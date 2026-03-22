from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass(slots=True)
class Settings:
    openai_api_key: str
    telegram_bot_token: str
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str
    database_url: str
    vector_db_path: str
    scraper_output_dir: str
    log_level: str
    voice_transport_log_level: str = "WARNING"
    voice_high_quality_mode: bool = False
    openai_chat_model: str = "gpt-4.1-mini"
    openai_chat_temperature: float = 0.1
    openai_chat_top_p: float = 1.0
    openai_chat_max_completion_tokens: int = 500
    openai_chat_verbosity: str = "medium"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_stt_model: str = "gpt-4o-mini-transcribe"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "sage"
    openai_tts_response_format: str = "wav"
    openai_tts_speed: float = 1.0
    livekit_room_name: str = "bank-support-demo"
    livekit_agent_identity: str = "bank-support-agent"
    livekit_agent_hidden: bool = False
    browser_echo_cancellation: bool = True
    browser_noise_suppression: bool = True
    browser_auto_gain_control: bool = True
    browser_audio_sample_rate: int = 48000
    browser_audio_channel_count: int = 1
    voice_input_pre_gain: float = 1.0
    voice_normalize_input_audio: bool = True
    voice_target_input_level_dbfs: float = -20.0
    voice_max_input_gain_db: float = 14.0
    voice_silence_threshold_dbfs: float = -36.0
    voice_min_speech_seconds: float = 0.35
    voice_end_of_utterance_delay_seconds: float = 0.75
    voice_max_utterance_seconds: float = 15.0
    voice_preroll_seconds: float = 0.2
    voice_min_transcription_duration_seconds: float = 0.28
    voice_min_transcription_rms_dbfs: float = -54.0
    voice_min_transcription_peak_dbfs: float = -36.0
    voice_stt_retry_duration_seconds: float = 0.7
    voice_stt_retry_rms_dbfs: float = -46.0
    kb_cleaning_debug: bool = False
    kb_cleaning_debug_sample_size: int = 8
    kb_chunk_max_chars: int = 1000
    kb_chunk_overlap_lines: int = 2
    kb_retrieval_top_k: int = 7
    kb_retrieval_candidate_pool_size: int = 40
    kb_retrieval_min_score: float = 0.2
    kb_retrieval_min_combined_score: float = 0.26
    kb_retrieval_min_lexical_score: float = 0.12
    kb_retrieval_max_chunks_per_source: int = 3
    kb_retrieval_adjacent_window: int = 1
    kb_retrieval_debug: bool = False
    openai_api_key_source: str = "missing"
    openai_api_key_process_env_conflict: bool = False
    env_file_path: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        env_path = _project_root() / ".env"
        env_values = {
            key: str(value).strip()
            for key, value in dotenv_values(env_path).items()
            if value is not None
        }
        openai_api_key, openai_api_key_source, openai_api_key_process_env_conflict = _resolve_setting_with_source(
            "OPENAI_API_KEY",
            env_values,
        )
        voice_high_quality_mode = _resolve_bool_setting("VOICE_HIGH_QUALITY_MODE", env_values, False)
        return cls(
            openai_api_key=openai_api_key,
            telegram_bot_token=_resolve_setting("TELEGRAM_BOT_TOKEN", env_values),
            livekit_url=_resolve_setting("LIVEKIT_URL", env_values, "ws://localhost:7880"),
            livekit_api_key=_resolve_setting("LIVEKIT_API_KEY", env_values),
            livekit_api_secret=_resolve_setting("LIVEKIT_API_SECRET", env_values),
            database_url=_resolve_setting("DATABASE_URL", env_values, "sqlite:///./data/bank_support_agent.db"),
            vector_db_path=_resolve_setting("VECTOR_DB_PATH", env_values, "./data/vector_store"),
            scraper_output_dir=_resolve_setting("SCRAPER_OUTPUT_DIR", env_values, "./data"),
            log_level=_resolve_setting("LOG_LEVEL", env_values, "INFO"),
            voice_transport_log_level=_resolve_setting("VOICE_TRANSPORT_LOG_LEVEL", env_values, "WARNING"),
            voice_high_quality_mode=voice_high_quality_mode,
            openai_chat_model=_resolve_setting(
                "OPENAI_CHAT_MODEL",
                env_values,
                "gpt-4.1" if voice_high_quality_mode else "gpt-4.1-mini",
            ),
            openai_chat_temperature=_resolve_float_setting(
                "OPENAI_CHAT_TEMPERATURE",
                env_values,
                0.08 if voice_high_quality_mode else 0.1,
            ),
            openai_chat_top_p=_resolve_float_setting(
                "OPENAI_CHAT_TOP_P",
                env_values,
                0.95 if voice_high_quality_mode else 1.0,
            ),
            openai_chat_max_completion_tokens=_resolve_int_setting(
                "OPENAI_CHAT_MAX_COMPLETION_TOKENS",
                env_values,
                700 if voice_high_quality_mode else 500,
            ),
            openai_chat_verbosity=_resolve_setting(
                "OPENAI_CHAT_VERBOSITY",
                env_values,
                "medium",
            ),
            openai_stt_model=_resolve_setting(
                "OPENAI_STT_MODEL",
                env_values,
                "gpt-4o-transcribe" if voice_high_quality_mode else "gpt-4o-mini-transcribe",
            ),
            openai_tts_model=_resolve_setting(
                "OPENAI_TTS_MODEL",
                env_values,
                "tts-1-hd" if voice_high_quality_mode else "gpt-4o-mini-tts",
            ),
            openai_tts_voice=_resolve_setting("OPENAI_TTS_VOICE", env_values, "sage"),
            openai_tts_response_format=_resolve_setting("OPENAI_TTS_RESPONSE_FORMAT", env_values, "wav"),
            openai_tts_speed=_resolve_float_setting(
                "OPENAI_TTS_SPEED",
                env_values,
                0.96 if voice_high_quality_mode else 1.0,
            ),
            livekit_room_name=_resolve_setting("LIVEKIT_ROOM_NAME", env_values, "bank-support-demo"),
            livekit_agent_identity=_resolve_setting("LIVEKIT_AGENT_IDENTITY", env_values, "bank-support-agent"),
            livekit_agent_hidden=_resolve_bool_setting("LIVEKIT_AGENT_HIDDEN", env_values, False),
            browser_echo_cancellation=_resolve_bool_setting("BROWSER_ECHO_CANCELLATION", env_values, True),
            browser_noise_suppression=_resolve_bool_setting("BROWSER_NOISE_SUPPRESSION", env_values, True),
            browser_auto_gain_control=_resolve_bool_setting("BROWSER_AUTO_GAIN_CONTROL", env_values, True),
            browser_audio_sample_rate=_resolve_int_setting("BROWSER_AUDIO_SAMPLE_RATE", env_values, 48000),
            browser_audio_channel_count=_resolve_int_setting("BROWSER_AUDIO_CHANNEL_COUNT", env_values, 1),
            voice_input_pre_gain=_resolve_float_setting(
                "VOICE_INPUT_PRE_GAIN",
                env_values,
                1.3 if voice_high_quality_mode else 1.0,
            ),
            voice_normalize_input_audio=_resolve_bool_setting("VOICE_NORMALIZE_INPUT_AUDIO", env_values, True),
            voice_target_input_level_dbfs=_resolve_float_setting(
                "VOICE_TARGET_INPUT_LEVEL_DBFS",
                env_values,
                -18.5 if voice_high_quality_mode else -20.0,
            ),
            voice_max_input_gain_db=_resolve_float_setting(
                "VOICE_MAX_INPUT_GAIN_DB",
                env_values,
                18.0 if voice_high_quality_mode else 14.0,
            ),
            voice_silence_threshold_dbfs=_resolve_float_setting(
                "VOICE_SILENCE_THRESHOLD_DBFS",
                env_values,
                -41.0 if voice_high_quality_mode else -36.0,
            ),
            voice_min_speech_seconds=_resolve_float_setting(
                "VOICE_MIN_SPEECH_SECONDS",
                env_values,
                0.42 if voice_high_quality_mode else 0.35,
            ),
            voice_end_of_utterance_delay_seconds=_resolve_float_setting(
                "VOICE_END_OF_UTTERANCE_DELAY_SECONDS",
                env_values,
                1.0 if voice_high_quality_mode else 0.75,
            ),
            voice_max_utterance_seconds=_resolve_float_setting(
                "VOICE_MAX_UTTERANCE_SECONDS",
                env_values,
                18.0 if voice_high_quality_mode else 15.0,
            ),
            voice_preroll_seconds=_resolve_float_setting(
                "VOICE_PREROLL_SECONDS",
                env_values,
                0.3 if voice_high_quality_mode else 0.2,
            ),
            voice_min_transcription_duration_seconds=_resolve_float_setting(
                "VOICE_MIN_TRANSCRIPTION_DURATION_SECONDS",
                env_values,
                0.3 if voice_high_quality_mode else 0.28,
            ),
            voice_min_transcription_rms_dbfs=_resolve_float_setting(
                "VOICE_MIN_TRANSCRIPTION_RMS_DBFS",
                env_values,
                -56.0 if voice_high_quality_mode else -54.0,
            ),
            voice_min_transcription_peak_dbfs=_resolve_float_setting(
                "VOICE_MIN_TRANSCRIPTION_PEAK_DBFS",
                env_values,
                -38.0 if voice_high_quality_mode else -36.0,
            ),
            voice_stt_retry_duration_seconds=_resolve_float_setting(
                "VOICE_STT_RETRY_DURATION_SECONDS",
                env_values,
                0.8 if voice_high_quality_mode else 0.7,
            ),
            voice_stt_retry_rms_dbfs=_resolve_float_setting(
                "VOICE_STT_RETRY_RMS_DBFS",
                env_values,
                -44.0 if voice_high_quality_mode else -46.0,
            ),
            kb_cleaning_debug=_resolve_bool_setting("KB_CLEANING_DEBUG", env_values, False),
            kb_cleaning_debug_sample_size=_resolve_int_setting("KB_CLEANING_DEBUG_SAMPLE_SIZE", env_values, 8),
            kb_chunk_max_chars=_resolve_int_setting("KB_CHUNK_MAX_CHARS", env_values, 1000),
            kb_chunk_overlap_lines=_resolve_int_setting("KB_CHUNK_OVERLAP_LINES", env_values, 2),
            kb_retrieval_top_k=_resolve_int_setting("KB_RETRIEVAL_TOP_K", env_values, 7),
            kb_retrieval_candidate_pool_size=_resolve_int_setting("KB_RETRIEVAL_CANDIDATE_POOL_SIZE", env_values, 40),
            kb_retrieval_min_score=_resolve_float_setting("KB_RETRIEVAL_MIN_SCORE", env_values, 0.2),
            kb_retrieval_min_combined_score=_resolve_float_setting("KB_RETRIEVAL_MIN_COMBINED_SCORE", env_values, 0.26),
            kb_retrieval_min_lexical_score=_resolve_float_setting("KB_RETRIEVAL_MIN_LEXICAL_SCORE", env_values, 0.12),
            kb_retrieval_max_chunks_per_source=_resolve_int_setting("KB_RETRIEVAL_MAX_CHUNKS_PER_SOURCE", env_values, 3),
            kb_retrieval_adjacent_window=_resolve_int_setting("KB_RETRIEVAL_ADJACENT_WINDOW", env_values, 1),
            kb_retrieval_debug=_resolve_bool_setting("KB_RETRIEVAL_DEBUG", env_values, False),
            openai_api_key_source=openai_api_key_source,
            openai_api_key_process_env_conflict=openai_api_key_process_env_conflict,
            env_file_path=str(env_path),
        )

    @property
    def project_root(self) -> Path:
        return _project_root()

    @property
    def data_root(self) -> Path:
        return self.resolve_path(self.scraper_output_dir)

    @property
    def raw_output_dir(self) -> Path:
        return self.data_root / "raw"

    @property
    def clean_output_dir(self) -> Path:
        return self.data_root / "clean"

    @property
    def vector_store_dir(self) -> Path:
        return self.resolve_path(self.vector_db_path)

    @property
    def database_path(self) -> Path:
        if self.database_url.startswith("sqlite:///"):
            return self.resolve_path(self.database_url.removeprefix("sqlite:///"))
        return self.resolve_path(self.database_url)

    def resolve_path(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return self.project_root / path

    def ensure_runtime_dirs(self) -> None:
        self.raw_output_dir.mkdir(parents=True, exist_ok=True)
        self.clean_output_dir.mkdir(parents=True, exist_ok=True)
        self.vector_store_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def openai_api_key_diagnostics(self) -> dict[str, object]:
        return {
            "present": bool(self.openai_api_key),
            "length": len(self.openai_api_key),
            "tail": self.openai_api_key[-8:] if self.openai_api_key else "",
            "source": self.openai_api_key_source,
            "process_env_conflict": self.openai_api_key_process_env_conflict,
            "env_file_path": self.env_file_path,
        }


def _resolve_setting(name: str, env_values: dict[str, str], default: str = "") -> str:
    file_value = env_values.get(name, "").strip()
    if file_value:
        return file_value
    return os.getenv(name, default).strip()


def _resolve_setting_with_source(name: str, env_values: dict[str, str], default: str = "") -> tuple[str, str, bool]:
    file_value = env_values.get(name, "").strip()
    process_value = os.getenv(name, "").strip()
    if file_value:
        return file_value, ".env", bool(process_value and process_value != file_value)
    if process_value:
        return process_value, "process_env_fallback", False
    return default.strip(), "missing", False


def _resolve_bool_setting(name: str, env_values: dict[str, str], default: bool) -> bool:
    raw_value = _resolve_setting(name, env_values, str(default).lower()).strip().casefold()
    if raw_value in {"1", "true", "yes", "on"}:
        return True
    if raw_value in {"0", "false", "no", "off"}:
        return False
    return default


def _resolve_float_setting(name: str, env_values: dict[str, str], default: float) -> float:
    raw_value = _resolve_setting(name, env_values, str(default)).strip()
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return default


def _resolve_int_setting(name: str, env_values: dict[str, str], default: int) -> int:
    raw_value = _resolve_setting(name, env_values, str(default)).strip()
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return default
