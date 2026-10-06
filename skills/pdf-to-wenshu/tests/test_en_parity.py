from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "lint_cluster.py"
SPEC = importlib.util.spec_from_file_location("lint_cluster_parity", SCRIPT)
assert SPEC and SPEC.loader
LC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LC)

BYLINE = ("**A B Author, C D Author**\n\n"
          "1. Department of Civil Engineering, Somewhere University, City, Country\n\n"
          "*Journal of Things 2024, 12(3): 1-20. DOI: 10.1000/abc*\n")
SRC = "Title\n\nR E F E R E N C E S\n\n1. Someone A. A paper. Journal. 2020;1:1-2.\n"


def article(refs: bool = True, watermark: bool = False, backmatter: bool = False) -> str:
    out = ["# An English Title", "", BYLINE, "## Abstract", "", "Abstract text.", "",
           "## 1. Introduction", "", "Body prose about granular flow.", ""]
    if watermark:
        out += ["OA articles are governed by the applicable Creative Commons License", ""]
    if backmatter:
        out += ["AU T H O R C O N T R I B U T I O N S Someone did something.", ""]
    if refs:
        out += ["## References", "", "1. Someone A. A paper. Journal. 2020;1:1-2.", ""]
    return "\n".join(out)


def run(art: str, src: str = SRC):
    lint = LC.Lint()
    LC.check_en_parity_with_zh(lint, "pid", art, BYLINE, src)
    # Draft validation allows an unassembled reference list; publication does not.
    LC.check_cluster_en_references(lint, "pid", art, BYLINE, src)
    return lint


class ParityTests(unittest.TestCase):
    """英文正文要和中文正文一样严——不对称是全部问题的总根源。"""

    def test_missing_references_section_is_an_error(self) -> None:
        """中文侧「缺参考文献章节」早就判错误，英文侧却完全不查，于是只有 8% 达标。"""
        lint = run(article(refs=False))
        self.assertTrue(any("## References" in m for _p, m in lint.errors))

    def test_references_not_required_when_source_has_none(self) -> None:
        lint = run(article(refs=False), src="Title\n\nJust body text, no reference list.\n")
        self.assertFalse(any("## References" in m for _p, m in lint.errors))

    def test_spaced_out_backmatter_label_is_an_error(self) -> None:
        """`AU T H O R C O N T R I B U T I O N S` 还躺在正文里 = 后置事项没分节。"""
        lint = run(article(backmatter=True))
        self.assertTrue(any("后置事项" in m for _p, m in lint.errors))

    def test_watermark_is_an_error(self) -> None:
        lint = run(article(watermark=True))
        self.assertTrue(any("水印" in m for _p, m in lint.errors))

    def test_fragmented_affiliation_is_an_error(self) -> None:
        """单位块被抽成碎片：一行里三段以上用「；」拼接的截断机构名。"""
        frag = ("**Authors**\n\nUniversity, Piscataway, New Jersey, USA；University, New York；"
                "Engineering, University of Tennessee,；Nikolaos N. Vlassis, Department of\n")
        lint = LC.Lint()
        LC.check_en_parity_with_zh(lint, "pid", article(), frag, SRC)
        self.assertTrue(any("单位块是碎片" in m for _p, m in lint.errors))

    def test_missing_journal_line_is_only_a_warning(self) -> None:
        lint = LC.Lint()
        LC.check_en_parity_with_zh(lint, "pid", article(), "**Authors**\n\nSome Dept\n", SRC)
        self.assertEqual(lint.errors, [])
        self.assertTrue(any("期刊信息行" in m for _p, m in lint.warns))

    def test_block_math_without_inline_math_is_a_warning(self) -> None:
        art = article() + "\n\n$$\nx = y\n$$\n\n" + ("Filler sentence. " * 1400)
        lint = run(art)
        self.assertTrue(any("行内公式" in m for _p, m in lint.warns))

    def test_a_clean_article_passes(self) -> None:
        art = article() + "\n\nThe value $C_D$ and $a_1$ and $p_a$ and $Re_x$ and $F_t$ hold.\n"
        lint = run(art)
        self.assertEqual(lint.errors, [])


if __name__ == "__main__":
    unittest.main()
