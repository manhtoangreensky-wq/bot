"""Focused regression contract for direct native public root-flow copy.

These tests deliberately execute no bot import: importing the production module
can initialize unrelated runtime services.  They protect presentation only.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from services import pricing_guide_content as public_copy


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
SUPPORTED_LOCALES = (
    "vi", "en", "zh", "es", "pt", "fr", "de", "ja", "ko", "hi", "ar",
    "ru", "tr", "th", "fil", "it", "id",
)

# These are the texts used when a customer leaves the localized Start hub.
# They must be direct values for the selected locale, not a vi/en fallback.
ROOT_COPY_FIELDS = (
    "free_title",
    "free_body",
    "audio_title",
    "audio_body",
    "feedback_title",
    "feedback_body",
    "support_title",
    "support_body",
    "memory_title",
    "memory_body",
    "docs_title",
    "docs_body",
    "translation_title",
    "translation_body",
    "translation_language_title",
    "translation_language_body",
    "audio_media_title",
    "audio_media_body",
    "profile_title",
    "profile_body",
    "video_menu_title",
    "video_menu_body",
)

ROOT_ACTION_FIELDS = (
    "image_quick",
    "image_prompt_from_image",
    "image_ai_edit",
    "image_edit",
    "notes_create",
    "notes_saved",
    "notes_reminder",
    "notes_save_document",
    "notes_search",
    "notes_delete",
    "notes_storage",
    "notes_add_storage",
    "notes_clean_files",
    "docs_tools",
    "docs_pdf_to_word",
    "docs_image_to_pdf",
    "docs_compress_pdf",
    "docs_split_pdf",
    "docs_merge_pdf",
    "docs_all_tools",
    "translation_language",
    "translation_subtitle_dubbing",
    "translation_text",
    "translation_file",
    "translation_audio",
    "translation_conversation",
    "translation_two_way",
    "translation_auto",
    "translation_languages",
    "translation_stop",
    "feedback_payment_topup",
    "feedback_image_error",
    "feedback_video_error",
    "feedback_document_pdf",
    "feedback_package_combo",
    "feedback_refund",
    "feedback_feature_request",
    "feedback_other",
)

SUPPORT_PROFILE_FIELDS = (
    "support_admin",
    "support_ticket",
    "support_my_tickets",
    "support_auto",
    "support_premium",
    "support_custom_bot",
    "support_consult",
    "profile_topup",
    "profile_pricing",
    "profile_packages",
    "profile_membership",
    "profile_xu_guide",
    "profile_referral_link",
    "profile_referral_stats",
    "profile_referral_policy",
    "profile_change_language",
    "profile_back_account",
    "profile_id",
    "profile_tier",
    "profile_balance",
    "profile_detail_hint",
    "profile_unlimited",
    "profile_remaining_uses",
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


def test_every_supported_locale_has_direct_native_root_flow_copy():
    english = public_copy.public_hub_copy("en")
    required = ROOT_COPY_FIELDS + ROOT_ACTION_FIELDS

    for locale in SUPPORTED_LOCALES:
        copy = public_copy.public_hub_copy(locale)
        missing = [field for field in required if not str(copy.get(field) or "").strip()]
        assert not missing, (locale, missing)

        if locale != "en":
            # A customer screen must not silently be the English body again.
            assert copy["free_body"] != english["free_body"], locale
            assert copy["translation_body"] != english["translation_body"], locale
            assert copy["video_menu_body"] != english["video_menu_body"], locale

    for locale, pattern in SCRIPT_RANGES.items():
        copy = public_copy.public_hub_copy(locale)
        body = "\n".join(copy[field] for field in ROOT_COPY_FIELDS)
        assert re.search(pattern, body), locale


def test_public_root_renderers_are_connected_to_the_native_copy_owner():
    # Source-level contract keeps this narrow: handlers/routes remain untouched.
    renderers = (
        "free_hub_main_text",
        "feedback_start_text",
        "main_memory_keyboard",
        "main_docs_keyboard",
        "main_image_keyboard",
        "main_audio_keyboard",
        "translation_menu_text",
        "translation_menu_keyboard",
        "translation_language_hub_text",
        "translation_language_hub_keyboard",
        "menu_text_main_video_i18n",
        "menu_text_main_memory_i18n",
        "menu_text_main_docs_i18n",
        "menu_text_main_audio_i18n",
        "menu_text_main_music_i18n",
    )
    for name in renderers:
        assert "public_hub_copy" in _function_source(name), name


def test_root_flow_copy_keeps_existing_callbacks_and_localizes_every_supported_locale():
    class Button:
        def __init__(self, text, callback_data=None, **_kwargs):
            self.text = text
            self.callback_data = callback_data

    class Markup:
        def __init__(self, rows):
            self.inline_keyboard = rows

    source = BOT_SOURCE
    namespace = {
        "__builtins__": __builtins__,
        "InlineKeyboardButton": Button,
        "InlineKeyboardMarkup": Markup,
        "public_hub_copy": public_copy.public_hub_copy,
        "public_support_consult_choices": public_copy.public_support_consult_choices,
        "normalize_user_language": public_copy.public_copy_locale,
        "is_admin_user": lambda _user_id: False,
        "product_context_callback": lambda *parts: "music_quick|" + "|".join(parts[1:]),
        "PRODUCT_CONTEXT_SHOWROOM": "showroom",
    }
    for name in (
        "build_2col_keyboard",
        "main_memory_keyboard",
        "main_docs_keyboard",
        "main_image_keyboard",
        "main_audio_keyboard",
        "translation_menu_keyboard",
        "translation_language_hub_keyboard",
    ):
        exec(_function_source(name), namespace)

    namespace["is_admin_user"] = lambda _user_id: True
    for locale in SUPPORTED_LOCALES:
        copy = public_copy.public_hub_copy(locale)
        memory = namespace["main_memory_keyboard"](locale, user_id=1)
        archive_buttons = [
            button
            for row in memory.inline_keyboard
            for button in row
            if button.callback_data == "menu|internal_archive"
        ]
        assert len(archive_buttons) == 1, locale
        assert copy["internal_archive"] in archive_buttons[0].text, locale

    expected = {
        "main_memory_keyboard": {"memory|create", "memory|list", "menu|main_docs", "menu|main"},
        "main_docs_keyboard": {"menu|hint_doc_pdf_to_word", "menu|hint_doc_image_to_pdf", "menu|doc_tools", "menu|main_memory", "menu|main"},
        "main_image_keyboard": {"create_media|quick_image", "menu|image_prompt_start", "imgtool|edit_ai_start", "menu|image_edit_start", "menu|main"},
        "main_audio_keyboard": {"music_quick|showroom|voice_hub", "music_quick|showroom|music_hub", "menu|main"},
        "translation_menu_keyboard": {"menu|translation_language_hub", "menu|translation_video_factory", "menu|main"},
        "translation_language_hub_keyboard": {"menu|translation_text", "menu|translation_media_file", "menu|translation_media_audio", "menu|translation_live_conversation", "menu|translation_two_way", "menu|translation_auto_target", "menu|translation_language", "menu|translation_stop_session", "menu|translate", "menu|main"},
    }
    for locale in SUPPORTED_LOCALES:
        copy = public_copy.public_hub_copy(locale)
        for name, callbacks_expected in expected.items():
            markup = namespace[name](locale)
            callbacks = {
                button.callback_data
                for row in markup.inline_keyboard
                for button in row
                if button.callback_data
            }
            assert callbacks_expected <= callbacks, (locale, name, callbacks)
            assert any(copy["main_menu"] in button.text for row in markup.inline_keyboard for button in row), (locale, name)

        memory = namespace["main_memory_keyboard"](locale)
        assert any(copy["notes_create"] in button.text for row in memory.inline_keyboard for button in row)
        translation = namespace["translation_menu_keyboard"](locale)
        assert any(copy["translation_language"] in button.text for row in translation.inline_keyboard for button in row)


def test_video_public_label_uses_native_menu_copy_without_touching_routes():
    route = {
        "label_vi": "🎬 Video AI chân thật",
        "label_en": "🎬 Real AI Video",
        "label_zh": "🎬 真实 AI 视频",
    }
    namespace = {
        "__builtins__": __builtins__,
        "video_public_route_for_tool": lambda _tool_id: route,
        "normalize_user_language": public_copy.public_copy_locale,
        "public_hub_copy": public_copy.public_hub_copy,
        "public_video_menu_label": public_copy.public_video_menu_label,
    }
    exec(_function_source("video_public_menu_label"), namespace)
    for locale in ("ja", "ko", "es"):
        assert namespace["video_public_menu_label"]("video_ai_real", locale) == public_copy.public_video_menu_label(
            "video_ai_real", locale
        )

    # Unknown legacy routes retain their existing label instead of being given a
    # guessed translation. This is presentation-only and cannot alter routing.
    assert namespace["video_public_menu_label"]("unknown_legacy_tool", "ja") == route["label_en"]


def test_every_visible_video_root_action_has_direct_native_display_copy():
    visible_tool_ids = (
        "video_trend",
        "video_ai_real",
        "script_image_video",
        "frame_video_local",
        "self_shot_scene_change",
        "storyboard_prompt",
        "multi_scene_film",
        "video_idea",
        "video_local_edit",
        "video_downloader",
        "video_edit_planning",
        "video_guide",
    )
    for locale in SUPPORTED_LOCALES:
        for tool_id in visible_tool_ids:
            assert public_copy.public_video_menu_label(tool_id, locale), (locale, tool_id)

    assert public_copy.public_video_menu_label("video_ai_real", "ja") == "🎬 リアルなAI動画"
    assert public_copy.public_video_menu_label("video_ai_real", "ko") == "🎬 사실적인 AI 동영상"
    assert public_copy.public_video_menu_label("video_ai_real", "es") == "🎬 Vídeo IA realista"


def test_support_and_profile_roots_have_direct_native_copy_with_unchanged_callbacks():
    class Button:
        def __init__(self, text, callback_data=None, **_kwargs):
            self.text = text
            self.callback_data = callback_data

    class Markup:
        def __init__(self, rows):
            self.inline_keyboard = rows

    namespace = {
        "__builtins__": __builtins__,
        "InlineKeyboardButton": Button,
        "InlineKeyboardMarkup": Markup,
        "public_hub_copy": public_copy.public_hub_copy,
        "normalize_user_language": public_copy.public_copy_locale,
        # The legacy branches use this generic stand-in. A native renderer must
        # not surface it for a supported customer locale.
        "ui_text": lambda _lang, _key: "ENGLISH FALLBACK",
    }
    for name in (
        "human_support_text",
        "human_support_keyboard",
        "main_profile_keyboard",
        "profile_child_keyboard",
        "menu_text_main_profile_i18n",
    ):
        exec(_function_source(name), namespace)

    expected_support_callbacks = {
        "support|admin_contact",
        "support|ticket",
        "ticket|mine",
        "support|premium",
        "support|bot",
        "support|consult",
        "support|cskh_auto",
        "menu|main",
    }
    expected_profile_callbacks = {
        "menu|main_topup",
        "pricing|main",
        "menu|profile_packages",
        "pricing|member",
        "menu|guide_credits",
        "menu|support",
        "menu|profile_ref_link",
        "menu|profile_ref_stats",
        "menu|profile_ref_policy",
        "back_lang",
        "menu|main",
    }

    english = public_copy.public_hub_copy("en")
    for locale in SUPPORTED_LOCALES:
        copy = public_copy.public_hub_copy(locale)
        missing = [key for key in SUPPORT_PROFILE_FIELDS if not str(copy.get(key) or "").strip()]
        assert not missing, (locale, missing)
        if locale != "en":
            assert copy["support_premium"] != english["support_premium"], locale
            assert copy["profile_detail_hint"] != english["profile_detail_hint"], locale

        support_text = namespace["human_support_text"](locale)
        assert copy["support_title"] in support_text, locale
        support_markup = namespace["human_support_keyboard"](locale)
        support_callbacks = {
            button.callback_data
            for row in support_markup.inline_keyboard
            for button in row
            if button.callback_data
        }
        assert expected_support_callbacks <= support_callbacks, (locale, support_callbacks)
        assert any(copy["support_ticket"] in button.text for row in support_markup.inline_keyboard for button in row)
        assert any(copy["support_premium"] in button.text for row in support_markup.inline_keyboard for button in row)

        profile_text = namespace["menu_text_main_profile_i18n"]("customer", locale)
        assert copy["profile_title"] in profile_text, locale
        assert copy["profile_body"] in profile_text, locale
        profile_markup = namespace["main_profile_keyboard"](locale)
        profile_callbacks = {
            button.callback_data
            for row in profile_markup.inline_keyboard
            for button in row
            if button.callback_data
        }
        assert expected_profile_callbacks <= profile_callbacks, (locale, profile_callbacks)
        assert any(copy["profile_topup"] in button.text for row in profile_markup.inline_keyboard for button in row)
        assert any(copy["profile_change_language"] in button.text for row in profile_markup.inline_keyboard for button in row)

        child_markup = namespace["profile_child_keyboard"](locale)
        assert any(copy["profile_back_account"] in button.text for row in child_markup.inline_keyboard for button in row)
        assert any(copy["main_menu"] in button.text for row in child_markup.inline_keyboard for button in row)


def test_support_root_handler_passes_the_selected_locale_to_its_renderer():
    """The real menu callback must not discard the locale at the Support edge."""
    handler = _function_source("handle_menu_callback")
    support_start = _function_source("handle_human_support_callback")
    assert "human_support_text(lang)" in handler
    assert "human_support_keyboard(lang)" in handler
    assert "lang = normalize_user_language(get_user_language(uid)) or \"vi\"" in support_start
    assert "human_support_text(lang)" in support_start
    assert "human_support_keyboard(lang)" in support_start


def test_support_live_entrypoints_forward_active_locale_to_root_renderer():
    """Every public Support entry must render with the customer's saved locale."""
    for name in ("handle_menu_callback", "handle_human_support_callback", "cmd_support"):
        source = _function_source(name)
        assert "human_support_text(lang)" in source, name
        assert "human_support_keyboard(lang)" in source, name


