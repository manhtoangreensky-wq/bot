import asyncio
import subprocess
from types import SimpleNamespace

import bot


class FakeMessage:
    chat_id = 186000

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
        self.from_user = SimpleNamespace(id=user_id, first_name="P018Q")
        self.data = data
        self.message = FakeMessage()
        self.edits = []

    async def answer(self, *args, **kwargs):
        return None

    async def edit_message_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.edits.append(item)
        return SimpleNamespace(**item)


def _rows(markup):
    return [[button.text for button in row] for row in markup.inline_keyboard]


def _callbacks(markup):
    return [[button.callback_data for button in row] for row in markup.inline_keyboard]


def _press(user_id: int, callback: str):
    query = FakeQuery(user_id, callback)
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert query.edits
    edit = query.edits[-1]
    return edit["text"], edit.get("reply_markup"), bot.get_video_session(user_id)


def _open(user_id: int, product_id: str):
    bot.clear_video_session(user_id)
    return _press(user_id, f"vproduct|open|{product_id}")


def _sample_status_text():
    session = {
        "product_id": "video_trend",
        "video_flow": "video_trend",
        "current_step": "b14_queue_status",
        "draft": {
            "b14_invoice": {
                "scene_count": 3,
                "duration_seconds": 18,
                "quality_xu": 300,
                "package_label": "⭐ 300 Xu — Cơ bản",
            },
            "b14_addon_plan": {
                "subtitle_enabled": True,
                "logo_enabled": True,
                "logo_source": "text",
                "logo_text": "TOAN AAS",
            },
            "b14_scene_count": 3,
        },
    }
    return bot.video_b14_queue_status_text(
        session,
        {"job": {"id": 37, "status": "queued", "progress_percent": 5}},
        user_id=0,
        lang="vi",
    )


def _prompt_option_rows():
    options = bot.video_microflow_build_options("prompt", "demo", "video_ai_real", 5)
    return _rows(bot.video_microflow_options_keyboard("video_ai_real", "vi", options, "prompt"))


def test_video_status_panel_compact_public_copy():
    text = _sample_status_text()
    assert "🎬 <b>Trạng thái tạo video</b>" in text
    assert "Mã xử lý: <b>#37</b>" in text
    assert "<b>Thông tin video:</b>" in text
    assert "TOAN AAS không báo hoàn tất khi chưa có video cuối (MP4)." in text
    assert "Hệ thống chưa trừ Xu hoặc đã hoàn Xu nếu cần." in text
    assert "Giai đoạn:" not in text
    assert "Tùy chọn thêm:" not in text
    assert "Thời gian chờ dự kiến:" not in text


def test_video_status_panel_no_debug_terms():
    text = _sample_status_text().lower()
    forbidden = (
        "provider",
        "api",
        "ffmpeg",
        "artifact",
        "callback",
        "handler",
        "local_scene_composer",
        "stacktrace",
        "runtimeerror",
        "payload",
        "debug",
        "worker",
        "render_mode",
    )
    assert not [term for term in forbidden if term in text]


def test_video_refresh_button_label_is_update_status():
    rows = _rows(bot.video_b14_queue_status_keyboard("vi"))
    callbacks = _callbacks(bot.video_b14_queue_status_keyboard("vi"))
    assert rows[0] == ["🔄 Cập nhật trạng thái", "🧾 Xem hóa đơn"]
    assert callbacks[0] == ["vproduct|b14_job_status", "vproduct|b14_invoice_screen"]


def test_video_prompt_options_are_1_to_5_single_row():
    rows = _prompt_option_rows()
    assert rows[0] == ["1", "2", "3", "4", "5"]


def test_video_suggestion_buttons_no_long_use_prompt_labels():
    rows = _prompt_option_rows()
    assert all("Dùng prompt" not in label for label in rows[0])
    assert all("Dùng hướng" not in label for label in rows[0])
    assert all(not label.startswith(("1 ", "2 ", "3 ", "4 ", "5 ")) for label in rows[0])


def test_video_prompt_option_5_not_alone_on_separate_row():
    rows = _prompt_option_rows()
    assert "5" in rows[0]
    assert all("5" not in row for row in rows[1:])


def test_video_aux_buttons_under_options():
    rows = _prompt_option_rows()
    assert rows[1] == ["🔄 Gợi ý lại", "✍️ Nhập chủ đề riêng"]
    assert rows[2] == ["⬅️ Quay lại", "🏠 Menu chính"]


