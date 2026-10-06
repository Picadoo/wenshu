#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lint_cluster.py —— 入库质检：流水线产出的结构性验收（提示词会走样，验收不会）。

血泪背景：子代理曾把概念卡写错位置（15 份散落 40_Flashcards）、107 篇正文没生成参考
文献、占位符残留没人发现——全是"提示词写了但没人检查"的走样。本脚本把规矩变成断言。

检查项（E=错误必修，W=警告酌情）：
- index：占位符/构造标记残留(E)、status 未回填(E)、citekey 缺失(W)
- 正文：翻译占位残留(E)、图片嵌入指向不存在的文件(E/W)、$$ 未闭合(E)、
        REFS_AUTO 标记破损(E)、缺参考文献章节(txt 可解析才算 E，否则 W-源数据)、
        表格裸 <>(W)、三层括号历史bug(W)、数学字母被抽成谚文字形(E)
- 英文正文：版式契约(见 check_english_shell)、数学字形错映射(E)、
        中文有带号 LaTeX 而英文零块公式=公式对拷失效(E)、两侧数量落差过半(W)
- notes：占位/标记残留(E)、深度分析模板残留(W)、写作逻辑未填(W)、图片检查同上
- 全局：content 缺全文 txt(W)、术语 registry JSON 可解析(E)、PDFs 收件箱滞留提示(INFO)

用法：python lint_cluster.py --vault "G:/论文知识库" [--paper <pid子串>] [--report]
      --paper 单篇（入库收尾用）；缺省全库体检；--report 写 90_系统/_质检报告.md
退出码：有 E 则 1（让流水线能感知），否则 0。
"""
import os
import re
import io
import sys
import json
import glob
import argparse
import datetime
import unicodedata

MARKER = re.compile(r'<!--(?:/?(?:SCI_Q|TLDR|SCORE|RELATED|KEYPOINTS|QA|ARTICLE_EN|ARTICLE|ORIGINAL)'
                    r'|TERMS_(?:START|END))-->')
EMBED = re.compile(r'!\[\[([^\]|#]+?)(?:\|[^\]]*)?\]\]')

# 部分 PDF（Springer 系尤甚）抽文本时丢掉 Plane-1 高位，把数学字母符号
# U+1D400–U+1D7FF 整体减 0x10000 落进谚文区：`휌`(U+D70C) 其实是 `𝜌`(U+1D70C)、
# `퐗`(U+D417) 是 `𝐗`(U+1D417)。加回 0x10000 再 NFKC 折一次即可无损还原。
LOST_PLANE1 = re.compile(r'[\ud400-\ud7ff]')
# 可疑窗口之外的谚文。出现它说明这真是韩语文档，还原规则必须整篇让开——
# 宁可留着乱码让 lint 报出来，也不能把真韩文改成希腊字母。
REAL_HANGUL = re.compile(r'[\uac00-\ud3ff\u1100-\u11ff\u3130-\u318f]')


def restore_math_glyphs(text):
    """还原丢了 Plane-1 高位的数学字母符号，返回 (新文本, 还原处数)。

    修复与检测共用这一份判据：fix_article 拿它修库内文稿、prep_article_en 拿它洗
    dump、本模块拿它做验收。三处各写一份正则迟早走样。
    """
    if not LOST_PLANE1.search(text) or REAL_HANGUL.search(text):
        return text, 0
    hits = [0]

    def rep(m):
        hits[0] += 1
        return unicodedata.normalize('NFKC', chr(ord(m.group(0)) + 0x10000))

    return LOST_PLANE1.sub(rep, text), hits[0]


def check_math_glyphs(L, pid, text, where):
    """数学字母符号被 PDF 抽取降级成谚文字形（读者看到的是 `휌lnxlnylnz`）。"""
    _fixed, n = restore_math_glyphs(text)
    if n:
        sample = ''.join(sorted(set(LOST_PLANE1.findall(text)))[:6])
        L.e(pid, '%s有 %d 处数学字母被 PDF 抽取降级成谚文字形（如 %s）；'
                 '跑 fix_article 可确定性还原成 ρ/λ/𝐗 等' % (where, n, sample))
    elif LOST_PLANE1.search(text):
        L.w(pid, '%s含 U+D400–U+D7FF 字符且整篇混有真韩文，自动还原已让开，需人工核对' % where)

IDX_PLACEHOLDERS = ['（本文要回答的核心科学问题', '（一句话说清', '待填充', '[SCORE]']
ART_PLACEHOLDERS = ['待**翻译子代理**填充', '待翻译子代理填充']
ART_EN_PLACEHOLDERS = ['待**英文重排子代理**填充', '待英文重排子代理填充']
NOTE_PLACEHOLDERS = ['待笔记子代理填充', '待 update_terms.py 填充', '（待填充）']
NOTE_TEMPLATE_BITS = ['[方法步骤 / 关键设计', '[架构描述', '[创新1 — 为什么重要]',
                      '[把论文关键结果表转写成', '[X.X/10]', '（问题背景 → 研究缺口']


def rd(p):
    try:
        return open(p, encoding='utf-8').read()
    except Exception:
        return ''


def fm_body(t):
    if t.startswith('---'):
        parts = t.split('---', 2)
        if len(parts) >= 3:
            return parts[1], parts[2]
    return '', t


class Lint:
    def __init__(self):
        self.errors, self.warns, self.infos = [], [], []

    def e(self, pid, msg):
        self.errors.append((pid, msg))

    def w(self, pid, msg):
        self.warns.append((pid, msg))

    def i(self, msg):
        self.infos.append(msg)


def collect_clusters(vault, pid_filter=None):
    """index(noteType: index) → (pid, index路径, content目录, images目录)。"""
    out = []
    for p in glob.glob(os.path.join(vault, 'Papers', '**', '*.md'), recursive=True):
        if os.sep + 'content' + os.sep in p or os.sep + 'images' + os.sep in p:
            continue
        if os.path.basename(p).startswith('_'):
            continue
        head = rd(p)[:2400]
        if 'noteType: index' not in head and 'p2o/paper' not in head:
            continue
        pid = os.path.basename(p)[:-3]
        if pid_filter and pid_filter not in pid:
            continue
        cdir = idir = None
        base = os.path.dirname(p)
        for sub in os.listdir(base):
            cand = os.path.join(base, sub, 'content')
            if os.path.isdir(cand) and os.path.isfile(os.path.join(cand, pid + '.正文.md')):
                cdir = cand
                idir = os.path.join(base, sub, 'images')
                break
        out.append((pid, p, cdir, idir))
    return out


FIG_GROUP_CAPTION = re.compile(
    r'^\*{0,2}\s*(?:图|表|Fig(?:ure)?\.?|Table|Graphical)\b', re.I)


def check_sliced_figure_groups(L, pid, text, where):
    """同一条图注前连续嵌 4 张以上，几乎一定是切碎面板被当成图组。

    原刊复合图应是一张整幅；真要分面板也不会在一条 Fig. N 下挂十几张碎片。
    Example2024 点云篇 Fig. 2 嵌了 6 张、Fig. 9 嵌了 12 张，就是这样进来的。
    """
    lines = text.splitlines()
    i, worst, n_bad = 0, 0, 0
    while i < len(lines):
        if not EMBED.search(lines[i]):
            i += 1
            continue
        n, j = 0, i
        while j < len(lines):
            s = lines[j].strip()
            if not s:
                j += 1
                continue
            if EMBED.search(s):
                n += 1
                j += 1
                continue
            break
        cap = lines[j].strip() if j < len(lines) else ''
        if n >= 4 and FIG_GROUP_CAPTION.match(cap):
            n_bad += 1
            worst = max(worst, n)
        i = j if j > i else i + 1
    if n_bad:
        L.e(pid, '%s有 %d 处图组把切碎面板全嵌了（最多一组 %d 张，阈值 4）；'
                 '一图一嵌，先按图注整幅重抽再改正文' % (where, n_bad, worst))


def check_images(L, pid, text, idir, all_imgs, where):
    local = set(os.listdir(idir)) if (idir and os.path.isdir(idir)) else set()
    for name in EMBED.findall(text):
        name = name.strip()
        if not re.search(r'\.(png|jpe?g|gif|webp|svg)$', name, re.I):
            continue
        base = os.path.basename(name)
        if base in local:
            continue
        if base in all_imgs:
            L.w(pid, '%s嵌入了别的集群的图片 %s（能显示但归属乱）' % (where, base))
        else:
            L.e(pid, '%s嵌入的图片不存在：%s' % (where, base))


# 前端 stripVaultChrome 会先剥掉的引用行，不算「杂引用块」
CHROME_QUOTE = re.compile(
    r'^>\s*(?:返回索引：|🤖)|^>.*(?:build_refs\.py|库内已入库|自动生成（条目保持原文)')


def blank_verbatim(lines):
    """把 ``` 代码围栏与 $$ 块公式内部的行清空（保留行数，行号不变）。

    `\\begin{cases}` 的分支行以 `>0, & …` 开头，逐行扫描会当成引用块（Example2024 曾因此误报）。
    """
    out, fence, math = [], False, False
    for ln in lines:
        s = ln.strip()
        if not fence and s.count('$$') % 2 == 1:
            math = not math
            out.append('')
        elif not math and s.startswith('```'):
            fence = not fence
            out.append('')
        else:
            out.append('' if (fence or math) else ln)
    return out


