import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import bot


ALL_VIDEO_LANES = (
    bot.VIDEO_SUBTITLE_MODE_CREATE,
    bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
    bot.VIDEO_SUBTITLE_MODE_DUB,
    bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
)


class CaptureSentMessage:
    def __init__(self, message_id):
        self.message_id = message_id
        self.edits = []

    async def edit_text(self, text, **kwargs):
        self.edits.append({"text": str(text), **kwargs})
        return self


class CaptureMessage:
    def __init__(self, media=None):
        self.chat_id = 250025
        self.message_id = 25
        self.reply_to_message = None
        self.video = media
        self.audio = None
        self.voice = None
        self.document = None
        self.outputs = []
        self.sent_messages = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"text": str(text), **kwargs})
        sent = CaptureSentMessage(len(self.outputs))
        self.sent_messages.append(sent)
        return sent


def command_update(user_id=250025):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(id=user_id),
        message=CaptureMessage(),
    )


def media_update(user_id=250025):
    media = SimpleNamespace(
        file_id="live25-video-file",
        file_unique_id="live25-video-unique",
        file_name="live25.mp4",
        mime_type="video/mp4",
        duration=8,
        file_size=2048,
    )
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(id=user_id),
        message=CaptureMessage(media),
    )


def confirmed_context():
    return SimpleNamespace(
        args=["--confirm-paid"],
        bot=SimpleNamespace(),
        application=None,
        user_data={},
        chat_data={},
    )


def resolved_video_media():
    return {
        "bytes": b"fixture-video-bytes",
        "content_type": "video/mp4",
        "mime_type": "video/mp4",
        "file_type": "video",
        "file_id": "live25-video-file",
        "file_unique_id": "live25-video-unique",
        "file_name": "live25.mp4",
        "file_size": len(b"fixture-video-bytes"),
        "duration": 8,
        "source": "last_media",
    }


def block_legacy_smoke_provider_path(monkeypatch):
    monkeypatch.setattr(bot, "key4u_asr_configured", lambda: False)
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "")
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "")
    monkeypatch.setattr(bot, "SHOPAIKEY_AUDIO_TRANSCRIPTION_ENDPOINT", "")

    async def forbidden_asr(*_args, **_kwargs):
        raise AssertionError("legacy smoke ASR path must not run")

    monkeypatch.setattr(bot, "transcribe_media_to_segments", forbidden_asr)


def test_admin_media_pending_window_handles_slow_telegram_uploads():
    assert bot.ADMIN_TOOL_TEST_PENDING_TTL_SECONDS >= 10 * 60


def test_admin_smoke_media_uses_canonical_bounded_download(monkeypatch):
    uid = 250024
    captured = []
    bot.LAST_MEDIA_BY_USER[str(uid)] = {
        "file_id": "bounded-download-file",
        "file_unique_id": "bounded-download-unique",
        "file_type": "video",
        "mime_type": "video/mp4",
        "file_name": "bounded-download.mp4",
        "file_size": 4096,
        "duration": 8,
        "created_at_ts": bot.time.time(),
    }

    async def canonical_download(_context, state):
        captured.append(dict(state))
        return b"canonical-video-bytes", "video/mp4"

    class NoDirectDownloadBot:
        async def get_file(self, *_args, **_kwargs):
            raise AssertionError("resolve_stt_test_media must use the canonical downloader")

    monkeypatch.setattr(bot, "video_dubbing_download_source", canonical_download)
    try:
        result = asyncio.run(
            bot.resolve_stt_test_media(
                command_update(uid),
                SimpleNamespace(bot=NoDirectDownloadBot()),
            )
        )
    finally:
        bot.LAST_MEDIA_BY_USER.pop(str(uid), None)

    assert result["bytes"] == b"canonical-video-bytes"
    assert result["content_type"] == "video/mp4"
    assert len(captured) == 1
    assert captured[0]["source_file_id"] == "bounded-download-file"
    assert captured[0]["source_file_size"] == 4096


