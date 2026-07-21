import asyncio
from types import SimpleNamespace

import bot


def _callbacks(markup):
    return {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }


class FakeQuery:
    def __init__(self, data: str, user_id: int = 990401):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id, username="story_user", first_name="Story User")
        self.message = FakeMessage("")
        self.message.chat_id = user_id
        self.edited = None

    async def answer(self, *args, **kwargs):
        return None

    async def edit_message_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        self.edited = {"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup}
        return self.edited


class FakeMessage:
    def __init__(self, text: str):
        self.text = text
        self.replies = []

    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        payload = {"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup}
        self.replies.append(payload)
        return payload


async def _press(data: str, user_id: int = 990401):
    query = FakeQuery(data, user_id)
    await bot.handle_storyboard_pack_callback(SimpleNamespace(callback_query=query), SimpleNamespace())
    with_markup = [reply for reply in query.message.replies if reply.get("reply_markup")]
    if with_markup:
        payload = dict(with_markup[-1])
        texts = []
        if query.edited:
            texts.append(str(query.edited.get("text") or ""))
        texts.extend(str(reply.get("text") or "") for reply in query.message.replies)
        payload["text"] = "\n".join(text for text in texts if text)
        return payload
    return query.edited or (query.message.replies[-1] if query.message.replies else None)


async def _send_text(text: str, user_id: int = 990401):
    message = FakeMessage(text)
    update = SimpleNamespace(
        message=message,
        effective_user=SimpleNamespace(id=user_id, username="story_user", first_name="Story User"),
    )
    handled = await bot.handle_developing_video_pending_text(update, SimpleNamespace())
    assert handled is True
    assert message.replies
    return message.replies[-1]


def test_storyboard_entry_opens_template_menu(monkeypatch):
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    text = bot.storyboard_pack_start_text("vi")
    callbacks = _callbacks(bot.storyboard_pack_start_keyboard("vi"))

    assert "Storyboard" in text
    assert "TOAN AAS chưa xử lý video và chưa trừ Xu" in text
    assert {
        "storypack|template|product_ad",
        "storypack|template|cinematic_story",
        "storypack|template|tiktok_reels",
        "storypack|template|tutorial",
        "storypack|template|shop_affiliate",
        "storypack|template|custom",
        "menu|main_video",
    }.issubset(callbacks)


def test_storyboard_topic_state_and_three_concepts(monkeypatch):
    uid = 990402
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    bot.clear_developing_video_pending(uid)

    template = asyncio.run(_press("storypack|template|product_ad", uid))
    assert "Quảng cáo sản phẩm" in template["text"]
    assert bot.get_developing_video_pending(uid)["step"] == "topic"

    brief = asyncio.run(_send_text("nước hoa nam cao cấp", uid))
    assert "Thiết lập nhanh" in brief["text"]
    assert bot.get_developing_video_pending(uid)["step"] == "brief"
    brief_callbacks = _callbacks(brief["reply_markup"])
    assert {
        "storypack|set_platform|TikTok/Reels",
        "storypack|set_ratio|9:16",
        "storypack|set_duration|30s",
        "storypack|set_style|cinematic",
        "storypack|set_goal|bán hàng",
        "storypack|generate_concepts",
    }.issubset(brief_callbacks)

    concepts = asyncio.run(_press("storypack|generate_concepts", uid))
    assert "3 hướng storyboard" in concepts["text"]
    assert "Concept 1" in concepts["text"]
    callbacks = _callbacks(concepts["reply_markup"])
    assert {"storypack|concept|1", "storypack|concept|2", "storypack|concept|3", "storypack|regenerate_concepts"}.issubset(callbacks)
    assert "storypack|back_brief" in callbacks
    assert "TOAN AAS chỉ bắt đầu xử lý sau khi quý khách xác nhận ở bước cuối" in concepts["text"]


def test_storyboard_concept_generates_required_scene_pack(monkeypatch):
    uid = 990403
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    state = {
        "reference_template": "product_ad",
        "selected_topic": "nước hoa nam cao cấp",
        "selected_suggestion_index": 2,
        "duration": "30s",
        "preferred_aspect_ratio": "9:16",
        "selected_style": "luxury",
        "goal": "bán hàng",
    }
    plan = bot.save_developing_video_plan(uid, "storypack", state)
    text = bot.storyboard_pack_result_text(plan, "vi")

    for expected in [
        "Storyboard chi tiết",
        "Kế hoạch từng cảnh, câu lệnh ảnh và câu lệnh video",
        "Cảnh 1",
        "Mục tiêu cảnh",
        "Nội dung hình ảnh",
        "Hành động chính",
        "Góc máy",
        "Chuyển động camera",
        "Ánh sáng",
        "Bối cảnh",
        "Text overlay/caption",
        "Voice/script gợi ý",
        "Nhạc/SFX gợi ý",
        "Prompt ảnh",
        "Prompt video",
        "Negative prompt",
        "Chuyển cảnh",
        "Kết thúc",
        "Caption ngắn",
        "Hashtag gợi ý",
        "Visual canon dùng xuyên suốt",
        "TOAN AAS chỉ bắt đầu xử lý sau khi quý khách xác nhận ở bước cuối",
    ]:
        assert expected in text

    callbacks = _callbacks(bot.storyboard_pack_result_keyboard("vi"))
    assert "vfinal|export_local" not in callbacks
    assert {"storypack|image_prompts", "storypack|video_prompts", "storypack|meta_ai_prompt", "storypack|copy_plan", "storypack|create_video_ai"}.issubset(callbacks)


def test_storyboard_prompt_views_and_video_guard(monkeypatch):
    uid = 990404
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    bot.save_developing_video_plan(uid, "storypack", {
        "reference_template": "cinematic_story",
        "selected_topic": "bot AI tự động hóa cho shop online",
        "selected_suggestion_index": 1,
        "duration": "30s",
    })

    image_prompts = asyncio.run(_press("storypack|image_prompts", uid))
    assert "Prompt ảnh từng cảnh" in image_prompts["text"]
    assert "Subject/setting" in image_prompts["text"]
    image_callbacks = _callbacks(image_prompts["reply_markup"])
    assert "storypack|back_detail" in image_callbacks
    assert "storypack|regenerate_image_prompts" in image_callbacks
    assert "storypack|video_prompts" in image_callbacks

    video_prompts = asyncio.run(_press("storypack|video_prompts", uid))
    assert "Prompt video từng cảnh" in video_prompts["text"]
    assert "Camera/motion" in video_prompts["text"]
    video_callbacks = _callbacks(video_prompts["reply_markup"])
    assert "storypack|back_detail" in video_callbacks
    assert "storypack|regenerate_video_prompts" in video_callbacks
    assert "storypack|image_prompts" in video_callbacks

    meta = asyncio.run(_press("storypack|meta_ai_prompt", uid))
    assert "3 prompt Meta AI" in meta["text"]
    assert "TOAN AAS chỉ chuẩn bị prompt" in meta["text"]
    assert "Caption gợi ý" in meta["text"]
    assert {"storypack|copy_meta_1", "storypack|copy_meta_2", "storypack|copy_meta_3", "storypack|regenerate_meta_ai_prompts"}.issubset(_callbacks(meta["reply_markup"]))

    guard = asyncio.run(_press("storypack|create_video_ai", uid))
    assert "Hệ thống tạo video đang bảo trì/nâng cấp nhẹ" in guard["text"]
    assert "chưa bắt đầu xử lý và chưa trừ Xu" in guard["text"]
    assert "TOAN AAS chưa bắt đầu xử lý" in guard["text"]
    guard_callbacks = _callbacks(guard["reply_markup"])
    assert "storypack|back_detail" in guard_callbacks
    assert "vfinal|export_local" not in guard_callbacks


def test_storyboard_product_ad_manual_path_v2(monkeypatch):
    uid = 990405
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    bot.clear_developing_video_pending(uid)

    entry = asyncio.run(_press("storypack|start", uid))
    assert "Storyboard" in entry["text"]
    assert "menu|main_video" in _callbacks(entry["reply_markup"])

    template = asyncio.run(_press("storypack|template|product_ad", uid))
    assert "Quảng cáo sản phẩm" in template["text"]
    assert bot.get_developing_video_pending(uid)["step"] == "topic"

    brief = asyncio.run(_send_text("nước hoa nam cao cấp", uid))
    assert "Thiết lập nhanh" in brief["text"]

    concepts = asyncio.run(_press("storypack|generate_concepts", uid))
    assert "Concept 1" in concepts["text"]
    assert "Concept 2" in concepts["text"]
    assert "Concept 3" in concepts["text"]

    detail = asyncio.run(_press("storypack|concept|1", uid))
    assert "Storyboard chi tiết" in detail["text"]
    for expected in ["Cảnh 1", "Prompt ảnh", "Prompt video", "Negative prompt", "Góc máy", "Chuyển động camera", "Ánh sáng"]:
        assert expected in detail["text"]
    detail_callbacks = _callbacks(detail["reply_markup"])
    assert "storypack|video_prompts" in detail_callbacks
    assert "storypack|image_prompts" in detail_callbacks
    assert "storypack|meta_ai_prompt" in detail_callbacks
    assert "storypack|back_concepts" in detail_callbacks
    assert "vfinal|export_local" not in detail_callbacks

    video_prompts = asyncio.run(_press("storypack|video_prompts", uid))
    assert "Prompt video từng cảnh" in video_prompts["text"]
    assert "storypack|back_detail" in _callbacks(video_prompts["reply_markup"])

    back_detail = asyncio.run(_press("storypack|back_detail", uid))
    assert "Storyboard chi tiết" in back_detail["text"]

    meta = asyncio.run(_press("storypack|meta_ai_prompt", uid))
    assert "3 prompt Meta AI" in meta["text"]
    assert "TOAN AAS chỉ chuẩn bị prompt" in meta["text"]

    video_guard = asyncio.run(_press("storypack|create_video_ai", uid))
    assert "Hệ thống tạo video đang bảo trì/nâng cấp nhẹ" in video_guard["text"]
    assert "storypack|back_detail" in _callbacks(video_guard["reply_markup"])
    assert "vfinal|export_local" not in _callbacks(video_guard["reply_markup"])

    image_guard = asyncio.run(_press("storypack|create_or_upload_images", uid))
    assert "Tạo/gửi ảnh trước" in image_guard["text"]
    assert "storypack|image_prompts" in _callbacks(image_guard["reply_markup"])
    assert "storypack|upload_images_guard" in _callbacks(image_guard["reply_markup"])
