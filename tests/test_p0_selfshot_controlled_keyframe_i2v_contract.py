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

    mock_continuity = {
        "ok": True,
        "blocker": "",
        "evidence_source": "local_vision_validator",
        "independent_visual_validation": "LOCAL_MODEL",
        "person_required": True,
        "object_required": False,
        "person_identity": True,
        "object_identity": False,
        "person_object_relationship": False,
    }

    with patch("services.video_real_render_connector._materialize_selfshot2_source_segment", return_value=str(source_video)), \
         patch("services.video_real_render_connector._extract_selfshot_keyframe", return_value=str(keyframe_file)), \
         patch("services.video_real_render_connector.run_provider_generation", return_value=mock_gen_result) as mock_gen, \
         patch("services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity", return_value=mock_continuity):

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
        assert res["continuity_validation_passed"] is True
        assert res["continuity_evidence"]["person_identity"] is True
        assert res["continuity_evidence"]["evidence_source"] == "local_vision_validator"
        assert res["continuity_evidence"]["independent_visual_validation"] == "LOCAL_MODEL"

        # Verify request parameters passed to run_provider_generation
        assert mock_gen.call_count == 1
        gen_req = mock_gen.call_args[0][0]
        assert gen_req.required_capability == "image_to_video"
        assert gen_req.image_paths == [str(keyframe_file)]
        assert gen_req.product_type == "self_shot_scene_change"
        assert gen_req.metadata["model_name"] == "kling-v3"


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
        "continuity_scores": {
            "identity": 0.95,
            "body": 0.95,
            "motion": 0.95,
            "object": 0.95,
            "interaction": 0.95,
            "temporal": 0.95,
        },
    }

    mock_continuity = {
        "ok": True,
        "blocker": "",
        "evidence_source": "local_vision_validator",
        "independent_visual_validation": "LOCAL_MODEL",
        "person_required": True,
        "object_required": False,
        "relationship_required": False,
        "person_identity": True,
        "object_identity": True,
        "person_object_relationship": True,
    }

    with patch("services.video_real_render_connector._extract_selfshot_keyframe", return_value=str(keyframe_file)), \
         patch("services.video_real_render_connector.run_provider_generation", return_value=mock_gen_result) as mock_gen, \
         patch("services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity", return_value=mock_continuity):

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
        assert res["model"] == "kling-v3"
        assert res["continuity_validation_required"] is True
        assert res["continuity_validation_passed"] is True
        assert res["evidence_source"] == "local_vision_validator"
        assert res["independent_visual_validation"] == "LOCAL_MODEL"
        assert res["continuity_scores"]["identity"] >= 0.8

        assert mock_gen.call_count == 1
        gen_req = mock_gen.call_args[0][0]
        assert gen_req.required_capability == "image_to_video"
        assert gen_req.image_paths == [str(keyframe_file)]
        assert gen_req.product_type == "self_shot_cinematic_transform"
        assert gen_req.metadata["model_name"] == "kling-v3"


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


# ---------------------------------------------------------------------------
# 9. Key4U Wire Model Pinning & SelfShot Continuity Closure
# ---------------------------------------------------------------------------

def test_17_key4u_i2v_wire_model_pinning_resolves_model(tmp_path: Path):
    """Key4U I2V wire payload resolves pinned model (kling-v3) without mapping gap."""
    from providers import video_generic_http_provider as vgp

    img = tmp_path / "keyframe.png"
    img.write_bytes(b"DUMMY_IMAGE")

    # When model is pinned to kling-v3 on payload, it correctly serializes to wire
    payload = {
        "model": "kling-v3",
        "image": str(img),
        "prompt": "Test pinned model",
        "aspect_ratio": "9:16",
        "duration": 5,
        "metadata": {
            "selected_family": "kling",
            "required_capability": "image_to_video",
        },
    }
    wire = vgp._key4u_wire_payload(payload, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
    assert wire["model_name"] == "kling-v3"
    assert wire["aspect_ratio"] == "9:16"
    assert wire["duration"] == 5


def test_18_key4u_i2v_wire_model_pinning_in_selfshot2_connector(tmp_path: Path):
    """SelfShot2 controlled keyframe I2V pins Key4U model and passes continuity evidence."""
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"VALID_SOURCE")
    raw_path = str(tmp_path / "raw.mp4")
    keyframe = tmp_path / "kf.jpg"
    keyframe.write_bytes(b"KEYFRAME")

    mock_gen = {
        "ok": True,
        "provider": "key4u_video",
        "model": "kling-v3",
        "provider_task_ids": ["task-1"],
        "final_video_path": raw_path,
        "output_path": raw_path,
        "output_bytes": 1000,
    }

    mock_continuity = {
        "ok": True,
        "blocker": "",
        "evidence_source": "local_vision_validator",
        "independent_visual_validation": "LOCAL_MODEL",
        "person_required": True,
        "object_required": True,
        "relationship_required": True,
        "person_identity": True,
        "object_identity": True,
        "person_object_relationship": True,
    }

    with patch("services.video_real_render_connector._materialize_selfshot2_source_segment", return_value=str(source_video)), \
         patch("services.video_real_render_connector._extract_selfshot_keyframe", return_value=str(keyframe)), \
         patch("services.video_real_render_connector.run_provider_generation", return_value=mock_gen) as mock_run, \
         patch("services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity", return_value=mock_continuity):

        res = video_real_render_connector._render_selfshot2_video_to_video(
            job={"source_video_local_path": str(source_video), "public_user_confirmed": True, "submit_source": "public_user_final_confirm", "route": "controlled_keyframe_image_to_video"},
            asset_pack={"route": "controlled_keyframe_image_to_video", "public_user_confirmed": True, "submit_source": "public_user_final_confirm"},
            raw_path=raw_path,
            provider_order=["key4u_video"],
            fallback_prompt="test",
            aspect_ratio="9:16",
            scene_index=0,
        )

        assert res["ok"] is True
        assert res["model"] == "kling-v3"
        assert res["continuity_validation_passed"] is True
        assert res["continuity_evidence"]["person_identity"] is True
        assert res["continuity_evidence"]["object_identity"] is True
        assert res["continuity_evidence"]["person_object_relationship"] is True
        assert res["continuity_evidence"]["evidence_source"] == "local_vision_validator"
        gen_req = mock_run.call_args[0][0]
        assert gen_req.metadata["model"] == "kling-v3"
        assert gen_req.metadata["model_name"] == "kling-v3"


