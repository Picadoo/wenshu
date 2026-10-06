"""把 PDF 机器 dump `content/<pid>.txt` 预清洗成 `<pid>.正文.en.md` 草稿。

这一步只做**确定性的机械修复**，不替代 references/prompts.md 提示词 C 的人工校订：

  ① 去 `----- Page N -----` 分页标记
  ② 按跨页重复度识别并删掉 running header / footer（页眉页脚、期刊水印、页码）
  ③ 按黑名单删出版社栏目行（Downloaded via / Cite This / Contents lists 等）
  ④ 软连字符断词拼回 —— 用**全文词表**判定该不该保留连字符，
     `non-` + `spherical` 若全文别处出现过 `non-spherical` 就保留连字符，
     出现过 `nonspherical` 才拼掉，避免把技术复合词改错
  ⑤ 硬断行接回成段落；短行 + 句末标点视作段落结束
  ⑥ 识别章节标题（`3.2 Contact model` → `### 3.2 Contact model`）与
     Abstract / Highlights / Keywords 等固定节
  ⑦ References 及其之后整段截掉（中文正文末尾已有 build_refs.py 生成的带链接版本，英文 tab 复用）
  ⑧ 按页插入该页抽出的配图 `![[<pid>_pageN_figM.png|700]]`，图注取该页 `Fig. N` 开头的行

**产物对拷（不让同一份内容被手搓两遍）**：

  ⑨ 表格：`extract_tables.py` 已从 PDF 版面解析出**英文原表**，按表号原位注入表题之后，
     并吃掉 dump 里被打散成一列一个词的表体碎片
  ⑩ 公式：中文 `正文.md` 里的 `$$…\tag{N}$$` 是**语言无关**的，按公式号搬进英文草稿，
     替换 dump 里那串散字符。中文正文还没写时自动跳过，只留 TODO 标出公式位置。
  ⑪ 字形：Springer 系 PDF 抽文本会丢 Plane-1 高位，把数学字母 U+1D400–U+1D7FF
     整体减 0x10000 落进谚文区（`휌` 其实是 `𝜌`）。加回高位再 NFKC 折平，纯算术无损。

留给人工的（草稿里以 `<!-- TODO … -->` 标出，别静默略过）：
  单位行、被页脚打断后需要缝回的段落、没对拷到的公式、图注归位核对。

用法：
    python prep_article_en.py --vault vault --out _work/en-draft [--only <pid>] [--limit N]
                              [--no-transplant]
"""
import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.config import load_config as load_skill_config  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_tables import load_tables            # noqa: E402  同目录脚本，复用表格索引解析
# 字形还原的判据与 lint_cluster 共用一份：这边洗 dump、那边做验收，
# 两处各写一份正则迟早走样（fix_article 也是这么复用的）
from lint_cluster import (restore_math_glyphs, eq_transplant_lost,   # noqa: E402
                          EQ_BLOCK as EQ_BLOCK_RE, LOST_PLANE1 as LOST_PLANE1_RE)

CJK = re.compile(r'[\u4e00-\u9fff]')
PAGE = re.compile(r'^-{3,}\s*Page\s+(\d+)\s*-{3,}$')

# PDF 连字合排字符：不展开的话 "ﬂuid" 在英文 tab 里双击查不到词
LIGATURES = {
    '\ufb00': 'ff', '\ufb01': 'fi', '\ufb02': 'fl', '\ufb03': 'ffi',
    '\ufb04': 'ffl', '\ufb05': 'st', '\ufb06': 'st',
    '\u2212': '-', '\u00ad': '',
}
LIG_RE = re.compile('[' + ''.join(LIGATURES) + ']')

# 出版社栏目行：整行匹配即删
FURNITURE = re.compile(
    r'^(?:'
    r'Downloaded (?:via|from)\b.*|'
    r'See https?://\S+.*|'
    r'Cite This:.*|'
    r'Contents lists available.*|'
    r'journal homepage:.*|'
    r'www\.\S+|https?://\S+|'
    r'ISSN[\s:].*|'
    r'©\s*\d{4}.*|Copyright\s*©.*|'
    r'All rights reserved\.?|'
    r'Published by .*|'
    r'This is an open access article.*|'
    r'(?:Received|Revised|Accepted|Available online|Published)\s*:?\s*'
    r'(?:\d{1,2}\s+\w+\s+\d{4}|\w+\s+\d{1,2},?\s+\d{4})?\.?|'
    # Elsevier 把收稿/修回/录用挤成一整行，后面常跟 ISSN 与版权声明
    r'(?:Received|Accepted)\s+\d{1,2}\s+\w+\s+\d{4}[;,].*|'
    r'Correspondence to:.*|Citation:.*|'
    r'(?:Article|Review|Research Article|ORIGINAL PAPER|Original Article|'
    r'RESEARCH ARTICLE|Regular Article)|'
    r'\d{1,4}|'                       # 孤立页码
    r'[ivxlIVXL]{1,6}|'               # 罗马页码
    r'doi:?\s*10\.\d{4,}/\S+|'
    r'https?://doi\.org/\S+|'
    r'[a-z0-9.-]+\.(?:org|com|net|edu|gov)(?:/\S*)?|'   # 裸域名水印 pubs.acs.org/IECR
    r'(?:January|February|March|April|May|June|July|August|September|'
    r'October|November|December)\s+\d{1,2},?\s+\d{4}|'  # Received/Accepted 拆行后的裸日期
    r'\d{1,2}\s+(?:January|February|March|April|May|June|July|August|'
    r'September|October|November|December)\s+\d{4}|'
    r'S\s+Supporting Information|Supporting Information'
    r')$', re.I)

# 段内水印：出版社水印常被 dump 硬折进正文行，接成段落后就缝在句子中间，
# FURNITURE 是整行匹配、管不到这种。只收「起止明确的成串水印」，
# 绝不按「含 URL」之类的粗条件清除——正文里的 GPIV、GitHub、数据仓库链接是真内容。
SCRUB = [
    # Wiley：`10969853, 2024, 16, Downloaded from <url> by <机构>, Wiley Online Library on [日期]. See the Terms and Conditions … rules of use; OA articles are governed by …`
    re.compile(r'\d{6,10},\s*\d{4},\s*\d+,\s*Downloaded from \S+.*?'
               r'(?:applicable Creative Commons License|rules of use;?)', re.I | re.S),
    re.compile(r'Downloaded from \S+\s+by [^.]{0,90}?Wiley Online Library on \[[^\]]*\]\.', re.I),
    # AIP：版权声明 + 下载者 IP + 访问时间
    re.compile(r'This article is copyrighted as indicated in the article\.\s*'
               r'Reuse of AIP content is subject to the terms at:\s*\S+\s*'
               r'(?:Downloaded to\s*IP:\s*(?:\d{1,3}(?:\.\d{1,3}){3})?'
               r'(?:\s*On:\s*[^.]{0,40}\.)?)?', re.I),
    re.compile(r'Redistribution subject to [^.]{0,90}\.', re.I),
    re.compile(r'Published under an exclusive license by [^.]{0,40}\.\s*https?://\S+', re.I),
    # ACS
    re.compile(r'Downloaded via [A-Z][^.]{0,70} on [^.]{0,40}\.', re.I),
    # Elsevier / Particuology 首页页脚：ISSN 或 © 年 + 出版方 + 权利声明。
    # 出版方与权利声明之间常隔着句点（`… Academy of Sciences. Published by Elsevier B.V.`），
    # 所以中段不能用 [^.]，得允许跨句，靠长度上限兜住不越界。
    re.compile(r'\b\d{4}-\d{3}[\dX]\s*/\s*©?\s*\d{4}[\s\S]{0,200}?Published by [\s\S]{0,90}?\.'
               r'(?:\s*All rights (?:are )?reserved[^.]{0,60}\.)?', re.I),
    re.compile(r'©\s*\d{4}[\s\S]{0,160}?Published by [\s\S]{0,90}?\.'
               r'(?:\s*All rights (?:are )?reserved[^.]{0,60}\.)?', re.I),
    # 自家出版、没有「Published by」的变体：`0022-1694/© 2026 Elsevier B.V. All rights are
    # reserved, including those for text and data mining, AI training…`
    re.compile(r'\b\d{4}-\d{3}[\dX]\s*/\s*©\s*\d{4}[\s\S]{0,80}?'
               r'All rights (?:are )?reserved[^.]{0,160}\.', re.I),
    re.compile(r'This is an open access article under the CC[^.]{0,90}?\([^)]{0,120}\)\s*\.?', re.I),
    # 期刊页眉整串：`PHYSICS OF FLUIDS VOLUME 14, NUMBER 11 NOVEMBER 2002`
    re.compile(r'\b[A-Z][A-Z ]{6,40}VOLUME\s+\d+,\s*NUMBER\s+\d+\s+[A-Z]+\s+\d{4}\b'),
    # 首页脚注：通讯作者联系方式。dump 有时会把正文碎片插在脚注中间
    # （见 Example2024），所以标记、地址、电话、邮箱各自独立锚定分开删，
    # 绝不用一条规则从「Corresponding author」一路桥到邮箱——那会连正文一起吞。
    re.compile(r'[*†‡§]?\s*Corresponding author at:[^.]{0,120}\.', re.I),
    re.compile(r'[⋆∗*†‡]+\s*Corresponding author\b\.?', re.I),
    re.compile(r'\bTel\.?\s*:?\s*\+?[\d ()+-]{6,25};?'
               r'(?:\s*fax\.?\s*:?\s*\+?[\d ()+-]{6,25})?', re.I),
    re.compile(r'E-?mail address(?:es)?:\s*[^\s()]+@[^\s()]+(?:\s*\([^)]{0,60}\))?'
               r'(?:\s*,?\s*[^\s()]+@[^\s()]+(?:\s*\([^)]{0,60}\))?)*', re.I),
    # arXiv 预印本页脚：`Preprint submitted to Elsevier arXiv:2209.10411v2 [cs.CE] 22 Nov 2022`
    re.compile(r'Preprint submitted to [A-Z][\w .&-]{0,40}?(?=\s*(?:arXiv:|$))'),
    re.compile(r'arXiv:\d{4}\.\d{4,5}(?:v\d+)?\s*\[[a-zA-Z.\-]+\]\s*'
               r'\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}'),
]


