import time
from pathlib import Path
import asyncio
from types import SimpleNamespace

import bot


def _callbacks(markup):
    return {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }


def _labels(markup):
    return [
        str(button.text)
        for row in markup.inline_keyboard
        for button in row
    ]


def _source_between(start_marker: str, end_marker: str) -> str:
    source = Path(bot.__file__).resolve().read_text(encoding="utf-8")
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def test_video_finalization_state_preserves_independent_options(monkeypatch):
    user_id = 991201
    bot.clear_video_finalization_state(user_id)
    monkeypatch.setattr(bot, "VIDEO_FINALIZATION_STATE_TTL_SECONDS", 600)

    state = bot.set_video_finalization_state(
        user_id,
        {
            "source": "trend",
            "photos": ["photo-1", "photo-2"],
            "source_payload": {"prompt": "A clean product reveal"},
        },
    )
    assert state["pending_action"] == "video_finalization"
    assert state["video_finalization"]["music_enabled"] is False

    bot.update_video_finalization(
        user_id,
        music_enabled=True,
        music_mode="suggested",
        music_prompt="subtle cinematic music",
    )
    bot.update_video_finalization(
        user_id,
        subtitle_enabled=True,
        subtitle_mode="manual",
        subtitle_text="TOAN AAS",
        subtitle_burn_in=True,
    )
    saved = bot.get_video_finalization_state(user_id)
    finalization = saved["video_finalization"]
    assert finalization["music_enabled"] is True
    assert finalization["music_mode"] == "suggested"
    assert finalization["subtitle_enabled"] is True
    assert finalization["subtitle_text"] == "TOAN AAS"
    assert finalization["voice_enabled"] is False
    assert saved["photos"] == ["photo-1", "photo-2"]
    bot.clear_video_finalization_state(user_id)


def test_video_finalization_package_maps_music_subtitle_and_dub():
    package = bot.video_finalization_package_from_state({
        "source": "promptvideo",
        "video_prompt": "A clean TOAN AAS product video",
        "has_video_prompt": True,
        "source_payload": {"prompt": "A clean TOAN AAS product video"},
        "video_finalization": {
            "music_enabled": True,
            "music_mode": "suno",
            "music_prompt": "uplifting tech background music",
            "subtitle_enabled": True,
            "subtitle_mode": "manual",
            "subtitle_text": "TOAN AAS",
            "voice_enabled": True,
            "voice_mode": "tts",
            "voice_text": "TOAN AAS",
            "dub_enabled": True,
            "translation_enabled": True,
            "subtitle_language": "en",
            "voice_style": "female",
            "finalization_confirmed": True,
        },
    })

    assert package["music_option"] == "suno"
    assert package["music_prompt"] == "uplifting tech background music"
    assert package["subtitle_option"] == "subtitle_translated"
    assert package["dubbing_option"] == "dub_translated"
    assert package["translation_enabled"] is True
    assert package["target_language"] == "en"
    assert package["voice_style"] == "female"
    assert package["video_finalization_confirmed"] is True


def test_video_finalization_state_expires():
    user_id = 991202
    state = bot.set_video_finalization_state(user_id, {"source": "storyboard"})
    key = bot.video_finalization_pending_key(user_id)
    state["expires_at_ts"] = time.time() - 1
    bot.USER_PENDING[key] = state
    assert bot.get_video_finalization_state(user_id) == {}
    assert key not in bot.USER_PENDING


def test_video_finalization_menu_has_distinct_music_voice_subtitle_and_combo_paths():
    callbacks = _callbacks(bot.video_finalization_menu_keyboard("vi"))
    assert {
        "vfinal|voice",
        "vfinal|music",
        "vfinal|addon",
        "vfinal|tier",
        "vfinal|skip",
        "vfinal|back",
        "vfinal|main",
    }.issubset(callbacks)
    assert "vfinal|music_library" not in callbacks
    assert "vfinal|voice_defaults" not in callbacks
    assert "vfinal|combo" not in callbacks

    addon_callbacks = _callbacks(bot.video_finalization_addon_keyboard("vi"))
    assert "vfinal|subtitle" in addon_callbacks
    assert "vfinal|translate_sub" in addon_callbacks
    assert "vfinal|dub" in addon_callbacks
    assert "vfinal|combo" in addon_callbacks


