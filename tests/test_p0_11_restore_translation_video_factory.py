import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def test_translation_gateway_has_language_and_video_factory():
    text = bot.translation_menu_text("vi")
    labels = _labels(bot.translation_menu_keyboard("vi"))
    assert "Trung tâm dịch thuật TOAN AAS" in text
    assert "🌐 Dịch ngôn ngữ" in labels
    assert "🎬 Dịch video" in labels
    assert "menu|translation_language_hub" in _callbacks(bot.translation_menu_keyboard("vi"))
    assert "menu|translation_video_factory" in _callbacks(bot.translation_menu_keyboard("vi"))


def test_language_translation_menu_restored():
    labels = _labels(bot.translation_language_hub_keyboard("vi"))
    assert "📝 Văn bản" in labels
    assert "📄 Tài liệu" in labels
    assert "🖼 Chữ trong ảnh" in labels
    assert "🎧 Audio" in labels
    assert "⚙️ Ngôn ngữ" in labels
    assert "⬅️ Trung tâm" in labels


def test_video_factory_menu_from_gateway():
    labels = _labels(bot.video_dubbing_menu_keyboard("vi", "translation"))
    assert "📝 Tạo phụ đề" in labels
    assert "🌐 Dịch phụ đề" in labels
    assert "🗣 Lồng tiếng" in labels
    assert not any("Dịch + lồng tiếng" in label for label in labels)
    assert "🔗 Tải từ link" in labels
    assert "📂 Media của tôi" in labels
    assert "✏️ Chỉnh phụ đề" in labels
    assert "⬅️ Trung tâm dịch thuật" in labels


def test_back_language_menu_to_gateway():
    assert "menu|translate" in _callbacks(bot.translation_language_hub_keyboard("vi"))


def test_back_video_factory_to_gateway():
    assert "menu|translate" in _callbacks(bot.video_dubbing_menu_keyboard("vi", "translation"))


def test_translation_removed_from_video_main_menu():
    labels = _labels(bot.main_video_keyboard("vi"))
    assert "🌐 Dịch/Lồng tiếng video" not in labels
    assert not any(label == "🌐 Dịch/lồng tiếng video" for label in labels)


def test_translation_addon_present_in_video_addon_step():
    labels = _labels(bot.video_finalization_menu_keyboard("vi"))
    addon_labels = _labels(bot.video_finalization_addon_keyboard("vi"))
    assert "🌐 Phụ đề / Dịch / Lồng tiếng" in labels
    assert "🌐 Phụ đề / Dịch / Lồng tiếng" in addon_labels
    assert "videodub|start|video_addon" in _callbacks(bot.video_finalization_addon_keyboard("vi"))


def test_social_link_import_restored():
    text = bot.social_link_import_text("vi")
    assert "Tải video từ link" in text
    assert "10 Xu / link tải thành công" in text
    assert bot.social_link_import_validate("https://www.tiktok.com/@abc/video/123")["ok"] is True
    assert bot.social_link_import_validate("https://example.com/video")["ok"] is False


def test_social_link_price_10_xu():
    assert bot.LINK_IMPORT_PRICE_XU == 10


def test_social_link_charge_only_after_success(monkeypatch):
    calls = []

    def fake_spend(*args, **kwargs):
        calls.append((args, kwargs))
        return {"ok": True, "final_cost": 10}

    monkeypatch.setattr(bot, "spend_fixed_credit_info", fake_spend)
    user_id = "p011-link-success"
    bot.set_video_dubbing_pending(user_id, "link_processing", link_import_job_id="77")
    previous = {"id": "77", "job_type": "social_link_import", "status": "running"}
    updated = {
        "id": "77",
        "job_type": "social_link_import",
        "status": "succeeded",
        "user_id": user_id,
        "output_file_id": "tg-video",
        "input_file_id": '{"user_id":"p011-link-success","source_url":"https://youtu.be/x","source_platform":"YouTube"}',
    }
    bot.handle_social_link_import_worker_job_update(previous, updated)
    state = bot.get_video_dubbing_pending(user_id)
    assert calls and calls[0][0][1] == 10
    assert state["source_file_id"] == "tg-video"
    assert state["link_import_status"] == "succeeded"


def test_social_link_no_charge_on_failure(monkeypatch):
    calls = []
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: calls.append(args))
    user_id = "p011-link-fail"
    bot.set_video_dubbing_pending(user_id, "link_processing", link_import_job_id="78")
    bot.handle_social_link_import_worker_job_update(
        {"id": "78", "job_type": "social_link_import", "status": "running"},
        {"id": "78", "job_type": "social_link_import", "status": "failed", "user_id": user_id, "input_file_id": '{"user_id":"p011-link-fail"}'},
    )
    assert calls == []
    assert bot.get_video_dubbing_pending(user_id)["link_import_status"] == "failed"


def test_social_link_rights_notice():
    text = bot.social_link_import_confirm_text({"source_url": "https://youtu.be/x", "source_platform": "YouTube"}, "vi")
    assert "bạn có quyền sử dụng nội dung này".lower() in text.lower()


def test_subtitle_flow_no_voice_selection():
    labels = _labels(bot.video_dubbing_output_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}))
    assert "📄 Xuất SRT" in labels
    assert "🎞 Gắn vào video" in labels
    assert not any("giọng" in label.lower() for label in labels)


