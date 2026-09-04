from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from runbook_rag_review.contracts import ContractError, Document

CHUNKING_RULES = "paragraph-v1"
SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    document_version: int
    start_offset: int
    end_offset: int
    text: str
    effective_from: str
    effective_to: str | None
    team_scope: str


def paragraph_chunks(documents: list[Document]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for document in documents:
        search_from = 0
        for paragraph in document.source_text.split("\n\n"):
            if not paragraph:
                continue
            start_offset = document.source_text.index(paragraph, search_from)
            end_offset = start_offset + len(paragraph)
            identity = (
                f"{document.document_id}\0{document.version}\0"
                f"{start_offset}\0{end_offset}\0{paragraph}"
            )
            chunks.append(
                Chunk(
                    chunk_id=sha256(identity.encode()).hexdigest(),
                    document_id=document.document_id,
                    document_version=document.version,
                    start_offset=start_offset,
                    end_offset=end_offset,
                    text=paragraph,
                    effective_from=document.effective_from.isoformat(),
                    effective_to=(
                        document.effective_to.isoformat() if document.effective_to else None
                    ),
                    team_scope=document.team_scope,
                )
            )
            search_from = end_offset
    return chunks


def index_identity(documents: list[Document]) -> str:
    records = [
        {
            "document_id": document.document_id,
            "version": document.version,
            "effective_from": document.effective_from.isoformat(),
            "effective_to": (
                document.effective_to.isoformat() if document.effective_to else None
            ),
            "team_scope": document.team_scope,
            "source_text": document.source_text,
            "source_text_sha256": document.source_text_sha256,
        }
        for document in sorted(
            documents, key=lambda item: (item.document_id, item.version)
        )
    ]
    corpus_bytes = json.dumps(
        records, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    return sha256(
        corpus_bytes + b"\0" + CHUNKING_RULES.encode() + b"\0" + SCHEMA_VERSION.encode()
    ).hexdigest()


def build_index(index_path: Path, documents: list[Document]) -> str:
    if not documents:
        raise ContractError("empty_corpus", "at least one document is required")
    index_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=index_path.parent, prefix=f".{index_path.name}.", suffix=".tmp"
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    digest = index_identity(documents)
    try:
        connection = sqlite3.connect(temporary_path)
        try:
            _populate_index(connection, paragraph_chunks(documents), digest)
        finally:
            connection.close()
        os.replace(temporary_path, index_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return digest


def _populate_index(
    connection: sqlite3.Connection, chunks: list[Chunk], digest: str
) -> None:
    try:
        connection.execute(
            "CREATE VIRTUAL TABLE chunks_fts USING fts5(text, tokenize='unicode61')"
        )
    except sqlite3.OperationalError as error:
        raise ContractError("fts5_unavailable", "SQLite FTS5 support is required") from error
    connection.executescript(
        """
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE chunks (
            chunk_id TEXT NOT NULL UNIQUE,
            document_id TEXT NOT NULL,
            document_version INTEGER NOT NULL,
            start_offset INTEGER NOT NULL,
            end_offset INTEGER NOT NULL,
            text TEXT NOT NULL,
            effective_from TEXT NOT NULL,
            effective_to TEXT,
            team_scope TEXT NOT NULL
        );
        """
    )
    connection.executemany(
        "INSERT INTO metadata (key, value) VALUES (?, ?)",
        (
            ("schema_version", SCHEMA_VERSION),
            ("chunking_rules", CHUNKING_RULES),
            ("index_digest", digest),
        ),
    )
    for chunk in chunks:
        cursor = connection.execute(
            """
            INSERT INTO chunks (
                chunk_id, document_id, document_version, start_offset, end_offset,
                text, effective_from, effective_to, team_scope
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk.chunk_id,
                chunk.document_id,
                chunk.document_version,
                chunk.start_offset,
                chunk.end_offset,
                chunk.text,
                chunk.effective_from,
                chunk.effective_to,
                chunk.team_scope,
            ),
        )
        connection.execute(
            "INSERT INTO chunks_fts (rowid, text) VALUES (?, ?)",
            (cursor.lastrowid, chunk.text),
        )
    connection.commit()
