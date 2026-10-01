from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "config" / "selfshot_vision_calibration_fixtures.json"
CANONICAL_FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "selfshot_vision" / "person_calibration"
YUNET_MODEL_PATH = REPO_ROOT / "assets" / "models" / "selfshot_vision" / "face_detection_yunet_2023mar.onnx"
SFACE_MODEL_PATH = REPO_ROOT / "assets" / "models" / "selfshot_vision" / "face_recognition_sface_2021dec.onnx"

REJECTED_HISTORICAL_NAMES = {
    "david_obs1.jpg", "david_obs2.jpg",
    "detect_obs1.jpg", "detect_obs2.jpg",
    "id100040721_obs1.jpg", "id100040721_obs2.jpg"
}


def test_fixture_manifest_parses_and_validates_exact_provenance() -> None:
    """1, 5, 6, 7, 8: Manifest exists, parses as valid JSON, defines schema, rights, and provenance."""
    assert MANIFEST_PATH.is_file(), f"Fixture manifest missing at {MANIFEST_PATH}"
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert data.get("schema_version") == "1.0.0"
    assert data.get("intended_purpose") == "person_identity_calibration"
    assert data.get("provenance_policy") == "PUBLIC_DOMAIN_EXACT_ASSETS"
    fixtures = data.get("fixtures")
    assert isinstance(fixtures, list) and len(fixtures) >= 6

    fixture_ids = set()
    for item in fixtures:
        fid = item.get("fixture_id")
        assert fid, "Fixture missing fixture_id"
        assert fid not in fixture_ids, f"Duplicate fixture_id: {fid}"
        fixture_ids.add(fid)

        # Every fixture has identity_id
        assert item.get("identity_id"), f"Fixture {fid} missing identity_id"

        # Exact provenance fields
        assert item.get("source_type"), f"Fixture {fid} missing source_type"
        assert item.get("source_url_or_repository"), f"Fixture {fid} missing source url"
        assert item.get("source_ref"), f"Fixture {fid} missing source_ref"
        assert item.get("source_file"), f"Fixture {fid} missing source_file"
        assert item.get("license") == "Public Domain", f"Fixture {fid} not Public Domain"
        assert item.get("license_document"), f"Fixture {fid} missing license_document"

        # Explicit rights verified: 6, 7, 8
        assert item.get("redistribution_allowed") is True, f"Redistribution not allowed for {fid}"
        assert item.get("commercial_use_allowed") is True, f"Commercial use not allowed for {fid}"
        assert item.get("testing_use_allowed") is True, f"Testing use not allowed for {fid}"

        assert item.get("synthetic_or_real") in {"real", "real_augmented"}
        assert item.get("derivation"), f"Fixture {fid} missing derivation"
        assert item.get("contains_person_face") is True


def test_fixture_filesystem_and_checksum_integrity() -> None:
    """2, 3, 4, 9: Files exist, byte counts & SHA256 match, no rejected historical files exist."""
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    fixtures = data.get("fixtures", [])

    # 9: No rejected historical fixture remains in canonical directory
    for rejected_name in REJECTED_HISTORICAL_NAMES:
        rejected_file = CANONICAL_FIXTURE_DIR / rejected_name
        assert not rejected_file.exists(), (
            f"Rejected historical fixture {rejected_name} still present in {CANONICAL_FIXTURE_DIR}"
        )

    declared_filenames = set()
    for item in fixtures:
        filename = item.get("filename")
        assert filename, "Fixture missing filename"
        assert filename not in REJECTED_HISTORICAL_NAMES, f"Declared filename {filename} is a rejected historical name"
        declared_filenames.add(filename)

        file_path = CANONICAL_FIXTURE_DIR / filename
        assert file_path.is_file(), f"Declared fixture file {filename} missing on disk"

        # Byte count verification
        expected_bytes = item.get("bytes")
        actual_bytes = file_path.stat().st_size
        assert actual_bytes == expected_bytes, (
            f"Byte mismatch for {filename}: expected {expected_bytes}, got {actual_bytes}"
        )

        # SHA-256 verification
        expected_sha256 = item.get("sha256")
        actual_sha256 = hashlib.sha256(file_path.read_bytes()).hexdigest()
        assert actual_sha256 == expected_sha256, (
            f"SHA-256 mismatch for {filename}: expected {expected_sha256}, got {actual_sha256}"
        )

    # No undeclared files in canonical fixture directory
    disk_files = {p.name for p in CANONICAL_FIXTURE_DIR.glob("*.jpg")}
    undeclared = disk_files - declared_filenames
    assert not undeclared, f"Undeclared files in {CANONICAL_FIXTURE_DIR}: {undeclared}"