def test_19_key4u_i2v_wire_model_pinning_in_selfshot3_connector(tmp_path: Path):
    """SelfShot3 controlled keyframe I2V pins Key4U model and passes continuity scores."""
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"VALID_SOURCE")
    raw_path = str(tmp_path / "raw.mp4")
    keyframe = tmp_path / "kf.jpg"
    keyframe.write_bytes(b"KEYFRAME")

    mock_gen = {
        "ok": True,
        "provider": "key4u_video",
        "model": "kling-v3",
        "provider_task_ids": ["task-1"],
        "final_video_path": raw_path,
        "output_path": raw_path,
        "output_bytes": 1000,
        "continuity_scores": {
            "identity": 0.95,
            "body": 0.95,
            "motion": 0.95,
            "object": 0.95,
            "interaction": 0.95,
            "temporal": 0.95,
        },
    }

    mock_continuity = {
        "ok": True,
        "blocker": "",
        "evidence_source": "local_vision_validator",
        "independent_visual_validation": "LOCAL_MODEL",
        "person_required": True,
        "object_required": True,
        "relationship_required": True,
        "person_identity": True,
        "object_identity": True,
        "person_object_relationship": True,
    }

    with patch("services.video_real_render_connector._extract_selfshot_keyframe", return_value=str(keyframe)), \
         patch("services.video_real_render_connector.run_provider_generation", return_value=mock_gen) as mock_run, \
         patch("services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity", return_value=mock_continuity):

        res = video_real_render_connector._render_selfshot3_video_to_video(
            job={"source_video_local_path": str(source_video), "public_user_confirmed": True, "submit_source": "public_user_final_confirm", "route": "controlled_keyframe_image_to_video"},
            asset_pack={"route": "controlled_keyframe_image_to_video", "public_user_confirmed": True, "submit_source": "public_user_final_confirm", "duration_seconds": 8},
            raw_path=raw_path,
            provider_order=["key4u_video"],
            fallback_prompt="test",
            aspect_ratio="9:16",
        )

        assert res["ok"] is True
        assert res["model"] == "kling-v3"
        assert res["continuity_validation_passed"] is True
        assert res["evidence_source"] == "local_vision_validator"
        assert res["independent_visual_validation"] == "LOCAL_MODEL"
        for layer in ("identity", "body", "motion", "object", "interaction", "temporal"):
            assert res["continuity_scores"][layer] >= 0.8
        gen_req = mock_run.call_args[0][0]
        assert gen_req.metadata["model"] == "kling-v3"
        assert gen_req.metadata["model_name"] == "kling-v3"


def test_20_selfshot3_continuity_validation_success(tmp_path: Path):
    """selfshot3_continuity_validation passes when final MP4 exists and scores are above threshold."""
    final_mp4 = tmp_path / "final.mp4"
    final_mp4.write_bytes(b"VALID_FINAL_MP4_CONTENT")

    val = video_real_render_connector.selfshot3_continuity_validation(
        job={"product_type": "self_shot_cinematic_transform"},
        result={
            "final_video_path": str(final_mp4),
            "evidence_source": "local_vision_validator",
            "independent_visual_validation": "LOCAL_MODEL",
            "continuity_scores": {
                "identity": 0.95,
                "body": 0.95,
                "motion": 0.95,
                "object": 0.95,
                "interaction": 0.95,
                "temporal": 0.95,
            },
        },
    )
    assert val["ok"] is True
    assert val["selfshot3"] is True
    assert val["blocker"] == ""
    assert val["final_mp4_valid"] is True
    assert val["continuity_validation_passed"] is True
    assert val["continuity_metadata_authority"] == "local_vision_validator"
    assert val["independent_visual_continuity_proven"] is True
    assert val["failures"] == []


def test_21_selfshot3_continuity_validation_degraded_scores_fails_closed(tmp_path: Path):
    """selfshot3_continuity_validation fails closed when identity score falls below threshold."""
    final_mp4 = tmp_path / "final.mp4"
    final_mp4.write_bytes(b"VALID_FINAL_MP4_CONTENT")

    val = video_real_render_connector.selfshot3_continuity_validation(
        job={"product_type": "self_shot_cinematic_transform"},
        result={
            "final_video_path": str(final_mp4),
            "evidence_source": "local_vision_validator",
            "independent_visual_validation": "LOCAL_MODEL",
            "continuity_scores": {
                "identity": 0.3,
                "body": 0.95,
                "motion": 0.95,
                "object": 0.95,
                "interaction": 0.95,
                "temporal": 0.95,
            },
        },
    )
    assert val["ok"] is False
    assert val["blocker"] == "selfshot3_continuity_validation_failed"
    assert "identity" in val["failures"]


def test_22_selfshot3_continuity_validation_missing_mp4_fails_closed(tmp_path: Path):
    """selfshot3_continuity_validation fails closed when final MP4 file is missing."""
    val = video_real_render_connector.selfshot3_continuity_validation(
        job={"product_type": "self_shot_cinematic_transform"},
        result={
            "final_video_path": str(tmp_path / "nonexistent.mp4"),
            "continuity_scores": {
                "identity": 0.95,
                "body": 0.95,
                "motion": 0.95,
                "object": 0.95,
                "interaction": 0.95,
                "temporal": 0.95,
            },
        },
    )
    assert val["ok"] is False
    assert val["blocker"] == "selfshot3_valid_final_mp4_required"


def test_23_selfshot3_continuity_validation_missing_scores_fails_closed(tmp_path: Path):
    """selfshot3_continuity_validation fails closed when continuity scores are missing (no default fallback)."""
    final_mp4 = tmp_path / "final.mp4"
    final_mp4.write_bytes(b"VALID_FINAL_MP4_CONTENT")

    val = video_real_render_connector.selfshot3_continuity_validation(
        job={"product_type": "self_shot_cinematic_transform"},
        result={
            "final_video_path": str(final_mp4),
            "evidence_source": "local_vision_validator",
            "independent_visual_validation": "LOCAL_MODEL",
        },
    )
    assert val["ok"] is False
    assert val["blocker"] == "selfshot3_continuity_validation_failed"
    assert val["continuity_validation_passed"] is False
    assert any(k in val["failures"] for k in ("identity", "body", "motion", "object", "interaction", "temporal"))


def test_24_selfshot2_controlled_keyframe_i2v_fails_when_local_vision_validator_fails(tmp_path: Path):
    """SelfShot2 controlled keyframe I2V fails closed when local vision validator detects continuity failure."""
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"VALID_SOURCE")
    raw_path = str(tmp_path / "raw.mp4")
    keyframe = tmp_path / "kf.jpg"
    keyframe.write_bytes(b"KEYFRAME")

    mock_gen = {
        "ok": True,
        "provider": "key4u_video",
        "model": "kling-v3",
        "provider_task_ids": ["task-1"],
        "final_video_path": raw_path,
        "output_path": raw_path,
        "output_bytes": 1000,
    }

    mock_failed_continuity = {
        "ok": False,
        "blocker": "person_identity_unverified",
        "failure_reason": "person_identity_unverified",
        "evidence_source": "local_vision_validator",
        "independent_visual_validation": "LOCAL_MODEL",
        "person_required": True,
        "object_required": False,
    }

    with patch("services.video_real_render_connector._materialize_selfshot2_source_segment", return_value=str(source_video)), \
         patch("services.video_real_render_connector._extract_selfshot_keyframe", return_value=str(keyframe)), \
         patch("services.video_real_render_connector.run_provider_generation", return_value=mock_gen), \
         patch("services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity", return_value=mock_failed_continuity):

        with pytest.raises(RealVideoRenderError) as exc_info:
            video_real_render_connector._render_selfshot2_video_to_video(
                job={"source_video_local_path": str(source_video), "public_user_confirmed": True, "submit_source": "public_user_final_confirm", "route": "controlled_keyframe_image_to_video"},
                asset_pack={"route": "controlled_keyframe_image_to_video", "public_user_confirmed": True, "submit_source": "public_user_final_confirm"},
                raw_path=raw_path,
                provider_order=["key4u_video"],
                fallback_prompt="test",
                aspect_ratio="9:16",
                scene_index=0,
            )

        assert exc_info.value.diagnostics["blocker"] == "person_identity_unverified"
        assert exc_info.value.diagnostics["result_rejected_locally"] is True


