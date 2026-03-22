from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.models import ExtractionResult, SourceConfig, Topic
from app.utils import dedupe_lines, normalize_whitespace


@dataclass(frozen=True, slots=True)
class InecobankSelectors:
    deposit_group: str = ".depositGroup"
    deposit_group_title: str = ".depositGroup__title"
    loan_group: str = ".loanGroup"
    loan_group_title: str = ".loanGroup__title"
    product_list: str = ".productList"
    product_card: str = ".productList__item"
    product_title: str = ".productInfo__title"
    product_description: str = ".rawContent__content"
    product_tags: str = ".tagGroup__item .tag"
    feature_items: str = ".featureGroup__item .feature"
    feature_value: str = ".feature__title"
    feature_postfix: str = ".feature__titlePostfix"
    feature_label: str = ".feature__subtitle"
    deposit_details_link: str = '.productInfo__actions a.btn__link[href*="/en/Individual/deposits/"]'
    deposit_apply_link: str = '.productInfo__actions a.btn__link[href*="reg.inecobank.am"]'
    loan_details_link: str = '.productInfo__actions a.btn__link[href*="/en/Individual/consumer-loans/"]'
    loan_apply_link: str = '.productInfo__actions a.btn__link:not([href*="/en/Individual/consumer-loans/"])'
    image: str = ".productBanner__image[src]"
    ignored_ui_selectors: tuple[str, ...] = (
        ".filter",
        ".currencyGroup",
        ".inputSlider",
        "input[type=checkbox]",
        ".checkbox",
    )


