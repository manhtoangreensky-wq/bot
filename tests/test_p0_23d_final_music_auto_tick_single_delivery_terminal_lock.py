import asyncio
from types import SimpleNamespace

import bot


class FakeBot:
    def __init__(self):
        self.audio = []
        self.sent = []
        self.edits = []
        self._release = None

    async def send_audio(self, **kwargs):
        self.audio.append(kwargs)
        if self._release:
            await self._release.wait()
        return SimpleNamespace(message_id=8000 + len(self.audio), audio=SimpleNamespace(file_id=f"file-{len(self.audio)}"))

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(message_id=7000 + len(self.sent))

    async def edit_message_text(self, **kwargs):
        self.edits.append(kwargs)
        return SimpleNamespace(message_id=kwargs.get("message_id"))


class CaptureMessage:
    def __init__(self, chat_id=230501):
        self.chat_id = chat_id
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"kind": "text", "text": text, **kwargs})
        return SimpleNamespace(chat_id=self.chat_id, message_id=len(self.outputs))

    async def reply_audio(self, audio=None, filename="", caption="", **kwargs):
        self.outputs.append({"kind": "audio", "audio": audio, "filename": filename, "caption": caption, **kwargs})
        return SimpleNamespace(message_id=len(self.outputs), audio=SimpleNamespace(file_id=f"reply-audio-{len(self.outputs)}"))


class CaptureQuery:
    def __init__(self, data, user_id=230501):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = CaptureMessage(user_id)
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append({"text": text, **kwargs})
        return SimpleNamespace(message_id=1)


def _ctx(fake_bot=None):
    return SimpleNamespace(bot=fake_bot or FakeBot())


def _reset():
    bot.PROGRESS_AUTO_REFRESH_JOBS.clear()
    bot.PROGRESS_AUTO_REFRESH_TASKS.clear()
    bot.MUSIC_PRODUCT_DELIVERY_MEMORY_LOCKS.clear()
    bot.USER_PENDING.clear()


def _result(mode="song"):
    return {
        "music_product_flow": "p0_20b1_suggestions",
        "music_product_mode": mode,
        "music_product_tier": "music_tier_premium",
        "provider_style_prompt": "bright pop",
        "provider_lyrics": "TOAN AAS",
        "song_vocal": "female",
    }


def _job(job_id="MUS-D23D", product_type="music_song"):
    return {
        "internal_job_id": job_id,
        "feature": "music_suno",
        "product_type": product_type,
        "music_product_type": product_type,
        "music_product_mode": "song" if product_type == "music_song" else "background",
        "music_product_tier": "music_tier_premium",
        "song_vocal": "female",
        "user_id": "230501",
        "chat_id": "230501",
        "provider": "key4u_suno",
        "provider_task_id": "provider-task-d23d",
        "provider_job_id": "provider-task-d23d",
        "status": "completed",
        "progress_percent": 85,
        "output_bytes": 4096,
        "artifact_duration_seconds": 96,
        "music_result_duration_seconds": 96,
        "output_sha256": "sha-d23d",
    }


def _patch_ready(monkeypatch, job_id="MUS-D23D", audio=b"real-mp3-bytes", product_type="music_song"):
    state = {"job": _job(job_id, product_type), "saves": [], "charges": []}

    async def fake_poll(_job_id, **_kwargs):
        job = dict(state["job"])
        return {"ok": True, "status": "COMPLETED", "job": job, "audio_bytes": audio}

    async def fake_duration(*_args, **_kwargs):
        return 96

    def fake_save(payload):
        state["job"] = dict(payload)
        state["saves"].append(dict(payload))
        return dict(payload)

    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: dict(state["job"]) if _job_id == job_id else {})
    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)
    monkeypatch.setattr(bot, "poll_music_suno_async_job", fake_poll)
    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", fake_duration)
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **_kwargs: {"vault_id": "MV-D23D", "storage_ref": ""})
    monkeypatch.setattr(bot, "get_music_vault_entry", lambda _vault_id: {"vault_id": _vault_id, "storage_ref": ""})
    monkeypatch.setattr(bot, "mark_music_vault_status", lambda *args, **kwargs: {"vault_id": args[0] if args else "MV-D23D"})
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    return state


