#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prepare chapter-aligned Luna A fragments and merge their Markdown outputs."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
TEMPLATE = SKILL_DIR / "references" / "luna-a-part-brief.md"
HEADING_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\.\s+([^\r\n]{1,140})\s*$")
REFERENCES_RE = re.compile(r"^\s*references\s*$", re.I)
ARTICLE_RE = re.compile(r"(<!--ARTICLE-->)(.*?)(<!--/ARTICLE-->)", re.S)
IMAGE_RE = re.compile(r"!\[\[([^|\]]+)\|700\]\]")
TABLE_SEPARATOR_RE = re.compile(r"(?m)^\|(?:\s*:?-+:?\s*\|)+$")
IMAGE_INDEX_NAME_RE = re.compile(r"(?m)^- 文件名：(.+?)\s*$")
TABLE_INDEX_TOTAL_RE = re.compile(r"(?m)^总计：\s*(\d+)\s*张表格\s*$")
IMAGE_LINE_RE = re.compile(r"^!\[\[([^|\]]+)\|700\]\]\s*$")
FIGURE_CAPTION_LINE_RE = re.compile(r"^\*\*图\s*\d+[^*]*\*\*")
TABLE_CAPTION_LINE_RE = re.compile(r"^\*\*表\s*(\d+)[^*]*\*\*")
NUMBERED_HEADING_RE = re.compile(r"^#{2,6}\s+(\d+(?:\.\d+)*)\s+(.+)$")


def require(job: dict, dotted: str):
    value = job
    for key in dotted.split("."):
        if not isinstance(value, dict) or key not in value:
            raise ValueError(f"job 缺字段：{dotted}")
        value = value[key]
    if value is None or str(value).strip() == "":
        raise ValueError(f"job 字段为空：{dotted}")
    return value


def section_blocks(lines: list[str]) -> list[tuple[int, int, list[str]]]:
    end = next((i for i, line in enumerate(lines) if REFERENCES_RE.match(line)), len(lines))
    starts = [0]
    headings: dict[int, str] = {}
    for i, line in enumerate(lines[:end]):
        match = HEADING_RE.match(line)
        if match:
            starts.append(i)
            headings[i] = f"{match.group(1)} {match.group(2).strip()}"
    starts = sorted(set(starts))
    blocks = []
    for pos, start in enumerate(starts):
        stop = starts[pos + 1] if pos + 1 < len(starts) else end
        if stop <= start or not any(line.strip() for line in lines[start:stop]):
            continue
        block_headings = [headings[start]] if start in headings else ["题名、亮点与摘要"]
        blocks.append((start, stop, block_headings))
    return blocks


def balanced_ranges(lines: list[str], parts: int) -> list[tuple[int, int, list[str]]]:
    blocks = section_blocks(lines)
    if not blocks:
        raise ValueError("全文在 References 之前没有可用内容")
    parts = max(1, min(parts, len(blocks)))
    weights = [sum(len(line) + 1 for line in lines[start:stop]) for start, stop, _ in blocks]
    prefix = [0]
    for weight in weights:
        prefix.append(prefix[-1] + weight)

    inf = float("inf")
    dp = [[inf] * (len(blocks) + 1) for _ in range(parts + 1)]
    back = [[-1] * (len(blocks) + 1) for _ in range(parts + 1)]
    dp[0][0] = 0
    for count in range(1, parts + 1):
        for end in range(count, len(blocks) + 1):
            for split in range(count - 1, end):
                score = max(dp[count - 1][split], prefix[end] - prefix[split])
                if score < dp[count][end]:
                    dp[count][end] = score
                    back[count][end] = split

    groups = []
    end = len(blocks)
    for count in range(parts, 0, -1):
        split = back[count][end]
        groups.append((split, end))
        end = split
    groups.reverse()

    result = []
    for first, last in groups:
        start_line = blocks[first][0]
        stop_line = blocks[last - 1][1]
        group_headings = [heading for _, _, hs in blocks[first:last] for heading in hs]
        result.append((start_line, stop_line, group_headings))
    return result


def render_brief(values: dict[str, str]) -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    unresolved = [part.split("}}", 1)[0] for part in text.split("{{")[1:]]
    if unresolved:
        raise ValueError(f"分片简报存在未解析占位符：{', '.join(unresolved)}")
    return text


