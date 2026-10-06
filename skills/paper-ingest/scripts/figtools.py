#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
figtools.py — 图片核对、手工裁切和人工确认。

    python figtools.py sheet --work <workdir>                 # 生成 images/_sheet.png 总览图（缩略图 + 图号）
    python figtools.py crop  --work <workdir> --page 5 --num 3 --box x0,y0,x1,y1 [--unit px|pt]
        # 按 pages/p5.png 上量出的像素坐标（默认）重新裁出 <key>_page5_fig3.png，覆盖旧图
    python figtools.py crop  --work <workdir> --page 5 --num 3 --above-caption
        # 取图注上方整栏空当（矢量图兜底）
    python figtools.py check --work <workdir>                 # 空白 / 过小 / 纯文字的可疑裁图清单（JSON）
    python figtools.py compare --work <workdir> [--num 3]     # 原页框选与裁图并列；默认只生成未确认图
    python figtools.py review --work <workdir> --num 3 --note "已对照原页核对全部子图、轴与图例"
        # 仅在实际看过原页/并列图后调用；crop 和自动裁图都不会自动通过人工确认
"""
from __future__ import annotations

import argparse
import io
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pymupdf

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover
    Image = None


def utf8() -> None:
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def load(work: Path):
    meta = json.loads((work / "meta.json").read_text(encoding="utf-8"))
    stats_path = work / "stats.json"
    stats = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.exists() else {}
    return meta, stats


def load_report(work: Path, key: str = "") -> dict:
    path = work / "figcut.json"
    report = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"key": key, "figures": []}
    nums = [str(f["num"]) for f in report.get("figures", [])]
    if len(nums) != len(set(nums)):
        raise ValueError("figcut.json 含重复图号，先核对图号与文件映射")
    return report


def save_report(work: Path, report: dict) -> None:
    figs = report.get("figures", [])
    statuses = ("ok", "manual", "kept", "carry", "gap-fallback", "missing")
    report["summary"] = {s: sum(f.get("status") == s for f in figs) for s in statuses}
    report["reviewSummary"] = {"reviewed": sum(f.get("reviewed") is True for f in figs),
                               "pending": sum(f.get("reviewed") is not True for f in figs)}
    (work / "figcut.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


def figure_num(num: str) -> str:
    num = str(num).strip()
    if not re.fullmatch(r"(?:[A-Za-z]\.?)?\d{1,3}(?:\.\d{1,3})*[a-z]?", num):
        raise ValueError(f"无效图号：{num!r}")
    return num


def valid_rect(page: pymupdf.Page, vals) -> pymupdf.Rect:
    if not isinstance(vals, (list, tuple)) or len(vals) != 4 or not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in vals):
        raise ValueError("bbox 必须包含四个有限数值 x0,y0,x1,y1（PDF pt）")
    rect = pymupdf.Rect(vals)
    if rect.width <= 0 or rect.height <= 0:
        raise ValueError("bbox 为空或坐标顺序错误：必须 x0 < x1 且 y0 < y1")
    bounds = page.rect
    if rect.x0 < bounds.x0 or rect.y0 < bounds.y0 or rect.x1 > bounds.x1 or rect.y1 > bounds.y1:
        raise ValueError(f"bbox 越界：{list(rect)}，原页范围为 {list(bounds)}；不会静默截断")
    return rect


def image_path(work: Path, file: str) -> Path:
    if not isinstance(file, str) or not file or Path(file).name != file or "/" in file or "\\" in file:
        raise ValueError("file 必须是 images/ 下的精确文件名")
    return work / "images" / file


def clear_review(entry: dict) -> None:
    entry["reviewed"] = False
    entry.pop("reviewNote", None)
    entry.pop("reviewedAt", None)
    entry.pop("comparisonFile", None)
    entry.pop("comparisonError", None)


def geometry_errors(work: Path, entry: dict, doc: pymupdf.Document | None = None) -> list[str]:
    """检查已记录的来源几何；调用者可传已打开 PDF，避免逐图重复打开。"""
    errors = []
    label = f"Fig. {entry.get('num', '?')}"
    try:
        if not image_path(work, entry.get("file", "")).is_file():
            errors.append(f"{label}: 裁图文件不存在")
    except ValueError as exc:
        errors.append(f"{label}: {exc}")
    opened = None
    try:
        if doc is None:
            meta, _ = load(work)
            opened = pymupdf.open(meta["pdf"])
            doc = opened
        page_no = entry.get("sourcePage")
        if not isinstance(page_no, int) or isinstance(page_no, bool) or not 1 <= page_no <= len(doc):
            errors.append(f"{label}: sourcePage 必须是 PDF 范围内的 1-based 整数")
        else:
            valid_rect(doc[page_no - 1], entry.get("bbox", []))
    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
        errors.append(f"{label}: {exc}")
    finally:
        if opened is not None:
            opened.close()
    return errors


def review_errors(work: Path) -> list[str]:
    """供 verify/翻译入口复用的记录检查；不执行视觉内容判断。"""
    try:
        layout_data = json.loads((work / "out" / "layout.json").read_text(encoding="utf-8"))
        figures = layout_data.get("figures", [])
        if not figures:
            return []
        nums = [figure_num(f.get("num", "")) for f in figures]
        if len(nums) != len(set(nums)):
            return ["layout.json 含重复图号"]
        report = load_report(work)
        records = {str(f["num"]): f for f in report["figures"]}
        meta, _ = load(work)
        errors = []
        with pymupdf.open(meta["pdf"]) as doc:
            for num in nums:
                entry = records.get(num)
                if entry is None:
                    errors.append(f"Fig. {num}: 缺少 figcut.json 记录")
                    continue
                if entry.get("reviewed") is not True:
                    errors.append(f"Fig. {num}: 尚未完成原页人工核对（reviewed）")
                if not isinstance(entry.get("reviewNote"), str) or not entry["reviewNote"].strip():
                    errors.append(f"Fig. {num}: 缺少原页核对结论 reviewNote")
                if entry.get("status") == "missing":
                    errors.append(f"Fig. {num}: 裁图状态为 missing")
                errors.extend(geometry_errors(work, entry, doc=doc))
        return errors
    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
        return [f"裁图核对记录无效：{exc}"]


def comparison(work: Path, entry: dict) -> Path:
    """生成核对用图，不判断图片是否完整，不写 reviewed。"""
    if Image is None:
        raise ValueError("需要 Pillow")
    num = figure_num(entry["num"])
    meta, _ = load(work)
    source_page = entry.get("sourcePage")
    if not isinstance(source_page, int) or isinstance(source_page, bool):
        raise ValueError(f"Fig. {num} 缺少 sourcePage，不能推测原页")
    with pymupdf.open(meta["pdf"]) as doc:
        if not 1 <= source_page <= len(doc):
            raise ValueError(f"Fig. {num} sourcePage 越界")
        page = doc[source_page - 1]
        rect = valid_rect(page, entry.get("bbox", []))
        pix = page.get_pixmap(matrix=pymupdf.Matrix(1.3, 1.3), alpha=False)
        source = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        sx, sy = source.width / page.rect.width, source.height / page.rect.height
        draw = ImageDraw.Draw(source)
        draw.rectangle([(rect.x0 - page.rect.x0) * sx, (rect.y0 - page.rect.y0) * sy,
                        (rect.x1 - page.rect.x0) * sx, (rect.y1 - page.rect.y0) * sy], outline="red", width=3)
    with Image.open(image_path(work, entry.get("file", ""))) as image:
        cropped = image.convert("RGB")
    cropped.thumbnail((1000, 1250))
    top, gap = 54, 18
    canvas = Image.new("RGB", (source.width + cropped.width + gap * 3,
                               max(source.height, cropped.height) + top + gap), "white")
    canvas.paste(source, (gap, top))
    canvas.paste(cropped, (source.width + gap * 2, top))
    draw = ImageDraw.Draw(canvas)
    draw.text((gap, 8), f"Fig. {num} | source page {source_page} | bbox (pt): {entry['bbox']}", fill="black")
    draw.text((source.width + gap * 2, 29), f"crop: {entry['file']}", fill="black")
    out = work / "images" / f"_review_fig{num}.png"
    canvas.save(out)
    entry["comparisonFile"] = out.name
    entry.pop("comparisonError", None)
    return out


def compare(work: Path, nums: list[str] | None = None) -> list[Path]:
    report = load_report(work)
    selected = {figure_num(n) for n in nums} if nums else None
    entries = [f for f in report["figures"] if str(f["num"]) in selected] if selected else [
        f for f in report["figures"] if f.get("file") and f.get("reviewed") is not True]
    if selected and selected != {str(f["num"]) for f in entries}:
        raise ValueError("请求的图号不在 figcut.json 中")
    paths = [comparison(work, f) for f in entries]
    save_report(work, report)
    return paths


def review(work: Path, num: str, note: str) -> dict:
    """记录调用者已完成的原页视觉核对，不执行自动内容判定。"""
    num = figure_num(num)
    if not note.strip():
        raise ValueError("必须 --note 记录实际原页核对结论")
    report = load_report(work)
    entry = next((f for f in report["figures"] if str(f["num"]) == num), None)
    if entry is None or not entry.get("file") or entry.get("status") == "missing":
        raise ValueError(f"Fig. {num} 没有可确认的裁图")
    # 校验精确来源和文件，并保留同一份可查看的原页/裁图核对图。
    if not entry.get("comparisonFile") or not image_path(work, entry["comparisonFile"]).exists():
        comparison(work, entry)
    else:
        meta, _ = load(work)
        with pymupdf.open(meta["pdf"]) as doc:
            page_no = entry.get("sourcePage")
            if not isinstance(page_no, int) or isinstance(page_no, bool) or not 1 <= page_no <= len(doc):
                raise ValueError("sourcePage 无效，不能确认")
            valid_rect(doc[page_no - 1], entry.get("bbox", []))
        if not image_path(work, entry["file"]).is_file():
            raise ValueError("裁图文件不存在，不能确认")
    entry.update({"reviewed": True, "reviewNote": note.strip(),
                  "reviewedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    save_report(work, report)
    return entry


def sheet(work: Path, cols: int = 4, thumb: int = 260) -> Path:
    if Image is None:
        raise SystemExit("需要 Pillow")
    if (work / "figcut.json").exists():
        imgs = [(image_path(work, f["file"]), f"Fig. {f['num']} p{f.get('sourcePage', '?')}")
                for f in load_report(work)["figures"] if f.get("file") and image_path(work, f["file"]).is_file()]
    else:
        paths = [p for p in (work / "images").glob("*.png") if not p.name.startswith("_") and re.search(r"_page(\d+)", p.name)]
        paths.sort(key=lambda p: (int(re.search(r"_page(\d+)", p.name).group(1)), p.name))
        imgs = [(p, re.sub(r"^.*?_page", "p", p.stem)) for p in paths]
    if not imgs:
        raise SystemExit("images/ 为空")
    rows = (len(imgs) + cols - 1) // cols
    cell_h = thumb + 34
    canvas = Image.new("RGB", (cols * (thumb + 12) + 12, rows * cell_h + 12), "white")
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except Exception:
        font = ImageFont.load_default()
    for i, (p, label) in enumerate(imgs):
        with Image.open(p) as source:
            im = source.convert("RGB")
        im.thumbnail((thumb, thumb))
        x = 12 + (i % cols) * (thumb + 12)
        y = 12 + (i // cols) * cell_h
        canvas.paste(im, (x, y))
        draw.rectangle([x - 1, y - 1, x + im.width, y + im.height], outline="#999")
        label += f"  {im.width}x{im.height}"
        draw.text((x, y + thumb + 6), label, fill="black", font=font)
    out = work / "images" / "_sheet.png"
    canvas.save(out)
    return out


def crop(work: Path, page_no: int, num: str, box: str | None, unit: str, above_caption: bool, dpi: int | None = None) -> Path:
    num = figure_num(num)
    meta, stats = load(work)
    if dpi is None:
        dpi = stats.get("renderDpi", 100)
    report = load_report(work, meta["key"])
    prior = next((f for f in report["figures"] if str(f["num"]) == num), None)
    if bool(box) == bool(above_caption):
        raise ValueError("--box x0,y0,x1,y1 或 --above-caption 必须二选一")
    with pymupdf.open(meta["pdf"]) as doc:
        if not 1 <= page_no <= len(doc):
            raise ValueError(f"页码越界：{page_no}，PDF 共 {len(doc)} 页")
        page = doc[page_no - 1]
        if above_caption:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import extract  # noqa
            caps, _ = extract.page_figures(page, page_no)
            cap = next((c for c in caps if c[0] == num), None)
            if cap is None:
                raise ValueError(f"第 {page_no} 页没找到 Fig. {num} 的图注")
            rect = extract.gap_above_caption(page, cap[1]) or pymupdf.Rect(page.rect.x0 + 30, page.rect.y0 + 40, page.rect.x1 - 30, cap[1].y0 - 2)
            rect = valid_rect(page, list(rect))
        else:
            vals = [float(v) for v in box.split(",")]
            if unit == "px":
                if not isinstance(dpi, (int, float)) or isinstance(dpi, bool) or not math.isfinite(dpi) or dpi <= 0:
                    raise ValueError("dpi 必须为正数")
                vals = [v * 72.0 / dpi for v in vals]
            elif unit != "pt":
                raise ValueError("unit 必须是 px 或 pt")
            rect = valid_rect(page, vals)
        name = f"{meta['key']}_page{page_no}_fig{num}.png"
        out = work / "images" / name
        out.parent.mkdir(exist_ok=True)
        page.get_pixmap(matrix=pymupdf.Matrix(2.2, 2.2), clip=rect, alpha=False).save(out)
    entry = dict(prior or {"num": num, "page": page_no})
    # 每次手工重裁都是一次变更，包括同框重裁；旧确认不能覆盖新像素。
    clear_review(entry)
    entry.update({"num": num, "status": "manual", "sourcePage": page_no, "bbox": list(rect), "file": name})
    entry.pop("why", None)
    entry.pop("paddingClipped", None)
    if prior:
        report["figures"][report["figures"].index(prior)] = entry
    else:
        layout_path = work / "out" / "layout.json"
        if layout_path.exists():
            f = next((f for f in json.loads(layout_path.read_text(encoding="utf-8")).get("figures", []) if str(f["num"]) == num), None)
            if f:
                entry.update({"page": f.get("page", page_no), "caption": f.get("caption", "")})
        report["figures"].append(entry)
    save_report(work, report)
    comparison(work, entry)
    save_report(work, report)
    sheet(work)
    return out


def check(work: Path) -> list[dict]:
    if Image is None:
        raise SystemExit("需要 Pillow")
    meta, stats = load(work)
    problems = []
    figcut = work / "figcut.json"
    figs = json.loads(figcut.read_text(encoding="utf-8")).get("figures", []) if figcut.exists() else stats.get("figureList", [])
    for f in figs:
        if not f.get("file"):
            problems.append({"num": f["num"], "page": f["page"], "issue": "missing", "hint": "用 crop --above-caption 或 --box 手工裁"})
            continue
        p = image_path(work, f["file"])
        if not p.exists():
            problems.append({"num": f["num"], "file": f["file"], "issue": "missing-file"})
            continue
        im = Image.open(p).convert("L")
        w, h = im.size
        hist = im.histogram()
        dark = sum(hist[:200]) / (w * h)
        issue = None
        if w < 200 or h < 120:
            issue = "too-small"
        elif dark < 0.004:
            issue = "blank"
        if f.get("status") == "gap-fallback":
            issue = issue or "fallback-region"
        if issue:
            problems.append({"num": f["num"], "page": f["page"], "file": f["file"], "issue": issue,
                             "size": [w, h], "sourcePage": f.get("sourcePage"),
                             "hint": "对照 sourcePage 原页及 compare 并列图决定是否重裁"})
        if f.get("reviewed") is not True:
            problems.append({"num": f["num"], "file": f["file"], "issue": "unreviewed",
                             "hint": "实际看原页/compare 图后，用 review --num --note 记录确认"})
    return problems


def main() -> None:
    utf8()
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sheet"); s.add_argument("--work", required=True)
    c = sub.add_parser("crop"); c.add_argument("--work", required=True); c.add_argument("--page", type=int, required=True)
    c.add_argument("--num", required=True); c.add_argument("--box"); c.add_argument("--unit", default="px", choices=["px", "pt"])
    c.add_argument("--above-caption", action="store_true"); c.add_argument("--dpi", type=int, default=None, help="像素框取抽取时 renderDpi，旧工作区默认100；可显式覆盖")
    k = sub.add_parser("check"); k.add_argument("--work", required=True)
    v = sub.add_parser("compare"); v.add_argument("--work", required=True); v.add_argument("--num", action="append")
    r = sub.add_parser("review", help="仅在实际看过原页后记录人工确认")
    r.add_argument("--work", required=True); r.add_argument("--num", required=True); r.add_argument("--note", required=True)
    a = ap.parse_args()
    work = Path(a.work).resolve()
    try:
        if a.cmd == "sheet":
            print(sheet(work))
        elif a.cmd == "crop":
            print(crop(work, a.page, a.num, a.box, a.unit, a.above_caption, a.dpi))
        elif a.cmd == "compare":
            print(json.dumps([str(p) for p in compare(work, a.num)], ensure_ascii=False))
        elif a.cmd == "review":
            print(json.dumps(review(work, a.num, a.note), ensure_ascii=False))
        else:
            print(json.dumps(check(work), ensure_ascii=False, indent=1))
    except ValueError as exc:
        ap.error(str(exc))


if __name__ == "__main__":
    main()
