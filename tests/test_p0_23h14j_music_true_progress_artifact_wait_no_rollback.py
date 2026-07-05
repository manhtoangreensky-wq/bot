import subprocess
from pathlib import Path

import bot
from services import product_progress_status


JOB_ID = "MUSH14JTRUE"
TASK_ID = "1279444349692403713"
RAW_AUDIO_URL = "https://cdn1.suno.ai/h14j-live.mp3"


def _job(**overrides):
    data = {
        "internal_job_id": JOB_ID,
        "job_id": JOB_ID,
        "feature": "music_suno",
        "product_type": "music_song",
        "music_product_type": "music_song",
        "user_id": "232914",
        "chat_id": "232914",
        "persist_helper_called": True,
        "provider": "key4u_suno",
        "provider_name_internal": "key4u_suno",
        "provider_task_id": TASK_ID,
        "provider_job_id": TASK_ID,
        "provider_submit_called": True,
        "status": "processing",
        "progress_percent": 65,
        "provider_lyrics": "[Verse]\nTOAN AAS test",
        "provider_style_prompt": "Vietnamese pop",
        "charged_xu": 0,
        "charge_status": "pending_no_charge",
    }
    data.update(overrides)
    return data


def test_music_progress_never_rolls_back_85_to_5():
    state = product_progress_status.product_progress_stage_from_job(
        "music_song",
        _job(
            status="failed",
            terminal_state="failed_no_charge",
            progress_percent=85,
            provider_completed=True,
            provider_status="completed",
            primary_blocker="artifact_not_ready",
        ),
    )

    assert state["current_stage"] == "validating_audio"
    assert state["percent"] >= 85
    assert state["terminal_state"] == ""
    assert state["progress_rollback_prevented"] is False


def test_music_does_not_show_85_before_artifact_check_started():
    state = product_progress_status.product_progress_stage_from_job(
        "music_song",
        _job(status="processing", progress_percent=95, provider_completed=False),
    )

    assert state["current_stage"] == "generating_song"
    assert 50 <= state["percent"] <= 75
    assert state["artifact_check_stage_allowed"] is False


def test_provider_generating_uses_50_to_75_progress_range():
    state = product_progress_status.product_progress_stage_from_job(
        "music_song",
        _job(status="running", progress_percent=5, provider_completed=False),
    )

    assert state["current_stage"] == "generating_song"
    assert 50 <= state["percent"] <= 75
    assert state["progress_source"] == "provider_generating"


def test_artifact_waiting_keeps_processing_not_failed_no_charge():
    state = product_progress_status.product_progress_stage_from_job(
        "music_song",
        _job(
            status="failed",
            terminal_state="failed_no_charge",
            progress_percent=85,
            provider_completed=True,
            artifact_waiting=True,
            music_artifact_waiting=True,
            final_audio_download_status="PENDING",
            primary_blocker="artifact_not_ready",
        ),
    )

    assert state["terminal_state"] == ""
    assert state["artifact_waiting"] is True
    assert state["terminal_fail_allowed"] is False
    assert 80 <= state["percent"] <= 90


def test_artifact_waiting_schedules_retry():
    state = product_progress_status.product_progress_stage_from_job(
        "music_song",
        _job(
            provider_completed=True,
            artifact_waiting=True,
            artifact_wait_attempt_count=2,
            artifact_wait_max_attempts=8,
            next_artifact_retry_at="2026-07-05T20:00:00+07:00",
            primary_blocker="artifact_not_ready",
            progress_percent=85,
        ),
    )

    assert state["artifact_wait_attempt_count"] == 2
    assert state["artifact_wait_max_attempts"] == 8
    assert state["next_artifact_retry_at"]
    assert state["terminal_state"] == ""


def test_failed_no_charge_only_after_artifact_wait_exhausted():
    state = product_progress_status.product_progress_stage_from_job(
        "music_song",
        _job(
            status="failed",
            terminal_state="failed_no_charge",
            provider_completed=True,
            progress_percent=85,
            terminal_after_wait_exhausted=True,
            artifact_wait_terminal_exhausted=True,
            artifact_wait_attempt_count=8,
            artifact_wait_max_attempts=8,
            primary_blocker="artifact_materialization_failed",
        ),
    )

    assert state["terminal_state"] == "failed_no_charge"
    assert state["terminal_fail_allowed"] is True
    assert state["percent"] >= 85


