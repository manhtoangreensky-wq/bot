import asyncio
from types import SimpleNamespace

import bot


AUDIO_BYTES = b"ID3-toan-aas-h6-real-music" * 300
USER_ID = 230606
JOB_ID = "MUS457A8FBB"


class FakeBot:
    def __init__(self, fail_audio=False):
        self.fail_audio = fail_audio
        self.audio = []
        self.messages = []
        self.edits = []

    async def send_audio(self, **kwargs):
        if self.fail_audio:
            raise RuntimeError("telegram unavailable")
        self.audio.append(kwargs)
        return SimpleNamespace(message_id=9000 + len(self.audio), audio=SimpleNamespace(file_id=f"audio-{len(self.audio)}"))

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)
        return SimpleNamespace(message_id=8000 + len(self.messages))

    async def edit_message_text(self, **kwargs):
        self.edits.append(kwargs)
        return SimpleNamespace(message_id=kwargs.get("message_id"))


class CaptureMessage:
    def __init__(self, chat_id=USER_ID):
        self.chat_id = chat_id
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"kind": "text", "text": text, **kwargs})
        return SimpleNamespace(chat_id=self.chat_id, message_id=100 + len(self.outputs))

    async def reply_audio(self, audio=None, filename="", caption="", **kwargs):
        self.outputs.append({"kind": "audio", "audio": audio, "filename": filename, "caption": caption, **kwargs})
        return SimpleNamespace(message_id=200 + len(self.outputs), audio=SimpleNamespace(file_id=f"reply-{len(self.outputs)}"))


class CaptureQuery:
    def __init__(self, data="music_quick|showroom|music_ai_confirm", user_id=USER_ID):
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


def _ctx(fake_bot=None, args=None):
    return SimpleNamespace(bot=fake_bot or FakeBot(), args=list(args or []))


def _reset():
    bot.PROGRESS_AUTO_REFRESH_JOBS.clear()
    bot.PROGRESS_AUTO_REFRESH_TASKS.clear()
    bot.ENGINE_ASYNC_MEMORY_JOBS.clear()
    bot.MUSIC_PRODUCT_DELIVERY_MEMORY_LOCKS.clear()
    bot.USER_PENDING.clear()


def _result():
    return bot.music_product_result_from_input({
        "music_product_mode": "song",
        "music_product_tier": "music_tier_standard",
        "description": "TOAN AAS product song",
        "genre": "pop",
        "mood": "bright",
        "song_vocal": "female",
    })


def _job(**overrides):
    data = {
        "internal_job_id": JOB_ID,
        "feature": "music_suno",
        "product_type": "music_song",
        "music_product_type": "music_song",
        "music_product_mode": "song",
        "music_product_tier": "music_tier_standard",
        "user_id": str(USER_ID),
        "chat_id": str(USER_ID),
        "provider": "key4u_suno",
        "provider_task_id": "provider-h6-task",
        "provider_job_id": "provider-h6-task",
        "provider_submit_called": True,
        "status": "submitted",
        "progress_percent": 15,
        "pending_charge_xu": 0,
        "charged_xu": 0,
    }
    data.update(overrides)
    return data


def _install_store(monkeypatch, initial_job=None):
    _reset()
    store = {}
    saves = []
    if initial_job:
        store[str(initial_job["internal_job_id"])] = dict(initial_job)

    def fake_save(payload):
        current = dict(payload)
        current.setdefault("internal_job_id", JOB_ID)
        store[str(current.get("internal_job_id") or "")] = current
        saves.append(current)
        return dict(current)

    def fake_get(job_id):
        return dict(store.get(str(job_id or ""), {}))

    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)
    monkeypatch.setattr(bot, "get_engine_async_job", fake_get)
    return SimpleNamespace(store=store, saves=saves)


def _patch_materializer(monkeypatch, tmp_path, *, payload=AUDIO_BYTES, detail="http=200; bytes=7800; content_type=audio/mpeg", status=200, duration=188):
    async def fake_download(_url, timeout_seconds=60.0):
        return payload, detail, status

    async def fake_duration(_audio, fallback=0):
        return duration

    def fake_upsert(audio_bytes, result=None, job=None, status="generated_unused", updated_by=""):
        vault_id = "MV-H6"
        storage = tmp_path / f"{vault_id}.mp3"
        storage.write_bytes(bytes(audio_bytes or b""))
        return {"vault_id": vault_id, "storage_ref": str(storage)}

    monkeypatch.setattr(bot, "_download_music_audio_url_bytes", fake_download)
    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", fake_duration)
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", fake_upsert)
    monkeypatch.setattr(bot, "get_music_vault_entry", lambda _vault_id: {"vault_id": _vault_id, "storage_ref": str(tmp_path / f"{_vault_id}.mp3")})
    monkeypatch.setattr(bot, "mark_music_vault_status", lambda *args, **kwargs: {"vault_id": args[0] if args else "MV-H6"})
    monkeypatch.setattr(bot, "music_product_charge_after_delivery", lambda *args, **kwargs: {"ok": True, "charged_xu": 0})


