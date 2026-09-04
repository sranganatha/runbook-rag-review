from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from hashlib import sha256
from io import StringIO
from pathlib import Path

from runbook_rag_review.answer import generate_answer
from runbook_rag_review.cli import main as cli_main
from runbook_rag_review.contracts import ContractError, validate_fixture_set
from runbook_rag_review.index import build_index
from runbook_rag_review.provider import fixture_response
from runbook_rag_review.retrieve import retrieve
from runbook_rag_review.review import (
    load_review_history,
    load_run_snapshot,
    record_review,
    save_run_snapshot,
)

REVIEWERS = {"reviewer-fixture-1", "reviewer-fixture-2"}
REVIEWED_AT = "2026-09-04T12:00:00+00:00"


class ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        fixture_dir = Path(__file__).parents[1] / "fixtures"
        documents = json.loads((fixture_dir / "documents.json").read_bytes())
        questions = json.loads((fixture_dir / "questions.json").read_bytes())
        cls.documents, _ = validate_fixture_set(documents, questions)

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store_dir = Path(self.temporary_directory.name) / "review-store"
        index_path = Path(self.temporary_directory.name) / "runbooks.db"
        build_index(index_path, self.documents)
        self.retrieval = retrieve(
            index_path, "monthly budget", "finops", date(2026, 1, 15)
        )
        self.answer = generate_answer(
            "run-review-001",
            "What are the monthly budget actions?",
            self.retrieval,
            fixture_response,
            generation_mode="fixture",
        )
        self.snapshot = save_run_snapshot(
            self.store_dir,
            "What are the monthly budget actions?",
            self.retrieval,
            self.answer,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_snapshot_preserves_exact_hashed_evidence_and_is_immutable(self) -> None:
        evidence = self.snapshot["retrieval"]["evidence"][0]

        self.assertEqual(sha256(evidence["text"].encode()).hexdigest(), evidence["text_sha256"])
        self.assertEqual(self.retrieval.hits[0].text, evidence["text"])
        with self.assertRaisesRegex(ContractError, "run_exists"):
            save_run_snapshot(
                self.store_dir, "Question", self.retrieval, self.answer
            )

    def test_correction_advances_answer_version_and_stale_review_is_rejected(self) -> None:
        evidence_id = self.retrieval.hits[0].chunk_id
        correction = self.review_record(
            decision="correct",
            corrected_claims=["Corrected budget action."],
            corrected_evidence_ids=[evidence_id],
        )

        stored = record_review(self.store_dir, correction, REVIEWERS)

        self.assertEqual(2, stored["resulting_answer_version"])
        with self.assertRaisesRegex(ContractError, "stale_answer_version"):
            record_review(self.store_dir, self.review_record(), REVIEWERS)
        self.assertEqual(1, len(load_review_history(self.store_dir, self.answer.run_id)))

        current_review = self.review_record(answer_version=2)
        record_review(self.store_dir, current_review, REVIEWERS)
        self.assertEqual(2, len(load_review_history(self.store_dir, self.answer.run_id)))

    def test_unknown_reviewer_and_uncaptured_evidence_are_rejected(self) -> None:
        with self.assertRaisesRegex(ContractError, "unknown_reviewer"):
            record_review(
                self.store_dir,
                self.review_record(reviewer_id="not-a-fixture"),
                REVIEWERS,
            )
        with self.assertRaisesRegex(ContractError, "unknown_corrected_evidence"):
            record_review(
                self.store_dir,
                self.review_record(
                    decision="correct",
                    corrected_claims=["Correction"],
                    corrected_evidence_ids=["invented"],
                ),
                REVIEWERS,
            )
        self.assertEqual([], load_review_history(self.store_dir, self.answer.run_id))

    def test_snapshot_tampering_is_detected(self) -> None:
        run_file = next((self.store_dir / "runs").glob("*.json"))
        record = json.loads(run_file.read_text(encoding="utf-8"))
        record["question"] = "tampered"
        run_file.write_text(json.dumps(record), encoding="utf-8")

        with self.assertRaisesRegex(ContractError, "run_snapshot_tampered"):
            load_run_snapshot(self.store_dir, self.answer.run_id)

    def test_review_cli_records_explicit_run_and_version(self) -> None:
        with redirect_stdout(StringIO()):
            exit_code = cli_main(
                [
                    "review",
                    "--store",
                    str(self.store_dir),
                    "--run-id",
                    self.answer.run_id,
                    "--answer-version",
                    "1",
                    "--reviewer-id",
                    "reviewer-fixture-1",
                    "--decision",
                    "accept",
                    "--rationale",
                    "Evidence supports the answer.",
                ]
            )

        self.assertEqual(0, exit_code)
        self.assertEqual(1, len(load_review_history(self.store_dir, self.answer.run_id)))

    def review_record(
        self,
        *,
        answer_version: int = 1,
        reviewer_id: str = "reviewer-fixture-1",
        decision: str = "accept",
        corrected_claims: list[str] | None = None,
        corrected_evidence_ids: list[str] | None = None,
    ) -> dict[str, object]:
        return {
            "answer_run_id": self.answer.run_id,
            "answer_version": answer_version,
            "reviewer_id": reviewer_id,
            "decision": decision,
            "rationale": "Reviewed against captured evidence.",
            "corrected_claims": corrected_claims or [],
            "corrected_evidence_ids": corrected_evidence_ids or [],
            "reviewed_at": REVIEWED_AT,
        }


if __name__ == "__main__":
    unittest.main()
