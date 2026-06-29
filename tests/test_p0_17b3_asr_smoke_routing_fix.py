import asyncio
import inspect
import time
from types import SimpleNamespace

import bot


class CaptureMessage:
    def __init__(self, text="", caption="", video=None, audio=None, voice=None, document=None):
        self.text = text
        self.caption = caption
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

    async def reply_video(self, video=None, filename=None, caption=None, **kwargs):
        self.outputs.append({"video": video, "filename": filename, "caption": str(caption or ""), **kwargs})
        return SimpleNamespace(video=SimpleNamespace(file_id=f"video-{filename or 'file'}"))


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


def test_tool_test_full_dub_video_requires_confirm_paid(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "save_tool_test_result", lambda *_args, **_kwargs: None)
    called = {"pipeline": 0}

    async def forbidden_pipeline(*_args, **_kwargs):
        called["pipeline"] += 1

    monkeypatch.setattr(bot, "build_subtitle_dubbed_video_pipeline", forbidden_pipeline)
    update = command_update("/tool_test_full_dub_video")

    asyncio.run(bot.cmd_tool_test_full_dub_video(update, SimpleNamespace(args=[])))

    assert called["pipeline"] == 0
    assert "--confirm-paid" in update.message.outputs[-1]["text"]


def test_tool_test_full_dub_video_requires_media(monkeypatch):
    uid = 173307
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "resolve_stt_test_media", lambda *_args, **_kwargs: asyncio.sleep(0, result=None))
    update = command_update("/tool_test_full_dub_video --confirm-paid", user_id=uid)

    asyncio.run(bot.cmd_tool_test_full_dub_video(update, SimpleNamespace(args=["--confirm-paid"])))

    assert update.message.outputs[-1]["text"] == "Gửi hoặc reply video ngắn rồi dùng /tool_test_full_dub_video --confirm-paid trong vòng 2 phút."
    assert bot.get_pending_admin_tool_test(uid)["tool"] == "full_dub_video"
    bot.clear_pending_admin_tool_test(uid)


def test_tool_test_full_dub_video_video_not_hijacked_by_generic_menu(monkeypatch):
    uid = 173308
    bot.set_pending_admin_tool_test(uid, "full_dub_video", "/tool_test_full_dub_video")
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    called = []

    async def fake_full_dub(_update, context):
        called.append(tuple(context.args))

    monkeypatch.setattr(bot, "cmd_tool_test_full_dub_video", fake_full_dub)
    update = media_update(uid, "video")

    asyncio.run(bot.handle_media_cache_only(update, SimpleNamespace(bot=SimpleNamespace())))

    assert called == [("--confirm-paid",)]
    assert update.message.outputs == []
    assert not bot.get_pending_admin_tool_test(uid)


def test_pending_admin_smoke_context_full_dub_video(monkeypatch):
    uid = 173312
    bot.set_pending_admin_tool_test(uid, "full_dub_video", "/tool_test_full_dub_video")
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    called = []

    async def fake_full_dub(_update, context):
        called.append(("full_dub_video", tuple(context.args)))

    monkeypatch.setattr(bot, "cmd_tool_test_full_dub_video", fake_full_dub)
    update = media_update(uid, "video")

    asyncio.run(bot.handle_media(update, SimpleNamespace(bot=SimpleNamespace())))

    assert called == [("full_dub_video", ("--confirm-paid",))]
    assert update.message.outputs == []


def test_pending_admin_smoke_clears_after_use(monkeypatch):
    uid = 173313
    bot.set_pending_admin_tool_test(uid, "full_dub_video", "/tool_test_full_dub_video")
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)

    async def fake_full_dub(_update, _context):
        return None

    monkeypatch.setattr(bot, "cmd_tool_test_full_dub_video", fake_full_dub)
    update = media_update(uid, "video")

    asyncio.run(bot.handle_media_cache_only(update, SimpleNamespace(bot=SimpleNamespace())))

    assert not bot.get_pending_admin_tool_test(uid)


