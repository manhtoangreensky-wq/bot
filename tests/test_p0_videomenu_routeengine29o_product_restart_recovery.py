from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

import bot
import remote_worker
from services import product_progress_status
from services import remote_worker_api
from services import video_project_queue as queue
from services import video_real_render_connector as connector


TASK_SCENE_1 = "task-scene-1-HR51"
TASK_SCENE_2 = "task-scene-2-nZHo"


def _live_job13_result() -> dict:
    return {
        "job_id": 13,
        "source": "product_video",
        "product_video": True,
        "scene_count": 2,
        "orchestration_mode": "per_scene_8s",
        "provider_pending_provider": "shopaikey_video",
        "provider_pending_task_id": TASK_SCENE_2,
        "provider_task_ids": [TASK_SCENE_2, TASK_SCENE_1],
        "canonical_scene_index": 1,
        "scene_task_map": {"1": [TASK_SCENE_1], "2": [TASK_SCENE_2]},
        "task_scene_index_map": {TASK_SCENE_1: 1, TASK_SCENE_2: 2},
        "task_to_scene_index": {TASK_SCENE_1: 1, TASK_SCENE_2: 2},
        "scene_active_task_by_index": {"1": TASK_SCENE_1, "2": TASK_SCENE_2},
        "scene_winner_task_by_index": {"1": TASK_SCENE_1, "2": TASK_SCENE_2},
        "scene_status_by_index": {"1": "provider_not_start", "2": "provider_running"},
        "provider_elapsed_seconds": 1_372,
        "status_panel_message_id": 777,
        "latest_status_message_id": 777,
        "chat_id": 919_013,
        "user_id": 919_013,
        "lang": "vi",
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "charged_xu": 0,
        "charge": 0,
        "scene_tasks": [
            {
                "scene_index": 1,
                "provider": "shopaikey_video",
                "status": "provider_not_start",
                "submitted_at_epoch": 1_800_000_000,
            },
            {
                "scene_index": 2,
                "provider": "shopaikey_video",
                "status": "provider_running",
                "submitted_at_epoch": 1_800_000_000,
            },
        ],
    }


def _live_job13_project() -> dict:
    return {
        "project_id": 13,
        "user_id": 919_013,
        "status": "failed",
        "is_confirmed": 1,
        "profile_id": "video_ai_prompt",
        "scene_count": 2,
        "asset_pack_json": json.dumps(
            {
                "source": "product_video",
                "product_type": "video_ai_prompt",
                "render_mode": "real",
                "public_user": True,
            }
        ),
        "invoice_json": json.dumps(
            {
                "scene_count": 2,
                "duration_seconds": 16,
                "user_visible_price_xu": 300,
                "persisted_quoted_price_xu": 300,
                "customer_charge_planned_xu": 300,
            }
        ),
    }


def _seed_rehydrate_job(
    db_path: Path,
    *,
    project_status: str = "processing",
    outbox_status: str = "acknowledged",
) -> tuple[int, int]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    project = queue.create_video_project(
        conn,
        user_id=919_013,
        profile_id="video_ai_prompt",
        topic="rehydrate Product Video panel",
        asset_pack={
            "source": "product_video",
            "product_type": "video_ai_prompt",
            "render_mode": "real",
            "public_user": True,
        },
    )
    project = queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="processing",
        is_confirmed=1,
        scene_count=2,
        invoice_json={"scene_count": 2, "duration_seconds": 16},
    )
    job = queue.enqueue_video_render_job(
        conn,
        project_id=int(project["project_id"]),
        user_id=919_013,
    )
    result = {
        **_live_job13_result(),
        "job_id": int(job["id"]),
        "project_id": int(project["project_id"]),
    }
    conn.execute(
        "UPDATE video_jobs SET status='processing',result_json=?,progress_percent=20 WHERE id=?",
        (json.dumps(result), int(job["id"])),
    )
    outbox = queue.ensure_product_video_dispatch_outbox(
        conn,
        job_id=int(job["id"]),
        project_id=int(project["project_id"]),
        scene_indexes=[1, 2],
    )
    conn.execute(
        "UPDATE video_dispatch_outbox SET dispatch_status=? WHERE outbox_id=?",
        (str(outbox_status), int(outbox["outbox_id"])),
    )
    conn.execute(
        "UPDATE video_projects SET status=? WHERE project_id=?",
        (str(project_status), int(project["project_id"])),
    )
    conn.commit()
    conn.close()
    return int(job["id"]), int(project["project_id"])


def _seed_existing_task_recovery_job(
    db_path: Path,
    *,
    project_scene_count: int = 2,
    include_result_scene_count: bool = True,
) -> tuple[sqlite3.Connection, int, int]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    project = queue.create_video_project(
        conn,
        user_id=919_013,
        profile_id="video_ai_prompt",
        topic="recover existing Product Video tasks",
        asset_pack={
            "source": "product_video",
            "product_type": "video_ai_prompt",
            "render_mode": "real",
            "public_user": True,
        },
    )
    project = queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="failed",
        is_confirmed=1,
        scene_count=project_scene_count,
        invoice_json={
            "scene_count": 2,
            "duration_seconds": 16,
            "user_visible_price_xu": 300,
            "persisted_quoted_price_xu": 300,
            "customer_charge_planned_xu": 300,
        },
    )
    job = queue.enqueue_video_render_job(
        conn,
        project_id=int(project["project_id"]),
        user_id=919_013,
        max_attempts=1,
    )
    queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="failed",
        job_id=int(job["id"]),
    )
    result = {
        **_live_job13_result(),
        "job_id": int(job["id"]),
        "project_id": int(project["project_id"]),
        "automatic_retry_allowed": False,
        "automatic_resubmit_allowed": False,
        "automatic_fallback_allowed": False,
    }
    if not include_result_scene_count:
        result.pop("scene_count", None)
    conn.execute(
        """UPDATE video_jobs
              SET status='failed',attempts=1,max_attempts=1,last_error='worker_restart',
                  result_json=?,progress_percent=20,completed_at=CURRENT_TIMESTAMP
            WHERE id=?""",
        (json.dumps(result), int(job["id"])),
    )
    outbox = queue.ensure_product_video_dispatch_outbox(
        conn,
        job_id=int(job["id"]),
        project_id=int(project["project_id"]),
        scene_indexes=[1, 2],
    )
    conn.execute(
        """UPDATE video_dispatch_outbox
              SET dispatch_status='acknowledged',acknowledged_at=CURRENT_TIMESTAMP
            WHERE outbox_id=?""",
        (int(outbox["outbox_id"]),),
    )
    conn.commit()
    return conn, int(job["id"]), int(project["project_id"])


