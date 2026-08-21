"""Source-only contract for localized Notes/Documents storage screens.

Only the status, cleanup and navigation presentation is covered here.  Storage
purchase, PayOS and persistence routes intentionally remain outside scope.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from services import pricing_guide_content as public_copy_module


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
COPY_SOURCE = (ROOT / "services" / "pricing_guide_content.py").read_text(encoding="utf-8")

SUPPORTED_LOCALES = (
    "vi", "en", "zh", "es", "pt", "fr", "de", "ja", "ko", "hi", "ar",
    "ru", "tr", "th", "fil", "it", "id",
)
STORAGE_FIELDS = (
    "storage_status_title",
    "storage_status_current_plan",
    "storage_status_free_plan",
    "storage_status_free_plus",
    "storage_status_notes",
    "storage_status_text_notes",
    "storage_status_files_media",
    "storage_status_total_used",
    "storage_status_ai_remaining",
    "storage_status_reminders_active",
    "storage_status_expand",
    "storage_status_near_quota",
    "storage_status_near_quota_body",
    "storage_addon_monthly_line",
    "storage_addon_custom_hint",
    "storage_cleanup_title",
    "storage_cleanup_body",
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


def test_storage_display_copy_is_direct_and_native_for_every_supported_locale():
    table = _literal_mapping("_PUBLIC_MEMORY_STORAGE_COPY")
    english = table["en"]

    assert tuple(table) == SUPPORTED_LOCALES
    for locale in SUPPORTED_LOCALES:
        copy = table[locale]
        assert not [field for field in STORAGE_FIELDS if not str(copy.get(field) or "").strip()], locale
        if locale != "en":
            assert copy["storage_cleanup_body"] != english["storage_cleanup_body"], locale
            assert copy["storage_status_near_quota_body"] != english["storage_status_near_quota_body"], locale

    for locale, pattern in SCRIPT_RANGES.items():
        assert re.search(pattern, "\n".join(table[locale][field] for field in STORAGE_FIELDS)), locale


def test_storage_display_renderers_use_copy_and_do_not_rewire_payment_or_persistence():
    renderer_names = (
        "memory_storage_display_addon_lines",
        "memory_status_text",
        "memory_storage_cleanup_text",
        "memory_storage_nav_keyboard",
    )
    protected = ("PayOS", "db_connect", "record_credit_event", "grant_memory_storage", "web_billing")

    for name in renderer_names:
        source = _function_source(name)
        assert "public_hub_copy" in source, name
        assert not [marker for marker in protected if marker in source], (name, source)

    menu = _function_source("localized_menu_content")
    assert "memory_status_text(user_id or \"__customer__\", lang)" in menu
    assert "memory_storage_cleanup_text(lang)" in menu

    command = _async_function_source("cmd_memory_status")
    assert "memory_status_text(uid, lang)" in command
    assert "lang = user_ui_lang(uid)" in command


def test_storage_navigation_keeps_existing_callbacks_and_uses_locale_copy():
    table = _literal_mapping("_PUBLIC_MEMORY_STORAGE_COPY")

    class Button:
        def __init__(self, text, callback_data=None, **_kwargs):
            self.text = text
            self.callback_data = callback_data

    class Markup:
        def __init__(self, rows):
            self.inline_keyboard = rows

    def public_copy(locale):
        copy = dict(table[locale])
        root = public_copy_module.public_hub_copy(locale)
        copy.update(root)
        return copy

    namespace = {
        "InlineKeyboardButton": Button,
        "InlineKeyboardMarkup": Markup,
        "normalize_user_language": lambda locale: locale if locale in table else "en",
        "public_hub_copy": public_copy,
    }
    exec(_function_source("memory_storage_nav_keyboard"), namespace)

    expected = {
        "menu|memory_storage_addon",
        "menu|memory_storage_cleanup",
        "menu|memory_storage_status",
        "menu|main_memory",
        "menu|main",
    }
    for locale in SUPPORTED_LOCALES:
        markup = namespace["memory_storage_nav_keyboard"](locale)
        callbacks = {
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.callback_data
        }
        assert callbacks == expected, locale
        labels = "\n".join(button.text for row in markup.inline_keyboard for button in row)
        copy = public_copy_module.public_hub_copy(locale)
        assert copy["notes_add_storage"] in labels, locale
        assert copy["notes_clean_files"] in labels, locale
