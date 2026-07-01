import asyncio
from types import SimpleNamespace

import bot


AUDIO_BYTES = b"ID3-toan-aas-h5-materialized-music" * 300
JOB_ID = "MUS457A8FBB"
USER_ID = 457005


class FakeBot:
    def __init__(self):
        self.audio = []
        self.messages = []
        self.edits = []

    async def send_audio(self, **kwargs):
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
    def __init__(self, data, user_id=USER_ID):
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


def _metadata_job(*, result_url=True, scheduler_failed=True, terminal="", output_bytes=0, audio_validated=False):
    job = {
        "internal_job_id": JOB_ID,
        "feature": "music_suno",
        "product_type": "music_song",
        "music_product_type": "music_song",
        "music_product_mode": "song",
        "music_product_tier": "music_tier_standard",
        "user_id": str(USER_ID),
        "chat_id": str(USER_ID),
        "provider": "key4u_suno",
        "provider_task_id": "provider-h5-task",
        "provider_job_id": "provider-h5-task",
        "provider_submit_called": True,
        "provider_completed": True,
        "music_provider_completed": True,
        "last_provider_status": "completed",
        "status": "completed",
        "progress_percent": 85,
        "artifact_ready": True,
        "music_artifact_ready": True,
        "artifact_validated": audio_validated,
        "audio_validated": audio_validated,
        "music_audio_validated": audio_validated,
        "artifact_state": "metadata_ready",
        "music_artifact_state": "metadata_ready",
        "output_bytes": output_bytes,
        "music_result_size_bytes": output_bytes,
        "artifact_duration_seconds": 120,
        "duration_seconds": 120,
        "music_result_duration_seconds": 120,
        "pending_charge_xu": 0,
        "charged_xu": 0,
    }
    if result_url:
        job.update({
            "result_url": "https://cdn.example.invalid/music/h5.mp3",
            "output_url": "https://cdn.example.invalid/music/h5.mp3",
            "music_output_url": "https://cdn.example.invalid/music/h5.mp3",
        })
    if scheduler_failed:
        job.update({
            "confirm_submit_blocker": "scheduler_start_failed",
            "auto_delivery_blocker": "scheduler_start_failed",
            "error_category": "scheduler_start_failed",
        })
    if terminal:
        job["terminal_state"] = terminal
        job["music_terminal_state"] = terminal
    return job


def _ready_delivered_job():
    job = _metadata_job(result_url=True, scheduler_failed=False, output_bytes=len(AUDIO_BYTES), audio_validated=True)
    job.update({
        "_auto_delivery_audio_bytes": AUDIO_BYTES,
        "output_sha256": bot.music_audio_sha256(AUDIO_BYTES),
        "artifact_state": "ready",
        "music_artifact_state": "ready",
        "status": "delivered",
        "terminal_state": "delivered",
        "music_terminal_state": "delivered",
        "delivery_state": "delivered",
        "music_delivery_lock": "sent",
        "delivery_message_id": "9001",
        "music_delivery_message_id": "9001",
        "output_file_id": "audio-1",
    })
    return job


def _install_job(monkeypatch, job, *, payload=AUDIO_BYTES, duration=188, http_status=200, detail="ok"):
    _reset()
    bot.ENGINE_ASYNC_MEMORY_JOBS[str(job["internal_job_id"])] = dict(job)
    saves = []
    provider_calls = []

    def fake_save(payload_job):
        current = dict(payload_job)
        bot.ENGINE_ASYNC_MEMORY_JOBS[str(current.get("internal_job_id") or "")] = current
        saves.append(current)
        return dict(current)

    async def fake_download(_url, timeout_seconds=60.0):
        return payload, detail, http_status

    async def fake_duration(_audio, fallback=0):
        return duration

    async def fail_provider(*args, **kwargs):
        provider_calls.append((args, kwargs))
        raise AssertionError("provider must not be called by H5 recovery")

    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)
    monkeypatch.setattr(bot, "_download_music_audio_url_bytes", fake_download)
    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", fake_duration)
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **_kwargs: {"vault_id": "MV-H5", "storage_ref": ""})
    monkeypatch.setattr(bot, "get_music_vault_entry", lambda _vault_id: {"vault_id": _vault_id, "storage_ref": ""})
    monkeypatch.setattr(bot, "mark_music_vault_status", lambda *args, **kwargs: {"vault_id": args[0] if args else "MV-H5"})
    monkeypatch.setattr(bot, "music_product_charge_after_delivery", lambda *args, **kwargs: {"ok": True, "charged_xu": 0})
    monkeypatch.setattr(bot, "poll_music_suno_async_job", fail_provider)
    monkeypatch.setattr(bot, "poll_music_generation_job", fail_provider)
    monkeypatch.setattr(bot, "submit_music_generation_job", fail_provider)
    monkeypatch.setattr(bot, "execute_engine", fail_provider)
    return saves, provider_calls


