from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Final

import cloudscraper
import requests
import logging

from app.models import SourceConfig

logger = logging.getLogger(__name__)


DEFAULT_HEADERS: Final[dict[str, str]] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


class PageFetcher(ABC):
    @abstractmethod
    def fetch(self, source: SourceConfig) -> str:
        raise NotImplementedError


class RequestsFetcher(PageFetcher):
    def __init__(self, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.cloudflare_fallback = CloudscraperFetcher(timeout_seconds=timeout_seconds)

    def fetch(self, source: SourceConfig) -> str:
        response = self.session.get(source.source_url, timeout=self.timeout_seconds)
        if source.bank_name.casefold() == "inecobank" and self._should_fallback_to_cloudscraper(response):
            logger.warning(
                "Requests fetch hit Cloudflare for %s on %s; retrying with cloudscraper",
                source.bank_name,
                source.source_url,
            )
            return self.cloudflare_fallback.fetch(source)
        response.raise_for_status()
        if response.apparent_encoding:
            response.encoding = response.apparent_encoding
        if source.bank_name.casefold() == "acba":
            return response.content.decode("utf-8", errors="replace")
        return response.text

    @staticmethod
    def _should_fallback_to_cloudscraper(response: requests.Response) -> bool:
        if response.status_code == 403:
            return True
        snippet = response.text[:500]
        return "Just a moment..." in snippet or "cf-browser-verification" in snippet


class CloudscraperFetcher(PageFetcher):
    def __init__(self, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = timeout_seconds
        self.scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "desktop": True},
        )
        self.scraper.headers.update(DEFAULT_HEADERS)

    def fetch(self, source: SourceConfig) -> str:
        response = self.scraper.get(source.source_url, timeout=self.timeout_seconds)
        response.raise_for_status()
        if response.apparent_encoding:
            response.encoding = response.apparent_encoding
        return response.text
