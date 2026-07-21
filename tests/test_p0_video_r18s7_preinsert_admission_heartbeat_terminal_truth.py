import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from services import product_progress_status
from services import remote_worker_api
from services import video_project_queue as queue
from services import video_provider_router as router


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SHA = "8c182f8b5f2ab975c06af445cf931a57df564451"


def _conn(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "r18s7.db")
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _project(conn: sqlite3.Connection, *, user_id: int = 132, scene_count: int = 2) -> dict:
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
        "scene_count": scene_count,
    }
    invoice = {
        **shared,
        "tier": "basic",
        "package_xu": 300,
        "quality_tier": 300,
        "duration_seconds": scene_count * 8,
        "scene_duration_seconds": 8,
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
        topic="fixture #132",
        ratio="9:16",
        asset_pack=shared,
    )
    queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="draft_invoice",
        invoice_json=invoice,
        scene_count=scene_count,
        prompt_text="fixture #132 blocked final confirm",
        quality_tier=300,
        total_xu_estimated=300,
    )
    return queue.get_video_project(conn, int(project["project_id"]))


def _admission(project: dict, *, candidates=None, snapshot_id: str = "r18s7-snapshot", **overrides) -> dict:
    keys = list(["shopaikey_video"] if candidates is None else candidates)
    checked_at = queue.now_text()
    quote = queue.product_video_admission_quote_fingerprint(project, int(project["user_id"]))
    route = router.product_video_route_contract("video_ai_prompt", "text_to_video", "per_scene_8s")
    snapshot = {
        "provider_eligibility_snapshot_id": snapshot_id,
        "admission_snapshot_id": snapshot_id,
        "admission_checked_at": checked_at,
        "admission_user_id": int(project["user_id"]),
        "admission_project_id": int(project["project_id"]),
        "admission_quote_fingerprint": quote,
        "admission_callback_handler_id": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID,
        "admission_callback_data": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_CALLBACK,
        "eligible_provider_keys": keys,
        "runtime_candidate_keys": keys,
        "final_eligible_provider_count": len(keys),
    }
    admission = {
        "ok": bool(keys),
        "provider_eligibility_snapshot": snapshot,
        "provider_eligibility_snapshot_id": snapshot_id,
        "admission_snapshot_id": snapshot_id,
        "admission_checked_at": checked_at,
        "admission_ttl_seconds": 60,
        "admission_candidate_keys": keys,
        "admission_candidate_count": len(keys),
        "admission_result": "PASS" if keys else "BLOCKED",
        "admission_block_reason": "" if keys else "no_eligible_product_video_provider",
        "admission_user_id": int(project["user_id"]),
        "admission_project_id": int(project["project_id"]),
        "admission_quote_fingerprint": quote,
        "admission_callback_handler_id": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID,
        "admission_callback_data": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_CALLBACK,
        "admission_provider_health_gate_pass": bool(keys),
        "admission_worker_runtime_sha": RUNTIME_SHA,
        "admission_worker_sha": RUNTIME_SHA,
        "admission_worker_version_compatible": True,
        "admission_route_requires_provider": bool(route["route_requires_provider"]),
        "worker_generation_id": "generation-r18s7",
        "worker_git_sha": RUNTIME_SHA,
        "runtime_sha": RUNTIME_SHA,
        "worker_compatible": True,
        "worker_connected": True,
        "worker_heartbeat_fresh": True,
        "worker_lease_valid": True,
        "worker_sha_match": True,
        "worker_capability_match": True,
        "worker_identity_conflict": False,
        "route_requires_provider": True,
        "handler_id": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID,
        "worker_admission_block_reason": "",
        "duplicate_confirm_handler_detected": False,
    }
    admission.update(overrides)
    return queue.sign_product_video_final_admission_context(admission)


def _confirm(conn: sqlite3.Connection, project: dict, admission: dict) -> dict:
    return queue.confirm_public_product_video_invoice(
        conn,
        project_id=int(project["project_id"]),
        user_id=int(project["user_id"]),
        balance_xu=300,
        provider_admission=admission,
    )


