"""Focused test suite for P0.PRODUCT_VIDEO_STORYBOARD_KLING_3_TURBO_DURATION_CONTRACT_CLOSURE_R12_1.

Covers:
- FIRST_RED_1: kling-3.0-turbo wire duration 8 rejected before transport with provider_duration_unsupported_no_charge
- FIRST_RED_2: Canonical Storyboard 8s target adapts to provider wire duration 10
- FIRST_RED_3: Provider catalog advertises kling-3.0-turbo with submit duration 10 / supported [5, 10]
- FIRST_RED_4: 10s provider clip deterministically trimmed to canonical 8s scene clip and concats to 16s master
- Routing / fail-closed / cost accounting invariants
"""

import asyncio
import json
import os
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from providers.video_generic_http_provider import (
    KLING_MODEL_SUPPORTED_I2V_DURATIONS,
    VideoProviderContractError,
    _key4u_wire_payload,
    build_key4u_video_payload,
)
from services.multiscene_video_pipeline import (
    SceneSpec,
    finalize_multiscene_scene_clips,
)
from services.video_provider_base import VideoGenerationRequest
from services.video_provider_catalog import load_video_provider_catalog
from services.video_real_render_connector import (
    _render_scene_async,
    _run_per_scene_provider_orchestrator,
)
import services.video_real_render_connector as video_real_render_connector
normalize_storyboard_provider_clip = getattr(
    video_real_render_connector,
    "normalize_storyboard_provider_clip",
    None,
)



@pytest.fixture
def mock_storyboard_files(tmp_path):
    panel1 = tmp_path / "panel_001.png"
    panel2 = tmp_path / "panel_002.png"
    clip1 = tmp_path / "provider_scene_001.mp4"
    clip2 = tmp_path / "provider_scene_002.mp4"

    panel1.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 256)
    panel2.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 256)
    clip1.write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 512)
    clip2.write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 512)

    return {
        "panel1": str(panel1),
        "panel2": str(panel2),
        "clip1": str(clip1),
        "clip2": str(clip2),
        "tmp_path": tmp_path,
    }


def _build_test_storyboard_job(files: dict, model: str = "kling-3.0-turbo") -> dict:
    scene_cards = [
        {"scene_index": 1, "prompt": "Scene 1: Turbo close up", "image_path": files["panel1"]},
        {"scene_index": 2, "prompt": "Scene 2: Turbo wide reveal", "image_path": files["panel2"]},
    ]
    return {
        "job_id": "job_1155_turbo_adaptation",
        "id": "job_1155_turbo_adaptation",
        "user_id": "7001",
        "product_type": "storyboard_to_video",
        "engine_route": "storyboard_to_video",
        "engine_adapter": "storyboard_scene_image_video_engine",
        "orchestration_mode": "per_scene_8s",
        "required_capability": "image_to_video",
        "selected_provider": "key4u_video",
        "model": model,
        "selected_model": model,
        "pinned_wire_model": model,
        "scene_count": 2,
        "scene_duration_seconds": 8,
        "duration_seconds": 16,
        "aspect_ratio": "9:16",
        "scene_cards": scene_cards,
        "storyboard_panels": [
            {"scene_index": 1, "local_path": files["panel1"]},
            {"scene_index": 2, "local_path": files["panel2"]},
        ],
        "project": {
            "id": 1155,
            "scene_cards_json": json.dumps(scene_cards),
            "asset_pack_json": json.dumps({
                "product_type": "storyboard_to_video",
                "selected_provider": "key4u_video",
                "selected_model": model,
                "model": model,
                "scene_cards": scene_cards,
            }),
            "invoice_json": json.dumps({
                "total_xu": 80,
                "selected_model": model,
            }),
        },
    }


# ===========================================================================
# FIRST_RED_1: Turbo direct 8s wire rejected before transport
# ===========================================================================

def test_first_red_1_turbo_supported_durations_strictly_5_and_10():
    """FIRST_RED_1: KLING_MODEL_SUPPORTED_I2V_DURATIONS for kling-3.0-turbo must be {5, 10}, excluding 8."""
    supported = KLING_MODEL_SUPPORTED_I2V_DURATIONS.get("kling-3.0-turbo")
    assert supported == {5, 10}, f"Expected {5, 10}, got {supported}"
    assert 8 not in supported, "Direct wire duration 8 must be forbidden for kling-3.0-turbo"


