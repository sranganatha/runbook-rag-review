from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from runbook_rag_review.contracts import ContractError
from runbook_rag_review.provider import (
    OLLAMA_MODEL_ID,
    ProviderStatus,
    ollama_response,
)


class OllamaProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = json.dumps(
            {
                "question": "What is required?",
                "passages": [{"evidence_id": "evidence-1", "text": "Do the work."}],
            }
        )

    def test_completed_response_uses_schema_and_reports_usage(self) -> None:
        result = {
            "model": OLLAMA_MODEL_ID,
            "message": {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "status": "answered",
                        "claims": [
                            {
                                "text": "Do the work.",
                                "evidence_ids": ["evidence-1"],
                            }
                        ],
                        "reason": None,
                    }
                ),
            },
            "done_reason": "stop",
            "prompt_eval_count": 10,
            "eval_count": 8,
        }
        with patch(
            "runbook_rag_review.provider.urlopen",
            return_value=io.BytesIO(json.dumps(result).encode()),
        ) as request_call:
            response = ollama_response(self.context, endpoint="http://ollama:11434")

        self.assertEqual(ProviderStatus.COMPLETED, response.status)
        self.assertEqual(18, response.usage_tokens)
        request = request_call.call_args.args[0]
        payload = json.loads(request.data)
        prompt = payload["messages"][0]["content"]
        self.assertEqual(OLLAMA_MODEL_ID, payload["model"])
        self.assertEqual(0, payload["options"]["temperature"])
        self.assertIn('The only allowed evidence IDs are ["evidence-1"]', prompt)
        self.assertEqual("string", payload["format"]["properties"]["reason"]["type"])

    def test_length_and_unknown_stop_reasons_are_visible(self) -> None:
        for reason, status in (
            ("length", ProviderStatus.TRUNCATED),
            ("unload", ProviderStatus.REFUSED),
        ):
            with self.subTest(reason=reason):
                result = {
                    "model": OLLAMA_MODEL_ID,
                    "message": {"role": "assistant", "content": "ignored"},
                    "done_reason": reason,
                }
                with patch(
                    "runbook_rag_review.provider.urlopen",
                    return_value=io.BytesIO(json.dumps(result).encode()),
                ):
                    response = ollama_response(
                        self.context, endpoint="http://127.0.0.1:11434"
                    )

                self.assertEqual(status, response.status)
                self.assertIsNone(response.output_text)

    def test_nonlocal_endpoint_and_invalid_response_are_rejected(self) -> None:
        with self.assertRaisesRegex(ContractError, "invalid_provider_endpoint"):
            ollama_response(self.context, endpoint="https://example.com")

        with patch(
            "runbook_rag_review.provider.urlopen",
            return_value=io.BytesIO(b"{}"),
        ):
            with self.assertRaisesRegex(ContractError, "invalid_provider_response"):
                ollama_response(self.context, endpoint="http://localhost:11434")


if __name__ == "__main__":
    unittest.main()
