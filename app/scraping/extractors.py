from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod

from bs4 import BeautifulSoup

from app.models import ExtractionResult, SourceConfig, Topic
from app.utils import dedupe_lines, flatten_json_strings, normalize_whitespace

logger = logging.getLogger(__name__)


def _split_lines(value: str) -> list[str]:
    text = normalize_whitespace(value.replace("\xa0", " "))
    return [line.strip() for line in text.splitlines() if line.strip()]


def _title_from_soup(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.get_text(strip=True):
        return soup.title.get_text(" ", strip=True)
    heading = soup.select_one("h1")
    return heading.get_text(" ", strip=True) if heading else "Untitled page"


def _meta_description(soup: BeautifulSoup) -> str:
    meta = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta",
        attrs={"property": "og:description"},
    )
    if not meta:
        return ""
    return normalize_whitespace(meta.get("content", ""))


def _remove_noise_tags(soup: BeautifulSoup) -> None:
    for tag_name in ("script", "style", "noscript", "svg", "img", "form", "button"):
        for tag in soup.find_all(tag_name):
            tag.decompose()
    for selector in ("nav", "header", "footer"):
        for tag in soup.select(selector):
            tag.decompose()


def _extract_json_ld_lines(soup: BeautifulSoup) -> list[str]:
    lines: list[str] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.get_text(strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug("Skipping invalid JSON-LD block")
            continue
        strings = [
            normalize_whitespace(item)
            for item in flatten_json_strings(payload)
            if isinstance(item, str) and len(item.strip()) > 5
        ]
        lines.extend(strings)
    return dedupe_lines(lines)


def _extract_candidate_blocks(soup: BeautifulSoup, selectors: tuple[str, ...]) -> list[str]:
    selectors_to_try = selectors or ("main", "article", "[role=main]", ".main-content", ".content", "body")
    blocks: list[str] = []
    for selector in selectors_to_try:
        for node in soup.select(selector):
            text = node.get_text("\n", strip=True)
            if len(text.strip()) >= 80:
                blocks.append(text)
        if blocks:
            break
    if not blocks:
        blocks.append(soup.get_text("\n", strip=True))
    return blocks


class SourceExtractor(ABC):
    @abstractmethod
    def extract(self, source: SourceConfig, html: str) -> ExtractionResult:
        raise NotImplementedError


class GenericExtractor(SourceExtractor):
    def extract(self, source: SourceConfig, html: str) -> ExtractionResult:
        soup = BeautifulSoup(html, "html.parser")
        title = _title_from_soup(soup)
        description = _meta_description(soup)
        json_ld_lines = _extract_json_ld_lines(soup)

        working_soup = BeautifulSoup(html, "html.parser")
        _remove_noise_tags(working_soup)
        blocks = _extract_candidate_blocks(working_soup, source.content_selectors)

        lines: list[str] = []
        if title:
            lines.append(title)
        if description:
            lines.append(description)
        lines.extend(json_ld_lines)
        for block in blocks:
            lines.extend(_split_lines(block))

        return ExtractionResult(
            page_title=title,
            raw_text="\n".join(dedupe_lines(lines)),
        )


class AmeriaExtractor(SourceExtractor):
    def extract(self, source: SourceConfig, html: str) -> ExtractionResult:
        soup = BeautifulSoup(html, "html.parser")
        title = _title_from_soup(soup)
        description = _meta_description(soup)
        lines: list[str] = [item for item in (title, description) if item]
        lines.extend(_extract_json_ld_lines(soup))

        for selector in (".banner-main__content", ".banner-main", "h1", "h2", ".faq", ".accordion"):
            for node in soup.select(selector):
                text = node.get_text("\n", strip=True)
                if text:
                    lines.extend(_split_lines(text))

        href_fragments: tuple[str, ...]
        if source.topic == Topic.CREDITS:
            href_fragments = ("/personal/loans/", "/loans/")
        elif source.topic == Topic.DEPOSITS:
            href_fragments = ("/personal/saving/deposits/", "/accounts/accounts/saving-account", "/avandi-hashvich")
        else:
            href_fragments = ()

        if href_fragments:
            for anchor in soup.find_all("a", href=True):
                href = anchor["href"]
                if any(fragment in href for fragment in href_fragments):
                    text = anchor.get_text(" ", strip=True)
                    if text:
                        lines.append(text)

        if source.topic == Topic.BRANCH_LOCATIONS:
            body_text = soup.get_text("\n", strip=True)
            for line in _split_lines(body_text):
                lowered = line.casefold()
                if any(keyword in lowered for keyword in ("head office", "street", "phone", "@", "branch", "atm")):
                    lines.append(line)

        return ExtractionResult(
            page_title=title,
            raw_text="\n".join(dedupe_lines(lines)),
        )


class ExtractorRegistry:
    def __init__(self) -> None:
        from app.scraping.acba_extractor import AcbaExtractor
        from app.scraping.inecobank_extractor import InecobankExtractor

        self._extractors: dict[str, SourceExtractor] = {
            "generic": GenericExtractor(),
            "acba": AcbaExtractor(),
            "ameria": AmeriaExtractor(),
            "inecobank": InecobankExtractor(),
        }

    def get(self, name: str) -> SourceExtractor:
        try:
            return self._extractors[name]
        except KeyError as exc:
            raise KeyError(f"Unknown extractor: {name}") from exc
