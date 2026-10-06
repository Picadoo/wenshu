from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
CONFIG = json.loads((SKILL_DIR / "config.json").read_text(encoding="utf-8"))
SCRIPT = Path(CONFIG["wenshu"]) / "scripts" / "web_lint.py"
SPEC = importlib.util.spec_from_file_location("web_lint", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CaptionTests(unittest.TestCase):
    def lint(self, caption: str):
        lint = MODULE.Lint()
        MODULE.check_captions(lint, "paper", f"![[paper_page1_fig1.png|700]]\n{caption}\n")
        return lint

    def test_caption_with_text_passes(self) -> None:
        self.assertEqual(self.lint("**图 1：** 有实际说明文字。").warns, [])

    def test_empty_caption_warns(self) -> None:
        lint = self.lint("**图 1：**")
        self.assertEqual(len(lint.warns), 1)
        self.assertIn("缺图注", lint.warns[0][1])


if __name__ == "__main__":
    unittest.main()
