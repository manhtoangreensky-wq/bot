import asyncio
from types import SimpleNamespace

import bot


class CaptureMessage:
    def __init__(self, chat_id=230601):
        self.chat_id = chat_id
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"kind": "text", "text": text, **kwargs})
        return SimpleNamespace(chat_id=self.chat_id, message_id=100 + len(self.outputs))

    async def reply_audio(self, **kwargs):
        self.outputs.append({"kind": "audio", **kwargs})
        return SimpleNamespace(message_id=200 + len(self.outputs), audio=SimpleNamespace(file_id="file-23f"))


class CaptureQuery:
    def __init__(self, user_id=230601, data="music_quick|showroom|music_ai_confirm"):
        self.data = data
        self.message = CaptureMessage(user_id)
        self.edits = []
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, **kwargs):
        self.edits.append(kwargs)
        return SimpleNamespace(chat_id=self.message.chat_id, message_id=501)


class FakeBot:
    def __init__(self):
        self.edits = []
        self.audios = []

    async def edit_message_text(self, **kwargs):
        self.edits.append(kwargs)
        return SimpleNamespace(message_id=kwargs.get("message_id") or 1)

    async def send_audio(self, **kwargs):
        self.audios.append(kwargs)
        return SimpleNamespace(message_id=700 + len(self.audios), audio=SimpleNamespace(file_id="file-23f"))


def _reset():
    bot.PROGRESS_AUTO_REFRESH_JOBS.clear()
    bot.PROGRESS_AUTO_REFRESH_TASKS.clear()
    bot.ENGINE_ASYNC_MEMORY_JOBS.clear()
    bot.MUSIC_PRODUCT_DELIVERY_MEMORY_LOCKS.clear()
    bot.USER_PENDING.clear()


def _panel(job):
    return bot.product_progress_status_from_job_text("music_song", job, job_id=job.get("internal_job_id", "MUS23F"), lang="vi")


def _base_job(**overrides):
    job = {
        "internal_job_id": "MUS23F",
        "product_type": "music_song",
        "status": "pending_submit",
        "progress_percent": 5,
        "provider_style_prompt": "bright pop, female lead vocal",
        "provider_lyrics": "TOAN AAS",
        "lyrics_prepared": True,
        "style_prepared": True,
        "output_bytes": 0,
    }
    job.update(overrides)
    return job


def _result():
    return bot.music_product_result_from_input({
        "music_product_mode": "song",
        "music_product_tier": "music_tier_standard",
        "description": "Bài hát thương hiệu",
        "genre": "pop",
        "mood": "tươi sáng",
        "lyrics": "TOAN AAS luôn đồng hành",
        "vocal_mode": "female",
    })


def _patch_confirm(monkeypatch, *, engine_result=None):
    _reset()
    store = {}
    submit_calls = []

    def fake_save(payload):
        current = dict(payload)
        store[str(current.get("internal_job_id") or "")] = current
        return dict(current)

    async def fake_execute(feature, params, context):
        submit_calls.append((feature, params, context))
        return engine_result or {"ok": True, "provider_result": {"ok": True, "provider": "key4u_suno", "task_id": "provider-task-23f", "status": "PASS_SUBMITTED"}}

    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda job_id: dict(store.get(str(job_id), {})))
    monkeypatch.setattr(bot, "can_user_access_product_engine", lambda *args, **kwargs: {"allowed": True})
    monkeypatch.setattr(bot, "get_user", lambda uid: (999, None, None))
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: False)
    monkeypatch.setattr(bot, "execute_engine", fake_execute)
    monkeypatch.setattr(bot, "progress_auto_refresh_start_task", lambda _ctx, _key: True)
    return SimpleNamespace(store=store, submit_calls=submit_calls)


def test_music_confirm_uses_working_provider_submit_path(monkeypatch):
    state = _patch_confirm(monkeypatch)
    query = CaptureQuery()
    asyncio.run(bot.handle_music_product_confirm(query, SimpleNamespace(), user_id=230601, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result()))
    assert len(state.submit_calls) == 1
    assert state.submit_calls[0][2]["confirm_paid"] is True
    assert state.submit_calls[0][2]["is_paid_job"] is True