def _patch_confirm(monkeypatch, *, engine_result=None, start_task=True):
    _reset()
    state = _install_store(monkeypatch)
    submit_calls = []
    start_calls = []

    async def fake_execute(feature, params, context):
        submit_calls.append((feature, params, context))
        return engine_result or {"ok": True, "provider_result": {"ok": True, "provider": "key4u_suno", "task_id": "provider-task-h6", "status": "PASS_SUBMITTED"}}

    def fake_start(_context, key):
        start_calls.append(key)
        return bool(start_task)

    monkeypatch.setattr(bot, "can_user_access_product_engine", lambda *args, **kwargs: {"allowed": True})
    monkeypatch.setattr(bot, "get_user", lambda uid: (999, None, None))
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: False)
    monkeypatch.setattr(bot, "execute_engine", fake_execute)
    monkeypatch.setattr(bot, "progress_auto_refresh_start_task", fake_start)
    state.submit_calls = submit_calls
    state.start_calls = start_calls
    return state


def test_music_confirm_submits_provider_once(monkeypatch):
    state = _patch_confirm(monkeypatch)
    query = CaptureQuery()
    asyncio.run(bot.handle_music_product_confirm(query, SimpleNamespace(), user_id=USER_ID, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result()))
    saved_result = bot.get_music_guided_result(USER_ID)
    asyncio.run(bot.handle_music_product_confirm(query, SimpleNamespace(), user_id=USER_ID, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=saved_result))
    assert len(state.submit_calls) == 1


def test_music_confirm_saves_provider_task_id(monkeypatch):
    state = _patch_confirm(monkeypatch)
    asyncio.run(bot.handle_music_product_confirm(CaptureQuery(), SimpleNamespace(), user_id=USER_ID, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result()))
    saved = list(state.store.values())[-1]
    assert saved["provider_task_id"] == "provider-task-h6"
    assert saved["provider_job_id"] == "provider-task-h6"


def test_music_duplicate_confirm_does_not_resubmit(monkeypatch):
    state = _patch_confirm(monkeypatch)
    query = CaptureQuery()
    asyncio.run(bot.handle_music_product_confirm(query, SimpleNamespace(), user_id=USER_ID, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result()))
    duplicate_result = bot.get_music_guided_result(USER_ID)
    asyncio.run(bot.handle_music_product_confirm(query, SimpleNamespace(), user_id=USER_ID, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=duplicate_result))
    assert len(state.submit_calls) == 1
    assert "khong gui lai" not in query.message.outputs[-1]["text"].lower()


def test_music_submit_failure_clean_no_charge(monkeypatch):
    state = _patch_confirm(monkeypatch, engine_result={"ok": False, "status": "FAILED", "detail": "submit rejected"})
    query = CaptureQuery()
    asyncio.run(bot.handle_music_product_confirm(query, SimpleNamespace(), user_id=USER_ID, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result()))
    failed = list(state.store.values())[-1]
    assert failed["terminal_state"] == "failed_no_charge"
    assert failed["confirm_submit_blocker"] == "provider_submit_failed"
    assert "chưa trừ Xu" in query.message.outputs[-1]["text"]


def test_music_provider_task_missing_after_submit_blocker(monkeypatch):
    state = _patch_confirm(monkeypatch, engine_result={"ok": True, "provider_result": {"ok": True, "provider": "key4u_suno", "status": "PASS_SUBMITTED"}})
    asyncio.run(bot.handle_music_product_confirm(CaptureQuery(), SimpleNamespace(), user_id=USER_ID, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result()))
    saved = list(state.store.values())[-1]
    assert saved["confirm_submit_blocker"] == "provider_job_id_missing_after_submit"
    assert saved["terminal_state"] == "failed_no_charge"


