import asyncio
import time
from types import SimpleNamespace

import bot


class CaptureMessage:
    def __init__(self, text="", video=None, audio=None, voice=None, document=None):
        self.text = text
        self.caption = ""
        self.chat_id = 173300
        self.message_id = 31
        self.reply_to_message = None
        self.video = video
        self.audio = audio
        self.voice = voice
        self.document = document
        self.outputs = []

    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        self.outputs.append({"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup, **kwargs})
        return SimpleNamespace(text=text, reply_markup=reply_markup)

    async def reply_document(self, document=None, filename=None, caption=None, **kwargs):
        self.outputs.append({"document": document, "filename": filename, "caption": str(caption or ""), **kwargs})
        return SimpleNamespace(document=SimpleNamespace(file_id=f"doc-{filename or 'file'}"))

    async def reply_audio(self, audio=None, filename=None, caption=None, **kwargs):
        self.outputs.append({"audio": audio, "filename": filename, "caption": str(caption or ""), **kwargs})
        return SimpleNamespace(audio=SimpleNamespace(file_id=f"audio-{filename or 'file'}"))


def command_update(command, user_id=173301):
    message = CaptureMessage(command)
    user = SimpleNamespace(id=user_id)
    return SimpleNamespace(
        effective_user=user,
        effective_chat=SimpleNamespace(id=user_id),
        effective_message=message,
        message=message,
    )


def media_update(user_id=173301, kind="video"):
    media = SimpleNamespace(
        file_id=f"{kind}-file",
        file_unique_id=f"{kind}-unique",
        file_name=f"sample.{ 'mp4' if kind == 'video' else 'mp3'}",
        mime_type="video/mp4" if kind == "video" else "audio/mpeg",
        duration=8,
        file_size=2048,
    )
    message = CaptureMessage(**{kind: media})
    user = SimpleNamespace(id=user_id)
    return SimpleNamespace(
        effective_user=user,
        effective_chat=SimpleNamespace(id=user_id),
        effective_message=message,
        message=message,
    )


def configured_deepgram(monkeypatch, smoke_status="NOT_TESTED"):
    monkeypatch.setattr(bot, "ASR_PROVIDER", "deepgram")
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "configured")
    monkeypatch.setattr(bot, "AgentDeepgram", object)
    monkeypatch.setattr(bot, "key4u_asr_configured", lambda: False)
    monkeypatch.setattr(bot, "shopaikey_stt_public_ready", lambda: False)
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "")
    monkeypatch.setattr(bot, "SHOPAIKEY_AUDIO_TRANSCRIPTION_ENDPOINT", "")
    monkeypatch.setattr(bot, "asr_smoke_status", lambda: smoke_status)
    monkeypatch.setattr(bot, "video_dubbing_audio_extract_ready", lambda: True)


def test_tool_test_asr_alias_uses_asr_copy(monkeypatch):
    configured_deepgram(monkeypatch)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "resolve_stt_test_media", lambda *_args, **_kwargs: asyncio.sleep(0, result=None))
    update = command_update("/tool_test_asr --confirm-paid")

    asyncio.run(bot.cmd_tool_test_asr(update, SimpleNamespace(args=["--confirm-paid"])))

    assert update.message.outputs[-1]["text"] == "Gửi hoặc reply voice/audio/video ngắn để test ASR."
    assert bot.get_pending_admin_tool_test(update.effective_user.id)["tool"] == "asr"
    bot.clear_pending_admin_tool_test(update.effective_user.id)


def test_tool_test_stt_still_works(monkeypatch):
    configured_deepgram(monkeypatch)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "resolve_stt_test_media", lambda *_args, **_kwargs: asyncio.sleep(0, result=None))
    update = command_update("/tool_test_stt --confirm-paid")

    asyncio.run(bot.cmd_tool_test_stt(update, SimpleNamespace(args=["--confirm-paid"])))

    assert "test ASR" in update.message.outputs[-1]["text"]
    bot.clear_pending_admin_tool_test(update.effective_user.id)


