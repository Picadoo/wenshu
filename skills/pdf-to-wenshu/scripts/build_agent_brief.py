#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a resolved, minimal A1/A/D/C task brief from an ingest job.

角色顺序（2026-09-01 起改为「先英后中」）：
  A1 英文重排 → 硬门禁 → A 中文翻译（照 A1 的层级逐节译）→ D 英文校订（仅残留 TODO）

改序的原因：双栏 dump 里标题和正文粘在一行，确定性脚本恢复不出章节层级；
以前排版重建只发生在中文侧，英文侧永远比中文烂（实测 38 个标题 vs 3 个）。
把重排挪到英文侧做一次，中文直接继承骨架。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.config import load_config as load_skill_config  # noqa: E402


SKILL_DIR = Path(__file__).resolve().parents[1]
ROLE_FILES = {
    "A1": SKILL_DIR / "references" / "luna-a1-brief.md",
    "A": SKILL_DIR / "references" / "luna-a-brief.md",
    "D": SKILL_DIR / "references" / "luna-d-brief.md",
    "C": SKILL_DIR / "references" / "luna-c-brief.md",
}


def job_from_cluster(cluster: Path, pid: str) -> dict:
    """存量论文返工用：从集群目录现推一份 job。

    `_ingest/*.job.json` 只有新流程入库的论文才有（本库 95 篇里仅 8 篇），
    而返工恰恰是冲着老论文去的——没有这条路，改好的角色一篇存量都修不了。
    字段口径与 `ingest_prepare` 产出的 job 一致，只推 brief 用得到的那些；
    路径按集群固定布局解析，缺文件当场报错而不是塞个空串糊弄下游。
    """
    cfg_path = SKILL_DIR / "config.json"
    cfg = load_skill_config(cfg_path)
    content, images = cluster / "content", cluster / "images"
    job = {
        "paperId": pid,
        "vault": cfg.get("vault", ""),
        "wenshu": cfg.get("wenshu", ""),
        "pdfPath": str(content / f"{pid}.pdf"),
        "fulltextPath": str(content / f"{pid}.txt"),
        "imageIndexPath": str(images / f"{pid}.images.md"),
        "tableIndexPath": str(content / f"{pid}.tables.md"),
        "notes": {
            "article": str(content / f"{pid}.正文.md"),
            "articleEn": str(content / f"{pid}.正文.en.md"),
        },
    }
    missing = [k for k in ("fulltextPath", "imageIndexPath") if not Path(job[k]).is_file()]
    if missing:
        raise ValueError(f"集群 {cluster} 缺少 {'、'.join(missing)}，无法现推 job")
    return job


def require(job: dict, dotted: str) -> str:
    value = job
    for key in dotted.split("."):
        if not isinstance(value, dict) or key not in value:
            raise ValueError(f"job 缺字段：{dotted}")
        value = value[key]
    if value is None or str(value).strip() == "":
        raise ValueError(f"job 字段为空：{dotted}")
    return str(value)