def test_25_selfshot2_controlled_keyframe_i2v_rejects_mock_visual_evidence(tmp_path: Path):
    """SelfShot2 controlled keyframe I2V rejects mock or non-local evidence and fails closed."""
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"VALID_SOURCE")
    raw_path = str(tmp_path / "raw.mp4")
    keyframe = tmp_path / "kf.jpg"
    keyframe.write_bytes(b"KEYFRAME")

    mock_gen = {
        "ok": True,
        "provider": "key4u_video",
        "model": "kling-v3",
        "provider_task_ids": ["task-1"],
        "final_video_path": raw_path,
        "output_path": raw_path,
        "output_bytes": 1000,
    }

    mock_unverified = {
        "ok": True,
        "blocker": "",
        "evidence_source": "unverified_mock_source",
        "independent_visual_validation": "NOT_PERFORMED",
        "person_required": True,
    }

    with patch("services.video_real_render_connector._materialize_selfshot2_source_segment", return_value=str(source_video)), \
         patch("services.video_real_render_connector._extract_selfshot_keyframe", return_value=str(keyframe)), \
         patch("services.video_real_render_connector.run_provider_generation", return_value=mock_gen), \
         patch("services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity", return_value=mock_unverified):

        with pytest.raises(RealVideoRenderError) as exc_info:
            video_real_render_connector._render_selfshot2_video_to_video(
                job={"source_video_local_path": str(source_video), "public_user_confirmed": True, "submit_source": "public_user_final_confirm", "route": "controlled_keyframe_image_to_video"},
                asset_pack={"route": "controlled_keyframe_image_to_video", "public_user_confirmed": True, "submit_source": "public_user_final_confirm"},
                raw_path=raw_path,
                provider_order=["key4u_video"],
                fallback_prompt="test",
                aspect_ratio="9:16",
                scene_index=0,
            )

        assert exc_info.value.diagnostics["blocker"] == "mock_or_unverified_visual_evidence"


def test_26_catalog_registers_kling_v3_with_i2v_capability():
    """Video provider catalog registers kling-v3 under key4u_video with image_to_video capability."""
    from services.video_provider_catalog import load_video_provider_catalog
    catalog = load_video_provider_catalog()
    key4u_models = catalog.get("providers", {}).get("key4u_video", {}).get("models", {})
    assert "kling-v3" in key4u_models
    model_cfg = key4u_models["kling-v3"]
    assert "image_to_video" in model_cfg.get("capabilities", [])
    assert model_cfg.get("payload_adapter") == "key4u_kling_small_clip"


def test_27_router_preflight_accepts_kling_v3_model_as_valid():
    """video_provider_router preflight accepts kling-v3 as a valid known model for key4u_video."""
    env = {
        "KEY4U_API_KEY": "dummy_key",
        "KEY4U_VIDEO_MODEL": "kling-v3",
        "KEY4U_SUBMIT_URL": "https://api.key4u.vn/submit",
        "KEY4U_POLL_URL": "https://api.key4u.vn/poll/{task_id}",
    }
    adapter = video_provider_router._generic_adapter_for("key4u_video", env)
    assert adapter.env["KEY4U_VIDEO_MODEL"] == "kling-v3"
    assert adapter.env["KEY4U_VIDEO_ENABLED"] == "1"
    assert adapter._configured() is True

    # Verify that an unmapped model fails readiness check
    unmapped_env = dict(env)
    unmapped_env["KEY4U_VIDEO_MODEL"] = "unmapped-arbitrary-model"
    bad_adapter = video_provider_router._generic_adapter_for("key4u_video", unmapped_env)
    assert bad_adapter.env["KEY4U_VIDEO_MODEL"] == ""
    assert bad_adapter.env["KEY4U_VIDEO_ENABLED"] == ""
    assert bad_adapter._configured() is False


# ---------------------------------------------------------------------------
# 10. End-to-End Key4U I2V Wire & Local Continuity Verification
# ---------------------------------------------------------------------------

def test_28_end_to_end_key4u_i2v_wire_selfshot2(tmp_path: Path, monkeypatch):
    """End-to-end Key4U I2V wire test for SelfShot2 intercepting GenericHttpVideoProvider._open_json."""
    from providers.video_generic_http_provider import GenericHttpVideoProvider
    from services.video_provider_base import VideoArtifactResult
    import base64

    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"VALID_SOURCE_MP4_CONTENT")
    raw_path = str(tmp_path / "raw_ss2.mp4")
    keyframe = tmp_path / "kf_ss2.jpg"
    keyframe_bytes = b"BINARY_IMAGE_BYTES_FOR_KEY4U_I2V_SS2_KEYFRAME"
    keyframe.write_bytes(keyframe_bytes)

    captured_wire_payloads: list[tuple[str, dict]] = []
    def fake_open_json(self, url, payload=None, *, method="POST", **_kwargs):
        if method == "POST":
            captured_wire_payloads.append((url, dict(payload or {})))
            return {
                "ok": True,
                "status_code": 200,
                "body": {"code": 0, "data": {"task_id": "key4u_wire_task_ss2_001"}},
                "response_shape": {"type": "dict"},
            }
        return {
            "ok": True,
            "status_code": 200,
            "body": {
                "code": 0,
                "data": {
                    "task_status": "succeed",
                    "task_result": {"videos": [{"url": "https://api.key4u.vn/media/ss2_rendered.mp4"}]},
                },
            },
            "response_shape": {"type": "dict"},
        }

    mock_continuity = {
        "ok": True,
        "blocker": "",
        "evidence_source": "local_vision_validator",
        "independent_visual_validation": "LOCAL_MODEL",
        "person_required": True,
        "object_required": False,
        "relationship_required": False,
        "person_identity": True,
        "object_identity": True,
        "person_object_relationship": True,
    }

    def fake_materialize(url, *args, **kwargs):
        out = tmp_path / "downloaded_ss2.mp4"
        out.write_bytes(b"DOWNLOADED_MP4_CONTENT_SS2")
        return VideoArtifactResult(
            ok=True,
            local_path=str(out),
            bytes=len(b"DOWNLOADED_MP4_CONTENT_SS2"),
            duration=5.0,
            has_video_stream=True,
        )

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open_json)
    monkeypatch.setattr("providers.video_generic_http_provider.materialize_video_url", fake_materialize)
    monkeypatch.setattr(
        "services.video_real_render_connector._materialize_selfshot2_source_segment",
        lambda *args, **kwargs: str(source_video),
    )
    monkeypatch.setattr(
        "services.video_real_render_connector._extract_selfshot_keyframe",
        lambda *args, **kwargs: str(keyframe),
    )
    monkeypatch.setattr(
        "services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity",
        lambda *args, **kwargs: mock_continuity,
    )

    env_overrides = {
        "KEY4U_API_KEY": "test_wire_api_key_valid",
        "KEY4U_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_SUBMIT_URL": "https://api.key4u.vn/kling/v1/videos/image2video",
        "KEY4U_VIDEO_POLL_URL": "https://api.key4u.vn/kling/v1/videos/query?id={task_id}",
        "KEY4U_BASE_URL": "https://api.key4u.vn",
    }
    for k, v in env_overrides.items():
        monkeypatch.setenv(k, v)

    res = video_real_render_connector._render_selfshot2_video_to_video(
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
            "scene_duration_seconds": 5,
        },
        raw_path=raw_path,
        provider_order=["key4u_video"],
        fallback_prompt="SelfShot2 cinematic scene replacement",
        aspect_ratio="9:16",
        scene_index=0,
    )

    assert res["ok"] is True
    assert res["provider"] == "key4u_video"
    assert res["model"] == "kling-v3"
    assert res["continuity_validation_passed"] is True
    assert res["continuity_evidence"]["evidence_source"] == "local_vision_validator"

    assert len(captured_wire_payloads) == 1
    wire_url, wire_body = captured_wire_payloads[0]
    assert wire_url == "https://api.key4u.vn/kling/v1/videos/image2video"
    assert wire_body["model_name"] == "kling-v3"
    assert wire_body["aspect_ratio"] == "9:16"
    assert wire_body["duration"] == 5
    assert "image" in wire_body
    decoded_img = base64.b64decode(wire_body["image"])
    assert decoded_img == keyframe_bytes


