import asyncio
from types import SimpleNamespace

import bot


class FakeMessage:
    chat_id = 184000

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
        self.from_user = SimpleNamespace(id=user_id, first_name="P018N4")
        self.data = data
        self.message = FakeMessage()
        self.edits = []

    async def answer(self, *args, **kwargs):
        return None

    async def edit_message_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.edits.append(item)
        return SimpleNamespace(**item)


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _press(user_id: int, callback: str):
    query = FakeQuery(user_id, callback)
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert query.edits
    edit = query.edits[-1]
    return edit["text"], edit.get("reply_markup"), bot.get_video_session(user_id)


def _open(user_id: int, product_id: str):
    bot.clear_video_session(user_id)
    return _press(user_id, f"vproduct|open|{product_id}")


def _send_text(user_id: int, text: str = "nước hoa nam cinematic"):
    message = FakeMessage(text)
    handled = asyncio.run(
        bot.handle_video_product_pending_text(
            SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id)),
            SimpleNamespace(),
        )
    )
    assert handled is True
    assert message.replies
    reply = message.replies[-1]
    return reply["text"], reply.get("reply_markup"), bot.get_video_session(user_id)


def test_no_inner_video_flow_shows_prompt_vault_button():
    product_ids = [
        "video_ai_real",
        "video_idea",
        "storyboard_prompt",
        "frame_video_local",
        "script_image_video",
        "self_shot_scene_change",
    ]
    for product_id in product_ids:
        markup = bot.task3d_product_intro_keyboard(product_id, "vi")
        assert "📚 Dùng prompt từ kho" not in _labels(markup)
        assert "vpromptlib|start" not in _callbacks(markup)


def test_video_ai_realistic_renames_status_to_analysis():
    markup = bot.task3d_product_intro_keyboard("video_ai_real", "vi")
    labels = _labels(markup)
    assert "📊 Phân tích video" in labels
    assert "📊 Trạng thái video" not in labels
    legacy_labels = _labels(bot.video_ai_true_keyboard("vi"))
    assert "📊 Phân tích video" in legacy_labels
    assert "📊 Trạng thái video" not in legacy_labels


def test_video_idea_removes_product_industry_and_trend_buttons():
    markup = bot.task3d_product_intro_keyboard("video_idea", "vi")
    labels = _labels(markup)
    callbacks = _callbacks(markup)
    assert "🎲 Gợi ý nhanh" in labels
    assert "✍️ Tự nhập chủ đề" in labels
    assert "📦 Theo sản phẩm/ngành" not in labels
    assert "🔥 Theo trend" not in labels
    assert "vproduct|idea_industry|video_idea" not in callbacks
    assert "vproduct|idea_trend|video_idea" not in callbacks


def test_prompt_suggestion_returns_at_least_3_selectable_prompts():
    user_id = 184001
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
    _press(user_id, "vproduct|suggest_prompt|video_ai_real")
    text, markup, session = _send_text(user_id, "quảng cáo nước hoa nam")
    callbacks = _callbacks(markup)
    assert session["current_step"] == "suggest_prompt"
    assert len(session["draft"]["microflow_options"]) >= 3
    assert "vproduct|microflow_choose|0" in callbacks
    assert "vproduct|microflow_choose|2" in callbacks
    assert "✅ Dùng hướng này" not in _labels(markup)
    assert "Dùng prompt từ kho" not in text


def test_prompt_choice_saves_state_and_goes_to_profile():
    user_id = 184002
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
    _press(user_id, "vproduct|suggest_prompt|video_ai_real")
    _send_text(user_id, "quảng cáo quán cà phê")
    text, _markup, session = _press(user_id, "vproduct|microflow_choose|1")
    assert session["current_step"] == "profile_select"
    assert session["draft"]["selected_prompt"]["title"].startswith("Prompt 2:")
    assert "Chọn loại video" in text


def test_image_suggestion_requires_image_before_video_ai_profile():
    user_id = 184003
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_image_menu|video_ai_real")
    _press(user_id, "vproduct|suggest_image|video_ai_real")
    _send_text(user_id, "ảnh lookbook áo khoác")
    text, markup, session = _press(user_id, "vproduct|microflow_choose|0")
    assert session["current_step"] == "image_to_video_prompt_set_options"
    assert "Bộ ảnh/prompt ảnh" in text
    text, markup, session = _press(user_id, "vproduct|image_prompt_set_use")
    assert session["current_step"] == "awaiting_source_image"
    assert "cần ảnh thật" in text
    assert "vproduct|media_continue" in _callbacks(markup)


def test_video_reference_suggestion_returns_at_least_3_selectable_directions():
    user_id = 184004
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_video_menu|video_ai_real")
    _press(user_id, "vproduct|suggest_video|video_ai_real")
    text, markup, session = _send_text(user_id, "video mỹ phẩm chân thật")
    assert len(session["draft"]["microflow_options"]) >= 3
    assert "vproduct|microflow_choose|2" in _callbacks(markup)
    assert "Concept:" in text


def test_script_suggestion_returns_at_least_3_scripts():
    user_id = 184005
    _open(user_id, "script_image_video")
    _press(user_id, "vproduct|script_ideas|script_image_video")
    text, markup, session = _send_text(user_id, "khóa học AI cho người mới")
    assert len(session["draft"]["microflow_options"]) >= 3
    assert "vproduct|microflow_choose|0" in _callbacks(markup)
    assert "Kịch bản" in text


