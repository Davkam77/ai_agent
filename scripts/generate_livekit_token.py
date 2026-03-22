from __future__ import annotations

import argparse

from app.bootstrap import build_settings
from app.voice.token import build_livekit_access_token


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a LiveKit access token for local testing.")
    parser.add_argument("--room", required=True, help="LiveKit room name.")
    parser.add_argument("--identity", required=True, help="Participant identity.")
    parser.add_argument("--hidden", action="store_true", help="Mark participant as hidden.")
    parser.add_argument("--agent", action="store_true", help="Mark participant as agent.")
    parser.add_argument("--ttl-hours", type=int, default=12, help="Token lifetime in hours.")
    args = parser.parse_args()

    settings = build_settings()
    token = build_livekit_access_token(
        settings,
        room_name=args.room,
        identity=args.identity,
        hidden=args.hidden,
        agent=args.agent,
        ttl_hours=args.ttl_hours,
    )
    print(token)


if __name__ == "__main__":
    main()
