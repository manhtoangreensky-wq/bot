"""Shared provider-result helpers for TOAN AAS provider adapters.

This module keeps a small common shape for provider results without importing
bot runtime state. User-facing code must hide ``raw_admin`` from public users.
"""

from __future__ import annotations

from typing import Any


def provider_result(
    *,
    ok: bool,
    provider: str,
    capability: str,
    model: str = "",
    status: str = "",
    task_id: str = "",
    output_url: str = "",
    output_bytes: bytes | None = None,
    text: str = "",
    images: list[str] | None = None,
    videos: list[str] | None = None,
    audio: list[str] | None = None,
    raw_admin: dict[str, Any] | None = None,
    error_class: str = "",
    error_message_safe: str = "",
    cost_estimate: Any = None,
) -> dict[str, Any]:
    return {
        "ok": bool(ok),
        "provider": provider,
        "capability": capability,
        "model": model,
        "status": status or ("SUCCESS" if ok else "FAIL"),
        "task_id": task_id,
        "output_url": output_url,
        "output_bytes": output_bytes or b"",
        "text": text,
        "images": images or [],
        "videos": videos or [],
        "audio": audio or [],
        "raw_admin": raw_admin or {},
        "error_class": error_class,
        "error_message_safe": error_message_safe,
        "cost_estimate": cost_estimate,
    }
