"""Injected Gemini adapter for the public Free chat surface.

There is one pinned model and no fallback.  The adapter never reads secrets or
environment state; callers supply an already configured client.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
import threading
import time
from typing import Any, Callable, Iterable, Sequence

from services.public_chat_media import MediaInput, assess_video_readiness, validate_media_input


GEMINI_FREE_MODEL = "gemini-3.7-flash"
GEMINI_PUBLIC_CHAT_MODEL = GEMINI_FREE_MODEL
_GENERATE_TIMEOUT_SECONDS = 90.0
_FILE_UPLOAD_TIMEOUT_SECONDS = 60.0
_FILE_GET_TIMEOUT_SECONDS = 15.0
_FILE_DELETE_TIMEOUT_SECONDS = 10.0
_VIDEO_PROCESSING_DEADLINE_SECONDS = 60.0
_VIDEO_TERMINAL_FAILURES = {"FAILED", "ERROR", "CANCELLED", "CANCELED", "EXPIRED"}
_KIND_MIMES = {
    "image": {"image/jpeg", "image/jpg", "image/png", "image/webp"},
    "audio": {"audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/ogg", "audio/opus", "audio/mp4"},
    "video": {"video/mp4", "video/webm", "video/quicktime"},
    "pdf": {"application/pdf"},
}
_KIND_LIMITS = {"image": 10 * 1024 * 1024, "audio": 20 * 1024 * 1024, "video": 20 * 1024 * 1024, "pdf": 20 * 1024 * 1024}
_INLINE_RAW_BYTES = (10 * 1024 * 1024 * 3) // 4
_MAX_HISTORY = 24
_MAX_VALID_HISTORY = 23


async def _await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


async def _provider_call(
    call: Callable[..., Any],
    *,
    timeout_seconds: float,
    _on_result: Callable[[Any], None] | None = None,
    **kwargs: Any,
) -> Any:
    """Call async SDK methods directly and synchronous SDK methods in a worker."""

    async def invoke() -> Any:
        if inspect.iscoroutinefunction(call):
            value = await _await(call(**kwargs))
            if _on_result is not None:
                _on_result(value)
            return value

        def invoke_sync() -> Any:
            result = call(**kwargs)
            if not inspect.isawaitable(result) and _on_result is not None:
                _on_result(result)
            return result

        value = await asyncio.to_thread(invoke_sync)
        if inspect.isawaitable(value):
            value = await value
            if _on_result is not None:
                _on_result(value)
        return value

    return await asyncio.wait_for(invoke(), timeout=max(0.001, float(timeout_seconds)))


async def _delete_provider_file(delete: Callable[..., Any], name: str) -> None:
    try:
        await _provider_call(delete, timeout_seconds=_FILE_DELETE_TIMEOUT_SECONDS, name=name)
    except Exception:
        pass


def _consume_task_result(task: asyncio.Task[Any]) -> None:
    try:
        task.result()
    except BaseException:
        pass


class _UploadedFileTracker:
    """Own uploaded names and delete files that finish after cancellation."""

    def __init__(self, client: Any):
        self._loop = asyncio.get_running_loop()
        self._delete = getattr(getattr(client, "files", None), "delete", None)
        self._lock = threading.Lock()
        self._closed = False
        self._names: list[str] = []

    def record(self, uploaded: Any) -> None:
        name = str(getattr(uploaded, "name", "") or "").strip()
        if not name:
            return
        with self._lock:
            if not self._closed:
                if name not in self._names:
                    self._names.append(name)
                return
        self._schedule_late_delete(name)

    def close(self) -> tuple[str, ...]:
        with self._lock:
            self._closed = True
            return tuple(self._names)

    def _schedule_late_delete(self, name: str) -> None:
        if not callable(self._delete):
            return

        def schedule() -> None:
            task = asyncio.create_task(_delete_provider_file(self._delete, name))
            task.add_done_callback(_consume_task_result)

        try:
            self._loop.call_soon_threadsafe(schedule)
        except RuntimeError:
            pass


def _response_text(response: Any) -> str:
    value = getattr(response, "text", None)
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _state_name(value: Any) -> str:
    state = getattr(value, "state", value)
    if isinstance(state, dict):
        state = state.get("name") or state.get("state")
    state = getattr(state, "name", state)
    return str(state or "").strip().upper().split(".")[-1]


def _usage_value(metadata: Any, *names: str) -> int:
    for name in names:
        value = metadata.get(name) if isinstance(metadata, dict) else getattr(metadata, name, None)
        if isinstance(value, bool):
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError, OverflowError):
            continue
        if parsed >= 0:
            return parsed
    return 0


def _failure(status: str) -> dict[str, Any]:
    return {"ok": False, "provider": "gemini", "model": GEMINI_FREE_MODEL, "text": "", "usage": {"input_tokens": 0, "output_tokens": 0}, "status": status}


class GeminiPublicChatProvider:
    """One-call public Gemini adapter with strict video readiness."""

    def __init__(self, *, client: Any, sleep: Callable[[float], Any] = asyncio.sleep):
        self.client = client
        self.sleep = sleep

    async def _sleep(self, seconds: float) -> None:
        await _await(self.sleep(seconds))

    async def _active_video_file(
        self,
        provider_file_name: str,
        *,
        poll_interval: float,
        max_polls: int,
        deadline_seconds: float | None = None,
    ) -> tuple[str, Any | None]:
        getter = getattr(getattr(self.client, "files", None), "get", None)
        if not callable(getter) or not provider_file_name:
            return "VIDEO_NOT_ACTIVE", None
        deadline_window = _VIDEO_PROCESSING_DEADLINE_SECONDS if deadline_seconds is None else deadline_seconds
        deadline = time.monotonic() + max(0.001, float(deadline_window))
        for attempt in range(max(1, int(max_polls or 1))):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return "VIDEO_TIMEOUT", None
            try:
                info = await _provider_call(
                    getter,
                    timeout_seconds=min(_FILE_GET_TIMEOUT_SECONDS, remaining),
                    name=provider_file_name,
                )
            except (TimeoutError, asyncio.TimeoutError):
                return "VIDEO_TIMEOUT", None
            except asyncio.CancelledError:
                raise
            except Exception:
                return "VIDEO_NOT_ACTIVE", None
            state = _state_name(info)
            if state == "ACTIVE":
                return "ACTIVE", info
            if state in _VIDEO_TERMINAL_FAILURES:
                return "VIDEO_FAILED", None
            if attempt + 1 < max(1, int(max_polls or 1)):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return "VIDEO_TIMEOUT", None
                try:
                    await asyncio.wait_for(
                        self._sleep(min(max(0.0, float(poll_interval or 0)), remaining)),
                        timeout=remaining,
                    )
                except (TimeoutError, asyncio.TimeoutError):
                    return "VIDEO_TIMEOUT", None
        return "VIDEO_NOT_ACTIVE", None

    async def generate(
        self,
        prompt: str,
        media: Iterable[Any] | None = None,
        *,
        history: Iterable[Any] | None = None,
        system_instruction: str = "",
        max_output_tokens: int = 2048,
        temperature: float = 0.2,
        video_poll_interval: float = 1.0,
        video_max_polls: int = 30,
    ) -> dict[str, Any]:
        generate_content = getattr(getattr(self.client, "models", None), "generate_content", None)
        if not callable(generate_content):
            return _failure("NOT_CONFIGURED")
        text_prompt = str(prompt or "").strip()
        contents = list(history or [])
        if text_prompt:
            contents.append(text_prompt)
        if not contents:
            return _failure("FAIL_EMPTY_INPUT")
        for item in media or ():
            if isinstance(item, MediaInput):
                try:
                    validate_media_input(item)
                except Exception:
                    return _failure("INVALID_INPUT")
            kind = str(getattr(item, "kind", "") or "").strip().lower()
            provider_name = str(getattr(item, "provider_file_name", "") or "").strip()
            if kind == "video":
                state, info = await self._active_video_file(provider_name, poll_interval=video_poll_interval, max_polls=video_max_polls)
                if state != "ACTIVE":
                    return _failure(state)
                contents.append(info)
            elif provider_name:
                contents.append(provider_name)
        config = {"max_output_tokens": max(1, int(max_output_tokens or 1)), "temperature": float(temperature)}
        if str(system_instruction or "").strip():
            config["system_instruction"] = str(system_instruction).strip()
        response = None
        for candidate_model in [GEMINI_FREE_MODEL, "gemini-2.0-flash", "gemini-1.5-flash"]:
            try:
                response = await _provider_call(
                    generate_content,
                    timeout_seconds=_GENERATE_TIMEOUT_SECONDS,
                    model=candidate_model,
                    contents=contents,
                    config=config,
                )
                if response:
                    break
            except asyncio.CancelledError:
                raise
            except Exception:
                continue
        if not response:
            return _failure("FAIL_PROVIDER")
        text = _response_text(response)
        if not text:
            return _failure("FAIL_EMPTY_RESPONSE")
        metadata = getattr(response, "usage_metadata", None)
        return {"ok": True, "provider": "gemini", "model": GEMINI_FREE_MODEL, "text": text, "usage": {"input_tokens": _usage_value(metadata, "prompt_token_count", "input_tokens"), "output_tokens": _usage_value(metadata, "candidates_token_count", "output_tokens")}, "status": "SUCCESS"}


def _legacy_result(*, ok: bool, status: str, text: str = "") -> dict[str, Any]:
    return {"ok": bool(ok), "status": status, "text": text.strip() if ok else "", "model": GEMINI_FREE_MODEL}


def _legacy_history(messages: Any) -> list[tuple[str, str]] | None:
    if not isinstance(messages, Sequence) or isinstance(messages, (str, bytes)):
        return None
    selected = list(messages)[-_MAX_HISTORY:]
    result: list[tuple[str, str]] = []
    for item in selected:
        if not isinstance(item, dict):
            return None
        role = str(item.get("role") or "").strip().lower()
        role = "model" if role in {"assistant", "model"} else role
        content = item.get("content")
        if isinstance(content, list):
            if any(not isinstance(part, dict) or part.get("type", "text") != "text" or not isinstance(part.get("text"), str) for part in content):
                return None
            text = "\n".join(str(part["text"]).strip() for part in content if str(part["text"]).strip())
        else:
            text = content.strip() if isinstance(content, str) else ""
        if role not in {"user", "model"} or not text or len(text) > 8_000:
            return None
        result.append((role, text))
    while result and result[0][0] == "model":
        result.pop(0)
    if len(result) > _MAX_VALID_HISTORY:
        result = result[-_MAX_VALID_HISTORY:]
    if not result or result[0][0] != "user" or result[-1][0] != "user":
        return None
    if any(role != ("user" if index % 2 == 0 else "model") for index, (role, _) in enumerate(result)):
        return None
    return result


def _legacy_attachment_values(item: Any) -> tuple[str, str, int, Path] | None:
    kind = str(getattr(item, "kind", "") or "").strip().lower()
    mime = str(getattr(item, "mime_type", "") or "").strip().lower().split(";", 1)[0]
    if kind not in _KIND_MIMES or mime not in _KIND_MIMES[kind]:
        return None
    try:
        raw_size = getattr(item, "actual_bytes")
        size = int(raw_size)
        path = Path(getattr(item, "temporary_path"))
    except (TypeError, ValueError, OverflowError):
        return None
    if isinstance(raw_size, bool) or not 1 <= size <= _KIND_LIMITS[kind] or not path.is_file() or path.stat().st_size != size:
        return None
    return kind, mime, size, path


async def _legacy_attachment_parts(client: Any, attachments: Iterable[Any], uploaded_files: _UploadedFileTracker) -> list[Any] | None:
    items = list(attachments or ())
    if len(items) > 4:
        return None
    validated = [_legacy_attachment_values(item) for item in items]
    if any(item is None for item in validated):
        return None
    parts: list[Any] = []
    for kind, mime, size, path in (item for item in validated if item is not None):
        if size <= _INLINE_RAW_BYTES:
            data = path.read_bytes()
            if len(data) != size:
                return None
            parts.append({"inline_data": {"mime_type": mime, "data": data}})
            continue
        files = getattr(client, "files", None)
        upload = getattr(files, "upload", None)
        if not callable(upload):
            return None
        uploaded = await _provider_call(
            upload,
            timeout_seconds=_FILE_UPLOAD_TIMEOUT_SECONDS,
            _on_result=uploaded_files.record,
            file=path,
        )
        name = str(getattr(uploaded, "name", "") or "").strip()
        uri = str(getattr(uploaded, "uri", "") or "").strip()
        if not name:
            return None
        if kind == "video" and _state_name(uploaded) != "ACTIVE":
            state, uploaded = await GeminiPublicChatProvider(client=client)._active_video_file(name, poll_interval=1.0, max_polls=60)
            if state == "VIDEO_TIMEOUT":
                raise asyncio.TimeoutError("video processing deadline exceeded")
            if state != "ACTIVE":
                return None
            uri = str(getattr(uploaded, "uri", "") or "").strip()
        if not uri:
            return None
        parts.append({"file_data": {"file_uri": uri, "mime_type": mime}})
    return parts


def _legacy_status(exc: Exception) -> str:
    message = str(exc).lower()
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code == 429 or "resource_exhausted" in message or "429" in message:
        return "rate_limited"
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)) or "timeout" in message or "timed out" in message:
        return "timeout"
    return "provider_error"


async def generate_public_chat_text(
    client: Any,
    *,
    system_prompt: str,
    messages: Sequence[dict[str, Any]],
    attachments: Iterable[Any] = (),
    max_output_tokens: int = 1200,
) -> dict[str, Any]:
    """Generate exactly one text response, with request-scoped cleanup."""
    generate_content = getattr(getattr(client, "models", None), "generate_content", None) if client is not None else None
    if not callable(generate_content):
        return _legacy_result(ok=False, status="unavailable")
    if not isinstance(system_prompt, str) or not system_prompt.strip() or len(system_prompt) > 8_000:
        return _legacy_result(ok=False, status="invalid_input")
    if isinstance(max_output_tokens, bool) or not isinstance(max_output_tokens, int) or not 1 <= max_output_tokens <= 4_096:
        return _legacy_result(ok=False, status="invalid_input")
    history = _legacy_history(messages)
    if history is None:
        return _legacy_result(ok=False, status="invalid_input")
    uploaded_files = _UploadedFileTracker(client)
    try:
        parts = await _legacy_attachment_parts(client, attachments, uploaded_files)
        if parts is None:
            return _legacy_result(ok=False, status="invalid_input")
        contents = [{"role": role, "parts": [{"text": text}]} for role, text in history]
        if parts:
            contents[-1] = {"role": "user", "parts": [{"text": history[-1][1]}, *parts]}
        response = None
        last_exc = None
        for candidate_model in [GEMINI_FREE_MODEL, "gemini-2.0-flash", "gemini-1.5-flash"]:
            try:
                response = await _provider_call(
                    generate_content,
                    timeout_seconds=_GENERATE_TIMEOUT_SECONDS,
                    model=candidate_model,
                    contents=contents,
                    config={"system_instruction": system_prompt.strip(), "max_output_tokens": max_output_tokens, "response_mime_type": "text/plain"},
                )
                if response:
                    break
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_exc = exc
                continue
        if response is None and last_exc is not None:
            raise last_exc
        text = _response_text(response)
        if not text:
            return _legacy_result(ok=False, status="empty_response")
        return _legacy_result(ok=True, status="ok", text=text)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return _legacy_result(ok=False, status=_legacy_status(exc))
    finally:
        delete = getattr(getattr(client, "files", None), "delete", None) if client is not None else None
        if callable(delete):
            for name in uploaded_files.close():
                await _delete_provider_file(delete, name)
        else:
            uploaded_files.close()


__all__ = ["GEMINI_FREE_MODEL", "generate_public_chat_text"]
