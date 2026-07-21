"""Canonical continuity contract for scene-first video planning."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


CONTINUITY_FIELDS = (
    "characters",
    "identity",
    "wardrobe",
    "products",
    "logos",
    "environment",
    "architecture_geometry",
    "color_palette",
    "creative_palette_lighting",
    "identity_color_locks",
    "color_conflict_policy",
    "lighting_state",
    "time_of_day",
    "motion_direction",
    "camera_language",
    "audio_style",
    "must_remain_constant",
)


def _items(value: Any) -> list[str]:
    if isinstance(value, str):
        values = re.split(r"[,;\n]+", value)
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = []
    return list(dict.fromkeys(str(item or "").strip() for item in values if str(item or "").strip()))


def build_continuity_contract(
    *,
    subject: str,
    profile_id: str,
    requirements: dict[str, Any] | None = None,
    assets: dict[str, Any] | None = None,
    content_addons: dict[str, Any] | None = None,
) -> dict[str, Any]:
    requirements = dict(requirements or {})
    assets = dict(assets or {})
    addons = dict(content_addons or {})
    subject_clean = re.sub(r"\s+", " ", str(subject or "chủ thể chính").strip())
    constants = _items(requirements.get("preserve_constraints"))
    constants.extend(_items(assets.get("preserve_constraints")))
    constants = list(dict.fromkeys(constants + [f"Giữ nguyên chủ thể: {subject_clean}"]))
    return {
        "characters": _items(assets.get("characters") or requirements.get("characters")),
        "identity": _items(assets.get("identity") or requirements.get("identity")) or [subject_clean],
        "wardrobe": _items(assets.get("wardrobe") or requirements.get("wardrobe")),
        "products": _items(assets.get("products") or requirements.get("products")),
        "logos": _items(assets.get("logos") or requirements.get("logos")),
        "environment": _items(assets.get("environment") or requirements.get("environment")),
        "architecture_geometry": _items(assets.get("architecture_geometry") or requirements.get("architecture_geometry")),
        "color_palette": _items(requirements.get("color_palette") or assets.get("color_palette")),
        "creative_palette_lighting": _items(requirements.get("creative_palette_lighting")),
        "identity_color_locks": _items(requirements.get("identity_color_locks")),
        "color_conflict_policy": str(
            requirements.get("color_conflict_policy")
            or "identity_color_locks_override_creative_palette"
        ),
        "lighting_state": str(requirements.get("lighting_state") or "ánh sáng nhất quán theo profile"),
        "time_of_day": str(requirements.get("time_of_day") or "giữ cùng thời điểm trừ khi có chuyển thời gian chủ ý"),
        "motion_direction": str(requirements.get("motion_direction") or "trái sang phải"),
        "camera_language": str(requirements.get("camera_language") or "chuyển động camera có động cơ, kết thúc tự nhiên"),
        "audio_style": str(addons.get("music_mood") or requirements.get("audio_style") or "đồng nhất theo mạch cảm xúc"),
        "must_remain_constant": constants,
        "profile_id": str(profile_id or "general"),
        "intentional_location_change": bool(requirements.get("intentional_location_change")),
        "intentional_time_jump": bool(requirements.get("intentional_time_jump")),
    }


def inherit_previous_completion(scene: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    result = deepcopy(scene)
    if previous:
        result["inherited_from_previous"] = str(previous.get("completion_state") or "").strip()
        if not str(result.get("start_state") or "").strip():
            result["start_state"] = result["inherited_from_previous"]
    else:
        result["inherited_from_previous"] = ""
    return result


def validate_continuity(scenes: list[dict[str, Any]], contract: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    motion = str(contract.get("motion_direction") or "").strip().lower()
    previous: dict[str, Any] | None = None
    for scene in scenes:
        index = int(scene.get("scene_index") or 0)
        if previous:
            inherited = str(scene.get("inherited_from_previous") or "").strip()
            completion = str(previous.get("completion_state") or "").strip()
            if completion and inherited != completion:
                warnings.append(f"scene_{index}:missing_previous_completion")
        scene_motion = str(scene.get("motion_direction") or motion).strip().lower()
        if motion and scene_motion and scene_motion != motion and not scene.get("intentional_direction_change"):
            warnings.append(f"scene_{index}:unexplained_direction_change")
        if not scene.get("preserve_constraints"):
            warnings.append(f"scene_{index}:missing_preserve_constraints")
        previous = scene
    return {
        "ok": not warnings,
        "warnings": warnings,
        "scene_count": len(scenes),
        "intentional_location_change_allowed": bool(contract.get("intentional_location_change")),
        "intentional_time_jump_allowed": bool(contract.get("intentional_time_jump")),
    }
