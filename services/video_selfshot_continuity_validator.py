"""Calibrated fail-closed scene continuity orchestrator for Self-shot Scene Change.

Composes three independently proven local vision lanes:
1. Person identity validator (YuNet + SFace)
2. Object identity validator (SIFT + FLANN + RANSAC)
3. Person-object relationship validator (spatial proximity Drel)

Enforces strict same-frame co-occurrence, per-frame order, and temporal aggregation.
"""

from __future__ import annotations

import math
import os
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from services.video_selfshot_object_validator import (
    CALIBRATED_OBJECT_MIN_RANSAC_INLIERS,
    verify_object_identity,
)
from services.video_selfshot_person_validator import (
    CALIBRATED_PERSON_THRESHOLD,
    verify_person_identity,
)
from services.video_selfshot_relationship_validator import (
    CALIBRATED_RELATIONSHIP_DISTANCE_MAX,
    PRIMARY_RELATION_TYPE,
    SUPPORTED_RELATION_TYPES,
    verify_person_object_relationship,
)

EVIDENCE_SOURCE = "local_vision_validator"


def sample_frames_from_clip(
    clip_source: str | Path | list[np.ndarray],
    scene_duration_seconds: int | float,
) -> tuple[list[np.ndarray], str]:
    """Sample frames deterministically from a video file or frame sequence.

    Contract:
    - 5s scene: 3 frames
    - 10s / 15s scene: 5 frames
    """
    if isinstance(clip_source, list):
        # Already pre-extracted frames (e.g. for testing)
        target_count = 3 if scene_duration_seconds <= 5 else 5
        if len(clip_source) < target_count:
            return [], "insufficient_frames_provided"
        return clip_source[:target_count], ""

    path_str = str(clip_source)
    if not os.path.isfile(path_str):
        return [], "clip_file_not_found"

    cap = cv2.VideoCapture(path_str)
    if not cap.isOpened():
        return [], "frame_extraction_failed"

    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            return [], "frame_extraction_failed"

        target_count = 3 if scene_duration_seconds <= 5 else 5
        if target_count == 3:
            fractions = [0.25, 0.50, 0.75]
        else:
            fractions = [0.166, 0.333, 0.500, 0.666, 0.833]

        frames: list[np.ndarray] = []
        for frac in fractions:
            frame_idx = max(0, min(total_frames - 1, int(total_frames * frac)))
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                return [], "frame_extraction_failed"
            frames.append(frame)

        return frames, ""
    finally:
        cap.release()