def test_tool_test_full_dub_video_outputs_mp4_when_mux_ready(monkeypatch):
    uid = 173309
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "save_tool_test_result", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        bot,
        "resolve_stt_test_media",
        lambda *_args, **_kwargs: asyncio.sleep(
            0,
            result={
                "bytes": b"video-bytes",
                "content_type": "video/mp4",
                "file_type": "video",
                "file_size": 11,
                "source": "reply",
            },
        ),
    )

    async def fake_pipeline(*_args, **_kwargs):
        return {
            "ok": True,
            "asr_provider": "key4u_audio",
            "translation_provider": "deepl",
            "tts_provider": "key4u_tts",
            "original_srt": "1\n00:00:00,000 --> 00:00:01,000\nXin chao\n",
            "translated_srt": "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
            "dub_audio": b"audio-bytes",
            "final_video": b"mp4-bytes",
            "mux_status": "completed",
        }

    monkeypatch.setattr(bot, "build_subtitle_dubbed_video_pipeline", fake_pipeline)
    update = command_update("/tool_test_full_dub_video --confirm-paid", user_id=uid)

    asyncio.run(bot.cmd_tool_test_full_dub_video(update, SimpleNamespace(args=["--confirm-paid"])))

    assert len([item for item in update.message.outputs if item.get("document")]) == 6
    assert any(item.get("audio") for item in update.message.outputs)
    assert any(item.get("video") for item in update.message.outputs)
    assert "Full Dub Video Smoke PASS" in update.message.outputs[-1]["text"]


def test_tool_test_full_dub_video_partial_outputs_when_mux_unavailable(monkeypatch):
    uid = 173310
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "save_tool_test_result", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        bot,
        "resolve_stt_test_media",
        lambda *_args, **_kwargs: asyncio.sleep(
            0,
            result={
                "bytes": b"video-bytes",
                "content_type": "video/mp4",
                "file_type": "video",
                "file_size": 11,
                "source": "last_media",
            },
        ),
    )

    async def fake_pipeline(*_args, **_kwargs):
        return {
            "ok": True,
            "asr_provider": "shopaikey_audio",
            "translation_provider": "gemini",
            "tts_provider": "shopaikey_tts",
            "original_srt": "1\n00:00:00,000 --> 00:00:01,000\nXin chao\n",
            "translated_srt": "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
            "dub_audio": b"audio-bytes",
            "final_video": b"",
            "mux_status": "unavailable",
        }

    monkeypatch.setattr(bot, "build_subtitle_dubbed_video_pipeline", fake_pipeline)
    update = command_update("/tool_test_full_dub_video --confirm-paid", user_id=uid)

    asyncio.run(bot.cmd_tool_test_full_dub_video(update, SimpleNamespace(args=["--confirm-paid"])))

    assert len([item for item in update.message.outputs if item.get("document")]) == 6
    assert any(item.get("audio") for item in update.message.outputs)
    assert not any(item.get("video") for item in update.message.outputs)
    assert any("ghép video đang tạm chưa sẵn sàng" in item.get("text", "") for item in update.message.outputs)


def test_tool_test_full_dub_video_no_customer_charge(monkeypatch):
    uid = 173311
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "save_tool_test_result", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        bot,
        "resolve_stt_test_media",
        lambda *_args, **_kwargs: asyncio.sleep(
            0,
            result={
                "bytes": b"video-bytes",
                "content_type": "video/mp4",
                "file_type": "video",
                "file_size": 11,
                "source": "reply",
            },
        ),
    )

    async def fake_pipeline(*_args, **_kwargs):
        return {
            "ok": True,
            "asr_provider": "key4u_audio",
            "translation_provider": "deepl",
            "tts_provider": "key4u_tts",
            "original_srt": "1\n00:00:00,000 --> 00:00:01,000\nXin chao\n",
            "translated_srt": "",
            "dub_audio": b"audio-bytes",
            "final_video": b"",
            "mux_status": "unavailable",
        }

    def forbidden_charge(*_args, **_kwargs):
        raise AssertionError("admin full dub smoke must not charge customer Xu")

    monkeypatch.setattr(bot, "build_subtitle_dubbed_video_pipeline", fake_pipeline)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", forbidden_charge)
    update = command_update("/tool_test_full_dub_video --confirm-paid", user_id=uid)

    asyncio.run(bot.cmd_tool_test_full_dub_video(update, SimpleNamespace(args=["--confirm-paid"])))

    assert "No Xu deducted" in update.message.outputs[-1]["text"]