def test_29_end_to_end_key4u_i2v_wire_selfshot3(tmp_path: Path, monkeypatch):
    """End-to-end Key4U I2V wire test for SelfShot3 intercepting GenericHttpVideoProvider._open_json."""
    from providers.video_generic_http_provider import GenericHttpVideoProvider
    from services.video_provider_base import VideoArtifactResult
    import base64

    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"VALID_SOURCE_MP4_CONTENT")
    raw_path = str(tmp_path / "raw_ss3.mp4")
    keyframe = tmp_path / "kf_ss3.jpg"
    keyframe_bytes = b"BINARY_IMAGE_BYTES_FOR_KEY4U_I2V_SS3_KEYFRAME"
    keyframe.write_bytes(keyframe_bytes)

    captured_wire_payloads: list[tuple[str, dict]] = []
    def fake_open_json(self, url, payload=None, *, method="POST", **_kwargs):
        if method == "POST":
            captured_wire_payloads.append((url, dict(payload or {})))
            return {
                "ok": True,
                "status_code": 200,
                "body": {"code": 0, "data": {"task_id": "key4u_wire_task_ss3_001"}},
                "response_shape": {"type": "dict"},
            }
        return {
            "ok": True,
            "status_code": 200,
            "body": {
                "code": 0,
                "data": {
                    "task_status": "succeed",
                    "task_result": {"videos": [{"url": "https://api.key4u.vn/media/ss3_rendered.mp4"}]},
                },
            },
            "response_shape": {"type": "dict"},
        }

    mock_continuity = {
        "ok": True,
        "blocker": "",
        "evidence_source": "local_vision_validator",
        "independent_visual_validation": "LOCAL_MODEL",
        "person_required": True,
        "object_required": False,
        "relationship_required": False,
        "person_identity": True,
        "object_identity": True,
        "person_object_relationship": True,
    }

    def fake_materialize(url, *args, **kwargs):
        out = tmp_path / "downloaded_ss3.mp4"
        out.write_bytes(b"DOWNLOADED_MP4_CONTENT_SS3")
        return VideoArtifactResult(
            ok=True,
            local_path=str(out),
            bytes=len(b"DOWNLOADED_MP4_CONTENT_SS3"),
            duration=5.0,
            has_video_stream=True,
        )

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open_json)
    monkeypatch.setattr("providers.video_generic_http_provider.materialize_video_url", fake_materialize)
    monkeypatch.setattr(
        "services.video_real_render_connector._extract_selfshot_keyframe",
        lambda *args, **kwargs: str(keyframe),
    )
    monkeypatch.setattr(
        "services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity",
        lambda *args, **kwargs: mock_continuity,
    )

    env_overrides = {
        "KEY4U_API_KEY": "test_wire_api_key_valid",
        "KEY4U_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_SUBMIT_URL": "https://api.key4u.vn/kling/v1/videos/image2video",
        "KEY4U_VIDEO_POLL_URL": "https://api.key4u.vn/kling/v1/videos/query?id={task_id}",
        "KEY4U_BASE_URL": "https://api.key4u.vn",
    }
    for k, v in env_overrides.items():
        monkeypatch.setenv(k, v)

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
            "duration_seconds": 5,
        },
        raw_path=raw_path,
        provider_order=["key4u_video"],
        fallback_prompt="SelfShot3 cinematic one-take",
        aspect_ratio="9:16",
    )

    assert res["ok"] is True
    assert res["selfshot3"] is True
    assert res["provider"] == "key4u_video"
    assert res["model"] == "kling-v3"
    assert res["continuity_validation_passed"] is True
    assert res["evidence_source"] == "local_vision_validator"
    assert res["independent_visual_validation"] == "LOCAL_MODEL"
    for layer in ("identity", "body", "motion", "object", "interaction", "temporal"):
        assert res["continuity_scores"][layer] >= 0.8

    assert len(captured_wire_payloads) == 1
    wire_url, wire_body = captured_wire_payloads[0]
    assert wire_url == "https://api.key4u.vn/kling/v1/videos/image2video"
    assert wire_body["model_name"] == "kling-v3"
    assert wire_body["aspect_ratio"] == "9:16"
    assert wire_body["duration"] == 5
    assert "image" in wire_body
    decoded_img = base64.b64decode(wire_body["image"])
    assert decoded_img == keyframe_bytes


def test_30_selfshot3_controlled_keyframe_i2v_fails_when_local_vision_validator_fails(tmp_path: Path):
    """SelfShot3 controlled keyframe I2V fails closed when local vision validator detects continuity failure."""
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"VALID_SOURCE")
    raw_path = str(tmp_path / "raw.mp4")
    keyframe = tmp_path / "kf.jpg"
    keyframe.write_bytes(b"KEYFRAME")

    mock_gen = {
        "ok": True,
        "provider": "key4u_video",
        "model": "kling-v3",
        "provider_task_ids": ["task-1"],
        "final_video_path": raw_path,
        "output_path": raw_path,
        "output_bytes": 1000,
    }

    mock_failed_continuity = {
        "ok": False,
        "blocker": "person_identity_unverified",
        "failure_reason": "person_identity_unverified",
        "evidence_source": "local_vision_validator",
        "independent_visual_validation": "LOCAL_MODEL",
        "person_required": True,
        "object_required": False,
    }

    with patch("services.video_real_render_connector._extract_selfshot_keyframe", return_value=str(keyframe)), \
         patch("services.video_real_render_connector.run_provider_generation", return_value=mock_gen), \
         patch("services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity", return_value=mock_failed_continuity):

        with pytest.raises(RealVideoRenderError) as exc_info:
            video_real_render_connector._render_selfshot3_video_to_video(
                job={"source_video_local_path": str(source_video), "public_user_confirmed": True, "submit_source": "public_user_final_confirm", "route": "controlled_keyframe_image_to_video"},
                asset_pack={"route": "controlled_keyframe_image_to_video", "public_user_confirmed": True, "submit_source": "public_user_final_confirm"},
                raw_path=raw_path,
                provider_order=["key4u_video"],
                fallback_prompt="test",
                aspect_ratio="9:16",
            )

        assert exc_info.value.diagnostics["blocker"] == "person_identity_unverified"
        assert exc_info.value.diagnostics["result_rejected_locally"] is True


