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
        "vfinal|music",
        "vfinal|voice",
        "vfinal|subtitle",
        "vfinal|combo",
        "vfinal|skip",
        "vfinal|review",
        "vfinal|back",
        "vfinal|main",
    }.issubset(callbacks)
    assert "vfinal|subtitle" != "vfinal|combo"

    subtitle_callbacks = _callbacks(bot.video_finalization_subtitle_keyboard("vi"))
    assert "vfinal|subtitle_manual" in subtitle_callbacks
    assert "vfinal|subtitle_asr" in subtitle_callbacks
    assert not any("voice" in callback for callback in subtitle_callbacks)


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
    assert "chưa mở render Video AI công khai" in guard
    assert "chưa gọi API" in guard
    assert "chưa trừ Xu" in guard


def test_video_finalization_summary_routes_prompt_without_images_to_ai_or_keyframe():
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
    assert "trendg|image_step" in callbacks

    text = bot.video_finalization_local_needs_images_text(state, "vi")
    assert "Ghép ảnh thành video cần có ảnh trước" in text
    assert "Tạo video AI chân thật" in text
    assert "chưa trừ Xu" in text

    guard_callbacks = _callbacks(bot.video_finalization_guard_keyboard(state, "vi"))
    assert "vfinal|export_local" not in guard_callbacks
    assert "vfinal|review" in guard_callbacks
    assert "vfinal|back" not in _callbacks(bot.video_finalization_local_needs_images_keyboard(state, "vi"))
    assert "vfinal|review" in _callbacks(bot.video_finalization_local_needs_images_keyboard(state, "vi"))


def test_video_finalization_summary_keeps_local_export_when_images_exist():
    state = {
        "source": "storyboard",
        "photos": [{"file_id": "photo-1"}, {"file_id": "photo-2"}],
        "has_script": True,
        "has_video_prompt": True,
    }
    callbacks = _callbacks(bot.video_finalization_summary_keyboard(state, "vi"))
    assert "vfinal|export_local" in callbacks
    assert "vfinal|export_ai" in callbacks
    assert "vfinal|export_local" in _callbacks(bot.video_finalization_guard_keyboard(state, "vi"))


def test_stale_local_export_without_images_uses_prompt_video_path(monkeypatch):
    user_id = 991209
    bot.clear_video_finalization_state(user_id)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "is_ai_video_ready", lambda: False)
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
    assert "Video AI chân thật đang được kiểm soát an toàn" in query.edited["text"]
    assert "Prompt/kế hoạch của bạn vẫn được giữ" in query.edited["text"]
    callbacks = _callbacks(query.edited["reply_markup"])
    assert "vfinal|review" in callbacks
    assert "vfinal|export_local" not in callbacks
    assert "vfinal|back" not in callbacks


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
    assert "Ghép ảnh thành video cần có ảnh trước" in query.edited["text"]
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
    assert "public_video_tier_selection_text" in handler_source


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
