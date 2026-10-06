#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把英文正文里跑马文字状的参考文献拆成 `## References` 一节，一条一行。

## 为什么需要这个

2026-09-01 实测：英文正文 73 篇里只有 **6 篇**有 `## References` 节（8%），
而中文侧 100% 有 `## 参考文献`——因为**中文侧 lint 查这条，英文侧不查**。

那 67 篇的文献表不是没有，是烂着：没有标题、揉进上一段、和 `O RC I D` 粘在一起、
一行挤好几条。Example2024 那篇长这样：

    …available in the Mendeley data repository.[82] O RC I D NikolaosN.Vlassis
    WaiChingSun Khalid A.Alshibli Richard A.Regueiro R E F E R E N C E S
    1. Beiser V. Why the world is running out of sand. BBC Future. 2019:18.

## 判据

- **标签必须独占一行或是拉开排的形态**。用宽松的 `References` 直接搜会命中
  `Reference velocity` 这类正文词组——实测误判了好几篇。
- **拆出的条目少于 5 条就不动**，交给 A1。宁可不改，也不要把正文切碎。
- **只认「数字 + 点 + 大写字母」这一种编号体例**（实测全库 37 篇都是它）；
  方括号 `[N]`、作者年份等体例留给 A1，不猜。
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

# 拉开排的 `R E F E R E N C E S`，或独占一行的 References / Bibliography
LABEL_SPACED = re.compile(r'R\s+E\s+F\s+E\s+R\s+E\s+N\s+C\s+E\s*S?')
LABEL_LINE = re.compile(r'^\s*(?:REFERENCES|References|Bibliography|BIBLIOGRAPHY)\s*:?\s*$', re.M)
# 文献表之前常粘着的 ORCID 段（同样是拉开排的标签）
ORCID = re.compile(r'O\s*RC\s*I\s*D\b.*?(?=R\s+E\s+F\s+E\s+R|$)', re.S)
HEAD = re.compile(r'^##\s+References\s*$', re.M | re.I)
# 一条条目的起点：句末之后跟「数字 + 点 + 空格 + 大写」
ENTRY_SPLIT = re.compile(r'(?<=[.\d\)])\s+(?=\d{1,3}\.\s+[A-Z])')
ENTRY_HEAD = re.compile(r'^(\d{1,3})\.\s+(.+)$', re.S)
CITE_TAIL = re.compile(r'\n*\s*How to cite this article:.*$', re.S)
MIN_ENTRIES = 5


def find_label(text: str):
    """返回文献表标签的 `(起, 止)`；找不到返回 None。"""
    best = None
    for m in LABEL_SPACED.finditer(text):
        best = m                      # 取最后一个：正文里讨论 references 的地方在前
    if best:
        return best.start(), best.end()
    hits = list(LABEL_LINE.finditer(text))
    return (hits[-1].start(), hits[-1].end()) if hits else None


def split_entries(block: str) -> list:
    """把跑马文字切成条目。切不出足够多条就返回空，让调用方放弃。"""
    block = re.sub(r'\s+', ' ', block).strip()
    items = [x.strip() for x in ENTRY_SPLIT.split(block) if x.strip()]
    out = []
    for it in items:
        m = ENTRY_HEAD.match(it)
        out.append('%s. %s' % (m.group(1), m.group(2).strip()) if m else it)
    return out if len(out) >= MIN_ENTRIES else []


def _refs_parser():
    """借 build_refs 的解析器。判据只写一份——中文侧的 `## 参考文献` 就是它切出来的。

    它读的是 `<pid>.txt`（PDF 原文 dump），不是中文正文，
    所以「英文侧不许依赖中文侧」这条架构约束不受影响。
    """
    import importlib.util
    src = Path(__file__).resolve().parent / 'build_refs.py'
    spec = importlib.util.spec_from_file_location('build_refs_for_en', src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def from_source(src_txt: str) -> list:
    """英文正文里压根没有文献表时，从原文 dump 解析。

    实测 73 篇里 **65 篇**是这个状态——`prep_article_en` 按旧规矩「References 一节
    不收录」在 STOP_HEAD 处把文章截断了，文献表根本没进英文正文。
    所以对这批而言，「拆条」是不够的，得先把它取回来。
    """
    if not src_txt:
        return []
    try:
        bf = _refs_parser()
        lines = bf.locate_refs_segment(src_txt)
        if not lines:
            return []
        _style, items = bf.clean_and_group(lines)
    except Exception:
        return []
    out = ['%d. %s' % (no, re.sub(r'\s+', ' ', text).strip()) for no, text in items]
    return out if len(out) >= MIN_ENTRIES else []


def normalize(article: str, src_txt: str = ''):
    """返回 `(新正文, 动作, 条数)`。"""
    if HEAD.search(article):
        return article, '已是标题节', 0
    pos = find_label(article)
    if not pos:
        entries = from_source(src_txt)
        if not entries:
            return article, '原文也解析不出（派 A1）', 0
        out = article.rstrip() + '\n\n## References\n\n' + '\n'.join(entries) + '\n'
        return out, '从原文补', len(entries)
    body, block = article[:pos[0]], article[pos[1]:]
    tail = CITE_TAIL.search(block)
    cite = tail.group(0).strip() if tail else ''
    if tail:
        block = block[:tail.start()]
    entries = split_entries(block)
    if not entries:
        return article, '切不出条目（派 A1）', 0
    body = ORCID.sub('', body).rstrip()
    out = body + '\n\n## References\n\n' + '\n'.join(entries)
    if cite:
        out += '\n\n> %s' % re.sub(r'\s+', ' ', cite)
    return re.sub(r'\n{3,}', '\n\n', out) + '\n', '已拆条', len(entries)


def main() -> None:
    ap = argparse.ArgumentParser(description='英文正文参考文献拆成 ## References 节')
    ap.add_argument('--vault', required=True)
    ap.add_argument('--out', help='草稿目录；不给则原地改写')
    ap.add_argument('--only')
    a = ap.parse_args()

    outdir = Path(a.out) if a.out else None
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)
    tally: dict = {}
    for en in sorted(Path(a.vault).rglob('content/*.正文.en.md')):
        pid = en.name[:-len('.正文.en.md')]
        if a.only and not pid.startswith(a.only):
            continue
        txt = en.with_name(pid + '.txt')
        new, action, n = normalize(en.read_text(encoding='utf-8', errors='replace'),
                                   txt.read_text(encoding='utf-8', errors='replace')
                                   if txt.is_file() else '')
        tally[action] = tally.get(action, 0) + 1
        if action in ('已拆条', '从原文补'):
            (outdir / en.name if outdir else en).write_text(new, encoding='utf-8')
            print('%-44s %s %3d 条' % (pid[:44], action, n))
    print()
    for k, v in sorted(tally.items(), key=lambda x: -x[1]):
        print('  %-18s %d 篇' % (k, v))


if __name__ == '__main__':
    main()
