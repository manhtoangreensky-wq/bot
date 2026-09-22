"""Targeted test suite for P0.PRODUCT_VIDEO.PV2_R05A.TIER700.RUNTIME.CONTRACT.CORRECTION.R1.

Covers Cases A through G:
- CASE A: R05A + Tier700 -> video_to_video_multipart, source bound, duration 15
- CASE B: R05A missing source video -> fail closed before transport
- CASE C: Tier700 quality key -> kling_long_audio_15, 15 seconds
- CASE D: motion_pro_audio_10 -> remains 10 seconds, no collision with Tier700
- CASE E: 2-scene Tier700 -> expected final duration 30
- CASE F: manual continuity booleans only -> independent visual validation NOT proven
- CASE G: non-R05A existing product routes -> unchanged
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from services import (
    video_ai_edit_provider,
    video_ai_real_pricing,
    video_final_output,
    video_project_queue,
    video_provider_router,
    video_real_render_connector,
    video_tail9,
)
from services.video_provider_base import VideoGenerationRequest


# ---------------------------------------------------------------------------
# CASE A: R05A + Tier700 -> video_to_video_multipart, source bound, duration 15
# ---------------------------------------------------------------------------
def test_case_a_r05a_tier700_route_and_source_binding_and_duration(tmp_path: Path):
    source_video = tmp_path / "PV-L05-self-shot-typing-source.mp4"
    source_video.write_bytes(b"TEST_VIDEO_BYTES_TIER700_FIXTURE_123456789")
    raw_path = str(tmp_path / "output_raw.mp4")

    job = {
        "job_id": "job_40_test",
        "product_type": "self_shot_scene_change",
        "quality_tier": 700,
        "public_user_confirmed": True,
        "submit_source": video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
    }
    asset_pack = {
        "product_type": "self_shot_scene_change",
        "quality_tier": 700,
        "source_video_local_path": str(source_video),
        "public_user_confirmed": True,
        "submit_source": video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
        "video_prompts": [
            {"scene_index": 1, "prompt": "Rooftop cafe transformation typing scene 1"},
            {"scene_index": 2, "prompt": "Rooftop cafe transformation typing scene 2"},
        ],
        "scene_source_segments": [
            {"scene_index": 1, "start_seconds": 0.0, "end_seconds": 15.0},
            {"scene_index": 2, "start_seconds": 15.0, "end_seconds": 30.0},
        ],
    }

    captured_call = {}

    def fake_submit_video_edit(config, **kwargs):
        captured_call["config"] = config
        captured_call.update(kwargs)
        return {
            "accepted": True,
            "provider_task_id": "test_task_700_1",
            "result_url_present": True,
            "result_url": "https://example.com/result.mp4",
        }

    def fake_download_result(url, target_path):
        Path(target_path).write_bytes(b"OUTPUT_MP4_BYTES")
        return {"path": target_path, "bytes": len(b"OUTPUT_MP4_BYTES")}

    fake_config = video_ai_edit_provider.AiEditProviderConfig(
        provider_name="key4u_video",
        enabled=True,
        submit_url="https://api.key4u.vn/kling/v1/videos/video2video",
        poll_url="https://api.key4u.vn/kling/v1/videos/video2video/{task_id}",
        auth_header_name="Authorization",
        auth_header_value="Bearer key4u_secret_test",
        model="kling-video",
        interface="video_to_video_multipart",
        capabilities=("video_to_video",),
    )

    with patch.object(video_real_render_connector, "_selfshot3_provider_configs", return_value=[fake_config]), \
         patch.object(video_real_render_connector, "_materialize_selfshot2_source_segment", return_value=str(source_video)), \
         patch.object(video_ai_edit_provider, "submit_video_edit", side_effect=fake_submit_video_edit), \
         patch.object(video_ai_edit_provider, "download_result", side_effect=fake_download_result):

        result = video_real_render_connector._render_selfshot2_video_to_video(
            job=job,
            asset_pack=asset_pack,
            raw_path=raw_path,
            provider_order=["key4u_video"],
            fallback_prompt="Fallback prompt",
            aspect_ratio="9:16",
            scene_index=1,
        )

    assert result["ok"] is True
    assert result["engine_route"] == "direct_video_to_video"
    assert result["selected_capability"] == "video_to_video"
    assert result["source_uploaded_multipart"] is True
    assert result["source_bound"] is True
    assert result["duration"] == 15
    assert result["scene_duration_seconds"] == 15

    # Verify what was passed to submit_video_edit
    assert captured_call["config"].interface == "video_to_video_multipart"
    assert captured_call["duration_seconds"] == 15
    assert os.path.isfile(captured_call["source_video_path"])


# ---------------------------------------------------------------------------
# CASE B: R05A missing source video -> fail closed before transport
# ---------------------------------------------------------------------------
def test_case_b_r05a_missing_source_video_fails_closed(tmp_path: Path):
    nonexistent_file = str(tmp_path / "does_not_exist.mp4")
    raw_path = str(tmp_path / "output_raw.mp4")

    job = {
        "job_id": "job_40_missing_src",
        "product_type": "self_shot_scene_change",
        "quality_tier": 700,
        "public_user_confirmed": True,
        "submit_source": video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
    }
    asset_pack = {
        "product_type": "self_shot_scene_change",
        "quality_tier": 700,
        "source_video_local_path": nonexistent_file,
        "public_user_confirmed": True,
        "submit_source": video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
    }

    with patch.object(video_ai_edit_provider, "submit_video_edit") as mock_submit:
        with pytest.raises(video_real_render_connector.RealVideoRenderError) as exc_info:
            video_real_render_connector._render_selfshot2_video_to_video(
                job=job,
                asset_pack=asset_pack,
                raw_path=raw_path,
                provider_order=["key4u_video"],
                fallback_prompt="Fallback prompt",
                aspect_ratio="9:16",
                scene_index=1,
            )

        assert "selfshot2_source_video_not_materialized" in str(exc_info.value)
        assert mock_submit.call_count == 0


# ---------------------------------------------------------------------------
# CASE C: Tier700 quality key -> kling_long_audio_15, 15 seconds
# ---------------------------------------------------------------------------
def test_case_c_tier700_quality_key_and_duration():
    route = video_ai_real_pricing.product_video_route_by_tier(700)
    assert route["quality_key"] == "kling_long_audio_15"
    assert route["seconds_per_scene"] == 15
    assert route["tier_id"] == 700
    assert route["two_scene_quote"]["subtotal_xu"] == 440
    assert route["two_scene_quote"]["discount_xu"] == 44
    assert route["two_scene_quote"]["total_xu"] == 396


# ---------------------------------------------------------------------------
# CASE D: motion_pro_audio_10 -> remains 10 seconds, no collision with Tier700
# ---------------------------------------------------------------------------
def test_case_d_motion_pro_audio_10_no_collision_with_tier700():
    route_700 = video_ai_real_pricing.product_video_route_by_tier(700)
    route_800 = video_ai_real_pricing.product_video_route_by_tier(800)

    assert route_700["quality_key"] == "kling_long_audio_15"
    assert route_700["seconds_per_scene"] == 15

    assert route_800["quality_key"] == "motion_pro_audio_10"
    assert route_800["seconds_per_scene"] == 10

    # No collision
    assert route_700["quality_key"] != route_800["quality_key"]
    assert route_700["seconds_per_scene"] != route_800["seconds_per_scene"]


# ---------------------------------------------------------------------------
# CASE E: 2-scene Tier700 -> expected final duration 30
# ---------------------------------------------------------------------------
def test_case_e_2_scene_tier700_expected_duration():
    project = {
        "scene_count": 2,
        "quality_tier": 700,
        "invoice_json": '{"quality_tier": 700, "scene_count": 2, "scene_duration_seconds": 15, "orchestration_mode": "per_scene"}',
    }
    payload = {
        "scene_count": 2,
        "quality_tier": 700,
        "orchestration_mode": "per_scene",
        "scene_duration_seconds": 15,
    }

    expected = video_project_queue.product_video_expected_duration_seconds(project, payload)
    assert expected == 30, f"Expected 30 seconds for 2-scene Tier 700, got {expected}"

    # Also test scene duration helper in video_real_render_connector
    job = {
        "quality_tier": 700,
        "scene_count": 2,
        "scene_duration_seconds": 15,
        "invoice": {"quality_tier": 700, "scene_duration_seconds": 15},
    }
    scene_sec = video_real_render_connector.product_video_scene_duration_seconds(job)
    assert scene_sec == 15, f"Expected 15 seconds per scene for Tier 700, got {scene_sec}"


# ---------------------------------------------------------------------------
# CASE F: manual continuity booleans only -> independent visual validation NOT proven
# ---------------------------------------------------------------------------
def test_case_f_manual_continuity_metadata_provenance(tmp_path: Path):
    final_video = tmp_path / "final.mp4"
    final_video.write_bytes(b"FAKE_FINAL_MP4_CONTENT")

    job = {
        "scene_count": 2,
        "asset_pack": {
            "subject_manifest": {
                "person_subject_ids": ["person-1"],
                "object_subject_ids": ["object-1"],
            }
        },
    }
    output = {
        "final_video_path": str(final_video),
        "output_bytes": len(b"FAKE_FINAL_MP4_CONTENT"),
        "has_video": True,
        "validation_status": "candidate_mp4_valid",
        "concat_ready": True,
    }
    scene_tasks = [
        {"scene_index": 1, "status": "downloaded", "clip_valid": True},
        {"scene_index": 2, "status": "downloaded", "clip_valid": True},
    ]
    debug_results = [
        {
            "scene_index": 1,
            "continuity_evidence": {
                "person_identity": True,
                "object_identity": True,
                "person_object_relationship": True,
            },
        },
        {
            "scene_index": 2,
            "continuity_evidence": {
                "person_identity": True,
                "object_identity": True,
                "person_object_relationship": True,
            },
        },
    ]

    res = video_real_render_connector.selfshot2_continuity_validation(
        job,
        output,
        scene_tasks=scene_tasks,
        debug_results=debug_results,
    )

    # Metadata contract passes for downstream pipeline
    assert res["ok"] is True
    assert res["metadata_contract_pass"] is True
    assert res["continuity_metadata_present"] is True

    # But independent visual validation is NOT performed / NOT proven
    assert res["independent_visual_validation"] == "NOT_PERFORMED"
    assert res["independent_visual_validation_pass"] is False
    assert res["independent_visual_continuity_proven"] is False


# ---------------------------------------------------------------------------
# CASE G: non-R05A existing product routes -> unchanged
# ---------------------------------------------------------------------------
def test_case_g_non_r05a_existing_product_routes_unchanged():
    # Non-R05A existing product normalization and route contracts
    assert video_final_output.normalize_video_product_type("video_idea") == "video_idea_to_product"
    route_idea = video_final_output.route_for_product_type("video_idea")
    assert route_idea["product_type"] == "video_idea_to_product"
    assert route_idea["engine_adapter"] == "delegates_to_selected_product"

    route_prompt = video_final_output.route_for_product_type("video_ai_prompt")
    assert route_prompt["engine_adapter"] == "text_to_video"

    route_image = video_final_output.route_for_product_type("video_ai_image")
    assert route_image["engine_adapter"] == "image_to_video"

    route_multiscene = video_final_output.route_for_product_type("multi_scene_film")
    assert route_multiscene["engine_adapter"] == "multiscene_render_and_stitch"

    contract_ss2 = video_project_queue.product_video_engine_contract("self_shot_scene_change")
    assert contract_ss2["required_capability"] == "video_to_video"
    assert contract_ss2["engine_route"] == "self_shot_scene_change"