def test_music_panel_schedules_auto_tick_after_send(monkeypatch):
    _reset()
    calls = []
    monkeypatch.setattr(bot, "progress_auto_refresh_start_task", lambda _context, key: calls.append(key) or True)
    bot.progress_auto_refresh_register(product_type="music_song", job_id="MUS-SCHEDULE", chat_id=1, message_id=2, context=_ctx(), start_task=True)
    assert calls == ["music_song:MUS-SCHEDULE"]


def test_music_auto_tick_runs_without_manual_click(monkeypatch):
    _reset()
    _patch_ready(monkeypatch, "MUS-AUTO-RUN")
    record = bot.progress_auto_refresh_register(product_type="music_song", job_id="MUS-AUTO-RUN", chat_id=230501, message_id=9, user_id=230501, start_task=False)
    fake = FakeBot()
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    assert len(fake.audio) == 1


def test_music_auto_tick_edits_panel_from_5_percent(monkeypatch):
    _reset()
    _patch_ready(monkeypatch, "MUS-PANEL5")
    record = bot.progress_auto_refresh_register(
        product_type="music_song",
        job_id="MUS-PANEL5",
        chat_id=230501,
        message_id=9,
        user_id=230501,
        initial_snapshot={"stage": "received_request", "percent": 5, "terminal_state": "", "text": "Tiến độ: 5%", "render_hash": "old"},
        start_task=False,
    )
    fake = FakeBot()
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    assert fake.edits
    assert "Tiến độ: 5%" not in fake.edits[-1]["text"]


def test_music_auto_tick_sets_panel_100_after_delivery(monkeypatch):
    _reset()
    _patch_ready(monkeypatch, "MUS-PANEL100")
    record = bot.progress_auto_refresh_register(product_type="music_song", job_id="MUS-PANEL100", chat_id=230501, message_id=9, user_id=230501, start_task=False)
    fake = FakeBot()
    result = asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    assert result["snapshot"]["percent"] == 100
    assert "Đã gửi file nhạc" in fake.edits[-1]["text"]


def test_progress_auto_refresh_status_shows_task_started(monkeypatch):
    _reset()
    monkeypatch.setattr(bot, "progress_auto_refresh_start_task", lambda _context, key: bot.PROGRESS_AUTO_REFRESH_JOBS[key].update({"task_started": True, "task_alive": True, "scheduler_mode": "test"}) or True)
    bot.progress_auto_refresh_register(product_type="music_song", job_id="MUS-STATUS", chat_id=1, message_id=2, context=_ctx(), start_task=True)
    text = bot.progress_auto_refresh_status_text("MUS-STATUS")
    assert "task_started" in text
    assert "scheduler_mode" in text
    assert "registry_saved" in text


def test_music_auto_tick_sends_audio_once(monkeypatch):
    _reset()
    _patch_ready(monkeypatch, "MUS-ONCE")
    record = bot.progress_auto_refresh_register(product_type="music_song", job_id="MUS-ONCE", chat_id=230501, message_id=9, user_id=230501, start_task=False)
    fake = FakeBot()
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    assert len(fake.audio) == 1


def test_music_manual_update_after_auto_tick_does_not_send_second_audio(monkeypatch):
    _reset()
    _patch_ready(monkeypatch, "MUS-MANUAL")
    record = bot.progress_auto_refresh_register(product_type="music_song", job_id="MUS-MANUAL", chat_id=230501, message_id=9, user_id=230501, start_task=False)
    fake = FakeBot()
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    query = CaptureQuery("progress|status|music_song|MUS-MANUAL")
    asyncio.run(bot.handle_product_progress_callback(SimpleNamespace(callback_query=query), _ctx(fake)))
    assert len(fake.audio) == 1
    assert len(fake.sent) == 1


