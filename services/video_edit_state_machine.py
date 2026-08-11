"""Canonical intake state for the three public Video Edit lanes."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from . import video_local_editing


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
    "brightness": "videoedit|color",
    "rotation_value": "videoedit|transform",
    "audio": "videoedit|workspace",
    "audio_input": "videoedit|audio",
    "color": "videoedit|workspace",
    "overlay": "videoedit|workspace",
    "text_input": "videoedit|overlay",
    "branding": "videoedit|workspace",
    "logo_input": "videoedit|branding",
    "logo_opacity_input": "videoedit|logo_options",
    "logo_options": "videoedit|branding",
    "watermark_input": "videoedit|branding",
    "watermark_opacity_input": "videoedit|watermark_options",
    "watermark_options": "videoedit|branding",
    "srt_input": "videoedit|overlay",
    "effects": "videoedit|workspace",
    "effect_detail": "videoedit|effects",
    "ai_source_summary": "videoedit|ai",
    "ai_suggestions": "videoedit|ai_source",
    "ai_settings": "videoedit|ai_suggestions",
    "ai_prompt": "videoedit|ai_settings",
    "quality_enhance": "videoedit|restore",
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
    "brightness": "videoedit|brightness",
    "audio": "videoedit|audio",
    "color": "videoedit|color",
    "overlay": "videoedit|overlay",
    "branding": "videoedit|branding",
    "logo_options": "videoedit|logo_options",
    "watermark_options": "videoedit|watermark_options",
    "effects": "videoedit|effects",
    "ai_source_summary": "videoedit|ai_source",
    "ai_suggestions": "videoedit|ai_suggestions",
    "ai_settings": "videoedit|ai_settings",
    "ai_prompt": "videoedit|ai_prompt",
    "quality_enhance": "videoedit|quality_source",
    "source_info": "videoedit|source_info",
    "review": "videoedit|review",
    "confirmation": "videoedit|confirmation",
}

_PENDING_RESUME_CALLBACKS = {
    "trim_edges": "videoedit|trim_edges",
    "trim_range": "videoedit|trim_range",
    "remove_middle": "videoedit|remove_middle",
    "split_fixed": "videoedit|split_fixed",
    "split_count": "videoedit|split_count",
    "split_custom": "videoedit|split_custom",
    "concat": "videoedit|concat",
    "concat_order": "videoedit|reorder",
    "text_overlay": "videoedit|text_overlay",
    "logo": "videoedit|logo",
    "logo_opacity": "videoedit|logo_opacity",
    "watermark_text": "videoedit|watermark_text",
    "watermark_opacity": "videoedit|watermark_opacity",
    "srt": "videoedit|srt",
    "rotation": "videoedit|rotation",
    "flip": "videoedit|flip",
}

_SCREEN_RESUME_CALLBACKS = {
    "choose_aspect": "videoedit|aspect",
    "choose_resolution": "videoedit|resolution",
    "choose_rotation": "videoedit|rotation",
    "choose_flip": "videoedit|flip",
    "choose_speed": "videoedit|speed",
    "choose_volume": "videoedit|volume",
    "choose_color_preset": "videoedit|color_preset",
    "rotation_value": "videoedit|transform",
}

_ALLOWED_PARENT_CALLBACKS = frozenset(
    {
        "videoedit|hub",
        *_LANE_CALLBACKS.values(),
        *_SCREEN_CALLBACKS.values(),
        *_SCREEN_PARENTS.values(),
        *_PENDING_RESUME_CALLBACKS.values(),
        *_SCREEN_RESUME_CALLBACKS.values(),
        "videoedit|options|manual",
        "videoedit|options|split",
        "videoedit|ai_source",
        "videoedit|quality_source",
    }
)

_COMPATIBILITY_ACTIONS = {
    "manual_info": "manual",
    "split_info": "split_from_manual",
    "ai_info": "ai",
    "audio": "manual_audio",
    "audio_upload": "audio_reupload",
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
    "logo": "branding",
    "watermark": "branding",
    "watermark_entry": "branding",
    "watermark_text": "branding",
    "sharpen": "quality",
    "manual_cut": "cut",
    "join": "join",
    "manual_join": "join",
    "manual_audio": "audio",
    "manual_effects": "effects",
    "review": "review",
}

_REQUESTED_GROUP_SCREENS = {
    "cut": "cut",
    "join": "join",
    "frame": "frame",
    "resolution": "resolution",
    "audio": "audio",
    "effects": "effects",
    "overlay": "overlay",
    "branding": "branding",
    "color": "color",
    "review": "review",
}

_REVIEW_BACK_CALLBACKS = {
    "brightness": "videoedit|brightness",
    "frame": "videoedit|frame",
    "transform": "videoedit|transform",
    "color": "videoedit|color",
    "cut": "videoedit|cut",
    "join": "videoedit|join",
    "audio": "videoedit|audio",
    "overlay": "videoedit|overlay",
    "branding": "videoedit|branding",
    "logo_options": "videoedit|logo_options",
    "watermark_options": "videoedit|watermark_options",
    "effects": "videoedit|effects",
    "split": "videoedit|split",
    "ai_prompt": "videoedit|ai_prompt",
    "ai_suggestions": "videoedit|ai_suggestions",
    "ai_settings": "videoedit|ai_settings",
    "ai_source_summary": "videoedit|ai_source",
    "quality_enhance": "videoedit|quality_source",
    "options": "videoedit|workspace",
    "workspace": "videoedit|workspace",
    # Compatibility for review states saved by the previous manual callbacks.
    "manual_cut": "videoedit|cut",
    "manual_join": "videoedit|join",
    "manual_audio": "videoedit|audio",
    "manual_effects": "videoedit|effects",
    "manual_rotate_flip": "videoedit|transform",
    "speed": "videoedit|transform",
}


def normalize_edit_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in EDIT_MODES else ""


def lane_callback(edit_mode: Any) -> str:
    return _LANE_CALLBACKS.get(normalize_edit_mode(edit_mode), "videoedit|hub")


def requested_group_screen(value: Any) -> str:
    """Return the exact post-upload screen for one legacy requested group."""

    return _REQUESTED_GROUP_SCREENS.get(str(value or "").strip().lower(), "")


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


def confirmation_token(edit_session_id: Any, review_revision: Any) -> str:
    """Return a short opaque token for one review revision.

    Telegram callback data must not carry the raw session identifier.  Binding
    the token to both values prevents an old confirmation button from
    submitting a later plan that happens to be in the same user state slot.
    """

    session = str(edit_session_id or "").strip()
    try:
        revision = int(review_revision or 0)
    except (TypeError, ValueError):
        revision = 0
    material = f"videoedit-confirm-v1:{session}:{revision}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:16]


def screen_callback(screen: Any) -> str:
    """Return the canonical callback that re-renders an existing screen."""

    return _SCREEN_CALLBACKS.get(str(screen or "").strip().lower(), "videoedit|workspace")


def review_back_callback(state: Mapping[str, Any] | None) -> str:
    """Return the exact canonical screen that opened a review."""

    return_to = str((state or {}).get("return_to") or "").strip().lower()
    if return_to.startswith("videoedit|"):
        return_to = return_to.split("|", 1)[1]
    return _REVIEW_BACK_CALLBACKS.get(return_to, "videoedit|workspace")


def resume_callback(screen: Any, pending_field: Any = "") -> str:
    """Return the exact callback that can reconstruct an interrupted input."""

    pending = str(pending_field or "").strip().lower()
    if pending in _PENDING_RESUME_CALLBACKS:
        return _PENDING_RESUME_CALLBACKS[pending]
    key = str(screen or "").strip().lower()
    return _SCREEN_RESUME_CALLBACKS.get(key, screen_callback(key))


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
        and current.get("intake_in_progress") is not True
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
    try:
        state_revision = max(0, int(current.get("state_revision") or 0))
    except (TypeError, ValueError, OverflowError):
        state_revision = 0
    try:
        revision = max(0, int(current.get("revision") or 0))
    except (TypeError, ValueError, OverflowError):
        revision = 0
    current.update(dict(source or {}))
    source_duration_ms = max(0, int((metadata or {}).get("duration_ms") or 0))
    manual_edit_plan = video_local_editing.default_manual_edit_plan("")
    manual_edit_plan["trim"] = {"start_ms": 0, "end_ms": source_duration_ms}
    current.update({
        "step": _READY_SCREENS[mode],
        "edit_mode": mode,
        "current_screen": _READY_SCREENS[mode],
        "return_to": "videoedit|hub",
        "awaiting_media": False,
        "intake_in_progress": False,
        "source_file_id": source_file_id,
        "source_video_id": source_file_id,
        "source_has_audio": bool((metadata or {}).get("has_audio")),
        "source_metadata": dict(metadata or {}),
        "manual_edit_plan": manual_edit_plan,
        "inspection_complete": True,
        "status": "source_ready",
        "state_revision": state_revision + 1,
        "revision": revision + 1,
        "probe_count": int(current.get("probe_count") or 0) + 1,
        "last_error": "",
    })
    return current


def back_target(edit_mode: Any, *, child: bool = False) -> str:
    """Child screens return to their lane; each lane returns to the edit hub."""
    mode = normalize_edit_mode(edit_mode)
    return lane_callback(mode) if child and mode else "videoedit|hub"
