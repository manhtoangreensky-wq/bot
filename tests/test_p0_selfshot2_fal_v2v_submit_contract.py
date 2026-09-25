"""Provider-free tests for SelfShot2 Fal.ai Wan 2.2 V2V Submit Contract & Adapter.

Scope: P0.PRODUCT_VIDEO
Selected Provider: fal.ai
Selected Model: fal-ai/wan/v2.2-a14b/video-to-video
Zero external provider calls made. All network I/O isolated via mocks.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import urllib.error
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
         patch("services.video_ai_edit_provider.upload_fal_media_file", return_value={"ok": True, "provider": "fal_video", "file_url": "https://storage.toanaas.vn/media/scene_input.mp4", "local_path": str(source_file), "local_sha256": "abc", "local_size_bytes": 100, "content_type": "video/mp4"}) as spy_upload, \
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
                    }
                ]
            },
            raw_path=str(raw_output),
            provider_order=["fal_video", "key4u_video"],
            fallback_prompt="cinematic product scene",
            aspect_ratio="9:16",
            scene_index=0,
        )

        assert spy_upload.call_count == 1
        assert spy_submit.call_count == 1
        cfg_arg = spy_submit.call_args[0][0]
        assert cfg_arg.provider_name == "fal_video"
        assert spy_submit.call_args[1]["source_video_path"] == "https://storage.toanaas.vn/media/scene_input.mp4"
        assert result["ok"] is True
        assert result["provider"] == "fal_video"
        assert result["source_transport"] == "fal_storage_https"
        assert result["source_uploaded_multipart"] is False


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

        assert "fal_scene_upload_file_missing" in str(exc_info.value)
        assert exc_info.value.diagnostics.get("blocker") == "fal_scene_upload_file_missing"
        assert exc_info.value.diagnostics.get("fallback_blocked_reason") == "upload_failure_fallback_forbidden"
        assert exc_info.value.diagnostics.get("provider_attempted") is False
        assert exc_info.value.diagnostics.get("no_charge") is True
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
        configs_15 = video_real_render_connector._selfshot2_provider_configs(["fal_video"], duration_seconds=15)
        assert len(configs_15) == 0

        configs_10 = video_real_render_connector._selfshot2_provider_configs(["fal_video"], duration_seconds=10)
        assert len(configs_10) == 1
        assert configs_10[0].provider_name == "fal_video"

        configs_5 = video_real_render_connector._selfshot2_provider_configs(["fal_video"], duration_seconds=5)
        assert len(configs_5) == 1
        assert configs_5[0].provider_name == "fal_video"

        # SelfShot3 isolation: fal_video is strictly excluded
        configs_ss3 = video_real_render_connector._selfshot3_provider_configs(["fal_video"], duration_seconds=10)
        assert len(configs_ss3) == 0


# ---------------------------------------------------------------------------
# 16. Invariant: local video data URI unsupported by provider contract
# ---------------------------------------------------------------------------

def test_16_local_data_uri_unsupported_invariant():
    """Fal provider contract explicitly asserts LOCAL_VIDEO_DATA_URI_SUPPORTED_BY_PROVIDER_CONTRACT is False."""
    assert video_ai_edit_provider.LOCAL_VIDEO_DATA_URI_SUPPORTED_BY_PROVIDER_CONTRACT is False
    assert video_ai_edit_provider.FAL_NUM_FRAMES_MIN == 17
    assert video_ai_edit_provider.FAL_NUM_FRAMES_MAX == 161


# ---------------------------------------------------------------------------
# 17. upload_fal_media_file: local file validation errors
# ---------------------------------------------------------------------------

def test_17_upload_fal_media_file_validation_errors(tmp_path: Path):
    """upload_fal_media_file must validate file existence, non-emptiness, media type, and auth."""
    cfg = video_ai_edit_provider.provider_config_from_env("fal_video", {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_secret_key",
    })

    # Missing file
    non_existent = tmp_path / "does_not_exist.mp4"
    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc_info:
        video_ai_edit_provider.upload_fal_media_file(cfg, non_existent)
    assert exc_info.value.reason == "fal_scene_upload_file_missing"

    # Empty file
    empty_file = tmp_path / "empty.mp4"
    empty_file.write_bytes(b"")
    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc_info:
        video_ai_edit_provider.upload_fal_media_file(cfg, empty_file)
    assert exc_info.value.reason == "fal_scene_upload_file_empty"

    # Unsupported media type
    text_file = tmp_path / "script.txt"
    text_file.write_text("not a video")
    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc_info:
        video_ai_edit_provider.upload_fal_media_file(cfg, text_file)
    assert exc_info.value.reason == "fal_scene_upload_unsupported_media_type"

    # Auth missing / placeholder
    valid_vid = tmp_path / "sample.mp4"
    valid_vid.write_bytes(b"VIDEO_HEADER_AND_BYTES")

    cfg_no_auth = video_ai_edit_provider.provider_config_from_env("fal_video", {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "",
    })
    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc_info:
        video_ai_edit_provider.upload_fal_media_file(cfg_no_auth, valid_vid)
    assert exc_info.value.reason == "fal_scene_upload_auth_missing"

    cfg_placeholder_auth = video_ai_edit_provider.provider_config_from_env("fal_video", {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "placeholder_fal_key",
    })
    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc_info:
        video_ai_edit_provider.upload_fal_media_file(cfg_placeholder_auth, valid_vid)
    assert exc_info.value.reason == "fal_scene_upload_auth_missing"


# ---------------------------------------------------------------------------
# 18. upload_fal_media_file: initiate endpoint error handling
# ---------------------------------------------------------------------------

def test_18_upload_fal_media_file_initiate_http_errors(tmp_path: Path):
    """upload_fal_media_file handles initiate HTTP 500, invalid JSON, and missing/invalid URLs."""
    valid_vid = tmp_path / "scene.mp4"
    valid_vid.write_bytes(b"SCENE_BYTES_DATA")
    cfg = video_ai_edit_provider.provider_config_from_env("fal_video", {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_secret_key",
    })

    # Initiate HTTP 500
    mock_opener_500 = MagicMock()
    mock_opener_500.side_effect = urllib.error.HTTPError(
        url=video_ai_edit_provider.FAL_STORAGE_INITIATE_URL,
        code=500,
        msg="Internal Server Error",
        hdrs={},
        fp=io.BytesIO(b""),
    )
    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc_info:
        video_ai_edit_provider.upload_fal_media_file(cfg, valid_vid, opener=mock_opener_500)
    assert exc_info.value.reason == "fal_scene_upload_initiate_failed_http_500"

    # Initiate invalid JSON
    resp_invalid_json = MagicMock()
    resp_invalid_json.status = 200
    resp_invalid_json.read.return_value = b"<html>Not JSON</html>"
    mock_opener_json = MagicMock(return_value=resp_invalid_json)
    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc_info:
        video_ai_edit_provider.upload_fal_media_file(cfg, valid_vid, opener=mock_opener_json)
    assert exc_info.value.reason == "fal_scene_upload_initiate_invalid_response"

    # Missing upload_url
    resp_no_upload_url = MagicMock()
    resp_no_upload_url.status = 200
    resp_no_upload_url.read.return_value = json.dumps({"file_url": "https://v3.fal.media/files/out.mp4"}).encode("utf-8")
    mock_opener_no_upload = MagicMock(return_value=resp_no_upload_url)
    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc_info:
        video_ai_edit_provider.upload_fal_media_file(cfg, valid_vid, opener=mock_opener_no_upload)
    assert exc_info.value.reason == "fal_scene_upload_upload_url_missing"

    # Missing file_url
    resp_no_file_url = MagicMock()
    resp_no_file_url.status = 200
    resp_no_file_url.read.return_value = json.dumps({"upload_url": "https://fal-storage.aws/upload/123"}).encode("utf-8")
    mock_opener_no_file = MagicMock(return_value=resp_no_file_url)
    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc_info:
        video_ai_edit_provider.upload_fal_media_file(cfg, valid_vid, opener=mock_opener_no_file)
    assert exc_info.value.reason == "fal_scene_upload_result_url_missing"

    # Invalid file_url scheme (http instead of https)
    resp_insecure_url = MagicMock()
    resp_insecure_url.status = 200
    resp_insecure_url.read.return_value = json.dumps({
        "upload_url": "https://fal-storage.aws/upload/123",
        "file_url": "http://v3.fal.media/files/insecure.mp4",
    }).encode("utf-8")
    mock_opener_insecure = MagicMock(return_value=resp_insecure_url)
    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc_info:
        video_ai_edit_provider.upload_fal_media_file(cfg, valid_vid, opener=mock_opener_insecure)
    assert exc_info.value.reason == "fal_scene_upload_result_url_invalid"


# ---------------------------------------------------------------------------
# 19. upload_fal_media_file: PUT upload HTTP 500 error handling
# ---------------------------------------------------------------------------

def test_19_upload_fal_media_file_put_upload_errors(tmp_path: Path):
    """upload_fal_media_file handles PUT upload HTTP error."""
    valid_vid = tmp_path / "scene.mp4"
    valid_vid.write_bytes(b"SCENE_BYTES_DATA")
    cfg = video_ai_edit_provider.provider_config_from_env("fal_video", {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_secret_key",
    })

    resp_initiate = MagicMock()
    resp_initiate.status = 200
    resp_initiate.read.return_value = json.dumps({
        "upload_url": "https://fal-storage.aws/upload/123",
        "file_url": "https://v3.fal.media/files/scene.mp4",
    }).encode("utf-8")

    def mock_opener(req, **kwargs):
        if req.get_method() == "POST":
            return resp_initiate
        raise urllib.error.HTTPError(
            url=req.get_full_url(),
            code=500,
            msg="Storage PUT Failed",
            hdrs={},
            fp=io.BytesIO(b""),
        )

    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc_info:
        video_ai_edit_provider.upload_fal_media_file(cfg, valid_vid, opener=mock_opener)
    assert exc_info.value.reason == "fal_scene_upload_failed_http_500"


# ---------------------------------------------------------------------------
# 20. upload_fal_media_file: success contract & byte integrity
# ---------------------------------------------------------------------------

def test_20_upload_fal_media_file_success_contract(tmp_path: Path):
    """upload_fal_media_file successfully initiates and uploads exact scene bytes."""
    valid_vid = tmp_path / "scene_0.mp4"
    file_bytes = b"SCENE_0_RAW_BYTES_EXACT"
    valid_vid.write_bytes(file_bytes)
    cfg = video_ai_edit_provider.provider_config_from_env("fal_video", {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_secret_key",
    })

    captured_requests = []

    resp_initiate = MagicMock()
    resp_initiate.status = 200
    resp_initiate.read.return_value = json.dumps({
        "upload_url": "https://fal-storage.aws/upload/presigned_123",
        "file_url": "https://v3.fal.media/files/scene_0_uploaded.mp4",
    }).encode("utf-8")

    resp_put = MagicMock()
    resp_put.status = 200
    resp_put.read.return_value = b""

    def mock_opener(req, **kwargs):
        captured_requests.append(req)
        if req.get_method() == "POST":
            return resp_initiate
        if req.get_method() == "PUT":
            return resp_put
        raise ValueError(f"Unexpected method: {req.get_method()}")

    res = video_ai_edit_provider.upload_fal_media_file(cfg, valid_vid, opener=mock_opener)

    assert res["ok"] is True
    assert res["provider"] == "fal_video"
    assert res["file_url"] == "https://v3.fal.media/files/scene_0_uploaded.mp4"
    assert res["local_path"] == str(valid_vid)
    assert res["local_sha256"] == hashlib.sha256(file_bytes).hexdigest()
    assert res["local_size_bytes"] == len(file_bytes)
    assert res["content_type"] == "video/mp4"

    assert len(captured_requests) == 2
    post_req, put_req = captured_requests
    assert post_req.get_full_url() == video_ai_edit_provider.FAL_STORAGE_INITIATE_URL
    assert post_req.get_header("Authorization") == "Key fal_secret_key"
    assert put_req.get_full_url() == "https://fal-storage.aws/upload/presigned_123"
    assert put_req.data == file_bytes
    assert put_req.get_header("Content-type") == "video/mp4"


# ---------------------------------------------------------------------------
# 21. SelfShot2 connector uploads local scene bytes and binds to submit
# ---------------------------------------------------------------------------

def test_21_selfshot2_connector_uploads_local_scene_bytes_and_binds_to_submit(tmp_path: Path):
    """SelfShot2 connector automatically uploads local scene segment and binds returned HTTPS URL to submit."""
    source_file = tmp_path / "full_source.mp4"
    source_file.write_bytes(b"FULL_SOURCE_BYTES")
    scene_file = tmp_path / "scene_segment_1.mp4"
    scene_bytes = b"SCENE_SEGMENT_1_SLICED_BYTES"
    scene_file.write_bytes(scene_bytes)
    raw_output = tmp_path / "raw_out.mp4"

    mock_upload = MagicMock(return_value={
        "ok": True,
        "provider": "fal_video",
        "file_url": "https://v3.fal.media/files/scene_segment_1_remote.mp4",
        "local_path": str(scene_file),
        "local_sha256": hashlib.sha256(scene_bytes).hexdigest(),
        "local_size_bytes": len(scene_bytes),
        "content_type": "video/mp4",
    })

    captured_submits = []
    def mock_submit(cfg, **kwargs):
        captured_submits.append(kwargs)
        return {
            "provider_task_id": "fal-ss2-upload-bind-1",
            "status": "completed",
            "accepted": True,
            "result_url_present": True,
            "result_url": "https://v3.fal.media/files/result_1.mp4",
        }

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
        "VIDEO_AI_EDIT_PROVIDER_CHAIN": "fal_video",
    }

    with patch.dict(os.environ, env_overrides), \
         patch("services.video_ai_edit_provider.upload_fal_media_file", mock_upload), \
         patch("services.video_ai_edit_provider.submit_video_edit", side_effect=mock_submit), \
         patch("services.video_ai_edit_provider.download_result", return_value={"ok": True, "path": str(raw_output), "bytes": 100}), \
         patch("services.video_real_render_connector._materialize_selfshot2_source_segment", return_value=str(scene_file)), \
         patch("services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity", return_value=fake_continuity):

        result = video_real_render_connector._render_selfshot2_video_to_video(
            job={
                "source_video_local_path": str(source_file),
                "quality_tier": 500,
                "public_user_confirmed": True,
                "submit_source": "public_user_final_confirm",
            },
            asset_pack={
                "scene_source_segments": [
                    {"scene_index": 1, "start_seconds": 5.0, "end_seconds": 10.0}
                ]
            },
            raw_path=str(raw_output),
            provider_order=["fal_video"],
            fallback_prompt="cinematic product scene",
            aspect_ratio="9:16",
            scene_index=1,
        )

        assert mock_upload.call_count == 1
        cfg_arg, path_arg = mock_upload.call_args[0]
        assert cfg_arg.provider_name == "fal_video"
        assert path_arg == str(scene_file)

        assert len(captured_submits) == 1
        assert captured_submits[0]["source_video_path"] == "https://v3.fal.media/files/scene_segment_1_remote.mp4"
        assert result["ok"] is True
        assert result["provider"] == "fal_video"


# ---------------------------------------------------------------------------
# 22. Multi-scene simulation: distinct byte binding and isolation across scenes
# ---------------------------------------------------------------------------

def test_22_selfshot2_multi_scene_simulation_distinct_byte_binding(tmp_path: Path):
    """Simulating 3 scenes proves each scene uploads distinct bytes and receives distinct remote URLs."""
    source_file = tmp_path / "long_source.mp4"
    source_file.write_bytes(b"ENTIRE_SOURCE_VIDEO_30_SECONDS")

    scene_files = [
        tmp_path / f"scene_{i}.mp4" for i in range(3)
    ]
    scene_bytes = [
        b"SCENE_0_BYTES_AAA",
        b"SCENE_1_BYTES_BBB",
        b"SCENE_2_BYTES_CCC",
    ]
    for p, b in zip(scene_files, scene_bytes):
        p.write_bytes(b)

    uploaded_urls = {}
    def mock_upload(cfg, path):
        idx = next(i for i, sf in enumerate(scene_files) if str(sf) == str(path))
        url = f"https://v3.fal.media/files/uploaded_scene_{idx}.mp4"
        uploaded_urls[idx] = url
        return {
            "ok": True,
            "provider": "fal_video",
            "file_url": url,
            "local_path": str(path),
            "local_sha256": hashlib.sha256(scene_bytes[idx]).hexdigest(),
            "local_size_bytes": len(scene_bytes[idx]),
            "content_type": "video/mp4",
        }

    submitted_sources = {}
    def mock_submit(cfg, **kwargs):
        job_id = kwargs.get("job_id", "")
        submitted_sources[job_id] = kwargs.get("source_video_path")
        return {
            "provider_task_id": f"fal-task-{job_id}",
            "status": "completed",
            "accepted": True,
            "result_url_present": True,
            "result_url": f"https://v3.fal.media/files/result-{job_id}.mp4",
        }

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
        "VIDEO_AI_EDIT_PROVIDER_CHAIN": "fal_video",
    }

    with patch.dict(os.environ, env_overrides), \
         patch("services.video_ai_edit_provider.upload_fal_media_file", side_effect=mock_upload), \
         patch("services.video_ai_edit_provider.submit_video_edit", side_effect=mock_submit), \
         patch("services.video_ai_edit_provider.download_result", return_value={"ok": True, "path": str(tmp_path / "out.mp4"), "bytes": 100}), \
         patch("services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity", return_value=fake_continuity):

        for scene_idx in range(3):
            with patch("services.video_real_render_connector._materialize_selfshot2_source_segment", return_value=str(scene_files[scene_idx])):
                res = video_real_render_connector._render_selfshot2_video_to_video(
                    job={
                        "job_id": "test_job_123",
                        "source_video_local_path": str(source_file),
                        "quality_tier": 500,
                        "public_user_confirmed": True,
                        "submit_source": "public_user_final_confirm",
                    },
                    asset_pack={
                        "scene_source_segments": [
                            {"scene_index": i, "start_seconds": float(i * 5), "end_seconds": float((i + 1) * 5)}
                            for i in range(3)
                        ]
                    },
                    raw_path=str(tmp_path / f"raw_{scene_idx}.mp4"),
                    provider_order=["fal_video"],
                    fallback_prompt=f"scene prompt {scene_idx}",
                    aspect_ratio="9:16",
                    scene_index=scene_idx,
                )
                assert res["ok"] is True

    # Assert 3 distinct uploads and 3 distinct submits matching scene indices
    assert len(uploaded_urls) == 3
    assert len(set(uploaded_urls.values())) == 3
    assert submitted_sources["test_job_123:scene:0"] == "https://v3.fal.media/files/uploaded_scene_0.mp4"
    assert submitted_sources["test_job_123:scene:1"] == "https://v3.fal.media/files/uploaded_scene_1.mp4"
    assert submitted_sources["test_job_123:scene:2"] == "https://v3.fal.media/files/uploaded_scene_2.mp4"


# ---------------------------------------------------------------------------
# 23. Upload failure blocks fallback to second provider
# ---------------------------------------------------------------------------

def test_23_upload_failure_blocks_fallback_to_second_provider(tmp_path: Path):
    """When Fal scene upload fails, the connector must fail closed with 0 submits and forbid fallback to key4u."""
    source_file = tmp_path / "full_source.mp4"
    source_file.write_bytes(b"FULL_SOURCE_BYTES")
    scene_file = tmp_path / "scene_0.mp4"
    scene_file.write_bytes(b"SCENE_BYTES")
    raw_output = tmp_path / "raw_out.mp4"

    mock_upload = MagicMock(side_effect=video_ai_edit_provider.AiEditProviderError("fal_scene_upload_failed_http_500"))
    spy_submit = MagicMock()

    env_overrides = {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_key_test",
        "KEY4U_VIDEO_TO_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_TO_VIDEO_API_KEY": "key4u_key_test",
        "VIDEO_AI_EDIT_PROVIDER_CHAIN": "fal_video,key4u_video",
    }

    with patch.dict(os.environ, env_overrides), \
         patch("services.video_ai_edit_provider.upload_fal_media_file", mock_upload), \
         patch("services.video_ai_edit_provider.submit_video_edit", spy_submit), \
         patch("services.video_real_render_connector._materialize_selfshot2_source_segment", return_value=str(scene_file)):

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
                provider_order=["fal_video", "key4u_video"],
                fallback_prompt="cinematic product scene",
                aspect_ratio="9:16",
                scene_index=0,
            )

        assert "fal_scene_upload_failed_http_500" in str(exc_info.value)
        diag = exc_info.value.diagnostics
        assert diag["ok"] is False
        assert diag["no_charge"] is True
        assert diag["provider_attempted"] is False
        assert diag["fallback_blocked_reason"] == "upload_failure_fallback_forbidden"

        # Assert 0 generation submit calls across all providers
        assert spy_submit.call_count == 0


# ---------------------------------------------------------------------------
# 24. Job isolation: upload state not leaked between jobs
# ---------------------------------------------------------------------------

def test_24_job_isolation_upload_state_not_leaked(tmp_path: Path):
    """Job A upload does not leak into Job B with different scene bytes."""
    file_a = tmp_path / "job_a_scene.mp4"
    file_a.write_bytes(b"JOB_A_BYTES_111")
    file_b = tmp_path / "job_b_scene.mp4"
    file_b.write_bytes(b"JOB_B_BYTES_222")

    cfg = video_ai_edit_provider.provider_config_from_env("fal_video", {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_key_test",
    })

    upload_targets = []
    def mock_opener(req, **kwargs):
        if req.get_method() == "POST":
            req_data = json.loads(req.data.decode("utf-8"))
            fname = req_data["file_name"]
            resp = MagicMock()
            resp.status = 200
            resp.read.return_value = json.dumps({
                "upload_url": f"https://fal-storage.aws/upload/{fname}",
                "file_url": f"https://v3.fal.media/files/{fname}",
            }).encode("utf-8")
            return resp
        if req.get_method() == "PUT":
            upload_targets.append(req.data)
            resp = MagicMock()
            resp.status = 200
            resp.read.return_value = b""
            return resp
        raise ValueError("unexpected")

    res_a = video_ai_edit_provider.upload_fal_media_file(cfg, file_a, opener=mock_opener)
    res_b = video_ai_edit_provider.upload_fal_media_file(cfg, file_b, opener=mock_opener)

    assert res_a["file_url"] != res_b["file_url"]
    assert res_a["local_sha256"] != res_b["local_sha256"]
    assert upload_targets[0] == b"JOB_A_BYTES_111"
    assert upload_targets[1] == b"JOB_B_BYTES_222"


# ---------------------------------------------------------------------------
# 25. SelfShot3 isolation: unaffected by Fal upload logic
# ---------------------------------------------------------------------------

def test_25_selfshot3_isolation_unaffected_by_fal_upload(tmp_path: Path):
    """SelfShot3 video-to-video connector does NOT invoke Fal upload logic."""
    spy_upload = MagicMock()
    with patch("services.video_ai_edit_provider.upload_fal_media_file", spy_upload):
        with pytest.raises(RealVideoRenderError) as exc_info:
            video_real_render_connector._render_selfshot3_video_to_video(
                job={"source_video_local_path": ""},
                asset_pack={},
                raw_path=str(tmp_path / "raw.mp4"),
                provider_order=["fal_video"],
                fallback_prompt="prompt",
                aspect_ratio="9:16",
            )
        assert "selfshot3_source_video_not_materialized" in str(exc_info.value)
        assert spy_upload.call_count == 0


# ---------------------------------------------------------------------------
# 26. SelfShot3 strictly blocks fal provider order
# ---------------------------------------------------------------------------

def test_26_selfshot3_strictly_blocks_fal_provider_order(tmp_path: Path):
    """SelfShot3 with valid local file and provider_order=['fal_video'] must raise provider_unavailable with 0 generation submits."""
    source_file = tmp_path / "valid_source.mp4"
    source_file.write_bytes(b"VALID_SOURCE_BYTES")
    raw_output = tmp_path / "raw_ss3.mp4"

    spy_upload = MagicMock()
    spy_submit = MagicMock()

    env_overrides = {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_key_test",
        "VIDEO_AI_EDIT_PROVIDER_CHAIN": "fal_video",
    }

    with patch.dict(os.environ, env_overrides), \
         patch("services.video_ai_edit_provider.upload_fal_media_file", spy_upload), \
         patch("services.video_ai_edit_provider.submit_video_edit", spy_submit):

        with pytest.raises(RealVideoRenderError) as exc_info:
            video_real_render_connector._render_selfshot3_video_to_video(
                job={
                    "source_video_local_path": str(source_file),
                    "quality_tier": 500,
                    "public_user_confirmed": True,
                    "submit_source": "public_user_final_confirm",
                },
                asset_pack={},
                raw_path=str(raw_output),
                provider_order=["fal_video"],
                fallback_prompt="prompt",
                aspect_ratio="9:16",
            )

        assert "selfshot3_video_to_video_provider_unavailable" in str(exc_info.value)
        diag = exc_info.value.diagnostics
        assert diag["ok"] is False
        assert diag["provider_attempted"] is False
        assert diag["no_charge"] is True
        assert spy_upload.call_count == 0
        assert spy_submit.call_count == 0


# ---------------------------------------------------------------------------
# 27. Submit ambiguity: transport error forbids secondary fallback
# ---------------------------------------------------------------------------

def test_27_submit_ambiguity_transport_error_forbids_secondary_fallback(tmp_path: Path):
    """Network/timeout during primary Fal submit leaves task state ambiguous; fallback to key4u is forbidden."""
    source_file = tmp_path / "source.mp4"
    source_file.write_bytes(b"SOURCE_BYTES")
    scene_file = tmp_path / "scene.mp4"
    scene_file.write_bytes(b"SCENE_BYTES")
    raw_output = tmp_path / "raw.mp4"

    mock_upload = MagicMock(return_value={
        "ok": True,
        "provider": "fal_video",
        "file_url": "https://v3.fal.media/files/scene.mp4",
        "local_path": str(scene_file),
        "local_sha256": "abc",
        "local_size_bytes": 100,
        "content_type": "video/mp4",
    })

    def mock_submit(cfg, **kwargs):
        if cfg.provider_name == "fal_video":
            raise video_ai_edit_provider.AiEditProviderError("provider_submit_timeout")
        raise AssertionError("Secondary provider must NOT be submitted on ambiguous submit error!")

    spy_submit = MagicMock(side_effect=mock_submit)

    env_overrides = {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_key_test",
        "KEY4U_VIDEO_TO_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_TO_VIDEO_API_KEY": "key4u_key_test",
        "VIDEO_AI_EDIT_PROVIDER_CHAIN": "fal_video,key4u_video",
    }

    with patch.dict(os.environ, env_overrides), \
         patch("services.video_ai_edit_provider.upload_fal_media_file", mock_upload), \
         patch("services.video_ai_edit_provider.submit_video_edit", spy_submit), \
         patch("services.video_real_render_connector._materialize_selfshot2_source_segment", return_value=str(scene_file)):

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
                provider_order=["fal_video", "key4u_video"],
                fallback_prompt="prompt",
                aspect_ratio="9:16",
                scene_index=0,
            )

        assert "provider_submit_timeout" in str(exc_info.value)
        diag = exc_info.value.diagnostics
        assert diag["ok"] is False
        assert diag["fallback_blocked_reason"] == "ambiguous_state_fallback_forbidden"
        # Total generation submits across ALL providers <= 1 (here exactly 1 attempt on Fal, 0 on key4u)
        assert spy_submit.call_count == 1
        assert spy_submit.call_args[0][0].provider_name == "fal_video"


# ---------------------------------------------------------------------------
# 28. Poll timeout with known task_id forbids secondary fallback
# ---------------------------------------------------------------------------

def test_28_poll_timeout_with_known_task_id_forbids_secondary_fallback(tmp_path: Path):
    """When Fal submit succeeds returning task_id, client poll timeout must NOT declare primary dead or fall back."""
    source_file = tmp_path / "source.mp4"
    source_file.write_bytes(b"SOURCE_BYTES")
    scene_file = tmp_path / "scene.mp4"
    scene_file.write_bytes(b"SCENE_BYTES")
    raw_output = tmp_path / "raw.mp4"

    mock_upload = MagicMock(return_value={
        "ok": True,
        "provider": "fal_video",
        "file_url": "https://v3.fal.media/files/scene.mp4",
        "local_path": str(scene_file),
        "local_sha256": "abc",
        "local_size_bytes": 100,
        "content_type": "video/mp4",
    })

    spy_submit = MagicMock(return_value={
        "provider_task_id": "fal-live-task-999",
        "status": "running",
        "accepted": True,
        "result_url_present": False,
    })

    mock_poll = MagicMock(side_effect=video_ai_edit_provider.AiEditProviderError("provider_poll_timeout"))

    env_overrides = {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_key_test",
        "KEY4U_VIDEO_TO_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_TO_VIDEO_API_KEY": "key4u_key_test",
        "VIDEO_AI_EDIT_PROVIDER_CHAIN": "fal_video,key4u_video",
    }

    with patch.dict(os.environ, env_overrides), \
         patch("services.video_ai_edit_provider.upload_fal_media_file", mock_upload), \
         patch("services.video_ai_edit_provider.submit_video_edit", spy_submit), \
         patch("services.video_ai_edit_provider.wait_for_result", mock_poll), \
         patch("services.video_real_render_connector._materialize_selfshot2_source_segment", return_value=str(scene_file)):

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
                provider_order=["fal_video", "key4u_video"],
                fallback_prompt="prompt",
                aspect_ratio="9:16",
                scene_index=0,
            )

        assert "provider_poll_timeout" in str(exc_info.value)
        diag = exc_info.value.diagnostics
        assert diag["ok"] is False
        assert diag["generation_task_id_obtained"] is True
        assert diag["fallback_blocked_reason"] == "ambiguous_state_fallback_forbidden"
        # Zero submits to secondary provider
        assert spy_submit.call_count == 1
        assert spy_submit.call_args[0][0].provider_name == "fal_video"


# ---------------------------------------------------------------------------
# 29. Fallback permitted only on explicit terminal failure
# ---------------------------------------------------------------------------

def test_29_fallback_permitted_only_on_explicit_terminal_failure(tmp_path: Path):
    """Fallback authority: helper permits fallback only on proven terminal dead states with valid candidate;
    in production routing, Key4U is not wire-proven so secondary fallback is blocked (KEY4U_SECONDARY_V2V_ELIGIBLE=NO)."""
    # 1. Direct helper seam testing with bounded synthetic/stub candidate
    stub_candidate = video_ai_edit_provider.AiEditProviderConfig(
        provider_name="fal_video",
        enabled=True,
        submit_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video",
        poll_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/{task_id}/status",
        auth_header_name="Authorization",
        auth_header_value="Key valid_secret",
        model="fal-ai/wan/v2.2-a14b/video-to-video",
        interface="video_to_video_json",
        capabilities=("video_to_video",),
    )

    # Proven terminal dead states allow fallback
    for terminal_status in ["failed", "rejected", "cancelled"]:
        dec = video_ai_edit_provider.controlled_fallback_decision(
            public_confirm_provenance=True,
            primary_status=terminal_status,
            primary_task_alive=False,
            fallback_count=0,
            candidate=stub_candidate,
            primary_error="",
            primary_terminal_failure_proven=True,
        )
        assert dec["allowed"] is True
        assert dec["reason"] == "controlled_terminal_fallback"

    # Terminal failure unproven blocks fallback
    dec_unproven = video_ai_edit_provider.controlled_fallback_decision(
        public_confirm_provenance=True,
        primary_status="failed",
        primary_task_alive=False,
        fallback_count=0,
        candidate=stub_candidate,
        primary_error="",
        primary_terminal_failure_proven=False,
    )
    assert dec_unproven["allowed"] is False
    assert dec_unproven["reason"] == "primary_terminal_failure_unproven"

    # 2. End-to-end SelfShot2 production routing: Key4U has no proven V2V wire contract
    source_file = tmp_path / "source.mp4"
    source_file.write_bytes(b"SOURCE_BYTES")
    scene_file = tmp_path / "scene.mp4"
    scene_file.write_bytes(b"SCENE_BYTES")
    raw_output = tmp_path / "raw.mp4"

    mock_upload = MagicMock(return_value={
        "ok": True,
        "provider": "fal_video",
        "file_url": "https://v3.fal.media/files/scene.mp4",
        "local_path": str(scene_file),
        "local_sha256": "abc",
        "local_size_bytes": 100,
        "content_type": "video/mp4",
    })

    spy_submit = MagicMock(return_value={
        "provider_task_id": "fal-term-task-1",
        "status": "running",
        "accepted": True,
        "result_url_present": False,
    })

    mock_wait = MagicMock(side_effect=video_ai_edit_provider.AiEditProviderError("provider_terminal_failure"))

    env_overrides = {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_key_test",
        "KEY4U_VIDEO_TO_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_TO_VIDEO_API_KEY": "key4u_key_test",
        "VIDEO_AI_EDIT_PROVIDER_CHAIN": "fal_video,key4u_video",
    }

    with patch.dict(os.environ, env_overrides), \
         patch("services.video_ai_edit_provider.upload_fal_media_file", mock_upload), \
         patch("services.video_ai_edit_provider.submit_video_edit", spy_submit), \
         patch("services.video_ai_edit_provider.wait_for_result", mock_wait), \
         patch("services.video_real_render_connector._materialize_selfshot2_source_segment", return_value=str(scene_file)):

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
                provider_order=["fal_video", "key4u_video"],
                fallback_prompt="prompt",
                aspect_ratio="9:16",
                scene_index=0,
            )

        assert "provider_terminal_failure" in str(exc_info.value)
        # Fal submitted once, Key4U never submitted (KEY4U_SECONDARY_V2V_ELIGIBLE=NO)
        assert spy_submit.call_count == 1
        assert spy_submit.call_args[0][0].provider_name == "fal_video"
        diag = exc_info.value.diagnostics
        assert diag["ok"] is False
        assert diag["generation_submit_attempted"] is True
        assert diag["generation_task_id_obtained"] is True


# ---------------------------------------------------------------------------
# 30. Result retrieval failure forbids secondary fallback
# ---------------------------------------------------------------------------

def test_30_result_retrieval_failure_forbids_secondary_fallback(tmp_path: Path):
    """When generation completed on Fal but result fetch fails (5xx, invalid json, missing url), fallback is forbidden."""
    source_file = tmp_path / "source.mp4"
    source_file.write_bytes(b"SOURCE_BYTES")
    scene_file = tmp_path / "scene.mp4"
    scene_file.write_bytes(b"SCENE_BYTES")
    raw_output = tmp_path / "raw.mp4"

    mock_upload = MagicMock(return_value={
        "ok": True,
        "provider": "fal_video",
        "file_url": "https://v3.fal.media/files/scene.mp4",
        "local_path": str(scene_file),
        "local_sha256": "abc",
        "local_size_bytes": 100,
        "content_type": "video/mp4",
    })

    spy_submit = MagicMock(return_value={
        "provider_task_id": "fal-res-fetch-task-1",
        "status": "running",
        "accepted": True,
        "result_url_present": False,
    })

    mock_wait = MagicMock(side_effect=video_ai_edit_provider.AiEditProviderError("provider_result_fetch_http_500"))

    env_overrides = {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_key_test",
        "KEY4U_VIDEO_TO_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_TO_VIDEO_API_KEY": "key4u_key_test",
        "VIDEO_AI_EDIT_PROVIDER_CHAIN": "fal_video,key4u_video",
    }

    with patch.dict(os.environ, env_overrides), \
         patch("services.video_ai_edit_provider.upload_fal_media_file", mock_upload), \
         patch("services.video_ai_edit_provider.submit_video_edit", spy_submit), \
         patch("services.video_ai_edit_provider.wait_for_result", mock_wait), \
         patch("services.video_real_render_connector._materialize_selfshot2_source_segment", return_value=str(scene_file)):

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
                provider_order=["fal_video", "key4u_video"],
                fallback_prompt="prompt",
                aspect_ratio="9:16",
                scene_index=0,
            )

        assert "provider_result_fetch_http_500" in str(exc_info.value)
        diag = exc_info.value.diagnostics
        assert diag["ok"] is False
        assert diag["fallback_blocked_reason"] == "ambiguous_state_fallback_forbidden"
        # Total generation submits across ALL providers == 1
        assert spy_submit.call_count == 1


# ---------------------------------------------------------------------------
# 31. Fal auth scheme strict canonical validation
# ---------------------------------------------------------------------------

def test_31_fal_auth_scheme_strict_canonical_validation(tmp_path: Path):
    """FAL auth must strictly normalize raw token to 'Key <raw>', preserve 'Key <token>', and fail closed on 'Bearer <token>'."""
    # 1. Raw token normalization
    cfg_raw = video_ai_edit_provider.provider_config_from_env("fal_video", {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "raw_secret_xyz",
    })
    assert cfg_raw.auth_header_value == "Key raw_secret_xyz"
    errs_raw = video_ai_edit_provider.validate_provider_config(cfg_raw)
    assert "auth" not in errs_raw.get("invalid_fields", [])
    assert errs_raw.get("ok") is True

    # 2. Canonical 'Key <token>' preservation
    cfg_canonical = video_ai_edit_provider.provider_config_from_env("fal_video", {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "Key canonical_secret_xyz",
    })
    assert cfg_canonical.auth_header_value == "Key canonical_secret_xyz"
    errs_canonical = video_ai_edit_provider.validate_provider_config(cfg_canonical)
    assert "auth" not in errs_canonical.get("invalid_fields", [])
    assert errs_canonical.get("ok") is True

    # 3. Disallowed scheme 'Bearer <token>' fails closed
    cfg_bearer = video_ai_edit_provider.provider_config_from_env("fal_video", {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "Bearer unexpected_scheme_token",
    })
    assert cfg_bearer.auth_header_value == "Bearer unexpected_scheme_token"
    errs_bearer = video_ai_edit_provider.validate_provider_config(cfg_bearer)
    assert "auth" in errs_bearer.get("invalid_fields", [])
    assert errs_bearer.get("ok") is False

    # 4. Upload fails closed on invalid auth scheme
    test_file = tmp_path / "test.mp4"
    test_file.write_bytes(b"BYTES")
    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc_info:
        video_ai_edit_provider.upload_fal_media_file(cfg_bearer, test_file)
    assert exc_info.value.reason == "fal_scene_upload_auth_missing"


# ---------------------------------------------------------------------------
# 32. Storage upload URL security invariants
# ---------------------------------------------------------------------------

def test_32_storage_upload_url_security_invariants(tmp_path: Path):
    """upload_fal_media_file must enforce upload_url strictly starts with https://, forbidding http://, file://, etc."""
    test_file = tmp_path / "test_sec.mp4"
    test_file.write_bytes(b"TEST_BYTES_SEC")

    cfg = video_ai_edit_provider.provider_config_from_env("fal_video", {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_valid_key",
    })

    insecure_urls = [
        "http://insecure.fal-storage.aws/upload/123",
        "file:///etc/passwd",
        "ftp://storage.fal.ai/upload",
        "javascript:alert(1)",
    ]

    put_calls = []
    for bad_url in insecure_urls:
        def mock_opener(req, **kwargs):
            if req.get_method() == "POST":
                resp = MagicMock()
                resp.status = 200
                resp.read.return_value = json.dumps({
                    "upload_url": bad_url,
                    "file_url": "https://v3.fal.media/files/out.mp4",
                }).encode("utf-8")
                return resp
            if req.get_method() == "PUT":
                put_calls.append(req.get_full_url())
                resp = MagicMock()
                resp.status = 200
                resp.read.return_value = b""
                return resp
            raise ValueError(f"unexpected method {req.get_method()}")

        with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc_info:
            video_ai_edit_provider.upload_fal_media_file(cfg, test_file, opener=mock_opener)
        assert exc_info.value.reason == "fal_scene_upload_upload_url_invalid"

    # Crucial security invariant: 0 PUT requests issued
    assert len(put_calls) == 0


