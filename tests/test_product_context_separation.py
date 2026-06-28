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


def _flatten_text(markup):
    return "\n".join(_labels(markup))


def test_product_context_callback_parser_is_explicit():
    assert bot.parse_product_context_callback("music_quick|showroom|voice_hub") == (
        "music_quick",
        bot.PRODUCT_CONTEXT_SHOWROOM,
        "voice_hub",
    )
    assert bot.parse_product_context_callback("music_quick|video_addon|music") == (
        "music_quick",
        bot.PRODUCT_CONTEXT_VIDEO_ADDON,
        "music",
    )
    assert bot.infer_product_context_from_callback("vfinal|music") == bot.PRODUCT_CONTEXT_VIDEO_ADDON
    assert bot.infer_product_context_from_callback("videoaddon|menu") == bot.PRODUCT_CONTEXT_VIDEO_ADDON
    assert bot.infer_product_context_from_callback("videodub|start|translation") == bot.PRODUCT_CONTEXT_SHOWROOM
    assert bot.infer_product_context_from_callback("music_quick|voice_hub") == bot.PRODUCT_CONTEXT_SHOWROOM


def test_start_menu_routes_voice_music_translation_to_showroom():
    callbacks = _callbacks(bot.localized_main_menu_keyboard(False, "vi"))

    assert "music_quick|showroom|root" in callbacks
    assert "menu|translate" in callbacks
    assert "menu|main_music" not in callbacks
    assert not any(callback.startswith("vfinal|") or callback.startswith("videoaddon|") for callback in callbacks)


