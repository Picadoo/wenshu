from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_agent_brief.py"
SPEC = importlib.util.spec_from_file_location("build_agent_brief", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def sample_job() -> dict:
    return {
        "paperId": "Wang2022 test",
        "vault": "D:/vault",
        "wenshu": "D:/wenshu",
        "pdfPath": "D:/vault/paper.pdf",
        "fulltextPath": "D:/vault/paper.txt",
        "cleanFulltextPath": "D:/vault/paper.clean.txt",
        "imageIndexPath": "D:/vault/paper.images.md",
        "tableIndexPath": "D:/vault/paper.tables.md",
        "notes": {
            "article": "D:/vault/paper.zh.md",
            "articleEn": "D:/vault/paper.en.md",
        },
        "englishWorkflow": {"cFallbackReason": None},
    }


class AgentBriefTests(unittest.TestCase):
    def test_a_brief_resolves_paths_and_forbids_full_rule_reload(self) -> None:
        brief = MODULE.render("A", sample_job())
        self.assertIn("D:/vault/paper.clean.txt", brief)
        self.assertIn("D:/vault/paper.zh.md", brief)
        self.assertIn("不要再读取 `SKILL.md`", brief)
        self.assertNotIn("{{", brief)

    def test_c_requires_registered_failure_reason(self) -> None:
        with self.assertRaises(ValueError):
            MODULE.render("C", sample_job(), Path("D:/draft.md"))

    def test_c_brief_contains_registered_reason(self) -> None:
        job = sample_job()
        job["englishWorkflow"]["cFallbackReason"] = (
            "The dump has no page markers and column order is unusable"
        )
        brief = MODULE.render("C", job, Path("D:/draft.md"))
        self.assertIn("column order is unusable", brief)

    def test_d_brief_contains_lint_report(self) -> None:
        brief = MODULE.render(
            "D",
            sample_job(),
            Path("D:/draft/Wang2022 test.正文.en.md"),
            "1 warning: missing caption",
        )
        self.assertIn("1 warning: missing caption", brief)
        self.assertIn("D:/vault/paper.en.md", brief)


if __name__ == "__main__":
    unittest.main()