def test_support_child_routes_are_native_copy_only_and_keep_callbacks():
    """Support child renderers must accept a locale without changing ticket routes."""
    child_names = (
        "support_cskh_auto_text",
        "support_cskh_auto_keyboard",
        "support_admin_contact_text",
        "support_admin_contact_keyboard",
        "support_general_ticket_prompt",
        "support_premium_text",
        "support_premium_keyboard",
        "support_custom_bot_text",
        "support_custom_bot_keyboard",
        "support_consult_keyboard",
        "support_custom_bot_detail_text",
        "support_custom_bot_detail_keyboard",
        "support_consult_detail_text",
        "support_consult_detail_keyboard",
        "support_lead_input_text",
        "support_flow_back_keyboard",
    )
    for name in child_names:
        source = _function_source(name)
        assert "public_hub_copy" in source, name
        assert "lang: str = \"vi\"" in source, name

    handler = _function_source("handle_human_support_callback")
    # Dispatcher branches compare the parsed action; callback payloads remain
    # declared by the existing keyboards and are covered separately below.
    for action in ("admin_contact", "ticket", "premium", "bot", "consult", "cskh_auto"):
        assert f'action == "{action}"' in handler
    for render_call in (
        "support_admin_contact_text(lang)",
        "support_admin_contact_keyboard(lang)",
        "support_cskh_auto_text(lang)",
        "support_cskh_auto_keyboard(lang)",
        "support_general_ticket_prompt(lang)",
        "support_premium_text(lang)",
        "support_premium_keyboard(lang)",
        "support_custom_bot_text(lang)",
        "support_custom_bot_keyboard(lang)",
        "support_consult_keyboard(lang)",
        "support_custom_bot_detail_text(bot_type, lang)",
        "support_custom_bot_detail_keyboard(bot_type, lang)",
        "support_consult_detail_text(service_type, lang)",
        "support_consult_detail_keyboard(service_type, lang)",
        "support_lead_input_text(\"premium_lead\", selected, lang)",
    ):
        assert render_call in handler

