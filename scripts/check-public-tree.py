#!/usr/bin/env python3
"""Check staged public source boundaries without printing file contents or secrets."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    paths = subprocess.check_output(
        ["git", "ls-files", "--cached", "-z"], cwd=ROOT
    ).decode("utf-8").split("\0")
    paths = [path for path in paths if path]
    if not paths:
        print("FAIL: stage the public files before checking")
        return 1
    errors = []
    forbidden = ("vault/", "_work/", "_backup/", "_archive/", "wenshu-pro/public/vault/")
    tokens = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{24,})\b|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
    local_paths = re.compile(r"\b[A-Z]:[\\/](?:Users|Works)[\\/]", re.I)
    pdfs = []
    indexes = []
    for name in paths:
        path = Path(name)
        if name.startswith(forbidden) or any(part in {"node_modules", "target", ".venv", "__pycache__"} for part in path.parts):
            errors.append((name, "private or generated directory"))
        if path.name.startswith(".env") and path.name != ".env.example":
            errors.append((name, "environment file"))
        if path.suffix in {".db", ".sqlite", ".sqlite3", ".log"} or "我的笔记" in name or "_web批注" in name or "_活动日志" in name:
            errors.append((name, "personal or runtime data"))
        if name.startswith("wenshu-pro/src/data/generated-"):
            errors.append((name, "generated catalog"))
        if path.suffix.lower() == ".pdf":
            pdfs.append(name)
        if name.startswith("examples/vault/Papers/") and path.suffix == ".md" and "content" not in path.parts and "images" not in path.parts:
            indexes.append(name)
        if path.suffix.lower() in {".png", ".webp", ".jpg", ".jpeg", ".ico", ".pdf"}:
            continue
        try:
            source = subprocess.check_output(
                ["git", "show", f":{name}"], cwd=ROOT
            ).decode("utf-8")
        except UnicodeDecodeError:
            errors.append((name, "unexpected binary file"))
            continue
        if tokens.search(source):
            errors.append((name, "credential pattern"))
        if local_paths.search(source):
            errors.append((name, "machine-specific path"))
    if len(pdfs) != 1 or not pdfs[0].startswith("examples/vault/"):
        errors.append(("examples/vault", "expected exactly one example PDF"))
    if len(indexes) != 1:
        errors.append(("examples/vault", "expected exactly one paper index"))
    for name, reason in errors:
        print(f"FAIL: {name}: {reason}")
    if errors:
        return 1
    print(f"PASS: {len(paths)} staged source files; one example paper; no forbidden files or detected credential patterns")
    return 0


if __name__ == "__main__":
    sys.exit(main())

