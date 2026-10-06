from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import translation
import run_agent
import pymupdf


SOURCE = """# Paper

## Abstract

The velocity $u_* = 2$ is defined here.

$$
x^2 + y^2 = 1 \\tag{1}
$$

![[Test_page1_fig1.png]]
Fig. 1. The full caption with $u_*$.

| Case | Velocity | Length |
| :--- | ---: | --- |
| Case 1 | 0.5 m/s | $L=2$ |

Use `solver()` unchanged.

```python
value = "$not_math$"
```

## References

Author (2020). Exact reference. ^ref-1
"""


class TranslationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        (self.work / "out").mkdir()
        (self.work / "images").mkdir()
        (self.work / "out/en.md").write_text(SOURCE, encoding="utf-8")
        doc = pymupdf.open()
        doc.new_page(width=300, height=400)
        doc.save(self.work / "source.pdf")
        doc.close()
        (self.work / "images/Test_page1_fig1.png").write_bytes(b"fixture")
        self.put("meta.json", {"key": "Test", "pdf": str(self.work / "source.pdf")})
        self.put("stats.json", {"pages": 1})
        self.put("out/layout.json", {"headings": [{"title": "Abstract", "page": 1}],
            "equations": [{"num": 1, "page": 1}], "tables": [{"num": 1, "page": 1}],
            "figures": [{"num": 1, "page": 1}]})
        self.put("figcut.json", {"figures": [{"num": 1, "sourcePage": 1, "bbox": [10, 20, 100, 200],
            "file": "Test_page1_fig1.png", "status": "manual", "reviewed": True,
            "reviewNote": "Saw original page and all panels", "reviewedAt": "2026-10-03T00:00:00Z"}]})
        with patch("mathcheck.check_renderable", return_value=[]):
            self.assertTrue(translation.review_source(self.work, "Checked page 1 equation/table/structure")["ok"])

    def put(self, name, data):
        (self.work / name).write_text(json.dumps(data), encoding="utf-8")

    def prepare(self):
        result = translation.prepare(self.work)
        self.assertTrue(result["ok"], result)
        return (self.work / "translation/input.md").read_text(encoding="utf-8")

    def translated(self):
        locked = self.prepare()
        for source, target in {"Paper": "论文", "Abstract": "摘要", "The velocity": "速度",
                "is defined here.": "在此定义。", "Fig. 1. The full caption with": "图1。完整图注，含",
                "Case": "工况", "Velocity": "速度", "Length": "长度", "Use": "使用",
                "unchanged.": "保持不变。", "References": "参考文献"}.items():
            locked = locked.replace(source, target)
        return locked

    def write_locked(self, text):
        (self.work / "translation/zh.locked.md").write_text(text, encoding="utf-8")

    def assert_rejected(self, locked):
        old = "Existing Chinese must survive"
        (self.work / "out/zh.md").write_text(old, encoding="utf-8")
        self.write_locked(locked)
        result = translation.merge(self.work)
        self.assertFalse(result["ok"])
        self.assertEqual(old, (self.work / "out/zh.md").read_text(encoding="utf-8"))

    def test_math_caption_code_references_table_roundtrip(self):
        locked = self.translated()
        self.assertNotIn("x^2", locked)
        self.assertNotIn("0.5 m/s", locked)
        self.assertNotIn("^ref-1", locked)
        self.write_locked(locked)
        result = translation.merge(self.work)
        self.assertTrue(result["ok"], result)
        zh = (self.work / "out/zh.md").read_text(encoding="utf-8")
        self.assertIn("图1。完整图注，含 $u_*$", zh)
        self.assertIn("| 工况 1 | 0.5 m/s | $L=2$ |", zh)
        self.assertIn("## 参考文献", zh)
        self.assertEqual([], translation.compare_protected(SOURCE, zh))
        self.assertTrue(translation.check_translation(self.work)["ok"])
        self.assertFalse((self.work / "out/notes.md").exists())

    def test_tokens_missing_duplicated_renamed_reordered(self):
        locked = self.translated()
        first, second = translation.TOKEN_RE.findall(locked)[:2]
        for altered in (locked.replace(first, "", 1), locked + first,
                        locked.replace(first, "⟦WS999999⟧", 1),
                        locked.replace(first, "TEMP", 1).replace(second, first, 1).replace("TEMP", second, 1)):
            with self.subTest(altered=altered[:60]):
                self.assert_rejected(altered)

    def test_new_math_image_code_rejected(self):
        locked = self.translated()
        for added in ("$extra$", "$$extra$$", "![[new.png]]", "![x](x.png)", "`new()`", r"\(x\)"):
            with self.subTest(added=added):
                self.assert_rejected(locked + added)

    def test_empty_translated_paragraph_rejected(self):
        locked = self.translated()
        self.assert_rejected(locked.replace("速度 ", "").replace(" 在此定义。", ""))

    def test_extra_paragraph_or_text_outside_skeleton_rejected(self):
        locked = self.translated()
        self.assert_rejected(locked + "\n\nNew paragraph")
        self.assert_rejected(locked.replace("速度 ", "速度\n\n新增段落 ", 1))

    def test_source_edit_invalidates_review_and_merge(self):
        locked = self.translated()
        (self.work / "out/en.md").write_text(SOURCE + "\nChanged", encoding="utf-8")
        self.assertTrue(translation.check_source_review(self.work))
        self.assert_rejected(locked)

    def test_prepared_input_or_manifest_tampering_rejected(self):
        locked = self.translated()
        input_path = self.work / "translation/input.md"
        input_path.write_text(locked.replace("速度", "篡改"), encoding="utf-8")
        self.assert_rejected(locked)
        self.prepare()
        manifest = json.loads((self.work / "translation/manifest.json").read_text(encoding="utf-8"))
        manifest["blocks"] = []
        self.put("translation/manifest.json", manifest)
        self.assert_rejected(locked)

    def test_layout_edit_invalidates_review(self):
        self.prepare()
        data = json.loads((self.work / "out/layout.json").read_text())
        data["equations"][0]["page"] = 2
        self.put("out/layout.json", data)
        errors = translation.check_source_review(self.work)
        self.assertTrue(any("页码" in e for e in errors))
        self.assertTrue(any("layout.json 已改变" in e for e in errors))
        self.assertFalse(translation.prepare(self.work)["ok"])

    def test_fig_review_file_and_geometry_required(self):
        path = self.work / "figcut.json"
        original = json.loads(path.read_text())
        for field, value in (("reviewed", False), ("reviewNote", ""), ("reviewedAt", ""),
                             ("sourcePage", 2), ("bbox", [1, 1, 999, 99]), ("file", "absent.png")):
            data = json.loads(json.dumps(original))
            data["figures"][0][field] = value
            self.put("figcut.json", data)
            with self.subTest(field=field):
                self.assertFalse(translation.prepare(self.work)["ok"])

    def test_all_flags_and_snapshot_required_even_no_equations(self):
        data = json.loads((self.work / "out/source-review.json").read_text())
        for flag in ("equationsReviewed", "tablesReviewed", "structureReviewed"):
            changed = {**data, flag: False}
            self.put("out/source-review.json", changed)
            self.assertFalse(translation.prepare(self.work)["ok"])
        self.put("out/source-review.json", data)
        (self.work / "out/source-review.layout.json").unlink()
        self.assertTrue(translation.check_source_review(self.work))

    def test_bad_rendering_writes_no_review(self):
        for name in ("source-review.json", "source-review.en.md", "source-review.layout.json"):
            (self.work / "out" / name).unlink()
        with patch("mathcheck.check_renderable", return_value=["unrenderable"]):
            self.assertFalse(translation.review_source(self.work, "Saw pages")["ok"])
        self.assertFalse((self.work / "out/source-review.json").exists())
        self.assertFalse((self.work / "out/source-review.en.md").exists())

    def test_protected_original_changes_and_heading_translation(self):
        self.assertEqual([], translation.compare_protected(SOURCE, SOURCE.replace("## References", "## 参考文献")))
        for old, new in (("x^2", "x^3"), ("Test_page1_fig1", "Wrong"), ("0.5 m/s", "0.6 m/s"),
                         ("Exact reference", "Changed reference")):
            self.assertTrue(translation.compare_protected(SOURCE, SOURCE.replace(old, new)))

    def test_code_is_opaque_including_double_backticks(self):
        spans = translation.protected_spans('Text ``code `$x$` `` and $u$\n')
        self.assertEqual(["code_inline", "math_inline"], [s["kind"] for s in spans])
        self.assertEqual('``code `$x$` ``', spans[0]["text"])

    def test_review_without_equations_still_seals_all_three_flags(self):
        (self.work / "out/en.md").write_text("## Abstract\n\nProse without formulas.\n", encoding="utf-8")
        self.put("out/layout.json", {"headings": [{"title": "Abstract", "page": 1}],
            "equations": [], "tables": [], "figures": []})
        with patch("mathcheck.check_renderable", return_value=[]):
            self.assertTrue(translation.review_source(self.work, "Checked the full one-page prose")["ok"])
        review = json.loads((self.work / "out/source-review.json").read_text())
        for flag in ("equationsReviewed", "tablesReviewed", "structureReviewed"):
            self.assertIs(True, review[flag])
        self.assertEqual([], translation.check_source_review(self.work))

    def test_unreviewed_source_cannot_prepare(self):
        (self.work / "out/source-review.json").unlink()
        self.assertFalse(translation.prepare(self.work)["ok"])
        self.assertFalse((self.work / "translation").exists())

    def test_inline_token_context_supports_lambda_sentence(self):
        sentence = r"Three different values of $\lambda$, $\lambda=2B$, $6B$ and $10B$ are selected. "
        source = SOURCE.replace("The velocity", sentence + "The velocity")
        (self.work / "out/en.md").write_text(source, encoding="utf-8")
        with patch("mathcheck.check_renderable", return_value=[]):
            self.assertTrue(translation.review_source(self.work, "Checked the lambda sentence against source")["ok"])
        self.prepare()
        context = translation.token_context(self.work)
        items = json.loads(context[context.index("["):])
        values = [entry["value"] for entry in items]
        self.assertIn(r"$\lambda$", values)
        self.assertIn(r"$\lambda=2B$", values)
        self.assertIn("$6B$", values)
        self.assertIn("0.5 m/s", context)
        self.assertNotIn("x^2 + y^2", context)
        self.assertNotIn("Test_page1_fig1.png", context)
        request = (self.work / "translation/request.md").read_text(encoding="utf-8")
        self.assertIn(context, request)
        self.assertIn("不要把释义内容抄入译文", request)
        self.assertEqual(0, self.run_main(expected_symbol=r"$\lambda$"))
        zh = (self.work / "out/zh.md").read_text(encoding="utf-8")
        self.assertEqual([], translation.compare_protected(source, zh))

    def test_en_source_never_falls_back_to_existing_zh(self):
        (self.work / "out/en.md").unlink()
        (self.work / "out/zh.md").write_text("## 摘要\n\n中文残留稿。", encoding="utf-8")
        with patch("mathcheck.check_renderable", return_value=[]):
            result = translation.review_source(self.work, "Review attempted")
        self.assertFalse(result["ok"])
        self.assertFalse((self.work / "out/source-review.zh.md").exists())
        self.assertFalse(translation.prepare(self.work)["ok"])

    def test_review_language_must_be_explicit_and_match_meta(self):
        data = json.loads((self.work / "out/source-review.json").read_text(encoding="utf-8"))
        for language in (None, "zh"):
            changed = {**data, "sourceLanguage": language}
            self.put("out/source-review.json", changed)
            self.assertTrue(any("sourceLanguage" in e for e in translation.check_source_review(self.work)))
            self.assertFalse(translation.prepare(self.work)["ok"])

    def test_zh_source_uses_meta_language_even_with_stale_en(self):
        meta = json.loads((self.work / "meta.json").read_text(encoding="utf-8"))
        self.put("meta.json", {**meta, "lang": "zh"})
        chinese = "## 摘要\n\n中文原刊正文。\n"
        (self.work / "out/zh.md").write_text(chinese, encoding="utf-8")
        self.assertTrue(any("meta.lang" in e for e in translation.check_source_review(self.work)))
        with patch("mathcheck.check_renderable", return_value=[]) as render:
            result = translation.review_source(self.work, "Checked original Chinese article")
        self.assertTrue(result["ok"], result)
        self.assertEqual("zh", result["sourceLanguage"])
        render.assert_called_once_with(chinese)
        self.assertEqual((self.work / "out/zh.md").read_bytes(), (self.work / "out/source-review.zh.md").read_bytes())
        self.assertEqual([], translation.check_source_review(self.work))
        self.assertFalse(translation.prepare(self.work)["ok"])

    def test_analyst_highlights_inserted_without_retranslation(self):
        self.write_locked(self.translated())
        self.assertTrue(translation.merge(self.work)["ok"])
        (self.work / "out/highlights.md").write_text("## 亮点\n\n- 一\n- 二\n- 三\n\n>【说明】原刊无 Highlights；此处是分析补稿。", encoding="utf-8")
        self.assertFalse(translation.check_translation(self.work)["ok"])
        result = translation.merge(self.work)
        self.assertTrue(result["ok"], result)
        zh = (self.work / "out/zh.md").read_text(encoding="utf-8")
        self.assertLess(zh.index("## 亮点"), zh.index("## 摘要"))
        self.assertTrue(translation.check_translation(self.work)["ok"])

    def test_highlights_cannot_add_math(self):
        self.write_locked(self.translated())
        (self.work / "out/highlights.md").write_text("## 亮点\n\n- $x$\n- 二\n- 三\n\n>【说明】补稿", encoding="utf-8")
        self.assertFalse(translation.merge(self.work)["ok"])

    def test_run_round_records_actual_pid_and_exit(self):
        proc = Mock(pid=456, stdin=io.BytesIO())
        proc.wait.return_value = 0
        proc.poll.return_value = 0
        resource = self.work / "round.resource.json"
        with patch("run_agent.subprocess.Popen", return_value=proc) as popen:
            rc, _ = run_agent.run_round(["fake", "arg"], self.work, "prompt", True,
                                       self.work / "round.log", 10, resource=resource)
        self.assertEqual(0, rc)
        record = json.loads(resource.read_text())
        self.assertEqual(456, record["pid"])
        self.assertEqual(["fake", "arg"], record["cmd"])
        self.assertEqual("exited", record["state"])
        popen.assert_called_once()

    def run_main(self, args=(), rc=0, repair=False, final_text=None, expected_symbol=None):
        def round_stub(cmd, work, prompt, *other):
            self.assertEqual(self.work / "translation", work)
            self.assertNotIn("brief.md", prompt)
            self.assertIn("BEGIN_LOCKED_ENGLISH", prompt)
            self.assertIn("The velocity", prompt)
            self.assertIn("不得调用工具", prompt)
            if expected_symbol:
                self.assertIn(json.dumps(expected_symbol, ensure_ascii=False), prompt)
                self.assertIn("只读 token 释义", prompt)
                self.assertIn("Three different values of", prompt)
            self.assertEqual("-o", cmd[1])
            self.assertEqual(work / "round1.last.md", Path(cmd[2]))
            if rc == 0:
                locked = (work / "input.md").read_text(encoding="utf-8").replace("Abstract", "摘要").replace("References", "参考文献")
                Path(cmd[2]).write_text(locked if final_text is None else final_text, encoding="utf-8")
            return rc, 0.1
        argv = ["run_agent.py", "--work", str(self.work), "--rounds", "1", *args]
        with patch.object(sys, "argv", argv), patch("run_agent.utf8"), patch("run_agent.say"), \
                patch("run_agent.load_config", return_value={"agent": {"runner": "codex", "models": {"codex": "gpt-5.6-luna"}, "effort": "high"}}), \
                patch("run_agent.build_cmd", side_effect=lambda template, ctx: ["mock-cli", "-o", ctx["last"]]), \
                patch("run_agent.run_round", side_effect=round_stub) as run, \
                patch("verify.verify", side_effect=AssertionError("translate must not run full verify")):
            if repair:
                run_agent.main()
                self.assertFalse(run.called)
                return None
            with self.assertRaises(SystemExit) as exited:
                run_agent.main()
            return exited.exception.code

    def test_default_cli_stage_and_explicit_effort(self):
        self.assertEqual(0, self.run_main())
        timing = json.loads((self.work / "timing.json").read_text())
        self.assertEqual("translate", timing["stage"])
        self.assertEqual("gpt-5.6-luna", timing["model"])
        self.assertEqual("low", timing["effort"])
        self.assertEqual(0, self.run_main(["--effort", "medium"]))
        self.assertEqual("medium", json.loads((self.work / "timing.json").read_text())["effort"])

    def test_failed_cli_does_not_merge_old_locked_translation(self):
        self.write_locked(self.translated())
        (self.work / "translation/round1.last.md").write_text(self.translated(), encoding="utf-8")
        (self.work / "out/zh.md").write_text("Existing translation", encoding="utf-8")
        self.assertEqual(1, self.run_main(rc=1))
        self.assertEqual("Existing translation", (self.work / "out/zh.md").read_text(encoding="utf-8"))

    def test_rc_zero_blank_final_does_not_reuse_old_translation(self):
        self.write_locked(self.translated())
        (self.work / "out/zh.md").write_text("Existing translation", encoding="utf-8")
        self.assertEqual(1, self.run_main(final_text="  \n"))
        self.assertEqual("Existing translation", (self.work / "out/zh.md").read_text(encoding="utf-8"))

    def test_codex_repair_prompt_contains_current_locked_draft(self):
        prompts = []
        def stub(cmd, work, prompt, *other):
            prompts.append(prompt)
            text = (work / "input.md").read_text(encoding="utf-8").replace("Abstract", "摘要").replace("References", "参考文献")
            if len(prompts) == 1:
                text = text.replace(translation.TOKEN_RE.findall(text)[0], "", 1)
            Path(cmd[2]).write_text(text, encoding="utf-8")
            return 0, 0.1
        argv = ["run_agent.py", "--work", str(self.work), "--rounds", "2"]
        with patch.object(sys, "argv", argv), patch("run_agent.utf8"), patch("run_agent.say"), \
                patch("run_agent.load_config", return_value={"agent": {"runner": "codex"}}), \
                patch("run_agent.build_cmd", side_effect=lambda template, ctx: ["mock-cli", "-o", ctx["last"]]), \
                patch("run_agent.run_round", side_effect=stub):
            with self.assertRaises(SystemExit) as exited:
                run_agent.main()
        self.assertEqual(0, exited.exception.code)
        self.assertEqual(2, len(prompts))
        self.assertIn("BEGIN_CURRENT_LOCKED_DRAFT", prompts[1])
        self.assertIn("仅局部修复", prompts[1])
        self.assertIn("BEGIN_LOCKED_ENGLISH", prompts[1])

    def test_repair_only_checks_translation_gate(self):
        self.write_locked(self.translated())
        self.assertTrue(translation.merge(self.work)["ok"])
        self.run_main(["--repair-only"], repair=True)


if __name__ == "__main__":
    unittest.main()
