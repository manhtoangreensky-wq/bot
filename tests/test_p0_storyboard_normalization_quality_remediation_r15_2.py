"""Regression tests for Storyboard Normalization Quality Remediation R15.2.

Issue: #1155
Task ID: P0.PRODUCT_VIDEO_STORYBOARD_NORMALIZATION_QUALITY_REMEDIATION_R15_2
Contract:
- STATIC_FRAME_PADDING_TO_MEET_DURATION = FORBIDDEN
- UNBOUNDED_SLOW_MOTION = FORBIDDEN
- FRAME_DUPLICATION_STRETCH = FORBIDDEN
- SILENT_DURATION_FABRICATION = FORBIDDEN
- Raw clips materially shorter than contracted 8.0s MUST fail closed with blocker:
  scene_duration_short_no_charge
"""

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from services import multiscene_video_pipeline as mvp
from services.multiscene_video_pipeline import (
    SceneSpec,
    STORYBOARD_DURATION_TOLERANCE_SECONDS,
    finalize_multiscene_scene_clips,
    normalize_scene_duration,
    validate_storyboard_scene_duration,
)
from services import video_real_render_connector as connector
from services.video_real_render_connector import RealVideoRenderError


# ---------------------------------------------------------------------------
# Unit tests for validate_storyboard_scene_duration
# ---------------------------------------------------------------------------

def test_validate_storyboard_scene_duration_exact():
    res = validate_storyboard_scene_duration(8.0, 8.0)
    assert res["duration_valid"] is True
    assert res["blocker"] == ""
    assert res["expected_duration"] == 8.0
    assert res["actual_duration"] == 8.0
    assert res["duration_delta"] == 0.0
    assert res["minimum_accepted_duration"] == 7.75
    assert res["maximum_accepted_duration"] == 8.25


def test_validate_storyboard_scene_duration_within_tolerance():
    # 7.95s is within [7.75, 8.25]
    res_under = validate_storyboard_scene_duration(7.95, 8.0)
    assert res_under["duration_valid"] is True
    assert res_under["blocker"] == ""
    assert res_under["duration_delta"] == -0.05

    # 8.20s is within [7.75, 8.25]
    res_over = validate_storyboard_scene_duration(8.20, 8.0)
    assert res_over["duration_valid"] is True
    assert res_over["blocker"] == ""
    assert res_over["duration_delta"] == 0.20


def test_validate_storyboard_scene_duration_veo_fast_raw_short_defect():
    # Veo 3.1 Fast defect returns ~6.016s when 8.0s contracted
    res = validate_storyboard_scene_duration(6.016, 8.0)
    assert res["duration_valid"] is False
    assert res["blocker"] == "scene_duration_short_no_charge"
    assert res["duration_delta"] == -1.984
    assert res["actual_duration"] == 6.016
    assert res["expected_duration"] == 8.0
    assert res["minimum_accepted_duration"] == 7.75


def test_validate_storyboard_scene_duration_extreme_short():
    res = validate_storyboard_scene_duration(2.0, 8.0)
    assert res["duration_valid"] is False
    assert res["blocker"] == "scene_duration_short_no_charge"

    res_zero = validate_storyboard_scene_duration(0.0, 8.0)
    assert res_zero["duration_valid"] is False
    assert res_zero["blocker"] == "scene_duration_short_no_charge"


def test_validate_storyboard_scene_duration_excessive_long():
    res = validate_storyboard_scene_duration(9.5, 8.0)
    assert res["duration_valid"] is False
    assert res["blocker"] == "scene_duration_long_no_charge"
    assert res["duration_delta"] == 1.5


# ---------------------------------------------------------------------------
# normalize_scene_duration tests
# ---------------------------------------------------------------------------

