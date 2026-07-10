from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from services import remote_worker_api
from services import video_project_queue as queue
from services import video_provider_router as router
from services.video_provider_base import VideoGenerationRequest


ROOT = Path(__file__).resolve().parents[1]


class _FixtureAdapter:
    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name

    def capabilities(self) -> dict:
        return {
            "provider": self.provider_name,
            "configured": True,
            "capabilities": ["text_to_video", "scene_video", "multi_scene_video"],
        }


def _healthy(provider: str) -> dict:
    return {
        "provider": provider,
        "route_ready": True,
        "live_healthy": True,
        "recent_valid_output": True,
        "fresh_success": True,
        "health_status": "healthy",
        "provider_health_state": "healthy",
        "multi_scene_eligible": True,
        "provider_degraded_for_product_video_public": False,
    }


def _status_payload() -> dict:
    return {
        "provider_chain": ["fixture_alpha", "fixture_beta"],
        "effective_provider_chain": ["fixture_alpha", "fixture_beta"],
        "providers": [
            {
                "provider": "fixture_alpha",
                "enabled": True,
                "configured": True,
                "credit_ok": True,
                "submit_url_configured": True,
                "poll_url_configured": True,
                "auth_configured": True,
                "model_present": True,
            },
            {
                "provider": "fixture_beta",
                "enabled": True,
                "configured": True,
                "credit_ok": True,
                "submit_url_configured": True,
                "poll_url_configured": True,
                "auth_configured": True,
                "model_present": True,
            },
        ],
    }


def _zero_task_job(now: datetime, *, status: str = "processing") -> dict:
    return {
        "id": 127,
        "job_id": 127,
        "status": status,
        "scene_count": 2,
        "progress_percent": 55,
        "created_at": queue.now_text(now - timedelta(seconds=520)),
        "updated_at": queue.now_text(now - timedelta(seconds=1)),
        "source": "product_video",
        "product_video": True,
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "submit_source": "public_user_final_confirm",
    }


def _zero_task_result(*, candidates: list[str], elapsed: int = 520) -> dict:
    return {
        "scene_count": 2,
        "scene_tasks": [
            {"scene_index": 1, "status": "queued_waiting_for_dispatch", "dispatch_state": "queued_waiting_for_dispatch"},
            {"scene_index": 2, "status": "queued_waiting_for_dispatch", "dispatch_state": "queued_waiting_for_dispatch"},
        ],
        "preconfirm_candidate_keys": list(candidates),
        "runtime_candidate_keys": list(candidates),
        "provider_candidates_count": len(candidates),
        "provider_router_called": True,
        "provider_submit_called": True,
        "provider_elapsed_seconds": elapsed,
        "provider_attempts": [
            {
                "provider": "fixture_alpha",
                "submit_called": True,
                "provider_http_request_sent": False,
                "provider_http_status": 0,
                "submit_http_status": 0,
                "submit_accepted": False,
            }
        ],
    }


def test_cooldown_expiry_becomes_probation_and_old_success_cannot_restore_health():
    attempts = [
        {
            "provider": "fixture_alpha",
            "job_id": "old-valid",
            "scene_index": 1,
            "provider_task_id": "valid-old",
            "status": "SUCCESS",
            "clip_valid": True,
            "artifact_size": 1024,
            "updated_at_epoch": 100,
        },
        {
            "provider": "fixture_alpha",
            "job_id": "failed-a",
            "scene_index": 1,
            "provider_task_id": "failed-a",
            "status": "NOT_START",
            "provider_elapsed_seconds": 120,
            "updated_at_epoch": 500,
        },
        {
            "provider": "fixture_alpha",
            "job_id": "failed-b",
            "scene_index": 1,
            "provider_task_id": "failed-b",
            "status": "NOT_START",
            "provider_elapsed_seconds": 120,
            "updated_at_epoch": 510,
        },
    ]

    state = router.product_video_provider_public_degradation(
        "fixture_alpha",
        attempts,
        environ={
            "PRODUCT_VIDEO_PROVIDER_DEGRADED_DURATION_SECONDS": "60",
            "VIDEO_PROVIDER_HEALTH_SUCCESS_TTL_SECONDS": "1800",
        },
        now_epoch=700,
    )

    assert state["provider_health_state"] == "probation"
    assert state["probation"] is True
    assert state["fresh_success"] is False
    assert state["live_healthy"] is False
    assert state["multi_scene_eligible"] is False


