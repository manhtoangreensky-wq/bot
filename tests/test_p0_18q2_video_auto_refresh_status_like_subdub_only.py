import asyncio
import inspect
import subprocess
from types import SimpleNamespace

import bot


class FakeTask:
    def __init__(self, done=False):
        self._done = done

    def done(self):
        return self._done


class FakeApplication:
    def __init__(self):
        self.created = []

    def create_task(self, coro):
        self.created.append(coro)
        coro.close()
        return FakeTask(False)


class FakeBot:
    def __init__(self, *, fail_edit=None):
        self.edits = []
        self.sent = []
        self.fail_edit = fail_edit

    async def edit_message_text(self, **kwargs):
        if self.fail_edit:
            raise RuntimeError(self.fail_edit)
        self.edits.append(kwargs)
        return SimpleNamespace(message_id=kwargs.get("message_id"), chat_id=kwargs.get("chat_id"))

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(message_id=999, chat_id=kwargs.get("chat_id"))


class FakeQuery:
    def __init__(self):
        self.message = SimpleNamespace(chat_id=187001, message_id=4401)
        self.edits = []

    async def edit_message_text(self, text, **kwargs):
        self.edits.append({"text": text, **kwargs})
        return SimpleNamespace(chat_id=187001, message_id=4401)


def _ctx(fake_bot=None, app=None):
    return SimpleNamespace(bot=fake_bot or FakeBot(), application=app)


def _reset():
    bot.VIDEO_STATUS_AUTO_REFRESH_JOBS.clear()
    bot.VIDEO_STATUS_AUTO_REFRESH_TASKS.clear()


def _session(job_id=987201, status="queued", progress=5, addons=None):
    return {
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
            "b14_addon_plan": dict(addons or {"music_enabled": True, "subtitle_enabled": True, "logo_enabled": True}),
            "b14_queue_job": {"id": job_id, "status": status, "progress_percent": progress},
            "b14_queue_job_id": job_id,
            "b14_scene_count": 3,
        },
    }


def _result(job_id=987201, status="queued", progress=5, final=False):
    job = {"id": job_id, "status": status, "progress_percent": progress}
    project = {"project_id": 9901, "job_id": job_id, "scene_count": 3}
    if final:
        job["final_video_file_id"] = "tg-final-video"
        project["final_video_file_id"] = "tg-final-video"
    return {"job": job, "project": project}


def _register(job_id=987201, status="queued", progress=5, *, start_task=False):
    _reset()
    return bot.video_b14_auto_refresh_register(
        job_id=job_id,
        chat_id=187001,
        message_id=4401,
        user_id=187001,
        lang="vi",
        context=_ctx(),
        session=_session(job_id, status, progress),
        result=_result(job_id, status, progress),
        start_task=start_task,
    )


def _rows(markup):
    return [[button.text for button in row] for row in markup.inline_keyboard]


def _callbacks(markup):
    return [[button.callback_data for button in row] for row in markup.inline_keyboard]


def test_video_status_panel_registers_auto_refresh_after_send():
    _reset()
    app = FakeApplication()
    query = FakeQuery()
    asyncio.run(bot.video_b14_send_or_edit_status_panel(query, _ctx(app=app), _session(), _result(), 187001, "vi"))
    record = bot.VIDEO_STATUS_AUTO_REFRESH_JOBS[bot.video_b14_auto_refresh_key(987201)]
    assert record["registry_saved"] is True
    assert record["task_started"] is True
    assert app.created


def test_video_auto_refresh_saves_chat_message_job_id():
    record = _register()
    assert record["job_id"] == "987201"
    assert record["chat_id"] == 187001
    assert record["message_id"] == 4401
    assert record["callback_data"] == "vproduct|b14_job_status"
    assert record["product_type"] == "video_trend"


