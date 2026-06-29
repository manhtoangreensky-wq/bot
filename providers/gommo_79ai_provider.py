"""Gommo / 79AI video provider adapter.

This adapter is deliberately Telegram-free. It returns redacted diagnostics and
never logs or exposes the access token.
"""

from __future__ import annotations

import os
import re
import json
import shutil
import time
import urllib.request
from pathlib import Path
from typing import Any

import httpx


PROVIDER_NAME = "gommo_79ai"
DEFAULT_API_BASE = "https://api.gommo.net"
DEFAULT_DOMAIN = "79ai.net"
PENDING_STATUSES = {"PENDING", "ACTIVE", "PROCESSING", "IN_PROGRESS", "RUNNING", "QUEUED", "MEDIA_GENERATION_STATUS_PENDING", "MEDIA_GENERATION_STATUS_ACTIVE", "MEDIA_GENERATION_STATUS_PROCESSING"}
SUCCESS_STATUSES = {"SUCCESS", "SUCCESSFUL", "COMPLETED", "DONE", "FINISHED", "MEDIA_GENERATION_STATUS_SUCCESSFUL"}
FAILED_STATUSES = {"FAILED", "FAIL", "ERROR", "CANCELLED", "CANCELED", "MEDIA_GENERATION_STATUS_FAILED"}
VIDEO_URL_EXTENSIONS = (".mp4", ".mov", ".m4v", ".webm")


def _env(environ: dict[str, str] | None, name: str, default: str = "") -> str:
    source = environ if environ is not None else os.environ
    value = source.get(name)
    return default if value is None else str(value)


def _flag(value: Any, default: bool = False) -> bool:
    if value in (None, ""):
        return bool(default)
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _safe_text(value: Any, limit: int = 4000) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:limit]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return int(default)


def _join_url(base: str, path: str) -> str:
    base = str(base or DEFAULT_API_BASE).strip().rstrip("/")
    path = str(path or "").strip()
    if path.startswith(("http://", "https://")):
        return path
    return base + "/" + path.lstrip("/")


def _sdk_form_payload(payload: dict[str, Any]) -> dict[str, str]:
    """Match the observed SDK contract: form body, no empty fields, JSON objects."""
    form: dict[str, str] = {}
    for key, value in dict(payload or {}).items():
        clean_key = str(key or "").strip()
        if not clean_key:
            continue
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            form[clean_key] = "true" if value else "false"
            continue
        if isinstance(value, (dict, list, tuple)):
            if not value:
                continue
            form[clean_key] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            continue
        text = str(value).strip()
        if not text:
            continue
        form[clean_key] = text
    return form


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _first_dict(payload: Any, keys: tuple[str, ...]) -> dict:
    if not isinstance(payload, dict):
        return {}
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    data = payload.get("data")
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, dict):
                return value
    return payload


def _status_text(value: Any) -> str:
    return str(value or "").strip().upper()


def normalize_status(value: Any, *, has_download_url: bool = False) -> str:
    raw = _status_text(value)
    if has_download_url and raw not in FAILED_STATUSES:
        return "SUCCESS"
    if raw in SUCCESS_STATUSES or raw.endswith("_SUCCESSFUL"):
        return "SUCCESS"
    if raw in PENDING_STATUSES or raw.endswith("_PENDING") or raw.endswith("_ACTIVE") or raw.endswith("_PROCESSING"):
        return "IN_PROGRESS"
    if raw in FAILED_STATUSES or raw.endswith("_FAILED"):
        return "FAILED"
    return raw or ("SUCCESS" if has_download_url else "UNKNOWN")


def extract_download_url(payload: Any) -> str:
    candidates: list[str] = []
    for item in _walk(payload):
        for key in ("download_url", "downloadUrl", "video_url", "videoUrl", "output_url", "outputUrl", "file_url", "fileUrl"):
            raw = item.get(key)
            if isinstance(raw, str) and raw.strip():
                candidates.append(raw.strip())
        raw_url = item.get("url")
        if isinstance(raw_url, str):
            url = raw_url.strip()
            lowered = url.lower().split("?", 1)[0]
            status = _status_text(item.get("status"))
            if lowered.endswith(VIDEO_URL_EXTENSIONS) or status in {"FINISH", "FINISHED", "SUCCESS", "SUCCESSFUL"}:
                candidates.append(url)
    for url in candidates:
        if url.startswith(("http://", "https://")):
            return url
    return ""


def _extract_models(payload: Any) -> list[dict[str, Any]]:
    models: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in _walk(payload):
        model = str(item.get("model") or item.get("id_base") or item.get("id") or "").strip()
        name = str(item.get("name") or item.get("title") or item.get("modelName") or "").strip()
        if not (model or name):
            continue
        if not (item.get("server") or item.get("type") or item.get("ratios") or item.get("durations") or item.get("modes") or item.get("model")):
            continue
        key = model or name
        if key in seen:
            continue
        seen.add(key)
        models.append(dict(item))
    return models