def test_music_worker_after_auto_tick_does_not_send_second_audio(monkeypatch):
    _reset()
    state = _patch_ready(monkeypatch, "MUS-WORKER")
    fake = FakeBot()
    first = asyncio.run(bot.deliver_music_result_once(CaptureMessage(), _ctx(fake), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result(), audio_bytes=b"real-mp3-bytes", job=state["job"], send_success_message=True, source="auto_tick"))
    second = asyncio.run(bot.deliver_music_result_once(CaptureMessage(), _ctx(fake), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=first["result"], audio_bytes=b"real-mp3-bytes", job=first["job"], send_success_message=True, source="worker"))
    assert second["duplicate"] is True
    assert len(fake.audio) == 1


def test_music_provider_poll_after_delivery_noops(monkeypatch):
    _reset()
    state = _patch_ready(monkeypatch, "MUS-PROVIDER")
    fake = FakeBot()
    first = asyncio.run(bot.deliver_music_result_once(CaptureMessage(), _ctx(fake), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result(), audio_bytes=b"real-mp3-bytes", job=state["job"], send_success_message=True, source="auto_tick"))
    second = asyncio.run(bot.deliver_music_result_once(CaptureMessage(), _ctx(fake), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=first["result"], audio_bytes=b"real-mp3-bytes", job=first["job"], source="provider_poll"))
    assert second["status"] == "ALREADY_DELIVERED"
    assert len(fake.audio) == 1


def test_music_legacy_check_result_callback_noops_after_delivered(monkeypatch):
    _reset()
    state = _patch_ready(monkeypatch, "MUS-LEGACY")
    state["job"].update({"status": "delivered", "terminal_state": "delivered", "music_delivery_message_id": "8001", "music_success_message_id": "7001"})
    bot.save_music_guided_result(230501, {"music_task_id": "provider-task-d23d", "music_internal_job_id": "MUS-LEGACY", "music_result_delivered_at": "now", "music_success_message_id": "7001"})
    fake = FakeBot()
    query = CaptureQuery("music_quick|showroom|music_ai_status")
    asyncio.run(bot.handle_music_quick_callback(SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=230501)), _ctx(fake)))
    assert len(fake.audio) == 0
    assert not any("Đã tạo nhạc thành công" in item.get("text", "") for item in query.message.outputs)


def test_music_delivery_lock_blocks_concurrent_delivery(monkeypatch):
    _reset()
    state = _patch_ready(monkeypatch, "MUS-LOCK")
    fake = FakeBot()

    async def run_pair():
        fake._release = asyncio.Event()
        task1 = asyncio.create_task(bot.deliver_music_result_once(CaptureMessage(), _ctx(fake), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result(), audio_bytes=b"real-mp3-bytes", job=state["job"], send_success_message=True, source="auto_tick"))
        await asyncio.sleep(0)
        task2 = asyncio.create_task(bot.deliver_music_result_once(CaptureMessage(), _ctx(fake), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result(), audio_bytes=b"real-mp3-bytes", job=state["job"], send_success_message=True, source="manual_update"))
        await asyncio.sleep(0)
        fake._release.set()
        return await asyncio.gather(task1, task2)

    results = asyncio.run(run_pair())
    assert len(fake.audio) == 1
    assert any(item.get("duplicate") for item in results)


def test_music_selects_final_artifact_not_preview(monkeypatch):
    _reset()
    _patch_ready(monkeypatch, "MUS-FINAL")
    result = _result()
    result["artifact_candidates"] = [
        {"role": "preview", "audio_bytes": b"preview-bytes", "duration_seconds": 12},
        {"role": "final_master", "audio_bytes": b"final-bytes", "duration_seconds": 96, "artifact_id": "final-1"},
    ]
    selected = asyncio.run(bot.select_music_delivery_artifact(result, {}, b""))
    assert selected["selected_artifact_id"] == "final-1"
    assert selected["audio_bytes"] == b"final-bytes"


