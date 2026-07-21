import asyncio
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class CaptureMessage:
    def __init__(self, text="", chat_id=171700):
        self.text = text
        self.chat_id = chat_id
        self.message_id = 17
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


class CaptureQuery:
    def __init__(self, data, user_id=171701):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = CaptureMessage(chat_id=user_id)
        self.outputs = self.message.outputs

    async def answer(self, *args, **kwargs):
        self.outputs.append({"answer": args, "answer_kwargs": kwargs})
        return None

    async def edit_message_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        self.outputs.append({"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup, **kwargs})
        return SimpleNamespace(text=text, reply_markup=reply_markup)


def _init_media_asset_db(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "p0_17b_assets.db"))
    monkeypatch.setattr(bot, "DB_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("SUBTITLE_ASSET_STORAGE_DIR", str(tmp_path / "subtitle_assets"))
    monkeypatch.setenv("TRANSLATION_ASSET_STORAGE_DIR", str(tmp_path / "translation_assets"))
    monkeypatch.setenv("DUB_ASSET_STORAGE_DIR", str(tmp_path / "dub_assets"))
    bot.init_db()


def test_subtitle_output_formats_srt_vtt_txt():
    srt = "1\n00:00:00,000 --> 00:00:03,000\nXin chao\n"
    srt_item = bot.video_dubbing_subtitle_output_items(srt, "srt", bot.VIDEO_SUBTITLE_MODE_CREATE)[0]
    vtt_item = bot.video_dubbing_subtitle_output_items(srt, "vtt", bot.VIDEO_SUBTITLE_MODE_CREATE)[0]
    txt_item = bot.video_dubbing_subtitle_output_items(srt, "txt", bot.VIDEO_SUBTITLE_MODE_CREATE)[0]

    assert srt_item["filename"].endswith(".srt")
    assert vtt_item["filename"].endswith(".vtt")
    assert vtt_item["bytes"].startswith(b"WEBVTT")
    assert b"00:00:00.000 --> 00:00:03.000" in vtt_item["bytes"]
    assert txt_item["filename"].endswith(".txt")
    assert txt_item["bytes"].strip() == b"Xin chao"


def test_subtitle_ready_keyboard_exports_final_video_and_optional_srt():
    markup = bot.video_dubbing_output_keyboard("vi", {
        "mode": bot.VIDEO_SUBTITLE_MODE_CREATE,
        "subtitle_ref": "video_dubbing_artifact:u:source_subtitle",
    })
    callbacks = set(_callbacks(markup))
    labels = _labels(markup)

    assert {"videodub|final", "videodub|output|srt"}.issubset(callbacks)
    assert "📹 Tải video phụ đề" in labels
    assert "📄 Tải SRT" in labels
    assert "📄 Tải VTT" not in labels
    assert "🧾 Tải TXT" not in labels


def test_translation_menu_text_requires_confirm_before_provider(monkeypatch):
    async def forbidden_translate(*_args, **_kwargs):
        raise AssertionError("provider must not run before text translation confirm")

    monkeypatch.setattr(bot, "run_translate_text_to_target", forbidden_translate)
    user_id = 171702
    bot.set_translation_menu_pending(user_id, "text", target_language="en")
    message = CaptureMessage("xin chao", chat_id=user_id)
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id))

    handled = asyncio.run(bot.handle_translation_menu_pending_text(update, SimpleNamespace()))
    pending = bot.get_translation_menu_pending(user_id)

    assert handled is True
    assert pending["source_type"] == "text_confirm"
    assert pending["source_text"] == "xin chao"
    assert "Xác nhận dịch văn bản" in message.outputs[-1]["text"]
    assert "chưa dịch nội dung" in message.outputs[-1]["text"]
    assert "chưa trừ Xu" in message.outputs[-1]["text"]


def test_translation_result_creates_translation_asset(monkeypatch, tmp_path):
    _init_media_asset_db(monkeypatch, tmp_path)

    async def fake_translate(text, target):
        assert text == "xin chao"
        assert target == "en"
        return {"provider": "stub_translation", "text": "hello"}

    monkeypatch.setattr(bot, "translate_to_language", fake_translate)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=171703),
        callback_query=None,
        message=CaptureMessage(chat_id=171703),
    )

    asyncio.run(bot.run_translate_text_to_target(update, SimpleNamespace(), "xin chao", "en"))

    rows = bot.list_translation_asset_records(status="generated_unused")
    assert rows
    assert rows[0]["target_language"] == "en"
    assert rows[0]["output_type"] == "txt"
    assert rows[0]["output_bytes"] == len("hello".encode("utf-8"))


