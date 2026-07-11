import asyncio
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
    capability = queue.PRODUCT_VIDEO_CANONICAL_WORKER_CAPABILITY
    identity = remote_worker_api.authoritative_product_video_worker_identity(
        [
            {
                "worker_id": "owner-product-video",
                "worker_instance_id": "owner-product-video:old",
                "generation_id": "generation-old",
                "worker_git_head_sha": "73b7d9b56aa0",
                "runtime_target_sha": "73b7d9b56aa0",
                "heartbeat_updated_at": queue.now_text(now - timedelta(minutes=10)),
                "lease_expires_at": queue.now_text(now - timedelta(minutes=8)),
                "worker_service_mode": "owner_product_video",
                "worker_capability_version": capability,
                "worker_capabilities": ["owner_product_video", capability],
            },
            {
                "worker_id": "owner-product-video",
                "worker_instance_id": "owner-product-video:new",
                "generation_id": "generation-new",
                "worker_git_head_sha": "4080cf000401b2da6d5c3f4cf6e81f7a7d682077",
                "runtime_target_sha": "4080cf000401b2da6d5c3f4cf6e81f7a7d682077",
                "worker_sha_source": "git_rev_parse_head",
                "worker_cwd": "/opt/toanaas-worker",
                "heartbeat_updated_at": queue.now_text(now - timedelta(seconds=5)),
                "lease_expires_at": queue.now_text(now + timedelta(seconds=85)),
                "worker_service_mode": "owner_product_video",
                "worker_capability_version": capability,
                "worker_capabilities": ["owner_product_video", capability],
            },
        ],
        runtime_sha="4080cf000401b2da6d5c3f4cf6e81f7a7d682077",
        now=now,
    )
    stale_only = remote_worker_api.authoritative_product_video_worker_identity(
        [
            {
                "worker_id": "owner-product-video",
                "worker_instance_id": "owner-product-video:old",
                "generation_id": "generation-old",
                "worker_git_head_sha": "73b7d9b56aa0",
                "runtime_target_sha": "73b7d9b56aa0",
                "heartbeat_updated_at": queue.now_text(now - timedelta(minutes=10)),
                "lease_expires_at": queue.now_text(now - timedelta(minutes=8)),
                "worker_service_mode": "owner_product_video",
                "worker_capability_version": capability,
                "worker_capabilities": ["owner_product_video", capability],
            }
        ],
        runtime_sha="4080cf000401b2da6d5c3f4cf6e81f7a7d682077",
        now=now,
    )

    assert identity["worker_sha"].startswith("4080cf")
    assert identity["worker_sha_matches_runtime"] is True
    assert identity["heartbeat_record_selected_by"] == "latest_active_owner_product_video_generation"
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


def _worker_generation(
    now: datetime,
    generation_id: str,
    *,
    sha: str = "45e5ea499465588563a746a5cc2f962762a9244a",
    heartbeat_age_seconds: int = 5,
    lease_seconds: int = 85,
    service_mode: str = "owner_product_video",
    capability_version: str | None = None,
) -> dict:
    capability = capability_version or queue.PRODUCT_VIDEO_CANONICAL_WORKER_CAPABILITY
    return {
        "worker_id": "owner-product-video",
        "worker_instance_id": f"owner-product-video:{generation_id}",
        "generation_id": generation_id,
        "service_mode": service_mode,
        "git_sha": sha,
        "runtime_target_sha": sha,
        "capability_version": capability,
        "capabilities": ["owner_product_video", capability],
        "process_started_at": queue.now_text(now - timedelta(minutes=2)),
        "heartbeat_at": queue.now_text(now - timedelta(seconds=heartbeat_age_seconds)),
        "lease_expires_at": queue.now_text(now + timedelta(seconds=lease_seconds)),
        "hostname": "vpssieutoc",
        "pid": 13100,
    }


