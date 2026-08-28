from __future__ import annotations

import asyncio
import importlib
import math
import threading
import time
from pathlib import Path

import pytest

from services import subdub_speaker_cast as speaker_cast
from services.subdub_blackboxes import auto_speaker


def _service():
    return importlib.import_module("services.subdub_two_speaker_gender_onnx")


def _scored(genders: str, *, start: float = 0.0) -> list[dict]:
    rows = []
    for index, gender in enumerate(genders):
        cue_start = start + index
        rows.append(
            {
                "start": cue_start,
                "end": cue_start + 1.0,
                "male_score": 0.9 if gender == "M" else 0.1,
                "female_score": 0.9 if gender == "F" else 0.1,
            }
        )
    return rows


def _union_seconds(items: list[dict]) -> float:
    intervals = sorted((float(item["start"]), float(item["end"])) for item in items)
    total = 0.0
    current_start = current_end = None
    for start, end in intervals:
        if current_start is None:
            current_start, current_end = start, end
        elif start <= current_end:
            current_end = max(current_end, end)
        else:
            total += current_end - current_start
            current_start, current_end = start, end
    if current_start is not None:
        total += current_end - current_start
    return total


@pytest.mark.parametrize(
    ("speaker_0", "speaker_1", "expected"),
    (
        ("MMMM", "MMMM", {"speaker_0": "male", "speaker_1": "male"}),
        ("MMMM", "FFFF", {"speaker_0": "male", "speaker_1": "female"}),
        ("FFFF", "FFFF", {"speaker_0": "female", "speaker_1": "female"}),
    ),
    ids=("male-male", "male-female", "female-female"),
)
def test_independent_group_votes_allow_same_and_mixed_gender_pairs(
    speaker_0,
    speaker_1,
    expected,
):
    service = _service()

    result = service._aggregate_gender_results(
        {
            "speaker_0": _scored(speaker_0),
            "speaker_1": _scored(speaker_1, start=10.0),
        }
    )

    assert {
        label: item["voice_gender"] for label, item in result.items()
    } == expected
    assert {
        label: item["voice_register"] for label, item in result.items()
    } == {
        label: "low" if gender == "male" else "high"
        for label, gender in expected.items()
    }
    assert all(item["confidence"] == 1.0 for item in result.values())
    assert all(
        item["reason"] == "classified_panns_audioset_after_uvr"
        for item in result.values()
    )


def test_group_confidence_is_literal_vote_dominance_and_duration_is_unique():
    service = _service()
    speaker_0 = _scored("MMMF")
    speaker_0[0]["end"] = 2.0
    speaker_0[1]["start"] = 1.0
    speaker_0[1]["end"] = 3.0
    speaker_0[2]["start"] = 3.0
    speaker_0[2]["end"] = 4.0
    speaker_0[3]["start"] = 4.0
    speaker_0[3]["end"] = 5.0

    result = service._aggregate_gender_results(
        {
            "speaker_0": speaker_0,
            "speaker_1": _scored("FFFF", start=5.0),
        }
    )

    assert result["speaker_0"]["voice_gender"] == "male"
    assert result["speaker_0"]["confidence"] == 0.75
    assert result["speaker_0"]["voiced_seconds"] == 5.0
    assert result["speaker_0"]["sample_count"] == 220_500
    assert result["speaker_1"]["confidence"] == 1.0
    assert result["speaker_1"]["voiced_seconds"] == 4.0
    assert result["speaker_1"]["sample_count"] == 176_400


@pytest.mark.parametrize(
    "scores",
    (
        {"speaker_0": _scored("MMFF"), "speaker_1": _scored("FFFF", start=8.0)},
        {"speaker_0": _scored("MMMFF"), "speaker_1": _scored("FFFF", start=8.0)},
        {"speaker_0": _scored("MMM"), "speaker_1": _scored("FFFF", start=8.0)},
        {
            "speaker_0": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "male_score": math.nan,
                    "female_score": 0.2,
                },
                *_scored("MMM", start=1.0),
            ],
            "speaker_1": _scored("FFFF", start=8.0),
        },
        {"speaker_0": _scored("MMMM")},
    ),
    ids=("tie", "dominance-below-075", "fewer-than-four", "nan", "one-label"),
)
def test_ambiguous_or_invalid_group_evidence_fails_closed(scores):
    service = _service()

    with pytest.raises(
        speaker_cast.AutoCastManualRequired,
        match="^AUTO_CAST_MANUAL_REQUIRED$",
    ):
        service._aggregate_gender_results(scores)


