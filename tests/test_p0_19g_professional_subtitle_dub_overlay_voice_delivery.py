import asyncio
import inspect
from types import SimpleNamespace

import bot


SRT_TEXT = "1\n00:00:00,000 --> 00:00:02,000\nXin chào\n\n2\n00:00:02,000 --> 00:00:04,000\nThế giới\n"


class CaptureMessage:
    def __init__(self):
        self.calls = []

    async def reply_video(self, **kwargs):
        self.calls.append(("video", kwargs))
        return SimpleNamespace(message_id=len(self.calls), video=SimpleNamespace(file_id=f"video-{len(self.calls)}"))

    async def reply_document(self, **kwargs):
        self.calls.append(("document", kwargs))
        return SimpleNamespace(message_id=len(self.calls), document=SimpleNamespace(file_id=f"document-{len(self.calls)}"))

    async def reply_audio(self, **kwargs):
        self.calls.append(("audio", kwargs))
        return SimpleNamespace(message_id=len(self.calls), audio=SimpleNamespace(file_id=f"audio-{len(self.calls)}"))


def _captions(message):
    return [str(kwargs.get("caption") or "") for _kind, kwargs in message.calls]


def test_subtitle_style_presets_include_cover_original():
    presets = bot.subdub_style_presets()

    assert "cover_original" in presets
    assert presets["cover_original"]["cover_original"] is True
    assert presets["cover_original"]["background"] == "box"
    assert presets["tiktok_clear"]["show_subtitles"] is True


def test_subtitle_style_normalization_accepts_product_state():
    style = bot.subdub_normalize_style({
        "subtitle_style_preset": "cover_original",
        "subtitle_size": 42,
        "cover_original_subtitle": "yes",
        "subtitle_color": "#FFE45C",
    })

    assert style["preset"] == "cover_original"
    assert style["size"] == 42
    assert style["cover_original"] is True
    assert style["text_color"] == "#FFE45C"


def test_ass_generation_builds_professional_subtitle_script():
    ass_text = bot.subdub_generate_ass_from_srt(SRT_TEXT, {"subtitle_style_preset": "cover_original"})

    assert "[V4+ Styles]" in ass_text
    assert "Style: Default" in ass_text
    assert "Dialogue: 0,0:00:00.00,0:00:02.00" in ass_text
    assert "Xin chào" in ass_text
    assert "Thế giới" in ass_text


def test_cover_old_subtitle_filter_draws_bottom_strip():
    filter_text = bot.subdub_cover_filter({"subtitle_style_preset": "cover_original"})

    assert "drawbox=" in filter_text
    assert "y=ih*0.90" in filter_text or "y=ih*0.91" in filter_text
    assert "h=ih*0.05" in filter_text or "h=ih*0.06" in filter_text
    assert "color=black@" in filter_text


def test_no_subtitle_option_skips_ass_generation():
    ass_text = bot.subdub_generate_ass_from_srt(SRT_TEXT, {"subtitle_style_preset": "cover_original", "display_subtitles": "off"})

    assert ass_text == ""


def test_direct_dub_defaults_to_new_voice_audio_only():
    assert bot.subdub_original_audio_volume("", keep_original_audio=False) == 0.0
    assert bot.subdub_original_audio_volume("mute", keep_original_audio=False) == 0.0
    assert bot.subdub_original_audio_volume("duck", keep_original_audio=False) == 0.25
    assert bot.subdub_original_audio_volume("keep", keep_original_audio=False) == 1.0


def test_blackbox_render_wrapper_passes_style_and_audio_mode():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)

    assert 'kwargs.setdefault("subtitle_style"' in source
    assert 'kwargs.setdefault("original_audio_mode"' in source
    assert 'kwargs.setdefault("require_audio"' in source
    assert '"mute" if mode in {VIDEO_SUBTITLE_MODE_DUB, VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}' in source


def test_video_render_uses_ass_overlay_and_output_validation():
    source = inspect.getsource(bot.video_dubbing_render_video)

    assert "subdub_generate_ass_from_srt" in source
    assert "subdub_cover_filter" in source
    assert "subtitle.ass" in source
    assert "subdub_validate_video_output" in source


def test_delivery_rejects_invalid_video_and_returns_partial_audio(monkeypatch):
    async def fake_validate(*_args, **_kwargs):
        return {"ok": False, "detail": "video_too_small"}

    monkeypatch.setattr(bot, "subdub_validate_video_output", fake_validate)
    message = CaptureMessage()

    sent = asyncio.run(bot.send_public_subtitle_dub_final_outputs(
        message,
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        audio_bytes=b"voice-audio",
        video_bytes=b"fake-video",
        subtitle_items=[],
        include_subtitle_outputs=False,
        strict_validation=True,
    ))

    assert sent["video"] == 0
    assert sent["audio"] == 1
    assert [kind for kind, _kwargs in message.calls] == ["audio"]


