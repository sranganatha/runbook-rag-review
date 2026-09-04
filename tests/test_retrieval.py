from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from runbook_rag_review.contracts import ContractError, validate_fixture_set
from runbook_rag_review.index import (
    _populate_index,
    build_index,
    index_identity,
    paragraph_chunks,
)
from runbook_rag_review.retrieve import retrieve


class RetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        fixture_dir = Path(__file__).parents[1] / "fixtures"
        document_records = json.loads((fixture_dir / "documents.json").read_bytes())
        question_records = json.loads((fixture_dir / "questions.json").read_bytes())
        cls.documents, _ = validate_fixture_set(document_records, question_records)

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.index_path = Path(self.temporary_directory.name) / "runbooks.db"
        self.index_digest = build_index(self.index_path, self.documents)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_chunks_have_stable_ids_and_exact_offsets(self) -> None:
        first = paragraph_chunks(self.documents)
        second = paragraph_chunks(self.documents)

        self.assertEqual(first, second)
        for chunk in first:
            document = next(
                item
                for item in self.documents
                if item.document_id == chunk.document_id
                and item.version == chunk.document_version
            )
            self.assertEqual(
                chunk.text, document.source_text[chunk.start_offset : chunk.end_offset]
            )

    def test_index_identity_includes_source_bytes_and_metadata(self) -> None:
        source_changed = self.documents.copy()
        source_changed[0] = replace(
            source_changed[0], source_text=source_changed[0].source_text + " changed"
        )
        metadata_changed = self.documents.copy()
        metadata_changed[0] = replace(metadata_changed[0], team_scope="another-team")

        self.assertNotEqual(index_identity(self.documents), index_identity(source_changed))
        self.assertNotEqual(index_identity(self.documents), index_identity(metadata_changed))

    def test_current_query_excludes_obsolete_version(self) -> None:
        result = retrieve(
            self.index_path,
            "tagging exception report",
            "finops",
            date(2026, 1, 15),
        )

        self.assertEqual(self.index_digest, result.index_digest)
        self.assertTrue(result.hits)
        tagging_hits = [
            hit for hit in result.hits if hit.document_id == "tagging-standard"
        ]
        self.assertTrue(tagging_hits)
        self.assertEqual({2}, {hit.document_version for hit in tagging_hits})

    def test_historical_query_uses_historical_version(self) -> None:
        result = retrieve(
            self.index_path,
            "weekly exception report",
            "finops",
            date(2025, 2, 1),
        )

        tagging_hits = [hit for hit in result.hits if hit.document_id == "tagging-standard"]
        self.assertEqual([1], [hit.document_version for hit in tagging_hits])

    def test_scope_filter_excludes_other_team_before_return(self) -> None:
        result = retrieve(
            self.index_path,
            "pipeline backfills job identifiers",
            "finops",
            date(2026, 1, 15),
        )

        self.assertNotIn("data-pipeline-costs", {hit.document_id for hit in result.hits})

    def test_failed_rebuild_preserves_existing_index(self) -> None:
        def interrupt_after_partial_write(
            connection: sqlite3.Connection, *_: object
        ) -> None:
            connection.execute("CREATE TABLE partial_build (value TEXT)")
            connection.commit()
            raise RuntimeError("simulated interruption")

        with patch(
            "runbook_rag_review.index._populate_index",
            side_effect=interrupt_after_partial_write,
        ):
            with self.assertRaisesRegex(RuntimeError, "simulated interruption"):
                build_index(self.index_path, self.documents)

        result = retrieve(
            self.index_path, "monthly budget", "finops", date(2026, 1, 15)
        )
        self.assertEqual(self.index_digest, result.index_digest)
        self.assertEqual("budget-alerts", result.hits[0].document_id)

    def test_fts_query_syntax_is_not_accepted_from_question_text(self) -> None:
        result = retrieve(
            self.index_path,
            'budget" OR team_scope:*',
            "finops",
            date(2026, 1, 15),
        )

        self.assertTrue(result.hits)

    def test_query_without_searchable_terms_is_rejected(self) -> None:
        with self.assertRaisesRegex(ContractError, "invalid_query"):
            retrieve(self.index_path, "***", "finops", date(2026, 1, 15))

    def test_fts5_unavailable_is_visible(self) -> None:
        connection = Mock()
        connection.execute.side_effect = sqlite3.OperationalError("no such module: fts5")

        with self.assertRaisesRegex(ContractError, "fts5_unavailable"):
            _populate_index(connection, [], "digest")


if __name__ == "__main__":
    unittest.main()