def test_cue_selection_is_bounded_to_48_unique_seconds_and_four_per_speaker():
    service = _service()
    ranges = {
        "speaker_0": [(0.0, 6.0), (12.0, 18.0), (24.0, 30.0), (36.0, 42.0), (48.0, 54.0)],
        "speaker_1": [(6.0, 12.0), (18.0, 24.0), (30.0, 36.0), (42.0, 48.0), (54.0, 60.0)],
    }

    selected = service._select_bounded_cues(ranges)
    flattened = [item for values in selected.values() for item in values]

    assert set(selected) == {"speaker_0", "speaker_1"}
    assert all(len(values) >= 4 for values in selected.values())
    assert all(
        len(values) <= service.MAX_CUES_PER_SPEAKER
        for values in selected.values()
    )
    assert _union_seconds(flattened) == 48.0
    assert _union_seconds(flattened) <= service.MAX_JOB_EVIDENCE_SECONDS


def test_cue_selection_accepts_more_than_64_input_cues_but_keeps_bounded_output():
    service = _service()
    ranges = {
        "speaker_0": [(index * 0.2, index * 0.2 + 0.1) for index in range(70)],
        "speaker_1": [(index * 0.2 + 0.1, index * 0.2 + 0.2) for index in range(70)],
    }

    selected = service._select_bounded_cues(ranges)

    assert all(
        service.MIN_CLASSIFIED_CUES_PER_SPEAKER
        <= len(values)
        <= service.MAX_CUES_PER_SPEAKER
        for values in selected.values()
    )
    assert sum(len(values) for values in selected.values()) <= (
        2 * service.MAX_CUES_PER_SPEAKER
    )


def test_cue_selection_skips_overlapping_first_cues_for_later_valid_subset():
    service = _service()
    ranges = {
        "speaker_0": [
            (0.0, 10.0),
            (0.0, 9.0),
            (0.0, 8.0),
            (0.0, 7.0),
            (20.0, 21.0),
            (22.0, 23.0),
            (24.0, 25.0),
            (26.0, 27.0),
        ],
        "speaker_1": [
            (0.0, 6.0),
            (0.0, 5.0),
            (0.0, 4.0),
            (0.0, 3.0),
            (21.0, 22.0),
            (23.0, 24.0),
            (25.0, 26.0),
            (27.0, 28.0),
        ],
    }

    selected = service._select_bounded_cues(ranges)
    flattened = [item for values in selected.values() for item in values]

    assert all(len(values) >= 4 for values in selected.values())
    assert all(
        sum(item["start"] >= 20.0 for item in values) >= 4
        for values in selected.values()
    )
    assert not service._has_overlap(flattened)
    assert _union_seconds(flattened) <= service.MAX_JOB_EVIDENCE_SECONDS


@pytest.mark.parametrize("stopped", (False, True))
def test_deadline_or_stop_callback_fails_closed(stopped):
    service = _service()
    deadline = time.monotonic() - 0.001 if not stopped else time.monotonic() + 10.0

    with pytest.raises(
        speaker_cast.AutoCastManualRequired,
        match="^AUTO_CAST_MANUAL_REQUIRED$",
    ):
        service._ensure_active(deadline, lambda: stopped)


@pytest.mark.parametrize("kind", ("missing", "hash-mismatch", "missing-license"))
def test_model_assets_fail_closed_before_inference(tmp_path, monkeypatch, kind):
    service = _service()
    uvr = tmp_path / "uvr.onnx"
    panns = tmp_path / "panns.onnx"
    uvr_license = tmp_path / "uvr.LICENSE"
    notices = tmp_path / "THIRD_PARTY_NOTICES.md"
    if kind != "missing":
        uvr.write_bytes(b"wrong-uvr")
        panns.write_bytes(b"wrong-panns")
        uvr_license.write_text("MIT", encoding="utf-8")
        if kind != "missing-license":
            notices.write_text("MIT and CC-BY-4.0", encoding="utf-8")
    monkeypatch.setattr(service, "UVR_MODEL_PATH", uvr)
    monkeypatch.setattr(service, "PANN_MODEL_PATH", panns)
    monkeypatch.setattr(service, "UVR_LICENSE_PATH", uvr_license)
    monkeypatch.setattr(service, "THIRD_PARTY_NOTICES_PATH", notices)

    with pytest.raises(
        speaker_cast.AutoCastManualRequired,
        match="^AUTO_CAST_MANUAL_REQUIRED$",
    ):
        service._validated_model_paths()


