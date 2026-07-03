import inspect
import os
import subprocess

import pytest

import bot


def _job_key(name: str) -> str:
    return f"p019m4b-{name}"


def _clear_job(key: str) -> None:
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)


def _current_branch_name():
    for key in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME", "BRANCH_NAME"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return subprocess.check_output(
        ["git", "branch", "--show-current"],
        text=True,
        encoding="utf-8",
    ).strip()


def _is_subdub_m4b_scope():
    branch = _current_branch_name().lower()
    branch_tokens = (
        "p0-19m4b",
        "subdub-long-video",
        "long-video-over-30s",
    )
    return any(token in branch for token in branch_tokens)


def test_short_subdub_auto_refresh_path_unchanged():
    assert bot.subdub_progress_percent_for_lifecycle("received_file") == 5
    assert bot.subdub_progress_stage_payload("received_file")["percent"] == 5
    keyboard = bot.subdub_progress_keyboard("SHORTJOB", "vi")
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "videodub|subdub_status|SHORTJOB" in callbacks


def test_subdub_full_duration_limit_default_300_not_30():
    assert bot.subdub_full_duration_limit_seconds(False) >= 300
    assert bot.subdub_full_duration_limit_seconds(False) != 30


def test_preview_limit_30_does_not_block_full_subdub():
    assert bot.subdub_preview_duration_seconds() == 30
    gate = bot.subdub_duration_gate_payload({"duration": 60}, {}, is_admin=False)
    assert gate["duration_gate_result"] == "pass_long"
    assert gate["long_media_allowed"] is True


def test_video_31s_passes_duration_gate():
    gate = bot.subdub_duration_gate_payload({"duration": 31}, {}, is_admin=False)
    assert gate["duration_gate_result"] == "pass_long"
    assert gate["is_long_media"] is True
    assert gate["long_media_allowed"] is True


def test_video_60s_passes_duration_gate():
    gate = bot.subdub_duration_gate_payload({"duration": 60}, {}, is_admin=False)
    assert gate["duration_gate_result"] == "pass_long"
    assert gate["long_media_allowed"] is True


def test_video_299s_passes_duration_gate():
    gate = bot.subdub_duration_gate_payload({"duration": 299}, {}, is_admin=False)
    assert gate["duration_gate_result"] in {"pass", "pass_long"}
    assert not str(gate["duration_gate_result"]).startswith("fail")


