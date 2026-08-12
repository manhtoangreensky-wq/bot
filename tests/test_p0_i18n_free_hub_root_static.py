"""Source-only contract for the localized Free Tools root hub.

This test deliberately avoids importing ``bot`` or production services: those
modules can initialize unrelated runtime integrations.  It verifies only the
customer-facing copy and the existing callback layout.
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

FREE_HUB_FIELDS = (
    "freehub_enable_ai_chatbot",
    "freehub_meta",
    "freehub_caption",
    "freehub_ideas",
    "freehub_prompts",
    "freehub_library",
    "freehub_publish_package",
    "freehub_notes_docs",
    "freehub_save_temp_media",
    "freehub_voice_subdub_script",
    "freehub_music_sfx_ideas",
)

SCRIPT_RANGES = {
    "zh": r"[\u3400-\u9fff]",
    "ko": r"[\uac00-\ud7af]",
    "ja": r"[\u3040-\u30ff\u3400-\u9fff]",
    "th": r"[\u0e00-\u0e7f]",
    "ru": r"[\u0400-\u04ff]",
    "ar": r"[\u0600-\u06ff]",
    "hi": r"[\u0900-\u097f]",
}


def _literal_mapping(name: str) -> dict:
    module = ast.parse(COPY_SOURCE)
    for statement in module.body:
        if not isinstance(statement, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in statement.targets):
            return ast.literal_eval(statement.value)
    raise AssertionError(f"missing literal mapping: {name}")


def _function_source(name: str) -> str:
    start = BOT_SOURCE.index(f"def {name}(")
    following = re.search(r"\n(?:async )?def ", BOT_SOURCE[start + 1 :])
    end = -1 if following is None else start + 1 + following.start()
    return BOT_SOURCE[start:] if end < 0 else BOT_SOURCE[start:end]


def test_free_hub_root_copy_is_direct_and_native_for_every_supported_locale():
    table = _literal_mapping("_PUBLIC_FREE_HUB_ROOT_COPY")
    english = table["en"]

    assert tuple(table) == SUPPORTED_LOCALES
    for locale in SUPPORTED_LOCALES:
        copy = table[locale]
        assert not [field for field in FREE_HUB_FIELDS if not str(copy.get(field) or "").strip()], (locale, copy)
        if locale != "en":
            assert copy["freehub_enable_ai_chatbot"] != english["freehub_enable_ai_chatbot"], locale
            assert copy["freehub_prompts"] != english["freehub_prompts"], locale

    for locale, pattern in SCRIPT_RANGES.items():
        text = "\n".join(table[locale][field] for field in FREE_HUB_FIELDS)
        assert re.search(pattern, text), locale


def test_free_hub_root_keyboard_uses_native_copy_without_changing_callbacks():
    table = _literal_mapping("_PUBLIC_FREE_HUB_ROOT_COPY")

    class Button:
        def __init__(self, text, callback_data=None, url=None, **_kwargs):
            self.text = text
            self.callback_data = callback_data
            self.url = url

    class Markup:
        def __init__(self, rows):
            self.inline_keyboard = rows

    def build_2col_keyboard(items, *, nav_main=False, **_kwargs):
        rows = [
            [Button(*item) for item in items[index:index + 2]]
            for index in range(0, len(items), 2)
        ]
        if nav_main:
            rows.append([Button("🏠 Main menu", callback_data="menu|main")])
        return Markup(rows)

    def public_copy(locale):
        copy = dict(table[locale])
        copy["main_menu"] = "Main menu"
        return copy

    namespace = {
        "InlineKeyboardButton": Button,
        "InlineKeyboardMarkup": Markup,
        "normalize_user_language": lambda locale: locale if locale in table else "en",
        "public_hub_copy": public_copy,
        "build_2col_keyboard": build_2col_keyboard,
    }
    exec(_function_source("free_hub_main_keyboard"), namespace)

    expected_callbacks = {
        "aichat|on",
        "freehub|meta",
        "freehub|caption",
        "freehub|ideas",
        "freehub|prompts",
        "freehub|library",
        "freehub|publish_package",
        "menu|main_memory",
        "freehub|upload",
        "freehub|hook",
        "freehub|lib_music",
        "menu|main",
    }
    for locale in SUPPORTED_LOCALES:
        markup = namespace["free_hub_main_keyboard"](locale)
        callbacks = {
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.callback_data
        }
        assert callbacks == expected_callbacks, locale
        labels = "\n".join(button.text for row in markup.inline_keyboard for button in row)
        assert table[locale]["freehub_enable_ai_chatbot"] in labels, locale
        assert table[locale]["freehub_prompts"] in labels, locale
