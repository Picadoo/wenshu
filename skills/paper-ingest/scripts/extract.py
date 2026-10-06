#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract.py — 论文 PDF → 工作区（v2「先排版」流程的第 ① 步，纯脚本，不用 AI，不裁图）。

    python extract.py --pdf <file.pdf> --work <workdir> [--no-crossref] [--dpi 100]

产出 <workdir>/：
    meta.json        DOI / 题名 / 作者 / 年份 / 期刊（Crossref 优先，离线回退首页启发式）
    pages/pP.png     每页渲染图（AI 排版、核公式 / 表格 / 单位时看）
    columns.md       按栏切分的干净正文（整幅行 → 左栏 → 右栏；段落已拼、断词已接；行首 [BOLD]/[ITAL]/[CAP]/[TAB]/[MATH]/[small] 提示）
    fulltext.txt     原始纯文本（兜底）
    refs.md          同源参考文献清单（- **[N]** … ^ref-N），供中英文正文末尾直接拼接
    brief.md         给 AI 的任务书：① 排版出 out/en.md + out/layout.json → ② cutfigs.py 按清单裁图 → ③ 翻译 / 笔记 → ④ verify
    stats.json       各步耗时与正则粗数（报告用）
不再产 en.draft.md（结构靠猜的草稿），不在这一步裁图——图注清单由 AI 排版核出后再切（cutfigs.py）。
"""
from __future__ import annotations

import argparse
import io
import json
import math
import re
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout  # noqa: E402
from references import extract_numbered_references  # noqa: E402

# ----------------------------------------------------------------------------- utils

def utf8_stdio() -> None:
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def ascii_name(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^A-Za-z0-9]+", "", text)


def cjk_ratio(text: str) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for ch in letters if "一" <= ch <= "鿿") / len(letters)


def norm_line(line: str) -> str:
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", line.strip().lower()))


# ----------------------------------------------------------------------------- metadata

DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>)\]]+)")


def find_doi(doc: pymupdf.Document) -> str:
    for i in range(min(3, len(doc))):
        text = doc[i].get_text()
        for m in DOI_RE.finditer(text):
            doi = m.group(1).rstrip(".,;")
            # 忽略参考文献里的 DOI：首页正文里第一个通常就是本文
            if not re.search(r"\(\d{4}\)", text[max(0, m.start() - 80): m.start()]):
                return doi
    return ""


def crossref(doi: str, timeout: float = 12.0) -> dict:
    try:
        import requests
    except Exception:
        return {}
    try:
        resp = requests.get(
            f"https://api.crossref.org/works/{doi}",
            headers={"User-Agent": "paper-ingest/1.0 (mailto:markraines280@gmail.com)"},
            timeout=timeout,
        )
        if resp.status_code != 200:
            return {}
        msg = resp.json().get("message", {})
    except Exception:
        return {}
    authors = []
    for a in msg.get("author", []) or []:
        given, family = a.get("given", ""), a.get("family", "")
        authors.append(f"{given} {family}".strip() if given else family)
    year = ""
    for k in ("published-print", "published-online", "issued", "created"):
        parts = (msg.get(k) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            year = str(parts[0][0])
            break
    abstract = re.sub(r"<[^>]+>", " ", msg.get("abstract") or "")
    abstract = re.sub(r"^\s*Abstract\s*", "", " ".join(abstract.split()), flags=re.I)
    return {
        "title": " ".join((msg.get("title") or [""])[0].split()),
        "abstract": abstract,
        "authors": authors,
        "year": year,
        "journal": (msg.get("container-title") or [""])[0],
        "volume": msg.get("volume", ""),
        "issue": msg.get("issue", ""),
        "pages": msg.get("page", ""),
        "publisher": msg.get("publisher", ""),
        "source": "crossref",
    }


def crossref_by_title(title: str, timeout: float = 12.0) -> dict:
    """没有 DOI 时按题名查 Crossref，题名高度相似才采纳。"""
    if not title or len(title) < 15:
        return {}
    try:
        import requests
        resp = requests.get("https://api.crossref.org/works",
                            params={"query.bibliographic": title, "rows": 3},
                            headers={"User-Agent": "paper-ingest/1.0 (mailto:markraines280@gmail.com)"},
                            timeout=timeout)
        items = resp.json().get("message", {}).get("items", []) if resp.status_code == 200 else []
    except Exception:
        return {}
    want = set(re.findall(r"[a-z0-9]{3,}", title.lower()))
    for it in items:
        got = set(re.findall(r"[a-z0-9]{3,}", " ".join(it.get("title") or []).lower()))
        if want and got and len(want & got) / len(want | got) >= 0.75 and it.get("DOI"):
            return crossref(it["DOI"], timeout) | {"doi": it["DOI"]}
    return {}


def title_from_layout(page: pymupdf.Page) -> str:
    """首页字号最大的连续行 = 题名（跳过页面最顶端的刊头）。"""
    spans = []
    top_cut = page.rect.y0 + page.rect.height * 0.07
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                t = span["text"].strip()
                if len(t) > 1 and span["size"] > 0.5 and span["bbox"][1] > top_cut:
                    spans.append((round(span["size"], 1), span["bbox"][1], t))
    if not spans:
        return ""
    sizes = Counter(s[0] for s in spans)
    body = sizes.most_common(1)[0][0]
    big = [s for s in spans if s[0] >= max(body * 1.35, body + 3)]
    if not big:
        return ""
    groups = Counter()
    for s in big:
        groups[s[0]] += len(s[2])
    top = max((sz for sz, n in groups.items() if n >= 8), default=max(big, key=lambda s: s[0])[0])
    lines = [s for s in big if abs(s[0] - top) < 0.6]
    lines.sort(key=lambda s: s[1])
    title = " ".join(l[2] for l in lines)
    return " ".join(title.split())[:300]


def year_guess(doc: pymupdf.Document, doi: str) -> str:
    text = "".join(doc[i].get_text() for i in range(min(2, len(doc))))
    for pat in (r"(?:©|\(c\)|Copyright)[^\n]{0,40}?((?:19|20)\d{2})",
                r"(?:Published|Available online|Accepted)[^\n]{0,60}?((?:19|20)\d{2})",
                r"\b((?:19|20)\d{2})\b[^\n]{0,30}(?:Springer|Elsevier|Wiley|Taylor|MDPI|Frontiers|Copernicus)"):
        m = re.search(pat, text)
        if m:
            return m.group(1)
    m = re.search(r"\b(20\d{2}|19\d{2})\b", doi)
    if m:
        return m.group(1)
    years = re.findall(r"\b(20\d{2})\b", text)
    return max(years) if years else ""


def build_meta(doc: pymupdf.Document, pdf: Path, use_crossref: bool) -> dict:
    doi = find_doi(doc)
    meta = {"doi": doi, "title": "", "authors": [], "year": "", "journal": "",
            "volume": "", "issue": "", "pages": "", "publisher": "", "source": "layout"}
    if doi and use_crossref:
        cr = crossref(doi)
        if cr.get("title"):
            meta.update(cr)
    if not meta["title"]:
        layout_title = title_from_layout(doc[0])
        if use_crossref and layout_title and cjk_ratio(layout_title) < 0.2:
            cr = crossref_by_title(layout_title)
            if cr.get("title"):
                meta.update(cr)
        if not meta["title"]:
            meta["title"] = layout_title or pdf.stem
    if not meta["year"]:
        meta["year"] = year_guess(doc, doi)
    head = "".join(doc[i].get_text() for i in range(min(3, len(doc))))
    meta["lang"] = "zh" if cjk_ratio(head) > 0.2 else "en"
    first = meta["authors"][0] if meta["authors"] else ""
    surname = ascii_name(first.split()[-1]) if first else ""
    meta["key"] = f"{surname or 'Paper'}{meta['year'] or ''}"
    meta["pageCount"] = len(doc)
    meta["pdf"] = str(pdf)
    return meta


# ----------------------------------------------------------------------------- figures

CAPTION_RE = re.compile(r"^\s*(?:\*\*)?\s*(Fig\.?|Figure|FIG\.?|图)\s*(?:\*\*)?\s*([A-Z]?\d{1,3}[a-z]?)\b", re.I)
TABLE_CAP_RE = re.compile(r"^\s*(?:\*\*)?\s*(Table|表)\s*(?:\*\*)?\s*([A-Z]?\d{1,3})\b", re.I)


def union_rects(rects: list[pymupdf.Rect], gap: float = 12.0) -> list[pymupdf.Rect]:
    rects = [pymupdf.Rect(r) for r in rects]
    changed = True
    while changed:
        changed = False
        out: list[pymupdf.Rect] = []
        for r in rects:
            merged = False
            for i, o in enumerate(out):
                grown = pymupdf.Rect(o.x0 - gap, o.y0 - gap, o.x1 + gap, o.y1 + gap)
                if grown.intersects(r):
                    out[i] = o | r
                    merged = True
                    changed = True
                    break
            if not merged:
                out.append(r)
        rects = out
    return rects


def text_coverage(page: pymupdf.Page, rect: pymupdf.Rect, words) -> float:
    area = rect.get_area()
    if area <= 0:
        return 1.0
    covered = 0.0
    for w in words:
        wr = pymupdf.Rect(w[:4])
        if wr.intersects(rect):
            covered += (wr & rect).get_area()
    return covered / area


def page_figures(page: pymupdf.Page, pno: int, min_w: float = 70, min_h: float = 45):
    """返回 (captions, regions)。captions: [(num, rect, text)]; regions: [Rect]。"""
    words = page.get_text("words")
    captions = []
    for rect, raw in layout.text_blocks(page):
        text = layout.despace(" ".join(raw.split()))
        m = CAPTION_RE.match(text)
        if m and len(text) > 8 and not TABLE_CAP_RE.match(text) and not layout.CAPTION_VERB.match(text):
            captions.append((m.group(2), rect, text))
    rects: list[pymupdf.Rect] = []
    for info in page.get_image_info():
        r = pymupdf.Rect(info["bbox"]) & page.rect
        if r.width >= 25 and r.height >= 25:
            rects.append(r)
    try:
        for r in page.cluster_drawings():
            r = pymupdf.Rect(r) & page.rect
            if r.width >= 40 and r.height >= 30:
                rects.append(r)
    except Exception:
        pass
    regions = []
    for r in union_rects(rects):
        if r.width < min_w or r.height < min_h:
            continue
        if r.width > page.rect.width * 0.98 and r.height > page.rect.height * 0.9:
            continue  # 整页背景框
        if text_coverage(page, r, words) > 0.35:
            continue  # 表格 / 文字框
        regions.append(r)
    return captions, regions


def assign_regions(captions, regions, page_rect):
    """每个图注 → 其上方（或紧邻）的图区并集。返回 {num: Rect}, 未配对区域列表。"""
    result: dict[str, pymupdf.Rect] = {}
    unassigned = []
    for r in regions:
        best = None
        best_d = 1e9
        for num, cr, _ in captions:
            overlap = min(r.x1, cr.x1) - max(r.x0, cr.x0)
            if overlap <= -20:
                continue
            if cr.y0 >= r.y1 - 6:          # 图注在图下方（常规）
                d = cr.y0 - r.y1
            elif cr.y1 <= r.y0 + 6:        # 图注在图上方
                d = (r.y0 - cr.y1) + 60    # 罚分：优先下方
            else:
                d = 0.0                    # 图注在图区内部（图区把图注框进去了）
            if d < best_d:
                best_d, best = d, num
        if best is None or best_d > 180:
            unassigned.append(r)
            continue
        result[best] = (result[best] | r) if best in result else pymupdf.Rect(r)
    # 图区若把图注框进去，裁掉图注部分
    for num, cr, _ in captions:
        if num in result and result[num].intersects(cr) and cr.y0 > result[num].y0 + 20:
            result[num].y1 = min(result[num].y1, cr.y0 - 2)
    return result, unassigned


def gap_above_caption(page: pymupdf.Page, cap_rect: pymupdf.Rect) -> pymupdf.Rect | None:
    """图注上方到最近一段正文之间的空当（矢量/文字画的图兜底）。"""
    x0, x1 = cap_rect.x0 - 4, cap_rect.x1 + 4
    top = page.rect.y0 + 36
    for br, raw in layout.text_blocks(page):
        if br.y1 <= cap_rect.y0 - 4 and min(br.x1, x1) - max(br.x0, x0) > 0.4 * cap_rect.width:
            txt = " ".join(raw.split())
            is_para = len(txt) > 80 and br.width > 0.5 * cap_rect.width
            is_other_caption = bool(CAPTION_RE.match(layout.despace(txt)) or TABLE_CAP_RE.match(txt))
            if is_para or is_other_caption:
                top = max(top, br.y1 + 2)
    rect = pymupdf.Rect(x0, top, x1, cap_rect.y0 - 2)
    if rect.height < 50 or rect.width < 60:
        return None
    return rect


# 裁图本身在 cutfigs.py（按 AI 排版出的 layout.json 清单驱动）；上面三个函数是它的零件。


# ----------------------------------------------------------------------------- front block

def front_block(meta: dict, doc: pymupdf.Document, lang: str) -> tuple[str, dict]:
    """题名块 + 从首页找单位行。返回 (markdown, {affiliations:[...]})。"""
    p1 = doc[0].get_text()
    affs = []
    for line in p1.splitlines():
        s = " ".join(line.split())
        if 25 < len(s) < 220 and (len(s.split()) >= 4 or cjk_ratio(s) > 0.3) and re.search(
            r"(University|Institute|Laboratory|School|Department|College|Academy|Cent(er|re)|"
            r"Faculty|大学|研究院|研究所|学院|实验室)", s) and not re.search(
            r"@|http|doi|Society|Published|Elsevier|Springer|Wiley|©|Copyright|Received|Accepted|Journal of", s, re.I):
            s = re.sub(r"^[a-z0-9]{1,2}\s+", "", s)
            if s not in affs:
                affs.append(s)
        if len(affs) >= 8:
            break
    authors = "、".join(meta["authors"]) if lang == "zh" else ", ".join(meta["authors"])
    journal = meta.get("journal", "")
    vol = meta.get("volume", "")
    issue = f"({meta['issue']})" if meta.get("issue") else ""
    pages = f": {meta['pages']}" if meta.get("pages") else ""
    jline = f"*{journal} {meta.get('year','')}, {vol}{issue}{pages}. DOI: {meta['doi']}*" if journal else \
            (f"*DOI: {meta['doi']}*" if meta.get("doi") else "")
    parts = [f"# {meta['title']}", ""]
    if authors:
        parts += [f"**{authors}**", ""]
    for a in affs[:6]:
        parts += [a, ""]
    if jline:
        parts += [jline.replace(" ,", ","), ""]
    return "\n".join(parts), {"affiliations": affs[:6]}


# ----------------------------------------------------------------------------- references

REF_START = re.compile(
    r"^(?:[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+(?:,\s*|\s+)(?:[A-Z]\.?\s*){1,3}|[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+\s+[A-Z]{1,3}[,.]|[一-鿿]{2,4}[，,])"
)


def format_reference(text: str) -> str:
    """Keep source text, formatting a literal DOI as the existing Markdown link."""
    text = re.sub(r"\s+", " ", text).strip()
    match = DOI_RE.search(text)
    if match:
        doi = match.group(1).rstrip(".,;")
        text = re.sub(
            r"\s*(?:https?://(?:dx\.)?doi\.org/|doi:\s*)?"
            + re.escape(match.group(1)) + r"\.?", "", text,
        ).strip()
        text = f"{text} ｜ [🔗 DOI](https://doi.org/{doi})"
    return text


def parse_refs(lines: list[str]) -> list[str]:
    # DOI / URL 被折行：`…/j.apm.2017.10.` + `014` → 接回
    joined: list[str] = []
    for ln in lines:
        if joined and re.match(r"^\d{2,6}\b", ln.strip()) and re.search(r"doi\.org/\S+[./]$|10\.\d{4,9}/\S+[./]$", joined[-1]):
            joined[-1] = joined[-1].rstrip() + ln.strip()
        else:
            joined.append(ln)
    lines = joined
    text = "\n".join(lines)
    text = re.sub(r"(\w)-\n([a-z])", r"\1\2", text)
    entries: list[str] = []
    if re.search(r"(?m)^\s*\[\d{1,3}\]", text):
        parts = re.split(r"(?m)^\s*\[(\d{1,3})\]\s*", text)
        for i in range(1, len(parts) - 1, 2):
            entries.append(" ".join(parts[i + 1].split()))
    elif len(re.findall(r"(?m)^\s*\d{1,3}\.\s+\S", text)) >= 5:
        parts = re.split(r"(?m)^\s*(\d{1,3})\.\s+(?=\S)", text)
        for i in range(1, len(parts) - 1, 2):
            entries.append(" ".join(parts[i + 1].split()))
    else:
        # 块边界（空行）优先当条目边界；块内再按「作者起头 + 上行收尾」切
        chunks: list[list[str]] = [[]]
        for line in lines:
            if line.strip():
                chunks[-1].append(line.strip())
            elif chunks[-1]:
                chunks.append([])
        for chunk in chunks:
            if not chunk:
                continue
            cur: list[str] = []
            prev = ""
            for s in chunk:
                if cur and REF_START.match(s) and re.search(r"[.)\d]$|\d{4}[a-z]?\.?$", prev):
                    entries.append(" ".join(" ".join(cur).split()))
                    cur = []
                cur.append(s)
                prev = s
            if cur:
                entries.append(" ".join(" ".join(cur).split()))
        # 块切得太碎（一行一块）：把不像条目开头的碎片并回上一条
        merged: list[str] = []
        for e in entries:
            if merged and not REF_START.match(e) and not re.match(r"^[\[（(]?\d", e):
                merged[-1] = merged[-1] + " " + e
            else:
                merged.append(e)
        entries = merged
    cleaned = []
    for e in entries:
        e = re.sub(r"\s+", " ", e).strip()
        if len(e) < 25:
            continue
        cleaned.append(format_reference(e))
    return cleaned


# ----------------------------------------------------------------------------- brief

BRIEF = """# 源稿核准任务：{key}（{lang_name}）

