import asyncio
import os
import subprocess
from types import SimpleNamespace

import pytest

import bot


PUBLIC_CODE = "257E5B0216"
JOB_ID = "257e5b0216b699877c2b"


def _current_branch_name() -> str:
    for key in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME", "BRANCH_NAME"):
        value = str(os.environ.get(key) or "").strip()
        if value:
            return value
    try:
        return subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
    except Exception:
        return ""


def _is_subdub_m6u_scope() -> bool:
    branch = _current_branch_name().lower()
    return bool("subdub" in branch and ("m6u" in branch or "input-save" in branch or "input_save" in branch))


class CaptureMessage:
    def __init__(self):
        self.texts = []

    async def reply_text(self, text, **kwargs):
        self.texts.append({"text": str(text), **kwargs})
        return SimpleNamespace(message_id=2601)


def _input_failed_job(**extra):
    job = {
        "feature": "subtitle_dub",
        "internal_job_id": JOB_ID,
        "job_id": JOB_ID,
        "public_code": PUBLIC_CODE,
        "mapped_product_type": "subtitle_dub",
        "mapped_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "product_type": "subtitle_dub",
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "status": "INPUT_SAVE_FAILED",
        "stage": "input_save",
        "terminal_state": "failed_no_charge",
        "progress_percent": 95,
        "input_save_attempted": True,
        "input_save_success": False,
        "input_save_blocker": "telegram_download_failed",
        "pipeline_blocker": "telegram_download_failed",
        "charge_status": "not_charged",
    }
    job.update(extra)
    return job


def test_input_save_failed_terminalizes_failed_no_charge():
    key = "p019m6u-input-save"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)

    stored = bot.update_subtitle_dub_pipeline_job(key, **_input_failed_job())

    assert stored["terminal_state"] == "failed_no_charge"
    assert stored["status"] == "failed_no_charge"
    assert stored["progress_stage"] == "input_save_failed"
    assert stored["progress_percent"] == 5
    assert stored["charge_status"] == "not_charged"


def test_telegram_download_failed_does_not_progress_to_95():
    job = bot.subdub_enrich_job_identity(_input_failed_job())
    state = bot.product_progress_status.product_progress_stage_from_job("subdub", job)

    assert job["progress_percent"] == 5
    assert state["percent"] == 5
    assert state["current_stage"] == "input_save_failed"


def test_input_save_failed_stops_before_asr_translation_tts_mux():
    job = bot.subdub_enrich_job_identity(_input_failed_job(asr_started=True, translation_started=True, tts_started=True, mux_started=True))

    assert job["pipeline_started"] is False
    assert job["asr_started"] is False
    assert job["translation_started"] is False
    assert job["tts_started"] is False
    assert job["mux_started"] is False
    assert job["delivery_attempted"] is False


def test_large_telegram_download_unsupported_edits_panel_to_terminal_failure():
    job = bot.subdub_enrich_job_identity(_input_failed_job(input_save_blocker="large_telegram_download_unsupported"))
    text = bot.product_progress_status_from_job_text("subdub", job, JOB_ID, "vi")
    public = bot.subdub_input_save_failure_public_text({"input_save_blocker": "large_telegram_download_unsupported"}, "vi")

    assert "chưa tải được video này vì file quá lớn hoặc Telegram chưa cho hệ thống tải trực tiếp" in public
    assert "5%" in text
    assert "chưa trừ Xu" in text
    assert job["status_panel_terminalized"] is True
    assert job["refresh_stopped_after_terminal"] is True


def test_refresh_after_input_save_failed_does_not_create_new_job():
    key = "p019m6u-refresh"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.update_subtitle_dub_pipeline_job(key, **_input_failed_job())
    before = len(bot.SUBTITLE_DUB_PIPELINE_JOBS)

    found = bot.subdub_progress_job_for_user("#" + PUBLIC_CODE.lower(), 0)
    after = len(bot.SUBTITLE_DUB_PIPELINE_JOBS)

    assert after == before
    assert found["job_key"] == key
    assert found["terminal_state"] == "failed_no_charge"


