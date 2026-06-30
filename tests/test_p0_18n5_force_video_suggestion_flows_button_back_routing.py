import asyncio
from types import SimpleNamespace

import bot


class FakeMessage:
    chat_id = 185000

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
        self.from_user = SimpleNamespace(id=user_id, first_name="P018N5")
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


def _send_text(user_id: int, text: str):
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


def _assert_immediate_options(user_id: int, product_id: str, callback: str, expected_step: str, min_options: int = 3):
    text, markup, session = _press(user_id, callback)
    callbacks = _callbacks(markup)
    assert session["product_id"] == product_id
    assert session["current_step"] == expected_step
    assert len(session["draft"]["microflow_options"]) >= min_options
    assert "vproduct|microflow_choose|0" in callbacks
    assert f"vproduct|microflow_choose|{min_options - 1}" in callbacks
    assert "vproduct|microflow_regenerate" in callbacks
    assert "vproduct|microflow_custom_topic" in callbacks
    assert "vproduct|microflow_edit" not in callbacks
    assert "✅ Dùng hướng này" not in _labels(markup)
    assert "Dùng prompt từ kho" not in text
    return text, markup, session


def test_all_video_suggestion_buttons_show_options_immediately():
    cases = [
        (185001, "video_ai_real", "vproduct|ai_prompt_menu|video_ai_real", "vproduct|suggest_prompt|video_ai_real", "suggest_prompt", 3),
        (185002, "video_ai_real", "vproduct|ai_image_menu|video_ai_real", "vproduct|suggest_image|video_ai_real", "suggest_image", 3),
        (185003, "video_ai_real", "vproduct|ai_video_menu|video_ai_real", "vproduct|suggest_video|video_ai_real", "suggest_video", 3),
        (185004, "script_image_video", None, "vproduct|script_ideas|script_image_video", "script_ideas", 3),
        (185005, "storyboard_prompt", None, "vproduct|storyboard_suggest|storyboard_prompt", "storyboard_idea", 3),
        (185006, "frame_video_local", None, "vproduct|frame_suggest_image|frame_video_local", "frame_suggest_image", 3),
        (185007, "self_shot_scene_change", None, "vproduct|selfshot_ideas|self_shot_scene_change", "selfshot_ideas", 3),
        (185008, "video_idea", None, "vproduct|idea_quick|video_idea", "idea_suggestions", 5),
        (185009, "multi_scene_film", None, "vproduct|film_story|multi_scene_film", "film_story_options", 3),
    ]
    for user_id, product_id, parent_callback, suggestion_callback, expected_step, min_options in cases:
        _open(user_id, product_id)
        if parent_callback:
            _press(user_id, parent_callback)
        _assert_immediate_options(user_id, product_id, suggestion_callback, expected_step, min_options)


def test_custom_topic_regenerates_options_in_same_suggestion_flow():
    user_id = 185020
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
    _assert_immediate_options(user_id, "video_ai_real", "vproduct|suggest_prompt|video_ai_real", "suggest_prompt")

    text, _markup, session = _press(user_id, "vproduct|microflow_custom_topic")
    assert session["current_step"] == "prompt_custom_topic"
    assert "chủ đề riêng" in text

    text, markup, session = _send_text(user_id, "quảng cáo nước hoa nam trong studio đen")
    assert session["current_step"] == "suggest_prompt"
    assert session["draft"]["microflow_topic"] == "quảng cáo nước hoa nam trong studio đen"
    assert len(session["draft"]["microflow_options"]) >= 3
    assert "vproduct|microflow_choose|0" in _callbacks(markup)
    assert "vproduct|microflow_custom_topic" in _callbacks(markup)


def test_storyboard_and_image_to_video_choose_before_scene_count_then_back_to_options():
    user_id = 185021
    _open(user_id, "storyboard_prompt")
    _assert_immediate_options(user_id, "storyboard_prompt", "vproduct|storyboard_suggest|storyboard_prompt", "storyboard_idea")
    _press(user_id, "vproduct|microflow_choose|0")
    assert bot.get_video_session(user_id)["current_step"] == "storyboard_suggestion_scene_count"
    text, _markup, session = _press(user_id, "vproduct|back")
    assert session["current_step"] == "storyboard_idea"
    assert "Gợi ý storyboard" in text

    user_id = 185022
    _open(user_id, "frame_video_local")
    _assert_immediate_options(user_id, "frame_video_local", "vproduct|frame_suggest_image|frame_video_local", "frame_suggest_image")
    _press(user_id, "vproduct|microflow_choose|0")
    assert bot.get_video_session(user_id)["current_step"] == "image_to_video_image_suggestion_scene_count"
    text, _markup, session = _press(user_id, "vproduct|back")
    assert session["current_step"] == "frame_suggest_image"
    assert "Bộ ảnh" in text


def test_suggestion_back_routes_to_exact_parent_menu():
    cases = [
        (185030, "video_ai_real", "vproduct|ai_prompt_menu|video_ai_real", "vproduct|suggest_prompt|video_ai_real", "ai_prompt_menu"),
        (185031, "video_ai_real", "vproduct|ai_image_menu|video_ai_real", "vproduct|suggest_image|video_ai_real", "ai_image_menu"),
        (185032, "video_ai_real", "vproduct|ai_video_menu|video_ai_real", "vproduct|suggest_video|video_ai_real", "ai_video_menu"),
        (185033, "script_image_video", None, "vproduct|script_ideas|script_image_video", "intro"),
        (185034, "storyboard_prompt", None, "vproduct|storyboard_suggest|storyboard_prompt", "intro"),
        (185035, "frame_video_local", None, "vproduct|frame_suggest_image|frame_video_local", "intro"),
        (185036, "self_shot_scene_change", None, "vproduct|selfshot_ideas|self_shot_scene_change", "intro"),
    ]
    for user_id, product_id, parent_callback, suggestion_callback, expected_back_step in cases:
        _open(user_id, product_id)
        if parent_callback:
            _press(user_id, parent_callback)
        _press(user_id, suggestion_callback)
        _press(user_id, "vproduct|microflow_custom_topic")
        _press(user_id, "vproduct|back")
        text, _markup, session = _press(user_id, "vproduct|back")
        assert session["product_id"] == product_id
        assert session["current_step"] == expected_back_step
        assert "Menu chính" not in text or expected_back_step == "intro"


def test_video_microflow_audit_catches_n5_contract():
    payload = bot.video_microflow_audit_payload()
    assert payload["ok"] is True
    checks = {row["name"]: row["ok"] for row in payload["checks"]}
    assert checks["suggestions_have_multiple_selectable_options"] is True
    assert checks["option_keyboard_not_single_use_direction"] is True
    assert checks["suggestion_buttons_show_options_before_count"] is True
