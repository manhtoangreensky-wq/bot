"""Source-only contract for the localized Feedback category prompt.

The test intentionally avoids importing ``bot``.  Feedback persistence and
ticket routing remain outside this presentation-only contract.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
COPY_SOURCE = (ROOT / "services" / "pricing_guide_content.py").read_text(encoding="utf-8")

SUPPORTED_LOCALES = (
    "vi", "en", "zh", "es", "pt", "fr", "de", "ja", "ko", "hi", "ar",
    "ru", "tr", "th", "fil", "it", "id",
)
PROMPT_FIELDS = (
    "feedback_prompt_title",
    "feedback_prompt_body",
    "feedback_prompt_back",
)
SCRIPT_RANGES = {
    "zh": r"[\u3400-\u9fff]", "ko": r"[\uac00-\ud7af]",
    "ja": r"[\u3040-\u30ff\u3400-\u9fff]", "th": r"[\u0e00-\u0e7f]",
    "ru": r"[\u0400-\u04ff]", "ar": r"[\u0600-\u06ff]", "hi": r"[\u0900-\u097f]",
}


def _literal_mapping(name: str) -> dict:
    module = ast.parse(COPY_SOURCE)
    for statement in module.body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in statement.targets
        ):
            return ast.literal_eval(statement.value)
    raise AssertionError(f"missing literal mapping: {name}")


def _function_source(name: str) -> str:
    start = BOT_SOURCE.index(f"def {name}(")
    following = re.search(r"\n(?:async )?def ", BOT_SOURCE[start + 1 :])
    end = -1 if following is None else start + 1 + following.start()
    return BOT_SOURCE[start:] if end < 0 else BOT_SOURCE[start:end]


def _async_function_source(name: str) -> str:
    start = BOT_SOURCE.index(f"async def {name}(")
    following = re.search(r"\n(?=(?:async )?def |@)", BOT_SOURCE[start + 1 :])
    end = -1 if following is None else start + 1 + following.start()
    return BOT_SOURCE[start:] if end < 0 else BOT_SOURCE[start:end]


def test_feedback_prompt_has_direct_native_copy_for_every_supported_locale():
    table = _literal_mapping("_PUBLIC_FEEDBACK_PROMPT_COPY")
    english = table["en"]

    assert tuple(table) == SUPPORTED_LOCALES
    for locale in SUPPORTED_LOCALES:
        copy = table[locale]
        assert not [field for field in PROMPT_FIELDS if not str(copy.get(field) or "").strip()], locale
        if locale != "en":
            assert copy["feedback_prompt_body"] != english["feedback_prompt_body"], locale

    for locale, pattern in SCRIPT_RANGES.items():
        assert re.search(pattern, "\n".join(table[locale][field] for field in PROMPT_FIELDS)), locale


def test_feedback_prompt_uses_copy_only_and_keeps_ticket_callback_contract():
    renderer = _function_source("feedback_message_prompt")
    handler = _async_function_source("handle_feedback_callback")

    assert "public_hub_copy" in renderer
    assert "FEEDBACK_CATEGORY_LABELS.get" not in renderer
    for key in PROMPT_FIELDS:
        assert key in renderer or key in handler, key

    for callback in (
        "feedback|start", "feedback|cancel", "feedback|cat|", "menu|main",
    ):
        assert callback in handler, callback
    for protected in (
        "set_feedback_pending", "clear_feedback_pending", "clear_support_ticket_pending",
    ):
        assert protected in handler, protected
