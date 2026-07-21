import asyncio
from types import SimpleNamespace

import bot


class CaptureMessage:
    def __init__(self, chat_id=230701):
        self.chat_id = chat_id
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"kind": "text", "text": text, **kwargs})
        return SimpleNamespace(chat_id=self.chat_id, message_id=100 + len(self.outputs))


class CaptureQuery:
    def __init__(self, user_id=230701):
        self.data = "music_quick|showroom|music_ai_confirm"
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


def _result(mode="song"):
    payload = {
        "music_product_mode": mode,
        "music_product_tier": "music_tier_standard",
        "description": "Nhạc thương hiệu TOAN AAS",
        "genre": "pop",
        "mood": "tươi sáng",
        "duration_seconds": 60,
    }
    if mode == "song":
        payload.update({"lyrics": "TOAN AAS luôn đồng hành", "vocal_mode": "female"})
    return bot.music_product_result_from_input(payload)


def _patch_confirm(monkeypatch, *, engine_result=None, start_task=True, save_raises=False):
    _reset()
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
                "task_id": "provider-task-23g0",
                "status": "PASS_SUBMITTED",
            },
        }

    def fake_start(_context, key):
        start_calls.append(key)
        return bool(start_task)

    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda job_id: dict(store.get(str(job_id), {})))
    monkeypatch.setattr(bot, "can_user_access_product_engine", lambda *args, **kwargs: {"allowed": True})
    monkeypatch.setattr(bot, "get_user", lambda uid: (999, None, None))
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: False)
    monkeypatch.setattr(bot, "execute_engine", fake_execute)
    monkeypatch.setattr(bot, "progress_auto_refresh_start_task", fake_start)
    return SimpleNamespace(store=store, save_events=save_events, submit_calls=submit_calls, start_calls=start_calls)


def _run_confirm(monkeypatch, *, user_id=230701, mode="song", **patch_kwargs):
    state = _patch_confirm(monkeypatch, **patch_kwargs)
    query = CaptureQuery(user_id)
    result = _result(mode)
    asyncio.run(bot.handle_music_product_confirm(
        query,
        SimpleNamespace(),
        user_id=user_id,
        lang="vi",
        product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
        result=result,
    ))
    return state, query


def test_music_confirm_persists_real_job_before_panel(monkeypatch):
    state, query = _run_confirm(monkeypatch)
    assert query.message.outputs[0]["kind"] == "text"
    persisted_before_submit = state.submit_calls[0][3]
    assert len(persisted_before_submit) == 1
    job = next(iter(persisted_before_submit.values()))
    assert job["internal_job_id"]
    assert job["status"] in {"pending_submit", "submitting"}


def test_music_confirm_saves_user_id_chat_id(monkeypatch):
    state, _query = _run_confirm(monkeypatch, user_id=230702)
    job = list(state.store.values())[-1]
    assert job["user_id"] == "230702"
    assert job["chat_id"] == "230702"


def test_music_confirm_saves_product_type_music_bg(monkeypatch):
    state, _query = _run_confirm(monkeypatch, user_id=230703, mode="background")
    job = list(state.store.values())[-1]
    assert job["product_type"] == "music_bg"
    assert job["music_product_type"] == "music_bg"


def test_music_confirm_saves_product_type_music_song(monkeypatch):
    state, _query = _run_confirm(monkeypatch, user_id=230704, mode="song")
    job = list(state.store.values())[-1]
    assert job["product_type"] == "music_song"
    assert job["music_product_type"] == "music_song"


def test_music_confirm_saves_progress_registry_after_panel(monkeypatch):
    state, query = _run_confirm(monkeypatch, user_id=230705)
    job_id = next(iter(state.store))
    key = bot.progress_auto_refresh_key("music_song", job_id)
    record = bot.PROGRESS_AUTO_REFRESH_JOBS[key]
    assert record["job_id"] == job_id
    assert record["chat_id"] == query.message.chat_id
    assert int(record["message_id"]) == 101
    assert record["product_type"] == "music_song"


def test_music_confirm_calls_provider_submit_after_job_persist(monkeypatch):
    state, _query = _run_confirm(monkeypatch, user_id=230706)
    assert len(state.submit_calls) == 1
    assert state.submit_calls[0][3]


