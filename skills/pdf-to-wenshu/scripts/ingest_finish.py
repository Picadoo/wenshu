#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""确定性入库后半段：术语对账 → 清标记 → 断链降级 → 文稿纠错 → 参考文献 → 质检 → 检索层/bib → 文枢 sync-vault。

    python ingest_finish.py --paper-id "Example2024 交汇角侧向来沙"
    python ingest_finish.py --job "<vault>/90_系统/_ingest/<pid>.job.json"
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
    return load_skill_config(SKILL_DIR / "config.json")


def job_path_for(vault: Path, pid: str) -> Path:
    safe = re.sub(r'[\\/:*?"<>|]+', "_", pid).strip()
    return vault / "90_系统" / "_ingest" / f"{safe}.job.json"


def save_job(job: dict, vault: Path, pid: str) -> None:
    try:
        job_path_for(vault, pid).write_text(
            json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass


def strict_preflight(job: dict) -> list[str]:
    """Fail before mutating the vault when a promised content artifact is absent."""
    issues: list[str] = []
    notes = job.get("notes") or {}
    required = {
        "index": notes.get("index"),
        "中文正文": notes.get("article"),
        "学习笔记": notes.get("notes"),
    }
    lang = str(job.get("lang") or "en").lower()
    if not lang.startswith("zh"):
        required["英文正文"] = notes.get("articleEn")

    placeholders = {
        "index": ("待分析子代理填充", "[SCORE]", "status: skeleton"),
        "中文正文": ("待翻译子代理填充", "待**翻译子代理**填充"),
        "英文正文": ("待英文重排子代理填充", "待**英文重排子代理**填充"),
        "学习笔记": ("待笔记子代理填充", "（待填充）"),
    }
    for label, raw_path in required.items():
        path = Path(raw_path) if raw_path else None
        if not path or not path.is_file():
            issues.append(f"缺少{label}文件")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text.strip()) < 200:
            issues.append(f"{label}内容过短")
        for marker in placeholders.get(label, ()):
            if marker in text:
                issues.append(f"{label}仍含占位内容：{marker}")

    terms_path = Path(job.get("termsJson") or "")
    if not terms_path.is_file():
        issues.append("缺少 terms.json")
    else:
        try:
            terms = json.loads(terms_path.read_text(encoding="utf-8"))
            if not isinstance(terms, list) or not terms:
                issues.append("terms.json 必须是非空数组")
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(f"terms.json 无法解析：{exc}")
    return issues


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=SCRIPTS, check=False, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    if proc.stdout:
        sys.stderr.write(proc.stdout)
    if check and proc.returncode:
        raise SystemExit(f"失败 ({proc.returncode}): {' '.join(cmd[:4])} …")
    return proc


def load_job(args, cfg: dict) -> dict:
    if args.job:
        path = Path(args.job)
        return json.loads(path.read_text(encoding="utf-8"))
    vault = Path(args.vault or cfg["vault"])
    if args.paper_id:
        cand = vault / "90_系统" / "_ingest" / f"{args.paper_id}.job.json"
        if cand.is_file():
            return json.loads(cand.read_text(encoding="utf-8"))
        # paper-id 含空格时文件名被换成下划线
        ingest = vault / "90_系统" / "_ingest"
        if ingest.is_dir():
            for p in ingest.glob("*.job.json"):
                data = json.loads(p.read_text(encoding="utf-8"))
                if data.get("paperId") == args.paper_id:
                    return data
    raise SystemExit("找不到 job JSON：传 --job 或先跑 ingest_prepare.py")


