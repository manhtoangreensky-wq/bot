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
         patch("services.video_real_render_connector.normalize_storyboard_provider_clip", return_value=raw_path), \
         patch("services.video_final_output.probe_video", return_value={"ok": True, "has_video": True, "duration": 8.0, "bytes": 512}):
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

    with patch("services.video_final_output.probe_video", return_value={"ok": True, "has_video": True, "duration": 8.0, "bytes": 256}), \
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
            "output_path": master_path,
            "final_output_path": master_path,
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
# BLOCKER 1 REMEDIATION: Fail-closed normalization & post-probe tests
# ===========================================================================

def test_first_red_a_normalization_failure_fails_closed_no_copy_fallback(mock_storyboard_files):
    """FIRST_RED_A: Normalization failure must raise storyboard_scene_duration_normalization_failed_no_charge.
    
    Must NOT copy original 10s source as fallback.
    Must NOT mark scene SUCCESS.
    Must NOT set metadata duration=8.
    """
    source_10s = str(mock_storyboard_files["tmp_path"] / "source_fail_closed_10s.mp4")
    Path(source_10s).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 512)
    target_8s = str(mock_storyboard_files["tmp_path"] / "target_fail_closed_8s.mp4")

    # 1. Direct call to normalize_storyboard_provider_clip with failing normalization
    def mock_failing_normalizer(src, dst, **kwargs):
        raise RuntimeError("ffmpeg_synthetic_codec_crash")

    with patch("services.video_final_output.probe_video", return_value={"ok": True, "has_video": True, "duration": 10.0, "bytes": 512}), \
         patch("services.video_real_render_connector.normalize_scene_duration", side_effect=mock_failing_normalizer):
        with pytest.raises(video_real_render_connector.RealVideoRenderError) as exc_info:
            normalize_storyboard_provider_clip(source_10s, target_8s, target_seconds=8.0)

        err = exc_info.value
        assert "storyboard_scene_duration_normalization_failed_no_charge" in str(err)
        # CRITICAL: Verify NO source copy fallback occurred!
        assert not os.path.exists(target_8s), "Fallback copy of original 10s clip is strictly forbidden"

    # 2. Scene async execution failure must not mark scene SUCCESS or claim duration=8
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
    raw_path = str(mock_storyboard_files["tmp_path"] / "scene_async_fail.mp4")

    def mock_run_provider(req, **kwargs):
        Path(raw_path).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 512)
        return {
            "ok": True,
            "status": "SUCCESS",
            "provider": "key4u_video",
            "provider_task_ids": ["task_fail_closed_scene"],
            "output_path": raw_path,
            "model": "kling-3.0-turbo",
            "duration": 10.0,
            "result_url_present": True,
        }

    with patch("services.video_real_render_connector.run_provider_generation", side_effect=mock_run_provider), \
         patch("services.video_real_render_connector.normalize_storyboard_provider_clip", side_effect=video_real_render_connector.RealVideoRenderError("storyboard_scene_duration_normalization_failed_no_charge")):
        with pytest.raises(video_real_render_connector.RealVideoRenderError) as exc_info2:
            asyncio.run(_render_scene_async(scene_obj, raw_path, ["key4u_video"]))

        assert "storyboard_scene_duration_normalization_failed_no_charge" in str(exc_info2.value)


def test_first_red_b_post_normalization_artifact_probing_10s_fails_closed(mock_storyboard_files):
    """FIRST_RED_B: If normalizer leaves an artifact that still probes as ~10s, fail closed."""
    source_10s = str(mock_storyboard_files["tmp_path"] / "source_probe_10s.mp4")
    Path(source_10s).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 512)
    target_8s = str(mock_storyboard_files["tmp_path"] / "target_probe_10s.mp4")

    # Normalizer runs but output artifact still probes as 10.0s (out of tolerance)
    def mock_bypass_normalizer(src, dst, **kwargs):
        Path(dst).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 512)
        return dst

    # Source probes 10.0s, and target also probes 10.0s
    with patch("services.video_final_output.probe_video", return_value={"ok": True, "has_video": True, "duration": 10.0, "bytes": 512}), \
         patch("services.video_real_render_connector.normalize_scene_duration", side_effect=mock_bypass_normalizer):
        with pytest.raises(video_real_render_connector.RealVideoRenderError) as exc_info:
            normalize_storyboard_provider_clip(source_10s, target_8s, target_seconds=8.0)

        err = exc_info.value
        assert "storyboard_scene_duration_normalization_failed_no_charge" in str(err)
        assert not os.path.exists(target_8s), "Out-of-tolerance artifact must be cleaned up on failure"


