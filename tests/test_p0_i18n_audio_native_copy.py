"""Focused source-only contract for native Audio/Music/Voice presentation.

The module deliberately avoids importing ``bot``.  It validates only the
customer-facing copy authority and renderer source, so providers, Telegram,
database services, workers and wallet code cannot start during collection.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
LOCALES = (
    "vi", "en", "zh", "ja", "ko", "th", "ar", "es", "pt", "fr", "de",
    "hi", "ru", "tr", "fil", "it", "id",
)


def _audio_slice() -> str:
    start = BOT_SOURCE.index("_AUDIO_NATIVE_LABELS = {")
    end = BOT_SOURCE.index("def music_hub_text", start)
    return BOT_SOURCE[start:end]


def _function_source(name: str) -> str:
    match = re.search(
        rf"^(?:async\s+)?def\s+{re.escape(name)}\b.*?(?=^(?:async\s+)?def\s+|^class\s+|\Z)",
        BOT_SOURCE,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, name
    return match.group(0)


def _literal_assignments() -> dict[str, object]:
    values: dict[str, object] = {}
    tree = ast.parse(_audio_slice())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            try:
                value = ast.literal_eval(node.value)
            except (TypeError, ValueError):
                continue
            for target in node.targets:
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
            except (TypeError, ValueError):
                # Auxiliary catalogs may be assembled from already-literal
                # rows; the four authority tables asserted below remain
                # directly reconstructable and are never skipped.
                continue
            values[name].update(addition)
    return values


def test_audio_copy_authority_has_direct_complete_native_values_for_17_locales():
    values = _literal_assignments()
    labels = values["_AUDIO_NATIVE_LABELS"]
    topics = values["_AUDIO_TOPIC_LABELS"]
    flow = values["_AUDIO_NATIVE_FLOW_COPY"]
    deep_keys = values["_AUDIO_NATIVE_DEEP_KEYS"]
    deep_values = values["_AUDIO_NATIVE_DEEP_VALUES"]
    assert set(labels) == set(LOCALES)
    assert set(topics) == set(LOCALES)
    assert set(flow) == set(LOCALES)
    assert set(deep_values) == set(LOCALES)
    for locale in LOCALES:
        assert labels[locale]
        assert topics[locale]
        assert flow[locale]
        assert len(deep_values[locale]) == len(deep_keys), locale
        assert all(str(value).strip() for value in deep_values[locale]), locale


def test_customer_audio_renderers_do_not_use_binary_vi_english_copy():
    renderers = (
        "send_standalone_tts_result", "send_default_free_tts_result",
        "music_ai_default_description", "music_prompt_suggestions_text",
        "preview_quota_product_label", "preview_quota_policy_text",
        "preview_quota_notice_text", "preview_quota_block_text",
        "preview_quota_notice_keyboard", "music_product_tier_selection_text",
        "music_product_tier_keyboard", "music_product_vocal_keyboard",
        "music_product_details_input_text", "music_product_style_input_text",
        "music_product_lyrics_input_text", "music_product_idea_input_text",
        "music_product_idea_keyboard", "music_product_suggestions_text",
        "music_product_suggestions_keyboard", "music_product_invoice_text",
        "music_product_invoice_keyboard", "music_product_type_label",
        "music_product_success_charge_line", "music_product_success_text",
        "music_product_success_keyboard", "music_song_length_selection_text",
        "music_song_product_text", "music_song_product_keyboard",
        "music_song_duration_keyboard", "music_song_options_keyboard",
        "music_song_topic_keyboard", "music_song_step_text",
        "music_guided_label", "music_guided_step_text",
        "music_guided_step_keyboard", "music_flow_back_keyboard",
        "music_ai_input_text", "suno_user_guard_text", "music_ai_preview_text",
        "music_ai_preview_keyboard", "music_ai_status_keyboard",
        "product_clean_no_charge_failure_text", "music_ai_guarded_keyboard",
        "music_merge_menu_text", "music_merge_upload_text",
        "music_merge_check_text", "voice_preview_notice_text",
        "voice_clone_permission_forbidden_keyboard",
        "voice_clone_product_failure_text", "voice_clone_keyboard",
        "voice_clone_step_back_keyboard", "default_tts_single_voice_notice",
        "voice_profile_not_ready_text", "voice_profile_status_label",
        "user_voice_profiles_summary", "voice_vault_keyboard",
        "voice_profile_actions_keyboard", "voice_clone_quote_text",
        "voice_clone_quote_keyboard", "voice_clone_preview_entry_keyboard",
        "music_provider_error_text", "music_license_notice_text",
        "voice_preview_quota_exhausted_keyboard",
    )
    stale_patterns = (
        r"\bis_vi\b",
        r"music_ui_lang\(lang=lang\)\s*[!=]=\s*['\"]vi['\"]",
        r"normalize_user_language\(lang\)\s*[!=]=\s*['\"]vi['\"]",
        r"\blang\s*[!=]=\s*['\"](?:vi|en|zh)['\"]",
        r"\blabels_(?:vi|en)\b",
    )
    for name in renderers:
        source = _function_source(name)
        stale = [pattern for pattern in stale_patterns if re.search(pattern, source)]
        assert not stale, (name, stale)
        assert "_audio_copy(" in source or "_audio_label(" in source or "_audio_topic(" in source or "_audio_guided_option(" in source or "public_hub_copy(" in source, name


def test_audio_native_copy_has_no_corruption_or_placeholder_runs():
    source = _audio_slice()
    assert "\ufffd" not in source
    assert "???" not in source
    assert not re.search(r"TOAN AAS(?:belum|no|non|尚|ยัง|未|hat|n’a|не|لم)", source)


def test_audio_callback_payloads_remain_in_customer_keyboards():
    expected = {
        "music_product_invoice_keyboard": (
            "music_ai_confirm", "music_product_regenerate_suggestions",
            "music_product_edit_description", "music_product_change_tier",
        ),
        "voice_clone_keyboard": ("voice_consent", "voice_cancel"),
        "voice_profile_actions_keyboard": (
            "voice_profile_listen", "voice_profile_read", "voice_profile_default",
            "voice_profile_delete",
        ),
        "voice_preview_quota_exhausted_keyboard": (
            "voice_clone_full", "voice_profile_rename", "voice_custom",
        ),
    }
    for name, callbacks in expected.items():
        source = _function_source(name)
        for callback in callbacks:
            assert callback in source, (name, callback)
