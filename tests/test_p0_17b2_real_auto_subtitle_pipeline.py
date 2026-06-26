import asyncio
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class CaptureMessage:
    def __init__(self, chat_id=172200, video=None, audio=None, voice=None, document=None):
        self.chat_id = chat_id
        self.message_id = 22
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


class CaptureQuery:
    def __init__(self, data, user_id=172201):
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
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "p0_17b2_assets.db"))
    monkeypatch.setattr(bot, "DB_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("SUBTITLE_ASSET_STORAGE_DIR", str(tmp_path / "subtitle_assets"))
    monkeypatch.setenv("TRANSLATION_ASSET_STORAGE_DIR", str(tmp_path / "translation_assets"))
    monkeypatch.setenv("DUB_ASSET_STORAGE_DIR", str(tmp_path / "dub_assets"))
    bot.init_db()


def test_public_type_guard_when_asr_not_ready(monkeypatch):
    uid = 172202
    bot.clear_video_dubbing_pending(uid)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "video_dubbing_public_processing_ready", lambda *_args, **_kwargs: False)

    async def forbidden_provider(*_args, **_kwargs):
        raise AssertionError("public guard must not call providers")

    monkeypatch.setattr(bot, "video_dubbing_transcribe_bytes", forbidden_provider)
    query = CaptureQuery(f"videodub|type|{bot.VIDEO_SUBTITLE_MODE_CREATE}", uid)

    asyncio.run(bot.handle_video_dubbing_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    text = query.outputs[-1]["text"]
    markup = query.outputs[-1]["reply_markup"]
    assert "Tạo phụ đề tự động" in text
    assert "Bot chưa xử lý và chưa trừ Xu" in text
    assert _callbacks(markup) == ["videodub|source_upload", "videodub|back_type", "menu|main"]
    assert bot.get_video_dubbing_pending(uid)["step"] == "source"


def test_transcribe_media_audio_does_not_require_ffmpeg(monkeypatch):
    async def forbidden_extract(*_args, **_kwargs):
        raise AssertionError("audio input must not require ffmpeg extraction")

    async def fake_transcribe(audio_bytes, _context, content_type="application/octet-stream", **_kwargs):
        assert audio_bytes == b"audio-bytes"
        assert content_type == "audio/mpeg"
        return "stub_asr", "xin chao tu audio", "ok"

    monkeypatch.setattr(bot, "video_dubbing_extract_audio", forbidden_extract)
    monkeypatch.setattr(bot, "video_dubbing_transcribe_bytes", fake_transcribe)

    result = asyncio.run(bot.transcribe_media_to_segments({
        "bytes": b"audio-bytes",
        "content_type": "audio/mpeg",
        "media_kind": "audio",
        "duration_seconds": 6,
    }))

    assert result["output_valid"] is True
    assert result["provider"] == "stub_asr"
    assert result["segments"][0]["start"] == 0


def test_transcribe_media_video_requires_audio_extract(monkeypatch):
    async def forbidden_transcribe(*_args, **_kwargs):
        raise AssertionError("ASR must not receive raw video bytes when extraction is unavailable")

    monkeypatch.setattr(bot, "video_dubbing_audio_extract_ready", lambda: False)
    monkeypatch.setattr(bot, "video_dubbing_transcribe_bytes", forbidden_transcribe)

    result = asyncio.run(bot.transcribe_media_to_segments({
        "bytes": b"video-bytes",
        "content_type": "video/mp4",
        "media_kind": "video",
        "duration_seconds": 6,
    }))

    assert result["output_valid"] is False
    assert result["status"] == "audio_extract_unavailable"


def test_transcribe_media_video_extracts_then_transcribes(monkeypatch):
    monkeypatch.setattr(bot, "video_dubbing_audio_extract_ready", lambda: True)

    async def fake_extract(source_bytes, content_type="application/octet-stream", max_seconds=0):
        assert source_bytes == b"video-bytes"
        assert content_type == "video/mp4"
        return b"audio-from-video", "audio/mpeg", "ffmpeg_audio_extract"

    async def fake_transcribe(audio_bytes, _context, content_type="application/octet-stream", **_kwargs):
        assert audio_bytes == b"audio-from-video"
        assert content_type == "audio/mpeg"
        return "stub_asr", "hello from video", "ok"

    monkeypatch.setattr(bot, "video_dubbing_extract_audio", fake_extract)
    monkeypatch.setattr(bot, "video_dubbing_transcribe_bytes", fake_transcribe)

    result = asyncio.run(bot.transcribe_media_to_segments({
        "bytes": b"video-bytes",
        "content_type": "video/mp4",
        "media_kind": "video",
        "duration_seconds": 8,
    }))

    assert result["output_valid"] is True
    assert result["detail"].startswith("ffmpeg_audio_extract")
    assert result["transcript_text"] == "hello from video"


def test_auto_subtitle_default_outputs_srt_vtt_txt():
    srt = bot.video_dubbing_srt_from_segments([
        {"start": 0, "end": 2, "text": "Xin chao"},
        {"start": 2, "end": 4, "text": "TOAN AAS"},
    ])

    items = bot.video_dubbing_subtitle_output_items(srt, "all", bot.VIDEO_SUBTITLE_MODE_CREATE)
    output_types = [item["output_type"] for item in items]

    assert output_types == ["srt", "vtt", "txt"]
    assert items[0]["filename"].endswith(".srt")
    assert items[1]["bytes"].startswith(b"WEBVTT")
    assert items[2]["bytes"].strip() == b"Xin chao\nTOAN AAS"


def test_auto_subtitle_pipeline_sends_srt_vtt_txt_after_confirm(monkeypatch, tmp_path):
    _init_media_asset_db(monkeypatch, tmp_path)

    async def fake_download(_context, state):
        assert state["source_file_id"] == "audio-file"
        return b"audio-bytes", "audio/mpeg"

    async def fake_transcribe(audio_bytes, _context, content_type="application/octet-stream", **_kwargs):
        assert audio_bytes == b"audio-bytes"
        assert content_type == "audio/mpeg"
        return "stub_asr", "xin chao day la phu de tu dong", "ok"

    monkeypatch.setattr(bot, "video_dubbing_public_processing_ready", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(bot, "video_dubbing_download_source", fake_download)
    monkeypatch.setattr(bot, "video_dubbing_transcribe_bytes", fake_transcribe)
    monkeypatch.setattr(bot, "get_user", lambda _uid: (99999, 0, 0))
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "apply_member_service_discount", lambda _uid, amount, _event: {"final_cost": amount})
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *_args, **_kwargs: {"ok": True, "final_cost": 1})

    query = CaptureQuery("videodub|final", 172203)
    result = asyncio.run(bot.execute_video_dubbing_pipeline(
        query,
        SimpleNamespace(),
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_CREATE,
            "video_file_id": "audio-file",
            "source_file_id": "audio-file",
            "source_file_ref": "audio-file",
            "source_mime_type": "audio/mpeg",
            "media_kind": "audio",
            "source_duration": 6,
            "product_context": bot.PRODUCT_CONTEXT_SHOWROOM,
        },
        "vi",
    ))

    sent_files = [item.get("filename") for item in query.outputs if item.get("document")]
    assert result["ok"] is True
    assert result["has_subtitle"] is True
    assert {".srt"} == {filename[-4:] for filename in sent_files}
    assert len(result["subtitle_asset_ids"]) == 1


