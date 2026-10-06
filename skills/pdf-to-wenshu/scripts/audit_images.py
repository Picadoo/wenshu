#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全库图片盘点：按 PDF 里的图注条数对账「磁盘上有几张、正文嵌了几张」。

`lint_cluster` 只读 images.md 里那次抽图**当时**写下的覆盖结论——抽取算法改进之后，
早年入库的论文不会自动复查，漏掉的图就一直漏着。本脚本直接回 PDF 重扫图注，
几十秒盘完全库，把「图注比正文图多」的论文挑出来排队重抽。不改任何文件。

用法:
  python audit_images.py --vault "<VAULT>"            # 全库
  python audit_images.py --vault "<VAULT>" --paper Example2024   # 单篇（pid 子串）
  python audit_images.py --vault "<VAULT>" --all      # 连正常的也列出来
"""

import argparse
import datetime
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_images as E
from lint_cluster import CAPTION_COUNT

EMBED = re.compile(r'!\s*\[\[([^\]|#]+?)(?:\|[^\]]*)?\]\]')
FIGFILE = re.compile(r'_page\d+_(?:fig|pic)[A-Za-z]?\d+\.(?:png|jpe?g)$', re.I)


def backfill_caption_count(images_dir: Path, pid: str, ncap: int) -> bool:
    """把回 PDF 数出的图注条数写进 images.md，供 lint 拿它当图覆盖的分母。

    图注条数是 **PDF 本身的属性**，抽图算法怎么改都不会变，所以回填一次即长期有效
    ——这点和「覆盖缺失」那条结论不同，后者依赖当时的抽取算法、会过期。
    早期入库的论文（本库 95 篇里有 81 篇）根本没记这个数，lint 只好拿磁盘图片数
    当分母，于是过度抽取的论文被误报、抽取阶段就漏图的论文反而查不出来。
    """
    md = images_dir / (pid + '.images.md')
    if not md.is_file() or CAPTION_COUNT.search(md.read_text(encoding='utf-8')):
        return False
    stamp = datetime.date.today().isoformat()
    md.write_text(md.read_text(encoding='utf-8').rstrip() + '\n\n'
                  + '## 图注对账\n'
                  + '- 图注识别：回 PDF 重扫（共 %d 处）\n' % ncap
                  + '- 来源：audit_images.py --backfill %s\n' % stamp,
                  encoding='utf-8')
    return True


def audit_one(pdf: Path):
    """返回 (pid, 图注数, 磁盘图数, 正文嵌图数, 说明)；说明为空＝没问题。"""
    cluster, pid = pdf.parent.parent, pdf.stem
    images, art = cluster / 'images', cluster / 'content' / f'{pid}.正文.md'
    if not images.is_dir() or not art.exists():
        return None
    try:
        caps = E.scan_captions(str(pdf))
    except Exception as exc:
        return (pid, -1, 0, 0, f'PDF 扫不动（{type(exc).__name__}）——需人工确认这篇的图')
    nums = {c['num'] for c in caps}
    on_disk = [f for f in images.iterdir() if FIGFILE.search(f.name)]
    embedded = {n.strip() for n in EMBED.findall(art.read_text(encoding='utf-8'))}
    used = [f for f in on_disk if f.name in embedded]
    note = ''
    if nums and len(used) < len(nums):
        note = f'缺 {len(nums) - len(used)} 张：图注 {len(nums)} 条，正文只嵌 {len(used)} 张'
    return (pid, len(nums), len(on_disk), len(used), note)


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--vault', required=True)
    ap.add_argument('--paper', default='', help='只盘 pid 含该子串的论文')
    ap.add_argument('--all', action='store_true', help='正常的也列出来')
    ap.add_argument('--backfill', action='store_true',
                    help='把数出的图注条数写进还没记录它的 images.md，'
                         '让 lint_cluster 的图覆盖检查有正确的分母可用')
    args = ap.parse_args()

    papers = Path(args.vault) / 'Papers'
    if not papers.is_dir():
        sys.exit(f'找不到 {papers}')

    rows, filled = [], 0
    for pdf in sorted(papers.rglob('content/*.pdf')):
        if args.paper and args.paper.lower() not in pdf.stem.lower():
            continue
        r = audit_one(pdf)
        if r:
            rows.append(r)
            # 图注数为 0 多半是这篇的图注体例没被识别出来，写进去只会误导 lint
            if args.backfill and r[1] > 0 and backfill_caption_count(
                    pdf.parent.parent / 'images', pdf.stem, r[1]):
                filled += 1
    if args.backfill:
        print('回填图注条数：%d 篇 images.md\n' % filled)

    risky = [r for r in rows if r[4]]
    show = rows if args.all else risky
    print(f'盘点 {len(rows)} 篇，疑似漏图 {len(risky)} 篇\n')
    if show:
        print(f'{"pid":<50}{"图注":>5}{"磁盘":>5}{"正文":>5}  说明')
        for pid, ncap, ndisk, nused, note in sorted(show, key=lambda r: r[3] - r[1]):
            print(f'{pid[:48]:<50}{ncap:>5}{ndisk:>5}{nused:>5}  {note}')
        print('\n重抽命令（逐篇跑，跑完用 contact_sheet.py 看总览图核对）：')
        print('  python reextract_images.py "<clusterDir>"')
    return 1 if risky else 0


if __name__ == '__main__':
    sys.exit(main())