def test_progress_status_debug_recovers_subdub_input_save_failed_from_persisted_store(monkeypatch):
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    persisted = _input_failed_job()
    monkeypatch.setattr(bot, "get_engine_async_job", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(bot, "list_engine_async_jobs", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(bot, "subdub_engine_async_persisted_scan", lambda limit=240: [persisted])

    text = bot.product_progress_debug_text(PUBLIC_CODE)

    assert "Product: <code>subdub</code>" in text
    assert "recovered_from_persisted_subdub_job: <code>yes</code>" in text
    assert "input_save_blocker: <code>telegram_download_failed</code>" in text


def test_progress_status_debug_does_not_show_95_for_input_save_failed(monkeypatch):
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    monkeypatch.setattr(bot, "get_engine_async_job", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(bot, "list_engine_async_jobs", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(bot, "subdub_engine_async_persisted_scan", lambda limit=240: [_input_failed_job()])

    text = bot.product_progress_debug_text(PUBLIC_CODE)

    assert "Percent: <code>5%</code>" in text
    assert "persisted_job_progress: <code>5%</code>" in text
    assert "persisted_job_progress: <code>95%</code>" not in text


def test_subdub_job_debug_never_badrequest_for_input_save_failed_job():
    text = bot.subdub_job_debug_text(_input_failed_job(), PUBLIC_CODE)

    assert "SUBDUB JOB DEBUG" in text
    assert "SUBDUB DEBUG SAFE ERROR" not in text
    assert len(text) < 3600


def test_subdub_job_debug_includes_input_save_blocker_fields():
    text = bot.subdub_job_debug_text(_input_failed_job(), PUBLIC_CODE)

    assert "input_save_attempted: <code>yes</code>" in text
    assert "input_save_success: <code>no</code>" in text
    assert "input_save_blocker: <code>telegram_download_failed</code>" in text
    assert "telegram_download_failed: <code>yes</code>" in text
    assert "asr_started: <code>no</code>" in text
    assert "delivery_attempted: <code>no</code>" in text


def test_no_public_audio_fallback_for_video_products_still_enforced(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_PUBLIC_AUDIO_FALLBACK_ENABLED", False)
    message = CaptureMessage()

    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            audio_bytes=b"internal-audio",
            video_bytes=b"",
            include_subtitle_outputs=False,
        )
    )

    assert sent["audio"] == 0
    assert sent["partial_audio_delivered"] is False
    assert sent["audio_fallback_suppressed"] is True


def test_no_video_success_without_delivered_mp4_still_enforced():
    key = "p019m6u-no-video-success"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key, user_id=2606, chat_id=2606, mode=bot.VIDEO_SUBTITLE_MODE_DUB)

    ok = bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered")
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]

    assert ok is False
    assert stored["terminal_state"] == "failed_no_charge"
    assert stored["success_blocked_reason"] == "missing_valid_delivered_mp4"


def test_no_product_video_music_payos_pricing_db_changes():
    if not _is_subdub_m6u_scope():
        pytest.skip("SubDub M6U scope guard is enforced only on SubDub M6U/input-save branches.")
    output = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True)
    changed = {line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()}
    allowed = {
        "bot.py",
        "services/product_progress_status.py",
        "tests/test_p0_19m5a_subdub_large_telegram_media_input_save_fix.py",
        "tests/test_p0_19m6a_subdub_one_terminal_public_outcome_late_error_duplicate_fix.py",
        "tests/test_p0_19m6u_subdub_input_save_failed_terminalization_debug_progress_fix.py",
    }
    assert changed <= allowed
    disallowed = ("payos", "wallet", "pricing", "finance", "music", "suno", "video_provider", "remote_worker.py", "local_worker.py")
    assert not any(any(token in path.lower() for token in disallowed) for path in changed)
