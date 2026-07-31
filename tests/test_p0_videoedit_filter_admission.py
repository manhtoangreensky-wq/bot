from __future__ import annotations

from types import SimpleNamespace

import pytest

from services import video_editengine1, video_local_editing


def _state() -> dict:
    return {
        "source_file_id": "source",
        "inspection_complete": True,
        "source_metadata": {"ok": True, "has_audio": True, "duration_ms": 10_000},
        "selected_tool": "manual",
        "manual_edit_plan": {
            "quality_filters": {"sharpen": True, "denoise": False},
        },
    }


def _runtime(**overrides) -> dict:
    value = {
        "enabled": True,
        "poll_enabled": True,
        "token_configured": True,
        "connected": True,
        "ffmpeg_path_configured": True,
        "ffprobe_path_configured": True,
        "delivery_configured": True,
        "heartbeat_contract_version": 1,
        "worker_owner": video_editengine1.OUTBOX_OWNER,
        "engine_route": video_editengine1.ENGINE_ROUTE,
        "capabilities": [video_editengine1.WORKER_CAPABILITY],
        "heartbeat_age_seconds": 1,
        "worker_id": "worker-a",
        "video_edit_filter_worker_id": "worker-a",
        "ffmpeg_path": "C:/ffmpeg/bin/ffmpeg.exe",
        "video_edit_filter_ffmpeg_path": "C:/ffmpeg/bin/ffmpeg.exe",
    }
    value.update(overrides)
    return value


def test_optional_filter_admission_fails_closed_without_worker_snapshot() -> None:
    result = video_editengine1.preflight(_state(), _runtime())
    assert result["ok"] is False
    assert result["reason"] == "local_worker_filter_snapshot_missing"
    assert result["required_filters"] == ["format", "unsharp"]


def test_optional_filter_admission_still_fails_closed_on_legacy_heartbeat() -> None:
    result = video_editengine1.preflight(
        _state(),
        _runtime(heartbeat_contract_version=0, video_edit_filters_known=False),
    )
    assert result["ok"] is False
    assert result["reason"] == "local_worker_contract_missing"


def test_canonical_filter_admission_requires_versioned_worker_ownership() -> None:
    result = video_editengine1.preflight(
        _state(),
        _runtime(
            heartbeat_contract_version=0,
            worker_owner="another-product",
            engine_route="provider-route",
            capabilities=[],
            video_edit_filters_known=True,
            video_edit_filters=["format", "unsharp"],
        ),
    )
    assert result["ok"] is False
    assert result["reason"] == "local_worker_contract_missing"


def test_boolean_heartbeat_contract_version_is_not_version_one() -> None:
    result = video_editengine1.preflight(
        _state(),
        _runtime(
            heartbeat_contract_version=True,
            video_edit_filters_known=True,
            video_edit_filters=["format", "unsharp"],
        ),
    )

    assert result["ok"] is False
    assert result["reason"] == "local_worker_contract_missing"


def test_boolean_heartbeat_age_is_not_a_fresh_runtime_snapshot() -> None:
    result = video_editengine1.preflight(
        _state(),
        _runtime(
            heartbeat_age_seconds=True,
            video_edit_filters_known=True,
            video_edit_filters=["format", "unsharp"],
        ),
    )

    assert result["ok"] is False
    assert result["reason"] == "local_worker_heartbeat_stale"


def test_optional_filter_admission_requires_the_exact_worker_filter() -> None:
    missing = video_editengine1.preflight(
        _state(),
        _runtime(video_edit_filters_known=True, video_edit_filters=["hqdn3d"]),
    )
    assert missing["ok"] is False
    assert missing["missing_filters"] == ["format", "unsharp"]

    ready = video_editengine1.preflight(
        _state(),
        _runtime(video_edit_filters_known=True, video_edit_filters=["format", "unsharp"]),
    )
    assert ready["ok"] is True
    assert ready["missing_filters"] == []


@pytest.mark.parametrize(
    ("runtime_patch", "reason"),
    [
        (
            {"worker_id": "", "video_edit_filter_worker_id": ""},
            "local_worker_filter_snapshot_owner_mismatch",
        ),
        (
            {"ffmpeg_path": "", "video_edit_filter_ffmpeg_path": ""},
            "local_worker_filter_snapshot_path_mismatch",
        ),
    ],
)
def test_filter_snapshot_never_passes_without_complete_executor_identity(
    runtime_patch: dict,
    reason: str,
) -> None:
    result = video_editengine1.preflight(
        _state(),
        _runtime(
            video_edit_filters_known=True,
            video_edit_filters=["format", "unsharp"],
            **runtime_patch,
        ),
    )

    assert result["ok"] is False
    assert result["reason"] == reason


