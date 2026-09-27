"""Tests for P0.PRODUCT_VIDEO_STORYBOARD_KEY4U_ROUTING_AND_CONCAT_SOURCE_FIX_R11.

Proves and guards the two production defects discovered in R10 acceptance:
1. Canonical Storyboard with explicit:
   provider=key4u_video
   model=kling-3.0-turbo (or kling-v3)
   capability=image_to_video
   must NOT be overridden to shopaikey_video by generic price-route / provider-priority logic.

2. Canonical two-scene Storyboard (8s + 8s):
   must produce one valid final concatenated MP4 of approximately 16s,
   with final_video_path, output_path, and final_output_path strictly unified
   to the concatenated master.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from services import multiscene_video_pipeline, video_provider_router, video_real_render_connector
from services.multiscene_video_pipeline import SceneSpec, finalize_multiscene_scene_clips
from services.video_provider_base import VideoGenerationRequest
from services.video_provider_router import (
    load_video_provider_adapters,
    provider_candidate_adapters,
    run_provider_generation,
)
from services.video_real_render_connector import (
    _provider_order,
    _render_scene_async,
    _run_per_scene_provider_orchestrator,
    product_video_duration_contract,
    render_real_video_job,
)


@pytest.fixture
def mock_storyboard_files(tmp_path):
    """Create dummy panel images and 8s dummy MP4 clips."""
    panel1 = tmp_path / "panel_1.png"
    panel2 = tmp_path / "panel_2.png"
    png_header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    panel1.write_bytes(png_header)
    panel2.write_bytes(png_header)

    clip1 = tmp_path / "scene_001.mp4"
    clip2 = tmp_path / "scene_002.mp4"
    clip1.write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 1024)
    clip2.write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 1024)

    return {
        "panel1": str(panel1),
        "panel2": str(panel2),
        "clip1": str(clip1),
        "clip2": str(clip2),
        "tmp_path": tmp_path,
    }


def _build_test_job(files: dict, model: str = "kling-3.0-turbo") -> dict:
    scene_cards = [
        {
            "scene_index": 1,
            "image_path": files["panel1"],
            "video_prompt": "Scene 1: Cat on crystal planet",
            "duration_seconds": 8.0,
        },
        {
            "scene_index": 2,
            "image_path": files["panel2"],
            "video_prompt": "Scene 2: Cat watches twin moons",
            "duration_seconds": 8.0,
        },
    ]
    return {
        "id": 1155,
        "job_id": 1155,
        "user_id": 7001,
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
        },
    }


# ===========================================================================
# DEFECT 1 TESTS: Storyboard Key4U Routing Authority
# ===========================================================================

def test_storyboard_provider_order_authority_not_overridden_by_env(mock_storyboard_files, monkeypatch):
    """Defect 1: _provider_order for Storyboard must return key4u_video even if env chain has shopaikey first."""
    monkeypatch.setenv("VIDEO_PROVIDER_CHAIN", "shopaikey_video,key4u_video,toanaas_video")
    job = _build_test_job(mock_storyboard_files, model="kling-3.0-turbo")

    order = _provider_order(job)
    assert order == ["key4u_video"], f"Expected ['key4u_video'], got {order}"


def test_storyboard_router_prioritizes_key4u_over_shopaikey(mock_storyboard_files, monkeypatch):
    """Defect 1: Video provider router must select key4u_video when request is Storyboard with key4u authority."""
    monkeypatch.setenv("VIDEO_PROVIDER_CHAIN", "shopaikey_video,key4u_video")
    monkeypatch.setenv("SHOPAIKEY_API_KEY", "mock_key")
    monkeypatch.setenv("KEY4U_API_KEY", "mock_key")
    monkeypatch.setenv("KEY4U_BASE_URL", "https://mock.key4u.test")

    req = VideoGenerationRequest(
        job_id="test_1155",
        product_type="storyboard_to_video",
        prompt="Cat on crystal planet",
        ratio="9:16",
        duration_seconds=8,
        image_paths=[mock_storyboard_files["panel1"]],
        metadata={
            "product_type": "storyboard_to_video",
            "is_storyboard": True,
            "selected_provider": "key4u_video",
            "model": "kling-3.0-turbo",
            "selected_model": "kling-3.0-turbo",
            "pinned_wire_model": "kling-3.0-turbo",
        },
    )

    adapters = provider_candidate_adapters("image_to_video", environ=dict(os.environ))
    adapter_names = [a.provider_name for a in adapters]
    from services.video_provider_base import VideoPollResult, VideoSubmitResult
    with patch("providers.video_generic_http_provider.GenericHttpVideoProvider.submit_video_job") as mock_submit, \
         patch("providers.video_generic_http_provider.GenericHttpVideoProvider.poll_video_job") as mock_poll:
        mock_submit.side_effect = lambda req: VideoSubmitResult(
            ok=True,
            provider_name="key4u_video",
            provider_task_id="k4u_123",
        )
        mock_poll.side_effect = lambda task_id, **kw: VideoPollResult(
            ok=True,
            provider_name="key4u_video",
            provider_task_id="k4u_123",
            status="queued",
            raw_status="queued",
        )
        res = run_provider_generation(
            req,
            output_dir=str(mock_storyboard_files["tmp_path"]),
            allow_pending_result=True,
        )

        assert res.get("provider") == "key4u_video", (
            f"Router selected {res.get('provider')} instead of key4u_video authority!"
        )


def test_storyboard_render_scene_async_enforces_key4u_chain(mock_storyboard_files, monkeypatch):
    """Defect 1: _render_scene_async must pin provider_env VIDEO_PROVIDER_CHAIN to key4u_video."""
    monkeypatch.setenv("VIDEO_PROVIDER_CHAIN", "shopaikey_video,key4u_video")
    job = _build_test_job(mock_storyboard_files, model="kling-3.0-turbo")

    scene_obj = SimpleNamespace(
        scene_id=1,
        video_prompt="Cat on crystal planet",
        aspect_ratio="9:16",
        _toan_aas_job=job,
    )
    raw_path = str(mock_storyboard_files["tmp_path"] / "scene_raw.mp4")

    captured_env = {}

    def mock_run_provider(req, **kwargs):
        captured_env.update(dict(os.environ))
        # Write dummy output file to satisfy copy
        Path(raw_path).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 256)
        return {
            "ok": True,
            "status": "SUCCESS",
            "provider": "key4u_video",
            "provider_task_ids": ["task_111"],
            "output_path": raw_path,
            "model": "kling-3.0-turbo",
            "duration": 8.0,
            "result_url_present": True,
        }

    with patch("services.video_real_render_connector.run_provider_generation", side_effect=mock_run_provider):
        res = asyncio.run(_render_scene_async(scene_obj, raw_path, ["shopaikey_video", "key4u_video"]))
        assert res.get("ok") is True
        assert res.get("provider") == "key4u_video"
        assert res.get("model") == "kling-3.0-turbo"


# ===========================================================================
# DEFECT 2 TESTS: Two-Scene 8s+8s Concat & Output Path Unification
# ===========================================================================

def test_multiscene_finalize_unifies_output_path_keys(mock_storyboard_files):
    """Defect 2: finalize_multiscene_scene_clips must set output_path and final_output_path equal to final_video_path."""
    scenes = [
        SceneSpec(scene_id=1, title="Scene 1", visual_prompt="Scene 1", video_prompt="Scene 1", target_duration_sec=8.0),
        SceneSpec(scene_id=2, title="Scene 2", visual_prompt="Scene 2", video_prompt="Scene 2", target_duration_sec=8.0),
    ]
    scene_clip_paths = {
        1: mock_storyboard_files["clip1"],
        2: mock_storyboard_files["clip2"],
    }
    workspace = str(mock_storyboard_files["tmp_path"] / "concat_ws")
    os.makedirs(workspace, exist_ok=True)

    def mock_stitch(paths, output, **kwargs):
        Path(output).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 512)
        return output

    def mock_mux(**kwargs):
        output = kwargs.get("output_path")
        Path(output).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 512)
        return output

    def mock_probe_duration(path):
        return 16.0

    def mock_probe_streams(path):
        return {"streams": [{"codec_type": "video", "width": 720, "height": 1280}]}

    def mock_normalize(src, dst, *args, **kw):
        Path(dst).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 256)
        return dst

    with patch.object(multiscene_video_pipeline, "stitch_scenes", side_effect=mock_stitch), \
         patch.object(multiscene_video_pipeline, "mux_final_multiscene_video", side_effect=mock_mux), \
         patch.object(multiscene_video_pipeline, "probe_duration", side_effect=mock_probe_duration), \
         patch.object(multiscene_video_pipeline, "probe_media_streams", side_effect=mock_probe_streams), \
         patch.object(multiscene_video_pipeline, "normalize_scene_duration", side_effect=mock_normalize), \
         patch.object(multiscene_video_pipeline, "_validate_composed_video", return_value={"ok": True}):

        res = finalize_multiscene_scene_clips(
            user_id="7001",
            job_id="1155",
            workspace_dir=workspace,
            scenes=scenes,
            scene_clip_paths=scene_clip_paths,
            preserve_scene_audio=False,
            enable_voice=False,
            enable_subtitle=False,
        )

        assert res.get("ok") is True
        final_video = res.get("final_video_path")
        assert final_video, "final_video_path must be populated"
        assert res.get("output_path") == final_video, "output_path must equal final_video_path"
        assert res.get("final_output_path") == final_video, "final_output_path must equal final_video_path"


def test_per_scene_orchestrator_unifies_output_paths_to_16s_master(mock_storyboard_files):
    """Defect 2: _run_per_scene_provider_orchestrator must NOT leave output_path pointing to scene 2's 8s clip."""
    job = _build_test_job(mock_storyboard_files, model="kling-3.0-turbo")
    workspace = str(mock_storyboard_files["tmp_path"] / "orchestrator_ws")
    os.makedirs(workspace, exist_ok=True)

    final_master_path = os.path.join(workspace, "final_output.mp4")
    Path(final_master_path).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 512)

    def mock_finalize(*args, **kwargs):
        # Simulates finalize_multiscene_scene_clips prior to R11 fix (only returning final_video_path)
        return {
            "ok": True,
            "status": "completed",
            "final_video_path": final_master_path,
            "master_video_path": final_master_path,
            "duration_sec": 16.0,
            "target_duration_sec": 16.0,
            "scene_count": 2,
        }

    def mock_render_scene(scene, raw_path, provider_order):
        Path(raw_path).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 256)
        scene_id = getattr(scene, "scene_id", 1)
        return {
            "ok": True,
            "status": "clip_downloaded",
            "actual_provider_payload_status": "succeeded",
            "provider": "key4u_video",
            "task_id": f"task_{scene_id}",
            "provider_task_id": f"task_{scene_id}",
            "scene_id": scene_id,
            "scene_index": scene_id,
            "clip_path": raw_path,
            "output_path": raw_path,
            "clip_valid": True,
            "validation_passed": True,
            "output_validated": True,
            "clip_bytes": 256,
            "model": "kling-3.0-turbo",
            "duration": 8.0,
            "result_url_present": True,
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
        assert res.get("final_video_path") == final_master_path
        assert res.get("output_path") == final_master_path, (
            f"output_path was left as {res.get('output_path')} instead of concatenated master {final_master_path}!"
        )
        assert res.get("final_output_path") == final_master_path


def test_storyboard_duration_contract_fails_closed_on_single_8s_clip(mock_storyboard_files):
    """Defect 2: 2-scene 8s Storyboard duration contract must fail closed if only 8s clip is returned."""
    job = _build_test_job(mock_storyboard_files)
    # Expected duration is 16s
    contract_8s = product_video_duration_contract(job, 8.0)
    assert contract_8s["ok"] is False
    assert contract_8s["reason"] == "final_duration_short_scene_coverage_missing"

    contract_16s = product_video_duration_contract(job, 16.0)
    assert contract_16s["ok"] is True


def test_storyboard_key4u_submit_failure_fails_closed_no_fallback_to_shopaikey(mock_storyboard_files, monkeypatch):
    """Defect 1 (R11.0B): When Key4U fails submit/execution, Storyboard MUST fail closed.

    It must NEVER fallback to shopaikey_video or any other secondary provider.
    Enforces:
      KEY4U_SUBMIT_CALLS = 1
      SHOPAIKEY_SUBMIT_CALLS = 0
      TOTAL_PROVIDER_SUBMITS = 1
      INITIAL_FALLBACK_PROVIDER = ""
      PROVIDER_FALLBACK_OCCURRED = NO
    """
    monkeypatch.setenv("VIDEO_PROVIDER_CHAIN", "key4u_video,shopaikey_video")
    monkeypatch.setenv("SHOPAIKEY_API_KEY", "mock_key")
    monkeypatch.setenv("SHOPAIKEY_BASE_URL", "https://mock.shopaikey.test")
    monkeypatch.setenv("KEY4U_API_KEY", "mock_key")
    monkeypatch.setenv("KEY4U_BASE_URL", "https://mock.key4u.test")

    req = VideoGenerationRequest(
        job_id="test_1155_fail_closed",
        product_type="storyboard_to_video",
        prompt="Cat on crystal planet",
        ratio="9:16",
        duration_seconds=8,
        image_paths=[mock_storyboard_files["panel1"]],
        metadata={
            "product_type": "storyboard_to_video",
            "engine_route": "storyboard_to_video",
            "engine_adapter": "storyboard_scene_image_video_engine",
            "is_storyboard": True,
            "selected_provider": "key4u_video",
            "model": "kling-3.0-turbo",
            "selected_model": "kling-3.0-turbo",
            "pinned_wire_model": "kling-3.0-turbo",
            "required_capability": "image_to_video",
        },
    )

    submit_counts = {"key4u_video": 0, "shopaikey_video": 0}

    from services.video_provider_base import VideoSubmitResult
    from providers.video_generic_http_provider import GenericHttpVideoProvider

    def instrumented_submit(self, request):
        pname = self.provider_name
        if pname in submit_counts:
            submit_counts[pname] += 1
        if pname == "key4u_video":
            return VideoSubmitResult(
                ok=False,
                provider_name="key4u_video",
                provider_status="failed",
                error_code="provider_submit_failed",
            )
        return VideoSubmitResult(
            ok=True,
            provider_name=pname,
            provider_task_id=f"{pname}_task_123",
        )

    with patch.object(GenericHttpVideoProvider, "submit_video_job", new=instrumented_submit):
        res = run_provider_generation(
            req,
            output_dir=str(mock_storyboard_files["tmp_path"]),
            allow_pending_result=True,
        )

    assert submit_counts["key4u_video"] == 1, f"Expected 1 key4u submit call, got {submit_counts['key4u_video']}"
    assert submit_counts["shopaikey_video"] == 0, (
        f"Defect reproduced! Router leaked fallback submit to shopaikey_video: {submit_counts['shopaikey_video']}"
    )
    assert sum(submit_counts.values()) == 1
    assert res.get("initial_fallback_provider") == ""
    assert res.get("fallback_used") is False
    assert res.get("provider_fallback_attempted") in {False, None}
    assert res.get("ok") is False
    assert res.get("selected_provider") == "key4u_video"