def test_fixture_identities_and_pair_readiness() -> None:
    """10, 11, 12, 13: Identity count >= 3, each with >= 2 observations, positive & negative pairs exist."""
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    fixtures = data.get("fixtures", [])

    identities: dict[str, list[str]] = {}
    for item in fixtures:
        ident = item["identity_id"]
        identities.setdefault(ident, []).append(item["filename"])

    # 10: At least 3 distinct identities
    assert len(identities) >= 3, f"Expected >= 3 distinct identities, found {len(identities)}"

    # 11: Each identity has at least 2 observations
    for ident, obs in identities.items():
        assert len(obs) >= 2, f"Identity {ident} has fewer than 2 observations: {obs}"

    # Calculate pair counts
    same_pairs = sum(len(obs) * (len(obs) - 1) // 2 for obs in identities.values())
    unique_ids = list(identities.keys())
    diff_pairs = sum(
        len(identities[unique_ids[i]]) * len(identities[unique_ids[j]])
        for i in range(len(unique_ids))
        for j in range(i + 1, len(unique_ids))
    )

    # 12: Positive same-person pairs exist
    assert same_pairs > 0, "No same-person positive pairs available"
    # 13: Negative different-person pairs exist
    assert diff_pairs > 0, "No different-person negative pairs available"


def test_yunet_detects_usable_faces_on_all_fixtures() -> None:
    """14: YuNet detects exactly 1 usable face for each declared fixture observation with high confidence."""
    assert YUNET_MODEL_PATH.is_file(), "YuNet model file missing"
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    fixtures = data.get("fixtures", [])

    for item in fixtures:
        file_path = CANONICAL_FIXTURE_DIR / item["filename"]
        img = cv2.imread(str(file_path))
        assert img is not None, f"Failed to read image at {file_path}"

        h, w = img.shape[:2]
        detector = cv2.FaceDetectorYN.create(str(YUNET_MODEL_PATH), "", (w, h))
        ret, faces = detector.detect(img)
        assert faces is not None, f"YuNet failed to detect any face in {item['filename']}"
        assert len(faces) == 1, (
            f"Expected exactly 1 face in calibration fixture {item['filename']}, got {len(faces)}"
        )
        conf = faces[0][-1]
        assert conf >= 0.90, f"Face detection confidence too low in {item['filename']}: {conf}"


def test_sface_embedding_extraction_smoke() -> None:
    """15: SFace aligns, crops 112x112, and extracts 128-d feature embeddings for all replacement fixtures."""
    assert SFACE_MODEL_PATH.is_file(), "SFace model file missing"
    recognizer = cv2.FaceRecognizerSF.create(str(SFACE_MODEL_PATH), "")

    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    fixtures = data.get("fixtures", [])

    for item in fixtures:
        file_path = CANONICAL_FIXTURE_DIR / item["filename"]
        img = cv2.imread(str(file_path))
        h, w = img.shape[:2]
        detector = cv2.FaceDetectorYN.create(str(YUNET_MODEL_PATH), "", (w, h))
        ret, faces = detector.detect(img)
        assert faces is not None and len(faces) >= 1

        aligned = recognizer.alignCrop(img, faces[0])
        assert aligned is not None and aligned.shape == (112, 112, 3)

        feat = recognizer.feature(aligned)
        assert feat is not None
        assert feat.shape == (1, 128)


def test_production_and_user_media_paths_absent() -> None:
    """16: Confirm no production user uploads or private media are referenced."""
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_str = json.dumps(data)
    forbidden_tokens = ["video AI", "7883224372459", "data/tmp", "operator_uploads", "backups"]
    for tok in forbidden_tokens:
        assert tok not in manifest_str, f"Forbidden production/user token '{tok}' found in fixture manifest"