def test_music_provider_job_id_saved_after_submit(monkeypatch):
    state = _patch_confirm(monkeypatch)
    query = CaptureQuery()
    asyncio.run(bot.handle_music_product_confirm(query, SimpleNamespace(), user_id=230602, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result()))
    saved = list(state.store.values())[-1]
    assert saved["provider_task_id"] == "provider-task-23f"
    assert saved["provider_job_id"] == "provider-task-23f"
    assert saved["confirm_submit_phase"] == "provider_job_id_saved"


def test_music_provider_poll_uses_saved_job_id(monkeypatch):
    job = _base_job(status="processing", provider_task_id="poll-task-23f", provider_job_id="poll-task-23f")
    saved = {}
    seen = []

    async def fake_poll(state, updated_by=""):
        seen.append(dict(state))
        return {"ok": False, "status": "PROCESSING"}

    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: dict(saved.get("job") or job))
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: saved.setdefault("job", dict(payload)) or dict(payload))
    monkeypatch.setattr(bot, "poll_music_generation_job", fake_poll)
    result = asyncio.run(bot.poll_music_suno_async_job("MUS23F", updated_by=230603, download=True))
    assert seen[0]["music_task_id"] == "poll-task-23f"
    assert result["status"] == "PROCESSING"


def test_music_engine_does_not_create_orphan_mus_job(monkeypatch):
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: dict(payload))
    job = bot.update_music_submit_job_provider_accepted({"internal_job_id": "MUS23F-ORPHAN"}, {"ok": True, "status": "PASS_SUBMITTED"}, updated_by=230604)
    assert job["terminal_state"] == "failed_no_charge"
    assert job["confirm_submit_blocker"] == "provider_job_id_missing_after_submit"


def test_music_received_request_only_ticks_first_step():
    job = {"internal_job_id": "MUS23F-REC", "product_type": "music_song", "status": "pending_submit", "progress_percent": 12}
    text = _panel(job)
    assert "✅ Nhận yêu cầu" in text
    assert "✅ Chuẩn bị lời bài hát" not in text
    assert "✅ Chuẩn bị phong cách" not in text


def test_music_lyrics_step_ticks_only_after_lyrics_prepared():
    no_lyrics = _base_job(provider_lyrics="", lyrics_prepared=False, style_prepared=False)
    has_lyrics = _base_job(provider_lyrics="TOAN AAS", lyrics_prepared=True, provider_style_prompt="", style_prepared=False)
    assert "✅ Chuẩn bị lời bài hát" not in _panel(no_lyrics)
    assert "✅ Chuẩn bị lời bài hát" in _panel(has_lyrics)
    assert "✅ Chuẩn bị phong cách" not in _panel(has_lyrics)


def test_music_style_step_ticks_only_after_style_prepared():
    no_style = _base_job(provider_style_prompt="", style_prepared=False)
    has_style = _base_job(provider_style_prompt="bright pop", style_prepared=True)
    assert "✅ Chuẩn bị phong cách" not in _panel(no_style)
    assert "✅ Chuẩn bị phong cách" in _panel(has_style)


def test_music_progress_does_not_tick_by_percent_only():
    job = {
        "internal_job_id": "MUS23F-PERCENT",
        "product_type": "music_song",
        "status": "pending_submit",
        "progress_percent": 65,
    }
    state = bot.product_progress_state_from_job("music_song", job)
    text = _panel(job)
    assert state["percent"] == 5
    assert "✅ Tạo bài hát" not in text
    assert "✅ Kiểm tra file nhạc" not in text
    assert "✅ Gửi kết quả" not in text


def test_music_progress_does_not_fake_12_percent_steps():
    job = {"internal_job_id": "MUS23F-12", "product_type": "music_song", "status": "submitting", "provider_submit_called": True, "progress_percent": 12}
    text = _panel(job)
    state = bot.product_progress_state_from_job("music_song", job)
    assert state["percent"] == 12
    assert "✅ Chuẩn bị lời bài hát" not in text
    assert "✅ Chuẩn bị phong cách" not in text


def test_music_create_song_step_not_green_before_provider_completed():
    job = _base_job(
        status="processing",
        progress_percent=65,
        provider_task_id="task-23f",
        provider_job_id="task-23f",
        provider_completed=False,
    )
    text = _panel(job)
    assert "⏳ Tạo bài hát" in text
    assert "✅ Tạo bài hát" not in text


