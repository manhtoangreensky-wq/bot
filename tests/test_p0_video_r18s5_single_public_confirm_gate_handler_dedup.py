import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import remote_worker
from services import remote_worker_api
from services import video_project_queue as queue
from services import video_provider_router as router


ROOT = Path(__file__).resolve().parents[1]


def _conn(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "r18s5.db")
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
        "product_type": "video_ai_prompt",
        "engine_adapter": "text_to_video",
        "orchestration_mode": "per_scene_8s",
        "provider_orchestration_mode": "per_scene_8s",
        "provider_chain": ["shopaikey_video"],
        "provider_order": "shopaikey_video",
        "scene_count": scene_count,
    }
    invoice = {
        **shared,
        "tier": "basic",
        "package_xu": 300,
        "quality_tier": 300,
        "scene_duration_seconds": 8,
        "duration_seconds": scene_count * 8,
        "total_xu": 300,
        "user_visible_price_xu": 300,
        "persisted_quoted_price_xu": 300,
        "customer_charge_planned_xu": 300,
        "wallet_charge_amount_xu": 300,
        "list_price_xu": 400,
        "provider_budget_xu": 400,
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
        status="draft_invoice",
        invoice_json=invoice,
        scene_count=scene_count,
        prompt_text="fixture product video",
        quality_tier=300,
        total_xu_estimated=300,
    )
    return queue.get_video_project(conn, int(project["project_id"]))


def _admission(
    project: dict,
    *,
    candidates=None,
    checked_at: datetime | None = None,
    worker_ok: bool = True,
    worker_reason: str = "",
    snapshot_id: str = "r18s5-snapshot",
    user_id: int | None = None,
    project_id: int | None = None,
    quote_fingerprint: str | None = None,
    duplicate_handler: bool = False,
    failure_stage: str = "",
) -> dict:
    candidates = list(["shopaikey_video"] if candidates is None else candidates)
    moment = checked_at or datetime.now()
    actual_user_id = int(project["user_id"])
    actual_project_id = int(project["project_id"])
    quote = queue.product_video_admission_quote_fingerprint(project, actual_user_id)
    route = router.product_video_route_contract("video_ai_prompt", "text_to_video", "per_scene_8s")
    snapshot = {
        "provider_eligibility_snapshot_id": snapshot_id,
        "admission_snapshot_id": snapshot_id,
        "admission_checked_at": queue.now_text(moment),
        "admission_user_id": actual_user_id if user_id is None else int(user_id),
        "admission_project_id": actual_project_id if project_id is None else int(project_id),
        "admission_quote_fingerprint": quote if quote_fingerprint is None else quote_fingerprint,
        "admission_callback_handler_id": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID,
        "admission_callback_data": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_CALLBACK,
        "eligible_provider_keys": candidates,
        "runtime_candidate_keys": candidates,
        "final_eligible_provider_count": len(candidates),
    }
    admission = {
        "ok": bool(candidates and worker_ok),
        "provider_eligibility_snapshot": snapshot,
        "provider_eligibility_snapshot_id": snapshot_id,
        "admission_snapshot_id": snapshot_id,
        "admission_checked_at": queue.now_text(moment),
        "admission_ttl_seconds": 60,
        "admission_candidate_keys": candidates,
        "admission_candidate_count": len(candidates),
        "admission_result": "PASS" if candidates and worker_ok else "BLOCKED",
        "admission_block_reason": "" if candidates and worker_ok else (worker_reason or "no_eligible_product_video_provider"),
        "admission_user_id": actual_user_id if user_id is None else int(user_id),
        "admission_project_id": actual_project_id if project_id is None else int(project_id),
        "admission_quote_fingerprint": quote if quote_fingerprint is None else quote_fingerprint,
        "admission_callback_handler_id": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID,
        "admission_callback_data": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_CALLBACK,
        "admission_worker_runtime_sha": "0400e614d4e2",
        "admission_worker_sha": "0400e614d4e2" if worker_ok else "778ba8eb555a",
        "admission_worker_version_compatible": worker_ok,
        "admission_route_requires_provider": bool(route["route_requires_provider"]),
        "admission_provider_health_gate_pass": bool(candidates),
        "worker_generation_id": "r18s5-generation",
        "worker_git_sha": "0400e614d4e2",
        "runtime_sha": "0400e614d4e2",
        "worker_compatible": worker_ok,
        "worker_connected": worker_ok,
        "worker_heartbeat_fresh": worker_ok,
        "worker_lease_valid": worker_ok,
        "worker_sha_match": worker_ok,
        "worker_capability_match": worker_ok,
        "worker_identity_conflict": False,
        "route_requires_provider": bool(route["route_requires_provider"]),
        "handler_id": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID,
        "worker_admission_block_reason": worker_reason,
        "duplicate_confirm_handler_detected": duplicate_handler,
        "_test_failure_stage": failure_stage,
    }
    return queue.sign_product_video_final_admission_context(admission)