def test_panns_model_asset_requires_explicit_cc_by_license(tmp_path, monkeypatch):
    service = _service()
    uvr = tmp_path / "uvr.onnx"
    panns = tmp_path / "panns.onnx"
    uvr_license = tmp_path / "uvr.LICENSE"
    panns_code_license = tmp_path / "PANNs.LICENSE.MIT"
    panns_model_license = tmp_path / "PANNs.MODEL.LICENSE.CC-BY-4.0"
    notices = tmp_path / "THIRD_PARTY_NOTICES.md"
    uvr.write_bytes(b"uvr")
    panns.write_bytes(b"panns")
    uvr_license.write_text("MIT", encoding="utf-8")
    panns_code_license.write_text("MIT", encoding="utf-8")
    notices.write_text("PANNs and AudioSet attribution", encoding="utf-8")
    monkeypatch.setattr(service, "UVR_MODEL_PATH", uvr)
    monkeypatch.setattr(service, "PANN_MODEL_PATH", panns)
    monkeypatch.setattr(service, "UVR_LICENSE_PATH", uvr_license)
    monkeypatch.setattr(service, "PANN_LICENSE_PATH", panns_code_license)
    monkeypatch.setattr(service, "PANN_MODEL_LICENSE_PATH", panns_model_license, raising=False)
    monkeypatch.setattr(service, "THIRD_PARTY_NOTICES_PATH", notices)
    monkeypatch.setattr(service, "UVR_MODEL_SHA256", service._sha256(uvr))
    monkeypatch.setattr(service, "PANN_MODEL_SHA256", service._sha256(panns))

    with pytest.raises(
        speaker_cast.AutoCastManualRequired,
        match="^AUTO_CAST_MANUAL_REQUIRED$",
    ):
        service._validated_model_paths()


def test_public_owner_uses_selected_cues_once_without_provider_or_forced_pair(
    tmp_path,
    monkeypatch,
):
    service = _service()
    pcm_path = tmp_path / "fixture-stereo.pcm"
    pcm_path.write_bytes(b"\x00\x00\x00\x00" * (8 * service.PCM_SAMPLE_RATE))
    ranges = {
        "speaker_0": [(0.0, 1.0), (2.0, 3.0), (4.0, 5.0), (6.0, 7.0)],
        "speaker_1": [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0), (7.0, 8.0)],
    }
    calls = []
    monkeypatch.setattr(
        service,
        "_validated_model_paths",
        lambda: (Path("uvr.onnx"), Path("panns.onnx")),
    )

    def infer(path, selected, model_paths, *, deadline_monotonic, stop_requested):
        calls.append((path, selected, model_paths, deadline_monotonic, stop_requested))
        return {
            "speaker_0": _scored("MMMM"),
            "speaker_1": _scored("FFFF", start=4.0),
        }

    monkeypatch.setattr(service, "_infer_selected_cues", infer)

    result = service.classify_two_speaker_genders(
        str(pcm_path),
        ranges,
        deadline_monotonic=time.monotonic() + 10.0,
        stop_requested=lambda: False,
    )

    assert len(calls) == 1
    assert calls[0][0] == pcm_path
    assert calls[0][2] == (Path("uvr.onnx"), Path("panns.onnx"))
    assert result["speaker_0"]["voice_register"] == "low"
    assert result["speaker_1"]["voice_register"] == "high"


