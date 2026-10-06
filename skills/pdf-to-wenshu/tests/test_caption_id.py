"""图注识别必须拒正文交叉引用，并认出附录图号。

Liu2026 点云篇：正文 'In Fig. 12b, we…' 曾被当成 Fig. 12 再裁一刀；
附录 'Fig. A.21.' / 'Fig. A.22.' 则完全漏掉。
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "extract_images.py"
SPEC = importlib.util.spec_from_file_location("extract_images", SCRIPT)
assert SPEC and SPEC.loader
EI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EI)


class CaptionIdTests(unittest.TestCase):
    def test_plain_caption(self) -> None:
        self.assertEqual(EI._caption_id("Fig. 2. Overview of the two-step method."), ("", 2))
        self.assertEqual(EI._caption_match("Fig. 2. Overview of the two-step method."), 2)

    def test_rejects_in_fig_crossref(self) -> None:
        self.assertIsNone(EI._caption_id(
            "In Fig. 12b, we further perform a convergence analysis on the proposed method."))

    def test_rejects_fig_na_plots(self) -> None:
        self.assertIsNone(EI._caption_id(
            "Fig. 12a plots the settling velocity, obtained by the proposed method."))

    def test_rejects_fig_range_illustrates(self) -> None:
        self.assertIsNone(EI._caption_id(
            "Fig. 19(a-f) illustrates the typical collapse dynamics of monodisperse systems."))

    def test_appendix_caption(self) -> None:
        self.assertEqual(
            EI._caption_id("Fig. A.21. No-flux point approach for physical boundaries."),
            ("A", 21),
        )
        self.assertEqual(
            EI._caption_id("Fig. A.22. Volume fraction distribution of a natural densely packed granular column."),
            ("A", 22),
        )
        self.assertEqual(EI._fig_tag("A", 21), "A21")

    def test_chinese_caption(self) -> None:
        self.assertEqual(EI._caption_id("图 2. 两步粗粒化方法概览。"), ("", 2))
        self.assertEqual(EI._caption_id("图 A.22. 体积分数分布。"), ("A", 22))

    def test_body_caption_still_rejected(self) -> None:
        self.assertIsNone(EI._caption_id("Fig. 5 shows the flow chart of the proposed method."))


if __name__ == "__main__":
    unittest.main()
