from __future__ import annotations

import re
from dataclasses import dataclass

from app.models import ChunkRecord, CleanDocument
from app.utils import dedupe_adjacent_lines, normalize_whitespace, sha256_text


SECTION_MARKER_RE = re.compile(r"^\[section:\s*(.+?)\]\s*$", re.IGNORECASE)
HEADING_PREFIXES = (
    "Section:",
    "Tab:",
    "Product:",
    "Business card",
    "CTA links",
    "Regions",
    "Last updated:",
)


@dataclass(slots=True)
class _TextBlock:
    section_name: str
    text: str


class TextChunker:
    def __init__(self, max_chars: int = 1000, overlap_lines: int = 2) -> None:
        self.max_chars = max(400, max_chars)
        self.overlap_lines = max(0, overlap_lines)

    def chunk_document(self, document: CleanDocument) -> list[ChunkRecord]:
        document_id = sha256_text(
            f"{document.bank_name}|{document.topic}|{document.source_url}|{document.content_hash}"
        )
        blocks = self._build_blocks(document.clean_text)
        chunk_parts = self._split_blocks(blocks)
        chunks: list[ChunkRecord] = []
        for index, part in enumerate(chunk_parts):
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
                    content=part.text,
                    fetched_at=document.fetched_at,
                    content_hash=document.content_hash,
                    is_active=True,
                    document_id=document_id,
                    section_name=part.section_name,
                    chunk_index=index,
                )
            )
        return chunks

    def _build_blocks(self, text: str) -> list[_TextBlock]:
        blocks: list[_TextBlock] = []
        current_lines: list[str] = []
        current_section = "Overview"

        def flush_block() -> None:
            if not current_lines:
                return
            cleaned = dedupe_adjacent_lines(current_lines)
            block_text = "\n".join(cleaned).strip()
            if not block_text:
                return
            section_name = current_section or self._infer_section_from_text(block_text) or "Overview"
            blocks.append(_TextBlock(section_name=section_name, text=block_text))

        for raw_line in text.splitlines():
            line = normalize_whitespace(raw_line)
            if not line:
                flush_block()
                current_lines = []
                continue
            section_name = self._extract_section_name(line)
            if section_name:
                flush_block()
                current_lines = [line]
                current_section = section_name
                continue
            current_lines.append(line)

        flush_block()
        return blocks

    def _split_blocks(self, blocks: list[_TextBlock]) -> list[_TextBlock]:
        chunk_parts: list[_TextBlock] = []
        for block in blocks:
            if len(block.text) <= self.max_chars:
                chunk_parts.append(block)
                continue
            chunk_parts.extend(self._split_block(block))
        return chunk_parts

    def _split_block(self, block: _TextBlock) -> list[_TextBlock]:
        lines = [line.strip() for line in block.text.splitlines() if line.strip()]
        if not lines:
            return []

        heading_line = ""
        first_line_section = self._extract_section_name(lines[0])
        if first_line_section:
            heading_line = lines[0]
            body_lines = lines[1:]
        else:
            body_lines = lines
            if block.section_name and block.section_name != "Overview":
                heading_line = f"[Section: {block.section_name}]"

        expanded_lines: list[str] = []
        for line in body_lines:
            expanded_lines.extend(self._split_long_line(line))

        chunks: list[_TextBlock] = []
        current: list[str] = [heading_line] if heading_line else []
        for line in expanded_lines:
            candidate_lines = [*current, line]
            candidate_text = "\n".join(item for item in candidate_lines if item).strip()
            if candidate_text and len(candidate_text) <= self.max_chars:
                current.append(line)
                continue

            chunk_text = "\n".join(item for item in current if item).strip()
            if chunk_text:
                chunks.append(_TextBlock(section_name=block.section_name, text=chunk_text))

            overlap_tail = [item for item in current if item and item != heading_line][-self.overlap_lines :]
            current = []
            if heading_line:
                current.append(heading_line)
            current.extend(overlap_tail)

            retry_candidate = "\n".join(item for item in [*current, line] if item).strip()
            if retry_candidate and len(retry_candidate) > self.max_chars and current:
                current = [heading_line] if heading_line else []
            current.append(line)

        final_text = "\n".join(item for item in current if item).strip()
        if final_text:
            chunks.append(_TextBlock(section_name=block.section_name, text=final_text))
        return chunks

    def _split_long_line(self, line: str) -> list[str]:
        if len(line) <= self.max_chars:
            return [line]
        if "|" in line:
            cells = [cell.strip() for cell in line.split("|")]
            grouped: list[str] = []
            current = ""
            for cell in cells:
                candidate = f"{current} | {cell}".strip(" |")
                if candidate and len(candidate) <= self.max_chars:
                    current = candidate
                    continue
                if current:
                    grouped.append(current)
                current = cell
            if current:
                grouped.append(current)
            if grouped:
                return grouped

        sentences = [item.strip() for item in re.split(r"(?<=[.!?։])\s+", line) if item.strip()]
        if len(sentences) > 1:
            grouped: list[str] = []
            current = ""
            for sentence in sentences:
                candidate = f"{current} {sentence}".strip()
                if candidate and len(candidate) <= self.max_chars:
                    current = candidate
                    continue
                if current:
                    grouped.append(current)
                current = sentence
            if current:
                grouped.append(current)
            if grouped:
                return grouped

        return [line[index : index + self.max_chars] for index in range(0, len(line), self.max_chars)]

    @staticmethod
    def _extract_section_name(line: str) -> str:
        match = SECTION_MARKER_RE.match(line)
        if match:
            return normalize_whitespace(match.group(1))
        for prefix in HEADING_PREFIXES:
            if line.startswith(prefix):
                return normalize_whitespace(line.removeprefix(prefix).strip() or prefix.rstrip(":"))
        return ""

    def _infer_section_from_text(self, text: str) -> str:
        first_line = text.splitlines()[0] if text else ""
        return self._extract_section_name(first_line)
