import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from services import product_progress_status
from services import remote_worker_api
from services import video_project_queue as queue


ROOT = Path(__file__).resolve().parents[1]


def _conn(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "r18s6.db")
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _project(conn: sqlite3.Connection, *, user_id: int = 131, scene_count: int = 2) -> dict:
    shared = {
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "original_submit_source": "public_user_final_confirm",
        "product_type": "video_ai_prompt",
        "engine_adapter": "text_to_video",
        "orchestration_mode": "per_scene_8s",
        "provider_orchestration_mode": "per_scene_8s",
        "scene_count": scene_count,
    }
    invoice = {
        **shared,
        "tier": "basic",
        "package_xu": 300,
        "scene_duration_seconds": 8,
        "duration_seconds": scene_count * 8,
        "total_xu": 300,
        "user_visible_price_xu": 300,
        "persisted_quoted_price_xu": 300,
        "customer_charge_planned_xu": 300,
        "wallet_charge_amount_xu": 300,
    }
    project = queue.create_video_project(
        conn,
        user_id=user_id,
        profile_id="video_ai_prompt",
        topic="fixture #131",
        ratio="9:16",
        asset_pack=shared,
    )
    queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="processing",
        invoice_json=invoice,
        scene_count=scene_count,
        prompt_text="fixture #131 two-scene product video",
        quality_tier=300,
        total_xu_estimated=300,
        is_confirmed=1,
    )
    return queue.get_video_project(conn, int(project["project_id"]))


def _legacy_zero_task_job(
    conn: sqlite3.Connection,
    *,
    candidates=None,
    age_seconds: int = 0,
    status: str = "processing",
) -> tuple[dict, dict]:
    project = _project(conn)
    job = queue.enqueue_video_render_job(
        conn,
        project_id=int(project["project_id"]),
        user_id=int(project["user_id"]),
    )
    candidate_keys = list(["shopaikey_video"] if candidates is None else candidates)
    moment = datetime.now() - timedelta(seconds=max(0, age_seconds))
    payload = {
        "source": "product_video",
        "product_video": True,
        "product_type": "video_ai_prompt",
        "engine_adapter": "text_to_video",
        "orchestration_mode": "per_scene_8s",
        "provider_orchestration_mode": "per_scene_8s",
        "route_requires_provider": False,
        "scene_count": 2,
        "scenes_total": 2,
        "scene_tasks_total": 2,
        "scene_tasks": queue.product_video_initial_scene_tasks(job["id"], 2),
        "runtime_candidate_keys": candidate_keys,
        "preconfirm_candidate_keys": candidate_keys,
        "runtime_candidates_evaluated": True,
        "admission_enforced": True,
        "admission_rechecked_before_dispatch": True,
        "final_eligible_provider_count": len(candidate_keys),
        "provider_router_called": False,
        "provider_submit_called": False,
        "provider_http_request_sent": False,
        "provider_http_status": 0,
        "fallback_count_effective": 0,
        "concat_attempted": False,
        "delivery_attempted": False,
        "charged_xu": 0,
        "charge": 0,
        "public_confirmed_at": queue.now_text(moment),
        "status_registry_present": False,
    }
    conn.execute(
        "UPDATE video_jobs SET status=?,locked_by='',locked_at=NULL,lease_expires_at=NULL,created_at=?,updated_at=?,result_json=? WHERE id=?",
        (status, queue.now_text(moment), queue.now_text(moment), json.dumps(payload), int(job["id"])),
    )
    conn.commit()
    return queue.get_video_render_job(conn, int(job["id"])), project


def _eligibility(candidates) -> dict:
    keys = list(candidates)
    return {
        "ok": bool(keys),
        "eligible_provider_keys": keys,
        "runtime_candidate_keys": keys,
        "final_eligible_provider_count": len(keys),
        "provider_eligibility_snapshot": {
            "eligible_provider_keys": keys,
            "runtime_candidate_keys": keys,
            "final_eligible_provider_count": len(keys),
        },
    }


def _payload(job: dict) -> dict:
    return json.loads(str(job.get("result_json") or "{}"))