def _stub_recovered_completion_validation(monkeypatch) -> None:
    monkeypatch.setattr(
        queue,
        "product_video_scene_coverage_state",
        lambda *_args, **_kwargs: {
            "delivery_blocked_by_scene_coverage": False,
            "scene_clip_coverage_complete": True,
            "scene_coverage_expected": 2,
            "scene_coverage_count": 2,
        },
    )
    monkeypatch.setattr(
        queue.video_final_output,
        "validate_final_video_output",
        lambda **_kwargs: {
            "ok": True,
            "bytes": 2048,
            "duration": 16.0,
            "has_video": True,
            "has_audio": False,
        },
    )
    monkeypatch.setattr(
        queue,
        "product_video_duration_contract",
        lambda *_args, **_kwargs: {
            "ok": True,
            "reason": "",
            "expected_duration_seconds": 16.0,
            "actual_duration_seconds": 16.0,
        },
    )


def test_provider_candidates_use_durable_scene_ownership_before_canonical_fallback():
    candidates = bot._video_provider_task_candidates(_live_job13_result(), _live_job13_project())
    by_task = {str(item["task_id"]): item for item in candidates}

    assert by_task[TASK_SCENE_1]["scene_index"] == 1
    assert by_task[TASK_SCENE_2]["scene_index"] == 2
    assert by_task[TASK_SCENE_1]["scene_index_explicit"] is True
    assert by_task[TASK_SCENE_2]["scene_index_explicit"] is True


def test_durable_task_scene_owner_map_is_fail_closed_and_complete():
    assert hasattr(queue, "product_video_durable_task_scene_owners")
    ownership = queue.product_video_durable_task_scene_owners(_live_job13_result())

    assert ownership["task_to_scene_index"] == {TASK_SCENE_1: 1, TASK_SCENE_2: 2}
    assert ownership["task_scene_mapping_conflicts"] == {}
    assert ownership["task_scene_mapping_verified"] is True


def test_provider_candidates_do_not_let_explicit_scene_override_durable_conflict():
    result = _live_job13_result()
    result["scene_tasks"][1]["provider_task_id"] = TASK_SCENE_1

    ownership = queue.product_video_durable_task_scene_owners(result)
    candidates = bot._video_provider_task_candidates(result, _live_job13_project())
    candidate = next(item for item in candidates if item["task_id"] == TASK_SCENE_1)

    assert ownership["task_scene_mapping_conflicts"][TASK_SCENE_1] == [1, 2]
    assert candidate["scene_index"] == 0
    assert candidate["scene_index_explicit"] is False
    assert candidate["scene_index_source"] == "durable_task_scene_conflict"


def test_failed_acknowledged_job_with_two_existing_tasks_is_recoverable_without_submit():
    assert hasattr(queue, "product_video_existing_task_recovery_state")
    state = queue.product_video_existing_task_recovery_state(
        {"id": 13, "project_id": 13, "user_id": 919_013, "status": "failed"},
        _live_job13_project(),
        _live_job13_result(),
        {"outbox_id": 13, "dispatch_status": "acknowledged"},
    )

    assert state["existing_task_recovery_recoverable"] is True
    assert state["required_scene_indexes"] == [1, 2]
    assert state["mapped_scene_indexes"] == [1, 2]
    assert state["provider_submit_allowed"] is False
    assert state["automatic_resubmit_allowed"] is False
    assert state["automatic_fallback_allowed"] is False
    assert state["charged_xu"] == 0


def test_cancelled_dispatch_outbox_cannot_recover_existing_provider_tasks():
    state = queue.product_video_existing_task_recovery_state(
        {"id": 13, "project_id": 13, "user_id": 919_013, "status": "failed"},
        _live_job13_project(),
        _live_job13_result(),
        {"outbox_id": 13, "dispatch_status": "cancelled"},
    )

    assert state["existing_task_recovery_recoverable"] is False
    assert state["existing_task_recovery_block_reason"] == "dispatch_outbox_cancelled"


def test_cancelled_project_cannot_recover_existing_provider_tasks():
    project = {**_live_job13_project(), "status": "cancelled"}

    state = queue.product_video_existing_task_recovery_state(
        {"id": 13, "project_id": 13, "user_id": 919_013, "status": "failed"},
        project,
        _live_job13_result(),
        {"outbox_id": 13, "dispatch_status": "acknowledged"},
    )

    assert state["existing_task_recovery_recoverable"] is False
    assert state["existing_task_recovery_block_reason"] == "project_cancelled"


def test_stale_result_outbox_status_cannot_replace_missing_durable_outbox_row():
    result = {**_live_job13_result(), "dispatch_outbox_status": "acknowledged"}

    state = queue.product_video_existing_task_recovery_state(
        {"id": 13, "project_id": 13, "user_id": 919_013, "status": "failed"},
        _live_job13_project(),
        result,
        {},
    )

    assert state["existing_task_recovery_recoverable"] is False
    assert state["existing_task_recovery_block_reason"] == "dispatch_outbox_missing"


