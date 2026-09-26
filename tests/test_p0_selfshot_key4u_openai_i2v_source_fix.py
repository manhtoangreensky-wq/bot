"""Provider-free tests for SelfShot Key4U OpenAI I2V Source Fix (grok-imagine-video).

Program: P0.PRODUCT_VIDEO
Tracking Issue: #1155
Model: grok-imagine-video (family: xai_grok, capability: image_to_video)
Provider: key4u_video

Invariants:
1. SS2 grok model survives connector
2. SS3 grok model survives connector
3. submit endpoint == /v1/videos
4. poll endpoint == /v1/video/query?id={task_id}
5. multipart input_reference contains actual image bytes
6. raw /tmp path not serialized as provider field
7. missing image fails closed before HTTP
8. unknown/non-I2V model fails closed
9. Kling-v3 existing route unchanged
10. ambiguous submit never produces second submit
11. no hidden model fallback
12. model identity remains grok-imagine-video end-to-end
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from services import (
    video_ai_edit_provider,
    video_provider_catalog as vpc,
    video_real_render_connector as vrrc,
)
from providers import video_generic_http_provider as vgp
from services.video_provider_base import VideoGenerationRequest
from services.video_real_render_connector import RealVideoRenderError


# ---------------------------------------------------------------------------
# Helpers & Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_keyframe(tmp_path: Path) -> Path:
    img = tmp_path / "test_keyframe.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRfake_png_data_bytes_1234567890")
    return img


# ---------------------------------------------------------------------------
# 1. SS2 grok model survives connector
# ---------------------------------------------------------------------------

def test_1_ss2_grok_model_survives_connector(fake_keyframe: Path, tmp_path: Path):
    """SelfShot2 honors selected_model=grok-imagine-video without overriding to kling-v3."""
    captured_req = None

    def mock_run_gen(req: VideoGenerationRequest, **kwargs):
        nonlocal captured_req
        captured_req = req
        return {"ok": True, "task_id": "test_ss2_task", "status": "completed", "result_url": "http://fake/video.mp4"}

    job = {"id": "test-ss2-job", "selected_model": "grok-imagine-video"}
    asset_pack = {"selected_model": "grok-imagine-video"}
    segment = {"start_seconds": 0.0, "duration_seconds": 5.0}

    with patch.object(vrrc, "_extract_selfshot_keyframe", return_value=str(fake_keyframe)), \
         patch.object(vrrc, "_materialize_selfshot2_source_segment", return_value=str(fake_keyframe)), \
         patch.object(vrrc, "run_provider_generation", side_effect=mock_run_gen):
        vrrc._render_selfshot2_controlled_keyframe_image_to_video(
            job=job,
            asset_pack=asset_pack,
            raw_path=str(tmp_path / "raw.mp4"),
            scene_index=0,
            segment=segment,
            provider_order=["key4u_video"],
            fallback_prompt="a cinematic scene",
            aspect_ratio="9:16",
            target_duration=5,
            source_path=str(tmp_path / "source.mp4"),
        )

    assert captured_req is not None
    assert captured_req.metadata.get("selected_model") == "grok-imagine-video"
    assert captured_req.metadata.get("model_name") == "grok-imagine-video"
    assert captured_req.metadata.get("model") == "grok-imagine-video"
    assert captured_req.metadata.get("selected_family") == "xai_grok"


# ---------------------------------------------------------------------------
# 2. SS3 grok model survives connector
# ---------------------------------------------------------------------------

def test_2_ss3_grok_model_survives_connector(fake_keyframe: Path, tmp_path: Path):
    """SelfShot3 honors selected_model=grok-imagine-video without overriding to kling-v3."""
    captured_req = None

    def mock_run_gen(req: VideoGenerationRequest, **kwargs):
        nonlocal captured_req
        captured_req = req
        return {"ok": True, "task_id": "test_ss3_task", "status": "completed", "result_url": "http://fake/video.mp4"}

    job = {"id": "test-ss3-job", "selected_model": "grok-imagine-video"}
    asset_pack = {"source_segment": {"start_ms": 0}, "selected_model": "grok-imagine-video"}

    with patch.object(vrrc, "_extract_selfshot_keyframe", return_value=str(fake_keyframe)), \
         patch.object(vrrc, "run_provider_generation", side_effect=mock_run_gen):
        vrrc._render_selfshot3_controlled_keyframe_image_to_video(
            job=job,
            asset_pack=asset_pack,
            raw_path=str(tmp_path / "raw.mp4"),
            provider_order=["key4u_video"],
            fallback_prompt="a cinematic scene",
            aspect_ratio="9:16",
            source_path=str(tmp_path / "source.mp4"),
            duration_seconds=5,
        )

    assert captured_req is not None
    assert captured_req.metadata.get("selected_model") == "grok-imagine-video"
    assert captured_req.metadata.get("model_name") == "grok-imagine-video"
    assert captured_req.metadata.get("model") == "grok-imagine-video"
    assert captured_req.metadata.get("selected_family") == "xai_grok"


# ---------------------------------------------------------------------------
# 3. submit endpoint == /v1/videos
# ---------------------------------------------------------------------------

def test_3_grok_i2v_submit_endpoint_is_v1_videos():
    """model_interface_contract resolves submit_url ending in /v1/videos for grok-imagine-video I2V."""
    contract = vpc.model_interface_contract(
        "key4u_video",
        "grok-imagine-video",
        capability="image_to_video",
        env={"KEY4U_BASE_URL": "https://api.key4u.vn"},
    )
    assert contract.get("contract_validation_status") == "ok"
    assert contract.get("provider_interface") == "key4u_openai_video_multipart_i2v"
    submit_url = contract.get("submit_url") or contract.get("provider_submit_url_override")
    assert submit_url is not None
    assert submit_url.endswith("/v1/videos")
    assert "/v1/video/create" not in submit_url


# ---------------------------------------------------------------------------
# 4. poll endpoint == /v1/video/query?id={task_id}
# ---------------------------------------------------------------------------

def test_4_grok_i2v_poll_endpoint_is_v1_video_query():
    """model_interface_contract resolves poll_url ending in /v1/video/query?id={task_id}."""
    contract = vpc.model_interface_contract(
        "key4u_video",
        "grok-imagine-video",
        capability="image_to_video",
        env={"KEY4U_BASE_URL": "https://api.key4u.vn"},
    )
    assert contract.get("contract_validation_status") == "ok"
    poll_url = contract.get("poll_url") or contract.get("provider_poll_url_override")
    assert poll_url is not None
    assert "/v1/video/query?id={task_id}" in poll_url


# ---------------------------------------------------------------------------
# 5. multipart input_reference contains actual image bytes
# ---------------------------------------------------------------------------

def test_5_multipart_input_reference_contains_actual_image_bytes(fake_keyframe: Path):
    """Wire payload or multipart fields format input_reference with actual file bytes, filename, and mime."""
    req = VideoGenerationRequest(
        job_id="test-wire-grok",
        product_type="self_shot_cinematic_transform",
        prompt="transform scene",
        image_paths=[str(fake_keyframe)],
        required_capability="image_to_video",
        metadata={
            "selected_model": "grok-imagine-video",
            "selected_family": "xai_grok",
            "pinned_wire_model": "grok-imagine-video",
        },
    )
    env = {"KEY4U_BASE_URL": "https://api.key4u.vn"}
    payload = vgp.build_key4u_video_payload(req, env=env)
    wire = vgp._key4u_wire_payload(payload, submit_url="https://api.key4u.vn/v1/videos")

    assert "input_reference" in wire
    field = wire["input_reference"]
    assert isinstance(field, tuple)
    assert len(field) == 3
    filename, file_bytes, mime = field
    assert filename == fake_keyframe.name
    assert file_bytes == fake_keyframe.read_bytes()
    assert len(file_bytes) > 0
    assert mime in {"image/png", "image/jpeg"}


# ---------------------------------------------------------------------------
# 6. raw /tmp path not serialized as provider field
# ---------------------------------------------------------------------------

def test_6_raw_local_path_not_serialized_as_provider_wire_field(fake_keyframe: Path):
    """Local filepath string is NOT sent as a provider wire field."""
    req = VideoGenerationRequest(
        job_id="test-no-raw-path",
        product_type="self_shot_cinematic_transform",
        prompt="transform scene",
        image_paths=[str(fake_keyframe)],
        required_capability="image_to_video",
        metadata={
            "selected_model": "grok-imagine-video",
            "selected_family": "xai_grok",
            "pinned_wire_model": "grok-imagine-video",
        },
    )
    env = {"KEY4U_BASE_URL": "https://api.key4u.vn"}
    payload = vgp.build_key4u_video_payload(req, env=env)
    wire = vgp._key4u_wire_payload(payload, submit_url="https://api.key4u.vn/v1/videos")

    # Values that are strings must not contain the local keyframe path
    for k, v in wire.items():
        if isinstance(v, str):
            assert str(fake_keyframe) not in v, f"Found local path in field {k}: {v}"
    # Specifically, input_reference is not a string
    assert not isinstance(wire.get("input_reference"), str)


# ---------------------------------------------------------------------------
# 7. missing image fails closed before HTTP
# ---------------------------------------------------------------------------

def test_7_missing_image_fails_closed_before_http(tmp_path: Path):
    """Missing keyframe image causes payload build / submit to fail closed with zero HTTP calls."""
    missing_file = tmp_path / "does_not_exist.png"
    req = VideoGenerationRequest(
        job_id="test-missing-img",
        product_type="self_shot_cinematic_transform",
        prompt="transform scene",
        image_paths=[str(missing_file)],
        required_capability="image_to_video",
        metadata={
            "selected_model": "grok-imagine-video",
            "selected_family": "xai_grok",
        },
    )
    env = {
        "KEY4U_BASE_URL": "https://api.key4u.vn",
        "KEY4U_API_KEY": "fake_key",
        "KEY4U_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_SUBMIT_URL": "https://api.key4u.vn/v1/videos",
        "KEY4U_VIDEO_POLL_URL": "https://api.key4u.vn/v1/video/query?id={task_id}",
        "KEY4U_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer fake_key",
        "KEY4U_VIDEO_MODEL": "grok-imagine-video",
    }
    provider = vgp.GenericHttpVideoProvider(
        provider_name="key4u_video",
        environ=env,
        enabled_env="KEY4U_VIDEO_ENABLED",
        submit_url_env="KEY4U_VIDEO_SUBMIT_URL",
        poll_url_env="KEY4U_VIDEO_POLL_URL",
        auth_header_name_env="KEY4U_VIDEO_AUTH_HEADER_NAME",
        auth_header_value_env="KEY4U_VIDEO_AUTH_HEADER_VALUE",
        model_env="KEY4U_VIDEO_MODEL",
    )
    with patch("urllib.request.urlopen") as mock_urlopen:
        result = provider.submit_video_job(req)
        assert result.ok is False
        assert result.error_code in {"provider_image_input_missing_or_invalid", "key4u_openai_i2v_image_missing_no_charge"}
        mock_urlopen.assert_not_called()


# ---------------------------------------------------------------------------
# 8. unknown/non-I2V model fails closed
# ---------------------------------------------------------------------------

def test_8_unknown_or_non_i2v_model_fails_closed(fake_keyframe: Path, tmp_path: Path):
    """Explicitly providing an unknown or non-I2V model fails closed without falling back to Kling."""
    job = {"id": "test-unknown-model", "selected_model": "completely-unknown-model"}
    asset_pack = {"source_segment": {"start_ms": 0}, "selected_model": "completely-unknown-model"}

    with patch.object(vrrc, "_extract_selfshot_keyframe", return_value=str(fake_keyframe)):
        with pytest.raises(RealVideoRenderError) as exc_info:
            vrrc._render_selfshot3_controlled_keyframe_image_to_video(
                job=job,
                asset_pack=asset_pack,
                raw_path=str(tmp_path / "raw.mp4"),
                provider_order=["key4u_video"],
                fallback_prompt="prompt",
                aspect_ratio="9:16",
                source_path=str(tmp_path / "source.mp4"),
                duration_seconds=5,
            )
        assert "selfshot_i2v_model_not_proven_no_charge" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 9. Kling-v3 existing route unchanged
# ---------------------------------------------------------------------------

def test_9_kling_v3_existing_route_unchanged(fake_keyframe: Path, tmp_path: Path):
    """When no alternate model is selected, Kling-v3 remains the safe default route."""
    captured_req = None

    def mock_run_gen(req: VideoGenerationRequest, **kwargs):
        nonlocal captured_req
        captured_req = req
        return {"ok": True, "task_id": "test_kling_task", "status": "completed", "result_url": "http://fake/video.mp4"}

    job = {"id": "test-kling-default"}
    asset_pack = {"source_segment": {"start_ms": 0}}

    with patch.object(vrrc, "_extract_selfshot_keyframe", return_value=str(fake_keyframe)), \
         patch.object(vrrc, "run_provider_generation", side_effect=mock_run_gen):
        vrrc._render_selfshot3_controlled_keyframe_image_to_video(
            job=job,
            asset_pack=asset_pack,
            raw_path=str(tmp_path / "raw.mp4"),
            provider_order=["key4u_video"],
            fallback_prompt="prompt",
            aspect_ratio="9:16",
            source_path=str(tmp_path / "source.mp4"),
            duration_seconds=5,
        )

    assert captured_req is not None
    assert captured_req.metadata.get("selected_model") == "kling-v3"
    assert captured_req.metadata.get("model_name") == "kling-v3"
    assert captured_req.metadata.get("selected_family") == "kling"


# ---------------------------------------------------------------------------
# 10. ambiguous submit never produces second submit
# ---------------------------------------------------------------------------

def test_10_ambiguous_submit_never_produces_second_submit(fake_keyframe: Path):
    """HTTP timeout during submit marks ambiguous submit and does not execute a second submit."""
    req = VideoGenerationRequest(
        job_id="test-timeout-ambiguous",
        product_type="self_shot_cinematic_transform",
        prompt="transform scene",
        image_paths=[str(fake_keyframe)],
        required_capability="image_to_video",
        metadata={
            "selected_model": "grok-imagine-video",
            "selected_family": "xai_grok",
            "pinned_wire_model": "grok-imagine-video",
        },
    )
    env = {
        "KEY4U_BASE_URL": "https://api.key4u.vn",
        "KEY4U_API_KEY": "fake_key",
        "KEY4U_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_SUBMIT_URL": "https://api.key4u.vn/v1/videos",
        "KEY4U_VIDEO_POLL_URL": "https://api.key4u.vn/v1/video/query?id={task_id}",
        "KEY4U_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer fake_key",
        "KEY4U_VIDEO_MODEL": "grok-imagine-video",
    }
    provider = vgp.GenericHttpVideoProvider(
        provider_name="key4u_video",
        environ=env,
        enabled_env="KEY4U_VIDEO_ENABLED",
        submit_url_env="KEY4U_VIDEO_SUBMIT_URL",
        poll_url_env="KEY4U_VIDEO_POLL_URL",
        auth_header_name_env="KEY4U_VIDEO_AUTH_HEADER_NAME",
        auth_header_value_env="KEY4U_VIDEO_AUTH_HEADER_VALUE",
        model_env="KEY4U_VIDEO_MODEL",
    )
    call_count = 0

    def mock_urlopen(request, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise TimeoutError("connection timed out after sending request")

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        result = provider.submit_video_job(req)
        assert result.ok is False
        assert call_count == 1
        assert (result.raw or {}).get("ambiguous_submit") is True or "timeout" in (result.error_code or "")


# ---------------------------------------------------------------------------
# 11. no hidden model fallback
# ---------------------------------------------------------------------------

def test_11_no_hidden_model_fallback(fake_keyframe: Path, tmp_path: Path):
    """If grok-imagine-video submit fails, system does NOT silently switch to kling-v3."""
    def mock_run_gen(req: VideoGenerationRequest, **kwargs):
        # Simulated failure for grok
        return {
            "ok": False,
            "provider_error": "key4u_grok_submit_failed",
            "blocker": "key4u_grok_submit_failed",
        }

    job = {"id": "test-no-hidden-fallback", "selected_model": "grok-imagine-video"}
    asset_pack = {"source_segment": {"start_ms": 0}, "selected_model": "grok-imagine-video"}

    with patch.object(vrrc, "_extract_selfshot_keyframe", return_value=str(fake_keyframe)), \
         patch.object(vrrc, "run_provider_generation", side_effect=mock_run_gen):
        with pytest.raises(RealVideoRenderError) as exc_info:
            vrrc._render_selfshot3_controlled_keyframe_image_to_video(
                job=job,
                asset_pack=asset_pack,
                raw_path=str(tmp_path / "raw.mp4"),
                provider_order=["key4u_video"],
                fallback_prompt="prompt",
                aspect_ratio="9:16",
                source_path=str(tmp_path / "source.mp4"),
                duration_seconds=5,
            )
        assert "key4u_grok_submit_failed" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 12. model identity remains grok-imagine-video end-to-end
# ---------------------------------------------------------------------------

def test_12_model_identity_remains_grok_end_to_end(fake_keyframe: Path, tmp_path: Path):
    """Model identity remains grok-imagine-video from connector down to multipart request."""
    captured_multipart: dict = {}

    def mock_open_multipart(url: str, fields: dict, **kwargs):
        nonlocal captured_multipart
        captured_multipart = dict(fields)
        return {"ok": True, "status_code": 200, "body": {"id": "task_grok_123"}}

    job = {"id": "test-e2e-grok", "selected_model": "grok-imagine-video"}
    asset_pack = {"source_segment": {"start_ms": 0}, "selected_model": "grok-imagine-video"}

    downloaded_mp4 = tmp_path / "downloaded_ss3.mp4"
    downloaded_mp4.write_bytes(b"FAKE_MP4_BYTES")
    mock_artifact = vgp.VideoArtifactResult(
        ok=True,
        local_path=str(downloaded_mp4),
        bytes=len(b"FAKE_MP4_BYTES"),
        duration=5.0,
        has_video_stream=True,
    )

    mock_continuity = {
        "ok": True,
        "blocker": "",
        "evidence_source": "local_vision_validator",
        "independent_visual_validation": "LOCAL_MODEL",
        "person_required": False,
        "object_required": False,
        "relationship_required": False,
    }

    with patch.object(vrrc, "_extract_selfshot_keyframe", return_value=str(fake_keyframe)), \
         patch.object(vgp.GenericHttpVideoProvider, "_open_multipart_form", side_effect=mock_open_multipart), \
         patch.object(vgp.GenericHttpVideoProvider, "poll_video_job", return_value=vgp.VideoPollResult(
             ok=True,
             provider_name="key4u_video",
             provider_task_id="task_grok_123",
             status="completed",
             result_url="https://fake.key4u.local/output.mp4",
         )), \
         patch("providers.video_generic_http_provider.materialize_video_url", return_value=mock_artifact), \
         patch("services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity", return_value=mock_continuity):
        env = {
            "KEY4U_BASE_URL": "https://api.key4u.vn",
            "KEY4U_API_KEY": "fake_key",
        }
        with patch.dict(os.environ, env):
            vrrc._render_selfshot3_controlled_keyframe_image_to_video(
                job=job,
                asset_pack=asset_pack,
                raw_path=str(tmp_path / "raw.mp4"),
                provider_order=["key4u_video"],
                fallback_prompt="prompt",
                aspect_ratio="9:16",
                source_path=str(tmp_path / "source.mp4"),
                duration_seconds=5,
            )

    assert captured_multipart.get("model") == "grok-imagine-video"
    assert captured_multipart.get("watermark") == "false"
    assert "input_reference" in captured_multipart
    assert isinstance(captured_multipart["input_reference"], tuple)


# ---------------------------------------------------------------------------
# 13. Unproven SelfShot I2V models rejected fail-closed
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("unproven_model", [
    "veo_3_1-fast",
    "MiniMax-Hailuo-02",
    "MiniMax-Hailuo-2.3",
    "pixverse-video",
    "completely-unknown-model",
    "t2v-only-unsupported-model",
])
def test_13_unproven_models_rejected_fail_closed(unproven_model: str, fake_keyframe: Path, tmp_path: Path):
    """Explicitly providing any unproven model fails closed with selfshot_i2v_model_not_proven_no_charge."""
    job = {"id": f"test-{unproven_model}", "selected_model": unproven_model}
    asset_pack = {"source_segment": {"start_ms": 0}, "selected_model": unproven_model}

    with patch.object(vrrc, "_extract_selfshot_keyframe", return_value=str(fake_keyframe)):
        with pytest.raises(RealVideoRenderError) as exc_info:
            vrrc._render_selfshot3_controlled_keyframe_image_to_video(
                job=job,
                asset_pack=asset_pack,
                raw_path=str(tmp_path / "raw.mp4"),
                provider_order=["key4u_video"],
                fallback_prompt="prompt",
                aspect_ratio="9:16",
                source_path=str(tmp_path / "source.mp4"),
                duration_seconds=5,
            )
        assert "selfshot_i2v_model_not_proven_no_charge" in str(exc_info.value)


def test_14_rejected_explicit_model_produces_zero_provider_submit(fake_keyframe: Path, tmp_path: Path):
    """When an unproven model is supplied, run_provider_generation is never called (zero submit)."""
    job = {"id": "test-zero-submit", "selected_model": "veo_3_1-fast"}
    asset_pack = {"source_segment": {"start_ms": 0}, "selected_model": "veo_3_1-fast"}

    mock_run_gen = MagicMock()
    with patch.object(vrrc, "_extract_selfshot_keyframe", return_value=str(fake_keyframe)), \
         patch.object(vrrc, "run_provider_generation", mock_run_gen):
        with pytest.raises(RealVideoRenderError) as exc_info:
            vrrc._render_selfshot3_controlled_keyframe_image_to_video(
                job=job,
                asset_pack=asset_pack,
                raw_path=str(tmp_path / "raw.mp4"),
                provider_order=["key4u_video"],
                fallback_prompt="prompt",
                aspect_ratio="9:16",
                source_path=str(tmp_path / "source.mp4"),
                duration_seconds=5,
            )
        assert "selfshot_i2v_model_not_proven_no_charge" in str(exc_info.value)
        mock_run_gen.assert_not_called()


def test_15_rejected_explicit_model_does_not_silently_fallback_to_kling(fake_keyframe: Path, tmp_path: Path):
    """Supplying an unsupported model does not silently fall back to Kling-v3."""
    job = {"id": "test-no-kling-fallback", "selected_model": "pixverse-video"}
    asset_pack = {"source_segment": {"start_ms": 0}, "selected_model": "pixverse-video"}

    mock_run_gen = MagicMock()
    with patch.object(vrrc, "_extract_selfshot_keyframe", return_value=str(fake_keyframe)), \
         patch.object(vrrc, "run_provider_generation", mock_run_gen):
        with pytest.raises(RealVideoRenderError) as exc_info:
            vrrc._render_selfshot3_controlled_keyframe_image_to_video(
                job=job,
                asset_pack=asset_pack,
                raw_path=str(tmp_path / "raw.mp4"),
                provider_order=["key4u_video"],
                fallback_prompt="prompt",
                aspect_ratio="9:16",
                source_path=str(tmp_path / "source.mp4"),
                duration_seconds=5,
            )
        assert "selfshot_i2v_model_not_proven_no_charge" in str(exc_info.value)
        mock_run_gen.assert_not_called()


def test_16_selfshot2_rejects_unproven_model_fail_closed(fake_keyframe: Path, tmp_path: Path):
    """SelfShot2 also fails closed with selfshot_i2v_model_not_proven_no_charge for unproven models."""
    job = {"id": "test-ss2-unproven", "selected_model": "veo_3_1-fast"}
    asset_pack = {"selected_model": "veo_3_1-fast"}
    segment = {"start_seconds": 0.0, "duration_seconds": 5.0}

    mock_run_gen = MagicMock()
    with patch.object(vrrc, "_extract_selfshot_keyframe", return_value=str(fake_keyframe)), \
         patch.object(vrrc, "_materialize_selfshot2_source_segment", return_value=str(fake_keyframe)), \
         patch.object(vrrc, "run_provider_generation", mock_run_gen):
        with pytest.raises(RealVideoRenderError) as exc_info:
            vrrc._render_selfshot2_controlled_keyframe_image_to_video(
                job=job,
                asset_pack=asset_pack,
                raw_path=str(tmp_path / "raw.mp4"),
                scene_index=0,
                segment=segment,
                provider_order=["key4u_video"],
                fallback_prompt="a cinematic scene",
                aspect_ratio="9:16",
                target_duration=5,
                source_path=str(tmp_path / "source.mp4"),
            )
        assert "selfshot_i2v_model_not_proven_no_charge" in str(exc_info.value)
        mock_run_gen.assert_not_called()


def test_17_proven_model_allowlist_accepts_kling_and_grok():
    """_resolve_selfshot_i2v_model accepts exactly kling-v3 and grok-imagine-video."""
    env = {
        "KEY4U_BASE_URL": "https://api.key4u.vn",
        "KEY4U_API_KEY": "fake_key",
        "KEY4U_KLING_I2V_SUBMIT_URL": "https://api.key4u.vn/kling/v1/videos/image2video",
    }
    model_kling, fam_kling = vrrc._resolve_selfshot_i2v_model(
        {"selected_model": "kling-v3"}, {}, env
    )
    assert model_kling == "kling-v3"
    assert fam_kling == "kling"

    model_grok, fam_grok = vrrc._resolve_selfshot_i2v_model(
        {"selected_model": "grok-imagine-video"}, {}, env
    )
    assert model_grok == "grok-imagine-video"
    assert fam_grok == "xai_grok"
