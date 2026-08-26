import asyncio
import inspect

import bot


def test_audio_mix_controls_enabled_for_dub_modes():
    assert bot.SUBDUB_VOLUME_MIX_UI_ENABLED is True
    assert bot.subdub_audio_mix_available({"mode": bot.VIDEO_SUBTITLE_MODE_DUB}) is True
    assert bot.subdub_audio_mix_available({"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}) is True
    assert bot.subdub_audio_mix_available({"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE}) is False


def test_audio_mix_default_preserves_existing_dub_only_behavior():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}
    mix = bot.subdub_audio_mix_state_fields(state)

    assert mix["keep_original_audio"] is False
    assert mix["original_audio_volume_percent"] == 0
    assert mix["dubbed_voice_volume_percent"] == 100
    assert mix["audio_mix_mode"] == "dub_only"
    assert mix["volume_config_source"] == "default_subdub_audio_mix"


def test_audio_mix_keep_original_persists_percentages():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "keep_original_audio": "1",
        "original_audio_volume_percent": "30",
        "dubbed_voice_volume_percent": "150",
        "volume_config_source": "user_audio_mix_controls",
    }
    mix = bot.subdub_audio_mix_state_fields(state)
    lines = bot.subdub_audio_mix_confirm_lines(state, "vi")

    assert mix["keep_original_audio"] is True
    assert mix["original_audio_volume_percent"] == 30
    assert mix["dubbed_voice_volume_percent"] == 150
    assert mix["audio_mix_mode"] == "keep_original"
    assert "Âm thanh gốc" in lines
    assert "30%" in lines
    assert "150%" in lines


def test_audio_mix_keyboard_restores_presets_and_keeps_numeric_layers():
    keyboard = bot.subdub_audio_mix_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB})
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    public = " ".join(labels).lower()

    assert [button.text for button in keyboard.inline_keyboard[0]] == [
        "🔊 Âm thanh gốc",
        "🎙 Giọng lồng tiếng",
    ]
    for value in (20, 40, 60, 80, 100):
        assert f"videodub|audio_original_volume|{value}" in callbacks
    for value in (80, 100, 120, 150, 200):
        assert f"videodub|audio_dub_volume|{value}" in callbacks
    assert all(len(label) <= 32 for label in labels)
    assert not any(term in public for term in ("provider", "api", "handler", "callback", "debug", "asr", "tts", "mux", "ffmpeg"))


def test_confirm_keyboard_shows_audio_mix_for_dub_modes_only():
    dub_callbacks = [
        button.callback_data
        for row in bot.video_dubbing_confirm_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}).inline_keyboard
        for button in row
    ]
    subtitle_callbacks = [
        button.callback_data
        for row in bot.video_dubbing_confirm_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE}).inline_keyboard
        for button in row
    ]

    assert "videodub|audio_mix" in dub_callbacks
    assert "videodub|audio_mix" not in subtitle_callbacks


def test_confirm_keyboard_names_audio_mix_truthfully_in_both_dub_lanes():
    for mode, active_flow in (
        (bot.VIDEO_SUBTITLE_MODE_DUB, "dub_audio"),
        (bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "subtitle_plus_dub"),
    ):
        keyboard = bot.video_dubbing_confirm_keyboard(
            "vi",
            {
                "mode": mode,
                "process_type": mode,
                "video_processing_mode": mode,
                "active_flow": active_flow,
            },
        )
        audio_buttons = [
            button
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data == "videodub|audio_mix"
        ]

        assert len(audio_buttons) == 1
        assert audio_buttons[0].text == "🎚 Âm thanh"


def test_render_video_accepts_volume_mix_parameters():
    signature = inspect.signature(bot.video_dubbing_render_video)

    assert "keep_original_audio" in signature.parameters
    assert "original_audio_volume_percent" in signature.parameters
    assert "dubbed_voice_volume_percent" in signature.parameters


def test_render_video_applies_volume_mix_when_enabled(monkeypatch):
    commands = []
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")

    async def fake_validate(*_args, **_kwargs):
        return {"ok": True, "detail": "ok"}

    async def fake_probe(*_args, **_kwargs):
        return {"ok": True, "has_audio": True, "has_video": True, "duration": 1, "width": 1280, "height": 720}

    monkeypatch.setattr(bot, "subdub_validate_video_output", fake_validate)
    monkeypatch.setattr(bot, "subdub_probe_video_bytes", fake_probe)

    async def fake_run(command, timeout=0):
        commands.append(list(command))
        output_path = str(command[-1])
        with open(output_path, "wb") as handle:
            handle.write(b"mp4")
        return True, "ok"

    monkeypatch.setattr(bot, "run_ffmpeg_command", fake_run)

    output, detail = asyncio.run(
        bot.video_dubbing_render_video(
            b"video-bytes",
            dubbed_audio=b"audio-bytes",
            keep_original_audio=True,
            original_audio_volume_percent=30,
            dubbed_voice_volume_percent=150,
            subtitle_style={"show_subtitles": False},
            require_audio=True,
        )
    )
    rendered = " ".join(commands[0])

    assert output == b"mp4"
    assert "ffmpeg_video_render_basic" in detail
    assert "[0:a]volume=0.300" in rendered
    assert "[1:a]volume=1.500" in rendered
    assert "[original]" in rendered
    assert "[dub]" in rendered
    assert "[original][dub]amix" in rendered
    assert "-map 0:v:0 -map 1:a:0" not in rendered


def test_subdub_voice_style_debug_includes_volume_mix_fields():
    fields = bot.subdub_voice_style_state_fields(
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        state={
            "keep_original_audio": "1",
            "original_audio_volume_percent": "40",
            "dubbed_voice_volume_percent": "120",
        },
        voice_resolution={"ok": True, "provider_voice_id": "female-real-voice", "selected_voice_gender": "female"},
        selected_tts_voice_id="female-real-voice",
    )

    assert fields["keep_original_audio"] is True
    assert fields["original_audio_volume_percent"] == 40
    assert fields["dubbed_voice_volume_percent"] == 120
    assert fields["audio_mix_mode"] == "keep_original"
    assert fields["volume_mix_applied"] is True


def test_dynamic_volume_ui_spec_is_enabled_and_numeric():
    spec = bot.subdub_dynamic_volume_ui_future_spec()

    assert spec["task"] == "P0.19N SubDub Original/Dub Volume Input UI"
    assert spec["enabled"] is True
    assert spec["public_fixed_percentage_grid"] is True
    assert spec["original_audio"]["numeric_input_max"] == 100
    assert spec["dub_voice"]["numeric_input_max"] == 200
