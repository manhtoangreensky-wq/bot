from __future__ import annotations

import hashlib
from typing import Any

from services import frame_video_runtime


FRAME_VIDEO_ROUTE_MATRIX = {
    "start": {"owner": "handle_frame_video_callback", "screen": "image_count", "back": "hub"},
    "source": {"owner": "handle_frame_video_callback", "screen": "image_count", "back": "hub"},
    "ai_first": {"owner": "handle_frame_video_callback", "screen": "source_next", "back": "ratio_first"},
    "how": {"owner": "handle_frame_video_callback", "screen": "how", "back": "hub"},
    "image_count": {"owner": "handle_frame_video_callback", "screen": "ratio_first", "back": "image_count_menu"},
    "image_count_menu": {"owner": "handle_frame_video_callback", "screen": "image_count", "back": "hub"},
    "image_count_custom": {"owner": "handle_frame_video_callback", "screen": "image_count_input", "back": "image_count_menu"},
    "ratio_first_menu": {"owner": "handle_frame_video_callback", "screen": "ratio_first", "back": "image_count_menu"},
    "ratio_first_set": {"owner": "handle_frame_video_callback", "screen": "source_next", "back": "image_count_menu"},
    "ratio_first_recommend": {"owner": "handle_frame_video_callback", "screen": "source_next", "back": "image_count_menu"},
    "ratio_first_custom": {"owner": "handle_frame_video_callback", "screen": "ratio_first_input", "back": "ratio_first"},
    "done": {"owner": "handle_frame_video_canonical_callback", "screen": "images", "back": "collect"},
    "ai_stitch_generated": {
        "owner": "handle_frame_video_canonical_callback",
        "screen": "images",
        "back": "collect",
    },
    "assets_done": {"owner": "handle_frame_video_canonical_callback", "screen": "duration", "back": "images"},
    "panel": {"owner": "handle_frame_video_canonical_callback", "screen": "panel", "back": "hub"},
    "upload": {"owner": "handle_frame_video_canonical_callback", "screen": "collect", "back": "ratio_first"},
    "images": {"owner": "handle_frame_video_canonical_callback", "screen": "images", "back": "collect"},
    "sort": {"owner": "handle_frame_video_canonical_callback", "screen": "images", "back": "collect"},
    "image_select": {"owner": "handle_frame_video_canonical_callback", "screen": "images", "back": "collect"},
    "image_action": {"owner": "handle_frame_video_canonical_callback", "screen": "images", "back": "collect"},
    "image_caption": {
        "owner": "handle_frame_video_canonical_callback",
        "screen": "images",
        "back": "images",
        "mutation": "read_only_redirect",
    },
    "image_receipt": {
        "owner": "handle_frame_video_canonical_callback",
        "screen": "images",
        "back": "images",
        "mutation": "read_only_redirect",
    },
    "image_regenerate": {"owner": "handle_img2vid_lock1_callback", "screen": "image_regenerate_invoice", "back": "images"},
    "image_regenerate_confirm": {
        "owner": "handle_img2vid_lock1_callback",
        "screen": "image_regenerate_delivery",
        "back": "image_regenerate_invoice",
        "side_effect": "explicit_image_regenerate_confirm_only",
    },
    "ai_prompt": {"owner": "handle_img2vid_lock1_callback", "screen": "ai_prompt_input", "back": "ai_prepared"},
    "ai_suggest": {"owner": "handle_img2vid_lock1_callback", "screen": "ai_suggestions", "back": "ai_first"},
    "ai_refresh": {"owner": "handle_img2vid_lock1_callback", "screen": "ai_suggestions", "back": "ai_first"},
    "ai_pick": {"owner": "handle_img2vid_lock1_callback", "screen": "ai_prepared", "back": "ai_suggestions"},
    "ai_prepared": {"owner": "handle_img2vid_lock1_callback", "screen": "ai_prepared", "back": "ai_first"},
    "ai_prompt_set": {"owner": "handle_img2vid_lock1_callback", "screen": "ai_prompt_set", "back": "ai_prepared"},
    "ai_prompt_image": {"owner": "handle_img2vid_lock1_callback", "screen": "ai_prompt_image", "back": "ai_prompt_set"},
    "ai_prompt_image_edit": {"owner": "handle_img2vid_lock1_callback", "screen": "ai_prompt_image_input", "back": "ai_prompt_image"},
    "ai_prompt_image_restore": {"owner": "handle_img2vid_lock1_callback", "screen": "ai_prompt_image", "back": "ai_prompt_set"},
    "ai_prompt_regenerate": {"owner": "handle_img2vid_lock1_callback", "screen": "ai_prepared", "back": "ai_prepared"},
    "ai_count_menu": {"owner": "handle_img2vid_lock1_callback", "screen": "ai_count", "back": "ai_prepared"},
    "ai_count": {"owner": "handle_img2vid_lock1_callback", "screen": "ai_first", "back": "ai_count"},
    "ai_count_custom": {"owner": "handle_img2vid_lock1_callback", "screen": "ai_count_input", "back": "ai_count"},
    "ai_tier_menu": {"owner": "handle_img2vid_lock1_callback", "screen": "ai_tier", "back": "ai_prepared"},
    "ai_tier": {"owner": "handle_img2vid_lock1_callback", "screen": "ai_invoice", "back": "ai_tier"},
    "ai_generate_confirm": {
        "owner": "handle_img2vid_lock1_callback",
        "screen": "ai_image_delivery",
        "back": "ai_invoice",
        "side_effect": "explicit_image_confirm_only",
    },
    "image_duration": {
        "owner": "handle_frame_video_canonical_callback",
        "screen": "images",
        "back": "images",
        "mutation": "read_only_redirect",
    },
    "duration_set": {"owner": "handle_frame_video_canonical_callback", "screen": "duration", "back": "duration"},
    "duration_custom": {"owner": "handle_frame_video_canonical_callback", "screen": "duration_input", "back": "duration"},
    "duration_menu": {"owner": "handle_frame_video_canonical_callback", "screen": "duration", "back": "images"},
    "duration_done": {"owner": "handle_frame_video_canonical_callback", "screen": "transition", "back": "duration"},
    "ratio_menu": {"owner": "handle_frame_video_canonical_callback", "screen": "ratio", "back": "panel"},
    "ratio_set": {"owner": "handle_frame_video_canonical_callback", "screen": "panel", "back": "ratio"},
    "ratio_custom": {"owner": "handle_frame_video_canonical_callback", "screen": "ratio_input", "back": "ratio"},
    "fit_menu": {"owner": "handle_frame_video_canonical_callback", "screen": "fit", "back": "ratio"},
    "fit_set": {"owner": "handle_frame_video_canonical_callback", "screen": "panel", "back": "fit"},
    "transition_menu": {"owner": "handle_frame_video_canonical_callback", "screen": "transition", "back": "duration"},
    "transition_set": {"owner": "handle_frame_video_canonical_callback", "screen": "motion", "back": "transition"},
    "transition_time": {"owner": "handle_frame_video_canonical_callback", "screen": "transition_input", "back": "transition"},
    "motion_menu": {"owner": "handle_frame_video_canonical_callback", "screen": "motion", "back": "transition"},
    "motion_set": {"owner": "handle_frame_video_canonical_callback", "screen": "addons", "back": "motion"},
    "music_menu": {"owner": "handle_frame_video_canonical_callback", "screen": "music", "back": "panel"},
    "music_upload": {"owner": "handle_frame_video_canonical_callback", "screen": "music_input", "back": "music"},
    "music_off": {"owner": "handle_frame_video_canonical_callback", "screen": "music", "back": "music"},
    "volume_menu": {"owner": "handle_frame_video_canonical_callback", "screen": "volume", "back": "music_or_addons"},
    "volume": {"owner": "handle_frame_video_canonical_callback", "screen": "music_or_addons", "back": "volume"},
    "volume_custom": {"owner": "handle_frame_video_canonical_callback", "screen": "volume_input", "back": "music_or_addons"},
    "audio_fade": {"owner": "handle_frame_video_canonical_callback", "screen": "music_or_addons", "back": "music_or_addons"},
    "addons": {"owner": "handle_frame_video_canonical_callback", "screen": "addons", "back": "motion"},
    "audio_menu": {"owner": "handle_frame_video_canonical_callback", "screen": "audio", "back": "addons"},
    "addons_done": {"owner": "handle_frame_video_canonical_callback", "screen": "review", "back": "addons"},
    "addons_skip": {"owner": "handle_frame_video_canonical_callback", "screen": "review", "back": "addons"},
    "addon": {"owner": "handle_frame_video_canonical_callback", "screen": "addon_input", "back": "addons"},
    "position_menu": {"owner": "handle_frame_video_canonical_callback", "screen": "position", "back": "addons"},
    "position_set": {"owner": "handle_frame_video_canonical_callback", "screen": "addons_or_text_editor", "back": "position"},
    "text_list": {"owner": "handle_frame_video_canonical_callback", "screen": "text_list", "back": "addons"},
    "text_select": {"owner": "handle_frame_video_canonical_callback", "screen": "text_editor", "back": "text_list"},
    "text_editor": {"owner": "handle_frame_video_canonical_callback", "screen": "text_editor", "back": "text_list"},
    "text_action": {"owner": "handle_frame_video_canonical_callback", "screen": "text_editor_or_list", "back": "text_editor"},
    "text_edit": {"owner": "handle_frame_video_canonical_callback", "screen": "text_input", "back": "text_editor"},
    "text_scope_menu": {"owner": "handle_frame_video_canonical_callback", "screen": "text_scope", "back": "text_editor"},
    "text_scope_set": {"owner": "handle_frame_video_canonical_callback", "screen": "text_editor", "back": "text_scope"},
    "text_timing": {"owner": "handle_frame_video_canonical_callback", "screen": "text_input", "back": "text_editor"},
    "text_animation_menu": {"owner": "handle_frame_video_canonical_callback", "screen": "text_animation", "back": "text_editor"},
    "text_animation_set": {"owner": "handle_frame_video_canonical_callback", "screen": "text_editor", "back": "text_animation"},
    "text_style_menu": {"owner": "handle_frame_video_canonical_callback", "screen": "text_style", "back": "text_editor"},
    "text_style_set": {"owner": "handle_frame_video_canonical_callback", "screen": "text_editor", "back": "text_style"},
    "quality_menu": {"owner": "handle_frame_video_canonical_callback", "screen": "quality", "back": "review"},
    "quality_set": {"owner": "handle_frame_video_canonical_callback", "screen": "quality", "back": "quality"},
    "quality_info": {"owner": "handle_frame_video_canonical_callback", "screen": "quality", "back": "quality"},
    "review": {"owner": "handle_frame_video_canonical_callback", "screen": "review", "back": "addons"},
    "continue": {"owner": "handle_frame_video_canonical_callback", "screen": "invoice", "back": "quality"},
    "status": {"owner": "handle_frame_video_callback", "screen": "status", "back": "invoice_or_review"},
    "status_back": {"owner": "handle_frame_video_callback", "screen": "invoice_or_review", "back": "status"},
    "confirm": {
        "owner": "handle_frame_video_final_confirm",
        "screen": "rendering",
        "back": "invoice",
        "side_effect": "explicit_final_confirm_only",
    },
    "media_image": {"owner": "handle_frame_video_pending_media", "screen": "collect_or_images", "back": "collect"},
    "media_audio": {"owner": "handle_frame_video_pending_media", "screen": "music_or_addons", "back": "addons"},
}

