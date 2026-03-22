from __future__ import annotations

from abc import ABC, abstractmethod

from app.models import AnswerPayload


class STTProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, *, language_hint: str | None = None) -> str:
        raise NotImplementedError


class LLMProvider(ABC):
    @abstractmethod
    async def answer(self, text: str) -> AnswerPayload:
        raise NotImplementedError


class TTSProvider(ABC):
    @abstractmethod
    async def synthesize(self, text: str, *, language_hint: str | None = None) -> bytes:
        raise NotImplementedError


class VoiceRuntime(ABC):
    @abstractmethod
    def run_forever(self) -> None:
        raise NotImplementedError
