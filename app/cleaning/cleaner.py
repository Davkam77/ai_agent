from __future__ import annotations

from dataclasses import dataclass
import re

from app.cleaning.rules import BANK_TOPIC_EXACT_NOISE, GLOBAL_CONTAINS_NOISE, GLOBAL_EXACT_NOISE
from app.models import CleanDocument, RawDocument
from app.utils import dedupe_adjacent_lines, normalize_whitespace


CURRENCY_CODES = {
    "AMD",
    "USD",
    "EUR",
    "RUR",
    "RUB",
    "GBP",
    "GEL",
    "CHF",
    "JPY",
    "CNY",
    "CAD",
    "AUD",
}

SHORT_TOKEN_RE = re.compile(
    r"^(?:"
    r"[A-Z]{2,4}"  # currency-like codes
    r"|[%№]"
    r"|\(?\d+(?:[.,]\d+)?%?\)?"
    r"|\d+\s*[-/]\s*\d+"
    r"|[()\[\]]"
    r")$"
)


@dataclass(slots=True)
class CleaningStats:
    total_lines: int
    kept_lines: int
    removed_lines: int
    removed_samples: list[str]


class TextCleaner:
    def __init__(self, sample_limit: int = 8) -> None:
        self.sample_limit = max(1, sample_limit)

    def clean_document(self, document: RawDocument) -> CleanDocument:
        cleaned, _stats = self.clean_document_with_stats(document)
        return cleaned

    def clean_document_with_stats(self, document: RawDocument) -> tuple[CleanDocument, CleaningStats]:
        lines = [normalize_whitespace(line) for line in document.raw_text.splitlines()]
        kept_lines: list[str] = []
        removed_samples: list[str] = []
        removed_count = 0

        for line in lines:
            if self._should_keep(line, document.bank_name, document.topic):
                kept_lines.append(line)
                continue
            removed_count += 1
            if len(removed_samples) < self.sample_limit and line:
                removed_samples.append(line)

        cleaned_lines = dedupe_adjacent_lines(kept_lines)
        clean_text = "\n".join(cleaned_lines)
        clean_text = re.sub(r"\n{3,}", "\n\n", clean_text).strip()
        cleaned = CleanDocument(
            bank_name=document.bank_name,
            topic=document.topic,
            source_url=document.source_url,
            page_title=document.page_title,
            clean_text=clean_text,
            fetched_at=document.fetched_at,
            content_hash=document.content_hash,
        )
        return cleaned, CleaningStats(
            total_lines=len(lines),
            kept_lines=len(kept_lines),
            removed_lines=removed_count,
            removed_samples=removed_samples,
        )

    def _should_keep(self, line: str, bank_name: str, topic: str) -> bool:
        if not line:
            return False
        if self._is_significant_short_token(line):
            return True
        exact_noise = GLOBAL_EXACT_NOISE | BANK_TOPIC_EXACT_NOISE.get((bank_name, topic), set())
        if line in exact_noise:
            return False
        lowered = line.casefold()
        if any(noise in lowered for noise in GLOBAL_CONTAINS_NOISE):
            return False
        if len(line.split()) == 1 and len(line) <= 3 and not self._is_significant_short_token(line):
            return False
        return True

    @staticmethod
    def _is_significant_short_token(line: str) -> bool:
        token = line.strip()
        if not token:
            return False
        if token.upper() in CURRENCY_CODES:
            return True
        if "|" in token:
            return True
        if any(char.isdigit() for char in token):
            return True
        if token in {"(", ")", "[", "]"}:
            return True
        if SHORT_TOKEN_RE.match(token):
            return True
        return False
