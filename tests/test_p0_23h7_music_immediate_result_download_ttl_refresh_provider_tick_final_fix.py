import asyncio
from types import SimpleNamespace

import bot


AUDIO_BYTES = b"ID3-toan-aas-h7-real-music" * 320
USER_ID = 230707
JOB_ID = "MUSA7CA8864"


class FakeBot:
    def __init__(self):
        self.audio = []
        self.messages = []
        self.edits = []

    async def send_audio(self, **kwargs):
        self.audio.append(kwargs)
        return SimpleNamespace(message_id=9100 + len(self.audio), audio=SimpleNamespace(file_id=f"audio-h7-{len(self.audio)}"))

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)
        return SimpleNamespace(message_id=8100 + len(self.messages))

    async def edit_message_text(self, **kwargs):
        self.edits.append(kwargs)
        return SimpleNamespace(message_id=kwargs.get("message_id"))


def _ctx(fake_bot=None):
    return SimpleNamespace(bot=fake_bot or FakeBot(), args=[])


def _reset():
    bot.PROGRESS_AUTO_REFRESH_JOBS.clear()
    bot.PROGRESS_AUTO_REFRESH_TASKS.clear()
    bot.ENGINE_ASYNC_MEMORY_JOBS.clear()
    bot.MUSIC_PRODUCT_DELIVERY_MEMORY_LOCKS.clear()
    bot.USER_PENDING.clear()


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
        "provider_task_id": "provider-h7-task",
        "provider_job_id": "provider-h7-task",
        "provider_submit_called": True,
        "status": "submitted",
        "progress_percent": 12,
        "pending_charge_xu": 0,
        "charged_xu": 0,
        "description": "TOAN AAS product song",
        "genre": "pop",
        "mood": "bright",
        "song_vocal": "female",
        "provider_style_prompt": "bright pop song",
        "provider_lyrics": "hello world",
        "provider_title": "TOAN AAS Song",
        "provider_tags": "pop",
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


def _patch_materializer(monkeypatch, tmp_path, *, downloads=None, duration=188):
    download_calls = []
    downloads = downloads or {}

    async def fake_download(url, timeout_seconds=60.0):
        download_calls.append(str(url))
        result = downloads.get(str(url))
        if result is None:
            result = (AUDIO_BYTES, "http=200; bytes=8192; content_type=audio/mpeg", 200)
        return result

    async def fake_duration(_audio, fallback=0):
        return duration

    def fake_upsert(*, audio_bytes, result=None, job=None, status="generated_unused", updated_by=""):
        vault_id = str((job or {}).get("vault_id") or "MV-H7")
        storage = tmp_path / f"{vault_id}.mp3"
        storage.write_bytes(bytes(audio_bytes or b""))
        return {"vault_id": vault_id, "storage_ref": str(storage)}

    monkeypatch.setattr(bot, "_download_music_audio_url_bytes", fake_download)
    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", fake_duration)
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", fake_upsert)
    monkeypatch.setattr(bot, "music_canonical_output_root", lambda: str(tmp_path / "music_outputs"))
    monkeypatch.setattr(bot, "get_music_vault_entry", lambda vault_id: {"vault_id": vault_id, "storage_ref": str(tmp_path / f"{vault_id}.mp3")})
    monkeypatch.setattr(bot, "mark_music_vault_status", lambda *args, **kwargs: {"vault_id": args[0] if args else "MV-H7"})
    monkeypatch.setattr(bot, "music_product_charge_after_delivery", lambda *args, **kwargs: {"ok": True, "charged_xu": 0})
    return download_calls


def _patch_provider_poll(monkeypatch, *, url="https://cdn1.suno.ai/fresh.mp3?token=fresh", status="COMPLETED", ok=True):
    calls = []

    async def fake_poll(state, updated_by=""):
        calls.append(dict(state or {}))
        return {"ok": ok, "status": status, "output_url": url, "detail": status}

    monkeypatch.setattr(bot, "poll_music_generation_job", fake_poll)
    return calls


