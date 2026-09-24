"""Contract tests for Product Video Self-Shot Relationship Calibration Fixtures.

Validates:
1. Manifest parsing and schema correctness.
2. All referenced fixture files exist in canonical storage.
3. Exact SHA256 checksum integrity.
4. Byte count integrity.
5. Licenses and provenance completeness (Public Domain, US Gov, 17 U.S.C. 105).
6. person_subject_id present for all fixtures.
7. object_subject_id present for all fixtures.
8. relationship_ground_truth present and valid (POSITIVE/NEGATIVE).
9. relationship_type present and valid.
10. person_bbox valid and within image bounds.
11. object_bbox valid and within image bounds.
12. positive case count >= 10.
13. negative case count >= 10.
14. same-frame co-occurrence guaranteed for all calibration fixtures.
15. Zero production or customer media paths.
16. Zero ambiguous ground-truth fixtures.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "config" / "selfshot_vision_relationship_calibration_fixtures.json"


@pytest.fixture(scope="module")
def relationship_manifest_data() -> dict:
    assert MANIFEST_PATH.is_file(), f"Missing relationship manifest at {MANIFEST_PATH}"
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_1_manifest_parses(relationship_manifest_data: dict) -> None:
    assert relationship_manifest_data.get("schema_version") == "1.0.0"
    assert relationship_manifest_data.get("intended_purpose") == "person_object_relationship_calibration"
    assert relationship_manifest_data.get("canonical_storage_directory") == "tests/fixtures/selfshot_vision/relationship_calibration"
    assert "fixtures" in relationship_manifest_data
    assert isinstance(relationship_manifest_data["fixtures"], list)
    assert len(relationship_manifest_data["fixtures"]) > 0


def test_2_all_referenced_fixture_files_exist(relationship_manifest_data: dict) -> None:
    storage_dir = REPO_ROOT / relationship_manifest_data["canonical_storage_directory"]
    assert storage_dir.is_dir(), f"Storage directory {storage_dir} missing"

    for fx in relationship_manifest_data["fixtures"]:
        file_path = storage_dir / fx["filename"]
        assert file_path.is_file(), f"Fixture file missing: {file_path}"


def test_3_and_4_sha256_and_byte_counts_match(relationship_manifest_data: dict) -> None:
    storage_dir = REPO_ROOT / relationship_manifest_data["canonical_storage_directory"]

    for fx in relationship_manifest_data["fixtures"]:
        file_path = storage_dir / fx["filename"]
        data = file_path.read_bytes()

        actual_sha = hashlib.sha256(data).hexdigest()
        assert actual_sha == fx["sha256"], f"SHA256 mismatch for {fx['fixture_id']}"
        assert len(data) == fx["bytes"], f"Byte count mismatch for {fx['fixture_id']}"


def test_5_licenses_and_provenance_complete(relationship_manifest_data: dict) -> None:
    for fx in relationship_manifest_data["fixtures"]:
        assert fx.get("license") in ("Public Domain", "CC0", "Open Access"), f"Invalid license: {fx['fixture_id']}"
        assert fx.get("commercial_use_allowed") is True
        assert fx.get("redistribution_allowed") is True
        assert fx.get("testing_use_allowed") is True
        assert bool(fx.get("source_url_or_repository")), f"Missing source URL for {fx['fixture_id']}"
        assert bool(fx.get("source_provenance")), f"Missing provenance for {fx['fixture_id']}"
        assert bool(fx.get("license_document")), f"Missing license document for {fx['fixture_id']}"


def test_6_and_7_subject_ids_present(relationship_manifest_data: dict) -> None:
    for fx in relationship_manifest_data["fixtures"]:
        assert bool(fx.get("person_subject_id")), f"Missing person_subject_id in {fx['fixture_id']}"
        assert bool(fx.get("object_subject_id")), f"Missing object_subject_id in {fx['fixture_id']}"


def test_8_and_9_relationship_ground_truth_and_type_present(relationship_manifest_data: dict) -> None:
    for fx in relationship_manifest_data["fixtures"]:
        gt = fx.get("relationship_ground_truth")
        assert gt in ("POSITIVE", "NEGATIVE"), f"Invalid ground truth in {fx['fixture_id']}"

        rt = fx.get("relationship_type")
        assert rt in ("holding_or_close", "beside", "separated"), f"Invalid relation type in {fx['fixture_id']}"
        if gt == "POSITIVE":
            assert rt in ("holding_or_close", "beside"), f"Unexpected positive relation type in {fx['fixture_id']}"
        else:
            assert rt == "separated", f"Unexpected negative relation type in {fx['fixture_id']}"


def test_10_and_11_bboxes_valid_and_in_bounds(relationship_manifest_data: dict) -> None:
    storage_dir = REPO_ROOT / relationship_manifest_data["canonical_storage_directory"]

    for fx in relationship_manifest_data["fixtures"]:
        file_path = storage_dir / fx["filename"]
        img = cv2.imread(str(file_path))
        assert img is not None, f"Could not decode image {file_path}"
        ih, iw = img.shape[:2]

        assert fx["image_width"] == iw, f"Width mismatch in {fx['fixture_id']}"
        assert fx["image_height"] == ih, f"Height mismatch in {fx['fixture_id']}"

        # Person bbox
        p_bbox = fx["person_bbox"]
        assert len(p_bbox) == 4, f"Invalid person bbox format in {fx['fixture_id']}"
        px, py, pw, ph = p_bbox
        assert px >= 0 and py >= 0 and pw > 0 and ph > 0, f"Invalid person bbox dimensions in {fx['fixture_id']}"
        assert px + pw <= iw, f"Person bbox exceeds image width in {fx['fixture_id']}: {px}+{pw} > {iw}"
        assert py + ph <= ih, f"Person bbox exceeds image height in {fx['fixture_id']}: {py}+{ph} > {ih}"

        # Object bbox
        o_bbox = fx["object_bbox"]
        assert len(o_bbox) == 4, f"Invalid object bbox format in {fx['fixture_id']}"
        ox, oy, ow, oh = o_bbox
        assert ox >= 0 and oy >= 0 and ow > 0 and oh > 0, f"Invalid object bbox dimensions in {fx['fixture_id']}"
        assert ox + ow <= iw, f"Object bbox exceeds image width in {fx['fixture_id']}: {ox}+{ow} > {iw}"
        assert oy + oh <= ih, f"Object bbox exceeds image height in {fx['fixture_id']}: {oy}+{oh} > {ih}"


def test_12_positive_count_at_least_10(relationship_manifest_data: dict) -> None:
    positives = [f for f in relationship_manifest_data["fixtures"] if f["relationship_ground_truth"] == "POSITIVE"]
    assert len(positives) >= 10, f"Expected >= 10 positive cases, got {len(positives)}"

    holding_or_close = [f for f in positives if f["relationship_type"] == "holding_or_close"]
    assert len(holding_or_close) >= 5, f"Expected >= 5 holding_or_close positive cases, got {len(holding_or_close)}"


def test_13_negative_count_at_least_10(relationship_manifest_data: dict) -> None:
    negatives = [f for f in relationship_manifest_data["fixtures"] if f["relationship_ground_truth"] == "NEGATIVE"]
    assert len(negatives) >= 10, f"Expected >= 10 negative cases, got {len(negatives)}"

    separated = [f for f in negatives if f["relationship_type"] == "separated"]
    assert len(separated) >= 5, f"Expected >= 5 same-frame separated cases, got {len(separated)}"


def test_14_same_frame_cooccurrence_guaranteed(relationship_manifest_data: dict) -> None:
    for fx in relationship_manifest_data["fixtures"]:
        assert fx.get("same_frame_cooccurrence") is True, f"same_frame_cooccurrence not True in {fx['fixture_id']}"


def test_15_zero_production_or_customer_media_paths(relationship_manifest_data: dict) -> None:
    forbidden_substrings = ["user_media", "customer", "upload", "production", "tmp", "webhook", "telegram_uploads"]
    manifest_str = json.dumps(relationship_manifest_data).lower()
    for forbidden in forbidden_substrings:
        assert forbidden not in manifest_str, f"Forbidden customer/production substring '{forbidden}' found in manifest"


def test_16_zero_ambiguous_ground_truth_fixtures(relationship_manifest_data: dict) -> None:
    for fx in relationship_manifest_data["fixtures"]:
        assert fx.get("ground_truth_ambiguous") is False, f"Ambiguous fixture: {fx['fixture_id']}"
        assert fx.get("relationship_ground_truth") in ("POSITIVE", "NEGATIVE")
        assert bool(fx.get("relative_position_ground_truth"))
