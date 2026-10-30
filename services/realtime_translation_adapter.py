"""Canonical Bot Core Realtime Translation Adapter (RT-01 / RT-FIX1).

Governed by owner-governed-codex, locked-focus-engineering.
Enforces:
1. Low-latency sentence translation with rolling context window (last 3 segments).
2. Canonical binding to Bot translation primitive (bot.translate_subtitle_text) WITHOUT requiring request-time context dictionary.
3. Zero-cost testing guard: supports dependency injection / mock hook without external provider network calls.
4. Clean subtitle formatting.
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
_CANONICAL_TRANSLATION_PRIMITIVE: Optional[Callable] = None


def set_test_translation_mock_handler(
    handler: Optional[Callable[[str, str], RealtimeTranslationResult]]
) -> None:
    """Sets a mock handler for testing environment."""
    global _TEST_MOCK_TRANSLATION_HANDLER
    _TEST_MOCK_TRANSLATION_HANDLER = handler


def set_canonical_translation_primitive(primitive: Optional[Callable]) -> None:
    """Dependency injection hook for binding the canonical translation primitive."""
    global _CANONICAL_TRANSLATION_PRIMITIVE
    _CANONICAL_TRANSLATION_PRIMITIVE = primitive


def get_canonical_translation_primitive() -> Optional[Callable]:
    """Resolves and returns the canonical translation primitive without blocking on cold module imports."""
    global _CANONICAL_TRANSLATION_PRIMITIVE
    if _CANONICAL_TRANSLATION_PRIMITIVE is not None:
        return _CANONICAL_TRANSLATION_PRIMITIVE
    import sys
    if "bot" in sys.modules:
        bot_mod = sys.modules["bot"]
        if hasattr(bot_mod, "translate_subtitle_text"):
            _CANONICAL_TRANSLATION_PRIMITIVE = bot_mod.translate_subtitle_text
            return _CANONICAL_TRANSLATION_PRIMITIVE
    return None


class RealtimeTranslationAdapter:
    """Translates incoming speech segments with rolling conversation context."""

    def __init__(
        self,
        target_language: str = "vi",
        max_context_segments: int = 3,
        provider: str = "auto",
        translation_primitive: Optional[Callable] = None,
    ):
        self.target_language = target_language
        self.max_context_segments = max_context_segments
        self.provider = provider
        self.context_history: List[Tuple[str, str]] = []
        self._primitive = translation_primitive

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

        # Resolve canonical translation primitive
        trans_func = self._primitive
        if trans_func is None and context and "bot_translate_func" in context:
            trans_func = context["bot_translate_func"]
        if trans_func is None:
            trans_func = get_canonical_translation_primitive()

        if trans_func is not None:
            try:
                res = await trans_func(clean_text, target_lang=target_lang)
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
                logger.warning(f"Canonical translation execution error: {e}")
                return RealtimeTranslationResult(
                    ok=False,
                    source_text=clean_text,
                    translated_text="",
                    target_language=target_lang,
                    error=str(e),
                    provider=self.provider,
                )

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
