from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import remote_worker_api
from services import video_project_queue as queue
from services import video_provider_router as router
from services import video_real_render_connector as connector


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 7, 12, 20, 5, 0, tzinfo=timezone.utc)


class _FixtureAdapter:
    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name

    def capabilities(self) -> dict:
        return {
            "provider": self.provider_name,
            "configured": True,
            "capabilities": ["text_to_video", "scene_video", "multi_scene_video"],
        }


def _status() -> dict:
    providers = []
    for provider in ("shopaikey_video", "key4u_video"):
        providers.append(
            {
                "provider": provider,
                "enabled": True,
                "configured": True,
                "credit_ok": True,
                "submit_url_configured": True,
                "poll_url_configured": True,
                "auth_configured": True,
                "model_present": True,
            }
        )
    return {
        "provider_chain": ["shopaikey_video", "key4u_video"],
        "effective_provider_chain": ["shopaikey_video", "key4u_video"],
        "providers": providers,
    }


def _health() -> dict:
    return {
        "shopaikey_video": {
            "provider": "shopaikey_video",
            "route_ready": True,
            "live_healthy": False,
            "provider_health_state": "degraded",
            "health_status": "degraded",
            "provider_degraded_for_product_video_public": True,
            "degraded_reason": "operational_no_output",
        },
        "key4u_video": {
            "provider": "key4u_video",
            "route_ready": True,
            "live_healthy": False,
            "provider_health_state": "unknown",
            "health_status": "unknown",
        },
    }


@pytest.fixture(autouse=True)
def _provider_contract(monkeypatch):
    monkeypatch.setattr(router, "provider_status_payload", lambda _env=None: _status())
    monkeypatch.setattr(
        router,
        "load_video_provider_adapters",
        lambda _env=None: [_FixtureAdapter("shopaikey_video"), _FixtureAdapter("key4u_video")],
    )
    monkeypatch.setattr(
        router,
        "product_video_submit_switch_detail",
        lambda _env=None: {"resolved": True, "raw": "1", "source": "fixture"},
    )


def _job135_payload(*, include_probation_job_id: bool = False) -> dict:
    payload = {
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "product_type": "video_trend",
        "engine_adapter": "text_to_video",
        "orchestration_mode": "per_scene_8s",
        "scene_count": 2,
        "scenes_total": 2,
        "duration_seconds": 16,
        "admission_enforced": True,
        "admission_snapshot_id": "job-135-admission",
        "provider_eligibility_snapshot_id": "job-135-admission",
        "provider_eligibility_snapshot": {
            "provider_eligibility_snapshot_id": "job-135-admission",
            "configured_provider_keys": ["shopaikey_video", "key4u_video"],
            "contract_valid_provider_chain": ["shopaikey_video", "key4u_video"],
            "scene_count": 2,
        },
        "configured_provider_chain": ["shopaikey_video", "key4u_video"],
        "contract_valid_provider_chain": ["shopaikey_video", "key4u_video"],
        "runtime_candidate_keys": ["shopaikey_video"],
        "preconfirm_candidate_keys": ["shopaikey_video"],
        "admission_candidate_keys": ["shopaikey_video"],
        "provider_health_at_submit": _health(),
        "provider_hard_block_reason_by_provider": {},
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "original_submit_source": "public_user_final_confirm",
        "public_user_confirmed": True,
        "worker_compatible": True,
        "worker_connected": True,
        "public_provider_freeze": False,
        "hidden_submit_freeze": True,
        "probation_lock_clear": False,
        "admission_mode": queue.PRODUCT_VIDEO_PROBATION_ADMISSION_MODE,
        "probation_candidate_key": "shopaikey_video",
        "probation_result": "pending",
        "probation_started_at": queue.now_text(NOW - timedelta(minutes=5)),
        "scene_tasks": queue.product_video_initial_scene_tasks(135, 2),
        "charge_policy": "after_valid_mp4_delivery",
        "charge": 0,
        "charged_xu": 0,
    }
    if include_probation_job_id:
        payload["probation_job_id"] = 135
    return payload


