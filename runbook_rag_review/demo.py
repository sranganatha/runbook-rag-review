from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path
from typing import Any

from runbook_rag_review.answer import Answer, Claim, generate_answer
from runbook_rag_review.contracts import AnswerStatus, ContractError, validate_fixture_set
from runbook_rag_review.evaluate import evaluate_answer
from runbook_rag_review.index import build_index
from runbook_rag_review.provider import fixture_response
from runbook_rag_review.retrieve import RetrievalResult, retrieve
from runbook_rag_review.review import export_feedback, record_review, save_run_snapshot

REVIEWED_AT = "2026-09-04T12:00:00+00:00"


def run_demo(fixture_dir: Path, output_dir: Path) -> dict[str, Any]:
    document_records = json.loads((fixture_dir / "documents.json").read_bytes())
    question_records = json.loads((fixture_dir / "questions.json").read_bytes())
    documents, labels = validate_fixture_set(document_records, question_records)
    labels_by_id = {label.case_id: label for label in labels}

    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_root = Path(temporary_directory)
        first_index = temporary_root / "first.db"
        second_index = temporary_root / "second.db"
        first_digest = build_index(first_index, documents)
        second_digest = build_index(second_index, documents)

        supported_label = labels_by_id["holdout-06-budget-thresholds"]
        supported_retrieval = retrieve(
            first_index,
            supported_label.question,
            supported_label.authorized_scope,
            supported_label.as_of,
        )
        supported_answer = generate_answer(
            "demo-supported",
            supported_label.question,
            supported_retrieval,
            fixture_response,
            generation_mode="fixture",
        )
        replay_retrieval = retrieve(
            second_index,
            supported_label.question,
            supported_label.authorized_scope,
            supported_label.as_of,
        )
        replay_answer = generate_answer(
            "demo-replay",
            supported_label.question,
            replay_retrieval,
            fixture_response,
            generation_mode="fixture",
        )

        store_dir = temporary_root / "review-store"
        save_run_snapshot(
            store_dir,
            supported_label.question,
            supported_retrieval,
            supported_answer,
        )
        evidence_id = supported_retrieval.hits[0].chunk_id
        correction = record_review(
            store_dir,
            {
                "answer_run_id": supported_answer.run_id,
                "answer_version": 1,
                "reviewer_id": "reviewer-fixture-1",
                "decision": "correct",
                "rationale": "Clarify the answer while retaining captured evidence.",
                "corrected_claims": [supported_retrieval.hits[0].text],
                "corrected_evidence_ids": [evidence_id],
                "reviewed_at": REVIEWED_AT,
            },
            {"reviewer-fixture-1"},
        )

        stale_as_of = date(2026, 1, 15)
        current_retrieval = retrieve(
            first_index,
            "tagging exception report",
            "finops",
            stale_as_of,
        )
        obsolete_tag_versions = sorted(
            document.version
            for document in documents
            if document.document_id == "tagging-standard"
            and document.effective_to is not None
            and document.effective_to < stale_as_of
        )
        current_tag_versions = sorted(
            {
                hit.document_version
                for hit in current_retrieval.hits
                if hit.document_id == "tagging-standard"
            }
        )

        unsupported_retrieval = retrieve(
            first_index,
            "quasarzebrafish",
            "finops",
            date(2026, 1, 15),
        )
        unsupported_answer = generate_answer(
            "demo-unsupported",
            "quasarzebrafish",
            unsupported_retrieval,
            fixture_response,
            generation_mode="fixture",
        )

        irrelevant_answer = replace(
            supported_answer,
            run_id="demo-irrelevant-citation",
            claims=(
                Claim(
                    text="Delete every cloud account immediately.",
                    evidence_ids=(evidence_id,),
                ),
            ),
        )
        irrelevant_evaluation = evaluate_answer(
            supported_label, supported_retrieval, irrelevant_answer
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        feedback = export_feedback(store_dir, output_dir / "feedback.json")

    checks = {
        "index_rebuild_stable": first_digest == second_digest,
        "fixture_replay_stable": (
            _normalized_retrieval(supported_retrieval)
            == _normalized_retrieval(replay_retrieval)
            and _normalized_answer(supported_answer)
            == _normalized_answer(replay_answer)
        ),
        "supported_answer": supported_answer.status is AnswerStatus.ANSWERED,
        "stale_source_excluded": (
            bool(obsolete_tag_versions) and current_tag_versions == [2]
        ),
        "unsupported_question_abstained": (
            unsupported_answer.status is AnswerStatus.ABSTAINED
        ),
        "review_correction_exported": (
            correction["resulting_answer_version"] == 2
            and len(feedback["runs"]) == 1
            and len(feedback["runs"][0]["reviews"]) == 1
        ),
        "irrelevant_citation_rejected": (
            irrelevant_evaluation["valid_citations"] == {
                "numerator": 1,
                "denominator": 1,
            }
            and irrelevant_evaluation["supported_claims"] == {
                "numerator": 0,
                "denominator": 1,
            }
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ContractError("demo_invariant_failed", ",".join(failed))
    report = {
        "schema_version": 1,
        "execution_mode": "deterministic_fixture",
        "checks": checks,
        "index_digest": first_digest,
        "supported_run_id": supported_answer.run_id,
        "unsupported_status": unsupported_answer.status.value,
        "obsolete_tag_versions": obsolete_tag_versions,
        "retrieved_current_tag_versions": current_tag_versions,
        "review_version": correction["review_version"],
        "irrelevant_citation": irrelevant_evaluation,
    }
    (output_dir / "demo.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (output_dir / "demo.md").write_text(
        _markdown(report), encoding="utf-8", newline="\n"
    )
    return report


def _normalized_retrieval(retrieval: RetrievalResult) -> dict[str, Any]:
    return {
        "query": retrieval.query,
        "authorized_scope": retrieval.authorized_scope,
        "as_of": retrieval.as_of.isoformat(),
        "index_digest": retrieval.index_digest,
        "hits": [asdict(hit) for hit in retrieval.hits],
    }


def _normalized_answer(answer: Answer) -> dict[str, Any]:
    normalized = asdict(answer)
    normalized.pop("run_id")
    return normalized


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Offline Demo",
        "",
        "Execution mode: `deterministic_fixture`. No network or model service is used.",
        "",
        "| Check | Result |",
        "|---|---|",
    ]
    lines.extend(
        f"| `{name}` | {'pass' if passed else 'fail'} |"
        for name, passed in report["checks"].items()
    )
    lines.extend(
        [
            "",
            f"Index digest: `{report['index_digest']}`.",
            "",
            "The feedback export preserves the reviewed run, exact evidence, answer, "
            "snapshot digest, and append-only correction.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts")
    fixture_dir = Path(__file__).parents[1] / "fixtures"
    try:
        report = run_demo(fixture_dir, output_dir)
    except ContractError as error:
        print(json.dumps({"error": error.code, "message": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps({"checks": report["checks"], "output_dir": str(output_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
