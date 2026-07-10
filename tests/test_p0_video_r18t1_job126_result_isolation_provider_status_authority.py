from __future__ import annotations

from pathlib import Path

from services import video_project_queue as queue
from services import video_provider_router as router
from services import video_real_render_connector as connector


ROOT = Path(__file__).resolve().parents[1]


def _job126_fixture() -> tuple[dict, dict]:
    task_id = "task-scene-1-DoKZ"
    job = {
        "id": 126,
        "job_id": 126,
        "status": "failed_no_charge",
        "progress_percent": 30,
        "source": "product_video",
        "product_video": True,
        "scene_count": 2,
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "original_submit_source": "public_user_final_confirm",
        "user_visible_price_xu": 300,
        "persisted_quoted_price_xu": 300,
        "customer_charge_planned_xu": 300,
        "provider_budget_xu": 400,
    }
    result = {
        "job_id": 126,
        "scene_count": 2,
        "terminal_state": "failed_no_charge",
        "final_decision": "failed_no_charge",
        "aggregate_status": "failed_no_charge",
        "aggregate_reason": "required_scene_exhausted_no_charge",
        "charged_xu": 0,
        "final_delivered": False,
        "concat_attempted": False,
        "provider_task_ids": [task_id],
        "canonical_scene_index": 1,
        "canonical_task_id": task_id,
        "canonical_result_url": "https://fixture.invalid/scene-1.mp4",
        "canonical_result_url_present": True,
        "scene_result_urls_by_index": {"1": "yes", "2": "yes"},
        "scene_tasks": [
            {
                "scene_index": 1,
                "provider": "shopaikey_video",
                "provider_task_id": task_id,
                "active_task_id": task_id,
                "status": "provider_running",
                "shopaikey_data_status": "SUCCESS",
                "provider_status_payload_source": "shopaikey.data.status",
                "provider_status_raw": "NOT_START",
                "raw_provider_status_before_source_fix": "NOT_START",
                "provider_progress_raw": 100,
                "result_url": "https://fixture.invalid/scene-1.mp4",
                "result_url_valid": True,
                "provider_result_url_present": True,
                "clip_valid": False,
                "submit_accepted": True,
                "submit_http_status": 500,
                "transport_http": 500,
                "task_id_present": True,
                "task_pollable": True,
                "dispatch_state": "task_submitted",
            },
            {
                "scene_index": 2,
                "status": "pending_submit",
                "dispatch_state": "submit_in_progress",
                "dispatch_attempted": False,
                # Reproduces the bad job-level URL copied into an unowned scene.
                "result_url": "https://fixture.invalid/scene-1.mp4",
                "result_url_valid": True,
                "provider_result_url_present": True,
            },
        ],
    }
    return job, result


def test_job126_result_url_is_owned_only_by_scene_with_matching_task():
    job, result = _job126_fixture()
    ledger = queue.product_video_scene_ledger_state({}, job, result)
    scenes = {int(item["scene_index"]): item for item in ledger["scene_ledger"]}

    assert ledger["task_to_scene_index"] == {"task-scene-1-DoKZ": 1}
    assert ledger["result_task_id_by_scene"]["1"] == "task-scene-1-DoKZ"
    assert ledger["scene_result_available_by_index"] == {"1": True, "2": False}
    assert ledger["scene_clip_valid_by_index"] == {"1": False, "2": False}
    assert scenes[2]["result_url"] == ""
    assert scenes[2]["task_scene_mapping_verified"] is False
    assert ledger["phantom_result_prevented"] is True


