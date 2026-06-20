import asyncio
from types import SimpleNamespace

import pytest

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


class CaptureMessage:
    def __init__(self, text=""):
        self.text = text
        self.chat_id = 991201
        self.message_id = 91
        self.outputs = []

    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        item = {"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup, **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(text=text, reply_markup=reply_markup)


class CaptureQuery:
    def __init__(self, data, user_id):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = CaptureMessage()
        self.outputs = self.message.outputs

    async def answer(self, *args, **kwargs):
        return None

    async def edit_message_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        item = {"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup, **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(text=text, reply_markup=reply_markup)


async def _press(data, user_id):
    query = CaptureQuery(data, user_id)
    await bot.handle_video_dubbing_callback(SimpleNamespace(callback_query=query), SimpleNamespace())
    return query


def _source_markup(mode):
    return bot.video_dubbing_source_keyboard("vi", {"mode": mode, "origin": "translation"})


def test_video_translation_menu_labels_auto():
    labels = _labels(bot.video_dubbing_menu_keyboard("vi", "translation"))
    assert labels[:4] == [
        "👁 Tạo phụ đề tự động",
        "🗣 Lồng tiếng tự động",
        "🎬 Phụ đề + lồng tiếng",
        "🔗 Tải video từ link",
    ]


def test_create_subtitle_auto_label():
    assert bot.VIDEO_TRANSLATE_MODES[bot.VIDEO_SUBTITLE_MODE_CREATE] == "Tạo phụ đề tự động"
    assert "Tạo phụ đề tự động" in bot.video_dubbing_source_text({"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}, "vi")


def test_auto_dubbing_label():
    assert bot.VIDEO_TRANSLATE_MODES[bot.VIDEO_SUBTITLE_MODE_DUB] == "Lồng tiếng tự động"
    assert "Lồng tiếng tự động" in bot.video_dubbing_source_text({"mode": bot.VIDEO_SUBTITLE_MODE_DUB}, "vi")


def test_link_import_only_top_level():
    top = bot.video_dubbing_menu_keyboard("vi", "translation")
    assert "videodub|link_start" in _callbacks(top)
    for mode in (
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    ):
        assert "videodub|link_start" not in _callbacks(_source_markup(mode))


def test_no_copied_source_menu_inside_product_flows():
    for mode in (
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    ):
        assert _labels(_source_markup(mode))[:2] == ["📎 Gửi video/audio", "📂 Chọn từ Media"]


def test_auto_subtitle_only_original_language():
    text = bot.video_dubbing_upload_text({"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}, "vi")
    assert "đúng ngôn ngữ đang nói" in text
    assert "không dịch" in text


def test_auto_subtitle_no_translation_no_voice():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}
    labels = _labels(bot.video_dubbing_output_keyboard("vi", state))
    assert not bot.video_dubbing_requires_language(bot.VIDEO_SUBTITLE_MODE_CREATE)
    assert not bot.video_dubbing_requires_voice(bot.VIDEO_SUBTITLE_MODE_CREATE)
    assert not any("lồng tiếng" in label.lower() or "giọng" in label.lower() for label in labels)


def test_auto_subtitle_input_no_link_button():
    assert "videodub|link_start" not in _callbacks(_source_markup(bot.VIDEO_SUBTITLE_MODE_CREATE))


def test_auto_subtitle_output_no_dubbing_button_basic_product():
    labels = _labels(bot.video_dubbing_output_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}))
    assert not any("lồng tiếng" in label.lower() for label in labels)


def test_auto_subtitle_output_srt_burn_edit():
    callbacks = _callbacks(bot.video_dubbing_output_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}))
    assert callbacks == ["videodub|confirm_subtitle_create", "videodub|final", "videodub|output_back", "menu|main"]
    assert not {"videodub|output|srt", "videodub|output|burn", "videodub|subtitle_editor"}.intersection(callbacks)
    ready_callbacks = _callbacks(bot.video_dubbing_output_keyboard("vi", {
        "mode": bot.VIDEO_SUBTITLE_MODE_CREATE,
        "subtitle_ref": "video_dubbing_artifact:test:subtitle",
    }))
    assert {"videodub|output|srt", "videodub|output|burn", "videodub|subtitle_editor"}.issubset(ready_callbacks)


def test_auto_dubbing_input_no_link_button():
    assert "videodub|link_start" not in _callbacks(_source_markup(bot.VIDEO_SUBTITLE_MODE_DUB))


def test_auto_dubbing_language_then_voice():
    uid = "task21-dub-language-voice"
    bot.clear_video_dubbing_pending(uid)
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "video_file_id": "video", "source_file_id": "video"}
    state, text, _markup = bot.video_dubbing_next_screen_after_source(uid, state, "vi")
    assert state["step"] == "language"
    assert "Chọn ngôn ngữ lồng tiếng" in text
    state = bot.set_video_dubbing_pending(uid, "language", target_language="English", translate_requested="1")
    state, text, _markup = bot.video_dubbing_next_screen_after_source(uid, state, "vi")
    assert state["step"] == "voice"
    assert "Chọn giọng lồng tiếng" in text


