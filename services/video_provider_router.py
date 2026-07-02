"""Video provider chain and routing for real product video rendering."""

from __future__ import annotations

import dataclasses
import hashlib
import os
import shutil
import subprocess
import tempfile
import time
from typing import Any

from providers.video_generic_http_provider import GenericHttpVideoProvider
from providers.video_kling_provider import KlingVideoProvider
from providers.video_veo_provider import VeoVideoProvider
from services.video_provider_base import (
    DisabledVideoProvider,
    VideoArtifactResult,
    VideoGenerationRequest,
    VideoPollResult,
    VideoProviderAdapter,
    mask_provider_task_id,
    normalize_provider_status,
    split_provider_chain,
)


DEFAULT_VIDEO_PROVIDER_CHAIN = "shopaikey_video,key4u_video,toanaas_video,veo,kling,generic_http"
VIDEO_STUB_PROVIDER_NAME = "stub_video"
PUBLIC_NO_VIDEO_PROVIDER_COPY = (
    "Hiện hệ thống dựng video AI chưa sẵn sàng. Bot chưa trừ Xu."
)
VIDEO_CREDIT_BLOCKED_STATUSES = {
    "low",
    "low_credit",
    "exhausted",
    "quota_exhausted",
    "quota_empty",
    "frozen",
    "disabled",
    "blocked",
    "bad_health",
    "health_bad",
    "unhealthy",
}


def _env_flag(env: dict[str, str], name: str, default: str = "0") -> bool:
    return str(env.get(name, default) or default).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(env: dict[str, str], name: str, default: int) -> int:
    try:
        return int(str(env.get(name, str(default)) or str(default)).strip())
    except Exception:
        return int(default)


def _join_url(base: str, endpoint: str) -> str:
    base = str(base or "").strip().rstrip("/")
    endpoint = str(endpoint or "").strip()
    if endpoint.startswith(("http://", "https://")):
        return endpoint
    return base + "/" + endpoint.lstrip("/") if base and endpoint else base or endpoint


def _with_derived(env: dict[str, str], updates: dict[str, str]) -> dict[str, str]:
    result = dict(env)
    for key, value in updates.items():
        if value and not result.get(key):
            result[key] = value
    return result


def _bearer(value: str) -> str:
    token = str(value or "").strip()
    if not token:
        return ""
    return token if token.lower().startswith(("bearer ", "apikey ", "key ")) else f"Bearer {token}"


def _first_env(env: dict[str, str], *names: str) -> str:
    for name in names:
        value = str(env.get(name) or "").strip()
        if value:
            return value
    return ""


