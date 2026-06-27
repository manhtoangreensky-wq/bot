import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace

import bot


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


class _FakeMessage:
    chat_id = 123456

    def __init__(self, text=""):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))
        return None


class _FakeQuery:
    def __init__(self, user_id: int, data: str):
        self.from_user = SimpleNamespace(id=user_id, first_name="B14")
        self.data = data
        self.message = _FakeMessage()
        self.answered = False
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answered = True

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))
        return None


def _press(user_id: int, data: str):
    query = _FakeQuery(user_id, data)
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    return query, bot.get_video_session(user_id)


def _seed_b14_session(user_id: int, *, topic: str = ""):
    bot.clear_video_session(user_id)
    session = bot.task3d_session_step(user_id, "profile_select", product_id="multi_scene_film", return_to="menu|main_video")
    session = bot.video_b14_set_profile(user_id, session, "product_review")
    session = bot.task3d_session_step(user_id, "intro", topic=topic, provider_called=False, xu_charged=0)
    return session


def test_b14_5_audit_report_exists_and_scopes_engine():
    report = Path("docs/reports/P0_17B14_5_VIDEO_FLOW_ROUTER_BACKSTACK_AUDIT.md")
    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    assert "Callback Matrix" in text
    assert "Backstack Matrix" in text
    assert "B13 multiscene render/stitch engine" in text
    assert "No file generation, provider call, or Xu charge happens before final confirm" in text


def test_asset_skip_without_idea_enters_real_text_state():
    user_id = 914501
    _seed_b14_session(user_id)
    _press(user_id, "vproduct|asset_intro")
    query, session = _press(user_id, "vproduct|asset_skip_confirm")
    assert session["current_step"] == "collect_input"
    assert session["draft"]["input_mode"] == "text"
    assert session["draft"]["input_after_assets"] is True
    assert "Nhập ý tưởng" in query.edits[-1][0]
    bot.clear_video_session(user_id)


def test_idea_after_asset_skip_continues_to_creative_not_generic_chat():
    user_id = 914502
    _seed_b14_session(user_id)
    _press(user_id, "vproduct|asset_intro")
    _press(user_id, "vproduct|asset_skip_confirm")
    message = _FakeMessage("mèo cam mập đi công viên")
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id))
    handled = asyncio.run(bot.handle_video_product_pending_text(update, SimpleNamespace()))
    session = bot.get_video_session(user_id)
    assert handled is True
    assert session["current_step"] == "b14_creative_controls"
    assert session["topic"] == "mèo cam mập đi công viên"
    assert "Tùy chỉnh phong cách video" in message.replies[-1][0]
    bot.clear_video_session(user_id)


def test_b14_back_renderer_knows_new_screens():
    source = inspect.getsource(bot.task3d_render_step)
    for step in (
        "profile_select",
        "asset_intake",
        "b14_creative_controls",
        "storyboard_preview",
        "b14_addons",
        "b14_voice",
        "b14_music",
        "b14_scene_count",
        "b14_invoice",
        "b14_queue_status",
    ):
        assert f'== "{step}"' in source or f'in {{"{step}"' in source


def test_profile_suggestions_are_profile_based_and_not_generic_dead_end():
    user_id = 914503
    _seed_b14_session(user_id)
    query, session = _press(user_id, "vproduct|ideas")
    assert session["current_step"] == "idea_suggestions"
    assert "Gợi ý ý tưởng cho" in query.edits[-1][0]
    callbacks = _callbacks(query.edits[-1][1]["reply_markup"])
    assert "vproduct|b14_idea_select|0" in callbacks
    query, session = _press(user_id, "vproduct|b14_idea_select|0")
    assert session["current_step"] == "asset_intake"
    assert session["topic"]
    bot.clear_video_session(user_id)


