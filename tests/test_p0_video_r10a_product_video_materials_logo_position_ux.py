import asyncio
import json
from types import SimpleNamespace

import bot


class FakeMessage:
    chat_id = 910100
    message_id = 1

    def __init__(self, text: str = ""):
        self.text = text
        self.photo = None
        self.video = None
        self.document = None
        self.audio = None
        self.voice = None
        self.caption = ""
        self.replies = []

    async def reply_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.replies.append(item)
        return SimpleNamespace(**item)


class FakeQuery:
    def __init__(self, user_id: int, data: str):
        self.from_user = SimpleNamespace(id=user_id, first_name="R10A")
        self.data = data
        self.message = FakeMessage()
        self.edits = []

    async def answer(self, *args, **kwargs):
        return None

    async def edit_message_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.edits.append(item)
        return SimpleNamespace(**item)


class FakeMedia:
    def __init__(self, file_id: str = "logo-file"):
        self.file_id = file_id
        self.file_unique_id = file_id
        self.file_size = 1024
        self.mime_type = "image/jpeg"
        self.file_name = "logo.jpg"


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


def _seed_assets(user_id: int):
    bot.clear_video_session(user_id)
    session = bot.task3d_session_step(
        user_id,
        "asset_intake",
        product_id="video_ai_real",
        topic="trailer thương hiệu",
        provider_called=False,
        xu_charged=0,
    )
    return bot.video_b14_set_profile(user_id, session, "cinematic_trailer")


def _send_logo(user_id: int, file_id: str = "logo-file"):
    message = FakeMessage()
    message.photo = [FakeMedia(file_id)]
    update = SimpleNamespace(effective_user=SimpleNamespace(id=user_id), message=message)
    handled = asyncio.run(bot.handle_video_product_pending_media(update, SimpleNamespace()))
    assert handled is True
    assert message.replies
    reply = message.replies[-1]
    return reply["text"], reply.get("reply_markup"), bot.get_video_session(user_id)


def test_materials_screen_hides_old_i_have_images_button():
    labels = _labels(bot.video_asset_intake_keyboard("vi"))
    assert "📷 Tôi có ảnh sẵn" not in labels
    for expected in (
        "🖼 Tạo ảnh AI trước",
        "📚 Gợi ý bố cục ảnh",
        "🎨 Dùng prompt ảnh từ storyboard",
        "📸 Gửi ảnh nhân vật/sản phẩm",
        "🏞 Gửi ảnh bối cảnh",
        "🧩 Gửi ảnh storyboard",
        "🏷 Gửi logo",
        "🎙 Gửi voice/audio",
        "🎵 Gửi nhạc nền",
        "⏭ Bỏ qua",
        "✅ Xong phần tư liệu",
    ):
        assert expected in labels


def test_legacy_subject_asset_callback_still_routes_to_specific_image_upload():
    user_id = 910101
    _seed_assets(user_id)
    text, markup, session = _press(user_id, "vproduct|asset_wait|subject")
    assert "gửi file tư liệu" in text.lower()
    assert session["current_step"] == "asset_intake"
    assert session["draft"]["asset_waiting_for"] == "subject"
    assert session["draft"]["pending_asset_type"] == "subject_reference"
    assert "vproduct|asset_intro" in _callbacks(markup)


def test_send_logo_then_receive_image_shows_six_position_screen():
    user_id = 910102
    _seed_assets(user_id)
    text, _markup, session = _press(user_id, "vproduct|asset_wait|logo")
    assert "gửi ảnh logo" in text.lower()
    assert session["draft"]["pending_asset_type"] == "logo"
    text, markup, session = _send_logo(user_id, "logo-position-file")
    callbacks = set(_callbacks(markup))
    assert "Chọn vị trí logo" in text
    assert session["current_step"] == "asset_logo_position"
    for position in bot.PRODUCT_VIDEO_LOGO_POSITIONS:
        assert f"vproduct|asset_logo_position|{position}" in callbacks
    assert "vproduct|asset_logo_none" in callbacks
    assert "vproduct|asset_intro" in callbacks