def test_public_auto_subtitle_uses_segments():
    source = inspect.getsource(bot.video_dubbing_resolve_source_script)

    assert "video_dubbing_srt_from_segments" in source
    assert "result.get(\"segments\")" in source


def test_public_translate_subtitle_preserves_timestamps(monkeypatch):
    async def fake_translate(text, target_lang, **_kwargs):
        return {"text": f"{text} / {target_lang}", "provider": "stub_translate"}

    monkeypatch.setattr(bot, "translate_subtitle_text", fake_translate)
    segments = [{"index": 1, "start": 1.25, "end": 2.75, "text": "xin chao"}]

    result = asyncio.run(bot.translate_subtitle_segments(segments, "en"))

    assert result["segments"][0]["start"] == 1.25
    assert result["segments"][0]["end"] == 2.75
    assert "00:00:01,250 --> 00:00:02,750" in result["srt"]


def test_public_dub_uses_tts_per_segment(monkeypatch):
    calls = []

    async def fake_tts(text, *_args, **_kwargs):
        calls.append(text)
        return "stub_tts", f"audio:{text}".encode("utf-8"), "ok"

    monkeypatch.setattr(bot, "video_dubbing_tts_bytes", fake_tts)
    monkeypatch.setattr(bot, "video_dubbing_audio_duration_seconds", lambda *_args, **_kwargs: asyncio.sleep(0, result=0.5))
    segments = [
        {"index": 1, "start": 0.0, "end": 1.0, "text": "cau mot"},
        {"index": 2, "start": 1.0, "end": 2.0, "text": "cau hai"},
    ]

    result = asyncio.run(bot.synthesize_dub_segment_chunks(segments, allow_admin=True))

    assert calls == ["cau mot", "cau hai"]
    assert len(result["chunks"]) == 2


def test_default_tts_prioritizes_openai_compatible_speech():
    source = inspect.getsource(bot.video_dubbing_tts_bytes)

    assert source.index("Key4U OpenAI TTS") < source.index("ShopAIKey OpenAI TTS")
    assert source.index("candidates = openai_tts_candidates + candidates") > source.index("openai_tts_candidates.append")


def test_asr_provider_order_prefers_openai_compatible_before_deepgram():
    source = inspect.getsource(bot.asr_transcribe_audio)

    assert '"auto": ["key4u", "shopaikey", "deepgram"]' in source
    assert source.index('route == "key4u"') < source.index('route == "shopaikey"') < source.index('route == "deepgram"')


def test_public_subtitle_plus_dub_outputs_all_assets():
    source = inspect.getsource(bot.send_public_subtitle_dub_final_outputs)

    assert "mode == VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB" in source
    assert "reply_document" in source
    assert "reply_audio" in source
    assert "reply_video" in source


def test_public_final_mp4_only_when_mux_ready():
    source = inspect.getsource(bot.build_subtitle_dubbed_video_pipeline)
    render_index = source.index("video_dubbing_render_video")
    mux_gate_index = source.index("video_dubbing_mux_ready()")

    assert mux_gate_index < render_index


def test_public_no_generic_video_menu_in_active_flows():
    source = inspect.getsource(bot.handle_media_cache_only)

    assert source.index("handle_video_dubbing_pending_upload") < source.index("video_upload_received_text")


def test_public_no_custom_voice_clone_dependency():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)

    assert "synthesize_dub_segment_chunks" in source
    assert "voice_clone_intro_text" not in source


def test_public_dub_audio_invalid_no_charge():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    service_source = inspect.getsource(bot.subtitle_dub_product_pipeline.process_subtitle_dub_job)

    assert '"status": "NO_AUDIO_BYTES"' in service_source
    assert source.index("subtitle_dub_product_pipeline.process_subtitle_dub_job") < source.index("spend_fixed_credit_info")


def test_normal_video_menu_still_works_without_pending_context(monkeypatch):
    uid = 173314
    bot.clear_pending_admin_tool_test(uid)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    update = media_update(uid, "video")

    asyncio.run(bot.handle_media_cache_only(update, SimpleNamespace(bot=SimpleNamespace())))

    assert "TOAN AAS đã nhận video của bạn" in update.message.outputs[-1]["text"]


