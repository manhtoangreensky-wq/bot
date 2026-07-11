import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from services import product_progress_status
from services import remote_worker_api
from services import video_project_queue as queue
from services import video_real_render_connector as connector


ROOT = Path(__file__).resolve().parents[1]


def _conn(tmp_path: Path) -> sqlite3.Connection:
    tmp_path.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(tmp_path / "r18s3.db")
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _project(conn: sqlite3.Connection, *, user_id: int = 128, scene_count: int = 2) -> dict:
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
        "provider_chain": ["shopaikey_video", "key4u_video"],
        "provider_order": "shopaikey_video,key4u_video",
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
        topic="fixture #128",
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


def _admission(candidates=None, *, ok: bool | None = None) -> dict:
    candidates = list(candidates if candidates is not None else ["shopaikey_video"])
    allowed = bool(candidates) if ok is None else bool(ok)
    snapshot = {
        "provider_eligibility_snapshot_id": "r18s3-final-snapshot",
        "configured_provider_keys": ["shopaikey_video", "key4u_video"],
        "contract_valid_provider_chain": ["shopaikey_video", "key4u_video"],
        "eligible_provider_keys": candidates,
        "runtime_candidate_keys": candidates,
        "final_eligible_provider_count": len(candidates),
    }
    return {
        **snapshot,
        "ok": allowed,
        "provider_eligibility_snapshot": snapshot,
        "admission_snapshot_id": snapshot["provider_eligibility_snapshot_id"],
        "admission_candidate_keys": candidates,
        "admission_candidate_count": len(candidates),
        "admission_result": "allowed" if allowed else "blocked",
        "admission_block_reason": "" if allowed else "no_eligible_product_video_provider",
    }


def _confirm(conn: sqlite3.Connection, project: dict, admission=None) -> dict:
    return queue.confirm_video_project_invoice(
        conn,
        project_id=int(project["project_id"]),
        user_id=int(project["user_id"]),
        provider_admission=_admission() if admission is None else admission,
        require_provider_admission=True,
    )


def _payload(job: dict) -> dict:
    return json.loads(str(job.get("result_json") or "{}"))


def test_final_confirm_candidate_zero_creates_nothing_and_does_not_mutate_project(tmp_path):
    conn = _conn(tmp_path)
    project = _project(conn)

    result = _confirm(conn, project, _admission([], ok=False))

    assert result["ok"] is False
    assert result["reason"] == "no_eligible_product_video_provider"
    assert result["public_message"] == (
        "TOAN AAS chưa thể bắt đầu tạo video lúc này.\n"
        "Hệ thống chưa trừ Xu.\n"
        "Anh/chị vui lòng thử lại sau."
    )
    assert conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM video_scenes").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox").fetchone()[0] == 0
    persisted = queue.get_video_project(conn, int(project["project_id"]))
    asset_pack = json.loads(persisted["asset_pack_json"])
    assert "admission_result" not in asset_pack
    assert "admission_candidate_count" not in asset_pack
    assert persisted["is_confirmed"] == 0


def test_quote_candidate_does_not_bypass_final_confirm_recheck(tmp_path):
    conn = _conn(tmp_path)
    project = _project(conn)
    queue.update_video_project(
        conn,
        int(project["project_id"]),
        asset_pack_json={
            **json.loads(project["asset_pack_json"]),
            "preconfirm_candidate_keys": ["shopaikey_video"],
        },
    )

    result = _confirm(conn, queue.get_video_project(conn, int(project["project_id"])), _admission([], ok=False))

    assert result["ok"] is False
    assert conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0] == 0


def test_job_scene_outbox_transaction_rolls_back_together(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    project = _project(conn)

    def fail_outbox(*_args, **_kwargs):
        raise sqlite3.OperationalError("fixture outbox failure")

    monkeypatch.setattr(queue, "_insert_product_video_dispatch_outbox_record", fail_outbox)
    result = _confirm(conn, project)

    assert result["ok"] is False
    assert result["reason"] == "dispatch_outbox_transaction_failed"
    assert conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM video_scenes").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox").fetchone()[0] == 0
    persisted = queue.get_video_project(conn, int(project["project_id"]))
    assert persisted["status"] == "draft_invoice"
    assert persisted["is_confirmed"] == 0


def test_atomic_confirm_persists_job_scene_records_and_pending_outbox(tmp_path):
    conn = _conn(tmp_path)
    project = _project(conn)

    result = _confirm(conn, project)

    assert result["ok"] is True
    assert result["job_created"] is True
    assert result["scene_records_created"] is True
    assert result["dispatch_outbox_created"] is True
    assert conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM video_scenes").fetchone()[0] == 2
    outbox = queue.get_product_video_dispatch_outbox(conn, job_id=int(result["job"]["id"]))
    assert outbox["dispatch_status"] == "pending"
    assert outbox["scene_indexes"] == [1, 2]
    assert outbox["owner"] == "owner_product_video"


