from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from services.video_selfshot_object_validator import (
    CALIBRATED_OBJECT_MIN_GOOD_MATCHES,
    CALIBRATED_OBJECT_MIN_INLIER_RATIO,
    CALIBRATED_OBJECT_MIN_RANSAC_INLIERS,
    INLIER_COUNT_OPERATOR,
    INLIER_RATIO_OPERATOR,
    evaluate_object_continuity_from_provider_payload,
    verify_object_identity,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "selfshot_vision" / "object_calibration"
MANIFEST_PATH = REPO_ROOT / "config" / "selfshot_vision_object_calibration_fixtures.json"


@pytest.fixture(scope="module")
def manifest_data() -> dict:
    assert MANIFEST_PATH.is_file()
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_determinism_and_drift_zero(manifest_data: dict) -> None:
    """Verify evaluation of object pairs is fully deterministic with zero drift."""
    fixtures = manifest_data["fixtures"]
    f1 = FIXTURE_DIR / fixtures[0]["filename"]
    f2 = FIXTURE_DIR / fixtures[1]["filename"]
    roi1 = fixtures[0]["roi_bbox"]
    roi2 = fixtures[1]["roi_bbox"]

    res1 = verify_object_identity(f1, f2, reference_roi=roi1, candidate_roi=roi2)
    res2 = verify_object_identity(f1, f2, reference_roi=roi1, candidate_roi=roi2)

    assert res1["ransac_inlier_count"] == res2["ransac_inlier_count"]
    assert res1["good_match_count"] == res2["good_match_count"]
    assert res1["ransac_inlier_ratio"] == res2["ransac_inlier_ratio"]
    assert res1["decision"] == res2["decision"]


def test_positive_same_object_pairs_verified(manifest_data: dict) -> None:
    """1: Same-object canonical pairs are verified above calibrated dual thresholds."""
    fixtures = manifest_data["fixtures"]
    identities: dict[str, list[dict]] = {}
    for item in fixtures:
        identities.setdefault(item["object_identity_id"], []).append(item)

    for ident, items in identities.items():
        assert len(items) >= 2
        f1 = FIXTURE_DIR / items[0]["filename"]
        f2 = FIXTURE_DIR / items[1]["filename"]
        res = verify_object_identity(
            f1,
            f2,
            reference_roi=items[0]["roi_bbox"],
            candidate_roi=items[1]["roi_bbox"],
            reference_fixture_id=items[0]["fixture_id"],
            candidate_fixture_id=items[1]["fixture_id"],
            reference_identity_id=ident,
            candidate_identity_id=ident,
        )
        assert res["decision"] is True, f"Failed for same object identity {ident}: {res}"
        assert res["object_identity"] is True
        assert res["ransac_inlier_count"] >= CALIBRATED_OBJECT_MIN_RANSAC_INLIERS
        assert res["ransac_inlier_ratio"] >= CALIBRATED_OBJECT_MIN_INLIER_RATIO
        assert res["failure_reason"] == ""


def test_same_category_different_object_pairs_fail_closed(manifest_data: dict) -> None:
    """2: Same-category different-object pairs (bottle A vs bottle B) fail closed (0 false positives)."""
    fixtures = manifest_data["fixtures"]
    same_cat_negatives = []
    for i in range(len(fixtures)):
        for j in range(i + 1, len(fixtures)):
            item1 = fixtures[i]
            item2 = fixtures[j]
            if (
                item1["object_identity_id"] != item2["object_identity_id"]
                and item1.get("category") == item2.get("category")
            ):
                same_cat_negatives.append((item1, item2))

    assert len(same_cat_negatives) == 4, f"Expected 4 same-category negative pairs, got {len(same_cat_negatives)}"

    for item1, item2 in same_cat_negatives:
        f1 = FIXTURE_DIR / item1["filename"]
        f2 = FIXTURE_DIR / item2["filename"]
        res = verify_object_identity(
            f1,
            f2,
            reference_roi=item1["roi_bbox"],
            candidate_roi=item2["roi_bbox"],
            reference_fixture_id=item1["fixture_id"],
            candidate_fixture_id=item2["fixture_id"],
            reference_identity_id=item1["object_identity_id"],
            candidate_identity_id=item2["object_identity_id"],
        )
        assert res["decision"] is False, f"False positive in same category: {item1['fixture_id']} vs {item2['fixture_id']}"
        assert res["object_identity"] is False
        assert res["ransac_inlier_count"] < CALIBRATED_OBJECT_MIN_RANSAC_INLIERS
        assert "inliers_below_threshold" in res["failure_reason"] or "insufficient" in res["failure_reason"]


def test_different_category_different_object_pairs_fail_closed(manifest_data: dict) -> None:
    """3: Different-category different-object pairs fail closed (0 false positives)."""
    fixtures = manifest_data["fixtures"]
    diff_cat_negatives = []
    for i in range(len(fixtures)):
        for j in range(i + 1, len(fixtures)):
            item1 = fixtures[i]
            item2 = fixtures[j]
            if item1.get("category") != item2.get("category"):
                diff_cat_negatives.append((item1, item2))

    assert len(diff_cat_negatives) == 8, f"Expected 8 diff-cat negative pairs, got {len(diff_cat_negatives)}"

    for item1, item2 in diff_cat_negatives:
        f1 = FIXTURE_DIR / item1["filename"]
        f2 = FIXTURE_DIR / item2["filename"]
        res = verify_object_identity(
            f1,
            f2,
            reference_roi=item1["roi_bbox"],
            candidate_roi=item2["roi_bbox"],
        )
        assert res["decision"] is False
        assert res["object_identity"] is False
        assert res["ransac_inlier_count"] < CALIBRATED_OBJECT_MIN_RANSAC_INLIERS


def test_missing_reference_and_candidate_fail_closed(manifest_data: dict) -> None:
    """4, 5: Missing reference or missing candidate fail closed."""
    item = manifest_data["fixtures"][0]
    valid_file = FIXTURE_DIR / item["filename"]
    roi = item["roi_bbox"]

    res_no_ref = verify_object_identity(None, valid_file, reference_roi=roi, candidate_roi=roi)
    assert res_no_ref["decision"] is False
    assert res_no_ref["failure_reason"] == "missing_reference"

    res_no_cand = verify_object_identity(valid_file, None, reference_roi=roi, candidate_roi=roi)
    assert res_no_cand["decision"] is False
    assert res_no_cand["failure_reason"] == "missing_candidate"


def test_invalid_and_out_of_bounds_roi_fail_closed(manifest_data: dict) -> None:
    """6: Invalid format or out-of-bounds ROI fail closed."""
    item = manifest_data["fixtures"][0]
    valid_file = FIXTURE_DIR / item["filename"]

    # Missing ROI
    res_none = verify_object_identity(valid_file, valid_file, reference_roi=None, candidate_roi=[0, 0, 10, 10])
    assert res_none["decision"] is False
    assert "invalid_reference_roi" in res_none["failure_reason"]

    # Out of bounds ROI
    res_oob = verify_object_identity(valid_file, valid_file, reference_roi=[5000, 5000, 100, 100], candidate_roi=[0, 0, 10, 10])
    assert res_oob["decision"] is False
    assert "invalid_reference_roi:roi_out_of_bounds" in res_oob["failure_reason"]


def test_insufficient_keypoints_and_descriptors_fail_closed(manifest_data: dict) -> None:
    """7: Blank or textureless image with < 4 keypoints fails closed."""
    item = manifest_data["fixtures"][0]
    valid_file = FIXTURE_DIR / item["filename"]
    roi = item["roi_bbox"]

    # Blank flat image yields 0 keypoints
    blank = np.full((300, 300, 3), 128, dtype=np.uint8)
    res = verify_object_identity(blank, valid_file, reference_roi=[10, 10, 100, 100], candidate_roi=roi)
    assert res["decision"] is False
    assert res["failure_reason"] == "insufficient_keypoints_in_reference"


def test_boundary_and_operator_semantics(manifest_data: dict) -> None:
    """9, 10, 11: Exact threshold, discrete step below (-1), and discrete step above (+1)."""
    item1 = manifest_data["fixtures"][0]
    item2 = manifest_data["fixtures"][1]
    f1 = FIXTURE_DIR / item1["filename"]
    f2 = FIXTURE_DIR / item2["filename"]

    # 9: Below threshold (forced_inliers = 24 < 25) -> False
    res_below = verify_object_identity(
        f1, f2,
        reference_roi=item1["roi_bbox"], candidate_roi=item2["roi_bbox"],
        forced_inliers=CALIBRATED_OBJECT_MIN_RANSAC_INLIERS - 1,
        forced_ratio=0.85,
    )
    assert res_below["decision"] is False
    assert "inliers_below_threshold" in res_below["failure_reason"]

    # 10: Exact threshold (forced_inliers = 25, ratio = 0.70) -> True with '>=' operator
    res_exact = verify_object_identity(
        f1, f2,
        reference_roi=item1["roi_bbox"], candidate_roi=item2["roi_bbox"],
        forced_inliers=CALIBRATED_OBJECT_MIN_RANSAC_INLIERS,
        forced_ratio=CALIBRATED_OBJECT_MIN_INLIER_RATIO,
    )
    assert res_exact["decision"] is True
    assert res_exact["inlier_count_operator"] == ">="
    assert res_exact["inlier_ratio_operator"] == ">="

    # 11: Above threshold (forced_inliers = 26, ratio = 0.75) -> True
    res_above = verify_object_identity(
        f1, f2,
        reference_roi=item1["roi_bbox"], candidate_roi=item2["roi_bbox"],
        forced_inliers=CALIBRATED_OBJECT_MIN_RANSAC_INLIERS + 1,
        forced_ratio=0.75,
    )
    assert res_above["decision"] is True


def test_transport_success_without_local_visual_evidence_fails_closed(manifest_data: dict) -> None:
    """12: Provider payload success alone cannot certify object continuity without local visual evidence."""
    provider_payload = {"status": "SUCCESS", "task_id": "pv-task-99", "video_url": "https://example.com/out.mp4"}

    # No images supplied
    res_no_images = evaluate_object_continuity_from_provider_payload(provider_payload)
    assert res_no_images["decision"] is False
    assert res_no_images["object_identity"] is False
    assert res_no_images["failure_reason"] == "transport_success_without_local_visual_evidence"

    # Failed provider status
    failed_payload = {"status": "FAILED", "task_id": "pv-task-99"}
    res_failed = evaluate_object_continuity_from_provider_payload(failed_payload)
    assert res_failed["decision"] is False
    assert "provider_status_not_success" in res_failed["failure_reason"]


def test_robustness_against_perturbations(manifest_data: dict) -> None:
    """Verify that same-object observations under moderate deterministic perturbations remain verified."""
    obs1_items = [f for f in manifest_data["fixtures"] if f["fixture_id"].endswith("_obs1")]
    assert len(obs1_items) == 3

    for item in obs1_items:
        img_path = FIXTURE_DIR / item["filename"]
        img = cv2.imread(str(img_path))
        roi = item["roi_bbox"]

        # JPEG compression perturbation
        _, enc = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        perturbed_img = cv2.imdecode(enc, cv2.IMREAD_COLOR)

        res = verify_object_identity(img, perturbed_img, reference_roi=roi, candidate_roi=roi)
        assert res["decision"] is True, f"Failed robustness on {item['fixture_id']}"
        assert res["ransac_inlier_count"] >= CALIBRATED_OBJECT_MIN_RANSAC_INLIERS
        assert res["ransac_inlier_ratio"] >= CALIBRATED_OBJECT_MIN_INLIER_RATIO
