"""Key4U provider adapter for admin-only TOAN AAS smoke tests.

Public routing is intentionally disabled by default. This module never logs or
returns API keys and keeps provider raw responses out of user-facing text.
"""

from __future__ import annotations

import base64
import os
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

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


def join_provider_url(base_url: str, endpoint: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    path = str(endpoint or "").strip()
    if not path:
        return base
    if path.startswith("http://") or path.startswith("https://"):
        return path.rstrip("/")
    match = re.match(r"^(https?://[^/]+)(/.*)?$", base)
    if not match:
        base_segments = [segment for segment in base.split("/") if segment]
        path_segments = [segment for segment in path.strip("/").split("/") if segment]
        prefix = ""
    else:
        prefix = match.group(1)
        base_segments = [segment for segment in (match.group(2) or "").strip("/").split("/") if segment]
        path_segments = [segment for segment in path.strip("/").split("/") if segment]
    overlap = 0
    max_overlap = min(len(base_segments), len(path_segments))
    for size in range(max_overlap, 0, -1):
        if base_segments[-size:] == path_segments[:size]:
            overlap = size
            break
    joined_segments = [*base_segments, *path_segments[overlap:]]
    joined_path = "/".join(joined_segments)
    if prefix:
        return prefix + ("/" + joined_path if joined_path else "")
    return "/" + joined_path if joined_path else ""


def safe_join_url(base_url: str, endpoint: str) -> str:
    return join_provider_url(base_url, endpoint)


def scoped_join_url(api_base_url: str, scoped_base_url: str, endpoint: str, scope_prefix: str) -> str:
    path = str(endpoint or "").strip()
    if path.startswith("http://") or path.startswith("https://"):
        return path.rstrip("/")
    scoped_base = str(scoped_base_url or "").strip() or join_provider_url(api_base_url, scope_prefix)
    return join_provider_url(scoped_base, path)


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


GROUP_UNAVAILABLE_MARKERS = (
    "no available channel",
    "channel unavailable",
    "no channel",
    "group unavailable",
    "under group",
    "provider unavailable",
    "distributor",
)

KEY4U_USER_APIKEY_BALANCE_DISCOVERY_CANDIDATES = (
    "/user/wallet/balance",
    "/wallet/balance",
    "/user/balance",
    "/api/user/wallet/balance",
    "/api/wallet/balance",
    "/user-api-key/wallet/balance",
    "/userapikey/wallet/balance",
    "/userApiKey/wallet/balance",
    "/logs/usage",
    "/user/usage",
    "/groups",
    "/health",
)

KEY4U_USAGE_DISCOVERY_HTTP_STATUSES = {401, 403, 404}
KEY4U_USAGE_AUTH_MODES = (
    "authorization_bearer",
    "x_api_key",
    "api_key",
    "authorization_raw",
)


def _is_group_or_channel_unavailable(status_code: int, message: Any) -> bool:
    if int(status_code or 0) != 503:
        return False
    msg = str(message or "").lower()
    return any(marker in msg for marker in GROUP_UNAVAILABLE_MARKERS)


def _classify_http(status_code: int, message: str = "") -> str:
    msg = str(message or "").lower()
    if any(marker in msg for marker in ("model not found", "invalid model", "model_not_found", "invalid_model")):
        return "FAIL_MODEL_NOT_FOUND"
    if _is_group_or_channel_unavailable(status_code, message):
        return "FAIL_PROVIDER_GROUP_UNAVAILABLE"
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


PLACEHOLDER_TASK_IDS = {
    "",
    "*",
    "-",
    "----",
    "<task_id>",
    "<task_id_thật>",
    "task_id",
    "task-id",
    "taskid",
    "task id",
    "your_task_id",
    "your-task-id",
    "none",
    "null",
    "abc",
    "abc123",
}


def is_placeholder_task_id(value: str | None) -> bool:
    raw = str(value or "").strip()
    lowered = raw.lower()
    if lowered in PLACEHOLDER_TASK_IDS:
        return True
    if lowered.startswith("<") and lowered.endswith(">"):
        return True
    if "task_id" in lowered or "taskid" in lowered or "your_task" in lowered:
        return True
    compact = re.sub(r"[^a-zA-Z0-9_-]", "", raw)
    if compact and len(compact) < 8:
        return True
    return False


SUNO_RESULT_FIELD_KEYS = (
    "status", "state", "result", "output",
    "audio_url", "url", "file_url", "download_url", "stream_url",
)
SUNO_AUDIO_URL_KEYS = {
    "audio_url", "audiourl", "audio", "download_url", "downloadurl",
    "stream_url", "streamurl", "file_url", "fileurl", "output_url",
    "outputurl", "source_audio_url", "sourceaudiourl", "url",
}
SUNO_STATUS_KEYS = {"status", "state", "task_status", "taskstatus"}
SUNO_FAILURE_KEYS = {"fail_reason", "failreason", "error", "message", "reason"}
SUNO_TEXT_KEYS = {"prompt", "text", "lyrics", "lyric"}
SUNO_ID_KEYS = {"clip_id", "clipid", "id"}
SUNO_AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")


def _suno_payload_field_presence(payload: Any) -> dict[str, bool]:
    fields = {key: False for key in SUNO_RESULT_FIELD_KEYS}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                lowered = str(key or "").strip().lower()
                for field in fields:
                    if lowered == field:
                        fields[field] = True
                visit(child)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)
    return fields


def _suno_first_string_for_keys(payload: Any, keys: set[str]) -> str:
    found = ""

    def visit(value: Any) -> None:
        nonlocal found
        if found:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                lowered = str(key or "").strip().lower()
                if lowered in keys and isinstance(child, (str, int, float)):
                    found = str(child).strip()
                    return
                visit(child)
                if found:
                    return
        elif isinstance(value, list):
            for item in value:
                visit(item)
                if found:
                    return

    visit(payload)
    return found


def _suno_audio_urls_from_payload(payload: Any) -> list[str]:
    urls: list[str] = []

    def add_candidate(key: str, raw: Any) -> None:
        if not isinstance(raw, str):
            return
        value = raw.strip()
        if not value.startswith(("http://", "https://")):
            return
        lowered_key = str(key or "").strip().lower()
        lowered_url = value.lower().split("?", 1)[0]
        key_supports_audio = lowered_key in SUNO_AUDIO_URL_KEYS or "audio" in lowered_key
        url_supports_audio = lowered_url.endswith(SUNO_AUDIO_EXTENSIONS) or "/audio" in lowered_url
        if (key_supports_audio or url_supports_audio) and value not in urls:
            urls.append(value)

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                add_candidate(key, child)
                visit(child)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)
    return urls


def _normalize_suno_query_status(raw_status: str, *, has_audio: bool, http_status: int = 0) -> str:
    lowered = str(raw_status or "").strip().lower()
    if has_audio:
        return "SUCCESS"
    if lowered in {"success", "ok", "complete", "completed", "succeeded", "done", "finish", "finished"}:
        return "SUCCESS"
    if lowered in {"submitted", "queued", "queue", "pending", "processing", "running", "in_progress", "generating", "process"}:
        return "PROCESSING"
    if lowered in {"fail", "failed", "error", "cancelled", "canceled", "timeout"}:
        return "FAILED"
    if http_status and int(http_status or 0) >= 400:
        return _classify_http(int(http_status or 0), raw_status)
    return raw_status.upper() if raw_status else "PROCESSING"


def should_try_model_fallback(result: dict[str, Any]) -> bool:
    haystack = " ".join(
        str(result.get(key) or "")
        for key in ("status", "error_class", "error_message_safe", "message_user_safe", "recommendation")
    ).lower()
    return any(
        marker in haystack
        for marker in (
            "model_not_found",
            "invalid_model",
            "model not found",
            "invalid model",
            "need_model",
            "fail_provider_group_unavailable",
            "no available channel",
            "channel unavailable",
            "group unavailable",
            "under group",
        )
    )


