import asyncio
import html
from types import SimpleNamespace

import bot


class FakeMessage:
    chat_id = 180180

    async def reply_text(self, text, **kwargs):
        return SimpleNamespace(text=text, **kwargs)


class FakeQuery:
    def __init__(self, user_id: int, data: str):
        self.from_user = SimpleNamespace(id=user_id, first_name="P018K")
        self.data = data
        self.message = FakeMessage()
        self.answered = False
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answered = True

    async def edit_message_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.edits.append(item)
        return SimpleNamespace(**item)


class FakeCommandMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.replies.append(item)
        return SimpleNamespace(**item)


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _rows(markup):
    return [[button.text for button in row] for row in markup.inline_keyboard]


def _press(user_id: int, callback: str):
    query = FakeQuery(user_id, callback)
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(user_data={})
    if callback.startswith("vid3|"):
        asyncio.run(bot.handle_video_uiflow3_callback(update, context))
    elif callback.startswith("vproduct|"):
        asyncio.run(bot.handle_video_product_callback(update, context))
    elif callback.startswith("videoidea|"):
        asyncio.run(bot.handle_video_idea_callback(update, context))
    elif callback.startswith("vpromptlib|"):
        asyncio.run(bot.handle_video_prompt_library_callback(update, context))
    elif callback.startswith("vdownload|"):
        asyncio.run(bot.handle_video_downloader_callback(update, context))
    elif callback.startswith("vprofile|"):
        asyncio.run(bot.handle_video_profile_studio_callback(update, context))
    elif callback.startswith("videoedit|"):
        asyncio.run(bot.handle_video_editor_callback(update, context))
    elif callback.startswith("longvideo|"):
        asyncio.run(bot.handle_long_video_callback(update, context))
    elif callback.startswith("menu|"):
        asyncio.run(bot.handle_menu_callback(update, context))
    else:
        raise AssertionError(f"unsupported video callback {callback}")
    assert query.edits
    return query.edits[-1]["text"], query.edits[-1].get("reply_markup"), bot.get_video_session(user_id)


def test_video_menu_layout_groups_primary_products_above_helpers():
    assert _rows(bot.main_video_keyboard("vi")) == [
        ["🔥 Video theo trend", "🎬 Video AI chân thật"],
        ["🧩 Kịch bản → Video", "🎞 Ghép ảnh thành video"],
        ["🎥 Tự quay & đổi cảnh AI", "🎬 Video dài tập"],
        ["🎞 Storyboard", "💡 Ý tưởng video"],
        ["🛠️ Chỉnh sửa / Nâng cấp video", "📥 Tải video từ liên kết"],
        ["🏠 Menu chính", "📖 Hướng dẫn video"],
    ]


def test_video_route_matrix_matches_public_menu_buttons():
    payload = bot.video_route_audit_payload()
    assert payload["ok"] is True
    matrix_callbacks = [row["entry_callback"] for row in payload["rows"]]
    menu_callbacks = [callback for callback in _callbacks(bot.main_video_keyboard("vi")) if callback != "menu|main"]
    assert matrix_callbacks == menu_callbacks
    assert len(matrix_callbacks) == 11
    assert len(set(matrix_callbacks)) == len(matrix_callbacks)


def test_video_route_matrix_each_button_has_parent_and_back_target():
    for row in bot.video_route_matrix_rows():
        assert row["parent_menu"] == "menu|main_video", row
        assert row["back_target"] == "menu|main_video", row
        assert row["expected_handler"] == row["actual_handler"], row
        assert row["ok"] is True, row


