import asyncio
from types import SimpleNamespace

import bot


class FakeMessage:
    chat_id = 181900

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


class FakeMedia:
    def __init__(self, file_id: str = "file-1", mime_type: str = "video/mp4"):
        self.file_id = file_id
        self.mime_type = mime_type
        self.file_name = "media.mp4"
        self.duration = 6
        self.file_size = 12345


class FakeQuery:
    def __init__(self, user_id: int, data: str):
        self.from_user = SimpleNamespace(id=user_id, first_name="P018N1")
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


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _rows(markup):
    return [[button.text for button in row] for row in markup.inline_keyboard]


def _press(user_id: int, callback: str):
    query = FakeQuery(user_id, callback)
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace()
    if callback.startswith("vproduct|"):
        asyncio.run(bot.handle_video_product_callback(update, context))
    elif callback.startswith("vpromptlib|"):
        asyncio.run(bot.handle_video_prompt_library_callback(update, context))
    elif callback.startswith("vdownload|"):
        asyncio.run(bot.handle_video_downloader_callback(update, context))
    else:
        raise AssertionError(f"unsupported callback {callback}")
    assert query.edits
    edit = query.edits[-1]
    return edit["text"], edit.get("reply_markup"), bot.get_video_session(user_id)


def _open(user_id: int, product_id: str):
    bot.clear_video_session(user_id)
    return _press(user_id, f"vproduct|open|{product_id}")


def _send_text(user_id: int, text: str = "nước hoa nam quay kiểu chân thật"):
    message = FakeMessage(text)
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id))
    context = SimpleNamespace()
    handled = asyncio.run(bot.handle_video_product_pending_text(update, context))
    assert handled is True
    assert message.replies
    return message.replies[-1]["text"], message.replies[-1].get("reply_markup"), bot.get_video_session(user_id)


def _send_media(user_id: int, *, kind: str = "video"):
    message = FakeMessage()
    media = FakeMedia("media-file-1", "video/mp4" if kind == "video" else "image/jpeg")
    if kind == "photo":
        message.photo = [media]
    else:
        message.video = media
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id))
    context = SimpleNamespace()
    handled = asyncio.run(bot.handle_video_product_pending_media(update, context))
    assert handled is True
    assert message.replies
    return message.replies[-1]["text"], message.replies[-1].get("reply_markup"), bot.get_video_session(user_id)


def test_video_menu_layout_preserved():
    assert _rows(bot.main_video_keyboard("vi")) == [
        ["🔥 Video theo trend", "🎬 Video AI chân thật"],
        ["🧩 Kịch bản → Video", "🎞 Ghép ảnh thành video"],
        ["🎥 Tự quay & đổi cảnh AI", "🎬 Phim AI nhiều cảnh"],
        ["🧠 Ý tưởng video", "🎬 Storyboard + Prompt"],
        ["📚 Kho prompt video", "📥 Tải video từ link"],
        ["🛠 Chỉnh sửa video local", "🏠 Menu chính"],
    ]


def test_video_profile_picker_shared_12_types():
    markup = bot.video_b14_profile_selection_keyboard("vi")
    callbacks = _callbacks(markup)
    profile_callbacks = [item for item in callbacks if item.startswith("vproduct|b14_profile|")]
    assert len(profile_callbacks) >= 12
    labels = _labels(markup)
    assert "📖 Kể chuyện" in labels
    assert "🛒 Review sản phẩm" in labels
    assert any("Phim ngắn / trailer" in label for label in labels)
    assert "vproduct|back" in callbacks


def test_profile_back_returns_origin_step():
    user_id = 181901
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
    _press(user_id, "vproduct|input_text|video_ai_real")
    _send_text(user_id)
    text, _markup, session = _press(user_id, "vproduct|back")
    assert session["current_step"] == "awaiting_prompt_text"
    assert "prompt" in text.lower()
    text, _markup, session = _press(user_id, "vproduct|back")
    assert session["current_step"] == "ai_prompt_menu"
    assert "Prompt" in text


def test_no_flow_jumps_to_main_menu_unless_main_button():
    user_id = 181902
    _open(user_id, "script_image_video")
    _press(user_id, "vproduct|script_manual|script_image_video")
    _send_text(user_id, "kịch bản affiliate mỹ phẩm")
    text, _markup, session = _press(user_id, "vproduct|back")
    assert session["current_step"] == "script_manual_topic"
    assert "Menu chính" not in text


