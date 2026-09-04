from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from runbook_rag_review.contracts import AnswerStatus, ContractError
from runbook_rag_review.provider import ProviderResponse, ProviderStatus
from runbook_rag_review.retrieve import RetrievalResult


@dataclass(frozen=True)
class GenerationLimits:
    max_context_chars: int = 12_000
    max_output_chars: int = 4_000
    max_claims: int = 8
    max_evidence_per_claim: int = 5
    max_calls: int = 1

    def __post_init__(self) -> None:
        for field_name, field_value in self.__dict__.items():
            if (
                isinstance(field_value, bool)
                or not isinstance(field_value, int)
                or field_value < 1
            ):
                raise ContractError("invalid_generation_limit", field_name)


@dataclass(frozen=True)
class Claim:
    text: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class Answer:
    run_id: str
    status: AnswerStatus
    claims: tuple[Claim, ...]
    reason: str | None
    generation_mode: str
    model_id: str
    attempted_calls: int
    elapsed_ms: float
    usage_tokens: int | None
    context_chunk_ids: tuple[str, ...]
    limits: GenerationLimits


def generate_answer(
    run_id: str,
    question: str,
    retrieval: RetrievalResult,
    provider_call: Callable[[str], ProviderResponse],
    *,
    generation_mode: str,
    limits: GenerationLimits = GenerationLimits(),
) -> Answer:
    if not isinstance(run_id, str) or not run_id.strip():
        raise ContractError("invalid_run_id", "run_id must not be empty")
    if not isinstance(question, str) or not question.strip():
        raise ContractError("invalid_question", "question must not be empty")
    if not isinstance(generation_mode, str) or not generation_mode.strip():
        raise ContractError("invalid_generation_mode", "generation_mode must not be empty")
    _verify_retrieval(retrieval)
    context_json = json.dumps(
        {
            "question": question,
            "passages": [
                {"evidence_id": hit.chunk_id, "text": hit.text}
                for hit in retrieval.hits
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(context_json) > limits.max_context_chars:
        raise ContractError("context_budget_exceeded", "retrieval context is too large")
    try:
        response = provider_call(context_json)
    except Exception as error:
        raise ContractError("provider_transport_error", "provider call failed") from error
    if not isinstance(response, ProviderResponse):
        raise ContractError(
            "invalid_provider_response", "provider returned an invalid response"
        )
    return _validated_answer(
        run_id, retrieval, response, generation_mode=generation_mode, limits=limits
    )


def _verify_retrieval(retrieval: RetrievalResult) -> None:
    as_of = retrieval.as_of.isoformat()
    for hit in retrieval.hits:
        if hit.team_scope != retrieval.authorized_scope or hit.effective_from > as_of or (
            hit.effective_to is not None and hit.effective_to < as_of
        ):
            raise ContractError(
                "retrieval_filter_violation", "context contains an unauthorized chunk"
            )


def _validated_answer(
    run_id: str,
    retrieval: RetrievalResult,
    response: ProviderResponse,
    *,
    generation_mode: str,
    limits: GenerationLimits,
) -> Answer:
    if response.attempted_calls > limits.max_calls:
        raise ContractError("provider_call_budget_exceeded", "too many provider calls")
    if response.status is ProviderStatus.REFUSED:
        raise ContractError("provider_refused", "provider refused the request")
    if response.status is ProviderStatus.TRUNCATED:
        raise ContractError("provider_truncated", "provider output was truncated")
    assert response.output_text is not None
    if len(response.output_text) > limits.max_output_chars:
        raise ContractError("provider_output_too_large", "provider output exceeds budget")
    try:
        output = json.loads(response.output_text)
    except json.JSONDecodeError as error:
        raise ContractError("invalid_provider_json", "provider output is not JSON") from error
    if not isinstance(output, dict) or set(output) - {"status", "claims", "reason"}:
        raise ContractError("invalid_answer_schema", "provider output has unknown fields")
    try:
        status = AnswerStatus(output.get("status"))
    except ValueError as error:
        raise ContractError("invalid_answer_status", "provider status is unknown") from error
    claims = _claims(output.get("claims"), retrieval, limits)
    reason = output.get("reason")
    if reason is not None and (not isinstance(reason, str) or not reason.strip()):
        raise ContractError("invalid_answer_reason", "reason must be non-empty text")
    if status is AnswerStatus.ABSTAINED:
        if claims or reason is None:
            raise ContractError(
                "invalid_abstention", "abstention requires a reason and no claims"
            )
    elif not claims:
        raise ContractError("missing_answer_claims", "answer requires at least one claim")
    if status is AnswerStatus.CONFLICT and (
        len(claims) < 2
        or len(_cited_document_ids(claims, retrieval)) < 2
    ):
        raise ContractError(
            "invalid_conflict", "conflict requires two claims from different documents"
        )
    return Answer(
        run_id=run_id,
        status=status,
        claims=claims,
        reason=reason,
        generation_mode=generation_mode,
        model_id=response.model_id,
        attempted_calls=response.attempted_calls,
        elapsed_ms=response.elapsed_ms,
        usage_tokens=response.usage_tokens,
        context_chunk_ids=tuple(hit.chunk_id for hit in retrieval.hits),
        limits=limits,
    )


def _claims(
    raw_claims: object, retrieval: RetrievalResult, limits: GenerationLimits
) -> tuple[Claim, ...]:
    if not isinstance(raw_claims, list) or len(raw_claims) > limits.max_claims:
        raise ContractError("invalid_answer_claims", "claims must be a bounded list")
    allowed_ids = {hit.chunk_id for hit in retrieval.hits}
    claims: list[Claim] = []
    for raw_claim in raw_claims:
        if not isinstance(raw_claim, dict) or set(raw_claim) != {"text", "evidence_ids"}:
            raise ContractError("invalid_claim_schema", "claim fields are invalid")
        text = raw_claim["text"]
        evidence_ids = raw_claim["evidence_ids"]
        if not isinstance(text, str) or not text.strip():
            raise ContractError("invalid_claim_text", "claim text must not be empty")
        if (
            not isinstance(evidence_ids, list)
            or not evidence_ids
            or len(evidence_ids) > limits.max_evidence_per_claim
            or any(not isinstance(evidence_id, str) for evidence_id in evidence_ids)
            or len(evidence_ids) != len(set(evidence_ids))
        ):
            raise ContractError(
                "invalid_claim_evidence", "evidence IDs must be a bounded unique list"
            )
        if not set(evidence_ids) <= allowed_ids:
            raise ContractError("unknown_evidence_id", "claim cites unavailable evidence")
        claims.append(Claim(text=text, evidence_ids=tuple(evidence_ids)))
    return tuple(claims)


def _cited_document_ids(
    claims: tuple[Claim, ...], retrieval: RetrievalResult
) -> set[str]:
    cited_ids = {
        evidence_id for claim in claims for evidence_id in claim.evidence_ids
    }
    return {
        hit.document_id for hit in retrieval.hits if hit.chunk_id in cited_ids
    }
