#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_article.py —— AI 生成文稿的确定性纠错（幂等；写前备份到 %TEMP%/fix_article_backups）。

只做机械修复、不创作内容。自动修复项：
1. H1 后缀「（中文翻译）」「（方法原理精讲）」剥离
2. `## 要点` → `## 亮点`；`## Key Points` → 中文正文改「## 亮点」、英文正文改「## Highlights」
2b. 英文正文里**原刊根本没印**的 `## Highlights` 整节删除（以同集群 txt 缓存自证；英文侧禁提炼）
2b'. 中文正文 `## 亮点`：原刊没印 Highlights 时在列表后补一行「AI 提炼」说明，印了则删掉该说明
     （同样以 txt 自证；说明必须在列表之后，插在标题与列表之间会让前端亮点卡片不渲染）
2c. `## 摘要（Abstract）` → `## 摘要`（只动契约要求精确匹配的前置块，正文章节的英文括注不碰）
2d. 题名块 `> 原题/作者/单位/期刊：` 引用块 → 裸段落（引用块会让说明卡吞掉整段正文）
2e. `> **图 3** 说明` → `**图 3：** 说明`（图注是图片下方的普通段落）
2f. `*图 3. 说明*` → `**图 3：** 说明`（斜体图注是旧体例，前端认不出、图退化成文件名）
3. 表格块前缺空行 → 补空行（含行尾文字直接顶表格的情况）
4. 表格行里的裸 < / > → 数学 $..$ 内改 \\lt / \\gt，数学外改 &lt; / &gt;
5. [[[…]]] 三层括号 → [[…]]（build_refs 嵌套历史 bug）
6. ![[x.png]] 缺宽度 → ![[x.png|700]]
7. 嵌入图片文件名与 images/ 实际文件不符（大小写 / png↔jpeg / 前缀笔误），唯一近似命中时自动改写
8. 3 个以上连续空行压成 2 个
9. 数学字母被 PDF 抽成谚文字形（`휌` → `ρ`、`퐗` → `X`）：码位 +0x10000 回到
   U+1D400–U+1D7FF 数学字母符号区再 NFKC 折平；整篇混有真韩文时自动让开

只报告不修（需要人或 AI 判断内容）：$$ 奇数个、图片行后缺图注、`## 通俗摘要` 成节。

用法：
    python fix_article.py <md文件>... [--images-dir DIR] [--dry-run]
    python fix_article.py --vault <VAULT> [--paper <pid子串>] [--dry-run]

