from __future__ import annotations

import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ingest_stage.py"
SPEC = importlib.util.spec_from_file_location("ingest_stage", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class StageTimingTests(unittest.TestCase):
    def test_stage_duration_is_recorded(self) -> None:
        job: dict = {}
        started = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
        MODULE.update_stage(job, "lunaA", "start", started)
        row = MODULE.update_stage(job, "lunaA", "finish", started + timedelta(seconds=95.25))
        self.assertEqual(row["status"], "finished")
        self.assertEqual(row["durationSec"], 95.25)

    def test_finish_without_start_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            MODULE.update_stage({}, "lunaD", "finish", datetime.now(timezone.utc))

    def test_c_fallback_requires_specific_reason(self) -> None:
        with self.assertRaises(ValueError):
            MODULE.allow_c_fallback({}, "parser bad", datetime.now(timezone.utc))

    def test_c_fallback_reason_is_recorded(self) -> None:
        job = {"englishWorkflow": {"mode": "draft-patch", "cFallbackReason": None}}
        row = MODULE.allow_c_fallback(
            job,
            "PDF dump has no page markers and reading order is unusable",
            datetime.now(timezone.utc),
        )
        self.assertEqual(row["mode"], "full-rebuild")
        self.assertIn("page markers", row["cFallbackReason"])


if __name__ == "__main__":
    unittest.main()
