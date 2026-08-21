import asyncio
from types import SimpleNamespace

import bot


class FakeMessage:
    chat_id = 181800

    def __init__(self, text: str = ""):
        self.text = text
        self.photo = None
        self.video = None
        self.document = None
        self.replies = []

    async def reply_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.replies.append(item)
        return SimpleNamespace(**item)


class FakeQuery:
    def __init__(self, user_id: int, data: str):
        self.from_user = SimpleNamespace(id=user_id, first_name="P018N")
        self.data = data
        self.message = FakeMessage()
        self.edits = []
        self.answered = False

    async def answer(self, *args, **kwargs):
        self.answered = True

    async def edit_message_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.edits.append(item)
        return SimpleNamespace(**item)


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


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
    else:
        raise AssertionError(f"unsupported callback {callback}")
    assert query.edits
    edit = query.edits[-1]
    return edit["text"], edit.get("reply_markup"), bot.get_video_session(user_id)


def _open(user_id: int, product_id: str):
    bot.clear_video_session(user_id)
    return _press(user_id, f"vproduct|open|{product_id}")


def _send_text(user_id: int, text: str):
    message = FakeMessage(text)
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id))
    handled = asyncio.run(bot.handle_video_product_pending_text(update, SimpleNamespace()))
    assert handled is True
    assert message.replies
    reply = message.replies[-1]
    return reply["text"], reply.get("reply_markup"), bot.get_video_session(user_id)


def test_video_menu_layout_preserved():
    assert _rows(bot.main_video_keyboard("vi")) == [
        ["🔥 Video theo trend", "🎬 Video AI chân thật"],
        ["🧩 Kịch bản → Video", "🎞 Ghép ảnh thành video"],
        ["🎥 Tự quay & đổi cảnh AI", "🎬 Video dài tập"],
        ["🎞 Storyboard", "💡 Ý tưởng video"],
        ["🛠 Chỉnh sửa video", "📥 Tải video từ liên kết"],
        ["🏠 Menu chính", "📖 Hướng dẫn video"],
    ]


def test_video_each_button_has_unique_flow():
    seen = set()
    for row in bot.video_route_matrix_rows():
        tool = row["video_tool"]
        assert tool not in seen
        seen.add(tool)
        assert row["entry_callback"]
        assert row["first_step"]
        assert row["parent_menu"] == "menu|main_video"
        assert row["back_target"] == "menu|main_video"


def test_video_ai_real_not_default():
    assert bot.video_public_route_for_tool("video_ai_real")["canonical"] is False
    assert bot.video_public_route_for_tool("video_trend")["canonical"] is True


def test_trend_flow_starts_initial_suggestions():
    text, markup, session = _open(181801, "video_trend")
    assert "Video theo trend" in text
    assert "Chọn loại video" not in text
    assert session["current_step"] == "intro"
    assert session["video_flow"] == "video_trend"
    assert "vproduct|trend_today" in _callbacks(markup)


def test_trend_profile_to_idea():
    user_id = 181802
    _open(user_id, "video_trend")
    _press(user_id, "vproduct|trend_today")
    _press(user_id, "vproduct|trend_select|0")
    text, markup, session = _press(user_id, "vproduct|b14_profile|product_review")
    assert "Gợi ý ý tưởng" in text
    assert session["current_step"] == "idea_suggestions"
    assert "vproduct|b14_idea_select|0" in _callbacks(markup)


def test_trend_idea_to_suggestions():
    user_id = 181803
    _open(user_id, "video_trend")
    _press(user_id, "vproduct|trend_today")
    _press(user_id, "vproduct|trend_select|0")
    _press(user_id, "vproduct|b14_profile|product_review")
    text, markup, session = _press(user_id, "vproduct|ideas|video_trend")
    assert "Gợi ý ý tưởng" in text
    assert session["current_step"] == "idea_suggestions"
    assert "vproduct|b14_idea_select|0" in _callbacks(markup)


def test_trend_suggestions_to_assets():
    user_id = 181804
    _open(user_id, "video_trend")
    _press(user_id, "vproduct|trend_today")
    _press(user_id, "vproduct|trend_select|0")
    _press(user_id, "vproduct|b14_profile|product_review")
    _press(user_id, "vproduct|ideas|video_trend")
    text, markup, session = _press(user_id, "vproduct|b14_idea_select|0")
    assert session["current_step"] == "asset_intake"
    assert "vproduct|asset_wait|subject" in _callbacks(markup)
    assert "ảnh" in text.lower()


