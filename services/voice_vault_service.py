"""Canonical Bot Core Voice Vault Management Service (R37 SPEC).

Provides owner-scoped, idempotent operations for:
- Listing voice profiles (sanitized, zero provider IDs or local file paths)
- Renaming voice profiles (display_name 2-80 chars)
- Setting default voice profile (with readiness check)
- Soft deleting voice profile (idempotent, sets status='deleted', is_default=0, deleted_at)
- Delivering preview audio safely (fail-closed when not ready, missing artifact, or unsafe remote URL)
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import sqlite3
from typing import Any
import urllib.parse

logger = logging.getLogger(__name__)

VOICE_PROFILE_READY_STATUSES = frozenset({"active", "ready", "saved"})
VOICE_PROFILE_PREVIEW_STATUSES = VOICE_PROFILE_READY_STATUSES | {"preview_ready"}


def sanitize_profile_record(row: dict[str, Any]) -> dict[str, Any]:
    """Return a browser-safe projection of a voice_profiles row.

    Never exposes provider_voice_id, source_file_id, source_file_ref,
    local filesystem path in preview_audio_ref, or internal secrets.
    """
    status = str(row.get("status") or "").strip().lower()
    provider_voice = str(row.get("provider_voice_id") or "").strip()
    preview_ref = str(row.get("preview_audio_ref") or "").strip()

    tts_ready = bool(status in VOICE_PROFILE_READY_STATUSES and provider_voice)
    preview_ready = bool(
        (status in VOICE_PROFILE_PREVIEW_STATUSES)
        and (preview_ref or provider_voice)
    )

    return {
        "id": int(row["id"]),
        "display_name": str(row.get("display_name") or "Giọng chưa đặt tên"),
        "status": status,
        "tts_ready": tts_ready,
        "preview_ready": preview_ready,
        "is_default": bool(row.get("is_default") or 0),
        "consent_status": str(row.get("consent_status") or "required"),
        "has_preview": bool(preview_ref),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def list_owner_voice_profiles(
    actor_id: str | int,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return sanitized, owner-bound voice profiles for Web presentation."""
    import bot

    clean_actor = str(actor_id or "").strip()
    if not clean_actor:
        return []

    try:
        with bot.db_connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, display_name, status, is_default, consent_status,
                       preview_audio_ref, provider_voice_id, created_at, updated_at
                FROM voice_profiles
                WHERE user_id=? AND deleted_at IS NULL AND status NOT IN ('deleted')
                ORDER BY is_default DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (clean_actor, max(1, min(100, int(limit))), max(0, int(offset))),
            ).fetchall()

            return [sanitize_profile_record(dict(r)) for r in rows]
    except Exception as exc:
        logger.warning("list_owner_voice_profiles failed: %s", exc)
        return []


def rename_owner_voice_profile(
    actor_id: str | int,
    profile_id: int,
    new_name: str,
) -> tuple[bool, str, int, dict[str, Any]]:
    """Rename a voice profile with owner isolation and validation."""
    import bot

    clean_actor = str(actor_id or "").strip()
    if not clean_actor:
        return False, "ACTOR_ID_REQUIRED", 401, {"message": "Actor ID is required"}

    profile = bot.get_user_voice_profile(clean_actor, profile_id)
    if not profile or str(profile.get("status") or "").lower() == "deleted":
        return False, "PROFILE_NOT_FOUND", 404, {"message": "Voice profile not found"}

    clean_name = re.sub(r"\s+", " ", str(new_name or "")).strip()
    if len(clean_name) < 2 or len(clean_name) > 80:
        return False, "VOICE_PROFILE_INVALID_NAME", 400, {"message": "Tên giọng từ 2 đến 80 ký tự."}

    ok = bot.update_user_voice_profile(clean_actor, profile_id, display_name=clean_name)
    if not ok:
        return False, "UPDATE_FAILED", 500, {"message": "Không thể cập nhật tên giọng"}

    updated = bot.get_user_voice_profile(clean_actor, profile_id)
    return True, "OK", 200, {
        "ok": True,
        "profile_id": profile_id,
        "display_name": clean_name,
        "profile": sanitize_profile_record(updated),
    }


def set_default_owner_voice_profile(
    actor_id: str | int,
    profile_id: int,
) -> tuple[bool, str, int, dict[str, Any]]:
    """Set a voice profile as default for the owner, enforcing readiness."""
    import bot

    clean_actor = str(actor_id or "").strip()
    if not clean_actor:
        return False, "ACTOR_ID_REQUIRED", 401, {"message": "Actor ID is required"}

    profile = bot.get_user_voice_profile(clean_actor, profile_id)
    if not profile or str(profile.get("status") or "").lower() == "deleted":
        return False, "PROFILE_NOT_FOUND", 404, {"message": "Voice profile not found"}

    if not bot.voice_profile_can_generate_tts(profile):
        return False, "VOICE_PROFILE_NOT_READY", 400, {
            "message": "Chỉ giọng đã lưu thành công mới có thể đặt mặc định."
        }

    ok = bot.set_default_voice_profile(clean_actor, profile_id)
    if not ok:
        return False, "UPDATE_FAILED", 500, {"message": "Không thể đặt làm giọng mặc định."}

    updated = bot.get_user_voice_profile(clean_actor, profile_id)
    return True, "OK", 200, {
        "ok": True,
        "profile_id": profile_id,
        "is_default": True,
        "profile": sanitize_profile_record(updated),
    }