FRAME_VIDEO_LEGACY_ROUTE_MATRIX = {
    action: {
        "owner": "handle_frame_video_canonical_callback",
        "screen": "panel",
        "back": "hub",
        "mutation": "read_only_redirect",
    }
    for action in {
        "planning_refresh",
        "planning_continue",
        "ratio",
        "duration",
        "effect",
        "music",
        "back",
        "img2vid_seconds_menu",
        "img2vid_seconds",
        "img2vid_seconds_custom",
        "img2vid_confirm",
        "preview",
        "preview_check",
        "mode_frame",
        "mode_audio",
        "mode_ai",
        "save",
        "text_delete_last",
    }
}


FRAME_VIDEO_DEFAULTS: dict[str, Any] = {
    "commercial_flow_version": "framevideo2",
    "step": "collect",
    "image_count": 0,
    "source": "existing_images",
    "image_sources": "uploaded",
    "mode": "existing_images",
    "img2vid_lock1": True,
    "seconds_per_image": 3.0,
    "image_durations": {},
    "duration_confirmed": False,
    "ratio": "9x16",
    "fit_mode": "contain",
    "background_color": "#111111",
    "transition": "fade",
    "effect": "fade",
    "transition_seconds": 0.35,
    "motion": "none",
    "quality": "balanced",
    "ai_image_count": 2,
    "ai_image_prompts": [],
    "selected_ai_prompt_index": 1,
    "ai_image_tier": "",
    "ai_image_model": "",
    "image_generation_price": 0,
    "image_generation_unit_price": 0,
    "image_generation_charged_amount": 0,
    "image_generation_paid": False,
    "image_batch_status": "",
    "image_batch_charge_recorded": False,
    "generated_image_receipts": [],
    "generated_image_job_ids": [],
    "image_regeneration_status": "",
    "image_regeneration_target_id": "",
    "image_regeneration_request_id": "",
    "image_regeneration_last_completed_id": "",
    "image_regeneration_pending": {},
    "image_regeneration_charge_count": 0,
    "music_enabled": False,
    "music_file_id": "",
    "music_volume_percent": 35,
    "music_fade_seconds": 0.35,
    "voice_enabled": False,
    "voice_file_id": "",
    "voice_volume_percent": 100,
    "voice_fade_seconds": 0.25,
    "subtitle_enabled": False,
    "subtitle_text": "",
    "subtitle_position": "bottom_center",
    "logo_enabled": False,
    "logo_file_id": "",
    "logo_position": "top_right",
    "logo_width_ratio": 0.12,
    "watermark_enabled": False,
    "watermark_text": "",
    "watermark_position": "top_right",
    "text_overlays": [],
    "selected_image_id": "",
    "pending_input": "",
    "processed_media_message_ids": [],
}