def test_pending_admin_smoke_expires():
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

    readiness = bot.get_asr_adapter_readiness(public=True)
    assert readiness["configured"] is True
    assert readiness["public_ready"] is False


def test_status_no_confusing_missing_when_adapter_detected(monkeypatch):
    configured_deepgram(monkeypatch, "NOT_TESTED")
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", False)

    joined = "\n".join(bot.subtitle_engine_status_lines() + bot.dub_engine_status_lines())

    assert "ASR configured: <code>YES</code>" in joined
    assert "Detected ASR adapter: <code>deepgram</code>" in joined
    assert "ASR adapter readiness: <code>MISSING</code>" not in joined
    assert not any(secret in joined for secret in ("Bearer ", "Authorization:", "API_KEY=", "SECRET="))


def _button_labels(markup):
    return [
        button.text
        for row in getattr(markup, "inline_keyboard", []) or []
        for button in row
    ]


def test_caption_tool_test_asr_consumes_video(monkeypatch):
    uid = 173401
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    called = []

    async def fake_asr(_update, context):
        called.append(tuple(context.args))

    monkeypatch.setattr(bot, "cmd_tool_test_asr", fake_asr)
    update = media_update(uid, "video")
    update.message.caption = "/tool_test_asr --confirm-paid"

    asyncio.run(bot.handle_media_cache_only(update, SimpleNamespace(bot=SimpleNamespace())))

    assert called == [("--confirm-paid",)]
    assert update.message.outputs == []


def test_caption_tool_test_requires_confirm_paid(monkeypatch):
    uid = 173402
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "save_tool_test_result", lambda *_args, **_kwargs: None)
    called = {"provider": 0}

    async def forbidden_provider(*_args, **_kwargs):
        called["provider"] += 1

    monkeypatch.setattr(bot, "transcribe_media_to_segments", forbidden_provider)
    update = media_update(uid, "video")
    update.message.caption = "/tool_test_asr"

    asyncio.run(bot.handle_media_cache_only(update, SimpleNamespace(bot=SimpleNamespace())))

    assert called["provider"] == 0
    assert "--confirm-paid" in update.message.outputs[-1]["text"]
    assert "TOAN AAS đã nhận video" not in update.message.outputs[-1]["text"]


def test_caption_tool_test_non_admin_rejected(monkeypatch):
    uid = 173403
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    update = media_update(uid, "video")
    update.message.caption = "/tool_test_full_dub_video --confirm-paid"

    asyncio.run(bot.handle_media_cache_only(update, SimpleNamespace(bot=SimpleNamespace())))

    assert "không có quyền" in update.message.outputs[-1]["text"]
    assert "TOAN AAS đã nhận video" not in update.message.outputs[-1]["text"]


def test_caption_tool_test_all_admin_smoke_commands_consume_media(monkeypatch):
    uid = 173404
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    called = []

    async def fake_auto(_update, context):
        called.append(("auto", tuple(context.args)))

    async def fake_dub(_update, context):
        called.append(("dub", tuple(context.args)))

    async def fake_full(_update, context):
        called.append(("full", tuple(context.args)))

    monkeypatch.setattr(bot, "cmd_tool_test_subtitle_generate", fake_auto)
    monkeypatch.setattr(bot, "cmd_tool_test_video_dub", fake_dub)
    monkeypatch.setattr(bot, "cmd_tool_test_full_dub_video", fake_full)

    for caption in (
        "/tool_test_auto_subtitle --confirm-paid",
        "/tool_test_dub_audio --confirm-paid",
        "/tool_test_full_dub_video --confirm-paid",
    ):
        update = media_update(uid, "video")
        update.message.caption = caption
        asyncio.run(bot.handle_media_cache_only(update, SimpleNamespace(bot=SimpleNamespace())))
        assert update.message.outputs == []

    assert called == [
        ("auto", ("--confirm-paid",)),
        ("dub", ("--confirm-paid",)),
        ("full", ("--confirm-paid",)),
    ]


