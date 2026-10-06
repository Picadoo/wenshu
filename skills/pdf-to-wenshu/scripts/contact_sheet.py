#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把一篇论文的图拼成一张总览图，供人眼一屏核对裁切质量。

抽图脚本能查出「漏了几张」，查不出「这张切歪了」——后者只有看才知道。逐张点开
三十张图很慢，拼成一张总览图几秒就能看出谁被切了顶、谁只剩半幅、谁是碎片。

用法:
  python contact_sheet.py "<clusterDir>" [-o 输出.png] [--cols 5] [--all] [--flagged]

默认只拼**正文实际引用**的图（按正文出现顺序，这才是读者看到的）；
`--all` 拼 images/ 下全部图（含未引用的，用于审「无图注新图」）；
`--flagged` 只拼 images.md「## 图质检查」里标了问题的图。
"""

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote

WIKI_IMAGE = re.compile(r'!\s*\[\[([^\]|#]+?)(?:\|[^\]]*)?\]\]')
WEB_IMAGE = re.compile(r'!\[[^\]]*\]\(([^)]+)\)')


def pick(cluster: Path, mode: str):
    """返回 (图片路径列表, 说明)。"""
    images = cluster / 'images'
    if not images.is_dir():
        sys.exit(f'找不到 images/ 目录：{images}')

    def all_files(note: str):
        files = sorted((p for p in images.iterdir()
                        if p.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp')
                        and not p.name.startswith('_')),
                       key=sort_key)
        return files, note

    if mode == 'all':
        return all_files('images/ 全部图片')

    if mode == 'flagged':
        md = next(images.glob('*.images.md'), None)
        if not md:
            sys.exit('找不到 <pid>.images.md，无法读「## 图质检查」段')
        block = re.search(r'^## 图质检查\s*$(.*?)(?=^## |\Z)',
                          md.read_text(encoding='utf-8'), re.M | re.S)
        if not block:
            return [], '图质检查：无异常'
        names = [l.strip('- ').split('：')[0].strip()
                 for l in block.group(1).splitlines() if l.startswith('- ')]
        return [images / n for n in names if (images / n).exists()], '图质检查标记的图'

    # 抽完图、正文还没写的时候正是最该看总览的时刻，而那会儿正文一张图都没引用。
    # 原先这里直接退出，等于把「入库当场核对裁切质量」这一步废掉了——退回全量拼图。
    art = next((cluster / 'content').glob('*.正文.md'), None)
    if art is None:
        return all_files('images/ 全部图片（正文还没写，按页序排）')
    text = art.read_text(encoding='utf-8')
    names = [m.strip() for m in WIKI_IMAGE.findall(text)]
    if not names:                      # 已同步到前端的镜像用的是 web 链接
        names = [unquote(u).rsplit('/', 1)[-1] for u in WEB_IMAGE.findall(text)]
    files = [p for p in (images / unquote(n) for n in names) if p.exists()]
    if not files:
        return all_files('images/ 全部图片（正文尚无图引用，按页序排）')
    return files, f'{art.name} 引用顺序'


def sort_key(p: Path):
    m = re.search(r'page(\d+)_\D*(\d+)', p.stem)
    return (int(m.group(1)), int(m.group(2))) if m else (10 ** 6, 0)


def label_of(p: Path):
    m = re.search(r'page(\d+)_(fig|pic)(\d+)', p.stem)
    return f'p{m.group(1)} {m.group(2)}{m.group(3)}' if m else p.stem[-18:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cluster')
    ap.add_argument('-o', '--out', default='')
    ap.add_argument('--cols', type=int, default=5)
    ap.add_argument('--cell', type=int, default=330)
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--all', action='store_true', help='拼 images/ 下全部图')
    g.add_argument('--flagged', action='store_true', help='只拼图质检查标记的图')
    args = ap.parse_args()

    try:
        from PIL import Image, ImageDraw
    except ImportError:
        sys.exit('需要 Pillow：pip install Pillow')

    cluster = Path(args.cluster)
    mode = 'all' if args.all else 'flagged' if args.flagged else 'article'
    files, note = pick(cluster, mode)
    if not files:
        print(f'没有可拼的图（{note}）')
        return

    out = Path(args.out) if args.out else cluster / 'images' / '_总览.png'
    cell, cols = args.cell, max(1, args.cols)
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * cell, rows * cell), 'white')
    draw = ImageDraw.Draw(sheet)
    for i, p in enumerate(files):
        try:
            im = Image.open(p).convert('RGB')
        except Exception as exc:
            print(f'  跳过打不开的图 {p.name}: {exc}')
            continue
        w, h = im.size
        im.thumbnail((cell - 16, cell - 30))
        x, y = (i % cols) * cell, (i // cols) * cell
        sheet.paste(im, (x + 8, y + 24))
        draw.rectangle([x + 2, y + 2, x + cell - 2, y + cell - 2], outline='#bbb')
        draw.text((x + 10, y + 8), f'{i + 1}. {label_of(p)}  {w}x{h}', fill='#c00')
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print(f'{len(files)} 张（{note}）-> {out}  {sheet.width}x{sheet.height}')
    print('肉眼过一遍：谁顶部被切、谁只剩半幅面板、谁是碎片或空白。')


if __name__ == '__main__':
    main()
