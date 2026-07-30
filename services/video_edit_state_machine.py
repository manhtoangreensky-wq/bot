"""Canonical intake state for the three public Video Edit lanes."""

from __future__ import annotations

from typing import Any, Mapping


EDIT_MODES = frozenset({"manual_edit", "ai_edit", "quality_enhance"})

_UPLOAD_SCREENS = {
    "manual_edit": "manual_edit_upload",
    "ai_edit": "ai_edit_upload",
    "quality_enhance": "quality_enhance_upload",
}

_READY_SCREENS = {
    "manual_edit": "manual_edit",
    "ai_edit": "ai_edit",
    "quality_enhance": "quality_enhance",
}

_LANE_CALLBACKS = {
    "manual_edit": "videoedit|manual",
    "ai_edit": "videoedit|ai",
    "quality_enhance": "videoedit|restore",
}

_SCREEN_PARENTS = {
    "cut": "videoedit|workspace",
    "trim_input": "videoedit|cut",
    "split": "videoedit|cut",
    "split_input": "videoedit|split",
    "join": "videoedit|workspace",
    "concat_input": "videoedit|join",
    "reorder_input": "videoedit|join",
    "frame": "videoedit|workspace",
    "transform": "videoedit|workspace",
    "rotation_value": "videoedit|transform",
    "audio": "videoedit|workspace",
    "audio_input": "videoedit|audio",
    "color": "videoedit|workspace",
    "overlay": "videoedit|workspace",
    "text_input": "videoedit|overlay",
    "logo_input": "videoedit|overlay",
    "srt_input": "videoedit|overlay",
    "effects": "videoedit|workspace",
    "effect_detail": "videoedit|effects",
    "source_info": "videoedit|workspace",
    "review": "videoedit|workspace",
    "confirmation": "videoedit|review",
}

_SCREEN_CALLBACKS = {
    "workspace": "videoedit|workspace",
    "cut": "videoedit|cut",
    "split": "videoedit|split",
    "join": "videoedit|join",
    "frame": "videoedit|frame",
    "transform": "videoedit|transform",
    "audio": "videoedit|audio",
    "color": "videoedit|color",
    "overlay": "videoedit|overlay",
    "effects": "videoedit|effects",
    "source_info": "videoedit|source_info",
    "review": "videoedit|review",
}

_ALLOWED_PARENT_CALLBACKS = frozenset(
    {
        "videoedit|hub",
        *_LANE_CALLBACKS.values(),
        *_SCREEN_CALLBACKS.values(),
        *_SCREEN_PARENTS.values(),
        "videoedit|options|manual",
        "videoedit|options|split",
    }
)

_COMPATIBILITY_ACTIONS = {
    "manual_info": "manual",
    "split_info": "split_from_manual",
    "ai_info": "ai",
    "audio": "manual_audio",
    "audio_upload": "manual",
    "timeline": "manual_join",
    "effects": "manual_effects",
    "plan": "review",
    "split": "split_from_manual",
    "reset_manual": "manual",
    "cut": "manual_cut",
    "join": "manual_join",
    "resize": "aspect",
    "crop": "aspect",
    "ratio": "aspect",
    "method": "aspect",
    "vertical": "aspect",
    "compress": "resolution",
    "subtitle": "srt",
    "preset": "color_preset",
    "text": "text_overlay",
    "sharpen": "restore",
}

_REQUESTED_GROUPS = {
    "manual_info": "manual",
    "split_info": "cut",
    "ai_info": "assistant",
    "audio": "audio",
    "audio_upload": "audio",
    "timeline": "join",
    "effects": "effects",
    "plan": "review",
    "split": "cut",
    "reset_manual": "manual",
    "cut": "cut",
    "resize": "frame",
    "crop": "frame",
    "ratio": "frame",
    "method": "frame",
    "vertical": "frame",
    "aspect": "frame",
    "compress": "resolution",
    "resolution": "resolution",
    "subtitle": "overlay",
    "srt": "overlay",
    "color": "color",
    "preset": "color",
    "color_preset": "color",
    "brightness": "color",
    "text": "overlay",
    "text_overlay": "overlay",
    "logo": "overlay",
    "sharpen": "quality",
    "manual_cut": "cut",
    "join": "join",
    "manual_join": "join",
    "manual_audio": "audio",
    "manual_effects": "effects",
    "review": "review",
}


def normalize_edit_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in EDIT_MODES else ""


def lane_callback(edit_mode: Any) -> str:
    return _LANE_CALLBACKS.get(normalize_edit_mode(edit_mode), "videoedit|hub")


def safe_parent_callback(value: Any, *, root: bool = False) -> str:
    """Return only a same-product parent or an explicitly allowed root exit."""

    callback = str(value or "").strip()
    if callback in _ALLOWED_PARENT_CALLBACKS:
        return callback
    if root and callback in {"menu|main_video", "menu|main"}:
        return callback
    return "videoedit|hub"


