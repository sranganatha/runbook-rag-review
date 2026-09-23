from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Sequence

from runbook_rag_review.answer import generate_answer
from runbook_rag_review.contracts import ContractError, validate_fixture_set
from runbook_rag_review.evaluate import run_evaluation
from runbook_rag_review.index import build_index
from runbook_rag_review.provider import fixture_response
from runbook_rag_review.retrieve import retrieve
from runbook_rag_review.review import load_reviewer_ids, record_review, save_run_snapshot


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ragreview")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest", help="build the local fixture index")
    ingest.add_argument("--index", type=Path, required=True)
    ask = commands.add_parser("ask", help="ask using deterministic fixture generation")
    ask.add_argument("--index", type=Path, required=True)
    ask.add_argument("--store", type=Path, required=True)
    ask.add_argument("--run-id", required=True)
    ask.add_argument("--caller-id", required=True)
    ask.add_argument("--as-of", required=True)
    ask.add_argument("--question", required=True)
    ask.add_argument("--limit", type=int, default=5)
    review = commands.add_parser("review", help="record a review for an explicit run")
    review.add_argument("--store", type=Path, required=True)
    review.add_argument("--run-id", required=True)
    review.add_argument("--answer-version", type=int, required=True)
    review.add_argument("--reviewer-id", required=True)
    review.add_argument("--decision", choices=("accept", "reject", "correct"), required=True)
    review.add_argument("--rationale", required=True)
    review.add_argument("--corrected-claim", action="append", default=[])
    review.add_argument("--corrected-evidence-id", action="append", default=[])
    evaluate = commands.add_parser("evaluate", help="write the offline evaluation report")
    evaluate.add_argument("--output-dir", type=Path, default=Path("artifacts"))
    evaluate.add_argument("--k", type=int, default=5)
    args = parser.parse_args(argv)

    fixture_dir = Path(__file__).parents[1] / "fixtures"
    try:
        if args.command == "ingest":
            document_records = json.loads((fixture_dir / "documents.json").read_bytes())
            question_records = json.loads((fixture_dir / "questions.json").read_bytes())
            documents, _ = validate_fixture_set(document_records, question_records)
            digest = build_index(args.index, documents)
            print(
                json.dumps(
                    {
                        "documents": len(documents),
                        "index": str(args.index),
                        "index_digest": digest,
                    },
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "ask":
            authorized_scope = _caller_scope(
                fixture_dir / "callers.json", args.caller_id
            )
            try:
                as_of = date.fromisoformat(args.as_of)
            except ValueError as error:
                raise ContractError(
                    "invalid_as_of", "as_of must be an ISO date"
                ) from error
            retrieval = retrieve(
                args.index,
                args.question,
                authorized_scope,
                as_of,
                limit=args.limit,
            )
            answer = generate_answer(
                args.run_id,
                args.question,
                retrieval,
                fixture_response,
                generation_mode="fixture",
            )
            snapshot = save_run_snapshot(
                args.store, args.question, retrieval, answer
            )
            print(json.dumps(snapshot, sort_keys=True))
            return 0
        if args.command == "evaluate":
            report = run_evaluation(fixture_dir, args.output_dir, k=args.k)
            print(
                json.dumps(
                    {
                        "configurations": list(report["configurations"]),
                        "execution_mode": report["execution_mode"],
                        "output_dir": str(args.output_dir),
                    },
                    sort_keys=True,
                )
            )
            return 0

        reviewer_fixture = fixture_dir / "reviewers.json"
        stored_review = record_review(
            args.store,
            {
                "answer_run_id": args.run_id,
                "answer_version": args.answer_version,
                "reviewer_id": args.reviewer_id,
                "decision": args.decision,
                "rationale": args.rationale,
                "corrected_claims": args.corrected_claim,
                "corrected_evidence_ids": args.corrected_evidence_id,
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
            },
            load_reviewer_ids(reviewer_fixture),
        )
    except ContractError as error:
        print(json.dumps({"error": error.code, "message": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps(stored_review, sort_keys=True))
    return 0


def _caller_scope(path: Path, caller_id: str) -> str:
    records = json.loads(path.read_bytes())
    if not isinstance(records, list):
        raise ContractError("invalid_caller_fixture", "callers must be a list")
    callers: dict[str, str] = {}
    for record in records:
        if not isinstance(record, dict) or set(record) != {
            "caller_id",
            "authorized_scope",
        }:
            raise ContractError("invalid_caller_fixture", "caller fields are invalid")
        fixture_id = record["caller_id"]
        scope = record["authorized_scope"]
        if (
            not isinstance(fixture_id, str)
            or not fixture_id.strip()
            or not isinstance(scope, str)
            or not scope.strip()
            or fixture_id in callers
        ):
            raise ContractError("invalid_caller_fixture", "caller values are invalid")
        callers[fixture_id] = scope
    try:
        return callers[caller_id]
    except KeyError as error:
        raise ContractError("unknown_caller", caller_id) from error


if __name__ == "__main__":
    raise SystemExit(main())
