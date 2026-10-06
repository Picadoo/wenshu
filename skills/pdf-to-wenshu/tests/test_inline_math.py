from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "inline_math_from_rich.py"
SPEC = importlib.util.spec_from_file_location("inline_math_from_rich", SCRIPT)
assert SPEC and SPEC.loader
IM = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IM)


class SymbolMapTests(unittest.TestCase):
    def test_flat_form_maps_to_latex(self) -> None:
        rich = "The C_{D} rises while C_{D} falls and a_{1} plus a_{1} matter."
        got = IM.build_symbol_map(rich)
        self.assertEqual(got["CD"], "C_{D}")
        self.assertEqual(got["a1"], "a_{1}")

    def test_greek_in_script_flattens_to_the_character(self) -> None:
        """rich 里是 `v_{\\infty}`，纯文本 dump 里就是 `v∞`，两者要对得上。"""
        rich = "speed v_{\\infty} and v_{\\infty} again"
        self.assertEqual(IM.build_symbol_map(rich)["v∞"], r"v_{\infty}")

    def test_single_occurrence_is_ignored(self) -> None:
        """只出现一次的多半是抽取噪声，不进表。"""
        self.assertNotIn("Qz", IM.build_symbol_map("only once Q_{z} here"))

    def test_true_ambiguity_is_dropped(self) -> None:
        """`Re_2` 与 `Re^2` 势均力敌又没有同族可参照，分不清就别猜。"""
        rich = "Re_{2} Re_{2} Re^{2} Re^{2}"
        self.assertNotIn("Re2", IM.build_symbol_map(rich))

    def test_family_consistency_resolves_baseline_noise(self) -> None:
        """a1/a2/a5 都是下标，占比只有 0.6 的 a3 也该判下标，而不是整条丢掉。

        丢掉的后果是正文里出现 `$a_{1}$ $a_{2}$ a3` 这种花脸。
        """
        rich = ("a_{1} a_{1} a_{2} a_{2} a_{5} a_{5} "
                "a_{3} a_{3} a_{3} a^{3} a^{3}")
        got = IM.build_symbol_map(rich)
        self.assertEqual(got["a3"], "a_{3}")

    def test_plain_word_is_dropped_by_rich_evidence(self) -> None:
        """某形态在 rich 里绝大多数时候光秃秃出现 = 它是普通词，不是符号。"""
        rich = ("Pa Pa Pa Pa Pa Pa measured in P_{a} P_{a} units")
        self.assertNotIn("Pa", IM.drop_wordlike(IM.build_symbol_map(rich), rich))

    def test_symbol_survives_when_mostly_marked(self) -> None:
        rich = "p_{a} p_{a} p_{a} p_{a} and one bare pa"
        self.assertIn("pa", IM.drop_wordlike(IM.build_symbol_map(rich), rich))


class WrapTests(unittest.TestCase):
    SMAP = {"CD": "C_{D}", "a1": "a_{1}"}

    def test_bare_token_is_wrapped(self) -> None:
        got, hits = IM.wrap_inline("The CD depends on a1 here.", self.SMAP)
        self.assertEqual(got, "The $C_{D}$ depends on $a_{1}$ here.")
        self.assertEqual(hits["CD"], 1)

    def test_word_boundary_prevents_partial_hits(self) -> None:
        got, _ = IM.wrap_inline("CDF and xCD and CD2 stay put.", self.SMAP)
        self.assertEqual(got, "CDF and xCD and CD2 stay put.")

    def test_existing_inline_math_is_not_double_wrapped(self) -> None:
        got, _ = IM.wrap_inline("already $C_D$ and bare CD.", self.SMAP)
        self.assertEqual(got, "already $C_D$ and bare $C_{D}$.")

    def test_block_math_and_comments_are_protected(self) -> None:
        src = "$$\nCD = a1\n$$\n<!-- TODO CD -->\ntext CD"
        got, _ = IM.wrap_inline(src, self.SMAP)
        self.assertIn("$$\nCD = a1\n$$", got)
        self.assertIn("<!-- TODO CD -->", got)
        self.assertTrue(got.endswith("text $C_{D}$"))

    def test_headings_and_wikilinks_are_protected(self) -> None:
        src = "## 2. CD model\n![[fig CD.png|700]]\nbody CD"
        got, _ = IM.wrap_inline(src, self.SMAP)
        self.assertIn("## 2. CD model", got)
        self.assertIn("![[fig CD.png|700]]", got)
        self.assertIn("body $C_{D}$", got)

    def test_heading_protection_does_not_swallow_the_rest(self) -> None:
        """保护区正则带 re.S，标题那条若写 `.*$` 会从第一个标题吃到文末。"""
        src = "# Title\n\nbody CD here\n\n## Section\n\nmore a1 text"
        got, hits = IM.wrap_inline(src, self.SMAP)
        self.assertEqual(sum(hits.values()), 2)


