from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prep_article_en.py"
SPEC = importlib.util.spec_from_file_location("prep_article_en", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class EquationAnchorTests(unittest.TestCase):
    def test_mojibake_parentheses_are_equation_numbers(self) -> None:
        match = MODULE.EQ_NUM.match("ð21Þ")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1) or match.group(2), "21")

    def test_right_aligned_tail_number_is_an_anchor(self) -> None:
        """`∇·u = 0        (5)` 是 LaTeX \\tag 的默认排版，编号不独占一行。"""
        match = MODULE.EQ_NUM_TAIL.match("∇ · u = 0                          (5)")
        self.assertIsNotNone(match)
        self.assertEqual(match.group("num"), "5")
        self.assertEqual(match.group("body"), "∇ · u = 0")

    def test_prose_with_trailing_citation_is_not_an_anchor(self) -> None:
        """句尾的引文号不带运算符，不能被当成公式号，否则整段正文会被剥成公式。"""
        self.assertIsNone(MODULE.EQ_NUM_TAIL.match(
            "as reported by previous work                       (7)"))

    def test_mojibake_equation_numbers_survive_running_header_cleanup(self) -> None:
        pages = [
            (number, ["Repeated journal header 2022", f"ð{number}Þ", "x = y"])
            for number in range(1, 5)
        ]
        cleaned = MODULE.strip_running(pages)
        for number, lines in cleaned:
            self.assertIn(f"ð{number}Þ", lines)
            self.assertNotIn("Repeated journal header 2022", lines)

    def test_mojibake_anchor_transplants_chinese_latex(self) -> None:
        body, stats = MODULE.reflow(
            [(1, ["The balance is:", "x = y", "ð1Þ"])],
            "Paper",
            {},
            {"1": r"x=y\tag{1}"},
            {},
        )
        rendered = "\n".join(body)
        self.assertIn(r"x=y\tag{1}", rendered)
        self.assertEqual(stats["eq_hit"], 1)
        self.assertEqual(stats["eq_miss"], [])

    def test_consecutive_equations_keep_both_latex_blocks(self) -> None:
        body, stats = MODULE.reflow(
            [(1, ["The relations are:", "x = y", "ð1Þ", "z = w", "ð2Þ"])],
            "Paper",
            {},
            {"1": r"x=y\tag{1}", "2": r"z=w\tag{2}"},
            {},
        )
        rendered = "\n".join(body)
        self.assertIn(r"x=y\tag{1}", rendered)
        self.assertIn(r"z=w\tag{2}", rendered)
        self.assertEqual(rendered.count("$$"), 4)
        self.assertEqual(stats["eq_hit"], 2)


class TablePlacementTests(unittest.TestCase):
    def test_caption_suffix_places_table_when_extractor_prepends_prose(self) -> None:
        tables = {
            3: {
                "caption": (
                    "increased bed porosity. Increasing superficial gas velocity also "
                    "increases the bed height. Mean pressure drops (unit: Pa) at "
                    "different operating parameters."
                ),
                "markdown": "| Ug | AR = 1 |\n| --- | --- |",
            }
        }
        self.assertTrue(
            MODULE._is_table_label(
                "Table 3",
                "Mean pressure drops (unit: Pa) at different operating parameters.",
                {3: "caption"},
                set(),
                tables,
            )
        )


class PromotionGateTests(unittest.TestCase):
    def test_only_todo_free_warning_free_draft_is_promoted(self) -> None:
        self.assertTrue(MODULE.promotion_eligible(0, 0))
        self.assertFalse(MODULE.promotion_eligible(1, 0))
        self.assertFalse(MODULE.promotion_eligible(0, 1))


class AffiliationTests(unittest.TestCase):
    def test_extracts_title_block_affiliation(self) -> None:
        pages = [(1, [
            "A paper title",
            "Shuai Wang, Yansong Shen",
            "School of Chemical Engineering, University of New South Wales, Sydney",
            "h i g h l i g h t s",
            "Department mentioned later must not be captured",
        ])]
        self.assertEqual(
            MODULE.extract_affiliation(pages),
            "School of Chemical Engineering, University of New South Wales, Sydney",
        )

    def test_unrecognized_title_block_keeps_todo_path(self) -> None:
        self.assertEqual(MODULE.extract_affiliation([(1, ["Title", "Author", "Abstract"])]), "")


