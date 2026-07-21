import asyncio
from types import SimpleNamespace

import bot


class CaptureMessage:
    def __init__(self, chat_id=232001):
        self.chat_id = chat_id
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"kind": "text", "text": text, **kwargs})
        return SimpleNamespace(chat_id=self.chat_id, message_id=100 + len(self.outputs))

    async def reply_audio(self, **kwargs):
        self.outputs.append({"kind": "audio", **kwargs})
        return SimpleNamespace(message_id=200 + len(self.outputs), audio=SimpleNamespace(file_id="reply-audio-23h"))


class CaptureQuery:
    def __init__(self, user_id=232001, data="music_quick|showroom|music_ai_confirm"):
        self.data = data
        self.message = CaptureMessage(user_id)
        self.from_user = SimpleNamespace(id=user_id)
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


class FakeBot:
    def __init__(self, *, with_message_id=True):
        self.with_message_id = with_message_id
        self.edits = []
        self.audios = []
        self.messages = []

    async def edit_message_text(self, **kwargs):
        self.edits.append(kwargs)
        return SimpleNamespace(message_id=kwargs.get("message_id") or 1)

    async def send_audio(self, **kwargs):
        self.audios.append(kwargs)
        message_id = 700 + len(self.audios) if self.with_message_id else 0
        return SimpleNamespace(message_id=message_id, audio=SimpleNamespace(file_id=f"audio-{len(self.audios)}"))

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)
        return SimpleNamespace(message_id=800 + len(self.messages))


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
        "description": "TOAN AAS brand music",
        "genre": "pop",
        "mood": "bright",
        "duration_seconds": 60,
    }
    if mode == "song":
        payload.update({"lyrics": "TOAN AAS luon dong hanh", "vocal_mode": "female"})
    return bot.music_product_result_from_input(payload)


def _base_job(**overrides):
    job = {
        "internal_job_id": "MUS23H",
        "feature": "music_suno",
        "user_id": "232001",
        "chat_id": "232001",
        "product_type": "music_song",
        "music_product_type": "music_song",
        "status": "submitted",
        "provider": "key4u_suno",
        "provider_task_id": "provider-task-23h",
        "provider_job_id": "provider-task-23h",
        "provider_submit_called": True,
        "provider_style_prompt": "bright pop, female lead vocal",
        "provider_lyrics": "TOAN AAS",
        "lyrics_prepared": True,
        "style_prepared": True,
        "output_bytes": 0,
        "progress_percent": 12,
        "music_product_flow": "p0_20a_3_tier",
        "music_product_mode": "song",
        "music_product_tier": "music_tier_standard",
    }
    job.update(overrides)
    return job


def _patch_store(monkeypatch, initial=None):
    store = {}
    if initial:
        store[str(initial.get("internal_job_id") or "MUS23H")] = dict(initial)

    def fake_save(payload):
        current = dict(payload)
        store[str(current.get("internal_job_id") or "")] = current
        return dict(current)

    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda job_id: dict(store.get(str(job_id), {})))
    return store


def _patch_confirm(monkeypatch, *, engine_result=None, mode="song"):
    _reset()
    store = _patch_store(monkeypatch)
    submit_calls = []
    start_calls = []
    user_id = 232001
    bot.save_music_guided_result(user_id, _result(mode))

    async def fake_execute(feature, params, context):
        submit_calls.append((feature, params, context, dict(store)))
        return engine_result or {
            "ok": True,
            "provider_result": {
                "ok": True,
                "provider": "key4u_suno",
                "task_id": "provider-task-23h",
                "status": "PASS_SUBMITTED",
            },
        }

    def fake_start(_context, key):
        start_calls.append(key)
        bot.PROGRESS_AUTO_REFRESH_JOBS[key].update({
            "task_started": True,
            "task_alive": True,
            "task_started_at": bot.now_text(),
            "scheduler_mode": "asyncio_task",
        })
        return True

    monkeypatch.setattr(bot, "execute_engine", fake_execute)
    monkeypatch.setattr(bot, "can_user_access_product_engine", lambda *args, **kwargs: {"allowed": True})
    monkeypatch.setattr(bot, "get_user", lambda uid: (999, None, None))
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: False)
    monkeypatch.setattr(bot, "progress_auto_refresh_start_task", fake_start)
    query = CaptureQuery(user_id)
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=user_id))
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace(bot=FakeBot())))
    return SimpleNamespace(store=store, submit_calls=submit_calls, start_calls=start_calls, query=query, user_id=user_id)


