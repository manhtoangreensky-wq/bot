import asyncio
import time

import bot
import pytest


@pytest.fixture(autouse=True)
def _restore_subdub_state():
    original_jobs = dict(bot.SUBTITLE_DUB_PIPELINE_JOBS)
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    yield
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    bot.SUBTITLE_DUB_PIPELINE_JOBS.update(original_jobs)


def test_pr330_mode_alias_dub_video_suppresses_late_public_fail(monkeypatch):
    monkeypatch.setattr(bot, "persist_subtitle_dub_pipeline_job_snapshot", lambda *args, **kwargs: True)
    key = "42|chat|video|dub_audio"
    bot.SUBTITLE_DUB_PIPELINE_JOBS[key] = {
        "job_key": key,
        "user_id": 42,
        "mode": bot.SUBDUB_CANONICAL_MODE_DUB,
        "mapped_mode": bot.SUBDUB_CANONICAL_MODE_DUB,
        "status": "running",
        "progress_stage": "generating_voice",
        "lifecycle_state": "generating_voice",
        "progress_percent": 65,
        "updated_at": time.time(),
    }
    sent = []

    class Message:
        async def reply_text(self, text, **kwargs):
            sent.append(text)
            return type("Sent", (), {"message_id": 123})()

    result = asyncio.run(
        bot.send_subdub_fail_once(
            Message(),
            "42|chat|video|different_key",
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            reason="subdub_failed",
            lang="vi",
        )
    )

    assert result["suppressed"] is True
    assert sent == []
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[key]["generic_fail_suppressed_while_active_or_delivered"] is True


def test_pr330_mode_alias_subtitle_dub_video_suppresses_late_public_fail(monkeypatch):
    monkeypatch.setattr(bot, "persist_subtitle_dub_pipeline_job_snapshot", lambda *args, **kwargs: True)
    key = "42|chat|video|subtitle_dub"
    bot.SUBTITLE_DUB_PIPELINE_JOBS[key] = {
        "job_key": key,
        "user_id": 42,
        "mode": bot.SUBDUB_CANONICAL_MODE_SUBTITLE_DUB,
        "mapped_mode": bot.SUBDUB_CANONICAL_MODE_SUBTITLE_DUB,
        "status": "running",
        "progress_stage": "muxing_subtitle_dub_video",
        "lifecycle_state": "muxing_subtitle_dub_video",
        "progress_percent": 65,
        "updated_at": time.time(),
    }
    sent = []

    class Message:
        async def reply_text(self, text, **kwargs):
            sent.append(text)
            return type("Sent", (), {"message_id": 124})()

    result = asyncio.run(
        bot.send_subdub_fail_once(
            Message(),
            "42|chat|video|different_key",
            mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            reason="video_render_failed",
            lang="vi",
        )
    )

    assert result["suppressed"] is True
    assert sent == []
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[key]["public_error_sent"] is False


def test_pr330_subdub_language_labels_do_not_fall_back_to_vietnamese():
    assert bot.normalize_translate_target("日本語") == "ja"
    assert bot.normalize_translate_target("中文") == "zh"
    assert bot.normalize_translate_target("한국어") == "ko"
    assert bot.translate_target_label("日本語") == bot.translate_target_label("ja")


def test_pr330_translate_segments_preserves_source_cue_timing(monkeypatch):
    async def fake_translate(text, target_language, allow_admin=False, updated_by=""):
        return {"provider": "fixture", "text": f"Dich: {text}", "target": target_language}

    monkeypatch.setattr(bot, "translate_subtitle_text", fake_translate)
    source = [
        {"index": 1, "start": 0.2, "end": 2.9, "text": "first source cue"},
        {"index": 2, "start": 5.0, "end": 8.25, "text": "second source cue"},
    ]

    result = asyncio.run(bot.translate_subtitle_segments(source, "日本語", allow_admin=True, updated_by=42))

    assert [item["start"] for item in result["segments"]] == [0.2, 5.0]
    assert [item["end"] for item in result["segments"]] == [2.9, 8.25]
    assert "00:00:00,200 --> 00:00:02,900" in result["srt"]
    assert "00:00:05,000 --> 00:00:08,250" in result["srt"]


def test_pr330_female_minimax_voice_id_uses_minimax_route_before_openai(monkeypatch):
    calls = []
    monkeypatch.setattr(bot, "TTS_PROVIDER", "auto")
    monkeypatch.setattr(bot.minimax_voice_adapter, "validate_provider_voice_id", lambda value: bool(value))
    monkeypatch.setattr(bot, "key4u_minimax_tts_public_ready", lambda: True)
    monkeypatch.setattr(bot, "shopaikey_minimax_tts_public_ready", lambda: False)
    monkeypatch.setattr(bot, "direct_minimax_tts_public_ready", lambda: False)
    monkeypatch.setattr(bot, "KEY4U_ENABLED", True)
    monkeypatch.setattr(bot, "KEY4U_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "KEY4U_API_KEY", "key")
    monkeypatch.setattr(bot, "KEY4U_AUDIO_SPEECH_ENDPOINT", "/audio/speech")

    async def fake_key4u_minimax(text, voice_id="", voice_style="", voice_speed="1.0", allow_admin=False):
        calls.append(("minimax", voice_id, voice_speed))
        return "PASS", b"female-audio", "ok", 200

    async def fake_openai_tts(*args, **kwargs):
        calls.append(("openai", kwargs.get("voice"), kwargs.get("speed")))
        return "PASS", b"openai-audio", "ok", 200

    monkeypatch.setattr(bot, "call_key4u_minimax_tts_bytes_with_speed", fake_key4u_minimax)
    monkeypatch.setattr(bot, "openai_compatible_tts_speech_bytes", fake_openai_tts)

    provider, audio, _detail = asyncio.run(
        bot.video_dubbing_tts_bytes(
            "Xin chao",
            voice_style="Giọng nữ",
            voice_id="female-real-voice",
            voice_speed="1.0",
            allow_admin=False,
        )
    )

    assert provider == "Key4U MiniMax"
    assert audio == b"female-audio"
    assert calls == [("minimax", "female-real-voice", "1.0")]
