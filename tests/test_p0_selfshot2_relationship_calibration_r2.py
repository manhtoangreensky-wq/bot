"""Contract and calibration tests for Product Video Self-Shot Relationship Validator (R2).

Verifies:
1. All 9 holding_or_close positive fixtures pass under calibrated threshold.
2. All 12 separated negative fixtures fail closed under calibrated threshold.
3. Confusion matrix, FAR=0.0%, FRR=0.0%, and separation gap.
4. Threshold boundary semantics: threshold - eps -> PASS, threshold -> PASS, threshold + eps -> FAIL.
5. Upstream identity lock: person_identity=False -> FAIL, object_identity=False -> FAIL.
6. Co-occurrence lock: same_frame_cooccurrence=False -> FAIL.
7. Bounding box validation: missing, zero area, negative, out of bounds, non-finite -> FAIL.
8. Unsupported relation types fail closed (drinking_from, applying_to_skin, unboxing, typing_on, etc.).
9. Temporal contract: 2/3 PASS, 1/3 FAIL for 5s; 3/5 PASS, 2/5 FAIL for 10/15s.
10. Transport success without relationship evidence fails closed.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from services.video_selfshot_relationship_validator import (
    CALIBRATED_RELATIONSHIP_DISTANCE_MAX,
    DREL_OPERATOR,
    PRIMARY_RELATION_TYPE,
    compute_relationship_geometry,
    evaluate_relationship_continuity_from_provider_payload,
    evaluate_scene_relationship_continuity,
    validate_bbox,
    verify_person_object_relationship,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "config" / "selfshot_vision_relationship_calibration_fixtures.json"


@pytest.fixture(scope="module")
def manifest_fixtures() -> dict:
    assert MANIFEST_PATH.is_file(), f"Missing manifest {MANIFEST_PATH}"
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_holding_or_close_positives_verified(manifest_fixtures: dict) -> None:
    """All 9 holding_or_close positive fixtures must evaluate to TRUE with zero false rejections."""
    holding_positives = [
        f for f in manifest_fixtures["fixtures"]
        if f["relationship_ground_truth"] == "POSITIVE" and f["relationship_type"] == "holding_or_close"
    ]
    assert len(holding_positives) == 9, f"Expected 9 holding_or_close fixtures, got {len(holding_positives)}"

    for fx in holding_positives:
        res = verify_person_object_relationship(
            person_identity=True,
            object_identity=True,
            same_frame_cooccurrence=True,
            person_bbox=fx["person_bbox"],
            object_bbox=fx["object_bbox"],
            frame_width=fx["image_width"],
            frame_height=fx["image_height"],
            relationship_type="holding_or_close",
        )
        assert res["decision"] is True, f"Positive fixture {fx['fixture_id']} failed: {res}"
        assert res["relationship_valid"] is True
        assert res["drel"] <= CALIBRATED_RELATIONSHIP_DISTANCE_MAX
        assert res["failure_reason"] == ""


def test_separated_negatives_fail_closed(manifest_fixtures: dict) -> None:
    """All 12 separated negative fixtures must fail closed with zero false acceptances."""
    negatives = [
        f for f in manifest_fixtures["fixtures"]
        if f["relationship_ground_truth"] == "NEGATIVE" and f["relationship_type"] == "separated"
    ]
    assert len(negatives) == 12, f"Expected 12 separated fixtures, got {len(negatives)}"

    for fx in negatives:
        # Even if upstream identities are true and both appear in same frame, spatial separation must fail
        res = verify_person_object_relationship(
            person_identity=True,
            object_identity=True,
            same_frame_cooccurrence=True,
            person_bbox=fx["person_bbox"],
            object_bbox=fx["object_bbox"],
            frame_width=fx["image_width"],
            frame_height=fx["image_height"],
            relationship_type="holding_or_close",
        )
        assert res["decision"] is False, f"Negative fixture {fx['fixture_id']} unexpectedly passed: {res}"
        assert res["relationship_valid"] is False
        assert res["drel"] > CALIBRATED_RELATIONSHIP_DISTANCE_MAX
        assert res["failure_reason"] == "drel_above_threshold"


def test_confusion_matrix_and_empirical_calibration_gap(manifest_fixtures: dict) -> None:
    """Verify clean distribution separation, zero overlap, FAR=0%, FRR=0%."""
    fixtures = manifest_fixtures["fixtures"]
    holding_positives = [
        f for f in fixtures
        if f["relationship_ground_truth"] == "POSITIVE" and f["relationship_type"] == "holding_or_close"
    ]
    separated_negatives = [
        f for f in fixtures
        if f["relationship_ground_truth"] == "NEGATIVE" and f["relationship_type"] == "separated"
    ]

    tp, fn, tn, fp = 0, 0, 0, 0
    pos_drels = []
    neg_drels = []

    for fx in holding_positives:
        geom = compute_relationship_geometry(fx["person_bbox"], fx["object_bbox"], fx["image_width"], fx["image_height"])
        d = geom["drel"]
        pos_drels.append(d)
        if d <= CALIBRATED_RELATIONSHIP_DISTANCE_MAX:
            tp += 1
        else:
            fn += 1

    for fx in separated_negatives:
        geom = compute_relationship_geometry(fx["person_bbox"], fx["object_bbox"], fx["image_width"], fx["image_height"])
        d = geom["drel"]
        neg_drels.append(d)
        if d <= CALIBRATED_RELATIONSHIP_DISTANCE_MAX:
            fp += 1
        else:
            tn += 1

    assert tp == 9
    assert fn == 0
    assert tn == 12
    assert fp == 0

    far = fp / (fp + tn)
    frr = fn / (fn + tp)
    assert far == 0.0
    assert frr == 0.0

    max_pos = max(pos_drels)
    min_neg = min(neg_drels)
    assert max_pos < min_neg
    gap = min_neg - max_pos
    assert gap > 0.045
    assert CALIBRATED_RELATIONSHIP_DISTANCE_MAX > max_pos
    assert CALIBRATED_RELATIONSHIP_DISTANCE_MAX < min_neg


def test_threshold_boundary_and_operator_semantics() -> None:
    """Test boundary behavior: threshold - eps, threshold, threshold + eps."""
    eps = 0.0001
    thresh = CALIBRATED_RELATIONSHIP_DISTANCE_MAX

    # Below threshold -> PASS
    res_below = verify_person_object_relationship(
        person_identity=True,
        object_identity=True,
        same_frame_cooccurrence=True,
        forced_drel=thresh - eps,
    )
    assert res_below["decision"] is True
    assert res_below["failure_reason"] == ""

    # Exactly threshold -> PASS (operator <=)
    res_exact = verify_person_object_relationship(
        person_identity=True,
        object_identity=True,
        same_frame_cooccurrence=True,
        forced_drel=thresh,
    )
    assert res_exact["decision"] is True
    assert res_exact["failure_reason"] == ""

    # Above threshold -> FAIL
    res_above = verify_person_object_relationship(
        person_identity=True,
        object_identity=True,
        same_frame_cooccurrence=True,
        forced_drel=thresh + eps,
    )
    assert res_above["decision"] is False
    assert res_above["failure_reason"] == "drel_above_threshold"


def test_upstream_identity_and_cooccurrence_locks() -> None:
    """Relationship decision must fail closed if person, object, or co-occurrence is false."""
    # Person identity False
    res_p_false = verify_person_object_relationship(
        person_identity=False,
        object_identity=True,
        same_frame_cooccurrence=True,
        forced_drel=0.05,
    )
    assert res_p_false["decision"] is False
    assert res_p_false["failure_reason"] == "person_identity_false"

    # Object identity False
    res_o_false = verify_person_object_relationship(
        person_identity=True,
        object_identity=False,
        same_frame_cooccurrence=True,
        forced_drel=0.05,
    )
    assert res_o_false["decision"] is False
    assert res_o_false["failure_reason"] == "object_identity_false"

    # Co-occurrence False
    res_co_false = verify_person_object_relationship(
        person_identity=True,
        object_identity=True,
        same_frame_cooccurrence=False,
        forced_drel=0.05,
    )
    assert res_co_false["decision"] is False
    assert res_co_false["failure_reason"] == "no_same_frame_cooccurrence"


def test_bbox_validation_and_geometry_fail_closed() -> None:
    """Verify invalid bounding boxes and non-finite coordinates fail closed with informative errors."""
    # Missing person bbox
    res = verify_person_object_relationship(
        person_identity=True,
        object_identity=True,
        same_frame_cooccurrence=True,
        person_bbox=None,
        object_bbox=[10, 10, 50, 50],
        frame_width=800,
        frame_height=600,
    )
    assert res["decision"] is False
    assert res["failure_reason"] == "missing_person_bbox"

    # Missing object bbox
    res = verify_person_object_relationship(
        person_identity=True,
        object_identity=True,
        same_frame_cooccurrence=True,
        person_bbox=[10, 10, 50, 50],
        object_bbox=None,
        frame_width=800,
        frame_height=600,
    )
    assert res["decision"] is False
    assert res["failure_reason"] == "missing_object_bbox"

    # Negative dimensions
    res = verify_person_object_relationship(
        person_identity=True,
        object_identity=True,
        same_frame_cooccurrence=True,
        person_bbox=[10, 10, -50, 50],
        object_bbox=[100, 100, 50, 50],
        frame_width=800,
        frame_height=600,
    )
    assert res["decision"] is False
    assert res["failure_reason"] == "invalid_person_bbox_dimensions"

    # Zero area
    res = verify_person_object_relationship(
        person_identity=True,
        object_identity=True,
        same_frame_cooccurrence=True,
        person_bbox=[10, 10, 0, 50],
        object_bbox=[100, 100, 50, 50],
        frame_width=800,
        frame_height=600,
    )
    assert res["decision"] is False
    assert res["failure_reason"] == "invalid_person_bbox_dimensions"

    # Out of bounds
    res = verify_person_object_relationship(
        person_identity=True,
        object_identity=True,
        same_frame_cooccurrence=True,
        person_bbox=[10, 10, 50, 50],
        object_bbox=[700, 500, 150, 150],  # 700+150=850 > 800
        frame_width=800,
        frame_height=600,
    )
    assert res["decision"] is False
    assert res["failure_reason"] == "object_bbox_out_of_bounds"

    # Non-finite coordinates
    res = verify_person_object_relationship(
        person_identity=True,
        object_identity=True,
        same_frame_cooccurrence=True,
        person_bbox=[10, float("nan"), 50, 50],
        object_bbox=[100, 100, 50, 50],
        frame_width=800,
        frame_height=600,
    )
    assert res["decision"] is False
    assert res["failure_reason"] == "nonfinite_person_bbox"


def test_unsupported_relation_types_fail_closed() -> None:
    """Action-recognition relations remain unsupported in R2 and fail closed."""
    unsupported_actions = [
        "drinking_from",
        "applying_to_skin",
        "unboxing",
        "typing_on",
        "fine_grained_manipulation",
    ]
    for action in unsupported_actions:
        res = verify_person_object_relationship(
            person_identity=True,
            object_identity=True,
            same_frame_cooccurrence=True,
            forced_drel=0.01,
            relationship_type=action,
        )
        assert res["decision"] is False
        assert res["failure_reason"] == "unsupported_relation_type"


def test_temporal_scene_aggregation_contract() -> None:
    """Verify temporal contracts: 2/3 for 5s, 3/5 for 10/15s scenes."""
    # 5-second scenes (3 samples required, minimum 2 passes)
    assert evaluate_scene_relationship_continuity([True, True, False], scene_duration_seconds=5)["decision"] is True
    assert evaluate_scene_relationship_continuity([True, False, True], scene_duration_seconds=5)["decision"] is True
    assert evaluate_scene_relationship_continuity([False, True, True], scene_duration_seconds=5)["decision"] is True
    assert evaluate_scene_relationship_continuity([True, False, False], scene_duration_seconds=5)["decision"] is False
    assert evaluate_scene_relationship_continuity([False, False, False], scene_duration_seconds=5)["decision"] is False

    # 10-second and 15-second scenes (5 samples required, minimum 3 passes)
    for dur in (10, 15):
        # 3/5 passes -> PASS
        assert evaluate_scene_relationship_continuity([True, True, True, False, False], scene_duration_seconds=dur)["decision"] is True
        assert evaluate_scene_relationship_continuity([True, False, True, False, True], scene_duration_seconds=dur)["decision"] is True
        # 2/5 passes -> FAIL
        assert evaluate_scene_relationship_continuity([True, True, False, False, False], scene_duration_seconds=dur)["decision"] is False
        assert evaluate_scene_relationship_continuity([False, False, True, False, True], scene_duration_seconds=dur)["decision"] is False
        # 1/5 passes -> FAIL
        assert evaluate_scene_relationship_continuity([True, False, False, False, False], scene_duration_seconds=dur)["decision"] is False


def test_transport_success_without_relationship_evidence_fails_closed() -> None:
    """Transport success (HTTP 200 / SUCCESS) without local relationship evidence must fail closed."""
    # Payload missing relationship_evidence
    payload_empty = {"status": "SUCCESS", "job_id": "job_123"}
    res = evaluate_relationship_continuity_from_provider_payload(payload_empty)
    assert res["decision"] is False
    assert res["failure_reason"] == "transport_success_without_relationship_evidence"

    # Payload with valid relationship evidence
    payload_valid = {
        "status": "SUCCESS",
        "job_id": "job_123",
        "relationship_evidence": {
            "person_identity": True,
            "object_identity": True,
            "same_frame_cooccurrence": True,
            "person_bbox": [200, 200, 100, 100],
            "object_bbox": [220, 220, 50, 50],
            "frame_width": 800,
            "frame_height": 600,
            "relationship_type": "holding_or_close",
        },
    }
    res = evaluate_relationship_continuity_from_provider_payload(payload_valid)
    assert res["decision"] is True
    assert res["relationship_valid"] is True
