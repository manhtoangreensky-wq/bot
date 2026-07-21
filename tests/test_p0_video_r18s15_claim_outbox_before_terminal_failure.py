from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import product_progress_status
from services import remote_worker_api
from services import video_project_queue as queue
from services import video_provider_router as router
from services import video_real_render_connector as connector


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 7, 13, 2, 0, 0, tzinfo=timezone.utc)


class _Adapter:
    def __init__(self, name: str) -> None:
        self.provider_name = name

    def capabilities(self) -> dict:
        return {
            "provider": self.provider_name,
            "configured": True,
            "capabilities": ["text_to_video", "scene_video", "multi_scene_video"],
        }


def _status() -> dict:
    return {
        "effective_provider_chain": ["shopaikey_video", "key4u_video"],
        "providers": [
            {
                "provider": name,
                "enabled": True,
                "configured": True,
                "credit_ok": True,
                "submit_url_configured": True,
                "poll_url_configured": True,
                "auth_configured": True,
                "model_present": True,
            }
            for name in ("shopaikey_video", "key4u_video")
        ],
    }


def _health() -> dict:
    return {
        "shopaikey_video": {
            "route_ready": True,
            "live_healthy": False,
            "provider_health_state": "degraded",
            "provider_degraded_for_product_video_public": True,
        },
        "key4u_video": {
            "route_ready": True,
            "live_healthy": False,
            "provider_health_state": "unknown",
        },
    }


@pytest.fixture(autouse=True)
def _provider_fixtures(monkeypatch):
    monkeypatch.setattr(router, "provider_status_payload", lambda _env=None: _status())
    monkeypatch.setattr(
        router,
        "load_video_provider_adapters",
        lambda _env=None: [_Adapter("shopaikey_video"), _Adapter("key4u_video")],
    )
    monkeypatch.setattr(
        router,
        "product_video_submit_switch_detail",
        lambda _env=None: {"resolved": True, "raw": "1", "source": "fixture"},
    )


def _payload() -> dict:
    return {
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "product_type": "video_trend",
        "engine_adapter": "text_to_video",
        "required_capability": "text_to_video_or_scene_video",
        "orchestration_mode": "per_scene_8s",
        "scene_count": 2,
        "scenes_total": 2,
        "duration_seconds": 16,
        "admission_enforced": True,
        "admission_mode": queue.PRODUCT_VIDEO_PROBATION_ADMISSION_MODE,
        "admission_snapshot_id": "job-136-admission",
        "provider_eligibility_snapshot_id": "job-136-admission",
        "provider_eligibility_snapshot": {
            "provider_eligibility_snapshot_id": "job-136-admission",
            "configured_provider_keys": ["shopaikey_video", "key4u_video"],
            "contract_valid_provider_chain": ["shopaikey_video", "key4u_video"],
        },
        "configured_provider_chain": ["shopaikey_video", "key4u_video"],
        "contract_valid_provider_chain": ["shopaikey_video", "key4u_video"],
        "runtime_candidate_keys": ["shopaikey_video"],
        "preconfirm_candidate_keys": ["shopaikey_video"],
        "admission_candidate_keys": ["shopaikey_video"],
        "provider_health_at_submit": _health(),
        "provider_hard_block_reason_by_provider": {
            "key4u_video": "provider_model_interface_contract_invalid"
        },
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "original_submit_source": "public_user_final_confirm",
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "worker_compatible": True,
        "worker_connected": True,
        "public_provider_freeze": False,
        "hidden_submit_freeze": True,
        "probation_lock_clear": False,
        "probation_candidate_key": "shopaikey_video",
        "probation_candidate_selected": "shopaikey_video",
        "probation_job_id": 136,
        "probation_result": "pending",
        "selected_provider": "shopaikey_video",
        "selected_model": "veo3.1-fast",
        "selected_provider_interface": "text_to_video",
        "scene_tasks": queue.product_video_initial_scene_tasks(136, 2),
        "charge_policy": "after_valid_mp4_delivery",
        "charge": 0,
        "charged_xu": 0,
    }