def _job135_db(
    tmp_path: Path,
    *,
    available_at: datetime | None = None,
    outbox_status: str = "retry_wait",
    include_probation_job_id: bool = False,
) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / f"r18s14-{id(tmp_path)}.db")
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
        user_id=1350,
        profile_id="video_trend",
        topic="job #135 fixture",
        ratio="9:16",
        asset_pack=shared,
    )
    original_project_id = int(project["project_id"])
    conn.execute("UPDATE video_projects SET project_id=133 WHERE project_id=?", (original_project_id,))
    queue.update_video_project(
        conn,
        133,
        status="queued_for_worker",
        invoice_json={
            **shared,
            "package_xu": 300,
            "user_visible_price_xu": 300,
            "persisted_quoted_price_xu": 300,
            "customer_charge_planned_xu": 300,
            "wallet_charge_amount_xu": 300,
        },
        scene_count=2,
        total_xu_estimated=300,
        is_confirmed=1,
    )
    job = queue.enqueue_video_render_job(conn, project_id=133, user_id=1350, max_attempts=3)
    original_job_id = int(job["id"])
    conn.execute("UPDATE video_jobs SET id=135 WHERE id=?", (original_job_id,))
    conn.execute("UPDATE video_projects SET job_id=135 WHERE project_id=133")
    payload = _job135_payload(include_probation_job_id=include_probation_job_id)
    conn.execute(
        """UPDATE video_jobs
              SET result_json=?,status='queued',locked_by='',locked_at=NULL,lease_expires_at=NULL,
                  created_at=?,updated_at=?,progress_percent=10,progress_message='queued_waiting_for_dispatch'
            WHERE id=135""",
        (json.dumps(payload), queue.now_text(NOW - timedelta(minutes=5)), queue.now_text(NOW - timedelta(minutes=5))),
    )
    for scene_index in (1, 2):
        conn.execute(
            "INSERT INTO video_scenes(project_id,scene_index,role,scene_status) VALUES (?,?,?,?)",
            (133, scene_index, "product_video_scene", "pending"),
        )
    queue.ensure_product_video_dispatch_outbox(
        conn,
        job_id=135,
        project_id=133,
        scene_indexes=[1, 2],
        now=NOW - timedelta(minutes=1),
    )
    conn.execute("UPDATE video_dispatch_outbox SET outbox_id=8 WHERE job_id=135")
    due_at = available_at or (NOW - timedelta(seconds=1))
    conn.execute(
        """UPDATE video_dispatch_outbox
              SET dispatch_status=?,available_at=?,attempt_count=0,last_error='dispatch_outbox_job_not_claimable',
                  lease_owner='',lease_expires_at=NULL
            WHERE outbox_id=8""",
        (outbox_status, queue.product_video_outbox_time_text(due_at)),
    )
    conn.commit()
    return conn


def _runtime(conn: sqlite3.Connection, *, job_id: int = 135) -> dict:
    job = queue.get_video_render_job(conn, job_id)
    project = queue.get_video_project(conn, int(job["project_id"]))
    result = json.loads(str(job.get("result_json") or "{}"))
    return remote_worker_api._product_video_runtime_eligibility(
        job,
        result,
        project,
        now=NOW,
        conn=conn,
    )


def _render_two_scenes(monkeypatch, job: dict) -> tuple[list[dict], list[dict]]:
    calls: list[dict] = []

    def fake_run_provider_generation(request, *, output_dir, environ):
        del environ
        calls.append(
            {
                "job_id": request.job_id,
                "duration_seconds": request.duration_seconds,
                "metadata": dict(request.metadata),
            }
        )
        path = Path(output_dir) / f"{request.job_id}.mp4"
        path.write_bytes(b"fixture-mp4")
        return {
            "ok": True,
            "provider": "shopaikey_video",
            "output_path": str(path),
            "provider_task_ids": [f"task-{request.job_id}"],
            "provider_task_id_saved": True,
            "result_url_present": True,
            "output_duration": 8,
            "provider_router_called": True,
        }

    monkeypatch.setattr(connector, "run_provider_generation", fake_run_provider_generation)
    monkeypatch.setattr(connector, "ensure_video_output", lambda path: str(path))
    scene_job = {
        **job,
        "job_id": str(job.get("id") or job.get("job_id") or 135),
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "product_type": "video_trend",
        "engine_adapter": "text_to_video",
        "scene_count": 2,
        "orchestration_mode": "per_scene_8s",
        "runtime_candidate_keys": ["shopaikey_video"],
        "provider_chain": ["shopaikey_video"],
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
    }
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
        results = [
            asyncio.run(
                connector._render_scene_async(
                    scene,
                    str(Path(tmp_dir) / f"raw_scene_{scene.scene_id}.mp4"),
                    [],
                )
            )
            for scene in scenes
        ]
    return calls, results


