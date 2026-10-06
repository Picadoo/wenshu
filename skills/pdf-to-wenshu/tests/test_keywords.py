from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "scripts"


def load(name: str):
    spec = importlib.util.spec_from_file_location("kw_" + name, ROOT / (name + ".py"))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


NK = load("normalize_keywords")
LC = load("lint_cluster")

ART = "# T\n\n**Authors**\n\n## Abstract\n\nAbstract text here.\n\n## 1. Introduction\n\nBody.\n"


class NormalizeTests(unittest.TestCase):
    def test_bold_line_becomes_a_section(self) -> None:
        art = ART.replace("Abstract text here.\n",
                          "Abstract text here.\n\n**Keywords:** sand, diffusion, latent space\n")
        got, action = NK.normalize(art)
        self.assertEqual(action, "形态归一")
        self.assertIn("## Keywords\n\nsand, diffusion, latent space", got)

    def test_spaced_out_journal_label_is_recognised(self) -> None:
        """期刊把标签字母拉开排成 `K E Y WO R D S`，抽文本时原样带进来。"""
        art = ART.replace("Abstract text here.\n",
                          "Abstract text here.\n\nK E Y WO R D S denoising diffusion, sand\n")
        got, action = NK.normalize(art)
        self.assertEqual(action, "形态归一")
        self.assertIn("## Keywords\n\ndenoising diffusion, sand", got)

    def test_section_lands_right_after_the_abstract(self) -> None:
        art = ART.replace("Abstract text here.\n",
                          "Abstract text here.\n\n**Keywords:** a, b, c\n")
        got, _ = NK.normalize(art)
        self.assertLess(got.index("## Keywords"), got.index("## 1. Introduction"))

    def test_missing_keywords_are_taken_from_the_source_dump(self) -> None:
        src = "Title\n\nKeywords: superquadric, angle of repose, DEM\n\n1. Introduction\n\nText"
        got, action = NK.normalize(ART, src)
        self.assertEqual(action, "从原文补")
        self.assertIn("superquadric, angle of repose, DEM", got)

    def test_nothing_is_invented_when_the_journal_printed_none(self) -> None:
        """与 Highlights 同一口径：原刊没印就不许硬造。"""
        got, action = NK.normalize(ART, "Title\n\n1. Introduction\n\nText without any labels")
        self.assertEqual(action, "原刊没印")
        self.assertNotIn("## Keywords", got)

    def test_existing_section_is_left_alone(self) -> None:
        art = ART.replace("## 1. Introduction", "## Keywords\n\na, b\n\n## 1. Introduction")
        got, action = NK.normalize(art)
        self.assertEqual(action, "已是标题节")
        self.assertEqual(got, art)


class LintTests(unittest.TestCase):
    def test_bold_line_is_an_error(self) -> None:
        lint = LC.Lint()
        LC.check_keywords(lint, "pid", "# T\n\n**Keywords:** a, b\n\n## 1. Intro\n", "Keywords: a")
        self.assertEqual(len(lint.errors), 1)
        self.assertIn("不是 `## Keywords` 标题节", lint.errors[0][1])

    def test_missing_but_printed_is_an_error(self) -> None:
        lint = LC.Lint()
        LC.check_keywords(lint, "pid", ART, "Title\n\nKeywords: superquadric, DEM\n\n1. Intro")
        self.assertEqual(len(lint.errors), 1)
        self.assertIn("原刊印了关键词", lint.errors[0][1])

    def test_missing_and_not_printed_is_clean(self) -> None:
        lint = LC.Lint()
        LC.check_keywords(lint, "pid", ART, "Title\n\n1. Introduction\n\nText")
        self.assertEqual(lint.errors, [])

    def test_proper_section_is_clean(self) -> None:
        lint = LC.Lint()
        LC.check_keywords(lint, "pid", "## Keywords\n\na, b\n", "Keywords: a, b")
        self.assertEqual(lint.errors, [])

    def test_no_source_dump_means_skip(self) -> None:
        lint = LC.Lint()
        LC.check_keywords(lint, "pid", ART, None)
        self.assertEqual(lint.errors, [])


if __name__ == "__main__":
    unittest.main()