def expected_images(job: dict) -> list[str]:
    if "figures" in job:
        return [row["filename"] for row in job["figures"] if row.get("filename")]
    index_path = Path(require(job, "imageIndexPath"))
    return IMAGE_INDEX_NAME_RE.findall(index_path.read_text(encoding="utf-8"))


def expected_table_count(job: dict) -> int:
    coverage = job.get("tableCoverage", {})
    if "total" in coverage:
        return int(coverage["total"])
    index_path = Path(require(job, "tableIndexPath"))
    match = TABLE_INDEX_TOTAL_RE.search(index_path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"无法从表格索引读取总数：{index_path}")
    return int(match.group(1))


def prepare(job_path: Path, out_dir: Path, parts: int) -> dict:
    job = json.loads(job_path.read_text(encoding="utf-8"))
    source_path = Path(job.get("cleanFulltextPath") or require(job, "fulltextPath"))
    lines = source_path.read_text(encoding="utf-8").splitlines()
    ranges = balanced_ranges(lines, parts)
    out_dir.mkdir(parents=True, exist_ok=True)
    template_values = {
        "PART_COUNT": str(len(ranges)),
        "IMAGE_INDEX_PATH": str(require(job, "imageIndexPath")),
        "TABLE_INDEX_PATH": str(require(job, "tableIndexPath")),
        "PDF_PATH": str(require(job, "pdfPath")),
    }
    rows = []
    for index, (start, stop, headings) in enumerate(ranges, 1):
        source_out = (out_dir / f"part-{index:02d}.source.txt").resolve()
        output_out = (out_dir / f"part-{index:02d}.zh.md").resolve()
        brief_out = (out_dir / f"part-{index:02d}.task.md").resolve()
        source_out.write_text("\n".join(lines[start:stop]).rstrip() + "\n", encoding="utf-8")
        boundary = (
            "这是第一个片段：从 H1 开始，写作者、单位、期刊三段，并包含 `## 亮点`、"
            "`## 摘要` 和摘要末尾 `**关键词：**`。"
            if index == 1 else
            "这不是第一个片段：直接从本片第一个编号章节标题开始，不写 H1、作者、亮点、摘要或关键词。"
        )
        if index == len(ranges):
            boundary += " 这是最后一个片段：写完结论、作者贡献/利益冲突/致谢等 References 之前的原文；不要写参考文献。"
        values = dict(template_values)
        values.update({
            "PART_INDEX": str(index),
            "OUTPUT_PATH": str(output_out),
            "PART_SOURCE_PATH": str(source_out),
            "SOURCE_START": str(start + 1),
            "SOURCE_END": str(stop),
            "HEADINGS": "；".join(headings),
            "BOUNDARY_RULES": boundary,
        })
        brief_out.write_text(render_brief(values), encoding="utf-8")
        rows.append({
            "index": index,
            "sourceStart": start + 1,
            "sourceEnd": stop,
            "headings": headings,
            "sourcePath": str(source_out),
            "outputPath": str(output_out),
            "briefPath": str(brief_out),
        })
    manifest = {
        "jobPath": str(job_path.resolve()),
        "paperId": require(job, "paperId"),
        "targetPath": str(Path(require(job, "notes.article")).resolve()),
        "expectedImages": expected_images(job),
        "expectedTables": expected_table_count(job),
        "parts": rows,
    }
    manifest_path = (out_dir / "manifest.json").resolve()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["manifestPath"] = str(manifest_path)
    return manifest


