from __future__ import annotations

import io
import wave
from collections import deque
from dataclasses import dataclass, field

import numpy as np
from livekit import rtc


@dataclass(frozen=True, slots=True)
class VoiceSegment:
    wav_bytes: bytes
    duration_seconds: float
    speech_seconds: float
    frame_count: int
    average_amplitude: float
    rms_level: float
    peak_level: int
    normalized_rms_level: float
    gain_applied: float
    was_normalized: bool
    pre_gain_applied: float = 1.0
    normalization_gain_applied: float = 1.0
    end_reason: str = "flush"
    trailing_silence_seconds: float = 0.0
    input_sample_rate: int = 16000
    input_channels: int = 1


def frame_to_mono_samples(frame: rtc.AudioFrame) -> np.ndarray:
    samples = np.frombuffer(frame.data, dtype=np.int16).copy()
    if frame.num_channels <= 1:
        return samples
    reshaped = samples.reshape(-1, frame.num_channels)
    mono = reshaped.mean(axis=1)
    return np.clip(np.round(mono), -32768, 32767).astype(np.int16)


def encode_wav(samples: np.ndarray, sample_rate: int, *, num_channels: int = 1) -> bytes:
    with io.BytesIO() as buffer:
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(num_channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(samples.astype(np.int16).tobytes())
        return buffer.getvalue()


def decode_wav(wav_bytes: bytes) -> tuple[np.ndarray, int, int]:
    with io.BytesIO(wav_bytes) as buffer:
        with wave.open(buffer, "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            num_channels = wav_file.getnchannels()
            raw = wav_file.readframes(wav_file.getnframes())
    samples = np.frombuffer(raw, dtype=np.int16).copy()
    return samples, sample_rate, num_channels


def remove_dc_offset(samples: np.ndarray) -> np.ndarray:
    if len(samples) == 0:
        return samples.astype(np.int16, copy=False)
    centered = samples.astype(np.float32) - float(np.mean(samples, dtype=np.float64))
    return np.clip(np.round(centered), -32768, 32767).astype(np.int16)


def compute_audio_levels(samples: np.ndarray) -> tuple[float, float, int]:
    if len(samples) == 0:
        return 0.0, 0.0, 0
    float_samples = samples.astype(np.float32)
    average_amplitude = float(np.mean(np.abs(float_samples)))
    rms_level = float(np.sqrt(np.mean(np.square(float_samples))))
    peak_level = int(np.max(np.abs(float_samples)))
    return average_amplitude, rms_level, peak_level


def level_to_dbfs(level: float, *, reference: float = 32767.0, floor_dbfs: float = -120.0) -> float:
    if level <= 0.0:
        return floor_dbfs
    return max(floor_dbfs, 20.0 * float(np.log10(level / reference)))


def dbfs_to_level(dbfs: float, *, reference: float = 32767.0) -> float:
    return float(reference * (10.0 ** (dbfs / 20.0)))


def db_to_gain(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def normalize_for_stt(
    samples: np.ndarray,
    *,
    pre_gain: float = 1.0,
    normalize_input: bool = True,
    target_level_dbfs: float = -20.0,
    max_input_gain_db: float = 14.0,
    silence_rms_floor_dbfs: float = -57.0,
    peak_headroom: float = 0.97,
) -> tuple[np.ndarray, float, float, float, float, bool]:
    centered = remove_dc_offset(samples)
    pre_gain = max(0.1, float(pre_gain))
    if pre_gain != 1.0 and len(centered) > 0:
        pre_scaled = centered.astype(np.float32) * pre_gain
        prepared_input = np.clip(np.round(pre_scaled), -32768, 32767).astype(np.int16)
    else:
        prepared_input = centered

    _, original_rms, original_peak = compute_audio_levels(prepared_input)
    if len(centered) == 0 or original_peak <= 0:
        return prepared_input, original_rms, original_rms, pre_gain, 1.0, False

    silence_rms_floor = dbfs_to_level(silence_rms_floor_dbfs)
    if original_rms < silence_rms_floor and original_peak < int(silence_rms_floor * 8):
        return prepared_input, original_rms, original_rms, pre_gain, 1.0, False

    if not normalize_input:
        return prepared_input, original_rms, original_rms, pre_gain, 1.0, False

    target_rms = dbfs_to_level(target_level_dbfs)
    max_gain = db_to_gain(max_input_gain_db)
    headroom_gain = (32767.0 * peak_headroom) / max(float(original_peak), 1.0)
    desired_gain = target_rms / max(original_rms, 1.0)
    normalization_gain = min(max_gain, headroom_gain, desired_gain)
    if 0.95 <= normalization_gain <= 1.05:
        return prepared_input, original_rms, original_rms, pre_gain, 1.0, False

    boosted = prepared_input.astype(np.float32) * normalization_gain
    prepared = np.clip(np.round(boosted), -32768, 32767).astype(np.int16)
    _, normalized_rms, _ = compute_audio_levels(prepared)
    return prepared, original_rms, normalized_rms, pre_gain, normalization_gain, True


def resample_samples(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate or len(samples) == 0:
        return samples.astype(np.int16, copy=False)

    source_positions = np.arange(len(samples), dtype=np.float32)
    target_length = max(1, int(round(len(samples) * target_rate / source_rate)))
    target_positions = np.linspace(0, max(len(samples) - 1, 0), num=target_length, dtype=np.float32)
    resampled = np.interp(target_positions, source_positions, samples.astype(np.float32))
    return np.clip(np.round(resampled), -32768, 32767).astype(np.int16)


def ensure_mono(samples: np.ndarray, num_channels: int) -> np.ndarray:
    if num_channels <= 1:
        return samples.astype(np.int16, copy=False)
    reshaped = samples.reshape(-1, num_channels)
    mono = reshaped.mean(axis=1)
    return np.clip(np.round(mono), -32768, 32767).astype(np.int16)


def wav_to_audio_frames(
    wav_bytes: bytes,
    *,
    target_sample_rate: int,
    target_channels: int = 1,
    frame_size_ms: int = 20,
) -> list[rtc.AudioFrame]:
    samples, sample_rate, num_channels = decode_wav(wav_bytes)
    mono_samples = ensure_mono(samples, num_channels)
    prepared = resample_samples(mono_samples, sample_rate, target_sample_rate)
    samples_per_channel = max(1, int(target_sample_rate * frame_size_ms / 1000))

    frames: list[rtc.AudioFrame] = []
    for start in range(0, len(prepared), samples_per_channel):
        chunk = prepared[start : start + samples_per_channel]
        if len(chunk) < samples_per_channel:
            chunk = np.pad(chunk, (0, samples_per_channel - len(chunk)), mode="constant")
        frames.append(
            rtc.AudioFrame(
                data=chunk.astype(np.int16).tobytes(),
                sample_rate=target_sample_rate,
                num_channels=target_channels,
                samples_per_channel=samples_per_channel,
            )
        )
    if not frames:
        frames.append(
            rtc.AudioFrame(
                data=np.zeros(samples_per_channel, dtype=np.int16).tobytes(),
                sample_rate=target_sample_rate,
                num_channels=target_channels,
                samples_per_channel=samples_per_channel,
            )
        )
    return frames


@dataclass(slots=True)
class VoiceTurnDetector:
    sample_rate: int
    speech_threshold: float = 575.0
    min_speech_seconds: float = 0.35
    min_silence_seconds: float = 0.75
    max_utterance_seconds: float = 15.0
    preroll_seconds: float = 0.2
    _preroll_frames: deque[np.ndarray] = field(default_factory=deque, init=False)
    _speech_frames: list[np.ndarray] = field(default_factory=list, init=False)
    _speech_active: bool = field(default=False, init=False)
    _voice_seconds: float = field(default=0.0, init=False)
    _silence_seconds: float = field(default=0.0, init=False)
    _total_seconds: float = field(default=0.0, init=False)
    _last_frame_seconds: float = field(default=0.02, init=False)

    def push_frame(
        self,
        frame: rtc.AudioFrame,
        *,
        input_pre_gain: float = 1.0,
        normalize_input_audio: bool = True,
        target_input_level_dbfs: float = -20.0,
        max_input_gain_db: float = 14.0,
    ) -> VoiceSegment | None:
        samples = remove_dc_offset(frame_to_mono_samples(frame))
        duration = frame.samples_per_channel / frame.sample_rate
        self._last_frame_seconds = duration
        amplitude, rms_level, peak_level = compute_audio_levels(samples)
        is_speech = (
            amplitude >= self.speech_threshold
            or rms_level >= self.speech_threshold * 0.85
            or peak_level >= int(self.speech_threshold * 5.5)
        )

        if not self._speech_active:
            self._append_preroll(samples, duration)
            if not is_speech:
                return None
            self._speech_active = True
            self._speech_frames.extend(self._preroll_frames)
            self._preroll_frames.clear()

        self._speech_frames.append(samples)
        self._total_seconds += duration
        if is_speech:
            self._voice_seconds += duration
            self._silence_seconds = 0.0
        else:
            self._silence_seconds += duration

        if self._voice_seconds < self.min_speech_seconds:
            return None
        if self._silence_seconds >= self.min_silence_seconds or self._total_seconds >= self.max_utterance_seconds:
            end_reason = "silence" if self._silence_seconds >= self.min_silence_seconds else "max_duration"
            return self._flush_current_turn(
                trim_trailing_silence=True,
                end_reason=end_reason,
                input_pre_gain=input_pre_gain,
                normalize_input_audio=normalize_input_audio,
                target_input_level_dbfs=target_input_level_dbfs,
                max_input_gain_db=max_input_gain_db,
            )
        return None

    def flush(
        self,
        *,
        input_pre_gain: float = 1.0,
        normalize_input_audio: bool = True,
        target_input_level_dbfs: float = -20.0,
        max_input_gain_db: float = 14.0,
    ) -> VoiceSegment | None:
        if not self._speech_frames or self._voice_seconds < self.min_speech_seconds:
            self._reset()
            return None
        return self._flush_current_turn(
            trim_trailing_silence=False,
            end_reason="flush",
            input_pre_gain=input_pre_gain,
            normalize_input_audio=normalize_input_audio,
            target_input_level_dbfs=target_input_level_dbfs,
            max_input_gain_db=max_input_gain_db,
        )

    def _append_preroll(self, samples: np.ndarray, duration: float) -> None:
        self._preroll_frames.append(samples)
        max_frames = max(1, int(round(self.preroll_seconds / max(duration, 0.02))))
        while len(self._preroll_frames) > max_frames:
            self._preroll_frames.popleft()

    def _flush_current_turn(
        self,
        *,
        trim_trailing_silence: bool,
        end_reason: str,
        input_pre_gain: float,
        normalize_input_audio: bool,
        target_input_level_dbfs: float,
        max_input_gain_db: float,
    ) -> VoiceSegment:
        frames = list(self._speech_frames)
        trailing_silence_seconds = self._silence_seconds if trim_trailing_silence else 0.0
        if trim_trailing_silence:
            trailing_frames = max(0, int(round(self._silence_seconds / max(self._last_frame_seconds, 0.02))))
            while trailing_frames > 0 and frames:
                frames.pop()
                trailing_frames -= 1
        samples = np.concatenate(frames) if frames else np.zeros(0, dtype=np.int16)
        prepared, original_rms, normalized_rms_level, pre_gain_applied, normalization_gain_applied, was_normalized = normalize_for_stt(
            samples,
            pre_gain=input_pre_gain,
            normalize_input=normalize_input_audio,
            target_level_dbfs=target_input_level_dbfs,
            max_input_gain_db=max_input_gain_db,
        )
        average_amplitude, _, peak_level = compute_audio_levels(samples)
        total_gain_applied = pre_gain_applied * normalization_gain_applied
        duration_seconds = len(samples) / self.sample_rate if self.sample_rate else 0.0
        speech_seconds = min(self._voice_seconds, duration_seconds)
        frame_count = len(frames)
        wav_bytes = encode_wav(prepared, self.sample_rate)
        self._reset()
        return VoiceSegment(
            wav_bytes=wav_bytes,
            duration_seconds=duration_seconds,
            speech_seconds=speech_seconds,
            frame_count=frame_count,
            average_amplitude=average_amplitude,
            rms_level=original_rms,
            peak_level=peak_level,
            normalized_rms_level=normalized_rms_level,
            pre_gain_applied=pre_gain_applied,
            normalization_gain_applied=normalization_gain_applied,
            gain_applied=total_gain_applied,
            was_normalized=was_normalized,
            end_reason=end_reason,
            trailing_silence_seconds=trailing_silence_seconds,
            input_sample_rate=self.sample_rate,
            input_channels=1,
        )

    def _reset(self) -> None:
        self._preroll_frames.clear()
        self._speech_frames.clear()
        self._speech_active = False
        self._voice_seconds = 0.0
        self._silence_seconds = 0.0
        self._total_seconds = 0.0
        self._last_frame_seconds = 0.02