def test_recovery_uses_project_scene_count_when_result_scene_count_is_missing():
    result = _live_job13_result()
    result.pop("scene_count")
    result["provider_task_ids"] = [TASK_SCENE_1]
    result["scene_task_map"] = {"1": [TASK_SCENE_1]}
    result["task_scene_index_map"] = {TASK_SCENE_1: 1}
    result["task_to_scene_index"] = {TASK_SCENE_1: 1}
    result["scene_active_task_by_index"] = {"1": TASK_SCENE_1}
    result["scene_winner_task_by_index"] = {"1": TASK_SCENE_1}
    result["scene_status_by_index"] = {"1": "provider_running"}
    result["scene_tasks"] = [result["scene_tasks"][0]]

    state = queue.product_video_existing_task_recovery_state(
        {"id": 13, "project_id": 13, "user_id": 919_013, "status": "failed"},
        _live_job13_project(),
        result,
        {"outbox_id": 13, "dispatch_status": "acknowledged"},
    )

    assert state["required_scene_indexes"] == [1, 2]
    assert state["mapped_scene_indexes"] == [1]
    assert state["existing_task_recovery_recoverable"] is False
    assert state["existing_task_recovery_block_reason"] == "existing_task_scene_coverage_incomplete"


def test_existing_task_recovery_requeues_job_without_reopening_dispatch_or_charge(tmp_path: Path):
    assert hasattr(queue, "recover_product_video_existing_tasks")
    conn = sqlite3.connect(tmp_path / "routeengine29o-recovery.db")
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    project = queue.create_video_project(
        conn,
        user_id=919_013,
        profile_id="video_ai_prompt",
        topic="recover existing Product Video tasks",
        asset_pack={
            "source": "product_video",
            "product_type": "video_ai_prompt",
            "render_mode": "real",
            "public_user": True,
        },
    )
    project = queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="failed",
        is_confirmed=1,
        scene_count=0,
        invoice_json={
            "scene_count": 2,
            "duration_seconds": 16,
            "user_visible_price_xu": 300,
            "persisted_quoted_price_xu": 300,
            "customer_charge_planned_xu": 300,
        },
    )
    job = queue.enqueue_video_render_job(
        conn,
        project_id=int(project["project_id"]),
        user_id=919_013,
        max_attempts=1,
    )
    queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="failed",
        job_id=int(job["id"]),
    )
    result = _live_job13_result()
    result.pop("scene_count")
    result.update(
        {
            "job_id": int(job["id"]),
            "project_id": int(project["project_id"]),
            "automatic_retry_allowed": False,
            "automatic_resubmit_allowed": False,
            "automatic_fallback_allowed": False,
        }
    )
    conn.execute(
        """UPDATE video_jobs
              SET status='failed',attempts=1,max_attempts=1,last_error='worker_restart',
                  result_json=?,progress_percent=20,completed_at=CURRENT_TIMESTAMP
            WHERE id=?""",
        (json.dumps(result), int(job["id"])),
    )
    outbox = queue.ensure_product_video_dispatch_outbox(
        conn,
        job_id=int(job["id"]),
        project_id=int(project["project_id"]),
        scene_indexes=[1, 2],
    )
    conn.execute(
        """UPDATE video_dispatch_outbox
              SET dispatch_status='acknowledged',acknowledged_at=CURRENT_TIMESTAMP
            WHERE outbox_id=?""",
        (int(outbox["outbox_id"]),),
    )
    conn.commit()

    recovered = queue.recover_product_video_existing_tasks(conn, job_id=int(job["id"]))

    assert recovered["existing_task_recovery_recovered"] is True
    stored_job = queue.get_video_render_job(conn, int(job["id"]))
    stored_project = queue.get_video_project(conn, int(project["project_id"]))
    stored_outbox = queue.get_product_video_dispatch_outbox(conn, job_id=int(job["id"]))
    stored_result = json.loads(stored_job["result_json"])
    assert stored_job["status"] == "queued"
    assert stored_project["status"] == "queued_for_worker"
    assert stored_project["scene_count"] == 2
    assert stored_outbox["dispatch_status"] == "acknowledged"
    assert stored_result["scene_count"] == 2
    assert stored_result["recovery_existing_tasks_only"] is True
    assert stored_result["provider_submit_allowed"] is False
    assert stored_result["automatic_resubmit_allowed"] is False
    assert stored_result["automatic_fallback_allowed"] is False
    assert stored_result["charged_xu"] == 0

    claimed = remote_worker_api._claim_video_render_candidate(
        conn,
        worker_id="routeengine29o-existing-task-recovery",
        product_video_only=True,
        public_enabled=True,
    )
    assert int(claimed["id"]) == int(job["id"])
    claimed_result = json.loads(claimed["result_json"])
    claimed_ownership = queue.product_video_durable_task_scene_owners(claimed_result)
    assert claimed_ownership["task_to_scene_index"] == {
        TASK_SCENE_1: 1,
        TASK_SCENE_2: 2,
    }
    assert claimed_ownership["scene_task_coverage_complete"] is True
    claimed_payload = remote_worker_api.build_worker_job_payload(
        queue.hydrate_video_job_payload(conn, claimed)
    )
    assert claimed_payload["recovery_existing_tasks_only"] is True
    assert [item["provider_task_id"] for item in claimed_payload["scene_tasks"]] == [
        TASK_SCENE_1,
        TASK_SCENE_2,
    ]
    assert queue.get_product_video_dispatch_outbox(
        conn,
        job_id=int(job["id"]),
    )["dispatch_status"] == "acknowledged"
    conn.close()


def test_completion_preserves_recovery_no_charge_contract_when_worker_result_omits_it(
    monkeypatch,
    tmp_path,
):
    conn, job_id, project_id = _seed_existing_task_recovery_job(
        tmp_path / "routeengine29o-completion-merge.db"
    )
    assert queue.recover_product_video_existing_tasks(
        conn,
        job_id=job_id,
    )["existing_task_recovery_recovered"] is True
    _stub_recovered_completion_validation(monkeypatch)
    final_path = tmp_path / "recovered-final.mp4"
    final_path.write_bytes(b"recovered-product-video")

    completed = queue.complete_video_job(
        conn,
        job_id=job_id,
        final_video_path=str(final_path),
        result={
            "ok": True,
            "renderer": "provider_scene_video",
            "visual_classification": "final_ai_video",
            "scene_count": 2,
        },
    )

    assert completed["ok"] is True
    completed_result = json.loads(completed["job"]["result_json"])
    assert completed_result["recovery_existing_tasks_only"] is True
    assert completed_result["provider_submit_allowed"] is False
    assert completed_result["automatic_retry_allowed"] is False
    assert completed_result["automatic_resubmit_allowed"] is False
    assert completed_result["automatic_fallback_allowed"] is False
    assert completed_result["no_charge"] is True
    assert completed_result["charged_xu"] == 0
    assert completed_result["status"] == "completed"
    assert completed_result["canonical_status"] == "completed"
    assert completed_result["terminal"] is True
    assert completed_result["terminal_state"] == "final_delivered"
    assert completed_result["continue_polling"] is False

    delivered = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=True,
        delivery_message_id="tg-recovered-29o",
    )
    decision = queue.product_video_delivery_charge_decision(
        queue.get_video_project(conn, project_id),
        queue.get_video_render_job(conn, job_id),
        json.loads(delivered["job"]["result_json"]),
    )
    assert decision["ok"] is False
    assert decision["amount_xu"] == 0
    assert decision["charge_skip_reason"] == "existing_task_recovery_no_charge"
    conn.close()


