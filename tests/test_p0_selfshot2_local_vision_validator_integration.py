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

    with patch("services.video_real_render_connector._selfshot2_provider_configs", return_value=[fake_config]), \
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
    assert res["evidence_source"] == "test_mock"
    assert res["independent_visual_validation"] == "NOT_PERFORMED"
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
    assert res["evidence_source"] == "test_mock"
    assert res["independent_visual_validation"] == "NOT_PERFORMED"


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
    assert res["evidence_source"] == "test_mock"
    assert res["independent_visual_validation"] == "NOT_PERFORMED"


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
    """16. Render connector accepts scene when genuine local visual continuity passes."""
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
        },
    }

    genuine_evidence = {
        "ok": True,
        "evidence_source": EVIDENCE_SOURCE,
        "independent_visual_validation": "LOCAL_MODEL",
        "person_identity": True,
        "object_identity": True,
        "person_object_relationship": True,
        "blocker": "",
        "failure_reason": "",
    }

    with patch("services.video_real_render_connector._selfshot2_provider_configs", return_value=[fake_config]), \
         patch("services.video_real_render_connector._materialize_selfshot2_source_segment", return_value=str(source_file)), \
         patch("services.video_ai_edit_provider.submit_video_edit", side_effect=fake_submit), \
         patch("services.video_ai_edit_provider.download_result", side_effect=fake_download), \
         patch("services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity", return_value=genuine_evidence) as mock_val:

        result = _render_selfshot2_video_to_video(
            job=job,
            asset_pack=job["asset_pack"],
            raw_path=str(out_file),
            provider_order=["key4u_video"],
            fallback_prompt="test",
            aspect_ratio="9:16",
            scene_index=1,
        )

        assert mock_val.called
        assert result["ok"] is True
        assert result["continuity_evidence_present"] is True
        evidence = result["continuity_evidence"]
        assert evidence["evidence_source"] == EVIDENCE_SOURCE
        assert evidence["independent_visual_validation"] == "LOCAL_MODEL"
        assert evidence["person_identity"] is True
        assert evidence["object_identity"] is True
        assert evidence["person_object_relationship"] is True


def test_asset_pack_mock_observations_rejected_and_connector_fails_closed(tmp_path: Path) -> None:
    """17. asset_pack['mock_frame_observations'] is rejected by validator and connector fails closed."""
    # 1. Direct validator invocation with asset_pack containing mock_frame_observations
    asset_pack = {
        "subject_manifest": {"person_subject_ids": ["p1"], "object_subject_ids": ["o1"]},
        "mock_frame_observations": [
            {"person_ok": True, "object_ok": True, "relationship_ok": True},
            {"person_ok": True, "object_ok": True, "relationship_ok": True},
            {"person_ok": True, "object_ok": True, "relationship_ok": True},
        ],
    }
    # No real person_reference provided -> validator must NOT consume asset_pack mock and must fail closed
    res = validate_selfshot_scene_continuity(
        "dummy.mp4",
        scene_index=1,
        scene_duration_seconds=5,
        asset_pack=asset_pack,
    )
    assert res["ok"] is False
    assert res["independent_visual_validation"] == "NOT_PERFORMED"
    assert res["blocker"] == "selfshot2_person_reference_missing"

    # 2. Render connector with asset_pack mock fails closed
    source_file = tmp_path / "source.mp4"
    source_file.write_bytes(b"dummy-source-video")
    out_file = tmp_path / "raw_out.mp4"
    fake_config = _mock_provider_config()

    def fake_submit(config, **kwargs):
        return {"provider_task_id": "test-task", "status": "completed", "result_url": "https://example.com/v.mp4", "result_url_present": True}

    def fake_download(url, target_path):
        p = Path(target_path)
        p.write_bytes(b"dummy-downloaded-video")
        return {"path": str(p)}

    job = {
        "job_id": "job-mock-bypass-test",
        "product_type": "self_shot_scene_change",
        "source_video_local_path": str(source_file),
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "quality_tier": 500,
        "asset_pack": asset_pack,
    }

    with patch("services.video_real_render_connector._selfshot2_provider_configs", return_value=[fake_config]), \
         patch("services.video_real_render_connector._materialize_selfshot2_source_segment", return_value=str(source_file)), \
         patch("services.video_ai_edit_provider.submit_video_edit", side_effect=fake_submit), \
         patch("services.video_ai_edit_provider.download_result", side_effect=fake_download):

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
        assert "selfshot2_person_reference_missing" in str(exc_info.value)


