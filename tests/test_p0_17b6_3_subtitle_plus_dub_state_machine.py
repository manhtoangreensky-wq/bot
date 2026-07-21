import asyncio
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class CaptureMessage:
    def __init__(self, file_id="b63-video"):
        self.chat_id = 6300
        self.message_id = 63
        self.outputs = []
        self.video = SimpleNamespace(
            file_id=file_id,
            file_unique_id=f"{file_id}-unique",
            file_name=f"{file_id}.mp4",
            mime_type="video/mp4",
            duration=12,
            file_size=2048,
            width=720,
            height=1280,
        )
        self.audio = None
        self.voice = None
        self.document = None

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"kind": "text", "text": str(text), **kwargs})
        return SimpleNamespace(text=text)

    async def reply_document(self, **kwargs):
        self.outputs.append({"kind": "document", **kwargs})

    async def reply_audio(self, **kwargs):
        self.outputs.append({"kind": "audio", **kwargs})

    async def reply_video(self, **kwargs):
        self.outputs.append({"kind": "video", **kwargs})


class DummyQuery:
    def __init__(self, uid, data):
        self.from_user = SimpleNamespace(id=uid)
        self.data = data
        self.answers = []
        self.edits = []
        self.message = CaptureMessage(file_id=f"query-{uid}")
        self.message.chat_id = uid

    async def answer(self, text=None, **kwargs):
        self.answers.append({"text": text, **kwargs})

    async def edit_message_text(self, text, **kwargs):
        self.edits.append({"text": str(text), **kwargs})
        self.message.outputs.append({"kind": "edit", "text": str(text), **kwargs})
        return SimpleNamespace(text=text)


def _update(uid, message):
    return SimpleNamespace(effective_user=SimpleNamespace(id=uid), message=message)


def _callback_update(query):
    return SimpleNamespace(callback_query=query, effective_user=query.from_user)


def _seed_combo(uid):
    bot.clear_video_dubbing_pending(uid)
    subtitle_ref = bot.set_video_dubbing_artifact(
        uid,
        "source_subtitle",
        "1\n00:00:00,000 --> 00:00:02,000\nXin chào\n\n2\n00:00:02,000 --> 00:00:04,000\nTOAN AAS\n",
    )
    return bot.set_video_dubbing_pending(
        uid,
        "original_subtitle_ready",
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        process_type=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        requested_mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
        source_file_id="source-video",
        video_file_id="source-video",
        source_mime_type="video/mp4",
        video_duration=12,
        subtitle_ref=subtitle_ref,
        source_language="vi",
        detected_language="vi",
        segment_count=2,
        subtitle_segment_count=2,
    )


async def _press(uid, data, context=None):
    query = DummyQuery(uid, data)
    await bot.handle_video_dubbing_callback(_callback_update(query), context or SimpleNamespace())
    return query


def test_subtitle_plus_dub_waiting_media_consumes_video(monkeypatch):
    uid = 630101
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "waiting_media",
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
    )
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: None)
    monkeypatch.setattr(bot, "remember_last_media", lambda _update: None)
    monkeypatch.setattr(bot, "video_dubbing_configured_readiness", lambda *_args, **_kwargs: {"missing": []})
    monkeypatch.setattr(bot, "video_dubbing_asr_missing_for_state", lambda *_args, **_kwargs: False)

    async def fake_prepare(_context, state, user_id, allow_admin=False):
        raise AssertionError("upload must wait for original subtitle confirmation")

    monkeypatch.setattr(bot, "video_dubbing_prepare_subtitles", fake_prepare)
    message = CaptureMessage("combo-upload")

    assert asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace())) is True

    state = bot.get_video_dubbing_pending(uid)
    assert state["step"] == "language"
    assert state["active_flow"] == bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB
    joined = "\n".join(item["text"] for item in message.outputs if item["kind"] == "text")
    assert "Chọn ngôn ngữ" in joined or "ngôn ngữ" in joined.lower()
    assert "TOAN AAS đang tạo phụ đề gốc" not in joined
    assert "Bạn muốn xử lý video này theo hướng nào" not in joined


def test_subtitle_plus_dub_no_generic_video_fallthrough(monkeypatch):
    uid = 630102
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "original_subtitle_ready",
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
        subtitle_ref="video_dubbing_artifact:missing",
    )
    message = CaptureMessage("second-video")
    assert asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace())) is True
    assert "Phiên Phụ đề + Lồng tiếng đang ở bước khác" in message.outputs[-1]["text"]