def test_provider_completed_triggers_immediate_download(monkeypatch, tmp_path):
    _install_store(monkeypatch, _job())
    calls = _patch_materializer(monkeypatch, tmp_path)
    _patch_provider_poll(monkeypatch, url="https://cdn1.suno.ai/song.mp3?token=live")
    result = asyncio.run(bot.poll_music_suno_async_job(JOB_ID, updated_by=USER_ID))
    assert result["ok"] is True
    assert calls == ["https://cdn1.suno.ai/song.mp3?token=live"]
    saved = result["job"]
    assert saved["result_url_first_seen_at"]
    assert saved["result_url_downloaded_at"]


def test_result_url_first_seen_downloaded_before_terminal(monkeypatch, tmp_path):
    _install_store(monkeypatch, _job())
    _patch_materializer(monkeypatch, tmp_path)
    _patch_provider_poll(monkeypatch)
    result = asyncio.run(bot.poll_music_suno_async_job(JOB_ID, updated_by=USER_ID))
    saved = result["job"]
    assert saved["result_url_first_seen_at"]
    assert saved["result_url_downloaded_at"]
    assert saved.get("terminal_state", "") != "failed_no_charge"


def test_local_artifact_saved_after_provider_completed(monkeypatch, tmp_path):
    job = _job(status="completed", provider_completed=True, result_url="https://cdn1.suno.ai/local.mp3")
    _install_store(monkeypatch, job)
    _patch_materializer(monkeypatch, tmp_path)
    result = asyncio.run(bot.materialize_music_artifact_for_job(job, updated_by=USER_ID, source="h7"))
    local_path = result["job"]["local_artifact_path"]
    assert local_path.endswith(f"{JOB_ID}.mp3")
    assert bot.os.path.exists(local_path)
    assert bot.os.path.getsize(local_path) == len(AUDIO_BYTES)


def test_valid_download_delivers_once_without_manual_recover(monkeypatch, tmp_path):
    job = _job(status="completed", provider_completed=True, result_url="https://cdn1.suno.ai/deliver.mp3")
    _install_store(monkeypatch, job)
    _patch_materializer(monkeypatch, tmp_path)
    fake = FakeBot()
    result = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=_ctx(fake), user_id=USER_ID, source="auto_tick"))
    assert result["ok"] is True
    assert len(fake.audio) == 1


def test_no_manual_recover_needed_for_success_path(monkeypatch, tmp_path):
    _install_store(monkeypatch, _job())
    _patch_materializer(monkeypatch, tmp_path)
    _patch_provider_poll(monkeypatch, url="https://cdn1.suno.ai/auto.mp3")
    fake = FakeBot()
    record = {"auto_delivery_enabled": True, "product_type": "music_song", "job_id": JOB_ID, "user_id": USER_ID, "chat_id": USER_ID, "lang": "vi"}
    result = asyncio.run(bot.progress_auto_refresh_status_for_tick(_ctx(fake), record))
    assert result["delivery_state"] == "delivered"
    assert len(fake.audio) == 1


def test_provider_completed_not_overwritten_by_scheduler_start_failed(monkeypatch):
    state = _install_store(monkeypatch)
    job = _job(provider_completed=True, status="completed", last_provider_status="COMPLETED", provider_status="completed")
    state.store[JOB_ID] = dict(job)
    updated = bot.mark_music_confirm_submit_blocker(job, "scheduler_start_failed", "scheduler_start_failed", updated_by=USER_ID)
    assert updated["provider_status"] == "completed"
    assert updated["last_provider_status"] == "COMPLETED"
    assert updated["scheduler_status"] == "start_failed"


def test_scheduler_start_failed_secondary_not_primary_when_result_url_exists(monkeypatch):
    _install_store(monkeypatch)
    job = _job(result_url="https://cdn1.suno.ai/expired.mp3", provider_completed=True, confirm_submit_blocker="scheduler_start_failed")
    updated = bot.set_music_artifact_blocker(job, "artifact_download_failed", secondary="scheduler_start_failed", detail="HTTP 403", updated_by=USER_ID)
    assert bot.music_job_artifact_primary_blocker(updated) == "artifact_download_failed"
    assert bot.music_job_artifact_secondary_blocker(updated) == "scheduler_start_failed"