def test_job_mock_observations_rejected_and_connector_fails_closed(tmp_path: Path) -> None:
    """18. job['mock_frame_observations'] is rejected by validator and connector fails closed."""
    job = {
        "job_id": "job-mock-job-bypass-test",
        "product_type": "self_shot_scene_change",
        "quality_tier": 500,
        "mock_frame_observations": [
            {"person_ok": True, "object_ok": True, "relationship_ok": True},
            {"person_ok": True, "object_ok": True, "relationship_ok": True},
            {"person_ok": True, "object_ok": True, "relationship_ok": True},
        ],
        "asset_pack": {
            "subject_manifest": {"person_subject_ids": ["p1"], "object_subject_ids": ["o1"]},
        },
    }
    # No real person_reference provided -> validator must NOT consume job mock and must fail closed
    res = validate_selfshot_scene_continuity(
        "dummy.mp4",
        scene_index=1,
        scene_duration_seconds=5,
        job=job,
    )
    assert res["ok"] is False
    assert res["independent_visual_validation"] == "NOT_PERFORMED"
    assert res["blocker"] == "selfshot2_person_reference_missing"


def test_real_local_model_path_executes_validators_and_produces_local_model() -> None:
    """19. Legitimate real local validation executes models and produces LOCAL_MODEL provenance."""
    import cv2
    repo_root = Path(__file__).resolve().parents[1]
    person_ref_path = repo_root / "tests" / "fixtures" / "selfshot_vision" / "person_calibration" / "obama_obs1.jpg"
    person_cand_path = repo_root / "tests" / "fixtures" / "selfshot_vision" / "person_calibration" / "obama_obs2.jpg"

    assert person_ref_path.is_file(), f"Missing fixture {person_ref_path}"
    assert person_cand_path.is_file(), f"Missing fixture {person_cand_path}"

    cand_frame = cv2.imread(str(person_cand_path))
    frames = [cand_frame, cand_frame, cand_frame]

    res = validate_selfshot_scene_continuity(
        frames,
        scene_index=1,
        scene_duration_seconds=5,
        person_required=True,
        object_required=False,
        relationship_required=False,
        person_reference=str(person_ref_path),
    )
    assert res["ok"] is True
    assert res["person_identity"] is True
    assert res["evidence_source"] == EVIDENCE_SOURCE
    assert res["independent_visual_validation"] == "LOCAL_MODEL"
    assert res["blocker"] == ""
    assert res["failure_reason"] == ""
    assert len(res["person_observations"]) == 3
    assert all(obs["person_ok"] is True for obs in res["person_observations"])


