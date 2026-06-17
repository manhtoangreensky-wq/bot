"""Key4U provider adapter for admin-only TOAN AAS smoke tests.

Public routing is intentionally disabled by default. This module never logs or
returns API keys and keeps provider raw responses out of user-facing text.
"""

from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return default if value is None else str(value)


def _flag(name: str, default: str = "false") -> bool:
    return str(_env(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def mask_key(value: str | None) -> str:
    raw = str(value or "")
    if not raw:
        return "missing"
    if len(raw) <= 8:
        return "***"
    return f"{raw[:4]}***{raw[-4:]}"


def safe_join_url(base_url: str, endpoint: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    path = str(endpoint or "").strip()
    if not path:
        return base
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if base.endswith("/v1") and path.startswith("/v1/"):
        path = path[3:]
    return f"{base}/{path.lstrip('/')}"


def _safe_message(value: Any, limit: int = 220) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    redacted_markers = ("sk-", "Bearer ", "apiKey=", "token=", "key=")
    for marker in redacted_markers:
        while marker in text:
            idx = text.find(marker)
            end = text.find(" ", idx + len(marker))
            if end < 0:
                end = min(len(text), idx + len(marker) + 32)
            text = text[:idx] + f"{marker}***" + text[end:]
    return text[:limit]


def _classify_http(status_code: int, message: str = "") -> str:
    msg = str(message or "").lower()
    if any(marker in msg for marker in ("model not found", "invalid model", "model_not_found", "invalid_model")):
        return "FAIL_MODEL_NOT_FOUND"
    if status_code in {401, 403}:
        return "FAIL_AUTH"
    if status_code == 429:
        return "FAIL_RATE_LIMIT"
    if status_code == 408 or "timeout" in msg:
        return "FAIL_TIMEOUT"
    if status_code in {400, 422}:
        return "FAIL_BAD_REQUEST"
    if status_code == 404 or "not found" in msg:
        return "FAIL_NOT_FOUND"
    if status_code >= 500:
        return "FAIL_PROVIDER_UNAVAILABLE"
    return "FAIL_PROVIDER_ERROR"


PLACEHOLDER_TASK_IDS = {"", "<task_id>", "task_id", "task-id", "taskid", "none", "null", "----", "-"}


def is_placeholder_task_id(value: str | None) -> bool:
    return str(value or "").strip().lower() in PLACEHOLDER_TASK_IDS


def should_try_model_fallback(result: dict[str, Any]) -> bool:
    haystack = " ".join(
        str(result.get(key) or "")
        for key in ("status", "error_class", "error_message_safe")
    ).lower()
    return any(marker in haystack for marker in ("model_not_found", "invalid_model", "model not found", "invalid model", "need_model"))


def _timeout_result(capability: str, model: str, exc: Exception, *, task_id: str = "", stage: str = "timeout") -> dict[str, Any]:
    if isinstance(exc, httpx.ConnectTimeout):
        stage = "connect_timeout"
    elif isinstance(exc, httpx.ReadTimeout):
        stage = "read_timeout"
    elif stage == "timeout":
        stage = "submit_timeout"
    return _result(
        ok=False,
        capability=capability,
        model=model,
        status="FAIL_TIMEOUT",
        task_id=task_id,
        error_class=stage,
        error_message_safe=f"{stage}: provider did not respond before timeout",
    )


def _result(
    *,
    ok: bool,
    capability: str,
    model: str = "",
    status: str = "",
    http_status: int = 0,
    latency_ms: int = 0,
    task_id: str = "",
    output_url: str = "",
    output_bytes: bytes | None = None,
    text: str = "",
    error_class: str = "",
    error_message_safe: str = "",
    raw_debug_admin_only: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": bool(ok),
        "provider": "key4u",
        "capability": capability,
        "model": model or "",
        "task_id": task_id or "",
        "output_url": output_url or "",
        "output_bytes": output_bytes or b"",
        "text": text or "",
        "status": status or ("PASS" if ok else "FAIL"),
        "http_status": int(http_status or 0),
        "latency_ms": int(latency_ms or 0),
        "error_class": error_class or ("" if ok else "FAIL"),
        "error_message_safe": _safe_message(error_message_safe),
        "raw_debug_admin_only": raw_debug_admin_only or {},
    }


@dataclass
class Key4UConfig:
    enabled: bool = True
    api_key: str = ""
    base_url: str = "https://api.key4u.shop"
    openai_base_url: str = "https://api.key4u.shop/v1"
    smart_routing: bool = True
    public_enabled: bool = False
    admin_smoke_enabled: bool = True
    usage_endpoint: str = ""
    balance_endpoint: str = ""
    models_endpoint: str = ""
    chat_endpoint: str = "/v1/chat/completions"
    image_edit_endpoint: str = "/v1/images/edits"
    nano_banana_edit_endpoint: str = "/fal-ai/nano-banana/edit"
    video_create_endpoint: str = "/v1/video/create"
    video_query_endpoint: str = "/v1/video/query"
    tts_endpoint: str = ""
    stt_endpoint: str = ""
    suno_create_endpoint: str = ""
    suno_query_endpoint: str = ""
    rerank_endpoint: str = ""
    chat_model: str = "qwen-plus"
    vision_model: str = "gemini-2.5-flash"
    image_edit_model: str = "grok-imagine-image-pro"
    nano_banana_edit_model: str = "nano-banana"
    video_model: str = "veo3.1-fast"
    tts_model: str = ""
    stt_model: str = ""
    suno_model: str = ""
    rerank_model: str = ""


def config_from_env() -> Key4UConfig:
    return Key4UConfig(
        enabled=_flag("KEY4U_ENABLED", "false"),
        api_key=_env("KEY4U_API_KEY", ""),
        base_url=_env("KEY4U_BASE_URL", "https://api.key4u.shop"),
        openai_base_url=_env("KEY4U_OPENAI_BASE_URL", "https://api.key4u.shop/v1"),
        smart_routing=_flag("KEY4U_SMART_ROUTING", "true"),
        public_enabled=_flag("KEY4U_PUBLIC_ENABLED", "false"),
        admin_smoke_enabled=_flag("KEY4U_ADMIN_SMOKE_ENABLED", "true"),
        usage_endpoint=_env("KEY4U_USAGE_ENDPOINT", ""),
        balance_endpoint=_env("KEY4U_BALANCE_ENDPOINT", ""),
        models_endpoint=_env("KEY4U_MODELS_ENDPOINT", ""),
        chat_endpoint=_env("KEY4U_CHAT_COMPLETIONS_ENDPOINT", _env("KEY4U_CHAT_ENDPOINT", "/v1/chat/completions")),
        image_edit_endpoint=_env("KEY4U_IMAGE_EDITS_ENDPOINT", _env("KEY4U_IMAGE_EDIT_ENDPOINT", "/v1/images/edits")),
        nano_banana_edit_endpoint=_env("KEY4U_NANO_BANANA_EDIT_ENDPOINT", "/fal-ai/nano-banana/edit"),
        video_create_endpoint=_env("KEY4U_VIDEO_CREATE_ENDPOINT", "/v1/video/create"),
        video_query_endpoint=_env("KEY4U_VIDEO_QUERY_ENDPOINT", "/v1/video/query"),
        tts_endpoint=_env("KEY4U_TTS_ENDPOINT", ""),
        stt_endpoint=_env("KEY4U_STT_ENDPOINT", ""),
        suno_create_endpoint=_env("KEY4U_SUNO_CREATE_ENDPOINT", ""),
        suno_query_endpoint=_env("KEY4U_SUNO_QUERY_ENDPOINT", ""),
        rerank_endpoint=_env("KEY4U_RERANK_ENDPOINT", ""),
        chat_model=_env("KEY4U_DEFAULT_CHAT_MODEL", _env("KEY4U_CHAT_MODEL", "qwen-plus")),
        vision_model=_env("KEY4U_DEFAULT_VISION_MODEL", _env("KEY4U_VISION_MODEL", "gemini-2.5-flash")),
        image_edit_model=_env("KEY4U_DEFAULT_IMAGE_EDIT_MODEL", _env("KEY4U_IMAGE_EDIT_MODEL", "grok-imagine-image-pro")),
        nano_banana_edit_model=_env("KEY4U_NANO_BANANA_EDIT_MODEL", "nano-banana"),
        video_model=_env("KEY4U_DEFAULT_VIDEO_MODEL", _env("KEY4U_VIDEO_MODEL", "veo3.1-fast")),
        tts_model=_env("KEY4U_DEFAULT_TTS_MODEL", _env("KEY4U_TTS_MODEL", "")),
        stt_model=_env("KEY4U_STT_MODEL", ""),
        suno_model=_env("KEY4U_DEFAULT_MUSIC_MODEL", _env("KEY4U_SUNO_MODEL", "")),
        rerank_model=_env("KEY4U_RERANK_MODEL", ""),
    )


class Key4UProvider:
    def __init__(self, config: Key4UConfig | None = None):
        self.config = config or config_from_env()

    def is_configured(self) -> bool:
        return bool(self.config.enabled and self.config.admin_smoke_enabled and self.config.api_key)

    def get_status(self) -> dict[str, Any]:
        return {
            "provider": "key4u",
            "enabled": bool(self.config.enabled),
            "public_enabled": bool(self.config.public_enabled),
            "admin_smoke_enabled": bool(self.config.admin_smoke_enabled),
            "smart_routing": bool(self.config.smart_routing),
            "api_key": mask_key(self.config.api_key),
            "configured": self.is_configured(),
            "base_url": self.config.base_url,
            "openai_base_url": self.config.openai_base_url,
            "usage_endpoint": "configured" if self.config.usage_endpoint else "NEED_ENDPOINT",
            "balance_endpoint": "configured" if self.config.balance_endpoint else "NEED_ENDPOINT",
            "models_endpoint": "configured" if self.config.models_endpoint else "NEED_ENDPOINT",
            "chat_model": self.config.chat_model or "",
            "vision_model": self.config.vision_model or "",
            "image_edit_model": self.config.image_edit_model or "",
            "nano_banana_edit_model": self.config.nano_banana_edit_model or "",
            "video_model": self.config.video_model or "",
            "tts_model": self.config.tts_model or "",
            "stt_model": self.config.stt_model or "",
            "suno_model": self.config.suno_model or "",
            "rerank_model": self.config.rerank_model or "",
        }

    def list_capabilities(self) -> dict[str, str]:
        return {
            "text_brain": "ready_for_smoke",
            "vision_analysis": "ready_for_smoke_requires_image",
            "image_edit": "admin_smoke_requires_image_input",
            "nano_banana_edit": "admin_smoke_requires_image_input",
            "video_generate": "ready_for_smoke",
            "video_query": "ready_for_task_id",
            "image_generate": "planned_needs_docs",
            "tts": "needs_endpoint_docs" if not self.config.tts_endpoint else "admin_smoke",
            "stt": "needs_endpoint_docs" if not self.config.stt_endpoint else "admin_smoke",
            "translate": "via_chat_if_chat_model_pass",
            "suno": "needs_endpoint_docs" if not self.config.suno_create_endpoint else "admin_smoke",
            "rerank": "local_keyword_fallback" if not self.config.rerank_endpoint else "admin_smoke",
        }

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Accept": "application/json",
        }

    async def request_json(
        self,
        method: str,
        endpoint_path: str,
        payload: dict[str, Any] | None = None,
        *,
        use_openai_base: bool = False,
        timeout_seconds: float = 30.0,
    ) -> dict[str, Any]:
        base_url = self.config.openai_base_url if use_openai_base else self.config.base_url
        endpoint = safe_join_url(base_url, endpoint_path)
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                if str(method or "GET").upper() == "POST":
                    response = await client.post(endpoint, headers={**self._headers(), "Content-Type": "application/json"}, json=payload or {})
                else:
                    response = await client.get(endpoint, headers=self._headers())
            latency_ms = int((time.perf_counter() - started) * 1000)
            try:
                data = response.json()
            except Exception:
                data = {}
            result = _result(
                ok=200 <= response.status_code < 300,
                capability="request_json",
                status="PASS" if 200 <= response.status_code < 300 else "FAIL",
                http_status=response.status_code,
                latency_ms=latency_ms,
                error_class="" if 200 <= response.status_code < 300 else _classify_http(response.status_code, data),
                error_message_safe={} if 200 <= response.status_code < 300 else data,
                raw_debug_admin_only={"keys": sorted(data.keys())[:12] if isinstance(data, dict) else []},
            )
            result["data"] = data
            return result
        except httpx.TimeoutException as exc:
            return _result(ok=False, capability="request_json", status="FAIL_TIMEOUT", error_class="FAIL_TIMEOUT", error_message_safe=exc)
        except Exception as exc:
            return _result(ok=False, capability="request_json", status="FAIL_EXCEPTION", error_class=type(exc).__name__, error_message_safe=exc)

    async def request_multipart(
        self,
        endpoint_path: str,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        *,
        use_openai_base: bool = False,
        timeout_seconds: float = 60.0,
    ) -> dict[str, Any]:
        base_url = self.config.openai_base_url if use_openai_base else self.config.base_url
        endpoint = safe_join_url(base_url, endpoint_path)
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(endpoint, headers=self._headers(), data=data or {}, files=files or {})
            latency_ms = int((time.perf_counter() - started) * 1000)
            try:
                payload = response.json()
            except Exception:
                payload = {}
            result = _result(
                ok=200 <= response.status_code < 300,
                capability="request_multipart",
                status="PASS" if 200 <= response.status_code < 300 else "FAIL",
                http_status=response.status_code,
                latency_ms=latency_ms,
                error_class="" if 200 <= response.status_code < 300 else _classify_http(response.status_code, payload),
                error_message_safe={} if 200 <= response.status_code < 300 else payload,
            )
            result["data"] = payload
            result["content_type"] = response.headers.get("content-type", "")
            result["content_bytes"] = response.content
            return result
        except httpx.TimeoutException as exc:
            return _result(ok=False, capability="request_multipart", status="FAIL_TIMEOUT", error_class="FAIL_TIMEOUT", error_message_safe=exc)
        except Exception as exc:
            return _result(ok=False, capability="request_multipart", status="FAIL_EXCEPTION", error_class=type(exc).__name__, error_message_safe=exc)

    def normalize_error(self, http_status: int = 0, payload: Any = None) -> dict[str, str]:
        return {
            "error_class": _classify_http(int(http_status or 0), payload if isinstance(payload, dict) else {}),
            "error_message_safe": _safe_message(payload),
        }

    async def get_usage(self) -> dict[str, Any]:
        if not self.is_configured():
            return self._missing_result("usage", "")
        if not self.config.usage_endpoint:
            return _result(ok=False, capability="usage", status="NEED_ENDPOINT", error_class="NEED_ENDPOINT", error_message_safe="KEY4U_USAGE_ENDPOINT is not configured")
        result = await self.request_json("GET", self.config.usage_endpoint)
        result["capability"] = "usage"
        return result

    async def get_balance(self) -> dict[str, Any]:
        if not self.is_configured():
            return self._missing_result("balance", "")
        if not self.config.balance_endpoint:
            return _result(ok=False, capability="balance", status="NEED_ENDPOINT", error_class="NEED_ENDPOINT", error_message_safe="KEY4U_BALANCE_ENDPOINT is not configured")
        result = await self.request_json("GET", self.config.balance_endpoint)
        result["capability"] = "balance"
        return result

    def get_local_estimated_usage(self) -> dict[str, Any]:
        return {"status": "BOT_DB_SUMMARY", "note": "Computed in bot from provider_usage_events."}

    def _missing_result(self, capability: str, model: str = "") -> dict[str, Any]:
        return _result(
            ok=False,
            capability=capability,
            model=model,
            status="NOT_CONFIGURED",
            error_class="NOT_CONFIGURED",
            error_message_safe="KEY4U_ENABLED/API_KEY/ADMIN_SMOKE not configured",
        )

    async def chat_completion(
        self,
        prompt: str = "Trả lời đúng một câu tiếng Việt có chữ TEST_OK.",
        model: str = "",
        timeout_seconds: float = 30.0,
    ) -> dict[str, Any]:
        selected_model = model or self.config.chat_model
        if not self.is_configured():
            return self._missing_result("text_brain", selected_model)
        if not selected_model:
            return _result(
                ok=False,
                capability="text_brain",
                status="NEED_MODEL",
                error_class="NEED_MODEL",
                error_message_safe="KEY4U_CHAT_MODEL is empty",
            )
        endpoint = safe_join_url(self.config.openai_base_url, self.config.chat_endpoint)
        started = time.perf_counter()
        payload = {
            "model": selected_model,
            "messages": [{"role": "user", "content": str(prompt or "")[:500]}],
            "max_tokens": 80,
            "temperature": 0.2,
        }
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(endpoint, headers={**self._headers(), "Content-Type": "application/json"}, json=payload)
            latency_ms = int((time.perf_counter() - started) * 1000)
            data: dict[str, Any] = {}
            try:
                data = response.json()
            except Exception:
                data = {}
            message = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
            if 200 <= response.status_code < 300 and str(message).strip():
                return _result(
                    ok=True,
                    capability="text_brain",
                    model=selected_model,
                    status="PASS",
                    http_status=response.status_code,
                    latency_ms=latency_ms,
                    text=str(message).strip(),
                    raw_debug_admin_only={"response_shape": sorted(data.keys())[:8]},
                )
            if 200 <= response.status_code < 300:
                return _result(
                    ok=False,
                    capability="text_brain",
                    model=selected_model,
                    status="FAIL_CONTENT_EMPTY",
                    http_status=response.status_code,
                    latency_ms=latency_ms,
                    error_class="FAIL_CONTENT_EMPTY",
                    error_message_safe="empty content",
                )
            err = data.get("error") if isinstance(data.get("error"), (dict, str)) else data
            return _result(
                ok=False,
                capability="text_brain",
                model=selected_model,
                status="FAIL",
                http_status=response.status_code,
                latency_ms=latency_ms,
                error_class=_classify_http(response.status_code, err),
                error_message_safe=err,
            )
        except httpx.TimeoutException as exc:
            return _timeout_result("text_brain", selected_model, exc)
        except Exception as exc:
            return _result(ok=False, capability="text_brain", model=selected_model, status="FAIL_EXCEPTION", error_class=type(exc).__name__, error_message_safe=exc)

    async def vision_analysis(
        self,
        prompt: str = "Mô tả ngắn ảnh này.",
        image_bytes: bytes | None = None,
        image_url: str = "",
        model: str = "",
        timeout_seconds: float = 30.0,
    ) -> dict[str, Any]:
        selected_model = model or self.config.vision_model
        if not self.is_configured():
            return self._missing_result("vision_analysis", selected_model)
        if not selected_model:
            return _result(ok=False, capability="vision_analysis", status="NEED_MODEL", error_class="NEED_MODEL", error_message_safe="KEY4U_VISION_MODEL is empty")
        if not image_bytes and not image_url:
            return _result(ok=False, capability="vision_analysis", model=selected_model, status="NEED_IMAGE_INPUT", error_class="NEED_IMAGE_INPUT", error_message_safe="Hãy reply một ảnh hoặc gửi ảnh trong 10 phút rồi chạy lại smoke test vision.")
        endpoint = safe_join_url(self.config.openai_base_url, self.config.chat_endpoint)
        image_content = image_url
        if image_bytes:
            image_content = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
        payload = {
            "model": selected_model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": str(prompt or "")[:500]},
                    {"type": "image_url", "image_url": {"url": image_content}},
                ],
            }],
            "max_tokens": 80,
            "temperature": 0.1,
        }
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(endpoint, headers={**self._headers(), "Content-Type": "application/json"}, json=payload)
            latency_ms = int((time.perf_counter() - started) * 1000)
            try:
                data = response.json()
            except Exception:
                data = {}
            text = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
            if 200 <= response.status_code < 300 and str(text).strip():
                return _result(ok=True, capability="vision_analysis", model=selected_model, status="PASS", http_status=response.status_code, latency_ms=latency_ms, text=str(text).strip())
            return _result(ok=False, capability="vision_analysis", model=selected_model, status="FAIL", http_status=response.status_code, latency_ms=latency_ms, error_class=_classify_http(response.status_code, data), error_message_safe=data)
        except httpx.TimeoutException as exc:
            return _timeout_result("vision_analysis", selected_model, exc)
        except Exception as exc:
            return _result(ok=False, capability="vision_analysis", model=selected_model, status="FAIL_EXCEPTION", error_class=type(exc).__name__, error_message_safe=exc)

    async def image_generation(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return _result(
            ok=False,
            capability="image_generate",
            status="NEED_DOCS",
            error_class="NEED_DOCS",
            error_message_safe="Key4U image generation endpoint not enabled in V1; use image_edit/nano_banana_edit smoke only",
        )

    def _needs_docs_result(self, capability: str, model: str = "", endpoint_name: str = "") -> dict[str, Any]:
        return _result(
            ok=False,
            capability=capability,
            model=model,
            status="NEED_DOCS",
            error_class="NEED_DOCS",
            error_message_safe=f"{endpoint_name or capability} endpoint/model docs are not configured yet",
        )

    async def image_edit(
        self,
        prompt: str = "Sửa nhẹ ảnh theo phong cách quảng cáo sạch.",
        image_bytes: bytes | None = None,
        model: str = "",
        use_nano_banana: bool = False,
        timeout_seconds: float = 60.0,
    ) -> dict[str, Any]:
        selected_model = model or (self.config.nano_banana_edit_model if use_nano_banana else self.config.image_edit_model)
        capability = "nano_banana_edit" if use_nano_banana else "image_edit"
        endpoint_path = self.config.nano_banana_edit_endpoint if use_nano_banana else self.config.image_edit_endpoint
        if not self.is_configured():
            return self._missing_result(capability, selected_model)
        if not image_bytes:
            return _result(ok=False, capability=capability, model=selected_model, status="NEED_IMAGE_INPUT", error_class="NEED_IMAGE_INPUT", error_message_safe="Hãy reply một ảnh hoặc gửi ảnh trong 10 phút rồi chạy lại smoke test image edit.")
        endpoint = safe_join_url(self.config.base_url if use_nano_banana else self.config.openai_base_url, endpoint_path)
        started = time.perf_counter()
        files = {"image": ("toan-aas-key4u-input.png", image_bytes, "image/png")}
        data = {"model": selected_model, "prompt": str(prompt or "")[:800]}
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(endpoint, headers=self._headers(), data=data, files=files)
            latency_ms = int((time.perf_counter() - started) * 1000)
            content_type = response.headers.get("content-type", "")
            if 200 <= response.status_code < 300 and content_type.startswith("image/"):
                return _result(ok=True, capability=capability, model=selected_model, status="PASS", http_status=response.status_code, latency_ms=latency_ms, output_bytes=response.content)
            try:
                payload = response.json()
            except Exception:
                payload = {}
            output_url = ""
            data_items = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(data_items, list) and data_items:
                output_url = str((data_items[0] or {}).get("url") or "")
            if 200 <= response.status_code < 300 and output_url:
                return _result(ok=True, capability=capability, model=selected_model, status="PASS", http_status=response.status_code, latency_ms=latency_ms, output_url=output_url)
            return _result(ok=False, capability=capability, model=selected_model, status="FAIL", http_status=response.status_code, latency_ms=latency_ms, error_class=_classify_http(response.status_code, payload), error_message_safe=payload)
        except httpx.TimeoutException as exc:
            return _timeout_result(capability, selected_model, exc)
        except Exception as exc:
            return _result(ok=False, capability=capability, model=selected_model, status="FAIL_EXCEPTION", error_class=type(exc).__name__, error_message_safe=exc)

    async def video_generation(
        self,
        prompt: str = "6-second jade green TOAN AAS logo reveal, clean tech style, smooth camera movement, no watermark.",
        model: str = "",
        timeout_seconds: float = 60.0,
    ) -> dict[str, Any]:
        selected_model = model or self.config.video_model
        if not self.is_configured():
            return self._missing_result("video_generate", selected_model)
        endpoint = safe_join_url(self.config.base_url, self.config.video_create_endpoint)
        payload = {
            "model": selected_model,
            "prompt": str(prompt or "")[:1000],
            "aspect_ratio": "16:9",
            "enhance_prompt": True,
            "enable_upsample": False,
        }
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(endpoint, headers={**self._headers(), "Content-Type": "application/json"}, json=payload)
            latency_ms = int((time.perf_counter() - started) * 1000)
            try:
                data = response.json()
            except Exception:
                data = {}
            body = data.get("data") if isinstance(data.get("data"), dict) else data
            task_id = str((body or {}).get("task_id") or (body or {}).get("id") or data.get("task_id") or "")
            provider_status = str((body or {}).get("status") or data.get("status") or "")
            if 200 <= response.status_code < 300 and task_id:
                return _result(ok=True, capability="video_generate", model=selected_model, status="PASS_SUBMITTED", http_status=response.status_code, latency_ms=latency_ms, task_id=task_id, raw_debug_admin_only={"provider_status": provider_status})
            return _result(ok=False, capability="video_generate", model=selected_model, status="FAIL", http_status=response.status_code, latency_ms=latency_ms, error_class=_classify_http(response.status_code, data), error_message_safe=data)
        except httpx.TimeoutException as exc:
            return _timeout_result("video_generate", selected_model, exc, stage="submit_timeout")
        except Exception as exc:
            return _result(ok=False, capability="video_generate", model=selected_model, status="FAIL_EXCEPTION", error_class=type(exc).__name__, error_message_safe=exc)

    async def poll_video_task(self, task_id: str, timeout_seconds: float = 30.0) -> dict[str, Any]:
        safe_task_id = str(task_id or "").strip()
        if not self.is_configured():
            return self._missing_result("video_query", self.config.video_model)
        if is_placeholder_task_id(safe_task_id):
            return _result(
                ok=False,
                capability="video_query",
                model=self.config.video_model,
                status="NEED_TASK_ID",
                error_class="NEED_TASK_ID",
                error_message_safe="Vui lòng nhập task_id thật. Ví dụ: /key4u_video_job abc123",
            )
        endpoint = safe_join_url(self.config.base_url, self.config.video_query_endpoint)
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.get(endpoint, headers=self._headers(), params={"id": safe_task_id})
            latency_ms = int((time.perf_counter() - started) * 1000)
            try:
                data = response.json()
            except Exception:
                data = {}
            body = data.get("data") if isinstance(data.get("data"), dict) else data
            status = str((body or {}).get("status") or data.get("status") or "")
            output_url = str((body or {}).get("result_url") or (body or {}).get("url") or data.get("result_url") or "")
            if 200 <= response.status_code < 300:
                return _result(
                    ok=bool(output_url),
                    capability="video_query",
                    model=self.config.video_model,
                    status="SUCCESS" if output_url else (status or "PROCESSING"),
                    http_status=response.status_code,
                    latency_ms=latency_ms,
                    task_id=safe_task_id,
                    output_url=output_url,
                    raw_debug_admin_only={"provider_status": status, "progress": (body or {}).get("progress") or data.get("progress") or ""},
                )
            return _result(ok=False, capability="video_query", model=self.config.video_model, status="FAIL", http_status=response.status_code, latency_ms=latency_ms, task_id=safe_task_id, error_class=_classify_http(response.status_code, data), error_message_safe=data)
        except httpx.TimeoutException as exc:
            return _timeout_result("video_query", self.config.video_model, exc, task_id=safe_task_id)
        except Exception as exc:
            return _result(ok=False, capability="video_query", model=self.config.video_model, status="FAIL_EXCEPTION", task_id=safe_task_id, error_class=type(exc).__name__, error_message_safe=exc)

    async def tts(self, text: str = "Xin chào TOAN AAS.", model: str = "", timeout_seconds: float = 30.0) -> dict[str, Any]:
        selected_model = model or self.config.tts_model
        if not self.is_configured():
            return self._missing_result("tts", selected_model)
        if not self.config.tts_endpoint or not selected_model:
            return self._needs_docs_result("tts", selected_model, "KEY4U_TTS_ENDPOINT/KEY4U_DEFAULT_TTS_MODEL")
        endpoint = safe_join_url(self.config.openai_base_url, self.config.tts_endpoint)
        payload = {"model": selected_model, "input": str(text or "")[:500]}
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(endpoint, headers={**self._headers(), "Content-Type": "application/json"}, json=payload)
            latency_ms = int((time.perf_counter() - started) * 1000)
            content_type = response.headers.get("content-type", "")
            if 200 <= response.status_code < 300 and (content_type.startswith("audio/") or response.content):
                return _result(ok=True, capability="tts", model=selected_model, status="PASS", http_status=response.status_code, latency_ms=latency_ms, output_bytes=response.content)
            try:
                data = response.json()
            except Exception:
                data = {}
            return _result(ok=False, capability="tts", model=selected_model, status="FAIL", http_status=response.status_code, latency_ms=latency_ms, error_class=_classify_http(response.status_code, data), error_message_safe=data)
        except httpx.TimeoutException as exc:
            return _result(ok=False, capability="tts", model=selected_model, status="FAIL_TIMEOUT", error_class="FAIL_TIMEOUT", error_message_safe=exc)
        except Exception as exc:
            return _result(ok=False, capability="tts", model=selected_model, status="FAIL_EXCEPTION", error_class=type(exc).__name__, error_message_safe=exc)

    async def stt(self, audio_bytes: bytes | None = None, model: str = "", timeout_seconds: float = 60.0) -> dict[str, Any]:
        selected_model = model or self.config.stt_model
        if not self.is_configured():
            return self._missing_result("stt", selected_model)
        if not self.config.stt_endpoint or not selected_model:
            return self._needs_docs_result("stt", selected_model, "KEY4U_STT_ENDPOINT/KEY4U_STT_MODEL")
        if not audio_bytes:
            return _result(ok=False, capability="stt", model=selected_model, status="NEED_AUDIO_INPUT", error_class="NEED_AUDIO_INPUT", error_message_safe="Reply/send an audio file for STT smoke test")
        endpoint = safe_join_url(self.config.openai_base_url, self.config.stt_endpoint)
        started = time.perf_counter()
        files = {"file": ("toan-aas-key4u-audio.mp3", audio_bytes, "audio/mpeg")}
        data = {"model": selected_model}
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(endpoint, headers=self._headers(), data=data, files=files)
            latency_ms = int((time.perf_counter() - started) * 1000)
            try:
                payload = response.json()
            except Exception:
                payload = {}
            text = str(payload.get("text") or payload.get("transcript") or "")
            if 200 <= response.status_code < 300 and text.strip():
                return _result(ok=True, capability="stt", model=selected_model, status="PASS", http_status=response.status_code, latency_ms=latency_ms, text=text.strip())
            return _result(ok=False, capability="stt", model=selected_model, status="FAIL", http_status=response.status_code, latency_ms=latency_ms, error_class=_classify_http(response.status_code, payload), error_message_safe=payload)
        except httpx.TimeoutException as exc:
            return _result(ok=False, capability="stt", model=selected_model, status="FAIL_TIMEOUT", error_class="FAIL_TIMEOUT", error_message_safe=exc)
        except Exception as exc:
            return _result(ok=False, capability="stt", model=selected_model, status="FAIL_EXCEPTION", error_class=type(exc).__name__, error_message_safe=exc)

    async def suno_create(self, prompt: str = "Short upbeat TOAN AAS intro.", model: str = "", timeout_seconds: float = 30.0) -> dict[str, Any]:
        selected_model = model or self.config.suno_model
        if not self.is_configured():
            return self._missing_result("suno", selected_model)
        if not self.config.suno_create_endpoint or not selected_model:
            return self._needs_docs_result("suno", selected_model, "KEY4U_SUNO_CREATE_ENDPOINT/KEY4U_DEFAULT_MUSIC_MODEL")
        endpoint = safe_join_url(self.config.base_url, self.config.suno_create_endpoint)
        payload = {"model": selected_model, "prompt": str(prompt or "")[:600]}
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(endpoint, headers={**self._headers(), "Content-Type": "application/json"}, json=payload)
            latency_ms = int((time.perf_counter() - started) * 1000)
            try:
                data = response.json()
            except Exception:
                data = {}
            body = data.get("data") if isinstance(data.get("data"), dict) else data
            task_id = str((body or {}).get("task_id") or (body or {}).get("id") or data.get("task_id") or "")
            if 200 <= response.status_code < 300 and task_id:
                return _result(ok=True, capability="suno", model=selected_model, status="PASS_SUBMITTED", http_status=response.status_code, latency_ms=latency_ms, task_id=task_id)
            return _result(ok=False, capability="suno", model=selected_model, status="FAIL", http_status=response.status_code, latency_ms=latency_ms, error_class=_classify_http(response.status_code, data), error_message_safe=data)
        except httpx.TimeoutException as exc:
            return _result(ok=False, capability="suno", model=selected_model, status="FAIL_TIMEOUT", error_class="FAIL_TIMEOUT", error_message_safe=exc)
        except Exception as exc:
            return _result(ok=False, capability="suno", model=selected_model, status="FAIL_EXCEPTION", error_class=type(exc).__name__, error_message_safe=exc)

    async def suno_query(self, task_id: str, timeout_seconds: float = 30.0) -> dict[str, Any]:
        selected_model = self.config.suno_model
        if not self.is_configured():
            return self._missing_result("suno_query", selected_model)
        if not self.config.suno_query_endpoint:
            return self._needs_docs_result("suno_query", selected_model, "KEY4U_SUNO_QUERY_ENDPOINT")
        safe_task_id = str(task_id or "").strip()
        if not safe_task_id:
            return _result(ok=False, capability="suno_query", model=selected_model, status="NEED_TASK_ID", error_class="NEED_TASK_ID", error_message_safe="Missing task_id")
        endpoint = safe_join_url(self.config.base_url, self.config.suno_query_endpoint)
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(endpoint, headers={**self._headers(), "Content-Type": "application/json"}, json={"task_id": safe_task_id})
            latency_ms = int((time.perf_counter() - started) * 1000)
            try:
                data = response.json()
            except Exception:
                data = {}
            body = data.get("data") if isinstance(data.get("data"), dict) else data
            output_url = str((body or {}).get("audio_url") or (body or {}).get("url") or data.get("audio_url") or "")
            status = str((body or {}).get("status") or data.get("status") or "")
            return _result(ok=bool(output_url), capability="suno_query", model=selected_model, status="SUCCESS" if output_url else (status or "PROCESSING"), http_status=response.status_code, latency_ms=latency_ms, task_id=safe_task_id, output_url=output_url)
        except httpx.TimeoutException as exc:
            return _result(ok=False, capability="suno_query", model=selected_model, status="FAIL_TIMEOUT", task_id=safe_task_id, error_class="FAIL_TIMEOUT", error_message_safe=exc)
        except Exception as exc:
            return _result(ok=False, capability="suno_query", model=selected_model, status="FAIL_EXCEPTION", task_id=safe_task_id, error_class=type(exc).__name__, error_message_safe=exc)

    async def rerank(self, query: str, candidates: list[str] | None = None, model: str = "", timeout_seconds: float = 30.0) -> dict[str, Any]:
        selected_model = model or self.config.rerank_model
        candidates = [str(item)[:500] for item in (candidates or []) if str(item).strip()]
        if not self.is_configured():
            return self._missing_result("rerank", selected_model)
        if not self.config.rerank_endpoint or not selected_model:
            return self._needs_docs_result("rerank", selected_model, "KEY4U_RERANK_ENDPOINT/KEY4U_RERANK_MODEL")
        endpoint = safe_join_url(self.config.base_url, self.config.rerank_endpoint)
        payload = {"model": selected_model, "query": str(query or "")[:500], "documents": candidates[:20]}
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(endpoint, headers={**self._headers(), "Content-Type": "application/json"}, json=payload)
            latency_ms = int((time.perf_counter() - started) * 1000)
            try:
                data = response.json()
            except Exception:
                data = {}
            if 200 <= response.status_code < 300:
                return _result(ok=True, capability="rerank", model=selected_model, status="PASS", http_status=response.status_code, latency_ms=latency_ms, raw_debug_admin_only={"response_shape": sorted(data.keys())[:8] if isinstance(data, dict) else []})
            return _result(ok=False, capability="rerank", model=selected_model, status="FAIL", http_status=response.status_code, latency_ms=latency_ms, error_class=_classify_http(response.status_code, data), error_message_safe=data)
        except httpx.TimeoutException as exc:
            return _result(ok=False, capability="rerank", model=selected_model, status="FAIL_TIMEOUT", error_class="FAIL_TIMEOUT", error_message_safe=exc)
        except Exception as exc:
            return _result(ok=False, capability="rerank", model=selected_model, status="FAIL_EXCEPTION", error_class=type(exc).__name__, error_message_safe=exc)


def is_configured() -> bool:
    return Key4UProvider().is_configured()


def get_status() -> dict[str, Any]:
    return Key4UProvider().get_status()


def list_capabilities() -> dict[str, str]:
    return Key4UProvider().list_capabilities()