def test_completion_cas_preserves_cancellation_committed_during_validation(
    monkeypatch,
    tmp_path,
):
    db_path = tmp_path / "routeengine29o-completion-cancel-race.db"
    conn, job_id, project_id = _seed_existing_task_recovery_job(db_path)
    assert queue.recover_product_video_existing_tasks(
        conn,
        job_id=job_id,
    )["existing_task_recovery_recovered"] is True
    claimed = remote_worker_api._claim_video_render_candidate(
        conn,
        worker_id="routeengine29o-completion-cancel-race",
        product_video_only=True,
        public_enabled=True,
    )
    assert int(claimed["id"]) == job_id
    final_path = tmp_path / "cancelled-race-final.mp4"
    final_path.write_bytes(b"must-not-complete-after-cancellation")
    cancellation_committed = False
    _stub_recovered_completion_validation(monkeypatch)

    def racing_validation(**_kwargs):
        nonlocal cancellation_committed
        racer = sqlite3.connect(db_path)
        try:
            racer.execute(
                "UPDATE video_projects SET status='cancelled' WHERE project_id=?",
                (project_id,),
            )
            racer.execute(
                "UPDATE video_dispatch_outbox SET dispatch_status='cancelled' WHERE job_id=?",
                (job_id,),
            )
            racer.commit()
            cancellation_committed = True
        finally:
            racer.close()
        return {
            "ok": True,
            "bytes": 2048,
            "duration": 16.0,
            "has_video": True,
            "has_audio": False,
        }

    monkeypatch.setattr(
        queue.video_final_output,
        "validate_final_video_output",
        racing_validation,
    )
    monkeypatch.setattr(
        queue,
        "product_video_duration_contract",
        lambda *_args, **_kwargs: {
            "ok": True,
            "reason": "",
            "expected_duration_seconds": 16.0,
            "actual_duration_seconds": 16.0,
        },
    )

    completed = queue.complete_video_job(
        conn,
        job_id=job_id,
        final_video_path=str(final_path),
        result={
            "ok": True,
            "renderer": "provider_scene_video",
            "visual_classification": "final_ai_video",
            "scene_count": 2,
        },
    )

    assert cancellation_committed is True
    assert completed["ok"] is False
    assert completed["reason"] in {
        "project_cancelled",
        "dispatch_outbox_cancelled",
    }
    assert queue.get_video_render_job(conn, job_id)["status"] != "completed"
    assert queue.get_video_project(conn, project_id)["status"] == "cancelled"
    assert queue.get_product_video_dispatch_outbox(
        conn,
        job_id=job_id,
    )["dispatch_status"] == "cancelled"
    conn.close()


def test_completion_failure_preserves_cancellation_committed_during_validation(
    monkeypatch,
    tmp_path,
):
    db_path = tmp_path / "routeengine29o-completion-failure-cancel-race.db"
    conn, job_id, project_id = _seed_existing_task_recovery_job(db_path)
    assert queue.recover_product_video_existing_tasks(
        conn,
        job_id=job_id,
    )["existing_task_recovery_recovered"] is True
    claimed = remote_worker_api._claim_video_render_candidate(
        conn,
        worker_id="routeengine29o-completion-failure-cancel-race",
        product_video_only=True,
        public_enabled=True,
    )
    assert int(claimed["id"]) == job_id
    final_path = tmp_path / "invalid-after-cancellation.mp4"
    final_path.write_bytes(b"invalid-after-cancellation")
    _stub_recovered_completion_validation(monkeypatch)

    def racing_invalid_validation(**_kwargs):
        racer = sqlite3.connect(db_path)
        try:
            racer.execute(
                "UPDATE video_projects SET status='cancelled' WHERE project_id=?",
                (project_id,),
            )
            racer.execute(
                "UPDATE video_dispatch_outbox SET dispatch_status='cancelled' WHERE job_id=?",
                (job_id,),
            )
            racer.commit()
        finally:
            racer.close()
        return {
            "ok": False,
            "reason": "final_output_invalid_after_cancel",
            "bytes": 0,
            "duration": 0.0,
            "has_video": False,
            "has_audio": False,
        }

    monkeypatch.setattr(
        queue.video_final_output,
        "validate_final_video_output",
        racing_invalid_validation,
    )

    completed = queue.complete_video_job(
        conn,
        job_id=job_id,
        final_video_path=str(final_path),
        result={
            "ok": False,
            "renderer": "provider_scene_video",
            "visual_classification": "final_ai_video",
            "scene_count": 2,
        },
    )

    assert completed["ok"] is False
    assert completed["reason"] in {
        "project_cancelled",
        "dispatch_outbox_cancelled",
    }
    assert queue.get_video_render_job(conn, job_id)["status"] not in {
        "completed",
        "failed",
    }
    assert queue.get_video_project(conn, project_id)["status"] == "cancelled"
    assert queue.get_product_video_dispatch_outbox(
        conn,
        job_id=job_id,
    )["dispatch_status"] == "cancelled"
    conn.close()