def test_video_auto_refresh_edits_existing_message(monkeypatch):
    record = _register()
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: {"id": 987201, "status": "processing", "progress_percent": 50})
    fake = FakeBot()
    result = asyncio.run(bot.video_b14_auto_refresh_tick(_ctx(fake), record["key"]))
    assert result["status"] == "updated"
    assert fake.edits[-1]["chat_id"] == 187001
    assert fake.edits[-1]["message_id"] == 4401
    assert "Tiến độ: <b>50%</b>" in fake.edits[-1]["text"]
    assert fake.sent == []


def test_video_auto_refresh_uses_same_renderer_as_manual_refresh(monkeypatch):
    record = _register()
    live_job = {"id": 987201, "status": "processing", "progress_percent": 50}
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: live_job)
    fake = FakeBot()
    asyncio.run(bot.video_b14_auto_refresh_tick(_ctx(fake), record["key"]))
    expected = bot.video_b14_queue_status_text(
        bot.video_b14_auto_refresh_session_from_status(live_job, {}, user_id=187001),
        {"job": live_job, "project": {}},
        187001,
        "vi",
    )
    assert fake.edits[-1]["text"] == expected


def test_video_manual_refresh_does_not_start_duplicate_loop():
    _reset()
    app = FakeApplication()
    query = FakeQuery()
    ctx = _ctx(app=app)
    asyncio.run(bot.video_b14_send_or_edit_status_panel(query, ctx, _session(), _result(), 187001, "vi"))
    first_count = len(app.created)
    asyncio.run(bot.video_b14_send_or_edit_status_panel(query, ctx, _session(), _result(), 187001, "vi"))
    assert len(app.created) == first_count


def test_video_manual_refresh_can_restart_dead_auto_task():
    _reset()
    app = FakeApplication()
    query = FakeQuery()
    ctx = _ctx(app=app)
    asyncio.run(bot.video_b14_send_or_edit_status_panel(query, ctx, _session(), _result(), 187001, "vi"))
    key = bot.video_b14_auto_refresh_key(987201)
    bot.VIDEO_STATUS_AUTO_REFRESH_TASKS[key] = FakeTask(True)
    bot.VIDEO_STATUS_AUTO_REFRESH_JOBS[key]["task_alive"] = False
    first_count = len(app.created)
    asyncio.run(bot.video_b14_send_or_edit_status_panel(query, ctx, _session(), _result(), 187001, "vi"))
    assert len(app.created) == first_count + 1


def test_video_auto_refresh_stops_on_delivered_terminal(monkeypatch):
    record = _register()
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: {"id": 987201, "status": "completed", "progress_percent": 100, "final_video_file_id": "tg-final"})
    asyncio.run(bot.video_b14_auto_refresh_tick(_ctx(), record["key"]))
    stored = bot.VIDEO_STATUS_AUTO_REFRESH_JOBS[record["key"]]
    assert stored["stopped"] is True
    assert stored["terminal_state"] == "delivered"


def test_video_auto_refresh_stops_on_failed_terminal(monkeypatch):
    record = _register()
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: {"id": 987201, "status": "failed", "progress_percent": 35, "last_error": "provider RuntimeError traceback"})
    asyncio.run(bot.video_b14_auto_refresh_tick(_ctx(), record["key"]))
    stored = bot.VIDEO_STATUS_AUTO_REFRESH_JOBS[record["key"]]
    assert stored["stopped"] is True
    assert stored["terminal_state"] == "failed_no_charge"
    assert "provider" not in bot.video_b14_queue_status_text(_session(status="failed", progress=35), {"job": {"id": 987201, "status": "failed", "progress_percent": 35}}, 187001, "vi").lower()


def test_video_auto_refresh_no_fake_95_without_artifact():
    snapshot = bot.video_b14_auto_refresh_snapshot(987202, user_id=187001, job={"id": 987202, "status": "processing", "progress_percent": 99}, project={})
    assert snapshot["percent"] == 85
    assert "Tiến độ: <b>95%</b>" not in snapshot["text"]
    assert "⏳ Dựng video" in snapshot["text"]


