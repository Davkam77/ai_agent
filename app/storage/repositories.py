from __future__ import annotations

import sqlite3
from pathlib import Path

from app.models import ChunkRecord, CleanDocument, RetrievedChunk


class MetadataRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def get_active_document_hash(self, bank_name: str, topic: str, source_url: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT content_hash
                FROM documents
                WHERE bank_name = ? AND topic = ? AND source_url = ? AND is_active = 1
                ORDER BY id DESC
                LIMIT 1
                """,
                (bank_name, topic, source_url),
            ).fetchone()
        return row["content_hash"] if row else None

    def get_active_chunk_ids(self, bank_name: str, topic: str, source_url: str) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT chunk_id
                FROM chunks
                WHERE bank_name = ? AND topic = ? AND source_url = ? AND is_active = 1
                """,
                (bank_name, topic, source_url),
            ).fetchall()
        return [row["chunk_id"] for row in rows]

    def has_legacy_chunk_metadata(self, bank_name: str, topic: str, source_url: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_chunks,
                    SUM(CASE WHEN document_id = '' THEN 1 ELSE 0 END) AS empty_document_id_chunks
                FROM chunks
                WHERE bank_name = ? AND topic = ? AND source_url = ? AND is_active = 1
                """,
                (bank_name, topic, source_url),
            ).fetchone()
        if not row:
            return False
        total_chunks = int(row["total_chunks"] or 0)
        if total_chunks == 0:
            return False
        return int(row["empty_document_id_chunks"] or 0) > 0

    def deactivate_source(self, bank_name: str, topic: str, source_url: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE documents
                SET is_active = 0
                WHERE bank_name = ? AND topic = ? AND source_url = ? AND is_active = 1
                """,
                (bank_name, topic, source_url),
            )
            connection.execute(
                """
                UPDATE chunks
                SET is_active = 0
                WHERE bank_name = ? AND topic = ? AND source_url = ? AND is_active = 1
                """,
                (bank_name, topic, source_url),
            )
            connection.commit()

    def insert_document(self, document: CleanDocument, source_file: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO documents (
                    bank_name,
                    topic,
                    source_url,
                    page_title,
                    fetched_at,
                    content_hash,
                    source_file,
                    is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(bank_name, topic, source_url, content_hash) DO UPDATE SET
                    page_title = excluded.page_title,
                    fetched_at = excluded.fetched_at,
                    source_file = excluded.source_file,
                    is_active = 1
                """,
                (
                    document.bank_name,
                    document.topic,
                    document.source_url,
                    document.page_title,
                    document.fetched_at,
                    document.content_hash,
                    source_file,
                ),
            )
            connection.commit()

    def insert_chunks(self, chunks: list[ChunkRecord]) -> None:
        if not chunks:
            return
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO chunks (
                    chunk_id,
                    bank_name,
                    topic,
                    source_url,
                    page_title,
                    content,
                    fetched_at,
                    content_hash,
                    document_id,
                    section_name,
                    chunk_index,
                    is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.chunk_id,
                        chunk.bank_name,
                        chunk.topic,
                        chunk.source_url,
                        chunk.page_title,
                        chunk.content,
                        chunk.fetched_at,
                        chunk.content_hash,
                        chunk.document_id,
                        chunk.section_name,
                        chunk.chunk_index,
                        1 if chunk.is_active else 0,
                    )
                    for chunk in chunks
                ],
            )
            connection.commit()

    def get_chunks_by_ids(self, chunk_ids: list[str]) -> list[RetrievedChunk]:
        if not chunk_ids:
            return []
        placeholders = ",".join("?" for _ in chunk_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT chunk_id, bank_name, topic, source_url, page_title, content, fetched_at, content_hash, document_id, section_name, chunk_index
                FROM chunks
                WHERE chunk_id IN ({placeholders}) AND is_active = 1
                """,
                chunk_ids,
            ).fetchall()
        row_by_id = {row["chunk_id"]: row for row in rows}
        results: list[RetrievedChunk] = []
        for chunk_id in chunk_ids:
            row = row_by_id.get(chunk_id)
            if not row:
                continue
            results.append(
                RetrievedChunk(
                    chunk_id=row["chunk_id"],
                    bank_name=row["bank_name"],
                    topic=row["topic"],
                    source_url=row["source_url"],
                    page_title=row["page_title"],
                    content=row["content"],
                    fetched_at=row["fetched_at"],
                    content_hash=row["content_hash"],
                    score=0.0,
                    document_id=row["document_id"] or "",
                    section_name=row["section_name"] or "",
                    chunk_index=int(row["chunk_index"] or 0),
                )
            )
        return results

    def list_active_chunks(self, topic: str, bank_name: str | None = None) -> list[RetrievedChunk]:
        query = """
            SELECT chunk_id, bank_name, topic, source_url, page_title, content, fetched_at, content_hash, document_id, section_name, chunk_index
            FROM chunks
            WHERE topic = ? AND is_active = 1
        """
        parameters: list[str] = [topic]
        if bank_name:
            query += " AND bank_name = ?"
            parameters.append(bank_name)
        query += " ORDER BY bank_name, page_title, source_url, chunk_index, chunk_id"

        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()

        return [
            RetrievedChunk(
                chunk_id=row["chunk_id"],
                bank_name=row["bank_name"],
                topic=row["topic"],
                source_url=row["source_url"],
                page_title=row["page_title"],
                content=row["content"],
                fetched_at=row["fetched_at"],
                content_hash=row["content_hash"],
                score=0.0,
                document_id=row["document_id"] or "",
                section_name=row["section_name"] or "",
                chunk_index=int(row["chunk_index"] or 0),
            )
            for row in rows
        ]
