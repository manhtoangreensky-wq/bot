import asyncio
from types import SimpleNamespace

import bot


AUDIO_BYTES = b"ID3-toan-aas-ready-music-artifact" * 200
LEGACY_ID = "MUS-91054179"
PLAIN_ID = "MUS91054179"
USER_ID = 230501


class FakeBot:
    def __init__(self, *, fail_audio=False, missing_message_id=False):
        self.audio = []
        self.messages = []
        self.edits = []
        self.fail_audio = fail_audio
        self.missing_message_id = missing_message_id

    async def send_audio(self, **kwargs):
        self.audio.append(kwargs)
        if self.fail_audio:
            raise RuntimeError("telegram down")
        message_id = "" if self.missing_message_id else 8000 + len(self.audio)
        return SimpleNamespace(message_id=message_id, audio=SimpleNamespace(file_id=f"audio-{len(self.audio)}"))

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)
        return SimpleNamespace(message_id=7000 + len(self.messages))

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


def _ready_job(job_id=LEGACY_ID, *, terminal_scheduler=False, delivered=False):
    job = {
        "internal_job_id": job_id,
        "feature": "music_suno",
        "product_type": "music_song",
        "music_product_type": "music_song",
        "music_product_mode": "song",
        "music_product_tier": "music_tier_standard",
        "user_id": str(USER_ID),
        "chat_id": str(USER_ID),
        "provider": "key4u_suno",
        "provider_task_id": "provider-ready-task",
        "provider_job_id": "provider-ready-task",
        "provider_submit_called": True,
        "provider_completed": True,
        "music_provider_completed": True,
        "status": "completed",
        "progress_percent": 85,
        "artifact_ready": True,
        "music_artifact_ready": True,
        "artifact_validated": True,
        "audio_validated": True,
        "music_audio_validated": True,
        "output_bytes": len(AUDIO_BYTES),
        "artifact_duration_seconds": 285,
        "duration_seconds": 285,
        "music_result_duration_seconds": 285,
        "_auto_delivery_audio_bytes": AUDIO_BYTES,
        "pending_charge_xu": 0,
        "charged_xu": 0,
    }
    if terminal_scheduler:
        job.update({
            "terminal_state": "failed_no_charge",
            "music_terminal_state": "failed_no_charge",
            "confirm_submit_blocker": "scheduler_start_failed",
            "auto_delivery_blocker": "scheduler_start_failed",
            "error_category": "scheduler_start_failed",
            "delivery_attempt_count": 0,
        })
    if delivered:
        job.update({
            "status": "delivered",
            "terminal_state": "delivered",
            "music_terminal_state": "delivered",
            "delivery_state": "delivered",
            "music_delivery_lock": "sent",
            "delivery_message_id": "8001",
            "music_delivery_message_id": "8001",
            "output_file_id": "audio-1",
        })
    return job


def _install_job(monkeypatch, job):
    _reset()
    bot.ENGINE_ASYNC_MEMORY_JOBS[str(job["internal_job_id"])] = dict(job)
    saves = []

    def fake_save(payload):
        current = dict(payload)
        bot.ENGINE_ASYNC_MEMORY_JOBS[str(current.get("internal_job_id") or "")] = current
        saves.append(current)
        return dict(current)

    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **_kwargs: {"vault_id": "MV-H4", "storage_ref": ""})
    monkeypatch.setattr(bot, "get_music_vault_entry", lambda _vault_id: {"vault_id": _vault_id, "storage_ref": ""})
    monkeypatch.setattr(bot, "mark_music_vault_status", lambda *args, **kwargs: {"vault_id": args[0] if args else "MV-H4"})
    monkeypatch.setattr(bot, "music_product_charge_after_delivery", lambda *args, **kwargs: {"ok": True, "charged_xu": 0})
    return saves


