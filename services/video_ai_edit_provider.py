"""Guarded video-to-video provider adapter for AI Video Editing only."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


PUBLIC_FINAL_CONFIRM_SOURCE = "public_ai_video_edit_final_confirm"
POLL_EXISTING_TASK_SOURCE = "worker_poll_existing_task"
HIDDEN_SUBMIT_SOURCES = frozenset({
    "codex_test", "smoke", "debug", "recover", "status", "background_retry",
    "fallback", "startup", "watchdog", "worker", "background",
})
TERMINAL_FAILURES = frozenset({"failed", "failure", "rejected", "cancelled", "canceled", "error", "timeout"})
RUNNING_STATUSES = frozenset({"queued", "pending", "submitted", "processing", "running", "in_progress", "not_start", "in_queue"})
SUCCESS_STATUSES = frozenset({"success", "succeeded", "completed", "complete", "done", "finished"})
PLACEHOLDER_TOKENS = ("example", "placeholder", "your_", "todo", "changeme", "xxx", "demo", "test_url", "submit_url_thật", "poll_url_thật")


class AiEditProviderError(RuntimeError):
    def __init__(self, reason: str, *, terminal: bool = True):
        super().__init__(reason)
        self.reason = reason
        self.terminal = terminal


def _remaining_timeout(
    configured_seconds: int | float,
    *,
    deadline_monotonic: float | None,
    monotonic: Callable[[], float],
) -> float:
    try:
        configured = float(configured_seconds)
        if configured <= 0 or not math.isfinite(configured) or not callable(monotonic):
            raise ValueError
        if deadline_monotonic is None:
            return configured
        if (
            isinstance(deadline_monotonic, bool)
            or not isinstance(deadline_monotonic, (int, float))
            or not math.isfinite(float(deadline_monotonic))
        ):
            raise ValueError
        current = monotonic()
        if (
            isinstance(current, bool)
            or not isinstance(current, (int, float))
            or not math.isfinite(float(current))
        ):
            raise ValueError
        remaining = float(deadline_monotonic) - float(current)
    except (TypeError, ValueError, OverflowError):
        raise AiEditProviderError("provider_deadline_invalid") from None
    if remaining <= 0:
        raise AiEditProviderError("provider_deadline_exceeded")
    return min(configured, remaining)


def _flag(env: dict[str, str] | os._Environ[str], name: str, default: str = "false") -> bool:
    return str(env.get(name, default) or default).strip().lower() in {"1", "true", "yes", "on"}


def _int(env: dict[str, str] | os._Environ[str], name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(env.get(name, default) or default).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _text(env: dict[str, str] | os._Environ[str], *names: str) -> str:
    for name in names:
        value = str(env.get(name, "") or "").strip()
        if value:
            return value
    return ""


def _valid_url(value: str) -> bool:
    text = str(value or "").strip()
    lowered = text.lower()
    if not text.startswith(("http://", "https://")) or any(token in lowered for token in PLACEHOLDER_TOKENS):
        return False
    try:
        parsed = urllib.parse.urlparse(text)
    except ValueError:
        return False
    return bool(parsed.scheme in {"http", "https"} and parsed.netloc)


def _safe_header_name(value: str) -> str:
    name = str(value or "Authorization").strip()
    return name if re.fullmatch(r"[A-Za-z0-9-]{1,80}", name) else "Authorization"


def _catalog() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "config" / "video_provider_catalog.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def model_contract(provider_name: str, model: str) -> dict[str, Any]:
    p_name = {"fal.ai": "fal_video", "fal": "fal_video"}.get(str(provider_name or "").strip().lower(), str(provider_name or "").strip().lower())
    providers = (_catalog().get("providers") or {})
    provider = providers.get(p_name) if isinstance(providers, dict) else {}
    models = provider.get("models") if isinstance(provider, dict) else {}
    contract = models.get(str(model or "")) if isinstance(models, dict) else {}
    capabilities = set(contract.get("capabilities") or []) if isinstance(contract, dict) else set()
    return {
        "known": bool(contract),
        "video_to_video": "video_to_video" in capabilities,
        "capabilities": sorted(capabilities),
        "max_single_task_seconds": int((contract or {}).get("max_single_task_seconds") or 0),
        "payload_adapter": str((contract or {}).get("payload_adapter") or ""),
    }


@dataclass(frozen=True)
class AiEditProviderConfig:
    provider_name: str
    enabled: bool
    submit_url: str
    poll_url: str
    auth_header_name: str
    auth_header_value: str
    model: str
    interface: str
    capabilities: tuple[str, ...]
    upload_field: str = "video"
    prompt_field: str = "prompt"
    timeout_seconds: int = 120
    poll_interval_seconds: int = 10
    max_wait_seconds: int = 900

    def safe_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["auth_header_value"] = "configured" if self.auth_header_value else ""
        payload["submit_url"] = _safe_url_label(self.submit_url)
        payload["poll_url"] = _safe_url_label(self.poll_url)
        return payload


def _safe_url_label(value: str) -> str:
    try:
        parsed = urllib.parse.urlparse(str(value or ""))
    except ValueError:
        return "invalid"
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}" if parsed.scheme and parsed.netloc else ""


def _provider_prefix(provider_name: str) -> str:
    return {
        "fal_video": "FAL_VIDEO_TO_VIDEO",
        "fal.ai": "FAL_VIDEO_TO_VIDEO",
        "fal": "FAL_VIDEO_TO_VIDEO",
        "key4u_video": "KEY4U_VIDEO_TO_VIDEO",
        "shopaikey_video": "SHOPAIKEY_VIDEO_TO_VIDEO",
        "generic_http": "VIDEO_AI_EDIT",
    }.get(str(provider_name or "").strip().lower(), "VIDEO_AI_EDIT")


def provider_config_from_env(provider_name: str, env: dict[str, str] | os._Environ[str] | None = None) -> AiEditProviderConfig:
    source = env if env is not None else os.environ
    name = str(provider_name or "").strip()
    prefix = _provider_prefix(name)
    is_fal = name.lower() in {"fal_video", "fal.ai", "fal"}
    default_submit = "https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video" if is_fal else ""
    default_poll = "https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/{task_id}/status" if is_fal else ""
    default_model = "fal-ai/wan/v2.2-a14b/video-to-video" if is_fal else ""
    default_interface = "video_to_video_json" if is_fal else "video_to_video_multipart"
    submit_url = _text(source, f"{prefix}_SUBMIT_URL", f"{prefix}_ENDPOINT") or default_submit
    poll_url = _text(source, f"{prefix}_POLL_URL", f"{prefix}_POLL_ENDPOINT", f"{prefix}_STATUS_ENDPOINT") or default_poll
    auth_value = _text(source, f"{prefix}_AUTH_HEADER_VALUE", f"{prefix}_API_KEY", f"{prefix}_KEY")
    if is_fal and auth_value and not auth_value.startswith(("Key ", "Bearer ")):
        auth_value = f"Key {auth_value}"
    model = _text(source, f"{prefix}_MODEL") or default_model
    capabilities = tuple(item.strip() for item in _text(source, f"{prefix}_CAPABILITIES").split(",") if item.strip()) or ("video_to_video",)
    return AiEditProviderConfig(
        provider_name=name,
        enabled=_flag(source, f"{prefix}_ENABLED", "false"),
        submit_url=submit_url,
        poll_url=poll_url,
        auth_header_name=_safe_header_name(_text(source, f"{prefix}_AUTH_HEADER_NAME") or "Authorization"),
        auth_header_value=auth_value,
        model=model,
        interface=_text(source, f"{prefix}_INTERFACE") or default_interface,
        capabilities=capabilities,
        upload_field=_text(source, f"{prefix}_UPLOAD_FIELD") or "video",
        prompt_field=_text(source, f"{prefix}_PROMPT_FIELD") or "prompt",
        timeout_seconds=_int(source, f"{prefix}_TIMEOUT_SECONDS", 120, 10, 600),
        poll_interval_seconds=_int(source, "VIDEO_AI_EDIT_POLL_INTERVAL_SECONDS", 10, 5, 60),
        max_wait_seconds=_int(source, "VIDEO_AI_EDIT_MAX_WAIT_SECONDS", 900, 30, 3600),
    )


def configured_provider_chain(env: dict[str, str] | os._Environ[str] | None = None) -> list[AiEditProviderConfig]:
    source = env if env is not None else os.environ
    raw = _text(source, "VIDEO_AI_EDIT_PROVIDER_CHAIN") or "key4u_video,shopaikey_video,generic_http"
    names = []
    for item in raw.split(","):
        name = item.strip().lower()
        if name and name not in names:
            names.append(name)
    return [provider_config_from_env(name, source) for name in names]


KEY4U_V2V_WIRE_CONTRACT = "UNAVAILABLE_FAIL_CLOSED"
CURRENT_KEY4U_MULTIPART_V2V_ADAPTER_PROVEN = False
ALL_KEY4U_V2V_GLOBALLY_DECLARED_UNAVAILABLE = False
MOTION_CONTROL_AUTO_ENABLED = False
MOTION_CONTROL_REUSED_AS_MULTIPART = False
UNVERIFIED_V2V_ENDPOINT_INVENTED = False

# Production authority: Zero test/harness URLs permitted in production authority.
PROVEN_V2V_WIRE_ADAPTERS: set[str] = set()
CANONICAL_PROVEN_V2V_PROVIDERS: frozenset[str] = frozenset({
    "fal_video",
    "fal.ai",
    "fal",
})
VALID_V2V_INTERFACES = frozenset({"video_to_video_multipart", "video_to_video_json", "fal_wan_v2v_json"})
LOCAL_VIDEO_DATA_URI_SUPPORTED_BY_PROVIDER_CONTRACT: bool = False
FAL_NUM_FRAMES_MIN: int = 17
FAL_NUM_FRAMES_MAX: int = 161
FAL_STORAGE_INITIATE_URL: str = "https://rest.fal.ai/storage/upload/initiate"


def classify_endpoint_capability(url: str) -> str:
    """Classify the capability of an endpoint URL from its path."""
    text = str(url or "").strip().lower()
    if not text:
        return "unknown"
    try:
        parsed = urllib.parse.urlparse(text)
        path = (parsed.path or "").lower()
    except Exception:
        path = text
    if "/text2video" in path or "text2video" in path:
        return "text_to_video"
    if "/image2video" in path or "image2video" in path:
        return "image_to_video"
    if "/video-to-video" in path or "video2video" in path or "video_to_video" in path:
        return "video_to_video"
    return "unknown"


def has_proven_v2v_wire_contract(provider_name: str, model: str = "", submit_url: str = "") -> bool:
    """Check if a real, provider-specific, source-bound V2V wire contract has been proven."""
    name = str(provider_name or "").strip().lower()
    url = str(submit_url or "").strip().lower()
    if name == "key4u_video":
        return False
    if url in PROVEN_V2V_WIRE_ADAPTERS:
        return True
    if (name, model) in PROVEN_V2V_WIRE_ADAPTERS or name in PROVEN_V2V_WIRE_ADAPTERS:
        return True
    if name in CANONICAL_PROVEN_V2V_PROVIDERS and model in {"fal-ai/wan/v2.2-a14b/video-to-video", ""}:
        return True
    return False


def validate_provider_config(config: AiEditProviderConfig, required_capability: str = "video_to_video") -> dict[str, Any]:
    invalid: list[str] = []
    if not config.enabled:
        invalid.append("enabled")
    if not _valid_url(config.submit_url):
        invalid.append("submit_url")
    if not _valid_url(config.poll_url):
        invalid.append("poll_url")
    if not config.auth_header_value or any(token in config.auth_header_value.lower() for token in PLACEHOLDER_TOKENS):
        invalid.append("auth")
    if not config.model:
        invalid.append("model")
    if config.interface not in VALID_V2V_INTERFACES:
        invalid.append("interface")
    if "video_to_video" not in config.capabilities:
        invalid.append("capability")
    contract = model_contract(config.provider_name, config.model)
    if not contract.get("known") or not contract.get("video_to_video"):
        invalid.append("model_contract")

    endpoint_cap = classify_endpoint_capability(config.submit_url)
    if required_capability == "video_to_video":
        proven_wire = has_proven_v2v_wire_contract(config.provider_name, config.model, config.submit_url)
        if endpoint_cap in {"text_to_video", "image_to_video", "unknown"} and not proven_wire:
            invalid.append("provider_capability_contract_mismatch")

    reason = ""
    if "provider_capability_contract_mismatch" in invalid:
        reason = "provider_capability_contract_mismatch"
    elif invalid:
        reason = "ai_edit_provider_contract_invalid"

    return {
        "ok": not invalid,
        "invalid_fields": invalid,
        "reason": reason,
        "provider_name": config.provider_name,
        "model": config.model,
        "contract": contract,
        "endpoint_capability": endpoint_cap,
    }


def pricing_snapshot(env: dict[str, str] | os._Environ[str] | None = None) -> dict[str, Any]:
    source = env if env is not None else os.environ
    price = _int(source, "VIDEO_AI_EDIT_PRICE_XU", 0, 0, 10_000_000)
    return {
        "configured": price > 0,
        "price_xu": price,
        "source": "VIDEO_AI_EDIT_PRICE_XU" if price > 0 else "quote_unavailable",
        "product_id": "video_ai_edit",
        "reused_product_video_price": False,
        "reused_subdub_price": False,
    }


def feature_snapshot(env: dict[str, str] | os._Environ[str] | None = None) -> dict[str, Any]:
    source = env if env is not None else os.environ
    providers = configured_provider_chain(source)
    validated = [{**item.safe_dict(), **validate_provider_config(item)} for item in providers]
    ready = [item for item in providers if validate_provider_config(item).get("ok")]
    return {
        "public_enabled": _flag(source, "VIDEO_AI_EDIT_PUBLIC_ENABLED", "false"),
        "local_lane_enabled": _flag(source, "VIDEO_AI_EDIT_LOCAL_ENABLED", "true"),
        "generative_lane_enabled": _flag(source, "VIDEO_AI_EDIT_GENERATIVE_ENABLED", "false"),
        "public_maintenance_freeze": _flag(source, "VIDEO_AI_EDIT_PUBLIC_FREEZE", "false"),
        "hidden_submit_freeze": _flag(source, "VIDEO_AI_EDIT_HIDDEN_SUBMIT_FREEZE", "true"),
        "pricing": pricing_snapshot(source),
        "providers": validated,
        "provider_capability_available": bool(ready),
        "first_ready_provider": ready[0].provider_name if ready else "",
    }


def submit_source_policy(
    source_name: str,
    *,
    public_user_confirmed: bool,
    lane: str,
    env: dict[str, str] | os._Environ[str] | None = None,
) -> dict[str, Any]:
    source = env if env is not None else os.environ
    name = str(source_name or "").strip().lower()
    snapshot = feature_snapshot(source)
    if lane == "local":
        allowed = bool(snapshot["local_lane_enabled"] and name == PUBLIC_FINAL_CONFIRM_SOURCE and public_user_confirmed)
        return {"allowed": allowed, "reason": "" if allowed else "local_ai_edit_final_confirm_required", "provider_submit": False}
    if name == POLL_EXISTING_TASK_SOURCE:
        return {"allowed": True, "reason": "poll_existing_task_only", "provider_submit": False, "poll_only": True}
    if name in HIDDEN_SUBMIT_SOURCES or name != PUBLIC_FINAL_CONFIRM_SOURCE:
        return {"allowed": False, "reason": "ai_edit_hidden_submit_blocked", "provider_submit": False}
    if not public_user_confirmed:
        return {"allowed": False, "reason": "ai_edit_public_final_confirm_required", "provider_submit": False}
    if not snapshot["public_enabled"]:
        return {"allowed": False, "reason": "ai_edit_public_disabled", "provider_submit": False}
    if not snapshot["generative_lane_enabled"]:
        return {"allowed": False, "reason": "ai_edit_generative_disabled", "provider_submit": False}
    if snapshot["public_maintenance_freeze"]:
        return {"allowed": False, "reason": "ai_edit_public_maintenance", "provider_submit": False}
    if not snapshot["pricing"]["configured"]:
        return {"allowed": False, "reason": "ai_edit_price_unconfigured", "provider_submit": False}
    ready = [config for config in configured_provider_chain(source) if validate_provider_config(config).get("ok")]
    if not ready:
        return {"allowed": False, "reason": "ai_edit_video_to_video_provider_unavailable", "provider_submit": False}
    return {
        "allowed": True,
        "reason": "public_ai_video_edit_final_confirm",
        "provider_submit": True,
        "selected_provider": ready[0].provider_name,
        "selected_model": ready[0].model,
        "selected_interface": ready[0].interface,
        "price_xu": snapshot["pricing"]["price_xu"],
        "fallback_provider": ready[1].provider_name if len(ready) > 1 else "",
    }


def _multipart_body(fields: dict[str, Any], file_field: str, file_path: str) -> tuple[bytes, str]:
    boundary = f"----TOANAASAiEdit{uuid.uuid4().hex}"
    body = bytearray()
    for key, value in fields.items():
        if value in (None, ""):
            continue
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode("utf-8"))
    target = Path(file_path)
    if not target.is_file() or target.suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm"}:
        raise AiEditProviderError("ai_edit_source_video_invalid")
    body.extend(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"source.mp4\"\r\n"
        "Content-Type: video/mp4\r\n\r\n".encode("utf-8")
    )
    body.extend(target.read_bytes())
    body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def _json_response(response: Any) -> tuple[int, dict[str, Any]]:
    status = int(getattr(response, "status", 0) or getattr(response, "code", 0) or 0)
    raw = response.read() if callable(getattr(response, "read", None)) else b""
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    try:
        payload = json.loads(bytes(raw or b"{}").decode("utf-8", errors="replace"))
    except (ValueError, json.JSONDecodeError):
        payload = {}
    return status, payload if isinstance(payload, dict) else {}


def _nested(payload: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        current: Any = payload
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current.get(part)
        if current not in (None, "", [], {}):
            return current
    return None


_CONTINUITY_CONTAINERS = (
    "continuity_metrics",
    "continuity_evidence",
    "continuity_validation",
    "subject_continuity",
)
_SENSITIVE_KEY_SUBSTRINGS = ("auth", "token", "secret", "password", "api_key", "credential")


def _sanitize_continuity_metadata(container: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, val in container.items():
        key_str = str(key).strip()
        lowered = key_str.lower()
        if any(bad in lowered for bad in _SENSITIVE_KEY_SUBSTRINGS):
            continue
        if isinstance(val, (bool, int, float, str)):
            sanitized[key_str] = val
        elif isinstance(val, dict):
            nested_sanitized = _sanitize_continuity_metadata(val)
            if nested_sanitized:
                sanitized[key_str] = nested_sanitized
    return sanitized


def _extract_continuity_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    extracted: dict[str, Any] = {}
    data_nested = payload.get("data")
    sources: list[dict[str, Any]] = []
    if isinstance(data_nested, dict):
        sources.append(data_nested)
    sources.append(payload)
    for container_name in _CONTINUITY_CONTAINERS:
        for src in sources:
            val = src.get(container_name)
            if isinstance(val, dict):
                cleaned = _sanitize_continuity_metadata(val)
                if cleaned:
                    extracted[container_name] = cleaned
                    break
    return extracted


def parse_provider_payload(payload: dict[str, Any]) -> dict[str, Any]:
    task_id = _nested(payload, "data.task_id", "data.id", "data.id_base", "task_id", "id", "job_id", "request_id")
    raw_status = _nested(payload, "data.status", "status", "state")
    result_url = _nested(payload, "data.result_url", "data.video_url", "data.url", "result_url", "video_url", "url", "video.url")
    raw = str(raw_status or "").strip()
    normalized = raw.lower().replace("-", "_").replace(" ", "_")
    if result_url:
        canonical = "completed"
    elif normalized in SUCCESS_STATUSES:
        canonical = "completed"
    elif normalized in TERMINAL_FAILURES:
        canonical = "failed"
    elif normalized in RUNNING_STATUSES or task_id:
        canonical = "running"
    else:
        canonical = "unknown"
    result = {
        "provider_task_id": str(task_id or ""),
        "raw_status": raw,
        "status": canonical,
        "result_url": str(result_url or ""),
        "result_url_present": bool(result_url),
    }
    result.update(_extract_continuity_metadata(payload))
    return result


def upload_fal_media_file(
    config: AiEditProviderConfig,
    local_path: str | os.PathLike[str],
    *,
    opener: Callable[..., Any] | None = None,
    timeout: float = 120.0,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Upload a local scene artifact to Fal official storage (POST /storage/upload/initiate -> PUT)."""
    p = Path(local_path)
    if not p.is_file():
        raise AiEditProviderError("fal_scene_upload_file_missing")
    size_bytes = p.stat().st_size
    if size_bytes <= 0:
        raise AiEditProviderError("fal_scene_upload_file_empty")
    suffix = p.suffix.lower()
    mime_types = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
    }
    if suffix not in mime_types:
        raise AiEditProviderError("fal_scene_upload_unsupported_media_type")
    content_type = mime_types[suffix]

    auth_val = str(config.auth_header_value or "").strip()
    if not auth_val or any(tok in auth_val.lower() for tok in PLACEHOLDER_TOKENS):
        raise AiEditProviderError("fal_scene_upload_auth_missing")

    with open(p, "rb") as f:
        file_bytes = f.read()
    digest = hashlib.sha256(file_bytes).hexdigest()

    transport = opener or urllib.request.urlopen

    # 1. Initiate upload
    initiate_payload = {
        "file_name": p.name,
        "content_type": content_type,
    }
    initiate_body = json.dumps(initiate_payload).encode("utf-8")
    initiate_req = urllib.request.Request(
        FAL_STORAGE_INITIATE_URL,
        data=initiate_body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "TOAN-AAS-AI-Edit/1.0",
            config.auth_header_name: auth_val,
        },
        method="POST",
    )
    try:
        initiate_resp = transport(initiate_req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise AiEditProviderError(f"fal_scene_upload_initiate_failed_http_{exc.code}") from exc
    except Exception as exc:
        raise AiEditProviderError("fal_scene_upload_initiate_failed") from exc

    status = getattr(initiate_resp, "status", None) or getattr(initiate_resp, "code", 200)
    if status < 200 or status >= 300:
        raise AiEditProviderError(f"fal_scene_upload_initiate_failed_http_{status}")

    try:
        raw_text = initiate_resp.read().decode("utf-8")
        parsed_initiate = json.loads(raw_text)
    except Exception as exc:
        raise AiEditProviderError("fal_scene_upload_initiate_invalid_response") from exc

    if not isinstance(parsed_initiate, dict):
        raise AiEditProviderError("fal_scene_upload_initiate_invalid_response")

    upload_url = str(parsed_initiate.get("upload_url") or "").strip()
    file_url = str(parsed_initiate.get("file_url") or "").strip()

    if not upload_url:
        raise AiEditProviderError("fal_scene_upload_upload_url_missing")
    if not file_url:
        raise AiEditProviderError("fal_scene_upload_result_url_missing")
    if not file_url.startswith("https://"):
        raise AiEditProviderError("fal_scene_upload_result_url_invalid")

    # 2. PUT upload bytes
    put_req = urllib.request.Request(
        upload_url,
        data=file_bytes,
        headers={
            "Content-Type": content_type,
            "User-Agent": "TOAN-AAS-AI-Edit/1.0",
        },
        method="PUT",
    )
    try:
        put_resp = transport(put_req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise AiEditProviderError(f"fal_scene_upload_failed_http_{exc.code}") from exc
    except Exception as exc:
        raise AiEditProviderError("fal_scene_upload_failed") from exc

    put_status = getattr(put_resp, "status", None) or getattr(put_resp, "code", 200)
    if put_status < 200 or put_status >= 300:
        raise AiEditProviderError(f"fal_scene_upload_failed_http_{put_status}")

    return {
        "ok": True,
        "provider": "fal_video",
        "file_url": file_url,
        "local_path": str(p),
        "local_sha256": digest,
        "local_size_bytes": size_bytes,
        "content_type": content_type,
    }


def submit_video_edit(
    config: AiEditProviderConfig,
    *,
    source_video_path: str,
    prompt: str,
    negative_prompt: str,
    aspect_ratio: str,
    duration_seconds: int,
    job_id: str,
    submit_source: str,
    public_user_confirmed: bool,
    opener: Callable[..., Any] | None = None,
    deadline_monotonic: float | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    validation = validate_provider_config(config)
    if not validation.get("ok"):
        raise AiEditProviderError(str(validation.get("reason") or "ai_edit_provider_invalid"))
    if submit_source != PUBLIC_FINAL_CONFIRM_SOURCE or not public_user_confirmed:
        raise AiEditProviderError("ai_edit_hidden_submit_blocked")
    if config.interface in {"video_to_video_json", "fal_wan_v2v_json"}:
        source_url = str(source_video_path or "").strip()
        if not source_url.startswith(("http://", "https://")):
            raise AiEditProviderError("fal_v2v_local_transport_unsupported_remote_url_required")
        video_url = source_url

        dur = float(duration_seconds or 5.0)
        # Wan 2.2 requires (num_frames - 1) % 4 == 0 (e.g. 5s -> 81 frames, 10s -> 161 frames)
        # fps = 16
        k = int(round((dur * 16.0) / 4.0))
        num_frames = 4 * k + 1
        if num_frames < FAL_NUM_FRAMES_MIN or num_frames > FAL_NUM_FRAMES_MAX:
            raise AiEditProviderError("fal_v2v_duration_exceeds_max_frames")
        json_fields = {
            config.prompt_field: str(prompt or "")[:12_000],
            "video_url": video_url,
            "num_frames": num_frames,
            "frames_per_second": 16,
            "aspect_ratio": str(aspect_ratio or "9:16"),
        }
        if negative_prompt:
            json_fields["negative_prompt"] = str(negative_prompt or "")[:8_000]
        body = json.dumps(json_fields).encode("utf-8")
        content_type = "application/json"
    else:
        fields = {
            config.prompt_field: str(prompt or "")[:12_000],
            "negative_prompt": str(negative_prompt or "")[:8_000],
            "model": config.model,
            "ratio": str(aspect_ratio or "9:16"),
            "duration": int(duration_seconds or 0),
            "job_id": str(job_id or "")[:120],
            "source": PUBLIC_FINAL_CONFIRM_SOURCE,
            "capability": "video_to_video",
        }
        body, content_type = _multipart_body(fields, config.upload_field, source_video_path)
    headers = {
        "Content-Type": content_type,
        "Accept": "application/json",
        "User-Agent": "TOAN-AAS-AI-Edit/1.0",
        config.auth_header_name: config.auth_header_value,
    }
    request = urllib.request.Request(config.submit_url, data=body, headers=headers, method="POST")
    transport = opener or urllib.request.urlopen
    try:
        response = transport(
            request,
            timeout=_remaining_timeout(
                config.timeout_seconds,
                deadline_monotonic=deadline_monotonic,
                monotonic=monotonic,
            ),
        )
        status, payload = _json_response(response)
    except urllib.error.HTTPError as exc:
        raise AiEditProviderError(f"provider_submit_http_{exc.code}") from exc
    except urllib.error.URLError as exc:
        raise AiEditProviderError("provider_submit_connection_failed") from exc
    if status < 200 or status >= 300:
        raise AiEditProviderError(f"provider_submit_http_{status or 0}")
    parsed = parse_provider_payload(payload)
    if not parsed["provider_task_id"] and not parsed["result_url_present"]:
        raise AiEditProviderError("provider_submit_task_id_missing")
    return {
        **parsed,
        "accepted": True,
        "submit_http_status": status,
        "provider_name": config.provider_name,
        "model": config.model,
        "interface": config.interface,
        "submit_source": submit_source,
        "public_user_confirmed": True,
    }


def _poll_url(template: str, task_id: str) -> str:
    encoded = urllib.parse.quote(str(task_id or ""), safe="")
    if "{task_id}" in template:
        return template.replace("{task_id}", encoded)
    if template.endswith("/"):
        return template + encoded
    separator = "&" if "?" in template else "?"
    return f"{template}{separator}task_id={encoded}"


def poll_video_edit(
    config: AiEditProviderConfig,
    provider_task_id: str,
    *,
    opener: Callable[..., Any] | None = None,
    deadline_monotonic: float | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    if not provider_task_id:
        raise AiEditProviderError("provider_task_id_required")
    url = _poll_url(config.poll_url, provider_task_id)
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "TOAN-AAS-AI-Edit/1.0",
            config.auth_header_name: config.auth_header_value,
        },
        method="GET",
    )
    transport = opener or urllib.request.urlopen
    try:
        response = transport(
            request,
            timeout=_remaining_timeout(
                config.timeout_seconds,
                deadline_monotonic=deadline_monotonic,
                monotonic=monotonic,
            ),
        )
        status, payload = _json_response(response)
    except urllib.error.HTTPError as exc:
        raise AiEditProviderError(f"provider_poll_http_{exc.code}", terminal=False) from exc
    except urllib.error.URLError as exc:
        raise AiEditProviderError("provider_poll_connection_failed", terminal=False) from exc
    if status < 200 or status >= 300:
        raise AiEditProviderError(f"provider_poll_http_{status or 0}", terminal=False)
    parsed = parse_provider_payload(payload)
    if parsed.get("status") == "completed" and not parsed.get("result_url_present"):
        result_endpoint = str(payload.get("response_url") or "").strip()
        if not result_endpoint and "/status" in url:
            result_endpoint = url.replace("/status", "")
        if result_endpoint and _valid_url(result_endpoint):
            try:
                res_req = urllib.request.Request(
                    result_endpoint,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "TOAN-AAS-AI-Edit/1.0",
                        config.auth_header_name: config.auth_header_value,
                    },
                    method="GET",
                )
                res_resp = transport(
                    res_req,
                    timeout=_remaining_timeout(
                        config.timeout_seconds,
                        deadline_monotonic=deadline_monotonic,
                        monotonic=monotonic,
                    ),
                )
                _, res_payload = _json_response(res_resp)
                res_parsed = parse_provider_payload(res_payload)
                if res_parsed.get("result_url"):
                    parsed["result_url"] = res_parsed["result_url"]
                    parsed["result_url_present"] = True
            except Exception:
                pass
    return {
        **parsed,
        "provider_task_id": provider_task_id,
        "poll_http_status": status,
        "provider_name": config.provider_name,
        "model": config.model,
    }


def download_result(
    result_url: str,
    destination: str,
    *,
    maximum_bytes: int = 200 * 1024 * 1024,
    opener: Callable[..., Any] | None = None,
    deadline_monotonic: float | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    if not _valid_url(result_url):
        raise AiEditProviderError("provider_result_url_invalid")
    target = Path(destination)
    if target.suffix.lower() != ".mp4":
        raise AiEditProviderError("provider_result_destination_invalid")
    request = urllib.request.Request(result_url, headers={"User-Agent": "TOAN-AAS-AI-Edit/1.0"}, method="GET")
    transport = opener or urllib.request.urlopen
    downloaded = 0
    try:
        response = transport(
            request,
            timeout=_remaining_timeout(
                180,
                deadline_monotonic=deadline_monotonic,
                monotonic=monotonic,
            ),
        )
        status = int(getattr(response, "status", 0) or getattr(response, "code", 0) or 0)
        if status < 200 or status >= 300:
            raise AiEditProviderError(f"provider_result_http_{status or 0}")
        with target.open("wb") as handle:
            while True:
                if deadline_monotonic is not None:
                    _remaining_timeout(
                        180,
                        deadline_monotonic=deadline_monotonic,
                        monotonic=monotonic,
                    )
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                downloaded += len(chunk)
                if downloaded > int(maximum_bytes):
                    raise AiEditProviderError("provider_result_too_large")
                handle.write(chunk)
    except AiEditProviderError:
        if target.exists():
            target.unlink()
        raise
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        if target.exists():
            target.unlink()
        raise AiEditProviderError(f"provider_result_download_failed:{type(exc).__name__}") from exc
    if downloaded <= 0:
        if target.exists():
            target.unlink()
        raise AiEditProviderError("provider_result_zero_bytes")
    return {"ok": True, "path": str(target), "bytes": downloaded, "download_http_status": status}


def controlled_fallback_decision(
    *,
    public_confirm_provenance: bool,
    primary_status: str,
    primary_task_alive: bool,
    fallback_count: int,
    candidate: AiEditProviderConfig | None,
    primary_error: str = "",
) -> dict[str, Any]:
    if not public_confirm_provenance:
        return {"allowed": False, "reason": "public_confirm_provenance_missing"}
    if (
        primary_error in {"provider_capability_contract_mismatch", "ai_edit_provider_contract_invalid", "fal_v2v_duration_exceeds_max_frames"}
        or primary_error.startswith("fal_scene_upload_")
    ):
        return {"allowed": False, "reason": "capability_contract_mismatch_fallback_forbidden"}
    if "contract_mismatch" in str(primary_status or "").lower() or "contract_mismatch" in str(primary_error or "").lower():
        return {"allowed": False, "reason": "capability_contract_mismatch_fallback_forbidden"}
    if primary_task_alive or str(primary_status or "").lower() in {"running", "pending", "processing", "in_progress"}:
        return {"allowed": False, "reason": "primary_task_alive"}
    if str(primary_status or "").lower() not in {"failed", "failure", "rejected", "cancelled", "timeout", "error"}:
        return {"allowed": False, "reason": "primary_not_terminal_failed"}
    if int(fallback_count or 0) >= 1:
        return {"allowed": False, "reason": "fallback_limit_reached"}
    if candidate is None or not validate_provider_config(candidate).get("ok"):
        return {"allowed": False, "reason": "fallback_provider_unavailable"}
    return {"allowed": True, "reason": "controlled_terminal_fallback", "provider": candidate.provider_name, "model": candidate.model}


def wait_for_result(
    config: AiEditProviderConfig,
    provider_task_id: str,
    *,
    poller: Callable[..., dict[str, Any]] = poll_video_edit,
    sleeper: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
    progress: Callable[[dict[str, Any]], None] | None = None,
    deadline_monotonic: float | None = None,
) -> dict[str, Any]:
    started = now()
    poll_count = 0
    while now() - started <= config.max_wait_seconds:
        sleep_seconds = float(config.poll_interval_seconds)
        if deadline_monotonic is not None:
            sleep_seconds = _remaining_timeout(
                sleep_seconds,
                deadline_monotonic=deadline_monotonic,
                monotonic=now,
            )
        sleeper(sleep_seconds)
        if deadline_monotonic is not None:
            _remaining_timeout(
                config.timeout_seconds,
                deadline_monotonic=deadline_monotonic,
                monotonic=now,
            )
        poll_count += 1
        if deadline_monotonic is None:
            result = poller(config, provider_task_id)
        else:
            result = poller(
                config,
                provider_task_id,
                deadline_monotonic=deadline_monotonic,
                monotonic=now,
            )
        result["poll_count"] = poll_count
        result["elapsed_seconds"] = max(0, int(now() - started))
        if progress:
            progress(dict(result))
        if result.get("status") == "completed" and result.get("result_url_present"):
            return result
        if result.get("status") == "failed":
            raise AiEditProviderError("provider_terminal_failure")
    raise AiEditProviderError("provider_poll_timeout")


def mask_task_id(value: str) -> str:
    text = str(value or "")
    if len(text) <= 8:
        return "***" if text else ""
    return f"{text[:4]}...{text[-4:]}"


__all__ = [
    "AiEditProviderConfig", "AiEditProviderError", "HIDDEN_SUBMIT_SOURCES",
    "POLL_EXISTING_TASK_SOURCE", "PUBLIC_FINAL_CONFIRM_SOURCE",
    "configured_provider_chain", "controlled_fallback_decision", "download_result",
    "feature_snapshot", "mask_task_id", "model_contract", "parse_provider_payload",
    "poll_video_edit", "pricing_snapshot", "provider_config_from_env",
    "submit_source_policy", "submit_video_edit", "validate_provider_config", "wait_for_result",
]