SRC_HL = re.compile(
    r'^[ \t]*(?:'
    r'h[ \t]*i[ \t]*g[ \t]*h[ \t]*l[ \t]*i[ \t]*g[ \t]*h[ \t]*t[ \t]*s'   # Elsevier 常拆开字母排版
    r'|k[ \t]*e[ \t]*y[ \t]*p[ \t]*o[ \t]*i[ \t]*n[ \t]*t[ \t]*s'         # AGU 系印的是 Key Points
    r')[ \t]*:?[ \t]*(?:[•·‣▪-][ \t]*\S.*)?$',
    re.I | re.M)


def src_has_highlights(src_txt: str) -> bool:
    """原刊有没有印 Highlights / Key Points 节。

    只认**独立成行**的标题（末尾允许直接跟第一个 bullet，AGU 的 `Key Points: • …` 就这样），
    不认正文里把 highlights 当动词、把 key points 当普通词组用的句子——
    Example2024 / Example2024 / Example2024 都栽在这上面。只扫开头一段：这节只印在首页。

    **Key Points 必须一起认**：prep_article_en 的 FIXED_HEAD 会把它归一成 `## Highlights`，
    漏了它就会把 AGU 论文的真要点误判成捏造（Example2024 已中过一次）。
    """
    return bool(SRC_HL.search(src_txt[:12000]))


def check_english_shell(L, pid, art_en, src_txt=None):
    """英文正文的版式契约。

    单独成函数是为了让入库前的 lint_en_draft.py 直接复用同一份规则：
    以前它只跑 web_lint 那套，比这里松，于是「草稿验过了再搬」搬进来照样报错。

    `src_txt` 给了才校验 Highlights 有无——英文正文是原文重排，Highlights
    该跟原刊一致，不给原文就无从判断，跳过而不是瞎警告。
    """
    for ph in ART_EN_PLACEHOLDERS:
        if ph in art_en:
            L.e(pid, '英文正文占位符残留（英文重排子代理没干活）')
            break
    if MARKER.search(art_en):
        L.e(pid, '英文正文残留构造标记')
    if art_en.count('$$') % 2 == 1:
        L.e(pid, '英文正文块公式 $$ 未闭合（奇数个定界符）')
    check_math_glyphs(L, pid, art_en, '英文正文')
    check_heading_recovery(L, pid, art_en)
    check_keywords(L, pid, art_en, src_txt)
    check_nomenclature_tables(L, pid, art_en)
    h1 = re.search(r'^# .+$', art_en, re.M)
    byline = ''
    if h1:
        rest = art_en[h1.end():]
        nxt = re.search(r'^##\s+', rest, re.M)
        byline = rest[:nxt.start()] if nxt else rest[:800]
    if re.search(r'\^\{\d', byline):
        L.e(pid, '英文正文作者行含 ^{单位号}（应写成一段加粗作者 + 一段单位）')
    if re.search(r'^##\s+(Key Points|要点|通俗摘要|Plain Language Summary)\b', art_en, re.I | re.M):
        L.e(pid, '英文正文含禁用标题（Key Points / 要点 / Plain Language Summary / 通俗摘要）')
    # 英文正文 = 原文重排，Highlights 必须与原刊一一对应：原刊有却丢了要补，
    # 原刊没有却写了就是凭空捏造（旧口径「原文无则从 Abstract 提炼」诱导了 18 篇伪造，已废）。
    if src_txt is not None:
        has_en = bool(re.search(r'^##\s+Highlights\s*$', art_en, re.M))
        has_src = src_has_highlights(src_txt)
        if has_src and not has_en:
            L.w(pid, '原刊印了 Highlights，英文正文却没有（重排时漏掉，回 txt 首页补原文）')
        elif has_en and not has_src:
            L.e(pid, '英文正文的 ## Highlights 原刊根本没有（英文侧禁止提炼，删掉该节；'
                     '提炼版归中文正文的 ## 亮点）')
    if re.search(r'^\*\*Abstract\*\*', art_en, re.M) or not re.search(r'^##\s+Abstract\s*$', art_en, re.M):
        L.e(pid, '英文正文摘要必须用「## Abstract」标题节（禁止行内加粗 **Abstract** 照搬原刊排版）')
    if re.search(r'^(Correspondence to:|Citation:|Received \d|Accepted \d)', byline, re.I | re.M):
        L.e(pid, '英文正文残留期刊页眉（Correspondence / Citation / Received / Accepted）')
    check_en_parity_with_zh(L, pid, art_en, byline, src_txt)
    check_sliced_figure_groups(L, pid, art_en, '英文正文')