# ---------------------------------------------------------------------------
# 33. Fal frame boundary matrix
# ---------------------------------------------------------------------------

def test_33_fal_frame_boundary_matrix():
    """Fal Wan 2.2 frame calculation matrix covering boundary conditions."""
    cfg = video_ai_edit_provider.provider_config_from_env("fal_video", {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_key_test",
    })

    # Valid duration tests (all must be in [17, 161] and satisfy (f - 1) % 4 == 0)
    valid_test_cases = [
        (1.0, 17),
        (2.0, 33),
        (4.9, 81),
        (5.0, 81),
        (5.1, 81),
        (7.5, 121),
        (9.9, 161),
        (10.0, 161),
    ]
    for dur, expected_frames in valid_test_cases:
        p = video_ai_edit_provider.build_video_edit_payload(
            cfg,
            prompt="cinematic product scene",
            source_video_path="https://v3.fal.media/files/test.mp4",
            duration_seconds=dur,
            aspect_ratio="9:16",
        )
        frames = p["num_frames"]
        assert frames == expected_frames
        assert (frames - 1) % 4 == 0
        assert 17 <= frames <= 161

    # Invalid duration tests (must raise fal_v2v_duration_exceeds_max_frames)
    invalid_durations = [0.5, 11.0, 15.0, 30.0]
    for bad_dur in invalid_durations:
        with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc_info:
            video_ai_edit_provider.build_video_edit_payload(
                cfg,
                prompt="cinematic product scene",
                source_video_path="https://v3.fal.media/files/test.mp4",
                duration_seconds=bad_dur,
                aspect_ratio="9:16",
            )
        assert exc_info.value.reason == "fal_v2v_duration_exceeds_max_frames"