def scrub_furniture(text: str) -> str:
    for pat in SCRUB:
        text = pat.sub(' ', text)
    # 脚注正文删掉后会剩下孤零零的脚注符和它带出来的空标点
    text = re.sub(r'\s[⋆†‡]+(?=\s|[,.;])', '', text)
    text = re.sub(r'\s+([,.;:])', r'\1', text)
    return re.sub(r'\s{2,}', ' ', text).strip()


STOP_HEAD = re.compile(r'^(?:References|REFERENCES|Bibliography|Literature cited)\.?$', re.I)
FIXED_HEAD = {
    'abstract': 'Abstract', 'a b s t r a c t': 'Abstract',
    'highlights': 'Highlights', 'h i g h l i g h t s': 'Highlights',
    'key points': 'Highlights',
    'keywords': 'Keywords', 'key words': 'Keywords', 'index terms': 'Keywords',
    'nomenclature': 'Nomenclature', 'acknowledgements': 'Acknowledgements',
    'acknowledgments': 'Acknowledgments', 'conclusions': 'Conclusions',
    'conclusion': 'Conclusion', 'introduction': 'Introduction',
    'declaration of competing interest': 'Declaration of competing interest',
    'data availability': 'Data availability', 'summary': 'Summary',
    # 不带编号的常见节名：Elsevier / Particuology 一类期刊整篇都不编号
    'methodology': 'Methodology', 'methods': 'Methods', 'method': 'Method',
    'materials and methods': 'Materials and methods',
    'results': 'Results', 'discussion': 'Discussion',
    'results and discussion': 'Results and discussion',
    'background': 'Background', 'theory': 'Theory',
    'governing equations': 'Governing equations',
    'numerical method': 'Numerical method', 'numerical methods': 'Numerical methods',
    'model description': 'Model description', 'validation': 'Validation',
    'concluding remarks': 'Concluding remarks',
    'conclusions and outlook': 'Conclusions and outlook',
    'author contributions': 'Author contributions', 'funding': 'Funding',
    'conflict of interest': 'Conflict of interest',
}
AFFILIATION = re.compile(
    r'\b(?:Department|School|Faculty|Institute|Institution|Laborator(?:y|ies)|'
    r'Centre|Center|University|College|Hospital|Academy)\b', re.I
)
NUM_HEAD = re.compile(r'^(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+([A-Z][^.]{2,80})$')
# Physics of Fluids 一类期刊用罗马数字编号：I. INTRODUCTION
ROMAN_HEAD = re.compile(r'^([IVX]{1,6})\.\s+([A-Z][^.]{2,80})$')
APP_HEAD = re.compile(r'^(Appendix\s+[A-Z0-9]+\.?)\s*(.{0,70})$')
FIGCAP = re.compile(r'^(?:Fig(?:ure)?\.?\s*\d+|Table\s*\d+)\b', re.I)
TABCAP = re.compile(r'^Table\s*(\d{1,2})\b', re.I)
TAB_BARE = re.compile(r'^Table\s*(\d{1,2})\s*[.:]?\s*$', re.I)
# 独占一行的 `(7)` = 公式号。部分 PDF 字体映射会把括号 dump 成 `ð7Þ`
# （Elsevier/Chemical Engineering Science 常见），语义仍是同一个公式号。
# 编号不都是裸整数：JFM 体例按节编号 `(2.1)`、附录用 `(A.1)`、拆式用 `(5a)`，
# 只认 `\d{1,2}` 会让整篇论文一条都对不上（Example2024 的 24 条公式就是这样全漏的）。
# 上限两位数是刻意的：`(2019)` 这类文献年份不能被当成公式号。
EQ_NUM = re.compile(
    r'^(?:\(\s*([A-Za-z]?\.?\d{1,2}(?:\.\d{1,2})?[a-z]?)\s*\)'
    r'|ð\s*([A-Za-z]?\.?\d{1,2}(?:\.\d{1,2})?[a-z]?)\s*Þ)$'
)
EQ_TAG = re.compile(r'\\tag\{\s*([A-Za-z]?\.?\d{1,2}(?:\.\d{1,2})?[a-z]?)\s*\}')
# 编号右对齐、与公式同处一行：`∇·u = 0                    (5)`。这是 LaTeX `\tag`
# 的默认排版，dump 保留原样时编号就不会独占一行，上面那条一个都对不上
# （Example2024 的 51 条公式因此全漏）。硬要求公式体含运算符：正文句子尾部的
# `(2019)`/`(见 Fig. 3)` 不带运算符，实测全库零误判。
EQ_NUM_TAIL = re.compile(
    r'^(?P<body>.*?[=∑∏∫√≈≤≥×⋅±∇∂].*\S)[ \t]{2,}'
    r'\((?P<num>[A-Za-z]?\.?\d{1,2}(?:\.\d{1,2})?[a-z]?)\)$')
# 抽图命名 `<pid>_page3_fig2.png`；jpeg/webp 同样是真图，只认 png 会漏
IMG_NAME = re.compile(r'_page(\d+)_fig(\d+)\.(?:png|jpe?g|webp|gif)$', re.I)
SENT_END = re.compile(r'[.!?:;”")\]]$')
# 回扫剥公式碎片时的刹车：句子收尾的标点。`)`/`]` 不算——公式碎片经常以它们结尾
EQ_STOP = re.compile(r'[.:;!?]$')
ZERO_WIDTH = re.compile(r'[\u200b\u200c\u200d\ufeff\u00a0]')


def spaced_word(s: str) -> str:
    """`h i g h l i g h t s` 这类逐字母排版还原成词，便于匹配固定节名。

    字母间可能不止一个空格（`A  B  S  T  R  A  C  T`），所以用 \\s+ 而不是 \\s。
    """
    return re.sub(r'\s+', '', s) if re.fullmatch(r'(?:\S\s+){2,}\S', s) else s


def extract_affiliation(pages: list) -> str:
    """Read affiliations only from the title block before Highlights/Abstract.

    The organization keyword is the hard anchor. If the title block is unusual or no
    organization line is present, return an empty string and keep the Luna D TODO.
    """
    if not pages:
        return ''
    title_lines: list[str] = []
    for raw in pages[0][1][:60]:
        s = LIG_RE.sub(lambda m: LIGATURES[m.group(0)], raw.strip())
        key = spaced_word(s).lower().rstrip('.:')
        if key in {'highlights', 'abstract', 'keywords', 'article info', 'article history'}:
            break
        title_lines.append(s)
    hits = [re.sub(r'\s+', ' ', s).strip() for s in title_lines if AFFILIATION.search(s)]
    return '；'.join(dict.fromkeys(hits))


# 结构性标记豁免：归一化会把数字换成 `#`，于是 `(1)`…`(14)`、`Table 1`…`Table 6`
# 全都塌成同一个字符串，公式或表格一多就跨够页数、被当成页眉整批删掉——草稿里连
# 公式和表格在哪都不剩（Example2024 的 14 条公式号与 6 个表标签就是这样一起消失的）。
# 页眉页脚不会长成这几种样子，豁免它们不会放真页眉进来。
KEEP_NORM = re.compile(r'^(?:\([A-Za-z]?\.?#(?:\.#)?[a-z]?\)'
                       r'|ð[A-Za-z]?\.?#(?:\.#)?[a-z]?Þ'
                       r'|(?:Table|Fig(?:ure)?\.?|Eq(?:uation)?\.?|Scheme)\s*#[.:]?)$', re.I)