def _normalize_credit_status(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not raw or raw in {"none", "null", "n_a", "na", "unknown"}:
        return "unknown"
    aliases = {
        "ok": "ok",
        "ready": "ok",
        "healthy": "ok",
        "has_credit": "ok",
        "sufficient": "ok",
        "available": "ok",
        "normal": "ok",
        "good": "ok",
        "lowcredit": "low_credit",
        "low_balance": "low_credit",
        "out_of_credit": "exhausted",
        "outofcredit": "exhausted",
        "no_credit": "exhausted",
        "no_balance": "exhausted",
        "empty": "exhausted",
        "quota_empty": "quota_exhausted",
        "quota_exceeded": "quota_exhausted",
        "rate_limited": "bad_health",
        "error": "bad_health",
        "failed": "bad_health",
    }
    return aliases.get(raw, raw)


def _provider_credit_prefixes(provider: str) -> list[str]:
    normalized = str(provider or "").strip().lower()
    if normalized == "shopaikey_video":
        return ["SHOPAIKEY_VIDEO", "SHOPAIKEY"]
    if normalized == "key4u_video":
        return ["KEY4U_VIDEO", "KEY4U"]
    if normalized == "toanaas_video":
        return ["VIDEO_TOANAAS", "TOANAAS_VIDEO", "TOANAAS"]
    if normalized == "veo":
        return ["VIDEO_VEO", "VEO"]
    if normalized == "kling":
        return ["VIDEO_KLING", "KLING"]
    if normalized == "generic_http":
        return ["VIDEO_GENERIC_HTTP", "GENERIC_HTTP"]
    return [normalized.upper()]


def provider_credit_status(provider: str, env: dict[str, str] | None = None) -> str:
    data = dict(env or os.environ)
    prefixes = _provider_credit_prefixes(provider)
    flag_suffixes = [
        ("FROZEN", "frozen"),
        ("EXHAUSTED", "exhausted"),
        ("QUOTA_EXHAUSTED", "quota_exhausted"),
        ("LOW_CREDIT", "low_credit"),
        ("LOW_BALANCE", "low_credit"),
        ("HEALTH_BAD", "bad_health"),
        ("DISABLED", "disabled"),
    ]
    for prefix in prefixes:
        for suffix, status in flag_suffixes:
            if _env_flag(data, f"{prefix}_{suffix}", "0"):
                return status
    for suffix in ("CREDIT_STATUS", "BALANCE_STATUS", "HEALTH_STATUS", "STATUS"):
        for prefix in prefixes:
            value = str(data.get(f"{prefix}_{suffix}") or "").strip()
            if value:
                return _normalize_credit_status(value)
    return "unknown"


def provider_credit_allows_selection(status: str) -> bool:
    normalized = _normalize_credit_status(status)
    return normalized not in VIDEO_CREDIT_BLOCKED_STATUSES


def _endpoint_alias(env: dict[str, str], direct_name: str, base_name: str, endpoint_name: str, *legacy_names: str) -> str:
    direct = _first_env(env, direct_name, *legacy_names)
    if direct:
        return direct
    base = str(env.get(base_name) or "").strip()
    endpoint = str(env.get(endpoint_name) or "").strip()
    if base and endpoint:
        return _join_url(base, endpoint)
    return ""


def _runtime_env_name(env: dict[str, str]) -> str:
    return str(
        env.get("APP_ENV")
        or env.get("ENVIRONMENT")
        or env.get("RAILWAY_ENVIRONMENT")
        or env.get("TOAN_AAS_ENV")
        or env.get("PYTHON_ENV")
        or ""
    ).strip().lower()


def _stub_env_allowed(env: dict[str, str]) -> bool:
    runtime = _runtime_env_name(env)
    if runtime in {"development", "dev", "test", "testing", "admin", "local"}:
        return True
    return bool(env.get("PYTEST_CURRENT_TEST")) and runtime not in {"production", "prod"}


class StubVideoProvider:
    provider_name = VIDEO_STUB_PROVIDER_NAME

    def __init__(self, environ: dict[str, str] | None = None):
        self.env = environ or os.environ

    def _enabled(self) -> bool:
        return _env_flag(dict(self.env), "VIDEO_STUB_PROVIDER_ENABLED", "0")

    def _configured(self) -> bool:
        return bool(self._enabled() and _stub_env_allowed(dict(self.env)))

    def capabilities(self) -> dict[str, Any]:
        enabled = self._enabled()
        allowed = _stub_env_allowed(dict(self.env))
        missing: list[str] = []
        if not enabled:
            missing.append("VIDEO_STUB_PROVIDER_ENABLED")
        if enabled and not allowed:
            missing.append("non_production_env")
        return {
            "provider": self.provider_name,
            "enabled": enabled,
            "configured": bool(enabled and allowed),
            "missing": missing,
            "capabilities": ["text_to_video", "image_to_video", "video_to_video", "multi_scene_video", "scene_video"],
            "endpoint_configured": False,
            "submit_url_present": False,
            "poll_url_present": False,
            "endpoint_present": False,
            "auth_configured": False,
            "auth_present": False,
            "model_configured": False,
            "model_present": False,
            "stub_test_only": True,
            "production_disabled": enabled and not allowed,
        }

    def submit_video_job(self, request: VideoGenerationRequest):
        from services.video_provider_base import VideoSubmitResult

        if not self._configured():
            return VideoSubmitResult(ok=False, provider_name=self.provider_name, error_code="stub_provider_disabled")
        task_seed = f"{request.job_id}:{request.prompt}:{time.time()}"
        task_id = "stub-" + hashlib.sha1(task_seed.encode("utf-8", errors="ignore")).hexdigest()[:12]
        return VideoSubmitResult(ok=True, provider_name=self.provider_name, provider_task_id=task_id, provider_status="succeeded")

    def poll_video_job(self, provider_task_id: str):
        return VideoPollResult(ok=True, status="succeeded", provider_name=self.provider_name, provider_task_id=provider_task_id)

    def materialize_result(self, poll_result: VideoPollResult, output_name: str) -> VideoArtifactResult:
        output_dir = os.path.abspath(os.getenv("VIDEO_STUB_PROVIDER_OUTPUT_DIR") or tempfile.gettempdir())
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{output_name or poll_result.provider_task_id or 'stub_video'}.mp4")
        ffmpeg = shutil.which("ffmpeg") or str(os.getenv("FFMPEG_PATH") or "").strip()
        if not ffmpeg:
            return VideoArtifactResult(ok=False, provider_name=self.provider_name, local_path=output_path, error_code="ffmpeg_missing")
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x568:d=1",
            "-vf",
            "format=yuv420p",
            "-movflags",
            "+faststart",
            output_path,
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        except Exception:
            return VideoArtifactResult(ok=False, provider_name=self.provider_name, local_path=output_path, error_code="stub_render_failed")
        size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        return VideoArtifactResult(
            ok=bool(size > 0),
            provider_name=self.provider_name,
            local_path=output_path,
            bytes=size,
            duration=1.0,
            has_video_stream=True,
            has_audio_stream=False,
            error_code="" if size > 0 else "stub_output_empty",
        )


def _generic_adapter_for(name: str, env: dict[str, str]) -> VideoProviderAdapter:
    if name == "toanaas_video":
        derived = _with_derived(
            env,
            {
                "VIDEO_TOANAAS_AUTH_HEADER_NAME": env.get("VIDEO_TOANAAS_AUTH_HEADER_NAME") or "Authorization",
                "VIDEO_TOANAAS_AUTH_HEADER_VALUE": env.get("VIDEO_TOANAAS_AUTH_HEADER_VALUE") or _bearer(env.get("VIDEO_TOANAAS_API_KEY") or ""),
            },
        )
        return GenericHttpVideoProvider(
            provider_name="toanaas_video",
            enabled_env="VIDEO_TOANAAS_ENABLED",
            submit_url_env="VIDEO_TOANAAS_SUBMIT_URL",
            poll_url_env="VIDEO_TOANAAS_POLL_URL",
            auth_header_name_env="VIDEO_TOANAAS_AUTH_HEADER_NAME",
            auth_header_value_env="VIDEO_TOANAAS_AUTH_HEADER_VALUE",
            result_field_env="VIDEO_TOANAAS_RESULT_FIELD",
            model_env="VIDEO_TOANAAS_MODEL",
            capabilities_env="VIDEO_TOANAAS_CAPABILITIES",
            environ=derived,
        )
    if name == "shopaikey_video":
        submit_url = _endpoint_alias(
            env,
            "SHOPAIKEY_VIDEO_SUBMIT_URL",
            "SHOPAIKEY_BASE_URL",
            "SHOPAIKEY_VIDEO_ENDPOINT",
            "SHOPAIKEY_VIDEO_URL",
        )
        poll_url = _endpoint_alias(
            env,
            "SHOPAIKEY_VIDEO_POLL_URL",
            "SHOPAIKEY_BASE_URL",
            "SHOPAIKEY_VIDEO_POLL_ENDPOINT",
            "SHOPAIKEY_VIDEO_STATUS_ENDPOINT",
        )
        derived = _with_derived(
            env,
            {
                "SHOPAIKEY_VIDEO_SUBMIT_URL": submit_url,
                "SHOPAIKEY_VIDEO_POLL_URL": poll_url,
                "SHOPAIKEY_VIDEO_AUTH_HEADER_NAME": env.get("SHOPAIKEY_VIDEO_AUTH_HEADER_NAME") or "Authorization",
                "SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE": env.get("SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE") or _bearer(env.get("SHOPAIKEY_API_KEY") or ""),
            },
        )
        return GenericHttpVideoProvider(
            provider_name="shopaikey_video",
            enabled_env="SHOPAIKEY_VIDEO_ENABLED",
            submit_url_env="SHOPAIKEY_VIDEO_SUBMIT_URL",
            poll_url_env="SHOPAIKEY_VIDEO_POLL_URL",
            auth_header_name_env="SHOPAIKEY_VIDEO_AUTH_HEADER_NAME",
            auth_header_value_env="SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE",
            result_field_env="SHOPAIKEY_VIDEO_RESULT_FIELD",
            model_env="SHOPAIKEY_VIDEO_MODEL",
            capabilities_env="SHOPAIKEY_VIDEO_CAPABILITIES",
            environ=derived,
        )
    if name == "key4u_video":
        submit_url = _endpoint_alias(env, "KEY4U_VIDEO_SUBMIT_URL", "KEY4U_BASE_URL", "KEY4U_VIDEO_ENDPOINT")
        poll_url = _endpoint_alias(env, "KEY4U_VIDEO_POLL_URL", "KEY4U_BASE_URL", "KEY4U_VIDEO_POLL_ENDPOINT")
        derived = _with_derived(
            env,
            {
                "KEY4U_VIDEO_SUBMIT_URL": submit_url,
                "KEY4U_VIDEO_POLL_URL": poll_url,
                "KEY4U_VIDEO_AUTH_HEADER_NAME": env.get("KEY4U_VIDEO_AUTH_HEADER_NAME") or "Authorization",
                "KEY4U_VIDEO_AUTH_HEADER_VALUE": env.get("KEY4U_VIDEO_AUTH_HEADER_VALUE") or _bearer(env.get("KEY4U_API_KEY") or env.get("KEY4U_TOKEN") or ""),
            },
        )
        return GenericHttpVideoProvider(
            provider_name="key4u_video",
            enabled_env="KEY4U_VIDEO_ENABLED",
            submit_url_env="KEY4U_VIDEO_SUBMIT_URL",
            poll_url_env="KEY4U_VIDEO_POLL_URL",
            auth_header_name_env="KEY4U_VIDEO_AUTH_HEADER_NAME",
            auth_header_value_env="KEY4U_VIDEO_AUTH_HEADER_VALUE",
            result_field_env="KEY4U_VIDEO_RESULT_FIELD",
            model_env="KEY4U_VIDEO_MODEL",
            capabilities_env="KEY4U_VIDEO_CAPABILITIES",
            environ=derived,
        )
    if name == "veo":
        return VeoVideoProvider(environ=env)
    if name == "kling":
        return KlingVideoProvider(environ=env)
    if name == "generic_http":
        return GenericHttpVideoProvider(environ=env)
    if name == VIDEO_STUB_PROVIDER_NAME:
        return StubVideoProvider(environ=env)
    return DisabledVideoProvider(name, missing=["unknown_provider"])


def configured_provider_chain(environ: dict[str, str] | None = None) -> list[str]:
    env = environ or os.environ
    return split_provider_chain(env.get("VIDEO_PROVIDER_CHAIN") or DEFAULT_VIDEO_PROVIDER_CHAIN)


def load_video_provider_adapters(environ: dict[str, str] | None = None) -> list[VideoProviderAdapter]:
    env = dict(environ or os.environ)
    adapters: list[VideoProviderAdapter] = []
    for name in configured_provider_chain(env):
        adapters.append(_generic_adapter_for(name, env))
    return adapters


def normalize_capability_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_values = value.replace("|", ",").replace(";", ",").split(",")
    else:
        try:
            raw_values = list(value)
        except TypeError:
            raw_values = [value]
    result: list[str] = []
    aliases = {
        "text_to_video_or_scene_engine": "text_to_video_or_scene_video",
        "text_to_video_or_scene": "text_to_video_or_scene_video",
        "scene_engine": "scene_video",
        "multiscene_video": "multi_scene_video",
        "multi_scene": "multi_scene_video",
    }
    for item in raw_values:
        token = str(item or "").strip().lower().replace("-", "_")
        token = aliases.get(token, token)
        if token and token not in result:
            result.append(token)
    return result


def capability_options(required_capability: str) -> list[str]:
    cap = (normalize_capability_values([required_capability]) or ["text_to_video"])[0]
    mapping = {
        "text_to_video_or_scene_video": ["multi_scene_video", "scene_video", "text_to_video"],
        "text_to_video_or_scene_engine": ["multi_scene_video", "scene_video", "text_to_video"],
        "multi_scene_video": ["multi_scene_video", "scene_video", "text_to_video"],
        "scene_video": ["scene_video", "multi_scene_video", "text_to_video"],
        "delegates_to_selected_product": ["multi_scene_video", "scene_video", "text_to_video", "image_to_video", "video_to_video"],
    }
    return mapping.get(cap, [cap] if cap else ["text_to_video"])


def provider_supports(adapter: VideoProviderAdapter, required_capability: str) -> bool:
    caps = adapter.capabilities()
    if not caps.get("configured"):
        return False
    supported = set(normalize_capability_values(caps.get("capabilities") or []))
    return any(cap in supported for cap in capability_options(required_capability))


def preferred_provider_capability(adapter: VideoProviderAdapter, required_capability: str) -> str:
    caps = adapter.capabilities()
    supported = set(normalize_capability_values(caps.get("capabilities") or []))
    for cap in capability_options(required_capability):
        if cap in supported:
            return cap
    return (capability_options(required_capability) or ["text_to_video"])[0]


def provider_status_payload(environ: dict[str, str] | None = None) -> dict[str, Any]:
    env = dict(environ or os.environ)
    adapters = load_video_provider_adapters(env)
    if VIDEO_STUB_PROVIDER_NAME not in [adapter.provider_name for adapter in adapters]:
        adapters.append(StubVideoProvider(environ=env))
    providers = []
    for adapter in adapters:
        caps = dict(adapter.capabilities())
        missing = list(caps.get("missing") or [])
        invalid_fields = list(caps.get("invalid_fields") or [])
        invalid_env = list(caps.get("invalid_env") or [])
        config_blocker = str(caps.get("config_blocker") or caps.get("blocker") or "")
        provider_name = str(caps.get("provider") or adapter.provider_name or "").strip()
        credit_status = provider_credit_status(provider_name, env)
        credit_ok = provider_credit_allows_selection(credit_status)
        configured = bool(caps.get("configured"))
        selection_blocker = ""
        if configured and not credit_ok:
            selection_blocker = f"credit_{credit_status}"
        elif not configured:
            selection_blocker = config_blocker or "not_configured"
        providers.append(
            {
                "provider": provider_name,
                "enabled": bool(caps.get("enabled")),
                "configured": configured,
                "missing": missing,
                "invalid_fields": invalid_fields,
                "invalid_env": invalid_env,
                "blocker": config_blocker,
                "config_blocker": config_blocker,
                "capabilities": normalize_capability_values(caps.get("capabilities") or []),
                "endpoint_configured": bool(caps.get("endpoint_configured")),
                "endpoint_present": bool(caps.get("endpoint_present") or caps.get("endpoint_configured")),
                "submit_url_present": bool(caps.get("submit_url_present") or caps.get("endpoint_configured")),
                "poll_url_present": bool(caps.get("poll_url_present") or caps.get("endpoint_configured")),
                "submit_url_configured": bool(caps.get("submit_url_configured")),
                "poll_url_configured": bool(caps.get("poll_url_configured")),
                "model_configured": bool(caps.get("model_configured")),
                "model_present": bool(caps.get("model_present") or caps.get("model_configured")),
                "auth_configured": bool(caps.get("auth_configured")),
                "auth_present": bool(caps.get("auth_present") or caps.get("auth_configured")),
                "stub_test_only": bool(caps.get("stub_test_only")),
                "production_disabled": bool(caps.get("production_disabled")),
                "credit_status": credit_status,
                "credit_ok": bool(credit_ok),
                "fallback_only": bool(provider_name == "key4u_video" or not credit_ok),
                "selection_blocker": selection_blocker,
            }
        )
    ready = [item["provider"] for item in providers if item["configured"] and item.get("credit_ok")]
    enabled = [item["provider"] for item in providers if item["enabled"]]
    configured = [item["provider"] for item in providers if item["configured"]]
    near_ready = [
        item["provider"]
        for item in providers
        if not item["configured"] and (item["endpoint_present"] or item["auth_present"] or item["enabled"])
    ]
    missing_env = {item["provider"]: item["missing"] for item in providers if item["missing"]}
    invalid_env = {item["provider"]: item["invalid_env"] for item in providers if item.get("invalid_env")}
    invalid_config = [item["provider"] for item in providers if item.get("config_blocker")]
    selected_provider = ready[0] if ready else ""
    fallback_order = [item["provider"] for item in providers if item["configured"] and item["provider"] != selected_provider]
    usable_fallback_order = [
        item["provider"]
        for item in providers
        if item["configured"] and item.get("credit_ok") and item["provider"] != selected_provider
    ]
    skipped_providers = [
        {"provider": item["provider"], "reason": item.get("selection_blocker") or f"credit_{item.get('credit_status')}"}
        for item in providers
        if (item["configured"] and not item.get("credit_ok")) or (not item["configured"] and item.get("selection_blocker") != "not_configured")
    ]
    if ready:
        reason = "provider_ready_and_has_credit"
    elif not enabled:
        reason = "chưa bật provider nào"
    elif invalid_config:
        reason = "provider_config_placeholder_or_invalid_url"
    elif not configured:
        reason = "provider chưa đủ endpoint/auth"
    elif skipped_providers:
        reason = "provider_credit_unavailable"
    else:
        reason = "provider thiếu capability"
    return {
        "ok": bool(ready),
        "ready": bool(ready),
        "reason": reason,
        "summary_reason": reason,
        "provider_chain": configured_provider_chain(env),
        "effective_provider_chain": configured_provider_chain(env),
        "ready_provider_order": ready,
        "first_ready_provider": selected_provider,
        "selected_provider": selected_provider,
        "selection_reason": reason,
        "fallback_order": fallback_order,
        "usable_fallback_order": usable_fallback_order,
        "skipped_providers": skipped_providers,
        "enabled_count": len(enabled),
        "configured_count": len(configured),
        "enabled_providers": enabled,
        "configured_providers": configured,
        "near_ready_providers": near_ready,
        "missing_env": missing_env,
        "invalid_env": invalid_env,
        "invalid_config_providers": invalid_config,
        "providers": providers,
        "public_no_provider_copy": PUBLIC_NO_VIDEO_PROVIDER_COPY,
    }


def provider_candidate_adapters(
    required_capability: str,
    environ: dict[str, str] | None = None,
    status: dict[str, Any] | None = None,
) -> list[VideoProviderAdapter]:
    env = dict(environ or os.environ)
    payload = dict(status or provider_status_payload(env))
    status_by_provider = {str(item.get("provider") or ""): item for item in (payload.get("providers") or []) if isinstance(item, dict)}
    candidates: list[VideoProviderAdapter] = []
    for adapter in load_video_provider_adapters(env):
        item = status_by_provider.get(adapter.provider_name, {})
        if item and not item.get("credit_ok", True):
            continue
        if provider_supports(adapter, required_capability):
            candidates.append(adapter)
    return candidates


def select_video_provider(required_capability: str, environ: dict[str, str] | None = None) -> tuple[VideoProviderAdapter | None, dict[str, Any]]:
    status = provider_status_payload(environ)
    for adapter in provider_candidate_adapters(required_capability, environ, status):
        return adapter, status
    return None, status


def _safe_exception_message(value: Any, limit: int = 220) -> str:
    text = str(value or "").replace("\n", " ").replace("\r", " ")
    for marker in ("Bearer ", "token=", "key=", "secret=", "authorization="):
        idx = text.lower().find(marker.lower())
        if idx >= 0:
            text = text[: idx + len(marker)] + "***"
            break
    return text[:limit]


def _debug_http_status(raw: dict[str, Any] | None = None, key: str = "http_status") -> int:
    raw = dict(raw or {})
    for candidate in (key, "http_status", "status_code", "submit_http_status", "poll_http_status"):
        try:
            value = int(raw.get(candidate) or 0)
        except Exception:
            value = 0
        if value:
            return value
    return 0


def provider_exception_result(exc: BaseException, *, provider: str = "", stage: str = "submit_request", status: dict[str, Any] | None = None) -> dict[str, Any]:
    blocker = str(getattr(exc, "blocker", "") or "")
    if not blocker:
        if isinstance(exc, ValueError):
            blocker = "provider_unhandled_exception"
        elif isinstance(exc, (KeyError, TypeError)):
            blocker = "provider_submit_response_invalid_shape"
        elif isinstance(exc, TimeoutError):
            blocker = "provider_submit_http_error"
        else:
            blocker = "provider_unhandled_exception"
    debug = dict(getattr(exc, "debug", {}) or {})
    return {
        "ok": False,
        **debug,
        "provider_router_called": True,
        "provider_attempted": stage != "payload_build",
        "provider_submit_called": stage == "submit_request",
        "provider": provider,
        "selected_provider": provider,
        "provider_error": blocker,
        "blocker": blocker,
        "provider_status": "failed",
        "smoke_stage": str(getattr(exc, "stage", "") or debug.get("smoke_stage") or stage),
        "exception_class": type(exc).__name__,
        "exception_message_safe": _safe_exception_message(exc),
        "provider_submit_exception_class": type(exc).__name__ if stage == "submit_request" else "",
        "provider_submit_exception_message_safe": _safe_exception_message(exc) if stage == "submit_request" else "",
        "provider_readiness": status or {},
    }


def _merge_contract_debug(target: dict[str, Any], raw: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = dict(raw or {})
    for key in (
        "smoke_stage",
        "exception_class",
        "exception_message_safe",
        "submit_url_configured",
        "poll_url_configured",
        "auth_configured",
        "payload_has_prompt",
        "payload_has_duration",
        "payload_has_ratio",
        "payload_keys",
        "prompt_chars",
        "duration",
        "ratio",
        "quality",
        "scenes_count",
        "submit_response_shape",
        "provider_task_id_present",
        "provider_task_id_masked",
        "poll_response_shape",
        "provider_status_raw",
        "result_field_path",
        "task_id_field_path",
        "video_id_field_path",
        "provider_submit_url_configured",
        "provider_submit_url_host",
        "provider_auth_header_name",
        "provider_auth_value_present",
        "provider_auth_scheme_prefix",
        "provider_payload_keys",
        "provider_payload_model",
        "provider_response_http_status",
        "provider_response_body_shape",
        "provider_submit_exception_class",
        "provider_submit_exception_message_safe",
    ):
        if key in raw and key not in target:
            target[key] = raw.get(key)
    if raw.get("exception_class") and not target.get("provider_submit_exception_class"):
        target["provider_submit_exception_class"] = raw.get("exception_class")
    if raw.get("exception_message_safe") and not target.get("provider_submit_exception_message_safe"):
        target["provider_submit_exception_message_safe"] = raw.get("exception_message_safe")
    if "provider_submit_blocker" in raw:
        target["provider_submit_stage"] = raw.get("smoke_stage") or "submit_response_parse"
        target["provider_submit_blocker"] = raw.get("provider_submit_blocker")
    if "provider_poll_blocker" in raw:
        target["provider_poll_blocker"] = raw.get("provider_poll_blocker")
    if "provider_result_blocker" in raw:
        target["provider_result_blocker"] = raw.get("provider_result_blocker")
    if "submit_http_status" in raw or "http_status" in raw or "status_code" in raw:
        target["provider_submit_http_status"] = _debug_http_status(raw, "submit_http_status")
    if "poll_http_status" in raw:
        target["provider_poll_http_status"] = _debug_http_status(raw, "poll_http_status")
    if raw.get("result_url_present") is not None:
        target["provider_result_url_present"] = bool(raw.get("result_url_present"))
    return target


def _config_validation_blocker_from_status(status: dict[str, Any], required_capability: str) -> dict[str, Any]:
    for item in status.get("providers") or []:
        if not isinstance(item, dict):
            continue
        if not item.get("config_blocker") and not item.get("blocker"):
            continue
        supported = set(normalize_capability_values(item.get("capabilities") or []))
        if not any(cap in supported for cap in capability_options(required_capability)):
            continue
        invalid_fields = [str(field) for field in (item.get("invalid_fields") or [])]
        if "submit_url" in invalid_fields:
            blocker = "provider_config_invalid_submit_url"
        elif "poll_url" in invalid_fields:
            blocker = "provider_config_invalid_poll_url"
        elif "auth" in invalid_fields:
            blocker = "provider_config_invalid_auth"
        else:
            blocker = str(item.get("config_blocker") or item.get("blocker") or "provider_config_placeholder_or_invalid_url")
        return {
            "provider": str(item.get("provider") or ""),
            "blocker": blocker,
            "invalid_fields": invalid_fields,
            "invalid_env": [str(env_name) for env_name in (item.get("invalid_env") or [])],
        }
    return {}


def run_provider_generation(
    request: VideoGenerationRequest,
    *,
    output_dir: str,
    environ: dict[str, str] | None = None,
    sleep_func=time.sleep,
) -> dict[str, Any]:
    env = dict(environ or os.environ)
    status = provider_status_payload(env)
    required_capability_original = str(request.required_capability or "").strip()
    normalized_capability_candidates = capability_options(required_capability_original)
    candidate_adapters = provider_candidate_adapters(request.required_capability, env, status)
    adapter = candidate_adapters[0] if candidate_adapters else None
    provider_candidates = [item.provider_name for item in candidate_adapters]
    allow_pending_result = bool(
        (request.metadata or {}).get("product_video")
        or (request.metadata or {}).get("allow_provider_pending")
        or (request.metadata or {}).get("interactive_product")
    )
    base_debug = {
        "provider_router_called": True,
        "required_capability_original": required_capability_original,
        "normalized_capability_candidates": list(normalized_capability_candidates),
        "provider_candidates_count": len([item for item in provider_candidates if item]),
        "selected_provider": adapter.provider_name if adapter else "",
        "selected_capability": preferred_provider_capability(adapter, request.required_capability) if adapter else "",
        "provider_selection_blocker": "" if adapter else "provider_capability_missing",
        "provider_chain": list(status.get("provider_chain") or []),
        "effective_provider_chain": list(status.get("effective_provider_chain") or status.get("provider_chain") or []),
        "fallback_order": list(status.get("fallback_order") or []),
        "usable_fallback_order": list(status.get("usable_fallback_order") or []),
        "fallback_used": False,
        "fallback_reason": "",
        "skipped_providers": list(status.get("skipped_providers") or []),
        "provider_submit_called": False,
        "provider_submit_http_status": 0,
        "provider_task_id_saved": False,
        "provider_poll_called": False,
        "provider_result_url_present": False,
    }
    if adapter is None:
        config_blocker = _config_validation_blocker_from_status(status, request.required_capability)
        if config_blocker:
            selected = str(config_blocker.get("provider") or "")
            return {
                "ok": False,
                **base_debug,
                "selected_provider": selected,
                "provider": selected,
                "provider_selection_blocker": str(config_blocker.get("blocker") or "provider_config_placeholder_or_invalid_url"),
                "provider_attempted": False,
                "provider_error": str(config_blocker.get("blocker") or "provider_config_placeholder_or_invalid_url"),
                "blocker": str(config_blocker.get("blocker") or "provider_config_placeholder_or_invalid_url"),
                "provider_status": "config_invalid",
                "smoke_stage": "config_validation",
                "exception_class": "",
                "exception_message_safe": "",
                "submit_url_configured": False,
                "poll_url_configured": False,
                "auth_configured": False,
                "payload_has_prompt": False,
                "payload_has_duration": False,
                "payload_has_ratio": False,
                "invalid_fields": list(config_blocker.get("invalid_fields") or []),
                "invalid_env": list(config_blocker.get("invalid_env") or []),
                "no_charge": True,
                "public_message": PUBLIC_NO_VIDEO_PROVIDER_COPY,
                "provider_readiness": status,
            }
        return {
            "ok": False,
            **base_debug,
            "provider_attempted": False,
            "provider_error": "provider_capability_missing",
            "blocker": "provider_capability_missing",
            "provider_status": "not_attempted",
            "provider_readiness": status,
        }

    def _submit_http_status(raw: dict[str, Any] | None) -> int:
        try:
            return int((raw or {}).get("http_status") or (raw or {}).get("status_code") or 0)
        except Exception:
            return 0

    attempt_failures: list[dict[str, Any]] = []
    first_fallback_reason = ""
    for attempt_index, current_adapter in enumerate(candidate_adapters):
        fallback_used = attempt_index > 0
        fallback_reason = first_fallback_reason if fallback_used else ""
        selected_capability = preferred_provider_capability(current_adapter, request.required_capability)
        provider_request = dataclasses.replace(request, required_capability=selected_capability)

        def _attempt_base() -> dict[str, Any]:
            return {
                **base_debug,
                "selected_provider": current_adapter.provider_name,
                "selected_capability": selected_capability,
                "provider": current_adapter.provider_name,
                "provider_selection_blocker": "",
                "fallback_used": fallback_used,
                "fallback_reason": fallback_reason,
                "provider_attempted": True,
                "provider_attempts": list(attempt_failures),
            }

        def _record_failure(reason: str) -> None:
            nonlocal first_fallback_reason
            clean_reason = str(reason or "provider_failed").strip() or "provider_failed"
            attempt_failures.append({"provider": current_adapter.provider_name, "reason": clean_reason})
            if not first_fallback_reason:
                first_fallback_reason = clean_reason

        try:
            submit = current_adapter.submit_video_job(provider_request)
        except Exception as exc:
            exc_payload = {
                **_attempt_base(),
                **provider_exception_result(exc, provider=current_adapter.provider_name, stage="submit_request", status=status),
                "fallback_used": attempt_index > 0,
                "fallback_reason": first_fallback_reason if attempt_index > 0 else "",
            }
            blocker = str(exc_payload.get("blocker") or "provider_unhandled_exception")
            if attempt_index + 1 < len(candidate_adapters):
                _record_failure(blocker)
                continue
            _record_failure(blocker)
            if allow_pending_result:
                exc_payload["no_charge"] = True
            exc_payload["provider_attempts"] = list(attempt_failures)
            return exc_payload
        submit_http_status = _submit_http_status(submit.raw)
        if not submit.ok:
            blocker = submit.error_code or "provider_submit_failed"
            if attempt_index + 1 < len(candidate_adapters):
                _record_failure(blocker)
                continue
            _record_failure(blocker)
            payload = {
                "ok": False,
                **_attempt_base(),
                "fallback_used": attempt_index > 0,
                "fallback_reason": first_fallback_reason if attempt_index > 0 else "",
                "provider_submit_called": True,
                "provider_submit_http_status": submit_http_status,
                "provider_task_id_saved": bool(submit.provider_task_id),
                "provider_error": blocker,
                "blocker": blocker,
                "provider_status": submit.provider_status or "failed",
                "provider_task_ids": [submit.provider_task_id] if submit.provider_task_id else [],
                "provider_readiness": status,
            }
            return _merge_contract_debug(payload, submit.raw)
        result_url = submit.result_url or submit.file_url
        poll_result = VideoPollResult(
            ok=True,
            status=normalize_provider_status(submit.provider_status, has_result_url=bool(result_url)),
            provider_name=current_adapter.provider_name,
            provider_task_id=submit.provider_task_id,
            provider_video_id=submit.provider_video_id,
            result_url=result_url,
            file_url=result_url,
            raw_status=submit.provider_status,
        )
        if not result_url:
            max_attempts = max(1, _env_int(env, "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS", 90))
            interval = max(0, _env_int(env, "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS", 10))
            for attempt in range(1, max_attempts + 1):
                if attempt > 1 and interval:
                    sleep_func(interval)
                try:
                    poll_result = current_adapter.poll_video_job(submit.provider_task_id or submit.provider_video_id)
                except Exception as exc:
                    exc_payload = {
                        **_attempt_base(),
                        **provider_exception_result(exc, provider=current_adapter.provider_name, stage="poll_request", status=status),
                        "fallback_used": attempt_index > 0,
                        "fallback_reason": first_fallback_reason if attempt_index > 0 else "",
                        "provider_submit_called": True,
                        "provider_submit_http_status": submit_http_status,
                        "provider_task_id_saved": bool(submit.provider_task_id),
                        "provider_poll_called": True,
                        "provider_task_ids": [submit.provider_task_id] if submit.provider_task_id else [],
                    }
                    blocker = str(exc_payload.get("blocker") or "provider_unhandled_exception")
                    if attempt_index + 1 < len(candidate_adapters):
                        _record_failure(blocker)
                        break
                    _record_failure(blocker)
                    exc_payload["provider_attempts"] = list(attempt_failures)
                    return _merge_contract_debug(exc_payload, submit.raw)
                poll_result.status = normalize_provider_status(poll_result.status, has_result_url=bool(poll_result.result_url or poll_result.file_url))
                if poll_result.status == "succeeded" and (poll_result.result_url or poll_result.file_url):
                    break
                if poll_result.status in {"failed", "cancelled"}:
                    blocker = poll_result.error_code or f"provider_poll_{poll_result.status}"
                    if attempt_index + 1 < len(candidate_adapters):
                        _record_failure(blocker)
                        break
                    _record_failure(blocker)
                    payload = {
                        "ok": False,
                        **_attempt_base(),
                        "fallback_used": attempt_index > 0,
                        "fallback_reason": first_fallback_reason if attempt_index > 0 else "",
                        "provider_submit_called": True,
                        "provider_submit_http_status": submit_http_status,
                        "provider_task_id_saved": bool(submit.provider_task_id),
                        "provider_poll_called": True,
                        "provider_error": blocker,
                        "blocker": blocker,
                        "provider_status": poll_result.status,
                        "provider_task_ids": [submit.provider_task_id] if submit.provider_task_id else [],
                        "provider_readiness": status,
                    }
                    return _merge_contract_debug(_merge_contract_debug(payload, submit.raw), getattr(poll_result, "raw", {}))
            else:
                if allow_pending_result and (submit.provider_task_id or submit.provider_video_id) and poll_result.status in {"queued", "running"}:
                    payload = {
                        "ok": False,
                        **_attempt_base(),
                        "fallback_used": attempt_index > 0,
                        "fallback_reason": first_fallback_reason if attempt_index > 0 else "",
                        "provider_submit_called": True,
                        "provider_submit_http_status": submit_http_status,
                        "provider_task_id_saved": bool(submit.provider_task_id or submit.provider_video_id),
                        "provider_poll_called": True,
                        "provider_result_url_present": False,
                        "provider_error": "provider_in_progress",
                        "blocker": "provider_in_progress",
                        "continue_polling": True,
                        "normalized_provider_status": poll_result.status,
                        "provider_status": poll_result.status,
                        "provider_task_ids": [submit.provider_task_id] if submit.provider_task_id else [],
                        "provider_video_ids": [submit.provider_video_id] if submit.provider_video_id else [],
                        "provider_readiness": status,
                        "no_charge": True,
                    }
                    return _merge_contract_debug(_merge_contract_debug(payload, submit.raw), getattr(poll_result, "raw", {}))
                blocker = "provider_timeout"
                if attempt_index + 1 < len(candidate_adapters):
                    _record_failure(blocker)
                    continue
                _record_failure(blocker)
                payload = {
                    "ok": False,
                    **_attempt_base(),
                    "fallback_used": attempt_index > 0,
                    "fallback_reason": first_fallback_reason if attempt_index > 0 else "",
                    "provider_submit_called": True,
                    "provider_submit_http_status": submit_http_status,
                    "provider_task_id_saved": bool(submit.provider_task_id),
                    "provider_poll_called": True,
                    "provider_error": blocker,
                    "blocker": blocker,
                    "provider_status": "timeout",
                    "provider_task_ids": [submit.provider_task_id] if submit.provider_task_id else [],
                    "provider_readiness": status,
                }
                return _merge_contract_debug(_merge_contract_debug(payload, submit.raw), getattr(poll_result, "raw", {}))
            if attempt_failures and attempt_failures[-1].get("provider") == current_adapter.provider_name:
                continue
        if not (poll_result.result_url or poll_result.file_url):
            blocker = "provider_result_url_missing"
            if attempt_index + 1 < len(candidate_adapters):
                _record_failure(blocker)
                continue
            _record_failure(blocker)
            payload = {
                "ok": False,
                **_attempt_base(),
                "fallback_used": attempt_index > 0,
                "fallback_reason": first_fallback_reason if attempt_index > 0 else "",
                "provider_submit_called": True,
                "provider_submit_http_status": submit_http_status,
                "provider_task_id_saved": bool(submit.provider_task_id),
                "provider_poll_called": bool(not result_url),
                "provider_result_url_present": False,
                "provider_error": blocker,
                "blocker": blocker,
                "provider_status": poll_result.status,
                "provider_task_ids": [submit.provider_task_id] if submit.provider_task_id else [],
                "provider_readiness": status,
            }
            return _merge_contract_debug(_merge_contract_debug(payload, submit.raw), getattr(poll_result, "raw", {}))
        try:
            artifact: VideoArtifactResult = current_adapter.materialize_result(poll_result, str(request.job_id or submit.provider_task_id))
        except Exception as exc:
            exc_payload = {
                **_attempt_base(),
                **provider_exception_result(exc, provider=current_adapter.provider_name, stage="download", status=status),
                "fallback_used": attempt_index > 0,
                "fallback_reason": first_fallback_reason if attempt_index > 0 else "",
                "provider_submit_called": True,
                "provider_submit_http_status": submit_http_status,
                "provider_task_id_saved": bool(submit.provider_task_id),
                "provider_poll_called": bool(not result_url),
                "provider_result_url_present": bool(poll_result.result_url or poll_result.file_url),
                "provider_task_ids": [submit.provider_task_id] if submit.provider_task_id else [],
            }
            blocker = str(exc_payload.get("blocker") or "provider_unhandled_exception")
            if attempt_index + 1 < len(candidate_adapters):
                _record_failure(blocker)
                continue
            _record_failure(blocker)
            exc_payload["provider_attempts"] = list(attempt_failures)
            return _merge_contract_debug(_merge_contract_debug(exc_payload, submit.raw), getattr(poll_result, "raw", {}))
        if not artifact.ok:
            blocker = artifact.error_code or "provider_download_failed"
            if attempt_index + 1 < len(candidate_adapters):
                _record_failure(blocker)
                continue
            _record_failure(blocker)
            payload = {
                "ok": False,
                **_attempt_base(),
                "fallback_used": attempt_index > 0,
                "fallback_reason": first_fallback_reason if attempt_index > 0 else "",
                "provider_submit_called": True,
                "provider_submit_http_status": submit_http_status,
                "provider_task_id_saved": bool(submit.provider_task_id),
                "provider_poll_called": bool(not result_url),
                "provider_result_url_present": True,
                "provider_error": blocker,
                "blocker": blocker,
                "provider_status": poll_result.status,
                "provider_task_ids": [submit.provider_task_id] if submit.provider_task_id else [],
                "provider_video_ids": [submit.provider_video_id] if submit.provider_video_id else [],
                "provider_task_id_masked": mask_provider_task_id(submit.provider_task_id),
                "result_url_present": True,
                "download_status": artifact.error_code or "failed",
                "provider_readiness": status,
            }
            payload["provider_result_blocker"] = payload["blocker"]
            return _merge_contract_debug(_merge_contract_debug(payload, submit.raw), getattr(poll_result, "raw", {}))
        payload = {
            "ok": True,
            **_attempt_base(),
            "provider_submit_called": True,
            "provider_submit_http_status": submit_http_status,
            "provider_task_id_saved": bool(submit.provider_task_id),
            "provider_poll_called": bool(not result_url),
            "provider_result_url_present": True,
            "provider_task_ids": [submit.provider_task_id] if submit.provider_task_id else [],
            "provider_video_ids": [submit.provider_video_id] if submit.provider_video_id else [],
            "provider_task_id_masked": mask_provider_task_id(submit.provider_task_id),
            "provider_status": "downloaded",
            "result_url_present": True,
            "download_status": "downloaded",
            "output_path": artifact.local_path,
            "local_path": artifact.local_path,
            "bytes": artifact.bytes,
            "duration": artifact.duration,
            "has_video_stream": artifact.has_video_stream,
            "has_audio_stream": artifact.has_audio_stream,
            "artifact_hash": artifact.artifact_hash,
            "provider_readiness": status,
        }
        return _merge_contract_debug(_merge_contract_debug(payload, submit.raw), getattr(poll_result, "raw", {}))
    return {
        "ok": False,
        **base_debug,
        "provider_attempted": False,
        "provider_error": "provider_capability_missing",
        "blocker": "provider_capability_missing",
        "provider_status": "not_attempted",
        "provider_readiness": status,
    }