def test_showroom_voice_music_have_no_video_addon_controls():
    voice_labels = _flatten_text(bot.voice_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    music_labels = _flatten_text(bot.music_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    voice_callbacks = _callbacks(bot.voice_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    music_callbacks = _callbacks(bot.music_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))

    for text in [voice_labels, music_labels]:
        assert "Không thêm" not in text
        assert "Chọn cho video" not in text
        assert "Dùng cho video hiện tại" not in text
        assert "Quay lại video" not in text
    assert not any(callback.startswith("vfinal|") or callback.startswith("videoaddon|") for callback in voice_callbacks)
    assert not any(callback.startswith("vfinal|") or callback.startswith("videoaddon|") for callback in music_callbacks)
    assert all("|showroom|" in callback or callback == "menu|main" for callback in voice_callbacks if callback.startswith("music_quick|") or callback == "menu|main")
    assert all("|showroom|" in callback or callback == "menu|main" for callback in music_callbacks if callback.startswith("music_quick|") or callback == "menu|main")


def test_showroom_translation_is_not_video_order_menu():
    text = bot.translation_menu_text("vi")
    labels = _flatten_text(bot.translation_menu_keyboard("vi"))
    callbacks = _callbacks(bot.translation_menu_keyboard("vi"))

    assert "Trung tâm dịch" in text
    assert "Dịch ngôn ngữ" in labels
    assert "Dịch phụ đề / Video" in labels
    assert "Dịch file" in labels
    assert "Dịch audio" in labels
    assert "Dịch phụ đề file" in labels
    assert "hóa đơn video" not in text.lower()
    assert "Không thêm" not in labels
    assert "Chọn cho video" not in labels
    assert "Quay lại video" not in labels
    assert not any(callback.startswith("vfinal|") or callback.startswith("videoaddon|") for callback in callbacks)


def test_video_addon_entry_points_do_not_route_to_showroom():
    labels = _flatten_text(bot.music_tools_keyboard("vi", "menu|main_video"))
    callbacks = _callbacks(bot.music_tools_keyboard("vi", "menu|main_video"))

    assert "Voice Studio" not in labels
    assert "Music Studio" not in labels
    assert "Giọng đọc cho video" in labels
    assert "Nhạc cho video" in labels
    assert {"vfinal|voice", "vfinal|music", "vfinal|addon"}.issubset(set(callbacks))
    assert "vfinal|my_media" not in callbacks
    assert not any("|showroom|" in callback for callback in callbacks)


def test_video_voice_and_music_keyboards_are_video_addon_only():
    voice_callbacks = _callbacks(bot.video_finalization_voice_keyboard("vi"))
    music_callbacks = _callbacks(bot.video_finalization_music_keyboard("vi"))
    voice_labels = _flatten_text(bot.video_finalization_voice_keyboard("vi"))
    music_labels = _flatten_text(bot.video_finalization_music_keyboard("vi"))

    assert "Không thêm giọng" in voice_labels
    assert "Giọng nữ miễn phí" in voice_labels
    assert "Voice đã lưu" in voice_labels
    assert "Không thêm nhạc" in music_labels
    assert "Kho nhạc có sẵn" in music_labels
    assert "Kho hiệu ứng âm thanh" in music_labels
    assert all(callback.startswith("vfinal|") for callback in voice_callbacks)
    assert all(callback.startswith("vfinal|") for callback in music_callbacks)
    assert not any("|showroom|" in callback for callback in voice_callbacks + music_callbacks)


def test_media_preview_copy_switches_by_context():
    items = [{"title": "Track", "preview_url": "https://example.test/track.mp3"}]

    showroom_labels = _flatten_text(bot.media_preview_keyboard("music", items, "vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    addon_labels = _flatten_text(bot.media_preview_keyboard("music", items, "vi", bot.PRODUCT_CONTEXT_VIDEO_ADDON))

    assert "Chọn 1" in showroom_labels
    assert "Gắn nhạc vào video 1" not in showroom_labels
    assert "Gắn nhạc vào video 1" in addon_labels


def test_video_addon_voice_choice_preserves_existing_video_draft(monkeypatch):
    user_id = 731801
    bot.clear_video_finalization_state(user_id)
    bot.clear_product_context(user_id)
    bot.set_video_finalization_state(user_id, {
        "source": "ai",
        "source_video_file_id": "video-file-id",
        "selected_video_tier": "basic",
        "current_video_duration_seconds": 95,
        "object_prompt": "serum bottle",
        "direction_prompt": "slow reveal",
        "source_payload": {"invoice_id": "invoice-123", "source_file_id": "source-file-id"},
        "video_order": {"invoice_id": "invoice-123", "package": "basic"},
        "video_finalization": {"music_mode": "library", "music_item_count": 1},
    })

    class FakeQuery:
        data = "music_quick|video_addon|voice_default_female"
        outputs = []
        message = SimpleNamespace()

        async def answer(self, *args, **kwargs):
            return None

        async def edit_message_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
            self.outputs.append({"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup, **kwargs})
            return SimpleNamespace(text=text, reply_markup=reply_markup)

    query = FakeQuery()
    asyncio.run(bot.handle_music_quick_callback(
        SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=user_id)),
        SimpleNamespace(),
    ))
    saved = bot.get_video_finalization_state(user_id)
    finalization = saved["video_finalization"]

    assert saved["step"] == "await_voice_script"
    assert "gửi nội dung/kịch bản cần đọc" in query.outputs[-1]["text"]
    assert saved["source_video_file_id"] == "video-file-id"
    assert saved["source_payload"]["source_file_id"] == "source-file-id"
    assert saved["video_order"]["invoice_id"] == "invoice-123"
    assert saved["selected_video_tier"] == "basic"
    assert saved["current_video_duration_seconds"] == 95
    assert saved["object_prompt"] == "serum bottle"
    assert saved["direction_prompt"] == "slow reveal"
    assert finalization["music_mode"] == "library"
    assert finalization["music_item_count"] == 1
    assert finalization["voice_mode"] == "default_female_free"
    assert finalization["dub_enabled"] is False
    assert bot.current_product_context(user_id) == bot.PRODUCT_CONTEXT_VIDEO_ADDON


def test_showroom_voice_choice_does_not_update_existing_video_draft():
    user_id = 731802
    replies = []
    bot.clear_video_finalization_state(user_id)
    bot.clear_product_context(user_id)
    bot.set_video_finalization_state(user_id, {
        "source": "ai",
        "source_video_file_id": "existing-video-file",
        "selected_video_tier": "standard",
        "current_video_duration_seconds": 42,
        "video_finalization": {"voice_mode": "none", "music_mode": "none"},
    })

    class FakeMessage:
        async def reply_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
            replies.append({"text": text, "reply_markup": reply_markup})
            return SimpleNamespace(text=text, reply_markup=reply_markup)

    class FakeQuery:
        data = "music_quick|showroom|voice_default_female"
        message = FakeMessage()

        async def answer(self, *args, **kwargs):
            return None

    asyncio.run(bot.handle_music_quick_callback(
        SimpleNamespace(callback_query=FakeQuery(), effective_user=SimpleNamespace(id=user_id)),
        SimpleNamespace(),
    ))
    saved = bot.get_video_finalization_state(user_id)

    assert replies
    assert "không gắn vào video hiện tại" in replies[-1]["text"]
    assert saved["source_video_file_id"] == "existing-video-file"
    assert saved["selected_video_tier"] == "standard"
    assert saved["current_video_duration_seconds"] == 42
    assert saved["video_finalization"]["voice_mode"] == "none"
    assert saved["video_finalization"]["music_mode"] == "none"
    assert bot.current_product_context(user_id) == bot.PRODUCT_CONTEXT_SHOWROOM


def test_new_product_surfaces_do_not_leak_raw_provider_terms():
    texts = [
        bot.voice_hub_text("vi", bot.PRODUCT_CONTEXT_SHOWROOM),
        bot.music_hub_text("vi", bot.PRODUCT_CONTEXT_SHOWROOM),
        bot.translation_menu_text("vi"),
        bot.video_finalization_voice_text({"selected_video_tier": "basic"}, "vi"),
        bot.video_finalization_music_text({"selected_video_tier": "basic"}, "vi"),
        bot.video_addon_menu_text({"video_tier": "basic", "current_video_duration_seconds": 61}, "vi"),
    ]
    bad_terms = ["api", "provider", "env", "traceback", "http", "raw error", "suno", "minimax", "key4u", "shopaikey"]

    for text in texts:
        lowered = text.lower()
        assert not any(term in lowered for term in bad_terms)
