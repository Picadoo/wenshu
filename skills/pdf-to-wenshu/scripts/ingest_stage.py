#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Record model-stage timing and explicitly unlock the exceptional English C path."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


STAGES = ("lunaA", "mainAnalysis", "prepEnglish", "lunaD")


def now() -> datetime:
    return datetime.now().astimezone()


def iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def update_stage(job: dict, stage: str, action: str, at: datetime) -> dict:
    content = job.setdefault("timing", {}).setdefault("content", {})
    row = content.setdefault(stage, {})
    if action == "start":
        row.clear()
        row.update({"startedAt": iso(at), "status": "running"})
        return row
    started_raw = row.get("startedAt")
    if not started_raw:
        raise ValueError(f"{stage} 尚未 start，不能 {action}")
    started = datetime.fromisoformat(started_raw)
    row.update({
        "finishedAt": iso(at),
        "durationSec": round((at - started).total_seconds(), 3),
        "status": "finished" if action == "finish" else "failed",
    })
    return row


def allow_c_fallback(job: dict, reason: str, at: datetime) -> dict:
    reason = reason.strip()
    if len(reason) < 12:
        raise ValueError("C 档兜底理由过短；请写明确定性草稿具体失效点")
    workflow = job.setdefault("englishWorkflow", {})
    workflow.update({
        "mode": "full-rebuild",
        "cFallbackReason": reason,
        "cFallbackApprovedAt": iso(at),
    })
    return workflow


def save_atomic(path: Path, job: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    ap = argparse.ArgumentParser(description="记录入库内容阶段耗时 / 解锁异常英文 C 档")
    ap.add_argument("--job", required=True)
    sub = ap.add_subparsers(dest="action", required=True)
    for action in ("start", "finish", "fail"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--stage", required=True, choices=STAGES)
    fallback = sub.add_parser("allow-c-fallback")
    fallback.add_argument("--reason", required=True)
    args = ap.parse_args()

    path = Path(args.job)
    if not path.is_file():
        raise SystemExit(f"找不到 job JSON：{path}")
    job = json.loads(path.read_text(encoding="utf-8"))
    try:
        if args.action == "allow-c-fallback":
            result = allow_c_fallback(job, args.reason, now())
        else:
            result = update_stage(job, args.stage, args.action, now())
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    save_atomic(path, job)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