def render(role: str, job: dict, draft: Path | None = None,
           lint_report: str = "") -> str:
    role = role.upper()
    if role not in ROLE_FILES:
        raise ValueError(f"未知角色：{role}")
    # A1 也要草稿：它的活是「在脚本草稿基础上恢复结构」，不是从零重写
    if role in {"A1", "C", "D"} and draft is None:
        raise ValueError(f"{role} 档必须传 --draft")
    reason = job.get("englishWorkflow", {}).get("cFallbackReason") or ""
    if role == "C" and len(reason.strip()) < 12:
        raise ValueError("C 档未登记具体 cFallbackReason，禁止生成任务")

    source = job.get("cleanFulltextPath") or require(job, "fulltextPath")
    # 带上下标的 dump 与 <pid>.txt 同目录同名，旧 job 里没有这个字段，按约定推出来。
    # 不能用 with_suffix：pid 里带点（`Fig.2` 之类）会被截断，逐个剥已知后缀才稳。
    src_path = Path(str(source))
    stem = src_path.name
    for suffix in ('.clean.txt', '.txt'):
        if stem.endswith(suffix):
            stem = stem[:-len(suffix)]
            break
    rich = src_path.with_name(stem + '.rich.txt')
    values = {
        "PAPER_ID": require(job, "paperId"),
        "ARTICLE_PATH": require(job, "notes.article"),
        "ARTICLE_EN_PATH": require(job, "notes.articleEn"),
        "SOURCE_PATH": str(source),
        "RICH_SOURCE_PATH": str(rich if rich.is_file() else source),
        "IMAGE_INDEX_PATH": require(job, "imageIndexPath"),
        "TABLE_INDEX_PATH": require(job, "tableIndexPath"),
        "PDF_PATH": require(job, "pdfPath"),
        "DRAFT_PATH": str(draft or ""),
        "DRAFT_DIR": str(draft.parent if draft else ""),
        "VAULT": require(job, "vault"),
        "WENSHU": require(job, "wenshu"),
        "LINT_SCRIPT": str(SKILL_DIR / "scripts" / "lint_en_draft.py"),
        "LINT_REPORT": lint_report.strip() or "未提供；父代理应先运行严格草稿 lint。",
        "C_FALLBACK_REASON": reason.strip(),
    }
    text = ROLE_FILES[role].read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    unresolved = [part.split("}}", 1)[0] for part in text.split("{{")[1:]]
    if unresolved:
        raise ValueError(f"简报存在未解析占位符：{', '.join(unresolved)}")
    return text


def run_d_lint(job: dict, draft: Path) -> tuple[int, str]:
    cmd = [
        sys.executable,
        str(SKILL_DIR / "scripts" / "lint_en_draft.py"),
        "--vault", require(job, "vault"),
        "--wenshu", require(job, "wenshu"),
        "--draft-dir", str(draft.parent),
        "--only", require(job, "paperId"),
        "--fail-on-warnings",
    ]
    proc = subprocess.run(
        cmd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    report = "\n".join(part.strip() for part in (proc.stdout, proc.stderr) if part.strip())
    return proc.returncode, report


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="从 ingest job 生成最小 Luna A1/A/D/C 任务简报")
    ap.add_argument("--job", help="ingest job JSON；返工存量论文时改用 --cluster")
    ap.add_argument("--cluster", help="集群目录（含 content/ 与 images/）；"
                                      "老论文没有 job.json 时从这里现推")
    ap.add_argument("--pid", help="配合 --cluster 使用；省略时按集群里的 .正文.md 推断")
    ap.add_argument("--role", required=True,
                    choices=("A1", "A", "D", "C", "a1", "a", "d", "c"))
    ap.add_argument("--draft", help="A1/D/C 暂存草稿路径")
    ap.add_argument("--out", help="输出文件；省略时打印到 stdout")
    args = ap.parse_args()

    if bool(args.job) == bool(args.cluster):
        raise SystemExit("--job 与 --cluster 二选一")
    if args.job:
        job_path = Path(args.job).resolve()
        if not job_path.is_file():
            raise SystemExit(f"找不到 job JSON：{job_path}")
        job = json.loads(job_path.read_text(encoding="utf-8"))
    else:
        cluster = Path(args.cluster).resolve()
        pid = args.pid
        if not pid:
            arts = [p for p in (cluster / "content").glob("*.正文.md")
                    if not p.name.endswith(".正文.en.md")]
            if len(arts) != 1:
                raise SystemExit(f"集群里有 {len(arts)} 个中文正文，请用 --pid 指明")
            pid = arts[0].name[: -len(".正文.md")]
        try:
            job = job_from_cluster(cluster, pid)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
    role = args.role.upper()
    draft = Path(args.draft).resolve() if args.draft else None
    if draft is not None and not draft.is_file() and role in {"A1", "D"}:
        raise SystemExit(f"找不到 {role} 档草稿：{draft}")

    lint_report = ""
    if role == "D":
        assert draft is not None
        code, lint_report = run_d_lint(job, draft)
        if code == 0:
            print("SKIP_D：英文草稿已严格 0 error / 0 warning；不要启动子代理")
            raise SystemExit(3)
    try:
        brief = render(role, job, draft, lint_report)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    if args.out:
        out = Path(args.out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(brief, encoding="utf-8")
        print(out)
    else:
        print(brief)


if __name__ == "__main__":
    main()
