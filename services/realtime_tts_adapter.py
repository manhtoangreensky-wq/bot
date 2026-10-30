"""Canonical Bot Core Realtime TTS Adapter (RT-01).

Governed by owner-governed-codex, locked-focus-engineering.
Enforces:
1. Low-latency chunk speech synthesis for live dubbing.
2. Returns base64 audio payload and duration for audio ducking synchronization.
3. Pluggable provider routing (Edge-TTS, VieNeu, Kokoro, Mock for tests).
4. Zero-cost testing guard: respects test environment mocks without touching paid APIs.
"""

from __future__ import annotations

import base64
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
    provider: str = "mock"
    error: Optional[str] = None


_TEST_MOCK_TTS_HANDLER: Optional[Callable[[str, ResolvedVoice], RealtimeTTSResult]] = None


def set_test_tts_mock_handler(
    handler: Optional[Callable[[str, ResolvedVoice], RealtimeTTSResult]]
) -> None:
    """Sets a mock handler for testing environment."""
    global _TEST_MOCK_TTS_HANDLER
    _TEST_MOCK_TTS_HANDLER = handler


class RealtimeTTSAdapter:
    """Adapter for synthesizing translated sentences into audio chunks for dubbing."""

    def __init__(self, default_format: str = "mp3"):
        self.default_format = default_format

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

        # Check if test mock handler is active
        if _TEST_MOCK_TTS_HANDLER is not None:
            return _TEST_MOCK_TTS_HANDLER(clean_text, voice)

        # Try Bot core tts helper if provided in context
        bot_tts = None
        if context and "bot_tts_func" in context:
            bot_tts = context["bot_tts_func"]

        if bot_tts:
            try:
                res = await bot_tts(clean_text, voice_id=voice.voice_id)
                audio_bytes = res.get("audio_bytes") or b""
                b64_str = base64.b64encode(audio_bytes).decode("ascii") if audio_bytes else ""
                dur_ms = int(res.get("duration_seconds", 1.0) * 1000)
                return RealtimeTTSResult(
                    ok=bool(b64_str),
                    audio_base64=b64_str,
                    duration_ms=dur_ms,
                    format=self.default_format,
                    provider=voice.provider,
                )
            except Exception as e:
                logger.warning(f"Bot TTS error: {e}")
                return RealtimeTTSResult(
                    ok=False,
                    audio_base64=None,
                    duration_ms=0,
                    error=str(e),
                    provider=voice.provider,
                )

        # Fallback if unconfigured
        return RealtimeTTSResult(
            ok=False,
            audio_base64=None,
            duration_ms=0,
            error="no_tts_provider_configured",
            provider="none",
        )
