import asyncio
from types import SimpleNamespace

import bot
import video_image_to_video_flow as ivf


class FakeMessage:
    chat_id = 123456

    async def reply_text(self, text, **kwargs):
        return SimpleNamespace(text=text, **kwargs)


class FakeQuery:
    def __init__(self, user_id: int, data: str):
        self.from_user = SimpleNamespace(id=user_id, first_name="P018F")
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


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _press(user_id: int, callback: str):
    query = FakeQuery(user_id, callback)
    update = SimpleNamespace(callback_query=query)
    if callback.startswith("vproduct|"):
        asyncio.run(bot.handle_video_product_callback(update, SimpleNamespace()))
    elif callback.startswith("vpromptlib|"):
        asyncio.run(bot.handle_video_prompt_library_callback(update, SimpleNamespace()))
    elif callback.startswith("vdownload|"):
        asyncio.run(bot.handle_video_downloader_callback(update, SimpleNamespace()))
    else:
        raise AssertionError(f"unsupported callback {callback}")
    assert query.edits
    return query.edits[-1]["text"], query.edits[-1]["reply_markup"], query


def _assert_route(user_id: int, callback: str, expected_text: str, expected_callbacks: tuple[str, ...], *, allow_profile: bool = False):
    text, markup, _query = _press(user_id, callback)
    callbacks = _callbacks(markup)
    assert expected_text in text
    for expected in expected_callbacks:
        assert expected in callbacks
    assert "menu|main_video" in callbacks
    assert not any(item.startswith(("music_quick|", "sfx_quick|", "videodub|")) for item in callbacks)
    assert "menu|translate" not in callbacks
    assert "menu|main_music" not in callbacks
    if not allow_profile:
        assert not any(item.startswith("vproduct|b14_profile|") for item in callbacks)
    return text, callbacks


def test_video_menu_current_buttons_unchanged():
    assert _labels(bot.main_video_keyboard("vi")) == [
        "🔥 Video theo trend",
        "🎬 Video AI chân thật",
        "🧩 Kịch bản → Video",
        "🎞 Ghép ảnh thành video",
        "🎥 Tự quay & đổi cảnh AI",
        "🎬 Phim AI nhiều cảnh",
        "🧠 Ý tưởng video",
        "🎬 Storyboard + Prompt",
        "📚 Kho prompt video",
        "📥 Tải video từ link",
        "🛠 Chỉnh sửa video local",
        "🏠 Menu chính",
    ]


def test_video_menu_each_button_routes_to_matching_flow():
    cases = [
        ("vproduct|open|video_trend", "Video theo trend", ("vproduct|b14_profile|storytelling", "vproduct|b14_profile|product_review")),
        ("vproduct|open|video_idea", "Ý tưởng video", ("vproduct|b14_profile|storytelling", "vproduct|b14_profile|product_review")),
        ("vproduct|open|storyboard_prompt", "Storyboard + Prompt", ("vproduct|b14_profile|storytelling", "vproduct|b14_profile|product_review")),
        ("vpromptlib|start", "Kho prompt video", ("vpromptlib|idea", "vpromptlib|image")),
        ("vproduct|open|video_ai_real", "Video AI chân thật", ("promptvideo|start", "imagevideo|start", "videoref|start")),
        ("vproduct|open|script_image_video", "Kịch bản", ("vproduct|ideas|script_image_video", "vproduct|input_text|script_image_video")),
        ("vproduct|open|frame_video_local", "Ghép ảnh thành video", ("framevideo|start", "framevideo|ai_first")),
        ("vproduct|open|self_shot_scene_change", "Tự quay & đổi cảnh AI", ("selfscene|await_video",)),
        ("vproduct|open|multi_scene_film", "Phim AI nhiều cảnh", ("vproduct|b14_profile|storytelling", "vproduct|b14_profile|cinematic_trailer")),
        ("vdownload|start", "Tải video từ link", ()),
        ("vproduct|open|video_local_edit", "Chỉnh sửa video local", ("videoedit|color", "videoedit|crop")),
    ]
    for index, (callback, expected_text, expected_callbacks) in enumerate(cases, start=1):
        _assert_route(918600 + index, callback, expected_text, expected_callbacks, allow_profile=callback in {
            "vproduct|open|video_trend",
            "vproduct|open|video_idea",
            "vproduct|open|storyboard_prompt",
            "vproduct|open|multi_scene_film",
        })


def test_video_menu_back_from_each_flow_returns_video_menu():
    callbacks = [callback for callback in _callbacks(bot.main_video_keyboard("vi")) if callback != "menu|main"]
    for index, callback in enumerate(callbacks, start=1):
        text, markup, _query = _press(918700 + index, callback)
        assert "menu|main_video" in _callbacks(markup), text


def test_video_menu_no_cross_route_to_translation_voice_music():
    callbacks = _callbacks(bot.main_video_keyboard("vi"))
    joined = " ".join(callbacks)
    assert "menu|translate" not in joined
    assert "music_quick|" not in joined
    assert "menu|main_music" not in joined
    assert "videodub|" not in joined


def test_video_trend_route():
    _assert_route(
        918801,
        "vproduct|open|video_trend",
        "Video theo trend",
        ("vproduct|b14_profile|storytelling", "vproduct|b14_profile|product_review"),
        allow_profile=True,
    )


def test_video_idea_route():
    _assert_route(
        918802,
        "vproduct|open|video_idea",
        "Ý tưởng video",
        ("vproduct|b14_profile|storytelling", "vproduct|b14_profile|product_review"),
        allow_profile=True,
    )


def test_video_storyboard_prompt_route():
    _assert_route(
        918803,
        "vproduct|open|storyboard_prompt",
        "Storyboard + Prompt",
        ("vproduct|b14_profile|storytelling",),
        allow_profile=True,
    )


