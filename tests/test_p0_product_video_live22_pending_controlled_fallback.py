import asyncio
import json
import sqlite3
import time
from datetime import datetime
from types import SimpleNamespace

import pytest

import remote_worker
from services import remote_worker_api
from services import video_real_render_connector as connector
from services import video_project_queue as queue


def _confirmed_exact_quote_job(**overrides):
    job = {
        "id": 22,
        "job_id": 22,
        "source": "product_video",
        "product_video": True,
        "admin_only": True,
        "no_charge": True,
        "original_submit_source": "public_user_final_confirm",
        "submit_source": "worker_poll_existing_task",
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "provider_order": ["shopaikey_video", "key4u_video"],
        "product_video_durable_public_seam": True,
        "automatic_fallback_allowed": False,
        "user_visible_price_xu": 144,
        "persisted_quoted_price_xu": 144,
        "customer_charge_planned_xu": 144,
        "provider_budget_xu": 144,
        "quote_consistent": True,
        "charged_xu": 0,
    }
    job.update(overrides)
    return job


def _stalled_primary_scene():
    return {
        "scene_index": 1,
        "provider": "shopaikey_video",
        "provider_task_id": "shop-task-live22",
        "provider_video_id": "shop-task-live22",
        "provider_status": "NOT_START",
        "provider_status_raw": "NOT_START",
        "provider_elapsed_seconds": 90,
        "provider_wait_elapsed_seconds": 90,
        "provider_progress_raw": 0,
        "fallback_count": 0,
        "result_url_valid": False,
    }


def test_live22_worker_preserves_provider_not_start_pending_reason(monkeypatch, tmp_path):
    pending = {
        "ok": False,
        "continue_polling": True,
        "terminal_state": "final_rendering",
        "provider_error": "provider_not_start",
        "blocker": "provider_not_start",
        "provider_task_ids": ["shop-task-live22"],
        "no_charge": True,
    }
    monkeypatch.setattr(connector, "render_real_video_job", lambda _job, _work_dir: dict(pending))

    with pytest.raises(RuntimeError, match="^provider_not_start$"):
        remote_worker.render_real_video(_confirmed_exact_quote_job(), str(tmp_path))

    assert remote_worker.LAST_REAL_VIDEO_RENDER_RESULT["continue_polling"] is True
    assert remote_worker.LAST_REAL_VIDEO_RENDER_RESULT["provider_error"] == "provider_not_start"