def test_first_red_c_real_media_normalization_ffmpeg_ffprobe(tmp_path):
    """FIRST_RED_C: Generate real 10s MP4 with ffmpeg, normalize to 8s, verify with real ffprobe."""
    import subprocess
    from services.video_final_output import probe_video

    # Check ffmpeg availability
    try:
        ver = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        if ver.returncode != 0:
            pytest.skip("ffmpeg not available in test environment")
    except Exception:
        pytest.skip("ffmpeg executable missing")

    real_10s_src = str(tmp_path / "real_10s_input.mp4")
    real_8s_dst = str(tmp_path / "real_8s_output.mp4")

    # 1. Generate real 10s MP4 test pattern
    gen_cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "testsrc=duration=10:size=720x1280:rate=25",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        real_10s_src,
    ]
    subprocess.run(gen_cmd, check=True, capture_output=True)

    # 2. Probe real input with ffprobe
    input_probe = probe_video(real_10s_src)
    assert input_probe.get("ok") is True
    assert input_probe.get("has_video") is True
    input_duration = float(input_probe.get("duration") or 0.0)
    assert 9.5 <= input_duration <= 10.5, f"Expected input ~10s, got {input_duration}"

    # 3. Call ACTUAL normalization without mocking
    result_path = normalize_storyboard_provider_clip(real_10s_src, real_8s_dst, target_seconds=8.0)
    assert result_path == real_8s_dst
    assert os.path.isfile(real_8s_dst)

    # 4. Probe real output with ffprobe
    output_probe = probe_video(real_8s_dst)
    assert output_probe.get("ok") is True
    assert output_probe.get("has_video") is True
    output_duration = float(output_probe.get("duration") or 0.0)
    assert 7.5 <= output_duration <= 8.5, f"Expected output ~8s, got {output_duration}"


# ===========================================================================
# BLOCKER 2 REMEDIATION: Cost Accounting Authority Tests
# ===========================================================================

def test_first_red_cost_authority_calculates_from_10s_provider_submit():
    """COST_FIRST_RED & PASS_EVIDENCE:
    Prove provider cost authority consumes submit duration 10s (20s total billable)
    while public output remains 8s (16s total) and customer quote is unchanged.
    """
    from services import video_ai_real_pricing

    # Canonical parameters:
    # provider = key4u_video
    # model = kling-3.0-turbo
    # scene_count = 2
    # public_scene_seconds = 8
    # provider_submit_seconds = 10

    cost_info = video_ai_real_pricing.calculate_product_video_provider_cost(
        provider="key4u_video",
        model="kling-3.0-turbo",
        scene_count=2,
        public_scene_seconds=8,
        provider_submit_seconds=10,
    )

    # Required metrics
    assert cost_info["provider_cost_authority_function"] == "services.video_ai_real_pricing.check_product_video_economics"
    assert cost_info["public_scene_seconds"] == 8
    assert cost_info["public_output_seconds_total"] == 16
    assert cost_info["provider_billable_submit_seconds"] == 10
    assert cost_info["provider_billable_seconds_total"] == 20

    # Numeric assertions:
    # Key4U Kling rate = 1.53001224 USD/s
    # 20 billable seconds * 1.53001224 = 30.6002448 USD
    expected_cost_usd = 30.6002448
    assert abs(cost_info["expected_provider_cost_usd"] - expected_cost_usd) < 1e-6
    assert abs(cost_info["computed_provider_cost_usd"] - expected_cost_usd) < 1e-6
    assert cost_info["requested_cost_model"] == "kling-3.0-turbo"
    assert cost_info["resolved_pricing_model"] == "kling-video"
    assert cost_info["model_cost_alias_authority"] == "EXPLICIT"
    assert cost_info["generic_kling_substring_match"] is False
    assert cost_info["unknown_model_economics_fail_closed"] is True

    # Verify check_product_video_economics directly
    econ = video_ai_real_pricing.check_product_video_economics(
        tier_id=400,
        scene_count=2,
        provider="key4u_video",
        model="kling-3.0-turbo",
        customer_quote_xu=668,
        provider_submit_seconds=10,
    )
    assert econ["provider_billable_seconds_total"] == 20
    assert econ["public_output_seconds_total"] == 16
    assert abs(econ["computed_provider_cost_usd"] - expected_cost_usd) < 1e-6
    assert abs(econ["expected_provider_cost_usd"] - expected_cost_usd) < 1e-6
    assert econ["requested_cost_model"] == "kling-3.0-turbo"
    assert econ["resolved_pricing_model"] == "kling-video"
    assert econ["model_cost_alias_authority"] == "EXPLICIT"
    assert econ["generic_kling_substring_match"] is False
    assert econ["unknown_model_economics_fail_closed"] is True
    # Verify customer wallet price is untouched (668 Xu)
    assert econ["customer_quote_xu"] == 668
    assert econ["customer_revenue_vnd"] == 66800


