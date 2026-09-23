from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from runbook_rag_review.cli import main as cli_main
from runbook_rag_review.review import load_run_snapshot


class LocalWorkflowCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.index_path = root / "runbooks.db"
        self.store_dir = root / "store"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_ingest_then_ask_saves_explicit_fixture_run(self) -> None:
        ingest_code, ingest_output, _ = self.run_cli(
            ["ingest", "--index", str(self.index_path)]
        )

        self.assertEqual(0, ingest_code)
        self.assertEqual(12, json.loads(ingest_output)["documents"])
        self.assertTrue(self.index_path.is_file())

        ask_code, ask_output, _ = self.run_cli(self.ask_arguments())

        self.assertEqual(0, ask_code)
        printed = json.loads(ask_output)
        saved = load_run_snapshot(self.store_dir, "run-cli-001")
        self.assertEqual(saved, printed)
        self.assertEqual("finops", saved["retrieval"]["authorized_scope"])
        self.assertEqual("fixture", saved["answer"]["generation_mode"])
        self.assertEqual(
            "deterministic-context-fixture-v1", saved["answer"]["model_id"]
        )

    def test_invalid_caller_date_and_missing_index_are_typed_failures(self) -> None:
        cases = (
            (self.ask_arguments(caller_id="unknown"), "unknown_caller"),
            (self.ask_arguments(as_of="not-a-date"), "invalid_as_of"),
            (self.ask_arguments(), "index_not_found"),
        )
        for arguments, error_code in cases:
            with self.subTest(error_code=error_code):
                exit_code, _, error_output = self.run_cli(arguments)

                self.assertEqual(2, exit_code)
                self.assertEqual(error_code, json.loads(error_output)["error"])
        self.assertFalse(self.store_dir.exists())

    def test_duplicate_run_id_is_rejected_without_overwrite(self) -> None:
        self.run_cli(["ingest", "--index", str(self.index_path)])
        first_code, first_output, _ = self.run_cli(self.ask_arguments())
        second_code, _, second_error = self.run_cli(self.ask_arguments())

        self.assertEqual(0, first_code)
        self.assertEqual(2, second_code)
        self.assertEqual("run_exists", json.loads(second_error)["error"])
        self.assertEqual(json.loads(first_output), load_run_snapshot(self.store_dir, "run-cli-001"))

    def ask_arguments(
        self,
        *,
        caller_id: str = "caller-fixture-finops",
        as_of: str = "2026-01-15",
    ) -> list[str]:
        return [
            "ask",
            "--index",
            str(self.index_path),
            "--store",
            str(self.store_dir),
            "--run-id",
            "run-cli-001",
            "--caller-id",
            caller_id,
            "--as-of",
            as_of,
            "--question",
            "What are the monthly budget thresholds?",
        ]

    @staticmethod
    def run_cli(arguments: list[str]) -> tuple[int, str, str]:
        standard_output = StringIO()
        standard_error = StringIO()
        with redirect_stdout(standard_output), redirect_stderr(standard_error):
            exit_code = cli_main(arguments)
        return exit_code, standard_output.getvalue(), standard_error.getvalue()


if __name__ == "__main__":
    unittest.main()