def test_real_object_homography_localization_and_ground_truth_sanity() -> None:
    """20. Real SIFT/FLANN/RANSAC homography derives candidate object localization matching ground truth."""
    import math
    import cv2
    from services.video_selfshot_object_validator import verify_object_identity
    repo_root = Path(__file__).resolve().parents[1]
    obj_ref_path = repo_root / "tests" / "fixtures" / "selfshot_vision" / "object_calibration" / "snuff_bottle_coins_obs1.jpg"
    obj_cand_path = repo_root / "tests" / "fixtures" / "selfshot_vision" / "object_calibration" / "snuff_bottle_coins_obs2.jpg"

    assert obj_ref_path.is_file(), f"Missing fixture {obj_ref_path}"
    assert obj_cand_path.is_file(), f"Missing fixture {obj_cand_path}"

    ref_roi = [130, 120, 200, 390]
    gt_cand_roi = [129, 119, 194, 382]

    # Verify with full candidate frame search space
    cand_img = cv2.imread(str(obj_cand_path))
    ch, cw = cand_img.shape[:2]
    res = verify_object_identity(
        obj_ref_path,
        obj_cand_path,
        reference_roi=ref_roi,
        candidate_roi=[0, 0, cw, ch],
    )
    assert res["decision"] is True
    assert res["homography_available"] is True
    assert res["ransac_inlier_count"] >= 25
    assert res["candidate_object_bbox"] is not None

    proj_bbox = res["candidate_object_bbox"]
    px, py, pw, ph = proj_bbox
    assert pw > 0 and ph > 0
    assert 0 <= px < cw and 0 <= py < ch

    # Ground truth sanity comparison
    gx, gy, gw, gh = gt_cand_roi
    center_dist = math.hypot((px + pw / 2) - (gx + gw / 2), (py + ph / 2) - (gy + gh / 2))
    assert center_dist < 10.0, f"Projected center deviated too far from ground truth: {center_dist}"

    # IoU
    ix1, iy1 = max(px, gx), max(py, gy)
    ix2, iy2 = min(px + pw, gx + gw), min(py + ph, gy + gh)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = (pw * ph) + (gw * gh) - inter
    iou = inter / union if union > 0.0 else 0.0
    assert iou > 0.80, f"Projected bbox IoU below expectation: {iou}"


def test_real_person_plus_object_plus_relationship_all_three_lanes_end_to_end() -> None:
    """21. Real execution across person + object + relationship lanes with same-frame localization."""
    import cv2
    import numpy as np
    repo_root = Path(__file__).resolve().parents[1]
    person_ref_path = repo_root / "tests" / "fixtures" / "selfshot_vision" / "person_calibration" / "obama_obs1.jpg"
    person_cand_path = repo_root / "tests" / "fixtures" / "selfshot_vision" / "person_calibration" / "obama_obs2.jpg"
    object_ref_path = repo_root / "tests" / "fixtures" / "selfshot_vision" / "object_calibration" / "snuff_bottle_coins_obs1.jpg"
    object_cand_path = repo_root / "tests" / "fixtures" / "selfshot_vision" / "object_calibration" / "snuff_bottle_coins_obs2.jpg"

    assert person_ref_path.is_file(), f"Missing fixture {person_ref_path}"
    assert person_cand_path.is_file(), f"Missing fixture {person_cand_path}"
    assert object_ref_path.is_file(), f"Missing fixture {object_ref_path}"
    assert object_cand_path.is_file(), f"Missing fixture {object_cand_path}"

    img_p2 = cv2.imread(str(person_cand_path))
    img_o2 = cv2.imread(str(object_cand_path))

    # Composite onto wide canvas: Obama on left, snuff bottle adjacent to ensure Drel <= 0.281528
    canvas = np.zeros((800, 1400, 3), dtype=np.uint8)
    hp, wp = img_p2.shape[:2]
    canvas[50:50+hp, 50:50+wp] = img_p2
    ho, wo = img_o2.shape[:2]
    canvas[50:50+ho, 400:400+wo] = img_o2

    frames = [canvas, canvas, canvas]

    res = validate_selfshot_scene_continuity(
        frames,
        scene_index=1,
        scene_duration_seconds=5,
        person_required=True,
        object_required=True,
        relationship_required=True,
        person_reference=str(person_ref_path),
        object_reference=str(object_ref_path),
        object_reference_roi=[130, 120, 200, 390],
    )

    assert res["ok"] is True
    assert res["person_identity"] is True
    assert res["object_identity"] is True
    assert res["person_object_relationship"] is True
    assert res["evidence_source"] == EVIDENCE_SOURCE
    assert res["independent_visual_validation"] == "LOCAL_MODEL"
    assert res["blocker"] == ""
    assert res["failure_reason"] == ""

    # Verify same-frame geometry inputs
    assert len(res["person_observations"]) == 3
    assert len(res["object_observations"]) == 3
    assert len(res["relationship_observations"]) == 3
    for p_obs, o_obs, r_obs in zip(res["person_observations"], res["object_observations"], res["relationship_observations"]):
        assert p_obs["person_ok"] is True
        assert p_obs["person_bbox"] is not None
        assert o_obs["object_ok"] is True
        assert o_obs["object_bbox"] is not None
        assert r_obs["relationship_ok"] is True


