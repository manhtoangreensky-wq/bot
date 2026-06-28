import asyncio
import inspect
from types import SimpleNamespace

import bot
import video_image_to_video_flow as ivf


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


class _FakeMessage:
    chat_id = 1702

    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))
        return SimpleNamespace(text=text, kwargs=kwargs)


class _FakeQuery:
    def __init__(self, user_id: int, data: str):
        self.from_user = SimpleNamespace(id=user_id, first_name="P0B7", username="p0b7")
        self.data = data
        self.message = _FakeMessage()
        self.answered = False
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answered = True

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))
        return SimpleNamespace(text=text, kwargs=kwargs)


def _photo(idx: int):
    return {"file_id": f"photo-{idx}", "file_unique_id": f"uniq-{idx}", "file_size": 2048}


def _run_frame(user_id: int, data: str):
    query = _FakeQuery(user_id, data)
    asyncio.run(bot.handle_frame_video_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    return query


def _run_vproduct(user_id: int, data: str):
    query = _FakeQuery(user_id, data)
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    return query


def test_video_menu_hides_duplicate_image_to_video_button():
    labels = _labels(bot.main_video_keyboard("vi"))
    callbacks = _callbacks(bot.main_video_keyboard("vi"))
    assert "🖼 Ảnh → Video" not in labels
    assert "🖼 Ảnh thành video" in labels
    assert "vproduct|open|image_to_video" in callbacks


def test_video_menu_hides_legacy_merge_images_button():
    labels = _labels(bot.main_video_keyboard("vi"))
    callbacks = _callbacks(bot.main_video_keyboard("vi"))
    assert "🎞 Ghép ảnh thành video" not in labels
    assert "vproduct|open|frame_video_local" not in callbacks


def test_image_to_video_callback_opens_product_flow():
    user_id = 1702001
    bot.clear_video_session(user_id)
    bot.clear_frame_video_state(user_id)
    query = _run_vproduct(user_id, "vproduct|open|image_to_video")
    text = query.edits[-1][0]
    callbacks = _callbacks(query.edits[-1][1]["reply_markup"])
    session = bot.get_video_session(user_id)
    assert session["product_id"] == "image_to_video"
    assert session["current_step"] == "profile_select"
    assert "Chọn loại video" in text
    assert "framevideo|start" not in callbacks
    assert "framevideo|ai_first" not in callbacks


def test_merge_images_menu_has_two_paths():
    labels = _labels(ivf.frame_video_unified_menu_keyboard("vi"))
    text = ivf.frame_video_unified_menu_text("vi")
    assert "📷 Tôi có ảnh sẵn" in labels
    assert "🖼 Tạo ảnh AI trước" in labels
    assert "Local Worker + FFmpeg" in text
    assert "không gọi AI video" in text


def test_merge_images_existing_images_path_collects_images(monkeypatch):
    user_id = 1702002
    bot.clear_frame_video_state(user_id)
    monkeypatch.setattr(bot, "FRAME_VIDEO_ENABLED", True)
    monkeypatch.setattr(bot, "FRAME_VIDEO_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "FRAME_VIDEO_REQUIRE_LOCAL_WORKER", True)
    monkeypatch.setattr(bot, "frame_video_worker_connected", lambda: False)
    query = _run_frame(user_id, "framevideo|start")
    state = bot.get_frame_video_state(user_id)
    assert state["step"] == "collect"
    assert state["source"] == "existing_images"
    assert "Gửi từ 2 đến" in query.edits[-1][0]


def test_merge_images_default_effect_no_red_error(monkeypatch):
    user_id = 1702003
    monkeypatch.setattr(bot, "shopaikey_preview_final_cost", lambda _uid, base_cost, _event_type: int(base_cost or 0))
    bot.set_frame_video_state(user_id, {"step": "effect", "photos": [_photo(1), _photo(2)], "ratio": "9x16", "duration": "standard"})
    query = _run_frame(user_id, "framevideo|effect|default")
    text = query.edits[-1][0]
    assert "Có lỗi khi xử lý lệnh" not in text
    assert "Ghép ảnh thành video" in text


def test_merge_images_default_effect_goes_to_summary(monkeypatch):
    user_id = 1702004
    monkeypatch.setattr(bot, "shopaikey_preview_final_cost", lambda _uid, base_cost, _event_type: int(base_cost or 0))
    bot.set_frame_video_state(user_id, {"step": "effect", "photos": [_photo(1), _photo(2)]})
    query = _run_frame(user_id, "framevideo|effect|default")
    state = bot.get_frame_video_state(user_id)
    assert state["step"] == "confirm"
    assert state["effect"] == "fade"
    assert "Bot chỉ trừ Xu sau khi bạn xác nhận" in query.edits[-1][0]


def test_merge_images_requires_final_confirm_before_processing(monkeypatch):
    user_id = 1702005
    monkeypatch.setattr(bot, "shopaikey_preview_final_cost", lambda _uid, base_cost, _event_type: int(base_cost or 0))
    bot.set_frame_video_state(user_id, {"step": "effect", "photos": [_photo(1), _photo(2)]})
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("charged too early")))
    _run_frame(user_id, "framevideo|effect|default")
    state = bot.get_frame_video_state(user_id)
    assert state["step"] == "confirm"
    assert not state.get("paid_preview_seen")


