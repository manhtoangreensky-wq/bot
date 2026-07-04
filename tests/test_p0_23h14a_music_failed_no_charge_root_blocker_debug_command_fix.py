import asyncio
import inspect
from types import SimpleNamespace

import bot


JOB_ID = "MUS92943BAB"


class CaptureMessage:
    def __init__(self):
        self.outputs = []
        self.chat_id = 230714

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"text": text, **kwargs})
        return SimpleNamespace(chat_id=self.chat_id, message_id=len(self.outputs))


def _failed_job(**overrides):
    data = {
        "internal_job_id": JOB_ID,
        "feature": "music_suno",
        "product_type": "music_song",
        "user_id": "230714",
        "chat_id": "230714",
        "status": "failed",
        "terminal_state": "failed_no_charge",
        "music_terminal_state": "failed_no_charge",
        "stage": "received_request",
        "current_stage": "received_request",
        "progress_percent": 5,
        "pending_charge_xu": 0,
        "charged_xu": 0,
    }
    data.update(overrides)
    return data


def _install_job(monkeypatch, job):
    monkeypatch.setattr(bot, "get_engine_async_job", lambda job_id: dict(job) if str(job_id or "").replace("-", "") == JOB_ID else {})


def test_music_job_debug_never_generic_errors_for_admin(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: True)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: (_ for _ in ()).throw(RuntimeError("broken debug source")))
    update = SimpleNamespace(effective_user=SimpleNamespace(id=1), message=CaptureMessage())
    asyncio.run(bot.cmd_music_job_debug(update, SimpleNamespace(args=[JOB_ID])))
    text = update.message.outputs[-1]["text"]
    assert "music_debug_exception_type" in text
    assert "music_debug_exception_stage" in text
    assert "Có lỗi khi xử lý lệnh" not in text


def test_music_job_debug_shows_partial_data_for_failed_job(monkeypatch):
    _install_job(
        monkeypatch,
        _failed_job(
            primary_blocker="provider_submit_failed",
            fail_stage="provider_submit",
            fail_reason_safe="provider rejected",
            provider_submit_called=True,
        ),
    )
    text = bot.music_job_debug_text(JOB_ID)
    assert f"music_job_id: <code>{JOB_ID}</code>" in text
    assert "user_id_present: <code>yes</code>" in text
    assert "chat_id_present: <code>yes</code>" in text
    assert "terminal_state: <code>failed_no_charge</code>" in text
    assert "primary_blocker: <code>provider_submit_failed</code>" in text
    assert "fail_stage: <code>provider_submit</code>" in text
    assert "provider_submit_called: <code>yes</code>" in text


def test_music_failed_no_charge_requires_primary_blocker():
    normalized = bot.normalize_engine_async_job(
        {
            "internal_job_id": JOB_ID,
            "feature": "music_suno",
            "status": "failed",
            "terminal_state": "failed_no_charge",
            "music_terminal_state": "failed_no_charge",
        }
    )
    assert normalized["primary_blocker"] == bot.MUSIC_FAILED_NO_CHARGE_COMPAT_BLOCKER
    assert normalized["fail_stage"] == "unknown"


def test_music_failed_at_received_request_requires_fail_stage():
    failed = bot.mark_music_confirm_submit_blocker(
        {"internal_job_id": JOB_ID, "feature": "music_suno", "stage": "received_request"},
        "provider_submit_not_called",
        persist=False,
    )
    assert failed["terminal_state"] == "failed_no_charge"
    assert failed["primary_blocker"] == "provider_submit_not_called"
    assert failed["fail_stage"] == "provider_submit"


def test_progress_status_debug_shows_music_failure_blocker(monkeypatch):
    job = _failed_job(primary_blocker="music_provider_submit_not_called", fail_stage="provider_submit", provider_submit_called=False)
    _install_job(monkeypatch, job)
    text = bot.product_progress_debug_text(JOB_ID, "", job)
    assert "primary_blocker: <code>music_provider_submit_not_called</code>" in text
    assert "fail_stage: <code>provider_submit</code>" in text
    assert "provider_submit_called: <code>no</code>" in text


def test_music_failed_job_audit_fails_without_blocker(monkeypatch):
    _install_job(monkeypatch, _failed_job())
    text = bot.music_failed_job_audit_text(JOB_ID)
    assert "Status: <b>FAIL</b>" in text
    assert "primary_blocker present: <code>no</code>" in text


def test_music_failed_job_audit_passes_with_blocker(monkeypatch):
    _install_job(
        monkeypatch,
        _failed_job(
            primary_blocker="music_provider_submit_not_called",
            fail_stage="provider_submit",
            provider_submit_called=False,
            stopped_reason="failed_no_charge",
        ),
    )
    text = bot.music_failed_job_audit_text(JOB_ID)
    assert "Status: <b>PASS</b>" in text
    assert "provider_submit_called: <code>no</code>" in text
    assert "debug_command_safe: <code>yes</code>" in text


def test_terminal_failed_no_charge_records_provider_submit_called_false_before_submit():
    failed = bot.mark_music_confirm_submit_blocker(
        {"internal_job_id": JOB_ID, "feature": "music_suno"},
        "provider_submit_not_called",
        persist=False,
    )
    assert failed["provider_submit_called"] is False
    assert failed["fail_stage"] == "provider_submit"


def test_terminal_failed_no_charge_records_provider_submit_called_true_after_submit():
    failed = bot.mark_music_confirm_submit_blocker(
        {"internal_job_id": JOB_ID, "feature": "music_suno", "provider_submit_called": True},
        "provider_submit_failed",
        "provider rejected",
        persist=False,
    )
    assert failed["provider_submit_called"] is True
    assert failed["primary_blocker"] == "provider_submit_failed"


def test_music_delivery_recover_does_not_create_new_job(monkeypatch):
    calls = []
    _install_job(
        monkeypatch,
        _failed_job(
            primary_blocker="music_provider_submit_not_called",
            fail_stage="provider_submit",
            provider_submit_called=False,
        ),
    )
    monkeypatch.setattr(bot, "create_music_suno_async_job", lambda *args, **kwargs: calls.append("create"))
    monkeypatch.setattr(bot, "submit_music_generation_job", lambda *args, **kwargs: calls.append("submit"))
    monkeypatch.setattr(bot, "execute_engine", lambda *args, **kwargs: calls.append("execute"))
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: True)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=1), message=CaptureMessage())
    asyncio.run(bot.cmd_music_delivery_recover(update, SimpleNamespace(args=[JOB_ID])))
    assert calls == []
    assert "provider_submit_called: <code>no</code>" in update.message.outputs[-1]["text"]
    assert "cannot_recover_reason: <code>provider_submit_called=no</code>" in update.message.outputs[-1]["text"]


def test_public_music_error_copy_stays_clean():
    text = bot.music_confirm_submit_public_failure_text("vi")
    forbidden = ("provider", "api", "handler", "callback", "stacktrace", "runtimeerror", "payload", "token", "signed url")
    assert "chưa trừ Xu" in text
    assert not any(term in text.lower() for term in forbidden)


def test_no_payos_video_subdub_voice_pricing_changes():
    source = "\n".join(
        inspect.getsource(obj)
        for obj in (
            bot.ensure_music_failed_no_charge_metadata,
            bot.music_job_debug_text,
            bot.music_failed_job_audit_text,
            bot.cmd_music_failed_job_audit,
        )
    )
    forbidden = ("PayOS", "wallet", "VIDEO_", "SUBDUB", "VOICE_", "CANONICAL_PRICE")
    assert not any(term in source for term in forbidden)