def test_auto_dubbing_speed_numeric_input():
    assert bot.parse_video_dubbing_voice_speed("0.9") == "0.9"
    assert bot.parse_video_dubbing_voice_speed("1") == "1.0"
    assert bot.parse_video_dubbing_voice_speed("1.0") == "1.0"
    assert bot.parse_video_dubbing_voice_speed("1.5") == "1.5"
    with pytest.raises(ValueError):
        bot.parse_video_dubbing_voice_speed("0.6")
    with pytest.raises(ValueError):
        bot.parse_video_dubbing_voice_speed("abc")


def test_auto_dubbing_invoice_after_speed():
    text = bot.video_dubbing_confirm_text(
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
            "video_file_id": "video",
            "target_language": "English",
            "voice_style": "giọng nữ mặc định",
            "voice_speed": "1.5",
        },
        "vi",
    )
    assert "Tốc độ: <b>1.5</b>" in text
    assert "Chi phí dự kiến" not in text


def test_auto_dubbing_preview_6s():
    assert bot.calculate_preview_seconds(30) == 6
    assert bot.calculate_preview_seconds(999) == 6


def test_auto_dubbing_no_fake_output_when_provider_off(monkeypatch):
    monkeypatch.setattr(bot, "video_dubbing_capability", lambda *_args, **_kwargs: {"ok": False, "reason": "public_disabled"})
    query = CaptureQuery("unused", 991202)
    result = asyncio.run(
        bot.execute_video_dubbing_preview(
            query,
            SimpleNamespace(),
            {"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "video_file_id": "video"},
            "vi",
        )
    )
    assert result["ok"] is False
    assert result["guard"] is True
    assert query.outputs == []


def test_subtitle_dubbing_input_no_link_button():
    assert "videodub|link_start" not in _callbacks(_source_markup(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB))


def test_subtitle_dubbing_translate_subtitle_first():
    uid = "task21-combo-first"
    bot.clear_video_dubbing_pending(uid)
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "video_file_id": "video",
        "source_file_id": "video",
    }
    state, text, _markup = bot.video_dubbing_next_screen_after_source(uid, state, "vi")
    assert state["step"] == "language"
    assert "Dịch phụ đề sang ngôn ngữ nào" in text


def test_subtitle_dubbing_export_before_voice(monkeypatch):
    monkeypatch.setattr(bot, "video_dubbing_capability", lambda *_args, **_kwargs: {"ok": True})
    uid = "task21-combo-export"
    bot.clear_video_dubbing_pending(uid)
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "video_file_id": "video",
        "source_file_id": "video",
        "target_language": "Tiếng Việt",
    }
    state, text, markup = bot.video_dubbing_next_screen_after_source(uid, state, "vi")
    assert state["mode"] == bot.VIDEO_SUBTITLE_MODE_TRANSLATE
    assert state["step"] == "output"
    assert "Video đã sẵn sàng tạo phụ đề dịch" in text
    assert "✅ Xác nhận tạo đầy đủ" in _labels(markup)
    assert "📄 Xuất SRT" not in _labels(markup)
    assert not any("Giọng nữ" in label for label in _labels(markup))


def test_subtitle_dubbing_continue_voice_after_output():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "target_language": "English",
        "translated_subtitle_ref": "video_dubbing_artifact:test:translated",
    }
    assert "🗣 Tiếp tục lồng tiếng" in _labels(bot.video_dubbing_output_keyboard("vi", state))


def test_subtitle_dubbing_uses_translated_subtitle_for_tts(monkeypatch):
    captured = {}

    async def fake_download(_context, _state):
        return b"video", "video/mp4"

    async def fake_transcribe(_data, _context, _content_type="application/octet-stream"):
        return "ASR", "hello world", "ok"

    async def fake_translate(text, target, **_kwargs):
        assert text == "hello world"
        assert target == "Tiếng Việt"
        return {"text": "xin chào thế giới"}

    async def fake_tts(text, voice_style="", voice_id="", voice_speed="1.0"):
        captured.update({"text": text, "voice_style": voice_style, "voice_id": voice_id, "voice_speed": voice_speed})
        return "TTS", b"audio", "ok"

    monkeypatch.setattr(bot, "video_dubbing_capability", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(bot, "video_dubbing_download_source", fake_download)
    monkeypatch.setattr(bot, "video_dubbing_transcribe_bytes", fake_transcribe)
    monkeypatch.setattr(bot, "translate_subtitle_text", fake_translate)
    monkeypatch.setattr(bot, "video_dubbing_tts_bytes", fake_tts)
    monkeypatch.setattr(bot, "get_user", lambda _uid: (99999, 0, 0))
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "apply_member_service_discount", lambda _uid, amount, _event: {"final_cost": amount})
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *_args, **_kwargs: {"ok": True, "final_cost": 1})

    class OutputMessage:
        async def reply_document(self, **_kwargs):
            return None

        async def reply_audio(self, **_kwargs):
            return None

    query = SimpleNamespace(from_user=SimpleNamespace(id=991203), message=OutputMessage())
    result = asyncio.run(
        bot.execute_video_dubbing_pipeline(
            query,
            SimpleNamespace(),
            {
                "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
                "video_file_id": "video",
                "target_language": "Tiếng Việt",
                "translate_requested": "1",
                "voice_style": "giọng nữ mặc định",
                "voice_speed": "1.5",
            },
            "vi",
        )
    )
    assert result["ok"] is True
    assert captured["text"] == "xin chào thế giới"
    assert captured["voice_speed"] == "1.5"


