from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field

from app.config.settings import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RuntimeSpec:
    name: str
    command: tuple[str, ...]


ProcessFactory = Callable[[RuntimeSpec], subprocess.Popen[object]]


@dataclass(slots=True)
class DemoStackSupervisor:
    settings: Settings
    room_name: str
    agent_identity: str
    python_executable: str = field(default_factory=lambda: sys.executable)
    poll_interval_seconds: float = 1.0
    process_factory: ProcessFactory | None = None
    _children: dict[str, subprocess.Popen[object]] = field(default_factory=dict, init=False)

    def run(self) -> int:
        self.start()
        exit_code = 0
        try:
            while True:
                exited_runtime = self._first_exited_runtime()
                if exited_runtime is not None:
                    runtime_name, runtime_exit_code = exited_runtime
                    logger.error(
                        "Demo stack runtime exited unexpectedly runtime=%s exit_code=%s; stopping remaining runtimes",
                        runtime_name,
                        runtime_exit_code,
                    )
                    exit_code = 1
                    break
                time.sleep(self.poll_interval_seconds)
        except KeyboardInterrupt:
            logger.info("Stopping combined demo stack due to keyboard interrupt")
        finally:
            self.shutdown()
        return exit_code

    def start(self) -> None:
        if self._children:
            raise RuntimeError("Demo stack supervisor is already running.")
        self._validate_settings()

        logger.info(
            "Launching combined demo stack telegram_text_active=%s livekit_voice_active=%s "
            "telegram_voice_supported=%s room=%s identity=%s livekit_url=%s "
            "telegram_token_configured=%s openai_configured=%s transport_log_level=%s "
            "livekit_secret_meets_recommended_length=%s database=%s vector_store=%s",
            True,
            True,
            False,
            self.room_name,
            self.agent_identity,
            self.settings.livekit_url,
            bool(self.settings.telegram_bot_token),
            bool(self.settings.openai_api_key),
            self.settings.voice_transport_log_level,
            len(self.settings.livekit_api_secret) >= 32,
            self.settings.database_path,
            self.settings.vector_store_dir,
        )

        for spec in self.runtime_specs():
            logger.info("Starting runtime=%s command=%s", spec.name, " ".join(spec.command))
            process = self._spawn_process(spec)
            self._children[spec.name] = process
            logger.info("Runtime started runtime=%s pid=%s", spec.name, getattr(process, "pid", "unknown"))

    def shutdown(self) -> None:
        children = list(self._children.items())
        if not children:
            return

        for name, process in children:
            if process.poll() is not None:
                continue
            logger.info("Stopping runtime=%s pid=%s", name, getattr(process, "pid", "unknown"))
            with suppress(Exception):
                process.terminate()

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if all(process.poll() is not None for _, process in children):
                break
            time.sleep(0.1)

        for name, process in children:
            if process.poll() is not None:
                continue
            logger.warning("Force-killing runtime=%s pid=%s", name, getattr(process, "pid", "unknown"))
            with suppress(Exception):
                process.kill()
            with suppress(Exception):
                process.wait(timeout=2)

        self._children.clear()

    def runtime_specs(self) -> list[RuntimeSpec]:
        return [
            RuntimeSpec(
                name="telegram_text_demo",
                command=(self.python_executable, "-m", "scripts.run_bot"),
            ),
            RuntimeSpec(
                name="livekit_voice_runtime",
                command=(
                    self.python_executable,
                    "-m",
                    "scripts.run_voice_agent",
                    "--room",
                    self.room_name,
                    "--identity",
                    self.agent_identity,
                ),
            ),
        ]

    def _spawn_process(self, spec: RuntimeSpec) -> subprocess.Popen[object]:
        factory = self.process_factory or self._default_process_factory
        return factory(spec)

    def _default_process_factory(self, spec: RuntimeSpec) -> subprocess.Popen[object]:
        return subprocess.Popen(
            list(spec.command),
            cwd=str(self.settings.project_root),
            env=os.environ.copy(),
        )

    def _first_exited_runtime(self) -> tuple[str, int | None] | None:
        for name, process in self._children.items():
            return_code = process.poll()
            if return_code is not None:
                return name, return_code
        return None

    def _validate_settings(self) -> None:
        missing = []
        if not self.settings.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not self.settings.telegram_bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.settings.livekit_url:
            missing.append("LIVEKIT_URL")
        if not self.settings.livekit_api_key:
            missing.append("LIVEKIT_API_KEY")
        if not self.settings.livekit_api_secret:
            missing.append("LIVEKIT_API_SECRET")
        if missing:
            raise RuntimeError(
                "Combined demo stack requires all Telegram and LiveKit settings. Missing: "
                + ", ".join(missing)
            )
