import asyncio
from types import SimpleNamespace

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
    def __init__(self, user_id=970700, text=""):
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
        return SimpleNamespace(**item)


class CaptureQuery:
    def __init__(self, data, user_id=970700):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = CaptureMessage(user_id)
        self.outputs = self.message.outputs

    async def answer(self, *args, **kwargs):
        return None


def _callback_update(query, user_id):
    return SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=user_id))


def _message_update(message, user_id):
    return SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id))


def _reset_user(user_id):
    bot.clear_music_guided_pending(user_id)
    bot.USER_PENDING.pop(bot.music_guided_result_key(user_id), None)
    bot.clear_product_context(user_id)
    bot.clear_video_addon_state(user_id)
    bot.clear_video_finalization_state(user_id)


def _assert_public_copy_safe(text):
    lowered = str(text or "").lower()
    for term in ["provider", "api", "suno", "minimax", "key4u", "shopaikey", "env", "http", "raw error"]:
        assert term not in lowered


def test_default_female_and_male_voice_ids_are_distinct():
    mapping = bot.default_tts_voice_map()
    assert mapping["distinct"] is True
    assert mapping["female"]
    assert mapping["male"]
    assert mapping["female"] != mapping["male"]


def test_selected_default_voice_uses_exact_voice_without_generic_fallback(monkeypatch):
    calls = []

    async def exact_tts(text, voice_id="", voice_style=""):
        calls.append((text, voice_id, voice_style))
        return "PASS", b"voice-bytes", "ok", 200

    async def forbidden_fallback(*args, **kwargs):
        raise AssertionError("selected voice must not fall back to a generic voice")

    monkeypatch.setattr(bot, "shopaikey_minimax_tts_bytes", exact_tts)
    monkeypatch.setattr(bot, "shopaikey_tts_bytes", forbidden_fallback)
    monkeypatch.setattr(bot, "video_dubbing_tts_bytes", forbidden_fallback)

    female = asyncio.run(bot.synthesize_standalone_tts_audio("Xin chào", voice_id="default_female"))
    male = asyncio.run(bot.synthesize_standalone_tts_audio("Xin chào", voice_id="default_male"))

    assert female[0] is True and male[0] is True
    assert calls[0][1] == bot.default_tts_voice_id("female")
    assert calls[1][1] == bot.default_tts_voice_id("male")
    assert calls[0][1] != calls[1][1]