def test_subtitle_plus_dub_creates_original_subtitle_first():
    text = bot.video_dubbing_source_text({"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}, "vi")
    labels = _labels(bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}))
    assert "xử lý video" in text.lower()
    assert "🎞 Video đã có phụ đề" in labels
    assert "🎧 Video chưa có phụ đề" in labels
    assert "📤 Gửi video cần xử lý" not in labels


def test_subtitle_plus_dub_no_confirm_full_before_original_subtitle():
    ui = bot.video_dubbing_source_text({"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}, "vi")
    ui += "\n" + "\n".join(_labels(bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB})))
    assert "Xác nhận tạo đầy đủ" not in ui
    assert "Tạo phụ đề gốc trước" not in ui


def test_subtitle_plus_dub_original_subtitle_ready_buttons():
    state = {"source_language": "vi", "video_duration": 12, "subtitle_segment_count": 2}
    labels = _labels(bot.subtitle_plus_dub_original_ready_keyboard("vi"))
    assert "Đã tạo phụ đề gốc" in bot.subtitle_plus_dub_original_ready_text(state, "vi")
    assert labels == ["🌐 Dịch phụ đề", "🎙 Lồng tiếng từ phụ đề gốc", "📄 Tải SRT gốc", "🧾 Xem transcript", "🏠 Menu chính"]


def test_subtitle_plus_dub_translation_language_screen():
    labels = _labels(bot.subtitle_plus_dub_translation_language_keyboard("vi"))
    assert bot.subtitle_plus_dub_translation_language_text("vi") == "🌐 <b>Chọn ngôn ngữ muốn dịch phụ đề</b>"
    assert labels[:6] == ["🇻🇳 Tiếng Việt", "🇺🇸 English", "🇨🇳 中文", "🇯🇵 日本語", "🇰🇷 한국어", "🌍 Ngôn ngữ khác"]


def test_subtitle_plus_dub_translate_preserves_timestamps(monkeypatch):
    async def fake_translate(text, target_lang="vi", allow_admin=False, updated_by=""):
        return {"text": f"{text} translated", "provider": "test"}

    monkeypatch.setattr(bot, "translate_subtitle_text", fake_translate)
    segments = [{"start": 5, "end": 7, "text": "hello"}, {"start": 7, "end": 9, "text": "world"}]
    result = asyncio.run(bot.translate_subtitle_segments(segments, "vi"))
    assert result["segments"][0]["start"] >= 5
    assert result["segments"][-1]["end"] <= 9
    assert "-->" in result["srt"]


def test_subtitle_plus_dub_translated_subtitle_ready_buttons():
    state = {"target_language": "English"}
    labels = _labels(bot.subtitle_plus_dub_translated_ready_keyboard("vi"))
    assert "Đã dịch phụ đề sang English" in bot.subtitle_plus_dub_translated_ready_text(state, "vi")
    assert labels == ["🎙 Lồng tiếng từ bản dịch này", "🌐 Dịch ngôn ngữ khác", "⬅️ Quay lại", "🏠 Menu chính"]


def test_subtitle_plus_dub_voice_selection_after_subtitle():
    labels = _labels(bot.subtitle_plus_dub_voice_keyboard("vi"))
    assert labels == ["👩 Giọng nữ mặc định", "👨 Giọng nam mặc định", "📚 Kho voice", "🎙 Tạo voice riêng", "⬅️ Quay lại", "🏠 Menu chính"]


def test_subtitle_plus_dub_preview_only_short_audio(monkeypatch):
    uid = 630110
    _seed_combo(uid)
    state = bot.set_video_dubbing_pending(uid, "dub_confirmation", dub_source="original_subtitle", voice_style="Nữ mặc định", voice_kind="default_female", voice_speed="1.0")
    calls = {"preview": 0, "full": 0}

    async def fake_preview(_query, _context, _state, _lang):
        calls["preview"] += 1
        return {"ok": True, "preview_seconds": 12}

    async def fake_full(*_args, **_kwargs):
        calls["full"] += 1
        raise AssertionError("full dub must not run on preview")

    monkeypatch.setattr(bot, "execute_subtitle_plus_dub_voice_preview", fake_preview)
    monkeypatch.setattr(bot, "execute_video_dubbing_pipeline", fake_full)
    query = asyncio.run(_press(uid, "videodub|combo_preview_dub"))
    assert calls == {"preview": 0, "full": 0}
    assert bot.get_video_dubbing_pending(uid)["step"] == "dub_confirmation"
    assert "Preview đang tạm khóa" in query.message.outputs[-1]["text"]