def test_invalid_geometry_localization_regressions_fail_closed() -> None:
    """22. Fail-closed regressions for invalid homography localization geometries."""
    from unittest.mock import patch
    import numpy as np
    from services.video_selfshot_object_validator import verify_object_identity
    repo_root = Path(__file__).resolve().parents[1]
    obj_ref = repo_root / "tests" / "fixtures" / "selfshot_vision" / "object_calibration" / "snuff_bottle_coins_obs1.jpg"
    obj_cand = repo_root / "tests" / "fixtures" / "selfshot_vision" / "object_calibration" / "snuff_bottle_coins_obs2.jpg"
    ref_roi = [130, 120, 200, 390]
    cand_roi = [0, 0, 450, 600]

    # 1. Invalid perspective transform (returns None or != 4 points)
    with patch("cv2.perspectiveTransform", return_value=None):
        res = verify_object_identity(obj_ref, obj_cand, reference_roi=ref_roi, candidate_roi=cand_roi)
        assert res["decision"] is False
        assert res["object_identity"] is False
        assert res["candidate_object_bbox"] is None
        assert res["failure_reason"] == "invalid_perspective_transform"

    # 2. Nonfinite projected coordinates (NaN/Inf)
    with patch("cv2.perspectiveTransform", return_value=np.array([[[np.nan, 0]], [[100, 0]], [[100, 100]], [[0, 100]]])):
        res = verify_object_identity(obj_ref, obj_cand, reference_roi=ref_roi, candidate_roi=cand_roi)
        assert res["decision"] is False
        assert res["object_identity"] is False
        assert res["candidate_object_bbox"] is None
        assert res["failure_reason"] == "nonfinite_projected_coordinates"

    # 3. Degenerate quad area (collinear points / area <= 0)
    with patch("cv2.perspectiveTransform", return_value=np.array([[[0, 0]], [[0, 0]], [[0, 0]], [[0, 0]]])):
        res = verify_object_identity(obj_ref, obj_cand, reference_roi=ref_roi, candidate_roi=cand_roi)
        assert res["decision"] is False
        assert res["object_identity"] is False
        assert res["candidate_object_bbox"] is None
        assert res["failure_reason"] == "degenerate_quad_area"

    # 4. Projected bbox outside frame
    with patch("cv2.perspectiveTransform", return_value=np.array([[[2000, 2000]], [[2100, 2000]], [[2100, 2100]], [[2000, 2100]]])):
        res = verify_object_identity(obj_ref, obj_cand, reference_roi=ref_roi, candidate_roi=cand_roi)
        assert res["decision"] is False
        assert res["object_identity"] is False
        assert res["candidate_object_bbox"] is None
        assert res["failure_reason"] == "projected_bbox_outside_frame"

    # 5. Degenerate clamped bbox (clamping collapses width or height)
    with patch("cv2.perspectiveTransform", return_value=np.array([[[0, 0]], [[0, 0]], [[0, 100]], [[0, 100]]])):
        res = verify_object_identity(obj_ref, obj_cand, reference_roi=ref_roi, candidate_roi=cand_roi)
        assert res["decision"] is False
        assert res["object_identity"] is False
        assert res["candidate_object_bbox"] is None

    # 6. Localization exception
    with patch("cv2.perspectiveTransform", side_effect=RuntimeError("internal_cv_error")):
        res = verify_object_identity(obj_ref, obj_cand, reference_roi=ref_roi, candidate_roi=cand_roi)
        assert res["decision"] is False
        assert res["object_identity"] is False
        assert res["candidate_object_bbox"] is None
        assert "localization_exception" in res["failure_reason"]

    # 7. Valid projection succeeds
    res_valid = verify_object_identity(obj_ref, obj_cand, reference_roi=ref_roi, candidate_roi=cand_roi)
    assert res_valid["decision"] is True
    assert res_valid["object_identity"] is True
    assert res_valid["candidate_object_bbox"] is not None


