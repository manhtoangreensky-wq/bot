import asyncio
from pathlib import Path
from types import SimpleNamespace

import bot


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class FakeMessage:
    chat_id = 918300
    message_id = 1

    def __init__(self, text=""):
        self.text = text
        self.sent = []
        self.photo = None
        self.document = None

    async def reply_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.sent.append(item)
        return SimpleNamespace(**item)


class FakeQuery:
    def __init__(self, user_id: int, data: str):
        self.from_user = SimpleNamespace(id=user_id, first_name="P018C")
        self.data = data
        self.message = FakeMessage()
        self.answered = False
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answered = True

    async def edit_message_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.edits.append(item)
        return SimpleNamespace(**item)


def _press(user_id: int, data: str):
    query = FakeQuery(user_id, data)
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    return query, bot.get_video_session(user_id)


def _send_text(user_id: int, text: str):
    message = FakeMessage(text)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=user_id), message=message)
    handled = asyncio.run(bot.handle_video_product_pending_text(update, SimpleNamespace()))
    return handled, message, bot.get_video_session(user_id)


def _send_logo(user_id: int, file_id="logo-file"):
    message = FakeMessage("")
    message.photo = [SimpleNamespace(file_id=file_id, file_unique_id=file_id, file_size=1000)]
    update = SimpleNamespace(effective_user=SimpleNamespace(id=user_id), message=message)
    handled = asyncio.run(bot.handle_video_product_pending_media(update, SimpleNamespace()))
    return handled, message, bot.get_video_session(user_id)


def _seed(user_id: int, scene_count=3):
    bot.clear_video_session(user_id)
    session = bot.task3d_session_step(user_id, "profile_select", product_id="multi_scene_film", return_to="menu|main_video")
    session = bot.video_b14_set_profile(user_id, session, "product_review")
    session = bot.task3d_session_step(user_id, "storyboard_preview", topic="review máy xay mini màu xanh", provider_called=False, xu_charged=0)
    bot.video_b14_build_storyboard_for_session(user_id, session, scene_count=scene_count)
    return bot.get_video_session(user_id)


def test_p0_18c_audit_report_exists():
    report = Path("docs/reports/P0_18C_LIVE_REAL_BUTTON_AUDIT.md")
    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    assert "Xem prompt video" in text
    assert "Logo/watermark chu" in text
    assert "waiting_voice_volume_percent" in text
    assert "Kiem tra trang thai" in text


def test_prompt_video_button_no_generic_error():
    user_id = 918301
    _seed(user_id, 3)
    query, _session = _press(user_id, "vproduct|b14_prompt_video_text")
    text = query.edits[-1]["text"]
    assert "🎥" in text and "Prompt video" in text
    assert "Camera/motion" in text
    assert "Có lỗi khi xử lý lệnh" not in text
    assert len(text) < 4096


def test_prompt_video_rebuilds_from_storyboard():
    user_id = 918302
    session = _seed(user_id, 3)
    draft = dict(session["draft"])
    draft.pop("prompt_bundle", None)
    session["draft"] = draft
    bot.save_video_session(user_id, session)
    query, _session = _press(user_id, "vproduct|b14_prompt_video_text")
    assert "Cảnh 1" in query.edits[-1]["text"]


def test_prompt_video_missing_session_recovery():
    user_id = 918303
    bot.clear_video_session(user_id)
    query, _session = _press(user_id, "vproduct|b14_prompt_video_text")
    assert "Phiên tạo video bị thiếu dữ liệu" in query.edits[-1]["text"]


def test_prompt_video_back_to_storyboard():
    callbacks = _callbacks(bot.video_b14_prompt_video_keyboard("vi"))
    assert "vproduct|b14_storyboard_screen" in callbacks


def test_logo_text_button_opens_input():
    user_id = 918304
    _seed(user_id)
    query, session = _press(user_id, "vproduct|b14_logo_text_start")
    assert session["current_step"] == "b14_logo_text_wait"
    assert "Nhập chữ logo/watermark" in query.edits[-1]["text"]


def test_logo_text_saves_then_asks_position():
    user_id = 918305
    _seed(user_id)
    _press(user_id, "vproduct|b14_logo_text_start")
    handled, message, session = _send_text(user_id, "TOAN AAS")
    plan = bot.video_b14_addon_plan_from_session(session)
    assert handled is True
    assert plan["logo_source"] == "text"
    assert plan["logo_text"] == "TOAN AAS"
    assert plan["logo_enabled"] is False
    assert session["current_step"] == "b14_logo_position"
    assert "Chọn vị trí" in message.sent[-1]["text"]


