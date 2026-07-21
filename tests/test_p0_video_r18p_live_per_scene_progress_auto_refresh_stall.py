from pathlib import Path

from services import product_progress_status, video_project_queue
from services.video_real_render_connector import product_video_scene_stall_policy


ROOT = Path(__file__).resolve().parents[1]


def _job119_payload(elapsed: int = 185) -> dict:
    return {
        "provider_task_id": "shop-task-119-1",
        "provider_task_id_saved": True,
        "provider_task_alive": True,
        "continue_polling": True,
        "provider_status_payload_source": "shopaikey.data.status",
        "shopaikey_data_status": "IN_PROGRESS",
        "shopaikey_raw_status": "IN_PROGRESS",
        "shopaikey_data_progress_raw": "30",
        "provider_progress_raw": "30",
        "provider_progress_source": "shopaikey.data.progress",
        "provider_elapsed_seconds": elapsed,
        "provider_wait_elapsed_seconds": elapsed,
        "provider_wait_max_seconds": 1200,
        "scene_count": 2,
        "scene_coverage_count": 0,
        "concat_attempted": True,
        "scene_tasks": [
            {
                "scene_index": 1,
                "provider": "shopaikey_video",
                "provider_task_id": "shop-task-119-1",
                "status": "provider_running",
                "provider_status_payload_source": "shopaikey.data.status",
                "shopaikey_data_status": "IN_PROGRESS",
                "provider_progress_raw": "30",
                "provider_elapsed_seconds": elapsed,
            },
            {
                "scene_index": 2,
                "provider": "shopaikey_video",
                "provider_task_id": "shop-task-119-2",
                "status": "provider_running",
                "provider_status_payload_source": "shopaikey.data.status",
                "shopaikey_data_status": "IN_PROGRESS",
                "provider_progress_raw": "30",
                "provider_elapsed_seconds": elapsed,
            },
        ],
    }


def test_job119_in_progress_smooths_public_progress_and_scene_board():
    job = {"id": 119, "status": "processing", "progress_percent": 39}
    payload = _job119_payload(elapsed=185)

    telemetry = video_project_queue.reconcile_provider_progress_telemetry(job, payload, refresh_source="r18p_fixture")

    assert telemetry["final_status_after_reconcile"] == "processing"
    assert telemetry["terminal_state"] == "final_rendering"
    assert 39 < telemetry["final_progress_after_reconcile"] <= 85
    assert telemetry["elapsed_estimate_progress"] >= 45
    assert telemetry["public_progress_source"] == "provider_elapsed_in_progress"
    assert telemetry["no_fake_success_guard"] is True
    assert telemetry["provider_in_progress_stalled"] is False

    board = product_progress_status.video_per_scene_progress_board_text({**payload, **telemetry})
    assert "Cảnh 1/2" in board
    assert "Cảnh 2/2" in board
    assert "Đang tạo" in board
    assert "chưa có MP4" not in board
    assert "ShopAIKey" not in board

    coverage = video_project_queue.product_video_scene_coverage_state(
        result={**payload, "scene_count": 2, "concat_attempted": True}
    )
    assert coverage["scene_coverage_count"] == 0
    assert coverage["concat_attempted"] is False
    assert coverage["concat_waiting_for_scene_coverage"] is True
    assert coverage["artifact_valid_for_charge_after_coverage"] is False


def test_auto_refresh_metadata_recovery_and_rebind_source_contract():
    bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")
    assert "video_b14_persist_auto_refresh_metadata" in bot_source
    assert "status_panel_message_id_source" in bot_source
    assert "auto_refresh_recovered_from_db" in bot_source
    assert "auto_refresh_next_tick_at" in bot_source
    assert "safe_edit_or_send" in bot_source
    assert "telegram_send_or_edit" in bot_source


def test_in_progress_under_threshold_continues_without_fallback():
    decision = product_video_scene_stall_policy(
        {
            "public_user_confirmed": True,
            "invoice_confirmed": True,
            "provider_order": "shopaikey_video,key4u_video",
        },
        {
            "scene_index": 1,
            "provider": "shopaikey_video",
            "provider_task_id": "task-1",
            "status": "provider_running",
            "provider_status_payload_source": "shopaikey.data.status",
            "shopaikey_data_status": "IN_PROGRESS",
            "provider_progress_raw": "30",
            "provider_elapsed_seconds": 185,
            "provider_progress_last_changed_elapsed_seconds": 185,
        },
        1,
    )
    assert decision["fallback_allowed"] is False
    assert decision["fallback_block_reason"] == "primary_provider_in_progress"
    assert decision["in_progress_stall_decision"] == "under_threshold_continue_polling"


