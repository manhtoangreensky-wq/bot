import asyncio
import io
import inspect
from types import SimpleNamespace

import bot


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


class CaptureMessage:
    def __init__(self, text="", user_id=997700):
        self.text = text
        self.chat_id = user_id
        self.message_id = 1
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"text": str(text), **kwargs})
        return SimpleNamespace(text=text)


class CaptureQuery:
    def __init__(self, data, user_id=997700):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id, first_name="Logo test")
        self.message = CaptureMessage(user_id=user_id)
        self.outputs = self.message.outputs

    async def answer(self, *args, **kwargs):
        return None

    async def edit_message_text(self, text, **kwargs):
        self.outputs.append({"text": str(text), **kwargs})
        return SimpleNamespace(text=text)


def _callback_update(query, user_id):
    return SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=user_id))


def _message_update(message, user_id):
    return SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id))


def test_image_flow_has_logo_watermark_step():
    callbacks = _callbacks(bot.quick_image_logo_choice_keyboard("vi"))
    assert callbacks == [
        "create_media|qi_logo_add",
        "create_media|qi_logo_skip",
        "create_media|qi_back_prompt",
        "menu|main",
    ]
    assert "logo_choice" in bot.QUICK_IMAGE_FLOW_STEPS
    assert "logo_position" in bot.QUICK_IMAGE_FLOW_STEPS


def test_image_logo_watermark_skip_works():
    user_id = 997701
    bot.clear_quick_image_flow(user_id)
    bot.set_quick_image_flow(user_id, "logo_choice", prompt="Ảnh sản phẩm", logo_watermark_decided=False)
    query = CaptureQuery("create_media|qi_logo_skip", user_id)
    asyncio.run(bot.handle_create_media_callback(_callback_update(query, user_id), SimpleNamespace()))
    state = bot.get_quick_image_flow(user_id)
    assert state["step"] == "ratio"
    assert state["logo_watermark_enabled"] is False
    assert state["logo_watermark_text"] == ""
    assert state["logo_watermark_position"] == ""
    bot.clear_quick_image_flow(user_id)


def test_image_logo_watermark_input_confirm_works():
    user_id = 997702
    bot.clear_quick_image_flow(user_id)
    bot.set_quick_image_flow(user_id, "logo_input", prompt="Ảnh sản phẩm")
    message = CaptureMessage("TOAN AAS", user_id)
    assert asyncio.run(bot.handle_quick_image_flow_pending_text(_message_update(message, user_id), SimpleNamespace())) is True
    state = bot.get_quick_image_flow(user_id)
    assert state["step"] == "logo_position"
    query = CaptureQuery("create_media|qi_logo_pos|top_left", user_id)
    asyncio.run(bot.handle_create_media_callback(_callback_update(query, user_id), SimpleNamespace()))
    assert bot.get_quick_image_flow(user_id)["step"] == "logo_confirm"
    query = CaptureQuery("create_media|qi_logo_confirm", user_id)
    asyncio.run(bot.handle_create_media_callback(_callback_update(query, user_id), SimpleNamespace()))
    state = bot.get_quick_image_flow(user_id)
    assert state["step"] == "ratio"
    assert state["logo_watermark_enabled"] is True
    assert state["logo_watermark_text"] == "TOAN AAS"
    assert state["logo_watermark_position"] == "top_left"
    bot.clear_quick_image_flow(user_id)


def test_image_logo_watermark_back_routing_correct():
    assert _callbacks(bot.quick_image_logo_input_keyboard("vi")) == ["create_media|qi_logo_choice", "menu|main"]
    assert _callbacks(bot.quick_image_logo_confirm_keyboard("vi")) == ["create_media|qi_logo_confirm", "create_media|qi_logo_add"]
    assert _callbacks(bot.task3d_prompt_image_logo_input_keyboard("vi")) == ["vproduct|prompt_image_logo_choice", "menu|main"]
    assert _callbacks(bot.task3d_prompt_image_logo_confirm_keyboard("vi")) == ["vproduct|prompt_image_logo_confirm", "vproduct|prompt_image_logo_add"]
    assert _callbacks(bot.image_prompt_confirm_keyboard("token", "low", "vi", "image_edit_create_new"))[1:3] == [
        "create_media|ia_token",
        "imgtool|edit_create_new",
    ]


def test_image_prompt_and_edit_routes_enter_logo_step_with_exact_back():
    source = inspect.getsource(bot.handle_image_tools_callback)
    assert 'logo_watermark_back_callback="imgtool|prompt_use"' in source
    assert 'logo_watermark_back_callback="imgtool|edit_create_new"' in source
    assert source.count('media_logo_watermark_choice_text("image", prompt, lang)') >= 2