def test_completion_failure_keeps_lock_from_guard_through_failure_mutation(
    monkeypatch,
    tmp_path,
):
    db_path = tmp_path / "routeengine29o-completion-failure-transaction-race.db"
    conn, job_id, project_id = _seed_existing_task_recovery_job(db_path)
    assert queue.recover_product_video_existing_tasks(
        conn,
        job_id=job_id,
    )["existing_task_recovery_recovered"] is True
    claimed = remote_worker_api._claim_video_render_candidate(
        conn,
        worker_id="routeengine29o-completion-failure-transaction-race",
        product_video_only=True,
        public_enabled=True,
    )
    assert int(claimed["id"]) == job_id
    final_path = tmp_path / "invalid-during-failure-transaction.mp4"
    final_path.write_bytes(b"invalid-during-failure-transaction")
    _stub_recovered_completion_validation(monkeypatch)
    monkeypatch.setattr(
        queue.video_final_output,
        "validate_final_video_output",
        lambda **_kwargs: {
            "ok": False,
            "reason": "final_output_invalid_during_cancel",
            "bytes": 0,
            "duration": 0.0,
            "has_video": False,
            "has_audio": False,
        },
    )

    start_cancellation = threading.Event()
    cancellation_committed = threading.Event()
    cancellation_errors: list[BaseException] = []

    def cancel_after_guard() -> None:
        if not start_cancellation.wait(timeout=5):
            cancellation_errors.append(AssertionError("failure mutation was not reached"))
            return
        racer = sqlite3.connect(db_path, timeout=5.0)
        try:
            racer.execute("PRAGMA busy_timeout=5000")
            racer.execute(
                "UPDATE video_jobs SET status='cancelled' WHERE id=?",
                (job_id,),
            )
            racer.execute(
                "UPDATE video_projects SET status='cancelled' WHERE project_id=?",
                (project_id,),
            )
            racer.execute(
                "UPDATE video_dispatch_outbox SET dispatch_status='cancelled' WHERE job_id=?",
                (job_id,),
            )
            racer.commit()
            cancellation_committed.set()
        except BaseException as exc:  # pragma: no cover - asserted below
            cancellation_errors.append(exc)
        finally:
            racer.close()

    cancellation_thread = threading.Thread(target=cancel_after_guard, daemon=True)
    cancellation_thread.start()
    first_failure_mutation = True

    def coordinate_cancellation(statement: str) -> None:
        nonlocal first_failure_mutation
        normalized = " ".join(str(statement or "").lower().split())
        if not first_failure_mutation or not normalized.startswith("update video_jobs set"):
            return
        if "result_json" not in normalized and "status='failed'" not in normalized:
            return
        first_failure_mutation = False
        start_cancellation.set()
        cancellation_committed.wait(timeout=0.5)

    conn.set_trace_callback(coordinate_cancellation)
    try:
        queue.complete_video_job(
            conn,
            job_id=job_id,
            final_video_path=str(final_path),
            result={
                "ok": False,
                "renderer": "provider_scene_video",
                "visual_classification": "final_ai_video",
                "scene_count": 2,
            },
        )
    finally:
        conn.set_trace_callback(None)
        cancellation_thread.join(timeout=10)

    assert not cancellation_thread.is_alive()
    assert cancellation_errors == []
    assert cancellation_committed.is_set()
    assert queue.get_video_render_job(conn, job_id)["status"] == "cancelled"
    assert queue.get_video_project(conn, project_id)["status"] == "cancelled"
    assert queue.get_product_video_dispatch_outbox(
        conn,
        job_id=job_id,
    )["dispatch_status"] == "cancelled"
    conn.close()


def test_cancelled_dispatch_outbox_is_never_worker_claimed(tmp_path):
    conn, job_id, _project_id = _seed_existing_task_recovery_job(
        tmp_path / "routeengine29o-cancelled-outbox-claim.db"
    )
    assert queue.recover_product_video_existing_tasks(
        conn,
        job_id=job_id,
    )["existing_task_recovery_recovered"] is True
    conn.execute(
        "UPDATE video_dispatch_outbox SET dispatch_status='cancelled' WHERE job_id=?",
        (job_id,),
    )
    conn.commit()

    claimed = remote_worker_api._claim_video_render_candidate(
        conn,
        worker_id="routeengine29o-cancelled-outbox",
        product_video_only=True,
        public_enabled=True,
    )

    assert claimed == {}
    assert queue.get_product_video_dispatch_outbox(
        conn,
        job_id=job_id,
    )["dispatch_status"] == "cancelled"
    assert not str(queue.get_video_render_job(conn, job_id).get("locked_by") or "")
    conn.close()


def test_recovery_cas_preserves_cancellation_that_wins_after_preflight(
    monkeypatch,
    tmp_path,
):
    db_path = tmp_path / "routeengine29o-recovery-cancel-race.db"
    conn, job_id, project_id = _seed_existing_task_recovery_job(db_path)
    original_state = queue.product_video_existing_task_recovery_state
    state_calls = 0

    def racing_state(job, project, result, outbox):
        nonlocal state_calls
        state = original_state(job, project, result, outbox)
        state_calls += 1
        if state_calls == 1:
            racer = sqlite3.connect(db_path)
            try:
                racer.execute(
                    "UPDATE video_projects SET status='cancelled' WHERE project_id=?",
                    (project_id,),
                )
                racer.execute(
                    "UPDATE video_dispatch_outbox SET dispatch_status='cancelled' WHERE job_id=?",
                    (job_id,),
                )
                racer.commit()
            finally:
                racer.close()
        return state

    monkeypatch.setattr(
        queue,
        "product_video_existing_task_recovery_state",
        racing_state,
    )

    recovered = queue.recover_product_video_existing_tasks(conn, job_id=job_id)

    assert recovered["existing_task_recovery_recovered"] is False
    assert recovered["existing_task_recovery_block_reason"] in {
        "project_cancelled",
        "dispatch_outbox_cancelled",
    }
    assert queue.get_video_render_job(conn, job_id)["status"] == "failed"
    assert queue.get_video_project(conn, project_id)["status"] == "cancelled"
    assert queue.get_product_video_dispatch_outbox(
        conn,
        job_id=job_id,
    )["dispatch_status"] == "cancelled"
    conn.close()


