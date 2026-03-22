from __future__ import annotations

import argparse

from app.bootstrap import build_demo_stack_supervisor, build_settings
from app.logging_utils import configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Telegram text demo and LiveKit voice runtime together.")
    parser.add_argument("--room", dest="room_name", help="LiveKit room name override.")
    parser.add_argument("--identity", dest="identity", help="LiveKit participant identity override.")
    args = parser.parse_args()

    settings = build_settings()
    if args.room_name:
        settings.livekit_room_name = args.room_name
    if args.identity:
        settings.livekit_agent_identity = args.identity

    configure_logging(settings.log_level, settings.voice_transport_log_level)
    supervisor = build_demo_stack_supervisor(
        settings,
        room_name=settings.livekit_room_name,
        agent_identity=settings.livekit_agent_identity,
    )
    raise SystemExit(supervisor.run())


if __name__ == "__main__":
    main()
