"""图覆盖检查的分母必须是「PDF 印了几条图注」，不是「磁盘上躺着几个文件」。

合成案例同时覆盖过度抽取造成的误报，以及抽取阶段漏图未被发现的情况。
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


def images_md(n_captions: int) -> str:
    return "# 图片索引\n\n## 覆盖检查\n- 图注识别：图1(p2)、图2(p3)（共 %d 处）\n" % n_captions


def figs(n: int) -> list:
    return ["p_page%d_fig1.png" % i for i in range(1, n + 1)]


class FigureCoverageTests(unittest.TestCase):
    def test_over_extraction_is_not_flagged(self) -> None:
        """正文覆盖所有图注时，多余的未引用文件不应增加覆盖分母。"""
        lint = LC.Lint()
        LC.check_figure_coverage(lint, "pid", images_md(5), figs(76), set(figs(5)))
        self.assertEqual(lint.errors, [])
        self.assertEqual(lint.warns, [])

    def test_extraction_stage_miss_is_error(self) -> None:
        """磁盘图片本身少于图注时，即使全部嵌入也应报告抽取缺失。"""
        lint = LC.Lint()
        LC.check_figure_coverage(lint, "pid", images_md(25), figs(22), set(figs(22)))
        self.assertEqual(len(lint.errors), 1)
        self.assertIn("抽图阶段就漏了", lint.errors[0][1])

    def test_body_missing_real_figures_is_warning(self) -> None:
        """磁盘图片足够，但正文嵌图不足，应报告正文覆盖缺失。"""
        lint = LC.Lint()
        LC.check_figure_coverage(lint, "pid", images_md(77), figs(78), set(figs(52)))
        self.assertEqual(lint.errors, [])
        self.assertEqual(len(lint.warns), 1)
        self.assertIn("少于 PDF 的 77 条图注", lint.warns[0][1])

    def test_body_may_embed_more_than_captions(self) -> None:
        """图注识别不全时，嵌图略多不应被反向认定为漏图。"""
        lint = LC.Lint()
        LC.check_figure_coverage(lint, "pid", images_md(3), figs(15), set(figs(7)))
        self.assertEqual(lint.errors, [])
        self.assertEqual(lint.warns, [])

    def test_sliced_over_embed_is_error(self) -> None:
        """大量碎片全部嵌入不能视为整幅图片已完整覆盖。"""
        lint = LC.Lint()
        LC.check_figure_coverage(lint, "pid", images_md(20), figs(61), set(figs(61)))
        self.assertEqual(len(lint.errors), 1)
        self.assertIn("切碎面板", lint.errors[0][1])

    def test_sliced_figure_group_is_error(self) -> None:
        art = "\n".join(
            ["![[p_page5_fig%d.png|700]]" % i for i in range(1, 7)]
            + ["", "**Fig. 2.** Overview of the two-step method."]
        )
        lint = LC.Lint()
        LC.check_sliced_figure_groups(lint, "pid", art, "英文正文")
        self.assertEqual(len(lint.errors), 1)
        self.assertIn("切碎面板", lint.errors[0][1])

    def test_one_embed_per_caption_is_fine(self) -> None:
        art = "![[p_page5_fig2.png|700]]\n\n**Fig. 2.** Overview of the two-step method.\n"
        lint = LC.Lint()
        LC.check_sliced_figure_groups(lint, "pid", art, "英文正文")
        self.assertEqual(lint.errors, [])

    def test_unreliable_caption_count_is_skipped(self) -> None:
        """图注只数出 1~2 条多半是体例没认出来，拿它当分母比不查还糟。"""
        lint = LC.Lint()
        LC.check_figure_coverage(lint, "pid", images_md(1), figs(13), set())
        self.assertEqual(lint.errors, [])
        self.assertEqual(lint.warns, [])

    def test_missing_record_skips_quietly(self) -> None:
        """老论文的 images.md 没记图注数，跳过而不是拿磁盘数硬凑一个分母。"""
        lint = LC.Lint()
        LC.check_figure_coverage(lint, "pid", "# 图片索引\n\n总计：13 张图片\n",
                                 figs(13), set(figs(2)))
        self.assertEqual(lint.errors, [])
        self.assertEqual(lint.warns, [])


if __name__ == "__main__":
    unittest.main()