def _job136_db(tmp_path: Path, *, available_at: datetime | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "r18s15-job136.db")
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    shared = {
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "product_type": "video_trend",
        "engine_adapter": "text_to_video",
        "orchestration_mode": "per_scene_8s",
        "scene_count": 2,
        "duration_seconds": 16,
    }
    project = queue.create_video_project(
        conn,
        user_id=1360,
        profile_id="video_trend",
        topic="job #136 fixture",
        ratio="9:16",
        asset_pack=shared,
    )
    old_project = int(project["project_id"])
    conn.execute("UPDATE video_projects SET project_id=134 WHERE project_id=?", (old_project,))
    queue.update_video_project(
        conn,
        134,
        status="queued_for_worker",
        invoice_json={
            **shared,
            "package_xu": 300,
            "user_visible_price_xu": 300,
            "persisted_quoted_price_xu": 300,
            "customer_charge_planned_xu": 300,
        },
        scene_count=2,
        total_xu_estimated=300,
        is_confirmed=1,
    )
    job = queue.enqueue_video_render_job(conn, project_id=134, user_id=1360, max_attempts=3)
    old_job = int(job["id"])
    conn.execute("UPDATE video_jobs SET id=136 WHERE id=?", (old_job,))
    conn.execute("UPDATE video_projects SET job_id=136 WHERE project_id=134")
    created = queue.now_text(NOW - timedelta(minutes=3))
    conn.execute(
        """UPDATE video_jobs
              SET result_json=?,status='queued',locked_by='',locked_at=NULL,lease_expires_at=NULL,
                  created_at=?,updated_at=?,progress_percent=10,progress_message='queued_waiting_for_dispatch'
            WHERE id=136""",
        (json.dumps(_payload()), created, created),
    )
    for index in (1, 2):
        conn.execute(
            "INSERT INTO video_scenes(project_id,scene_index,role,scene_status) VALUES (?,?,?,?)",
            (134, index, "product_video_scene", "pending"),
        )
    queue.ensure_product_video_dispatch_outbox(
        conn,
        job_id=136,
        project_id=134,
        scene_indexes=[1, 2],
        now=NOW - timedelta(minutes=1),
    )
    conn.execute("UPDATE video_dispatch_outbox SET outbox_id=9 WHERE job_id=136")
    due = available_at or NOW - timedelta(seconds=1)
    conn.execute(
        """UPDATE video_dispatch_outbox
              SET dispatch_status='retry_wait',available_at=?,attempt_count=0,last_error='',
                  lease_owner='',lease_expires_at=NULL WHERE outbox_id=9""",
        (queue.product_video_outbox_time_text(due),),
    )
    conn.commit()
    return conn


def _runtime(conn: sqlite3.Connection) -> dict:
    job = queue.get_video_render_job(conn, 136)
    project = queue.get_video_project(conn, 134)
    result = json.loads(job["result_json"])
    return remote_worker_api._product_video_runtime_eligibility(
        job,
        result,
        project,
        now=NOW,
        conn=conn,
    )


def _premature_terminal(conn: sqlite3.Connection) -> None:
    result = json.loads(queue.get_video_render_job(conn, 136)["result_json"])
    reason = "dispatch_not_started_dispatch_outbox_job_not_claimable"
    result.update(
        {
            "terminal_state": "failed_no_charge",
            "canonical_status": "failed_no_charge",
            "final_decision": "failed_no_charge",
            "continue_polling": False,
            "dispatch_outbox_status": "terminal_failed",
            "dispatch_outbox_terminal_reason": reason,
            "dispatch_terminal_failure_reason": reason,
            "provider_submit_called": False,
            "provider_http_request_sent": False,
            "provider_router_called": False,
            "charge": 0,
            "charged_xu": 0,
        }
    )
    conn.execute(
        "UPDATE video_jobs SET status='failed',result_json=?,last_error=?,completed_at=? WHERE id=136",
        (json.dumps(result), reason, queue.now_text(NOW)),
    )
    conn.execute(
        "UPDATE video_projects SET status='failed',video_terminal_state='failed_no_charge',error_log=? WHERE project_id=134",
        (reason,),
    )
    conn.execute(
        "UPDATE video_dispatch_outbox SET dispatch_status='terminal_failed',terminal_reason=?,last_error=? WHERE outbox_id=9",
        (reason, "dispatch_outbox_job_not_claimable"),
    )
    conn.execute("UPDATE video_scenes SET scene_status='terminal_failed' WHERE project_id=134")
    conn.commit()


