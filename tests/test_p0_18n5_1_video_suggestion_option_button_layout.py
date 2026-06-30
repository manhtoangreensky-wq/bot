import asyncio
from types import SimpleNamespace

import bot


NUMBER_LABELS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]


class FakeMessage:
    chat_id = 185100

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
        self.from_user = SimpleNamespace(id=user_id, first_name="P018N51")
        self.data = data
        self.message = FakeMessage()
        self.edits = []

    async def answer(self, *args, **kwargs):
        return None

    async def edit_message_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.edits.append(item)
        return SimpleNamespace(**item)


def _press(user_id: int, callback: str):
    query = FakeQuery(user_id, callback)
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert query.edits
    edit = query.edits[-1]
    return edit["text"], edit.get("reply_markup"), bot.get_video_session(user_id)


def _open(user_id: int, product_id: str):
    bot.clear_video_session(user_id)
    return _press(user_id, f"vproduct|open|{product_id}")


def _row_labels(markup, row_index: int = 0) -> list[str]:
    return [button.text for button in markup.inline_keyboard[row_index]]


def _row_callbacks(markup, row_index: int = 0) -> list[str]:
    return [button.callback_data for button in markup.inline_keyboard[row_index]]


def _all_labels(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def _all_callbacks(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def _assert_number_option_row(markup, expected_count: int):
    expected = NUMBER_LABELS[:expected_count]
    assert _row_labels(markup) == expected
    assert _row_callbacks(markup) == [f"vproduct|microflow_choose|{index}" for index in range(expected_count)]


def _assert_aux_buttons_below(markup):
    callbacks = _all_callbacks(markup)
    assert callbacks.index("vproduct|microflow_regenerate") > 0
    assert callbacks.index("vproduct|microflow_custom_topic") > 0
    assert callbacks.index("vproduct|back") > 0
    assert callbacks.index("menu|main") > 0


def _suggestion_screen(user_id: int, product_id: str, parent_callback: str | None, suggestion_callback: str):
    _open(user_id, product_id)
    if parent_callback:
        _press(user_id, parent_callback)
    return _press(user_id, suggestion_callback)


def test_trend_suggestion_option_buttons_single_row_1_to_5():
    _open(185101, "video_trend")
    _text, markup, session = _press(185101, "vproduct|trend_today")
    count = len((session.get("draft") or {}).get("trend_ideas") or [])
    assert count >= 3
    assert _row_labels(markup) == [str(index) for index in range(1, min(5, count) + 1)]
    assert _row_callbacks(markup) == [f"vproduct|trend_select|{index}" for index in range(min(5, count))]


def test_prompt_suggestion_option_buttons_single_row_1_to_5():
    _text, markup, _session = _suggestion_screen(185102, "video_ai_real", "vproduct|ai_prompt_menu|video_ai_real", "vproduct|suggest_prompt|video_ai_real")
    _assert_number_option_row(markup, 5)


def test_image_suggestion_option_buttons_single_row_1_to_5():
    _text, markup, _session = _suggestion_screen(185103, "video_ai_real", "vproduct|ai_image_menu|video_ai_real", "vproduct|suggest_image|video_ai_real")
    _assert_number_option_row(markup, 5)


def test_video_reference_suggestion_option_buttons_single_row_1_to_5():
    _text, markup, _session = _suggestion_screen(185104, "video_ai_real", "vproduct|ai_video_menu|video_ai_real", "vproduct|suggest_video|video_ai_real")
    _assert_number_option_row(markup, 5)


def test_script_suggestion_option_buttons_single_row_1_to_5():
    _text, markup, _session = _suggestion_screen(185105, "script_image_video", None, "vproduct|script_ideas|script_image_video")
    _assert_number_option_row(markup, 5)


def test_storyboard_suggestion_option_buttons_single_row():
    _text, markup, _session = _suggestion_screen(185106, "storyboard_prompt", None, "vproduct|storyboard_suggest|storyboard_prompt")
    _assert_number_option_row(markup, 3)


def test_image_to_video_suggestion_option_buttons_single_row():
    _text, markup, _session = _suggestion_screen(185107, "frame_video_local", None, "vproduct|frame_suggest_image|frame_video_local")
    _assert_number_option_row(markup, 3)


def test_idea_suggestion_option_buttons_single_row_1_to_5():
    _text, markup, _session = _suggestion_screen(185108, "video_idea", None, "vproduct|idea_quick|video_idea")
    _assert_number_option_row(markup, 5)


def test_self_shot_suggestion_option_buttons_single_row_1_to_5():
    _text, markup, _session = _suggestion_screen(185109, "self_shot_scene_change", None, "vproduct|selfshot_ideas|self_shot_scene_change")
    _assert_number_option_row(markup, 5)


def test_film_suggestion_option_buttons_single_row_1_to_5():
    _text, markup, _session = _suggestion_screen(185110, "multi_scene_film", None, "vproduct|film_story|multi_scene_film")
    _assert_number_option_row(markup, 5)


def test_option_callbacks_still_select_correct_item():
    _text, markup, session = _suggestion_screen(185111, "video_ai_real", "vproduct|ai_prompt_menu|video_ai_real", "vproduct|suggest_prompt|video_ai_real")
    assert _row_callbacks(markup) == [f"vproduct|microflow_choose|{index}" for index in range(5)]
    original_options = list((session.get("draft") or {}).get("microflow_options") or [])
    _press(185111, "vproduct|microflow_choose|3")
    selected_session = bot.get_video_session(185111)
    assert selected_session["draft"]["microflow_selected_index"] == 3
    assert bot.video_microflow_selected_option(selected_session)["title"] == original_options[3]["title"]


def test_no_long_option_labels_like_dung_y_tuong_1():
    cases = [
        ("video_ai_real", "vproduct|ai_prompt_menu|video_ai_real", "vproduct|suggest_prompt|video_ai_real"),
        ("video_ai_real", "vproduct|ai_image_menu|video_ai_real", "vproduct|suggest_image|video_ai_real"),
        ("video_ai_real", "vproduct|ai_video_menu|video_ai_real", "vproduct|suggest_video|video_ai_real"),
        ("script_image_video", None, "vproduct|script_ideas|script_image_video"),
        ("storyboard_prompt", None, "vproduct|storyboard_suggest|storyboard_prompt"),
        ("frame_video_local", None, "vproduct|frame_suggest_image|frame_video_local"),
        ("video_idea", None, "vproduct|idea_quick|video_idea"),
        ("self_shot_scene_change", None, "vproduct|selfshot_ideas|self_shot_scene_change"),
        ("multi_scene_film", None, "vproduct|film_story|multi_scene_film"),
    ]
    forbidden = ("Dùng ý tưởng", "Dùng prompt", "Dùng ảnh", "Dùng hướng", "Dùng kịch bản", "Dùng storyboard", "Dùng cốt truyện")
    for offset, (product_id, parent_callback, suggestion_callback) in enumerate(cases):
        _text, markup, _session = _suggestion_screen(185120 + offset, product_id, parent_callback, suggestion_callback)
        labels = _all_labels(markup)
        assert not any(any(word in label for word in forbidden) for label in labels)


def test_aux_buttons_remain_below_option_row():
    _text, markup, _session = _suggestion_screen(185140, "video_ai_real", "vproduct|ai_prompt_menu|video_ai_real", "vproduct|suggest_prompt|video_ai_real")
    _assert_number_option_row(markup, 5)
    _assert_aux_buttons_below(markup)