def _counts(conn: sqlite3.Connection) -> tuple[int, int, int, int]:
    return tuple(
        int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in ("video_projects", "video_jobs", "video_scenes", "video_dispatch_outbox")
    )


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"candidates": []}, "no_eligible_product_video_provider"),
        ({"worker_connected": False, "worker_compatible": False, "worker_admission_block_reason": "worker_disconnected"}, "worker_disconnected"),
        ({"worker_heartbeat_fresh": False, "worker_admission_block_reason": "worker_heartbeat_stale"}, "worker_heartbeat_stale"),
        ({"worker_lease_valid": False, "worker_admission_block_reason": "worker_lease_expired"}, "worker_lease_expired"),
        ({"worker_sha_match": False, "worker_admission_block_reason": "worker_sha_mismatch"}, "worker_sha_mismatch"),
        ({"worker_capability_match": False, "worker_admission_block_reason": "worker_capability_mismatch"}, "worker_capability_mismatch"),
        ({"worker_identity_conflict": True}, "worker_generation_conflict"),
        ({"admission_provider_health_gate_pass": False, "admission_block_reason": "provider_health_gate_blocked"}, "provider_health_gate_blocked"),
        ({"admission_result": "BLOCKED", "ok": False, "admission_block_reason": "provider_health_gate_blocked"}, "provider_health_gate_blocked"),
        ({"route_requires_provider": False, "admission_route_requires_provider": False}, "product_video_route_contract_mismatch"),
        ({"admission_callback_handler_id": "legacy_public_confirm"}, "admission_callback_handler_mismatch"),
    ],
)
def test_fixture_132_final_admission_failures_create_zero_records(tmp_path, overrides, reason):
    conn = _conn(tmp_path)
    project = _project(conn)
    options = dict(overrides)
    candidate_override = options.pop("candidates", None) if "candidates" in options else None
    admission = _admission(project, candidates=[] if candidate_override == [] else None, **options)

    result = _confirm(conn, project, admission)

    assert result["ok"] is False
    assert result["reason"] == reason
    assert _counts(conn) == (1, 0, 0, 0)
    assert result["charge"] == 0
    assert result["job_created"] is False
    assert "Hệ thống chưa trừ Xu" in result["public_message"]


def test_unsigned_legacy_public_context_is_rejected_without_insert(tmp_path):
    conn = _conn(tmp_path)
    project = _project(conn)
    unsigned = _admission(project)
    unsigned.pop("admission_context_signature")

    result = _confirm(conn, project, unsigned)

    assert result["reason"] == "admission_context_missing_or_invalid"
    assert _counts(conn) == (1, 0, 0, 0)


def test_signed_candidate_snapshot_cannot_be_swapped_after_admission(tmp_path):
    conn = _conn(tmp_path)
    project = _project(conn)
    tampered = _admission(project)
    tampered["admission_candidate_keys"] = ["key4u_video"]

    result = _confirm(conn, project, tampered)

    assert result["reason"] == "admission_context_missing_or_invalid"
    assert _counts(conn) == (1, 0, 0, 0)


def test_exact_job_132_blocked_fixture_combines_zero_candidates_stale_worker_and_gate_block(tmp_path):
    conn = _conn(tmp_path)
    project = _project(conn)
    admission = _admission(
        project,
        candidates=[],
        admission_provider_health_gate_pass=False,
        worker_compatible=False,
        worker_connected=False,
        worker_heartbeat_fresh=False,
        worker_lease_valid=False,
        worker_admission_block_reason="worker_heartbeat_stale",
    )

    result = _confirm(conn, project, admission)

    assert result["reason"] == "no_eligible_product_video_provider"
    assert _counts(conn) == (1, 0, 0, 0)
    assert result["charge"] == 0