def test_artifact_ready_false_when_bytes_zero():
    job = _metadata_job(output_bytes=0, audio_validated=True)
    assert bot.music_job_artifact_ready_value(job) is False
    assert bot.music_job_artifact_primary_blocker(job) == "artifact_zero_bytes"


def test_artifact_ready_requires_audio_validated():
    job = _metadata_job(output_bytes=len(AUDIO_BYTES), audio_validated=False)
    job["_auto_delivery_audio_bytes"] = AUDIO_BYTES
    job["output_sha256"] = bot.music_audio_sha256(AUDIO_BYTES)
    assert bot.music_job_artifact_ready_value(job) is False
    assert bot.music_job_artifact_primary_blocker(job) == "artifact_validation_failed"


def test_duration_metadata_alone_not_artifact_ready():
    job = _metadata_job(result_url=False, scheduler_failed=False, output_bytes=0, audio_validated=False)
    assert bot.music_job_artifact_duration_value(job) == 120
    assert bot.music_job_artifact_ready_value(job) is False
    assert bot.music_job_artifact_state(job) in {"metadata_ready", "invalid"}


def test_music_recover_materializes_from_result_url_without_resubmit(monkeypatch):
    _install_job(monkeypatch, _metadata_job())
    fake = FakeBot()
    result = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=_ctx(fake), user_id=USER_ID, source="h5_recover"))
    assert result["ok"] is True
    assert result["recovery_action"] == "materialize_success"
    assert result["job"]["output_bytes"] == len(AUDIO_BYTES)
    assert result["job"]["audio_validated"] is True
    assert len(fake.audio) == 1


def test_music_recover_validates_materialized_audio_before_delivery(monkeypatch):
    _install_job(monkeypatch, _metadata_job(), payload=AUDIO_BYTES, duration=0)
    fake = FakeBot()
    result = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=_ctx(fake), user_id=USER_ID, source="h5_bad_duration"))
    assert result["ok"] is False
    assert result["primary_blocker"] == "artifact_validation_failed"
    assert len(fake.audio) == 0


def test_music_recover_does_not_deliver_zero_byte_audio(monkeypatch):
    _install_job(monkeypatch, _metadata_job(), payload=b"", http_status=200, detail="empty body")
    fake = FakeBot()
    result = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=_ctx(fake), user_id=USER_ID, source="h5_zero"))
    assert result["ok"] is False
    assert result["primary_blocker"] == "artifact_zero_bytes"
    assert len(fake.audio) == 0


def test_music_recover_sets_artifact_zero_bytes_primary_blocker(monkeypatch):
    _install_job(monkeypatch, _metadata_job(), payload=b"", http_status=200)
    result = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=_ctx(FakeBot()), user_id=USER_ID, source="h5_zero_blocker"))
    assert result["job"]["primary_blocker"] == "artifact_zero_bytes"
    assert result["job"]["auto_delivery_blocker"] == "artifact_zero_bytes"


def test_scheduler_start_failed_is_secondary_when_artifact_invalid(monkeypatch):
    _install_job(monkeypatch, _metadata_job(scheduler_failed=True), payload=b"", http_status=200)
    result = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=_ctx(FakeBot()), user_id=USER_ID, source="h5_secondary"))
    assert result["primary_blocker"] == "artifact_zero_bytes"
    assert result["secondary_blocker"] == "scheduler_start_failed"
    assert result["job"]["secondary_blocker"] == "scheduler_start_failed"


def test_music_recover_missing_url_sets_artifact_missing(monkeypatch):
    _install_job(monkeypatch, _metadata_job(result_url=False), payload=AUDIO_BYTES)
    result = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=_ctx(FakeBot()), user_id=USER_ID, source="h5_missing"))
    assert result["ok"] is False
    assert result["primary_blocker"] == "artifact_missing"
    assert result["job"]["artifact_state"] == "missing"


def test_music_recover_download_failed_sets_materialization_failed(monkeypatch):
    _install_job(monkeypatch, _metadata_job(), payload=b"", http_status=500, detail="upstream failed")
    result = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=_ctx(FakeBot()), user_id=USER_ID, source="h5_download_fail"))
    assert result["ok"] is False
    assert result["primary_blocker"] == "artifact_materialization_failed"
    assert result["job"]["artifact_materialization_status"] == "ARTIFACT_DOWNLOAD_FAILED"