def test_capability_admission_requires_the_same_worker_and_ffmpeg_identity() -> None:
    common = {
        "available_filters": {"format", "unsharp"},
        "filters_known": True,
        "has_audio": True,
        "snapshot_age_seconds": 1,
    }

    missing = video_editengine1.preflight(
        _state(),
        _runtime(
            video_edit_filters_known=True,
            video_edit_filters=["format", "unsharp"],
            worker_id="",
            video_edit_filter_worker_id="",
        ),
    )
    assert missing["reason"] == "local_worker_filter_snapshot_owner_mismatch"

    from services import video_edit_capabilities

    admission = video_edit_capabilities.runtime_capability_admission(
        "enhance_basic_sharpen",
        worker_id="",
        filter_worker_id="",
        ffmpeg_path="",
        filter_ffmpeg_path="",
        **common,
    )
    assert admission["ready"] is False
    assert admission["reason"] == "local_worker_filter_snapshot_owner_mismatch"


def test_loudnorm_without_audio_fails_closed_with_exact_reason() -> None:
    state = _state()
    state["source_metadata"] = {"ok": True, "has_audio": False, "duration_ms": 10_000}
    state["manual_edit_plan"] = {"audio_normalization": "loudnorm"}
    result = video_editengine1.preflight(
        state,
        _runtime(video_edit_filters_known=True, video_edit_filters=["loudnorm"]),
    )
    assert result["ok"] is False
    assert result["reason"] == "audio_stream_required_for_loudnorm"


def test_preflight_rejects_unknown_manual_plan_fields_before_job_creation() -> None:
    state = _state()
    state["source_metadata"] = {"ok": True, "has_audio": True, "duration_ms": 10_000}
    state["manual_edit_plan"] = {"provider_magic_effect": True}
    result = video_editengine1.preflight(state, _runtime())
    assert result["ok"] is False
    assert result["reason"] == "unknown_edit_plan_field:provider_magic_effect"


@pytest.mark.parametrize(
    ("patch", "expected"),
    [
        ({"crop_or_fit": {"aspect_ratio": "9:16", "mode": "fit"}}, {"format", "scale", "pad", "setsar"}),
        ({"crop_or_fit": {"aspect_ratio": "1:1", "mode": "crop"}}, {"format", "scale", "crop", "setsar"}),
        ({"rotation": 90}, {"format", "transpose"}),
        ({"flip": "horizontal"}, {"format", "hflip"}),
        ({"speed": 0.5}, {"format", "setpts", "atempo"}),
        ({"color_preset": "bright_clear"}, {"format", "eq", "unsharp"}),
        ({"text_overlay": {"content": "Chào", "start_ms": 0, "end_ms": 1_000}}, {"format", "drawtext"}),
        ({"subtitle_file": "subtitle.srt"}, {"format", "subtitles"}),
        ({"logo_overlay": {"path": "logo.png", "position": "top_right", "scale": 0.12, "opacity": 1.0}}, {"format", "colorchannelmixer", "scale", "overlay"}),
        ({"volume": 0.5}, {"format", "volume"}),
        ({"local_effects": {"fade_in_ms": 300, "fade_out_ms": 300}}, {"format", "fade", "afade"}),
        ({"remove_middle": {"start_ms": 2_000, "end_ms": 4_000}}, {"format", "trim", "setpts", "atrim", "asetpts", "concat"}),
        (
            {"concat_inputs": ["second.mp4"]},
            {
                "format", "scale", "pad", "setsar", "fps", "anullsrc",
                "trim", "setpts", "atrim", "asetpts",
            },
        ),
    ],
)
def test_every_executable_operation_declares_its_ffmpeg_filters(patch: dict, expected: set[str]) -> None:
    plan = video_local_editing.default_manual_edit_plan("source.mp4")
    plan["trim"] = {"start_ms": 0, "end_ms": 10_000}
    for key, value in patch.items():
        plan[key] = value

    required = video_local_editing.required_optional_filters(plan, has_audio=True)
    assert expected <= required