def _patch_delivery(monkeypatch, *, selector=None, bot_instance=None, job=None):
    _reset()
    store = _patch_store(monkeypatch, job or _base_job())
    fake_bot = bot_instance or FakeBot()
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: True)
    monkeypatch.setattr(bot, "music_product_charge_after_delivery", lambda *args, **kwargs: {"ok": True, "charged_xu": 0})
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **kwargs: {"vault_id": "vault-23h", "storage_ref": ""})
    monkeypatch.setattr(bot, "get_music_vault_entry", lambda _vault_id: {})
    monkeypatch.setattr(bot, "mark_music_vault_status", lambda *args, **kwargs: None)
    if selector is None:
        async def selector(*args, **kwargs):
            return {
                "ok": True,
                "audio_bytes": b"real-mp3-bytes-23h",
                "artifact_candidates_count": 1,
                "selected_artifact_id": "artifact-23h",
                "selected_artifact_hash": "hash-23h",
                "selected_artifact_duration": 60,
                "selected_artifact_bytes": 19,
            }
    monkeypatch.setattr(bot, "select_music_delivery_artifact", selector)
    return store, fake_bot


def test_music_live_confirm_persists_real_job(monkeypatch):
    state = _patch_confirm(monkeypatch)
    job = list(state.store.values())[-1]
    assert job["internal_job_id"].startswith("MUS")
    assert job["user_id"] == str(state.user_id)
    assert job["chat_id"] == str(state.user_id)
    assert job["product_type"] == "music_song"


def test_music_job_debug_not_missing_job_after_confirm(monkeypatch):
    state = _patch_confirm(monkeypatch)
    job_id = next(iter(state.store))
    assert "missing_job" not in bot.music_job_debug_text(job_id)


def test_music_confirm_route_fields_saved(monkeypatch):
    state = _patch_confirm(monkeypatch)
    job = list(state.store.values())[-1]
    assert job["confirm_route"] == "music_quick|showroom|music_ai_confirm"
    assert job["confirm_callback_data"] == "music_quick|showroom|music_ai_confirm"
    assert job["confirm_handler_name"] == "handle_music_quick_callback"
    assert job["persist_helper_called"] is True


def test_music_provider_submit_called_after_confirm(monkeypatch):
    state = _patch_confirm(monkeypatch)
    assert len(state.submit_calls) == 1
    assert list(state.store.values())[-1]["provider_submit_called"] is True


def test_music_provider_job_id_saved_when_accepted(monkeypatch):
    state = _patch_confirm(monkeypatch)
    job = list(state.store.values())[-1]
    assert job["provider_task_id"] == "provider-task-23h"
    assert job["provider_job_id"] == "provider-task-23h"


def test_music_no_provider_submit_before_final_confirm(monkeypatch):
    called = []
    monkeypatch.setattr(bot, "execute_engine", lambda *args, **kwargs: called.append(True))
    result = _result("song")
    bot.music_product_invoice_text(result, "vi")
    bot.music_product_invoice_keyboard(result, "vi", bot.PRODUCT_CONTEXT_SHOWROOM)
    assert called == []


def test_music_no_duplicate_provider_submit_on_update(monkeypatch):
    job = _base_job()
    _patch_store(monkeypatch, job)
    called = []
    monkeypatch.setattr(bot, "execute_engine", lambda *args, **kwargs: called.append(True))

    async def fake_poll(*args, **kwargs):
        return {"ok": False, "status": "PROCESSING", "job": job, "audio_bytes": b""}

    monkeypatch.setattr(bot, "poll_music_suno_async_job", fake_poll)
    asyncio.run(bot.music_progress_refresh_job_status("MUS23H", user_id=232001))
    assert called == []