def test_music_materializes_valid_result_url_to_local_file(monkeypatch, tmp_path):
    job = _job(status="completed", provider_completed=True, result_url="https://cdn.example.test/h6.mp3")
    _install_store(monkeypatch, job)
    _patch_materializer(monkeypatch, tmp_path)
    result = asyncio.run(bot.materialize_music_artifact_for_job(job, updated_by=USER_ID, source="h6"))
    assert result["ok"] is True
    assert result["job"]["output_bytes"] == len(AUDIO_BYTES)
    assert result["job"]["audio_validated"] is True
    assert result["job"]["music_result_path"]


def test_music_materialization_follows_redirect(monkeypatch, tmp_path):
    seen = []

    async def fake_download(url, timeout_seconds=60.0):
        seen.append(url)
        return AUDIO_BYTES, "http=200; bytes=7800; content_type=audio/mpeg; redirected=yes", 200

    job = _job(status="completed", provider_completed=True, result_url="https://redirect.example.test/song")
    _install_store(monkeypatch, job)
    _patch_materializer(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "_download_music_audio_url_bytes", fake_download)
    result = asyncio.run(bot.materialize_music_artifact_for_job(job, updated_by=USER_ID, source="h6_redirect"))
    assert result["ok"] is True
    assert seen == ["https://redirect.example.test/song"]


def test_music_materialization_rejects_zero_bytes(monkeypatch, tmp_path):
    job = _job(status="completed", provider_completed=True, result_url="https://cdn.example.test/zero.mp3")
    _install_store(monkeypatch, job)
    _patch_materializer(monkeypatch, tmp_path, payload=b"", detail="empty body", status=200)
    result = asyncio.run(bot.materialize_music_artifact_for_job(job, updated_by=USER_ID, source="h6_zero"))
    assert result["ok"] is False
    assert result["job"]["primary_blocker"] == "artifact_zero_bytes"


def test_music_materialization_rejects_html_error_page(monkeypatch):
    async def fake_base(_url, timeout_seconds=60.0):
        return b"<html><body>expired</body></html>" * 80, "http=200; bytes=2400; content_type=text/html", 200

    monkeypatch.setattr(bot, "_download_audio_url_bytes", fake_base)
    payload, detail, status = asyncio.run(bot._download_music_audio_url_bytes("https://cdn.example.test/song.mp3"))
    assert payload == b""
    assert status == 200
    assert "html_error_page" in detail or "invalid_content_type" in detail


def test_music_materialization_rejects_invalid_content_type(monkeypatch):
    async def fake_base(_url, timeout_seconds=60.0):
        return b"not really audio" * 300, "http=200; bytes=4800; content_type=text/plain", 200

    monkeypatch.setattr(bot, "_download_audio_url_bytes", fake_base)
    payload, detail, _status = asyncio.run(bot._download_music_audio_url_bytes("https://cdn.example.test/song.mp3"))
    assert payload == b""
    assert "invalid_content_type" in detail


def test_music_materialization_saves_bytes_duration_hash(monkeypatch, tmp_path):
    job = _job(status="completed", provider_completed=True, result_url="https://cdn.example.test/hash.mp3")
    _install_store(monkeypatch, job)
    _patch_materializer(monkeypatch, tmp_path, duration=203)
    result = asyncio.run(bot.materialize_music_artifact_for_job(job, updated_by=USER_ID, source="h6_hash"))
    saved = result["job"]
    assert saved["output_bytes"] == len(AUDIO_BYTES)
    assert saved["artifact_duration_seconds"] == 203
    assert saved["output_sha256"] == bot.music_audio_sha256(AUDIO_BYTES)


def test_music_result_url_expired_sets_download_failed(monkeypatch, tmp_path):
    job = _job(status="completed", provider_completed=True, result_url="https://cdn.example.test/expired.mp3?token=secret")
    _install_store(monkeypatch, job)
    _patch_materializer(monkeypatch, tmp_path, payload=b"", detail="HTTP 403", status=403)
    result = asyncio.run(bot.materialize_music_artifact_for_job(job, updated_by=USER_ID, source="h6_expired"))
    assert result["ok"] is False
    assert result["job"]["primary_blocker"] == "artifact_download_failed"
    assert result["job"]["artifact_download_error_category"] == "result_url_expired"
    assert result["job"]["artifact_materialization_status"] == "ARTIFACT_DOWNLOAD_FAILED"