def test_keep_resolution_large_source_rechecks_scale_filters_on_worker() -> None:
    plan = video_local_editing.default_manual_edit_plan("source.mp4")
    plan["trim"] = {"start_ms": 0, "end_ms": 10_000}
    required = video_local_editing.required_optional_filters(
        plan,
        has_audio=True,
        source_width=3_840,
        source_height=2_160,
    )
    assert {"format", "scale", "setsar"} <= required

    with pytest.raises(video_local_editing.LocalVideoEditError, match="ffmpeg_filter_unavailable:scale"):
        video_local_editing.validate_required_optional_filters(
            plan,
            available_filters={"format", "pad", "setsar"},
            has_audio=True,
            source_width=3_840,
            source_height=2_160,
        )


def test_split_executor_rechecks_filters_on_the_exact_ffmpeg_binary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from services.video_smart_splitter import SplitRange

    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    monkeypatch.setattr(video_local_editing, "find_ffmpeg", lambda _value="": "ffmpeg")
    monkeypatch.setattr(video_local_editing, "find_ffprobe", lambda *_args, **_kwargs: "ffprobe")
    monkeypatch.setattr(
        video_local_editing,
        "probe_video_file",
        lambda *_args, **_kwargs: {
            "ok": True,
            "duration_ms": 4_000,
            "has_audio": True,
        },
    )
    discoveries: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        video_local_editing,
        "available_ffmpeg_filters",
        lambda path, *, refresh=False: (
            discoveries.append((path, refresh))
            or frozenset({"format", "setsar"})
        ),
    )

    with pytest.raises(
        video_local_editing.LocalVideoEditError,
        match="ffmpeg_filter_unavailable:scale",
    ):
        video_local_editing.execute_split_plan(
            str(source),
            [SplitRange(index=1, start_ms=0, end_ms=4_000)],
            workspace=tmp_path,
            coverage_required=True,
            ffmpeg_path="ffmpeg",
            ffprobe_path="ffprobe",
        )
    assert discoveries == [("ffmpeg", True)]


def test_manual_executor_rechecks_filters_on_the_exact_ffmpeg_binary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    plan = video_local_editing.default_manual_edit_plan(str(source))
    plan["quality_filters"]["sharpen"] = True
    discoveries: list[tuple[str, bool]] = []
    monkeypatch.setattr(video_local_editing, "find_ffmpeg", lambda _value="": "ffmpeg")
    monkeypatch.setattr(video_local_editing, "find_ffprobe", lambda *_args, **_kwargs: "ffprobe")
    monkeypatch.setattr(
        video_local_editing,
        "probe_video_file",
        lambda *_args, **_kwargs: {
            "ok": True,
            "duration_ms": 4_000,
            "has_audio": True,
            "width": 640,
            "height": 360,
        },
    )
    monkeypatch.setattr(
        video_local_editing,
        "available_ffmpeg_filters",
        lambda path, *, refresh=False: (
            discoveries.append((path, refresh)) or frozenset({"format"})
        ),
    )

    with pytest.raises(
        video_local_editing.LocalVideoEditError,
        match="ffmpeg_filter_unavailable:unsharp",
    ):
        video_local_editing.execute_manual_edit(
            plan,
            output_path=str(tmp_path / "output.mp4"),
            workspace=tmp_path,
            ffmpeg_path="ffmpeg",
            ffprobe_path="ffprobe",
        )

    assert discoveries == [("ffmpeg", True)]


def test_filter_cache_invalidates_when_the_same_binary_path_is_replaced(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    binary = tmp_path / "ffmpeg.exe"
    binary.write_bytes(b"first")
    calls: list[list[str]] = []

    def fake_run(args, **_kwargs):
        calls.append(list(args))
        filter_name = "format" if len(calls) == 1 else "scale"
        return SimpleNamespace(
            returncode=0,
            stdout=f" .. {filter_name}          V->V       test\n",
        )

    monkeypatch.setattr(video_local_editing.subprocess, "run", fake_run)

    first = video_local_editing.available_ffmpeg_filters(str(binary))
    binary.write_bytes(b"second-binary-image")
    second = video_local_editing.available_ffmpeg_filters(str(binary))

    assert "format" in first
    assert "scale" in second
    assert len(calls) == 2