def test_recovery_only_scene_never_submits_when_scene_task_mapping_is_missing(monkeypatch, tmp_path):
    provider_calls: list[str] = []

    def forbidden_provider_call(*_args, **_kwargs):
        provider_calls.append("called")
        raise AssertionError("existing-task recovery must never submit a provider job")

    monkeypatch.setattr(connector, "run_provider_generation", forbidden_provider_call)
    scene = SimpleNamespace(
        scene_id=2,
        video_prompt="second scene",
        visual_prompt="second scene",
        aspect_ratio="9:16",
        target_duration_sec=8.0,
    )
    scene._toan_aas_job = {
        "id": 13,
        "job_id": 13,
        "source": "product_video",
        "product_video": True,
        "product_type": "video_ai_prompt",
        "scene_count": 2,
        "orchestration_mode": "per_scene_8s",
        "product_video_durable_public_seam": True,
        "automatic_retry_allowed": False,
        "automatic_resubmit_allowed": False,
        "automatic_fallback_allowed": False,
        "recovery_existing_tasks_only": True,
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "scene_tasks": [],
    }

    with pytest.raises(connector.RealVideoRenderError) as exc_info:
        asyncio.run(
            connector._render_scene_async(
                scene,
                str(tmp_path / "scene-2.mp4"),
                ["shopaikey_video"],
            )
        )

    assert str(exc_info.value) == "scene_provider_task_id_missing"
    assert exc_info.value.diagnostics["provider_submit_called"] is False
    assert provider_calls == []


def test_recovery_only_scene_provider_mismatch_fails_before_router(monkeypatch, tmp_path):
    provider_calls: list[str] = []

    def forbidden_provider_call(*_args, **_kwargs):
        provider_calls.append("called")
        raise AssertionError("provider mismatch must fail before provider routing")

    monkeypatch.setattr(connector, "run_provider_generation", forbidden_provider_call)
    scene = SimpleNamespace(
        scene_id=1,
        video_prompt="first scene",
        visual_prompt="first scene",
        aspect_ratio="9:16",
        target_duration_sec=8.0,
    )
    scene._toan_aas_job = {
        "id": 13,
        "job_id": 13,
        "source": "product_video",
        "product_video": True,
        "product_type": "video_ai_prompt",
        "scene_count": 2,
        "orchestration_mode": "per_scene_8s",
        "product_video_durable_public_seam": True,
        "automatic_retry_allowed": False,
        "automatic_resubmit_allowed": False,
        "automatic_fallback_allowed": False,
        "recovery_existing_tasks_only": True,
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "scene_tasks": [
            {
                "scene_index": 1,
                "provider": "key4u_video",
                "provider_task_id": TASK_SCENE_1,
                "status": "provider_running",
            }
        ],
    }

    with pytest.raises(connector.RealVideoRenderError) as exc_info:
        asyncio.run(
            connector._render_scene_async(
                scene,
                str(tmp_path / "scene-1.mp4"),
                ["shopaikey_video"],
            )
        )

    assert str(exc_info.value) == "scene_provider_mismatch"
    assert exc_info.value.diagnostics["provider_submit_called"] is False
    assert provider_calls == []


def test_worker_payload_preserves_existing_task_only_contract():
    result = _live_job13_result()
    result.update(
        {
            "recovery_existing_tasks_only": True,
            "provider_submit_allowed": False,
            "automatic_retry_allowed": False,
            "automatic_resubmit_allowed": False,
            "automatic_fallback_allowed": False,
        }
    )
    hydrated = {
        "id": 13,
        "project_id": 13,
        "user_id": 919_013,
        "job_type": queue.VIDEO_RENDER_JOB_TYPE,
        "status": "queued",
        "result_json": json.dumps(result),
        "project": _live_job13_project(),
        "scenes": [],
    }

    payload = remote_worker_api.build_worker_job_payload(hydrated)

    assert payload["recovery_existing_tasks_only"] is True
    assert payload["provider_submit_allowed"] is False
    assert payload["automatic_resubmit_allowed"] is False
    assert payload["automatic_fallback_allowed"] is False
    assert [item["provider_task_id"] for item in payload["scene_tasks"]] == [TASK_SCENE_1, TASK_SCENE_2]


def test_recovery_only_worker_payload_passes_poll_gate_without_reopening_submit():
    result = {
        **_live_job13_result(),
        "recovery_existing_tasks_only": True,
        "provider_submit_allowed": False,
        "automatic_retry_allowed": False,
        "automatic_resubmit_allowed": False,
        "automatic_fallback_allowed": False,
    }
    payload = remote_worker_api.build_worker_job_payload(
        {
            "id": 13,
            "project_id": 13,
            "user_id": 919_013,
            "job_type": queue.VIDEO_RENDER_JOB_TYPE,
            "status": "queued",
            "result_json": json.dumps(result),
            "project": _live_job13_project(),
            "scenes": [],
        }
    )

    assert payload["provider_call"] is True
    assert payload["provider_submit_allowed"] is False
    assert payload["recovery_existing_tasks_only"] is True
    assert remote_worker.product_video_job_allowed(payload) is True


def test_recovery_only_delivery_never_reopens_xu_charge(tmp_path):
    mp4 = tmp_path / "recovered-final.mp4"
    mp4.write_bytes(b"valid-recovered-product-video")
    project = {
        "video_delivered_at": "2026-08-03 23:00:00",
        "video_delivery_message_id": "tg-recovery-13",
        "final_video_path": str(mp4),
        "invoice_json": json.dumps(
            {
                "user_visible_price_xu": 300,
                "persisted_quoted_price_xu": 300,
                "customer_charge_planned_xu": 300,
                "wallet_charge_amount_xu": 300,
            }
        ),
    }
    result = {
        "final_video_path": str(mp4),
        "final_mp4_valid": True,
        "final_delivered": True,
        "artifact_valid_for_charge": True,
        "recovery_existing_tasks_only": True,
        "provider_submit_allowed": False,
        "charged_xu": 0,
    }

    decision = queue.product_video_delivery_charge_decision(
        project,
        {"id": 13},
        result,
    )

    assert decision["ok"] is False
    assert decision["amount_xu"] == 0
    assert decision["charge_skip_reason"] == "existing_task_recovery_no_charge"