@pytest.mark.parametrize("error", (IndexError("invalid-output"), OverflowError("overflow")))
def test_invalid_onnx_output_exceptions_fail_closed(tmp_path, monkeypatch, error):
    service = _service()
    pcm_path = tmp_path / "fixture-stereo.pcm"
    pcm_path.write_bytes(b"\x00\x00\x00\x00" * 44_100)
    ranges = {
        "speaker_0": [(0.0, 0.1), (0.2, 0.3), (0.4, 0.5), (0.6, 0.7)],
        "speaker_1": [(0.1, 0.2), (0.3, 0.4), (0.5, 0.6), (0.7, 0.8)],
    }
    monkeypatch.setattr(
        service,
        "_validated_model_paths",
        lambda: (Path("uvr.onnx"), Path("panns.onnx")),
    )

    def invalid_output(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(service, "_infer_selected_cues", invalid_output)

    with pytest.raises(
        speaker_cast.AutoCastManualRequired,
        match="^AUTO_CAST_MANUAL_REQUIRED$",
    ):
        service.classify_two_speaker_genders(
            str(pcm_path),
            ranges,
            deadline_monotonic=time.monotonic() + 10.0,
            stop_requested=lambda: False,
        )


def test_exact_two_preflight_requests_stereo_44100_and_cleans_pcm(
    tmp_path,
    monkeypatch,
):
    service = _service()
    ranges = {
        "speaker_0": [(0.0, 1.0), (2.0, 3.0), (4.0, 5.0), (6.0, 7.0)],
        "speaker_1": [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0), (7.0, 8.0)],
    }
    extracted = tmp_path / "auto_speaker_44100_stereo_s16le.pcm"
    extract_calls = []
    classifier_calls = []
    monkeypatch.setattr(
        auto_speaker,
        "_validated_classifier_inputs",
        lambda _prepared: (["speaker_0", "speaker_1"], ranges),
    )

    async def extract_pcm(_prepared, _state, **kwargs):
        extract_calls.append(kwargs)
        extracted.write_bytes(b"\x00\x00\x00\x00" * (8 * service.PCM_SAMPLE_RATE))
        return str(extracted)

    def classify(path, received_ranges, **kwargs):
        classifier_calls.append((path, received_ranges, kwargs))
        return {
            "speaker_0": {"voice_gender": "male", "voice_register": "low", "confidence": 1.0},
            "speaker_1": {"voice_gender": "female", "voice_register": "high", "confidence": 1.0},
        }

    monkeypatch.setattr(service, "classify_two_speaker_genders", classify)
    prepared = {"state": {"_pipeline_workspace": str(tmp_path)}}

    result = asyncio.run(
        auto_speaker.run_auto_speaker_preflight(
            {
                "voice_kind": "auto_speaker_gender",
                "voice_selection_mode": "auto_speaker",
            },
            prepare_subtitles=lambda *_args, **_kwargs: prepared,
            post_prepare_gate=lambda *_args, **_kwargs: True,
            extract_pcm=extract_pcm,
        )
    )

    assert result["ok"] is True
    assert result["status"] == auto_speaker.AUTO_SPEAKER_PREFLIGHT_READY
    assert extract_calls == [
        {"channels": 2, "sample_rate": 44_100, "sample_format": "s16le"}
    ]
    assert len(classifier_calls) == 1
    assert classifier_calls[0][0] == str(extracted)
    assert classifier_calls[0][1] == ranges
    assert not extracted.exists()


def test_multi_lane_marker_never_enters_exact_two_preflight(monkeypatch):
    service = _service()
    calls = {"prepare": 0, "extract": 0, "classify": 0}

    async def forbidden_prepare(*_args, **_kwargs):
        calls["prepare"] += 1
        raise AssertionError("multi lane must not enter exact-two prepare")

    async def forbidden_extract(*_args, **_kwargs):
        calls["extract"] += 1
        raise AssertionError("multi lane must not enter exact-two extractor")

    def forbidden_classify(*_args, **_kwargs):
        calls["classify"] += 1
        raise AssertionError("multi lane must not enter exact-two ONNX")

    monkeypatch.setattr(service, "classify_two_speaker_genders", forbidden_classify)

    result = asyncio.run(
        auto_speaker.run_auto_speaker_preflight(
            {
                "voice_kind": "auto_speaker_gender",
                "voice_selection_mode": "auto_speaker",
                "auto_speaker_lane": "multi",
            },
            prepare_subtitles=forbidden_prepare,
            post_prepare_gate=lambda *_args, **_kwargs: True,
            extract_pcm=forbidden_extract,
        )
    )

    assert result["ok"] is False
    assert result["status"] == speaker_cast.AUTO_CAST_MANUAL_REQUIRED
    assert calls == {"prepare": 0, "extract": 0, "classify": 0}


