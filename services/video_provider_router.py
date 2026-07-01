"""Video provider chain and routing for real product video rendering."""

from __future__ import annotations

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


DEFAULT_VIDEO_PROVIDER_CHAIN = "toanaas_video,key4u_video,shopaikey_video,veo,kling,generic_http"
VIDEO_STUB_PROVIDER_NAME = "stub_video"
PUBLIC_NO_VIDEO_PROVIDER_COPY = (
    "TOAN AAS chưa có máy dựng video phù hợp cho kiểu video này lúc này. "
    "Hệ thống chưa trừ Xu. Anh/chị có thể thử kiểu video khác hoặc quay lại sau."
)


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


def capability_options(required_capability: str) -> list[str]:
    cap = str(required_capability or "").strip()
    mapping = {
        "text_to_video_or_scene_video": ["text_to_video", "scene_video", "multi_scene_video"],
        "multi_scene_video": ["multi_scene_video", "scene_video", "text_to_video"],
        "scene_video": ["scene_video", "text_to_video", "multi_scene_video"],
        "delegates_to_selected_product": ["text_to_video", "scene_video", "image_to_video", "video_to_video", "multi_scene_video"],
    }
    return mapping.get(cap, [cap] if cap else ["text_to_video"])


def provider_supports(adapter: VideoProviderAdapter, required_capability: str) -> bool:
    caps = adapter.capabilities()
    if not caps.get("configured"):
        return False
    supported = {str(item) for item in caps.get("capabilities") or []}
    return any(cap in supported for cap in capability_options(required_capability))


def provider_status_payload(environ: dict[str, str] | None = None) -> dict[str, Any]:
    env = dict(environ or os.environ)
    adapters = load_video_provider_adapters(env)
    if VIDEO_STUB_PROVIDER_NAME not in [adapter.provider_name for adapter in adapters]:
        adapters.append(StubVideoProvider(environ=env))
    providers = []
    for adapter in adapters:
        caps = dict(adapter.capabilities())
        missing = list(caps.get("missing") or [])
        providers.append(
            {
                "provider": caps.get("provider") or adapter.provider_name,
                "enabled": bool(caps.get("enabled")),
                "configured": bool(caps.get("configured")),
                "missing": missing,
                "capabilities": list(caps.get("capabilities") or []),
                "endpoint_configured": bool(caps.get("endpoint_configured")),
                "endpoint_present": bool(caps.get("endpoint_present") or caps.get("endpoint_configured")),
                "submit_url_present": bool(caps.get("submit_url_present") or caps.get("endpoint_configured")),
                "poll_url_present": bool(caps.get("poll_url_present") or caps.get("endpoint_configured")),
                "model_configured": bool(caps.get("model_configured")),
                "model_present": bool(caps.get("model_present") or caps.get("model_configured")),
                "auth_configured": bool(caps.get("auth_configured")),
                "auth_present": bool(caps.get("auth_present") or caps.get("auth_configured")),
                "stub_test_only": bool(caps.get("stub_test_only")),
                "production_disabled": bool(caps.get("production_disabled")),
            }
        )
    ready = [item["provider"] for item in providers if item["configured"]]
    enabled = [item["provider"] for item in providers if item["enabled"]]
    configured = [item["provider"] for item in providers if item["configured"]]
    near_ready = [
        item["provider"]
        for item in providers
        if not item["configured"] and (item["endpoint_present"] or item["auth_present"] or item["enabled"])
    ]
    missing_env = {item["provider"]: item["missing"] for item in providers if item["missing"]}
    if ready:
        reason = "ready"
    elif not enabled:
        reason = "chưa bật provider nào"
    elif not configured:
        reason = "provider chưa đủ endpoint/auth"
    else:
        reason = "provider thiếu capability"
    return {
        "ok": bool(ready),
        "ready": bool(ready),
        "reason": reason,
        "summary_reason": reason,
        "provider_chain": configured_provider_chain(env),
        "ready_provider_order": ready,
        "first_ready_provider": ready[0] if ready else "",
        "enabled_count": len(enabled),
        "configured_count": len(configured),
        "enabled_providers": enabled,
        "configured_providers": configured,
        "near_ready_providers": near_ready,
        "missing_env": missing_env,
        "providers": providers,
        "public_no_provider_copy": PUBLIC_NO_VIDEO_PROVIDER_COPY,
    }


