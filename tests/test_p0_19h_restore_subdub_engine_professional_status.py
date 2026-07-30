import asyncio
import os
from types import SimpleNamespace

import bot


SRT_TEXT = "1\n00:00:00,000 --> 00:00:02,000\nXin chao\n"
MP4_BYTES = (b"\x00\x00\x00\x18ftypmp42" + b"x" * 4096)


class CaptureMessage:
    def __init__(self):
        self.calls = []
        self.chat_id = 12345

    async def reply_video(self, **kwargs):
        self.calls.append(("video", kwargs))
        return SimpleNamespace(message_id=19001, video=SimpleNamespace(file_id="video-file"))

    async def reply_document(self, **kwargs):
        self.calls.append(("document", kwargs))
        return SimpleNamespace(message_id=19002, document=SimpleNamespace(file_id="doc-file"))

    async def reply_audio(self, **kwargs):
        self.calls.append(("audio", kwargs))
        return SimpleNamespace(message_id=19003, audio=SimpleNamespace(file_id="audio-file"))

    async def reply_text(self, text, **kwargs):
        self.calls.append(("text", {"text": text, **kwargs}))


class CaptureQuery:
    def __init__(self):
        self.message = CaptureMessage()
        self.from_user = SimpleNamespace(id=12345)
        self.edits = []

    async def edit_message_text(self, text, **kwargs):
        self.edits.append({"text": text, **kwargs})

    async def answer(self, *args, **kwargs):
        self.edits.append({"answer": args, **kwargs})


def _patch_render_success(monkeypatch, calls):
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")

    async def fake_validate(video_bytes, **kwargs):
        return {"ok": True, "detail": "ok", "duration": 2.0, "has_video": True, "has_audio": bool(kwargs.get("require_audio")), "size": len(video_bytes)}

    async def fake_run(command, timeout=300):
        calls.append(list(command))
        output_path = command[-1]
        with open(output_path, "wb") as handle:
            handle.write(MP4_BYTES)
        return True, "ok"

    monkeypatch.setattr(bot, "subdub_validate_video_output", fake_validate)
    monkeypatch.setattr(bot, "run_ffmpeg_command", fake_run)


def test_p0_19h_restores_p019f_engine_path(monkeypatch):
    calls = []
    _patch_render_success(monkeypatch, calls)
    monkeypatch.setattr(bot, "SUBDUB_ADVANCED_STYLE_ENABLED", False)

    output, detail = asyncio.run(bot.video_dubbing_render_video(
        b"source-video",
        subtitle_bytes=SRT_TEXT.encode("utf-8"),
        subtitle_style={"subtitle_style_preset": "cover_original", "advanced_style_enabled": True},
    ))

    command_text = " ".join(str(part) for part in calls[0])
    assert output == MP4_BYTES
    assert "ffmpeg_video_render_advanced_style" in detail
    assert "subtitle.ass" in command_text
    ass_text = bot.subdub_generate_ass_from_srt(
        SRT_TEXT,
        {"subtitle_style_preset": "cover_original", "advanced_style_enabled": True},
    )
    assert "drawbox" in command_text or ",3," in ass_text


def test_subdub_advanced_style_disabled_still_outputs_mp4(monkeypatch):
    calls = []
    _patch_render_success(monkeypatch, calls)
    monkeypatch.setattr(bot, "SUBDUB_ADVANCED_STYLE_ENABLED", False)

    output, detail = asyncio.run(bot.video_dubbing_render_video(
        b"source-video",
        dubbed_audio=b"new-voice-audio",
        subtitle_bytes=SRT_TEXT.encode("utf-8"),
        subtitle_style={"subtitle_style_preset": "cover_original"},
        require_audio=True,
    ))

    assert output == MP4_BYTES
    assert "advanced_style" in detail
    assert len(calls) == 1


def test_subdub_style_failure_falls_back_to_basic_render(monkeypatch):
    calls = []
    monkeypatch.setattr(bot, "SUBDUB_ADVANCED_STYLE_ENABLED", True)
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")

    async def fake_validate(video_bytes, **_kwargs):
        return {"ok": True, "detail": "ok", "duration": 2.0, "has_video": True, "has_audio": True, "size": len(video_bytes)}

    async def fake_run(command, timeout=300):
        calls.append(list(command))
        command_text = " ".join(str(part) for part in command)
        if "subtitle.ass" in command_text or "drawbox" in command_text:
            return False, "style failed"
        with open(command[-1], "wb") as handle:
            handle.write(MP4_BYTES)
        return True, "ok"

    monkeypatch.setattr(bot, "subdub_validate_video_output", fake_validate)
    monkeypatch.setattr(bot, "run_ffmpeg_command", fake_run)

    output, detail = asyncio.run(bot.video_dubbing_render_video(
        b"source-video",
        dubbed_audio=b"new-voice-audio",
        subtitle_bytes=SRT_TEXT.encode("utf-8"),
        subtitle_style={"subtitle_style_preset": "cover_original", "advanced_style_enabled": True},
        require_audio=True,
    ))

    assert output == MP4_BYTES
    assert len(calls) == 2
    assert "advanced_style_fallback" in detail
    assert "subtitle.srt" in " ".join(str(part) for part in calls[-1])