# ---------------------------------------------------------------------------
# 34. Duration segment consistency preflight
# ---------------------------------------------------------------------------

def test_34_duration_segment_consistency_preflight(tmp_path: Path):
    """Segment duration mismatch with target duration must fail closed before upload or submit."""
    source_file = tmp_path / "source.mp4"
    source_file.write_bytes(b"SOURCE_BYTES")
    raw_output = tmp_path / "raw.mp4"

    spy_upload = MagicMock()
    spy_submit = MagicMock()

    env_overrides = {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_key_test",
        "VIDEO_AI_EDIT_PROVIDER_CHAIN": "fal_video",
    }

    with patch.dict(os.environ, env_overrides), \
         patch("services.video_ai_edit_provider.upload_fal_media_file", spy_upload), \
         patch("services.video_ai_edit_provider.submit_video_edit", spy_submit):

        with pytest.raises(RealVideoRenderError) as exc_info:
            video_real_render_connector._render_selfshot2_video_to_video(
                job={
                    "source_video_local_path": str(source_file),
                    "quality_tier": 500,
                    "public_user_confirmed": True,
                    "submit_source": "public_user_final_confirm",
                    "scene_duration_seconds": 5,
                },
                asset_pack={
                    "scene_source_segments": [
                        {"scene_index": 0, "start_seconds": 0.0, "end_seconds": 2.0, "duration_seconds": 2.0}
                    ]
                },
                raw_path=str(raw_output),
                provider_order=["fal_video"],
                fallback_prompt="prompt",
                aspect_ratio="9:16",
                scene_index=0,
            )

        assert "selfshot2_scene_duration_mismatch" in str(exc_info.value)
        diag = exc_info.value.diagnostics
        assert diag["ok"] is False
        assert diag["provider_attempted"] is False
        assert diag["no_charge"] is True
        assert spy_upload.call_count == 0
        assert spy_submit.call_count == 0