def test_live22_exact_quote_authorizes_one_controlled_scene_fallback(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", "60")

    policy = connector.product_video_scene_stall_policy(
        _confirmed_exact_quote_job(),
        _stalled_primary_scene(),
        1,
    )

    assert policy["automatic_fallback_forbidden"] is True
    assert policy["controlled_fallback_allowed"] is True
    assert policy["fallback_allowed"] is True
    assert policy["fallback_provider_order"] == ["key4u_video"]
    assert policy["fallback_count"] == 0
    assert policy["fallback_idempotency_key"]
    assert policy["fallback_authorization_source"] == "persisted_exact_quote_final_confirm"


def test_live22_controlled_fallback_stays_blocked_without_exact_quote(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", "60")

    policy = connector.product_video_scene_stall_policy(
        _confirmed_exact_quote_job(customer_charge_planned_xu=145, quote_consistent=False),
        _stalled_primary_scene(),
        1,
    )

    assert policy["controlled_fallback_allowed"] is False
    assert policy["fallback_allowed"] is False
    assert policy["fallback_block_reason"] == "automatic_fallback_forbidden"


def test_live22_exact_customer_price_allows_larger_internal_provider_budget(
    monkeypatch,
):
    monkeypatch.setenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", "60")
    policy = connector.product_video_scene_stall_policy(
        _confirmed_exact_quote_job(provider_budget_xu=212),
        _stalled_primary_scene(),
        1,
    )

    assert policy["exact_quote_preserved"] is True
    assert policy["controlled_fallback_allowed"] is True
    assert policy["fallback_allowed"] is True
    assert policy["fallback_provider_order"] == ["key4u_video"]


def test_live22_controlled_fallback_stays_blocked_without_final_confirm(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", "60")

    policy = connector.product_video_scene_stall_policy(
        _confirmed_exact_quote_job(
            original_submit_source="",
            public_user_confirmed=False,
            invoice_confirmed=False,
        ),
        _stalled_primary_scene(),
        1,
    )

    assert policy["controlled_fallback_allowed"] is False
    assert policy["fallback_allowed"] is False
    assert policy["fallback_block_reason"] == "automatic_fallback_forbidden"


def test_live22_started_at_text_drives_not_start_elapsed(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", "60")
    now_epoch = time.mktime(time.strptime("2026-08-27 16:34:28", "%Y-%m-%d %H:%M:%S"))
    monkeypatch.setattr(connector.time, "time", lambda: now_epoch)
    scene = {
        **_stalled_primary_scene(),
        "provider_elapsed_seconds": 0,
        "provider_wait_elapsed_seconds": 0,
        "started_at": "2026-08-27 16:32:58",
    }

    policy = connector.product_video_scene_stall_policy(
        _confirmed_exact_quote_job(),
        scene,
        1,
    )

    assert policy["scene_not_start_elapsed"] == 90
    assert policy["provider_stalled_not_start"] is True
    assert policy["fallback_allowed"] is True


def test_live22_controlled_scene_fallback_uses_key4u_once(monkeypatch, tmp_path):
    monkeypatch.setenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", "60")
    stalled_scene = {
        **_stalled_primary_scene(),
        "request_job_id": "22-1",
    }
    job = _confirmed_exact_quote_job(
        scene_count=2,
        scenes=[{"scene_index": 1}, {"scene_index": 2}],
        scene_tasks=[stalled_scene],
        provider_budget_xu=212,
        fallback_provider_cost_xu=212,
        recovery_existing_tasks_only=True,
        provider_submit_allowed=False,
        automatic_retry_allowed=False,
        automatic_resubmit_allowed=False,
    )
    captured = {}

    def fake_provider_generation(request, *, output_dir, environ, **_kwargs):
        captured["provider_chain"] = environ.get("VIDEO_PROVIDER_CHAIN")
        captured["submit_source"] = request.metadata.get("submit_source")
        captured["provider_budget_xu"] = request.metadata.get("provider_budget_xu")
        captured["fallback_provider_cost_xu"] = request.metadata.get(
            "fallback_provider_cost_xu"
        )
        output = tmp_path / "key4u-scene-1.mp4"
        output.write_bytes(b"key4u-live22-scene")
        return {
            "ok": True,
            "output_path": str(output),
            "provider": "key4u_video",
            "provider_task_ids": ["key4u-task-live22"],
            "provider_video_ids": ["key4u-task-live22"],
        }

    monkeypatch.setattr(connector, "run_provider_generation", fake_provider_generation)
    scene = SimpleNamespace(
        scene_id=1,
        video_prompt="approved Product Video prompt",
        visual_prompt="approved Product Video prompt",
        aspect_ratio="9:16",
        target_duration_sec=8,
        _toan_aas_job=job,
    )

    result = asyncio.run(
        connector._render_scene_async(
            scene,
            str(tmp_path / "rendered-scene-1.mp4"),
            ["shopaikey_video", "key4u_video"],
        )
    )

    assert result["ok"] is True
    assert captured["provider_chain"].split(",")[0] == "key4u_video"
    assert captured["submit_source"] == "public_confirmed_scene_fallback_once"
    assert captured["provider_budget_xu"] == 212
    assert captured["fallback_provider_cost_xu"] == 212
    assert result["fallback_count"] == 1
    assert result["fallback_idempotency_key"]


def test_live23_collapsed_primary_chain_recovers_ready_key4u_candidate(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", "60")
    monkeypatch.setattr(
        connector,
        "real_video_provider_readiness",
        lambda *_args, **_kwargs: {
            "ok": True,
            "ready_provider_order": ["shopaikey_video", "key4u_video"],
            "providers": [],
        },
    )

    policy = connector.product_video_scene_stall_policy(
        _confirmed_exact_quote_job(
            provider_order=["shopaikey_video"],
            configured_provider_chain=["shopaikey_video", "key4u_video"],
            required_capability="text_to_video_or_scene_video",
            product_video_durable_public_seam=None,
            product_video_route_decision=None,
        ),
        _stalled_primary_scene(),
        1,
    )

    assert policy["runtime_fallback_candidate_recovered"] is True
    assert policy["automatic_fallback_forbidden"] is True
    assert policy["fallback_provider_order"] == ["key4u_video"]
    assert policy["controlled_fallback_allowed"] is True
    assert policy["fallback_allowed"] is True
    assert policy["fallback_authorization_source"] == "persisted_exact_quote_final_confirm"


def test_live24_claim_gate_preserves_stalled_scenes_for_controlled_fallback(
    monkeypatch,
    tmp_path,
):
    conn = sqlite3.connect(tmp_path / "live24-claim-gate.db")
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    project = queue.create_video_project(
        conn,
        user_id=7126457028,
        profile_id="video_trend",
        topic="PV-L01 controlled fallback claim",
        asset_pack={
            "source": "product_video",
            "product_type": "video_trend",
            "render_mode": "real",
            "provider_call": True,
            "admin_only": True,
            "no_charge": True,
            "public_user": False,
        },
    )
    project_id = int(project["project_id"])
    queue.update_video_project(
        conn,
        project_id,
        status="queued_for_worker",
        is_confirmed=1,
        scene_count=2,
        invoice_json={
            "scene_count": 2,
            "duration_seconds": 16,
            "user_visible_price_xu": 144,
            "persisted_quoted_price_xu": 144,
            "customer_charge_planned_xu": 144,
            "provider_budget_xu": 144,
            "quote_consistent": True,
            "admin_only": True,
            "no_charge": True,
        },
    )
    job = queue.enqueue_video_render_job(
        conn,
        project_id=project_id,
        user_id=7126457028,
        max_attempts=3,
    )
    job_id = int(job["id"])
    queue.update_video_project(conn, project_id, job_id=job_id)
    stalled_scenes = [
        {
            "scene_index": index,
            "request_job_id": f"{job_id}-{index}",
            "provider": "shopaikey_video",
            "provider_task_id": f"shop-task-live24-{index}",
            "provider_video_id": f"shop-task-live24-{index}",
            "active_task_id": f"shop-task-live24-{index}",
            "status": "provider_not_start",
            "provider_status_raw": "NOT_START",
            "failure_reason": "provider_stalled_not_start",
            "provider_stalled_not_start": False,
            "scene_not_start_elapsed": 53,
            "provider_wait_elapsed_seconds": 53,
            "stall_threshold": 60,
            "fallback_count": 0,
            "fallback_allowed": False,
            "fallback_provider_order": [],
            "result_url_valid": False,
            "clip_valid": False,
        }
        for index in (1, 2)
    ]
    payload = {
        **_confirmed_exact_quote_job(
            id=job_id,
            job_id=job_id,
            project_id=project_id,
            provider_order=["shopaikey_video"],
            configured_provider_chain=["shopaikey_video", "key4u_video"],
            product_video_durable_public_seam=None,
            product_video_route_decision=None,
        ),
        "scene_count": 2,
        "scenes_total": 2,
        "scene_tasks_total": 2,
        "scene_tasks": stalled_scenes,
        "provider_stalled_not_start": True,
        "scene_not_start_elapsed": 61,
        "stall_threshold": 60,
        "fallback_scene_index": 1,
        "continue_polling": True,
        "terminal_state": "final_rendering",
        "final_decision": "continue_polling",
        "recovery_existing_tasks_only": True,
        "provider_submit_allowed": False,
        "automatic_retry_allowed": False,
        "automatic_resubmit_allowed": False,
        "automatic_fallback_allowed": False,
        "charged_xu": 0,
    }
    conn.execute(
        "UPDATE video_jobs SET status='queued',result_json=?,progress_percent=20,progress_message='provider_not_start' WHERE id=?",
        (json.dumps(payload), job_id),
    )
    outbox = queue.ensure_product_video_dispatch_outbox(
        conn,
        job_id=job_id,
        project_id=project_id,
        scene_indexes=[1, 2],
    )
    conn.execute(
        "UPDATE video_dispatch_outbox SET dispatch_status='acknowledged',acknowledged_at=CURRENT_TIMESTAMP WHERE outbox_id=?",
        (int(outbox["outbox_id"]),),
    )
    conn.commit()

    assert queue.product_video_scene_ledger_state(
        {}, job, payload, now=datetime(2026, 8, 27, 18, 28, 0)
    )["aggregate_job_status"] == "failed_no_charge"
    monkeypatch.setattr(
        remote_worker_api,
        "_product_video_runtime_eligibility",
        lambda *_args, **_kwargs: {
            "runtime_candidate_keys": ["shopaikey_video"],
            "eligible_provider_keys": ["shopaikey_video"],
            "worker_local_ready_provider_keys": [
                "shopaikey_video",
                "key4u_video",
            ],
            "contract_valid_provider_chain": [
                "shopaikey_video",
                "key4u_video",
            ],
            "provider_submit_allowed": False,
        },
    )

    claimed = remote_worker_api._claim_video_render_candidate(
        conn,
        worker_id="live24-owner-worker",
        owner_product_video_only=True,
        public_enabled=False,
        now=datetime(2026, 8, 27, 18, 28, 0),
    )

    assert int(claimed["id"]) == job_id
    stored = queue.get_video_render_job(conn, job_id)
    stored_payload = json.loads(stored["result_json"])
    assert stored["status"] == "processing"
    assert stored_payload["claim_terminal_suppressed_for_controlled_fallback"] is True
    assert stored_payload["fallback_provider_candidate"] == "key4u_video"
    assert stored_payload["fallback_scene_index"] == 1
    assert [
        item["scene_index"]
        for item in stored_payload["scene_tasks"]
        if item.get("controlled_fallback_allowed")
    ] == [1]
    assert stored_payload["controlled_fallback_allowed"] is True
    assert stored_payload["charged_xu"] == 0
    assert queue.get_product_video_dispatch_outbox(
        conn, job_id=job_id
    )["dispatch_status"] == "acknowledged"
    conn.close()