def _list_values(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,|/ ]+", value) if item.strip()]
    return []


def _model_enabled(model: dict[str, Any]) -> bool:
    status = _status_text(model.get("status") or model.get("state") or model.get("enabled") or model.get("is_active"))
    if status in {"0", "FALSE", "OFF", "DISABLED", "PAUSED", "UNAVAILABLE", "INACTIVE"}:
        return False
    if model.get("disabled") is True or model.get("paused") is True:
        return False
    max_today = _safe_int(model.get("videoMaxToday"), 0)
    total_today = _safe_int(model.get("videoTotalToday"), -1)
    if max_today > 0 and total_today >= max_today:
        return False
    return True


def _nearest_duration(requested: int, supported: list[str], model_name: str = "") -> int:
    values = sorted({_safe_int(item, 0) for item in supported if _safe_int(item, 0) > 0})
    if not values:
        if "seedance" in model_name.lower():
            values = list(range(4, 16))
        elif "veo" in model_name.lower():
            values = [4, 6, 8]
        else:
            values = [6]
    requested = max(1, int(requested or 6))
    return min(values, key=lambda item: (abs(item - requested), item))


class Gommo79AIProvider:
    def __init__(self, environ: dict[str, str] | None = None, client: Any | None = None):
        self.environ = environ
        self.client = client
        self.access_token = _env(environ, "GOMMO_ACCESS_TOKEN", "").strip()
        self.domain = _env(environ, "GOMMO_DOMAIN", DEFAULT_DOMAIN).strip() or DEFAULT_DOMAIN
        self.api_base = _env(environ, "GOMMO_API_BASE", DEFAULT_API_BASE).strip() or DEFAULT_API_BASE
        self.enabled = _flag(_env(environ, "GOMMO_VIDEO_ENABLED", "false"), False)

    def is_ready(self) -> bool:
        return bool(self.enabled and self.access_token and self.domain and self.api_base)

    def readiness(self) -> dict[str, Any]:
        missing = []
        if not self.enabled:
            missing.append("video_enabled")
        if not self.access_token:
            missing.append("access_token")
        if not self.domain:
            missing.append("domain")
        if not self.api_base:
            missing.append("api_base")
        return {"ok": not missing, "provider": PROVIDER_NAME, "missing": missing}

    def redact_debug(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = dict(payload or {})
        for key in list(data):
            if "token" in str(key).lower() or "access" in str(key).lower():
                data[key] = "***"
        return data

    def _auth_payload(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {"access_token": self.access_token, "domain": self.domain}
        payload.update(dict(extra or {}))
        return payload

    def _post(self, endpoint: str, payload: dict[str, Any], timeout: float = 60.0) -> dict[str, Any]:
        url = _join_url(self.api_base, endpoint)
        form = _sdk_form_payload(payload)
        try:
            if self.client is not None:
                response = self.client.post(url, data=form, timeout=timeout)
            else:
                response = httpx.post(url, data=form, timeout=timeout)
            try:
                body = response.json()
            except Exception:
                body = {}
            if int(response.status_code) >= 400:
                return {"ok": False, "http_status": int(response.status_code), "payload": body, "error": _safe_text(body.get("message") or body.get("error") or f"http_{response.status_code}", 240)}
            return {"ok": True, "http_status": int(response.status_code), "payload": body}
        except Exception as exc:
            return {"ok": False, "http_status": 0, "payload": {}, "error": f"{type(exc).__name__}"}

    def list_models(self, type: str = "video") -> dict[str, Any]:
        response = self._post("/ai/models", self._auth_payload({"type": type}), timeout=45.0)
        if not response.get("ok"):
            return {"ok": False, "provider": PROVIDER_NAME, "models": [], "error": response.get("error") or "gommo_models_failed"}
        models = _extract_models(response.get("payload"))
        return {"ok": True, "provider": PROVIDER_NAME, "models": models}

    def pick_video_model(
        self,
        *,
        package: str = "basic",
        scenes: int = 1,
        duration: int = 6,
        aspect_ratio: str = "9:16",
        references: dict[str, Any] | None = None,
        models: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        del package, scenes, references
        model_list = models if models is not None else self.list_models("video").get("models", [])
        enabled = [dict(item) for item in model_list if _model_enabled(dict(item))]
        preferred = [
            _env(self.environ, "GOMMO_DEFAULT_VIDEO_MODEL", "seedance_20_pro_edit").strip() or "seedance_20_pro_edit",
            _env(self.environ, "GOMMO_FALLBACK_VIDEO_MODEL", "veo_3_1").strip() or "veo_3_1",
        ]
        selected: dict[str, Any] | None = None
        for wanted in preferred:
            for item in enabled:
                if str(item.get("model") or item.get("id_base") or item.get("id") or "").strip() == wanted:
                    selected = item
                    break
            if selected:
                break
        if not selected and enabled:
            selected = enabled[0]
        if not selected:
            return {"ok": False, "provider": PROVIDER_NAME, "error": "gommo_video_model_unavailable"}
        model_id = str(selected.get("model") or selected.get("id_base") or selected.get("id") or "").strip()
        ratios = _list_values(selected.get("ratios") or selected.get("ratio"))
        ratio = aspect_ratio if not ratios or aspect_ratio in ratios else ratios[0]
        resolutions = _list_values(selected.get("resolutions") or selected.get("resolution"))
        resolution = "720p" if not resolutions or "720p" in resolutions else resolutions[0]
        modes = _list_values(selected.get("modes") or selected.get("mode"))
        model_name = f"{model_id} {selected.get('name') or ''}"
        if "seedance" in model_name.lower():
            mode = "business_fast" if not modes or "business_fast" in modes else ("fast" if "fast" in modes else modes[0])
        else:
            mode = "fast" if not modes or "fast" in modes else modes[0]
        chosen_duration = _nearest_duration(duration, _list_values(selected.get("durations") or selected.get("duration")), model_name)
        return {
            "ok": True,
            "provider": PROVIDER_NAME,
            "model": model_id,
            "model_name": str(selected.get("name") or model_id),
            "mode": mode,
            "ratio": ratio,
            "resolution": resolution,
            "duration": chosen_duration,
            "raw_model": selected,
        }

    def upload_image(self, file_or_url: str) -> dict[str, Any]:
        data = str(file_or_url or "").strip()
        if not data:
            return {"ok": False, "provider": PROVIDER_NAME, "error": "upload_image_invalid_data"}
        response = self._post("/ai/image-upload", self._auth_payload({"data": data}), timeout=90.0)
        if not response.get("ok"):
            return {"ok": False, "provider": PROVIDER_NAME, "error": response.get("error") or "upload_image_failed"}
        info = _first_dict(response.get("payload"), ("imageInfo", "image", "data"))
        return {"ok": True, "provider": PROVIDER_NAME, "image_id": str(info.get("id_base") or info.get("id") or ""), "url": str(info.get("url") or info.get("download_url") or "")}

    def upload_video(self, file_or_url: str) -> dict[str, Any]:
        data = str(file_or_url or "").strip()
        if not data:
            return {"ok": False, "provider": PROVIDER_NAME, "error": "upload_video_invalid_data"}
        response = self._post("/ai/video-upload", self._auth_payload({"data": data}), timeout=120.0)
        if not response.get("ok"):
            return {"ok": False, "provider": PROVIDER_NAME, "error": response.get("error") or "upload_video_failed"}
        info = _first_dict(response.get("payload"), ("videoInfo", "video", "data"))
        return {"ok": True, "provider": PROVIDER_NAME, "video_id": str(info.get("id_base") or info.get("id") or ""), "url": str(info.get("url") or info.get("download_url") or "")}

    def create_video(
        self,
        *,
        prompt: str,
        model: str,
        ratio: str = "9:16",
        resolution: str = "720p",
        duration: int = 6,
        mode: str = "business_fast",
        count_tasks: int = 1,
        references: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = self._auth_payload(
            {
                "model": model,
                "prompt": _safe_text(prompt, 1800),
                "ratio": ratio,
                "resolution": resolution,
                "duration": int(duration or 6),
                "mode": mode,
                "countTasks": int(count_tasks or 1),
            }
        )
        for key, value in dict(references or {}).items():
            if value:
                payload[str(key)] = value
        response = self._post("/ai/create-video", payload, timeout=90.0)
        if not response.get("ok"):
            return {"ok": False, "provider": PROVIDER_NAME, "error": response.get("error") or "gommo_create_video_failed"}
        body = response.get("payload") or {}
        info = _first_dict(body, ("videoInfo", "video", "data"))
        video_id = str(body.get("id_base") or info.get("id_base") or info.get("id") or "").strip()
        task_id = str(info.get("task_id") or body.get("task_id") or video_id).strip()
        download_url = extract_download_url(body)
        status = normalize_status(info.get("status") or body.get("status"), has_download_url=bool(download_url))
        accepted = bool(video_id or task_id)
        return {
            "ok": accepted,
            "provider": PROVIDER_NAME,
            "video_id": video_id or task_id,
            "task_id": task_id or video_id,
            "status": status,
            "download_url": download_url,
            "model": str(info.get("model") or model),
            "mode": str(info.get("mode") or mode),
            "ratio": str(info.get("ratio") or ratio),
            "resolution": str(info.get("resolution") or resolution),
            "duration": _safe_int(info.get("duration") or duration, duration),
            "credit_fee": _safe_int(info.get("credit_fee") or body.get("credit_fee"), 0),
            "raw": self.redact_debug(body if isinstance(body, dict) else {}),
            "error": "" if accepted else "gommo_create_video_missing_id",
        }

    def check_video_status(self, video_id: str) -> dict[str, Any]:
        video_id = str(video_id or "").strip()
        if not video_id:
            return {"ok": False, "provider": PROVIDER_NAME, "error": "video_id_missing"}
        response = self._post("/ai/video", self._auth_payload({"videoId": video_id}), timeout=60.0)
        if not response.get("ok"):
            return {"ok": False, "provider": PROVIDER_NAME, "error": response.get("error") or "gommo_status_failed"}
        return self._normalize_video_payload(response.get("payload"), video_id=video_id)

    def list_videos(self, project_id: str = "") -> dict[str, Any]:
        payload = {"project_id": project_id} if project_id else {}
        response = self._post("/ai/videos", self._auth_payload(payload), timeout=60.0)
        if not response.get("ok"):
            return {"ok": False, "provider": PROVIDER_NAME, "videos": [], "error": response.get("error") or "gommo_list_videos_failed"}
        videos = [dict(item) for item in _walk(response.get("payload")) if isinstance(item, dict) and (item.get("id_base") or item.get("task_id") or item.get("download_url"))]
        return {"ok": True, "provider": PROVIDER_NAME, "videos": videos}

    def _normalize_video_payload(self, payload: Any, *, video_id: str = "") -> dict[str, Any]:
        info = _first_dict(payload, ("videoInfo", "video", "data"))
        download_url = extract_download_url(payload)
        status = normalize_status(info.get("status") or (payload or {}).get("status") if isinstance(payload, dict) else "", has_download_url=bool(download_url))
        return {
            "ok": True,
            "provider": PROVIDER_NAME,
            "video_id": str(info.get("id_base") or info.get("id") or video_id),
            "task_id": str(info.get("task_id") or video_id),
            "status": status,
            "download_url": download_url,
            "model": str(info.get("model") or ""),
            "mode": str(info.get("mode") or ""),
            "ratio": str(info.get("ratio") or ""),
            "resolution": str(info.get("resolution") or ""),
            "duration": _safe_int(info.get("duration"), 0),
            "credit_fee": _safe_int(info.get("credit_fee"), 0),
        }

    def poll_video_until_ready(self, video_id: str, *, max_attempts: int = 24, interval_seconds: float = 25.0, success_url_extra_attempts: int = 4) -> dict[str, Any]:
        last: dict[str, Any] = {}
        for attempt in range(1, max(1, int(max_attempts or 1)) + 1):
            if attempt > 1 and interval_seconds > 0:
                time.sleep(float(interval_seconds))
            last = self.check_video_status(video_id)
            status = normalize_status(last.get("status"), has_download_url=bool(last.get("download_url")))
            last["status"] = status
            if status == "SUCCESS" and last.get("download_url"):
                return last
            if status == "SUCCESS":
                for extra in range(max(0, int(success_url_extra_attempts or 0))):
                    if interval_seconds > 0:
                        time.sleep(float(interval_seconds))
                    extra_result = self.check_video_status(video_id)
                    extra_result["status"] = normalize_status(extra_result.get("status"), has_download_url=bool(extra_result.get("download_url")))
                    last = extra_result
                    if extra_result.get("download_url"):
                        return extra_result
                return last
            if status == "FAILED":
                return last
        last.setdefault("status", "IN_PROGRESS")
        last["timeout"] = True
        return last

    def download_video(self, download_url: str, destination: str) -> dict[str, Any]:
        url = str(download_url or "").strip()
        if not url:
            return {"ok": False, "provider": PROVIDER_NAME, "error": "download_url_missing"}
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with urllib.request.urlopen(url, timeout=180) as response:
                with target.open("wb") as handle:
                    shutil.copyfileobj(response, handle)
        except Exception as exc:
            return {"ok": False, "provider": PROVIDER_NAME, "error": f"download_failed:{type(exc).__name__}"}
        if not target.is_file() or target.stat().st_size <= 0:
            return {"ok": False, "provider": PROVIDER_NAME, "error": "download_empty"}
        return {"ok": True, "provider": PROVIDER_NAME, "path": str(target), "bytes": int(target.stat().st_size)}
