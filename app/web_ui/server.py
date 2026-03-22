from __future__ import annotations

import json
import logging
import secrets
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from typing import Any
from urllib.parse import urlparse

from app.config.settings import Settings
from app.voice.token import build_livekit_access_token

logger = logging.getLogger(__name__)

STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}


@dataclass(slots=True)
class LiveKitTestUIServer:
    settings: Settings
    host: str = "127.0.0.1"
    port: int = 8766
    room_name: str | None = None
    identity_prefix: str = "web-user"

    @property
    def ui_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def build_client_config(self) -> dict[str, Any]:
        return {
            "livekitUrl": self.settings.livekit_url,
            "roomName": self.room_name or self.settings.livekit_room_name,
            "suggestedIdentity": f"{self.identity_prefix}-{secrets.token_hex(3)}",
            "tokenEndpoint": "/api/token",
            "canGenerateToken": bool(
                self.settings.livekit_url and self.settings.livekit_api_key and self.settings.livekit_api_secret
            ),
            "voiceQualityMode": "high_quality" if self.settings.voice_high_quality_mode else "balanced",
            "audioCaptureOptions": {
                "echoCancellation": self.settings.browser_echo_cancellation,
                "noiseSuppression": self.settings.browser_noise_suppression,
                "autoGainControl": self.settings.browser_auto_gain_control,
                "sampleRate": self.settings.browser_audio_sample_rate,
                "channelCount": self.settings.browser_audio_channel_count,
            },
        }

    def generate_participant_token(self, room_name: str, identity: str) -> str:
        resolved_room_name = room_name.strip()
        resolved_identity = identity.strip()
        if not resolved_room_name:
            raise ValueError("room_name is required")
        if not resolved_identity:
            raise ValueError("identity is required")
        return build_livekit_access_token(
            self.settings,
            room_name=resolved_room_name,
            identity=resolved_identity,
        )

    def serve_forever(self) -> None:
        server = self.create_http_server()
        logger.info(
            "Starting local LiveKit test UI web_ui_active=%s ui_url=%s livekit_url=%s room=%s token_generation_available=%s",
            True,
            self.ui_url,
            self.settings.livekit_url,
            self.room_name or self.settings.livekit_room_name,
            self.build_client_config()["canGenerateToken"],
        )
        with server:
            server.serve_forever()

    def create_http_server(self) -> ThreadingHTTPServer:
        parent = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "LiveKitTestUIServer/1.0"

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == "/api/config":
                    self._send_json(parent.build_client_config())
                    return
                if parsed.path == "/healthz":
                    self._send_json({"ok": True})
                    return
                static_file = STATIC_FILES.get(parsed.path)
                if static_file is None:
                    self.send_error(HTTPStatus.NOT_FOUND, "File not found")
                    return
                file_name, content_type = static_file
                self._serve_static(file_name, content_type)

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path != "/api/token":
                    self.send_error(HTTPStatus.NOT_FOUND, "Endpoint not found")
                    return
                try:
                    payload = self._read_json()
                    token = parent.generate_participant_token(
                        room_name=str(payload.get("roomName", "")),
                        identity=str(payload.get("identity", "")),
                    )
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                except Exception:
                    logger.exception("Local LiveKit test UI token endpoint failed")
                    self._send_json({"error": "token_generation_failed"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                    return
                self._send_json({"token": token})

            def log_message(self, format: str, *args: object) -> None:
                logger.debug("LiveKit test UI request: " + format, *args)

            def _serve_static(self, file_name: str, content_type: str) -> None:
                static_root = files("app.web_ui").joinpath("static")
                asset = static_root.joinpath(file_name)
                if not asset.is_file():
                    self.send_error(HTTPStatus.NOT_FOUND, "Static file not found")
                    return
                body = asset.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _read_json(self) -> dict[str, Any]:
                content_length = int(self.headers.get("Content-Length", "0") or 0)
                raw_body = self.rfile.read(content_length) if content_length else b"{}"
                try:
                    payload = json.loads(raw_body.decode("utf-8"))
                except json.JSONDecodeError as exc:
                    raise ValueError("invalid_json") from exc
                if not isinstance(payload, dict):
                    raise ValueError("invalid_json")
                return payload

            def _send_json(self, payload: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return ThreadingHTTPServer((self.host, self.port), Handler)