@pytest.mark.parametrize(
    ("channels", "sample_rate", "sample_format", "expected_name"),
    (
        (1, 16_000, "s16le", "auto_speaker_16000_mono_s16le.pcm"),
        (2, 44_100, "s16le", "auto_speaker_44100_stereo_s16le.pcm"),
    ),
)
def test_pcm_extractor_accepts_only_the_two_locked_contracts(
    tmp_path,
    monkeypatch,
    channels,
    sample_rate,
    sample_format,
    expected_name,
):
    import bot

    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    calls = []
    monkeypatch.setattr(bot, "subtitle_dub_workspace_path_safety", lambda _path: {"allowed": True})
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(bot.subdub_media_preflight, "timeout_for_stage", lambda *_args, **_kwargs: 10.0)

    async def run(command, timeout):
        calls.append((command, timeout))
        Path(command[-1]).write_bytes(
            b"\x00\x00" * channels * sample_rate
        )
        return True, "ok"

    monkeypatch.setattr(bot, "run_subdub_ffmpeg_command", run)
    result = asyncio.run(
        bot._extract_subdub_auto_pcm(
            {
                "state": {
                    "_pipeline_workspace": str(tmp_path),
                    "_pipeline_saved_source_path": str(source),
                },
                "duration_seconds": 1,
            },
            {},
            channels=channels,
            sample_rate=sample_rate,
            sample_format=sample_format,
        )
    )

    assert result == str(tmp_path / expected_name)
    assert calls[0][0][calls[0][0].index("-ac") + 1] == str(channels)
    assert calls[0][0][calls[0][0].index("-ar") + 1] == str(sample_rate)


def test_stereo_extractor_covers_fractional_final_cue_for_montage(
    tmp_path,
    monkeypatch,
):
    import bot
    np = pytest.importorskip("numpy")

    service = _service()
    source = tmp_path / "fractional-source.mp4"
    source.write_bytes(b"source")
    calls = []
    monkeypatch.setattr(bot, "subtitle_dub_workspace_path_safety", lambda _path: {"allowed": True})
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(bot.subdub_media_preflight, "timeout_for_stage", lambda *_args, **_kwargs: 10.0)

    async def run(command, timeout):
        calls.append((command, timeout))
        seconds = float(command[command.index("-t") + 1])
        frame_count = int(round(seconds * service.PCM_SAMPLE_RATE))
        Path(command[-1]).write_bytes(b"\x00\x00\x00\x00" * frame_count)
        return True, "ok"

    monkeypatch.setattr(bot, "run_subdub_ffmpeg_command", run)
    pcm_path = asyncio.run(
        bot._extract_subdub_auto_pcm(
            {
                "state": {
                    "_pipeline_workspace": str(tmp_path),
                    "_pipeline_saved_source_path": str(source),
                },
                "duration_seconds": 1,
                "source_segments": [
                    {"start": 0.0, "end": 0.5},
                    {"start": 1.5, "end": 1.75},
                ],
            },
            {},
            channels=2,
            sample_rate=44_100,
            sample_format="s16le",
        )
    )

    assert calls[0][0][calls[0][0].index("-t") + 1] == "1.75"
    mix, mapped = service._read_montage(
        np,
        Path(pcm_path),
        {
            "speaker_0": [{"start": 0.0, "end": 0.5}],
            "speaker_1": [{"start": 1.5, "end": 1.75}],
        },
    )
    assert mix.shape == (2, int(0.75 * service.PCM_SAMPLE_RATE))
    assert mapped["speaker_1"][0]["end"] == 1.75


@pytest.mark.parametrize(
    ("channels", "sample_rate", "sample_format"),
    (
        (1, 44_100, "s16le"),
        (2, 16_000, "s16le"),
        (2, 44_100, "f32le"),
        (3, 44_100, "s16le"),
    ),
)
def test_pcm_extractor_rejects_every_other_contract_before_ffmpeg(
    tmp_path,
    monkeypatch,
    channels,
    sample_rate,
    sample_format,
):
    import bot

    calls = []
    monkeypatch.setattr(
        bot,
        "frame_video_ffmpeg_path",
        lambda: calls.append("ffmpeg") or "ffmpeg",
    )

    with pytest.raises(
        speaker_cast.AutoCastUnavailable,
        match="^AUTO_CAST_UNAVAILABLE$",
    ):
        asyncio.run(
            bot._extract_subdub_auto_pcm(
                {},
                {},
                channels=channels,
                sample_rate=sample_rate,
                sample_format=sample_format,
            )
        )

    assert calls == []


