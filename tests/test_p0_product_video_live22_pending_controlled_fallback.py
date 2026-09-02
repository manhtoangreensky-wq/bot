import asyncio
import json
import sqlite3
import time
from datetime import datetime
from types import SimpleNamespace

import pytest

import remote_worker
from services import remote_worker_api
from services import video_provider_router as router
from services import video_real_render_connector as connector
from services import video_project_queue as queue


def _configure_key4u_veo_contract(monkeypatch) -> None:
    for key, value in {
        "KEY4U_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_SUBMIT_URL": "https://api.key4u.vn/v1/video/create",
        "KEY4U_VIDEO_POLL_URL": (
            "https://api.key4u.vn/v1/video/query?id={task_id}"
        ),
        "KEY4U_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer test-key",
        "KEY4U_VIDEO_MODEL": "veo_3_1-fast",
        "KEY4U_VIDEO_CAPABILITIES": (
            "text_to_video,scene_video,multi_scene_video"
        ),
    }.items():
        monkeypatch.setenv(key, value)


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
    _configure_key4u_veo_contract(monkeypatch)
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
        captured["fallback_count_before_submit"] = request.metadata.get(
            "fallback_count_before_submit"
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
    assert captured["fallback_count_before_submit"] == 0
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
            provider_budget_xu=212,
            fallback_provider_cost_xu=212,
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
    assert stored["attempts"] == 0
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
    worker_payload = remote_worker_api.build_worker_job_payload(
        queue.hydrate_video_job_payload(conn, claimed)
    )
    assert worker_payload["controlled_fallback_worker_context"] is True
    assert worker_payload["user_visible_price_xu"] == 144
    assert worker_payload["persisted_quoted_price_xu"] == 144
    assert worker_payload["customer_charge_planned_xu"] == 144
    assert worker_payload["provider_budget_xu"] == 212
    assert worker_payload["fallback_provider_cost_xu"] == 212
    assert worker_payload["provider_order"] == [
        "shopaikey_video",
        "key4u_video",
    ]
    assert worker_payload["fallback_scene_index"] == 1
    assert worker_payload["scene_tasks"][0]["fallback_idempotency_key"]
    assert queue.get_product_video_dispatch_outbox(
        conn, job_id=job_id
    )["dispatch_status"] == "acknowledged"
    conn.close()


def test_live28_worker_payload_preserves_controlled_fallback_context(
    monkeypatch,
    tmp_path,
):
    _configure_key4u_veo_contract(monkeypatch)
    fallback_key = connector.product_video_scene_fallback_idempotency_key(
        28,
        1,
        "key4u_video",
    )
    scene_tasks = [
        {
            "scene_index": index,
            "scene_id": index,
            "request_job_id": f"28-{index}",
            "provider": "shopaikey_video",
            "provider_task_id": f"primary-task-{index}",
            "active_task_id": f"primary-task-{index}",
            "status": "provider_running",
            "actual_provider_payload_status": "IN_PROGRESS",
            "provider_status_payload_source": "shopaikey.data.status",
            "provider_started_at_epoch": 1,
            "fallback_count": 0,
            "fallback_allowed": index == 1,
            "controlled_fallback_allowed": index == 1,
            "fallback_provider_order": ["key4u_video"] if index == 1 else [],
            "fallback_provider_candidate": "key4u_video" if index == 1 else "",
            "fallback_scene_index": 1 if index == 1 else 0,
            "fallback_idempotency_key": fallback_key if index == 1 else "",
            "fallback_authorization_source": (
                "persisted_exact_quote_final_confirm" if index == 1 else ""
            ),
            "result_url_valid": False,
            "clip_valid": False,
        }
        for index in (1, 2)
    ]
    persisted = {
        "source": "product_video",
        "product_video": True,
        "product_type": "video_trend",
        "scene_count": 2,
        "orchestration_mode": "per_scene_8s",
        "recovery_existing_tasks_only": True,
        "original_submit_source": "public_user_final_confirm",
        "submit_source": "worker_poll_existing_task",
        "provider_submit_source": "worker_poll_existing_task",
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "provider_submit_accepted_before": True,
        "configured_provider_chain": ["shopaikey_video", "key4u_video"],
        "contract_valid_provider_chain": ["shopaikey_video", "key4u_video"],
        "runtime_candidate_keys": ["shopaikey_video"],
        "preconfirm_candidate_keys": ["shopaikey_video"],
        "user_visible_price_xu": 144,
        "persisted_quoted_price_xu": 144,
        "customer_charge_planned_xu": 144,
        "provider_budget_xu": 212,
        "provider_cost_cap_xu": 212,
        "fallback_provider_cost_xu": 212,
        "quote_consistent": True,
        "paid_fallback_confirmed": True,
        "explicit_paid_retry_confirmed": True,
        "owner_provider_gate_approved": True,
        "automatic_retry_allowed": False,
        "automatic_resubmit_allowed": False,
        "automatic_fallback_allowed": False,
        "provider_submit_allowed": False,
        "fallback_count": 0,
        "fallback_count_before_submit": 0,
        "fallback_count_by_scene": {"1": 0, "2": 0},
        "fallback_scene_index": 1,
        "fallback_allowed": True,
        "controlled_fallback_allowed": True,
        "fallback_provider_candidate": "key4u_video",
        "fallback_provider_order": ["key4u_video"],
        "fallback_authorization_source": "persisted_exact_quote_final_confirm",
        "claim_terminal_suppressed_for_controlled_fallback": True,
        "scene_tasks": scene_tasks,
        "provider_scene_tasks": scene_tasks,
        "charged_xu": 0,
        "no_charge": True,
    }
    project = {
        "project_id": 32,
        "user_id": 7126457028,
        "profile_id": "video_trend",
        "topic": "PV2-R01",
        "ratio": "9:16",
        "quality_tier": 400,
        "scene_count": 2,
        "total_xu_estimated": 144,
        "is_confirmed": 1,
        "asset_pack_json": json.dumps(
            {
                "source": "product_video",
                "product_type": "video_trend",
                "admin_only": True,
                "no_charge": True,
                "provider_call": True,
                "public_user": False,
            }
        ),
        "invoice_json": json.dumps(
            {
                "source": "product_video",
                "product_type": "video_trend",
                "scene_count": 2,
                "quality_tier": 400,
                "quality_xu": 80,
                "total_xu": 144,
                "admin_only": True,
                "no_charge": True,
                "public_user_confirmed": True,
            }
        ),
        "addon_plan_json": "{}",
        "scene_cards_json": json.dumps(
            [
                {"scene_index": 1, "video_prompt": "scene one"},
                {"scene_index": 2, "video_prompt": "scene two"},
            ]
        ),
    }
    hydrated = {
        "id": 28,
        "job_id": 28,
        "project_id": 32,
        "user_id": 7126457028,
        "job_type": queue.VIDEO_RENDER_JOB_TYPE,
        "status": "processing",
        "attempts": 7,
        "max_attempts": 3,
        "result_json": json.dumps(persisted),
        "project": project,
        "scenes": [
            {"scene_id": 130, "project_id": 32, "scene_index": 1},
            {"scene_id": 131, "project_id": 32, "scene_index": 2},
        ],
    }

    payload = remote_worker_api.build_worker_job_payload(hydrated)

    assert payload["user_visible_price_xu"] == 144
    assert payload["persisted_quoted_price_xu"] == 144
    assert payload["customer_charge_planned_xu"] == 144
    assert payload["provider_budget_xu"] == 212
    assert payload["fallback_provider_cost_xu"] == 212
    assert payload["provider_order"] == ["shopaikey_video", "key4u_video"]
    assert payload["fallback_scene_index"] == 1
    assert payload["controlled_fallback_allowed"] is True
    assert payload["fallback_provider_candidate"] == "key4u_video"
    assert payload["fallback_count_before_submit"] == 0
    assert payload["claim_terminal_suppressed_for_controlled_fallback"] is True
    assert [
        item["scene_index"]
        for item in payload["scene_tasks"]
        if item.get("controlled_fallback_allowed")
    ] == [1]
    assert payload["scene_tasks"][0]["fallback_idempotency_key"] == fallback_key
    assert payload["automatic_resubmit_allowed"] is False
    assert payload["charged_xu"] == 0

    captured = {}

    def fake_provider_generation(request, *, output_dir, environ, **_kwargs):
        captured["provider_chain"] = environ.get("VIDEO_PROVIDER_CHAIN")
        captured["submit_source"] = request.metadata.get("submit_source")
        captured["customer_quote"] = [
            request.metadata.get("user_visible_price_xu"),
            request.metadata.get("persisted_quoted_price_xu"),
            request.metadata.get("customer_charge_planned_xu"),
        ]
        captured["provider_budget_xu"] = request.metadata.get(
            "provider_budget_xu"
        )
        captured["fallback_provider_cost_xu"] = request.metadata.get(
            "fallback_provider_cost_xu"
        )
        captured["fallback_count_before_submit"] = request.metadata.get(
            "fallback_count_before_submit"
        )
        captured["fallback_count"] = request.metadata.get("fallback_count")
        captured["router_policy"] = router.product_video_controlled_fallback_policy(
            "provider_timeout",
            request.metadata,
        )
        captured["retry_router_policy"] = (
            router.product_video_controlled_fallback_policy(
                "provider_timeout",
                {
                    **request.metadata,
                    "fallback_count": 2,
                    "fallback_count_before_submit": 1,
                },
            )
        )
        captured["fallback_idempotency_key"] = request.metadata.get(
            "fallback_idempotency_key"
        )
        captured["pending_task_id"] = request.metadata.get(
            "provider_pending_task_id"
        )
        captured["pending_video_id"] = request.metadata.get(
            "provider_pending_video_id"
        )
        output = tmp_path / "key4u-live28-scene-1.mp4"
        output.write_bytes(b"key4u-live28-scene")
        return {
            "ok": True,
            "output_path": str(output),
            "provider": "key4u_video",
            "provider_task_ids": ["key4u-task-live28"],
            "provider_video_ids": ["key4u-task-live28"],
        }

    monkeypatch.setattr(
        connector,
        "run_provider_generation",
        fake_provider_generation,
    )
    scene = SimpleNamespace(
        scene_id=1,
        video_prompt="approved scene one",
        visual_prompt="approved scene one",
        aspect_ratio="9:16",
        target_duration_sec=8,
        _toan_aas_job=payload,
    )

    rendered = asyncio.run(
        connector._render_scene_async(
            scene,
            str(tmp_path / "provider-scene-1.mp4"),
            ["key4u_video"],
        )
    )

    assert rendered["ok"] is True
    assert captured["provider_chain"] == "key4u_video"
    assert captured["submit_source"] == "public_confirmed_scene_fallback_once"
    assert captured["customer_quote"] == [144, 144, 144]
    assert captured["provider_budget_xu"] == 212
    assert captured["fallback_provider_cost_xu"] == 212
    assert captured["fallback_count_before_submit"] == 0
    assert captured["fallback_count"] == 1
    assert captured["router_policy"]["fallback_submit_allowed"] is True
    assert captured["router_policy"]["fallback_block_reason"] == ""
    assert captured["retry_router_policy"]["fallback_submit_allowed"] is False
    assert (
        captured["retry_router_policy"]["fallback_block_reason"]
        == "fallback_limit_reached"
    )
    assert captured["fallback_idempotency_key"] == fallback_key
    assert captured["pending_task_id"] == ""
    assert captured["pending_video_id"] == ""

    normal_persisted = {
        **persisted,
        "claim_terminal_suppressed_for_controlled_fallback": False,
        "controlled_fallback_allowed": False,
    }
    normal_payload = remote_worker_api.build_worker_job_payload(
        {
            **hydrated,
            "result_json": json.dumps(normal_persisted),
        }
    )
    assert "controlled_fallback_worker_context" not in normal_payload


def test_live28_controlled_recovery_authorizes_only_locked_scene(monkeypatch):
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
    scenes = [
        {
            **_stalled_primary_scene(),
            "scene_index": index,
            "provider_task_id": f"shop-task-live28-{index}",
            "provider_video_id": f"shop-task-live28-{index}",
            "active_task_id": f"shop-task-live28-{index}",
            "request_job_id": f"28-{index}",
            "controlled_fallback_allowed": index == 1,
            "fallback_provider_candidate": "key4u_video" if index == 1 else "",
            "fallback_scene_index": 1 if index == 1 else 0,
        }
        for index in (1, 2)
    ]
    job = _confirmed_exact_quote_job(
        id=28,
        job_id=28,
        scene_count=2,
        provider_order=["shopaikey_video", "key4u_video"],
        configured_provider_chain=["shopaikey_video", "key4u_video"],
        recovery_existing_tasks_only=True,
        fallback_scene_index=1,
        fallback_provider_candidate="key4u_video",
        controlled_fallback_allowed=True,
        claim_terminal_suppressed_for_controlled_fallback=True,
        scene_tasks=scenes,
        provider_budget_xu=212,
        fallback_provider_cost_xu=212,
        automatic_retry_allowed=False,
        automatic_resubmit_allowed=False,
        provider_submit_allowed=False,
    )

    scene_one = connector.product_video_scene_stall_policy(job, scenes[0], 1)
    scene_two = connector.product_video_scene_stall_policy(job, scenes[1], 2)
    scene_one_without_candidate = connector.product_video_scene_stall_policy(
        job,
        {**scenes[0], "fallback_provider_candidate": ""},
        1,
    )

    assert scene_one["controlled_fallback_allowed"] is True
    assert scene_one["fallback_allowed"] is True
    assert scene_one["fallback_provider_candidate"] == "key4u_video"
    assert scene_two["controlled_fallback_allowed"] is False
    assert scene_two["fallback_allowed"] is False
    assert scene_two["fallback_block_reason"] == "automatic_fallback_forbidden"
    assert scene_two["fallback_provider_candidate"] == ""
    assert scene_two["fallback_provider_order"] == []
    assert scene_two["fallback_idempotency_key"] == ""
    assert scene_one_without_candidate["controlled_fallback_allowed"] is False
    assert scene_one_without_candidate["fallback_allowed"] is False


def test_live28_deferred_provider_poll_waits_until_next_poll_at(
    monkeypatch,
    tmp_path,
):
    conn = sqlite3.connect(tmp_path / "live28-next-poll.db")
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    project = queue.create_video_project(
        conn,
        user_id=7126457028,
        profile_id="video_trend",
        topic="PV2-R01 bounded provider poll",
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
            "total_xu": 144,
            "admin_only": True,
            "no_charge": True,
            "public_user_confirmed": True,
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
    scene_tasks = [
        {
            "scene_index": index,
            "request_job_id": f"{job_id}-{index}",
            "provider": "shopaikey_video",
            "provider_task_id": f"shop-task-live28-{index}",
            "active_task_id": f"shop-task-live28-{index}",
            "status": "provider_running",
            "actual_provider_payload_status": "IN_PROGRESS",
            "provider_status_payload_source": "shopaikey.data.status",
            "fallback_count": 0,
            "clip_valid": False,
        }
        for index in (1, 2)
    ]
    payload = {
        **_confirmed_exact_quote_job(
            id=job_id,
            job_id=job_id,
            project_id=project_id,
        ),
        "scene_count": 2,
        "scene_tasks": scene_tasks,
        "provider_scene_tasks": scene_tasks,
        "recovery_existing_tasks_only": True,
        "provider_pending_deferred": True,
        "continue_polling": True,
        "provider_error": "provider_in_progress",
        "blocker": "provider_in_progress",
        "next_poll_at": "2026-08-31 16:35:22",
        "next_poll_scheduled_at": "2026-08-31 16:35:22",
        "automatic_retry_allowed": False,
        "automatic_resubmit_allowed": False,
        "automatic_fallback_allowed": False,
        "provider_submit_allowed": False,
    }
    conn.execute(
        "UPDATE video_jobs SET status='queued',attempts=8,result_json=? WHERE id=?",
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
    monkeypatch.setattr(
        remote_worker_api,
        "_product_video_runtime_eligibility",
        lambda *_args, **_kwargs: {
            "runtime_candidate_keys": ["shopaikey_video"],
            "eligible_provider_keys": ["shopaikey_video"],
            "worker_local_ready_provider_keys": ["shopaikey_video", "key4u_video"],
            "contract_valid_provider_chain": ["shopaikey_video", "key4u_video"],
            "provider_submit_allowed": False,
        },
    )

    early = remote_worker_api._claim_video_render_candidate(
        conn,
        worker_id="live28-owner-worker",
        owner_product_video_only=True,
        public_enabled=False,
        now=datetime(2026, 8, 31, 16, 35, 10),
    )
    after_early = queue.get_video_render_job(conn, job_id)
    due = remote_worker_api._claim_video_render_candidate(
        conn,
        worker_id="live28-owner-worker",
        owner_product_video_only=True,
        public_enabled=False,
        now=datetime(2026, 8, 31, 16, 35, 23),
    )

    assert early == {}
    assert after_early["status"] == "queued"
    assert int(after_early["attempts"]) == 8
    assert int(due["id"]) == job_id
    assert int(queue.get_video_render_job(conn, job_id)["attempts"]) == 8
    conn.close()