def test_music_duplicate_artifact_hash_not_sent_twice(monkeypatch):
    _reset()
    state = _patch_ready(monkeypatch, "MUS-HASH", audio=b"same-final")
    fake = FakeBot()
    first = asyncio.run(bot.deliver_music_result_once(CaptureMessage(), _ctx(fake), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result(), audio_bytes=b"same-final", job=state["job"], send_success_message=True, source="auto_tick"))
    second = asyncio.run(bot.deliver_music_result_once(CaptureMessage(), _ctx(fake), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=first["result"], audio_bytes=b"same-final", job=first["job"], send_success_message=True, source="manual_update"))
    assert second["duplicate"] is True
    assert len(fake.audio) == 1


def test_music_duplicate_artifact_url_not_sent_twice(monkeypatch):
    _reset()
    state = _patch_ready(monkeypatch, "MUS-URL")
    state["job"]["music_artifact_url"] = "https://cdn.example/final.mp3"
    fake = FakeBot()
    first = asyncio.run(bot.deliver_music_result_once(CaptureMessage(), _ctx(fake), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result={**_result(), "music_output_url": "https://cdn.example/final.mp3?token=1"}, audio_bytes=b"real-mp3-bytes", job=state["job"], send_success_message=True, source="auto_tick"))
    second = asyncio.run(bot.deliver_music_result_once(CaptureMessage(), _ctx(fake), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=first["result"], audio_bytes=b"real-mp3-bytes", job=first["job"], send_success_message=True, source="manual_update"))
    assert second["duplicate"] is True
    assert len(fake.audio) == 1


def test_music_multiple_candidates_sends_only_one_best_artifact(monkeypatch):
    _reset()
    _patch_ready(monkeypatch, "MUS-BEST")
    fake = FakeBot()
    result = {**_result(), "artifact_candidates": [{"role": "preview", "audio_bytes": b"preview", "duration_seconds": 12}, {"role": "final_master", "audio_bytes": b"final", "duration_seconds": 96}]}
    asyncio.run(bot.deliver_music_result_once(CaptureMessage(), _ctx(fake), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=result, audio_bytes=b"", job=_job("MUS-BEST"), send_success_message=True, source="auto_tick"))
    assert len(fake.audio) == 1


def test_music_delivered_blocks_late_fail_message():
    assert bot.music_delivery_should_suppress_public_fail({"music_result_delivered_at": "now"}, {})


def test_music_delivery_success_does_not_emit_generic_error(monkeypatch):
    _reset()
    monkeypatch.setattr(bot, "completed_music_job_for_callback_error", lambda _update: {"internal_job_id": "MUS-ERR", "terminal_state": "delivered", "music_delivery_message_id": "8001"})

    class NoPublicBot:
        async def send_message(self, **_kwargs):
            raise AssertionError("generic public error must be suppressed after music delivered")

    context = SimpleNamespace(error=RuntimeError("late callback error"), bot=NoPublicBot(), chat_data={})
    asyncio.run(bot.on_telegram_error(SimpleNamespace(), context))


def test_music_failed_terminal_blocks_late_success(monkeypatch):
    _reset()
    state = _patch_ready(monkeypatch, "MUS-FAILED")
    state["job"].update({"status": "failed", "terminal_state": "failed_no_charge"})
    fake = FakeBot()
    result = asyncio.run(bot.deliver_music_result_once(CaptureMessage(), _ctx(fake), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result(), audio_bytes=b"real-mp3-bytes", job=state["job"], send_success_message=True, source="provider_poll"))
    assert result["status"] == "TERMINAL_FAILED"
    assert len(fake.audio) == 0


def test_music_terminal_state_locked_after_delivery(monkeypatch):
    _reset()
    state = _patch_ready(monkeypatch, "MUS-TERM")
    fake = FakeBot()
    delivered = asyncio.run(bot.deliver_music_result_once(CaptureMessage(), _ctx(fake), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result(), audio_bytes=b"real-mp3-bytes", job=state["job"], send_success_message=True, source="auto_tick"))
    assert delivered["job"]["terminal_state"] == "delivered"
    assert delivered["job"]["music_terminal_locked_at"]


