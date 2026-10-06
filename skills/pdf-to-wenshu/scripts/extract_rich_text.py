#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从 PDF 抽带上下标的 dump：`<pid>.rich.txt`。

## 为什么要这份

`generate_cluster.dump_pdf_text()` 用的是 `page.get_text()`——纯文本模式**只返回字符，
丢掉字号与基线**，于是 `C_D` 被压成 `CD`、`v_∞^2` 压成 `v2∞`、`a_{p1}` 压成 `ap1`。
英文正文的行内公式全库为零（73 篇里 72 篇一处都没有），根子就在这里：
脚本拿到的原料本身就没有上下标，再怎么改也变不出来。

上下标信息 **PDF 里一直都在**。`get_text('dict')` 会给出每个 span 的字号与基线 y，
下标字号更小、基线更低，上标字号更小、基线更高。抽样 14 份 PDF，14 份全部可用
（上下标 span 127~1332 个/篇）。

## 为什么另存一份而不是改 `.txt`

`.txt` 有四个消费者：`build_refs` 找参考文献、`prep_article_en` 刨正文、
`lint_cluster.src_has_highlights` 判原刊有没有印 Highlights、检索层当全文缓存。
参考文献里的卷期号常常也是上标，直接改格式很可能打乱 `build_refs` 的匹配。
并存的代价只是多占一点磁盘，换来零回归，并且英文侧立刻可用。

## 为什么直接写 LaTeX 而不是自定义标记

这份 dump 的第一读者是做英文重排的 A1 子代理。写成 `C_{D}`、`v_{\\infty}^{2}`、
`\\log^{2}(Re)` 它抄起来就是 `$C_D$`，不必再学一套私有标记、也不会猜错嵌套层级。

## 阈值必须按篇自取

正文字号各篇不同（实测 8.0 / 8.1 / 9.0 / 10.0 / 10.9 都有），
所以基准取「本篇出现最多的字号」，绝不写死。
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

# 比正文小这么多才算上下标。实测下标普遍比正文小 2pt 以上，
# 取 0.6 既拦得住图注这类整体略小的字号，又不会漏掉小幅缩排的下标。
SIZE_GAP = 0.6
# 基线偏移超过这么多才判上下标；小于它说明只是同行里字号略有差异
BASE_GAP = 0.3
# 上下标片段最长几个字符。真下标都很短（D、p1、∞、max），
# 长的多半是整段小字（脚注、版权行），不能当上下标包起来
MAX_SCRIPT = 8

GREEK_TO_TEX = {
    'α': r'\alpha', 'β': r'\beta', 'γ': r'\gamma', 'δ': r'\delta', 'ε': r'\epsilon',
    'ζ': r'\zeta', 'η': r'\eta', 'θ': r'\theta', 'λ': r'\lambda', 'μ': r'\mu',
    'ν': r'\nu', 'ξ': r'\xi', 'π': r'\pi', 'ρ': r'\rho', 'σ': r'\sigma',
    'τ': r'\tau', 'ϕ': r'\phi', 'φ': r'\varphi', 'ψ': r'\psi', 'ω': r'\omega',
    '∞': r'\infty',
}


def tex_escape(s: str) -> str:
    """上下标内容里的希腊字母与无穷符号换成 LaTeX 命令，其余原样。"""
    return ''.join(GREEK_TO_TEX.get(ch, ch) for ch in s)


def body_size(doc) -> float:
    """本篇的正文字号 = 出现最多的那个字号。每篇自取，绝不写死。"""
    c: collections.Counter = collections.Counter()
    for page in doc:
        for blk in page.get_text('dict').get('blocks', []):
            for line in blk.get('lines', []):
                for sp in line.get('spans', []):
                    if sp['text'].strip():
                        c[round(sp['size'], 1)] += len(sp['text'].strip())
    return c.most_common(1)[0][0] if c else 0.0


def classify_span(sp: dict, base_size: float, base_y: float) -> str:
    """这个 span 是正常文字、上标还是下标。"""
    txt = sp['text'].strip()
    if not txt or len(txt) > MAX_SCRIPT or sp['size'] > base_size - SIZE_GAP:
        return 'text'
    dy = sp['origin'][1] - base_y
    if dy > BASE_GAP:
        return 'sub'
    if dy < -BASE_GAP:
        return 'sup'
    return 'text'