def test_active_subtitle_flows_do_not_show_generic_video_menu(monkeypatch):
    uid = 173405
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    modes = [
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    ]
    for mode in modes:
        bot.clear_video_dubbing_pending(uid)
        bot.set_video_dubbing_pending(
            uid,
            "source",
            mode=mode,
            video_processing_mode=mode,
            origin="translation",
            product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
            active_flow={
                bot.VIDEO_SUBTITLE_MODE_CREATE: "auto_subtitle",
                bot.VIDEO_SUBTITLE_MODE_TRANSLATE: "subtitle_translate",
                bot.VIDEO_SUBTITLE_MODE_DUB: "dub_audio",
                bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB: "subtitle_plus_dub",
            }[mode],
        )
        update = media_update(uid, "video")

        asyncio.run(bot.handle_media_cache_only(update, SimpleNamespace(bot=SimpleNamespace())))

        joined = "\n".join(item.get("text", "") for item in update.message.outputs)
        assert "TOAN AAS đã nhận video" not in joined
        assert "Bạn muốn xử lý video này theo hướng nào" not in joined
    bot.clear_video_dubbing_pending(uid)


def test_translation_studio_lost_state_recovery_menu(monkeypatch):
    uid = 173406
    bot.clear_video_dubbing_pending(uid)
    bot.enter_product_context(uid, bot.PRODUCT_CONTEXT_SHOWROOM, origin_screen="menu|translate", product_area="translation")
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    update = media_update(uid, "video")

    asyncio.run(bot.handle_media_cache_only(update, SimpleNamespace(bot=SimpleNamespace())))

    text = update.message.outputs[-1]["text"]
    labels = _button_labels(update.message.outputs[-1]["reply_markup"])
    assert "Studio Dịch / Phụ đề / Lồng tiếng" in text
    assert "Tạo phụ đề" in " ".join(labels)
    assert "Dịch phụ đề" in " ".join(labels)
    assert "Lồng tiếng" not in " ".join(labels)
    assert "Tự quay" not in text + " ".join(labels)
    assert "Nâng cấp video" not in text + " ".join(labels)
    bot.clear_video_dubbing_pending(uid)
    bot.clear_product_context(uid)


def test_subtitle_file_upload_stays_in_dub_flow(monkeypatch):
    uid = 173407
    bot.clear_video_dubbing_pending(uid)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    bot.set_video_dubbing_pending(
        uid,
        "source",
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        origin="translation",
        product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
        active_flow="dub_audio",
    )
    document = SimpleNamespace(
        file_id="subtitle-file",
        file_unique_id="subtitle-unique",
        file_name="captions.srt",
        mime_type="application/x-subrip",
        file_size=128,
    )
    message = CaptureMessage(document=document)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=uid),
        effective_chat=SimpleNamespace(id=uid),
        effective_message=message,
        message=message,
    )
    subtitle_bytes = b"1\n00:00:00,000 --> 00:00:02,000\nXin chao\n"

    class FakeTelegramFile:
        async def download_as_bytearray(self):
            return bytearray(subtitle_bytes)

    class FakeBot:
        async def get_file(self, file_id):
            assert file_id == "subtitle-file"
            return FakeTelegramFile()

    asyncio.run(bot.handle_document_cache_only(update, SimpleNamespace(bot=FakeBot())))

    joined = "\n".join(item.get("text", "") for item in update.message.outputs)
    assert "chỉ xử lý video" in joined
    assert "Dịch file" not in joined
    assert "TOAN AAS đã nhận video" not in joined
    bot.clear_video_dubbing_pending(uid)


def test_dub_audio_source_keyboard_offers_recent_subtitle():
    markup = bot.video_dubbing_source_keyboard(
        "vi",
        {"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_DUB},
    )

    labels = " ".join(_button_labels(markup))
    assert "Gửi video cần lồng tiếng" in labels
    assert "Video đã có phụ đề" not in labels
    assert "Video chỉ có tiếng" not in labels
    assert "Dùng phụ đề vừa tạo" not in labels


def test_status_mentions_b4_isolation_flags(monkeypatch):
    configured_deepgram(monkeypatch, "NOT_TESTED")

    joined = "\n".join(bot.subtitle_engine_status_lines() + bot.dub_engine_status_lines())

    assert "ASR provider: <code>deepgram</code>" in joined
    assert "Generic video handler isolation: <code>YES</code>" in joined
    assert "Caption smoke command support: <code>YES</code>" in joined
