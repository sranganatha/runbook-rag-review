from __future__ import annotations

import json
from pathlib import Path

from runbook_rag_review.contracts import validate_fixture_set


def main() -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures"
    document_records = json.loads(
        (fixture_dir / "documents.json").read_text(encoding="utf-8")
    )
    question_records = json.loads(
        (fixture_dir / "questions.json").read_text(encoding="utf-8")
    )
    documents, questions = validate_fixture_set(document_records, question_records)
    development = sum(question.split == "development" for question in questions)
    holdout = len(questions) - development
    print(
        f"validated {len(documents)} documents and {len(questions)} questions "
        f"({development} development, {holdout} holdout)"
    )


if __name__ == "__main__":
    main()