# 期刊 PDF 里的版权 / 下载水印，抽文本时会整段带进正文
WATERMARK = re.compile(r'articles are governed by the applicable Creative Commons License'
                       r'|Downloaded from https://onlinelibrary'
                       r'|This is an open access article under the terms', re.I)
# 后置事项标签被期刊拉开字母排版，抽文本时原样留在正文里
BACKMATTER_RAW = re.compile(r'AU\s?T\s?H\s?O\s?R\s+C\s?O\s?N\s?T\s?R\s?I\s?B'
                            r'|AC\s?K\s?N\s?OW\s?L\s?E\s?D\s?G'
                            r'|C\s?O\s?N\s?F\s?L\s?I\s?C\s?T\s+O\s?F\s+I\s?N\s?T\s?E\s?R\s?E\s?S\s?T'
                            r'|DATA\s+AVA\s?I\s?L\s?A\s?B\s?I\s?L\s?I\s?T\s?Y'
                            r'|R\s?E\s?F\s?E\s?R\s?E\s?N\s?C\s?E\s?S'
                            r'|O\s?RC\s?I\s?D')
# 单位块被抽成碎片：一行里三段以上用中文分号拼起来的截断片段
AFFIL_FRAG = re.compile(r'^[^\n]*；[^\n]*；[^\n]*；[^\n]*$', re.M)
REF_SEC_EN = re.compile(r'^##\s+References\s*$', re.M | re.I)
REF_IN_SRC = re.compile(r'^\s*(?:R[ \t]?E[ \t]?F[ \t]?E[ \t]?R[ \t]?E[ \t]?N[ \t]?C[ \t]?E[ \t]?S'
                        r'|References?|Bibliography|参[ \t]*考[ \t]*文[ \t]*献)\s*$', re.M | re.I)
REF_RAW_EN = re.compile(r'^[ \t]*(?:References?|Bibliography)\s*[:.]?\s*$', re.M | re.I)
REF_ENTRY_EN = re.compile(r'^[ \t]*(?:[-*][ \t]+)?(?:\*{0,2}\[\d+\]\*{0,2}[ \t]+|\d+\.[ \t]+)?'
                         r'[A-Z][^\n]{0,100},[^\n]{0,180}\(\d{4}[a-z]?\)\.[ \t]+\S', re.M)
JOURNAL_LINE = re.compile(r'^\*[^*\n]*\d{4}[^*\n]*\*\s*$', re.M)
INLINE_MATH = re.compile(r'(?<!\$)\$(?!\$)[^$\n]{1,120}\$(?!\$)')
NOM_HEAD = re.compile(
    r'^#{1,3}\s+(Nomenclature|List of symbols|Notations?|Notation)\s*$',
    re.I)
HEADING = re.compile(r'^#{1,6}\s+\S')
NOM_ENTRY = re.compile(r'^\$[^$]+\$\s+\S')


def check_nomenclature_tables(L, pid, art_en):
    """符号表必须是 Markdown 表格，不能一段一行。

    原刊 Nomenclature / List of symbols / Notations 是符号–释义对照。
    Example2024 曾把 89 条排成 `$A$ Bottom area, m$^2$` 这种段落，前端看起来不像表。
    """
    lines = art_en.splitlines()
    i, n = 0, len(lines)
    while i < n:
        if not NOM_HEAD.search(lines[i]):
            i += 1
            continue
        title = lines[i].lstrip('#').strip()
        j = i + 1
        while j < n and not HEADING.search(lines[j]):
            j += 1
        block = lines[i + 1:j]
        table_rows = sum(1 for ln in block if ln.strip().startswith('|') and '---' not in ln)
        loose = sum(1 for ln in block if NOM_ENTRY.search(ln.strip()))
        if loose >= 3 and table_rows < 3:
            L.e(pid, '英文正文「%s」有 %d 条符号排成普通段落，应改成 Markdown 表格'
                     '（| Symbol | Description |）' % (title, loose))
        elif table_rows < 3:
            L.w(pid, '英文正文「%s」几乎没有表格行（%d），核对是否漏排符号表'
                     % (title, table_rows))
        i = j


def check_en_parity_with_zh(L, pid, art_en, byline, src_txt=None):
    """英文正文的后置事项与排版检查。

    中英文正式正文各有完整参考表，从同一份已核 refs 复制，不分别重写。
    本函数也供内容阶段的英文草稿复用，只检查实际污染，不提前要求 References；
    正式集群的缺表要求由 check_cluster_en_references 检查。

    - **后置事项**：`AU T H O R C O N T R I B` 这类拉开排的标签还躺在正文里 = 没分节 → 错误
    - **版权水印**：`Creative Commons License` / Wiley 下载串残留 → 错误
    - **单位块**：一行里三段以上用 `；` 拼起来 = 被抽成碎片 → 错误
    - **期刊信息行 / 行内公式**：缺了判警告（体例问题，不阻断入库）
    """
    # 文献条目应在 References 节内，不能揉进其他正文段落。
    ref_sec = REF_SEC_EN.search(art_en)
    en_body = art_en[:ref_sec.start()] if ref_sec else art_en
    if REF_RAW_EN.search(en_body) or len(REF_ENTRY_EN.findall(en_body)) >= 2:
        L.e(pid, '英文正文混入未分节的参考文献标题或条目；'
                 '恢复 `## References`，从同一份已核 refs 复制完整参考表')
    m = BACKMATTER_RAW.search(REF_SEC_EN.sub('', art_en))
    if m:
        L.e(pid, '英文正文残留期刊拉开排的后置事项标签「%s」；'
                 '应分成 `## Author Contributions` / `## Acknowledgments` / '
                 '`## Conflict of Interest Statement` / `## Data Availability Statement` / '
                 '`## References`' % re.sub(r'\s+', ' ', m.group(0))[:28])
    m = WATERMARK.search(art_en)
    if m:
        L.e(pid, '英文正文残留版权/下载水印：%s…' % m.group(0)[:38])
    if AFFIL_FRAG.search(byline or ''):
        L.e(pid, '英文正文单位块是碎片（一行里多段用「；」拼接的截断机构名）；'
                 '照 PDF 首页重建完整机构名，一行一个')
    if byline and not JOURNAL_LINE.search(byline):
        L.w(pid, '英文正文题名块缺斜体期刊信息行（`*期刊名 年份, 卷(期): 页码. DOI: …*`）')
    if len(art_en) > 20000 and len(INLINE_MATH.findall(art_en)) < 5 \
            and re.search(r'\$\$', art_en):
        L.w(pid, '英文正文有块公式却几乎没有行内公式（%d 处）；'
                 '多半是 dump 把上下标压平了，跑 inline_math_from_rich.py'
            % len(INLINE_MATH.findall(art_en)))