def test_idea_quick_returns_5_real_ideas_and_requires_development_path():
    user_id = 184006
    _open(user_id, "video_idea")
    text, markup, session = _press(user_id, "vproduct|idea_quick|video_idea")
    assert session["current_step"] == "idea_suggestions"
    assert len(session["draft"]["microflow_options"]) == 5
    assert "vproduct|microflow_choose|4" in _callbacks(markup)
    text, markup, session = _press(user_id, "vproduct|microflow_choose|0")
    assert session["current_step"] == "idea_development_path"
    assert "muốn phát triển ý tưởng này theo dạng nào" in text
    assert "vproduct|idea_develop|script_image_video" in _callbacks(markup)


def test_idea_development_path_routes_to_selected_product_flow():
    user_id = 184007
    _open(user_id, "video_idea")
    _press(user_id, "vproduct|idea_quick|video_idea")
    _press(user_id, "vproduct|microflow_choose|0")
    text, markup, session = _press(user_id, "vproduct|idea_develop|storyboard_prompt")
    assert session["product_id"] == "storyboard_prompt"
    assert session["current_step"] == "intro"
    assert "Storyboard + Prompt" in text
    assert "vproduct|storyboard_suggest|storyboard_prompt" in _callbacks(markup)


def test_storyboard_suggestion_asks_topic_before_count():
    user_id = 184008
    _open(user_id, "storyboard_prompt")
    text, markup, session = _press(user_id, "vproduct|storyboard_suggest|storyboard_prompt")
    assert session["current_step"] == "storyboard_suggestion_topic"
    assert "Nhập chủ đề" in text
    assert not any("khung hình/cảnh ảnh" in label for label in _labels(markup))
    text, markup, session = _send_text(user_id, "mèo cam đi công viên")
    assert session["current_step"] == "storyboard_suggestion_scene_count"
    assert any("khung hình/cảnh ảnh" in label for label in _labels(markup))


def test_storyboard_generates_image_then_final_video_scenes():
    user_id = 184009
    _open(user_id, "storyboard_prompt")
    _press(user_id, "vproduct|storyboard_suggest|storyboard_prompt")
    _send_text(user_id, "câu chuyện sản phẩm nước hoa")
    text, markup, session = _press(user_id, "vproduct|storyboard_scene_count|4")
    assert session["current_step"] == "storyboard_image_scenes"
    assert len(session["draft"]["storyboard_image_scenes"]) == 4
    assert "khung hình/cảnh ảnh" in text
    text, markup, session = _press(user_id, "vproduct|storyboard_use")
    assert session["current_step"] == "storyboard_final_video_duration"
    text, markup, session = _press(user_id, "vproduct|storyboard_video_duration|5")
    assert session["current_step"] == "storyboard_final_video_scenes"
    assert len(session["draft"]["final_video_scenes"]) == 4
    assert "5s" in text


def test_image_to_video_suggestion_topic_then_image_count_then_prompt_set():
    user_id = 184010
    _open(user_id, "frame_video_local")
    _press(user_id, "vproduct|frame_suggest_image|frame_video_local")
    text, markup, session = _send_text(user_id, "bộ ảnh du lịch Đà Lạt")
    assert session["current_step"] == "image_to_video_image_suggestion_scene_count"
    assert any("ảnh" in label for label in _labels(markup))
    text, markup, session = _press(user_id, "vproduct|image_suggest_scene_count|4")
    assert session["current_step"] == "image_to_video_prompt_set_options"
    assert len(session["draft"]["microflow_options"]) >= 3
    assert "vproduct|microflow_choose|0" in _callbacks(markup)


def test_self_shot_direction_returns_at_least_3_and_requires_source_video():
    user_id = 184011
    _open(user_id, "self_shot_scene_change")
    _press(user_id, "vproduct|selfshot_ideas|self_shot_scene_change")
    text, markup, session = _send_text(user_id, "giữ người thật đổi nền studio")
    assert len(session["draft"]["microflow_options"]) >= 3
    text, markup, session = _press(user_id, "vproduct|microflow_choose|0")
    assert session["current_step"] == "awaiting_self_shot_video"
    assert "Gửi video" in text


def test_back_from_prompt_suggestion_to_prompt_submenu():
    user_id = 184012
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
    _press(user_id, "vproduct|suggest_prompt|video_ai_real")
    text, markup, session = _press(user_id, "vproduct|back")
    assert session["current_step"] == "ai_prompt_menu"
    assert "Prompt → Video AI" in text


def test_back_from_storyboard_count_to_storyboard_topic():
    user_id = 184013
    _open(user_id, "storyboard_prompt")
    _press(user_id, "vproduct|storyboard_suggest|storyboard_prompt")
    _send_text(user_id, "quảng cáo quán cà phê")
    text, _markup, session = _press(user_id, "vproduct|back")
    assert session["current_step"] == "storyboard_suggestion_topic"
    assert "Nhập chủ đề" in text


def test_back_from_idea_development_path_to_idea_result():
    user_id = 184014
    _open(user_id, "video_idea")
    _press(user_id, "vproduct|idea_quick|video_idea")
    _press(user_id, "vproduct|microflow_choose|0")
    text, _markup, session = _press(user_id, "vproduct|back")
    assert session["current_step"] == "idea_suggestions"
    assert "Gợi ý ý tưởng" in text


def test_video_microflow_audits_pass():
    assert bot.video_semantics_audit_payload()["ok"] is True
    assert bot.video_callback_audit_payload()["ok"] is True
    assert bot.video_microflow_audit_payload()["ok"] is True