def test_music_auto_tick_starts_after_registry(monkeypatch):
    state = _patch_confirm(monkeypatch)
    assert state.start_calls
    record = bot.PROGRESS_AUTO_REFRESH_JOBS[state.start_calls[0]]
    assert record["registry_saved"] is True
    assert record["task_started"] is True


def test_music_auto_tick_runs_without_user_click(monkeypatch):
    job = _base_job()
    _patch_store(monkeypatch, job)
    fake_bot = FakeBot()
    record = bot.progress_auto_refresh_register(
        product_type="music_song",
        job_id="MUS23H",
        chat_id=232001,
        message_id=10,
        user_id=232001,
        initial_snapshot={"stage": "received_request", "percent": 5, "terminal_state": "", "text": "old", "render_hash": "old"},
        start_task=False,
    )

    async def fake_refresh(*args, **kwargs):
        return {**job, "status": "processing", "progress_percent": 65}

    monkeypatch.setattr(bot, "music_progress_refresh_job_status", fake_refresh)
    result = asyncio.run(bot.progress_auto_refresh_tick(SimpleNamespace(bot=fake_bot), record["key"]))
    assert result["record"]["update_count"] == 1
    assert result["record"]["last_tick_at"]


def test_music_auto_tick_fallback_asyncio_when_job_queue_missing(monkeypatch):
    _reset()
    _patch_store(monkeypatch, _base_job())

    async def run_register():
        record = bot.progress_auto_refresh_register(
            product_type="music_song",
            job_id="MUS23H",
            chat_id=232001,
            message_id=10,
            user_id=232001,
            context=SimpleNamespace(bot=FakeBot()),
            initial_snapshot={"stage": "received_request", "percent": 5, "terminal_state": "", "text": "old", "render_hash": "old"},
            start_task=True,
        )
        await asyncio.sleep(0)
        return bot.PROGRESS_AUTO_REFRESH_JOBS[record["key"]]

    record = asyncio.run(run_register())
    assert record["task_started"] is True
    assert record["scheduler_mode"] == "asyncio_task"


def test_progress_auto_refresh_status_has_last_tick(monkeypatch):
    job = _base_job()
    _patch_store(monkeypatch, job)
    record = bot.progress_auto_refresh_register(
        product_type="music_song",
        job_id="MUS23H",
        chat_id=232001,
        message_id=10,
        user_id=232001,
        initial_snapshot={"stage": "received_request", "percent": 5, "terminal_state": "", "text": "old", "render_hash": "old"},
        start_task=False,
    )
    asyncio.run(bot.progress_auto_refresh_tick(SimpleNamespace(bot=FakeBot()), record["key"]))
    text = bot.progress_auto_refresh_status_text("MUS23H")
    assert "registry_saved: <code>true</code>" in text
    assert "last_tick_at" in text
    assert "update_count/max" in text


def test_music_poll_uses_provider_job_id(monkeypatch):
    job = _base_job(provider_task_id="provider-job-xyz", provider_job_id="provider-job-xyz")
    _patch_store(monkeypatch, job)
    seen = []

    async def fake_poll(state, updated_by=""):
        seen.append(dict(state))
        return {"ok": False, "status": "PROCESSING"}

    monkeypatch.setattr(bot, "poll_music_generation_job", fake_poll)
    asyncio.run(bot.poll_music_suno_async_job("MUS23H"))
    assert seen[0]["music_task_id"] == "provider-job-xyz"


def test_music_provider_completed_sets_artifact_ready(monkeypatch):
    job = _base_job()
    store = _patch_store(monkeypatch, job)

    async def fake_poll(*args, **kwargs):
        return {"ok": True, "status": "COMPLETED", "output_url": "https://example.test/song.mp3"}

    monkeypatch.setattr(bot, "poll_music_generation_job", fake_poll)
    monkeypatch.setattr(bot, "_download_music_audio_url_bytes", lambda *args, **kwargs: asyncio.sleep(0, result=(b"mp3-bytes", "", 200)))
    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", lambda *args, **kwargs: asyncio.sleep(0, result=60))
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **kwargs: {"vault_id": "vault-23h", "storage_ref": ""})
    result = asyncio.run(bot.poll_music_suno_async_job("MUS23H"))
    saved = store["MUS23H"]
    assert result["ok"] is True
    assert saved["provider_completed"] is True
    assert saved["artifact_ready"] is True
    assert saved["audio_validated"] is True
    assert saved["output_bytes"] > 0