def check_unified_references(L, pid, art, src_txt=None):
    """中文正文须保留参考表；中英文应复用同一份已核参考文献数据。"""
    has_refs = ('<!--REFS_AUTO-->' in art) or re.search(
        r'^#{1,6}[^\n]{0,40}?(参\s*考\s*文\s*献|References?)', art, re.M | re.I)
    if has_refs:
        return
    if src_txt and REF_IN_SRC.search(src_txt):
        L.e(pid, '中文正文缺参考文献表，但 txt 里有 References（参考文献装配没跑或失败）')
    else:
        L.w(pid, '中文正文缺参考文献表（txt 也解析不出——源数据问题，需对照原 PDF）')


def check_cluster_en_references(L, pid, art_en, art_zh, src_txt=None):
    """仅正式集群检查英文参考表，避免阻断尚未装配 refs 的内容阶段草稿。"""
    zh_has_refs = ('<!--REFS_AUTO-->' in art_zh) or re.search(
        r'^#{1,6}[^\n]{0,40}?(参\s*考\s*文\s*献|References?)', art_zh, re.M | re.I)
    if not (zh_has_refs or (src_txt and REF_IN_SRC.search(src_txt))):
        return
    ref_sec = REF_SEC_EN.search(art_en)
    if not ref_sec:
        L.e(pid, '正式英文正文缺 `## References`，但原文或中文正文已有参考文献；'
                 '从同一份已核 refs 复制完整参考表，不重新生成')
        return
    rest = art_en[ref_sec.end():]
    next_section = re.search(r'^#{1,2}\s+', rest, re.M)
    ref_body = rest[:next_section.start()] if next_section else rest
    if not re.sub(r'<!--[\s\S]*?-->', '', ref_body).strip():
        L.e(pid, '正式英文正文的 `## References` 为空；从同一份已核 refs 复制完整参考表')


def check_note_swallow(L, pid, text, where):
    """首个「说明」块之前不得有别的引用块。

    文枢 wrapFormulaNotes 把 `> **【说明】**` 渲染成注解卡片。若前面先出现一个不含【说明】的
    引用块（最常见是把作者/期刊行写成 `> **文献信息**：…`），旧版正则会从那里一路吞到说明块，
    把中间整段正文卷进卡片里。渲染器已加护栏，这里守住内容侧，避免 Obsidian 观感同样错乱。
    """
    body = re.sub(r'^---[\s\S]*?\n---\s*', '', text)
    lines = blank_verbatim(body.split('\n'))
    blocks, i, n = [], 0, len(lines)
    while i < n:
        if lines[i].startswith('>') and not CHROME_QUOTE.search(lines[i]):
            j = i
            while j < n and lines[j].startswith('>'):
                j += 1
            blocks.append((i + 1, '\n'.join(lines[i:j])))
            i = j
        else:
            i += 1
    first = next((k for k, (_, b) in enumerate(blocks) if '【说明】' in b), None)
    if first is None:
        return
    strays = [ln for ln, b in blocks[:first] if '【说明】' not in b]
    if strays:
        L.e(pid, '%s在首个「说明」块（L%d）之前有 %d 个杂引用块（L%s），会被渲染成说明卡吞掉中间正文；'
                 '作者/单位/期刊行请写成裸加粗段与裸文本段，不要用 >'
            % (where, blocks[first][0], len(strays), '、L'.join(str(x) for x in strays[:3])))


def check_eqno_ref(L, pid, text, where):
    """公式号被 build_refs --inline 误链成参考文献锚点。"""
    hits = re.findall(r'(?:式|公式|方程|等式|Eqs?\.?|Equations?)\s*\[\[#\^ref-\d+\|\d+\]\]',
                      text, re.I)
    if hits:
        L.e(pid, '%s有 %d 处公式号被链成参考文献（如 %s）；应写 式 (N)，跑 fix_article 可自动还原'
            % (where, len(hits), hits[0]))


# images.md 里记录的「这篇 PDF 一共印了几条图注」。extract_images 写的是
# `- 图注识别：图1(p2)、…（共 N 处）`，audit_images --backfill 回填的是同一行体例。
CAPTION_COUNT = re.compile(r'^- 图注识别：.*?（共 (\d+) 处）\s*$', re.M)
# 图注条数太少时，多半是这篇的图注体例没被识别出来，不能拿它当分母
MIN_TRUSTED_CAPTIONS = 3


def check_figure_coverage(L, pid, imd, fig_files, embedded):
    """图覆盖：分母必须是 **PDF 印了几条图注**，不是磁盘上躺着几个文件。

    磁盘图数会因过度抽取虚高——缺号时抽图会整页渲染兜底，跨栏复合图还会被切成
    好几张。Example2024 那篇博论 PDF 只印了 5 条图注，磁盘上却有 76 张，
    拿磁盘数当分母就报「5/76 漏 71 张」，而正文其实一张没漏。

    反过来，抽取阶段就没抽出来的图，旧口径根本查不出：Example2024 的 PDF 有 25 条图注、
    磁盘只有 22 张，正文把这 22 张全嵌了，「22/22」看起来完美无缺。

    2026-09-01 用 audit_images 回 PDF 全库对账，旧口径 24 条警告里 21 条是误报、
    另有 7 篇真漏图一条没报。改判后两头都对上。
    """
    m = CAPTION_COUNT.search(imd)
    if not m:
        return                      # 没记图注数：跑 audit_images --backfill 补上再查
    caps = int(m.group(1))
    if caps < MIN_TRUSTED_CAPTIONS:
        return
    used = sum(1 for f in fig_files if f in embedded)
    if len(fig_files) < caps:
        L.e(pid, '抽图阶段就漏了：PDF 印了 %d 条图注，images/ 只有 %d 张；'
                 '跑 reextract_images.py "<clusterDir>" 重抽' % (caps, len(fig_files)))
    elif used < caps:
        L.w(pid, '正文嵌图 %d 张，少于 PDF 的 %d 条图注（磁盘 %d 张，多出的是整页兜底/'
                 '复合图切片）；核对是哪几条图注没落到正文' % (used, caps, len(fig_files)))
    elif caps >= 8 and used >= caps * 2:
        # Example2024 点云篇：20 条图注、61 张面板碎片被正文全嵌。图注识别偏低时
        # （3 条图注嵌 7 张）仍允许，所以只在图注足够多、嵌图翻倍时判错误。
        L.e(pid, '正文嵌图 %d 张，约为 PDF %d 条图注的 %.1f 倍；多半是把切碎面板全嵌了。'
                 '一图一嵌，先 reextract_images.py 按图注整幅重抽，再改正文'
                 % (used, caps, used / float(caps)))


