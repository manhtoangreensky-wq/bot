"""Calibrated fail-closed person identity validator for Self-shot Scene Change.

Uses YuNet face detector and SFace face recognizer from OpenCV Zoo.
Threshold is derived empirically from safe local public domain calibration fixtures.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
YUNET_PATH = REPO_ROOT / "assets" / "models" / "selfshot_vision" / "face_detection_yunet_2023mar.onnx"
SFACE_PATH = REPO_ROOT / "assets" / "models" / "selfshot_vision" / "face_recognition_sface_2021dec.onnx"

# Empirically calibrated from local safe public domain fixtures:
# MAX_NEGATIVE_SCORE = 0.205084, MIN_POSITIVE_SCORE = 0.943245, GAP = 0.738161
CALIBRATED_PERSON_THRESHOLD: float = 0.574165
THRESHOLD_OPERATOR: str = ">="
SIMILARITY_METRIC: str = "cosine"


def _read_image(source: str | Path | np.ndarray | None) -> np.ndarray | None:
    if source is None:
        return None
    if isinstance(source, np.ndarray):
        return source
    path_str = str(source)
    p = Path(path_str)
    if not p.is_file():
        return None
    return cv2.imread(str(p))


def verify_person_identity(
    reference: str | Path | np.ndarray | None,
    candidate: str | Path | np.ndarray | None,
    *,
    reference_fixture_id: str = "",
    candidate_fixture_id: str = "",
    reference_identity_id: str = "",
    candidate_identity_id: str = "",
    threshold: float = CALIBRATED_PERSON_THRESHOLD,
    forced_score: float | None = None,
) -> dict[str, Any]:
    """Evaluate person identity continuity between a reference and a candidate frame.

    Fail-closed semantics:
    - missing reference or candidate -> False
    - unreadable image -> False
    - no face detected -> False
    - multiple ambiguous faces -> False
    - alignment or embedding failure -> False
    - score < threshold -> False
    - score >= threshold -> True
    """
    evidence: dict[str, Any] = {
        "reference_fixture_id": reference_fixture_id,
        "candidate_fixture_id": candidate_fixture_id,
        "reference_identity_id": reference_identity_id,
        "candidate_identity_id": candidate_identity_id,
        "face_count_reference": 0,
        "face_count_candidate": 0,
        "similarity_metric": SIMILARITY_METRIC,
        "similarity_score": None,
        "threshold": threshold,
        "threshold_operator": THRESHOLD_OPERATOR,
        "decision": False,
        "person_identity": False,
        "failure_reason": "",
    }

    if reference is None:
        evidence["failure_reason"] = "missing_reference"
        return evidence
    if candidate is None:
        evidence["failure_reason"] = "missing_candidate"
        return evidence

    ref_img = _read_image(reference)
    if ref_img is None:
        evidence["failure_reason"] = "unreadable_reference_image"
        return evidence

    cand_img = _read_image(candidate)
    if cand_img is None:
        evidence["failure_reason"] = "unreadable_candidate_image"
        return evidence

    if not YUNET_PATH.is_file():
        evidence["failure_reason"] = "yunet_model_missing"
        return evidence
    if not SFACE_PATH.is_file():
        evidence["failure_reason"] = "sface_model_missing"
        return evidence

    # Detect faces in reference
    h_r, w_r = ref_img.shape[:2]
    det_r = cv2.FaceDetectorYN.create(str(YUNET_PATH), "", (w_r, h_r))
    ret_r, faces_r = det_r.detect(ref_img)
    face_count_r = len(faces_r) if faces_r is not None else 0
    evidence["face_count_reference"] = face_count_r

    if face_count_r == 0:
        evidence["failure_reason"] = "no_face_in_reference"
        return evidence
    if face_count_r > 1:
        evidence["failure_reason"] = "multiple_ambiguous_faces_in_reference"
        return evidence

    # Detect faces in candidate
    h_c, w_c = cand_img.shape[:2]
    det_c = cv2.FaceDetectorYN.create(str(YUNET_PATH), "", (w_c, h_c))
    ret_c, faces_c = det_c.detect(cand_img)
    face_count_c = len(faces_c) if faces_c is not None else 0
    evidence["face_count_candidate"] = face_count_c

    if face_count_c == 0:
        evidence["failure_reason"] = "no_face_in_candidate"
        return evidence
    if face_count_c > 1:
        evidence["failure_reason"] = "multiple_ambiguous_faces_in_candidate"
        return evidence

    recognizer = cv2.FaceRecognizerSF.create(str(SFACE_PATH), "")

    # Align & feature reference
    try:
        aligned_r = recognizer.alignCrop(ref_img, faces_r[0])
        if aligned_r is None or aligned_r.size == 0:
            evidence["failure_reason"] = "alignment_failure_reference"
            return evidence
        feat_r = recognizer.feature(aligned_r)
        if feat_r is None or feat_r.size == 0:
            evidence["failure_reason"] = "embedding_failure_reference"
            return evidence
    except Exception as exc:
        evidence["failure_reason"] = f"alignment_exception_reference: {exc}"
        return evidence

    # Align & feature candidate
    try:
        aligned_c = recognizer.alignCrop(cand_img, faces_c[0])
        if aligned_c is None or aligned_c.size == 0:
            evidence["failure_reason"] = "alignment_failure_candidate"
            return evidence
        feat_c = recognizer.feature(aligned_c)
        if feat_c is None or feat_c.size == 0:
            evidence["failure_reason"] = "embedding_failure_candidate"
            return evidence
    except Exception as exc:
        evidence["failure_reason"] = f"alignment_exception_candidate: {exc}"
        return evidence

    # If a forced score is specified for boundary testing
    if forced_score is not None:
        score = float(forced_score)
    else:
        score = float(recognizer.match(feat_r, feat_c, cv2.FaceRecognizerSF_FR_COSINE))

    evidence["similarity_score"] = round(score, 6)

    # Threshold decision: >=
    if score >= threshold:
        evidence["decision"] = True
        evidence["person_identity"] = True
        evidence["failure_reason"] = ""
    else:
        evidence["decision"] = False
        evidence["person_identity"] = False
        evidence["failure_reason"] = "score_below_threshold"

    return evidence


def evaluate_person_continuity_from_provider_payload(
    payload: dict[str, Any] | None,
    reference: str | Path | np.ndarray | None = None,
    candidate: str | Path | np.ndarray | None = None,
    *,
    threshold: float = CALIBRATED_PERSON_THRESHOLD,
) -> dict[str, Any]:
    """Ensure transport/provider success NEVER implies person identity evidence."""
    payload_dict = dict(payload or {})
    transport_success = str(payload_dict.get("status") or "").strip().lower() in {
        "success", "succeeded", "ok", "done", "completed"
    }

    # If no visual evidence is supplied, fail closed regardless of transport success
    if reference is None or candidate is None:
        return {
            "transport_success": transport_success,
            "visual_evidence_present": False,
            "person_identity": False,
            "failure_reason": "transport_success_without_visual_evidence",
        }

    res = verify_person_identity(reference, candidate, threshold=threshold)
    res["transport_success"] = transport_success
    res["visual_evidence_present"] = True
    return res
