# -*- coding: utf-8 -*-
"""
layout.py — 用 PyMuPDF 的 span 级数据自己做版面还原（不依赖 pymupdf4llm）。

输出一串「元素」（dict）：
    {"kind": "heading", "level": 2, "text": "...", "page": 3}
    {"kind": "para",    "text": "...", "page": 3}
    {"kind": "caption", "num": "3", "text": "Fig. 3. ...", "page": 5}      # 图注
    {"kind": "table",   "num": "2", "caption": "...", "md": "| a | b |", "page": 6}
    {"kind": "equation","num": "4", "text": "raw", "page": 4}
    {"kind": "refs",    "lines": [...]}                                      # 参考文献原始行
"""
from __future__ import annotations

import math
import re
from collections import Counter

import pymupdf

CAPTION_RE = re.compile(r"^\s*(Fig\.?|Figure|FIG\.?|图)\s*([A-Z]?\d{1,3}[a-z]?)\b\.?", re.I)
CAPTION_VERB = re.compile(r"^\s*(?:Fig\.?|Figure|图)\s*[A-Z]?\d{1,3}[a-z]?\s*[.:]?\s*(?:(?:shows?|illustrates?|depicts?|displays?|presents?|gives?|compares?|demonstrates?|plots?|summarizes?|indicates?|reveals?|provides?|reports?|and|to|in|of|for|is|are|was|were|also)\b|中|所示|给出|显示|为|展示|反映|表明|可见|可以看出|说明|对比|描述|绘出|示出)", re.I)
EQ_NUM_ONLY = re.compile(r"^\s*[(（]\s*(\d{1,3}[a-z]?)\s*[)）]\s*$")
TABLE_CAP_RE = re.compile(r"^\s*(Table|TABLE|表)\s*([A-Z]?\d{1,3})\b\.?", re.I)
TABLE_VERB = re.compile(r"^\s*(?:Table|表)\s*[A-Z]?\d{1,3}\s*[.:]?\s*(?:shows?|lists?|summarizes?|presents?|gives?|compares?|and|to|in|of|for|is|are|中|所示|给出|列出)\b", re.I)
NUMBERED = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+([A-Za-zÀ-ɏ(].{1,140})$")
APPENDIX_SUB = re.compile(r"^([A-H](?:\.\d{1,2}){1,2})\.?\s+([A-Za-z(].{1,120})$")
CN_NUMBERED = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,3})\s*[、.]?\s*([一-鿿].{0,60})$")
SECTION_H2 = re.compile(
    r"^(abstract|keywords?|key\s*words|highlights|introduction|conclusions?|concluding remarks|summary|"
    r"acknowledg?e?ments?|references|bibliography|literature cited|nomenclature|list of symbols|notation|"
    r"funding|data availability(?: statement)?|declaration of competing interest|conflicts? of interest(?: statement)?|"
    r"credit authorship contribution statement|author contributions?|supplementary (?:material|data|information)|"
    r"appendix(?:\s+[A-Z])?(?:[.:]\s*.*)?|methods?|methodology|results?|discussion|results and discussion|"
    r"materials and methods|background|related work|引言|结论|摘要|关键词|参考文献|致谢|结语|讨论)\b",
    re.I,
)
NOISE_RE = re.compile(
    r"downloaded from|creative commons|all rights reserved|rights and content|sciencedirect|"
    r"contents lists available|journal homepage|^\s*©|^\s*\(c\)\s*20\d\d|terms and conditions|"
    r"wiley online library|for rules of use|licensed under|open access article|^\s*\d{1,4}\s*$|"
    r"^\s*page \d+ of \d+|^\s*https?://\S+$|corresponding author|e-?mail address|^\s*\*?\s*corresponding|"
    r"^\s*E-?mail:|^\s*Received:? \d|^\s*Accepted:? \d|^\s*Available online|^\s*Article history|"
    r"^\s*\d{4}-\d{3,4}[Xx\d]?/|^\s*doi:\s*10\.|^\s*https?://doi\.org|^\s*(?:Citation|Correspondence|Funding information)[:：]|"
    r"^\s*This is an open access|^\s*Published by|^\s*Copyright\b|^\s*\S+@\S+\.(?:edu|com|org|cn|ac|net)\b",
    re.I,
)
MATH_FONT = re.compile(r"math|symbol|cmmi|cmsy|cmex|mtmi|mtsy|mtex|euclid|msam|msbm|stix", re.I)
BOLD_FONT = re.compile(r"bold|black|heavy|semibold|demibold|hei\b|hei[-_]|_hei|BL$|-B$|\.B$|Bd$", re.I)
SPACED_PREFIX = re.compile(r"^((?:[A-Za-z]\s){2,}[A-Za-z])(?=\s|$)")
LABEL_ONLY = re.compile(r"^\s*(?:Fig\.?|Figure|FIG\.?|Table|TABLE|图|表)\s*(?:[A-Z]?\d{1,3}[a-z]?)?\s*[.:：]?\s*$", re.I)
REFS_INLINE = re.compile(r"^\s*(?:参\s*考\s*文\s*献|References|REFERENCES|Bibliography)\s*(?:[（(]\s*References\s*[)）])?\s*[:：]?\s*(?=\S)")


WILEY_LABEL = re.compile(r"^(F\s?I\s?G\s?U\s?R\s?E|T\s?A\s?B\s?L\s?E)(?=\s|\d)", re.I)


def despace(t: str) -> str:
    """`a b s t r a c t` / `F I G U R E 1 0 …` / `TA B L E 2` → 合并开头被拉开的单词和紧随的编号。"""
    t = t.strip()
    collapsed = False
    m = WILEY_LABEL.match(t)
    if m:
        t = m.group(1).replace(" ", "") + t[m.end():]
        collapsed = True
    m = SPACED_PREFIX.match(t)
    while m:
        t = m.group(1).replace(" ", "") + t[m.end():]
        collapsed = True
        m = SPACED_PREFIX.match(t)
    if collapsed:
        t = re.sub(r"^([A-Za-z]+)\s*(\d(?:\s\d){1,2})(?=\s|$)", lambda mm: mm.group(1) + " " + mm.group(2).replace(" ", ""), t)
    return t


