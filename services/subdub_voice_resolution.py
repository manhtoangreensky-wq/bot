"""Canonical Bot Core SubDub Voice Resolution Authority (BOT-SUBDUB-D3).

Governed by owner-governed-codex, locked-focus-engineering.
Enforces:
1. Canonical server-side voice resolution; client has zero provider voice authority.
2. Owner-bound Voice Vault/profile lookup; cross-owner denied (403), missing denied (422/404).
3. Zero raw provider voice ID leakage in external/public projection.
4. Mode contract:
   - Dubbing modes (dub, dubbing, subtitle_plus_dub, subtitle_plus_dubbing) require valid voice resolution.
   - Non-dubbing modes (subtitle_create, subtitle_translate) succeed without voice requirement.
5. Deterministic safe response projection with masked voice ID identifier.
6. Fail-closed on unsupported TTS languages or unready voice profiles.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

logger = logging.getLogger("subdub_voice_resolution")

SUBDUB_DUBBING_MODES = {
    "dub",
    "dubbing",
    "subtitle_plus_dub",
    "subtitle_plus_dubbing",
}

SUBDUB_NON_DUBBING_MODES = {
    "subtitle_create",
    "subtitle_only",
    "subtitle_translate",
    "translated_subtitle",
}

VOICE_PROFILE_READY_STATUSES = {"active", "ready", "saved"}


def mask_voice_id(voice_id: str) -> str:
    """Safely mask internal provider voice identifier for public projection."""
    clean = str(voice_id or "").strip()
    if not clean:
        return ""
    if len(clean) > 8:
        return f"{clean[:3]}...{clean[-3:]}"
    return "***"


def normalize_subdub_mode(mode: str) -> str:
    """Normalize input mode to canonical SubDub mode."""
    raw = str(mode or "").strip().lower()
    if raw in {"dub", "dubbing"}:
        return "dub"
    if raw in {"subtitle_plus_dub", "subtitle_plus_dubbing"}:
        return "subtitle_plus_dub"
    if raw in {"subtitle_create", "subtitle_only"}:
        return "subtitle_create"
    if raw in {"subtitle_translate", "translated_subtitle"}:
        return "subtitle_translate"
    return ""


def parse_safe_speed(speed: Any) -> float:
    """Parse and clamp voice playback speed between 0.7 and 1.8."""
    try:
        val = float(speed)
        return max(0.7, min(1.8, round(val, 2)))
    except (ValueError, TypeError):
        return 1.0


def get_owner_voice_profiles_safe(
    actor_id: str | int,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return sanitized, owner-bound voice profiles safe for Web client presentation.
    
    Zero provider_voice_id or internal paths are returned.
    """
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
                WHERE user_id=? AND deleted_at IS NULL
                ORDER BY is_default DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (clean_actor, max(1, min(100, int(limit))), max(0, int(offset))),
            ).fetchall()

            items = []
            for row in rows:
                r = dict(row)
                status = str(r.get("status") or "").strip().lower()
                provider_voice = str(r.get("provider_voice_id") or "").strip()
                preview_ref = str(r.get("preview_audio_ref") or "").strip()

                tts_ready = bool(status in VOICE_PROFILE_READY_STATUSES and provider_voice)
                preview_ready = bool(
                    (status in VOICE_PROFILE_READY_STATUSES or status == "preview_ready")
                    and (preview_ref or provider_voice)
                )

                items.append({
                    "id": int(r["id"]),
                    "display_name": str(r.get("display_name") or "Giọng chưa đặt tên"),
                    "status": status,
                    "tts_ready": tts_ready,
                    "preview_ready": preview_ready,
                    "is_default": bool(r.get("is_default") or 0),
                    "consent_status": str(r.get("consent_status") or "required"),
                    "created_at": str(r.get("created_at") or ""),
                    "updated_at": str(r.get("updated_at") or ""),
                })
            return items
    except Exception as exc:
        logger.warning("get_owner_voice_profiles_safe failed: %s", exc)
        return []


