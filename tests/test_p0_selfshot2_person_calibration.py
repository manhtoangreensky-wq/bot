from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from services.video_selfshot_person_validator import (
    CALIBRATED_PERSON_THRESHOLD,
    THRESHOLD_OPERATOR,
    evaluate_person_continuity_from_provider_payload,
    verify_person_identity,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "selfshot_vision" / "person_calibration"
MANIFEST_PATH = REPO_ROOT / "config" / "selfshot_vision_calibration_fixtures.json"


@pytest.fixture(scope="module")
def manifest_data() -> dict:
    assert MANIFEST_PATH.is_file()
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_determinism_and_drift_zero(manifest_data: dict) -> None:
    """Verify evaluation of pairs is fully deterministic with zero drift."""
    fixtures = manifest_data["fixtures"]
    f1 = FIXTURE_DIR / fixtures[0]["filename"]
    f2 = FIXTURE_DIR / fixtures[1]["filename"]

    res1 = verify_person_identity(f1, f2)
    res2 = verify_person_identity(f1, f2)
    assert res1["similarity_score"] is not None
    assert res2["similarity_score"] is not None
    assert res1["similarity_score"] == res2["similarity_score"]


def test_positive_same_person_pairs_verified(manifest_data: dict) -> None:
    """1: Same-person pairs are verified above calibrated threshold."""
    fixtures = manifest_data["fixtures"]
    identities: dict[str, list[dict]] = {}
    for item in fixtures:
        identities.setdefault(item["identity_id"], []).append(item)

    for ident, items in identities.items():
        assert len(items) >= 2
        f1 = FIXTURE_DIR / items[0]["filename"]
        f2 = FIXTURE_DIR / items[1]["filename"]
        res = verify_person_identity(
            f1,
            f2,
            reference_fixture_id=items[0]["fixture_id"],
            candidate_fixture_id=items[1]["fixture_id"],
            reference_identity_id=ident,
            candidate_identity_id=ident,
        )
        assert res["decision"] is True, f"Failed for same identity {ident}: {res}"
        assert res["person_identity"] is True
        assert res["similarity_score"] >= CALIBRATED_PERSON_THRESHOLD
        assert res["failure_reason"] == ""


def test_negative_different_person_pairs_fail_closed(manifest_data: dict) -> None:
    """2: Different-person pairs fail closed below calibrated threshold (0 false positives)."""
    fixtures = manifest_data["fixtures"]
    for i in range(len(fixtures)):
        for j in range(i + 1, len(fixtures)):
            item1 = fixtures[i]
            item2 = fixtures[j]
            if item1["identity_id"] == item2["identity_id"]:
                continue
            f1 = FIXTURE_DIR / item1["filename"]
            f2 = FIXTURE_DIR / item2["filename"]
            res = verify_person_identity(
                f1,
                f2,
                reference_fixture_id=item1["fixture_id"],
                candidate_fixture_id=item2["fixture_id"],
                reference_identity_id=item1["identity_id"],
                candidate_identity_id=item2["identity_id"],
            )
            assert res["decision"] is False, f"False positive detected between {item1['identity_id']} and {item2['identity_id']}"
            assert res["person_identity"] is False
            assert res["similarity_score"] < CALIBRATED_PERSON_THRESHOLD
            assert res["failure_reason"] == "score_below_threshold"


def test_no_face_fails_closed(manifest_data: dict) -> None:
    """3: Images with no face fail closed."""
    valid_file = FIXTURE_DIR / manifest_data["fixtures"][0]["filename"]
    # Blank white image has no face
    blank = np.full((300, 300, 3), 255, dtype=np.uint8)

    res = verify_person_identity(blank, valid_file)
    assert res["decision"] is False
    assert res["failure_reason"] == "no_face_in_reference"

    res2 = verify_person_identity(valid_file, blank)
    assert res2["decision"] is False
    assert res2["failure_reason"] == "no_face_in_candidate"


def test_missing_reference_fails_closed(manifest_data: dict) -> None:
    """4: Missing reference or candidate fails closed."""
    valid_file = FIXTURE_DIR / manifest_data["fixtures"][0]["filename"]

    res1 = verify_person_identity(None, valid_file)
    assert res1["decision"] is False
    assert res1["failure_reason"] == "missing_reference"

    res2 = verify_person_identity(valid_file, None)
    assert res2["decision"] is False
    assert res2["failure_reason"] == "missing_candidate"


def test_multiple_faces_fails_closed(manifest_data: dict) -> None:
    """6: Ambiguous multiple faces fail closed."""
    # Concatenate two different faces side-by-side to create a 2-face image
    f1 = FIXTURE_DIR / manifest_data["fixtures"][0]["filename"]
    f2 = FIXTURE_DIR / manifest_data["fixtures"][2]["filename"]
    img1 = cv2.imread(str(f1))
    img2 = cv2.imread(str(f2))
    img2_resized = cv2.resize(img2, (img1.shape[1], img1.shape[0]))
    multi = np.concatenate([img1, img2_resized], axis=1)

    res = verify_person_identity(multi, f1)
    assert res["decision"] is False
    assert res["face_count_reference"] >= 2
    assert res["failure_reason"] == "multiple_ambiguous_faces_in_reference"


def test_boundary_and_operator_semantics(manifest_data: dict) -> None:
    """7, 8, & Boundary: Operator >=, testing threshold - eps, threshold, threshold + eps."""
    valid_file = FIXTURE_DIR / manifest_data["fixtures"][0]["filename"]
    eps = 0.001

    # Immediately below threshold
    res_below = verify_person_identity(valid_file, valid_file, forced_score=CALIBRATED_PERSON_THRESHOLD - eps)
    assert res_below["decision"] is False
    assert res_below["person_identity"] is False
    assert res_below["failure_reason"] == "score_below_threshold"

    # Exactly at threshold
    res_exact = verify_person_identity(valid_file, valid_file, forced_score=CALIBRATED_PERSON_THRESHOLD)
    assert res_exact["decision"] is True
    assert res_exact["person_identity"] is True
    assert res_exact["failure_reason"] == ""

    # Immediately above threshold
    res_above = verify_person_identity(valid_file, valid_file, forced_score=CALIBRATED_PERSON_THRESHOLD + eps)
    assert res_above["decision"] is True
    assert res_above["person_identity"] is True
    assert res_above["failure_reason"] == ""


def test_transport_success_without_visual_evidence_fails_closed() -> None:
    """9: Provider / transport success NEVER implies person identity evidence."""
    provider_payload = {
        "status": "succeeded",
        "task_id": "v2v-12345",
        "output_url": "https://example.com/rendered.mp4",
    }
    # No visual evidence passed
    res = evaluate_person_continuity_from_provider_payload(provider_payload, reference=None, candidate=None)
    assert res["transport_success"] is True
    assert res["visual_evidence_present"] is False
    assert res["person_identity"] is False
    assert res["failure_reason"] == "transport_success_without_visual_evidence"


def test_robustness_against_perturbations(manifest_data: dict) -> None:
    """Robustness check: small deterministic perturbations of same identity stay above threshold."""
    fixtures = manifest_data["fixtures"]
    # Check anchor observation for each identity
    for item in fixtures:
        if not item["filename"].endswith("_obs1.jpg"):
            continue
        img_path = FIXTURE_DIR / item["filename"]
        img = cv2.imread(str(img_path))

        # 1. JPEG compression
        _, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
        p_jpeg = cv2.imdecode(enc, cv2.IMREAD_COLOR)

        # 2. Brightness variation
        p_bright = cv2.convertScaleAbs(img, alpha=1.05, beta=15)

        # 3. Minor crop
        h, w = img.shape[:2]
        dh, dw = int(h * 0.03), int(w * 0.03)
        p_crop = cv2.resize(img[dh:h-dh, dw:w-dw], (w, h))

        for p_img in (p_jpeg, p_bright, p_crop):
            res = verify_person_identity(img, p_img)
            assert res["decision"] is True
            assert res["person_identity"] is True
            assert res["similarity_score"] >= CALIBRATED_PERSON_THRESHOLD
