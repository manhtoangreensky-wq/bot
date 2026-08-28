import asyncio
from types import SimpleNamespace

import bot
from services import subtitle_dub_product_pipeline

class CaptureMessage:
    def __init__(self):
        self.texts = []

    async def reply_text(self, text, **kwargs):
        self.texts.append(str(text))
        return SimpleNamespace(message_id=len(self.texts), chat_id=123)


def test_subtitle_translate_preserve_timestamps_keeps_original_cue_duration():
    segments = [
        {
            "start": 2.0,
            "end": 8.5,
            "text": "Đây là câu phụ đề dịch khá dài nhưng vẫn phải bám đúng thời gian của phụ đề gốc",
        }
    ]

    qc = bot.video_dubbing_qc_segments(segments, preserve_timestamps=True)

    assert len(qc) == 1
    assert qc[0]["start"] == 2.0
    assert qc[0]["end"] == 8.5
    assert len(qc[0]["text"].splitlines()) <= 2


def test_ass_bottom_subtitle_uses_single_dialogue_for_original_cue_timing():
    srt = (
        "1\n"
        "00:00:02,000 --> 00:00:08,500\n"
        "Đây là câu phụ đề dịch khá dài nhưng vẫn phải bám đúng thời gian của phụ đề gốc\n"
    )

    ass = bot.subdub_generate_ass_from_srt(
        srt,
        {
            "m4live2_subtitle_bottom_lock": True,
            "m4live1_style_renderer_only": True,
            "show_subtitles": True,
            "font": "Arial",
            "subtitle_font_resolution_ok": True,
        },
    )

    dialogues = [line for line in ass.splitlines() if line.startswith("Dialogue:")]
    assert len(dialogues) == 1
    assert "0:00:02.00,0:00:08.50" in dialogues[0]


def test_subdub_dub_speech_rate_never_exceeds_normal_speed():
    config = bot.subdub_dub_speech_config({"voice_speed": "1.35"}, "1.35")

    assert config["dub_speech_rate"] <= 1.0
    assert config["dub_max_speech_rate"] <= 1.0


def test_subdub_service_keeps_manual_cap_and_scopes_auto_cue_fit():
    assert subtitle_dub_product_pipeline._cue_locked_timing_requested({"voice_kind": "default_female"}) is False
    assert subtitle_dub_product_pipeline._cue_locked_timing_requested({"voice_kind": "auto_speaker_gender"}) is True
    assert subtitle_dub_product_pipeline._cue_locked_timing_requested({"auto_speaker_lane": "multi"}) is False


def test_synthesize_dub_segment_chunks_does_not_retry_above_1x(monkeypatch):
    calls = []

    async def fake_tts(text, voice_style, voice_id, speed, allow_admin=False):
        calls.append(float(speed))
        return "fake", b"audio", "ok"

    async def fake_duration(_audio):
        return 12.0

    monkeypatch.setattr(bot, "video_dubbing_tts_bytes", fake_tts)
    monkeypatch.setattr(bot, "video_dubbing_audio_duration_seconds", fake_duration)

    result = asyncio.run(
        bot.synthesize_dub_segment_chunks(
            [{"start": 0, "end": 3, "text": "Xin chào, đây là lời lồng tiếng"}],
            voice_style="Giọng nữ",
            voice_id="female-real-voice",
            base_speed=1.35,
            max_speed=1.35,
            allow_admin=True,
        )
    )

    assert calls == [1.0]
    assert result["chunks"][0]["speed"] == 1.0
    assert result["chunks"][0]["text"] == "Xin chào, đây là lời lồng tiếng"


def test_dub_generic_video_failure_is_not_sent_to_public(monkeypatch):
    monkeypatch.setattr(bot, "persist_subtitle_dub_pipeline_job_snapshot", lambda *args, **kwargs: True)
    message = CaptureMessage()

    result = asyncio.run(
        bot.send_subdub_fail_once(
            message,
            "322|dub|generic-output-fail",
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            reason="FINAL_VIDEO_NOT_CREATED",
            lang="vi",
        )
    )

    assert result["suppressed"] is True
    assert result["reason"] == "generic_dub_video_fail_public_suppressed"
    assert message.texts == []


def test_true_input_download_failure_still_reports_clean_public_fail(monkeypatch):
    monkeypatch.setattr(bot, "persist_subtitle_dub_pipeline_job_snapshot", lambda *args, **kwargs: True)
    message = CaptureMessage()

    result = asyncio.run(
        bot.send_subdub_fail_once(
            message,
            "322|dub|input-fail",
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            reason="telegram_download_failed",
            lang="vi",
        )
    )

    assert result["sent"] is True
    assert len(message.texts) == 1
    assert "chưa tạo được video hoàn chỉnh" in message.texts[0]


def test_default_female_voice_resolves_to_female_provider_id(monkeypatch):
    monkeypatch.setattr(bot.minimax_voice_adapter, "validate_provider_voice_id", lambda value: bool(value))
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "female-real-voice")
    monkeypatch.setattr(bot, "MINIMAX_DEFAULT_FEMALE_VOICE_ID", "female-real-voice")
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "male-real-voice")
    monkeypatch.setattr(bot, "MINIMAX_DEFAULT_MALE_VOICE_ID", "male-real-voice")

    state = bot.video_dubbing_voice_payload("default_female", None, "vi")
    resolution = bot.resolve_video_dub_tts_voice(123, state)

    assert resolution["ok"] is True
    assert resolution["provider_voice_id"] == "female-real-voice"
    assert resolution["resolved_gender"] == "female"
    assert state["selected_tts_voice_id"] == "female-real-voice"