def test_music_panel_shows_downloading_file_after_provider_completed():
    job = _job(status="downloading", provider_completed=True, music_provider_completed=True, result_url="https://cdn1.suno.ai/panel.mp3")
    text = bot.product_progress_status_from_job_text("music_song", job, JOB_ID, "vi")
    assert "Đang tải file nhạc" in text


def test_file_check_green_only_after_audio_validated():
    job = _job(status="downloading", provider_completed=True, output_bytes=len(AUDIO_BYTES), artifact_duration_seconds=180, audio_validated=False)
    state = bot.product_progress_state_from_job("music_song", job)
    assert "generating_song" in state["completed_steps"]
    assert "validating_audio" not in state["completed_steps"]


def test_no_stuck_12_percent_after_provider_completed():
    job = _job(status="downloading", provider_completed=True, music_provider_completed=True, progress_percent=12, result_url="https://cdn1.suno.ai/panel.mp3")
    state = bot.product_progress_state_from_job("music_song", job)
    assert state["percent"] >= 80
    assert state["percent"] < 100


def test_403_cdn_url_sets_result_url_expired(monkeypatch):
    async def fake_base(_url, timeout_seconds=60.0):
        return b"", "http=403; downloaded_bytes=0; content_type=text/html", 403

    monkeypatch.setattr(bot, "_download_audio_url_bytes", fake_base)
    payload, detail, status = asyncio.run(bot._download_music_audio_url_bytes("https://cdn1.suno.ai/song.mp3?token=old"))
    assert payload == b""
    assert status == 403
    assert bot.music_download_error_category(detail, status) == "result_url_expired"


def test_expired_url_triggers_provider_repoll_for_fresh_url(monkeypatch, tmp_path):
    old = "https://cdn1.suno.ai/old.mp3?token=old"
    fresh = "https://cdn1.suno.ai/fresh.mp3?token=fresh"
    job = _job(status="failed", terminal_state="failed_no_charge", provider_completed=True, result_url=old)
    _install_store(monkeypatch, job)
    _patch_materializer(monkeypatch, tmp_path, downloads={old: (b"", "http=403; downloaded_bytes=0; content_type=text/html", 403), fresh: (AUDIO_BYTES, "http=200; bytes=8192; content_type=audio/mpeg", 200)})
    poll_calls = _patch_provider_poll(monkeypatch, url=fresh)
    result = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=_ctx(FakeBot()), user_id=USER_ID, source="recover"))
    assert poll_calls
    assert result["job"]["refreshed_result_url"] is True


def test_provider_poll_expired_url_refreshes_before_terminal(monkeypatch, tmp_path):
    old = "https://cdn1.suno.ai/provider-old.mp3?token=old"
    fresh = "https://cdn1.suno.ai/provider-fresh.mp3?token=fresh"
    _install_store(monkeypatch, _job())
    _patch_materializer(monkeypatch, tmp_path, downloads={old: (b"", "http=403; downloaded_bytes=0; content_type=text/html", 403), fresh: (AUDIO_BYTES, "http=200; bytes=8192; content_type=audio/mpeg", 200)})
    calls = []

    async def fake_poll(state, updated_by=""):
        calls.append(dict(state or {}))
        if len(calls) == 1:
            return {"ok": True, "status": "COMPLETED", "output_url": old, "detail": "completed"}
        return {"ok": True, "status": "COMPLETED", "output_url": fresh, "detail": "completed"}

    monkeypatch.setattr(bot, "poll_music_generation_job", fake_poll)
    result = asyncio.run(bot.poll_music_suno_async_job(JOB_ID, updated_by=USER_ID))
    assert result["ok"] is True
    assert len(calls) == 2
    assert result["job"]["refreshed_result_url"] is True
    assert result["job"].get("terminal_state", "") != "failed_no_charge"


