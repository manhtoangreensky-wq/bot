import asyncio
from types import SimpleNamespace

import pytest

import bot


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


class FakeTelegramFile:
    def __init__(self, data=b"telegram-media"):
        self.data = data
        self.bytearray_called = False
        self.drive_called = False

    async def download_as_bytearray(self):
        self.bytearray_called = True
        return bytearray(self.data)

    async def download_to_drive(self, custom_path=None):
        self.drive_called = True
        with open(custom_path, "wb") as handle:
            handle.write(self.data)


class FakeBot:
    def __init__(self, tg_file):
        self.tg_file = tg_file

    async def get_file(self, file_id):
        self.file_id = file_id
        return self.tg_file


class CaptureMessage:
    def __init__(self, file_id="media-file", *, kind="audio", mime_type=None, file_name=None):
        self.chat_id = 17065
        self.message_id = 65
        self.outputs = []
        self.video = None
        self.audio = None
        self.voice = None
        self.document = None
        media = SimpleNamespace(
            file_id=file_id,
            file_unique_id=f"{file_id}-unique",
            file_name=file_name or (f"{file_id}.mp4" if kind == "video" else f"{file_id}.mp3"),
            mime_type=mime_type or ("video/mp4" if kind == "video" else "audio/mpeg"),
            duration=6,
            file_size=2048,
            width=720,
            height=1280,
        )
        if kind == "video":
            self.video = media
        elif kind == "voice":
            self.voice = media
        else:
            self.audio = media

    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        self.outputs.append({
            "kind": "text",
            "text": str(text),
            "parse_mode": parse_mode,
            "reply_markup": reply_markup,
            **kwargs,
        })
        return SimpleNamespace(text=text, reply_markup=reply_markup)


def _update(uid, message):
    return SimpleNamespace(effective_user=SimpleNamespace(id=uid), message=message)


def _seed_upload(monkeypatch):
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: None)
    monkeypatch.setattr(bot, "remember_last_media", lambda _update: None)


def _ctx_with_file(data=b"telegram-audio"):
    tg_file = FakeTelegramFile(data)
    return SimpleNamespace(bot=FakeBot(tg_file)), tg_file


def _patch_asr(monkeypatch, calls, transcript="xin chao tu asr"):
    async def fake_transcribe(audio_bytes, context, audio_content_type, **kwargs):
        calls.append({
            "audio_bytes": bytes(audio_bytes),
            "content_type": audio_content_type,
            "allow_admin": kwargs.get("allow_admin"),
        })
        return "unit-pr38-asr", transcript, "ok"

    monkeypatch.setattr(bot, "video_dubbing_transcribe_bytes", fake_transcribe)


def test_telegram_download_uses_pr38_bytearray_before_asr(monkeypatch):
    uid = 176501
    bot.clear_video_dubbing_pending(uid)
    ctx, tg_file = _ctx_with_file(b"telegram-audio")
    calls = []
    _patch_asr(monkeypatch, calls)
    state = bot.set_video_dubbing_pending(
        uid,
        "creating_original_subtitle",
        mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        source_file_id="audio-file",
        video_file_id="audio-file",
        source_file_name="speech.mp3",
        source_mime_type="audio/mpeg",
        media_kind="audio",
        source_media_type="audio",
        video_duration=6,
    )

    prepared = asyncio.run(bot.video_dubbing_prepare_subtitles(ctx, state, uid))

    pending = bot.get_video_dubbing_pending(uid)
    assert tg_file.bytearray_called is True
    assert tg_file.drive_called is False
    assert calls and calls[0]["audio_bytes"] == b"telegram-audio"
    assert prepared["source_segments"]
    assert "unit-pr38-asr" == prepared["asr_provider"]
    assert pending["subtitle_ref"]
    assert pending["source_subtitle_ref"] == pending["subtitle_ref"]