def test_subtitle_export_after_generation():
    callbacks = _callbacks(bot.video_dubbing_output_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}))
    assert "videodub|output|srt" in callbacks
    assert "videodub|output|burn" in callbacks
    assert "videodub|output|both" in callbacks


def test_subtitle_continue_to_dubbing_option():
    labels = _labels(bot.video_dubbing_preview_ready_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}))
    assert "🗣 Tiếp tục lồng tiếng" in labels


def test_translate_subtitle_no_voice_selection():
    labels = _labels(bot.video_dubbing_output_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE}))
    assert "📄 Xuất SRT" in labels
    assert "🗣 Lồng tiếng" in labels
    assert not any("giọng" in label.lower() for label in labels)


def test_translate_subtitle_export_before_dubbing():
    callbacks = _callbacks(bot.video_dubbing_output_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE}))
    assert "videodub|output|srt" in callbacks
    assert "videodub|preview" in callbacks
    assert "videodub|continue_dubbing" in callbacks


def test_translate_subtitle_language_selection():
    labels = _labels(bot.video_dubbing_language_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE}))
    assert "🇻🇳 Tiếng Việt" in labels
    assert "🇺🇸 Tiếng Anh" in labels
    assert "✍️ Nhập ngôn ngữ khác" in labels


def test_auto_dubbing_voice_selection_required():
    assert bot.video_dubbing_requires_voice(bot.VIDEO_SUBTITLE_MODE_DUB)
    labels = _labels(bot.video_dubbing_voice_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}))
    assert "👩 Giọng nữ" in labels
    assert "👨 Giọng nam" in labels
    assert "📁 Kho voice" in labels
    assert "🎙 Tạo voice" in labels


def test_auto_dubbing_voice_settings():
    labels = _labels(bot.video_dubbing_voice_settings_keyboard("vi"))
    assert "⏱ 1.0" in labels
    assert "⏱ 1.25" in labels
    assert "🔊 Âm gốc 30%" in labels
    assert "🔊 Âm gốc 50%" in labels


def test_auto_dubbing_itemized_invoice():
    text = bot.video_dubbing_confirm_text({"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "video_duration": 61, "voice_style": "Giọng nữ"}, "vi")
    assert "Phí xử lý nền" in text
    assert "Ước tính voice theo chữ" in text
    assert "Tổng phí dự kiến" in text


def test_translate_dub_translate_first_then_voice():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "target_language": "English"}
    labels = _labels(bot.video_dubbing_output_keyboard("vi", state))
    assert "📄 Xuất SRT" in labels
    assert "🗣 Lồng tiếng" in labels


def test_translate_dub_can_export_srt_before_voice():
    callbacks = _callbacks(bot.video_dubbing_output_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}))
    assert "videodub|output|srt" in callbacks
    assert "videodub|continue_dubbing" in callbacks


def test_subtitle_editor_line_number_edit():
    state = {"subtitle_draft": "Xin chào\nTạm biệt"}
    assert bot.subtitle_editor_replace_line(state, 2, "Hẹn gặp lại") == "Xin chào\nHẹn gặp lại"


def test_subtitle_editor_find_replace():
    state = {"subtitle_draft": "Xin chào\nXin cảm ơn"}
    assert bot.subtitle_editor_find_replace_text(state, "Xin", "Kính") == "Kính chào\nKính cảm ơn"


def test_subtitle_editor_save_draft():
    labels = _labels(bot.subtitle_editor_keyboard("vi"))
    assert "✅ Lưu phụ đề" in labels


def test_video_addon_translation_preserves_session():
    user_id = "p011-addon"
    bot.clear_video_finalization_state(user_id)
    bot.set_video_finalization_state(user_id, {"step": "menu", "video_project": {"source_file_id": "current-video"}, "source": "promptvideo"})
    updated = bot.apply_video_factory_to_finalization(user_id, {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "target_language": "English", "output_type": "srt"})
    finalization = updated["video_finalization"]
    assert finalization["translation_enabled"] is True
    assert finalization["subtitle_enabled"] is True
    assert updated["source"] == "promptvideo"


def test_video_addon_translation_returns_to_invoice_when_origin_invoice():
    user_id = "p011-addon-invoice"
    bot.clear_video_finalization_state(user_id)
    bot.set_video_finalization_state(user_id, {"step": "tier", "return_to_invoice": True})
    state = bot.get_video_finalization_state(user_id)
    assert state["return_to_invoice"] is True


def test_no_public_dich_long_tieng_slash_label():
    surfaces = "\n".join([
        bot.translation_menu_text("vi"),
        "\n".join(_labels(bot.video_dubbing_menu_keyboard("vi", "translation"))),
        bot.video_dubbing_pricing_text("vi"),
    ])
    assert "Dịch/Lồng tiếng" not in surfaces


def test_no_public_nghe_xem_combo():
    surfaces = "\n".join([
        bot.translation_menu_text("vi"),
        bot.video_dubbing_menu_text("vi", "translation"),
        "\n".join(_labels(bot.video_dubbing_confirm_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}))),
    ]).lower()
    assert "nghe/xem" not in surfaces


def test_no_public_provider_leak_translation_factory():
    surfaces = "\n".join([
        bot.social_link_import_text("vi"),
        bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, {}, "vi", admin=False),
        bot.translation_language_hub_text("vi"),
    ]).lower()
    for term in ("api", "provider", "key4u", "shopaikey", "minimax", "gemini", "admin blocker", "traceback", "ready=false"):
        assert term not in surfaces
