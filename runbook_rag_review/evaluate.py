from __future__ import annotations

import json
import sqlite3
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from runbook_rag_review.answer import Answer, generate_answer
from runbook_rag_review.contracts import QuestionLabel, validate_fixture_set
from runbook_rag_review.index import build_index
from runbook_rag_review.provider import fixture_response
from runbook_rag_review.retrieve import (
    RetrievalResult,
    _match_query,
    retrieve,
    retrieve_scope_only_baseline,
)

RetrievalFunction = Callable[..., RetrievalResult]


def run_evaluation(fixture_dir: Path, output_dir: Path, *, k: int = 5) -> dict[str, Any]:
    document_records = json.loads((fixture_dir / "documents.json").read_bytes())
    question_records = json.loads((fixture_dir / "questions.json").read_bytes())
    documents, labels = validate_fixture_set(document_records, question_records)
    with tempfile.TemporaryDirectory() as temporary_directory:
        index_path = Path(temporary_directory) / "runbooks.db"
        index_digest = build_index(index_path, documents)
        configurations = {
            "scope_only_then_applicability": retrieve_scope_only_baseline,
            "scope_and_version_before_ranking": retrieve,
        }
        results = {
            name: _evaluate_configuration(index_path, labels, function, name, k)
            for name, function in configurations.items()
        }
        negative_control = _unscoped_negative_control(index_path, labels, k)

    report = {
        "schema_version": 1,
        "execution_mode": "deterministic_fixture",
        "index_digest": index_digest,
        "k": k,
        "development_tuning": "none",
        "configurations": results,
        "unscoped_negative_control": negative_control,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "evaluation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (output_dir / "evaluation.md").write_text(
        _markdown(report), encoding="utf-8", newline="\n"
    )
    return report


def evaluate_answer(
    label: QuestionLabel, retrieval: RetrievalResult, answer: Answer
) -> dict[str, Any]:
    evidence_matches: list[set[str]] = []
    for expected in label.relevant_evidence:
        evidence_matches.append(
            {
                hit.chunk_id
                for hit in retrieval.hits
                if hit.document_id == expected.document_id
                and hit.document_version == expected.version
                and expected.exact_text in hit.text
            }
        )
    retrieved_evidence = sum(bool(matches) for matches in evidence_matches)
    available_ids = {hit.chunk_id for hit in retrieval.hits}
    cited_ids = [
        evidence_id for claim in answer.claims for evidence_id in claim.evidence_ids
    ]
    valid_citations = sum(evidence_id in available_ids for evidence_id in cited_ids)
    hits_by_id = {hit.chunk_id: hit for hit in retrieval.hits}
    supported_claims = sum(
        any(
            claim.text in hits_by_id[evidence_id].text
            for evidence_id in claim.evidence_ids
            if evidence_id in hits_by_id
        )
        for claim in answer.claims
    )
    all_labeled_evidence_cited = all(
        matches and matches.intersection(cited_ids) for matches in evidence_matches
    )
    required_facts_supported = (
        len(label.required_facts)
        if supported_claims == len(answer.claims) and all_labeled_evidence_cited
        else 0
    )
    stale_chunks = sum(
        hit.effective_from > label.as_of.isoformat()
        or (hit.effective_to is not None and hit.effective_to < label.as_of.isoformat())
        for hit in retrieval.hits
    )
    unauthorized_chunks = sum(
        hit.team_scope != label.authorized_scope for hit in retrieval.hits
    )
    return {
        "case_id": label.case_id,
        "split": label.split,
        "category": label.category,
        "expected_status": label.expected_status.value,
        "actual_status": answer.status.value,
        "status_match": answer.status is label.expected_status,
        "retrieved_chunk_ids": [hit.chunk_id for hit in retrieval.hits],
        "cited_evidence_ids": cited_ids,
        "retrieval_recall": {
            "numerator": retrieved_evidence,
            "denominator": len(label.relevant_evidence),
        },
        "required_facts_supported": {
            "numerator": required_facts_supported,
            "denominator": len(label.required_facts),
        },
        "valid_citations": {
            "numerator": valid_citations,
            "denominator": len(cited_ids),
        },
        "supported_claims": {
            "numerator": supported_claims,
            "denominator": len(answer.claims),
        },
        "false_answer": (
            label.expected_status.value == "abstained"
            and answer.status.value != "abstained"
        ),
        "stale_chunks": stale_chunks,
        "unauthorized_chunks": unauthorized_chunks,
    }


def _evaluate_configuration(
    index_path: Path,
    labels: list[QuestionLabel],
    retrieval_function: RetrievalFunction,
    configuration_name: str,
    k: int,
) -> dict[str, Any]:
    cases = []
    for label in labels:
        retrieval = retrieval_function(
            index_path,
            label.question,
            label.authorized_scope,
            label.as_of,
            limit=k,
        )
        answer = generate_answer(
            f"evaluation:{configuration_name}:{label.case_id}",
            label.question,
            retrieval,
            fixture_response,
            generation_mode="fixture",
        )
        cases.append(evaluate_answer(label, retrieval, answer))
    return {
        "provider_calls": len(cases),
        "splits": {
            split: _summarize([case for case in cases if case["split"] == split])
            for split in ("development", "holdout")
        },
        "cases": cases,
    }