def _mock_two_scene_render(monkeypatch, job: dict) -> list[str]:
    submitted: list[str] = []

    def fake_generation(request, *, output_dir, environ):
        del environ
        submitted.append(str(request.job_id))
        output = Path(output_dir) / f"{request.job_id}.mp4"
        output.write_bytes(b"fixture-mp4")
        return {
            "ok": True,
            "provider": "shopaikey_video",
            "output_path": str(output),
            "provider_task_ids": [f"task-{request.job_id}"],
            "provider_task_id_saved": True,
            "result_url_present": True,
            "output_duration": 8,
            "provider_router_called": True,
        }

    monkeypatch.setattr(connector, "run_provider_generation", fake_generation)
    monkeypatch.setattr(connector, "ensure_video_output", lambda path: str(path))
    payload = json.loads(job["result_json"])
    scene_job = {**job, **payload, "job_id": "136", "runtime_candidate_keys": ["shopaikey_video"]}
    scenes = [
        SimpleNamespace(
            scene_id=index,
            video_prompt=f"Scene {index}",
            visual_prompt=f"Scene {index}",
            aspect_ratio="9:16",
            target_duration_sec=8,
            _toan_aas_job=scene_job,
        )
        for index in (1, 2)
    ]
    temp_root = ROOT / ".pytest_tmp"
    temp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp_root) as tmp_dir:
        for scene in scenes:
            result = asyncio.run(
                connector._render_scene_async(
                    scene,
                    str(Path(tmp_dir) / f"scene-{scene.scene_id}.mp4"),
                    [],
                )
            )
            assert result["provider_router_called"] is True
    return submitted


def test_r18s15_due_outbox_claimed_before_terminal_failure(tmp_path):
    conn = _job136_db(tmp_path)
    claimed = remote_worker_api.claim_remote_worker_product_video_job(
        conn, worker_id="owner-product-video", owner_only=True, now=NOW
    )
    assert claimed["id"] == 136
    assert queue.get_video_render_job(conn, 136)["status"] == "processing"


def test_r18s15_no_terminal_failure_before_first_due_claim(tmp_path):
    conn = _job136_db(tmp_path, available_at=NOW + timedelta(seconds=20))
    report = queue.sweep_product_video_zero_task_watchdog(
        conn,
        now=NOW,
        job_id=136,
        eligibility_evaluator=lambda *_args: {"runtime_candidate_keys": []},
    )
    assert report["terminal_failed"] == 0
    assert queue.get_video_render_job(conn, 136)["status"] == "queued"


def test_r18s15_retryable_outbox_keeps_job_queued(tmp_path):
    conn = _job136_db(tmp_path)
    claimed = queue.claim_product_video_dispatch_outbox(conn, worker_id="owner", now=NOW)
    assert claimed
    assert queue.retry_product_video_dispatch_outbox(
        conn,
        outbox_id=9,
        worker_id="owner",
        error="dispatch_outbox_job_not_claimable",
        now=NOW,
    )
    assert queue.get_video_render_job(conn, 136)["status"] == "queued"
    assert queue.get_product_video_dispatch_outbox(conn, job_id=136)["dispatch_status"] == "retry_wait"


