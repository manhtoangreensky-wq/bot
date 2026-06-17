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
    public_enabled: bool = False
    admin_smoke_enabled: bool = True
    chat_endpoint: str = "/v1/chat/completions"
    image_edit_endpoint: str = "/v1/images/edits"
    nano_banana_edit_endpoint: str = "/fal-ai/nano-banana/edit"
    video_create_endpoint: str = "/v1/video/create"
    video_query_endpoint: str = "/v1/video/query"
    chat_model: str = ""
    vision_model: str = ""
    image_edit_model: str = "grok-imagine-image-pro"
    nano_banana_edit_model: str = "nano-banana"
    video_model: str = "veo3.1-fast"


def config_from_env() -> Key4UConfig:
    return Key4UConfig(
        enabled=_flag("KEY4U_ENABLED", "false"),
        api_key=_env("KEY4U_API_KEY", ""),
        base_url=_env("KEY4U_BASE_URL", "https://api.key4u.shop"),
        openai_base_url=_env("KEY4U_OPENAI_BASE_URL", "https://api.key4u.shop/v1"),
        public_enabled=_flag("KEY4U_PUBLIC_ENABLED", "false"),
        admin_smoke_enabled=_flag("KEY4U_ADMIN_SMOKE_ENABLED", "true"),
        chat_endpoint=_env("KEY4U_CHAT_ENDPOINT", "/v1/chat/completions"),
        image_edit_endpoint=_env("KEY4U_IMAGE_EDIT_ENDPOINT", "/v1/images/edits"),
        nano_banana_edit_endpoint=_env("KEY4U_NANO_BANANA_EDIT_ENDPOINT", "/fal-ai/nano-banana/edit"),
        video_create_endpoint=_env("KEY4U_VIDEO_CREATE_ENDPOINT", "/v1/video/create"),
        video_query_endpoint=_env("KEY4U_VIDEO_QUERY_ENDPOINT", "/v1/video/query"),
        chat_model=_env("KEY4U_CHAT_MODEL", ""),
        vision_model=_env("KEY4U_VISION_MODEL", ""),
        image_edit_model=_env("KEY4U_IMAGE_EDIT_MODEL", "grok-imagine-image-pro"),
        nano_banana_edit_model=_env("KEY4U_NANO_BANANA_EDIT_MODEL", "nano-banana"),
        video_model=_env("KEY4U_VIDEO_MODEL", "veo3.1-fast"),
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
            "api_key": mask_key(self.config.api_key),
            "configured": self.is_configured(),
            "base_url": self.config.base_url,
            "openai_base_url": self.config.openai_base_url,
            "chat_model": self.config.chat_model or "",
            "vision_model": self.config.vision_model or "",
            "image_edit_model": self.config.image_edit_model or "",
            "nano_banana_edit_model": self.config.nano_banana_edit_model or "",
            "video_model": self.config.video_model or "",
        }

    def list_capabilities(self) -> dict[str, str]:
        return {
            "text_brain": "admin_smoke",
            "vision_analysis": "admin_smoke_requires_model_and_image",
            "image_edit": "admin_smoke_requires_image_input",
            "nano_banana_edit": "admin_smoke_requires_image_input",
            "video_generate": "admin_smoke",
            "video_query": "admin_smoke",
            "image_generate": "planned_needs_docs",
        }

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Accept": "application/json",
        }

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
            return _result(ok=False, capability="text_brain", model=selected_model, status="FAIL_TIMEOUT", error_class="FAIL_TIMEOUT", error_message_safe=exc)
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
            return _result(ok=False, capability="vision_analysis", model=selected_model, status="NEED_IMAGE_INPUT", error_class="NEED_IMAGE_INPUT", error_message_safe="Reply/send an image for vision smoke test")
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
            return _result(ok=False, capability="vision_analysis", model=selected_model, status="FAIL_TIMEOUT", error_class="FAIL_TIMEOUT", error_message_safe=exc)
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
            return _result(ok=False, capability=capability, model=selected_model, status="NEED_IMAGE_INPUT", error_class="NEED_IMAGE_INPUT", error_message_safe="Reply/send an image for image edit smoke test")
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
            return _result(ok=False, capability=capability, model=selected_model, status="FAIL_TIMEOUT", error_class="FAIL_TIMEOUT", error_message_safe=exc)
        except Exception as exc:
            return _result(ok=False, capability=capability, model=selected_model, status="FAIL_EXCEPTION", error_class=type(exc).__name__, error_message_safe=exc)

    async def video_generation(
        self,
        prompt: str = "A short clean futuristic turquoise AI automation logo animation, white background, minimal, no extra text except TOAN AAS",
        model: str = "",
        timeout_seconds: float = 30.0,
    ) -> dict[str, Any]:
        selected_model = model or self.config.video_model
        if not self.is_configured():
            return self._missing_result("video_generate", selected_model)
        endpoint = safe_join_url(self.config.base_url, self.config.video_create_endpoint)
        payload = {"model": selected_model, "prompt": str(prompt or "")[:1000]}
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
            return _result(ok=False, capability="video_generate", model=selected_model, status="FAIL_TIMEOUT", error_class="FAIL_TIMEOUT", error_message_safe=exc)
        except Exception as exc:
            return _result(ok=False, capability="video_generate", model=selected_model, status="FAIL_EXCEPTION", error_class=type(exc).__name__, error_message_safe=exc)

    async def poll_video_task(self, task_id: str, timeout_seconds: float = 30.0) -> dict[str, Any]:
        safe_task_id = str(task_id or "").strip()
        if not self.is_configured():
            return self._missing_result("video_query", self.config.video_model)
        if not safe_task_id:
            return _result(ok=False, capability="video_query", model=self.config.video_model, status="NEED_TASK_ID", error_class="NEED_TASK_ID", error_message_safe="Missing task_id")
        endpoint = safe_join_url(self.config.base_url, self.config.video_query_endpoint)
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
            return _result(ok=False, capability="video_query", model=self.config.video_model, status="FAIL_TIMEOUT", task_id=safe_task_id, error_class="FAIL_TIMEOUT", error_message_safe=exc)
        except Exception as exc:
            return _result(ok=False, capability="video_query", model=self.config.video_model, status="FAIL_EXCEPTION", task_id=safe_task_id, error_class=type(exc).__name__, error_message_safe=exc)


def is_configured() -> bool:
    return Key4UProvider().is_configured()


def get_status() -> dict[str, Any]:
    return Key4UProvider().get_status()


def list_capabilities() -> dict[str, str]:
    return Key4UProvider().list_capabilities()
