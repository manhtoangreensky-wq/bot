"""Canonical Bot Core Realtime TTS Adapter (RT-01 / RT-FIX1).

Governed by owner-governed-codex, locked-focus-engineering.
Enforces:
1. Low-latency chunk speech synthesis for live dubbing.
2. Canonical binding to Bot TTS primitive (bot.tts_edge_bytes) WITHOUT requiring request-time context dictionary.
3. Zero-cost testing guard: supports dependency injection / mock hook without external provider network calls.
4. Returns base64 audio payload and duration for audio ducking synchronization.
"""

from __future__ import annotations

import base64
import inspect
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from services.realtime_voice_resolution import ResolvedVoice

logger = logging.getLogger(__name__)


@dataclass
class RealtimeTTSResult:
    ok: bool
    audio_base64: Optional[str]
    duration_ms: int
    format: str = "mp3"
    sample_rate: int = 24000
    provider: str = "mock"
    error: Optional[str] = None
    error_code: Optional[str] = None


_TEST_MOCK_TTS_HANDLER: Optional[Callable[[str, ResolvedVoice], RealtimeTTSResult]] = None
_CANONICAL_TTS_PRIMITIVE: Optional[Callable] = None


def set_test_tts_mock_handler(
    handler: Optional[Callable[[str, ResolvedVoice], RealtimeTTSResult]]
) -> None:
    """Sets a mock handler for testing environment."""
    global _TEST_MOCK_TTS_HANDLER
    _TEST_MOCK_TTS_HANDLER = handler


def set_canonical_tts_primitive(primitive: Optional[Callable]) -> None:
    """Dependency injection hook for binding the canonical TTS primitive."""
    global _CANONICAL_TTS_PRIMITIVE
    _CANONICAL_TTS_PRIMITIVE = primitive


def get_canonical_tts_primitive() -> Optional[Callable]:
    """Resolves and returns the canonical TTS primitive without blocking on cold module imports."""
    global _CANONICAL_TTS_PRIMITIVE
    if _CANONICAL_TTS_PRIMITIVE is not None:
        return _CANONICAL_TTS_PRIMITIVE
    import sys
    for mod_name in ("bot", "__main__"):
        bot_mod = sys.modules.get(mod_name)
        if bot_mod is not None and callable(getattr(bot_mod, "realtime_dub_tts_bytes", None)):
            _CANONICAL_TTS_PRIMITIVE = bot_mod.realtime_dub_tts_bytes
            return _CANONICAL_TTS_PRIMITIVE
        if bot_mod is not None and hasattr(bot_mod, "tts_edge_bytes"):
            _CANONICAL_TTS_PRIMITIVE = bot_mod.tts_edge_bytes
            return _CANONICAL_TTS_PRIMITIVE
    return None


class RealtimeTTSAdapter:
    """Adapter for synthesizing translated sentences into audio chunks for dubbing."""

    def __init__(self, default_format: str = "mp3", tts_primitive: Optional[Callable] = None):
        self.default_format = default_format
        self._primitive = tts_primitive

    async def synthesize(
        self,
        text: str,
        voice: ResolvedVoice,
        context: Optional[Dict[str, Any]] = None,
    ) -> RealtimeTTSResult:
        """Synthesizes text into base64 audio with specified voice."""
        clean_text = text.strip()
        if not clean_text:
            return RealtimeTTSResult(
                ok=True,
                audio_base64=None,
                duration_ms=0,
                format=self.default_format,
                provider="noop",
            )

        if voice.validation_status != "valid" or not voice.voice_id:
            return RealtimeTTSResult(
                ok=False,
                audio_base64=None,
                duration_ms=0,
                format=self.default_format,
                provider=voice.provider or "unknown",
                error_code=voice.error_code or "INVALID_VOICE",
            )

        # Check if test mock handler is active
        if _TEST_MOCK_TTS_HANDLER is not None:
            return _TEST_MOCK_TTS_HANDLER(clean_text, voice)

        # Resolve canonical TTS primitive
        tts_func = self._primitive
        if tts_func is None and context and "bot_tts_func" in context:
            tts_func = context["bot_tts_func"]
        if tts_func is None:
            tts_func = get_canonical_tts_primitive()

        if tts_func is not None:
            try:
                # Invoke bound canonical TTS primitive (either realtime_dub_tts_bytes or legacy tts_edge_bytes / test mock)
                kwargs = {"voice_id": voice.voice_id}
                try:
                    sig_params = inspect.signature(tts_func).parameters
                    has_var_kw = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in sig_params.values())
                    if has_var_kw or "gender" in sig_params:
                        kwargs["gender"] = voice.gender
                    if has_var_kw or "language_code" in sig_params:
                        kwargs["language_code"] = voice.language_code
                    if has_var_kw or "voice_vault_id" in sig_params:
                        kwargs["voice_vault_id"] = voice.voice_vault_id or ""
                    if has_var_kw or "speed" in sig_params:
                        kwargs["speed"] = voice.speed
                except (TypeError, ValueError):
                    pass
                res = await tts_func(clean_text, **kwargs)
                audio_bytes = b""
                dur_ms = 1500
                detail_msg = None
                if isinstance(res, tuple):
                    status, audio_bytes, detail, _ = res
                    ok = (status == "PASS" and bool(audio_bytes))
                    if not ok:
                        detail_msg = str(detail or status or "tts_failed")
                elif isinstance(res, dict):
                    audio_bytes = res.get("audio_bytes") or b""
                    ok = bool(res.get("ok", bool(audio_bytes)))
                    dur_ms = int(res.get("duration_seconds", 1.5) * 1000)
                    if not ok:
                        detail_msg = str(res.get("error") or res.get("error_code") or "tts_failed")
                else:
                    ok = False
                    detail_msg = "invalid_tts_response"

                b64_str = base64.b64encode(audio_bytes).decode("ascii") if audio_bytes else None
                return RealtimeTTSResult(
                    ok=bool(b64_str),
                    audio_base64=b64_str,
                    duration_ms=dur_ms,
                    format=self.default_format,
                    provider=voice.provider,
                    error=detail_msg,
                )
            except Exception as e:
                logger.warning(f"Canonical TTS execution error: {e}")
                return RealtimeTTSResult(
                    ok=False,
                    audio_base64=None,
                    duration_ms=0,
                    error=str(e),
                    provider=voice.provider,
                )

        return RealtimeTTSResult(
            ok=False,
            audio_base64=None,
            duration_ms=0,
            error="no_tts_provider_configured",
            provider="none",
        )
