#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把已建集群迁移到新命名/新结构（确定性，一次性整理用）：
1) 全库把 old_pid 文本替换成 new_pid（更新所有 wikilink/图片嵌入/registry/MOC/相关论文）
2) 集群内文件名里的 old_pid 改成 new_pid（含 images 里的图）
3) 重整为：外露 <new_pid>.index.md，content/ 放 md+notes+pdf，images/ 不动
4) 集群文件夹改名为 new_folder（全标题）
old_pid 是唯一 token，全库替换安全、不误伤。
"""

import os
import re
import sys
import io
import glob
import shutil
import argparse


def replace_in_files(root, old, new):
    n = 0
    for dp, _, fns in os.walk(root):
        for fn in fns:
            if fn.endswith('.md') or fn == '_registry.json':
                p = os.path.join(dp, fn)
                try:
                    with open(p, encoding='utf-8') as f:
                        t = f.read()
                except (IOError, UnicodeDecodeError):
                    continue
                if old in t:
                    with open(p, 'w', encoding='utf-8') as f:
                        f.write(t.replace(old, new))
                    n += 1
    return n


def rename_in_dir(d, old, new):
    for dp, _, fns in os.walk(d):
        for fn in fns:
            if old in fn:
                os.rename(os.path.join(dp, fn), os.path.join(dp, fn.replace(old, new)))


def main():
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    ap = argparse.ArgumentParser(description='集群改名/重整结构')
    ap.add_argument('--vault', required=True)
    ap.add_argument('--old-pid', required=True)
    ap.add_argument('--new-pid', required=True)
    ap.add_argument('--new-folder', required=True)
    args = ap.parse_args()

    papers = os.path.join(args.vault, 'Papers')
    hits = glob.glob(os.path.join(papers, '**', f'{args.old_pid}.index.md'), recursive=True)
    if not hits:
        print('找不到集群:', args.old_pid)
        sys.exit(1)
    cluster = os.path.dirname(hits[0])

    nrep = replace_in_files(args.vault, args.old_pid, args.new_pid)
    print(f'① 全库文本替换 {args.old_pid} -> {args.new_pid}: {nrep} 个文件')

    rename_in_dir(cluster, args.old_pid, args.new_pid)
    print('② 集群内文件已改名')

    content = os.path.join(cluster, 'content')
    os.makedirs(content, exist_ok=True)
    for nm in (f'{args.new_pid}.md', f'{args.new_pid}.notes.md', f'{args.new_pid}.pdf'):
        src = os.path.join(cluster, nm)
        if os.path.exists(src):
            shutil.move(src, os.path.join(content, nm))
    print('③ md/notes/pdf 已收进 content/，index 留外层')

    parent = os.path.dirname(cluster)
    newdir = os.path.join(parent, args.new_folder)
    if os.path.abspath(cluster) != os.path.abspath(newdir):
        os.rename(cluster, newdir)
        cluster = newdir
    print('④ 文件夹改名 ->', os.path.basename(cluster))

    print('--- 迁移后结构 ---')
    for dp, dns, fns in os.walk(cluster):
        rel = os.path.relpath(dp, cluster)
        prefix = '' if rel == '.' else rel + '/'
        for fn in sorted(fns):
            print('  ', prefix + fn)


if __name__ == '__main__':
    main()
