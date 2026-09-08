"""Customer-facing SubDub information must match the live product contract."""

from __future__ import annotations

import bot
from services.pricing_guide_content import (
    PUBLIC_COPY_LOCALES,
    public_subdub_auto_pricing_line,
    public_subdub_deep_copy,
)


def _button_map(markup) -> dict[str, str]:
    return {
        str(button.callback_data or ""): str(button.text or "")
        for row in markup.inline_keyboard
        for button in row
    }


def test_subdub_menu_names_every_live_lane_and_current_output_contract():
    text = bot.video_dubbing_menu_text("vi", "translation")

    for expected in (
        "Tạo phụ đề tự động",
        "Dịch phụ đề video",
        "Lồng tiếng video",
        "Phụ đề + Lồng tiếng",
        "MP4",
        "SRT",
        "2 người nói",
        "3–8 người nói",
    ):
        assert expected in text
    assert "tối đa 16" not in text


def test_subdub_voice_picker_names_each_current_voice_service(monkeypatch):
    monkeypatch.setattr(bot, "subdub_auto_provider_capacity_ready", lambda: True)

    for locale in sorted(PUBLIC_COPY_LOCALES):
        copy = public_subdub_deep_copy(locale)
        buttons = _button_map(
            bot.video_dubbing_voice_keyboard(
                locale,
                {
                    "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
                    "target_language": "English",
                },
            )
        )

        assert buttons["videodub|voice|default_female"] == copy["voice_default_female"]
        assert buttons["videodub|voice|default_male"] == copy["voice_default_male"]
        assert buttons["videodub|voice|auto_speaker_gender"] == copy["voice_auto_speaker"]
        assert buttons["videodub|voice|auto_multi_speaker"] == copy["voice_auto_multi_speaker"]
        assert buttons["videodub|voice_create"] == copy["voice_custom_create"]
        assert len(set(buttons.values())) == len(buttons.values())


def test_all_locales_describe_exact_two_and_three_to_eight_auto_lanes():
    for locale in sorted(PUBLIC_COPY_LOCALES):
        copy = public_subdub_deep_copy(locale)
        current_copy = " ".join(
            (
                copy["menu_body"],
                copy["voice_auto_speaker"],
                copy["voice_auto_multi_speaker"],
                copy["voice_auto_explanation"],
            )
        )

        assert all(marker in current_copy for marker in ("2", "3", "8"))
        assert "16" not in current_copy
        assert copy["output_mp4_srt"]


def test_subdub_pricing_names_auto_two_and_auto_multi_separately():
    for locale in sorted(PUBLIC_COPY_LOCALES):
        copy = public_subdub_deep_copy(locale)
        text = bot.video_dubbing_pricing_text(locale)

        assert copy["voice_auto_speaker"] in text
        assert copy["voice_auto_multi_speaker"] in text
        assert text.count(copy["voice_auto_price_rule"]) == 2
        assert "16" not in text
        guide_line = public_subdub_auto_pricing_line(locale)
        assert copy["voice_auto_speaker"] in guide_line
        assert copy["voice_auto_multi_speaker"] in guide_line


def test_subdub_confirmation_distinguishes_primary_mp4_and_optional_srt():
    states = {
        bot.VIDEO_SUBTITLE_MODE_CREATE: {},
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE: {"target_language": "English"},
        bot.VIDEO_SUBTITLE_MODE_DUB: {
            "target_language": "English",
            "voice_style": "Giọng nữ mặc định",
        },
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB: {
            "target_language": "English",
            "voice_style": "Giọng nữ mặc định",
        },
    }
    copy = public_subdub_deep_copy("vi")

    for mode, fields in states.items():
        text = bot.video_dubbing_confirm_text(
            {"mode": mode, "source_file_id": "fixture", **fields},
            "vi",
        )
        assert "MP4" in text
        if mode == bot.VIDEO_SUBTITLE_MODE_DUB:
            assert copy["output_mp4_srt"] not in text
        else:
            assert copy["output_mp4_srt"] in text


def test_subdub_exact_price_screen_names_auto_two_or_auto_multi():
    copy = public_subdub_deep_copy("vi")
    base = {
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "auto_exact_receipt": {
            "actual_billable_words": 100,
            "actual_auto_xu": 50,
            "actual_subtitle_xu": 0,
            "actual_total_xu": 50,
        },
    }

    auto_two = bot.subdub_auto_exact_confirmation_text(base, "vi")
    auto_multi = bot.subdub_auto_exact_confirmation_text(
        {**base, "auto_speaker_lane": "multi"},
        "vi",
    )

    assert copy["voice_auto_speaker"] in auto_two
    assert copy["voice_auto_multi_speaker"] in auto_multi
    assert copy["voice_auto_multi_speaker"] not in auto_two


def test_subdub_catalog_is_identical_for_admin_and_customer():
    customer_text, customer_markup = bot.localized_menu_content(
        "translation_video_factory",
        False,
        "vi",
    )
    admin_text, admin_markup = bot.localized_menu_content(
        "translation_video_factory",
        True,
        "vi",
    )

    assert admin_text == customer_text
    assert _button_map(admin_markup) == _button_map(customer_markup)