def test_support_child_copy_has_direct_native_text_for_every_supported_locale():
    required = (
        "support_contact_title",
        "support_contact_body",
        "support_auto_title",
        "support_auto_body",
        "support_ticket_prompt_title",
        "support_ticket_prompt_body",
        "support_premium_body",
        "support_custom_body",
        "support_consult_body",
    )
    english = public_copy.public_hub_copy("en")
    for locale in SUPPORTED_LOCALES:
        copy = public_copy.public_hub_copy(locale)
        assert not [key for key in required if not copy.get(key)], (locale, required)
        if locale != "en":
            assert copy["support_auto_body"] != english["support_auto_body"], locale
            assert copy["support_ticket_prompt_body"] != english["support_ticket_prompt_body"], locale

    for locale, pattern in SCRIPT_RANGES.items():
        copy = public_copy.public_hub_copy(locale)
        body = "\n".join(copy[key] for key in required if key.endswith("body"))
        assert re.search(pattern, body), locale


def test_support_deep_copy_has_direct_native_text_for_every_supported_locale():
    required = (
        "support_detail_title",
        "support_detail_body",
        "support_detail_questions",
        "support_detail_enter_need",
        "support_detail_create_lead",
        "support_detail_back_bot",
        "support_consult_detail_title",
        "support_consult_detail_intro",
        "support_consult_detail_input",
        "support_consult_detail_ticket",
        "support_consult_detail_premium",
        "support_consult_detail_back",
        "support_lead_premium_title",
        "support_lead_premium_body",
        "support_lead_custom_title",
        "support_lead_custom_body",
    )
    english = public_copy.public_hub_copy("en")
    for locale in SUPPORTED_LOCALES:
        copy = public_copy.public_hub_copy(locale)
        missing = [key for key in required if not str(copy.get(key) or "").strip()]
        assert not missing, (locale, missing)
        if locale != "en":
            assert copy["support_detail_body"] != english["support_detail_body"], locale
            assert copy["support_lead_custom_body"] != english["support_lead_custom_body"], locale

    for locale, pattern in SCRIPT_RANGES.items():
        copy = public_copy.public_hub_copy(locale)
        body = "\n".join(copy[key] for key in required if key.endswith(("body", "questions", "intro")))
        assert re.search(pattern, body), locale


def test_support_deep_renderers_keep_callbacks_and_render_native_copy():
    class Button:
        def __init__(self, text, callback_data=None, **_kwargs):
            self.text = text
            self.callback_data = callback_data

    class Markup:
        def __init__(self, rows):
            self.inline_keyboard = rows

    namespace = {
        "__builtins__": __builtins__,
        "InlineKeyboardButton": Button,
        "InlineKeyboardMarkup": Markup,
        "html": __import__("html"),
        "public_hub_copy": public_copy.public_hub_copy,
        "public_support_consult_choices": public_copy.public_support_consult_choices,
        "normalize_user_language": public_copy.public_copy_locale,
        "SUPPORT_CUSTOM_BOT_DETAILS": {"shop": {"title": "Shop", "lead_type": "shop_bot", "body": "body", "questions": "questions"}, "custom": {"title": "Custom", "lead_type": "custom_bot", "body": "body", "questions": "questions"}},
        "SUPPORT_CONSULT_DETAILS": {"video": ("Video", ["A", "B", "C"], "Question")},
    }
    for name in (
        "support_custom_bot_public_label",
        "support_consult_public_label",
        "support_consult_choice_labels",
        "support_custom_bot_detail_text",
        "support_custom_bot_detail_keyboard",
        "support_consult_detail_text",
        "support_consult_detail_keyboard",
        "support_lead_input_text",
        "support_flow_back_keyboard",
    ):
        exec(_function_source(name), namespace)

    for locale in SUPPORTED_LOCALES:
        copy = public_copy.public_hub_copy(locale)
        detail = namespace["support_custom_bot_detail_text"]("shop", locale)
        assert copy["support_detail_body"] in detail, locale
        assert copy["support_detail_questions"] in detail, locale
        detail_callbacks = {
            button.callback_data
            for row in namespace["support_custom_bot_detail_keyboard"]("shop", locale).inline_keyboard
            for button in row
            if button.callback_data
        }
        assert detail_callbacks == {"support|bot_input|shop", "support|bot", "menu|main"}

        consult = namespace["support_consult_detail_text"]("video", locale)
        assert copy["support_consult_detail_intro"] in consult, locale
        consult_callbacks = {
            button.callback_data
            for row in namespace["support_consult_detail_keyboard"]("video", locale).inline_keyboard
            for button in row
            if button.callback_data
        }
        assert {"support|consult_need|video|0", "support|consult_need|video|1", "support|consult_need|video|2", "support|consult_input|video", "support|premium", "support|consult", "menu|main"} <= consult_callbacks

        assert copy["support_lead_premium_body"] in namespace["support_lead_input_text"]("premium_lead", "personal", locale)
        assert copy["support_lead_custom_body"] in namespace["support_lead_input_text"]("custom_bot", "shop", locale)


