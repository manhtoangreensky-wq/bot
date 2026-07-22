import asyncio
from types import SimpleNamespace

import pytest

import bot


MODES = (
    bot.VIDEO_SUBTITLE_MODE_CREATE,
    bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
    bot.VIDEO_SUBTITLE_MODE_DUB,
    bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
)


class _ReceiptMessage:
    def __init__(self):
        self.calls = []

    async def reply_text(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return SimpleNamespace(message_id=902)


class _PanelTimeoutQuery:
    def __init__(self, message):
        self.message = message

    async def edit_message_text(self, *_args, **_kwargs):
        raise TimeoutError("ReadTimeout while editing status panel")


def _seed_delivered_job(mode: str, key: str) -> dict:
    job = {
        "job_key": key,
        "job_id": "DUB-TERMINAL-1",
        "internal_job_id": "DUB-TERMINAL-1",
        "mode": mode,
        "mapped_mode": mode,
        "status": "running",
        "terminal_state": "",
        "lifecycle_state": "validating_output",
        "progress_stage": "validating_output",
        "progress_percent": 90,
        "completed_steps": bot.subdub_completed_steps_for_lifecycle("validating_output"),
        "video_delivery_message_id": "701",
        "delivery_message_id": "701",
        "delivery_success": True,
        "delivery_succeeded": True,
        "final_mp4_delivered": True,
        "output_validation": {"ok": True},
        "charged_xu": 0,
        "target_language": "Tiếng Việt",
    }
    bot.SUBTITLE_DUB_PIPELINE_JOBS[key] = job
    return job


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    monkeypatch.setattr(bot, "persist_subtitle_dub_pipeline_job_snapshot", lambda *_args, **_kwargs: True)
    yield
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()


@pytest.mark.parametrize("mode", MODES)
def test_real_video_delivery_survives_panel_timeout_and_sends_one_receipt(mode):
    key = f"terminal|{mode}"
    job = _seed_delivered_job(mode, key)
    result = bot.subdub_reconcile_delivered_video_result(
        mode,
        {"ok": False, "status": "LATE_UI_ERROR", "state": {"mode": mode}},
        job,
        {"mode": mode},
    )
    assert result["ok"] is True
    assert result["video_delivery_message_id"] == "701"

    bot.subdub_mark_delivered_terminal(key, result)
    message = _ReceiptMessage()
    query = _PanelTimeoutQuery(message)
    asyncio.run(bot.subdub_send_progress_update(query, key, "DUB-TERMINAL-1", "delivered", "vi"))
    receipt = bot.video_dubbing_receipt_text({"mode": mode}, result, "vi")
    sent = asyncio.run(bot.subdub_send_success_receipt_once(message, key, receipt))

    final_job = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    assert sent.message_id == 902
    assert final_job["terminal_state"] == "delivered"
    assert final_job["progress_percent"] == 100
    assert final_job["panel_final_percent"] == 100
    assert final_job["status_panel_terminalized"] is True
    assert final_job["receipt_sent_once"] is True
    assert final_job["subdub_success_message_id"] == "902"
    assert final_job["status_panel_edit_failed"] is True
    assert len(message.calls) == 1
    assert "Đã gửi video" in receipt

    duplicate = asyncio.run(bot.subdub_send_success_receipt_once(message, key, receipt))
    assert duplicate is None
    assert len(message.calls) == 1
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[key]["duplicate_receipt_prevented"] is True


@pytest.mark.parametrize("mode", MODES)
def test_terminal_contract_never_fakes_success_without_video_message_id(mode):
    key = f"no-delivery|{mode}"
    job = {
        "job_key": key,
        "mode": mode,
        "status": "running",
        "progress_percent": 90,
        "final_mp4_delivered": True,
        "delivery_success": True,
    }
    bot.SUBTITLE_DUB_PIPELINE_JOBS[key] = dict(job)
    original = {"ok": False, "status": "RENDER_FAILED", "state": {"mode": mode}}

    reconciled = bot.subdub_reconcile_delivered_video_result(mode, original, job, {"mode": mode})
    marked = bot.subdub_mark_delivered_terminal(key, reconciled)
    message = _ReceiptMessage()
    receipt = asyncio.run(bot.subdub_send_success_receipt_once(message, key, "receipt"))

    assert reconciled == original
    assert marked.get("progress_percent") == 90
    assert receipt is None
    assert message.calls == []


def test_delivered_panel_renders_every_public_step_green():
    text = bot.subdub_progress_text("delivered", "DUB-TERMINAL-1", "vi")
    expected_labels = [
        item["label"]
        for item in bot.product_progress_status.product_progress_spec("subdub")["steps"]
        if item["key"] != "delivered"
    ]
    for label in expected_labels:
        assert f"✅ {label}" in text
    assert "Tiến độ: 100%" in text
    assert "⌛" not in text
    assert "⬜" not in text


def test_receipt_timeout_does_not_downgrade_delivered_terminal_or_retry():
    key = "receipt-timeout|dub"
    _seed_delivered_job(bot.VIDEO_SUBTITLE_MODE_DUB, key)

    class _TimeoutMessage:
        def __init__(self):
            self.calls = 0

        async def reply_text(self, *_args, **_kwargs):
            self.calls += 1
            raise TimeoutError("ReadTimeout while sending receipt")

    message = _TimeoutMessage()
    sent = asyncio.run(bot.subdub_send_success_receipt_once(message, key, "receipt"))
    final_job = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]

    assert sent is None
    assert message.calls == 1
    assert final_job["delivery_succeeded"] is True
    assert final_job["final_mp4_delivered"] is True
    assert final_job["receipt_send_state"] == "unknown"
    assert final_job["receipt_send_uncertain"] is True
    assert final_job.get("public_failure_sent") is not True