BARE_NUM = re.compile(r'^(\d{1,2}(?:\.\d{1,2}){0,3})\.?$')
# 标题续行的收尾标点：出现它就不再往下拼
TITLE_STOP = re.compile(r'[.;?!]$')


def _plausible_next_section(prev: str, num: str) -> bool:
    """`num` 是不是 `prev` 之后合理的下一个章节号。

    裸数字行在 dump 里遍地都是——页码、公式号、表格单元格、参考文献序号。
    靠「必须是上一个章节号的合理后继」把它们挡住，比任何长度/字形启发都可靠。
    允许三种走法：同级递增（2→3）、下钻一级（2→2.1）、上浮到某层再递增（2.3.4→2.4 / 3）。
    """
    n = [int(x) for x in num.split('.')]
    if prev is None:
        return len(n) == 1 and n[0] == 1
    p = [int(x) for x in prev.split('.')]
    if len(n) == len(p) + 1:
        return n[:-1] == p and n[-1] == 1
    if len(n) <= len(p):
        k = len(n) - 1
        return n[:k] == p[:k] and n[k] == p[k] + 1
    return False


def page_number_lines(pages: list) -> set:
    """定位印在版面上的页码行，返回 `(页序, 行号)` 集合。

    页码和裸章节号长得一模一样（都是「一行只有一个数字」），但页码有两个章节号
    没有的特征：只出现在整页的第一或最后一个非空行，且**与 dump 页序保持固定偏移**
    （封面算第 1 页时，第 5 页印的就是 5；有前言页时整体差个常数）。
    连续 3 页对得上同一个偏移，就可以判定这一串是页码而不是章节号。
    """
    cand: dict = {}
    for pi, (_pno, lines) in enumerate(pages):
        idxs = [k for k, s in enumerate(lines) if s.strip()]
        if not idxs:
            continue
        for k in {idxs[0], idxs[-1]}:
            m = BARE_NUM.match(lines[k].strip())
            if m and '.' not in m.group(1):
                cand.setdefault(int(m.group(1)) - pi, set()).add((pi, k))
    hit: set = set()
    for _off, pos in cand.items():
        if len(pos) >= 3:
            hit |= pos
    return hit


def _title_boundary(s: str) -> bool:
    """这一行自成一体，不能被上面的裸章节号吸走。

    刻意**不含** `FIXED_HEAD`：`1` + `Introduction` 正是要拼的那种，
    用 `is_break_line` 会把整条章节链的第一环拦掉，后面全部失联。
    `STOP_HEAD` 必须留着——`6` + `References` 一旦拼成 `6 References`，
    收尾检测就认不出参考文献从哪开始，整段文献会被卷进正文。
    """
    return bool(FIGCAP.match(s) or STOP_HEAD.match(s) or NUM_HEAD.match(s)
                or ROMAN_HEAD.match(s) or APP_HEAD.match(s))


def _grab_title(lines: list, i: int, full: float, vocab: Counter):
    """从裸号行 `i` 往下收标题文本，返回 `(标题, 结束行号)`；拼不成返回 `('', i+1)`。"""
    title, j = '', i + 1
    while j < len(lines) and len(title) < 90:
        nxt = lines[j].strip()
        if not nxt or _title_boundary(nxt):
            break
        if not title and not re.match(r'[A-Z]', nxt):
            break                               # 编号后面不是标题词，多半是页码撞上了
        if len(lines[j]) >= full:
            break                               # 满宽行 = 正文，绝不吸收；判断必须在拼接之前
        if title:
            mh = re.search(r'([A-Za-z]{2,})-$', title)
            mn = re.match(r"([A-Za-z][A-Za-z']*)", nxt)
            glue = hyphen_glue(mh.group(1), mn.group(1), vocab,
                               mh.start(1) > 0 and title[mh.start(1) - 1] == '-') \
                if mh and mn else None
            title = (title[:mh.start(1)] + mh.group(1) + glue + nxt
                     if glue is not None else title + ' ' + nxt)
        else:
            title = nxt
        j += 1
        if TITLE_STOP.search(title):
            break
    if title and len(title) <= 90 and not TITLE_STOP.search(title):
        return title, j
    return '', i + 1


