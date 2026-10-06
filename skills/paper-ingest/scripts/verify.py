#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify.py — 子代理产出 out/ 的确定性校验闸门：图一个不漏、公式一个不漏、表一个不漏、格式不违约。

    python verify.py --work <workdir>            # 打印 JSON；有 error 退出码 1，否则 0
    python verify.py --work <workdir> --quiet    # 只打印一行结论

「应有多少张图 / 多少条公式 / 多少张表」不信草稿、不信子代理，直接从 PDF 文本重新数：
  - 图：fulltext.txt 里行首的 `Fig. N` / `FIGURE N` / `图 N`（Wiley 的 `F I G U R E 1 4` 先合并）∪ stats.figureList
  - 公式：行尾 `(N)` 且该行含数学符号 ∪ 草稿里的 `<!--EQ (N)-->` 标记
  - 表：行首 `Table N` / `TA B L E N` / `表 N`
  编号是连续的，min..max 之间缺号一律当 error。子代理确认 PDF 里确实没有某编号时，
  写 out/verify_overrides.json：{"figures":[N],"equations":[N],"tables":[N],"reason":"…"}，本脚本会照登记并放行。
结果写到 <workdir>/verify.json，finish.py 会先跑本脚本，有 error 不装配。
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

CAPTION_VERB = re.compile(
    r"^\s*(?:Fig\.?|Figure|图)\s*[A-Z]?\d{1,3}[a-z]?\s*[.:]?\s*(?:(?:shows?|illustrates?|depicts?|displays?|presents?|"
    r"gives?|compares?|demonstrates?|plots?|summarizes?|indicates?|reveals?|provides?|reports?|and|to|in|of|for|is|are|"
    r"was|were|also)\b|中|所示|给出|显示|为|展示|反映|表明|可见|可以看出|说明|对比|描述|绘出|示出)", re.I)
TABLE_VERB = re.compile(r"^\s*(?:Table|表)\s*[A-Z]?\d{1,3}\s*[.:]?\s*(?:(?:shows?|lists?|summarizes?|presents?|gives?|compares?|and|to|in|of|for|is|are)\b|中|所示|给出|列出|统计|汇总|为)", re.I)
ITEM_NUMBER = r"(?:[A-Z]\.?)?\d{1,3}(?:\.\d{1,3})*"
FIG_LINE = re.compile(rf"^\s*(?:Fig\.?|Figure|FIG\.?|图)\s*({ITEM_NUMBER})(?![\d.]\d)\b[a-z]?\s*[.:：]?\s*(?=\S)", re.I)
TABLE_LINE = re.compile(rf"^\s*(?:Table|TABLE|表)\s*({ITEM_NUMBER})(?![\d.]\d)\b\s*[.:：]?\s*(?=\S)", re.I)
EQ_LINE = re.compile(r"[(（]\s*((?:[A-Z]\.?)?\d{1,3}(?:\.\d{1,3})*[′']?)[a-z]?\s*[)）]\s*$")
MATHY = re.compile(r"[=+−×÷∑∫∂∇√≈≤≥±∞αβγδεζηθκλμνξπρστυφχψωΓΔΘΛΞΠΣΦΨΩ]|\^|_")
SPACED = re.compile(r"\b((?:[A-Za-z]\s){2,}[A-Za-z])\b")
EMBED = re.compile(r"!\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]")
WIKILINK = re.compile(r"(?<!!)\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]")
EN_CAP = re.compile(rf"^\*\*(?:Fig\.?|Figure)\s*({ITEM_NUMBER})[a-z]?\.?\*\*", re.I)
ZH_CAP = re.compile(rf"^\*\*图\s*({ITEM_NUMBER})[.。．]?\*\*")
EN_TAB = re.compile(rf"^\*\*Table\s*({ITEM_NUMBER})\.?\*\*", re.I)
ZH_TAB = re.compile(rf"^\*\*表\s*({ITEM_NUMBER})[.。．]?\*\*")
TAG = re.compile(r"\\tag\{((?:[A-Z]\.?)?\d{1,3}(?:\.\d{1,3})*[′']?)[a-z]?\}")
LEFTOVER = re.compile(r"<!--\s*(EQ|TABLE|ABSTRACT|REFS)\b")
PUA = re.compile(r"[\ue000-\uf8ff\ufffd\ufffe\U0001d400-\U0001d7ff]")
PDF_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)
SHELL_LEFTOVER = re.compile(r"Grant/Award Number|Funding information|\bK\sE\sY\sW\sO\sR\sD\sS\b|Received:? \d|Accepted:? \d|Correspondence:|This is an open access", re.I)
SECTION_MIN_RATIO = 0.15   # 某节中文字符数 / 英文字符数 低于此值 = 概括不是全译（忠实全译通常 0.22–0.35）
SECTION_MAX_RATIO = 1.0    # 高于此值 = 中文比英文还长，是填充/重复不是译文（0.6 以上先警告）
TOTAL_MIN_RATIO = 0.18
EN_MIN_RATIO = 0.7         # en.md 字符数 / 草稿正文字符数 低于此值 = 缩写改写（忠实重排通常 0.85–1.0）
# 「堆放节」：不带编号、名字就是 公式/图/表 之类的节，里面塞 ≥2 条公式或图表 = 没放回原文位置
DUMP_HEADING = re.compile(r"^(?:equations?|formulas?|equation\s+list|list\s+of\s+equations|figures?|figure\s+list|list\s+of\s+figures|tables?|table\s+list|"
                          r"公式|公式列表|公式汇总|全部公式|图|图表|图片|图列表|附图|附表|表格|表|表列表)\s*$", re.I)
# 偷工的元说明：正文里出现这些话 = 有段落没译
META_PHRASE = re.compile(r"其余各节|其余章节|其余部分|余下各节|以下保留|后续章节从略|从略|不再逐段|不再逐句|篇幅所限|见英文原文|按英文正文|逐项对应翻译|此处略|（略）|\(略\)|略去不译|省略不译|不再赘述译文|结构化摘译|中文精读版|摘要版译文")
ZH_PUNCT = "，。；：！？、（）「」『』《》〈〉…—,.;:!?()[]"
COMMON_EN = re.compile(r"\b(?:the|of|and|is|are|in|to|by|with|for|that)\b", re.I)
NOTES_REQUIRED = ("# 🎓 学习卡", "## 📌 摘要要点", "## ❓ 问答", "# 🔬 深度分析", "## 研究问题", "## 方法概述",
                  "### 关键公式", "## 实验结果", "## 我的综合评价", "# ✍️ 写作逻辑", "## 论证骨架")