def test_logo_position_requires_confirm():
    user_id = 918306
    _seed(user_id)
    _press(user_id, "vproduct|b14_logo_text_start")
    _send_text(user_id, "TOAN AAS")
    query, session = _press(user_id, "vproduct|b14_logo_position|top_center")
    plan = bot.video_b14_addon_plan_from_session(session)
    assert plan["logo_position"] == "top_center"
    assert plan["logo_enabled"] is False
    assert session["current_step"] == "b14_logo_confirm"
    assert "Xác nhận logo/watermark" in query.edits[-1]["text"]


def test_logo_confirm_returns_addons():
    user_id = 918307
    _seed(user_id)
    _press(user_id, "vproduct|b14_logo_text_start")
    _send_text(user_id, "TOAN AAS")
    _press(user_id, "vproduct|b14_logo_position|bottom_center")
    query, session = _press(user_id, "vproduct|b14_logo_confirm")
    plan = bot.video_b14_addon_plan_from_session(session)
    assert plan["logo_source"] == "text"
    assert plan["logo_enabled"] is True
    assert plan["logo_text"] == "TOAN AAS"
    assert plan["logo_position"] == "bottom_center"
    assert session["current_step"] == "b14_addons"
    assert "Voice / nhạc / phụ đề / logo" in query.edits[-1]["text"]


def test_logo_done_returns_addons():
    user_id = 918308
    _seed(user_id)
    query, session = _press(user_id, "vproduct|b14_logo_done")
    assert session["current_step"] == "b14_addons"
    assert "Voice / nhạc / phụ đề / logo" in query.edits[-1]["text"]


def test_logo_back_returns_addons():
    callbacks = _callbacks(bot.video_b14_logo_keyboard("vi"))
    assert "vproduct|b14_addons" in callbacks
    assert "vproduct|b14_logo_upload" not in callbacks


def test_voice_edit_text_sets_waiting_state():
    user_id = 918309
    _seed(user_id)
    query, session = _press(user_id, "vproduct|b14_voice_edit")
    assert session["current_step"] == "waiting_video_narration_text"
    assert "Sửa lời đọc video" in query.edits[-1]["text"]


def test_voice_edit_text_saves_narration():
    user_id = 918310
    _seed(user_id)
    _press(user_id, "vproduct|b14_voice_edit")
    handled, _message, session = _send_text(user_id, "Cảnh 1: Lời đọc mới")
    assert handled is True
    assert bot.video_b14_addon_plan_from_session(session)["narration_text"] == "Cảnh 1: Lời đọc mới"


def test_voice_edit_text_returns_voice_menu():
    user_id = 918311
    _seed(user_id)
    _press(user_id, "vproduct|b14_voice_edit")
    handled, message, session = _send_text(user_id, "Cảnh 1: Lời đọc mới")
    assert handled is True
    assert session["current_step"] == "b14_voice"
    assert "Giọng đọc cho video" in message.sent[-1]["text"]


def test_voice_narration_used_by_subtitle():
    user_id = 918312
    _seed(user_id)
    _press(user_id, "vproduct|b14_voice_edit")
    _send_text(user_id, "Cảnh 1: Lời đọc dùng cho phụ đề")
    session = bot.video_b14_set_addon_plan(user_id, bot.get_video_session(user_id), subtitle_enabled=True, subtitle_source="from_narration")
    assert "Lời đọc dùng cho phụ đề" in bot.video_b14_narration_from_storyboard(session)


def test_voice_default_does_not_skip_narration():
    user_id = 918313
    _seed(user_id)
    query, session = _press(user_id, "vproduct|b14_voice_source|default_female")
    plan = bot.video_b14_addon_plan_from_session(session)
    assert plan["voice_source"] == "default_female"
    assert str(plan.get("narration_text") or "").strip()
    assert "Lời đọc dự kiến" in query.edits[-1]["text"]


def test_voice_volume_asks_manual_input():
    user_id = 918314
    _seed(user_id)
    query, session = _press(user_id, "vproduct|b14_voice_volume")
    assert session["current_step"] == "waiting_voice_volume_percent"
    assert "Nhập mức âm lượng giọng" in query.edits[-1]["text"]


