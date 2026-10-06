"""中文正文 `## 亮点` 必须让读者分清：是原刊印的要点，还是 AI 提炼的。

技能对两侧的口径本来不对称——英文侧禁止捏造 Highlights，中文侧允许提炼却从不标注。
2026-09-01 全库 95 篇里 84 篇的亮点是 AI 总结的，零标注，和期刊自印要点长得一模一样。
"""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

LC_PATH = Path(__file__).resolve().parents[1] / "scripts" / "lint_cluster.py"
LC_SPEC = importlib.util.spec_from_file_location("lint_cluster", LC_PATH)
assert LC_SPEC and LC_SPEC.loader
LC = importlib.util.module_from_spec(LC_SPEC)
LC_SPEC.loader.exec_module(LC)

FIX_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fix_article.py"
FIX_SPEC = importlib.util.spec_from_file_location("fix_article", FIX_PATH)
assert FIX_SPEC and FIX_SPEC.loader
FIX = importlib.util.module_from_spec(FIX_SPEC)
FIX_SPEC.loader.exec_module(FIX)

SRC_WITH_HL = "Some Title\n\nHighlights\n\n• We propose a model\n\nAbstract\n\nText."
SRC_WITHOUT_HL = "Some Title\n\nAbstract\n\nWe propose a model and validate it."

PLAIN = "# 题目\n\n## 亮点\n\n- 要点一\n- 要点二\n\n## 摘要\n\n正文。\n"
MARKED = ("# 题目\n\n## 亮点\n\n- 要点一\n- 要点二\n\n"
          + LC.AI_HL_NOTICE + "\n\n## 摘要\n\n正文。\n")


class ProvenanceLintTests(unittest.TestCase):
    def test_ai_written_highlights_without_notice_is_error(self) -> None:
        lint = LC.Lint()
        LC.check_highlights_provenance(lint, "pid", PLAIN, SRC_WITHOUT_HL)
        self.assertEqual(len(lint.errors), 1)
        self.assertIn("没有标注", lint.errors[0][1])

    def test_ai_written_highlights_with_notice_passes(self) -> None:
        lint = LC.Lint()
        LC.check_highlights_provenance(lint, "pid", MARKED, SRC_WITHOUT_HL)
        self.assertEqual(lint.errors, [])

    def test_translated_highlights_need_no_notice(self) -> None:
        lint = LC.Lint()
        LC.check_highlights_provenance(lint, "pid", PLAIN, SRC_WITH_HL)
        self.assertEqual(lint.errors, [])

    def test_translated_highlights_wrongly_marked_is_error(self) -> None:
        """原刊自己印了要点，却标成 AI 提炼，同样是误导读者。"""
        lint = LC.Lint()
        LC.check_highlights_provenance(lint, "pid", MARKED, SRC_WITH_HL)
        self.assertEqual(len(lint.errors), 1)
        self.assertIn("译自原文", lint.errors[0][1])

    def test_no_source_text_skips_quietly(self) -> None:
        lint = LC.Lint()
        LC.check_highlights_provenance(lint, "pid", PLAIN, None)
        self.assertEqual(lint.errors, [])


class ProvenanceFixTests(unittest.TestCase):
    def _write(self, tmp: str, art: str, src: str) -> Path:
        p = Path(tmp) / "p.正文.md"
        p.write_text(art, encoding="utf-8")
        (Path(tmp) / "p.txt").write_text(src, encoding="utf-8")
        return p

    def test_notice_is_added_after_the_list(self) -> None:
        """必须加在列表之后：插在标题和列表之间会让前端亮点卡片不渲染。"""
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, PLAIN, SRC_WITHOUT_HL)
            fixes: list = []
            out = FIX.fix_ai_highlights_notice(PLAIN, str(p), True, fixes)
            self.assertEqual(len(fixes), 1)
            self.assertIn(LC.AI_HL_NOTICE, out)
            self.assertLess(out.index("- 要点二"), out.index("【说明】"))
            self.assertLess(out.index("【说明】"), out.index("## 摘要"))

    def test_notice_is_removed_when_source_has_highlights(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, MARKED, SRC_WITH_HL)
            fixes: list = []
            out = FIX.fix_ai_highlights_notice(MARKED, str(p), True, fixes)
            self.assertEqual(len(fixes), 1)
            self.assertNotIn("【说明】", out)

    def test_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, MARKED, SRC_WITHOUT_HL)
            fixes: list = []
            out = FIX.fix_ai_highlights_notice(MARKED, str(p), True, fixes)
            self.assertEqual(fixes, [])
            self.assertEqual(out, MARKED)

    def test_english_article_is_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, PLAIN, SRC_WITHOUT_HL)
            fixes: list = []
            out = FIX.fix_ai_highlights_notice(PLAIN, str(p), False, fixes)
            self.assertEqual(fixes, [])
            self.assertEqual(out, PLAIN)


if __name__ == "__main__":
    unittest.main()
