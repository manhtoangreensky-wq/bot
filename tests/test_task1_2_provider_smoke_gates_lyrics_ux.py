import asyncio
import json
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class CaptureMessage:
    def __init__(self, text="", chat_id=12012):
        self.text = text
        self.chat_id = chat_id
        self.outputs = []
        self.reply_to_message = None

    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        item = {"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup, **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(**item)


class CaptureBot:
    def __init__(self):
        self.audio_calls = []

    async def send_audio(self, **kwargs):
        self.audio_calls.append(kwargs)
        return SimpleNamespace(audio=SimpleNamespace(file_id="audio-file-id"))


class CaptureQuery:
    def __init__(self, data, user_id=12012):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = CaptureMessage(chat_id=user_id)

    async def answer(self, *args, **kwargs):
        return None


def _callback_update(data, user_id=12012):
    query = CaptureQuery(data, user_id)
    return SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=user_id)), query


def _command_update(user_id=12012):
    message = CaptureMessage(chat_id=user_id)
    return SimpleNamespace(
        message=message,
        effective_message=message,
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(id=user_id),
    ), message


def _message_update(text, user_id=12012):
    message = CaptureMessage(text=text, chat_id=user_id)
    return SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id)), message


def _settings_store(monkeypatch):
    store = {}

    def get_setting(key, default=""):
        return store.get(str(key), default)

    def set_setting(key, value, note="", updated_by=""):
        store[str(key)] = str(value or "")

    monkeypatch.setattr(bot, "get_system_setting", get_setting)
    monkeypatch.setattr(bot, "set_system_setting", set_setting)
    return store


def _reset_music(user_id):
    bot.clear_music_guided_pending(user_id)
    bot.USER_PENDING.pop(bot.music_guided_result_key(user_id), None)


def test_tool_test_minimax_tts_persists_smoke_pass(monkeypatch):
    store = _settings_store(monkeypatch)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "get_minimax_voice_readiness", lambda: {"ready": True, "saved_voice_id": ""})
    monkeypatch.setattr(bot, "key4u_minimax_tts_configured", lambda require_public=False: False)

    async def tts(_text, voice_id="", voice_style=""):
        return "PASS", b"real-audio", "ok", 200

    monkeypatch.setattr(bot, "shopaikey_minimax_tts_bytes", tts)
    update, _message = _command_update()
    context = SimpleNamespace(args=[], bot=CaptureBot())
    asyncio.run(bot.cmd_tool_test_minimax_tts(update, context))

    assert store["tool_test:minimax_tts:status"] == "PASS"
    assert store["tool_test:minimax_tts_shopaikey:status"] == "PASS"
    attempt = json.loads(store["provider_attempt:voice_tts"])
    assert attempt["called"] is True
    assert attempt["bytes"] > 0
    assert attempt["output_sent"] is True


def test_voice_provider_status_reflects_tts_smoke(monkeypatch):
    monkeypatch.setattr(bot, "key4u_status_payload", lambda: {"configured": False})
    monkeypatch.setattr(bot, "get_minimax_voice_readiness", lambda: {
        "ready": True,
        "public_enabled": True,
        "last_tts_smoke": "PASS at 2026-06-19 12:00",
        "last_clone_smoke": "NOT_TESTED",
        "missing_env": [],
    })
    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", lambda: {
        "ready": True,
        "public_enabled": False,
        "clone_smoke": "NOT_TESTED",
        "routes": ["shopaikey_minimax"],
        "missing_env": [],
    })
    monkeypatch.setattr(bot, "load_provider_attempt", lambda kind: {
        "called": True,
        "at": "2026-06-19 12:00",
        "provider": "shopaikey_minimax",
        "route": "shopaikey/default_female",
        "status": "PASS",
        "error": "-",
    } if kind == "voice_tts" else {})
    monkeypatch.setattr(bot, "tool_test_status_text", lambda name: "PASS at 2026-06-19 12:00" if "shopaikey" in name else "NOT_TESTED")
    text = bot.voice_status_text()
    assert "Last TTS called: <code>YES</code>" in text
    assert "PASS at 2026-06-19 12:00" in text
    assert "Voice clone public: <code>OFF</code>" in text


