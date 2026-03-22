from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class Topic(str, Enum):
    CREDITS = "credits"
    DEPOSITS = "deposits"
    BRANCH_LOCATIONS = "branch_locations"

    @classmethod
    def from_value(cls, value: str) -> "Topic":
        for item in cls:
            if item.value == value:
                return item
        raise ValueError(f"Unsupported topic: {value}")


@dataclass(slots=True)
class SourceConfig:
    bank_name: str
    topic: Topic
    source_url: str
    fetcher: str = "requests"
    extractor: str = "generic"
    content_selectors: tuple[str, ...] = ()
    include_keywords: tuple[str, ...] = ()
    exclude_keywords: tuple[str, ...] = ()
    expand_urls: bool = False
    child_url_prefixes: tuple[str, ...] = ()


@dataclass(slots=True)
class ExtractionResult:
    page_title: str
    raw_text: str
    structured_data: dict[str, Any] | None = None
    skip_document: bool = False


@dataclass(slots=True)
class RawDocument:
    bank_name: str
    topic: str
    source_url: str
    page_title: str
    raw_text: str
    fetched_at: str
    content_hash: str
    structured_data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CleanDocument:
    bank_name: str
    topic: str
    source_url: str
    page_title: str
    clean_text: str
    fetched_at: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ChunkRecord:
    chunk_id: str
    bank_name: str
    topic: str
    source_url: str
    page_title: str
    content: str
    fetched_at: str
    content_hash: str
    is_active: bool
    document_id: str = ""
    section_name: str = ""
    chunk_index: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class VectorRecord:
    chunk_id: str
    bank_name: str
    topic: str
    vector: list[float]
    source_url: str = ""
    page_title: str = ""
    document_id: str = ""
    section_name: str = ""
    chunk_index: int = 0


@dataclass(slots=True)
class RetrievedChunk:
    chunk_id: str
    bank_name: str
    topic: str
    source_url: str
    page_title: str
    content: str
    fetched_at: str
    content_hash: str
    score: float
    document_id: str = ""
    section_name: str = ""
    chunk_index: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AnswerPayload:
    question: str
    topic: str | None
    answer_text: str
    sources: list[dict[str, Any]]
    refusal: bool
    debug: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
