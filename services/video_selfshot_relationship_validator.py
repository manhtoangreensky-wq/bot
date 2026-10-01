"""Calibrated fail-closed person-object relationship validator for Self-shot Scene Change.

Evaluates spatial relationship continuity between verified person and object detections.
Threshold is derived empirically from safe local public domain NASA calibration fixtures.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

# Empirically calibrated from local safe NASA relationship fixtures:
# POSITIVE_DREL_RANGE: [0.008842, 0.256615], MEDIAN = 0.128593
# NEGATIVE_DREL_RANGE: [0.306441, 0.553601], MEDIAN = 0.442893
# GAP: 0.049826 (min_neg - max_pos)
# MIDPOINT: 0.281528, MARGIN = 0.024913
CALIBRATED_RELATIONSHIP_DISTANCE_MAX: float = 0.281528
DREL_OPERATOR: str = "<="
PRIMARY_RELATION_TYPE: str = "holding_or_close"
SUPPORTED_RELATION_TYPES: set[str] = {"holding_or_close"}


def validate_bbox(
    bbox: Any,
    frame_width: int | float | None,
    frame_height: int | float | None,
    bbox_name: str = "bbox",
) -> tuple[bool, str]:
    """Validate bounding box dimensions and bounds."""
    if bbox is None:
        return False, f"missing_{bbox_name}"
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return False, f"invalid_{bbox_name}_format"

    x, y, w, h = bbox
    for val in (x, y, w, h):
        if not isinstance(val, (int, float)) or not math.isfinite(val):
            return False, f"nonfinite_{bbox_name}"

    if w <= 0 or h <= 0 or x < 0 or y < 0:
        return False, f"invalid_{bbox_name}_dimensions"

    if frame_width is not None and frame_height is not None:
        if not math.isfinite(frame_width) or not math.isfinite(frame_height) or frame_width <= 0 or frame_height <= 0:
            return False, "invalid_frame_dimensions"
        if x + w > frame_width or y + h > frame_height:
            return False, f"{bbox_name}_out_of_bounds"

    return True, ""


def compute_relationship_geometry(
    person_bbox: list[int | float] | tuple[int | float, ...],
    object_bbox: list[int | float] | tuple[int | float, ...],
    frame_width: int | float,
    frame_height: int | float,
) -> dict[str, Any]:
    """Compute spatial distance and overlap metrics between person and object bboxes."""
    p_ok, p_err = validate_bbox(person_bbox, frame_width, frame_height, "person_bbox")
    if not p_ok:
        return {"valid": False, "error": p_err}

    o_ok, o_err = validate_bbox(object_bbox, frame_width, frame_height, "object_bbox")
    if not o_ok:
        return {"valid": False, "error": o_err}

    px, py, pw, ph = person_bbox
    ox, oy, ow, oh = object_bbox

    c_px = px + pw / 2.0
    c_py = py + ph / 2.0
    c_ox = ox + ow / 2.0
    c_oy = oy + oh / 2.0

    center_distance_pixels = math.hypot(c_px - c_ox, c_py - c_oy)
    frame_diagonal = math.hypot(frame_width, frame_height)
    drel = center_distance_pixels / frame_diagonal

    # IoU
    ix1, iy1 = max(px, ox), max(py, oy)
    ix2, iy2 = min(px + pw, ox + ow), min(py + ph, oy + oh)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    union = (pw * ph) + (ow * oh) - inter
    iou = inter / union if union > 0.0 else 0.0

    return {
        "valid": True,
        "error": "",
        "person_center": (round(c_px, 2), round(c_py, 2)),
        "object_center": (round(c_ox, 2), round(c_oy, 2)),
        "center_distance_pixels": round(center_distance_pixels, 4),
        "frame_diagonal": round(frame_diagonal, 4),
        "drel": round(drel, 6),
        "iou": round(iou, 6),
    }


def verify_person_object_relationship(
    *,
    person_identity: bool = False,
    object_identity: bool = False,
    same_frame_cooccurrence: bool = True,
    person_bbox: list[int | float] | tuple[int | float, ...] | None = None,
    object_bbox: list[int | float] | tuple[int | float, ...] | None = None,
    frame_width: int | float | None = None,
    frame_height: int | float | None = None,
    relationship_type: str = PRIMARY_RELATION_TYPE,
    threshold: float = CALIBRATED_RELATIONSHIP_DISTANCE_MAX,
    forced_drel: float | None = None,
) -> dict[str, Any]:
    """Verify person-object relationship in a single frame with strict fail-closed gates."""
    result: dict[str, Any] = {
        "relationship_type": relationship_type,
        "primary_metric": "NORMALIZED_CENTER_DISTANCE_DREL",
        "secondary_metric": "NOT_REQUIRED",
        "iou_role": "SUPPORTING_GEOMETRY_ONLY",
        "threshold": threshold,
        "threshold_operator": DREL_OPERATOR,
        "drel": None,
        "iou": None,
        "person_identity": person_identity,
        "object_identity": object_identity,
        "same_frame_cooccurrence": same_frame_cooccurrence,
        "decision": False,
        "relationship_valid": False,
        "failure_reason": "",
    }

    # Upstream identity gates
    if not person_identity:
        result["failure_reason"] = "person_identity_false"
        return result
    if not object_identity:
        result["failure_reason"] = "object_identity_false"
        return result
    if not same_frame_cooccurrence:
        result["failure_reason"] = "no_same_frame_cooccurrence"
        return result

    # Relation type gate
    if relationship_type not in SUPPORTED_RELATION_TYPES:
        result["failure_reason"] = "unsupported_relation_type"
        return result

    # Forced Drel for boundary testing
    if forced_drel is not None:
        if not math.isfinite(forced_drel) or forced_drel < 0:
            result["failure_reason"] = "nonfinite_drel"
            return result
        drel_val = float(forced_drel)
        result["drel"] = round(drel_val, 6)
        if drel_val <= threshold:
            result["decision"] = True
            result["relationship_valid"] = True
        else:
            result["failure_reason"] = "drel_above_threshold"
        return result

    # Geometry calculation
    if person_bbox is None:
        result["failure_reason"] = "missing_person_bbox"
        return result
    if object_bbox is None:
        result["failure_reason"] = "missing_object_bbox"
        return result
    if frame_width is None or frame_height is None:
        result["failure_reason"] = "missing_frame_dimensions"
        return result

    geom = compute_relationship_geometry(person_bbox, object_bbox, frame_width, frame_height)
    if not geom["valid"]:
        result["failure_reason"] = geom["error"]
        return result

    drel_val = geom["drel"]
    result["drel"] = drel_val
    result["iou"] = geom["iou"]
    result["center_distance_pixels"] = geom["center_distance_pixels"]
    result["frame_diagonal"] = geom["frame_diagonal"]

    # Threshold evaluation: operator <=
    if drel_val <= threshold:
        result["decision"] = True
        result["relationship_valid"] = True
    else:
        result["decision"] = False
        result["relationship_valid"] = False
        result["failure_reason"] = "drel_above_threshold"

    return result


def evaluate_scene_relationship_continuity(
    frame_decisions: list[bool],
    scene_duration_seconds: int | float,
) -> dict[str, Any]:
    """Aggregate frame-level relationship decisions according to the temporal contract."""
    total_frames = len(frame_decisions)
    passing_frames = sum(1 for d in frame_decisions if d)

    if scene_duration_seconds <= 5:
        required_samples = 3
        required_passes = 2
    else:
        required_samples = 5
        required_passes = 3

    passed = (total_frames >= required_samples) and (passing_frames >= required_passes)

    return {
        "scene_duration_seconds": scene_duration_seconds,
        "total_frames_sampled": total_frames,
        "passing_frames": passing_frames,
        "required_samples": required_samples,
        "required_passes": required_passes,
        "temporal_ratio": f"{passing_frames}/{total_frames}",
        "decision": passed,
        "scene_relationship_continuity": passed,
    }


def evaluate_relationship_continuity_from_provider_payload(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate relationship continuity from an upstream provider payload.

    Fail-closed: transport success without local relationship evidence is rejected.
    """
    transport_success = payload.get("status") in ("COMPLETED", "SUCCESS", "DONE")
    relationship_evidence = payload.get("relationship_evidence")

    if not transport_success:
        return {
            "decision": False,
            "relationship_valid": False,
            "failure_reason": "transport_unsuccessful",
        }

    if not relationship_evidence or not isinstance(relationship_evidence, dict):
        return {
            "decision": False,
            "relationship_valid": False,
            "failure_reason": "transport_success_without_relationship_evidence",
        }

    # Evaluate using local validator
    return verify_person_object_relationship(
        person_identity=relationship_evidence.get("person_identity", False),
        object_identity=relationship_evidence.get("object_identity", False),
        same_frame_cooccurrence=relationship_evidence.get("same_frame_cooccurrence", False),
        person_bbox=relationship_evidence.get("person_bbox"),
        object_bbox=relationship_evidence.get("object_bbox"),
        frame_width=relationship_evidence.get("frame_width"),
        frame_height=relationship_evidence.get("frame_height"),
        relationship_type=relationship_evidence.get("relationship_type", PRIMARY_RELATION_TYPE),
    )