def test_merge_images_no_ai_video_provider_call(monkeypatch):
    user_id = 1702006
    monkeypatch.setattr(bot, "shopaikey_preview_final_cost", lambda _uid, base_cost, _event_type: int(base_cost or 0))
    bot.set_frame_video_state(user_id, {"step": "effect", "photos": [_photo(1), _photo(2)]})
    if hasattr(bot, "shopaikey_workflow_image_to_video_create"):
        monkeypatch.setattr(bot, "shopaikey_workflow_image_to_video_create", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("AI video provider called")))
    if hasattr(bot, "shopaikey_video_create"):
        monkeypatch.setattr(bot, "shopaikey_video_create", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("AI video provider called")))
    _run_frame(user_id, "framevideo|effect|default")
    assert bot.get_frame_video_state(user_id)["step"] == "confirm"


def test_merge_images_no_charge_before_confirm(monkeypatch):
    user_id = 1702007
    monkeypatch.setattr(bot, "shopaikey_preview_final_cost", lambda _uid, base_cost, _event_type: int(base_cost or 0))
    bot.set_frame_video_state(user_id, {"step": "effect", "photos": [_photo(1), _photo(2)]})
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("charged too early")))
    _run_frame(user_id, "framevideo|effect|fade")
    assert bot.get_frame_video_state(user_id)["step"] == "confirm"


def test_merge_images_ai_first_path_uses_existing_image_core_guarded():
    user_id = 1702008
    query = _run_frame(user_id, "framevideo|ai_first")
    assert "Tạo ảnh AI trước đang được chuẩn bị" in query.edits[-1][0]
    assert "chưa trừ Xu" in query.edits[-1][0]


def test_merge_images_ai_first_handoff_to_effect_selection():
    user_id = 1702009
    state = ivf.frame_video_handoff_images_state([_photo(1), _photo(2)], source="ai_image_first", max_images=bot.FRAME_VIDEO_MAX_IMAGES)
    bot.set_frame_video_state(user_id, state)
    assert state["step"] == "effect"
    assert state["source"] == "ai_image_first"
    assert bot.get_frame_video_state(user_id)["step"] == "effect"


def test_merge_images_prompt_layout_helper_no_charge(monkeypatch):
    user_id = 1702010
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("charged from layout helper")))
    query = _run_frame(user_id, "framevideo|layout")
    assert "Gợi ý bố cục ảnh" in query.edits[-1][0]
    assert "chưa xử lý media và chưa trừ Xu" in query.edits[-1][0]


def test_video_menu_no_music_voice_sfx():
    labels = _labels(bot.main_video_keyboard("vi"))
    assert "🎵 Nhạc / Voice / SFX" not in labels


def test_video_menu_no_video_sample_channel():
    labels = _labels(bot.main_video_keyboard("vi"))
    assert "📥 Video mẫu / Kênh mẫu" not in labels


def test_video_menu_no_prompt_motion():
    labels = _labels(bot.main_video_keyboard("vi"))
    assert "🎥 Prompt / Chuyển động" not in labels


def test_translation_dub_studio_not_touched():
    source = inspect.getsource(bot.translation_voice_menu_keyboard)
    assert "framevideo|" not in source
    assert "vproduct|open|image_to_video" not in source


def test_image_flow_not_broken_by_video_handoff():
    callbacks = _callbacks(bot.video_ai_true_keyboard("vi"))
    assert "imagevideo|start" in callbacks
    state = ivf.frame_video_handoff_images_state([_photo(1), _photo(2)], source="ai_image_first", max_images=bot.FRAME_VIDEO_MAX_IMAGES)
    bot.set_frame_video_state(1702011, state)
    assert state["step"] == "effect"


def test_payment_pricing_not_touched():
    scoped_source = "\n".join(
        [
            inspect.getsource(ivf.frame_video_unified_menu_text),
            inspect.getsource(ivf.frame_video_unified_menu_keyboard),
            inspect.getsource(ivf.frame_video_apply_effect_defaults),
            inspect.getsource(ivf.frame_video_handoff_images_state),
        ]
    )
    forbidden = ("PAYOS", "naptien", "wallet", "ledger", "payment webhook")
    assert all(term.lower() not in scoped_source.lower() for term in forbidden)