def test_fresh_validated_scene_after_probation_restores_healthy_state():
    attempts = [
        {
            "provider": "fixture_alpha",
            "job_id": "failed-a",
            "scene_index": 1,
            "provider_task_id": "failed-a",
            "status": "NOT_START",
            "provider_elapsed_seconds": 120,
            "updated_at_epoch": 500,
        },
        {
            "provider": "fixture_alpha",
            "job_id": "failed-b",
            "scene_index": 1,
            "provider_task_id": "failed-b",
            "status": "NOT_START",
            "provider_elapsed_seconds": 120,
            "updated_at_epoch": 510,
        },
        {
            "provider": "fixture_alpha",
            "job_id": "fresh-valid",
            "scene_index": 1,
            "provider_task_id": "fresh-valid",
            "status": "SUCCESS",
            "clip_valid": True,
            "artifact_size": 4096,
            "updated_at_epoch": 701,
        },
    ]

    state = router.product_video_provider_public_degradation(
        "fixture_alpha",
        attempts,
        environ={
            "PRODUCT_VIDEO_PROVIDER_DEGRADED_DURATION_SECONDS": "60",
            "VIDEO_PROVIDER_HEALTH_SUCCESS_TTL_SECONDS": "1800",
        },
        now_epoch=720,
    )

    assert state["provider_health_state"] == "healthy"
    assert state["probation"] is False
    assert state["fresh_success"] is True
    assert state["live_healthy"] is True
    assert state["multi_scene_eligible"] is True


def test_preconfirm_and_runtime_use_the_same_eligibility_snapshot(monkeypatch):
    adapters = [_FixtureAdapter("fixture_alpha"), _FixtureAdapter("fixture_beta")]
    monkeypatch.setattr(router, "load_video_provider_adapters", lambda _env=None: adapters)
    health = {
        "fixture_alpha": {
            "provider_health_state": "degraded",
            "provider_degraded_for_product_video_public": True,
            "live_healthy": False,
        },
        "fixture_beta": _healthy("fixture_beta"),
    }
    status = _status_payload()
    preconfirm = router.product_video_provider_eligibility_snapshot(
        status=status,
        chain=status["provider_chain"],
        provider_health=health,
        contract_valid_provider_chain=status["provider_chain"],
        scene_count=2,
        require_live_health=True,
    )
    runtime = router.product_video_provider_eligibility_snapshot(
        status=status,
        chain=preconfirm["configured_provider_keys"],
        provider_health=health,
        contract_valid_provider_chain=preconfirm["contract_valid_provider_chain"],
        scene_count=2,
        require_live_health=True,
        persisted_snapshot_id=preconfirm["provider_eligibility_snapshot_id"],
    )
    gate = router.product_video_multi_scene_public_gate(
        2,
        health,
        effective_provider_chain=preconfirm["eligible_provider_keys"],
        contract_valid_provider_chain=preconfirm["contract_valid_provider_chain"],
        eligibility_snapshot=preconfirm,
        environ={"PRODUCT_VIDEO_MULTI_SCENE_PUBLIC_ENABLED": "true"},
    )

    assert preconfirm["eligible_provider_keys"] == ["fixture_beta"]
    assert runtime["eligible_provider_keys"] == preconfirm["eligible_provider_keys"]
    assert runtime["provider_eligibility_snapshot_id"] == preconfirm["provider_eligibility_snapshot_id"]
    assert gate["ok"] is True
    assert gate["final_eligible_provider_count"] == 1