def test_object_only_scene_fails_closed_when_localization_fails() -> None:
    """23. Object-only scene fails closed when SIFT matches but localization geometry fails."""
    from unittest.mock import patch
    import cv2
    import numpy as np
    repo_root = Path(__file__).resolve().parents[1]
    obj_ref = repo_root / "tests" / "fixtures" / "selfshot_vision" / "object_calibration" / "snuff_bottle_coins_obs1.jpg"
    obj_cand = repo_root / "tests" / "fixtures" / "selfshot_vision" / "object_calibration" / "snuff_bottle_coins_obs2.jpg"
    cand_img = cv2.imread(str(obj_cand))
    frames = [cand_img, cand_img, cand_img]

    # Localization fails via nonfinite projection
    with patch("cv2.perspectiveTransform", return_value=np.array([[[np.nan, 0]], [[100, 0]], [[100, 100]], [[0, 100]]])):
        res = validate_selfshot_scene_continuity(
            frames,
            scene_index=1,
            scene_duration_seconds=5,
            person_required=False,
            object_required=True,
            relationship_required=False,
            object_reference=str(obj_ref),
            object_reference_roi=[130, 120, 200, 390],
        )
        assert res["ok"] is False
        assert res["object_identity"] is False
        assert res["independent_visual_validation"] == "NOT_PERFORMED"
        assert res["blocker"] == "insufficient_temporal_evidence"
        for obs in res["object_observations"]:
            assert obs["object_ok"] is False
            assert obs["object_bbox"] is None


def test_relationship_scene_fails_closed_when_object_localization_fails() -> None:
    """24. Relationship scene fails closed when object localization cannot be produced."""
    from unittest.mock import patch
    import cv2
    import numpy as np
    repo_root = Path(__file__).resolve().parents[1]
    person_ref = repo_root / "tests" / "fixtures" / "selfshot_vision" / "person_calibration" / "obama_obs1.jpg"
    person_cand = repo_root / "tests" / "fixtures" / "selfshot_vision" / "person_calibration" / "obama_obs2.jpg"
    object_ref = repo_root / "tests" / "fixtures" / "selfshot_vision" / "object_calibration" / "snuff_bottle_coins_obs1.jpg"
    object_cand = repo_root / "tests" / "fixtures" / "selfshot_vision" / "object_calibration" / "snuff_bottle_coins_obs2.jpg"

    img_p2 = cv2.imread(str(person_cand))
    img_o2 = cv2.imread(str(object_cand))
    canvas = np.zeros((800, 1400, 3), dtype=np.uint8)
    canvas[50:50+img_p2.shape[0], 50:50+img_p2.shape[1]] = img_p2
    canvas[50:50+img_o2.shape[0], 400:400+img_o2.shape[1]] = img_o2

    frames = [canvas, canvas, canvas]

    # Object localization produces degenerate quad
    with patch("cv2.perspectiveTransform", return_value=np.array([[[0, 0]], [[0, 0]], [[0, 0]], [[0, 0]]])):
        res = validate_selfshot_scene_continuity(
            frames,
            scene_index=1,
            scene_duration_seconds=5,
            person_required=True,
            object_required=True,
            relationship_required=True,
            person_reference=str(person_ref),
            object_reference=str(object_ref),
            object_reference_roi=[130, 120, 200, 390],
        )
        assert res["ok"] is False
        assert res["person_identity"] is True  # Person alone matched
        assert res["object_identity"] is False  # Object localization failed
        assert res["person_object_relationship"] is False  # Relationship blocked
        assert res["independent_visual_validation"] == "NOT_PERFORMED"