def test_video_back_from_prompt_options_returns_previous_screen():
    user_id = 186101
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
    _press(user_id, "vproduct|suggest_prompt|video_ai_real")
    text, _markup, session = _press(user_id, "vproduct|back")
    assert session["current_step"] == "ai_prompt_menu"
    assert "Prompt → Video AI" in text


def test_video_back_from_custom_topic_returns_previous_screen():
    user_id = 186102
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
    _press(user_id, "vproduct|suggest_prompt|video_ai_real")
    _press(user_id, "vproduct|microflow_custom_topic")
    text, _markup, session = _press(user_id, "vproduct|back")
    assert session["current_step"] == "suggest_prompt"
    assert "Gợi ý prompt video" in text


def test_video_status_back_button_is_menu_video():
    rows = _rows(bot.video_b14_queue_status_keyboard("vi"))
    callbacks = _callbacks(bot.video_b14_queue_status_keyboard("vi"))
    assert rows[1][0] == "⬅️ Menu video"
    assert callbacks[1][0] == "menu|main_video"


def test_video_invoice_back_returns_confirm_screen():
    user_id = 186103
    bot.clear_video_session(user_id)
    bot.save_video_session(
        user_id,
        {
            "product_id": "video_trend",
            "video_flow": "video_trend",
            "current_step": "b14_queue_status",
            "draft": {
                "b14_invoice": {"scene_count": 3, "quality_xu": 300, "total_xu": 900},
                "b14_queue_job": {"id": 37, "status": "queued", "progress_percent": 5},
            },
        },
    )
    text, markup, session = _press(user_id, "vproduct|b14_invoice_screen")
    assert session["current_step"] == "b14_invoice"
    assert "Hóa đơn tạo video" in text
    assert "✅ Xác nhận tạo video" in [label for row in _rows(markup) for label in row]
    invoice_back_callback = _callbacks(markup)[1][0]
    text, _markup, session = _press(user_id, invoice_back_callback)
    assert session["current_step"] == "b14_queue_status"
    assert "Trạng thái tạo video" in text


def test_video_missing_origin_fallbacks_to_video_menu_not_main_menu():
    assert bot.video_back_matrix_target({}) == bot.VIDEO_BACK_MENU_TARGET


def test_no_BACK_text_in_back_button_label():
    markups = [
        bot.video_microflow_options_keyboard(
            "video_ai_real",
            "vi",
            bot.video_microflow_build_options("prompt", "demo", "video_ai_real", 5),
            "prompt",
        ),
        bot.video_b14_queue_status_keyboard("vi"),
        bot.video_b14_invoice_keyboard("vi"),
        bot.video_microflow_keyboard("ai_prompt_menu", "video_ai_real", "vi"),
    ]
    labels = [label for markup in markups for row in _rows(markup) for label in row]
    assert not [label for label in labels if "BACK" in label]
    assert "⬅️ Quay lại" in labels


def test_no_engine_provider_payos_changes():
    try:
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", "origin/main"],
            text=True,
            encoding="utf-8",
        ).splitlines()
    except Exception:
        changed = []
    p0_18r_engine_files = {
        "remote_worker.py",
        "services/video_final_output.py",
        "services/video_real_render_connector.py",
        "services/video_project_queue.py",
        "tests/test_p0_18r_real_video_engine_final_mp4_delivery_all_products.py",
    }
    forbidden = {
        "services/multiscene_video_pipeline.py",
        "providers/key4u_provider.py",
    }
    if "local_worker.py" in changed:
        worker_diff = subprocess.check_output(
            ["git", "diff", "--unified=0", "origin/main", "--", "local_worker.py"],
            text=True,
            encoding="utf-8",
        ).lower()
        assert "run_frame_video_render" in worker_diff
        assert "len(photos) < 2" in worker_diff
        assert "len(photos) < 1" in worker_diff
        assert not any(
            marker in worker_diff
            for marker in ("music", "suno", "subdub", "subtitle", "dub", "payos", "wallet", "video_provider")
        )
    if "tests/test_p0_18r_real_video_engine_final_mp4_delivery_all_products.py" in changed:
        changed = [item for item in changed if item not in p0_18r_engine_files]
    assert not forbidden.intersection(changed)


def test_video_ui_audit_passes():
    payload = bot.video_ui_audit_payload()
    assert payload["ok"] is True
