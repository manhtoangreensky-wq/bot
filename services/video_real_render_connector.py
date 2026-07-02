"""Real provider connector for product video worker jobs.

This module bridges the B14/remote-worker job contract to existing video
providers. It never generates testsrc/color bars and never marks a job complete
without a downloaded MP4 for every rendered scene.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import time
import urllib.request
from pathlib import Path
from typing import Any

import httpx

from services.multiscene_video_pipeline import ensure_video_output, process_multiscene_video_pipeline, safe_run_ffmpeg
from services import video_final_output
from services.video_provider_base import VideoGenerationRequest
from services.video_provider_router import (
    PUBLIC_NO_VIDEO_PROVIDER_COPY,
    capability_options,
    normalize_capability_values,
    provider_status_payload,
    run_provider_generation,
)


REAL_VIDEO_RENDER_UNAVAILABLE = "real_video_renderer_unavailable"
FINAL_AI_VIDEO = "final_ai_video"
PARTIAL_SIMPLE_VIDEO = "partial_simple_video"
FAILED_NO_REAL_VISUAL = "failed_no_real_visual"
LOCAL_PLACEHOLDER_RENDERER = "local_scene_composer"
LOCAL_IMAGE_SEQUENCE_RENDERER = video_final_output.LOCAL_IMAGE_SEQUENCE_RENDERER
LOCAL_SCENE_CARD_RENDERER = video_final_output.LOCAL_SCENE_CARD_RENDERER
PROVIDER_SCENE_RENDERER = "provider_scene_video"
VISUAL_SOURCE_PROVIDER_MP4 = "provider_mp4"
VISUAL_SOURCE_LOCAL_PLACEHOLDER = "local_placeholder"
VISUAL_SOURCE_LOCAL_IMAGE_SEQUENCE = video_final_output.VISUAL_SOURCE_LOCAL_IMAGE_SEQUENCE
VISUAL_SOURCE_LOCAL_SCENE_CARD = video_final_output.VISUAL_SOURCE_LOCAL_SCENE_CARD
LOCAL_IMAGE_SEQUENCE_PRODUCT_TYPES = {"image_to_video", "storyboard_prompt", "script_to_video"}
LOCAL_SCENE_CARD_PRODUCT_TYPES = {"script_to_video", "storyboard_prompt", "multi_scene_film"}
PROVIDER_BRIDGE_RENDERER = "video_provider_bridge"
PROVIDER_VIDEO_SOURCE = "provider"
PROVIDER_REQUIRED_PRODUCT_TYPES = {
    "video_ai_prompt",
    "prompt_vault_to_video",
}
PROVIDER_REQUIRED_CAPABILITIES = {
    "text_to_video",
    "image_to_video",
    "video_to_video",
    "multi_scene_video",
    "scene_video",
    "text_to_video_or_scene_video",
    "delegates_to_selected_product",
}
PROVIDER_CLEAN_FAIL_FALLBACKS = {
    "clean_fail_provider_capability_missing",
    "delegate_or_clean_fail",
}

RAW_PROMPT_FRAME_MARKERS = (
    "chủ thể chính:",
    "chu the chinh:",
    "visual:",
    "prompt:",
    "provider:",
    "debug:",
    "pov trải nghiệm thật: add one subtle visual",
    "pov trai nghiem that: add one subtle visual",
)


LAST_RENDER_DIAGNOSTICS: dict[str, Any] = {}


class RealVideoRenderError(RuntimeError):
    """Safe worker-facing render error with admin-only diagnostics."""

    def __init__(self, message: str = "", diagnostics: dict[str, Any] | None = None):
        super().__init__(message or REAL_VIDEO_RENDER_UNAVAILABLE)
        self.diagnostics = dict(diagnostics or {})


def _record_render_diagnostics(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global LAST_RENDER_DIAGNOSTICS
    LAST_RENDER_DIAGNOSTICS = dict(payload or {})
    return LAST_RENDER_DIAGNOSTICS


def _env_flag(name: str, default: str = "0") -> bool:
    return str(os.environ.get(name, default) or default).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.environ.get(name, str(default)) or str(default)).strip())
    except Exception:
        return int(default)


def _json_loads(value: Any, fallback: Any = None) -> Any:
    if value in (None, ""):
        return {} if fallback is None else fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return {} if fallback is None else fallback


def _safe_text(value: Any, limit: int = 4000) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text[:limit]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def is_local_placeholder_renderer(renderer: Any) -> bool:
    value = str(renderer or "").strip().lower()
    return any(marker in value for marker in ("local_scene_composer", "local_placeholder", "text_slide", "color_slide", "placeholder"))


def classify_visual_result(result: dict | None = None) -> str:
    payload = dict(result or {})
    explicit = str(payload.get("visual_classification") or payload.get("final_classification") or "").strip()
    if explicit in {FINAL_AI_VIDEO, PARTIAL_SIMPLE_VIDEO, FAILED_NO_REAL_VISUAL}:
        return explicit
    if not payload.get("ok"):
        return FAILED_NO_REAL_VISUAL
    renderer = str(payload.get("renderer") or payload.get("connector_renderer") or "").strip().lower()
    if is_local_placeholder_renderer(renderer) or payload.get("placeholder_detected") or payload.get("placeholder_visual"):
        return PARTIAL_SIMPLE_VIDEO
    if payload.get("raw_prompt_burned_into_frame"):
        return FAILED_NO_REAL_VISUAL
    if renderer in {LOCAL_IMAGE_SEQUENCE_RENDERER, LOCAL_SCENE_CARD_RENDERER} or payload.get("visual_source") in {VISUAL_SOURCE_LOCAL_IMAGE_SEQUENCE, VISUAL_SOURCE_LOCAL_SCENE_CARD}:
        return FINAL_AI_VIDEO
    if renderer in {"real_provider", PROVIDER_SCENE_RENDERER, "provider_video"} or payload.get("provider_attempted"):
        return FINAL_AI_VIDEO
    return FAILED_NO_REAL_VISUAL


def _contains_raw_prompt_marker(text: Any) -> bool:
    value = _safe_text(text, 3000).lower()
    if not value:
        return False
    return any(marker in value for marker in RAW_PROMPT_FRAME_MARKERS)


def _provider_order(job: dict | None = None) -> list[str]:
    job = dict(job or {})
    asset_pack = _json_loads(job.get("asset_pack"), {})
    if not asset_pack and isinstance(job.get("project"), dict):
        asset_pack = _json_loads((job.get("project") or {}).get("asset_pack_json"), {})
    raw = (
        job.get("provider_order")
        or asset_pack.get("provider_order")
        or os.environ.get("VIDEO_PROVIDER_CHAIN")
        or os.environ.get("VIDEO_PROVIDER_ORDER")
        or "shopaikey_video,key4u_video,toanaas_video,veo,kling,generic_http"
    )
    if isinstance(raw, (list, tuple)):
        values = raw
    else:
        values = re.split(r"[,|>\s]+", str(raw or ""))
    result = []
    for item in values:
        provider = str(item or "").strip().lower()
        if provider in {"shopai", "shopaikey", "shopaikey_video"}:
            provider = "shopaikey_video"
        elif provider in {"key4u", "k4u", "key4u_video"}:
            provider = "key4u_video"
        elif provider in {"toanaas", "toanaas_video"}:
            provider = "toanaas_video"
        elif provider in {"veo", "video_veo"}:
            provider = "veo"
        elif provider in {"kling", "video_kling"}:
            provider = "kling"
        elif provider in {"generic", "generic_http", "gommo", "79ai", "gommo79ai", "gommo_79ai", "go-mmo"}:
            provider = "generic_http"
        else:
            continue
        if provider not in result:
            result.append(provider)
    return result or ["shopaikey_video", "key4u_video", "toanaas_video", "veo", "kling", "generic_http"]


def real_video_provider_readiness(job: dict | None = None, environ: dict[str, str] | None = None) -> dict:
    del job
    status = provider_status_payload(environ)
    providers = list(status.get("providers") or [])
    ordered_ready = list(status.get("ready_provider_order") or [])
    return {
        "ok": bool(ordered_ready),
        "provider_order": list(status.get("provider_chain") or []),
        "configured_providers": ordered_ready,
        "ready_provider_order": ordered_ready,
        "first_ready_provider": status.get("first_ready_provider") or (ordered_ready[0] if ordered_ready else ""),
        "enabled_count": int(status.get("enabled_count") or 0),
        "configured_count": int(status.get("configured_count") or 0),
        "enabled_providers": list(status.get("enabled_providers") or []),
        "missing_env": dict(status.get("missing_env") or {}),
        "providers": providers,
    }


def _provider_candidates_for_capability(readiness: dict | None = None, required_capability: str = "") -> list[str]:
    payload = dict(readiness or {})
    allowed = set(capability_options(required_capability))
    candidates: list[str] = []
    for item in payload.get("providers") or []:
        if not isinstance(item, dict):
            continue
        if not item.get("configured"):
            continue
        supported = set(normalize_capability_values(item.get("capabilities") or []))
        if allowed and not (supported & allowed):
            continue
        provider_name = str(item.get("provider") or "").strip()
        if provider_name and provider_name not in candidates:
            candidates.append(provider_name)
    if candidates:
        return candidates
    ready = [str(item or "").strip() for item in (payload.get("ready_provider_order") or []) if str(item or "").strip()]
    return ready


def _route_requires_provider(
    product_type: str,
    required_capability: str,
    fallback_capability: str,
    *,
    provider_ready: bool = False,
) -> bool:
    product = video_final_output.normalize_video_product_type(product_type)
    capability = str(required_capability or "").strip()
    fallback = str(fallback_capability or "").strip()
    if product in PROVIDER_REQUIRED_PRODUCT_TYPES:
        return True
    if capability not in PROVIDER_REQUIRED_CAPABILITIES:
        return False
    if fallback in PROVIDER_CLEAN_FAIL_FALLBACKS:
        return True
    if provider_ready and product in {"video_ai_image", "video_ai_video_reference", "self_shot_scene_change"}:
        return True
    return False


def _addon_plan(job: dict | None = None) -> dict:
    job = dict(job or {})
    candidates = [
        job.get("addon_plan"),
        job.get("addon_plan_json"),
        (job.get("project") or {}).get("addon_plan_json") if isinstance(job.get("project"), dict) else "",
    ]
    for candidate in candidates:
        value = _json_loads(candidate, {})
        if isinstance(value, dict) and value:
            return value
    return {}


def original_prompt_from_job(job: dict | None = None) -> str:
    job = dict(job or {})
    asset_pack = _json_loads(job.get("asset_pack"), {})
    if not asset_pack and isinstance(job.get("project"), dict):
        asset_pack = _json_loads((job.get("project") or {}).get("asset_pack_json"), {})
    candidates = [
        job.get("original_user_prompt"),
        job.get("cleaned_user_prompt"),
        asset_pack.get("original_user_prompt") if isinstance(asset_pack, dict) else "",
        asset_pack.get("cleaned_user_prompt") if isinstance(asset_pack, dict) else "",
        job.get("prompt_text"),
        (job.get("project") or {}).get("prompt_text") if isinstance(job.get("project"), dict) else "",
        job.get("topic"),
        (job.get("project") or {}).get("topic") if isinstance(job.get("project"), dict) else "",
    ]
    for candidate in candidates:
        text = _safe_text(candidate, 4000)
        if text and "No render/provider call before" not in text:
            return text
    return "short product video"


def _scene_cards(job: dict | None = None) -> list[dict]:
    job = dict(job or {})
    cards = job.get("scene_cards")
    if not cards and isinstance(job.get("project"), dict):
        cards = _json_loads((job.get("project") or {}).get("scene_cards_json"), [])
    if isinstance(cards, list):
        return [dict(item or {}) for item in cards if isinstance(item, dict)]
    return []


def _has_user_facing_subtitle_text(job: dict | None = None) -> bool:
    addon = _addon_plan(job)
    if _safe_text(addon.get("narration_text") or addon.get("script_text") or addon.get("subtitle_text"), 1000):
        return True
    for card in _scene_cards(job):
        if _safe_text(card.get("narration_line") or card.get("script_text") or card.get("subtitle_line"), 1000):
            return True
    return False


def _subtitle_raw_prompt_burn_detected(job: dict | None, result: dict | None) -> bool:
    subtitle_path = str((result or {}).get("subtitle_path") or "").strip()
    if not subtitle_path or not os.path.isfile(subtitle_path):
        return False
    try:
        with open(subtitle_path, "r", encoding="utf-8", errors="ignore") as handle:
            content = handle.read(6000)
    except OSError:
        return False
    if _contains_raw_prompt_marker(content):
        return True
    return False


def _scene_count(job: dict | None = None) -> int:
    job = dict(job or {})
    value = job.get("scene_count")
    if not value and isinstance(job.get("project"), dict):
        value = (job.get("project") or {}).get("scene_count")
    return max(1, min(20, _safe_int(value, 3)))


def _product_type(job: dict | None = None) -> str:
    job = dict(job or {})
    project = dict(job.get("project") or {})
    if not project and job.get("asset_pack"):
        project = {"asset_pack_json": job.get("asset_pack")}
    product_type = video_final_output.product_type_from_project(project, job)
    return video_final_output.normalize_video_product_type(product_type)


def _local_image_sequence_paths(job: dict | None = None) -> list[str]:
    return video_final_output.extract_local_image_paths(job or {})


def _local_image_sequence_allowed(job: dict | None = None, paths: list[str] | None = None) -> bool:
    if not paths:
        return False
    product_type = _product_type(job)
    if product_type in LOCAL_IMAGE_SEQUENCE_PRODUCT_TYPES:
        return True
    route = video_final_output.route_for_product_type(product_type)
    return str(route.get("engine_family") or "") in {"image_sequence", "storyboard"} and product_type not in {"video_ai_image"}


def _local_scene_card_allowed(job: dict | None = None) -> bool:
    """Allow local final MP4 only for products whose canonical output is scenes."""
    product_type = _product_type(job)
    if product_type in LOCAL_SCENE_CARD_PRODUCT_TYPES:
        return True
    if product_type == "video_trend":
        return bool(_scene_cards(job))
    return False


def _local_addon_audio_path(job: dict | None = None) -> str:
    addon = _addon_plan(job)
    candidates = [
        addon.get("music_path"),
        addon.get("music_audio_path"),
        addon.get("bgm_audio_path"),
        addon.get("voice_path"),
        addon.get("voice_audio_path"),
        addon.get("audio_path"),
    ]
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text and os.path.isfile(text) and os.path.getsize(text) > 0:
            return text
    return ""


def _aspect_ratio(job: dict | None = None) -> str:
    job = dict(job or {})
    value = job.get("aspect_ratio") or job.get("ratio")
    if not value and isinstance(job.get("project"), dict):
        value = (job.get("project") or {}).get("ratio")
    text = str(value or "9:16").strip()
    return text if re.match(r"^\d{1,2}:\d{1,2}$", text) else "9:16"


def _soft_prompt(base_prompt: str, scene_index: int, scene_count: int, aspect_ratio: str, style: str = "") -> str:
    base = _safe_text(base_prompt, 900)
    stage = {
        1: "opening establishing shot with the clearest subject and mood",
        2: "detail/action shot showing benefit, texture, motion, and context",
        3: "closing hero shot with satisfying payoff and polished composition",
    }.get(scene_index, "continuation shot with a new angle and clear visual progression")
    style_text = _safe_text(style, 220)
    return (
        f"Vertical {aspect_ratio} cinematic video scene {scene_index}/{scene_count}. "
        f"User intent: {base}. "
        f"Scene direction: {stage}. "
        f"{style_text + '. ' if style_text else ''}"
        "Natural camera movement, realistic lighting, coherent continuity with previous scenes, "
        "professional commercial quality, no fake logo, no extra text, no watermark, no subtitles."
    )[:1200]


def real_video_scene_plan(job: dict | None = None) -> dict:
    job = dict(job or {})
    count = _scene_count(job)
    aspect_ratio = _aspect_ratio(job)
    total_duration = _safe_int(job.get("expected_duration_seconds") or job.get("duration_seconds"), 0)
    if total_duration > 0:
        default_duration = max(1.0, min(8.0, float(total_duration) / max(1, count)))
    else:
        default_duration = max(1.0, min(8.0, float(_safe_int(job.get("scene_duration") or 6, 6))))
    original = original_prompt_from_job(job)
    style = _safe_text(job.get("profile_id") or "", 120)
    cards = _scene_cards(job)
    scenes = []
    for index in range(1, count + 1):
        card = cards[index - 1] if index - 1 < len(cards) else {}
        prompt = _safe_text(
            card.get("provider_prompt")
            or card.get("video_prompt")
            or card.get("visual_goal")
            or card.get("image_prompt"),
            1200,
        )
        if not prompt:
            prompt = _soft_prompt(original, index, count, aspect_ratio, style)
        elif original and original.lower() not in prompt.lower():
            prompt = f"{prompt} User intent to preserve: {original}"[:1200]
        scenes.append(
            {
                "scene_id": index,
                "title": _safe_text(card.get("title") or card.get("role") or f"Scene {index}", 120),
                "visual_prompt": _safe_text(card.get("visual_goal") or card.get("image_prompt") or prompt, 1200),
                "video_prompt": prompt,
                "narration_text": _safe_text(card.get("narration_line") or card.get("script_text") or card.get("subtitle_line") or "", 1000) or None,
                "target_duration_sec": default_duration,
                "aspect_ratio": aspect_ratio,
                "transition": None if index == count else "cut",
                "provider_params": {"real_provider": True, "original_user_prompt": original},
            }
        )
    return {"scenes": scenes}


def real_video_llm_func_from_job(job: dict | None = None):
    plan = real_video_scene_plan(job)

    def _llm_func(*_args, **_kwargs):
        return plan

    return _llm_func


def _join_url(base: str, path: str) -> str:
    base = str(base or "").strip().rstrip("/")
    path = str(path or "").strip()
    if path.startswith(("http://", "https://")):
        return path
    return base + "/" + path.lstrip("/")


def _video_payload_data(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _extract_task_id(payload: dict) -> str:
    data = _video_payload_data(payload)
    for value in (data.get("task_id"), data.get("taskId"), data.get("id"), payload.get("task_id"), payload.get("id")):
        text = str(value or "").strip()
        if text:
            return text[:180]
    return ""


def _extract_output_url(payload: dict) -> str:
    data = _video_payload_data(payload)
    candidates = [
        data.get("result_url"),
        data.get("video_url"),
        data.get("output_url"),
        data.get("url"),
        payload.get("result_url"),
        payload.get("video_url"),
        payload.get("output_url"),
        payload.get("url"),
    ]
    nested = data.get("result") if isinstance(data.get("result"), dict) else {}
    candidates.extend([nested.get("result_url"), nested.get("video_url"), nested.get("url")])
    for value in candidates:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _normalized_status(payload: dict) -> str:
    data = _video_payload_data(payload)
    raw = str(data.get("status") or payload.get("status") or payload.get("code") or "").strip().upper()
    if raw in {"SUCCESS", "SUCCEEDED", "COMPLETED", "DONE", "FINISHED"}:
        return "SUCCESS"
    if raw in {"FAIL", "FAILED", "FAILURE", "ERROR", "CANCELLED", "CANCELED"}:
        return "FAILED"
    if raw in {"QUEUED", "PENDING", "SUBMITTED", "PROCESSING", "IN_PROGRESS", "RUNNING", "STARTED", "GENERATING"}:
        return "IN_PROGRESS"
    return raw or "UNKNOWN"


async def _submit_shopaikey(prompt: str, aspect_ratio: str) -> dict:
    api_key = str(os.environ.get("SHOPAIKEY_API_KEY") or "").strip()
    url = str(os.environ.get("SHOPAIKEY_VIDEO_URL") or "").strip()
    if not url:
        base = str(os.environ.get("SHOPAIKEY_BASE_URL") or "").strip()
        endpoint = str(os.environ.get("SHOPAIKEY_VIDEO_ENDPOINT") or "/video/generations").strip()
        url = _join_url(base, endpoint) if base else ""
    model = str(os.environ.get("SHOPAIKEY_VIDEO_MODEL") or os.environ.get("SHOPAIKEY_VIDEO_MODEL_PRIMARY") or "veo3.1-fast").strip()
    if not api_key or not url or not model:
        return {"ok": False, "provider": "shopaikey", "error": "shopaikey_video_config_missing"}
    payload = {
        "model": model,
        "prompt": _safe_text(prompt, 1200),
        "metadata": {"aspect_ratio": aspect_ratio, "enhance_prompt": False, "enable_upsample": False},
    }
    async with httpx.AsyncClient(timeout=float(_env_int("REAL_VIDEO_SUBMIT_TIMEOUT_SECONDS", 60))) as client:
        response = await client.post(url, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json=payload)
    try:
        data = response.json()
    except Exception:
        data = {}
    task_id = _extract_task_id(data)
    if response.status_code < 400 and task_id:
        return {"ok": True, "provider": "shopaikey", "task_id": task_id, "model": model}
    return {"ok": False, "provider": "shopaikey", "error": f"shopaikey_submit_failed:{response.status_code}"}


async def _poll_shopaikey(task_id: str) -> dict:
    api_key = str(os.environ.get("SHOPAIKEY_API_KEY") or "").strip()
    submit_url = str(os.environ.get("SHOPAIKEY_VIDEO_URL") or "").strip()
    status_endpoint = str(os.environ.get("SHOPAIKEY_VIDEO_STATUS_ENDPOINT") or "").strip()
    if status_endpoint:
        if "{task_id}" in status_endpoint:
            url = status_endpoint.replace("{task_id}", task_id)
        elif "{id}" in status_endpoint:
            url = status_endpoint.replace("{id}", task_id)
        else:
            url = status_endpoint.rstrip("/") + "/" + task_id
    else:
        url = submit_url.rstrip("/") + "/" + task_id
    if not api_key or not url:
        return {"ok": False, "provider": "shopaikey", "error": "shopaikey_status_config_missing"}
    async with httpx.AsyncClient(timeout=float(_env_int("REAL_VIDEO_POLL_TIMEOUT_SECONDS", 45))) as client:
        response = await client.get(url, headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"})
    try:
        data = response.json()
    except Exception:
        data = {}
    output_url = _extract_output_url(data)
    status = _normalized_status(data)
    return {"ok": bool(response.status_code < 400), "provider": "shopaikey", "status": status, "output_url": output_url, "http_status": response.status_code}


async def _submit_key4u(prompt: str, aspect_ratio: str) -> dict:
    try:
        from providers.key4u_provider import Key4UProvider
    except Exception as exc:
        return {"ok": False, "provider": "key4u", "error": f"key4u_import_failed:{type(exc).__name__}"}
    provider = Key4UProvider()
    if not provider.is_configured():
        return {"ok": False, "provider": "key4u", "error": "key4u_video_config_missing"}
    result = await provider.video_generation(
        prompt=prompt,
        model=str(os.environ.get("KEY4U_VIDEO_MODEL") or os.environ.get("KEY4U_DEFAULT_VIDEO_MODEL") or ""),
        timeout_seconds=float(_env_int("REAL_VIDEO_SUBMIT_TIMEOUT_SECONDS", 60)),
        aspect_ratio=aspect_ratio,
    )
    task_id = str(result.get("task_id") or "").strip()
    if result.get("ok") and task_id:
        return {"ok": True, "provider": "key4u", "task_id": task_id, "model": result.get("model") or ""}
    return {"ok": False, "provider": "key4u", "error": str(result.get("error_class") or result.get("status") or "key4u_submit_failed")}


async def _poll_key4u(task_id: str) -> dict:
    from providers.key4u_provider import Key4UProvider

    result = await Key4UProvider().poll_video_task(task_id, timeout_seconds=float(_env_int("REAL_VIDEO_POLL_TIMEOUT_SECONDS", 45)))
    output_url = str(result.get("output_url") or result.get("result_url") or "").strip()
    status = str(result.get("status") or "").upper()
    if output_url:
        status = "SUCCESS"
    elif status not in {"SUCCESS", "FAILED", "FAIL", "ERROR"}:
        status = "IN_PROGRESS"
    return {"ok": bool(result.get("ok") or output_url), "provider": "key4u", "status": status, "output_url": output_url, "http_status": result.get("http_status") or 0}


async def _submit_gommo(prompt: str, aspect_ratio: str, duration_seconds: float = 6.0) -> dict:
    try:
        from providers.gommo_79ai_provider import Gommo79AIProvider
    except Exception as exc:
        return {"ok": False, "provider": "gommo_79ai", "error": f"gommo_import_failed:{type(exc).__name__}"}
    provider = Gommo79AIProvider()
    if not provider.is_ready():
        return {"ok": False, "provider": "gommo_79ai", "error": "gommo_video_config_missing"}
    plan = await asyncio.to_thread(
        provider.pick_video_model,
        package="basic",
        scenes=1,
        duration=max(1, int(round(float(duration_seconds or 6.0)))),
        aspect_ratio=aspect_ratio,
        references={},
    )
    if not plan.get("ok"):
        return {"ok": False, "provider": "gommo_79ai", "error": str(plan.get("error") or "gommo_model_unavailable")}
    result = await asyncio.to_thread(
        provider.create_video,
        prompt=_safe_text(prompt, 1800),
        model=str(plan.get("model") or ""),
        ratio=str(plan.get("ratio") or aspect_ratio),
        resolution=str(plan.get("resolution") or "720p"),
        duration=int(plan.get("duration") or 6),
        mode=str(plan.get("mode") or "business_fast"),
        count_tasks=1,
        references={},
    )
    if result.get("ok") and (result.get("video_id") or result.get("task_id")):
        video_id = str(result.get("video_id") or result.get("task_id") or "").strip()
        task_id = str(result.get("task_id") or video_id).strip()
        return {
            "ok": True,
            "provider": "gommo_79ai",
            "video_id": video_id,
            "task_id": task_id,
            "status": str(result.get("status") or "IN_PROGRESS"),
            "download_url": str(result.get("download_url") or ""),
            "model": str(result.get("model") or plan.get("model") or ""),
            "mode": str(result.get("mode") or plan.get("mode") or ""),
            "ratio": str(result.get("ratio") or plan.get("ratio") or aspect_ratio),
            "resolution": str(result.get("resolution") or plan.get("resolution") or ""),
            "duration": int(result.get("duration") or plan.get("duration") or 6),
            "credit_fee": int(result.get("credit_fee") or 0),
        }
    return {"ok": False, "provider": "gommo_79ai", "error": str(result.get("error") or "gommo_create_video_failed")}


async def _poll_gommo(video_id: str) -> dict:
    try:
        from providers.gommo_79ai_provider import Gommo79AIProvider
    except Exception as exc:
        return {"ok": False, "provider": "gommo_79ai", "status": "FAILED", "error": f"gommo_import_failed:{type(exc).__name__}"}
    provider = Gommo79AIProvider()
    if not provider.is_ready():
        return {"ok": False, "provider": "gommo_79ai", "status": "FAILED", "error": "gommo_video_config_missing"}
    result = await asyncio.to_thread(
        provider.poll_video_until_ready,
        str(video_id or ""),
        max_attempts=max(1, _env_int("GOMMO_POLL_MAX_ATTEMPTS", _env_int("REAL_VIDEO_POLL_MAX_ATTEMPTS", 24))),
        interval_seconds=max(0, _env_int("GOMMO_POLL_INTERVAL_SECONDS", _env_int("REAL_VIDEO_POLL_INTERVAL_SECONDS", 25))),
        success_url_extra_attempts=max(0, _env_int("GOMMO_SUCCESS_URL_EXTRA_POLLS", 4)),
    )
    status = str(result.get("status") or "").upper()
    if result.get("download_url"):
        status = "SUCCESS"
    elif result.get("timeout"):
        status = "IN_PROGRESS"
    return {
        "ok": bool(result.get("ok", True)),
        "provider": "gommo_79ai",
        "status": status or "UNKNOWN",
        "output_url": str(result.get("download_url") or ""),
        "video_id": str(result.get("video_id") or video_id),
        "task_id": str(result.get("task_id") or video_id),
        "model": str(result.get("model") or ""),
        "mode": str(result.get("mode") or ""),
        "duration": int(result.get("duration") or 0),
        "credit_fee": int(result.get("credit_fee") or 0),
        "error": str(result.get("error") or ("poll_timeout" if result.get("timeout") else "")),
    }


async def _submit_provider(provider: str, prompt: str, aspect_ratio: str) -> dict:
    if provider == "shopaikey":
        return await _submit_shopaikey(prompt, aspect_ratio)
    if provider == "key4u":
        return await _submit_key4u(prompt, aspect_ratio)
    if provider == "gommo_79ai":
        return await _submit_gommo(prompt, aspect_ratio)
    return {"ok": False, "provider": provider, "error": "provider_unsupported"}


async def _poll_provider(provider: str, task_id: str, submit: dict | None = None) -> dict:
    if provider == "shopaikey":
        return await _poll_shopaikey(task_id)
    if provider == "key4u":
        return await _poll_key4u(task_id)
    if provider == "gommo_79ai":
        submit = dict(submit or {})
        return await _poll_gommo(str(submit.get("video_id") or task_id))
    return {"ok": False, "provider": provider, "status": "FAILED", "error": "provider_unsupported"}


def _download_output(source: str, destination: str) -> str:
    source = str(source or "").strip()
    target = os.path.abspath(destination)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if os.path.isfile(source):
        shutil.copyfile(source, target)
    elif source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=_env_int("REAL_VIDEO_DOWNLOAD_TIMEOUT_SECONDS", 180)) as response:
            with open(target, "wb") as handle:
                shutil.copyfileobj(response, handle)
    else:
        raise RealVideoRenderError("provider_output_url_missing")
    if not os.path.isfile(target) or os.path.getsize(target) <= 0:
        raise RealVideoRenderError("provider_output_empty")
    return target


async def _render_scene_async(scene, raw_path: str, provider_order: list[str]) -> dict:
    del provider_order
    prompt = _safe_text(getattr(scene, "video_prompt", "") or getattr(scene, "visual_prompt", ""), 1200)
    aspect_ratio = str(getattr(scene, "aspect_ratio", "") or "9:16")
    job = getattr(scene, "_toan_aas_job", {}) if hasattr(scene, "_toan_aas_job") else {}
    product_type = _product_type(job)
    route = video_final_output.route_for_product_type(product_type)
    required_capability = str(route.get("provider_capability") or "text_to_video")
    request = VideoGenerationRequest(
        job_id=(
            str((job or {}).get("id") or (job or {}).get("job_id") or "video_job")
            + "-"
            + str(_safe_int(getattr(scene, "scene_id", 0), 0) or 1)
        ),
        product_type=product_type or "video_ai_prompt",
        video_flow_type=str((job or {}).get("video_flow") or product_type or ""),
        prompt=prompt,
        negative_prompt=str((job or {}).get("negative_prompt") or ""),
        scenes=[dict(getattr(scene, "__dict__", {}) or {})],
        storyboard=_scene_cards(job),
        image_paths=_local_image_sequence_paths(job),
        source_video_path=str((job or {}).get("source_video_path") or ""),
        ratio=aspect_ratio,
        duration_seconds=float(getattr(scene, "target_duration_sec", 6.0) or 6.0),
        quality=str((job or {}).get("quality") or ""),
        style=str((job or {}).get("style") or ""),
        add_ons=_addon_plan(job),
        metadata={
            "scene_id": _safe_int(getattr(scene, "scene_id", 0), 0),
            "raw_output_path": raw_path,
            "product_video": bool(str((job or {}).get("source") or "") == "product_video" or (job or {}).get("product_video")),
            "render_mode": str((job or {}).get("render_mode") or ""),
            "allow_provider_pending": True,
        },
        required_capability=required_capability,
    )
    output_dir = os.path.dirname(os.path.abspath(raw_path))
    result = run_provider_generation(request, output_dir=output_dir)
    if not result.get("ok"):
        raise RealVideoRenderError(str(result.get("blocker") or result.get("provider_error") or REAL_VIDEO_RENDER_UNAVAILABLE), diagnostics=result)
    output_path = str(result.get("output_path") or result.get("local_path") or "")
    if not output_path:
        raise RealVideoRenderError("provider_result_missing", diagnostics=result)
    if os.path.abspath(output_path) != os.path.abspath(raw_path):
        shutil.copyfile(output_path, raw_path)
        output_path = raw_path
    return {
        "ok": True,
        "provider": str(result.get("provider") or ""),
        "task_id": str((result.get("provider_task_ids") or [""])[0] or ""),
        "video_id": str((result.get("provider_video_ids") or [""])[0] or ""),
        "status": "SUCCESS",
        "output_path": ensure_video_output(output_path),
        "model": str(result.get("model") or ""),
        "mode": str(result.get("mode") or ""),
        "duration": result.get("duration") or result.get("output_duration") or 0,
        "download_url_present": bool(result.get("result_url_present")),
        "artifact_hash": str(result.get("artifact_hash") or ""),
    }


def build_real_scene_renderer(job: dict | None = None, events: list[dict[str, Any]] | None = None):
    provider_order = _provider_order(job)

    def _render(scene, raw_path: str):
        try:
            setattr(scene, "_toan_aas_job", dict(job or {}))
        except Exception:
            pass
        result = asyncio.run(_render_scene_async(scene, raw_path, provider_order))
        if isinstance(events, list) and isinstance(result, dict):
            events.append(
                {
                    "scene_id": _safe_int(getattr(scene, "scene_id", 0), 0),
                    "provider": str(result.get("provider") or ""),
                    "task_id": str(result.get("task_id") or "")[:180],
                    "video_id": str(result.get("video_id") or "")[:180],
                    "status": "downloaded" if result.get("ok") else str(result.get("status") or "failed"),
                    "model": str(result.get("model") or "")[:120],
                    "mode": str(result.get("mode") or "")[:80],
                    "duration": result.get("duration") or 0,
                    "download_url_present": bool(result.get("download_url_present")),
                }
            )
        return result

    return _render


def _logo_enabled(addon_plan: dict) -> bool:
    return bool(addon_plan.get("logo_enabled") and _safe_text(addon_plan.get("logo_text"), 120))


def _addon_degrade_notes(addon_plan: dict, *, bgm_audio_path: str | None = None, job: dict | None = None) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    if addon_plan.get("voice_enabled"):
        notes.append(
            {
                "addon": "voice",
                "requested": True,
                "applied": False,
                "reason": "voice_addon_not_available_in_video_composer",
            }
        )
    if addon_plan.get("music_enabled"):
        source = str(addon_plan.get("music_source") or "none").strip().lower()
        notes.append(
            {
                "addon": "music",
                "requested": True,
                "applied": bool(bgm_audio_path),
                "source": source,
                "reason": "" if bgm_audio_path else "music_default_missing_or_unavailable",
            }
        )
    if addon_plan.get("subtitle_enabled"):
        subtitle_source_ready = _has_user_facing_subtitle_text(job)
        notes.append(
            {
                "addon": "subtitle",
                "requested": True,
                "applied": bool(subtitle_source_ready),
                "source": str(addon_plan.get("subtitle_source") or ""),
                "reason": "" if subtitle_source_ready else "subtitle_source_missing",
            }
        )
    if addon_plan.get("logo_enabled"):
        notes.append({"addon": "logo", "requested": True, "applied": _logo_enabled(addon_plan), "source": str(addon_plan.get("logo_source") or "text")})
    return notes


def _local_composer_enabled(job: dict | None = None) -> bool:
    del job
    return _env_flag("REAL_VIDEO_LOCAL_COMPOSER_FALLBACK_ENABLED", "1")


def _ffmpeg_binary() -> str:
    configured = str(os.getenv("FFMPEG_PATH") or os.getenv("LOCAL_FFMPEG_PATH") or "").strip()
    if configured and (os.path.isfile(configured) or shutil.which(configured)):
        return configured
    return shutil.which("ffmpeg") or ""


def _canvas_size(aspect_ratio: str) -> tuple[int, int]:
    value = str(aspect_ratio or "9:16").strip()
    if value == "16:9":
        return 960, 540
    if value == "1:1":
        return 720, 720
    return 540, 960


def _ffmpeg_text(value: Any, limit: int = 320) -> str:
    text = _safe_text(value, limit)
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def _scene_color(scene_id: int) -> str:
    palette = ("0b1f3a", "163b2f", "40213a", "1f3344", "3b2f16", "24351f")
    return palette[(max(1, int(scene_id or 1)) - 1) % len(palette)]


def _render_local_composer_scene(scene, raw_path: str) -> dict:
    ffmpeg = _ffmpeg_binary()
    if not ffmpeg:
        raise RealVideoRenderError("ffmpeg_missing")
    scene_id = _safe_int(getattr(scene, "scene_id", 1), 1)
    duration = max(1.0, min(8.0, float(getattr(scene, "target_duration_sec", 6.0) or 6.0)))
    width, height = _canvas_size(str(getattr(scene, "aspect_ratio", "") or "9:16"))
    target = os.path.abspath(raw_path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    color = _scene_color(scene_id)
    fade_out = max(0.1, duration - 0.3)
    primary_filter = (
        f"scale={width}:{height},"
        "format=yuv420p,"
        f"drawbox=x=36:y=36:w=iw-72:h=ih-72:color=white@0.08:t=4,"
        f"fade=t=in:st=0:d=0.25,fade=t=out:st={fade_out:.3f}:d=0.25"
    )
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x{color}:s={width}x{height}:r=30:d={duration:.3f}",
        "-vf",
        primary_filter,
        "-t",
        f"{duration:.3f}",
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
        target,
    ]
    result = safe_run_ffmpeg(cmd, timeout=max(60, int(duration * 30)))
    if result.returncode != 0:
        fallback = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x{color}:s={width}x{height}:r=30:d={duration:.3f}",
            "-vf",
            "format=yuv420p",
            "-t",
            f"{duration:.3f}",
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
            target,
        ]
        result = safe_run_ffmpeg(fallback, timeout=max(60, int(duration * 30)))
    if result.returncode != 0:
        raise RealVideoRenderError("local_composer_ffmpeg_failed")
    return {"ok": True, "provider": "local_scene_composer", "output_path": ensure_video_output(target)}


def _render_local_scene_card_scene(scene, raw_path: str) -> dict:
    ffmpeg = _ffmpeg_binary()
    if not ffmpeg:
        raise RealVideoRenderError("ffmpeg_missing")
    scene_id = _safe_int(getattr(scene, "scene_id", 1), 1)
    duration = max(1.0, min(8.0, float(getattr(scene, "target_duration_sec", 6.0) or 6.0)))
    width, height = _canvas_size(str(getattr(scene, "aspect_ratio", "") or "9:16"))
    target = os.path.abspath(raw_path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    palette = (
        ("10233f", "32d3c8", "f5c542"),
        ("183428", "9af06a", "60a5fa"),
        ("321b36", "f472b6", "facc15"),
        ("1f2a44", "38bdf8", "f97316"),
        ("2b2615", "f59e0b", "22c55e"),
        ("1f2f25", "a3e635", "e879f9"),
    )
    base, accent, glow = palette[(max(1, scene_id) - 1) % len(palette)]
    fade_out = max(0.1, duration - 0.3)
    filter_graph = (
        "format=yuv420p,"
        f"drawbox=x=0:y=0:w=iw:h=ih:color=0x{base}@1.0:t=fill,"
        f"drawbox=x=iw*0.08:y=ih*0.10:w=iw*0.42:h=ih*0.26:color=0x{accent}@0.28:t=fill,"
        f"drawbox=x=iw*0.18:y=ih*0.46:w=iw*0.62:h=ih*0.12:color=white@0.10:t=fill,"
        f"drawbox=x=iw*0.52:y=ih*0.64:w=iw*0.34:h=ih*0.20:color=0x{glow}@0.22:t=fill,"
        "drawbox=x=24:y=24:w=iw-48:h=ih-48:color=white@0.08:t=3,"
        f"fade=t=in:st=0:d=0.25,fade=t=out:st={fade_out:.3f}:d=0.25"
    )
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x{base}:s={width}x{height}:r=30:d={duration:.3f}",
        "-vf",
        filter_graph,
        "-t",
        f"{duration:.3f}",
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
        target,
    ]
    result = safe_run_ffmpeg(cmd, timeout=max(60, int(duration * 30)))
    if result.returncode != 0:
        fallback = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x{base}:s={width}x{height}:r=30:d={duration:.3f}",
            "-vf",
            "format=yuv420p,drawbox=x=24:y=24:w=iw-48:h=ih-48:color=white@0.08:t=3",
            "-t",
            f"{duration:.3f}",
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
            target,
        ]
        result = safe_run_ffmpeg(fallback, timeout=max(60, int(duration * 30)))
    if result.returncode != 0:
        raise RealVideoRenderError("local_scene_card_ffmpeg_failed")
    return {"ok": True, "provider": "local_scene_card", "output_path": ensure_video_output(target)}


def build_local_scene_composer(job: dict | None = None):
    del job

    def _render(scene, raw_path: str):
        return _render_local_composer_scene(scene, raw_path)

    return _render


def build_local_scene_card_renderer(job: dict | None = None):
    del job

    def _render(scene, raw_path: str):
        return _render_local_scene_card_scene(scene, raw_path)

    return _render


def _default_bgm_path(addon_plan: dict, workspace: str, duration_seconds: float) -> str | None:
    if not addon_plan.get("music_enabled"):
        return None
    source = str(addon_plan.get("music_source") or "none").strip().lower()
    if source in {"none", "off", "disabled", ""}:
        return None
    explicit = str(addon_plan.get("music_path") or addon_plan.get("music_audio_path") or addon_plan.get("bgm_audio_path") or "").strip()
    if explicit and os.path.isfile(explicit) and os.path.getsize(explicit) > 0:
        return explicit
    if source not in {"default", "saved", "vault", "system"}:
        return None
    ffmpeg = _ffmpeg_binary()
    if not ffmpeg:
        return None
    os.makedirs(workspace, exist_ok=True)
    duration = max(1.0, min(180.0, float(duration_seconds or 6.0)))
    volume = max(0.0, min(1.0, _safe_int(addon_plan.get("music_volume_percent"), 30) / 100.0))
    output = os.path.join(workspace, "default_bgm.m4a")
    result = safe_run_ffmpeg(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=220:sample_rate=44100:duration={duration:.3f}",
            "-filter:a",
            f"volume={max(0.01, volume * 0.12):.3f}",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            output,
        ],
        timeout=max(60, int(duration * 2)),
    )
    if result.returncode != 0:
        return None
    try:
        return ensure_video_output(output)
    except RuntimeError:
        return None


def _run_multiscene_render(job: dict, workspace: str, *, render_video_func, bgm_audio_path: str | None = None) -> dict:
    addon = _addon_plan(job)
    subtitle_requested = bool(addon.get("subtitle_enabled", True))
    subtitle_enabled = bool(subtitle_requested and _has_user_facing_subtitle_text(job))
    return process_multiscene_video_pipeline(
        user_id=str(job.get("user_id") or ""),
        job_id=str(job.get("job_id") or job.get("id") or int(time.time())),
        user_prompt=original_prompt_from_job(job),
        workspace_dir=workspace,
        render_video_func=render_video_func,
        llm_func=real_video_llm_func_from_job(job),
        max_scenes=_scene_count(job),
        default_scene_duration=6.0,
        aspect_ratio=_aspect_ratio(job),
        enable_voice=False,
        bgm_audio_path=bgm_audio_path,
        enable_subtitle=subtitle_enabled,
        enable_logo=_logo_enabled(addon),
        logo_text=str(addon.get("logo_text") or ""),
        logo_position=str(addon.get("logo_position") or "bottom_right"),
    )


def render_real_video_job(job: dict, work_dir: str) -> dict:
    addon = _addon_plan(job)
    workspace = os.path.abspath(work_dir)
    total_duration = max(1.0, float(_safe_int(job.get("expected_duration_seconds") or _scene_count(job) * 6, _scene_count(job) * 6)))
    bgm_audio_path = _default_bgm_path(addon, workspace, total_duration)
    degrade_notes = _addon_degrade_notes(addon, bgm_audio_path=bgm_audio_path, job=job)
    readiness = real_video_provider_readiness(job)
    is_product_video = bool(str(job.get("source") or "") == "product_video" or job.get("product_video"))
    product_type = _product_type(job)
    product_route = video_final_output.route_for_product_type(product_type)
    required_capability = str(product_route.get("provider_capability") or "text_to_video")
    fallback_capability = str(product_route.get("fallback_capability") or "")
    render_mode = str(job.get("render_mode") or "").strip().lower().replace("-", "_")
    test_pattern = bool(job.get("test_pattern") or job.get("admin_video_delivery"))
    provider_call_requested = bool(job.get("provider_call") or job.get("real_renderer_required") or product_type == "video_ai_prompt")
    result: dict[str, Any] = {}
    provider_attempted = False
    provider_events: list[dict[str, Any]] = []
    provider_error = ""
    fallback_used = False
    fallback_reason = ""
    provider_candidates = _provider_candidates_for_capability(readiness, required_capability)
    force_product_provider_route = bool(
        is_product_video
        and render_mode == "real"
        and not test_pattern
        and provider_call_requested
        and required_capability in PROVIDER_REQUIRED_CAPABILITIES
    )
    route_requires_provider = bool(
        is_product_video
        and (
            force_product_provider_route
            or _route_requires_provider(
                product_type,
                required_capability,
                fallback_capability,
                provider_ready=bool(provider_candidates),
            )
        )
    )
    provider_route_selected = bool(provider_candidates) if route_requires_provider else bool(readiness.get("ok"))
    local_fallback_allowed = not route_requires_provider
    local_image_sequence_used = False
    local_scene_card_used = False

    def _base_diagnostics(payload: dict[str, Any] | None = None, *, error: str = "") -> dict[str, Any]:
        data = dict(payload or {})
        if error:
            data.setdefault("error", error)
        data["provider_attempted"] = bool(provider_attempted)
        data["provider_route_selected"] = bool(provider_route_selected)
        data["fallback_used"] = bool(fallback_used or data.get("fallback_used"))
        data["fallback_reason"] = str(data.get("fallback_reason") or fallback_reason or "")
        data["provider_events"] = data.get("provider_events") or provider_events
        data["provider_task_ids"] = data.get("provider_task_ids") or [item.get("task_id") for item in provider_events if item.get("task_id")]
        data["provider_video_ids"] = data.get("provider_video_ids") or [item.get("video_id") for item in provider_events if item.get("video_id")]
        data["provider_models"] = data.get("provider_models") or [item.get("model") for item in provider_events if item.get("model")]
        data["provider_modes"] = data.get("provider_modes") or [item.get("mode") for item in provider_events if item.get("mode")]
        data["chunk_count"] = data.get("chunk_count") or _scene_count(job)
        data["downloaded_clip_paths"] = data.get("downloaded_clip_paths") or list(data.get("created_files") or [])[:80]
        data["stitch_attempted"] = bool(data.get("master_video_path") or data.get("final_video_path") or data.get("stitch_attempted"))
        data["provider_status"] = str(
            data.get("provider_status")
            or ("downloaded" if provider_events else ("attempted" if provider_attempted else "not_attempted"))
        )
        effective_provider_error = str(data.get("provider_error") or provider_error or "")
        if provider_attempted and not data["provider_task_ids"] and not effective_provider_error:
            effective_provider_error = str(data.get("error") or data.get("visual_classification") or "provider_attempt_no_artifact")
        data["provider_error"] = effective_provider_error
        data["provider_order"] = _provider_order(job)
        data["required_capability"] = required_capability
        data["required_capability_original"] = str(data.get("required_capability_original") or required_capability)
        data["normalized_capability_candidates"] = list(
            data.get("normalized_capability_candidates") or capability_options(required_capability)
        )
        data["fallback_capability"] = fallback_capability
        data["route_requires_provider"] = bool(route_requires_provider)
        data["local_fallback_allowed"] = bool(local_fallback_allowed)
        data["provider_router_called"] = bool(route_requires_provider or provider_attempted or data.get("provider_router_called"))
        data["provider_candidates_count"] = int(data.get("provider_candidates_count") or len(provider_candidates))
        data["selected_provider"] = str(
            data.get("selected_provider")
            or data.get("provider")
            or (provider_events[0].get("provider") if provider_events else "")
            or (provider_candidates[0] if provider_candidates else "")
        )
        data["provider_selection_blocker"] = str(
            data.get("provider_selection_blocker")
            or ("" if provider_candidates else ("provider_capability_missing" if route_requires_provider else ""))
        )
        data["provider_submit_called"] = bool(data.get("provider_submit_called") or provider_attempted)
        data["provider_submit_http_status"] = data.get("provider_submit_http_status") or data.get("provider_http_status") or 0
        data["provider_task_id_saved"] = bool(data.get("provider_task_id_saved") or data["provider_task_ids"])
        data["provider_poll_called"] = bool(data.get("provider_poll_called") or provider_attempted)
        data["provider_result_url_present"] = bool(
            data.get("provider_result_url_present")
            or data.get("result_url_present")
            or any((item or {}).get("download_url_present") for item in provider_events if isinstance(item, dict))
        )
        if not data.get("connector_renderer") and (route_requires_provider or provider_attempted):
            data["connector_renderer"] = PROVIDER_BRIDGE_RENDERER
        if not data.get("renderer") and (route_requires_provider or provider_attempted):
            data["renderer"] = PROVIDER_SCENE_RENDERER
        data["continue_polling"] = bool(data.get("continue_polling"))
        data["normalized_provider_status"] = str(data.get("normalized_provider_status") or data.get("provider_status") or "")
        data["base_video_source"] = str(
            data.get("base_video_source")
            or (
                PROVIDER_VIDEO_SOURCE
                if data.get("visual_source") == VISUAL_SOURCE_PROVIDER_MP4 or data.get("provider_task_ids")
                else ("placeholder" if data.get("visual_source") == VISUAL_SOURCE_LOCAL_PLACEHOLDER else ("local" if data.get("visual_source") else ""))
            )
        )
        data["visual_source"] = str(data.get("visual_source") or ("provider_pending" if provider_attempted else ""))
        data["placeholder_detected"] = bool(data.get("placeholder_detected") or False)
        data["placeholder_visual"] = bool(data.get("placeholder_visual") or False)
        data["placeholder_forbidden"] = bool(route_requires_provider)
        data["fallback_policy"] = fallback_capability
        data["provider_readiness"] = {
            "ok": bool(readiness.get("ok")),
            "ready_provider_order": readiness.get("ready_provider_order") or [],
            "first_ready_provider": readiness.get("first_ready_provider") or "",
            "enabled_count": readiness.get("enabled_count") or 0,
            "configured_count": readiness.get("configured_count") or 0,
            "enabled_providers": readiness.get("enabled_providers") or [],
            "configured_providers": readiness.get("configured_providers") or [],
            "missing_env": readiness.get("missing_env") or {},
        }
        data["enabled_providers"] = readiness.get("enabled_providers") or []
        data["configured_providers"] = readiness.get("configured_providers") or []
        data["missing_env"] = readiness.get("missing_env") or {}
        data["original_user_prompt"] = original_prompt_from_job(job)
        data["addon_degrade_notes"] = degrade_notes
        data["partial_addons"] = any(item.get("requested") and not item.get("applied") for item in degrade_notes)
        data["voice_requested"] = bool(addon.get("voice_enabled"))
        data["music_requested"] = bool(addon.get("music_enabled"))
        data["subtitle_requested"] = bool(addon.get("subtitle_enabled"))
        data["subtitle_user_facing_source"] = bool(_has_user_facing_subtitle_text(job))
        data["logo_requested"] = bool(addon.get("logo_enabled"))
        if bgm_audio_path:
            data["bgm_audio_path"] = bgm_audio_path
        return _record_render_diagnostics(data)

    def _raise_render_error(reason: str, payload: dict[str, Any] | None = None) -> None:
        data = _base_diagnostics(payload, error=reason or REAL_VIDEO_RENDER_UNAVAILABLE)
        if is_product_video:
            data["no_charge"] = True
        if reason == FAILED_NO_REAL_VISUAL:
            data["visual_classification"] = FAILED_NO_REAL_VISUAL
            data["final_classification"] = FAILED_NO_REAL_VISUAL
        if reason == "provider_capability_missing":
            data["blocker"] = "provider_capability_missing"
            data["provider_error"] = "provider_capability_missing"
            data["provider_status"] = "not_attempted"
            data["provider_attempted"] = False
            data["public_message"] = PUBLIC_NO_VIDEO_PROVIDER_COPY
        raise RealVideoRenderError(reason or REAL_VIDEO_RENDER_UNAVAILABLE, diagnostics=data)

    local_image_paths = _local_image_sequence_paths(job) if is_product_video else []
    if is_product_video and _local_image_sequence_allowed(job, local_image_paths) and local_fallback_allowed:
        local_image_sequence_used = True
        local_workspace = os.path.join(workspace, "local_image_sequence")
        local_output = os.path.join(local_workspace, "final_output.mp4")
        result = video_final_output.render_local_image_sequence_video(
            local_image_paths,
            local_output,
            aspect_ratio=_aspect_ratio(job),
            duration_per_image=max(1.0, min(8.0, total_duration / max(1, len(local_image_paths)))),
            audio_path=_local_addon_audio_path(job) or bgm_audio_path or "",
            ffmpeg=_ffmpeg_binary(),
        )
        if not result.get("ok"):
            _raise_render_error(str(result.get("error") or "local_image_sequence_failed"), result)
        result["renderer"] = LOCAL_IMAGE_SEQUENCE_RENDERER
        result["provider_attempted"] = False
        result["provider_route_selected"] = False
        result["provider_events"] = []
        result["provider_task_ids"] = []
        result["provider_video_ids"] = []
        result["provider_models"] = []
        result["provider_modes"] = []
        result["provider_status"] = "not_needed"
        result["provider_error"] = ""
        result["fallback_used"] = False
        result["fallback_reason"] = ""
        result["visual_source"] = VISUAL_SOURCE_LOCAL_IMAGE_SEQUENCE
        result["base_video_source"] = "local"
        result["connector_renderer"] = LOCAL_IMAGE_SEQUENCE_RENDERER
        result["placeholder_detected"] = False
        result["placeholder_visual"] = False
        result["raw_prompt_burned_into_frame"] = False
        result["visual_classification"] = FINAL_AI_VIDEO
        result["final_classification"] = FINAL_AI_VIDEO
        result["no_charge"] = bool(job.get("no_charge"))
    elif is_product_video and not readiness.get("ok") and fallback_capability in {
        "clean_fail_provider_capability_missing",
        "delegate_or_clean_fail",
    }:
        provider_error = "provider_capability_missing"
        _raise_render_error(
            "provider_capability_missing",
            {
                "ok": False,
                "blocker": "provider_capability_missing",
                "provider_error": "provider_capability_missing",
                "provider_status": "not_attempted",
                "provider_attempted": False,
                "provider_readiness": readiness,
                "public_message": PUBLIC_NO_VIDEO_PROVIDER_COPY,
                "progress_percent": 40,
                "no_charge": True,
            },
        )
    elif readiness.get("ok") or not is_product_video:
        provider_attempted = True
        try:
            result = _run_multiscene_render(
                job,
                workspace,
                render_video_func=build_real_scene_renderer(job, provider_events),
                bgm_audio_path=bgm_audio_path,
            )
        except RealVideoRenderError as exc:
            provider_error = str(exc) or REAL_VIDEO_RENDER_UNAVAILABLE
            result = dict(getattr(exc, "diagnostics", {}) or {})
            result["ok"] = False
            result["error"] = provider_error
        except Exception as exc:
            provider_error = f"provider_render_failed:{type(exc).__name__}"
            result = {"ok": False, "error": provider_error}
        if not result.get("ok"):
            provider_error = str(result.get("error") or provider_error or REAL_VIDEO_RENDER_UNAVAILABLE)
    elif is_product_video:
        provider_error = str(readiness.get("reason") or "provider_capability_missing")
    if is_product_video and route_requires_provider and (not result or not result.get("ok")):
        blocker = str((result or {}).get("blocker") or (result or {}).get("provider_error") or provider_error or REAL_VIDEO_RENDER_UNAVAILABLE)
        if blocker == REAL_VIDEO_RENDER_UNAVAILABLE and not provider_candidates:
            blocker = "provider_capability_missing"
        _raise_render_error(blocker, result or {"ok": False, "provider_error": blocker, "provider_status": "failed" if provider_attempted else "not_attempted"})
    if is_product_video and not local_image_sequence_used and (not result or not result.get("ok")) and local_fallback_allowed and _local_scene_card_allowed(job):
        local_scene_card_used = True
        local_workspace = os.path.join(workspace, "local_scene_card")
        fallback_used = True
        fallback_reason = provider_error or "provider_unavailable"
        try:
            result = _run_multiscene_render(job, local_workspace, render_video_func=build_local_scene_card_renderer(job), bgm_audio_path=bgm_audio_path)
        except RealVideoRenderError as exc:
            _raise_render_error(str(exc) or REAL_VIDEO_RENDER_UNAVAILABLE, dict(getattr(exc, "diagnostics", {}) or {}))
        result["renderer"] = LOCAL_SCENE_CARD_RENDERER
        result["provider_attempted"] = bool(provider_attempted)
        result["provider_route_selected"] = bool(provider_route_selected)
        result["provider_events"] = provider_events
        result["provider_task_ids"] = [item.get("task_id") for item in provider_events if item.get("task_id")]
        result["provider_video_ids"] = [item.get("video_id") for item in provider_events if item.get("video_id")]
        result["provider_models"] = [item.get("model") for item in provider_events if item.get("model")]
        result["provider_modes"] = [item.get("mode") for item in provider_events if item.get("mode")]
        result["provider_status"] = "downloaded" if provider_events else ("attempted" if provider_attempted else "not_needed")
        result["provider_error"] = provider_error
        result["fallback_used"] = True
        result["fallback_reason"] = fallback_reason
        result["visual_source"] = VISUAL_SOURCE_LOCAL_SCENE_CARD
        result["base_video_source"] = "local"
        result["connector_renderer"] = LOCAL_SCENE_CARD_RENDERER
        result["placeholder_detected"] = False
        result["placeholder_visual"] = False
        result["raw_prompt_burned_into_frame"] = _subtitle_raw_prompt_burn_detected(job, result)
        result["visual_classification"] = FINAL_AI_VIDEO if result.get("ok") and not result["raw_prompt_burned_into_frame"] else FAILED_NO_REAL_VISUAL
        result["final_classification"] = result["visual_classification"]
        result["no_charge"] = bool(job.get("no_charge"))
    if is_product_video and not local_image_sequence_used and (not result or not result.get("ok")) and local_fallback_allowed and _local_composer_enabled(job):
        local_workspace = os.path.join(workspace, "local_composer")
        fallback_used = True
        fallback_reason = provider_error or "provider_unavailable"
        try:
            result = _run_multiscene_render(job, local_workspace, render_video_func=build_local_scene_composer(job), bgm_audio_path=bgm_audio_path)
        except RealVideoRenderError as exc:
            _raise_render_error(str(exc) or REAL_VIDEO_RENDER_UNAVAILABLE, dict(getattr(exc, "diagnostics", {}) or {}))
        result["renderer"] = LOCAL_PLACEHOLDER_RENDERER
        result["provider_attempted"] = bool(provider_attempted)
        result["provider_route_selected"] = bool(provider_route_selected)
        result["provider_events"] = provider_events
        result["provider_task_ids"] = [item.get("task_id") for item in provider_events if item.get("task_id")]
        result["provider_video_ids"] = [item.get("video_id") for item in provider_events if item.get("video_id")]
        result["provider_models"] = [item.get("model") for item in provider_events if item.get("model")]
        result["provider_modes"] = [item.get("mode") for item in provider_events if item.get("mode")]
        result["provider_status"] = "downloaded" if provider_events else ("attempted" if provider_attempted else "not_attempted")
        result["provider_error"] = provider_error
        result["fallback_used"] = True
        result["fallback_reason"] = fallback_reason
        result["visual_source"] = VISUAL_SOURCE_LOCAL_PLACEHOLDER
        result["base_video_source"] = "placeholder"
        result["connector_renderer"] = LOCAL_PLACEHOLDER_RENDERER
        result["placeholder_detected"] = True
        result["placeholder_visual"] = True
        result["raw_prompt_burned_into_frame"] = _subtitle_raw_prompt_burn_detected(job, result)
        result["visual_classification"] = PARTIAL_SIMPLE_VIDEO if result.get("ok") and not result["raw_prompt_burned_into_frame"] else FAILED_NO_REAL_VISUAL
        result["final_classification"] = result["visual_classification"]
        result["no_charge"] = True
    elif result and not local_image_sequence_used and not local_scene_card_used:
        result["renderer"] = PROVIDER_SCENE_RENDERER
        result["connector_renderer"] = PROVIDER_BRIDGE_RENDERER
        result["provider_attempted"] = bool(provider_attempted)
        result["provider_route_selected"] = bool(provider_route_selected)
        result["fallback_used"] = False
        result["fallback_reason"] = ""
        result["provider_events"] = provider_events
        result["provider_task_ids"] = [item.get("task_id") for item in provider_events if item.get("task_id")]
        result["provider_video_ids"] = [item.get("video_id") for item in provider_events if item.get("video_id")]
        result["provider_models"] = [item.get("model") for item in provider_events if item.get("model")]
        result["provider_modes"] = [item.get("mode") for item in provider_events if item.get("mode")]
        result["provider_status"] = "downloaded" if provider_events else ("attempted" if provider_attempted else "not_attempted")
        result["provider_error"] = provider_error
        result["visual_source"] = VISUAL_SOURCE_PROVIDER_MP4
        result["base_video_source"] = PROVIDER_VIDEO_SOURCE
        result["placeholder_detected"] = False
        result["placeholder_visual"] = False
        result["raw_prompt_burned_into_frame"] = _subtitle_raw_prompt_burn_detected(job, result)
        result["visual_classification"] = FINAL_AI_VIDEO if result.get("ok") and not result["raw_prompt_burned_into_frame"] else FAILED_NO_REAL_VISUAL
        result["final_classification"] = result["visual_classification"]
    final_path = str(result.get("final_video_path") or "")
    if not result.get("ok") or not final_path or not os.path.exists(final_path) or os.path.getsize(final_path) <= 0:
        _raise_render_error(str(result.get("error") or provider_error or REAL_VIDEO_RENDER_UNAVAILABLE), result)
    if is_product_video and result.get("visual_classification") == FAILED_NO_REAL_VISUAL:
        _raise_render_error(FAILED_NO_REAL_VISUAL, result)
    probe = video_final_output.probe_video(final_path)
    if probe.get("ok"):
        result["output_bytes"] = int(probe.get("bytes") or 0)
        result["output_duration"] = float(probe.get("duration") or 0)
        result["has_video"] = bool(probe.get("has_video"))
        result["has_audio"] = bool(probe.get("has_audio"))
        result["validation_status"] = "candidate_mp4_valid"
    else:
        result["validation_status"] = str(probe.get("reason") or "candidate_mp4_probe_failed")
    if addon.get("music_enabled") and not result.get("has_audio"):
        for note in degrade_notes:
            if note.get("addon") == "music":
                note["applied"] = False
                note["reason"] = "music_mux_missing_audio_stream"
                break
    result["provider_order"] = _provider_order(job)
    result["provider_readiness"] = {"ok": bool(readiness.get("ok")), "ready_provider_order": readiness.get("ready_provider_order") or []}
    result["required_capability"] = required_capability
    result["required_capability_original"] = str(result.get("required_capability_original") or required_capability)
    result["normalized_capability_candidates"] = list(
        result.get("normalized_capability_candidates") or capability_options(required_capability)
    )
    result["fallback_capability"] = fallback_capability
    result["route_requires_provider"] = bool(route_requires_provider)
    result["local_fallback_allowed"] = bool(local_fallback_allowed)
    result["provider_router_called"] = bool(route_requires_provider or provider_attempted or result.get("provider_router_called"))
    result["provider_candidates_count"] = int(result.get("provider_candidates_count") or len(provider_candidates))
    result["selected_provider"] = str(
        result.get("selected_provider")
        or result.get("provider")
        or (provider_events[0].get("provider") if provider_events else "")
        or (provider_candidates[0] if provider_candidates else "")
    )
    result["provider_selection_blocker"] = str(
        result.get("provider_selection_blocker")
        or ("" if provider_candidates else ("provider_capability_missing" if route_requires_provider else ""))
    )
    result["provider_submit_called"] = bool(result.get("provider_submit_called") or provider_attempted)
    result["provider_submit_http_status"] = result.get("provider_submit_http_status") or result.get("provider_http_status") or 0
    result["provider_task_id_saved"] = bool(result.get("provider_task_id_saved") or result.get("provider_task_ids"))
    result["provider_poll_called"] = bool(result.get("provider_poll_called") or provider_attempted)
    result["provider_result_url_present"] = bool(
        result.get("provider_result_url_present")
        or result.get("result_url_present")
        or any((item or {}).get("download_url_present") for item in provider_events if isinstance(item, dict))
    )
    result["continue_polling"] = bool(result.get("continue_polling"))
    result["normalized_provider_status"] = str(result.get("normalized_provider_status") or result.get("provider_status") or "")
    result["base_video_source"] = str(
        result.get("base_video_source")
        or (
            PROVIDER_VIDEO_SOURCE
            if result.get("visual_source") == VISUAL_SOURCE_PROVIDER_MP4 or result.get("provider_task_ids")
            else ("placeholder" if result.get("visual_source") == VISUAL_SOURCE_LOCAL_PLACEHOLDER else "local")
        )
    )
    result["placeholder_forbidden"] = bool(route_requires_provider)
    result["fallback_policy"] = fallback_capability
    result["original_user_prompt"] = original_prompt_from_job(job)
    result["addon_degrade_notes"] = degrade_notes
    result["partial_addons"] = any(item.get("requested") and not item.get("applied") for item in degrade_notes)
    result["voice_requested"] = bool(addon.get("voice_enabled"))
    result["music_requested"] = bool(addon.get("music_enabled"))
    result["subtitle_requested"] = bool(addon.get("subtitle_enabled"))
    result["subtitle_user_facing_source"] = bool(_has_user_facing_subtitle_text(job))
    result["logo_requested"] = bool(addon.get("logo_enabled"))
    if bgm_audio_path:
        result["bgm_audio_path"] = bgm_audio_path
    result["chunk_count"] = result.get("chunk_count") or _scene_count(job)
    result["downloaded_clip_paths"] = result.get("downloaded_clip_paths") or list(result.get("created_files") or [])[:80]
    result["stitch_attempted"] = bool(result.get("master_video_path") or result.get("final_video_path") or result.get("stitch_attempted"))
    result["visual_classification"] = classify_visual_result(result)
    result["final_classification"] = result["visual_classification"]
    if result["visual_classification"] != FINAL_AI_VIDEO:
        result["no_charge"] = True
    _record_render_diagnostics(result)
    return result