def test_exact_two_classifier_timeout_sets_stop_and_returns_manual(monkeypatch):
    service = _service()
    stopped = threading.Event()

    def block_until_stopped(*_args, stop_requested, **_kwargs):
        while not stop_requested():
            time.sleep(0.005)
        stopped.set()
        raise speaker_cast.AutoCastManualRequired()

    monkeypatch.setattr(service, "CLASSIFIER_WALL_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(service, "classify_two_speaker_genders", block_until_stopped)

    with pytest.raises(
        speaker_cast.AutoCastManualRequired,
        match="^AUTO_CAST_MANUAL_REQUIRED$",
    ):
        asyncio.run(
            auto_speaker._classify_off_event_loop(
                Path("unused-stereo.pcm"),
                {"speaker_0": [(0.0, 1.0)], "speaker_1": [(1.0, 2.0)]},
            )
        )

    assert stopped.is_set()


def test_noncooperative_onnx_call_cannot_block_timeout_forever(monkeypatch):
    service = _service()
    release = threading.Event()
    started = threading.Event()
    safety_release = threading.Timer(1.0, release.set)

    def noncooperative(*_args, **_kwargs):
        started.set()
        release.wait()
        raise speaker_cast.AutoCastManualRequired()

    monkeypatch.setattr(service, "CLASSIFIER_WALL_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(service, "classify_two_speaker_genders", noncooperative)
    monkeypatch.setattr(auto_speaker, "_CLASSIFIER_DRAIN_GRACE_SECONDS", 0.05, raising=False)
    safety_release.start()
    started_at = time.monotonic()
    returned_at = []

    async def scenario():
        with pytest.raises(
            speaker_cast.AutoCastManualRequired,
            match="^AUTO_CAST_MANUAL_REQUIRED$",
        ):
            await auto_speaker._classify_off_event_loop(
                Path("unused-stereo.pcm"),
                {"speaker_0": [(0.0, 1.0)], "speaker_1": [(1.0, 2.0)]},
            )
        returned_at.append(time.monotonic())
        release.set()

    try:
        asyncio.run(scenario())
        elapsed = returned_at[0] - started_at
    finally:
        release.set()
        safety_release.cancel()

    assert started.is_set()
    assert elapsed < 0.25


def test_classifier_concurrency_lock_rejects_second_heavy_inference(monkeypatch):
    service = _service()
    lock = threading.Lock()
    assert lock.acquire(blocking=False)
    monkeypatch.setattr(service, "_CLASSIFIER_LOCK", lock, raising=False)
    monkeypatch.setattr(
        service,
        "_select_bounded_cues",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("second call must fail before buffers or models")
        ),
    )

    with pytest.raises(
        speaker_cast.AutoCastManualRequired,
        match="^AUTO_CAST_MANUAL_REQUIRED$",
    ):
        service.classify_two_speaker_genders(
            "unused.pcm",
            {"speaker_0": [(0.0, 1.0)] * 4, "speaker_1": [(1.0, 2.0)] * 4},
            deadline_monotonic=time.monotonic() + 10.0,
            stop_requested=lambda: False,
        )

    assert lock.locked()
    lock.release()


def test_preflight_cancel_stops_classifier_and_cleans_pcm(tmp_path, monkeypatch):
    service = _service()
    ranges = {
        "speaker_0": [(0.0, 1.0), (2.0, 3.0), (4.0, 5.0), (6.0, 7.0)],
        "speaker_1": [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0), (7.0, 8.0)],
    }
    pcm_path = tmp_path / "cancel-stereo.pcm"
    started = threading.Event()
    stopped = threading.Event()
    monkeypatch.setattr(auto_speaker, "_validated_classifier_inputs", lambda _prepared: (["speaker_0", "speaker_1"], ranges))

    async def extract_pcm(*_args, **_kwargs):
        pcm_path.write_bytes(b"\x00\x00\x00\x00" * (8 * service.PCM_SAMPLE_RATE))
        return str(pcm_path)

    def block_until_stopped(*_args, stop_requested, **_kwargs):
        started.set()
        while not stop_requested():
            time.sleep(0.005)
        stopped.set()
        raise speaker_cast.AutoCastManualRequired()

    monkeypatch.setattr(service, "CLASSIFIER_WALL_TIMEOUT_SECONDS", 10.0)
    monkeypatch.setattr(service, "classify_two_speaker_genders", block_until_stopped)

    async def scenario():
        task = asyncio.create_task(
            auto_speaker.run_auto_speaker_preflight(
                {
                    "voice_kind": "auto_speaker_gender",
                    "voice_selection_mode": "auto_speaker",
                },
                prepare_subtitles=lambda *_args, **_kwargs: {
                    "state": {"_pipeline_workspace": str(tmp_path)}
                },
                post_prepare_gate=lambda *_args, **_kwargs: True,
                extract_pcm=extract_pcm,
            )
        )
        await asyncio.to_thread(started.wait, 1.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())

    assert stopped.is_set()
    assert not pcm_path.exists()
