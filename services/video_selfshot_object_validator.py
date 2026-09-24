"""Calibrated fail-closed object identity validator for Self-shot Scene Change.

Uses native OpenCV SIFT + FLANN + RANSAC homography.
Thresholds derived empirically from safe local CC0 object calibration fixtures.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]

# Empirically calibrated from local safe CC0 object fixtures:
# POSITIVE_INLIER_RANGE: [45, 218], NEGATIVE_INLIER_RANGE: [0, 5], GAP: 40 inliers
# Canonical R3 decision rule: homography_available AND ransac_inlier_count >= 25
# Secondary metric: NONE (inlier ratio is diagnostic only)
CALIBRATED_OBJECT_MIN_RANSAC_INLIERS: int = 25
CALIBRATED_OBJECT_MIN_INLIER_RATIO: float = 0.70  # Diagnostic reference only
CALIBRATED_OBJECT_MIN_GOOD_MATCHES: int = 25

RATIO_TEST_CUTOFF: float = 0.75
RANSAC_REPROJECTION_THRESHOLD: float = 3.0
INLIER_COUNT_OPERATOR: str = ">="
INLIER_RATIO_OPERATOR: str = ">="
GOOD_MATCH_OPERATOR: str = ">="


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


def _extract_roi(img: np.ndarray, roi: list[int] | tuple[int, int, int, int] | None) -> tuple[np.ndarray | None, str]:
    if roi is None or len(roi) != 4:
        return None, "invalid_roi_format"
    rx, ry, rw, rh = roi
    if rw <= 0 or rh <= 0 or rx < 0 or ry < 0:
        return None, "invalid_roi_dimensions"
    ih, iw = img.shape[:2]
    if rx + rw > iw or ry + rh > ih:
        return None, "roi_out_of_bounds"
    roi_img = img[ry:ry+rh, rx:rx+rw]
    if roi_img.size == 0:
        return None, "empty_roi"
    return roi_img, ""


def verify_object_identity(
    reference: str | Path | np.ndarray | None,
    candidate: str | Path | np.ndarray | None,
    *,
    reference_roi: list[int] | tuple[int, int, int, int] | None = None,
    candidate_roi: list[int] | tuple[int, int, int, int] | None = None,
    reference_fixture_id: str = "",
    candidate_fixture_id: str = "",
    reference_identity_id: str = "",
    candidate_identity_id: str = "",
    min_inliers: int = CALIBRATED_OBJECT_MIN_RANSAC_INLIERS,
    min_ratio: float | None = None,
    forced_inliers: int | None = None,
    forced_ratio: float | None = None,
    rng_seed: int = 42,
) -> dict[str, Any]:
    """Evaluate object identity continuity between a reference and a candidate frame.

    Fail-closed semantics:
    - missing reference or candidate -> False
    - unreadable image -> False
    - invalid or missing ROI -> False
    - insufficient keypoints (< 4) -> False
    - descriptor unavailable -> False
    - good matches < 4 -> False
    - homography unavailable / RANSAC failure -> False
    - ransac_inliers < min_inliers -> False
    - ransac_inlier_ratio < min_ratio (if min_ratio is provided) -> False
    """
    evidence: dict[str, Any] = {
        "reference_fixture_id": reference_fixture_id,
        "candidate_fixture_id": candidate_fixture_id,
        "reference_identity_id": reference_identity_id,
        "candidate_identity_id": candidate_identity_id,
        "reference_keypoint_count": 0,
        "candidate_keypoint_count": 0,
        "knn_pair_count": 0,
        "good_match_count": 0,
        "homography_available": False,
        "ransac_inlier_count": 0,
        "ransac_inlier_ratio": 0.0,
        "min_inliers_threshold": min_inliers,
        "min_ratio_threshold": min_ratio,
        "inlier_count_operator": INLIER_COUNT_OPERATOR,
        "inlier_ratio_operator": INLIER_RATIO_OPERATOR,
        "decision": False,
        "object_identity": False,
        "candidate_object_bbox": None,
        "candidate_object_quad": None,
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

    # ROI verification (fail closed on missing or out of bounds)
    ref_roi_img, ref_roi_err = _extract_roi(ref_img, reference_roi)
    if ref_roi_img is None:
        evidence["failure_reason"] = f"invalid_reference_roi:{ref_roi_err}"
        return evidence

    cand_roi_img, cand_roi_err = _extract_roi(cand_img, candidate_roi)
    if cand_roi_img is None:
        evidence["failure_reason"] = f"invalid_candidate_roi:{cand_roi_err}"
        return evidence

    # SIFT feature extraction
    sift = cv2.SIFT_create()
    ref_gray = cv2.cvtColor(ref_roi_img, cv2.COLOR_BGR2GRAY)
    cand_gray = cv2.cvtColor(cand_roi_img, cv2.COLOR_BGR2GRAY)

    ref_kp, ref_desc = sift.detectAndCompute(ref_gray, None)
    cand_kp, cand_desc = sift.detectAndCompute(cand_gray, None)

    ref_kp_count = len(ref_kp) if ref_kp is not None else 0
    cand_kp_count = len(cand_kp) if cand_kp is not None else 0
    evidence["reference_keypoint_count"] = ref_kp_count
    evidence["candidate_keypoint_count"] = cand_kp_count

    if ref_kp_count < 4:
        evidence["failure_reason"] = "insufficient_keypoints_in_reference"
        return evidence
    if cand_kp_count < 4:
        evidence["failure_reason"] = "insufficient_keypoints_in_candidate"
        return evidence

    if ref_desc is None or len(ref_desc) < 4:
        evidence["failure_reason"] = "descriptor_unavailable_reference"
        return evidence
    if cand_desc is None or len(cand_desc) < 4:
        evidence["failure_reason"] = "descriptor_unavailable_candidate"
        return evidence

    # Deterministic matching setup
    cv2.setRNGSeed(rng_seed)
    np.random.seed(rng_seed)

    FLANN_INDEX_KDTREE = 1
    index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
    search_params = dict(checks=50)
    flann = cv2.FlannBasedMatcher(index_params, search_params)

    matches = flann.knnMatch(ref_desc, cand_desc, k=2)
    evidence["knn_pair_count"] = len(matches)

    good = []
    for pair in matches:
        if len(pair) == 2:
            m, n = pair
            if m.distance < RATIO_TEST_CUTOFF * n.distance:
                good.append(m)

    good_count = len(good)
    evidence["good_match_count"] = good_count

    if good_count < 4:
        evidence["failure_reason"] = "insufficient_ratio_test_matches"
        return evidence

    # Geometric verification via RANSAC homography
    src_pts = np.float32([ref_kp[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst_pts = np.float32([cand_kp[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

    H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, RANSAC_REPROJECTION_THRESHOLD)
    if H is None or mask is None:
        evidence["failure_reason"] = "homography_unavailable"
        return evidence

    evidence["homography_available"] = True
    inliers = int(mask.sum())
    ratio = inliers / good_count if good_count > 0 else 0.0

    if forced_inliers is not None:
        inliers = forced_inliers
    if forced_ratio is not None:
        ratio = forced_ratio

    evidence["ransac_inlier_count"] = inliers
    evidence["ransac_inlier_ratio"] = ratio

    if inliers < min_inliers:
        evidence["failure_reason"] = f"inliers_below_threshold:{inliers}<{min_inliers}"
        return evidence

    if min_ratio is not None and ratio < min_ratio:
        evidence["failure_reason"] = f"ratio_below_threshold:{ratio:.4f}<{min_ratio}"
        return evidence

    # Homography-derived candidate object localization
    ref_h, ref_w = ref_roi_img.shape[:2]
    ref_corners = np.float32([[0.0, 0.0], [float(ref_w), 0.0], [float(ref_w), float(ref_h)], [0.0, float(ref_h)]]).reshape(-1, 1, 2)

    try:
        projected = cv2.perspectiveTransform(ref_corners, H)
        if projected is None or len(projected) != 4:
            evidence["failure_reason"] = "invalid_perspective_transform"
            evidence["localization_failure_reason"] = "invalid_perspective_transform"
            return evidence

        cand_offset_x = float(candidate_roi[0]) if candidate_roi is not None and len(candidate_roi) >= 1 else 0.0
        cand_offset_y = float(candidate_roi[1]) if candidate_roi is not None and len(candidate_roi) >= 2 else 0.0

        quad: list[list[float]] = []
        coords_finite = True
        for pt in projected:
            qx = float(pt[0][0]) + cand_offset_x
            qy = float(pt[0][1]) + cand_offset_y
            if not (math.isfinite(qx) and math.isfinite(qy)):
                coords_finite = False
                break
            quad.append([round(qx, 2), round(qy, 2)])

        if not coords_finite or len(quad) != 4:
            evidence["failure_reason"] = "nonfinite_projected_coordinates"
            evidence["localization_failure_reason"] = "nonfinite_projected_coordinates"
            return evidence

        contour = np.array(quad, dtype=np.float32)
        quad_area = float(cv2.contourArea(contour))
        if quad_area <= 0.0 or not math.isfinite(quad_area):
            evidence["failure_reason"] = "degenerate_quad_area"
            evidence["localization_failure_reason"] = "degenerate_quad_area"
            return evidence

        cand_h_full, cand_w_full = cand_img.shape[:2]
        xs = [p[0] for p in quad]
        ys = [p[1] for p in quad]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        if max_x <= 0.0 or min_x >= float(cand_w_full) or max_y <= 0.0 or min_y >= float(cand_h_full):
            evidence["failure_reason"] = "projected_bbox_outside_frame"
            evidence["localization_failure_reason"] = "projected_bbox_outside_frame"
            return evidence

        clamped_min_x = max(0.0, min_x)
        clamped_max_x = min(float(cand_w_full), max_x)
        clamped_min_y = max(0.0, min_y)
        clamped_max_y = min(float(cand_h_full), max_y)
        bbox_w = clamped_max_x - clamped_min_x
        bbox_h = clamped_max_y - clamped_min_y

        if bbox_w <= 0.0 or bbox_h <= 0.0:
            evidence["failure_reason"] = "degenerate_clamped_bbox"
            evidence["localization_failure_reason"] = "degenerate_clamped_bbox"
            return evidence

        evidence["candidate_object_bbox"] = [
            round(clamped_min_x, 2),
            round(clamped_min_y, 2),
            round(bbox_w, 2),
            round(bbox_h, 2),
        ]
        evidence["candidate_object_quad"] = quad
    except Exception as loc_exc:
        evidence["failure_reason"] = f"localization_exception:{loc_exc}"
        evidence["localization_failure_reason"] = f"localization_exception:{loc_exc}"
        return evidence

    evidence["decision"] = True
    evidence["object_identity"] = True
    return evidence


def evaluate_object_continuity_from_provider_payload(
    provider_task_payload: dict[str, Any] | None,
    *,
    reference_path: str | Path | None = None,
    candidate_path: str | Path | None = None,
    reference_roi: list[int] | None = None,
    candidate_roi: list[int] | None = None,
) -> dict[str, Any]:
    """Provider transport success alone NEVER constitutes object continuity evidence.

    Fails closed if local visual verification has not been performed.
    """
    if provider_task_payload is None:
        return {
            "decision": False,
            "object_identity": False,
            "candidate_object_bbox": None,
            "candidate_object_quad": None,
            "failure_reason": "missing_provider_payload",
        }

    status = provider_task_payload.get("status") or provider_task_payload.get("task_status")
    if status not in {"SUCCESS", "COMPLETED", "200"}:
        return {
            "decision": False,
            "object_identity": False,
            "candidate_object_bbox": None,
            "candidate_object_quad": None,
            "failure_reason": f"provider_status_not_success:{status}",
        }

    # If no local images provided, provider success alone cannot certify identity
    if reference_path is None or candidate_path is None:
        return {
            "decision": False,
            "object_identity": False,
            "candidate_object_bbox": None,
            "candidate_object_quad": None,
            "failure_reason": "transport_success_without_local_visual_evidence",
        }

    return verify_object_identity(
        reference_path,
        candidate_path,
        reference_roi=reference_roi,
        candidate_roi=candidate_roi,
    )
