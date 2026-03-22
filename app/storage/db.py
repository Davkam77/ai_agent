from __future__ import annotations

import sqlite3
from pathlib import Path


def initialize_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bank_name TEXT NOT NULL,
                topic TEXT NOT NULL,
                source_url TEXT NOT NULL,
                page_title TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                source_file TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                UNIQUE(bank_name, topic, source_url, content_hash)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                bank_name TEXT NOT NULL,
                topic TEXT NOT NULL,
                source_url TEXT NOT NULL,
                page_title TEXT NOT NULL,
                content TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                document_id TEXT NOT NULL DEFAULT '',
                section_name TEXT NOT NULL DEFAULT '',
                chunk_index INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        _ensure_column(cursor, "chunks", "document_id", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(cursor, "chunks", "section_name", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(cursor, "chunks", "chunk_index", "INTEGER NOT NULL DEFAULT 0")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_lookup ON documents(bank_name, topic, source_url, is_active)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_topic_active ON chunks(topic, is_active)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_source_lookup ON chunks(bank_name, topic, source_url, is_active)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_source_order ON chunks(source_url, chunk_index, is_active)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_document_lookup ON chunks(document_id, is_active)"
        )
        connection.commit()
    finally:
        connection.close()


def _ensure_column(cursor: sqlite3.Cursor, table_name: str, column_name: str, definition: str) -> None:
    existing = {
        row[1]
        for row in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name in existing:
        return
    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