def _stable_text_id(content: str, ordinal: int) -> str:
    digest = hashlib.sha256(f"{content}:{ordinal}".encode("utf-8")).hexdigest()[:12]
    return f"fvtxt_{digest}"


def _safe_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(fallback)


def normalize_text_overlays(state: dict[str, Any]) -> list[dict[str, Any]]:
    total = max(0.1, frame_video_runtime.expected_duration_seconds(state))
    normalized: list[dict[str, Any]] = []
    used: set[str] = set()
    for ordinal, raw in enumerate(list(state.get("text_overlays") or [])[:30], start=1):
        item = dict(raw or {})
        content = " ".join(str(item.get("content") or "").split())[:500]
        if not content:
            continue
        text_id = str(item.get("text_id") or _stable_text_id(content, ordinal))
        if text_id in used:
            text_id = _stable_text_id(content, ordinal + len(normalized) + 100)
        used.add(text_id)
        start = max(0.0, min(total - 0.1, _safe_float(item.get("start_seconds"), 0.0)))
        end = max(start + 0.1, min(total, _safe_float(item.get("end_seconds"), total)))
        normalized.append({
            **item,
            "text_id": text_id,
            "content": content,
            "image_id": str(item.get("image_id") or ""),
            "start_seconds": round(start, 3),
            "end_seconds": round(end, 3),
            "position": str(item.get("position") or "top_center"),
            "animation": str(item.get("animation") or "fade"),
            "style": str(item.get("style") or "readable"),
        })
    return normalized


