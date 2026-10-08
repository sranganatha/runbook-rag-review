from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from runbook_rag_review.provider import (
    OLLAMA_MODEL_ID,
    ProviderResponse,
    ProviderStatus,
    fixture_response,
)
from runbook_rag_review.verify_model import run_model_verification


class ModelVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture_dir = Path(__file__).parents[1] / "fixtures"

    def test_all_cases_are_counted_and_artifacts_are_written(self) -> None:
        def model_response(context_json: str):
            return replace(fixture_response(context_json), model_id=OLLAMA_MODEL_ID)

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory)
            report = run_model_verification(
                self.fixture_dir,
                output_dir,
                endpoint="http://ollama:11434",
                provider_call=model_response,
            )

            self.assertEqual(20, report["provider_calls"])
            self.assertEqual(8, report["splits"]["development"]["cases"])
            self.assertEqual(12, report["splits"]["holdout"]["cases"])
            self.assertEqual("real_local_model", report["execution_mode"])
            self.assertTrue(report["run_completed"])
            self.assertTrue(report["safety_verification_passed"])
            self.assertTrue((output_dir / "model-verification.json").is_file())
            self.assertTrue((output_dir / "model-verification.md").is_file())

    def test_provider_error_is_reported_without_fixture_fallback(self) -> None:
        calls = 0

        def truncate_once(context_json: str):
            nonlocal calls
            calls += 1
            if calls == 1:
                return ProviderResponse(
                    status=ProviderStatus.TRUNCATED,
                    output_text=None,
                    model_id=OLLAMA_MODEL_ID,
                    attempted_calls=1,
                    elapsed_ms=12.5,
                    usage_tokens=42,
                )
            return replace(fixture_response(context_json), model_id=OLLAMA_MODEL_ID)

        with tempfile.TemporaryDirectory() as temporary_directory:
            report = run_model_verification(
                self.fixture_dir,
                Path(temporary_directory),
                endpoint="http://ollama:11434",
                provider_call=truncate_once,
            )

        self.assertTrue(report["run_completed"])
        self.assertTrue(report["safety_verification_passed"])
        self.assertEqual(1, report["splits"]["development"]["errors"])
        self.assertEqual("provider_truncated", report["cases"][0]["error"]["code"])
        self.assertEqual(12.5, report["cases"][0]["provider_response"]["elapsed_ms"])
        self.assertEqual(42, report["cases"][0]["provider_response"]["usage_tokens"])
        self.assertEqual(20, calls)


if __name__ == "__main__":
    unittest.main()
