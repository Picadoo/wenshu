#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_agent.py — 把核准后的锁定英文交给翻译 agent，检查并合并中文译文。

    python run_agent.py --work <workdir> [--runner codex|claude|grok|kimi|<自定义名>] [--model M] [--effort E]
                        [--rounds 2] [--timeout-min 90] [--dry-run]

runner / model / effort 的默认值来自 config.json 的 "agent" 段；每个 runner 是一个命令模板（见 RUNNERS），
config.json "agent.runners" 里可以覆盖或新增。模板占位符：
    {work} 工作区   {model} 模型   {effort} 推理强度   {prompt} 任务书文件   {prompt_text} 任务书全文
    {last} 让 CLI 写最终回复的文件   {scripts} 本技能 scripts 目录
产出：<workdir>/agent/round<N>.log（CLI 全部输出）、round<N>.prompt.md、round<N>.last.md，
      <workdir>/timing.json（每轮起止、耗时、退出码、verify 结果），供 finish.py 记进 lite.json。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.config import load_config as load_skill_config  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from translation import prepare, merge, check_translation, token_context, TEXT_REQUEST  # noqa: E402

RUNNERS: dict[str, dict] = {
    # OpenAI Codex CLI：沙箱只许写工作区；prompt 从 stdin 进（"-"）
    "codex": {"cmd": ["codex", "exec", "--skip-git-repo-check", "--color", "never", "-C", "{work}", "-s", "workspace-write",
                      "-m", "{model}", "-c", "model_reasoning_effort={effort}", "-o", "{last}", "-"], "stdin": True},
    # Claude Code：-p 无头，prompt 从 stdin 进
    "claude": {"cmd": ["claude", "-p", "--model", "{model}", "--dangerously-skip-permissions", "--output-format", "text",
                       "--add-dir", "{work}"], "stdin": True},
    # Grok Build CLI（~/.grok/bin/agent.exe）
    "grok": {"cmd": ["agent", "--prompt-file", "{prompt}", "--cwd", "{work}", "--permission-mode", "bypassPermissions",
                     "-m", "{model}", "--reasoning-effort", "{effort}", "--no-memory", "--output-format", "plain"], "stdin": False},
    # Kimi Code CLI
    "kimi": {"cmd": ["kimi", "-p", "{prompt_text}", "-y", "-m", "{model}", "--add-dir", "{work}"], "stdin": False},
}

def utf8() -> None:
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_config(path: Path | None) -> dict:
    p = path or (HERE.parent / "config.json")
    return load_skill_config(p)


def resolve_exe(name: str) -> str:
    """Windows 上 npm shim 是 .cmd/.ps1；Grok 的 agent.exe 不在 PATH 时按默认安装位找。"""
    found = shutil.which(name)
    if found:
        return found
    if name == "agent":
        cand = Path.home() / ".grok" / "bin" / "agent.exe"
        if cand.exists():
            return str(cand)
    raise SystemExit(f"找不到可执行文件：{name}（runner 未安装或不在 PATH）")


def build_cmd(template: list[str], ctx: dict) -> list[str]:
    """空的 {model}/{effort} 连同前面的开关一起丢掉，其余占位符替换。"""
    out: list[str] = []
    for i, arg in enumerate(template):
        if any("{" + key + "}" in arg and not ctx.get(key) for key in ("model", "effort")):
            if i > 0 and template[i - 1].startswith("-") and out:
                out.pop()
            continue
        out.append(arg.format(**ctx))
    out[0] = resolve_exe(out[0])
    return out


def kill_tree(proc: subprocess.Popen) -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.kill()


def say(*args) -> None:
    """关闭父 shell 后输出管道可能断开；仍允许本轮正常结束。"""
    try:
        print(*args, flush=True)
    except (OSError, ValueError):
        pass