def test_video_route_entry_context_is_saved_per_button():
    for index, route in enumerate(bot.video_route_matrix_rows(), start=1):
        user_id = 180000 + index
        text, markup, session = _press(user_id, route["entry_callback"])
        callbacks = _callbacks(markup)
        if route["video_tool"] == "multi_scene_film":
            assert "đang phát triển" in text
            assert not session
            assert callbacks == ["menu|main_video", "menu|main"]
            continue
        if route["video_tool"] == "video_guide":
            assert "video" in text.lower()
            assert "menu|main_video" in callbacks
            continue
        assert route["label"].split(" ", 1)[-1].split("→", 1)[0].strip()[:8] in text
        assert session.get("product_area") == "video"
        assert session.get("video_tool") == route["video_tool"]
        assert session.get("parent_menu") == "video_main"
        assert session.get("return_to") == "menu|main_video"
        expected_step = route["first_step"]
        assert session.get("flow_stack") == ["video_main", route["video_tool"], expected_step]
        assert "menu|main_video" in callbacks or "vproduct|back" in callbacks
        for child in route["expected_children"]:
            assert child in callbacks


def test_storyboard_is_image_required_planning_that_can_reach_confirmed_render():
    route = bot.video_public_route_for_tool("storyboard_prompt")
    assert route["category"] == "planning"
    assert route["invoice_reachable"] is True
    assert route["job_reachable"] is True
    text, markup, session = _press(180101, route["entry_callback"])
    callbacks = _callbacks(markup)
    assert "Storyboard" in text
    assert "vproduct|storyboard_manual|storyboard_prompt" in callbacks
    assert "vproduct|storyboard_suggest|storyboard_prompt" in callbacks
    assert "vproduct|b14_confirm" not in callbacks
    assert session.get("video_tool") == "storyboard_prompt"


def test_video_back_audit_and_route_audit_pass_text():
    assert "Status: <b>PASS</b>" in bot.video_route_audit_text()
    assert "Status: <b>PASS</b>" in bot.video_back_audit_text()
    assert "Video Route Matrix" in bot.video_route_matrix_text()


def test_video_public_forbidden_words_are_detected_and_not_in_menu_copy():
    detected = bot.video_public_text_forbidden_words("admin test provider API worker RuntimeError debug payload")
    for term in ("admin", "test", "provider", "API", "worker", "RuntimeError", "debug", "payload"):
        assert term in detected
    assert bot.video_public_text_forbidden_words(bot.menu_text_main_video()) == []
    assert bot.video_public_text_forbidden_words(bot.VIDEO_PUBLIC_CLEAN_FAIL_TEXT) == []


def test_video_audit_commands_are_admin_only_and_return_matrix(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda user_id: True)
    message = FakeCommandMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=180900), message=message)
    asyncio.run(bot.cmd_video_route_audit(update, SimpleNamespace()))
    asyncio.run(bot.cmd_video_route_matrix(update, SimpleNamespace()))
    asyncio.run(bot.cmd_video_back_audit(update, SimpleNamespace()))
    assert len(message.replies) == 3
    assert "Video Route Audit" in message.replies[0]["text"]
    assert "Video Route Matrix" in message.replies[1]["text"]
    assert "Video Back Audit" in message.replies[2]["text"]


def test_video_product_routes_do_not_jump_to_voice_music_translation():
    bad_prefixes = ("music_quick|", "sfx_quick|", "videodub|")
    for index, route in enumerate(bot.video_route_matrix_rows(), start=1):
        text, markup, _session = _press(181000 + index, route["entry_callback"])
        callbacks = _callbacks(markup)
        assert "menu|translate" not in callbacks
        assert "menu|main_music" not in callbacks
        assert not any(callback.startswith(bad_prefixes) for callback in callbacks)
        assert bot.video_public_text_forbidden_words(text) == []


def test_video_menu_buttons_have_registered_routes():
    for callback in _callbacks(bot.main_video_keyboard("vi")):
        if callback == "menu|main":
            continue
        assert bot.video_public_route_for_callback(callback), callback


def test_video_menu_buttons_have_unique_tool_ids():
    tool_ids = [row["video_tool"] for row in bot.video_route_matrix_rows()]
    assert len(tool_ids) == len(set(tool_ids))


