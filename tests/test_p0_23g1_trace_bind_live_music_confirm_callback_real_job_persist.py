import asyncio
from types import SimpleNamespace

import bot


class CaptureMessage:
    def __init__(self, chat_id=231001):
        self.chat_id = chat_id
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"kind": "text", "text": text, **kwargs})
        return SimpleNamespace(chat_id=self.chat_id, message_id=100 + len(self.outputs))


class CaptureQuery:
    def __init__(self, user_id=231001, data="music_quick|showroom|music_ai_confirm"):
        self.data = data
        self.message = CaptureMessage(user_id)
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _reset():
    bot.PROGRESS_AUTO_REFRESH_JOBS.clear()
    bot.PROGRESS_AUTO_REFRESH_TASKS.clear()
    bot.ENGINE_ASYNC_MEMORY_JOBS.clear()
    bot.MUSIC_PRODUCT_DELIVERY_MEMORY_LOCKS.clear()
    bot.USER_PENDING.clear()


def _legacy_result(mode="background"):
    payload = {
        "music_product_mode": mode,
        "selected_prompt": "bright TOAN AAS brand music, clean production",
        "description": "Nhac thuong hieu TOAN AAS",
        "genre": "pop",
        "mood": "bright",
        "duration_seconds": 60,
        "music_ai_kind": "lyrics" if mode == "song" else "guided",
    }
    if mode == "song":
        payload.update({
            "song_product": "full",
            "lyrics": "TOAN AAS luon dong hanh",
            "vocal_mode": "female",
        })
    return payload


def _product_result(mode="background"):
    payload = {
        "music_product_mode": mode,
        "music_product_tier": "music_tier_standard",
        "description": "Nhac thuong hieu TOAN AAS",
        "genre": "pop",
        "mood": "bright",
        "duration_seconds": 60,
    }
    if mode == "song":
        payload.update({"lyrics": "TOAN AAS luon dong hanh", "vocal_mode": "female"})
    return bot.music_product_result_from_input(payload)


def _patch_live_confirm(monkeypatch, *, guided_result, engine_result=None, save_raises=False):
    _reset()
    user_id = 231001
    bot.save_music_guided_result(user_id, guided_result)
    store = {}
    save_events = []
    submit_calls = []
    start_calls = []

    def fake_save(payload):
        if save_raises:
            raise RuntimeError("db locked")
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
                "task_id": "provider-task-23g1",
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


def _run_live_confirm(monkeypatch, *, guided_result, callback_data="music_quick|showroom|music_ai_confirm", **patch_kwargs):
    state = _patch_live_confirm(monkeypatch, guided_result=guided_result, **patch_kwargs)
    query = CaptureQuery(state.user_id, callback_data)
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=state.user_id))
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    return state, query


def _last_job(state):
    return list(state.store.values())[-1]


def test_music_confirm_route_audit_lists_all_music_confirm_callbacks():
    text = bot.music_confirm_route_audit_text()
    assert "music_bg" in text
    assert "music_song" in text
    assert "music_ai_confirm" in text
    assert "package/video-addon" in text
    assert "prompt/style" in text
    assert "handle_music_quick_callback" in text
    assert "handle_music_product_confirm" in text


def test_music_bg_live_confirm_callback_calls_persist_helper(monkeypatch):
    state, _query = _run_live_confirm(monkeypatch, guided_result=_legacy_result("background"))
    job = _last_job(state)
    assert job["product_type"] == "music_bg"
    assert job["persist_helper_called"] is True


def test_music_song_live_confirm_callback_calls_persist_helper(monkeypatch):
    state, _query = _run_live_confirm(monkeypatch, guided_result=_legacy_result("song"))
    job = _last_job(state)
    assert job["product_type"] == "music_song"
    assert job["persist_helper_called"] is True


def test_package_confirm_music_callback_calls_persist_helper(monkeypatch):
    callback = "music_quick|video_addon|music_ai_confirm"
    state, _query = _run_live_confirm(monkeypatch, guided_result=_product_result("song"), callback_data=callback)
    job = _last_job(state)
    assert job["persist_helper_called"] is True
    assert job["confirm_route"] == callback


def test_legacy_music_confirm_wrapper_calls_new_helper(monkeypatch):
    state, _query = _run_live_confirm(monkeypatch, guided_result=_legacy_result("background"))
    job = _last_job(state)
    assert job["music_product_flow"] == "p0_20a_3_tier"
    assert job["confirm_handler_name"] == "handle_music_quick_callback"


def test_confirm_route_saved_to_music_job_debug(monkeypatch):
    state, _query = _run_live_confirm(monkeypatch, guided_result=_product_result("background"))
    job_id = next(iter(state.store))
    text = bot.music_job_debug_text(job_id)
    assert "confirm_route: <code>music_quick|showroom|music_ai_confirm</code>" in text


def test_confirm_callback_data_saved_to_music_job_debug(monkeypatch):
    callback = "music_quick|showroom|music_ai_confirm"
    state, _query = _run_live_confirm(monkeypatch, guided_result=_product_result("song"), callback_data=callback)
    job_id = next(iter(state.store))
    text = bot.music_job_debug_text(job_id)
    assert f"confirm_callback_data: <code>{callback}</code>" in text


def test_persist_helper_called_true_for_new_confirmed_job(monkeypatch):
    state, _query = _run_live_confirm(monkeypatch, guided_result=_product_result("background"))
    assert _last_job(state)["persist_helper_called"] is True


def test_new_confirmed_music_job_not_missing_job(monkeypatch):
    state, _query = _run_live_confirm(monkeypatch, guided_result=_product_result("song"))
    job_id = next(iter(state.store))
    assert "missing_job" not in bot.music_job_debug_text(job_id)


def test_no_progress_panel_without_real_job_persist(monkeypatch):
    state, query = _run_live_confirm(monkeypatch, guided_result=_product_result("background"), save_raises=True)
    assert state.submit_calls == []
    assert bot.PROGRESS_AUTO_REFRESH_JOBS == {}
    assert len(query.message.outputs) == 1
    assert "chưa trừ Xu" in query.message.outputs[0]["text"]


def test_provider_submit_called_after_live_confirm_route(monkeypatch):
    state, _query = _run_live_confirm(monkeypatch, guided_result=_product_result("song"))
    assert len(state.submit_calls) == 1
    assert state.submit_calls[0][3]


def test_provider_job_id_saved_after_live_confirm_route(monkeypatch):
    state, _query = _run_live_confirm(monkeypatch, guided_result=_product_result("background"))
    job = _last_job(state)
    assert job["provider_task_id"] == "provider-task-23g1"
    assert job["provider_job_id"] == "provider-task-23g1"


def test_auto_tick_started_after_live_confirm_route(monkeypatch):
    state, _query = _run_live_confirm(monkeypatch, guided_result=_product_result("song"))
    assert state.start_calls
    assert state.start_calls[0] in bot.PROGRESS_AUTO_REFRESH_JOBS


def test_no_provider_submit_before_final_confirm(monkeypatch):
    called = []
    monkeypatch.setattr(bot, "execute_engine", lambda *args, **kwargs: called.append(True))
    result = _product_result("song")
    bot.music_product_invoice_text(result, "vi")
    bot.music_product_invoice_keyboard(result, "vi", bot.PRODUCT_CONTEXT_SHOWROOM)
    assert called == []
