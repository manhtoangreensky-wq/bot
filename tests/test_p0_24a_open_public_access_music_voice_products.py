import asyncio
from types import SimpleNamespace

import bot


def _words(count: int = 24) -> str:
    return " ".join(f"tu{i}" for i in range(int(count)))


class CaptureMessage:
    def __init__(self, user_id=240001):
        self.chat_id = user_id
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"kind": "text", "text": str(text or ""), **kwargs})
        return SimpleNamespace(message_id=len(self.outputs))

    async def reply_audio(self, audio=None, filename="", caption="", **kwargs):
        self.outputs.append({"kind": "audio", "audio": audio, "filename": filename, "caption": str(caption or ""), **kwargs})
        return SimpleNamespace(audio=SimpleNamespace(file_id=f"audio-{len(self.outputs)}"))


class CaptureQuery:
    def __init__(self, data="", user_id=240001):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = CaptureMessage(user_id)
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _update_with_query(data: str, user_id=240001):
    return SimpleNamespace(callback_query=CaptureQuery(data, user_id), effective_user=SimpleNamespace(id=user_id))


def _music_state(user_id=240001, mode="background", tier="music_tier_basic", vocal="female"):
    state = {
        "music_product_flow": "p0_20b1_suggestions",
        "music_product_mode": mode,
        "music_product_tier": tier,
        "song_vocal": vocal,
        "vocal_mode": vocal,
        "music_user_idea": "Nhac thuong hieu TOAN AAS vui tuoi",
    }
    prepared = bot.music_product_prepare_suggestions_result(state, idea=state["music_user_idea"], offset=0, lang="vi")
    result = bot.music_product_result_from_suggestion(prepared, prepared["music_suggestions"][0])
    bot.save_music_guided_result(user_id, result)
    return result


def _profile(profile_id: int = 240):
    return {
        "id": profile_id,
        "display_name": "Voice ban hang",
        "provider_voice_id": f"voice-{profile_id}",
        "status": "active",
        "preview_audio_ref": "demo-file-id",
        "provider": "minimax",
    }


def _open_music(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: False)
    monkeypatch.setattr(bot, "MUSIC_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "MUSIC_INSTRUMENTAL_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "MUSIC_SONG_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "SUNO_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "music_pricing_configured", lambda: True)
    monkeypatch.setattr(
        bot,
        "get_suno_music_readiness",
        lambda: {
            "ready": True,
            "public_enabled": False,
            "product_public_enabled": True,
            "missing_env": [],
            "full_result_ok": False,
            "cost_gate_ok": True,
            "status_endpoint_ready": True,
            "preferred_provider": "key4u_suno",
            "providers": {"key4u_suno": {"configured": True, "smoke": "NOT_TESTED"}},
            "reason": "ready_for_public_submit",
        },
    )


def _open_voice(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: False)
    monkeypatch.setattr(bot, "VOICE_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VOICE_TTS_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "MINIMAX_VOICE_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "voice_pricing_configured", lambda: True)
    monkeypatch.setattr(
        bot,
        "get_minimax_voice_readiness",
        lambda: {
            "ready": True,
            "public_enabled": False,
            "product_public_enabled": True,
            "missing_env": [],
            "last_tts_smoke": "NOT_TESTED",
            "reason": "ready_for_public_tts",
        },
    )
    monkeypatch.setattr(
        bot,
        "get_tts_provider_readiness",
        lambda public=False: {
            "configured": True,
            "public_ready": False,
            "reason": "ready",
            "configured_providers": ["shopaikey_minimax"],
            "public_providers": [],
            "supported_voices": ["female-shaonv", "male-qn-qingse"],
            "default_female_voice_id": "female-shaonv",
            "default_male_voice_id": "male-qn-qingse",
        },
    )


def _clean_user_text(text: str):
    lowered = str(text or "").lower()
    for forbidden in ("admin test", "provider_voice_id", "route_errors", "diagnostic", "traceback", "shopaikey", "key4u", "minimax", "provider", "api", "payload"):
        assert forbidden not in lowered


async def _fake_music_submit(*_args, **_kwargs):
    return {"ok": True, "provider_result": {"ok": True, "provider": "key4u_suno", "task_id": "music-task-24"}, "provider_task_id": "music-task-24"}


async def _no_auto_delivery(*_args, **_kwargs):
    return {"ok": False, "status": "processing"}


def test_public_user_can_confirm_instrumental_music(monkeypatch):
    user_id = 240101
    _open_music(monkeypatch)
    result = _music_state(user_id, "background")
    monkeypatch.setattr(bot, "get_user", lambda uid: (1000, None, None))
    monkeypatch.setattr(bot, "execute_engine", _fake_music_submit)
    monkeypatch.setattr(bot, "create_music_suno_async_job", lambda **kwargs: {"internal_job_id": "MUSIC-BG-24"})
    monkeypatch.setattr(bot, "music_product_auto_deliver_job", _no_auto_delivery)
    query = CaptureQuery("music_quick|showroom|music_ai_confirm", user_id)
    asyncio.run(bot.handle_music_product_confirm(query, SimpleNamespace(), user_id=user_id, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=result))
    text = query.message.outputs[-1]["text"]
    assert "TOAN AAS đang tạo nhạc nền" in text
    assert "Dịch vụ đang được kiểm tra" not in text


