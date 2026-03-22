from __future__ import annotations

import io

from openai import OpenAI, RateLimitError

from app.config.settings import Settings
from app.utils import chunked


class OpenAIClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = OpenAI(api_key=settings.openai_api_key or None)

    def require_api_key(self) -> None:
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for embeddings and answer generation.")

    def embed_texts(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        self.require_api_key()
        embeddings: list[list[float]] = []
        for batch in chunked(texts, batch_size):
            response = self.client.embeddings.create(
                model=self.settings.openai_embedding_model,
                input=list(batch),
            )
            embeddings.extend([item.embedding for item in response.data])
        return embeddings

    def generate_answer(self, system_prompt: str, user_prompt: str) -> str:
        self.require_api_key()
        request_kwargs = {
            "model": self.settings.openai_chat_model,
            "temperature": self.settings.openai_chat_temperature,
            "top_p": self.settings.openai_chat_top_p,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "verbosity": self.settings.openai_chat_verbosity,
        }
        if self.settings.openai_chat_max_completion_tokens > 0:
            request_kwargs["max_completion_tokens"] = self.settings.openai_chat_max_completion_tokens
        response = self.client.chat.completions.create(
            **request_kwargs,
        )
        content = response.choices[0].message.content
        return content.strip() if content else ""

    def transcribe_audio(self, audio_bytes: bytes, *, language: str | None = "hy", prompt: str | None = None) -> str:
        self.require_api_key()
        if len(audio_bytes) < 1024:
            return ""
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "utterance.wav"
        request_kwargs = {
            "model": self.settings.openai_stt_model,
            "file": audio_file,
            "prompt": prompt
            or (
                "This is Armenian banking support audio. Product names and branch names may appear in English or Latin script."
            ),
            "response_format": "text",
            "temperature": 0.0,
        }
        if language:
            request_kwargs["language"] = language
        try:
            response = self.client.audio.transcriptions.create(**request_kwargs)
        except RateLimitError as error:
            raise OpenAITranscriptionError(
                reason=_transcription_error_reason(error),
                safe_message="OpenAI STT is currently unavailable for the configured API key.",
                status_code=getattr(error, "status_code", 429),
            ) from error
        if isinstance(response, str):
            return response.strip()
        text = getattr(response, "text", "")
        return text.strip() if text else ""

    def synthesize_speech(
        self,
        text: str,
        *,
        voice: str | None = None,
        instructions: str | None = None,
        response_format: str | None = None,
    ) -> bytes:
        self.require_api_key()
        response = self.client.audio.speech.create(
            model=self.settings.openai_tts_model,
            voice=voice or self.settings.openai_tts_voice,
            input=text,
            instructions=instructions or (
                "Speak naturally in Armenian. Keep the delivery clear, helpful, and concise. "
                "If a bank product name is written in English, pronounce it naturally but keep the rest in Armenian."
            ),
            response_format=response_format or self.settings.openai_tts_response_format,
            speed=self.settings.openai_tts_speed,
        )
        return response.read()


class OpenAITranscriptionError(RuntimeError):
    def __init__(self, *, reason: str, safe_message: str, status_code: int | None = None) -> None:
        super().__init__(safe_message)
        self.reason = reason
        self.safe_message = safe_message
        self.status_code = status_code


def _transcription_error_reason(error: RateLimitError) -> str:
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        error_payload = body.get("error", {})
        if isinstance(error_payload, dict):
            error_type = str(error_payload.get("type", "")).strip()
            error_code = str(error_payload.get("code", "")).strip()
            if error_type == "insufficient_quota" or error_code == "insufficient_quota":
                return "insufficient_quota"
    return "rate_limit"