def test_first_red_1_direct_wire_duration_8_fails_closed_before_transport():
    """FIRST_RED_1: Attempting direct wire duration 8 for kling-3.0-turbo must raise provider_duration_unsupported_no_charge."""
    payload = {
        "capability": "image_to_video",
        "metadata": {
            "selected_family": "kling",
            "pinned_wire_model": "kling-3.0-turbo",
        },
        "image": "data:image/jpeg;base64,dGVzdA==",
        "duration": 8,
    }
    with pytest.raises(VideoProviderContractError) as exc_info:
        _key4u_wire_payload(payload)

    err = exc_info.value
    assert err.code == "provider_duration_unsupported_no_charge"
    assert err.debug.get("supported_durations") == [5, 10]
    assert err.debug.get("no_charge") is True
    assert err.debug.get("duration") == 8
    assert err.debug.get("model") == "kling-3.0-turbo"


# ===========================================================================
# FIRST_RED_2: Storyboard 8s target adapts to 10s wire
# ===========================================================================

def test_first_red_2_storyboard_8s_target_adapts_to_wire_duration_10(mock_storyboard_files, monkeypatch):
    """FIRST_RED_2: Storyboard with kling-3.0-turbo must submit duration=10 on wire while retaining public_scene_target=8."""
    monkeypatch.setenv("VIDEO_PROVIDER_CHAIN", "key4u_video")
    job = _build_test_storyboard_job(mock_storyboard_files, model="kling-3.0-turbo")

    scene_payload = {
        "scene_id": 1,
        "video_prompt": "Scene 1: Turbo close up",
        "aspect_ratio": "9:16",
        "target_duration_sec": 8.0,
    }
    from types import SimpleNamespace
    scene_obj = SimpleNamespace(**scene_payload)
    scene_obj._toan_aas_job = job
    raw_path = str(mock_storyboard_files["tmp_path"] / "scene_raw.mp4")

    captured_requests = []

    def mock_run_provider(req, **kwargs):
        captured_requests.append(req)
        Path(raw_path).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 512)
        return {
            "ok": True,
            "status": "SUCCESS",
            "provider": "key4u_video",
            "provider_task_ids": ["task_turbo_10s"],
            "output_path": raw_path,
            "model": "kling-3.0-turbo",
            "duration": 10.0,
            "result_url_present": True,
        }

    with patch("services.video_real_render_connector.run_provider_generation", side_effect=mock_run_provider), \
         patch("services.video_real_render_connector.normalize_storyboard_provider_clip", return_value=raw_path):
        res = asyncio.run(_render_scene_async(scene_obj, raw_path, ["key4u_video"]))

    assert len(captured_requests) == 1
    req = captured_requests[0]
    # Wire submit duration must be 10
    assert req.duration_seconds == 10.0, f"Expected wire duration 10.0, got {req.duration_seconds}"
    assert req.metadata.get("provider_submit_duration_seconds") == 10
    assert req.metadata.get("public_scene_target_seconds") == 8
    assert req.metadata.get("scene_duration_seconds") == 8
    assert req.metadata.get("selected_model") == "kling-3.0-turbo"
    assert req.metadata.get("pinned_wire_model") == "kling-3.0-turbo"


# ===========================================================================
# FIRST_RED_3: Provider catalog advertises Turbo submit duration 10
# ===========================================================================

def test_first_red_3_catalog_advertises_turbo_submit_duration_10():
    """FIRST_RED_3: Provider catalog for kling-3.0-turbo must advertise clip_seconds=10 and max_single_task_seconds=10."""
    catalog = load_video_provider_catalog()
    model_cfg = catalog.get("providers", {}).get("key4u_video", {}).get("models", {}).get("kling-3.0-turbo", {})
    assert model_cfg, "kling-3.0-turbo must exist in key4u_video catalog"
    assert model_cfg.get("clip_seconds") == 10, f"Expected clip_seconds 10, got {model_cfg.get('clip_seconds')}"
    assert model_cfg.get("max_single_task_seconds") == 10, f"Expected max_single_task_seconds 10, got {model_cfg.get('max_single_task_seconds')}"
    assert model_cfg.get("supported_durations") == [5, 10], f"Expected supported_durations [5, 10], got {model_cfg.get('supported_durations')}"


# ===========================================================================
# FIRST_RED_4: 10s provider clip normalized to 8s scene and 16s master concat
# ===========================================================================

def test_first_red_4_provider_output_normalization_contract(mock_storyboard_files):
    """FIRST_RED_4: normalize_storyboard_provider_clip must deterministically trim 10s clip to canonical 8s scene clip."""
    source_10s = str(mock_storyboard_files["tmp_path"] / "source_10s.mp4")
    Path(source_10s).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 512)
    normalized_8s = str(mock_storyboard_files["tmp_path"] / "normalized_8s.mp4")

    def mock_normalize_scene_duration(src, dst, target_duration_sec, **kw):
        assert target_duration_sec == 8.0, f"Expected target 8.0, got {target_duration_sec}"
        Path(dst).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 256)
        return dst

    with patch("services.video_real_render_connector.probe_duration", return_value=10.0), \
         patch("services.video_real_render_connector.normalize_scene_duration", side_effect=mock_normalize_scene_duration):
        out = normalize_storyboard_provider_clip(source_10s, normalized_8s, target_seconds=8.0)
        assert out == normalized_8s
        assert os.path.isfile(out)