def _add_video_unavailable_guidance(result: dict[str, Any]) -> dict[str, Any]:
    if str(result.get("error_class") or "") == "FAIL_PROVIDER_GROUP_UNAVAILABLE":
        result["message_user_safe"] = "Nhà cung cấp video Key4U hiện chưa có kênh khả dụng cho model này."
        result["recommendation"] = "Thử model khác hoặc kiểm tra group/model trong Key4U dashboard."
    return result


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
    final_url: str = "",
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
        "final_url": final_url or "",
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
    video_auth_header_value: str = ""
    system_api_key: str = ""
    usage_auth_header_name: str = "Authorization"
    usage_auth_header_value: str = ""
    usage_auth_mode: str = ""
    base_url: str = "https://api.key4u.shop"
    openai_base_url: str = "https://api.key4u.shop/v1"
    minimax_base_url: str = "https://api.key4u.shop/minimax"
    voice_base_url: str = "https://voice.key4u.shop/api/v1"
    suno_base_url: str = "https://api.key4u.shop/suno"
    smart_routing: bool = True
    public_enabled: bool = False
    admin_smoke_enabled: bool = True
    usage_endpoint: str = ""
    usage_check_url: str = ""
    balance_endpoint: str = ""
    balance_url: str = ""
    wallet_balance_url: str = ""
    usage_discovery_enabled: bool = False
    models_endpoint: str = ""
    chat_endpoint: str = "/v1/chat/completions"
    image_edit_endpoint: str = "/v1/images/edits"
    nano_banana_edit_endpoint: str = "/fal-ai/nano-banana/edit"
    video_create_endpoint: str = "/v1/video/create"
    video_query_endpoint: str = "/v1/video/query"
    tts_endpoint: str = ""
    tts_async_endpoint: str = ""
    tts_query_endpoint: str = ""
    tts_retrieve_endpoint: str = ""
    voice_tts_endpoint: str = ""
    minimax_upload_endpoint: str = ""
    minimax_clone_endpoint: str = ""
    stt_endpoint: str = ""
    suno_create_endpoint: str = ""
    suno_query_endpoint: str = ""
    suno_lyrics_endpoint: str = ""
    suno_wav_endpoint: str = ""
    suno_timing_endpoint: str = ""
    rerank_endpoint: str = ""
    chat_model: str = "qwen-plus"
    vision_model: str = "gemini-2.5-flash"
    image_edit_model: str = "grok-imagine-image-pro"
    nano_banana_edit_model: str = "nano-banana"
    video_model: str = "veo3.1-fast"
    tts_model: str = "speech-02-hd"
    tts_alt_model: str = "speech-2.6-hd"
    clone_model: str = "speech-2.8-hd"
    stt_model: str = ""
    suno_model: str = "chirp-v4"
    rerank_model: str = ""


def config_from_env() -> Key4UConfig:
    api_base = _env("KEY4U_API_BASE", _env("KEY4U_BASE_URL", "https://api.key4u.shop"))
    usage_url = _env("KEY4U_USAGE_ENDPOINT", _env("KEY4U_USAGE_URL", _env("KEY4U_USAGE_CHECK_URL", "")))
    balance_url = _env("KEY4U_BALANCE_URL", "")
    wallet_balance_url = _env("KEY4U_WALLET_BALANCE_URL", "")
    balance_endpoint = _env("KEY4U_BALANCE_ENDPOINT", balance_url or wallet_balance_url or _env("KEY4U_USAGE_CHECK_URL", _env("KEY4U_USAGE_URL", "")))
    return Key4UConfig(
        enabled=_flag("KEY4U_ENABLED", "false"),
        api_key=_env("KEY4U_TOKEN", _env("KEY4U_API_KEY", "")),
        video_auth_header_value=_env("KEY4U_VIDEO_AUTH_HEADER_VALUE", ""),
        system_api_key=_env("KEY4U_SYSTEM_API_KEY", ""),
        usage_auth_header_name=_env("KEY4U_USAGE_AUTH_HEADER_NAME", "Authorization"),
        usage_auth_header_value=_env("KEY4U_USAGE_AUTH_HEADER_VALUE", ""),
        usage_auth_mode=_env("KEY4U_USAGE_AUTH_MODE", ""),
        base_url=api_base,
        openai_base_url=_env("KEY4U_OPENAI_BASE_URL", safe_join_url(api_base, "/v1")),
        minimax_base_url=_env("KEY4U_MINIMAX_BASE", safe_join_url(api_base, "/minimax")),
        voice_base_url=_env("KEY4U_VOICE_BASE", "https://voice.key4u.shop/api/v1"),
        suno_base_url=_env("KEY4U_SUNO_BASE", safe_join_url(api_base, "/suno")),
        smart_routing=_flag("KEY4U_SMART_ROUTING", "true"),
        public_enabled=_flag("KEY4U_PUBLIC_ENABLED", "false"),
        admin_smoke_enabled=_flag("KEY4U_ADMIN_SMOKE_ENABLED", "true"),
        usage_endpoint=usage_url,
        usage_check_url=_env("KEY4U_USAGE_CHECK_URL", ""),
        balance_endpoint=balance_endpoint,
        balance_url=balance_url,
        wallet_balance_url=wallet_balance_url,
        usage_discovery_enabled=_flag("KEY4U_USAGE_DISCOVERY_ENABLED", "false"),
        models_endpoint=_env("KEY4U_MODELS_ENDPOINT", ""),
        chat_endpoint=_env("KEY4U_CHAT_COMPLETIONS_ENDPOINT", _env("KEY4U_CHAT_ENDPOINT", "/v1/chat/completions")),
        image_edit_endpoint=_env("KEY4U_IMAGE_EDITS_ENDPOINT", _env("KEY4U_IMAGE_EDIT_ENDPOINT", "/v1/images/edits")),
        nano_banana_edit_endpoint=_env("KEY4U_NANO_BANANA_EDIT_ENDPOINT", "/fal-ai/nano-banana/edit"),
        video_create_endpoint=_env("KEY4U_VIDEO_CREATE_ENDPOINT", "/v1/video/create"),
        video_query_endpoint=_env("KEY4U_VIDEO_QUERY_ENDPOINT", "/v1/video/query"),
        tts_endpoint=_env("KEY4U_TTS_ENDPOINT", "/v1/t2a_v2"),
        tts_async_endpoint=_env("KEY4U_MINIMAX_TTS_ASYNC_ENDPOINT", "/v1/t2a_async_v2"),
        tts_query_endpoint=_env("KEY4U_MINIMAX_TTS_QUERY_ENDPOINT", "/v1/query/t2a_async_query_v2"),
        tts_retrieve_endpoint=_env("KEY4U_MINIMAX_TTS_RETRIEVE_ENDPOINT", "/v1/files/retrieve"),
        voice_tts_endpoint=_env("KEY4U_VOICE_TTS_ENDPOINT", "/tts"),
        minimax_upload_endpoint=_env("KEY4U_MINIMAX_UPLOAD_ENDPOINT", "/v1/files"),
        minimax_clone_endpoint=_env("KEY4U_MINIMAX_CLONE_ENDPOINT", "/v1/voice_clone"),
        stt_endpoint=_env("KEY4U_STT_ENDPOINT", "/audio/transcriptions"),
        suno_create_endpoint=_env("KEY4U_SUNO_CREATE_ENDPOINT", "/submit/music"),
        suno_query_endpoint=_env("KEY4U_SUNO_QUERY_ENDPOINT", "/fetch/{taskId}"),
        suno_lyrics_endpoint=_env("KEY4U_SUNO_LYRICS_ENDPOINT", "/submit/lyrics"),
        suno_wav_endpoint=_env("KEY4U_SUNO_WAV_ENDPOINT", "/act/wav/{clipId}"),
        suno_timing_endpoint=_env("KEY4U_SUNO_TIMING_ENDPOINT", "/act/timing/{clipId}"),
        rerank_endpoint=_env("KEY4U_RERANK_ENDPOINT", ""),
        chat_model=_env("KEY4U_DEFAULT_CHAT_MODEL", _env("KEY4U_CHAT_MODEL", "qwen-plus")),
        vision_model=_env("KEY4U_DEFAULT_VISION_MODEL", _env("KEY4U_VISION_MODEL", "gemini-2.5-flash")),
        image_edit_model=_env("KEY4U_DEFAULT_IMAGE_EDIT_MODEL", _env("KEY4U_IMAGE_EDIT_MODEL", "grok-imagine-image-pro")),
        nano_banana_edit_model=_env("KEY4U_NANO_BANANA_EDIT_MODEL", "nano-banana"),
        video_model=_env("KEY4U_DEFAULT_VIDEO_MODEL", _env("KEY4U_VIDEO_MODEL", "veo3.1-fast")),
        tts_model=_env("KEY4U_DEFAULT_TTS_MODEL", _env("KEY4U_TTS_MODEL", "speech-02-hd")),
        tts_alt_model=_env("KEY4U_ALT_TTS_MODEL", "speech-2.6-hd"),
        clone_model=_env("KEY4U_MINIMAX_CLONE_MODEL", "speech-2.8-hd"),
        stt_model=_env("KEY4U_STT_MODEL", "whisper-1"),
        suno_model=_env("KEY4U_DEFAULT_MUSIC_MODEL", _env("KEY4U_SUNO_MODEL", "chirp-v4")),
        rerank_model=_env("KEY4U_RERANK_MODEL", ""),
    )


