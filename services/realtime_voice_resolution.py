"""Canonical Bot Core Realtime Voice Resolution Authority (RT-01 / RT-FIX1).

Governed by owner-governed-codex, locked-focus-engineering.
Enforces:
1. Server retains absolute authority over voice selection and provider resolution.
2. Owner-scoped Voice Vault validation:
   - FOREIGN_VOICE_PROFILE_BLOCKED: Profiles belonging to a different owner are rejected.
   - DELETED_PROFILE_BLOCKED: Archived/deleted profiles are rejected.
   - NOT_READY_PROFILE_BLOCKED: Pending/unready/revoked-consent profiles are rejected.
   - VALID_OWNER_PROFILE: Valid, ready profiles resolve to provider voice.
3. gender_preference is strictly passed and honored for canonical fallbacks.
4. Client has zero authority to directly inject unverified external voice IDs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ResolvedVoice:
    voice_id: str
    provider: str
    gender: str
    language_code: str
    speed: float = 1.0
    pitch: float = 0.0
    voice_vault_id: Optional[str] = None
    validation_status: str = "valid"
    error_code: Optional[str] = None


# Canonical default voice mapping per language
CANONICAL_VOICE_CATALOG: Dict[str, Dict[str, str]] = {
    "vi": {
        "female": "vi-VN-HoaiMyNeural",
        "male": "vi-VN-NamMinhNeural",
        "default": "vi-VN-NamMinhNeural",
    },
    "en": {
        "female": "en-US-JennyNeural",
        "male": "en-US-GuyNeural",
        "default": "en-US-JennyNeural",
    },
    "ja": {
        "female": "ja-JP-NanamiNeural",
        "male": "ja-JP-KeitaNeural",
        "default": "ja-JP-NanamiNeural",
    },
    "zh": {
        "female": "zh-CN-XiaoxiaoNeural",
        "male": "zh-CN-YunxiNeural",
        "default": "zh-CN-XiaoxiaoNeural",
    },
    "ko": {
        "female": "ko-KR-SunHiNeural",
        "male": "ko-KR-InJoonNeural",
        "default": "ko-KR-SunHiNeural",
    },
}


_TEST_VOICE_VAULT_LOOKUP: Optional[Callable[[str, str], Optional[Dict[str, Any]]]] = None


def set_test_voice_vault_lookup(func: Optional[Callable[[str, str], Optional[Dict[str, Any]]]]) -> None:
    """Sets a test lookup function for canonical Voice Vault records in provider-free tests."""
    global _TEST_VOICE_VAULT_LOOKUP
    _TEST_VOICE_VAULT_LOOKUP = func


def canonical_db_voice_vault_lookup(voice_profile_id: str, owner_id: str) -> Optional[Dict[str, Any]]:
    """Default DB-backed owner-scoped voice profile lookup in Bot."""
    clean_actor = str(owner_id or "").strip()
    clean_id = str(voice_profile_id or "").strip()
    if not clean_actor or not clean_id:
        return None
    try:
        import bot
        import sqlite3
        with bot.db_connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM voice_profiles WHERE id=? OR client_voice_id=?",
                (clean_id, clean_id),
            ).fetchone()
            if not row:
                return None
            record = dict(row)
            return {
                "id": str(record["id"]),
                "owner_id": str(record.get("user_id") or ""),
                "voice_id": str(record.get("provider_voice_id") or ""),
                "provider": str(record.get("provider") or "voice_vault"),
                "status": str(record.get("status") or ""),
                "state": "deleted" if record.get("deleted_at") is not None else "active",
                "consent_status": str(record.get("consent_status") or "active"),
                "gender": str(record.get("gender") or "male"),
            }
    except Exception as exc:
        logger.warning(f"canonical_db_voice_vault_lookup query failed: {exc}")
        return None


class RealtimeVoiceResolver:
    """Server-side authority for resolving TTS voices and validating Voice Vault records."""

    def __init__(self, default_provider: str = "edge_tts", vault_lookup_func: Optional[Callable] = None):
        self.default_provider = default_provider
        self.vault_lookup_func = vault_lookup_func

    def resolve(
        self,
        target_language: str = "vi",
        gender_preference: Optional[str] = None,
        voice_profile_id: Optional[str] = None,
        owner_id: Optional[str] = None,
    ) -> ResolvedVoice:
        """Resolves target language, gender, and owner-scoped voice profile into a verified voice."""
        lang_key = target_language.lower().split("-")[0]
        lang_catalog = CANONICAL_VOICE_CATALOG.get(lang_key, CANONICAL_VOICE_CATALOG["vi"])

        # Normalize gender preference
        gender = (gender_preference or "male").lower().strip()
        if gender not in ("male", "female"):
            gender = "male"

        canonical_fallback_voice = lang_catalog.get(gender, lang_catalog["default"])

        # Check if user requested a specific Voice Vault profile
        if voice_profile_id:
            profile = None
            if _TEST_VOICE_VAULT_LOOKUP is not None:
                try:
                    profile = _TEST_VOICE_VAULT_LOOKUP(str(voice_profile_id), str(owner_id or ""))
                except Exception as e:
                    logger.warning(f"Test voice vault lookup error: {e}")
            elif self.vault_lookup_func is not None:
                try:
                    profile = self.vault_lookup_func(str(voice_profile_id), str(owner_id or ""))
                except Exception as e:
                    logger.warning(f"Voice vault lookup error: {e}")
            else:
                profile = canonical_db_voice_vault_lookup(str(voice_profile_id), str(owner_id or ""))

            if not profile:
                return ResolvedVoice(
                    voice_id="",
                    provider=self.default_provider,
                    gender=gender,
                    language_code=lang_key,
                    validation_status="invalid",
                    error_code="MISSING_PROFILE_BLOCKED",
                )

            # 1. Foreign profile check (must match owner_id if owner specified)
            profile_owner = str(profile.get("owner_id") or profile.get("account_id") or "").strip()
            if owner_id and profile_owner and profile_owner != str(owner_id).strip():
                return ResolvedVoice(
                    voice_id="",
                    provider=self.default_provider,
                    gender=gender,
                    language_code=lang_key,
                    validation_status="invalid",
                    error_code="FOREIGN_PROFILE_BLOCKED",
                )

            # 2. Deleted / archived profile check
            state = str(profile.get("state") or "active").lower()
            if state in ("deleted", "archived"):
                return ResolvedVoice(
                    voice_id="",
                    provider=self.default_provider,
                    gender=gender,
                    language_code=lang_key,
                    validation_status="invalid",
                    error_code="DELETED_PROFILE_BLOCKED",
                )

            # 3. Ready status / consent revoked check
            status = str(profile.get("status") or "ready").lower()
            consent_status = str(profile.get("consent_status") or "active").lower()
            if status not in ("ready", "active") or consent_status == "revoked":
                return ResolvedVoice(
                    voice_id="",
                    provider=self.default_provider,
                    gender=gender,
                    language_code=lang_key,
                    validation_status="invalid",
                    error_code="NOT_READY_PROFILE_BLOCKED",
                )

            # 4. Valid profile
            resolved_gender = profile.get("gender") or gender
            return ResolvedVoice(
                voice_id=str(profile.get("voice_id") or canonical_fallback_voice),
                provider=str(profile.get("provider") or "voice_vault"),
                gender=resolved_gender,
                language_code=lang_key,
                voice_vault_id=voice_profile_id,
                validation_status="valid",
            )

        # Canonical lookup
        return ResolvedVoice(
            voice_id=canonical_fallback_voice,
            provider=self.default_provider,
            gender=gender,
            language_code=lang_key,
            speed=1.0,
            validation_status="valid",
        )
