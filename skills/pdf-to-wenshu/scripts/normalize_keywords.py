#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把英文正文的关键词统一成 `## Keywords` 节。

## 为什么需要这个

`luna-a1-brief.md` 的 11 条产出要求里**一个字都没提 Keywords**，脚本侧也没有规则，
于是全库 73 篇的形态完全靠运气（2026-09-01 实测）：

```
## Keywords 节        29 篇
**Keywords** 加粗行     6 篇
K E Y WO R D S 原样     2 篇   ← 期刊把字母拉开排，抽文本时原样带进来
其它形态               11 篇
完全没有               25 篇   ← 其中 18 篇原刊明明印了
```

对照之下 `luna-a-brief.md` 对中文侧写死了「摘要末尾必须有 `**关键词：**` 行」，
**英文侧的契约就是漏了**。这个脚本补形态统一那一半，
`lint_cluster.check_keywords()` 补检测那一半，A1 任务包补要求那一半。

## 判据

- **原刊印了才写**。跟 Highlights 同一个口径：`.txt` 里找不到关键词字样就不许硬造。
- **只做确定性的形态搬运**，不做语义提取：能从原文干净截出关键词串的就补，
  截不干净的留给 A1，不猜。
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

# 期刊常把标签字母拉开排：`K E Y WO R D S`、`KEY WORDS`、`Keywords:`
KW_LABEL = r'K\s?E\s?Y\s?\s?W\s?O?\s?R\s?D\s?S|Key\s*words?|Keywords?'
ART_LABEL = re.compile(r'^\s*(?:%s)\s*[:：]?\s*' % KW_LABEL, re.I)
# 正文里已有的三种形态
HEAD_SEC = re.compile(r'^##\s+Keywords\s*$', re.M | re.I)
BOLD_LINE = re.compile(r'^\*\*Keywords?\s*[:：]?\*\*\s*(.+)$', re.M | re.I)
RAW_LINE = re.compile(r'^(?:%s)\s*[:：]?\s*(.+)$' % KW_LABEL, re.M)
# 关键词串到哪里为止。**必须认拉开排的 `A B S T R A C T`**：不少 PDF 里关键词块与
# 摘要之间没有空行，只靠空行切会把整篇摘要一起带进来（实测 16 篇卡在这里）。
KW_STOP = re.compile(r'\s*(?:A\s?B\s?S\s?T\s?R\s?A\s?C\s?T'
                     r'|A\s?R\s?T\s?I\s?C\s?L\s?E\s+I\s?N\s?F\s?O'
                     r'|\d+\.?\s+I\s?N\s?T\s?R\s?O|\d+\.?\s+Introduction|INTRODUCTION'
                     r'|©|Received:|This is an open access|medium, provided)', re.I)
ABSTRACT = re.compile(r'^##\s+Abstract\s*$', re.M | re.I)


def source_keywords(src_txt: str) -> str:
    """从原文 dump 里截关键词串；截不干净就返回空，交给 A1，不猜。

    实测这批 PDF 的形态高度一致——**关键词一行一个，整块之后空一行接摘要**：

        Keywords:
        rCFD-DEM
        Coarse-grained model
        Superquadric particle model

        A B S T R A C T

    所以以**空行**为界最准。第一版用「撞上 Introduction 才停」，
    结果全都撞不到（中间隔着 `A B S T R A C T`），18 篇只补回 3 篇。
    """
    m = re.search(r'(?:%s)\s*[:：]?\s*' % KW_LABEL, src_txt[:12000])
    if not m:
        return ''
    tail = src_txt[m.end():m.end() + 600].lstrip('\r\n')
    block = re.split(r'\n\s*\n', tail)[0]
    stop = KW_STOP.search(block)
    if stop:
        block = block[:stop.start()]
    parts = [x.strip(' ,;.·') for x in block.split('\n') if x.strip(' ,;.·')]
    body = ', '.join(parts) if len(parts) > 1 else re.sub(r'\s+', ' ', block).strip(' ,;.·')
    # 关键词一般 2~12 个、总长几十到二三百字符；超出这个范围多半截歪了
    return body if 8 < len(body) < 300 else ''


def normalize(article: str, src_txt: str = '') -> tuple:
    """返回 `(新正文, 动作)`。动作取值：已是标题节 / 形态归一 / 从原文补 / 原刊没印。"""
    if HEAD_SEC.search(article):
        return article, '已是标题节'

    body = ''
    m = BOLD_LINE.search(article)
    if m:
        body = m.group(1).strip()
        article = article[:m.start()] + article[m.end():]
    else:
        for mm in RAW_LINE.finditer(article):
            line = mm.group(0)
            if line.startswith(('#', '>', '|', '**')):
                continue
            body = ART_LABEL.sub('', line).strip()
            article = article[:mm.start()] + article[mm.end():]
            break

    action = '形态归一'
    if not body:
        body = source_keywords(src_txt)
        action = '从原文补'
    if not body:
        # 区分「原刊真没印」和「印了但截不干净」——后者要留给 A1，不能当没事
        printed = bool(re.search(r'(?:%s)\s*[:：]' % KW_LABEL, src_txt[:12000]))
        return article, '印了但截不出（派 A1）' if printed else '原刊没印'

    body = re.sub(r'\s{2,}', ', ', body).strip(' ,;.')
    section = '## Keywords\n\n%s\n' % body
    # 放在 Abstract 一节之后：读者先看摘要再看关键词，也与中文侧的位置一致
    ma = ABSTRACT.search(article)
    if ma:
        nxt = re.search(r'^##\s+', article[ma.end():], re.M)
        pos = ma.end() + (nxt.start() if nxt else len(article) - ma.end())
        article = article[:pos] + section + '\n' + article[pos:]
    else:
        article = article.rstrip() + '\n\n' + section
    return re.sub(r'\n{3,}', '\n\n', article), action


def main() -> None:
    ap = argparse.ArgumentParser(description='英文正文关键词统一成 ## Keywords 节')
    ap.add_argument('--vault', required=True)
    ap.add_argument('--out', help='草稿目录；不给则原地改写')
    ap.add_argument('--only')
    a = ap.parse_args()

    outdir = Path(a.out) if a.out else None
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)
    tally: dict = {}
    for en in sorted(Path(a.vault).rglob('content/*.正文.en.md')):
        pid = en.name[:-len('.正文.en.md')]
        if a.only and not pid.startswith(a.only):
            continue
        txt = en.with_name(pid + '.txt')
        new, action = normalize(en.read_text(encoding='utf-8', errors='replace'),
                                txt.read_text(encoding='utf-8', errors='replace')
                                if txt.is_file() else '')
        tally[action] = tally.get(action, 0) + 1
        if action in ('形态归一', '从原文补'):
            (outdir / en.name if outdir else en).write_text(new, encoding='utf-8')
            print('%-44s %s' % (pid[:44], action))
    print()
    for k, v in sorted(tally.items(), key=lambda x: -x[1]):
        print('  %-10s %d 篇' % (k, v))


if __name__ == '__main__':
    main()
