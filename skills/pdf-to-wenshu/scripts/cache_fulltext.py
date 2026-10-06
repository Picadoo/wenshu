#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为已有 PDF 补全「全文文本缓存」`<pdf同名>.txt`（机器可读，0 token，供日后/别的 AI 复用）。

用法：
    python cache_fulltext.py <pdf> [<pdf> ...] [--force] [--quiet]
    python cache_fulltext.py --scan vault/Papers          # 扫目录补齐所有缺的

默认**跳过已存在**的 .txt：整库补缓存时不必每次重解析一遍全部 PDF；要重建加 `--force`。
"""

import argparse
import io
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_cluster import dump_pdf_text            # noqa: E402


def cache_one(pdf: Path, force: bool, quiet: bool) -> str:
    out = pdf.with_suffix('.txt')
    if out.is_file() and not force:
        if not quiet:
            print(f'{out.name}: 已存在，跳过')
        return 'skip'
    try:
        txt = dump_pdf_text(str(pdf))
    except Exception as exc:                           # noqa: BLE001 - 单篇解析失败不该中断整批
        print(f'{pdf.name}: 解析失败 {exc}', file=sys.stderr)
        return 'fail'
    out.write_text(txt, encoding='utf-8')
    if not quiet:
        print(f'{out.name}: {len(txt)} 字符')
    return 'done'


def main() -> None:
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    ap = argparse.ArgumentParser(description='为 PDF 补全全文文本缓存 <pdf同名>.txt')
    ap.add_argument('pdfs', nargs='*', help='PDF 路径，可多个')
    ap.add_argument('--scan', help='扫描该目录下所有 PDF（递归）')
    ap.add_argument('--force', action='store_true', help='已有 .txt 也重建')
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()

    targets = [Path(p) for p in args.pdfs]
    if args.scan:
        targets += sorted(Path(args.scan).rglob('*.pdf'))
    if not targets:
        ap.error('至少给一个 PDF，或用 --scan 指定目录')

    tally = {'done': 0, 'skip': 0, 'fail': 0, 'missing': 0}
    for pdf in targets:
        if not pdf.is_file():
            print('找不到 PDF:', pdf, file=sys.stderr)
            tally['missing'] += 1
            continue
        tally[cache_one(pdf, args.force, args.quiet)] += 1
    print('新建 %(done)d，跳过 %(skip)d，失败 %(fail)d，找不到 %(missing)d' % tally)
    if tally['fail'] or tally['missing']:
        sys.exit(1)


if __name__ == '__main__':
    main()
