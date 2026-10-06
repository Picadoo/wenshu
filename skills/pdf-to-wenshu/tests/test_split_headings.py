from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prep_article_en.py"
SPEC = importlib.util.spec_from_file_location("prep_article_en_headings", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

BODY = ("Settling columns of heights between 0.45 and 3.6 m were used here "
        "to measure the drag of the particles.")


def page(*lines: str) -> list:
    return list(lines)


def heads(pages: list) -> list:
    return [s.strip() for _n, pg in pages for s in pg if MODULE.NUM_HEAD.match(s.strip())]


class SplitHeadingTests(unittest.TestCase):
    """arXiv 体例把章节号单独排一行，编号与标题必须先接回同一行才认得出层级。"""

    def test_bare_number_and_title_are_joined(self) -> None:
        pages = [(1, page("1", "Introduction", BODY, "2", "Materials", BODY))]
        self.assertEqual(heads(MODULE.join_split_headings(pages)),
                         ["1 Introduction", "2 Materials"])

    def test_wrapped_title_is_joined_until_a_full_width_body_line(self) -> None:
        """标题折成几段时要全部拼回；一撞上满宽正文行就停，不能把正文首句吸进标题。"""
        pages = [(1, page("1", "Introduction", BODY,
                          "2", "Intermediate regime:", "experiments in", "settling columns",
                          BODY))]
        self.assertIn("2 Intermediate regime: experiments in settling columns",
                      heads(MODULE.join_split_headings(pages)))

    def test_hyphenated_title_uses_the_shared_glue_rule(self) -> None:
        """`solu-`+`tions` 要拼成 solutions，`particle-to-`+`fluid` 的连字符却得留着。"""
        pages = [(1, page("1", "Introduction", BODY,
                          "2", "Analytical solu-", "tions", BODY,
                          "3", "Particle-to-", "fluid density ratio", BODY,
                          "The particle-to-fluid density ratio governs the settling behaviour."))]
        got = heads(MODULE.join_split_headings(pages))
        self.assertIn("2 Analytical solutions", got)
        self.assertIn("3 Particle-to-fluid density ratio", got)

    def test_printed_page_numbers_are_not_mistaken_for_sections(self) -> None:
        """页码也是「一行一个数字」，但它贴在页首/页尾且与页序同步递增。"""
        pages = [(n, page(str(n), BODY, "Conclusions of the study are summarised here."))
                 for n in range(1, 6)]
        self.assertEqual(heads(MODULE.join_split_headings(pages)), [])

    def test_affiliation_numbering_does_not_hijack_the_section_chain(self) -> None:
        """首页机构编号同样是 1/2/3 独占一行；贪心接受会让正文 1 Introduction 失联。"""
        pages = [
            (1, page("1", "Department of Civil Engineering, Anywhere University",
                     "2", "Institute of Particle Technology, Elsewhere University")),
            (2, page("1", "Introduction", BODY,
                     "2", "Governing equations", BODY,
                     "3", "Results", BODY)),
        ]
        got = heads(MODULE.join_split_headings(pages))
        self.assertEqual(got, ["1 Introduction", "2 Governing equations", "3 Results"])

    def test_references_heading_is_left_alone(self) -> None:
        """`6`+`References` 一旦拼成一行，收尾检测就找不到参考文献起点。"""
        pages = [(1, page("1", "Introduction", BODY, "6", "References", BODY))]
        got = heads(MODULE.join_split_headings(pages))
        self.assertEqual(got, ["1 Introduction"])

    def test_bare_section_numbers_survive_running_header_cleanup(self) -> None:
        """strip_running 把数字归一成 `#`，裸章节号会被整批当页眉删光——所以必须先拼。"""
        pages = [(n, page("2.%d" % n, "Section title %s" % "abcd"[n - 1], BODY))
                 for n in range(1, 5)]
        stripped = MODULE.strip_running([(n, list(pg)) for n, pg in pages])
        self.assertEqual([s for _n, pg in stripped for s in pg
                          if MODULE.BARE_NUM.match(s.strip())], [])


class TitleCaseTests(unittest.TestCase):
    """全大写标题还原成正常大小写时，缩写不能被压成 Cfd-dem。"""

    def test_hyphenated_acronym_survives(self) -> None:
        """`CFD-DEM` 整体是缩写，逐词判会把它压成 `Cfd-dem`。"""
        self.assertEqual(
            MODULE.titlecase("DESCRIPTION OF CFD-DEM COUPLING METHOD"),
            "Description Of CFD-DEM Coupling Method")

    def test_acronym_is_collected_from_mixed_case_prose(self) -> None:
        """白名单里没有的缩写，靠正文里「小写句子中的全大写词」自证。"""
        prose = ["The proposed SDFEM solver couples the phases.",
                 "Results from SDFEM agree with experiments."]
        got = MODULE.collect_acronyms(prose)
        self.assertIn("SDFEM", got)
        self.assertEqual(MODULE.titlecase("THE SDFEM FRAMEWORK", got),
                         "The SDFEM Framework")
        self.assertEqual(MODULE.titlecase("THE SDFEM FRAMEWORK"), "The Sdfem Framework")

    def test_all_caps_lines_are_not_evidence(self) -> None:
        """整行大写是版式，拿它当语料等于把每个词都认成缩写。"""
        self.assertEqual(MODULE.collect_acronyms(["A COMPLETELY UPPERCASE HEADING"]), set())

    def test_common_word_shouted_once_is_not_an_acronym(self) -> None:
        """图例里喊了一次 MODEL，正文满篇 model —— 它是普通词，不能当缩写留着。"""
        prose = ["The MODEL column lists each case.",
                 "The MODEL is calibrated against experiments.",
                 "Our model reproduces the measured drag.",
                 "This model is compared with the SDFEM model.",
                 "The SDFEM solver couples both phases."]
        got = MODULE.collect_acronyms(prose)
        self.assertNotIn("MODEL", got)
        self.assertIn("SDFEM", got)

    def test_mixed_case_title_is_left_alone(self) -> None:
        self.assertEqual(MODULE.titlecase("Point cloud autoencoder"),
                         "Point cloud autoencoder")


class ReworkGateTests(unittest.TestCase):
    """返工晋级门槛：任一维度真的更好、另一维度都不许更差。"""

    @staticmethod
    def art(heads: int, eqs: int) -> str:
        out = ["# T", "", "## Abstract", "", "Text.", ""]
        for i in range(1, heads + 1):
            out += ["## %d. Section" % i, "", "Prose about granular flow.", ""]
        for i in range(1, eqs + 1):
            out += ["$$", "a = b \\tag{%d}" % i, "$$", ""]
        return "\n".join(out)

    def test_more_headings_alone_is_enough(self) -> None:
        """公式数一样、标题从 8 涨到 23 —— 只看公式会把这类改进整个漏掉。"""
        self.assertTrue(MODULE.rework_promotion_eligible(
            self.art(23, 39), self.art(8, 39), 0))

    def test_more_equations_alone_is_still_enough(self) -> None:
        self.assertTrue(MODULE.rework_promotion_eligible(
            self.art(5, 28), self.art(5, 0), 0))

    def test_losing_headings_blocks_promotion(self) -> None:
        """公式更多但标题变少，说明重生成砸了结构，不许入库。"""
        self.assertFalse(MODULE.rework_promotion_eligible(
            self.art(3, 40), self.art(20, 39), 0))

    def test_no_improvement_is_not_promotable(self) -> None:
        self.assertFalse(MODULE.rework_promotion_eligible(
            self.art(8, 39), self.art(8, 39), 0))

    def test_hard_lint_error_blocks_promotion(self) -> None:
        self.assertFalse(MODULE.rework_promotion_eligible(
            self.art(23, 39), self.art(8, 39), 1))


if __name__ == "__main__":
    unittest.main()
