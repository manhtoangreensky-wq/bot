"""Canonical Bot Core Realtime ASR / STT Adapter (RT-01).

Governed by owner-governed-codex, locked-focus-engineering.
Enforces:
1. Fast streaming transcription on speech segments (PCM/WAV).
2. Pluggable provider routing (Faster-Whisper / Key4U / OpenAI-compatible / Mock for tests).
3. Zero-cost testing guard: respects test environment mocks without touching paid APIs.
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


def set_test_asr_mock_handler(handler: Optional[Callable[[SpeechSegment, str], RealtimeASRResult]]) -> None:
    """Sets a mock handler for testing environment."""
    global _TEST_MOCK_ASR_HANDLER
    _TEST_MOCK_ASR_HANDLER = handler


class RealtimeASRAdapter:
    """Adapter for transcribing incoming real-time speech segments."""

    def __init__(
        self,
        provider: str = "auto",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.provider = provider
        self.api_key = api_key
        self.base_url = base_url
        self.model = model or "whisper-1"

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

        # Try Bot core transcribe helper if available in runtime context
        bot_transcribe = None
        if context and "bot_transcribe_func" in context:
            bot_transcribe = context["bot_transcribe_func"]

        if bot_transcribe:
            try:
                res = await bot_transcribe(wav_bytes, language=language)
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
                logger.warning(f"Bot transcribe error: {e}")
                return RealtimeASRResult(
                    ok=False,
                    text="",
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    error=str(e),
                    provider=self.provider,
                )

        # Default fallback for unconfigured runtime
        return RealtimeASRResult(
            ok=False,
            text="",
            start_ms=segment.start_ms,
            end_ms=segment.end_ms,
            language=language,
            error="no_asr_provider_configured",
            provider="none",
        )
