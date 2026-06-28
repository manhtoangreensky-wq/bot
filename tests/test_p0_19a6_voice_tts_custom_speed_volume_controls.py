import inspect
import subprocess
from pathlib import Path

import pytest

import bot
from services import audio_postprocess, voice_clone_pipeline


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_voice_tts_speed_accepts_decimal_0_1_to_2_0():
    assert float(bot.parse_voice_tts_speed_input("0.1")) == pytest.approx(0.1)
    assert float(bot.parse_voice_tts_speed_input("1.0")) == pytest.approx(1.0)
    assert float(bot.parse_voice_tts_speed_input("2.0")) == pytest.approx(2.0)


def test_voice_tts_speed_accepts_vietnamese_decimal_comma():
    assert bot.parse_voice_tts_speed_input("1,2") == "1.2"


def test_voice_tts_speed_rejects_out_of_range():
    with pytest.raises(ValueError):
        bot.parse_voice_tts_speed_input("0.09")
    with pytest.raises(ValueError):
        bot.parse_voice_tts_speed_input("2.1")


def test_voice_tts_speed_invalid_copy_clean():
    text = bot.voice_tts_speed_invalid_text("vi").lower()
    for term in ("admin", "provider", "provider_voice_id", "diagnostic", "route_errors", "api", "debug", "minimax", "key4u", "ffmpeg"):
        assert term not in text


def test_voice_tts_volume_accepts_percent_0_to_200():
    assert bot.parse_voice_tts_volume_input("0") == 0
    assert bot.parse_voice_tts_volume_input("100%") == 100
    assert bot.parse_voice_tts_volume_input("200") == 200


def test_voice_tts_volume_rejects_out_of_range():
    with pytest.raises(ValueError):
        bot.parse_voice_tts_volume_input("-1")
    with pytest.raises(ValueError):
        bot.parse_voice_tts_volume_input("201")


def test_voice_tts_volume_rejects_ambiguous_decimal_1_5():
    with pytest.raises(ValueError):
        bot.parse_voice_tts_volume_input("1.5")
    with pytest.raises(ValueError):
        bot.parse_voice_tts_volume_input("1,5")


def test_voice_tts_volume_zero_requires_confirm():
    text = bot.voice_tts_zero_volume_confirm_text("vi")
    labels = _labels(bot.voice_tts_zero_volume_confirm_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))

    assert "Âm lượng 0% sẽ tạo audio không có tiếng" in text
    assert "✅ Vẫn tạo audio" in labels
    assert "✏️ Nhập lại âm lượng" in labels


def test_voice_tts_volume_100_preserves_p0_19a5_boost():
    assert bot.voice_tts_effective_volume_factor(100) == pytest.approx(2.0)
    assert voice_clone_pipeline._voice_tts_effective_volume_factor(100) == pytest.approx(2.0)


def test_voice_tts_volume_200_doubles_current_boost_with_limiter(tmp_path):
    source = tmp_path / "voice.mp3"
    target = tmp_path / "voice_boosted.mp3"
    source.write_bytes(b"audio")
    seen = {}

    def fake_runner(command):
        seen["command"] = list(command)
        target.write_bytes(b"boosted-audio")
        return subprocess.CompletedProcess(command, 0)

    result = audio_postprocess.boost_voice_audio(
        str(source),
        str(target),
        volume_factor=bot.voice_tts_effective_volume_factor(200),
        ffmpeg_path="ffmpeg",
        run_command_func=fake_runner,
    )

    assert result.ok is True
    assert result.factor == pytest.approx(4.0)
    assert "volume=4.000,alimiter=limit=0.95" in seen["command"]


def test_voice_tts_no_double_boost(tmp_path):
    source = tmp_path / "voice_boosted.mp3"
    target = tmp_path / "voice_twice_boosted.mp3"
    source.write_bytes(b"already-boosted")

    result = audio_postprocess.boost_voice_audio(
        str(source),
        str(target),
        volume_factor=bot.voice_tts_effective_volume_factor(100),
        ffmpeg_path="ffmpeg",
        run_command_func=lambda _command: (_ for _ in ()).throw(AssertionError("must not run twice")),
    )

    assert result.ok is True
    assert result.skipped_double_boost is True
    assert target.read_bytes() == b"already-boosted"


def test_voice_numeric_settings_ui_has_no_technical_words():
    text = "\n".join([
        bot.voice_tts_settings_text("1.2", 150, "vi"),
        bot.voice_tts_speed_input_text("vi"),
        bot.voice_tts_volume_input_text("vi"),
        bot.voice_tts_zero_volume_confirm_text("vi"),
        "\n".join(_labels(bot.voice_tts_settings_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))),
    ]).lower()

    for term in ("admin", "provider", "provider_voice_id", "diagnostic", "route_errors", "api", "debug", "minimax", "key4u", "ffmpeg"):
        assert term not in text


def test_admin_voice_numeric_settings_ui_same_as_user():
    admin_text = bot.voice_tts_settings_text("1.0", 100, "vi")
    user_text = bot.voice_tts_settings_text("1.0", 100, "vi")
    admin_labels = _labels(bot.voice_tts_settings_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    user_labels = _labels(bot.voice_tts_settings_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))

    assert admin_text == user_text
    assert admin_labels == user_labels
    assert "admin" not in admin_text.lower()


def test_voice_numeric_settings_back_returns_previous_screen():
    callbacks = _callbacks(bot.voice_tts_settings_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))

    assert "music_quick|showroom|voice_tts_settings_back" in callbacks
    assert "menu|main" not in callbacks


def test_custom_voice_creation_not_modified():
    create_source = inspect.getsource(voice_clone_pipeline.process_custom_voice_create)
    quote_source = inspect.getsource(bot.voice_clone_quote_keyboard)

    assert "voice_tts_settings" not in create_source
    assert "volume_percent" not in create_source
    assert "voice_tts_settings" not in quote_source