def normalize_state(state: dict[str, Any] | None = None) -> dict[str, Any]:
    clean = dict(FRAME_VIDEO_DEFAULTS)
    clean.update(dict(state or {}))
    requested_count = _safe_int(clean.get("image_count"), 0)
    clean["image_count"] = (
        max(frame_video_runtime.FRAME_VIDEO_MIN_IMAGES, min(frame_video_runtime.FRAME_VIDEO_MAX_IMAGES, requested_count))
        if requested_count >= frame_video_runtime.FRAME_VIDEO_MIN_IMAGES
        else 0
    )
    requested_ai_count = _safe_int(clean.get("ai_image_count"), frame_video_runtime.FRAME_VIDEO_MIN_IMAGES)
    clean["ai_image_count"] = max(
        frame_video_runtime.FRAME_VIDEO_MIN_IMAGES,
        min(frame_video_runtime.FRAME_VIDEO_MAX_IMAGES, requested_ai_count),
    )
    clean["photos"] = frame_video_runtime.canonical_image_manifest(clean.get("photos") or [])
    valid_ids = {row["image_id"] for row in clean["photos"]}
    if clean.get("selected_image_id") not in valid_ids:
        clean["selected_image_id"] = clean["photos"][0]["image_id"] if clean["photos"] else ""
    clean["processed_media_message_ids"] = [
        str(value)
        for value in list(clean.get("processed_media_message_ids") or [])[-100:]
        if str(value)
    ]
    clean["generated_image_receipts"] = [
        dict(value)
        for value in list(clean.get("generated_image_receipts") or [])[-frame_video_runtime.FRAME_VIDEO_MAX_IMAGES:]
        if isinstance(value, dict)
    ]
    clean["generated_image_job_ids"] = [
        int(value)
        for value in list(clean.get("generated_image_job_ids") or [])[-frame_video_runtime.FRAME_VIDEO_MAX_IMAGES:]
        if str(value).isdigit() and int(value) > 0
    ]
    normalized_prompts: list[dict[str, Any]] = []
    for ordinal, raw in enumerate(list(clean.get("ai_image_prompts") or [])[:frame_video_runtime.FRAME_VIDEO_MAX_IMAGES], start=1):
        item = dict(raw) if isinstance(raw, dict) else {"prompt": str(raw or "")}
        prompt = " ".join(str(item.get("prompt") or "").split())[:2000]
        if not prompt:
            continue
        normalized_prompts.append(
            {
                "index": ordinal,
                "prompt": prompt,
                "previous_prompt": " ".join(str(item.get("previous_prompt") or "").split())[:2000],
            }
        )
    clean["ai_image_prompts"] = normalized_prompts
    clean["duration_confirmed"] = bool(clean.get("duration_confirmed"))
    prompt_count = len(normalized_prompts)
    selected_prompt_index = _safe_int(clean.get("selected_ai_prompt_index"), 1)
    clean["selected_ai_prompt_index"] = max(1, min(selected_prompt_index, prompt_count or 1))
    clean["text_overlays"] = normalize_text_overlays(clean)
    text_ids = {row["text_id"] for row in clean["text_overlays"] if str(row.get("kind") or "") != "subtitle"}
    if clean.get("selected_text_id") not in text_ids:
        clean["selected_text_id"] = next(
            (row["text_id"] for row in clean["text_overlays"] if str(row.get("kind") or "") != "subtitle"),
            "",
        )
    return clean