def test_back_stack_empty_returns_video_menu():
    session = {"product_id": "video_ai_real", "video_flow": "video_ai_real", "current_step": "", "step_history": []}
    assert bot.video_back_matrix_target(session) == bot.VIDEO_BACK_MENU_TARGET


def test_video_ai_real_intro_first():
    text, markup, session = _open(181903, "video_ai_real")
    callbacks = _callbacks(markup)
    assert "Video AI chân thật" in text
    assert session["current_step"] == "intro"
    assert "vproduct|ai_prompt_menu|video_ai_real" in callbacks
    assert "vproduct|ai_image_menu|video_ai_real" in callbacks
    assert "vproduct|ai_video_menu|video_ai_real" in callbacks
    assert "promptvideo|start" not in callbacks


def test_video_ai_real_prompt_then_profile():
    user_id = 181904
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
    _press(user_id, "vproduct|input_text|video_ai_real")
    text, markup, session = _send_text(user_id, "prompt quảng cáo nước hoa nam chân thật")
    assert session["current_step"] == "profile_select"
    assert "Chọn loại video" in text
    assert "vproduct|b14_profile|product_review" in _callbacks(markup)


def test_video_ai_real_image_then_profile():
    user_id = 181905
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_image_menu|video_ai_real")
    _press(user_id, "vproduct|input_media|video_ai_real")
    text, markup, session = _send_media(user_id, kind="photo")
    assert session["current_step"] == "profile_select"
    assert "Chọn loại video" in text
    assert "vproduct|b14_profile|storytelling" in _callbacks(markup)


def test_video_ai_real_not_default_for_other_flows():
    text, markup, session = _open(181906, "script_image_video")
    assert session["video_flow"] == "script_image_video"
    assert "Video AI chân thật" not in text
    assert "promptvideo|start" not in _callbacks(markup)


def test_script_to_video_intro_first():
    text, markup, session = _open(181907, "script_image_video")
    assert "Kịch bản" in text
    assert session["current_step"] == "intro"
    assert "vproduct|b14_profile|storytelling" not in _callbacks(markup)


def test_script_to_video_input_then_profile():
    user_id = 181908
    _open(user_id, "script_image_video")
    _press(user_id, "vproduct|input_text|script_image_video")
    text, markup, session = _send_text(user_id, "kịch bản review sản phẩm")
    assert session["current_step"] == "profile_select"
    assert "Chọn loại video" in text
    assert "vproduct|b14_profile|product_review" in _callbacks(markup)


def test_script_to_video_profile_then_scene_planning():
    user_id = 181909
    _open(user_id, "script_image_video")
    _press(user_id, "vproduct|input_text|script_image_video")
    _send_text(user_id, "kịch bản review sản phẩm")
    text, markup, session = _press(user_id, "vproduct|b14_profile|product_review")
    assert session["current_step"] == "panels"
    assert "Chọn số" in text
    assert "vproduct|panels|6" in _callbacks(markup)


def test_script_to_video_not_jump_video_ai_real():
    text, markup, session = _open(181910, "script_image_video")
    assert session["product_id"] == "script_image_video"
    assert session["video_flow"] == "script_image_video"
    assert "Prompt → Video AI" not in _labels(markup)


def test_self_shot_intro_first():
    text, markup, session = _open(181911, "self_shot_scene_change")
    assert "Tự quay" in text
    assert session["current_step"] == "intro"
    assert "vproduct|selfshot_source|upload" in _callbacks(markup)
    assert "vproduct|selfshot_source|recent" in _callbacks(markup)


def test_self_shot_video_source_then_profile():
    user_id = 181912
    _open(user_id, "self_shot_scene_change")
    _press(user_id, "vproduct|selfshot_source|upload")
    text, markup, session = _send_media(user_id, kind="video")
    assert session["current_step"] == "profile_select"
    assert "Chọn loại video" in text
    assert "vproduct|b14_profile|storytelling" in _callbacks(markup)


def test_self_shot_profile_then_object_selection():
    user_id = 181913
    _open(user_id, "self_shot_scene_change")
    _press(user_id, "vproduct|selfshot_source|upload")
    _send_media(user_id, kind="video")
    text, markup, session = _press(user_id, "vproduct|b14_profile|storytelling")
    assert session["current_step"] == "subject"
    assert "Chọn chủ thể" in text
    assert "vproduct|subject|person" in _callbacks(markup)