def test_31_selfshot3_controlled_keyframe_i2v_rejects_mock_visual_evidence(tmp_path: Path):
    """SelfShot3 controlled keyframe I2V rejects mock or non-local evidence and fails closed."""
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"VALID_SOURCE")
    raw_path = str(tmp_path / "raw.mp4")
    keyframe = tmp_path / "kf.jpg"
    keyframe.write_bytes(b"KEYFRAME")

    mock_gen = {
        "ok": True,
        "provider": "key4u_video",
        "model": "kling-v3",
        "provider_task_ids": ["task-1"],
        "final_video_path": raw_path,
        "output_path": raw_path,
        "output_bytes": 1000,
    }

    mock_unverified = {
        "ok": True,
        "blocker": "",
        "evidence_source": "unverified_mock_source",
        "independent_visual_validation": "NOT_PERFORMED",
        "person_required": True,
    }

    with patch("services.video_real_render_connector._extract_selfshot_keyframe", return_value=str(keyframe)), \
         patch("services.video_real_render_connector.run_provider_generation", return_value=mock_gen), \
         patch("services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity", return_value=mock_unverified):

        with pytest.raises(RealVideoRenderError) as exc_info:
            video_real_render_connector._render_selfshot3_video_to_video(
                job={"source_video_local_path": str(source_video), "public_user_confirmed": True, "submit_source": "public_user_final_confirm", "route": "controlled_keyframe_image_to_video"},
                asset_pack={"route": "controlled_keyframe_image_to_video", "public_user_confirmed": True, "submit_source": "public_user_final_confirm"},
                raw_path=raw_path,
                provider_order=["key4u_video"],
                fallback_prompt="test",
                aspect_ratio="9:16",
            )

        assert exc_info.value.diagnostics["blocker"] == "mock_or_unverified_visual_evidence"
        assert exc_info.value.diagnostics["result_rejected_locally"] is True


# ---------------------------------------------------------------------------
# 11. Default Provider Chain Kling Pinning & Final SelfShot3 Local Authority
# ---------------------------------------------------------------------------

def test_32_default_provider_chain_pins_kling_v3_for_selfshot2(tmp_path: Path, monkeypatch):
    """SelfShot2 controlled I2V with default provider chain (shopaikey first) prioritizes key4u and pins kling-v3."""
    from providers.video_generic_http_provider import GenericHttpVideoProvider
    from services.video_provider_base import VideoArtifactResult

    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"VALID_SOURCE_MP4_CONTENT")
    raw_path = str(tmp_path / "raw_ss2.mp4")
    keyframe = tmp_path / "kf_ss2.jpg"
    keyframe.write_bytes(b"BINARY_KEYFRAME_SS2")

    captured_wire_payloads: list[tuple[str, dict]] = []
    def fake_open_json(self, url, payload=None, *, method="POST", **_kwargs):
        if method == "POST":
            captured_wire_payloads.append((url, dict(payload or {})))
            return {
                "ok": True,
                "status_code": 200,
                "body": {"code": 0, "data": {"task_id": "key4u_wire_task_default_chain_ss2"}},
                "response_shape": {"type": "dict"},
            }
        return {
            "ok": True,
            "status_code": 200,
            "body": {
                "code": 0,
                "data": {
                    "task_status": "succeed",
                    "task_result": {"videos": [{"url": "https://api.key4u.vn/media/ss2_out.mp4"}]},
                },
            },
            "response_shape": {"type": "dict"},
        }

    mock_continuity = {
        "ok": True,
        "blocker": "",
        "evidence_source": "local_vision_validator",
        "independent_visual_validation": "LOCAL_MODEL",
        "person_required": True,
        "object_required": False,
        "relationship_required": False,
        "person_identity": True,
        "object_identity": True,
        "person_object_relationship": True,
    }

    def fake_materialize(url, *args, **kwargs):
        out = tmp_path / "downloaded_ss2.mp4"
        out.write_bytes(b"DOWNLOADED_MP4")
        return VideoArtifactResult(
            ok=True,
            local_path=str(out),
            bytes=len(b"DOWNLOADED_MP4"),
            duration=5.0,
            has_video_stream=True,
        )

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open_json)
    monkeypatch.setattr("providers.video_generic_http_provider.materialize_video_url", fake_materialize)
    monkeypatch.setattr(
        "services.video_real_render_connector._materialize_selfshot2_source_segment",
        lambda *args, **kwargs: str(source_video),
    )
    monkeypatch.setattr(
        "services.video_real_render_connector._extract_selfshot_keyframe",
        lambda *args, **kwargs: str(keyframe),
    )
    monkeypatch.setattr(
        "services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity",
        lambda *args, **kwargs: mock_continuity,
    )

    env_overrides = {
        "KEY4U_API_KEY": "test_wire_api_key_valid",
        "KEY4U_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_SUBMIT_URL": "https://api.key4u.vn/kling/v1/videos/image2video",
        "KEY4U_VIDEO_POLL_URL": "https://api.key4u.vn/kling/v1/videos/query?id={task_id}",
        "KEY4U_BASE_URL": "https://api.key4u.vn",
        "KEY4U_VIDEO_MODEL": "arbitrary_env_model_must_be_overridden",
    }
    for k, v in env_overrides.items():
        monkeypatch.setenv(k, v)

    # Pass the standard default provider chain where shopaikey_video is at index 0
    res = video_real_render_connector._render_selfshot2_video_to_video(
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
            "scene_duration_seconds": 5,
        },
        raw_path=raw_path,
        provider_order=["shopaikey_video", "key4u_video"],
        fallback_prompt="SelfShot2 default chain test",
        aspect_ratio="9:16",
        scene_index=0,
    )

    assert res["ok"] is True
    assert res["provider"] == "key4u_video"
    assert res["model"] == "kling-v3"
    assert res["continuity_validation_passed"] is True
    assert res["continuity_metadata_authority"] == "local_vision_validator"
    assert res["independent_visual_continuity_proven"] is True

    # Wire payload was sent directly to Key4U with hard-pinned kling-v3
    assert len(captured_wire_payloads) == 1
    wire_url, wire_body = captured_wire_payloads[0]
    assert wire_url == "https://api.key4u.vn/kling/v1/videos/image2video"
    assert wire_body["model_name"] == "kling-v3"
    assert wire_body["duration"] == 5


