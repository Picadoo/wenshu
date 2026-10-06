"""Deterministic, source-reviewed translation handoff. No model or PDF semantics here.

Public APIs return error strings rather than treating token counts as source evidence.
Numeric-only table cells (including ASCII units) are locked whole; mixed cells lock
their numbers. Prose outside tables is translated, not checked for semantic fidelity.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TOKEN_RE = re.compile(r"⟦WS\d{6}⟧")
REF_HEAD = re.compile(r"(?im)^#{1,6}[ \t]+(?:References|参考文献)[ \t]*\r?$")
NUMBER = re.compile(r"(?<![\d.])[-+−]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?(?:%|‰)?")


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _source_language(work: Path) -> str:
    language = _json(work / "meta.json").get("lang", "en")
    if language not in ("en", "zh"):
        raise ValueError("meta.lang 只能为 en/zh")
    return language


def protected_spans(md: str) -> list[dict]:
    """Nonoverlapping original strings, in order: kind/text/start/end.

    Code/references contain opaque text. Dollar math, wiki/Markdown images and
    inline code are exact strings. This is syntax protection, not OCR validation.
    """
    spans: list[dict] = []

    def add(start: int, end: int, kind: str) -> None:
        if end > start and not any(start < s["end"] and end > s["start"] for s in spans):
            spans.append({"kind": kind, "text": md[start:end], "start": start, "end": end})

    for m in re.finditer(r"(?m)^([ \t]*)(`{3,}|~{3,})[^\n]*\n[\s\S]*?^\1\2[ \t]*(?:\n|$)", md):
        add(m.start(), m.end(), "code_fence")
    for m in REF_HEAD.finditer(md):
        end = len(md)
        level = len(m.group().split()[0])
        for nxt in re.finditer(r"(?m)^(#{1,6})[ \t]+.+$", md[m.end():]):
            if len(nxt.group(1)) <= level:
                end = m.end() + nxt.start()
                break
        # Leave the heading available for References -> 参考文献 translation.
        add(m.end(), end, "references")
    patterns = (
        ("math_block", r"(?<!\\)\$\$[\s\S]*?(?<!\\)\$\$"),
        ("image", r"!\[\[[^\]\n]+\]\]|!\[[^\]\n]*\]\([^\n]+?\)"),
        ("code_inline", r"(?<!`)(`+)([^\n]+?)\1(?!`)"),
        ("math_inline", r"(?<![\\$])\$(?!\$)(?:\\.|[^$\n])+?(?<!\\)\$(?!\$)"),
    )
    for kind, pattern in patterns:
        for m in re.finditer(pattern, md):
            add(m.start(), m.end(), kind)
    for row in re.finditer(r"(?m)^[ \t]*\|[^\n]*\|[ \t]*$", md):
        start = row.start()
        pipes = [m.start() for m in re.finditer(r"(?<!\\)\|", row.group())]
        for left, right in zip(pipes, pipes[1:]):
            a, b = start + left + 1, start + right
            cell = md[a:b]
            stripped = cell.strip()
            if not stripped or re.fullmatch(r"[:\- ]+", stripped):
                continue
            # Whole numeric cells retain units and sign. Label cells translate.
            if NUMBER.match(stripped) and not re.search(r"[^\w\s.,/%‰°+−\-±×^()\[\]{}*·⁻¹²³]", stripped) and not re.search(r"[\u3400-\u9fff]", stripped):
                add(a, b, "table_cell")
            else:
                for n in NUMBER.finditer(cell):
                    add(a + n.start(), a + n.end(), "table_number")
    return sorted(spans, key=lambda s: s["start"])


def compare_protected(en: str, zh: str) -> list[str]:
    """Compare exact protected originals; References heading may be translated."""
    left = [(s["kind"], s["text"]) for s in protected_spans(en)]
    right = [(s["kind"], s["text"]) for s in protected_spans(zh)]
    if left == right:
        return []
    errors = []
    if len(left) != len(right):
        errors.append(f"受保护内容数量不同：EN {len(left)} / ZH {len(right)}")
    for i, (a, b) in enumerate(zip(left, right), 1):
        if a != b:
            errors.append(f"受保护内容第 {i} 项不同：{a[0]} {a[1][:100]!r} / {b[0]} {b[1][:100]!r}")
            if len(errors) >= 8:
                break
    return errors


def _layout_errors(work: Path) -> list[str]:
    try:
        layout = _json(work / "out/layout.json")
        stats = _json(work / "stats.json")
    except (OSError, ValueError) as exc:
        return [f"源审核缺少有效 layout.json/stats.json：{exc}"]
    pages = stats.get("pages")
    if not isinstance(pages, int) or isinstance(pages, bool) or pages < 1:
        return ["stats.pages 必须是原稿正整数页数"]
    errors = []
    if not isinstance(layout.get("headings"), list) or not layout["headings"]:
        errors.append("layout.headings 为空，不能记录结构审核通过")
    for group in ("headings", "equations", "tables"):
        items = layout.get(group, [])
        if not isinstance(items, list):
            errors.append(f"layout.{group} 必须是列表")
            continue
        for item in items:
            if not isinstance(item, dict):
                errors.append(f"layout.{group} 项目必须是对象")
                continue
            page = item.get("page")
            if not isinstance(page, int) or isinstance(page, bool) or not 1 <= page <= pages:
                errors.append(f"layout.{group} 页码无效：{item.get('num', item.get('title', '?'))} page={page}")
    return errors


def review_source(work: Path, note: str) -> dict:
    """Seal a caller's actual original-page review; never infer it automatically."""
    errors = _layout_errors(work)
    if not note.strip():
        errors.append("source review 必须有实际原页核对 notes")
    try:
        language = _source_language(work)
    except (OSError, ValueError) as exc:
        return {"ok": False, "errors": errors + [f"源语言元数据无效：{exc}"]}
    source = work / f"out/{language}.md"
    if not source.is_file() or not source.read_bytes().strip():
        errors.append(f"缺少 meta.lang={language} 对应的非空 out/{language}.md；不能回退到其他语言")
    if not errors:
        from mathcheck import check_renderable
        try:
            errors.extend(check_renderable(source.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            errors.append(f"不能审核正文或公式语法：{exc}")
    if errors:
        return {"ok": False, "errors": errors}
    (work / f"out/source-review.{language}.md").write_bytes(source.read_bytes())
    (work / "out/source-review.layout.json").write_bytes((work / "out/layout.json").read_bytes())
    _write_json(work / "out/source-review.json", {
        "equationsReviewed": True, "tablesReviewed": True, "structureReviewed": True,
        "notes": note.strip(), "sourceLanguage": language,
    })
    return {"ok": True, "errors": [], "sourceLanguage": language}


def check_source_review(work: Path) -> list[str]:
    errors = _layout_errors(work)
    try:
        review = _json(work / "out/source-review.json")
    except (OSError, ValueError) as exc:
        return errors + [f"缺少有效 source-review.json；必须先实际核对原页：{exc}"]
    for flag in ("equationsReviewed", "tablesReviewed", "structureReviewed"):
        if review.get(flag) is not True:
            errors.append(f"源审核未确认 {flag}")
    if not isinstance(review.get("notes"), str) or not review["notes"].strip():
        errors.append("source-review.notes 不能为空")
    lang = review.get("sourceLanguage")
    if lang not in ("en", "zh"):
        errors.append("source-review.sourceLanguage 只能为 en/zh")
        return errors
    try:
        if lang != _source_language(work):
            errors.append("source-review.sourceLanguage 与 meta.lang 不一致，需核对原刊语言后重新审核")
    except (OSError, ValueError) as exc:
        errors.append(f"源语言元数据无效：{exc}")
    for source, snapshot in ((work / f"out/{lang}.md", work / f"out/source-review.{lang}.md"),
                             (work / "out/layout.json", work / "out/source-review.layout.json")):
        if not source.is_file() or not snapshot.is_file():
            errors.append(f"源审核快照缺失：{snapshot.name}")
        elif source.read_bytes() != snapshot.read_bytes():
            errors.append(f"源审核后 {source.name} 已改变，需重新对照原页并 review-source")
    return errors


def _figure_errors(work: Path) -> list[str]:
    from figtools import load_report, review_errors
    errors = review_errors(work)
    try:
        report = load_report(work)
        for figure in report.get("figures", []):
            if not isinstance(figure.get("reviewedAt"), str) or not figure["reviewedAt"].strip():
                errors.append(f"Fig. {figure.get('num', '?')} 缺少 reviewedAt")
    except (OSError, ValueError) as exc:
        errors.append(f"裁图记录无效：{exc}")
    return errors


def _lock(md: str) -> tuple[str, dict]:
    tokens: list[dict] = []
    blocks: list[dict] = []

    def token(text: str, kind: str) -> str:
        name = f"⟦WS{len(tokens) + 1:06d}⟧"
        tokens.append({"token": name, "kind": kind, "text": text})
        return name

    parts, pos = [], 0
    for span in protected_spans(md):
        parts.extend((md[pos:span["start"]], token(span["text"], span["kind"])))
        pos = span["end"]
    parts.append(md[pos:])
    locked = "".join(parts)
    # Retain Markdown heading/list syntax and table geometry, not English labels.
    locked = re.sub(r"(?m)^(#{1,6}[ \t]+|[ \t]*(?:[-+*]|\d+[.)])[ \t]+)",
                    lambda m: token(m.group(), "structure"), locked)
    locked = re.sub(r"(?m)^([ \t]*\|.*\|[ \t]*)$", lambda row: re.sub(
        r"(?<!\\)\||(?<=\|)[ \t]*:?-+:?[ \t]*(?=\|)",
        lambda m: token(m.group(), "structure"), row.group()), locked)
    output = []
    for part in re.split(r"(\n[ \t]*\n+)", locked):
        if not part:
            continue
        if re.fullmatch(r"\n[ \t]*\n+", part):
            output.append(token(part, "separator") + "\n\n")
            continue
        begin, end = token("", "block_begin"), token("", "block_end")
        translatable = bool(TOKEN_RE.sub("", part).strip())
        blocks.append({"begin": begin, "end": end, "translatable": translatable})
        output.append(begin + part + end)
    body = "".join(output)
    return body, {"version": 1, "tokens": tokens, "order": TOKEN_RE.findall(body), "blocks": blocks}


REQUEST = """# 仅翻译已审核英文正文

读取本目录 input.md，忠实逐段翻译为中文，写入且只写入本目录 zh.locked.md。
不要读取或执行 brief、其他技能、PDF、原页、refs、layout、笔记，也不要修改任何其他文件。
所有 ⟦WS000001⟧ 形式 token 必须逐字保留，各出现一次，且原顺序不变。
token 代表已核对公式、图片、代码、参考表、表内数字/单位和 Markdown/段落骨架；不要解码、替换或补造它们。
翻译 token 之间的英文正文、标题、图注及非数字表格文字；References 标题译为“参考文献”，Highlights 译为“亮点”，Abstract 译为“摘要”，Preface 译为“前言”。
不增删段落，不添加摘要、解释、公式、图片或参考文献。每个有英文文字的段落必须有译文。
每段内部也须完整翻译，不能用精读、概述或摘译代替；正文原有引文编号、推导和限制条件保留。
混合表格单元中的数字已锁定；ASCII 数字/单位单元整格锁定。普通正文数字、翻译正确性仍需宿主内容复核。
只回复简短完成报告。宿主会恢复锁定原串并进行翻译阶段校验。
"""

TEXT_REQUEST = """这是纯文本翻译，不是仓库任务。不得调用工具、运行命令、读写文件或查阅其他资料。
将下方完整锁定英文逐段忠实译为中文。最终回复只含完整锁定译文，不加说明、前后引言或代码围栏。
所有 ⟦WS000001⟧ 形式 token 逐字保留，各一次、原顺序不变；不要解码、替换或补造。
段首和段尾的控制 token 也必须保留，包括整个译文末尾的 token；每段文字只能写在该段的首尾 token 之间。
token 已锁定公式、图片、代码、参考表、表格数字/单位和Markdown/段落骨架，只翻译其间英文文字。
References 译为“参考文献”，Highlights 译为“亮点”，Abstract 译为“摘要”，Preface 译为“前言”。
每个有英文文字的段落都须有译文；不增删段落，不添加摘要、解释、数学、图片、代码或引用。
每段内部也须完整翻译，不能用精读、概述或摘译代替；正文原有引文编号、推导和限制条件保留。
"""


def token_context(work: Path) -> str:
    """Read-only inline math/table context, never an instruction to restore it."""
    manifest = _json(work / "translation/manifest.json")
    items = [{"token": entry["token"], "kind": entry["kind"], "value": entry["text"]}
             for entry in manifest["tokens"]
             if entry["kind"] in ("math_inline", "table_cell", "table_number")]
    return ("\n以下 JSON 是只读 token 释义，仅用于理解行内符号和表格数值/单位在句子中的作用。\n"
            "不要把释义内容抄入译文，不要手工恢复公式或数字；最终输出仍只保留原 token。\n"
            + json.dumps(items, ensure_ascii=False, indent=1) + "\n")


def prepare(work: Path) -> dict:
    errors = check_source_review(work) + _figure_errors(work)
    try:
        if _source_language(work) != "en":
            errors.append("translate 仅用于 meta.lang=en；中文原刊无需此阶段")
    except (OSError, ValueError) as exc:
        errors.append(f"源语言元数据无效：{exc}")
    source = work / "out/en.md"
    if not source.is_file():
        errors.append("translate 仅接收已审核 out/en.md；中文原刊无需此阶段")
    elif "⟦WS" in source.read_text(encoding="utf-8"):
        errors.append("英文含翻译保留 token 前缀 ⟦WS，不能准备")
    directory = work / "translation"
    snapshot = directory / "source.en.md"
    if snapshot.exists() and source.is_file() and snapshot.read_bytes() != source.read_bytes():
        errors.append("prepare 后英文源已改变；不能复用旧翻译，先核对并清理本篇旧 translation 产物再准备")
    if errors:
        return {"ok": False, "errors": errors}
    directory.mkdir(exist_ok=True)
    body, manifest = _lock(source.read_text(encoding="utf-8"))
    snapshot.write_bytes(source.read_bytes())
    (directory / "input.md").write_text(body, encoding="utf-8")
    _write_json(directory / "manifest.json", manifest)
    (directory / "request.md").write_text(REQUEST + token_context(work), encoding="utf-8")
    return {"ok": True, "errors": [], "input": str(directory / "input.md"),
            "request": str(directory / "request.md"), "tokens": len(manifest["tokens"])}


def _restore(work: Path, locked: str) -> tuple[str, list[str]]:
    errors = check_source_review(work) + _figure_errors(work)
    directory = work / "translation"
    try:
        manifest = _json(directory / "manifest.json")
        source = (work / "out/en.md").read_bytes()
        if (directory / "source.en.md").read_bytes() != source:
            errors.append("prepare 后英文源已改变；拒绝合并")
        expected_input, expected_manifest = _lock((work / "out/en.md").read_text(encoding="utf-8"))
        if manifest != expected_manifest or (directory / "input.md").read_text(encoding="utf-8") != expected_input:
            errors.append("翻译 input/manifest 已偏离已审核英文的确定性骨架，拒绝合并")
    except (OSError, ValueError) as exc:
        return "", errors + [f"翻译准备产物缺失或无效：{exc}"]
    tokens = {t["token"]: t for t in manifest["tokens"]}
    actual = TOKEN_RE.findall(locked)
    if actual != manifest["order"]:
        errors.append("翻译 token 遗漏、重复、改名或顺序改变")
    residue = TOKEN_RE.sub("", locked)
    if "⟦WS" in residue or "⟧" in residue:
        errors.append("翻译包含未知或损坏 token")
    if re.search(r"(?<!\\)\$|!\[|`|(?<!\\)\\[([]", residue):
        errors.append("翻译新增未授权数学、图片或代码语法")
    # Every free-text segment must remain inside its original paragraph block.
    inside, cursor = False, 0
    for match in TOKEN_RE.finditer(locked):
        if not inside and locked[cursor:match.start()].strip():
            errors.append("翻译在原段落骨架之外新增正文")
            break
        kind = tokens.get(match.group(), {}).get("kind")
        if kind == "block_begin":
            inside = True
        elif kind == "block_end":
            inside = False
        cursor = match.end()
    if not inside and locked[cursor:].strip():
        errors.append("翻译在原段落骨架之外新增正文")
    for block in manifest["blocks"]:
        if block["begin"] in locked and block["end"] in locked:
            content = locked.split(block["begin"], 1)[1].split(block["end"], 1)[0]
            if block["translatable"] and not TOKEN_RE.sub("", content).strip():
                errors.append(f"翻译段落 {block['begin']} 缺少正文")
            if re.search(r"\n[ \t]*\n", content.strip()):
                errors.append(f"翻译段落 {block['begin']} 新增段落分隔")
    if errors:
        return "", errors
    # Ignore formatting whitespace outside paragraph bounds. Restore exact source
    # separators, while each paragraph's translation remains the model's prose.
    restored = []
    cursor = 0
    for token in actual:
        index = locked.index(token, cursor)
        prior = locked[cursor:index]
        entry = tokens[token]
        if entry["kind"] == "block_begin":
            prior = prior.strip()
        elif entry["kind"] == "separator":
            prior = prior.rstrip()
        restored.extend((prior, entry["text"]))
        cursor = index + len(token)
    restored.append(locked[cursor:].strip())
    text = "".join(restored)
    errors.extend(compare_protected((work / "out/en.md").read_text(encoding="utf-8"), text))
    return text, errors


def merge(work: Path, locked_path: Path | None = None) -> dict:
    path = locked_path or work / "translation/zh.locked.md"
    try:
        text, errors = _restore(work, path.read_text(encoding="utf-8"))
        text, supplement_errors = _compose(work, text)
        errors.extend(supplement_errors)
    except (OSError, ValueError, KeyError) as exc:
        return {"ok": False, "errors": [f"不能读取/合并翻译：{exc}"]}
    if errors:
        return {"ok": False, "errors": errors}
    output = work / "out/zh.md"
    temporary = output.with_suffix(".md.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(output)
    return {"ok": True, "errors": [], "output": str(output)}


def check_translation(work: Path) -> dict:
    try:
        restored, errors = _restore(work, (work / "translation/zh.locked.md").read_text(encoding="utf-8"))
        restored, supplement_errors = _compose(work, restored)
        errors.extend(supplement_errors)
        output = work / "out/zh.md"
        if not output.exists() or output.read_text(encoding="utf-8") != restored:
            errors.append("out/zh.md 与本轮受保护翻译合并结果不同或缺失")
    except (OSError, ValueError, KeyError) as exc:
        errors = [f"翻译阶段产物缺失或无效：{exc}"]
    return {"ok": not errors, "errors": errors, "warnings": []}


def _compose(work: Path, translated: str) -> tuple[str, list[str]]:
    """Insert an optional analyst-authored Highlights supplement mechanically."""
    source = work / "out/en.md"
    supplemental = work / "out/highlights.md"
    if not source.is_file() or re.search(r"(?im)^##[ \t]+Highlights[ \t]*$", source.read_text(encoding="utf-8")) or not supplemental.exists():
        return translated, []
    extra = supplemental.read_text(encoding="utf-8").strip()
    errors = []
    if protected_spans(extra) or re.search(r"(?<!\\)\$|!\[|`|(?<!\\)\\[([]", extra):
        errors.append("highlights.md 补稿不能含数学、图片、代码或参考表")
    if not re.match(r"^##[ \t]+亮点\s*\n", extra) or len(re.findall(r"(?m)^[-*] ", extra)) not in range(3, 6) or ">【说明】" not in extra:
        errors.append("highlights.md 必须含 ## 亮点、3–5条列表和 >【说明】免责声明")
    headings = re.findall(r"(?m)^#{1,6} .+$", extra)
    if headings != ["## 亮点"]:
        errors.append("highlights.md 只能有亮点标题")
    if errors:
        return translated, errors
    abstract = re.search(r"(?m)^##[ \t]+摘要[ \t]*$", translated)
    if abstract is None:
        return translated, ["无法把 highlights.md 补稿插入 ## 摘要 前"]
    return translated[:abstract.start()] + extra + "\n\n" + translated[abstract.start():], []


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("review-source", "prepare", "merge", "check"))
    ap.add_argument("--work", required=True)
    ap.add_argument("--note", default="")
    args = ap.parse_args()
    work = Path(args.work).resolve()
    functions = {"prepare": prepare, "merge": merge, "check": check_translation}
    result = review_source(work, args.note) if args.command == "review-source" else functions[args.command](work)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