def test_tool_test_asr_requires_confirm_paid(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "save_tool_test_result", lambda *_args, **_kwargs: None)
    called = {"provider": 0}

    async def forbidden_provider(*_args, **_kwargs):
        called["provider"] += 1

    monkeypatch.setattr(bot, "transcribe_media_to_segments", forbidden_provider)
    update = command_update("/tool_test_asr")

    asyncio.run(bot.cmd_tool_test_asr(update, SimpleNamespace(args=[])))

    assert called["provider"] == 0
    assert "--confirm-paid" in update.message.outputs[-1]["text"]


def test_tool_test_asr_runs_when_adapter_configured_but_not_smoked(monkeypatch):
    configured_deepgram(monkeypatch, "NOT_TESTED")
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(
        bot,
        "resolve_stt_test_media",
        lambda *_args, **_kwargs: asyncio.sleep(
            0,
            result={
                "bytes": b"audio",
                "content_type": "audio/mpeg",
                "file_type": "audio",
                "file_size": 5,
                "source": "reply",
            },
        ),
    )

    async def fake_transcribe(*_args, **_kwargs):
        return {
            "output_valid": True,
            "status": "pass",
            "transcript_text": "xin chao",
            "provider": "deepgram",
            "detail": "ok",
        }

    saved = []
    monkeypatch.setattr(bot, "transcribe_media_to_segments", fake_transcribe)
    monkeypatch.setattr(bot, "save_tool_test_result", lambda *args, **_kwargs: saved.append(args))
    update = command_update("/tool_test_asr --confirm-paid")

    asyncio.run(bot.cmd_tool_test_asr(update, SimpleNamespace(args=["--confirm-paid"])))

    assert any(row[0] == "asr" and row[1] == "PASS" for row in saved)
    assert "ASR PASS" in update.message.outputs[-1]["text"]


def test_tool_test_asr_fail_does_not_enable_public(monkeypatch):
    configured_deepgram(monkeypatch, "FAIL")
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", True)

    readiness = bot.get_asr_adapter_readiness(public=True)

    assert readiness["configured"] is True
    assert readiness["smoke_ready"] is False
    assert readiness["public_ready"] is False


def test_tool_test_auto_subtitle_does_not_require_previous_asr_ready(monkeypatch):
    called = []

    async def fake_core(_update, _context, mode):
        called.append(mode)
        return "ran"

    monkeypatch.setattr(bot, "_run_admin_video_pipeline_smoke_core", fake_core)
    result = asyncio.run(
        bot.run_admin_video_pipeline_smoke(
            command_update("/tool_test_auto_subtitle --confirm-paid"),
            SimpleNamespace(args=["--confirm-paid"]),
            bot.VIDEO_SUBTITLE_MODE_CREATE,
        )
    )

    assert result == "ran"
    assert called == [bot.VIDEO_SUBTITLE_MODE_CREATE]


def test_admin_asr_media_not_hijacked_by_generic_video_menu(monkeypatch):
    uid = 173302
    bot.set_pending_admin_tool_test(uid, "asr", "/tool_test_asr")
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    called = []

    async def fake_asr(_update, context):
        called.append(tuple(context.args))

    monkeypatch.setattr(bot, "cmd_tool_test_asr", fake_asr)
    update = media_update(uid, "video")

    asyncio.run(bot.handle_media_cache_only(update, SimpleNamespace(bot=SimpleNamespace())))

    assert called == [("--confirm-paid",)]
    assert update.message.outputs == []
    assert not bot.get_pending_admin_tool_test(uid)


def test_admin_auto_subtitle_media_not_hijacked_by_generic_video_menu(monkeypatch):
    uid = 173303
    bot.set_pending_admin_tool_test(uid, "auto_subtitle", "/tool_test_auto_subtitle")
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    called = []

    async def fake_auto(_update, _context):
        called.append("auto")

    monkeypatch.setattr(bot, "cmd_tool_test_subtitle_generate", fake_auto)
    update = media_update(uid, "video")

    asyncio.run(bot.handle_media_cache_only(update, SimpleNamespace(bot=SimpleNamespace())))

    assert called == ["auto"]
    assert update.message.outputs == []


