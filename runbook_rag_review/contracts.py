from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any


class ContractError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class AnswerStatus(StrEnum):
    ANSWERED = "answered"
    ABSTAINED = "abstained"
    CONFLICT = "conflict"


class ReviewDecision(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    CORRECT = "correct"


@dataclass(frozen=True)
class Review:
    answer_run_id: str
    answer_version: int
    reviewer_id: str
    decision: ReviewDecision
    rationale: str
    corrected_claims: tuple[str, ...]
    corrected_evidence_ids: tuple[str, ...]
    reviewed_at: datetime

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> Review:
        answer_version = record.get("answer_version")
        if (
            not isinstance(answer_version, int)
            or isinstance(answer_version, bool)
            or answer_version < 1
        ):
            raise ContractError("invalid_answer_version", "answer_version must be positive")
        try:
            decision = ReviewDecision(_required_text(record, "decision"))
        except ValueError as error:
            raise ContractError("invalid_review_decision", "unknown decision") from error
        corrected_claims = _text_list(record, "corrected_claims")
        corrected_evidence_ids = _text_list(record, "corrected_evidence_ids")
        if decision is ReviewDecision.CORRECT and (
            not corrected_claims or not corrected_evidence_ids
        ):
            raise ContractError(
                "incomplete_correction", "correct requires claims and evidence IDs"
            )
        if decision is not ReviewDecision.CORRECT and (corrected_claims or corrected_evidence_ids):
            raise ContractError(
                "unexpected_correction", "only correct may include corrected content"
            )
        try:
            reviewed_at = datetime.fromisoformat(_required_text(record, "reviewed_at"))
        except ValueError as error:
            raise ContractError("invalid_timestamp", "reviewed_at must be ISO 8601") from error
        if reviewed_at.tzinfo is None:
            raise ContractError("invalid_timestamp", "reviewed_at must include an offset")
        return cls(
            answer_run_id=_required_text(record, "answer_run_id"),
            answer_version=answer_version,
            reviewer_id=_required_text(record, "reviewer_id"),
            decision=decision,
            rationale=_required_text(record, "rationale"),
            corrected_claims=corrected_claims,
            corrected_evidence_ids=corrected_evidence_ids,
            reviewed_at=reviewed_at,
        )


def _required_text(record: dict[str, Any], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ContractError("invalid_text", f"{field} must be a non-empty string")
    return value


def _date(record: dict[str, Any], field: str, *, optional: bool = False) -> date | None:
    value = record.get(field)
    if value is None and optional:
        return None
    try:
        return date.fromisoformat(_required_text(record, field))
    except ValueError as error:
        raise ContractError("invalid_date", f"{field} must be an ISO date") from error


@dataclass(frozen=True)
class Document:
    document_id: str
    version: int
    title: str
    effective_from: date
    effective_to: date | None
    team_scope: str
    source_text: str
    source_text_sha256: str

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> Document:
        if record.get("original_synthetic_content") is not True:
            raise ContractError("not_declared_synthetic", "document must declare original content")
        version = record.get("version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ContractError("invalid_version", "version must be a positive integer")
        effective_from = _date(record, "effective_from")
        effective_to = _date(record, "effective_to", optional=True)
        assert effective_from is not None
        if effective_to is not None and effective_to < effective_from:
            raise ContractError("invalid_effective_period", "effective_to precedes effective_from")
        source_text = _required_text(record, "source_text")
        digest = _required_text(record, "source_text_sha256")
        if sha256(source_text.encode()).hexdigest() != digest:
            raise ContractError("digest_mismatch", "source_text_sha256 does not match source_text")
        return cls(
            document_id=_required_text(record, "document_id"),
            version=version,
            title=_required_text(record, "title"),
            effective_from=effective_from,
            effective_to=effective_to,
            team_scope=_required_text(record, "team_scope"),
            source_text=source_text,
            source_text_sha256=digest,
        )


@dataclass(frozen=True)
class EvidenceLabel:
    document_id: str
    version: int
    exact_text: str


@dataclass(frozen=True)
class QuestionLabel:
    case_id: str
    split: str
    category: str
    question: str
    authorized_scope: str
    as_of: date
    expected_status: AnswerStatus
    required_facts: tuple[str, ...]
    critical_constraints: tuple[str, ...]
    relevant_evidence: tuple[EvidenceLabel, ...]

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> QuestionLabel:
        split = _required_text(record, "split")
        if split not in {"development", "holdout"}:
            raise ContractError("invalid_split", "split must be development or holdout")
        try:
            status = AnswerStatus(_required_text(record, "expected_status"))
        except ValueError as error:
            raise ContractError("invalid_answer_status", "unknown expected_status") from error
        required_facts = _text_list(record, "required_facts")
        constraints = _text_list(record, "critical_constraints")
        raw_evidence = record.get("relevant_evidence")
        if not isinstance(raw_evidence, list):
            raise ContractError("invalid_evidence", "relevant_evidence must be a list")
        evidence = tuple(
            EvidenceLabel(
                document_id=_required_text(item, "document_id"),
                version=item.get("version"),
                exact_text=_required_text(item, "exact_text"),
            )
            for item in raw_evidence
            if isinstance(item, dict)
        )
        if len(evidence) != len(raw_evidence):
            raise ContractError("invalid_evidence", "each evidence label must be an object")
        if any(
            not isinstance(item.version, int)
            or isinstance(item.version, bool)
            or item.version < 1
            for item in evidence
        ):
            raise ContractError(
                "invalid_evidence_version", "evidence version must be a positive integer"
            )
        if status is AnswerStatus.ABSTAINED and (required_facts or evidence):
            raise ContractError(
                "invalid_abstention_label", "abstention cannot require facts or evidence"
            )
        if status is not AnswerStatus.ABSTAINED and (not required_facts or not evidence):
            raise ContractError(
                "missing_expected_support",
                "answered and conflict labels require facts and evidence",
            )
        if status is AnswerStatus.CONFLICT and len(evidence) < 2:
            raise ContractError(
                "missing_conflict_evidence", "conflict requires at least two passages"
            )
        as_of = _date(record, "as_of")
        assert as_of is not None
        return cls(
            case_id=_required_text(record, "case_id"),
            split=split,
            category=_required_text(record, "category"),
            question=_required_text(record, "question"),
            authorized_scope=_required_text(record, "authorized_scope"),
            as_of=as_of,
            expected_status=status,
            required_facts=required_facts,
            critical_constraints=constraints,
            relevant_evidence=evidence,
        )


def _text_list(record: dict[str, Any], field: str) -> tuple[str, ...]:
    value = record.get(field)
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ContractError("invalid_text_list", f"{field} must be a list of non-empty strings")
    return tuple(value)


def validate_fixture_set(
    document_records: object, question_records: object
) -> tuple[list[Document], list[QuestionLabel]]:
    if not isinstance(document_records, list):
        raise ContractError("invalid_document_set", "documents must be a list")
    if not isinstance(question_records, list):
        raise ContractError("invalid_question_set", "questions must be a list")
    if any(not isinstance(record, dict) for record in document_records):
        raise ContractError("invalid_document_record", "each document must be an object")
    if any(not isinstance(record, dict) for record in question_records):
        raise ContractError("invalid_question_record", "each question must be an object")
    documents = [Document.from_dict(record) for record in document_records]
    questions = [QuestionLabel.from_dict(record) for record in question_records]
    _unique(
        ((document.document_id, document.version) for document in documents),
        "duplicate_document",
    )
    _unique(((question.case_id,) for question in questions), "duplicate_case")
    _validate_version_periods(documents)

    documents_by_id = {
        (document.document_id, document.version): document for document in documents
    }
    for question in questions:
        for evidence in question.relevant_evidence:
            document = documents_by_id.get((evidence.document_id, evidence.version))
            if document is None:
                raise ContractError(
                    "unknown_evidence_document",
                    f"{evidence.document_id}@{evidence.version}",
                )
            if evidence.exact_text not in document.source_text:
                raise ContractError("evidence_text_mismatch", question.case_id)
            if document.team_scope != question.authorized_scope:
                raise ContractError("evidence_scope_mismatch", question.case_id)
            if question.as_of < document.effective_from or (
                document.effective_to is not None and question.as_of > document.effective_to
            ):
                raise ContractError("evidence_date_mismatch", question.case_id)

    if len(documents) not in range(10, 16):
        raise ContractError("invalid_document_count", "expected 10 to 15 documents")
    if len(questions) != 20:
        raise ContractError("invalid_question_count", "expected exactly 20 questions")
    split_counts = {
        split: sum(question.split == split for question in questions)
        for split in ("development", "holdout")
    }
    if split_counts != {"development": 8, "holdout": 12}:
        raise ContractError("invalid_split_counts", str(split_counts))
    required_categories = {
        "supported",
        "absent_evidence",
        "obsolete_guidance",
        "wrong_scope",
        "conflict",
        "injected_instruction",
    }
    categories = {question.category for question in questions}
    if not required_categories <= categories:
        raise ContractError("missing_case_category", str(sorted(required_categories - categories)))
    return documents, questions


def _unique(keys: Any, code: str) -> None:
    seen: set[tuple[Any, ...]] = set()
    for key in keys:
        if key in seen:
            raise ContractError(code, str(key))
        seen.add(key)


def _validate_version_periods(documents: list[Document]) -> None:
    by_id: dict[str, list[Document]] = {}
    for document in documents:
        by_id.setdefault(document.document_id, []).append(document)
    for versions in by_id.values():
        ordered = sorted(versions, key=lambda document: document.effective_from)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if previous.effective_to is None or previous.effective_to >= current.effective_from:
                raise ContractError("overlapping_versions", previous.document_id)
