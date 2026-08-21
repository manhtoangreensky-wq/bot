import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest
from services.pricing_guide_content import public_hub_copy, public_copy_locale
from bot import (
    free_hub_main_keyboard,
    video_downloader_start_keyboard,
    video_downloader_choice_keyboard,
)

ALL_TEST_LOCALES = ["vi", "en", "zh", "ru", "ja", "ko", "es", "fr", "de", "pt", "hi", "ar", "th", "fil", "it", "id", "tr"]

def test_all_locales_have_required_free_hub_keys():
    required_keys = [
        "free_tools_label",
        "main_menu",
        "freehub_utilities",
        "freehub_translation",
        "freehub_video_downloader",
        "freehub_util_rate",
        "freehub_util_weather",
        "freehub_util_qr",
        "freehub_util_avatar",
        "freehub_back_freehub",
        "freehub_translate_another",
        "freehub_rate_another",
        "freehub_weather_another",
        "freehub_qr_another",
        "freehub_avatar_another",
    ]
    for loc in ALL_TEST_LOCALES:
        copy = public_hub_copy(loc)
        for k in required_keys:
            val = copy.get(k)
            assert val and isinstance(val, str), f"Locale '{loc}' missing required key '{k}'"
            assert len(val.strip()) > 0, f"Locale '{loc}' has empty value for key '{k}'"

def test_free_hub_main_keyboard_i18n():
    for loc in ["en", "zh", "ru", "ja", "ko"]:
        kb = free_hub_main_keyboard(loc)
        copy = public_hub_copy(loc)
        main_button = kb.inline_keyboard[-1][0]
        assert main_button.callback_data == "menu|main"
        assert copy["main_menu"] in main_button.text
        if loc != "vi":
            assert "Menu chính" not in main_button.text

def test_video_downloader_keyboards_i18n():
    for loc in ["en", "zh", "ru"]:
        copy = public_hub_copy(loc)
        kb_start = video_downloader_start_keyboard(loc)
        
        callbacks = [btn.callback_data for row in kb_start.inline_keyboard for btn in row]
        assert "freehub|main" in callbacks
        assert "menu|main" in callbacks
        assert "menu|main_video" in callbacks

        for row in kb_start.inline_keyboard:
            for btn in row:
                if btn.callback_data == "freehub|main":
                    assert copy["free_tools_label"] in btn.text
                elif btn.callback_data == "menu|main":
                    assert copy["main_menu"] in btn.text

def test_non_vietnamese_locales_no_vietnamese_in_freehub_keys():
    vietnamese_markers = ["Công cụ miễn phí", "Menu chính", "Tỷ giá", "Tiện ích", "Dịch thuật"]
    for loc in ["en", "zh", "ru", "ja", "ko", "es", "fr", "de"]:
        copy = public_hub_copy(loc)
        for k in ["free_tools_label", "main_menu", "freehub_utilities", "freehub_translation"]:
            val = copy[k]
            for marker in vietnamese_markers:
                assert marker != val, f"Locale '{loc}' key '{k}' has unlocalized Vietnamese string '{val}'"
