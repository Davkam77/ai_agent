from __future__ import annotations

import argparse
import logging
import webbrowser

from app.bootstrap import build_livekit_test_ui_server, build_settings
from app.logging_utils import configure_logging

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local LiveKit voice test UI.")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP host for the local UI.")
    parser.add_argument("--port", type=int, default=8766, help="HTTP port for the local UI.")
    parser.add_argument("--room", dest="room_name", help="Default LiveKit room name override.")
    parser.add_argument("--open-browser", action="store_true", help="Open the local UI in the default browser.")
    args = parser.parse_args()

    settings = build_settings()
    if args.room_name:
        settings.livekit_room_name = args.room_name

    configure_logging(settings.log_level, settings.voice_transport_log_level)
    server = build_livekit_test_ui_server(
        settings,
        host=args.host,
        port=args.port,
        room_name=settings.livekit_room_name,
    )

    logger.info(
        "Starting local LiveKit test UI ui_url=%s livekit_url=%s room=%s token_generation_available=%s transport_log_level=%s "
        "voice_quality_mode=%s browser_echo_cancellation=%s browser_noise_suppression=%s browser_auto_gain_control=%s "
        "browser_audio_sample_rate=%s browser_audio_channel_count=%s",
        server.ui_url,
        settings.livekit_url,
        settings.livekit_room_name,
        bool(settings.livekit_api_key and settings.livekit_api_secret),
        settings.voice_transport_log_level,
        settings.voice_high_quality_mode,
        settings.browser_echo_cancellation,
        settings.browser_noise_suppression,
        settings.browser_auto_gain_control,
        settings.browser_audio_sample_rate,
        settings.browser_audio_channel_count,
    )

    if args.open_browser:
        webbrowser.open(server.ui_url)

    server.serve_forever()


if __name__ == "__main__":
    main()
