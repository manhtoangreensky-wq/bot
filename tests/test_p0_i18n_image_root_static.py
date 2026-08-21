"""Source-only contract for the localized Image root screen.

The real Image engine, provider, job and credit boundaries are intentionally
not imported.  This verifies only the root copy and stable menu callbacks.
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


def test_image_root_copy_is_direct_and_native_for_every_supported_locale():
    table = _literal_mapping("_PUBLIC_IMAGE_ROOT_COPY")
    english = table["en"]

    assert tuple(table) == SUPPORTED_LOCALES
    for locale in SUPPORTED_LOCALES:
        copy = table[locale]
        assert str(copy.get("image_menu_title") or "").strip(), locale
        assert str(copy.get("image_menu_body") or "").strip(), locale
        if locale != "en":
            assert copy["image_menu_body"] != english["image_menu_body"], locale

    for locale, pattern in SCRIPT_RANGES.items():
        text = f"{table[locale]['image_menu_title']}\n{table[locale]['image_menu_body']}"
        assert re.search(pattern, text), locale


def test_image_root_renderer_and_keyboard_keep_presentation_only_callbacks():
    table = _literal_mapping("_PUBLIC_IMAGE_ROOT_COPY")
    renderer = _function_source("image_menu_v5_text")
    keyboard = _function_source("main_image_keyboard")

    assert "public_hub_copy" in renderer
    assert '"create_media|quick_image"' in keyboard
    assert '"menu|image_prompt_start"' in keyboard
    assert '"imgtool|edit_ai_start"' in keyboard
    assert '"menu|image_edit_start"' in keyboard
    assert "call_image_edit_provider" not in renderer + keyboard
    assert "spend_media_factory_after_success_or_reply" not in renderer + keyboard