def test_public_guard_no_admin_blocker():
    text = bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_CREATE, {}, "vi", admin=False)
    assert "Admin blocker" not in text
    assert "Tạo phụ đề tự động chưa sẵn sàng xử lý" in text


def test_admin_guard_can_show_blocker():
    text = bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_CREATE, {}, "vi", admin=True)
    assert "Admin blocker" in text


def test_no_provider_terms_public_translation_flows():
    public = "\n".join(
        [
            bot.video_dubbing_source_text({"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}, "vi"),
            bot.video_dubbing_source_text({"mode": bot.VIDEO_SUBTITLE_MODE_DUB}, "vi"),
            bot.video_dubbing_source_text({"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}, "vi"),
            bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_CREATE, {}, "vi", admin=False),
            bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_DUB, {}, "vi", admin=False),
        ]
    ).lower()
    for term in ("key4u", "shopaikey", "api", "provider", "minimax", "env", "smoke", "traceback", "admin blocker"):
        assert term not in public


def test_translation_back_source_to_video_menu():
    assert "videodub|back_type" in _callbacks(_source_markup(bot.VIDEO_SUBTITLE_MODE_CREATE))


def test_dubbing_back_voice_to_language(monkeypatch):
    uid = 991204
    bot.clear_video_dubbing_pending(uid)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    bot.set_video_dubbing_pending(
        uid,
        "voice",
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        target_language="English",
        video_file_id="video",
    )
    asyncio.run(_press("videodub|back_voice", uid))
    assert bot.get_video_dubbing_pending(uid)["step"] == "language"


def test_dubbing_back_speed_to_voice(monkeypatch):
    uid = 991205
    bot.clear_video_dubbing_pending(uid)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    bot.set_video_dubbing_pending(
        uid,
        "voice_speed",
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        target_language="English",
        voice_style="giọng nữ mặc định",
        video_file_id="video",
    )
    asyncio.run(_press("videodub|back_speed", uid))
    assert bot.get_video_dubbing_pending(uid)["step"] == "voice"


def test_dubbing_back_invoice_to_speed(monkeypatch):
    uid = 991206
    bot.clear_video_dubbing_pending(uid)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    bot.set_video_dubbing_pending(
        uid,
        "confirm",
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        target_language="English",
        voice_style="giọng nữ mặc định",
        voice_speed="1.0",
        video_file_id="video",
    )
    asyncio.run(_press("videodub|back_confirm", uid))
    assert bot.get_video_dubbing_pending(uid)["step"] == "voice_speed"


def test_subtitle_dubbing_back_continue_voice_to_subtitle_output(monkeypatch):
    uid = 991207
    bot.clear_video_dubbing_pending(uid)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    bot.set_video_dubbing_pending(
        uid,
        "voice",
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        requested_mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        target_language="English",
        video_file_id="video",
    )
    query = asyncio.run(_press("videodub|back_voice", uid))
    state = bot.get_video_dubbing_pending(uid)
    assert state["step"] == "output"
    assert state["mode"] == bot.VIDEO_SUBTITLE_MODE_TRANSLATE
    assert "Video đã sẵn sàng tạo phụ đề dịch" in query.outputs[-1]["text"]


def test_translation_provider_curl_appendix_complete():
    assert bot.SHOPAIKEY_DUBBING_TTS_ENDPOINT == "/audio/speech"
    curls = "\n".join(bot.translation_provider_curl_appendix_chunks())
    for marker in (
        "https://api.key4u.shop/v1/audio/transcriptions",
        '"model": "qwen-mt-turbo"',
        "https://api.key4u.shop/minimax/v1/t2a_v2",
        "https://api.key4u.shop/minimax/v1/t2a_async_v2",
        "t2a_async_query_v2?task_id=<TASK_ID>",
        "files/retrieve?file_id=<FILE_ID>",
        "$SHOPAIKEY_BASE_URL/models",
        "$SHOPAIKEY_BASE_URL/audio/speech",
        "https://api.shopaikey.com/tts/openai/speech",
        "$SHOPAIKEY_BASE_URL/audio/transcriptions",
        "$SHOPAIKEY_BASE_URL/chat/completions",
    ):
        assert marker in curls
    assert "Suno" not in curls