def test_video_media_extracts_audio_before_asr_even_with_octet_stream(monkeypatch):
    uid = 176502
    bot.clear_video_dubbing_pending(uid)
    ctx, _tg_file = _ctx_with_file(b"fake-video-bytes")
    calls = []
    _patch_asr(monkeypatch, calls)
    extract_calls = []

    monkeypatch.setattr(bot, "video_dubbing_audio_extract_ready", lambda: True)

    async def fake_embedded_subtitle(*_args, **_kwargs):
        return "", "no_embedded_subtitle"

    async def fake_extract(source_bytes, content_type, max_seconds=0):
        extract_calls.append((bytes(source_bytes), content_type, max_seconds))
        return b"audio-from-video", "audio/mpeg", "unit-video-extract"

    monkeypatch.setattr(bot, "video_dubbing_extract_embedded_subtitle", fake_embedded_subtitle)
    monkeypatch.setattr(bot, "video_dubbing_extract_audio", fake_extract)
    state = bot.set_video_dubbing_pending(
        uid,
        "creating_original_subtitle",
        mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        source_file_id="video-file",
        video_file_id="video-file",
        source_file_name="clear-voice.mp4",
        source_mime_type="application/octet-stream",
        media_kind="video",
        source_media_type="video",
        video_duration=6,
    )

    prepared = asyncio.run(bot.video_dubbing_prepare_subtitles(ctx, state, uid))

    assert extract_calls == [(b"fake-video-bytes", "application/octet-stream", 0)]
    assert calls and calls[0]["audio_bytes"] == b"audio-from-video"
    assert prepared["source_segments"]


def test_pr38_asr_engine_path_is_called_for_subtitle_plus_dub_media(monkeypatch):
    uid = 176503
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "waiting_media",
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
    )
    _seed_upload(monkeypatch)
    monkeypatch.setattr(bot, "video_dubbing_configured_readiness", lambda *_args, **_kwargs: {"missing": []})
    monkeypatch.setattr(bot, "video_dubbing_asr_missing_for_state", lambda *_args, **_kwargs: False)
    calls = []
    _patch_asr(monkeypatch, calls)
    ctx, tg_file = _ctx_with_file(b"combo-audio")
    message = CaptureMessage("combo-media", kind="audio")

    assert asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), ctx)) is True

    state = bot.get_video_dubbing_pending(uid)
    joined = "\n".join(item["text"] for item in message.outputs)
    assert tg_file.bytearray_called is True
    assert calls
    assert state["step"] == "original_subtitle_ready"
    assert state["source_subtitle_ref"] == state["subtitle_ref"]
    assert "TOAN AAS đang tạo phụ đề gốc" in joined
    assert "Đã tạo phụ đề gốc" in message.outputs[-1]["text"]


def test_pr38_asr_engine_path_is_called_for_subtitle_translate_media(monkeypatch):
    uid = 176504
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "await_video",
        mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        origin="translation",
    )
    _seed_upload(monkeypatch)
    calls = []
    _patch_asr(monkeypatch, calls)
    ctx, _tg_file = _ctx_with_file(b"translate-audio")
    message = CaptureMessage("translate-media", kind="audio")

    assert asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), ctx)) is True

    state = bot.get_video_dubbing_pending(uid)
    assert calls == []
    assert state["step"] == "language"
    assert not state["subtitle_ref"]
    assert not state["source_subtitle_ref"]
    assert "Dịch phụ đề sang ngôn ngữ nào" in message.outputs[-1]["text"]
    assert "videodub|output|srt" not in _callbacks(message.outputs[-1]["reply_markup"])


def test_pr38_asr_engine_path_is_called_for_auto_subtitle_media(monkeypatch):
    uid = 176505
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "await_video",
        mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        origin="translation",
    )
    _seed_upload(monkeypatch)
    calls = []
    _patch_asr(monkeypatch, calls)
    ctx, _tg_file = _ctx_with_file(b"subtitle-audio")
    message = CaptureMessage("subtitle-media", kind="audio")

    assert asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), ctx)) is True

    state = bot.get_video_dubbing_pending(uid)
    labels = _labels(message.outputs[-1]["reply_markup"])
    assert calls == []
    assert state["step"] == "confirm"
    assert not state["subtitle_ref"]
    assert not state["source_subtitle_ref"]
    assert "✅ Xuất video phụ đề" in labels
    assert "📄 Tải SRT" not in labels
    assert "📄 Tải VTT" not in labels
    assert "🧾 Tải TXT" not in labels