def test_r18s14_same_job_probation_lock_allows_reentry(tmp_path):
    conn = _job135_db(tmp_path)
    state = queue.product_video_probation_lock_state(conn, current_job_id=135, current_project_id=133)
    assert state["probation_lock_clear"] is False
    assert state["probation_lock_clear_for_current_job"] is True
    assert state["current_job_matches_lock"] is True


def test_r18s14_same_job_lock_does_not_duplicate_lock(tmp_path):
    conn = _job135_db(tmp_path)
    first = queue.product_video_probation_lock_state(conn, current_job_id=135)
    second = queue.product_video_probation_lock_state(conn, current_job_id=135)
    count = conn.execute("SELECT COUNT(*) FROM video_jobs WHERE result_json LIKE '%public_confirmed_probation%'").fetchone()[0]
    assert first["active_probation_job_id"] == second["active_probation_job_id"] == 135
    assert count == 1


def test_r18s14_other_job_probation_lock_blocks(tmp_path):
    conn = _job135_db(tmp_path)
    state = queue.product_video_probation_lock_state(conn, current_job_id=136)
    assert state["probation_lock_clear_for_current_job"] is False
    assert state["probation_lock_reject_reason"] == "probation_lock_owned_by_other_job"


def test_r18s14_expired_probation_lock_is_reclaimable(tmp_path):
    conn = _job135_db(tmp_path)
    payload = json.loads(conn.execute("SELECT result_json FROM video_jobs WHERE id=135").fetchone()[0])
    payload["probation_lock_expires_at"] = queue.now_text(NOW - timedelta(seconds=1))
    conn.execute("UPDATE video_jobs SET result_json=? WHERE id=135", (json.dumps(payload),))
    conn.commit()
    state = queue.product_video_probation_lock_state(conn, current_job_id=136, now=NOW)
    assert state["probation_active"] is False
    assert state["probation_lock_clear_for_current_job"] is True


def test_r18s14_same_job_provider_selection_preserved(tmp_path):
    conn = _job135_db(tmp_path)
    result = _runtime(conn)
    assert result["runtime_candidate_keys"] == ["shopaikey_video"]
    assert result["probation_candidate_selected"] == "shopaikey_video"


def test_r18s14_same_job_lock_never_returns_probation_lock_not_clear(tmp_path):
    conn = _job135_db(tmp_path)
    result = _runtime(conn)
    assert result["probation_reject_reason"] != "probation_lock_not_clear"
    assert result["router_skip_reason"] == ""


def test_r18s14_retry_wait_not_claimable_before_available_at(tmp_path):
    conn = _job135_db(tmp_path, available_at=NOW + timedelta(seconds=30))
    assert queue.claim_product_video_dispatch_outbox(conn, worker_id="owner", now=NOW) == {}


def test_r18s14_retry_wait_claimable_at_available_at(tmp_path):
    conn = _job135_db(tmp_path, available_at=NOW)
    claimed = queue.claim_product_video_dispatch_outbox(conn, worker_id="owner", now=NOW)
    assert claimed["outbox_id"] == 8


def test_r18s14_retry_wait_claimable_after_available_at(tmp_path):
    conn = _job135_db(tmp_path, available_at=NOW - timedelta(seconds=30))
    claimed = queue.claim_product_video_dispatch_outbox(conn, worker_id="owner", now=NOW)
    assert claimed["dispatch_status"] == "leased"