def main() -> None:
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

    import argparse

    finish_started_at = now_iso()
    finish_started = time.perf_counter()
    stage_timings: dict[str, float] = {}
    cfg = load_cfg()
    ap = argparse.ArgumentParser(description="pdf-to-wenshu 确定性收尾 + 文枢同步")
    ap.add_argument("--job", default=None)
    ap.add_argument("--paper-id", default=None)
    ap.add_argument("--vault", default=None)
    ap.add_argument("--skip-web", action="store_true", help="不跑 wenshu-pro/scripts/sync-vault.py")
    ap.add_argument("--no-crossref", action="store_true")
    strict_group = ap.add_mutually_exclusive_group()
    strict_group.add_argument("--strict", dest="strict", action="store_true",
                              help="严格验收：核心产物缺失、任一步失败或 Web 警告都不算完成")
    strict_group.add_argument("--no-strict", dest="strict", action="store_false",
                              help="兼容旧 job：仅阻断既有 error")
    ap.set_defaults(strict=None)
    args = ap.parse_args()

    job = load_job(args, cfg)
    vault = Path(job["vault"])
    notes = job["notes"]
    pid = job["paperId"]
    article = notes.get("article")
    article_en = notes.get("articleEn")
    notes_md = notes.get("notes")
    index = notes.get("index")
    strict = bool(job.get("strict", False)) if args.strict is None else args.strict
    steps: dict[str, int | str] = {}

    def timed_run(name: str, cmd: list[str]) -> subprocess.CompletedProcess:
        started = time.perf_counter()
        proc = run(cmd, check=False)
        stage_timings[name] = elapsed(started)
        return proc

    if strict:
        preflight_issues = strict_preflight(job)
        if preflight_issues:
            job["status"] = "preflight-failed"
            job["strict"] = True
            job["preflightIssues"] = preflight_issues
            job.setdefault("timing", {})["finish"] = {
                "startedAt": finish_started_at,
                "finishedAt": now_iso(),
                "durationSec": elapsed(finish_started),
                "stages": stage_timings,
            }
            save_job(job, vault, pid)
            print(json.dumps({
                "paperId": pid,
                "strict": True,
                "status": job["status"],
                "issues": preflight_issues,
            }, ensure_ascii=False, indent=2))
            raise SystemExit(1)

    # update_terms 必须先于 strip_markers：术语表回填靠 <!--TERMS_START/END--> 定位
    terms_json = Path(job.get("termsJson") or "")
    if terms_json.is_file() and notes_md:
        terms_proc = timed_run(
            "updateTerms",
            [
                py(),
                str(SCRIPTS / "update_terms.py"),
                "--terms",
                str(terms_json),
                "--paper-id",
                pid,
                "--vault",
                str(vault),
                "--notes-note",
                notes_md,
            ],
        )
        steps["updateTerms"] = terms_proc.returncode
    else:
        sys.stderr.write("跳过 update_terms.py（还没有 terms.json）\n")
        steps["updateTerms"] = "skipped"

    md_files = [p for p in (index, article, article_en, notes_md) if p and Path(p).is_file()]
    if md_files:
        steps["stripMarkers"] = timed_run(
            "stripMarkers", [py(), str(SCRIPTS / "strip_markers.py"), *md_files]
        ).returncode

    unlink_targets = [p for p in (notes_md, article, index) if p and Path(p).is_file()]
    if unlink_targets:
        steps["delinkUnresolved"] = timed_run(
            "delinkUnresolved",
            [py(), str(SCRIPTS / "delink_unresolved.py"), str(vault), *unlink_targets],
        ).returncode

    # 确定性纠错：AI 文稿的机械性格式问题（表格空行、裸 <>、图片宽度/名字等）先修一遍再验收
    fix_targets = [p for p in (article, article_en, notes_md) if p and Path(p).is_file()]
    if fix_targets:
        fix_cmd = [py(), str(SCRIPTS / "fix_article.py"), *fix_targets]
        if job.get("imagesDir"):
            fix_cmd += ["--images-dir", job["imagesDir"]]
        steps["fixArticle"] = timed_run("fixArticle", fix_cmd).returncode

    if article:
        refs_cmd = [py(), str(SCRIPTS / "build_refs.py"), "--vault", str(vault), "--article", article, "--inline"]
        if args.no_crossref:
            refs_cmd.append("--no-crossref")
        steps["buildRefs"] = timed_run("buildRefs", refs_cmd).returncode
        steps["refreshRefLinks"] = timed_run(
            "refreshRefLinks",
            [py(), str(SCRIPTS / "build_refs.py"), "--vault", str(vault), "--all", "--no-crossref"],
        ).returncode

    # build_bib 先于 lint：citekey 回填后 lint 才不会报「缺 citekey」假警告
    steps["buildIndex"] = timed_run(
        "buildIndex", [py(), str(SCRIPTS / "build_index.py"), "--vault", str(vault)]
    ).returncode
    steps["buildBib"] = timed_run(
        "buildBib", [py(), str(SCRIPTS / "build_bib.py"), "--vault", str(vault)]
    ).returncode
    lint = timed_run(
        "lintCluster",
        [py(), str(SCRIPTS / "lint_cluster.py"), "--vault", str(vault), "--paper", pid],
    )
    steps["lintCluster"] = lint.returncode

    web_rc = 0
    web_strict_rc = 0
    wenshu = Path(job.get("wenshu") or cfg.get("wenshu") or (SKILL_DIR.parent.parent / "wenshu-pro"))
    sync = wenshu / "scripts" / "sync-vault.py"
    if not args.skip_web and sync.is_file():
        stage_started = time.perf_counter()
        web = subprocess.run(
            [py(), str(sync), "--vault", str(vault)],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        stage_timings["syncVault"] = elapsed(stage_started)
        sys.stderr.write(web.stderr or "")
        sys.stderr.write(web.stdout or "")
        web_rc = web.returncode
        steps["syncVault"] = web_rc
    elif not args.skip_web:
        sys.stderr.write(f"找不到文枢 sync-vault.py：{sync}\n")
        web_rc = 1
        steps["syncVault"] = web_rc
    else:
        steps["syncVault"] = "skipped"

    web_lint = wenshu / "scripts" / "web_lint.py"
    if strict and not args.skip_web and web_lint.is_file():
        strict_web = timed_run(
            "webStrict",
            [
                py(), str(web_lint), "--vault", str(vault), "--paper", pid,
                "--fail-on-warnings",
            ],
        )
        web_strict_rc = strict_web.returncode
        steps["webStrict"] = web_strict_rc
    elif strict and not args.skip_web:
        web_strict_rc = 1
        steps["webStrict"] = web_strict_rc
    else:
        steps["webStrict"] = "skipped"

    failures = {
        name: code for name, code in steps.items()
        if isinstance(code, int) and code != 0
    }
    job["strict"] = strict
    job["steps"] = steps
    job["status"] = "finished" if not failures else "lint-failed"
    job.setdefault("timing", {})["finish"] = {
        "startedAt": finish_started_at,
        "finishedAt": now_iso(),
        "durationSec": elapsed(finish_started),
        "stages": stage_timings,
    }
    save_job(job, vault, pid)

    result = {
        "paperId": pid,
        "strict": strict,
        "lint": lint.returncode,
        "web": web_rc,
        "webStrict": web_strict_rc,
        "steps": steps,
        "timing": job["timing"]["finish"],
        "status": job["status"],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