由具备原页视觉核对能力的主代理/较强模型负责。只产正文、清单和审核记录；Luna 等翻译模型另收锁定任务，不能承担公式转写或裁图判断。

## 输入
工作区：{work}
- columns.md：主要抽取原料，按连续章节读；只有乱码或乱序时才读对应页的 fulltext.txt，避免两份全文重复加载。
- pages/pP.png：{pages} 页，{dpi} dpi；结构、公式、表格、图注以原页为准。看不清时放大对应区域。
- meta.json：题名/作者/DOI；有错照首页补 fields.json，由分析任务处理。
- refs.md：原刊参考表草稿，对照参考页核对一次，保留原号和原刊重复条目。finish 同源复制到中英文末尾。
- 正则提示：图 {hint_figs}；表 {hint_tabs}；公式 {hint_eqs}。不能作为真实总数。

## 1 整理原文与清单
{step1_body}
先看首页版本和摘要、末页及参考起止，确认是真正完整论文，不是摘要网页打印件。沿连续章节看原页结构与跨栏/跨页衔接，同时整理清单；正常文字直接复用，不逐字重抄。发现乱码、乱序或疑似漏段，只扩大对应片段核查。
公式、表体数据和参考条目必须逐项对原页：上下标、正负号、分母、指数、log/ln、数字、单位、脚注及条目边界。不猜乱码、不替作者改排印错误，保留全部段落和适用条件。
写 {out}/layout.json：
{{
  "headings":[{{"level":2,"title":"Introduction","page":1}}],
  "figures":[{{"num":1,"page":4,"caption":"Fig. 1. 原文完整图注"}}],
  "tables":[{{"num":1,"page":4,"title":"Table 1. 原文完整表题"}}],
  "equations":[{{"num":"2.1","page":3}}],
  "notes":"原刊疑点及依据，无疑点可空"
}}
公式号保留完整原号（整数、2.1、A1），缺号回原页；确实跳号才登记 verify_overrides.json + 非空理由。

