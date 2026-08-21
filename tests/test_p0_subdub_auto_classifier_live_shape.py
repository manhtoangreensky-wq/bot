from array import array
import math
import sys
import time

from services import subdub_speaker_cast as speaker_cast


def _pcm_bytes(kind, *, seconds: float) -> bytes:
    sample_rate = speaker_cast.PCM_SAMPLE_RATE
    samples = array("h")
    for index in range(int(round(sample_rate * seconds))):
        elapsed = index / sample_rate
        value = (
            0.0
            if kind == "silence"
            else 12_000.0 * math.sin(2.0 * math.pi * float(kind) * elapsed)
        )
        samples.append(max(-32_768, min(32_767, int(round(value)))))
    if sys.byteorder != "little":
        samples.byteswap()
    return samples.tobytes()


def test_register_classifier_distributes_samples_past_silent_lead_in(tmp_path):
    pcm_path = tmp_path / "silent-lead-in-then-high.pcm"
    pcm_path.write_bytes(
        _pcm_bytes("silence", seconds=3.0)
        + _pcm_bytes(180.0, seconds=3.0)
    )

    result = speaker_cast.classify_speaker_registers(
        str(pcm_path),
        {"chunk_00:speaker_0": [(0.0, 3.0), (3.0, 6.0)]},
        deadline_monotonic=time.monotonic() + 10.0,
        stop_requested=lambda: False,
    )

    assert result["chunk_00:speaker_0"]["voice_register"] == "high"
    assert result["chunk_00:speaker_0"]["voiced_seconds"] >= 1.0


def test_register_classifier_trims_one_opposite_register_outlier(tmp_path):
    pcm_path = tmp_path / "stable-low-with-one-high-outlier.pcm"
    payload = bytearray()
    ranges = []
    cursor = 0.0
    for frequency in (120.0, 120.0, 120.0, 120.0, 120.0, 180.0):
        payload.extend(_pcm_bytes(frequency, seconds=0.5))
        ranges.append((cursor, cursor + 0.5))
        cursor += 0.5
        payload.extend(_pcm_bytes("silence", seconds=0.5))
        cursor += 0.5
    pcm_path.write_bytes(bytes(payload))

    result = speaker_cast.classify_speaker_registers(
        str(pcm_path),
        {"chunk_00:speaker_0": ranges},
        deadline_monotonic=time.monotonic() + 10.0,
        stop_requested=lambda: False,
    )

    assert result["chunk_00:speaker_0"]["voice_register"] == "low"
    assert result["chunk_00:speaker_0"]["voiced_seconds"] == 2.5