def test_existing_image_aspect_is_preserved_through_logo_step():
    user_id = 997705
    bot.clear_media_aspect_pending(user_id)
    bot.set_media_aspect_pending(
        user_id,
        "image",
        "low",
        "Ảnh sản phẩm",
        selected_aspect_ratio="4:5",
        logo_watermark_back_callback="imgtool|prompt_use",
        confirmation_source="image_prompt_tool",
    )
    pending = bot.get_media_aspect_pending(user_id, "image")
    assert pending["selected_aspect_ratio"] == "4:5"
    assert pending["logo_watermark_back_callback"] == "imgtool|prompt_use"
    assert pending["confirmation_source"] == "image_prompt_tool"
    bot.clear_media_aspect_pending(user_id)


def test_video_tools_has_logo_watermark_button():
    labels = _labels(bot.video_finalization_menu_keyboard("vi"))
    callbacks = _callbacks(bot.video_finalization_menu_keyboard("vi"))
    assert "🎭 Logo / Watermark" in labels
    assert "vfinal|logo" in callbacks


def test_video_logo_watermark_input_screen_opens():
    user_id = 997703
    bot.clear_video_finalization_state(user_id)
    bot.set_video_finalization_state(user_id, {
        "step": "menu",
        "source": "storyboard_prompt",
        "selected_video_aspect_ratio": "9:16",
        "aspect_source": "user_selected",
        "source_payload": {"video_prompt": "Video sản phẩm"},
    })
    query = CaptureQuery("vfinal|logo", user_id)
    asyncio.run(bot.handle_video_finalization_callback(_callback_update(query, user_id), SimpleNamespace()))
    assert bot.get_video_finalization_state(user_id)["step"] == "await_logo_watermark"
    assert "Logo / Watermark" in query.outputs[-1]["text"]
    bot.clear_video_finalization_state(user_id)


def test_video_logo_watermark_confirm_returns_to_tools():
    user_id = 997704
    bot.clear_video_finalization_state(user_id)
    bot.set_video_finalization_state(user_id, {
        "step": "await_logo_watermark",
        "source": "storyboard_prompt",
        "selected_video_aspect_ratio": "9:16",
        "aspect_source": "user_selected",
        "source_payload": {"video_prompt": "Video sản phẩm"},
    })
    message = CaptureMessage("TOAN AAS", user_id)
    assert asyncio.run(bot.handle_video_finalization_pending_text(_message_update(message, user_id), SimpleNamespace())) is True
    assert bot.get_video_finalization_state(user_id)["step"] == "logo_watermark_position"
    query = CaptureQuery("vfinal|logo_pos|bottom_right", user_id)
    asyncio.run(bot.handle_video_finalization_callback(_callback_update(query, user_id), SimpleNamespace()))
    assert bot.get_video_finalization_state(user_id)["step"] == "logo_watermark_confirm"
    query = CaptureQuery("vfinal|logo_confirm", user_id)
    asyncio.run(bot.handle_video_finalization_callback(_callback_update(query, user_id), SimpleNamespace()))
    state = bot.get_video_finalization_state(user_id)
    assert state["step"] == "menu"
    assert state["video_finalization"]["logo_watermark_enabled"] is True
    assert state["video_finalization"]["logo_watermark_position"] == "bottom_right"
    bot.clear_video_finalization_state(user_id)


def test_video_logo_watermark_back_routing_correct():
    assert _callbacks(bot.video_finalization_logo_input_keyboard("vi")) == ["vfinal|menu", "vfinal|main"]
    assert _callbacks(bot.video_finalization_logo_confirm_keyboard("vi")) == ["vfinal|logo_confirm", "vfinal|logo"]
    position_callbacks = _callbacks(bot.video_finalization_logo_position_keyboard("vi"))
    assert position_callbacks[-2:] == ["vfinal|logo", "vfinal|main"]


def test_logo_watermark_no_xu_charge():
    base = bot.calculate_video_quote({"video_tier": "basic", "selected_scene_count": 3})
    with_logo = bot.calculate_video_quote({
        "video_tier": "basic",
        "selected_scene_count": 3,
        "video_finalization": bot.logo_watermark_session_fields(True, "TOAN AAS", "top_left"),
    })
    assert with_logo["addon_fee_xu"] == base["addon_fee_xu"] == 0
    assert with_logo["total_xu"] == base["total_xu"]