def test_first_red_4_two_scenes_concat_to_16s_master(mock_storyboard_files, monkeypatch):
    """FIRST_RED_4: Two normalized 8s clips concat to 16s master MP4 with unified paths."""
    job = _build_test_storyboard_job(mock_storyboard_files, model="kling-3.0-turbo")
    workspace = str(mock_storyboard_files["tmp_path"] / "r12_1_concat_ws")
    os.makedirs(workspace, exist_ok=True)
    master_path = os.path.join(workspace, "final_master.mp4")
    Path(master_path).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 1024)

    def mock_render_scene(scene, raw_path, provider_order):
        Path(raw_path).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 256)
        scene_id = getattr(scene, "scene_id", 1)
        return {
            "ok": True,
            "status": "clip_downloaded",
            "provider": "key4u_video",
            "task_id": f"task_{scene_id}",
            "scene_id": scene_id,
            "scene_index": scene_id,
            "output_path": raw_path,
            "clip_path": raw_path,
            "clip_valid": True,
            "validation_passed": True,
            "output_validated": True,
            "model": "kling-3.0-turbo",
            "duration": 8.0,
            "normalized_scene_duration": 8.0,
            "public_scene_target_seconds": 8,
            "provider_submit_duration_seconds": 10,
            "result_url_present": True,
        }

    def mock_finalize(*args, **kwargs):
        return {
            "ok": True,
            "status": "completed",
            "final_video_path": master_path,
            "master_video_path": master_path,
            "duration_sec": 16.0,
            "scene_count": 2,
        }

    with patch("services.video_real_render_connector._render_scene_async", side_effect=mock_render_scene), \
         patch("services.video_real_render_connector.finalize_multiscene_scene_clips", side_effect=mock_finalize), \
         patch("services.video_local_validation.probe_video_file", return_value={"ok": True, "duration": 8.0, "has_video": True}), \
         patch("services.video_final_output.probe_video", return_value={"ok": True, "duration": 8.0, "has_video": True}):
        res = _run_per_scene_provider_orchestrator(
            job,
            workspace,
            provider_order=["key4u_video"],
            provider_events=[],
            debug_results=[],
        )

    assert res.get("ok") is True
    assert res.get("final_video_path") == master_path
    assert res.get("output_path") == master_path
    assert res.get("final_output_path") == master_path
    assert res.get("duration_sec") == 16.0 or res.get("final_duration_seconds") == 16.0


# ===========================================================================
# COST ACCOUNTING INVARIANT
# ===========================================================================

def test_provider_cost_accounting_uses_submit_duration_10s(mock_storyboard_files, monkeypatch):
    """Cost accounting must base estimated provider cost on submit duration 10s, not public 8s."""
    job = _build_test_storyboard_job(mock_storyboard_files, model="kling-3.0-turbo")
    scene_payload = {
        "scene_id": 1,
        "video_prompt": "Scene 1: Turbo close up",
        "aspect_ratio": "9:16",
        "target_duration_sec": 8.0,
    }
    from types import SimpleNamespace
    scene_obj = SimpleNamespace(**scene_payload)
    scene_obj._toan_aas_job = job
    raw_path = str(mock_storyboard_files["tmp_path"] / "scene_raw_cost.mp4")

    captured_requests = []

    def mock_run_provider(req, **kwargs):
        captured_requests.append(req)
        Path(raw_path).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 512)
        return {
            "ok": True,
            "status": "SUCCESS",
            "provider": "key4u_video",
            "provider_task_ids": ["task_turbo_cost"],
            "output_path": raw_path,
            "model": "kling-3.0-turbo",
            "duration": 10.0,
            "result_url_present": True,
        }

    with patch("services.video_real_render_connector.run_provider_generation", side_effect=mock_run_provider), \
         patch("services.video_real_render_connector.normalize_storyboard_provider_clip", return_value=raw_path):
        asyncio.run(_render_scene_async(scene_obj, raw_path, ["key4u_video"]))

    assert len(captured_requests) == 1
    req = captured_requests[0]
    meta = req.metadata
    assert meta.get("provider_billable_submit_seconds") == 10
    # Customer price remains unchanged
    assert meta.get("public_scene_target_seconds") == 8
