from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT = (ROOT / "bot.py").read_text(encoding="utf-8")


def function_source(name: str) -> str:
    marker = f"def {name}("
    async_marker = f"async def {name}("
    start = BOT.find(marker)
    if start < 0:
        start = BOT.find(async_marker)
    assert start >= 0, name
    next_def = BOT.find("\ndef ", start + 1)
    next_async = BOT.find("\nasync def ", start + 1)
    endings = [item for item in (next_def, next_async) if item >= 0]
    return BOT[start:min(endings) if endings else len(BOT)]


def test_subdub_video_success_sets_delivery_success_lock():
    source = function_source("mark_subtitle_dub_pipeline_output_sent")
    assert 'job["delivery_succeeded"] = True' in source
    assert 'job["public_success_sent"] = True' in source
    assert 'job["final_video_message_id"]' in source


def test_no_public_failure_or_generic_x_after_video_success():
    fail_source = function_source("send_subdub_fail_once")
    error_source = function_source("subdub_should_suppress_outer_error")
    assert "subdub_should_suppress_late_public_failure(job)" in fail_source
    assert '"public_failure_sent"] = False' in fail_source
    assert "late_error_after_video_success" in error_source


def test_no_srt_partial_copy_after_success_video():
    source = function_source("send_public_subtitle_dub_final_outputs")
    assert "subdub_should_skip_public_subtitle_fallback" in source
    assert 'sent["srt_fallback_suppressed"] = True' in source
    assert 'sent["auto_srt_after_video_prevented"] = True' in source


def test_female_voice_reaches_segment_tts_without_male_fallback():
    resolver = function_source("resolve_video_dub_tts_voice")
    pipeline = (ROOT / "services" / "subtitle_dub_product_pipeline.py").read_text(encoding="utf-8")
    assert 'get_tts_voice_id("default_female")' in resolver
    assert "selected_voice_gender_unavailable" in resolver
    assert "voice_id=selected_tts_voice_id" in pipeline


def test_subtitle_size_is_moderate_bottom_center_and_wraps():
    size_source = function_source("subdub_render_subtitle_size")
    ass_source = function_source("subdub_generate_ass_from_srt")
    wrap_source = function_source("subdub_ass_wrap_text")
    assert "live_effective_before - 2" in size_source
    assert "frame_cap" in size_source
    assert "subdub_ass_alignment" in ass_source
    assert "subdub_ass_wrap_text" in ass_source
    assert "play_res_x * 0.76" in wrap_source


def test_audio_controls_are_split_and_accept_numeric_input():
    keyboard = function_source("subdub_audio_mix_keyboard")
    handler = function_source("handle_video_dubbing_pending_text")
    assert "audio_original" in keyboard
    assert "audio_dub" in keyboard
    assert "subdub_original_volume_input" in handler
    assert "subdub_dub_volume_input" in handler
    assert "maximum = 100 if layer == \"original\" else 200" in handler


def test_delivered_video_terminalizes_panel_at_full_green():
    callback = function_source("handle_video_dubbing_callback")
    assert 'subdub_progress_text("delivered"' in callback
    assert "progress_percent=100" in callback
    assert "panel_final_percent=100" in callback
    assert "refresh_stopped_after_terminal=True" in callback


def test_final_receipt_has_product_duration_and_cost():
    source = function_source("video_dubbing_receipt_text")
    assert "• Kết quả:" in source
    assert "• Thời lượng:" in source
    assert "subdub_success_cost_line" in source