def test_music_debug_plain_id_finds_hyphen_legacy_job(monkeypatch):
    _install_job(monkeypatch, _ready_job(LEGACY_ID))
    text = bot.music_job_debug_text(PLAIN_ID)
    assert "lookup_found: <code>yes</code>" in text
    assert f"resolved_job_id: <code>{LEGACY_ID}</code>" in text
    assert f"canonical_job_id: <code>{PLAIN_ID}</code>" in text


def test_music_debug_hyphen_id_finds_same_job(monkeypatch):
    _install_job(monkeypatch, _ready_job(LEGACY_ID))
    plain = bot.get_engine_async_job_lookup(PLAIN_ID)
    hyphen = bot.get_engine_async_job_lookup(LEGACY_ID)
    assert plain["lookup_found"] is True
    assert hyphen["lookup_found"] is True
    assert plain["resolved_job_id"] == hyphen["resolved_job_id"] == LEGACY_ID


def test_music_id_lookup_does_not_truncate_last_digit():
    callback = bot.product_progress_status.product_progress_update_callback("music_song", PLAIN_ID)
    assert callback.endswith(PLAIN_ID)
    assert PLAIN_ID in callback


def test_music_callback_accepts_plain_and_hyphen_id(monkeypatch):
    _install_job(monkeypatch, _ready_job(LEGACY_ID))
    fake = FakeBot()
    asyncio.run(bot.handle_product_progress_callback(
        SimpleNamespace(callback_query=CaptureQuery(f"progress|status|music_song|{PLAIN_ID}")),
        _ctx(fake),
    ))
    assert len(fake.audio) == 1
    _install_job(monkeypatch, _ready_job(LEGACY_ID))
    fake = FakeBot()
    asyncio.run(bot.handle_product_progress_callback(
        SimpleNamespace(callback_query=CaptureQuery(f"progress|status|music_song|{LEGACY_ID}")),
        _ctx(fake),
    ))
    assert len(fake.audio) == 1


def test_scheduler_start_failed_does_not_terminal_fail_ready_artifact():
    _reset()
    updated = bot.mark_music_confirm_submit_blocker(_ready_job(PLAIN_ID), "scheduler_start_failed", "queue unavailable", persist=False)
    assert updated["terminal_state"] == ""
    assert updated["music_terminal_state"] == ""
    assert updated["auto_delivery_blocker"] == "scheduler_start_failed"


def test_ready_artifact_triggers_direct_delivery(monkeypatch):
    _install_job(monkeypatch, _ready_job(LEGACY_ID, terminal_scheduler=True))
    fake = FakeBot()
    result = asyncio.run(bot.deliver_music_ready_artifact_once(PLAIN_ID, context=_ctx(fake), user_id=USER_ID, source="unit_ready"))
    assert result["ok"] is True
    assert len(fake.audio) == 1
    assert result["job"]["terminal_state"] == "delivered"


def test_manual_status_update_delivers_ready_artifact(monkeypatch):
    _install_job(monkeypatch, _ready_job(LEGACY_ID, terminal_scheduler=True))
    fake = FakeBot()
    asyncio.run(bot.handle_product_progress_callback(
        SimpleNamespace(callback_query=CaptureQuery(f"progress|status|music_song|{PLAIN_ID}")),
        _ctx(fake),
    ))
    assert len(fake.audio) == 1


def test_music_delivery_recover_delivers_ready_artifact(monkeypatch):
    _install_job(monkeypatch, _ready_job(LEGACY_ID, terminal_scheduler=True))
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    fake = FakeBot()
    message = CaptureMessage(chat_id=999)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=999), message=message)
    asyncio.run(bot.cmd_music_delivery_recover(update, _ctx(fake, [PLAIN_ID])))
    assert len(fake.audio) == 1
    assert "lookup_found: <code>yes</code>" in message.outputs[-1]["text"]


def test_music_delivery_recover_noops_if_already_delivered(monkeypatch):
    _install_job(monkeypatch, _ready_job(LEGACY_ID, delivered=True))
    fake = FakeBot()
    result = asyncio.run(bot.deliver_music_ready_artifact_once(PLAIN_ID, context=_ctx(fake), user_id=USER_ID, source="unit_noop"))
    assert result["status"] == "ALREADY_DELIVERED"
    assert len(fake.audio) == 0


