import asyncio
import re

import bot


MP4_BYTES = b"\x00\x00\x00\x18ftypmp42-p019m5" + b"x" * 4096
VALID_SRT = "1\n00:00:00,000 --> 00:00:02,000\nXin chào thế giới\n"


class CaptureMessage:
    def __init__(self, *, message_ids=True):
        self.chat_id = 123
        self.calls = []
        self.message_ids = message_ids

    def _message(self):
        if not self.message_ids:
            return object()
        return type("Msg", (), {"message_id": len(self.calls)})()

    async def reply_video(self, **kwargs):
        self.calls.append(("video", kwargs))
        return self._message()

    async def reply_document(self, **kwargs):
        self.calls.append(("document", kwargs))
        return self._message()

    async def reply_audio(self, **kwargs):
        self.calls.append(("audio", kwargs))
        return self._message()


def _labels(mode):
    return [item["label"] for item in bot.subdub_progress_steps_for_product(mode)]


def test_status_panel_subtitle_translate_mode_specific():
    labels = _labels(bot.VIDEO_SUBTITLE_MODE_TRANSLATE)
    assert labels == [
        "Nhận video",
        "Đọc phụ đề/lời thoại gốc",
        "Dịch phụ đề",
        "Gắn phụ đề vào video",
        "Kiểm tra file",
        "Gửi kết quả",
    ]
    assert "Tách âm thanh" not in labels
    assert "Tạo giọng lồng tiếng" not in labels


def test_status_panel_dub_mode_specific():
    labels = _labels(bot.VIDEO_SUBTITLE_MODE_DUB)
    assert "Tách âm thanh" in labels
    assert "Chọn giọng lồng tiếng" in labels
    assert "Tạo giọng lồng tiếng" in labels
    assert "Ghép giọng vào video" in labels
    assert "Gắn phụ đề vào video" not in labels


def test_status_panel_subtitle_dub_mode_specific():
    labels = _labels(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB)
    assert "Tạo phụ đề dịch" in labels
    assert "Chọn giọng lồng tiếng" in labels
    assert "Ghép phụ đề + giọng vào video" in labels


def test_status_panel_auto_subtitle_mode_specific():
    labels = _labels(bot.VIDEO_SUBTITLE_MODE_CREATE)
    assert "Tạo phụ đề tự động" in labels
    assert "Dịch nội dung" not in labels
    assert "Tạo giọng lồng tiếng" not in labels


def test_success_copy_exact_per_mode():
    assert bot.subdub_mode_success_text(bot.VIDEO_SUBTITLE_MODE_TRANSLATE) == "✅ Đã tạo video phụ đề dịch."
    assert bot.subdub_mode_success_text(bot.VIDEO_SUBTITLE_MODE_DUB) == "✅ Đã tạo video lồng tiếng."
    assert bot.subdub_mode_success_text(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB) == "✅ Đã tạo video phụ đề + lồng tiếng."
    assert bot.subdub_mode_success_text(bot.VIDEO_SUBTITLE_MODE_CREATE) == "✅ Đã tạo video phụ đề tự động."


def test_dub_video_delivery_does_not_send_audio_after_mp4():
    message = CaptureMessage()
    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            audio_bytes=b"audio",
            video_bytes=MP4_BYTES,
            include_subtitle_outputs=False,
        )
    )
    assert sent["video"] == 1
    assert sent["audio"] == 0
    assert sent["terminal_artifact_type"] == "video"
    assert sent["video_delivery_message_id"]
    assert [kind for kind, _payload in message.calls] == ["video"]


def test_audio_fallback_only_when_no_video_delivered(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_PUBLIC_AUDIO_FALLBACK_ENABLED", True)
    message = CaptureMessage()
    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            audio_bytes=b"audio",
            video_bytes=b"",
            include_subtitle_outputs=False,
        )
    )
    assert sent["video"] == 0
    assert sent["audio"] == 1
    assert sent["terminal_artifact_type"] == "audio_fallback"
    assert "chưa tạo được video hoàn chỉnh" in message.calls[0][1]["caption"]
    assert "đã tạo được file audio lồng tiếng" in message.calls[0][1]["caption"]