def test_video_finalization_summary_and_guard_are_explicit(monkeypatch):
    monkeypatch.setattr(
        bot,
        "video_finalization_readiness",
        lambda: {
            "local_frame": False,
            "music_mux": False,
            "voice_mux": False,
            "subtitle_burn": False,
            "asr": False,
            "translate": False,
            "dub": False,
            "ai_video": False,
        },
    )
    state = {
        "source": "storyboard",
        "photos": ["photo-1", "photo-2", "photo-3"],
        "has_script": True,
        "has_video_prompt": True,
        "video_finalization": {
            "music_enabled": True,
            "voice_enabled": False,
            "subtitle_enabled": True,
        },
    }
    text = bot.video_finalization_summary_text(state, "vi")
    assert "Xác nhận xuất video" in text
    assert "Ghép ảnh local" in text
    assert "Video AI" in text
    assert "chưa trừ Xu" in text

    guard = bot.video_finalization_ai_guard_text("vi")
    assert "bảo trì / nâng cấp" in guard
    assert "chưa xử lý video" in guard
    assert "chưa trừ Xu" in guard


def test_video_finalization_summary_keeps_prompt_export_when_ai_not_ready(monkeypatch):
    monkeypatch.setattr(
        bot,
        "get_video_prompt_export_readiness",
        lambda user_is_admin=False: {
            "public_ready": False,
            "admin_ready": False,
            "ready": False,
            "missing_public": ["VIDEO_AI_PUBLIC_ENABLED=false"],
            "missing_admin": ["admin required"],
            "reason": "VIDEO_AI_PUBLIC_ENABLED=false",
        },
    )
    state = {
        "source": "trend",
        "source_label": "Video theo trend",
        "photos": [],
        "has_script": True,
        "has_video_prompt": True,
    }
    summary_text = bot.video_finalization_summary_text(state, "vi")
    assert "không bắt buộc nếu xuất từ prompt" in summary_text

    callbacks = _callbacks(bot.video_finalization_summary_keyboard(state, "vi"))
    assert "vfinal|export_local" not in callbacks
    assert "vfinal|export_ai" in callbacks
    assert "vfinal|ai_guard" not in callbacks
    assert "vfinal|copy_prompt" in callbacks
    assert "trendg|image_step" not in callbacks

    text = bot.video_finalization_local_needs_images_text(state, "vi")
    assert "Ghép ảnh thành video cần có ảnh trước" in text
    assert "Tạo video AI chân thật" in text
    assert "chưa trừ Xu" in text

    guard_callbacks = _callbacks(bot.video_finalization_guard_keyboard(state, "vi"))
    assert "vfinal|export_local" not in guard_callbacks
    assert "vfinal|review" in guard_callbacks
    assert "vfinal|back" not in _callbacks(bot.video_finalization_local_needs_images_keyboard(state, "vi"))
    assert "vfinal|review" in _callbacks(bot.video_finalization_local_needs_images_keyboard(state, "vi"))
    assert "vfinal|export_ai" in _callbacks(bot.video_finalization_local_needs_images_keyboard(state, "vi"))
    assert "vfinal|ai_guard" not in _callbacks(bot.video_finalization_local_needs_images_keyboard(state, "vi"))


def test_video_finalization_summary_shows_prompt_export_only_when_ai_ready(monkeypatch):
    monkeypatch.setattr(
        bot,
        "get_video_prompt_export_readiness",
        lambda user_is_admin=False: {
            "public_ready": True,
            "admin_ready": False,
            "ready": True,
            "missing_public": [],
            "missing_admin": ["admin required"],
            "reason": "ready",
        },
    )
    state = {
        "source": "trend",
        "source_label": "Video theo trend",
        "photos": [],
        "has_script": True,
        "has_video_prompt": True,
    }
    callbacks = _callbacks(bot.video_finalization_summary_keyboard(state, "vi"))
    assert "vfinal|export_local" not in callbacks
    assert "vfinal|export_ai" in callbacks
    assert "vfinal|ai_guard" not in callbacks
    assert "vfinal|copy_prompt" in callbacks


def test_video_finalization_summary_keeps_local_export_when_images_exist(monkeypatch):
    monkeypatch.setattr(
        bot,
        "video_finalization_readiness",
        lambda: {
            "local_frame": True,
            "music_mux": False,
            "voice_mux": False,
            "subtitle_burn": False,
            "asr": False,
            "translate": False,
            "dub": False,
            "ai_video": True,
        },
    )
    monkeypatch.setattr(
        bot,
        "get_video_prompt_export_readiness",
        lambda user_is_admin=False: {
            "public_ready": True,
            "admin_ready": False,
            "ready": True,
            "missing_public": [],
            "missing_admin": ["admin required"],
            "reason": "ready",
        },
    )
    state = {
        "source": "storyboard",
        "photos": [{"file_id": "photo-1"}, {"file_id": "photo-2"}],
        "has_script": True,
        "has_video_prompt": True,
    }
    callbacks = _callbacks(bot.video_finalization_summary_keyboard(state, "vi"))
    assert "vfinal|export_local" in callbacks
    assert "vfinal|export_ai" in callbacks
    guard_callbacks = _callbacks(bot.video_finalization_guard_keyboard(state, "vi"))
    assert "vfinal|copy_prompt" in guard_callbacks
    assert "vfinal|export_local" not in guard_callbacks


