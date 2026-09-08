"""Focused contracts for public Auto Multi concurrency and speaker continuity."""

import asyncio
import threading
import time

import numpy as np
import pytest

from services import subdub_multi_speaker_embedding_onnx as embedding
from services import subdub_speaker_cast as speaker_cast
from services.subdub_blackboxes import auto_multi_speaker


def test_identity_partition_keeps_one_person_one_register_across_scenes():
    # One noisy window votes male, while the speaker's acoustic embedding stays
    # in the same identity cluster. The register must not flip between scenes.
    expected_identities = [0] * 4 + [1] * 4 + [2] * 4
    matrix = np.zeros((12, embedding.EMBEDDING_DIM), dtype=np.float32)
    for index, identity in enumerate(expected_identities):
        matrix[index, identity] = 1.0
    female_probabilities = [0.99, 0.99, 0.01, 0.99] + [0.01] * 4 + [0.99] * 4

    result = embedding.build_gender_constrained_speech_authority(
        matrix,
        matrix.copy(),
        np.arange(12, dtype=np.float64),
        np.full(12, 1.5, dtype=np.float64),
        female_probabilities,
        speaker_count=3,
    )

    assert len(set(result["labels"][:4])) == 1
    first_identity = result["labels"][0]
    assert result["speaker_registers"][first_identity] == "high"
    assert result["identity_continuity_repaired"] is True
    assert result["identity_gender_outlier_window_count"] == 1


def test_identity_partition_keeps_two_same_register_people_distinct():
    identities = [0] * 3 + [1] * 3 + [2] * 3
    matrix = np.zeros((9, embedding.EMBEDDING_DIM), dtype=np.float32)
    for index, identity in enumerate(identities):
        matrix[index, identity] = 1.0

    result = embedding.build_gender_constrained_speech_authority(
        matrix,
        matrix.copy(),
        np.arange(9, dtype=np.float64),
        np.full(9, 1.5, dtype=np.float64),
        [0.99] * 6 + [0.01] * 3,
        speaker_count=3,
    )

    assert len(set(result["labels"][:3])) == 1
    assert len(set(result["labels"][3:6])) == 1
    assert result["labels"][0] != result["labels"][3]
    assert result["speaker_registers"].count("high") == 2


def test_rejected_identity_partition_cannot_remap_gender_partition_registers(
    monkeypatch,
):
    """A rejected identity candidate must not lend registers to other labels."""

    matrix = np.zeros((12, embedding.EMBEDDING_DIM), dtype=np.float32)
    for index, identity in enumerate([0] * 4 + [1] * 4 + [2] * 4):
        matrix[index, identity] = 1.0
    female_probabilities = (
        [0.99, 0.99, 0.99, 0.01]
        + [0.99, 0.99, 0.99, 0.01]
        + [0.01] * 4
    )
    gender_labels = {
        1: np.asarray([0, 0, 0, 1, 0, 0, 0, 1, 2, 2, 2, 2]),
        2: np.asarray([0, 0, 0, 2, 1, 1, 1, 2, 2, 2, 2, 2]),
    }

    monkeypatch.setattr(
        embedding,
        "_gender_partition_for_allocation",
        lambda *_args, female_count, **_kwargs: gender_labels[female_count],
    )
    monkeypatch.setattr(
        embedding,
        "_gender_partition_score",
        lambda *_args, **_kwargs: 1.0,
    )
    monkeypatch.setattr(
        embedding,
        "_fixed_count_window_partition",
        lambda *_args, **_kwargs: np.asarray([0] * 4 + [1] * 4 + [2] * 4),
    )

    result = embedding.build_gender_constrained_speech_authority(
        matrix,
        matrix.copy(),
        np.arange(12, dtype=np.float64),
        np.full(12, 1.5, dtype=np.float64),
        female_probabilities,
        speaker_count=3,
    )

    assert result["identity_continuity_repaired"] is False
    assert result["speaker_registers"] == ["high", "low", "low"]


def test_three_views_use_majority_then_aggregate_tiebreak_without_global_quorum(
    monkeypatch,
):
    """Distributed boundary jitter must not reject a complete 2-of-3 vote."""

    expected = np.repeat(np.arange(5), 12)
    matrix = np.zeros((60, embedding.EMBEDDING_DIM), dtype=np.float32)
    for index, identity in enumerate(expected):
        matrix[index, identity] = 1.0
    base_view = expected.copy()
    shifted_view = expected.copy()
    aggregate_view = expected.copy()
    base_view[[25, 37]] = [3, 4]
    shifted_view[[26, 38]] = [4, 2]
    aggregate_view[[27, 39]] = [3, 2]
    base_view[50] = 2
    shifted_view[50] = 3
    assert len({base_view[50], shifted_view[50], aggregate_view[50]}) == 3
    views = [base_view, shifted_view, aggregate_view]
    call_index = 0

    def gender_partition(*_args, female_count, **_kwargs):
        nonlocal call_index
        if female_count != 2:
            raise ValueError("unsupported_test_allocation")
        result = views[call_index]
        call_index += 1
        return result

    monkeypatch.setattr(
        embedding,
        "_gender_partition_for_allocation",
        gender_partition,
    )
    monkeypatch.setattr(
        embedding,
        "_gender_partition_score",
        lambda *_args, **_kwargs: 1.0,
    )
    monkeypatch.setattr(
        embedding,
        "_fixed_count_window_partition",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("identity_candidate_unavailable")
        ),
    )

    result = embedding.build_gender_constrained_speech_authority(
        matrix,
        matrix.copy(),
        np.arange(60, dtype=np.float64),
        np.full(60, 1.5, dtype=np.float64),
        [0.99] * 24 + [0.01] * 36,
        speaker_count=5,
    )

    assert result["labels"] == expected.tolist()
    assert result["labels"][50] == aggregate_view[50]
    assert result["speaker_registers"] == ["high", "high", "low", "low", "low"]


