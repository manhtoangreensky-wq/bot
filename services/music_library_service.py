"""Canonical Music Library Service for TOAN AAS Ecosystem (R40).

Governed by: owner-governed-codex, locked-focus-engineering, single-agent-anti-overengineering.
SPEC_ID: BOT-CANONICAL-MUSIC-LIBRARY-JAMENDO-R1

Provides server-authority Jamendo public music library search, selection, and preview parity:
- Search: /music_library <query> -> fetch_jamendo_tracks(query, limit=8)
- Select: /select_music <number> -> select_media_preview("music", ...)
- Preview: 1-based index playback with safe domain validation and zero secret leakage
- Selection State: stored in Bot authority SELECTED_MUSIC[actor_id]
- Pricing Parity: 0 Xu immediate intake charge ("Bot chưa trừ Xu")
"""

from __future__ import annotations

import html
import ipaddress
import logging
import os
import re
import time
from typing import Any
from urllib.parse import urlparse

import bot

logger = logging.getLogger(__name__)

JAMENDO_TRUSTED_DOMAINS = frozenset({
    "jamendo.com",
    "storage.jamendo.com",
    "prod-1.storage.jamendo.com",
    "cdn.jamendo.com",
    "mp3d.jamendo.com",
})

DANGEROUS_SCHEMES = frozenset({"javascript:", "data:", "file:", "vbscript:", "blob:", "about:"})

# Pricing constants mirroring Bot truth:
BOT_SEARCH_IMMEDIATE_XU = 0
BOT_SELECT_IMMEDIATE_XU = 0
BOT_DOWNSTREAM_USAGE_XU = 0


def _safe_actor_key(actor_id: Any) -> int | str:
    s = str(actor_id or "").strip()
    if s.isdigit():
        return int(s)
    return s


def _is_private_host(host: str) -> bool:
    h = str(host or "").strip().lower().rstrip(".")
    if not h:
        return True
    if h in {"localhost", "0.0.0.0"} or h.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(h)
        return bool(ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)
    except ValueError:
        return False


def validate_preview_url_safety(url: str) -> tuple[bool, str]:
    """Validate that audio preview URL belongs strictly to trusted public CDNs and has no SSRF risk."""
    clean_url = str(url or "").strip()
    if not clean_url:
        return False, "EMPTY_URL"
    lower_url = clean_url.lower()
    for scheme in DANGEROUS_SCHEMES:
        if lower_url.startswith(scheme):
            return False, "DANGEROUS_SCHEME"
    try:
        parsed = urlparse(clean_url)
    except Exception:
        return False, "MALFORMED_URL"
    if parsed.scheme not in {"http", "https"}:
        return False, "INVALID_SCHEME"
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False, "MISSING_HOSTNAME"
    if _is_private_host(hostname):
        return False, "PRIVATE_HOST_BLOCKED"
    if not any(hostname == d or hostname.endswith("." + d) for d in JAMENDO_TRUSTED_DOMAINS):
        return False, "UNTRUSTED_DOMAIN"
    return True, "SAFE"


async def handle_music_library_search(
    query: str,
    actor_id: str,
    limit: int = 8,
) -> tuple[bool, dict[str, Any], int]:
    """Execute canonical Jamendo search and register 1-based preview session for actor."""
    clean_actor = str(actor_id or "").strip()
    if not clean_actor:
        return False, {
            "ok": False,
            "error_code": "DELIVERY_ACTOR_REQUIRED",
            "message": "Authenticated actor_id / user_id is required",
        }, 401

    clean_query = str(query or "").strip()
    if not clean_query:
        return False, {
            "ok": False,
            "error_code": "INVALID_QUERY",
            "message": "Từ khóa tìm kiếm không được để trống.",
        }, 400

    if len(clean_query) > 160:
        clean_query = clean_query[:160]

    # Pre-network credential check: fail closed if Jamendo client ID not configured
    jamendo_client_id = getattr(bot, "JAMENDO_CLIENT_ID", None)
    if not jamendo_client_id:
        return False, {
            "ok": False,
            "error_code": "JAMENDO_CREDENTIALS_MISSING",
            "message": "Kho nhạc chưa được cấu hình. Bot chưa trừ Xu.",
            "charged_xu": 0,
        }, 503

    try:
        clamped_limit = max(1, min(int(limit or 8), 10))
        raw_results = await bot.fetch_jamendo_tracks(clean_query, limit=clamped_limit)
    except Exception as e:
        logger.warning("Jamendo provider search error: %s", e)
        return False, {
            "ok": False,
            "error_code": "JAMENDO_FETCH_FAILED",
            "message": "Lỗi kết nối dịch vụ âm thanh ngoài. Bot chưa trừ Xu.",
            "detail": str(e),
            "charged_xu": 0,
        }, 502

    normalized_items = [bot.jamendo_preview_item(item) for item in (raw_results or [])]
    # Filter to items with preview_url
    valid_items = [it for it in normalized_items if it.get("preview_url")]

    if not valid_items:
        return True, {
            "ok": True,
            "results": [],
            "items": [],
            "count": 0,
            "query": clean_query,
            "callback_token": "",
            "message": "Chưa tìm thấy nhạc phù hợp. Bot chưa trừ Xu.",
            "charged_xu": 0,
        }, 200

    token = bot.save_media_preview_results("music", clean_actor, clean_query, valid_items)
    return True, {
        "ok": True,
        "results": valid_items,
        "items": valid_items,
        "count": len(valid_items),
        "query": clean_query,
        "callback_token": token,
        "charged_xu": 0,
    }, 200


