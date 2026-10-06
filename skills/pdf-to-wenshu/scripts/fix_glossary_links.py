#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把笔记里表格内的 [[base\\|中文名]] 转成 [[base]] 中文名（去掉会断链的转义竖线）。"""

import sys
import re
import io

PAT = re.compile(r'\[\[([^\\\]|]+)\\\|([^\]]+)\]\]')
# 把"引文式"的悬空 wikilink 去括号变纯文本（子代理偶尔给未入库论文也加了[[]]）
CITE = re.compile(r'\[\[([^\]\|]*(?:et al\.|\([12]\d{3}\))[^\]\|]*)\]\]')


def main():
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    for p in sys.argv[1:]:
        with open(p, encoding='utf-8') as f:
            t = f.read()
        n = PAT.sub(r'[[\1]] \2', t)
        n = CITE.sub(r'\1', n)
        if n != t:
            with open(p, 'w', encoding='utf-8') as f:
                f.write(n)
            print('已修复表格链接:', p)
        else:
            print('无需修复:', p)


if __name__ == '__main__':
    main()
