from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from runbook_rag_review.contracts import ContractError
from runbook_rag_review.review import load_reviewer_ids, record_review


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ragreview")
    commands = parser.add_subparsers(dest="command", required=True)
    review = commands.add_parser("review", help="record a review for an explicit run")
    review.add_argument("--store", type=Path, required=True)
    review.add_argument("--run-id", required=True)
    review.add_argument("--answer-version", type=int, required=True)
    review.add_argument("--reviewer-id", required=True)
    review.add_argument("--decision", choices=("accept", "reject", "correct"), required=True)
    review.add_argument("--rationale", required=True)
    review.add_argument("--corrected-claim", action="append", default=[])
    review.add_argument("--corrected-evidence-id", action="append", default=[])
    args = parser.parse_args(argv)

    reviewer_fixture = Path(__file__).parents[1] / "fixtures" / "reviewers.json"
    try:
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


if __name__ == "__main__":
    raise SystemExit(main())
