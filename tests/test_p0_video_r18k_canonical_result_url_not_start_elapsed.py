from pathlib import Path

from services import product_progress_status
from services import video_project_queue
from services import video_real_render_connector as connector


ROOT = Path(__file__).resolve().parents[1]


def _job_112(**overrides):
    data = {
        "id": 112,
        "job_id": 112,
        "source": "product_video",
        "product_video": True,
        "status": "failed",
        "terminal_state": "failed_no_charge",
        "render_mode": "real",
        "provider_call": True,
        "scene_count": 2,
        "orchestration_mode": "per_scene_8s",
        "provider_order": "shopaikey_video,key4u_video",
        "configured_provider_chain": "shopaikey_video,key4u_video",
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "original_submit_source": "public_user_final_confirm",
        "provider_elapsed_seconds": 55,
        "provider_wait_elapsed_seconds": 55,
        "progress_percent": 20,
        "selected_provider": "shopaikey_video",
        "selected_model": "veo3.1-fast",
        "provider_model_map": {"shopaikey_video": "veo3.1-fast", "key4u_video": "kling-3.0-turbo"},
    }
    data.update(overrides)
    return data


def _job_112_payload(**overrides):
    data = {
        "scene_index": 1,
        "request_job_id": "112-1",
        "provider": "shopaikey_video",
        "selected_provider": "shopaikey_video",
        "provider_pending_provider": "shopaikey_video",
        "provider_pending_task_id": "task-112-live",
        "provider_task_id": "task-112-live",
        "provider_task_ids": ["task-112-live"],
        "status": "IN_PROGRESS",
        "provider_status": "IN_PROGRESS",
        "normalized_provider_status": "running",
        "provider_status_raw": "IN_PROGRESS",
        "raw_provider_status": "IN_PROGRESS",
        "raw_provider_status_before_source_fix": "IN_PROGRESS",
        "provider_status_payload_source": "shopaikey.data.status",
        "shopaikey_data_status": "NOT_START",
        "shopaikey_raw_status": "NOT_START",
        "shopaikey_data_progress_raw": "0%",
        "provider_elapsed_seconds": 55,
        "provider_wait_elapsed_seconds": 55,
        "elapsed_wall_clock_seconds": 55,
        "scene_not_start_elapsed": 0,
        "continue_polling": True,
        "provider_task_id_saved": True,
        "provider_result_url_present": False,
        "result_url_present": False,
        "result_url_valid": False,
        "artifact_size": 0,
        "output_bytes": 0,
        "provider_error": "provider_in_progress",
        "blocker": "provider_in_progress",
        "fallback_block_reason": "primary_provider_in_progress",
        "key4u_submit_suppressed": True,
        "key4u_submit_suppressed_reason": "primary_provider_in_progress",
        "provider_attempts": [
            {
                "scene_index": 2,
                "provider": "shopaikey_video",
                "provider_task_id": "task-112-stale",
                "status": "SUCCESS",
                "provider_status": "succeeded",
                "result_url": "https://cdn.example.com/stale-other-scene.mp4",
                "result_url_valid": True,
                "result_url_present": True,
                "updated_at": "2026-07-09T12:00:00",
            }
        ],
    }
    data.update(overrides)
    return data


def test_job_112_under_threshold_uses_provider_elapsed_and_ignores_stale_result_url(monkeypatch):
    monkeypatch.delenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", raising=False)
    payload = _job_112_payload()
    job = _job_112()

    scene_debug = connector.product_video_scene_tasks_debug(job, debug_results=[payload], scene_count=2)
    assert scene_debug[0]["status"] == "provider_not_start"
    assert scene_debug[0]["scene_not_start_elapsed"] >= 55
    assert scene_debug[0]["provider_stalled_not_start"] is False
    assert scene_debug[0]["fallback_block_reason"] == "not_start_under_threshold"

    bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")

    assert "primary_not_start_task" in bot_source
    assert "stale_result_url_ignored" in bot_source
    assert "result_url_task_matches_canonical" in bot_source
    assert "finance_result_task_id" in bot_source
    assert "canonical_status != \"succeeded\"" in bot_source


def test_progress_terminal_fail_is_blocked_while_not_start_under_threshold():
    job = _job_112()
    payload = connector._enforce_shopaikey_not_start_final_invariant(_job_112_payload(), job=job)

    telemetry = video_project_queue.reconcile_provider_progress_telemetry(job, payload, refresh_source="r18k_fixture")

    assert telemetry["provider_task_alive"] is True
    assert telemetry["scene_not_start_elapsed"] >= 55
    assert telemetry["provider_stalled_not_start"] is False
    assert telemetry["fallback_block_reason"] == "not_start_under_threshold"
    assert telemetry["final_status_after_reconcile"] == "processing"
    assert telemetry["final_user_visible_state"] == "final_rendering"
    assert telemetry["next_poll_scheduled"] is True

    progress = product_progress_status.product_progress_debug_payload(
        "multiscene_video",
        "112",
        {**job, **payload, **telemetry},
    )
    assert progress["final_user_visible_state"] == "final_rendering"
    assert progress["scene_not_start_elapsed"] >= 55


def test_not_start_over_threshold_fallback_and_no_fallback_paths(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", "40")
    payload = _job_112_payload(provider_elapsed_seconds=55, provider_wait_elapsed_seconds=55)

    with_fallback = connector._enforce_shopaikey_not_start_final_invariant(
        {**payload, "fallback_provider_order": ["key4u_video"]},
        job=_job_112(provider_elapsed_seconds=55),
    )
    assert with_fallback["provider_stalled_not_start"] is True
    assert with_fallback["fallback_allowed"] is True
    assert with_fallback["key4u_submit_suppressed"] is False

    no_fallback = connector._enforce_shopaikey_not_start_final_invariant(
        {**payload, "fallback_provider_order": []},
        job=_job_112(provider_order="shopaikey_video", configured_provider_chain="shopaikey_video"),
    )
    assert no_fallback["terminal_state"] == "failed_no_charge"
    assert no_fallback["continue_polling"] is False
    assert no_fallback["no_charge"] is True


def test_r18g_r18c_r18d_and_no_hidden_submit_source_contracts_preserved():
    r18g = (ROOT / "tests" / "test_p0_video_r18g_key4u_family_endpoint_quote_consistency.py").read_text(encoding="utf-8")
    connector_source = (ROOT / "services" / "video_real_render_connector.py").read_text(encoding="utf-8")
    catalog_source = (ROOT / "services" / "video_provider_catalog.py").read_text(encoding="utf-8")
    routing_source = (ROOT / "config" / "product_video_model_routing.json").read_text(encoding="utf-8")
    bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")

    assert 'payload["customer_charge_planned_xu"] == 300' in r18g
    assert "test_low_and_basic_route_shopaikey_primary_key4u_fallback_only" in r18g
    assert "PRODUCT_VIDEO_RENDER_PIPELINE_HISTORICAL_CONCAT" in connector_source
    assert "PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S" in connector_source
    assert "resolve_product_video_model" in catalog_source
    assert "veo3.1-fast" in routing_source
    assert "cmd_video_provider_job_debug" in bot_source
    assert "debug/recover/status" not in bot_source


def test_no_real_provider_calls_in_r18k_tests():
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "urllib.request." + "urlopen",
        "provider" + "_smoke",
    )
    assert all(token not in source for token in forbidden)
