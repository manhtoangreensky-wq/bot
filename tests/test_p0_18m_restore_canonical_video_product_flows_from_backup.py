import asyncio
from types import SimpleNamespace

import bot
import video_image_to_video_flow as ivf


class FakeMessage:
    chat_id = 180180

    async def reply_text(self, text, **kwargs):
        return SimpleNamespace(text=str(text), **kwargs)


class FakeQuery:
    def __init__(self, user_id: int, data: str):
        self.from_user = SimpleNamespace(id=user_id, first_name="P018M")
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


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _rows(markup):
    return [[button.text for button in row] for row in markup.inline_keyboard]


def _press(user_id: int, callback: str):
    query = FakeQuery(user_id, callback)
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(user_data={})
    if callback.startswith("vproduct|"):
        asyncio.run(bot.handle_video_product_callback(update, context))
    elif callback.startswith("videoidea|"):
        asyncio.run(bot.handle_video_idea_callback(update, context))
    elif callback.startswith("framevideo|"):
        asyncio.run(bot.handle_frame_video_callback(update, context))
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
    else:
        raise AssertionError(f"unsupported callback {callback}")
    assert query.edits
    edit = query.edits[-1]
    return edit["text"], edit.get("reply_markup"), bot.get_video_session(user_id)


def _start_trend(user_id: int = 180001):
    bot.clear_video_session(user_id)
    return _press(user_id, "vproduct|open|video_trend")


def test_video_menu_layout_preserved_after_p0_18m():
    assert _rows(bot.main_video_keyboard("vi")) == [
        ["🔥 Video theo trend", "🎬 Video AI chân thật"],
        ["🧩 Kịch bản → Video", "🎞 Ghép ảnh thành video"],
        ["🎥 Tự quay & đổi cảnh AI", "🎬 Video dài tập"],
        ["🎯 Studio Profile AI", "🎞 Storyboard"],
        ["💡 Ý tưởng video", "🛠 Chỉnh sửa video"],
        ["📥 Tải video từ liên kết"],
        ["🏠 Menu chính", "📖 Hướng dẫn video"],
    ]


def test_video_ai_real_not_default_canonical_flow():
    assert bot.video_public_route_for_tool("video_ai_real").get("canonical") is False
    text, markup, session = _press(180002, "vproduct|open|video_ai_real")
    callbacks = _callbacks(markup)
    assert "Video AI chân thật" in text
    assert "vproduct|ai_prompt_menu|video_ai_real" in callbacks
    assert "vproduct|ai_image_menu|video_ai_real" in callbacks
    assert "vproduct|ai_video_menu|video_ai_real" in callbacks
    assert "vproduct|b14_profile|storytelling" not in callbacks
    assert session.get("video_tool") == "video_ai_real"


def test_video_trend_is_canonical_flow():
    route = bot.video_public_route_for_tool("video_trend")
    assert route.get("canonical") is True
    assert route.get("flow_type") == "trend_first"


def test_video_trend_starts_initial_suggestions():
    text, markup, session = _start_trend(180003)
    callbacks = _callbacks(markup)
    assert "Video theo trend" in text
    assert "Chọn loại video" not in text
    assert "vproduct|trend_today" in callbacks
    assert "vproduct|trend_custom" in callbacks
    assert session.get("current_step") == "intro"
    assert session.get("flow_stack") == ["video_main", "video_trend", "intro"]


def test_video_trend_profile_then_topic():
    user_id = 180004
    _start_trend(user_id)
    _press(user_id, "vproduct|trend_today")
    _press(user_id, "vproduct|trend_select|0")
    text, markup, session = _press(user_id, "vproduct|b14_profile|product_review")
    callbacks = _callbacks(markup)
    assert "Gợi ý ý tưởng" in text
    assert "vproduct|b14_idea_select|0" in callbacks
    assert session.get("current_step") == "idea_suggestions"


def test_video_trend_generates_suggestions():
    user_id = 180005
    _start_trend(user_id)
    _press(user_id, "vproduct|trend_today")
    _press(user_id, "vproduct|trend_select|0")
    _press(user_id, "vproduct|b14_profile|product_review")
    text, markup, session = _press(user_id, "vproduct|ideas|video_trend")
    callbacks = _callbacks(markup)
    assert "Gợi ý ý tưởng" in text
    assert "vproduct|b14_idea_select|0" in callbacks
    assert session.get("current_step") == "idea_suggestions"
    assert session["draft"]["provider_called"] is False


