from pathlib import Path

import asyncio

import bot


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
    return BOT_SOURCE[start:] if next_start < 0 else BOT_SOURCE[start:next_start]


def test_m4live8_ass_preserves_original_start_end_not_text_weight_duration():
    source = _function_source("subdub_generate_ass_from_srt")

    assert "subtitle_timing_preserved: yes" in source
    assert "subtitle_text_length_duration_split: no" in source
    assert "total_weight" not in source
    assert "elapsed_weight" not in source
    assert "chunk_start = block_start + ((block_end - block_start)" not in source
    assert "subdub_ass_timestamp(block_start)" in source
    assert "subdub_ass_timestamp(block_end)" in source


def test_m4live8_long_translation_text_does_not_shorten_last_segment():
    source = _function_source("subdub_generate_ass_from_srt")

    assert "Long text wraps; it must not shorten the cue." in source
    assert "last_dialogue_end = max(last_dialogue_end, block_end)" in source
    assert "subdub_ass_wrap_text(str(block.get(\"text\") or \"\"), style" in source


def test_m4live8_processing_65_suppresses_generic_fail_text():
    job = {
        "status": "running",
        "terminal_state": "",
        "progress_stage": "generating_voice",
        "progress_percent": 65,
    }

    assert bot.subdub_should_suppress_generic_fail_for_active_job(job, {"status": "NO_OUTPUT_BYTES"})


def test_m4live8_early_terminal_input_error_not_suppressed():
    job = {
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "progress_stage": "input_save_failed",
        "progress_percent": 5,
    }

    assert not bot.subdub_should_suppress_generic_fail_for_active_job(job, {"status": "INPUT_SAVE_FAILED"})


def test_m4live8_send_fail_once_suppresses_active_or_delivered_job():
    class DummyMessage:
        async def reply_text(self, *_args, **_kwargs):
            raise AssertionError("generic public fail should not be sent")

    key = "m4live8-active-suppress"
    bot.SUBTITLE_DUB_PIPELINE_JOBS[key] = {
        "job_key": key,
        "status": "running",
        "terminal_state": "",
        "progress_stage": "generating_voice",
        "progress_percent": 65,
    }
    try:
        result = asyncio.run(
            bot.send_subdub_fail_once(
                DummyMessage(),
                key,
                mode=bot.VIDEO_SUBTITLE_MODE_DUB,
                reason="late_generic",
            )
        )
        job = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
        assert result["suppressed"] is True
        assert job["generic_fail_suppressed_while_active_or_delivered"] is True
        assert job["public_error_sent"] is False
    finally:
        bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)


def test_m4live8_subdub_female_voice_uses_strict_female_default(monkeypatch):
    monkeypatch.setattr(bot.minimax_voice_adapter, "validate_provider_voice_id", lambda value: bool(value))
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "female-real-voice")
    monkeypatch.setattr(bot, "MINIMAX_DEFAULT_FEMALE_VOICE_ID", "female-real-voice")
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "male-real-voice")
    monkeypatch.setattr(bot, "MINIMAX_DEFAULT_MALE_VOICE_ID", "male-real-voice")

    state = bot.video_dubbing_voice_payload("default_female", None, "vi")
    resolution = bot.resolve_video_dub_tts_voice(123, state)

    assert state["selected_voice_gender"] == "female"
    assert resolution["ok"] is True
    assert resolution["provider_voice_id"] == "female-real-voice"
    assert resolution["resolved_gender"] == "female"
    assert resolution["fallback_used"] is False


def test_m4live8_missing_female_voice_blocks_instead_of_male_fallback(monkeypatch):
    monkeypatch.setattr(bot.minimax_voice_adapter, "validate_provider_voice_id", lambda value: bool(value))
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "")
    monkeypatch.setattr(bot, "MINIMAX_DEFAULT_FEMALE_VOICE_ID", "")
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "male-real-voice")
    monkeypatch.setattr(bot, "MINIMAX_DEFAULT_MALE_VOICE_ID", "male-real-voice")

    state = {
        "voice_kind": "default_female",
        "voice_style": "giọng nữ mặc định",
        "selected_voice_gender": "female",
        "requested_voice_gender": "female",
        "voice_id": "male-real-voice",
    }
    resolution = bot.resolve_video_dub_tts_voice(123, state)

    assert resolution["ok"] is False
    assert resolution["reason"] == "selected_voice_gender_unavailable"
    assert state.get("selected_tts_voice_id", "") != "male-real-voice"


def test_m4live8_long_video_chunk_plan_for_43s_and_75s():
    short = bot.subdub_long_video_chunk_plan(24)
    forty_three = bot.subdub_long_video_chunk_plan(43)
    seventy_five = bot.subdub_long_video_chunk_plan(75)

    assert short["chunking_enabled"] is False
    assert forty_three["chunking_enabled"] is True
    assert forty_three["chunk_count"] == 2
    assert forty_three["chunk_ranges"] == [
        {"index": 1, "start": 0, "end": 30},
        {"index": 2, "start": 30, "end": 43},
    ]
    assert seventy_five["chunk_count"] == 3
    assert seventy_five["concat_required"] is True
    assert seventy_five["global_timing_preserved"] is True


def test_m4live8_duration_gate_reports_long_video_chunks():
    payload = bot.subdub_duration_gate_payload({"duration": 75}, {}, is_admin=False)

    assert payload["duration_gate_result"] == "pass_long"
    assert payload["long_media_allowed"] is True
    assert payload["chunking_enabled"] is True
    assert payload["chunk_count"] == 3
    assert payload["concat_required"] is True
    assert payload["global_timing_preserved"] is True


def test_m4live8_large_telegram_copy_not_generic_or_shorter_video_blame():
    text = bot.subdub_large_telegram_media_public_text("vi")

    assert "chưa tải trực tiếp được file này từ Telegram" in text
    assert "chưa trừ Xu" in text
    assert "video ngắn/nhẹ hơn" not in text
    assert "thử video rõ tiếng hơn" not in text


def test_m4live8_no_real_provider_calls_in_touched_helpers():
    touched = "\n".join(
        [
            _function_source("subdub_generate_ass_from_srt"),
            _function_source("subdub_should_suppress_generic_fail_for_active_job"),
            _function_source("subdub_long_video_chunk_plan"),
            _function_source("subdub_default_tts_voice_for_gender"),
        ]
    )

    assert "requests." not in touched
    assert "httpx." not in touched
    assert "shopaikey" not in touched.lower()
    assert "key4u" not in touched.lower()
