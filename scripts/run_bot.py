from __future__ import annotations

import logging

from app.bootstrap import build_settings, build_support_agent
from app.logging_utils import configure_logging
from app.telegram_ui.bot import TelegramDemoBot

logger = logging.getLogger(__name__)


def main() -> None:
    settings = build_settings()
    configure_logging(settings.log_level, settings.voice_transport_log_level)
    logger.info(
        "Starting Telegram text demo runtime telegram_text_active=%s telegram_voice_supported=%s "
        "telegram_token_configured=%s openai_configured=%s transport_log_level=%s database=%s vector_store=%s",
        True,
        False,
        bool(settings.telegram_bot_token),
        bool(settings.openai_api_key),
        settings.voice_transport_log_level,
        settings.database_path,
        settings.vector_store_dir,
    )
    support_agent = build_support_agent(settings)
    TelegramDemoBot(settings, support_agent).run()


if __name__ == "__main__":
    main()
