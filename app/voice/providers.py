from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.llm.openai_client import OpenAIClient
from app.llm.service import SupportAgentService
from app.models import AnswerPayload
from app.voice.interfaces import LLMProvider, STTProvider, TTSProvider


@dataclass(slots=True)
class OpenAISTTProvider(STTProvider):
    openai_client: OpenAIClient

    async def transcribe(self, audio_bytes: bytes, *, language_hint: str | None = None) -> str:
        return await asyncio.to_thread(
            self.openai_client.transcribe_audio,
            audio_bytes,
            language=language_hint,
        )


@dataclass(slots=True)
class SupportAgentLLMProvider(LLMProvider):
    support_agent: SupportAgentService

    async def answer(self, text: str) -> AnswerPayload:
        return await asyncio.to_thread(self.support_agent.answer_question, text)


@dataclass(slots=True)
class OpenAITTSProvider(TTSProvider):
    openai_client: OpenAIClient

    async def synthesize(self, text: str, *, language_hint: str | None = None) -> bytes:
        return await asyncio.to_thread(self.openai_client.synthesize_speech, text)