def test_r18s14_retry_wait_uses_utc_consistently(tmp_path):
    conn = _job135_db(tmp_path, available_at=NOW)
    same_in_plus_two = datetime(2026, 7, 12, 22, 5, 0, tzinfo=timezone(timedelta(hours=2)))
    diagnostic = queue.product_video_dispatch_outbox_diagnostic(conn, job_id=135, now=same_in_plus_two)
    assert diagnostic["dispatch_outbox_available_at_timezone"] == "UTC"
    assert diagnostic["dispatch_outbox_due"] is True


def test_r18s14_due_outbox_claimed_by_owner_product_video(tmp_path):
    conn = _job135_db(tmp_path)
    claimed = remote_worker_api.claim_remote_worker_product_video_job(
        conn, worker_id="owner-product-video", owner_only=True, now=NOW
    )
    assert claimed["id"] == 135


def test_r18s14_watchdog_does_not_duplicate_worker_claim(tmp_path):
    conn = _job135_db(tmp_path)
    queue.sweep_product_video_zero_task_watchdog(
        conn,
        now=NOW,
        job_id=135,
        eligibility_evaluator=lambda job, result, project: remote_worker_api._product_video_runtime_eligibility(
            job, result, project, now=NOW, conn=conn
        ),
    )
    first = remote_worker_api.claim_remote_worker_product_video_job(
        conn, worker_id="owner-one", owner_only=True, now=NOW
    )
    second = remote_worker_api.claim_remote_worker_product_video_job(
        conn, worker_id="owner-two", owner_only=True, now=NOW
    )
    assert first["id"] == 135
    assert second == {}


def test_r18s14_available_at_not_extended_without_new_failure(tmp_path):
    conn = _job135_db(tmp_path)
    first = queue.claim_product_video_dispatch_outbox(conn, worker_id="owner", now=NOW)
    original = first["available_at"]
    assert queue.retry_product_video_dispatch_outbox(
        conn,
        outbox_id=8,
        worker_id="owner",
        error="dispatch_outbox_job_not_claimable",
        now=NOW,
    )
    latest = queue.get_product_video_dispatch_outbox(conn, job_id=135)
    assert latest["available_at"] == original


def test_r18s14_same_job_lock_does_not_requeue_outbox(tmp_path):
    conn = _job135_db(tmp_path)
    claimed = remote_worker_api.claim_remote_worker_product_video_job(
        conn, worker_id="owner", owner_only=True, now=NOW
    )
    outbox = queue.get_product_video_dispatch_outbox(conn, job_id=135)
    assert claimed["id"] == 135
    assert outbox["dispatch_status"] == "acknowledged"


def test_r18s14_probation_candidate_survives_to_worker(tmp_path):
    conn = _job135_db(tmp_path)
    result = _runtime(conn)
    assert result["candidate_before_retry"] == ["shopaikey_video"]
    assert result["candidate_after_worker_revalidation"] == ["shopaikey_video"]


def test_r18s14_probation_candidate_survives_retry_wait(tmp_path):
    conn = _job135_db(tmp_path)
    claimed = remote_worker_api.claim_remote_worker_product_video_job(
        conn, worker_id="owner", owner_only=True, now=NOW
    )
    result = json.loads(claimed["result_json"])
    assert result["runtime_candidate_keys"] == ["shopaikey_video"]


def test_r18s14_provider_router_runs_after_due_outbox_claim(tmp_path, monkeypatch):
    conn = _job135_db(tmp_path)
    claimed = remote_worker_api.claim_remote_worker_product_video_job(
        conn, worker_id="owner", owner_only=True, now=NOW
    )
    calls, results = _render_two_scenes(monkeypatch, claimed)
    assert len(calls) == 2
    assert all(item["provider_router_called"] is True for item in results)


def test_r18s14_selected_provider_recorded_before_submit(tmp_path, monkeypatch):
    conn = _job135_db(tmp_path)
    claimed = remote_worker_api.claim_remote_worker_product_video_job(
        conn, worker_id="owner", owner_only=True, now=NOW
    )
    calls, _results = _render_two_scenes(monkeypatch, claimed)
    assert all(call["metadata"]["runtime_candidate_keys"] == ["shopaikey_video"] for call in calls)
    assert all(call["metadata"]["selected_provider"] == "shopaikey_video" for call in calls)


