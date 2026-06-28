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

from services.multiscene_video_pipeline import process_multiscene_video_pipeline


REAL_VIDEO_RENDER_UNAVAILABLE = "real_video_renderer_unavailable"


class RealVideoRenderError(RuntimeError):
    """Safe worker-facing render error."""


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


def _provider_order(job: dict | None = None) -> list[str]:
    job = dict(job or {})
    asset_pack = _json_loads(job.get("asset_pack"), {})
    if not asset_pack and isinstance(job.get("project"), dict):
        asset_pack = _json_loads((job.get("project") or {}).get("asset_pack_json"), {})
    raw = (
        job.get("provider_order")
        or asset_pack.get("provider_order")
        or os.environ.get("VIDEO_PROVIDER_ORDER")
        or "shopaikey,key4u"
    )
    if isinstance(raw, (list, tuple)):
        values = raw
    else:
        values = re.split(r"[,|>\s]+", str(raw or ""))
    result = []
    for item in values:
        provider = str(item or "").strip().lower()
        if provider in {"shopai", "shopaikey"}:
            provider = "shopaikey"
        elif provider in {"key4u", "k4u"}:
            provider = "key4u"
        else:
            continue
        if provider not in result:
            result.append(provider)
    return result or ["shopaikey", "key4u"]


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


def _scene_count(job: dict | None = None) -> int:
    job = dict(job or {})
    value = job.get("scene_count")
    if not value and isinstance(job.get("project"), dict):
        value = (job.get("project") or {}).get("scene_count")
    return max(1, min(5, _safe_int(value, 3)))


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


async def _submit_provider(provider: str, prompt: str, aspect_ratio: str) -> dict:
    if provider == "shopaikey":
        return await _submit_shopaikey(prompt, aspect_ratio)
    if provider == "key4u":
        return await _submit_key4u(prompt, aspect_ratio)
    return {"ok": False, "provider": provider, "error": "provider_unsupported"}


async def _poll_provider(provider: str, task_id: str) -> dict:
    if provider == "shopaikey":
        return await _poll_shopaikey(task_id)
    if provider == "key4u":
        return await _poll_key4u(task_id)
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
    prompt = _safe_text(getattr(scene, "video_prompt", "") or getattr(scene, "visual_prompt", ""), 1200)
    aspect_ratio = str(getattr(scene, "aspect_ratio", "") or "9:16")
    errors = []
    for provider in provider_order:
        submit = await _submit_provider(provider, prompt, aspect_ratio)
        if not submit.get("ok") or not submit.get("task_id"):
            errors.append(f"{provider}:{submit.get('error') or submit.get('status') or 'submit_failed'}")
            continue
        task_id = str(submit["task_id"])
        attempts = max(1, _env_int("REAL_VIDEO_POLL_MAX_ATTEMPTS", 24))
        interval = max(0, _env_int("REAL_VIDEO_POLL_INTERVAL_SECONDS", 25))
        last = {}
        for attempt in range(1, attempts + 1):
            if attempt > 1 and interval:
                await asyncio.sleep(interval)
            last = await _poll_provider(provider, task_id)
            output_url = str(last.get("output_url") or "").strip()
            status = str(last.get("status") or "").upper()
            if output_url:
                return {"ok": True, "provider": provider, "task_id": task_id, "output_path": _download_output(output_url, raw_path)}
            if status in {"FAILED", "FAIL", "ERROR", "CANCELLED", "CANCELED"}:
                errors.append(f"{provider}:poll_failed:{status}")
                break
        else:
            errors.append(f"{provider}:poll_timeout")
    raise RealVideoRenderError(";".join(errors) or REAL_VIDEO_RENDER_UNAVAILABLE)


def build_real_scene_renderer(job: dict | None = None):
    provider_order = _provider_order(job)

    def _render(scene, raw_path: str):
        return asyncio.run(_render_scene_async(scene, raw_path, provider_order))

    return _render


def _logo_enabled(addon_plan: dict) -> bool:
    return bool(addon_plan.get("logo_enabled") and _safe_text(addon_plan.get("logo_text"), 120))


def render_real_video_job(job: dict, work_dir: str) -> dict:
    addon = _addon_plan(job)
    if addon.get("voice_enabled"):
        raise RealVideoRenderError("voice_addon_connector_missing")
    if addon.get("music_enabled") and str(addon.get("music_source") or "none") not in {"none", ""}:
        raise RealVideoRenderError("music_addon_source_missing")
    workspace = os.path.abspath(work_dir)
    result = process_multiscene_video_pipeline(
        user_id=str(job.get("user_id") or ""),
        job_id=str(job.get("job_id") or job.get("id") or int(time.time())),
        user_prompt=original_prompt_from_job(job),
        workspace_dir=workspace,
        render_video_func=build_real_scene_renderer(job),
        llm_func=real_video_llm_func_from_job(job),
        max_scenes=_scene_count(job),
        default_scene_duration=6.0,
        aspect_ratio=_aspect_ratio(job),
        enable_voice=False,
        enable_subtitle=bool(addon.get("subtitle_enabled", True)),
        enable_logo=_logo_enabled(addon),
        logo_text=str(addon.get("logo_text") or ""),
        logo_position=str(addon.get("logo_position") or "bottom_right"),
    )
    final_path = str(result.get("final_video_path") or "")
    if not result.get("ok") or not final_path or not os.path.exists(final_path) or os.path.getsize(final_path) <= 0:
        raise RealVideoRenderError(str(result.get("error") or REAL_VIDEO_RENDER_UNAVAILABLE))
    result["provider_order"] = _provider_order(job)
    result["original_user_prompt"] = original_prompt_from_job(job)
    return result