def test_music_create_song_step_green_after_provider_completed():
    job = _base_job(
        status="downloading",
        progress_percent=85,
        provider_task_id="task-23f",
        provider_completed=True,
        output_url="https://example.test/song.mp3",
    )
    text = _panel(job)
    assert "✅ Tạo bài hát" in text
    assert "✅ Kiểm tra file nhạc" not in text


def test_music_check_file_step_only_after_artifact_ready():
    no_artifact = _base_job(status="processing", progress_percent=65, provider_task_id="task-23f")
    validated = _base_job(status="completed", progress_percent=85, provider_task_id="task-23f", output_bytes=2048, artifact_duration_seconds=60)
    assert "✅ Kiểm tra file nhạc" not in _panel(no_artifact)
    assert "✅ Kiểm tra file nhạc" in _panel(validated)


def test_music_check_file_step_only_after_validated_artifact():
    artifact_only = _base_job(
        status="completed",
        progress_percent=85,
        provider_task_id="task-23f",
        output_bytes=2048,
        artifact_duration_seconds=0,
    )
    validated = _base_job(
        status="completed",
        progress_percent=85,
        provider_task_id="task-23f",
        output_bytes=2048,
        artifact_duration_seconds=60,
    )
    assert "✅ Kiểm tra file nhạc" not in _panel(artifact_only)
    assert "✅ Kiểm tra file nhạc" in _panel(validated)


def test_music_send_result_step_only_after_delivery():
    test_music_send_result_step_only_after_telegram_delivery()


def test_music_send_result_step_only_after_telegram_delivery():
    ready = _base_job(
        status="completed",
        progress_percent=85,
        provider_task_id="task-23f",
        output_bytes=2048,
        artifact_duration_seconds=60,
    )
    delivered = _base_job(
        status="delivered",
        progress_percent=5,
        provider_task_id="task-23f",
        output_bytes=2048,
        artifact_duration_seconds=60,
        sent_full_at="now",
        music_delivery_message_id="901",
        terminal_state="delivered",
    )
    assert "✅ Gửi kết quả" not in _panel(ready)
    assert "✅ Gửi kết quả" in _panel(delivered)


def test_music_auto_tick_uses_real_state_not_fake_increment():
    snapshot = bot.progress_auto_refresh_snapshot(
        "music_song",
        "MUS23F-AUTO1",
        job={"internal_job_id": "MUS23F-AUTO1", "product_type": "music_song", "status": "pending_submit", "progress_percent": 65},
    )
    assert snapshot["percent"] == 5
    assert snapshot["completed_steps"] == ["received_request"]


def test_music_auto_tick_polls_provider_and_updates_stage(monkeypatch):
    job = _base_job(status="processing", progress_percent=65, provider_task_id="task-23f")

    async def fake_poll(_job_id, *, updated_by="", download=True):
        return {"ok": True, "status": "COMPLETED", "job": {**job, "status": "completed", "output_bytes": 2048, "artifact_duration_seconds": 60}, "audio_bytes": b"mp3"}

    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: dict(job))
    monkeypatch.setattr(bot, "poll_music_suno_async_job", fake_poll)
    refreshed = asyncio.run(bot.music_progress_refresh_job_status("MUS23F-AUTO2", user_id=230605))
    state = bot.product_progress_state_from_job("music_song", refreshed)
    assert state["current_stage"] == "delivering"
    assert "validating_audio" in state["completed_steps"]


def test_music_auto_tick_edits_panel_like_subdub(monkeypatch):
    fake_bot = FakeBot()
    record = bot.progress_auto_refresh_register(
        product_type="music_song",
        job_id="MUS23F-AUTO3",
        chat_id=230606,
        message_id=10,
        user_id=230606,
        initial_snapshot={"stage": "received_request", "percent": 5, "terminal_state": "", "text": "old", "render_hash": "old"},
        start_task=False,
    )
    record["auto_delivery_enabled"] = False
    bot.PROGRESS_AUTO_REFRESH_JOBS[record["key"]] = record
    async def fake_refresh(*args, **kwargs):
        return _base_job(status="processing", progress_percent=65, provider_task_id="task-23f")

    monkeypatch.setattr(bot, "music_progress_refresh_job_status", fake_refresh)
    result = asyncio.run(bot.progress_auto_refresh_tick(SimpleNamespace(bot=fake_bot), record["key"]))
    assert result["status"] == "updated"
    assert fake_bot.edits


