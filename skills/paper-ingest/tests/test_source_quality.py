"""Checks that new ingestion cannot silently swap images or mutate reviewed math."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import extract
import mathcheck
import verify


class SourceQualityAcceptance(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[3] / "_work/skill-acceptance"
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="quality-", dir=root)
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        (self.work / "out").mkdir()
        (self.work / "images").mkdir()
        self.en = "# Flow\n\n## Abstract\n\nVelocity $u$ follows:\n\n$$u=\\frac{Q}{A}\\tag{1}$$\n\n![[Test_page1_fig1.png|700]]\n\n**Fig. 1.** Flow.\n\n![[Test_page1_fig2.png|700]]\n\n**Fig. 2.** Bed.\n"
        self.zh = self.en.replace("# Flow", "# 绕流").replace("Abstract", "摘要").replace("Velocity", "流速").replace("follows:", "如下：").replace("Fig.", "图").replace("Flow.", "绕流。").replace("Bed.", "河床。")
        self.layout = {"headings": [{"level": 2, "title": "Abstract", "page": 1}],
                       "figures": [{"num": 1, "page": 1, "caption": "Fig. 1. Flow."},
                                   {"num": 2, "page": 1, "caption": "Fig. 2. Bed."}],
                       "tables": [], "equations": [{"num": 1, "page": 1}]}
        layout = json.dumps(self.layout).encode()
        (self.work / "out/layout.json").write_bytes(layout)
        (self.work / "out/source-review.layout.json").write_bytes(layout)
        (self.work / "out/en.md").write_text(self.en, encoding="utf-8")
        (self.work / "out/source-review.en.md").write_bytes((self.work / "out/en.md").read_bytes())
        (self.work / "out/source-review.json").write_text(json.dumps({"equationsReviewed": True,
            "tablesReviewed": True, "structureReviewed": True, "sourceLanguage": "en",
            "notes": "Fixture review evidence."}), encoding="utf-8")
        pdf = self.work / "source.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=300, height=400)
        boxes = [[20, 20, 120, 100], [20, 140, 120, 220]]
        for n, box in enumerate(boxes, 1):
            page.draw_rect(pymupdf.Rect(box), color=(0, 0, 0))
        doc.save(pdf)
        entries = []
        for n, box in enumerate(boxes, 1):
            name = f"Test_page1_fig{n}.png"
            page.get_pixmap(clip=pymupdf.Rect(box), matrix=pymupdf.Matrix(2.2, 2.2)).save(self.work / "images" / name)
            entries.append({"num": str(n), "page": 1, "sourcePage": 1, "bbox": box, "file": name,
                            "status": "manual", "reviewed": True, "reviewNote": "All panels verified.",
                            "reviewedAt": "2026-10-03T00:00:00+00:00"})
        doc.close()
        (self.work / "meta.json").write_text(json.dumps({"key": "Test", "lang": "en", "pdf": str(pdf),
           "qualityPolicy": "source-reviewed-v1"}), encoding="utf-8")
        (self.work / "stats.json").write_text('{"pages":1}', encoding="utf-8")
        (self.work / "figcut.json").write_text(json.dumps({"figures": entries}), encoding="utf-8")

    def check(self, en=None, zh=None):
        errors, counts = [], {}
        verify.check_source_quality(self.work, en or self.en, zh or self.zh, {1, 2}, "en", errors, counts)
        return errors

    def test_reviewed_source_and_images_pass(self):
        self.assertEqual(self.check(), [])

    def test_editorial_without_abstract_keeps_other_document_frontmatter_requirements(self):
        (self.work / "out/en.md").write_text(self.en.replace("## Abstract", "## Editorial"), encoding="utf-8")
        (self.work / "out/zh.md").write_text(self.zh.replace("## 摘要", "## 导言"), encoding="utf-8")
        meta_path = self.work / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        for document_type, expected_front in (("editorial", None), ("article", "Abstract"), ("book", "Preface")):
            with self.subTest(document_type=document_type):
                meta["documentType"] = document_type
                meta_path.write_text(json.dumps(meta), encoding="utf-8")
                errors = verify.verify(self.work)["errors"]
                if expected_front:
                    self.assertTrue(any(f"## {expected_front}" in e for e in errors))
                else:
                    self.assertFalse(any("缺 `## Abstract`" in e or "缺 `## 摘要`" in e for e in errors))

    def test_same_count_swapped_images_are_rejected(self):
        swapped = self.zh.replace("fig1", "TEMP").replace("fig2", "fig1").replace("TEMP", "fig2")
        self.assertTrue(any("已核对文件" in e for e in self.check(zh=swapped)))

    def test_formula_changed_with_identical_number_is_rejected(self):
        self.assertTrue(self.check(zh=self.zh.replace("Q}{A}", "Q}{A^2}")))

    def test_edit_after_review_invalidates_seal(self):
        (self.work / "out/en.md").write_text(self.en + "Changed source.\n", encoding="utf-8")
        self.assertTrue(self.check())

    def test_unreviewed_or_out_of_page_crop_is_rejected(self):
        report = json.loads((self.work / "figcut.json").read_text(encoding="utf-8"))
        report["figures"][0]["reviewed"] = False
        report["figures"][1]["bbox"] = [20, 140, 500, 220]
        (self.work / "figcut.json").write_text(json.dumps(report), encoding="utf-8")
        self.assertGreaterEqual(len(self.check()), 2)

    def test_source_prompt_routes_luna_to_separate_translation(self):
        extract.write_brief(self.work, {"key": "Test", "lang": "en"}, [], {"pages": 1}, "# Flow")
        brief = (self.work / "brief.md").read_text(encoding="utf-8")
        self.assertIn("源稿核准任务", brief)
        self.assertIn("review-source", brief)
        self.assertTrue((self.work / "analysis-brief.md").is_file())

    def test_bundled_reader_accepts_valid_and_rejects_invalid_latex(self):
        self.assertEqual(mathcheck.check_renderable(self.en), [])
        errors = mathcheck.check_renderable("$$\\unknownEquationCommand{x}\\tag{1}$$")
        self.assertTrue(any("不能渲染" in e for e in errors))

    def test_unclosed_math_cannot_be_sealed_as_reviewed(self):
        for text in ("The velocity $u is high.", "$$u=Q/A", "$$u=Q/A$"):
            with self.subTest(text=text):
                self.assertTrue(mathcheck.check_renderable(text))

    def test_chapter_numbers_do_not_collapse_and_missing_items_are_detected(self):
        text = "Fig. 1.1. First chart.\nFig. 2.1. Second chart.\nFig. B.1. Appendix chart.\nTable 4.1. Values.\nTable 4.3. More values.\n"
        expected = verify.expected_from_pdf(text, "", {"columns": {"hintFigures": [1, 2], "hintTables": [4]}})
        self.assertEqual(expected["figures"], {"1.1", "2.1", "B.1"})
        self.assertEqual(expected["tables"], {"4.1", "4.3"})
        self.assertEqual(verify.consecutive(expected["tables"])[1], ["4.2"])
        errors = []
        have, embedded = verify.check_captions("![[one.png]]\n\n**Fig. 1.1.** First.", verify.EN_CAP,
                                              expected["figures"], "Fig.", errors, "en.md")
        self.assertEqual(have, {"1.1"})
        self.assertEqual(embedded, {"1.1"})
        self.assertEqual(len(errors), 2)
        self.assertEqual(verify.ZH_CAP.match("**图4.5。** 湍流。").group(1), "4.5")
        self.assertEqual(verify.ZH_TAB.match("**表B.1。** 系数。").group(1), "B.1")

    def test_primed_equation_is_preserved_as_additional_original_label(self):
        labels = {"4.25", "4.26", "4.26′", "4.27"}
        self.assertEqual(verify.consecutive(labels), (labels, []))
        self.assertEqual(verify.equation_id("4.26′"), "4.26′")
        self.assertEqual(verify.TAG.search(r"\tag{4.26′}").group(1), "4.26′")
        self.assertEqual(verify.consecutive({"4.25", "4.27", "4.27′"})[1], ["4.26"])


if __name__ == "__main__":
    unittest.main()