def test_support_deep_handler_keeps_locale_for_each_existing_route():
    handler = _function_source("handle_human_support_callback")
    required = (
        "support_lead_input_text(\"premium_lead\", selected, lang)",
        "support_flow_back_keyboard(\"support|premium\",",
        "support_custom_bot_detail_text(bot_type, lang)",
        "support_custom_bot_detail_keyboard(bot_type, lang)",
        "support_input_one_message']",
        "support_consult_detail_text(service_type, lang)",
        "support_consult_detail_keyboard(service_type, lang)",
        "support_consult_detail_back']",
        "include_tickets=True,\n                lang=lang,",
    )
    for fragment in required:
        assert fragment in handler, fragment


def test_support_deep_choices_are_presentation_data_not_vietnamese_route_copy():
    source = _function_source("support_custom_bot_detail_text") + _function_source("support_consult_detail_text")
    assert "detail['body']" not in source
    assert "detail['questions']" not in source
    assert "SUPPORT_CONSULT_DETAILS" not in _function_source("support_consult_detail_text")

    handler = _function_source("handle_human_support_callback")
    for legacy_source in ("SUPPORT_CUSTOM_BOT_DETAILS", "SUPPORT_CONSULT_DETAILS"):
        assert legacy_source in handler  # stable codes/state data still own routing


def test_support_i18n_keeps_canonical_lead_labels_out_of_ticket_persistence():
    """Translated Support labels are presentation only, never ticket payload data."""
    handler = _function_source("handle_human_support_callback")

    # Each public choice must render in the selected locale, but the pending
    # ticket payload must retain the existing canonical label used by admin
    # history/search.  The input handler persists ``selected_option``.
    assert handler.count("selected_option=stored_selected") == 3
    assert 'selected_option=support_custom_bot_public_label(bot_type, lang)' not in handler
    assert "selected_option=selected," not in handler
    assert "canonical_title, canonical_choices, _ = SUPPORT_CONSULT_DETAILS[service_type]" in handler
    assert 'stored_selected = str(detail["title"] or "")' in handler


def test_support_consult_options_are_direct_native_copy_for_all_locales():
    expected_english_video = (
        "TikTok / affiliate video",
        "Product advertising video",
        "Business video",
    )
    assert public_copy.public_support_consult_choices("video", "en") == expected_english_video

    service_types = ("image", "video", "frame_video", "document", "voice", "package")
    for locale in SUPPORTED_LOCALES:
        for service_type in service_types:
            choices = public_copy.public_support_consult_choices(service_type, locale)
            assert len(choices) == 3, (locale, service_type, choices)
            assert len(set(choices)) == 3, (locale, service_type, choices)
            assert all(str(choice).strip() for choice in choices), (locale, service_type)
            if locale != "en":
                assert choices != public_copy.public_support_consult_choices(service_type, "en"), (locale, service_type)

    for locale, pattern in SCRIPT_RANGES.items():
        rendered = "\n".join(public_copy.public_support_consult_choices("video", locale))
        assert re.search(pattern, rendered), (locale, rendered)


def test_support_ticket_root_and_common_ticket_actions_receive_active_locale():
    handler = _function_source("handle_ticket_callback")
    required = (
        'lang = normalize_user_language(get_user_language(uid)) or "vi"',
        "support_ticket_menu_text(lang)",
        "support_ticket_menu_keyboard(lang)",
        "support_ticket_message_prompt(category, lang)",
        "support_ticket_input_keyboard(lang)",
        "public_support_ticket_list_keyboard(uid, lang)",
        "public_support_ticket_text(ticket, lang)",
        "support_ticket_detail_keyboard(ticket, lang)",
    )
    for fragment in required:
        assert fragment in handler, fragment


def test_support_ticket_copy_has_direct_native_text_for_every_supported_locale():
    """Ticket copy must be real locale data, not the legacy Vietnamese labels."""
    required = (
        "support_ticket_ack",
        "support_ticket_label_code",
        "support_ticket_label_category",
        "support_ticket_label_status",
        "support_ticket_label_priority",
        "support_ticket_label_time",
        "support_ticket_label_latest_message",
        "support_ticket_label_latest_reply",
        "support_ticket_list_empty",
        "support_ticket_list_recent",
        "support_ticket_attachment_present",
        "support_ticket_view_current",
        "support_ticket_add_message",
        "support_ticket_add_attachment",
        "support_ticket_mark_done",
        "support_ticket_back_to_ticket",
        "support_ticket_message_too_short",
        "support_ticket_reply_too_short",
        "support_ticket_not_found",
        "support_ticket_reply_prompt",
        "support_ticket_done_success",
        "support_ticket_attachment_prompt",
        "support_ticket_attachment_success",
        "support_ticket_attachment_need_media",
        "support_ticket_action_unsupported",
        "support_ticket_append_success",
        "support_ticket_append_notice",
        "support_ticket_feedback_notice",
        "support_ticket_status_refund_pending",
        "support_ticket_priority_high",
    )
    english = public_copy.public_hub_copy("en")
    for locale in SUPPORTED_LOCALES:
        copy = public_copy.public_hub_copy(locale)
        missing = [key for key in required if not str(copy.get(key) or "").strip()]
        assert not missing, (locale, missing)
        if locale != "en":
            assert copy["support_ticket_ack"] != english["support_ticket_ack"], locale
            assert copy["support_ticket_list_empty"] != english["support_ticket_list_empty"], locale
            assert copy["support_ticket_attachment_prompt"] != english["support_ticket_attachment_prompt"], locale

    for locale, pattern in SCRIPT_RANGES.items():
        copy = public_copy.public_hub_copy(locale)
        body = "\n".join(copy[key] for key in required)
        assert re.search(pattern, body), locale


