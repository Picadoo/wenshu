"""Load skill configuration with paths relative to the repository root."""
from __future__ import annotations

import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def load_config(path: str | Path) -> dict:
    config_path = Path(path)
    if not config_path.is_file():
        return {}
    config = json.loads(config_path.read_text(encoding="utf-8"))
    for key in ("vault", "wenshu", "work"):
        value = config.get(key)
        if value:
            configured_path = Path(value).expanduser()
            if not configured_path.is_absolute():
                configured_path = REPOSITORY_ROOT / configured_path
            config[key] = str(configured_path.resolve())
    return config
