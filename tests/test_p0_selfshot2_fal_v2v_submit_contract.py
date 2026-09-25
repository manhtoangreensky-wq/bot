"""Provider-free tests for SelfShot2 Fal.ai Wan 2.2 V2V Submit Contract & Adapter.

Scope: P0.PRODUCT_VIDEO
Selected Provider: fal.ai
Selected Model: fal-ai/wan/v2.2-a14b/video-to-video
Zero external provider calls made. All network I/O isolated via mocks.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from services import video_ai_edit_provider
from services import video_real_render_connector
from services.video_real_render_connector import RealVideoRenderError


# ---------------------------------------------------------------------------
# 1. Model Catalog Contract for Fal Wan 2.2 V2V
# ---------------------------------------------------------------------------

def test_1_fal_model_contract_registered_in_catalog():
    """Fal Wan 2.2 V2V model must be recognized in the catalog with video_to_video capability."""
    contract = video_ai_edit_provider.model_contract("fal_video", "fal-ai/wan/v2.2-a14b/video-to-video")
    assert contract["known"] is True
    assert contract["video_to_video"] is True
    assert "video_to_video" in contract["capabilities"]
    assert contract["payload_adapter"] == "fal_wan_v2v"

    # Alias fal.ai and fal must resolve identically
    contract_alias = video_ai_edit_provider.model_contract("fal.ai", "fal-ai/wan/v2.2-a14b/video-to-video")
    assert contract_alias["known"] is True
    assert contract_alias["video_to_video"] is True


# ---------------------------------------------------------------------------
# 2. Endpoint Capability Classification
# ---------------------------------------------------------------------------

def test_2_fal_endpoint_classification_recognizes_video_to_video():
    """Fal submit endpoint must classify as video_to_video."""
    url = "https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video"
    cap = video_ai_edit_provider.classify_endpoint_capability(url)
    assert cap == "video_to_video"


# ---------------------------------------------------------------------------
# 3. Proven V2V Wire Contract Authority
# ---------------------------------------------------------------------------

def test_3_has_proven_v2v_wire_contract_for_fal():
    """has_proven_v2v_wire_contract must return True for fal_video / fal.ai with Wan 2.2 V2V model."""
    assert video_ai_edit_provider.has_proven_v2v_wire_contract("fal_video", "fal-ai/wan/v2.2-a14b/video-to-video")
    assert video_ai_edit_provider.has_proven_v2v_wire_contract("fal.ai", "fal-ai/wan/v2.2-a14b/video-to-video")
    assert video_ai_edit_provider.has_proven_v2v_wire_contract("fal", "fal-ai/wan/v2.2-a14b/video-to-video")

    # Key4U must remain False (strict baseline preservation)
    assert not video_ai_edit_provider.has_proven_v2v_wire_contract("key4u_video", "kling-video")


# ---------------------------------------------------------------------------
# 4. Provider Config From Env & Validation
# ---------------------------------------------------------------------------

def test_4_fal_provider_config_from_env_and_validation():
    """Fal provider config loaded from environment must pass validation."""
    env = {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "test_fal_api_key_12345",
    }
    cfg = video_ai_edit_provider.provider_config_from_env("fal_video", env)
    assert cfg.enabled is True
    assert cfg.provider_name == "fal_video"
    assert cfg.model == "fal-ai/wan/v2.2-a14b/video-to-video"
    assert cfg.interface == "video_to_video_json"
    assert cfg.auth_header_value == "Key test_fal_api_key_12345"
    assert "https://queue.fal.run" in cfg.submit_url
    assert "{task_id}" in cfg.poll_url

    val = video_ai_edit_provider.validate_provider_config(cfg, required_capability="video_to_video")
    assert val["ok"] is True
    assert val["reason"] == ""


# ---------------------------------------------------------------------------
# 5. Local Video Transport Fails Closed Without Remote URL (Zero Assumption)
# ---------------------------------------------------------------------------

def test_5_fal_local_video_transport_fails_closed_without_remote_url(tmp_path: Path):
    """Local video file fails closed before HTTP because data URI is unproven in official contract."""
    sample_video = tmp_path / "scene_source.mp4"
    sample_video.write_bytes(b"FAKE_MP4_BYTES_FOR_FAL_SUBMIT")

    cfg = video_ai_edit_provider.provider_config_from_env("fal_video", {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_secret_key",
    })

    mock_transport = MagicMock()
    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc:
        video_ai_edit_provider.submit_video_edit(
            cfg,
            source_video_path=str(sample_video),
            prompt="transform scene to cinematic golden hour",
            negative_prompt="blurry, distorted",
            aspect_ratio="9:16",
            duration_seconds=5,
            job_id="fal-job-1",
            submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
            public_user_confirmed=True,
            opener=mock_transport,
        )
    assert exc.value.reason == "fal_v2v_local_transport_unsupported_remote_url_required"
    assert mock_transport.call_count == 0


# ---------------------------------------------------------------------------
# 6. Submit Payload Contract with Remote Video URL
# ---------------------------------------------------------------------------

def test_6_fal_submit_payload_contract_with_remote_url():
    """Remote HTTPS video URL must be passed directly as video_url without base64 encoding."""
    cfg = video_ai_edit_provider.provider_config_from_env("fal_video", {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_secret_key",
    })

    captured_requests = []

    def mock_transport(req, timeout=120):
        captured_requests.append(req)
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = json.dumps({
            "request_id": "fal-req-remote-456",
            "status": "IN_QUEUE",
        }).encode("utf-8")
        return resp

    result = video_ai_edit_provider.submit_video_edit(
        cfg,
        source_video_path="https://storage.toanaas.vn/media/input_scene.mp4",
        prompt="cinematic color grading",
        negative_prompt="",
        aspect_ratio="16:9",
        duration_seconds=5,
        job_id="fal-job-remote",
        submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
        public_user_confirmed=True,
        opener=mock_transport,
    )

    assert result["provider_task_id"] == "fal-req-remote-456"
    req = captured_requests[0]
    payload = json.loads(req.data.decode("utf-8"))
    assert payload["video_url"] == "https://storage.toanaas.vn/media/input_scene.mp4"


# ---------------------------------------------------------------------------
# 7. Polling and Result Resolution
# ---------------------------------------------------------------------------

def test_7_fal_poll_video_edit_resolves_response_url():
    """Polling status endpoint returning COMPLETED must resolve final video URL from response_url."""
    cfg = video_ai_edit_provider.provider_config_from_env("fal_video", {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_secret_key",
    })

    call_urls = []

    def mock_transport(req, timeout=120):
        url = req.full_url
        call_urls.append(url)
        resp = MagicMock()
        resp.status = 200
        if "/status" in url:
            # Status check response
            resp.read.return_value = json.dumps({
                "status": "COMPLETED",
                "response_url": "https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/fal-task-789",
            }).encode("utf-8")
        else:
            # Result payload response
            resp.read.return_value = json.dumps({
                "video": {
                    "url": "https://v3.fal.media/files/monkey/output_transformed.mp4",
                    "content_type": "video/mp4",
                    "file_size": 2048000,
                }
            }).encode("utf-8")
        return resp

    result = video_ai_edit_provider.poll_video_edit(
        cfg,
        "fal-task-789",
        opener=mock_transport,
    )

    assert result["status"] == "completed"
    assert result["result_url_present"] is True
    assert result["result_url"] == "https://v3.fal.media/files/monkey/output_transformed.mp4"
    assert len(call_urls) == 2


# ---------------------------------------------------------------------------
# 8. Fail-Closed on Unconfirmed or Hidden Submit Source
# ---------------------------------------------------------------------------

def test_8_fal_fail_closed_on_unconfirmed_submit(tmp_path: Path):
    """Unconfirmed submit or hidden submit source fails closed before HTTP."""
    sample_video = tmp_path / "source.mp4"
    sample_video.write_bytes(b"VIDEO_BYTES")

    cfg = video_ai_edit_provider.provider_config_from_env("fal_video", {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_secret_key",
    })

    mock_transport = MagicMock()

    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc:
        video_ai_edit_provider.submit_video_edit(
            cfg,
            source_video_path=str(sample_video),
            prompt="prompt",
            negative_prompt="",
            aspect_ratio="9:16",
            duration_seconds=5,
            job_id="unconfirmed-job",
            submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
            public_user_confirmed=False,
            opener=mock_transport,
        )
    assert exc.value.reason == "ai_edit_hidden_submit_blocked"
    assert mock_transport.call_count == 0


# ---------------------------------------------------------------------------
# 9. Fail-Closed on Invalid or Missing Source Video
# ---------------------------------------------------------------------------

def test_9_fal_fail_closed_on_missing_source_video():
    """Missing or invalid source video file fails closed before HTTP."""
    cfg = video_ai_edit_provider.provider_config_from_env("fal_video", {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_secret_key",
    })

    mock_transport = MagicMock()

    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc:
        video_ai_edit_provider.submit_video_edit(
            cfg,
            source_video_path="/nonexistent/path/to/source.mp4",
            prompt="prompt",
            negative_prompt="",
            aspect_ratio="9:16",
            duration_seconds=5,
            job_id="missing-video-job",
            submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
            public_user_confirmed=True,
            opener=mock_transport,
        )
    assert exc.value.reason == "fal_v2v_local_transport_unsupported_remote_url_required"
    assert mock_transport.call_count == 0


# ---------------------------------------------------------------------------
# 10. SelfShot2 Connector Integration with Fal
# ---------------------------------------------------------------------------

def test_10_selfshot2_connector_with_fal_provider(tmp_path: Path):
    """SelfShot2 connector successfully routes to Fal V2V provider when configured as primary."""
    source_file = tmp_path / "user_shot_source.mp4"
    source_file.write_bytes(b"USER_SHOT_VIDEO_DATA")

    raw_output = tmp_path / "raw_output.mp4"

    def mock_submit(cfg, **kwargs):
        return {
            "provider_task_id": "fal-ss2-task-100",
            "status": "running",
            "accepted": True,
            "result_url_present": False,
        }

    def mock_poll(cfg, task_id, **kwargs):
        return {
            "provider_task_id": task_id,
            "status": "completed",
            "result_url_present": True,
            "result_url": "https://v3.fal.media/files/transformed_scene.mp4",
        }

    def mock_download(url, dest, **kwargs):
        Path(dest).write_bytes(b"TRANSFORMED_MP4_RESULT_BYTES")
        return {"ok": True, "path": dest, "bytes": len(b"TRANSFORMED_MP4_RESULT_BYTES")}

    fake_continuity = {
        "ok": True,
        "evidence_source": "local_vision_validator",
        "independent_visual_validation": "LOCAL_MODEL",
        "person_required": False,
        "object_required": False,
    }

    env_overrides = {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_key_test",
        "VIDEO_AI_EDIT_PROVIDER_CHAIN": "fal_video,key4u_video",
    }

    with patch.dict(os.environ, env_overrides), \
         patch("services.video_ai_edit_provider.submit_video_edit", side_effect=mock_submit) as spy_submit, \
         patch("services.video_ai_edit_provider.wait_for_result", side_effect=mock_poll), \
         patch("services.video_ai_edit_provider.download_result", side_effect=mock_download), \
         patch("services.video_real_render_connector._materialize_selfshot2_source_segment", return_value=str(source_file)), \
         patch("services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity", return_value=fake_continuity):

        result = video_real_render_connector._render_selfshot2_video_to_video(
            job={
                "source_video_url": "https://storage.toanaas.vn/media/scene_input.mp4",
                "source_video_local_path": str(source_file),
                "quality_tier": 500,
                "public_user_confirmed": True,
                "submit_source": "public_user_final_confirm",
            },
            asset_pack={
                "scene_source_segments": [
                    {
                        "scene_index": 0,
                        "start_seconds": 0.0,
                        "end_seconds": 5.0,
                        "source_video_url": "https://storage.toanaas.vn/media/scene_input.mp4",
                    }
                ]
            },
            raw_path=str(raw_output),
            provider_order=["fal_video", "key4u_video"],
            fallback_prompt="cinematic product scene",
            aspect_ratio="9:16",
            scene_index=0,
        )

        assert spy_submit.call_count == 1
        cfg_arg = spy_submit.call_args[0][0]
        assert cfg_arg.provider_name == "fal_video"
        assert spy_submit.call_args[1]["source_video_path"] == "https://storage.toanaas.vn/media/scene_input.mp4"
        assert result["ok"] is True
        assert result["provider"] == "fal_video"


# ---------------------------------------------------------------------------
# 11. Later-scene source binding must NOT receive full-source video URL (FIRST RED FIXED)
# ---------------------------------------------------------------------------

def test_11_selfshot2_later_scene_must_not_receive_full_source_video_url(tmp_path: Path):
    """For scene_index > 0, Fal must NOT receive the unsliced full-source URL when intended source is materialized segment."""
    source_file = tmp_path / "full_source_30s.mp4"
    source_file.write_bytes(b"FULL_30S_SOURCE_VIDEO_BYTES")
    raw_output = tmp_path / "raw_output_scene1.mp4"

    def mock_submit(cfg, **kwargs):
        source = kwargs.get("source_video_path")
        # Assert that the full unsliced source video URL is NOT passed for scene 1
        assert source != "https://storage.toanaas.vn/media/full_source_30s.mp4", (
            "Violation: scene_index 1 received the full unsliced source_video_url, "
            "violating scene start_seconds, duration_seconds, and source-bound continuity!"
        )
        return {
            "provider_task_id": "fal-ss2-task-101",
            "status": "running",
            "accepted": True,
            "result_url_present": False,
        }

    env_overrides = {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_key_test",
        "VIDEO_AI_EDIT_PROVIDER_CHAIN": "fal_video",
    }

    with patch.dict(os.environ, env_overrides), \
         patch("services.video_ai_edit_provider.submit_video_edit", side_effect=mock_submit) as spy_submit, \
         patch("services.video_real_render_connector._materialize_selfshot2_source_segment", return_value=str(tmp_path / "selfshot2-source-scene-01.mp4")), \
         patch("services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity", return_value={"ok": True}):

        try:
            video_real_render_connector._render_selfshot2_video_to_video(
                job={
                    "source_video_url": "https://storage.toanaas.vn/media/full_source_30s.mp4",
                    "source_video_local_path": str(source_file),
                    "quality_tier": 500,
                    "public_user_confirmed": True,
                    "submit_source": "public_user_final_confirm",
                },
                asset_pack={
                    "scene_source_segments": [
                        {"scene_index": 0, "start_seconds": 0.0, "end_seconds": 5.0},
                        {"scene_index": 1, "start_seconds": 5.0, "end_seconds": 10.0},
                    ]
                },
                raw_path=str(raw_output),
                provider_order=["fal_video"],
                fallback_prompt="cinematic product scene",
                aspect_ratio="9:16",
                scene_index=1,
            )
        except RealVideoRenderError:
            pass


# ---------------------------------------------------------------------------
# 12. 15-second tier request must NOT reach transport with 240 frames (FIRST RED FIXED)
# ---------------------------------------------------------------------------

def test_12_fal_15s_duration_must_not_reach_transport_with_240_frames():
    """Fal Wan 2.2 V2V has num_frames limit of 17..161. 15s (240 frames) must fail closed before transport."""
    cfg = video_ai_edit_provider.provider_config_from_env("fal_video", {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_secret_key",
    })

    mock_transport = MagicMock()

    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc_info:
        video_ai_edit_provider.submit_video_edit(
            cfg,
            source_video_path="https://storage.toanaas.vn/media/input_scene.mp4",
            prompt="transform scene",
            negative_prompt="",
            aspect_ratio="9:16",
            duration_seconds=15,
            job_id="fal-15s-job",
            submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
            public_user_confirmed=True,
            opener=mock_transport,
        )

    assert exc_info.value.reason in {
        "fal_v2v_duration_exceeds_max_frames",
        "fal_v2v_duration_out_of_bounds",
        "fal_v2v_frame_limit_exceeded",
    }
    assert mock_transport.call_count == 0


# ---------------------------------------------------------------------------
# 13. Valid 5s and 10s frame counts reach transport with canonical frames
# ---------------------------------------------------------------------------

def test_13_fal_5s_and_10s_valid_frame_counts():
    """5s produces 81 frames, 10s produces 161 frames in Wan 2.2 format."""
    cfg = video_ai_edit_provider.provider_config_from_env("fal_video", {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_secret_key",
    })

    captured_requests = []

    def mock_transport(req, timeout=120):
        captured_requests.append(req)
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = json.dumps({"request_id": "req-1", "status": "IN_QUEUE"}).encode("utf-8")
        return resp

    # 5s duration test
    video_ai_edit_provider.submit_video_edit(
        cfg,
        source_video_path="https://storage.toanaas.vn/media/scene5s.mp4",
        prompt="transform scene 5s",
        negative_prompt="",
        aspect_ratio="9:16",
        duration_seconds=5,
        job_id="job-5s",
        submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
        public_user_confirmed=True,
        opener=mock_transport,
    )
    p5 = json.loads(captured_requests[0].data.decode("utf-8"))
    assert p5["num_frames"] == 81

    # 10s duration test
    video_ai_edit_provider.submit_video_edit(
        cfg,
        source_video_path="https://storage.toanaas.vn/media/scene10s.mp4",
        prompt="transform scene 10s",
        negative_prompt="",
        aspect_ratio="9:16",
        duration_seconds=10,
        job_id="job-10s",
        submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
        public_user_confirmed=True,
        opener=mock_transport,
    )
    p10 = json.loads(captured_requests[1].data.decode("utf-8"))
    assert p10["num_frames"] == 161


# ---------------------------------------------------------------------------
# 14. Missing remote scene URL fails closed without provider HTTP call
# ---------------------------------------------------------------------------

def test_14_missing_remote_scene_url_fails_closed(tmp_path: Path):
    """When a local scene segment is materialized and no remote URL exists, Fal must fail closed with 0 HTTP calls."""
    source_file = tmp_path / "full_source.mp4"
    source_file.write_bytes(b"FULL_SOURCE_BYTES")
    raw_output = tmp_path / "raw_out.mp4"

    mock_transport = MagicMock()

    env_overrides = {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_key_test",
        "VIDEO_AI_EDIT_PROVIDER_CHAIN": "fal_video",
    }

    with patch.dict(os.environ, env_overrides), \
         patch("services.video_real_render_connector._materialize_selfshot2_source_segment", return_value=str(tmp_path / "selfshot2-source-scene-01.mp4")), \
         patch("urllib.request.urlopen", mock_transport):

        with pytest.raises(RealVideoRenderError) as exc_info:
            video_real_render_connector._render_selfshot2_video_to_video(
                job={
                    "source_video_local_path": str(source_file),
                    "quality_tier": 500,
                    "public_user_confirmed": True,
                    "submit_source": "public_user_final_confirm",
                },
                asset_pack={},
                raw_path=str(raw_output),
                provider_order=["fal_video"],
                fallback_prompt="cinematic product scene",
                aspect_ratio="9:16",
                scene_index=1,
            )

        assert "fal_v2v_local_transport_unsupported_remote_url_required" in str(exc_info.value)
        assert exc_info.value.diagnostics.get("blocker") == "fal_v2v_local_transport_unsupported_remote_url_required"
        assert mock_transport.call_count == 0


# ---------------------------------------------------------------------------
# 15. Catalog max_single_task_seconds=10 blocks 15s tier selection for Fal
# ---------------------------------------------------------------------------

def test_15_catalog_max_seconds_blocks_15s_tier_for_fal():
    """Fal Wan 2.2 model advertises max_single_task_seconds=10, so 15s duration tier excludes Fal."""
    env_overrides = {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_key_test",
        "VIDEO_AI_EDIT_PROVIDER_CHAIN": "fal_video",
    }
    with patch.dict(os.environ, env_overrides):
        configs_15 = video_real_render_connector._selfshot3_provider_configs(["fal_video"], duration_seconds=15)
        assert len(configs_15) == 0

        configs_10 = video_real_render_connector._selfshot3_provider_configs(["fal_video"], duration_seconds=10)
        assert len(configs_10) == 1
        assert configs_10[0].provider_name == "fal_video"

        configs_5 = video_real_render_connector._selfshot3_provider_configs(["fal_video"], duration_seconds=5)
        assert len(configs_5) == 1
        assert configs_5[0].provider_name == "fal_video"


# ---------------------------------------------------------------------------
# 16. Invariant: local video data URI unsupported by provider contract
# ---------------------------------------------------------------------------

def test_16_local_data_uri_unsupported_invariant():
    """Fal provider contract explicitly asserts LOCAL_VIDEO_DATA_URI_SUPPORTED_BY_PROVIDER_CONTRACT is False."""
    assert video_ai_edit_provider.LOCAL_VIDEO_DATA_URI_SUPPORTED_BY_PROVIDER_CONTRACT is False
    assert video_ai_edit_provider.FAL_NUM_FRAMES_MIN == 17
    assert video_ai_edit_provider.FAL_NUM_FRAMES_MAX == 161