def test_public_ticket_renderers_use_native_copy_and_preserve_customer_callbacks():
    class Button:
        def __init__(self, text, callback_data=None, **_kwargs):
            self.text = text
            self.callback_data = callback_data

    class Markup:
        def __init__(self, rows):
            self.inline_keyboard = rows

    ticket = {
        "id": 17,
        "ticket_code": "TA-20260812-000017",
        "category": "payment_topup",
        "status": "refund_pending",
        "priority": "high",
        "created_at": "2026-08-12 18:00:00",
        "message": "Customer message",
        "attachment_file_id": "file-17",
        "admin_note": "PRIVATE ADMIN NOTE",
    }
    namespace = {
        "__builtins__": __builtins__,
        "InlineKeyboardButton": Button,
        "InlineKeyboardMarkup": Markup,
        "html": __import__("html"),
        "public_hub_copy": public_copy.public_hub_copy,
        "normalize_user_language": public_copy.public_copy_locale,
        "latest_admin_ticket_reply": lambda _ticket_id: "Admin reply",
        "latest_support_ticket_message": lambda _ticket_id, _sender: "Customer message",
        "list_support_tickets": lambda **_kwargs: [ticket],
    }
    for name in (
        "public_support_ticket_category_label",
        "public_support_ticket_status_label",
        "public_support_ticket_priority_label",
        "support_ticket_menu_text",
        "support_ticket_menu_keyboard",
        "support_ticket_message_prompt",
        "support_ticket_input_keyboard",
        "support_ticket_created_text",
        "support_ticket_created_keyboard",
        "support_ticket_detail_keyboard",
        "public_support_ticket_text",
        "public_support_ticket_list_keyboard",
    ):
        exec(_function_source(name), namespace)

    expected_menu = {
        "ticket|cat|payment_topup", "ticket|cat|image_error", "ticket|cat|video_error",
        "ticket|cat|document_pdf", "ticket|cat|package_combo", "ticket|cat|refund",
        "ticket|cat|feature_request", "ticket|cat|lead_consulting", "ticket|cat|other",
        "ticket|mine", "menu|main",
    }
    expected_created = {
        "ticket|pv|17", "ticket|reply_user|17", "ticket|attach|17", "ticket|mine",
        "support|start", "menu|main",
    }
    expected_detail = {
        "ticket|reply_user|17", "ticket|attach|17", "ticket|done|17", "ticket|mine",
        "support|start", "menu|main",
    }
    for locale in SUPPORTED_LOCALES:
        copy = public_copy.public_hub_copy(locale)
        menu = namespace["support_ticket_menu_keyboard"](locale)
        menu_callbacks = {button.callback_data for row in menu.inline_keyboard for button in row if button.callback_data}
        assert menu_callbacks == expected_menu, (locale, menu_callbacks)
        menu_labels = "\n".join(button.text for row in menu.inline_keyboard for button in row)
        assert copy["feedback_payment_topup"] in menu_labels, locale
        assert copy["support_my_tickets"] in menu_labels, locale

        prompt = namespace["support_ticket_message_prompt"]("payment_topup", locale)
        assert copy["feedback_payment_topup"] in prompt, locale
        assert copy["support_ticket_prompt_body"] in prompt, locale

        created = namespace["support_ticket_created_text"](ticket, locale)
        assert copy["support_ticket_label_status"] in created, locale
        assert copy["support_ticket_status_refund_pending"] in created, locale
        created_callbacks = {
            button.callback_data
            for row in namespace["support_ticket_created_keyboard"](17, locale).inline_keyboard
            for button in row
            if button.callback_data
        }
        assert created_callbacks == expected_created, (locale, created_callbacks)

        detail = namespace["public_support_ticket_text"](ticket, locale)
        assert copy["support_ticket_label_priority"] in detail, locale
        assert copy["support_ticket_priority_high"] in detail, locale
        assert "Customer message" in detail and "Admin reply" in detail
        assert "PRIVATE ADMIN NOTE" not in detail
        detail_callbacks = {
            button.callback_data
            for row in namespace["support_ticket_detail_keyboard"](ticket, locale).inline_keyboard
            for button in row
            if button.callback_data
        }
        assert detail_callbacks == expected_detail, (locale, detail_callbacks)

        list_text, list_keyboard = namespace["public_support_ticket_list_keyboard"]("customer", locale)
        assert copy["support_ticket_list_recent"] in list_text, locale
        list_callbacks = {button.callback_data for row in list_keyboard.inline_keyboard for button in row if button.callback_data}
        assert list_callbacks == {"ticket|pv|17", "support|ticket", "support|start", "menu|main"}, (locale, list_callbacks)


def test_customer_ticket_entrypoints_thread_active_locale_without_touching_admin_routes():
    pending = _function_source("handle_support_pending_input")
    attachment = _function_source("handle_support_ticket_attachment")
    feedback = _function_source("handle_feedback_pending_text")
    command = _function_source("cmd_tickets")
    persona = _function_source("handle_support_persona_message")

    for source, name in (
        (pending, "handle_support_pending_input"),
        (attachment, "handle_support_ticket_attachment"),
        (feedback, "handle_feedback_pending_text"),
        (command, "cmd_tickets"),
        (persona, "handle_support_persona_message"),
    ):
        assert 'lang = normalize_user_language(' in source, name

    for fragment in (
        "support_ticket_created_text(ticket, lang)",
        "support_ticket_created_keyboard(ticket[\"id\"], lang)",
        "support_ticket_input_keyboard(lang)",
        "support_ticket_message_too_short",
        "support_ticket_reply_too_short",
        "support_ticket_not_found",
        "support_ticket_attachment_need_media",
    ):
        assert fragment in pending, fragment

    assert "support_ticket_attachment_success" in attachment
    assert "support_ticket_created_keyboard(ticket_id, lang)" in attachment
    assert "support_ticket_feedback_notice" in feedback
    assert "support_ticket_created_keyboard(ticket[\"id\"], lang)" in feedback
    assert "public_support_ticket_list_keyboard(update.effective_user.id, lang)" in command
    assert "support_ticket_created_keyboard(ticket[\"id\"], lang)" in persona

    ticket_handler = _function_source("handle_ticket_callback")
    admin_start = ticket_handler.index('if action == "admin":')
    customer_slice = ticket_handler[:admin_start]
    assert "support_ticket_detail_keyboard(ticket, lang)" in customer_slice
    assert 'action in admin_actions' in ticket_handler
    # Admin rendering is intentionally left on its existing protected path.
    assert "support_ticket_admin_text(ticket)" in ticket_handler[admin_start:]


def test_public_support_child_keyboard_copy_is_native_and_callbacks_are_stable():
    class Button:
        def __init__(self, text, callback_data=None, url=None, **_kwargs):
            self.text = text
            self.callback_data = callback_data
            self.url = url

    class Markup:
        def __init__(self, rows):
            self.inline_keyboard = rows

    namespace = {
        "__builtins__": __builtins__,
        "InlineKeyboardButton": Button,
        "InlineKeyboardMarkup": Markup,
        "SUPPORT_TELEGRAM_URL": "https://t.me/toanaas",
        "public_hub_copy": public_copy.public_hub_copy,
        "normalize_user_language": public_copy.public_copy_locale,
    }
    for name in (
        "support_cskh_auto_text",
        "support_cskh_auto_keyboard",
        "support_admin_contact_text",
        "support_admin_contact_keyboard",
        "support_general_ticket_prompt",
        "support_premium_text",
        "support_premium_keyboard",
        "support_custom_bot_text",
        "support_custom_bot_keyboard",
        "support_consult_keyboard",
    ):
        exec(_function_source(name), namespace)

    expected = {
        "support_cskh_auto_keyboard": {"support|ticket", "ticket|mine", "support|start", "menu|main"},
        "support_admin_contact_keyboard": {"support|ticket", "ticket|mine", "support|start", "menu|main"},
        "support_premium_keyboard": {"support|premium_type|personal", "support|premium_type|shop", "support|premium_type|business", "support|premium_type|private", "ticket|mine", "support|start", "menu|main"},
        "support_custom_bot_keyboard": {"support|bot_type|shop", "support|bot_type|content", "support|bot_type|support", "support|bot_type|internal", "support|bot_type|custom", "support|start", "menu|main"},
        "support_consult_keyboard": {"support|consult_type|image", "support|consult_type|video", "support|consult_type|frame_video", "support|consult_type|document", "support|consult_type|voice", "support|consult_type|package", "support|start", "menu|main"},
    }
    for locale in SUPPORTED_LOCALES:
        copy = public_copy.public_hub_copy(locale)
        for text_name in ("support_cskh_auto_text", "support_admin_contact_text", "support_general_ticket_prompt", "support_premium_text", "support_custom_bot_text"):
            rendered = namespace[text_name](locale)
            assert rendered.strip(), (locale, text_name)
            if locale not in {"en", "vi"}:
                assert rendered != namespace[text_name]("en"), (locale, text_name)
        for name, callbacks_expected in expected.items():
            markup = namespace[name](locale)
            callbacks = {button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data}
            assert callbacks == callbacks_expected, (locale, name, callbacks)
            labels = "\n".join(button.text for row in markup.inline_keyboard for button in row)
            assert copy["main_menu"] in labels, (locale, name)