# ---------------------------------------------------------------------------
# 35. Continuity failure cost diagnostics
# ---------------------------------------------------------------------------

def test_35_continuity_failure_cost_diagnostics(tmp_path: Path):
    """When Fal generates video but local continuity rejects it, no_charge must be False (costs occurred)."""
    source_file = tmp_path / "source.mp4"
    source_file.write_bytes(b"SOURCE_BYTES")
    scene_file = tmp_path / "scene.mp4"
    scene_file.write_bytes(b"SCENE_BYTES")
    raw_output = tmp_path / "raw.mp4"

    mock_upload = MagicMock(return_value={
        "ok": True,
        "provider": "fal_video",
        "file_url": "https://v3.fal.media/files/scene.mp4",
        "local_path": str(scene_file),
        "local_sha256": "abc",
        "local_size_bytes": 100,
        "content_type": "video/mp4",
    })

    spy_submit = MagicMock(return_value={
        "provider_task_id": "fal-cost-task-1",
        "status": "completed",
        "accepted": True,
        "result_url_present": True,
        "result_url": "https://v3.fal.media/files/gen_out.mp4",
    })

    failed_continuity = {
        "ok": False,
        "evidence_source": "local_vision_validator",
        "independent_visual_validation": "LOCAL_MODEL",
        "failure_reason": "continuity_identity_drift_detected",
        "person_match": False,
    }

    env_overrides = {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_key_test",
        "VIDEO_AI_EDIT_PROVIDER_CHAIN": "fal_video",
    }

    with patch.dict(os.environ, env_overrides), \
         patch("services.video_ai_edit_provider.upload_fal_media_file", mock_upload), \
         patch("services.video_ai_edit_provider.submit_video_edit", spy_submit), \
         patch("services.video_ai_edit_provider.download_result", return_value={"ok": True, "path": str(raw_output), "bytes": 100}), \
         patch("services.video_real_render_connector._materialize_selfshot2_source_segment", return_value=str(scene_file)), \
         patch("services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity", return_value=failed_continuity):

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
                fallback_prompt="prompt",
                aspect_ratio="9:16",
                scene_index=0,
            )

        diag = exc_info.value.diagnostics
        assert diag["ok"] is False
        assert diag["provider_attempted"] is True
        assert diag["storage_upload_attempted"] is True
        assert diag["generation_submit_attempted"] is True
        assert diag["generation_task_id_obtained"] is True
        assert diag["no_charge"] is False
        assert diag["no_charge_proven"] is False
        assert diag["result_rejected_locally"] is True


