#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把已入库论文集群搬到另一个领域文件夹（改分类，确定性）：
1) 找到 Papers/**/<pid>.md 索引与同级集群文件夹（content/ 里有 <pid>.* 的那个）
2) 移动 索引 + 集群文件夹 到 Papers/<新大类/子类>/
3) 改索引 frontmatter 的 domain 字段
pid/citekey 不变：互链 [[pid]] 与 Web slug/分享链接全部不受影响。
收尾需重跑：build_index.py + build_bib.py + wenshu sync-vault.py（本脚本会提示）。

用法：
  python move_cluster.py --vault <VAULT> --pid "<pid>" --new-domain "大类/子类"
"""

import io
import re
import sys
import glob
import shutil
import argparse
from pathlib import Path


def main():
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    ap = argparse.ArgumentParser(description='集群跨领域搬家（改分类）')
    ap.add_argument('--vault', required=True)
    ap.add_argument('--pid', required=True)
    ap.add_argument('--new-domain', required=True, help='如 泥沙输运/离散模拟')
    args = ap.parse_args()

    papers = Path(args.vault) / 'Papers'
    hits = glob.glob(str(papers / '**' / f'{args.pid}.md'), recursive=True)
    hits = [h for h in hits if Path(h).parent.name not in ('content',)]
    if not hits:
        print(f'找不到索引: {args.pid}.md')
        sys.exit(1)
    index_path = Path(hits[0])
    old_dir = index_path.parent

    cluster = None
    for sub in old_dir.iterdir():
        if sub.is_dir() and list((sub / 'content').glob(f'{args.pid}.*')):
            cluster = sub
            break
    if cluster is None:
        print(f'找不到集群文件夹（content/ 下应有 {args.pid}.*）')
        sys.exit(1)

    new_dir = papers / args.new_domain
    if new_dir.resolve() == old_dir.resolve():
        print('目标领域与当前相同，无需搬家')
        sys.exit(0)
    new_dir.mkdir(parents=True, exist_ok=True)

    shutil.move(str(index_path), str(new_dir / index_path.name))
    shutil.move(str(cluster), str(new_dir / cluster.name))
    print(f'① 已移动: {index_path.name} + {cluster.name}/')
    print(f'   {old_dir.relative_to(papers)} -> {args.new_domain}')

    new_index = new_dir / index_path.name
    text = new_index.read_text(encoding='utf-8')
    new_text, n = re.subn(
        r'^domain:\s*.*$', f'domain: {args.new_domain}', text, count=1, flags=re.M
    )
    if n:
        new_index.write_text(new_text, encoding='utf-8')
        print(f'② frontmatter domain -> {args.new_domain}')
    else:
        print('② 警告: 索引里没找到 domain 字段，请手动核对')

    # 旧子类文件夹空了就顺手删掉（只删空目录，安全）
    try:
        old_dir.rmdir()
        print(f'③ 旧领域文件夹已空，删除: {old_dir.relative_to(papers)}')
    except OSError:
        print(f'③ 旧领域文件夹仍有其他论文，保留: {old_dir.relative_to(papers)}')

    print('收尾请重跑: build_index.py + build_bib.py + wenshu-pro/scripts/sync-vault.py')


if __name__ == '__main__':
    main()
