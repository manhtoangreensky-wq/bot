import inspect

import pytest

import bot


LONG_VI_SRT = (
    "1\n"
    "00:00:00,000 --> 00:00:03,000\n"
    "Đây là một câu phụ đề tiếng Việt khá dài cần tự xuống dòng để không tràn khỏi màn hình\n"
)


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_subdub_female_voice_not_misread_as_male(monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "female-real-voice")
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "male-real-voice")

    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        **bot.video_dubbing_voice_payload("default_female", None, "vi"),
    }

    assert bot.resolve_video_dub_tts_voice_id(190901, state) == "female-real-voice"
    assert bot.subdub_voice_id_gender_hint("female-real-voice") == "female"
    source = inspect.getsource(bot.video_dubbing_tts_bytes)
    assert '"male" in str(voice_id' not in source
    assert "gender_hint" in source


def test_subdub_subtitle_bottom_center_moderate_wrapped():
    style = bot.subdub_normalize_style(
        {"subtitle_style_preset": "cover_original", "video_width": 1280, "video_height": 720}
    )
    ass = bot.subdub_generate_ass_from_srt(LONG_VI_SRT, style)

    assert style["position"] == "bottom"
    assert style["align"] == "center"
    assert 34 <= style["render_size"] <= 58
    assert style["subtitle_font_multiplier"] <= 1.6
    assert "WrapStyle: 0" in ass
    assert "\\N" in ass
    assert "PlayResX: 1280" in ass
    assert "PlayResY: 720" in ass


def test_audio_mix_uses_dynamic_input_not_fixed_grid():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}
    labels = _labels(bot.subdub_audio_mix_keyboard("vi", state))
    callbacks = _callbacks(bot.subdub_audio_mix_keyboard("vi", state))

    assert bot.SUBDUB_VOLUME_MIX_UI_ENABLED is True
    assert "✏️ Nhập % gốc" in labels
    assert "✏️ Nhập % lồng" in labels
    assert not any(label.startswith("Gốc ") or label.startswith("Lồng ") for label in labels)
    assert "videodub|audio_original_input" in callbacks
    assert "videodub|audio_dub_input" in callbacks


def test_audio_mix_custom_numeric_ranges():
    assert bot.subdub_parse_volume_percent_input("30%", low=0, high=100) == 30
    assert bot.subdub_parse_volume_percent_input("120", low=0, high=200) == 120
    with pytest.raises(ValueError):
        bot.subdub_parse_volume_percent_input("201", low=0, high=200)


def test_subdub_delivered_panel_full_green():
    text = bot.subdub_progress_text("delivered", "JOB123", "vi")

    assert "Tiến độ: 100%" in text
    assert "✅ Gửi kết quả" in text
    assert "⬜ Gửi kết quả" not in text


def test_subdub_success_receipt_has_report_not_fail():
    text = bot.video_dubbing_receipt_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "video_duration": 92, "_pipeline_job_id": "ABC123"},
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
            "terminal_state": "delivered",
            "video_delivery_message_id": "777",
            "charged": 12,
        },
        "vi",
    )

    assert "Đã gửi video hoàn chỉnh" in text
    assert "Thời lượng:" in text
    assert "Chi phí:" in text
    assert "chưa xử lý được" not in text


def test_success_after_public_failure_suppressed_when_video_delivered():
    source = inspect.getsource(bot.handle_video_dubbing_callback)

    assert "delivered_video_result" in source
    assert "subdub_job_has_failure_public_outcome(latest_pipeline_job) and not delivered_video_result" in source
    assert "late_public_error_suppressed" in source
