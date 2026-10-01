import html
from pathlib import Path

import pytest

from services.subdub_blackboxes import auto_multi_speaker, auto_smart_multivoice, auto_speaker


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def _source_between(start: str, end: str) -> str:
    start_at = BOT_SOURCE.index(start)
    end_at = BOT_SOURCE.index(end, start_at)
    return BOT_SOURCE[start_at:end_at]


def test_combo_full_dub_uses_the_canonical_completion_report():
    combo_completion = _source_between(
        '        if action == "combo_full_dub":',
        '        if action == "combo_redub_voice":',
    )

    assert "video_dubbing_receipt_text(" in combo_completion
    assert "video_dubbing_receipt_keyboard(" in combo_completion
    assert "subtitle_plus_dub_completed_text(" not in combo_completion
    assert "subtitle_plus_dub_completed_keyboard(" not in combo_completion


def test_subdub_customer_menu_never_sends_admin_debug_blocks():
    customer_handler = _source_between(
        "async def handle_video_dubbing_callback(",
        "def marketing_pending_key(",
    )

    assert "subdub_job_debug_text(" not in customer_handler
    assert "subtitle_dub_debug_text(" not in customer_handler
    assert "SUBDUB JOB DEBUG" not in customer_handler


def _receipt_text(state, lang):
    namespace = {
        "html": html,
        "auto_multi_speaker": auto_multi_speaker,
        "auto_smart_multivoice": auto_smart_multivoice,
        "auto_speaker": auto_speaker,
        "normalize_video_translate_mode": lambda value: value,
        "normalize_user_language": lambda value: value,
        "subdub_duration_validation_allows_success": lambda _state: True,
        "subdub_result_has_delivered_video": lambda state: state.get("final_mp4_delivered") is True,
        "subdub_auto_multi_terminal_proof_fields": lambda _state: {},
        "subdub_receipt_duration_label": lambda value, _lang: str(value),
        "subdub_public_job_code": lambda value: value,
        "_safe_int": lambda value, default=0: int(value or default),
        "SUBDUB_PUBLIC_AUDIO_FALLBACK_ENABLED": False,
        "VIDEO_SUBTITLE_MODE_CREATE": "create",
        "VIDEO_SUBTITLE_MODE_TRANSLATE": "translate",
        "VIDEO_SUBTITLE_MODE_DUB": "dub",
        "VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB": "subtitle_plus_dub",
    }
    source = _source_between(
        "def video_dubbing_receipt_text(",
        "\nSUBDUB_POSTDELIVERY_VIDEO_EDIT_CONTEXT",
    )
    exec(compile(source, "bot.py", "exec"), namespace)
    return namespace["video_dubbing_receipt_text"]({
        "mode": "subtitle_plus_dub",
        "terminal_state": "delivered",
        "final_mp4_delivered": True,
        "final_mp4_duration": 181.0,
        "voice_selection_mode": "auto_speaker",
        **state,
    }, {}, lang)


@pytest.mark.parametrize("lang", ["vi", "en"])
@pytest.mark.parametrize("selection", [
    {"auto_smart_multivoice_opt_in": True, "auto_multi_engine": "v2"},
    {"auto_exact_resume_state": {
        "auto_speaker_lane": "auto_smart_multivoice",
        "auto_smart_dispatch": "n3_plus_proven_v2",
    }},
])
def test_smart_multi_receipt_keeps_selected_product_after_v2_dispatch(lang, selection):
    text = _receipt_text(selection, lang)

    assert "<b>Smart Multi</b>" in text
    assert "Auto-detected two-speaker" not in text


def test_exact_two_receipt_still_names_exact_two_product():
    text = _receipt_text({"voice_kind": "auto_speaker_gender"}, "en")

    assert "Auto-detected two-speaker" in text
    assert "Smart Multi" not in text