def handle_music_library_select(
    index: int,
    actor_id: str,
    callback_token: str | None = None,
) -> tuple[bool, dict[str, Any], int]:
    """Select a music track from the actor's latest search session via 1-based index."""
    clean_actor = str(actor_id or "").strip()
    if not clean_actor:
        return False, {
            "ok": False,
            "error_code": "DELIVERY_ACTOR_REQUIRED",
            "message": "Authenticated actor_id / user_id is required",
        }, 401

    item, error = bot.get_media_preview_item("music", clean_actor, str(index), callback_token=callback_token)
    if error == "expired":
        return False, {
            "ok": False,
            "error_code": "SEARCH_SESSION_EXPIRED",
            "message": "Kết quả nghe thử đã hết hạn. Vui lòng tìm kiếm lại.",
            "charged_xu": 0,
        }, 410
    if error or not item:
        return False, {
            "ok": False,
            "error_code": "INVALID_INDEX",
            "message": "Số thứ tự không hợp lệ hoặc nằm ngoài danh sách kết quả vừa tìm.",
            "charged_xu": 0,
        }, 422

    selected = dict(item)
    selected["created_at"] = time.time()
    actor_key = _safe_actor_key(clean_actor)
    bot.SELECTED_MUSIC[actor_key] = selected

    return True, {
        "ok": True,
        "selected": selected,
        "message": f"Đã chọn nhạc: {selected.get('title')}",
        "charged_xu": 0,
    }, 200


def handle_music_library_selected(actor_id: str) -> tuple[bool, dict[str, Any], int]:
    """Retrieve the currently selected music track for the authenticated actor."""
    clean_actor = str(actor_id or "").strip()
    if not clean_actor:
        return False, {
            "ok": False,
            "error_code": "DELIVERY_ACTOR_REQUIRED",
            "message": "Authenticated actor_id / user_id is required",
        }, 401

    actor_key = _safe_actor_key(clean_actor)
    selected = bot.get_selected_media_state(bot.SELECTED_MUSIC, actor_key)
    return True, {
        "ok": True,
        "selected": selected or None,
    }, 200


def handle_music_library_preview(
    index: int,
    actor_id: str,
    callback_token: str | None = None,
) -> tuple[bool, dict[str, Any], int]:
    """Resolve and validate a safe audio preview for 1-based track index."""
    clean_actor = str(actor_id or "").strip()
    if not clean_actor:
        return False, {
            "ok": False,
            "error_code": "DELIVERY_ACTOR_REQUIRED",
            "message": "Authenticated actor_id / user_id is required",
        }, 401

    item, error = bot.get_media_preview_item("music", clean_actor, str(index), callback_token=callback_token)
    if error == "expired":
        return False, {
            "ok": False,
            "error_code": "SEARCH_SESSION_EXPIRED",
            "message": "Kết quả nghe thử đã hết hạn. Vui lòng tìm kiếm lại.",
        }, 410
    if error or not item:
        return False, {
            "ok": False,
            "error_code": "INVALID_INDEX",
            "message": "Không tìm thấy kết quả để nghe thử.",
        }, 422

    raw_preview_url = str(item.get("preview_url") or "").strip()
    is_safe, reason = validate_preview_url_safety(raw_preview_url)
    if not is_safe:
        logger.warning("Blocked unsafe preview URL '%s': %s", raw_preview_url, reason)
        return False, {
            "ok": False,
            "error_code": "PREVIEW_UNSAFE_URL_BLOCKED",
            "message": "Đường dẫn nghe thử không an toàn hoặc không thuộc nhà cung cấp tin cậy.",
            "reason": reason,
        }, 400

    return True, {
        "ok": True,
        "preview_url": raw_preview_url,
        "title": item.get("title"),
        "author": item.get("author"),
        "duration": item.get("duration"),
        "license": item.get("license"),
        "provider": item.get("provider", "Jamendo"),
    }, 200
