from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Any

from runbook_rag_review.answer import Answer
from runbook_rag_review.contracts import ContractError, Review, ReviewDecision
from runbook_rag_review.retrieve import RetrievalResult

RUN_SCHEMA_VERSION = 1
REVIEW_SCHEMA_VERSION = 1


def save_run_snapshot(
    store_dir: Path,
    question: str,
    retrieval: RetrievalResult,
    answer: Answer,
) -> dict[str, Any]:
    if not isinstance(question, str) or not question.strip():
        raise ContractError("invalid_question", "question must not be empty")
    retrieved_ids = tuple(hit.chunk_id for hit in retrieval.hits)
    if answer.context_chunk_ids != retrieved_ids:
        raise ContractError(
            "answer_context_mismatch", "answer does not match retrieved evidence"
        )
    cited_ids = {
        evidence_id for claim in answer.claims for evidence_id in claim.evidence_ids
    }
    if not cited_ids <= set(retrieved_ids):
        raise ContractError("unknown_evidence_id", "answer cites unavailable evidence")

    snapshot = {
        "schema_version": RUN_SCHEMA_VERSION,
        "run_id": answer.run_id,
        "answer_version": 1,
        "question": question,
        "retrieval": {
            "query": retrieval.query,
            "authorized_scope": retrieval.authorized_scope,
            "as_of": retrieval.as_of.isoformat(),
            "index_digest": retrieval.index_digest,
            "evidence": [
                {
                    "chunk_id": hit.chunk_id,
                    "document_id": hit.document_id,
                    "document_version": hit.document_version,
                    "start_offset": hit.start_offset,
                    "end_offset": hit.end_offset,
                    "text": hit.text,
                    "text_sha256": sha256(hit.text.encode()).hexdigest(),
                    "score": hit.score,
                    "effective_from": hit.effective_from,
                    "effective_to": hit.effective_to,
                    "team_scope": hit.team_scope,
                }
                for hit in retrieval.hits
            ],
        },
        "answer": {
            "status": answer.status.value,
            "claims": [
                {"text": claim.text, "evidence_ids": list(claim.evidence_ids)}
                for claim in answer.claims
            ],
            "reason": answer.reason,
            "generation_mode": answer.generation_mode,
            "model_id": answer.model_id,
            "attempted_calls": answer.attempted_calls,
            "elapsed_ms": answer.elapsed_ms,
            "usage_tokens": answer.usage_tokens,
            "limits": asdict(answer.limits),
        },
    }
    snapshot["snapshot_sha256"] = _digest(snapshot)
    try:
        _write_new_json(_run_path(store_dir, answer.run_id), snapshot)
    except FileExistsError as error:
        raise ContractError("run_exists", answer.run_id) from error
    return snapshot


def load_run_snapshot(store_dir: Path, run_id: str) -> dict[str, Any]:
    path = _run_path(store_dir, run_id)
    if not path.is_file():
        raise ContractError("run_not_found", run_id)
    snapshot = _read_hashed_json(path, "snapshot_sha256", "run_snapshot_tampered")
    if snapshot.get("schema_version") != RUN_SCHEMA_VERSION:
        raise ContractError("unsupported_run_schema", str(snapshot.get("schema_version")))
    if snapshot.get("run_id") != run_id:
        raise ContractError("run_id_mismatch", run_id)
    return snapshot