正文格式：
- # 原题 → **作者** → 完整单位（一行一个）→ *刊名 年份 卷页 DOI*；删页眉、水印、收稿日期等期刊壳。
- 英文有 ## Abstract，原刊 Keywords/Highlights 有才保留；章节层级和编号照原刊。
- 编号公式 $$ … \\tag{{N}} $$ 放在引出段落后；变量用 $…$。禁止集中堆公式。
- 图注 **Fig. N.** 原文图注（中文原刊 **图 N.**）；图片行由裁图脚本插入。
- **Table N.** 表题（中文原刊 **表 N.**），下一段紧跟 Markdown 表；数字和单位逐行对原页。
- 参考表只核对 refs.md，不在正文重复手抄。
首页题名块原料：
{titleblock}

## 2 裁图与一次核图
python "{cutfigs}" --work "{work}" --embed
自动结果是候选。直接看 cutfigs 已生成的 images/_review_figN.png，核对整幅子图、坐标轴、图例、色条及图号；不能只看缩略图或相信 status=ok。只有核对图缺失或裁图改变时才运行 figtools compare，不重复生成已有正确核对图。
坏图只重裁对应图：python "{figtools}" crop --work "{work}" --page P --num N --box x0,y0,x1,y1
默认 box 为原页像素，DPI 取 stats.renderDpi；使用 pt 时显式 --unit pt。完整核对后：
python "{figtools}" review --work "{work}" --num N --note "核对 pP，全部子图/轴/图例完整，图号对应"
重裁撤销确认；不重裁正确图。首次 --embed 已插图；只有修过裁图才再次 embed。

