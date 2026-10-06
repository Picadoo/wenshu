from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "lint_en_draft.py"
SPEC = importlib.util.spec_from_file_location("lint_en_draft", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BlockingPolicyTests(unittest.TestCase):
    def test_warning_is_advisory_by_default(self) -> None:
        self.assertEqual(MODULE.blocking_count([], ["missing caption"], False), 0)

    def test_warning_blocks_strict_promotion(self) -> None:
        self.assertEqual(MODULE.blocking_count([], ["missing caption"], True), 1)

    def test_error_always_blocks(self) -> None:
        self.assertEqual(MODULE.blocking_count(["bad math"], [], False), 1)


if __name__ == "__main__":
    unittest.main()
