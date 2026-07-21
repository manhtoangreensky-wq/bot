import asyncio
from types import SimpleNamespace

import bot


class CaptureMessage:
    def __init__(self, user_id=230901):
        self.chat_id = user_id
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"kind": "text", "text": text, **kwargs})
        return SimpleNamespace(chat_id=self.chat_id, message_id=100 + len(self.outputs))

    async def reply_audio(self, audio=None, filename="", caption="", **kwargs):
        self.outputs.append({"kind": "audio", "audio": audio, "filename": filename, "caption": caption, **kwargs})
        return SimpleNamespace(message_id=200 + len(self.outputs), audio=SimpleNamespace(file_id="music-file"))


class CaptureQuery:
    def __init__(self, user_id=230901):
        self.data = "music_quick|showroom|music_ai_confirm"
        self.message = CaptureMessage(user_id)
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


class FakeBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)
        return SimpleNamespace(message_id=len(self.messages))


def _reset():
    bot.PROGRESS_AUTO_REFRESH_JOBS.clear()
    bot.PROGRESS_AUTO_REFRESH_TASKS.clear()
    bot.ENGINE_ASYNC_MEMORY_JOBS.clear()
    bot.MUSIC_PRODUCT_DELIVERY_MEMORY_LOCKS.clear()
    bot.USER_PENDING.clear()


def _result():
    return bot.music_product_result_from_input({
        "music_product_mode": "background",
        "music_product_tier": "music_tier_standard",
        "description": "Nhạc nền AI thương hiệu TOAN AAS",
        "genre": "cinematic pop",
        "mood": "tươi sáng",
        "duration_seconds": 60,
    })


def _patch_confirm(monkeypatch, *, engine_result=None, start_task=True):
    _reset()
    store = {}
    saves = []
    submit_calls = []
    start_calls = []

    def fake_save(payload):
        current = dict(payload)
        store[str(current.get("internal_job_id") or "")] = current
        saves.append(current)
        return dict(current)

    async def fake_execute(feature, params, context):
        submit_calls.append((feature, params, context))
        return engine_result or {"ok": True, "provider_result": {"ok": True, "provider": "key4u_suno", "task_id": "provider-task-23e", "status": "PASS_SUBMITTED"}}

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
    return SimpleNamespace(store=store, saves=saves, submit_calls=submit_calls, start_calls=start_calls)


def test_music_confirm_calls_provider_submit_once(monkeypatch):
    state = _patch_confirm(monkeypatch)
    query = CaptureQuery()
    asyncio.run(bot.handle_music_product_confirm(query, SimpleNamespace(), user_id=230901, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result()))
    assert len(state.submit_calls) == 1
    assert state.submit_calls[0][2]["confirm_paid"] is True


def test_music_confirm_saves_provider_job_id(monkeypatch):
    state = _patch_confirm(monkeypatch)
    query = CaptureQuery()
    asyncio.run(bot.handle_music_product_confirm(query, SimpleNamespace(), user_id=230902, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result()))
    saved = list(state.store.values())[-1]
    assert saved["provider_task_id"] == "provider-task-23e"
    assert saved["provider_job_id"] == "provider-task-23e"
    assert saved["status"] == "submitted"


def test_music_confirm_provider_submit_fail_not_stuck_5(monkeypatch):
    state = _patch_confirm(monkeypatch, engine_result={"ok": False, "status": "FAILED", "detail": "provider rejected"})
    query = CaptureQuery()
    asyncio.run(bot.handle_music_product_confirm(query, SimpleNamespace(), user_id=230903, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result()))
    failed = list(state.store.values())[-1]
    assert failed["terminal_state"] == "failed_no_charge"
    assert failed["confirm_submit_blocker"] == "provider_submit_failed"
    assert int(failed["progress_percent"]) > 5
    assert "chưa trừ Xu" in query.message.outputs[-1]["text"]


