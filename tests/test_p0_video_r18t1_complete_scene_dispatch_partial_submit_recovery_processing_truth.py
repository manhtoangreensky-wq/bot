from __future__ import annotations

from pathlib import Path

from providers.video_generic_http_provider import GenericHttpVideoProvider
from services import product_progress_status
from services import video_project_queue as queue
from services import video_provider_router as router
from services import video_real_render_connector as connector
from services.video_provider_base import VideoGenerationRequest


ROOT = Path(__file__).resolve().parents[1]


def _job125(*, status: str = "failed") -> tuple[dict, dict]:
    job = {
        "id": 125,
        "job_id": 125,
        "status": status,
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
        "provider_order": "shopaikey_video,key4u_video",
    }
    result = {
        "job_id": 125,
        "scene_count": 2,
        "terminal_state": "failed_no_charge",
        "final_decision": "failed_no_charge",
        "charged_xu": 0,
        "final_delivered": False,
        "concat_attempted": False,
        "scene_tasks": [
            {
                "scene_index": 1,
                "provider": "shopaikey_video",
                "provider_task_id": "task-scene-1-spBx",
                "active_task_id": "task-scene-1-spBx",
                "status": "provider_running",
                "provider_status_raw": "IN_PROGRESS",
                "provider_progress_raw": 30,
                "provider_elapsed_seconds": 59,
                "submit_accepted": True,
                "submit_http_status": 500,
                "transport_http": 500,
                "task_id_present": True,
                "task_pollable": True,
                "effective_submit_outcome": "accepted",
                "transport_anomaly": True,
                "transport_anomaly_ignored_due_to_valid_task": True,
                "dispatch_state": "task_submitted",
            },
            {
                "scene_index": 2,
                "status": "pending_submit",
                "dispatch_state": "submit_in_progress",
                "dispatch_attempted": False,
            },
        ],
    }
    return job, result


def _pending_diagnostic(scene_index: int) -> dict:
    return {
        "ok": False,
        "scene_index": scene_index,
        "scene_id": scene_index,
        "provider": "shopaikey_video",
        "selected_provider": "shopaikey_video",
        "provider_task_ids": [f"task-{scene_index}"],
        "provider_task_id_saved": True,
        "task_id_present": True,
        "task_pollable": True,
        "submit_accepted": True,
        "effective_submit_outcome": "accepted",
        "status": "provider_running",
        "provider_status": "running",
        "continue_polling": True,
        "dispatch_state": "task_submitted",
        "dispatch_attempted": scene_index == 2,
        "scene_dispatch_idempotency_key": f"dispatch-{scene_index}",
        "no_charge": True,
    }


def test_job125_ledger_recovers_missing_scene_without_resubmitting_active_scene():
    job, result = _job125()
    ledger = queue.product_video_scene_ledger_state({}, job, result)

    assert ledger["required_scene_indexes"] == [1, 2]
    assert ledger["dispatched_scene_indexes"] == [1]
    assert ledger["undispatched_scene_indexes"] == [2]
    assert ledger["dispatchable_scene_indexes"] == [2]
    assert ledger["scene_dispatch_state_by_index"]["1"] == "task_submitted"
    assert ledger["scene_dispatch_state_by_index"]["2"] == "submit_in_progress"
    assert ledger["aggregate_job_status"] == "processing_scenes"
    assert ledger["terminal_state"] == "final_rendering"
    assert ledger["continue_polling"] is True
    assert ledger["concat_attempted"] is False
    assert ledger["delivery_blocked_by_scene_coverage"] is True


def test_job125_processing_truth_overrides_stale_failed_persistence_and_public_panel():
    job, result = _job125()
    telemetry = queue.reconcile_provider_progress_telemetry(job, result, refresh_source="r18t1_job125")
    board = product_progress_status.video_per_scene_progress_board_text({**result, **telemetry})

    assert telemetry["final_status_after_reconcile"] == "processing"
    assert telemetry["processing_truth_applied"] is True
    assert telemetry["stale_persisted_failure_cleared"] is True
    assert telemetry["provider_state_overrode_persisted_status"] is True
    assert telemetry["refresh_terminal_suppressed"] is True
    assert "Cảnh 1/2: Đang tạo" in board
    assert "Cảnh 2/2: Đang chờ bắt đầu" in board
    assert "Gửi kết quả: Chưa bắt đầu" in board
    assert "Chưa tạo được" not in board