class MathLetterTests(unittest.TestCase):
    """有些期刊的 PDF 把变量原样保留成 Plane-1 数学字母（𝑝 𝑵 ℝ），不是 ASCII。"""

    def test_style_comes_from_the_codepoint_block(self) -> None:
        self.assertEqual(IM.mathletter_to_tex("\U0001D45D"), "p")          # 数学斜体 p
        self.assertEqual(IM.mathletter_to_tex("\U0001D407"), r"\mathbf{H}")  # 数学粗体 H
        self.assertEqual(IM.mathletter_to_tex("ℝ"), r"\mathbb{R}")
        self.assertEqual(IM.mathletter_to_tex("plain"), "plain")

    def test_math_root_enters_the_symbol_table(self) -> None:
        """词根只认 [A-Za-z] 时，`𝑝_{𝑖}` 一条都进不了表——实测 14 篇因此全无效。"""
        rich = "point \U0001D45D_{\U0001D456} and \U0001D45D_{\U0001D456} again"
        got = IM.build_symbol_map(rich)
        self.assertEqual(got["\U0001D45D\U0001D456"], "p_{i}")

    def test_stuck_word_gets_its_space_back(self) -> None:
        """`𝑝𝑖in the cloud` 里符号与单词粘着，纯词边界判定会整句放弃。"""
        smap = {"\U0001D45D\U0001D456": "p_{i}"}
        got, hits = IM.wrap_inline("Each point \U0001D45D\U0001D456in the cloud", smap)
        self.assertEqual(got, "Each point $p_{i}$ in the cloud")

    def test_bare_math_letter_is_wrapped_too(self) -> None:
        """符号表覆盖不到的裸数学字母也要包，否则前端不按数学体渲染。"""
        got, _ = IM.wrap_inline("space ℝ3 holds \U0001D40Fis bold", {})
        self.assertIn(r"$\mathbb{R}$3", got)
        self.assertIn(r"$\mathbf{P}$ is bold", got)

    def test_math_inside_existing_formula_is_left_alone(self) -> None:
        got, _ = IM.wrap_inline("$\U0001D45D$ stays", {})
        self.assertEqual(got, "$\U0001D45D$ stays")


class CitationTests(unittest.TestCase):
    """期刊用上标排引文号，抽纯文本时塌进词尾：`world1`、`pressure2–5`。"""

    def test_word_with_numeric_superscript_is_a_citation(self) -> None:
        got = IM.citation_map("in the world^{1} under pressure^{2–5} here")
        self.assertEqual(got["world1"], "world[1]")
        self.assertEqual(got["pressure2–5"], "pressure[2–5]")

    def test_trailing_punctuation_is_kept_with_the_word(self) -> None:
        """`rheology.6–8` 里句号在引文号之前，剥出来要还原成 `rheology.[6–8]`。"""
        got = IM.citation_map("granular rheology.^{6–8} however")
        self.assertEqual(got["rheology.6–8"], "rheology.[6–8]")

    def test_single_letter_superscript_is_math_not_citation(self) -> None:
        """`C^{2}`、`Re^{-1/2}` 是数学，不能当引文号剥。"""
        got = IM.citation_map("value C^{2} and Re^{-1/2} appear")
        self.assertEqual(got, {})

    def test_citation_bypasses_the_min_hits_gate(self) -> None:
        """每个「单词+引文号」全文只出现一次，走符号表那条路永远够不到 MIN_HITS。"""
        rich = "in the world^{1} only once"
        self.assertNotIn("world1", IM.build_symbol_map(rich))
        self.assertIn("world1", IM.citation_map(rich))

    def test_applied_to_the_article(self) -> None:
        cites = {"world1": "world[1]"}
        got, hits = IM.wrap_inline("material in the world1 (the first being water)", {}, cites)
        self.assertEqual(got, "material in the world[1] (the first being water)")
        self.assertEqual(hits["(引文号)"], 1)


if __name__ == "__main__":
    unittest.main()