def test_music_panel_not_left_at_5_after_delivered(monkeypatch):
    _reset()
    _patch_ready(monkeypatch, "MUS-NOT5")
    record = bot.progress_auto_refresh_register(product_type="music_song", job_id="MUS-NOT5", chat_id=230501, message_id=9, user_id=230501, initial_snapshot={"stage": "received_request", "percent": 5, "terminal_state": "", "text": "Tiến độ: 5%", "render_hash": "old"}, start_task=False)
    result = asyncio.run(bot.progress_auto_refresh_tick(_ctx(FakeBot()), record["key"]))
    assert result["snapshot"]["percent"] == 100


def test_music_success_message_sent_once(monkeypatch):
    _reset()
    _patch_ready(monkeypatch, "MUS-SUCCESS1")
    fake = FakeBot()
    first = asyncio.run(bot.deliver_music_result_once(CaptureMessage(), _ctx(fake), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result(), audio_bytes=b"real-mp3-bytes", job=_job("MUS-SUCCESS1"), send_success_message=True, source="auto_tick"))
    asyncio.run(bot.deliver_music_result_once(CaptureMessage(), _ctx(fake), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=first["result"], audio_bytes=b"real-mp3-bytes", job=first["job"], send_success_message=True, source="manual_update"))
    assert len(fake.sent) == 1


def test_music_plain_success_not_sent_if_detailed_success_sent(monkeypatch):
    _reset()
    _patch_ready(monkeypatch, "MUS-NOPLAIN")
    fake = FakeBot()
    asyncio.run(bot.deliver_music_result_once(CaptureMessage(), _ctx(fake), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result(), audio_bytes=b"real-mp3-bytes", job=_job("MUS-NOPLAIN"), send_success_message=True, source="auto_tick"))
    assert len([item for item in fake.sent if "Đã tạo nhạc thành công" in item.get("text", "")]) == 1


def test_music_file_caption_not_counted_as_second_success(monkeypatch):
    _reset()
    _patch_ready(monkeypatch, "MUS-CAPTION")
    fake = FakeBot()
    asyncio.run(bot.deliver_music_result_once(CaptureMessage(), _ctx(fake), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result(), audio_bytes=b"real-mp3-bytes", job=_job("MUS-CAPTION"), send_success_message=True, source="auto_tick"))
    assert fake.audio[0]["caption"] == "🎵 File nhạc TOAN AAS"
    assert not fake.audio[0]["caption"].startswith("✅")


def test_manual_update_is_fallback_not_primary(monkeypatch):
    _reset()
    _patch_ready(monkeypatch, "MUS-FALLBACK")
    record = bot.progress_auto_refresh_register(product_type="music_song", job_id="MUS-FALLBACK", chat_id=230501, message_id=9, user_id=230501, start_task=False)
    fake = FakeBot()
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    assert fake.audio


def test_manual_update_after_delivered_no_duplicate(monkeypatch):
    test_music_manual_update_after_auto_tick_does_not_send_second_audio(monkeypatch)


def test_music_job_debug_read_only(monkeypatch):
    _reset()
    state = _patch_ready(monkeypatch, "MUS-DEBUG")
    before = dict(state["job"])
    text = bot.music_job_debug_text("MUS-DEBUG")
    assert "delivery_source_first" in text
    assert state["job"] == before


def test_music_debug_shows_delivery_source_and_duplicate_blocks(monkeypatch):
    _reset()
    state = _patch_ready(monkeypatch, "MUS-DEBUG2")
    fake = FakeBot()
    first = asyncio.run(bot.deliver_music_result_once(CaptureMessage(), _ctx(fake), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result(), audio_bytes=b"real-mp3-bytes", job=state["job"], send_success_message=True, source="auto_tick"))
    asyncio.run(bot.deliver_music_result_once(CaptureMessage(), _ctx(fake), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=first["result"], audio_bytes=b"real-mp3-bytes", job=first["job"], send_success_message=True, source="manual_update"))
    text = bot.music_job_debug_text("MUS-DEBUG2")
    assert "auto_tick" in text
    assert "manual_update" in text