def test_voice_public_open_safe_requires_tts_smoke(monkeypatch):
    _settings_store(monkeypatch)
    monkeypatch.setattr(bot, "is_owner_user", lambda _uid: True)
    monkeypatch.setattr(bot, "get_minimax_voice_readiness", lambda: {"ready": True, "missing_env": []})
    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", lambda: {"ready": True})
    monkeypatch.setattr(bot, "voice_pricing_configured", lambda: True)
    monkeypatch.setattr(bot, "preferred_tool_test_status_text", lambda *names: "NOT_TESTED")
    update, message = _command_update()
    asyncio.run(bot.cmd_voice_public_open_safe(update, SimpleNamespace(args=[])))
    assert "Không mở Voice public" in message.outputs[-1]["text"]
    assert bot.MINIMAX_VOICE_PUBLIC_ENABLED is False


def test_voice_public_open_safe_blocks_clone_without_clone_smoke(monkeypatch):
    _settings_store(monkeypatch)
    monkeypatch.setattr(bot, "is_owner_user", lambda _uid: True)
    monkeypatch.setattr(bot, "get_minimax_voice_readiness", lambda: {"ready": True, "missing_env": []})
    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", lambda: {"ready": True})
    monkeypatch.setattr(bot, "voice_pricing_configured", lambda: True)
    monkeypatch.setattr(
        bot,
        "preferred_tool_test_status_text",
        lambda *names: "NOT_TESTED" if names == ("minimax_voice_clone",) else "PASS at 2026-06-19 12:00",
    )
    update, message = _command_update()
    asyncio.run(bot.cmd_voice_public_open_safe(update, SimpleNamespace(args=[])))
    assert "Default TTS public: ON" in message.outputs[-1]["text"]
    assert "Voice clone public: OFF" in message.outputs[-1]["text"]


def test_voice_clone_off_does_not_leave_pending_confirm(monkeypatch):
    user_id = 12013
    _reset_music(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")
    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", lambda: {
        "ready": True,
        "public_enabled": False,
        "clone_smoke": "NOT_TESTED",
    })
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    update, query = _callback_update("music_quick|showroom|voice_clone", user_id)
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    assert bot.get_music_guided_pending(user_id) is None
    assert "khóa thử nghiệm" in query.message.outputs[-1]["text"]


def test_admin_voice_clone_bypasses_public_gate_when_configured(monkeypatch):
    user_id = 12014
    _reset_music(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")
    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", lambda: {
        "ready": True,
        "public_enabled": False,
        "clone_smoke": "NOT_TESTED",
    })
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    update, query = _callback_update("music_quick|showroom|voice_clone", user_id)
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    assert bot.get_music_guided_pending(user_id)["pending_action"] == "voice_clone_intro"
    assert "khóa thử nghiệm" not in query.message.outputs[-1]["text"]


def test_admin_failed_voice_profile_keeps_retry_when_provider_configured(monkeypatch):
    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", lambda: {
        "ready": True,
        "public_enabled": False,
    })
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: str(uid) == "12014")
    labels = _labels(bot.voice_profile_actions_keyboard(
        9,
        "vi",
        bot.PRODUCT_CONTEXT_SHOWROOM,
        {"id": 9, "user_id": 12014, "status": "failed", "provider_voice_id": ""},
    ))
    assert "🔁 Tạo/nghe thử lại" in labels


