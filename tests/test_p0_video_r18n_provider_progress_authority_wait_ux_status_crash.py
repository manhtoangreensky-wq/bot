from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from services import video_project_queue as queue
from services import video_real_render_connector as connector


ROOT = Path(__file__).resolve().parents[1]


def _job116_payload(elapsed: int = 123) -> dict:
    return {
        "selected_provider": "shopaikey_video",
        "provider_pending_provider": "shopaikey_video",
        "provider_pending_task_id": "task-AVWB",
        "provider_task_ids": ["task-AVWB"],
        "provider_task_id_saved": True,
        "submit_accepted": True,
        "provider_submit_called": True,
        "provider_poll_called": True,
        "continue_polling": True,
        "primary_provider_continue_polling": True,
        "primary_provider_task_alive": True,
        "provider_status_payload_source": "shopaikey.data.status",
        "shopaikey_data_status": "IN_PROGRESS",
        "shopaikey_raw_status": "IN_PROGRESS",
        "shopaikey_data_progress_raw": 30,
        "provider_progress_raw": 30,
        "raw_provider_status": "NOT_START",
        "provider_status_raw": "NOT_START",
        "provider_error": "provider_not_start",
        "blocker": "provider_not_start",
        "scene_not_start_elapsed": elapsed,
        "provider_elapsed_seconds": elapsed,
        "provider_wait_elapsed_seconds": elapsed,
        "not_start_threshold_seconds": 60,
        "stall_threshold": 60,
        "provider_stalled_not_start": True,
        "fallback_block_reason": "not_start_under_threshold",
        "fallback_blocked_reason": "not_start_under_threshold",
        "terminal_state": "final_rendering",
        "provider_attempts": [
            {
                "provider": "shopaikey_video",
                "provider_task_id": "task-AVWB",
                "submit_accepted": True,
                "continue_polling": True,
                "raw_provider_status": "NOT_START",
                "provider_status": "not_start",
                "blocker": "provider_not_start",
            }
        ],
    }


def test_job116_actual_in_progress_dominates_stale_not_start_connector():
    result = connector._apply_pending_provider_dominance(_job116_payload(), job={"source": "product_video"})

    assert result["raw_provider_status"] == "IN_PROGRESS"
    assert result["not_start_override_applied"] is False
    assert result["stale_not_start_blocker_ignored"] is True
    assert result["provider_stalled_not_start"] is False
    assert result["current_scene_status"] == "provider_running"
    assert result["fallback_block_reason"] == "primary_provider_in_progress"
    assert result["key4u_submit_suppressed_reason"] == "primary_provider_in_progress"


def test_job116_progress_uses_actual_in_progress_not_stale_not_start():
    now = datetime(2026, 7, 10, 12, 0, 0)
    payload = _job116_payload(elapsed=800)
    payload["provider_started_at"] = (now - timedelta(seconds=800)).strftime("%Y-%m-%d %H:%M:%S")
    payload["provider_wait_max_seconds"] = 1200

    telemetry = queue.reconcile_provider_progress_telemetry(
        {"status": "processing", "progress_percent": 39},
        payload,
        now=now,
        refresh_source="r18n_job116",
    )

    assert telemetry["provider_status_raw"] == "IN_PROGRESS"
    assert telemetry["provider_status_for_progress"] == "in_progress"
    assert telemetry["scene_not_start_elapsed"] == 0
    assert telemetry["provider_stalled_not_start"] is False
    assert telemetry["fallback_block_reason"] == "primary_provider_in_progress"
    assert telemetry["terminal_state"] == "final_rendering"
    assert telemetry["final_status_after_reconcile"] == "processing"
    assert telemetry["stale_not_start_blocker_ignored"] is True
    assert telemetry["not_start_decision_source"] == "actual_provider_payload_in_progress"
    assert 30 < telemetry["render_video_progress_percent"] <= 85
    assert telemetry["no_fake_success_guard"] is True