def test_music_confirm_sets_provider_submit_called(monkeypatch):
    state, _query = _run_confirm(monkeypatch, user_id=230707)
    job = list(state.store.values())[-1]
    assert job["provider_submit_called"] is True
    assert job["confirm_submit_phase"] == "submitted"


def test_music_confirm_saves_provider_job_id_when_accepted(monkeypatch):
    state, _query = _run_confirm(monkeypatch, user_id=230708)
    job = list(state.store.values())[-1]
    assert job["provider_task_id"] == "provider-task-23g0"
    assert job["provider_job_id"] == "provider-task-23g0"


def test_music_confirm_starts_auto_tick_after_registry_saved(monkeypatch):
    state, _query = _run_confirm(monkeypatch, user_id=230709)
    assert state.start_calls
    key = state.start_calls[0]
    assert key in bot.PROGRESS_AUTO_REFRESH_JOBS
    assert bot.PROGRESS_AUTO_REFRESH_JOBS[key]["registry_saved"] is True


def test_music_job_debug_new_job_not_missing_job(monkeypatch):
    state, _query = _run_confirm(monkeypatch, user_id=230710)
    job_id = next(iter(state.store))
    text = bot.music_job_debug_text(job_id)
    assert "missing_job" not in text
    assert "provider_submit_called: <code>yes</code>" in text
    assert "provider-task" not in text


def test_music_persist_fail_clean_no_charge_no_fake_panel(monkeypatch):
    _reset()
    _patch_confirm(monkeypatch, save_raises=True)
    query = CaptureQuery(230711)
    asyncio.run(bot.handle_music_product_confirm(
        query,
        SimpleNamespace(),
        user_id=230711,
        lang="vi",
        product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
        result=_result("song"),
    ))
    assert len(query.message.outputs) == 1
    assert "chưa trừ Xu" in query.message.outputs[-1]["text"]
    assert "TOAN AAS đang tạo bài hát" not in query.message.outputs[-1]["text"]
    assert bot.PROGRESS_AUTO_REFRESH_JOBS == {}


def test_music_provider_submit_fail_clean_no_charge(monkeypatch):
    state, query = _run_confirm(
        monkeypatch,
        user_id=230712,
        engine_result={"ok": False, "status": "FAILED", "detail": "provider rejected"},
    )
    job = list(state.store.values())[-1]
    assert job["terminal_state"] == "failed_no_charge"
    assert job["confirm_submit_blocker"] == "provider_submit_failed"
    assert job["confirm_submit_phase"] == "submit_failed"
    assert "chưa trừ Xu" in query.message.outputs[-1]["text"]


def test_music_no_provider_before_final_confirm(monkeypatch):
    called = []
    monkeypatch.setattr(bot, "execute_engine", lambda *args, **kwargs: called.append(True))
    result = _result("song")
    bot.music_product_invoice_text(result, "vi")
    bot.music_product_invoice_keyboard(result, "vi", bot.PRODUCT_CONTEXT_SHOWROOM)
    assert called == []


def test_music_no_generic_error_for_known_confirm_failure(monkeypatch):
    _reset()
    monkeypatch.setattr(bot, "get_music_guided_result", lambda uid: {"music_internal_job_id": "MUS-G0-FAIL"})
    monkeypatch.setattr(bot, "get_engine_async_job", lambda job_id: {
        "internal_job_id": job_id,
        "feature": "music_suno",
        "status": "failed",
        "terminal_state": "failed_no_charge",
        "confirm_submit_blocker": "provider_submit_failed",
        "error_category": "provider_submit_failed",
    })
    sent = []
    fake_bot = SimpleNamespace(send_message=lambda **kwargs: sent.append(kwargs))
    update = SimpleNamespace(
        callback_query=SimpleNamespace(data="music_quick|showroom|music_ai_confirm"),
        effective_user=SimpleNamespace(id=230713),
        effective_chat=SimpleNamespace(id=230713),
        effective_message=None,
    )
    asyncio.run(bot.on_telegram_error(update, SimpleNamespace(error=RuntimeError("known music submit fail"), bot=fake_bot, chat_data={})))
    assert sent == []