def join_split_headings(pages: list, vocab: Counter = None) -> list:
    """把被 dump 拆成两行的章节号与标题接回同一行。

    单栏预印本（arXiv 体例）常把编号单独排一行、标题再按版心宽度折成几段：

        2
        Aerodynamics studies: state-
        of-the-art

    `NUM_HEAD` 要求编号与标题同行，于是这类论文整篇标题一个都认不出来——实测
    Example2024 的 27 个章节只识别出 1 个、Example2024 的 17 个一个都不认。
    章节层级塌了，中文侧就得自己重建一遍，英文侧则永远是一堵没有小标题的文字墙。

    两处判据决定了它准不准：

    - **续行到哪为止看行宽**。dump 按版心宽度硬折，正文行都贴着宽度中位数，标题
      续行明显偏短，撞上接近满宽的行就说明标题结束了。只按「有没有连字符」判会把
      `Stokes' regime: analytical solutions` 这种没断词的多行标题拦腰截断。
    - **取最长的一条章节链**。首页作者的附属机构编号也是 `1` `2` `3` 独占一行、
      后面跟机构名，形状与章节号一模一样；贪心地从头接受就会让 `prev` 停在 `3`，
      正文真正的 `1 Introduction` 反而被判成「不是合理后继」而全链失联。
      章节链几十环、机构链两三环，按最长链取舍就不会认错。
    """
    if vocab is None:
        vocab = build_vocab(s for _n, pg in pages for s in pg)
    widths = sorted(len(s) for _n, pg in pages for s in pg if len(s.strip()) > 20)
    # 满宽阈值取中位数的 0.85：标题末行常有七八成宽，正文行几乎总是压着满宽
    full = widths[len(widths) // 2] * 0.85 if widths else 0
    skip = page_number_lines(pages)

    # 已经拼在一行的章节号也要参与定链：整篇只有个别章节被拆行时，链条得能从它们接上
    seen: list = []
    cand: list = []
    for pi, (_pno, lines) in enumerate(pages):
        for i, ln in enumerate(lines):
            s = ln.strip()
            mh = NUM_HEAD.match(s)
            if mh:
                seen.append((len(cand), mh.group(1)))
                continue
            m = BARE_NUM.match(s)
            if not m or (pi, i) in skip:
                continue
            title, j = _grab_title(lines, i, full, vocab)
            if title:
                cand.append((pi, i, j, m.group(1), title))

    best_len, best_end, dp, par = 0, -1, [0] * len(cand), [-1] * len(cand)
    for k, (_pi, _i, _j, num, _t) in enumerate(cand):
        rooted = _plausible_next_section(None, num) or any(
            p <= k and _plausible_next_section(n, num) for p, n in seen)
        dp[k] = 1 if rooted else 0
        for q in range(k):
            if dp[q] and _plausible_next_section(cand[q][3], num) and dp[q] + 1 > dp[k]:
                dp[k], par[k] = dp[q] + 1, q
        if dp[k] > best_len:
            best_len, best_end = dp[k], k

    chain, k = [], best_end
    while k >= 0:
        chain.append(k)
        k = par[k]
    # 倒序落地：同一页上先改后面的，前面的行号才不会被改乱
    for k in sorted(chain, reverse=True):
        pi, i, j, num, title = cand[k]
        pages[pi][1][i:j] = ['%s %s' % (num, title)]
    return pages


def strip_running(pages: list) -> list:
    """跨页重复出现的短行 = running header/footer，删掉。

    不能只看每页首尾几行：双栏 dump 常把页眉甩到页面中部
    （Example2024 的 `Industrial & Engineering Chemistry Research …` 就夹在正文段落之间）。
    所以整页扫，用「短行 + 跨页高重复」双条件锁定，避免误删正文。
    """
    norm = lambda s: re.sub(r'\d+', '#', s).strip()
    cnt = Counter()
    for _, pg in pages:
        for s in {x.strip() for x in pg if 0 < len(x.strip()) < 120}:
            cnt[norm(s)] += 1
    thresh = max(3, int(len(pages) * 0.3))
    junk = {k for k, v in cnt.items() if v >= thresh and not KEEP_NORM.match(k)}
    return [(n, [s for s in pg if norm(s.strip()) not in junk]) for n, pg in pages]


def is_break_line(s: str) -> bool:
    """标题、图表题、参考文献这类行自成一体，绝不能被上一行的断词吸走。"""
    t = s.strip()
    return bool(FIGCAP.match(t) or STOP_HEAD.match(t) or NUM_HEAD.match(t)
                or ROMAN_HEAD.match(t) or APP_HEAD.match(t)
                or t.lower().rstrip('.:').strip() in FIXED_HEAD)


# 词表判不出时的兜底：这些后缀/前缀构成的复合词，英文里习惯保留连字符
HYPHEN_TAILS = {
    'based', 'scale', 'driven', 'induced', 'dependent', 'independent', 'free',
    'like', 'type', 'wise', 'related', 'specific', 'level', 'oriented', 'aware',
    'guided', 'weighted', 'resolved', 'controlled', 'dominated', 'limited',
    'sized', 'shaped', 'averaged', 'normalized', 'scaled', 'derived', 'assisted',
    'informed', 'constrained', 'invariant', 'wide', 'width', 'term',
}
HYPHEN_HEADS = {
    'non', 'self', 'semi', 'multi', 'cross', 'intra', 'well', 'real', 'high',
    'low', 'large', 'small', 'long', 'short', 'fine', 'coarse', 'state', 'time',
    'space', 'first', 'second', 'third', 'two', 'three', 'four', 'single',
}


def build_vocab(lines) -> Counter:
    vocab = Counter()
    for s in lines:
        for w in re.findall(r"[A-Za-z][A-Za-z\-']+", s):
            vocab[w.lower()] += 1
    return vocab


def hyphen_glue(a: str, b: str, vocab: Counter, compound: bool = False):
    """两个被行末连字符拆开的词该用什么拼回；None 表示这两行根本不该拼。

    正文断词和标题续行是同一件事（`analytical solu-` / `tions` 要拼成 `solutions`，
    `particle-to-` / `fluid` 的连字符却必须留着），所以判据只写这一份，
    `dehyphenate` 和 `join_split_headings` 共用——各写一份迟早走样。

    `compound` = 断点左边那个词本身就挂在连字符后面（`particle-` **`to-`**）。
    词表判不出时这个信号比构词习惯可靠：`particle-to-fluid` 这类多段复合词整体只
    作为一个 token 进词表，`to-fluid` 和 `tofluid` 的词频都是 0，光靠词频会平局，
    然后被兜底规则拆成 `particle-tofluid`。
    """
    if b[:1].islower():
        joined, hyph = (a + b).lower(), (a + '-' + b).lower()
        if vocab[hyph] != vocab[joined]:
            return '-' if vocab[hyph] > vocab[joined] else ''
        # 全文都没完整出现过，词频判不了：按英文构词习惯兜底
        return '-' if (compound or b.lower() in HYPHEN_TAILS
                       or a.lower() in HYPHEN_HEADS) else ''
    # 续词首字母大写的，只有 Newton-Raphson、MI-DELBM 这类真复合词才拼，且连字符要留着
    return '-' if a[:1].isupper() else None


def dehyphenate(lines: list, vocab: Counter = None) -> list:
    """行末软连字符拼回；用全文词表决定保不保留连字符。

    拼出来的新行可能又以连字符收尾（原文连着两行都在断词），所以拼接结果要留在
    队尾继续参与下一行的判断——拼完就定稿会让这种连续断词永远漏网。

    vocab 必须是**全文**词表：逐页统计的话，`depth-guided` 只在别页完整出现过时，
    本页那处断词就会被拼成 `depthguided`。
    """
    if vocab is None:
        vocab = build_vocab(lines)

    out: list = []
    for cur in lines:
        m = re.search(r'([A-Za-z]{2,})-$', out[-1]) if out else None
        m2 = re.match(r"([A-Za-z][A-Za-z']*)", cur.lstrip()) if m else None
        if m and m2 and not is_break_line(cur):
            glue = hyphen_glue(m.group(1), m2.group(1), vocab,
                               m.start(1) > 0 and out[-1][m.start(1) - 1] == '-')
            if glue is not None:
                out[-1] = (out[-1][:m.start(1)] + m.group(1) + glue
                           + m2.group(1) + cur.lstrip()[m2.end():])
                continue
        out.append(cur)
    return out


def join_across_blocks(md: str) -> str:
    """断词正好落在换页处时，逐页跑的 dehyphenate 够不着，成文后再兜一次。

    只认「小写词 + 连字符 + 空行 + 小写字母」：标题、图片、图注都不以小写起头，
    所以不会误并；连字符留不留仍按全文词频决定。
    """
    vocab = Counter()
    for w in re.findall(r"[A-Za-z][A-Za-z\-']+", md):
        vocab[w.lower()] += 1

    def repl(m):
        a, b = m.group(1), m.group(2)
        glue = '-' if vocab[(a + '-' + b).lower()] > vocab[(a + b).lower()] else ''
        return a + glue + b

    return re.sub(r"([a-z]{2,})-\n{2,}([a-z][a-z']*)", repl, md)


# 自采不到时的兜底缩写表；主判据是 collect_acronyms 的文档自证，这里只保底
ACRONYM_FLOOR = {'CFD', 'DEM', 'LBM', 'DNS', 'IBM', 'MRI', 'GPU', 'CPU', 'PCM',
                 'DPVM', 'VOF', 'FVM', 'SDF', 'MFIX', 'RANS', 'LES', 'PIV', 'DKT'}


def collect_acronyms(lines) -> set:
    """从正文里自采缩写：出现在**混合大小写行**里的全大写词。

    全大写标题本身看不出哪个词是缩写——整行都是大写。但同一个 `CFD-DEM` 在正文段落
    里一定还会以全大写夹在小写句子中间，那才是可信证据。所以只把混合大小写的行当
    语料，整行大写的行（版式）一律不采信。

    固定白名单救不了这件事：表里没有的缩写照样会被压成 `Cfd-dem`，而库里每加一个新
    领域就要改一次代码——`build_index.py` 的 METHOD_MAP 已经因为同样的毛病在漏搜了。

    两道过滤压住误采：**至少出现两次**（挡掉图注标签、强调用的一次性大写），以及
    **全文不能再有它的小写写法**——`MODEL` 在图例里大写过一次，正文里却满篇都是
    `model`，那它就是普通词；`CFD` 则从头到尾只有大写形态。少了这条会写出
    `Numerical MODEL Application In Sandpiles`。
    """
    caps, low = Counter(), Counter()
    for s in lines:
        if not re.search(r'[a-z]', s):
            continue
        caps.update(re.findall(r'\b[A-Z][A-Z0-9]{1,7}\b', s))
        low.update(w.lower() for w in re.findall(r"\b[A-Za-z][A-Za-z']+\b", s)
                   if not w.isupper())
    return {w for w, n in caps.items() if n >= 2 and not low[w.lower()]}


def titlecase(s: str, acronyms=()) -> str:
    """期刊把标题排成全大写是版式而非作者措辞，还原成正常大小写。"""
    if not re.search(r'[A-Z]', s) or re.search(r'[a-z]', s):
        return s
    keep = ACRONYM_FLOOR | set(acronyms)
    out = []
    for w in s.split():
        core = w.strip('.,:;()')
        # 连字符/斜杠复合缩写要整体保留：逐段判才认得出 CFD-DEM、DEM/CFD
        parts = [p for p in re.split(r'[-/]', core) if p]
        if parts and all(p.upper() in keep for p in parts):
            out.append(w)
        else:
            out.append(w[:1] + w[1:].lower() if w[:1].isupper() else w.lower())
    r = ' '.join(out)
    return r[:1].upper() + r[1:]


# 块公式两种写法都得认：换行围栏 `$$\n…\n$$` 与单行 `$$… \tag{1}$$`。
# 只认前者时，用单行写法的论文会一条都对拷不上（泥石流那批 155 条公式全落空）。
ZH_EQ = re.compile(r'\$\$(.+?)\$\$', re.S)


def load_equations(zh_article) -> dict:
    """从中文正文取 `$$…\\tag{N}$$`，按公式号建表，供英文草稿对拷。

    公式和表格数字本来就与语言无关：中文正文里已经转好的 LaTeX 直接搬过来，
    比让英文侧对着同一串 dump 散字符再手转一遍便宜一个数量级。
    含中文的公式（如 `\\text{降雨量}`）不搬——那是译者加的，不是原文。
    """
    path = Path(zh_article)
    if not path.is_file():
        return {}
    out: dict = {}
    for m in ZH_EQ.finditer(path.read_text(encoding='utf-8', errors='replace')):
        body = m.group(1).strip()
        tag = EQ_TAG.search(body)
        if tag and not CJK.search(body):
            out[eq_key(tag.group(1))] = body
    return out


def eq_key(raw: str) -> str:
    """公式号归一化：`2.1` / `A.1` / `5a` 各自成键，大小写与空白不影响配对。"""
    return re.sub(r'\s+', '', raw).upper()


def _eq_fragment(text: str) -> bool:
    """这一行像公式碎片，而不像正文句子。"""
    return len(text) <= 120 and len(re.findall(r'[A-Za-z]{3,}', text)) < 6


def take_eq_fragments(para: list, limit: int = 16) -> list:
    """从段尾往回剥公式碎片，剥到引出句为止（原地改 para，返回剥下来的行）。

    引出句几乎总以 `:` 或 `.` 收尾（"…is generated using a standard convolution
    with a reduced number of filters:" / "…as shown in Equation(5)."），拿它当刹车最稳；
    再叠一条「一行超过 5 个英文词就不是公式」兜住没有标点的情况。
    """
    i = len(para)
    while i > 0 and len(para) - i < limit:
        t = para[i - 1].strip()
        if not t:
            i -= 1
            continue
        if EQ_STOP.search(t) or not _eq_fragment(t):
            break
        i -= 1
    frags = [x.strip() for x in para[i:] if x.strip()]
    del para[i:]
    return frags


# 公式碎片几乎总带等号或大运算符；拿它当「这段是公式不是正文」的硬条件
MATHY = re.compile(r'[=∑∏∫√≈≤≥×⋅±]')


def _frag_line(t: str) -> bool:
    """整行是公式碎片：要么带等号/大运算符，要么根本没有成词的字母（`] ) )` 这种符号汤）。"""
    return _eq_fragment(t) and bool(MATHY.search(t) or not re.search(r'[A-Za-z]{3,}', t))


def _split_math_tail(t: str):
    """段尾粘着一截公式soup（`…as shown in Equation(5). xi,j = ⎧ ⎨ ⎩ F Res(Ii)`）就切开。"""
    for m in reversed(list(re.finditer(r'(?<=[.:])\s+', t))):
        head, tail = t[:m.start()], t[m.end():]
        if head and _frag_line(tail):
            return head, tail
    return t, ''


def take_body_fragments(body: list, limit: int = 5) -> list:
    """公式碎片常在公式号到达之前就被刷进了正文，回到 body 尾部把它摘下来。

    碎片多半以 `)` 或 `]` 收尾，又比正文行短，正好同时命中「句末标点 + 短行」这条
    断段规则，于是 `take_eq_fragments` 回扫 para 时那儿已经空了——同一条公式就会
    既留一行乱码、又贴一段 LaTeX。要求带等号/大运算符（或整行无成词字母）才摘，
    正文段落不会被误伤；碎片粘在引出句尾部时只切走尾巴、保留正文。
    """
    out: list = []
    while len(out) < limit:
        i = len(body)
        while i and not body[i - 1].strip():
            i -= 1
        if not i:
            break
        t = body[i - 1].strip()
        # 上一条公式已按 LaTeX 块完整注入时，末行也是 `$$`。它不是 dump 碎片；
        # 继续回剥会把连续公式中的前一条整块删掉（Example2024 式 21/22、23/24）。
        if t == '$$':
            break
        if _frag_line(t):
            del body[i - 1:]
            out.insert(0, t)
            continue
        head, tail = _split_math_tail(t)
        if tail:
            body[i - 1] = head
            out.insert(0, tail)
        break
    if out and body and body[-1].strip():
        body.append('')
    return out


def classify(line: str, acronyms=frozenset()):
    """返回 (kind, payload)：heading / figcap / tabcap / text。

    `acronyms` 只影响全大写标题的还原写法，判断是不是标题跟它无关，所以只在真正
    要落成正文的那处主循环传；封面页与前言的探测调用只看 Abstract/Highlights，不必传。
    """
    s = spaced_word(line.strip())
    key = s.lower().rstrip('.:').strip()
    if key in FIXED_HEAD:
        return 'h2', FIXED_HEAD[key]
    m = APP_HEAD.match(s)
    if m:
        return 'h2', (m.group(1) + ' ' + m.group(2)).strip()
    m = NUM_HEAD.match(s)
    if m and len(s) < 90:
        depth = m.group(1).count('.') + 2
        return ('h%d' % min(depth, 4),
                '%s. %s' % (m.group(1), titlecase(m.group(2).strip(), acronyms)))
    m = ROMAN_HEAD.match(s)
    # "I. Smith" 这种作者名也长这样，所以要求标题是全大写或至少两个词
    if m and len(s) < 90 and (re.search(r'[A-Z]{2,}', m.group(2)) or ' ' in m.group(2).strip()):
        return 'h2', '%s. %s' % (m.group(1), titlecase(m.group(2).strip(), acronyms))
    if TABCAP.match(s):
        return 'tabcap', s
    if FIGCAP.match(s):
        return 'figcap', s
    return 'text', line


INLINE_MARK = re.compile(r'\b(ABSTRACT|A B S T R A C T|HIGHLIGHTS|KEYWORDS)\s*[:：]\s*', re.I)
# Elsevier 首页把单位、`a r t i c l e i n f o`、`a b s t r a c t` 排在同一行，
# 逐字母间隔的节名后面不带冒号。这种字母序列在正文里不会自然出现，可放心切。
SPACED_MARK = re.compile(r'(?<!\S)(a\s+b\s+s\s+t\s+r\s+a\s+c\s+t|h\s+i\s+g\s+h\s+l\s+i\s+g\s+h\s+t\s+s)(?!\S)', re.I)


def split_inline_markers(lines: list) -> list:
    """`* S Supporting Information ABSTRACT: This paper …` 这类把节名压在正文行里的，切开成独立行。"""
    out = []
    for s in lines:
        m = INLINE_MARK.search(s)
        if m and len(s) > len(m.group(0)) + 20:
            out += [re.sub(r'\s+', ' ', m.group(1)).strip(), s[m.end():]]
            continue
        m = SPACED_MARK.search(s)
        if m and len(s) - m.end() > 40:
            out += [s[:m.start()], re.sub(r'\s+', '', m.group(1)), s[m.end():]]
            continue
        out.append(s)
    return out


COVER_MARK = re.compile(
    r'^(?:Citation:|View online:|View Table of Contents:|Published by the |'
    r'Articles you may be interested in|HAL Id:|Submitted on |'
    r'This article is copyrighted|Downloaded from |To cite this version)', re.I)


def drop_cover_page(pages: list) -> list:
    """AIP 的引文页、HAL 的存档页是整页样板，真正的正文从下一页才开始。

    仅当第一页样板行占比过半时才丢，避免误伤正文起始就在第一页的常规排版。
    """
    if len(pages) < 2:
        return pages
    _, first = pages[0]
    body = [s for s in first if s.strip()]
    if body and sum(bool(COVER_MARK.match(s.strip())) for s in body) >= max(2, len(body) * 0.25):
        return pages[1:]
    return pages


BARE_MARK = re.compile(
    r'(?:^|\s)(Abstract|A\s?b\s?s\s?t\s?r\s?a\s?c\s?t|Summary|Synopsis)'
    r'\s*[:.]?\s*(?=[A-Z(])')


def ensure_abstract_marker(pages: list) -> list:
    """摘要标记未独占一行时（`Abstract We present …` / 粘成 `AbstractThe …`）把它切出来。

    不带冒号的裸标记在正文里是常见普通词，所以只在前两页找、只切第一处，
    且已能认出摘要节时完全不动，避免误伤正文。
    """
    for _, pg in pages[:2]:
        for s in pg:
            k, v = classify(s)
            if k == 'h2' and v in ('Abstract', 'Summary', 'Highlights'):
                return pages
    for pi, (pno, pg) in enumerate(pages[:2]):
        for li, s in enumerate(pg):
            m = BARE_MARK.search(s)
            if not m:
                continue
            # 标记独占行首时信号已经足够强（`Abstract In this paper, …`），
            # 不必再要求后面接着一长段——摘要首行常被硬折得很短。
            if m.start() == 0 or len(s) - m.end() > 60:
                new = pg[:li] + [m.group(1).replace(' ', ''), s[m.end():]] + pg[li + 1:]
                return pages[:pi] + [(pno, new)] + pages[pi + 1:]
    return pages


def drop_front_matter(pages: list):
    """题名块由 index 元数据重建，dump 里第一页的题名/作者/单位/投稿信息一律不要。

    从第一个 Highlights / Abstract 节起算。两者都找不到时原样返回并报 False，
    调用方据此在草稿里留 TODO，不静默丢内容。
    """
    for pi, (pno, pg) in enumerate(pages):
        for li, s in enumerate(pg):
            kind, payload = classify(s)
            if kind == 'h2' and payload in ('Highlights', 'Abstract', 'Summary'):
                return [(pno, pg[li:])] + pages[pi + 1:], True
    return pages, False


def real_table_captions(pages: list) -> dict:
    """先通读全文，判定每个表号的**表题行**到底是哪一行。

    为什么要预扫：正文里「…are presented in **Table 5.** The data of NDSI…」被硬折行后
    同样是行首 `Table 5`，只看当前行分不出表题和正文。而期刊排版的真表题几乎总是独占一行
    的裸 `Table 5`。所以规则是：某个表号只要**在全文任何位置**出现过裸标签，就只认裸标签；
    整篇都没有裸标签（有些期刊写成 `Table 1. Caption…`），才退回认第一次出现。

    返回 {表号: 'bare' | 'first'}。
    """
    mode = {}
    for _, pg in pages:
        for s in pg:
            m = TABCAP.match(s.strip())
            if not m:
                continue
            num = int(m.group(1))
            if TAB_BARE.match(s.strip()):
                mode[num] = 'bare'
            else:
                mode.setdefault(num, 'first')
    return mode


def _debris_blob(cells) -> str:
    return ''.join(sorted(ZERO_WIDTH.sub('', c).replace(' ', '').lower() for c in cells))


def reflow(pages: list, pid: str, img_by_page: dict,
           eqs: dict = None, tables: dict = None) -> list:
    """逐页处理：删栏目行 → 拼词 → 认标题 → 接段落 → 图文配对 → 注入表格与公式。"""
    eqs = eqs or {}
    tables = tables or {}
    body, para = [], []
    stats = {'eq_hit': 0, 'eq_miss': [], 'tab_hit': [], 'tab_review': [], 'tab_empty': []}

    def flush():
        if para:
            joined = scrub_furniture(' '.join(x.strip() for x in para if x.strip()))
            if joined:
                body.append(joined)
                body.append('')
            para.clear()

    cap, page_caps = [], []

    def flush_cap():
        """图题不就地落地，先入本页队列——契约要求图注紧跟在图片之后。"""
        if cap:
            page_caps.append('**' + ' '.join(x.strip() for x in cap) + '**')
            cap.clear()

    def flush_page(pno: int) -> None:
        """本页图片按序落地，每张紧跟一条图题；配不上的图题原样留下，不丢内容。

        用 pop 而不是 get：留在 img_by_page 里的就是从未落地的图，由收尾统一兜住。
        """
        flush()
        imgs = img_by_page.pop(pno, [])
        for i, img in enumerate(imgs):
            body.extend(['![[%s|700]]' % img, ''])
            if i < len(page_caps):
                body.extend([page_caps[i], ''])
        for extra in page_caps[len(imgs):]:
            body.extend([extra, ''])
        page_caps.clear()

    tcap: list = []
    tnum = [0]
    debris = {'blob': '', 'left': 0}

    def flush_tcap():
        """表题就地落地，并把抽好的英文原表跟在它后面。

        表题**不能**进 page_caps：那个队列是按顺序配给本页图片的，表题一旦混进去就会
        顶掉真正的图注（2026-08 Example2024 的表 5/表 6 就是这样抢了图 10/图 11 的坑位）。
        """
        if not tcap:
            return
        num = tnum[0]
        body.extend(['**' + ' '.join(x.strip() for x in tcap) + '**', ''])
        tcap.clear()
        tab = tables.get(num)
        if not tab:
            return
        if not tab['markdown']:
            stats['tab_empty'].append(num)
            body.extend(['<!-- TODO 表 %d：版面模型没抽出表体（多半是整张图片式表格，'
                         '或跨页续表），照 PDF 这一页手工补一张 Markdown 表 -->' % num, ''])
            return
        body.extend([tab['markdown'], ''])
        (stats['tab_hit'] if tab['clean'] else stats['tab_review']).append(num)
        if not tab['clean']:
            body.extend(['<!-- TODO 表 %d：版面有合并单元格，抽表脚本拆不准，'
                         '照 PDF 核对行标签（数值已逐格解析、不用重敲） -->' % num, ''])
        debris['blob'] = _debris_blob(tab['cells'])
        debris['left'] = len(tab['cells']) * 3 + 10

    def eat_debris(line: str) -> bool:
        """表格注入之后，dump 里那串一行一个词的表体碎片就是重复内容，吃掉。

        判据是「整行去掉空格后能在本表所有单元格里找到」，配一个行数上限刹车；
        一旦有一行对不上就立刻停手——宁可留几行碎片，也不能顺手吃掉正文。
        """
        if debris['left'] <= 0:
            return False
        key = ZERO_WIDTH.sub('', line).replace(' ', '').lower()
        if not key:
            return True
        if len(key) <= 40 and key in debris['blob']:
            debris['left'] -= 1
            return True
        debris['left'] = 0
        return False

    lengths = [len(s) for _, pg in pages for s in pg if len(s) > 20]
    full = sorted(lengths)[len(lengths) // 2] if lengths else 70

    cap_mode = real_table_captions(pages)
    seen_tab: set = set()
    stopped = False
    vocab = build_vocab(s for _, pg in pages for s in pg)
    acronyms = collect_acronyms(s for _, pg in pages for s in pg)
    for pno, pg in pages:
        pg = [s for s in pg if s.strip() and not FURNITURE.match(s.strip())]
        pg = dehyphenate(pg, vocab)
        for si, s in enumerate(pg):
            if not s.strip():
                continue
            if STOP_HEAD.match(s.strip()):
                flush_cap()
                flush_tcap()
                flush()
                body += [c for cc in page_caps for c in (cc, '')]
                page_caps.clear()
                stopped = True
                break
            if debris['left'] > 0 and not tcap and eat_debris(s):
                continue
            m = EQ_NUM.match(s.strip())
            tail = None if m else EQ_NUM_TAIL.match(s.rstrip())
            if tail and not cap and not tcap:
                # 公式号右对齐、跟公式同一行（Example2024 的 51 条全是这样）。
                # 把公式体先塞回段尾，下面的 take_eq_fragments 就能照常剥它。
                para.append(tail.group('body'))
            if (m or tail) and not cap and not tcap:
                num = eq_key(m.group(1) or m.group(2) if m else tail.group('num'))
                frags = take_eq_fragments(para)
                flush()
                frags = take_body_fragments(body) + frags
                if num in eqs:
                    body.extend(['$$', eqs[num], '$$', ''])
                    stats['eq_hit'] += 1
                else:
                    stats['eq_miss'].append(num)
                    body.append('<!-- TODO 式 (%s)：dump 里是散字符，中文正文也没有可对拷的'
                                ' LaTeX，需照 PDF 这一页转写 -->' % num)
                    body.extend([' '.join(frags), ''] if frags else [''])
                continue
            kind, payload = classify(s, acronyms)
            if kind.startswith('h'):
                flush_cap()
                flush_tcap()
                flush()
                body += ['#' * int(kind[1]) + ' ' + payload, '']
            elif kind == 'tabcap' and _is_table_label(
                    s, pg[si + 1] if si + 1 < len(pg) else '', cap_mode, seen_tab, tables):
                flush_cap()
                flush_tcap()
                flush()
                tnum[0] = int(TABCAP.match(s.strip()).group(1))
                seen_tab.add(tnum[0])
                tcap.append(payload)
                if TAB_BARE.match(s.strip()) is None and SENT_END.search(s.strip()):
                    flush_tcap()
            elif tcap:
                tcap.append(s)                      # 表题也常被折成两三行
                if SENT_END.search(s.strip()):
                    flush_tcap()
            elif kind == 'figcap':
                flush_cap()
                flush()
                cap.append(payload)
            elif cap:
                # 图题常被硬折成两三行，接着收，直到句末为止
                cap.append(s)
                if SENT_END.search(s.strip()):
                    flush_cap()
            else:
                para.append(s)
                if SENT_END.search(s.strip()) and len(s.strip()) < full * 0.75:
                    flush()
        if stopped:
            break
        flush_cap()
        flush_tcap()
        flush_page(pno)
    if not stopped:
        flush_cap()
        flush_tcap()
        flush()
        body += [c for cc in page_caps for c in (cc, '')]

    # 页号对不上的图（dump 缺页标记、该页被题名页裁掉、或落在参考文献之后）
    # 一张都不能丢：先兜到文末，位置留给人工挪。
    orphans = [name for _pno, names in sorted(img_by_page.items()) for name in names]
    if orphans:
        body += ['', '## Unplaced figures', '',
                 '<!-- TODO 以下 %d 张图按页号找不到落点（dump 缺 Page 标记，或该页被'
                 '题名页/参考文献截断），暂列文末：需人工挪回正文对应位置并补图注 -->' % len(orphans), '']
        for name in orphans:
            body += ['![[%s|700]]' % name, '']
    placed = set(stats['tab_hit']) | set(stats['tab_review']) | set(stats['tab_empty'])
    missed = sorted(num for num in set(tables) - placed if tables[num]['markdown'])
    if missed:
        body += ['', '## Unplaced tables', '',
                 '<!-- TODO 以下 %d 张表在正文里没找到表题落点（dump 的表题被裁掉或写法特殊），'
                 '暂列文末：需人工挪回正文对应位置 -->' % len(missed), '']
        for num in missed:
            body += ['**Table %d.** %s' % (num, tables[num]['caption']), '',
                     tables[num]['markdown'], '']
    stats['tab_unplaced'] = missed
    return body, stats


def _cap_key(s: str) -> str:
    return re.sub(r'[^a-z0-9]', '', ZERO_WIDTH.sub('', s).lower())


def _is_table_label(line: str, nxt: str, cap_mode: dict, seen: set, tables: dict) -> bool:
    """这一行是表题，还是正文里被折行折到行首的「…summarized in Table 6.」？

    光看「是不是裸标签」不够：正文句尾的 `Table 6.` 被硬折行后**也**独占一行，与真表题
    长得一模一样（Example2024 就因此把表 6 注入了两次）。真正能分开两者的是
    `tables.md` 里版面模型解析出的题注——真表题行自带题注开头，或下一行就是题注开头。
    没有权威题注时（没抽到表）才退回原来的裸标签启发式。
    """
    t = line.strip()
    m = TABCAP.match(t)
    num = int(m.group(1))
    if num in seen:
        return False                                # 一个表号只落位一次
    caption = _cap_key((tables.get(num) or {}).get('caption', ''))
    if caption:
        tail = _cap_key(t[m.end():])
        if tail:
            return len(tail) >= 6 and tail[:24] in caption
        # 版面抽表偶尔把表题前一段正文一起并进 caption；真实题注仍会出现在
        # caption 尾部，所以不能只比 caption 的开头（Example2024 Table 3）。
        nxt_key = _cap_key(nxt)
        return len(nxt_key) >= 6 and nxt_key[:24] in caption
    if cap_mode.get(num) == 'bare':
        return bool(TAB_BARE.match(t))
    return True


def build(pid: str, txt_path: Path, idx_path: Path, img_dir: Path,
          eqs: dict = None, tables: dict = None) -> tuple:
    eqs, tables = eqs or {}, tables or {}
    text = txt_path.read_text(encoding='utf-8', errors='replace')
    # 先还原被抽成谚文字形的数学字母（`휌` → `ρ`）：后面的水印清洗、公式碎片判定、
    # 表体吃碎片都在做字符级匹配，带着乱码跑等于拿错字符去比对
    text, glyph_fixed = restore_math_glyphs(text)
    # 行尾软连字符先升格成真连字符，dehyphenate 才看得见这是断词；
    # 直接连同行内的一起删掉，"indi<shy>\ncator" 会被后面的接段逻辑拼成 "indi cator"
    text = re.sub('\u00ad(?=[ \t]*\n)', '-', text)
    text = LIG_RE.sub(lambda m: LIGATURES[m.group(0)], text)
    # dump 里偶尔混进裸 $$：本脚本自己不产块公式，留着只会把前端的数学块撑坏
    text, stray_math = re.subn(r'\$\$', '', text)
    pages, cur, pno = [], [], 1
    for ln in text.split('\n'):
        m = PAGE.match(ln.strip())
        if m:
            pages.append((pno, cur))
            pno, cur = int(m.group(1)), []
        else:
            cur.append(ln.rstrip())
    pages.append((pno, cur))
    pages = [(n, p) for n, p in pages if any(x.strip() for x in p)]
    # 必须排在 strip_running 之前：strip_running 归一化时把数字一律换成 `#`，于是页码、
    # 公式号、章节号全塌成同一个字符串，跨页一超阈值就被整批当页眉删光——Example2024
    # 的 132 个裸数字行会被删到 0，章节号一个不剩，拼标题这步就永远没有原料。
    # 页码不靠 strip_running 兜底，join_split_headings 内部用 page_number_lines 精确剔除。
    pages = join_split_headings(pages)
    pages = strip_running(pages)
    affiliation = extract_affiliation(pages)

    meta = idx_path.read_text(encoding='utf-8') if idx_path.exists() else ''
    grab = lambda k: (re.search(r'^-\s+\*\*%s\*\*[:：](.+)$' % k, meta, re.M) or [None, ''])[1].strip() \
        if re.search(r'^-\s+\*\*%s\*\*[:：](.+)$' % k, meta, re.M) else ''
    title = html.unescape(grab('原题') or pid)
    authors = html.unescape(grab('作者').replace('、', ', '))
    journal = html.unescape(grab('期刊').replace('，', ', ').replace('：', ': '))
    doi = (re.search(r'^doi\s*:\s*"?(.+?)"?\s*$', meta, re.M) or [None, ''])[1] \
        if re.search(r'^doi\s*:\s*"?(.+?)"?\s*$', meta, re.M) else ''

    # 首页刊头里孤零零的期刊名：strip_running 只认跨页重复的页眉，管不到它，
    # 留着会跟下一段接成 "Journal of Hydrology 0022-1694/© 2026 …" 缝进正文
    masthead = re.split(r'\s+\d', journal)[0].strip(' .,').lower() if journal else ''
    if masthead:
        pages = [(n, [s for s in pg if s.strip().rstrip('.').lower() != masthead])
                 for n, pg in pages]
    pages = drop_cover_page(pages)
    pages = [(n, split_inline_markers(p)) for n, p in pages]
    pages = ensure_abstract_marker(pages)
    pages, front_ok = drop_front_matter(pages)

    # 按 (页号, 图号) 数值排序：字典序会把 fig10 排到 fig2 前面，同页多图就会串位
    img_by_page = {}
    if img_dir.is_dir():
        found = []
        for f in img_dir.iterdir():
            m = IMG_NAME.search(f.name)
            if m:
                found.append((int(m.group(1)), int(m.group(2)), f.name))
        for page, _fig, name in sorted(found):
            img_by_page.setdefault(page, []).append(name)

    head = [
        '---', 'noteType: article', 'paper: "[[%s]]"' % pid,
        'tags:', '  - p2o/sub', '---',
        '> 返回索引：[[%s]]' % pid, '',
        '# ' + title, '',
        '**%s**' % authors if authors else '<!-- TODO 作者行 -->', '',
        affiliation or ('<!-- TODO 单位行：回 content/%s.txt 第 1 页摘英文原文单位，'
                        '字母前缀保留 -->' % pid), '',
        '*%s%s*' % (journal, '. DOI: ' + doi if doi else '') if journal else '<!-- TODO 期刊行 -->', '',
    ]
    if not front_ok:
        head += ['<!-- TODO 未识别到 Highlights/Abstract 节，正文开头可能混入题名页残留，需人工裁剪 -->', '']
    if stray_math:
        head += ['<!-- TODO dump 里有 %d 处裸块公式定界符已删；该处公式仍是纯文本，需人工转 LaTeX -->'
                 % stray_math, '']
    body, stats = reflow(pages, pid, img_by_page, eqs, tables)
    out = '\n'.join(head + body)
    out = join_across_blocks(re.sub(r'\n{3,}', '\n\n', out).rstrip() + '\n')
    # 兜底再洗一遍：注入的表格、对拷来的公式、index 里的题名都绕过了上面那道
    # dump 清洗，任何一处带乱码都会直接进英文正文（Example2024 的表体就漏过一次）
    out, tail_fixed = restore_math_glyphs(out)
    stats['glyph_fixed'] = glyph_fixed + tail_fixed
    return out, stats


def _is_placeholder_en(path):
    """骨架刚建出来的 .正文.en.md 只有 frontmatter + H1 + 一段「待子代理填充」引用块。
    这种空壳不算「已有英文正文」，否则新论文首次入库永远跑不出草稿。"""
    try:
        txt = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return False
    body = re.search(r'<!--ARTICLE_EN-->(.*?)<!--/ARTICLE_EN-->', txt, re.S)
    body = body.group(1) if body else txt
    real = [ln for ln in body.splitlines()
            if ln.strip() and not ln.lstrip().startswith('>')]
    return not real


def _is_stale_machine_en(zh_path, en_path):
    """旧版流水线留下的陈旧机器稿：中文侧有一批带号 LaTeX，英文侧一条块公式都没有。

    `_is_placeholder_en` 只分得清「空骨架」和「非空」，于是公式对拷成熟之前生成的
    英文正文被防覆盖闸永久锁死——脚本修好了也修不进去（2026-09-01 全库 42 篇就是
    这么烂着的）。这道闸本意是护住人工校订版，而**人工校订过的稿不可能一条公式都
    没有**，所以「中文一堆带号 LaTeX + 英文零块公式」足以把陈旧机器稿单独拣出来。

    判据与 lint_cluster 的验收规则同源：那边报错误、这边据此放行返工，
    不会出现「lint 说坏了、脚本却拒绝重生成」的死锁。
    """
    try:
        zh = Path(zh_path).read_text(encoding='utf-8', errors='replace')
        en = Path(en_path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return False
    return eq_transplant_lost(zh, en)[2]


def _backup_before_overwrite(target: Path) -> None:
    """覆盖既有英文正文前留一份带时间戳的副本，口径同 fix_article。"""
    backup_dir = Path(tempfile.gettempdir()) / 'prep_article_en_backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M%S')
    shutil.copy2(target, backup_dir / ('%s.%s.bak' % (target.name, stamp)))


def promotion_eligible(todo_count: int, lint_returncode: int) -> bool:
    """Only a warning-free, TODO-free deterministic draft may bypass Luna D."""
    return todo_count == 0 and lint_returncode == 0


def heading_count(text: str) -> int:
    """正文里的章节标题数（不含 References 之后）。晋级门槛与门禁用同一个口径。"""
    return len(re.findall(r'^#{2,6}\s+\S',
                          re.split(r'^##\s+References', text, flags=re.M)[0], re.M))


def rework_promotion_eligible(draft: str, incumbent: str, lint_returncode: int) -> bool:
    """返工存量英文正文的晋级门槛：草稿必须**严格更好**，而不是必须完美。

    首次入库时草稿的对照物是空骨架，「零 TODO + 零警告」这条严门槛当然对——差一点
    就宁可空着等 D 档。返工时对照物完全不同：库里躺着的是一篇公式全丢、留着 dump
    散字符冒充公式的坏正文。对它沿用同一条门槛，等于「宁可留着坏的」——2026-09-01
    实测 42 篇待返工里只放行了 4 篇，其余 38 篇继续烂着，门禁反而在保护故障。

    「更好」看两个维度，**任一项真的变多、另一项都不许变少**：

    - **块公式**——公式对拷失效那一轮的判据；
    - **章节标题**——「先英后中」新流程的核心产物。只看公式会把标题恢复这类改进整个
      漏掉：Example2024 的公式数 39 条前后一样、标题却从 8 个变成 23 个，
      最长一段无标题正文从 66283 字缩到 14860 字，按旧口径反而不给放行。

    另外错映射字形不得增加。TODO 允许保留——它们是 HTML 注释、读者看不见，
    本来就是留给 D 档的工单标记。
    """
    if lint_returncode != 0:
        return False
    if len(LOST_PLANE1_RE.findall(draft)) > len(LOST_PLANE1_RE.findall(incumbent)):
        return False
    d_eq, i_eq = len(EQ_BLOCK_RE.findall(draft)), len(EQ_BLOCK_RE.findall(incumbent))
    d_hd, i_hd = heading_count(draft), heading_count(incumbent)
    if d_eq < i_eq or d_hd < i_hd:
        return False
    return d_eq > i_eq or d_hd > i_hd


def strict_lint(draft_dir: Path, pid: str, vault: Path, wenshu: Path,
                fail_on_warnings: bool = True) -> int:
    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / 'lint_en_draft.py'),
            '--vault', str(vault),
            '--wenshu', str(wenshu),
            '--draft-dir', str(draft_dir),
            '--only', pid,
        ] + (['--fail-on-warnings'] if fail_on_warnings else []),
        check=False,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    )
    if proc.stdout:
        sys.stderr.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    return proc.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vault', default='vault')
    ap.add_argument('--out', default='_work/en-draft')
    ap.add_argument('--only')
    ap.add_argument('--limit', type=int)
    ap.add_argument('--redo-list', help='清单里的 pid 即便库内已有英文正文也重新生成草稿；'
                                        '脚本改进后重跑本机产草稿用，人工稿不在清单里就不会被碰。'
                                        '陈旧机器稿（中文有带号 LaTeX、英文零块公式）无需列进来，'
                                        '会被自动认出并允许返工')
    ap.add_argument('--no-transplant', action='store_true',
                    help='关掉中英产物对拷（不注入 tables.md 的表、不搬中文正文的公式）')
    ap.add_argument('--promote-clean', action='store_true',
                    help='零 TODO 且严格草稿质检零错误/零警告时，直接替换集群里的英文占位骨架；'
                         '已有人工英文正文永不覆盖')
    ap.add_argument('--wenshu', default=None,
                    help='文枢根目录；--promote-clean 的严格草稿质检使用')
    args = ap.parse_args()

    papers = Path(args.vault) / 'Papers'
    arts = {f.name[:-len('.正文.md')]: f for f in papers.rglob('*.正文.md')}
    en_files = {f.name[:-len('.正文.en.md')]: f for f in papers.rglob('*.正文.en.md')}
    # 「已有英文正文、不必重生成」的集合。空骨架与陈旧机器稿都不算数：
    # 前者是待填的壳，后者是脚本改好前留下的残次品，两者都必须允许覆盖返工。
    ens = {pid for pid, f in en_files.items()
           if not _is_placeholder_en(f)
           and not (pid in arts and _is_stale_machine_en(arts[pid], f))}
    redo_set: set = set()
    if args.redo_list:
        redo_set = {x.lstrip('\ufeff').strip() for x in
                    Path(args.redo_list).read_text(encoding='utf-8').splitlines() if x.strip()}
        unknown = redo_set - set(en_files)
        if unknown:
            sys.exit('redo 清单里有 %d 个 pid 库内没有英文正文，先核对：%s'
                     % (len(unknown), '、'.join(sorted(unknown)[:3])))
        ens -= redo_set
    idx = {}
    for p in papers.rglob('*.md'):
        if p.parent.name != 'content' and 'images' not in p.parts:
            idx[p.stem] = p

    todo = []
    for pid in sorted(set(arts) - ens):
        tf = arts[pid].parent / (pid + '.txt')
        if not tf.exists():
            continue
        t = tf.read_text(encoding='utf-8', errors='replace')
        if len(CJK.findall(t)) / max(len(t), 1) > 0.05:
            continue                                  # 中文源，按流水线规则不建 en 文件
        todo.append(pid)
    if args.only:
        todo = [p for p in todo if p == args.only]
    if args.limit:
        todo = todo[:args.limit]

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    cfg_path = Path(__file__).resolve().parent.parent / 'config.json'
    cfg = load_skill_config(cfg_path)
    wenshu = Path(args.wenshu or cfg.get('wenshu') or 'wenshu-pro')
    for pid in todo:
        cdir = arts[pid].parent
        eqs, tables = {}, {}
        if not args.no_transplant:
            eqs = load_equations(arts[pid])
            tables = load_tables(cdir / (pid + '.tables.md'))
        md, stats = build(pid, cdir / (pid + '.txt'), idx.get(pid, Path('nul')),
                          cdir.parent / 'images', eqs, tables)
        draft_path = outdir / (pid + '.正文.en.md')
        draft_path.write_text(md, encoding='utf-8')
        note = []
        if stats['eq_hit'] or stats['eq_miss']:
            note.append('式 %d 对拷 / %d 待转' % (stats['eq_hit'], len(stats['eq_miss'])))
        if tables:
            note.append('表 %d 注入 / %d 待核 / %d 无表体 / %d 未落位'
                        % (len(stats['tab_hit']), len(stats['tab_review']),
                           len(stats['tab_empty']), len(stats['tab_unplaced'])))
        if stats.get('glyph_fixed'):
            note.append('字形还原 %d' % stats['glyph_fixed'])
        if args.promote_clean:
            todo_count = md.count('<!-- TODO')
            lint_rc = strict_lint(outdir, pid, Path(args.vault), wenshu)
            target = en_files.get(pid)
            # 陈旧机器稿自动认出；redo 清单是人工点名要重做的，同样按返工口径处置——
            # 否则「脚本改好了、稿子也确实更好」还是会被首入库那条严门槛挡在外面
            stale = bool(target and (_is_stale_machine_en(arts[pid], target)
                                     or pid in redo_set))
            if stale:
                # 返工走「严格更好」门槛：对照物是坏正文，不是空骨架
                err_rc = strict_lint(outdir, pid, Path(args.vault), wenshu,
                                     fail_on_warnings=False)
                incumbent = target.read_text(encoding='utf-8', errors='replace')
                if rework_promotion_eligible(md, incumbent, err_rc):
                    _backup_before_overwrite(target)
                    shutil.copyfile(draft_path, target)
                    note.append('返工入库（严格更好；TODO %d 留给 D 档）' % todo_count)
                else:
                    note.append('未返工：strict-lint 硬错误 exit %d，派 D 档修补' % err_rc)
            elif promotion_eligible(todo_count, lint_rc) and target and _is_placeholder_en(target):
                shutil.copyfile(draft_path, target)
                note.append('严格晋级入库')
            elif promotion_eligible(todo_count, lint_rc) and target:
                note.append('未晋级：已有人工英文正文')
            else:
                note.append('未晋级：TODO %d / strict-lint exit %d，派 D 档修补'
                            % (todo_count, lint_rc))
        print('%-46s %6d 字符  %s' % (pid[:46], len(md), '，'.join(note)))
    print('共生成 %d 篇草稿 → %s' % (len(todo), outdir))


if __name__ == '__main__':
    main()