def test_subtitle_plus_dub_full_requires_confirm(monkeypatch):
    uid = 630111
    _seed_combo(uid)
    calls = {"full": 0}

    async def fake_full(*_args, **_kwargs):
        calls["full"] += 1
        return {"ok": True, "has_audio": True, "has_subtitle": True, "has_video": False}

    async def fake_execute_engine(_feature, params, _context):
        return {"ok": True, "runner_result": await params["runner"]()}

    monkeypatch.setattr(bot, "execute_video_dubbing_pipeline", fake_full)
    monkeypatch.setattr(bot, "execute_engine", fake_execute_engine)
    asyncio.run(_press(uid, "videodub|combo_dub_original"))
    asyncio.run(_press(uid, "videodub|voice|default_female"))
    assert calls["full"] == 0
    query = asyncio.run(_press(uid, "videodub|combo_full_dub"))
    assert calls["full"] == 1
    assert bot.get_video_dubbing_pending(uid)["step"] == "completed"
    assert "đã tạo được audio/phụ đề" in query.message.outputs[-1]["text"]
    assert "chưa ghép được thành video hoàn chỉnh" in query.message.outputs[-1]["text"]


def test_subtitle_plus_dub_outputs_audio_or_video_cleanly():
    audio_state = {"final_audio_available": "1", "final_video_available": "0"}
    video_state = {"final_audio_available": "1", "final_video_available": "1"}
    assert "📹 Tải video" not in _labels(bot.subtitle_plus_dub_completed_keyboard("vi", audio_state))
    assert "🔁 Thử ghép lại video" in _labels(bot.subtitle_plus_dub_completed_keyboard("vi", audio_state))
    assert "📹 Tải video hoàn chỉnh" in _labels(bot.subtitle_plus_dub_completed_keyboard("vi", video_state))


def test_subtitle_plus_dub_mux_unavailable_no_fake_mp4():
    text = bot.subtitle_plus_dub_completed_text({}, {"has_audio": True, "has_video": False}, "vi")
    assert "đã tạo được audio/phụ đề" in text
    assert "MP4" not in text


def test_subtitle_plus_dub_no_technical_public_terms():
    samples = [
        bot.video_dubbing_source_text({"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}, "vi"),
        bot.subtitle_plus_dub_original_ready_text({"source_language": "vi"}, "vi"),
        bot.subtitle_plus_dub_translation_language_text("vi"),
        bot.subtitle_plus_dub_voice_text({}, "vi"),
        bot.subtitle_plus_dub_confirm_text({"dub_source": "original_subtitle", "voice_style": "Nữ mặc định"}, "vi"),
    ]
    forbidden = ("provider", "api", "asr", "tts", "smoke", "mode_disabled", "traceback", "key4u", "shopaikey")
    for sample in samples:
        lowered = sample.lower()
        assert all(term not in lowered for term in forbidden)


def test_subtitle_plus_dub_back_routing():
    uid = 630115
    _seed_combo(uid)
    asyncio.run(_press(uid, "videodub|combo_translate"))
    assert bot.get_video_dubbing_pending(uid)["step"] == "choosing_translation_language"
    asyncio.run(_press(uid, "videodub|combo_back_original"))
    assert bot.get_video_dubbing_pending(uid)["step"] == "original_subtitle_ready"
    asyncio.run(_press(uid, "videodub|combo_dub_original"))
    asyncio.run(_press(uid, "videodub|voice|default_female"))
    assert bot.get_video_dubbing_pending(uid)["step"] == "dub_confirmation"
    asyncio.run(_press(uid, "videodub|combo_back_voice"))
    assert bot.get_video_dubbing_pending(uid)["step"] == "choosing_voice"


def test_subtitle_plus_dub_keeps_assets_between_steps(monkeypatch):
    uid = 630116
    state = _seed_combo(uid)
    subtitle_ref = state["subtitle_ref"]
    asyncio.run(_press(uid, "videodub|combo_translate"))
    assert bot.get_video_dubbing_pending(uid)["subtitle_ref"] == subtitle_ref
    asyncio.run(_press(uid, "videodub|combo_back_original"))
    assert bot.get_video_dubbing_pending(uid)["subtitle_ref"] == subtitle_ref