def record_review(
    store_dir: Path,
    review_record: dict[str, Any],
    allowed_reviewer_ids: set[str],
) -> dict[str, Any]:
    review = Review.from_dict(review_record)
    if review.reviewer_id not in allowed_reviewer_ids:
        raise ContractError("unknown_reviewer", review.reviewer_id)
    snapshot = load_run_snapshot(store_dir, review.answer_run_id)
    history = load_review_history(store_dir, review.answer_run_id)
    current_answer_version = (
        history[-1]["resulting_answer_version"]
        if history
        else snapshot["answer_version"]
    )
    if review.answer_version != current_answer_version:
        raise ContractError(
            "stale_answer_version",
            f"expected {current_answer_version}, received {review.answer_version}",
        )
    captured_ids = {
        evidence["chunk_id"] for evidence in snapshot["retrieval"]["evidence"]
    }
    if not set(review.corrected_evidence_ids) <= captured_ids:
        raise ContractError(
            "unknown_corrected_evidence", "correction cites uncaptured evidence"
        )

    review_version = len(history) + 1
    resulting_answer_version = current_answer_version + (
        1 if review.decision is ReviewDecision.CORRECT else 0
    )
    stored_review = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "review_version": review_version,
        "run_id": review.answer_run_id,
        "run_snapshot_sha256": snapshot["snapshot_sha256"],
        "answer_version": review.answer_version,
        "resulting_answer_version": resulting_answer_version,
        "reviewer_id": review.reviewer_id,
        "decision": review.decision.value,
        "rationale": review.rationale,
        "corrected_claims": list(review.corrected_claims),
        "corrected_evidence_ids": list(review.corrected_evidence_ids),
        "reviewed_at": review.reviewed_at.isoformat(),
    }
    stored_review["review_sha256"] = _digest(stored_review)
    review_path = _review_dir(store_dir, review.answer_run_id) / f"{review_version:06}.json"
    try:
        _write_new_json(review_path, stored_review)
    except FileExistsError as error:
        raise ContractError("review_version_conflict", str(review_version)) from error
    return stored_review


def load_review_history(store_dir: Path, run_id: str) -> list[dict[str, Any]]:
    snapshot = load_run_snapshot(store_dir, run_id)
    review_dir = _review_dir(store_dir, run_id)
    if not review_dir.is_dir():
        return []
    history = [
        _read_hashed_json(path, "review_sha256", "review_record_tampered")
        for path in sorted(review_dir.glob("*.json"))
    ]
    current_answer_version = snapshot["answer_version"]
    for expected_version, record in enumerate(history, start=1):
        if record.get("review_version") != expected_version:
            raise ContractError("review_history_gap", str(expected_version))
        if record.get("run_id") != run_id or record.get(
            "run_snapshot_sha256"
        ) != snapshot.get("snapshot_sha256"):
            raise ContractError("review_run_mismatch", str(expected_version))
        if record.get("answer_version") != current_answer_version:
            raise ContractError("review_answer_version_mismatch", str(expected_version))
        current_answer_version = record.get("resulting_answer_version")
        if not isinstance(current_answer_version, int) or current_answer_version < 1:
            raise ContractError("invalid_review_version", str(expected_version))
    return history


def load_reviewer_ids(path: Path) -> set[str]:
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError("invalid_reviewer_fixture", str(path)) from error
    if (
        not isinstance(records, list)
        or not records
        or any(not isinstance(record, str) or not record.strip() for record in records)
        or len(records) != len(set(records))
    ):
        raise ContractError("invalid_reviewer_fixture", str(path))
    return set(records)


def _run_key(run_id: str) -> str:
    if not isinstance(run_id, str) or not run_id.strip():
        raise ContractError("invalid_run_id", "run_id must not be empty")
    return sha256(run_id.encode()).hexdigest()


def _run_path(store_dir: Path, run_id: str) -> Path:
    return store_dir / "runs" / f"{_run_key(run_id)}.json"


def _review_dir(store_dir: Path, run_id: str) -> Path:
    return store_dir / "reviews" / _run_key(run_id)


def _digest(record: dict[str, Any]) -> str:
    return sha256(
        json.dumps(
            record, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
    ).hexdigest()


def _read_hashed_json(path: Path, digest_field: str, error_code: str) -> dict[str, Any]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(error_code, str(path)) from error
    if not isinstance(record, dict):
        raise ContractError(error_code, str(path))
    expected_digest = record.pop(digest_field, None)
    actual_digest = _digest(record)
    record[digest_field] = expected_digest
    if expected_digest != actual_digest:
        raise ContractError(error_code, str(path))
    return record


def _write_new_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=".write-")
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            json.dump(record, output, ensure_ascii=False, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
