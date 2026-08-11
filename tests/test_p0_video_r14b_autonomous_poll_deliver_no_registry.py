from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
QUEUE_SOURCE = (ROOT / "services" / "video_project_queue.py").read_text(encoding="utf-8")
REMOTE_WORKER_API_SOURCE = (ROOT / "services" / "remote_worker_api.py").read_text(encoding="utf-8")


def _between(source: str, start: str, end: str) -> str:
    assert start in source, start
    head = source.split(start, 1)[1]
    if end in head:
        return head.split(end, 1)[0]
    return head


def test_registry_missing_provider_running_becomes_autonomous_db_poll_candidate():
    helper = _between(
        BOT_SOURCE,
        "def video_b14_autonomous_db_poll_metadata",
        "async def video_b14_autonomous_materialize_and_deliver",
    )
    for expected in (
        '"autonomous_db_poller_enabled": True',
        '"db_poll_candidate": bool(candidate)',
        '"registry_required_for_poll": False',
        '"registry_missing_is_blocker": False',
        '"next_poll_at"',
        '"next_refresh_expected_at"',
        '"no_new_paid_submit": True',
    ):
        assert expected in helper


def test_auto_refresh_missing_registry_reports_db_poll_not_no_registry_blocker():
    status_text = _between(
        BOT_SOURCE,
        "def video_b14_auto_refresh_status_text",
        "def video_b14_insufficient_balance_text",
    )
    assert "Auto poll DB" in status_text
    assert "db_auto_poll_can_follow_existing_provider_task" in status_text
    assert "registry_missing_is_blocker" in status_text
    recovered_block = status_text.split("scheduler_mode: <code>autonomous_db_poll", 1)[1].split("if not records:", 1)[0]
    assert "no_registry_after_restart" not in recovered_block


def test_provider_running_never_surfaces_failed_no_charge_terminal_in_video_debug():
    terminal = _between(
        BOT_SOURCE,
        "def video_b14_auto_refresh_terminal_state",
        "def video_b14_auto_refresh_stage_from_snapshot",
    )
    assert 'telemetry.get("provider_task_alive")' in terminal
    assert 'return ""' in terminal

    progress_debug = _between(
        BOT_SOURCE,
        "def product_progress_debug_text",
        "def progress_audit_text",
    )
    assert 'if (job or {}).get("provider_task_alive"):' in progress_debug
    assert 'payload["terminal_state"] = ""' in progress_debug
    assert "provider_running_overrides_failed_no_charge" in BOT_SOURCE


def test_refresh_only_renders_persisted_state_while_worker_keeps_recovery_owner():
    materialize = _between(
        BOT_SOURCE,
        "async def video_b14_autonomous_materialize_and_deliver",
        "def video_provider_recover_existing_task",
    )
    assert "video_provider_recover_existing_task(jid, download=True, source=source)" in materialize
    assert "complete_video_job" in materialize
    assert "maybe_send_remote_worker_final_video" in materialize
    assert "note_video_delivery_result" in materialize
    assert "download_button_visible" in materialize
    assert "submit_video_job" not in materialize

    tick = _between(BOT_SOURCE, "async def video_b14_auto_refresh_tick", "async def video_b14_send_or_edit_status_panel")
    assert "video_b14_autonomous_materialize_and_deliver" not in tick
    assert "video_b14_auto_refresh_snapshot" in tick
    assert "video_b14_persist_auto_refresh_metadata" not in tick

    callback = _between(BOT_SOURCE, 'if action == "b14_job_status":', 'if action == "b14_download_video":')
    assert "video_b14_autonomous_materialize_and_deliver" not in callback
    assert "safe_edit_or_send" not in callback
    assert "video_b14_edit_existing_status_message" in callback
    assert "video_b14_auto_refresh_status_bundle" in callback
    assert "register_auto_refresh=False" in callback
    assert "edit_existing_only=True" in callback

    worker_claim = _between(BOT_SOURCE, "async def api_worker_claim", "async def api_worker_heartbeat")
    assert "video_b14_recover_existing_tasks_for_worker_claim" in worker_claim


def test_autonomous_recovery_finalizes_provider_artifact_before_complete_and_delivery():
    materialize = _between(
        BOT_SOURCE,
        "async def video_b14_autonomous_materialize_and_deliver",
        "def video_provider_recover_existing_task",
    )
    finalize_call = "finalize_recovered_product_video_artifact"
    complete_call = "video_project_queue.complete_video_job"

    assert finalize_call in materialize
    assert materialize.index(finalize_call) < materialize.index(complete_call)
    assert "recovery_finalization" in materialize

    recover = _between(BOT_SOURCE, "def video_provider_recover_existing_task", "def video_provider_recover_text")
    assert '"postprocess_not_required_for_recovery": True' not in recover
    assert '"postprocess_required_for_recovery": True' in recover


def test_result_url_download_button_resends_without_submit_or_extra_charge():
    resend = _between(
        BOT_SOURCE,
        "async def video_b14_resend_delivered_video",
        "def video_b14_auto_refresh_session_from_status",
    )
    assert "video_provider_recover_existing_task(safe_int(job_id, 0), download=True)" in resend
    assert "caption = \"📥 TOAN AAS gửi lại video đã hoàn tất. Không trừ thêm Xu.\"" in resend
    assert "submit_video_job" not in resend
    assert "charge" not in resend.lower()

    keyboard = _between(BOT_SOURCE, "def video_b14_queue_status_keyboard", "def video_b14_auto_refresh_key")
    assert "📥 Tải video" in keyboard
    assert "video_b14_delivered_video_artifact(jid).get(\"ok\")" in keyboard


def test_duration_gate_preserved_for_sold_16s_video_before_success_delivery():
    assert "PRODUCT_VIDEO_SCENE_SECONDS = 8" in QUEUE_SOURCE
    assert "final_duration_short_scene_coverage_missing" in QUEUE_SOURCE
    complete = _between(QUEUE_SOURCE, "def complete_video_job", "def note_video_delivery_result")
    assert "product_video_duration_contract" in complete
    assert "fail_video_job" in complete
    assert '"terminal_state"] = "failed_no_charge"' in complete


def test_stale_timeout_does_not_fail_alive_provider_task():
    stale = _between(
        REMOTE_WORKER_API_SOURCE,
        "def fail_stale_product_video_jobs",
        "def heartbeat_remote_worker_job",
    )
    assert "video_project_queue.provider_task_alive(payload)" in stale
    assert '"db_poll_candidate": True' in stale
    assert '"registry_missing_is_blocker": False' in stale
    assert "continue" in stale


def test_recover_command_remains_read_only_for_submit_and_can_materialize_result_url():
    recover = _between(BOT_SOURCE, "def video_provider_recover_existing_task", "def video_provider_recover_text")
    assert "adapter.poll_video_job(task_id)" in recover
    assert "adapter.materialize_result" in recover
    assert "no_new_paid_submit" in recover
    assert "submit_video_job" not in recover
