from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from dataclasses import dataclass, field

from livekit import rtc

from app.config.settings import Settings
from app.llm.openai_client import OpenAITranscriptionError
from app.models import AnswerPayload
from app.retrieval.query_utils import detect_language
from app.voice.audio import VoiceSegment, VoiceTurnDetector, dbfs_to_level, level_to_dbfs, wav_to_audio_frames
from app.voice.interfaces import LLMProvider, STTProvider, TTSProvider, VoiceRuntime
from app.voice.token import build_livekit_access_token

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _TrackSession:
    participant_identity: str
    track_sid: str
    audio_stream: rtc.AudioStream
    detector: VoiceTurnDetector
    utterance_queue: asyncio.Queue[VoiceSegment | None]
    consume_task: asyncio.Task[None]
    process_task: asyncio.Task[None]


@dataclass(slots=True)
class LiveKitVoiceRuntime(VoiceRuntime):
    settings: Settings
    stt_provider: STTProvider
    llm_provider: LLMProvider
    tts_provider: TTSProvider
    room_name: str | None = None
    agent_identity: str | None = None
    hidden_agent: bool | None = None
    input_sample_rate: int = 16000
    output_sample_rate: int = 48000
    audio_frame_ms: int = 20
    input_channels: int = 1
    input_pre_gain: float = 1.0
    normalize_input_audio: bool = True
    target_input_level_dbfs: float = -20.0
    max_input_gain_db: float = 14.0
    silence_threshold_dbfs: float = -36.0
    min_speech_seconds: float = 0.35
    min_silence_seconds: float = 0.75
    max_utterance_seconds: float = 15.0
    preroll_seconds: float = 0.2
    min_transcription_duration_seconds: float = 0.28
    min_transcription_rms_dbfs: float = -54.0
    min_transcription_peak_dbfs: float = -36.0
    stt_retry_duration_seconds: float = 0.7
    stt_retry_rms_dbfs: float = -46.0
    empty_transcript_prompt_cooldown_seconds: float = 5.0
    stt_service_prompt_cooldown_seconds: float = 15.0
    queue_size: int = 3
    _room: rtc.Room | None = field(default=None, init=False)
    _audio_source: rtc.AudioSource | None = field(default=None, init=False)
    _published_track: rtc.LocalAudioTrack | None = field(default=None, init=False)
    _stop_event: asyncio.Event | None = field(default=None, init=False)
    _publish_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _sessions: dict[str, _TrackSession] = field(default_factory=dict, init=False)
    _last_unclear_prompt_at: dict[str, float] = field(default_factory=dict, init=False)
    _last_stt_service_prompt_at: dict[str, float] = field(default_factory=dict, init=False)

    def run_forever(self) -> None:
        asyncio.run(self.run())

    async def run(self) -> None:
        self._validate_settings()
        self._stop_event = asyncio.Event()
        room_name = self.room_name or self.settings.livekit_room_name
        agent_identity = self.agent_identity or self.settings.livekit_agent_identity
        hidden_agent = self._resolved_hidden_agent()

        room = rtc.Room()
        self._room = room
        self._register_room_handlers(room)

        token = build_livekit_access_token(
            self.settings,
            room_name=room_name,
            identity=agent_identity,
            hidden=hidden_agent,
            agent=True,
        )
        logger.info(
            "Starting LiveKit voice runtime room=%s identity=%s hidden_agent=%s url=%s",
            room_name,
            agent_identity,
            hidden_agent,
            self.settings.livekit_url,
        )
        logger.info(
            "Voice runtime quality_config quality_mode=%s input_format=pcm16_mono/%sHz output_format=pcm16_mono/%sHz frame_ms=%s "
            "silence_threshold_dbfs=%.1f min_speech_seconds=%.2f end_of_utterance_delay_seconds=%.2f max_utterance_seconds=%.2f preroll_seconds=%.2f "
            "input_pre_gain=%.2f normalize_input_audio=%s target_input_level_dbfs=%.1f max_input_gain_db=%.1f "
            "stt_model=%s min_transcription_duration_seconds=%.2f min_transcription_rms_dbfs=%.1f min_transcription_peak_dbfs=%.1f "
            "stt_retry_duration_seconds=%.2f stt_retry_rms_dbfs=%.1f llm_model=%s tts_model=%s tts_voice=%s tts_format=%s tts_speed=%.2f",
            self.settings.voice_high_quality_mode,
            self.input_sample_rate,
            self.output_sample_rate,
            self.audio_frame_ms,
            self.silence_threshold_dbfs,
            self.min_speech_seconds,
            self.min_silence_seconds,
            self.max_utterance_seconds,
            self.preroll_seconds,
            self.input_pre_gain,
            self.normalize_input_audio,
            self.target_input_level_dbfs,
            self.max_input_gain_db,
            self.settings.openai_stt_model,
            self.min_transcription_duration_seconds,
            self.min_transcription_rms_dbfs,
            self.min_transcription_peak_dbfs,
            self.stt_retry_duration_seconds,
            self.stt_retry_rms_dbfs,
            self.settings.openai_chat_model,
            self.settings.openai_tts_model,
            self.settings.openai_tts_voice,
            self.settings.openai_tts_response_format,
            self.settings.openai_tts_speed,
        )

        try:
            await room.connect(
                self.settings.livekit_url,
                token,
                rtc.RoomOptions(auto_subscribe=True),
            )
            await self._publish_agent_track(room)
            await self._subscribe_existing_audio_tracks(room)
            await self._stop_event.wait()
        except asyncio.CancelledError:
            raise
        finally:
            await self._shutdown()

    async def handle_transcript(self, participant_identity: str, transcript: str) -> AnswerPayload | None:
        cleaned_transcript = transcript.strip()
        if not cleaned_transcript:
            logger.info("Voice transcript skipped for participant=%s because it is empty", participant_identity)
            return None

        logger.info("Voice transcript participant=%s text=%r", participant_identity, cleaned_transcript)
        llm_started_at = time.perf_counter()
        answer_payload = await self.llm_provider.answer(cleaned_transcript)
        llm_latency_ms = (time.perf_counter() - llm_started_at) * 1000.0

        refusal_reason = answer_payload.debug.get("reason")
        logger.info(
            "Voice answer participant=%s topic=%s refusal=%s refusal_reason=%s source_count=%s llm_latency_ms=%.1f",
            participant_identity,
            answer_payload.topic,
            answer_payload.refusal,
            refusal_reason,
            len(answer_payload.sources),
            llm_latency_ms,
        )

        answer_text = answer_payload.answer_text.strip()
        if not answer_text:
            return answer_payload

        tts_language = detect_language(answer_text) or "hy"
        tts_started_at = time.perf_counter()
        synthesized_audio = await self.tts_provider.synthesize(answer_text, language_hint=tts_language)
        tts_latency_ms = (time.perf_counter() - tts_started_at) * 1000.0
        if synthesized_audio:
            logger.info(
                "Voice TTS generated participant=%s bytes=%s language_hint=%s tts_latency_ms=%.1f",
                participant_identity,
                len(synthesized_audio),
                tts_language,
                tts_latency_ms,
            )
            await self.publish_audio_response(synthesized_audio)
        return answer_payload

    async def publish_audio_response(self, wav_audio: bytes) -> None:
        if not self._audio_source:
            raise RuntimeError("LiveKit audio source is not initialized.")

        frames = wav_to_audio_frames(
            wav_audio,
            target_sample_rate=self.output_sample_rate,
            target_channels=1,
            frame_size_ms=self.audio_frame_ms,
        )
        logger.info(
            "Publishing voice playback frames=%s output_sample_rate=%s frame_ms=%s payload_bytes=%s",
            len(frames),
            self.output_sample_rate,
            self.audio_frame_ms,
            len(wav_audio),
        )
        async with self._publish_lock:
            for frame in frames:
                await self._audio_source.capture_frame(frame)

    def stop(self) -> None:
        if self._stop_event and not self._stop_event.is_set():
            self._stop_event.set()

    def _validate_settings(self) -> None:
        missing = []
        if not self.settings.livekit_url:
            missing.append("LIVEKIT_URL")
        if not self.settings.livekit_api_key:
            missing.append("LIVEKIT_API_KEY")
        if not self.settings.livekit_api_secret:
            missing.append("LIVEKIT_API_SECRET")
        if missing:
            raise RuntimeError(f"Missing required LiveKit settings: {', '.join(missing)}")
        self.settings.ensure_runtime_dirs()

    def _resolved_hidden_agent(self) -> bool:
        if self.hidden_agent is not None:
            return self.hidden_agent
        return self.settings.livekit_agent_hidden

    def _register_room_handlers(self, room: rtc.Room) -> None:
        room.on("connected", lambda: logger.info("LiveKit room connected"))
        room.on("reconnecting", lambda: logger.warning("LiveKit room reconnecting"))
        room.on("reconnected", lambda: logger.info("LiveKit room reconnected"))
        room.on("disconnected", self._on_room_disconnected)
        room.on("participant_connected", lambda participant: logger.debug("Participant connected identity=%s", participant.identity))
        room.on("participant_disconnected", self._on_participant_disconnected)
        room.on("track_subscribed", self._on_track_subscribed)
        room.on("track_unsubscribed", self._on_track_unsubscribed)
        room.on("track_subscription_failed", self._on_track_subscription_failed)

    async def _publish_agent_track(self, room: rtc.Room) -> None:
        self._audio_source = rtc.AudioSource(sample_rate=self.output_sample_rate, num_channels=1)
        track = rtc.LocalAudioTrack.create_audio_track("bank-support-agent-voice", self._audio_source)
        publish_options = rtc.TrackPublishOptions()
        publish_options.source = rtc.TrackSource.SOURCE_MICROPHONE
        publish_options.dtx = True
        await room.local_participant.publish_track(track, publish_options)
        self._published_track = track
        logger.info("Published agent audio track sample_rate=%s", self.output_sample_rate)

    async def _subscribe_existing_audio_tracks(self, room: rtc.Room) -> None:
        for participant in room.remote_participants.values():
            for publication in participant.track_publications.values():
                if publication.kind != rtc.TrackKind.KIND_AUDIO:
                    continue
                publication.set_subscribed(True)
                if publication.track and isinstance(publication.track, rtc.RemoteAudioTrack):
                    await self._ensure_track_session(publication.track, participant)

    def _on_room_disconnected(self, reason: object) -> None:
        logger.info("LiveKit room disconnected reason=%s", reason)
        self.stop()

    def _on_participant_disconnected(self, participant: rtc.RemoteParticipant) -> None:
        logger.debug("Participant disconnected identity=%s", participant.identity)
        asyncio.create_task(self._cleanup_participant_sessions(participant.identity))

    def _on_track_subscribed(
        self,
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ) -> None:
        publication.set_subscribed(True)
        if not isinstance(track, rtc.RemoteAudioTrack):
            return
        logger.info(
            "Subscribed to remote audio track sid=%s participant=%s source=%s",
            track.sid,
            participant.identity,
            publication.source,
        )
        asyncio.create_task(self._ensure_track_session(track, participant))

    def _on_track_unsubscribed(
        self,
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ) -> None:
        logger.debug(
            "Track unsubscribed sid=%s participant=%s source=%s",
            getattr(track, "sid", "unknown"),
            participant.identity,
            publication.source,
        )
        asyncio.create_task(self._cleanup_track_session(getattr(track, "sid", "")))

    def _on_track_subscription_failed(self, participant: rtc.RemoteParticipant, track_sid: str, error: str) -> None:
        logger.warning(
            "Track subscription failed participant=%s track_sid=%s error=%s",
            participant.identity,
            track_sid,
            error,
        )

    async def _ensure_track_session(self, track: rtc.RemoteAudioTrack, participant: rtc.RemoteParticipant) -> None:
        if track.sid in self._sessions:
            return
        audio_stream = rtc.AudioStream.from_track(
            track=track,
            sample_rate=self.input_sample_rate,
            num_channels=self.input_channels,
            frame_size_ms=self.audio_frame_ms,
        )
        detector = VoiceTurnDetector(
            sample_rate=self.input_sample_rate,
            speech_threshold=dbfs_to_level(self.silence_threshold_dbfs),
            min_speech_seconds=self.min_speech_seconds,
            min_silence_seconds=self.min_silence_seconds,
            max_utterance_seconds=self.max_utterance_seconds,
            preroll_seconds=self.preroll_seconds,
        )
        logger.info(
            "Voice input subscribed participant=%s track_sid=%s input_format=pcm16_mono/%sHz frame_ms=%s silence_threshold_dbfs=%.1f",
            participant.identity,
            track.sid,
            self.input_sample_rate,
            self.audio_frame_ms,
            self.silence_threshold_dbfs,
        )
        utterance_queue: asyncio.Queue[VoiceSegment | None] = asyncio.Queue(maxsize=self.queue_size)
        consume_task = asyncio.create_task(
            self._consume_audio_track(participant.identity, track.sid, audio_stream, detector, utterance_queue)
        )
        process_task = asyncio.create_task(
            self._process_utterances(participant.identity, track.sid, utterance_queue)
        )
        self._sessions[track.sid] = _TrackSession(
            participant_identity=participant.identity,
            track_sid=track.sid,
            audio_stream=audio_stream,
            detector=detector,
            utterance_queue=utterance_queue,
            consume_task=consume_task,
            process_task=process_task,
        )

    async def _consume_audio_track(
        self,
        participant_identity: str,
        track_sid: str,
        audio_stream: rtc.AudioStream,
        detector: VoiceTurnDetector,
        utterance_queue: asyncio.Queue[VoiceSegment | None],
    ) -> None:
        try:
            async for event in audio_stream:
                utterance = detector.push_frame(
                    event.frame,
                    input_pre_gain=self.input_pre_gain,
                    normalize_input_audio=self.normalize_input_audio,
                    target_input_level_dbfs=self.target_input_level_dbfs,
                    max_input_gain_db=self.max_input_gain_db,
                )
                if utterance:
                    await self._enqueue_utterance(utterance_queue, utterance, participant_identity, track_sid)
            trailing = detector.flush(
                input_pre_gain=self.input_pre_gain,
                normalize_input_audio=self.normalize_input_audio,
                target_input_level_dbfs=self.target_input_level_dbfs,
                max_input_gain_db=self.max_input_gain_db,
            )
            if trailing:
                await self._enqueue_utterance(utterance_queue, trailing, participant_identity, track_sid)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Voice track consumer crashed participant=%s track_sid=%s", participant_identity, track_sid)
        finally:
            with suppress(asyncio.QueueFull):
                utterance_queue.put_nowait(None)
            with suppress(Exception):
                await audio_stream.aclose()

    async def _process_utterances(
        self,
        participant_identity: str,
        track_sid: str,
        utterance_queue: asyncio.Queue[VoiceSegment | None],
    ) -> None:
        try:
            while True:
                segment = await utterance_queue.get()
                if segment is None:
                    break
                logger.info(
                    "Voice segment finalized participant=%s track_sid=%s duration=%.2fs speech=%.2fs end_reason=%s trailing_silence=%.2fs "
                    "input_format=pcm16_mono/%sHz frames=%s rms_dbfs=%.1f normalized_rms_dbfs=%.1f peak_dbfs=%.1f "
                    "pre_gain=%.2f normalization_gain=%.2f total_gain=%.2f",
                    participant_identity,
                    track_sid,
                    segment.duration_seconds,
                    segment.speech_seconds,
                    segment.end_reason,
                    segment.trailing_silence_seconds,
                    segment.input_sample_rate,
                    segment.frame_count,
                    level_to_dbfs(segment.rms_level),
                    level_to_dbfs(segment.normalized_rms_level),
                    level_to_dbfs(segment.peak_level),
                    segment.pre_gain_applied,
                    segment.normalization_gain_applied,
                    segment.gain_applied,
                )
                if not self._should_transcribe_segment(segment):
                    logger.debug(
                        "Skipping low-signal voice segment participant=%s track_sid=%s duration=%.2fs normalized_rms=%.1f peak=%s",
                        participant_identity,
                        track_sid,
                        segment.duration_seconds,
                        level_to_dbfs(segment.normalized_rms_level),
                        level_to_dbfs(segment.peak_level),
                    )
                    continue
                try:
                    transcript = await self._transcribe_segment(participant_identity, track_sid, segment)
                except OpenAITranscriptionError as error:
                    logger.warning(
                        "Voice STT unavailable participant=%s track_sid=%s reason=%s status_code=%s",
                        participant_identity,
                        track_sid,
                        error.reason,
                        error.status_code,
                    )
                    await self._maybe_prompt_for_stt_service_issue(participant_identity)
                    continue
                except Exception:
                    logger.exception(
                        "Voice STT failed unexpectedly participant=%s track_sid=%s",
                        participant_identity,
                        track_sid,
                    )
                    continue
                if not transcript:
                    await self._maybe_prompt_for_repeat(participant_identity, segment)
                    continue
                await self.handle_transcript(participant_identity, transcript)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Voice utterance processor crashed participant=%s track_sid=%s", participant_identity, track_sid)

    async def _enqueue_utterance(
        self,
        utterance_queue: asyncio.Queue[VoiceSegment | None],
        utterance: VoiceSegment,
        participant_identity: str,
        track_sid: str,
    ) -> None:
        if utterance_queue.full():
            with suppress(asyncio.QueueEmpty):
                utterance_queue.get_nowait()
            logger.warning(
                "Dropping oldest queued utterance participant=%s track_sid=%s due to backpressure",
                participant_identity,
                track_sid,
            )
        await utterance_queue.put(utterance)

    async def _cleanup_track_session(self, track_sid: str) -> None:
        session = self._sessions.pop(track_sid, None)
        if not session:
            return
        for task in (session.consume_task, session.process_task):
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        with suppress(Exception):
            await session.audio_stream.aclose()

    async def _cleanup_participant_sessions(self, participant_identity: str) -> None:
        matching_sids = [
            track_sid
            for track_sid, session in self._sessions.items()
            if session.participant_identity == participant_identity
        ]
        for track_sid in matching_sids:
            await self._cleanup_track_session(track_sid)
        self._last_unclear_prompt_at.pop(participant_identity, None)
        self._last_stt_service_prompt_at.pop(participant_identity, None)

    async def _shutdown(self) -> None:
        for track_sid in list(self._sessions):
            await self._cleanup_track_session(track_sid)
        if self._room and self._room.isconnected():
            with suppress(Exception):
                await self._room.disconnect()

    def _should_transcribe_segment(self, segment: VoiceSegment) -> bool:
        if segment.frame_count < 3:
            return False
        if segment.duration_seconds < self.min_transcription_duration_seconds:
            return False
        min_transcription_rms_level = dbfs_to_level(self.min_transcription_rms_dbfs)
        min_transcription_peak_level = int(dbfs_to_level(self.min_transcription_peak_dbfs))
        if segment.normalized_rms_level < min_transcription_rms_level and segment.peak_level < min_transcription_peak_level:
            return False
        return True

    def _should_retry_empty_transcript(self, segment: VoiceSegment) -> bool:
        if segment.duration_seconds < self.stt_retry_duration_seconds:
            return False
        stt_retry_rms_level = dbfs_to_level(self.stt_retry_rms_dbfs)
        min_transcription_peak_level = int(dbfs_to_level(self.min_transcription_peak_dbfs))
        return segment.normalized_rms_level >= stt_retry_rms_level or segment.peak_level >= min_transcription_peak_level * 3

    async def _transcribe_segment(self, participant_identity: str, track_sid: str, segment: VoiceSegment) -> str:
        stt_started_at = time.perf_counter()
        transcript = (await self.stt_provider.transcribe(segment.wav_bytes, language_hint="hy")).strip()
        stt_latency_ms = (time.perf_counter() - stt_started_at) * 1000.0
        if transcript:
            logger.info(
                "Voice STT completed participant=%s track_sid=%s language_hint=%s latency_ms=%.1f transcript_chars=%s",
                participant_identity,
                track_sid,
                "hy",
                stt_latency_ms,
                len(transcript),
            )
            return transcript
        if not self._should_retry_empty_transcript(segment):
            logger.info(
                "Voice STT returned empty transcript participant=%s track_sid=%s duration=%.2fs normalized_rms_dbfs=%.1f latency_ms=%.1f",
                participant_identity,
                track_sid,
                segment.duration_seconds,
                level_to_dbfs(segment.normalized_rms_level),
                stt_latency_ms,
            )
            return ""

        logger.info(
            "Retrying STT without forced language participant=%s track_sid=%s duration=%.2fs normalized_rms_dbfs=%.1f first_latency_ms=%.1f",
            participant_identity,
            track_sid,
            segment.duration_seconds,
            level_to_dbfs(segment.normalized_rms_level),
            stt_latency_ms,
        )
        retry_started_at = time.perf_counter()
        transcript = (await self.stt_provider.transcribe(segment.wav_bytes, language_hint=None)).strip()
        retry_latency_ms = (time.perf_counter() - retry_started_at) * 1000.0
        logger.info(
            "Voice STT retry completed participant=%s track_sid=%s language_hint=%s latency_ms=%.1f transcript_chars=%s",
            participant_identity,
            track_sid,
            "auto",
            retry_latency_ms,
            len(transcript),
        )
        if not transcript:
            logger.info(
                "Voice STT remained empty after retry participant=%s track_sid=%s duration=%.2fs normalized_rms_dbfs=%.1f",
                participant_identity,
                track_sid,
                segment.duration_seconds,
                level_to_dbfs(segment.normalized_rms_level),
            )
        return transcript

    async def _maybe_prompt_for_repeat(self, participant_identity: str, segment: VoiceSegment) -> None:
        if not self._should_retry_empty_transcript(segment):
            return
        now = time.monotonic()
        last_prompt_at = self._last_unclear_prompt_at.get(participant_identity, 0.0)
        if now - last_prompt_at < self.empty_transcript_prompt_cooldown_seconds:
            logger.debug("Skipping unclear-speech prompt due to cooldown participant=%s", participant_identity)
            return
        self._last_unclear_prompt_at[participant_identity] = now
        retry_prompt = (
            "Ներեցեք, ձայնը հստակ չլսվեց։ Կարո՞ղ եք հարցը մի փոքր ավելի դանդաղ կամ բարձր կրկնել։"
        )
        tts_started_at = time.perf_counter()
        synthesized_audio = await self.tts_provider.synthesize(retry_prompt, language_hint="hy")
        if not synthesized_audio:
            return
        tts_latency_ms = (time.perf_counter() - tts_started_at) * 1000.0
        logger.info(
            "Publishing unclear-speech prompt participant=%s bytes=%s tts_latency_ms=%.1f",
            participant_identity,
            len(synthesized_audio),
            tts_latency_ms,
        )
        await self.publish_audio_response(synthesized_audio)

    async def _maybe_prompt_for_stt_service_issue(self, participant_identity: str) -> None:
        now = time.monotonic()
        last_prompt_at = self._last_stt_service_prompt_at.get(participant_identity, 0.0)
        if now - last_prompt_at < self.stt_service_prompt_cooldown_seconds:
            logger.debug("Skipping STT-service prompt due to cooldown participant=%s", participant_identity)
            return
        self._last_stt_service_prompt_at[participant_identity] = now
        service_prompt = (
            "Ներեցեք, հիմա ձայնային հարցումը ժամանակավորապես մշակել չեմ կարող։ "
            "Խնդրում եմ մի փոքր ուշ փորձեք կամ հարցը գրեք տեքստով։"
        )
        tts_started_at = time.perf_counter()
        synthesized_audio = await self.tts_provider.synthesize(service_prompt, language_hint="hy")
        if not synthesized_audio:
            return
        tts_latency_ms = (time.perf_counter() - tts_started_at) * 1000.0
        logger.info(
            "Publishing STT-service fallback prompt participant=%s bytes=%s tts_latency_ms=%.1f",
            participant_identity,
            len(synthesized_audio),
            tts_latency_ms,
        )
        await self.publish_audio_response(synthesized_audio)
