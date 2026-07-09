import asyncio
import time

import bot
import pytest


@pytest.fixture(autouse=True)
def _restore_subdub_jobs():
    original = dict(bot.SUBTITLE_DUB_PIPELINE_JOBS)
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    yield
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    bot.SUBTITLE_DUB_PIPELINE_JOBS.update(original)


def test_dub_output_stage_generic_fail_line_is_suppressed(monkeypatch):
    monkeypatch.setattr(bot, "persist_subtitle_dub_pipeline_job_snapshot", lambda *args, **kwargs: True)
    key = "42|chat|video|dub_audio"
    bot.SUBTITLE_DUB_PIPELINE_JOBS[key] = {
        "job_key": key,
        "user_id": 42,
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "progress_stage": "generating_voice",
        "lifecycle_state": "generating_voice",
        "progress_percent": 65,
        "updated_at": time.time(),
    }
    sent = []

    class Message:
        async def reply_text(self, text, **kwargs):
            sent.append(text)
            return type("Sent", (), {"message_id": 321})()

    result = asyncio.run(
        bot.send_subdub_fail_once(
            Message(),
            key,
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            reason="subdub_failed",
            lang="vi",
        )
    )

    assert result["suppressed"] is True
    assert sent == []
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[key]["public_error_sent"] is False


def test_dub_input_save_failure_still_sends_clean_failure(monkeypatch):
    monkeypatch.setattr(bot, "persist_subtitle_dub_pipeline_job_snapshot", lambda *args, **kwargs: True)
    key = "42|chat|video|dub_audio"
    bot.SUBTITLE_DUB_PIPELINE_JOBS[key] = {
        "job_key": key,
        "user_id": 42,
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "status": "running",
        "progress_stage": "received_file",
        "lifecycle_state": "received_file",
        "progress_percent": 5,
        "updated_at": time.time(),
    }
    sent = []

    class Message:
        async def reply_text(self, text, **kwargs):
            sent.append(text)
            return type("Sent", (), {"message_id": 322})()

    result = asyncio.run(
        bot.send_subdub_fail_once(
            Message(),
            key,
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            reason="large_telegram_download_unsupported",
            lang="vi",
        )
    )

    assert result["sent"] is True
    assert sent


def test_dub_tts_retries_slower_when_audio_finishes_before_cue(monkeypatch):
    calls = []

    async def fake_tts(text, voice_style="", voice_id="", voice_speed="1.0", allow_admin=False):
        calls.append(float(voice_speed))
        if len(calls) == 1:
            return "fake", b"fast", "ok"
        return "fake", b"slow", "ok"

    async def fake_duration(audio_bytes, suffix=".mp3"):
        return 1.0 if audio_bytes == b"fast" else 3.4

    monkeypatch.setattr(bot, "video_dubbing_tts_bytes", fake_tts)
    monkeypatch.setattr(bot, "video_dubbing_audio_duration_seconds", fake_duration)

    result = asyncio.run(
        bot.synthesize_dub_segment_chunks(
            [{"index": 1, "start": 0.0, "end": 4.0, "text": "Xin chào TOAN AAS"}],
            voice_style="Giọng nữ",
            voice_id="female-real-voice",
            base_speed=1.0,
            max_speed=1.0,
            allow_admin=True,
        )
    )

    assert len(calls) == 2
    assert calls[0] == 1.0
    assert 0.7 <= calls[1] < 1.0
    assert result["chunks"][0]["audio_duration"] == 3.4
    assert result["chunks"][0]["speed"] == round(calls[1], 3)


def test_subtitle_ass_bottom_gap_and_original_timing_preserved(monkeypatch):
    monkeypatch.setattr(bot, "resolve_subdub_subtitle_font", lambda style: {"ok": True, "family": "Arial", "path": "", "blocker": ""})
    style = bot.subdub_normalize_style(
        {
            "output_type": "burn",
            "video_width": 1280,
            "video_height": 720,
        }
    )
    assert 6 <= int(style["subtitle_margin_v_after"]) <= 14
    assert int(style["subtitle_margin_v_after"]) > 3

    ass = bot.subdub_generate_ass_from_srt(
        "1\n00:00:00,000 --> 00:00:05,000\nĐây là phụ đề dịch cần bám đúng thời gian gốc.\n",
        style,
    )

    assert ass.count("Dialogue:") == 1
    assert "0:00:00.00,0:00:05.00" in ass
    assert "subtitle_margin_v_effective" in ass


def test_female_voice_request_does_not_use_stale_male(monkeypatch):
    monkeypatch.setattr(bot.minimax_voice_adapter, "validate_provider_voice_id", lambda value: bool(value))
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "female-real-voice")
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "male-real-voice")
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "voice_style": "Giọng nữ",
        "voice_kind": "default_female",
        "voice_id": "male-real-voice",
        "selected_voice_id": "male-real-voice",
    }

    resolution = bot.resolve_video_dub_tts_voice(42, state)

    assert resolution["ok"] is True
    assert resolution["provider_voice_id"] == "female-real-voice"
    assert resolution["resolved_gender"] == "female"
    assert state["selected_tts_voice_id"] == "female-real-voice"


def test_subdub_duration_gate_supports_300_seconds_without_30s_block():
    payload = bot.subdub_duration_gate_payload({"duration": 300}, {}, is_admin=False)
    over = bot.subdub_duration_gate_payload({"duration": 301}, {}, is_admin=False)

    assert payload["duration_limit_seconds"] >= 300
    assert payload["duration_gate_result"] == "pass_long"
    assert payload["chunking_enabled"] is True
    assert payload["chunk_count"] >= 10
    assert over["duration_gate_result"] == "fail_over_limit"
