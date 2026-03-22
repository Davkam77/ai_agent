from __future__ import annotations

from app.bootstrap import build_settings
from app.logging_utils import configure_logging
from app.storage.db import initialize_database


def main() -> None:
    settings = build_settings()
    configure_logging(settings.log_level)
    initialize_database(settings.database_path)
    print(f"Initialized SQLite metadata database at {settings.database_path}")


if __name__ == "__main__":
    main()
