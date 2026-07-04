import asyncio
import os
import subprocess
from types import SimpleNamespace

import pytest

import bot


class CaptureMessage:
    def __init__(self):
        self.chat_id = 7070
        self.texts = []

    async def reply_text(self, text, **kwargs):
        self.texts.append(str(text))
        return SimpleNamespace(message_id=len(self.texts), chat_id=self.chat_id)


def _branch_name():
    for key in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME", "BRANCH_NAME"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    try:
        return subprocess.check_output(["git", "branch", "--show-current"], text=True, encoding="utf-8").strip()
    except Exception:
        return ""


def _is_m6_scope():
    branch = _branch_name().lower()
    return "p0-19m6" in branch or "subdub-one-terminal-public-outcome" in branch


def _fresh_job(key="p019m6a-job", *, stage="received_file"):
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    _, job = bot.acquire_subtitle_dub_pipeline_job(
        key,
        user_id=7070,
        chat_id=7070,
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        status_panel_message_id="panel-1",
    )
    if stage != "received_file":
        bot.update_subtitle_dub_pipeline_job(
            key,
            lifecycle_state=stage,
            current_stage=stage,
            progress_stage=stage,
            progress_percent=bot.subdub_progress_percent_for_lifecycle(stage),
        )
    return key, job


def test_success_after_delivery_suppresses_late_error():
    key, _job = _fresh_job("p019m6a-late-error")
    assert bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        video_delivery_message_id="777",
    )

    message = CaptureMessage()
    result = asyncio.run(
        bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_DUB, reason="late")
    )
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]

    assert result["suppressed"] is True
    assert message.texts == []
    assert stored["terminal_state"] == "delivered"
    assert stored["late_fail_suppressed"] is True
    assert stored["error_sent_after_delivery"] is False
    assert stored["terminal_public_outcome_type"] == "success"


def test_error_after_delivery_not_sent():
    key, _job = _fresh_job("p019m6a-error-after-delivery")
    bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered", delivery_message_id="888")

    message = CaptureMessage()
    asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, reason="boom"))

    assert message.texts == []
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[key]["public_error_sent"] is False
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[key]["duplicate_error_prevented"] is True


def test_public_error_then_success_not_both_sent():
    key, _job = _fresh_job("p019m6a-error-then-success")
    message = CaptureMessage()

    first = asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_DUB, reason="input_save"))
    second = bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered", video_delivery_message_id="999")
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]

    assert first["sent"] is True
    assert second is False
    assert len(message.texts) == 1
    assert stored["terminal_public_outcome_type"] == "failure"
    assert stored["success_after_error_prevented"] is True
    assert stored["output_sent"] is False


def test_duplicate_success_message_prevented():
    key, _job = _fresh_job("p019m6a-duplicate-success")

    assert bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        delivery_message_id="111",
        video_delivery_message_id="111",
    )
    assert bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered", delivery_message_id="222") is False

    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    assert stored["delivery_message_id"] == "111"
    assert stored["duplicate_success_prevented"] is True
    assert stored["success_sent_count"] == 1


def test_duplicate_generic_error_prevented():
    key, _job = _fresh_job("p019m6a-duplicate-error")
    message = CaptureMessage()

    first = asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_DUB, reason="fail-1"))
    second = asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_DUB, reason="fail-2"))
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]

    assert first["sent"] is True
    assert second["suppressed"] is True
    assert len(message.texts) == 1
    assert stored["public_error_sent_count"] == 1
    assert stored["duplicate_error_prevented"] is True
    assert "Có lỗi khi xử lý lệnh" not in message.texts[0]


def test_failed_before_delivery_sends_one_clean_failure():
    key, _job = _fresh_job("p019m6a-clean-failure")
    message = CaptureMessage()

    result = asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE, reason="asr_empty"))
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]

    assert result["sent"] is True
    assert stored["terminal_state"] == "failed_no_charge"
    assert stored["charge_status"] == "not_charged"
    assert stored["terminal_public_outcome_type"] == "failure"
    assert stored["status_panel_terminalized"] is True
    assert stored["refresh_stopped_after_terminal"] is True
    assert "Hệ thống chưa trừ Xu" in message.texts[0]


def test_refresh_after_terminal_does_not_create_new_job():
    key, job = _fresh_job("p019m6a-refresh-terminal")
    message = CaptureMessage()
    asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE, reason="input_save"))

    before = len(bot.SUBTITLE_DUB_PIPELINE_JOBS)
    found = bot.subdub_progress_job_for_user("#" + job["job_id"].lower(), 7070)
    after = len(bot.SUBTITLE_DUB_PIPELINE_JOBS)

    assert after == before
    assert found["job_key"] == key
    assert found["terminal_state"] == "failed_no_charge"


def test_terminal_public_outcome_debug_fields_present():
    text = bot.subtitle_dub_debug_text(
        {
            "job_id": "M6DEBUG",
            "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
            "status": "completed",
            "terminal_state": "delivered",
            "terminal_public_outcome_sent": True,
            "terminal_public_outcome_type": "success",
            "terminal_public_outcome_message_id": "456",
            "public_error_sent_count": 0,
            "success_sent_count": 1,
            "late_fail_suppressed": True,
            "duplicate_success_prevented": True,
            "duplicate_error_prevented": True,
            "output_validated_before_success": True,
            "delivery_confirmed_before_success": True,
            "validation_started": True,
            "validation_passed": True,
            "delivery_started": True,
            "delivery_success": True,
            "panel_finalized": True,
            "panel_final_percent": 100,
            "charge_after_delivery": True,
            "success_cost_line": "Chi phí: <b>12 Xu</b>",
            "cost_line_rendered": True,
            "cost_line_reason": "after_delivery",
        }
    )

    assert "terminal public outcome sent" in text
    assert "duplicate success prevented" in text
    assert "duplicate error prevented" in text
    assert "delivery confirmed before success" in text
    assert "panel final percent" in text
    assert "success cost line" in text


