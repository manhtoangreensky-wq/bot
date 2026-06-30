import asyncio
from types import SimpleNamespace

import bot


class FakeMessage:
    chat_id = 182000

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
        self.from_user = SimpleNamespace(id=user_id, first_name="P018N2")
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


def _send_text(user_id: int, text: str = "nước hoa nam"):
    message = FakeMessage(text)
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id))
    handled = asyncio.run(bot.handle_video_product_pending_text(update, SimpleNamespace()))
    assert handled is True
    assert message.replies
    reply = message.replies[-1]
    return reply["text"], reply.get("reply_markup"), bot.get_video_session(user_id)


def test_trend_entry_restores_initial_suggestion_screen():
    text, markup, session = _open(182001, "video_trend")
    callbacks = _callbacks(markup)
    assert session["current_step"] == "intro"
    assert "Video theo trend" in text
    assert any("Gợi ý trend hot" in label for label in _labels(markup))
    assert "vproduct|trend_today" in callbacks
    assert "vproduct|b14_profile|storytelling" not in callbacks
    assert "video_trend" not in bot.VIDEO_PROFILE_FIRST_PRODUCTS


def test_trend_profile_back_returns_trend_input():
    user_id = 182002
    _open(user_id, "video_trend")
    _press(user_id, "vproduct|trend_custom")
    _send_text(user_id, "quán cà phê cuối tuần")
    session = bot.get_video_session(user_id)
    assert session["current_step"] == "profile_select"
    text, markup, session = _press(user_id, "vproduct|back")
    assert session["current_step"] == "trend_manual_input"
    assert "Nhập trend" in text or "trend" in text.lower()


def test_trend_quick_suggestion_and_product_industry_distinct():
    markup = bot.task3d_product_intro_keyboard("video_trend", "vi")
    callbacks = _callbacks(markup)
    assert "vproduct|trend_today" in callbacks
    assert "vproduct|trend_custom" in callbacks
    assert "vproduct|trend_industry" not in callbacks
    assert "vproduct|trend_video_suggest" not in callbacks


def test_video_ai_real_has_prompt_image_video_and_suggestion_buttons():
    text, markup, session = _open(182003, "video_ai_real")
    labels = _labels(markup)
    callbacks = _callbacks(markup)
    assert "Video AI chân thật" in text
    assert session["current_step"] == "intro"
    assert "📝 Prompt → Video AI" in labels
    assert "🖼 Ảnh → Video AI" in labels
    assert "🎞 Video mẫu → Video AI" in labels
    assert "💡 Gợi ý prompt video" not in labels
    assert "🖼 Gợi ý tạo ảnh" not in labels
    assert "🎬 Gợi ý tạo video" not in labels
    assert "vproduct|ai_prompt_menu|video_ai_real" in callbacks
    assert "vproduct|ai_image_menu|video_ai_real" in callbacks
    assert "vproduct|ai_video_menu|video_ai_real" in callbacks
    assert "vproduct|suggest_prompt|video_ai_real" not in callbacks
    assert "vproduct|suggest_image|video_ai_real" not in callbacks
    assert "vproduct|suggest_video|video_ai_real" not in callbacks
    assert not any("trend_" in item for item in callbacks)


def test_video_ai_real_suggestion_back_matrix():
    user_id = 182004
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
    text, _markup, session = _press(user_id, "vproduct|suggest_prompt|video_ai_real")
    assert session["current_step"] == "prompt_suggestion_topic"
    assert "gợi ý prompt" in text.lower()
    text, _markup, session = _press(user_id, "vproduct|back")
    assert session["current_step"] == "ai_prompt_menu"
    assert "Prompt" in text


def test_script_to_video_semantics_not_storyboard():
    text, markup, session = _open(182005, "script_image_video")
    labels = _labels(markup)
    callbacks = _callbacks(markup)
    assert "Kịch bản" in text
    assert any("Gợi ý kịch bản" in label for label in labels)
    assert any("Gửi kịch bản có sẵn" in label for label in labels)
    assert any("Tự nhập chủ đề" in label for label in labels)
    assert "vproduct|script_ideas|script_image_video" in callbacks
    assert "vproduct|storyboard_many_images|storyboard_prompt" not in callbacks


def test_storyboard_semantics_visual_sequence():
    text, markup, session = _open(182006, "storyboard_prompt")
    labels = _labels(markup)
    callbacks = _callbacks(markup)
    assert "chuỗi cảnh" in text
    assert any("Gửi ảnh/storyboard có sẵn" in label for label in labels)
    assert any("Gợi ý storyboard" in label for label in labels)
    assert any("Tự nhập storyboard" in label for label in labels)
    assert "vproduct|storyboard_upload|storyboard_prompt" in callbacks
    assert "vproduct|script_ideas|script_image_video" not in callbacks


def test_idea_quick_and_product_industry_not_same_behavior():
    markup = bot.task3d_product_intro_keyboard("video_idea", "vi")
    callbacks = _callbacks(markup)
    assert "vproduct|idea_quick|video_idea" in callbacks
    assert "vproduct|idea_industry|video_idea" in callbacks
    assert "vproduct|idea_quick|video_idea" != "vproduct|idea_industry|video_idea"


def test_image_to_video_starts_with_image_flow():
    text, markup, session = _open(182007, "frame_video_local")
    callbacks = _callbacks(markup)
    assert "Ghép ảnh thành video" in text
    assert session["current_step"] == "intro"
    assert "vproduct|frame_send_images|frame_video_local" in callbacks
    assert "vproduct|frame_suggest_image|frame_video_local" in callbacks
    assert "vproduct|b14_profile|storytelling" not in callbacks


def test_self_shot_starts_with_source_video_and_idea_option():
    text, markup, session = _open(182008, "self_shot_scene_change")
    callbacks = _callbacks(markup)
    assert "Tự quay" in text
    assert "vproduct|selfshot_source|upload" in callbacks
    assert "vproduct|selfshot_source|recent" in callbacks
    assert "vproduct|selfshot_ideas|self_shot_scene_change" in callbacks


def test_video_semantics_audit_passes():
    payload = bot.video_semantics_audit_payload()
    assert payload["ok"] is True
    assert payload["semantics"]["video_trend"].startswith("tìm/gợi ý trend")
    assert payload["semantics"]["storyboard_prompt"].startswith("tạo chuỗi hình ảnh")
    assert bot.video_flow_audit_payload()["ok"] is True


def test_video_public_no_technical_words_and_no_charge_copy():
    for product_id in ("video_trend", "video_ai_real", "script_image_video", "storyboard_prompt", "frame_video_local"):
        text = bot.task3d_product_intro_text(product_id, "vi")
        assert not bot.video_public_text_forbidden_words(text)
        assert "chưa trừ Xu" in text