def test_auto_subtitle_sends_video_and_srt_without_audio():
    message = CaptureMessage()
    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
            srt_text=VALID_SRT,
            audio_bytes=b"audio-ignored",
            video_bytes=MP4_BYTES,
            include_subtitle_outputs=True,
        )
    )
    assert sent["video"] == 1
    assert sent["documents"] == 1
    assert sent["audio"] == 0
    assert [kind for kind, _payload in message.calls] == ["video", "document"]


def test_terminal_lock_stores_video_message_id_and_suppresses_late_fail():
    key = "p019m5-terminal-lock"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key, user_id=1, chat_id=1)
    assert bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        terminal_artifact_type="video",
        video_delivery_message_id="777",
    )
    job = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    assert job["terminal_state"] == "delivered"
    assert job["terminal_artifact_type"] == "video"
    assert job["video_delivery_message_id"] == "777"
    message = CaptureMessage()
    result = asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_DUB, reason="late"))
    assert result["suppressed"] is True
    assert message.calls == []


def test_selected_voice_id_not_replaced_by_default(monkeypatch):
    monkeypatch.setattr(bot.minimax_voice_adapter, "validate_provider_voice_id", lambda value: bool(value))
    state = {
        "selected_voice_id": "female-real-voice",
        "selected_voice_gender": "female",
        "voice_style": "Giọng nữ",
    }
    assert bot.resolve_video_dub_tts_voice_id(1, state) == "female-real-voice"
    assert state["resolved_voice_id"] == "female-real-voice"
    assert state["resolved_gender"] == "female"
    assert state["voice_fallback_used"] is False


def test_subtitle_ass_uses_moderate_boxed_readable_style():
    style = bot.subdub_normalize_style(
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            "output_type": "burn",
            "video_width": 1280,
            "video_height": 720,
        }
    )
    ass = bot.subdub_generate_ass_from_srt(VALID_SRT, style)
    font_size = int(re.search(r"Style: Default,[^,]+,(\d+),", ass).group(1))
    assert font_size >= style["size"] + 4
    assert font_size <= 64
    assert font_size >= style["size"]
    assert 1.0 <= style["subtitle_font_multiplier"] <= 1.25
    assert style["font_size_cap_applied"] in {True, False}
    assert style["boxed_background"] is True
    assert ",3," in ass
    assert style["outline"] >= 4
    assert bot.subdub_cover_filter(style) == ""


def test_dub_audio_gain_x2_configured():
    payload = bot.subdub_dub_audio_gain_debug()
    assert payload["gain"] == 2.0
    assert "volume=2.000" in payload["filter"]
    assert payload["loudness_normalize"] is True


def test_receipt_does_not_show_fail_after_video_delivery():
    text = bot.video_dubbing_receipt_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_DUB},
        {"video_delivered": True, "charged": 12, "terminal_state": "delivered"},
    )
    assert "Đã hoàn tất" in text
    assert "Thời lượng:" in text
    assert "Chi phí:" in text
    assert "Đã tạo video lồng tiếng." not in text
    assert "chưa" not in text.lower()
    assert "lỗi" not in text.lower()


def test_subdub_audit_exposes_mode_steps_style_gain_delivery():
    pipeline = bot.subdub_pipeline_audit_payload()
    style = bot.subdub_render_style_audit_payload()
    assert "dub_video" in pipeline["expected_steps"]
    assert "Ghép giọng vào video" in pipeline["expected_steps"]["dub_video"]
    assert style["render_font_size"] >= style["font_size"]
    assert style["text_box_enabled"] is True
    assert style["full_black_strip_default_disabled"] is True
    assert style["dub_audio_gain"]["gain"] == 2.0