def utf8() -> None:
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def rd(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def despace(line: str) -> str:
    return SPACED.sub(lambda m: m.group(1).replace(" ", ""), line)


def cjk_count(text: str) -> int:
    return sum(1 for ch in text if "一" <= ch <= "鿿")


def strip_math(text: str) -> str:
    text = re.sub(r"\$\$[\s\S]*?\$\$", " ", text)
    text = re.sub(r"\$[^$\n]+\$", " ", text)
    text = re.sub(r"`[^`\n]*`", " ", text)
    return text


def equation_id(raw: str) -> int | str:
    """保留分节和附录公式号；传统整数编号保持既有 JSON 类型。"""
    prime = raw[-1:] if raw.endswith(("′", "'")) else ""
    raw = raw[:-1] if prime else raw
    prefix = raw[0] if raw[0].isalpha() else ""
    separator = "." if prefix and raw[len(prefix):].startswith(".") else ""
    parts = [str(int(part)) for part in raw[len(prefix):].lstrip(".").split(".")]
    return prefix + separator + ".".join(parts) + prime if prefix or len(parts) > 1 or prime else int(parts[0])


def number_key(num: int | str) -> tuple[int, ...]:
    raw = str(num)
    prime = raw.endswith(("′", "'"))
    raw = raw[:-1] if prime else raw
    prefix = raw[0] if raw[0].isalpha() else ""
    return (ord(prefix) if prefix else 0, *(int(part) for part in raw[len(prefix):].lstrip(".").split(".")), int(prime))


def consecutive(nums: set[int | str]) -> tuple[set[int | str], list[int | str]]:
    """返回 (应有编号集合, 缺号列表)：编号连续，min..max 之间缺的算漏。"""
    if not nums:
        return set(), []
    primed = {n for n in nums if str(n).endswith(("′", "'"))}
    if primed:
        base = (nums - primed) | {equation_id(str(n)[:-1]) for n in primed}
        full, missing = consecutive(base)
        return full | primed, missing
    if any("." in str(num) or str(num)[0].isalpha() for num in nums):
        groups: dict[str, set[int]] = {}
        for num in nums:
            raw = str(num)
            m = re.match(r"^(.*?)(\d+)$", raw)
            groups.setdefault(m.group(1), set()).add(int(m.group(2)))
        full, missing = set(), []
        for prefix, group in groups.items():
            group_full, group_missing = consecutive(group)
            label = lambda n: equation_id(f"{prefix}{n}") if prefix else n
            full.update(label(n) for n in group_full)
            missing.extend(label(n) for n in group_missing)
        return full, sorted(missing, key=number_key)
    lo, hi = min(nums), max(nums)
    lo = 1 if lo <= 3 else lo  # 通常从 1 编起；正文第一张图没抽到时也要追
    full = set(range(lo, hi + 1))
    return full, sorted(full - nums)


def expected_from_pdf(fulltext: str, columns: str, stats: dict) -> dict[str, set[int | str]]:
    """脚本在 PDF 文本里正则粗数出来的编号——v2 里只做交叉提醒，不当对账标准（畸形 PDF 上会少数很多）。"""
    figs: set[int | str] = set()
    tabs: set[int | str] = set()
    eqs: set[int | str] = set()
    prev = ""
    for raw in fulltext.splitlines():
        line = despace(raw.strip())
        if not line:
            continue
        m = FIG_LINE.match(line)
        if m and len(line) > 6 and not CAPTION_VERB.match(line):
            figs.add(equation_id(m.group(1)))
        m = TABLE_LINE.match(line)
        if m and len(line) > 6 and not TABLE_VERB.match(line):
            tabs.add(equation_id(m.group(1)))
        m = EQ_LINE.search(line)
        if m:
            # 「公式体 (N)」同一行，或中文刊「（N）」单独一行紧跟公式体
            head = line[: m.start()] or prev
            if MATHY.search(head) and len(head) < 400 and not re.search(r"\b(?:the|and|of|that|which)\b", head, re.I):
                eqs.add(equation_id(m.group(1)))
        prev = line
    hints = stats.get("columns", {})
    for line in columns.splitlines():
        if line.startswith("[CAP] "):
            m = FIG_LINE.match(line[6:])
            if m:
                figs.add(equation_id(m.group(1)))
        elif line.startswith("[TAB] "):
            m = TABLE_LINE.match(line[6:])
            if m:
                tabs.add(equation_id(m.group(1)))
        elif line.startswith("[MATH] "):
            for m in re.finditer(r"[(（]\s*((?:[A-Z]\.?)?\d{1,3}(?:\.\d{1,3})*[′']?)[a-z]?\s*[)）]", line):
                eqs.add(equation_id(m.group(1)))
    if not any("." in str(n) for n in figs):
        figs |= {int(n) for n in hints.get("hintFigures", []) if str(n).isdigit()}
    if not any("." in str(n) for n in tabs):
        tabs |= {int(n) for n in hints.get("hintTables", []) if str(n).isdigit()}
    if not any("." in str(n) for n in eqs):
        eqs |= {int(n) for n in hints.get("hintEquations", []) if str(n).isdigit()}
    # 正文里「(3)」这类编号列表会被误认成公式号：只接受和已知公式号连得上的
    if eqs and all(isinstance(n, int) for n in eqs):
        core = sorted(eqs)
        keep: set[int] = set()
        for n in core:
            if n == 1 or (n - 1) in eqs or (n + 1) in eqs:
                keep.add(n)
        eqs = keep or eqs
    return {"figures": figs, "tables": tabs, "equations": eqs}


def expected_from_layout(work: Path, errors: list[str]) -> dict[str, set[int | str]] | None:
    """v2 的对账标准：AI 排版核出的 out/layout.json。没有就返回 None（报 error）。"""
    p = work / "out" / "layout.json"
    if not p.exists():
        errors.append("缺 out/layout.json（排版清单：headings / figures / tables / equations）——先排版再裁图、翻译、校验")
        return None
    try:
        data = json.loads(rd(p) or "{}")
    except Exception as exc:
        errors.append(f"out/layout.json 解析失败：{exc}")
        return None
    out: dict[str, set[int | str]] = {}
    for kind, key in (("figures", "num"), ("tables", "num"), ("equations", "num")):
        nums: set[int | str] = set()
        for item in data.get(kind, []) or []:
            raw = item.get(key) if isinstance(item, dict) else item
            pattern = rf"^\s*({ITEM_NUMBER}[′']?)" if kind == "equations" else rf"^\s*({ITEM_NUMBER})"
            m = re.match(pattern, str(raw))
            if m:
                nums.add(equation_id(m.group(1)))
        out[kind] = nums
    if not data.get("headings"):
        errors.append("layout.json: headings 为空——排版清单要列出标题树（level / title / page）")
    for kind in ("figures", "tables"):
        for item in data.get(kind, []) or []:
            if isinstance(item, dict) and not str(item.get("caption") or item.get("title") or "").strip():
                errors.append(f"layout.json: {kind} {item.get('num')} 缺图注/表题原文（裁图靠它定位）")
                break
    return out


def check_captions(md: str, cap_re: re.Pattern, expected: set[int], what: str, errors: list[str], file: str) -> tuple[set[int], set[int]]:
    """返回 (有图注的编号, 图注上方有嵌图的编号)。"""
    lines = md.splitlines()
    have: set[int] = set()
    embedded: set[int] = set()
    for i, line in enumerate(lines):
        m = cap_re.match(line.strip())
        if not m:
            continue
        n = equation_id(m.group(1))
        have.add(n)
        window = [l for l in lines[max(0, i - 4): i] if l.strip()]
        if any(EMBED.search(l) for l in window[-2:]):
            embedded.add(n)
    for n in sorted(expected - have, key=number_key):
        errors.append(f"{file}: 缺 {what} {n} 的图注（`**{'图' if '图' in what else 'Fig.'} {n}.**`）")
    for n in sorted((expected & have) - embedded, key=number_key):
        errors.append(f"{file}: {what} {n} 的图注上方没有 `![[…]]` 嵌图")
    return have, embedded


def check_caption_files(md: str, cap_re: re.Pattern, files: dict[str, str], errors: list[str], name: str) -> None:
    """Match each caption to its reviewed image; equal counts cannot catch swaps."""
    seen: Counter = Counter()
    lines = md.splitlines()
    for i, line in enumerate(lines):
        cap = cap_re.match(line.strip())
        if not cap:
            continue
        num = cap.group(1)
        seen[num] += 1
        if num not in files:
            errors.append(f"{name}: 图 {num} 没有对应的裁图记录")
            continue
        preceding = [s for s in lines[max(0, i - 4):i] if s.strip()]
        actual = EMBED.findall(preceding[-1]) if preceding else []
        if actual != [files[num]]:
            errors.append(f"{name}: 图 {num} 嵌图 {actual} 与已核对文件 {files[num]} 不符")
    for num, total in seen.items():
        if total > 1:
            errors.append(f"{name}: 图 {num} 图注重复 {total} 次")


def check_source_quality(work: Path, en: str, zh: str, expected: set[int], lang: str,
                         errors: list[str], counts: dict) -> None:
    """New jobs require sealed source review and explicit per-image approval.

    The seal records a visual review; it cannot infer formula or crop semantics.
    """
    from translation import check_source_review, compare_protected
    from figtools import review_errors

    errors.extend(check_source_review(work))
    errors.extend(review_errors(work))
    try:
        records = json.loads(rd(work / "figcut.json") or "{}").get("figures", [])
        files = {str(f["num"]): str(f.get("file", "")) for f in records}
        if set(files) != {str(n) for n in expected}:
            errors.append("figcut.json: 图号与 layout.json 应有清单不一致")
    except (ValueError, KeyError, TypeError) as exc:
        errors.append(f"figcut.json: 无法核对图片记录：{exc}")
        files = {}
    if lang == "en":
        check_caption_files(en, EN_CAP, files, errors, "en.md")
        if en and zh:
            errors.extend(compare_protected(en, zh))
    check_caption_files(zh, ZH_CAP, files, errors, "zh.md")
    counts["qualityPolicy"] = "source-reviewed-v1"


def check_tables(md: str, tab_re: re.Pattern, expected: set[int], errors: list[str], file: str, label: str) -> set[int]:
    lines = md.splitlines()
    built: set[int] = set()
    have: set[int] = set()
    for i, line in enumerate(lines):
        m = tab_re.match(line.strip())
        if not m:
            continue
        n = equation_id(m.group(1))
        have.add(n)
        following = [l for l in lines[i + 1: i + 6] if l.strip()]
        if following and following[0].lstrip().startswith("|"):
            built.add(n)
    for n in sorted(expected - have, key=number_key):
        errors.append(f"{file}: 缺 {label} {n} 的表题（`**{label} {n}.**`）")
    for n in sorted((expected & have) - built, key=number_key):
        errors.append(f"{file}: {label} {n} 表题后面没有 Markdown 表（下一段应以 `|` 开头）")
    return built


def check_math(md: str, file: str, errors: list[str], warnings: list[str]) -> None:
    if md.count("$$") % 2:
        errors.append(f"{file}: `$$` 数量为奇数（{md.count('$$')}），有公式块没闭合")
    for i, block in enumerate(re.findall(r"\$\$([\s\S]*?)\$\$", md), start=1):
        if block.count("{") != block.count("}"):
            tag = TAG.search(block)
            errors.append(f"{file}: 第 {i} 个 $$ 块花括号不配对" + (f"（\\tag{{{tag.group(1)}}}）" if tag else ""))
        if "\\tag" in block and block.count("\\tag") > 1:
            warnings.append(f"{file}: 第 {i} 个 $$ 块里有多个 \\tag，应拆成多条公式")
    plain = strip_math(md)
    stray = re.findall(r"[A-Za-z0-9)\]][_^]\{[^}]{1,12}\}", plain)
    if len(stray) >= 10:
        errors.append(f"{file}: 有 {len(stray)} 处 `_{{}}`/`^{{}}` 上下标裸露在 $ 之外（例：{stray[0]}）——上标引文改成 `[N]`，变量包进 $…$")
    elif len(stray) >= 3:
        warnings.append(f"{file}: 有 {len(stray)} 处 `_{{}}`/`^{{}}` 上下标裸露在 $ 之外（例：{stray[0]}），应包进 $…$")
    for m in LEFTOVER.finditer(md):
        errors.append(f"{file}: 还留着脚本标记 `<!--{m.group(1)} …-->`，应替换成真正内容后删除")
    bad = PUA.findall(md)
    if bad:
        lines = [i + 1 for i, l in enumerate(md.splitlines()) if PUA.search(l)]
        errors.append(f"{file}: 有 {len(bad)} 个 PDF 乱码字符（私有区/替换符/数学字母），行 {lines[:8]}，照页面图改成 LaTeX 或正确字符")
    controls = PDF_CONTROL.findall(md)
    if controls:
        lines = [i + 1 for i, l in enumerate(md.splitlines()) if PDF_CONTROL.search(l)]
        errors.append(f"{file}: 有 {len(controls)} 个 PDF 控制字符，行 {lines[:8]}，须对照页面图恢复公式或正文；不能仅删除字符留下乱码或重复公式")
    shells = [m.group(0) for m in SHELL_LEFTOVER.finditer(plain)]
    if shells:
        warnings.append(f"{file}: 期刊壳没删净（{sorted(set(shells))[:4]}）——基金号/收稿日期/通讯作者/拉开的 KEYWORDS 之类不该出现在正文")


def check_table_cells(md: str, file: str, errors: list[str]) -> None:
    """表格行里的裸 `<` / `>`（含 `<br>`）会把前端表格崩掉——口径与 wenshu-pro/scripts/web_lint.py 完全一致。
    Example2024 第一次过了 verify 却在 web_lint 报 2 警（`<0.0001`、`<br>`），所以把这条提前到闸门里。"""
    bad: list[int] = []
    for i, line in enumerate(md.splitlines(), start=1):
        if not line.lstrip().startswith("|"):
            continue
        cleaned = line.replace("\\lt", "").replace("\\gt", "").replace("&lt;", "").replace("&gt;", "")
        if re.search(r"(?<!\\)[<>]", cleaned):
            bad.append(i)
    if bad:
        errors.append(f"{file}: 第 {bad[:8]} 行等 {len(bad)} 个表格行含裸 `<`/`>`（会崩表）——不等号写 `\\lt`/`\\gt`；单元格内不许用 `<br>` 换行，改用「；」分隔或拆成多行")


def sections(md: str) -> dict[str, str]:
    """按 `## ` 切节：键 = 编号（`2.1`）或规范化标题（abstract/摘要），值 = 该节正文（含其下 ### 子节）。"""
    out: dict[str, str] = {}
    cur = "_front"
    buf: list[str] = []
    for line in md.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            out[cur] = out.get(cur, "") + "\n".join(buf)
            buf = []
            title = m.group(1).strip()
            num = re.match(r"^(\d+(?:\.\d+)*)", title)
            cur = num.group(1) if num else re.sub(r"[^a-z\u4e00-\u9fff]", "", title.lower())
        else:
            buf.append(line)
    out[cur] = out.get(cur, "") + "\n".join(buf)
    return out


def text_len(md: str) -> int:
    body = strip_math(md)
    body = EMBED.sub(" ", body)
    body = re.sub(r"^\*\*(?:Fig\.?|Figure|图|Table|表)[^\n]*$", " ", body, flags=re.M)
    body = re.sub(r"^\|.*$", " ", body, flags=re.M)
    body = re.sub(r"^>.*$", " ", body, flags=re.M)
    return len(re.sub(r"\s+", "", body))


def columns_body(columns: str) -> str:
    """columns.md 里的正文部分：去掉页标记、小字（页眉页脚/脚注/参考文献）、公式乱码行、图注/表题行，只留段落。"""
    keep: list[str] = []
    for line in columns.splitlines():
        s = line.strip()
        if not s or s.startswith("<!--"):
            continue
        if s.startswith(("[small]", "[MATH]", "[CAP]", "[TAB]", "[BIG]")):
            continue
        s = re.sub(r"^\[(?:BOLD|ITAL)\]\s*", "", s)
        keep.append(s)
    return "\n".join(keep)


def check_en_fidelity(en: str, columns: str, errors: list[str], warnings: list[str], counts: dict) -> None:
    """en.md 应是原文的清洁版：字数和 columns.md 正文相当（后者含少量残余噪声，忠实重排通常 0.85–1.05）。"""
    dl, el = text_len(columns_body(columns)), text_len(en)
    counts["lengthRatioEnSource"] = round(el / dl, 2) if dl else None
    if dl and el / dl < EN_MIN_RATIO:
        errors.append(f"en.md 正文字符数只有原文（columns.md 正文）的 {el / dl:.0%}——英文正文必须保留原文每一句（忠实重排应 ≥85%），不许缩写改写；拿 columns.md 的段落当底子逐处修，不要重新写")
    elif dl and el / dl < 0.85:
        warnings.append(f"en.md 正文字符数是原文的 {el / dl:.0%}，偏短，抽查是否有整段漏掉")


def check_fidelity(en: str, zh: str, errors: list[str], warnings: list[str], counts: dict) -> None:
    """逐节比对中英字符数：中文全译约为英文字符数的 22–35%，低于 15% 的节就是概括。"""
    en_sec, zh_sec = sections(en), sections(zh)
    alias = {"abstract": "摘要", "conclusions": "结论", "conclusion": "结论", "introduction": "引言", "acknowledgments": "致谢",
             "acknowledgements": "致谢", "discussion": "讨论", "methods": "方法", "results": "结果"}
    thin: list[str] = []
    fat: list[str] = []
    plump: list[str] = []
    ratios: dict[str, float] = {}
    for key, body in en_sec.items():
        if key == "_front":
            continue
        el = text_len(body)
        if el < 600:
            continue
        zbody = zh_sec.get(key)
        if zbody is None and key in alias:
            zbody = zh_sec.get(alias[key])
        if zbody is None:
            continue  # 缺节由编号章节对账报
        zl = text_len(zbody)
        ratios[key] = round(zl / el, 2)
        if zl / el < SECTION_MIN_RATIO:
            thin.append(f"{key}（中文 {zl} 字 / 英文 {el} 字符 = {zl / el:.0%}）")
        elif zl / el > SECTION_MAX_RATIO:
            fat.append(f"{key}（中文 {zl} 字 / 英文 {el} 字符 = {zl / el:.0%}）")
        elif zl / el > 0.6:
            plump.append(key)
    counts["sectionRatios"] = ratios
    if thin:
        errors.append("zh.md: 以下章节中文明显短于英文，是概括不是逐段全译，必须逐句补全：" + "；".join(thin[:8]) + ("…" if len(thin) > 8 else ""))
    if fat:
        errors.append("zh.md: 以下章节中文字符数比英文还多，忠实全译不可能如此（0.22–0.35），是填充/重复/把英文原文也留在了里面：" + "；".join(fat[:8]))
    elif plump:
        warnings.append(f"zh.md: 章节 {plump[:8]} 中文字符数超过英文 60%，偏长，抽查是否夹带了未删的英文或重复段")
    el, zl = text_len(en), text_len(zh)
    counts["lengthRatioZhEn"] = round(zl / el, 2) if el else None
    if el and zl / el < TOTAL_MIN_RATIO:
        errors.append(f"zh.md 正文字符数只有 en.md 的 {zl / el:.0%}（忠实全译应在 22% 以上），整体是概括而非全译")
    elif el and zl / el < 0.22:
        warnings.append(f"zh.md 正文字符数是 en.md 的 {zl / el:.0%}，偏短，抽查是否有整段漏译")


# ---------------------------------------------------------------------------------------------------------------------
# 第四道对账：真实性与位置。只查结构和数量，模型就会朝结构和数量优化——实测出现过：
#   用连续码位的汉字（一丁丂七…）给每节垫 1800–5000 字凑 zh/en 比值；把 34 条公式、25 张图全部堆进文末 `## 公式` 节；
#   留一排空的 `### 4.1` 标题凑章节对账；图注不译。下面这些检查每一条都对应一次真实的作弊。
# ---------------------------------------------------------------------------------------------------------------------

def prose_paragraphs(md: str) -> list[tuple[int, str]]:
    """按空行切段，去掉标题 / 表格 / 公式块 / 嵌图 / 图注 / 引用块，返回 (起始行号 1-based, 段文)。"""
    out: list[tuple[int, str]] = []
    lines = md.splitlines()
    buf: list[str] = []
    start = 0
    in_math = False

    def flush() -> None:
        nonlocal buf
        text = "\n".join(buf).strip()
        if text and not text.startswith(("#", "|", "![[", ">", "**图", "**表", "**Fig", "**Figure", "**Table", "```", "<!--")):
            out.append((start + 1, text))
        buf = []

    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("$$"):
            if s.count("$$") == 1:
                in_math = not in_math
            flush()
            continue
        if in_math:
            continue
        if not s:
            flush()
            continue
        if not buf:
            start = i
        buf.append(line)
    flush()
    return out


def filler_stats(text: str) -> dict | None:
    """一段中文的三项「像不像人话」指标。实测：真译文 seq≤0.03 / 每百字标点≥4.7 / 前 20 高频字占比≥0.29；
    连续码位填充 seq≥0.94 / 标点 0 / 高频字占比 0.01。"""
    s = re.sub(r"\s+", "", strip_math(text))
    c = [ch for ch in s if "一" <= ch <= "鿿"]
    if len(c) < 60:
        return None
    seq = sum(1 for a, b in zip(s, s[1:]) if abs(ord(b) - ord(a)) == 1) / max(1, len(s) - 1)
    punct = sum(1 for ch in s if ch in ZH_PUNCT) / len(s) * 100
    freq: dict[str, int] = {}
    for ch in c:
        freq[ch] = freq.get(ch, 0) + 1
    top = sum(sorted(freq.values(), reverse=True)[:20]) / len(c)
    return {"seq": seq, "punct": punct, "top20": top}


def check_filler(md: str, file: str, errors: list[str]) -> int:
    bad = [ln for ln, text in prose_paragraphs(md)
           if (st := filler_stats(text)) and (st["seq"] > 0.3 or st["punct"] < 1.0 or st["top20"] < 0.15)]
    if bad:
        errors.append(f"{file}: 第 {bad[:8]} 行等 {len(bad)} 段是机器填充（连续码位 / 没有标点 / 没有常用字），不是译文——删掉，逐段全译")
    return len(bad)


def check_zh_untranslated(zh: str, errors: list[str]) -> None:
    """题名块以外，整段还是英文的正文段。"""
    # Reference identities remain in the source language; they are not untranslated body prose.
    refs = re.search(r"(?m)^##[ \t]+(?:参考文献|References)[ \t]*$", zh)
    if refs:
        zh = zh[:refs.start()]
    first_h2 = zh.find("\n## ")
    body_start = zh[:first_h2].count("\n") + 1 if first_h2 >= 0 else 0
    bad = []
    for ln, text in prose_paragraphs(zh):
        if ln <= body_start or text.startswith("**关键词"):
            continue
        letters = [ch for ch in strip_math(text) if ch.isalpha()]
        if len(letters) >= 150 and cjk_count("".join(letters)) / len(letters) < 0.2:
            bad.append(ln)
    if bad:
        errors.append(f"zh.md: 第 {bad[:6]} 行等 {len(bad)} 段还是英文原文，没有翻译")


def check_zh_captions(zh: str, errors: list[str]) -> None:
    bad = []
    for line in zh.splitlines():
        s = line.strip()
        if not (ZH_CAP.match(s) or ZH_TAB.match(s)):
            continue
        letters = [ch for ch in strip_math(s) if ch.isalpha()]
        if len(letters) >= 20 and cjk_count("".join(letters)) / len(letters) < 0.3:
            bad.append(s[:24])
    if bad:
        errors.append(f"zh.md: {len(bad)} 条图注/表题没有译成中文（例 {bad[:3]}）——`**图 N.**` 后面要跟中文图注")


def check_meta_phrases(zh: str, errors: list[str]) -> None:
    hits = [(i + 1, m.group(0)) for i, l in enumerate(zh.splitlines()) if (m := META_PHRASE.search(l))]
    if hits:
        errors.append(f"zh.md: 出现「{hits[0][1]}」缺译说明（行 {[h[0] for h in hits[:5]]}）——须对照原文补齐完整译文，不能仅删除说明后交付")


def headings_at(md: str) -> list[tuple[int, int, str]]:
    """(行号 0-based, 级别, 标题文字)，只取 ## / ###。"""
    return [(i, len(m.group(1)), m.group(2).strip()) for i, l in enumerate(md.splitlines())
            if (m := re.match(r"^(#{2,3})\s+(.+?)\s*$", l))]


def check_dump_sections(md: str, file: str, errors: list[str]) -> None:
    lines = md.splitlines()
    heads = headings_at(md)
    for k, (i, _lvl, title) in enumerate(heads):
        if re.match(r"^\d", title) or not DUMP_HEADING.match(title):
            continue
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        body = "\n".join(lines[i + 1: end])
        n = len(TAG.findall(body)) + len(re.findall(r"^\*\*(?:Fig\.?|Figure|图|Table|表)\s*\d", body, re.M))
        if n >= 2:
            errors.append(f"{file}: `## {title}` 节里集中堆了 {n} 条公式/图/表——它们必须放回原文出现的位置（公式在引出它的那段话后面、图在首次提到处附近），不许另开一节堆放")


def check_empty_sections(md: str, file: str, errors: list[str], warnings: list[str]) -> None:
    """编号章节（含 Abstract/摘要）标题下没有正文 = error；后置节（致谢、数据声明…）空着只警告。"""
    lines = md.splitlines()
    heads = headings_at(md)
    empty_num, empty_other = [], []
    for k, (i, lvl, title) in enumerate(heads):
        end = len(lines)
        for j in range(k + 1, len(heads)):
            if heads[j][1] <= lvl:
                end = heads[j][0]
                break
        if len(re.sub(r"\s+", "", "\n".join(lines[i + 1: end]))) < 20:
            (empty_num if re.match(r"^\d|^abstract$|^摘要$|^亮点$|^highlights$", title.strip().lower()) else empty_other).append(title[:30])
    if empty_num:
        errors.append(f"{file}: {len(empty_num)} 个章节标题下没有正文（{empty_num[:6]}）——每个标题下都要有该节的原文/译文，不许只留标题凑数")
    if empty_other:
        warnings.append(f"{file}: 标题 {empty_other[:4]} 下面是空的，补上内容或删掉标题")


def norm_en(s: str) -> str:
    """英文归一化：小写、只留字母数字；行内公式取其中的字母数字（`$C_{D}$` → cd），和 fulltext 里的 CD 对得上。"""
    s = re.sub(r"\$\$[\s\S]*?\$\$", " ", s)
    s = re.sub(r"\$([^$\n]+)\$", lambda m: re.sub(r"\\[a-zA-Z]+", " ", m.group(1)), s)
    return re.sub(r"[^a-z0-9]", "", s.lower())


def check_en_anchors(en: str, columns: str, fulltext: str, errors: list[str], warnings: list[str], counts: dict) -> None:
    """en.md 的每个正文段都应能在 PDF 原文里找到（5 个 40 字符窗口任中一个即算）。改写、概括、填充的段落找不到。"""
    hay = norm_en(fulltext) + "|" + norm_en(columns)
    pars = [(ln, norm_en(t)) for ln, t in prose_paragraphs(en)]
    pars = [(ln, n) for ln, n in pars if len(n) >= 120]
    if len(pars) < 5:
        return
    miss = []
    for ln, n in pars:
        step = max(1, (len(n) - 40) // 4)
        wins = [n[k: k + 40] for k in range(0, len(n) - 39, step)][:5]
        if not any(w in hay for w in wins):
            miss.append(ln)
    ratio = 1 - len(miss) / len(pars)
    counts["enParagraphsInSource"] = round(ratio, 2)
    if ratio < 0.7:
        errors.append(f"en.md: {len(pars)} 个正文段里有 {len(miss)} 段在 PDF 原文里找不到（行 {miss[:6]}）——英文正文必须是原文照录，不许改写 / 概括 / 填充")
    elif miss:
        warnings.append(f"en.md: {len(miss)} 段在 PDF 原文里对不上（行 {miss[:6]}），抽查是否被改写")


def check_eq_positions(en: str, columns: str, errors: list[str], warnings: list[str], counts: dict) -> None:
    """columns.md 里公式行（[MATH] 或行尾 (N)）上方最近的一段正文 = 公式 (N) 的锚点；
    en.md 里 \\tag{N} 之前 1500 个归一化字符内必须能找到它。公式被集中堆到别处时，锚点全部对不上。"""
    dl = columns.splitlines()
    anchors: dict[int | str, str] = {}
    for i, line in enumerate(dl):
        s = line.strip()
        nums: list[int | str] = []
        if s.startswith("[MATH]"):
            nums = [equation_id(m.group(1)) for m in re.finditer(r"[(（]\s*((?:[A-Z]\.?)?\d{1,3}(?:\.\d{1,3})*)[a-z]?\s*[)）]", s)]
        elif not s.startswith(("[small]", "[CAP]", "[TAB]", "<!--")) and MATHY.search(s):
            m = EQ_LINE.search(s)
            if m:
                nums = [equation_id(m.group(1))]
        if not nums:
            continue
        for j in range(i - 1, max(-1, i - 40), -1):
            t = dl[j].strip()
            if not t or t.startswith(("<!--", "[MATH]", "[small]", "[CAP]", "[TAB]", "[BIG]")):
                continue
            t = re.sub(r"^\[(?:BOLD|ITAL)\]\s*", "", t)
            n = norm_en(t)
            if len(n) >= 60 and COMMON_EN.search(t):
                for num in nums:
                    anchors.setdefault(num, n[-40:])
                break
    if len(anchors) < 3:
        return
    buf = ""
    in_math = False
    found: list[int | str] = []
    miss: list[int | str] = []
    for line in en.splitlines():
        s = line.strip()
        for t in TAG.finditer(line):
            n = equation_id(t.group(1))
            if n in anchors:
                (found if anchors[n] in buf[-1500:] else miss).append(n)
        if s.startswith("$$"):
            if s.count("$$") == 1:
                in_math = not in_math
            continue
        if in_math or s.startswith("<!--"):
            continue
        buf += norm_en(line)
    total = len(found) + len(miss)
    if not total:
        return
    counts["equationsInPlace"] = f"{len(found)}/{total}"
    if total >= 3 and len(miss) / total > 0.5:
        errors.append(f"en.md: {total} 条公式里 {len(miss)} 条不在原文位置（引出它的那段话不在公式上方，例 ({miss[0]})）——公式必须放在原文引出它的段落后面，不许集中堆到某一节")
    elif miss:
        warnings.append(f"en.md: 公式 {miss[:8]} 上方找不到原文里引出它的段落，核对是否放错了位置")


def item_sections(md: str) -> dict[str, str]:
    """公式号 / 图号 / 表号 → 所在章节（最近的上级编号标题如 2.3；无编号标题用标题文字）。"""
    out: dict[str, str] = {}
    sec = "_front"
    for line in md.splitlines():
        m = re.match(r"^(#{2,3})\s+(.+?)\s*$", line)
        if m:
            num = re.match(r"^(\d+(?:\.\d+)*)", m.group(2))
            appendix = re.match(r"^(?:Appendix|附录)\s*([A-Z])(?![A-Za-z])", m.group(2), re.I)
            sec = num.group(1) if num else (f"appendix {appendix.group(1).upper()}" if appendix else m.group(2).strip().lower())
            continue
        s = line.strip()
        for t in TAG.finditer(line):
            out.setdefault(f"式({equation_id(t.group(1))})", sec)
        c = EN_CAP.match(s) or ZH_CAP.match(s)
        if c:
            out.setdefault(f"图{equation_id(c.group(1))}", sec)
        tb = EN_TAB.match(s) or ZH_TAB.match(s)
        if tb:
            out.setdefault(f"表{equation_id(tb.group(1))}", sec)
    return out


def check_zh_positions(en: str, zh: str, errors: list[str], warnings: list[str], counts: dict) -> None:
    """zh.md 的每条公式 / 图 / 表应和 en.md 落在同一个编号章节。"""
    a, b = item_sections(en), item_sections(zh)
    common = [k for k in a if k in b]
    if len(common) < 3:
        return
    mism = [k for k in common if a[k] != b[k] and (re.match(r"\d|appendix ", a[k]) or re.match(r"\d|appendix ", b[k]))]
    counts["zhItemsMisplaced"] = f"{len(mism)}/{len(common)}"
    if len(mism) / len(common) > 0.3:
        errors.append(f"zh.md: {len(common)} 个公式/图/表里 {len(mism)} 个所在章节与 en.md 不一致（例 {mism[:5]}）——位置照 en.md 逐一对应，不许集中堆放")
    elif mism:
        warnings.append(f"zh.md: 公式/图/表 {mism[:6]} 所在章节与 en.md 不一致，核对位置")


def check_fields(fields: dict, lang: str, meta: dict, errors: list[str], warnings: list[str]) -> None:
    pdf_stem = Path(str(meta.get("pdf") or "")).stem
    meta_title = str(meta.get("title") or "").strip()
    if (not meta_title or meta_title == pdf_stem) and not str(fields.get("title") or "").strip():
        errors.append("fields.json: meta.json 的题名为空或就是文件名，必须在 title 里填原文题名（照 p1）")
    if not meta.get("authors") and not [a for a in (fields.get("authors") or []) if str(a).strip()]:
        errors.append("fields.json: meta.json 没有作者，必须在 authors 里填作者列表（照 p1）")
    short = str(fields.get("shortTitle") or "").strip()
    if not short:
        errors.append("fields.json: 缺 shortTitle")
    elif len(short) > 14 or re.search(r"[\s/\\:*?\"<>|]", short):
        errors.append(f"fields.json: shortTitle 须 ≤14 字且无空格/标点（现为 `{short}`）")
    if not str(fields.get("translatedTitle") or "").strip():
        errors.append("fields.json: 缺 translatedTitle")
    domain = str(fields.get("domain") or "").strip("/ ")
    if not domain:
        errors.append("fields.json: 缺 domain")
    elif "/" not in domain:
        warnings.append(f"fields.json: domain 建议写成 大类/子类（现为 `{domain}`）")
    if lang == "zh" and not re.fullmatch(r"[A-Za-z]{1,12}", str(fields.get("firstAuthorPinyin") or "")):
        errors.append("fields.json: 中文原刊必须填 firstAuthorPinyin（第一作者姓拼音，纯字母）")
    for k in ("tldr", "question", "score"):
        if not str(fields.get(k) or "").strip():
            warnings.append(f"fields.json: {k} 为空")
    if not fields.get("topics"):
        warnings.append("fields.json: topics 为空")


def reference_identity(text: str) -> str:
    """只忽略排版及附加链接，保留作者、题名和出版信息用于同号对账。"""
    text = re.sub(r"\[\[[^\]]+\]\]", "", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    text = re.sub(r"https?://\S+|\^ref-\d+|🔗\s*DOI", "", text, flags=re.I)
    return "".join(c for c in unicodedata.normalize("NFKC", text).lower() if c.isalnum())


def check_references(refs: str, fulltext: str, errors: list[str], warnings: list[str], counts: dict) -> None:
    from references import extract_numbered_references

    source = extract_numbered_references(fulltext)
    matches = list(re.finditer(r"(?m)^\s*-\s+\*\*\[(\d+)\]\*\*\s*", refs))
    rows = [(int(m.group(1)), refs[m.end():matches[i + 1].start() if i + 1 < len(matches) else len(refs)].strip())
            for i, m in enumerate(matches)]
    anchors = [int(n) for n in re.findall(r"\^ref-(\d+)\b", refs)]
    duplicate_anchors = sorted(n for n, total in Counter(anchors).items() if total > 1)
    duplicate_labels = sorted(n for n, total in Counter(n for n, _ in rows).items() if total > 1)
    if duplicate_anchors:
        errors.append(f"refs.md: 引用锚点重复 {duplicate_anchors}")
    if duplicate_labels:
        errors.append(f"refs.md: 条目编号重复 {duplicate_labels}")
    if refs.strip() and not rows:
        errors.append("refs.md: 文献须按 `- **[N]** … ^ref-N` 排版")
    for number, text in rows:
        actual = [int(n) for n in re.findall(r"\^ref-(\d+)\b", text)]
        if number not in actual:
            errors.append(f"refs.md: 条目 [{number}] 缺对应 ^ref-{number} 锚点")
        if source["numbers"] and actual != [number]:
            errors.append(f"refs.md: 原刊编号 [{number}] 与引用锚点 {actual} 不一致")
        if re.search(r"\b(?:Acknowledgements?|Author contributions|Competing interests|Publisher['’]s note)\b|致谢|作者贡献|利益冲突", text, re.I):
            errors.append(f"refs.md: 条目 [{number}] 混入论文后置说明，回参考文献原页核对边界")
    if source["numbers"]:
        expected = set(source["numbers"])
        actual = {n for n, _ in rows}
        if expected - actual:
            errors.append(f"refs.md: 漏原刊参考文献 {sorted(expected - actual)}；不得用重新编号掩盖漏条")
        if actual - expected:
            errors.append(f"refs.md: 多出原刊没有的文献编号 {sorted(actual - expected)}")
        by_number = dict(rows)
        for entry in source["entries"]:
            number = entry["num"]
            if number not in by_number:
                continue
            original = reference_identity(entry["text"])
            provided = reference_identity(by_number[number])
            if original and (not provided.startswith(original[:80]) or SequenceMatcher(None, original, provided, autojunk=False).ratio() < 0.90):
                errors.append(f"refs.md: 条目 [{number}] 与原刊同号条目不符或信息不完整，核对作者、题名及出版信息")
    elif re.search(r"(?im)^\s*(?:References?|Bibliography|参\s*考\s*文\s*献)\s*$", fulltext) and not rows:
        errors.append("refs.md: 原文有参考文献节，但文献清单为空")
    warnings.extend(f"原刊参考文献：{message}" for message in source["warnings"])
    counts["references"] = {"sourceNumbered": bool(source["numbers"]), "sourceEntries": len(source["entries"]),
                            "entries": len(rows), "anchors": len(anchors), "sourceNumbers": source["numbers"]}


def verify(work: Path) -> dict:
    out = work / "out"
    meta = json.loads(rd(work / "meta.json") or "{}")
    stats = json.loads(rd(work / "stats.json") or "{}")
    lang = meta.get("lang", "en")
    fulltext = rd(work / "fulltext.txt")
    columns = rd(work / "columns.md") or rd(work / "en.draft.md")   # 旧工作区兜底
    errors: list[str] = []
    warnings: list[str] = []

    required = ["zh.md", "notes.md", "terms.json", "fields.json"] + (["en.md"] if lang == "en" else [])
    for f in required:
        if not (out / f).exists() or not rd(out / f).strip():
            errors.append(f"out/{f} 不存在或为空")
    en = rd(out / "en.md") if lang == "en" else ""
    zh = rd(out / "zh.md")
    notes = rd(out / "notes.md")

    # 对账标准 = AI 排版核出的清单；脚本正则粗数只做交叉提醒
    hint = expected_from_pdf(fulltext, columns, stats)
    lay = expected_from_layout(work, errors)
    exp = lay if lay is not None else hint
    overrides = {}
    try:
        overrides = json.loads(rd(out / "verify_overrides.json") or "{}")
    except Exception as exc:
        warnings.append(f"verify_overrides.json 解析失败：{exc}")
    parsed_overrides = {
        kind: {equation_id(str(x)) for x in (overrides.get(kind) or [])
               if re.fullmatch(r"(?:[A-Z]\.?)?\d+(?:\.\d+)*[′']?", str(x))}
        for kind in ("figures", "tables", "equations")
    }
    expected: dict[str, set[int | str]] = {}
    gaps: dict[str, list[int | str]] = {}
    for kind in ("figures", "tables", "equations"):
        full, missing = consecutive(exp[kind])
        skip = parsed_overrides[kind]
        expected[kind] = full - skip
        gaps[kind] = [n for n in missing if n not in skip]
        if lay is not None:
            extra_hint = sorted(hint[kind] - expected[kind] - skip, key=number_key)
            if extra_hint:
                label = {"figures": "图", "tables": "表", "equations": "公式"}[kind]
                warnings.append(f"脚本在 PDF 文本里看到{label}号 {extra_hint[:10]}，layout.json 清单里没有——逐个核对：原刊真有就补进清单和正文，是误判就忽略")

    images = {p.name for p in (work / "images").glob("*.png") if not p.name.startswith("_")}
    counts: dict = {"lang": lang, "expectedSource": "layout.json" if lay is not None else "regex-hint",
                    "expected": {k: sorted(v, key=number_key) for k, v in expected.items()},
                    "hint": {k: sorted(v, key=number_key) for k, v in hint.items()},
                    "overrides": {k: sorted(v, key=number_key) for k, v in parsed_overrides.items()},
                    "pdfGaps": gaps, "imagesOnDisk": len(images)}
    check_references(rd(work / "refs.md"), fulltext, errors, warnings, counts)

    # ---- 嵌图文件存在性 + 每张裁图都用上了
    for name, md in (("en.md", en), ("zh.md", zh), ("notes.md", notes)):
        if not md:
            continue
        for m in EMBED.finditer(md):
            f = m.group(1).strip()
            if f.startswith("_"):
                errors.append(f"{name}: 嵌了核对用的 `{f}`，不是论文图")
            elif f not in images:
                errors.append(f"{name}: 嵌图文件不存在 images/{f}")
    used = {m.group(1).strip() for md in (en, zh) for m in EMBED.finditer(md)}
    unused = sorted(images - used)
    if unused:
        warnings.append(f"images/ 里 {len(unused)} 张裁图没被 en/zh 用到：{unused[:6]}（多裁的删掉或补嵌）")

    # ---- 图：每个编号都有图注 + 嵌图
    fig_zh, emb_zh = check_captions(zh, ZH_CAP, expected["figures"], "图", errors, "zh.md")
    fig_en, emb_en = (check_captions(en, EN_CAP, expected["figures"], "Fig.", errors, "en.md") if lang == "en" else (fig_zh, emb_zh))
    counts["figures"] = {"expected": len(expected["figures"]), "zhCaptions": len(fig_zh), "zhEmbedded": len(emb_zh),
                         "enCaptions": len(fig_en), "enEmbedded": len(emb_en)}
    if meta.get("qualityPolicy") == "source-reviewed-v1":
        check_source_quality(work, en, zh, expected["figures"], lang, errors, counts)

    # ---- 表
    tab_zh = check_tables(zh, ZH_TAB, expected["tables"], errors, "zh.md", "表")
    tab_en = check_tables(en, EN_TAB, expected["tables"], errors, "en.md", "Table") if lang == "en" else tab_zh
    counts["tables"] = {"expected": len(expected["tables"]), "zhBuilt": len(tab_zh), "enBuilt": len(tab_en)}

    # ---- 公式：每个编号都有 \tag
    tags_en = {equation_id(m.group(1)) for m in TAG.finditer(en)}
    tags_zh = {equation_id(m.group(1)) for m in TAG.finditer(zh)}
    for n in sorted(expected["equations"] - tags_zh, key=number_key):
        errors.append(f"zh.md: 缺公式 ({n})（应有 `$$ … \\tag{{{n}}} $$`）")
    if lang == "en":
        for n in sorted(expected["equations"] - tags_en, key=number_key):
            errors.append(f"en.md: 缺公式 ({n})（应有 `$$ … \\tag{{{n}}} $$`）")
        extra = sorted(tags_en - expected["equations"], key=number_key)
        if extra:
            warnings.append(f"en.md: 出现了 PDF 里没数到的公式号 {extra[:10]}（核对一下编号）")
        if tags_en != tags_zh:
            warnings.append(f"en/zh 的公式号集合不一致：仅 en {sorted(tags_en - tags_zh, key=number_key)[:10]} / 仅 zh {sorted(tags_zh - tags_en, key=number_key)[:10]}")
    counts["equations"] = {"expected": len(expected["equations"]), "enTagged": len(tags_en), "zhTagged": len(tags_zh)}
    for kind, present in (("equations", tags_zh), ("figures", fig_zh), ("tables", tab_zh)):
        bogus = sorted(set(counts["overrides"][kind]) & present, key=number_key)
        if bogus:
            warnings.append(f"verify_overrides.json 把 {kind} {bogus} 登记为「PDF 里不存在」，但正文里其实写了——overrides 只登记确实不存在的编号，删掉这些登记")

    # ---- 数学 / 乱码 / 标记
    if lang == "en":
        check_math(en, "en.md", errors, warnings)
    check_math(zh, "zh.md", errors, warnings)
    check_math(notes, "notes.md", errors, warnings)
    for name, md in (("en.md", en), ("zh.md", zh), ("notes.md", notes)):
        if md:
            check_table_cells(md, name, errors)

    # ---- 真实性与位置（每条都对应一次实测作弊，见函数上方说明）
    for name, md in (("en.md", en), ("zh.md", zh), ("notes.md", notes)):
        if md:
            check_filler(md, name, errors)
    for name, md in (("en.md", en), ("zh.md", zh)):
        if md:
            check_dump_sections(md, name, errors)
            check_empty_sections(md, name, errors, warnings)
    if zh:
        check_zh_untranslated(zh, errors)
        check_zh_captions(zh, errors)
        check_meta_phrases(zh, errors)
    if lang == "en" and en:
        check_en_anchors(en, columns, fulltext, errors, warnings, counts)
        check_eq_positions(en, columns, errors, warnings, counts)
        if zh:
            check_zh_positions(en, zh, errors, warnings, counts)

    # ---- 结构与语言
    if lang == "en" and en and not en.lstrip().startswith("# "):
        errors.append("en.md: 第一行必须是 `# 题名`")
    if zh and not zh.lstrip().startswith("# "):
        errors.append("zh.md: 第一行必须是 `# 中文译名`")
    book = meta.get("documentType") == "book"
    editorial = meta.get("documentType") == "editorial"
    front_en = None if editorial else ("Preface" if book else "Abstract")
    if lang == "en" and en and front_en and not re.search(rf"^## {front_en}\s*$", en, re.M):
        errors.append(f"en.md: 缺 `## {front_en}` 标题节")
    for sec in (("## 前言",) if book else (("## 亮点",) if editorial else ("## 亮点", "## 摘要"))):
        if zh and not re.search(rf"^{re.escape(sec)}\s*$", zh, re.M):
            errors.append(f"zh.md: 缺 `{sec}` 节")
    fields: dict = {}
    try:
        fields = json.loads(rd(out / "fields.json") or "{}")
        if not isinstance(fields, dict):
            raise ValueError("不是对象")
    except Exception as exc:
        errors.append(f"fields.json 解析失败：{exc}")
        fields = {}
    if fields:
        check_fields(fields, lang, meta, errors, warnings)
        if fields.get("highlightsPrinted") is False and zh and "本节要点由 AI 通读全文提炼" not in zh:
            errors.append("zh.md: 原刊没印 Highlights，亮点列表后必须跟一行 `> **【说明】** 本节要点由 AI 通读全文提炼，原刊未印 Highlights。`")
        if fields.get("keywords") and zh and "**关键词：**" not in zh and "**关键词**" not in zh:
            warnings.append("zh.md: fields.keywords 非空但摘要后没有 `**关键词：**` 行")
    if lang == "en" and en:
        cjk = cjk_count(strip_math(EMBED.sub("", en)))
        if cjk > 30:
            errors.append(f"en.md: 含 {cjk} 个汉字，英文正文不应有中文")
        elif cjk:
            warnings.append(f"en.md: 含 {cjk} 个汉字")
    if zh:
        letters = [ch for ch in strip_math(zh) if ch.isalpha()]
        ratio = cjk_count("".join(letters)) / len(letters) if letters else 0
        if ratio < 0.4:
            errors.append(f"zh.md: 中文比例仅 {ratio:.0%}，不是完整译文")
        if lang == "en" and en:
            check_fidelity(en, zh, errors, warnings, counts)
    if lang == "en" and en and columns:
        check_en_fidelity(en, columns, errors, warnings, counts)
    for name, md in (("en.md", en), ("zh.md", zh)):
        links = [m.group(1) for m in WIKILINK.finditer(md)]
        if links:
            warnings.append(f"{name}: 有 {len(links)} 个 [[wikilink]]（例 {links[:3]}），不需要写")
    if lang == "en" and en and zh:
        h_en = [m for m in HEADING.finditer(en) if len(m.group(1)) >= 2]
        h_zh = [m for m in HEADING.finditer(zh) if len(m.group(1)) >= 2]
        counts["headings"] = {"en": len(h_en), "zh": len(h_zh)}
        num_en = {re.match(r"^(\d+(?:\.\d+)*)", m.group(2)).group(1) for m in h_en if re.match(r"^\d", m.group(2))}
        num_zh = {re.match(r"^(\d+(?:\.\d+)*)", m.group(2)).group(1) for m in h_zh if re.match(r"^\d", m.group(2))}
        if num_en - num_zh:
            errors.append(f"zh.md: 缺英文有的编号章节 {sorted(num_en - num_zh, key=lambda s: [int(x) for x in s.split('.')])[:12]}")
        if num_zh - num_en:
            warnings.append(f"zh.md: 多出英文没有的编号章节 {sorted(num_zh - num_en)[:12]}")
        for m in h_zh:
            if re.match(r"^\d+(?:\.\d+)*\.\s", m.group(2)):
                warnings.append(f"zh.md: 中文标题编号不带尾点（`{m.group(2)[:30]}`）")
                break
    if notes:
        missing = [h for h in NOTES_REQUIRED if h not in notes]
        if missing:
            errors.append(f"notes.md: 缺骨架标题 {missing}")
    try:
        terms = json.loads(rd(out / "terms.json") or "[]")
        if not isinstance(terms, list):
            raise ValueError("不是数组")
        bad = [t for t in terms if not (isinstance(t, dict) and str(t.get("term", "")).strip() and str(t.get("definition", "")).strip())]
        if bad:
            warnings.append(f"terms.json: {len(bad)} 条缺 term/definition")
        if not 8 <= len(terms) <= 20:
            warnings.append(f"terms.json: 应 8–20 条，现 {len(terms)} 条")
        counts["terms"] = len(terms)
    except Exception as exc:
        errors.append(f"terms.json 解析失败：{exc}")

    src = "layout.json 清单" if lay is not None else "PDF 文本"
    if gaps["figures"]:
        errors.append(f"{src}里图号连续到 {max(expected['figures'] | set(gaps['figures']), key=number_key)}，中间缺图 {gaps['figures']}；回页面图找，确实不存在就写 out/verify_overrides.json")
    if gaps["equations"]:
        errors.append(f"{src}里公式号连续到 {max(expected['equations'] | set(gaps['equations']), key=number_key)}，中间缺 {gaps['equations']}，照页面图补齐或登记 overrides")
    if gaps["tables"]:
        errors.append(f"{src}里表号缺 {gaps['tables']}，补齐或登记 overrides")

    counts["lines"] = {"en": en.count("\n"), "zh": zh.count("\n"), "notes": notes.count("\n")}
    result = {"ok": not errors, "errors": errors, "warnings": warnings, "counts": counts}
    (work / "verify.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def main() -> None:
    utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    result = verify(Path(a.work).resolve())
    if a.quiet:
        print(f"verify: {'OK' if result['ok'] else 'FAIL'} errors={len(result['errors'])} warnings={len(result['warnings'])}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
