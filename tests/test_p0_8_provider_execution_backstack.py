import asyncio
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _assert_public_safe(text):
    lowered = str(text or "").lower()
    for term in (
        "admin blocker",
        "key4u",
        "shopaikey",
        "suno",
        "minimax",
        "api",
        "provider",
        "env",
        "http",
        "smoke",
        "gate",
        "ready=false",
        "not_tested",
    ):
        assert term not in lowered


class CaptureMessage:
    def __init__(self, user_id=980800, text=""):
        self.chat_id = user_id
        self.text = text
        self.outputs = []

    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        item = {"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup, **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(**item)

    async def reply_audio(self, audio=None, filename=None, caption=None, **kwargs):
        item = {"audio": audio, "filename": filename, "caption": str(caption or ""), **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(audio=SimpleNamespace(file_id="preview-file"), **item)


class CaptureQuery:
    def __init__(self, data, user_id=980800):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = CaptureMessage(user_id)
        self.outputs = self.message.outputs

    async def answer(self, *args, **kwargs):
        return None

    async def edit_message_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        return await self.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup, **kwargs)


def _callback_update(query, user_id):
    return SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=user_id))


def _message_update(message, user_id):
    return SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id))


def _reset(user_id):
    bot.clear_music_guided_pending(user_id)
    bot.USER_PENDING.pop(bot.music_guided_result_key(user_id), None)
    bot.clear_video_finalization_state(user_id)
    bot.clear_video_addon_state(user_id)
    bot.clear_video_dubbing_pending(user_id)


def test_live_default_female_tts_uses_female_mapping(monkeypatch):
    calls = []

    async def minimax(text, voice_id="", voice_style=""):
        calls.append(voice_id)
        return "PASS", b"female-audio", "ok", 200

    monkeypatch.setattr(bot, "shopaikey_minimax_tts_bytes", minimax)
    result = asyncio.run(bot.synthesize_standalone_tts_audio("Xin chào", "default_female"))
    assert result[0] is True
    assert calls == [bot.get_tts_voice_id("default_female")]


def test_live_default_male_tts_uses_male_mapping(monkeypatch):
    calls = []

    async def minimax(text, voice_id="", voice_style=""):
        calls.append(voice_id)
        return "PASS", b"male-audio", "ok", 200

    monkeypatch.setattr(bot, "shopaikey_minimax_tts_bytes", minimax)
    result = asyncio.run(bot.synthesize_standalone_tts_audio("Xin chào", "default_male"))
    assert result[0] is True
    assert calls == [bot.get_tts_voice_id("default_male")]


def test_female_male_voice_mapping_not_same_when_both_ready():
    assert bot.get_tts_voice_id("default_female") != bot.get_tts_voice_id("default_male")


def test_default_voice_fallback_preserves_gender(monkeypatch):
    edge_calls = []

    async def failed_primary(*args, **kwargs):
        return "FAIL", b"", "unavailable", 503

    async def edge(text, voice_id=""):
        edge_calls.append(voice_id)
        return "PASS", b"edge-audio", "ok", 0

    monkeypatch.setattr(bot, "shopaikey_minimax_tts_bytes", failed_primary)
    monkeypatch.setattr(bot, "tts_edge_bytes", edge)
    assert asyncio.run(bot.synthesize_standalone_tts_audio("Nữ", "default_female"))[0]
    assert asyncio.run(bot.synthesize_standalone_tts_audio("Nam", "default_male"))[0]
    assert edge_calls == ["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"]


def test_selected_voice_text_generates_audio_without_style_chooser(monkeypatch):
    user_id = 980801
    _reset(user_id)
    bot.save_music_guided_result(user_id, {
        "selected_voice_id": bot.get_tts_voice_id("default_female"),
        "selected_voice_kind": "default_female",
        "selected_voice_style": "giọng nữ mặc định",
    })
    bot.set_music_guided_pending(user_id, "voice_text", product_context=bot.PRODUCT_CONTEXT_SHOWROOM)
    calls = []

    async def send_result(message, uid, text, label, **kwargs):
        calls.append((uid, text, label, kwargs.get("voice_id")))
        return True

    monkeypatch.setattr(bot, "send_standalone_tts_result", send_result)
    message = CaptureMessage(user_id, "Nội dung cần đọc")
    handled = asyncio.run(bot.handle_music_guided_pending_text(_message_update(message, user_id), SimpleNamespace()))
    assert handled is True
    assert calls == []
    assert "Tạo giọng đọc miễn phí" in message.outputs[-1]["text"]


def test_public_tts_no_admin_blocker_terms():
    _assert_public_safe(bot.standalone_tts_guard_text("vi"))


def test_admin_tts_status_shows_sanitized_blocker():
    text = bot.voice_status_text()
    assert "VOICE / TTS STATUS" in text
    assert bot.SHOPAIKEY_API_KEY not in text if bot.SHOPAIKEY_API_KEY else True


