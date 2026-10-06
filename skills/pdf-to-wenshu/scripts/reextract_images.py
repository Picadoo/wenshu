#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重抽已入库论文的图片，并按图注编号把正文嵌入自动改写到新文件名。

用法:
  python reextract_images.py "<clusterDir>" [--dry-run]

<clusterDir> 是论文集群目录（含 content/ 与 images/）。流程：
1. 解析旧正文：每个 ![[嵌入]] → 其下方图注（跳过空行与图组的后续图行）→ 图键（图5/表1/图形摘要）。
2. 调 extract_images.py 重抽（清掉同前缀旧图，layout 优先）。
3. 解析新 images.md：图键 → 新文件名；无图注的新图单列（人工审：拆开的面板→图组补嵌，商标/廃图→删）。
4. 按图键把 正文/正文.en/notes 里的旧文件名替换为新文件名；旧图组多张映射到同一新图时去重。
5. 打印报告。审图、删废图、lint、sync 由调用方完成。
"""

import argparse
import io
import re
import subprocess
import sys
from pathlib import Path

WIKI_IMAGE = re.compile(r'!\s*\[\[([^\]|#]+?)(?:\|[^\]]*)?\]\]')
FIG_KEY = re.compile(r'(?:图|Fig(?:ure)?\.?)\s*(?:([A-Za-z])\s*\.\s*)?(\d+)', re.I)
TAB_KEY = re.compile(r'(?:表|Table)\s*(\d+)', re.I)
GA_KEY = re.compile(r'图形摘要|Graphical\s+abstract', re.I)


def caption_key(text):
    """图注文本 → 归一化图键；识别不了返回 None。"""
    t = text.strip().lstrip('*_ ').strip()
    if GA_KEY.search(t[:30]):
        return '图形摘要'
    m = TAB_KEY.match(t)
    if m:
        return f'表{int(m.group(1))}'
    m = FIG_KEY.match(t)
    if m:
        app = (m.group(1) or '').upper()
        num = int(m.group(2))
        return f'图{app}.{num}' if app else f'图{num}'
    return None


def parse_article_embeds(text):
    """正文 → [(旧文件名, 图键或None)]；图组成员共享其后第一条图注。"""
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines):
        m = WIKI_IMAGE.search(line)
        if not m:
            continue
        name = m.group(1).strip()
        key = None
        for j in range(i + 1, len(lines)):
            nxt = lines[j].strip()
            if not nxt or WIKI_IMAGE.search(nxt):
                continue          # 图组成员、空行都跳过，共享其后第一条图注
            key = caption_key(nxt)
            break
        out.append((name, key))
    return out


def parse_images_md(path):
    """新 images.md → (图键→新文件名, 无图注文件列表)。"""
    entries = []
    cur = None
    for line in path.read_text(encoding='utf-8').splitlines():
        m = re.match(r'- 文件名：(.+)', line.strip())
        if m:
            cur = {'name': m.group(1).strip(), 'cap': ''}
            entries.append(cur)
            continue
        m = re.match(r'- 图注：(.+)', line.strip())
        if m and cur is not None:
            cur['cap'] = m.group(1).strip()
    keyed, orphan = {}, []
    for e in entries:
        key = caption_key(e['cap']) if e['cap'] else None
        if key and key not in keyed:
            keyed[key] = e['name']
        elif key:
            orphan.append(f"{e['name']}（与 {keyed[key]} 同图注 {key}，疑似拆开的面板）")
        else:
            orphan.append(e['name'])
    return keyed, orphan


def dedupe_embeds(text):
    """旧图组多张 → 同一新图时会产生重复嵌入行（可能隔空行），压成一行。
    同一图注被拆成两组面板时，改写后还会留下两套「嵌入+图注」；整块也要压掉。"""
    lines = text.splitlines()
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if WIKI_IMAGE.search(line):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            cap = lines[j] if j < len(lines) else ''
            block = [ln.strip() for ln in lines[i:j + 1] if ln.strip()]
            prev = []
            k = len(out) - 1
            while k >= 0 and len(prev) < len(block):
                if out[k].strip():
                    prev.insert(0, out[k].strip())
                k -= 1
            if block and block == prev:
                i = j + 1 if cap else i + 1
                continue
        out.append(line)
        i += 1
    return '\n'.join(out) + ('\n' if text.endswith('\n') else '')


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('cluster')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--no-layout', action='store_true',
                    help='跳过版面级、用图注裁切整图重抽（layout 拆碎复合图时用）')
    args = ap.parse_args()

    cluster = Path(args.cluster)
    content, images = cluster / 'content', cluster / 'images'
    pdfs = list(content.glob('*.pdf'))
    if len(pdfs) != 1:
        sys.exit(f'期望 content/ 里恰好 1 个 PDF，实际 {len(pdfs)}')
    pdf = pdfs[0]
    pid = pdf.stem
    index_md = images / f'{pid}.images.md'
    article = content / f'{pid}.正文.md'
    targets = [article, content / f'{pid}.正文.en.md', content / f'{pid}.notes.md']
    targets = [t for t in targets if t.exists()]

    # 1) 旧映射：文件名 → 图键
    old_map = {}
    for name, key in parse_article_embeds(article.read_text(encoding='utf-8')):
        old_map.setdefault(name, key)

    # 2) 重抽
    if not args.dry_run:
        cmd = [sys.executable, str(Path(__file__).parent / 'extract_images.py'),
               str(pdf), str(images), str(index_md), '--prefix', pid]
        if args.no_layout:
            cmd.append('--no-layout')
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if r.returncode != 0:
            sys.exit(f'extract_images 失败:\n{r.stderr[-2000:]}')
        cov = [l for l in r.stdout.splitlines() if l.startswith('COVERAGE')]
        print(f'== {pid}\n重抽完成 {cov[0] if cov else ""}')

    # 3) 新映射：图键 → 新文件名
    keyed, orphan = parse_images_md(index_md)

    # 4) 改写嵌入
    rename, unmapped = {}, []
    for old, key in old_map.items():
        new = keyed.get(key) if key else None
        if new and new != old:
            rename[old] = new
        elif not new:
            unmapped.append((old, key))
    if rename and not args.dry_run:
        pat = re.compile('|'.join(re.escape(k) for k in sorted(rename, key=len, reverse=True)))
        for t in targets:
            txt = t.read_text(encoding='utf-8')
            new_txt, n = pat.subn(lambda m: rename[m.group(0)], txt)
            new_txt = dedupe_embeds(new_txt)
            if new_txt != txt:
                t.write_text(new_txt, encoding='utf-8')
                print(f'  改写 {t.name}: {n} 处')

    # 5) 报告
    exist = {f.name for f in images.iterdir() if f.suffix.lower() in ('.png', '.jpg', '.jpeg')}
    dangling = []
    for t in targets:
        for m in WIKI_IMAGE.finditer(t.read_text(encoding='utf-8')):
            if m.group(1).strip() not in exist:
                dangling.append(f'{t.name}: {m.group(1).strip()}')
    print(f'  映射替换 {len(rename)} 名；图键配对 {len(keyed)}')
    if unmapped:
        print('  ⚠️ 未映射旧嵌入（需人工处理）:')
        for old, key in unmapped:
            print(f'    - {old} (图键 {key})')
    if orphan:
        print('  ⚠️ 无图注新图（人工审：面板拆块→图组补嵌 / 商标廃图→删）:')
        for o in orphan:
            print(f'    - {o}')
    if dangling:
        print('  ❌ 嵌入指向不存在文件:')
        for d in dangling:
            print(f'    - {d}')


if __name__ == '__main__':
    main()