def selected_text(state: dict[str, Any]) -> dict[str, Any]:
    clean = normalize_state(state)
    selected = str(clean.get("selected_text_id") or "")
    return next(
        (row for row in clean["text_overlays"] if row["text_id"] == selected and str(row.get("kind") or "") != "subtitle"),
        {},
    )


def add_text_overlay(state: dict[str, Any], content: str) -> dict[str, Any]:
    clean = normalize_state(state)
    overlays = list(clean.get("text_overlays") or [])
    total = max(0.1, frame_video_runtime.expected_duration_seconds(clean))
    row = {
        "kind": "animated_text",
        "text_id": _stable_text_id(content, len(overlays) + 1),
        "content": " ".join(str(content or "").split())[:500],
        "image_id": "",
        "position": "top_center",
        "start_seconds": 0.0,
        "end_seconds": total,
        "animation": "fade",
        "style": "readable",
        "font_color": "white",
        "box_color": "black@0.28",
    }
    overlays.append(row)
    clean["text_overlays"] = overlays
    clean["selected_text_id"] = row["text_id"]
    return normalize_state(clean)


def apply_text_action(state: dict[str, Any], action: str, text_id: str = "") -> dict[str, Any]:
    clean = normalize_state(state)
    target = str(text_id or clean.get("selected_text_id") or "")
    subtitle_rows = [row for row in clean.get("text_overlays") or [] if str(row.get("kind") or "") == "subtitle"]
    overlays = [row for row in clean.get("text_overlays") or [] if str(row.get("kind") or "") != "subtitle"]
    index = next((idx for idx, row in enumerate(overlays) if row.get("text_id") == target), -1)
    if action == "select":
        if index >= 0:
            clean["selected_text_id"] = target
        return clean
    if index < 0:
        raise ValueError("text_not_found")
    if action == "delete":
        overlays.pop(index)
    elif action in {"up", "down"}:
        other = index - 1 if action == "up" else index + 1
        if 0 <= other < len(overlays):
            overlays[index], overlays[other] = overlays[other], overlays[index]
    clean["text_overlays"] = overlays + subtitle_rows
    clean["selected_text_id"] = target if any(row.get("text_id") == target for row in overlays) else (overlays[0]["text_id"] if overlays else "")
    return normalize_state(clean)


