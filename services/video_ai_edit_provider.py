"""Guarded video-to-video provider adapter for AI Video Editing only."""

from __future__ import annotations

import json
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
RUNNING_STATUSES = frozenset({"queued", "pending", "submitted", "processing", "running", "in_progress", "not_start"})
SUCCESS_STATUSES = frozenset({"success", "succeeded", "completed", "complete", "done", "finished"})
PLACEHOLDER_TOKENS = ("example", "placeholder", "your_", "todo", "changeme", "xxx", "demo", "test_url", "submit_url_thật", "poll_url_thật")


class AiEditProviderError(RuntimeError):
    def __init__(self, reason: str, *, terminal: bool = True):
        super().__init__(reason)
        self.reason = reason
        self.terminal = terminal


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
    providers = (_catalog().get("providers") or {})
    provider = providers.get(str(provider_name or "")) if isinstance(providers, dict) else {}
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
        "key4u_video": "KEY4U_VIDEO_TO_VIDEO",
        "shopaikey_video": "SHOPAIKEY_VIDEO_TO_VIDEO",
        "generic_http": "VIDEO_AI_EDIT",
    }.get(str(provider_name or ""), "VIDEO_AI_EDIT")


def provider_config_from_env(provider_name: str, env: dict[str, str] | os._Environ[str] | None = None) -> AiEditProviderConfig:
    source = env if env is not None else os.environ
    name = str(provider_name or "").strip()
    prefix = _provider_prefix(name)
    submit_url = _text(source, f"{prefix}_SUBMIT_URL", f"{prefix}_ENDPOINT")
    poll_url = _text(source, f"{prefix}_POLL_URL", f"{prefix}_POLL_ENDPOINT", f"{prefix}_STATUS_ENDPOINT")
    auth_value = _text(source, f"{prefix}_AUTH_HEADER_VALUE", f"{prefix}_API_KEY")
    model = _text(source, f"{prefix}_MODEL")
    capabilities = tuple(item.strip() for item in _text(source, f"{prefix}_CAPABILITIES").split(",") if item.strip()) or ("video_to_video",)
    return AiEditProviderConfig(
        provider_name=name,
        enabled=_flag(source, f"{prefix}_ENABLED", "false"),
        submit_url=submit_url,
        poll_url=poll_url,
        auth_header_name=_safe_header_name(_text(source, f"{prefix}_AUTH_HEADER_NAME") or "Authorization"),
        auth_header_value=auth_value,
        model=model,
        interface=_text(source, f"{prefix}_INTERFACE") or "video_to_video_multipart",
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


def validate_provider_config(config: AiEditProviderConfig) -> dict[str, Any]:
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
    if config.interface != "video_to_video_multipart":
        invalid.append("interface")
    if "video_to_video" not in config.capabilities:
        invalid.append("capability")
    contract = model_contract(config.provider_name, config.model)
    if not contract.get("known") or not contract.get("video_to_video"):
        invalid.append("model_contract")
    return {
        "ok": not invalid,
        "invalid_fields": invalid,
        "reason": "" if not invalid else "ai_edit_provider_contract_invalid",
        "provider_name": config.provider_name,
        "model": config.model,
        "contract": contract,
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


def parse_provider_payload(payload: dict[str, Any]) -> dict[str, Any]:
    task_id = _nested(payload, "data.task_id", "data.id", "data.id_base", "task_id", "id", "job_id")
    raw_status = _nested(payload, "data.status", "status", "state")
    result_url = _nested(payload, "data.result_url", "data.video_url", "data.url", "result_url", "video_url", "url")
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
    return {
        "provider_task_id": str(task_id or ""),
        "raw_status": raw,
        "status": canonical,
        "result_url": str(result_url or ""),
        "result_url_present": bool(result_url),
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
) -> dict[str, Any]:
    validation = validate_provider_config(config)
    if not validation.get("ok"):
        raise AiEditProviderError(str(validation.get("reason") or "ai_edit_provider_invalid"))
    if submit_source != PUBLIC_FINAL_CONFIRM_SOURCE or not public_user_confirmed:
        raise AiEditProviderError("ai_edit_hidden_submit_blocked")
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
        response = transport(request, timeout=config.timeout_seconds)
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
        response = transport(request, timeout=config.timeout_seconds)
        status, payload = _json_response(response)
    except urllib.error.HTTPError as exc:
        raise AiEditProviderError(f"provider_poll_http_{exc.code}", terminal=False) from exc
    except urllib.error.URLError as exc:
        raise AiEditProviderError("provider_poll_connection_failed", terminal=False) from exc
    if status < 200 or status >= 300:
        raise AiEditProviderError(f"provider_poll_http_{status or 0}", terminal=False)
    return {
        **parse_provider_payload(payload),
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
        response = transport(request, timeout=180)
        status = int(getattr(response, "status", 0) or getattr(response, "code", 0) or 0)
        if status < 200 or status >= 300:
            raise AiEditProviderError(f"provider_result_http_{status or 0}")
        with target.open("wb") as handle:
            while True:
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
) -> dict[str, Any]:
    if not public_confirm_provenance:
        return {"allowed": False, "reason": "public_confirm_provenance_missing"}
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
) -> dict[str, Any]:
    started = now()
    poll_count = 0
    while now() - started <= config.max_wait_seconds:
        sleeper(config.poll_interval_seconds)
        poll_count += 1
        result = poller(config, provider_task_id)
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
