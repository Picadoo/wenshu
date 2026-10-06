from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "normalize_references.py"
SPEC = importlib.util.spec_from_file_location("normalize_references", SCRIPT)
assert SPEC and SPEC.loader
NR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NR)

RUN_ON = (
    "# T\n\n## 6. Conclusion\n\nWe conclude.\n\n"
    "## Data Availability Statement\n\nAvailable in the repository.[82] "
    "O RC I D NikolaosN.Vlassis WaiChingSun Khalid A.Alshibli "
    "R E F E R E N C E S 1. Beiser V. Why the world is running out of sand. BBC Future. 2019:18. "
    "2. Nova R, Wood DM. A constitutive model for sand. Int J. 1979;3(3):255-278. "
    "3. Mitchell JK, Soga K. Fundamentals of Soil Behavior. Wiley; 2005. "
    "4. Jefferies M. Nor-Sand: a critical state model. Geotechnique. 1993;43(1):91-103. "
    "5. Dafalias YF. Simple plasticity sand model. J Eng Mech. 2004;130(6):622-634. "
    "6. Wieghardt K. Experiments in granular flow. Annu Rev. 1975;7(1):89-114.\n\n"
    "How to cite this article: Vlassis NN. Synthesizing sand. Int J. 2024;48:3933.\n")


class SplitTests(unittest.TestCase):
    def test_run_on_text_becomes_a_section(self) -> None:
        got, action, n = NR.normalize(RUN_ON)
        self.assertEqual(action, "已拆条")
        self.assertEqual(n, 6)
        self.assertIn("## References\n\n1. Beiser V.", got)
        self.assertIn("\n2. Nova R, Wood DM.", got)

    def test_orcid_block_is_stripped(self) -> None:
        got, _a, _n = NR.normalize(RUN_ON)
        self.assertNotIn("NikolaosN.Vlassis WaiChingSun", got)

    def test_how_to_cite_is_kept_as_a_quote(self) -> None:
        got, _a, _n = NR.normalize(RUN_ON)
        self.assertIn("> How to cite this article:", got)

    def test_existing_section_is_left_alone(self) -> None:
        art = "# T\n\n## References\n\n1. Someone A. A paper. 2020.\n"
        got, action, _n = NR.normalize(art)
        self.assertEqual(action, "已是标题节")
        self.assertEqual(got, art)

    def test_reference_velocity_is_not_a_label(self) -> None:
        """宽松地搜 `References` 会命中 `Reference velocity` 这类正文词组。"""
        art = "# T\n\nThe reference velocity is defined below. References to prior work follow.\n"
        _got, action, _n = NR.normalize(art)
        self.assertNotEqual(action, "已拆条")

    def test_too_few_entries_are_left_to_a1(self) -> None:
        """宁可不改，也不要把正文切碎。"""
        art = ("# T\n\nR E F E R E N C E S 1. Only A. One entry. 2020. "
               "2. Only B. Two entries. 2021.\n")
        _got, action, _n = NR.normalize(art)
        self.assertEqual(action, "切不出条目（派 A1）")

    def test_missing_list_is_taken_from_the_source_dump(self) -> None:
        """65 篇的文献表被 prep_article_en 按旧规矩整段截掉了，得从原文取回。"""
        art = "# T\n\n## 6. Conclusion\n\nWe conclude.\n"
        src = "Body text.\n\nReferences\n\n" + "\n".join(
            "%d. Author %d. A paper title here. Journal Name. 20%02d;%d:1-10."
            % (i, i, i, i) for i in range(1, 9))
        got, action, n = NR.normalize(art, src)
        self.assertEqual(action, "从原文补")
        self.assertGreaterEqual(n, 5)
        self.assertIn("## References", got)

    def test_nothing_is_invented_when_the_source_has_none(self) -> None:
        got, action, _n = NR.normalize("# T\n\n## 6. Conclusion\n\nDone.\n", "No list here.")
        self.assertEqual(action, "原文也解析不出（派 A1）")
        self.assertNotIn("## References", got)


if __name__ == "__main__":
    unittest.main()