def test_fresh_url_after_repoll_materializes_and_delivers(monkeypatch, tmp_path):
    old = "https://cdn1.suno.ai/old-deliver.mp3?token=old"
    fresh = "https://cdn1.suno.ai/fresh-deliver.mp3?token=fresh"
    _install_store(monkeypatch, _job(status="failed", terminal_state="failed_no_charge", provider_completed=True, result_url=old))
    _patch_materializer(monkeypatch, tmp_path, downloads={old: (b"", "http=403; downloaded_bytes=0; content_type=text/html", 403), fresh: (AUDIO_BYTES, "http=200; bytes=8192; content_type=audio/mpeg", 200)})
    _patch_provider_poll(monkeypatch, url=fresh)
    fake = FakeBot()
    result = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=_ctx(fake), user_id=USER_ID, source="recover"))
    assert result["ok"] is True
    assert result["job"]["delivery_state"] == "delivered"
    assert len(fake.audio) == 1


def test_expired_url_without_refresh_clean_failed_no_charge(monkeypatch, tmp_path):
    old = "https://cdn1.suno.ai/no-refresh.mp3?token=old"
    _install_store(monkeypatch, _job(status="failed", terminal_state="failed_no_charge", provider_completed=True, result_url=old))
    _patch_materializer(monkeypatch, tmp_path, downloads={old: (b"", "http=403; downloaded_bytes=0; content_type=text/html", 403)})
    _patch_provider_poll(monkeypatch, url=old)
    result = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=_ctx(FakeBot()), user_id=USER_ID, source="recover"))
    assert result["ok"] is False
    assert result["primary_blocker"] == "result_url_expired"
    assert result["job"]["terminal_state"] == "failed_no_charge"


def test_recovery_does_not_resubmit_automatically(monkeypatch, tmp_path):
    old = "https://cdn1.suno.ai/no-resubmit.mp3?token=old"
    _install_store(monkeypatch, _job(status="failed", terminal_state="failed_no_charge", provider_completed=True, result_url=old))
    _patch_materializer(monkeypatch, tmp_path, downloads={old: (b"", "http=403; downloaded_bytes=0; content_type=text/html", 403)})
    _patch_provider_poll(monkeypatch, url=old)

    async def fail_submit(*args, **kwargs):
        raise AssertionError("recovery must not resubmit provider")

    monkeypatch.setattr(bot, "submit_music_generation_job", fail_submit)
    result = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=_ctx(FakeBot()), user_id=USER_ID, source="recover"))
    assert result["status"] == "RESULT_URL_EXPIRED"


def test_music_retry_job_creates_new_provider_task_from_saved_request(monkeypatch):
    state = _install_store(monkeypatch, _job(status="failed", terminal_state="failed_no_charge", primary_blocker="result_url_expired"))

    async def fake_submit(result, preview=False, admin_smoke=False, updated_by=""):
        return {"ok": True, "status": "PASS_SUBMITTED", "provider": "key4u_suno", "task_id": "retry-provider-task"}

    monkeypatch.setattr(bot, "submit_music_generation_job", fake_submit)
    result = asyncio.run(bot.retry_music_job_from_saved_request(JOB_ID, user_id=USER_ID, chat_id=USER_ID, updated_by=USER_ID))
    retry_job = result["retry_job"]
    assert result["ok"] is True
    assert retry_job["provider_task_id"] == "retry-provider-task"
    assert retry_job["internal_job_id"] in state.store


def test_retry_job_links_old_job(monkeypatch):
    _install_store(monkeypatch, _job(status="failed", terminal_state="failed_no_charge", primary_blocker="result_url_expired"))

    async def fake_submit(result, preview=False, admin_smoke=False, updated_by=""):
        return {"ok": True, "status": "PASS_SUBMITTED", "provider": "key4u_suno", "task_id": "retry-provider-task"}

    monkeypatch.setattr(bot, "submit_music_generation_job", fake_submit)
    result = asyncio.run(bot.retry_music_job_from_saved_request(JOB_ID, user_id=USER_ID, chat_id=USER_ID, updated_by=USER_ID))
    old_job = result["job"]
    assert old_job["retry_job_id"] == result["new_job_id"]