def degenerate(d: dict) -> bool:
    """每词一行的畸形 PDF（老 Particuology 等）：行数逼近词数。"""
    blocks = [b for b in d["blocks"] if b.get("type") == 0]
    nlines = sum(len(b.get("lines", [])) for b in blocks)
    nwords = sum(len(s["text"].split()) for b in blocks for l in b.get("lines", []) for s in l.get("spans", []))
    return nlines > 40 and nlines >= 0.6 * nwords


def regroup_spans(d: dict) -> list[dict]:
    """把散成一词一块的 span 按基线重组成行、按行距重组成块，产出和 get_text('dict') 同构的 blocks。"""
    spans = []
    for b in d["blocks"]:
        if b.get("type") != 0:
            continue
        for l in b.get("lines", []):
            for s in l.get("spans", []):
                if s["text"].strip():
                    spans.append(dict(s))
    spans.sort(key=lambda s: (round(s["origin"][1] / 2), s["bbox"][0]))
    lines: list[dict] = []
    for s in spans:
        y, h = s["origin"][1], (s["size"] if s["size"] > 0.5 else 8.0)
        x0, x1 = s["bbox"][0], s["bbox"][2]
        for ln in reversed(lines[-8:]):
            if abs(ln["y"] - y) <= max(2.0, 0.35 * h) and -1.5 * h <= x0 - ln["x1"] <= 2.5 * h:
                last = ln["spans"][-1]
                if x0 - last["bbox"][2] > 0.12 * h and not last["text"].endswith(" "):
                    last["text"] += " "
                ln["spans"].append(s)
                ln["x1"] = max(ln["x1"], x1)
                bb = ln["bbox"]
                ln["bbox"] = [min(bb[0], s["bbox"][0]), min(bb[1], s["bbox"][1]), max(bb[2], s["bbox"][2]), max(bb[3], s["bbox"][3])]
                break
        else:
            lines.append({"y": y, "x1": x1, "bbox": list(s["bbox"]), "spans": [s]})
    lines.sort(key=lambda l: (l["bbox"][1], l["bbox"][0]))
    blocks: list[dict] = []
    for ln in lines:
        h = max(ln["bbox"][3] - ln["bbox"][1], 1.0)
        w = ln["bbox"][2] - ln["bbox"][0]
        for pb in reversed(blocks[-4:]):
            last = pb["lines"][-1]["bbox"]
            gap = ln["bbox"][1] - last[3]
            xov = min(ln["bbox"][2], pb["bbox"][2]) - max(ln["bbox"][0], pb["bbox"][0])
            if -0.5 * h <= gap <= 0.9 * h and xov > 0.3 * min(w, pb["bbox"][2] - pb["bbox"][0]):
                pb["lines"].append({"bbox": ln["bbox"], "spans": ln["spans"]})
                bb = pb["bbox"]
                pb["bbox"] = [min(bb[0], ln["bbox"][0]), min(bb[1], ln["bbox"][1]), max(bb[2], ln["bbox"][2]), max(bb[3], ln["bbox"][3])]
                break
        else:
            blocks.append({"type": 0, "bbox": list(ln["bbox"]), "lines": [{"bbox": ln["bbox"], "spans": ln["spans"]}]})
    return blocks


def text_dict(page: pymupdf.Page, flags: int | None = None) -> tuple[dict, bool]:
    """get_text('dict')，畸形页自动重组。返回 (dict, 是否重组过)。"""
    d = page.get_text("dict", flags=flags) if flags is not None else page.get_text("dict")
    if degenerate(d):
        d = {"blocks": regroup_spans(d), "width": d.get("width"), "height": d.get("height")}
        return d, True
    return d, False


def text_blocks(page: pymupdf.Page) -> list[tuple[pymupdf.Rect, str]]:
    """(Rect, 文本) 列表：get_text('blocks') 的替代——畸形页先重组；「正文段 + 图注」粘成一块的在图注行切开。"""
    d, _ = text_dict(page)
    out: list[tuple[pymupdf.Rect, str]] = []
    for b in d["blocks"]:
        if b.get("type") != 0:
            continue
        lines: list[tuple[str, pymupdf.Rect]] = []
        for l in b["lines"]:
            t = "".join(s["text"] for s in l["spans"]).strip()
            if t:
                lines.append((t, pymupdf.Rect(l["bbox"])))
        if not lines:
            continue
        cuts = [0]
        for i in range(1, len(lines)):
            t, r = lines[i]
            pt, pr = lines[i - 1]
            dt = despace(t)
            label = CAPTION_RE.match(dt) or TABLE_CAP_RE.match(dt)
            if not label:
                continue
            strong = re.match(r"^\s*(?:Fig\.?|Figure|FIG\.?|图|Table|TABLE|表)\s*[A-Z]?\d{1,3}[a-z]?\s*[.:：]", dt, re.I)
            if strong or re.search(r"[.!?:。！？；;)\]]$", pt) or r.y0 - pr.y1 > 0.9 * max(r.height, pr.height, 1):
                cuts.append(i)
        cuts.append(len(lines))
        for a, z in zip(cuts, cuts[1:]):
            seg = lines[a:z]
            rect = pymupdf.Rect(seg[0][1])
            for _, rr in seg[1:]:
                rect |= rr
            out.append((rect, "\n".join(t for t, _ in seg)))
    return out


def is_cjk(ch: str) -> bool:
    return "一" <= ch <= "鿿" or "　" <= ch <= "〿" or "＀" <= ch <= "￯"


def norm(text: str) -> str:
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", text.strip().lower()))


# ----------------------------------------------------------------------------- spans → text

