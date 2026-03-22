from __future__ import annotations

from app.cleaning.service import CleaningPipeline
from app.config.settings import Settings
from app.ingestion.service import IngestionPipeline
from app.llm.openai_client import OpenAIClient
from app.llm.service import SupportAgentService
from app.retrieval.classifier import TopicClassifier
from app.retrieval.service import RetrievalService
from app.runtime.demo_stack import DemoStackSupervisor
from app.scraping.service import ScrapingPipeline
from app.storage.db import initialize_database
from app.storage.repositories import MetadataRepository
from app.storage.vector_store import LocalNumpyVectorStore
from app.voice.livekit_runtime import LiveKitVoiceRuntime
from app.voice.providers import OpenAISTTProvider, OpenAITTSProvider, SupportAgentLLMProvider
from app.web_ui.server import LiveKitTestUIServer


def build_settings() -> Settings:
    settings = Settings.from_env()
    settings.ensure_runtime_dirs()
    return settings


def build_scraping_pipeline(settings: Settings | None = None) -> ScrapingPipeline:
    return ScrapingPipeline(settings or build_settings())


def build_cleaning_pipeline(settings: Settings | None = None) -> CleaningPipeline:
    return CleaningPipeline(settings or build_settings())


def build_ingestion_pipeline(settings: Settings | None = None) -> IngestionPipeline:
    resolved_settings = settings or build_settings()
    initialize_database(resolved_settings.database_path)
    repository = MetadataRepository(resolved_settings.database_path)
    vector_store = LocalNumpyVectorStore(resolved_settings.vector_store_dir)
    openai_client = OpenAIClient(resolved_settings)
    return IngestionPipeline(
        resolved_settings,
        repository,
        vector_store,
        openai_client,
        chunk_max_chars=resolved_settings.kb_chunk_max_chars,
        chunk_overlap_lines=resolved_settings.kb_chunk_overlap_lines,
    )


def build_support_agent(settings: Settings | None = None) -> SupportAgentService:
    resolved_settings = settings or build_settings()
    initialize_database(resolved_settings.database_path)
    repository = MetadataRepository(resolved_settings.database_path)
    vector_store = LocalNumpyVectorStore(resolved_settings.vector_store_dir)
    openai_client = OpenAIClient(resolved_settings)
    classifier = TopicClassifier()
    retrieval_service = RetrievalService(
        repository,
        vector_store,
        openai_client,
        classifier=classifier,
        min_score=resolved_settings.kb_retrieval_min_score,
        top_k=resolved_settings.kb_retrieval_top_k,
        candidate_pool_size=resolved_settings.kb_retrieval_candidate_pool_size,
        min_combined_score=resolved_settings.kb_retrieval_min_combined_score,
        min_lexical_score=resolved_settings.kb_retrieval_min_lexical_score,
        max_chunks_per_source=resolved_settings.kb_retrieval_max_chunks_per_source,
        adjacent_window=resolved_settings.kb_retrieval_adjacent_window,
        debug_verbose=resolved_settings.kb_retrieval_debug,
    )
    return SupportAgentService(retrieval_service, openai_client, classifier=classifier)


def build_voice_runtime(settings: Settings | None = None) -> LiveKitVoiceRuntime:
    resolved_settings = settings or build_settings()
    support_agent = build_support_agent(resolved_settings)
    openai_client = OpenAIClient(resolved_settings)
    return LiveKitVoiceRuntime(
        settings=resolved_settings,
        stt_provider=OpenAISTTProvider(openai_client),
        llm_provider=SupportAgentLLMProvider(support_agent),
        tts_provider=OpenAITTSProvider(openai_client),
        room_name=resolved_settings.livekit_room_name,
        agent_identity=resolved_settings.livekit_agent_identity,
        input_pre_gain=resolved_settings.voice_input_pre_gain,
        normalize_input_audio=resolved_settings.voice_normalize_input_audio,
        target_input_level_dbfs=resolved_settings.voice_target_input_level_dbfs,
        max_input_gain_db=resolved_settings.voice_max_input_gain_db,
        silence_threshold_dbfs=resolved_settings.voice_silence_threshold_dbfs,
        min_speech_seconds=resolved_settings.voice_min_speech_seconds,
        min_silence_seconds=resolved_settings.voice_end_of_utterance_delay_seconds,
        max_utterance_seconds=resolved_settings.voice_max_utterance_seconds,
        preroll_seconds=resolved_settings.voice_preroll_seconds,
        min_transcription_duration_seconds=resolved_settings.voice_min_transcription_duration_seconds,
        min_transcription_rms_dbfs=resolved_settings.voice_min_transcription_rms_dbfs,
        min_transcription_peak_dbfs=resolved_settings.voice_min_transcription_peak_dbfs,
        stt_retry_duration_seconds=resolved_settings.voice_stt_retry_duration_seconds,
        stt_retry_rms_dbfs=resolved_settings.voice_stt_retry_rms_dbfs,
    )


def build_demo_stack_supervisor(
    settings: Settings | None = None,
    *,
    room_name: str | None = None,
    agent_identity: str | None = None,
) -> DemoStackSupervisor:
    resolved_settings = settings or build_settings()
    return DemoStackSupervisor(
        settings=resolved_settings,
        room_name=room_name or resolved_settings.livekit_room_name,
        agent_identity=agent_identity or resolved_settings.livekit_agent_identity,
    )


def build_livekit_test_ui_server(
    settings: Settings | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8766,
    room_name: str | None = None,
) -> LiveKitTestUIServer:
    resolved_settings = settings or build_settings()
    return LiveKitTestUIServer(
        settings=resolved_settings,
        host=host,
        port=port,
        room_name=room_name or resolved_settings.livekit_room_name,
    )
