from __future__ import annotations

import argparse

from app.bootstrap import build_scraping_pipeline, build_settings
from app.logging_utils import configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape official bank pages into raw JSON.")
    parser.add_argument("--bank", dest="bank_name", help="Filter by bank name")
    parser.add_argument("--topic", help="Filter by topic")
    args = parser.parse_args()

    settings = build_settings()
    configure_logging(settings.log_level)
    pipeline = build_scraping_pipeline(settings)
    files = pipeline.run(bank_name=args.bank_name, topic=args.topic)
    print(f"Scraped {len(files)} source files")


if __name__ == "__main__":
    main()