def run_round(cmd: list[str], work: Path, prompt: str, use_stdin: bool, log: Path, timeout_s: float, idle_s: float = 0,
              resource: Path | None = None) -> tuple[int | str, float]:
    """跑一轮。总时长超过 timeout_s → 'timeout'；日志 idle_s 秒没长（CLI 断网后静默挂住，实测 codex 'Reconnecting 5/5' 后一直不退）→ 'stalled'。"""
    env = dict(os.environ, PYTHONIOENCODING="utf-8", NO_COLOR="1", TERM="dumb")
    t0 = time.time()
    with log.open("ab") as fh:
        fh.write(f"$ {' '.join(cmd)}\n\n".encode("utf-8"))
        fh.flush()
        proc = subprocess.Popen(cmd, cwd=str(work), stdin=subprocess.PIPE if use_stdin else subprocess.DEVNULL,
                                stdout=fh, stderr=subprocess.STDOUT, env=env,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        record = {"pid": proc.pid, "cmd": cmd, "cwd": str(work), "started_at": now_iso(), "state": "running"}
        if resource:
            resource.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        rc: int | str = "timeout"
        try:
            if use_stdin and proc.stdin:
                proc.stdin.write(prompt.encode("utf-8"))
                proc.stdin.close()
            last_size, last_grow = -1, time.time()
            while True:
                try:
                    rc = proc.wait(timeout=15)
                    break
                except subprocess.TimeoutExpired:
                    pass
                now = time.time()
                if now - t0 > timeout_s:
                    kill_tree(proc)
                    rc = "timeout"
                    break
                size = log.stat().st_size if log.exists() else 0
                if size != last_size:
                    last_size, last_grow = size, now
                elif idle_s and now - last_grow > idle_s:
                    kill_tree(proc)
                    rc = "stalled"
                    fh.write(f"\n[run_agent] 日志 {int(idle_s // 60)} 分钟没有新输出，判定挂死，已终止\n".encode("utf-8"))
                    break
        except KeyboardInterrupt:
            kill_tree(proc)
            rc = "interrupted"
            raise
        except BaseException:
            if proc.poll() is None:
                kill_tree(proc)
            rc = "exception"
            raise
        finally:
            if proc.poll() is None:
                kill_tree(proc)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            record.update({"completed_at": now_iso(), "rc": rc, "returncode": proc.poll(),
                           "state": "exited" if proc.poll() is not None else "cleanup-unconfirmed"})
            if resource:
                resource.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return rc, round(time.time() - t0, 1)


def main() -> None:
    utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--runner", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--effort", default=None)
    ap.add_argument("--rounds", type=int, default=0, help="最多几轮（第 1 轮写，之后每轮只修 verify errors）")
    ap.add_argument("--timeout-min", type=float, default=0)
    ap.add_argument("--idle-min", type=float, default=None, help="日志多少分钟没长就判挂死终止（默认 config agent.idleMinutes，0 = 不判）")
    ap.add_argument("--config", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--repair-only", action="store_true", help="不重写，直接按当前 verify 的 errors 派一轮修复（out/ 已有产出时用）")
    a = ap.parse_args()

    work = Path(a.work).resolve()
    cfg = load_config(Path(a.config).resolve() if a.config else None).get("agent", {})
    runners = dict(RUNNERS)
    for name, spec in (cfg.get("runners") or {}).items():
        runners[name] = {"cmd": spec.get("cmd") or runners.get(name, {}).get("cmd"), "stdin": bool(spec.get("stdin", runners.get(name, {}).get("stdin", False)))}
    runner = a.runner or cfg.get("runner") or "codex"
    if runner not in runners:
        raise SystemExit(f"未知 runner `{runner}`，可选：{sorted(runners)}")
    model = a.model or (cfg.get("models") or {}).get(runner) or cfg.get("model") or ""
    effort = a.effort if a.effort is not None else "low"
    rounds = a.rounds or int(cfg.get("rounds") or 2)
    timeout_s = (a.timeout_min or float(cfg.get("timeoutMinutes") or 90)) * 60
    idle_s = (a.idle_min if a.idle_min is not None else float(cfg.get("idleMinutes") or 10)) * 60

    agent_dir = work / "agent"
    agent_dir.mkdir(exist_ok=True)
    timing = {"stage": "translate", "runner": runner, "model": model, "effort": effort, "started_at": now_iso(), "rounds": []}
    if a.repair_only:
        old = json.loads((work / "timing.json").read_text(encoding="utf-8")) if (work / "timing.json").exists() else {}
        timing = {**old, "stage": "translate", "runner": runner, "model": model, "effort": effort, "rounds": list(old.get("rounds") or [])}
        timing.setdefault("started_at", now_iso())
    (work / "timing.json").write_text(json.dumps(timing, ensure_ascii=False, indent=1), encoding="utf-8")

    def repair_prompt(res: dict) -> str:
        if runner == "codex":
            current = work / "translation/zh.locked.md"
            draft = current.read_text(encoding="utf-8") if current.exists() else "（本轮未形成译文）"
            return text_prompt() + "\n仅局部修复下列错误，仍只返回完整锁定译文：\n" + "\n".join(f"- {e}" for e in res["errors"]) + "\n\nBEGIN_CURRENT_LOCKED_DRAFT\n" + draft + "\nEND_CURRENT_LOCKED_DRAFT\n"
        return (work / "translation/request.md").read_text(encoding="utf-8") + "\n仅修 zh.locked.md 的下列错误，不改其他文件：\n" + "\n".join(f"- {e}" for e in res["errors"])

    prepared = prepare(work)
    if not prepared["ok"]:
        raise SystemExit("翻译准备失败：\n" + "\n".join(prepared["errors"]))
    def text_prompt() -> str:
        return TEXT_REQUEST + token_context(work) + "\nBEGIN_LOCKED_ENGLISH\n" + (work / "translation/input.md").read_text(encoding="utf-8") + "\nEND_LOCKED_ENGLISH\n"

    prompt = text_prompt() if runner == "codex" else (work / "translation/request.md").read_text(encoding="utf-8")
    cli_work = work / "translation"

    def gate() -> dict:
        result = merge(work)
        return check_translation(work) if result["ok"] else {**result, "warnings": []}
    result: dict = {}
    first = 1
    if a.repair_only:
        result = gate()
        if result["ok"]:
            say("翻译校验已通过，无需修复")
            say(json.dumps({"timing": timing, "verify": result}, ensure_ascii=False, indent=1))
            return
        prompt = repair_prompt(result)
        first = len(timing["rounds"]) + 1
        rounds = first + max(1, rounds - 1) - 1
    for rnd in range(first, rounds + 1):
        # Codex's write sandbox is narrowed to translation/ for this stage.
        artifact_dir = cli_work
        ctx = {"work": str(cli_work), "model": model, "effort": effort, "prompt": str(artifact_dir / f"round{rnd}.prompt.md"),
               "prompt_text": prompt, "last": str(artifact_dir / f"round{rnd}.last.md"), "scripts": str(HERE)}
        Path(ctx["prompt"]).write_text(prompt, encoding="utf-8")
        cmd = build_cmd(list(runners[runner]["cmd"]), ctx)
        if a.dry_run:
            say(json.dumps({"stage": "translate", "round": rnd, "cwd": str(cli_work), "stdin": runners[runner]["stdin"], "cmd": cmd}, ensure_ascii=False, indent=1))
            return
        if runner == "codex":
            # -o is host-written final text. Clear this round's owned stale file;
            # an rc=0 command must produce fresh, nonempty output to merge.
            Path(ctx["last"]).unlink(missing_ok=True)
        log = agent_dir / f"round{rnd}.log"
        say(f"[round {rnd}] {runner} model={model or '(default)'} effort={effort or '(default)'} → {log.name}")
        started = now_iso()
        rc, secs = run_round(cmd, cli_work, prompt, runners[runner]["stdin"], log, timeout_s, idle_s,
                             agent_dir / f"round{rnd}.resource.json")
        # A failed CLI cannot publish a previous round's surviving locked file.
        if rc != 0:
            result = {"ok": False, "errors": [f"CLI 本轮退出失败 rc={rc}，未合并或采用旧产物"], "warnings": []}
        elif runner == "codex":
            last = Path(ctx["last"])
            text = last.read_text(encoding="utf-8") if last.exists() else ""
            if not text.strip():
                result = {"ok": False, "errors": ["Codex 本轮最终锁定译文为空或缺失；未合并旧产物"], "warnings": []}
            else:
                (work / "translation/zh.locked.md").write_text(text, encoding="utf-8")
                result = gate()
        else:
            result = gate()
        entry = {"round": rnd, "stage": "translate", "started_at": started, "completed_at": now_iso(), "seconds": secs, "rc": rc,
                 "verify": {"ok": result["ok"], "errors": len(result["errors"]), "warnings": len(result["warnings"])}}
        timing["rounds"].append(entry)
        timing["completed_at"] = entry["completed_at"]
        timing["seconds"] = round(sum(r["seconds"] for r in timing["rounds"]), 1)
        (work / "timing.json").write_text(json.dumps(timing, ensure_ascii=False, indent=1), encoding="utf-8")
        say(f"[round {rnd}] rc={rc} {secs}s translation check: ok={result['ok']} errors={len(result['errors'])} warnings={len(result['warnings'])}")
        if result["ok"] or rnd == rounds:
            break
        prompt = repair_prompt(result)
    say(json.dumps({"timing": timing, "verify": result}, ensure_ascii=False, indent=1))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
