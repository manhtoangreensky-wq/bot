import asyncio
import inspect
from types import SimpleNamespace

import bot


class _Message:
    def __init__(self, text=""):
        self.text = text
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"text": text, **kwargs})

    async def reply_video(self, **kwargs):
        self.outputs.append(dict(kwargs))


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


def test_audio_mix_keyboard_uses_split_numeric_layers_without_fixed_grid():
    keyboard = bot.subdub_audio_mix_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB})
    rows = keyboard.inline_keyboard
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    public = " ".join(labels).lower()

    assert labels == ["🔊 Âm thanh gốc", "🎙 Giọng lồng tiếng", "⬅️ Quay lại"]
    assert [button.text for button in rows[0]] == ["🔊 Âm thanh gốc", "🎙 Giọng lồng tiếng"]
    assert len(rows[0]) == 2
    assert "Gốc 20%" not in labels
    assert "Lồng 80%" not in labels
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
    assert "[0:a]volume=0.300[original]" in rendered
    assert "[1:a]volume=1.500[dub]" in rendered
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
    assert spec["public_fixed_percentage_grid"] is False
    assert spec["original_audio"]["numeric_input_max"] == 100
    assert spec["dub_voice"]["numeric_input_max"] == 200


def test_legacy_combo_pending_state_is_persisted_as_canonical():
    uid = 9191901
    bot.clear_video_dubbing_pending(uid)
    try:
        stale = bot.set_video_dubbing_pending(
            uid,
            "language",
            mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            combo_subpath=bot.VIDEO_DUBBING_NO_SUBTITLE_DIRECT_DUB,
            translate_requested="0",
            output_type="video",
        )

        normalized = bot.normalize_video_dubbing_combo_pending_state(uid, stale)
        persisted = bot.get_video_dubbing_pending(uid)

        assert normalized["combo_subpath"] == bot.VIDEO_DUBBING_NO_SUBTITLE_CREATE_THEN_DUB
        assert persisted["translate_requested"] == "1"
        assert persisted["dub_text_source"] == "translated"
        assert persisted["dub_source"] == "translated_subtitle"
        assert persisted["output_type"] == "video_subtitle"
    finally:
        bot.clear_video_dubbing_pending(uid)


def test_dub_only_next_screen_skips_translation_language(monkeypatch):
    uid = 9191902
    bot.clear_video_dubbing_pending(uid)
    monkeypatch.setattr(bot, "video_dubbing_public_flow_locked", lambda *_args, **_kwargs: False)
    try:
        state = bot.set_video_dubbing_pending(
            uid,
            "source",
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            source_file_id="fixture-video",
            source_language="vi",
            translate_requested="1",
        )

        next_state, _text, markup = bot.video_dubbing_next_screen_after_source(uid, state, "vi")
        callbacks = [
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.callback_data
        ]

        assert next_state["step"] == "voice"
        assert next_state["translate_requested"] == "0"
        assert next_state["dub_text_source"] == "source"
        assert not any("language" in value for value in callbacks)
    finally:
        bot.clear_video_dubbing_pending(uid)


def test_original_volume_numeric_input_persists_and_rejects_out_of_range(monkeypatch):
    uid = 9191903
    bot.clear_video_dubbing_pending(uid)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    try:
        bot.set_video_dubbing_pending(
            uid,
            "subdub_original_volume_input",
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        )
        accepted = _Message("30")
        update = SimpleNamespace(message=accepted, effective_user=SimpleNamespace(id=uid))
        assert asyncio.run(bot.handle_video_dubbing_pending_text(update, SimpleNamespace())) is True
        state = bot.get_video_dubbing_pending(uid)
        assert state["keep_original_audio"] == "1"
        assert state["original_audio_volume_percent"] == "30"
        assert state["audio_mix_mode"] == "keep_original"

        bot.set_video_dubbing_pending(uid, "subdub_original_volume_input")
        rejected = _Message("101")
        update = SimpleNamespace(message=rejected, effective_user=SimpleNamespace(id=uid))
        assert asyncio.run(bot.handle_video_dubbing_pending_text(update, SimpleNamespace())) is True
        state = bot.get_video_dubbing_pending(uid)
        assert state["step"] == "subdub_original_volume_input"
        assert "0 đến 100" in rejected.outputs[-1]["text"]

        bot.set_video_dubbing_pending(uid, "subdub_dub_volume_input")
        muted_dub = _Message("0")
        update = SimpleNamespace(message=muted_dub, effective_user=SimpleNamespace(id=uid))
        assert asyncio.run(bot.handle_video_dubbing_pending_text(update, SimpleNamespace())) is True
        state = bot.get_video_dubbing_pending(uid)
        assert state["dubbed_voice_volume_percent"] == "0"
        assert bot.subdub_audio_mix_state_fields(state)["dubbed_voice_volume_percent"] == 0
    finally:
        bot.clear_video_dubbing_pending(uid)


def test_retry_mux_preserves_original_and_dub_volume(monkeypatch, tmp_path):
    uid = 9191904
    bot.clear_video_dubbing_pending(uid)
    audio_path = tmp_path / "dub.mp3"
    audio_path.write_bytes(b"audio")
    rendered = []

    async def fake_download(_context, _state):
        return b"video", "video/mp4"

    async def fake_render(_source, **kwargs):
        rendered.append(dict(kwargs))
        return b"mp4", "rendered"

    monkeypatch.setattr(bot, "get_media_asset_record", lambda *_args: {"local_path": str(audio_path)})
    monkeypatch.setattr(bot, "video_dubbing_has_media", lambda _state: True)
    monkeypatch.setattr(bot, "video_dubbing_download_source", fake_download)
    monkeypatch.setattr(bot, "subtitle_plus_dub_subtitle_text", lambda *_args, **_kwargs: "1\n00:00:00,000 --> 00:00:01,000\nHello")
    monkeypatch.setattr(bot, "video_dubbing_render_video", fake_render)
    monkeypatch.setattr(bot, "pipeline_final_video_sendable", lambda _data: True)
    monkeypatch.setattr(bot, "write_media_asset_bytes", lambda *_args, **_kwargs: "out.mp4")
    monkeypatch.setattr(bot, "create_dub_asset_record", lambda **_kwargs: {"asset_id": "retry-video"})
    monkeypatch.setattr(bot, "media_asset_make_id", lambda *_args, **_kwargs: "retry-video")
    monkeypatch.setattr(bot, "media_asset_video_session_id", lambda *_args, **_kwargs: "session")

    state = bot.set_video_dubbing_pending(
        uid,
        "completed",
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        source_file_id="fixture-video",
        final_dub_asset_id="fixture-audio",
        translated_subtitle_ref="translated",
        keep_original_audio="1",
        original_audio_volume_percent=30,
        dubbed_voice_volume_percent=150,
    )
    message = _Message()
    query = SimpleNamespace(message=message)
    try:
        assert asyncio.run(
            bot.subtitle_plus_dub_retry_mux_final_video(
                query,
                SimpleNamespace(),
                uid,
                state,
                "vi",
            )
        ) is True
        assert rendered[0]["keep_original_audio"] is True
        assert rendered[0]["original_audio_volume_percent"] == 30
        assert rendered[0]["dubbed_voice_volume_percent"] == 150
        assert rendered[0]["original_audio_mode"] == "keep_original"
    finally:
        bot.clear_video_dubbing_pending(uid)
