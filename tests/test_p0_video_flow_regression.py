import inspect

import bot


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def test_public_video_queue_copy_is_clean():
    text = bot.ui_text("vi", "video.queue_submitted", task_id="task_123", auto_poll="ON")
    assert text == "TOAN AAS đang tạo video cho bạn. Vui lòng chờ, hệ thống sẽ gửi kết quả khi hoàn tất."
    for forbidden in ("Provider", "ShopAIKey", "User", "Job", "Task", "task_123", "Auto poll", "provider", "job", "task"):
        assert forbidden not in text


def test_public_video_submitted_keyboard_hides_shopaikey_status():
    labels = _labels(bot.public_video_submitted_keyboard("task_123", "vi", {"provider_route": "shopaikey"}, public_user=True))
    callbacks = _callbacks(bot.public_video_submitted_keyboard("task_123", "vi", {"provider_route": "shopaikey"}, public_user=True))
    assert "🔄 Kiểm tra trạng thái video" in labels
    assert "🏠 Menu chính" in labels
    assert not any("ShopAIKey" in label for label in labels)
    assert callbacks == ["shopai_video_job|task_123", "shopai_video_job|main"]


def test_public_video_submit_forces_public_keyboard_even_for_admin_flow():
    source = inspect.getsource(bot.handle_shopaikey_public_callback)
    assert "public_user=not is_admin_user(uid)" not in source
    assert "public_user=True" in source
    assert "Provider đã nhận gói Video 200 Xu" not in source
    assert "• User:" not in source
    assert "• Job:" not in source
    assert "• Task:" not in source


def test_multiscene_guard_copy_is_clean_and_no_provider_terms():
    text = bot.VIDEO_MULTISCENE_PUBLIC_GUARD_TEXT
    assert text == "Tạo video nhiều cảnh đang được kiểm tra. TOAN AAS chưa xử lý và chưa trừ Xu. Vui lòng thử lại sau."
    for forbidden in ("kiểm thử", "provider", "chi phí", "ShopAIKey", "Job", "Task", "User", "task_id", "user_id", "API"):
        assert forbidden not in text


def test_video_200_exports_without_paid_addons():
    state = {
        "source": "ai",
        "video_tier": "low",
        "selected_scene_count": 1,
        "pending_payload": {"job_type": "video", "video_tier": "low", "base_cost": 200, "music_option": "none"},
        "current_video_price_preview": {"total_xu": 200, "raw_total_xu": 200, "addon_xu": 0},
    }
    quote = bot.calculate_video_quote(state)
    classified = bot.classify_video_addons_for_package(state)
    assert quote["is_package_200_valid"] is True
    assert quote["scene_count"] == 1
    assert quote["total_xu"] == 200
    assert classified["allowed_for_200"] is True
    assert classified["paid_addons"] == []
    assert bot.validate_video_tier_selection(state, "low")["ok"] is True


def test_video_200_not_blocked_by_free_logo_watermark():
    state = {
        "source": "ai",
        "video_tier": "low",
        "selected_scene_count": 1,
        "pending_payload": {"job_type": "video", "video_tier": "low", "base_cost": 200, "music_option": "none"},
        "video_finalization": bot.logo_watermark_session_fields(True, "TOAN AAS", "bottom_right"),
        "current_video_price_preview": {"total_xu": 200, "raw_total_xu": 200, "addon_xu": 0},
    }
    quote = bot.calculate_video_quote(state)
    classified = bot.classify_video_addons_for_package(state)
    assert quote["is_package_200_valid"] is True
    assert quote["addon_fee_xu"] == 0
    assert classified["allowed_for_200"] is True
    assert classified["paid_addons"] == []


def test_video_200_not_blocked_by_unconfirmed_draft_addon():
    state = {
        "source": "ai",
        "video_tier": "low",
        "selected_scene_count": 1,
        "pending_payload": {"job_type": "video", "video_tier": "low", "base_cost": 200, "music_option": "none"},
        "video_finalization": {
            "music_enabled": False,
            "music_prompt": "draft only, not confirmed",
            "voice_enabled": False,
            "voice_text": "draft only, not confirmed",
            "subtitle_enabled": False,
            "subtitle_text": "draft only, not confirmed",
            "finalization_confirmed": False,
        },
        "current_video_price_preview": {"total_xu": 200, "raw_total_xu": 200, "addon_xu": 0},
    }
    quote = bot.calculate_video_quote(state)
    classified = bot.classify_video_addons_for_package(state)
    assert quote["is_package_200_valid"] is True
    assert classified["allowed_for_200"] is True
    assert classified["paid_addons"] == []


def test_video_tools_continue_button_and_two_column_layout():
    labels = _labels(bot.video_finalization_menu_keyboard("vi"))
    callbacks = _callbacks(bot.video_finalization_menu_keyboard("vi"))
    assert "🎚 Chọn chất lượng video" in labels
    assert "vfinal|tier" in callbacks
    first_rows = bot.video_finalization_menu_keyboard("vi").inline_keyboard[:4]
    assert all(len(row) == 2 for row in first_rows)
