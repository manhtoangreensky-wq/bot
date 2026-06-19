import asyncio
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _joined(markup):
    return "\n".join(
        [button.text for row in markup.inline_keyboard for button in row]
        + [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]
    )


class CaptureMessage:
    def __init__(self, text="", user_id=960600, media=None):
        self.text = text
        self.chat_id = user_id
        self.message_id = 66
        self.outputs = []
        self.voice = media if getattr(media, "kind", "") == "voice" else None
        self.audio = media if getattr(media, "kind", "") == "audio" else None
        self.video = media if getattr(media, "kind", "") == "video" else None
        self.document = media if getattr(media, "kind", "") == "document" else None

    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        item = {"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup, **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(text=text, reply_markup=reply_markup)

    async def reply_audio(self, audio=None, filename=None, caption=None, **kwargs):
        item = {"audio": audio, "filename": filename, "caption": str(caption or ""), **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(audio=audio, caption=caption)


class CaptureQuery:
    def __init__(self, data, user_id=960600):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = CaptureMessage(user_id=user_id)
        self.outputs = self.message.outputs

    async def answer(self, *args, **kwargs):
        return None

    async def edit_message_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        item = {"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup, **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(text=text, reply_markup=reply_markup)


def _callback_update(query, user_id):
    return SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=user_id))


def _message_update(message, user_id):
    return SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id))


def _reset_user(user_id):
    bot.clear_music_guided_pending(user_id)
    bot.USER_PENDING.pop(bot.music_guided_result_key(user_id), None)
    bot.clear_product_context(user_id)
    bot.clear_video_finalization_state(user_id)
    bot.clear_video_addon_state(user_id)
    bot.clear_public_video_package_context(user_id)


def _seed_video_state(user_id):
    bot.set_video_finalization_state(user_id, {
        "source": "selfscene",
        "source_file_id": "source-file-id",
        "source_video_file_id": "source-video-file-id",
        "selected_prompt": "Video quảng cáo mỹ phẩm.",
        "selected_video_tier": "basic",
        "duration_seconds": 20,
        "object_prompt": "lọ serum",
        "direction_prompt": "quay cận cảnh",
        "source_payload": {"prompt": "Video quảng cáo mỹ phẩm.", "video_tier": "basic", "duration_seconds": 20},
        "video_finalization": {},
    })


def test_paid_voice_profile_first_free_then_50_xu(monkeypatch):
    monkeypatch.setattr(bot, "active_voice_profile_count", lambda user_id, exclude_profile_id=0: 0)
    assert bot.voice_profile_storage_price_xu(123, bot.PRODUCT_CONTEXT_SHOWROOM, 10) == 0

    monkeypatch.setattr(bot, "active_voice_profile_count", lambda user_id, exclude_profile_id=0: 1)
    assert bot.voice_profile_storage_price_xu(123, bot.PRODUCT_CONTEXT_SHOWROOM, 11) == bot.VOICE_PROFILE_PRICE_XU == 50


def test_text_to_voice_generates_audio_with_selected_default_voice(monkeypatch):
    user_id = 960601
    _reset_user(user_id)
    calls = {}
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")

    async def fake_tts(text, voice_id="", voice_style="", speed="normal"):
        calls.update(text=text, voice_id=voice_id, voice_style=voice_style, speed=speed)
        return True, b"mp3-bytes", "ok"

    monkeypatch.setattr(bot, "synthesize_standalone_tts_audio", fake_tts)

    query = CaptureQuery("music_quick|showroom|voice_default_female", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(query, user_id), SimpleNamespace()))
    assert bot.get_music_guided_pending(user_id)["pending_action"] == "voice_text"

    message = CaptureMessage("Xin chào khách hàng TOAN AAS.", user_id)
    handled = asyncio.run(bot.handle_music_guided_pending_text(_message_update(message, user_id), SimpleNamespace()))

    assert handled is True
    assert calls["text"] == "Xin chào khách hàng TOAN AAS."
    assert calls["voice_id"] == bot.default_tts_voice_id("female")
    assert message.outputs[-1]["filename"] == "toan_aas_voice.mp3"
    assert "giọng nữ mặc định" in message.outputs[-1]["caption"]


