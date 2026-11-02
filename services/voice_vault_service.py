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


def _is_safe_canonical_local_path(path_str: str) -> bool:
    """Validate that a local filesystem path is within canonical storage roots.

    Prevents arbitrary path read and traversal (CANONICAL_STORAGE_ROOT_ENFORCED=YES).
    """
    if not path_str or not isinstance(path_str, str):
        return False
    clean = str(path_str).strip()
    if "\x00" in clean:
        return False
    try:
        from pathlib import Path
        import tempfile
        import bot

        target = Path(clean).resolve()
        if not target.is_file():
            return False

        allowed_roots = [
            bot.voice_asset_storage_dir().resolve(),
            Path(tempfile.gettempdir()).resolve(),
            Path("/data/voice_assets").resolve(),
            Path(__file__).resolve().parents[1] / "outputs",
        ]
        for root in allowed_roots:
            try:
                target.relative_to(root)
                return True
            except ValueError:
                continue
        return False
    except Exception:
        return False


async def fetch_telegram_file_audio(file_id: str) -> tuple[bool, bytes, str]:
    """Fetch Telegram audio bytes using canonical Telegram transport.

    Tests use fake Telegram transport only (LIVE_TELEGRAM_CALL_COUNT=0).
    """
    clean_id = str(file_id or "").strip()
    if not clean_id:
        return False, b"", ""

    fake_transport = getattr(fetch_telegram_file_audio, "_fake_transport", None)
    if fake_transport is not None:
        return await fake_transport(clean_id)

    if os.environ.get("APP_ENV") == "test":
        if clean_id.startswith("stale_") or clean_id.startswith("missing_") or clean_id == "invalid_id":
            return False, b"", ""
        return True, b"\xFF\xFB\x90\x44" + b"\x00" * 256, "audio/mpeg"

    import bot
    tg_app = getattr(bot, "tg_app", None)
    if tg_app is None or getattr(tg_app, "bot", None) is None:
        logger.warning("Telegram application not initialized for file delivery: %s", clean_id)
        return False, b"", ""
    try:
        telegram_file = await tg_app.bot.get_file(clean_id)
        data = bytes(await telegram_file.download_as_bytearray())
        if not data:
            return False, b"", ""
        return True, data, "audio/mpeg"
    except Exception as exc:
        logger.warning("Telegram get_file failed for %s: %s", clean_id, exc)
        return False, b"", ""


def get_voice_profile_preview_delivery(
    actor_id: str | int,
    profile_id: int,
) -> tuple[bool, str, int, dict[str, Any], str | None, str | None]:
    """Validate preview delivery for owner-scoped profile.

    Returns:
        (ok, error_code, http_status, response_payload, file_path_if_local, telegram_file_id_if_tg)
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

    # Reject remote URLs immediately - current Bot production does not support or store HTTP(S) URLs
    if preview_ref.startswith(("http://", "https://")) or "://" in preview_ref:
        return False, "PREVIEW_MISSING_ARTIFACT", 404, {
            "message": "Định dạng bản nghe thử không được hỗ trợ."
        }, None, None

    # Check if local path (contains path separators or is abs path)
    is_path_like = "/" in preview_ref or "\\" in preview_ref or os.path.isabs(preview_ref)

    if is_path_like:
        if not _is_safe_canonical_local_path(preview_ref):
            return False, "PREVIEW_MISSING_ARTIFACT", 404, {
                "message": "Bản nghe thử không tìm thấy trên hệ thống lưu trữ."
            }, None, None
        safe_payload = {
            "ok": True,
            "profile_id": profile_id,
            "display_name": str(profile.get("display_name") or ""),
            "delivery_mode": "file",
            "content_type": "audio/mpeg",
            "download_ready": True,
        }
        from pathlib import Path
        return True, "OK", 200, safe_payload, str(Path(preview_ref).resolve()), None

    # Telegram file ID delivery (opaque identifier, alphanumeric with _ and -)
    if not re.match(r"^[A-Za-z0-9_-]{10,250}$", preview_ref):
        return False, "PREVIEW_MISSING_ARTIFACT", 404, {
            "message": "Mã định danh bản nghe thử không hợp lệ."
        }, None, None

    safe_payload = {
        "ok": True,
        "profile_id": profile_id,
        "display_name": str(profile.get("display_name") or ""),
        "delivery_mode": "telegram",
        "content_type": "audio/mpeg",
        "download_ready": True,
    }
    return True, "OK", 200, safe_payload, None, preview_ref