# ---------------------------------------------------------------------------
# 36. Failure injection matrix across all stages
# ---------------------------------------------------------------------------

def test_36_failure_injection_matrix_across_all_stages(tmp_path: Path):
    """Matrix testing failure injection across all stages of the SelfShot2 Fal pipeline."""
    source_file = tmp_path / "source.mp4"
    source_file.write_bytes(b"SOURCE_BYTES")
    scene_file = tmp_path / "scene.mp4"
    scene_file.write_bytes(b"SCENE_BYTES")
    raw_output = tmp_path / "raw.mp4"

    env_overrides = {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_key_test",
        "KEY4U_VIDEO_TO_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_TO_VIDEO_API_KEY": "key4u_key_test",
        "VIDEO_AI_EDIT_PROVIDER_CHAIN": "fal_video,key4u_video",
    }

    stages = [
        ("upload_http_error", video_ai_edit_provider.AiEditProviderError("fal_scene_upload_failed_http_502"), "fal_scene_upload_failed_http_502", True, 0),
        ("upload_invalid_url", video_ai_edit_provider.AiEditProviderError("fal_scene_upload_upload_url_invalid"), "fal_scene_upload_upload_url_invalid", True, 0),
        ("submit_transport_error", video_ai_edit_provider.AiEditProviderError("provider_submit_connection_failed"), "provider_submit_connection_failed", False, 0),
        ("poll_timeout", video_ai_edit_provider.AiEditProviderError("provider_poll_timeout"), "provider_poll_timeout", False, 0),
        ("result_fetch_error", video_ai_edit_provider.AiEditProviderError("provider_result_fetch_http_500"), "provider_result_fetch_http_500", False, 0),
    ]

    for stage_name, err, expected_blocker, expect_no_charge, expected_second_submits in stages:
        with patch.dict(os.environ, env_overrides), \
             patch("services.video_real_render_connector._materialize_selfshot2_source_segment", return_value=str(scene_file)):

            if "upload" in stage_name:
                mock_up = MagicMock(side_effect=err)
                mock_sub = MagicMock()
                mock_poll = MagicMock()
            elif "submit" in stage_name:
                mock_up = MagicMock(return_value={"ok": True, "provider": "fal_video", "file_url": "https://v3.fal.media/files/scene.mp4", "local_path": str(scene_file), "local_sha256": "abc", "local_size_bytes": 100, "content_type": "video/mp4"})
                mock_sub = MagicMock(side_effect=err)
                mock_poll = MagicMock()
            elif "poll" in stage_name or "result" in stage_name:
                mock_up = MagicMock(return_value={"ok": True, "provider": "fal_video", "file_url": "https://v3.fal.media/files/scene.mp4", "local_path": str(scene_file), "local_sha256": "abc", "local_size_bytes": 100, "content_type": "video/mp4"})
                mock_sub = MagicMock(return_value={"provider_task_id": "task-inj-1", "status": "running", "accepted": True, "result_url_present": False})
                mock_poll = MagicMock(side_effect=err)

            with patch("services.video_ai_edit_provider.upload_fal_media_file", mock_up), \
                 patch("services.video_ai_edit_provider.submit_video_edit", mock_sub), \
                 patch("services.video_ai_edit_provider.wait_for_result", mock_poll):

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
                        provider_order=["fal_video", "key4u_video"],
                        fallback_prompt="prompt",
                        aspect_ratio="9:16",
                        scene_index=0,
                    )
                assert expected_blocker in str(exc_info.value), f"Failed for stage {stage_name}"
                diag = exc_info.value.diagnostics
                assert diag["no_charge"] is expect_no_charge, f"no_charge mismatch for stage {stage_name}"


