from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runbook_rag_review.demo import run_demo


class DemoTests(unittest.TestCase):
    def test_demo_passes_and_writes_feedback_evidence(self) -> None:
        fixture_dir = Path(__file__).parents[1] / "fixtures"
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory)
            report = run_demo(fixture_dir, output_dir)
            feedback = json.loads((output_dir / "feedback.json").read_bytes())

            self.assertTrue(all(report["checks"].values()))
            self.assertEqual(1, len(feedback["runs"]))
            self.assertEqual("correct", feedback["runs"][0]["reviews"][0]["decision"])
            self.assertTrue((output_dir / "demo.json").is_file())
            self.assertTrue((output_dir / "demo.md").is_file())


if __name__ == "__main__":
    unittest.main()