def test_subtitle_translate_upload_keeps_product_context(monkeypatch):
    uid = 172204
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "await_video",
        mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        origin="translation",
        product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
        entry_surface="studio",
    )
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: None)
    monkeypatch.setattr(bot, "remember_last_media", lambda _update: None)

    async def fake_prepare(_context, passed_state, user_id, allow_admin=False):
        assert passed_state["mode"] == bot.VIDEO_SUBTITLE_MODE_CREATE
        assert passed_state["requested_mode"] == bot.VIDEO_SUBTITLE_MODE_TRANSLATE
        source = "1\n00:00:00,000 --> 00:00:02,000\nXin chao tu video"
        ref = bot.set_video_dubbing_artifact(user_id, "source_subtitle", source)
        saved = bot.set_video_dubbing_pending(user_id, passed_state.get("step") or "creating_original_subtitle", subtitle_ref=ref)
        return {
            "state": saved,
            "source_subtitle": source,
            "source_segments": [{"start": 0, "end": 2, "text": "Xin chao tu video"}],
            "detected_language": "vi",
        }

    monkeypatch.setattr(bot, "video_dubbing_prepare_subtitles", fake_prepare)
    message = CaptureMessage(
        chat_id=uid,
        video=SimpleNamespace(
            file_id="translate-video",
            file_unique_id="translate-video-unique",
            file_name="translate-video.mp4",
            mime_type="video/mp4",
            duration=10,
            file_size=2048,
            width=720,
            height=1280,
        ),
    )

    handled = asyncio.run(bot.handle_video_dubbing_pending_upload(
        SimpleNamespace(effective_user=SimpleNamespace(id=uid), message=message),
        SimpleNamespace(),
    ))

    state = bot.get_video_dubbing_pending(uid)
    assert handled is True
    assert state["active_flow"] == "subtitle_translate"
    assert state["product_context"] == bot.PRODUCT_CONTEXT_SHOWROOM
    assert state["source_file_ref"] == "translate-video"
    assert state["source_media_type"] == "video"
    assert state["step"] == "language"
    assert state["subtitle_ref"]


def test_subtitle_engine_status_mentions_real_media_pipeline():
    joined = "\n".join(bot.subtitle_engine_status_lines() + bot.dub_engine_status_lines())

    assert "Video audio extraction" in joined
    assert "Auto subtitle from video/audio" in joined
    assert "Dub from video/audio" in joined
    forbidden = ["Bearer ", "Authorization:", "API_KEY=", "SECRET="]
    assert not any(marker in joined for marker in forbidden)
