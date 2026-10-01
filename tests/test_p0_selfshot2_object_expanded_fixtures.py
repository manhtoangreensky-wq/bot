from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import pytest

from services.video_selfshot_object_validator import (
    CALIBRATED_OBJECT_MIN_INLIER_RATIO,
    CALIBRATED_OBJECT_MIN_RANSAC_INLIERS,
    verify_object_identity,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPANDED_DIR = REPO_ROOT / "tests" / "fixtures" / "selfshot_vision" / "object_expanded"
MANIFEST_PATH = REPO_ROOT / "config" / "selfshot_vision_object_expanded_fixtures.json"


@pytest.fixture(scope="module")
def expanded_manifest() -> dict:
    assert MANIFEST_PATH.is_file(), f"Expanded manifest missing at {MANIFEST_PATH}"
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_expanded_manifest_parses_and_validates_provenance(expanded_manifest: dict) -> None:
    """Validate manifest schema, CC0 exact provenance, and commercial/redistribution rights."""
    assert expanded_manifest.get("schema_version") == "1.0.0"
    assert expanded_manifest.get("intended_purpose") == "canonical_object_calibration_dataset_expansion"
    assert expanded_manifest.get("provenance_policy") == "PUBLIC_DOMAIN_CC0_EXACT_ASSETS"
    assert expanded_manifest.get("algorithm_target") == "OpenCV_SIFT_FLANN_RANSAC_HOMOGRAPHY"

    summary = expanded_manifest.get("summary", {})
    assert summary.get("same_product_positive_pair_count", 0) >= 20
    assert summary.get("same_category_different_product_negative_pair_count", 0) >= 20
    assert summary.get("occlusion_blur_corrupt_negative_case_count", 0) >= 10

    fixtures = expanded_manifest.get("fixtures", [])
    assert len(fixtures) >= 20

    for item in fixtures:
        assert item.get("fixture_id"), "Missing fixture_id"
        assert item.get("object_identity_id"), "Missing object_identity_id"
        assert item.get("category_id"), "Missing category_id"
        assert item.get("source_type"), "Missing source_type"
        assert item.get("source_url_or_repository"), "Missing source_url_or_repository"
        assert item.get("source_ref"), "Missing source_ref"
        assert "CC0" in item.get("license", ""), f"License must be CC0: {item.get('license')}"
        assert item.get("redistribution_allowed") is True
        assert item.get("commercial_use_allowed") is True
        assert item.get("testing_use_allowed") is True


def test_expanded_fixtures_filesystem_and_checksum_integrity(expanded_manifest: dict) -> None:
    """Verify files exist on disk, byte counts match, and SHA-256 hashes match."""
    fixtures = expanded_manifest.get("fixtures", [])
    stress_cases = expanded_manifest.get("stress_cases", [])

    all_declared = set()
    for item in fixtures:
        fname = item["filename"]
        all_declared.add(fname)
        fpath = EXPANDED_DIR / fname
        assert fpath.is_file(), f"Visual fixture missing: {fname}"
        assert fpath.stat().st_size == item["bytes"], f"Byte mismatch: {fname}"
        assert hashlib.sha256(fpath.read_bytes()).hexdigest() == item["sha256"], f"SHA mismatch: {fname}"

    for item in stress_cases:
        fname = item["filename"]
        all_declared.add(fname)
        fpath = EXPANDED_DIR / fname
        assert fpath.is_file(), f"Stress fixture missing: {fname}"
        assert fpath.stat().st_size == item["bytes"], f"Byte mismatch: {fname}"
        assert hashlib.sha256(fpath.read_bytes()).hexdigest() == item["sha256"], f"SHA mismatch: {fname}"

    disk_files = {p.name for p in EXPANDED_DIR.glob("*.jpg")}
    undeclared = disk_files - all_declared
    assert not undeclared, f"Undeclared files in {EXPANDED_DIR}: {undeclared}"


def test_expanded_fixtures_deterministic_roi_bounds(expanded_manifest: dict) -> None:
    """Verify every visual observation has deterministic ROI within image bounds."""
    for item in expanded_manifest["fixtures"]:
        roi = item.get("roi_bbox")
        assert isinstance(roi, list) and len(roi) == 4, f"Invalid ROI in {item['fixture_id']}"
        rx, ry, rw, rh = roi
        assert rx >= 0 and ry >= 0 and rw > 0 and rh > 0, f"Invalid ROI dimensions: {roi}"
        assert item.get("roi_authority") == "PROVEN_OBJECT_BOUNDING_BOX"

        fpath = EXPANDED_DIR / item["filename"]
        img = cv2.imread(str(fpath))
        assert img is not None
        ih, iw = img.shape[:2]
        assert rx + rw <= iw, f"ROI width out of bounds in {item['fixture_id']}: {rx+rw} > {iw}"
        assert ry + rh <= ih, f"ROI height out of bounds in {item['fixture_id']}: {ry+rh} > {ih}"


def test_expanded_sift_descriptors_available_for_visual_rois(expanded_manifest: dict) -> None:
    """Verify SIFT preflight: readable ROI, keypoints >= 50, descriptors available for all visual observations."""
    sift = cv2.SIFT_create()
    for item in expanded_manifest["fixtures"]:
        fpath = EXPANDED_DIR / item["filename"]
        img = cv2.imread(str(fpath))
        assert img is not None, f"Failed to read image {fpath}"

        rx, ry, rw, rh = item["roi_bbox"]
        roi = img[ry:ry+rh, rx:rx+rw]
        assert roi.size > 0

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        kp, desc = sift.detectAndCompute(gray, None)

        assert kp is not None and len(kp) >= 50, f"Insufficient keypoints in {item['fixture_id']}: {len(kp) if kp else 0}"
        assert desc is not None and len(desc) == len(kp), f"Descriptor mismatch in {item['fixture_id']}"
        assert desc.shape[1] == 128


def test_expanded_canonical_pair_inventory_counts(expanded_manifest: dict) -> None:
    """Verify pair counts: positive >= 20, same-category negative >= 20, stress negative >= 10."""
    pairs = expanded_manifest.get("pairs", [])
    pos_pairs = [p for p in pairs if p["pair_class"] == "SAME_INSTANCE"]
    same_cat_neg_pairs = [p for p in pairs if p["pair_class"] == "DIFFERENT_INSTANCE_SAME_CATEGORY"]
    stress_cases = [p for p in pairs if p["pair_class"] == "STRESS_NEGATIVE"]

    assert len(pos_pairs) >= 20, f"Expected >= 20 positive pairs, got {len(pos_pairs)}"
    assert len(same_cat_neg_pairs) >= 20, f"Expected >= 20 same-cat neg pairs, got {len(same_cat_neg_pairs)}"
    assert len(stress_cases) >= 10, f"Expected >= 10 stress negative cases, got {len(stress_cases)}"


def test_expanded_positive_same_product_pairs_verified(expanded_manifest: dict) -> None:
    """Verify all canonical positive pairs pass validator above provisional thresholds."""
    fixtures_map = {f["fixture_id"]: f for f in expanded_manifest["fixtures"]}
    pos_pairs = [p for p in expanded_manifest["pairs"] if p["pair_class"] == "SAME_INSTANCE"]

    for p in pos_pairs:
        f1 = fixtures_map[p["reference_fixture_id"]]
        f2 = fixtures_map[p["candidate_fixture_id"]]
        p1 = EXPANDED_DIR / f1["filename"]
        p2 = EXPANDED_DIR / f2["filename"]

        res = verify_object_identity(p1, p2, reference_roi=f1["roi_bbox"], candidate_roi=f2["roi_bbox"])
        assert res["decision"] is True, f"Positive pair failed: {p['pair_id']}"
        assert res["object_identity"] is True
        assert res["ransac_inlier_count"] >= CALIBRATED_OBJECT_MIN_RANSAC_INLIERS
        assert res["ransac_inlier_ratio"] >= CALIBRATED_OBJECT_MIN_INLIER_RATIO


def test_expanded_same_category_different_product_negatives_fail_closed(expanded_manifest: dict) -> None:
    """Verify all canonical same-category negative pairs fail closed with 0 false positives."""
    fixtures_map = {f["fixture_id"]: f for f in expanded_manifest["fixtures"]}
    neg_pairs = [p for p in expanded_manifest["pairs"] if p["pair_class"] == "DIFFERENT_INSTANCE_SAME_CATEGORY"]

    for p in neg_pairs:
        f1 = fixtures_map[p["reference_fixture_id"]]
        f2 = fixtures_map[p["candidate_fixture_id"]]
        p1 = EXPANDED_DIR / f1["filename"]
        p2 = EXPANDED_DIR / f2["filename"]

        res = verify_object_identity(p1, p2, reference_roi=f1["roi_bbox"], candidate_roi=f2["roi_bbox"])
        assert res["decision"] is False, f"False positive in same category: {p['pair_id']}"
        assert res["object_identity"] is False
        assert res["ransac_inlier_count"] < CALIBRATED_OBJECT_MIN_RANSAC_INLIERS


def test_expanded_stress_negatives_fail_closed(expanded_manifest: dict) -> None:
    """Verify all 10 stress negative observations fail closed."""
    fixtures_map = {f["fixture_id"]: f for f in expanded_manifest["fixtures"]}
    stress_map = {s["fixture_id"]: s for s in expanded_manifest["stress_cases"]}
    stress_pairs = [p for p in expanded_manifest["pairs"] if p["pair_class"] == "STRESS_NEGATIVE"]

    for p in stress_pairs:
        f1 = fixtures_map[p["reference_fixture_id"]]
        s = stress_map[p["candidate_fixture_id"]]
        p1 = EXPANDED_DIR / f1["filename"]
        p2 = EXPANDED_DIR / s["filename"]

        res = verify_object_identity(p1, p2, reference_roi=f1["roi_bbox"], candidate_roi=s["roi_bbox"])
        assert res["decision"] is False, f"Stress case failed to fail closed: {s['fixture_id']}"
        assert res["object_identity"] is False


def test_no_production_or_user_media_paths(expanded_manifest: dict) -> None:
    """Verify no customer or production media paths appear in expanded manifest."""
    manifest_str = json.dumps(expanded_manifest)
    forbidden = ["video AI", "7883224372459", "data/tmp", "operator_uploads", "customer", "production_uploads"]
    for tok in forbidden:
        assert tok not in manifest_str, f"Forbidden token {tok} in manifest"