@pytest.mark.parametrize("mode", ALL_VIDEO_LANES)
def test_admin_video_smoke_pending_preserves_exact_lane(monkeypatch, mode):
    uid = 250025
    bot.clear_pending_admin_tool_test(uid)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(
        bot,
        "resolve_stt_test_media",
        lambda *_args, **_kwargs: asyncio.sleep(0, result=None),
    )

    asyncio.run(
        bot._run_admin_video_pipeline_smoke_core(
            command_update(uid),
            confirmed_context(),
            mode,
        )
    )

    pending = bot.get_pending_admin_tool_test(uid)
    assert pending["tool"] == "video_pipeline"
    assert pending["mode"] == mode
    bot.clear_pending_admin_tool_test(uid)


@pytest.mark.parametrize("mode", ALL_VIDEO_LANES)
def test_pending_media_dispatches_the_original_video_lane(monkeypatch, mode):
    uid = 250026
    bot.clear_pending_admin_tool_test(uid)
    bot.set_pending_admin_tool_test(
        uid,
        "video_pipeline",
        "/tool_test_video_pipeline",
        mode=mode,
    )
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    called = []

    async def fake_smoke(_update, context, requested_mode):
        called.append((requested_mode, tuple(context.args)))

    monkeypatch.setattr(bot, "run_admin_video_pipeline_smoke", fake_smoke)

    consumed = asyncio.run(
        bot.handle_pending_admin_tool_test_media(
            media_update(uid),
            SimpleNamespace(bot=SimpleNamespace(), user_data={}, chat_data={}),
        )
    )

    assert consumed is True
    assert called == [(mode, ("--confirm-paid",))]
    assert bot.get_pending_admin_tool_test(uid) == {}


def test_admin_smoke_readiness_honors_persisted_asr_force_open(monkeypatch):
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", False)
    monkeypatch.setattr(
        bot,
        "subdub_public_override_value",
        lambda name: "true" if name == "VIDEO_ASR_ENABLED" else "",
    )

    def video_dubbing_capability(_mode, _state, public=False):
        return {"ok": True, "missing": [], "reason": "ready", "public": public}

    monkeypatch.setattr(bot, "video_dubbing_capability", video_dubbing_capability)

    readiness = bot._product_engine_readiness(
        "subtitle_auto",
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        {"admin_real_test": True},
    )

    assert "asr_adapter_missing" not in readiness["technical_missing"]


def test_video_translate_smoke_alias_is_registered():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert "async def cmd_tool_test_video_translate" in source
    assert 'CommandHandler("tool_test_video_translate", cmd_tool_test_video_translate)' in source