def select_video_provider(required_capability: str, environ: dict[str, str] | None = None) -> tuple[VideoProviderAdapter | None, dict[str, Any]]:
    adapters = load_video_provider_adapters(environ)
    status = provider_status_payload(environ)
    for adapter in adapters:
        if provider_supports(adapter, required_capability):
            return adapter, status
    return None, status


def run_provider_generation(
    request: VideoGenerationRequest,
    *,
    output_dir: str,
    environ: dict[str, str] | None = None,
    sleep_func=time.sleep,
) -> dict[str, Any]:
    env = dict(environ or os.environ)
    adapter, status = select_video_provider(request.required_capability, env)
    if adapter is None:
        return {
            "ok": False,
            "provider_attempted": False,
            "provider_error": "provider_capability_missing",
            "blocker": "provider_capability_missing",
            "provider_status": "not_attempted",
            "provider_readiness": status,
        }
    submit = adapter.submit_video_job(request)
    if not submit.ok:
        return {
            "ok": False,
            "provider_attempted": True,
            "provider": adapter.provider_name,
            "provider_error": submit.error_code or "provider_submit_failed",
            "blocker": submit.error_code or "provider_submit_failed",
            "provider_status": submit.provider_status or "failed",
            "provider_task_ids": [submit.provider_task_id] if submit.provider_task_id else [],
            "provider_readiness": status,
        }
    result_url = submit.result_url or submit.file_url
    poll_result = VideoPollResult(
        ok=True,
        status=normalize_provider_status(submit.provider_status, has_result_url=bool(result_url)),
        provider_name=adapter.provider_name,
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
            poll_result = adapter.poll_video_job(submit.provider_task_id or submit.provider_video_id)
            poll_result.status = normalize_provider_status(poll_result.status, has_result_url=bool(poll_result.result_url or poll_result.file_url))
            if poll_result.status == "succeeded" and (poll_result.result_url or poll_result.file_url):
                break
            if poll_result.status in {"failed", "cancelled"}:
                return {
                    "ok": False,
                    "provider_attempted": True,
                    "provider": adapter.provider_name,
                    "provider_error": poll_result.error_code or f"provider_poll_{poll_result.status}",
                    "blocker": poll_result.error_code or f"provider_poll_{poll_result.status}",
                    "provider_status": poll_result.status,
                    "provider_task_ids": [submit.provider_task_id] if submit.provider_task_id else [],
                    "provider_readiness": status,
                }
        else:
            return {
                "ok": False,
                "provider_attempted": True,
                "provider": adapter.provider_name,
                "provider_error": "provider_timeout",
                "blocker": "provider_timeout",
                "provider_status": "timeout",
                "provider_task_ids": [submit.provider_task_id] if submit.provider_task_id else [],
                "provider_readiness": status,
            }
    if not (poll_result.result_url or poll_result.file_url):
        return {
            "ok": False,
            "provider_attempted": True,
            "provider": adapter.provider_name,
            "provider_error": "provider_result_url_missing",
            "blocker": "provider_result_url_missing",
            "provider_status": poll_result.status,
            "provider_task_ids": [submit.provider_task_id] if submit.provider_task_id else [],
            "provider_readiness": status,
        }
    artifact: VideoArtifactResult = adapter.materialize_result(poll_result, str(request.job_id or submit.provider_task_id))
    if not artifact.ok:
        return {
            "ok": False,
            "provider_attempted": True,
            "provider": adapter.provider_name,
            "provider_error": artifact.error_code or "provider_download_failed",
            "blocker": artifact.error_code or "provider_download_failed",
            "provider_status": poll_result.status,
            "provider_task_ids": [submit.provider_task_id] if submit.provider_task_id else [],
            "provider_video_ids": [submit.provider_video_id] if submit.provider_video_id else [],
            "provider_task_id_masked": mask_provider_task_id(submit.provider_task_id),
            "result_url_present": True,
            "download_status": artifact.error_code or "failed",
            "provider_readiness": status,
        }
    return {
        "ok": True,
        "provider_attempted": True,
        "provider": adapter.provider_name,
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
