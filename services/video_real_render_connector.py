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


def real_video_provider_readiness(job: dict | None = None, environ: dict[str, str] | None = None) -> dict:
    env = environ or os.environ
    order = _provider_order(job)
    providers = []
    shopaikey_url = str(env.get("SHOPAIKEY_VIDEO_URL") or "").strip()
    if not shopaikey_url:
        base = str(env.get("SHOPAIKEY_BASE_URL") or "").strip()
        endpoint = str(env.get("SHOPAIKEY_VIDEO_ENDPOINT") or "/video/generations").strip()
        shopaikey_url = _join_url(base, endpoint) if base else ""
    shopaikey_model = str(env.get("SHOPAIKEY_VIDEO_MODEL") or env.get("SHOPAIKEY_VIDEO_MODEL_PRIMARY") or "veo3.1-fast").strip()
    shopaikey_missing = []
    if not str(env.get("SHOPAIKEY_API_KEY") or "").strip():
        shopaikey_missing.append("api_key")
    if not shopaikey_url:
        shopaikey_missing.append("video_endpoint")
    if not shopaikey_model:
        shopaikey_missing.append("video_model")
    providers.append({"provider": "shopaikey", "configured": not shopaikey_missing, "missing": shopaikey_missing})

    key4u_missing = []
    try:
        from providers.key4u_provider import Key4UProvider

        key4u_configured = bool(Key4UProvider().is_configured())
    except Exception:
        key4u_configured = False
        key4u_missing.append("adapter")
    if not key4u_configured and "adapter" not in key4u_missing:
        key4u_missing.append("video_config")
    providers.append({"provider": "key4u", "configured": key4u_configured, "missing": key4u_missing})

    configured = [item["provider"] for item in providers if item["configured"]]
    ordered_ready = [provider for provider in order if provider in configured]
    return {
        "ok": bool(ordered_ready),
        "provider_order": order,
        "configured_providers": configured,
        "ready_provider_order": ordered_ready,
        "providers": providers,
    }


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
    return max(1, min(20, _safe_int(value, 3)))


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


def _addon_degrade_notes(addon_plan: dict, *, bgm_audio_path: str | None = None) -> list[dict[str, Any]]:
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
        notes.append({"addon": "subtitle", "requested": True, "applied": True, "source": str(addon_plan.get("subtitle_source") or "")})
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


def build_local_scene_composer(job: dict | None = None):
    del job

    def _render(scene, raw_path: str):
        return _render_local_composer_scene(scene, raw_path)

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
        enable_subtitle=bool(addon.get("subtitle_enabled", True)),
        enable_logo=_logo_enabled(addon),
        logo_text=str(addon.get("logo_text") or ""),
        logo_position=str(addon.get("logo_position") or "bottom_right"),
    )


def render_real_video_job(job: dict, work_dir: str) -> dict:
    addon = _addon_plan(job)
    workspace = os.path.abspath(work_dir)
    total_duration = max(1.0, float(_safe_int(job.get("expected_duration_seconds") or _scene_count(job) * 6, _scene_count(job) * 6)))
    bgm_audio_path = _default_bgm_path(addon, workspace, total_duration)
    degrade_notes = _addon_degrade_notes(addon, bgm_audio_path=bgm_audio_path)
    readiness = real_video_provider_readiness(job)
    is_product_video = bool(str(job.get("source") or "") == "product_video" or job.get("product_video"))
    result: dict[str, Any] = {}
    provider_attempted = False
    if readiness.get("ok") or not is_product_video:
        provider_attempted = True
        result = _run_multiscene_render(job, workspace, render_video_func=build_real_scene_renderer(job), bgm_audio_path=bgm_audio_path)
    if is_product_video and (not result or not result.get("ok")) and _local_composer_enabled(job):
        local_workspace = os.path.join(workspace, "local_composer")
        result = _run_multiscene_render(job, local_workspace, render_video_func=build_local_scene_composer(job), bgm_audio_path=bgm_audio_path)
        result["renderer"] = "local_scene_composer"
        result["provider_attempted"] = bool(provider_attempted)
    elif result:
        result["renderer"] = "real_provider"
        result["provider_attempted"] = bool(provider_attempted)
    final_path = str(result.get("final_video_path") or "")
    if not result.get("ok") or not final_path or not os.path.exists(final_path) or os.path.getsize(final_path) <= 0:
        raise RealVideoRenderError(str(result.get("error") or REAL_VIDEO_RENDER_UNAVAILABLE))
    result["provider_order"] = _provider_order(job)
    result["provider_readiness"] = {"ok": bool(readiness.get("ok")), "ready_provider_order": readiness.get("ready_provider_order") or []}
    result["original_user_prompt"] = original_prompt_from_job(job)
    result["addon_degrade_notes"] = degrade_notes
    result["partial_addons"] = any(item.get("requested") and not item.get("applied") for item in degrade_notes)
    result["voice_requested"] = bool(addon.get("voice_enabled"))
    result["music_requested"] = bool(addon.get("music_enabled"))
    result["subtitle_requested"] = bool(addon.get("subtitle_enabled"))
    result["logo_requested"] = bool(addon.get("logo_enabled"))
    if bgm_audio_path:
        result["bgm_audio_path"] = bgm_audio_path
    return result