def test_music_recovery_materializes_existing_result_without_resubmit(monkeypatch, tmp_path):
    job = _job(status="completed", provider_completed=True, result_url="https://cdn.example.test/recover.mp3")
    _install_store(monkeypatch, job)
    _patch_materializer(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "submit_music_generation_job", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("resubmit")))
    fake = FakeBot()
    result = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=_ctx(fake), user_id=USER_ID, source="h6_recover"))
    assert result["ok"] is True
    assert len(fake.audio) == 1


def test_music_artifact_ready_requires_bytes_duration_validation():
    job = _job(status="completed", provider_completed=True, artifact_ready=True, audio_validated=True, output_bytes=len(AUDIO_BYTES), artifact_duration_seconds=0)
    assert bot.music_job_artifact_ready_value(job) is False


def test_music_duration_metadata_alone_not_ready():
    job = {"duration_seconds": 120, "artifact_duration_seconds": 120}
    assert bot.music_job_artifact_metadata_ready(job) is False
    assert bot.music_job_artifact_ready_value(job) is False


def test_music_audio_validated_required_before_delivery(tmp_path):
    path = tmp_path / "ready.mp3"
    path.write_bytes(AUDIO_BYTES)
    job = _job(output_path=str(path), output_bytes=len(AUDIO_BYTES), artifact_duration_seconds=120, artifact_ready=True, audio_validated=False)
    assert bot.music_job_ready_artifact_validated(job) is False


def test_music_auto_status_edits_existing_panel(monkeypatch, tmp_path):
    job = _job(status="submitted", progress_percent=5)
    _install_store(monkeypatch, job)
    _patch_materializer(monkeypatch, tmp_path)

    async def fake_poll(_state, updated_by=""):
        return {"ok": True, "status": "SUCCESS", "output_url": "https://cdn.example.test/auto.mp3"}

    monkeypatch.setattr(bot, "poll_music_generation_job", fake_poll)
    record = bot.progress_auto_refresh_register(product_type="music_song", job_id=JOB_ID, chat_id=USER_ID, message_id=7, user_id=USER_ID, initial_snapshot={"stage": "received_request", "percent": 5, "terminal_state": "", "text": "old 5", "render_hash": "old"}, start_task=False)
    fake = FakeBot()
    result = asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    assert fake.edits
    assert result["snapshot"]["percent"] == 100


def test_music_manual_refresh_read_only(monkeypatch, tmp_path):
    job = _job(status="processing", provider_task_id="provider-h6-task")
    _install_store(monkeypatch, job)
    monkeypatch.setattr(bot, "execute_engine", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no submit from refresh")))

    async def fake_poll(_state, updated_by=""):
        return {"ok": False, "status": "PROCESSING", "output_url": ""}

    monkeypatch.setattr(bot, "poll_music_generation_job", fake_poll)
    query = CaptureQuery(f"progress|status|music_song|{JOB_ID}")
    result = asyncio.run(bot.maybe_deliver_music_progress_job(query, _ctx(FakeBot()), product_type="music_song", job_id=JOB_ID, user_id=USER_ID, lang="vi"))
    assert result["ok"] is False
    assert result["status"] in {"ARTIFACT_NOT_READY", "TERMINAL_FAILED"}


def test_music_terminal_delivered_final_edit(monkeypatch, tmp_path):
    test_music_auto_status_edits_existing_panel(monkeypatch, tmp_path)


def test_music_failed_no_charge_final_edit(monkeypatch):
    job = _job(status="failed", terminal_state="failed_no_charge", music_terminal_state="failed_no_charge", error_category="artifact_materialization_failed", progress_percent=85)
    _install_store(monkeypatch, job)
    record = bot.progress_auto_refresh_register(product_type="music_song", job_id=JOB_ID, chat_id=USER_ID, message_id=9, user_id=USER_ID, initial_snapshot={"stage": "received_request", "percent": 5, "terminal_state": "", "text": "old", "render_hash": "old"}, start_task=False)
    fake = FakeBot()
    result = asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    assert result["snapshot"]["terminal_state"] == "failed_no_charge"
    assert fake.edits


def test_music_step_create_song_green_only_after_provider_complete():
    job = _job(status="processing", result_url="https://cdn.example.test/not-yet.mp3", provider_completed=False, music_provider_completed=False)
    state = bot.product_progress_state_from_job("music_song", job)
    assert "generating_song" not in state["completed_steps"]


def test_music_file_check_green_only_after_audio_validated():
    job = _job(status="completed", provider_completed=True, output_bytes=len(AUDIO_BYTES), artifact_duration_seconds=120, audio_validated=False)
    state = bot.product_progress_state_from_job("music_song", job)
    assert "validating_audio" not in state["completed_steps"]


def test_music_no_generic_error_for_known_blockers(monkeypatch):
    fake = FakeBot()
    monkeypatch.setattr(bot, "get_music_guided_result", lambda uid: {"music_internal_job_id": JOB_ID})
    monkeypatch.setattr(bot, "get_engine_async_job", lambda job_id: _job(status="failed", terminal_state="failed_no_charge", confirm_submit_blocker="provider_submit_failed", error_category="provider_submit_failed"))
    update = SimpleNamespace(
        callback_query=SimpleNamespace(data="music_quick|showroom|music_ai_confirm"),
        effective_user=SimpleNamespace(id=USER_ID),
        effective_chat=SimpleNamespace(id=USER_ID),
        effective_message=None,
    )
    asyncio.run(bot.on_telegram_error(update, SimpleNamespace(error=RuntimeError("known music blocker"), bot=fake, chat_data={})))
    assert fake.messages == []


def test_music_deliver_once_after_valid_audio(monkeypatch, tmp_path):
    job = _job(status="completed", provider_completed=True, result_url="https://cdn.example.test/once.mp3")
    _install_store(monkeypatch, job)
    _patch_materializer(monkeypatch, tmp_path)
    fake = FakeBot()
    result = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=_ctx(fake), user_id=USER_ID, source="h6_once"))
    assert result["ok"] is True
    assert len(fake.audio) == 1