def update_selected_text(state: dict[str, Any], **changes: Any) -> dict[str, Any]:
    clean = normalize_state(state)
    target = str(clean.get("selected_text_id") or "")
    overlays = []
    found = False
    for row in clean.get("text_overlays") or []:
        if row.get("text_id") == target:
            row = {**row, **changes}
            found = True
        overlays.append(row)
    if not found:
        raise ValueError("text_not_found")
    clean["text_overlays"] = overlays
    return normalize_state(clean)


def image_time_range(state: dict[str, Any], image_id: str) -> tuple[float, float]:
    clean = normalize_state(state)
    durations = frame_video_runtime.image_duration_map(clean)
    overlap = frame_video_runtime.transition_overlap_seconds(clean)
    cursor = 0.0
    for row in clean.get("photos") or []:
        duration = float(durations.get(row["image_id"]) or clean.get("seconds_per_image") or 3.0)
        start, end = cursor, cursor + duration
        if row["image_id"] == image_id:
            return round(start, 3), round(end, 3)
        cursor = max(0.0, end - overlap)
    total = frame_video_runtime.expected_duration_seconds(clean)
    return 0.0, total


def selected_image(state: dict[str, Any]) -> dict[str, Any]:
    clean = normalize_state(state)
    selected = str(clean.get("selected_image_id") or "")
    return next((row for row in clean["photos"] if row["image_id"] == selected), {})


def update_selected_image(state: dict[str, Any], **changes: Any) -> dict[str, Any]:
    clean = normalize_state(state)
    selected = str(clean.get("selected_image_id") or "")
    if not selected:
        raise ValueError("image_not_selected")
    found = False
    updated: list[dict[str, Any]] = []
    for row in clean["photos"]:
        item = dict(row)
        if item["image_id"] == selected:
            found = True
            for key, value in changes.items():
                if key == "caption":
                    item[key] = " ".join(str(value or "").split())[:1000]
        updated.append(item)
    if not found:
        raise ValueError("image_not_found")
    clean["photos"] = frame_video_runtime.canonical_image_manifest(updated)
    return normalize_state(clean)


def set_ai_image_prompts(state: dict[str, Any], prompts: list[str]) -> dict[str, Any]:
    clean = normalize_state(state)
    expected = _safe_int(clean.get("image_count") or clean.get("ai_image_count"), 0)
    expected = max(
        frame_video_runtime.FRAME_VIDEO_MIN_IMAGES,
        min(frame_video_runtime.FRAME_VIDEO_MAX_IMAGES, expected),
    )
    values = [" ".join(str(value or "").split())[:2000] for value in list(prompts or [])]
    if len(values) != expected or any(not value for value in values):
        raise ValueError("ai_image_prompt_count_mismatch")
    clean["ai_image_prompts"] = [
        {"index": index, "prompt": value, "previous_prompt": ""}
        for index, value in enumerate(values, start=1)
    ]
    clean["selected_ai_prompt_index"] = 1
    return normalize_state(clean)


