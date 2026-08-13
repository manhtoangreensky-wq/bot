"""Source-only contract for native Video and SubDub customer presentation.

The test never imports ``bot``.  It inspects only public copy and renderer
source so no provider, worker, wallet, payment, database, or Telegram action
can run.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
COPY_SOURCE = (ROOT / "services" / "pricing_guide_content.py").read_text(encoding="utf-8")
LOCALES = (
    "vi", "en", "zh", "ja", "ko", "th", "ar", "es", "pt", "fr", "de",
    "hi", "ru", "tr", "fil", "it", "id",
)


def _literal(name: str):
    match = re.search(
        rf"^{re.escape(name)}\s*=\s*(.+?)(?=^[A-Z_][A-Z0-9_]*(?::[^=]+)?\s*=|^def\s+|\Z)",
        COPY_SOURCE,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, f"missing literal assignment: {name}"
    return ast.literal_eval(match.group(1).strip())


def _function_source(name: str) -> str:
    match = re.search(
        rf"^(?:async\s+)?def\s+{re.escape(name)}\b.*?(?=^(?:async\s+)?def\s+|^class\s+|^@|\Z)",
        BOT_SOURCE,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, name
    return match.group(0)


def _aligned_copy(keys_name: str, values_name: str) -> dict[str, dict[str, str]]:
    keys = _literal(keys_name)
    values = _literal(values_name)
    assert set(values) == set(LOCALES)
    return {
        locale: dict(zip(keys, values[locale], strict=True))
        for locale in LOCALES
    }


def _assert_native_table(table: dict[str, dict[str, str]]) -> None:
    english = table["en"]
    vietnamese = table["vi"]
    for locale, row in table.items():
        assert row
        assert all(str(value).strip() for value in row.values()), locale
        assert all("\ufffd" not in str(value) and "???" not in str(value) for value in row.values()), locale
        if locale in {"vi", "en"}:
            continue
        assert not [key for key, value in row.items() if value == english[key]], (locale, "English fallback")
        assert not [key for key, value in row.items() if value == vietnamese[key]], (locale, "Vietnamese fallback")


VIDEO_CORE_RENDERERS = (
    "video_profile_studio_menu_text",
    "video_profile_studio_menu_keyboard",
    "video_profile_studio_question_text",
    "video_profile_studio_preview_text",
    "video_profile_scene1_subject_text",
    "architecture_profile_menu_text",
    "video_edit_hub_text",
    "video_edit_hub_keyboard",
    "video_edit_info_text",
    "video_edit_guide_text",
    "video_ai_edit_intro_text",
    "video_editor_menu_text",
    "video_editor_upload_required_text",
    "video_editor_public_guard_text",
    "video_editor_menu_keyboard",
    "video_editor_job_status_text",
    "video_script_hub_text",
    "video_script_hub_keyboard",
    "video_script_nav_keyboard",
)

VIDEO_TAIL_RENDERERS = (
    "video_finalization_menu_text",
    "video_finalization_menu_keyboard",
    "video_finalization_aspect_text",
    "video_finalization_tier_text",
    "video_finalization_scene_count_text",
    "video_finalization_music_text",
    "video_finalization_addon_text",
    "video_finalization_voice_text",
    "video_finalization_summary_text",
    "video_addon_menu_text",
    "video_addon_menu_keyboard",
    "video_quote_invoice_text",
    "public_video_confirm_text",
    "trend_workflow_content_confirm_text",
    "trend_video_pending_prompt_text",
)

SUBDUB_RENDERERS = (
    "video_dubbing_menu_text",
    "video_dubbing_menu_keyboard",
    "video_dubbing_source_text",
    "video_dubbing_source_keyboard",
    "video_dubbing_output_text",
    "video_dubbing_output_keyboard",
    "video_dubbing_language_text",
    "video_dubbing_language_keyboard",
    "video_dubbing_voice_text",
    "video_dubbing_voice_keyboard",
    "video_dubbing_confirm_text",
    "video_dubbing_confirm_keyboard",
    "subdub_progress_text",
    "subdub_progress_keyboard",
    "subdub_clean_failure_text",
    "subdub_mode_success_text",
    "subdub_mode_fail_text",
    "video_dubbing_job_status_text",
    "subtitle_editor_text",
    "subtitle_editor_keyboard",
)


def test_video_and_subdub_copy_tables_are_direct_native_for_all_17_locales():
    _assert_native_table(_aligned_copy("_PUBLIC_VIDEO_DEEP_KEYS", "_PUBLIC_VIDEO_DEEP_VALUES"))
    _assert_native_table(_aligned_copy("_PUBLIC_SUBDUB_DEEP_KEYS", "_PUBLIC_SUBDUB_DEEP_VALUES"))


def test_video_customer_renderers_use_native_copy_without_binary_locale_branch():
    stale_patterns = (
        r"normalize_user_language\([^)]*\)\s*[!=]=\s*['\"]vi['\"]",
        r"\b(?:is_vi|labels_vi|labels_en)\b",
        r"\bif\s+lang\s*==\s*['\"](?:vi|en|zh)['\"]",
    )
    for name in VIDEO_CORE_RENDERERS + VIDEO_TAIL_RENDERERS:
        source = _function_source(name)
        assert "public_video_deep_copy" in source, name
        assert not [pattern for pattern in stale_patterns if re.search(pattern, source)], name


def test_subdub_customer_renderers_use_native_copy_without_binary_locale_branch():
    stale_patterns = (
        r"normalize_user_language\([^)]*\)\s*[!=]=\s*['\"]vi['\"]",
        r"\b(?:is_vi|labels_vi|labels_en)\b",
        r"\bif\s+lang\s*==\s*['\"](?:vi|en|zh)['\"]",
    )
    for name in SUBDUB_RENDERERS:
        source = _function_source(name)
        assert "public_subdub_deep_copy" in source, name
        assert not [pattern for pattern in stale_patterns if re.search(pattern, source)], name


def test_copy_only_change_keeps_video_and_subdub_route_callbacks_present():
    for callback in (
        "vprofile|start", "videoedit|ai", "videoedit|manual", "vproduct|script_ai",
        "vproduct|script_manual", "vproduct|script_upload", "vfinal|voice",
        "vfinal|music", "vfinal|addon", "videoaddon|invoice", "trendg|start",
        "videodub|source_upload", "videodub|confirm", "menu|main_video", "menu|main",
    ):
        assert callback in BOT_SOURCE