def test_pr173_direct_get_path_debug_fields_present(monkeypatch):
    job = _job(
        status="completed",
        provider_completed=True,
        progress_percent=85,
        music_output_url=RAW_AUDIO_URL,
        pr173_artifact_engine_restored=True,
        direct_audio_url_get_attempted=True,
        provider_download_endpoint_bypassed_for_raw_audio=True,
        provider_download_bytes=83,
    )
    lookup = {"job": job, "lookup_found": True, "canonical_job_id": JOB_ID, "resolved_job_id": JOB_ID}
    monkeypatch.setattr(bot, "get_engine_async_job_lookup", lambda _job_id: lookup)

    text = bot.music_job_debug_text(JOB_ID)

    assert "pr173_artifact_engine_restored" in text
    assert "direct_audio_url_get_attempted" in text
    assert "provider_download_endpoint_bypassed_for_raw_audio" in text


def test_provider_download_json_83_bytes_does_not_override_raw_audio(monkeypatch):
    job = _job(
        status="completed",
        provider_completed=True,
        music_output_url=RAW_AUDIO_URL,
        pr173_artifact_engine_restored=True,
        direct_audio_url_get_attempted=True,
        provider_download_endpoint_bypassed_for_raw_audio=True,
        provider_download_bytes=83,
        download_strategy_used="direct_cdn",
    )
    lookup = {"job": job, "lookup_found": True, "canonical_job_id": JOB_ID, "resolved_job_id": JOB_ID}
    monkeypatch.setattr(bot, "get_engine_async_job_lookup", lambda _job_id: lookup)

    text = bot.music_job_debug_text(JOB_ID)

    assert "provider_download_json_83_bytes_ignored" in text
    assert "direct_cdn" in text


def test_progress_status_top_percent_equals_final_reconciled_percent():
    job = _job(provider_completed=True, artifact_waiting=True, progress_percent=85, primary_blocker="artifact_not_ready")
    state = product_progress_status.product_progress_stage_from_job("music_song", job)
    text = bot.product_progress_status_from_job_text("music_song", job, JOB_ID, "vi")

    assert state["percent"] == state["final_progress_after_reconcile"]
    assert f"Tiến độ: {state['percent']}%" in text


def test_public_copy_waiting_no_debug_terms():
    job = _job(
        provider_completed=True,
        artifact_waiting=True,
        progress_percent=85,
        primary_blocker="artifact_not_ready",
        music_output_url=RAW_AUDIO_URL,
    )
    text = bot.product_progress_status_from_job_text("music_song", job, JOB_ID, "vi").lower()

    for forbidden in ("provider", "api", "debug", "key4u", "suno", "traceback"):
        assert forbidden not in text
    assert "đang chuẩn bị file nhạc" in text


def test_music_debug_no_generic_x_for_artifact_waiting_job(monkeypatch):
    job = _job(
        status="failed",
        terminal_state="failed_no_charge",
        provider_completed=True,
        artifact_waiting=True,
        progress_percent=85,
        primary_blocker="artifact_not_ready",
    )
    lookup = {"job": job, "lookup_found": True, "canonical_job_id": JOB_ID, "resolved_job_id": JOB_ID}
    monkeypatch.setattr(bot, "get_engine_async_job_lookup", lambda _job_id: lookup)

    text = bot.music_job_debug_text(JOB_ID)

    assert "generic" not in text.lower()
    assert "progress_source" in text
    assert "artifact_waiting" in text


def test_no_product_video_subdub_payos_pricing_db_changes():
    repo = Path(__file__).resolve().parents[1]
    changed = subprocess.check_output(
        [
            "git",
            "-c",
            f"safe.directory={repo.as_posix()}",
            "diff",
            "--name-only",
            "origin/main",
        ],
        cwd=repo,
        text=True,
    ).splitlines()
    forbidden_prefixes = (
        "providers/video",
        "services/video",
        "services/subdub",
        "services/payos",
        "services/wallet",
        "services/pricing",
        "migrations/",
        "web/",
    )
    forbidden_exact = {
        "local_worker.py",
        "remote_worker.py",
        "providers/key4u_provider.py",
    }
    assert not [
        path
        for path in changed
        if path in forbidden_exact or any(path.startswith(prefix) for prefix in forbidden_prefixes)
    ]