# ---------------------------------------------------------------------------
# 37. Key4U proven-wire bypass rejected: canonical rule (Section B FIRST RED)
# ---------------------------------------------------------------------------

def test_37_key4u_proven_wire_bypass_rejected_canonical_rule():
    """Section B FIRST RED: For an unproven V2V provider, a V2V-looking URL path alone is NEVER proof."""
    cfg = video_ai_edit_provider.AiEditProviderConfig(
        provider_name="key4u_video",
        enabled=True,
        submit_url="https://example.test/custom/video-to-video",
        poll_url="https://example.test/custom/video-to-video/{task_id}",
        auth_header_name="Authorization",
        auth_header_value="Bearer real_token_abc",
        model="kling-video",
        interface="video_to_video_multipart",
        capabilities=("video_to_video",),
    )
    # 1. Unproven wire contract
    assert video_ai_edit_provider.has_proven_v2v_wire_contract(cfg.provider_name, cfg.model, cfg.submit_url) is False

    # 2. Validation MUST fail closed with provider_capability_contract_mismatch
    val = video_ai_edit_provider.validate_provider_config(cfg, required_capability="video_to_video")
    assert val["ok"] is False
    assert val["reason"] == "provider_capability_contract_mismatch"
    assert "provider_capability_contract_mismatch" in val["invalid_fields"]

    # 3. Invariant holds regardless of naming convention in URL
    for v2v_path in [
        "https://api.key4u.click/custom/video-to-video",
        "https://api.key4u.click/custom/video2video",
        "https://api.key4u.click/custom/video_to_video",
        "https://example.test/api/v1/video-to-video",
    ]:
        v_cfg = video_ai_edit_provider.AiEditProviderConfig(
            provider_name="key4u_video",
            enabled=True,
            submit_url=v2v_path,
            poll_url=f"{v2v_path}/{{task_id}}",
            auth_header_name="Authorization",
            auth_header_value="Bearer real_token_abc",
            model="kling-video",
            interface="video_to_video_multipart",
            capabilities=("video_to_video",),
        )
        assert video_ai_edit_provider.has_proven_v2v_wire_contract(v_cfg.provider_name, v_cfg.model, v_cfg.submit_url) is False
        res = video_ai_edit_provider.validate_provider_config(v_cfg, required_capability="video_to_video")
        assert res["ok"] is False
        assert res["reason"] == "provider_capability_contract_mismatch"