def test_trend_assets_back_to_suggestions():
    user_id = 181805
    _open(user_id, "video_trend")
    _press(user_id, "vproduct|trend_today")
    _press(user_id, "vproduct|trend_select|0")
    _press(user_id, "vproduct|b14_profile|product_review")
    _press(user_id, "vproduct|ideas|video_trend")
    _press(user_id, "vproduct|b14_idea_select|0")
    text, _markup, session = _press(user_id, "vproduct|back")
    assert session["current_step"] == "idea_suggestions"
    assert "Gợi ý ý tưởng" in text


def test_trend_back_stack_no_double_back_needed():
    user_id = 181806
    _open(user_id, "video_trend")
    _press(user_id, "vproduct|trend_today")
    _press(user_id, "vproduct|trend_select|0")
    _press(user_id, "vproduct|b14_profile|product_review")
    text, _markup, session = _press(user_id, "vproduct|back")
    assert session["current_step"] == "profile_select"
    assert "Chọn loại video" in text
    text, _markup, session = _press(user_id, "vproduct|back")
    assert session["current_step"] == "trend_ideas"
    assert "trend" in text.lower()


def test_idea_flow_starts_intro():
    text, markup, session = _open(181807, "video_idea")
    assert "Ý tưởng video" in text
    assert "Chọn loại video" not in text
    assert session["current_step"] == "intro"
    assert "vproduct|idea_quick|video_idea" in _callbacks(markup)


def test_idea_flow_quick_options_before_development_path():
    user_id = 181808
    _open(user_id, "video_idea")
    text, markup, session = _press(user_id, "vproduct|idea_quick|video_idea")
    assert session["current_step"] == "idea_suggestions"
    assert "vproduct|microflow_choose|0" in _callbacks(markup)
    assert "vproduct|microflow_choose|4" in _callbacks(markup)
    assert "Gợi ý ý tưởng" in text


def test_idea_flow_back_matrix():
    user_id = 181809
    _open(user_id, "video_idea")
    _press(user_id, "vproduct|idea_quick|video_idea")
    _press(user_id, "vproduct|microflow_choose|0")
    text, _markup, session = _press(user_id, "vproduct|back")
    assert session["current_step"] == "idea_suggestions"
    assert "Gợi ý ý tưởng" in text
    text, _markup, session = _press(user_id, "vproduct|back")
    assert session["current_step"] == "intro"
    assert "Ý tưởng video" in text


def test_script_to_video_not_jump_to_video_ai_real():
    text, markup, session = _open(181810, "script_image_video")
    assert "Kịch bản" in text
    assert session["product_id"] == "script_image_video"
    assert session["video_flow"] == "script_image_video"
    assert "promptvideo|start" not in _callbacks(markup)


def test_script_to_video_scene_split_step():
    assert bot.task3d_next_guided_step("script_image_video", "platform") == "panels"
    assert "panels" in bot.task3d_guided_steps("script_image_video")


def test_script_to_video_back_matrix():
    user_id = 181811
    _open(user_id, "script_image_video")
    _press(user_id, "vproduct|script_manual|script_image_video")
    text, _markup, session = _press(user_id, "vproduct|back")
    assert session["current_step"] == "intro"
    assert "Kịch bản" in text


def test_frame_video_button_not_jump_main_menu():
    text, markup, session = _open(181812, "frame_video_local")
    assert "Ghép ảnh thành video" in text
    callbacks = _callbacks(markup)
    assert "framevideo|start" in callbacks
    assert "framevideo|ai_first" in callbacks
    assert "vproduct|open|storyboard_prompt" not in callbacks
    assert "vproduct|open|video_ai_real" not in callbacks
    assert session["video_tool"] == "frame_video_local"


def test_frame_video_starts_image_collection(monkeypatch):
    user_id = 181813
    monkeypatch.setattr(bot, "FRAME_VIDEO_ENABLED", True)
    monkeypatch.setattr(bot, "FRAME_VIDEO_PUBLIC_ENABLED", True)
    bot.clear_frame_video_state(user_id)
    text, markup, _session = _press(user_id, "framevideo|start")
    assert bot.get_frame_video_state(user_id)["step"] == "collect"
    assert "Gửi từ 2 đến" in text
    assert "menu|main_video" in _callbacks(markup)


def test_frame_video_back_returns_video_menu():
    callbacks = _callbacks(bot.frame_video_collect_keyboard())
    assert "menu|main_video" in callbacks
    assert "framevideo|main" in callbacks


