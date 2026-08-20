from __future__ import annotations

import math
import time
from array import array

from services import subdub_speaker_cast


def _speech_like_register(seconds: float, fundamental_hz: float) -> array:
    """Build deterministic harmonic-rich voiced audio, not a pure-tone fixture."""

    sample_rate = subdub_speaker_cast.PCM_SAMPLE_RATE
    phase = 0.0
    samples = array("h")
    for index in range(int(seconds * sample_rate)):
        timestamp = index / sample_rate
        vibrato = 1.0 + (0.012 * math.sin(2.0 * math.pi * 4.3 * timestamp))
        phase += 2.0 * math.pi * fundamental_hz * vibrato / sample_rate
        envelope = 0.72 + (0.18 * math.sin(2.0 * math.pi * 3.1 * timestamp))
        harmonic_signal = (
            0.30 * math.sin(phase)
            + 0.48 * math.sin((2.0 * phase) + 0.17)
            + 0.34 * math.sin((3.0 * phase) + 0.41)
            + 0.22 * math.sin((4.0 * phase) + 0.73)
            + 0.12 * math.sin((5.0 * phase) + 0.29)
        )
        deterministic_breath = 0.025 * math.sin(
            (2.0 * math.pi * 1733.0 * timestamp) + 0.11
        )
        value = envelope * harmonic_signal + deterministic_breath
        samples.append(max(-32768, min(32767, int(round(value * 12_000.0)))))
    return samples


def _tone_pcm(seconds: float, *frequencies: float) -> bytes:
    samples = array("h")
    sample_rate = subdub_speaker_cast.PCM_SAMPLE_RATE
    scale = 12_000.0 if len(frequencies) == 1 else 7_000.0
    for index in range(int(seconds * sample_rate)):
        timestamp = index / sample_rate
        value = scale * sum(
            math.sin(2.0 * math.pi * frequency * timestamp)
            for frequency in frequencies
        )
        samples.append(max(-32768, min(32767, int(round(value)))))
    return samples.tobytes()


def test_classifier_handles_harmonic_rich_low_and_high_speech_registers():
    deadline = time.monotonic() + 30.0
    low = subdub_speaker_cast._estimate_window_pitch(
        _speech_like_register(0.5, 122.0).tobytes(),
        deadline_monotonic=deadline,
        stop_requested=lambda: False,
    )
    high = subdub_speaker_cast._estimate_window_pitch(
        _speech_like_register(0.5, 222.0).tobytes(),
        deadline_monotonic=deadline,
        stop_requested=lambda: False,
    )

    assert low is not None
    assert high is not None
    assert subdub_speaker_cast.pitch_register(low[0], confidence=low[1]) == "low"
    assert subdub_speaker_cast.pitch_register(high[0], confidence=high[1]) == "high"


def test_ambiguous_mid_register_remains_fail_closed():
    assert subdub_speaker_cast.pitch_register(175.0, confidence=0.90) == "unknown"


def test_classifier_keeps_natural_intonation_inside_one_low_register(tmp_path):
    pcm_path = tmp_path / "natural-low-intonation.pcm"
    samples = array("h")
    for frequency in (115.0, 125.0, 135.0, 145.0, 130.0, 120.0):
        samples.extend(_speech_like_register(0.5, frequency))
    pcm_path.write_bytes(samples.tobytes())

    result = subdub_speaker_cast.classify_speaker_registers(
        str(pcm_path),
        {"chunk_00:speaker_0": [(0.0, 3.0)]},
        deadline_monotonic=time.monotonic() + 30.0,
        stop_requested=lambda: False,
    )

    assert result["chunk_00:speaker_0"]["voice_register"] == "low"
    assert result["chunk_00:speaker_0"]["confidence"] >= 0.75


def test_classifier_skips_unvoiced_windows_when_one_second_is_still_proven(tmp_path):
    pcm_path = tmp_path / "voiced-with-pauses.pcm"
    samples = array("h")
    silence = array("h", [0]) * int(0.5 * subdub_speaker_cast.PCM_SAMPLE_RATE)
    for frequency in (122.0, 126.0, 130.0):
        samples.extend(_speech_like_register(0.5, frequency))
        samples.extend(silence)
    pcm_path.write_bytes(samples.tobytes())

    result = subdub_speaker_cast.classify_speaker_registers(
        str(pcm_path),
        {"chunk_00:speaker_0": [(0.0, 3.0)]},
        deadline_monotonic=time.monotonic() + 30.0,
        stop_requested=lambda: False,
    )

    speaker = result["chunk_00:speaker_0"]
    assert speaker["voice_register"] == "low"
    assert speaker["voiced_seconds"] == 1.5
    assert speaker["sample_count"] == 24_000


def test_classifier_preserves_inclusive_low_edge_after_pitch_estimation(tmp_path):
    pcm_path = tmp_path / "low-edge-155.pcm"
    pcm_path.write_bytes(_tone_pcm(3.0, 155.0))

    result = subdub_speaker_cast.classify_speaker_registers(
        str(pcm_path),
        {"chunk_00:speaker_0": [(0.0, 3.0)]},
        deadline_monotonic=time.monotonic() + 30.0,
        stop_requested=lambda: False,
    )

    assert result["chunk_00:speaker_0"]["voice_register"] == "low"


def test_classifier_keeps_two_overlapping_pitches_fail_closed(tmp_path):
    pcm_path = tmp_path / "overlap-120-220.pcm"
    pcm_path.write_bytes(_tone_pcm(3.0, 120.0, 220.0))

    try:
        subdub_speaker_cast.classify_speaker_registers(
            str(pcm_path),
            {"chunk_00:speaker_0": [(0.0, 3.0)]},
            deadline_monotonic=time.monotonic() + 30.0,
            stop_requested=lambda: False,
        )
    except subdub_speaker_cast.AutoCastManualRequired:
        return
    raise AssertionError("overlapping pitches must require manual voice selection")