def test_33_default_provider_chain_pins_kling_v3_for_selfshot3(tmp_path: Path, monkeypatch):
    """SelfShot3 controlled I2V with default provider chain (shopaikey first) prioritizes key4u and pins kling-v3."""
    from providers.video_generic_http_provider import GenericHttpVideoProvider
    from services.video_provider_base import VideoArtifactResult

    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"VALID_SOURCE_MP4_CONTENT")
    raw_path = str(tmp_path / "raw_ss3.mp4")
    keyframe = tmp_path / "kf_ss3.jpg"
    keyframe.write_bytes(b"BINARY_KEYFRAME_SS3")

    captured_wire_payloads: list[tuple[str, dict]] = []
    def fake_open_json(self, url, payload=None, *, method="POST", **_kwargs):
        if method == "POST":
            captured_wire_payloads.append((url, dict(payload or {})))
            return {
                "ok": True,
                "status_code": 200,
                "body": {"code": 0, "data": {"task_id": "key4u_wire_task_default_chain_ss3"}},
                "response_shape": {"type": "dict"},
            }
        return {
            "ok": True,
            "status_code": 200,
            "body": {
                "code": 0,
                "data": {
                    "task_status": "succeed",
                    "task_result": {"videos": [{"url": "https://api.key4u.vn/media/ss3_out.mp4"}]},
                },
            },
            "response_shape": {"type": "dict"},
        }

    mock_continuity = {
        "ok": True,
        "blocker": "",
        "evidence_source": "local_vision_validator",
        "independent_visual_validation": "LOCAL_MODEL",
        "person_required": True,
        "object_required": False,
        "relationship_required": False,
        "person_identity": True,
        "object_identity": True,
        "person_object_relationship": True,
    }

    def fake_materialize(url, *args, **kwargs):
        out = tmp_path / "downloaded_ss3.mp4"
        out.write_bytes(b"DOWNLOADED_MP4")
        return VideoArtifactResult(
            ok=True,
            local_path=str(out),
            bytes=len(b"DOWNLOADED_MP4"),
            duration=5.0,
            has_video_stream=True,
        )

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open_json)
    monkeypatch.setattr("providers.video_generic_http_provider.materialize_video_url", fake_materialize)
    monkeypatch.setattr(
        "services.video_real_render_connector._extract_selfshot_keyframe",
        lambda *args, **kwargs: str(keyframe),
    )
    monkeypatch.setattr(
        "services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity",
        lambda *args, **kwargs: mock_continuity,
    )

    env_overrides = {
        "KEY4U_API_KEY": "test_wire_api_key_valid",
        "KEY4U_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_SUBMIT_URL": "https://api.key4u.vn/kling/v1/videos/image2video",
        "KEY4U_VIDEO_POLL_URL": "https://api.key4u.vn/kling/v1/videos/query?id={task_id}",
        "KEY4U_BASE_URL": "https://api.key4u.vn",
        "KEY4U_VIDEO_MODEL": "arbitrary_env_model_must_be_overridden",
    }
    for k, v in env_overrides.items():
        monkeypatch.setenv(k, v)

    # Pass the standard default provider chain where shopaikey_video is at index 0
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
            "duration_seconds": 5,
        },
        raw_path=raw_path,
        provider_order=["shopaikey_video", "key4u_video"],
        fallback_prompt="SelfShot3 default chain test",
        aspect_ratio="9:16",
    )

    assert res["ok"] is True
    assert res["selfshot3"] is True
    assert res["provider"] == "key4u_video"
    assert res["model"] == "kling-v3"
    assert res["continuity_validation_passed"] is True
    assert res["continuity_metadata_authority"] == "local_vision_validator"
    assert res["independent_visual_continuity_proven"] is True

    # Wire payload was sent directly to Key4U with hard-pinned kling-v3
    assert len(captured_wire_payloads) == 1
    wire_url, wire_body = captured_wire_payloads[0]
    assert wire_url == "https://api.key4u.vn/kling/v1/videos/image2video"
    assert wire_body["model_name"] == "kling-v3"
    assert wire_body["duration"] == 5


def test_34_selfshot3_local_evidence_authority_proven(tmp_path: Path):
    """selfshot3_continuity_validation reports local vision validator authority when proven."""
    final_mp4 = tmp_path / "final.mp4"
    final_mp4.write_bytes(b"VALID_FINAL_MP4_CONTENT")

    val = video_real_render_connector.selfshot3_continuity_validation(
        job={"product_type": "self_shot_cinematic_transform"},
        result={
            "final_video_path": str(final_mp4),
            "evidence_source": "local_vision_validator",
            "independent_visual_validation": "LOCAL_MODEL",
            "continuity_evidence_present": True,
            "continuity_scores": {
                "identity": 0.95,
                "body": 0.95,
                "motion": 0.95,
                "object": 0.95,
                "interaction": 0.95,
                "temporal": 0.95,
            },
        },
    )
    assert val["ok"] is True
    assert val["selfshot3"] is True
    assert val["blocker"] == ""
    assert val["final_mp4_valid"] is True
    assert val["continuity_validation_passed"] is True
    assert val["continuity_metadata_authority"] == "local_vision_validator"
    assert val["independent_visual_validation"] == "LOCAL_MODEL"
    assert val["independent_visual_validation_pass"] is True
    assert val["independent_visual_continuity_proven"] is True


def test_35_selfshot3_local_evidence_authority_rejects_mock_or_unverified(tmp_path: Path):
    """selfshot3_continuity_validation fails closed when evidence is mock or unverified."""
    final_mp4 = tmp_path / "final.mp4"
    final_mp4.write_bytes(b"VALID_FINAL_MP4_CONTENT")

    val = video_real_render_connector.selfshot3_continuity_validation(
        job={"product_type": "self_shot_cinematic_transform"},
        result={
            "final_video_path": str(final_mp4),
            "evidence_source": "unverified_mock_source",
            "independent_visual_validation": "NOT_PERFORMED",
            "continuity_evidence_present": True,
            "continuity_scores": {
                "identity": 0.95,
                "body": 0.95,
                "motion": 0.95,
                "object": 0.95,
                "interaction": 0.95,
                "temporal": 0.95,
            },
        },
    )
    assert val["ok"] is False
    assert val["blocker"] == "mock_or_unverified_visual_evidence"
    assert val["continuity_validation_passed"] is False
    assert val["independent_visual_validation_pass"] is False
    assert val["independent_visual_continuity_proven"] is False