def test_valid_task_id_wins_over_transport_http_anomaly_but_missing_task_does_not():
    accepted = router.product_video_submit_response_truth(
        provider_accepted=True,
        provider_task_id="task-spBx",
        transport_http=500,
    )
    failed = router.product_video_submit_response_truth(
        provider_accepted=False,
        provider_task_id="",
        transport_http=500,
    )

    assert accepted["effective_submit_accepted"] is True
    assert accepted["task_pollable"] is True
    assert accepted["transport_anomaly_ignored_due_to_valid_task"] is True
    assert failed["effective_submit_accepted"] is False
    assert failed["task_pollable"] is False


def test_http_500_with_parsed_task_id_polls_instead_of_resubmitting(monkeypatch, tmp_path):
    calls: list[str] = []

    def fake_open(self, _url, payload=None, *, method="POST", timeout=90):
        del self, payload, timeout
        calls.append(method)
        if method == "POST":
            return {
                "ok": False,
                "status_code": 500,
                "body": {"task_id": "task-spBx", "status": "IN_PROGRESS"},
                "response_shape": {"type": "dict", "top_level_keys": ["task_id", "status"], "nested_keys": []},
            }
        return {
            "ok": True,
            "status_code": 200,
            "body": {"task_id": "task-spBx", "status": "IN_PROGRESS"},
            "response_shape": {"type": "dict", "top_level_keys": ["task_id", "status"], "nested_keys": []},
        }

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open)
    env = {
        "VIDEO_PROVIDER_CHAIN": "shopaikey_video",
        "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1",
        "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS": "0",
        "SHOPAIKEY_VIDEO_ENABLED": "1",
        "SHOPAIKEY_VIDEO_SUBMIT_URL": "https://fixture.invalid/submit",
        "SHOPAIKEY_VIDEO_POLL_URL": "https://fixture.invalid/status/{task_id}",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE": "Bearer fixture",
        "SHOPAIKEY_VIDEO_MODEL": "veo3.1-fast",
        "SHOPAIKEY_VIDEO_CAPABILITIES": "text_to_video",
    }
    request = VideoGenerationRequest(
        job_id="job-125-scene-1",
        product_type="video_ai_prompt",
        video_flow_type="video_ai_prompt",
        prompt="fixture scene",
        ratio="9:16",
        duration_seconds=8,
        required_capability="text_to_video",
        metadata={"product_video": True, "allow_provider_pending": True},
    )
    result = router.run_provider_generation(request, output_dir=str(tmp_path), environ=env, sleep_func=lambda _seconds: None)

    assert calls == ["POST", "GET"]
    assert result["submit_accepted"] is True
    assert result["task_id_present"] is True
    assert result["task_pollable"] is True
    assert result["transport_anomaly_ignored_due_to_valid_task"] is True
    assert result["continue_polling"] is True
    assert result["provider_task_ids"] == ["task-spBx"]


def test_original_confirm_authorizes_one_in_budget_fallback_but_never_price_increase():
    base = {
        "submit_source": "public_user_final_confirm",
        "original_submit_source": "public_user_final_confirm",
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "user_visible_price_xu": 300,
        "persisted_quoted_price_xu": 300,
        "customer_charge_planned_xu": 300,
        "provider_budget_xu": 400,
        "fallback_candidate_prevalidated": True,
    }
    allowed = router.product_video_controlled_fallback_policy("provider_submit_failed", base)
    blocked = router.product_video_controlled_fallback_policy(
        "provider_submit_failed",
        {**base, "fallback_provider_cost_xu": 401},
    )

    assert allowed["original_job_confirmation_valid_for_fallback"] is True
    assert allowed["fallback_within_persisted_budget"] is True
    assert allowed["fallback_submit_allowed"] is True
    assert blocked["fallback_allowed"] is False
    assert blocked["fallback_requires_new_price"] is True
    assert blocked["fallback_budget_block_reason"] == "fallback_exceeds_persisted_budget"


