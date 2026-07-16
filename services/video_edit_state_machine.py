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


def normalize_edit_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in EDIT_MODES else ""


def lane_callback(edit_mode: Any) -> str:
    return _LANE_CALLBACKS.get(normalize_edit_mode(edit_mode), "videoedit|hub")


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