def test_signed_snapshot_is_consumed_once_and_positive_path_reaches_b13_r18c(tmp_path):
    conn = _conn(tmp_path)
    project = _project(conn)
    admission = _admission(project)

    first = _confirm(conn, project, admission)
    second = _confirm(conn, queue.get_video_project(conn, int(project["project_id"])), admission)

    assert first["ok"] is True
    assert _counts(conn) == (1, 1, 2, 1)
    payload = json.loads(first["job"]["result_json"])
    persisted_project = queue.get_video_project(conn, int(project["project_id"]))
    persisted_invoice = json.loads(persisted_project["invoice_json"])
    assert payload["canonical_engine_entry"] == queue.PRODUCT_VIDEO_CANONICAL_ENGINE_ENTRY
    assert payload["route_requires_provider"] is True
    assert persisted_invoice["admission_snapshot_consumed"] is True
    assert persisted_invoice["admission_snapshot_consumed_id"] == "r18s7-snapshot"
    assert second["ok"] is False
    assert second["reason"] == "admission_snapshot_replayed"
    assert _counts(conn) == (1, 1, 2, 1)
    claimed_outbox = queue.claim_product_video_dispatch_outbox(conn, worker_id="owner-r18s7")
    assert int(claimed_outbox["job_id"]) == int(first["job"]["id"])
    assert claimed_outbox["scene_indexes"] == [1, 2]