def test_language_command_uses_the_saved_locale_for_heading_and_picker():
    """`/language` must not reset a non-Vietnamese user to Vietnamese copy."""
    command = _function_source("cmd_language")

    assert "lang = normalize_user_language(get_user_language(uid)) or \"vi\"" in command
    assert "language_choice_text(lang)" in command
    assert "language_choice_keyboard(lang)" in command


TRANSLATION_DEEP_FIELDS = (
    "translation_session_two_way_title",
    "translation_session_live_title",
    "translation_session_pair",
    "translation_session_send",
    "translation_session_voice_fallback",
    "translation_session_swap",
    "translation_session_change_pair",
    "translation_session_enable_voice",
    "translation_session_stop",
    "translation_pair_source",
    "translation_pair_target",
    "translation_pair_start",
    "translation_picker_source",
    "translation_picker_target",
    "translation_picker_choose",
    "translation_picker_auto_detect",
    "translation_picker_more",
    "translation_picker_back",
    "translation_picker_no_charge",
    "translation_text_confirm_title",
    "translation_text_confirm_target",
    "translation_text_confirm_continue",
    "translation_text_confirm_action",
    "translation_text_cancel",
    "translation_result_more",
    "translation_result_change",
    "translation_result_direction",
    "translation_result_original",
    "translation_result_translated",
    "translation_result_no_charge",
    "translation_auto_target",
    "translation_interface_language",
    "translation_input_too_long",
    "translation_service_unavailable",
    "translation_target_label_vi",
    "translation_target_label_en",
    "translation_target_label_zh",
    "translation_target_label_ja",
    "translation_target_label_ko",
    "translation_target_label_th",
)


# These keys own the customer-facing file/voice Translation shell.  They are
# deliberately separate from provider/runtime outcome values: a locale must
# keep its native copy while the existing callback, pending-state and provider
# routes remain unchanged.
TRANSLATION_MEDIA_FIELDS = (
    "translation_file_entry_title",
    "translation_file_entry_body",
    "translation_file_only",
    "translation_audio_video_redirect",
    "translation_audio_need_file",
    "translation_recent_media_missing",
    "translation_recent_file_missing",
    "translation_invalid_selection",
    "translation_invalid_target",
    "translation_unsupported_source",
    "translation_voice_guard",
    "translation_audio_received_body",
    "translation_pair_example_or",
    "translation_file_too_large",
)


def _translation_deep_runtime_namespace() -> dict:
    class Button:
        def __init__(self, text, callback_data=None, **_kwargs):
            self.text = text
            self.callback_data = callback_data

    class Markup:
        def __init__(self, rows):
            self.inline_keyboard = rows

    namespace = {
        "__builtins__": __builtins__,
        "InlineKeyboardButton": Button,
        "InlineKeyboardMarkup": Markup,
        "html": __import__("html"),
        "public_hub_copy": public_copy.public_hub_copy,
        "normalize_user_language": public_copy.public_copy_locale,
        "get_translation_pair_draft": lambda _user, mode: {"source": "auto", "target": "en", "mode": mode},
        "translation_pair_label": lambda left, right: f"{left or 'vi'} ↔ {right or 'en'}",
        "translate_target_label": lambda code: {"vi": "Vietnamese", "en": "English", "zh": "Chinese", "ja": "Japanese", "ko": "Korean", "th": "Thai"}.get(code, str(code)),
        "translation_source_label_for_button": lambda source, lang="vi": public_copy.public_hub_copy(lang)["translation_picker_auto_detect"] if source == "auto" else str(source),
    }
    for name in (
        "build_2col_keyboard",
        "translation_session_keyboard",
        "translation_session_started_text",
        "translation_pair_keyboard",
        "translation_pair_language_picker_text",
        "translation_pair_language_picker_keyboard",
        "translation_text_confirm_text",
        "translation_text_confirm_keyboard",
        "translation_text_target_keyboard",
        "translation_result_keyboard",
        "translation_language_options_keyboard",
        "translation_voice_menu_text",
        "translation_voice_menu_keyboard",
        "translation_stop_text",
        "translate_language_keyboard",
        "translation_file_error_text",
    ):
        exec(_function_source(name), namespace)
    return namespace


def test_translation_deep_flow_has_native_copy_and_stable_callbacks_for_all_locales():
    """A selected locale must not fall back to English after entering Translation."""
    english = public_copy.public_hub_copy("en")
    for locale in SUPPORTED_LOCALES:
        copy = public_copy.public_hub_copy(locale)
        missing = [key for key in TRANSLATION_DEEP_FIELDS if not str(copy.get(key) or "").strip()]
        assert not missing, (locale, missing)
        if locale != "en":
            assert copy["translation_session_send"] != english["translation_session_send"], locale
            assert copy["translation_text_confirm_continue"] != english["translation_text_confirm_continue"], locale

    runtime = _translation_deep_runtime_namespace()
    expected_session_callbacks = {
        "menu|translation_swap_languages",
        "menu|translation_two_way",
        "menu|translation_output_voice",
        "menu|translation_stop_session",
        "menu|translation_language_hub",
        "menu|main",
    }
    expected_pair_callbacks = {
        "menu|translation_pair_source_two_way",
        "menu|translation_pair_target_two_way",
        "menu|translation_pair_swap_two_way",
        "menu|translation_pair_start_two_way",
        "menu|translation_language_hub",
        "menu|main",
    }
    for locale in SUPPORTED_LOCALES:
        session_markup = runtime["translation_session_keyboard"](locale, "two_way")
        pair_markup = runtime["translation_pair_keyboard"]("two_way", locale, "customer")
        assert {
            button.callback_data
            for row in session_markup.inline_keyboard
            for button in row
            if button.callback_data
        } == expected_session_callbacks
        assert {
            button.callback_data
            for row in pair_markup.inline_keyboard
            for button in row
            if button.callback_data
        } == expected_pair_callbacks
        labels = "\n".join(button.text for row in session_markup.inline_keyboard for button in row)
        assert public_copy.public_hub_copy(locale)["translation_session_stop"] in labels, locale

    session = {"mode": "two_way", "lang_a": "vi", "lang_b": "en", "input_mode": "text_voice", "output_mode": "text"}
    for locale, pattern in SCRIPT_RANGES.items():
        rendered = runtime["translation_session_started_text"](session, locale)
        assert re.search(pattern, rendered), (locale, rendered)

    for name in (
        "translation_session_keyboard",
        "translation_session_started_text",
        "translation_pair_keyboard",
        "translation_pair_language_picker_text",
        "translation_pair_language_picker_keyboard",
        "translation_text_confirm_text",
        "translation_text_confirm_keyboard",
        "translation_text_target_keyboard",
        "translation_result_keyboard",
        "translation_language_options_keyboard",
        "translation_voice_menu_text",
        "translation_voice_menu_keyboard",
        "translation_stop_text",
        "translate_language_keyboard",
    ):
        assert "public_hub_copy" in _function_source(name), name