def soft_delete_owner_voice_profile(
    actor_id: str | int,
    profile_id: int,
) -> tuple[bool, str, int, dict[str, Any]]:
    """Soft delete a voice profile idempotently."""
    import bot

    clean_actor = str(actor_id or "").strip()
    if not clean_actor:
        return False, "ACTOR_ID_REQUIRED", 401, {"message": "Actor ID is required"}

    profile = bot.get_user_voice_profile(clean_actor, profile_id)
    if not profile:
        # Check if already deleted (idempotent delete)
        try:
            with bot.db_connect() as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT id, status, deleted_at FROM voice_profiles WHERE id=? AND user_id=?",
                    (profile_id, clean_actor),
                ).fetchone()
                if row and (str(row["status"]).lower() == "deleted" or row["deleted_at"] is not None):
                    return True, "OK", 200, {
                        "ok": True,
                        "profile_id": profile_id,
                        "deleted": True,
                    }
        except Exception:
            pass
        return False, "PROFILE_NOT_FOUND", 404, {"message": "Voice profile not found"}

    bot.soft_delete_voice_profile(clean_actor, profile_id)
    return True, "OK", 200, {
        "ok": True,
        "profile_id": profile_id,
        "deleted": True,
    }


def validate_safe_remote_preview_url(url: str) -> tuple[bool, str]:
    """Validate remote preview URL against SSRF, dangerous schemes, and private network addresses.

    Returns:
        (is_safe, error_code)
    """
    if not url or not isinstance(url, str):
        return False, "EMPTY_URL"
    clean = str(url).strip()
    if len(clean) > 2048:
        return False, "URL_TOO_LONG"
    try:
        parsed = urllib.parse.urlsplit(clean)
    except Exception:
        return False, "MALFORMED_URL"

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return False, "UNSAFE_SCHEME_BLOCKED"

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        return False, "MISSING_HOST"

    if parsed.username or parsed.password:
        return False, "CREDENTIAL_SMUGGLING_BLOCKED"

    if hostname in ("localhost", "127.0.0.1", "::1") or hostname.endswith(".localhost") or hostname.endswith(".local"):
        return False, "LOOPBACK_URL_BLOCKED"

    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_loopback:
            return False, "LOOPBACK_URL_BLOCKED"
        if ip.is_link_local:
            return False, "LINK_LOCAL_URL_BLOCKED"
        if ip.is_private:
            return False, "PRIVATE_IP_URL_BLOCKED"
        if ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False, "PRIVATE_IP_URL_BLOCKED"
    except ValueError:
        pass

    return True, "OK"


async def fetch_remote_preview_audio(url: str) -> tuple[bool, bytes, str]:
    """Fetch remote preview audio safely without real network calls in test mode."""
    if os.environ.get("APP_ENV") == "test":
        return True, b"\xFF\xFB\x90\x44" + b"\x00" * 256, "audio/mpeg"
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return False, b"", "audio/mpeg"
            ct = resp.headers.get("content-type") or "audio/mpeg"
            return True, resp.content, ct
    except Exception:
        return False, b"", "audio/mpeg"


def get_voice_profile_preview_delivery(
    actor_id: str | int,
    profile_id: int,
) -> tuple[bool, str, int, dict[str, Any], str | None, str | None]:
    """Validate preview delivery for owner-scoped profile.

    Returns:
        (ok, error_code, http_status, response_payload, file_path_if_local, remote_url_if_safe)
    """
    import bot

    clean_actor = str(actor_id or "").strip()
    if not clean_actor:
        return False, "ACTOR_ID_REQUIRED", 401, {"message": "Actor ID is required"}, None, None

    profile = bot.get_user_voice_profile(clean_actor, profile_id)
    if not profile or str(profile.get("status") or "").lower() == "deleted":
        return False, "PROFILE_NOT_FOUND", 404, {"message": "Voice profile not found"}, None, None

    if not bot.voice_profile_can_preview(profile):
        return False, "PREVIEW_NOT_READY", 400, {
            "message": "Voice profile is not in preview-ready status"
        }, None, None

    preview_ref = str(profile.get("preview_audio_ref") or "").strip()
    if not preview_ref:
        return False, "PREVIEW_MISSING_ARTIFACT", 404, {
            "message": "Giọng này chưa có bản nghe thử."
        }, None, None

    # Safe payload NEVER contains raw preview_url or filesystem path
    safe_payload = {
        "ok": True,
        "profile_id": profile_id,
        "display_name": str(profile.get("display_name") or ""),
        "delivery_mode": "stream",
        "content_type": "audio/mpeg",
        "download_ready": True,
    }

    # Remote URL delivery
    if preview_ref.startswith("http://") or preview_ref.startswith("https://") or "://" in preview_ref:
        is_safe, url_err = validate_safe_remote_preview_url(preview_ref)
        if not is_safe:
            return False, url_err, 400, {
                "message": f"URL bản nghe thử không hợp lệ: {url_err}"
            }, None, None
        return True, "OK", 200, safe_payload, None, preview_ref

    # Local file delivery
    if os.path.isfile(preview_ref):
        return True, "OK", 200, safe_payload, preview_ref, None

    # Preview ref exists in record but physical file is absent on storage
    return False, "PREVIEW_MISSING_ARTIFACT", 404, {
        "message": "Bản nghe thử không tìm thấy trên hệ thống lưu trữ."
    }, None, None