def test_dubbing_custom_voice_guarded_no_clone_route(monkeypatch):
    user_id = 171704
    bot.clear_video_dubbing_pending(user_id)
    bot.set_video_dubbing_pending(
        user_id,
        "voice",
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        origin="translation",
        product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
        target_language="English",
        video_file_id="video-file",
        source_file_id="video-file",
    )

    def forbidden_clone_intro(*_args, **_kwargs):
        raise AssertionError("dub flow must not enter custom clone creation")

    monkeypatch.setattr(bot, "voice_clone_intro_text", forbidden_clone_intro)
    query = CaptureQuery("videodub|voice_create", user_id)

    asyncio.run(bot.handle_video_dubbing_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert any("Voice riêng cho lồng tiếng đang tạm giới hạn" in item.get("text", "") for item in query.outputs)
    assert any("Giọng nữ mặc định" in label for item in query.outputs if item.get("reply_markup") for label in _labels(item["reply_markup"]))


def test_dub_pipeline_default_voice_asset_no_forced_video_render(monkeypatch, tmp_path):
    _init_media_asset_db(monkeypatch, tmp_path)

    async def fake_prepare(_context, state, _user_id, allow_admin=False):
        return {
            "state": state,
            "source_bytes": b"video-bytes",
            "content_type": "video/mp4",
            "source_subtitle": "1\n00:00:00,000 --> 00:00:02,000\nhello\n",
            "source_script": "hello",
            "output_subtitle": "1\n00:00:00,000 --> 00:00:02,000\nhello\n",
            "output_script": "hello",
            "asr_provider": "stub_asr",
        }

    async def fake_synthesize(segments, **kwargs):
        assert segments
        assert kwargs.get("base_speed") == 1.0
        return {"provider": "stub_tts", "chunks": [{"start": 0, "end": 2, "audio_bytes": b"audio-bytes"}]}

    async def fake_timeline(chunks, total_duration=0):
        assert chunks
        return b"timeline-audio", "timeline"

    async def fake_normalize(audio_bytes):
        assert audio_bytes == b"timeline-audio"
        return b"normalized-audio", "normalized"

    async def forbidden_render(*_args, **_kwargs):
        raise AssertionError("video render must not run when mux/render is not ready")

    monkeypatch.setattr(bot, "video_dubbing_public_processing_ready", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(bot, "video_dubbing_prepare_subtitles", fake_prepare)
    monkeypatch.setattr(bot, "synthesize_dub_segment_chunks", fake_synthesize)
    monkeypatch.setattr(bot, "build_dub_timeline_audio", fake_timeline)
    monkeypatch.setattr(bot, "normalize_dub_audio_bytes", fake_normalize)
    monkeypatch.setattr(bot, "video_dubbing_render_video", forbidden_render)
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "")
    monkeypatch.setattr(bot, "local_worker_status_payload", lambda: {"connected": False, "ffmpeg_path": ""})
    monkeypatch.setattr(bot, "get_user", lambda _uid: (99999, 0, 0))
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "apply_member_service_discount", lambda _uid, amount, _event: {"final_cost": amount})
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *_args, **_kwargs: {"ok": True, "final_cost": 1})

    query = CaptureQuery("unused", 171705)
    result = asyncio.run(bot.execute_video_dubbing_pipeline(
        query,
        SimpleNamespace(),
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
            "video_file_id": "video-file",
            "source_file_id": "video-file",
            "source_duration": 8,
            "target_language": "English",
            "voice_style": "giọng nữ mặc định",
            "voice_kind": "default_female",
            "voice_speed": "1.0",
            "output_type": "video",
            "source_mime_type": "video/mp4",
            "_pipeline_source_bytes_override": b"video-bytes",
        },
        "vi",
    ))

    assert result["ok"] is False
    assert result.get("has_video") is not True
    assert not any(item.get("video") for item in query.outputs)
    assert not any(item.get("audio") for item in query.outputs)


def test_video_addon_requires_session_and_back_route_preserves_context():
    user_id = 171706
    bot.clear_video_finalization_state(user_id)
    assert bot.video_dubbing_video_addon_session_ready(user_id) is False

    bot.set_video_finalization_state(user_id, {
        "source_file_id": "video-source",
        "selected_video_tier": "basic",
        "current_video_duration_seconds": 30,
        "object_prompt": "product",
        "direction_prompt": "pan right",
        "return_to_invoice": True,
    })

    assert bot.video_dubbing_video_addon_session_ready(user_id) is True
    labels = _labels(bot.video_dubbing_receipt_keyboard("vi", "video_addon", {}))
    assert "⬅️ Quay lại tùy chọn video" in labels


def test_asset_status_and_engine_status_do_not_call_providers(monkeypatch, tmp_path):
    _init_media_asset_db(monkeypatch, tmp_path)

    async def forbidden_provider(*_args, **_kwargs):
        raise AssertionError("status commands must not call providers")

    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "video_dubbing_transcribe_bytes", forbidden_provider)
    monkeypatch.setattr(bot, "video_dubbing_tts_bytes", forbidden_provider)
    monkeypatch.setattr(bot, "translate_subtitle_text", forbidden_provider)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=171707),
        message=CaptureMessage(chat_id=171707),
    )
    context = SimpleNamespace(args=[])

    asyncio.run(bot.cmd_subtitle_asset_status(update, context))
    asyncio.run(bot.cmd_translation_engine_status(update, context))
    asyncio.run(bot.cmd_dub_engine_status(update, context))

    joined = "\n".join(item.get("text", "") for item in update.message.outputs)
    assert "SUBTITLE ASSET STATUS" in joined
    assert "TRANSLATION ENGINE STATUS" in joined
    assert "DUB ENGINE STATUS" in joined
    assert "No provider call" in joined


def test_engine_status_no_secret_leak():
    joined = "\n".join(
        bot.subtitle_engine_status_lines()
        + bot.translation_engine_status_lines()
        + bot.dub_engine_status_lines()
    )
    forbidden = ["sk-live", "Bearer ", "Authorization:", "API_KEY=", "SECRET="]
    assert not any(marker in joined for marker in forbidden)
