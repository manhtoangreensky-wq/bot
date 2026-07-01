import asyncio
from types import SimpleNamespace

import bot


class CaptureMessage:
    def __init__(self, chat_id=232201):
        self.chat_id = chat_id
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"kind": "text", "text": text, **kwargs})
        return SimpleNamespace(chat_id=self.chat_id, message_id=100 + len(self.outputs))


class CaptureQuery:
    def __init__(self, user_id=232201, data="music_quick|showroom|music_ai_confirm"):
        self.data = data
        self.message = CaptureMessage(user_id)
        self.from_user = SimpleNamespace(id=user_id)
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append({"text": text, **kwargs})
        return SimpleNamespace(message_id=200 + len(self.edits))


def _reset():
    bot.PROGRESS_AUTO_REFRESH_JOBS.clear()
    bot.PROGRESS_AUTO_REFRESH_TASKS.clear()
    bot.ENGINE_ASYNC_MEMORY_JOBS.clear()
    bot.MUSIC_PRODUCT_DELIVERY_MEMORY_LOCKS.clear()
    bot.MUSIC_PANEL_CREATOR_TRACES.clear()
    bot.USER_PENDING.clear()


def _legacy_result(mode="song"):
    payload = {
        "music_product_mode": mode,
        "music_product_tier": "music_tier_standard",
        "description": "Nhac thuong hieu TOAN AAS",
        "genre": "pop",
        "mood": "bright",
        "duration_seconds": 60,
        "selected_prompt": "bright clean TOAN AAS brand music",
    }
    if mode == "song":
        payload.update({"lyrics": "TOAN AAS luon dong hanh", "vocal_mode": "female", "music_ai_kind": "lyrics"})
    return payload


def _product_result(mode="song"):
    return bot.music_confirm_result_for_real_job_persist(_legacy_result(mode))


def _patch_confirm(monkeypatch, *, guided_result=None, engine_result=None):
    _reset()
    user_id = 232201
    bot.save_music_guided_result(user_id, guided_result or _product_result("song"))
    store = {}
    save_events = []
    submit_calls = []
    start_calls = []

    def fake_save(payload):
        current = dict(payload)
        store[str(current.get("internal_job_id") or "")] = current
        save_events.append(dict(current))
        return dict(current)

    async def fake_execute(feature, params, context):
        submit_calls.append((feature, params, context, dict(store)))
        return engine_result or {
            "ok": True,
            "provider_result": {
                "ok": True,
                "provider": "key4u_suno",
                "task_id": "provider-task-23h2",
                "status": "PASS_SUBMITTED",
            },
        }

    def fake_start(_context, key):
        start_calls.append(key)
        return True

    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda job_id: dict(store.get(str(job_id), {})))
    monkeypatch.setattr(bot, "can_user_access_product_engine", lambda *args, **kwargs: {"allowed": True})
    monkeypatch.setattr(bot, "get_user", lambda uid: (999, None, None))
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: False)
    monkeypatch.setattr(bot, "execute_engine", fake_execute)
    monkeypatch.setattr(bot, "progress_auto_refresh_start_task", fake_start)
    return SimpleNamespace(user_id=user_id, store=store, save_events=save_events, submit_calls=submit_calls, start_calls=start_calls)


def _run_live_confirm(monkeypatch, *, guided_result=None):
    state = _patch_confirm(monkeypatch, guided_result=guided_result)
    query = CaptureQuery(state.user_id)
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=state.user_id))
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    return state, query


def _last_job(state):
    return list(state.store.values())[-1]


def test_music_panel_creator_audit_lists_all_panel_creators():
    text = bot.music_panel_creator_audit_text()
    assert "engine_async_job_id(feature=music_suno)" in text
    assert "create_music_pending_submit_job" in text
    assert "handle_music_product_confirm" in text
    assert "send_product_progress_message" in text
    assert "product_progress_status_from_job_text" in text
    assert "product_progress_debug_text" in text


def test_no_music_panel_sent_without_real_job(monkeypatch):
    _reset()
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {})
    message = CaptureMessage()
    asyncio.run(bot.send_product_progress_message(
        message,
        SimpleNamespace(),
        product_type="music_song",
        job_id="MUS165D40F",
        current_stage="received_request",
        percent=5,
        start_task=True,
    ))
    assert "TOAN AAS đang tạo bài hát" not in message.outputs[-1]["text"]
    assert "chưa trừ Xu" in message.outputs[-1]["text"]
    assert bot.PROGRESS_AUTO_REFRESH_JOBS == {}
    assert bot.music_panel_creator_trace("MUS165D40F")["blocked"] is True


