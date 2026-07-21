from pathlib import Path

from services import product_progress_status
from services import video_project_queue as queue
from services import video_real_render_connector as connector


ROOT = Path(__file__).resolve().parents[1]


def _job(**overrides):
    data = {
        "job_id": "110",
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "product_type": "video_trend",
        "scene_count": 2,
        "orchestration_mode": "per_scene_8s",
        "provider_order": "shopaikey_video,key4u_video",
        "configured_provider_chain": "shopaikey_video,key4u_video",
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "original_submit_source": "public_user_final_confirm",
        "provider_elapsed_seconds": 46,
        "provider_wait_elapsed_seconds": 46,
        "progress_percent": 39,
        "selected_provider": "shopaikey_video",
        "selected_model": "veo3.1-fast",
        "provider_model_map": {"shopaikey_video": "veo3.1-fast", "key4u_video": "kling-3.0-turbo"},
    }
    data.update(overrides)
    return data


def _scene_payload(scene_index=1, task_id="task-110-a", elapsed=46, **overrides):
    data = {
        "scene_index": scene_index,
        "request_job_id": f"110-{scene_index}",
        "provider": "shopaikey_video",
        "selected_provider": "shopaikey_video",
        "provider_task_id": task_id,
        "provider_video_id": f"video-{task_id}",
        "provider_task_ids": [task_id],
        "provider_video_ids": [f"video-{task_id}"],
        "status": "running",
        "provider_status": "running",
        "normalized_provider_status": "running",
        "provider_status_raw": "IN_PROGRESS",
        "raw_provider_status": "IN_PROGRESS",
        "raw_provider_status_before_source_fix": "IN_PROGRESS",
        "provider_status_payload_source": "shopaikey.data.status",
        "shopaikey_raw_status": "NOT_START",
        "shopaikey_data_status": "NOT_START",
        "nonterminal_provider_status": "IN_PROGRESS",
        "provider_progress_raw": 0,
        "shopaikey_data_progress_raw": 0,
        "provider_progress_normalized": 0,
        "provider_elapsed_seconds": elapsed,
        "provider_wait_elapsed_seconds": elapsed,
        "scene_not_start_elapsed": 0,
        "provider_stalled_not_start": False,
        "fallback_allowed": False,
        "fallback_block_reason": "primary_provider_in_progress",
        "fallback_blocked_reason": "primary_provider_in_progress",
        "primary_provider_task_alive": True,
        "key4u_submit_suppressed": True,
        "continue_polling": True,
        "selected_model": "veo3.1-fast",
        "blocker": "provider_not_start",
        "provider_error": "provider_not_start",
    }
    data.update(overrides)
    return data


def test_job_110_actual_not_start_overrides_in_progress_summary():
    payload = {
        **_scene_payload(elapsed=46),
        "provider_pending_provider": "shopaikey_video",
        "provider_pending_task_id": "task-110-a",
        "provider_pending_video_id": "video-task-110-a",
        "provider_pending_request_job_id": "110-1",
        "provider_attempts": [
            _scene_payload(elapsed=46, blocker="provider_not_start", provider_error="provider_not_start")
        ],
    }

    result = connector._apply_pending_provider_dominance(payload, job=_job())

    assert result["provider_status_payload_source"] == "shopaikey.data.status"
    assert result["raw_provider_status_before_source_fix"] == "IN_PROGRESS"
    assert result["raw_provider_status"] == "NOT_START"
    assert result["provider_status_raw"] == "NOT_START"
    assert result["normalized_provider_status"] == "not_start"
    assert result["provider_status"] == "not_start"
    assert result["provider_error"] == "provider_not_start"
    assert result["blocker"] == "provider_not_start"
    assert result["not_start_override_applied"] is True
    assert result["provider_elapsed_seconds"] >= 46


def test_canonical_scene_task_is_stable_by_scene_index():
    scene_1 = _scene_payload(scene_index=1, task_id="scene-1-task", elapsed=46)
    scene_2 = _scene_payload(
        scene_index=2,
        task_id="scene-2-task",
        elapsed=12,
        provider_status_payload_source="shopaikey.status",
        shopaikey_raw_status="IN_PROGRESS",
        shopaikey_data_status="IN_PROGRESS",
        raw_provider_status="IN_PROGRESS",
        provider_status_raw="IN_PROGRESS",
        blocker="provider_in_progress",
        provider_error="provider_in_progress",
    )

    debug = connector.product_video_scene_tasks_debug(
        _job(),
        debug_results=[scene_2, scene_1],
        scene_count=2,
    )

    assert debug[0]["canonical_scene_index"] == 1
    assert debug[0]["canonical_task_selected"] == "scene-1-task"
    assert debug[0]["provider_status_raw"] == "NOT_START"
    assert debug[0]["status"] == "provider_not_start"
    assert debug[1]["canonical_scene_index"] == 2
    assert debug[1]["canonical_task_selected"] == "scene-2-task"
    assert debug[1]["status"] == "provider_running"
    assert debug[0]["canonical_task_candidates_by_scene"]["1"][0]["task_id_masked"]
    assert debug[0]["canonical_task_reject_reasons"]["2"][0]["reason"] == "different_scene"


