from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from services.video_selfshot_object_validator import (
    CALIBRATED_OBJECT_MIN_RANSAC_INLIERS,
    INLIER_COUNT_OPERATOR,
    evaluate_object_continuity_from_provider_payload,
    verify_object_identity,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPANDED_DIR = REPO_ROOT / "tests" / "fixtures" / "selfshot_vision" / "object_expanded"
MANIFEST_PATH = REPO_ROOT / "config" / "selfshot_vision_object_expanded_fixtures.json"

OBJECT_MIN_RANSAC_INLIERS_FINAL: int = 25
RANSAC_INLIER_OPERATOR: str = ">="


@pytest.fixture(scope="module")
def expanded_data() -> dict:
    assert MANIFEST_PATH.is_file(), f"Expanded manifest missing at {MANIFEST_PATH}"
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_determinism_and_drift_zero(expanded_data: dict) -> None:
    """Verify evaluation across repeated executions is completely deterministic with zero drift."""
    fixtures_map = {f["fixture_id"]: f for f in expanded_data["fixtures"]}
    f1 = fixtures_map["id_snuff_bottle_coins_obs1"]
    f2 = fixtures_map["id_snuff_bottle_coins_obs2"]

    p1 = EXPANDED_DIR / f1["filename"]
    p2 = EXPANDED_DIR / f2["filename"]

    base = verify_object_identity(p1, p2, reference_roi=f1["roi_bbox"], candidate_roi=f2["roi_bbox"], min_inliers=OBJECT_MIN_RANSAC_INLIERS_FINAL)
    for _ in range(5):
        rep = verify_object_identity(p1, p2, reference_roi=f1["roi_bbox"], candidate_roi=f2["roi_bbox"], min_inliers=OBJECT_MIN_RANSAC_INLIERS_FINAL)
        assert rep["good_match_count"] == base["good_match_count"]
        assert rep["ransac_inlier_count"] == base["ransac_inlier_count"]
        assert rep["ransac_inlier_ratio"] == base["ransac_inlier_ratio"]
        assert rep["decision"] == base["decision"]


def test_expanded_positive_matrix_and_frr(expanded_data: dict) -> None:
    """Verify all 30 same-instance positive pairs pass and FRR <= 0.05."""
    fixtures_map = {f["fixture_id"]: f for f in expanded_data["fixtures"]}
    pos_pairs = [p for p in expanded_data["pairs"] if p["pair_class"] == "SAME_INSTANCE"]
    assert len(pos_pairs) == 30

    tp = 0
    fn = 0
    inliers_list = []

    for p in pos_pairs:
        f1 = fixtures_map[p["reference_fixture_id"]]
        f2 = fixtures_map[p["candidate_fixture_id"]]
        p1 = EXPANDED_DIR / f1["filename"]
        p2 = EXPANDED_DIR / f2["filename"]

        res = verify_object_identity(
            p1, p2,
            reference_roi=f1["roi_bbox"], candidate_roi=f2["roi_bbox"],
            min_inliers=OBJECT_MIN_RANSAC_INLIERS_FINAL,
            min_ratio=None,
        )
        inl = res["ransac_inlier_count"]
        inliers_list.append(inl)
        if res["decision"] is True:
            tp += 1
        else:
            fn += 1

    assert fn == 0, f"False negatives detected: {fn}"
    assert tp == 30
    frr = fn / len(pos_pairs)
    assert frr <= 0.05, f"FRR exceeded canonical bound: {frr}"
    assert min(inliers_list) >= 45, f"Min positive inliers unexpectedly low: {min(inliers_list)}"


def test_same_category_negative_matrix_and_far(expanded_data: dict) -> None:
    """Verify all 96 same-category different-product negative pairs fail closed and FAR <= 0.01."""
    fixtures_map = {f["fixture_id"]: f for f in expanded_data["fixtures"]}
    neg_pairs = [p for p in expanded_data["pairs"] if p["pair_class"] == "DIFFERENT_INSTANCE_SAME_CATEGORY"]
    assert len(neg_pairs) == 96

    tn = 0
    fp = 0
    inliers_list = []

    for p in neg_pairs:
        f1 = fixtures_map[p["reference_fixture_id"]]
        f2 = fixtures_map[p["candidate_fixture_id"]]
        p1 = EXPANDED_DIR / f1["filename"]
        p2 = EXPANDED_DIR / f2["filename"]

        res = verify_object_identity(
            p1, p2,
            reference_roi=f1["roi_bbox"], candidate_roi=f2["roi_bbox"],
            min_inliers=OBJECT_MIN_RANSAC_INLIERS_FINAL,
            min_ratio=None,
        )
        inl = res["ransac_inlier_count"]
        inliers_list.append(inl)
        if res["decision"] is False:
            tn += 1
        else:
            fp += 1

    assert fp == 0, f"False positives detected: {fp}"
    assert tn == 96
    far = fp / len(neg_pairs)
    assert far <= 0.01, f"FAR exceeded canonical bound: {far}"
    assert max(inliers_list) <= 5, f"Max negative inliers exceeded expectation: {max(inliers_list)}"


def test_confusion_matrix_and_roc_evidence(expanded_data: dict) -> None:
    """Verify confusion matrix and ROC AUC = 1.0 (complete empirical separability)."""
    fixtures_map = {f["fixture_id"]: f for f in expanded_data["fixtures"]}
    pos_pairs = [p for p in expanded_data["pairs"] if p["pair_class"] == "SAME_INSTANCE"]
    neg_pairs = [p for p in expanded_data["pairs"] if p["pair_class"] == "DIFFERENT_INSTANCE_SAME_CATEGORY"]

    pos_inliers = []
    for p in pos_pairs:
        f1 = fixtures_map[p["reference_fixture_id"]]
        f2 = fixtures_map[p["candidate_fixture_id"]]
        res = verify_object_identity(
            EXPANDED_DIR / f1["filename"], EXPANDED_DIR / f2["filename"],
            reference_roi=f1["roi_bbox"], candidate_roi=f2["roi_bbox"],
        )
        pos_inliers.append(res["ransac_inlier_count"])

    neg_inliers = []
    for p in neg_pairs:
        f1 = fixtures_map[p["reference_fixture_id"]]
        f2 = fixtures_map[p["candidate_fixture_id"]]
        res = verify_object_identity(
            EXPANDED_DIR / f1["filename"], EXPANDED_DIR / f2["filename"],
            reference_roi=f1["roi_bbox"], candidate_roi=f2["roi_bbox"],
        )
        neg_inliers.append(res["ransac_inlier_count"])

    # Separation gap
    gap = min(pos_inliers) - max(neg_inliers)
    assert gap >= 35, f"Separation gap insufficient: {gap}"

    # ROC AUC
    auc = sum(1.0 if p > n else (0.5 if p == n else 0.0) for p in pos_inliers for n in neg_inliers) / (len(pos_inliers) * len(neg_inliers))
    assert auc == 1.0, f"ROC AUC is not 1.0: {auc}"


def test_minimal_metric_contract_no_redundancy(expanded_data: dict) -> None:
    """Verify that ransac_inlier_count alone is sufficient and minimal (redundant_threshold_count=0)."""
    fixtures_map = {f["fixture_id"]: f for f in expanded_data["fixtures"]}
    pos_pairs = [p for p in expanded_data["pairs"] if p["pair_class"] == "SAME_INSTANCE"]
    neg_pairs = [p for p in expanded_data["pairs"] if p["pair_class"] == "DIFFERENT_INSTANCE_SAME_CATEGORY"]

    for p in pos_pairs:
        f1 = fixtures_map[p["reference_fixture_id"]]
        f2 = fixtures_map[p["candidate_fixture_id"]]
        res = verify_object_identity(
            EXPANDED_DIR / f1["filename"], EXPANDED_DIR / f2["filename"],
            reference_roi=f1["roi_bbox"], candidate_roi=f2["roi_bbox"],
            min_inliers=25,
            min_ratio=None,
        )
        assert res["decision"] is True

    for p in neg_pairs:
        f1 = fixtures_map[p["reference_fixture_id"]]
        f2 = fixtures_map[p["candidate_fixture_id"]]
        res = verify_object_identity(
            EXPANDED_DIR / f1["filename"], EXPANDED_DIR / f2["filename"],
            reference_roi=f1["roi_bbox"], candidate_roi=f2["roi_bbox"],
            min_inliers=25,
            min_ratio=None,
        )
        assert res["decision"] is False


def test_boundary_semantics_discrete_steps(expanded_data: dict) -> None:
    """Verify exact threshold boundary semantics (inliers 24 -> False, inliers 25 -> True, inliers 26 -> True)."""
    fixtures_map = {f["fixture_id"]: f for f in expanded_data["fixtures"]}
    f1 = fixtures_map["id_snuff_bottle_coins_obs1"]
    f2 = fixtures_map["id_snuff_bottle_coins_obs2"]
    p1 = EXPANDED_DIR / f1["filename"]
    p2 = EXPANDED_DIR / f2["filename"]

    # Step below threshold: 24 < 25 -> Rejected
    res_below = verify_object_identity(
        p1, p2,
        reference_roi=f1["roi_bbox"], candidate_roi=f2["roi_bbox"],
        min_inliers=OBJECT_MIN_RANSAC_INLIERS_FINAL,
        min_ratio=None,
        forced_inliers=OBJECT_MIN_RANSAC_INLIERS_FINAL - 1,
    )
    assert res_below["decision"] is False
    assert "inliers_below_threshold" in res_below["failure_reason"]

    # Exact threshold: 25 -> Accepted with '>=' operator
    res_exact = verify_object_identity(
        p1, p2,
        reference_roi=f1["roi_bbox"], candidate_roi=f2["roi_bbox"],
        min_inliers=OBJECT_MIN_RANSAC_INLIERS_FINAL,
        min_ratio=None,
        forced_inliers=OBJECT_MIN_RANSAC_INLIERS_FINAL,
    )
    assert res_exact["decision"] is True

    # Step above threshold: 26 > 25 -> Accepted
    res_above = verify_object_identity(
        p1, p2,
        reference_roi=f1["roi_bbox"], candidate_roi=f2["roi_bbox"],
        min_inliers=OBJECT_MIN_RANSAC_INLIERS_FINAL,
        min_ratio=None,
        forced_inliers=OBJECT_MIN_RANSAC_INLIERS_FINAL + 1,
    )
    assert res_above["decision"] is True


def test_all_ten_stress_cases_fail_closed(expanded_data: dict) -> None:
    """Verify all 10 stress safety cases fail closed with zero false accepts."""
    fixtures_map = {f["fixture_id"]: f for f in expanded_data["fixtures"]}
    stress_map = {s["fixture_id"]: s for s in expanded_data["stress_cases"]}
    stress_pairs = [p for p in expanded_data["pairs"] if p["pair_class"] == "STRESS_NEGATIVE"]
    assert len(stress_pairs) == 10

    false_accepts = 0
    for p in stress_pairs:
        f1 = fixtures_map[p["reference_fixture_id"]]
        s = stress_map[p["candidate_fixture_id"]]
        p1 = EXPANDED_DIR / f1["filename"]
        p2 = EXPANDED_DIR / s["filename"]

        res = verify_object_identity(p1, p2, reference_roi=f1["roi_bbox"], candidate_roi=s["roi_bbox"], min_inliers=OBJECT_MIN_RANSAC_INLIERS_FINAL)
        if res["decision"] is True:
            false_accepts += 1
        assert res["decision"] is False
        assert res["object_identity"] is False

    assert false_accepts == 0


def test_robustness_across_viewpoints_and_lighting(expanded_data: dict) -> None:
    """Verify robust FRR = 0 across all 30 legitimate photographic variations."""
    fixtures_map = {f["fixture_id"]: f for f in expanded_data["fixtures"]}
    pos_pairs = [p for p in expanded_data["pairs"] if p["pair_class"] == "SAME_INSTANCE"]

    fails = 0
    for p in pos_pairs:
        f1 = fixtures_map[p["reference_fixture_id"]]
        f2 = fixtures_map[p["candidate_fixture_id"]]
        res = verify_object_identity(
            EXPANDED_DIR / f1["filename"], EXPANDED_DIR / f2["filename"],
            reference_roi=f1["roi_bbox"], candidate_roi=f2["roi_bbox"],
            min_inliers=OBJECT_MIN_RANSAC_INLIERS_FINAL,
        )
        if res["decision"] is not True:
            fails += 1

    assert fails == 0


def test_transport_success_without_object_evidence_fails_closed() -> None:
    """Provider transport success alone never certifies object continuity."""
    provider_payload = {"status": "SUCCESS", "task_id": "pv-task-canonical", "video_url": "https://example.com/out.mp4"}
    res = evaluate_object_continuity_from_provider_payload(provider_payload)
    assert res["decision"] is False
    assert res["object_identity"] is False
    assert res["failure_reason"] == "transport_success_without_local_visual_evidence"
