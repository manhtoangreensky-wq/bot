import bot


def test_video_session_push_pop_preserves_draft_and_order():
    user_id = 992401
    bot.clear_video_session(user_id)
    bot.go_video_screen(user_id, "promptvideo:prompt", "promptvideo", prompt="A product reveal")
    bot.go_video_screen(user_id, "video_finalization", "video_finalization")
    bot.go_video_screen(user_id, "videoaddon:video_addon_menu", "video_finalization")

    session = bot.get_video_session(user_id)
    assert session["draft"]["prompt"] == "A product reveal"
    assert session["current_screen"] == "videoaddon:video_addon_menu"
    assert bot.pop_video_screen(user_id) == "video_finalization"
    assert bot.get_video_session(user_id)["draft"]["prompt"] == "A product reveal"
    bot.clear_video_session(user_id)


def test_video_addon_state_syncs_video_order_to_shared_session():
    user_id = 992402
    bot.clear_video_addon_state(user_id)
    bot.clear_video_session(user_id)
    state = bot.set_video_addon_state(user_id, {
        "source": "ai",
        "video_tier": "basic",
        "pending_payload": {"video_tier": "basic", "video_prompt": "Ready"},
    })
    state = bot.set_video_addon_screen(user_id, state, "addon_language")

    session = bot.get_video_session(user_id)
    assert session["current_screen"] == "videoaddon:addon_language"
    assert session["order"]["current_screen"] == "addon_language"
    assert session["draft"]["video_tier"] == "basic"
    bot.clear_video_addon_state(user_id)
    bot.clear_video_session(user_id)


def test_video_order_back_is_one_screen_at_a_time():
    order = bot.video_order_create(992403, "basic")
    order = bot.video_order_push_screen(order, "addon_language")
    order = bot.video_order_push_screen(order, "addon_voice")
    order = bot.video_order_push_screen(order, "invoice")

    order = bot.video_order_back_screen(order)
    assert order["current_screen"] == "addon_voice"
    order = bot.video_order_back_screen(order)
    assert order["current_screen"] == "addon_language"
    order = bot.video_order_back_screen(order)
    assert order["current_screen"] == "video_addon_menu"


def test_video_addon_keyboards_use_two_columns_and_real_back():
    for markup in (
        bot.video_addon_menu_keyboard("vi", {"video_tier": "basic"}),
        bot.video_addon_language_keyboard("vi"),
        bot.video_addon_voice_keyboard("vi"),
    ):
        assert all(len(row) <= 2 for row in markup.inline_keyboard)
    language_callbacks = {
        button.callback_data
        for row in bot.video_addon_language_keyboard("vi").inline_keyboard
        for button in row
    }
    assert "videoaddon|back" in language_callbacks
    assert "videoaddon|menu" not in language_callbacks


def test_self_scene_starts_with_source_video_gate():
    labels = [
        button.text
        for row in bot.self_scene_upload_keyboard("vi", False).inline_keyboard
        for button in row
    ]
    callbacks = {
        button.callback_data
        for row in bot.self_scene_upload_keyboard("vi", False).inline_keyboard
        for button in row
    }
    assert "📎 Tôi sẽ gửi video" in labels
    assert "✍️ Lập kế hoạch trước" not in labels
    assert "selfscene|await_video" in callbacks
    assert "selfscene|plan_without_video" not in callbacks
    assert "chưa xử lý video và chưa trừ Xu" in bot.self_scene_upload_text("vi")
