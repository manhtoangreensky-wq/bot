"""Final video route and artifact validation for TOAN AAS product video.

This module is intentionally UI-free. It protects the locked Video flows from
being confused with renderer/provider state and prevents draft/placeholder
artifacts from being marked as final product videos.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


VIDEO_FINAL_STATES = {
    "draft_ready",
    "final_rendering",
    "final_delivered",
    "failed_no_charge",
    "failed_refunded",
    "needs_admin_review",
}
VIDEO_PRODUCT_ENGINE_ROUTES: dict[str, dict[str, Any]] = {
    "video_trend": {
        "adapter": "text_to_video_or_scene_engine",
        "input_requirements": ("selected_trend", "profile", "prompt_or_script"),
        "engine_family": "scene_video",
    },
    "video_ai_prompt": {
        "adapter": "text_to_video",
        "input_requirements": ("selected_prompt", "ratio", "duration", "style", "package"),
        "engine_family": "single_video",
    },
    "video_ai_image": {
        "adapter": "image_to_video",
        "input_requirements": ("source_image", "motion_prompt", "style", "duration"),
        "engine_family": "image_video",
    },
    "video_ai_video_reference": {
        "adapter": "video_to_video_or_clean_fail",
        "input_requirements": ("reference_video", "change_prompt"),
        "engine_family": "reference_video",
        "allow_clean_fail": True,
    },
    "script_to_video": {
        "adapter": "script_scene_engine",
        "input_requirements": ("selected_script", "scene_prompts"),
        "engine_family": "scene_video",
    },
    "image_to_video": {
        "adapter": "image_sequence_slideshow_or_i2v",
        "input_requirements": ("images_or_image_prompts", "order", "transition", "duration"),
        "engine_family": "image_sequence",
    },
    "self_shot_scene_change": {
        "adapter": "video_to_video_scene_change_or_clean_fail",
        "input_requirements": ("source_video", "subject_preservation", "scene_change_direction"),
        "engine_family": "reference_video",
        "allow_clean_fail": True,
    },
    "multi_scene_film": {
        "adapter": "multiscene_render_and_stitch",
        "input_requirements": ("story", "scene_plan", "scene_prompts", "style"),
        "engine_family": "multiscene",
    },
    "video_idea_to_product": {
        "adapter": "delegates_to_selected_product",
        "input_requirements": ("selected_idea", "development_path"),
        "engine_family": "delegated",
    },
    "storyboard_prompt": {
        "adapter": "storyboard_scene_image_video_engine",
        "input_requirements": ("storyboard_image_scenes", "final_video_scenes"),
        "engine_family": "storyboard",
    },
    "prompt_vault_to_video": {
        "adapter": "prompt_vault_text_to_video",
        "input_requirements": ("vault_prompt", "profile", "package"),
        "engine_family": "single_video",
    },
    "video_local_edit": {
        "adapter": "local_ffmpeg_edit",
        "input_requirements": ("source_video", "edit_plan"),
        "engine_family": "local_edit",
        "allow_local": True,
    },
}


def json_loads(value: Any, fallback: Any = None) -> Any:
    if value in (None, ""):
        return {} if fallback is None else fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return {} if fallback is None else fallback


def normalize_video_product_type(value: Any = "") -> str:
    token = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "video_ai_real": "video_ai_prompt",
        "prompt_to_video": "video_ai_prompt",
        "ai_prompt": "video_ai_prompt",
        "ai_image": "video_ai_image",
        "image_ai_video": "video_ai_image",
        "ai_video_reference": "video_ai_video_reference",
        "video_reference": "video_ai_video_reference",
        "script_image_video": "script_to_video",
        "frame_video_local": "image_to_video",
        "storyboard": "storyboard_prompt",
        "video_idea": "video_idea_to_product",
        "multiscene_video": "multi_scene_film",
    }
    return aliases.get(token, token)


def product_type_from_project(project: dict | None = None, result: dict | None = None) -> str:
    project = dict(project or {})
    result = dict(result or {})
    asset_pack = json_loads(project.get("asset_pack_json") or project.get("asset_pack"), {})
    invoice = json_loads(project.get("invoice_json") or project.get("invoice"), {})
    candidates = [
        result.get("product_type"),
        asset_pack.get("product_type") if isinstance(asset_pack, dict) else "",
        asset_pack.get("video_product_type") if isinstance(asset_pack, dict) else "",
        invoice.get("product_type") if isinstance(invoice, dict) else "",
        project.get("product_type"),
        project.get("profile_id"),
    ]
    for candidate in candidates:
        normalized = normalize_video_product_type(candidate)
        if normalized in VIDEO_PRODUCT_ENGINE_ROUTES:
            return normalized
    return "video_ai_prompt"


def route_for_product_type(product_type: str = "") -> dict[str, Any]:
    normalized = normalize_video_product_type(product_type)
    route = dict(VIDEO_PRODUCT_ENGINE_ROUTES.get(normalized) or {})
    if route:
        route["product_type"] = normalized
    return route


def ffprobe_path(ffmpeg_path: str = "") -> str:
    if ffmpeg_path:
        ffmpeg = Path(ffmpeg_path)
        sibling = ffmpeg.with_name("ffprobe.exe" if ffmpeg.suffix.lower() == ".exe" else "ffprobe")
        if sibling.exists():
            return str(sibling)
    return shutil.which("ffprobe") or ""


def probe_video(path: str, *, ffprobe: str = "") -> dict[str, Any]:
    if not path:
        return {"ok": False, "reason": "output_missing"}
    clean = str(path or "").strip()
    if not os.path.exists(clean):
        return {"ok": False, "reason": "output_missing", "path": clean}
    size = os.path.getsize(clean)
    if size <= 0:
        return {"ok": False, "reason": "output_zero_bytes", "path": clean, "bytes": int(size)}
    probe_bin = ffprobe or ffprobe_path()
    if not probe_bin:
        return {"ok": False, "reason": "ffprobe_missing", "path": clean, "bytes": int(size)}
    cmd = [
        probe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type",
        "-of",
        "json",
        clean,
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    if completed.returncode != 0:
        return {"ok": False, "reason": "ffprobe_failed", "path": clean, "bytes": int(size)}
    payload = json_loads(completed.stdout, {})
    streams = list(payload.get("streams") or []) if isinstance(payload, dict) else []
    has_video = any(str(item.get("codec_type") or "") == "video" for item in streams if isinstance(item, dict))
    has_audio = any(str(item.get("codec_type") or "") == "audio" for item in streams if isinstance(item, dict))
    try:
        duration = float(((payload.get("format") or {}) if isinstance(payload, dict) else {}).get("duration") or 0)
    except Exception:
        duration = 0.0
    if duration <= 0:
        return {"ok": False, "reason": "output_zero_duration", "path": clean, "bytes": int(size), "duration": duration, "has_video": has_video, "has_audio": has_audio}
    if not has_video:
        return {"ok": False, "reason": "output_no_video_stream", "path": clean, "bytes": int(size), "duration": duration, "has_audio": has_audio}
    return {"ok": True, "path": clean, "bytes": int(size), "duration": duration, "has_video": True, "has_audio": has_audio}


def is_placeholder_or_draft(result: dict | None = None) -> bool:
    payload = dict(result or {})
    renderer = str(payload.get("connector_renderer") or payload.get("renderer") or "").strip().lower()
    classification = str(payload.get("visual_classification") or payload.get("final_classification") or "").strip().lower()
    if classification in {"partial_simple_video", "failed_no_real_visual"}:
        return True
    if payload.get("placeholder_detected") or payload.get("placeholder_visual") or payload.get("raw_prompt_burned_into_frame"):
        return True
    return any(marker in renderer for marker in ("local_scene_composer", "local_placeholder", "text_slide", "color_slide", "placeholder", "testsrc", "test_pattern"))


def validate_final_video_output(
    *,
    path: str = "",
    result: dict | None = None,
    require_audio: bool = False,
    allow_admin_test: bool = False,
    ffprobe: str = "",
) -> dict[str, Any]:
    payload = dict(result or {})
    if not allow_admin_test and is_placeholder_or_draft(payload):
        return {"ok": False, "reason": "placeholder_not_final_video"}
    probe = probe_video(path or str(payload.get("final_video_path") or ""), ffprobe=ffprobe)
    if not probe.get("ok"):
        return probe
    if require_audio and not probe.get("has_audio"):
        return {**probe, "ok": False, "reason": "output_no_audio_stream"}
    return {**probe, "ok": True, "terminal_state": "final_delivered"}


def final_output_audit_payload() -> dict[str, Any]:
    routes = {key: route_for_product_type(key) for key in VIDEO_PRODUCT_ENGINE_ROUTES}
    checks = [
        {"name": "all_products_have_routes", "ok": all(route.get("adapter") for route in routes.values())},
        {"name": "final_states_defined", "ok": VIDEO_FINAL_STATES >= {"draft_ready", "final_rendering", "final_delivered", "failed_no_charge", "failed_refunded", "needs_admin_review"}},
        {"name": "placeholder_rejected", "ok": validate_final_video_output(path="", result={"visual_classification": "partial_simple_video"}).get("reason") == "placeholder_not_final_video"},
    ]
    return {"ok": all(item["ok"] for item in checks), "checks": checks, "routes": routes}