def test_frame_video_step_back_matrix():
    user_id = 181814
    bot.set_frame_video_state(user_id, {"step": "ratio", "photos": [{"file_id": "a"}, {"file_id": "b"}]})
    text, _markup, _session = _press(user_id, "framevideo|back|planning")
    assert "Kế hoạch ghép ảnh thành video" in text
    assert bot.get_frame_video_state(user_id)["step"] == "planning"


def test_storyboard_prompt_intro_first():
    text, markup, session = _open(181815, "storyboard_prompt")
    assert "Storyboard" in text
    assert "Chọn loại video" not in text
    assert session["current_step"] == "intro"
    assert "vproduct|storyboard_manual|storyboard_prompt" in _callbacks(markup)


def test_storyboard_does_not_auto_render():
    text, markup, session = _open(181816, "storyboard_prompt")
    assert session["draft"]["provider_called"] is False
    assert session["draft"]["xu_charged"] == 0
    assert "vproduct|b14_confirm" not in _callbacks(markup)
    assert "Storyboard" in text


def test_storyboard_back_matrix():
    user_id = 181817
    _open(user_id, "storyboard_prompt")
    _press(user_id, "vproduct|storyboard_manual|storyboard_prompt")
    _send_text(user_id, "mèo cam đi công viên")
    _press(user_id, "vproduct|b14_profile|storytelling")
    text, _markup, session = _press(user_id, "vproduct|back")
    assert session["current_step"] == "profile_select"
    assert "Chọn loại video" in text


def test_prompt_vault_list_back_video_idea_hub():
    text, markup, session = _press(181818, "vpromptlib|start")
    assert "Kho mẫu ý tưởng và câu lệnh" in text
    assert session["video_tool"] == "prompt_library"
    assert "videoidea|start" in _callbacks(markup)


def test_prompt_vault_use_prompt_returns_origin():
    user_id = 181819
    _press(user_id, "vpromptlib|idea")
    text, markup, session = _press(user_id, "vpromptlib|use|idea|1")
    assert "Đã dùng prompt" in text
    assert session["video_flow"] == "prompt_library"
    assert session["return_to"] == "menu|main_video"
    assert "vproduct|back" in _callbacks(markup)


def test_self_shot_flow_stack_preserved():
    _text, _markup, session = _open(181820, "self_shot_scene_change")
    assert session["draft"]["video_tool"] == "self_shot_scene_change"
    assert session["draft"]["back_target"] == "menu|main_video"


def test_multiscene_ui_flow_starts_intro_or_type():
    text, markup, session = _open(181821, "multi_scene_film")
    assert "Video dài tập" in text
    assert "đang phát triển" in text
    assert not session
    assert _callbacks(markup) == ["menu|main_video", "menu|main"]


def test_multiscene_guard_clean_if_engine_not_ready():
    text = bot.task3d_product_intro_text("multi_scene_film", "vi")
    assert "provider" not in text.lower()
    assert "worker" not in text.lower()
    assert "chưa trừ Xu" not in bot.video_public_text_forbidden_words(text)


def test_local_edit_back_video_menu():
    bot.clear_video_session(181822)
    text, markup, session = _press(181822, "videoedit|hub")
    assert "Chỉnh sửa video" in text
    assert session["video_tool"] == "video_local_edit"
    assert "menu|main_video" in _callbacks(markup)


def test_video_back_never_main_menu_unless_main_button():
    user_id = 181823
    _open(user_id, "video_trend")
    text, markup, session = _press(user_id, "vproduct|back")
    assert "Video TOAN AAS" in text
    assert "vid3|entry|video_trend" in _callbacks(markup)
    assert "menu|main" in _callbacks(markup)
    assert session["current_step"] == bot.VIDEO_BACK_MENU_TARGET


def test_video_back_stack_empty_returns_video_menu():
    session = {"product_id": "video_trend", "video_flow": "video_trend", "current_step": "profile_select", "step_history": []}
    assert bot.video_back_matrix_target(session) == bot.VIDEO_BACK_MENU_TARGET


def test_video_public_no_technical_words():
    texts = [
        bot.menu_text_main_video(),
        bot.video_b14_profile_selection_text({"product_id": "video_trend", "draft": {"product_id": "video_trend"}}, 0, "vi"),
        bot.video_editor_menu_text("vi"),
        bot.video_placeholder_audit_text(),
    ]
    for text in texts:
        assert not bot.video_public_text_forbidden_words(text), text


def test_video_flow_audit_back_audit_placeholder_audit_pass():
    assert bot.video_flow_audit_payload()["ok"] is True
    assert bot.video_back_audit_payload()["ok"] is True
    assert bot.video_placeholder_audit_payload()["ok"] is True