def test_retry_does_not_double_charge(monkeypatch):
    _install_store(monkeypatch, _job(status="failed", terminal_state="failed_no_charge", primary_blocker="result_url_expired", pending_charge_xu=300))

    async def fake_submit(result, preview=False, admin_smoke=False, updated_by=""):
        return {"ok": True, "status": "PASS_SUBMITTED", "provider": "key4u_suno", "task_id": "retry-provider-task"}

    monkeypatch.setattr(bot, "submit_music_generation_job", fake_submit)
    result = asyncio.run(bot.retry_music_job_from_saved_request(JOB_ID, user_id=USER_ID, chat_id=USER_ID, updated_by=USER_ID))
    assert int(result["retry_job"]["pending_charge_xu"]) == 0
    assert result["retry_job"]["retry_no_duplicate_charge"] is True


def test_retry_button_not_shown_after_delivered(monkeypatch):
    _install_store(monkeypatch, _job(status="delivered", delivery_state="delivered", delivery_message_id="123"))

    async def fail_submit(*args, **kwargs):
        raise AssertionError("delivered job must not retry")

    monkeypatch.setattr(bot, "submit_music_generation_job", fail_submit)
    result = asyncio.run(bot.retry_music_job_from_saved_request(JOB_ID, user_id=USER_ID, chat_id=USER_ID, updated_by=USER_ID))
    assert result["status"] == "ALREADY_DELIVERED"


def test_downloader_follows_redirect(monkeypatch):
    init_kwargs = {}

    class Response:
        status_code = 200
        content = AUDIO_BYTES
        text = ""
        headers = {"content-type": "audio/mpeg"}

    class FakeClient:
        def __init__(self, **kwargs):
            init_kwargs.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, target):
            return Response()

    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)
    payload, _detail, _status = asyncio.run(bot._download_audio_url_bytes("https://cdn1.suno.ai/redirect.mp3"))
    assert payload
    assert init_kwargs["follow_redirects"] is True


def test_downloader_sets_user_agent(monkeypatch):
    init_kwargs = {}

    class Response:
        status_code = 200
        content = AUDIO_BYTES
        text = ""
        headers = {"content-type": "audio/mpeg"}

    class FakeClient:
        def __init__(self, **kwargs):
            init_kwargs.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, target):
            return Response()

    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)
    asyncio.run(bot._download_audio_url_bytes("https://cdn1.suno.ai/ua.mp3"))
    assert "User-Agent" in init_kwargs["headers"]
    assert init_kwargs["headers"]["User-Agent"]


def test_downloader_rejects_html_error(monkeypatch):
    async def fake_base(_url, timeout_seconds=60.0):
        return b"<html><body>expired</body></html>" * 100, "http=200; bytes=3200; content_type=text/html", 200

    monkeypatch.setattr(bot, "_download_audio_url_bytes", fake_base)
    payload, detail, _status = asyncio.run(bot._download_music_audio_url_bytes("https://cdn1.suno.ai/html.mp3"))
    assert payload == b""
    assert "html_error_page" in detail or "invalid_content_type" in detail


def test_downloader_retries_5xx(monkeypatch):
    calls = {"count": 0}

    class Response:
        def __init__(self, status_code, content=b"", content_type="text/plain"):
            self.status_code = status_code
            self.content = content
            self.text = "server error"
            self.headers = {"content-type": content_type}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, target):
            calls["count"] += 1
            if calls["count"] == 1:
                return Response(500)
            return Response(200, AUDIO_BYTES, "audio/mpeg")

    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(bot, "MUSIC_RESULT_DOWNLOAD_RETRY_SLEEP_SECONDS", 0)
    payload, detail, status = asyncio.run(bot._download_audio_url_bytes("https://cdn1.suno.ai/retry.mp3"))
    assert status == 200
    assert payload
    assert calls["count"] == 2
    assert "attempts=2" in detail


def test_downloader_records_http_status_content_type_bytes(monkeypatch):
    class Response:
        status_code = 200
        content = AUDIO_BYTES
        text = ""
        headers = {"content-type": "audio/mpeg"}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, target):
            return Response()

    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)
    payload, detail, status = asyncio.run(bot._download_audio_url_bytes("https://cdn1.suno.ai/detail.mp3"))
    assert status == 200
    assert payload
    assert "http=200" in detail
    assert "bytes=" in detail
    assert "content_type=audio/mpeg" in detail