def _summarize(cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "cases": len(cases),
        "retrieval_recall": _sum_fraction(cases, "retrieval_recall"),
        "required_facts_supported": _sum_fraction(
            cases, "required_facts_supported"
        ),
        "valid_citations": _sum_fraction(cases, "valid_citations"),
        "supported_claims": _sum_fraction(cases, "supported_claims"),
        "status_matches": {
            "numerator": sum(case["status_match"] for case in cases),
            "denominator": len(cases),
        },
        "false_answers": {
            "numerator": sum(case["false_answer"] for case in cases),
            "denominator": sum(
                case["expected_status"] == "abstained" for case in cases
            ),
        },
        "stale_chunks": sum(case["stale_chunks"] for case in cases),
        "unauthorized_chunks": sum(case["unauthorized_chunks"] for case in cases),
    }


def _sum_fraction(cases: list[dict[str, Any]], field: str) -> dict[str, int]:
    return {
        part: sum(case[field][part] for case in cases)
        for part in ("numerator", "denominator")
    }


def _unscoped_negative_control(
    index_path: Path, labels: list[QuestionLabel], k: int
) -> dict[str, Any]:
    connection = sqlite3.connect(f"{index_path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        cases = []
        for label in labels:
            rows = connection.execute(
                """
                SELECT chunks.chunk_id, chunks.team_scope, chunks.effective_from,
                       chunks.effective_to
                FROM chunks_fts
                JOIN chunks ON chunks.rowid = chunks_fts.rowid
                WHERE chunks_fts MATCH ?
                ORDER BY bm25(chunks_fts), chunks.chunk_id
                LIMIT ?
                """,
                (_match_query(label.question), k),
            ).fetchall()
            cases.append(
                {
                    "case_id": label.case_id,
                    "unauthorized_chunk_ids": [
                        row[0] for row in rows if row[1] != label.authorized_scope
                    ],
                    "stale_chunk_ids": [
                        row[0]
                        for row in rows
                        if row[2] > label.as_of.isoformat()
                        or (row[3] is not None and row[3] < label.as_of.isoformat())
                    ],
                }
            )
    finally:
        connection.close()
    return {
        "mode": "offline_only_no_generation",
        "provider_calls": 0,
        "unauthorized_chunks": sum(
            len(case["unauthorized_chunk_ids"]) for case in cases
        ),
        "stale_chunks": sum(len(case["stale_chunk_ids"]) for case in cases),
        "cases": cases,
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Offline Evaluation Report",
        "",
        "Execution mode: `deterministic_fixture`. This is not real-model quality evidence.",
        "",
        f"Fixed retrieval depth: `k={report['k']}`. Development tuning performed: none.",
        "",
        "## Summary",
        "",
        "| Configuration | Split | Cases | Retrieval recall | Required facts | "
        "Citation IDs | Claims | Status | False answers | Scope | Stale |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for configuration_name, configuration in report["configurations"].items():
        for split, metrics in configuration["splits"].items():
            lines.append(
                f"| `{configuration_name}` | {split} | {metrics['cases']} | "
                f"{_ratio(metrics['retrieval_recall'])} | "
                f"{_ratio(metrics['required_facts_supported'])} | "
                f"{_ratio(metrics['valid_citations'])} | "
                f"{_ratio(metrics['supported_claims'])} | "
                f"{_ratio(metrics['status_matches'])} | "
                f"{_ratio(metrics['false_answers'])} | "
                f"{metrics['unauthorized_chunks']} | {metrics['stale_chunks']} |"
            )
    negative = report["unscoped_negative_control"]
    lines.extend(
        [
            "",
            "## Isolated negative control",
            "",
            "The unscoped control is retrieval-only and made zero provider calls.",
            "",
            f"Unauthorized chunks: {negative['unauthorized_chunks']}. "
            f"Stale chunks: {negative['stale_chunks']}.",
            "",
            "## Per-case results",
            "",
            "| Configuration | Split | Case | Expected | Actual | Recall | Facts | "
            "Citation IDs | Claims | False answer |",
            "|---|---|---|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for configuration_name, configuration in report["configurations"].items():
        for case in configuration["cases"]:
            lines.append(
                f"| `{configuration_name}` | {case['split']} | `{case['case_id']}` | "
                f"{case['expected_status']} | {case['actual_status']} | "
                f"{_ratio(case['retrieval_recall'])} | "
                f"{_ratio(case['required_facts_supported'])} | "
                f"{_ratio(case['valid_citations'])} | "
                f"{_ratio(case['supported_claims'])} | "
                f"{'yes' if case['false_answer'] else 'no'} |"
            )
    return "\n".join(lines) + "\n"


def _ratio(value: dict[str, int]) -> str:
    return f"{value['numerator']}/{value['denominator']}"