def test_text_to_voice_flow_does_not_reask_voice_after_default_selected(monkeypatch):
    user_id = 960602
    _reset_user(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")
    monkeypatch.setattr(bot, "synthesize_standalone_tts_audio", lambda *args, **kwargs: asyncio.sleep(0, result=(True, b"ok", "ok")))

    query = CaptureQuery("music_quick|showroom|voice_default_male", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(query, user_id), SimpleNamespace()))
    message = CaptureMessage("Đọc ngay bằng giọng đã chọn.", user_id)
    asyncio.run(bot.handle_music_guided_pending_text(_message_update(message, user_id), SimpleNamespace()))

    assert "Chọn kiểu giọng" not in "\n".join(str(item.get("text") or item.get("caption") or "") for item in message.outputs)
    assert message.outputs[-1]["filename"] == "toan_aas_voice.mp3"


def test_speech_to_text_upload_transcribes_public_audio(monkeypatch):
    user_id = 960603
    _reset_user(user_id)
    media = SimpleNamespace(kind="voice", file_id="voice-file", mime_type="audio/ogg", file_name="", file_size=100)
    message = CaptureMessage(user_id=user_id, media=media)
    bot.set_music_guided_pending(user_id, "speech_to_text_upload", product_context=bot.PRODUCT_CONTEXT_SHOWROOM)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")

    async def fake_stt(update, context):
        return True, "Xin chào từ file audio.", "ok"

    monkeypatch.setattr(bot, "transcribe_standalone_audio_message", fake_stt)
    handled = asyncio.run(bot.handle_music_guided_pending_media(_message_update(message, user_id), SimpleNamespace()))

    assert handled is True
    assert "Bản chuyển văn bản" in message.outputs[-1]["text"]
    assert "Xin chào từ file audio." in message.outputs[-1]["text"]


def test_guided_music_creation_reaches_three_prompt_choices(monkeypatch):
    user_id = 960604
    _reset_user(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")

    start = CaptureQuery("music_quick|showroom|ai_music", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(start, user_id), SimpleNamespace()))
    assert "Tạo nhạc nền" in start.outputs[-1]["text"]
    assert "Video bán hàng" in _joined(start.outputs[-1]["reply_markup"])

    for data in [
        "music_quick|showroom|music_ai_purpose_sales_video",
        "music_quick|showroom|music_ai_style_cinematic",
        "music_quick|showroom|music_ai_mood_cheerful",
    ]:
        query = CaptureQuery(data, user_id)
        asyncio.run(bot.handle_music_quick_callback(_callback_update(query, user_id), SimpleNamespace()))

    duration = CaptureQuery("music_quick|showroom|music_ai_duration_30s", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(duration, user_id), SimpleNamespace()))
    assert "3 prompt nhạc gợi ý" in duration.outputs[-1]["text"]
    assert "Chọn gợi ý 1" in _joined(duration.outputs[-1]["reply_markup"])


def test_video_voice_choice_asks_script_and_saves_to_draft(monkeypatch):
    user_id = 960605
    _reset_user(user_id)
    monkeypatch.setattr(bot, "get_user_language", lambda uid: "vi")
    _seed_video_state(user_id)

    query = CaptureQuery("vfinal|voice_default|female", user_id)
    asyncio.run(bot.handle_video_finalization_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    state = bot.get_video_finalization_state(user_id)

    assert state["step"] == "await_voice_script"
    assert state["video_finalization"]["voice_choice"] == "default_female"
    assert "20 giây" in query.outputs[-1]["text"]

    message = CaptureMessage("Serum này giúp da sáng hơn mỗi ngày.", user_id)
    handled = asyncio.run(bot.handle_video_finalization_pending_text(_message_update(message, user_id), SimpleNamespace()))
    finalization = bot.get_video_finalization_state(user_id)["video_finalization"]

    assert handled is True
    assert finalization["voice_text"] == "Serum này giúp da sáng hơn mỗi ngày."
    assert finalization["voice_script"] == "Serum này giúp da sáng hơn mỗi ngày."
    assert bot.get_video_finalization_state(user_id)["source_file_id"] == "source-file-id"


def test_translation_public_flow_has_upload_language_and_no_provider_words():
    text = "\n".join([
        bot.translation_menu_text("vi"),
        bot.video_dubbing_upload_text({"video_processing_mode": "translate_subtitle"}, "vi"),
        bot.video_dubbing_language_text({"mode": "translate_subtitle"}, "vi"),
        _joined(bot.translation_menu_keyboard("vi")),
    ]).lower()
    for term in ["provider", "api", "suno", "minimax", "key4u", "shopaikey", "env", "http", "raw error", "bot chưa gọi api"]:
        assert term not in text
    assert "gửi hoặc reply video/audio" in text
    assert "ngôn ngữ" in text