def test_fixture_131_reproduces_idle_when_durable_outbox_is_missing(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    job, _project_row = _legacy_zero_task_job(conn, age_seconds=0)
    monkeypatch.setattr(remote_worker_api, "_product_video_runtime_eligibility", lambda *_args, **_kwargs: _eligibility(["shopaikey_video"]))

    result = remote_worker_api.claim_remote_worker_job(
        conn,
        worker_id="owner-r18s6",
        capabilities=["owner_product_video"],
        owner_product_video_only=True,
    )

    assert result["job"] is None
    assert result["reason"] == "no_owner_product_video_job"
    diagnostic = result["debug"]["latest_product_diagnostic"]
    assert diagnostic["job_id"] == job["id"]
    assert diagnostic["reason"] == "dispatch_outbox_missing"
    assert diagnostic["outbox_exists"] is False
    assert diagnostic["exact_claim_block_reason"] == "dispatch_outbox_missing"


@pytest.mark.parametrize("initial_status", ["queued", "processing"])
def test_actual_scheduler_tick_recovers_historical_two_scene_job_once(tmp_path, monkeypatch, initial_status):
    conn = _conn(tmp_path)
    job, _project_row = _legacy_zero_task_job(conn, age_seconds=90, status=initial_status)
    evaluator = lambda *_args: _eligibility(["shopaikey_video"])

    tick = queue.run_product_video_watchdog_scheduler_tick(conn, eligibility_evaluator=evaluator)
    outbox = queue.get_product_video_dispatch_outbox(conn, job_id=int(job["id"]))

    assert tick["scheduler_registered"] is True
    assert tick["scheduler_running"] is True
    assert tick["jobs_scanned"] == 1
    assert tick["jobs_reconciled"] == 1
    assert tick["last_run_at"]
    assert tick["last_success_at"]
    assert tick["next_run_at"]
    assert outbox["dispatch_status"] == "pending"
    assert outbox["scene_indexes"] == [1, 2]

    monkeypatch.setattr(remote_worker_api, "_product_video_runtime_eligibility", lambda *_args, **_kwargs: evaluator())
    claimed = remote_worker_api.claim_remote_worker_product_video_job(
        conn,
        worker_id="owner-r18s6",
        owner_only=True,
    )
    duplicate = remote_worker_api.claim_remote_worker_product_video_job(
        conn,
        worker_id="owner-r18s6-duplicate",
        owner_only=True,
    )

    assert claimed["id"] == job["id"]
    claimed_payload = _payload(claimed)
    assert sorted(claimed_payload["scene_dispatch_lease_by_index"]) == ["1", "2"]
    assert all(
        item["lease_owner"] == "owner-r18s6"
        for item in claimed_payload["scene_dispatch_lease_by_index"].values()
    )
    assert duplicate == {}
    assert conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox WHERE job_id=?", (int(job["id"]),)).fetchone()[0] == 1


def test_existing_pending_outbox_and_processing_zero_task_job_are_claimable(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    job, project = _legacy_zero_task_job(conn, age_seconds=90)
    queue.ensure_product_video_dispatch_outbox(
        conn,
        job_id=int(job["id"]),
        project_id=int(project["project_id"]),
        scene_indexes=[1, 2],
    )
    diagnostic = queue.product_video_dispatch_outbox_diagnostic(conn, job_id=int(job["id"]))
    assert diagnostic["claimable"] is True
    assert diagnostic["outbox_status"] == "pending"
    monkeypatch.setattr(remote_worker_api, "_product_video_runtime_eligibility", lambda *_args, **_kwargs: _eligibility(["shopaikey_video"]))

    claimed = remote_worker_api.claim_remote_worker_product_video_job(
        conn,
        worker_id="owner-existing-outbox",
        owner_only=True,
    )

    assert claimed["id"] == job["id"]


def test_scheduler_terminalizes_job_131_without_provider_and_without_charge(tmp_path):
    conn = _conn(tmp_path)
    job, _project_row = _legacy_zero_task_job(conn, candidates=[], age_seconds=90)

    tick = queue.run_product_video_watchdog_scheduler_tick(
        conn,
        eligibility_evaluator=lambda *_args: _eligibility([]),
    )
    failed = queue.get_video_render_job(conn, int(job["id"]))
    payload = _payload(failed)
    outbox = queue.get_product_video_dispatch_outbox(conn, job_id=int(job["id"]))

    assert tick["terminal_failed"] == 1
    assert failed["status"] == "failed"
    assert payload["terminal_state"] == "failed_no_charge"
    assert payload["route_requires_provider"] is True
    assert payload["route_requirement_override"] == "legacy_persisted_false_ignored"
    assert payload["continue_polling"] is False
    assert payload["zero_task_terminal_reason"] == "no_eligible_provider_before_scene_dispatch"
    assert payload["provider_http_request_sent"] is False
    assert payload["provider_http_status"] == 0
    assert payload["fallback_count_effective"] == 0
    assert payload["concat_attempted"] is False
    assert payload["delivery_attempted"] is False
    assert payload["charged_xu"] == 0
    assert outbox["dispatch_status"] == "terminal_failed"
    assert outbox["terminal_reason"] == "no_eligible_provider_before_scene_dispatch"


def test_active_job_lease_blocks_claim_and_is_reported(tmp_path):
    conn = _conn(tmp_path)
    job, project = _legacy_zero_task_job(conn, age_seconds=90)
    queue.ensure_product_video_dispatch_outbox(
        conn,
        job_id=int(job["id"]),
        project_id=int(project["project_id"]),
        scene_indexes=[1, 2],
    )
    future = queue.now_text(datetime.now() + timedelta(minutes=5))
    conn.execute(
        "UPDATE video_jobs SET locked_by='owner-active',lease_expires_at=? WHERE id=?",
        (future, int(job["id"])),
    )
    conn.commit()

    diagnostic = queue.product_video_dispatch_outbox_diagnostic(conn, job_id=int(job["id"]))
    claimed = queue.claim_product_video_dispatch_outbox(conn, worker_id="owner-other")

    assert diagnostic["claimable"] is False
    assert diagnostic["exact_claim_block_reason"] == "video_job_lease_active"
    assert claimed == {}


def test_canonical_route_contract_ignores_legacy_persisted_false(tmp_path):
    conn = _conn(tmp_path)
    _job, project = _legacy_zero_task_job(conn)

    contract = queue.canonical_product_video_route_contract(
        project,
        {
            "product_type": "video_ai_prompt",
            "engine_adapter": "text_to_video",
            "orchestration_mode": "per_scene_8s",
            "route_requires_provider": False,
        },
    )
    debug = product_progress_status.product_progress_debug_payload(
        "multiscene_video",
        "131",
        {
            "source": "product_video",
            "product_type": "video_ai_prompt",
            "engine_adapter": "text_to_video",
            "orchestration_mode": "per_scene_8s",
            "route_requires_provider": False,
            "status": "processing",
        },
    )

    assert contract["route_requires_provider"] is True
    assert contract["route_requirement_override"] == "legacy_persisted_false_ignored"
    assert debug["route_requires_provider"] is True
    assert debug["route_requirement_override"] == "legacy_persisted_false_ignored"


def test_latest_owner_heartbeat_wins_and_stale_sha_is_not_reused():
    now = datetime(2030, 1, 2, 3, 4, 5)
    identity = remote_worker_api.authoritative_product_video_worker_identity(
        [
            {
                "worker_id": "owner-product-video",
                "worker_git_head_sha": "73b7d9b56aa0",
                "heartbeat_updated_at": queue.now_text(now - timedelta(minutes=10)),
                "worker_service_mode": "owner_product_video",
            },
            {
                "worker_id": "owner-product-video",
                "worker_git_head_sha": "4080cf000401b2da6d5c3f4cf6e81f7a7d682077",
                "worker_sha_source": "git_rev_parse_head",
                "worker_cwd": "/opt/toanaas-worker",
                "heartbeat_updated_at": queue.now_text(now - timedelta(seconds=5)),
                "worker_service_mode": "owner_product_video",
            },
        ],
        runtime_sha="4080cf000401b2da6d5c3f4cf6e81f7a7d682077",
        now=now,
    )
    stale_only = remote_worker_api.authoritative_product_video_worker_identity(
        [
            {
                "worker_id": "owner-product-video",
                "worker_git_head_sha": "73b7d9b56aa0",
                "heartbeat_updated_at": queue.now_text(now - timedelta(minutes=10)),
            }
        ],
        runtime_sha="4080cf000401b2da6d5c3f4cf6e81f7a7d682077",
        now=now,
    )

    assert identity["worker_sha"].startswith("4080cf")
    assert identity["worker_sha_matches_runtime"] is True
    assert identity["heartbeat_record_selected_by"] == "latest_owner_product_video_updated_at"
    assert identity["heartbeat_records_considered"] == 2
    assert stale_only["worker_sha"] == ""
    assert stale_only["worker_sha_source"] == "unknown"
    assert stale_only["stale_worker_sha_ignored"] is True


def test_bot_registers_real_scheduler_and_uses_same_owner_identity_for_public_status():
    source = (ROOT / "bot.py").read_text(encoding="utf-8")
    assert "async def product_video_watchdog_scheduler_loop" in source
    assert "run_product_video_watchdog_scheduler_tick" in source
    assert "tg_product_video_watchdog_task = asyncio.create_task(product_video_watchdog_scheduler_loop())" in source
    assert 'remote_worker = {\n        **product_video_worker,' in source
    assert '"product_video_watchdog_scheduler": product_video_watchdog' in source


def test_claim_debug_exposes_exact_query_and_scheduler_contract(tmp_path):
    conn = _conn(tmp_path)
    _legacy_zero_task_job(conn)
    snapshot = remote_worker_api.remote_worker_claim_debug_snapshot(
        conn,
        claim_route="owner_product_video",
    )

    assert snapshot["claim_query_source"] == "video_dispatch_outbox_join_video_jobs_video_projects"
    assert snapshot["claim_allowed_job_statuses"] == ["queued", "processing"]
    assert snapshot["claim_allowed_outbox_states"] == ["pending", "retry_wait", "expired_lease"]
    assert snapshot["claim_owner_filter"] == "owner_product_video"
    assert snapshot["claim_job_age_filter"] == "none"
    assert "scheduler_registered" in snapshot["product_video_watchdog_scheduler"]


def test_r18s6_has_no_provider_http_or_charge_path():
    test_source = Path(__file__).read_text(encoding="utf-8")
    queue_source = (ROOT / "services" / "video_project_queue.py").read_text(encoding="utf-8")
    worker_source = (ROOT / "services" / "remote_worker_api.py").read_text(encoding="utf-8")
    for marker in (
        "product_video_dispatch_outbox_diagnostic",
        "run_product_video_watchdog_scheduler_tick",
        "legacy_persisted_false_ignored",
    ):
        assert marker in queue_source
    assert "dispatch_outbox_missing" in worker_source
    forbidden = (
        "urllib.request." + "urlopen",
        "run_provider" + "_generation(",
        "provider" + "_smoke",
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
    )
    assert all(token not in test_source for token in forbidden)