def test_stale_local_export_without_images_uses_prompt_video_path(monkeypatch):
    user_id = 991209
    bot.clear_video_finalization_state(user_id)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(
        bot,
        "get_video_prompt_export_readiness",
        lambda user_is_admin=False: {
            "public_ready": False,
            "admin_ready": False,
            "ready": False,
            "missing_public": ["VIDEO_AI_PUBLIC_ENABLED=false"],
            "missing_admin": ["admin required"],
            "reason": "VIDEO_AI_PUBLIC_ENABLED=false",
        },
    )
    bot.set_video_finalization_state(user_id, {
        "source": "trend",
        "source_label": "Video theo trend",
        "photos": [],
        "has_script": True,
        "has_video_prompt": True,
    })

    class FakeQuery:
        data = "vfinal|export_local"
        from_user = SimpleNamespace(id=user_id)
        message = SimpleNamespace(chat_id=user_id)
        edited = None

        async def answer(self, *args, **kwargs):
            return None

        async def edit_message_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
            self.edited = {"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup}
            return self.edited

    query = FakeQuery()
    asyncio.run(bot.handle_video_finalization_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.edited is not None
    assert "Chọn gói xuất video AI" in query.edited["text"]
    assert "Prompt video: <b>Có</b>" in query.edited["text"]
    callbacks = _callbacks(query.edited["reply_markup"])
    assert "vfinal|tier|low" in callbacks
    assert "vfinal|tier|basic" in callbacks
    assert "vfinal|export_local" not in callbacks
    assert "vfinal|back" in callbacks


def test_ready_prompt_export_opens_public_video_tiers(monkeypatch):
    user_id = 991211
    bot.clear_video_finalization_state(user_id)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(
        bot,
        "get_video_prompt_export_readiness",
        lambda user_is_admin=False: {
            "public_ready": True,
            "admin_ready": False,
            "ready": True,
            "missing_public": [],
            "missing_admin": ["admin required"],
            "reason": "ready",
        },
    )
    bot.set_video_finalization_state(user_id, {
        "source": "trend",
        "source_label": "Video theo trend",
        "photos": [],
        "source_payload": {"video_prompt": "Prompt video ready"},
        "has_script": True,
        "has_video_prompt": True,
    })

    class FakeQuery:
        data = "vfinal|export_ai"
        from_user = SimpleNamespace(id=user_id)
        message = SimpleNamespace(chat_id=user_id)
        edited = None

        async def answer(self, *args, **kwargs):
            return None

        async def edit_message_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
            self.edited = {"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup}
            return self.edited

    query = FakeQuery()
    asyncio.run(bot.handle_video_finalization_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.edited is not None
    assert "Chọn gói xuất video AI" in query.edited["text"]
    callbacks = _callbacks(query.edited["reply_markup"])
    assert "vfinal|tier|basic" in callbacks
    assert "vfinal|tier|common" in callbacks
    pending = bot.get_video_finalization_state(user_id)
    assert pending.get("source_payload", {}).get("video_prompt") or pending.get("source_payload", {}).get("prompt")


def test_video_finalization_tier_menu_is_two_columns_and_not_misleading():
    markup = bot.video_finalization_tier_keyboard("vi")
    assert all(len(row) <= 2 for row in markup.inline_keyboard)
    labels = _labels(markup)
    assert any("Trải nghiệm" in label and "200 Xu" in label for label in labels)
    assert any("Bán hàng" in label and "600 Xu" in label for label in labels)
    assert not any("nếu" in label.lower() for label in labels)
    callbacks = _callbacks(markup)
    assert "vfinal|tier|low" in callbacks
    assert "vfinal|tier|basic" in callbacks
    assert "vfinal|tier|common" in callbacks
    assert "vfinal|review" in callbacks


def test_video_result_keyboard_uses_clear_ai_action_label():
    labels = _labels(bot.guided_video_result_keyboard("promptvideo", "vi"))
    assert "🎬 Tạo video AI" in labels
    assert not any("nếu" in label.lower() for label in labels)


def test_video_addon_confirm_keeps_finalization_back_context():
    markup = bot.video_addon_confirm_keyboard("tok123", "low", "vi")
    callbacks = _callbacks(markup)
    ordered_callbacks = [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]
    assert "videoaddon|preview|tok123" in callbacks
    assert "shopai|confirm|tok123" in callbacks
    assert ordered_callbacks.index("videoaddon|preview|tok123") < ordered_callbacks.index("shopai|confirm|tok123")
    assert "vfinal|tier" in callbacks
    assert "vfinal|voice" in callbacks
    assert "vfinal|music" in callbacks
    assert "vfinal|addon" in callbacks
    assert "videoaddon|back" in callbacks
    assert "create_media|quick_video" not in callbacks


def test_video_addon_language_and_voice_back_use_screen_stack():
    language_callbacks = _callbacks(bot.video_addon_language_keyboard("vi"))
    voice_callbacks = _callbacks(bot.video_addon_voice_keyboard("vi"))
    assert "videoaddon|back" in language_callbacks
    assert "videoaddon|back" in voice_callbacks
    assert "videoaddon|menu" not in language_callbacks
    assert "videoaddon|menu" not in voice_callbacks


def test_video_addon_invoice_back_returns_canonical_video_options(monkeypatch):
    user_id = 991213
    bot.clear_video_addon_state(user_id)
    bot.clear_video_session(user_id)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "get_user", lambda _uid: (5000, None, None))
    monkeypatch.setattr(bot, "record_shopaikey_billing_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(bot, "set_shopaikey_pending_confirmation", lambda *_args, **_kwargs: "token-back-test")
    monkeypatch.setattr(bot, "active_package_item_for_user", lambda *_args, **_kwargs: None)

    state = bot.set_video_addon_state(user_id, {
        "source": "ai",
        "video_tier": "basic",
        "pending_payload": {
            "video_tier": "basic",
            "video_prompt": "Prompt video ready",
            "video_finalization_confirmed": True,
        },
    })
    state = bot.set_video_addon_screen(user_id, state, "addon_voice")
    state["current_video_dubbing_option"] = "dub_original"
    state["current_video_voice_style"] = "female"

    class FakeQuery:
        data = "videoaddon|back"
        from_user = SimpleNamespace(id=user_id)
        message = SimpleNamespace(chat_id=user_id)
        edited = None

        async def answer(self, *args, **kwargs):
            return None

        async def edit_message_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
            self.edited = {"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup}
            return self.edited

    query = FakeQuery()
    asyncio.run(bot.finalize_video_addon_confirmation(query, user_id, state, "vi"))
    saved = bot.get_video_addon_state(user_id)
    assert saved["video_order"]["current_screen"] == "invoice"
    assert saved["video_order"]["screen_stack"][-2:] == ["addon_voice", "invoice"]

    asyncio.run(bot.handle_video_addon_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert "Tùy chọn hoàn thiện video" in query.edited["text"]
    saved = bot.get_video_addon_state(user_id)
    assert saved["video_order"]["current_screen"] == "invoice"
    assert "vfinal|voice" in _callbacks(query.edited["reply_markup"])
    assert "vfinal|music" in _callbacks(query.edited["reply_markup"])
    assert "vfinal|addon" in _callbacks(query.edited["reply_markup"])
    bot.clear_video_addon_state(user_id)
    bot.clear_video_session(user_id)


def test_video_addon_back_returns_to_existing_finalization_tier(monkeypatch):
    user_id = 991212
    bot.clear_video_finalization_state(user_id)
    bot.clear_video_addon_state(user_id)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    bot.set_video_finalization_state(user_id, {
        "source": "promptvideo",
        "source_label": "Prompt → Video AI",
        "source_payload": {"video_prompt": "Prompt video ready"},
        "has_script": False,
        "has_video_prompt": True,
        "step": "confirm",
    })
    bot.set_video_addon_state(user_id, {
        "source": "ai",
        "video_tier": "low",
        "pending_payload": {
            "video_tier": "low",
            "video_prompt": "Prompt video ready",
            "aspect_ratio": "9:16",
        },
    })

    class FakeQuery:
        data = "videoaddon|back"
        from_user = SimpleNamespace(id=user_id)
        message = SimpleNamespace(chat_id=user_id)
        edited = None

        async def answer(self, *args, **kwargs):
            return None

        async def edit_message_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
            self.edited = {"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup}
            return self.edited

    query = FakeQuery()
    asyncio.run(bot.handle_video_addon_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.edited is not None
    assert "Chọn gói xuất video AI" in query.edited["text"]
    callbacks = _callbacks(query.edited["reply_markup"])
    assert "vfinal|tier|low" in callbacks
    assert "create_media|quick_video" not in callbacks
    current = bot.get_video_finalization_state(user_id)
    assert current.get("step") == "tier"


def test_local_export_without_prompt_or_images_keeps_image_slideshow_guard(monkeypatch):
    user_id = 991210
    bot.clear_video_finalization_state(user_id)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    bot.set_video_finalization_state(user_id, {
        "source": "videoidea",
        "source_label": "Ý tưởng video",
        "photos": [],
        "has_script": False,
        "has_video_prompt": False,
    })

    class FakeQuery:
        data = "vfinal|export_local"
        from_user = SimpleNamespace(id=user_id)
        message = SimpleNamespace(chat_id=user_id)
        edited = None

        async def answer(self, *args, **kwargs):
            return None

        async def edit_message_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
            self.edited = {"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup}
            return self.edited

    query = FakeQuery()
    asyncio.run(bot.handle_video_finalization_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.edited is not None
    assert "Ghép ảnh thành video local chưa sẵn" in query.edited["text"]
    callbacks = _callbacks(query.edited["reply_markup"])
    assert "vfinal|review" in callbacks
    assert "vfinal|back" not in callbacks


def test_video_finalization_readiness_requires_explicit_flags(monkeypatch):
    monkeypatch.setattr(bot, "VIDEO_LOCAL_FRAME_RENDER_ENABLED", True)
    monkeypatch.setattr(bot, "FRAME_VIDEO_ENABLED", True)
    monkeypatch.setattr(bot, "FRAME_VIDEO_DIRECT_RENDER_ENABLED", False)
    monkeypatch.setattr(bot, "FRAME_VIDEO_REQUIRE_LOCAL_WORKER", True)
    monkeypatch.setattr(bot, "frame_video_worker_connected", lambda: False)
    monkeypatch.setattr(bot, "VIDEO_MUSIC_MUX_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_VOICE_MUX_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_BURN_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_DUB_TTS_ENABLED", False)
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_VIDEO_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_AI_PUBLIC_ENABLED", False)

    readiness = bot.video_finalization_readiness()
    assert readiness["local_frame"] is False
    assert readiness["music_mux"] is False
    assert readiness["voice_mux"] is False
    assert readiness["subtitle_burn"] is False
    assert readiness["asr"] is False
    assert readiness["dub"] is False
    assert readiness["ai_video"] is False


def test_video_result_keyboards_link_to_common_finalization():
    for markup in (
        bot.guided_video_result_keyboard("promptvideo", "vi"),
        bot.video_reference_result_keyboard("vi"),
        bot.self_scene_result_keyboard("vi"),
        bot.long_video_result_keyboard("vi"),
        bot.video_idea_result_keyboard("vi"),
    ):
        assert any(
            callback.endswith("|finalization")
            for callback in _callbacks(markup)
        )


def test_finalization_callback_is_registered_and_has_no_direct_billing():
    source = Path(bot.__file__).resolve().read_text(encoding="utf-8")
    assert 'CallbackQueryHandler(handle_video_finalization_callback, pattern=r"^vfinal\\|")' in source
    assert "Chọn bước muốn quay lại" not in source
    assert "Bạn chưa có bộ ảnh để ghép video" not in source
    handler_source = _source_between(
        "async def handle_video_finalization_callback",
        "async def handle_video_finalization_pending_text",
    )
    for forbidden in (
        "spend_fixed_credit_info(",
        "deduct_credits(",
        "charge_user(",
        "create_payment",
    ):
        assert forbidden not in handler_source
    assert "set_public_video_package_context" in handler_source
    assert "video_finalization_tier_text" in handler_source


def test_video_finalization_flags_are_documented():
    env_text = (
        Path(bot.__file__).resolve().parent / ".env.example"
    ).read_text(encoding="utf-8")
    for name in (
        "VIDEO_LOCAL_FRAME_RENDER_ENABLED",
        "VIDEO_MUSIC_MUX_ENABLED",
        "VIDEO_VOICE_MUX_ENABLED",
        "VIDEO_SUBTITLE_BURN_ENABLED",
        "VIDEO_ASR_ENABLED",
        "VIDEO_DUB_TTS_ENABLED",
        "VIDEO_TO_VIDEO_PUBLIC_ENABLED",
        "VIDEO_LONG_AI_PUBLIC_ENABLED",
    ):
        assert f"{name}=" in env_text