def test_public_user_can_confirm_lyric_song(monkeypatch):
    user_id = 240102
    _open_music(monkeypatch)
    result = _music_state(user_id, "song", tier="music_tier_premium", vocal="duet")
    monkeypatch.setattr(bot, "get_user", lambda uid: (1000, None, None))
    monkeypatch.setattr(bot, "execute_engine", _fake_music_submit)
    monkeypatch.setattr(bot, "create_music_suno_async_job", lambda **kwargs: {"internal_job_id": "MUSIC-SONG-24"})
    monkeypatch.setattr(bot, "music_product_auto_deliver_job", _no_auto_delivery)
    query = CaptureQuery("music_quick|showroom|music_ai_confirm", user_id)
    asyncio.run(bot.handle_music_product_confirm(query, SimpleNamespace(), user_id=user_id, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=result))
    text = query.message.outputs[-1]["text"]
    assert "TOAN AAS đang tạo bài hát" in text
    assert "Dịch vụ đang được kiểm tra" not in text


def test_music_confirm_no_beta_guard_for_public_user(monkeypatch):
    _open_music(monkeypatch)
    decision = bot.can_user_access_product_engine(240103, "music_song", "confirm", is_provider_call=True, is_paid_job=True, confirm_paid=True)
    assert decision["status"] == "allowed_public"
    assert decision["message"] == ""


def test_music_public_progress_panel_shown(monkeypatch):
    user_id = 240104
    _open_music(monkeypatch)
    result = _music_state(user_id, "background")
    monkeypatch.setattr(bot, "get_user", lambda uid: (1000, None, None))
    monkeypatch.setattr(bot, "execute_engine", _fake_music_submit)
    monkeypatch.setattr(bot, "create_music_suno_async_job", lambda **kwargs: {"internal_job_id": "MUSIC-PANEL-24"})
    monkeypatch.setattr(bot, "music_product_auto_deliver_job", _no_auto_delivery)
    query = CaptureQuery("music_quick|showroom|music_ai_confirm", user_id)
    asyncio.run(bot.handle_music_product_confirm(query, SimpleNamespace(), user_id=user_id, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=result))
    assert "Trạng thái:" in query.message.outputs[-1]["text"]
    assert "Tiến độ:" in query.message.outputs[-1]["text"]


def test_music_no_provider_before_final_confirm(monkeypatch):
    user_id = 240105
    _music_state(user_id, "song")
    monkeypatch.setattr(bot, "execute_engine", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider before final confirm")))
    update = _update_with_query("music_quick|showroom|music_product_select_suggestion:1", user_id)
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    assert "Xác nhận tạo bài hát" in update.callback_query.message.outputs[-1]["text"]


def test_music_no_charge_on_failure(monkeypatch):
    user_id = 240106
    _open_music(monkeypatch)
    result = _music_state(user_id, "background")
    monkeypatch.setattr(bot, "get_user", lambda uid: (1000, None, None))
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("charged on failure")))

    async def fail_engine(*_args, **_kwargs):
        return {"ok": False, "status": "FAILED", "detail": "clean fail"}

    monkeypatch.setattr(bot, "execute_engine", fail_engine)
    query = CaptureQuery("music_quick|showroom|music_ai_confirm", user_id)
    asyncio.run(bot.handle_music_product_confirm(query, SimpleNamespace(), user_id=user_id, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=result))
    assert "Hệ thống chưa trừ Xu" in query.message.outputs[-1]["text"]


def test_music_no_fake_success(monkeypatch):
    user_id = 240107
    _open_music(monkeypatch)
    result = _music_state(user_id, "background")
    monkeypatch.setattr(bot, "get_user", lambda uid: (1000, None, None))

    async def fail_engine(*_args, **_kwargs):
        return {"ok": False, "status": "NO_PROVIDER_JOB", "detail": "no task"}

    monkeypatch.setattr(bot, "execute_engine", fail_engine)
    query = CaptureQuery("music_quick|showroom|music_ai_confirm", user_id)
    asyncio.run(bot.handle_music_product_confirm(query, SimpleNamespace(), user_id=user_id, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=result))
    text = query.message.outputs[-1]["text"]
    assert "Đã gửi" not in text
    assert "Đã tạo" not in text


