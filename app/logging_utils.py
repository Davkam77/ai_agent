from __future__ import annotations

import logging


NOISY_TRANSPORT_LOGGERS = (
    "aioice",
    "aiortc",
    "asyncio",
    "httpcore",
    "httpx",
    "livekit",
    "livekit.api",
    "livekit.rtc",
    "websockets",
)


def configure_logging(level: str, transport_level: str = "WARNING") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        force=True,
    )
    resolved_transport_level = getattr(logging, transport_level.upper(), logging.WARNING)
    for logger_name in NOISY_TRANSPORT_LOGGERS:
        logging.getLogger(logger_name).setLevel(resolved_transport_level)