def test_r18s15_terminal_failure_only_after_retry_exhaustion(tmp_path):
    conn = _job136_db(tmp_path)
    for attempt in range(3):
        attempt_at = NOW + timedelta(seconds=16 * attempt)
        assert queue.claim_product_video_dispatch_outbox(conn, worker_id="owner", now=attempt_at)
        assert queue.retry_product_video_dispatch_outbox(
            conn,
            outbox_id=9,
            worker_id="owner",
            error="dispatch_outbox_job_not_claimable",
            now=attempt_at,
        )
        if attempt < 2:
            assert queue.get_video_render_job(conn, 136)["status"] == "queued"
    assert queue.get_video_render_job(conn, 136)["status"] == "failed"


def test_r18s15_terminal_failure_has_explicit_reason(tmp_path):
    conn = _job136_db(tmp_path)
    conn.execute(
        "UPDATE video_dispatch_outbox SET dispatch_status='leased',lease_owner='owner',attempt_count=3,last_attempt_at=? WHERE outbox_id=9",
        (queue.product_video_outbox_time_text(NOW),),
    )
    conn.commit()
    queue.retry_product_video_dispatch_outbox(
        conn, outbox_id=9, worker_id="owner", error="dispatch_outbox_job_not_claimable", now=NOW
    )
    result = json.loads(queue.get_video_render_job(conn, 136)["result_json"])
    assert result["provider_submit_block_reason"].startswith("dispatch_not_started_")
    assert result["dispatch_terminal_transition_source"] == "dispatch_claim_retry_exhausted"


def test_r18s15_job136_premature_failure_recoverable(tmp_path):
    conn = _job136_db(tmp_path)
    _premature_terminal(conn)
    state = queue.product_video_premature_dispatch_failure_state(
        queue.get_video_render_job(conn, 136),
        queue.get_video_project(conn, 134),
        json.loads(queue.get_video_render_job(conn, 136)["result_json"]),
        queue.get_product_video_dispatch_outbox(conn, job_id=136),
    )
    assert state["premature_dispatch_failure_recoverable"] is True


def test_r18s15_job136_due_outbox_claimed(tmp_path):
    conn = _job136_db(tmp_path)
    _premature_terminal(conn)
    claimed = remote_worker_api.claim_remote_worker_product_video_job(
        conn, worker_id="owner-product-video", owner_only=True, now=NOW
    )
    assert claimed["id"] == 136


def test_r18s15_job136_router_called_once(tmp_path, monkeypatch):
    conn = _job136_db(tmp_path)
    _premature_terminal(conn)
    claimed = remote_worker_api.claim_remote_worker_product_video_job(
        conn, worker_id="owner-product-video", owner_only=True, now=NOW
    )
    submitted = _mock_two_scene_render(monkeypatch, claimed)
    assert submitted == ["136-1", "136-2"]


def test_r18s15_job136_two_scenes_submitted_once_each(tmp_path, monkeypatch):
    conn = _job136_db(tmp_path)
    claimed = remote_worker_api.claim_remote_worker_product_video_job(
        conn, worker_id="owner-product-video", owner_only=True, now=NOW
    )
    submitted = _mock_two_scene_render(monkeypatch, claimed)
    assert submitted.count("136-1") == submitted.count("136-2") == 1


def test_r18s15_real_provider_terminal_failure_not_reopened(tmp_path):
    conn = _job136_db(tmp_path)
    _premature_terminal(conn)
    result = json.loads(queue.get_video_render_job(conn, 136)["result_json"])
    result.update({"provider_submit_called": True, "provider_task_id": "real-task"})
    conn.execute("UPDATE video_jobs SET result_json=? WHERE id=136", (json.dumps(result),))
    conn.commit()
    recovered = queue.recover_product_video_premature_dispatch_failure(conn, job_id=136, now=NOW)
    assert recovered["premature_dispatch_recovered"] is False
    assert recovered["premature_dispatch_recovery_block_reason"] == "genuine_provider_terminal_failure"


