from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "config" / "selfshot_vision_object_calibration_fixtures.json"
CANONICAL_FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "selfshot_vision" / "object_calibration"


def test_object_fixture_manifest_parses_and_validates_exact_provenance() -> None:
    """1, 8, 9, 10, 11: Manifest exists, parses as valid JSON, defines schema, rights, and exact CC0 provenance."""
    assert MANIFEST_PATH.is_file(), f"Object fixture manifest missing at {MANIFEST_PATH}"
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert data.get("schema_version") == "1.0.0"
    assert data.get("canonical_storage_directory") == "tests/fixtures/selfshot_vision/object_calibration"
    assert data.get("intended_purpose") == "object_identity_calibration"
    assert data.get("provenance_policy") == "PUBLIC_DOMAIN_CC0_EXACT_ASSETS"
    assert data.get("algorithm_target") == "OpenCV_SIFT_FLANN_RANSAC_HOMOGRAPHY"

    fixtures = data.get("fixtures")
    assert isinstance(fixtures, list) and len(fixtures) >= 6

    fixture_ids = set()
    for item in fixtures:
        fid = item.get("fixture_id")
        assert fid, "Fixture missing fixture_id"
        assert fid not in fixture_ids, f"Duplicate fixture_id: {fid}"
        fixture_ids.add(fid)

        # 5: Every fixture has object_identity_id
        assert item.get("object_identity_id"), f"Fixture {fid} missing object_identity_id"

        # 8: Exact provenance fields
        assert item.get("source_type"), f"Fixture {fid} missing source_type"
        assert item.get("source_url_or_repository"), f"Fixture {fid} missing source url"
        assert item.get("source_ref"), f"Fixture {fid} missing source_ref"
        assert item.get("source_file"), f"Fixture {fid} missing source_file"
        assert "CC0" in item.get("license", ""), f"Fixture {fid} license must be CC0, got {item.get('license')}"
        assert item.get("license_document"), f"Fixture {fid} missing license_document"

        # 9, 10, 11: Explicit rights verified
        assert item.get("redistribution_allowed") is True, f"Redistribution not allowed for {fid}"
        assert item.get("commercial_use_allowed") is True, f"Commercial use not allowed for {fid}"
        assert item.get("testing_use_allowed") is True, f"Testing use not allowed for {fid}"

        assert item.get("synthetic_or_real") in {"real", "real_augmented"}
        assert item.get("derivation"), f"Fixture {fid} missing derivation"
        assert item.get("contains_object") is True


def test_object_fixture_filesystem_and_checksum_integrity() -> None:
    """2, 3, 4: Every declared image exists, byte count matches, SHA-256 matches."""
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    fixtures = data.get("fixtures", [])

    declared_filenames = set()
    for item in fixtures:
        filename = item.get("filename")
        assert filename, "Fixture missing filename"
        declared_filenames.add(filename)

        file_path = CANONICAL_FIXTURE_DIR / filename
        assert file_path.is_file(), f"Declared fixture file {filename} missing on disk at {file_path}"

        # 3: Byte count matches
        expected_bytes = item.get("bytes")
        actual_bytes = file_path.stat().st_size
        assert actual_bytes == expected_bytes, (
            f"Byte mismatch for {filename}: expected {expected_bytes}, got {actual_bytes}"
        )

        # 4: SHA-256 matches
        expected_sha256 = item.get("sha256")
        actual_sha256 = hashlib.sha256(file_path.read_bytes()).hexdigest()
        assert actual_sha256 == expected_sha256, (
            f"SHA-256 mismatch for {filename}: expected {expected_sha256}, got {actual_sha256}"
        )

    # No undeclared files in canonical object fixture directory
    disk_files = {p.name for p in CANONICAL_FIXTURE_DIR.glob("*.jpg")}
    undeclared = disk_files - declared_filenames
    assert not undeclared, f"Undeclared files in {CANONICAL_FIXTURE_DIR}: {undeclared}"