def test_video_render_step_not_done_without_final_mp4():
    snapshot = bot.video_b14_auto_refresh_snapshot(987203, user_id=187001, job={"id": 987203, "status": "processing", "progress_percent": 90}, project={})
    assert "✅ Dựng video" not in snapshot["text"]
    assert "⏳ Dựng video" in snapshot["text"]


def test_video_auto_refresh_debug_reports_registry_task_tick(monkeypatch):
    record = _register()
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: {"id": 987201, "status": "processing", "progress_percent": 50})
    asyncio.run(bot.video_b14_auto_refresh_tick(_ctx(), record["key"]))
    text = bot.video_b14_auto_refresh_status_text("987201")
    for expected in ("job_id", "chat_id", "message_id", "registry_saved", "task_started", "last_tick_at", "update_count", "current_stage", "percent", "final_artifact_valid", "blocker"):
        assert expected in text


def test_video_auto_refresh_scheduler_failure_not_public_debug():
    _reset()
    record = bot.video_b14_auto_refresh_register(
        job_id=987204,
        chat_id=187001,
        message_id=4401,
        user_id=187001,
        lang="vi",
        context=SimpleNamespace(),
        session=_session(987204),
        result=_result(987204),
        start_task=True,
    )
    assert record["scheduler_mode"] == "scheduler_failed"
    public_text = bot.video_b14_queue_status_text(_session(987204), _result(987204), 187001, "vi")
    assert "scheduler" not in public_text.lower()
    assert "debug" not in public_text.lower()


def test_video_auto_refresh_no_duplicate_panel_messages(monkeypatch):
    record = _register()
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: {"id": 987201, "status": "processing", "progress_percent": 50})
    fake = FakeBot(fail_edit="message is not modified")
    asyncio.run(bot.video_b14_auto_refresh_tick(_ctx(fake), record["key"]))
    assert fake.sent == []


def test_video_buttons_unchanged():
    rows = _rows(bot.video_b14_queue_status_keyboard("vi"))
    callbacks = _callbacks(bot.video_b14_queue_status_keyboard("vi"))
    assert rows == [["🔄 Cập nhật trạng thái", "🧾 Xem hóa đơn"], ["⬅️ Menu video", "🏠 Menu chính"]]
    assert callbacks == [["vproduct|b14_job_status", "vproduct|b14_invoice_screen"], ["menu|main_video", "menu|main"]]


def test_video_flow_menu_unchanged():
    rows = _rows(bot.main_video_keyboard("vi"))
    flattened = [label for row in rows for label in row]
    assert "🔥 Video theo trend" in flattened
    assert "🎬 Video AI chân thật" in flattened
    assert "🧩 Kịch bản → Video" in flattened
    assert "🎬 Storyboard + Prompt" in flattened


def test_no_video_engine_provider_changes():
    changed = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True, encoding="utf-8").splitlines()
    forbidden = {
        "services/video_final_output.py",
        "services/video_real_render_connector.py",
        "services/multiscene_video_pipeline.py",
        "local_worker.py",
        "remote_worker.py",
        "providers/key4u_provider.py",
    }
    assert not forbidden.intersection(changed)


def test_no_music_subdub_voice_payos_changes():
    changed = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True, encoding="utf-8").splitlines()
    forbidden_prefixes = (
        "services/minimax_voice_adapter.py",
        "services/subtitle_dub_pipeline.py",
        "services/payos",
        "music/",
        "providers/suno",
        "wallet",
    )
    assert not [path for path in changed if path.startswith(forbidden_prefixes)]


def test_video_auto_refresh_handlers_registered():
    source = inspect.getsource(bot)
    assert 'CommandHandler("video_auto_status", cmd_video_progress_auto_refresh_status)' in source
    assert 'CommandHandler("video_status_debug", cmd_video_status_debug)' in source