def test_r18s15_recovery_idempotent(tmp_path):
    conn = _job136_db(tmp_path)
    _premature_terminal(conn)
    first = queue.recover_product_video_premature_dispatch_failure(conn, job_id=136, now=NOW)
    second = queue.recover_product_video_premature_dispatch_failure(conn, job_id=136, now=NOW)
    assert first["premature_dispatch_recovered"] is True
    assert second["premature_dispatch_recovered"] is False


def test_r18s15_failed_job_cannot_render_processing_without_recovery(tmp_path):
    conn = _job136_db(tmp_path)
    _premature_terminal(conn)
    stale_result = json.loads(queue.get_video_render_job(conn, 136)["result_json"])
    stale_result["provider_task_id"] = "stale-task-id"
    authority = queue.product_video_dispatch_status_authority(
        queue.get_video_render_job(conn, 136),
        stale_result,
        queue.get_product_video_dispatch_outbox(conn, job_id=136),
    )
    assert authority["dispatch_canonical_status"] == "failed_no_charge"


def test_r18s15_retry_wait_renders_queued_truth(tmp_path):
    conn = _job136_db(tmp_path)
    authority = queue.product_video_dispatch_status_authority(
        queue.get_video_render_job(conn, 136), _payload(), queue.get_product_video_dispatch_outbox(conn, job_id=136)
    )
    assert authority["dispatch_canonical_status"] == "queued"


def test_r18s15_claimed_outbox_renders_processing_truth(tmp_path):
    conn = _job136_db(tmp_path)
    queue.claim_product_video_dispatch_outbox(conn, worker_id="owner", now=NOW)
    authority = queue.product_video_dispatch_status_authority(
        queue.get_video_render_job(conn, 136), _payload(), queue.get_product_video_dispatch_outbox(conn, job_id=136)
    )
    assert authority["dispatch_canonical_status"] == "processing"


def test_r18s15_exhausted_dispatch_renders_failed_no_charge(tmp_path):
    conn = _job136_db(tmp_path)
    _premature_terminal(conn)
    diagnostic = queue.product_video_dispatch_outbox_diagnostic(conn, job_id=136, now=NOW)
    assert diagnostic["dispatch_canonical_status"] == "failed_no_charge"


def test_r18s15_valid_shopaikey_model_contract_not_rejected(tmp_path):
    conn = _job136_db(tmp_path)
    runtime = _runtime(conn)
    assert runtime["selected_probation_contract_valid"] is True
    assert runtime["runtime_candidate_keys"] == ["shopaikey_video"]
    assert runtime["selected_probation_contract_reject_reason"] == ""


def test_r18s15_invalid_contract_not_selected_as_probation(tmp_path):
    conn = _job136_db(tmp_path)
    result = json.loads(queue.get_video_render_job(conn, 136)["result_json"])
    result["selected_model"] = "missing-model"
    result["contract_valid_provider_chain"] = ["key4u_video"]
    result["provider_eligibility_snapshot"]["contract_valid_provider_chain"] = ["key4u_video"]
    conn.execute("UPDATE video_jobs SET result_json=? WHERE id=136", (json.dumps(result),))
    conn.commit()
    runtime = _runtime(conn)
    assert runtime["selected_probation_contract_valid"] is False
    assert "shopaikey_video" not in runtime["runtime_candidate_keys"]


def test_r18s15_rejection_reason_is_provider_specific():
    evaluated = router.product_video_provider_eligibility_snapshot(
        status=_status(),
        chain=["shopaikey_video", "key4u_video"],
        required_capability="text_to_video_or_scene_video",
        provider_health=_health(),
        contract_valid_provider_chain=["shopaikey_video"],
        scene_count=2,
        allow_public_confirmed_probation=True,
        allow_operational_degradation_probation=True,
        admission_source="public_user_final_confirm",
        public_user_confirmed=True,
        public_submit_enabled=True,
        worker_compatible=True,
        probation_lock_clear=True,
    )
    assert evaluated["probation_candidate_selected"] == "shopaikey_video"
    assert evaluated["probation_reject_reason"] == ""
    assert "provider_model_interface_contract_invalid" in evaluated["hard_block_reason_by_provider"]["key4u_video"]