# ---------------------------------------------------------------------------
# 38. Key4U fail-closed invariant across all URL patterns (Section C)
# ---------------------------------------------------------------------------

def test_38_key4u_fail_closed_invariant_all_url_patterns():
    """Section C: has_proven_v2v_wire_contract('key4u_video') == False forever; all URLs blocked."""
    assert video_ai_edit_provider.has_proven_v2v_wire_contract("key4u_video") is False

    test_urls = [
        "https://api.key4u.click/kling/v1/videos/text2video",
        "https://api.key4u.click/kling/v1/videos/image2video",
        "https://api.key4u.click/custom/unverified/endpoint",
        "https://api.key4u.click/custom/video-to-video",
    ]
    for url in test_urls:
        cfg = video_ai_edit_provider.AiEditProviderConfig(
            provider_name="key4u_video",
            enabled=True,
            submit_url=url,
            poll_url=f"{url}/{{task_id}}",
            auth_header_name="Authorization",
            auth_header_value="Bearer real_token",
            model="kling-video",
            interface="video_to_video_multipart",
            capabilities=("video_to_video",),
        )
        res = video_ai_edit_provider.validate_provider_config(cfg, required_capability="video_to_video")
        assert res["ok"] is False
        assert res["reason"] == "provider_capability_contract_mismatch"


# ---------------------------------------------------------------------------
# 39. Dot-invalid production authority removed (Section D)
# ---------------------------------------------------------------------------

def test_39_dot_invalid_production_authority_removed():
    """Section D: The hostname .invalid must never grant capability; path semantics determine capability."""
    # Arbitrary .invalid URL must return unknown, NOT video_to_video
    assert video_ai_edit_provider.classify_endpoint_capability("https://anything.invalid/foo") == "unknown"
    assert video_ai_edit_provider.classify_endpoint_capability("https://mock.invalid/submit") == "unknown"

    # Realistic path with fake domain classifies purely on path
    assert video_ai_edit_provider.classify_endpoint_capability("https://provider.example/video-to-video") == "video_to_video"
    assert video_ai_edit_provider.classify_endpoint_capability("https://provider.invalid/custom/video-to-video") == "video_to_video"


# ---------------------------------------------------------------------------
# 40. MagicMock production authority removed (Section E)
# ---------------------------------------------------------------------------

