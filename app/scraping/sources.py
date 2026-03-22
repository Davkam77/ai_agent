from __future__ import annotations

from app.models import SourceConfig, Topic


BANK_SOURCES: tuple[SourceConfig, ...] = (
    SourceConfig(
        bank_name="Acba",
        topic=Topic.CREDITS,
        source_url="https://www.acba.am/en/individuals/loans",
        fetcher="requests",
        extractor="acba",
        expand_urls=True,
        child_url_prefixes=("https://www.acba.am/en/individuals/loans/",),
    ),
    SourceConfig(
        bank_name="Acba",
        topic=Topic.DEPOSITS,
        source_url="https://www.acba.am/en/individuals/save-and-invest/deposits",
        fetcher="requests",
        extractor="acba",
        expand_urls=True,
        child_url_prefixes=("https://www.acba.am/en/individuals/save-and-invest/deposits/",),
    ),
    SourceConfig(
        bank_name="Acba",
        topic=Topic.BRANCH_LOCATIONS,
        source_url="https://www.acba.am/en/about-bank/Branches-and-ATMs",
        fetcher="requests",
        extractor="acba",
    ),
    SourceConfig(
        bank_name="Ameriabank",
        topic=Topic.CREDITS,
        source_url="https://ameriabank.am/en/personal/loans/consumer-loans/consumer-loans",
        fetcher="requests",
        extractor="ameria",
        content_selectors=(".banner-main__content", ".faq", "body"),
    ),
    SourceConfig(
        bank_name="Ameriabank",
        topic=Topic.DEPOSITS,
        source_url="https://ameriabank.am/en/personal/saving/deposits/see-all",
        fetcher="requests",
        extractor="ameria",
    ),
    SourceConfig(
        bank_name="Ameriabank",
        topic=Topic.BRANCH_LOCATIONS,
        source_url="https://ameriabank.am/en/service-network",
        fetcher="requests",
        extractor="ameria",
    ),
    SourceConfig(
        bank_name="Inecobank",
        topic=Topic.CREDITS,
        source_url="https://www.inecobank.am/en/Individual/consumer-loans",
        fetcher="requests",
        extractor="inecobank",
        content_selectors=("main",),
    ),
    SourceConfig(
        bank_name="Inecobank",
        topic=Topic.DEPOSITS,
        source_url="https://www.inecobank.am/en/Individual/deposits",
        fetcher="requests",
        extractor="inecobank",
        content_selectors=("main",),
    ),
    SourceConfig(
        bank_name="Inecobank",
        topic=Topic.BRANCH_LOCATIONS,
        source_url="https://www.inecobank.am/en/map",
        fetcher="requests",
        extractor="inecobank",
    ),
)


def get_sources(bank_name: str | None = None, topic: str | None = None) -> list[SourceConfig]:
    output: list[SourceConfig] = []
    for source in BANK_SOURCES:
        if bank_name and source.bank_name.casefold() != bank_name.casefold():
            continue
        if topic and source.topic.value != topic:
            continue
        output.append(source)
    return output