def test_public_hides_fake_gender_choices_when_only_one_voice_ready(monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "same-voice")
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "same-voice")

    studio_labels = _labels(bot.voice_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    video_labels = _labels(bot.video_finalization_voice_keyboard("vi"))

    assert not any("Giọng nữ" in label or "Giọng nam" in label for label in studio_labels + video_labels)
    assert any("Giọng mặc định" in label for label in studio_labels + video_labels)


def test_voice_vault_is_paginated_with_five_numeric_profile_buttons(monkeypatch):
    profiles = [
        {"id": idx, "display_name": f"Voice {idx}", "status": "active", "provider_voice_id": f"voice-{idx}", "is_default": 0}
        for idx in range(1, 13)
    ]
    monkeypatch.setattr(bot, "user_voice_profile_count", lambda user_id, include_inactive=True: len(profiles))
    monkeypatch.setattr(
        bot,
        "user_voice_profile_rows",
        lambda user_id, limit=5, offset=0, include_inactive=True: profiles[offset:offset + limit],
    )

    first = bot.voice_vault_keyboard(1, "vi", bot.PRODUCT_CONTEXT_SHOWROOM, page=0)
    second = bot.voice_vault_keyboard(1, "vi", bot.PRODUCT_CONTEXT_SHOWROOM, page=1)

    assert _labels(first)[:5] == ["1", "2", "3", "4", "5"]
    assert "music_quick|showroom|voice_profiles_page:1" in _callbacks(first)
    assert "music_quick|showroom|voice_profiles_page:0" in _callbacks(second)
    assert len([cb for cb in _callbacks(first) if "voice_profile_select_code:" in cb]) == 5


def test_failed_voice_profile_cannot_generate_or_offer_final_use():
    profile = {
        "id": 8,
        "display_name": "Voice lỗi",
        "status": "failed",
        "provider_voice_id": "must-not-be-used",
    }
    labels = _labels(bot.voice_profile_actions_keyboard(8, "vi", bot.PRODUCT_CONTEXT_SHOWROOM, profile))

    assert bot.voice_profile_can_generate_tts(profile) is False
    assert "📝 Nhập chữ để giọng này đọc" not in labels
    assert "▶️ Nghe thử" not in labels


def test_failed_voice_profile_pending_text_does_not_call_tts(monkeypatch):
    user_id = 970701
    _reset_user(user_id)
    profile = {"id": 8, "display_name": "Voice lỗi", "status": "failed", "provider_voice_id": "bad"}
    monkeypatch.setattr(bot, "get_user_voice_profile", lambda uid, profile_id: profile)

    async def forbidden_tts(*args, **kwargs):
        raise AssertionError("failed profile must not create audio")

    monkeypatch.setattr(bot, "send_standalone_tts_result", forbidden_tts)
    bot.set_music_guided_pending(
        user_id,
        "voice_profile_read_text",
        profile_id=8,
        product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
    )
    message = CaptureMessage(user_id, "Đọc thử câu này")

    handled = asyncio.run(
        bot.handle_music_guided_pending_text(_message_update(message, user_id), SimpleNamespace())
    )

    assert handled is True
    assert "chưa sẵn sàng" in message.outputs[-1]["text"]


def test_voice_profile_pricing_and_fixed_confirmation_sentence(monkeypatch):
    monkeypatch.setattr(bot, "active_voice_profile_count", lambda user_id, exclude_profile_id=0: 0)
    assert bot.voice_profile_storage_price_xu(1, bot.PRODUCT_CONTEXT_SHOWROOM, 10) == 0
    monkeypatch.setattr(bot, "active_voice_profile_count", lambda user_id, exclude_profile_id=0: 1)
    assert bot.voice_profile_storage_price_xu(1, bot.PRODUCT_CONTEXT_SHOWROOM, 11) == 50
    assert bot.VOICE_CLONE_CONFIRMATION_SAMPLE_TEXT == "Cảm ơn bạn đã sử dụng trình nhân bản giọng nói của TOAN AAS."
    assert "600 Xu" not in bot.voice_clone_quote_text({"id": 11, "user_id": "1"}, "vi", bot.PRODUCT_CONTEXT_SHOWROOM)


def test_music_duration_menu_uses_18_30_60_and_custom_not_preview_length():
    labels = _labels(bot.music_guided_step_keyboard("duration", "vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    joined = "\n".join(labels)

    assert all(label in labels for label in ["18 giây", "30 giây", "60 giây", "Nhập thời lượng khác"])
    assert "6 giây" not in joined
    assert bot.paid_preview_seconds(120) == 6


def test_longer_music_costs_more_and_full_song_is_half_times_1_8():
    assert bot.music_ai_output_price_xu(60) > bot.music_ai_output_price_xu(30)
    half = bot.music_ai_output_price_xu(60, "song_half")
    full = bot.music_ai_output_price_xu(120, "song_full")

    assert half == bot.HALF_SONG_PRICE_XU
    assert full == bot.round_video_xu(half * 1.8, bot.MUSIC_AI_PRICE_ROUND_TO_XU)


def test_song_product_has_half_and_full_complete_lyrics_choices():
    labels = _labels(bot.music_song_product_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    text = bot.music_song_product_text("vi")

    assert "1️⃣ Nửa bài" in labels
    assert "2️⃣ Full bài" in labels
    assert "không cắt giữa câu" in text


def test_change_music_suggestion_preserves_duration_and_song_product(monkeypatch):
    user_id = 970703
    _reset_user(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")
    bot.save_music_guided_result(user_id, {
        "description": "Bài hát vui về thương hiệu",
        "music_ai_kind": "lyrics",
        "song_product": "full",
        "guided_duration_seconds": 120,
        "suggestions": bot.music_prompt_suggestions("Bài hát vui về thương hiệu", 0, "vi", "lyrics"),
    })

    query = CaptureQuery("music_quick|showroom|prompt_more", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(query, user_id), SimpleNamespace()))
    saved = bot.get_music_guided_result(user_id)

    assert saved["song_product"] == "full"
    assert saved["guided_duration_seconds"] == 120
    assert len(saved["suggestions"]) == 3


def test_music_preview_submits_preview_job_and_confirm_submits_full_job(monkeypatch):
    user_id = 970702
    _reset_user(user_id)
    bot.save_music_guided_result(user_id, {
        "selected_prompt": "Nhạc pop vui tươi nguyên bản",
        "guided_duration_seconds": 30,
        "music_ai_kind": "guided",
    })
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")
    monkeypatch.setattr(bot, "get_suno_music_readiness", lambda: {
        "public_enabled": True,
        "ready": True,
        "full_result_ok": True,
        "cost_gate_ok": True,
    })
    submitted = []

    async def fake_submit(result, preview=False):
        submitted.append({"result": dict(result), "preview": preview})
        task_id = "music-preview-1" if preview else "music-task-1"
        return {"ok": True, "task_id": task_id, "provider": "test-route", "status": "SUBMITTED"}

    monkeypatch.setattr(bot, "submit_music_generation_job", fake_submit)

    preview = CaptureQuery("music_quick|showroom|music_ai_preview", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(preview, user_id), SimpleNamespace()))
    assert len(submitted) == 1
    assert submitted[0]["preview"] is True
    preview_state = bot.get_music_guided_result(user_id)
    assert preview_state["music_preview_seen"] is False
    assert preview_state["music_preview_task_id"] == "music-preview-1"

    preview_state["music_preview_seen"] = True
    bot.save_music_guided_result(user_id, preview_state)

    monkeypatch.setattr(bot, "get_user", lambda uid: (5000, None, None))
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: {"ok": True, "final_cost": 300})
    confirm = CaptureQuery("music_quick|showroom|music_ai_confirm", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(confirm, user_id), SimpleNamespace()))

    assert len(submitted) == 2
    assert submitted[1]["preview"] is False
    assert bot.get_music_guided_result(user_id)["music_task_id"] == "music-task-1"
    assert "Đã xác nhận tạo bản đầy đủ" in confirm.outputs[-1]["text"]


def test_translation_admin_blockers_are_exact_but_public_copy_is_clean(monkeypatch):
    monkeypatch.setattr(bot, "VIDEO_TRANSLATE_SUBTITLE_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_TRANSLATE_SUBTITLE_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", False)
    monkeypatch.setattr(bot, "DEEPL_API_KEY", "")
    monkeypatch.setattr(bot, "gemini_client", None)
    monkeypatch.setattr(bot, "openai_client", None)
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "")
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "")

    blockers = bot.video_translation_admin_blockers(
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        {"target_language": "en"},
    )
    public = bot.video_dubbing_guard_text(
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        {"target_language": "en"},
        "vi",
        admin=False,
    )

    assert "mode_disabled" in blockers
    assert "VIDEO_TRANSLATE_SUBTITLE_PUBLIC_ENABLED" in blockers
    assert any("Key4U qwen-mt-turbo smoke or ShopAIKey chat smoke" in item for item in blockers)
    _assert_public_copy_safe(public)