def test_translation_deep_handlers_keep_copy_scope_and_existing_state_routes():
    handler = _async_function_source("handle_menu_callback")
    pending = _async_function_source("handle_translation_menu_pending_text")
    session = _async_function_source("handle_translation_session_text")
    result = _async_function_source("send_translation_session_result")
    direct_result = _async_function_source("run_translate_text_to_target")

    for source, name in (
        (handler, "handle_menu_callback"),
        (pending, "handle_translation_menu_pending_text"),
        (session, "handle_translation_session_text"),
        (result, "send_translation_session_result"),
        (direct_result, "run_translate_text_to_target"),
    ):
        assert "public_hub_copy" in source, name

    for action in (
        "translation_text_confirm", "translation_text_cancel",
        "translation_pair_source_", "translation_pair_target_",
        "translation_pair_swap_", "translation_pair_start_",
        "translation_swap_languages", "translation_output_voice",
        "translation_stop_session", "translate_off",
    ):
        assert action in handler, action

    for state_call in (
        "set_translation_menu_pending", "clear_translation_menu_pending",
        "set_translation_pair_draft", "get_translation_pair_draft",
        "set_translation_session", "get_translation_session", "clear_translation_session",
    ):
        assert state_call in handler or state_call in pending or state_call in session, state_call

    protected = (
        "translate_to_language", "translate_subtitle_text", "video_dubbing_tts_bytes",
        "set_user_translate_mode",
    )
    assert all(marker in (handler + session + result + direct_result) for marker in protected)


def test_translation_file_voice_shell_has_direct_native_copy_and_keeps_routes():
    """File/voice Translation must not return to vi/en after a locale is chosen."""
    english = public_copy.public_hub_copy("en")
    for locale in SUPPORTED_LOCALES:
        copy = public_copy.public_hub_copy(locale)
        missing = [key for key in TRANSLATION_MEDIA_FIELDS if not str(copy.get(key) or "").strip()]
        assert not missing, (locale, missing)
        if locale != "en":
            assert copy["translation_file_entry_body"] != english["translation_file_entry_body"], locale
            assert copy["translation_audio_received_body"] != english["translation_audio_received_body"], locale
            assert copy["translation_voice_guard"] != english["translation_voice_guard"], locale

    for locale, pattern in SCRIPT_RANGES.items():
        copy = public_copy.public_hub_copy(locale)
        body = "\n".join(copy[key] for key in TRANSLATION_MEDIA_FIELDS)
        assert re.search(pattern, body), (locale, body)

    renderer_names = (
        "localized_menu_content",
        "handle_translation_callback",
        "run_translate_voice_to_target",
        "run_translate_file_to_target",
        "handle_translation_media_pending_upload",
        "audio_voice_received_text",
        "voice_translation_action_keyboard",
        "translation_session_started_text",
        "send_translation_session_result",
        "translation_voice_guard_text",
    )
    for name in renderer_names:
        source = _async_function_source(name) if name.startswith(("handle_", "run_", "send_")) else _function_source(name)
        assert "public_hub_copy" in source or name == "localized_menu_content", name

    callback_source = _async_function_source("handle_translation_callback")
    for route in ("tr_transcribe", "tr_pick|", "tr_more|", "tr_target|"):
        assert route in callback_source, route

    runtime = _translation_deep_runtime_namespace()
    for locale in SUPPORTED_LOCALES:
        copy = public_copy.public_hub_copy(locale)
        session = {"mode": "two_way", "lang_a": "vi", "lang_b": "en", "input_mode": "text_voice", "output_mode": "text"}
        rendered = runtime["translation_session_started_text"](session, locale)
        assert copy["translation_input_text_voice"] in rendered, locale
        assert copy["translation_output_text"] in rendered, locale


def test_voice_translation_result_renderer_source_compiles():
    """Protect the extracted public Voice Translation renderer from syntax drift."""
    ast.parse(_async_function_source("run_translate_voice_to_target"))


def test_main_menu_keeps_the_owner_approved_eight_row_layout_for_every_locale():
    """The root Hub stays navigable and localized without changing callbacks.

    The Owner-approved root layout keeps every public action in a two-column
    row. The current root is already the main menu, so it does not add a
    redundant single-button Main menu row; Admin remains a full-width row.
    """

    class Button:
        def __init__(self, text, callback_data=None, url=None, **_kwargs):
            self.text = text
            self.callback_data = callback_data
            self.url = url

    class Markup:
        def __init__(self, rows):
            self.inline_keyboard = rows

    namespace = {
        "__builtins__": __builtins__,
        "InlineKeyboardButton": Button,
        "InlineKeyboardMarkup": Markup,
        "normalize_user_language": public_copy.public_copy_locale,
        "public_hub_copy": public_copy.public_hub_copy,
        "public_chat_runtime": type("ChatPro", (), {"CHAT_PRO_RATE_LABEL": "5/25 Xu/1K"}),
        "product_context_callback": lambda *parts: "music_quick|" + "|".join(parts[1:]),
        "PRODUCT_CONTEXT_SHOWROOM": "showroom",
        "TOAN_AAS_COMMUNITY_URL": "https://example.invalid/center",
    }
    exec(_function_source("localized_main_menu_keyboard"), namespace)

    expected_callbacks = (
        ("freehub|main",),
        ("menu|main_video", "menu|main_image"),
        ("menu|translate", "music_quick|showroom|root"),
        ("menu|main_profile", "pricing|main"),
        ("menu|autopost", "menu|chat_pro"),
        ("menu|main_memory", "menu|support"),
        ("menu|main_guide", "feedback|start"),
        (None, "back_lang"),
    )
    for locale in SUPPORTED_LOCALES:
        copy = public_copy.public_hub_copy(locale)
        markup = namespace["localized_main_menu_keyboard"](False, locale)
        rows = markup.inline_keyboard
        assert len(rows) == 8, (locale, len(rows))
        assert tuple(tuple(button.callback_data for button in row) for row in rows) == expected_callbacks, locale
        assert [len(row) for row in rows] == [1, 2, 2, 2, 2, 2, 2, 2], locale
        assert copy["free_tools_label"] in rows[0][0].text, locale
        assert copy["video_label"] in rows[1][0].text, locale
        assert copy["image_label"] in rows[1][1].text, locale
        assert copy["translation_label"] in rows[2][0].text, locale
        assert copy["audio_studio_label"] in rows[2][1].text, locale
        assert copy["account_label"] in rows[3][0].text, locale
        assert copy["topup_pricing_label"] in rows[3][1].text, locale
        assert copy["autopost_label"] in rows[4][0].text, locale
        assert copy["chat_pro_label"] in rows[4][1].text, locale
        assert copy["notes_docs_label"] in rows[5][0].text, locale
        assert copy["support"] in rows[5][1].text, locale
        assert copy["guide_label"] in rows[6][0].text, locale
        assert copy["feedback_label"] in rows[6][1].text, locale
        assert copy["center"] in rows[7][0].text, locale
        assert rows[7][0].url == "https://example.invalid/center", locale
        assert copy["change_language"] in rows[7][1].text, locale

    admin_markup = namespace["localized_main_menu_keyboard"](True, "ko")
    assert len(admin_markup.inline_keyboard) == 9
    assert [button.callback_data for button in admin_markup.inline_keyboard[-1]] == ["menu|admin"]
    assert len(admin_markup.inline_keyboard[-1]) == 1