# 已经成为 Markdown 标题的章节编号
SEC_HEAD_NUM = re.compile(r'^#{2,6}\s+(\d{1,2}(?:\.\d{1,2})*)\b', re.M)
# 散落在正文行里的「编号 + 标题词」：`…equation 2.1 Description of the superquadric…`
INLINE_SEC_TITLE = re.compile(
    r'(?:(?<=[.\s])|^)(\d{1,2}(?:\.\d{1,2})+)\s+([A-Z][a-z]+(?:\s+[a-z]+){0,3})')
# 层级恢复得太差的门槛，实测定的：正常论文约 2000–4000 字符一个标题，
# Example2024 是 32035、Example2024 是 30167（96 KB 正文只有 3 个标题）
HEAD_DENSITY_ERR = 10000
HEAD_DENSITY_WARN = 6000
HEAD_MIN_BODY = 20000


def credible_section_num(num: str, known: set) -> bool:
    """`num` 真的是个章节号，而不是正文里的一个小数。

    `INLINE_SEC_TITLE` 只看形状（数字 + 空格 + 大写词），于是「粒径 0.25 Particle
    diameter」「体积分数 0.02 Voidage」这类正文里遍地都是的小数全被当成漏掉的章节号
    ——实测 12 篇报错里有 5 篇（Example2024 / Example2024 / Example2024 / Example2024 /
    Example2024）纯粹是这么误报出来的。两条判据把它们挡掉：

    1. **章节号不带前导零**：`0.25`、`0.50`、`4.0`、`1.00` 一律不是章节号；
    2. **必须有同族编号**：真章节 `2.1` 漏了，同父的 `2.2`／`2.1.1` 总还在——要么已是
       标题，要么同样躺在正文里当孤儿，所以 `known` 要把标题号和其它孤儿候选一起算。
       `11.6`、`67.1` 这种小数举目无亲，据此剔除。

    `known` 含自己，所以找同族时必须把自己排掉，否则任何编号都能自证。
    """
    parts = num.split('.')
    if any(p == '0' or (len(p) > 1 and p[0] == '0') for p in parts):
        return False
    parent = '.'.join(parts[:-1])
    return parent in known or any(k != num and k.startswith(parent + '.') for k in known)


def check_heading_recovery(L, pid, art_en):
    """英文正文的章节层级到底恢复出来没有——「先英后中」新流程的验收关口。

    双栏 PDF dump 里标题和正文本来就粘在一行（`2 Non-spherical representation …
    2.1 Description of the superquadric equation The superquadric equation is …`），
    确定性脚本没有语义理解、恢复不出层级。2026-09-01 实测：中文侧 Example2024 有
    38 个标题，英文侧同一篇只有 3 个——因为中文侧有子代理通读全文，英文侧只有脚本。

    A1 英文重排必须把层级建出来，A2 中文翻译才有骨架可继承，所以这条必须是硬门禁。
    两个信号互补：孤儿编号精确但保守，标题密度粗糙但抓得住灾难性的那几篇。
    """
    body = re.split(r'^##\s+References', art_en, flags=re.M)[0]
    heads = re.findall(r'^#{2,6}\s+\S', body, re.M)
    head_nums = set(SEC_HEAD_NUM.findall(body))
    cand = set()
    for line in body.splitlines():
        s = line.strip()
        if not s or s[0] in '#|>!$':
            continue
        for num, _word in INLINE_SEC_TITLE.findall(s):
            if num not in head_nums:
                cand.add(num)
    known = head_nums | cand
    orphan = {n for n in cand if credible_section_num(n, known)}
    density = len(body) / max(len(heads), 1)
    if len(orphan) >= 3:
        L.e(pid, '英文正文章节层级没恢复：正文里有 %d 个编号章节名（%s）没成为标题，'
                 '还粘在段落里；派 A1 英文重排按原文层级重建'
            % (len(orphan), '、'.join(sorted(orphan)[:5])))
    elif len(body) > HEAD_MIN_BODY and density >= HEAD_DENSITY_ERR:
        L.e(pid, '英文正文章节层级几乎没恢复：%d 字符只有 %d 个标题（平均 %d 字符一个，'
                 '正常是 2000~4000）；派 A1 英文重排按原文层级重建'
            % (len(body), len(heads), density))
    elif len(body) > HEAD_MIN_BODY and density >= HEAD_DENSITY_WARN:
        L.w(pid, '英文正文标题偏少：%d 字符只有 %d 个标题（平均 %d 字符一个）；'
                 '核对是不是有整节标题没恢复' % (len(body), len(heads), density))


# 中文正文 `## 亮点` 小节里，标明这批要点是 AI 提炼而非原刊自印的说明块
AI_HL_NOTICE = '> **【说明】** 本节要点由 AI 通读全文提炼，原刊未印 Highlights / Key Points。'
AI_HL_MARK = re.compile(r'^>\s*\*\*【说明】\*\*\s*本节要点由\s*AI\s*通读全文提炼', re.M)
HL_ZH_HEAD = re.compile(r'^##\s+亮点\s*$', re.M)


def highlights_section(art):
    """取中文正文 `## 亮点` 小节的正文（不含标题），没有该节返回 None。"""
    m = HL_ZH_HEAD.search(art)
    if not m:
        return None
    rest = art[m.end():]
    nxt = re.search(r'^##\s', rest, re.M)
    return rest[:nxt.start()] if nxt else rest