def render_line(line: dict, fallback_size: float) -> tuple[str, float, bool]:
    """一行 spans → 文本（带 ^{} _{} 上下标）。返回 (text, 主字号, 是否加粗)。"""
    spans = [s for s in line.get("spans", []) if s.get("text")]
    if not spans:
        return "", 0.0, False
    sizes = [s["size"] for s in spans if s["size"] > 0.5]
    main = max(sizes) if sizes else fallback_size
    mains = [s for s in spans if s["size"] >= main - 0.6 or s["size"] <= 0.5]
    base_y = sorted(s["origin"][1] for s in mains)[len(mains) // 2]
    bold_chars = sum(len(s["text"]) for s in spans if (s["flags"] & 16) or BOLD_FONT.search(s["font"]))
    total = sum(len(s["text"]) for s in spans) or 1
    out = ""
    for s in spans:
        t = s["text"]
        if not t.strip():
            out += t
            continue
        size = s["size"] if s["size"] > 0.5 else main
        small = main - size >= 1.0 and size <= main * 0.85
        sup_flag = bool(s["flags"] & 1)
        if small or sup_flag:
            dy = s["origin"][1] - base_y
            body = t.strip()
            if sup_flag or dy < -1.2:
                out = out.rstrip() + "^{" + body + "}"
                continue
            if dy > 1.2:
                out = out.rstrip() + "_{" + body + "}"
                continue
        out += t
    return out, main, bold_chars / total > 0.6


def join_lines(lines: list[str]) -> str:
    text = lines[0]
    for nxt in lines[1:]:
        if text and nxt and is_cjk(text[-1]) and is_cjk(nxt[0]):
            text += nxt
        elif text.endswith("-") and nxt[:1].islower():
            text = text[:-1] + nxt
        else:
            text += " " + nxt
    return text


def body_font_size(doc: pymupdf.Document, sample: int = 6) -> float:
    sizes: Counter = Counter()
    step = max(1, len(doc) // sample)
    for i in range(0, len(doc), step):
        for b in doc[i].get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l.get("spans", []):
                    if s["text"].strip() and s["size"] > 0.5:
                        sizes[round(s["size"], 1)] += len(s["text"])
    return sizes.most_common(1)[0][0] if sizes else 10.0


# ----------------------------------------------------------------------------- block → segments

def looks_like_label(text: str) -> bool:
    t = despace(text)
    return bool(CAPTION_RE.match(t) or TABLE_CAP_RE.match(t) or NUMBERED.match(t) or CN_NUMBERED.match(t)
                or APPENDIX_SUB.match(t) or (SECTION_H2.match(t) and len(t) <= 40))


def segment_block(block: dict, body: float) -> list[dict]:
    """把「标题+正文」「图注+正文」粘成一块的情况按行样式切开。"""
    rows = []
    for line in block.get("lines", []):
        t, size, bold = render_line(line, body)
        if t.strip():
            rows.append({"text": t.strip(), "size": size, "bold": bold, "rect": pymupdf.Rect(line["bbox"]),
                         "font": (line["spans"][0]["font"] if line.get("spans") else "")})
    if not rows:
        return []
    segs: list[list[dict]] = [[rows[0]]]
    for prev, cur in zip(rows, rows[1:]):
        style_break = (cur["bold"] != prev["bold"]) or abs(cur["size"] - prev["size"]) >= 1.0
        label_break = looks_like_label(cur["text"]) and re.search(r"[.!?:。！？；;)]$|^\s*$", prev["text"]) is not None
        prev_label = len(segs[-1]) == 1 and looks_like_label(prev["text"]) and len(prev["text"]) <= 60 \
            and not LABEL_ONLY.match(prev["text"]) and not looks_like_label(cur["text"])
        gap_break = cur["rect"].y0 - prev["rect"].y1 > max(cur["size"], prev["size"]) * 0.9
        if style_break and (len(segs[-1]) <= 2 or len(cur["text"]) <= 120) or label_break or prev_label or gap_break:
            segs.append([cur])
        else:
            segs[-1].append(cur)
    # 「Fig. 2.」「Table 1」这种只剩标签的段并回它后面的说明文字
    merged: list[list[dict]] = []
    for seg in segs:
        if merged and LABEL_ONLY.match(join_lines([r["text"] for r in merged[-1]])):
            merged[-1].extend(seg)
        else:
            merged.append(seg)
    segs = merged
    out = []
    for seg in segs:
        rect = pymupdf.Rect(seg[0]["rect"])
        for r in seg[1:]:
            rect |= r["rect"]
        sizes = Counter(round(r["size"], 1) for r in seg)
        fonts = Counter(r["font"] for r in seg)
        out.append({"rect": rect, "text": join_lines([r["text"] for r in seg]), "lines": [r["text"] for r in seg],
                    "size": sizes.most_common(1)[0][0], "bold": sum(r["bold"] for r in seg) >= max(1, len(seg) * 0.6),
                    "font": fonts.most_common(1)[0][0], "nlines": len(seg)})
    return out


# ----------------------------------------------------------------------------- page → ordered blocks

def page_blocks(page: pymupdf.Page, fig_regions: list[pymupdf.Rect], table_rects: list[pymupdf.Rect], body: float):
    d, _ = text_dict(page, pymupdf.TEXT_DEHYPHENATE | pymupdf.TEXT_MEDIABOX_CLIP)
    H = page.rect.height
    blocks = []
    for b in d["blocks"]:
        if b.get("type") != 0:
            continue
        for seg in segment_block(b, body):
            r = seg["rect"]
            text = seg["text"]
            inside = False
            for reg in fig_regions + table_rects:
                if reg.intersects(r) and (reg & r).get_area() > 0.6 * r.get_area():
                    inside = True
                    break
            if inside and not CAPTION_RE.match(despace(text)) and not TABLE_CAP_RE.match(despace(text)):
                continue
            blocks.append(seg)
    top, bot = page.rect.y0 + H * 0.045, page.rect.y1 - H * 0.045
    kept = []
    for b in blocks:
        r = b["rect"]
        if (r.y1 <= top or r.y0 >= bot) and b["nlines"] <= 2 and len(b["text"]) < 160:
            continue  # 页眉页脚
        if r.y0 >= page.rect.y1 - H * 0.18 and b["size"] <= body - 1.5 and b["nlines"] <= 4 \
                and not TABLE_CAP_RE.match(b["text"]) and not b["text"].startswith("|"):
            continue  # 脚注
        kept.append(b)
    return kept


def order_blocks(blocks: list[dict], page: pymupdf.Page) -> list[dict]:
    """双栏识别：宽块切带，带内先左栏后右栏。"""
    if not blocks:
        return []
    x0 = min(b["rect"].x0 for b in blocks)
    x1 = max(b["rect"].x1 for b in blocks)
    W = max(x1 - x0, 1)
    narrow_chars = sum(len(b["text"]) for b in blocks if b["rect"].width < 0.62 * W)
    total_chars = sum(len(b["text"]) for b in blocks) or 1
    if narrow_chars / total_chars < 0.45:
        return sorted(blocks, key=lambda b: (round(b["rect"].y0 / 4), b["rect"].x0))
    mid = x0 + W / 2
    lefts = [b["rect"].x0 for b in blocks if b["rect"].width < 0.62 * W]
    right_starts = [x for x in lefts if x > mid - 0.15 * W]
    split = (min(right_starts) - 3) if right_starts else mid
    ordered = []
    band: list[dict] = []

    def flush_band():
        if not band:
            return
        left = sorted((b for b in band if b["rect"].x0 < split), key=lambda b: b["rect"].y0)
        right = sorted((b for b in band if b["rect"].x0 >= split), key=lambda b: b["rect"].y0)
        ordered.extend(left + right)
        band.clear()

    for b in sorted(blocks, key=lambda b: b["rect"].y0):
        if b["rect"].width >= 0.62 * W:
            flush_band()
            ordered.append(b)
        else:
            band.append(b)
    flush_band()
    return ordered


# ----------------------------------------------------------------------------- classification

MATHY = re.compile(r"[=∕∑∫∂∇√≈≤≥×÷{}]|_\{|\^\{")


def heading_of(text: str, size: float, bold: bool, body: float, nlines: int) -> tuple[int, str] | None:
    t = despace(text)
    if nlines > 3 or len(t) > 160 or MATHY.search(t):
        return None
    big = size >= body + 1.4
    m = NUMBERED.match(t)
    if m and (big or bold or size >= body + 0.5):
        depth = m.group(1).count(".") + 1
        title_body = m.group(2).strip()
        if depth > 4 or (title_body.endswith(".") and len(title_body.split()) > 10):
            return None
        dot = "." if t[len(m.group(1)):len(m.group(1)) + 1] == "." else ""
        return min(1 + depth, 5), f"{m.group(1)}{dot} {title_body.rstrip('.')}"
    m = CN_NUMBERED.match(t)
    if m and (big or bold):
        depth = m.group(1).count(".") + 1
        return min(1 + depth, 5), f"{m.group(1)} {m.group(2).strip()}"
    m = APPENDIX_SUB.match(t)
    if m and (big or bold):
        return 2 + m.group(1).count("."), f"{m.group(1)} {m.group(2).strip()}"
    if SECTION_H2.match(t) and len(t) <= 80 and (big or bold or t.lower() in ("abstract", "references", "keywords", "highlights")):
        return 2, t
    if re.match(r"^Appendix\b", t, re.I) and (big or bold):
        return 2, t
    if (big and size >= body + 2.5 or bold and size >= body + 1.0) and len(t) <= 90 and len(t.split()) <= 14 \
            and not t.endswith((".", "。", ":", "：", ",")) and not re.search(r"\bet al\b|@|\d{4}\)", t):
        return 3, t
    return None


def junk_heading(t: str) -> bool:
    return bool(re.search(r"\bet al\b", t, re.I) or re.match(r"^([A-Z]\.\s?)+[A-Z][a-z]+(,|$)", t)
                or (re.search(r"\b(Journal|Vol\.?|Volume|Issue|pp\.)\b", t) and len(t) < 90))


def is_equation(b: dict, body: float) -> str | None:
    t = b["text"]
    m = re.search(r"[(（]\s*(\d{1,3}[a-z]?)\s*[)）]\s*$", t)
    mathy = bool(MATH_FONT.search(b["font"])) or len(re.findall(r"[=+−∑∫∂∇√≈≤≥×÷^_{}λμρσθαβγδεφψωΔΩπ]", t)) >= 2
    if m and mathy and len(t) < 500:
        words = len(re.findall(r"\b(?:the|and|of|is|are|with|for|that|this|which)\b", t, re.I))
        if words <= 2:
            return m.group(1)
    return None


def page_tables(page: pymupdf.Page, want_text_strategy: bool) -> list[tuple[pymupdf.Rect, str]]:
    tabs = []
    for strategy in (["lines"] + (["text"] if want_text_strategy else [])):
        try:
            found = page.find_tables(strategy=strategy).tables
        except Exception:
            found = []
        for tb in found:
            if tb.row_count >= 2 and tb.col_count >= 2:
                md = tb.to_markdown().strip()
                cells = [c for row in tb.extract() for c in row if c]
                if md.count("|") >= 6 and len(cells) >= 4:
                    tabs.append((pymupdf.Rect(tb.bbox), md))
        if tabs:
            break
    return tabs


# ----------------------------------------------------------------------------- document

def extract_elements(doc: pymupdf.Document, fig_regions_by_page: dict[int, list[pymupdf.Rect]]) -> tuple[list[dict], dict]:
    body = body_font_size(doc)
    per_page: list[list[dict]] = []
    tables_by_page: dict[int, list[tuple[pymupdf.Rect, str]]] = {}
    regrouped_pages = 0
    for pno, page in enumerate(doc, start=1):
        if degenerate(page.get_text("dict")):
            regrouped_pages += 1
        has_table_caption = bool(re.search(r"(?m)^\s*(?:Table|TABLE|表|T\s?A\s?B\s?L\s?E)\s*[A-Z]?\d", page.get_text()))
        tabs = page_tables(page, has_table_caption)
        tables_by_page[pno] = tabs
        blocks = order_blocks(page_blocks(page, fig_regions_by_page.get(pno, []), [t[0] for t in tabs], body), page)
        for b in blocks:
            b["page"] = pno
        per_page.append(blocks)

    n = len(per_page)
    counter: Counter = Counter()
    for blocks in per_page:
        for key in {norm(b["text"][:120]) for b in blocks if 3 < len(b["text"]) <= 160 and not EQ_NUM_ONLY.match(b["text"])}:
            counter[key] += 1
    repeated = {k for k, c in counter.items() if c >= max(3, math.ceil(n * 0.3))} if n >= 3 else set()

    elements: list[dict] = []
    in_refs = False
    refs_lines: list[str] = []
    stats = {"bodyFontSize": body, "tables": 0, "equations": 0, "headings": 0, "captions": 0, "equationList": [],
             "regroupedPages": regrouped_pages}
    label_hold = ""
    for pno, blocks in enumerate(per_page, start=1):
        pending_tables = list(tables_by_page.get(pno, []))
        for b in blocks:
            t = despace(" ".join(b["text"].split()))
            if not t or (norm(t[:120]) in repeated and not EQ_NUM_ONLY.match(t)) or NOISE_RE.search(t):
                continue
            if LABEL_ONLY.match(t):
                label_hold = t          # 「Table 1」单独一块：并到下一块前面
                continue
            em = EQ_NUM_ONLY.match(t)
            if em:
                # 中文刊常把「（3）」单独排成一块，紧跟在公式体后面：把上一段升级成公式
                num = em.group(1)
                stats["equations"] += 1
                if num not in stats["equationList"]:
                    stats["equationList"].append(num)
                prev = elements[-1] if elements else None
                if prev and prev["kind"] == "para" and prev["page"] == pno and len(prev["text"]) < 500:
                    prev.update({"kind": "equation", "num": num})
                    prev.pop("size", None)
                else:
                    elements.append({"kind": "equation", "num": num, "text": "", "page": pno})
                continue
            if label_hold:
                t = f"{label_hold} {t}"
                label_hold = ""
            rm = REFS_INLINE.match(t)
            if rm and not in_refs and pno >= max(2, len(per_page) // 2):
                in_refs = True
                refs_lines.extend(b["lines"][:1] and [t[rm.end():]] + b["lines"][1:])
                refs_lines.append("")
                continue
            hd = heading_of(t, b["size"], b["bold"], body, b["nlines"])
            if hd and not junk_heading(hd[1]):
                level, title = hd
                if re.match(r"^(references|bibliography|literature cited|参考文献)\b", title, re.I):
                    in_refs = True
                    continue
                if re.match(r"^(funding information|correspondence|article info)", title, re.I):
                    continue
                if in_refs and level <= 2 and re.match(r"^(appendix|supplementary|nomenclature|附录)", title, re.I):
                    in_refs = False
                if in_refs:
                    continue
                if title.lower() in ("abstract", "keywords", "key words", "highlights", "references"):
                    title = title.capitalize()
                stats["headings"] += 1
                elements.append({"kind": "heading", "level": level, "text": title, "page": pno})
                continue
            if in_refs:
                refs_lines.extend(b["lines"])
                refs_lines.append("")
                continue
            cm = CAPTION_RE.match(t)
            if cm and not TABLE_CAP_RE.match(t) and len(t) > 10 and not CAPTION_VERB.match(t):
                stats["captions"] += 1
                elements.append({"kind": "caption", "num": cm.group(2), "text": t, "page": pno})
                continue
            tm = TABLE_CAP_RE.match(t)
            if tm and not TABLE_VERB.match(t):
                md = ""
                if pending_tables:
                    cap_y = b["rect"].y1
                    pending_tables.sort(key=lambda it: abs(it[0].y0 - cap_y))
                    md = pending_tables.pop(0)[1]
                    stats["tables"] += 1
                elements.append({"kind": "table", "num": tm.group(2), "caption": t, "md": md, "page": pno})
                continue
            eq = is_equation(b, body)
            if eq:
                stats["equations"] += 1
                if eq not in stats["equationList"]:
                    stats["equationList"].append(eq)
                elements.append({"kind": "equation", "num": eq, "text": t, "page": pno})
                continue
            low = t[:40].lower()
            if re.match(r"^abstract\b[\s.:—-]*", low) and len(t) > 60:
                elements.append({"kind": "heading", "level": 2, "text": "Abstract", "page": pno})
                t = re.sub(r"^\s*abstract\b[\s.:—-]*", "", t, flags=re.I)
            elif re.match(r"^摘\s*要", t) and len(t) > 40:
                elements.append({"kind": "heading", "level": 2, "text": "摘要", "page": pno})
                t = re.sub(r"^\s*摘\s*要[\s:：]*", "", t)
            elif re.match(r"^(keywords?|key words|index terms)\b", low):
                elements.append({"kind": "heading", "level": 2, "text": "Keywords", "page": pno})
                t = re.sub(r"^\s*(?:keywords?|key words|index terms)\b[\s.:—-]*", "", t, flags=re.I)
            elif re.match(r"^关键词", t):
                elements.append({"kind": "heading", "level": 2, "text": "关键词", "page": pno})
                t = re.sub(r"^\s*关键词[\s:：]*", "", t)
            elif re.match(r"^highlights\b", low) and len(t) > 30:
                elements.append({"kind": "heading", "level": 2, "text": "Highlights", "page": pno})
                t = re.sub(r"^\s*highlights\b[\s.:—-]*", "", t, flags=re.I)
                t = "\n".join(f"- {x.strip()}" for x in re.split(r"\s*[•●▪]\s*", t) if x.strip())
            elements.append({"kind": "para", "text": t, "page": pno, "size": b["size"]})
        for _, md in pending_tables:
            stats["tables"] += 1
            elements.append({"kind": "table", "num": "", "caption": "", "md": md, "page": pno})
    if refs_lines:
        elements.append({"kind": "refs", "lines": refs_lines})
    return merge_paragraphs(elements), stats


def merge_paragraphs(elements: list[dict]) -> list[dict]:
    """跨栏 / 跨页续段：上一段没收尾标点且下一段小写开头 → 合并。"""
    out: list[dict] = []
    for el in elements:
        if el["kind"] == "para" and out and out[-1]["kind"] == "para" and not el["text"].startswith("- "):
            prev = out[-1]["text"]
            cur = el["text"]
            if not re.search(r"[.!?:。！？；;]\s*[\"'”’)\]]?$", prev) and (
                    cur[:1].islower() or cur[:1] in "(,;" or (is_cjk(cur[:1]) and is_cjk(prev[-1:]))):
                if prev.endswith("-") and cur[:1].islower():
                    out[-1]["text"] = prev[:-1] + cur
                else:
                    joiner = "" if (is_cjk(prev[-1:]) and is_cjk(cur[:1])) else " "
                    out[-1]["text"] = prev + joiner + cur
                continue
        out.append(el)
    return out


# ----------------------------------------------------------------------------- elements → markdown

def citation_sups(text: str) -> str:
    """`word^{12,13}` / `by^{36,37}` / `al.^{5}` 上标引文 → `[12,13]`；`x^{2}` 这类单字母留给公式。"""
    return re.sub(r"(\b(?:by|of|in|on|to|as|at|is|et|al)\b\.?|[A-Za-z]{3}|[.,;)\]])\^\{(\d{1,3}(?:\s*[,–-]\s*\d{1,3})*)\}", r"\1[\2]", text)


def to_markdown(elements: list[dict], figures: dict[str, dict], lang: str) -> tuple[str, list[str], set[str]]:
    out: list[str] = []
    used: set[str] = set()
    refs: list[str] = []
    for el in elements:
        k = el["kind"]
        if k == "heading":
            out.append(f"{'#' * el['level']} {el['text']}")
        elif k == "para":
            out.append(citation_sups(el["text"]))
        elif k == "caption":
            num = el["num"]
            text = el["text"]
            m = CAPTION_RE.match(text)
            body = text[m.end():].lstrip(" .:：") if m else text
            label = f"**图 {num}.** {body}" if lang == "zh" else f"**Fig. {num}.** {body}"
            fig = figures.get(num)
            if fig and num not in used:
                used.add(num)
                out.append(f"![[{fig['file']}|700]]\n\n{label}")
            else:
                out.append(label)
        elif k == "table":
            cap = el["caption"]
            if cap:
                m = TABLE_CAP_RE.match(cap)
                body = cap[m.end():].lstrip(" .:：") if m else cap
                out.append(f"**{'表' if lang == 'zh' else 'Table'} {el['num']}.** {body}")
            if el["md"]:
                out.append(el["md"])
            elif cap:
                out.append(f"<!--TABLE {el['num']} p{el['page']}: 版面未抽出表体，照 pages/p{el['page']}.png 重建-->")
        elif k == "equation":
            out.append(f"<!--EQ ({el['num']}) p{el['page']}-->\n{el['text']}")
        elif k == "refs":
            refs = el["lines"]
    text = "\n\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text, refs, used


# ----------------------------------------------------------------------------- 按栏切分的干净正文（v2「先排版」的原料）

LIGATURES = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl"}
KEEP_HYPHEN = {
    "non", "fluid", "particle", "two", "one", "three", "self", "quasi", "semi", "multi", "inter", "intra",
    "cross", "co", "pre", "post", "well", "sub", "super", "micro", "macro", "ultra", "anti", "half", "full",
    "long", "short", "high", "low", "large", "small", "time", "space", "real", "wall", "gas", "solid", "liquid",
    "free", "in", "coarse", "fine", "grid", "drag", "shape", "size", "density", "volume", "fixed", "finite",
    "lattice", "single", "double", "mass", "stress", "second", "first", "data", "field", "model", "based",
    "depth", "flow", "water", "debris", "rain", "soil", "rock", "ice", "snow", "land", "sea", "wind", "quasi",
}
COL_CAP = re.compile(r"^(?:Fig\.?|Figure|FIGURE|图)\s*[A-Z]?\d{1,3}", re.I)
COL_TAB = re.compile(r"^(?:Table|TABLE|表)\s*[A-Z]?\d{1,3}", re.I)
COL_EQNUM = re.compile(r"[(（]\s*(\d{1,3}[a-z]?)\s*[)）]")


def columns_markdown(doc: pymupdf.Document) -> tuple[str, dict]:
    """把每页文本按「整幅行 / 左栏 / 右栏」切开，再按栏拼段落：不猜标题层级、不猜图表位置，只给 AI 一份读得通的原料。

    每页先输出整幅（跨栏）行，再左栏、再右栏；栏内按缩进 / 行距 / 样式切段并接回断词。
    行首标记（供排版时快速定位，不是结论）：
        [BOLD] 整行粗体（多半是标题）        [ITAL] 整行斜体（多半是小标题）
        [CAP]  以 Fig./Figure/图 N 开头       [TAB] 以 Table/表 N 开头
        [MATH] 数学字体占多数（公式，字符多半是乱码，照页面图转写）
        [small] 小字（页眉页脚、脚注、表体、参考文献）  [BIG] 大字（题名）
    上下标写成 `^{…}` / `_{…}`。返回 (markdown, 统计)。
    """
    pages_spans = []
    vocab: set[str] = set()
    for page in doc:
        d = page.get_text("dict")
        spans = []
        for b in d["blocks"]:
            if b.get("type") != 0:
                continue
            for l in b["lines"]:
                for s in l["spans"]:
                    t = s["text"]
                    for k, v in LIGATURES.items():
                        t = t.replace(k, v)
                    if not t.strip():
                        continue
                    x0, y0, x1, y1 = s["bbox"]
                    spans.append(dict(x0=x0, y0=y0, x1=x1, y1=y1, t=t, size=s["size"],
                                      bold=bool(s["flags"] & 16) or bool(BOLD_FONT.search(s["font"])),
                                      italic=bool(s["flags"] & 2), font=s["font"], by=s["origin"][1]))
                    for w in re.findall(r"[A-Za-z]+", t):
                        vocab.add(w.lower())
        pages_spans.append((page.rect.width, spans))

    sizes = Counter(round(s["size"], 1) for _, sp in pages_spans for s in sp if s["size"] > 3)
    body = sizes.most_common(1)[0][0] if sizes else 10.0
    small = body * 0.82
    stats = {"bodyFontSize": body, "pages": len(pages_spans), "twoColumnPages": 0,
             "hintFigures": set(), "hintTables": set(), "hintEquations": set()}

    def cjk_like(ch: str) -> bool:
        return bool(ch) and (is_cjk(ch) or "\u3000" <= ch <= "\u303f" or "\uff00" <= ch <= "\uffef")

    def render(sps: list[dict]) -> str:
        txt = ""
        prev_x1 = None
        for s in sps:
            t = s["t"].strip()
            sc = s.get("script", "")
            if sc == "sup":
                t = "^{" + t + "}"
            elif sc == "sub":
                t = "_{" + t + "}"
            if prev_x1 is not None and s["x0"] - prev_x1 > 1.0 and t and txt \
                    and not (cjk_like(txt[-1]) or cjk_like(t[0])):
                txt += " "
            txt += t
            prev_x1 = s["x1"]
        txt = despace(" ".join(txt.split()))
        # `x^{2}_{p}` 相邻碎片合并；`C_{D}` 前后多余空格去掉；中文标点两侧不留空格
        txt = re.sub(r"\s+([_^]\{)", r"\1", txt)
        txt = re.sub(r"\s*([，。；：！？、（）《》「」【】])\s*", r"\1", txt)
        return txt

    def tag(sps: list[dict], txt: str) -> str:
        big = [s for s in sps if not s.get("script")]
        if not big:
            return ""
        n_math = sum(1 for s in big if MATH_FONT.search(s["font"]))
        # Wiley 等正文用 STIX 字体也会命中 MATH_FONT：整句英文（≥4 个 3 字母以上的词、无数学符号）不算公式
        wordy = len(re.findall(r"[A-Za-z]{3,}", txt)) >= 4 and not MATHY.search(txt) and not COL_EQNUM.search(txt[-8:])
        if COL_CAP.match(txt) and not CAPTION_VERB.match(txt):
            return "[CAP] "
        if COL_TAB.match(txt) and not TABLE_VERB.match(txt):
            return "[TAB] "
        if n_math >= max(1, len(big) // 2) and not wordy:
            return "[MATH] "
        if all(s["bold"] for s in big) and len(txt) < 140:
            return "[BOLD] "
        if all(s["italic"] for s in big) and len(txt) < 140:
            return "[ITAL] "
        if all(s["size"] < body - 1.0 for s in big):
            return "[small] "
        if all(s["size"] > body + 1.5 for s in big):
            return "[BIG] "
        return ""

    out: list[str] = []
    for pno, (W, spans) in enumerate(pages_spans, start=1):
        mid = W / 2
        spans.sort(key=lambda s: (s["by"], s["x0"]))
        lines: list[dict] = []
        for s in spans:
            if lines and abs(lines[-1]["by"] - s["by"]) <= 1.6:
                lines[-1]["spans"].append(s)
            else:
                lines.append(dict(by=s["by"], spans=[s]))
        # 只含小字的「行」多半是上下标：并回最近的正常行
        normal = [ln for ln in lines if any(s["size"] >= small for s in ln["spans"])]
        for ln in lines:
            if ln in normal:
                continue
            best = None
            for n in normal:
                dy = ln["by"] - n["by"]
                if -4.5 <= dy <= 3.5:
                    lo = min(s["x0"] for s in n["spans"]) - 20
                    hi = max(s["x1"] for s in n["spans"]) + 20
                    if all(lo <= s["x0"] <= hi for s in ln["spans"]) and (best is None or abs(dy) < abs(best[0])):
                        best = (dy, n)
            if best is None:
                normal.append(ln)
                continue
            dy, n = best
            for s in ln["spans"]:
                s["script"] = "sup" if dy < -0.8 else ("sub" if dy > 0.8 else "")
                n["spans"].append(s)
        lines = sorted(normal, key=lambda l: l["by"])
        for ln in lines:
            ln["spans"].sort(key=lambda s: s["x0"])

        def line_boundaries() -> list[float | None]:
            """给每条基线找它所在版面带的栏沟：看上下各 8 行的墨迹覆盖，页宽 20%–80% 之间几乎没人穿过（≤1 行）、
            宽 ≥8pt、两侧各至少 3 行有字的空白竖带就是栏沟。整页单栏 / 首页「信息栏 + 摘要」/ 正文双栏 各带各的分界；
            没有栏沟的行返回 None（整幅行）。"""
            n = len(lines)
            step = 2.0
            nb = int(W / step) + 2
            ivs = [[(int(s["x0"] / step), int(s["x1"] / step) + 1) for s in ln["spans"]] for ln in lines]
            lo_x, hi_x = int(0.2 * W / step), int(0.8 * W / step)
            res: list[float | None] = []
            for i in range(n):
                a, b = max(0, i - 8), min(n, i + 9)
                diff = [0] * (nb + 1)
                for j in range(a, b):
                    for x0, x1 in ivs[j]:
                        diff[max(0, x0)] += 1
                        diff[min(nb, x1)] -= 1
                cov = []
                c = 0
                for v in diff[:nb]:
                    c += v
                    cov.append(c)
                runs: list[tuple[int, int]] = []
                x = lo_x
                while x < hi_x:
                    if cov[x] <= 1:
                        y = x
                        while y < hi_x and cov[y] <= 1:
                            y += 1
                        if (y - x) * step >= 8:
                            runs.append((x, y))
                        x = y
                    x += 1
                if not runs:
                    res.append(None)
                    continue
                # 真栏沟两侧都有字；有多条候选时取最靠页中线的（表格列间空、右栏空白区都比它偏）
                scored: list[tuple[float, float, float]] = []
                for x0, x1 in runs:
                    gx0, gx1 = x0 * step, x1 * step
                    left_lines = sum(1 for j in range(a, b) if any(s["x1"] <= gx0 + 1 for s in lines[j]["spans"]))
                    right_lines = sum(1 for j in range(a, b) if any(s["x0"] >= gx1 - 1 for s in lines[j]["spans"]))
                    if left_lines >= 3 and right_lines >= 3:
                        scored.append((abs((gx0 + gx1) / 2 - W / 2), -(gx1 - gx0), (gx0 + gx1) / 2))
                if scored:
                    scored.sort()
                    res.append(scored[0][2])
                    continue
                # 只有一侧有字（另一栏是整幅图）：拿最宽的空白带当分界，让这些行仍按栏归类
                x0, x1 = max(runs, key=lambda r: r[1] - r[0])
                gx = (x0 + x1) / 2 * step
                left_lines = sum(1 for j in range(a, b) if any(s["x1"] < gx for s in lines[j]["spans"]))
                right_lines = sum(1 for j in range(a, b) if any(s["x0"] > gx for s in lines[j]["spans"]))
                res.append(gx if (left_lines >= 3 or right_lines >= 3) else None)
            return res

        def split_lines(bounds: list[float | None]) -> list[tuple]:
            """每条基线 → 整幅(F) 或 左(L)/右(R)。没有栏沟的行是 F；跨过栏沟的 span、或左右两半之间没有真空隙（<6pt）的算整幅。
            返回 (baseline, kind, x0, x1, text, tag)。"""
            res: list[tuple] = []
            for ln, boundary in zip(lines, bounds):
                sps = ln["spans"]
                if boundary is None:
                    spanning, left, right = sps, [], []
                else:
                    spanning = [s for s in sps if s["x0"] < boundary - 3 and s["x1"] > boundary + 3]
                    left = [s for s in sps if s["x1"] <= boundary + 3 and s not in spanning]
                    right = [s for s in sps if s["x0"] >= boundary - 3 and s not in spanning]
                gutter = (min(s["x0"] for s in right) - max(s["x1"] for s in left)) if (left and right) else 1e9
                if spanning or (left and right and gutter < 6):
                    txt = render(sps)
                    res.append((ln["by"], "F", min(s["x0"] for s in sps), max(s["x1"] for s in sps), txt, tag(sps, txt)))
                else:
                    if left:
                        txt = render(left)
                        res.append((ln["by"], "L", min(s["x0"] for s in left), max(s["x1"] for s in left), txt, tag(left, txt)))
                    if right:
                        txt = render(right)
                        res.append((ln["by"], "R", min(s["x0"] for s in right), max(s["x1"] for s in right), txt, tag(right, txt)))
            return res

        items = split_lines(line_boundaries())
        if sum(1 for it in items if it[1] in "LR") > 10:
            stats["twoColumnPages"] += 1

        def col_left(kind: str) -> float:
            xs = sorted(it[2] for it in items if it[1] == kind)
            return xs[len(xs) // 10] if xs else 0.0

        def col_right(kind: str) -> float:
            xs = sorted(it[3] for it in items if it[1] == kind)
            return xs[-1 - len(xs) // 10] if xs else 0.0

        lefts = {k: col_left(k) for k in "FLR"}
        rights = {k: col_right(k) for k in "FLR"}
        HEAD_TAGS = ("[BOLD]", "[ITAL]", "[BIG]")

        def flush(buf: list[tuple], kind: str) -> list[str]:
            """栏内按行拼段。断段依据：大行距 / 样式标记变化 / 图注表题 / 上一行没排满（齐行排版的段末）/ 首行缩进。"""
            paras: list[dict] = []
            cur = None
            prev = None
            width = max(rights[kind] - lefts[kind], 1.0)
            for it in buf:
                by, _, x0, x1, txt, tg = it
                new_para = cur is None
                if cur is not None:
                    if by - prev[0] > 1.75 * body:
                        new_para = True
                    if tg != prev[5] and (tg or prev[5]):
                        new_para = True
                    if tg.startswith(("[CAP]", "[TAB]")):
                        new_para = True
                    heading_pair = tg.startswith(HEAD_TAGS) and prev[5].startswith(HEAD_TAGS)
                    ragged_prev = prev[3] < rights[kind] - 0.12 * width
                    if ragged_prev and not heading_pair and not prev[5].startswith("[MATH]") and not tg.startswith("[MATH]"):
                        new_para = True
                    # 首行缩进：双栏正文左边齐、看绝对缩进；整幅行左边不齐（题名/摘要/作者各有各的边），只看相对上一行的缩进
                    if kind in "LR" and x0 > lefts[kind] + 4.5 and not prev[5].startswith("[MATH]"):
                        new_para = True
                    if kind == "F" and x0 > prev[2] + 4.5 and not prev[5].startswith("[MATH]") and not heading_pair:
                        new_para = True
                if new_para:
                    cur = {"tag": tg, "txt": txt}
                    paras.append(cur)
                else:
                    a = cur["txt"]
                    if a.endswith("-") and txt and txt[0].islower():
                        stem = re.findall(r"[A-Za-z]+$", a[:-1])
                        head = re.findall(r"^[A-Za-z]+", txt)
                        if stem and head and ((stem[0] + head[0]).lower() in vocab or stem[0].lower() not in KEEP_HYPHEN):
                            cur["txt"] = a[:-1] + txt
                        else:
                            cur["txt"] = a + txt
                    elif a and is_cjk(a[-1]) and txt and is_cjk(txt[0]):
                        cur["txt"] = a + txt
                    else:
                        cur["txt"] = a + " " + txt
                prev = it
            res = []
            for p in paras:
                res.append(f'{p["tag"]}{p["txt"]}')
                m = COL_CAP.match(p["txt"])
                if p["tag"].startswith("[CAP]") and m:
                    mm = re.search(r"\d{1,3}", m.group(0))
                    if mm:
                        stats["hintFigures"].add(int(mm.group(0)))
                m = COL_TAB.match(p["txt"])
                if p["tag"].startswith("[TAB]") and m:
                    mm = re.search(r"\d{1,3}", m.group(0))
                    if mm:
                        stats["hintTables"].add(int(mm.group(0)))
                if p["tag"].startswith("[MATH]") or (MATHY.search(p["txt"]) and COL_EQNUM.search(p["txt"][-8:])):
                    for mm in COL_EQNUM.finditer(p["txt"]):
                        n = re.match(r"\d{1,3}", mm.group(1))
                        if n:
                            stats["hintEquations"].add(int(n.group(0)))
            return res

        out.append(f"\n<!-- ===== p{pno} ===== -->\n")
        F: list[tuple] = []
        L: list[tuple] = []
        R: list[tuple] = []
        for it in sorted(items, key=lambda x: (x[0], x[1])):
            if it[1] == "F":
                # 从双栏切回整幅：先把上面两栏按左→右吐出来
                if L or R:
                    out.extend(flush(F, "F")); F = []
                    out.extend(flush(L, "L")); L = []
                    out.extend(flush(R, "R")); R = []
                F.append(it)
            else:
                # 从整幅切到双栏：先吐整幅段落
                if F:
                    out.extend(flush(F, "F")); F = []
                (L if it[1] == "L" else R).append(it)
        out.extend(flush(F, "F"))
        out.extend(flush(L, "L"))
        out.extend(flush(R, "R"))
    for k in ("hintFigures", "hintTables", "hintEquations"):
        stats[k] = sorted(stats[k])
    return "\n\n".join(out).strip() + "\n", stats