def test_object_fixture_deterministic_roi_bounds() -> None:
    """6, 7: Every observation has deterministic roi_bbox [x, y, w, h] lying strictly inside image bounds."""
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    fixtures = data.get("fixtures", [])

    for item in fixtures:
        roi = item.get("roi_bbox")
        assert isinstance(roi, list) and len(roi) == 4, f"Fixture {item['fixture_id']} missing valid roi_bbox"
        rx, ry, rw, rh = roi
        assert rx >= 0 and ry >= 0 and rw > 0 and rh > 0, f"Invalid roi dimensions in {item['fixture_id']}: {roi}"
        assert item.get("roi_authority") == "PROVEN_OBJECT_BOUNDING_BOX"

        file_path = CANONICAL_FIXTURE_DIR / item["filename"]
        img = cv2.imread(str(file_path))
        assert img is not None, f"Could not read image {file_path}"
        ih, iw = img.shape[:2]

        # 7: bbox lies inside image bounds
        assert rx + rw <= iw, f"ROI width exceeds image bound: rx({rx}) + rw({rw}) = {rx+rw} > iw({iw})"
        assert ry + rh <= ih, f"ROI height exceeds image bound: ry({ry}) + rh({rh}) = {ry+rh} > ih({ih})"


def test_object_fixture_identities_and_pair_readiness() -> None:
    """12, 13, 14, 15: At least 3 identities, >=2 obs each, positive & negative pairs exist, same-category neg pair."""
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    fixtures = data.get("fixtures", [])

    identities: dict[str, list[dict]] = {}
    categories: dict[str, str] = {}
    for item in fixtures:
        ident = item["object_identity_id"]
        identities.setdefault(ident, []).append(item)
        categories[ident] = item.get("category", "")

    # 12: At least 3 distinct object identities
    assert len(identities) >= 3, f"Expected >= 3 distinct object identities, found {len(identities)}"

    # 13: At least 2 observations per identity
    for ident, obs in identities.items():
        assert len(obs) >= 2, f"Identity {ident} has fewer than 2 observations: {len(obs)}"

    # 14: Positive same-object pairs exist (>= 3)
    same_pairs = sum(len(obs) * (len(obs) - 1) // 2 for obs in identities.values())
    assert same_pairs >= 3, f"Expected >= 3 same-object positive pairs, found {same_pairs}"

    # 15: Different-object negative pairs exist (> 0)
    unique_ids = list(identities.keys())
    diff_pairs = sum(
        len(identities[unique_ids[i]]) * len(identities[unique_ids[j]])
        for i in range(len(unique_ids))
        for j in range(i + 1, len(unique_ids))
    )
    assert diff_pairs > 0, "No different-object negative pairs found"

    # Same-category negative pair requirement
    same_category_neg_pairs = sum(
        len(identities[unique_ids[i]]) * len(identities[unique_ids[j]])
        for i in range(len(unique_ids))
        for j in range(i + 1, len(unique_ids))
        if categories[unique_ids[i]] == categories[unique_ids[j]]
    )
    assert same_category_neg_pairs > 0, "Expected at least 1 same-category different-object negative pair"


def test_sift_descriptors_available_for_all_accepted_rois() -> None:
    """16: Provider-free OpenCV SIFT extracts usable keypoints and 128-d descriptors on all accepted ROIs."""
    sift = cv2.SIFT_create()
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    fixtures = data.get("fixtures", [])

    for item in fixtures:
        file_path = CANONICAL_FIXTURE_DIR / item["filename"]
        img = cv2.imread(str(file_path))
        assert img is not None, f"Failed to load image: {file_path}"

        rx, ry, rw, rh = item["roi_bbox"]
        roi_img = img[ry:ry+rh, rx:rx+rw]
        assert roi_img.size > 0, f"Empty ROI slice for {item['fixture_id']}"

        gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
        kp, desc = sift.detectAndCompute(gray, None)

        assert kp is not None and len(kp) >= 50, (
            f"Insufficient SIFT keypoints for {item['fixture_id']}: {len(kp) if kp else 0} < 50"
        )
        assert desc is not None, f"SIFT descriptor is None for {item['fixture_id']}"
        assert desc.shape == (len(kp), 128), (
            f"Unexpected descriptor shape for {item['fixture_id']}: {desc.shape}"
        )


def test_production_and_user_media_paths_absent() -> None:
    """17: Confirm no production user uploads, customer media, or forbidden tokens appear in manifest."""
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_str = json.dumps(data)
    forbidden_tokens = [
        "video AI", "7883224372459", "data/tmp", "operator_uploads", "backups",
        "customer", "telegram_uploads", "production_uploads"
    ]
    for tok in forbidden_tokens:
        assert tok not in manifest_str, f"Forbidden token '{tok}' found in object fixture manifest"