def _confirm(conn: sqlite3.Connection, project: dict, admission: dict) -> dict:
    return queue.confirm_public_product_video_invoice(
        conn,
        project_id=int(project["project_id"]),
        user_id=int(project["user_id"]),
        balance_xu=300,
        provider_admission=admission,
    )


def _counts(conn: sqlite3.Connection) -> tuple[int, int, int]:
    return tuple(
        conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("video_jobs", "video_scenes", "video_dispatch_outbox")
    )


@pytest.mark.parametrize(
    ("admission_kwargs", "reason"),
    [
        ({"candidates": []}, "no_eligible_product_video_provider"),
        ({"worker_ok": False, "worker_reason": "owner_product_video_worker_version_mismatch"}, "owner_product_video_worker_version_mismatch"),
        ({"worker_ok": False, "worker_reason": "owner_product_video_worker_disconnected"}, "owner_product_video_worker_disconnected"),
        ({"worker_ok": False, "worker_reason": "owner_product_video_worker_heartbeat_stale"}, "owner_product_video_worker_heartbeat_stale"),
        ({"duplicate_handler": True}, "duplicate_product_video_confirm_handler"),
    ],
)
def test_public_gate_blocks_before_any_insert(tmp_path, admission_kwargs, reason):
    conn = _conn(tmp_path)
    project = _project(conn)
    result = _confirm(conn, project, _admission(project, **admission_kwargs))
    assert result["ok"] is False
    assert result["reason"] == reason
    assert _counts(conn) == (0, 0, 0)
    assert result["charge"] == 0


@pytest.mark.parametrize(
    "admission_kwargs",
    [
        {"checked_at": datetime.now() - timedelta(seconds=61)},
        {"user_id": 999},
        {"project_id": 999},
        {"quote_fingerprint": "wrong-quote"},
    ],
)
def test_snapshot_identity_and_ttl_cannot_be_bypassed(tmp_path, admission_kwargs):
    conn = _conn(tmp_path)
    project = _project(conn)
    result = _confirm(conn, project, _admission(project, **admission_kwargs))
    assert result["ok"] is False
    assert _counts(conn) == (0, 0, 0)


def test_authoritative_confirm_creates_exact_job_scenes_outbox_and_handoff(tmp_path):
    conn = _conn(tmp_path)
    project = _project(conn)
    result = _confirm(conn, project, _admission(project))
    assert result["ok"] is True
    assert _counts(conn) == (1, 2, 1)
    job = result["job"]
    payload = json.loads(job["result_json"])
    assert payload["admission_handler_id"] == queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID
    assert payload["canonical_engine_entry"] == "b13_r18c"
    assert payload["scene_dispatch_count"] == 2
    assert payload["finalizer_reached"] is False
    assert payload["route_requires_provider"] is True
    outbox = queue.claim_product_video_dispatch_outbox(conn, worker_id="r18s5-worker")
    assert int(outbox["job_id"]) == int(job["id"])
    hydrated = queue.hydrate_video_job_payload(conn, job)
    worker_payload = remote_worker_api.build_worker_job_payload(hydrated)
    assert worker_payload["canonical_engine_entry"] == "b13_r18c"
    assert worker_payload["scene_dispatch_count"] == 2
    assert worker_payload["route_requires_provider"] is True


def test_admission_snapshot_is_single_use(tmp_path):
    conn = _conn(tmp_path)
    project = _project(conn)
    admission = _admission(project)
    first = _confirm(conn, project, admission)
    second = _confirm(conn, queue.get_video_project(conn, int(project["project_id"])), admission)
    assert first["ok"] is True
    assert second["ok"] is False
    assert second["reason"] == "admission_snapshot_replayed"
    assert _counts(conn) == (1, 2, 1)


@pytest.mark.parametrize(
    "failure_stage",
    ["after_job_insert", "after_scene_insert", "after_outbox_insert", "before_snapshot_consume", "during_commit"],
)
def test_transaction_failure_rolls_back_every_record(tmp_path, failure_stage):
    conn = _conn(tmp_path)
    project = _project(conn)
    result = _confirm(conn, project, _admission(project, failure_stage=failure_stage))
    assert result["ok"] is False
    assert result["reason"] == "dispatch_outbox_transaction_failed"
    assert _counts(conn) == (0, 0, 0)
    persisted = queue.get_video_project(conn, int(project["project_id"]))
    assert persisted["status"] == "draft_invoice"
    assert persisted["is_confirmed"] == 0