def test_each_logo_position_saves_enum_and_small_ratio():
    for index, position in enumerate(bot.PRODUCT_VIDEO_LOGO_POSITIONS, start=1):
        user_id = 910200 + index
        _seed_assets(user_id)
        _press(user_id, "vproduct|asset_wait|logo")
        _send_logo(user_id, f"logo-{position}")
        _press(user_id, f"vproduct|asset_logo_position|{position}")
        material = bot.product_video_logo_material_from_session(bot.get_video_session(user_id))
        assert material["logo_enabled"] is True
        assert material["logo_file_id"] == f"logo-{position}"
        assert material["logo_position"] == position
        assert material["logo_width_ratio"] == 0.12
        assert material["logo_max_width_ratio"] == 0.18
        assert material["logo_margin_x_ratio"] == 0.04
        assert material["logo_margin_y_ratio"] == 0.035
        assert material["logo_preserve_aspect_ratio"] is True
        assert material["logo_overlay_applied"] is False


def test_invoice_logo_copy_only_when_logo_exists():
    user_id = 910303
    session = _seed_assets(user_id)
    no_logo_invoice = bot.video_b14_invoice_text(session, user_id, "vi")
    assert "Logo:" not in no_logo_invoice
    _press(user_id, "vproduct|asset_wait|logo")
    _send_logo(user_id, "invoice-logo")
    _press(user_id, "vproduct|asset_logo_position|top_right")
    text = bot.video_b14_invoice_text(bot.get_video_session(user_id), user_id, "vi")
    assert "Logo: bật · vị trí Trên phải · nhỏ 12% chiều ngang" in text
    assert "chữ logo/watermark" not in text
    assert "TOAN AAS · giữa phía trên" not in text


def test_status_logo_copy_only_when_logo_exists():
    user_id = 910304
    session = _seed_assets(user_id)
    no_logo_status = bot.video_b14_queue_status_text(session, {"job": {"id": 1, "status": "queued"}}, user_id, "vi")
    assert "Logo:" not in no_logo_status
    _press(user_id, "vproduct|asset_wait|logo")
    _send_logo(user_id, "status-logo")
    _press(user_id, "vproduct|asset_logo_position|bottom_left")
    session = bot.get_video_session(user_id)
    status = bot.video_b14_queue_status_text(session, {"job": {"id": 2, "status": "queued"}}, user_id, "vi")
    assert "Logo: bật · vị trí Dưới trái · nhỏ 12% chiều ngang" in status


def test_back_from_logo_position_returns_materials_screen():
    user_id = 910305
    _seed_assets(user_id)
    _press(user_id, "vproduct|asset_wait|logo")
    _send_logo(user_id, "back-logo")
    text, markup, session = _press(user_id, "vproduct|asset_intro")
    assert session["current_step"] == "asset_intake"
    assert "Muốn video sát ý hơn" in text
    assert "🏷 Gửi logo" in _labels(markup)


def test_logo_material_stays_in_asset_pack_for_job_payload_only_after_position():
    user_id = 910306
    _seed_assets(user_id)
    _press(user_id, "vproduct|asset_wait|logo")
    _send_logo(user_id, "payload-logo")
    session = bot.get_video_session(user_id)
    assert not bot.product_video_logo_material_from_session(session).get("logo_enabled")
    _press(user_id, "vproduct|asset_logo_position|top_center")
    session = bot.get_video_session(user_id)
    project = bot.video_b14_prepare_project_for_invoice(user_id, session)
    asset_pack = json.loads(project["asset_pack_json"])
    assert asset_pack["logo_material"]["logo_enabled"] is True
    assert asset_pack["logo_material"]["logo_position"] == "top_center"
    assert asset_pack["logo_material"]["logo_material_only"] is True
    assert asset_pack["logo_material"]["logo_overlay_applied"] is False