def test_music_delivered_blocks_late_fail(monkeypatch, tmp_path):
    test_music_deliver_once_after_valid_audio(monkeypatch, tmp_path)
    fake = FakeBot()
    result = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=_ctx(fake), user_id=USER_ID, source="late_fail"))
    assert result["duplicate"] is True
    assert len(fake.audio) == 0


def test_music_manual_refresh_after_delivered_no_redelivery(monkeypatch, tmp_path):
    test_music_deliver_once_after_valid_audio(monkeypatch, tmp_path)
    fake = FakeBot()
    query = CaptureQuery(f"progress|status|music_song|{JOB_ID}")
    asyncio.run(bot.handle_product_progress_callback(SimpleNamespace(callback_query=query), _ctx(fake)))
    assert len(fake.audio) == 0


def test_music_telegram_delivery_failed_retryable(monkeypatch, tmp_path):
    job = _job(status="completed", provider_completed=True, result_url="https://cdn.example.test/retry.mp3")
    _install_store(monkeypatch, job)
    _patch_materializer(monkeypatch, tmp_path)
    result = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=_ctx(FakeBot(fail_audio=True)), user_id=USER_ID, source="h6_retry"))
    assert result["ok"] is False
    assert result["job"]["delivery_state"] == "retryable"
    assert result["job"]["auto_delivery_blocker"] == "telegram_delivery_failed"


def test_music_recover_lookup_all_id_variants(monkeypatch):
    job = _job(internal_job_id="MUSABC12345")
    _install_store(monkeypatch, job)
    lookup = bot.get_engine_async_job_lookup("MUS-ABC12345")
    assert lookup["lookup_found"] is True
    assert lookup["resolved_job_id"] == "MUSABC12345"


def test_music_recover_delivers_materialized_audio_once(monkeypatch, tmp_path):
    test_music_deliver_once_after_valid_audio(monkeypatch, tmp_path)


def test_music_debug_shows_materialization_fields(monkeypatch):
    job = _job(
        status="failed",
        result_url="https://cdn.example.test/song.mp3?token=secret-token",
        artifact_materialization_status="ARTIFACT_DOWNLOAD_FAILED",
        artifact_download_http_status=403,
        artifact_download_content_type="text/html",
        artifact_downloaded_bytes=0,
        artifact_download_error_category="result_url_expired",
        primary_blocker="artifact_materialization_failed",
    )
    _install_store(monkeypatch, job)
    text = bot.music_job_debug_text(JOB_ID)
    assert "materialization_status" in text
    assert "download_http_status" in text
    assert "result_url_expired" in text


def test_music_debug_does_not_leak_secret_result_url(monkeypatch):
    job = _job(result_url="https://cdn.example.test/song.mp3?token=secret-token")
    _install_store(monkeypatch, job)
    text = bot.music_job_debug_text(JOB_ID)
    assert "secret-token" not in text
    assert "https://cdn.example.test/song.mp3" not in text
