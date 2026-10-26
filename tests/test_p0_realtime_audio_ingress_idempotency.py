"""Unit tests for RealtimeAudioIngressBuffer, RMS energy calculation, and VAD chunking (RT-01).

Governed by owner-governed-codex, locked-focus-engineering.
"""

import math
import struct
import wave
import io
try:
    import pytest
except ImportError:
    pytest = None

from services.realtime_audio_ingress import RealtimeAudioIngressBuffer, SpeechSegment


def _generate_pcm_sine(duration_ms: int, freq_hz: float = 440.0, amplitude: int = 10000, sample_rate: int = 16000) -> bytes:
    """Generates synthetic 16-bit PCM audio samples."""
    num_samples = int((sample_rate * duration_ms) / 1000)
    samples = []
    for i in range(num_samples):
        val = int(amplitude * math.sin(2 * math.pi * freq_hz * (i / sample_rate)))
        samples.append(max(-32768, min(32767, val)))
    return struct.pack(f"<{num_samples}h", *samples)


def _generate_pcm_silence(duration_ms: int, sample_rate: int = 16000) -> bytes:
    """Generates synthetic silence PCM (amplitude ~0)."""
    num_samples = int((sample_rate * duration_ms) / 1000)
    return b"\x00\x00" * num_samples


def test_rms_calculation():
    # True silence
    silence = _generate_pcm_silence(duration_ms=100)
    assert RealtimeAudioIngressBuffer.calculate_rms(silence) == 0.0

    # Sine wave with amplitude 10,000 -> RMS is approximately 10,000 / sqrt(2) ~= 7071
    tone = _generate_pcm_sine(duration_ms=100, amplitude=10000)
    rms = RealtimeAudioIngressBuffer.calculate_rms(tone)
    assert 6900 < rms < 7200


def test_audio_ingress_silence_boundary_segmentation():
    ingress = RealtimeAudioIngressBuffer(
        sample_rate=16000,
        silence_threshold_rms=300.0,
        silence_duration_trigger_ms=500,
        min_speech_duration_ms=500,
    )

    # 1. Feed 1000ms speech tone (amplitude 8000)
    speech_chunk = _generate_pcm_sine(duration_ms=1000, amplitude=8000)
    segments = ingress.push_chunk(seq=1, pcm_bytes=speech_chunk, timestamp_ms=0)
    assert len(segments) == 0  # In speech, no boundary yet

    # 2. Feed 600ms silence -> triggers silence boundary
    silence_chunk = _generate_pcm_silence(duration_ms=600)
    segments = ingress.push_chunk(seq=2, pcm_bytes=silence_chunk, timestamp_ms=1000)

    assert len(segments) == 1
    seg = segments[0]
    assert seg.segment_id == "seg_0001"
    assert seg.sequence_start == 1
    assert seg.sequence_end == 2
    assert seg.duration_ms == 1600
    assert not seg.is_silence

    # Verify WAV packaging
    wav_bytes = seg.to_wav_bytes()
    assert wav_bytes.startswith(b"RIFF")
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 16000


def test_audio_ingress_max_duration_segmentation():
    ingress = RealtimeAudioIngressBuffer(
        sample_rate=16000,
        max_segment_duration_ms=3000,
    )

    # Feed continuously active speech chunks of 1000ms each
    speech_1 = _generate_pcm_sine(duration_ms=1000, amplitude=8000)
    speech_2 = _generate_pcm_sine(duration_ms=1000, amplitude=8000)
    speech_3 = _generate_pcm_sine(duration_ms=1000, amplitude=8000)

    s1 = ingress.push_chunk(seq=1, pcm_bytes=speech_1, timestamp_ms=0)
    assert len(s1) == 0

    s2 = ingress.push_chunk(seq=2, pcm_bytes=speech_2, timestamp_ms=1000)
    assert len(s2) == 0

    # 3rd chunk hits max duration of 3000ms
    s3 = ingress.push_chunk(seq=3, pcm_bytes=speech_3, timestamp_ms=2000)
    assert len(s3) == 1
    assert s3[0].duration_ms >= 3000


def test_audio_ingress_flush():
    ingress = RealtimeAudioIngressBuffer(sample_rate=16000)

    # Feed 800ms speech but no silence following
    speech = _generate_pcm_sine(duration_ms=800, amplitude=8000)
    ingress.push_chunk(seq=1, pcm_bytes=speech, timestamp_ms=0)

    # Flush must emit the unclosed speech segment
    seg = ingress.flush()
    assert seg is not None
    assert seg.sequence_start == 1
    assert seg.duration_ms == 800