def ai_image_prompt_values(state: dict[str, Any]) -> list[str]:
    clean = normalize_state(state)
    expected = _safe_int(clean.get("image_count") or clean.get("ai_image_count"), 0)
    values = [str(row.get("prompt") or "") for row in clean.get("ai_image_prompts") or []]
    return (
        values
        if expected >= frame_video_runtime.FRAME_VIDEO_MIN_IMAGES and len(values) == expected and all(values)
        else []
    )


def selected_ai_image_prompt(state: dict[str, Any]) -> dict[str, Any]:
    clean = normalize_state(state)
    selected_index = _safe_int(clean.get("selected_ai_prompt_index"), 1)
    return next(
        (dict(row) for row in clean.get("ai_image_prompts") or [] if _safe_int(row.get("index"), 0) == selected_index),
        {},
    )


def update_ai_image_prompt(state: dict[str, Any], index: int, prompt: str) -> dict[str, Any]:
    clean = normalize_state(state)
    target = _safe_int(index, 0)
    value = " ".join(str(prompt or "").split())[:2000]
    if target <= 0 or not value:
        raise ValueError("ai_image_prompt_invalid")
    found = False
    rows: list[dict[str, Any]] = []
    for raw in clean.get("ai_image_prompts") or []:
        row = dict(raw)
        if _safe_int(row.get("index"), 0) == target:
            found = True
            previous = str(row.get("prompt") or "")
            row.update({"prompt": value, "previous_prompt": previous})
        rows.append(row)
    if not found:
        raise ValueError("ai_image_prompt_not_found")
    clean["ai_image_prompts"] = rows
    clean["selected_ai_prompt_index"] = target
    return normalize_state(clean)


def restore_ai_image_prompt(state: dict[str, Any], index: int) -> dict[str, Any]:
    clean = normalize_state(state)
    target = _safe_int(index, 0)
    found = False
    rows: list[dict[str, Any]] = []
    for raw in clean.get("ai_image_prompts") or []:
        row = dict(raw)
        if _safe_int(row.get("index"), 0) == target:
            previous = str(row.get("previous_prompt") or "").strip()
            if not previous:
                raise ValueError("ai_image_prompt_restore_unavailable")
            found = True
            current = str(row.get("prompt") or "")
            row.update({"prompt": previous, "previous_prompt": current})
        rows.append(row)
    if not found:
        raise ValueError("ai_image_prompt_not_found")
    clean["ai_image_prompts"] = rows
    clean["selected_ai_prompt_index"] = target
    return normalize_state(clean)


def mark_media_message_processed(state: dict[str, Any], message_id: Any) -> tuple[dict[str, Any], bool]:
    clean = normalize_state(state)
    token = str(message_id or "")
    if token and token in clean["processed_media_message_ids"]:
        return clean, False
    if token:
        clean["processed_media_message_ids"] = (clean["processed_media_message_ids"] + [token])[-100:]
    return clean, True


def add_photo(state: dict[str, Any], photo: dict[str, Any]) -> dict[str, Any]:
    clean = normalize_state(state)
    clean["photos"] = frame_video_runtime.manifest_add(clean["photos"], photo)
    clean["selected_image_id"] = clean["photos"][-1]["image_id"] if clean["photos"] else ""
    clean["duration_confirmed"] = False
    return clean


def apply_image_action(state: dict[str, Any], action: str, image_id: str = "") -> dict[str, Any]:
    clean = normalize_state(state)
    target = str(image_id or clean.get("selected_image_id") or "")
    if action == "select":
        if target in {row["image_id"] for row in clean["photos"]}:
            clean["selected_image_id"] = target
        return clean
    if action == "delete":
        clean["photos"] = frame_video_runtime.manifest_delete(clean["photos"], target)
        clean["duration_confirmed"] = False
    elif action == "duplicate":
        clean["photos"] = frame_video_runtime.manifest_duplicate(clean["photos"], target)
        clean["duration_confirmed"] = False
    elif action in {"up", "down"}:
        clean["photos"] = frame_video_runtime.manifest_move(clean["photos"], target, action)
    elif action == "cover":
        clean["photos"] = frame_video_runtime.manifest_set_cover(clean["photos"], target)
    return normalize_state(clean)


