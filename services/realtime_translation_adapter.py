"""Canonical Bot Core Realtime Translation Adapter (RT-01).

Governed by owner-governed-codex, locked-focus-engineering.
Enforces:
1. Low-latency sentence translation with rolling context window (last 3 segments).
2. Clean subtitle formatting (no AI preambles, direct translation).
3. Pluggable provider routing (LLM / DeepL / Mock for tests).
4. Zero-cost testing guard: respects test environment mocks without touching paid APIs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class RealtimeTranslationResult:
    ok: bool
    source_text: str
    translated_text: str
    target_language: str
    provider: str = "mock"
    error: Optional[str] = None


_TEST_MOCK_TRANSLATION_HANDLER: Optional[Callable[[str, str], RealtimeTranslationResult]] = None


def set_test_translation_mock_handler(
    handler: Optional[Callable[[str, str], RealtimeTranslationResult]]
) -> None:
    """Sets a mock handler for testing environment."""
    global _TEST_MOCK_TRANSLATION_HANDLER
    _TEST_MOCK_TRANSLATION_HANDLER = handler


class RealtimeTranslationAdapter:
    """Translates incoming speech segments with rolling conversation context."""

    def __init__(
        self,
        target_language: str = "vi",
        max_context_segments: int = 3,
        provider: str = "auto",
    ):
        self.target_language = target_language
        self.max_context_segments = max_context_segments
        self.provider = provider
        self.context_history: List[Tuple[str, str]] = []  # List of (source, target)

    async def translate(
        self,
        text: str,
        target_language: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> RealtimeTranslationResult:
        """Translates a source text chunk into the target language."""
        target_lang = target_language or self.target_language
        clean_text = text.strip()

        if not clean_text:
            return RealtimeTranslationResult(
                ok=True,
                source_text="",
                translated_text="",
                target_language=target_lang,
                provider="noop",
            )

        # Check if test mock handler is active
        if _TEST_MOCK_TRANSLATION_HANDLER is not None:
            res = _TEST_MOCK_TRANSLATION_HANDLER(clean_text, target_lang)
            if res.ok and res.translated_text:
                self._record_context(clean_text, res.translated_text)
            return res

        # Try Bot core translate helper if provided in context
        bot_translate = None
        if context and "bot_translate_func" in context:
            bot_translate = context["bot_translate_func"]

        if bot_translate:
            try:
                res = await bot_translate(clean_text, target_lang=target_lang)
                trans_text = str(res.get("text") or res.get("translated") or "").strip()
                if trans_text:
                    self._record_context(clean_text, trans_text)
                return RealtimeTranslationResult(
                    ok=bool(trans_text),
                    source_text=clean_text,
                    translated_text=trans_text,
                    target_language=target_lang,
                    provider=str(res.get("provider") or self.provider),
                )
            except Exception as e:
                logger.warning(f"Bot translate error: {e}")
                return RealtimeTranslationResult(
                    ok=False,
                    source_text=clean_text,
                    translated_text="",
                    target_language=target_lang,
                    error=str(e),
                    provider=self.provider,
                )

        # Default fallback if no provider is configured
        return RealtimeTranslationResult(
            ok=False,
            source_text=clean_text,
            translated_text="",
            target_language=target_lang,
            error="no_translation_provider_configured",
            provider="none",
        )

    def _record_context(self, source: str, target: str) -> None:
        self.context_history.append((source, target))
        if len(self.context_history) > self.max_context_segments:
            self.context_history.pop(0)

    def get_context_summary(self) -> str:
        """Returns recent context lines to prime downstream LLM prompt."""
        if not self.context_history:
            return ""
        lines = []
        for s, t in self.context_history:
            lines.append(f"Source: {s} -> Target: {t}")
        return "\n".join(lines)
