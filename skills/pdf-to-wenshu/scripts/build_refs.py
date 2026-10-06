#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_refs.py —— 给 <pid>.正文.md 生成「## 参考文献」章节（确定性脚本，零 token，可回填存量）。

做什么：
1. 从 content/<pid>.txt 全文缓存里提取原文 References 段，解析成条目
   （支持 [N] 序号体裁 与 author-year 体裁；自动剔除页码/页眉页脚/混入的图表题注）。
2. 每条挂超链接：条目里印了 DOI → 直接 https://doi.org/…；
   没印 → 调 Crossref API 反查 DOI（带严格校验：年份/一作/卷页/标题重合度，宁缺勿滥）。
3. 库内互链：条目与 90_系统/_文献库.bib + 各 index 的 citekey/doi 匹配，
   已入库论文追加 📥 [[pid]] 双链（引用边接入关系图）。
4. 章节写进 正文.md 末尾，包在 <!--REFS_AUTO--> 标记里（strip_markers 白名单外，不会被误删）；
   重跑按标记替换=幂等。写前自动备份原文件到系统临时目录。
5. --inline（仅 [N] 体裁）：把正文里的 [N]/[N,M] 引用改写为同文件块链接 [[#^ref-N|N]]
   （渲染为可点击裸数字），点击跳到文末对应条目；跳过公式/代码块/表格/wikilink 内部。
   ⚠️ 严禁在链接外再包方括号伪装 [N] 外观——嵌套括号 Obsidian 解析错乱、点击会新建垃圾笔记。

用法：
  单篇：python build_refs.py --vault "G:/论文知识库" --article "<...>.正文.md" [--inline]
  全库：python build_refs.py --vault "G:/论文知识库" --all [--inline]
  其他：--no-crossref 断网模式（只用条目里印的 DOI + 缓存）；--dry-run 只打印不写文件；
        --force 已有非自动生成的参考文献章节也强制替换。
  ⚠️ ingest_finish 会对全库跑 --all --no-crossref。若新生成章节的 DOI 链接少于已有
     REFS_AUTO 块，默认跳过（skip-richer），避免把 Crossref 回填刷掉。--force 才覆盖。

Crossref 解析结果缓存在 <vault>/90_系统/_引文DOI缓存.json（可手改纠错：value 填 DOI 或 null）。
"""
import os
import re
import sys
import io
import json
import time
import glob
import shutil
import argparse
import datetime
import urllib.parse

# ---------------- 通用 ----------------

HEAD_PAT = re.compile(
    r'^[ \t]*(?:[■□▪◆•●]\s*)?(?:\d{1,2}[.、]?\s+)?'
    r'(References?|REFERENCES?|R\s?E\s?F\s?E\s?R\s?E\s?N\s?C\s?E\s?S?|'
    r'Bibliography|Literature\s+[Cc]ited|参\s*考\s*文\s*献)'
    r'(?:\s*[（(][A-Za-z ]{3,20}[）)])?[ \t]*[:：]?[ \t]*$', re.M)
# ↑ 容忍的标题变体（实测踩坑）：「参 考 文 献」字间空格（中文刊）、「■REFERENCES」（ACS）、
#   「6. References」（会议/MDPI 编号章节）、「参考文献（References）：」（中文刊装饰）
PAGE_MARK = re.compile(r'^-{2,}\s*(Page\s+\d+|（.*截断.*）)\s*-{2,}$')
# 注意：ASCE/Wiley 老式 DOI 自带括号（10.1061/(ASCE)HY…、10.1002/(SICI)…），
# 字符类不能排除 ()[]，否则截断成 "10.1061/(ASCE" ——所有 ASCE 论文会共享同一个
# 残缺 DOI 被错误合并（引文缺口榜实测翻车）；尾部多余的 )] 由 extract_doi 配平剔除
DOI_PAT = re.compile(r'\b10\.\d{4,9}/[^\s"\'<>）]+')
YEAR_PAT = re.compile(r'\b(18|19|20)\d{2}[a-z]?\b')

# PDF 抽取常见的「组合变音符在前」乱码：H¨olzer → Hölzer
DIACRITIC_FIX = [
    ('¨a', 'ä'), ('¨o', 'ö'), ('¨u', 'ü'), ('¨A', 'Ä'), ('¨O', 'Ö'), ('¨U', 'Ü'),
    ('´e', 'é'), ('´a', 'á'), ('´o', 'ó'), ('´i', 'í'), ('´u', 'ú'), ('´c', 'ć'), ('´n', 'ń'),
    ('`e', 'è'), ('`a', 'à'), ('ˆe', 'ê'), ('ˆo', 'ô'), ('ˆa', 'â'), ('ˆi', 'î'),
    ('˜n', 'ñ'), ('˜a', 'ã'), ('˜o', 'õ'), ('¸c', 'ç'), ('˚a', 'å'),
    ('ˇc', 'č'), ('ˇs', 'š'), ('ˇz', 'ž'), ('ˇr', 'ř'),
]


def fix_diacritics(s):
    for a, b in DIACRITIC_FIX:
        s = s.replace(a, b)
    return s


def norm_tokens(s):
    """内容词表：小写、去非字母数字，长度≥4 且**非纯数字**（用于标题重合度）。
    排纯数字是血泪教训：纯中文标题分词后只剩「2024」这种年份 token，
    一命中重合度就是 1.0，曾把 Example2024(气化炉) 错链到 Example2024(滑坡)。"""
    return [w for w in re.split(r'[^a-z0-9]+', s.lower())
            if len(w) >= 4 and not w.isdigit()]


def containment(cand_title, entry_text):
    """候选标题的内容词，有多大比例出现在条目文本里。"""
    ct = norm_tokens(cand_title)
    if not ct:
        return 0.0
    et = set(norm_tokens(entry_text))
    return sum(1 for w in ct if w in et) / len(ct)


def strip_accents(s):
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn')


# ---------------- 1. 提取 & 解析参考文献段 ----------------

CAPTION_START = re.compile(r'^(Fig(?:ure)?\.?\s*\d|Table\s*\d|Scheme\s*\d|图\s*\d|表\s*\d)')
RUN_HEADER = re.compile(r'.{3,60}/\s*[A-Z][^/]{3,60}\d+\s*\(\d{4}\)\s*\d+([–\-]\d+)?\s*$')
# 无斜杠版页眉："D. Xu et al. Chemical Engineering Science 315 (2025) 121838"
ET_AL_HEADER = re.compile(r"^[A-Z]\.\s*[A-Za-zÀ-ÿ'’\-]+ et al\.?,?\s+[A-Z][\w .&:\-]*\d+\s*\(\d{4}\)\s*[\dA-Za-z]+\s*$")
# 纯作者串页眉："G. Ren, J. Xu, J. Xu et al."（无期刊尾巴的变体）
AUTHOR_RUN = re.compile(r"^(?:[A-Z]\.\s*[A-Za-zÀ-ÿ'’\-]+,?\s+){1,5}et al\.?\s*$")
BOILER = re.compile(r'(journal homepage|www\.elsevier|sciencedirect|contents lists available'
                    r'|creativecommons|all rights reserved|downloaded from'
                    r'|www\.[\w.-]+\.(?:net|org|com)/\d)', re.I)
# ↑ 末项抓 Copernicus 系页脚 "…, 2012 www.nat-hazards-earth-syst-sci.net/12/201/2012/"
# 尾部章节：仅当**独立短行**时才算章节标题——"Glossary of Geology"是书名不是章节，
# 曾把 Example2024 的解析拦腰切断，故 Glossary/Highlights 移出名单
TAIL_SECTION = re.compile(r'^[ \t]*(Appendix\b|Nomenclature\b|Supplementary\b|'
                          r'List of symbols|Notation\b)', re.I)

BRACKET_START = re.compile(r'^\[(\d{1,3})\]\s*')
NUMDOT_START = re.compile(r'^(\d{1,3})\.\s+(?=\S)')
# AIP/PoF 上标式条目："1J. S. Wu, G. M. Faeth, …"（序号直接粘在作者首字母前）
NUMGLUE_START = re.compile(r'^(\d{1,3})(?=[A-ZÀ-Þ])')
# ACS 圆括号序号条目："(1) Sederman, A. J. …"
PAREN_START = re.compile(r'^\((\d{1,3})\)\s+(?=\S)')
# author-year 体裁条目起始：Surname, I. …（姓氏段不含数字）。
# 三个必须处理的排版现实：
# ① 缩写允许「D.」「D,」——有的期刊缩写不带句点（"Gou, D, Shen, Y, 2024"）；
# ② 姓氏允许小写前缀 van/von/de/der…（"van Buijtenen, M.S., …"）；
# ③ 首词黑名单挡机构/地名——AGU 体裁学位论文地址换行后
#    "Univ. of Wash., Seattle, 1977." 会被误认成新条目（Example2024 实测）。
_AY_BLACKLIST = (r'(?!(?:Univ|Univer\w*|Dept|Depart\w*|Inst|Institut\w*|Proc|Press|Acad\w*|'
                 r'Vol|Rep|Bull|Surv|Calif|Wash|Oreg|Amer|Assoc|Soc|Agric|Geol|Ltd|Eds?|In|Ibid)\b)')
AY_START = re.compile(
    r"^(?:(?:van|von|de|del|den|der|da|di|du|la|le|ten|ter|te|el|al)\s+){0,2}"
    + _AY_BLACKLIST +
    r"[A-ZÀ-Þ][A-Za-zÀ-ÿ'’.\- ]{0,34},\s+(?:[A-ZÀ-Þ][.,]|[A-ZÀ-Þ][a-z])")
# 「两条粘成一条」的二次切分点（仅 author-year 用）：
# 年份句号（"…, 1983. Pierson, T.C., …"）或 URL 文件尾（"…hec-18-scour.pdf. Bailey, L.P., …"）
# 后紧跟下一条的作者头
YEAR_DOT = re.compile(r'(?:\b(?:18|19|20)\d{2}[a-z]?|\.pdf|\.html?)\.\s+', re.I)


def split_merged_ay(text, min_len=40):
    """把粘连条目在 年份句号/URL尾 处切开；切出的无年份碎片由调用方并回上一条。"""
    pieces, start = [], 0
    for m in YEAR_DOT.finditer(text):
        if m.end() - start >= min_len and AY_START.match(text[m.end():]):
            pieces.append(text[start:m.end()].strip())
            start = m.end()
    pieces.append(text[start:].strip())
    return [p for p in pieces if p]


# DOI 换行截断修复："10.1016/j. oceaneng.2024.119456" → 去掉断点空格
DOI_WRAP = re.compile(r'(10\.\d{4,9}/[^\s]*[./\-])\s+(?=[a-z0-9])')


def _headingless_tail(txt):
    """PNAS/PRL/老 PoF 等无 References 标题、正文后直接开列的兜底：
    在全文后 55% 里找「编号 1 开头的条目行」，且其后 40 行内 ≥5 行是条目起始。"""
    lines = txt.splitlines()
    start_from = int(len(lines) * 0.45)
    first1 = re.compile(r'^(?:\[1\]\s|1\.\s+\S|1(?=[A-ZÀ-Þ]))')
    any_start = re.compile(r'^(?:\[\d{1,3}\]\s|\d{1,3}\.\s+\S|\d{1,3}(?=[A-ZÀ-Þ]))')
    for i in range(start_from, len(lines)):
        s = lines[i].strip()
        if not first1.match(s):
            continue
        window = [l.strip() for l in lines[i:i + 40]]
        if sum(1 for l in window if any_start.match(l)) >= 5:
            return '\n'.join(lines[i:])
    return None


def locate_refs_segment(txt):
    """返回参考文献段的行列表（已初步清洗）；找不到返回 None。"""
    matches = list(HEAD_PAT.finditer(txt))
    if matches:
        seg = txt[matches[-1].end():]
    else:
        seg = _headingless_tail(txt)
        if seg is None:
            return None
    lines = []
    for raw in seg.splitlines():
        ln = raw.rstrip()
        if PAGE_MARK.match(ln.strip()):
            continue
        lines.append(ln)
    return lines


def clean_and_group(lines):
    """剔噪 + 判体裁 + 分组成条目。返回 (style, [(no, text), ...])。no 从 1 起。"""
    from collections import Counter
    counts = Counter(fix_diacritics(l.strip()) for l in lines if l.strip())
    body = []
    n_entryish = 0
    in_caption = False
    for ln in lines:
        # 变音符纠正必须在模式匹配之前（"H¨olzer" 的 ¨ 会让条目起始正则失配 → 条目被并进上一条）；
        # 中文刊归一化：全角括号 ［1］→[1]、不换行空格 \xa0→空格（否则序号正则全体失配）
        s = fix_diacritics(ln.strip()).replace('［', '[').replace('］', ']').replace('\xa0', ' ').strip()
        if not s:
            in_caption = False
            continue
        if re.fullmatch(r'\d{1,4}', s):          # 纯页码
            continue
        if RUN_HEADER.match(s) or ET_AL_HEADER.match(s) or AUTHOR_RUN.match(s) or BOILER.search(s):
            continue
        is_start = bool(BRACKET_START.match(s) or NUMDOT_START.match(s) or
                        NUMGLUE_START.match(s) or PAREN_START.match(s) or AY_START.match(s))
        # 页眉/页脚在参考文献段每页重复一次 → 同一行出现≥2次且不是条目起始，剔掉
        if counts[s] >= 2 and not is_start and len(s) <= 110:
            continue
        # 尾部章节标题必须是独立短行（长行多半是含 "Appendix"/"Notation" 字样的条目）
        if TAIL_SECTION.match(s) and len(s) <= 40 and n_entryish >= 5:
            break
        if CAPTION_START.match(s) and not BRACKET_START.match(s):
            in_caption = True
            continue
        if in_caption and not is_start:
            continue
        in_caption = False
        if is_start:
            n_entryish += 1
        body.append(s)

    n_bracket = sum(1 for s in body if BRACKET_START.match(s))
    n_numdot = sum(1 for s in body if NUMDOT_START.match(s))
    n_ay = sum(1 for s in body if AY_START.match(s))
    # numdot 的铁证是序号严格递增（1. 2. 3. …）——续行常被 AY 正则误认，
    # 曾把 Example2024 的编号列表误判成 author-year，故递增时 numdot 优先
    def ascending(pat, min_n, first_max=3):
        nums = [int(pat.match(s).group(1)) for s in body if pat.match(s)]
        return (len(nums) >= min_n and nums[0] <= first_max and
                all(b > a for a, b in zip(nums, nums[1:])))
    if n_bracket >= 3:
        style, start_pat = 'bracket', BRACKET_START
    elif ascending(PAREN_START, 3):
        # ACS 圆括号序号（"(1) Sederman, …"）——须递增，防止把正文里的 "(3) 第三点" 当条目
        style, start_pat = 'paren', PAREN_START
    elif ascending(NUMDOT_START, 3):
        style, start_pat = 'numdot', NUMDOT_START
    elif ascending(NUMGLUE_START, 5, first_max=1):
        # AIP 上标粘连式（"1J. S. Wu, …"）：模式宽松，须严格递增且从 1 起才敢认
        style, start_pat = 'numglue', NUMGLUE_START
    elif n_numdot >= 3 and n_numdot > n_ay:
        style, start_pat = 'numdot', NUMDOT_START
    elif n_ay >= 3:
        style, start_pat = 'author-year', AY_START
    else:
        return None, []

    # 「序号在下」子模式（部分中文刊双栏提取：条目文本在前、［N］标签行印在其后）——
    # 标签独占一行且占 bracket 命中的多数时启用，此时标签行是上一条的**终止符**
    label_below = False
    if style == 'bracket':
        only = sum(1 for s in body if BRACKET_START.match(s) and
                   not s[BRACKET_START.match(s).end():].strip())
        label_below = only >= 3 and only * 2 > n_bracket

    entries, cur, cur_no = [], [], None
    auto_no = 0
    for s in body:
        if label_below:
            m = BRACKET_START.match(s)
            if m and not s[m.end():].strip():
                if cur:
                    entries.append((int(m.group(1)), ' '.join(cur)))
                cur = []
            else:
                cur.append(s)
            continue
        m = start_pat.match(s)
        # author-year：上一条还没出现年份 → 本行的 "Surname, I." 是被换行拆散的
        # 作者名单续行，不是新条目（条目几乎必有年份；Example2024 的 Bailey/Wallerand 实测）
        if m and style == 'author-year' and cur and not YEAR_PAT.search(' '.join(cur)):
            m = None
        if m:
            if cur:
                entries.append((cur_no, ' '.join(cur)))
            auto_no += 1
            cur_no = int(m.group(1)) if style in ('bracket', 'numdot', 'numglue', 'paren') else auto_no
            cur = [s[m.end():].strip() if style in ('bracket', 'numdot', 'numglue', 'paren') else s]
        else:
            if cur:
                # 断词连字符：上一行以 - 结尾且本行小写开头 → 直接拼
                if cur[-1].endswith('-') and s[:1].islower():
                    cur[-1] = cur[-1][:-1] + s
                else:
                    cur.append(s)
    if not label_below and cur:
        entries.append((cur_no, ' '.join(cur)))

    out = []
    for no, text in entries:
        text = re.sub(r'[\u200b\u200c\u200d\ufeff\u00ad]', '', text)   # PDF 抽取夹带的零宽字符
        text = fix_diacritics(re.sub(r'\s+', ' ', text).strip())
        text = DOI_WRAP.sub(r'\1', DOI_WRAP.sub(r'\1', text))   # DOI 换行截断，最多修两段
        if len(text) < 15:      # 碎渣
            continue
        # 换行导致的「两条粘一条」：author-year 体裁在年份句号后二次切分
        parts = split_merged_ay(text) if style == 'author-year' else [text]
        for pt in parts:
            # author-year 体裁里没有年份的"条目"多半是误切，并回上一条
            if style == 'author-year' and not YEAR_PAT.search(pt) and out:
                out[-1] = (out[-1][0], out[-1][1] + ' ' + pt)
                continue
            out.append((no, pt))
    if style == 'author-year':          # 切分/并条后重新顺序编号
        out = [(i + 1, t) for i, (_, t) in enumerate(out)]
    return style, out


# ---------------- 2. DOI：条目自带 or Crossref 反查 ----------------

def extract_doi(text):
    m = DOI_PAT.search(text)
    if not m:
        return None
    doi = m.group(0).rstrip('.,;:')
    # 配平剔除粘上的右括号/右方括号（条目文本形如 "(doi:10.xxxx/yyy)"）
    for op, cl in (('(', ')'), ('[', ']')):
        while doi.endswith(cl) and doi.count(op) < doi.count(cl):
            doi = doi[:-1].rstrip('.,;:')
    # 换行截断的半截 DOI（"10.1016/j."、"10.1038/s41561-024-"、"10.1061/(ASCE"）
    # 宁可不要，返回 None 让 Crossref 反查出完整的
    suffix = doi.split('/', 1)[1] if '/' in doi else ''
    if len(suffix) < 4 or not suffix[-1].isalnum() or doi.count('(') > doi.count(')'):
        return None
    return doi


def load_cache(path):
    try:
        return json.load(open(path, encoding='utf-8'))
    except Exception:
        return {}


def save_cache(path, cache):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(cache, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def cache_key(text):
    return re.sub(r'\s+', ' ', text.strip())[:220]


def crossref_resolve(entry_text, session):
    """Crossref 反查 DOI。校验严格，宁缺勿滥。
    返回 (status, doi)：('ok', doi | None)＝查询成功（None=确无可靠匹配，可缓存）；
    ('err', None)＝网络/服务瞬时失败（**不可缓存**，下次重试）。"""
    q = urllib.parse.quote(entry_text[:300])
    url = ('https://api.crossref.org/works?query.bibliographic=%s&rows=3'
           '&select=DOI,title,author,issued,volume,page&mailto=p2o-skill@example.org' % q)
    items = None
    for attempt in (1, 2):
        try:
            r = session.get(url, timeout=20)
            if r.status_code == 200:
                items = r.json().get('message', {}).get('items', [])
                break
            if r.status_code in (429, 500, 502, 503) and attempt == 1:
                time.sleep(2.0)
                continue
            return ('err', None)
        except Exception:
            if attempt == 1:
                time.sleep(1.5)
                continue
            return ('err', None)
    if items is None:
        return ('err', None)

    ym = YEAR_PAT.search(entry_text)
    entry_year = int(ym.group(0)[:4]) if ym else None
    entry_nums = set(re.findall(r'\d+', entry_text))
    entry_lower = strip_accents(entry_text).lower()

    for it in items:
        cand_doi = it.get('DOI')
        if not cand_doi:
            continue
        # 年份（必要条件）
        cy = None
        dp = (it.get('issued') or {}).get('date-parts') or []
        if dp and dp[0]:
            cy = dp[0][0]
        if entry_year and cy and abs(cy - entry_year) > 1:
            continue
        year_exact = bool(entry_year and cy and cy == entry_year)
        # 一作姓氏
        fam = ''
        au = it.get('author') or []
        if au:
            fam = strip_accents(au[0].get('family') or '').lower()
        a_ok = bool(fam) and (fam in entry_lower)
        # 卷 & 首页
        v_ok = bool(it.get('volume')) and it['volume'] in entry_nums
        first_page = (it.get('page') or '').split('-')[0].strip()
        p_ok = bool(first_page) and first_page in entry_nums
        # 标题重合度
        t = containment((it.get('title') or [''])[0], entry_text)

        accept = (
            (t >= 0.75 and a_ok) or
            (t >= 0.60 and a_ok and (v_ok or p_ok)) or
            (a_ok and v_ok and p_ok and year_exact) or          # 老式无标题条目
            (t >= 0.55 and v_ok and p_ok and year_exact)
        )
        if accept:
            return ('ok', cand_doi.lower())
    return ('ok', None)


# ---------------- 3. 库内互链 ----------------

def load_vault_papers(vault):
    """扫 index（noteType: index）：返回 [{pid, doi, citekey}]，并从 bib 补 title/year。"""
    papers = {}
    for p in glob.glob(os.path.join(vault, 'Papers', '**', '*.md'), recursive=True):
        try:
            head = open(p, encoding='utf-8').read(2400)
        except Exception:
            continue
        if 'noteType: index' not in head and 'p2o/paper' not in head:
            continue
        pid = os.path.basename(p)[:-3]
        doi = re.search(r'^doi:\s*"?([^"\n]*)"?', head, re.M)
        ck = re.search(r'^citekey:\s*"?([^"\n]*)"?', head, re.M)
        papers[pid] = {
            'pid': pid,
            'doi': (doi.group(1).strip().lower() if doi else ''),
            'citekey': (ck.group(1).strip() if ck else ''),
            'title': '', 'year': '',
        }
    bib_path = os.path.join(vault, '90_系统', '_文献库.bib')
    if os.path.isfile(bib_path):
        bib = open(bib_path, encoding='utf-8').read()
        by_ck = {p['citekey']: p for p in papers.values() if p['citekey']}
        for m in re.finditer(r'@\w+\{([^,\s]+),(.*?)\n\}', bib, re.S):
            ck, body = m.group(1), m.group(2)
            p = by_ck.get(ck)
            if not p:
                continue
            tm = re.search(r'title\s*=\s*\{(.*?)\}[,\n]', body, re.S)
            ym = re.search(r'year\s*=\s*\{(\d{4})\}', body)
            if tm:
                p['title'] = re.sub(r'\s+', ' ', tm.group(1)).strip()
            if ym:
                p['year'] = ym.group(1)
    return list(papers.values())


def match_vault(entry_text, entry_doi, papers, self_pid):
    """条目 → 已入库论文。DOI 相等最硬；否则 bib 标题重合度 + 年份。
    标题匹配要求标题至少有 3 个英文内容词——纯中文/超短标题只走 DOI
    （否则「同年份」就能凑出 1.0 重合度，把不相干论文错链进来）。"""
    el = entry_text.lower()
    ym = YEAR_PAT.search(entry_text)
    ey = ym.group(0)[:4] if ym else ''
    best = None
    for p in papers:
        if p['pid'] == self_pid:
            continue
        if entry_doi and p['doi'] and entry_doi == p['doi']:
            return p
        if p['title'] and p['year'] and ey == p['year'] and len(norm_tokens(p['title'])) >= 3:
            t = containment(p['title'], el)
            if t >= 0.8 and (best is None or t > best[0]):
                best = (t, p)
    return best[1] if best else None


# ---------------- 4. 组装章节 & 写回 ----------------

REFS_OPEN, REFS_CLOSE = '<!--REFS_AUTO-->', '<!--/REFS_AUTO-->'


def doi_url(doi):
    return 'https://doi.org/' + urllib.parse.quote(doi, safe='/:').replace('(', '%28').replace(')', '%29')


def md_escape(text):
    # 裸 < / > 可能被 Obsidian 当 HTML；条目文本里罕见但要兜住
    return text.replace('<', '&lt;').replace('>', '&gt;')


def build_section(style, rows, stats):
    L = ['## 参考文献', '', REFS_OPEN,
         '> 🤖 由 build_refs.py 自动生成（条目保持原文、不翻译）：共 %d 条，带 DOI 链接 %d 条，📥 库内已入库 %d 篇。'
         % (stats['total'], stats['doi'], stats['vault']), '']
    for r in rows:
        no, text, doi, vp = r['no'], md_escape(r['text']), r['doi'], r['vault']
        head = '**[%d]** ' % no if style in ('bracket', 'numdot', 'numglue', 'paren') else ''
        parts = [head + text]
        if doi:
            parts.append('[🔗 DOI](%s)' % doi_url(doi))
        if vp:
            parts.append('📥 [[%s]]' % vp)
        L.append('- %s ^ref-%d' % (' ｜ '.join(parts), no))
    L.append(REFS_CLOSE)
    return '\n'.join(L)


# 已有参考文献章的标题——必须宽容装饰性写法（如「## 参考文献（REFERENCES）」），
# 否则识别不到 → append 出第二节参考文献（Example2024 实测翻车）
EXIST_HEAD = re.compile(r'^#{1,6}[ \t]*[^\n]{0,40}?(参\s*考\s*文\s*献|References?)[^\n]{0,60}$',
                        re.M | re.I)


def splice(article_text, section, force=False):
    """把 section 放进正文：优先替换旧 REFS_AUTO；其次替换 stub 章节；否则追加文末。
    返回 (新文本, 动作)；动作 in {replace-auto, replace-stub, append, skip-existing, skip-richer}。"""
    if REFS_OPEN in article_text and REFS_CLOSE in article_text:
        i = article_text.index(REFS_OPEN)
        j = article_text.index(REFS_CLOSE) + len(REFS_CLOSE)
        old_block = article_text[i:j]
        if not force and old_block.count('[🔗 DOI]') > section.count('[🔗 DOI]'):
            return article_text, 'skip-richer'
        # 连同我们生成的标题一起换掉（标题在标记上方两行内）
        head_m = None
        for m in EXIST_HEAD.finditer(article_text[:i]):
            head_m = m
        if head_m and article_text[head_m.end():i].strip() == '':
            i = head_m.start()
        return article_text[:i] + section + article_text[j:], 'replace-auto'

    m = None
    for m0 in EXIST_HEAD.finditer(article_text):
        m = m0
    if m:
        seg = article_text[m.end():]
        nxt = re.search(r'^#{1,2}[ \t]', seg, re.M)
        end = m.end() + (nxt.start() if nxt else len(seg))
        old = article_text[m.start():end]
        n_lines = len([l for l in old.splitlines() if l.strip()])
        if n_lines <= 14 or force:
            return article_text[:m.start()] + section + article_text[end:], 'replace-stub'
        return article_text, 'skip-existing'

    return article_text.rstrip() + '\n\n' + section + '\n', 'append'


# ---------------- 5. 行内 [N] → 块链接（仅 bracket 体裁） ----------------

# 紧贴在 [N] 之前、说明这个 N 是公式号而非引用序号的前缀
EQ_PREFIX = re.compile(
    r'(?:式|公式|方程|等式|Eqs?|Eqns?|Equations?)\s*[\.．]?\s*$', re.I)


def linkify_inline(article_text, valid_nos):
    """[N] / [N,M,...] → [[#^ref-N|N]]…（渲染为可点击裸数字）；跳过 代码块/公式/wikilink/已有链接。
    ⚠️ 不许在 wikilink 外再包方括号（如 [[[#^ref-1|1]]]）——嵌套会让 Obsidian 把别名当目标文件，
    点击直接新建一个叫「1」的空笔记（2026-08 实测踩坑）。"""
    # 修复旧版三层括号残留：先还原成纯 [N]，随后按新格式重新链接
    article_text = re.sub(r'\[\[\[#\^ref-(\d+)\|\d+\]\]\]', r'[\1]', article_text)
    # 先把不能碰的区域挖成占位符
    holes = []

    def stash(m):
        holes.append(m.group(0))
        return '\x00%d\x00' % (len(holes) - 1)

    guards = [
        re.compile(r'<!--REFS_AUTO-->.*?<!--/REFS_AUTO-->', re.S),  # 参考文献列表自身不改写（否则序号变自跳转）
        re.compile(r'```.*?```', re.S),        # 代码块
        re.compile(r'^\|.*$', re.M),           # 表格行——改写出的 [[…|N]] 带竖线会崩表，整行跳过
        re.compile(r'\$\$.*?\$\$', re.S),      # 块公式
        re.compile(r'\$[^$\n]+\$'),            # 行内公式
        re.compile(r'!?\[\[[^\]]*\]\]'),       # wikilink / 嵌入
        re.compile(r'\[[^\]]*\]\([^)]*\)'),    # markdown 链接
        re.compile(r'<!--.*?-->', re.S),       # 注释
        re.compile(r'\^ref-\d+'),              # 锚点自身
    ]
    txt = article_text
    for g in guards:
        txt = g.sub(stash, txt)

    # 单号、逗号列表、区间三种混排：[7] / [1,3] / [2-4] / [1,5-8]
    num = r'\d{1,3}(?:\s*[-–—~]\s*\d{1,3})?'
    cite = re.compile(r'\[(%s(?:\s*[,，]\s*%s)*)\]' % (num, num))
    seg_re = re.compile(r'^(\d{1,3})(?:\s*[-–—~]\s*(\d{1,3}))?$')

    def repl(m):
        # 「式[3]」「Eq. [3]」是公式号不是引用记号，链成 ^ref-3 会跳到第 3 篇参考文献。
        # 图/表不拦：「图 1 … [30]」里的 [30] 通常是真引用。
        if EQ_PREFIX.search(m.string[:m.start()]):
            return m.group(0)
        out = []
        for seg in re.split(r'[,，]\s*', m.group(1).replace(' ', '')):
            sm = seg_re.match(seg)
            if not sm:
                return m.group(0)
            a = int(sm.group(1))
            if sm.group(2) is None:
                if a not in valid_nos:
                    return m.group(0)
                out.append('[[#^ref-%d|%d]]' % (a, a))
                continue
            # 区间：只链首尾两端、中间保留连接号，否则 [18-28] 会炸出 11 个芯片。
            # 端点都要在参考文献里，且区间要递增且长度合理，避免误伤页码/年份区间。
            b = int(sm.group(2))
            if not (a < b <= a + 40) or a not in valid_nos or b not in valid_nos:
                return m.group(0)
            out.append('[[#^ref-%d|%d]]–[[#^ref-%d|%d]]' % (a, a, b, b))
        return ','.join(out)

    txt, n_sub = cite.subn(repl, txt)

    def unstash(m):
        return holes[int(m.group(1))]

    # 占位符可能嵌套（如公式先挖走、所在表格行再整行挖走），循环还原到干净为止
    while re.search(r'\x00\d+\x00', txt):
        txt = re.sub(r'\x00(\d+)\x00', unstash, txt)
    return txt, n_sub


# ---------------- 主流程 ----------------

def process_article(article, vault, papers, cache, cache_path,
                    use_crossref=True, inline=False, dry=False, force=False, session=None):
    pid = os.path.basename(article)[:-len('.正文.md')]
    txt_path = os.path.join(os.path.dirname(article), pid + '.txt')
    if not os.path.isfile(txt_path):
        return {'pid': pid, 'ok': False, 'why': '无全文缓存 txt'}

    # 提前探测「已有人工参考文献章」：直接跳过，省掉整套解析+联网（全库回填时省大量时间）
    art_text0 = open(article, encoding='utf-8').read()
    if not force and REFS_OPEN not in art_text0:
        m_head = None
        for m0 in EXIST_HEAD.finditer(art_text0):
            m_head = m0
        if m_head:
            seg = art_text0[m_head.end():]
            nxt = re.search(r'^#{1,2}[ \t]', seg, re.M)
            old = seg[:nxt.start() if nxt else len(seg)]
            if len([l for l in old.splitlines() if l.strip()]) > 14:
                return {'pid': pid, 'ok': True, 'style': '--', 'action': 'skip-existing',
                        'inline_links': 0, 'backup': None,
                        'total': 0, 'doi': 0, 'vault': 0, 'unresolved': []}
    lines = locate_refs_segment(open(txt_path, encoding='utf-8').read())
    if lines is None:
        return {'pid': pid, 'ok': False, 'why': 'txt 里找不到 References 段'}
    style, entries = clean_and_group(lines)
    if not entries:
        return {'pid': pid, 'ok': False, 'why': '解析不出参考文献条目'}

    rows, n_doi, n_vault, n_cr = [], 0, 0, 0
    for no, text in entries:
        doi = extract_doi(text)
        if not doi:
            k = cache_key(text)
            if k in cache:
                doi = cache[k]      # 缓存查询不受 --no-crossref 影响——否则断网重跑会把
                                    # 已解析的 DOI 链接从章节里刷掉（只有联网查询才受门控）
            elif use_crossref:
                status, doi = crossref_resolve(text, session)
                if status == 'ok':      # 瞬时网络失败不缓存，下次重试
                    cache[k] = doi
                    n_cr += 1
                time.sleep(0.15)
        vp = match_vault(text, doi, papers, pid)
        if doi:
            n_doi += 1
        if vp:
            n_vault += 1
        rows.append({'no': no, 'text': text, 'doi': doi, 'vault': vp['pid'] if vp else None})

    stats = {'total': len(rows), 'doi': n_doi, 'vault': n_vault}
    section = build_section(style, rows, stats)

    art_text = open(article, encoding='utf-8').read()
    new_text, action = splice(art_text, section, force=force)
    n_inline = 0
    # 行内跳转对所有数字体裁开启——译文里的引用统一写成 [N]，
    # 不管原文是 [N]/1./1X/(1) 哪种排版，序号身份一致。
    # ⚠️ 不受 action 影响：参考文献列表「已经够好、无需重建」（skip-richer）与「正文里的
    # 引用记号还没链」是两回事。早期版本把两者绑在一起，导致 skip-richer 的论文永远拿不到
    # 行内跳转（2026-08 实测：29 篇共 97 处区间引用因此一直是死文本）。
    if inline and style in ('bracket', 'numdot', 'numglue', 'paren'):
        new_text, n_inline = linkify_inline(new_text, {r['no'] for r in rows})

    backup = None
    if not dry and new_text != art_text:
        bdir = os.path.join(os.environ.get('TEMP', '/tmp'), 'build_refs_backups')
        os.makedirs(bdir, exist_ok=True)
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup = os.path.join(bdir, '%s.正文.md.%s.bak' % (pid, stamp))
        shutil.copy2(article, backup)
        open(article, 'w', encoding='utf-8').write(new_text)
    if n_cr:            # 缓存不属于用户内容，dry-run 也保存（避免重复打 API）
        save_cache(cache_path, cache)

    return {'pid': pid, 'ok': True, 'style': style, 'action': action, 'inline_links': n_inline,
            'backup': backup, **stats,
            'unresolved': [r['no'] for r in rows if not r['doi']]}


def main():
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    ap = argparse.ArgumentParser(description='为正文翻译生成带链接的参考文献章节')
    ap.add_argument('--vault', required=True)
    ap.add_argument('--article', help='单篇 <pid>.正文.md 路径')
    ap.add_argument('--all', action='store_true', help='全库批量')
    ap.add_argument('--inline', action='store_true', help='正文 [N] 改写为跳转链接（仅序号体裁）')
    ap.add_argument('--no-crossref', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()

    session = None
    if not a.no_crossref:
        import requests
        session = requests.Session()
        session.headers['User-Agent'] = 'p2o-build-refs/1.0 (mailto:p2o-skill@example.org)'

    papers = load_vault_papers(a.vault)
    cache_path = os.path.join(a.vault, '90_系统', '_引文DOI缓存.json')
    cache = load_cache(cache_path)

    targets = []
    if a.article:
        targets = [a.article]
    elif a.all:
        targets = sorted(glob.glob(os.path.join(a.vault, 'Papers', '**', '*.正文.md'), recursive=True))
    else:
        ap.error('要么 --article 要么 --all')

    results = []
    for t in targets:
        r = process_article(t, a.vault, papers, cache, cache_path,
                            use_crossref=not a.no_crossref, inline=a.inline,
                            dry=a.dry_run, force=a.force, session=session)
        results.append(r)
        if r['ok']:
            print('✔ %-46s %s %-12s 条目%3d DOI%3d 入库%2d 行内%3d%s'
                  % (r['pid'][:46], r['style'][:2], r['action'], r['total'], r['doi'],
                     r['vault'], r['inline_links'],
                     ('  未解析:' + ','.join(map(str, r['unresolved'][:12]))) if r['unresolved'] else ''))
        else:
            print('✘ %-46s %s' % (r['pid'][:46], r['why']))
    ok = [r for r in results if r['ok']]
    print('—— 共 %d 篇：成功 %d，跳过/失败 %d' % (len(results), len(ok), len(results) - len(ok)))


if __name__ == '__main__':
    main()