def test_video_prompt_library_route():
    _assert_route(918804, "vpromptlib|start", "Kho prompt video", ("vpromptlib|idea", "vpromptlib|cinematic"))


def test_realistic_ai_video_route():
    _assert_route(918805, "vproduct|open|video_ai_real", "Video AI chân thật", ("promptvideo|start", "imagevideo|start", "videoref|start"))


def test_script_to_video_route():
    _assert_route(918806, "vproduct|open|script_image_video", "Kịch bản", ("vproduct|ideas|script_image_video", "vproduct|input_text|script_image_video"))


def test_image_to_video_route():
    text, callbacks = _assert_route(918807, "vproduct|open|frame_video_local", "Ghép ảnh thành video", ("framevideo|start", "framevideo|ai_first"))
    assert "Local Worker" not in text
    assert "FFmpeg" not in text
    assert "framevideo|start" in callbacks


def test_self_shot_scene_change_route():
    _assert_route(918808, "vproduct|open|self_shot_scene_change", "Tự quay & đổi cảnh AI", ("selfscene|await_video",))


def test_multiscene_video_route():
    _assert_route(
        918809,
        "vproduct|open|multi_scene_film",
        "Phim AI nhiều cảnh",
        ("vproduct|b14_profile|storytelling", "vproduct|b14_profile|cinematic_trailer"),
        allow_profile=True,
    )


def test_download_video_link_route():
    text, callbacks = _assert_route(918810, "vdownload|start", "Tải video từ link", ())
    state = bot.get_video_downloader_pending(918810)
    assert "Gửi link video công khai" in text
    assert state.get("step") == "await_link"
    assert "vdownload|download|video" not in callbacks


def test_local_video_edit_route():
    _assert_route(918811, "vproduct|open|video_local_edit", "Chỉnh sửa video local", ("videoedit|color", "videoedit|crop"))


def test_video_open_same_product_keeps_existing_draft():
    user_id = 918812
    bot.clear_video_session(user_id)
    bot.task3d_session_step(user_id, "result", product_id="video_idea", topic="mèo cam mập đi công viên", return_to="menu|main_video")
    _press(user_id, "vproduct|open|video_idea")
    session = bot.get_video_session(user_id)
    assert session.get("topic") == "mèo cam mập đi công viên"
    assert session.get("product_id") == "video_idea"


def test_video_invoice_back_to_addons_or_previous_step():
    callbacks = _callbacks(bot.video_b14_invoice_keyboard("vi"))
    assert "vproduct|b14_scene_count_screen" in callbacks
    assert "menu|main" in callbacks
    assert "menu|translate" not in callbacks


def test_video_addons_return_to_invoice_when_started_from_invoice():
    state = bot.video_finalization_set_origin({"step": "confirm"}, "invoice")
    assert state["return_to_invoice"] is True
    assert state["addon_return_target"] == "invoice"


def test_video_failed_render_no_charge_no_fake_success():
    session = {
        "draft": {
            "b14_invoice": {"scene_count": 3, "duration_seconds": 18, "package_label": "300 Xu"},
            "b14_queue_job": {"id": 28, "status": "failed", "progress_percent": 35, "last_error": "provider test_pattern ffmpeg_missing"},
        }
    }
    text = bot.video_b14_queue_status_text(session, None, 918813, "vi")
    assert "chưa dựng được" in text
    assert "Hệ thống chưa trừ Xu" in text
    assert "đã dựng xong" not in text
    assert "test_pattern" not in text
    assert "provider" not in text.lower()


def test_video_status_polling_clean_failure_copy():
    text = bot.frame_video_job_status_text({
        "job_id": "fv-1",
        "status": "failed",
        "image_count": 3,
        "charged_amount": 0,
        "detail": "ffmpeg_missing provider worker RuntimeError traceback",
    })
    assert "chưa ghép được" in text
    assert "Hệ thống chưa trừ Xu" in text
    for forbidden in ("ffmpeg", "provider", "worker", "runtimeerror", "traceback"):
        assert forbidden not in text.lower()


def test_video_public_ui_no_technical_words():
    texts = [
        bot.menu_text_main_video(),
        ivf.frame_video_unified_menu_text("vi"),
        bot.video_editor_job_status_text({"id": 1, "status": "queued"}, "vi"),
        bot.video_editor_job_status_text({"id": 1, "status": "succeeded"}, "vi"),
        bot.frame_video_job_status_text({"job_id": "fv-2", "status": "failed", "image_count": 2, "detail": "payload render_mode debug adapter mux ffmpeg"}),
    ]
    for index, (callback, _label) in enumerate([
        ("vproduct|open|video_trend", "trend"),
        ("vproduct|open|video_idea", "idea"),
        ("vproduct|open|storyboard_prompt", "storyboard"),
        ("vpromptlib|start", "prompt library"),
        ("vproduct|open|video_ai_real", "real video"),
        ("vproduct|open|script_image_video", "script"),
        ("vproduct|open|frame_video_local", "frame"),
        ("vproduct|open|self_shot_scene_change", "self scene"),
        ("vproduct|open|multi_scene_film", "multiscene"),
        ("vdownload|start", "download"),
        ("vproduct|open|video_local_edit", "local edit"),
    ], start=1):
        text, _markup, _query = _press(918900 + index, callback)
        texts.append(text)
    forbidden = ("provider", "api", "worker", "payload", "render_mode", "test_pattern", "debug", "traceback", "runtimeerror", "adapter", "mux", "ffmpeg")
    for text in texts:
        lower = str(text).lower()
        for term in forbidden:
            assert term not in lower
