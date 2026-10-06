from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ingest_finish.py"
SPEC = importlib.util.spec_from_file_location("ingest_finish", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class StrictPreflightTests(unittest.TestCase):
    def make_job(self, root: Path) -> dict:
        files = {
            "index": root / "paper.md",
            "article": root / "paper.正文.md",
            "articleEn": root / "paper.正文.en.md",
            "notes": root / "paper.notes.md",
        }
        files["index"].write_text("---\nstatus: analyzed\n---\n" + "索引" * 120, encoding="utf-8")
        files["article"].write_text("# 中文正文\n\n" + "正文" * 120, encoding="utf-8")
        files["articleEn"].write_text("# English article\n\n" + "content " * 80, encoding="utf-8")
        files["notes"].write_text("# 学习笔记\n\n" + "分析" * 120, encoding="utf-8")
        terms = root / "paper.terms.json"
        terms.write_text(json.dumps([{"term": "DEM"}]), encoding="utf-8")
        return {
            "lang": "en",
            "termsJson": str(terms),
            "notes": {key: str(value) for key, value in files.items()},
        }

    def test_complete_job_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = self.make_job(Path(tmp))
            self.assertEqual(MODULE.strict_preflight(job), [])

    def test_missing_terms_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = self.make_job(Path(tmp))
            Path(job["termsJson"]).unlink()
            self.assertIn("缺少 terms.json", MODULE.strict_preflight(job))

    def test_placeholder_index_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = self.make_job(Path(tmp))
            index = Path(job["notes"]["index"])
            index.write_text("status: skeleton\n" + "待分析子代理填充" * 30, encoding="utf-8")
            issues = MODULE.strict_preflight(job)
            self.assertTrue(any("status: skeleton" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
