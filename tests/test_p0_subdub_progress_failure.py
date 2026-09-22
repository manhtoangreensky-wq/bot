import pytest
import bot



def test_subtitle_plus_dub_should_not_suppress_failure_when_no_video_delivered():
    """Prove that a failed pipeline result is NEVER suppressed into an active progress panel."""
    incident_result = {
        "ok": False,
        "mode": "subtitle_plus_dub",
        "status": "NO_OUTPUT_BYTES",
        "last_error_stage": "audio",
        "progress_percent": 50,
        "lifecycle_state": "translating",
    }
    # Video delivery never succeeded, so public failure MUST NOT be suppressed into translating (50%)
    assert bot.subtitle_plus_dub_should_suppress_public_failure(incident_result, None) is False


def test_subdub_job_public_status_text_terminal_failure_precedence():
    """Prove FAILURE_RENDER_PRECEDENCE=PASS: terminal failure states must never render active progress."""
    incident_job = {
        "job_id": "8F01DD6E17",
        "internal_job_id": "8f01dd6e17c38e251fcf",
        "mode": "subtitle_plus_dub",
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "progress_stage": "audio",
        "progress_percent": 50,
        "last_error_stage": "audio",
        "last_error_safe": "TOAN AAS\n❌ Chưa thể tạo kết quả.\n⚠️ Không thể xử lý lúc này. Hệ thống chưa trừ Xu.",
    }
    text = bot.subdub_job_public_status_text(incident_job, "vi")
    assert "Tiến độ: 50%" not in text
    assert "Dịch nội dung" not in text
    assert "Chưa thể tạo kết quả" in text or "chưa trừ Xu" in text

    # Also for needs_admin_review
    admin_job = {
        "job_id": "8F01DD6E17",
        "status": "needs_admin_review",
        "terminal_state": "needs_admin_review",
        "progress_stage": "translating",
        "progress_percent": 50,
    }
    text_admin = bot.subdub_job_public_status_text(admin_job, "vi")
    assert "Tiến độ: 50%" not in text_admin


def test_subdub_progress_text_never_renders_active_progress_for_terminal_failure():
    """Prove TERMINAL_FAILURE_ACTIVE_PROGRESS=0: calling subdub_progress_text with failure stage returns clean failure."""
    for fail_stage in ("failed_no_charge", "failed_refunded", "needs_admin_review", "input_save_failed"):
        text = bot.subdub_progress_text(fail_stage, "8F01DD6E17", "vi")
        assert "Tiến độ:" not in text
        assert "0% 🟩" not in text


def test_subdub_unknown_stage_forward_jump_zero():
    """Prove UNKNOWN_STAGE_FORWARD_JUMP=0: unknown stage like 'audio' defaults to 0 or 5, never jumps forward."""
    payload = bot.subdub_progress_stage_payload("audio")
    assert payload["percent"] <= 5

class CaptureMessage:
    def __init__(self, chat_id=7714990570):
        self.chat_id = chat_id
        self.texts = []
        self.edited_texts = []

    async def reply_text(self, text, **kwargs):
        self.texts.append(str(text))
        from types import SimpleNamespace
        return SimpleNamespace(message_id=100 + len(self.texts), chat_id=self.chat_id)

    async def edit_message_text(self, text, **kwargs):
        self.edited_texts.append(str(text))
        from types import SimpleNamespace
        return SimpleNamespace(message_id=28874, chat_id=self.chat_id)


def test_first_failure_not_suppressed_by_terminal_outcome_type_alone():
    """Case A: Classified failure but not publicly emitted must NOT be prematurely suppressed."""
    import asyncio
    key = "7714990570|test_premature_suppression"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)

    # State matching incident: classified failure in debug_job, but no public emission yet
    bot.SUBTITLE_DUB_PIPELINE_JOBS[key] = {
        "job_key": key,
        "user_id": 7714990570,
        "chat_id": 7714990570,
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "status": "failed",
        "terminal_state": "failed_no_charge",
        "terminal_public_outcome_type": "failure",
        "terminal_public_outcome_sent": False,
        "terminal_public_outcome_message_id": "",
        "public_error_sent": False,
        "public_error_sent_count": 0,
        "progress_stage": "translating_subtitle",
        "progress_percent": 50,
        "status_panel_message_id": "28874",
        "charged_xu": 0,
    }

    message = CaptureMessage(chat_id=7714990570)
    result = asyncio.run(
        bot.send_subdub_fail_once(
            message,
            key,
            mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            reason="subdub_failed",
            terminalize_active=True,
        )
    )

    # Under buggy code, result['sent'] is False, result['suppressed'] is True, reason='already_failed'
    assert result["sent"] is True
    assert result["suppressed"] is False
    assert (len(message.texts) + len(message.edited_texts)) == 1
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    assert stored["public_error_sent_count"] == 1
    assert stored["public_error_sent"] is True
    assert stored["terminal_public_outcome_sent"] is True
    assert stored["charged_xu"] == 0


def test_duplicate_failure_suppressed_after_public_emission():
    """Case B: Once actual failure is publicly emitted, subsequent calls are deduplicated."""
    import asyncio
    key = "7714990570|test_dedup_failure"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)

    bot.SUBTITLE_DUB_PIPELINE_JOBS[key] = {
        "job_key": key,
        "user_id": 7714990570,
        "chat_id": 7714990570,
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "status": "failed",
        "terminal_state": "failed_no_charge",
        "terminal_public_outcome_type": "failure",
        "terminal_public_outcome_sent": True,
        "terminal_public_outcome_message_id": "28870",
        "public_error_sent": True,
        "public_error_sent_count": 1,
        "progress_stage": "failed_no_charge",
        "progress_percent": 5,
        "charged_xu": 0,
    }

    message = CaptureMessage(chat_id=7714990570)
    result = asyncio.run(
        bot.send_subdub_fail_once(
            message,
            key,
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            reason="subdub_failed_again",
            terminalize_active=True,
        )
    )

    assert result["sent"] is False
    assert result["suppressed"] is True
    assert result["reason"] == "already_failed"
    assert len(message.texts) == 0
    assert len(message.edited_texts) == 0
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    assert stored["public_error_sent_count"] == 1
    assert stored["charged_xu"] == 0


def test_late_failure_suppressed_after_delivered_success():
    """Case C: Existing late-failure suppression after delivered success remains intact."""
    import asyncio
    key = "7714990570|test_success_wins"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)

    bot.SUBTITLE_DUB_PIPELINE_JOBS[key] = {
        "job_key": key,
        "user_id": 7714990570,
        "chat_id": 7714990570,
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "status": "completed",
        "terminal_state": "delivered",
        "terminal_public_outcome_type": "success",
        "terminal_public_outcome_sent": True,
        "video_delivery_message_id": "9999",
        "output_sent": True,
        "delivery_succeeded": True,
        "progress_stage": "delivered",
        "progress_percent": 100,
    }

    message = CaptureMessage(chat_id=7714990570)
    result = asyncio.run(
        bot.send_subdub_fail_once(
            message,
            key,
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            reason="late_render_glitch",
            terminalize_active=False,
        )
    )

    assert result["sent"] is False
    assert result["suppressed"] is True
    assert len(message.texts) == 0
    assert len(message.edited_texts) == 0
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    assert stored["terminal_state"] == "delivered"
    assert stored["terminal_public_outcome_type"] == "success"
