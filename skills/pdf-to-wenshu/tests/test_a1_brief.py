"""A1 英文重排角色的任务包必须自包含、且不把 A 档的活写进去。

「先英后中」改序后，A1 是新流程的第一棒：它只写英文正文、只管结构，
A 档照它的骨架逐节翻译。两档写权混了就会互相覆盖。
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_agent_brief.py"
SPEC = importlib.util.spec_from_file_location("build_agent_brief", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

JOB = {
    "paperId": "Demo2026 演示论文",
    "vault": "D:/vault",
    "wenshu": "D:/wenshu",
    "pdfPath": "D:/vault/Papers/x/content/Demo2026 演示论文.pdf",
    "fulltextPath": "D:/vault/Papers/x/content/Demo2026 演示论文.txt",
    "imageIndexPath": "D:/vault/Papers/x/images/Demo2026 演示论文.images.md",
    "tableIndexPath": "D:/vault/Papers/x/content/Demo2026 演示论文.tables.md",
    "notes": {
        "article": "D:/vault/Papers/x/content/Demo2026 演示论文.正文.md",
        "articleEn": "D:/vault/Papers/x/content/Demo2026 演示论文.正文.en.md",
    },
}
DRAFT = Path("_work/en-draft/Demo2026 演示论文.正文.en.md")


class A1BriefTests(unittest.TestCase):
    def test_a1_is_a_known_role(self) -> None:
        self.assertIn("A1", MODULE.ROLE_FILES)
        self.assertTrue(MODULE.ROLE_FILES["A1"].is_file())

    def test_a1_requires_a_draft(self) -> None:
        """A1 的活是在脚本草稿上恢复结构，不是从零重写。"""
        with self.assertRaises(ValueError):
            MODULE.render("A1", JOB, None)

    def test_a1_brief_resolves_and_targets_english_only(self) -> None:
        brief = MODULE.render("A1", JOB, DRAFT)
        self.assertNotIn("{{", brief)
        self.assertIn(JOB["notes"]["articleEn"], brief)
        self.assertIn(str(DRAFT), brief)
        self.assertIn("只允许写", brief)
        # 写权必须排除中文正文，否则 A1 和 A 会互相覆盖
        self.assertNotIn("只允许写：`%s`" % JOB["notes"]["article"], brief)

    def test_a1_brief_states_the_heading_gate(self) -> None:
        """层级恢复是 A1 存在的唯一理由，任务包必须写明并给出验收命令。"""
        brief = MODULE.render("A1", JOB, DRAFT)
        self.assertIn("章节层级", brief)
        self.assertIn("--fail-on-warnings", brief)

    def test_a1_brief_forbids_reloading_the_whole_skill(self) -> None:
        brief = MODULE.render("A1", JOB, DRAFT)
        self.assertIn("不要再读取", brief)
        self.assertIn("SKILL.md", brief)

    def test_a_brief_now_translates_from_the_english_article(self) -> None:
        """改序后中文档的原料是已验收英文正文，不再是 dump。"""
        brief = MODULE.render("A", JOB)
        self.assertIn(JOB["notes"]["articleEn"], brief)
        self.assertIn("逐节", brief)


if __name__ == "__main__":
    unittest.main()