def test_scheduler_loop_runs_two_ticks_and_survives_first_tick_exception():
    queue.mark_product_video_watchdog_scheduler(registered=True, running=False)
    calls: list[int] = []
    sleeps: list[float] = []
    moments = iter(
        datetime(2030, 1, 1, 0, 0, second)
        for second in range(10)
    )

    async def tick():
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            raise RuntimeError("first_tick_fixture")
        return {"scanned": 2, "recovered": 1, "terminal_failed": 0}

    async def fake_sleep(seconds: float):
        sleeps.append(seconds)

    result = asyncio.run(
        queue.run_product_video_watchdog_scheduler_loop(
            tick,
            sleep=fake_sleep,
            configured_interval_seconds=20,
            generation_id="watchdog-two-ticks",
            max_ticks=2,
            now_provider=lambda: next(moments),
        )
    )

    assert calls == [1, 2]
    assert sleeps == [20.0]
    assert result["ticks_executed"] == 2
    assert result["watchdog_tick_count"] >= 2
    assert result["watchdog_tick_error_count"] >= 1
    assert result["watchdog_enabled"] is True
    assert result["watchdog_scheduler_registered"] is True
    assert result["scheduler_running_at_return"] is True
    assert result["watchdog_started_at"]
    assert result["watchdog_last_run_at"]
    assert result["watchdog_last_success_at"]
    assert result["watchdog_jobs_scanned"] == 2
    assert result["watchdog_jobs_reconciled"] == 1
    assert result["watchdog_next_run_at"]
    assert result["watchdog_interval_seconds"] == 20
    assert result["watchdog_generation_id"] == "watchdog-two-ticks"


def test_scheduler_registers_once_and_rejects_duplicate_generation():
    queue.mark_product_video_watchdog_scheduler(registered=True, running=False)
    first = queue.mark_product_video_watchdog_scheduler(
        registered=True,
        running=True,
        configured_interval_seconds=20,
        generation_id="watchdog-primary",
    )
    calls: list[int] = []

    async def duplicate_tick():
        calls.append(1)
        return {}

    duplicate = asyncio.run(
        queue.run_product_video_watchdog_scheduler_loop(
            duplicate_tick,
            configured_interval_seconds=20,
            generation_id="watchdog-duplicate",
            max_ticks=1,
        )
    )
    queue.mark_product_video_watchdog_scheduler(
        registered=True,
        running=False,
        configured_interval_seconds=20,
        generation_id="watchdog-primary",
    )

    assert first["scheduler_start_accepted"] is True
    assert duplicate["duplicate_scheduler_prevented"] is True
    assert duplicate["ticks_executed"] == 0
    assert calls == []


@pytest.mark.parametrize(
    ("configured", "effective", "clamped"),
    [(5, 15, True), (300, 30, True), (20, 20, False)],
)
def test_watchdog_interval_is_locked_to_15_30_seconds(configured, effective, clamped):
    config = queue.product_video_watchdog_interval_config(configured)
    assert config["effective_interval_seconds"] == effective
    assert config["clamp_applied"] is clamped


def test_worker_generation_authority_and_conflict_fail_closed():
    now = datetime(2030, 1, 2, 3, 4, 5)
    runtime_sha = "45e5ea499465588563a746a5cc2f962762a9244a"
    active = _worker_generation(now, "generation-new")
    expired = _worker_generation(now, "generation-old", heartbeat_age_seconds=600, lease_seconds=-500)

    one = remote_worker_api.product_video_worker_compatibility([active], runtime_sha=runtime_sha, now=now)
    restarted = remote_worker_api.product_video_worker_compatibility([active, expired], runtime_sha=runtime_sha, now=now)
    conflict = remote_worker_api.product_video_worker_compatibility(
        [active, _worker_generation(now, "generation-other")],
        runtime_sha=runtime_sha,
        now=now,
    )

    assert one["compatible"] is True
    assert one["authoritative_worker_generation_id"] == "generation-new"
    assert one["runtime_target_sha"] == runtime_sha
    assert one["lease_valid"] is True
    assert one["hostname"] == "vpssieutoc"
    assert one["pid"] == 13100
    assert restarted["compatible"] is True
    assert restarted["stale_worker_generations"] == ["generation-old"]
    assert conflict["compatible"] is False
    assert conflict["worker_identity_conflict"] is True
    assert conflict["duplicate_active_worker_generations"] is True
    assert set(conflict["active_worker_generation_ids"]) == {"generation-new", "generation-other"}
    assert conflict["block_reason"] == "worker_generation_conflict"


