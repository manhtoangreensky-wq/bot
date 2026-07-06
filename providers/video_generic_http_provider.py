"""Generic HTTP video provider adapter.

The adapter is intentionally conservative: disabled until submit/poll URLs and
auth config are present. It supports API-compatible providers that expose
submit -> poll -> result_url without hardcoding a vendor-specific SDK.
"""

from __future__ import annotations

import json
import os
import re
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


TASK_ID_PATHS = (
    "task_id",
    "id",
    "job_id",
    "request_id",
    "data_id",
    "data.task_id",
    "data.id",
    "data.job_id",
    "data.request_id",
    "result.task_id",
    "result.id",
    "result.job_id",
    "output.task_id",
)
VIDEO_ID_PATHS = (
    "video_id",
    "videoId",
    "id_base",
    "data.video_id",
    "data.videoId",
    "data.id_base",
    "result.video_id",
    "result.videoId",
    "result.id_base",
)
STATUS_PATHS = (
    "status",
    "state",
    "task_status",
    "data.status",
    "data.state",
    "data.task_status",
    "result.status",
    "result.state",
    "output.status",
)
RESULT_URL_PATHS = (
    "data.result_url",
    "download_url",
    "file_url",
    "result_url",
    "video_url",
    "output_url",
    "media_url",
    "url",
    "data.download_url",
    "data.file_url",
    "data.video_url",
    "data.output_url",
    "data.media_url",
    "data.url",
    "result.download_url",
    "result.file_url",
    "result.result_url",
    "result.video_url",
    "outputs.0.url",
    "videos.0.url",
    "files.0.url",
)
VIDEO_RESULT_URL_KEYS = {
    "result_url",
    "video_url",
    "output_url",
    "download_url",
    "file_url",
    "media_url",
    "url",
    "uri",
}
VIDEO_RESULT_CONTAINER_KEYS = {
    "data",
    "result",
    "output",
    "outputs",
    "files",
    "artifacts",
    "videos",
    "task",
}
CONFIG_PLACEHOLDER_MARKERS = (
    "th\u1eadt",
    "example",
    "placeholder",
    "your_",
    "todo",
    "changeme",
    "xxx",
    "demo",
    "test_url",
)
VALID_URL_PREFIXES = ("http://", "https://")


def _config_value_is_placeholder(value: str) -> bool:
    lowered = str(value or "").strip().lower()
    return any(marker in lowered for marker in CONFIG_PLACEHOLDER_MARKERS)


def _valid_config_url(value: str) -> bool:
    cleaned = str(value or "").strip()
    return bool(cleaned and cleaned.lower().startswith(VALID_URL_PREFIXES) and not _config_value_is_placeholder(cleaned))


def _valid_config_secret(value: str) -> bool:
    cleaned = str(value or "").strip()
    return bool(cleaned and not _config_value_is_placeholder(cleaned))


class VideoProviderContractError(ValueError):
    """Provider contract error with safe stage/debug fields for admin diagnostics."""

    def __init__(self, blocker: str, *, stage: str = "payload_build", message: str = "", debug: dict[str, Any] | None = None):
        super().__init__(message or blocker)
        self.blocker = blocker
        self.stage = stage
        self.debug = dict(debug or {})


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


def _parse_progress_value(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        raw = float(str(value).strip().rstrip("%"))
    except Exception:
        return None
    if 0 < raw <= 1:
        raw *= 100
    return max(0, min(100, int(raw)))


def _result_url_rejected(value: str) -> bool:
    parsed = urllib.parse.urlparse(str(value or "").strip())
    path = (parsed.path or "").lower()
    if path.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".json")):
        return True
    if any(marker in path for marker in ("/dashboard", "/console", "/admin")):
        return True
    return False


def _recursive_video_url(payload: Any, prefix: str = "") -> tuple[str, str]:
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_text = str(key or "")
            path = f"{prefix}.{key_text}" if prefix else key_text
            if key_text in VIDEO_RESULT_URL_KEYS:
                candidate = str(value or "").strip()
                if candidate.startswith(("http://", "https://")) and not _result_url_rejected(candidate):
                    return candidate, path
        for key, value in payload.items():
            key_text = str(key or "")
            if key_text not in VIDEO_RESULT_CONTAINER_KEYS:
                continue
            path = f"{prefix}.{key_text}" if prefix else key_text
            found, found_path = _recursive_video_url(value, path)
            if found:
                return found, found_path
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            path = f"{prefix}.{index}" if prefix else str(index)
            found, found_path = _recursive_video_url(value, path)
            if found:
                return found, found_path
    return "", ""