def test_music_auto_tick_does_not_submit_provider_again(monkeypatch):
    called = []
    fake_bot = FakeBot()
    record = bot.progress_auto_refresh_register(
        product_type="music_song",
        job_id="MUS23F-AUTO4",
        chat_id=230607,
        message_id=10,
        user_id=230607,
        initial_snapshot={"stage": "received_request", "percent": 5, "terminal_state": "", "text": "old", "render_hash": "old"},
        start_task=False,
    )
    record["auto_delivery_enabled"] = False
    bot.PROGRESS_AUTO_REFRESH_JOBS[record["key"]] = record
    monkeypatch.setattr(bot, "execute_engine", lambda *args, **kwargs: called.append(True))
    async def fake_refresh(*args, **kwargs):
        return _base_job(status="processing", progress_percent=65, provider_task_id="task-23f")

    monkeypatch.setattr(bot, "music_progress_refresh_job_status", fake_refresh)
    asyncio.run(bot.progress_auto_refresh_tick(SimpleNamespace(bot=fake_bot), record["key"]))
    assert called == []


def test_provider_submit_fail_clean_no_charge(monkeypatch):
    _patch_confirm(monkeypatch, engine_result={"ok": False, "status": "FAILED", "detail": "submit failed"})
    query = CaptureQuery()
    asyncio.run(bot.handle_music_product_confirm(query, SimpleNamespace(), user_id=230608, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result()))
    assert "chưa trừ Xu" in query.message.outputs[-1]["text"]


def test_provider_job_id_missing_not_stuck_fake_progress(monkeypatch):
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: dict(payload))
    job = bot.update_music_submit_job_provider_accepted(_base_job(internal_job_id="MUS23F-MISSING"), {"ok": True}, updated_by=230609)
    state = bot.product_progress_state_from_job("music_song", job)
    assert job["terminal_state"] == "failed_no_charge"
    assert state["percent"] >= 5
    assert "generating_song" not in state.get("completed_steps", [])


def test_provider_processing_timeout_needs_admin_review_or_clean_fail(monkeypatch):
    job = _base_job(status="processing", provider_task_id="task-23f")
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: dict(job))
    monkeypatch.setattr(bot, "engine_async_provider_processing_timed_out", lambda _job: True)
    async def fake_poll(*args, **kwargs):
        return {"ok": False, "status": "PROCESSING"}

    monkeypatch.setattr(bot, "poll_music_generation_job", fake_poll)
    saved = {}
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: saved.setdefault("job", dict(payload)) or dict(payload))
    result = asyncio.run(bot.poll_music_suno_async_job("MUS23F-TIMEOUT"))
    assert result["job"]["terminal_state"] == "failed_no_charge"
    assert result["job"]["error_category"] == "timeout_provider_processing"


def test_artifact_missing_after_completed_no_success():
    snapshot = bot.progress_auto_refresh_snapshot("music_song", "MUS23F-NOART", job={"internal_job_id": "MUS23F-NOART", "status": "completed", "progress_percent": 100, "output_bytes": 0})
    assert snapshot["terminal_state"] == "failed_no_charge"
    assert "✅ Gửi kết quả" not in snapshot["text"]