def test_generic_stale_heartbeat_is_ignored_and_worker_block_reasons_are_exact():
    now = datetime(2030, 1, 2, 3, 4, 5)
    runtime_sha = "45e5ea499465588563a746a5cc2f962762a9244a"
    generic_stale = {
        **_worker_generation(now, "generic-old", heartbeat_age_seconds=600, lease_seconds=-500),
        "service_mode": "general",
        "capabilities": ["ffmpeg"],
    }
    active = _worker_generation(now, "owner-current")
    selected = remote_worker_api.product_video_worker_compatibility(
        [generic_stale, active],
        runtime_sha=runtime_sha,
        now=now,
    )
    expired = remote_worker_api.product_video_worker_compatibility(
        [_worker_generation(now, "expired", lease_seconds=-1)],
        runtime_sha=runtime_sha,
        now=now,
    )
    bad_capability = remote_worker_api.product_video_worker_compatibility(
        [_worker_generation(now, "bad-capability", capability_version="old-capability")],
        runtime_sha=runtime_sha,
        now=now,
    )
    bad_sha = remote_worker_api.product_video_worker_compatibility(
        [_worker_generation(now, "bad-sha", sha="different-sha")],
        runtime_sha=runtime_sha,
        now=now,
    )

    assert selected["compatible"] is True
    assert selected["authoritative_worker_generation_id"] == "owner-current"
    assert selected["heartbeat_records_considered"] == 1
    assert expired["block_reason"] == "worker_lease_expired"
    assert bad_capability["block_reason"] == "worker_capability_mismatch"
    assert bad_sha["block_reason"] == "worker_sha_mismatch"


def test_claim_uses_shared_compatibility_and_does_not_consume_outbox_when_blocked(tmp_path):
    conn = _conn(tmp_path)
    job, project = _legacy_zero_task_job(conn, age_seconds=90)
    queue.ensure_product_video_dispatch_outbox(
        conn,
        job_id=int(job["id"]),
        project_id=int(project["project_id"]),
        scene_indexes=[1, 2],
    )
    now = datetime(2030, 1, 2, 3, 4, 5)
    runtime_sha = "45e5ea499465588563a746a5cc2f962762a9244a"
    compatibility = remote_worker_api.product_video_worker_compatibility(
        [_worker_generation(now, "one"), _worker_generation(now, "two")],
        runtime_sha=runtime_sha,
        caller_generation_id="two",
        now=now,
    )

    result = remote_worker_api.claim_remote_worker_job(
        conn,
        worker_id="owner-product-video",
        capabilities=["owner_product_video", queue.PRODUCT_VIDEO_CANONICAL_WORKER_CAPABILITY],
        owner_product_video_only=True,
        worker_compatibility=compatibility,
    )
    outbox = queue.get_product_video_dispatch_outbox(conn, job_id=int(job["id"]))

    assert result["job"] is None
    assert result["status"] == "blocked"
    assert result["reason"] == "worker_generation_conflict"
    assert result["provider_submit_called"] is False
    assert result["debug"]["exact_claim_block_reason"] == "worker_generation_conflict"
    assert outbox["dispatch_status"] == "pending"
    assert outbox["attempt_count"] == 0


def test_shared_compatibility_result_is_identical_for_admission_claim_and_watchdog():
    now = datetime(2030, 1, 2, 3, 4, 5)
    runtime_sha = "45e5ea499465588563a746a5cc2f962762a9244a"
    records = [_worker_generation(now, "shared-generation")]
    results = [
        remote_worker_api.product_video_worker_compatibility(
            records,
            runtime_sha=runtime_sha,
            caller_generation_id="shared-generation" if context == "claim" else "",
            now=now,
        )
        for context in ("admission", "claim", "watchdog")
    ]
    assert {item["compatible"] for item in results} == {True}
    assert {item["worker_sha"] for item in results} == {runtime_sha}
    assert {item["block_reason"] for item in results} == {""}


