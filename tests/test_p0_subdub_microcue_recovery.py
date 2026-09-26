"""Unit tests for services/subdub_microcue_recovery.py.

Verifies:
1. Invariant safety gates (same speaker, non-speech boundary, gap limits, fragment threshold)
2. Zero data loss coalescence (text, audio bytes, provenance, expanded window)
3. Iterative recovery logic with fit ratio preference
4. Strictly unchanged MAX_INTELLIGIBLE_FIT_RATIO = 1.80
"""

import pytest
from services.subdub_microcue_recovery import (
    MAX_INTELLIGIBLE_FIT_RATIO,
    DEFAULT_MAX_COALESCE_GAP_SECONDS,
    DEFAULT_MAX_FRAGMENT_DURATION_SECONDS,
    can_coalesce_cues,
    coalesce_cue_pair,
    recover_cue_locked_micro_cues,
)


def test_fit_ratio_constant_invariant():
    """MAX_INTELLIGIBLE_FIT_RATIO must remain strictly 1.80."""
    assert MAX_INTELLIGIBLE_FIT_RATIO == 1.80


def test_can_coalesce_speaker_mismatch():
    """Cross-speaker cues must not coalesce."""
    c1 = {"cue_id": "c1", "speaker_id": "spk_1", "start": 0.0, "end": 2.0}
    c2 = {"cue_id": "c2", "speaker_id": "spk_2", "start": 2.0, "end": 2.5}
    assert can_coalesce_cues(c1, c2) is False


def test_can_coalesce_non_speech_boundary():
    """Cues separated by non-speech boundary must not coalesce."""
    c1 = {"cue_id": "c1", "speaker_id": "spk_1", "start": 0.0, "end": 2.0, "non_speech_boundary": True}
    c2 = {"cue_id": "c2", "speaker_id": "spk_1", "start": 2.0, "end": 2.5}
    assert can_coalesce_cues(c1, c2) is False

    c3 = {"cue_id": "c3", "speaker_id": "spk_1", "start": 0.0, "end": 2.0}
    c4 = {"cue_id": "c4", "speaker_id": "spk_1", "start": 2.0, "end": 2.5, "non_speech_boundary": True}
    assert can_coalesce_cues(c3, c4) is False


def test_can_coalesce_gap_limits():
    """Gap exceeding max_gap_seconds or backward beyond 55ms must not coalesce."""
    # Gap > 0.5s
    c1 = {"cue_id": "c1", "speaker_id": "spk_1", "start": 0.0, "end": 2.0}
    c2 = {"cue_id": "c2", "speaker_id": "spk_1", "start": 2.6, "end": 3.0}  # gap = 0.6s
    assert can_coalesce_cues(c1, c2, max_gap_seconds=0.5) is False

    # Gap = 0.5s -> Allowed
    c3 = {"cue_id": "c3", "speaker_id": "spk_1", "start": 2.5, "end": 3.0}  # gap = 0.5s
    assert can_coalesce_cues(c1, c3, max_gap_seconds=0.5) is True

    # Overlap > 55ms -> Rejected
    c4 = {"cue_id": "c4", "speaker_id": "spk_1", "start": 1.9, "end": 2.5}  # gap = -0.1s
    assert can_coalesce_cues(c1, c4) is False


def test_can_coalesce_fragment_threshold():
    """If neither cue is a short fragment (<= 3.0s), they must not coalesce."""
    c1 = {"cue_id": "c1", "speaker_id": "spk_1", "start": 0.0, "end": 5.0}  # window = 5.0s
    c2 = {"cue_id": "c2", "speaker_id": "spk_1", "start": 5.0, "end": 9.0}  # window = 4.0s
    assert can_coalesce_cues(c1, c2, max_fragment_duration_seconds=3.0) is False

    # One cue is a fragment (0.8s) -> Allowed
    c3 = {"cue_id": "c3", "speaker_id": "spk_1", "start": 5.0, "end": 5.8}  # window = 0.8s
    assert can_coalesce_cues(c1, c3, max_fragment_duration_seconds=3.0) is True


def test_coalesce_cue_pair_preservation():
    """Coalescing preserves text, audio, provenance, timing window."""
    c1 = {
        "cue_id": "c1",
        "speaker_id": "spk_1",
        "start": 10.0,
        "end": 15.0,
        "text": "Hello world",
        "audio": b"AUDIO_1_",
        "audio_duration": 4.5,
        "original_cue_ids": ["c1"],
    }
    c2 = {
        "cue_id": "c2",
        "speaker_id": "spk_1",
        "start": 15.0,
        "end": 15.6,
        "text": "again",
        "audio": b"AUDIO_2",
        "audio_duration": 1.1,
        "original_cue_ids": ["c2"],
    }
    merged = coalesce_cue_pair(c1, c2)
    assert merged["cue_id"] == "c1+c2"
    assert merged["speaker_id"] == "spk_1"
    assert merged["start"] == 10.0
    assert merged["end"] == 15.6
    assert merged["cue_window"] == pytest.approx(5.6)
    assert merged["text"] == "Hello world again"
    assert merged["audio"] == b"AUDIO_1_AUDIO_2"
    assert merged["audio_duration"] == pytest.approx(5.6)
    assert merged["fit_ratio"] == pytest.approx(1.0, abs=0.01)
    assert merged["coalesced"] is True
    assert merged["cue_locked_timing"] is True
    assert merged["original_cue_ids"] == ["c1", "c2"]


def test_recover_empty_and_single():
    """Edge cases: empty list and single item return unchanged."""
    assert recover_cue_locked_micro_cues([]) == []
    single = [{"cue_id": "c1", "start": 0, "end": 1, "fit_ratio": 2.0}]
    assert recover_cue_locked_micro_cues(single) == single


def test_recover_no_exceeding_ratio_unchanged():
    """Cues that all satisfy <= 1.80 remain untouched."""
    items = [
        {"cue_id": "c1", "speaker_id": "spk_1", "start": 0.0, "end": 2.0, "audio_duration": 2.0},
        {"cue_id": "c2", "speaker_id": "spk_1", "start": 2.0, "end": 4.0, "audio_duration": 2.5},
    ]
    recovered = recover_cue_locked_micro_cues(items)
    assert len(recovered) == 2
    assert recovered[0]["cue_id"] == "c1"
    assert recovered[1]["cue_id"] == "c2"


def test_recover_prefers_lower_fit_ratio():
    """When both left and right are valid candidates, pick the one with lower combined fit ratio."""
    # Left neighbor: 10s window, 5s audio -> combined: 11s win, 7.5s aud -> fit = 0.68
    # Middle microcue: 1s window, 2.5s audio -> fit = 2.5 (needs recovery)
    # Right neighbor: 2s window, 3s audio -> combined: 3s win, 5.5s aud -> fit = 1.83 (would exceed)
    c_left = {"cue_id": "left", "speaker_id": "spk_1", "start": 0.0, "end": 10.0, "audio_duration": 5.0}
    c_mid = {"cue_id": "mid", "speaker_id": "spk_1", "start": 10.0, "end": 11.0, "audio_duration": 2.5}
    c_right = {"cue_id": "right", "speaker_id": "spk_1", "start": 11.0, "end": 13.0, "audio_duration": 3.0}

    recovered = recover_cue_locked_micro_cues([c_left, c_mid, c_right])
    assert len(recovered) == 2
    # c_left and c_mid must coalesce
    assert recovered[0]["original_cue_ids"] == ["left", "mid"]
    assert recovered[1]["cue_id"] == "right"
