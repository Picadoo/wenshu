#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
扫描 PDF 收件箱，用内容指纹(sha256)做去重，列出"尚未入库"的新论文。

去重逻辑：遍历 Papers 目录下所有 *.md，读取 frontmatter 里的 sourceHash（仅 index 笔记有该
字段；布局 v2 的 index 是子类层的 <pid>.md，不再是 *.index.md），组成已入库集合；
收件箱里 sha256 不在该集合中的 PDF 即为新论文。

输出：JSON 数组到 stdout，每项 {path, filename, sha256}；日志走 stderr。
用法：
    python scan_inbox.py --vault G:/每日论文/每日论文
    python scan_inbox.py --vault <vault> --pdf-dir <dir> --papers-dir <dir>
"""

import os
import sys
import json
import glob
import argparse
import hashlib
import logging

logger = logging.getLogger(__name__)


def sha256_of(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return "sha256:" + h.hexdigest()


def collect_existing_hashes(papers_dir):
    """从所有 *.index.md 的 frontmatter 收集已入库的 sourceHash。"""
    seen = set()
    if not os.path.isdir(papers_dir):
        return seen
    # 布局 v2：index 不再是 *.index.md，而是子类层的 <pid>.md（frontmatter 含 noteType: index + sourceHash）。
    # 旧代码 glob '*.index.md' 匹配 0 个 → 去重永远失效、会重复入库。改为扫所有 *.md，
    # 凡 frontmatter 里有 sourceHash 的即已入库论文（只有 index 才有该字段）。
    for idx in glob.glob(os.path.join(papers_dir, '**', '*.md'), recursive=True):
        try:
            with open(idx, 'r', encoding='utf-8') as f:
                started = False
                for _ in range(50):
                    line = f.readline()
                    if not line:
                        break
                    s = line.strip()
                    if s == '---':
                        if not started:
                            started = True
                            continue
                        break  # frontmatter 结束
                    if s.startswith('sourceHash:'):
                        val = s.split(':', 1)[1].strip().strip('"').strip("'")
                        if val:
                            seen.add(val)
                        break
        except (IOError, OSError) as e:
            logger.warning("读取索引失败 %s: %s", idx, e)
    return seen


def main():
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(levelname)s] %(message)s',
                        datefmt='%H:%M:%S', stream=sys.stderr)

    ap = argparse.ArgumentParser(description='扫描收件箱并按 sourceHash 去重')
    ap.add_argument('--vault', required=True, help='文库 vault 根路径')
    ap.add_argument('--pdf-dir', default=None, help='PDF 收件箱(默认 vault/99_System/PDFs)')
    ap.add_argument('--papers-dir', default=None, help='笔记目录(默认 vault/20_Research/Papers)')
    args = ap.parse_args()

    pdf_dir = args.pdf_dir or os.path.join(args.vault, 'PDFs')
    papers_dir = args.papers_dir or os.path.join(args.vault, 'Papers')

    existing = collect_existing_hashes(papers_dir)
    logger.info("已入库指纹数: %d", len(existing))

    new_items = []
    pdfs = sorted(glob.glob(os.path.join(pdf_dir, '*.pdf')))
    for p in pdfs:
        try:
            digest = sha256_of(p)
        except (IOError, OSError) as e:
            logger.warning("无法读取 %s: %s", p, e)
            continue
        if digest in existing:
            logger.info("跳过(已入库): %s", os.path.basename(p))
            continue
        new_items.append({
            'path': p,
            'filename': os.path.basename(p),
            'sha256': digest,
        })

    logger.info("收件箱共 %d 个 PDF，其中新论文 %d 个", len(pdfs), len(new_items))
    print(json.dumps(new_items, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