def test_admin_standalone_tts_passes_key4u_admin_bypass(monkeypatch):
    calls = []

    async def key4u_tts(_text, **kwargs):
        calls.append(kwargs)
        return "PASS", b"admin-audio", "ok", 200

    monkeypatch.setattr(bot, "key4u_minimax_tts_bytes", key4u_tts)
    result = asyncio.run(bot.synthesize_standalone_tts_audio(
        "Admin TTS",
        voice_id="default_male",
        provider_hint="key4u_minimax",
        allow_admin=True,
    ))
    assert result[0] is True
    assert calls[0]["allow_admin"] is True


def test_admin_not_owner_can_close_voice_music_public_gates(monkeypatch):
    _settings_store(monkeypatch)
    monkeypatch.setattr(bot, "is_owner_user", lambda _uid: False)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    music_update, music_message = _command_update(12018)
    voice_update, voice_message = _command_update(12018)
    asyncio.run(bot.cmd_suno_public_close(music_update, SimpleNamespace(args=[])))
    asyncio.run(bot.cmd_voice_public_close(voice_update, SimpleNamespace(args=[])))
    assert "Đã đóng Suno public" in music_message.outputs[-1]["text"]
    assert "Đã đóng MiniMax Voice/clone public" in voice_message.outputs[-1]["text"]


def test_tool_test_voice_clone_persists_upload_clone_tts_results(monkeypatch):
    store = _settings_store(monkeypatch)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "KEY4U_ENABLED", False)
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "configured")
    monkeypatch.setattr(bot, "MINIMAX_VOICE_UPLOAD_ENDPOINT", "/upload")
    monkeypatch.setattr(bot, "MINIMAX_VOICE_CLONE_ENDPOINT", "/clone")
    monkeypatch.setattr(bot, "resolve_stt_test_media", lambda *_args, **_kwargs: asyncio.sleep(0, result={
        "bytes": b"sample",
        "file_name": "sample.mp3",
        "content_type": "audio/mpeg",
    }))

    async def upload(*_args, **_kwargs):
        return "PASS", "file-id", "ok", 200

    async def clone(*_args, **_kwargs):
        return "PASS", {"voice_id": "voice-real-1"}, "ok", 200

    async def tts(*_args, **_kwargs):
        return "PASS", b"clone-audio", "ok", 200

    monkeypatch.setattr(bot, "shopaikey_minimax_upload_voice_sample", upload)
    monkeypatch.setattr(bot, "shopaikey_minimax_voice_clone", clone)
    monkeypatch.setattr(bot, "shopaikey_minimax_tts_bytes", tts)
    update, _message = _command_update()
    context = SimpleNamespace(args=[], bot=CaptureBot())
    asyncio.run(bot.cmd_tool_test_minimax_voice_clone(update, context))
    assert store["tool_test:minimax_voice_clone_upload:status"] == "PASS"
    assert store["tool_test:minimax_voice_clone_tts:status"] == "PASS"
    assert store["tool_test:minimax_voice_clone:status"] == "PASS"


def test_preview_quota_hides_preview_button():
    labels = _labels(bot.voice_preview_quota_exhausted_keyboard(5, "vi"))
    assert "▶️ Nghe thử" not in labels
    assert "✅ Tạo bản đầy đủ" in labels


def test_preview_quota_full_generation_goes_to_confirm():
    callbacks = _callbacks(bot.voice_preview_quota_exhausted_keyboard(5, "vi"))
    assert "music_quick|showroom|voice_clone_full:5" in callbacks


def test_preview_quota_no_loop():
    assert bot.voice_preview_guard_message("quota") == (
        "Bạn đã hết lượt nghe thử miễn phí hôm nay. Bạn vẫn có thể tạo bản đầy đủ sau khi xác nhận."
    )