def test_complete_dispatch_outbox_contract_matches_exact_query_and_terminal_truth(tmp_path):
    conn = _conn(tmp_path)
    job, project = _legacy_zero_task_job(conn, age_seconds=90)
    queue.ensure_product_video_dispatch_outbox(
        conn,
        job_id=int(job["id"]),
        project_id=int(project["project_id"]),
        scene_indexes=[1, 2],
    )
    pending = queue.product_video_dispatch_outbox_diagnostic(conn, job_id=int(job["id"]))
    required = {
        "dispatch_outbox_present",
        "dispatch_outbox_id",
        "dispatch_outbox_status",
        "dispatch_outbox_owner",
        "dispatch_outbox_available_at",
        "dispatch_outbox_attempt_count",
        "dispatch_outbox_last_attempt_at",
        "dispatch_outbox_lease_owner",
        "dispatch_outbox_lease_expires_at",
        "dispatch_outbox_claimable",
        "dispatch_outbox_claim_block_reason",
        "dispatch_outbox_acknowledged_at",
        "dispatch_outbox_last_error",
        "dispatch_outbox_terminal_reason",
    }
    assert required <= set(pending)
    assert pending["dispatch_outbox_claimable"] is pending["claimable"] is True
    assert pending["dispatch_outbox_claim_block_reason"] == ""

    queue.run_product_video_watchdog_scheduler_tick(
        conn,
        eligibility_evaluator=lambda *_args: _eligibility([]),
    )
    terminal = queue.product_video_dispatch_outbox_diagnostic(conn, job_id=int(job["id"]))
    failed = queue.get_video_render_job(conn, int(job["id"]))
    payload = _payload(failed)

    assert terminal["dispatch_outbox_status"] == "terminal_failed"
    assert terminal["dispatch_outbox_claimable"] is False
    assert terminal["dispatch_outbox_claim_block_reason"] == "dispatch_outbox_terminal_failed"
    assert terminal["dispatch_outbox_terminal_reason"] == "no_eligible_provider_before_scene_dispatch"
    assert payload["dispatch_outbox_claimable"] is False
    assert payload["dispatch_outbox_terminal_reason"] == "no_eligible_provider_before_scene_dispatch"
    assert payload["terminal_state"] == "failed_no_charge"
    assert payload["continue_polling"] is False
    assert payload["provider_http_status"] == 0
    assert payload["fallback_count_effective"] == 0
    assert payload["charged_xu"] == 0
    progress_debug = product_progress_status.product_progress_debug_payload(
        "multiscene_video",
        str(job["id"]),
        {**payload, "status": failed["status"]},
    )
    assert progress_debug["dispatch_outbox_claimable"] is False
    assert progress_debug["dispatch_outbox_terminal_reason"] == "no_eligible_provider_before_scene_dispatch"
    assert progress_debug["terminal_state"] == "failed_no_charge"
    assert progress_debug["route_requires_provider"] is True


def test_bot_wires_production_scheduler_and_shared_compatibility_at_all_gates():
    source = (ROOT / "bot.py").read_text(encoding="utf-8")
    worker_source = (ROOT / "remote_worker.py").read_text(encoding="utf-8")
    assert "video_project_queue.run_product_video_watchdog_scheduler_loop(" in source
    assert "if tg_product_video_watchdog_task is None or tg_product_video_watchdog_task.done():" in source
    assert source.count("def product_video_worker_admission_status(") == 1
    assert "product_video_worker_compatibility(" in source
    assert "worker_compatibility=worker_compatibility" in source
    assert "worker_compatibility = product_video_worker_admission_status(" in source
    assert "worker = product_video_worker_admission_status()" in source
    assert source.count("*_video_dispatch_outbox_debug_lines(result)") >= 2
    for field in (
        "worker_instance_id",
        "generation_id",
        "runtime_target_sha",
        "lease_expires_at",
        "hostname",
        "pid",
    ):
        assert field in worker_source