def zh_with_equations(n: int) -> str:
    return "\n\n".join("$$a_{%d}=b \\tag{%d}$$" % (i, i) for i in range(1, n + 1))


class StaleMachineDraftTests(unittest.TestCase):
    """防覆盖闸必须放行陈旧机器稿，同时继续护住人工校订稿。

    2026-09-01 之前这道闸只看「非空」，把 42 篇公式全丢的旧稿永久锁死——
    lint 报错误、脚本却拒绝重生成，形成死锁。
    """

    def _pair(self, tmp: str, zh: str, en: str):
        zh_path, en_path = Path(tmp) / "p.正文.md", Path(tmp) / "p.正文.en.md"
        zh_path.write_text(zh, encoding="utf-8")
        en_path.write_text(en, encoding="utf-8")
        return zh_path, en_path

    def test_stale_machine_draft_is_overwritable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            zh, en = self._pair(tmp, zh_with_equations(28), "Ms = Nz ∑ nz=1 Ny ∑ ny=1")
            self.assertTrue(MODULE._is_stale_machine_en(zh, en))

    def test_reviewed_article_with_equations_is_protected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            zh, en = self._pair(tmp, zh_with_equations(28), zh_with_equations(28))
            self.assertFalse(MODULE._is_stale_machine_en(zh, en))

    def test_paper_without_equations_is_protected(self) -> None:
        """本来就没公式的论文，英文稿零公式是正常的，不能当陈旧稿覆盖掉。"""
        with tempfile.TemporaryDirectory() as tmp:
            zh, en = self._pair(tmp, "纯文字综述，没有公式", "A prose-only review")
            self.assertFalse(MODULE._is_stale_machine_en(zh, en))

    def test_missing_file_is_protected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            zh, _en = self._pair(tmp, zh_with_equations(9), "x")
            self.assertFalse(MODULE._is_stale_machine_en(zh, Path(tmp) / "nope.md"))


class ReworkGateTests(unittest.TestCase):
    """返工门槛的对照物是「已经坏掉的正文」，不是「完美稿」。

    沿用首次入库那条零警告门槛的话，42 篇待返工只放行 4 篇——门禁反过来在保护故障。
    """

    BROKEN = "Ms = Nz ∑ nz=1 Ny ∑ ny=1 \ud70c"      # 库内现状：零公式 + 乱码

    def test_strictly_better_draft_is_promoted(self) -> None:
        self.assertTrue(MODULE.rework_promotion_eligible(
            zh_with_equations(28), self.BROKEN, 0))

    def test_hard_error_still_blocks(self) -> None:
        self.assertFalse(MODULE.rework_promotion_eligible(
            zh_with_equations(28), self.BROKEN, 1))

    def test_draft_without_more_equations_is_not_promoted(self) -> None:
        """公式没变多就不算返工成功，别拿一份等价稿去覆盖库内文件。"""
        self.assertFalse(MODULE.rework_promotion_eligible(
            "no math at all", self.BROKEN, 0))

    def test_draft_adding_mojibake_is_rejected(self) -> None:
        """公式变多但引入了新的错映射字形，属于按下葫芦浮起瓢，不放行。"""
        draft = zh_with_equations(28) + "\n\n\ud70c\ud706\ud714"
        self.assertFalse(MODULE.rework_promotion_eligible(draft, self.BROKEN, 0))

    def test_todo_alone_does_not_block_rework(self) -> None:
        """TODO 是 HTML 注释、读者看不见，是给 D 档的工单，不该拦住一份更好的稿。"""
        draft = zh_with_equations(28) + "\n\n<!-- TODO 单位行需人工补 -->"
        self.assertTrue(MODULE.rework_promotion_eligible(draft, self.BROKEN, 0))


if __name__ == "__main__":
    unittest.main()