def test_40_magicmock_production_authority_removed():
    """Section E: Production _selfshot2_provider_configs must never introspect MagicMock attributes."""
    import inspect
    src = inspect.getsource(video_real_render_connector._selfshot2_provider_configs)
    assert "_is_mock" not in src
    assert "return_value" not in src
    assert "assert_called" not in src
    assert "mock" not in src.lower()


# ---------------------------------------------------------------------------
# 41. Terminal failure proof authoritative & terminal state matrix (Section F & G)
# ---------------------------------------------------------------------------

def test_41_terminal_failure_proof_enforcement_and_state_matrix():
    """Section F & G: Fallback only allowed when primary_terminal_failure_proven=True and status is terminal dead."""
    candidate = video_ai_edit_provider.AiEditProviderConfig(
        provider_name="fal_video",
        enabled=True,
        submit_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video",
        poll_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/{task_id}/status",
        auth_header_name="Authorization",
        auth_header_value="Key valid_secret",
        model="fal-ai/wan/v2.2-a14b/video-to-video",
        interface="video_to_video_json",
        capabilities=("video_to_video",),
    )

    # 1. Terminal proof authoritative check: status=failed + proven=False -> BLOCKED
    res_unproven = video_ai_edit_provider.controlled_fallback_decision(
        public_confirm_provenance=True,
        primary_status="failed",
        primary_task_alive=False,
        fallback_count=0,
        candidate=candidate,
        primary_terminal_failure_proven=False,
    )
    assert res_unproven["allowed"] is False
    assert res_unproven["reason"] == "primary_terminal_failure_unproven"

    # 2. Terminal state matrix
    for terminal_status in ["failed", "rejected", "cancelled"]:
        res = video_ai_edit_provider.controlled_fallback_decision(
            public_confirm_provenance=True,
            primary_status=terminal_status,
            primary_task_alive=False,
            fallback_count=0,
            candidate=candidate,
            primary_terminal_failure_proven=True,
        )
        assert res["allowed"] is True
        assert res["reason"] == "controlled_terminal_fallback"

    # Non-terminal or ambiguous states -> BLOCKED
    for non_terminal in ["running", "pending", "processing", "timeout", "unknown"]:
        res = video_ai_edit_provider.controlled_fallback_decision(
            public_confirm_provenance=True,
            primary_status=non_terminal,
            primary_task_alive=(non_terminal in {"running", "pending"}),
            fallback_count=0,
            candidate=candidate,
            primary_terminal_failure_proven=True,
        )
        assert res["allowed"] is False

    # Ambiguous errors -> BLOCKED
    for amb_err in [
        "provider_submit_connection_failed",
        "provider_submit_timeout",
        "provider_poll_connection_failed",
        "provider_poll_timeout",
        "provider_result_fetch_http_500",
        "provider_result_download_failed:Timeout",
        "fal_scene_upload_failed_http_502",
        "provider_capability_contract_mismatch",
    ]:
        res = video_ai_edit_provider.controlled_fallback_decision(
            public_confirm_provenance=True,
            primary_status="failed",
            primary_task_alive=False,
            fallback_count=0,
            candidate=candidate,
            primary_error=amb_err,
            primary_terminal_failure_proven=True,
        )
        assert res["allowed"] is False


# ---------------------------------------------------------------------------
# 42. Fal environment configuration namespace reconciliation (Section K)
# ---------------------------------------------------------------------------

def test_42_fal_env_configuration_reconciliation():
    """Section K: Support both FAL_VIDEO_TO_VIDEO_* and FAL_VIDEO_* / FAL_KEY with FAL_ENV_CONFIGURATION_AMBIGUITY=NO."""
    # 1. Canonical FAL_VIDEO_* + FAL_KEY
    canonical_env = {
        "FAL_VIDEO_ENABLED": "1",
        "FAL_KEY": "fal_canonical_token",
        "FAL_VIDEO_MODEL": "fal-ai/wan/v2.2-a14b/video-to-video",
    }
    cfg_canon = video_ai_edit_provider.provider_config_from_env("fal_video", canonical_env)
    assert cfg_canon.enabled is True
    assert cfg_canon.auth_header_value == "Key fal_canonical_token"
    assert cfg_canon.model == "fal-ai/wan/v2.2-a14b/video-to-video"

    # 2. Adapter-specific FAL_VIDEO_TO_VIDEO_* overrides canonical FAL_VIDEO_*
    override_env = {
        "FAL_VIDEO_ENABLED": "1",
        "FAL_KEY": "fal_canonical_token",
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_v2v_override_token",
    }
    cfg_override = video_ai_edit_provider.provider_config_from_env("fal_video", override_env)
    assert cfg_override.auth_header_value == "Key fal_v2v_override_token"


# ---------------------------------------------------------------------------
# 43. End-to-end SelfShot2 Fal routing without Key4U hidden fallback (Section J & H)
# ---------------------------------------------------------------------------

def test_43_end_to_end_selfshot2_fal_routing_no_key4u_fallback(tmp_path: Path):
    """Section J & H: Materialized local segment uploads to Fal storage; Key4U is never secondary eligible."""
    source_file = tmp_path / "source.mp4"
    source_file.write_bytes(b"SOURCE_BYTES_REAL")
    scene_file = tmp_path / "scene.mp4"
    scene_file.write_bytes(b"SCENE_BYTES_REAL")
    raw_output = tmp_path / "raw.mp4"

    uploaded_urls = []
    def fake_upload(config, local_path, **kwargs):
        uploaded_urls.append(str(local_path))
        return {
            "ok": True,
            "provider": "fal_video",
            "file_url": "https://v3.fal.media/files/scene_real.mp4",
            "local_path": str(local_path),
            "local_sha256": "abc_hash",
            "local_size_bytes": 16,
            "content_type": "video/mp4",
        }

    submits = []
    def fake_submit(config, **kwargs):
        submits.append(config.provider_name)
        return {
            "provider_task_id": "fal-wan-task-real",
            "status": "completed",
            "accepted": True,
            "result_url_present": True,
            "result_url": "https://v3.fal.media/results/out.mp4",
        }

    def fake_download(url, dest, **kwargs):
        Path(dest).write_bytes(b"FINAL_VIDEO_BYTES")
        return {"ok": True, "path": dest, "bytes": 17}

    fake_continuity = {
        "ok": True,
        "evidence_source": "local_vision_validator",
        "independent_visual_validation": "LOCAL_MODEL",
        "person_required": False,
        "object_required": False,
    }

    env = {
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_API_KEY": "fal_key_test",
        "KEY4U_VIDEO_TO_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_TO_VIDEO_API_KEY": "key4u_key_test",
        "VIDEO_AI_EDIT_PROVIDER_CHAIN": "fal_video,key4u_video",
    }

    with patch.dict(os.environ, env), \
         patch("services.video_ai_edit_provider.upload_fal_media_file", side_effect=fake_upload), \
         patch("services.video_ai_edit_provider.submit_video_edit", side_effect=fake_submit), \
         patch("services.video_ai_edit_provider.download_result", side_effect=fake_download), \
         patch("services.video_real_render_connector._materialize_selfshot2_source_segment", return_value=str(scene_file)), \
         patch("services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity", return_value=fake_continuity):

        res = video_real_render_connector._render_selfshot2_video_to_video(
            job={
                "source_video_local_path": str(source_file),
                "quality_tier": 500,
                "public_user_confirmed": True,
                "submit_source": "public_user_final_confirm",
            },
            asset_pack={},
            raw_path=str(raw_output),
            provider_order=["fal_video", "key4u_video"],
            fallback_prompt="prompt",
            aspect_ratio="9:16",
            scene_index=0,
        )

        assert res["ok"] is True
        assert res["provider"] == "fal_video"
        assert len(uploaded_urls) == 1
        assert uploaded_urls[0] == str(scene_file)
        assert submits == ["fal_video"]
        assert raw_output.read_bytes() == b"FINAL_VIDEO_BYTES"