def test_r18s14_submit_called_once_per_scene(tmp_path, monkeypatch):
    conn = _job135_db(tmp_path)
    claimed = remote_worker_api.claim_remote_worker_product_video_job(
        conn, worker_id="owner", owner_only=True, now=NOW
    )
    calls, _results = _render_two_scenes(monkeypatch, claimed)
    assert [item["job_id"] for item in calls] == ["135-1", "135-2"]


def test_r18s14_duplicate_worker_claim_does_not_duplicate_submit(tmp_path, monkeypatch):
    conn = _job135_db(tmp_path)
    claimed = remote_worker_api.claim_remote_worker_product_video_job(
        conn, worker_id="owner-one", owner_only=True, now=NOW
    )
    duplicate = remote_worker_api.claim_remote_worker_product_video_job(
        conn, worker_id="owner-two", owner_only=True, now=NOW
    )
    calls, _results = _render_two_scenes(monkeypatch, claimed)
    assert duplicate == {}
    assert len(calls) == 2


def test_r18s14_job135_same_lock_reentry_regression(tmp_path):
    conn = _job135_db(tmp_path)
    result = _runtime(conn)
    assert result["current_job_matches_lock"] is True
    assert result["same_job_lock_reentry_allowed"] is True


def test_r18s14_job135_due_outbox_claimed(tmp_path):
    conn = _job135_db(tmp_path)
    claimed = remote_worker_api.claim_remote_worker_product_video_job(
        conn, worker_id="owner", owner_only=True, now=NOW
    )
    assert claimed["id"] == 135


def test_r18s14_job135_router_called(tmp_path, monkeypatch):
    conn = _job135_db(tmp_path)
    claimed = remote_worker_api.claim_remote_worker_product_video_job(
        conn, worker_id="owner", owner_only=True, now=NOW
    )
    _calls, results = _render_two_scenes(monkeypatch, claimed)
    assert all(item.get("provider_router_called") for item in results)


def test_r18s14_job135_scene_submit_started(tmp_path, monkeypatch):
    conn = _job135_db(tmp_path)
    claimed = remote_worker_api.claim_remote_worker_product_video_job(
        conn, worker_id="owner", owner_only=True, now=NOW
    )
    calls, results = _render_two_scenes(monkeypatch, claimed)
    assert len(calls) == len(results) == 2
    assert all(item.get("provider_task_id_saved") for item in results)


def test_r18s14_job135_no_duplicate_submit(tmp_path, monkeypatch):
    conn = _job135_db(tmp_path)
    claimed = remote_worker_api.claim_remote_worker_product_video_job(
        conn, worker_id="owner", owner_only=True, now=NOW
    )
    calls, _results = _render_two_scenes(monkeypatch, claimed)
    assert len({item["job_id"] for item in calls}) == 2


def test_r18s14_job135_charge_zero_before_delivery(tmp_path):
    conn = _job135_db(tmp_path)
    decision = queue.product_video_delivery_charge_decision(
        queue.get_video_project(conn, 133),
        queue.get_video_render_job(conn, 135),
        _job135_payload(),
    )
    assert decision["ok"] is False
    assert decision["amount_xu"] == 0


def test_r18s14_future_retry_shows_retry_countdown(tmp_path):
    conn = _job135_db(tmp_path, available_at=NOW + timedelta(seconds=25))
    diagnostic = queue.product_video_dispatch_outbox_diagnostic(conn, job_id=135, now=NOW)
    assert diagnostic["dispatch_outbox_due"] is False
    assert diagnostic["dispatch_outbox_retry_seconds_remaining"] == 25
    assert diagnostic["dispatch_outbox_retry_reason"] == "dispatch_outbox_job_not_claimable"


def test_r18s14_due_retry_does_not_show_indefinite_wait(tmp_path):
    conn = _job135_db(tmp_path)
    diagnostic = queue.product_video_dispatch_outbox_diagnostic(conn, job_id=135, now=NOW)
    assert diagnostic["dispatch_outbox_due"] is True
    assert diagnostic["dispatch_outbox_claimable"] is True
    assert diagnostic["dispatch_outbox_retry_seconds_remaining"] == 0