def test_translation_provider_status_command_is_registered():
    source = open(bot.__file__, "r", encoding="utf-8").read()
    assert 'CommandHandler("translation_provider_status", cmd_translation_provider_status)' in source


def test_video_200_allows_free_choices_but_blocks_paid_addons():
    assert bot.video_tier_allows_paid_addons("low") is False
    assert bot.video_tier_allows_paid_addons("basic") is True
    allowed = set(bot.get_allowed_addons_for_tier("low"))

    assert "stock_music_library" in allowed
    assert "default_voice_library" in allowed
    assert "suno_music" not in allowed
    assert "voice_clone_create" not in allowed


def test_video_200_lock_returns_to_options_and_public_copy_is_clean():
    markup = bot.video_experience_tier_lock_keyboard("vi")
    labels = _labels(markup)
    callbacks = _callbacks(markup)
    text = bot.video_experience_tier_lock_text("vi", ["paid_music"])

    assert labels == ["🔷 Nâng lên 300 Xu", "⬅️ Quay lại"]
    assert callbacks == ["videoaddon|upgrade_300", "videoaddon|export_back"]
    _assert_public_copy_safe(text)


def test_final_video_preview_worker_payload_is_free_and_max_six_seconds():
    state = {
        "current_video_duration_seconds": 90,
        "pending_payload": {"duration_seconds": 90, "video_tier": "basic"},
    }
    payload = bot.video_paid_preview_worker_payload(1, 1, state, "preview-token")

    assert payload["preview_seconds"] == 6
    assert payload["confirm_token"] == "preview-token"
    assert "price_xu" not in payload
