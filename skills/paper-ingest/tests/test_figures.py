"""Scoped checks for crop provenance, explicit review and exact figure mapping."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf
from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import cutfigs
import figtools


class FigureAcceptance(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[3] / "_work" / "skill-figures"
        root.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(prefix="case-", dir=root)
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name).resolve()
        self.assertTrue(self.work.is_relative_to(root.resolve()))
        (self.work / "out").mkdir()
        (self.work / "images").mkdir()
        self.pdf = self.work / "fixture.pdf"
        self.make_pdf()
        self.write_json("meta.json", {"key": "Fixture2026", "pdf": str(self.pdf)})
        self.set_layout([("1", 1), ("2", 2)])

    def make_pdf(self, cross_page=False):
        with pymupdf.open() as doc:
            for index in range(2):
                page = doc.new_page(width=400, height=500)
                if not cross_page or index == 0:
                    color = (0, 0, 1) if index == 0 else (0, 0.6, 0)
                    page.draw_rect(pymupdf.Rect(50, 60, 330, 280), color=color, width=2)
                    page.draw_line((70, 250), (310, 90), color=color, width=2)
                    page.insert_text((150, 270), "x axis / all panels")
                    page.insert_text((55, 100), "y axis")
                if cross_page and index == 1:
                    page.insert_text((50, 40), "Fig. 1. A complete test chart.")
                elif not cross_page:
                    page.insert_text((50, 320), f"Fig. {index + 1}. A complete test chart.")
            doc.save(self.pdf)

    def write_json(self, name, data):
        (self.work / name).write_text(json.dumps(data), encoding="utf-8")

    def set_layout(self, figures):
        self.write_json("out/layout.json", {"figures": [
            {"num": num, "page": page, "caption": f"Fig. {num}. A complete test chart."}
            for num, page in figures]})

    def manual(self, num="1", page=1, box="40,50,340,290", unit="pt", dpi=100):
        return figtools.crop(self.work, page, num, box, unit, False, dpi)

    def entry(self, num="1"):
        return next(f for f in figtools.load_report(self.work)["figures"] if f["num"] == num)

    def test_manual_crop_records_exact_geometry_without_review(self):
        target = self.manual()
        entry = self.entry()
        self.assertEqual(entry["status"], "manual")
        self.assertEqual(entry["sourcePage"], 1)
        self.assertEqual(entry["bbox"], [40, 50, 340, 290])
        self.assertEqual(entry["file"], target.name)
        self.assertFalse(entry["reviewed"])
        self.assertEqual(figtools.geometry_errors(self.work, entry), [])
        self.assertTrue((self.work / "images" / entry["comparisonFile"]).is_file())
        self.assertTrue((self.work / "images" / "_sheet.png").is_file())

    def test_pixel_box_is_recorded_in_pdf_points(self):
        self.manual(box="40,50,340,290", unit="px", dpi=72)
        self.assertEqual(self.entry()["bbox"], [40, 50, 340, 290])

    def test_pixel_box_uses_extraction_dpi_unless_explicitly_overridden(self):
        self.write_json("stats.json", {"renderDpi": 144})
        figtools.crop(self.work, 1, "1", "80,100,680,580", "px", False)
        self.assertEqual(self.entry()["bbox"], [40, 50, 340, 290])
        self.manual(box="80,100,680,580", unit="px", dpi=144)
        self.assertEqual(self.entry()["bbox"], [40, 50, 340, 290])

    def test_invalid_boxes_do_not_write_or_silently_clip(self):
        for box in ("-1,50,340,290", "40,50,401,290", "40,50,340,501", "40,50,40,290",
                    "340,50,40,290", "40,290,340,50", "nan,50,340,290", "40,50,inf,290",
                    "40,50,340", "bad,50,340,290"):
            with self.subTest(box=box), self.assertRaises(ValueError):
                self.manual(box=box)
        self.assertFalse((self.work / "figcut.json").exists())
        self.assertEqual(list((self.work / "images").iterdir()), [])

    def test_invalid_page_and_dpi_are_rejected(self):
        for page in (0, -1, 3):
            with self.subTest(page=page), self.assertRaises(ValueError):
                self.manual(page=page)
        with self.assertRaises(ValueError):
            self.manual(unit="px", dpi=0)

    def test_review_requires_note_and_valid_source(self):
        self.manual()
        with self.assertRaises(ValueError):
            figtools.review(self.work, "1", " ")
        reviewed = figtools.review(self.work, "1", "Checked original page, axes, legend and all panels.")
        self.assertTrue(reviewed["reviewed"])
        self.assertTrue(reviewed["reviewedAt"])
        self.assertTrue(reviewed["reviewNote"])
        (self.work / "images" / reviewed["file"]).unlink()
        with self.assertRaises(ValueError):
            figtools.review(self.work, "1", "Checked source.")

    def test_each_manual_recrop_clears_old_review_even_for_same_box(self):
        self.manual()
        figtools.review(self.work, "1", "Checked source.")
        self.manual()
        self.assertFalse(self.entry()["reviewed"])
        self.assertNotIn("reviewNote", self.entry())
        self.assertNotIn("reviewedAt", self.entry())
        figtools.review(self.work, "1", "Checked source again.")
        self.manual(box="30,40,350,300")
        self.assertFalse(self.entry()["reviewed"])
        self.assertEqual(self.entry()["bbox"], [30, 40, 350, 300])

    def test_keep_manual_crop_preserves_bbox_file_and_review(self):
        self.set_layout([("1", 1)])
        self.manual()
        figtools.review(self.work, "1", "All source panels included.")
        before = self.entry()
        with patch.object(cutfigs, "find_caption", side_effect=AssertionError("kept crop must not need a text caption")):
            result = cutfigs.cut(self.work, 2.2, False)
        after = result["figures"][0]
        for field in ("bbox", "sourcePage", "file", "status", "reviewed", "reviewNote", "reviewedAt", "comparisonFile"):
            self.assertEqual(after[field], before[field])

    def test_automatic_candidate_kept_metadata_and_force_invalidates_review(self):
        self.set_layout([("1", 1)])
        initial = cutfigs.cut(self.work, 2.2, False)["figures"][0]
        self.assertEqual(initial["status"], "ok")
        self.assertFalse(initial["reviewed"])
        self.assertEqual(initial["sourcePage"], 1)
        figtools.review(self.work, "1", "Checked entire original chart.")
        kept = cutfigs.cut(self.work, 2.2, False)["figures"][0]
        self.assertEqual(kept["status"], "kept")
        self.assertEqual(kept["bbox"], initial["bbox"])
        self.assertTrue(kept["reviewed"])
        forced = cutfigs.cut(self.work, 2.2, True)["figures"][0]
        self.assertFalse(forced["reviewed"])
        self.assertNotIn("reviewNote", forced)
        self.assertNotIn("reviewedAt", forced)

    def test_cross_page_caption_uses_actual_source_page_and_file(self):
        self.make_pdf(cross_page=True)
        self.set_layout([("1", 2)])
        result = cutfigs.cut(self.work, 2.2, False)
        entry = result["figures"][0]
        self.assertEqual(entry["status"], "carry")
        self.assertEqual(entry["page"], 2)
        self.assertEqual(entry["sourcePage"], 1)
        self.assertEqual(entry["file"], "Fixture2026_page1_fig1.png")
        self.manual()
        self.assertEqual(self.entry()["page"], 2)
        self.assertEqual(self.entry()["sourcePage"], 1)

    def test_embed_corrects_exact_files_once_and_preserves_prose(self):
        self.manual()
        self.manual(num="2", page=2)
        for name, captions in (("en.md", ("Fig. 1.", "Fig. 2.")), ("zh.md", ("图 1.", "图 2."))):
            (self.work / "out" / name).write_text(
                f"Unrelated prose.\n\n![[wrong1.png|700]]\n\n**{captions[0]}** One.\n\n"
                f"![[wrong2.png|700]]\n\n**{captions[1]}** Two.\n", encoding="utf-8")
        report = figtools.load_report(self.work)
        self.assertEqual(cutfigs.embed(self.work, report), {"en.md": 2, "zh.md": 2})
        for name in ("en.md", "zh.md"):
            text = (self.work / "out" / name).read_text(encoding="utf-8")
            self.assertEqual(text.count("![["), 2)
            self.assertIn("Fixture2026_page1_fig1.png", text)
            self.assertIn("Fixture2026_page2_fig2.png", text)
            self.assertIn("Unrelated prose.", text)
        self.assertEqual(cutfigs.embed(self.work, report), {"en.md": 0, "zh.md": 0})

    def test_compare_selects_exact_figure_and_keeps_review_pending(self):
        self.manual()
        self.manual(num="2", page=2)
        paths = figtools.compare(self.work, ["2"])
        self.assertEqual([p.name for p in paths], ["_review_fig2.png"])
        self.assertFalse(self.entry("2")["reviewed"])
        with Image.open(paths[0]) as image:
            self.assertGreater(image.width, 1000)  # Original page and readable crop are side by side.
            self.assertGreater(image.height, 600)
        with self.assertRaises(ValueError):
            figtools.compare(self.work, ["3"])

    def test_shared_review_gate_requires_each_record_and_opens_pdf_once(self):
        self.manual()
        self.manual(num="2", page=2)
        self.assertTrue(any("reviewed" in error for error in figtools.review_errors(self.work)))
        for num in ("1", "2"):
            figtools.review(self.work, num, "Original page checked.")
        with patch.object(figtools.pymupdf, "open", wraps=pymupdf.open) as opened:
            self.assertEqual(figtools.review_errors(self.work), [])
            self.assertEqual(opened.call_count, 1)
        report = figtools.load_report(self.work)
        report["figures"][1]["bbox"] = [40, 50, 401, 290]
        figtools.save_report(self.work, report)
        self.assertTrue(any("越界" in error for error in figtools.review_errors(self.work)))

    def test_duplicate_records_and_missing_or_unknown_geometry_are_rejected(self):
        self.set_layout([("1", 1)])
        self.manual()
        report = figtools.load_report(self.work)
        record = dict(report["figures"][0])
        report["figures"].append(record)
        self.write_json("figcut.json", report)
        self.assertTrue(any("重复图号" in error for error in figtools.review_errors(self.work)))
        self.write_json("figcut.json", {"figures": []})
        self.assertTrue(any("缺少 figcut" in error for error in figtools.review_errors(self.work)))
        # An image without a source record remains intact; never guess its bbox.
        kept = cutfigs.cut(self.work, 2.2, False)["figures"][0]
        self.assertEqual(kept["status"], "kept")
        self.assertNotIn("bbox", kept)
        self.assertNotIn("sourcePage", kept)
        self.assertFalse(kept["reviewed"])

    def test_paper_without_figures_needs_no_figcut(self):
        self.set_layout([])
        self.assertEqual(figtools.review_errors(self.work), [])

    def test_chapter_and_appendix_figures_keep_distinct_images(self):
        for num in ("1.1", "2.1", "B.1"):
            self.assertEqual(figtools.figure_num(num), num)
        source = "# Book\n\n**Fig. 1.1.** First.\n\n**Fig. 2.1.** Second.\n\n**Fig. B.1.** Appendix.\n"
        (self.work / "out/en.md").write_text(source, encoding="utf-8")
        result = {"figures": [{"num": n, "file": f"chapter-{n}.png"} for n in ("1.1", "2.1", "B.1")]}
        self.assertEqual(cutfigs.embed(self.work, result)["en.md"], 3)
        text = (self.work / "out/en.md").read_text(encoding="utf-8")
        self.assertIn("![[chapter-1.1.png|700]]\n\n**Fig. 1.1.**", text)
        self.assertIn("![[chapter-2.1.png|700]]\n\n**Fig. 2.1.**", text)
        self.assertIn("![[chapter-B.1.png|700]]\n\n**Fig. B.1.**", text)


if __name__ == "__main__":
    unittest.main()