def test_in_progress_over_threshold_stuck_allows_single_fallback(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_IN_PROGRESS_STALL_SECONDS", "300")
    decision = product_video_scene_stall_policy(
        {
            "public_user_confirmed": True,
            "invoice_confirmed": True,
            "provider_order": "shopaikey_video,key4u_video",
        },
        {
            "scene_index": 1,
            "provider": "shopaikey_video",
            "provider_task_id": "task-1",
            "status": "provider_running",
            "provider_status_payload_source": "shopaikey.data.status",
            "shopaikey_data_status": "IN_PROGRESS",
            "provider_progress_raw": "30",
            "provider_elapsed_seconds": 360,
            "provider_progress_last_changed_elapsed_seconds": 360,
        },
        1,
    )
    assert decision["provider_in_progress_stalled"] is True
    assert decision["fallback_allowed"] is True
    assert decision["fallback_due_to_in_progress_stall"] is True
    assert decision["fallback_provider_order"] == ["key4u_video"]


def test_in_progress_over_threshold_recent_progress_does_not_fallback(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_IN_PROGRESS_STALL_SECONDS", "300")
    decision = product_video_scene_stall_policy(
        {
            "public_user_confirmed": True,
            "invoice_confirmed": True,
            "provider_order": "shopaikey_video,key4u_video",
        },
        {
            "scene_index": 1,
            "provider": "shopaikey_video",
            "provider_task_id": "task-1",
            "status": "provider_running",
            "provider_status_payload_source": "shopaikey.data.status",
            "shopaikey_data_status": "IN_PROGRESS",
            "provider_progress_raw": "45",
            "provider_elapsed_seconds": 360,
            "provider_progress_last_changed_elapsed_seconds": 60,
        },
        1,
    )
    assert decision["provider_in_progress_stalled"] is False
    assert decision["fallback_allowed"] is False
    assert decision["fallback_block_reason"] == "provider_progress_changed_recently"


def test_true_not_start_over_threshold_still_fallback(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", "60")
    decision = product_video_scene_stall_policy(
        {
            "public_user_confirmed": True,
            "invoice_confirmed": True,
            "provider_order": "shopaikey_video,key4u_video",
        },
        {
            "scene_index": 1,
            "provider": "shopaikey_video",
            "provider_task_id": "task-1",
            "status": "provider_not_start",
            "provider_status_payload_source": "shopaikey.data.status",
            "shopaikey_data_status": "NOT_START",
            "provider_progress_raw": "0",
            "provider_elapsed_seconds": 75,
        },
        1,
    )
    assert decision["provider_stalled_not_start"] is True
    assert decision["fallback_allowed"] is True


def test_multiscene_full_coverage_allows_concat_and_partial_does_not():
    partial = video_project_queue.product_video_scene_coverage_state(
        result={
            "scene_count": 2,
            "concat_attempted": True,
            "scene_tasks": [
                {"scene_index": 1, "status": "clip_downloaded", "result_url": "https://example.test/1.mp4", "clip_valid": True},
            ],
        }
    )
    assert partial["scene_coverage_count"] == 1
    assert partial["concat_attempted"] is False
    assert partial["concat_waiting_for_scene_coverage"] is True

    full = video_project_queue.product_video_scene_coverage_state(
        result={
            "scene_count": 2,
            "concat_attempted": True,
            "concat_output_valid": True,
            "final_mp4_valid": True,
            "scene_tasks": [
                {"scene_index": 1, "status": "clip_downloaded", "result_url": "https://example.test/1.mp4", "clip_valid": True},
                {"scene_index": 2, "status": "clip_downloaded", "result_url": "https://example.test/2.mp4", "clip_valid": True},
            ],
        }
    )
    assert full["scene_coverage_count"] == 2
    assert full["concat_attempted"] is True
    assert full["artifact_valid_for_charge_after_coverage"] is True


def test_hidden_status_debug_recover_paths_remain_read_only_source_contract():
    bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")
    for marker in ("cmd_video_progress_auto_refresh_status", "video_b14_auto_refresh_status_text", "video_b14_autonomous_db_poll_metadata"):
        assert marker in bot_source
    assert "no_new_paid_submit" in bot_source
    assert "debug_status_read_only_no_submit" in bot_source
