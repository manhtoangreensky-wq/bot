"""Tests for P0.PRODUCT_VIDEO.SELF_SHOT_SCENE_CHANGE.LOCAL.VISION.VALIDATOR.INTEGRATION.R1

Empirical integration proof for local scene continuity validator:
- Person lane (YuNet + SFace)
- Object lane (SIFT + FLANN + RANSAC)
- Relationship lane (spatial proximity Drel)
- Fail-closed integration into services/video_real_render_connector.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch
import pytest

from services import video_ai_edit_provider
from services import video_real_render_connector
from services.video_real_render_connector import (
    RealVideoRenderError,
    _render_selfshot2_video_to_video,
    selfshot2_continuity_validation,
)
from services.video_selfshot_continuity_validator import (
    CALIBRATED_OBJECT_MIN_RANSAC_INLIERS,
    CALIBRATED_PERSON_THRESHOLD,
    CALIBRATED_RELATIONSHIP_DISTANCE_MAX,
    EVIDENCE_SOURCE,
    PRIMARY_RELATION_TYPE,
    validate_selfshot_scene_continuity,
)


def _mock_provider_config() -> video_ai_edit_provider.AiEditProviderConfig:
    return video_ai_edit_provider.AiEditProviderConfig(
        provider_name="key4u_video",
        enabled=True,
        submit_url="https://api.key4u.vn/v1/video/generations",
        poll_url="https://api.key4u.vn/v1/video/generations/{task_id}",
        auth_header_name="Authorization",
        auth_header_value="Bearer test-token",
        model="kling-video",
        interface="video_to_video_multipart",
        capabilities=("video_to_video",),
    )


def test_first_red_render_connector_fails_closed_when_local_continuity_fails(tmp_path: Path) -> None:
    """FIRST RED -> GREEN: render connector invokes local continuity validator and fails closed on failure."""
    source_file = tmp_path / "source.mp4"
    source_file.write_bytes(b"dummy-source-video")
    out_file = tmp_path / "raw_out.mp4"

    fake_config = _mock_provider_config()

    def fake_submit(config, **kwargs):
        return {
            "provider_task_id": "test-task-red",
            "status": "completed",
            "result_url": "https://example.com/red.mp4",
            "result_url_present": True,
        }

    def fake_download(url, target_path):
        p = Path(target_path)
        p.write_bytes(b"dummy-downloaded-video")
        return {"path": str(p)}

    job = {
        "job_id": "job-red-test",
        "product_type": "self_shot_scene_change",
        "source_video_local_path": str(source_file),
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "quality_tier": 500,
        "asset_pack": {
            "subject_manifest": {
                "person_subject_ids": ["p1"],
                "object_subject_ids": ["o1"],
            },
        },
    }

    with patch("services.video_real_render_connector._selfshot3_provider_configs", return_value=[fake_config]), \
         patch("services.video_real_render_connector._materialize_selfshot2_source_segment", return_value=str(source_file)), \
         patch("services.video_ai_edit_provider.submit_video_edit", side_effect=fake_submit), \
         patch("services.video_ai_edit_provider.download_result", side_effect=fake_download), \
         patch("services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity") as mock_validator:

        mock_validator.return_value = {
            "ok": False,
            "blocker": "person_identity_failed",
            "failure_reason": "person_identity_failed",
            "evidence_source": EVIDENCE_SOURCE,
        }

        with pytest.raises(RealVideoRenderError) as exc_info:
            _render_selfshot2_video_to_video(
                job=job,
                asset_pack=job["asset_pack"],
                raw_path=str(out_file),
                provider_order=["key4u_video"],
                fallback_prompt="test",
                aspect_ratio="9:16",
                scene_index=1,
            )

        assert mock_validator.called, "validate_selfshot_scene_continuity was not called by render connector!"
        assert "person_identity_failed" in str(exc_info.value)


def test_local_validator_all_three_lanes_pass() -> None:
    """1. All three required lanes pass -> scene PASS."""
    mock_frames = [
        {"person_ok": True, "object_ok": True, "relationship_ok": True},
        {"person_ok": True, "object_ok": True, "relationship_ok": True},
        {"person_ok": True, "object_ok": True, "relationship_ok": True},
    ]
    res = validate_selfshot_scene_continuity(
        "dummy.mp4",
        scene_index=1,
        scene_duration_seconds=5,
        person_required=True,
        object_required=True,
        relationship_required=True,
        mock_frame_observations=mock_frames,
    )
    assert res["ok"] is True
    assert res["person_identity"] is True
    assert res["object_identity"] is True
    assert res["person_object_relationship"] is True
    assert res["evidence_source"] == EVIDENCE_SOURCE
    assert res["independent_visual_validation"] == "LOCAL_MODEL"
    assert res["blocker"] == ""


def test_local_validator_person_fails() -> None:
    """2. Person lane fails -> integrated scene FAIL."""
    mock_frames = [
        {"person_ok": False, "object_ok": True, "relationship_ok": True},
        {"person_ok": False, "object_ok": True, "relationship_ok": True},
        {"person_ok": True, "object_ok": True, "relationship_ok": True},
    ]
    res = validate_selfshot_scene_continuity(
        "dummy.mp4",
        scene_index=1,
        scene_duration_seconds=5,
        person_required=True,
        object_required=True,
        relationship_required=True,
        mock_frame_observations=mock_frames,
    )
    assert res["ok"] is False
    assert res["person_identity"] is False
    assert res["blocker"] == "insufficient_temporal_evidence"
    assert res["independent_visual_validation"] == "NOT_PERFORMED"


def test_local_validator_object_fails() -> None:
    """3. Object lane fails -> integrated scene FAIL."""
    mock_frames = [
        {"person_ok": True, "object_ok": False, "relationship_ok": True},
        {"person_ok": True, "object_ok": False, "relationship_ok": True},
        {"person_ok": True, "object_ok": True, "relationship_ok": True},
    ]
    res = validate_selfshot_scene_continuity(
        "dummy.mp4",
        scene_index=1,
        scene_duration_seconds=5,
        person_required=True,
        object_required=True,
        relationship_required=True,
        mock_frame_observations=mock_frames,
    )
    assert res["ok"] is False
    assert res["object_identity"] is False
    assert res["blocker"] == "insufficient_temporal_evidence"


def test_local_validator_relationship_fails() -> None:
    """4. Relationship lane fails -> integrated scene FAIL."""
    mock_frames = [
        {"person_ok": True, "object_ok": True, "relationship_ok": False},
        {"person_ok": True, "object_ok": True, "relationship_ok": False},
        {"person_ok": True, "object_ok": True, "relationship_ok": True},
    ]
    res = validate_selfshot_scene_continuity(
        "dummy.mp4",
        scene_index=1,
        scene_duration_seconds=5,
        person_required=True,
        object_required=True,
        relationship_required=True,
        mock_frame_observations=mock_frames,
    )
    assert res["ok"] is False
    assert res["person_object_relationship"] is False
    assert res["blocker"] == "insufficient_temporal_evidence"


def test_transport_success_without_local_evidence_fails(tmp_path: Path) -> None:
    """5. Transport succeeds but local evidence absent -> FAIL independent visual validation."""
    mp4_path = tmp_path / "final.mp4"
    mp4_path.write_bytes(b"dummy-mp4-content")
    output = {
        "final_video_path": str(mp4_path),
        "output_bytes": mp4_path.stat().st_size,
        "has_video": True,
        "validation_status": "candidate_mp4_valid_full",
        "concat_ready": True,
    }
    job = {
        "product_type": "self_shot_scene_change",
        "scene_count": 1,
        "asset_pack": {
            "subject_manifest": {
                "person_subject_ids": ["p1"],
                "object_subject_ids": ["o1"],
            }
        },
    }
    validation = selfshot2_continuity_validation(
        job,
        output,
        scene_tasks=[{"scene_index": 1, "status": "downloaded", "clip_valid": True}],
        debug_results=[],  # No local validator evidence
    )
    assert validation["ok"] is False
    assert validation["independent_visual_continuity_proven"] is False
    assert validation["independent_visual_validation"] == "NOT_PERFORMED"


def test_manual_boolean_bypass_fails_closed(tmp_path: Path) -> None:
    """6. Manual continuity booleans without local validator provenance fail closed."""
    mp4_path = tmp_path / "final.mp4"
    mp4_path.write_bytes(b"dummy-mp4-content")
    output = {
        "final_video_path": str(mp4_path),
        "output_bytes": mp4_path.stat().st_size,
        "has_video": True,
        "validation_status": "candidate_mp4_valid_full",
        "concat_ready": True,
    }
    job = {
        "product_type": "self_shot_scene_change",
        "scene_count": 1,
        "asset_pack": {
            "subject_manifest": {
                "person_subject_ids": ["p1"],
                "object_subject_ids": ["o1"],
            }
        },
    }
    # Payload has True booleans, but NO evidence_source="local_vision_validator"
    manual_payload = {
        "scene_index": 1,
        "continuity_evidence": {
            "person_identity": True,
            "object_identity": True,
            "person_object_relationship": True,
        },
    }
    validation = selfshot2_continuity_validation(
        job,
        output,
        scene_tasks=[{"scene_index": 1, "status": "downloaded", "clip_valid": True}],
        debug_results=[manual_payload],
    )
    assert validation["independent_visual_continuity_proven"] is False
    assert validation["independent_visual_validation"] == "NOT_PERFORMED"
    assert validation["independent_visual_validation_pass"] is False


def test_temporal_aggregation_2_of_3_pass() -> None:
    """7. 2/3 integrated frames -> scene PASS for 5s scene."""
    mock_frames = [
        {"person_ok": True, "object_ok": True, "relationship_ok": True},
        {"person_ok": False, "object_ok": True, "relationship_ok": True},  # 1 frame fails
        {"person_ok": True, "object_ok": True, "relationship_ok": True},
    ]
    res = validate_selfshot_scene_continuity(
        "dummy.mp4",
        scene_index=1,
        scene_duration_seconds=5,
        person_required=True,
        object_required=True,
        relationship_required=True,
        mock_frame_observations=mock_frames,
    )
    assert res["ok"] is True
    assert res["independent_visual_validation"] == "LOCAL_MODEL"


def test_temporal_aggregation_1_of_3_fails() -> None:
    """8. 1/3 integrated frames -> scene FAIL for 5s scene."""
    mock_frames = [
        {"person_ok": True, "object_ok": True, "relationship_ok": True},   # Only 1 passes
        {"person_ok": False, "object_ok": True, "relationship_ok": True},
        {"person_ok": True, "object_ok": False, "relationship_ok": True},
    ]
    res = validate_selfshot_scene_continuity(
        "dummy.mp4",
        scene_index=1,
        scene_duration_seconds=5,
        person_required=True,
        object_required=True,
        relationship_required=True,
        mock_frame_observations=mock_frames,
    )
    assert res["ok"] is False
    assert res["blocker"] == "insufficient_temporal_evidence"


def test_temporal_aggregation_3_of_5_pass() -> None:
    """9. 3/5 integrated frames -> scene PASS for 10s/15s scene."""
    mock_frames = [
        {"person_ok": True, "object_ok": True, "relationship_ok": True},
        {"person_ok": False, "object_ok": True, "relationship_ok": True},
        {"person_ok": True, "object_ok": True, "relationship_ok": True},
        {"person_ok": True, "object_ok": False, "relationship_ok": True},
        {"person_ok": True, "object_ok": True, "relationship_ok": True},
    ]
    res = validate_selfshot_scene_continuity(
        "dummy.mp4",
        scene_index=1,
        scene_duration_seconds=10,
        person_required=True,
        object_required=True,
        relationship_required=True,
        mock_frame_observations=mock_frames,
    )
    assert res["ok"] is True
    assert res["sampled_frame_count"] == 5
    assert res["independent_visual_validation"] == "LOCAL_MODEL"


def test_temporal_aggregation_2_of_5_fails() -> None:
    """10. 2/5 integrated frames -> scene FAIL for 10s/15s scene."""
    mock_frames = [
        {"person_ok": True, "object_ok": True, "relationship_ok": True},
        {"person_ok": False, "object_ok": True, "relationship_ok": True},
        {"person_ok": True, "object_ok": True, "relationship_ok": True},
        {"person_ok": False, "object_ok": False, "relationship_ok": True},
        {"person_ok": True, "object_ok": False, "relationship_ok": True},
    ]
    res = validate_selfshot_scene_continuity(
        "dummy.mp4",
        scene_index=1,
        scene_duration_seconds=15,
        person_required=True,
        object_required=True,
        relationship_required=True,
        mock_frame_observations=mock_frames,
    )
    assert res["ok"] is False
    assert res["blocker"] == "insufficient_temporal_evidence"


def test_scene_evidence_isolation(tmp_path: Path) -> None:
    """11. Scene-1 evidence cannot satisfy Scene-2."""
    mp4_path = tmp_path / "final.mp4"
    mp4_path.write_bytes(b"dummy-mp4-content")
    output = {
        "final_video_path": str(mp4_path),
        "output_bytes": mp4_path.stat().st_size,
        "has_video": True,
        "validation_status": "candidate_mp4_valid_full",
        "concat_ready": True,
    }
    job = {
        "product_type": "self_shot_scene_change",
        "scene_count": 2,
        "asset_pack": {
            "subject_manifest": {
                "person_subject_ids": ["p1"],
                "object_subject_ids": ["o1"],
            }
        },
    }
    # Only Scene 1 has valid local evidence; Scene 2 does not
    scene1_local_evidence = {
        "scene_index": 1,
        "evidence_source": EVIDENCE_SOURCE,
        "person_identity": True,
        "object_identity": True,
        "person_object_relationship": True,
    }
    validation = selfshot2_continuity_validation(
        job,
        output,
        scene_tasks=[
            {"scene_index": 1, "status": "downloaded", "clip_valid": True},
            {"scene_index": 2, "status": "downloaded", "clip_valid": True},
        ],
        debug_results=[scene1_local_evidence],
    )
    assert validation["ok"] is False
    assert validation["independent_visual_continuity_proven"] is False
    assert validation["continuity_missing_scene_indexes"] == [2]


def test_unsupported_relation_type_fails_closed() -> None:
    """12. Unsupported relationship type fails closed."""
    res = validate_selfshot_scene_continuity(
        "dummy.mp4",
        scene_index=1,
        scene_duration_seconds=5,
        person_required=True,
        object_required=True,
        relationship_required=True,
        relationship_type="drinking_from",
        mock_frame_observations=[{"person_ok": True, "object_ok": True, "relationship_ok": True}],
    )
    assert res["ok"] is False
    assert res["blocker"] == "unsupported_relation_type"
    assert res["failure_reason"] == "unsupported_relation_type"


def test_validator_exception_fails_closed(tmp_path: Path) -> None:
    """13. Validator exception fails closed."""
    # When person validator raises an unexpected error during real frame evaluation
    import numpy as np
    dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)

    with patch("services.video_selfshot_continuity_validator.verify_person_identity", side_effect=RuntimeError("internal_dnn_crash")):
        res = validate_selfshot_scene_continuity(
            [dummy_frame, dummy_frame, dummy_frame],
            scene_index=1,
            scene_duration_seconds=5,
            person_required=True,
            object_required=False,
            relationship_required=False,
            person_reference=dummy_frame,
        )
        assert res["ok"] is False
        assert "validator_exception" in res["failure_reason"]
        assert "person_validator_exception" in res["blocker"]


def test_person_only_cardinality_contract() -> None:
    """14. Person-only required scene follows cardinality contract."""
    mock_frames = [
        {"person_ok": True},
        {"person_ok": True},
        {"person_ok": True},
    ]
    res = validate_selfshot_scene_continuity(
        "dummy.mp4",
        scene_index=1,
        scene_duration_seconds=5,
        person_required=True,
        object_required=False,
        relationship_required=False,
        mock_frame_observations=mock_frames,
    )
    assert res["ok"] is True
    assert res["person_identity"] is True
    assert res["object_identity"] is False  # not required, not fabricated as proven
    assert res["person_object_relationship"] is False


def test_object_only_cardinality_contract() -> None:
    """15. Object-only required scene follows cardinality contract."""
    mock_frames = [
        {"object_ok": True},
        {"object_ok": True},
        {"object_ok": True},
    ]
    res = validate_selfshot_scene_continuity(
        "dummy.mp4",
        scene_index=1,
        scene_duration_seconds=5,
        person_required=False,
        object_required=True,
        relationship_required=False,
        mock_frame_observations=mock_frames,
    )
    assert res["ok"] is True
    assert res["person_identity"] is False
    assert res["object_identity"] is True
    assert res["person_object_relationship"] is False


def test_render_connector_passes_when_all_lanes_pass(tmp_path: Path) -> None:
    """16. Render connector accepts scene when local visual continuity passes."""
    source_file = tmp_path / "source.mp4"
    source_file.write_bytes(b"dummy-source-video")
    out_file = tmp_path / "raw_out.mp4"

    fake_config = _mock_provider_config()

    def fake_submit(config, **kwargs):
        return {
            "provider_task_id": "test-task-green",
            "status": "completed",
            "result_url": "https://example.com/green.mp4",
            "result_url_present": True,
        }

    def fake_download(url, target_path):
        p = Path(target_path)
        p.write_bytes(b"dummy-downloaded-video")
        return {"path": str(p)}

    job = {
        "job_id": "job-green-test",
        "product_type": "self_shot_scene_change",
        "source_video_local_path": str(source_file),
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "quality_tier": 500,
        "asset_pack": {
            "subject_manifest": {
                "person_subject_ids": ["p1"],
                "object_subject_ids": ["o1"],
            },
            "mock_frame_observations": [
                {"person_ok": True, "object_ok": True, "relationship_ok": True},
                {"person_ok": True, "object_ok": True, "relationship_ok": True},
                {"person_ok": True, "object_ok": True, "relationship_ok": True},
            ],
        },
    }

    with patch("services.video_real_render_connector._selfshot3_provider_configs", return_value=[fake_config]), \
         patch("services.video_real_render_connector._materialize_selfshot2_source_segment", return_value=str(source_file)), \
         patch("services.video_ai_edit_provider.submit_video_edit", side_effect=fake_submit), \
         patch("services.video_ai_edit_provider.download_result", side_effect=fake_download):

        result = _render_selfshot2_video_to_video(
            job=job,
            asset_pack=job["asset_pack"],
            raw_path=str(out_file),
            provider_order=["key4u_video"],
            fallback_prompt="test",
            aspect_ratio="9:16",
            scene_index=1,
        )

        assert result["ok"] is True
        assert result["continuity_evidence_present"] is True
        evidence = result["continuity_evidence"]
        assert evidence["evidence_source"] == EVIDENCE_SOURCE
        assert evidence["independent_visual_validation"] == "LOCAL_MODEL"
        assert evidence["person_identity"] is True
        assert evidence["object_identity"] is True
        assert evidence["person_object_relationship"] is True