def test_video_trend_suggestion_then_image_choice():
    user_id = 180006
    _start_trend(user_id)
    _press(user_id, "vproduct|trend_today")
    _press(user_id, "vproduct|trend_select|0")
    _press(user_id, "vproduct|b14_profile|product_review")
    _press(user_id, "vproduct|ideas|video_trend")
    text, markup, session = _press(user_id, "vproduct|b14_idea_select|0")
    callbacks = _callbacks(markup)
    assert "gửi ảnh" in text.lower() or "ảnh" in text.lower()
    for callback in ("vproduct|asset_wait|subject", "vproduct|asset_create_ai_image", "vproduct|asset_layout_ideas", "vproduct|asset_storyboard_prompt"):
        assert callback in callbacks
    assert session.get("current_step") == "asset_intake"


def test_video_trend_create_ai_image_not_placeholder_when_handler_exists():
    user_id = 180007
    _start_trend(user_id)
    _press(user_id, "vproduct|trend_today")
    _press(user_id, "vproduct|trend_select|0")
    _press(user_id, "vproduct|b14_profile|product_review")
    _press(user_id, "vproduct|ideas|video_trend")
    _press(user_id, "vproduct|b14_idea_select|0")
    text, markup, session = _press(user_id, "vproduct|asset_create_ai_image")
    assert "Tạo ảnh AI trước" in text
    assert "đang được chuẩn bị" not in text
    assert "menu|main_image" in _callbacks(markup)
    assert session.get("current_step") == "asset_ai_image"


def test_video_trend_my_images_routes_upload():
    user_id = 180008
    _start_trend(user_id)
    _press(user_id, "vproduct|trend_today")
    _press(user_id, "vproduct|trend_select|0")
    _press(user_id, "vproduct|b14_profile|product_review")
    _press(user_id, "vproduct|ideas|video_trend")
    _press(user_id, "vproduct|b14_idea_select|0")
    text, markup, session = _press(user_id, "vproduct|asset_wait|subject")
    assert "gửi file" in text.lower()
    assert session.get("draft", {}).get("asset_waiting_for") == "subject"
    assert "vproduct|asset_intro" in _callbacks(markup)


def test_video_trend_layout_suggestion_routes():
    user_id = 180009
    _start_trend(user_id)
    _press(user_id, "vproduct|trend_today")
    _press(user_id, "vproduct|trend_select|0")
    _press(user_id, "vproduct|b14_profile|product_review")
    _press(user_id, "vproduct|ideas|video_trend")
    _press(user_id, "vproduct|b14_idea_select|0")
    text, markup, session = _press(user_id, "vproduct|asset_layout_ideas")
    assert "Gợi ý bố cục ảnh" in text
    assert "vproduct|asset_wait|subject" in _callbacks(markup)
    assert session.get("current_step") == "asset_layout_ideas"


def test_video_trend_back_routing_matrix():
    route = bot.video_public_route_for_tool("video_trend")
    assert route["parent_menu"] == "menu|main_video"
    assert route["back_target"] == "menu|main_video"
    assert bot.video_route_session_fields("video_trend", "profile_select")["flow_stack"] == ["video_main", "video_trend", "profile_select"]


def test_frame_video_button_routes_real_flow():
    text, markup, session = _press(180010, "vproduct|open|frame_video_local")
    callbacks = _callbacks(markup)
    assert "Ghép ảnh thành video" in text
    assert "framevideo|start" in callbacks
    assert "framevideo|ai_first" in callbacks
    assert "vproduct|open|storyboard_prompt" not in callbacks
    assert "vproduct|open|video_ai_real" not in callbacks
    assert session.get("video_tool") == "frame_video_local"


