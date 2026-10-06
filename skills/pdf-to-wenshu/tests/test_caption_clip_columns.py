"""caption-clip 栏宽必须跟图走，不跟图注走。

Frontiers 把跨栏图的图注左对齐挤在左栏：只看图注会切成半幅。
同页并排两栏图的并集也会跨中线：不能因此合成一张。
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

PDF = (
    Path(__file__).resolve().parent
    / "fixtures/two-column-figures.pdf"
)


def _caption(page, needle: str):
    for block in page.get_text("dict").get("blocks") or []:
        if block.get("type") != 0:
            continue
        text = EI._block_text(block)
        if needle not in text:
            continue
        rect = EI.fitz.Rect(block["bbox"])
        num = EI._caption_match(text)
        cut_y, _ = EI._figure_line_cut(block, num) if num is not None else (None, None)
        return rect, cut_y if cut_y is not None else rect.y0
    raise AssertionError("caption not found: " + needle)


@unittest.skipUnless(PDF.is_file(), "Optional two-column PDF fixture not provided")
class CaptionClipColumnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.doc = EI.fitz.open(PDF)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.doc.close()

    def _bounds(self, page_i: int, needle: str):
        page = self.doc[page_i]
        cap, cut_y = _caption(page, needle)
        return EI._column_bounds(page, cap, cut_y), page.rect.width / 2

    def test_fig2_full_width_despite_left_caption(self) -> None:
        (col, x0, x1), mid = self._bounds(4, "FIGURE 2")
        self.assertEqual(col, "full")
        self.assertLess(x0, mid - 40)
        self.assertGreater(x1, mid + 40)

    def test_fig3_full_width_despite_left_caption(self) -> None:
        (col, x0, x1), mid = self._bounds(4, "FIGURE 3")
        self.assertEqual(col, "full")
        self.assertLess(x0, mid - 40)
        self.assertGreater(x1, mid + 40)

    def test_fig10_stays_left_column(self) -> None:
        (col, x0, x1), mid = self._bounds(10, "FIGURE 10")
        self.assertEqual(col, "left")
        self.assertLess(x1, mid + 20)

    def test_fig11_stays_right_column(self) -> None:
        (col, x0, x1), mid = self._bounds(10, "FIGURE 11")
        self.assertEqual(col, "right")
        self.assertGreater(x0, mid - 20)


if __name__ == "__main__":
    unittest.main()