def test_job126_result_bearing_success_overrides_historical_not_start_but_not_validation():
    job, result = _job126_fixture()
    ledger = queue.product_video_scene_ledger_state({}, job, result)

    assert ledger["scene_status_by_index"]["1"] == "result_pending_validation"
    assert ledger["authoritative_status_source_by_scene"]["1"].startswith("current_result_bearing_success")
    assert ledger["historical_status_ignored"] is True
    assert ledger["success_result_overrode_stale_not_start"] is True
    assert ledger["provider_status_conflict"] is True
    assert ledger["provider_status_conflict_resolution"] == "result_bearing_success_pending_validation"
    assert ledger["result_processing_action_by_scene"]["1"] == "download_and_validate"
    assert ledger["completed_scene_count"] == 0


def test_job126_active_result_and_pending_scene_suppress_false_terminal():
    job, result = _job126_fixture()
    ledger = queue.product_video_scene_ledger_state({}, job, result)

    assert ledger["aggregate_job_status"] == "processing_scenes"
    assert ledger["terminal_eligibility"] is False
    assert ledger["terminal_blocked_by_active_task"] is True
    assert ledger["terminal_blocked_by_pending_scene"] is True
    assert ledger["terminal_blocked_by_unprocessed_result"] is True
    assert ledger["unprocessed_result_indexes"] == [1]
    assert ledger["dispatchable_scene_indexes"] == [2]
    assert ledger["exhausted_scene_indexes"] == []
    assert ledger["continue_polling"] is True
    assert ledger["terminal_state"] == "final_rendering"
    assert ledger["concat_attempted"] is False
    assert ledger["final_delivered"] is False
    assert ledger["artifact_valid_for_charge_after_coverage"] is False


def test_scene_debug_never_copies_shared_job_task_or_result_to_missing_scene():
    job, result = _job126_fixture()
    job["scene_tasks"] = result["scene_tasks"]
    job["provider_task_ids"] = result["provider_task_ids"]
    job["result_url"] = result["canonical_result_url"]
    scenes = connector.product_video_scene_tasks_debug(job, scene_count=2)
    by_index = {int(item["scene_index"]): item for item in scenes}

    assert by_index[1]["provider_task_id"] == "task-scene-1-DoKZ"
    assert by_index[1]["result_url_valid"] is True
    assert by_index[1]["status"] == "result_pending_validation"
    assert by_index[2]["provider_task_id"] == ""
    assert by_index[2]["result_url_valid"] is False
    assert by_index[2]["result_url"] == ""
    assert by_index[2]["clip_valid"] is False
    assert by_index[2]["phantom_result_prevented"] is True


def test_pollable_task_makes_http_500_transport_anomaly_effectively_accepted():
    truth = router.product_video_submit_response_truth(
        provider_accepted=False,
        provider_task_id="task-scene-1-DoKZ",
        transport_http=500,
        task_pollable=True,
    )

    assert truth["effective_submit_outcome"] == "accepted"
    assert truth["effective_submit_accepted"] is True
    assert truth["transport_anomaly"] is True
    assert truth["duplicate_submit_prevented"] is True


def test_result_url_is_not_a_validated_clip_or_final_video():
    assert connector._normalize_scene_task_status(
        "SUCCESS",
        {
            "provider_task_id": "task-scene-1-DoKZ",
            "result_url_valid": True,
            "clip_valid": False,
            "clip_bytes": 0,
        },
    ) == "result_pending_validation"


def test_job126_no_concat_delivery_or_charge_before_two_valid_scene_clips():
    job, result = _job126_fixture()
    ledger = queue.product_video_scene_ledger_state({}, job, result)

    assert ledger["scene_coverage_count"] == 0
    assert ledger["concat_attempted"] is False
    assert ledger["delivery_succeeded"] is False
    assert ledger["artifact_valid_for_charge_after_coverage"] is False
    assert result["charged_xu"] == 0


def test_r18t1_job126_is_fixture_only_and_preserves_cleanup_guard():
    source = Path(__file__).read_text(encoding="utf-8")
    bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")

    assert "cleanup_audit_persisted" in bot_source
    for forbidden in (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "provider" + "_smoke",
        "url" + "open",
    ):
        assert forbidden not in source