def test_music_delivery_recover_does_not_resubmit_provider(monkeypatch):
    _install_job(monkeypatch, _ready_job(LEGACY_ID, terminal_scheduler=True))
    poll_calls = []

    async def fake_poll(*args, **kwargs):
        poll_calls.append((args, kwargs))
        raise AssertionError("provider poll must not run for ready artifact recovery")

    monkeypatch.setattr(bot, "poll_music_suno_async_job", fake_poll)
    fake = FakeBot()
    asyncio.run(bot.deliver_music_ready_artifact_once(PLAIN_ID, context=_ctx(fake), user_id=USER_ID, source="unit_no_provider"))
    assert poll_calls == []
    assert len(fake.audio) == 1


def test_delivery_success_requires_telegram_message_id(monkeypatch):
    _install_job(monkeypatch, _ready_job(LEGACY_ID, terminal_scheduler=True))
    fake = FakeBot(missing_message_id=True)
    result = asyncio.run(bot.deliver_music_ready_artifact_once(PLAIN_ID, context=_ctx(fake), user_id=USER_ID, source="unit_missing_message_id"))
    assert result["ok"] is False
    assert result["status"] == "TELEGRAM_MESSAGE_ID_MISSING"
    assert result["job"]["terminal_state"] != "delivered"


def test_telegram_send_fail_keeps_retryable_state(monkeypatch):
    _install_job(monkeypatch, _ready_job(LEGACY_ID, terminal_scheduler=True))
    fake = FakeBot(fail_audio=True)
    result = asyncio.run(bot.deliver_music_ready_artifact_once(PLAIN_ID, context=_ctx(fake), user_id=USER_ID, source="unit_send_fail"))
    assert result["ok"] is False
    assert result["status"] == "SEND_FAILED"
    assert result["job"]["auto_delivery_blocker"] == "telegram_delivery_failed"
    assert result["job"]["terminal_state"] != "delivered"


def test_terminal_failed_scheduler_artifact_ready_is_recoverable(monkeypatch):
    job = _ready_job(LEGACY_ID, terminal_scheduler=True)
    assert bot.music_job_scheduler_artifact_recoverable(job) is True
    assert bot.music_job_terminal_failed(job) is False
    _install_job(monkeypatch, job)
    fake = FakeBot()
    result = asyncio.run(bot.deliver_music_ready_artifact_once(PLAIN_ID, context=_ctx(fake), user_id=USER_ID, source="unit_recoverable"))
    assert result["job"]["terminal_state"] == "delivered"


def test_no_duplicate_delivery_after_recovery(monkeypatch):
    _install_job(monkeypatch, _ready_job(LEGACY_ID, terminal_scheduler=True))
    fake = FakeBot()
    first = asyncio.run(bot.deliver_music_ready_artifact_once(PLAIN_ID, context=_ctx(fake), user_id=USER_ID, source="unit_first"))
    second = asyncio.run(bot.deliver_music_ready_artifact_once(LEGACY_ID, context=_ctx(fake), user_id=USER_ID, source="unit_second"))
    assert first["ok"] is True
    assert second["duplicate"] is True
    assert len(fake.audio) == 1


def test_debug_commands_read_only_except_recover_command(monkeypatch):
    _install_job(monkeypatch, _ready_job(LEGACY_ID, terminal_scheduler=True))
    before = dict(bot.get_engine_async_job(PLAIN_ID))
    text = bot.music_job_debug_text(PLAIN_ID)
    after = dict(bot.get_engine_async_job(PLAIN_ID))
    assert "lookup_found: <code>yes</code>" in text
    assert before.get("delivery_message_id") == after.get("delivery_message_id")
    fake = FakeBot()
    asyncio.run(bot.deliver_music_ready_artifact_once(PLAIN_ID, context=_ctx(fake), user_id=USER_ID, source="unit_recover"))
    assert len(fake.audio) == 1
