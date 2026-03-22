from __future__ import annotations

import argparse
import logging

from app.bootstrap import build_settings, build_voice_runtime
from app.logging_utils import configure_logging

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the LiveKit OSS voice support agent.")
    parser.add_argument("--room", dest="room_name", help="LiveKit room name override.")
    parser.add_argument("--identity", dest="identity", help="LiveKit participant identity override.")
    visibility_group = parser.add_mutually_exclusive_group()
    visibility_group.add_argument(
        "--hidden-agent",
        dest="hidden_agent",
        action="store_true",
        help="Run the agent as a hidden LiveKit participant.",
    )
    visibility_group.add_argument(
        "--visible-agent",
        dest="hidden_agent",
        action="store_false",
        help="Run the agent as a visible LiveKit participant for local debug/demo playback.",
    )
    parser.set_defaults(hidden_agent=None)
    args = parser.parse_args()

    settings = build_settings()
    if args.room_name:
        settings.livekit_room_name = args.room_name
    if args.identity:
        settings.livekit_agent_identity = args.identity
    if args.hidden_agent is not None:
        settings.livekit_agent_hidden = args.hidden_agent

    configure_logging(settings.log_level, settings.voice_transport_log_level)
    openai_key_diagnostics = settings.openai_api_key_diagnostics()
    logger.info(
        "Starting LiveKit voice runtime livekit_voice_active=%s telegram_voice_supported=%s "
        "room=%s identity=%s agent_hidden=%s livekit_url=%s openai_configured=%s quality_mode=%s stt_model=%s llm_model=%s "
        "tts_model=%s tts_voice=%s tts_format=%s tts_speed=%.2f transport_log_level=%s livekit_secret_meets_recommended_length=%s "
        "database=%s vector_store=%s",
        True,
        False,
        settings.livekit_room_name,
        settings.livekit_agent_identity,
        settings.livekit_agent_hidden,
        settings.livekit_url,
        bool(settings.openai_api_key),
        settings.voice_high_quality_mode,
        settings.openai_stt_model,
        settings.openai_chat_model,
        settings.openai_tts_model,
        settings.openai_tts_voice,
        settings.openai_tts_response_format,
        settings.openai_tts_speed,
        settings.voice_transport_log_level,
        len(settings.livekit_api_secret) >= 32,
        settings.database_path,
        settings.vector_store_dir,
    )
    logger.info(
        "Voice tuning input_pre_gain=%.2f normalize_input_audio=%s target_input_level_dbfs=%.1f max_input_gain_db=%.1f "
        "silence_threshold_dbfs=%.1f min_speech_seconds=%.2f end_of_utterance_delay_seconds=%.2f max_utterance_seconds=%.2f "
        "browser_echo_cancellation=%s browser_noise_suppression=%s browser_auto_gain_control=%s browser_audio_sample_rate=%s browser_audio_channel_count=%s",
        settings.voice_input_pre_gain,
        settings.voice_normalize_input_audio,
        settings.voice_target_input_level_dbfs,
        settings.voice_max_input_gain_db,
        settings.voice_silence_threshold_dbfs,
        settings.voice_min_speech_seconds,
        settings.voice_end_of_utterance_delay_seconds,
        settings.voice_max_utterance_seconds,
        settings.browser_echo_cancellation,
        settings.browser_noise_suppression,
        settings.browser_auto_gain_control,
        settings.browser_audio_sample_rate,
        settings.browser_audio_channel_count,
    )
    logger.info(
        "OpenAI key diagnostics present=%s length=%s tail=%s source=%s process_env_conflict=%s env_file=%s",
        openai_key_diagnostics["present"],
        openai_key_diagnostics["length"],
        openai_key_diagnostics["tail"],
        openai_key_diagnostics["source"],
        openai_key_diagnostics["process_env_conflict"],
        openai_key_diagnostics["env_file_path"],
    )
    build_voice_runtime(settings).run_forever()


if __name__ == "__main__":
    main()