def test_r18s15_router_receives_selected_probation_provider(tmp_path, monkeypatch):
    conn = _job136_db(tmp_path)
    claimed = remote_worker_api.claim_remote_worker_product_video_job(
        conn, worker_id="owner-product-video", owner_only=True, now=NOW
    )
    submitted = _mock_two_scene_render(monkeypatch, claimed)
    assert len(submitted) == 2


def test_r18s15_submit_denial_never_blank(tmp_path):
    conn = _job136_db(tmp_path)
    job = queue.get_video_render_job(conn, 136)
    project = queue.get_video_project(conn, 134)
    result = json.loads(job["result_json"])
    result.update({"submit_source": "status", "provider_submit_source": "status", "public_user_confirmed": False})
    denied = remote_worker_api._product_video_runtime_eligibility(job, result, project, now=NOW, conn=conn)
    assert denied["provider_submit_allowed"] is False
    assert denied["provider_submit_block_reason"]


def test_r18s15_router_skip_never_blank(tmp_path):
    conn = _job136_db(tmp_path)
    job = queue.get_video_render_job(conn, 136)
    project = queue.get_video_project(conn, 134)
    result = json.loads(job["result_json"])
    result.update({"submit_source": "debug", "provider_submit_source": "debug", "public_user_confirmed": False})
    denied = remote_worker_api._product_video_runtime_eligibility(job, result, project, now=NOW, conn=conn)
    assert denied["router_skip_reason"]


def test_r18s15_debug_reports_claim_attempt_count(tmp_path):
    conn = _job136_db(tmp_path)
    queue.claim_product_video_dispatch_outbox(conn, worker_id="owner", now=NOW)
    queue.retry_product_video_dispatch_outbox(
        conn, outbox_id=9, worker_id="owner", error="dispatch_outbox_job_not_claimable", now=NOW
    )
    diagnostic = queue.product_video_dispatch_outbox_diagnostic(conn, job_id=136, now=NOW)
    assert diagnostic["dispatch_claim_attempt_count"] == 1
    assert diagnostic["dispatch_claim_failure_count"] == 1


def test_r18s15_debug_reports_terminal_transition_source(tmp_path):
    conn = _job136_db(tmp_path)
    conn.execute(
        "UPDATE video_dispatch_outbox SET dispatch_status='leased',lease_owner='owner',attempt_count=3,last_attempt_at=? WHERE outbox_id=9",
        (queue.product_video_outbox_time_text(NOW),),
    )
    conn.commit()
    queue.retry_product_video_dispatch_outbox(
        conn, outbox_id=9, worker_id="owner", error="dispatch_outbox_job_not_claimable", now=NOW
    )
    diagnostic = queue.product_video_dispatch_outbox_diagnostic(conn, job_id=136, now=NOW)
    assert diagnostic["dispatch_terminal_transition_source"] == "dispatch_claim_retry_exhausted"


def test_r18s15_no_charge_before_valid_delivered_mp4(tmp_path):
    conn = _job136_db(tmp_path)
    decision = queue.product_video_delivery_charge_decision(
        queue.get_video_project(conn, 134), queue.get_video_render_job(conn, 136), _payload()
    )
    assert decision["ok"] is False
    assert decision["amount_xu"] == 0


def test_r18s15_progress_debug_contract_includes_dispatch_truth():
    source = Path(product_progress_status.__file__).read_text(encoding="utf-8")
    for field in (
        "dispatch_claim_attempt_count",
        "dispatch_claim_failure_count",
        "dispatch_terminal_transition_source",
        "premature_dispatch_recovery_used",
    ):
        assert field in source


def test_r18s15_no_real_provider_calls_in_tests():
    source = Path(__file__).read_text(encoding="utf-8")
    assert "requests" + "." not in source
    assert "httpx" + "." not in source
    assert "urllib" + ".request" not in source