def test_video_menu_entry_sets_video_context():
    _text, _markup, session = _press(181101, "vproduct|open|video_trend")
    assert session.get("product_area") == "video"
    assert session.get("video_tool") == "video_trend"
    assert session.get("parent_menu") == "video_main"


def test_every_video_tool_has_parent_video_menu():
    assert all(row["parent_menu"] == "menu|main_video" for row in bot.video_route_matrix_rows())


def test_every_video_tool_has_back_target():
    assert all(row["back_target"] == "menu|main_video" for row in bot.video_route_matrix_rows())


def test_back_from_each_tool_home_returns_video_menu():
    for row in bot.video_route_matrix_rows():
        assert row["back_target"] == "menu|main_video"


def test_menu_video_button_returns_video_menu():
    text, markup = bot.localized_menu_content("main_video", False, "vi", 181102)
    assert "Video TOAN AAS" in text
    assert _labels(markup) == _labels(bot.main_video_keyboard("vi"))


def test_menu_main_button_returns_main_menu(monkeypatch):
    monkeypatch.setattr(bot, "get_user", lambda user_id, username="Unknown": (0, 0, 0))
    text, markup = bot.localized_menu_content("main", False, "vi", 181103)
    assert "TOAN AAS" in text
    assert "menu|main_video" in _callbacks(markup)


def test_storyboard_prompt_does_not_jump_profile_flow():
    text, markup, session = _press(181104, "vproduct|open|storyboard_prompt")
    callbacks = _callbacks(markup)
    assert "Storyboard" in text
    assert session.get("video_tool") == "storyboard_prompt"
    assert not any("b14_profile" in callback for callback in callbacks)
    assert "vproduct|storyboard_manual|storyboard_prompt" in callbacks
    assert session.get("current_step") == "intro"


def test_storyboard_prompt_back_matrix():
    route = bot.video_public_route_for_tool("storyboard_prompt")
    assert route["back_target"] == "menu|main_video"
    text, markup, _session = _press(181105, route["entry_callback"])
    assert "menu|main_video" in _callbacks(markup)
    assert "Storyboard" in text


def test_storyboard_prompt_can_save_to_prompt_vault():
    callbacks = _callbacks(bot.task3d_result_keyboard("storyboard_prompt", "vi"))
    assert "vproduct|prompt_vault_save" in callbacks
    assert "vproduct|render" in callbacks


def test_video_ai_real_scene_count_back_target():
    callbacks = _callbacks(bot.video_b14_scene_count_keyboard(181106, "vi"))
    assert "vproduct|b14_quality_screen" in callbacks
    assert "menu|main" in callbacks
    assert "menu|translate" not in callbacks


def test_video_ai_logo_watermark_back_target():
    assert "vproduct|b14_addons" in _callbacks(bot.video_b14_logo_keyboard("vi"))
    assert "vproduct|b14_addon_logo" in _callbacks(bot.video_b14_logo_position_keyboard("vi"))
    assert "vproduct|b14_logo_position_screen" in _callbacks(bot.video_b14_logo_confirm_keyboard("vi"))


def test_video_ai_logo_watermark_does_not_call_admin_test_path():
    logo_callbacks = (
        _callbacks(bot.video_b14_logo_keyboard("vi"))
        + _callbacks(bot.video_b14_logo_position_keyboard("vi"))
        + _callbacks(bot.video_b14_logo_confirm_keyboard("vi"))
    )
    assert not any("admin" in callback.lower() or "test" in callback.lower() for callback in logo_callbacks)


def test_multiscene_product_does_not_show_admin_test_public_copy():
    text, _markup, _session = _press(181107, "vproduct|open|multi_scene_film")
    assert "Video dài tập" in text
    assert bot.video_public_text_forbidden_words(text) == []


