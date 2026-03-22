from __future__ import annotations

import logging
from pathlib import Path

from app.config.settings import Settings
from app.cleaning.cleaner import TextCleaner
from app.models import CleanDocument, RawDocument
from app.utils import iter_json_files, read_json, slugify, write_json

logger = logging.getLogger(__name__)

HELPER_PAGE_TYPES = {
    "acba_seed_index",
    "acba_unstructured_page",
    "inecobank_branches_pending",
    "inecobank_unstructured_page",
}


class CleaningPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.ensure_runtime_dirs()
        self.cleaner = TextCleaner()

    def run(self, bank_name: str | None = None, topic: str | None = None) -> list[Path]:
        written_files: list[Path] = []
        for raw_file in iter_json_files(self.settings.raw_output_dir):
            payload = RawDocument(**read_json(raw_file))
            if bank_name and payload.bank_name.casefold() != bank_name.casefold():
                continue
            if topic and payload.topic != topic:
                continue
            output_path = self._output_path(payload.bank_name, payload.topic, raw_file.name)
            page_type = None
            if payload.structured_data:
                page_type = payload.structured_data.get("page_type")
            if page_type in HELPER_PAGE_TYPES:
                tombstone = CleanDocument(
                    bank_name=payload.bank_name,
                    topic=payload.topic,
                    source_url=payload.source_url,
                    page_title=payload.page_title,
                    clean_text="",
                    fetched_at=payload.fetched_at,
                    content_hash=payload.content_hash,
                )
                write_json(output_path, tombstone.to_dict())
                written_files.append(output_path)
                logger.info("Wrote tombstone clean JSON for helper raw file %s", raw_file)
                continue
            cleaned = self.cleaner.clean_document(payload)
            write_json(output_path, cleaned.to_dict())
            written_files.append(output_path)
            logger.info("Saved clean JSON to %s", output_path)
        return written_files

    def _output_path(self, bank_name: str, topic: str, filename: str) -> Path:
        return self.settings.clean_output_dir / slugify(bank_name) / topic / filename
