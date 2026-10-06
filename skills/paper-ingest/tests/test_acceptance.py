"""Scoped regression checks for reference fidelity and publication failure handling."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import finish
import verify

SOURCE = """Introduction
References
1. Alpha, A. Particle transport. Journal 10, 12–20 (2020).
2. Beta, B. Flow separation. Journal 11, 21–30 (2021).
3. Alpha, A. Particle transport. Journal 10, 12–20 (2020).
Acknowledgements
This work was funded by Example Foundation.
"""
ENTRIES = [
    "Alpha, A. Particle transport. Journal 10, 12–20 (2020).",
    "Beta, B. Flow separation. Journal 11, 21–30 (2021).",
    "Alpha, A. Particle transport. Journal 10, 12–20 (2020).",
]
REFS = "\n".join(f"- **[{i}]** {text} ^ref-{i}" for i, text in enumerate(ENTRIES, 1)) + "\n"


class ReferenceAcceptance(unittest.TestCase):
    def check(self, text):
        errors, warnings, counts = [], [], {}
        verify.check_references(text, SOURCE, errors, warnings, counts)
        return errors, warnings, counts

    def test_complete_source_duplicates_remain_distinct(self):
        errors, warnings, counts = self.check(REFS)
        self.assertEqual((errors, warnings), ([], []))
        self.assertEqual(counts["references"]["entries"], 3)

    def test_missing_first_or_last_entry_is_rejected(self):
        for lines in [REFS.splitlines()[1:], REFS.splitlines()[:-1]]:
            with self.subTest(lines=lines):
                self.assertTrue(self.check("\n".join(lines))[0])

    def test_same_count_with_wrong_reference_identity_is_rejected(self):
        text = REFS.replace(ENTRIES[1], ENTRIES[0])
        self.assertTrue(self.check(text)[0])

    def test_duplicate_or_wrong_anchor_is_rejected(self):
        for text in [REFS.replace("^ref-2", "^ref-1"), REFS.replace("^ref-2", "^ref-9")]:
            with self.subTest(text=text):
                self.assertTrue(self.check(text)[0])

    def test_publisher_backmatter_is_rejected(self):
        self.assertTrue(self.check(REFS + "Author contributions: draft and review.")[0])


class FinishAcceptance(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[3] / "_work" / "skill-acceptance"
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="case-", dir=root)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        assert self.base.is_relative_to(root.resolve())
        self.work, self.vault, self.web = [self.base / name for name in ("work", "vault", "web")]
        out = self.work / "out"
        out.mkdir(parents=True)
        pdf = self.work / "fixture.pdf"
        pdf.write_bytes(b"fixture: content validation is mocked in finish boundary tests")
        meta = {"key": "Test2026", "lang": "en", "title": "Transport acceptance",
                "authors": ["A Tester"], "year": "2026", "pdf": str(pdf), "doi": "10.1234/fixture"}
        (self.work / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        (self.work / "refs.md").write_text(REFS, encoding="utf-8")
        (self.work / "fulltext.txt").write_text(SOURCE, encoding="utf-8")
        fields = {"shortTitle": "验收", "domain": "测试/输沙", "translatedTitle": "输沙验收"}
        (out / "fields.json").write_text(json.dumps(fields), encoding="utf-8")
        for name in ("en", "zh", "notes"):
            (out / f"{name}.md").write_text(f"# {name}\n\nVerified fixture body.\n", encoding="utf-8")
        (out / "terms.json").write_text("[]", encoding="utf-8")
        self.index = self.vault / "Papers/测试/输沙/Test2026 验收.md"

    def invoke(self, responses, extra=()):
        argv = ["finish.py", "--work", str(self.work), "--vault", str(self.vault), "--wenshu", str(self.web), *extra]
        checked = {"ok": True, "errors": [], "warnings": [], "counts": {}}
        # No file hashes, external tools, services or live vault writes in these boundary tests.
        with patch.object(sys, "argv", argv), patch.object(finish, "utf8"), \
             patch.object(verify, "verify", return_value=checked) as gate, \
             patch.object(finish, "run", side_effect=responses) as commands, \
             patch.object(finish.hashlib, "sha256", return_value=Mock(hexdigest=lambda: "fixture")), \
             contextlib.redirect_stdout(io.StringIO()):
            code = 0
            try:
                finish.main()
            except SystemExit as exc:
                code = exc.code
        return code, gate.call_count, commands.call_count

    def summary(self):
        return json.loads((self.vault / "90_系统/_ingest/Test2026 验收.lite.json").read_text(encoding="utf-8"))["summary"]

    def test_ready_has_identical_reference_tables_in_both_languages(self):
        self.assertEqual(self.invoke([(0, "lint ok"), (0, "sync ok")]), (0, 1, 2))
        summary = self.summary()
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["refs"], 3)
        self.assertTrue(summary["readingPath"].endswith(summary["citekey"]))
        content = Path(summary["folder"]) / "content"
        en = (content / "Test2026 验收.正文.en.md").read_text(encoding="utf-8")
        zh = (content / "Test2026 验收.正文.md").read_text(encoding="utf-8")
        self.assertIn("## References", en)
        self.assertIn("## 参考文献", zh)
        self.assertIn(REFS.strip(), en)
        self.assertIn(REFS.strip(), zh)

    def test_failed_lint_never_syncs_or_reports_ready(self):
        self.assertEqual(self.invoke([(7, "lint failed")]), (1, 1, 1))
        self.assertEqual(self.summary()["status"], "failed")
        self.assertNotIn("sync", self.summary())

    def test_book_reading_link_is_distinct_from_same_author_year_title_word_article(self):
        meta_path = self.work / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["documentType"] = "book"
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        self.assertEqual(self.invoke([(0, "lint ok"), (0, "sync ok")]), (0, 1, 2))
        self.assertEqual(self.summary()["citekey"], "tester2026booktransport")
        self.assertTrue(self.summary()["readingPath"].endswith("tester2026booktransport"))
        self.assertIn('citekey: "tester2026booktransport"', self.index.read_text(encoding="utf-8"))

    def test_source_checked_metadata_overrides_nonempty_extraction(self):
        p = self.work / "out/fields.json"
        fields = json.loads(p.read_text(encoding="utf-8"))
        fields.update(authors=["Corrected Author"], journal="Correct Journal", doi="10.1234/corrected")
        p.write_text(json.dumps(fields), encoding="utf-8")
        self.assertEqual(self.invoke([(0, "lint ok"), (0, "sync ok")]), (0, 1, 2))
        index = self.index.read_text(encoding="utf-8")
        self.assertIn('"Corrected Author"', index)
        self.assertIn('journal: "Correct Journal"', index)
        self.assertIn('doi: "10.1234/corrected"', index)
        self.assertEqual(self.summary()["citekey"], "author2026transport")

    def test_failed_sync_returns_failure(self):
        self.assertEqual(self.invoke([(0, "lint ok"), (9, "sync failed")]), (1, 1, 2))
        self.assertEqual(self.summary()["sync"]["rc"], 9)
        self.assertEqual(self.summary()["status"], "failed")

    def test_conflicting_reading_link_blocks_before_vault_writes(self):
        catalog = self.web / "public/vault/catalog.json"
        catalog.parent.mkdir(parents=True)
        catalog.write_text(json.dumps({"papers": [{"pid": "Old", "doi": "10.1234/other",
                           "citekey": "tester2026transport"}]}), encoding="utf-8")
        code, gate, commands = self.invoke([])
        self.assertNotEqual(code, 0)
        self.assertEqual((gate, commands), (0, 0))
        self.assertFalse(self.vault.exists())

    def test_explicit_distinct_reading_link_preserves_catalog(self):
        catalog = self.web / "public/vault/catalog.json"
        catalog.parent.mkdir(parents=True)
        old = json.dumps({"papers": [{"pid": "Old", "citekey": "tester2026transport"}]})
        catalog.write_text(old, encoding="utf-8")
        path = self.work / "out/fields.json"
        fields = json.loads(path.read_text(encoding="utf-8"))
        fields["citekey"] = "tester2026transportupstream"
        path.write_text(json.dumps(fields), encoding="utf-8")
        self.assertEqual(self.invoke([(0, "lint ok"), (0, "sync ok")]), (0, 1, 2))
        self.assertEqual(self.summary()["citekey"], "tester2026transportupstream")
        self.assertEqual(catalog.read_text(encoding="utf-8"), old)

    def test_invalid_reading_link_blocks_before_vault_writes(self):
        path = self.work / "out/fields.json"
        fields = json.loads(path.read_text(encoding="utf-8"))
        fields["citekey"] = "../old"
        path.write_text(json.dumps(fields), encoding="utf-8")
        code, gate, commands = self.invoke([])
        self.assertNotEqual(code, 0)
        self.assertEqual((gate, commands), (0, 0))
        self.assertFalse(self.vault.exists())

    def test_no_sync_is_assembled_not_ready(self):
        self.assertEqual(self.invoke([(0, "lint ok")], ["--no-sync"]), (0, 1, 1))
        self.assertEqual(self.summary()["status"], "assembled")

    def test_existing_index_is_untouched_before_verify_or_publication(self):
        self.index.parent.mkdir(parents=True)
        old = '---\ncitekey: existing2026\nreading: 在读\n---\nUser index\n'
        self.index.write_text(old, encoding="utf-8")
        code, gate, commands = self.invoke([])
        self.assertNotEqual(code, 0)
        self.assertEqual((gate, commands), (0, 0))
        self.assertEqual(self.index.read_text(encoding="utf-8"), old)
        self.assertFalse((self.vault / "30_Terms").exists())

    def test_catalog_doi_match_blocks_renamed_duplicate(self):
        self.index.parent.mkdir(parents=True)
        self.index.write_text("Existing paper", encoding="utf-8")
        catalog = self.web / "public/vault/catalog.json"
        catalog.parent.mkdir(parents=True)
        catalog.write_text(json.dumps({"papers": [{"pid": "Existing", "doi": "https://doi.org/10.1234/FIXTURE",
                           "vault": {"index": str(self.index.relative_to(self.vault))}}]}), encoding="utf-8")
        result = finish.existing_paper(self.vault.resolve(), self.index.with_name("Other.md"), "10.1234/fixture", self.web)
        self.assertEqual(result, "Existing")


if __name__ == "__main__":
    unittest.main()
