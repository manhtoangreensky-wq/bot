"""Canonical Bot Core Realtime ASR / STT Adapter (RT-01 / RT-FIX1).

Governed by owner-governed-codex, locked-focus-engineering.
Enforces:
1. Fast streaming transcription on speech segments (PCM/WAV).
2. Canonical binding to Bot STT/ASR primitive (bot.asr_transcribe_audio) WITHOUT requiring request-time context dictionary.
3. Zero-cost testing guard: supports dependency injection / mock hook without external provider network calls.
4. Returns RealtimeASRResult with text, start_ms, and end_ms.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from services.realtime_audio_ingress import SpeechSegment

logger = logging.getLogger(__name__)


@dataclass
class RealtimeASRResult:
    ok: bool
    text: str
    start_ms: int
    end_ms: int
    language: str = "auto"
    confidence: float = 1.0
    provider: str = "mock"
    error: Optional[str] = None


# Mock hook for deterministic unit testing without external network or provider calls
_TEST_MOCK_ASR_HANDLER: Optional[Callable[[SpeechSegment, str], RealtimeASRResult]] = None
_CANONICAL_ASR_PRIMITIVE: Optional[Callable] = None


def set_test_asr_mock_handler(handler: Optional[Callable[[SpeechSegment, str], RealtimeASRResult]]) -> None:
    """Sets a mock handler for testing environment."""
    global _TEST_MOCK_ASR_HANDLER
    _TEST_MOCK_ASR_HANDLER = handler


def set_canonical_asr_primitive(primitive: Optional[Callable]) -> None:
    """Dependency injection hook for binding the canonical ASR primitive."""
    global _CANONICAL_ASR_PRIMITIVE
    _CANONICAL_ASR_PRIMITIVE = primitive


def get_canonical_asr_primitive() -> Optional[Callable]:
    """Resolves and returns the canonical ASR primitive without blocking on cold module imports."""
    global _CANONICAL_ASR_PRIMITIVE
    if _CANONICAL_ASR_PRIMITIVE is not None:
        return _CANONICAL_ASR_PRIMITIVE
    import sys
    if "bot" in sys.modules:
        bot_mod = sys.modules["bot"]
        if hasattr(bot_mod, "asr_transcribe_audio"):
            _CANONICAL_ASR_PRIMITIVE = bot_mod.asr_transcribe_audio
            return _CANONICAL_ASR_PRIMITIVE
    return None


class RealtimeASRAdapter:
    """Adapter for transcribing incoming real-time speech segments."""

    def __init__(
        self,
        provider: str = "auto",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        asr_primitive: Optional[Callable] = None,
    ):
        self.provider = provider
        self.api_key = api_key
        self.base_url = base_url
        self.model = model or "whisper-1"
        self._primitive = asr_primitive

    async def transcribe(
        self,
        segment: SpeechSegment,
        language: str = "auto",
        context: Optional[Dict[str, Any]] = None,
    ) -> RealtimeASRResult:
        """Transcribes a SpeechSegment into text with timestamps."""
        # Check if test mock handler is active
        if _TEST_MOCK_ASR_HANDLER is not None:
            return _TEST_MOCK_ASR_HANDLER(segment, language)

        if segment.is_silence or len(segment.pcm_bytes) == 0:
            return RealtimeASRResult(
                ok=True,
                text="",
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                language=language,
                provider="vad_silence",
            )

        wav_bytes = segment.to_wav_bytes()

        # Resolve canonical ASR primitive (from instance, context, or global resolver)
        asr_func = self._primitive
        if asr_func is None and context and "bot_transcribe_func" in context:
            asr_func = context["bot_transcribe_func"]
        if asr_func is None:
            asr_func = get_canonical_asr_primitive()

        if asr_func is not None:
            try:
                res = await asr_func(wav_bytes, content_type="audio/wav", language=language)
                text = str(res.get("text") or "").strip()
                return RealtimeASRResult(
                    ok=bool(text),
                    text=text,
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    language=str(res.get("language") or language),
                    provider=str(res.get("provider") or self.provider),
                )
            except Exception as e:
                logger.warning(f"Canonical ASR execution error: {e}")
                return RealtimeASRResult(
                    ok=False,
                    text="",
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    error=str(e),
                    provider=self.provider,
                )

        return RealtimeASRResult(
            ok=False,
            text="",
            start_ms=segment.start_ms,
            end_ms=segment.end_ms,
            language=language,
            error="no_asr_provider_configured",
            provider="none",
        )
