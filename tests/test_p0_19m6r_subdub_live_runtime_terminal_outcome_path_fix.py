import asyncio
import os
import subprocess
from types import SimpleNamespace

import pytest

import bot


GENERIC_ERROR = "Có lỗi khi xử lý lệnh. Bot chưa trừ Xu"


class CaptureBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)
        return SimpleNamespace(message_id=len(self.messages), chat_id=kwargs.get("chat_id"))


class CaptureMessage:
    def __init__(self, chat_id=19060):
        self.chat_id = chat_id
        self.texts = []

    async def reply_text(self, text, **kwargs):
        self.texts.append(str(text))
        return SimpleNamespace(message_id=len(self.texts), chat_id=self.chat_id)


def _branch_name():
    for key in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME", "BRANCH_NAME"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return subprocess.check_output(["git", "branch", "--show-current"], text=True, encoding="utf-8").strip()


def _is_m6r_scope():
    branch = _branch_name().lower()
    return "p0-19m6r" in branch or "runtime-terminal-outcome" in branch


def _fresh_job(key="p019m6r-job", *, user_id=19060, stage="received_file"):
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    acquired, job = bot.acquire_subtitle_dub_pipeline_job(
        key,
        user_id=user_id,
        chat_id=user_id,
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        status_panel_message_id="panel-1",
    )
    assert acquired is True
    if stage != "received_file":
        bot.update_subtitle_dub_pipeline_job(
            key,
            lifecycle_state=stage,
            current_stage=stage,
            progress_stage=stage,
            progress_percent=bot.subdub_progress_percent_for_lifecycle(stage),
        )
        job = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    return key, job


def _update(monkeypatch, *, callback="", text="", user_id=19060):
    monkeypatch.setattr(bot, "Update", SimpleNamespace)
    message = SimpleNamespace(text=text, chat_id=user_id)
    query = SimpleNamespace(data=callback) if callback else None
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(id=user_id),
        effective_message=message,
        callback_query=query,
    )


def _context(fake_bot, error):
    return SimpleNamespace(error=error, bot=fake_bot, chat_data={})


def test_generic_outer_exception_does_not_send_public_error_after_subdub_success(monkeypatch):
    key, job = _fresh_job("p019m6r-success-late-error")
    assert bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered", video_delivery_message_id="777")
    fake = CaptureBot()

    update = _update(monkeypatch, callback=f"videodub|subdub_status|{job['job_id']}")
    asyncio.run(bot.on_telegram_error(update, _context(fake, RuntimeError("late callback error"))))

    assert fake.messages == []
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    assert stored["late_fail_suppressed"] is True
    assert stored["error_sent_after_delivery"] is False


def test_status_panel_edit_failure_does_not_send_generic_job_failure(monkeypatch):
    key, job = _fresh_job("p019m6r-status-panel", stage="transcribing")
    fake = CaptureBot()

    update = _update(monkeypatch, callback=f"videodub|subdub_status|{job['job_id']}")
    asyncio.run(bot.on_telegram_error(update, _context(fake, RuntimeError("Message is not modified"))))

    assert fake.messages == []
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    assert stored["status_panel_edit_failed"] is True
    assert stored["public_panel_update_failed_nonterminal"] is True
    assert stored["terminal_state"] == ""


def test_result_delivery_success_then_late_exception_suppressed(monkeypatch):
    key, job = _fresh_job("p019m6r-delivery-late")
    bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        delivery_message_id="888",
        video_delivery_message_id="888",
    )
    fake = CaptureBot()

    update = _update(monkeypatch, callback=f"videodub|download_final_video|{job['job_id']}")
    asyncio.run(bot.on_telegram_error(update, _context(fake, RuntimeError("reply markup update failed"))))

    assert fake.messages == []
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[key]["ignored_late_error_count"] >= 1


def test_public_failure_then_success_message_prevented():
    key, _job = _fresh_job("p019m6r-failure-then-success")
    message = CaptureMessage()

    first = asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_DUB, reason="known_blocker"))
    second = bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered", video_delivery_message_id="999")

    assert first["sent"] is True
    assert second is False
    assert len(message.texts) == 1
    assert GENERIC_ERROR not in message.texts[0]
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[key]["success_after_error_prevented"] is True


