from __future__ import annotations

import json
import unittest

from runbook_rag_review.contracts import ContractError
from runbook_rag_review.provider import (
    BEDROCK_MODEL_ID,
    ProviderStatus,
    bedrock_response,
)


class FakeBedrockClient:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls = []

    def converse(self, **request):
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return self.response


class BedrockProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = json.dumps(
            {
                "question": "What is required?",
                "passages": [{"evidence_id": "evidence-1", "text": "Do the work."}],
            }
        )

    def test_completed_response_uses_converse_and_reports_usage(self) -> None:
        output = {
            "status": "answered",
            "claims": [{"text": "Do the work.", "evidence_ids": ["evidence-1"]}],
            "reason": "The passage directly supports the claim.",
        }
        client = FakeBedrockClient(
            {
                "output": {
                    "message": {
                        "content": [
                            {
                                "toolUse": {
                                    "toolUseId": "tool-1",
                                    "name": "submit_answer",
                                    "input": output,
                                }
                            }
                        ]
                    }
                },
                "stopReason": "tool_use",
                "usage": {"inputTokens": 10, "outputTokens": 8, "totalTokens": 18},
            }
        )

        response = bedrock_response(
            self.context, region="us-east-1", client=client
        )

        self.assertEqual(ProviderStatus.COMPLETED, response.status)
        self.assertEqual(BEDROCK_MODEL_ID, response.model_id)
        self.assertEqual(18, response.usage_tokens)
        request = client.calls[0]
        self.assertEqual(BEDROCK_MODEL_ID, request["modelId"])
        self.assertEqual(0, request["inferenceConfig"]["temperature"])
        self.assertEqual(
            "submit_answer", request["toolConfig"]["toolChoice"]["tool"]["name"]
        )
        self.assertIn(
            'The only allowed evidence IDs are ["evidence-1"]',
            request["messages"][0]["content"][0]["text"],
        )

    def test_stop_reasons_and_transport_failures_are_visible(self) -> None:
        for reason, status in (
            ("max_tokens", ProviderStatus.TRUNCATED),
            ("content_filtered", ProviderStatus.REFUSED),
        ):
            with self.subTest(reason=reason):
                client = FakeBedrockClient(
                    {
                        "output": {"message": {"content": []}},
                        "stopReason": reason,
                        "usage": {"totalTokens": 12},
                    }
                )
                response = bedrock_response(
                    self.context, region="us-east-1", client=client
                )
                self.assertEqual(status, response.status)
                self.assertIsNone(response.output_text)

        client = FakeBedrockClient(error=TimeoutError("unavailable"))
        with self.assertRaisesRegex(ContractError, "provider_transport_error"):
            bedrock_response(self.context, region="us-east-1", client=client)

    def test_invalid_region_and_response_are_rejected(self) -> None:
        with self.assertRaisesRegex(ContractError, "invalid_provider_region"):
            bedrock_response(self.context, region="", client=FakeBedrockClient())

        with self.assertRaisesRegex(ContractError, "invalid_provider_response"):
            bedrock_response(
                self.context,
                region="us-east-1",
                client=FakeBedrockClient({}),
            )


if __name__ == "__main__":
    unittest.main()