def test_public_chat_root_uses_direct_locale_copy_without_rewiring_runtime():
    """Chat's public shell must follow the selected locale; runtime stays untouched."""

    required = (
        "chat_menu_title",
        "chat_mode_label",
        "chat_mode_free",
        "chat_mode_pro",
        "chat_balance_label",
        "chat_free_summary",
        "chat_pro_summary",
        "chat_memory_summary",
        "chat_owner_admin_summary",
        "chat_pro_enable",
        "chat_pro_disable",
        "chat_free_label",
        "chat_account_label",
        "chat_free_title",
        "chat_free_body",
        "chat_error_quota",
        "chat_error_insufficient_xu",
        "chat_error_unsupported",
        "chat_error_duplicate",
        "chat_error_provider",
        "chat_media_redirect_body",
        "chat_media_redirect_image",
        "chat_media_redirect_video",
        "chat_footer_pro_admin",
        "chat_footer_pro_usage",
        "chat_footer_free_admin",
        "chat_footer_free_remaining",
        "chat_attachment_error_unsupported_type",
        "chat_attachment_error_unknown_size",
        "chat_attachment_error_size_limit",
        "chat_attachment_error_pro_capability",
        "chat_attachment_error_invalid_file",
        "chat_attachment_prompt_image",
        "chat_attachment_prompt_audio",
        "chat_attachment_prompt_video",
        "chat_attachment_prompt_pdf",
        "chat_attachment_prompt_text",
    )
    english = public_copy.public_hub_copy("en")
    for locale in SUPPORTED_LOCALES:
        copy = public_copy.public_hub_copy(locale)
        missing = [key for key in required if not str(copy.get(key) or "").strip()]
        assert not missing, (locale, missing)
        if locale != "en":
            assert copy["chat_free_body"] != english["chat_free_body"], locale
            assert copy["chat_error_provider"] != english["chat_error_provider"], locale
            assert copy["chat_attachment_error_invalid_file"] != english["chat_attachment_error_invalid_file"], locale
            assert copy["chat_attachment_prompt_image"] != english["chat_attachment_prompt_image"], locale

    for name in (
        "public_chat_menu_text",
        "public_chat_menu_keyboard",
        "public_chat_free_text",
        "_public_chat_failure_text",
    ):
        assert "public_hub_copy" in _function_source(name), name

    runtime = _async_function_source("handle_public_chat_text")
    assert "public_hub_copy" in runtime
    for presentation_key in (
        "chat_media_redirect_body",
        "chat_media_redirect_image",
        "chat_media_redirect_video",
        "chat_footer_pro_admin",
        "chat_footer_pro_usage",
        "chat_footer_free_admin",
        "chat_footer_free_remaining",
    ):
        assert presentation_key in runtime, presentation_key
    for protected in (
        "public_chat_runtime.run_public_chat_request",
        "public_chat_store.ensure_schema",
        "record_credit_event",
        "key4u_provider_instance",
    ):
        assert protected in runtime, protected

    attachment = _async_function_source("handle_public_chat_attachment")
    assert "public_hub_copy" in attachment
    for presentation_key in (
        "chat_attachment_error_unsupported_type",
        "chat_attachment_error_unknown_size",
        "chat_attachment_error_size_limit",
        "chat_attachment_error_pro_capability",
        "chat_attachment_error_invalid_file",
        "chat_attachment_prompt_image",
        "chat_attachment_prompt_audio",
        "chat_attachment_prompt_video",
        "chat_attachment_prompt_pdf",
        "chat_attachment_prompt_text",
    ):
        assert presentation_key in attachment, presentation_key
    for protected in (
        "public_chat_media.classify_attachment",
        "public_chat_media.PUBLIC_ATTACHMENT_LIMITS",
        "public_chat_media.capability_decision",
        "public_chat_media.validate_attachment",
        "context.bot.get_file",
        "download_to_drive",
        "os.remove",
    ):
        assert protected in attachment, protected
    assert '"menu|main_image"' in attachment
    assert '"menu|main_video"' in attachment


def test_translation_command_shell_uses_direct_locale_copy_without_provider_changes():
    """Direct commands share the selected locale with the interactive hub."""

    required = (
        "translation_command_missing_text",
        "translation_command_missing_target",
        "translation_tools_title",
        "translation_tools_body",
        "translation_auto_mode_enabled",
        "translation_auto_mode_disabled",
        "translation_auto_mode_already_disabled",
        "translation_auto_mode_invalid_target",
        "translation_auto_status_title",
        "translation_auto_status_enabled",
        "translation_auto_status_disabled",
        "translation_auto_status_target",
        "translation_auto_status_enable_hint",
        "translation_auto_status_disable_hint",
        "translation_auto_result_title",
        "translation_auto_result_source",
        "translation_auto_result_target",
        "translation_auto_result_disable_hint",
        "translation_auto_failed",
        "translation_auto_no_chat_fallback",
        "translation_recent_file_missing",
        "translation_recent_media_missing",
        "translation_audio_missing_stt",
        "translation_audio_error",
        "translation_audio_timeout",
        "translation_transcribe_title",
        "translation_transcribe_ready",
        "translation_transcribe_content",
        "translation_transcribe_balance",
        "translation_result_transcript_ready",
        "translation_result_translation_ready",
        "translation_result_already_target",
    )
    english = public_copy.public_hub_copy("en")
    for locale in SUPPORTED_LOCALES:
        copy = public_copy.public_hub_copy(locale)
        missing = [key for key in required if not str(copy.get(key) or "").strip()]
        assert not missing, (locale, missing)
        if locale != "en":
            assert copy["translation_tools_body"] != english["translation_tools_body"], locale
            assert copy["translation_auto_status_title"] != english["translation_auto_status_title"], locale

    renderer_names = (
        "translate_voice_missing_target_text",
        "translate_tools_text",
        "translation_file_error_text",
    )
    handler_names = (
        "cmd_translate",
        "cmd_translate_mode",
        "cmd_translate_mode_off",
        "cmd_translate_status",
        "cmd_translate_file",
        "cmd_translate_voice",
        "cmd_transcribe",
        "handle_auto_translate_message",
    )
    for name in renderer_names:
        assert "public_hub_copy" in _function_source(name), name
    for name in handler_names:
        assert "public_hub_copy" in _async_function_source(name), name

    # These provider/state calls remain present; localization must not rewire
    # their existing execution or charging path.
    command_source = _async_function_source("cmd_transcribe")
    assert "AgentDeepgram.transcribe" in command_source
    assert "preview_media_factory_credit_or_reply" in command_source
    assert "spend_media_factory_after_success_or_reply" in command_source
    auto_source = _async_function_source("handle_auto_translate_message")
    assert "translate_to_language" in auto_source
    assert "record_usage_event" in auto_source
