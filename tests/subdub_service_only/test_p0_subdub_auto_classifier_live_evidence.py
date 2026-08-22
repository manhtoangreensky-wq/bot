from __future__ import annotations

import time

import pytest

from services import subdub_speaker_cast as speaker_cast


def _pcm_file(tmp_path, seconds: float = 7.0):
    path = tmp_path / "auto-classifier-live-evidence.pcm"
    path.write_bytes(b"\0" * int(seconds * speaker_cast.PCM_SAMPLE_RATE * 2))
    return path


def test_live_two_speaker_strong_unopposed_pitch_evidence_is_accepted(
    tmp_path,
    monkeypatch,
):
    estimates = iter(
        [
            (172.576, 0.788734), None, None, None, None, None,
            (128.0, 0.914142), (105.097, 0.770368),
            (135.236, 0.782908), (114.487, 0.866952),
            (99.379, 0.868637), (125.768, 0.785862),
        ]
    )
    monkeypatch.setattr(
        speaker_cast,
        "_estimate_window_pitch",
        lambda *_args, **_kwargs: next(estimates),
    )

    result = speaker_cast.classify_speaker_registers(
        str(_pcm_file(tmp_path)),
        {
            "chunk_00:speaker_0": [(0.0, 3.0)],
            "chunk_00:speaker_1": [(3.5, 6.5)],
        },
        deadline_monotonic=time.monotonic() + 10.0,
        stop_requested=lambda: False,
    )

    assert result["chunk_00:speaker_0"]["voice_register"] == "high"
    assert result["chunk_00:speaker_0"]["voiced_seconds"] == 0.5
    assert result["chunk_00:speaker_1"]["voice_register"] == "low"
    assert result["chunk_00:speaker_1"]["confidence"] >= 0.78


@pytest.mark.parametrize(
    "estimate",
    (
        (166.667, 0.793447),
        (210.526, 0.766003),
    ),
)
def test_live_high_register_observations_are_accepted(
    tmp_path,
    monkeypatch,
    estimate,
):
    estimates = iter([estimate, None, None, None, None, None])
    monkeypatch.setattr(
        speaker_cast,
        "_estimate_window_pitch",
        lambda *_args, **_kwargs: next(estimates),
    )

    result = speaker_cast.classify_speaker_registers(
        str(_pcm_file(tmp_path, 3.0)),
        {"chunk_00:speaker_0": [(0.0, 3.0)]},
        deadline_monotonic=time.monotonic() + 10.0,
        stop_requested=lambda: False,
    )

    assert result["chunk_00:speaker_0"]["voice_register"] == "high"
    assert result["chunk_00:speaker_0"]["confidence"] == pytest.approx(estimate[1])


@pytest.mark.parametrize(
    "estimate",
    ((160.0, 0.99), (172.576, 0.74), (145.5, 0.99)),
)
def test_single_ambiguous_or_low_confidence_window_remains_manual(
    tmp_path,
    monkeypatch,
    estimate,
):
    estimates = iter([estimate, None, None, None, None, None])
    monkeypatch.setattr(
        speaker_cast,
        "_estimate_window_pitch",
        lambda *_args, **_kwargs: next(estimates),
    )

    with pytest.raises(
        speaker_cast.AutoCastManualRequired,
        match="^AUTO_CAST_MANUAL_REQUIRED$",
    ):
        speaker_cast.classify_speaker_registers(
            str(_pcm_file(tmp_path, 3.0)),
            {"chunk_00:speaker_0": [(0.0, 3.0)]},
            deadline_monotonic=time.monotonic() + 10.0,
            stop_requested=lambda: False,
        )


def test_conflicting_pitch_registers_remain_manual(tmp_path, monkeypatch):
    estimates = iter([(120.0, 0.95), (220.0, 0.95), None, None, None, None])
    monkeypatch.setattr(
        speaker_cast,
        "_estimate_window_pitch",
        lambda *_args, **_kwargs: next(estimates),
    )

    with pytest.raises(
        speaker_cast.AutoCastManualRequired,
        match="^AUTO_CAST_MANUAL_REQUIRED$",
    ):
        speaker_cast.classify_speaker_registers(
            str(_pcm_file(tmp_path, 3.0)),
            {"chunk_00:speaker_0": [(0.0, 3.0)]},
            deadline_monotonic=time.monotonic() + 10.0,
            stop_requested=lambda: False,
        )