class InecobankExtractor:
    def __init__(self) -> None:
        self.selectors = InecobankSelectors()

    def extract(self, source: SourceConfig, html: str) -> ExtractionResult:
        soup = BeautifulSoup(html, "html.parser")
        page_title = self._page_title(soup)

        if source.topic == Topic.BRANCH_LOCATIONS:
            return self._extract_branches_placeholder(source, page_title)

        if source.topic == Topic.DEPOSITS:
            sections = self._extract_sections(
                source=source,
                soup=soup,
                group_selector=self.selectors.deposit_group,
                title_selector=self.selectors.deposit_group_title,
                details_selector=self.selectors.deposit_details_link,
                apply_selector=self.selectors.deposit_apply_link,
            )
        elif source.topic == Topic.CREDITS:
            sections = self._extract_sections(
                source=source,
                soup=soup,
                group_selector=self.selectors.loan_group,
                title_selector=self.selectors.loan_group_title,
                details_selector=self.selectors.loan_details_link,
                apply_selector=self.selectors.loan_apply_link,
            )
        else:
            return self._extract_unstructured_page(source, page_title, "unsupported_topic")

        if not any(section["products"] for section in sections):
            return self._extract_unstructured_page(source, page_title, "no_product_cards_found")

        structured_data = {
            "page_type": "inecobank_product_list_page",
            "bank_name": source.bank_name,
            "topic": source.topic.value,
            "page_title": page_title,
            "sections": sections,
        }
        return ExtractionResult(
            page_title=page_title,
            raw_text=self._render_product_list_raw_text(structured_data),
            structured_data=structured_data,
        )

    def _extract_sections(
        self,
        source: SourceConfig,
        soup: BeautifulSoup,
        group_selector: str,
        title_selector: str,
        details_selector: str,
        apply_selector: str,
    ) -> list[dict[str, object]]:
        sections: list[dict[str, object]] = []
        for index, group in enumerate(soup.select(group_selector), start=1):
            section_title = self._text_or_default(
                group.select_one(title_selector),
                f"{source.topic.value.replace('_', ' ').title()} section {index}",
            )
            products: list[dict[str, object]] = []
            for product_list in group.select(self.selectors.product_list):
                for card in product_list.select(self.selectors.product_card):
                    product = self._extract_product_card(
                        source=source,
                        card=card,
                        section_title=section_title,
                        details_selector=details_selector,
                        apply_selector=apply_selector,
                    )
                    if product:
                        products.append(product)
            sections.append({"section_title": section_title, "products": products})
        return sections

    def _extract_product_card(
        self,
        source: SourceConfig,
        card: Tag,
        section_title: str,
        details_selector: str,
        apply_selector: str,
    ) -> dict[str, object] | None:
        product_title = self._text_or_default(card.select_one(self.selectors.product_title), "")
        description_lines = [
            normalize_whitespace(node.get_text("\n", strip=True))
            for node in card.select(self.selectors.product_description)
            if normalize_whitespace(node.get_text("\n", strip=True))
        ]
        description = "\n".join(dedupe_lines(description_lines))

        tags = dedupe_lines(
            [
                normalize_whitespace(node.get_text(" ", strip=True))
                for node in card.select(self.selectors.product_tags)
                if normalize_whitespace(node.get_text(" ", strip=True))
            ]
        )

        features: list[dict[str, str]] = []
        for feature in card.select(self.selectors.feature_items):
            value = self._compose_feature_value(feature)
            label = self._text_or_default(feature.select_one(self.selectors.feature_label), "")
            if label or value:
                features.append({"label": label, "value": value})

        details_url = self._extract_link(source.source_url, card.select_one(details_selector))
        apply_url = self._extract_link(source.source_url, card.select_one(apply_selector))
        image_url = self._extract_image_url(source.source_url, card.select_one(self.selectors.image))

        if not any((product_title, description, tags, features, details_url, apply_url, image_url)):
            return None

        return {
            "bank_name": source.bank_name,
            "topic": source.topic.value,
            "section_title": section_title,
            "product_title": product_title,
            "description": description,
            "tags": tags,
            "features": features,
            "details_url": details_url,
            "apply_url": apply_url,
            "image_url": image_url,
            "source_url": source.source_url,
        }

    def _extract_branches_placeholder(self, source: SourceConfig, page_title: str) -> ExtractionResult:
        structured_data = {
            "page_type": "inecobank_branches_pending",
            "bank_name": source.bank_name,
            "topic": source.topic.value,
            "page_title": page_title,
            "source_url": source.source_url,
            "status": "pending",
            "reason": (
                "The current /en/map HTML is mostly Google Maps rendering and controls. "
                "A stable list-view DOM or a documented XHR dataset is required before "
                "branch extraction can be enabled."
            ),
        }
        raw_text = "\n".join(
            [
                page_title,
                "Inecobank branch extraction is pending.",
                "The current /en/map page is mostly Google Maps rendering and UI controls.",
                "A stable list-view DOM selector set or a documented XHR branch dataset is required.",
            ]
        )
        return ExtractionResult(
            page_title=page_title,
            raw_text=raw_text,
            structured_data=structured_data,
        )

    def _extract_unstructured_page(self, source: SourceConfig, page_title: str, reason: str) -> ExtractionResult:
        structured_data = {
            "page_type": "inecobank_unstructured_page",
            "bank_name": source.bank_name,
            "topic": source.topic.value,
            "page_title": page_title,
            "source_url": source.source_url,
            "reason": reason,
        }
        raw_text = "\n".join(
            [
                page_title,
                "Inecobank list-page extraction did not produce normalized product cards.",
                f"Reason: {reason}",
            ]
        )
        return ExtractionResult(
            page_title=page_title,
            raw_text=raw_text,
            structured_data=structured_data,
        )

    def _render_product_list_raw_text(self, payload: dict[str, object]) -> str:
        lines: list[str] = []
        page_title = str(payload.get("page_title", "")).strip()
        if page_title:
            lines.append(page_title)

        sections = payload.get("sections", [])
        if isinstance(sections, list):
            for section in sections:
                if not isinstance(section, dict):
                    continue
                section_title = str(section.get("section_title", "")).strip()
                if section_title:
                    lines.append(f"Section: {section_title}")
                products = section.get("products", [])
                if not isinstance(products, list):
                    continue
                for product in products:
                    if not isinstance(product, dict):
                        continue
                    product_title = str(product.get("product_title", "")).strip()
                    description = str(product.get("description", "")).strip()
                    details_url = str(product.get("details_url", "")).strip()
                    apply_url = str(product.get("apply_url", "")).strip()
                    image_url = str(product.get("image_url", "")).strip()
                    tags = product.get("tags", [])
                    features = product.get("features", [])

                    if product_title:
                        lines.append(f"Product: {product_title}")
                    if description:
                        lines.append(description)
                    if isinstance(tags, list) and tags:
                        lines.append(f"Tags: {', '.join(str(tag).strip() for tag in tags if str(tag).strip())}")
                    if isinstance(features, list):
                        for feature in features:
                            if not isinstance(feature, dict):
                                continue
                            label = str(feature.get("label", "")).strip()
                            value = str(feature.get("value", "")).strip()
                            if label and value:
                                lines.append(f"{label}: {value}")
                            elif value:
                                lines.append(value)
                    if details_url:
                        lines.append(f"Details URL: {details_url}")
                    if apply_url:
                        lines.append(f"Apply URL: {apply_url}")
                    if image_url:
                        lines.append(f"Image URL: {image_url}")
        return "\n".join(dedupe_lines(lines))

    def _compose_feature_value(self, feature: Tag) -> str:
        value = self._text_or_default(feature.select_one(self.selectors.feature_value), "")
        postfix = self._text_or_default(feature.select_one(self.selectors.feature_postfix), "")
        return normalize_whitespace(" ".join(part for part in (value, postfix) if part))

    @staticmethod
    def _extract_link(base_url: str, node: Tag | None) -> str:
        if not node:
            return ""
        href = node.get("href", "").strip()
        if not href:
            return ""
        return urljoin(base_url, href)

    @staticmethod
    def _extract_image_url(base_url: str, node: Tag | None) -> str:
        if not node:
            return ""
        src = node.get("src", "").strip()
        if not src:
            return ""
        return urljoin(base_url, src)

    @staticmethod
    def _page_title(soup: BeautifulSoup) -> str:
        if soup.title and soup.title.get_text(strip=True):
            return normalize_whitespace(soup.title.get_text(" ", strip=True))
        heading = soup.select_one("h1")
        if heading:
            return normalize_whitespace(heading.get_text(" ", strip=True))
        return "Inecobank page"

    @staticmethod
    def _text_or_default(node: Tag | None, default: str) -> str:
        if not node:
            return default
        return normalize_whitespace(node.get_text(" ", strip=True)) or default