class Key4UProvider:
    def __init__(self, config: Key4UConfig | None = None):
        self.config = config or config_from_env()

    def is_configured(self) -> bool:
        return bool(self.config.enabled and self.config.admin_smoke_enabled and self.config.api_key)

    def usage_auth_configured(self) -> bool:
        return bool(self._usage_auth_info()["value"])

    def usage_configured(self) -> bool:
        return bool(self.config.enabled and self.usage_auth_configured())

    def get_status(self) -> dict[str, Any]:
        return {
            "provider": "key4u",
            "enabled": bool(self.config.enabled),
            "public_enabled": bool(self.config.public_enabled),
            "admin_smoke_enabled": bool(self.config.admin_smoke_enabled),
            "smart_routing": bool(self.config.smart_routing),
            "api_key": mask_key(self.config.api_key),
            "configured": self.is_configured(),
            "usage_auth_configured": self.usage_auth_configured(),
            "usage_auth_source": self._usage_auth_info()["source"],
            "usage_auth_header_name": self._usage_auth_info()["header_name"],
            "usage_auth_scheme_prefix": self._usage_auth_info()["scheme_prefix"],
            "usage_auth_mode": self._usage_auth_info()["auth_mode"],
            "base_url": self.config.base_url,
            "openai_base_url": self.config.openai_base_url,
            "minimax_base_url": self.config.minimax_base_url,
            "voice_base_url": self.config.voice_base_url,
            "suno_base_url": self.config.suno_base_url,
            "minimax_tts_final_url": self._minimax_url(self.config.tts_endpoint) if self.config.tts_endpoint else "",
            "minimax_clone_upload_final_url": self._minimax_url(self.config.minimax_upload_endpoint) if self.config.minimax_upload_endpoint else "",
            "minimax_clone_final_url": self._minimax_url(self.config.minimax_clone_endpoint) if self.config.minimax_clone_endpoint else "",
            "suno_submit_final_url": self._suno_url(self.config.suno_create_endpoint) if self.config.suno_create_endpoint else "",
            "suno_fetch_final_url": self._suno_url(self._path_with_id(self.config.suno_query_endpoint, "{taskId}", "taskId", "task_id")) if self.config.suno_query_endpoint else "",
            "suno_lyrics_final_url": self._suno_url(self.config.suno_lyrics_endpoint) if self.config.suno_lyrics_endpoint else "",
            "usage_endpoint": "configured" if self.config.usage_endpoint else "NEED_ENDPOINT",
            "usage_check_url": "configured" if self.config.usage_check_url else "NEED_ENDPOINT",
            "balance_endpoint": "configured" if self.config.balance_endpoint else "NEED_ENDPOINT",
            "balance_url": "configured" if self.config.balance_url else "NEED_ENDPOINT",
            "wallet_balance_url": "configured" if self.config.wallet_balance_url else "NEED_ENDPOINT",
            "usage_discovery_enabled": bool(self.config.usage_discovery_enabled),
            "models_endpoint": "configured" if self.config.models_endpoint else "NEED_ENDPOINT",
            "chat_model": self.config.chat_model or "",
            "vision_model": self.config.vision_model or "",
            "image_edit_model": self.config.image_edit_model or "",
            "nano_banana_edit_model": self.config.nano_banana_edit_model or "",
            "video_model": self.config.video_model or "",
            "video_create_endpoint": self.config.video_create_endpoint or "missing endpoint",
            "video_query_endpoint": self.config.video_query_endpoint or "missing endpoint",
            "video_submit_final_url": safe_join_url(self.config.base_url, self.config.video_create_endpoint) if self.config.video_create_endpoint else "",
            "video_fetch_final_url": (
                safe_join_url(self.config.base_url, self.config.video_query_endpoint) + "?id={task_id}"
                if self.config.video_query_endpoint else ""
            ),
            "tts_model": self.config.tts_model or "",
            "tts_alt_model": self.config.tts_alt_model or "",
            "clone_model": self.config.clone_model or "",
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
            "tts_async": "needs_endpoint_docs" if not self.config.tts_async_endpoint else "admin_smoke",
            "voice_tts_fallback": "needs_endpoint_docs" if not self.config.voice_tts_endpoint else "admin_smoke",
            "stt": "needs_endpoint_docs" if not self.config.stt_endpoint else "admin_smoke",
            "translate": "via_chat_if_chat_model_pass",
            "suno": "needs_endpoint_docs" if not self.config.suno_create_endpoint else "admin_smoke",
            "suno_lyrics": "needs_endpoint_docs" if not self.config.suno_lyrics_endpoint else "admin_smoke",
            "suno_wav": "needs_endpoint_docs" if not self.config.suno_wav_endpoint else "admin_smoke",
            "suno_timing": "needs_endpoint_docs" if not self.config.suno_timing_endpoint else "admin_smoke",
            "rerank": "local_keyword_fallback" if not self.config.rerank_endpoint else "admin_smoke",
        }

    def _headers(self) -> dict[str, str]:
        auth_value = str(self.config.api_key or self.config.video_auth_header_value or "").strip()
        if auth_value and not auth_value.lower().startswith(("bearer ", "apikey ", "key ")):
            auth_value = f"Bearer {auth_value}"
        return {
            "Authorization": auth_value,
            "Accept": "application/json",
        }

    def _normalize_usage_auth_mode(self, mode: str = "") -> str:
        selected = str(mode or self.config.usage_auth_mode or "").strip().lower().replace("-", "_")
        if selected in {"x_api_key", "xapikey", "x_api"}:
            return "x_api_key"
        if selected in {"api_key", "apikey"}:
            return "api_key"
        if selected in {"authorization_raw", "raw", "authorization"}:
            return "authorization_raw"
        if selected in {"authorization_bearer", "bearer"}:
            return "authorization_bearer"
        header = str(self.config.usage_auth_header_name or "Authorization").strip().lower()
        if header == "x-api-key":
            return "x_api_key"
        if header == "api-key":
            return "api_key"
        return "authorization_bearer"

    def _usage_auth_info(self, mode: str = "") -> dict[str, str]:
        candidates = (
            ("usage_auth_header_value", self.config.usage_auth_header_value),
            ("system_api_key", self.config.system_api_key),
            ("api_key", self.config.api_key),
            ("video_auth_header_value", self.config.video_auth_header_value),
        )
        source = "missing"
        raw_value = ""
        for candidate_source, candidate_value in candidates:
            value = str(candidate_value or "").strip()
            if value:
                source = candidate_source
                raw_value = value
                break
        auth_mode = self._normalize_usage_auth_mode(mode)
        if auth_mode == "x_api_key":
            header_name = "x-api-key"
        elif auth_mode == "api_key":
            header_name = "api-key"
        else:
            header_name = "Authorization"
        header_value = raw_value
        if auth_mode == "authorization_bearer" and header_value and not header_value.lower().startswith(("bearer ", "apikey ", "key ", "basic ")):
            header_value = f"Bearer {header_value}"
        scheme_prefix = "missing"
        if header_value:
            scheme_prefix = header_value.split(" ", 1)[0] if " " in header_value else "raw"
        return {
            "source": source,
            "header_name": header_name,
            "value": header_value,
            "scheme_prefix": scheme_prefix,
            "auth_mode": auth_mode,
        }

    def _usage_headers(self, mode: str = "") -> dict[str, str]:
        auth_info = self._usage_auth_info(mode)
        headers = {"Accept": "application/json"}
        if auth_info["value"]:
            headers[auth_info["header_name"]] = auth_info["value"]
        return headers

    def _usage_endpoint_debug(self, endpoint_path: str, mode: str = "") -> dict[str, Any]:
        endpoint = safe_join_url(self.config.base_url, endpoint_path)
        parsed = urlparse(endpoint)
        auth_info = self._usage_auth_info(mode)
        return {
            "usage_auth_source": auth_info["source"],
            "usage_auth_header_name": auth_info["header_name"],
            "usage_auth_scheme_prefix": auth_info["scheme_prefix"],
            "usage_auth_mode": auth_info["auth_mode"],
            "usage_endpoint_host": parsed.netloc or "",
            "usage_endpoint_path": parsed.path or "",
        }

    @staticmethod
    def _response_shape(data: Any) -> str:
        if isinstance(data, dict):
            keys = [str(key) for key in sorted(data.keys())[:10]]
            nested = data.get("data")
            if isinstance(nested, dict):
                keys.extend(f"data.{key}" for key in sorted(str(key) for key in nested.keys())[:8])
                wallet = nested.get("wallet")
                if isinstance(wallet, dict):
                    keys.extend(f"data.wallet.{key}" for key in sorted(str(key) for key in wallet.keys())[:6])
            return ",".join(keys) or "dict_empty"
        if isinstance(data, list):
            return "list"
        return type(data).__name__

    @staticmethod
    def _safe_endpoint_host_path(base_url: str, endpoint_path: str) -> str:
        parsed = urlparse(safe_join_url(base_url, endpoint_path))
        return (parsed.netloc or "") + (parsed.path or "")

    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        out = []
        seen = set()
        for item in items:
            safe = str(item or "").strip()
            if not safe or safe in seen:
                continue
            seen.add(safe)
            out.append(safe)
        return out

    def _usage_candidate_endpoints(self, primary_endpoint: str, capability: str) -> list[str]:
        candidates = []
        if capability == "balance":
            candidates.extend([
                primary_endpoint,
                self.config.balance_endpoint,
                self.config.wallet_balance_url,
                self.config.balance_url,
                self.config.usage_check_url,
                self.config.usage_endpoint,
            ])
        else:
            candidates.extend([
                primary_endpoint,
                self.config.usage_endpoint,
                self.config.usage_check_url,
                self.config.balance_endpoint,
                self.config.wallet_balance_url,
                self.config.balance_url,
            ])
        if self.config.usage_discovery_enabled:
            candidates.extend(KEY4U_USER_APIKEY_BALANCE_DISCOVERY_CANDIDATES)
        return self._dedupe(candidates)

    def _usage_attempt_label(self, endpoint_path: str, auth_mode: str, result: dict[str, Any]) -> str:
        return f"{self._safe_endpoint_host_path(self.config.base_url, endpoint_path)}|{auth_mode}|{int(result.get('http_status') or 0)}"

    def _apply_usage_debug(
        self,
        result: dict[str, Any],
        endpoint_path: str,
        auth_mode: str = "",
        *,
        candidates_tried: list[str] | None = None,
        auth_modes_tried: list[str] | None = None,
        success_endpoint_host_path: str = "",
        success_auth_mode: str = "",
    ) -> dict[str, Any]:
        debug = dict(result.get("raw_debug_admin_only") or {})
        debug.update(self._usage_endpoint_debug(endpoint_path, auth_mode))
        debug["usage_http_status"] = int(result.get("http_status") or 0)
        debug["usage_response_shape"] = self._response_shape(result.get("data"))
        debug["usage_reason"] = str(result.get("error_class") or result.get("status") or "-")
        debug["usage_endpoint_candidates_tried"] = list(candidates_tried or [])
        debug["usage_auth_modes_tried"] = list(auth_modes_tried or [])
        debug["usage_last_http_status"] = int(result.get("http_status") or 0)
        debug["usage_last_error_message_safe"] = str(result.get("error_message_safe") or "")[:220]
        debug["usage_success_endpoint_host_path"] = success_endpoint_host_path
        debug["usage_success_auth_mode"] = success_auth_mode
        result["raw_debug_admin_only"] = debug
        return result

    async def _request_usage_or_balance(self, capability: str, primary_endpoint: str) -> dict[str, Any]:
        if not primary_endpoint:
            return _result(ok=False, capability=capability, status="NEED_ENDPOINT", error_class="key4u_usage_url_missing", error_message_safe="key4u_usage_url_missing")
        primary_mode = self._usage_auth_info()["auth_mode"]
        candidates_tried: list[str] = []
        auth_modes_tried: list[str] = []
        result = await self.request_json("GET", primary_endpoint, headers=self._usage_headers(primary_mode))
        result["capability"] = capability
        candidates_tried.append(self._usage_attempt_label(primary_endpoint, primary_mode, result))
        auth_modes_tried.append(primary_mode)
        if result.get("ok"):
            return self._apply_usage_debug(
                result,
                primary_endpoint,
                primary_mode,
                candidates_tried=candidates_tried,
                auth_modes_tried=self._dedupe(auth_modes_tried),
                success_endpoint_host_path=self._safe_endpoint_host_path(self.config.base_url, primary_endpoint),
                success_auth_mode=primary_mode,
            )
        http_status = int(result.get("http_status") or 0)
        if not self.config.usage_discovery_enabled or http_status not in KEY4U_USAGE_DISCOVERY_HTTP_STATUSES:
            return self._apply_usage_debug(
                result,
                primary_endpoint,
                primary_mode,
                candidates_tried=candidates_tried,
                auth_modes_tried=self._dedupe(auth_modes_tried),
            )
        last_result = result
        last_endpoint = primary_endpoint
        last_mode = primary_mode
        for endpoint in self._usage_candidate_endpoints(primary_endpoint, capability):
            for auth_mode in KEY4U_USAGE_AUTH_MODES:
                if endpoint == primary_endpoint and auth_mode == primary_mode:
                    continue
                current = await self.request_json("GET", endpoint, headers=self._usage_headers(auth_mode))
                current["capability"] = capability
                candidates_tried.append(self._usage_attempt_label(endpoint, auth_mode, current))
                auth_modes_tried.append(auth_mode)
                if current.get("ok"):
                    return self._apply_usage_debug(
                        current,
                        endpoint,
                        auth_mode,
                        candidates_tried=candidates_tried,
                        auth_modes_tried=self._dedupe(auth_modes_tried),
                        success_endpoint_host_path=self._safe_endpoint_host_path(self.config.base_url, endpoint),
                        success_auth_mode=auth_mode,
                    )
                last_result = current
                last_endpoint = endpoint
                last_mode = auth_mode
        last_result["error_class"] = "KEY4U_USERAPIKEY_ENDPOINT_NOT_FOUND_OR_FORBIDDEN"
        return self._apply_usage_debug(
            last_result,
            last_endpoint,
            last_mode,
            candidates_tried=candidates_tried,
            auth_modes_tried=self._dedupe(auth_modes_tried),
        )

    def _minimax_url(self, endpoint: str) -> str:
        return scoped_join_url(self.config.base_url, self.config.minimax_base_url, endpoint, "/minimax/v1")

    def _voice_url(self, endpoint: str) -> str:
        return scoped_join_url(self.config.base_url, self.config.voice_base_url, endpoint, "/api/v1")

    def _suno_url(self, endpoint: str) -> str:
        return scoped_join_url(self.config.base_url, self.config.suno_base_url, endpoint, "/suno")

    @staticmethod
    def _path_with_id(endpoint: str, value: str, *names: str) -> str:
        safe_value = str(value or "").strip()
        path = str(endpoint or "")
        changed = False
        for name in names:
            token = "{" + name + "}"
            if token in path:
                path = path.replace(token, safe_value)
                changed = True
        if not changed and safe_value:
            path = path.rstrip("/") + "/" + safe_value
        return path

    async def request_json(
        self,
        method: str,
        endpoint_path: str,
        payload: dict[str, Any] | None = None,
        *,
        use_openai_base: bool = False,
        timeout_seconds: float = 30.0,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        base_url = self.config.openai_base_url if use_openai_base else self.config.base_url
        endpoint = safe_join_url(base_url, endpoint_path)
        request_headers = headers or self._headers()
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                if str(method or "GET").upper() == "POST":
                    response = await client.post(endpoint, headers={**request_headers, "Content-Type": "application/json"}, json=payload or {})
                else:
                    response = await client.get(endpoint, headers=request_headers)
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
        if not self.usage_configured():
            return self._missing_result("usage", "")
        if not self.config.usage_endpoint:
            return _result(ok=False, capability="usage", status="NEED_ENDPOINT", error_class="key4u_usage_url_missing", error_message_safe="key4u_usage_url_missing")
        return await self._request_usage_or_balance("usage", self.config.usage_endpoint)

    async def get_balance(self) -> dict[str, Any]:
        if not self.usage_configured():
            return self._missing_result("balance", "")
        if not self.config.balance_endpoint:
            return _result(ok=False, capability="balance", status="NEED_ENDPOINT", error_class="key4u_usage_url_missing", error_message_safe="key4u_usage_url_missing")
        return await self._request_usage_or_balance("balance", self.config.balance_endpoint)

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
        max_tokens: int = 1200,
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
            "messages": [{"role": "user", "content": str(prompt or "")[:6000]}],
            "max_tokens": max(80, min(4000, int(max_tokens or 1200))),
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

    async def translate(
        self,
        text: str,
        target_lang: str,
        source_lang: str = "auto",
        model: str = "qwen-mt-turbo",
        timeout_seconds: float = 30.0,
    ) -> dict[str, Any]:
        selected_model = str(model or "qwen-mt-turbo").strip()
        if not self.is_configured():
            return self._missing_result("translation", selected_model)
        content = str(text or "").strip()[:6000]
        if not content or not str(target_lang or "").strip():
            return _result(
                ok=False,
                capability="translation",
                model=selected_model,
                status="FAIL_BAD_REQUEST",
                error_class="FAIL_BAD_REQUEST",
                error_message_safe="Missing text or target language",
            )
        endpoint = safe_join_url(self.config.openai_base_url, self.config.chat_endpoint)
        payload = {
            "model": selected_model,
            "messages": [{"role": "user", "content": content}],
            "translation_options": {
                "source_lang": str(source_lang or "auto").strip() or "auto",
                "target_lang": str(target_lang or "").strip(),
            },
        }
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(
                    endpoint,
                    headers={**self._headers(), "Content-Type": "application/json"},
                    json=payload,
                )
            latency_ms = int((time.perf_counter() - started) * 1000)
            try:
                data = response.json()
            except Exception:
                data = {}
            translated = str((((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")).strip()
            if 200 <= response.status_code < 300 and translated:
                return _result(
                    ok=True,
                    capability="translation",
                    model=selected_model,
                    status="PASS",
                    http_status=response.status_code,
                    latency_ms=latency_ms,
                    text=translated,
                    raw_debug_admin_only={"response_shape": sorted(data.keys())[:8]},
                )
            return _result(
                ok=False,
                capability="translation",
                model=selected_model,
                status="FAIL_CONTENT_EMPTY" if response.status_code < 300 else "FAIL",
                http_status=response.status_code,
                latency_ms=latency_ms,
                error_class="FAIL_CONTENT_EMPTY" if response.status_code < 300 else _classify_http(response.status_code, data),
                error_message_safe="empty content" if response.status_code < 300 else data,
            )
        except httpx.TimeoutException as exc:
            return _timeout_result("translation", selected_model, exc)
        except Exception as exc:
            return _result(ok=False, capability="translation", model=selected_model, status="FAIL_EXCEPTION", error_class=type(exc).__name__, error_message_safe=exc)

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
        aspect_ratio: str = "16:9",
    ) -> dict[str, Any]:
        selected_model = model or self.config.video_model
        if not self.is_configured():
            return self._missing_result("video_generate", selected_model)
        endpoint = safe_join_url(self.config.base_url, self.config.video_create_endpoint)
        payload = {
            "model": selected_model,
            "prompt": str(prompt or "")[:1000],
            "aspect_ratio": str(aspect_ratio or "16:9")[:20],
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
            result = _result(ok=False, capability="video_generate", model=selected_model, status="FAIL", http_status=response.status_code, latency_ms=latency_ms, error_class=_classify_http(response.status_code, data), error_message_safe=data)
            return _add_video_unavailable_guidance(result)
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
                error_message_safe="Vui lòng dùng task_id thật do /tool_test_key4u_video trả về. Hiện chưa có task_id vì lệnh tạo video chưa submit thành công.",
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
            result = _result(ok=False, capability="video_query", model=self.config.video_model, status="FAIL", http_status=response.status_code, latency_ms=latency_ms, task_id=safe_task_id, error_class=_classify_http(response.status_code, data), error_message_safe=data)
            return _add_video_unavailable_guidance(result)
        except httpx.TimeoutException as exc:
            return _timeout_result("video_query", self.config.video_model, exc, task_id=safe_task_id)
        except Exception as exc:
            return _result(ok=False, capability="video_query", model=self.config.video_model, status="FAIL_EXCEPTION", task_id=safe_task_id, error_class=type(exc).__name__, error_message_safe=exc)

    async def tts(self, text: str = "Xin chào TOAN AAS.", model: str = "", voice_id: str = "", speed: float = 1.0, timeout_seconds: float = 30.0) -> dict[str, Any]:
        selected_model = model or self.config.tts_model
        if not self.is_configured():
            return self._missing_result("tts", selected_model)
        if not self.config.tts_endpoint or not selected_model:
            return self._needs_docs_result("tts", selected_model, "KEY4U_TTS_ENDPOINT/KEY4U_DEFAULT_TTS_MODEL")
        endpoint = self._minimax_url(self.config.tts_endpoint)
        payload = {
            "model": selected_model,
            "text": str(text or "")[:3500],
            "voice_setting": {
                "voice_id": str(voice_id or "male-qn-qingse")[:256],
                "speed": float(speed or 1.0),
                "vol": 1,
                "pitch": 0,
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "mp3",
                "channel": 1,
            },
            "language_boost": "Vietnamese",
            "stream": False,
            "subtitle_enable": False,
        }
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
                response = await client.post(endpoint, headers={**self._headers(), "Content-Type": "application/json"}, json=payload)
            latency_ms = int((time.perf_counter() - started) * 1000)
            content_type = response.headers.get("content-type", "")
            if 200 <= response.status_code < 300 and content_type.startswith("audio/") and response.content:
                return _result(ok=True, capability="tts", model=selected_model, status="PASS", http_status=response.status_code, latency_ms=latency_ms, output_bytes=response.content, final_url=endpoint)
            try:
                data = response.json()
            except Exception:
                data = {}
            body = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data
            audio_value = str((body or {}).get("audio") or (body or {}).get("audio_url") or (body or {}).get("url") or "").strip() if isinstance(body, dict) else ""
            if 200 <= response.status_code < 300 and audio_value.startswith(("http://", "https://")):
                return _result(ok=True, capability="tts", model=selected_model, status="PASS", http_status=response.status_code, latency_ms=latency_ms, output_url=audio_value, final_url=endpoint)
            if 200 <= response.status_code < 300 and audio_value:
                audio_bytes = b""
                try:
                    if re.fullmatch(r"[0-9a-fA-F]+", audio_value) and len(audio_value) % 2 == 0:
                        audio_bytes = bytes.fromhex(audio_value)
                    else:
                        audio_bytes = base64.b64decode(audio_value, validate=False)
                except Exception:
                    audio_bytes = b""
                if len(audio_bytes) > 0:
                    return _result(ok=True, capability="tts", model=selected_model, status="PASS", http_status=response.status_code, latency_ms=latency_ms, output_bytes=audio_bytes, final_url=endpoint)
            return _result(ok=False, capability="tts", model=selected_model, status="FAIL", http_status=response.status_code, latency_ms=latency_ms, final_url=endpoint, error_class=_classify_http(response.status_code, data), error_message_safe=data)
        except httpx.TimeoutException as exc:
            return _result(ok=False, capability="tts", model=selected_model, status="FAIL_TIMEOUT", final_url=endpoint, error_class="FAIL_TIMEOUT", error_message_safe=exc)
        except Exception as exc:
            return _result(ok=False, capability="tts", model=selected_model, status="FAIL_EXCEPTION", final_url=endpoint, error_class=type(exc).__name__, error_message_safe=exc)

    async def voice_tts_fallback(self, text: str = "Xin chào TOAN AAS.", voice_id: str = "", speed: float = 1.0, timeout_seconds: float = 30.0) -> dict[str, Any]:
        selected_model = self.config.tts_alt_model or "speech-2.6-hd"
        if not self.is_configured():
            return self._missing_result("voice_tts_fallback", selected_model)
        if not self.config.voice_tts_endpoint:
            return self._needs_docs_result("voice_tts_fallback", selected_model, "KEY4U_VOICE_TTS_ENDPOINT")
        endpoint = self._voice_url(self.config.voice_tts_endpoint)
        payload = {
            "model": selected_model,
            "text": str(text or "")[:3500],
            "stream": False,
            "voice_setting": {
                "voice_id": str(voice_id or "English_expressive_narrator")[:256],
                "speed": float(speed or 1.0),
                "vol": 1,
                "pitch": 0,
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "mp3",
                "channel": 1,
            },
            "language_boost": "auto",
            "output_format": "hex",
        }
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
                response = await client.post(endpoint, headers={**self._headers(), "Content-Type": "application/json"}, json=payload)
            latency_ms = int((time.perf_counter() - started) * 1000)
            try:
                data = response.json()
            except Exception:
                data = {}
            body = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data
            audio_value = str((body or {}).get("audio") or (body or {}).get("audio_url") or (body or {}).get("url") or "").strip() if isinstance(body, dict) else ""
            if 200 <= response.status_code < 300 and audio_value.startswith(("http://", "https://")):
                return _result(ok=True, capability="voice_tts_fallback", model=selected_model, status="PASS", http_status=response.status_code, latency_ms=latency_ms, output_url=audio_value)
            if 200 <= response.status_code < 300 and audio_value:
                try:
                    audio_bytes = bytes.fromhex(audio_value) if re.fullmatch(r"[0-9a-fA-F]+", audio_value) and len(audio_value) % 2 == 0 else base64.b64decode(audio_value, validate=False)
                except Exception:
                    audio_bytes = b""
                if len(audio_bytes) > 0:
                    return _result(ok=True, capability="voice_tts_fallback", model=selected_model, status="PASS", http_status=response.status_code, latency_ms=latency_ms, output_bytes=audio_bytes)
            return _result(ok=False, capability="voice_tts_fallback", model=selected_model, status="FAIL", http_status=response.status_code, latency_ms=latency_ms, error_class=_classify_http(response.status_code, data), error_message_safe=data)
        except httpx.TimeoutException as exc:
            return _result(ok=False, capability="voice_tts_fallback", model=selected_model, status="FAIL_TIMEOUT", error_class="FAIL_TIMEOUT", error_message_safe=exc)
        except Exception as exc:
            return _result(ok=False, capability="voice_tts_fallback", model=selected_model, status="FAIL_EXCEPTION", error_class=type(exc).__name__, error_message_safe=exc)

    async def tts_async(self, text: str, voice_id: str = "", model: str = "", speed: float = 1.0, timeout_seconds: float = 30.0) -> dict[str, Any]:
        selected_model = model or self.config.tts_model
        if not self.is_configured():
            return self._missing_result("tts_async", selected_model)
        if not self.config.tts_async_endpoint or not selected_model:
            return self._needs_docs_result("tts_async", selected_model, "KEY4U_MINIMAX_TTS_ASYNC_ENDPOINT/KEY4U_DEFAULT_TTS_MODEL")
        endpoint = self._minimax_url(self.config.tts_async_endpoint)
        payload = {
            "model": selected_model,
            "text": str(text or "")[:10000],
            "voice_setting": {
                "voice_id": str(voice_id or "male-qn-qingse")[:256],
                "speed": float(speed or 1.0),
                "vol": 1,
                "pitch": 0,
            },
        }
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
                response = await client.post(endpoint, headers={**self._headers(), "Content-Type": "application/json"}, json=payload)
            latency_ms = int((time.perf_counter() - started) * 1000)
            try:
                data = response.json()
            except Exception:
                data = {}
            body = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data
            task_id = str((body or {}).get("task_id") or (body or {}).get("taskId") or data.get("task_id") or "").strip() if isinstance(data, dict) else ""
            file_id = str((body or {}).get("file_id") or data.get("file_id") or "").strip() if isinstance(data, dict) else ""
            task_token = str((body or {}).get("task_token") or data.get("task_token") or "").strip() if isinstance(data, dict) else ""
            ok = bool(200 <= response.status_code < 300 and task_id)
            result = _result(ok=ok, capability="tts_async", model=selected_model, status="PASS_SUBMITTED" if ok else "FAIL", http_status=response.status_code, latency_ms=latency_ms, task_id=task_id, final_url=endpoint, error_class="" if ok else _classify_http(response.status_code, data), error_message_safe="" if ok else data)
            result["file_id"] = file_id
            result["task_token"] = task_token
            return result
        except httpx.TimeoutException as exc:
            return _result(ok=False, capability="tts_async", model=selected_model, status="FAIL_TIMEOUT", final_url=endpoint, error_class="FAIL_TIMEOUT", error_message_safe=exc)
        except Exception as exc:
            return _result(ok=False, capability="tts_async", model=selected_model, status="FAIL_EXCEPTION", final_url=endpoint, error_class=type(exc).__name__, error_message_safe=exc)

    async def query_tts_task(self, task_id: str, timeout_seconds: float = 30.0) -> dict[str, Any]:
        selected_model = self.config.tts_model
        safe_task_id = str(task_id or "").strip()
        if not self.is_configured():
            return self._missing_result("tts_query", selected_model)
        if not self.config.tts_query_endpoint:
            return self._needs_docs_result("tts_query", selected_model, "KEY4U_MINIMAX_TTS_QUERY_ENDPOINT")
        if not safe_task_id:
            return _result(ok=False, capability="tts_query", model=selected_model, status="NEED_TASK_ID", error_class="NEED_TASK_ID", error_message_safe="Missing task_id")
        endpoint = self._minimax_url(self.config.tts_query_endpoint)
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
                response = await client.get(endpoint, headers=self._headers(), params={"task_id": safe_task_id})
            latency_ms = int((time.perf_counter() - started) * 1000)
            try:
                data = response.json()
            except Exception:
                data = {}
            body = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data
            status = str((body or {}).get("status") or data.get("status") or "").strip() if isinstance(data, dict) else ""
            file_id = str((body or {}).get("file_id") or data.get("file_id") or "").strip() if isinstance(data, dict) else ""
            ok = bool(200 <= response.status_code < 300 and status.lower() in {"success", "succeeded", "completed"} and file_id)
            result = _result(ok=ok, capability="tts_query", model=selected_model, status="SUCCESS" if ok else (status or "PROCESSING"), http_status=response.status_code, latency_ms=latency_ms, task_id=safe_task_id, final_url=endpoint, error_class="" if response.status_code < 400 else _classify_http(response.status_code, data), error_message_safe="" if response.status_code < 400 else data)
            result["file_id"] = file_id
            return result
        except httpx.TimeoutException as exc:
            return _result(ok=False, capability="tts_query", model=selected_model, status="FAIL_TIMEOUT", task_id=safe_task_id, final_url=endpoint, error_class="FAIL_TIMEOUT", error_message_safe=exc)
        except Exception as exc:
            return _result(ok=False, capability="tts_query", model=selected_model, status="FAIL_EXCEPTION", task_id=safe_task_id, final_url=endpoint, error_class=type(exc).__name__, error_message_safe=exc)

    async def retrieve_file(self, file_id: str, timeout_seconds: float = 30.0) -> dict[str, Any]:
        safe_file_id = str(file_id or "").strip()
        if not self.is_configured():
            return self._missing_result("file_retrieve", self.config.tts_model)
        if not self.config.tts_retrieve_endpoint:
            return self._needs_docs_result("file_retrieve", self.config.tts_model, "KEY4U_MINIMAX_TTS_RETRIEVE_ENDPOINT")
        if not safe_file_id:
            return _result(ok=False, capability="file_retrieve", model=self.config.tts_model, status="NEED_FILE_ID", error_class="NEED_FILE_ID", error_message_safe="Missing file_id")
        endpoint = self._minimax_url(self.config.tts_retrieve_endpoint)
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
                response = await client.get(endpoint, headers=self._headers(), params={"file_id": safe_file_id})
            latency_ms = int((time.perf_counter() - started) * 1000)
            try:
                data = response.json()
            except Exception:
                data = {}
            file_obj = data.get("file") if isinstance(data, dict) and isinstance(data.get("file"), dict) else {}
            download_url = str((file_obj or {}).get("download_url") or (data or {}).get("download_url") or "").strip() if isinstance(data, dict) else ""
            return _result(ok=bool(200 <= response.status_code < 300 and download_url), capability="file_retrieve", model=self.config.tts_model, status="PASS" if download_url else "FAIL", http_status=response.status_code, latency_ms=latency_ms, output_url=download_url, final_url=endpoint, error_class="" if download_url else _classify_http(response.status_code, data), error_message_safe="" if download_url else data)
        except httpx.TimeoutException as exc:
            return _result(ok=False, capability="file_retrieve", model=self.config.tts_model, status="FAIL_TIMEOUT", final_url=endpoint, error_class="FAIL_TIMEOUT", error_message_safe=exc)
        except Exception as exc:
            return _result(ok=False, capability="file_retrieve", model=self.config.tts_model, status="FAIL_EXCEPTION", final_url=endpoint, error_class=type(exc).__name__, error_message_safe=exc)

    async def upload_voice_sample(
        self,
        audio_bytes: bytes,
        filename: str = "voice-sample.mp3",
        content_type: str = "audio/mpeg",
        timeout_seconds: float = 60.0,
    ) -> dict[str, Any]:
        if not self.is_configured():
            return self._missing_result("voice_upload", self.config.tts_model)
        if not self.config.minimax_upload_endpoint:
            return self._needs_docs_result("voice_upload", self.config.tts_model, "KEY4U_MINIMAX_UPLOAD_ENDPOINT")
        if not audio_bytes:
            return _result(ok=False, capability="voice_upload", status="NEED_AUDIO_INPUT", error_class="NEED_AUDIO_INPUT", error_message_safe="missing audio sample")
        endpoint = self._minimax_url(self.config.minimax_upload_endpoint)
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(filename or "voice-sample.mp3"))[:80]
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
                response = await client.post(
                    endpoint,
                    headers=self._headers(),
                    data={"purpose": "prompt_audio"},
                    files={"file": (safe_name, audio_bytes, str(content_type or "audio/mpeg"))},
                )
            latency_ms = int((time.perf_counter() - started) * 1000)
            try:
                payload = response.json()
            except Exception:
                payload = {}
            file_obj = payload.get("file") if isinstance(payload, dict) and isinstance(payload.get("file"), dict) else {}
            file_id = str((file_obj or {}).get("file_id") or (payload or {}).get("file_id") or "").strip() if isinstance(payload, dict) else ""
            result = _result(
                ok=bool(200 <= response.status_code < 300 and file_id),
                capability="voice_upload",
                model=self.config.tts_model,
                status="PASS" if file_id else "FAIL",
                http_status=response.status_code,
                latency_ms=latency_ms,
                final_url=endpoint,
                error_class="" if file_id else _classify_http(response.status_code, payload),
                error_message_safe="" if file_id else payload,
            )
            result["file_id"] = file_id
            return result
        except httpx.TimeoutException as exc:
            return _result(ok=False, capability="voice_upload", model=self.config.tts_model, status="FAIL_TIMEOUT", final_url=endpoint, error_class="FAIL_TIMEOUT", error_message_safe=exc)
        except Exception as exc:
            return _result(ok=False, capability="voice_upload", model=self.config.tts_model, status="FAIL_EXCEPTION", final_url=endpoint, error_class=type(exc).__name__, error_message_safe=exc)

    async def clone_voice(
        self,
        file_id: str,
        voice_id: str,
        prompt_text: str,
        timeout_seconds: float = 60.0,
    ) -> dict[str, Any]:
        if not self.is_configured():
            return self._missing_result("voice_clone", self.config.tts_model)
        if not self.config.minimax_clone_endpoint:
            return self._needs_docs_result("voice_clone", self.config.tts_model, "KEY4U_MINIMAX_CLONE_ENDPOINT")
        safe_file_id = str(file_id or "").strip()
        safe_voice_id = re.sub(r"[^A-Za-z0-9-]+", "-", str(voice_id or "").strip())[:128].strip("-")
        if not safe_file_id or not safe_voice_id:
            return _result(ok=False, capability="voice_clone", model=self.config.tts_model, status="FAIL_BAD_REQUEST", error_class="FAIL_BAD_REQUEST", error_message_safe="missing file_id or voice_id")
        endpoint = self._minimax_url(self.config.minimax_clone_endpoint)
        payload = {
            "file_id": int(safe_file_id) if safe_file_id.isdigit() else safe_file_id,
            "voice_id": safe_voice_id,
            "clone_prompt": {
                "prompt_audio": int(safe_file_id) if safe_file_id.isdigit() else safe_file_id,
                "prompt_text": str(prompt_text or "")[:500],
            },
            "text": str(prompt_text or "")[:500],
            "model": self.config.clone_model or "speech-2.8-hd",
            "language_boost": "Vietnamese",
            "need_noise_reduction": True,
            "need_volume_normalization": True,
            "aigc_watermark": False,
        }
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
                response = await client.post(endpoint, headers={**self._headers(), "Content-Type": "application/json"}, json=payload)
            latency_ms = int((time.perf_counter() - started) * 1000)
            try:
                data = response.json()
            except Exception:
                data = {}
            base_resp = data.get("base_resp") if isinstance(data, dict) and isinstance(data.get("base_resp"), dict) else {}
            provider_code = str((base_resp or {}).get("status_code") or "0")
            ok = bool(200 <= response.status_code < 300 and provider_code in {"0", "1", ""})
            demo_audio = str((data or {}).get("demo_audio") or (data or {}).get("trial_audio") or "") if isinstance(data, dict) else ""
            result = _result(
                ok=ok,
                capability="voice_clone",
                model=self.config.clone_model or self.config.tts_model,
                status="PASS" if ok else "FAIL",
                http_status=response.status_code,
                latency_ms=latency_ms,
                output_url=demo_audio if demo_audio.startswith(("http://", "https://")) else "",
                final_url=endpoint,
                error_class="" if ok else _classify_http(response.status_code, data),
                error_message_safe="" if ok else data,
            )
            result["voice_id"] = safe_voice_id if ok else ""
            result["demo_audio"] = demo_audio
            return result
        except httpx.TimeoutException as exc:
            return _result(ok=False, capability="voice_clone", model=self.config.clone_model or self.config.tts_model, status="FAIL_TIMEOUT", final_url=endpoint, error_class="FAIL_TIMEOUT", error_message_safe=exc)
        except Exception as exc:
            return _result(ok=False, capability="voice_clone", model=self.config.clone_model or self.config.tts_model, status="FAIL_EXCEPTION", final_url=endpoint, error_class=type(exc).__name__, error_message_safe=exc)

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

    async def suno_create(
        self,
        prompt: str = "Short upbeat TOAN AAS intro.",
        model: str = "",
        timeout_seconds: float = 30.0,
        duration_seconds: int = 30,
        instrumental: bool = True,
        title: str = "TOAN AAS Music",
        lyrics: str = "",
        tags: str = "",
    ) -> dict[str, Any]:
        selected_model = model or self.config.suno_model
        if not self.is_configured():
            return self._missing_result("suno", selected_model)
        if not self.config.suno_create_endpoint or not selected_model:
            return self._needs_docs_result("suno", selected_model, "KEY4U_SUNO_CREATE_ENDPOINT/KEY4U_DEFAULT_MUSIC_MODEL")
        endpoint = self._suno_url(self.config.suno_create_endpoint)
        lyrics_text = str(lyrics or "").strip()
        payload = {
            "mv": selected_model,
            "make_instrumental": bool(instrumental),
            "title": str(title or "TOAN AAS Music")[:120],
            "tags": str(tags or ("instrumental" if instrumental else "vocal, original"))[:240],
        }
        if lyrics_text:
            payload["prompt"] = lyrics_text[:4000]
        else:
            payload["gpt_description_prompt"] = str(prompt or "")[:1200]
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(endpoint, headers={**self._headers(), "Content-Type": "application/json"}, json=payload)
            latency_ms = int((time.perf_counter() - started) * 1000)
            try:
                data = response.json()
            except Exception:
                data = {}
            data_value = data.get("data") if isinstance(data, dict) else ""
            if isinstance(data_value, str):
                task_id = data_value.strip()
            else:
                body = data_value if isinstance(data_value, dict) else data
                task_id = str((body or {}).get("task_id") or (body or {}).get("taskId") or (body or {}).get("id") or data.get("task_id") or "")
            if 200 <= response.status_code < 300 and task_id:
                return _result(ok=True, capability="suno", model=selected_model, status="PASS_SUBMITTED", http_status=response.status_code, latency_ms=latency_ms, task_id=task_id, final_url=endpoint)
            return _result(ok=False, capability="suno", model=selected_model, status="FAIL", http_status=response.status_code, latency_ms=latency_ms, final_url=endpoint, error_class=_classify_http(response.status_code, data), error_message_safe=data)
        except httpx.TimeoutException as exc:
            return _result(ok=False, capability="suno", model=selected_model, status="FAIL_TIMEOUT", final_url=endpoint, error_class="FAIL_TIMEOUT", error_message_safe=exc)
        except Exception as exc:
            return _result(ok=False, capability="suno", model=selected_model, status="FAIL_EXCEPTION", final_url=endpoint, error_class=type(exc).__name__, error_message_safe=exc)

    async def suno_query(self, task_id: str, timeout_seconds: float = 30.0) -> dict[str, Any]:
        selected_model = self.config.suno_model
        if not self.is_configured():
            return self._missing_result("suno_query", selected_model)
        if not self.config.suno_query_endpoint:
            return self._needs_docs_result("suno_query", selected_model, "KEY4U_SUNO_QUERY_ENDPOINT")
        safe_task_id = str(task_id or "").strip()
        if not safe_task_id:
            return _result(ok=False, capability="suno_query", model=selected_model, status="NEED_TASK_ID", error_class="NEED_TASK_ID", error_message_safe="Missing task_id")
        endpoint_path = str(self.config.suno_query_endpoint or "")
        if "{taskId}" in endpoint_path:
            endpoint_path = endpoint_path.replace("{taskId}", safe_task_id)
        elif "{task_id}" in endpoint_path:
            endpoint_path = endpoint_path.replace("{task_id}", safe_task_id)
        else:
            endpoint_path = endpoint_path.rstrip("/") + "/" + safe_task_id
        endpoint = self._suno_url(endpoint_path)
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.get(endpoint, headers=self._headers())
            latency_ms = int((time.perf_counter() - started) * 1000)
            try:
                data = response.json()
            except Exception:
                data = {}
            audio_urls = _suno_audio_urls_from_payload(data)
            output_url = audio_urls[0] if audio_urls else ""
            status = _suno_first_string_for_keys(data, SUNO_STATUS_KEYS)
            fail_reason = _suno_first_string_for_keys(data, SUNO_FAILURE_KEYS)
            output_id = _suno_first_string_for_keys(data, SUNO_ID_KEYS)
            lyrics_text = _suno_first_string_for_keys(data, SUNO_TEXT_KEYS)
            parsed_fields = _suno_payload_field_presence(data)
            normalized_status = _normalize_suno_query_status(
                status,
                has_audio=bool(output_url),
                http_status=int(response.status_code or 0),
            )
            ok = bool(200 <= response.status_code < 300 and output_url)
            result = _result(
                ok=ok,
                capability="suno_query",
                model=selected_model,
                status=normalized_status,
                http_status=response.status_code,
                latency_ms=latency_ms,
                task_id=safe_task_id,
                output_url=output_url,
                final_url=endpoint,
                error_class="" if ok else _classify_http(response.status_code, fail_reason or normalized_status),
                error_message_safe=fail_reason,
                raw_debug_admin_only={
                    "parsed_fields": parsed_fields,
                    "audio_url_count": len(audio_urls),
                    "response_shape": sorted(data.keys())[:12] if isinstance(data, dict) else [],
                },
            )
            result["raw_provider_result"] = data if isinstance(data, dict) else {}
            result["audio_url_candidates"] = list(audio_urls)
            result["clip_id"] = output_id
            result["text"] = lyrics_text
            result["parsed_fields"] = parsed_fields
            return result
        except httpx.TimeoutException as exc:
            return _result(ok=False, capability="suno_query", model=selected_model, status="FAIL_TIMEOUT", task_id=safe_task_id, final_url=endpoint, error_class="FAIL_TIMEOUT", error_message_safe=exc)
        except Exception as exc:
            return _result(ok=False, capability="suno_query", model=selected_model, status="FAIL_EXCEPTION", task_id=safe_task_id, final_url=endpoint, error_class=type(exc).__name__, error_message_safe=exc)

    async def suno_lyrics(self, prompt: str, title: str = "TOAN AAS Lyrics", tags: str = "", timeout_seconds: float = 30.0) -> dict[str, Any]:
        selected_model = self.config.suno_model
        if not self.is_configured():
            return self._missing_result("suno_lyrics", selected_model)
        if not self.config.suno_lyrics_endpoint:
            return self._needs_docs_result("suno_lyrics", selected_model, "KEY4U_SUNO_LYRICS_ENDPOINT")
        endpoint = self._suno_url(self.config.suno_lyrics_endpoint)
        payload = {
            "prompt": str(prompt or "")[:1200],
            "title": str(title or "TOAN AAS Lyrics")[:120],
            "tags": str(tags or "pop, vietnamese")[:240],
        }
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
                response = await client.post(endpoint, headers={**self._headers(), "Content-Type": "application/json"}, json=payload)
            latency_ms = int((time.perf_counter() - started) * 1000)
            try:
                data = response.json()
            except Exception:
                data = {}
            data_value = data.get("data") if isinstance(data, dict) else ""
            task_id = data_value.strip() if isinstance(data_value, str) else str((data_value or {}).get("task_id") or (data_value or {}).get("taskId") or "")
            ok = bool(200 <= response.status_code < 300 and task_id)
            return _result(ok=ok, capability="suno_lyrics", model=selected_model, status="PASS_SUBMITTED" if ok else "FAIL", http_status=response.status_code, latency_ms=latency_ms, task_id=task_id, final_url=endpoint, error_class="" if ok else _classify_http(response.status_code, data), error_message_safe="" if ok else data)
        except httpx.TimeoutException as exc:
            return _result(ok=False, capability="suno_lyrics", model=selected_model, status="FAIL_TIMEOUT", final_url=endpoint, error_class="FAIL_TIMEOUT", error_message_safe=exc)
        except Exception as exc:
            return _result(ok=False, capability="suno_lyrics", model=selected_model, status="FAIL_EXCEPTION", final_url=endpoint, error_class=type(exc).__name__, error_message_safe=exc)

    async def suno_wav(self, clip_id: str, timeout_seconds: float = 30.0) -> dict[str, Any]:
        selected_model = self.config.suno_model
        safe_clip_id = str(clip_id or "").strip()
        if not self.is_configured():
            return self._missing_result("suno_wav", selected_model)
        if not self.config.suno_wav_endpoint:
            return self._needs_docs_result("suno_wav", selected_model, "KEY4U_SUNO_WAV_ENDPOINT")
        if not safe_clip_id:
            return _result(ok=False, capability="suno_wav", model=selected_model, status="NEED_CLIP_ID", error_class="NEED_CLIP_ID", error_message_safe="Missing clip_id")
        endpoint = self._suno_url(self._path_with_id(self.config.suno_wav_endpoint, safe_clip_id, "clipId", "clip_id"))
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
                response = await client.get(endpoint, headers=self._headers())
            latency_ms = int((time.perf_counter() - started) * 1000)
            content_type = response.headers.get("content-type", "")
            if 200 <= response.status_code < 300 and content_type.startswith("audio/") and response.content:
                return _result(ok=True, capability="suno_wav", model=selected_model, status="PASS", http_status=response.status_code, latency_ms=latency_ms, output_bytes=response.content, final_url=endpoint)
            try:
                data = response.json()
            except Exception:
                data = {}
            body = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data
            output_url = str((body or {}).get("url") or (body or {}).get("download_url") or (body or {}).get("audio_url") or "").strip() if isinstance(body, dict) else ""
            return _result(ok=bool(200 <= response.status_code < 300 and output_url), capability="suno_wav", model=selected_model, status="PASS" if output_url else "FAIL", http_status=response.status_code, latency_ms=latency_ms, output_url=output_url, final_url=endpoint, error_class="" if output_url else _classify_http(response.status_code, data), error_message_safe="" if output_url else data)
        except httpx.TimeoutException as exc:
            return _result(ok=False, capability="suno_wav", model=selected_model, status="FAIL_TIMEOUT", final_url=endpoint, error_class="FAIL_TIMEOUT", error_message_safe=exc)
        except Exception as exc:
            return _result(ok=False, capability="suno_wav", model=selected_model, status="FAIL_EXCEPTION", final_url=endpoint, error_class=type(exc).__name__, error_message_safe=exc)

    async def suno_timing(self, clip_id: str, timeout_seconds: float = 30.0) -> dict[str, Any]:
        selected_model = self.config.suno_model
        safe_clip_id = str(clip_id or "").strip()
        if not self.is_configured():
            return self._missing_result("suno_timing", selected_model)
        if not self.config.suno_timing_endpoint:
            return self._needs_docs_result("suno_timing", selected_model, "KEY4U_SUNO_TIMING_ENDPOINT")
        if not safe_clip_id:
            return _result(ok=False, capability="suno_timing", model=selected_model, status="NEED_CLIP_ID", error_class="NEED_CLIP_ID", error_message_safe="Missing clip_id")
        endpoint = self._suno_url(self._path_with_id(self.config.suno_timing_endpoint, safe_clip_id, "clipId", "clip_id"))
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
                response = await client.get(endpoint, headers=self._headers())
            latency_ms = int((time.perf_counter() - started) * 1000)
            try:
                data = response.json()
            except Exception:
                data = {}
            ok = bool(200 <= response.status_code < 300 and data)
            result = _result(ok=ok, capability="suno_timing", model=selected_model, status="PASS" if ok else "FAIL", http_status=response.status_code, latency_ms=latency_ms, final_url=endpoint, error_class="" if ok else _classify_http(response.status_code, data), error_message_safe="" if ok else data, raw_debug_admin_only={"keys": sorted(data.keys())[:8] if isinstance(data, dict) else []})
            result["data"] = data if ok else {}
            return result
        except httpx.TimeoutException as exc:
            return _result(ok=False, capability="suno_timing", model=selected_model, status="FAIL_TIMEOUT", final_url=endpoint, error_class="FAIL_TIMEOUT", error_message_safe=exc)
        except Exception as exc:
            return _result(ok=False, capability="suno_timing", model=selected_model, status="FAIL_EXCEPTION", final_url=endpoint, error_class=type(exc).__name__, error_message_safe=exc)

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
