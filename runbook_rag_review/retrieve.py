from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from runbook_rag_review.contracts import ContractError


@dataclass(frozen=True)
class RetrievalHit:
    chunk_id: str
    document_id: str
    document_version: int
    start_offset: int
    end_offset: int
    text: str
    score: float
    effective_from: str
    effective_to: str | None
    team_scope: str


@dataclass(frozen=True)
class RetrievalResult:
    query: str
    authorized_scope: str
    as_of: date
    index_digest: str
    hits: tuple[RetrievalHit, ...]


def retrieve(
    index_path: Path,
    query: str,
    authorized_scope: str,
    as_of: date,
    *,
    limit: int = 5,
) -> RetrievalResult:
    return _retrieve(
        index_path,
        query,
        authorized_scope,
        as_of,
        limit=limit,
        version_filter_before_ranking=True,
    )


def retrieve_scope_only_baseline(
    index_path: Path,
    query: str,
    authorized_scope: str,
    as_of: date,
    *,
    limit: int = 5,
) -> RetrievalResult:
    return _retrieve(
        index_path,
        query,
        authorized_scope,
        as_of,
        limit=limit,
        version_filter_before_ranking=False,
    )


def _retrieve(
    index_path: Path,
    query: str,
    authorized_scope: str,
    as_of: date,
    *,
    limit: int,
    version_filter_before_ranking: bool,
) -> RetrievalResult:
    if not index_path.is_file():
        raise ContractError("index_not_found", str(index_path))
    if not isinstance(query, str):
        raise ContractError("invalid_query", "query must be a string")
    if not isinstance(authorized_scope, str) or not authorized_scope.strip():
        raise ContractError("invalid_scope", "authorized_scope must not be empty")
    if type(as_of) is not date:
        raise ContractError("invalid_as_of", "as_of must be a date")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ContractError("invalid_limit", "limit must be a positive integer")
    match_query = _match_query(query)

    connection = sqlite3.connect(f"{index_path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        digest_row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'index_digest'"
        ).fetchone()
        if digest_row is None:
            raise ContractError("invalid_index", "index identity is missing")
        version_clause = (
            """
              AND chunks.effective_from <= ?
              AND (chunks.effective_to IS NULL OR chunks.effective_to >= ?)
            """
            if version_filter_before_ranking
            else ""
        )
        parameters: tuple[object, ...] = (match_query, authorized_scope)
        if version_filter_before_ranking:
            parameters += (as_of.isoformat(), as_of.isoformat())
        parameters += (limit,)
        rows = connection.execute(
            f"""
            SELECT
                chunks.chunk_id,
                chunks.document_id,
                chunks.document_version,
                chunks.start_offset,
                chunks.end_offset,
                chunks.text,
                bm25(chunks_fts) AS score,
                chunks.effective_from,
                chunks.effective_to,
                chunks.team_scope
            FROM chunks_fts
            JOIN chunks ON chunks.rowid = chunks_fts.rowid
            WHERE chunks_fts MATCH ?
              AND chunks.team_scope = ?
              {version_clause}
            ORDER BY score, chunks.chunk_id
            LIMIT ?
            """,
            parameters,
        ).fetchall()
    except sqlite3.DatabaseError as error:
        raise ContractError("invalid_index", "index cannot be queried") from error
    finally:
        connection.close()

    hits = [
        hit
        for hit in (RetrievalHit(*row) for row in rows)
        if hit.effective_from <= as_of.isoformat()
        and (hit.effective_to is None or hit.effective_to >= as_of.isoformat())
    ]
    for hit in hits:
        if hit.team_scope != authorized_scope or hit.effective_from > as_of.isoformat() or (
            hit.effective_to is not None and hit.effective_to < as_of.isoformat()
        ):
            raise ContractError(
                "retrieval_filter_violation", "retrieved chunk violates trusted filters"
            )

    return RetrievalResult(
        query=query,
        authorized_scope=authorized_scope,
        as_of=as_of,
        index_digest=digest_row[0],
        hits=tuple(hits),
    )


def _match_query(query: str) -> str:
    tokens = list(dict.fromkeys(re.findall(r"[^\W_]+", query.casefold())))
    if not tokens:
        raise ContractError("invalid_query", "query must contain a searchable term")
    return " OR ".join(f'"{token}"' for token in tokens)
