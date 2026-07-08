from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    marker = f"def {name}("
    async_marker = f"async def {name}("
    start = BOT_SOURCE.find(marker)
    if start < 0:
        start = BOT_SOURCE.index(async_marker)
    next_def = BOT_SOURCE.find("\ndef ", start + len(marker))
    next_async = BOT_SOURCE.find("\nasync def ", start + len(marker))
    candidates = [item for item in (next_def, next_async) if item >= 0]
    next_start = min(candidates) if candidates else -1
    if next_start < 0:
        return BOT_SOURCE[start:]
    return BOT_SOURCE[start:next_start]


def test_m4live7_subtitle_only_pipeline_shape_preserved():
    core_source = _function_source("_execute_video_dubbing_pipeline_core")
    ass_source = _function_source("subdub_generate_ass_from_srt")

    assert "subdub_dub_speech_config" in core_source
    assert "synthesize_dub_segment_chunks(*args, allow_admin=is_admin_user(uid), **kwargs)" in core_source
    assert "run_subdub_pipeline" not in ass_source


def test_m4live7_subtitle_bottom_position_lower_than_previous_safe_gap():
    normalize_source = _function_source("subdub_normalize_style")
    ass_source = _function_source("subdub_generate_ass_from_srt")

    assert 'style["subtitle_alignment"] = "bottom_center"' in normalize_source
    assert 'style["subtitle_max_lines"] = 2' in normalize_source
    assert 'style["subtitle_margin_v_after"] = max(1, min(3' in normalize_source
    assert "if style.get(\"m4live1_style_renderer_only\"):" in ass_source
    assert 'margin_v = int(style.get("subtitle_margin_v_after") or 0)' in ass_source
    assert "subtitle_margin_v_effective" in ass_source


def test_m4live7_subtitle_max_two_lines_no_three_line_overlap():
    ass_source = _function_source("subdub_generate_ass_from_srt")
    wrap_source = _function_source("subdub_ass_wrap_text")
    chunk_source = _function_source("subdub_ass_text_chunks")

    assert 'f"; subtitle_max_lines: {int(style.get(\'max_lines\') or 2)}"' in ass_source
    assert "WrapStyle: 2" in ass_source
    assert "limit = max(1, int(max_lines or 2))" in wrap_source
    assert "line_limit = max(1, min(2, int(max_lines or 2)))" in chunk_source
    assert "overlap_suppressed" in ass_source


def test_m4live7_dub_success_uses_video_delivery_not_stale_public_failure():
    helper_source = _function_source("subdub_result_has_delivered_video")
    receipt_source = _function_source("video_dubbing_receipt_text")
    confirm_source = _function_source("handle_video_dubbing_callback")

    assert "video_delivery_message_id" in helper_source
    assert "sent_video_document" in helper_source
    assert "delivered_video = subdub_result_has_delivered_video(result)" in receipt_source
    assert "public_failure_overridden_by_video_delivery=True" in confirm_source
    assert 'result["terminal_public_outcome_type"] = "success"' in confirm_source
    assert "subdub_mode_fail_text(mode, lang)" in receipt_source


def test_m4live7_dub_status_full_green_after_video_delivery():
    confirm_source = _function_source("handle_video_dubbing_callback")
    lifecycle_source = _function_source("subdub_completed_steps_for_lifecycle")

    assert 'terminal_state="delivered"' in confirm_source
    assert "progress_percent=100" in confirm_source
    assert 'completed_steps=subdub_completed_steps_for_lifecycle("delivered", "delivered")' in confirm_source
    assert "status_panel_terminalized=True" in confirm_source
    assert "panel_final_percent=100" in confirm_source
    assert 'if terminal == "delivered":' in lifecycle_source
    assert 'item.get("key") != "delivered"' in lifecycle_source


def test_m4live7_dub_receipt_contains_voice_line_like_subtitle_receipt():
    receipt_source = _function_source("video_dubbing_receipt_text")
    voice_label_source = _function_source("subdub_receipt_voice_label")

    assert "subdub_receipt_voice_label" in receipt_source
    assert "• Giọng:" in receipt_source
    assert "• Voice:" in receipt_source
    assert "Giọng nữ" in voice_label_source
    assert "Giọng nam" in voice_label_source
    assert "Đã gửi video" in receipt_source


def test_m4live7_female_voice_mapping_does_not_silently_fallback_to_male():
    voice_source = _function_source("resolve_video_dub_tts_voice")
    gender_source = _function_source("subdub_voice_gender_from_state")

    assert '"giong nu"' in gender_source
    assert "default_gender_requested" in voice_source
    assert "get_tts_voice_id(f\"default_{gender}\") or get_tts_voice_id(gender)" in voice_source
    assert '"selected_voice_gender_unavailable"' in voice_source
    assert "SUBDUB_ALLOW_SILENT_VOICE_FALLBACK" in voice_source


def test_m4live7_over_30_seconds_supported_or_blocked_before_pipeline():
    duration_source = _function_source("subdub_duration_gate_payload")

    assert 'PIPELINE_MAX_DURATION_SECONDS_PUBLIC = max(1, env_int("PIPELINE_MAX_DURATION_SECONDS_PUBLIC", 300))' in BOT_SOURCE
    assert 'SUBDUB_MAX_DURATION_SECONDS = max(1, env_int("SUBDUB_MAX_DURATION_SECONDS", PIPELINE_MAX_DURATION_SECONDS_PUBLIC))' in BOT_SOURCE
    assert 'SUBDUB_PREVIEW_DURATION_SECONDS = max(1, env_int("SUBDUB_PREVIEW_DURATION_SECONDS", 30))' in BOT_SOURCE
    assert '"pass_long" if long_allowed' in duration_source
    assert '"blocked_clean" if over_limit' in duration_source
    assert '"duration_guard_stage": "after_input_save"' in duration_source


def test_m4live7_no_real_provider_calls_in_touched_helpers():
    touched = "\n".join(
        [
            _function_source("subdub_result_has_delivered_video"),
            _function_source("subdub_receipt_voice_label"),
            _function_source("video_dubbing_receipt_text"),
            _function_source("subdub_normalize_style"),
            _function_source("subdub_generate_ass_from_srt"),
        ]
    )

    assert "synthesize_text_to_audio" not in touched
    assert "requests." not in touched
    assert "httpx." not in touched
