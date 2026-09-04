from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from runbook_rag_review.contracts import ContractError, Review, validate_fixture_set


class FixtureContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        fixture_dir = Path(__file__).parents[1] / "fixtures"
        cls.documents = json.loads((fixture_dir / "documents.json").read_text(encoding="utf-8"))
        cls.questions = json.loads((fixture_dir / "questions.json").read_text(encoding="utf-8"))

    def test_frozen_fixture_set_is_valid(self) -> None:
        documents, questions = validate_fixture_set(self.documents, self.questions)

        self.assertEqual(12, len(documents))
        self.assertEqual(20, len(questions))
        self.assertEqual(8, sum(question.split == "development" for question in questions))

    def test_top_level_fixture_shape_is_validated(self) -> None:
        with self.assertRaisesRegex(ContractError, "invalid_document_set"):
            validate_fixture_set({}, self.questions)

    def test_changed_source_text_invalidates_digest(self) -> None:
        documents = copy.deepcopy(self.documents)
        documents[0]["source_text"] += " changed"

        with self.assertRaisesRegex(ContractError, "digest_mismatch"):
            validate_fixture_set(documents, self.questions)

    def test_evidence_must_be_exact_source_text(self) -> None:
        questions = copy.deepcopy(self.questions)
        questions[0]["relevant_evidence"][0]["exact_text"] = "plausible but absent"

        with self.assertRaisesRegex(ContractError, "evidence_text_mismatch"):
            validate_fixture_set(self.documents, questions)

    def test_abstention_cannot_smuggle_expected_evidence(self) -> None:
        questions = copy.deepcopy(self.questions)
        abstention = next(
            question for question in questions if question["expected_status"] == "abstained"
        )
        abstention["required_facts"] = ["invented answer"]

        with self.assertRaisesRegex(ContractError, "invalid_abstention_label"):
            validate_fixture_set(self.documents, questions)

    def test_label_cannot_use_evidence_outside_authorized_scope(self) -> None:
        questions = copy.deepcopy(self.questions)
        questions[0]["relevant_evidence"] = [
            {
                "document_id": "data-pipeline-costs",
                "version": 1,
                "exact_text": "FinOps may view aggregate spend",
            }
        ]

        with self.assertRaisesRegex(ContractError, "evidence_scope_mismatch"):
            validate_fixture_set(self.documents, questions)

    def test_correction_requires_claims_and_evidence(self) -> None:
        record = {
            "answer_run_id": "run-001",
            "answer_version": 1,
            "reviewer_id": "reviewer-fixture-1",
            "decision": "correct",
            "rationale": "The deadline is stale.",
            "corrected_claims": ["Apply tags within three calendar days."],
            "corrected_evidence_ids": [],
            "reviewed_at": "2026-09-03T12:00:00+00:00",
        }

        with self.assertRaisesRegex(ContractError, "incomplete_correction"):
            Review.from_dict(record)


if __name__ == "__main__":
    unittest.main()