def test_music_deliver_once(monkeypatch):
    _reset()
    fake_message = CaptureMessage()
    fake_bot = FakeBot()
    job = _base_job(internal_job_id="MUS23F-DELIVER", status="completed", provider_task_id="task-23f", output_bytes=2048, artifact_duration_seconds=60)
    result = _result()
    async def fake_select(*args, **kwargs):
        return {"ok": True, "audio_bytes": b"real-mp3-bytes", "selected_artifact_duration": 60, "artifact_candidates_count": 1}

    monkeypatch.setattr(bot, "select_music_delivery_artifact", fake_select)
    monkeypatch.setattr(bot, "music_product_charge_after_delivery", lambda *args, **kwargs: {"ok": True, "charged_xu": 0})
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **kwargs: {"vault_id": "vault-23f", "storage_ref": ""})
    monkeypatch.setattr(bot, "get_music_vault_entry", lambda _vault_id: {})
    monkeypatch.setattr(bot, "mark_music_vault_status", lambda *args, **kwargs: None)
    saved = {}

    def fake_save(payload):
        current = dict(payload)
        saved[str(current.get("internal_job_id") or "job")] = current
        return dict(current)

    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: dict(saved.get("MUS23F-DELIVER") or job))
    first = asyncio.run(bot.deliver_music_result_once(fake_message, SimpleNamespace(bot=fake_bot), user_id=230610, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=result, audio_bytes=b"real-mp3-bytes", job=job, source="auto_tick"))
    second = asyncio.run(bot.deliver_music_result_once(fake_message, SimpleNamespace(bot=fake_bot), user_id=230610, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=first["result"], audio_bytes=b"real-mp3-bytes", job=first["job"], source="manual_update"))
    assert first["ok"] is True
    assert second["duplicate"] is True
    assert len(fake_bot.audios) == 1


def test_late_error_suppressed_after_delivered():
    assert bot.music_delivery_should_suppress_public_fail({"music_result_delivered_at": "now"}, {})


def test_manual_update_after_delivered_no_resend(monkeypatch):
    sent = []
    monkeypatch.setattr(bot, "send_music_product_audio_result", lambda *args, **kwargs: sent.append(True))
    snapshot = bot.progress_auto_refresh_snapshot("music_song", "MUS23F-DONE", job={"internal_job_id": "MUS23F-DONE", "status": "delivered", "sent_full_at": "now", "output_file_id": "file"})
    assert snapshot["terminal_state"] == "delivered"
    assert sent == []


def test_debug_read_only(monkeypatch):
    called = []
    monkeypatch.setattr(bot, "poll_music_suno_async_job", lambda *args, **kwargs: called.append("poll"))
    monkeypatch.setattr(bot, "send_music_product_audio_result", lambda *args, **kwargs: called.append("send"))
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: _base_job(status="processing", provider_task_id="task-23f"))
    text = bot.music_job_debug_text("MUS23F-DEBUG")
    assert "Music job debug" in text
    assert called == []


def test_music_pending_submit_job_persists_real_lifecycle_fields(monkeypatch):
    saved = {}

    def fake_save(payload):
        saved.update(payload)
        return dict(payload)

    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)
    result = bot.music_product_result_from_input({
        "music_product_mode": "song",
        "music_product_tier": "music_tier_standard",
        "description": "Bài hát thương hiệu",
        "genre": "pop",
        "mood": "tươi sáng",
        "lyrics": "TOAN AAS luôn đồng hành",
        "vocal_mode": "female",
    })
    job = bot.create_music_pending_submit_job(user_id=230601, chat_id=230601, result=result)
    assert job["lyrics_prepared"] is True
    assert job["style_prepared"] is True
    assert job["provider_style_prompt"]
    assert job["provider_lyrics"]


def test_music_auto_refresh_snapshot_uses_real_stage_not_stale_stage():
    job = _base_job(
        status="completed",
        current_stage="received_request",
        progress_percent=5,
        provider_task_id="task-23f",
        output_bytes=2048,
        artifact_duration_seconds=60,
    )
    snapshot = bot.progress_auto_refresh_snapshot("music_song", "MUS23F-STALE", job=job)
    assert snapshot["stage"] == "delivering"
    assert "validating_audio" in snapshot["completed_steps"]


def test_music_debug_shows_real_lifecycle_flags(monkeypatch):
    job = _base_job(
        status="processing",
        progress_percent=65,
        provider_task_id="task-23f",
        provider_submit_called=True,
    )
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: dict(job))
    bot.PROGRESS_AUTO_REFRESH_JOBS[bot.progress_auto_refresh_key("music_song", "MUS23F")] = {
        "scheduler_mode": "application_task",
        "task_started": True,
        "last_tick_at": "now",
    }
    text = bot.music_job_debug_text("MUS23F")
    assert "completed_steps" in text
    assert "provider_submit_called" in text
    assert "style_prepared" in text
    assert "scheduler_mode" in text
