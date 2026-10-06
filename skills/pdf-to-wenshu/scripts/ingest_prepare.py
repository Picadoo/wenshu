#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""确定性入库前半段：DOI 增强 → 集群骨架 → 抽图 → 写出 job JSON。

内容（中译 / 英文重排 / 学习卡）仍由子代理填；本脚本不调用模型。
收尾用 ingest_finish.py（含 lint + 文枢 sync-vault）。

    python ingest_prepare.py --pdf "<pdf>" --domain "泥沙输运/CFD-DEM" \
        --paper-id "Example2024 示例论文" --translated-title "……"
"""
from __future__ import annotations

import io
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.config import load_config as load_skill_config  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent


def py() -> str:
    return sys.executable


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def elapsed(start: float) -> float:
    return round(time.perf_counter() - start, 3)


def load_cfg() -> dict:
    path = SKILL_DIR / "config.json"
    return load_skill_config(path)


def run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=cwd or SCRIPTS,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def last_json(stdout: str) -> dict:
    text = stdout.strip()
    start = text.find("{")
    if start < 0:
        raise RuntimeError(f"脚本没有输出 JSON：{text[-800:]}")
    return json.loads(text[start:])


def parse_figures(image_index: Path) -> list[dict]:
    """从 .images.md 抽出 filename+caption，写入 job 给内容子代理，避免编造图号。"""
    if not image_index or not image_index.is_file():
        return []
    figs: list[dict] = []
    cur: dict | None = None
    for line in image_index.read_text(encoding="utf-8").splitlines():
        if line.startswith("- 文件名："):
            if cur:
                figs.append(cur)
            cur = {"filename": line.split("：", 1)[1].strip()}
        elif cur and line.startswith("- 图注："):
            cur["caption"] = line.split("：", 1)[1].strip()
        elif cur and line.startswith("- 路径："):
            cur["path"] = line.split("：", 1)[1].strip()
    if cur:
        figs.append(cur)
    return figs


def extract_tables(pdf: Path, content_dir: Path, prefix: str) -> tuple[Path | None, dict | None]:
    """抽英文原表 → content/<pid>.tables.md，失败只警告不阻断入库。

    抽不到表的论文（综述、纯图文）本来就没表可抽，不该因此拦下整篇入库；
    `pymupdf4llm` 没装同理——退回到「译者照 PDF 手搓表格」的老路，慢但不断。
    """
    # 子进程 cwd 是 SCRIPTS，相对路径会被解析到脚本目录去，先绝对化
    out = (content_dir / f"{prefix}.tables.md").resolve()
    proc = subprocess.run(
        [py(), str(SCRIPTS / "extract_tables.py"), str(pdf.resolve()), str(out), "--pid", prefix],
        cwd=SCRIPTS,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    sys.stderr.write(proc.stderr or "")
    sys.stderr.write(proc.stdout or "")
    if proc.returncode:
        sys.stderr.write(f"警告：extract_tables 失败（exit {proc.returncode}），表格需人工重建。\n")
        return None, None
    coverage = None
    for line in (proc.stdout or "").splitlines():
        if line.startswith("TABLE_COVERAGE "):
            coverage = json.loads(line[len("TABLE_COVERAGE "):])
    if coverage and coverage.get("needsReview"):
        nums = "、".join(f"表{n}" for n in coverage["needsReview"])
        sys.stderr.write(f"提示：{nums} 有合并单元格，抽表脚本已标「需人工核对」。\n")
    if coverage and coverage.get("missing"):
        nums = "、".join(f"表{n}" for n in coverage["missing"])
        sys.stderr.write(f"警告：正文提到 {nums} 但没抽到，需人工补。\n")
    return (out if out.is_file() else None), coverage


def write_clean_txt(txt_path: Path) -> Path | None:
    if not txt_path or not txt_path.is_file():
        return None
    raw = txt_path.read_text(encoding="utf-8")
    cleaned = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", raw)
    out = txt_path.with_name(txt_path.stem + ".clean.txt")
    out.write_text(cleaned, encoding="utf-8")
    return out


def main() -> None:
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

    import argparse

    prepare_started_at = now_iso()
    prepare_started = time.perf_counter()
    stage_timings: dict[str, float] = {}
    cfg = load_cfg()
    ap = argparse.ArgumentParser(description="pdf-to-wenshu 确定性准备（DOI/骨架/抽图）")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--vault", default=cfg.get("vault"))
    ap.add_argument("--domain", required=True, help="大类/子类，须与文枢主题筛选一致")
    ap.add_argument("--paper-id", required=True, help="作者年份 中文短题")
    ap.add_argument("--translated-title", required=True)
    ap.add_argument("--folder-name", default=None)
    ap.add_argument("--doi", default=None,
                    help="手动指定 DOI（老扫描件 PDF 抽不出 DOI 时必给，否则文件夹会落成 Anon）")
    ap.add_argument("--mode", default=cfg.get("default_mode", "beginner"))
    ap.add_argument("--archive", default="copy", choices=["move", "copy"])
    ap.add_argument("--relaxed", action="store_true",
                    help="兼容旧库：新论文默认严格验收；传此参数允许警告通过")
    args = ap.parse_args()

    # 所有子脚本都以 SCRIPTS 为 cwd；入口路径若保持相对形式，会被错误地解析到
    # skill/scripts 下，出现“主进程看得到 PDF、子进程却报不存在”的假失败。
    vault = Path(args.vault).resolve()
    pdf = Path(args.pdf).resolve()
    if not pdf.is_file():
        raise SystemExit(f"PDF 不存在: {pdf}")

    work = vault / "90_系统" / "_ingest"
    work.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]+', "_", args.paper_id).strip()
    meta_path = work / f"{safe}.meta.json"
    terms_path = work / f"{safe}.terms.json"
    job_path = work / f"{safe}.job.json"

    enrich_cmd = [py(), str(SCRIPTS / "doi_enrich.py"), "--pdf", str(pdf), "--out", str(meta_path)]
    if args.doi:
        enrich_cmd += ["--doi", args.doi]
    stage_started = time.perf_counter()
    enrich = run(enrich_cmd)
    stage_timings["doiEnrich"] = elapsed(stage_started)
    sys.stderr.write(enrich.stderr)
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else last_json(enrich.stdout)
    if not meta_path.is_file():
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    folder = args.folder_name or meta.get("suggestedFolder") or args.paper_id
    stage_started = time.perf_counter()
    gen = run(
        [
            py(),
            str(SCRIPTS / "generate_cluster.py"),
            "--paper-id",
            args.paper_id,
            "--folder-name",
            folder,
            "--domain",
            args.domain,
            "--pdf",
            str(pdf),
            "--meta",
            str(meta_path),
            "--vault",
            str(vault),
            "--translated-title",
            args.translated_title,
            "--mode",
            args.mode,
            "--archive",
            args.archive,
        ]
    )
    stage_timings["generateCluster"] = elapsed(stage_started)
    sys.stderr.write(gen.stderr)
    cluster = last_json(gen.stdout)

    pdf_path = Path(cluster["pdfPath"])
    images_dir = Path(cluster["imagesDir"])
    image_index = Path(cluster["imageIndexPath"])
    prefix = cluster["paperId"]
    stage_started = time.perf_counter()
    img = subprocess.run(
        [
            py(),
            str(SCRIPTS / "extract_images.py"),
            str(pdf_path),
            str(images_dir),
            str(image_index),
            "--prefix",
            prefix,
        ],
        cwd=SCRIPTS,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stage_timings["extractImages"] = elapsed(stage_started)
    sys.stderr.write(img.stderr or "")
    sys.stderr.write(img.stdout or "")
    if img.returncode:
        raise SystemExit(f"extract_images 失败（exit {img.returncode}）")

    stage_started = time.perf_counter()
    table_index, table_coverage = extract_tables(pdf_path, Path(cluster["contentDir"]), prefix)
    stage_timings["extractTables"] = elapsed(stage_started)

    fulltext = Path(cluster["fulltextPath"]) if cluster.get("fulltextPath") else None
    stage_started = time.perf_counter()
    clean = write_clean_txt(fulltext) if fulltext else None
    stage_timings["cleanFulltext"] = elapsed(stage_started)
    figures = parse_figures(image_index)
    if len(figures) < 3:
        sys.stderr.write(f"警告：只抽出 {len(figures)} 张图，正文 Figure 可能被漏抽。\n")
    wenshu = Path(cfg["wenshu"]) if cfg.get("wenshu") else SKILL_DIR.parent.parent / "wenshu-pro"

    job = {
        "paperId": cluster["paperId"],
        "domain": args.domain,
        "vault": str(vault),
        "wenshu": str(wenshu),
        "lang": meta.get("detectedSourceLanguage") or "en",
        "metaPath": str(meta_path),
        "termsJson": str(terms_path),
        "pdfPath": str(pdf_path),
        "fulltextPath": str(fulltext) if fulltext else None,
        "cleanFulltextPath": str(clean) if clean else None,
        "imagesDir": str(images_dir),
        "imageIndexPath": str(image_index),
        "figures": figures,
        "tableIndexPath": str(table_index) if table_index else None,
        "tableCoverage": table_coverage,
        "clusterDir": cluster["clusterDir"],
        "contentDir": cluster["contentDir"],
        "notes": cluster["notes"],
        "title": meta.get("title"),
        "translatedTitle": args.translated_title,
        "strict": not args.relaxed,
        "source": {
            "type": "pdf",
            "inputPath": str(pdf.resolve()),
            "preparedFromPdf": True,
        },
        "timing": {
            "prepare": {
                "startedAt": prepare_started_at,
                "finishedAt": now_iso(),
                "durationSec": elapsed(prepare_started),
                "stages": stage_timings,
            }
        },
        "englishWorkflow": {
            "mode": "draft-patch",
            "cFallbackReason": None,
        },
        "contentRoles": {
            "translation": "gpt-5.6-luna/max",
            "analysis": "main-agent",
        },
        "status": "skeleton",
    }
    job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"job": str(job_path), **job}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
