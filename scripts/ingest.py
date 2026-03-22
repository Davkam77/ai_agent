from __future__ import annotations

import argparse

from app.bootstrap import build_ingestion_pipeline, build_settings
from app.logging_utils import configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Chunk, embed and ingest clean JSON into SQLite + local vectors.")
    parser.add_argument("--bank", dest="bank_name", help="Filter by bank name")
    parser.add_argument("--topic", help="Filter by topic")
    args = parser.parse_args()

    settings = build_settings()
    configure_logging(settings.log_level)
    pipeline = build_ingestion_pipeline(settings)
    files = pipeline.run(bank_name=args.bank_name, topic=args.topic)
    print(f"Processed {len(files)} clean files for ingestion")


if __name__ == "__main__":
    main()
