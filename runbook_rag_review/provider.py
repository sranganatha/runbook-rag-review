from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from runbook_rag_review.contracts import ContractError


class ProviderStatus(StrEnum):
    COMPLETED = "completed"
    REFUSED = "refused"
    TRUNCATED = "truncated"


@dataclass(frozen=True)
class ProviderResponse:
    status: ProviderStatus
    output_text: str | None
    model_id: str
    attempted_calls: int
    elapsed_ms: float
    usage_tokens: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ProviderStatus):
            raise ContractError("invalid_provider_response", "status is unknown")
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ContractError("invalid_provider_response", "model_id must not be empty")
        if (
            isinstance(self.attempted_calls, bool)
            or not isinstance(self.attempted_calls, int)
            or self.attempted_calls < 1
        ):
            raise ContractError(
                "invalid_provider_response", "attempted_calls must be positive"
            )
        if (
            isinstance(self.elapsed_ms, bool)
            or not isinstance(self.elapsed_ms, (int, float))
            or self.elapsed_ms < 0
        ):
            raise ContractError("invalid_provider_response", "elapsed_ms must not be negative")
        if self.usage_tokens is not None and (
            isinstance(self.usage_tokens, bool)
            or not isinstance(self.usage_tokens, int)
            or self.usage_tokens < 0
        ):
            raise ContractError(
                "invalid_provider_response", "usage_tokens must be unknown or nonnegative"
            )
        if self.status is ProviderStatus.COMPLETED and not isinstance(
            self.output_text, str
        ):
            raise ContractError(
                "invalid_provider_response", "completed response requires output_text"
            )
        if self.status is not ProviderStatus.COMPLETED and self.output_text is not None:
            raise ContractError(
                "invalid_provider_response", "failed response must not include output_text"
            )


def fixture_response(context_json: str) -> ProviderResponse:
    context: dict[str, Any] = json.loads(context_json)
    passages = context["passages"]
    if not passages:
        output = {
            "status": "abstained",
            "reason": "No retrieved evidence was supplied.",
            "claims": [],
        }
    else:
        output = {
            "status": "answered",
            "claims": [
                {
                    "text": passages[0]["text"],
                    "evidence_ids": [passages[0]["evidence_id"]],
                }
            ],
        }
    return ProviderResponse(
        status=ProviderStatus.COMPLETED,
        output_text=json.dumps(output, separators=(",", ":"), sort_keys=True),
        model_id="deterministic-context-fixture-v1",
        attempted_calls=1,
        elapsed_ms=0,
        usage_tokens=None,
    )