def test_job127_zero_tasks_after_grace_fails_clean_without_fake_progress_or_fallback():
    now = datetime(2030, 1, 2, 3, 4, 5)
    job = _zero_task_job(now)
    result = _zero_task_result(candidates=[])

    watchdog = queue.product_video_zero_task_watchdog_state(job, result, now=now)
    ledger = queue.product_video_scene_ledger_state({}, job, result, now=now)
    telemetry = queue.reconcile_provider_progress_telemetry(job, result, now=now, refresh_source="r18s2_job127")

    assert watchdog["zero_task_watchdog_triggered"] is True
    assert watchdog["failed_no_charge"] is True
    assert watchdog["zero_task_terminal_reason"] == "no_eligible_provider_before_scene_dispatch"
    assert watchdog["provider_http_request_sent"] is False
    assert watchdog["provider_http_status"] == 0
    assert watchdog["fallback_count_effective"] == 0
    assert ledger["aggregate_job_status"] == "failed_no_charge"
    assert telemetry["zero_task_progress_guard"] is True
    assert telemetry["progress_suppressed_without_task"] is True
    assert telemetry["render_video_progress_percent"] == 0
    assert telemetry["final_progress_after_reconcile"] <= 20
    assert telemetry["final_status_after_reconcile"] == "failed"


def test_zero_tasks_under_grace_waits_in_preparation_without_fake_55_percent():
    now = datetime(2030, 1, 2, 3, 4, 5)
    job = _zero_task_job(now)
    job["created_at"] = queue.now_text(now - timedelta(seconds=10))
    result = _zero_task_result(candidates=[], elapsed=0)

    watchdog = queue.product_video_zero_task_watchdog_state(job, result, now=now)
    telemetry = queue.reconcile_provider_progress_telemetry(job, result, now=now, refresh_source="r18s2_under_grace")

    assert watchdog["zero_task_watchdog_triggered"] is False
    assert watchdog["failed_no_charge"] is False
    assert watchdog["dispatch_recovery_result"] == "waiting_for_dispatch_grace"
    assert telemetry["public_stage"] == "preparing"
    assert telemetry["render_video_progress_percent"] == 0
    assert telemetry["final_progress_after_reconcile"] <= 20


def test_processing_job_scene_claim_recovers_once_after_grace_and_respects_leases():
    now = datetime(2030, 1, 2, 3, 4, 5)
    job = _zero_task_job(now)
    result = _zero_task_result(candidates=["fixture_beta"])

    first = queue.product_video_processing_scene_claim_state(job, result, now=now, worker_id="worker-a")
    leased = queue.acquire_product_video_scene_dispatch_leases(job, result, worker_id="worker-a", now=now)
    second = queue.product_video_processing_scene_claim_state(job, leased, now=now, worker_id="worker-b")
    recovered = queue.product_video_processing_scene_claim_state(
        job,
        leased,
        now=now + timedelta(seconds=601),
        worker_id="worker-b",
    )

    assert first["processing_job_scene_claimable"] is True
    assert first["dispatch_recovery_attempted"] is True
    assert leased["scene_dispatch_lease_by_index"]["1"]["lease_owner"] == "worker-a"
    assert second["processing_job_scene_claimable"] is False
    assert second["claim_block_reason_by_scene"]["1"] == "scene_dispatch_lease_active"
    assert recovered["processing_job_scene_claimable"] is True
    assert recovered["stale_dispatch_lease_recovered"] is True


def test_existing_scene_task_cannot_be_claimed_or_resubmitted():
    now = datetime(2030, 1, 2, 3, 4, 5)
    job = _zero_task_job(now)
    result = _zero_task_result(candidates=["fixture_beta"])
    result["scene_tasks"][0].update(
        {
            "provider_task_id": "fixture-task-1",
            "active_task_id": "fixture-task-1",
            "status": "task_submitted",
            "dispatch_state": "task_submitted",
        }
    )

    state = queue.product_video_processing_scene_claim_state(job, result, now=now, worker_id="worker-b")

    assert state["scene_claimable_by_index"]["1"] is False
    assert state["claim_block_reason_by_scene"]["1"] == "scene_task_already_exists"
    assert state["scene_claimable_by_index"]["2"] is True