def test_logo_watermark_no_provider_call(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("logo/watermark planning must not call a provider")

    monkeypatch.setattr(bot, "shopaikey_image_generate", forbidden)
    monkeypatch.setattr(bot, "submit_public_video_with_key4u_fallback", forbidden)
    assert bot.logo_watermark_session_fields(True, "TOAN AAS", "top_left")["logo_watermark_enabled"] is True
    assert "top left" in bot.apply_logo_watermark_to_prompt("Product image.", "TOAN AAS", "image", "top_left")


def test_logo_watermark_saved_in_session():
    fields = bot.logo_watermark_session_fields(True, "TOAN AAS", "center")
    assert fields == {
        "logo_watermark_enabled": True,
        "logo_watermark_text": "TOAN AAS",
        "logo_watermark_position": "center",
        "logo_watermark_source": "text",
    }


def test_existing_image_flow_not_broken():
    assert "create_media|qi_choose_ratio" in _callbacks(bot.quick_image_prepared_prompt_keyboard("vi"))
    assert "create_media|qi_ratio_4x5" in _callbacks(bot.quick_image_ratio_keyboard("vi"))
    assert "create_media|qi_tier_low" in _callbacks(bot.quick_image_tier_keyboard("vi"))


def test_existing_video_flow_not_reordered():
    menu_callbacks = _callbacks(bot.video_finalization_menu_keyboard("vi"))
    assert menu_callbacks[:4] == ["vfinal|voice", "vfinal|music", "vfinal|addon", "vfinal|logo"]
    assert "vfinal|tier|basic" in _callbacks(bot.video_finalization_tier_keyboard("vi"))
    assert "vfinal|scene_count|3" in _callbacks(bot.video_finalization_scene_count_keyboard({"selected_video_tier": "basic"}, "vi"))


def test_logo_watermark_position_supported_across_image_video():
    assert bot.image_editor_overlay_xy(1000, 800, 100, 50, "top_left", 20) == (20, 20)
    assert bot.image_editor_overlay_xy(1000, 800, 100, 50, "center", 20) == (450, 375)
    assert bot.image_editor_overlay_xy(1000, 800, 100, 50, "bottom_right", 20) == (880, 730)
    assert "bottom right" in bot.logo_watermark_prompt_instruction("video", "TOAN AAS", "bottom_right")


def test_image_editor_applies_selected_logo_position():
    if bot.Image is None:
        return
    base = bot.Image.new("RGB", (400, 300), (255, 255, 255))
    base_buffer = io.BytesIO()
    base.save(base_buffer, format="PNG")
    logo = bot.Image.new("RGB", (40, 20), (255, 0, 0))
    logo_buffer = io.BytesIO()
    logo.save(logo_buffer, format="PNG")
    ok_top, top_bytes, _, _ = bot.process_image_local_editor_bytes(
        base_buffer.getvalue(),
        "photo_clear_detail",
        logo_bytes=logo_buffer.getvalue(),
        overlay_position="top_left",
    )
    ok_bottom, bottom_bytes, _, _ = bot.process_image_local_editor_bytes(
        base_buffer.getvalue(),
        "photo_clear_detail",
        logo_bytes=logo_buffer.getvalue(),
        overlay_position="bottom_right",
    )
    assert ok_top is True and ok_bottom is True
    with bot.Image.open(io.BytesIO(top_bytes)) as top_image, bot.Image.open(io.BytesIO(bottom_bytes)) as bottom_image:
        assert top_image.getpixel((20, 20))[0] > top_image.getpixel((20, 20))[1]
        assert bottom_image.getpixel((20, 20)) == (255, 255, 255)
        assert bottom_image.getpixel((350, 270))[0] > bottom_image.getpixel((350, 270))[1]


def test_no_payos_touched():
    sources = "\n".join([
        inspect.getsource(bot.logo_watermark_session_fields),
        inspect.getsource(bot.handle_media_logo_watermark_pending_text),
        inspect.getsource(bot.video_finalization_logo_position_keyboard),
    ]).lower()
    assert "payos" not in sources
    assert "payment" not in sources


def test_no_provider_internals_touched():
    sources = "\n".join([
        inspect.getsource(bot.logo_watermark_prompt_instruction),
        inspect.getsource(bot.apply_logo_watermark_to_prompt),
        inspect.getsource(bot.image_editor_overlay_xy),
    ]).lower()
    assert "key4u" not in sources
    assert "shopaikey" not in sources
    assert "http" not in sources