def test_restart_target_reuses_same_status_message_and_keeps_elapsed_timer():
    assert hasattr(bot, "video_b14_auto_refresh_recovery_target")
    result = _live_job13_result()
    target = bot.video_b14_auto_refresh_recovery_target(
        {"id": 13, "project_id": 13, "user_id": 919_013, "status": "failed"},
        _live_job13_project(),
        result,
    )

    assert target["eligible"] is True
    assert target["chat_id"] == 919_013
    assert target["message_id"] == 777
    assert target["auto_refresh_recovered_from_db"] is True
    assert target["elapsed_live_tick_enabled"] is True

    candidates = bot._video_provider_task_candidates(result, _live_job13_project())
    summaries = [
        {
            "provider": item["provider"],
            "task_id": item["task_id"],
            "scene_index": item["scene_index"],
            "status": "running",
            "result_url_valid": False,
        }
        for item in candidates
    ]
    ledger = queue.product_video_scene_ledger_state(
        _live_job13_project(),
        {"id": 13, "status": "processing", "progress_percent": 20},
        {**result, "canonical_candidate_summaries": summaries},
    )
    board = product_progress_status.video_per_scene_progress_board(
        {**result, **ledger, "_panel_now_epoch": 1_800_000_100}
    )

    assert board["elapsed_live_tick_enabled"] is True
    assert board["elapsed_seconds_by_scene"] == {"1": 100, "2": 100}


def test_cancelled_status_wins_over_persisted_provider_alive_state():
    job = {
        "id": 13,
        "project_id": 13,
        "status": "processing",
        "result_json": json.dumps(
            {
                **_live_job13_result(),
                "provider_task_alive": True,
                "continue_polling": True,
            }
        ),
    }
    project = {**_live_job13_project(), "status": "cancelled"}

    assert bot.video_b14_auto_refresh_terminal_state(job, project) == "cancelled"


def test_rehydrate_target_rejects_conflicting_result_owner_and_private_chat():
    job = {
        "id": 13,
        "project_id": 13,
        "user_id": 919_013,
        "status": "processing",
        "result_json": "{}",
    }
    project = {
        **_live_job13_project(),
        "status": "processing",
        "user_id": 919_013,
    }
    payload = {
        **_live_job13_result(),
        "user_id": 404_404,
        "chat_id": 404_404,
    }
    outbox = {
        "outbox_id": 1,
        "job_id": 13,
        "project_id": 13,
        "dispatch_status": "acknowledged",
    }

    target = bot.video_b14_auto_refresh_recovery_target(
        job,
        project,
        payload,
        outbox,
    )

    assert target["eligible"] is False
    assert target["blocker"] == "status_owner_mismatch"
    assert target["user_id"] == 919_013
    assert target["chat_id"] == 0
    assert target["owner_consistent"] is False
    assert target["private_chat_owner_consistent"] is False


@pytest.mark.parametrize(
    ("project_status", "outbox_status", "expected_blocker"),
    [
        ("cancelled", "acknowledged", "project_cancelled"),
        ("processing", "cancelled", "dispatch_outbox_cancelled"),
    ],
)
def test_provider_recovery_stops_cancelled_work_before_any_provider_poll(
    monkeypatch,
    tmp_path,
    project_status,
    outbox_status,
    expected_blocker,
):
    db_path = tmp_path / f"routeengine29o-provider-cancel-{expected_blocker}.db"
    job_id, _project_id = _seed_rehydrate_job(
        db_path,
        project_status=project_status,
        outbox_status=outbox_status,
    )
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    provider_polls: list[int] = []

    def forbidden_provider_resolution(*_args, **_kwargs):
        provider_polls.append(job_id)
        raise AssertionError("cancelled Product Video must not poll a provider")

    monkeypatch.setattr(
        bot,
        "resolve_canonical_video_provider_task",
        forbidden_provider_resolution,
    )

    recovered = bot.video_provider_recover_existing_task(
        job_id,
        download=True,
        conn=conn,
        source="manual_status_refresh",
    )

    assert recovered["ok"] is False
    assert recovered["blocker"] == expected_blocker
    assert recovered["charge"] == 0
    assert provider_polls == []
    conn.close()


def test_autonomous_manual_refresh_stops_cancelled_job_before_recovery_or_delivery(
    monkeypatch,
    tmp_path,
):
    db_path = tmp_path / "routeengine29o-autonomous-cancel.db"
    job_id, _project_id = _seed_rehydrate_job(
        db_path,
        project_status="cancelled",
        outbox_status="acknowledged",
    )

    def open_test_db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    provider_polls: list[int] = []

    def forbidden_recovery(*_args, **_kwargs):
        provider_polls.append(job_id)
        raise AssertionError("cancelled manual refresh must not enter recovery")

    monkeypatch.setattr(bot, "db_connect", open_test_db)
    monkeypatch.setattr(
        bot,
        "run_product_video_bot_side_zero_task_watchdog",
        lambda *_args, **_kwargs: {"terminal_failed": 0, "details": []},
    )
    monkeypatch.setattr(
        bot,
        "video_b14_delivered_video_artifact",
        lambda *_args, **_kwargs: {"ok": False},
    )
    monkeypatch.setattr(bot, "video_provider_recover_existing_task", forbidden_recovery)

    result = asyncio.run(
        bot.video_b14_autonomous_materialize_and_deliver(
            SimpleNamespace(bot=SimpleNamespace()),
            919_013,
            job_id,
            source="manual_status_refresh",
        )
    )

    assert result["ok"] is False
    assert result["sent"] is False
    assert result["reason"] == "project_cancelled"
    assert result["charge"] == 0
    assert provider_polls == []