def test_music_recover_valid_artifact_calls_deliver_once(monkeypatch):
    _install_job(monkeypatch, _metadata_job())
    fake = FakeBot()
    first = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=_ctx(fake), user_id=USER_ID, source="h5_first"))
    second = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=_ctx(fake), user_id=USER_ID, source="h5_second"))
    assert first["ok"] is True
    assert second["duplicate"] is True
    assert len(fake.audio) == 1


def test_music_recover_preserves_duplicate_delivery_lock(monkeypatch):
    _install_job(monkeypatch, _ready_delivered_job())
    fake = FakeBot()
    result = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=_ctx(fake), user_id=USER_ID, source="h5_duplicate"))
    assert result["status"] == "ALREADY_DELIVERED"
    assert len(fake.audio) == 0


def test_music_recover_does_not_provider_resubmit_existing_result(monkeypatch):
    _saves, provider_calls = _install_job(monkeypatch, _metadata_job())
    fake = FakeBot()
    result = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=_ctx(fake), user_id=USER_ID, source="h5_no_resubmit"))
    assert result["ok"] is True
    assert provider_calls == []
    assert len(fake.audio) == 1


def test_music_progress_does_not_mark_file_check_green_for_zero_bytes():
    job = _metadata_job()
    text = bot.product_progress_status_from_job_text("music_song", job, JOB_ID, "vi")
    assert "✅ Kiểm tra file nhạc" not in text


def test_music_progress_marks_create_song_green_only_when_provider_complete_or_artifact_metadata_ready():
    job = _metadata_job()
    text = bot.product_progress_status_from_job_text("music_song", job, JOB_ID, "vi")
    assert "✅ Tạo bài hát" in text
    no_metadata = _metadata_job(result_url=False, scheduler_failed=False)
    no_metadata["provider_completed"] = False
    no_metadata["music_provider_completed"] = False
    no_metadata["status"] = "submitted"
    no_metadata["artifact_duration_seconds"] = 0
    no_metadata["duration_seconds"] = 0
    no_metadata["artifact_ready"] = False
    no_metadata["music_artifact_ready"] = False
    no_metadata["artifact_state"] = ""
    no_metadata["music_artifact_state"] = ""
    text = bot.product_progress_status_from_job_text("music_song", no_metadata, JOB_ID, "vi")
    assert "✅ Tạo bài hát" not in text


def test_music_failed_no_charge_panel_truthful_not_fake_green():
    job = _metadata_job(terminal="failed_no_charge")
    text = bot.product_progress_status_from_job_text("music_song", job, JOB_ID, "vi")
    assert "Chưa xử lý được lúc này, TOAN AAS chưa trừ Xu" in text
    assert "⚠️ Kiểm tra file nhạc" in text
    assert "✅ Gửi kết quả" not in text


def test_music_debug_shows_artifact_state_and_primary_blocker(monkeypatch):
    _install_job(monkeypatch, _metadata_job())
    text = bot.music_job_debug_text(JOB_ID)
    assert "artifact_state: <code>" in text
    assert "artifact_state: <code>ready</code>" not in text
    assert "artifact_ready: <code>no</code>" in text
    assert "primary_blocker: <code>artifact_zero_bytes</code>" in text
    assert "secondary_blocker: <code>scheduler_start_failed</code>" in text


def test_music_update_status_does_not_resubmit_or_duplicate_deliver(monkeypatch):
    _saves, provider_calls = _install_job(monkeypatch, _metadata_job())
    monkeypatch.setattr(bot, "MUSIC_AUTO_DELIVERY_ENABLED", True)
    fake = FakeBot()
    record = {
        "auto_delivery_enabled": True,
        "job_id": JOB_ID,
        "chat_id": str(USER_ID),
        "user_id": str(USER_ID),
        "lang": "vi",
    }
    first = asyncio.run(bot.music_auto_deliver_from_progress_record(_ctx(fake), record, bot.get_engine_async_job(JOB_ID)))
    second = asyncio.run(bot.music_auto_deliver_from_progress_record(_ctx(fake), record, bot.get_engine_async_job(JOB_ID)))
    assert provider_calls == []
    assert len(fake.audio) == 0
    assert first.get("terminal_state") != "delivered"
    assert second.get("terminal_state") != "delivered"