## 3 封存已核准源稿
python "{scripts}/translation.py" review-source --work "{work}" --note "已核对原页结构、各式上下标/分母/指数及表格数值；疑点和页码…"
这一步记录审核并保存源文/布局快照，使用文枢现有 KaTeX 批量检查公式能否渲染。语法成功不证明公式含义正确，原页核对不能省。
核准后不要再改正文/布局；必要修正后重新核准对应源稿，翻译只重做受影响部分。

结束只报告源稿/清单、裁图核对与未解决疑点。尚有看不清的公式或子图不能记录审核完成。其他任务由主代理派发；不改正式库/索引/个人数据。
"""

ANALYSIS_BRIEF = """# 分析与字段任务：{key}
输入：{work}/out/en.md（英文原刊）或 zh.md（中文原刊）、layout.json；字段目录：{domains}。
只写 out/notes.md、terms.json、fields.json。原刊没有 Highlights 时另写 out/highlights.md：## 亮点、3–5 条纯文字列表，以及 > **【说明】** 本节要点由 AI 通读全文提炼，原刊未印 Highlights。 不含数学、图片或代码，由宿主在翻译后机械插入。原刊有 Highlights 则由翻译任务翻译它。
翻译另一个模型负责；不修改正文、公式、图、refs 或审核记录。只读本任务输入，按所需章节取内容；不重复打开所有原页。默认简洁笔记：每个必需小节只写与本文直接相关的内容，不重复摘要或扩写通用教材。
笔记中的数字和结论注明章节、图表号或页码；作者结论、原刊疑点及自己的建议分开。重点公式从核准正文复制，解释放 notes，不能改正文公式或另造公式。拿不准交回源稿核准者。