def test_processing_job_is_claimable_by_owner_worker_when_scene_is_undispatched():
    now = datetime(2030, 1, 2, 3, 4, 5)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        project = queue.create_video_project(
            conn,
            user_id=127,
            profile_id="video_trend",
            topic="fixture",
            asset_pack={
                "source": "product_video",
                "render_mode": "real",
                "provider_call": True,
                "public_user": True,
                "public_user_confirmed": True,
                "submit_source": "public_user_final_confirm",
                "scene_count": 2,
            },
        )
        queue.update_video_project(
            conn,
            int(project["project_id"]),
            status="processing",
            is_confirmed=1,
            scene_count=2,
            total_xu_estimated=300,
        )
        job = queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=127)
        result = _zero_task_result(candidates=["fixture_beta"])
        conn.execute(
            "UPDATE video_jobs SET status='processing', result_json=?, locked_by='', lease_expires_at=NULL, created_at=?, updated_at=? WHERE id=?",
            (json.dumps(result), queue.now_text(now - timedelta(seconds=520)), queue.now_text(now), int(job["id"])),
        )
        conn.commit()

        claimed = remote_worker_api.claim_remote_worker_product_video_job(
            conn,
            worker_id="owner-r18s2",
            owner_only=True,
            now=now,
        )
        duplicate = remote_worker_api.claim_remote_worker_product_video_job(
            conn,
            worker_id="owner-r18s2-second",
            owner_only=True,
            now=now + timedelta(seconds=1),
        )
        claim_detail = remote_worker_api.explain_product_video_claimability(
            conn,
            int(job["id"]),
            owner_only=True,
        )

        assert claimed
        assert duplicate == {}
        claimed_payload = json.loads(claimed["result_json"])
        assert claimed_payload["scene_dispatch_lease_by_index"]["1"]["lease_owner"] == "owner-r18s2"
        assert claim_detail["claimable"] is False
        assert claim_detail["reason"] == "processing_job_has_no_claimable_scene"
    finally:
        conn.close()


def test_no_candidate_runtime_diagnostic_never_sends_http(monkeypatch, tmp_path):
    status = {
        "provider_chain": ["fixture_alpha"],
        "effective_provider_chain": ["fixture_alpha"],
        "providers": [{"provider": "fixture_alpha", "enabled": True, "configured": False, "credit_ok": True}],
    }
    monkeypatch.setattr(router, "provider_status_payload", lambda _env=None: status)
    monkeypatch.setattr(router, "load_video_provider_adapters", lambda _env=None: [])
    result = router.run_provider_generation(
        VideoGenerationRequest(
            job_id="127-1",
            product_type="video_trend",
            video_flow_type="video_trend",
            prompt="fixture",
            duration_seconds=8,
            required_capability="text_to_video",
            metadata={
                "product_video": True,
                "provider_eligibility_snapshot": {
                    "provider_eligibility_snapshot_id": "fixture-snapshot",
                    "configured_provider_keys": ["fixture_alpha"],
                    "eligible_provider_keys": [],
                    "contract_valid_provider_chain": ["fixture_alpha"],
                },
                "preconfirm_candidate_keys": [],
                "runtime_candidate_keys": [],
            },
        ),
        output_dir=str(tmp_path),
        environ={"VIDEO_PROVIDER_CHAIN": "fixture_alpha"},
        sleep_func=lambda _seconds: None,
    )

    assert result["submit_orchestrator_invoked"] is True
    assert result["provider_http_request_sent"] is False
    assert result["provider_http_status"] == 0
    assert result["provider_key_selected"] == ""
    assert result["task_id_received"] is False
    assert result["fallback_count_effective"] == 0