def test_self_shot_session_preserved():
    user_id = 181914
    _open(user_id, "self_shot_scene_change")
    _press(user_id, "vproduct|selfshot_source|upload")
    _send_media(user_id, kind="video")
    session = bot.get_video_session(user_id)
    assert session["draft"]["source_media_refs"]
    assert session["video_tool"] == "self_shot_scene_change"


def test_multiscene_intro_first_not_profile_first():
    text, markup, session = _open(181915, "multi_scene_film")
    assert "Phim AI nhiều cảnh" in text
    assert session["current_step"] == "intro"
    assert "vproduct|b14_profile|cinematic_trailer" not in _callbacks(markup)


def test_multiscene_intro_then_profile():
    user_id = 181916
    _open(user_id, "multi_scene_film")
    text, markup, session = _press(user_id, "vproduct|film_manual|multi_scene_film")
    assert session["current_step"] == "film_manual_topic"
    text, markup, session = _send_text(user_id, "phim ngắn về cô gái mở tiệm hoa")
    assert session["current_step"] == "profile_select"
    assert "Chọn loại video" in text
    assert "vproduct|b14_profile|cinematic_trailer" in _callbacks(markup)


def test_multiscene_profile_then_scene_count_or_outline():
    user_id = 181917
    _open(user_id, "multi_scene_film")
    _press(user_id, "vproduct|film_manual|multi_scene_film")
    _send_text(user_id, "phim ngắn về cô gái mở tiệm hoa")
    text, markup, session = _press(user_id, "vproduct|b14_profile|cinematic_trailer")
    assert session["current_step"] == "panels"
    assert "Chọn số" in text
    assert "vproduct|panels|9" in _callbacks(markup)


def test_multiscene_engine_not_touched():
    user_id = 181918
    _open(user_id, "multi_scene_film")
    _press(user_id, "vproduct|film_manual|multi_scene_film")
    _send_text(user_id, "phim ngắn về cô gái mở tiệm hoa")
    _press(user_id, "vproduct|b14_profile|cinematic_trailer")
    session = bot.get_video_session(user_id)
    assert session["draft"]["provider_called"] is False
    assert session["draft"]["xu_charged"] == 0


def test_idea_intro_first_not_profile_first():
    text, markup, session = _open(181919, "video_idea")
    assert "Ý tưởng video" in text
    assert session["current_step"] == "intro"
    assert "vproduct|b14_profile|storytelling" not in _callbacks(markup)


def test_idea_intro_then_profile():
    user_id = 181920
    _open(user_id, "video_idea")
    text, markup, session = _press(user_id, "vproduct|ideas|video_idea")
    assert session["current_step"] == "profile_select"
    assert "Chọn loại video" in text
    assert "vproduct|b14_profile|storytelling" in _callbacks(markup)


def test_idea_profile_then_idea_list():
    user_id = 181921
    _open(user_id, "video_idea")
    _press(user_id, "vproduct|ideas|video_idea")
    text, markup, session = _press(user_id, "vproduct|b14_profile|storytelling")
    assert session["current_step"] == "idea_suggestions"
    assert "Gợi ý ý tưởng" in text
    assert "vproduct|microflow_choose|0" in _callbacks(markup)
    assert "vproduct|microflow_choose|4" in _callbacks(markup)


def test_idea_does_not_jump_assets():
    user_id = 181922
    _open(user_id, "video_idea")
    _press(user_id, "vproduct|ideas|video_idea")
    session = bot.get_video_session(user_id)
    assert session["current_step"] == "profile_select"
    assert session["current_step"] != "asset_intake"


def test_storyboard_intro_first_not_profile_first():
    text, markup, session = _open(181923, "storyboard_prompt")
    assert "Storyboard + Prompt" in text
    assert session["current_step"] == "intro"
    assert "vproduct|b14_profile|storytelling" not in _callbacks(markup)


def test_storyboard_intro_then_profile():
    user_id = 181924
    _open(user_id, "storyboard_prompt")
    _press(user_id, "vproduct|input_text|storyboard_prompt")
    text, markup, session = _send_text(user_id, "mèo cam đi công viên")
    assert session["current_step"] == "profile_select"
    assert "Chọn loại video" in text
    assert "vproduct|b14_profile|storytelling" in _callbacks(markup)