def test_video_over_configured_limit_fails_clean_no_charge(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_MAX_DURATION_SECONDS", 60)
    gate = bot.subdub_duration_gate_payload({"duration": 61}, {}, is_admin=False)
    text = bot.subdub_duration_over_limit_text("vi")

    assert gate["duration_gate_result"] == "fail_over_limit"
    assert gate["duration_limit"] == 60
    assert "TOAN AAS chưa trừ Xu" in text
    assert "provider" not in text.lower()


def test_long_video_persists_input_duration():
    key = _job_key("duration")
    _clear_job(key)
    try:
        _, job = bot.acquire_subtitle_dub_pipeline_job(key, user_id=1, chat_id=2, mode=bot.VIDEO_SUBTITLE_MODE_DUB)
        gate = bot.subdub_duration_gate_payload({"duration": 60}, {}, is_admin=False)
        updated = bot.update_subtitle_dub_pipeline_job(key, **gate)

        assert job["job_id"]
        assert updated["input_duration"] == 60
        assert updated["duration_gate_result"] == "pass_long"
        assert updated["long_media_allowed"] is True
    finally:
        _clear_job(key)


def test_long_video_persists_progress_registry():
    key = _job_key("registry")
    _clear_job(key)
    try:
        _, job = bot.acquire_subtitle_dub_pipeline_job(key, user_id=10, chat_id=20, mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB)
        gate = bot.subdub_duration_gate_payload({"duration": 75}, {}, is_admin=False)
        bot.update_subtitle_dub_pipeline_job(
            key,
            **gate,
            registry_job_id=job["job_id"],
            registry_chat_id_present=True,
            lifecycle_state="extracting_audio",
            current_stage="extracting_audio",
            progress_stage="extracting_audio",
            progress_percent=bot.subdub_progress_percent_for_lifecycle("extracting_audio"),
        )
        found = bot.subdub_progress_job_for_user(job["job_id"], 10)

        assert found["job_key"] == key
        assert found["registry_job_id"] == job["job_id"]
        assert found["registry_chat_id_present"] is True
    finally:
        _clear_job(key)


def test_long_video_progress_advances_beyond_5_after_duration_pass():
    gate = bot.subdub_duration_gate_payload({"duration": 45}, {}, is_admin=False)
    percent = bot.subdub_progress_percent_for_lifecycle("extracting_audio")

    assert gate["duration_gate_result"] == "pass_long"
    assert percent > 5


def test_long_video_waiting_worker_not_stuck_at_5():
    key = _job_key("worker")
    _clear_job(key)
    try:
        _, job = bot.acquire_subtitle_dub_pipeline_job(key, user_id=11, chat_id=22, mode=bot.VIDEO_SUBTITLE_MODE_DUB)
        gate = bot.subdub_duration_gate_payload({"duration": 90}, {}, is_admin=False)
        bot.update_subtitle_dub_pipeline_job(
            key,
            **gate,
            worker_claim_required=True,
            worker_claimed=False,
            lifecycle_state="extracting_audio",
            current_stage="extracting_audio",
            progress_stage="extracting_audio",
            progress_percent=bot.subdub_progress_percent_for_lifecycle("extracting_audio"),
        )
        text = bot.product_progress_status_from_job_text("subdub", bot.SUBTITLE_DUB_PIPELINE_JOBS[key], job["job_id"])

        assert "20%" in text
        assert "worker" not in text.lower()
    finally:
        _clear_job(key)


def test_long_video_status_refresh_reads_existing_job():
    key = _job_key("refresh")
    _clear_job(key)
    try:
        _, job = bot.acquire_subtitle_dub_pipeline_job(key, user_id=12, chat_id=24, mode=bot.VIDEO_SUBTITLE_MODE_DUB)
        bot.update_subtitle_dub_pipeline_job(key, **bot.subdub_duration_gate_payload({"duration": 60}, {}, is_admin=False))
        found = bot.subdub_progress_job_for_user("#" + job["job_id"].lower(), 12)
        assert found["job_key"] == key
    finally:
        _clear_job(key)


def test_long_video_status_refresh_does_not_create_new_job():
    key = _job_key("no-new")
    _clear_job(key)
    try:
        _, job = bot.acquire_subtitle_dub_pipeline_job(key, user_id=13, chat_id=26, mode=bot.VIDEO_SUBTITLE_MODE_DUB)
        before = len(bot.SUBTITLE_DUB_PIPELINE_JOBS)
        bot.subdub_progress_job_for_user(job["job_id"], 13)
        after = len(bot.SUBTITLE_DUB_PIPELINE_JOBS)
        assert after == before
    finally:
        _clear_job(key)


def test_old_30s_gate_not_present_in_full_subdub_paths():
    assert bot.subdub_long_video_audit_payload()["full_job_hardcoded_30_gate_absent"] is True
    source = "\n".join([
        inspect.getsource(bot.subdub_duration_gate_payload),
        inspect.getsource(bot._execute_video_dubbing_pipeline_core),
    ])
    assert "max_seconds=30" not in source
    assert "min(30" not in source


def test_subdub_job_debug_exposes_duration_fields():
    text = bot.subtitle_dub_debug_text(
        {
            "internal_job_id": "LONGJOB123",
            "job_id": "LONGJOB123",
            "product_type": "subtitle_dub",
            "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            "status": "running",
            "stage": "extracting_audio",
            "lifecycle_state": "extracting_audio",
            "progress_percent": 20,
            "input_duration": 60,
            "detected_duration_source": "ffprobe",
            "telegram_duration": 59,
            "ffprobe_duration": 60,
            "duration_limit": 300,
            "duration_gate_result": "pass_long",
            "duration_guard_stage": "after_input_save",
            "is_long_media": True,
            "long_media_allowed": True,
            "worker_claim_required": False,
            "worker_claimed": False,
            "pipeline_started": True,
            "asr_started": False,
            "translation_started": False,
            "tts_started": False,
            "mux_started": False,
            "artifact_started": False,
            "last_completed_step": "received_file",
            "registry_job_id": "LONGJOB123",
            "registry_chat_id_present": True,
            "status_panel_message_id": "456",
            "last_error_stage": "",
            "last_error_safe": "",
            "charge_status": "not_charged",
        }
    )

    for label in (
        "input duration",
        "detected duration source",
        "telegram duration",
        "ffprobe duration",
        "duration gate result",
        "long media allowed",
        "registry job id",
        "status panel message id",
        "charge status",
    ):
        assert label in text


def test_subdub_long_video_audit_passes():
    payload = bot.subdub_long_video_audit_payload()
    required = [
        "preview_limit_separate_from_full_job",
        "supports_31s",
        "supports_60s",
        "supports_299s",
        "over_limit_fails_clean_no_charge",
        "accepted_long_progress_beyond_5",
        "progress_registry_available",
        "status_refresh_uses_existing_job",
        "worker_claim_fields_present",
        "full_job_hardcoded_30_gate_absent",
        "public_long_status_no_debug_terms",
    ]
    assert all(payload[name] is True for name in required)


def test_no_music_video_payos_pricing_changes():
    if not _is_subdub_m4b_scope():
        pytest.skip("SubDub M4B scope guard is not active for this branch")

    output = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True)
    changed = {line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()}
    disallowed = ("providers/", "payos", "pricing", "music", "video_provider", "remote_worker.py", "local_worker.py")

    assert changed <= {
        "bot.py",
        "tests/test_p0_19m4b_subdub_long_video_over_30s_progress_duration_gate_fix.py",
        "tests/test_p0_19m5a_subdub_large_telegram_media_input_save_fix.py",
        "tests/test_p0_19m8r_selective_rollback_subdub_m8_keep_international_subtitle_only.py",
    }
    assert not any(any(token in path.lower() for token in disallowed) for path in changed)
