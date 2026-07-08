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


def test_m4live8b_subtitle_only_ass_restored_to_m4live7_text_chunking():
    source = _function_source("subdub_generate_ass_from_srt")

    assert "subtitle_timing_preserved: yes" not in source
    assert "subtitle_text_length_duration_split: no" not in source
    assert "subdub_ass_text_chunks" in source
    assert "total_weight" in source
    assert "elapsed_weight" in source
    assert "chunk_start = block_start + ((block_end - block_start)" in source
    assert "subdub_ass_timestamp(chunk_start)" in source
    assert "subdub_ass_timestamp(chunk_end)" in source


def test_m4live8b_subtitle_only_no_single_cue_timing_override():
    source = _function_source("subdub_generate_ass_from_srt")

    assert "Long text wraps; it must not shorten the cue." not in source
    assert "last_dialogue_end = max(last_dialogue_end, chunk_end)" in source
    assert "subdub_ass_wrap_text(chunk, style" in source


def test_m4live8_generic_active_job_suppress_helper_removed_by_m4live8f():
    assert "def subdub_should_suppress_generic_fail_for_active_job" not in BOT_SOURCE


def test_m4live8_chunk_plan_helper_removed_by_m4live8f():
    assert "def subdub_long_video_chunk_plan" not in BOT_SOURCE


def test_m4live8_send_fail_once_uses_m4live7_failure_path():
    class DummyMessage:
        def __init__(self):
            self.texts = []

        async def reply_text(self, *_args, **_kwargs):
            self.texts.append(_args[0])
            return type("Msg", (), {"message_id": "fail"})()

    key = "m4live8-active-suppress"
    bot.SUBTITLE_DUB_PIPELINE_JOBS[key] = {
        "job_key": key,
        "status": "running",
        "terminal_state": "",
        "progress_stage": "generating_voice",
        "progress_percent": 65,
    }
    message = DummyMessage()
    try:
        result = asyncio.run(
            bot.send_subdub_fail_once(
                message,
                key,
                mode=bot.VIDEO_SUBTITLE_MODE_DUB,
                reason="late_generic",
            )
        )
        job = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
        assert result["sent"] is True
        assert result["suppressed"] is False
        assert message.texts
        assert job["public_error_sent"] is True
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


def test_m4live8_long_video_chunk_plan_not_used_after_m4live8f_restore():
    assert "subdub_long_video_chunk_plan(" not in BOT_SOURCE


def test_m4live8_duration_gate_reports_m4live7_long_video_without_chunks():
    payload = bot.subdub_duration_gate_payload({"duration": 75}, {}, is_admin=False)

    assert payload["duration_gate_result"] == "pass_long"
    assert payload["long_media_allowed"] is True
    assert "chunking_enabled" not in payload
    assert "chunk_count" not in payload
    assert "concat_required" not in payload
    assert "global_timing_preserved" not in payload


def test_m4live8_large_telegram_copy_restored_to_m4live7_baseline():
    text = bot.subdub_large_telegram_media_public_text("vi")

    assert "file quá lớn" in text
    assert "chưa trừ Xu" in text
    assert "video ngắn/nhẹ hơn" in text
    assert "thử video rõ tiếng hơn" not in text


def test_m4live8_no_real_provider_calls_in_touched_helpers():
    touched = "\n".join(
        [
            _function_source("subdub_generate_ass_from_srt"),
            _function_source("send_subdub_fail_once"),
            _function_source("subdub_duration_gate_payload"),
        ]
    )

    assert "requests." not in touched
    assert "httpx." not in touched
    assert "shopaikey" not in touched.lower()
    assert "key4u" not in touched.lower()