def test_no_charge_before_delivery():
    key, _job = _fresh_job("p019m6a-no-charge")
    message = CaptureMessage()
    asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_DUB, reason="delivery_failed"))
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]

    assert stored["charge_status"] == "not_charged"
    assert stored["charge_after_delivery"] is False
    assert stored["cost_line_rendered"] is False
    assert "Chi phí:" not in message.texts[0]


def test_success_cost_line_no_trailing_comma_for_zero_xu():
    text = bot.video_dubbing_receipt_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_DUB},
        {"video_delivered": True, "charged": 0, "terminal_state": "delivered"},
    )

    assert "Chi phí: <b>0 Xu</b>" in text
    assert "Xu," not in text


def test_failed_no_charge_has_no_success_cost_line():
    text = bot.video_dubbing_receipt_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "public_error_sent": True, "terminal_public_outcome_type": "failure"},
        {"ok": False, "charged": 0},
    )

    assert "Đã tạo video" not in text
    assert "Chi phí:" not in text
    assert "Hệ thống chưa trừ Xu" in text


def test_90_percent_validation_success_delivery_success_finalizes_100():
    key, _job = _fresh_job("p019m6a-90-success", stage="validating_output")

    assert bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered", video_delivery_message_id="9090")
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]

    assert stored["progress_percent"] == 100
    assert stored["panel_finalized"] is True
    assert stored["panel_final_percent"] == 100
    assert stored["validation_passed"] is True
    assert stored["delivery_success"] is True


def test_90_percent_validation_fail_finalizes_failed_no_charge():
    key, _job = _fresh_job("p019m6a-90-validation-fail", stage="validating_output")
    message = CaptureMessage()

    asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_DUB, reason="validation_failed"))
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]

    assert stored["terminal_state"] == "failed_no_charge"
    assert stored["panel_finalized"] is True
    assert stored["panel_final_percent"] == 95
    assert stored["validation_started"] is True
    assert stored["validation_passed"] is False
    assert "Có lỗi khi xử lý lệnh" not in message.texts[0]


def test_90_percent_delivery_fail_finalizes_failed_no_charge():
    key, _job = _fresh_job("p019m6a-90-delivery-fail", stage="delivering")
    bot.update_subtitle_dub_pipeline_job(key, delivery_attempted=True)
    message = CaptureMessage()

    asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_DUB, reason="delivery_failed"))
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]

    assert stored["terminal_state"] == "failed_no_charge"
    assert stored["delivery_started"] is True
    assert stored["delivery_success"] is False
    assert stored["status_panel_terminalized"] is True


def test_no_product_video_music_payos_pricing_db_changes():
    if not _is_m6_scope():
        pytest.skip("SubDub M6 scope guard is not active for this branch")

    output = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True)
    changed = {line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()}
    allowed = {
        "bot.py",
        "services/product_progress_status.py",
        "tests/test_p0_17b_subtitle_translation_dubbing.py",
        "tests/test_p0_17b12_2_live_hotfix_contract.py",
        "tests/test_p0_17b6_2_final_product_pipeline.py",
        "tests/test_p0_18q_video_ui_polish_back_routing_5_option_buttons.py",
        "tests/test_p0_19b3_subtitle_dub_clean_product_ux_two_path_flow.py",
        "tests/test_p0_19b7_restore_pr38_subtitle_dub_engine_no_subtitle_branch.py",
        "tests/test_p0_19d_live_subtitle_dub_blackbox_engine_fix_only.py",
        "tests/test_p0_19g_professional_subtitle_dub_overlay_voice_delivery.py",
        "tests/test_p0_19h_restore_subdub_engine_professional_status.py",
        "tests/test_p0_19j_restore_subdub_real_video_engine_delivery.py",
        "tests/test_p0_19m5_complete_subdub_status_style_dub_voice_audio_delivery_sync.py",
        "tests/test_p0_19m5a_subdub_large_telegram_media_input_save_fix.py",
        "tests/test_p0_19m5c_subdub_mode_route_female_voice_state_fix.py",
        "tests/test_p0_19m6a_subdub_one_terminal_public_outcome_late_error_duplicate_fix.py",
        "tests/test_p0_19m6r_subdub_live_runtime_terminal_outcome_path_fix.py",
        "tests/test_p0_19m6s_subdub_live_job_registry_partial_audio_debug_fix.py",
        "tests/test_p0_19m6t_subdub_final_video_only_delivery_no_public_audio_fallback.py",
        "tests/test_p0_19m6u_subdub_input_save_failed_terminalization_debug_progress_fix.py",
        "tests/test_p0_19m6v_subdub_final_delivery_report_font2x_female_voice_fix.py",
        "tests/test_p0_19n_subdub_original_voice_retention_volume_mix_controls.py",
        "tests/test_p0_19m8r_selective_rollback_subdub_m8_keep_international_subtitle_only.py",
        "tests/test_task2_1_translation_product_logic_cleanup.py",
        "tests/test_task2_4_public_product_screens.py",
        "tests/test_task2_5_user_ux_confirmation_cleanup.py",
    }
    assert changed <= allowed
    disallowed = ("payos", "wallet", "pricing", "finance", "music", "suno", "video_provider", "remote_worker.py", "local_worker.py")
    assert not any(any(token in path.lower() for token in disallowed) for path in changed)