def test_tool_test_music_ai_persists_submit_fetch_download(monkeypatch):
    store = _settings_store(monkeypatch)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "music_ai_provider_summary", lambda: "key4u_suno")
    monkeypatch.setattr(bot, "get_suno_music_readiness", lambda: {"ready": True, "provider": "key4u_suno"})

    async def submit(*_args, **_kwargs):
        return {"ok": True, "status": "PASS_SUBMITTED", "provider": "key4u_suno", "task_id": "task-1", "detail": ""}

    async def poll(*_args, **_kwargs):
        return {"ok": True, "status": "SUCCESS", "output_url": "https://example.com/audio.mp3", "detail": ""}

    async def download(*_args, **_kwargs):
        return b"real-music-audio", "ok", 200

    monkeypatch.setattr(bot, "submit_music_generation_job", submit)
    monkeypatch.setattr(bot, "poll_music_generation_job", poll)
    monkeypatch.setattr(bot, "_download_audio_url_bytes", download)
    update, _message = _command_update()
    asyncio.run(bot.cmd_tool_test_music_ai(update, SimpleNamespace(args=[], bot=CaptureBot())))
    assert store["tool_test:key4u_suno:status"] == "PASS_SUBMITTED"
    assert store["tool_test:key4u_suno_job:status"] == "PASS"
    assert store["tool_test:music_ai_download:status"] == "PASS"


def test_music_provider_status_reflects_smoke_results(monkeypatch):
    monkeypatch.setattr(bot, "get_suno_music_readiness", lambda: {
        "provider": "key4u_suno",
        "endpoint": "configured",
        "public_enabled": False,
        "reason": "smoke incomplete",
        "providers": {
            "key4u_suno": {"configured": True, "smoke": "PASS_SUBMITTED", "missing_env": []},
            "shopaikey_music": {"configured": False, "smoke": "NOT_TESTED", "missing_env": ["endpoint"]},
        },
    })
    monkeypatch.setattr(bot, "load_provider_attempt", lambda _kind: {
        "called": True,
        "at": "2026-06-19 12:00",
        "provider": "key4u_suno",
        "status": "PASS_SUBMITTED",
        "task_id": "task-1",
        "fetch_status": "SUCCESS",
        "download_status": "PASS",
        "error": "-",
    })
    monkeypatch.setattr(bot, "music_ai_admin_blockers", lambda: ["public gate closed"])
    text = bot.music_status_text()
    assert "Last music called: <code>YES</code>" in text
    assert "task-1" in text
    assert "Exact blocker" in text


def test_music_public_open_safe_requires_smoke(monkeypatch):
    _settings_store(monkeypatch)
    monkeypatch.setattr(bot, "is_owner_user", lambda _uid: True)
    monkeypatch.setattr(bot, "get_suno_music_readiness", lambda: {"ready": True, "missing_env": []})
    monkeypatch.setattr(bot, "preferred_tool_test_result", lambda *names: {"status": "NOT_TESTED"})
    update, message = _command_update()
    asyncio.run(bot.cmd_music_public_open_safe(update, SimpleNamespace(args=[])))
    assert "Không mở Music public" in message.outputs[-1]["text"]
    assert bot.SUNO_PUBLIC_ENABLED is False


def test_music_guard_shows_admin_blocker_only_to_admin():
    public_labels = _labels(bot.music_ai_guarded_keyboard("vi", admin=False))
    admin_labels = _labels(bot.music_ai_guarded_keyboard("vi", admin=True))
    assert public_labels == ["✏️ Sửa mô tả", "⬅️ Quay lại", "🏠 Menu chính"]
    assert "🧪 Kiểm tra nhạc AI" in admin_labels
    assert "⚙️ Trạng thái nhạc" in admin_labels


def test_lyrics_topic_has_three_suggestions_and_more():
    labels = _labels(bot.music_song_topic_keyboard("vi"))
    assert labels[:3] == ["Câu chuyện thương hiệu", "Cảm ơn khách hàng", "Ra mắt sản phẩm"]
    assert "🔁 Gợi ý chủ đề khác" in labels
    assert "✍️ Tự nhập chủ đề" in labels