def test_voice_volume_accepts_percent():
    user_id = 918315
    _seed(user_id)
    _press(user_id, "vproduct|b14_voice_volume")
    handled, _message, session = _send_text(user_id, "120%")
    assert handled is True
    assert bot.video_b14_addon_plan_from_session(session)["voice_volume_percent"] == 120


def test_voice_volume_rejects_invalid():
    user_id = 918316
    _seed(user_id)
    _press(user_id, "vproduct|b14_voice_volume")
    handled, message, session = _send_text(user_id, "500")
    assert handled is True
    assert session["current_step"] == "waiting_voice_volume_percent"
    assert "cho phép từ 10% đến 200%" in message.sent[-1]["text"]


def test_music_volume_asks_manual_input():
    user_id = 918317
    _seed(user_id)
    query, session = _press(user_id, "vproduct|b14_music_volume")
    assert session["current_step"] == "waiting_music_volume_percent"
    assert "Nhập mức âm lượng nhạc nền" in query.edits[-1]["text"]


def test_music_volume_accepts_percent():
    user_id = 918318
    _seed(user_id)
    _press(user_id, "vproduct|b14_music_volume")
    handled, _message, session = _send_text(user_id, "10")
    assert handled is True
    assert bot.video_b14_addon_plan_from_session(session)["music_volume_percent"] == 10


def test_music_volume_rejects_invalid():
    user_id = 918319
    _seed(user_id)
    _press(user_id, "vproduct|b14_music_volume")
    handled, message, session = _send_text(user_id, "150")
    assert handled is True
    assert session["current_step"] == "waiting_music_volume_percent"
    assert "cho phép từ 0% đến 100%" in message.sent[-1]["text"]


def test_volume_back_routes_correctly():
    assert "vproduct|b14_addon_voice" in _callbacks(bot.video_b14_volume_input_keyboard("voice", "vi"))
    assert "vproduct|b14_addon_music" in _callbacks(bot.video_b14_volume_input_keyboard("music", "vi"))


def test_scene_count_preserves_storyboard():
    user_id = 918320
    session = _seed(user_id, 3)
    before = list((session["draft"]["b14_storyboard_plan"] or {}).get("scene_cards") or [])
    session, _note = bot.video_b14_resize_storyboard_for_session(user_id, session, 3)
    after = list((session["draft"]["b14_storyboard_plan"] or {}).get("scene_cards") or [])
    assert after[0]["visual_goal"] == before[0]["visual_goal"]


def test_scene_count_extends_storyboard():
    user_id = 918321
    session = _seed(user_id, 3)
    first = session["draft"]["b14_storyboard_plan"]["scene_cards"][0]["visual_goal"]
    session, note = bot.video_b14_resize_storyboard_for_session(user_id, session, 5)
    cards = session["draft"]["b14_storyboard_plan"]["scene_cards"]
    assert len(cards) == 5
    assert cards[0]["visual_goal"] == first
    assert "mở rộng" in note


def test_custom_scene_count_waits_for_input():
    user_id = 918322
    _seed(user_id)
    query, session = _press(user_id, "vproduct|b14_scene_custom")
    assert session["current_step"] == "waiting_scene_count"
    assert "Nhập số cảnh" in query.edits[-1]["text"]


def test_custom_scene_count_validates_range():
    user_id = 918323
    _seed(user_id)
    _press(user_id, "vproduct|b14_scene_custom")
    handled, message, _session = _send_text(user_id, "21")
    assert handled is True
    assert "1–20" in message.sent[-1]["text"]


def test_unsupported_multiscene_guard_no_charge():
    ok, text = bot.video_b14_extended_scene_guard(918324, 10)
    assert ok is True
    assert text == ""


def _invoice_for(scenes: int):
    return bot.video_b14_invoice_breakdown(300, scenes)


def test_video_discount_1_to_4_scenes_20_percent():
    assert _invoice_for(3)["discount_percent"] == 20
    assert _invoice_for(3)["total_xu"] == 720


def test_video_discount_5_to_9_scenes_25_percent():
    assert _invoice_for(5)["discount_percent"] == 25
    assert _invoice_for(5)["total_xu"] == 1125


def test_video_discount_10_to_19_scenes_30_percent():
    assert _invoice_for(10)["discount_percent"] == 30
    assert _invoice_for(10)["total_xu"] == 2100


def test_invoice_shows_discount_amount():
    user_id = 918325
    session = _seed(user_id, 3)
    draft = dict(session["draft"])
    draft["b14_quality_xu"] = 300
    session["draft"] = draft
    bot.save_video_session(user_id, session)
    text = bot.video_b14_invoice_text(bot.get_video_session(user_id), user_id, "vi")
    assert "Tạm tính" in text
    assert "Giảm giá số cảnh" in text
    assert "-20%" in text


