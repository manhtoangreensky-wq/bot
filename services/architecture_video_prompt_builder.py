"""Provider-free architecture video prompt builder."""

from __future__ import annotations

import re
from typing import Any

from services.architecture_scene_planner import build_architecture_scene_plan


CAMERA_PRESETS = (
    "Slow dolly-in", "Smooth corridor walkthrough", "Orbit around exterior",
    "Crane-up reveal", "Doorway transition", "Room-to-room continuity",
    "Top-down floor-plan reveal", "Wireframe-to-render transition",
    "Before/after split reveal", "Day-to-night timelapse",
    "Static cinematic push-in",
)

VIDEO_NEGATIVE_PROMPT = (
    "geometry drift", "changing door or window positions",
    "inconsistent furniture", "camera teleport", "camera jitter", "flicker",
    "warped walls", "bending columns", "duplicated furniture",
    "disappearing objects", "changing floor plan", "unstable lighting",
    "impossible reflections", "sudden weather changes", "text artifacts",
    "watermark", "low detail", "frame interpolation artifacts",
    "invented dimensions", "invented amenities", "misleading room scale",
)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        match = re.search(r"\d+", _clean(value))
        return int(match.group()) if match else int(default)


def _text_list(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple, set)) else [value]
    return [_clean(item) for item in values if _clean(item)]


def _transition_for(payload: dict[str, Any]) -> str:
    transition = _clean(payload.get("transition"))
    if transition:
        return transition
    text = _clean(payload.get("user_text")).lower()
    if "before" in text or "after" in text or "trước" in text or "sau cải tạo" in text:
        return "before/after match-cut reveal while preserving the same viewpoint"
    if "wireframe" in text or "mặt bằng" in text:
        return "wireframe-to-render reveal with fixed geometry"
    if "ban đêm" in text or "day to night" in text:
        return "controlled day-to-night transition with stable materials"
    return "natural spatial continuity without camera teleport"


def build_architecture_video_prompt(payload: dict[str, Any]) -> dict[str, Any]:
    raw_plan = payload.get("scene_plan")
    if isinstance(raw_plan, dict):
        plan = dict(raw_plan)
    elif isinstance(raw_plan, list):
        plan = {
            "shots": [dict(item) for item in raw_plan if isinstance(item, dict)],
            "total_duration_seconds": _safe_int(payload.get("duration"), 0),
            "aspect_ratio": _clean(payload.get("aspect_ratio") or "16:9"),
        }
    else:
        plan = {}
    if not plan.get("shots"):
        plan = build_architecture_scene_plan(payload)
    shots = [dict(item) for item in (plan.get("shots") or []) if isinstance(item, dict)]
    source = _clean(payload.get("source_description") or payload.get("existing_condition") or "customer-supplied project context")
    objective = _clean(payload.get("user_text") or payload.get("architecture_objective") or "create a coherent architecture presentation")
    preserve = _text_list(payload.get("preserve_requirements"))
    if not preserve:
        preserve = ["preserve geometry, openings, room sequence, materials and customer constraints"]
    start = _clean(payload.get("start_point") or (shots[0].get("start_frame") if shots else "customer-selected start point"))
    camera_path = " → ".join(_clean(item.get("space")) for item in shots if _clean(item.get("space")))
    progression = "; ".join(
        f"Scene {item.get('index')}: {_clean(item.get('camera_motion'))}, focus {_clean(item.get('visual_focus'))}"
        for item in shots
    )
    speed = _clean(payload.get("camera_speed") or "slow, stable and physically plausible")
    lighting = _clean(payload.get("lighting") or "consistent natural daylight with realistic exposure")
    material = _clean(payload.get("material_behavior") or "physically plausible material response without texture drift")
    transition = _transition_for(payload)
    duration = _safe_int(plan.get("total_duration_seconds") or payload.get("duration"), 0)
    ratio = _clean(plan.get("aspect_ratio") or payload.get("aspect_ratio") or "16:9")
    sections = {
        "source_reference_description": source,
        "architecture_objective": objective,
        "preservation_constraints": "; ".join(preserve),
        "starting_camera_position": start,
        "camera_path": camera_path or "single controlled architectural reveal",
        "shot_progression": progression or "one stable architectural hero shot",
        "speed": speed,
        "lighting_state": lighting,
        "material_behavior": material,
        "transition_behavior": transition,
        "scene_consistency": "carry the previous scene end state into the next scene; keep layout, subject, palette and style stable",
        "duration": f"{duration}s",
        "aspect_ratio": ratio,
        "negative_prompt": ", ".join(VIDEO_NEGATIVE_PROMPT),
    }
    prompt = (
        f"Architecture source: {source}. Objective: {objective}. Preserve: {sections['preservation_constraints']}. "
        f"Start camera: {start}. Camera path: {sections['camera_path']}. Shot progression: {sections['shot_progression']}. "
        f"Motion speed: {speed}. Lighting: {lighting}. Materials: {material}. Transition: {transition}. "
        f"Continuity: {sections['scene_consistency']}. Total duration {duration}s, aspect ratio {ratio}. "
        "Do not promise exact architectural accuracy without customer dimensions or references."
    )
    return {
        "ok": True,
        "prompt": _clean(prompt),
        "negative_prompt": sections["negative_prompt"],
        "sections": sections,
        "scene_plan": plan,
        "provider_called": False,
        "job_created": False,
        "xu_charged": 0,
    }
