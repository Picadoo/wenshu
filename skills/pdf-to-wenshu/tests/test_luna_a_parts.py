from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "luna_a_parts.py"
SPEC = importlib.util.spec_from_file_location("luna_a_parts", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class LunaAPartsTests(unittest.TestCase):
    def test_balances_only_at_numbered_heading_boundaries(self) -> None:
        lines = ["Title", "Abstract", "1. Intro", "a" * 30, "2. Method", "b" * 50,
                 "2.1. Detail", "c" * 40, "3. Results", "d" * 35, "References", "ref"]
        parts = MODULE.balanced_ranges(lines, 3)
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[-1][1], 10)
        self.assertTrue(all(start < stop for start, stop, _ in parts))

    def test_prepare_writes_resolved_briefs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.txt"
            source.write_text("Title\n1. Intro\nText\n2. Method\nText\n3. End\nText\nReferences\nR\n", encoding="utf-8")
            target = root / "article.md"
            target.write_text("<!--ARTICLE-->\nwait\n<!--/ARTICLE-->\n", encoding="utf-8")
            job = {
                "paperId": "P1", "cleanFulltextPath": str(source), "imageIndexPath": "img.md",
                "tableIndexPath": "tab.md", "pdfPath": "p.pdf", "notes": {"article": str(target)},
                "figures": [], "tableCoverage": {"total": 0},
            }
            job_path = root / "job.json"
            job_path.write_text(json.dumps(job), encoding="utf-8")
            manifest = MODULE.prepare(job_path, root / "parts", 2)
            self.assertEqual(len(manifest["parts"]), 2)
            brief = Path(manifest["parts"][0]["briefPath"]).read_text(encoding="utf-8")
            self.assertNotIn("{{", brief)
            self.assertIn("第 `1 / 2`", brief)

    def test_prepare_falls_back_to_generated_indexes_for_quality_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.txt"
            source.write_text("Title\n1. Intro\nText\nReferences\nR\n", encoding="utf-8")
            target = root / "article.md"
            target.write_text("<!--ARTICLE-->\nwait\n<!--/ARTICLE-->\n", encoding="utf-8")
            images = root / "images.md"
            images.write_text("# 图片索引\n\n- 文件名：f1.png\n- 文件名：f2.png\n", encoding="utf-8")
            tables = root / "tables.md"
            tables.write_text("# 表格索引\n\n总计：3 张表格\n", encoding="utf-8")
            job = {
                "paperId": "P1", "cleanFulltextPath": str(source),
                "imageIndexPath": str(images), "tableIndexPath": str(tables),
                "pdfPath": "p.pdf", "notes": {"article": str(target)},
            }
            job_path = root / "job.json"
            job_path.write_text(json.dumps(job), encoding="utf-8")
            manifest = MODULE.prepare(job_path, root / "parts", 1)
            self.assertEqual(manifest["expectedImages"], ["f1.png", "f2.png"])
            self.assertEqual(manifest["expectedTables"], 3)

    def test_merge_checks_and_writes_article_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "article.md"
            target.write_text("front\n<!--ARTICLE-->\nwait\n<!--/ARTICLE-->\ntail\n", encoding="utf-8")
            first = root / "part-01.zh.md"
            second = root / "part-02.zh.md"
            first.write_text("# 标题\n\n## 亮点\n\n- x\n\n## 摘要\n\n正文\n\n![[f.png|700]]\n\n**图 1：** caption\n", encoding="utf-8")
            second.write_text("## 1 结论\n\n| A |\n|---|\n| 1 |\n", encoding="utf-8")
            manifest = {
                "targetPath": str(target), "expectedImages": ["f.png"], "expectedTables": 1,
                "parts": [{"outputPath": str(first)}, {"outputPath": str(second)}],
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = MODULE.merge(manifest_path)
            merged = target.read_text(encoding="utf-8")
            self.assertEqual(result["parts"], 2)
            self.assertIn("# 标题", merged)
            self.assertNotIn("wait", merged)

    def test_merge_dedupes_two_column_boundary_assets_and_normalizes_headings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "article.md"
            target.write_text("<!--ARTICLE-->\nwait\n<!--/ARTICLE-->\n", encoding="utf-8")
            first = root / "part-01.zh.md"
            second = root / "part-02.zh.md"
            first.write_text(
                "# 标题\n\n## 亮点\n\n- x\n\n## 摘要\n\n正文\n\n"
                "![[f.png|700]]\n\n**图 1：** first\n\n"
                "**表 1：** first\n\n| A |\n|---|\n| 1 |\n",
                encoding="utf-8",
            )
            second.write_text(
                "### 2 方法\n\n![[f.png|700]]\n\n**图 1：** duplicate\n\n"
                "**表 1：** duplicate\n\n| A |\n|---|\n| 1 |\n",
                encoding="utf-8",
            )
            manifest = {
                "targetPath": str(target), "expectedImages": ["f.png"], "expectedTables": 1,
                "parts": [{"outputPath": str(first)}, {"outputPath": str(second)}],
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = MODULE.merge(manifest_path)
            merged = target.read_text(encoding="utf-8")
            self.assertEqual(result["dedupedImages"], ["f.png"])
            self.assertEqual(result["dedupedTables"], ["1"])
            self.assertEqual(merged.count("![[f.png|700]]"), 1)
            self.assertEqual(merged.count("**表 1：**"), 1)
            self.assertIn("## 2 方法", merged)


if __name__ == "__main__":
    unittest.main()