def validate_selfshot_scene_continuity(
    clip_source: str | Path | list[np.ndarray],
    *,
    scene_index: int = 1,
    scene_duration_seconds: int | float = 5,
    person_required: bool = False,
    object_required: bool = False,
    relationship_required: bool = False,
    person_reference: Any = None,
    object_reference: Any = None,
    object_reference_roi: list[int] | tuple[int, int, int, int] | None = None,
    relationship_type: str = PRIMARY_RELATION_TYPE,
    asset_pack: dict[str, Any] | None = None,
    subject_manifest: dict[str, Any] | None = None,
    job: dict[str, Any] | None = None,
    mock_frame_observations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate integrated scene continuity across person, object, and relationship lanes."""
    start_time = time.perf_counter()

    # Resolve requirements from subject_manifest or asset_pack if provided
    manifest = dict(subject_manifest or {})
    if not manifest and asset_pack:
        manifest = dict(asset_pack.get("subject_manifest") or {})
    if not manifest and job:
        manifest = dict((job.get("asset_pack") or {}).get("subject_manifest") or {})

    if manifest:
        person_required = person_required or bool(manifest.get("person_subject_ids"))
        object_required = object_required or bool(manifest.get("object_subject_ids"))
        relationship_required = relationship_required or (person_required and object_required)

    threshold_profile = {
        "person_threshold": CALIBRATED_PERSON_THRESHOLD,
        "object_min_ransac_inliers": CALIBRATED_OBJECT_MIN_RANSAC_INLIERS,
        "relationship_distance_max": CALIBRATED_RELATIONSHIP_DISTANCE_MAX,
    }

    is_mock = mock_frame_observations is not None
    base_result: dict[str, Any] = {
        "ok": False,
        "blocker": "",
        "failure_reason": "",
        "scene_index": scene_index,
        "scene_duration_seconds": scene_duration_seconds,
        "sampled_frame_count": 0,
        "person_required": person_required,
        "object_required": object_required,
        "relationship_required": relationship_required,
        "person_identity": False,
        "object_identity": False,
        "person_object_relationship": False,
        "person_observations": [],
        "object_observations": [],
        "relationship_observations": [],
        "threshold_profile": threshold_profile,
        "evidence_source": "test_mock" if is_mock else EVIDENCE_SOURCE,
        "independent_visual_validation": "NOT_PERFORMED",
        "wall_clock_seconds": 0.0,
    }

    # If neither person nor object is required, visual identity is not required
    if not (person_required or object_required):
        base_result["ok"] = True
        base_result["blocker"] = ""
        base_result["failure_reason"] = ""
        base_result["independent_visual_validation"] = "NOT_PERFORMED"
        base_result["wall_clock_seconds"] = round(time.perf_counter() - start_time, 4)
        return base_result

    # Resolve references and options from asset_pack or job if not explicitly provided
    # STRICT SAFETY: asset_pack and job can NEVER inject mock_frame_observations.
    # mock_frame_observations is strictly reserved for unit test temporal aggregation harnesses
    # passed directly as a function argument.
    if person_reference is None:
        person_reference = (
            (asset_pack or {}).get("person_reference")
            or (asset_pack or {}).get("person_reference_image")
            or (asset_pack or {}).get("person_image_path")
            or (job or {}).get("person_reference")
            or (job or {}).get("person_reference_image")
            or (manifest or {}).get("person_reference")
        )
    if object_reference is None:
        object_reference = (
            (asset_pack or {}).get("object_reference")
            or (asset_pack or {}).get("object_reference_image")
            or (asset_pack or {}).get("object_image_path")
            or (job or {}).get("object_reference")
            or (job or {}).get("object_reference_image")
            or (manifest or {}).get("object_reference")
        )
    if object_reference_roi is None:
        object_reference_roi = (
            (asset_pack or {}).get("object_reference_roi")
            or (job or {}).get("object_reference_roi")
            or (manifest or {}).get("object_reference_roi")
        )
    if relationship_type == PRIMARY_RELATION_TYPE:
        custom_type = (
            (asset_pack or {}).get("relationship_type")
            or (job or {}).get("relationship_type")
            or (manifest or {}).get("relationship_type")
        )
        if custom_type:
            relationship_type = str(custom_type).strip().lower()

    # Reference checks
    if person_required and person_reference is None and mock_frame_observations is None:
        base_result["blocker"] = "selfshot2_person_reference_missing"
        base_result["failure_reason"] = "person_reference_missing"
        base_result["wall_clock_seconds"] = round(time.perf_counter() - start_time, 4)
        return base_result

    if object_required and object_reference is None and mock_frame_observations is None:
        base_result["blocker"] = "selfshot2_object_reference_missing"
        base_result["failure_reason"] = "object_reference_missing"
        base_result["wall_clock_seconds"] = round(time.perf_counter() - start_time, 4)
        return base_result

    # Relationship type check
    if relationship_required and relationship_type not in SUPPORTED_RELATION_TYPES:
        base_result["blocker"] = "unsupported_relation_type"
        base_result["failure_reason"] = "unsupported_relation_type"
        base_result["wall_clock_seconds"] = round(time.perf_counter() - start_time, 4)
        return base_result

    # Frame extraction or mock injection
    sampled_frames: list[Any] = []
    if mock_frame_observations is not None:
        frame_observations = []
        for f_idx, item in enumerate(mock_frame_observations):
            obs = dict(item)
            obs.setdefault("frame_index", f_idx)
            p_ok = bool(obs.get("person_ok")) if person_required else True
            o_ok = bool(obs.get("object_ok")) if object_required else True
            if relationship_required:
                if not (p_ok and o_ok):
                    r_ok = False
                else:
                    r_ok = bool(obs.get("relationship_ok"))
            else:
                r_ok = True
            obs["person_ok"] = p_ok
            obs["object_ok"] = o_ok
            obs["relationship_ok"] = r_ok
            p_cond = (not person_required) or p_ok
            o_cond = (not object_required) or o_ok
            r_cond = (not relationship_required) or r_ok
            obs["integrated_ok"] = p_cond and o_cond and r_cond
            frame_observations.append(obs)
        sampled_count = len(frame_observations)
    else:
        sampled_frames, err = sample_frames_from_clip(clip_source, scene_duration_seconds)
        if err or not sampled_frames:
            base_result["blocker"] = err or "frame_extraction_failed"
            base_result["failure_reason"] = err or "frame_extraction_failed"
            base_result["wall_clock_seconds"] = round(time.perf_counter() - start_time, 4)
            return base_result
        sampled_count = len(sampled_frames)

        frame_observations = []
        for f_idx, frame in enumerate(sampled_frames):
            fh, fw = frame.shape[:2]
            f_obs: dict[str, Any] = {
                "frame_index": f_idx,
                "person_ok": False,
                "object_ok": False,
                "relationship_ok": False,
                "person_bbox": None,
                "object_bbox": None,
                "integrated_ok": False,
            }

            # 1. Person Identity
            if person_required:
                try:
                    p_res = verify_person_identity(person_reference, frame)
                    f_obs["person_ok"] = bool(p_res.get("decision"))
                    f_obs["person_bbox"] = p_res.get("face_bbox")
                except Exception as exc:
                    base_result["blocker"] = f"person_validator_exception: {exc}"
                    base_result["failure_reason"] = "validator_exception"
                    base_result["wall_clock_seconds"] = round(time.perf_counter() - start_time, 4)
                    return base_result
            else:
                f_obs["person_ok"] = True

            # 2. Object Identity
            if object_required:
                try:
                    c_roi = [0, 0, fw, fh]
                    o_res = verify_object_identity(object_reference, frame, reference_roi=object_reference_roi, candidate_roi=c_roi)
                    f_obs["object_ok"] = bool(o_res.get("decision"))
                    f_obs["object_bbox"] = o_res.get("candidate_object_bbox")
                    f_obs["object_quad"] = o_res.get("candidate_object_quad")
                except Exception as exc:
                    base_result["blocker"] = f"object_validator_exception: {exc}"
                    base_result["failure_reason"] = "validator_exception"
                    base_result["wall_clock_seconds"] = round(time.perf_counter() - start_time, 4)
                    return base_result
            else:
                f_obs["object_ok"] = True

            # 3. Relationship Evaluation (Strict Same-Frame Co-occurrence)
            if relationship_required:
                if f_obs["person_ok"] and f_obs["object_ok"]:
                    try:
                        r_res = verify_person_object_relationship(
                            person_identity=f_obs["person_ok"],
                            object_identity=f_obs["object_ok"],
                            same_frame_cooccurrence=True,
                            person_bbox=f_obs.get("person_bbox"),
                            object_bbox=f_obs.get("object_bbox"),
                            frame_width=fw,
                            frame_height=fh,
                            relationship_type=relationship_type,
                        )
                        f_obs["relationship_ok"] = bool(r_res.get("decision"))
                    except Exception as exc:
                        base_result["blocker"] = f"relationship_validator_exception: {exc}"
                        base_result["failure_reason"] = "validator_exception"
                        base_result["wall_clock_seconds"] = round(time.perf_counter() - start_time, 4)
                        return base_result
                else:
                    # Identity failure blocks relationship from rescuing frame
                    f_obs["relationship_ok"] = False
            else:
                f_obs["relationship_ok"] = True

            # Integrated frame decision
            p_cond = (not person_required) or f_obs["person_ok"]
            o_cond = (not object_required) or f_obs["object_ok"]
            r_cond = (not relationship_required) or f_obs["relationship_ok"]
            f_obs["integrated_ok"] = p_cond and o_cond and r_cond
            frame_observations.append(f_obs)

    base_result["sampled_frame_count"] = sampled_count
    base_result["person_observations"] = [
        {"frame_index": obs.get("frame_index"), "person_ok": obs.get("person_ok"), "person_bbox": obs.get("person_bbox")}
        for obs in frame_observations
    ]
    base_result["object_observations"] = [
        {"frame_index": obs.get("frame_index"), "object_ok": obs.get("object_ok"), "object_bbox": obs.get("object_bbox")}
        for obs in frame_observations
    ]
    base_result["relationship_observations"] = [
        {"frame_index": obs.get("frame_index"), "relationship_ok": obs.get("relationship_ok")}
        for obs in frame_observations
    ]

    # Temporal Aggregation
    if scene_duration_seconds <= 5:
        required_samples = 3
        required_passes = 2
    else:
        required_samples = 5
        required_passes = 3

    if sampled_count < required_samples:
        base_result["blocker"] = "insufficient_temporal_evidence"
        base_result["failure_reason"] = "insufficient_temporal_evidence"
        base_result["wall_clock_seconds"] = round(time.perf_counter() - start_time, 4)
        return base_result

    passing_integrated = sum(1 for obs in frame_observations if obs.get("integrated_ok"))
    person_passes = sum(1 for obs in frame_observations if obs.get("person_ok"))
    object_passes = sum(1 for obs in frame_observations if obs.get("object_ok"))
    relationship_passes = sum(1 for obs in frame_observations if obs.get("relationship_ok"))

    # Cardinality rules
    if person_required:
        base_result["person_identity"] = person_passes >= required_passes
    else:
        base_result["person_identity"] = False  # Not required, not claimed as visually proven

    if object_required:
        base_result["object_identity"] = object_passes >= required_passes
    else:
        base_result["object_identity"] = False

    if relationship_required:
        base_result["person_object_relationship"] = relationship_passes >= required_passes
    else:
        base_result["person_object_relationship"] = False

    # Measured continuity dimensions (strictly empirical, no synthetic boolean proxies)
    temporal_pass_ratio = round(passing_integrated / max(1, sampled_count), 4)
    identity_score = round(person_passes / max(1, sampled_count), 4) if person_required else 1.0
    object_score = round(object_passes / max(1, sampled_count), 4) if object_required else 1.0
    relationship_score = round(relationship_passes / max(1, sampled_count), 4) if relationship_required else 1.0

    # Measured motion score from inter-frame differences or explicit motion observation measurements
    motion_scores_list = []
    if isinstance(sampled_frames, list) and len(sampled_frames) >= 2:
        for idx in range(len(sampled_frames) - 1):
            f1 = sampled_frames[idx]
            f2 = sampled_frames[idx + 1]
            if f1 is not None and f2 is not None:
                g1 = cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY)
                g2 = cv2.cvtColor(f2, cv2.COLOR_BGR2GRAY)
                if g1.shape == g2.shape:
                    diff = cv2.absdiff(g1, g2)
                    diff_val = float(np.mean(diff) / 255.0)
                    motion_scores_list.append(max(0.0, min(1.0, 1.0 - diff_val)))
    if not motion_scores_list and frame_observations:
        for obs in frame_observations:
            if obs.get("motion_score") is not None:
                motion_scores_list.append(float(obs["motion_score"]))
            elif obs.get("motion_diff") is not None:
                diff_val = float(obs["motion_diff"])
                motion_scores_list.append(max(0.0, min(1.0, 1.0 - diff_val)))

    # Measured motion score: strictly zero if unmeasured, never falls back to temporal_pass_ratio or boolean ok
    measured_motion_score = round(float(np.mean(motion_scores_list)), 4) if motion_scores_list else 0.0

    # Measured body proportion score from bounding box stability
    person_boxes = [obs["person_bbox"] for obs in frame_observations if obs.get("person_bbox")]
    if not person_required:
        measured_body_score = 1.0
    elif person_boxes and len(person_boxes) >= 2:
        ratios = [b[3] / max(1.0, b[2]) for b in person_boxes if len(b) >= 4]
        if len(ratios) >= 2:
            mean_r = sum(ratios) / len(ratios)
            max_dev = max(abs(r - mean_r) / mean_r for r in ratios)
            measured_body_score = round(max(0.0, min(1.0, 1.0 - max_dev)), 4)
        else:
            measured_body_score = 0.0
    else:
        # Person required but bounding boxes missing or insufficient -> strictly fail closed 0.0
        measured_body_score = 0.0

    base_result["passing_integrated"] = passing_integrated
    base_result["temporal_pass_ratio"] = temporal_pass_ratio
    base_result["motion_score"] = measured_motion_score
    base_result["body_score"] = measured_body_score
    base_result["continuity_scores"] = {
        "identity": identity_score,
        "body": measured_body_score,
        "motion": measured_motion_score,
        "object": object_score,
        "interaction": relationship_score,
        "temporal": temporal_pass_ratio,
    }

    if passing_integrated >= required_passes:
        base_result["ok"] = True
        base_result["independent_visual_validation"] = "NOT_PERFORMED" if is_mock else "LOCAL_MODEL"
        base_result["evidence_source"] = "test_mock" if is_mock else EVIDENCE_SOURCE
        base_result["blocker"] = ""
        base_result["failure_reason"] = ""
    else:
        base_result["ok"] = False
        base_result["independent_visual_validation"] = "NOT_PERFORMED"
        base_result["evidence_source"] = "test_mock" if is_mock else EVIDENCE_SOURCE
        base_result["blocker"] = "insufficient_temporal_evidence"
        base_result["failure_reason"] = "insufficient_temporal_evidence"

    base_result["wall_clock_seconds"] = round(time.perf_counter() - start_time, 4)
    return base_result