notes.md 保留以下骨架：
# 🎓 学习卡：<中文译名>
## 📌 摘要要点
1. …（3–5 条，覆盖问题、方法、主要结果与局限）
## ❓ 问答
### Q1：本文要回答的科学问题是什么？
（共 4–6 个问题，各有简短、有原文依据的回答）
# 🔬 深度分析
## 研究问题
## 方法概述
### 核心方法
### 关键公式（LaTeX）
### 关键创新
## 实验结果
## 深度分析
### 研究价值
### 优势
### 局限性
### 适用场景
## 技术路线定位
## 未来工作建议
## 我的综合评价
（总分 X.X/10；创新性/严谨性/可复现性/写作/影响力各一句）
# ✍️ 写作逻辑
## 论证骨架
## 谋篇布局
## 值得模仿的写法

terms.json：默认 8–10 个核心术语，复杂论文最多 20 项，字段 term/zhName/fullName/type/definition/context；
term 为标准英文名，type 为方法/模型/指标/算法/物理量/概念/数据集，definition 1–3 句准确解释，context 一句本文用法。JSON 反斜杠双写，不加 wiki 链接。

fields.json：
{{
 "title":"原题（meta 无误可空）", "authors":[], "year":"", "journal":"",
 "firstAuthorPinyin":"中文原刊必填姓拼音，英文可空",
 "shortTitle":"14字以内中文短题，无空格标点", "translatedTitle":"完整中文译名",
 "domain":"大类/子类", "tldr":"40字以内摘要", "question":"研究问题", "score":"8.5/10",
 "topics":["中文主题"], "keywords":["原刊关键词，无则空"],
 "affiliations":["完整机构名"], "highlightsPrinted":false
}}
meta 的非空值若已确认错误，照原页填写纠正值；fields 会覆盖它。不要自行推测出版信息。
只回复完成文件与疑点；不运行整篇验收/发布，同步由主代理串行处理。
"""

STEP1_EN = """写 out/en.md，拿 columns.md 的原句作底，对着原页恢复层级、公式、表格；图先写 **Fig. N.** 图注。首页信息与摘要可能交错，摘要对照 p1。正文与 layout.json 的图、表、公式须双向一一对应。"""
STEP1_ZH = """中文原刊：**不写 en.md**。这一步产 `layout.json` 和 `zh.md` 的正文部分——拿 columns.md 的段落当底子，对着页面图整理出干净的中文正文（不翻译、不改写，只修版式：标题层级、段落、公式 LaTeX、表格、图注 `**图 N.** …`），前面按「格式契约」补 `## 亮点` / `## 摘要`；嵌图行由 ② 自动插。写完把 layout.json 对一遍：正文里每条 `**图 N.**`、`**表 N.**`、`\\tag{N}` 都要在清单里，反之亦然。"""


def _fmt_nums(nums: list[int]) -> str:
    if not nums:
        return "无"
    runs: list[str] = []
    start = prev = nums[0]
    for n in nums[1:] + [None]:
        if n is not None and n == prev + 1:
            prev = n
            continue
        runs.append(f"{start}" if start == prev else f"{start}–{prev}")
        if n is not None:
            start = prev = n
    return "、".join(runs)


def write_brief(work: Path, meta: dict, domains: list[str], stats: dict, titleblock: str) -> None:
    """写 brief.md（v2「先排版」任务书）。应有清单不再由脚本给，只给正则粗数作提示。"""
    lang = meta.get("lang", "en")
    hints = stats.get("columns", {})
    scripts = Path(__file__).resolve().parent
    text = BRIEF.format(
        key=meta["key"],
        pages=stats.get("pages", "?"),
        dpi=stats.get("renderDpi", 100),
        scripts=str(scripts),
        cutfigs=str(scripts / "cutfigs.py"),
        figtools=str(scripts / "figtools.py"),
        verify=str(scripts / "verify.py"),
        lang_name="中文原刊" if lang == "zh" else "英文原刊",
        work=str(work),
        out=str(work / "out"),
        domains="；".join(domains) if domains else "（空库）",
        en_rule="中文原刊：**不写 en.md**" if lang == "zh" else "原文清洁版，逐句照录，只修版式",
        zh_rule="中文原刊：① 已整理出正文，这一步只补亮点/摘要格式并核对" if lang == "zh" else "照 en.md 骨架逐节全译",
        step1_body=STEP1_ZH if lang == "zh" else STEP1_EN,
        titleblock=titleblock.strip(),
        hint_figs=_fmt_nums(hints.get("hintFigures", [])),
        hint_tabs=_fmt_nums(hints.get("hintTables", [])),
        hint_eqs=_fmt_nums(hints.get("hintEquations", [])),
    )
    (work / "brief.md").write_text(text, encoding="utf-8")
    (work / "analysis-brief.md").write_text(ANALYSIS_BRIEF.format(
        key=meta["key"], work=str(work), domains="；".join(domains) or "（空库）"), encoding="utf-8")


# ----------------------------------------------------------------------------- main

def main() -> None:
    utf8_stdio()
    ap = argparse.ArgumentParser(description="PDF → 结构化工作区")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--vault", default="", help="用于列出已有领域目录")
    ap.add_argument("--no-crossref", action="store_true")
    ap.add_argument("--dpi", type=int, default=100)
    ap.add_argument("--key", default="", help="覆盖自动生成的 AuthorYear 键")
    args = ap.parse_args()

    pdf = Path(args.pdf).resolve()
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    (work / "out").mkdir(exist_ok=True)
    stats: dict = {"pdf": str(pdf), "flow": "v2-layout-first", "renderDpi": args.dpi, "steps": {}}
    t0 = time.time()

    doc = pymupdf.open(pdf)
    t = time.time()
    meta = build_meta(doc, pdf, not args.no_crossref)
    meta["qualityPolicy"] = "source-reviewed-v1"
    if args.key:
        meta["key"] = args.key
    stats["steps"]["meta"] = round(time.time() - t, 2)

    t = time.time()
    pages_dir = work / "pages"
    pages_dir.mkdir(exist_ok=True)
    for pno, page in enumerate(doc, start=1):
        page.get_pixmap(dpi=args.dpi, alpha=False).save(pages_dir / f"p{pno}.png")
    stats["steps"]["pages"] = round(time.time() - t, 2)

    # 原始纯文本（兜底）+ 按栏切分的干净正文（AI 排版的原料；不再产 en.draft.md，也不在这一步裁图）
    t = time.time()
    fulltext = "\n\n".join(f"<<< page {i} >>>\n{p.get_text()}" for i, p in enumerate(doc, start=1))
    (work / "fulltext.txt").write_text(fulltext, encoding="utf-8")
    columns, cstats = layout.columns_markdown(doc)
    (work / "columns.md").write_text(columns, encoding="utf-8")
    stats["steps"]["columns"] = round(time.time() - t, 2)

    # 编号文献直接取原始全文：保留原刊号与重复条目，不依赖正文栏切分。
    # 作者年份制仍沿用元素流水线；stats.references 只记录明确的原刊数字证据。
    t = time.time()
    refs: list[dict] = []
    reference_source = extract_numbered_references(fulltext)
    stats["references"] = {
        "numbers": reference_source["numbers"],
        "warnings": reference_source["warnings"],
        "entryCount": len(reference_source["entries"]),
    }
    try:
        if reference_source["entries"]:
            refs = [
                {"num": entry["num"], "text": format_reference(entry["text"])}
                for entry in reference_source["entries"]
            ]
        else:
            elements, _ = layout.extract_elements(doc, {})
            refs_lines = next((el["lines"] for el in elements if el["kind"] == "refs"), [])
            refs = [
                {"num": num, "text": entry}
                for num, entry in enumerate(parse_refs(refs_lines), start=1)
            ]
    except Exception as exc:  # 参考文献抽不出不影响后面的步骤
        stats["refsError"] = str(exc)
    (work / "refs.md").write_text(
        "\n".join(f'- **[{e["num"]}]** {e["text"]} ^ref-{e["num"]}' for e in refs) + ("\n" if refs else ""),
        encoding="utf-8")
    stats["steps"]["refs"] = round(time.time() - t, 2)

    head, extra = front_block(meta, doc, meta["lang"])
    meta.update(extra)
    (work / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    domains = []
    if args.vault:
        papers = Path(args.vault) / "Papers"
        if papers.is_dir():
            for d1 in sorted(p for p in papers.iterdir() if p.is_dir()):
                subs = [p for p in d1.iterdir() if p.is_dir() and not (p / "content").exists()]
                domains += [f"{d1.name}/{s.name}" for s in sorted(subs)] or [d1.name]

    stats.update({
        "key": meta["key"], "lang": meta["lang"], "pages": len(doc), "doi": meta["doi"],
        "metaSource": meta["source"], "refs": len(refs),
        "layoutEngine": f"pymupdf {pymupdf.__version__} spans → columns.md（按栏切分）",
        "columns": cstats,
    })
    write_brief(work, meta, domains, stats, head)
    stats["totalSeconds"] = round(time.time() - t0, 2)
    (work / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
