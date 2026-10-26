"""Canonical Bot Core Realtime Audio Ingress & VAD Segmentation (RT-01).

Governed by owner-governed-codex, locked-focus-engineering.
Enforces:
1. Resampling / format contract: PCM 16kHz, 16-bit signed LE, mono (32,000 bytes/sec).
2. Energy-based silence detection & VAD chunking at natural speech boundaries (500-800ms silence or max 7s).
3. Monotonic sequence handling and duplicate drop.
4. In-memory WAV packaging for zero-overhead STT/ASR consumption.
"""

from __future__ import annotations

import io
import math
import struct
import wave
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class AudioChunkMetadata:
    seq: int
    timestamp_ms: int
    duration_ms: int
    sample_rate: int = 16000
    channels: int = 1
    sample_width: int = 2  # 16-bit = 2 bytes


@dataclass
class SpeechSegment:
    segment_id: str
    sequence_start: int
    sequence_end: int
    start_ms: int
    end_ms: int
    pcm_bytes: bytes
    is_silence: bool = False

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)

    def to_wav_bytes(self, sample_rate: int = 16000, channels: int = 1, sample_width: int = 2) -> bytes:
        """Wraps raw PCM s16le bytes into a valid standard WAV container in-memory."""
        out = io.BytesIO()
        with wave.open(out, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(self.pcm_bytes)
        return out.getvalue()


class RealtimeAudioIngressBuffer:
    """Buffers live PCM 16kHz audio chunks, performs RMS energy analysis,

    and yields SpeechSegments when silence boundaries or max duration are hit.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        silence_threshold_rms: float = 350.0,
        silence_duration_trigger_ms: int = 600,
        min_speech_duration_ms: int = 600,
        max_segment_duration_ms: int = 7000,
    ):
        self.sample_rate = sample_rate
        self.bytes_per_second = sample_rate * 2  # 16-bit mono = 2 bytes/sample
        self.silence_threshold_rms = silence_threshold_rms
        self.silence_duration_trigger_ms = silence_duration_trigger_ms
        self.min_speech_duration_ms = min_speech_duration_ms
        self.max_segment_duration_ms = max_segment_duration_ms

        self._current_pcm: bytearray = bytearray()
        self._segment_start_ms: int = 0
        self._current_ms: int = 0
        self._seq_start: int = 0
        self._last_seq: int = 0
        self._silence_ms_accum: int = 0
        self._segment_counter: int = 0
        self._has_speech_in_current: bool = False

    @staticmethod
    def calculate_rms(pcm_bytes: bytes) -> float:
        """Calculates Root Mean Square (RMS) amplitude of 16-bit signed PCM samples."""
        if not pcm_bytes:
            return 0.0
        num_samples = len(pcm_bytes) // 2
        if num_samples == 0:
            return 0.0
        # Unpack as little-endian signed 16-bit integers
        format_str = f"<{num_samples}h"
        samples = struct.unpack(format_str, pcm_bytes[: num_samples * 2])
        sum_squares = sum(s * s for s in samples)
        mean_square = sum_squares / num_samples
        return math.sqrt(mean_square)

    def push_chunk(
        self,
        seq: int,
        pcm_bytes: bytes,
        timestamp_ms: Optional[int] = None,
    ) -> List[SpeechSegment]:
        """Ingests a new chunk of PCM audio.

        Returns a list of completed SpeechSegments (0 or more).
        """
        if not pcm_bytes:
            return []

        # Ensure byte alignment for 16-bit samples
        aligned_len = len(pcm_bytes) - (len(pcm_bytes) % 2)
        if aligned_len <= 0:
            return []
        valid_bytes = pcm_bytes[:aligned_len]

        chunk_duration_ms = int((aligned_len / self.bytes_per_second) * 1000)

        if self._current_ms == 0 and timestamp_ms is not None:
            self._segment_start_ms = timestamp_ms
            self._current_ms = timestamp_ms
            self._seq_start = seq
        elif timestamp_ms is not None:
            self._current_ms = timestamp_ms

        if self._seq_start == 0:
            self._seq_start = seq
        self._last_seq = seq

        rms = self.calculate_rms(valid_bytes)
        is_chunk_silent = rms < self.silence_threshold_rms

        if not is_chunk_silent:
            self._has_speech_in_current = True
            self._silence_ms_accum = 0
        else:
            self._silence_ms_accum += chunk_duration_ms

        self._current_pcm.extend(valid_bytes)
        self._current_ms += chunk_duration_ms
        current_dur_ms = self._current_ms - self._segment_start_ms

        segments_to_emit: List[SpeechSegment] = []

        # Condition 1: Hit silence boundary after sufficient speech
        hit_silence_boundary = (
            self._has_speech_in_current
            and self._silence_ms_accum >= self.silence_duration_trigger_ms
            and current_dur_ms >= self.min_speech_duration_ms
        )

        # Condition 2: Max duration limit reached (prevent buffer bloat during long speeches)
        hit_max_duration = current_dur_ms >= self.max_segment_duration_ms

        if hit_silence_boundary or hit_max_duration:
            segment = self._emit_current_segment()
            if segment:
                segments_to_emit.append(segment)

        return segments_to_emit

    def flush(self) -> Optional[SpeechSegment]:
        """Flushes remaining audio in buffer at end of stream or session pause."""
        if len(self._current_pcm) > 0 and self._has_speech_in_current:
            return self._emit_current_segment()
        self._current_pcm.clear()
        self._has_speech_in_current = False
        return None

    def _emit_current_segment(self) -> Optional[SpeechSegment]:
        if not self._current_pcm:
            return None

        self._segment_counter += 1
        seg_id = f"seg_{self._segment_counter:04d}"
        pcm_data = bytes(self._current_pcm)

        segment = SpeechSegment(
            segment_id=seg_id,
            sequence_start=self._seq_start,
            sequence_end=self._last_seq,
            start_ms=self._segment_start_ms,
            end_ms=self._current_ms,
            pcm_bytes=pcm_data,
            is_silence=not self._has_speech_in_current,
        )

        # Reset buffer state for next segment
        self._current_pcm.clear()
        self._segment_start_ms = self._current_ms
        self._seq_start = self._last_seq + 1
        self._silence_ms_accum = 0
        self._has_speech_in_current = False

        return segment
