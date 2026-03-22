from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse

from app.config.settings import Settings
from app.models import RawDocument, SourceConfig
from app.scraping.extractors import ExtractorRegistry
from app.scraping.fetchers import CloudscraperFetcher, RequestsFetcher
from app.scraping.sources import get_sources
from app.utils import sha256_text, slugify, utc_now_iso, write_json

logger = logging.getLogger(__name__)


class ScrapingPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.ensure_runtime_dirs()
        self.extractors = ExtractorRegistry()
        self.fetchers = {
            "requests": RequestsFetcher(),
            "cloudscraper": CloudscraperFetcher(),
        }

    def run(self, bank_name: str | None = None, topic: str | None = None) -> list[Path]:
        written_files: list[Path] = []
        for source in get_sources(bank_name=bank_name, topic=topic):
            try:
                written_files.extend(self._scrape_source(source))
            except Exception:
                logger.exception("Failed to scrape %s %s", source.bank_name, source.source_url)
        return written_files

    def _scrape_source(self, source: SourceConfig) -> list[Path]:
        logger.info("Scraping %s | %s", source.bank_name, source.source_url)
        extractor = self.extractors.get(source.extractor)
        html = self.fetchers[source.fetcher].fetch(source)
        if source.expand_urls and hasattr(extractor, "discover_child_urls"):
            child_urls = extractor.discover_child_urls(source, html)
            if child_urls:
                written_files: list[Path] = []
                logger.info("Discovered %s child pages for %s", len(child_urls), source.source_url)
                index_text = "Discovered child pages\n" + "\n".join(child_urls)
                index_payload = RawDocument(
                    bank_name=source.bank_name,
                    topic=source.topic.value,
                    source_url=source.source_url,
                    page_title=f"{source.bank_name} {source.topic.value} seed index",
                    raw_text=index_text,
                    fetched_at=utc_now_iso(),
                    content_hash=sha256_text(index_text),
                    structured_data={"page_type": "acba_seed_index", "child_urls": child_urls},
                )
                index_output_path = self._build_output_path(source)
                write_json(index_output_path, index_payload.to_dict())
                written_files.append(index_output_path)
                for child_url in child_urls:
                    child_source = replace(source, source_url=child_url, expand_urls=False)
                    written_files.extend(self._scrape_source(child_source))
                return written_files

        extraction = extractor.extract(source, html)
        if extraction.skip_document:
            logger.info("Skipping unstructured page %s", source.source_url)
            return []

        payload = RawDocument(
            bank_name=source.bank_name,
            topic=source.topic.value,
            source_url=source.source_url,
            page_title=extraction.page_title,
            raw_text=extraction.raw_text,
            fetched_at=utc_now_iso(),
            content_hash=sha256_text(extraction.raw_text),
            structured_data=extraction.structured_data,
        )
        output_path = self._build_output_path(source)
        write_json(output_path, payload.to_dict())
        logger.info("Saved raw JSON to %s", output_path)
        return [output_path]

    def _build_output_path(self, source: SourceConfig) -> Path:
        parsed = urlparse(source.source_url)
        slug_source = slugify(parsed.path.replace("/", "-"))
        return (
            self.settings.raw_output_dir
            / slugify(source.bank_name)
            / source.topic.value
            / f"{slug_source}.json"
        )
