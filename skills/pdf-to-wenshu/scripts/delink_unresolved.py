#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把笔记里"解析不到目标"的非嵌入 wikilink 去掉方括号变纯文本（保留嵌入 ![[图]]）。
子代理偶尔会给未入库的论文/生造术语加 [[]]，在图谱里成悬空节点；收尾跑一遍清掉。
用法：python delink_unresolved.py <vault> <file.md> [more.md ...]"""

import os
import re
import sys
import io

# 非嵌入 wikilink（前面不是 !），不含 # ^ 的块/标题引用
LINK = re.compile(r'(?<!\!)\[\[([^\]\|#\^]+)(\|[^\]]+)?\]\]')


def all_names(vault):
    s = set()
    for dp, _, fns in os.walk(vault):
        if os.sep + '.obsidian' in dp:
            continue
        for fn in fns:
            s.add(fn)
            if fn.endswith('.md'):
                s.add(fn[:-3])
    return s


def main():
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    vault = sys.argv[1]
    names = all_names(vault)

    def repl(m):
        tgt = m.group(1).strip()
        alias = m.group(2)
        if tgt in names:
            return m.group(0)                      # 能解析 -> 保留
        return alias[1:] if alias else tgt         # 解析不到 -> 去括号留文本

    for p in sys.argv[2:]:
        with open(p, encoding='utf-8') as f:
            t = f.read()
        n = LINK.sub(repl, t)
        if n != t:
            with open(p, 'w', encoding='utf-8') as f:
                f.write(n)
            print('已清理悬空链接:', os.path.basename(p))
        else:
            print('无悬空链接:', os.path.basename(p))


if __name__ == '__main__':
    main()
