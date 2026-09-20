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