def parent_callback(screen: Any, *, lane: Any = "") -> str:
    """Resolve the immediate parent for a canonical Video Edit screen."""

    key = str(screen or "").strip().lower()
    if key == "workspace":
        return lane_callback(lane)
    return _SCREEN_PARENTS.get(key, "videoedit|hub")


def parent_matrix() -> dict[str, str]:
    """Return a caller-owned copy so navigation constants cannot be mutated."""

    return dict(_SCREEN_PARENTS)


def screen_callback(screen: Any) -> str:
    """Return the canonical callback that re-renders an existing screen."""

    return _SCREEN_CALLBACKS.get(str(screen or "").strip().lower(), "videoedit|workspace")


def canonical_compatibility_action(value: Any) -> str:
    """Map an old callback action onto one live canonical Video Edit action."""

    action = str(value or "").strip().lower()
    return _COMPATIBILITY_ACTIONS.get(action, action)


def requested_group(value: Any) -> str:
    """Return the editor group to preserve while a compatibility upload waits."""

    action = str(value or "").strip().lower()
    return _REQUESTED_GROUPS.get(action, "")


def ready_screen(edit_mode: Any) -> str:
    return _READY_SCREENS.get(normalize_edit_mode(edit_mode), "")


def start_lane(edit_mode: Any) -> dict[str, Any]:
    """Return a fresh canonical state; this function has no external side effects."""
    mode = normalize_edit_mode(edit_mode)
    if not mode:
        raise ValueError("invalid_video_edit_mode")
    return {
        "step": "await_edit_video",
        "edit_mode": mode,
        "current_screen": _UPLOAD_SCREENS[mode],
        "return_to": "videoedit|hub",
        "awaiting_media": True,
        "source_file_id": None,
        "last_media_message_id": 0,
        "intake_in_progress": False,
        "probe_count": 0,
    }


def is_active_intake(state: Mapping[str, Any] | None) -> bool:
    current = dict(state or {})
    return bool(
        normalize_edit_mode(current.get("edit_mode"))
        and current.get("step") == "await_edit_video"
        and current.get("awaiting_media") is True
        and not current.get("source_file_id")
    )


def is_duplicate_message(state: Mapping[str, Any] | None, message_id: Any) -> bool:
    try:
        candidate = int(message_id or 0)
        previous = int((state or {}).get("last_media_message_id") or 0)
    except (TypeError, ValueError):
        return False
    return bool(candidate > 0 and candidate == previous)


def claim_message(state: Mapping[str, Any] | None, message_id: Any) -> dict[str, Any]:
    """Atomically claim one Telegram message in the caller's synchronous state store."""
    current = dict(state or {})
    if not is_active_intake(current):
        return {"accepted": False, "duplicate": False, "state": current, "reason": "inactive_edit_intake"}
    if is_duplicate_message(current, message_id):
        return {"accepted": False, "duplicate": True, "state": current, "reason": "duplicate_message"}
    try:
        claimed_id = max(0, int(message_id or 0))
    except (TypeError, ValueError):
        claimed_id = 0
    current.update({"last_media_message_id": claimed_id, "intake_in_progress": True, "last_error": ""})
    return {"accepted": True, "duplicate": False, "state": current, "reason": ""}


def keep_waiting_after_invalid(state: Mapping[str, Any] | None, reason: Any) -> dict[str, Any]:
    current = dict(state or {})
    mode = normalize_edit_mode(current.get("edit_mode"))
    if not mode:
        raise ValueError("invalid_video_edit_mode")
    current.update({
        "step": "await_edit_video",
        "edit_mode": mode,
        "current_screen": _UPLOAD_SCREENS[mode],
        "return_to": "videoedit|hub",
        "awaiting_media": True,
        "source_file_id": None,
        "intake_in_progress": False,
        "last_error": str(reason or "invalid_video")[:180],
    })
    return current


def complete_intake(
    state: Mapping[str, Any] | None,
    source: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    current = dict(state or {})
    mode = normalize_edit_mode(current.get("edit_mode"))
    source_file_id = str((source or {}).get("source_file_id") or "").strip()
    if not mode or not source_file_id:
        raise ValueError("invalid_video_edit_completion")
    current.update(dict(source or {}))
    current.update({
        "step": _READY_SCREENS[mode],
        "edit_mode": mode,
        "current_screen": _READY_SCREENS[mode],
        "return_to": "videoedit|hub",
        "awaiting_media": False,
        "intake_in_progress": False,
        "source_file_id": source_file_id,
        "source_metadata": dict(metadata or {}),
        "inspection_complete": True,
        "probe_count": int(current.get("probe_count") or 0) + 1,
        "last_error": "",
    })
    return current


def back_target(edit_mode: Any, *, child: bool = False) -> str:
    """Child screens return to their lane; each lane returns to the edit hub."""
    mode = normalize_edit_mode(edit_mode)
    return lane_callback(mode) if child and mode else "videoedit|hub"
