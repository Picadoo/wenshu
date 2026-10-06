"""数学字母字形错映射 + 中英公式对拷落差的回归测试。

背景：Springer 系 PDF 抽文本会丢 Plane-1 高位，把 U+1D400–U+1D7FF 的数学字母整体
减 0x10000 落进谚文区（`휌` 其实是 `𝜌`）。合成案例检查字形恢复、韩文保护，
以及中英公式数量不一致时的检查行为。
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "lint_cluster.py"
SPEC = importlib.util.spec_from_file_location("lint_cluster", SCRIPT)
assert SPEC and SPEC.loader
LC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LC)

FIX_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fix_article.py"
FIX_SPEC = importlib.util.spec_from_file_location("fix_article", FIX_SCRIPT)
assert FIX_SPEC and FIX_SPEC.loader
FIX = importlib.util.module_from_spec(FIX_SPEC)
FIX_SPEC.loader.exec_module(FIX)

# 构造丢失高位的数学字母码点，作为合成样本。
RHO = "\ud70c"        # U+1D70C MATHEMATICAL ITALIC SMALL RHO 丢高位
LAMBDA = "\ud706"     # U+1D706 MATHEMATICAL ITALIC SMALL LAMDA 丢高位
BOLD_X = "\ud417"     # U+1D417 MATHEMATICAL BOLD CAPITAL X 丢高位


class RestoreMathGlyphTests(unittest.TestCase):
    def test_restores_lost_plane1_math_letters(self) -> None:
        src = "where %s and %s are density, %s is a multiplier" % (RHO, BOLD_X, LAMBDA)
        fixed, n = LC.restore_math_glyphs(src)
        self.assertEqual(n, 3)
        self.assertEqual(fixed, "where ρ and X are density, λ is a multiplier")

    def test_clean_text_is_untouched(self) -> None:
        src = "where ρ and X are density"
        fixed, n = LC.restore_math_glyphs(src)
        self.assertEqual(n, 0)
        self.assertIs(fixed, src)

    def test_real_korean_document_is_left_alone(self) -> None:
        """真韩语文档必须整篇让开——宁可留乱码报警，也不能把韩文改成希腊字母。"""
        src = "한국어 논문 %s" % RHO
        fixed, n = LC.restore_math_glyphs(src)
        self.assertEqual(n, 0)
        self.assertEqual(fixed, src)

    def test_lint_reports_mojibake_as_error(self) -> None:
        lint = LC.Lint()
        LC.check_math_glyphs(lint, "pid", "M = %slnxlnylnz" % RHO, "英文正文")
        self.assertEqual(len(lint.errors), 1)
        self.assertIn("谚文字形", lint.errors[0][1])

    def test_lint_downgrades_to_warning_when_korean_present(self) -> None:
        lint = LC.Lint()
        LC.check_math_glyphs(lint, "pid", "한국어 %s" % RHO, "英文正文")
        self.assertEqual(lint.errors, [])
        self.assertEqual(len(lint.warns), 1)

    def test_fix_article_repairs_and_reports(self) -> None:
        fixes: list = []
        out = FIX.fix_math_glyphs("density %s" % RHO, fixes)
        self.assertEqual(out, "density ρ")
        self.assertEqual(len(fixes), 1)
        self.assertIn("字形还原", fixes[0])


def zh_article(n: int) -> str:
    return "\n\n".join("$$a_{%d}=b \\tag{%d}$$" % (i, i) for i in range(1, n + 1))


class EquationParityTests(unittest.TestCase):
    def test_english_without_any_equation_is_error(self) -> None:
        lint = LC.Lint()
        LC.check_eq_parity(lint, "pid", zh_article(28), "Ms = Nz ∑ nz=1 Ny ∑ ny=1")
        self.assertEqual(len(lint.errors), 1)
        self.assertIn("公式对拷没生效", lint.errors[0][1])

    def test_matching_counts_pass(self) -> None:
        lint = LC.Lint()
        LC.check_eq_parity(lint, "pid", zh_article(28), zh_article(28))
        self.assertEqual(lint.errors, [])
        self.assertEqual(lint.warns, [])

    def test_half_missing_is_warning(self) -> None:
        lint = LC.Lint()
        LC.check_eq_parity(lint, "pid", zh_article(20), zh_article(4))
        self.assertEqual(lint.errors, [])
        self.assertEqual(len(lint.warns), 1)

    def test_short_paper_without_equations_is_not_flagged(self) -> None:
        """公式本来就少的论文不该被误报——阈值 3 条以下不判。"""
        lint = LC.Lint()
        LC.check_eq_parity(lint, "pid", zh_article(2), "no math here")
        self.assertEqual(lint.errors, [])
        self.assertEqual(lint.warns, [])

    def test_translator_added_chinese_equations_do_not_count(self) -> None:
        """含中文的公式是译者加的，不在对拷范围，不能拿它要求英文侧也有。"""
        lint = LC.Lint()
        zh = "\n\n".join("$$\\text{降雨量}_{%d} \\tag{%d}$$" % (i, i) for i in range(1, 9))
        LC.check_eq_parity(lint, "pid", zh, "plain english text")
        self.assertEqual(lint.errors, [])


if __name__ == "__main__":
    unittest.main()