def render_line(spans: list, body: float) -> str:
    """把一行 span 还原成带 `_{}` / `^{}` 的文本。

    同类相邻的 span 要先合并再包：`a_{p}_{1}` 是错的，`a_{p1}` 才对
    （实测 `ap1` 就是 `a` + 8pt 的 `p` + 6pt 的 `1` 三个 span）。
    """
    spans = [s for s in spans if s['text'].strip() or s['text'] == ' ']
    if not spans:
        return ''
    real = [s for s in spans if s['text'].strip()]
    if not real:
        return ''
    anchor = max(real, key=lambda s: s['size'])
    base_y, base_size = anchor['origin'][1], max(body, anchor['size'])

    out, buf, kind = [], '', 'text'

    def flush():
        nonlocal buf, kind
        if not buf:
            return
        if kind == 'text':
            out.append(buf)
        else:
            mark = '^' if kind == 'sup' else '_'
            out.append('%s{%s}' % (mark, tex_escape(buf.strip())))
        buf = ''

    for sp in spans:
        k = classify_span(sp, base_size, base_y)
        if k != kind:
            flush()
            kind = k
        buf += sp['text']
    flush()
    return ''.join(out)


def build_rich_text(pdf_path, max_chars: int = 600000) -> str:
    try:
        import pymupdf
    except ImportError:                                     # pragma: no cover
        try:
            import fitz as pymupdf
        except ImportError:
            return ''
    doc = pymupdf.open(str(pdf_path))
    try:
        body = body_size(doc)
        parts = []
        for i, page in enumerate(doc):
            parts.append('\n\n----- Page %d -----\n\n' % (i + 1))
            for blk in page.get_text('dict').get('blocks', []):
                for line in blk.get('lines', []):
                    s = render_line(line.get('spans', []), body)
                    if s.strip():
                        parts.append(s.rstrip() + '\n')
                parts.append('\n')
    finally:
        doc.close()
    txt = ''.join(parts).strip()
    return txt[:max_chars] if len(txt) > max_chars else txt


def count_scripts(txt: str) -> int:
    return len(re.findall(r'[_^]\{[^}]{1,8}\}', txt))


def main() -> None:
    ap = argparse.ArgumentParser(description='抽带上下标的 PDF dump（<pid>.rich.txt）')
    ap.add_argument('--vault', help='全库回填：给每个有 PDF 的集群补一份 rich dump')
    ap.add_argument('--pdf', help='单篇 PDF 路径')
    ap.add_argument('--out', help='单篇输出路径；不给则打印到 stdout')
    ap.add_argument('--only', help='--vault 模式下只处理 pid 前缀匹配的')
    ap.add_argument('--force', action='store_true', help='已存在也重新生成')
    a = ap.parse_args()

    if a.pdf:
        txt = build_rich_text(a.pdf)
        if a.out:
            Path(a.out).write_text(txt, encoding='utf-8')
            print('%s  %d 字符 / 上下标 %d 处' % (a.out, len(txt), count_scripts(txt)))
        else:
            sys.stdout.write(txt)
        return

    if not a.vault:
        ap.error('要么给 --pdf，要么给 --vault')

    done = skipped = 0
    for pdf in sorted(Path(a.vault).rglob('content/*.pdf')):
        pid = pdf.stem
        if a.only and not pid.startswith(a.only):
            continue
        out = pdf.with_name(pid + '.rich.txt')
        if out.is_file() and not a.force:
            skipped += 1
            continue
        try:
            txt = build_rich_text(pdf)
        except Exception as exc:                            # PDF 坏了不该中断全库
            print('%-46s 抽取失败：%s' % (pid[:46], str(exc)[:50]))
            continue
        if not txt:
            print('%-46s 抽不出文本' % pid[:46])
            continue
        out.write_text(txt, encoding='utf-8')
        print('%-46s %7d 字符 / 上下标 %4d 处' % (pid[:46], len(txt), count_scripts(txt)))
        done += 1
    print('新生成 %d 份，已存在跳过 %d 份' % (done, skipped))


if __name__ == '__main__':
    main()