def test_admin_dub_audio_media_not_hijacked_by_generic_video_menu(monkeypatch):
    uid = 173304
    bot.set_pending_admin_tool_test(uid, "dub_audio", "/tool_test_dub_audio")
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    called = []

    async def fake_dub(_update, _context):
        called.append("dub")

    monkeypatch.setattr(bot, "cmd_tool_test_video_dub", fake_dub)
    update = media_update(uid, "audio")

    asyncio.run(bot.handle_media(update, SimpleNamespace(bot=SimpleNamespace())))

    assert called == ["dub"]
    assert update.message.outputs == []


def test_admin_smoke_pending_expires_after_2_minutes():
    uid = 173305
    bot.PENDING_ADMIN_TOOL_TEST[uid] = {
        "tool": "asr",
        "confirm_paid": True,
        "created_at": time.time() - 130,
        "expires_at": time.time() - 10,
    }

    assert bot.get_pending_admin_tool_test(uid) == {}
    assert uid not in bot.PENDING_ADMIN_TOOL_TEST


def test_normal_user_video_menu_still_works(monkeypatch):
    uid = 173306
    bot.clear_pending_admin_tool_test(uid)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    update = media_update(uid, "video")

    asyncio.run(bot.handle_media_cache_only(update, SimpleNamespace(bot=SimpleNamespace())))

    assert "TOAN AAS đã nhận video của bạn" in update.message.outputs[-1]["text"]


def test_status_asr_configured_distinct_from_smoke_ready(monkeypatch):
    configured_deepgram(monkeypatch, "NOT_TESTED")
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", False)

    readiness = bot.get_asr_adapter_readiness(public=True)

    assert readiness["configured"] is True
    assert readiness["smoke_ready"] is False
    assert readiness["public_ready"] is False
    assert readiness["adapter"] == "deepgram"


def test_status_public_ready_only_after_smoke_pass(monkeypatch):
    configured_deepgram(monkeypatch, "PASS")
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", False)

    readiness = bot.get_asr_adapter_readiness(public=True)

    assert readiness["configured"] is True
    assert readiness["smoke_ready"] is True
    assert readiness["public_ready"] is True


def test_public_auto_subtitle_opens_after_asr_smoke_pass(monkeypatch):
    configured_deepgram(monkeypatch, "PASS")
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PUBLIC_ENABLED", False)

    assert bot.video_dubbing_public_processing_ready(bot.VIDEO_SUBTITLE_MODE_CREATE)


def test_public_dub_opens_after_asr_and_tts_ready(monkeypatch):
    configured_deepgram(monkeypatch, "PASS")
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_DUB_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_DUB_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_DUB_TTS_ENABLED", True)
    monkeypatch.setattr(bot, "video_tts_provider_available_for", lambda public=True: True)

    assert bot.video_dubbing_public_processing_ready(bot.VIDEO_SUBTITLE_MODE_DUB)


def test_public_still_guarded_if_asr_smoke_fail(monkeypatch):
    configured_deepgram(monkeypatch, "FAIL")
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PUBLIC_ENABLED", False)

    assert not bot.video_dubbing_public_processing_ready(bot.VIDEO_SUBTITLE_MODE_CREATE)


def test_status_no_confusing_missing_when_adapter_detected(monkeypatch):
    configured_deepgram(monkeypatch, "NOT_TESTED")
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", False)

    joined = "\n".join(bot.subtitle_engine_status_lines() + bot.dub_engine_status_lines())

    assert "ASR configured: <code>YES</code>" in joined
    assert "Detected ASR adapter: <code>deepgram</code>" in joined
    assert "ASR adapter readiness: <code>MISSING</code>" not in joined
    assert not any(secret in joined for secret in ("Bearer ", "Authorization:", "API_KEY=", "SECRET="))
