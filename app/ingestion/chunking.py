from __future__ import annotations

import re

from app.models import ChunkRecord, CleanDocument
from app.utils import normalize_whitespace, sha256_text


class TextChunker:
    def __init__(self, max_chars: int = 900, overlap_chars: int = 120) -> None:
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars

    def chunk_document(self, document: CleanDocument) -> list[ChunkRecord]:
        parts = self._split_text(document.clean_text)
        chunks: list[ChunkRecord] = []
        for index, content in enumerate(parts):
            chunk_id = sha256_text(
                f"{document.bank_name}|{document.topic}|{document.source_url}|{document.content_hash}|{index}"
            )
            chunks.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    bank_name=document.bank_name,
                    topic=document.topic,
                    source_url=document.source_url,
                    page_title=document.page_title,
                    content=content,
                    fetched_at=document.fetched_at,
                    content_hash=document.content_hash,
                    is_active=True,
                )
            )
        return chunks

    def _split_text(self, text: str) -> list[str]:
        segments = [segment.strip() for segment in re.split(r"\n{2,}|\n", text) if segment.strip()]
        chunks: list[str] = []
        current = ""

        for segment in segments:
            normalized = normalize_whitespace(segment)
            if len(normalized) > self.max_chars:
                for item in self._split_long_segment(normalized):
                    current = self._append_or_flush(current, item, chunks)
                continue
            current = self._append_or_flush(current, normalized, chunks)

        if current:
            chunks.append(current.strip())
        return chunks

    def _append_or_flush(self, current: str, addition: str, output: list[str]) -> str:
        if not current:
            return addition
        candidate = f"{current}\n{addition}"
        if len(candidate) <= self.max_chars:
            return candidate
        output.append(current.strip())
        overlap = current[-self.overlap_chars :] if self.overlap_chars else ""
        return normalize_whitespace(f"{overlap}\n{addition}")

    def _split_long_segment(self, segment: str) -> list[str]:
        sentences = [item.strip() for item in re.split(r"(?<=[.!?։])\s+", segment) if item.strip()]
        if len(sentences) <= 1:
            return [segment[index : index + self.max_chars] for index in range(0, len(segment), self.max_chars)]

        chunks: list[str] = []
        current = ""
        for sentence in sentences:
            if not current:
                current = sentence
                continue
            candidate = f"{current} {sentence}"
            if len(candidate) <= self.max_chars:
                current = candidate
                continue
            chunks.append(current.strip())
            current = sentence
        if current:
            chunks.append(current.strip())
        return chunks