退出码恒为 0（修复是服务不是验收；验收交给 lint_cluster / web_lint）。
"""
from __future__ import annotations

import argparse
import glob
import io
import os
import re
import shutil
import sys
import tempfile
import time

H1_SUFFIX = re.compile(r'^(#\s+.+?)（(?:中文翻译|方法原理精讲)）[ \t]*$', re.M)
TRIPLE_BRACKET = re.compile(r'\[\[\[([^\[\]]+)\]\]\]')
EMBED_NO_WIDTH = re.compile(r'!\[\[([^\]|#]+\.(?:png|jpe?g|gif|webp))\]\]', re.I)
EMBED_ANY = re.compile(r'!\[\[([^\]|#]+?)(?:\|[^\]]*)?\]\]')
MATH_SPAN = re.compile(r'\$[^$\n]+\$')
CAPTION_LINE = re.compile(r'^(?:\*\*|__)?\s*(?:图|表|Fig|Figure|Table|Graphical)', re.I)
IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.webp')

# 旧骨架模板里写给 AI 的提示行（新模板已改为 <!--HINT-->，成稿不该给人看）
TEMPLATE_HINTS = re.compile(
    r'^>\s*(?:不是原文摘要，而是|术语链接到全局术语库|\*\*必填项\*\*。读 PDF 全文后填写).*\n?',
    re.M,
)
HINT_COMMENT = re.compile(r'<!--HINT[^>]*-->\n?')

# 英文正文是原文重排，Highlights 只该在原刊印了的时候出现。旧 lint 口径写着
# 「原文无则从 Abstract 提炼」，诱导出 18 篇冒充原文的 AI 自撰要点。判据与 lint 共用
# 一份（漏认 AGU 的 Key Points 会反过来误删真要点，两处各写一份迟早走样）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lint_cluster import (CHROME_QUOTE, src_has_highlights, restore_math_glyphs,  # noqa: E402
                          AI_HL_NOTICE, AI_HL_MARK, HL_ZH_HEAD)

EN_HL_SECTION = re.compile(r'^##[ \t]+Highlights[ \t]*$.*?(?=^##[ \t]|\Z)', re.M | re.S)

# CommonMark 强调坑：`**图 5：**河道…` 收尾 ** 前是全角标点、后紧贴汉字时不构成
# 右侧定界符，加粗解析失败、星号裸奔。图注前缀的 ** 后必须留一个空格。
CAPTION_BOLD_TIGHT = re.compile(
    r'^(\*{2}(?:图|表|Fig|Figure|Table|Graphical)[^*\n]{0,80}\*{2})(?=\S)', re.M
)

# build_refs --inline 早期版本把「式[3]」的 3 当成引用序号链成了 ^ref-3，
# 点进去跳到第 3 篇参考文献。脚本侧已加前缀护栏，这里清存量。
EQNO_AS_REF = re.compile(
    r'(式|公式|方程|等式|Eqs?\.?|Eqns?\.?|Equations?)\s*\[\[#\^ref-(\d+)\|\d+\]\]', re.I
)
# 区间续写：「式 (7)–[[#^ref-8|8]]」的后半截
EQNO_RANGE_TAIL = re.compile(r'(\(\d+\)\s*[–—~-]\s*)\[\[#\^ref-(\d+)\|\d+\]\]')

# 正文里的图表引用加粗，方便读者在长正文里一眼定位。
# 续接「和 4」这类并列时要防住量词——「图 3 和 4 个颗粒」里的 4 是数量不是图号。
_MEASURE = ('个|种|组|次|篇|条|幅|张|类|项|维|阶|倍|例|名|位|层|步|段|行|列|点|度|'
            '根|块|片|面|台|套|批|轮|遍|万|千|百|亿')
_NUM = r'\d{1,2}[a-z]?'
# 「图」「表」也常做复合词词尾（示意图/流程图/图表/代表…），这些后面跟数字纯属巧合，
# 不能加粗。注意 \w 在 Python 里连汉字一起匹配，拿它挡前缀会把「如图」也挡掉。
_NOT_COMPOUND = ('A-Za-z0-9_*＊'
                 '意程构理面插视地子附简略草拼截云谱线柱饼散直等网相全制绘试'
                 '图列报量仪手代发外钟')
FIGREF = re.compile(
    rf'(?<![{_NOT_COMPOUND}])(图|表)\s*{_NUM}'
    rf'(?:\s*[-–—~]\s*{_NUM})?'
    rf'(?:(?:\s*[、,，]\s*|\s*(?:和|与|及)\s*){_NUM}(?!\s*(?:{_MEASURE})))*'
)
FIGREF_EN = re.compile(
    r'(?<![\w*])(Figs?|Figures?|Tables?)\.?\s*\d{1,2}[a-z]?'
    r'(?:\s*[-–—~]\s*\d{1,2}[a-z]?)?'
    r'(?:(?:\s*,\s*|\s+and\s+)\d{1,2}[a-z]?)*',
    re.I,
)
# 加粗前先把这些片段挖走，避免在数学、链接、行内代码、已加粗处误伤
FIGREF_MASK = re.compile(
    r'\$\$[\s\S]*?\$\$|\$[^$\n]+\$|!?\[\[[^\]]*\]\]|`[^`\n]+`|\*\*[^*\n]+\*\*'
)
# 图注行本身不参与加粗。只认「已加粗的图注」和「图 3.」这种带尾标点的编号，
# 不能整行以 Table 开头就跳——「Table 1 summarizes the parameters.」是正文。
FIGREF_SKIP_LINE = re.compile(
    r'^(?:\*\*|__)\s*(?:图|表|Fig|Figure|Table|Graphical)'
    r'|^(?:图|表|Fig(?:ure)?|Table)\s*\d{1,3}\s*[.:：、]',
    re.I,
)


def norm_stem(name: str) -> str:
    stem = os.path.splitext(os.path.basename(name))[0]
    return ''.join(ch for ch in stem.lower() if ch.isalnum() or '\u4e00' <= ch <= '\u9fff')


def fix_template_hints(text: str, fixes: list) -> str:
    new = TEMPLATE_HINTS.sub('', text)
    new = HINT_COMMENT.sub('', new)
    if new != text:
        fixes.append('清除模板提示行（AI 填写说明，人不该看到）')
    return new


def fix_caption_bold_space(text: str, fixes: list) -> str:
    new, n = CAPTION_BOLD_TIGHT.subn(r'\1 ', text)
    if n:
        fixes.append(f'图注加粗后补空格 ×{n}（CommonMark 全角标点+**加粗失效坑）')
    return new


def fix_h1_suffix(text: str, fixes: list) -> str:
    new = H1_SUFFIX.sub(r'\1', text)
    if new != text:
        fixes.append('H1 剥离「（中文翻译）」类后缀')
    return new


def fix_headings(text: str, is_en: bool, fixes: list) -> str:
    target = '## Highlights' if is_en else '## 亮点'
    new = re.sub(r'^##[ \t]+(?:要点|Key[ \t]*Points)[ \t]*$', target, text, flags=re.M | re.I)
    if new != text:
        fixes.append(f'标题改写 → {target}')
    return new


SECTION_NUM_DOT = re.compile(r'^(#{2,6}[ \t]+)(\d+(?:\.\d+)*)\.(?=[ \t]|$)', re.M)


def fix_front_heading_paren(text: str, fixes: list) -> str:
    """`## 摘要（Abstract）` → `## 摘要`。

    只动**文枢契约要求精确匹配**的前置块标题；`## 3 方法（Methodology）` 这种带英文括注的
    正文章节标题是库里既有风格（10 篇在用），不碰。
    """
    new, n = re.subn(r'^(##[ \t]+(?:摘要|亮点))[ \t]*（[A-Za-z][A-Za-z ]*）[ \t]*$',
                     r'\1', text, flags=re.M)
    m = 0
    new, m = re.subn(r'^\*\*关键词（[A-Za-z][A-Za-z ]*）：\*\*', '**关键词：**', new, flags=re.M)
    if n or m:
        fixes.append(f'前置块标题去英文括注 ×{n + m}')
    return new


def fix_quoted_caption(text: str, fixes: list) -> str:
    """`> **图 3** 说明` → `**图 3：** 说明`（图注是图片下方的普通段落，不能包在引用块里）。

    引用块里的图注会被文枢渲染成注解卡，图与图注在版面上被拆开。`> **【说明】…**` 是
    正经的注解卡，模式不重叠，不会误伤。
    """
    new, n = re.subn(r'^>[ \t]*\*\*((?:图|表)[ \t]*\d+[a-zA-Z]?)\*\*[ \t：:]*(.*)$',
                     lambda m: '**%s：** %s' % (m.group(1).strip(), m.group(2).strip()),
                     text, flags=re.M)
    if n:
        fixes.append(f'图注移出引用块 ×{n}（图注应为图片下方普通段落）')
    return new


ITALIC_CAPTION = re.compile(
    r'^\*(?!\*)[ \t]*((?:图|表|Fig|Figure|Table)\.?[ \t]*[A-Z]?\d{1,3}[a-z]?)'
    r'[ \t]*[.．。:：、]?[ \t]*(.*[^*])\*[ \t]*$',
    re.M,
)


def fix_italic_caption(text: str, fixes: list) -> str:
    """`*图 3. 说明*` → `**图 3：** 说明`（上一代技能留下的斜体图注体例）。

    契约要求图注是 `**图 N：** 说明`，前端据此包 figure/figcaption、驱动「图片」页的图名与
    「在正文中定位」。斜体形式渲染出来只是一行倾斜文字，图退化成文件名展示，
    `web_lint` 的 CAPTION_LINE 也只认加粗前缀，整篇图注全被判成「缺图注」。

    收尾 `*` 前要求一个非 `*` 字符：图注内部常有 `见**图 2**` 这类加粗引用，
    末尾贴着 `**` 的行属于斜体没闭合的脏数据，宁可不动也不要拆出孤立星号。
    """
    def repl(m: re.Match) -> str:
        return '**%s：** %s' % (m.group(1).strip(), m.group(2).strip())

    new, n = ITALIC_CAPTION.subn(repl, text)
    if n:
        fixes.append(f'斜体图注转加粗 ×{n}（`*图 N. …*` → `**图 N：** …`，契约体例）')
    return new


QUOTED_RUN = re.compile(r'(?:^>.*\n)+', re.M)
BYLINE_KEYS = {'原题', '作者', '单位', '期刊', '关键词', '关键字', '通讯邮箱'}
# callout（`> [!abstract] 导读说明`）与注解卡（`> **【说明】…**`）是**有意为之**的引用块，
# 拍平就毁了渲染。整段里出现这两种标记就整段不碰。
QUOTE_KEEP = re.compile(r'\[!|【说明】')


def _byline_line(raw: str, keep_title: bool):
    """题名区里的一行引用内容 → (是否独立成段, 文本)；None 表示丢弃。"""
    body = raw.lstrip('>').strip()
    key, _, val = body.partition('：')
    key, val = key.strip(), val.strip()
    if key == '原题':
        return (False, val) if keep_title else None
    if key == '作者':
        return True, '**%s**' % val
    if key in ('关键词', '关键字'):
        return True, '**关键词：** %s' % val
    if key in ('单位', '期刊'):
        return True, val
    return False, body            # 无字段名的裸行（多为单位续行），并进同一段


def fix_quoted_byline(text: str, path: str, fixes: list) -> str:
    """题名区（H1 → 第一个 `##`）里的引用块 → 契约要求的裸段落。

    这是文枢渲染器最致命的一类脏数据：`## 亮点` 之前只要出现任何非「说明」的引用块，
    渲染器就会把它到下一个说明块之间的**整段正文**卷进说明卡（2026-08 全库损坏 32 篇）。

    按字段名分派而非按行号：`作者：` 转一段加粗、`单位：/期刊：` 各自成段、`关键词：` 转
    契约的加粗行；没有字段名的裸行（作者单位常拆成 `ª …` / `ᵇ …` 两行）并进同一段，
    正好落成契约里的「单位段」。`> 返回索引：` / `> 🤖` 是前端会剥掉的框架行，跳过。

    **只处理确含题名字段的引用块**：callout 导读、`【说明】` 注解卡都是有意写成引用块的，
    整段拍平会直接毁掉渲染（Example2024 的 `> [!abstract] 导读说明` 就险些被误伤）。

    `原题` 不在契约的三行里；仅当同集群索引卡确有 `- **原题**：` 时才丢弃（自证无损），
    否则降级成裸段落保留，绝不静默丢内容。
    """
    h1 = re.search(r'^# .+$', text, re.M)
    if not h1:
        return text
    zone_end = text.find('\n## ', h1.end())
    zone_end = len(text) if zone_end < 0 else zone_end

    keep_title = True
    pid = os.path.basename(path).split('.正文')[0]
    card = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(path))), pid + '.md')
    if os.path.isfile(card):
        with open(card, encoding='utf-8', errors='ignore') as f:
            keep_title = '- **原题**：' not in f.read()

    dropped = [False]

    def convert(m):
        lines = [ln for ln in m.group(0).splitlines() if not CHROME_QUOTE.search(ln)]
        if len(lines) != len(m.group(0).splitlines()):
            return m.group(0)                    # 混了框架行，别碰
        if any(QUOTE_KEEP.search(ln) for ln in lines):
            return m.group(0)                    # callout / 说明卡，有意为之
        if not any(ln.lstrip('>').strip().partition('：')[0].strip() in BYLINE_KEYS
                   for ln in lines):
            return m.group(0)                    # 没有任何题名字段，不是题名块
        paras, run = [], []
        for ln in lines:
            got = _byline_line(ln, keep_title)
            if got is None:
                dropped[0] = True
                continue
            solo, txt = got
            if not txt:
                continue
            if solo:
                if run:
                    paras.append('\n'.join(run))
                    run = []
                paras.append(txt)
            else:
                run.append(txt)
        if run:
            paras.append('\n'.join(run))
        return ('\n\n'.join(paras) + '\n') if paras else ''

    zone = QUOTED_RUN.sub(convert, text[:zone_end])
    if zone == text[:zone_end]:
        return text
    fixes.append('题名块引用块改裸段落（说明卡会吞正文）%s'
                 % ('，原题已在索引卡文献卡内，丢弃' if dropped[0] else ''))
    return zone + text[zone_end:]


def fix_fabricated_highlights(text: str, path: str, is_en: bool, fixes: list) -> str:
    """英文正文里原刊没有的 ## Highlights 整节删掉。

    只在**拿得到同集群 txt 全文缓存、且缓存里确实找不到 Highlights/Key Points 标题**
    时才动手，属自证式删除而非盲删；没有 txt 就什么都不做。提炼版要点归中文正文 `## 亮点`。
    """
    if not is_en or not EN_HL_SECTION.search(text):
        return text
    src = os.path.join(os.path.dirname(path),
                       os.path.basename(path)[:-len('.正文.en.md')] + '.txt')
    if not os.path.isfile(src):
        return text
    with open(src, encoding='utf-8', errors='ignore') as f:
        if src_has_highlights(f.read(12000)):
            return text
    new = EN_HL_SECTION.sub('', text, count=1)
    fixes.append('删除原刊没有的 ## Highlights 节（英文正文禁提炼；要点见中文正文 ## 亮点）')
    return new


def fix_ai_highlights_notice(text: str, path: str, is_article: bool, fixes: list) -> str:
    """中文正文 `## 亮点`：原刊没印 Highlights 就补一行「AI 提炼」说明，印了就删掉它。

    英文侧禁止捏造要点，中文侧允许提炼——但**必须让读者知道这是 AI 写的**，
    否则 AI 总结的要点和期刊自印的要点长得一模一样（全库 84 篇曾都是这个状态）。

    说明块只能放在**亮点列表之后**：前端 decorateHighlights 的正则要求
    `<h2>亮点</h2>` 紧跟 `<ul>`，中间插任何东西亮点卡片就不渲染了。
    与 fix_fabricated_highlights 一样是自证式修改——拿不到 txt 就什么都不做。
    """
    if not is_article:
        return text
    m = HL_ZH_HEAD.search(text)
    if not m:
        return text
    src = os.path.join(os.path.dirname(path),
                       os.path.basename(path)[:-len('.正文.md')] + '.txt')
    if not os.path.isfile(src):
        return text
    with open(src, encoding='utf-8', errors='ignore') as f:
        from_source = src_has_highlights(f.read(12000))

    rest = text[m.end():]
    nxt = re.search(r'^##\s', rest, re.M)
    end = m.end() + (nxt.start() if nxt else len(rest))
    section = text[m.end():end]
    marked = bool(AI_HL_MARK.search(section))

    if from_source and marked:
        cleaned = AI_HL_MARK.sub('', section).replace('\n\n\n', '\n\n')
        fixes.append('删除「AI 提炼」说明（原刊印了 Highlights，这批要点译自原文）')
        return text[:m.end()] + cleaned + text[end:]
    if not from_source and not marked:
        fixes.append('补「AI 提炼」说明（原刊未印 Highlights，需让读者分清要点来源）')
        return text[:m.end()] + section.rstrip('\n') + '\n\n' + AI_HL_NOTICE + '\n\n' + text[end:]
    return text


def fix_section_number_dot(text: str, is_article: bool, fixes: list) -> str:
    """中文正文章节编号去尾点：`## 1. 引言` → `## 1 引言`、`### 2.1. …` → `### 2.1 …`。

    基准篇 Example2024 中文侧写无点、英文侧写 `## 1. Introduction`，故英文正文不动。
    notes.md 也不动：那边的 `## N. 标题` 是笔记自己的教程编号体系，与论文章节无关。
    """
    if not is_article:
        return text
    new, n = SECTION_NUM_DOT.subn(r'\1\2', text)
    if n:
        fixes.append(f'章节编号去尾点 ×{n}（## 1. → ## 1）')
    return new


def fix_triple_brackets(text: str, fixes: list) -> str:
    new = TRIPLE_BRACKET.sub(r'[[\1]]', text)
    if new != text:
        fixes.append('三层括号 [[[…]]] → [[…]]')
    return new


def fix_math_glyphs(text: str, fixes: list) -> str:
    """`휌lnxlnylnz` → `ρlnxlnylnz`：PDF 抽取丢了 Plane-1 高位，数学字母掉进谚文区。

    还原是纯算术（码位 +0x10000 再 NFKC），不猜不改语义，所以放在自动修一档；
    判据与 lint_cluster 共用一份，混有真韩文时函数自己会整篇让开。
    """
    new, n = restore_math_glyphs(text)
    if n:
        fixes.append(f'数学字母字形还原 ×{n}（U+D400–U+D7FF → 数学字母符号，如 휌 → ρ）')
    return new


def fix_eqno_as_ref(text: str, fixes: list) -> str:
    """「式[[#^ref-3|3]]」还原成「式 (3)」——公式号被 build_refs --inline 误当引用序号链掉了。"""
    new, n = EQNO_AS_REF.subn(r'\1 (\2)', text)
    new, m = EQNO_RANGE_TAIL.subn(r'\1(\2)', new)
    if n or m:
        fixes.append(f'公式号误链还原 ×{n + m}（式[[#^ref-N|N]] → 式 (N)）')
    return new


def fix_figref_bold(text: str, is_en: bool, fixes: list) -> str:
    """正文里的「图 13」「Fig. 13」加粗，长正文里一眼能找到引用点。

    跳过图注行、标题、嵌入行与代码块——图注本来就以 `**图 N.**` 开头，
    再加一层会套成 `****`。
    """
    pattern = FIGREF_EN if is_en else FIGREF
    out, n = [], 0
    in_fence = False
    for line in text.split('\n'):
        stripped = line.lstrip()
        if stripped.startswith('```'):
            in_fence = not in_fence
            out.append(line)
            continue
        if (in_fence or not stripped or stripped[0] == '#'
                or stripped.startswith(('![[', '>', '|'))
                or FIGREF_SKIP_LINE.match(stripped)):
            out.append(line)
            continue

        holes: list[str] = []

        def stash(m: re.Match) -> str:
            holes.append(m.group(0))
            return f'\x00{len(holes) - 1}\x00'

        masked = FIGREF_MASK.sub(stash, line)
        masked, hits = pattern.subn(lambda m: f'**{m.group(0)}**', masked)
        n += hits
        out.append(re.sub(r'\x00(\d+)\x00', lambda m: holes[int(m.group(1))], masked))

    if n:
        fixes.append(f'图表引用加粗 ×{n}')
    return '\n'.join(out)


def fix_embed_width(text: str, fixes: list) -> str:
    new = EMBED_NO_WIDTH.sub(r'![[\1|700]]', text)
    if new != text:
        fixes.append('图片嵌入补 |700 宽度')
    return new


def fix_table_gt_lt(text: str, fixes: list) -> str:
    """表格行里的裸 < / >：$..$ 数学内 → \\lt/\\gt；数学外 → &lt;/&gt;。"""
    changed = False
    out_lines = []
    for line in text.splitlines():
        if not line.lstrip().startswith('|') or '<!--' in line:
            out_lines.append(line)
            continue
        probe = line.replace('\\lt', '').replace('\\gt', '').replace('&lt;', '').replace('&gt;', '')
        if '<' not in probe and '>' not in probe:
            out_lines.append(line)
            continue

        spans = [(m.start(), m.end()) for m in MATH_SPAN.finditer(line)]

        def in_math(pos: int) -> bool:
            return any(a <= pos < b for a, b in spans)

        # 已转义形式（&lt; \lt 等）不含裸 <>，逐字符替换不会二次转义
        buf = []
        for i, ch in enumerate(line):
            if ch == '<':
                buf.append('\\lt ' if in_math(i) else '&lt;')
            elif ch == '>':
                buf.append('\\gt ' if in_math(i) else '&gt;')
            else:
                buf.append(ch)
        new_line = ''.join(buf)
        if new_line != line:
            changed = True
        out_lines.append(new_line)
    if changed:
        fixes.append('表格裸 </> 转义（数学内 \\lt/\\gt，数学外 &lt;/&gt;）')
    return '\n'.join(out_lines) + ('\n' if text.endswith('\n') else '')


def fix_table_blank_line(text: str, fixes: list) -> str:
    lines = text.splitlines()
    out, changed = [], False
    for idx, line in enumerate(lines):
        if (line.lstrip().startswith('|') and out and out[-1].strip()
                and not out[-1].lstrip().startswith('|')):
            out.append('')
            changed = True
        out.append(line)
    if changed:
        fixes.append('表格前补空行')
    return '\n'.join(out) + ('\n' if text.endswith('\n') else '')


def fix_embed_names(text: str, images_dir: str, fixes: list) -> str:
    if not images_dir or not os.path.isdir(images_dir):
        return text
    actual = [n for n in os.listdir(images_dir) if n.lower().endswith(IMAGE_EXTS)]
    actual_set = set(actual)
    by_stem: dict[str, list] = {}
    for name in actual:
        by_stem.setdefault(norm_stem(name), []).append(name)

    def repl(match):
        raw = match.group(0)
        name = match.group(1).strip()
        base = os.path.basename(name)
        if not base.lower().endswith(IMAGE_EXTS) or base in actual_set:
            return raw
        cands = by_stem.get(norm_stem(base)) or []
        if len(cands) == 1:
            fixes.append(f'图片名纠正 {base} → {cands[0]}')
            return raw.replace(name, cands[0])
        return raw

    return EMBED_ANY.sub(repl, text)


def compress_blank_lines(text: str, fixes: list) -> str:
    new = re.sub(r'\n{4,}', '\n\n\n', text)
    if new != text:
        fixes.append('压缩连续空行')
    return new


def report_only(text: str, path: str, reports: list) -> None:
    if text.count('$$') % 2 == 1:
        reports.append('块公式 $$ 奇数个（无法自动修，需人工核对）')
    if re.search(r'^##\s+(?:通俗摘要|Plain Language Summary)\s*$', text, re.M | re.I):
        reports.append('存在「通俗摘要」独立成节（契约禁止，需人工并入摘要或删除）')
    if '.正文.' not in os.path.basename(path):
        return  # 图注段只对正文强制，notes 嵌图不要求重复图注
    lines = text.splitlines()
    missing_caption = 0
    for i, line in enumerate(lines):
        if not EMBED_ANY.search(line):
            continue
        # 连续图组共享一个图注：跳过空行和后续图行，看到的第一段文字算图注
        has_caption = False
        j = i + 1
        while j < min(i + 8, len(lines)):
            nxt = lines[j].strip()
            if not nxt or EMBED_ANY.search(nxt):
                j += 1
                continue
            has_caption = bool(CAPTION_LINE.match(nxt))
            break
        if not has_caption:
            missing_caption += 1
    if missing_caption:
        reports.append(f'{missing_caption} 张图后缺「**图 N：**」图注段（需补写）')


def fix_file(path: str, images_dir: str | None, dry_run: bool) -> tuple[list, list]:
    with open(path, encoding='utf-8') as f:
        text = f.read()
    original = text
    is_en = path.endswith('.正文.en.md')
    is_article = path.endswith('.正文.md')
    fixes: list = []
    reports: list = []

    # 排在最前：后面每一条规则都在读文本内容，先把错映射的字形还原成真字符，
    # 它们看到的才是真正的正文而不是谚文乱码
    text = fix_math_glyphs(text, fixes)
    text = fix_template_hints(text, fixes)
    text = fix_h1_suffix(text, fixes)
    text = fix_headings(text, is_en, fixes)
    text = fix_front_heading_paren(text, fixes)
    text = fix_quoted_byline(text, path, fixes)
    text = fix_quoted_caption(text, fixes)
    # 必须排在 fix_figref_bold 之前：转出来的 `**图 N：**` 是图注前缀，
    # 先转好才能让 FIGREF_SKIP_LINE 认出整行是图注、不去加粗图注里的图号
    text = fix_italic_caption(text, fixes)
    # 必须排在 fix_headings 之后：`## Key Points` 先归一成 `## Highlights` 才认得出来
    text = fix_fabricated_highlights(text, path, is_en, fixes)
    text = fix_ai_highlights_notice(text, path, is_article, fixes)
    text = fix_section_number_dot(text, is_article, fixes)
    text = fix_triple_brackets(text, fixes)
    text = fix_eqno_as_ref(text, fixes)
    # 必须排在补空格之前：加粗会在行首造出新的 `**图 N**`，紧跟汉字时同样踩加粗失效坑
    text = fix_figref_bold(text, is_en, fixes)
    text = fix_caption_bold_space(text, fixes)
    if images_dir:
        text = fix_embed_names(text, images_dir, fixes)
    text = fix_embed_width(text, fixes)
    text = fix_table_blank_line(text, fixes)
    text = fix_table_gt_lt(text, fixes)
    text = compress_blank_lines(text, fixes)
    report_only(text, path, reports)

    if fixes and text != original and not dry_run:
        backup_dir = os.path.join(tempfile.gettempdir(), 'fix_article_backups')
        os.makedirs(backup_dir, exist_ok=True)
        stamp = time.strftime('%Y%m%d-%H%M%S')
        shutil.copy2(path, os.path.join(backup_dir, f'{os.path.basename(path)}.{stamp}.bak'))
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
    return fixes, reports


def guess_images_dir(path: str) -> str | None:
    """content/<pid>.xxx.md → 同集群 images/ 目录。"""
    parent = os.path.dirname(path)
    if os.path.basename(parent) == 'content':
        cand = os.path.join(os.path.dirname(parent), 'images')
        if os.path.isdir(cand):
            return cand
    return None


def collect_vault_targets(vault: str, pid_filter: str | None):
    targets = []
    for p in glob.glob(os.path.join(vault, 'Papers', '**', '*.md'), recursive=True):
        if os.sep + 'content' + os.sep in p or os.sep + 'images' + os.sep in p:
            continue
        if os.path.basename(p).startswith('_'):
            continue
        with open(p, encoding='utf-8') as f:
            head = f.read(2400)
        if 'noteType: index' not in head and 'p2o/paper' not in head:
            continue
        pid = os.path.basename(p)[:-3]
        if pid_filter and pid_filter not in pid:
            continue
        base = os.path.dirname(p)
        for sub in os.listdir(base):
            cdir = os.path.join(base, sub, 'content')
            if not (os.path.isdir(cdir) and os.path.isfile(os.path.join(cdir, pid + '.正文.md'))):
                continue
            idir = os.path.join(base, sub, 'images')
            for suffix in ('.正文.md', '.正文.en.md', '.notes.md'):
                fp = os.path.join(cdir, pid + suffix)
                if os.path.isfile(fp):
                    targets.append((fp, idir if os.path.isdir(idir) else None))
            break
    return targets


def main() -> None:
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    ap = argparse.ArgumentParser(description='AI 文稿确定性纠错')
    ap.add_argument('files', nargs='*', help='要修的 md 文件')
    ap.add_argument('--vault', default=None, help='全库模式：扫所有论文集群')
    ap.add_argument('--paper', default=None, help='vault 模式下只修 pid 含此子串的论文')
    ap.add_argument('--images-dir', default=None, help='images/ 目录（文件模式下用于图片名纠正）')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    if args.vault:
        targets = collect_vault_targets(args.vault, args.paper)
    else:
        targets = [(f, args.images_dir or guess_images_dir(f)) for f in args.files]
    if not targets:
        print('没有可处理的文件')
        return

    n_fixed = 0
    for path, idir in targets:
        fixes, reports = fix_file(path, idir, args.dry_run)
        name = os.path.basename(path)
        if fixes:
            n_fixed += 1
            tag = '[dry-run] ' if args.dry_run else ''
            print(f'🔧 {tag}{name}')
            for fx in fixes:
                print(f'   - {fx}')
        for rp in reports:
            print(f'📋 {name} ｜ {rp}')
    print(f'—— fix_article：处理 {len(targets)} 个文件，修复 {n_fixed} 个'
          + ('（dry-run 未写盘）' if args.dry_run else ''))


if __name__ == '__main__':
    main()