def test_actual_in_progress_over_not_start_threshold_does_not_fallback_scene_policy():
    policy = connector.product_video_scene_stall_policy(
        {
            "source": "product_video",
            "public_user_confirmed": True,
            "invoice_confirmed": True,
            "provider_order": ["shopaikey_video", "key4u_video"],
        },
            _job116_payload(elapsed=123) | {"provider_task_id": "task-AVWB", "provider": "shopaikey_video"},
        1,
    )

    assert policy["provider_not_start"] is False
    assert policy["provider_stalled_not_start"] is False
    assert policy["fallback_allowed"] is False
    assert policy["fallback_block_reason"] == "primary_provider_in_progress"
    assert policy["source_of_truth"] == "actual_provider_in_progress"


def test_true_not_start_over_threshold_still_fallbacks():
    policy = connector.product_video_scene_stall_policy(
        {
            "source": "product_video",
            "public_user_confirmed": True,
            "invoice_confirmed": True,
            "provider_order": ["shopaikey_video", "key4u_video"],
        },
        {
            "provider_task_id": "task-not-start",
            "provider": "shopaikey_video",
            "provider_status_payload_source": "shopaikey.data.status",
            "shopaikey_data_status": "NOT_START",
            "raw_provider_status": "NOT_START",
            "provider_elapsed_seconds": 90,
            "provider_wait_elapsed_seconds": 90,
            "progress": 0,
        },
        1,
    )

    assert policy["provider_not_start"] is True
    assert policy["provider_stalled_not_start"] is True
    assert policy["fallback_allowed"] is True
    assert policy["fallback_provider_order"] == ["key4u_video"]


def test_result_url_valid_not_delivered_is_not_completed_or_charged(tmp_path):
    mp4 = tmp_path / "provider.mp4"
    mp4.write_bytes(b"valid-mp4")
    telemetry = queue.reconcile_provider_progress_telemetry(
        {"status": "processing", "progress_percent": 39},
        {"result_url_present": True, "final_video_path": str(mp4), "final_mp4_valid": True},
        now=datetime(2026, 7, 10, 12, 0, 0),
    )
    decision = queue.product_video_delivery_charge_decision(
        {"final_video_path": str(mp4)},
        {"id": 116},
        {"final_video_path": str(mp4), "final_mp4_valid": True, "final_delivered": False},
    )

    assert 85 <= telemetry["final_progress_after_reconcile"] <= 95
    assert telemetry["final_status_after_reconcile"] != "completed"
    assert decision["ok"] is False
    assert decision["charge_skip_reason"] == "delivery_required_before_charge"


def test_delivered_valid_mp4_progress_100_and_charge_once(tmp_path):
    mp4 = tmp_path / "final.mp4"
    mp4.write_bytes(b"valid-mp4")
    decision = queue.product_video_delivery_charge_decision(
        {
            "video_delivered_at": "2026-07-10 12:10:00",
            "final_video_path": str(mp4),
            "invoice_json": queue._json_dumps(
                {
                    "user_visible_price_xu": 300,
                    "persisted_quoted_price_xu": 300,
                    "customer_charge_planned_xu": 300,
                }
            ),
        },
        {"id": 116},
        {"final_video_path": str(mp4), "final_mp4_valid": True, "final_delivered": True},
    )
    telemetry = queue.reconcile_provider_progress_telemetry(
        {"status": "completed", "progress_percent": 39},
        {"final_video_path": str(mp4), "final_mp4_valid": True, "final_delivered": True},
    )

    assert decision["ok"] is True
    assert decision["amount_xu"] == 300
    assert telemetry["final_status_after_reconcile"] == "completed"
    assert telemetry["final_progress_after_reconcile"] == 100


def test_video_public_status_health_guard_source_contract():
    source = (ROOT / "bot.py").read_text(encoding="utf-8")
    block = source[source.index("def video_public_status_text") : source.index("VIDEO_GATE_FEATURES")]

    assert "health_render_error" in block
    assert "video_public_status_health_render_error" in block
    assert "isinstance(payload.get(\"product_video_provider_health\"), dict)" in block
    assert "shopaikey_health.get('health_status')" in block


def test_no_real_provider_calls_in_r18n_tests():
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "url" + "open",
        "provider" + "_smoke",
    )
    assert all(token not in source for token in forbidden)