def test_pr38_asr_engine_path_is_called_for_dub_media_before_language(monkeypatch):
    uid = 176506
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "await_video",
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        origin="translation",
    )
    _seed_upload(monkeypatch)
    calls = []
    _patch_asr(monkeypatch, calls)
    ctx, _tg_file = _ctx_with_file(b"dub-audio")
    message = CaptureMessage("dub-media", kind="audio")

    assert asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), ctx)) is True

    state = bot.get_video_dubbing_pending(uid)
    assert calls == []
    assert state["step"] == "language"
    assert not state["subtitle_ref"]
    assert not state["source_subtitle_ref"]
    assert "TOAN AAS đang tạo phụ đề gốc" not in message.outputs[0]["text"]
    assert "lồng tiếng sang ngôn ngữ nào" in message.outputs[-1]["text"]


def test_non_empty_segments_are_required_before_success(monkeypatch):
    uid = 176507
    bot.clear_video_dubbing_pending(uid)
    ctx, _tg_file = _ctx_with_file(b"empty-audio")

    async def empty_resolve(*_args, **_kwargs):
        return {"subtitle": "", "script": "", "segments": [], "asr_provider": "unit-empty"}

    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", empty_resolve)
    state = bot.set_video_dubbing_pending(
        uid,
        "creating_original_subtitle",
        mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        source_file_id="empty-file",
        source_mime_type="audio/mpeg",
        media_kind="audio",
    )

    with pytest.raises(RuntimeError, match="subtitle_segments_empty"):
        asyncio.run(bot.video_dubbing_prepare_subtitles(ctx, state, uid))


def test_srt_vtt_txt_created_after_asr_success(monkeypatch):
    uid = 176508
    bot.clear_video_dubbing_pending(uid)
    ctx, _tg_file = _ctx_with_file(b"subtitle-audio")
    calls = []
    _patch_asr(monkeypatch, calls, transcript="mot hai ba bon")
    state = bot.set_video_dubbing_pending(
        uid,
        "creating_original_subtitle",
        mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        source_file_id="subtitle-file",
        source_mime_type="audio/mpeg",
        media_kind="audio",
        video_duration=6,
    )

    prepared = asyncio.run(bot.video_dubbing_prepare_subtitles(ctx, state, uid))
    outputs = bot.video_dubbing_subtitle_output_items(prepared["source_subtitle"], "all", bot.VIDEO_SUBTITLE_MODE_CREATE)

    assert [item["output_type"] for item in outputs] == ["srt", "vtt", "txt"]
    assert b"-->" in outputs[0]["bytes"]
    assert outputs[1]["bytes"].startswith(b"WEBVTT")
    assert b"mot hai ba bon" in outputs[2]["bytes"]


def test_transcript_media_uses_asr_and_defaults_to_txt_output(monkeypatch):
    uid = 176509
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "await_video",
        mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        active_flow=bot.VIDEO_DUBBING_FLOW_TRANSCRIPT,
        origin="translation",
    )
    _seed_upload(monkeypatch)
    calls = []
    _patch_asr(monkeypatch, calls, transcript="day la transcript")
    ctx, _tg_file = _ctx_with_file(b"transcript-audio")
    message = CaptureMessage("transcript-media", kind="audio")

    assert asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), ctx)) is True

    state = bot.get_video_dubbing_pending(uid)
    assert calls == []
    assert state["step"] == "confirm"
    assert state["active_flow"] == bot.VIDEO_DUBBING_FLOW_TRANSCRIPT
    assert state["output_type"] == "txt"
    assert state["output_format"] == "txt"


def test_no_charge_before_final_confirm(monkeypatch):
    uid = 176510
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "await_video",
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        origin="translation",
    )
    _seed_upload(monkeypatch)
    calls = []
    _patch_asr(monkeypatch, calls)
    monkeypatch.setattr(
        bot,
        "spend_fixed_credit_info",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("charged before final confirm")),
    )
    ctx, _tg_file = _ctx_with_file(b"no-charge-audio")
    message = CaptureMessage("no-charge-media", kind="audio")

    assert asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), ctx)) is True
    assert calls == []
    assert bot.get_video_dubbing_pending(uid)["step"] == "language"


def test_public_asr_failure_copy_has_no_provider_terms_b65():
    text = bot.video_dubbing_asr_failure_text("vi").lower()

    assert "toan aas chưa tạo được phụ đề từ file này" in text
    for term in ("provider", "adapter", "ffmpeg", "env", "api", "deepgram", "stack", "asr"):
        assert term not in text