def test_multiscene_product_uses_product_route_not_admin_smoke():
    route = bot.video_public_route_for_tool("multi_scene_film")
    assert route["entry_callback"] == "longvideo|public_guard"
    assert route["flow_type"] == "development_guard"
    assert route["job_reachable"] is False
    assert "admin" not in route["entry_callback"].lower()
    assert "smoke" not in route["entry_callback"].lower()


def test_image_to_video_route_stays_image_to_video():
    text, markup, session = _press(181108, "vproduct|open|frame_video_local")
    callbacks = _callbacks(markup)
    assert "Ghép ảnh thành video" in text
    assert session.get("video_tool") == "frame_video_local"
    assert "framevideo|start" in callbacks
    assert "framevideo|ai_first" in callbacks
    assert "promptvideo|start" not in callbacks
    assert "vproduct|open|storyboard_prompt" not in callbacks
    assert "vproduct|open|video_ai_real" not in callbacks


def test_self_shot_route_preserves_draft():
    user_id = 181109
    bot.set_developing_video_pending(user_id, "selfscene", "object", source_file_id="video-file-1", subject_kind="person")
    _text, _markup, session = _press(user_id, "vproduct|open|self_shot_scene_change")
    pending = bot.get_developing_video_pending(user_id) or {}
    assert pending.get("step") == "object"
    assert pending.get("source_file_id") == "video-file-1"
    assert session.get("video_tool") == "self_shot_scene_change"


def test_local_edit_missing_worker_public_copy_clean():
    text = bot.video_editor_public_guard_text("vi")
    assert "Chỉnh sửa video" in text
    assert bot.video_public_text_forbidden_words(text) == []


def test_download_link_back_returns_video_menu():
    _text, markup, session = _press(181110, "vdownload|start")
    assert "menu|main_video" in _callbacks(markup)
    assert session.get("video_tool") == "video_downloader"


def test_no_public_forbidden_words_in_video_flows():
    public_texts = [
        bot.menu_text_main_video(),
        bot.VIDEO_PUBLIC_CLEAN_FAIL_TEXT,
        bot.video_editor_public_guard_text("vi"),
        bot.frame_video_job_status_text({"job_id": "p018k", "status": "failed", "image_count": 2, "charged_amount": 0}),
    ]
    for text in public_texts:
        assert bot.video_public_text_forbidden_words(text) == []


def test_video_route_audit_command_lists_all_buttons(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda user_id: True)
    message = FakeCommandMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=181111), message=message)
    asyncio.run(bot.cmd_video_route_audit(update, SimpleNamespace()))
    text = message.replies[-1]["text"]
    for row in bot.video_route_matrix_rows():
        assert html.escape(row["label"]) in text


def test_video_route_audit_detects_missing_handler(monkeypatch):
    broken = dict(bot.VIDEO_PUBLIC_ROUTE_MATRIX["video_trend"])
    broken["handler"] = "missing_handler"
    monkeypatch.setitem(bot.VIDEO_PUBLIC_ROUTE_MATRIX, "video_trend", broken)
    payload = bot.video_route_audit_payload()
    assert payload["ok"] is False
    assert any(row["video_tool"] == "video_trend" and not row["ok"] for row in payload["rows"])


def test_video_back_audit_all_pass():
    assert "Status: <b>PASS</b>" in bot.video_back_audit_text()


def test_no_engine_provider_changes():
    import inspect

    source = inspect.getsource(bot.video_route_matrix_rows) + inspect.getsource(bot.main_video_keyboard)
    for term in ("render_real_video", "video_project_real_scene_renderer", "submit_video", "poll_video"):
        assert term not in source


def test_no_voice_music_subtitle_payos_changes():
    import inspect

    source = inspect.getsource(bot.video_route_matrix_rows) + inspect.getsource(bot.set_video_route_session)
    for term in ("payos", "wallet", "suno", "voice_clone", "subtitle_dub"):
        assert term not in source.lower()
