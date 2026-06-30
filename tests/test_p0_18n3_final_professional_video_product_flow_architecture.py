import asyncio
from types import SimpleNamespace

import bot


class FakeMessage:
    chat_id = 183000

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
    def __init__(self, file_id: str, mime_type: str):
        self.file_id = file_id
        self.mime_type = mime_type
        self.file_name = "media.mp4" if mime_type.startswith("video/") else "image.jpg"
        self.duration = 6
        self.file_size = 12345


class FakeQuery:
    def __init__(self, user_id: int, data: str):
        self.from_user = SimpleNamespace(id=user_id, first_name="P018N3")
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
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id))
    handled = asyncio.run(bot.handle_video_product_pending_text(update, SimpleNamespace()))
    assert handled is True
    assert message.replies
    reply = message.replies[-1]
    return reply["text"], reply.get("reply_markup"), bot.get_video_session(user_id)


def _send_media(user_id: int, *, kind: str):
    message = FakeMessage()
    if kind == "photo":
        message.photo = [FakeMedia(f"photo-{user_id}", "image/jpeg")]
    else:
        message.video = FakeMedia(f"video-{user_id}", "video/mp4")
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id))
    handled = asyncio.run(bot.handle_video_product_pending_media(update, SimpleNamespace()))
    assert handled is True
    assert message.replies
    reply = message.replies[-1]
    return reply["text"], reply.get("reply_markup"), bot.get_video_session(user_id)


def test_trend_entry_only_hot_and_manual_then_profile():
    text, markup, session = _open(183001, "video_trend")
    callbacks = set(_callbacks(markup))
    assert "Video theo trend" in text
    assert {"vproduct|trend_today", "vproduct|trend_custom"} <= callbacks
    assert "vproduct|trend_industry" not in callbacks
    assert "vproduct|trend_video_suggest" not in callbacks
    _press(183001, "vproduct|trend_custom")
    text, markup, session = _send_text(183001, "trend cafe cuối tuần")
    assert session["current_step"] == "profile_select"
    assert "Chọn loại video" in text


def test_video_ai_entry_has_three_subflows_and_suggestions_inside():
    text, markup, session = _open(183002, "video_ai_real")
    callbacks = set(_callbacks(markup))
    assert "Video AI chân thật" in text
    assert {"vproduct|ai_prompt_menu|video_ai_real", "vproduct|ai_image_menu|video_ai_real", "vproduct|ai_video_menu|video_ai_real"} <= callbacks
    assert "vproduct|suggest_prompt|video_ai_real" not in callbacks
    assert "vproduct|suggest_image|video_ai_real" not in callbacks
    assert "vproduct|suggest_video|video_ai_real" not in callbacks
    text, markup, session = _press(183002, "vproduct|ai_video_menu|video_ai_real")
    assert session["current_step"] == "ai_video_menu"
    assert "vproduct|suggest_video|video_ai_real" in _callbacks(markup)
    assert "Gợi ý video" not in _labels(bot.task3d_product_intro_keyboard("video_trend", "vi"))


def test_prompt_image_video_subflows_have_distinct_input_steps():
    _open(183003, "video_ai_real")
    _press(183003, "vproduct|ai_prompt_menu|video_ai_real")
    text, _markup, session = _press(183003, "vproduct|input_text|video_ai_real")
    assert session["current_step"] == "awaiting_prompt_text"
    assert "Gửi prompt" in text

    _open(183004, "video_ai_real")
    _press(183004, "vproduct|ai_image_menu|video_ai_real")
    text, _markup, session = _press(183004, "vproduct|input_media|video_ai_real")
    assert session["current_step"] == "awaiting_source_image"
    assert "Gửi ảnh" in text

    _open(183005, "video_ai_real")
    _press(183005, "vproduct|ai_video_menu|video_ai_real")
    text, _markup, session = _press(183005, "vproduct|entry_media|video_ai_real")
    assert session["current_step"] == "awaiting_reference_video"
    assert "video mẫu" in text.lower() or "Video mẫu" in text


def test_script_and_storyboard_are_not_same_flow():
    script_text, script_markup, _session = _open(183006, "script_image_video")
    storyboard_text, storyboard_markup, _session = _open(183007, "storyboard_prompt")
    assert "Kịch bản" in script_text
    assert "Storyboard" in storyboard_text
    assert "vproduct|script_existing|script_image_video" in _callbacks(script_markup)
    assert "vproduct|storyboard_upload|storyboard_prompt" in _callbacks(storyboard_markup)
    assert set(_callbacks(script_markup)).isdisjoint(set(_callbacks(storyboard_markup)) - {"menu|main", "menu|main_video"})


def test_image_to_video_accumulates_images_before_profile():
    _open(183008, "frame_video_local")
    text, _markup, session = _press(183008, "vproduct|frame_send_images|frame_video_local")
    assert session["current_step"] == "awaiting_multiple_images"
    assert "Gửi ảnh" in text
    _send_media(183008, kind="photo")
    text, markup, session = _press(183008, "vproduct|media_continue")
    assert session["current_step"] == "profile_select"
    assert "Chọn loại video" in text


def test_self_shot_requires_video_before_profile():
    _open(183009, "self_shot_scene_change")
    text, _markup, session = _press(183009, "vproduct|selfshot_source|upload")
    assert session["current_step"] == "awaiting_self_shot_video"
    assert "Gửi video" in text
    _send_media(183009, kind="video")
    session = bot.get_video_session(183009)
    assert session["current_step"] == "profile_select"
    assert session["draft"]["source_media_refs"]


def test_video_semantic_callback_microflow_audits_pass():
    assert bot.video_semantics_audit_payload()["ok"] is True
    assert bot.video_callback_audit_payload()["ok"] is True
    assert bot.video_microflow_audit_payload()["ok"] is True