def test_three_views_fail_when_consensus_drops_speaker_support(monkeypatch):
    expected = np.asarray([0] + [1] * 9 + [2] * 10)
    matrix = np.zeros((20, embedding.EMBEDDING_DIM), dtype=np.float32)
    for index, identity in enumerate(expected):
        matrix[index, identity] = 1.0
    base_view = expected.copy()
    shifted_view = expected.copy()
    aggregate_view = expected.copy()
    base_view[1] = 0
    shifted_view[2] = 0
    aggregate_view[3] = 0
    views = [
        base_view,
        shifted_view,
        aggregate_view,
    ]
    call_index = 0

    def gender_partition(*_args, female_count, **_kwargs):
        nonlocal call_index
        if female_count != 1:
            raise ValueError("unsupported_test_allocation")
        result = views[call_index]
        call_index += 1
        return result

    monkeypatch.setattr(
        embedding,
        "_gender_partition_for_allocation",
        gender_partition,
    )
    monkeypatch.setattr(
        embedding,
        "_gender_partition_score",
        lambda *_args, **_kwargs: 1.0,
    )
    monkeypatch.setattr(
        embedding,
        "_fixed_count_window_partition",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("identity_candidate_unavailable")
        ),
    )

    with pytest.raises(speaker_cast.AutoCastManualRequired) as error:
        embedding.build_gender_constrained_speech_authority(
            matrix,
            matrix.copy(),
            np.arange(20, dtype=np.float64),
            np.full(20, 1.5, dtype=np.float64),
            [0.99] * 2 + [0.01] * 18,
            speaker_count=3,
        )
    cause = error.value
    while getattr(cause, "__cause__", None) is not None:
        cause = cause.__cause__
    assert str(cause) == "acoustic_cluster_unsupported"


def test_auto_multi_runtime_lock_waits_for_previous_job_instead_of_busy_fail():
    lock = threading.Lock()
    assert lock.acquire(blocking=False)
    timer = threading.Timer(0.05, lock.release)
    timer.start()
    processing_budgets = []

    def owned_runner(
        _path,
        _words,
        *,
        duration_seconds,
        deadline_monotonic,
        stop_requested,
        **_kwargs,
    ):
        assert duration_seconds == pytest.approx(1.0)
        assert stop_requested() is False
        processing_budgets.append(deadline_monotonic - time.monotonic())
        return {"ok": True, "status": "PASS"}

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(embedding, "_FIXED_VOCAL_PIPELINE_LOCK", lock)
    monkeypatch.setattr(
        embedding,
        "_diarize_fixed_vocal_word_timeline_owned",
        owned_runner,
    )
    pcm_path = None
    try:
        from pathlib import Path

        pcm_path = Path("test-tmp-continuity-queue.pcm")
        pcm_path.write_bytes(b"\x01\x00\x01\x00" * 44_100)
        result = asyncio.run(
            auto_multi_speaker.run_local_acoustic_diarization_off_event_loop(
                pcm_path,
                [{"word": "hello", "start": 0.0, "end": 0.5}],
                duration_seconds=1.0,
            )
        )
        assert result["status"] == "PASS"
        assert processing_budgets == [
            pytest.approx(
                auto_multi_speaker.ACOUSTIC_WALL_TIMEOUT_SECONDS,
                abs=0.1,
            )
        ]
    finally:
        timer.join(timeout=1.0)
        if pcm_path is not None:
            pcm_path.unlink(missing_ok=True)
        monkeypatch.undo()
        if lock.locked():
            lock.release()


def test_auto_multi_runtime_lock_times_out_fail_closed():
    lock = threading.Lock()
    assert lock.acquire(blocking=False)
    try:
        with pytest.raises(speaker_cast.AutoCastManualRequired) as error:
            embedding._acquire_runtime_lock(
                lock,
                deadline_monotonic=time.monotonic() + 0.03,
                stop_requested=lambda: False,
                timeout_code="fixed_vocal_demix_timeout",
            )
        cause = error.value
        while getattr(cause, "__cause__", None) is not None:
            cause = cause.__cause__
        assert str(cause) == "fixed_vocal_demix_timeout"
    finally:
        lock.release()
