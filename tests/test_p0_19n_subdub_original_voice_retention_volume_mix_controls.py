import asyncio
import inspect

import bot


def test_audio_mix_controls_hidden_by_default():
    assert bot.SUBDUB_VOLUME_MIX_UI_ENABLED is False
    assert bot.subdub_audio_mix_available({"mode": bot.VIDEO_SUBTITLE_MODE_DUB}) is False
    assert bot.subdub_audio_mix_available({"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}) is False
    assert bot.subdub_audio_mix_available({"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE}) is False


def test_audio_mix_default_preserves_existing_dub_only_behavior():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}
    mix = bot.subdub_audio_mix_state_fields(state)

    assert mix["keep_original_audio"] is False
    assert mix["original_audio_volume_percent"] == 0
    assert mix["dubbed_voice_volume_percent"] == 100
    assert mix["audio_mix_mode"] == "dub_only"
    assert mix["volume_config_source"] == "volume_mix_ui_disabled"


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

    assert mix["keep_original_audio"] is False
    assert mix["original_audio_volume_percent"] == 0
    assert mix["dubbed_voice_volume_percent"] == 100
    assert mix["audio_mix_mode"] == "dub_only"
    assert lines == ""


def test_audio_mix_keyboard_hides_fixed_percentage_grid_by_default():
    keyboard = bot.subdub_audio_mix_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB})
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    public = " ".join(labels).lower()

    assert labels == ["⬅️ Quay lại"]
    assert "Gốc 20%" not in labels
    assert "Lồng 80%" not in labels
    assert all(len(label) <= 32 for label in labels)
    assert not any(term in public for term in ("provider", "api", "handler", "callback", "debug", "asr", "tts", "mux", "ffmpeg"))


def test_confirm_keyboard_hides_audio_mix_by_default():
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

    assert "videodub|audio_mix" not in dub_callbacks
    assert "videodub|audio_mix" not in subtitle_callbacks


def test_render_video_accepts_volume_mix_parameters():
    signature = inspect.signature(bot.video_dubbing_render_video)

    assert "keep_original_audio" in signature.parameters
    assert "original_audio_volume_percent" in signature.parameters
    assert "dubbed_voice_volume_percent" in signature.parameters


def test_render_video_ignores_volume_mix_when_ui_disabled(monkeypatch):
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
    assert "[0:a]volume=0.300[original]" not in rendered
    assert "[1:a]volume=1.500[dub]" not in rendered
    assert "[original][dub]amix" not in rendered
    assert "-map 0:v:0 -map 1:a:0" in rendered


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

    assert fields["keep_original_audio"] is False
    assert fields["original_audio_volume_percent"] == 0
    assert fields["dubbed_voice_volume_percent"] == 100
    assert fields["audio_mix_mode"] == "dub_only"
    assert fields["volume_mix_applied"] is False


def test_dynamic_volume_ui_future_spec_exists_but_disabled():
    spec = bot.subdub_dynamic_volume_ui_future_spec()

    assert spec["task"] == "P0.19N.2 SubDub Dynamic Original/Dub Volume Input UI"
    assert spec["enabled"] is False
    assert spec["public_fixed_percentage_grid"] is False