def resolve_subdub_voice_authority(
    actor_id: str | int,
    payload: dict[str, Any] | None,
) -> tuple[bool, str, int, dict[str, Any]]:
    """Canonical server-side voice resolution authority for SubDub Web.
    
    Returns (ok, error_code, http_status_code, resolution_data).
    Client-provided provider_voice_id or voice_id are strictly rejected/ignored as authority.
    """
    import bot
    clean_actor = str(actor_id or "").strip()
    if not clean_actor:
        return False, "ACTOR_ID_REQUIRED", 401, {"detail": "Actor ID is required"}

    data = dict(payload or {})
    raw_mode = str(data.get("mode") or "").strip()
    mode = normalize_subdub_mode(raw_mode)

    if not mode:
        return False, "INVALID_SUBDUB_MODE", 422, {"detail": f"Unrecognized SubDub mode: '{raw_mode}'"}

    target_lang = str(data.get("target_language") or "").strip()
    speed = parse_safe_speed(data.get("voice_speed") or data.get("speed"))

    # 1. Non-dubbing modes: do not require voice
    if mode in {"subtitle_create", "subtitle_translate"}:
        return True, "OK", 200, {
            "ok": True,
            "mode": mode,
            "needs_voice": False,
            "voice_selection_mode": "none",
            "voice_profile_id": None,
            "resolved_voice_name": "",
            "resolved_gender": "",
            "target_language": target_lang,
            "voice_speed": speed,
            "resolved_voice_id_masked": "",
        }

    # 2. Dubbing modes: require valid voice resolution
    profile_id_raw = data.get("voice_profile_id")
    profile_id = None
    if profile_id_raw is not None and str(profile_id_raw).strip() != "":
        try:
            parsed_pid = int(profile_id_raw)
            if parsed_pid > 0:
                profile_id = parsed_pid
        except (ValueError, TypeError):
            return False, "INVALID_VOICE_PROFILE_ID", 422, {"detail": "voice_profile_id must be a positive integer"}

    # 2A. Custom Voice Vault profile requested
    if profile_id is not None:
        try:
            with bot.db_connect() as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM voice_profiles WHERE id=?",
                    (profile_id,),
                ).fetchone()

                if not row or row["deleted_at"] is not None:
                    return False, "PROFILE_NOT_FOUND", 422, {"detail": f"Voice profile #{profile_id} not found"}

                record = dict(row)
                if str(record.get("user_id") or "").strip() != clean_actor:
                    return False, "FORBIDDEN_CROSS_OWNER", 403, {"detail": "Cannot access voice profile belonging to another user"}

                status = str(record.get("status") or "").strip().lower()
                provider_voice = str(record.get("provider_voice_id") or "").strip()

                if status not in VOICE_PROFILE_READY_STATUSES or not provider_voice:
                    return False, "VOICE_NOT_READY", 422, {"detail": f"Voice profile #{profile_id} is not ready for TTS generation"}

                display_name = str(record.get("display_name") or f"Profile #{profile_id}")
                return True, "OK", 200, {
                    "ok": True,
                    "mode": mode,
                    "needs_voice": True,
                    "voice_selection_mode": "manual",
                    "voice_profile_id": profile_id,
                    "resolved_voice_name": display_name,
                    "resolved_gender": str(data.get("voice_gender") or "").strip().lower(),
                    "target_language": target_lang or "vi",
                    "voice_speed": speed,
                    "resolved_voice_id_masked": mask_voice_id(provider_voice),
                    "_internal_provider_voice_id": provider_voice,
                }
        except Exception as exc:
            logger.error("Error looking up voice profile: %s", exc)
            return False, "INTERNAL_LOOKUP_ERROR", 500, {"detail": str(exc)}

    # 2B. Preset voice requested (default routing by language & gender)
    # Note: any client-supplied provider_voice_id or voice_id is IGNORED
    gender = str(data.get("voice_gender") or data.get("gender") or "female").strip().lower()
    if gender not in {"female", "male"}:
        gender = "female"

    effective_lang = target_lang or "vi"
    from services.subdub_tts_language_routing import resolve_subdub_tts_language_route

    route_res = resolve_subdub_tts_language_route({
        "target_language": effective_lang,
        "selected_voice_gender": gender,
    })

    if not route_res.get("ok"):
        return False, "UNSUPPORTED_LANGUAGE", 422, {
            "detail": f"Target language '{effective_lang}' is not supported for TTS synthesis"
        }

    edge_voice = str(route_res.get("resolved_edge_voice_id") or "").strip()
    lang_name = str(route_res.get("resolved_tts_language_name") or effective_lang)
    preset_label = f"{lang_name} ({'Nữ' if gender == 'female' else 'Nam'})"

    return True, "OK", 200, {
        "ok": True,
        "mode": mode,
        "needs_voice": True,
        "voice_selection_mode": "preset",
        "voice_profile_id": None,
        "resolved_voice_name": preset_label,
        "resolved_gender": gender,
        "target_language": str(route_res.get("resolved_tts_language_code") or effective_lang),
        "voice_speed": speed,
        "resolved_voice_id_masked": mask_voice_id(edge_voice),
        "_internal_provider_voice_id": edge_voice,
    }


def to_safe_voice_resolution_projection(res: dict[str, Any]) -> dict[str, Any]:
    """Sanitize internal resolution dictionary to remove internal keys before JSON response."""
    safe = dict(res or {})
    safe.pop("_internal_provider_voice_id", None)
    safe.pop("provider_voice_id", None)
    return safe