def test_parallel_dispatch_continues_to_scene_two_after_scene_one_task_persists(monkeypatch, tmp_path):
    calls: list[int] = []
    monkeypatch.setattr(
        connector,
        "real_video_scene_plan",
        lambda _job: {"scenes": [{"scene_id": 1, "video_prompt": "one"}, {"scene_id": 2, "video_prompt": "two"}]},
    )

    async def fake_render(scene, _raw_path, _order):
        calls.append(int(scene.scene_id))
        raise connector.RealVideoRenderError("provider_in_progress", diagnostics=_pending_diagnostic(int(scene.scene_id)))

    monkeypatch.setattr(connector, "_render_scene_async", fake_render)
    result = connector._run_per_scene_provider_orchestrator(
        {"id": 125, "job_id": 125, "source": "product_video", "product_video": True, "scene_count": 2},
        str(tmp_path),
        provider_order=["shopaikey_video"],
        provider_events=[],
        debug_results=[],
    )

    assert calls == [1, 2]
    assert result["scene_tasks_submitted"] == 2
    assert result["aggregate_job_status"] == "processing_scenes"
    assert result["continue_polling"] is True
    assert result["concat_attempted"] is False


def test_sequential_dispatch_records_explicit_wait_for_missing_scene(monkeypatch, tmp_path):
    calls: list[int] = []
    monkeypatch.setattr(
        connector,
        "real_video_scene_plan",
        lambda _job: {"scenes": [{"scene_id": 1, "video_prompt": "one"}, {"scene_id": 2, "video_prompt": "two"}]},
    )

    async def fake_render(scene, _raw_path, _order):
        calls.append(int(scene.scene_id))
        raise connector.RealVideoRenderError("provider_in_progress", diagnostics=_pending_diagnostic(int(scene.scene_id)))

    monkeypatch.setattr(connector, "_render_scene_async", fake_render)
    result = connector._run_per_scene_provider_orchestrator(
        {
            "id": 125,
            "job_id": 125,
            "source": "product_video",
            "product_video": True,
            "scene_count": 2,
            "scene_dispatch_mode": "sequential",
            "scene_tasks": [{"scene_index": 1, "provider_task_id": "task-1", "status": "provider_running"}],
        },
        str(tmp_path),
        provider_order=["shopaikey_video"],
        provider_events=[],
        debug_results=[],
    )

    assert calls == [1]
    assert result["scene_dispatch_state_by_index"]["2"] == "submit_in_progress"
    assert result["scene_dispatch_block_reason_by_index"]["2"] == "scheduled_after_scene_1_progress"
    assert result["continue_polling"] is True


def test_all_scenes_exhausted_is_terminal_but_partial_coverage_never_delivers():
    job, result = _job125(status="processing")
    result["scene_tasks"] = [
        {"scene_index": 1, "status": "failed", "dispatch_state": "exhausted", "exhausted": True},
        {"scene_index": 2, "status": "failed", "dispatch_state": "exhausted", "exhausted": True},
    ]
    ledger = queue.product_video_scene_ledger_state({}, job, result)

    assert ledger["aggregate_job_status"] == "failed_no_charge"
    assert ledger["continue_polling"] is False
    assert ledger["final_delivered"] is False
    assert ledger["artifact_valid_for_charge_after_coverage"] is False


def test_r18t1_public_status_and_debug_stay_read_only_and_provider_free():
    bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")
    router_source = (ROOT / "services" / "video_provider_router.py").read_text(encoding="utf-8")
    this_source = Path(__file__).read_text(encoding="utf-8")

    assert "processing_truth_applied" in bot_source
    assert "dispatchable_scene_indexes" in bot_source
    assert "product_video_submit_response_truth" in router_source
    for forbidden in ("SHOPAIKEY" + "_API_KEY", "KEY4U" + "_API_KEY", "url" + "open", "provider" + "_smoke"):
        assert forbidden not in this_source
