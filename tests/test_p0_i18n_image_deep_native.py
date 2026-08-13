"""Source-only contract for the complete native Image customer flow.

The test intentionally avoids importing ``bot`` so it cannot start Telegram,
providers, workers, payment code or database services.
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
        rf"^{re.escape(name)}\s*=\s*(.+?)(?=^[A-Z_][A-Z0-9_]*\s*=|^def\s+|\Z)",
        COPY_SOURCE,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, f"missing literal assignment: {name}"
    return ast.literal_eval(match.group(1).strip())


def _function_source(name: str) -> str:
    match = re.search(
        rf"^(?:async\s+)?def\s+{re.escape(name)}\b.*?(?=^(?:async\s+)?def\s+|^class\s+|\Z)",
        BOT_SOURCE,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, name
    return match.group(0)


def _aligned_copy(keys_name: str, values_name: str) -> dict[str, dict[str, str]]:
    keys = _literal(keys_name)
    values = _literal(values_name)
    return {
        locale: dict(zip(keys, values[locale], strict=True))
        for locale in LOCALES
    }


IMAGE_RENDERERS = (
    "build_image_prompt_output",
    "image_prompt_variants_text",
    "image_prompt_variants",
    "image_edit_detail_request_keyboard",
    "image_edit_option_variants",
    "image_edit_options_text",
    "image_edit_options_keyboard",
    "image_edit_suggestion_text",
    "image_edit_suggestion_keyboard",
    "image_edit_ready_text",
    "image_edit_prompt_text",
    "image_edit_result_keyboard",
    "image_edit_ai_guard_keyboard",
    "image_edit_ai_guard_text",
    "image_ai_edit_output_keyboard",
    "image_edit_create_new_text",
    "image_resize_choice_text",
    "image_resize_ratio_text",
    "image_resize_pixels_text",
    "image_editor_overlay_input_prompt",
    "image_editor_overlay_confirm_text",
    "image_editor_start_text",
    "image_editor_brightness_text",
    "image_editor_brightness_keyboard",
    "image_editor_preset_keyboard",
    "image_editor_overlay_keyboard",
    "image_editor_result_keyboard",
    "image_resize_method_label",
    "image_resize_result_keyboard",
    "image_upload_outside_flow_text",
    "image_upload_outside_flow_keyboard",
    "image_upscale_ai_guard_text",
    "image_aspect_ai_guard_text",
)


def test_image_deep_copy_is_complete_and_native_for_all_17_locales():
    copy = _literal("_PUBLIC_IMAGE_DEEP_COPY")
    assert set(copy) == set(LOCALES)
    english = copy["en"]
    vietnamese = copy["vi"]
    for locale, values in copy.items():
        assert values
        assert all(str(value).strip() for value in values.values()), locale
        assert all("\ufffd" not in str(value) for value in values.values()), locale
        if locale in {"vi", "en"}:
            continue
        exact_english = [key for key, value in values.items() if value == english[key]]
        exact_vietnamese = [key for key, value in values.items() if value == vietnamese[key]]
        assert not exact_english, (locale, "English fallback", exact_english)
        assert not exact_vietnamese, (locale, "Vietnamese fallback", exact_vietnamese)


def test_image_renderers_use_direct_copy_without_vi_else_english_branch():
    stale_patterns = (
        r"normalize_user_language\([^)]*\)\s*[!=]=\s*['\"]vi['\"]",
        r"\b(?:is_vi|labels_vi|labels_en)\b",
        r"\bvi\s*=\s*normalize_user_language",
    )
    for name in IMAGE_RENDERERS:
        source = _function_source(name)
        assert "public_image_deep_copy" in source, name
        stale = [pattern for pattern in stale_patterns if re.search(pattern, source)]
        assert not stale, (name, stale)


def test_runtime_image_results_use_native_copy_without_changing_execution_owners():
    for name in ("send_local_edited_image", "send_local_resized_image", "run_image_ai_edit_from_state"):
        source = _function_source(name)
        assert "public_image_deep_copy" in source, name
    ai_edit = _function_source("run_image_ai_edit_from_state")
    for owner in (
        "preview_media_factory_credit_or_reply",
        "spend_media_factory_after_success_or_reply",
        "refund_charged_credit",
        "call_image_edit_provider",
    ):
        assert owner in ai_edit


def test_vietnamese_image_copy_keeps_the_established_precise_meanings():
    flow = _aligned_copy("_PUBLIC_IMAGE_FLOW_KEYS", "_PUBLIC_IMAGE_FLOW_VALUES")["vi"]
    deep = _literal("_PUBLIC_IMAGE_DEEP_COPY")["vi"]
    assert flow["resize_blur"] == "Nền mờ, không cắt chủ thể"
    assert deep["style_product_1"] == "Studio sạch đẹp"
    assert deep["style_product_2"] == "Luxury showroom"
    assert deep["style_product_3"] == "Lifestyle đời thường"
    assert deep["resize_pixel"] == "Resize pixel"
