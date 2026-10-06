from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "lint_cluster.py"
SPEC = importlib.util.spec_from_file_location("lint_cluster_tables", SCRIPT)
assert SPEC and SPEC.loader
LC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LC)

TABLE = "\n".join(["| a | b |", "| --- | --- |", "| 1 | 2 |"])


def article(tables: int = 0, captions: int = 0) -> str:
    out = ["# T", "", "## Abstract", "", "Text.", ""]
    for i in range(1, captions + 1):
        out += ["**Table %d: Coefficients for the model**" % i, ""]
    for _ in range(tables):
        out += [TABLE, ""]
    return "\n".join(out)


class TableParityTests(unittest.TestCase):
    def test_chinese_has_tables_but_english_has_none_is_error(self) -> None:
        """一侧有完整表格，另一侧只有表题时，应报告表体缺失。"""
        lint = LC.Lint()
        LC.check_table_parity(lint, "pid", article(tables=17), article(captions=17))
        self.assertEqual(len(lint.errors), 1)
        self.assertIn("一张表都没有", lint.errors[0][1])

    def test_both_sides_have_tables_is_clean(self) -> None:
        lint = LC.Lint()
        LC.check_table_parity(lint, "pid", article(tables=5), article(tables=5, captions=5))
        self.assertEqual(lint.errors, [])
        self.assertEqual(lint.warns, [])

    def test_fewer_bodies_than_captions_is_only_a_warning(self) -> None:
        """有些表是被当图片抽走的，表体确实不在 Markdown 里，判错误会误伤。"""
        lint = LC.Lint()
        LC.check_table_parity(lint, "pid", article(tables=3), article(tables=2, captions=3))
        self.assertEqual(lint.errors, [])
        self.assertEqual(len(lint.warns), 1)

    def test_paper_without_tables_is_not_flagged(self) -> None:
        lint = LC.Lint()
        LC.check_table_parity(lint, "pid", article(), article())
        self.assertEqual(lint.errors, [])
        self.assertEqual(lint.warns, [])

    def test_bold_sentence_opening_is_not_a_caption(self) -> None:
        """`**Table 11** shows the relative error…` 是正文句子，不是表题。"""
        prose = ("**Table 11** shows the relative error of the logarithmic models, "
                 "and the available correlations are compared below.")
        self.assertEqual(LC.TAB_CAP.findall(prose), [])
        self.assertEqual(len(LC.TAB_CAP.findall("**Table 1: Coefficients for Eq.(7)**")), 1)

    def test_english_only_paper_is_skipped(self) -> None:
        lint = LC.Lint()
        LC.check_table_parity(lint, "pid", article(tables=4), "")
        self.assertEqual(lint.errors, [])


if __name__ == "__main__":
    unittest.main()
