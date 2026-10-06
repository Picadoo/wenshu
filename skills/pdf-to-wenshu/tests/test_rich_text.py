from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "extract_rich_text.py"
SPEC = importlib.util.spec_from_file_location("extract_rich_text", SCRIPT)
assert SPEC and SPEC.loader
RT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RT)


def span(text: str, size: float, y: float) -> dict:
    return {"text": text, "size": size, "origin": (0.0, y)}


class RenderLineTests(unittest.TestCase):
    """PDF 的上下标靠「字号更小 + 基线偏移」识别，与语言无关。"""

    def test_subscript_becomes_latex(self) -> None:
        line = [span("C", 10.9, 607.2), span("D", 8.0, 609.3), span(" = 1", 10.9, 607.2)]
        self.assertEqual(RT.render_line(line, 10.9), "C_{D} = 1")

    def test_superscript_becomes_latex(self) -> None:
        line = [span("log", 10.9, 607.2), span("2", 8.0, 601.1), span("(Re)", 10.9, 607.2)]
        self.assertEqual(RT.render_line(line, 10.9), "log^{2}(Re)")

    def test_adjacent_subscript_spans_merge_into_one_group(self) -> None:
        """`ap1` 是 a + 8pt 的 p + 6pt 的 1 三个 span，必须拼成 a_{p1} 而不是 a_{p}_{1}。"""
        line = [span("a", 10.9, 406.6), span("p", 8.0, 406.6 + 1.0),
                span("1", 6.0, 406.6 + 1.1), span(" term", 10.9, 406.6)]
        self.assertEqual(RT.render_line(line, 10.9), "a_{p1} term")

    def test_greek_in_script_is_converted_to_a_command(self) -> None:
        line = [span("v", 10.9, 244.0), span("∞", 8.0, 245.1), span(" is", 10.9, 244.0)]
        self.assertEqual(RT.render_line(line, 10.9), r"v_{\infty} is")

    def test_uniform_line_is_left_untouched(self) -> None:
        line = [span("plain prose without any math", 10.9, 100.0)]
        self.assertEqual(RT.render_line(line, 10.9), "plain prose without any math")

    def test_small_but_baseline_aligned_text_is_not_a_script(self) -> None:
        """整段小字（脚注、版权行）字号虽小但基线不偏，不能被包成下标。"""
        line = [span("Body text", 10.9, 100.0), span("note", 8.0, 100.0)]
        self.assertEqual(RT.render_line(line, 10.9), "Body textnote")

    def test_long_small_span_is_not_a_script(self) -> None:
        """真下标都很短；长的小字多半是整段脚注，包起来会毁掉正文。"""
        line = [span("Text", 10.9, 100.0),
                span("a whole sentence set in small type", 8.0, 101.5)]
        got = RT.render_line(line, 10.9)
        self.assertNotIn("_{", got)

    def test_body_size_is_taken_per_document(self) -> None:
        """正文字号各篇不同（实测 8.0/8.1/9.0/10.0/10.9），阈值必须按篇自取。"""
        line = [span("C", 8.0, 200.0), span("D", 6.0, 201.5)]
        self.assertEqual(RT.render_line(line, 8.0), "C_{D}")

    def test_count_scripts(self) -> None:
        self.assertEqual(RT.count_scripts("C_{D} and a^{2} and plain"), 2)


if __name__ == "__main__":
    unittest.main()