def test_36_video_selfshot3_module_continuity_authority():
    """video_selfshot3.continuity_validation reports authority and rejects mock evidence."""
    good_scores = {
        "identity": 0.95,
        "body": 0.95,
        "motion": 0.95,
        "object": 0.95,
        "interaction": 0.95,
        "temporal": 0.95,
        "evidence_source": "local_vision_validator",
        "independent_visual_validation": "LOCAL_MODEL",
    }
    val = video_selfshot3.continuity_validation(good_scores)
    assert val["ok"] is True
    assert val["continuity_metadata_authority"] == "local_vision_validator"
    assert val["independent_visual_continuity_proven"] is True

    # Rejection of mock evidence
    mock_scores = {
        **good_scores,
        "evidence_source": "unverified_mock_source",
    }
    val_mock = video_selfshot3.continuity_validation(mock_scores)
    assert val_mock["ok"] is False
    assert "mock_or_unverified_visual_evidence" in val_mock["failures"]
    assert val_mock["independent_visual_continuity_proven"] is False


def test_37_selfshot3_continuity_validation_rejects_synthetic_0_95_without_local_authority(tmp_path: Path):
    """selfshot3_continuity_validation fails closed when scores lack local vision authority."""
    final_mp4 = tmp_path / "final.mp4"
    final_mp4.write_bytes(b"VALID_FINAL_MP4_CONTENT")

    val = video_real_render_connector.selfshot3_continuity_validation(
        job={"product_type": "self_shot_cinematic_transform"},
        result={
            "final_video_path": str(final_mp4),
            "continuity_scores": {
                "identity": 0.95,
                "body": 0.95,
                "motion": 0.95,
                "object": 0.95,
                "interaction": 0.95,
                "temporal": 0.95,
            },
        },
    )
    assert val["ok"] is False
    assert val["blocker"] == "missing_local_vision_authority"
    assert val["continuity_validation_passed"] is False
    assert val["continuity_metadata_authority"] != "local_vision_validator"
    assert val["independent_visual_continuity_proven"] is False


def test_38_selfshot3_continuity_validation_rejects_provider_metadata_and_forged_high_scores(tmp_path: Path):
    """selfshot3_continuity_validation rejects provider-claimed scores without local validator."""
    final_mp4 = tmp_path / "final.mp4"
    final_mp4.write_bytes(b"VALID_FINAL_MP4_CONTENT")

    val = video_real_render_connector.selfshot3_continuity_validation(
        job={"product_type": "self_shot_cinematic_transform"},
        result={
            "final_video_path": str(final_mp4),
            "continuity_scores": {
                "identity": 0.99,
                "body": 0.99,
                "motion": 0.99,
                "object": 0.99,
                "interaction": 0.99,
                "temporal": 0.99,
            },
            "evidence_source": "provider_kling_ai",
            "independent_visual_validation": "PROVIDER_CLAIM",
        },
    )
    assert val["ok"] is False
    assert val["blocker"] == "missing_local_vision_authority"
    assert val["continuity_validation_passed"] is False
    assert val["continuity_metadata_authority"] != "local_vision_validator"
    assert val["independent_visual_continuity_proven"] is False


def test_39_selfshot3_continuity_validation_requires_local_model_independent_visual_validation(tmp_path: Path):
    """selfshot3_continuity_validation requires independent_visual_validation == LOCAL_MODEL."""
    final_mp4 = tmp_path / "final.mp4"
    final_mp4.write_bytes(b"VALID_FINAL_MP4_CONTENT")

    val = video_real_render_connector.selfshot3_continuity_validation(
        job={"product_type": "self_shot_cinematic_transform"},
        result={
            "final_video_path": str(final_mp4),
            "evidence_source": "local_vision_validator",
            "independent_visual_validation": "NOT_PERFORMED",
            "continuity_evidence_present": True,
            "continuity_scores": {
                "identity": 1.0,
                "body": 1.0,
                "motion": 1.0,
                "object": 1.0,
                "interaction": 1.0,
                "temporal": 1.0,
            },
        },
    )
    assert val["ok"] is False
    assert val["blocker"] == "independent_visual_validation_required"
    assert val["continuity_validation_passed"] is False
    assert val["independent_visual_validation_pass"] is False
    assert val["independent_visual_continuity_proven"] is False


def test_40_video_selfshot3_record_delivery_rejects_scores_missing_local_authority():
    """video_selfshot3.record_delivery rejects scores missing local vision validator authority."""
    with pytest.raises(ValueError, match="continuity_validation_required"):
        video_selfshot3.record_delivery(
            {},
            final_mp4_valid=True,
            message_id=99,
            receipt_key="job:99",
            continuity={
                "identity": 0.95,
                "body": 0.95,
                "motion": 0.95,
                "object": 0.95,
                "interaction": 0.95,
                "temporal": 0.95,
            },
        )


def test_41_video_selfshot3_continuity_validation_requires_local_authority():
    """video_selfshot3.continuity_validation rejects scores missing local vision validator authority."""
    raw_scores = {
        "identity": 0.95,
        "body": 0.95,
        "motion": 0.95,
        "object": 0.95,
        "interaction": 0.95,
        "temporal": 0.95,
    }
    val = video_selfshot3.continuity_validation(raw_scores)
    assert val["ok"] is False
    assert "missing_local_vision_authority" in val["failures"]
    assert val["continuity_metadata_authority"] != "local_vision_validator"
    assert val["independent_visual_continuity_proven"] is False


