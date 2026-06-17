"""Central provider router metadata for TOAN AAS.

This V1 router is deliberately conservative: ShopAIKey remains primary, Key4U
is a configured backup candidate, and WokuShop is parked due higher cost.
"""

from __future__ import annotations

import os
from typing import Any


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return default if value is None else str(value)


def _flag(name: str, default: str = "false") -> bool:
    return str(_env(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def provider_router_enabled() -> bool:
    return _flag("PROVIDER_ROUTER_ENABLED", "true")


def provider_fallback_enabled() -> bool:
    return _flag("PROVIDER_FALLBACK_ENABLED", "false")


def provider_fallback_order() -> list[str]:
    raw = _env("PROVIDER_FALLBACK_ORDER", "shopaikey,key4u")
    result: list[str] = []
    seen: set[str] = set()
    for item in raw.split(","):
        key = item.strip().lower()
        if not key or key in seen or key in {"woku", "wokushop"}:
            continue
        seen.add(key)
        result.append(key)
    if "shopaikey" not in seen:
        result.insert(0, "shopaikey")
    if "key4u" not in seen:
        result.append("key4u")
    return result


def woku_status() -> dict[str, Any]:
    return {
        "provider": "wokushop",
        "label": "WokuShop",
        "enabled": _flag("WOKU_ENABLED", _env("WOKUSHOP_ENABLED", "false")),
        "public_enabled": _flag("WOKU_PUBLIC_ENABLED", _env("WOKUSHOP_PUBLIC_ENABLED", "false")),
        "admin_smoke_enabled": _flag("WOKU_ADMIN_SMOKE_ENABLED", _env("WOKUSHOP_ADMIN_SMOKE_ENABLED", "false")),
        "stage": "disabled",
        "reason": _env("WOKU_REASON", _env("WOKUSHOP_REASON", "cost_high_parked")),
        "configured": False,
        "capabilities": [],
        "fallback": [],
    }


def provider_matrix_payload(
    *,
    shopaikey: dict[str, Any] | None = None,
    key4u: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "router_enabled": provider_router_enabled(),
        "fallback_enabled": provider_fallback_enabled(),
        "fallback_order": provider_fallback_order(),
        "providers": {
            "shopaikey": shopaikey or {"role": "primary"},
            "key4u": key4u or {"role": "backup", "public_enabled": False},
            "wokushop": woku_status(),
        },
    }
