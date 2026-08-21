"""Deterministic, secret-free fingerprints for V2 artifacts and claims."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any


_SECRET_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "bot_token",
    "password",
    "secret",
    "token",
    "webhook_secret",
}
_ADMIN_ONLY_KEYS = {
    "admin_provider_metadata",
    "admin_provenance_ref",
    "provider_task_id",
    "provider_task_ids",
    "signed_url",
}
_DERIVED_KEYS = {"artifact_id", "output_fingerprint", "lineage_fingerprint"}


def _sensitive_key(key: str) -> bool:
    normalized = str(key or "").strip().lower().replace("-", "_")
    if normalized in _SECRET_KEYS or normalized in _ADMIN_ONLY_KEYS:
        return True
    markers = (
        "api_key",
        "apikey",
        "authorization",
        "bearer",
        "password",
        "secret",
        "signed_url",
        "provider_task_id",
        "admin_provider",
    )
    return "token" in normalized or any(marker in normalized for marker in markers)


def _safe_value(value: Any, *, key: str = "") -> Any:
    normalized_key = str(key or "").strip().lower()
    if _sensitive_key(normalized_key):
        return "<redacted>"
    if dataclasses.is_dataclass(value):
        value = dataclasses.asdict(value)
    if isinstance(value, bytes):
        return {"__bytes_sha256__": hashlib.sha256(value).hexdigest(), "length": len(value)}
    if isinstance(value, dict):
        return {
            str(item_key): _safe_value(item_value, key=str(item_key))
            for item_key, item_value in sorted(value.items(), key=lambda item: str(item[0]))
            if str(item_key).strip().lower() not in _DERIVED_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def canonical_json(value: Any) -> str:
    return json.dumps(_safe_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_hex(value: Any) -> str:
    if isinstance(value, bytes):
        data = value
    else:
        data = canonical_json(value).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def short_id(prefix: str, value: Any, length: int = 12) -> str:
    return f"{str(prefix).strip()}-{sha256_hex(value)[:max(4, int(length))]}"


def source_fingerprint(source_id: str, media: dict[str, Any]) -> str:
    media_identity = dict(media or {})
    media_identity.pop("path", None)
    media_identity.pop("bytes", None)
    return sha256_hex({"source_id": str(source_id), "media": media_identity})


def artifact_fingerprint(artifact: dict[str, Any]) -> str:
    return sha256_hex(artifact)


def config_fingerprint(config: dict[str, Any] | None = None) -> str:
    return sha256_hex(config or {})
