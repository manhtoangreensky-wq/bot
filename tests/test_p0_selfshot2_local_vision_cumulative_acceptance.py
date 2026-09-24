"""Cumulative local vision acceptance tests for Self-shot Scene Change.

Task: P0.PRODUCT_VIDEO.SELF_SHOT_SCENE_CHANGE.LOCAL.VISION.CUMULATIVE.LOCAL.ACCEPTANCE.R1
Asserts end-to-end provider-free local consistency across:
- Pinned calibrated threshold authorities
- Real public domain fixture evaluation (person, object, relationship)
- Integrated scenes A through H (same-frame evidence only)
- Temporal persistence contracts (2/3 for 5s; 3/5 for 10s/15s)
- Strict fail-closed provenance & bypass rejection
- Biometric hygiene & zero drift determinism
- Performance within 3.5s budget
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
import pytest

from services.video_selfshot_person_validator import (
    CALIBRATED_PERSON_THRESHOLD,
    THRESHOLD_OPERATOR as PERSON_OPERATOR,
    verify_person_identity,
)
from services.video_selfshot_object_validator import (
    CALIBRATED_OBJECT_MIN_RANSAC_INLIERS,
    INLIER_COUNT_OPERATOR as OBJECT_OPERATOR,
    verify_object_identity,
)
from services.video_selfshot_relationship_validator import (
    CALIBRATED_RELATIONSHIP_DISTANCE_MAX,
    DREL_OPERATOR as RELATIONSHIP_OPERATOR,
    PRIMARY_RELATION_TYPE,
    verify_person_object_relationship,
)
from services.video_selfshot_continuity_validator import (
    EVIDENCE_SOURCE,
    validate_selfshot_scene_continuity,
)
from services.video_real_render_connector import selfshot2_continuity_validation

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_1_canonical_threshold_profile_truth() -> None:
    """Step 2: Canonical thresholds must match empirical calibration and reject stale placeholders."""
    assert CALIBRATED_PERSON_THRESHOLD == 0.574165
    assert PERSON_OPERATOR == ">="
    assert CALIBRATED_OBJECT_MIN_RANSAC_INLIERS == 25
    assert OBJECT_OPERATOR == ">="
    assert CALIBRATED_RELATIONSHIP_DISTANCE_MAX == 0.281528
    assert RELATIONSHIP_OPERATOR == "<="

    # Reject stale architecture placeholder values
    assert CALIBRATED_PERSON_THRESHOLD != 0.650
    assert CALIBRATED_OBJECT_MIN_RANSAC_INLIERS != 60  # old placeholder
    assert CALIBRATED_RELATIONSHIP_DISTANCE_MAX != 0.320


def test_2_real_local_fixtures_acceptance() -> None:
    """Step 3: Real fixture acceptance across person, object, and relationship lanes."""
    # 1. Person: same vs different
    p_manifest = json.loads((REPO_ROOT / "config" / "selfshot_vision_calibration_fixtures.json").read_text(encoding="utf-8"))
    p_dir = REPO_ROOT / "tests" / "fixtures" / "selfshot_vision" / "person_calibration"
    p_ref = p_dir / p_manifest["fixtures"][0]["filename"]
    p_cand_same = p_dir / p_manifest["fixtures"][1]["filename"]
    p_cand_diff = p_dir / p_manifest["fixtures"][2]["filename"]

    res_p_same = verify_person_identity(p_ref, p_cand_same)
    assert res_p_same["decision"] is True
    assert res_p_same["similarity_score"] >= CALIBRATED_PERSON_THRESHOLD

    res_p_diff = verify_person_identity(p_ref, p_cand_diff)
    assert res_p_diff["decision"] is False
    assert res_p_diff["similarity_score"] < CALIBRATED_PERSON_THRESHOLD

    # 2. Object: same vs different instance
    o_manifest = json.loads((REPO_ROOT / "config" / "selfshot_vision_object_calibration_fixtures.json").read_text(encoding="utf-8"))
    o_dir = REPO_ROOT / "tests" / "fixtures" / "selfshot_vision" / "object_calibration"
    o_ref = o_dir / o_manifest["fixtures"][0]["filename"]
    o_cand_same = o_dir / o_manifest["fixtures"][1]["filename"]
    o_cand_diff = o_dir / o_manifest["fixtures"][4]["filename"]
    roi_ref = o_manifest["fixtures"][0]["roi_bbox"]
    roi_same = o_manifest["fixtures"][1]["roi_bbox"]
    roi_diff = o_manifest["fixtures"][4]["roi_bbox"]

    res_o_same = verify_object_identity(o_ref, o_cand_same, reference_roi=roi_ref, candidate_roi=roi_same)
    assert res_o_same["decision"] is True
    assert res_o_same["ransac_inlier_count"] >= CALIBRATED_OBJECT_MIN_RANSAC_INLIERS

    res_o_diff = verify_object_identity(o_ref, o_cand_diff, reference_roi=roi_ref, candidate_roi=roi_diff)
    assert res_o_diff["decision"] is False
    assert res_o_diff["ransac_inlier_count"] < CALIBRATED_OBJECT_MIN_RANSAC_INLIERS

    # 3. Relationship: holding_or_close vs separated
    r_manifest = json.loads((REPO_ROOT / "config" / "selfshot_vision_relationship_calibration_fixtures.json").read_text(encoding="utf-8"))
    pos_fix = next(f for f in r_manifest["fixtures"] if f.get("relationship_ground_truth") == "POSITIVE")
    neg_fix = next(f for f in r_manifest["fixtures"] if f.get("relationship_ground_truth") == "NEGATIVE")

    res_r_pos = verify_person_object_relationship(
        person_identity=True,
        object_identity=True,
        same_frame_cooccurrence=True,
        person_bbox=pos_fix["person_bbox"],
        object_bbox=pos_fix["object_bbox"],
        frame_width=pos_fix["image_width"],
        frame_height=pos_fix["image_height"],
    )
    assert res_r_pos["decision"] is True
    assert res_r_pos["drel"] <= CALIBRATED_RELATIONSHIP_DISTANCE_MAX

    res_r_neg = verify_person_object_relationship(
        person_identity=True,
        object_identity=True,
        same_frame_cooccurrence=True,
        person_bbox=neg_fix["person_bbox"],
        object_bbox=neg_fix["object_bbox"],
        frame_width=neg_fix["image_width"],
        frame_height=neg_fix["image_height"],
    )
    assert res_r_neg["decision"] is False
    assert res_r_neg["drel"] > CALIBRATED_RELATIONSHIP_DISTANCE_MAX


def test_3_integrated_scene_acceptance_matrix_a_to_h() -> None:
    """Step 4: Integrated scene acceptance across classes A through H with same-frame evidence only."""
    # A. Person-only valid -> PASS
    res_a = validate_selfshot_scene_continuity(
        "dummy.mp4",
        scene_index=1,
        scene_duration_seconds=5,
        person_required=True,
        object_required=False,
        relationship_required=False,
        mock_frame_observations=[{"person_ok": True}] * 3,
    )
    assert res_a["ok"] is True
    assert res_a["person_identity"] is True
    assert res_a["object_identity"] is False
    assert res_a["person_object_relationship"] is False

    # B. Person-only wrong identity -> FAIL
    res_b = validate_selfshot_scene_continuity(
        "dummy.mp4",
        scene_index=1,
        scene_duration_seconds=5,
        person_required=True,
        object_required=False,
        relationship_required=False,
        mock_frame_observations=[{"person_ok": False}] * 3,
    )
    assert res_b["ok"] is False
    assert res_b["person_identity"] is False

    # C. Object-only valid -> PASS
    res_c = validate_selfshot_scene_continuity(
        "dummy.mp4",
        scene_index=1,
        scene_duration_seconds=5,
        person_required=False,
        object_required=True,
        relationship_required=False,
        mock_frame_observations=[{"object_ok": True}] * 3,
    )
    assert res_c["ok"] is True
    assert res_c["person_identity"] is False
    assert res_c["object_identity"] is True

    # D. Object-only wrong instance -> FAIL
    res_d = validate_selfshot_scene_continuity(
        "dummy.mp4",
        scene_index=1,
        scene_duration_seconds=5,
        person_required=False,
        object_required=True,
        relationship_required=False,
        mock_frame_observations=[{"object_ok": False}] * 3,
    )
    assert res_d["ok"] is False
    assert res_d["object_identity"] is False

    # E. Person + Object + holding_or_close all valid -> PASS
    res_e = validate_selfshot_scene_continuity(
        "dummy.mp4",
        scene_index=1,
        scene_duration_seconds=5,
        person_required=True,
        object_required=True,
        relationship_required=True,
        mock_frame_observations=[{"person_ok": True, "object_ok": True, "relationship_ok": True}] * 3,
    )
    assert res_e["ok"] is True
    assert res_e["person_identity"] is True
    assert res_e["object_identity"] is True
    assert res_e["person_object_relationship"] is True

    # F. Correct identities but separated relation -> FAIL
    res_f = validate_selfshot_scene_continuity(
        "dummy.mp4",
        scene_index=1,
        scene_duration_seconds=5,
        person_required=True,
        object_required=True,
        relationship_required=True,
        mock_frame_observations=[{"person_ok": True, "object_ok": True, "relationship_ok": False}] * 3,
    )
    assert res_f["ok"] is False
    assert res_f["person_object_relationship"] is False

    # G. Person valid + object invalid -> FAIL
    res_g = validate_selfshot_scene_continuity(
        "dummy.mp4",
        scene_index=1,
        scene_duration_seconds=5,
        person_required=True,
        object_required=True,
        relationship_required=True,
        mock_frame_observations=[{"person_ok": True, "object_ok": False, "relationship_ok": True}] * 3,
    )
    assert res_g["ok"] is False
    assert res_g["object_identity"] is False
    # Object failure prevents relationship from rescuing frame
    assert res_g["person_object_relationship"] is False

    # H. Object valid + person invalid -> FAIL
    res_h = validate_selfshot_scene_continuity(
        "dummy.mp4",
        scene_index=1,
        scene_duration_seconds=5,
        person_required=True,
        object_required=True,
        relationship_required=True,
        mock_frame_observations=[{"person_ok": False, "object_ok": True, "relationship_ok": True}] * 3,
    )
    assert res_h["ok"] is False
    assert res_h["person_identity"] is False
    assert res_h["person_object_relationship"] is False


def test_4_temporal_acceptance_aggregation() -> None:
    """Step 5: Temporal aggregation (2/3 for 5s, 3/5 for 10s/15s, single lucky frame forbidden)."""
    # 5s: 2/3 pass
    assert validate_selfshot_scene_continuity(
        "dummy.mp4", scene_duration_seconds=5, person_required=True,
        mock_frame_observations=[{"person_ok": True}, {"person_ok": True}, {"person_ok": False}]
    )["ok"] is True

    # 5s: 1/3 fail
    assert validate_selfshot_scene_continuity(
        "dummy.mp4", scene_duration_seconds=5, person_required=True,
        mock_frame_observations=[{"person_ok": True}, {"person_ok": False}, {"person_ok": False}]
    )["ok"] is False

    # 10s: 3/5 pass
    assert validate_selfshot_scene_continuity(
        "dummy.mp4", scene_duration_seconds=10, person_required=True,
        mock_frame_observations=[{"person_ok": True}, {"person_ok": True}, {"person_ok": True}, {"person_ok": False}, {"person_ok": False}]
    )["ok"] is True

    # 10s: 2/5 fail
    assert validate_selfshot_scene_continuity(
        "dummy.mp4", scene_duration_seconds=10, person_required=True,
        mock_frame_observations=[{"person_ok": True}, {"person_ok": True}, {"person_ok": False}, {"person_ok": False}, {"person_ok": False}]
    )["ok"] is False

    # 15s: 3/5 pass
    assert validate_selfshot_scene_continuity(
        "dummy.mp4", scene_duration_seconds=15, person_required=True,
        mock_frame_observations=[{"person_ok": True}, {"person_ok": True}, {"person_ok": True}, {"person_ok": False}, {"person_ok": False}]
    )["ok"] is True

    # 15s: 2/5 fail
    assert validate_selfshot_scene_continuity(
        "dummy.mp4", scene_duration_seconds=15, person_required=True,
        mock_frame_observations=[{"person_ok": True}, {"person_ok": True}, {"person_ok": False}, {"person_ok": False}, {"person_ok": False}]
    )["ok"] is False


def test_5_provenance_and_bypass_regression(tmp_path: Path) -> None:
    """Step 6: Fail closed on manual booleans, transport only, untrusted metadata, and enforce scene isolation."""
    mp4_file = tmp_path / "final.mp4"
    mp4_file.write_bytes(b"dummy-valid-mp4")
    ready_out = {
        "final_video_path": str(mp4_file),
        "output_bytes": mp4_file.stat().st_size,
        "has_video": True,
        "validation_status": "candidate_mp4_valid_full",
        "concat_ready": True,
    }
    job_1scene = {
        "product_type": "self_shot_scene_change",
        "scene_count": 1,
        "asset_pack": {"subject_manifest": {"person_subject_ids": ["p1"], "object_subject_ids": ["o1"]}},
    }

    # Manual booleans without evidence_source="local_vision_validator" fail closed as independent visual validation
    val_manual = selfshot2_continuity_validation(
        job_1scene,
        ready_out,
        scene_tasks=[{"scene_index": 1, "status": "downloaded", "clip_valid": True}],
        debug_results=[{"scene_index": 1, "continuity_evidence": {"person_identity": True, "object_identity": True, "person_object_relationship": True}}],
    )
    assert val_manual["independent_visual_validation"] == "NOT_PERFORMED"
    assert val_manual["independent_visual_continuity_proven"] is False

    # Transport only fails closed
    val_trans = selfshot2_continuity_validation(
        job_1scene,
        ready_out,
        scene_tasks=[{"scene_index": 1, "status": "downloaded", "clip_valid": True}],
        debug_results=[],
    )
    assert val_trans["independent_visual_continuity_proven"] is False
    assert val_trans["ok"] is False

    # Scene isolation: 2-scene job where scene 1 has valid local evidence but scene 2 is missing
    job_2scene = {
        "product_type": "self_shot_scene_change",
        "scene_count": 2,
        "asset_pack": {"subject_manifest": {"person_subject_ids": ["p1"], "object_subject_ids": ["o1"]}},
    }
    val_iso = selfshot2_continuity_validation(
        job_2scene,
        ready_out,
        scene_tasks=[
            {"scene_index": 1, "status": "downloaded", "clip_valid": True},
            {"scene_index": 2, "status": "downloaded", "clip_valid": True},
        ],
        debug_results=[
            {"scene_index": 1, "evidence_source": EVIDENCE_SOURCE, "person_identity": True, "object_identity": True, "person_object_relationship": True},
        ],
    )
    assert val_iso["ok"] is False
    assert val_iso["independent_visual_continuity_proven"] is False
    assert val_iso["continuity_missing_scene_indexes"] == [2]


def test_6_evidence_schema_and_biometric_hygiene() -> None:
    """Step 8: Output evidence schema must be complete and free of raw biometric vectors or secrets."""
    res = validate_selfshot_scene_continuity(
        "dummy.mp4",
        scene_index=1,
        scene_duration_seconds=5,
        person_required=True,
        object_required=True,
        relationship_required=True,
        mock_frame_observations=[{"person_ok": True, "object_ok": True, "relationship_ok": True}] * 3,
    )
    expected_fields = {
        "person_identity", "object_identity", "person_object_relationship",
        "ok", "blocker", "failure_reason", "scene_index", "sampled_frame_count",
        "person_observations", "object_observations", "relationship_observations",
        "threshold_profile", "evidence_source", "independent_visual_validation",
        "wall_clock_seconds",
    }
    assert expected_fields.issubset(set(res.keys()))
    assert res["threshold_profile"]["person_threshold"] == CALIBRATED_PERSON_THRESHOLD
    assert res["threshold_profile"]["object_min_ransac_inliers"] == CALIBRATED_OBJECT_MIN_RANSAC_INLIERS
    assert res["threshold_profile"]["relationship_distance_max"] == CALIBRATED_RELATIONSHIP_DISTANCE_MAX

    # Biometric hygiene: No raw vectors, embeddings, crops, or secrets
    forbidden_keys = {"face_crop", "face_embedding", "raw_vector", "biometric_tensor", "api_key", "secret"}
    assert forbidden_keys.isdisjoint(set(res.keys()))


def test_7_determinism_and_drift_zero() -> None:
    """Step 11: Repeat evaluations of identical inputs produce zero decision drift."""
    p_manifest = json.loads((REPO_ROOT / "config" / "selfshot_vision_calibration_fixtures.json").read_text(encoding="utf-8"))
    p_dir = REPO_ROOT / "tests" / "fixtures" / "selfshot_vision" / "person_calibration"
    p_ref = p_dir / p_manifest["fixtures"][0]["filename"]
    p_cand = p_dir / p_manifest["fixtures"][1]["filename"]

    # 10 repeated decisions
    decisions = [verify_person_identity(p_ref, p_cand)["decision"] for _ in range(10)]
    assert len(set(decisions)) == 1
    assert decisions[0] is True


def test_8_performance_budget_under_3_5s() -> None:
    """Step 10: Performance of real local validation is well within the 3.5s budget."""
    p_manifest = json.loads((REPO_ROOT / "config" / "selfshot_vision_calibration_fixtures.json").read_text(encoding="utf-8"))
    p_dir = REPO_ROOT / "tests" / "fixtures" / "selfshot_vision" / "person_calibration"
    import cv2
    ref_img = cv2.imread(str(p_dir / p_manifest["fixtures"][0]["filename"]))
    cand_img = cv2.imread(str(p_dir / p_manifest["fixtures"][1]["filename"]))

    t0 = time.perf_counter()
    res = validate_selfshot_scene_continuity(
        [cand_img, cand_img, cand_img],
        scene_index=1,
        scene_duration_seconds=5,
        person_required=True,
        object_required=False,
        relationship_required=False,
        person_reference=ref_img,
    )
    elapsed = time.perf_counter() - t0
    assert res["ok"] is True
    assert elapsed <= 3.5, f"Validation elapsed time {elapsed:.3f}s exceeded budget of 3.5s"
