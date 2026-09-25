"""Provider-free tests for SelfShot2 & SelfShot3 Controlled Keyframe Image-to-Video Source Closure.

Scope: P0.PRODUCT_VIDEO
Primary Source Route: key4u_video
Authorized Scope: SELFSHOT2_AND_SELFSHOT3_CONTROLLED_KEYFRAME_IMAGE_TO_VIDEO_PROVIDER_FREE_SOURCE_CLOSURE

Zero external provider calls made. All network I/O isolated via mocks.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from services import (
    video_ai_edit_provider,
    video_provider_router,
    video_real_render_connector,
    video_selfshot2,
    video_selfshot3,
    video_tail9,
)
from services.video_provider_base import VideoGenerationRequest
from services.video_real_render_connector import RealVideoRenderError


# ---------------------------------------------------------------------------
# 1. SelfShot2 Capability Route: controlled_keyframe_image_to_video
# ---------------------------------------------------------------------------

def test_1_selfshot2_capability_route_controlled_keyframe_i2v():
    """SelfShot2 returns controlled_keyframe_image_to_video when I2V is available and keyframes are ready."""
    route = video_selfshot2.capability_route(
        capabilities={"image_to_video"},
        subject_manifest={"person_subject_ids": ["person-1"]},
        direction={"required_capabilities": ["environment_replacement"]},
        reference_keyframes_ready=True,
    )
    assert route["ok"] is True
    assert route["route"] == "controlled_keyframe_image_to_video"
    assert route["truth"] == "image_to_video_fallback_not_direct_v2v"
    assert route["continuity_validation_required"] is True


def test_2_selfshot2_capability_route_fails_when_keyframes_not_ready():
    """SelfShot2 fails closed before invoice when I2V is available but keyframes are NOT ready."""
    route = video_selfshot2.capability_route(
        capabilities={"image_to_video"},
        subject_manifest={"person_subject_ids": ["person-1"]},
        direction={"required_capabilities": ["environment_replacement"]},
        reference_keyframes_ready=False,
    )
    assert route["ok"] is False
    assert route["blocker"] == "selfshot2_required_capability_unavailable"


# ---------------------------------------------------------------------------
# 2. SelfShot3 Capability Route: controlled_keyframe_image_to_video
# ---------------------------------------------------------------------------

def test_3_selfshot3_capability_route_controlled_keyframe_i2v():
    """SelfShot3 returns controlled_keyframe_image_to_video when image_to_video capability is available."""
    route = video_selfshot3.capability_route(
        {"image_to_video"},
        mode=video_selfshot3.MODE_ONE_TAKE,
    )
    assert route["ok"] is True
    assert route["route"] == "controlled_keyframe_image_to_video"
    assert route["truthful_fallback"] is True
    assert "continuity_validation_required" in route["limitations"]
    assert "not_direct_video_to_video" in route["limitations"]


def test_4_selfshot3_capability_route_direct_v2v_takes_precedence():
    """Direct V2V takes precedence over keyframe fallback when direct capability is available."""
    route = video_selfshot3.capability_route(
        {"video_to_video", "image_to_video"},
        mode=video_selfshot3.MODE_ONE_TAKE,
    )
    assert route["ok"] is True
    assert route["route"] == "direct_video_to_video"
    assert route["truthful_fallback"] is False


# ---------------------------------------------------------------------------
# 3. Router Gate: Text-to-Video FORBIDDEN, Controlled Keyframe I2V Allowed
# ---------------------------------------------------------------------------

def test_5_router_blocks_text_to_video_for_selfshot2():
    """Router blocks text-to-video for self_shot_scene_change with selfshot2_text_to_video_route_forbidden."""
    req = VideoGenerationRequest(
        job_id="test-router-ss2-t2v",
        product_type="self_shot_scene_change",
        required_capability="text_to_video",
    )
    result = video_provider_router.run_provider_generation(req, output_dir="/tmp")
    assert result["ok"] is False
    assert result["blocker"] == "selfshot2_text_to_video_route_forbidden"
    assert result["provider_attempted"] is False
    assert result["external_provider_spend_prevented"] is True


def test_6_router_blocks_text_to_video_for_selfshot3():
    """Router blocks text-to-video for self_shot_cinematic_transform with selfshot2_text_to_video_route_forbidden."""
    req = VideoGenerationRequest(
        job_id="test-router-ss3-t2v",
        product_type="self_shot_cinematic_transform",
        required_capability="text_to_video",
    )
    result = video_provider_router.run_provider_generation(req, output_dir="/tmp")
    assert result["ok"] is False
    assert result["blocker"] == "selfshot2_text_to_video_route_forbidden"
    assert result["provider_attempted"] is False
    assert result["external_provider_spend_prevented"] is True


def test_7_router_blocks_i2v_when_keyframe_missing():
    """Router blocks image_to_video for SelfShot when image_paths is empty with selfshot_keyframe_missing."""
    req = VideoGenerationRequest(
        job_id="test-router-ss-missing-kf",
        product_type="self_shot_scene_change",
        required_capability="image_to_video",
        image_paths=[],
    )
    result = video_provider_router.run_provider_generation(req, output_dir="/tmp")
    assert result["ok"] is False
    assert result["blocker"] == "selfshot_keyframe_missing"
    assert result["provider_attempted"] is False


# ---------------------------------------------------------------------------
# 4. Keyframe Extraction & Safe Run
# ---------------------------------------------------------------------------

def test_8_extract_selfshot_keyframe_success(tmp_path: Path):
    """Keyframe extraction calls ffmpeg with exact single frame extraction parameters."""
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"DUMMY_SOURCE_VIDEO")
    raw_video = tmp_path / "raw.mp4"
    raw_video.write_bytes(b"DUMMY_RAW")

    mock_proc = MagicMock()
    mock_proc.returncode = 0

    def fake_ffmpeg(cmd, timeout=30):
        # Create output file
        out_target = Path(cmd[-1])
        out_target.write_bytes(b"DUMMY_KEYFRAME_IMAGE_BYTES")
        return mock_proc

    with patch("services.video_real_render_connector._ffmpeg_binary", return_value="ffmpeg"), \
         patch("services.video_real_render_connector.safe_run_ffmpeg", side_effect=fake_ffmpeg) as mock_ffmpeg:
        kf_path = video_real_render_connector._extract_selfshot_keyframe(
            str(source_video),
            str(raw_video),
            scene_index=1,
            timestamp_seconds=2.5,
            prefix="selfshot2",
        )
        assert os.path.isfile(kf_path)
        assert kf_path.endswith("selfshot2-keyframe-scene-01.jpg")
        cmd_called = mock_ffmpeg.call_args[0][0]
        assert "-ss" in cmd_called
        assert "2.500" in cmd_called
        assert "-frames:v" in cmd_called
        assert "1" in cmd_called


def test_9_extract_selfshot_keyframe_failure_fails_closed(tmp_path: Path):
    """Keyframe extraction failure raises RealVideoRenderError and prevents provider submit."""
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"DUMMY_SOURCE_VIDEO")
    raw_video = tmp_path / "raw.mp4"

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "ffmpeg error"

    with patch("services.video_real_render_connector._ffmpeg_binary", return_value="ffmpeg"), \
         patch("services.video_real_render_connector.safe_run_ffmpeg", return_value=mock_proc):
        with pytest.raises(RealVideoRenderError) as exc_info:
            video_real_render_connector._extract_selfshot_keyframe(
                str(source_video),
                str(raw_video),
                scene_index=1,
                timestamp_seconds=0.0,
                prefix="selfshot2",
            )
        assert exc_info.value.diagnostics["blocker"] == "selfshot2_keyframe_extraction_failed"
        assert exc_info.value.diagnostics["no_charge"] is True
        assert exc_info.value.diagnostics["provider_attempted"] is False


# ---------------------------------------------------------------------------
# 5. SelfShot2 Controlled Keyframe Image-to-Video Execution
# ---------------------------------------------------------------------------

def test_10_selfshot2_controlled_keyframe_i2v_execution(tmp_path: Path):
    """SelfShot2 renders through controlled keyframe image-to-video with Key4U as primary route."""
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"VALID_SOURCE_MP4_BYTES")
    raw_path = str(tmp_path / "raw_scene_0.mp4")
    keyframe_file = tmp_path / "selfshot2-keyframe-scene-00.jpg"
    keyframe_file.write_bytes(b"KEYFRAME_BYTES")

    mock_gen_result = {
        "ok": True,
        "provider": "key4u_video",
        "model": "veo_3_1-fast",
        "provider_task_ids": ["task_key4u_i2v_001"],
        "provider_video_ids": [],
        "output_path": raw_path,
        "final_video_path": raw_path,
        "output_bytes": 1024,
    }

    with patch("services.video_real_render_connector._materialize_selfshot2_source_segment", return_value=str(source_video)), \
         patch("services.video_real_render_connector._extract_selfshot_keyframe", return_value=str(keyframe_file)), \
         patch("services.video_real_render_connector.run_provider_generation", return_value=mock_gen_result) as mock_gen:

        res = video_real_render_connector._render_selfshot2_video_to_video(
            job={
                "source_video_local_path": str(source_video),
                "quality_tier": 500,
                "public_user_confirmed": True,
                "submit_source": "public_user_final_confirm",
                "route": "controlled_keyframe_image_to_video",
            },
            asset_pack={
                "route": "controlled_keyframe_image_to_video",
                "public_user_confirmed": True,
                "submit_source": "public_user_final_confirm",
            },
            raw_path=raw_path,
            provider_order=["key4u_video", "shopaikey_video"],
            fallback_prompt="Cinematic city transformation",
            aspect_ratio="9:16",
            scene_index=0,
        )

        assert res["ok"] is True
        assert res["selfshot2"] is True
        assert res["route"] == "controlled_keyframe_image_to_video"
        assert res["truth"] == "image_to_video_fallback_not_direct_v2v"
        assert res["provider"] == "key4u_video"
        assert res["continuity_validation_required"] is True

        # Verify request parameters passed to run_provider_generation
        assert mock_gen.call_count == 1
        gen_req = mock_gen.call_args[0][0]
        assert gen_req.required_capability == "image_to_video"
        assert gen_req.image_paths == [str(keyframe_file)]
        assert gen_req.product_type == "self_shot_scene_change"


# ---------------------------------------------------------------------------
# 6. SelfShot3 Controlled Keyframe Image-to-Video Execution
# ---------------------------------------------------------------------------

def test_11_selfshot3_controlled_keyframe_i2v_execution(tmp_path: Path):
    """SelfShot3 renders through controlled keyframe image-to-video with Key4U as primary route."""
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"VALID_SOURCE_MP4_SS3")
    raw_path = str(tmp_path / "raw_selfshot3.mp4")
    keyframe_file = tmp_path / "selfshot3-keyframe-scene-00.jpg"
    keyframe_file.write_bytes(b"KEYFRAME_BYTES_SS3")

    mock_gen_result = {
        "ok": True,
        "provider": "key4u_video",
        "model": "veo_3_1-fast",
        "provider_task_ids": ["task_key4u_ss3_001"],
        "provider_video_ids": [],
        "output_path": raw_path,
        "final_video_path": raw_path,
        "output_bytes": 2048,
    }

    with patch("services.video_real_render_connector._extract_selfshot_keyframe", return_value=str(keyframe_file)), \
         patch("services.video_real_render_connector.run_provider_generation", return_value=mock_gen_result) as mock_gen:

        res = video_real_render_connector._render_selfshot3_video_to_video(
            job={
                "source_video_local_path": str(source_video),
                "public_user_confirmed": True,
                "submit_source": "public_user_final_confirm",
                "route": "controlled_keyframe_image_to_video",
            },
            asset_pack={
                "route": "controlled_keyframe_image_to_video",
                "public_user_confirmed": True,
                "submit_source": "public_user_final_confirm",
                "duration_seconds": 8,
            },
            raw_path=raw_path,
            provider_order=["key4u_video", "shopaikey_video"],
            fallback_prompt="One-take fantasy transformation",
            aspect_ratio="9:16",
        )

        assert res["ok"] is True
        assert res["selfshot3"] is True
        assert res["route"] == "controlled_keyframe_image_to_video"
        assert res["truth"] == "image_to_video_fallback_not_direct_v2v"
        assert res["provider"] == "key4u_video"
        assert res["continuity_validation_required"] is True

        assert mock_gen.call_count == 1
        gen_req = mock_gen.call_args[0][0]
        assert gen_req.required_capability == "image_to_video"
        assert gen_req.image_paths == [str(keyframe_file)]
        assert gen_req.product_type == "self_shot_cinematic_transform"


# ---------------------------------------------------------------------------
# 7. Fail-Closed Security & Integrity Gates
# ---------------------------------------------------------------------------

def test_12_selfshot2_unconfirmed_fails_closed(tmp_path: Path):
    """SelfShot2 fails closed when public user confirmation is missing (no provider call)."""
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"VALID_SOURCE")
    with pytest.raises(RealVideoRenderError) as exc_info:
        video_real_render_connector._render_selfshot2_video_to_video(
            job={"source_video_local_path": str(source_video)},
            asset_pack={"route": "controlled_keyframe_image_to_video"},
            raw_path=str(tmp_path / "raw.mp4"),
            provider_order=["key4u_video"],
            fallback_prompt="prompt",
            aspect_ratio="9:16",
            scene_index=0,
        )
    assert exc_info.value.diagnostics["blocker"] == "selfshot2_public_confirm_required"
    assert exc_info.value.diagnostics["no_charge"] is True
    assert exc_info.value.diagnostics["provider_attempted"] is False


def test_13_selfshot3_unconfirmed_fails_closed(tmp_path: Path):
    """SelfShot3 fails closed when public user confirmation is missing (no provider call)."""
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"VALID_SOURCE")
    with pytest.raises(RealVideoRenderError) as exc_info:
        video_real_render_connector._render_selfshot3_video_to_video(
            job={"source_video_local_path": str(source_video)},
            asset_pack={"route": "controlled_keyframe_image_to_video"},
            raw_path=str(tmp_path / "raw.mp4"),
            provider_order=["key4u_video"],
            fallback_prompt="prompt",
            aspect_ratio="9:16",
        )
    assert exc_info.value.diagnostics["blocker"] == "selfshot3_public_confirm_required"
    assert exc_info.value.diagnostics["no_charge"] is True
    assert exc_info.value.diagnostics["provider_attempted"] is False


def test_14_selfshot2_missing_source_fails_closed(tmp_path: Path):
    """SelfShot2 fails closed when source video file does not exist (no provider call)."""
    with pytest.raises(RealVideoRenderError) as exc_info:
        video_real_render_connector._render_selfshot2_video_to_video(
            job={"source_video_local_path": str(tmp_path / "nonexistent.mp4")},
            asset_pack={"route": "controlled_keyframe_image_to_video", "public_user_confirmed": True, "submit_source": "public_user_final_confirm"},
            raw_path=str(tmp_path / "raw.mp4"),
            provider_order=["key4u_video"],
            fallback_prompt="prompt",
            aspect_ratio="9:16",
            scene_index=0,
        )
    assert exc_info.value.diagnostics["blocker"] == "selfshot2_source_video_not_materialized"
    assert exc_info.value.diagnostics["no_charge"] is True


def test_15_selfshot3_missing_source_fails_closed(tmp_path: Path):
    """SelfShot3 fails closed when source video file does not exist (no provider call)."""
    with pytest.raises(RealVideoRenderError) as exc_info:
        video_real_render_connector._render_selfshot3_video_to_video(
            job={"source_video_local_path": str(tmp_path / "nonexistent.mp4")},
            asset_pack={"route": "controlled_keyframe_image_to_video", "public_user_confirmed": True, "submit_source": "public_user_final_confirm"},
            raw_path=str(tmp_path / "raw.mp4"),
            provider_order=["key4u_video"],
            fallback_prompt="prompt",
            aspect_ratio="9:16",
        )
    assert exc_info.value.diagnostics["blocker"] == "selfshot3_source_video_not_materialized"
    assert exc_info.value.diagnostics["no_charge"] is True


# ---------------------------------------------------------------------------
# 8. Commercial Contract Fallback Capabilities
# ---------------------------------------------------------------------------

def test_16_commercial_contracts_document_i2v_fallback():
    """video_tail9 commercial contracts document controlled keyframe I2V as approved fallback capabilities."""
    c2 = video_tail9.commercial_contract("self_shot_scene_change")
    assert "controlled_keyframe_image_to_video" in c2["fallback_capabilities"]
    assert "image_to_video" in c2["fallback_capabilities"]

    c3 = video_tail9.commercial_contract("self_shot_cinematic_transform")
    assert "controlled_keyframe_image_to_video" in c3["fallback_capabilities"]
    assert "image_to_video" in c3["fallback_capabilities"]