def test_42_selfshot3_i2v_connector_rejects_gen_result_and_job_continuity_scores(tmp_path: Path, monkeypatch):
    """SelfShot3 connector ignores unverified gen_result/job scores and fails closed on local validator failure."""
    from services.video_real_render_connector import RealVideoRenderError
    from services.video_provider_base import VideoGenerationRequest

    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"VALID_SOURCE_MP4_CONTENT")
    raw_path = str(tmp_path / "raw_ss3.mp4")
    keyframe = tmp_path / "kf_ss3.jpg"
    keyframe.write_bytes(b"BINARY_KEYFRAME_SS3")

    fake_gen_result = {
        "ok": True,
        "provider": "key4u_video",
        "model": "kling-v3",
        "output_path": raw_path,
        "continuity_scores": {
            "identity": 0.99,
            "body": 0.99,
            "motion": 0.99,
            "object": 0.99,
            "interaction": 0.99,
            "temporal": 0.99,
        },
    }

    mock_failed_continuity = {
        "ok": False,
        "blocker": "insufficient_temporal_evidence",
        "evidence_source": "local_vision_validator",
        "independent_visual_validation": "LOCAL_MODEL",
    }

    monkeypatch.setattr(
        "services.video_real_render_connector.run_provider_generation",
        lambda *args, **kwargs: fake_gen_result,
    )
    monkeypatch.setattr(
        "services.video_real_render_connector._extract_selfshot_keyframe",
        lambda *args, **kwargs: str(keyframe),
    )
    monkeypatch.setattr(
        "services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity",
        lambda *args, **kwargs: mock_failed_continuity,
    )

    with pytest.raises(RealVideoRenderError) as exc_info:
        video_real_render_connector._render_selfshot3_video_to_video(
            job={
                "source_video_local_path": str(source_video),
                "public_user_confirmed": True,
                "submit_source": "public_user_final_confirm",
                "route": "controlled_keyframe_image_to_video",
                "continuity_scores": {"identity": 0.99, "body": 0.99, "motion": 0.99, "object": 0.99, "interaction": 0.99, "temporal": 0.99},
            },
            asset_pack={
                "route": "controlled_keyframe_image_to_video",
                "public_user_confirmed": True,
                "submit_source": "public_user_final_confirm",
                "duration_seconds": 5,
                "continuity_scores": {"identity": 0.99, "body": 0.99, "motion": 0.99, "object": 0.99, "interaction": 0.99, "temporal": 0.99},
            },
            raw_path=raw_path,
            provider_order=["key4u_video"],
            fallback_prompt="test prompt",
            aspect_ratio="9:16",
        )
    assert str(exc_info.value) == "insufficient_temporal_evidence"
    diag = exc_info.value.diagnostics
    assert diag["result_rejected_locally"] is True

    # Now verify success case: genuine local validator passes
    mock_good_continuity = {
        "ok": True,
        "blocker": "",
        "evidence_source": "local_vision_validator",
        "independent_visual_validation": "LOCAL_MODEL",
        "person_identity": True,
        "object_identity": True,
        "person_object_relationship": True,
        "person_required": True,
        "object_required": False,
        "relationship_required": False,
        "person_observations": [{"frame_index": 0, "person_ok": True}, {"frame_index": 1, "person_ok": True}],
    }
    monkeypatch.setattr(
        "services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity",
        lambda *args, **kwargs: mock_good_continuity,
    )
    res = video_real_render_connector._render_selfshot3_video_to_video(
        job={
            "source_video_local_path": str(source_video),
            "public_user_confirmed": True,
            "submit_source": "public_user_final_confirm",
            "route": "controlled_keyframe_image_to_video",
            "continuity_scores": {"identity": 0.99, "body": 0.99, "motion": 0.99, "object": 0.99, "interaction": 0.99, "temporal": 0.99},
        },
        asset_pack={
            "route": "controlled_keyframe_image_to_video",
            "public_user_confirmed": True,
            "submit_source": "public_user_final_confirm",
            "duration_seconds": 5,
            "continuity_scores": {"identity": 0.99, "body": 0.99, "motion": 0.99, "object": 0.99, "interaction": 0.99, "temporal": 0.99},
        },
        raw_path=raw_path,
        provider_order=["key4u_video"],
        fallback_prompt="test prompt",
        aspect_ratio="9:16",
    )
    assert res["ok"] is True
    # Verify that scores did NOT come from the unverified 0.99 dict in job/asset_pack
    assert res["continuity_scores"]["identity"] != 0.99
    assert res["continuity_metadata_authority"] == "local_vision_validator"


def test_43_temporal_score_uses_actual_frame_pass_ratio_not_ok_boolean(tmp_path: Path, monkeypatch):
    """Temporal score uses actual frame or integrated pass ratio, not overall ok boolean."""
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"VALID_SOURCE_MP4_CONTENT")
    raw_path = str(tmp_path / "raw_ss3.mp4")
    keyframe = tmp_path / "kf_ss3.jpg"
    keyframe.write_bytes(b"BINARY_KEYFRAME_SS3")

    fake_gen_result = {
        "ok": True,
        "provider": "key4u_video",
        "model": "kling-v3",
        "output_path": raw_path,
    }

    # 2 out of 3 frames pass -> ratio is 2/3 = 0.6667 (below 0.8 threshold)
    mock_partial_continuity = {
        "ok": True,  # Claimed ok boolean must NOT be mapped to 1.0!
        "blocker": "",
        "evidence_source": "local_vision_validator",
        "independent_visual_validation": "LOCAL_MODEL",
        "person_required": True,
        "object_required": False,
        "relationship_required": False,
        "person_identity": True,
        "object_identity": True,
        "person_object_relationship": True,
        "passing_integrated": 2,
        "sampled_frame_count": 3,
        "temporal_pass_ratio": 0.6667,
        "motion_score": 0.95,
        "body_score": 0.95,
        "person_observations": [{"person_ok": True}, {"person_ok": True}, {"person_ok": False}],
    }

    monkeypatch.setattr(
        "services.video_real_render_connector.run_provider_generation",
        lambda *args, **kwargs: fake_gen_result,
    )
    monkeypatch.setattr(
        "services.video_real_render_connector._extract_selfshot_keyframe",
        lambda *args, **kwargs: str(keyframe),
    )
    monkeypatch.setattr(
        "services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity",
        lambda *args, **kwargs: mock_partial_continuity,
    )

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
            "duration_seconds": 5,
        },
        raw_path=raw_path,
        provider_order=["key4u_video"],
        fallback_prompt="test prompt",
        aspect_ratio="9:16",
    )
    # Temporal score was measured from pass ratio 2/3 = 0.6667, NOT 1.0 from ok boolean
    assert res["continuity_scores"]["temporal"] == 0.6667


def test_44_unmeasured_motion_and_body_fail_closed(tmp_path: Path):
    """When dimensions are unmeasured, they fail closed (0.0) and do not pass delivery validation."""
    final_mp4 = tmp_path / "final.mp4"
    final_mp4.write_bytes(b"VALID_FINAL_MP4_CONTENT")

    val = video_real_render_connector.selfshot3_continuity_validation(
        job={"product_type": "self_shot_cinematic_transform"},
        result={
            "final_video_path": str(final_mp4),
            "evidence_source": "local_vision_validator",
            "independent_visual_validation": "LOCAL_MODEL",
            "continuity_evidence_present": True,
            "continuity_scores": {
                "identity": 0.95,
                "body": 0.0,  # Unmeasured body fails closed
                "motion": 0.95,
                "object": 0.95,
                "interaction": 0.95,
                "temporal": 0.95,
            },
        },
    )
    assert val["ok"] is False
    assert val["blocker"] == "selfshot3_continuity_validation_failed"
    assert "body" in val["failures"]


def test_45_local_vision_validator_computes_measured_continuity_scores(tmp_path: Path):
    """validate_selfshot_scene_continuity computes empirical continuity scores without synthetic proxies."""
    from services.video_selfshot_continuity_validator import validate_selfshot_scene_continuity
    import numpy as np

    # Frame observations where 3 of 3 pass
    mock_obs = [
        {"frame_index": 0, "person_ok": True, "object_ok": True, "relationship_ok": True, "person_bbox": [10, 10, 50, 100], "integrated_ok": True},
        {"frame_index": 1, "person_ok": True, "object_ok": True, "relationship_ok": True, "person_bbox": [12, 10, 50, 102], "integrated_ok": True},
        {"frame_index": 2, "person_ok": True, "object_ok": True, "relationship_ok": True, "person_bbox": [11, 11, 50, 100], "integrated_ok": True},
    ]

    res = validate_selfshot_scene_continuity(
        clip_source="dummy_path",
        scene_duration_seconds=5,
        person_required=True,
        object_required=True,
        relationship_required=True,
        mock_frame_observations=mock_obs,
    )
    assert res["ok"] is True
    assert "continuity_scores" in res
    scores = res["continuity_scores"]
    assert scores["temporal"] == 1.0
    assert scores["identity"] == 1.0
    assert scores["object"] == 1.0
    assert scores["interaction"] == 1.0
    assert scores["body"] >= 0.8
    assert scores["motion"] >= 0.8







