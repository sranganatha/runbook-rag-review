from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import Mock

from runbook_rag_review.answer import GenerationLimits, generate_answer
from runbook_rag_review.contracts import AnswerStatus, ContractError, validate_fixture_set
from runbook_rag_review.index import build_index
from runbook_rag_review.provider import ProviderResponse, ProviderStatus, fixture_response
from runbook_rag_review.retrieve import retrieve


class AnswerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        fixture_dir = Path(__file__).parents[1] / "fixtures"
        documents = json.loads((fixture_dir / "documents.json").read_bytes())
        questions = json.loads((fixture_dir / "questions.json").read_bytes())
        cls.documents, _ = validate_fixture_set(documents, questions)

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.index_path = Path(self.temporary_directory.name) / "runbooks.db"
        build_index(self.index_path, self.documents)
        self.retrieval = retrieve(
            self.index_path,
            "monthly budget thresholds",
            "finops",
            date(2026, 1, 15),
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_fixture_answer_uses_supplied_context(self) -> None:
        answer = generate_answer(
            "run-001",
            "What are the budget thresholds?",
            self.retrieval,
            fixture_response,
            generation_mode="fixture",
        )

        self.assertEqual(AnswerStatus.ANSWERED, answer.status)
        self.assertEqual(self.retrieval.hits[0].text, answer.claims[0].text)
        self.assertEqual((self.retrieval.hits[0].chunk_id,), answer.claims[0].evidence_ids)
        self.assertIsNone(answer.usage_tokens)

    def test_empty_retrieval_abstains(self) -> None:
        empty = replace(self.retrieval, hits=())

        answer = generate_answer(
            "run-002", "Unknown question", empty, fixture_response, generation_mode="fixture"
        )

        self.assertEqual(AnswerStatus.ABSTAINED, answer.status)
        self.assertEqual((), answer.claims)

    def test_unknown_evidence_id_is_rejected(self) -> None:
        response = completed_response(
            {"status": "answered", "claims": [{"text": "Claim", "evidence_ids": ["invented"]}]}
        )

        with self.assertRaisesRegex(ContractError, "unknown_evidence_id"):
            self.generate_with(response)

    def test_conflict_requires_two_claims_and_sources(self) -> None:
        retrieval = retrieve(
            self.index_path,
            "page service owner platform duty manager",
            "finops",
            date(2026, 1, 15),
        )
        hits_by_document = {hit.document_id: hit for hit in retrieval.hits}
        evidence_ids = [
            hits_by_document[document_id].chunk_id
            for document_id in ("anomaly-triage", "anomaly-escalation")
        ]
        response = completed_response(
            {
                "status": "conflict",
                "claims": [
                    {"text": "First", "evidence_ids": [evidence_ids[0]]},
                    {"text": "Second", "evidence_ids": [evidence_ids[1]]},
                ],
            }
        )

        answer = generate_answer(
            "run-conflict",
            "Who should be paged?",
            retrieval,
            lambda _: response,
            generation_mode="fixture",
        )

        self.assertEqual(AnswerStatus.CONFLICT, answer.status)

    def test_refusal_and_truncation_are_visible(self) -> None:
        for status, error_code in (
            (ProviderStatus.REFUSED, "provider_refused"),
            (ProviderStatus.TRUNCATED, "provider_truncated"),
        ):
            with self.subTest(status=status):
                with self.assertRaisesRegex(ContractError, error_code):
                    self.generate_with(
                        ProviderResponse(status, None, "fixture", 1, 0, None)
                    )

    def test_invalid_json_is_visible(self) -> None:
        with self.assertRaisesRegex(ContractError, "invalid_provider_json"):
            self.generate_with(
                ProviderResponse(
                    ProviderStatus.COMPLETED, "{", "fixture", 1, 0, None
                )
            )

    def test_context_budget_is_checked_before_provider_call(self) -> None:
        provider_call = Mock()

        with self.assertRaisesRegex(ContractError, "context_budget_exceeded"):
            generate_answer(
                "run-003",
                "Budget?",
                self.retrieval,
                provider_call,
                generation_mode="fixture",
                limits=GenerationLimits(max_context_chars=1),
            )

        provider_call.assert_not_called()

    def test_call_and_output_budgets_are_enforced(self) -> None:
        with self.assertRaisesRegex(ContractError, "provider_call_budget_exceeded"):
            self.generate_with(
                ProviderResponse(
                    ProviderStatus.COMPLETED, "{}", "fixture", 2, 0, None
                )
            )
        with self.assertRaisesRegex(ContractError, "provider_output_too_large"):
            generate_answer(
                "run-004",
                "Budget?",
                self.retrieval,
                lambda _: completed_response(
                    {"status": "abstained", "claims": [], "reason": "none"}
                ),
                generation_mode="fixture",
                limits=GenerationLimits(max_output_chars=1),
            )

    def test_transport_failure_has_no_fixture_fallback(self) -> None:
        def fail(_: str) -> ProviderResponse:
            raise TimeoutError("provider timed out")

        with self.assertRaisesRegex(ContractError, "provider_transport_error"):
            generate_answer(
                "run-005",
                "Budget?",
                self.retrieval,
                fail,
                generation_mode="model",
            )

    def test_provider_boundary_rechecks_retrieval_scope(self) -> None:
        unauthorized_hit = replace(self.retrieval.hits[0], team_scope="data-platform")
        retrieval = replace(self.retrieval, hits=(unauthorized_hit,))

        with self.assertRaisesRegex(ContractError, "retrieval_filter_violation"):
            generate_answer(
                "run-006", "Budget?", retrieval, fixture_response, generation_mode="fixture"
            )

    def generate_with(self, response: ProviderResponse):
        return generate_answer(
            "run-test",
            "What does the evidence say?",
            self.retrieval,
            lambda _: response,
            generation_mode="fixture",
        )


def completed_response(output: dict[str, object]) -> ProviderResponse:
    return ProviderResponse(
        ProviderStatus.COMPLETED,
        json.dumps(output),
        "fixture",
        1,
        0,
        None,
    )


if __name__ == "__main__":
    unittest.main()
