import asyncio
from pathlib import Path

import bot


class CaptureMessage:
    def __init__(self):
        self.chat_id = 123
        self.calls = []

    async def reply_text(self, text, **kwargs):
        self.calls.append(("text", text, kwargs))
        return type("Msg", (), {"message_id": len(self.calls)})()


def test_subdub_accepts_50mb_300s_video():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "video_file_size": 50 * 1024 * 1024,
        "video_duration": 300,
    }
    assert bot.SUBDUB_INPUT_MAX_MB == 50
    assert bot.SUBDUB_OUTPUT_MAX_MB == 50
    assert bot.subdub_duration_limit_seconds(False) == 300
    assert bot.subtitle_plus_dub_exceeds_limits(state, admin=False) is False


def test_subdub_rejects_over_300s_clean_no_charge():
    validation = bot.subdub_media_limit_validation(
        size_bytes=10 * 1024 * 1024,
        duration_seconds=301,
        is_admin=False,
    )
    assert validation["ok"] is False
    assert validation["blocker"] == "duration_too_long"
    text = bot.subdub_clean_failure_text("vi", validation["blocker"])
    assert "300" in text
    assert "chưa trừ Xu" in text
    assert "provider" not in text.lower()


def test_subdub_audio_extract_records_bytes_and_duration():
    payload = bot.subtitle_dub_debug_job_payload(
        user_id=1,
        chat_id=1,
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        state={"video_duration": 299, "audio_extract_bytes": 2048, "audio_extract_detail": "ffmpeg_audio_extract"},
        status="processing",
        stage="audio",
        input_save={"ok": True, "path": __file__, "size": 2048, "duration": 299, "limit_mb": 50, "duration_limit": 300},
        gate_matrix={"gate_blockers": []},
        pipeline_attempted=True,
        route_attempts={"asr": True},
    )
    assert payload["input_limit_mb"] >= 50
    assert payload["duration_limit_seconds"] == 300
    assert payload["audio_extract_bytes"] == 2048
    assert payload["duration_seconds"] == 299


def test_subdub_asr_chunking_for_long_audio(monkeypatch):
    calls = []

    async def fake_slice(audio_bytes, content_type, start, end):
        return b"chunk", f"{start}-{end}"

    async def fake_asr(audio_bytes, content_type, **kwargs):
        idx = len(calls)
        calls.append((audio_bytes, content_type, kwargs))
        return {
            "ok": True,
            "status": "PASS",
            "provider": "fake_asr",
            "text": f"cau {idx}",
            "segments": [{"start": 0.0, "end": 1.0, "text": f"cau {idx}"}],
            "language": "vi",
            "detail": "ok",
        }

    monkeypatch.setattr(bot, "subdub_slice_audio_for_asr", fake_slice)
    monkeypatch.setattr(bot, "asr_transcribe_audio", fake_asr)
    result = asyncio.run(
        bot.subdub_transcribe_audio_chunks(
            b"audio",
            "audio/mpeg",
            duration_seconds=60,
            language="auto",
            allow_admin=True,
        )
    )
    assert result["ok"] is True
    assert result["asr_chunked"] is True
    assert result["asr_chunk_count"] == len(calls)
    assert len(calls) >= 3
    assert result["segments"][1]["start"] >= 23


def test_subdub_multilingual_detects_chinese_english_vietnamese():
    assert bot.subdub_detect_language_from_text("你好世界") == "zh"
    assert bot.subdub_detect_language_from_text("Hello world, this is clear speech") == "en"
    assert bot.subdub_detect_language_from_text("Xin chào anh chị, tôi đang nói tiếng Việt") == "vi"


def test_subdub_translation_preserves_segment_timestamps(monkeypatch):
    async def fake_translate(text, target_language, **kwargs):
        return {"text": f"{target_language}:{text}", "provider": "fake_translate"}

    monkeypatch.setattr(bot, "translate_subtitle_text", fake_translate)
    segments = [{"index": 1, "start": 1.25, "end": 3.5, "text": "hello"}]
    result = asyncio.run(bot.translate_subtitle_segments(segments, "vi", allow_admin=True))
    assert result["segments"][0]["start"] == 1.25
    assert result["segments"][0]["end"] == 3.5
    assert result["provider"] == "fake_translate"
    assert "-->" in result["srt"]


