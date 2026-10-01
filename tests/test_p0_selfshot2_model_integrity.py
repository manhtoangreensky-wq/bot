from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "config" / "selfshot_vision_models.json"
CANONICAL_MODEL_DIR = REPO_ROOT / "assets" / "models" / "selfshot_vision"


def test_selfshot_vision_models_manifest_integrity() -> None:
    """Verify that the manifest exists, is valid JSON, and defines models."""
    assert MANIFEST_PATH.is_file(), f"Manifest missing at {MANIFEST_PATH}"
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert data.get("schema_version") == "1.0.0"
    models = data.get("models")
    assert isinstance(models, list) and len(models) >= 2

    # Check for duplicate roles
    roles = [m.get("role") for m in models]
    assert len(roles) == len(set(roles)), f"Duplicate role collision detected: {roles}"

    # Verify every declared model
    declared_filenames = set()
    for m in models:
        filename = m.get("filename")
        assert filename, "Model entry missing filename"
        declared_filenames.add(filename)

        file_path = CANONICAL_MODEL_DIR / filename
        assert file_path.is_file(), f"Declared model artifact {filename} missing on disk"

        # Byte count verification
        expected_bytes = m.get("bytes")
        actual_bytes = file_path.stat().st_size
        assert actual_bytes == expected_bytes, (
            f"Byte count mismatch for {filename}: expected {expected_bytes}, got {actual_bytes}"
        )

        # SHA-256 checksum verification
        expected_sha256 = m.get("sha256")
        actual_sha256 = hashlib.sha256(file_path.read_bytes()).hexdigest()
        assert actual_sha256 == expected_sha256, (
            f"SHA-256 mismatch for {filename}: expected {expected_sha256}, got {actual_sha256}"
        )

        # Provenance and license fields
        assert m.get("license") in {"MIT", "Apache-2.0"}
        assert m.get("source_repository") == "https://github.com/opencv/opencv_zoo"
        assert m.get("provenance_status") == "OFFICIAL_OPENCV_ZOO"

    # Verify no undeclared model binary exists in canonical directory
    disk_files = {p.name for p in CANONICAL_MODEL_DIR.glob("*.onnx")}
    undeclared = disk_files - declared_filenames
    assert not undeclared, f"Undeclared model files present in {CANONICAL_MODEL_DIR}: {undeclared}"


def test_yunet_model_load_smoke() -> None:
    """Smoke test: OpenCV can instantiate and load YuNet detector."""
    yunet_file = CANONICAL_MODEL_DIR / "face_detection_yunet_2023mar.onnx"
    assert yunet_file.is_file()

    # OpenCV dedicated loader
    detector = cv2.FaceDetectorYN.create(str(yunet_file), "", (320, 320))
    assert detector is not None

    # OpenCV DNN loader
    net = cv2.dnn.readNetFromONNX(str(yunet_file))
    assert not net.empty()


def test_sface_model_load_smoke() -> None:
    """Smoke test: OpenCV can instantiate and load SFace recognizer."""
    sface_file = CANONICAL_MODEL_DIR / "face_recognition_sface_2021dec.onnx"
    assert sface_file.is_file()

    # OpenCV dedicated loader
    recognizer = cv2.FaceRecognizerSF.create(str(sface_file), "")
    assert recognizer is not None

    # OpenCV DNN loader
    net = cv2.dnn.readNetFromONNX(str(sface_file))
    assert not net.empty()


def test_sift_zero_download_runtime_available() -> None:
    """Verify SIFT, FLANN matcher, and RANSAC homography are available in runtime."""
    sift = cv2.SIFT_create()
    assert sift is not None

    index_params = dict(algorithm=1, trees=5)
    search_params = dict(checks=50)
    flann = cv2.FlannBasedMatcher(index_params, search_params)
    assert flann is not None