def check_highlights_provenance(L, pid, art, src_txt):
    """`## 亮点` 到底是原刊印的要点，还是 AI 自己提炼的——必须让读者分得清。

    技能对两侧的口径本来是不对称的：英文正文禁止捏造 Highlights（原刊没有却写了
    就是伪造，曾一次性诱导出 18 篇），中文正文却允许提炼、`## 亮点` 还是必填项。
    允许提炼没问题，**不标注来源**才是问题——2026-09-01 全库 95 篇里有 84 篇的
    亮点是 AI 读完全文总结的，和期刊自印的要点长得一模一样，读者分不出来。
    """
    section = highlights_section(art)
    if section is None or src_txt is None:
        return
    marked = bool(AI_HL_MARK.search(section))
    if src_has_highlights(src_txt):
        if marked:
            L.e(pid, '原刊印了 Highlights，中文亮点却标着「AI 提炼」；这批要点译自原文，'
                     '删掉该说明块（跑 fix_article 自动处理）')
    elif not marked:
        L.e(pid, '原刊没印 Highlights，这节亮点是 AI 提炼的却没有标注；'
                 '在亮点列表之后补一行「> **【说明】** 本节要点由 AI 通读全文提炼…」'
                 '（跑 fix_article 自动补）')


EQ_BLOCK = re.compile(r'\$\$(.+?)\$\$', re.S)
EQ_TAGGED = re.compile(r'\\tag\{')
CJK_RE = re.compile(r'[\u4e00-\u9fff]')


def eq_transplant_lost(art, art_en):
    """返回 (中文可搬条数, 英文块公式条数, 是否判定为对拷整批失效)。

    验收与返工共用这一份判据：本模块拿它报错误，prep_article_en 拿它认出
    「旧版脚本产的陈旧机器稿」从而允许覆盖返工。两处各写一份阈值迟早对不上。

    含中文的 `$$` 不计入——那是译者自己加的公式，本来就不在对拷范围。
    """
    zh_tagged = [b for b in EQ_BLOCK.findall(art)
                 if EQ_TAGGED.search(b) and not CJK_RE.search(b)]
    en_blocks = EQ_BLOCK.findall(art_en)
    return len(zh_tagged), len(en_blocks), bool(len(zh_tagged) >= 3 and not en_blocks)


TAB_SEP = re.compile(r'^\s*\|[\s:|-]+\|\s*$', re.M)
# 真表题整行加粗收尾（`**Table 1: Coefficients for Eq.(7)**`）。松成「行首 **Table N」
# 会把 `**Table 11** shows the relative error…` 这类加粗开头的正文句子一起算进来——
# 实测 Example2024 松判 25 条、严判 1 条，Example2024 松判 9 条、严判 0 条。
TAB_CAP = re.compile(r'^\*\*Tab(?:le)?\s*\.?\s*\d+[^\n]*\*\*\s*$', re.M | re.I)


KW_SEC = re.compile(r'^##\s+Keywords\s*$', re.M | re.I)
KW_ANY = re.compile(r'K\s?E\s?Y\s?\s?W\s?O?\s?R\s?D\s?S|^\s*\**Keywords?\b', re.M | re.I)
KW_SRC = re.compile(r'K\s?E\s?Y\s?\s?W\s?O?\s?R\s?D\s?S|\bKeywords?\b|\bKey\s+words\b', re.I)


def check_keywords(L, pid, art_en, src_txt=None):
    """英文正文的关键词必须是 `## Keywords` 标题节。

    `luna-a1-brief` 的产出要求里原本**一个字都没提 Keywords**，脚本侧也没有规则，
    于是 2026-09-01 实测全库形态四分五裂：29 篇是标题节、6 篇是加粗行、
    2 篇原样留着期刊拉开排的 `K E Y WO R D S`、11 篇别的形态、
    **25 篇完全没有——其中 18 篇原刊明明印了**。

    中文侧的 `luna-a-brief` 早就写死了「摘要末尾必须有 `**关键词：**` 行」，
    英文侧漏了这条，所以谁也没发现。

    判据与 Highlights 那条对称：**原刊印了才该有，原刊没印就不许硬造**。
    拿不到原文 dump 时跳过，不瞎报。
    """
    if KW_SEC.search(art_en):
        return
    if KW_ANY.search(art_en):
        L.e(pid, '英文正文的关键词不是 `## Keywords` 标题节（还是加粗行或 dump 原样）；'
                 '跑 normalize_keywords.py 统一')
        return
    if src_txt and KW_SRC.search(src_txt[:12000]):
        L.e(pid, '英文正文缺 `## Keywords` 节，但原刊印了关键词；'
                 '跑 normalize_keywords.py，截不干净的派 A1 照 PDF 补')


def check_table_parity(L, pid, art, art_en):
    """英文正文该有的表整批缺失：中文侧有表，英文侧一张都没有。

    表格和公式一样与语言无关——同一篇论文中英两侧的表数天然同量级，中文有、英文
    一张没有只可能是没落进去。2026-09-01 实测全库 15 篇是这个状态，其中 11 篇是
    `extract_tables.py` 抽表阶段就抽空了（`.tables.md` 写着「总计：0 张表格」），
    英文侧无料可注入；中文侧则是 A 档子代理通读 PDF 自己把表建了出来。
    Example2024 最严重：中文 17 张表，英文 0 张，而 17 条表题一条不少地立在那里，
    读者看到的就是「**Table 1: Coefficients for Eq.(7)**」下面空空如也。

    跟公式对拷失效当初一样，**这件事以前没有任何规则查**，于是静默复制了 15 次。

    表题多于表体只判警告不判错误：有些表是被当作图片抽出来的，表体确实不在
    Markdown 里，一律判错误会误伤（实测 5 篇属于这一类）。
    """
    if not art_en:
        return
    zh_tab, en_tab = len(TAB_SEP.findall(art)), len(TAB_SEP.findall(art_en))
    en_cap = len(TAB_CAP.findall(art_en))
    if zh_tab and not en_tab:
        L.e(pid, '英文正文一张表都没有，中文正文有 %d 张（英文侧还立着 %d 条表题）；'
                 '查 .tables.md 是不是「总计 0 张」，抽表失败就得派 A1 照 PDF 重建'
            % (zh_tab, en_cap))
    elif en_cap >= 2 and en_tab < en_cap:
        L.w(pid, '英文正文 %d 条表题只对上 %d 张表体；核对缺的那几张是被当图片抽走了，'
                 '还是压根没落位' % (en_cap, en_tab))


def check_eq_parity(L, pid, art, art_en):
    """英文正文该有的公式整批丢失：中文侧转好了 LaTeX，英文侧一条块公式都没有。

    prep_article_en 会按公式号把中文正文的 `$$…\\tag{N}$$` 原样搬进英文草稿——
    公式与语言无关，两侧数量天然同量级。中文一堆、英文零条只可能是对拷没生效，
    此时英文正文里留着的是 dump 的散字符（`Ms = Nz ∑ nz=1 …`）在冒充公式，
    读者看到的是乱码而不是公式。旧版脚本产的英文正文全库有 42 篇是这个状态，
    而当时没有任何一条规则查得出来，于是它们带着「严格验收通过」的记录入了库。
    """
    zh_n, en_n, lost = eq_transplant_lost(art, art_en)
    if lost:
        L.e(pid, '英文正文一条块公式都没有，中文正文却有 %d 条带公式号的 LaTeX；公式对拷没生效，'
                 '英文侧现在是 dump 散字符冒充公式。重跑 prep_article_en.py 出草稿再按门禁晋级'
            % zh_n)
    elif zh_n >= 6 and en_n * 2 < zh_n:
        L.w(pid, '英文正文块公式 %d 条、中文带号 LaTeX %d 条，落差过半；'
                 '可能有整节公式没对拷上，核对 prep_article_en 的「待转」计数' % (en_n, zh_n))