def test_subdub_translation_failure_blocks_success(monkeypatch):
    async def fake_translate(text, target_language, **kwargs):
        return {"text": "", "provider": "fake_translate"}

    monkeypatch.setattr(bot, "translate_subtitle_text", fake_translate)
    try:
        asyncio.run(bot.translate_subtitle_segments([{"start": 0, "end": 1, "text": "hello"}], "vi", allow_admin=True))
    except RuntimeError as exc:
        assert "translation_empty" in str(exc)
    else:
        raise AssertionError("empty translation must block success")


def test_subdub_voice_female_exact_no_male_fallback(monkeypatch):
    monkeypatch.setattr(bot.minimax_voice_adapter, "validate_provider_voice_id", lambda value: bool(value))
    state = {
        "selected_voice_id": "female-real-voice",
        "selected_voice_gender": "female",
        "voice_style": "Giọng nữ",
    }
    resolution = bot.resolve_video_dub_tts_voice(1, state)
    assert resolution["ok"] is True
    assert resolution["provider_voice_id"] == "female-real-voice"
    assert resolution["fallback_used"] is False


def test_subdub_voice_mismatch_blocks_clean(monkeypatch):
    monkeypatch.setattr(bot.minimax_voice_adapter, "validate_provider_voice_id", lambda value: bool(value))
    state = {
        "selected_voice_id": "male-default-voice",
        "selected_voice_gender": "female",
        "voice_style": "Giọng nữ",
    }
    resolution = bot.resolve_video_dub_tts_voice(1, state)
    assert resolution["ok"] is False
    assert resolution["blocker"] == "voice_gender_mismatch"
    text = bot.subdub_clean_failure_text("vi", resolution["blocker"])
    assert "giọng" in text.lower()
    assert "provider" not in text.lower()


def test_subdub_tts_chunking_for_long_segments():
    long_text = " ".join(f"word{i}" for i in range(260))
    segments = [{"index": 1, "start": 0, "end": 65, "text": long_text}]
    split = bot.subdub_split_tts_segments(segments)
    assert len(split) >= 4
    assert all((item["end"] - item["start"]) <= bot.SUBDUB_TTS_CHUNK_SECONDS + 0.2 for item in split)
    assert split[0]["start"] == 0
    assert split[-1]["end"] == 65


def test_subdub_mux_success_requires_valid_mp4():
    ok = bot.subdub_media_limit_validation(size_bytes=49 * 1024 * 1024, duration_seconds=120, output=True)
    too_big = bot.subdub_media_limit_validation(size_bytes=51 * 1024 * 1024, duration_seconds=120, output=True)
    assert ok["ok"] is True
    assert too_big["ok"] is False
    assert too_big["blocker"] == "file_too_large"


def test_subdub_known_blocker_no_generic_red_x():
    text = bot.subdub_clean_failure_text("vi", "no_speech_detected")
    assert "❌" not in text
    assert "traceback" not in text.lower()
    assert bot.subdub_normalize_blocker("asr_failed:empty") == "asr_failed"


def test_subdub_terminal_delivered_suppresses_late_fail():
    key = "p019m7-terminal"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key, user_id=1, chat_id=1)
    assert bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered", video_delivery_message_id="777")
    message = CaptureMessage()
    result = asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_DUB, reason="asr_failed"))
    assert result["suppressed"] is True
    assert message.calls == []


def test_subdub_status_debug_contains_language_duration_fields():
    payload = bot.subdub_duration_audit_payload()
    assert payload["input_limit_mb"] == 50
    assert payload["output_limit_mb"] == 50
    assert payload["duration_limit_seconds"] == 300
    assert payload["sample_300s_chunk_count"] >= 12
    lang = bot.subdub_language_debug_payload({"state": {"source_language": "zh", "target_language": "vi", "asr_chunk_count": 3}})
    assert lang["detected_language"] == "zh"
    assert lang["target_language"] == "vi"
    assert lang["asr_chunk_count"] == 3


def test_subdub_debug_commands_registered_and_short():
    commands = {
        "subdub_status_debug",
        "subdub_pipeline_audit",
        "subdub_voice_debug",
        "subdub_delivery_debug",
        "subdub_language_debug",
        "subdub_duration_audit",
    }
    registered = set()
    with Path(bot.__file__).open("r", encoding="utf-8") as handle:
        for line in handle:
            for command in commands:
                if f'CommandHandler("{command}"' in line:
                    registered.add(command)
    assert registered == commands
    assert hasattr(bot, "cmd_subtitle_dub_debug")
    for command in commands:
        assert len(command) <= 32