def test_owner_admin_no_charge_still_applies():
    report = bot.video_b14_live_buttons_regression_report(bot.ADMIN_ID)
    assert report["checks"]["confirm_no_charge"] is True
    assert "OWNER/ADMIN TEST MODE" not in report["status_text"]
    assert "không trừ Xu" not in report["status_text"]


def test_video_status_shows_job_stage_progress():
    text = bot.video_b14_queue_status_text({"draft": {"b14_queue_job": {"id": 1, "status": "queued"}, "b14_invoice": {"scene_count": 3, "duration_seconds": 18, "package_label": "Cơ bản"}}}, None, bot.ADMIN_ID, "vi")
    assert "Trạng thái" in text and "Tiến trình" in text and "Tiến độ" in text
    assert "Giai đoạn" not in text


def test_video_status_shows_addons():
    session = {"draft": {"b14_queue_job": {"id": 1, "status": "queued"}, "b14_invoice": {"scene_count": 3}, "b14_addon_plan": {"voice_enabled": True, "voice_source": "default_female", "voice_label": "Nữ mặc định", "music_enabled": True, "music_source": "default", "music_volume_percent": 10, "subtitle_enabled": True, "subtitle_source": "from_narration", "dub_enabled": False, "logo_enabled": True, "logo_source": "text", "logo_text": "TOAN AAS", "logo_position": "top_right"}}}
    text = bot.video_b14_queue_status_text(session, None, bot.ADMIN_ID, "vi")
    assert "Hậu kỳ: <b>Voice, Nhạc nền, phụ đề, logo</b>" in text
    assert "Voice:" not in text and "Nhạc:" not in text and "Logo:" not in text


def test_video_status_no_fake_success(monkeypatch):
    monkeypatch.setattr(bot, "video_b14_fail_stale_product_job_for_status", lambda _job_id: 0)
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: {})
    text = bot.video_b14_queue_status_text({"draft": {"b14_queue_job": {"id": 1, "status": "completed"}, "b14_invoice": {"scene_count": 3}}}, None, bot.ADMIN_ID, "vi")
    assert "đã có MP4" not in text
    assert bot.VIDEO_B14_PRODUCT_CLEAN_FAIL_MESSAGE in text


def test_video_status_queued_worker_message(monkeypatch):
    monkeypatch.setattr(bot, "video_b14_fail_stale_product_job_for_status", lambda _job_id: 0)
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: {})
    text = bot.video_b14_queue_status_text({"draft": {"b14_queue_job": {"id": 1, "status": "queued"}, "b14_invoice": {"scene_count": 3}}}, None, bot.ADMIN_ID, "vi")
    assert "⏳ Chuẩn bị dựng" in text
    assert "worker" not in text.lower()


def test_video_status_owner_no_charge():
    text = bot.video_b14_queue_status_text({"draft": {"b14_queue_job": {"id": 1, "status": "queued"}, "b14_invoice": {"scene_count": 3}}}, None, bot.ADMIN_ID, "vi")
    assert "OWNER/ADMIN TEST MODE" not in text
    assert "không trừ Xu" not in text


def test_tool_test_live_video_buttons_regression_admin_only(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=918326), message=FakeMessage())
    asyncio.run(bot.cmd_tool_test_live_video_buttons_regression(update, SimpleNamespace(args=["--no-charge"])))
    assert "chưa xử lý" in update.message.sent[-1]["text"] and "chưa trừ Xu" in update.message.sent[-1]["text"]


def test_tool_test_live_video_buttons_regression_no_charge(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=918327), message=FakeMessage())
    asyncio.run(bot.cmd_tool_test_live_video_buttons_regression(update, SimpleNamespace(args=[])))
    assert "--no-charge" in update.message.sent[-1]["text"]


def test_tool_test_live_video_buttons_regression_covers_prompt_logo_voice_volume_discount_status():
    report = bot.video_b14_live_buttons_regression_report(bot.ADMIN_ID)
    assert report["ok"] is True
    for key in [
        "prompt_video_no_generic_error",
        "logo_text_position_confirm",
        "voice_text_saved",
        "voice_volume_120",
        "music_volume_10",
        "scene_count_3_discount_20",
        "status_job_addons",
    ]:
        assert report["checks"][key] is True