def set_global_duration(state: dict[str, Any], seconds: float) -> dict[str, Any]:
    clean = normalize_state(state)
    value = max(0.5, min(30.0, float(seconds)))
    clean["seconds_per_image"] = value
    clean["image_durations"] = {}
    clean["duration"] = "custom"
    clean["duration_confirmed"] = True
    return clean


def set_selected_duration(state: dict[str, Any], seconds: float) -> dict[str, Any]:
    clean = normalize_state(state)
    selected = str(clean.get("selected_image_id") or "")
    if selected:
        durations = dict(clean.get("image_durations") or {})
        durations[selected] = max(0.5, min(30.0, float(seconds)))
        clean["image_durations"] = durations
        clean["duration_confirmed"] = True
    return clean


def set_transition(state: dict[str, Any], transition: str) -> dict[str, Any]:
    clean = normalize_state(state)
    aliases = {"cut": "none", "natural": "none"}
    token = aliases.get(str(transition or ""), str(transition or ""))
    if token not in frame_video_runtime.TRANSITIONS:
        token = "fade"
    clean["transition"] = token
    clean["effect"] = token
    return clean


def set_volume(state: dict[str, Any], kind: str, percent: int) -> dict[str, Any]:
    clean = normalize_state(state)
    if kind not in {"music", "voice"}:
        return clean
    clean[f"{kind}_volume_percent"] = max(0, min(200, int(percent)))
    return clean


def sync_render_overlays(state: dict[str, Any]) -> dict[str, Any]:
    clean = normalize_state(state)
    overlays = [
        dict(row)
        for row in list(clean.get("text_overlays") or [])
        if str((row or {}).get("content") or "").strip() and str((row or {}).get("kind") or "") != "subtitle"
    ]
    if clean.get("subtitle_enabled") and str(clean.get("subtitle_text") or "").strip():
        overlays.append(
            {
                "kind": "subtitle",
                "content": str(clean.get("subtitle_text") or "")[:500],
                "position": "bottom_center",
                "start_seconds": 0,
                "end_seconds": frame_video_runtime.expected_duration_seconds(clean),
                "animation": "fade",
            }
        )
    clean["text_overlays"] = overlays
    if not clean.get("watermark_enabled"):
        clean["watermark_text"] = ""
    if not clean.get("logo_enabled"):
        clean["logo_file_id"] = ""
    if not clean.get("music_enabled"):
        clean["music_file_id"] = ""
    if not clean.get("voice_enabled"):
        clean["voice_file_id"] = ""
    return normalize_state(clean)


def plan_summary(state: dict[str, Any]) -> dict[str, Any]:
    clean = sync_render_overlays(state)
    plan = frame_video_runtime.validate_plan(clean)
    return {
        "state": clean,
        "ok": bool(plan.get("ok")),
        "errors": list(plan.get("errors") or []),
        "image_count": len(clean["photos"]),
        "duration_seconds": frame_video_runtime.expected_duration_seconds(clean),
        "ratio": (
            f"{int(clean.get('custom_width') or 0)}×{int(clean.get('custom_height') or 0)}"
            if clean.get("ratio") == "custom"
            else str(clean.get("ratio") or "9x16").replace("x", ":")
        ),
        "fit_mode": str(clean.get("fit_mode") or "contain"),
        "transition": str(clean.get("transition") or "fade"),
        "motion": str(clean.get("motion") or "none"),
        "quality": str(clean.get("quality") or "balanced"),
        "has_music": bool(clean.get("music_enabled") and clean.get("music_file_id")),
        "has_voice": bool(clean.get("voice_enabled") and clean.get("voice_file_id")),
        "has_logo": bool(clean.get("logo_enabled") and clean.get("logo_file_id")),
        "has_watermark": bool(clean.get("watermark_enabled") and clean.get("watermark_text")),
        "text_count": len(clean.get("text_overlays") or []),
    }