def test_public_user_can_create_voice_tts_audio(monkeypatch):
    user_id = 240201
    _open_voice(monkeypatch)
    bot.save_music_guided_result(user_id, {"voice_tts_settings_source": "default", "voice_tts_settings_gender": "female", "voice_text": _words(24)})
    calls = []

    async def fake_send(message, uid, text, gender, **kwargs):
        calls.append((uid, gender, text))
        await message.reply_audio(audio=b"audio", filename="voice.mp3", caption="✅ Đã tạo audio.")
        return True

    monkeypatch.setattr(bot, "send_default_free_tts_result", fake_send)
    message = CaptureMessage(user_id)
    asyncio.run(bot.voice_tts_generate_after_confirm(message, user_id, "vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    assert calls and calls[0][1] == "female"
    assert message.outputs[-1]["kind"] == "audio"


def test_public_user_can_select_female_voice(monkeypatch):
    user_id = 240202
    _open_voice(monkeypatch)
    update = _update_with_query("music_quick|showroom|voice_default_female", user_id)
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    text = update.callback_query.message.outputs[-1]["text"]
    assert "giọng nữ mặc định" in text
    assert "Dịch vụ đang được kiểm tra" not in text


def test_public_user_can_select_male_voice(monkeypatch):
    user_id = 240203
    _open_voice(monkeypatch)
    update = _update_with_query("music_quick|showroom|voice_default_male", user_id)
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    text = update.callback_query.message.outputs[-1]["text"]
    assert "giọng nam mặc định" in text
    assert "Dịch vụ đang được kiểm tra" not in text


def test_voice_confirm_no_beta_guard_for_public_user(monkeypatch):
    _open_voice(monkeypatch)
    decision = bot.can_user_access_product_engine(240204, "voice_tts", "tts", is_provider_call=True, is_paid_job=True, confirm_paid=True)
    assert decision["status"] == "allowed_public"
    assert decision["message"] == ""


def test_voice_no_provider_before_final_confirm(monkeypatch):
    user_id = 240205
    bot.save_music_guided_result(user_id, {"voice_tts_settings_source": "default", "voice_tts_settings_gender": "female", "voice_text": _words(24)})
    monkeypatch.setattr(bot, "send_default_free_tts_result", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider before confirm")))
    message = CaptureMessage(user_id)
    asyncio.run(bot.voice_tts_create_from_settings(message, user_id, "vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    assert "Xác nhận tạo audio" in message.outputs[-1]["text"]


def test_voice_no_charge_on_failure(monkeypatch):
    user_id = 240206
    profile = _profile()
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("charged on failure")))

    async def fail_tts(**_kwargs):
        return SimpleNamespace(ok=False, audio_path="", safe_public_message=bot.tts_failure_text("vi"), admin_debug_summary="failed")

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_voice_tts", fail_tts)
    message = CaptureMessage(user_id)
    ok = asyncio.run(bot.send_paid_saved_voice_tts_result(message, user_id, profile, _words(24), lang="vi"))
    assert ok is False
    assert "chưa tạo được" in message.outputs[-1]["text"].lower()


def test_voice_no_fake_success(monkeypatch):
    user_id = 240207
    profile = _profile()

    async def fail_tts(**_kwargs):
        return SimpleNamespace(ok=False, audio_path="", safe_public_message=bot.tts_failure_text("vi"), admin_debug_summary="failed")

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_voice_tts", fail_tts)
    message = CaptureMessage(user_id)
    asyncio.run(bot.send_paid_saved_voice_tts_result(message, user_id, profile, _words(24), lang="vi"))
    assert "Đã tạo audio" not in message.outputs[-1]["text"]


def test_admin_can_still_use_music(monkeypatch):
    _open_music(monkeypatch)
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: True)
    monkeypatch.setattr(bot, "MUSIC_PUBLIC_ENABLED", False)
    decision = bot.can_user_access_product_engine(1, "music_song", "confirm", is_provider_call=True, is_paid_job=True, admin_interactive_confirm=True)
    assert decision["status"] == "allowed_admin"


def test_admin_can_still_use_voice(monkeypatch):
    _open_voice(monkeypatch)
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: True)
    monkeypatch.setattr(bot, "VOICE_PUBLIC_ENABLED", False)
    decision = bot.can_user_access_product_engine(1, "voice_tts", "tts", is_provider_call=True, is_paid_job=True, admin_interactive_confirm=True)
    assert decision["status"] == "allowed_admin"


def test_public_no_admin_test_words(monkeypatch):
    user_id = 240208
    result = _music_state(user_id, "song")
    text = "\n".join([
        bot.music_product_invoice_text(result, "vi"),
        bot.voice_tts_price_summary_text(voice_name="giọng nữ mặc định", text=_words(24), lang="vi"),
        bot.product_clean_no_charge_failure_text("vi"),
    ])
    for forbidden in ("admin", "test mode", "diagnostic"):
        assert forbidden not in text.lower()


def test_public_no_provider_debug_words(monkeypatch):
    user_id = 240209
    result = _music_state(user_id, "background")
    text = "\n".join([
        bot.music_product_invoice_text(result, "vi"),
        bot.voice_tts_price_summary_text(voice_name="giọng nam mặc định", text=_words(24), lang="vi"),
        bot.product_clean_no_charge_failure_text("vi"),
    ])
    _clean_user_text(text)
