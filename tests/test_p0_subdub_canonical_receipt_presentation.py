import html
import os
from pathlib import Path

import pytest

from services.subdub_blackboxes import auto_multi_speaker, auto_smart_multivoice, auto_speaker
from services import subdub_speaker_cast


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
        "subdub_speaker_cast": subdub_speaker_cast,
        "os": os,
        "subdub_aspect_ratio_close": lambda sw, sh, ow, oh: bool(
            sh and oh and abs(sw / sh - ow / oh) < 0.001
        ),
        "subdub_receipt_duration_label": lambda value, _lang: str(value),
        "subdub_public_job_code": lambda value: value,
        "_safe_int": lambda value, default=0: int(default if value in (None, "") else value),
        "SUBDUB_PUBLIC_AUDIO_FALLBACK_ENABLED": False,
        "VIDEO_SUBTITLE_MODE_CREATE": "create",
        "VIDEO_SUBTITLE_MODE_TRANSLATE": "translate",
        "VIDEO_SUBTITLE_MODE_DUB": "dub",
        "VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB": "subtitle_plus_dub",
    }
    proof_source = _source_between(
        "def subdub_auto_multi_terminal_proof_fields(",
        "\ndef subdub_auto_routing_decision(",
    )
    exec(compile(proof_source, "bot.py", "exec"), namespace)
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


@pytest.mark.parametrize("lang", ["vi", "en"])
@pytest.mark.parametrize("count", [3, 5, 8])
def test_smart_receipt_reports_verified_speaker_and_voice_counts(lang, count):
    state = {
        "auto_speaker_lane": "auto_smart_multivoice",
        "auto_smart_multivoice_opt_in": True,
        "auto_smart_dispatch": "n3_plus_proven_v2",
        "source_file_name": "input.mp4",
        "auto_detected_speaker_count": count,
        "auto_distinct_voice_count": count,
        "auto_multi_voice_verified": True,
        "auto_multi_attribution_verified": True,
        "auto_multi_geometry_verified": True,
        "auto_multi_source_display_width": 1080,
        "auto_multi_source_display_height": 1920,
        "auto_multi_output_display_width": 1080,
        "auto_multi_output_display_height": 1920,
        "auto_multi_output_rotation": 0,
        "auto_multi_cast_sha256": "c" * 64,
        "multi_acoustic_backend": "local_wespeaker_resnet34_fixed_vocal",
        "multi_acoustic_model_sha256": "9fea6516d7ad6bf0a76c7689f5a49b65d330fad6dde96c91bb4435ffbfe056a1",
        "multi_acoustic_algorithm_version": "wespeaker-resnet34-fixed-vocal-v4",
        "multi_acoustic_speaker_count": count,
        "multi_acoustic_word_count": 50,
        "multi_acoustic_unit_count": count * 2,
        "multi_acoustic_embedding_window_count": count * 4,
        "multi_acoustic_cluster_sizes": [2] * count,
        "multi_acoustic_stability_pass": True,
        "multi_acoustic_word_coverage_count": 50,
        "multi_acoustic_overlap_mapped_count": count * 2,
        "multi_acoustic_centroid_mapped_count": 0,
        "multi_acoustic_speaker_unit_counts": [2] * count,
        "multi_acoustic_speaker_registers": ["high"] + ["low"] * (count - 1),
        "multi_acoustic_speaker_register_confidences": [0.99] * count,
        "multi_acoustic_female_speaker_count": 1,
        "multi_acoustic_male_speaker_count": count - 1,
        "multi_acoustic_gender_model_sha256": "e98f8bc6d7960a8a2169368fe4533636903e712790e96dbff81b679ede5de252",
        "multi_acoustic_gender_ambiguous_window_count": 0,
        "multi_acoustic_speaker_count_authority_asr_independent": True,
        "multi_acoustic_word_attribution_uses_asr_timeline": True,
    }
    text = _receipt_text(state, lang)
    speaker_label = "Số người nói nhận diện" if lang == "vi" else "Detected speakers"
    voice_label = "Số giọng lồng tiếng đã dùng" if lang == "vi" else "Dubbing voices used"
    assert f"{speaker_label}: <b>{count}</b>" in text
    assert f"{voice_label}: <b>{count}</b>" in text
    unverified = _receipt_text({**state, "auto_multi_voice_verified": False}, lang)
    assert f"{voice_label}: <b>{count}</b>" not in unverified