def test_r18s14_exhausted_dispatch_retry_fails_no_charge(tmp_path):
    conn = _job135_db(tmp_path)
    conn.execute(
        "UPDATE video_dispatch_outbox SET dispatch_status='leased',lease_owner='owner',attempt_count=3 WHERE outbox_id=8"
    )
    conn.commit()
    assert queue.retry_product_video_dispatch_outbox(
        conn,
        outbox_id=8,
        worker_id="owner",
        error="dispatch_outbox_job_not_claimable",
        now=NOW,
    )
    job = queue.get_video_render_job(conn, 135)
    result = json.loads(job["result_json"])
    assert job["status"] == "failed"
    assert result["terminal_state"] == "failed_no_charge"
    assert result["charge"] == 0


def test_r18s14_no_fake_provider_progress(tmp_path):
    conn = _job135_db(tmp_path, available_at=NOW + timedelta(seconds=15))
    job = queue.get_video_render_job(conn, 135)
    result = json.loads(job["result_json"])
    assert result.get("provider_submit_called") is not True
    assert result.get("provider_task_id") in (None, "")
    assert int(job["progress_percent"] or 0) <= 20


def test_r18s14_no_charge_on_dispatch_failure(tmp_path):
    conn = _job135_db(tmp_path)
    conn.execute(
        "UPDATE video_dispatch_outbox SET dispatch_status='leased',lease_owner='owner',attempt_count=3 WHERE outbox_id=8"
    )
    conn.commit()
    queue.retry_product_video_dispatch_outbox(
        conn,
        outbox_id=8,
        worker_id="owner",
        error="dispatch_outbox_job_not_claimable",
        now=NOW,
    )
    result = json.loads(queue.get_video_render_job(conn, 135)["result_json"])
    assert result["charged_xu"] == 0


def test_r18s14_debug_reports_same_job_lock_truth(tmp_path):
    conn = _job135_db(tmp_path)
    result = _runtime(conn)
    assert result["probation_lock_owner_job"] == 135
    assert result["current_job_matches_lock"] is True
    assert result["same_job_lock_reentry_allowed"] is True


def test_r18s14_debug_reports_outbox_due_truth(tmp_path):
    conn = _job135_db(tmp_path)
    result = queue.product_video_dispatch_outbox_diagnostic(conn, job_id=135, now=NOW)
    for key in (
        "dispatch_outbox_retry_count",
        "dispatch_outbox_retry_reason",
        "dispatch_outbox_available_at",
        "dispatch_outbox_due",
        "dispatch_outbox_claimable",
    ):
        assert key in result


def test_r18s14_debug_reports_candidate_loss_stage(tmp_path):
    conn = _job135_db(tmp_path)
    result = _runtime(conn)
    assert result["candidate_before_retry"] == ["shopaikey_video"]
    assert result["candidate_after_retry"][:1] == ["shopaikey_video"]
    assert result["candidate_after_worker_revalidation"] == ["shopaikey_video"]


def test_r18s14_debug_never_has_blank_router_skip_reason(tmp_path):
    conn = _job135_db(tmp_path)
    job = queue.get_video_render_job(conn, 135)
    project = queue.get_video_project(conn, 133)
    result = json.loads(job["result_json"])
    result["submit_source"] = "status"
    result["provider_submit_source"] = "status"
    result["public_user_confirmed"] = False
    blocked = remote_worker_api._product_video_runtime_eligibility(
        job, result, project, now=NOW, conn=conn
    )
    assert blocked["provider_submit_allowed"] is False
    assert blocked["router_skip_reason"]


def test_r18s14_no_real_provider_calls_in_tests():
    source = Path(__file__).read_text(encoding="utf-8")
    for marker in (
        "requests" + ".post",
        "requests" + ".get",
        "url" + "open",
        "submit_video" + "_job(",
        "video_provider" + "_smoke",
    ):
        assert marker not in source
