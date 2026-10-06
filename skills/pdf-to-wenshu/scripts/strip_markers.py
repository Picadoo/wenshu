#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""收尾：去掉笔记里用于填充定位的构造标记 <!--XXX-->（保留其间已填内容）。
内容全部填好后对 index / 正文 / notes 跑一遍，让成稿不残留这些印记。
"""

import re
import sys
import io
import argparse

# 一次性构造标记（RELATED 现按标题锚定，这里也把残留的旧 RELATED 标记一并清掉）
# HINT 是骨架里写给 AI 的填写提示，成稿一律清掉，人不该看到
TAGS = r'<!--(?:/?(?:SCI_Q|TLDR|SCORE|RELATED|KEYPOINTS|QA|ARTICLE_EN|ARTICLE|ORIGINAL)|TERMS_(?:START|END)|HINT[^>]*)-->'


def strip(text):
    text = re.sub(TAGS, '', text)
    text = re.sub(r'[ \t]+\n', '\n', text)      # 行尾空格
    text = re.sub(r'\n{3,}', '\n\n', text)      # 多余空行收敛
    return text


def main():
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    ap = argparse.ArgumentParser(description='去掉构造标记 <!--XXX-->')
    ap.add_argument('files', nargs='+', help='要清理的 md 文件路径')
    args = ap.parse_args()

    n = 0
    for p in args.files:
        try:
            with open(p, encoding='utf-8') as f:
                t = f.read()
        except IOError as e:
            print(f'跳过 {p}: {e}', file=sys.stderr)
            continue
        s = strip(t)
        if s != t:
            with open(p, 'w', encoding='utf-8') as f:
                f.write(s)
            n += 1
            print(f'已清理标记: {p}')
        else:
            print(f'无需清理: {p}')
    print(f'共清理 {n} 个文件')


if __name__ == '__main__':
    main()