def test_unknown_kling_like_models_fail_closed_in_economics():
    """Requirement 2: Generic substring matching 'kling' in model_name removed.
    Unknown Kling-like models fail closed and do not inherit another Kling rate.
    """
    from services import video_ai_real_pricing

    for unknown_model in ["kling-unknown-variant", "kling-9.9", "kling-experimental-v4"]:
        econ = video_ai_real_pricing.check_product_video_economics(
            tier_id=400,
            scene_count=2,
            provider="key4u_video",
            model=unknown_model,
            customer_quote_xu=668,
            provider_submit_seconds=10,
        )
        assert econ["economics_safe"] is False
        assert econ["block_reason"] == "PRODUCT_VIDEO_PROVIDER_ECONOMICS_UNSAFE"
        assert econ["requested_cost_model"] == unknown_model
        assert econ["resolved_pricing_model"] == ""
        assert econ["model_cost_alias_authority"] == "EXPLICIT"
        assert econ["generic_kling_substring_match"] is False
        assert econ["unknown_model_economics_fail_closed"] is True
        assert econ["provider_total_cost_usd"] == 0.0


def test_production_router_economics_call_delivers_10s_provider_submit(mock_storyboard_files, monkeypatch):
    """Requirement 3: Test the ACTUAL production router economics call.
    Capture the arguments delivered by the real router and require:
    provider=key4u_video, model=kling-3.0-turbo, provider_submit_seconds=10.
    """
    from services import video_provider_router, video_ai_real_pricing
    from services.video_provider_base import VideoSubmitResult
    from providers.video_generic_http_provider import GenericHttpVideoProvider

    captured_router_calls = []
    real_econ_fn = video_ai_real_pricing.check_product_video_economics

    def spy_econ_check(*args, **kwargs):
        res = real_econ_fn(*args, **kwargs)
        captured_router_calls.append({"args": args, "kwargs": dict(kwargs), "result": res})
        return res

    req = VideoGenerationRequest(
        job_id="job_prod_econ_call_test",
        product_type="storyboard_to_video",
        prompt="Scene 1 test prompt",
        ratio="9:16",
        duration_seconds=10.0,
        metadata={
            "product_type": "storyboard_to_video",
            "is_storyboard": True,
            "product_video": True,
            "selected_provider": "key4u_video",
            "model": "kling-3.0-turbo",
            "storyboard_model": "kling-3.0-turbo",
            "selected_model": "kling-3.0-turbo",
            "pinned_wire_model": "kling-3.0-turbo",
            "tier_id": 400,
            "scene_count": 2,
            "customer_quote_xu": 668,
            "provider_billable_submit_seconds": 10,
            "provider_submit_duration_seconds": 10,
        },
    )

    with patch.object(video_ai_real_pricing, "check_product_video_economics", side_effect=spy_econ_check):
        with patch.object(GenericHttpVideoProvider, "submit_video_job") as mock_submit:
            mock_submit.return_value = VideoSubmitResult(
                ok=True,
                provider_name="key4u_video",
                provider_task_id="k4u_test_task_123",
                provider_status="queued",
            )
            res = video_provider_router.run_provider_generation(
                req,
                output_dir=str(mock_storyboard_files["tmp_path"]),
                allow_pending_result=True,
                environ={
                    "KEY4U_API_KEY": "mock_key",
                    "KEY4U_BASE_URL": "https://mock.key4u.test",
                    "KEY4U_VIDEO_MODEL": "kling-3.0-turbo",
                },
            )

    assert len(captured_router_calls) >= 1, "Real router must execute check_product_video_economics"
    router_call = captured_router_calls[0]
    call_kwargs = router_call["kwargs"]
    call_result = router_call["result"]

    assert call_kwargs.get("provider") == "key4u_video"
    assert call_kwargs.get("model") == "kling-3.0-turbo"
    assert call_kwargs.get("provider_submit_seconds") == 10
    assert call_kwargs.get("tier_id") == 400
    assert call_kwargs.get("scene_count") == 2

    assert call_result["public_output_seconds_total"] == 16
    assert call_result["provider_billable_seconds_total"] == 20
    expected_cost_usd = 30.6002448
    assert abs(call_result["expected_provider_cost_usd"] - expected_cost_usd) < 1e-6
    assert abs(call_result["computed_provider_cost_usd"] - expected_cost_usd) < 1e-6
    assert call_result["requested_cost_model"] == "kling-3.0-turbo"
    assert call_result["resolved_pricing_model"] == "kling-video"
    assert call_result["model_cost_alias_authority"] == "EXPLICIT"
    assert call_result["generic_kling_substring_match"] is False
    assert call_result["unknown_model_economics_fail_closed"] is True


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
         patch("services.video_real_render_connector.normalize_storyboard_provider_clip", return_value=raw_path), \
         patch("services.video_final_output.probe_video", return_value={"ok": True, "has_video": True, "duration": 8.0, "bytes": 512}):
        asyncio.run(_render_scene_async(scene_obj, raw_path, ["key4u_video"]))

    assert len(captured_requests) == 1
    req = captured_requests[0]
    meta = req.metadata
    assert meta.get("provider_billable_submit_seconds") == 10
    # Customer price remains unchanged
    assert meta.get("public_scene_target_seconds") == 8