QUOTED_CAPTION = re.compile(r'^\s*>\s?\*\*\s*(?:图|表|Fig|Figure|Table)\s*\d', re.I | re.M)


def check_quoted_caption(L, pid, text, where):
    """图注被写成引用块。

    `> **图 1.** …` 在文枢会渲染成引用卡片而不是图注；若它出现在首个「说明」块之前，
    还会成为说明卡吞正文的触发点。图注应当是图片行下方紧跟的普通段落。
    """
    hits = QUOTED_CAPTION.findall(text)
    if hits:
        L.e(pid, '%s有 %d 行图注被包在引用块里（> **图 N**）；图注要写成图片行下方的普通段落，不加 >'
            % (where, len(hits)))


# 图注行常见「中文（English caption）」双语写法，是有意保留原文，不算残留
BODY_EN_FIGREF = re.compile(
    r'(?<![A-Za-z_])(?:Fig(?:ure)?s?\.|Tables?\s)\s*\d{1,3}', re.I)
# 「整理自原文 Table 1」这类明确指向英文原件的说法，保留英文才对
SOURCE_REF = re.compile(r'(?:原文|原著|原刊|原表|原图)\s*$')
EN_MASK = re.compile(
    r'!?\[\[[^\]]*\]\]|`[^`\n]+`|\$[^$\n]+\$|[\w\u4e00-\u9fff-]+_page\d+_fig[A-Za-z]?\d+[\w.]*')


def check_untranslated_figref(L, pid, text, where):
    """中文正文正文段里残留英文图表引用（「见 Fig. 7」没译成「见图 7」）。"""
    body = re.split(r'^##\s*(?:📚\s*)?参考文献', text, flags=re.M)[0]
    bad = 0
    for line in body.split('\n'):
        s = line.strip()
        if not s or not re.search(r'[\u4e00-\u9fff]', s):
            continue
        if re.match(r'^(?:\*\*|>)?\s*(?:图|表|Fig|Table)', s, re.I):
            continue  # 图注行（含双语图注）
        clean = EN_MASK.sub('', s)
        if any(not SOURCE_REF.search(clean[:m.start()])
               for m in BODY_EN_FIGREF.finditer(clean)):
            bad += 1
    if bad:
        L.w(pid, '%s有 %d 行正文残留英文图表引用（Fig. N / Table N）；中文正文应写「图 N」「表 N」'
            % (where, bad))