def test_music_artifact_validation_requires_bytes_duration(monkeypatch):
    async def no_bytes(*args, **kwargs):
        return {"ok": False, "status": "ARTIFACT_BYTES_MISSING", "artifact_candidates_count": 1}

    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", lambda *args, **kwargs: asyncio.sleep(0, result=0))
    result = asyncio.run(no_bytes())
    assert result["ok"] is False
    assert "MISSING" in result["status"]


def test_music_zero_duration_audio_blocks_success(monkeypatch):
    async def fake_duration(*args, **kwargs):
        return 0

    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", fake_duration)
    result = asyncio.run(bot.select_music_delivery_artifact({}, {"duration_seconds": 0}, b"not-real-audio"))
    assert result["ok"] is False
    assert result["status"] == "AUDIO_DURATION_MISSING"


def test_music_delivers_mp3_after_valid_artifact(monkeypatch):
    store, fake_bot = _patch_delivery(monkeypatch)
    result = asyncio.run(bot.deliver_music_result_once(
        CaptureMessage(),
        SimpleNamespace(bot=fake_bot),
        user_id=232001,
        lang="vi",
        product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
        result=_result(),
        audio_bytes=b"real-mp3-bytes-23h",
        job=store["MUS23H"],
        source="auto_tick",
        send_success_message=True,
    ))
    assert result["ok"] is True
    assert len(fake_bot.audios) == 1
    assert store["MUS23H"]["terminal_state"] == "delivered"


def test_music_delivery_success_requires_telegram_message_id(monkeypatch):
    store, fake_bot = _patch_delivery(monkeypatch, bot_instance=FakeBot(with_message_id=False))
    result = asyncio.run(bot.deliver_music_result_once(
        CaptureMessage(),
        SimpleNamespace(bot=fake_bot),
        user_id=232001,
        lang="vi",
        product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
        result=_result(),
        audio_bytes=b"real-mp3-bytes-23h",
        job=store["MUS23H"],
        source="auto_tick",
    ))
    assert result["ok"] is False
    assert result["status"] == "TELEGRAM_MESSAGE_ID_MISSING"
    assert store["MUS23H"].get("terminal_state") != "delivered"


def test_music_delivery_once_with_manual_update_race(monkeypatch):
    store, fake_bot = _patch_delivery(monkeypatch)
    first = asyncio.run(bot.deliver_music_result_once(
        CaptureMessage(),
        SimpleNamespace(bot=fake_bot),
        user_id=232001,
        lang="vi",
        product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
        result=_result(),
        audio_bytes=b"real-mp3-bytes-23h",
        job=store["MUS23H"],
        source="auto_tick",
    ))
    second = asyncio.run(bot.deliver_music_result_once(
        CaptureMessage(),
        SimpleNamespace(bot=fake_bot),
        user_id=232001,
        lang="vi",
        product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
        result=first["result"],
        audio_bytes=b"real-mp3-bytes-23h",
        job=first["job"],
        source="manual_update",
    ))
    assert first["ok"] is True
    assert second["duplicate"] is True
    assert len(fake_bot.audios) == 1


def test_music_terminal_delivered_blocks_duplicate_success(monkeypatch):
    job = _base_job(status="delivered", terminal_state="delivered", music_delivery_message_id="9001")
    store, fake_bot = _patch_delivery(monkeypatch, job=job)
    result = asyncio.run(bot.deliver_music_result_once(
        CaptureMessage(),
        SimpleNamespace(bot=fake_bot),
        user_id=232001,
        lang="vi",
        product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
        result=_result(),
        audio_bytes=b"real-mp3-bytes-23h",
        job=store["MUS23H"],
        source="manual_update",
    ))
    assert result["duplicate"] is True
    assert fake_bot.audios == []


