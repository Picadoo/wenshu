#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cutfigs.py — 按核准清单 out/layout.json 裁图、嵌图。

    python cutfigs.py --work <workdir> [--embed] [--force] [--zoom 2.2]

读 out/layout.json 的 figures（num / page / caption），逐张：在该页（找不到再看前后页）定位图注 →
栅格图框 ∪ 矢量簇 → 与图注就近配对 → 裁 zoom 倍整幅图到 images/<key>_pageP_figN.png；
没有图区时取图注上方空当（gap-fallback）；上一页尾部的无图注大图区留给下一页的图注（跨页图）。
已存在的裁图默认不动（AI 用 figtools 手工重裁过的不会被覆盖），--force 才全部重裁。
--embed：把 `![[文件|700]]` 插到 out/en.md、out/zh.md 每条 `**Fig. N.**` / `**图 N.**` 图注上方（幂等）。
产出 figcut.json（每张 ok / gap-fallback / carry / missing / kept / manual）、images/_sheet.png
及未确认图的 images/_review_figN.png 原页/裁图并列图。自动成功仅表示候选，默认 reviewed=false。
"""
from __future__ import annotations

import argparse
import io
import json
import math
import re
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract  # noqa: E402
import layout  # noqa: E402
import figtools  # noqa: E402

EN_CAP = re.compile(r"^\*\*(?:Fig\.?|Figure)\s*((?:[A-Z]\.?)?\d{1,3}(?:\.\d{1,3})*)[a-z]?\.?\*\*", re.I)
ZH_CAP = re.compile(r"^\*\*图\s*((?:[A-Z]\.?)?\d{1,3}(?:\.\d{1,3})*)\.?\*\*")
EMBED = re.compile(r"!\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]")


def utf8() -> None:
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(s).lower())


def load_layout(work: Path) -> dict:
    p = work / "out" / "layout.json"
    if not p.exists():
        raise SystemExit(f"缺 {p}：先排版，把图/表/公式清单写进 out/layout.json 再裁图")
    data = json.loads(p.read_text(encoding="utf-8"))
    figs = []
    for f in data.get("figures", []):
        num = str(f.get("num", "")).strip()
        if not num:
            continue
        figs.append({"num": num, "page": int(f.get("page") or 0), "caption": str(f.get("caption", "")).strip()})
    nums = [norm(f["num"]) for f in figs]
    if len(nums) != len(set(nums)):
        raise ValueError("layout.json 含重复图号，不能确定图片映射")
    for f in figs:
        figtools.figure_num(f["num"])
    return {"figures": figs}


def find_caption(page: pymupdf.Page, pno: int, num: str, caption: str):
    """返回 (Rect, text, regions) 或 None。先按图号，再按图注文字前缀。"""
    caps, regions = extract.page_figures(page, pno)
    for n, r, t in caps:
        if norm(n) == norm(num):
            return r, t, regions
    key = norm(re.sub(r"^\s*(?:Fig\.?|Figure|FIG\.?|图)\s*(?:[A-Z]\.?)?\d{1,3}(?:\.\d{1,3})*[a-z]?\s*[.:：]?", "", caption))[:24]
    if len(key) >= 12:
        for r, raw in layout.text_blocks(page):
            if norm(raw).startswith(key):
                return r, " ".join(raw.split()), regions
    return None


def cut(work: Path, zoom: float, force: bool) -> dict:
    if not math.isfinite(zoom) or zoom <= 0:
        raise ValueError("zoom 必须是有限正数")
    meta = json.loads((work / "meta.json").read_text(encoding="utf-8"))
    key = meta["key"]
    lay = load_layout(work)
    previous = {str(f["num"]): f for f in figtools.load_report(work, key)["figures"]}
    out_dir = work / "images"
    out_dir.mkdir(exist_ok=True)
    report: list[dict] = []
    changed = False
    with pymupdf.open(meta["pdf"]) as doc:
        # 保留已记录的精确文件与几何信息；手工裁图即使没有可提取图注也有效。
        located: dict[int, list[tuple[str, pymupdf.Rect, str, dict]]] = {}
        for f in lay["figures"]:
            old = previous.get(f["num"])
            if old and old.get("file") and figtools.image_path(work, old["file"]).is_file() and not force:
                entry = dict(old)
                entry.update({"num": f["num"], "listedPage": f["page"]})
                if entry.get("status") != "manual":
                    entry["status"] = "kept"
                entry.setdefault("reviewed", False)
                report.append(entry)
                continue
            hit = None
            for pno in [f["page"], f["page"] + 1, f["page"] - 1]:
                if 1 <= pno <= len(doc):
                    got = find_caption(doc[pno - 1], pno, f["num"], f["caption"])
                    if got:
                        hit = (pno, got)
                        break
            if not hit:
                report.append({"num": f["num"], "page": f["page"], "file": "", "status": "missing", "reviewed": False,
                               "why": "在清单页及前后页都没找到这条图注；用 figtools.py crop --box 手工裁"})
                continue
            pno, (rect, text, _) = hit
            located.setdefault(pno, []).append((f["num"], rect, text, f))

        carry: list[pymupdf.Rect] = []
        carry_page = 0
        for pno in (range(1, len(doc) + 1) if located else []):
            page = doc[pno - 1]
            caps = located.get(pno, [])
            captions, regions = extract.page_figures(page, pno)
            # 已保留图的原图注也参加配对，避免它的图区被误当作下一页的跨页图。
            known = {norm(n) for n, _, _ in captions}
            captions += [(n, r, t) for n, r, t, _ in caps if norm(n) not in known]
            assigned, unassigned = extract.assign_regions(captions, regions, page.rect)
            for n, cr, text, f in caps:
                entry = {"num": n, "page": pno, "listedPage": f["page"], "caption": text, "reviewed": False}
                rect = assigned.get(n)
                src = page
                status = "ok"
                if rect is None and carry and carry_page == pno - 1:
                    src, rect, status = doc[pno - 2], carry.pop(0), "carry"
                if rect is None:
                    rect = extract.gap_above_caption(page, cr)
                    status = "gap-fallback"
                if rect is None:
                    entry.update({"file": "", "status": "missing", "why": "找到图注但没找到图区，也没有空当；手工裁"})
                    report.append(entry)
                    continue
                try:
                    rect = figtools.valid_rect(src, list(rect))
                except ValueError as exc:
                    entry.update({"file": "", "status": "missing", "why": str(exc)})
                    report.append(entry)
                    continue
                padded = pymupdf.Rect(rect.x0 - 4, rect.y0 - 4, rect.x1 + 4, rect.y1 + 4)
                rect = padded & src.rect
                source_page = src.number + 1
                name = f"{key}_page{source_page}_fig{n}.png"
                target = out_dir / name
                # 旧图片没有可信的来源记录时不猜 bbox，也不覆盖手工结果。
                if target.exists() and not force:
                    entry.update({"file": name, "status": "kept",
                                  "why": "旧图片没有 figcut 来源记录；用 crop 明确原页与 bbox 后再确认"})
                    report.append(entry)
                    continue
                src.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=rect, alpha=False).save(target)
                changed = True
                entry.update({"file": name, "status": status, "sourcePage": source_page, "bbox": list(rect)})
                if padded != rect:
                    entry["paddingClipped"] = True
                report.append(entry)
            big = [r for r in unassigned if r.width >= 150 and r.height >= 100]
            carry, carry_page = (big, pno) if (big and not captions) else ([], 0)

    report.sort(key=lambda e: (int(re.sub(r"\D", "", e["num"]) or 0), e["num"]))
    result = {"key": key, "figures": report}
    figtools.save_report(work, result)
    try:
        if any(e["file"] for e in report) and (changed or not (out_dir / "_sheet.png").exists()):
            figtools.sheet(work)
    except Exception as exc:  # 没装 Pillow 等：不影响裁图
        result["sheetError"] = str(exc)
    for entry in report:
        if entry.get("file") and entry.get("sourcePage") and entry.get("bbox") and entry.get("reviewed") is not True:
            if entry.get("comparisonFile") and figtools.image_path(work, entry["comparisonFile"]).is_file():
                continue
            try:
                figtools.comparison(work, entry)
            except Exception as exc:
                entry["comparisonError"] = str(exc)
    figtools.save_report(work, result)
    return result


def embed(work: Path, result: dict) -> dict:
    """按图号插入/纠正精确文件映射；保持其他正文不动。"""
    files = {norm(e["num"]): e["file"] for e in result["figures"] if e.get("file")}
    done: dict[str, int] = {}
    for name, cap_re in (("en.md", EN_CAP), ("zh.md", ZH_CAP)):
        p = work / "out" / name
        if not p.exists():
            continue
        lines = p.read_text(encoding="utf-8").splitlines()
        out: list[str] = []
        inserted = 0
        for line in lines:
            m = cap_re.match(line.strip())
            if m:
                file = files.get(norm(m.group(1)))
                prev = [j for j in range(max(0, len(out) - 3), len(out)) if out[j].strip()]
                previous = prev[-1] if prev else None
                old_embed = EMBED.fullmatch(out[previous].strip()) if previous is not None else None
                has_embed = old_embed is not None
                if file and old_embed and old_embed.group(1) != file:
                    out[previous] = f"![[{file}|700]]"
                    inserted += 1
                if file and not has_embed:
                    if out and out[-1].strip():
                        out.append("")
                    out.append(f"![[{file}|700]]")
                    out.append("")
                    inserted += 1
            out.append(line)
        if inserted:
            p.write_text("\n".join(out) + "\n", encoding="utf-8")
        done[name] = inserted
    return done


def main() -> None:
    utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--embed", action="store_true", help="把嵌图行插到 en.md / zh.md 图注上方")
    ap.add_argument("--force", action="store_true", help="已存在的裁图也重裁")
    ap.add_argument("--zoom", type=float, default=2.2)
    a = ap.parse_args()
    work = Path(a.work).resolve()
    try:
        result = cut(work, a.zoom, a.force)
    except ValueError as exc:
        ap.error(str(exc))
    if a.embed:
        result["embedded"] = embed(work, result)
    print(json.dumps({k: v for k, v in result.items() if k != "figures"}, ensure_ascii=False))
    for e in result["figures"]:
        if e["status"] in ("missing", "gap-fallback", "carry"):
            print(f"  Fig. {e['num']} p{e['page']}: {e['status']} {e.get('why', '')}")


if __name__ == "__main__":
    main()
