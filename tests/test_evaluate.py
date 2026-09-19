from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path

from runbook_rag_review.answer import Claim, generate_answer
from runbook_rag_review.cli import main as cli_main
from runbook_rag_review.contracts import validate_fixture_set
from runbook_rag_review.evaluate import evaluate_answer, run_evaluation
from runbook_rag_review.index import build_index
from runbook_rag_review.provider import fixture_response
from runbook_rag_review.retrieve import retrieve


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture_dir = Path(__file__).parents[1] / "fixtures"
        document_records = json.loads((cls.fixture_dir / "documents.json").read_bytes())
        question_records = json.loads((cls.fixture_dir / "questions.json").read_bytes())
        cls.documents, cls.labels = validate_fixture_set(
            document_records, question_records
        )

    def test_report_counts_every_case_and_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory)
            first = run_evaluation(self.fixture_dir, output_dir)
            first_json = (output_dir / "evaluation.json").read_bytes()
            first_markdown = (output_dir / "evaluation.md").read_bytes()
            second = run_evaluation(self.fixture_dir, output_dir)

            self.assertEqual(first, second)
            self.assertEqual(first_json, (output_dir / "evaluation.json").read_bytes())
            self.assertEqual(
                first_markdown, (output_dir / "evaluation.md").read_bytes()
            )
            self.assertEqual("deterministic_fixture", first["execution_mode"])
            for result in first["configurations"].values():
                self.assertEqual(8, result["splits"]["development"]["cases"])
                self.assertEqual(12, result["splits"]["holdout"]["cases"])
                self.assertEqual(20, len(result["cases"]))
                for split in result["splits"].values():
                    self.assertEqual(0, split["unauthorized_chunks"])
                    self.assertEqual(0, split["stale_chunks"])

            control = first["unscoped_negative_control"]
            self.assertEqual(0, control["provider_calls"])
            self.assertGreater(control["unauthorized_chunks"], 0)

    def test_irrelevant_real_citation_fails_claim_and_fact_support(self) -> None:
        label = next(
            item
            for item in self.labels
            if item.case_id == "dev-01-current-tag-deadline"
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            index_path = Path(temporary_directory) / "runbooks.db"
            build_index(index_path, self.documents)
            retrieval = retrieve(
                index_path,
                label.question,
                label.authorized_scope,
                label.as_of,
            )
            answer = generate_answer(
                "irrelevant-citation",
                label.question,
                retrieval,
                fixture_response,
                generation_mode="fixture",
            )
            answer = replace(
                answer,
                claims=(
                    Claim(
                        "This claim is not in the cited passage.",
                        answer.claims[0].evidence_ids,
                    ),
                ),
            )

        result = evaluate_answer(label, retrieval, answer)

        self.assertEqual({"numerator": 1, "denominator": 1}, result["valid_citations"])
        self.assertEqual({"numerator": 0, "denominator": 1}, result["supported_claims"])
        self.assertEqual(0, result["required_facts_supported"]["numerator"])

    def test_evaluate_cli_writes_both_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory) / "report"
            with redirect_stdout(StringIO()):
                exit_code = cli_main(["evaluate", "--output-dir", str(output_dir)])

            self.assertEqual(0, exit_code)
            self.assertTrue((output_dir / "evaluation.json").is_file())
            self.assertTrue((output_dir / "evaluation.md").is_file())


if __name__ == "__main__":
    unittest.main()
