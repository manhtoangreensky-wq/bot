"""Generic HTTP video provider adapter.

The adapter is intentionally conservative: disabled until submit/poll URLs and
auth config are present. It supports API-compatible providers that expose
submit -> poll -> result_url without hardcoding a vendor-specific SDK.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from services.video_provider_base import (
    VideoArtifactResult,
    VideoGenerationRequest,
    VideoPollResult,
    VideoSubmitResult,
    materialize_video_url,
    normalize_provider_status,
)


def _safe_text(value: Any, limit: int = 4000) -> str:
    return str(value or "").strip()[:limit]


def _json_path(payload: Any, path: str) -> Any:
    current = payload
    for part in str(path or "").split("."):
        if not part:
            continue
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if 0 <= index < len(current) else None
        else:
            return None
    return current


def _first_value(payload: Any, keys: tuple[str, ...]) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in keys:
        value = _json_path(payload, key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


class GenericHttpVideoProvider:
    provider_name = "generic_http"

    def __init__(
        self,
        *,
        provider_name: str = "generic_http",
        enabled_env: str = "VIDEO_GENERIC_HTTP_ENABLED",
        submit_url_env: str = "VIDEO_GENERIC_HTTP_SUBMIT_URL",
        poll_url_env: str = "VIDEO_GENERIC_HTTP_POLL_URL",
        auth_header_name_env: str = "VIDEO_GENERIC_HTTP_AUTH_HEADER_NAME",
        auth_header_value_env: str = "VIDEO_GENERIC_HTTP_AUTH_HEADER_VALUE",
        result_field_env: str = "VIDEO_GENERIC_HTTP_RESULT_FIELD",
        model_env: str = "VIDEO_GENERIC_HTTP_MODEL",
        capabilities_env: str = "VIDEO_GENERIC_HTTP_CAPABILITIES",
        environ: dict[str, str] | None = None,
    ):
        self.provider_name = provider_name
        self.env = environ or os.environ
        self.enabled_env = enabled_env
        self.submit_url_env = submit_url_env
        self.poll_url_env = poll_url_env
        self.auth_header_name_env = auth_header_name_env
        self.auth_header_value_env = auth_header_value_env
        self.result_field_env = result_field_env
        self.model_env = model_env
        self.capabilities_env = capabilities_env

    def _enabled(self) -> bool:
        return str(self.env.get(self.enabled_env) or "").strip().lower() in {"1", "true", "yes", "on"}

    def _submit_url(self) -> str:
        return str(self.env.get(self.submit_url_env) or "").strip()

    def _poll_url(self) -> str:
        return str(self.env.get(self.poll_url_env) or "").strip()

    def _auth_header(self) -> tuple[str, str]:
        return str(self.env.get(self.auth_header_name_env) or "").strip(), str(self.env.get(self.auth_header_value_env) or "").strip()

    def _configured(self) -> bool:
        name, value = self._auth_header()
        return bool(self._enabled() and self._submit_url() and self._poll_url() and name and value)

    def _capability_list(self) -> list[str]:
        raw = str(self.env.get(self.capabilities_env) or "text_to_video,image_to_video,video_to_video,multi_scene_video,scene_video")
        result = []
        for item in raw.replace("|", ",").split(","):
            token = item.strip()
            if token and token not in result:
                result.append(token)
        return result

    def capabilities(self) -> dict[str, Any]:
        missing = []
        name, value = self._auth_header()
        submit_url_present = bool(self._submit_url())
        poll_url_present = bool(self._poll_url())
        auth_present = bool(name and value)
        model_present = bool(str(self.env.get(self.model_env) or "").strip())
        if not self._enabled():
            missing.append(self.enabled_env)
        if not submit_url_present:
            missing.append(self.submit_url_env)
        if not poll_url_present:
            missing.append(self.poll_url_env)
        if not name:
            missing.append(self.auth_header_name_env)
        if not value:
            missing.append(self.auth_header_value_env)
        return {
            "provider": self.provider_name,
            "enabled": self._enabled(),
            "configured": not missing,
            "missing": missing,
            "capabilities": self._capability_list(),
            "endpoint_configured": bool(submit_url_present and poll_url_present),
            "submit_url_present": submit_url_present,
            "poll_url_present": poll_url_present,
            "endpoint_present": bool(submit_url_present or poll_url_present),
            "model_configured": model_present,
            "model_present": model_present,
            "auth_configured": auth_present,
            "auth_present": auth_present,
        }

    def _headers(self) -> dict[str, str]:
        name, value = self._auth_header()
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if name and value:
            headers[name] = value
        return headers

    def _open_json(self, url: str, payload: dict[str, Any] | None = None, *, method: str = "POST", timeout: int = 90) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
                try:
                    parsed = json.loads(body.decode("utf-8", errors="replace"))
                except Exception:
                    parsed = {}
                return {"ok": int(getattr(response, "status", 200)) < 400, "status_code": int(getattr(response, "status", 200)), "body": parsed}
        except urllib.error.HTTPError as exc:
            try:
                parsed = json.loads(exc.read().decode("utf-8", errors="replace"))
            except Exception:
                parsed = {}
            return {"ok": False, "status_code": int(exc.code), "body": parsed, "error": "http_error"}
        except Exception as exc:
            return {"ok": False, "status_code": 0, "body": {}, "error": type(exc).__name__}

    def submit_video_job(self, request: VideoGenerationRequest) -> VideoSubmitResult:
        caps = self.capabilities()
        if not caps.get("configured"):
            return VideoSubmitResult(ok=False, provider_name=self.provider_name, error_code="provider_not_configured")
        payload = {
            "job_id": request.job_id,
            "product_type": request.product_type,
            "capability": request.required_capability,
            "prompt": _safe_text(request.prompt, 4000),
            "negative_prompt": _safe_text(request.negative_prompt, 1200),
            "ratio": request.ratio,
            "duration_seconds": request.duration_seconds,
            "quality": request.quality,
            "style": request.style,
            "seed": request.seed,
            "scenes": request.scenes,
            "storyboard": request.storyboard,
            "image_paths": request.image_paths,
            "source_video_path": request.source_video_path,
            "model": str(self.env.get(self.model_env) or ""),
            "metadata": request.metadata,
        }
        result = self._open_json(self._submit_url(), payload, timeout=int(self.env.get("VIDEO_PROVIDER_SUBMIT_TIMEOUT_SECONDS") or 90))
        body = result.get("body") or {}
        task_id = _first_value(body, ("provider_task_id", "task_id", "taskId", "id", "data.task_id", "data.id"))
        video_id = _first_value(body, ("video_id", "videoId", "id_base", "data.video_id", "data.id_base"))
        result_url = _first_value(body, ("result_url", "file_url", "download_url", "data.result_url", "data.file_url", "data.download_url"))
        status = normalize_provider_status(_first_value(body, ("status", "data.status")), has_result_url=bool(result_url))
        if result.get("ok") and (task_id or video_id or result_url):
            return VideoSubmitResult(
                ok=True,
                provider_name=self.provider_name,
                provider_task_id=task_id or video_id,
                provider_video_id=video_id or task_id,
                provider_status=status,
                result_url=result_url,
                submitted_at=str(int(time.time())),
                raw=body if isinstance(body, dict) else {},
            )
        return VideoSubmitResult(
            ok=False,
            provider_name=self.provider_name,
            provider_status=status,
            error_code=str(result.get("error") or f"submit_failed:{result.get('status_code') or 0}"),
            raw=body if isinstance(body, dict) else {},
        )

    def poll_video_job(self, provider_task_id: str) -> VideoPollResult:
        caps = self.capabilities()
        if not caps.get("configured"):
            return VideoPollResult(ok=False, provider_name=self.provider_name, provider_task_id=provider_task_id, status="failed", error_code="provider_not_configured")
        poll_url = self._poll_url()
        encoded = urllib.parse.quote(str(provider_task_id or ""))
        if "{task_id}" in poll_url:
            url = poll_url.replace("{task_id}", encoded)
        elif "{id}" in poll_url:
            url = poll_url.replace("{id}", encoded)
        else:
            url = poll_url.rstrip("/") + "/" + encoded
        result = self._open_json(url, None, method="GET", timeout=int(self.env.get("VIDEO_PROVIDER_POLL_HTTP_TIMEOUT_SECONDS") or 60))
        body = result.get("body") or {}
        result_field = str(self.env.get(self.result_field_env) or "result_url")
        result_url = str(_json_path(body, result_field) or "").strip() or _first_value(
            body,
            ("result_url", "file_url", "download_url", "video_url", "data.result_url", "data.file_url", "data.download_url", "data.video_url"),
        )
        status = normalize_provider_status(_first_value(body, ("status", "data.status", "state", "data.state")), has_result_url=bool(result_url))
        progress = _first_value(body, ("progress", "progress_percent", "data.progress", "data.progress_percent"))
        try:
            progress_value = int(float(progress)) if progress != "" else None
        except Exception:
            progress_value = None
        return VideoPollResult(
            ok=bool(result.get("ok")),
            status=status,
            provider_name=self.provider_name,
            provider_task_id=str(provider_task_id or ""),
            provider_video_id=_first_value(body, ("video_id", "videoId", "id_base", "data.video_id", "data.id_base")),
            progress_percent=progress_value,
            result_url=result_url,
            file_url=result_url,
            error_code="" if result.get("ok") else str(result.get("error") or f"poll_failed:{result.get('status_code') or 0}"),
            raw_status=_first_value(body, ("status", "data.status", "state", "data.state")),
            raw=body if isinstance(body, dict) else {},
        )

    def materialize_result(self, result: VideoPollResult, job_id: str) -> VideoArtifactResult:
        return materialize_video_url(
            result.result_url or result.file_url,
            job_id=job_id,
            output_dir=str(self.env.get("VIDEO_PROVIDER_OUTPUT_DIR") or ""),
            timeout_seconds=int(self.env.get("VIDEO_PROVIDER_DOWNLOAD_TIMEOUT_SECONDS") or 180),
            filename_prefix=self.provider_name,
        )

    def cancel_video_job(self, provider_task_id: str):
        del provider_task_id
        return {"ok": False, "provider_name": self.provider_name, "error_code": "cancel_not_supported"}