def test_storyboard_profile_then_prompt_generation():
    user_id = 181925
    _open(user_id, "storyboard_prompt")
    _press(user_id, "vproduct|input_text|storyboard_prompt")
    _send_text(user_id, "mèo cam đi công viên")
    text, markup, session = _press(user_id, "vproduct|b14_profile|storytelling")
    assert session["current_step"] == "panels"
    assert "panel" in text.lower()
    assert "vproduct|panels|12" in _callbacks(markup)


def test_storyboard_does_not_auto_render():
    user_id = 181926
    _open(user_id, "storyboard_prompt")
    _press(user_id, "vproduct|ideas|storyboard_prompt")
    _press(user_id, "vproduct|b14_profile|storytelling")
    session = bot.get_video_session(user_id)
    assert session["draft"]["provider_called"] is False
    assert session["draft"]["xu_charged"] == 0


def test_frame_video_intro_first():
    text, markup, session = _open(181927, "frame_video_local")
    assert "Ghép ảnh thành video" in text
    assert session["current_step"] == "intro"
    callbacks = _callbacks(markup)
    assert "framevideo|start" in callbacks
    assert "framevideo|ai_first" in callbacks


def test_frame_video_image_collection_then_optional_profile():
    text, markup, session = _open(181928, "frame_video_local")
    callbacks = _callbacks(markup)
    assert "framevideo|start" in callbacks
    assert "framevideo|ai_first" in callbacks
    assert "vproduct|asset_storyboard_prompt" not in callbacks
    assert "vproduct|open|video_ai_real" not in callbacks
    assert session["video_tool"] == "frame_video_local"


def test_frame_video_back_menu_video():
    user_id = 181929
    _open(user_id, "frame_video_local")
    text, markup, session = _press(user_id, "vproduct|back")
    assert session["current_step"] == bot.VIDEO_BACK_MENU_TARGET
    assert "Video TOAN AAS" in text
    assert "vproduct|open|video_trend" in _callbacks(markup)


def test_prompt_vault_direct_search_no_profile_required():
    text, markup, session = _press(181930, "vpromptlib|start")
    assert "Kho prompt video" in text
    assert session["video_tool"] == "prompt_library"
    assert "vproduct|b14_profile|storytelling" not in _callbacks(markup)


def test_link_download_no_profile_required():
    route = bot.video_public_route_for_tool("video_downloader")
    assert route["first_step"] == "tool_home"
    assert route["flow_type"] == "download_link"


def test_local_edit_no_profile_required():
    route = bot.video_public_route_for_tool("video_local_edit")
    assert route["first_step"] == "tool_home"
    assert route["flow_type"] == "local_edit"


def test_video_public_copy_no_technical_words():
    texts = [
        bot.task3d_product_intro_text("video_ai_real", "vi"),
        bot.task3d_product_intro_text("script_image_video", "vi"),
        bot.task3d_product_intro_text("self_shot_scene_change", "vi"),
        bot.task3d_product_intro_text("multi_scene_film", "vi"),
        bot.video_b14_profile_selection_text({"product_id": "video_ai_real", "draft": {"product_id": "video_ai_real"}}, 0, "vi"),
    ]
    for text in texts:
        assert not bot.video_public_text_forbidden_words(text), text
        assert "placeholder" not in text.lower()
        assert "đang được chuẩn bị" not in text.lower()


def test_video_planning_copy_no_charge_until_confirm():
    for product_id in ("video_ai_real", "script_image_video", "self_shot_scene_change", "multi_scene_film", "video_idea", "storyboard_prompt"):
        text = bot.task3d_product_intro_text(product_id, "vi")
        assert "chưa trừ Xu" in text
        assert "xác nhận" in text or product_id in {"self_shot_scene_change", "multi_scene_film"}


def test_video_flow_audit_back_audit_placeholder_audit_pass():
    flow = bot.video_flow_audit_payload()
    assert flow["ok"] is True
    by_label = {row["public_label"]: row for row in flow["rows"]}
    assert by_label["🎬 Video AI chân thật"]["first_step"] == "intro"
    assert by_label["🎬 Phim AI nhiều cảnh"]["profile_step_position"] == "after_product_intro_input"
    assert bot.video_back_audit_payload()["ok"] is True
    assert bot.video_placeholder_audit_payload()["ok"] is True