def test_pending_outbox_atomic_lease_blocks_second_worker_and_recovers_expiry(tmp_path):
    conn = _conn(tmp_path)
    project = _project(conn)
    result = _confirm(conn, project)
    now = datetime(2030, 1, 2, 3, 4, 5)

    first = queue.claim_product_video_dispatch_outbox(conn, worker_id="worker-a", lease_seconds=30, now=now)
    blocked = queue.claim_product_video_dispatch_outbox(conn, worker_id="worker-b", lease_seconds=30, now=now + timedelta(seconds=1))
    recovered = queue.claim_product_video_dispatch_outbox(conn, worker_id="worker-b", lease_seconds=30, now=now + timedelta(seconds=31))
    duplicate = queue.claim_product_video_dispatch_outbox(conn, worker_id="worker-c", lease_seconds=30, now=now + timedelta(seconds=32))

    assert first["job_id"] == result["job"]["id"]
    assert blocked == {}
    assert recovered["job_id"] == result["job"]["id"]
    assert recovered["stale_dispatch_lease_recovered"] is True
    assert recovered["attempt_count"] == 2
    assert duplicate == {}


def test_owner_worker_consumes_outbox_for_queued_and_processing_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(
        remote_worker_api,
        "_product_video_runtime_eligibility",
        lambda *_args, **_kwargs: _admission(["shopaikey_video"]),
    )
    for offset, initial_status in enumerate(("queued", "processing"), start=1):
        conn = _conn(tmp_path / str(offset))
        project = _project(conn, user_id=128 + offset)
        result = _confirm(conn, project)
        if initial_status == "processing":
            conn.execute(
                "UPDATE video_jobs SET status='processing',locked_by='',locked_at=NULL,lease_expires_at=NULL WHERE id=?",
                (int(result["job"]["id"]),),
            )
            conn.execute("UPDATE video_projects SET status='processing' WHERE project_id=?", (int(project["project_id"]),))
            conn.commit()

        claimed = remote_worker_api.claim_remote_worker_product_video_job(
            conn,
            worker_id=f"owner-{initial_status}",
            owner_only=True,
            now=datetime(2030, 1, 2, 3, 4, 5),
        )
        second = remote_worker_api.claim_remote_worker_product_video_job(
            conn,
            worker_id=f"owner-{initial_status}-second",
            owner_only=True,
            now=datetime(2030, 1, 2, 3, 4, 6),
        )

        assert claimed
        payload = _payload(claimed)
        assert payload["worker_scan_seen_job"] is True
        assert payload["worker_scan_seen_outbox"] is True
        assert payload["dispatch_outbox_acknowledged"] is True
        assert payload["scene_dispatch_lease_by_index"]["1"]["lease_owner"] == f"owner-{initial_status}"
        assert queue.get_product_video_dispatch_outbox(conn, job_id=int(claimed["id"]))["dispatch_status"] == "acknowledged"
        assert second == {}