def test_progress_debug_uses_same_canonical_scene_fields():
    scene = _scene_payload(scene_index=1, task_id="same-task", elapsed=46)
    scene_debug = connector.product_video_scene_tasks_debug(_job(), debug_results=[scene], scene_count=2)
    job = {
        **_job(),
        "status": "processing",
        "current_scene_status": scene_debug[0]["status"],
        "scene_not_start_elapsed": scene_debug[0]["scene_not_start_elapsed"],
        "raw_provider_status": scene_debug[0]["provider_status_raw"],
        "normalized_provider_status": "not_start",
        "canonical_scene_index": scene_debug[0]["canonical_scene_index"],
        "canonical_task_selected": scene_debug[0]["canonical_task_selected"],
        "canonical_task_candidates_by_scene": scene_debug[0]["canonical_task_candidates_by_scene"],
        "canonical_task_reject_reasons": scene_debug[0]["canonical_task_reject_reasons"],
    }

    payload = product_progress_status.product_progress_debug_payload("multiscene_video", "110", job)

    assert payload["current_scene_status"] == "provider_not_start"
    assert payload["raw_provider_status"] == "NOT_START"
    assert payload["canonical_scene_index"] == 1
    assert payload["canonical_task_selected"] == "same-task"


def test_failed_no_charge_terminal_disables_polling_and_final_rendering():
    job = _job(status="failed", terminal_state="failed_no_charge", progress_percent=65)
    payload = _scene_payload(
        terminal_state="failed_no_charge",
        final_decision="failed_no_charge",
        continue_polling=True,
        next_poll_scheduled=True,
        provider_error="provider_not_start",
    )

    result = connector._apply_pending_provider_dominance(payload, job=job)
    telemetry = queue.reconcile_provider_progress_telemetry(job, result, refresh_source="r18i_test")

    assert result["terminal_state"] == "failed_no_charge"
    assert result["final_decision"] == "failed_no_charge"
    assert result["continue_polling"] is False
    assert result["next_poll_scheduled"] is False
    assert telemetry["provider_task_alive"] is False
    assert telemetry["next_poll_scheduled"] is False
    assert telemetry["final_status_after_reconcile"] == "failed"


def test_real_in_progress_is_not_not_start():
    scene = _scene_payload(
        provider_status_payload_source="shopaikey.status",
        shopaikey_raw_status="IN_PROGRESS",
        shopaikey_data_status="IN_PROGRESS",
        raw_provider_status="IN_PROGRESS",
        provider_status_raw="IN_PROGRESS",
        blocker="provider_in_progress",
        provider_error="provider_in_progress",
    )
    policy = connector.product_video_scene_stall_policy(_job(), scene, 1)

    assert policy["current_scene_status"] == "provider_running"
    assert policy["provider_stalled_not_start"] is False
    assert policy["fallback_block_reason"] == "scene_not_stalled"


def test_r18g_basic_quote_semantics_still_source_locked():
    source = (ROOT / "tests" / "test_p0_video_r18g_key4u_family_endpoint_quote_consistency.py").read_text(encoding="utf-8")
    assert 'payload["user_visible_price_xu"] == 300' in source
    assert 'payload["persisted_quoted_price_xu"] == 300' in source
    assert 'payload["customer_charge_planned_xu"] == 300' in source
    assert 'payload["wallet_charge_amount_xu"] == 300' in source


def test_r18c_r18d_source_contracts_preserved():
    connector_source = (ROOT / "services" / "video_real_render_connector.py").read_text(encoding="utf-8")
    catalog_source = (ROOT / "services" / "video_provider_catalog.py").read_text(encoding="utf-8")
    routing_source = (ROOT / "config" / "product_video_model_routing.json").read_text(encoding="utf-8")
    assert "PRODUCT_VIDEO_RENDER_PIPELINE_HISTORICAL_CONCAT" in connector_source
    assert "PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S" in connector_source
    assert "resolve_product_video_model" in catalog_source
    assert "veo3.1-fast" in routing_source


def test_hidden_debug_status_recover_do_not_submit_provider():
    bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")
    assert "cmd_video_provider_job_debug" in bot_source
    assert "provider_submit_block_reason" in bot_source
    assert "public_user_final_confirm" in bot_source
    assert "debug/recover/status" not in bot_source


def test_no_real_provider_calls_in_r18i_tests():
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "urllib.request." + "urlopen",
        "provider" + "_smoke",
    )
    assert all(token not in source for token in forbidden)