def test_frame_video_collects_images(monkeypatch):
    user_id = 180011
    monkeypatch.setattr(bot, "FRAME_VIDEO_ENABLED", True)
    monkeypatch.setattr(bot, "FRAME_VIDEO_PUBLIC_ENABLED", True)
    bot.clear_frame_video_state(user_id)
    text, _markup, _session = _press(user_id, "framevideo|start")
    state = bot.get_frame_video_state(user_id)
    assert state["step"] == "collect"
    assert state["source"] == "existing_images"
    assert "Gửi từ 2 đến" in text


def test_frame_video_package_confirm_before_render(monkeypatch):
    user_id = 180012
    monkeypatch.setattr(bot, "shopaikey_preview_final_cost", lambda _uid, base_cost, _event_type: int(base_cost or 0))
    bot.set_frame_video_state(user_id, {"step": "effect", "photos": [{"file_id": "a"}, {"file_id": "b"}]})
    text, _markup, _session = _press(user_id, "framevideo|effect|default")
    state = bot.get_frame_video_state(user_id)
    assert state["step"] == "confirm"
    assert "xác nhận" in text.lower()


def test_frame_video_no_placeholder_if_handler_exists():
    text, markup, _session = _press(180013, "framevideo|ai_first")
    assert "đang được chuẩn bị" not in text
    callbacks = _callbacks(markup)
    assert "framevideo|ai_prompt" in callbacks
    assert "framevideo|start" in callbacks
    assert "vproduct|open|storyboard_prompt" not in callbacks
    assert "vproduct|open|video_ai_real" not in callbacks


def test_script_to_video_splits_scenes():
    user_id = 180014
    _press(user_id, "vproduct|open|script_image_video")
    _press(user_id, "vproduct|ideas|script_image_video")
    _press(user_id, "vproduct|b14_profile|product_review")
    _press(user_id, "vproduct|panels|6")
    _press(user_id, "vproduct|style|default")
    _press(user_id, "vproduct|color|warm")
    _press(user_id, "vproduct|image_plan|skip")
    _press(user_id, "vproduct|scene_skip")
    text, _markup, session = _press(user_id, "vproduct|b14_creative_done")
    assert "Storyboard" in text or "Cảnh" in text
    assert session.get("draft", {}).get("b14_storyboard_plan")


def test_script_to_video_does_not_jump_to_text_to_video_default():
    text, markup, session = _press(180015, "vproduct|open|script_image_video")
    callbacks = _callbacks(markup)
    assert "Kịch bản" in text
    assert "promptvideo|start" not in callbacks
    assert session.get("product_id") == "script_image_video"


def test_script_to_video_can_continue_to_storyboard_or_render():
    callbacks = _callbacks(bot.task3d_result_keyboard("script_image_video", "vi"))
    assert "vproduct|prompt_image" in callbacks
    assert "vproduct|prompt_video" in callbacks
    assert "vproduct|render" in callbacks


def test_multiscene_flow_restored():
    text, markup, session = _press(180016, "vproduct|open|multi_scene_film")
    callbacks = _callbacks(markup)
    assert "Video dài tập" in text
    assert "đang phát triển" in text
    assert callbacks == ["menu|main_video", "menu|main"]
    assert not session


def test_multiscene_addon_package_confirm_order():
    addon_callbacks = _callbacks(bot.video_b14_addon_keyboard("vi"))
    assert "vproduct|b14_addon_done" in addon_callbacks
    scene_callbacks = _callbacks(bot.video_b14_scene_count_keyboard(180017, "vi"))
    assert "vproduct|b14_scene_count|3" in scene_callbacks
    invoice_callbacks = _callbacks(bot.video_b14_invoice_keyboard("vi"))
    assert "vproduct|b14_confirm" in invoice_callbacks


def test_self_shot_flow_session_preserved():
    user_id = 180018
    bot.set_developing_video_pending(user_id, "selfscene", "object", source_file_id="self-video")
    _press(user_id, "vproduct|open|self_shot_scene_change")
    pending = bot.get_developing_video_pending(user_id)
    assert pending.get("step") == "object"
    assert pending.get("source_file_id") == "self-video"


def test_self_shot_back_routing_preserved():
    route = bot.video_public_route_for_tool("self_shot_scene_change")
    assert route["parent_menu"] == "menu|main_video"
    assert route["back_target"] == "menu|main_video"


