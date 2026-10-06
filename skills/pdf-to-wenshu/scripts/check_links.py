#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 vault 内所有 [[wikilink]] / ![[embed]] 是否能按 basename 解析（找断链）。"""

import os
import re
import sys
import io

LINK = re.compile(r'!?\[\[([^\]\|#\^]+)')


def main():
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    vault = sys.argv[1]
    names = set()
    for dp, _, fns in os.walk(vault):
        if os.sep + '.obsidian' in dp:
            continue
        for fn in fns:
            names.add(fn)                       # 全名(含 .pdf/.png/.txt)
            if fn.endswith('.md'):
                names.add(fn[:-3])              # 笔记名(去 .md)
    broken = []
    for dp, _, fns in os.walk(vault):
        if os.sep + '.obsidian' in dp:
            continue
        for fn in fns:
            if not fn.endswith('.md'):
                continue
            with open(os.path.join(dp, fn), encoding='utf-8') as f:
                t = f.read()
            t = re.sub(r'```.*?```', '', t, flags=re.S)   # 跳过代码块(含 dataview)，避免误报
            t = re.sub(r'`[^`\n]*`', '', t)               # 跳过行内代码
            for m in LINK.finditer(t):
                tgt = m.group(1).strip()
                if tgt and tgt not in names:
                    broken.append((fn, tgt))
    print(f'断链数: {len(broken)}')
    seen = set()
    for fn, tgt in broken:
        key = (fn, tgt)
        if key in seen:
            continue
        seen.add(key)
        print(f'  {fn}  ->  [[{tgt}]]')


if __name__ == '__main__':
    main()