def lint(vault, pid_filter=None):
    L = Lint()
    all_imgs = {os.path.basename(p) for p in
                glob.glob(os.path.join(vault, 'Papers', '**', 'images', '*.*'), recursive=True)}

    clusters = collect_clusters(vault, pid_filter)
    for pid, idx_path, cdir, idir in clusters:
        idx = rd(idx_path)
        fm, body = fm_body(idx)
        # --- index ---
        if MARKER.search(idx):
            L.e(pid, 'index 残留构造标记（strip_markers 没跑）')
        for ph in IDX_PLACEHOLDERS:
            if ph in idx:
                L.e(pid, 'index 占位符未回填：%s' % ph)
                break
        if re.search(r'^status:\s*"?skeleton', fm, re.M):
            L.e(pid, 'index status=skeleton（流水线没走完）')
        if not re.search(r'^citekey:\s*"?\S', fm, re.M):
            L.w(pid, 'index 缺 citekey（build_bib 没跑）')
        if not re.search(r'^reading:\s*"?\S', fm, re.M):
            L.e(pid, 'index 缺 reading 字段（文枢必填：待读/在读/已读/重读）')

        if not cdir:
            L.e(pid, '找不到 content/ 目录（集群结构破损）')
            continue
        # --- 正文 ---
        art = rd(os.path.join(cdir, pid + '.正文.md'))
        for ph in ART_PLACEHOLDERS:
            if ph in art:
                L.e(pid, '正文翻译占位符残留（翻译子代理没干活）')
                break
        if MARKER.search(art):
            L.e(pid, '正文残留构造标记')
        if art.count('$$') % 2 == 1:
            L.e(pid, '正文块公式 $$ 未闭合（奇数个定界符）')
        check_math_glyphs(L, pid, art, '正文')
        if ('<!--REFS_AUTO-->' in art) != ('<!--/REFS_AUTO-->' in art):
            L.e(pid, '正文 REFS_AUTO 标记破损（有开无关或反之）')
        if '[[[' in art:
            L.w(pid, '正文残留三层括号链接（历史 bug，重跑 build_refs --inline 自愈）')
        check_unified_references(L, pid, art, rd(os.path.join(cdir, pid + '.txt')) or None)
        for ln in art.splitlines():
            if ln.startswith('|') and re.search(r'(?<!\\)(?<!&[lg]t)[<>]', ln.replace('\\lt', '').replace('\\gt', '').replace('&lt;', '').replace('&gt;', '')):
                L.w(pid, '正文表格行含裸 </>（HTML 转义会崩表）：%s' % ln[:60])
                break
        check_images(L, pid, art, idir, all_imgs, '正文')
        check_sliced_figure_groups(L, pid, art, '正文')
        fig_files = []
        if idir and os.path.isdir(idir):
            # `_pic\d+` 是版面里的内嵌位图（照片、渲染图），和 `_fig\d+` 一样是正经图，
            # 抽图与 audit_images 两边都算它。这里漏掉就会把它对应的那条图注当成
            # 「抽图阶段漏了」误报（Example2024 有 2 张 pic，13 条图注只数出 11 张）。
            fig_files = [f for f in os.listdir(idir)
                         if re.search(r'_page\d+_(?:fig|pic)[A-Za-z]?\d+\.(png|jpe?g)$', f, re.I)]
        embedded = {os.path.basename(n.strip()) for n in EMBED.findall(art)}
        if len(fig_files) >= 3:
            hit = sum(1 for f in fig_files if f in embedded)
            if hit < min(3, len(fig_files)):
                L.e(pid, '正文几乎没嵌抽出的图（images 有 %d 张 fig，正文只嵌了 %d）' % (len(fig_files), hit))
        # --- 抽图覆盖检查（extract_images 写入 images.md 的机器可读段） ---
        if idir and os.path.isdir(idir):
            imd = rd(os.path.join(idir, pid + '.images.md'))
            check_figure_coverage(L, pid, imd, fig_files, embedded)
            m = re.search(r'^- 覆盖缺失：(.+)$', imd, re.M)
            if m and m.group(1).strip() != '无':
                L.e(pid, '抽图覆盖缺失（图注识别到但没抽出）：%s' % m.group(1).strip())
            m = re.search(r'^- 整页兜底：(.+?)（', imd, re.M)
            if m:
                L.w(pid, '存在整页兜底图（含正文，建议人工裁切替换）：%s' % m.group(1).strip())
            # 图质检查段：近乎空白 / 区内无图形墨迹——抽出来了但裁错位置的图
            m = re.search(r'^## 图质检查\s*$(.*?)(?=^## |\Z)', imd, re.M | re.S)
            if m:
                bad = [l.strip('- ').strip() for l in m.group(1).splitlines() if l.startswith('- ')]
                used = [b for b in bad if b.split('：')[0] in embedded]
                if used:
                    L.w(pid, '正文引用了裁切可疑的图（建议重抽或人工裁切）：%s'
                        % '；'.join(used[:4]) + ('…' if len(used) > 4 else ''))
        if re.search(r'^# .*(中文翻译|方法原理精讲)', art, re.M):
            L.e(pid, '正文 H1 不要加「（中文翻译）」等后缀（文枢 content-contract）')
        if re.search(r'^##\s+(要点|通俗摘要|Key Points)\b', art, re.M):
            L.e(pid, '正文含禁用标题（要点 / 通俗摘要 / Key Points）；Highlights 用「## 亮点」')
        if not re.search(r'^##\s+亮点\s*$', art, re.M):
            L.e(pid, '正文缺 ## 亮点（文枢前置块）')
        check_highlights_provenance(L, pid, art, rd(os.path.join(cdir, pid + '.txt')) or None)
        if re.search(r'^\*\*摘要\*\*', art, re.M) or not re.search(r'^##\s+摘要\s*$', art, re.M):
            L.e(pid, '正文摘要必须用「## 摘要」标题节（禁止行内加粗 **摘要** 照搬原刊排版）')
        check_note_swallow(L, pid, art, '正文')
        check_eqno_ref(L, pid, art, '正文')
        check_quoted_caption(L, pid, art, '正文')
        check_untranslated_figref(L, pid, art, '正文')
        if os.path.isfile(os.path.join(cdir, pid + '.cards.md')):
            L.e(pid, '存在已废弃的概念卡 <pid>.cards.md（闪卡随 Obsidian 于 2026-08 移除）；删掉该文件')
        # --- 英文正文（重排版；仅英文源论文有） ---
        art_en = rd(os.path.join(cdir, pid + '.正文.en.md'))
        if art_en:
            src_txt = rd(os.path.join(cdir, pid + '.txt')) or None
            check_english_shell(L, pid, art_en, src_txt)
            check_cluster_en_references(L, pid, art_en, art, src_txt)
            check_note_swallow(L, pid, art_en, '英文正文')
            check_quoted_caption(L, pid, art_en, '英文正文')
            check_images(L, pid, art_en, idir, all_imgs, '英文正文')
            check_eq_parity(L, pid, art, art_en)
            check_table_parity(L, pid, art, art_en)
        # --- notes ---
        notes = rd(os.path.join(cdir, pid + '.notes.md'))
        if notes:
            if MARKER.search(notes):
                L.e(pid, 'notes 残留构造标记')
            for ph in NOTE_PLACEHOLDERS:
                if ph in notes:
                    L.e(pid, 'notes 占位符未回填：%s' % ph)
                    break
            for ph in NOTE_TEMPLATE_BITS:
                if ph in notes:
                    L.w(pid, 'notes 深度分析/写作逻辑模板残留：%s' % ph[:24])
                    break
            check_images(L, pid, notes, idir, all_imgs, 'notes')
        else:
            L.e(pid, '缺 notes 文件')
        if not os.path.isfile(os.path.join(cdir, pid + '.txt')):
            L.w(pid, '缺全文缓存 txt（机器复用/参考文献提取都依赖它）')

    # --- 全局 ---
    if not pid_filter:
        reg = os.path.join(vault, '30_Terms', '术语', '_registry.json')
        if os.path.isfile(reg):
            try:
                json.load(open(reg, encoding='utf-8'))
            except Exception as ex:
                L.e('术语库', 'registry JSON 解析失败：%s' % ex)
        inbox = glob.glob(os.path.join(vault, 'PDFs', '*.pdf'))
        if inbox:
            L.i('收件箱有 %d 个 PDF 待入库：%s' % (len(inbox),
                '、'.join(os.path.basename(p) for p in inbox[:5])))
    return L, len(clusters)


def main():
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--vault', required=True)
    ap.add_argument('--paper', default=None, help='只查 pid 含此子串的论文（入库收尾用）')
    ap.add_argument('--report', action='store_true', help='写 90_系统/_质检报告.md')
    a = ap.parse_args()

    L, n = lint(a.vault, a.paper)
    lines = []
    for tag, items in (('❌', L.errors), ('⚠️', L.warns)):
        for pid, msg in items:
            lines.append('%s %s ｜ %s' % (tag, pid, msg))
    for m in L.infos:
        lines.append('ℹ️ ' + m)
    print('\n'.join(lines) if lines else '✅ 全部通过')
    print('—— 质检 %d 个集群：%d 错误 · %d 警告' % (n, len(L.errors), len(L.warns)))

    if a.report:
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        R = ['# 🧪 入库质检报告', '', '> %s 由 lint_cluster.py 生成（勿手改）。'
             '错误=必修（流水线走样），警告=酌情。' % now, '',
             '共查 %d 个集群：**%d 错误 · %d 警告**' % (n, len(L.errors), len(L.warns)), '']
        if L.errors:
            R += ['## ❌ 错误', ''] + ['- **%s**：%s' % x for x in L.errors] + ['']
        if L.warns:
            R += ['## ⚠️ 警告', ''] + ['- %s：%s' % x for x in L.warns] + ['']
        if L.infos:
            R += ['## ℹ️ 提示', ''] + ['- %s' % m for m in L.infos]
        out = os.path.join(a.vault, '90_系统', '_质检报告.md')
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, 'w', encoding='utf-8').write('\n'.join(R) + '\n')
        print('报告：%s' % out)
    sys.exit(1 if L.errors else 0)


if __name__ == '__main__':
    main()