@pytest.mark.parametrize("mode", ALL_VIDEO_LANES)
def test_admin_video_smoke_uses_canonical_product_mp4_executor(monkeypatch, mode):
    uid = 250027
    captured = []
    saved = []
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    block_legacy_smoke_provider_path(monkeypatch)
    monkeypatch.setattr(
        bot,
        "resolve_stt_test_media",
        lambda *_args, **_kwargs: asyncio.sleep(0, result=resolved_video_media()),
    )
    monkeypatch.setattr(
        bot,
        "save_tool_test_result",
        lambda *args, **_kwargs: saved.append(args),
    )

    async def fake_executor(query, _context, state, _lang="vi", **kwargs):
        captured.append((query, dict(state), dict(kwargs)))
        await query.edit_message_text(
            "✅ <b>Hoàn tất</b>\n\nTiến độ: 100%",
            parse_mode="HTML",
        )
        return {
            "ok": True,
            "mode": mode,
            "video_delivered": True,
            "final_mp4_exists": True,
            "final_mp4_validated": True,
            "final_mp4_delivered": True,
            "canonical_final_artifact_bytes": 4096,
            "source_duration": 8.0,
            "final_mp4_duration": 8.0,
            "duration_coverage_ok": True,
            "sent_video": 1,
            "telegram_message_id": "250027",
            "provider_route": {
                "asr": "fixture-asr",
                "translation": "fixture-translation",
                "tts": "fixture-tts",
                "mux": "ffmpeg",
            },
        }

    monkeypatch.setattr(bot, "execute_video_dubbing_pipeline", fake_executor)
    update = command_update(uid)

    result = asyncio.run(
        bot._run_admin_video_pipeline_smoke_core(
            update,
            confirmed_context(),
            mode,
        )
    )

    assert result["final_mp4_delivered"] is True
    assert len(captured) == 1
    _query, state, kwargs = captured[0]
    assert state["mode"] == mode
    assert state["video_processing_mode"] == mode
    assert state["_pipeline_source_bytes_override"] == b"fixture-video-bytes"
    assert state["_pipeline_source_content_type_override"] == "video/mp4"
    assert kwargs["admin_interactive_confirm"] is True
    assert len(update.message.sent_messages[0].edits) == 1
    assert "Tiến độ: 100%" in update.message.sent_messages[0].edits[0]["text"]
    assert any(row[1] == "PASS" for row in saved)
    assert "Final MP4 delivered: <code>YES</code>" in update.message.outputs[-1]["text"]


def test_admin_video_smoke_never_passes_without_delivered_mp4(monkeypatch):
    uid = 250028
    saved = []
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    block_legacy_smoke_provider_path(monkeypatch)
    monkeypatch.setattr(
        bot,
        "resolve_stt_test_media",
        lambda *_args, **_kwargs: asyncio.sleep(0, result=resolved_video_media()),
    )
    monkeypatch.setattr(
        bot,
        "save_tool_test_result",
        lambda *args, **_kwargs: saved.append(args),
    )

    async def partial_executor(*_args, **_kwargs):
        return {
            "ok": True,
            "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
            "partial_audio_delivered": True,
            "final_mp4_delivered": False,
            "status": "PARTIAL_AUDIO_ONLY",
            "detail": "mux_not_completed",
        }

    monkeypatch.setattr(bot, "execute_video_dubbing_pipeline", partial_executor)
    update = command_update(uid)

    result = asyncio.run(
        bot._run_admin_video_pipeline_smoke_core(
            update,
            confirmed_context(),
            bot.VIDEO_SUBTITLE_MODE_DUB,
        )
    )

    assert result["final_mp4_delivered"] is False
    assert any(row[1] == "FAIL" for row in saved)
    assert not any(row[1] == "PASS" for row in saved)
    assert "Final MP4 delivered: <code>NO</code>" in update.message.outputs[-1]["text"]


def test_tts_failure_keeps_sanitized_provider_detail_for_admin_debug():
    source = inspect.getsource(bot.video_dubbing_tts_bytes)
    assert "sanitize_log_text(str(detail or status))" in source
    assert "errors.append(f\"{label}={status}:" in source


def test_generated_video_delivery_waits_for_message_id_without_retry():
    calls = []

    class DeliveryMessage:
        async def reply_video(self, **kwargs):
            calls.append(dict(kwargs))
            return SimpleNamespace(
                message_id=55225,
                video=SimpleNamespace(file_id="delivered-video-file"),
            )

    result = asyncio.run(
        bot.send_generated_video_bytes_for_delivery(
            DeliveryMessage(),
            b"valid-video-bytes" * 128,
            filename="subdub-live25.mp4",
            caption="SubDub delivery",
        )
    )

    assert result["sent"] is True
    assert result["telegram_message_id"] == "55225"
    assert len(calls) == 1
    assert calls[0]["read_timeout"] >= 60
    assert calls[0]["write_timeout"] >= 60
    assert calls[0]["connect_timeout"] >= 20
    assert calls[0]["pool_timeout"] >= 20