def test_direct_dub_generates_new_audio_even_when_style_disabled(monkeypatch):
    calls = []
    _patch_render_success(monkeypatch, calls)
    monkeypatch.setattr(bot, "SUBDUB_ADVANCED_STYLE_ENABLED", False)

    output, _detail = asyncio.run(bot.video_dubbing_render_video(
        b"source-video",
        dubbed_audio=b"new-voice-audio",
        subtitle_bytes=b"",
        original_audio_mode="mute",
        require_audio=True,
    ))

    command_text = " ".join(str(part) for part in calls[0])
    assert output == MP4_BYTES
    assert "1:a:0" in command_text
    assert "amix" not in command_text


def test_subtitle_dub_muxes_audio_video_after_p019g(monkeypatch):
    calls = []
    _patch_render_success(monkeypatch, calls)

    output, _detail = asyncio.run(bot.video_dubbing_render_video(
        b"source-video",
        dubbed_audio=b"new-voice-audio",
        subtitle_bytes=SRT_TEXT.encode("utf-8"),
        original_audio_mode="mute",
        require_audio=True,
    ))

    command_text = " ".join(str(part) for part in calls[0])
    assert output == MP4_BYTES
    assert "-map 0:v:0 -map 1:a:0" in command_text
    assert "-shortest" in command_text


def test_subdub_progress_status_stages():
    text = bot.subdub_progress_text("generating_voice", "abc123", "vi")

    assert "TOAN AAS đang xử lý video" in text
    assert "Tiến độ: 65%" in text
    assert "Tạo giọng lồng tiếng" in text
    assert "#ABC123" in text


def test_subdub_status_update_button():
    keyboard = bot.subdub_progress_keyboard("job123", "vi")
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]

    assert "videodub|subdub_status|job123" in callbacks
    assert "videodub|source_upload" in callbacks
    assert "videodub|status_back_type" in callbacks


def test_subdub_no_duplicate_terminal_messages():
    assert bot.subdub_terminal_state_allows_transition("delivered", "failed_no_charge") is False
    assert bot.subdub_terminal_state_allows_transition("delivered", "failed_refunded") is False
    assert bot.subdub_terminal_state_allows_transition("processing", "delivered") is True


def test_subdub_no_fail_then_success_conflict():
    assert bot.subdub_terminal_state_allows_transition("failed_no_charge", "delivered") is False
    assert bot.subdub_terminal_state_allows_transition("failed_refunded", "completed") is False


def test_subdub_no_success_without_delivery():
    job_key = "p019h-no-success"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(job_key, None)
    bot.update_subtitle_dub_pipeline_job(job_key, status="failed", terminal_state="failed_no_charge")
    bot.update_subtitle_dub_pipeline_job(job_key, status="completed", terminal_state="delivered")

    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[job_key]["terminal_state"] == "failed_no_charge"
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[job_key]["status"] == "failed_no_charge"


def test_subdub_no_zero_duration_delivery():
    result = asyncio.run(bot.subdub_validate_video_output(MP4_BYTES, require_audio=False, min_bytes=512))

    assert result["ok"] is False or float(result.get("duration") or 0) != 0


def test_subdub_public_no_technical_words():
    text = bot.subdub_progress_text("muxing_video", "job123", "vi") + "\n" + bot.subdub_clean_failure_text("vi")
    banned = ("asr", "tts", "ffmpeg", "provider", "adapter", "debug", "payload", "local_worker", "component")

    assert not any(word in text.lower() for word in banned)


def test_subdub_admin_debug_has_blocker(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    payload = bot.subtitle_dub_debug_job_payload(
        user_id=1,
        chat_id=2,
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        state={
            "_subdub_render_debug": {
                "advanced_style_enabled": False,
                "fallback_render_attempted": True,
                "fallback_render_pass": True,
                "render_detail": "ffprobe_unavailable_basic_mp4_ok",
            },
            "_subdub_terminal_state": "delivered",
        },
        status="completed",
        stage="delivered",
        input_save={"path": str(source), "size": os.path.getsize(source)},
        workspace_artifacts={"source": str(source)},
        detail="",
        pipeline_attempted=True,
    )

    assert "pipeline_blocker" in payload
    assert payload["fallback_render_attempted"] is True
    assert payload["fallback_render_pass"] is True
    assert payload["terminal_state"] == "delivered"


def test_subdub_no_charge_on_failure():
    text = bot.subdub_clean_failure_text("vi")

    assert "chưa trừ Xu" in text


def test_subdub_delivery_fallback_does_not_break_engine(monkeypatch):
    async def fake_validate(*_args, **_kwargs):
        return {"ok": True, "detail": "ok", "duration": 2.0, "has_video": True, "has_audio": True, "size": 1024}

    async def fake_compress(*_args, **_kwargs):
        return b"", "compress_failed"

    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_SEND_VIDEO_MAX_MB", 1)
    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_DOCUMENT_MAX_MB", 3)
    monkeypatch.setattr(bot, "SUBDUB_ENABLE_DOCUMENT_FALLBACK", True)
    monkeypatch.setattr(bot, "subdub_validate_video_output", fake_validate)
    monkeypatch.setattr(bot, "subdub_compress_video_bytes", fake_compress)
    message = CaptureMessage()

    sent = asyncio.run(bot.send_public_subtitle_dub_final_outputs(
        message,
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        audio_bytes=b"audio",
        video_bytes=b"x" * (2 * 1024 * 1024),
        include_subtitle_outputs=False,
        strict_validation=True,
    ))

    assert sent["video_document"] == 1
    assert [kind for kind, _kwargs in message.calls] == ["document"]