def test_worker_recheck_blocks_changed_eligibility_before_scene_dispatch(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    project = _project(conn)
    result = _confirm(conn, project)
    monkeypatch.setattr(
        remote_worker_api,
        "_product_video_runtime_eligibility",
        lambda *_args, **_kwargs: _admission([], ok=False),
    )

    claimed = remote_worker_api.claim_remote_worker_product_video_job(
        conn,
        worker_id="owner-no-provider",
        owner_only=True,
        now=datetime(2030, 1, 2, 3, 4, 5),
    )

    assert claimed == {}
    failed = queue.get_video_render_job(conn, int(result["job"]["id"]))
    payload = _payload(failed)
    assert failed["status"] == "failed"
    assert payload["terminal_state"] == "failed_no_charge"
    assert payload["zero_task_terminal_reason"] == "no_eligible_provider_before_scene_dispatch"
    assert payload["provider_http_request_sent"] is False
    assert payload["charged_xu"] == 0


def test_fixture_128_independent_watchdog_terminalizes_without_registry_or_http(tmp_path):
    conn = _conn(tmp_path)
    project = _project(conn)
    result = _confirm(conn, project)
    now = datetime(2030, 1, 2, 3, 4, 5)
    stale = queue.now_text(now - timedelta(seconds=140))
    payload = _payload(result["job"])
    payload.update(
        {
            "runtime_candidate_keys": [],
            "final_eligible_provider_count": 0,
            "provider_attempts": [],
            "provider_http_request_sent": False,
            "provider_http_status": 0,
            "status_registry_present": False,
        }
    )
    conn.execute(
        "UPDATE video_jobs SET created_at=?,updated_at=?,result_json=? WHERE id=?",
        (stale, stale, json.dumps(payload), int(result["job"]["id"])),
    )
    conn.commit()

    report = queue.sweep_product_video_zero_task_watchdog(
        conn,
        now=now,
        eligibility_evaluator=lambda *_args: _admission([], ok=False),
    )

    failed = queue.get_video_render_job(conn, int(result["job"]["id"]))
    final = _payload(failed)
    assert report["terminal_failed"] == 1
    assert failed["status"] == "failed"
    assert final["zero_task_watchdog_triggered"] is True
    assert final["zero_task_elapsed_seconds"] >= 140
    assert final["zero_task_candidate_count"] == 0
    assert final["zero_task_terminal_reason"] == "no_eligible_provider_before_scene_dispatch"
    assert final["continue_polling"] is False
    assert final["provider_http_request_sent"] is False
    assert final["concat_attempted"] is False
    assert final["delivery_attempted"] is False
    assert final["charged_xu"] == 0


def test_zero_task_watchdog_recreates_missing_outbox_exactly_once(tmp_path):
    conn = _conn(tmp_path)
    project = _project(conn)
    queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="queued_for_worker",
        is_confirmed=1,
    )
    job = queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=int(project["user_id"]))
    now = datetime(2030, 1, 2, 3, 4, 5)
    stale = queue.now_text(now - timedelta(seconds=140))
    payload = {
        "source": "product_video",
        "scene_count": 2,
        "scene_tasks": queue.product_video_initial_scene_tasks(job["id"], 2),
        "runtime_candidate_keys": ["shopaikey_video"],
        "preconfirm_candidate_keys": ["shopaikey_video"],
        "final_eligible_provider_count": 1,
    }
    conn.execute(
        "UPDATE video_jobs SET created_at=?,updated_at=?,result_json=? WHERE id=?",
        (stale, stale, json.dumps(payload), int(job["id"])),
    )
    conn.commit()

    first = queue.sweep_product_video_zero_task_watchdog(
        conn,
        now=now,
        eligibility_evaluator=lambda *_args: _admission(["shopaikey_video"]),
    )
    second = queue.sweep_product_video_zero_task_watchdog(
        conn,
        now=now + timedelta(seconds=1),
        eligibility_evaluator=lambda *_args: _admission(["shopaikey_video"]),
    )

    assert first["recovered"] == 1
    assert second["recovered"] == 1
    assert conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox WHERE job_id=?", (int(job["id"]),)).fetchone()[0] == 1


def test_text_to_video_per_scene_contract_requires_provider_even_with_zero_candidates():
    required = connector._route_requires_provider(
        "video_ai_prompt",
        "",
        "",
        provider_ready=False,
        engine_adapter="text_to_video",
        orchestration_mode="per_scene_8s",
        explicit_local_renderer=False,
    )

    assert required is True


def test_public_zero_task_state_is_preparing_without_false_reroute_promise():
    state = {
        "status": "queued",
        "scene_count": 2,
        "scenes_total": 2,
        "current_scene_status": "queued_waiting_for_dispatch",
        "valid_provider_task_count": 0,
        "zero_task_progress_guard": True,
        "progress_percent": 55,
        "fallback_allowed": False,
        "fallback_provider_candidate": "",
        "not_start_threshold_seconds": 60,
        "provider_elapsed_seconds": 10,
        "scene_tasks": [
            {"scene_index": 1, "status": "queued_waiting_for_dispatch"},
            {"scene_index": 2, "status": "queued_waiting_for_dispatch"},
        ],
    }

    stage = product_progress_status.product_progress_stage_from_job("multiscene_video", state)
    board = product_progress_status.video_per_scene_progress_board_text(state)

    assert stage["current_stage"] == "preparing_content"
    assert stage["percent"] <= 20
    assert "Cảnh 1/2: Đang chờ bắt đầu" in board
    assert "tự chuyển hướng" not in board


def test_r18s3_source_contract_has_no_real_provider_calls_and_keeps_scope():
    test_source = Path(__file__).read_text(encoding="utf-8")
    queue_source = (ROOT / "services" / "video_project_queue.py").read_text(encoding="utf-8")
    worker_source = (ROOT / "services" / "remote_worker_api.py").read_text(encoding="utf-8")
    bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")
    for marker in (
        "video_dispatch_outbox",
        "sweep_product_video_zero_task_watchdog",
        "no_eligible_provider_before_scene_dispatch",
    ):
        assert marker in queue_source
    assert "claim_product_video_dispatch_outbox" in worker_source
    assert "require_provider_admission=True" in bot_source
    assert "require_provider_admission=not is_internal" not in bot_source
    forbidden = (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "urllib.request." + "urlopen",
        "provider" + "_smoke",
        "run_provider" + "_generation(",
    )
    assert all(token not in test_source for token in forbidden)