def test_storyboard_prompt_does_not_auto_render():
    text, markup, session = _press(180019, "vproduct|open|storyboard_prompt")
    callbacks = _callbacks(markup)
    assert "Storyboard" in text
    assert "vproduct|storyboard_manual|storyboard_prompt" in callbacks
    assert "vproduct|storyboard_suggest|storyboard_prompt" in callbacks
    assert "vproduct|b14_confirm" not in callbacks
    assert session["draft"]["provider_called"] is False


def test_storyboard_prompt_save_to_vault():
    assert "vproduct|prompt_vault_save" in _callbacks(bot.task3d_result_keyboard("storyboard_prompt", "vi"))


def test_storyboard_prompt_use_prompt_this():
    assert "vproduct|prompt_image" in _callbacks(bot.task3d_result_keyboard("storyboard_prompt", "vi"))
    assert "vproduct|prompt_video" in _callbacks(bot.task3d_result_keyboard("storyboard_prompt", "vi"))


def test_video_prompt_vault_routes_real_search():
    text, markup, session = _press(180020, "vpromptlib|idea")
    callbacks = _callbacks(markup)
    assert "Prompt từ ý tưởng" in text
    assert any(callback.startswith("vpromptlib|use|idea|") for callback in callbacks)
    assert "đang được hoàn thiện" not in text
    assert session.get("video_tool") == "prompt_library"


def test_video_prompt_vault_use_prompt_routes_back_to_video():
    _press(180021, "vpromptlib|idea")
    text, markup, session = _press(180021, "vpromptlib|use|idea|1")
    assert "Đã dùng câu lệnh từ Kho mẫu ý tưởng" in text
    assert "vproduct|prompt_image" in _callbacks(markup)
    assert session.get("return_to") == "menu|main_video"
    assert session.get("product_id") in bot.VIDEO_PRODUCT_REGISTRY


def test_video_local_edit_routes_to_local1_hub():
    text, markup, session = _press(180022, "videoedit|hub")
    callbacks = _callbacks(markup)
    assert "Chỉnh sửa video" in text
    assert callbacks == ["videoedit|ai", "videoedit|manual", "videoedit|split", "menu|main_video"]
    assert "hiện không thu Xu" in text
    assert session.get("video_tool") == "video_local_edit"


def test_video_public_no_admin_test_words():
    texts = [bot.menu_text_main_video(), bot.video_placeholder_audit_text()]
    assert all("Admin test" not in text and "admin test" not in text.lower() for text in texts)


def test_video_public_no_local_worker_leak():
    texts = [ivf.frame_video_unified_menu_text("vi"), bot.video_editor_public_guard_text("vi"), bot.VIDEO_PUBLIC_CLEAN_FAIL_TEXT]
    assert all("local_worker" not in text and "Local Worker" not in text for text in texts)


def test_video_public_no_provider_leak():
    texts = [
        bot.video_b14_profile_selection_text({"product_id": "video_trend", "draft": {"product_id": "video_trend"}}, 0, "vi"),
        ivf.frame_video_ai_first_guard_text("vi"),
        bot.video_prompt_library_category_text("idea", bot.video_prompt_library_search("idea", 3), "vi"),
        bot.video_ai_true_text("vi"),
    ]
    for text in texts:
        assert not bot.video_public_text_forbidden_words(text), text


def test_video_no_fake_success():
    text = bot.frame_video_job_status_text({"job_id": "fv-p018m", "status": "failed", "image_count": 3, "charged_amount": 0})
    assert "chưa ghép được" in text
    assert "đã hoàn tất" not in text
    assert "Hệ thống chưa trừ Xu" in text


def test_video_no_xu_before_final_confirm():
    user_id = 180023
    _start_trend(user_id)
    _press(user_id, "vproduct|b14_profile|product_review")
    _press(user_id, "vproduct|ideas|video_trend")
    _press(user_id, "vproduct|b14_idea_select|0")
    session = bot.get_video_session(user_id)
    assert session["draft"]["provider_called"] is False
    assert session["draft"]["xu_charged"] == 0


def test_video_flow_audit_and_placeholder_audit_pass():
    assert bot.video_flow_audit_payload()["ok"] is True
    assert bot.video_placeholder_audit_payload()["ok"] is True
