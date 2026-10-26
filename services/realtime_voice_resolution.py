"""Canonical Bot Core Realtime Voice Resolution Authority (RT-01).

Governed by owner-governed-codex, locked-focus-engineering.
Enforces:
1. Server retains absolute authority over voice selection and provider resolution.
2. Client can only submit gender or voice profile preferences.
3. Maps languages and genders to canonical provider voices (Edge-TTS, VieNeu, Kokoro, Minimax).
4. Integrates seamlessly with Voice Vault profiles.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

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


class RealtimeVoiceResolver:
    """Server-side authority for resolving TTS voices."""

    def __init__(self, default_provider: str = "edge_tts"):
        self.default_provider = default_provider

    def resolve(
        self,
        target_language: str = "vi",
        gender_preference: Optional[str] = None,
        voice_profile_id: Optional[str] = None,
        voice_vault_data: Optional[Dict[str, Any]] = None,
    ) -> ResolvedVoice:
        """Resolves target language and user preference into a verified server voice."""
        lang_key = target_language.lower().split("-")[0]
        lang_catalog = CANONICAL_VOICE_CATALOG.get(lang_key, CANONICAL_VOICE_CATALOG["vi"])

        gender = (gender_preference or "male").lower().strip()
        if gender not in ("male", "female"):
            gender = "male"

        # Check if user requested a specific Voice Vault profile
        if voice_profile_id and voice_vault_data:
            vault_profile = voice_vault_data.get(voice_profile_id)
            if vault_profile and isinstance(vault_profile, dict):
                return ResolvedVoice(
                    voice_id=vault_profile.get("voice_id", lang_catalog.get(gender, lang_catalog["default"])),
                    provider=vault_profile.get("provider", "voice_vault"),
                    gender=vault_profile.get("gender", gender),
                    language_code=lang_key,
                    voice_vault_id=voice_profile_id,
                )

        # Canonical lookup
        voice_id = lang_catalog.get(gender, lang_catalog["default"])

        return ResolvedVoice(
            voice_id=voice_id,
            provider=self.default_provider,
            gender=gender,
            language_code=lang_key,
            speed=1.0,
        )