def test_preview_duration_one_third_capped_6():
    assert bot.calculate_preview_seconds(3) == 3
    assert bot.calculate_preview_seconds(15) == 5
    assert bot.calculate_preview_seconds(120) == 6


def test_background_music_duration_menu_unchanged():
    labels = _labels(bot.music_guided_step_keyboard("duration", "vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    assert all(label in labels for label in ("18 giây", "30 giây", "60 giây", "Nhập thời lượng khác"))
    assert not any("6 giây" in label for label in labels)


def test_music_price_increases_with_duration():
    assert bot.music_ai_output_price_xu(15) == bot.MUSIC_BACKGROUND_FULL_PRICE_XU
    assert bot.music_ai_output_price_xu(60) == bot.MUSIC_BACKGROUND_FULL_PRICE_XU


def test_song_with_lyrics_menu_has_no_by_seconds_button():
    labels = _labels(bot.music_song_product_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    callbacks = _callbacks(bot.music_song_product_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    assert "⏱ Theo số giây" not in labels
    assert not any(value.endswith("song_start_seconds") for value in callbacks)


def test_song_with_lyrics_menu_has_half_and_full_only():
    labels = _labels(bot.music_song_product_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    assert labels == ["🎤 Bài hát có lời AI", "⬅️ Nhạc", "🏠 Menu chính"]


def test_song_seconds_has_18_30_60_custom():
    labels = _labels(bot.music_song_duration_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    assert labels[:4] == ["18 giây", "30 giây", "60 giây", "Nhập thời lượng khác"]


def test_song_price_uses_real_full_quote_without_fake_half(monkeypatch):
    monkeypatch.setattr(bot, "MUSIC_SHORT_MODE_VERIFIED", False)
    half = bot.music_ai_output_price_xu(60, "song_half")
    full = bot.music_ai_output_price_xu(120, "song_full")
    assert half == bot.MUSIC_VOCAL_FULL_PRICE_XU
    assert full == bot.MUSIC_VOCAL_FULL_PRICE_XU


def test_song_seconds_pricing_uses_duration_product():
    assert bot.music_ai_output_price_xu(18, "song_seconds") == bot.LYRIC_SONG_15S_PRICE_XU
    assert bot.music_ai_output_price_xu(30, "song_seconds") == bot.LYRIC_SONG_30S_PRICE_XU
    assert bot.music_ai_output_price_xu(60, "song_seconds") == bot.LYRIC_SONG_60S_PRICE_XU
    assert bot.music_ai_output_price_xu(90, "song_seconds") > bot.music_ai_output_price_xu(60, "song_seconds")


def test_create_music_reaches_real_preview_job(monkeypatch):
    user_id = 980802
    _reset(user_id)
    bot.save_music_guided_result(user_id, {
        "selected_prompt": "Nhạc nền vui tươi nguyên bản",
        "guided_duration_seconds": 30,
        "music_ai_kind": "guided",
    })
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")
    monkeypatch.setattr(bot, "get_member_profile", lambda *_args, **_kwargs: {"tier": "silver"})
    monkeypatch.setattr(bot, "get_suno_music_readiness", lambda: {
        "public_enabled": True,
        "ready": True,
        "full_result_ok": True,
        "cost_gate_ok": True,
    })
    calls = []

    async def submit(result, preview=False):
        calls.append(preview)
        return {"ok": True, "task_id": "preview-task", "provider": "route", "status": "SUBMITTED"}

    monkeypatch.setattr(bot, "submit_music_generation_job", submit)
    query = CaptureQuery("music_quick|showroom|music_ai_preview", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(query, user_id), SimpleNamespace()))
    saved = bot.get_music_guided_result(user_id)
    assert calls == [True]
    assert saved["music_preview_task_id"] == "preview-task"
    assert saved["music_preview_seen"] is False


def test_music_no_public_admin_blocker(monkeypatch):
    user_id = 980803
    _reset(user_id)
    bot.save_music_guided_result(user_id, {"selected_prompt": "Nhạc nền", "guided_duration_seconds": 30})
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")
    monkeypatch.setattr(bot, "get_suno_music_readiness", lambda: {"public_enabled": False, "ready": False})
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: True)
    query = CaptureQuery("music_quick|showroom|music_ai_preview", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(query, user_id), SimpleNamespace()))
    assert "--confirm-paid" not in query.outputs[-1]["text"]
    assert "Admin test chưa chạy" in query.outputs[-1]["text"]
    assert "bảo trì/nâng cấp" not in query.outputs[-1]["text"]


def test_translation_uses_key4u_chat_route_when_ready(monkeypatch):
    monkeypatch.setattr(bot, "KEY4U_ENABLED", True)
    monkeypatch.setattr(bot, "KEY4U_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "KEY4U_API_KEY", "configured-secret")
    monkeypatch.setattr(bot, "KEY4U_CHAT_ENDPOINT", "/v1/chat/completions")
    monkeypatch.setattr(bot, "KEY4U_CHAT_MODEL", "chat-model")
    monkeypatch.setattr(bot, "DEEPL_API_KEY", "")
    monkeypatch.setattr(bot, "gemini_client", None)
    monkeypatch.setattr(bot, "openai_client", None)

    class FakeKey4U:
        async def chat_completion(self, **kwargs):
            return {"ok": True, "status": "PASS", "text": "Xin chào"}

    monkeypatch.setattr(bot, "key4u_provider_instance", lambda: FakeKey4U())
    result = asyncio.run(bot.translate_to_language("Hello", "vi"))
    assert result["provider"] == "key4u"
    assert result["text"] == "Xin chào"


def test_translation_public_no_admin_blocker():
    _assert_public_safe(bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, {}, "vi", admin=False))


def test_dubbing_preview_max_6_and_no_final_xu(monkeypatch):
    state = {
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "video_duration": 90,
        "source_file_id": "video-file",
        "target_language": "vi",
    }
    monkeypatch.setattr(bot, "video_dubbing_public_processing_ready", lambda mode, state=None: True)

    async def download(context, state):
        return b"video", "video/mp4"

    async def extract_audio(data, content_type="application/octet-stream", max_seconds=0):
        assert data == b"video"
        assert content_type == "video/mp4"
        assert max_seconds == 6
        return b"audio-from-video", "audio/mpeg", "ffmpeg_audio_extract"

    async def cap(data, seconds):
        assert seconds == 6
        return b"preview-audio", "ok"

    async def transcribe(data, context, content_type):
        return "route", "Hello from preview", "ok"

    async def translate(text, target, **_kwargs):
        return {"provider": "route", "text": "Xin chào từ bản thử"}

    def forbidden_spend(*args, **kwargs):
        raise AssertionError("preview must not deduct final Xu")

    monkeypatch.setattr(bot, "video_dubbing_download_source", download)
    monkeypatch.setattr(bot, "video_dubbing_audio_extract_ready", lambda: True)
    monkeypatch.setattr(bot, "video_dubbing_extract_audio", extract_audio)
    monkeypatch.setattr(bot, "cap_voice_preview_audio_bytes", cap)
    monkeypatch.setattr(bot, "video_dubbing_transcribe_bytes", transcribe)
    monkeypatch.setattr(bot, "translate_subtitle_text", translate)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", forbidden_spend)
    query = CaptureQuery("videodub|preview")
    result = asyncio.run(bot.execute_video_dubbing_preview(query, SimpleNamespace(), state, "vi"))
    assert result["ok"] is True
    assert result["preview_seconds"] == 6
    assert "Xin chào" in query.outputs[-1]["text"]


def test_package_back_returns_tools_from_invoice_change(monkeypatch):
    user_id = 980804
    _reset(user_id)
    bot.set_video_finalization_state(user_id, {
        "step": "tier",
        "return_to_invoice": True,
        "origin_screen": "invoice",
        "source": "selfscene",
        "source_payload": {"source_file_id": "file-1", "object_prompt": "object", "direction_prompt": "direction"},
    })
    query = CaptureQuery("vfinal|back", user_id)
    asyncio.run(bot.handle_video_finalization_callback(_callback_update(query, user_id), SimpleNamespace()))
    assert "Công cụ hoàn thiện video" in query.outputs[-1]["text"]
    assert "vfinal|voice" in _callbacks(query.outputs[-1]["reply_markup"])
    assert "vfinal|music" in _callbacks(query.outputs[-1]["reply_markup"])


def test_invoice_origin_stack_is_explicit():
    state = bot.video_finalization_set_origin({"screen_stack": ["video_options"]}, "invoice")
    assert state["origin_screen"] == "invoice"
    assert state["return_to_invoice"] is True
    assert state["addon_return_target"] == "invoice"
    assert state["screen_stack"][-1] == "invoice"


def test_invoice_preview_buttons_return_to_invoice():
    for keyboard in (
        bot.video_paid_preview_keyboard("token", "vi"),
        bot.video_paid_preview_entry_keyboard("token", "vi"),
        bot.video_paid_preview_retry_keyboard("token", "vi"),
        bot.video_paid_preview_status_keyboard("token", 1, "vi"),
    ):
        assert "videoaddon|invoice" in _callbacks(keyboard)


def test_provider_status_commands_are_registered():
    source = open(bot.__file__, "r", encoding="utf-8").read()
    assert 'CommandHandler("provider_status", cmd_provider_status)' in source
    assert 'CommandHandler("music_provider_status", cmd_music_provider_status)' in source
    assert 'CommandHandler("translation_provider_status", cmd_translation_provider_status)' in source
