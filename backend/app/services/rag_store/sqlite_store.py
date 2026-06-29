from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from backend.app.core.config import SQLITE_DB_PATH

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    file_name TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    file_size INTEGER NOT NULL CHECK(file_size >= 0),
    block_count INTEGER NOT NULL DEFAULT 0 CHECK(block_count >= 0),
    status TEXT NOT NULL CHECK(status IN ('processing', 'ready', 'failed')),
    chunk_count INTEGER NOT NULL DEFAULT 0 CHECK(chunk_count >= 0),
    strategy_json TEXT NOT NULL DEFAULT '{}',
    statistics_json TEXT NOT NULL DEFAULT '{}',
    preprocess_json TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_documents_status_updated
ON documents(status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_documents_sha
ON documents(file_sha256);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal > 0),
    chunk_type TEXT NOT NULL,
    content TEXT NOT NULL,
    summary TEXT,
    char_count INTEGER NOT NULL CHECK(char_count >= 0),
    title_path_json TEXT NOT NULL,
    source_refs_json TEXT NOT NULL,
    backlink_json TEXT NOT NULL,
    quality_flags_json TEXT NOT NULL,
    strategy_info_json TEXT NOT NULL,
    label_json TEXT NOT NULL,
    entity_tags_json TEXT NOT NULL,
    section_titles_json TEXT NOT NULL DEFAULT '[]',
    retrieval_text TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(doc_id, ordinal),
    FOREIGN KEY(doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_ordinal ON chunks(doc_id, ordinal);
"""


def _ensure_parent_dir() -> None:
    Path(SQLITE_DB_PATH).parent.mkdir(parents=True, exist_ok=True)


def _get_conn() -> sqlite3.Connection:
    _ensure_parent_dir()
    conn = sqlite3.connect(str(SQLITE_DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_sqlite() -> None:
    with _get_conn() as conn:
        conn.executescript(SCHEMA_SQL)
        _ensure_chunk_column(conn, "section_titles_json", "TEXT NOT NULL DEFAULT '[]'")
        _ensure_chunk_column(conn, "retrieval_text", "TEXT")


def _ensure_chunk_column(conn: sqlite3.Connection, column_name: str, column_spec: str) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(chunks)").fetchall()}
    if column_name not in columns:
        conn.execute(f"ALTER TABLE chunks ADD COLUMN {column_name} {column_spec}")


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _row_to_document(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "doc_id": row["doc_id"],
        "file_name": row["file_name"],
        "file_sha256": row["file_sha256"],
        "file_size": row["file_size"],
        "block_count": row["block_count"],
        "status": row["status"],
        "chunk_count": row["chunk_count"],
        "strategy": _load_json(row["strategy_json"], {}),
        "statistics": _load_json(row["statistics_json"], {}),
        "preprocess": _load_json(row["preprocess_json"], {}),
        "last_error": row["last_error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_chunk(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "chunk_id": row["chunk_id"],
        "doc_id": row["doc_id"],
        "ordinal": row["ordinal"],
        "chunk_type": row["chunk_type"],
        "content": row["content"],
        "summary": row["summary"] or "",
        "char_count": row["char_count"],
        "title_path": _load_json(row["title_path_json"], []),
        "source_refs": _load_json(row["source_refs_json"], []),
        "backlink": _load_json(row["backlink_json"], {}),
        "quality_flags": _load_json(row["quality_flags_json"], []),
        "strategy_info": _load_json(row["strategy_info_json"], {}),
        "label": _load_json(row["label_json"], []),
        "entity_tags": _load_json(row["entity_tags_json"], []),
        "section_titles": _load_json(row["section_titles_json"], []),
        "retrieval_text": row["retrieval_text"] or "",
    }


def upsert_document_processing(
    doc_id: str,
    file_name: str,
    file_sha256: str,
    file_size: int,
    block_count: int,
) -> None:
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO documents (
                doc_id, file_name, file_sha256, file_size, block_count,
                status, chunk_count, strategy_json, statistics_json,
                preprocess_json, last_error, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'processing', 0, '{}', '{}', '{}', NULL, datetime('now'), datetime('now'))
            ON CONFLICT(doc_id) DO UPDATE SET
                file_name=excluded.file_name,
                file_sha256=excluded.file_sha256,
                file_size=excluded.file_size,
                block_count=excluded.block_count,
                status='processing',
                chunk_count=0,
                strategy_json='{}',
                statistics_json='{}',
                preprocess_json='{}',
                last_error=NULL,
                updated_at=datetime('now')
            """,
            (doc_id, file_name, file_sha256, file_size, block_count),
        )


def mark_document_ready(
    doc_id: str,
    chunk_count: int,
    strategy: dict[str, Any],
    statistics: dict[str, Any],
    preprocess: dict[str, Any],
) -> None:
    with _get_conn() as conn:
        conn.execute(
            """
            UPDATE documents
            SET status='ready',
                chunk_count=?,
                strategy_json=?,
                statistics_json=?,
                preprocess_json=?,
                last_error=NULL,
                updated_at=datetime('now')
            WHERE doc_id=?
            """,
            (
                chunk_count,
                _dump_json(strategy),
                _dump_json(statistics),
                _dump_json(preprocess),
                doc_id,
            ),
        )


def mark_document_failed(doc_id: str, error_message: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            """
            UPDATE documents
            SET status='failed',
                last_error=?,
                updated_at=datetime('now')
            WHERE doc_id=?
            """,
            (error_message, doc_id),
        )


def get_document(doc_id: str) -> dict[str, Any] | None:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE doc_id=?",
            (doc_id,),
        ).fetchone()
    if not row:
        return None
    return _row_to_document(row)


def replace_chunks(doc_id: str, chunks: list[dict[str, Any]]) -> None:
    with _get_conn() as conn:
        conn.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))
        for ordinal, chunk in enumerate(chunks, start=1):
            conn.execute(
                """
                INSERT INTO chunks (
                    chunk_id, doc_id, ordinal, chunk_type, content, summary, char_count,
                    title_path_json, source_refs_json, backlink_json, quality_flags_json,
                    strategy_info_json, label_json, entity_tags_json,
                    section_titles_json, retrieval_text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk["chunk_id"],
                    doc_id,
                    ordinal,
                    chunk.get("chunk_type", "normal"),
                    chunk.get("content", ""),
                    chunk.get("summary", ""),
                    int(chunk.get("char_count", 0)),
                    _dump_json(chunk.get("title_path", [])),
                    _dump_json(chunk.get("source_refs", [])),
                    _dump_json(chunk.get("backlink", {})),
                    _dump_json(chunk.get("quality_flags", [])),
                    _dump_json(chunk.get("strategy_info", {})),
                    _dump_json(chunk.get("label", [])),
                    _dump_json(chunk.get("entity_tags", [])),
                    _dump_json(chunk.get("section_titles", [])),
                    chunk.get("retrieval_text", ""),
                ),
            )


def get_chunks_by_doc(doc_id: str) -> list[dict[str, Any]]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM chunks WHERE doc_id=? ORDER BY ordinal ASC",
            (doc_id,),
        ).fetchall()
    return [_row_to_chunk(row) for row in rows]


def get_chunks_by_ids(chunk_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    ids = list(chunk_ids)
    if not ids:
        return {}

    placeholders = ",".join(["?"] * len(ids))
    with _get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM chunks WHERE chunk_id IN ({placeholders})",
            ids,
        ).fetchall()
    return {row["chunk_id"]: _row_to_chunk(row) for row in rows}
