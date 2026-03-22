from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from app.models import ExtractionResult, SourceConfig, Topic
from app.utils import dedupe_lines, normalize_whitespace


@dataclass(frozen=True, slots=True)
class AcbaSelectors:
    product_title: str = ".template_head__title"
    product_summary: str = ".product__right__text-forHeight"
    product_cta: str = ".btn__tpl1"
    product_business_card_item: str = ".product__bus_cart__item-c"
    product_business_card_item_title: str = ".product__bus_cart__item-c__title"
    product_business_card_item_subtitle: str = ".product__bus_cart__item-c__sub_title"
    product_business_card_item_link: str = ".product__bus_cart__item-c__sub_link"
    product_tab_title: str = ".tabs__tpl1__tabs__item"
    product_tab_body: str = ".tabs__tpl1__bodys__item .txt__tpl1"
    last_update: str = "#update_info .update_info__text"
    branches_title: str = ".fb_branches__title__left"
    region_choices: str = "#f_regions .f_regionChoice"
    branch_cards: str = ".allBranches .fb_branch"
    branch_name: str = ".fb_branch__head__title"
    branch_place: str = ".fb_branch__place"
    branch_list_items: str = ".fb_branch__list__item"


class AcbaExtractor:
    def __init__(self) -> None:
        self.selectors = AcbaSelectors()

    def discover_child_urls(self, source: SourceConfig, html: str) -> list[str]:
        if not source.child_url_prefixes:
            return []
        soup = BeautifulSoup(html, "html.parser")
        urls: list[str] = []
        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "").strip()
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue
            absolute_url = self._resolve_url(source.source_url, href).split("#", 1)[0]
            if absolute_url == source.source_url:
                continue
            if any(absolute_url.startswith(prefix) for prefix in source.child_url_prefixes):
                urls.append(absolute_url)
        return self._dedupe_preserve_order(urls)

    def extract(self, source: SourceConfig, html: str) -> ExtractionResult:
        soup = BeautifulSoup(html, "html.parser")

        if source.topic == Topic.BRANCH_LOCATIONS or soup.select_one(self.selectors.branches_title):
            return self._extract_branches_page(soup)
        if self._looks_like_product_page(soup):
            return self._extract_product_page(source, soup)

        title = self._text_or_default(soup.select_one(self.selectors.product_title), "Acba page")
        return ExtractionResult(
            page_title=title,
            raw_text="",
            structured_data={"page_type": "acba_unstructured_page", "title": title},
            skip_document=True,
        )

    def _extract_product_page(self, source: SourceConfig, soup: BeautifulSoup) -> ExtractionResult:
        title = self._text_or_default(soup.select_one(self.selectors.product_title), "Acba product page")
        summary = self._text_or_default(soup.select_one(self.selectors.product_summary), "")
        last_update = self._text_or_default(soup.select_one(self.selectors.last_update), "")

        business_card: list[dict[str, str]] = []
        for item in soup.select(self.selectors.product_business_card_item):
            label = self._text_or_default(item.select_one(self.selectors.product_business_card_item_title), "")
            value = self._extract_business_card_value(item, soup)
            if label or value:
                business_card.append({"label": label, "value": value})

        tab_titles = [normalize_whitespace(node.get_text(" ", strip=True)) for node in soup.select(self.selectors.product_tab_title)]
        tab_bodies = soup.select(self.selectors.product_tab_body)
        tabs: list[dict[str, str]] = []
        for index in range(max(len(tab_titles), len(tab_bodies))):
            title_value = tab_titles[index] if index < len(tab_titles) else f"Tab {index + 1}"
            body_node = tab_bodies[index] if index < len(tab_bodies) else None
            content_html = body_node.decode_contents().strip() if body_node else ""
            content_text = normalize_whitespace(body_node.get_text("\n", strip=True)) if body_node else ""
            if title_value or content_html or content_text:
                tabs.append(
                    {
                        "title": title_value,
                        "content_html": content_html,
                        "content_text": content_text,
                    }
                )

        cta_links = self._extract_cta_links(source, soup)
        structured_data = {
            "page_type": "acba_product_page",
            "title": title,
            "summary": summary,
            "business_card": business_card,
            "tabs": tabs,
            "cta_links": cta_links,
            "last_update": last_update,
        }

        return ExtractionResult(
            page_title=title,
            raw_text=self._render_product_raw_text(structured_data),
            structured_data=structured_data,
        )

    def _extract_branches_page(self, soup: BeautifulSoup) -> ExtractionResult:
        page_title = self._text_or_default(soup.select_one(self.selectors.branches_title), "Branches")
        regions: list[dict[str, str | None]] = []
        for node in soup.select(self.selectors.region_choices):
            label = normalize_whitespace(node.get_text(" ", strip=True))
            if not label:
                continue
            region_id = None
            node_id = node.get("id", "")
            match = re.search(r"f_regionChoice_(\d+)", node_id)
            if match:
                region_id = match.group(1)
            regions.append({"label": label, "region_id": region_id})

        branches: list[dict[str, object]] = []
        for card in soup.select(self.selectors.branch_cards):
            container = card.parent if isinstance(card.parent, Tag) else None
            region_id = self._extract_region_id(container)
            branch_name = self._text_or_default(card.select_one(self.selectors.branch_name), "")
            city_or_place = self._text_or_default(card.select_one(self.selectors.branch_place), "")
            items = [
                normalize_whitespace(item.get_text(" ", strip=True))
                for item in card.select(self.selectors.branch_list_items)
                if normalize_whitespace(item.get_text(" ", strip=True))
            ]
            address = items[0] if items else ""
            schedule_lines = items[1:] if len(items) > 1 else []
            if not branch_name and not address:
                continue
            branches.append(
                {
                    "branch_name": branch_name,
                    "city_or_place": city_or_place,
                    "address": address,
                    "schedule_lines": schedule_lines,
                    "region_id": region_id,
                }
            )

        general_notes = self._extract_general_notes(soup)
        structured_data = {
            "page_type": "acba_branches_page",
            "page_title": page_title,
            "regions": regions,
            "branches": branches,
            "general_notes": general_notes,
        }

        return ExtractionResult(
            page_title=page_title,
            raw_text=self._render_branches_raw_text(structured_data),
            structured_data=structured_data,
        )

    def _extract_business_card_value(self, item: Tag, soup: BeautifulSoup) -> str:
        subtitle = item.select_one(self.selectors.product_business_card_item_subtitle)
        if subtitle:
            return normalize_whitespace(subtitle.get_text(" ", strip=True))

        link = item.select_one(self.selectors.product_business_card_item_link)
        if not link:
            return ""

        target_id = link.get("href", "").strip().lstrip("#")
        if target_id:
            hidden_root = item.find(id=target_id) or soup.find(id=target_id)
            if hidden_root:
                hidden_text_node = hidden_root.select_one(".wizGuide__text")
                if hidden_text_node:
                    return normalize_whitespace(hidden_text_node.get_text("\n", strip=True))
        return normalize_whitespace(link.get_text(" ", strip=True))

    def _extract_cta_links(self, source: SourceConfig, soup: BeautifulSoup) -> list[dict[str, str]]:
        links: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for button in soup.select(self.selectors.product_cta):
            if self._is_navigation_button(button):
                continue
            label = normalize_whitespace(button.get_text(" ", strip=True))
            href = button.get("href", "").strip()
            if not label or not href:
                continue
            absolute_href = self._resolve_url(source.source_url, href)
            key = (label, absolute_href)
            if key in seen:
                continue
            seen.add(key)
            links.append({"label": label, "href": absolute_href})
        return links

    def _extract_general_notes(self, soup: BeautifulSoup) -> list[str]:
        notes: list[str] = []
        for node in soup.find_all("div"):
            if node.select_one(".fb_branch"):
                continue
            text = normalize_whitespace(node.get_text("\n", strip=True))
            if not text:
                continue
            if "To contact any branch of the Bank you can call" in text:
                notes.append(text)
            if "There are cash-in terminals in all branches of the Bank." in text:
                notes.append(text)
        row = soup.select_one(".fb_branches .row.flex-container")
        if row:
            for child in row.find_all("div", recursive=False):
                if child.select_one(".fb_branch"):
                    continue
                text = normalize_whitespace(child.get_text("\n", strip=True))
                if text:
                    notes.append(text)
        return dedupe_lines(notes)

    def _render_product_raw_text(self, payload: dict[str, object]) -> str:
        lines: list[str] = []
        title = str(payload.get("title", "")).strip()
        summary = str(payload.get("summary", "")).strip()
        last_update = str(payload.get("last_update", "")).strip()
        if title:
            lines.append(title)
        if summary:
            lines.append(summary)
        business_card = payload.get("business_card", [])
        if isinstance(business_card, list) and business_card:
            lines.append("Business card")
            for item in business_card:
                if isinstance(item, dict):
                    label = str(item.get("label", "")).strip()
                    value = str(item.get("value", "")).strip()
                    if label or value:
                        lines.append(f"{label}: {value}".strip(": "))
        tabs = payload.get("tabs", [])
        if isinstance(tabs, list):
            for tab in tabs:
                if not isinstance(tab, dict):
                    continue
                tab_title = str(tab.get("title", "")).strip()
                tab_text = str(tab.get("content_text", "")).strip()
                if tab_title:
                    lines.append(f"Tab: {tab_title}")
                if tab_text:
                    lines.append(tab_text)
        cta_links = payload.get("cta_links", [])
        if isinstance(cta_links, list) and cta_links:
            lines.append("CTA links")
            for item in cta_links:
                if isinstance(item, dict):
                    label = str(item.get("label", "")).strip()
                    href = str(item.get("href", "")).strip()
                    if label or href:
                        lines.append(f"{label}: {href}".strip(": "))
        if last_update:
            lines.append(f"Last updated: {last_update}")
        return "\n".join(dedupe_lines(lines))

    def _render_branches_raw_text(self, payload: dict[str, object]) -> str:
        lines: list[str] = []
        page_title = str(payload.get("page_title", "")).strip()
        if page_title:
            lines.append(page_title)
        regions = payload.get("regions", [])
        if isinstance(regions, list) and regions:
            lines.append("Regions")
            for region in regions:
                if isinstance(region, dict):
                    label = str(region.get("label", "")).strip()
                    region_id = str(region.get("region_id", "") or "").strip()
                    lines.append(f"{label} ({region_id})" if region_id else label)
        general_notes = payload.get("general_notes", [])
        if isinstance(general_notes, list):
            lines.extend(str(note).strip() for note in general_notes if str(note).strip())
        branches = payload.get("branches", [])
        if isinstance(branches, list):
            for branch in branches:
                if not isinstance(branch, dict):
                    continue
                branch_name = str(branch.get("branch_name", "")).strip()
                city_or_place = str(branch.get("city_or_place", "")).strip()
                address = str(branch.get("address", "")).strip()
                region_id = str(branch.get("region_id", "") or "").strip()
                schedule_lines = branch.get("schedule_lines", [])
                header = branch_name
                if city_or_place:
                    header = f"{header} | {city_or_place}" if header else city_or_place
                if region_id:
                    header = f"{header} | region_id={region_id}" if header else f"region_id={region_id}"
                if header:
                    lines.append(header)
                if address:
                    lines.append(f"Address: {address}")
                if isinstance(schedule_lines, list):
                    for schedule in schedule_lines:
                        schedule_text = str(schedule).strip()
                        if schedule_text:
                            lines.append(f"Schedule: {schedule_text}")
        return "\n".join(dedupe_lines(lines))

    @staticmethod
    def _extract_region_id(container: Tag | None) -> str | None:
        if not container:
            return None
        classes = container.get("class", [])
        for class_name in classes:
            match = re.fullmatch(r"branchRegion_(\d+)", class_name)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _is_navigation_button(button: Tag) -> bool:
        for ancestor in button.parents:
            if not isinstance(ancestor, Tag):
                continue
            if ancestor.name in {"header", "footer", "nav"}:
                return True
            class_blob = " ".join(ancestor.get("class", []))
            if any(token in class_blob for token in ("header", "slideMenu", "footer")):
                return True
        return False

    @staticmethod
    def _looks_like_product_page(soup: BeautifulSoup) -> bool:
        selectors = AcbaSelectors()
        if not soup.select_one(selectors.product_title):
            return False
        return bool(
            soup.select_one(selectors.product_summary)
            or soup.select_one(selectors.product_business_card_item)
            or soup.select_one(selectors.product_tab_title)
            or soup.select_one(selectors.product_tab_body)
        )

    @staticmethod
    def _text_or_default(node: Tag | None, default: str) -> str:
        if not node:
            return default
        return normalize_whitespace(node.get_text(" ", strip=True)) or default

    @staticmethod
    def _resolve_url(base_url: str, href: str) -> str:
        if href.startswith(("http://", "https://")):
            return href
        parsed = urlparse(base_url)
        site_root = f"{parsed.scheme}://{parsed.netloc}/"
        if href.startswith("/"):
            return urljoin(site_root, href.lstrip("/"))
        if re.match(r"^[a-z]{2}/", href):
            return urljoin(site_root, href)
        return urljoin(base_url, href)

    @staticmethod
    def _dedupe_preserve_order(values: list[str]) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            output.append(value)
        return output