def test_voice_default_applies_and_stays_on_voice_screen():
    user_id = 914504
    _seed_b14_session(user_id, topic="review máy xay mini màu xanh")
    _press(user_id, "vproduct|asset_skip_confirm")
    _press(user_id, "vproduct|b14_creative_done")
    _press(user_id, "vproduct|storyboard_confirm")
    query, session = _press(user_id, "vproduct|b14_addon_voice")
    assert session["current_step"] == "b14_voice"
    assert "Lời đọc dự kiến" in query.edits[-1][0]
    query, session = _press(user_id, "vproduct|b14_voice_source|default_male")
    plan = bot.video_b14_addon_plan_from_session(session)
    assert session["current_step"] == "b14_voice"
    assert plan["voice_enabled"] is True
    assert plan["voice_source"] == "default_male"
    assert plan.get("narration_text")
    assert "Giọng đọc cho video" in query.edits[-1][0]
    bot.clear_video_session(user_id)


def test_music_vault_and_done_return_to_addons_cleanly():
    user_id = 914505
    _seed_b14_session(user_id, topic="video quán cà phê sáng")
    _press(user_id, "vproduct|asset_skip_confirm")
    _press(user_id, "vproduct|b14_creative_done")
    _press(user_id, "vproduct|storyboard_confirm")
    query, session = _press(user_id, "vproduct|b14_addon_music")
    assert session["current_step"] == "b14_music"
    assert "Nhạc nền" in query.edits[-1][0]
    query, session = _press(user_id, "vproduct|b14_music_source|vault")
    plan = bot.video_b14_addon_plan_from_session(session)
    assert session["current_step"] == "b14_music"
    assert plan["music_enabled"] is True
    assert plan["music_source"] == "vault"
    query, session = _press(user_id, "vproduct|b14_music_done")
    assert session["current_step"] == "b14_addons"
    assert "Voice / nhạc / phụ đề / logo" in query.edits[-1][0]
    bot.clear_video_session(user_id)


def test_scene_count_before_package_forces_package_screen():
    user_id = 914506
    _seed_b14_session(user_id, topic="trailer phim ngắn về robot giao hàng")
    _press(user_id, "vproduct|asset_skip_confirm")
    _press(user_id, "vproduct|b14_creative_done")
    query, session = _press(user_id, "vproduct|b14_scene_count|3")
    assert session["current_step"] == "b14_quality"
    assert "Chọn gói chất lượng video" in query.edits[-1][0]
    bot.clear_video_session(user_id)


def test_final_status_text_has_eta_and_buttons():
    session = {
        "product_id": "multi_scene_film",
        "topic": "video sản phẩm",
        "draft": {
            "b14_scene_count": 3,
            "b14_invoice": {"scene_count": 3, "duration_seconds": 18, "total_xu": 900},
            "b14_queue_job": {"id": 77},
            "b14_project_id": 12,
        },
    }
    text = bot.video_b14_queue_status_text(session, None, 0, "vi")
    callbacks = _callbacks(bot.video_b14_queue_status_keyboard("vi"))
    assert "Thời gian chờ dự kiến" in text
    assert "MP4" in text
    assert "vproduct|b14_job_status" in callbacks
    assert "vproduct|b14_invoice_screen" in callbacks


def test_public_b14_copy_avoids_internal_terms():
    plan = bot.video_b14_storyboard_plan("product_review", 3, idea_text="review máy xay mini")
    combined = "\n".join([
        bot.video_b14_storyboard_preview_text(plan),
        bot.video_b14_addon_text({"draft": {"b14_profile_id": "product_review"}}, "vi"),
        bot.video_b14_quality_text("vi"),
        bot.video_b14_scene_count_text({"draft": {"b14_quality_xu": 300}}, "vi"),
        bot.video_b14_queue_status_text({"draft": {"b14_queue_job": {"id": 1}, "b14_invoice": {"scene_count": 3}}}, None, 0, "vi"),
    ]).lower()
    for term in ("provider", "ffmpeg", "callback", "queue lease", "local_worker", "continuity ledger", "prompt context engine", "qc:"):
        assert term not in combined


def test_admin_router_commands_are_registered():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    for command in (
        "tool_test_video_flow_router",
        "tool_test_video_backstack",
        "tool_test_video_live_dry_run",
        "tool_test_video_job_status",
    ):
        assert f'CommandHandler("{command}"' in source
        assert f"cmd_{command}" in source