def test_inner_transaction_assertion_stops_toctou_before_first_insert(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    project = _project(conn)
    original = queue.product_video_assert_final_admission
    calls = {"count": 0}

    def raced(*args, **kwargs):
        calls["count"] += 1
        state = original(*args, **kwargs)
        if calls["count"] == 2:
            return {
                **state,
                "admission_passed": False,
                "admission_block_reason": "worker_lease_expired",
                "admission_pre_insert_hard_stop": True,
            }
        return state

    monkeypatch.setattr(queue, "product_video_assert_final_admission", raced)
    result = _confirm(conn, project, _admission(project))

    assert calls["count"] == 2
    assert result["ok"] is False
    assert result["reason"] == "worker_lease_expired"
    assert _counts(conn) == (1, 0, 0, 0)


def _heartbeat_record(now: datetime, *, generation: str = "generation-r18s7", heartbeat_age: int = 0, lease_delta: int = 90) -> dict:
    capability = queue.PRODUCT_VIDEO_CANONICAL_WORKER_CAPABILITY
    return {
        "worker_id": "owner-product-video",
        "worker_instance_id": "owner-product-video:instance",
        "generation_id": generation,
        "git_sha": RUNTIME_SHA,
        "runtime_target_sha": RUNTIME_SHA,
        "service_mode": "owner_product_video",
        "capability_version": capability,
        "capabilities": ["owner_product_video", capability],
        "heartbeat_at": queue.now_text(now - timedelta(seconds=heartbeat_age)),
        "lease_expires_at": queue.now_text(now + timedelta(seconds=lease_delta)),
        "last_claim_at": queue.now_text(now),
        "last_idle_claim_at": queue.now_text(now),
        "heartbeat_refresh_source": "claim_idle",
    }


def _heartbeat_payload(*, generation: str = "generation-r18s7", service_mode: str = "owner_product_video") -> dict:
    capability = queue.PRODUCT_VIDEO_CANONICAL_WORKER_CAPABILITY
    return {
        "worker_id": "owner-product-video",
        "worker_instance_id": "owner-product-video:instance",
        "generation_id": generation,
        "git_sha": RUNTIME_SHA,
        "runtime_target_sha": RUNTIME_SHA,
        "service_mode": service_mode,
        "capability_version": capability,
        "capabilities": ["owner_product_video", capability],
        "process_started_at": "2030-01-02 03:00:00",
        "hostname": "vps",
        "pid": 132,
    }


def test_idle_claim_and_successful_heartbeat_refresh_authoritative_lease():
    now = datetime(2030, 1, 2, 3, 4, 5)
    decision = remote_worker_api.owner_product_video_heartbeat_update_decision(
        [_heartbeat_record(now, heartbeat_age=20, lease_delta=70)],
        _heartbeat_payload(),
        runtime_sha=RUNTIME_SHA,
        now=now,
        heartbeat_ttl_seconds=90,
    )

    assert decision["heartbeat_accepted"] is True
    assert decision["owner_heartbeat_request_received"] is True
    assert decision["caller_generation_id"] == "generation-r18s7"
    assert decision["authoritative_generation_id"] == "generation-r18s7"
    assert decision["caller_git_sha"] == RUNTIME_SHA
    assert decision["lease_expires_at"] == queue.now_text(now + timedelta(seconds=90))


def test_transient_502_does_not_expire_worker_and_next_success_recovers_lease():
    now = datetime(2030, 1, 2, 3, 4, 5)
    records = [_heartbeat_record(now, heartbeat_age=0, lease_delta=90)]
    during_502 = remote_worker_api.product_video_worker_compatibility(
        records,
        runtime_sha=RUNTIME_SHA,
        now=now + timedelta(seconds=40),
        heartbeat_ttl_seconds=90,
    )
    recovered = remote_worker_api.owner_product_video_heartbeat_update_decision(
        records,
        _heartbeat_payload(),
        runtime_sha=RUNTIME_SHA,
        now=now + timedelta(seconds=50),
        heartbeat_ttl_seconds=90,
    )

    assert during_502["worker_connected"] is True
    assert during_502["worker_version_compatible"] is True
    assert recovered["heartbeat_accepted"] is True
    assert recovered["lease_expires_at"] == queue.now_text(now + timedelta(seconds=140))


def test_wrong_generation_is_rejected_but_expired_generation_can_be_replaced():
    now = datetime(2030, 1, 2, 3, 4, 5)
    wrong = remote_worker_api.owner_product_video_heartbeat_update_decision(
        [_heartbeat_record(now)],
        _heartbeat_payload(generation="generation-r18s7-new"),
        runtime_sha=RUNTIME_SHA,
        now=now,
    )
    expired = remote_worker_api.owner_product_video_heartbeat_update_decision(
        [_heartbeat_record(now, heartbeat_age=200, lease_delta=-100)],
        _heartbeat_payload(generation="generation-r18s7-new"),
        runtime_sha=RUNTIME_SHA,
        now=now,
    )

    assert wrong["heartbeat_accepted"] is False
    assert wrong["owner_heartbeat_reject_reason"] == "worker_generation_conflict"
    assert expired["heartbeat_accepted"] is True


def test_malformed_generation_update_is_rejected_without_authoritative_replacement():
    now = datetime(2030, 1, 2, 3, 4, 5)
    malformed = remote_worker_api.owner_product_video_heartbeat_update_decision(
        [_heartbeat_record(now)],
        _heartbeat_payload(generation="bad id"),
        runtime_sha=RUNTIME_SHA,
        now=now,
    )

    assert malformed["heartbeat_accepted"] is False
    assert malformed["owner_heartbeat_reject_reason"] == "worker_generation_malformed"
    assert malformed["authoritative_generation_id"] == "generation-r18s7"


def test_generic_heartbeat_cannot_replace_owner_record():
    now = datetime(2030, 1, 2, 3, 4, 5)
    decision = remote_worker_api.owner_product_video_heartbeat_update_decision(
        [_heartbeat_record(now)],
        {
            "worker_id": "generic-worker",
            "generation_id": "generic-generation",
            "git_sha": RUNTIME_SHA,
            "runtime_target_sha": RUNTIME_SHA,
            "service_mode": "default_video",
            "capabilities": ["video_render"],
        },
        runtime_sha=RUNTIME_SHA,
        now=now,
    )

    assert decision["heartbeat_accepted"] is False
    assert decision["owner_heartbeat_request_received"] is False
    assert decision["owner_heartbeat_reject_reason"] == "not_owner_product_video_heartbeat"
    assert decision["authoritative_generation_id"] == "generation-r18s7"


def _historical_zero_task_job(conn: sqlite3.Connection, *, age_seconds: int = 90) -> tuple[dict, dict]:
    project = _project(conn)
    legacy = queue.confirm_video_project_invoice(
        conn,
        project_id=int(project["project_id"]),
        user_id=int(project["user_id"]),
    )
    job = legacy["job"]
    old = datetime.now() - timedelta(seconds=age_seconds)
    payload = {
        "source": "product_video",
        "product_video": True,
        "product_type": "video_ai_prompt",
        "engine_adapter": "text_to_video",
        "orchestration_mode": "per_scene_8s",
        "route_requires_provider": True,
        "scene_count": 2,
        "scene_tasks_total": 2,
        "scene_tasks": queue.product_video_initial_scene_tasks(int(job["id"]), 2),
        "runtime_candidate_keys": [],
        "preconfirm_candidate_keys": [],
        "runtime_candidates_evaluated": True,
        "final_eligible_provider_count": 0,
        "public_confirm_kickoff_attempted": True,
        "provider_submit_called": False,
        "provider_http_request_sent": False,
        "provider_http_status": 0,
        "fallback_count_effective": 0,
        "concat_attempted": False,
        "delivery_attempted": False,
        "wallet_charge_recorded": False,
        "charged_xu": 0,
        "charge": 0,
        "public_confirmed_at": queue.now_text(old),
    }
    conn.execute(
        "UPDATE video_jobs SET status='processing',created_at=?,updated_at=?,result_json=? WHERE id=?",
        (queue.now_text(old), queue.now_text(old), json.dumps(payload), int(job["id"])),
    )
    queue.ensure_product_video_dispatch_outbox(
        conn,
        job_id=int(job["id"]),
        project_id=int(project["project_id"]),
        scene_indexes=[1, 2],
        now=old,
    )
    conn.commit()
    return queue.get_video_render_job(conn, int(job["id"])), queue.get_video_project(conn, int(project["project_id"]))


def test_status_read_reconciliation_persists_source_and_full_terminal_truth(tmp_path):
    conn = _conn(tmp_path)
    job, project = _historical_zero_task_job(conn)

    failed = remote_worker_api.fail_stale_product_video_jobs(
        conn,
        max_wait_seconds=1,
        job_id=int(job["id"]),
        reconciliation_source="public_status_read_reconcile",
        reconciliation_run_id="status-read-r18s7",
    )

    current = queue.get_video_render_job(conn, int(job["id"]))
    payload = json.loads(current["result_json"])
    outbox = queue.product_video_dispatch_outbox_diagnostic(conn, job_id=int(job["id"]))
    scene_states = {
        str(row[0])
        for row in conn.execute("SELECT scene_status FROM video_scenes WHERE project_id=?", (int(project["project_id"]),)).fetchall()
    }
    assert failed == 1
    assert current["status"] == "failed"
    assert payload["canonical_status"] == "failed_no_charge"
    assert payload["terminal"] is True
    assert payload["continue_polling"] is False
    assert payload["next_scene_poll_at"] == ""
    assert payload["next_refresh_expected_at"] == ""
    assert payload["fallback_allowed"] is False
    assert payload["dispatch_status"] == "terminal_failed"
    assert payload["wallet_charge_recorded"] is False
    assert payload["charged_xu"] == 0
    assert payload["reconciliation_source"] == "public_status_read_reconcile"
    assert payload["reconciliation_run_id"] == "status-read-r18s7"
    assert outbox["outbox_status"] == "terminal_failed"
    assert outbox["claimable"] is False
    assert scene_states == {"terminal_failed"}


def test_scheduler_counters_only_count_scheduler_reconciliation(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    job, _project_row = _historical_zero_task_job(conn)
    monkeypatch.setattr(
        queue,
        "_PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE",
        {
            **queue._PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE,
            "watchdog_generation_id": "generation-r18s7",
            "watchdog_generation_jobs_scanned": 0,
            "watchdog_generation_jobs_reconciled": 0,
            "watchdog_last_reconciled_job_ids": [],
            "jobs_scanned": 0,
            "jobs_reconciled": 0,
        },
    )

    report = queue.run_product_video_watchdog_scheduler_tick(
        conn,
        eligibility_evaluator=lambda *_args: {
            "eligible_provider_keys": [],
            "runtime_candidate_keys": [],
            "final_eligible_provider_count": 0,
        },
    )

    assert report["terminal_failed"] == 1
    assert report["watchdog_generation_jobs_scanned"] == 1
    assert report["watchdog_generation_jobs_reconciled"] == 1
    assert report["watchdog_last_reconciled_job_ids"] == [int(job["id"])]
    assert report["last_reconciliation_source"] == "watchdog_scheduler"


def test_terminal_scene_board_has_no_processing_or_refresh_copy():
    board = product_progress_status.video_per_scene_progress_board(
        {
            "scene_count": 2,
            "status": "failed",
            "canonical_status": "failed_no_charge",
            "terminal_state": "failed_no_charge",
            "terminal": True,
            "scene_tasks": [{"scene_index": 1, "status": "processing"}, {"scene_index": 2, "status": "queued"}],
            "wallet_charge_recorded": False,
            "charged_xu": 0,
        }
    )
    text = "\n".join(board["lines"])

    assert "Cảnh 1/2: Chưa thể bắt đầu" in text
    assert "Cảnh 2/2: Chưa thể bắt đầu" in text
    assert "Đang xử lý" not in text
    assert "Đang tạo" not in text
    assert "Đang dựng" not in text
    assert "tự kiểm tra lại" not in text
    assert board["auto_refresh_enabled"] is False


def test_exact_live_path_and_protocol_diagnostics_are_wired_without_provider_http():
    bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")
    queue_source = (ROOT / "services" / "video_project_queue.py").read_text(encoding="utf-8")
    worker_source = (ROOT / "remote_worker.py").read_text(encoding="utf-8")
    target_source = Path(__file__).read_text(encoding="utf-8")

    assert 'callback_data="vproduct|b14_confirm"' in bot_source
    assert 'CallbackQueryHandler(handle_product_video_public_confirm_callback, pattern=r"^vproduct\\|b14_confirm$")' in bot_source
    assert "setattr(context, \"_product_video_authoritative_confirm\", True)" in bot_source
    live_confirm = bot_source[bot_source.index('if action == "b14_confirm":'):bot_source.index('if action == "b14_job_status":')]
    assert "product_video_public_preflight_evaluation(" in live_confirm
    assert "explicit_public_final_confirm=True" in live_confirm
    assert live_confirm.index("product_video_public_preflight_evaluation(") < live_confirm.index("build_product_video_public_final_admission")
    assert "build_product_video_public_final_admission" in live_confirm
    assert "require_provider_admission=True" in live_confirm
    assert "product_video_assert_final_admission" in queue_source
    confirm_source = queue_source[
        queue_source.index("def _confirm_product_video_invoice_atomic"):queue_source.index("def confirm_public_product_video_invoice")
    ]
    assert confirm_source.index('assertion_phase="pre_transaction"') < confirm_source.index('conn.execute("BEGIN IMMEDIATE")')
    assert "inside_transaction_before_first_insert" in confirm_source
    assert "PRODUCT_VIDEO_FINAL_ADMISSION_CONTEXT_VERSION" in queue_source
    assert 'reconciliation_source="public_status_read_reconcile"' in bot_source
    assert "owner_heartbeat_request_received" in bot_source
    assert "last_idle_claim_at" in bot_source
    assert "heartbeat_refresh_source" in bot_source
    assert 'refresh_source="claim_idle"' in bot_source
    assert 'refresh_source="job_complete"' in bot_source
    assert "worker_identity_payload" in worker_source
    assert r"Hệ thống chưa trừ Xu.\n" in bot_source
    assert 'status_label = "Chưa thể bắt đầu tạo video"' in bot_source
    assert '"auto_refresh_enabled": False' in (ROOT / "services" / "product_progress_status.py").read_text(encoding="utf-8")
    product_failure_copy = bot_source[
        bot_source.index("VIDEO_B14_PRODUCT_CLEAN_FAIL_MESSAGE"):bot_source.index("def video_b14_result_renderer_has_test_marker")
    ]
    assert "đã hoàn Xu" not in product_failure_copy
    assert "chưa trừ Xu hoặc đã hoàn Xu" not in bot_source[bot_source.index("if failed_no_charge_terminal:"):bot_source.index("def video_b14_queue_status_keyboard")]
    for marker in (
        "url" + "open",
        "requests" + ".post",
        "run_provider" + "_generation",
        "submit" + "_video",
    ):
        assert marker not in target_source
