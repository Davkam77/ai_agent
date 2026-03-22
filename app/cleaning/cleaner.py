from __future__ import annotations

import re

from app.cleaning.rules import BANK_TOPIC_EXACT_NOISE, GLOBAL_CONTAINS_NOISE, GLOBAL_EXACT_NOISE
from app.models import CleanDocument, RawDocument
from app.utils import dedupe_lines, normalize_whitespace


class TextCleaner:
    def clean_document(self, document: RawDocument) -> CleanDocument:
        lines = [normalize_whitespace(line) for line in document.raw_text.splitlines()]
        lines = [line for line in lines if self._should_keep(line, document.bank_name, document.topic)]
        cleaned_lines = dedupe_lines(lines)
        clean_text = "\n".join(cleaned_lines)
        clean_text = re.sub(r"\n{3,}", "\n\n", clean_text).strip()
        return CleanDocument(
            bank_name=document.bank_name,
            topic=document.topic,
            source_url=document.source_url,
            page_title=document.page_title,
            clean_text=clean_text,
            fetched_at=document.fetched_at,
            content_hash=document.content_hash,
        )

    def _should_keep(self, line: str, bank_name: str, topic: str) -> bool:
        if not line or len(line) < 2:
            return False
        exact_noise = GLOBAL_EXACT_NOISE | BANK_TOPIC_EXACT_NOISE.get((bank_name, topic), set())
        if line in exact_noise:
            return False
        lowered = line.casefold()
        if any(noise in lowered for noise in GLOBAL_CONTAINS_NOISE):
            return False
        if len(line.split()) == 1 and len(line) <= 3:
            return False
        return True
