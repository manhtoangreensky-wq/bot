from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable


KEY4U_API_ROOT = "https://api.key4u.shop"
SHOPAIKEY_API_ROOT = "https://api.shopaikey.com"
MINIMAX_VOICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$")


@dataclass(frozen=True)
class ProviderCapability:
    provider_name: str
    capability: str
    base_url: str
    endpoint: str
    model: str
    request_mode: str
    response_mode: str
    voice_source: str = ""
    configured: bool = False
    smoke_status: str = "NOT_TESTED"

    @property
    def final_url(self) -> str:
        return join_url(self.base_url, self.endpoint)


def join_url(base_url: str, endpoint: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    path = str(endpoint or "").strip()
    if not path:
        return base
    if path.startswith(("http://", "https://")):
        return path.rstrip("/")
    match = re.match(r"^(https?://[^/]+)(/.*)?$", base)
    if not match:
        return "/".join([base.rstrip("/"), path.lstrip("/")]).rstrip("/")
    root = match.group(1)
    base_parts = [part for part in (match.group(2) or "").strip("/").split("/") if part]
    path_parts = [part for part in path.strip("/").split("/") if part]
    overlap = 0
    for size in range(min(len(base_parts), len(path_parts)), 0, -1):
        if base_parts[-size:] == path_parts[:size]:
            overlap = size
            break
    parts = [*base_parts, *path_parts[overlap:]]
    return root + ("/" + "/".join(parts) if parts else "")


def normalize_minimax_voice_id(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    normalized = re.sub(r"\s+", "-", raw)
    normalized = re.sub(r"[^A-Za-z0-9._-]", "", normalized)
    return normalized[:128]


def is_valid_minimax_voice_id(value: str | None) -> bool:
    normalized = normalize_minimax_voice_id(value)
    if not normalized:
        return False
    return bool(MINIMAX_VOICE_ID_PATTERN.fullmatch(normalized))


def _capability(
    provider_name: str,
    capability: str,
    base_url: str,
    endpoint: str,
    model: str,
    request_mode: str,
    response_mode: str,
    voice_source: str = "",
) -> ProviderCapability:
    return ProviderCapability(
        provider_name=provider_name,
        capability=capability,
        base_url=base_url,
        endpoint=endpoint,
        model=model,
        request_mode=request_mode,
        response_mode=response_mode,
        voice_source=voice_source,
    )


def key4u_asr(model: str) -> ProviderCapability:
    return _capability("key4u", "asr", f"{KEY4U_API_ROOT}/v1", "/audio/transcriptions", model, "multipart", "transcript")


def key4u_openai_tts(model: str) -> ProviderCapability:
    return _capability("key4u", "tts", f"{KEY4U_API_ROOT}/v1", "/audio/speech", model, "json", "binary_audio", "openai_voice_set")


def key4u_minimax_tts(model: str) -> ProviderCapability:
    return _capability("key4u_minimax", "tts", f"{KEY4U_API_ROOT}/minimax/v1", "/t2a_v2", model, "json", "hex_audio_or_url", "provider_voice_id")


def key4u_minimax_async(model: str) -> ProviderCapability:
    return _capability("key4u_minimax", "tts", f"{KEY4U_API_ROOT}/minimax/v1", "/t2a_async_v2", model, "json", "async_task", "provider_voice_id")


def key4u_minimax_query(model: str) -> ProviderCapability:
    return _capability("key4u_minimax", "tts_query", f"{KEY4U_API_ROOT}/minimax/v1", "/query/t2a_async_query_v2", model, "query", "async_task", "")


def key4u_minimax_retrieve(model: str) -> ProviderCapability:
    return _capability("key4u_minimax", "tts_retrieve", f"{KEY4U_API_ROOT}/minimax/v1", "/files/retrieve", model, "query", "json_url", "")


def shopaikey_asr(model: str) -> ProviderCapability:
    return _capability("shopaikey", "asr", f"{SHOPAIKEY_API_ROOT}/v1", "/audio/transcriptions", model, "multipart", "transcript")


def shopaikey_openai_tts(model: str) -> ProviderCapability:
    return _capability("shopaikey_openai", "tts", f"{SHOPAIKEY_API_ROOT}/v1", "/audio/speech", model, "json", "binary_audio", "openai_voice_set")


def shopaikey_openai_custom_tts(model: str) -> ProviderCapability:
    return _capability("shopaikey_openai_custom", "tts", SHOPAIKEY_API_ROOT, "/tts/openai/speech", model, "json", "json_url", "openai_voice_set")


def shopaikey_minimax_tts(model: str) -> ProviderCapability:
    return _capability("shopaikey_minimax", "tts", SHOPAIKEY_API_ROOT, "/tts/minimax/t2a_v2", model, "json", "hex_audio_or_url", "shopaikey_minimax_catalog")


def shopaikey_minimax_async(model: str) -> ProviderCapability:
    return _capability("shopaikey_minimax", "tts", SHOPAIKEY_API_ROOT, "/tts/minimax/t2a_async_v2", model, "json", "async_task", "shopaikey_minimax_catalog")


def shopaikey_minimax_query(model: str) -> ProviderCapability:
    return _capability("shopaikey_minimax", "tts_query", SHOPAIKEY_API_ROOT, "/tts/minimax/query/t2a_async_query_v2", model, "query", "async_task")


def shopaikey_minimax_retrieve(model: str) -> ProviderCapability:
    return _capability("shopaikey_minimax", "tts_retrieve", SHOPAIKEY_API_ROOT, "/tts/minimax/files/retrieve", model, "query", "json_url")


def normalize_subdub_provider_name(value: str | None, *, capability: str) -> str:
    provider = str(value or "").strip().lower()
    if capability == "asr":
        return {"shopai": "shopaikey", "key4u_asr": "key4u"}.get(provider, provider)
    if capability == "tts":
        return {
            "key4u": "key4u_minimax",
            "shopai": "shopaikey_minimax",
            "shopaikey": "shopaikey_minimax",
        }.get(provider, provider)
    return provider


def parse_shopaikey_minimax_voice_catalog(payload: Any) -> tuple[str, ...]:
    rows = payload.get("voices") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return ()
    voices: list[str] = []
    for row in rows:
        voice_id = normalize_minimax_voice_id((row or {}).get("voice_id")) if isinstance(row, dict) else ""
        if voice_id and is_valid_minimax_voice_id(voice_id) and voice_id not in voices:
            voices.append(voice_id)
    return tuple(voices)


def load_shopaikey_minimax_voice_catalog(fetcher: Callable[[], Any]) -> tuple[str, ...]:
    return parse_shopaikey_minimax_voice_catalog(fetcher())


def _voice_gender_hint(value: str) -> str:
    lowered = str(value or "").lower()
    if any(marker in lowered for marker in ("female", "woman", "girl", "shaonv", "nu")):
        return "female"
    if any(marker in lowered for marker in ("male", "man", "qingse", "nam")):
        return "male"
    return ""


def resolve_shopaikey_minimax_voice_id(
    *,
    requested_voice_id: str | None,
    configured_default_voice: str | None,
    configured_female_voice: str | None,
    configured_male_voice: str | None,
    generic_legacy_voice_ids: set[str] | tuple[str, ...] | list[str],
) -> str:
    requested = normalize_minimax_voice_id(requested_voice_id)
    generic = {
        normalize_minimax_voice_id(item).lower()
        for item in generic_legacy_voice_ids
        if normalize_minimax_voice_id(item)
    }
    if requested and requested.lower() not in generic:
        return requested
    gender = _voice_gender_hint(requested)
    candidates = (
        (configured_female_voice, configured_default_voice, configured_male_voice)
        if gender == "female"
        else (configured_male_voice, configured_default_voice, configured_female_voice)
        if gender == "male"
        else (configured_default_voice, configured_female_voice, configured_male_voice)
    )
    for candidate in candidates:
        normalized = normalize_minimax_voice_id(candidate)
        if is_valid_minimax_voice_id(normalized):
            return normalized
    return ""