def test_legacy_fake_panel_path_wrapped_to_real_confirm(monkeypatch):
    state, query = _run_live_confirm(monkeypatch, guided_result=_legacy_result("background"))
    job = _last_job(state)
    assert job["persist_helper_called"] is True
    assert job["internal_job_id"].startswith("MUS")
    assert "TOAN AAS đang tạo nhạc nền" in query.message.outputs[0]["text"]


def test_music_panel_records_panel_created_by(monkeypatch):
    state, _query = _run_live_confirm(monkeypatch)
    job = _last_job(state)
    assert job["panel_created_by"] == "handle_music_product_confirm"
    assert job["panel_created_at"]
    assert job["panel_route"] == "music_quick|showroom|music_ai_confirm"


def test_music_panel_records_chat_message_id(monkeypatch):
    state, query = _run_live_confirm(monkeypatch)
    job = _last_job(state)
    assert job["panel_chat_id"] == str(query.message.chat_id)
    assert job["panel_message_id"] == "101"
    assert job["panel_callback_data"].startswith("progress|status|music_song|MUS")


def test_music_job_debug_shows_real_job_created_before_panel(monkeypatch):
    state, _query = _run_live_confirm(monkeypatch)
    job_id = next(iter(state.store))
    text = bot.music_job_debug_text(job_id)
    assert "lookup_found: <code>yes</code>" in text
    assert "real_job_created_before_panel: <code>yes</code>" in text
    assert "panel_chat_id/message_id" in text


def test_music_job_debug_missing_job_reports_panel_source_if_any():
    _reset()
    bot.record_music_panel_creator_trace(
        "MUS165D40F",
        product_type="music_bg",
        source="send_product_progress_message",
        callback_data="progress|status|music_bg|MUS165D40F",
        blocked=True,
        reason="missing_real_music_job",
    )
    text = bot.music_job_debug_text("MUS165D40F")
    assert "lookup_found: <code>no</code>" in text
    assert "panel_created_by: <code>send_product_progress_message</code>" in text
    assert "blocker: <code>missing_job</code>" in text


def test_progress_status_debug_flags_synthetic_status_without_real_job():
    _reset()
    text = bot.product_progress_debug_text("MUS165D40F", "music_bg", {})
    assert "lookup_found: <code>no</code>" in text
    assert "synthetic_status_used: <code>no</code>" in text
    assert "warning: <code>progress_status_without_real_music_job</code>" in text
    assert "Percent: <code>5%</code>" not in text


def test_new_music_job_has_registry_immediately_after_panel(monkeypatch):
    state, _query = _run_live_confirm(monkeypatch)
    job_id = next(iter(state.store))
    key = bot.progress_auto_refresh_key("music_song", job_id)
    assert key in bot.PROGRESS_AUTO_REFRESH_JOBS
    assert bot.PROGRESS_AUTO_REFRESH_JOBS[key]["registry_saved"] is True


def test_progress_auto_refresh_status_not_no_registry_for_new_job(monkeypatch):
    state, _query = _run_live_confirm(monkeypatch)
    job_id = next(iter(state.store))
    text = bot.progress_auto_refresh_status_text(job_id)
    assert "registry_saved: <code>true</code>" in text
    assert "no_registry_after_restart" not in text


def test_music_confirm_route_still_calls_provider_submit(monkeypatch):
    state, _query = _run_live_confirm(monkeypatch)
    assert len(state.submit_calls) == 1
    assert state.submit_calls[0][0] == "music_song"


def test_no_provider_before_final_confirm(monkeypatch):
    _reset()
    called = []
    monkeypatch.setattr(bot, "execute_engine", lambda *args, **kwargs: called.append(True))
    result = _product_result("song")
    bot.music_product_invoice_text(result, "vi")
    bot.music_product_invoice_keyboard(result, "vi", bot.PRODUCT_CONTEXT_SHOWROOM)
    assert called == []


def test_no_duplicate_provider_submit(monkeypatch):
    state, _query = _run_live_confirm(monkeypatch)
    job_id = next(iter(state.store))
    asyncio.run(bot.handle_product_progress_callback(
        SimpleNamespace(callback_query=CaptureQuery(state.user_id, f"progress|status|music_song|{job_id}")),
        SimpleNamespace(),
    ))
    assert len(state.submit_calls) == 1


def test_debug_commands_read_only(monkeypatch):
    _reset()
    called = []
    monkeypatch.setattr(bot, "execute_engine", lambda *args, **kwargs: called.append("execute"))
    monkeypatch.setattr(bot, "poll_music_suno_async_job", lambda *args, **kwargs: called.append("poll"))
    monkeypatch.setattr(bot, "send_music_product_audio_result", lambda *args, **kwargs: called.append("send"))
    bot.music_panel_creator_audit_text()
    bot.music_job_debug_text("MUS-NOJOB")
    bot.product_progress_debug_text("MUS-NOJOB", "music_song", {})
    bot.progress_auto_refresh_status_text("MUS-NOJOB")
    assert called == []