def test_worker_payload_preserves_snapshot_and_does_not_count_queued_scenes_as_submitted():
    snapshot = {
        "provider_eligibility_snapshot_id": "fixture-snapshot",
        "configured_provider_keys": ["fixture_beta"],
        "eligible_provider_keys": ["fixture_beta"],
        "runtime_candidate_keys": ["fixture_beta"],
        "contract_valid_provider_chain": ["fixture_beta"],
    }
    persisted = {
        "scene_count": 2,
        "orchestration_mode": "per_scene_8s",
        "provider_eligibility_snapshot": snapshot,
        "provider_eligibility_snapshot_id": "fixture-snapshot",
        "preconfirm_candidate_keys": ["fixture_beta"],
        "runtime_candidate_keys": ["fixture_beta"],
        "selected_provider": "fixture_beta",
        "selected_model": "fixture-model",
        "provider_model_map": {"fixture_beta": "fixture-model"},
        "scene_tasks": [
            {"scene_index": 1, "status": "queued_waiting_for_dispatch", "dispatch_state": "queued_waiting_for_dispatch"},
            {"scene_index": 2, "status": "queued_waiting_for_dispatch", "dispatch_state": "queued_waiting_for_dispatch"},
        ],
    }
    asset_pack = {
        "source": "product_video",
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "scene_count": 2,
        "provider_eligibility_snapshot": snapshot,
    }
    payload = remote_worker_api.build_worker_job_payload(
        {
            "id": 127,
            "project_id": 1270,
            "user_id": 127,
            "job_type": "video_render",
            "status": "processing",
            "result_json": json.dumps(persisted),
            "project": {
                "project_id": 1270,
                "user_id": 127,
                "status": "processing",
                "profile_id": "video_trend",
                "topic": "fixture",
                "ratio": "9:16",
                "scene_count": 2,
                "asset_pack_json": json.dumps(asset_pack),
                "invoice_json": json.dumps({"scene_count": 2}),
                "addon_plan_json": "{}",
            },
            "scenes": [],
        }
    )

    assert payload["provider_eligibility_snapshot_id"] == "fixture-snapshot"
    assert payload["preconfirm_candidate_keys"] == ["fixture_beta"]
    assert payload["runtime_candidate_keys"] == ["fixture_beta"]
    assert payload["provider_order"] == ["fixture_beta"]
    assert payload["scene_tasks_submitted"] == 0
    assert payload["scene_tasks_submitted_count"] == 0
    assert [item["status"] for item in payload["scene_tasks"]] == [
        "queued_waiting_for_dispatch",
        "queued_waiting_for_dispatch",
    ]


def test_r18s2_source_contract_keeps_scope_and_tests_provider_free():
    test_source = Path(__file__).read_text(encoding="utf-8")
    router_source = (ROOT / "services" / "video_provider_router.py").read_text(encoding="utf-8")
    queue_source = (ROOT / "services" / "video_project_queue.py").read_text(encoding="utf-8")
    worker_api_source = (ROOT / "services" / "remote_worker_api.py").read_text(encoding="utf-8")
    connector_source = (ROOT / "services" / "video_real_render_connector.py").read_text(encoding="utf-8")

    for marker in (
        "product_video_provider_eligibility_snapshot",
        "provider_health_state",
        "submit_orchestrator_invoked",
        "provider_http_request_sent",
    ):
        assert marker in router_source
    for marker in (
        "product_video_zero_task_watchdog_state",
        "queued_waiting_for_dispatch",
        "no_eligible_provider_before_scene_dispatch",
    ):
        assert marker in queue_source
    assert "processing_job_scene_claimable" in worker_api_source
    assert '"provider_eligibility_snapshot": _meta_value("provider_eligibility_snapshot")' in connector_source
    forbidden = (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "urllib.request." + "urlopen",
        "provider" + "_smoke",
    )
    assert all(token not in test_source for token in forbidden)
