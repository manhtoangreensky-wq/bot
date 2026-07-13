"""Deterministic semantic transition planning between complete scene beats."""

from __future__ import annotations

from typing import Any


SUPPORTED_TRANSITIONS = (
    "cut on action",
    "match cut",
    "motion match",
    "camera pan continuation",
    "object wipe",
    "doorway transition",
    "reveal",
    "dissolve",
    "fade",
    "whip pan",
    "before/after morph",
    "sound bridge",
    "dialogue bridge",
)

PROFILE_TRANSITIONS = {
    "architecture": ("doorway transition", "camera pan continuation", "reveal", "match cut"),
    "real_estate": ("doorway transition", "camera pan continuation", "reveal", "dissolve"),
    "product": ("cut on action", "object wipe", "match cut", "sound bridge"),
    "fashion": ("motion match", "whip pan", "match cut", "cut on action"),
    "vfx": ("before/after morph", "match cut", "reveal", "sound bridge"),
    "animation": ("cut on action", "motion match", "dialogue bridge", "dissolve"),
    "tutorial": ("cut on action", "match cut", "sound bridge", "dissolve"),
}


def profile_family(profile_id: str) -> str:
    value = str(profile_id or "").lower()
    for family in PROFILE_TRANSITIONS:
        if family in value:
            return family
    if any(token in value for token in ("property", "estate", "interior")):
        return "real_estate" if "estate" in value or "property" in value else "architecture"
    if any(token in value for token in ("ugc", "review", "showcase")):
        return "product"
    if "character" in value:
        return "animation"
    return "product"


def plan_transitions(
    scenes: list[dict[str, Any]],
    *,
    profile_id: str,
    preferred_style: str = "",
) -> list[dict[str, Any]]:
    family = profile_family(profile_id)
    candidates = list(PROFILE_TRANSITIONS.get(family) or PROFILE_TRANSITIONS["product"])
    preferred = str(preferred_style or "").strip().lower()
    if preferred in SUPPORTED_TRANSITIONS:
        candidates.insert(0, preferred)
    transitions: list[dict[str, Any]] = []
    for offset, (left, right) in enumerate(zip(scenes, scenes[1:])):
        transition = candidates[offset % len(candidates)]
        if offset >= 2 and transitions[-1]["transition_type"] == transitions[-2]["transition_type"] == transition:
            transition = candidates[(offset + 1) % len(candidates)]
        transitions.append({
            "from_scene": int(left.get("scene_index") or offset + 1),
            "to_scene": int(right.get("scene_index") or offset + 2),
            "transition_type": transition,
            "from_state": str(left.get("completion_state") or "cảnh trước hoàn tất"),
            "to_state": str(right.get("start_state") or "cảnh sau bắt đầu"),
            "motion_direction": str(left.get("motion_direction") or right.get("motion_direction") or "giữ hướng chuyển động"),
            "instruction": (
                f"Dùng {transition} sau khi hành động cảnh {int(left.get('scene_index') or offset + 1)} đã hoàn tất; "
                f"nối trạng thái cuối sang mở đầu cảnh {int(right.get('scene_index') or offset + 2)} mà không nhảy camera."
            ),
        })
    return transitions


def apply_transitions(scenes: list[dict[str, Any]], transitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_from = {int(item["from_scene"]): item for item in transitions}
    by_to = {int(item["to_scene"]): item for item in transitions}
    for scene in scenes:
        index = int(scene.get("scene_index") or 0)
        incoming = by_to.get(index)
        outgoing = by_from.get(index)
        scene["transition_in"] = str((incoming or {}).get("transition_type") or ("mở trực tiếp" if index == 1 else "cut"))
        scene["transition_out"] = str((outgoing or {}).get("transition_type") or "kết thúc trọn vẹn")
    return scenes
