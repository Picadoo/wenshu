"""英文正文的章节层级必须真的恢复出来——「先英后中」新流程的验收关口。

双栏 PDF dump 里标题和正文粘在一行，确定性脚本恢复不出层级。2026-09-01 实测：
中文侧 Rettinger2022 有 38 个标题，英文侧同一篇只有 3 个（96 KB 正文）。
A1 英文重排必须把层级建出来，A2 中文翻译才有骨架可继承。
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

PROSE = "The superquadric equation is an effective method for describing particles. " * 8


def article(headings: int, body_chars: int, inline_titles: str = "") -> str:
    out = ["# Title", "", "## Abstract", "", "Abstract text.", ""]
    for i in range(1, headings + 1):
        out += ["## %d Section %d" % (i, i), "", PROSE, ""]
    if inline_titles:
        out += [inline_titles, ""]
    text = "\n".join(out)
    if len(text) < body_chars:
        text += "\n\n" + "Filler sentence about granular flow. " * ((body_chars - len(text)) // 37 + 1)
    return text


class HeadingRecoveryTests(unittest.TestCase):
    def test_orphan_section_numbers_are_error(self) -> None:
        """正文行里躺着编号章节名，说明层级没建出来。"""
        inline = ("equation 2.1 Description of the superquadric equation The superquadric "
                  "equation is used 3.2 Contact algorithm between particles A poly element "
                  "consists of eight 4.1 Results and discussion The mass flow rate shows")
        lint = LC.Lint()
        # 4 个章节标题：孤儿 2.1 / 3.2 / 4.1 各自都能在标题里找到同族编号，
        # 否则会被「举目无亲的编号多半是小数」那条判据当噪声滤掉
        LC.check_heading_recovery(lint, "pid", article(4, 5000, inline))
        self.assertEqual(len(lint.errors), 1)
        self.assertIn("章节层级没恢复", lint.errors[0][1])

    def test_decimals_in_prose_are_not_orphan_sections(self) -> None:
        """`0.25 Particle diameter` 这种正文小数不是漏掉的章节号，报了就是噪声。"""
        inline = ("the diameter 0.25 Particle diameter was used and voidage 0.02 Voidage "
                  "ratio while 1.00 Reference case gives 4.0 Terminal velocity results")
        lint = LC.Lint()
        LC.check_heading_recovery(lint, "pid", article(4, 5000, inline))
        self.assertEqual(lint.errors, [])

    def test_lone_number_without_siblings_is_not_an_orphan_section(self) -> None:
        """`67.1 Sediment concentration`：全文没有第 67 章，它只能是个小数。"""
        inline = ("concentration 67.1 Sediment concentration and slope 31.9 Channel slope "
                  "with depth 11.6 Flow depth measured")
        lint = LC.Lint()
        LC.check_heading_recovery(lint, "pid", article(4, 5000, inline))
        self.assertEqual(lint.errors, [])

    def test_numbers_already_used_as_headings_are_not_orphans(self) -> None:
        """同一个编号已经是真标题时，正文里再提到它不算孤儿。"""
        body = article(3, 5000)
        body += "\n\nAs described in 1 Section 1 the model is defined.\n"
        lint = LC.Lint()
        LC.check_heading_recovery(lint, "pid", body)
        self.assertEqual(lint.errors, [])

    def test_catastrophic_density_is_error(self) -> None:
        """Rettinger2022 型：96 KB 正文只有 3 个标题，孤儿检测抓不住，靠密度抓。"""
        lint = LC.Lint()
        LC.check_heading_recovery(lint, "pid", article(2, 60000))
        self.assertEqual(len(lint.errors), 1)
        self.assertIn("几乎没恢复", lint.errors[0][1])

    def test_moderate_density_is_warning(self) -> None:
        """35 KB / 5 个标题 = 7000 字符一个，落在警告带（6000~10000）。"""
        lint = LC.Lint()
        LC.check_heading_recovery(lint, "pid", article(4, 35000))
        self.assertEqual(lint.errors, [])
        self.assertEqual(len(lint.warns), 1)

    def test_well_structured_article_passes(self) -> None:
        lint = LC.Lint()
        LC.check_heading_recovery(lint, "pid", article(20, 40000))
        self.assertEqual(lint.errors, [])
        self.assertEqual(lint.warns, [])

    def test_short_article_is_not_judged_by_density(self) -> None:
        """短文（通讯、勘误）本来就没几个章节，不能拿密度苛求它。"""
        lint = LC.Lint()
        LC.check_heading_recovery(lint, "pid", article(1, 3000))
        self.assertEqual(lint.errors, [])
        self.assertEqual(lint.warns, [])


if __name__ == "__main__":
    unittest.main()