def test_auto_refresh_tick_stops_cancelled_job_before_poll_or_delivery(monkeypatch):
    key = bot.video_b14_auto_refresh_key(13)
    record = {
        "key": key,
        "job_id": 13,
        "chat_id": 919_013,
        "message_id": 777,
        "user_id": 919_013,
        "lang": "vi",
        "interval_seconds": 5,
        "last_render_hash": "cancelled",
        "terminal_state": "cancelled",
        "current_stage": "cancelled",
        "percent": 0,
        "stopped": False,
    }
    job = {"id": 13, "project_id": 13, "status": "processing"}
    project = {"project_id": 13, "status": "cancelled"}
    delivery_calls: list[int] = []

    async def delivery(*_args, **kwargs):
        delivery_calls.append(int(kwargs.get("job_id") or 13))
        return {"waiting": True, "sent": False}

    monkeypatch.setattr(bot, "VIDEO_STATUS_AUTO_REFRESH_JOBS", {key: record})
    monkeypatch.setattr(
        bot,
        "video_b14_auto_refresh_status_bundle",
        lambda *_args, **_kwargs: {"job": job, "project": project, "session": {}},
    )
    monkeypatch.setattr(bot, "video_b14_autonomous_materialize_and_deliver", delivery)
    monkeypatch.setattr(
        bot,
        "video_b14_auto_refresh_snapshot",
        lambda *_args, **_kwargs: {
            "render_hash": "cancelled",
            "terminal_state": "cancelled",
            "stage": "cancelled",
            "percent": 0,
            "text": "cancelled",
            "final_artifact_exists": False,
            "final_artifact_valid": False,
            "blocker": "",
        },
    )

    result = asyncio.run(
        bot.video_b14_auto_refresh_tick(SimpleNamespace(bot=SimpleNamespace()), key)
    )

    assert result["status"] == "stopped"
    assert result["reason"] == "cancelled"
    assert delivery_calls == []


def test_auto_refresh_metadata_cas_preserves_concurrent_claim_and_progress(monkeypatch, tmp_path):
    db_path = tmp_path / "routeengine29o-metadata-cas.db"
    job_id, _project_id = _seed_rehydrate_job(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    original_get = queue.get_video_render_job
    get_calls = 0

    def racing_get(db, wanted_job_id):
        nonlocal get_calls
        row = original_get(db, wanted_job_id)
        get_calls += 1
        if get_calls == 2:
            fresh = json.loads(row["result_json"])
            fresh.update(
                {
                    "worker_claim_id": "fresh-worker-claim",
                    "scene_dispatch_lease_by_index": {
                        "1": {"lease_owner": "fresh-worker"},
                        "2": {"lease_owner": "fresh-worker"},
                    },
                }
            )
            db.execute(
                "UPDATE video_jobs SET result_json=?,progress_percent=80 WHERE id=?",
                (json.dumps(fresh), int(wanted_job_id)),
            )
            db.commit()
        return row

    monkeypatch.setattr(bot.video_project_queue, "get_video_render_job", racing_get)

    bot.video_b14_persist_auto_refresh_metadata(
        job_id,
        {
            "auto_refresh_last_update_at": "2026-08-03 23:15:00",
            "final_progress_after_reconcile": 30,
        },
        conn=conn,
    )

    stored = original_get(conn, job_id)
    stored_result = json.loads(stored["result_json"])
    assert stored_result["worker_claim_id"] == "fresh-worker-claim"
    assert stored_result["scene_dispatch_lease_by_index"]["1"]["lease_owner"] == "fresh-worker"
    assert stored_result["auto_refresh_last_update_at"] == "2026-08-03 23:15:00"
    assert stored["progress_percent"] == 80
    conn.close()


def test_lifespan_rehydrates_product_video_status_registry_after_restart(monkeypatch, tmp_path):
    db_path = tmp_path / "routeengine29o-rehydrate.db"
    job_id, _project_id = _seed_rehydrate_job(db_path)

    def open_test_db():
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        return db

    registrations: list[dict] = []
    persisted: list[tuple[int, dict]] = []

    def register(**kwargs):
        registrations.append(dict(kwargs))
        return {"key": bot.video_b14_auto_refresh_key(kwargs["job_id"]), **kwargs}

    monkeypatch.setattr(bot, "db_connect", open_test_db)
    monkeypatch.setattr(bot, "VIDEO_STATUS_AUTO_REFRESH_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_STATUS_AUTO_REFRESH_JOBS", {})
    monkeypatch.setattr(bot, "video_b14_auto_refresh_register", register)
    monkeypatch.setattr(
        bot,
        "video_b14_persist_auto_refresh_metadata",
        lambda job_id, payload: persisted.append((int(job_id), dict(payload))),
    )

    report = asyncio.run(
        bot.video_b14_rehydrate_auto_refresh_registry(SimpleNamespace(), limit=10)
    )

    assert report == {
        "ok": True,
        "scanned": 1,
        "eligible": 1,
        "registered": 1,
        "recovered_jobs": 0,
    }
    assert registrations[0]["job_id"] == job_id
    assert registrations[0]["chat_id"] == 919_013
    assert registrations[0]["message_id"] == 777
    assert registrations[0]["start_task"] is True
    assert persisted[0][0] == job_id
    assert persisted[0][1]["status_panel_message_id"] == 777
    assert persisted[0][1]["elapsed_live_tick_enabled"] is True


@pytest.mark.parametrize(
    ("project_status", "outbox_status"),
    [("cancelled", "acknowledged"), ("processing", "cancelled")],
)
def test_lifespan_does_not_rehydrate_cancelled_product_video(
    monkeypatch,
    tmp_path,
    project_status,
    outbox_status,
):
    db_path = tmp_path / f"routeengine29o-rehydrate-{project_status}-{outbox_status}.db"
    _seed_rehydrate_job(
        db_path,
        project_status=project_status,
        outbox_status=outbox_status,
    )

    def open_test_db():
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        return db

    registrations: list[dict] = []
    monkeypatch.setattr(bot, "db_connect", open_test_db)
    monkeypatch.setattr(bot, "VIDEO_STATUS_AUTO_REFRESH_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_STATUS_AUTO_REFRESH_JOBS", {})
    monkeypatch.setattr(
        bot,
        "video_b14_auto_refresh_register",
        lambda **kwargs: registrations.append(dict(kwargs)),
    )

    report = asyncio.run(
        bot.video_b14_rehydrate_auto_refresh_registry(SimpleNamespace(), limit=10)
    )

    assert report["scanned"] == 1
    assert report["eligible"] == 0
    assert report["registered"] == 0
    assert registrations == []