def test_normalize_scene_duration_forbids_tpad_by_default(monkeypatch, tmp_path):
    source = tmp_path / "raw_6s.mp4"
    source.write_bytes(b"dummy_mp4_bytes")
    target = tmp_path / "normalized_8s.mp4"

    monkeypatch.setattr(mvp, "_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(mvp, "probe_duration", lambda _path: 6.016)
    monkeypatch.setattr(mvp, "_display_geometry", lambda _path: (540, 960))

    # By default, allow_frame_padding is False, so attempting to normalize 6.016s to 8.0s MUST raise
    with pytest.raises(ValueError, match="scene_duration_short_no_charge"):
        normalize_scene_duration(str(source), str(target), 8.0)


def test_normalize_scene_duration_explicit_frame_padding(monkeypatch, tmp_path):
    source = tmp_path / "raw_6s.mp4"
    source.write_bytes(b"dummy_mp4_bytes")
    target = tmp_path / "normalized_8s.mp4"

    captured = {}

    def fake_run(command, timeout):
        captured["command"] = list(command)
        Path(command[-1]).write_bytes(b"padded_video")
        return MagicMock(returncode=0)

    monkeypatch.setattr(mvp, "_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(mvp, "probe_duration", lambda _path: 6.016)
    monkeypatch.setattr(mvp, "_display_geometry", lambda _path: (540, 960))
    monkeypatch.setattr(mvp, "safe_run_ffmpeg", fake_run)

    # If explicitly requested, allow_frame_padding=True can use tpad
    normalize_scene_duration(str(source), str(target), 8.0, allow_frame_padding=True)
    vf = captured["command"][captured["command"].index("-vf") + 1]
    assert "tpad=stop_mode=clone" in vf


# ---------------------------------------------------------------------------
# finalize_multiscene_scene_clips integration tests
# ---------------------------------------------------------------------------

def test_finalize_multiscene_scene_clips_fails_closed_on_short_scene(tmp_path, monkeypatch):
    workspace = tmp_path / "ws_short"
    workspace.mkdir()

    scene_1_file = tmp_path / "scene_001.mp4"
    scene_1_file.write_bytes(b"scene1_bytes")
    scene_2_file = tmp_path / "scene_002.mp4"
    scene_2_file.write_bytes(b"scene2_bytes")

    durations = {
        str(scene_1_file): 8.000,
        str(scene_2_file): 6.016,  # DEFECTIVE SCENE
    }

    def mock_probe_duration(p):
        path_str = str(p)
        for key, val in durations.items():
            if key in path_str or Path(path_str).name in key:
                return val
        if "scene_001" in path_str:
            return 8.000
        if "scene_002" in path_str:
            return 6.016
        return 8.0

    monkeypatch.setattr(mvp, "probe_duration", mock_probe_duration)
    monkeypatch.setattr(mvp, "_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(mvp, "_display_geometry", lambda _p: (540, 960))
    monkeypatch.setattr(mvp, "probe_media_streams", lambda _p: {"streams": [{"codec_type": "video"}]})

    def fake_normalize(src, dst, target_duration_sec, **kw):
        Path(dst).write_bytes(b"normalized")
        return dst

    monkeypatch.setattr(mvp, "normalize_scene_duration", fake_normalize)

    mock_stitch = MagicMock()
    monkeypatch.setattr(mvp, "stitch_scenes", mock_stitch)

    scenes = [
        SceneSpec(scene_id=1, title="S1", visual_prompt="p1", video_prompt="vp1", target_duration_sec=8.0),
        SceneSpec(scene_id=2, title="S2", visual_prompt="p2", video_prompt="vp2", target_duration_sec=8.0),
    ]
    scene_clip_paths = {
        1: str(scene_1_file),
        2: str(scene_2_file),
    }

    res = finalize_multiscene_scene_clips(
        user_id="user1",
        job_id="job_short",
        workspace_dir=str(workspace),
        scenes=scenes,
        scene_clip_paths=scene_clip_paths,
    )

    # Must fail closed immediately on scene 2
    assert res["ok"] is False
    assert res["status"] == "failed"
    assert res["error"] == "scene_duration_short_no_charge"
    assert res["blocker"] == "scene_duration_short_no_charge"
    assert res["no_charge"] is True
    assert res["concat_attempted"] is False
    assert res["concat_ready"] is False
    assert res["final_mp4_valid"] is False
    assert res["failed_scene_index"] == 2
    assert res["raw_duration"] == 6.016
    assert res["expected_duration"] == 8.0

    # stitch_scenes must NEVER have been called
    mock_stitch.assert_not_called()

    # Manifest must reflect failed status and blocked concat
    manifest = mvp.load_multiscene_manifest(str(workspace), job_id="job_short", user_id="user1")
    assert manifest.status == "failed"
    assert manifest.concat_state == "blocked"
    assert manifest.errors.get("2") == "scene_duration_short_no_charge"
    assert manifest.errors.get("final") == "scene_duration_short_no_charge"


def test_finalize_multiscene_scene_clips_passes_when_all_scenes_meet_contract(tmp_path, monkeypatch):
    workspace = tmp_path / "ws_pass"
    workspace.mkdir()

    scene_1_file = tmp_path / "scene_001.mp4"
    scene_1_file.write_bytes(b"scene1_bytes")
    scene_2_file = tmp_path / "scene_002.mp4"
    scene_2_file.write_bytes(b"scene2_bytes")

    durations = {
        "scene_001": 8.000,
        "scene_002": 7.950,  # Within 0.25s tolerance of 8.0s
        "master_video_only": 15.95,
        "final_output": 15.95,
    }

    def mock_probe_duration(p):
        path_str = str(p)
        for key, val in durations.items():
            if key in path_str:
                return val
        return 15.95

    monkeypatch.setattr(mvp, "probe_duration", mock_probe_duration)
    monkeypatch.setattr(mvp, "_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(mvp, "_display_geometry", lambda _p: (540, 960))
    monkeypatch.setattr(mvp, "probe_media_streams", lambda _p: {"streams": [{"codec_type": "video"}]})

    def fake_normalize(src, dst, target_duration_sec, **kw):
        Path(dst).write_bytes(b"normalized")
        return dst

    monkeypatch.setattr(mvp, "normalize_scene_duration", fake_normalize)

    def fake_stitch(inputs, output_path, **kw):
        Path(output_path).write_bytes(b"master_video")
        return output_path

    monkeypatch.setattr(mvp, "stitch_scenes", fake_stitch)
    monkeypatch.setattr(
        mvp,
        "mux_final_multiscene_video",
        lambda **kw: Path(kw["output_path"]).write_bytes(b"final") or kw["output_path"],
    )
    monkeypatch.setattr(mvp, "_validate_composed_video", lambda p, **kw: {"valid": True, "duration": 15.95})

    scenes = [
        SceneSpec(scene_id=1, title="S1", visual_prompt="p1", video_prompt="vp1", target_duration_sec=8.0),
        SceneSpec(scene_id=2, title="S2", visual_prompt="p2", video_prompt="vp2", target_duration_sec=8.0),
    ]
    scene_clip_paths = {
        1: str(scene_1_file),
        2: str(scene_2_file),
    }

    res = finalize_multiscene_scene_clips(
        user_id="user1",
        job_id="job_pass",
        workspace_dir=str(workspace),
        scenes=scenes,
        scene_clip_paths=scene_clip_paths,
        final_duration_tolerance_sec=0.25,
    )

    assert res["ok"] is True
    assert res["status"] == "completed"
    assert res["final_mp4_valid"] is True
    assert res["error"] is None
    manifest = mvp.load_multiscene_manifest(str(workspace), job_id="job_pass", user_id="user1")
    assert manifest.status == "final_ready"
    assert manifest.concat_state == "completed"


# ---------------------------------------------------------------------------
# Connector fail-closed tests
# ---------------------------------------------------------------------------

def test_connector_orchestrator_preserves_short_scene_blocker(monkeypatch, tmp_path):
    job = {
        "job_id": "job_storyboard_test",
        "user_id": "user1",
        "storyboard_scenes": [
            {"scene_id": 1, "prompt": "Scene 1", "scene_seconds": 8},
            {"scene_id": 2, "prompt": "Scene 2", "scene_seconds": 8},
        ],
        "no_charge": False,
    }
    workspace = tmp_path / "ws_orchestrator"
    workspace.mkdir()
    monkeypatch.setattr(connector, "_canonical_product_video_workspace", lambda _job: str(workspace))

    s1 = workspace / "s1.mp4"
    s1.write_bytes(b"s1")
    s2 = workspace / "s2.mp4"
    s2.write_bytes(b"s2")

    async def fake_render_async(scene, raw_path, provider_order):
        idx = scene.scene_id
        path = str(s1 if idx == 1 else s2)
        return {
            "ok": True,
            "scene_index": idx,
            "status": "completed",
            "output_path": path,
            "video_path": path,
            "provider_status": "completed",
        }

    monkeypatch.setattr(connector, "_render_scene_async", fake_render_async)
    monkeypatch.setattr(
        connector.video_final_output,
        "probe_video",
        lambda _p: {"ok": True, "has_video": True, "duration": 8.0, "bytes": 1000},
    )

    monkeypatch.setattr(
        connector.video_project_queue_service,
        "product_video_scene_ledger_state",
        lambda _q, _j, _b: {"finalizer_unlocked": True, "completed_scene_count": 2},
    )

    mock_fail_result = {
        "ok": False,
        "status": "failed",
        "error": "scene_duration_short_no_charge",
        "blocker": "scene_duration_short_no_charge",
        "no_charge": True,
        "concat_attempted": False,
        "final_video_path": "",
    }
    monkeypatch.setattr(connector, "finalize_multiscene_scene_clips", lambda **kw: mock_fail_result)

    res = connector._run_per_scene_provider_orchestrator(
        job=job,
        workspace=str(workspace),
        provider_order=["shopaikey_video"],
        provider_events=[],
        debug_results=[],
    )

    assert res["ok"] is False
    assert res["status"] == "failed"
    assert res["terminal_state"] == "failed"
    assert res["error"] == "scene_duration_short_no_charge"
    assert res["blocker"] == "scene_duration_short_no_charge"
    assert res["final_decision"] == "scene_duration_short_no_charge"
    assert res["no_charge"] is True
    assert res["final_mp4_valid"] is False
    assert res["concat_output_valid"] is False


def test_connector_single_scene_inplace_normalizer_raises_short_error(tmp_path, monkeypatch):
    source = tmp_path / "raw.mp4"
    source.write_bytes(b"video")
    target = tmp_path / "norm.mp4"

    monkeypatch.setattr(
        connector.video_final_output,
        "probe_video",
        lambda _p: {"ok": True, "has_video": True, "duration": 6.016, "bytes": 1000},
    )

    with pytest.raises(RealVideoRenderError) as exc_info:
        connector.normalize_storyboard_provider_clip(
            str(source),
            str(target),
            target_seconds=8.0,
            tolerance_seconds=0.25,
        )

    err = exc_info.value
    assert str(err) == "scene_duration_short_no_charge"
    assert err.diagnostics["reason"] == "scene_duration_short"
    assert err.diagnostics["current_duration"] == 6.016
    assert err.diagnostics["target_seconds"] == 8.0