def test_music_confirm_job_persist_fail_clean_no_charge(monkeypatch):
    _reset()
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: (_ for _ in ()).throw(RuntimeError("db locked")))
    monkeypatch.setattr(bot, "can_user_access_product_engine", lambda *args, **kwargs: {"allowed": True})
    monkeypatch.setattr(bot, "get_user", lambda uid: (999, None, None))
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: False)
    monkeypatch.setattr(bot, "execute_engine", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider submit must not run after persist fail")))
    query = CaptureQuery()
    asyncio.run(bot.handle_music_product_confirm(query, SimpleNamespace(), user_id=230904, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result()))
    assert "chưa trừ Xu" in query.message.outputs[-1]["text"]
    assert any(job.get("confirm_submit_blocker") == "job_persist_failed" for job in bot.ENGINE_ASYNC_MEMORY_JOBS.values())


def test_music_auto_tick_starts_after_confirm(monkeypatch):
    state = _patch_confirm(monkeypatch)
    query = CaptureQuery()
    asyncio.run(bot.handle_music_product_confirm(query, SimpleNamespace(), user_id=230905, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result()))
    assert state.start_calls
    job_id = state.start_calls[0].split(":", 1)[1]
    assert state.store[job_id]["provider_task_id"] == "provider-task-23e"


def test_music_auto_tick_start_failure_debugged(monkeypatch):
    state = _patch_confirm(monkeypatch, start_task=False)
    query = CaptureQuery()
    asyncio.run(bot.handle_music_product_confirm(query, SimpleNamespace(), user_id=230906, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result()))
    job_id = next(iter(state.store))
    assert state.store[job_id]["confirm_submit_blocker"] == "scheduler_start_failed"
    text = bot.progress_auto_refresh_status_text(job_id)
    assert "scheduler_failed" in text
    assert "stopped_reason" in text


def test_music_generic_error_not_sent_for_known_music_submit_failure(monkeypatch):
    _reset()
    job = {
        "internal_job_id": "MUS-23E-FAIL",
        "user_id": "230907",
        "feature": "music_suno",
        "status": "failed",
        "terminal_state": "failed_no_charge",
        "confirm_submit_blocker": "provider_submit_failed",
        "error_category": "provider_submit_failed",
    }
    monkeypatch.setattr(bot, "get_music_guided_result", lambda uid: {"music_internal_job_id": "MUS-23E-FAIL"})
    monkeypatch.setattr(bot, "get_engine_async_job", lambda job_id: dict(job) if job_id == "MUS-23E-FAIL" else {})
    fake_bot = FakeBot()
    update = SimpleNamespace(
        callback_query=SimpleNamespace(data="music_quick|showroom|music_ai_confirm"),
        effective_user=SimpleNamespace(id=230907),
        effective_chat=SimpleNamespace(id=230907),
        effective_message=None,
    )
    asyncio.run(bot.on_telegram_error(update, SimpleNamespace(error=RuntimeError("known submit fail"), bot=fake_bot, chat_data={})))
    assert fake_bot.messages == []


def test_music_debug_shows_confirm_submit_blocker(monkeypatch):
    monkeypatch.setattr(bot, "get_engine_async_job", lambda job_id: {
        "internal_job_id": job_id,
        "feature": "music_suno",
        "status": "failed",
        "terminal_state": "failed_no_charge",
        "confirm_submit_blocker": "provider_job_id_missing_after_submit",
        "error_category": "provider_job_id_missing_after_submit",
    })
    text = bot.music_job_debug_text("MUS-23E-DBG")
    assert "provider_job_id_missing_after_submit" in text


def test_music_no_provider_before_final_confirm(monkeypatch):
    called = []
    monkeypatch.setattr(bot, "execute_engine", lambda *args, **kwargs: called.append(True))
    result = _result()
    bot.music_product_invoice_text(result, "vi")
    bot.music_product_invoice_keyboard(result, "vi", bot.PRODUCT_CONTEXT_SHOWROOM)
    assert called == []


def test_music_no_charge_when_submit_fails(monkeypatch):
    _patch_confirm(monkeypatch, engine_result={"ok": False, "status": "FAILED", "detail": "submit failed"})
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("charged on submit fail")))
    query = CaptureQuery()
    asyncio.run(bot.handle_music_product_confirm(query, SimpleNamespace(), user_id=230908, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result()))
    assert "chưa trừ Xu" in query.message.outputs[-1]["text"]