def test_route_contract_is_authoritative_and_state_independent():
    contract = router.product_video_route_contract(
        "video_ai_prompt",
        "text_to_video",
        "per_scene_8s",
    )
    assert contract == {
        "route_requires_provider": True,
        "route_requirement_source": "product_video_text_per_scene_contract",
        "allowed_execution_modes": ["provider_per_scene_8s"],
        "local_renderer_selected": False,
        "provider_required_reason": "text_to_video_per_scene_requires_provider",
    }


def test_job_131_zero_task_reconciles_failed_no_charge_without_worker(tmp_path):
    conn = _conn(tmp_path)
    project = _project(conn)
    legacy = queue.confirm_video_project_invoice(
        conn,
        project_id=int(project["project_id"]),
        user_id=int(project["user_id"]),
    )
    job_id = int(legacy["job"]["id"])
    old = datetime.now() - timedelta(minutes=3)
    fixture = {
        "source": "product_video",
        "product_video": True,
        "scene_count": 2,
        "provider_candidates_count": 0,
        "runtime_candidate_keys": [],
        "provider_router_called": False,
        "provider_submit_called": False,
        "provider_http_status": 0,
        "admission_worker_runtime_sha": "0400e614d4e2",
        "admission_worker_sha": "778ba8eb555a",
        "charged_xu": 0,
        "charge": 0,
        "public_confirmed_at": queue.now_text(old),
    }
    conn.execute(
        "UPDATE video_jobs SET result_json=?,created_at=?,updated_at=? WHERE id=?",
        (json.dumps(fixture), queue.now_text(old), queue.now_text(old), job_id),
    )
    conn.commit()
    report = queue.sweep_product_video_zero_task_watchdog(
        conn,
        now=datetime.now(),
        job_id=job_id,
        eligibility_evaluator=lambda *_: {
            "eligible_provider_keys": [],
            "runtime_candidate_keys": [],
            "final_eligible_provider_count": 0,
            "reconciliation_reason": "worker_version_mismatch_before_dispatch",
        },
    )
    assert report["terminal_failed"] == 1
    job = queue.get_video_render_job(conn, job_id)
    result = json.loads(job["result_json"])
    outbox = queue.get_product_video_dispatch_outbox(conn, job_id=job_id)
    assert job["status"] == "failed"
    assert result["terminal_state"] == "failed_no_charge"
    assert result["continue_polling"] is False
    assert result["provider_http_status"] == 0
    assert result["fallback_count_effective"] == 0
    assert result["concat_attempted"] is False
    assert result["delivery_attempted"] is False
    assert result["charged_xu"] == 0
    assert outbox["dispatch_status"] == "terminal_failed"


def test_handler_registration_and_catch_all_cannot_own_confirm():
    source = (ROOT / "bot.py").read_text(encoding="utf-8")
    assert 'pattern=r"^vproduct\\|b14_confirm$"' in source
    assert 'pattern=r"^vproduct\\|(?!b14_confirm(?:\\||$))"' in source
    assert "return await handle_product_video_public_confirm_callback(update, context)" in source
    assert "CallbackQueryHandler(safe_mode_callback_guard), group=-10" in source
    assert "product_video_confirm_handler_count" in source
    assert "duplicate_callback_pattern_detected" in source


def test_owner_worker_reports_canonical_capability_without_provider_call():
    capabilities = remote_worker.product_video_worker_capabilities()
    assert queue.PRODUCT_VIDEO_CANONICAL_WORKER_CAPABILITY in capabilities
    source = (ROOT / "remote_worker.py").read_text(encoding="utf-8")
    assert '"worker_service_mode"' in source
    assert '"worker_capability_version"' in source
    assert "run_provider_generation" not in source


def test_no_mp4_and_hidden_paths_never_charge_or_submit():
    bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")
    watchdog_source = bot_source[bot_source.index("def product_video_bot_watchdog_eligibility"):]
    watchdog_source = watchdog_source[:watchdog_source.index("def product_video_apply_provider_preflight_to_session")]
    assert "run_provider_generation" not in watchdog_source
    assert '"no_provider_call_verified": True' in watchdog_source
    assert '"no_charge_verified"' in watchdog_source
    assert "TOAN AAS chưa thể bắt đầu tạo video. Hệ thống chưa trừ Xu." in bot_source