def test_music_submit_fail_failed_no_charge(monkeypatch):
    state = _patch_confirm(monkeypatch, engine_result={"ok": False, "status": "FAILED", "detail": "provider rejected"})
    job = list(state.store.values())[-1]
    assert job["terminal_state"] == "failed_no_charge"
    assert job["confirm_submit_blocker"] == "provider_submit_failed"
    assert "chưa trừ Xu" in state.query.message.outputs[-1]["text"]


def test_music_provider_timeout_failed_no_charge(monkeypatch):
    job = _base_job(status="processing")
    _patch_store(monkeypatch, job)
    monkeypatch.setattr(bot, "engine_async_provider_processing_timed_out", lambda _job: True)
    monkeypatch.setattr(bot, "poll_music_generation_job", lambda *args, **kwargs: asyncio.sleep(0, result={"ok": False, "status": "PROCESSING"}))
    result = asyncio.run(bot.poll_music_suno_async_job("MUS23H"))
    assert result["job"]["terminal_state"] == "failed_no_charge"
    assert result["job"]["error_category"] == "timeout_provider_processing"


def test_music_artifact_missing_failed_no_charge(monkeypatch):
    async def missing_artifact(*args, **kwargs):
        return {"ok": False, "status": "FINAL_ARTIFACT_NOT_READY", "artifact_candidates_count": 0}

    job = _base_job(status="completed", provider_completed=True)
    store, fake_bot = _patch_delivery(monkeypatch, selector=missing_artifact, job=job)
    result = asyncio.run(bot.deliver_music_result_once(
        CaptureMessage(),
        SimpleNamespace(bot=fake_bot),
        user_id=232001,
        lang="vi",
        product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
        result=_result(),
        audio_bytes=b"",
        job=store["MUS23H"],
        source="auto_tick",
    ))
    assert result["ok"] is False
    assert store["MUS23H"]["terminal_state"] == "failed_no_charge"


def test_music_no_generic_public_error():
    assert bot.music_delivery_should_suppress_public_fail({"music_result_delivered_at": "now"}, {})


def test_music_public_panel_no_debug_terms():
    text = bot.product_progress_status_from_job_text(
        "music_song",
        _base_job(status="processing", progress_percent=65),
        job_id="MUS23H",
        lang="vi",
    )
    lowered = text.lower()
    for token in ("provider", "api", "callback", "handler", "artifact", "scheduler", "runtimeerror", "payload", "debug"):
        assert token not in lowered
    assert "🎙 TOAN AAS đang tạo bài hát" in text


def test_music_refresh_label_update_status():
    labels = [
        button.text
        for row in bot.product_progress_status_keyboard("music_song", "MUS23H", "vi").inline_keyboard
        for button in row
    ]
    assert "🔄 Cập nhật trạng thái" in labels
    assert "📥 Tạo bài hát khác" in labels


def test_music_debug_commands_read_only(monkeypatch):
    called = []
    monkeypatch.setattr(bot, "poll_music_suno_async_job", lambda *args, **kwargs: called.append("poll"))
    monkeypatch.setattr(bot, "send_music_product_audio_result", lambda *args, **kwargs: called.append("send"))
    _patch_store(monkeypatch, _base_job(provider_poll_count=2, provider_last_poll_at="now"))
    bot.PROGRESS_AUTO_REFRESH_JOBS[bot.progress_auto_refresh_key("music_song", "MUS23H")] = {
        "job_id": "MUS23H",
        "product_type": "music_song",
        "registry_saved": True,
        "task_started": True,
        "scheduler_mode": "asyncio_task",
        "last_tick_at": "now",
        "update_count": 2,
    }
    assert "provider_poll_count" in bot.music_job_debug_text("MUS23H")
    assert "registry_saved" in bot.progress_auto_refresh_status_text("MUS23H")
    assert "TOAN AAS progress status" in bot.product_progress_debug_text("MUS23H", "music_song", _base_job())
    assert called == []
