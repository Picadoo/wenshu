"""Read explicitly numbered source references without renumbering or deduplication.

This module only uses source text and the standard library, so extraction and
verification can share the same evidence. An unnumbered bibliography returns
empty ``numbers`` and ``entries`` for the existing author-year parser to handle.
"""
from __future__ import annotations

import re
from collections import Counter


_PAGE = re.compile(r"(?m)^\s*<<< page \d+ >>>[^\S\n]*$")
_HEADING = re.compile(
    r"^(?:#{1,6}\s*)?(?:references|bibliography|literature\s+cited|参考文献|參考文獻)"
    r"(?=\s|[:：\[［]|$)\s*[:：]?\s*(.*)$", re.I,
)
_NUMBER = re.compile(
    r"^\s*(?:[\[［](\d{1,3})[\]］]|(\d{1,3})[.．)、])"
    r"(?:\s+|(?=[A-Za-zÀ-ÿ一-鿿])|$)(.*)$"
)
_AFTER_REFERENCES = re.compile(
    r"^(?:#{1,6}\s*)?(?:\d+(?:\.\d+)*\.?\s+)?(?:"
    r"acknowledg(?:e)?ments?|authors?['’]?\s+contributions?(?:\s+statement)?|"
    r"credit\s+authorship\s+contribution\s+statement|funding(?:\s+information)?|"
    r"declarations?|declaration\s+of\s+competing\s+interests?|competing\s+interests?|"
    r"conflicts?\s+of\s+interests?(?:\s+statement)?|data\s+availability(?:\s+statement)?|"
    r"additional\s+information|supplementary\s+(?:information|materials?)|"
    r"appendix(?:\s+[A-Z])?|appendices|nomenclature|publisher['’]s\s+note|open\s+access|"
    r"致谢|致謝|作者贡献|作者貢獻|基金资助|利益冲突|利益衝突|数据可用性|附录|附錄"
    r")(?:\s*[:：].*)?$", re.I,
)
_YEAR = re.compile(r"(?<!\d)(?:18|19|20)\d{2}(?!\d)")


def _numbered(line: str):
    match = _NUMBER.match(line)
    if match and int(match.group(1) or match.group(2)) > 0:
        return int(match.group(1) or match.group(2)), match.group(3)
    return None


def _source_lines(fulltext: str) -> list[str]:
    # PDF zero-width characters can split otherwise literal DOI strings.
    text = re.sub(r"[\u200b-\u200f\u2060\ufeff]", "", fulltext)
    pages = [[line.strip() for line in page.splitlines()] for page in _PAGE.split(text)]
    pages = [page for page in pages if any(page)]
    edge_keys: Counter[str] = Counter()
    before_references: set[str] = set()
    first_reference_page = next(
        (i for i, page in enumerate(pages) if any(_HEADING.match(line) for line in page)),
        len(pages),
    )
    for page_index, page in enumerate(pages):
        nonempty = [line for line in page if line]
        keys = set()
        for line in nonempty[:4] + nonempty[-6:]:
            if _numbered(line) or _HEADING.match(line) or _AFTER_REFERENCES.match(line):
                continue
            # Repeated reference fragments are still source entries. In
            # particular, don't strip repeated years, authors, or DOI lines.
            if "|" not in line and (
                _YEAR.search(line) or re.search(r"doi\.org/|10\.\d{4,9}/", line)
                or re.match(r"^[A-ZÀ-Þ][\w'’\-]+,\s*[A-Z]", line)
            ):
                continue
            if len(line) <= 180:
                keys.add(re.sub(r"\d+", "#", re.sub(r"\s+", " ", line.lower())))
        edge_keys.update(keys)
        if page_index < first_reference_page:
            before_references.update(keys)
    # Require a footer/header to recur on a substantial fraction of pages;
    # sharing a title or DOI across two source references is not deduplication.
    threshold = max(2, (len(pages) + 2) // 3)
    repeated = {
        key for key, count in edge_keys.items()
        if count >= threshold and (
            key in before_references or "|" in key
            or re.fullmatch(r"#|www\.\S+", key)
        )
    }
    result = []
    for page in pages:
        for line in page:
            key = re.sub(r"\d+", "#", re.sub(r"\s+", " ", line.lower()))
            if key not in repeated or _numbered(line):
                result.append(line)
    return result


def _join_entry(lines: list[str]) -> str:
    text = "\n".join(lines)
    text = re.sub(r"(\w)[-\u00ad]\n([a-z])", r"\1\2", text)
    text = re.sub(
        r"(https?://(?:dx\.)?doi\.org/\S+|10\.\d{4,9}/\S+)\n(?=[A-Za-z0-9./_-])",
        r"\1", text,
    )
    return " ".join(text.split())


def extract_numbered_references(fulltext: str) -> dict:
    """Return ``numbers``, ``entries`` (``num``/``text``), and ``warnings``.

    Only explicit [N]/N. markers following a References heading count. Source
    numbers and duplicate entries are preserved. Entries are sorted stably by
    their explicit numbers, allowing reference columns to arrive out of order.
    Missing or repeated numbers produce warnings; they are never filled in.
    """
    lines = _source_lines(fulltext)
    start = None
    first = ""
    for index, line in enumerate(lines):
        heading = _HEADING.match(line)
        if not heading:
            continue
        rest = heading.group(1)
        if rest and not _numbered(rest):
            continue
        following = rest or next((s for s in lines[index + 1:] if s), "")
        if _numbered(following):
            start, first = index + 1, rest
            break
    if start is None:
        return {"numbers": [], "entries": [], "warnings": []}

    entries: list[dict] = []
    number = None
    current: list[str] = []
    for line in ([first] if first else []) + lines[start:]:
        if not line or _HEADING.match(line):
            continue
        if _AFTER_REFERENCES.match(line):
            break
        marker = _numbered(line)
        if marker:
            if number is not None:
                entries.append({"num": number, "text": _join_entry(current)})
            number, body = marker
            current = [body]
        elif number is not None:
            current.append(line)
    if number is not None:
        entries.append({"num": number, "text": _join_entry(current)})
    # A heading plus a numeric line without bibliographic text is not evidence.
    if not entries or not any(re.search(r"[A-Za-zÀ-ÿ一-鿿]", e["text"]) for e in entries):
        return {"numbers": [], "entries": [], "warnings": []}

    entries.sort(key=lambda entry: entry["num"])
    numbers = [entry["num"] for entry in entries]
    warnings = []
    counts = Counter(numbers)
    repeated = sorted(num for num, count in counts.items() if count > 1)
    if repeated:
        warnings.append(f"Repeated source reference numbers: {repeated}")
    missing = sorted(set(range(1, max(numbers) + 1)) - set(numbers))
    if missing:
        warnings.append(f"Missing source reference numbers: {missing}")
    empty = [entry["num"] for entry in entries if not entry["text"]]
    if empty:
        warnings.append(f"Empty source references: {empty}")
    return {"numbers": numbers, "entries": entries, "warnings": warnings}