def test_lyrics_topic_text_routes_to_genre(monkeypatch):
    user_id = 12014
    _reset_music(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")
    bot.save_music_guided_result(user_id, {"song_product": "seconds", "lyrics_state": "lyrics_wait_topic"})
    bot.set_music_guided_pending(user_id, "music_song_topic", product_context=bot.PRODUCT_CONTEXT_SHOWROOM)
    update, message = _message_update("Bài hát cảm ơn khách hàng", user_id)
    assert asyncio.run(bot.handle_music_guided_pending_text(update, SimpleNamespace())) is True
    assert bot.get_music_guided_result(user_id)["lyrics_state"] == "lyrics_select_genre"
    assert "Chọn thể loại nhạc" in message.outputs[-1]["text"]


def test_lyrics_genre_routes_to_mood(monkeypatch):
    user_id = 12015
    _reset_music(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")
    bot.save_music_guided_result(user_id, {"song_product": "seconds", "song_topic": "Thương hiệu"})
    update, query = _callback_update("music_quick|showroom|song_genre_pop", user_id)
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    assert bot.get_music_guided_result(user_id)["lyrics_state"] == "lyrics_select_mood"
    assert "Chọn cảm xúc" in query.message.outputs[-1]["text"]


def test_lyrics_mood_routes_to_vocal(monkeypatch):
    user_id = 12016
    _reset_music(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")
    bot.save_music_guided_result(user_id, {"song_product": "seconds", "song_topic": "Thương hiệu", "song_genre": "pop"})
    update, query = _callback_update("music_quick|showroom|song_mood_cheerful", user_id)
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    assert bot.get_music_guided_result(user_id)["lyrics_state"] == "lyrics_select_vocal"
    assert "Chọn giọng hát" in query.message.outputs[-1]["text"]


def test_lyrics_vocal_routes_to_three_options(monkeypatch):
    user_id = 12017
    _reset_music(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")
    bot.save_music_guided_result(user_id, {
        "song_product": "seconds",
        "guided_duration_seconds": 30,
        "song_topic": "Cảm ơn khách hàng",
        "song_genre": "pop",
        "song_mood": "cheerful",
    })
    update, query = _callback_update("music_quick|showroom|song_vocal_male", user_id)
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    result = bot.get_music_guided_result(user_id)
    assert result["lyrics_state"] == "lyrics_options"
    assert len(result["suggestions"]) == 3
    assert "Chọn hướng bài hát" in query.message.outputs[-1]["text"]


def test_lyrics_options_before_invoice():
    labels = _labels(bot.music_prompt_result_keyboard("vi", result={"song_product": "seconds"}))
    assert "1️⃣ Chọn PA1" in labels
    assert "▶️ Nghe thử" not in labels
    assert "✅ Tạo bài hát" not in labels


def test_lyrics_invoice_only_after_option_selected(monkeypatch):
    user_id = 12018
    _reset_music(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")
    monkeypatch.setattr(bot, "get_suno_music_readiness", lambda: {"public_enabled": False})
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    suggestions = bot.music_prompt_suggestions("Bài hát thương hiệu", 0, "vi", "lyrics")
    bot.save_music_guided_result(user_id, {
        "song_product": "seconds",
        "music_ai_kind": "lyrics",
        "guided_duration_seconds": 30,
        "suggestions": suggestions,
        "lyrics_state": "lyrics_options",
    })
    update, query = _callback_update("music_quick|showroom|prompt_choose_1", user_id)
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    assert bot.get_music_guided_result(user_id)["lyrics_state"] == "lyrics_invoice_preview"
    labels = _labels(query.message.outputs[-1]["reply_markup"])
    assert "▶️ Nghe thử" not in labels
    assert "✅ Tạo bài hát" not in labels


def test_lyrics_back_stack_exact():
    assert "music_quick|showroom|song_back_topic" in _callbacks(bot.music_song_options_keyboard("genre", "vi"))
    assert "music_quick|showroom|song_back_genre" in _callbacks(bot.music_song_options_keyboard("mood", "vi"))
    assert "music_quick|showroom|song_back_mood" in _callbacks(bot.music_song_options_keyboard("vocal", "vi"))
    assert "music_quick|showroom|song_back_vocal" in _callbacks(bot.music_prompt_result_keyboard("vi", result={"song_product": "seconds"}))
    assert "music_quick|showroom|music_ai_back_suggestions" in _callbacks(bot.music_ai_preview_keyboard("vi", result={"song_product": "seconds"}))


def test_music_gate_off_hides_preview_create_for_public():
    labels = _labels(bot.music_ai_guarded_keyboard("vi", admin=False))
    assert "▶️ Nghe thử" not in labels
    assert "✅ Tạo bài hát" not in labels
    assert "✅ Tạo nhạc" not in labels


def test_music_gate_off_admin_shows_smoke_buttons():
    labels = _labels(bot.music_ai_guarded_keyboard("vi", admin=True))
    assert "🧪 Kiểm tra nhạc AI" in labels
    assert "⚙️ Trạng thái nhạc" in labels


def test_admin_music_gate_shows_output_buttons_when_provider_configured(monkeypatch):
    monkeypatch.setattr(bot, "get_suno_music_readiness", lambda: {
        "ready": True,
        "public_enabled": False,
    })
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    labels = _labels(bot.music_ai_gate_keyboard(
        12012,
        "vi",
        result={"song_product": "seconds"},
    ))
    assert "▶️ Nghe thử" in labels
    assert "✅ Tạo bài hát" in labels


def test_admin_music_preview_bypasses_public_gate(monkeypatch):
    user_id = 12015
    _reset_music(user_id)
    bot.save_music_guided_result(user_id, {
        "selected_prompt": "Original admin music test",
        "guided_duration_seconds": 30,
        "music_ai_kind": "guided",
    })
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "get_suno_music_readiness", lambda: {
        "ready": True,
        "public_enabled": False,
    })
    calls = []

    async def submit(_result, preview=False, admin_smoke=False, updated_by=""):
        calls.append({"preview": preview, "admin_smoke": admin_smoke, "updated_by": updated_by})
        return {"ok": True, "status": "PASS_SUBMITTED", "provider": "test", "task_id": "admin-preview"}

    monkeypatch.setattr(bot, "submit_music_generation_job", submit)
    update, _query = _callback_update("music_quick|showroom|music_ai_preview", user_id)
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    assert calls == [{"preview": True, "admin_smoke": True, "updated_by": user_id}]
    assert bot.get_music_guided_result(user_id)["music_preview_task_id"] == "admin-preview"


def test_admin_music_full_create_is_zero_xu_and_bypasses_public_gate(monkeypatch):
    user_id = 12016
    _reset_music(user_id)
    bot.save_music_guided_result(user_id, {
        "selected_prompt": "Original admin full music test",
        "guided_duration_seconds": 30,
        "music_ai_kind": "guided",
    })
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "get_user", lambda _uid: (0, None, None))
    monkeypatch.setattr(bot, "get_suno_music_readiness", lambda: {
        "ready": True,
        "public_enabled": False,
    })
    calls = []

    async def submit(_result, preview=False, admin_smoke=False, updated_by=""):
        calls.append({"preview": preview, "admin_smoke": admin_smoke, "updated_by": updated_by})
        return {"ok": True, "status": "PASS_SUBMITTED", "provider": "test", "task_id": "admin-full"}

    monkeypatch.setattr(bot, "submit_music_generation_job", submit)
    update, query = _callback_update("music_quick|showroom|music_ai_confirm", user_id)
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    assert calls == [{"preview": False, "admin_smoke": True, "updated_by": user_id}]
    result = bot.get_music_guided_result(user_id)
    assert result["music_charged_xu"] == 0
    assert "Đã trừ: 0 Xu" in query.message.outputs[-1]["text"]


def test_admin_music_test_button_runs_real_smoke_command(monkeypatch):
    user_id = 12017
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    called = []

    async def smoke(update, context):
        called.append((update.effective_user.id, update.effective_chat.id, context))
        return await update.message.reply_text("smoke-called")

    monkeypatch.setattr(bot, "cmd_tool_test_music_ai", smoke)
    context = SimpleNamespace(bot=CaptureBot())
    update, query = _callback_update("music_quick|showroom|music_admin_test", user_id)
    asyncio.run(bot.handle_music_quick_callback(update, context))
    assert called == [(user_id, user_id, context)]
    assert query.message.outputs[-1]["text"] == "smoke-called"


def test_music_gate_on_preview_creates_job(monkeypatch):
    monkeypatch.setattr(bot, "get_suno_music_readiness", lambda: {
        "public_enabled": True,
        "preferred_provider": "key4u_suno",
        "providers": {"key4u_suno": {"configured": True, "smoke": "PASS"}},
    })

    class Provider:
        async def suno_create(self, **_kwargs):
            return {"ok": True, "status": "PASS_SUBMITTED", "task_id": "preview-task"}

    monkeypatch.setattr(bot, "key4u_provider_instance", lambda: Provider())
    monkeypatch.setattr(bot, "record_music_provider_attempt", lambda **kwargs: kwargs)
    result = asyncio.run(bot.submit_music_generation_job(
        {"selected_prompt": "original", "guided_duration_seconds": 30},
        preview=True,
    ))
    assert result["ok"] is True
    assert result["task_id"] == "preview-task"


def test_music_gate_on_full_create_creates_job(monkeypatch):
    monkeypatch.setattr(bot, "get_suno_music_readiness", lambda: {
        "public_enabled": True,
        "preferred_provider": "key4u_suno",
        "providers": {"key4u_suno": {"configured": True, "smoke": "PASS"}},
    })

    class Provider:
        async def suno_create(self, **_kwargs):
            return {"ok": True, "status": "PASS_SUBMITTED", "task_id": "full-task"}

    monkeypatch.setattr(bot, "key4u_provider_instance", lambda: Provider())
    monkeypatch.setattr(bot, "record_music_provider_attempt", lambda **kwargs: kwargs)
    result = asyncio.run(bot.submit_music_generation_job(
        {"selected_prompt": "original", "guided_duration_seconds": 60},
        preview=False,
    ))
    assert result["ok"] is True
    assert result["task_id"] == "full-task"


def test_music_buttons_no_loop_when_guarded():
    callbacks = _callbacks(bot.music_ai_guarded_keyboard("vi", admin=False))
    assert not any(value.endswith("music_ai_preview") for value in callbacks)
    assert not any(value.endswith("music_ai_confirm") for value in callbacks)


def test_admin_voice_status_shows_last_called(monkeypatch):
    monkeypatch.setattr(bot, "load_provider_attempt", lambda kind: {
        "called": True,
        "at": "2026-06-19 12:00",
        "provider": "shopaikey_minimax",
        "status": "PASS",
        "error": "-",
    } if kind == "voice_tts" else {})
    assert "called: <code>YES</code>" in bot.admin_attempt_summary("Last TTS", bot.load_provider_attempt("voice_tts"))


def test_admin_music_status_shows_last_called(monkeypatch):
    attempt = {"called": True, "at": "2026-06-19 12:00", "provider": "key4u_suno", "status": "PASS_SUBMITTED", "error": "-"}
    assert "called: <code>YES</code>" in bot.admin_attempt_summary("Last music", attempt)


def test_provider_attempt_saved_on_failure(monkeypatch):
    store = _settings_store(monkeypatch)
    bot.record_music_provider_attempt(provider="key4u_suno", submit_status="FAIL_TIMEOUT", error="secret token timeout", updated_by=1)
    attempt = json.loads(store["provider_attempt:music"])
    assert attempt["called"] is True
    assert attempt["status"] == "FAIL_TIMEOUT"
    assert attempt["error"]