def test_old_success_copy_path_routes_through_terminal_guard():
    text = bot.video_dubbing_receipt_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "public_error_sent": True, "terminal_public_outcome_type": "failure"},
        {"ok": True, "video_delivered": True, "charged": 0, "public_error_sent_count": 1},
    )

    assert "Đã tạo video lồng tiếng" in text
    assert "Trạng thái: <b>Đã gửi video</b>" in text
    assert "Hệ thống chưa trừ Xu" not in text


def test_success_cost_line_from_live_path_no_duplicate_no_trailing_comma():
    text = bot.video_dubbing_receipt_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_DUB},
        {"video_delivered": True, "charged": 0, "terminal_state": "delivered", "sent_video": 1},
    )

    assert text.count("Chi phí:") == 1
    assert "Chi phí: <b>0 Xu</b>" in text
    assert "Xu," not in text


def test_early_failure_is_suppressed_from_public_subdub_runtime(monkeypatch):
    key, _job = _fresh_job("p019m6r-early-runtime-fail", stage="transcribing")
    fake = CaptureBot()

    update = _update(monkeypatch, callback="videodub|confirm_dub")
    asyncio.run(bot.on_telegram_error(update, _context(fake, RuntimeError("unexpected runtime fail"))))

    assert fake.messages == []
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    assert stored["generic_fail_suppressed_while_active_or_delivered"] is True
    assert stored["public_error_sent"] is False
    assert stored["public_failure_sent"] is False


def test_subdub_job_debug_lookup_by_uppercase_public_code():
    key, job = _fresh_job("p019m6r-uppercase-lookup")
    public_code = bot.product_progress_status.product_progress_public_job_code(job["job_id"]).lstrip("#").upper()

    found = bot.subtitle_dub_debug_lookup_job(public_code)

    assert found["job_key"] == key
    assert found["lookup_store_hit"] in {"subtitle_dub_memory", "engine_async_direct", "engine_async_feature_index", "engine_async_persisted_scan"}


def test_subdub_job_debug_never_generic_fails_for_missing_job(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    message = CaptureMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=1), message=message)
    context = SimpleNamespace(args=["MISSINGJOB"])

    asyncio.run(bot.cmd_subdub_job_debug(update, context))

    assert len(message.texts) == 1
    assert "job_lookup_missing" in message.texts[0]
    assert GENERIC_ERROR not in message.texts[0]


def test_subdub_job_debug_checks_persisted_store_not_memory_only(monkeypatch):
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    persisted_job = {
        "feature": "subtitle_dub",
        "internal_job_id": "SDUB-PERSISTED",
        "job_id": "FCBA0E1FC4-PERSISTED",
        "status": "completed",
        "terminal_state": "delivered",
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
    }
    monkeypatch.setattr(bot, "list_engine_async_jobs", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(bot, "get_engine_async_job", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(bot, "subdub_engine_async_persisted_scan", lambda limit=240: [persisted_job])

    found = bot.subtitle_dub_debug_lookup_job("FCBA0E1FC4")

    assert found["internal_job_id"] == "SDUB-PERSISTED"
    assert found["lookup_store_hit"] == "engine_async_persisted_scan"


def test_no_product_video_music_payos_pricing_db_changes():
    if not _is_m6r_scope():
        pytest.skip("SubDub M6R scope guard is not active for this branch")

    output = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True)
    changed = {line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()}
    allowed = {
        "bot.py",
        "tests/test_p0_19m6a_subdub_one_terminal_public_outcome_late_error_duplicate_fix.py",
        "tests/test_p0_19m6r_subdub_live_runtime_terminal_outcome_path_fix.py",
    }
    assert changed <= allowed
    disallowed = ("payos", "wallet", "pricing", "finance", "music", "suno", "video_provider", "remote_worker.py", "local_worker.py")
    assert not any(any(token in path.lower() for token in disallowed) for path in changed)