def clean_fragment(text: str) -> str:
    text = text.strip()
    if text.startswith("```") and text.endswith("```"):
        text = re.sub(r"^```(?:markdown)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    if "<!--ARTICLE" in text:
        raise ValueError("分片不得包含 ARTICLE 标记")
    if re.search(r"(?im)^##\s+参考文献\s*$", text):
        raise ValueError("分片不得写参考文献节")
    return text.strip()


def normalize_numbered_headings(text: str) -> str:
    lines = []
    for line in text.splitlines():
        match = NUMBERED_HEADING_RE.match(line)
        if match:
            level = 2 + match.group(1).count(".")
            line = "#" * level + " " + match.group(1) + " " + match.group(2)
        lines.append(line)
    return "\n".join(lines).strip()


def dedupe_fragment_assets(
    text: str, seen_images: set[str], seen_tables: set[str]
) -> tuple[str, list[str], list[str]]:
    """Keep the first cross-fragment image/table occurrence from a two-column dump."""
    lines = text.splitlines()
    out: list[str] = []
    removed_images: list[str] = []
    removed_tables: list[str] = []
    i = 0
    while i < len(lines):
        image = IMAGE_LINE_RE.match(lines[i].strip())
        if image:
            name = image.group(1)
            if name in seen_images:
                removed_images.append(name)
                i += 1
                while i < len(lines) and not lines[i].strip():
                    i += 1
                if i < len(lines) and FIGURE_CAPTION_LINE_RE.match(lines[i].strip()):
                    i += 1
                while i < len(lines) and not lines[i].strip():
                    i += 1
                continue
            seen_images.add(name)

        table = TABLE_CAPTION_LINE_RE.match(lines[i].strip())
        if table:
            number = table.group(1)
            if number in seen_tables:
                removed_tables.append(number)
                i += 1
                while i < len(lines) and not lines[i].strip():
                    i += 1
                while i < len(lines) and lines[i].lstrip().startswith("|"):
                    i += 1
                while i < len(lines) and not lines[i].strip():
                    i += 1
                continue
            seen_tables.add(number)

        out.append(lines[i])
        i += 1
    return "\n".join(out).strip(), removed_images, removed_tables


def merge(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fragments = []
    seen_images: set[str] = set()
    seen_tables: set[str] = set()
    deduped_images: list[str] = []
    deduped_tables: list[str] = []
    for row in manifest["parts"]:
        path = Path(row["outputPath"])
        if not path.is_file():
            raise ValueError(f"缺分片输出：{path}")
        fragment = normalize_numbered_headings(clean_fragment(path.read_text(encoding="utf-8")))
        fragment, removed_images, removed_tables = dedupe_fragment_assets(
            fragment, seen_images, seen_tables
        )
        deduped_images.extend(removed_images)
        deduped_tables.extend(removed_tables)
        fragments.append(fragment)
    body = "\n\n".join(fragments).strip() + "\n"
    images = IMAGE_RE.findall(body)
    expected_images = manifest.get("expectedImages", [])
    missing = [name for name in expected_images if name not in images]
    unexpected = [name for name in images if expected_images and name not in expected_images]
    duplicate = sorted({name for name in images if images.count(name) > 1})
    tables = len(TABLE_SEPARATOR_RE.findall(body))
    expected_tables = int(manifest.get("expectedTables", 0))
    errors = []
    if missing:
        errors.append("缺图片：" + "、".join(missing))
    if unexpected:
        errors.append("未知图片：" + "、".join(unexpected))
    if duplicate:
        errors.append("重复图片：" + "、".join(duplicate))
    if expected_tables and tables != expected_tables:
        errors.append(f"表格数 {tables}，期望 {expected_tables}")
    if body.count("$$") % 2:
        errors.append("$$ 定界符未配对")
    if "TODO" in body:
        errors.append("仍有 TODO")
    if len(re.findall(r"(?m)^#\s+", body)) != 1:
        errors.append("H1 必须恰好 1 个")
    for heading in ("## 亮点", "## 摘要"):
        if heading not in body:
            errors.append(f"缺 {heading}")
    if errors:
        raise ValueError("；".join(errors))

    target = Path(manifest["targetPath"])
    original = target.read_text(encoding="utf-8")
    if len(ARTICLE_RE.findall(original)) != 1:
        raise ValueError("目标 ARTICLE 标记必须恰好一对")
    backup = manifest_path.parent / (target.name + ".before-parallel-a.md")
    if not backup.exists():
        shutil.copy2(target, backup)
    merged = ARTICLE_RE.sub(lambda m: m.group(1) + "\n" + body + m.group(3), original, count=1)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(merged, encoding="utf-8")
    tmp.replace(target)
    return {
        "targetPath": str(target),
        "parts": len(fragments),
        "characters": len(body),
        "equations": len(re.findall(r"\\tag\{\d+\}", body)),
        "images": len(images),
        "tables": tables,
        "dedupedImages": deduped_images,
        "dedupedTables": deduped_tables,
        "backupPath": str(backup),
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="准备/合并 Luna A 章节并行分片")
    sub = ap.add_subparsers(dest="action", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--job", required=True)
    prep.add_argument("--out-dir", required=True)
    prep.add_argument("--parts", type=int, default=3)
    join = sub.add_parser("merge")
    join.add_argument("--manifest", required=True)
    args = ap.parse_args()
    try:
        if args.action == "prepare":
            result = prepare(Path(args.job).resolve(), Path(args.out_dir).resolve(), args.parts)
        else:
            result = merge(Path(args.manifest).resolve())
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
