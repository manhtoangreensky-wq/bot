"""Source/copy-only contract for native deep customer menus.

This module deliberately does not import ``bot`` or any service module.  It
parses their source instead, so collection cannot start Telegram, providers,
payment code, workers, or database services.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
COPY_SOURCE = (ROOT / "services" / "pricing_guide_content.py").read_text(encoding="utf-8")
SUPPORTED_LOCALES = (
    "vi", "en", "zh", "ja", "ko", "th", "ar", "es", "pt", "fr", "de",
    "hi", "ru", "tr", "fil", "it", "id",
)


def _module_literals(source: str) -> dict[str, object]:
    """Read literal assignments and subsequent ``dict.update`` additions."""

    values: dict[str, object] = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            value_node = node.value
            try:
                value = ast.literal_eval(value_node)
            except (ValueError, TypeError):
                if (
                    isinstance(value_node, ast.Call)
                    and isinstance(value_node.func, ast.Name)
                    and value_node.func.id == "frozenset"
                    and len(value_node.args) == 1
                ):
                    value = frozenset(ast.literal_eval(value_node.args[0]))
                else:
                    continue
            for target in targets:
                if isinstance(target, ast.Name):
                    values[target.id] = value
            continue
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not (
            isinstance(call.func, ast.Attribute)
            and call.func.attr == "update"
            and isinstance(call.func.value, ast.Name)
            and len(call.args) == 1
        ):
            continue
        name = call.func.value.id
        if isinstance(values.get(name), dict):
            try:
                addition = ast.literal_eval(call.args[0])
            except (ValueError, TypeError):
                # Auxiliary catalogs may include computed values.  The direct
                # native authority tables asserted below remain literal and
                # must still be reconstructed instead of aborting collection.
                continue
            values[name].update(addition)
    return values


COPY_LITERALS = _module_literals(COPY_SOURCE)


def _literal(name: str):
    return COPY_LITERALS[name]


def _function_source(name: str) -> str:
    """Extract one top-level function without parsing the huge bot module."""

    match = re.search(
        rf"^(?:async\s+)?def\s+{re.escape(name)}\b.*?(?=^(?:async\s+)?def\s+|^class\s+|^@|\Z)",
        BOT_SOURCE,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, name
    return match.group(0)


def _direct_public_copy() -> dict[str, dict[str, str]]:
    """Reconstruct public_hub_copy without importing its dependency-heavy module."""

    table_names = (
        "_PUBLIC_HUB_COPY",
        "_PUBLIC_HUB_AUXILIARY_COPY",
        "_PUBLIC_ROOT_NAVIGATION_COPY",
        "_PUBLIC_CHAT_ROOT_COPY",
        "_PUBLIC_CHAT_ATTACHMENT_COPY",
        "_PUBLIC_ROOT_SCREEN_COPY",
        "_PUBLIC_FREE_HUB_ROOT_COPY",
        "_PUBLIC_IMAGE_ROOT_COPY",
        "_PUBLIC_AUDIO_ROOT_COPY",
        "_PUBLIC_DEEP_MENU_COPY",
        "_PUBLIC_ROOT_FLOW_COPY",
        "_PUBLIC_ROOT_ACTION_COPY",
        "_PUBLIC_FEEDBACK_PROMPT_COPY",
        "_PUBLIC_MEMORY_STORAGE_COPY",
        "_PUBLIC_TRANSLATION_FLOW_COPY",
        "_PUBLIC_TRANSLATION_MEDIA_COPY",
        "_PUBLIC_TRANSLATION_COMMAND_COPY",
        "_PUBLIC_INTERNATIONAL_SUPPORT_COPY",
        "_PUBLIC_SUPPORT_PROFILE_COPY",
        "_PUBLIC_SUPPORT_CHILD_LABELS",
        "_PUBLIC_SUPPORT_CHILD_TEXT",
        "_PUBLIC_SUPPORT_DEEP_COPY",
        "_PUBLIC_SUPPORT_TICKET_COPY",
        "_PUBLIC_PACKAGE_NAVIGATION_COPY",
        "_PUBLIC_DOCS_ACTION_NATIVE_COPY",
        "_PUBLIC_MEMORY_NOTE_FIELD_COPY",
    )
    result = {locale: {} for locale in SUPPORTED_LOCALES}
    for name in table_names:
        table = _literal(name)
        for locale in SUPPORTED_LOCALES:
            result[locale].update(table.get(locale, {}))

    # Reconstruct aligned copy tables which are intentionally assembled by
    # production code instead of being stored as one giant literal.
    docs_keys = _literal("_PUBLIC_DOCS_MEMORY_NATIVE_KEYS")
    docs_values = _literal("_PUBLIC_DOCS_MEMORY_NATIVE_VALUES")
    for locale in SUPPORTED_LOCALES:
        result[locale].update(dict(zip(docs_keys, docs_values[locale], strict=True)))

    task_labels = _literal("_PUBLIC_FREE_TASK_LABELS")
    for locale in SUPPORTED_LOCALES:
        result[locale].update({f"freehub_task_{key}": value for key, value in task_labels[locale].items()})

    deep_keys = _literal("_PUBLIC_NATIVE_DEEP_FLOW_KEYS")
    deep_values = _literal("_PUBLIC_NATIVE_DEEP_FLOW_VALUES")
    for locale in SUPPORTED_LOCALES:
        result[locale].update(dict(zip(deep_keys, deep_values[locale], strict=True)))
    return result


PUBLIC_COPY = _direct_public_copy()


def test_copy_authority_directly_covers_all_17_locales():
    assert set(_literal("PUBLIC_COPY_LOCALES")) == set(SUPPORTED_LOCALES)
    assert set(PUBLIC_COPY) == set(SUPPORTED_LOCALES)


def test_public_native_copy_contains_no_unicode_replacement_or_question_mark_runs():
    assert "\ufffd" not in COPY_SOURCE
    assert "???" not in COPY_SOURCE


def test_rendered_ui_copy_has_readable_spacing_around_stable_product_tokens():
    # The generated source may be compact, but the table returned to bot.py
    # must never expose glued text such as ``TOAN AASno`` or ``cobróXu``.
    assert "tokens =" in COPY_SOURCE
    assert "re.sub" in COPY_SOURCE


def test_cjk_and_non_latin_ui_tables_retain_native_script():
    # A translated surface must not silently become an English-only table.
    for locale, pattern in {
        "ja": r"[\u3040-\u30ff\u4e00-\u9fff]",
        "ko": r"[\uac00-\ud7af]",
        "th": r"[\u0e00-\u0e7f]",
        "ar": r"[\u0600-\u06ff]",
        "hi": r"[\u0900-\u097f]",
        "ru": r"[\u0400-\u04ff]",
    }.items():
        joined = "\n".join(_literal("_PUBLIC_UI_TEXT_VALUES")[locale])
        assert re.search(pattern, joined), locale


def test_deep_customer_surfaces_have_direct_native_copy_without_sentence_fallback():
    required_by_surface = {
        "ai_quick_help_hints": (
            "ai_menu_title", "ai_menu_body", "ai_better_prompts", "quick_menu_title",
            "quick_menu_body", "quick_video", "quick_memory", "quick_documents",
            "quick_topup", "quick_translation", "quick_images", "quick_music",
            "help_title", "help_body", "hint_choose_group",
        ),
        "free_tools": (
            "free_title", "free_body", "freehub_input_title", "freehub_input_privacy",
            "freehub_input_free", "freehub_suggestions_title", "freehub_suggestions_body",
            "freehub_ready", "freehub_result_title", "freehub_copy_result", "freehub_try_again",
        ),
        "image": (
            "image_menu_title", "image_menu_body", "image_create_title", "image_send_prompt",
            "image_upload_reference", "image_confirm", "image_creating", "image_success",
            "image_failure", "image_edit_title",
        ),
        "docs_memory_storage": (
            "memory_title", "memory_body", "docs_title", "docs_body", "memory_create_title",
            "memory_send_note", "memory_saved", "memory_search_title", "memory_search_prompt",
            "memory_delete_confirm", "memory_empty", "docs_upload_title", "docs_send_file",
            "docs_confirm", "docs_processing", "docs_success", "docs_failure",
            "storage_status_title", "storage_status_total_used", "storage_addon_title",
            "storage_addon_intro", "storage_addon_custom", "storage_addon_back",
        ),
        "audio_music_voice": (
            "audio_title", "audio_body", "audio_voice", "audio_music", "audio_menu_title",
            "music_create_title", "voice_create_title", "audio_send_file", "audio_confirm",
            "audio_processing", "audio_failure",
        ),
        "packages_referral_account_support_topup": (
            "package_title", "package_choose", "package_details", "package_buy",
            "referral_title", "referral_link", "referral_policy", "referral_stats",
            "account_title", "account_balance", "topup_title", "topup_choose_amount",
            "packages_label", "account_label", "topup_label", "support_title", "support_contact",
            "support_contact_title", "support_contact_body", "support_ticket_prompt_title",
            "profile_topup", "profile_pricing", "profile_packages",
        ),
    }
    required = tuple(dict.fromkeys(key for keys in required_by_surface.values() for key in keys))
    english = PUBLIC_COPY["en"]
    vietnamese = PUBLIC_COPY["vi"]
    # These product names, formats, units, commands, and brands are immutable;
    # equality is permitted only for these keys, not as a blanket English-token ban.
    immutable_equal_keys = {
        "quick_video", "quick_documents", "profile_topup", "profile_pricing", "profile_packages",
        # These are natural cognates or established product/UI terms in the
        # target language, not evidence of an English fallback.
        "quick_images", "memory_title", "account_label",
    }

    for locale in SUPPORTED_LOCALES:
        copy = PUBLIC_COPY[locale]
        missing = [key for key in required if not str(copy.get(key) or "").strip()]
        assert not missing, (locale, "missing direct public_hub_copy keys", missing)
        if locale in {"vi", "en"}:
            continue
        exact_english = [
            key for key in required
            if key not in immutable_equal_keys and copy[key].strip() == english[key].strip()
        ]
        exact_vietnamese = [
            key for key in required
            if key not in immutable_equal_keys and copy[key].strip() == vietnamese[key].strip()
        ]
        assert not exact_english, (locale, "exact English sentence fallback", exact_english)
        assert not exact_vietnamese, (locale, "exact Vietnamese sentence fallback", exact_vietnamese)


def test_targeted_renderers_use_public_hub_copy_without_binary_locale_branches():
    renderers = (
        "ui_text", "main_ai_keyboard", "main_quick_keyboard", "menu_nav_keyboard_i18n",
        "menu_text_main_ai_i18n", "menu_text_main_quick_i18n", "free_hub_suggestion_title",
        "free_hub_suggestions_text", "free_hub_suggestions_keyboard", "image_menu_child_keyboard",
        "image_prompt_menu_start_text", "memory_storage_addon_text", "memory_storage_addon_keyboard",
        "package_i18n_group_label", "human_support_text", "support_ticket_menu_text",
    )
    binary_locale_patterns = (
        r'normalize_user_language\([^)]*\)\s*[!=]=\s*["\']vi["\']',
        r'\b(?:lang|locale)\s*[!=]=\s*["\']vi["\']',
        r'\bif\s+is_vi\s+else\b',
        r'\blabels_en\b',
    )
    for name in renderers:
        source = _function_source(name)
        assert "public_hub_copy" in source, name
        stale = [pattern for pattern in binary_locale_patterns if re.search(pattern, source)]
        assert not stale, (name, stale)


def test_localized_menu_content_has_no_legacy_vietnamese_public_fallback():
    source = _function_source("localized_menu_content")
    assert "return menu_content(action, is_admin)" not in source
    assert "localized_start_menu_text" in source


def test_docs_memory_renderers_use_native_public_copy():
    required = (
        "docs_menu_body", "docs_send_image", "docs_send_pdf", "docs_send_file",
        "docs_received", "docs_wrong_file", "docs_confirm", "docs_add_more",
        "memory_create_body", "memory_search_body", "memory_delete_body",
        "memory_list_title", "memory_empty", "memory_detail_title",
        "memory_delete_confirm_body", "storage_confirm_title", "storage_confirm_payment",
    )
    for locale in SUPPORTED_LOCALES:
        missing = [key for key in required if not str(PUBLIC_COPY[locale].get(key) or "").strip()]
        assert not missing, (locale, missing)

    renderers = (
        "doc_tools_menu_text_i18n", "doc_tools_keyboard", "doc_tool_parent_label",
        "doc_tool_display_copy", "doc_tool_start_text", "doc_tool_start_keyboard",
        "doc_tool_received_text", "doc_tool_after_file_keyboard",
        "doc_tool_confirm_text", "doc_tool_confirm_keyboard",
        "memory_main_keyboard", "memory_create_prompt_text", "memory_search_prompt_text",
        "memory_delete_prompt_text", "memory_notes_list_text", "memory_notes_list_keyboard",
        "memory_note_detail_text", "memory_note_detail_keyboard", "memory_delete_confirm_text",
        "memory_delete_confirm_keyboard", "memory_storage_addon_confirm_text",
        "memory_storage_addon_confirm_keyboard", "storage_addon_checkout_keyboard",
    )
    for name in renderers:
        source = _function_source(name)
        assert "public_hub_copy" in source, name
        assert "is_vi" not in source, name
        assert not re.search(r"normalize_user_language\([^)]*\)\s*[!=]=\s*['\"]vi['\"]", source), name


def test_manual_package_and_support_shells_do_not_use_binary_vi_english_copy():
    renderers = (
        "manual_payment_menu_keyboard",
        "user_package_summary_text",
        "support_contact_text",
    )
    for name in renderers:
        source = _function_source(name)
        assert "public_hub_copy" in source, name
        assert "is_vi" not in source, name
        assert "if normalize_user_language(lang) == \"vi\" else" not in source, name
