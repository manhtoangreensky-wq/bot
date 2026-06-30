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
import tempfile
from pathlib import Path
from typing import Any


FINAL_AI_VIDEO = "final_ai_video"
LOCAL_IMAGE_SEQUENCE_RENDERER = "local_image_sequence_engine"
VISUAL_SOURCE_LOCAL_IMAGE_SEQUENCE = "local_image_sequence"
SUPPORTED_LOCAL_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".ppm"}
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


def ffmpeg_path(configured: str = "") -> str:
    value = str(configured or os.environ.get("FFMPEG_PATH") or os.environ.get("LOCAL_FFMPEG_PATH") or "").strip()
    if value and (os.path.isfile(value) or shutil.which(value)):
        return value
    return shutil.which("ffmpeg") or ""


def _looks_like_image_path(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text and Path(text).suffix.lower() in SUPPORTED_LOCAL_IMAGE_SUFFIXES)


def _existing_file_path(value: Any, *, suffixes: set[str] | None = None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    path = Path(text)
    if suffixes and path.suffix.lower() not in suffixes:
        return ""
    try:
        if path.is_file() and path.stat().st_size > 0:
            return str(path)
    except OSError:
        return ""
    return ""


def _payload_dict(value: Any) -> dict[str, Any]:
    payload = json_loads(value, {})
    return payload if isinstance(payload, dict) else {}


def _payload_list(value: Any) -> list[Any]:
    payload = json_loads(value, [])
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return [payload]
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def extract_local_image_paths(payload: Any, *, limit: int = 80) -> list[str]:
    """Collect already-downloaded image paths from a job/project payload."""
    image_value_keys = {
        "path",
        "local_path",
        "file_path",
        "source_path",
        "image_path",
        "image_file_path",
        "frame_path",
        "storyboard_frame_path",
        "reference_image_path",
    }
    image_list_keys = {
        "image_paths",
        "images",
        "source_images",
        "photo_paths",
        "photos",
        "storyboard_image_paths",
        "storyboard_images",
        "storyboard_frames",
        "storyboard_image_scenes",
        "image_scenes",
        "scene_images",
        "scene_cards",
        "scenes",
        "product_refs",
        "subject_refs",
        "object_refs",
        "character_refs",
        "background_refs",
        "style_refs",
    }
    nested_keys = {
        "asset_pack",
        "asset_pack_json",
        "project",
        "project_json",
        "storyboard",
        "storyboard_json",
        "story_bible",
        "story_bible_json",
        "draft",
        "selected_suggestion",
        "selected_suggestion_json",
    }
    result: list[str] = []
    seen: set[str] = set()

    def add_path(value: Any) -> None:
        if len(result) >= max(1, int(limit or 80)):
            return
        if not _looks_like_image_path(value):
            return
        clean = _existing_file_path(value, suffixes=SUPPORTED_LOCAL_IMAGE_SUFFIXES)
        if not clean:
            return
        key = os.path.abspath(clean).lower()
        if key in seen:
            return
        seen.add(key)
        result.append(clean)

    def scan(value: Any, depth: int = 0) -> None:
        if len(result) >= max(1, int(limit or 80)) or depth > 8:
            return
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                parsed = json_loads(stripped, None)
                if parsed is not None:
                    scan(parsed, depth + 1)
                    return
            add_path(stripped)
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                scan(item, depth + 1)
            return
        if not isinstance(value, dict):
            return
        for key, item in value.items():
            key_text = str(key or "")
            lowered = key_text.lower()
            if lowered in image_value_keys or lowered.endswith("_image_path") or lowered.endswith("_file_path"):
                if isinstance(item, (list, tuple)):
                    for entry in item:
                        add_path(entry)
                else:
                    add_path(item)
            elif lowered in image_list_keys:
                for entry in _payload_list(item):
                    scan(entry, depth + 1)
            elif lowered in nested_keys:
                nested = _payload_dict(item) if isinstance(item, str) else item
                scan(nested, depth + 1)

    scan(payload, 0)
    return result


def _canvas_size(aspect_ratio: str = "9:16") -> tuple[int, int]:
    value = str(aspect_ratio or "9:16").strip()
    if value == "16:9":
        return 960, 540
    if value == "1:1":
        return 720, 720
    return 540, 960


def _concat_file_line(path: str) -> str:
    clean = str(Path(path).resolve()).replace("\\", "/").replace("'", "'\\''")
    return f"file '{clean}'\n"


def render_local_image_sequence_video(
    image_paths: list[str] | tuple[str, ...],
    output_path: str,
    *,
    aspect_ratio: str = "9:16",
    duration_per_image: float = 2.0,
    audio_path: str = "",
    ffmpeg: str = "",
    ffprobe: str = "",
) -> dict[str, Any]:
    """Render real user-provided images into a validated MP4 slideshow."""
    clean_images = []
    seen: set[str] = set()
    for path in image_paths or []:
        clean = _existing_file_path(path, suffixes=SUPPORTED_LOCAL_IMAGE_SUFFIXES)
        if not clean:
            continue
        key = os.path.abspath(clean).lower()
        if key in seen:
            continue
        seen.add(key)
        clean_images.append(clean)
    if not clean_images:
        return {"ok": False, "error": "local_image_sequence_no_images"}
    ffmpeg_bin = ffmpeg_path(ffmpeg)
    if not ffmpeg_bin:
        return {"ok": False, "error": "ffmpeg_missing"}
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    width, height = _canvas_size(aspect_ratio)
    duration = max(0.8, min(12.0, float(duration_per_image or 2.0)))
    timeout = max(90, int(duration * max(1, len(clean_images)) * 30))
    with tempfile.TemporaryDirectory(prefix="toan_image_sequence_", dir=str(output.parent)) as temp_dir:
        temp_root = Path(temp_dir)
        clips: list[str] = []
        fade_out = max(0.1, duration - 0.25)
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},format=yuv420p,"
            f"fade=t=in:st=0:d=0.18,fade=t=out:st={fade_out:.3f}:d=0.20"
        )
        for index, image in enumerate(clean_images, start=1):
            clip = temp_root / f"clip_{index:03d}.mp4"
            cmd = [
                ffmpeg_bin,
                "-y",
                "-loop",
                "1",
                "-t",
                f"{duration:.3f}",
                "-i",
                str(image),
                "-vf",
                vf,
                "-r",
                "30",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "22",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(clip),
            ]
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if completed.returncode != 0:
                return {"ok": False, "error": "image_clip_render_failed", "stderr": (completed.stderr or completed.stdout or "")[:500]}
            clips.append(str(clip))
        concat_path = temp_root / "concat.txt"
        concat_path.write_text("".join(_concat_file_line(path) for path in clips), encoding="utf-8")
        silent_output = temp_root / "silent.mp4"
        concat_cmd = [
            ffmpeg_bin,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(silent_output),
        ]
        completed = subprocess.run(concat_cmd, capture_output=True, text=True, timeout=timeout)
        if completed.returncode != 0:
            return {"ok": False, "error": "image_sequence_concat_failed", "stderr": (completed.stderr or completed.stdout or "")[:500]}
        clean_audio = _existing_file_path(audio_path) if audio_path else ""
        if clean_audio:
            mux_cmd = [
                ffmpeg_bin,
                "-y",
                "-i",
                str(silent_output),
                "-stream_loop",
                "-1",
                "-i",
                clean_audio,
                "-shortest",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                str(output),
            ]
            completed = subprocess.run(mux_cmd, capture_output=True, text=True, timeout=timeout)
            if completed.returncode != 0:
                return {"ok": False, "error": "image_sequence_audio_mux_failed", "stderr": (completed.stderr or completed.stdout or "")[:500]}
        else:
            shutil.copyfile(str(silent_output), str(output))
    validation = validate_final_video_output(
        path=str(output),
        result={"renderer": LOCAL_IMAGE_SEQUENCE_RENDERER, "visual_classification": FINAL_AI_VIDEO},
        ffprobe=ffprobe or ffprobe_path(ffmpeg_bin),
    )
    if not validation.get("ok"):
        return {"ok": False, "error": str(validation.get("reason") or "local_image_sequence_invalid"), "validation": validation}
    return {
        "ok": True,
        "final_video_path": str(output),
        "renderer": LOCAL_IMAGE_SEQUENCE_RENDERER,
        "visual_source": VISUAL_SOURCE_LOCAL_IMAGE_SEQUENCE,
        "visual_classification": FINAL_AI_VIDEO,
        "final_classification": FINAL_AI_VIDEO,
        "image_count": len(clean_images),
        "output_bytes": int(validation.get("bytes") or 0),
        "output_duration": float(validation.get("duration") or 0),
        "has_video": bool(validation.get("has_video")),
        "has_audio": bool(validation.get("has_audio")),
    }


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