def _first_value(payload: Any, keys: tuple[str, ...]) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in keys:
        value = _json_path(payload, key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _first_value_with_path(payload: Any, keys: tuple[str, ...]) -> tuple[str, str]:
    if not isinstance(payload, dict):
        return "", ""
    for key in keys:
        value = _json_path(payload, key)
        if value not in (None, ""):
            return str(value).strip(), key
    return "", ""


def _response_shape(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"type": type(payload).__name__, "top_level_keys": [], "nested_keys": []}
    nested: list[str] = []
    for key, value in payload.items():
        if isinstance(value, dict):
            nested.append(str(key) + ":{" + ",".join(sorted(str(k) for k in value.keys())[:20]) + "}")
        elif isinstance(value, list):
            first = value[0] if value else None
            if isinstance(first, dict):
                nested.append(str(key) + "[0]:{" + ",".join(sorted(str(k) for k in first.keys())[:20]) + "}")
            else:
                nested.append(str(key) + "[]")
    return {"type": "dict", "top_level_keys": sorted(str(key) for key in payload.keys())[:40], "nested_keys": nested[:40]}


def _safe_exception_message(value: Any, limit: int = 220) -> str:
    text = re.sub(r"(?i)(bearer|token|key|secret|authorization)=?\s*[^\s,;]+", r"\1=***", str(value or ""))
    text = re.sub(r"https?://\S+", "<url>", text)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _safe_provider_error_message(payload: Any, limit: int = 180) -> str:
    if not isinstance(payload, dict):
        return ""
    candidates: list[Any] = []
    context_parts: list[str] = []
    for key in ("status", "code", "type"):
        value = payload.get(key)
        if value not in (None, ""):
            context_parts.append(f"{key}={_safe_exception_message(value, limit=60)}")
    for key in ("message", "error", "detail", "type", "reason"):
        candidates.append(payload.get(key))
    for nested_key in ("data", "error", "errors", "result"):
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            for key in ("status", "code", "type"):
                value = nested.get(key)
                if value not in (None, ""):
                    context_parts.append(f"{key}={_safe_exception_message(value, limit=60)}")
            for key in ("message", "error", "detail", "type", "reason"):
                candidates.append(nested.get(key))
    for value in candidates:
        if value in (None, ""):
            continue
        if isinstance(value, (dict, list, tuple)):
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            text = str(value)
        text = _safe_exception_message(text, limit=limit)
        if text:
            if context_parts:
                text = "; ".join([*context_parts[:3], f"message={text}"])
            return text[:limit]
    return "; ".join(context_parts[:3])[:limit] if context_parts else ""


def _submit_error_classification(status_code: int, error: Any = "") -> tuple[str, bool, bool]:
    try:
        status = int(status_code or 0)
    except Exception:
        status = 0
    error_text = str(error or "").lower()
    if any(marker in error_text for marker in ("get_channel_failed", "no available channel", "no channel")):
        return "provider_capacity_unavailable", True, True
    if status == 503:
        return "provider_temporarily_unavailable", True, True
    if 500 <= status <= 599:
        return "provider_submit_http_5xx", True, True
    if str(error or "") == "url_missing":
        return "provider_submit_url_missing", False, False
    return "provider_submit_http_error", False, False


def _safe_url_host(value: Any) -> str:
    try:
        parsed = urllib.parse.urlparse(str(value or "").strip())
        return str(parsed.netloc or "").strip()[:160]
    except Exception:
        return ""


def _safe_url_path(value: Any) -> str:
    try:
        parsed = urllib.parse.urlparse(str(value or "").strip())
        return str(parsed.path or "").strip()[:180]
    except Exception:
        return ""


def _auth_scheme_prefix(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    first = text.split(None, 1)[0].strip()
    if not re.match(r"^[A-Za-z][A-Za-z0-9_.-]{0,30}$", first):
        return "present"
    return first[:32]


def _payload_debug(payload: dict[str, Any]) -> dict[str, Any]:
    keys = sorted(str(key) for key in payload.keys())[:80]
    model = str(payload.get("model") or payload.get("model_id") or payload.get("modelName") or "")[:120]
    return {
        "payload_keys": keys,
        "provider_payload_keys": keys,
        "provider_payload_model": model,
        "payload_has_prompt": bool(payload.get("prompt")),
        "payload_has_duration": bool(payload.get("duration") or payload.get("duration_seconds")),
        "payload_has_ratio": bool(payload.get("ratio") or payload.get("aspect_ratio") or payload.get("aspectRatio")),
        "prompt_chars": len(str(payload.get("prompt") or "")),
        "duration": payload.get("duration") or payload.get("duration_seconds") or 0,
        "ratio": payload.get("ratio") or payload.get("aspect_ratio") or payload.get("aspectRatio") or "",
        "quality": str(payload.get("quality") or ""),
        "scenes_count": len(payload.get("scenes") or []),
    }


def _model_debug_value(env: dict[str, str] | os._Environ[str] | None, model_env: str) -> str:
    data = env or os.environ
    return str(data.get(model_env) or data.get("VIDEO_PROVIDER_MODEL") or "").strip()[:120]


def _validated_prompt(request: VideoGenerationRequest) -> str:
    prompt = _safe_text(request.prompt, 4000)
    if not prompt:
        raise VideoProviderContractError("provider_payload_missing_prompt", debug={"payload_has_prompt": False})
    return prompt


def _validated_duration(request: VideoGenerationRequest) -> int:
    raw = request.duration_seconds
    if raw in (None, ""):
        raise VideoProviderContractError("provider_payload_missing_duration", debug={"payload_has_duration": False})
    try:
        duration = float(raw)
    except Exception as exc:
        raise VideoProviderContractError("provider_payload_invalid_duration", message=str(exc), debug={"duration": str(raw)}) from exc
    if duration <= 0:
        raise VideoProviderContractError("provider_payload_invalid_duration", debug={"duration": raw})
    return max(1, min(30, int(round(duration))))


def _validated_ratio(request: VideoGenerationRequest) -> str:
    ratio = str(request.ratio or "").strip()
    if not ratio:
        raise VideoProviderContractError("provider_payload_missing_ratio", debug={"payload_has_ratio": False})
    if not re.match(r"^\d{1,2}:\d{1,2}$", ratio):
        raise VideoProviderContractError("provider_payload_invalid_ratio", debug={"ratio": ratio})
    return ratio


def _base_video_payload(request: VideoGenerationRequest, env: dict[str, str] | os._Environ[str] | None = None) -> dict[str, Any]:
    env = env or os.environ
    source = str((request.metadata or {}).get("source") or ("admin_smoke" if (request.metadata or {}).get("admin_smoke") else "product_video"))
    duration = _validated_duration(request)
    ratio = _validated_ratio(request)
    quality = str(request.quality or env.get("VIDEO_PROVIDER_DEFAULT_QUALITY") or "basic").strip() or "basic"
    return {
        "job_id": request.job_id or "smoke",
        "source": source,
        "wallet_charge": False,
        "product_type": request.product_type or "video_ai_prompt",
        "capability": request.required_capability or "text_to_video",
        "prompt": _validated_prompt(request),
        "negative_prompt": _safe_text(request.negative_prompt, 1200),
        "ratio": ratio,
        "aspect_ratio": ratio,
        "aspectRatio": ratio,
        "duration": duration,
        "duration_seconds": duration,
        "quality": quality,
        "style": request.style,
        "seed": request.seed,
        "scenes": list(request.scenes or []),
        "storyboard": list(request.storyboard or []),
        "image_paths": list(request.image_paths or []),
        "source_video_path": request.source_video_path,
        "metadata": {"job_id": request.job_id or "smoke", "source": source, "wallet_charge": False},
    }


def build_key4u_video_payload(request: VideoGenerationRequest, env: dict[str, str] | os._Environ[str] | None = None) -> dict[str, Any]:
    data = _base_video_payload(request, env)
    model = str((env or os.environ).get("KEY4U_VIDEO_MODEL") or (env or os.environ).get("VIDEO_PROVIDER_MODEL") or "").strip()
    if model:
        data["model"] = model
    return data


def build_shopaikey_video_payload(request: VideoGenerationRequest, env: dict[str, str] | os._Environ[str] | None = None) -> dict[str, Any]:
    data = _base_video_payload(request, env)
    model = str((env or os.environ).get("SHOPAIKEY_VIDEO_MODEL") or (env or os.environ).get("VIDEO_PROVIDER_MODEL") or "").strip()
    if model:
        data["model"] = model
    return data


def _build_provider_payload(provider_name: str, request: VideoGenerationRequest, env: dict[str, str] | os._Environ[str]) -> dict[str, Any]:
    if provider_name == "key4u_video":
        return build_key4u_video_payload(request, env)
    if provider_name == "shopaikey_video":
        return build_shopaikey_video_payload(request, env)
    data = _base_video_payload(request, env)
    model = str(env.get("VIDEO_GENERIC_HTTP_MODEL") or env.get("VIDEO_PROVIDER_MODEL") or "").strip()
    if model:
        data["model"] = model
    return data


def parse_submit_task_ids(body: Any) -> tuple[str, str, str, str]:
    task_id, task_path = _first_value_with_path(body, TASK_ID_PATHS)
    video_id, video_path = _first_value_with_path(body, VIDEO_ID_PATHS)
    return task_id, task_path, video_id, video_path


def parse_provider_status(body: Any, *, has_result_url: bool = False) -> tuple[str, str, str]:
    raw, path = _first_value_with_path(body, STATUS_PATHS)
    return normalize_provider_status(raw, has_result_url=has_result_url), raw, path


def parse_result_url(body: Any, configured_field: str = "") -> tuple[str, str]:
    paths = tuple([configured_field] if configured_field else []) + RESULT_URL_PATHS
    for path in paths:
        value = str(_json_path(body, path) or "").strip()
        if not value:
            continue
        if _result_url_rejected(value):
            continue
        return value, path
    return _recursive_video_url(body)


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

    def _config_validation(self) -> dict[str, Any]:
        missing: list[str] = []
        invalid_fields: list[str] = []
        invalid_env: list[str] = []
        name, value = self._auth_header()
        submit_url = self._submit_url()
        poll_url = self._poll_url()
        enabled = self._enabled()
        if not enabled:
            missing.append(self.enabled_env)
        if not submit_url:
            missing.append(self.submit_url_env)
        elif not _valid_config_url(submit_url):
            invalid_fields.append("submit_url")
            invalid_env.append(self.submit_url_env)
        if not poll_url:
            missing.append(self.poll_url_env)
        elif not _valid_config_url(poll_url):
            invalid_fields.append("poll_url")
            invalid_env.append(self.poll_url_env)
        if not name:
            missing.append(self.auth_header_name_env)
        elif not _valid_config_secret(name):
            invalid_fields.append("auth")
            invalid_env.append(self.auth_header_name_env)
        if not value:
            missing.append(self.auth_header_value_env)
        elif not _valid_config_secret(value):
            if "auth" not in invalid_fields:
                invalid_fields.append("auth")
            invalid_env.append(self.auth_header_value_env)
        blocker = "provider_config_placeholder_or_invalid_url" if invalid_fields else ""
        return {
            "enabled": enabled,
            "configured": bool(enabled and not missing and not invalid_fields),
            "missing": missing,
            "invalid_fields": invalid_fields,
            "invalid_env": invalid_env,
            "blocker": blocker,
            "submit_url_configured": bool(_valid_config_url(submit_url)),
            "poll_url_configured": bool(_valid_config_url(poll_url)),
            "auth_configured": bool(_valid_config_secret(name) and _valid_config_secret(value)),
        }

    def _configured(self) -> bool:
        return bool(self._config_validation().get("configured"))

    def _capability_list(self) -> list[str]:
        raw = str(self.env.get(self.capabilities_env) or "text_to_video,image_to_video,video_to_video,multi_scene_video,scene_video")
        result = []
        for item in raw.replace("|", ",").split(","):
            token = item.strip()
            if token and token not in result:
                result.append(token)
        return result

    def capabilities(self) -> dict[str, Any]:
        config = self._config_validation()
        missing = list(config.get("missing") or [])
        name, value = self._auth_header()
        submit_url = self._submit_url()
        submit_url_present = bool(self._submit_url())
        poll_url_present = bool(self._poll_url())
        auth_present = bool(name and value)
        model_present = bool(str(self.env.get(self.model_env) or "").strip())
        return {
            "provider": self.provider_name,
            "enabled": bool(config.get("enabled")),
            "configured": bool(config.get("configured")),
            "missing": missing,
            "invalid_fields": list(config.get("invalid_fields") or []),
            "invalid_env": list(config.get("invalid_env") or []),
            "blocker": str(config.get("blocker") or ""),
            "config_blocker": str(config.get("blocker") or ""),
            "capabilities": self._capability_list(),
            "endpoint_configured": bool(config.get("submit_url_configured") and config.get("poll_url_configured")),
            "submit_url_present": submit_url_present,
            "poll_url_present": poll_url_present,
            "submit_url_configured": bool(config.get("submit_url_configured")),
            "poll_url_configured": bool(config.get("poll_url_configured")),
            "endpoint_present": bool(submit_url_present or poll_url_present),
            "model_configured": model_present,
            "model_present": model_present,
            "provider_model_present": model_present,
            "provider_payload_model": _model_debug_value(self.env, self.model_env),
            "auth_configured": bool(config.get("auth_configured")),
            "auth_present": auth_present,
            "provider_config_source": f"env:{self.provider_name}",
            "provider_submit_url_host": _safe_url_host(submit_url),
            "provider_submit_url_path": _safe_url_path(submit_url),
            "provider_auth_header_name": str(name or "")[:80],
            "provider_auth_value_present": bool(str(value or "").strip()),
            "provider_auth_scheme_prefix": _auth_scheme_prefix(value),
            "provider_config_namespaces_checked": list(self.env.get("_VIDEO_PROVIDER_NAMESPACES_CHECKED", "").split(",")) if self.env.get("_VIDEO_PROVIDER_NAMESPACES_CHECKED") else [],
            "selected_provider_env_prefix": str(self.env.get("_VIDEO_PROVIDER_ENV_PREFIX") or "").strip(),
            "selected_provider_alias_prefixes_checked": list(self.env.get("_VIDEO_PROVIDER_ALIAS_PREFIXES_CHECKED", "").split(",")) if self.env.get("_VIDEO_PROVIDER_ALIAS_PREFIXES_CHECKED") else [],
            "selected_provider_config_source": str(self.env.get("_VIDEO_PROVIDER_CONFIG_SOURCE") or f"env:{self.provider_name}").strip(),
            "provider_env_namespace_mismatch": str(self.env.get("_VIDEO_PROVIDER_NAMESPACE_MISMATCH") or "0").strip().lower() in {"1", "true", "yes", "on"},
        }

    def _headers(self) -> dict[str, str]:
        name, value = self._auth_header()
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if name and value:
            headers[name] = value
        return headers

    def _open_json(self, url: str, payload: dict[str, Any] | None = None, *, method: str = "POST", timeout: int = 90) -> dict[str, Any]:
        if not str(url or "").strip():
            return {"ok": False, "status_code": 0, "body": {}, "error": "url_missing", "response_shape": _response_shape({})}
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
                try:
                    parsed = json.loads(body.decode("utf-8", errors="replace"))
                except Exception:
                    parsed = {}
                    return {
                        "ok": False,
                        "status_code": int(getattr(response, "status", 200)),
                        "body": parsed,
                        "error": "invalid_json",
                        "response_shape": _response_shape(parsed),
                    }
                return {
                    "ok": int(getattr(response, "status", 200)) < 400,
                    "status_code": int(getattr(response, "status", 200)),
                    "body": parsed,
                    "response_shape": _response_shape(parsed),
                }
        except urllib.error.HTTPError as exc:
            try:
                parsed = json.loads(exc.read().decode("utf-8", errors="replace"))
            except Exception:
                parsed = {}
                return {"ok": False, "status_code": int(exc.code), "body": parsed, "error": "http_error_invalid_json", "response_shape": _response_shape(parsed)}
            return {"ok": False, "status_code": int(exc.code), "body": parsed, "error": "http_error", "response_shape": _response_shape(parsed)}
        except Exception as exc:
            return {
                "ok": False,
                "status_code": 0,
                "body": {},
                "error": type(exc).__name__,
                "exception_class": type(exc).__name__,
                "exception_message_safe": _safe_exception_message(exc),
                "response_shape": _response_shape({}),
            }

    def submit_video_job(self, request: VideoGenerationRequest) -> VideoSubmitResult:
        caps = self.capabilities()
        if not caps.get("configured"):
            name, value = self._auth_header()
            raw_debug = {
                "smoke_stage": "config_validation",
                "provider_config_source": caps.get("provider_config_source") or f"env:{self.provider_name}",
                "selected_provider_config_source": caps.get("selected_provider_config_source") or caps.get("provider_config_source") or f"env:{self.provider_name}",
                "provider_config_namespaces_checked": list(caps.get("provider_config_namespaces_checked") or []),
                "selected_provider_env_prefix": caps.get("selected_provider_env_prefix") or "",
                "selected_provider_alias_prefixes_checked": list(caps.get("selected_provider_alias_prefixes_checked") or []),
                "provider_env_namespace_mismatch": bool(caps.get("provider_env_namespace_mismatch")),
                "selected_provider_before_submit": self.provider_name,
                "submit_provider_key": self.provider_name,
                "submit_url_configured": bool(caps.get("submit_url_configured")),
                "provider_submit_url_configured": bool(caps.get("submit_url_configured")),
                "provider_submit_url_host": caps.get("provider_submit_url_host") or _safe_url_host(self._submit_url()),
                "provider_submit_url_path": caps.get("provider_submit_url_path") or _safe_url_path(self._submit_url()),
                "poll_url_configured": bool(caps.get("poll_url_configured")),
                "auth_configured": bool(caps.get("auth_configured")),
                "auth_present": bool(str(value or "").strip()),
                "auth_scheme": _auth_scheme_prefix(value),
                "provider_auth_header_name": str(name or "")[:80],
                "provider_auth_value_present": bool(str(value or "").strip()),
                "provider_auth_scheme_prefix": _auth_scheme_prefix(value),
                "provider_model_present": bool(caps.get("provider_model_present") or caps.get("model_present")),
                "provider_payload_model": caps.get("provider_payload_model") or _model_debug_value(self.env, self.model_env),
                "submit_accepted": False,
                "poll_allowed": False,
                "poll_skipped_reason": "submit_not_accepted",
                "missing": list(caps.get("missing") or []),
                "invalid_fields": list(caps.get("invalid_fields") or []),
                "invalid_env": list(caps.get("invalid_env") or []),
                "provider_submit_blocker": "provider_config_missing_at_submit",
            }
            return VideoSubmitResult(
                ok=False,
                provider_name=self.provider_name,
                provider_status="config_invalid",
                error_code="provider_config_missing_at_submit",
                raw=raw_debug,
            )
        try:
            payload = _build_provider_payload(self.provider_name, request, self.env)
        except VideoProviderContractError:
            raise
        except Exception as exc:
            raise VideoProviderContractError("provider_payload_invalid_shape", stage="payload_build", message=str(exc)) from exc
        submit_url = self._submit_url()
        auth_name, auth_value = self._auth_header()
        result = self._open_json(submit_url, payload, timeout=int(self.env.get("VIDEO_PROVIDER_SUBMIT_TIMEOUT_SECONDS") or 90))
        body = result.get("body") or {}
        task_id, task_path, video_id, video_path = parse_submit_task_ids(body)
        result_url, result_url_path = parse_result_url(body, str(self.env.get(self.result_field_env) or "result_url"))
        status, raw_status, status_path = parse_provider_status(body, has_result_url=bool(result_url))
        raw_debug = {
            "smoke_stage": "submit_response_parse",
            **_payload_debug(payload),
            "provider_config_source": caps.get("provider_config_source") or f"env:{self.provider_name}",
            "selected_provider_config_source": caps.get("selected_provider_config_source") or caps.get("provider_config_source") or f"env:{self.provider_name}",
            "provider_config_namespaces_checked": list(caps.get("provider_config_namespaces_checked") or []),
            "selected_provider_env_prefix": caps.get("selected_provider_env_prefix") or "",
            "selected_provider_alias_prefixes_checked": list(caps.get("selected_provider_alias_prefixes_checked") or []),
            "provider_env_namespace_mismatch": bool(caps.get("provider_env_namespace_mismatch")),
            "selected_provider_before_submit": self.provider_name,
            "submit_provider_key": self.provider_name,
            "submit_url_configured": bool(caps.get("submit_url_configured")),
            "provider_submit_url_configured": bool(caps.get("submit_url_configured")),
            "provider_submit_url_host": _safe_url_host(submit_url),
            "provider_submit_url_path": _safe_url_path(submit_url),
            "poll_url_configured": bool(caps.get("poll_url_configured")),
            "auth_configured": bool(caps.get("auth_configured")),
            "auth_present": bool(str(auth_value or "").strip()),
            "auth_scheme": _auth_scheme_prefix(auth_value),
            "provider_auth_header_name": str(auth_name or "")[:80],
            "provider_auth_value_present": bool(str(auth_value or "").strip()),
            "provider_auth_scheme_prefix": _auth_scheme_prefix(auth_value),
            "provider_model_present": bool(caps.get("provider_model_present") or caps.get("model_present")),
            "http_status": int(result.get("status_code") or 0),
            "submit_http_status": int(result.get("status_code") or 0),
            "provider_response_http_status": int(result.get("status_code") or 0),
            "submit_response_shape": result.get("response_shape") or _response_shape(body),
            "provider_response_body_shape": result.get("response_shape") or _response_shape(body),
            "provider_error_message_safe": _safe_provider_error_message(body),
            "provider_task_id_present": bool(task_id or video_id),
            "provider_task_id_masked": (str(task_id or video_id)[:4] + "***") if (task_id or video_id) else "",
            "provider_status_raw": raw_status,
            "provider_status_path": status_path,
            "result_url_present": bool(result_url),
            "submit_accepted": bool(result.get("ok") and (task_id or video_id or result_url)),
            "poll_allowed": bool(result.get("ok") and (task_id or video_id) and not result_url),
            "poll_skipped_reason": "" if bool(result.get("ok") and (task_id or video_id) and not result_url) else ("result_url_from_submit" if result_url else "provider_task_id_missing"),
            "result_field_path": result_url_path,
            "task_id_field_path": task_path,
            "video_id_field_path": video_path,
        }
        if result.get("exception_class"):
            raw_debug["exception_class"] = result.get("exception_class")
            raw_debug["exception_message_safe"] = result.get("exception_message_safe") or ""
        error_probe = result.get("error") or _safe_provider_error_message(body)
        if result.get("error") in {"invalid_json", "http_error_invalid_json"}:
            blocker, retriable, is_5xx = _submit_error_classification(int(result.get("status_code") or 0), error_probe)
            if is_5xx:
                raw_debug["provider_submit_blocker"] = blocker
                raw_debug["provider_submit_http_5xx"] = True
                raw_debug["provider_submit_retriable"] = True
                return VideoSubmitResult(ok=False, provider_name=self.provider_name, provider_status=status or "failed", error_code=blocker, raw=raw_debug)
            raw_debug["provider_submit_blocker"] = "provider_submit_response_invalid_json"
            return VideoSubmitResult(ok=False, provider_name=self.provider_name, provider_status="failed", error_code="provider_submit_response_invalid_json", raw=raw_debug)
        if not result.get("ok"):
            blocker, retriable, is_5xx = _submit_error_classification(int(result.get("status_code") or 0), error_probe)
            raw_debug["provider_submit_blocker"] = blocker
            raw_debug["provider_submit_http_5xx"] = bool(is_5xx)
            raw_debug["provider_submit_retriable"] = bool(retriable)
            return VideoSubmitResult(ok=False, provider_name=self.provider_name, provider_status=status or "failed", error_code=blocker, raw=raw_debug)
        if not isinstance(body, dict):
            raw_debug["provider_submit_blocker"] = "provider_submit_response_invalid_shape"
            return VideoSubmitResult(ok=False, provider_name=self.provider_name, provider_status="failed", error_code="provider_submit_response_invalid_shape", raw=raw_debug)
        if result.get("ok") and not (task_id or video_id or result_url):
            raw_debug["provider_submit_blocker"] = "provider_task_id_missing"
            return VideoSubmitResult(ok=False, provider_name=self.provider_name, provider_status=status or "failed", error_code="provider_task_id_missing", raw=raw_debug)
        if result.get("ok") and (task_id or video_id or result_url):
            return VideoSubmitResult(
                ok=True,
                provider_name=self.provider_name,
                provider_task_id=task_id or video_id,
                provider_video_id=video_id or task_id,
                provider_status=status,
                result_url=result_url,
                submitted_at=str(int(time.time())),
                raw=raw_debug,
            )
        raw_debug["provider_submit_blocker"] = "provider_submit_response_invalid_shape"
        return VideoSubmitResult(ok=False, provider_name=self.provider_name, provider_status=status, error_code="provider_submit_response_invalid_shape", raw=raw_debug)

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
        result_field = str(
            self.env.get(self.result_field_env)
            or ("data.result_url" if self.provider_name == "shopaikey_video" else "result_url")
        )
        result_url, result_url_path = parse_result_url(body, result_field)
        status, raw_status, status_path = parse_provider_status(body, has_result_url=bool(result_url))
        progress = _first_value(body, ("data.progress", "data.progress_percent", "progress", "progress_percent"))
        progress_value = _parse_progress_value(progress)
        fail_reason = _first_value(body, ("data.fail_reason", "data.error", "data.message", "fail_reason", "error", "message"))
        is_shopaikey_status = self.provider_name == "shopaikey_video"
        raw_debug = {
            "smoke_stage": "poll_response_parse",
            "poll_http_status": int(result.get("status_code") or 0),
            "poll_response_shape": result.get("response_shape") or _response_shape(body),
            "provider_status_raw": raw_status,
            "provider_status_path": status_path,
            "result_url_present": bool(result_url),
            "result_field_path": result_url_path,
            "result_url_primary_path_checked": True,
            "result_url_found": bool(result_url),
            "result_url_source_path": result_url_path or "none",
            "provider_progress_raw": progress if progress not in (None, "") else "",
            "provider_progress_raw_number": progress_value if progress_value is not None else "",
            "provider_progress_source": "data.progress" if progress not in (None, "") else "none",
            "http_200_not_used_as_progress": True,
            "shopaikey_fail_reason": fail_reason if fail_reason not in (None, "") else "",
        }
        if is_shopaikey_status:
            raw_debug.update(
                {
                    "shopaikey_status_endpoint_exact": True,
                    "shopaikey_status_http_code": int(result.get("status_code") or 0),
                    "shopaikey_raw_status": raw_status,
                    "shopaikey_normalized_status": status,
                    "shopaikey_data_progress_raw": progress if progress not in (None, "") else "",
                    "shopaikey_progress_source": "data.progress" if progress not in (None, "") else "none",
                    "shopaikey_result_url_from_data": result_url_path == "data.result_url",
                }
            )
        if result.get("exception_class"):
            raw_debug["exception_class"] = result.get("exception_class")
            raw_debug["exception_message_safe"] = result.get("exception_message_safe") or ""
        ok = bool(result.get("ok"))
        error_code = ""
        if result.get("error") in {"invalid_json", "http_error_invalid_json"}:
            ok = False
            status = "failed"
            error_code = "provider_poll_response_invalid_json"
            raw_debug["provider_poll_blocker"] = error_code
        elif not result.get("ok"):
            ok = False
            status = "failed"
            error_code = "provider_poll_http_error"
            raw_debug["provider_poll_blocker"] = error_code
        elif not isinstance(body, dict):
            ok = False
            status = "failed"
            error_code = "provider_poll_response_invalid_shape"
            raw_debug["provider_poll_blocker"] = error_code
        elif raw_status and status not in {"queued", "running", "succeeded", "failed", "cancelled"}:
            ok = False
            status = "failed"
            error_code = "provider_status_unknown"
            raw_debug["provider_poll_blocker"] = error_code
        elif not raw_status and not result_url:
            ok = False
            status = "failed"
            error_code = "provider_status_unknown"
            raw_debug["provider_poll_blocker"] = error_code
        return VideoPollResult(
            ok=ok,
            status=status,
            provider_name=self.provider_name,
            provider_task_id=str(provider_task_id or ""),
            provider_video_id=_first_value(body, VIDEO_ID_PATHS),
            progress_percent=progress_value,
            result_url=result_url,
            file_url=result_url,
            error_code=error_code,
            raw_status=raw_status,
            raw=raw_debug,
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