def test_delivery_sends_large_video_as_document_when_needed(monkeypatch):
    async def fake_validate(*_args, **_kwargs):
        return {"ok": True, "duration": 12.0, "has_video": True, "has_audio": True, "detail": "ok"}

    async def fake_compress(*_args, **_kwargs):
        return b"", "not_smaller"

    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_SEND_VIDEO_MAX_MB", 1)
    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_DOCUMENT_MAX_MB", 3)
    monkeypatch.setattr(bot, "SUBDUB_COMPRESS_IF_OVER_MB", 1)
    monkeypatch.setattr(bot, "SUBDUB_ENABLE_DOCUMENT_FALLBACK", True)
    monkeypatch.setattr(bot, "subdub_validate_video_output", fake_validate)
    monkeypatch.setattr(bot, "subdub_compress_video_bytes", fake_compress)
    message = CaptureMessage()

    sent = asyncio.run(bot.send_public_subtitle_dub_final_outputs(
        message,
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        audio_bytes=b"voice-audio",
        video_bytes=b"x" * (2 * 1024 * 1024),
        include_subtitle_outputs=False,
        strict_validation=True,
    ))

    assert sent["video"] == 0
    assert sent["video_document"] == 1
    assert sent["delivery_method"] == "document"
    assert [kind for kind, _kwargs in message.calls] == ["document"]


def test_delivery_uses_compressed_video_before_document(monkeypatch):
    async def fake_validate(*_args, **_kwargs):
        return {"ok": True, "duration": 12.0, "has_video": True, "has_audio": True, "detail": "ok"}

    async def fake_compress(*_args, **_kwargs):
        return b"small-real-video", "compressed"

    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_SEND_VIDEO_MAX_MB", 1)
    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_DOCUMENT_MAX_MB", 1)
    monkeypatch.setattr(bot, "SUBDUB_COMPRESS_IF_OVER_MB", 1)
    monkeypatch.setattr(bot, "subdub_validate_video_output", fake_validate)
    monkeypatch.setattr(bot, "subdub_compress_video_bytes", fake_compress)
    message = CaptureMessage()

    sent = asyncio.run(bot.send_public_subtitle_dub_final_outputs(
        message,
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        audio_bytes=b"voice-audio",
        video_bytes=b"x" * (2 * 1024 * 1024),
        include_subtitle_outputs=False,
        strict_validation=True,
    ))

    assert sent["video"] == 1
    assert sent["delivery_method"] == "compressed_video"
    assert [kind for kind, _kwargs in message.calls] == ["video"]


def test_terminal_state_does_not_flip_delivered_to_failure():
    assert bot.subdub_terminal_state_allows_transition("delivered", "failed") is False
    assert bot.subdub_terminal_state_allows_transition("failed", "delivered") is False
    assert bot.subdub_terminal_state_allows_transition("processing", "delivered") is True


def test_public_delivery_captions_hide_internal_words(monkeypatch):
    async def fake_validate(*_args, **_kwargs):
        return {"ok": False, "detail": "adapter_missing"}

    monkeypatch.setattr(bot, "subdub_validate_video_output", fake_validate)
    message = CaptureMessage()

    asyncio.run(bot.send_public_subtitle_dub_final_outputs(
        message,
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        audio_bytes=b"voice-audio",
        video_bytes=b"fake-video",
        subtitle_items=[{"output_type": "srt", "bytes": SRT_TEXT.encode("utf-8"), "filename": "result.srt"}],
        strict_validation=True,
    ))

    banned = ("adapter", "provider", "ffmpeg", "mux", "asr", "tts", "traceback", "runtimeerror", "payload")
    public_text = "\n".join(_captions(message)).lower()
    assert not any(word in public_text for word in banned)


def test_debug_payload_records_voice_style_and_delivery(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    audio = tmp_path / "dub.mp3"
    audio.write_bytes(b"audio")
    final = tmp_path / "final.mp4"
    final.write_bytes(b"video")

    payload = bot.subtitle_dub_debug_job_payload(
        user_id=1,
        chat_id=2,
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        state={
            "voice_style": "Nữ mặc định",
            "selected_tts_voice_id": "female_voice",
            "subtitle_style_preset": "cover_original",
            "_subdub_delivery_method": "compressed_video",
            "_subdub_output_validation": {"ok": True, "duration": 5},
        },
        status="completed",
        stage="completed",
        input_save={"path": str(source), "size": source.stat().st_size},
        workspace_artifacts={"source": str(source), "dub_audio": str(audio), "final_mp4": str(final)},
        pipeline_attempted=True,
    )

    assert payload["selected_tts_voice_id"] == "female_voice"
    assert payload["selected_voice_label"] == "Nữ mặc định"
    assert payload["subtitle_style_preset"] == "cover_original"
    assert payload["cover_original_subtitle"] is True
    assert payload["delivery_method"] == "compressed_video"
    assert payload["output_validation"]["ok"] is True


def test_p0_19g_admin_debug_aliases_are_registered():
    source = inspect.getsource(bot)

    for command in (
        "subdub_job_debug",
        "subdub_render_debug",
        "subdub_delivery_debug",
        "subdub_voice_debug",
        "subdub_style_preview",
        "subdub_status",
    ):
        assert f'CommandHandler("{command}"' in source
