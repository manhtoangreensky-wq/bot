from __future__ import annotations

import json
import sqlite3

import remote_worker
from services import remote_worker_api, video_project_queue


def _job28_pending_diagnostics() -> dict:
    return {
        "continue_polling": True,
        "terminal_state": "failed_no_charge",
        "final_decision": "failed_no_charge",
        "provider_error": "provider_in_progress",
        "blocker": "provider_in_progress",
        "provider_task_id_saved": True,
        "provider_task_ids": ["existing-scene-task-1"],
        "valid_provider_task_count": 2,
        "provider_status": "failed_no_charge",
        "normalized_provider_status": "failed_no_charge",
        "scene_tasks": [
            {
                "scene_index": 1,
                "provider": "shopaikey_video",
                "provider_task_id": "existing-scene-task-1",
                "status": "provider_running",
                "actual_provider_payload_status": "IN_PROGRESS",
                "provider_status_payload_source": "shopaikey.data.status",
                "state_authority_source": "shopaikey.data.status",
                "provider_progress_authoritative": True,
                "continue_polling": True,
                "submit_accepted": True,
                "task_pollable": True,
                "dispatch_state": "task_submitted",
            },
            {
                "scene_index": 2,
                "provider": "shopaikey_video",
                "provider_task_id": "existing-scene-task-2",
                "status": "provider_running",
                "actual_provider_payload_status": "IN_PROGRESS",
                "provider_status_payload_source": "shopaikey.data.status",
                "state_authority_source": "shopaikey.data.status",
                "provider_progress_authoritative": True,
                "continue_polling": True,
                "submit_accepted": True,
                "task_pollable": True,
                "dispatch_state": "task_submitted",
            },
        ],
    }


def test_job28_authoritative_running_tasks_override_only_stale_terminal_marker(
    monkeypatch,
) -> None:
    captured: dict = {}
    job = {
        "job_id": "28",
        "job_type": "video_render",
        "source": "product_video",
        "product_video": True,
        "provider_call": True,
    }

    monkeypatch.setattr(remote_worker, "claim_job", lambda **_kwargs: dict(job))
    monkeypatch.setattr(remote_worker, "product_video_job_allowed", lambda _job: True)

    def pending_provider(_job):
        remote_worker.LAST_REAL_VIDEO_RENDER_RESULT = _job28_pending_diagnostics()
        raise RuntimeError("provider_in_progress")

    def capture_failure(job_id, safe_error, retryable=True, partial_artifacts=None):
        captured.update(
            {
                "job_id": job_id,
                "safe_error": safe_error,
                "retryable": retryable,
                "partial_artifacts": partial_artifacts,
                "diagnostics": dict(remote_worker.LAST_REAL_VIDEO_RENDER_RESULT),
            }
        )
        return {
            "ok": True,
            "deferred": bool(retryable),
            "continue_polling": bool(retryable),
            "status": "queued" if retryable else "failed",
        }

    monkeypatch.setattr(remote_worker, "process_claimed_job", pending_provider)
    monkeypatch.setattr(remote_worker, "fail_job", capture_failure)

    assert remote_worker.run_once(owner_product_video_only=True) == "pending"
    assert captured["job_id"] == "28"
    assert captured["retryable"] is True
    assert captured["diagnostics"]["continue_polling"] is True
    assert captured["diagnostics"]["terminal_state"] == "failed_no_charge"
    assert captured["diagnostics"]["provider_task_ids"] == [
        "existing-scene-task-1",
    ]
    assert [
        item["provider_task_id"]
        for item in captured["diagnostics"]["scene_tasks"]
    ] == ["existing-scene-task-1", "existing-scene-task-2"]


def test_job28_explicit_scene_exhaustion_still_wins_over_stale_polling(
    monkeypatch,
) -> None:
    captured: dict = {}
    job = {
        "job_id": "28",
        "job_type": "video_render",
        "source": "product_video",
        "product_video": True,
        "provider_call": True,
    }

    monkeypatch.setattr(remote_worker, "claim_job", lambda **_kwargs: dict(job))
    monkeypatch.setattr(remote_worker, "product_video_job_allowed", lambda _job: True)

    def exhausted_provider(_job):
        remote_worker.LAST_REAL_VIDEO_RENDER_RESULT = _job28_pending_diagnostics()
        raise RuntimeError("all_scene_providers_exhausted_no_charge")

    def capture_failure(job_id, safe_error, retryable=True, partial_artifacts=None):
        captured.update(
            {
                "job_id": job_id,
                "safe_error": safe_error,
                "retryable": retryable,
                "partial_artifacts": partial_artifacts,
                "diagnostics": dict(remote_worker.LAST_REAL_VIDEO_RENDER_RESULT),
            }
        )
        return {"ok": True, "status": "failed"}

    monkeypatch.setattr(remote_worker, "process_claimed_job", exhausted_provider)
    monkeypatch.setattr(remote_worker, "fail_job", capture_failure)

    assert remote_worker.run_once(owner_product_video_only=True) == "failed"
    assert captured["retryable"] is False
    assert captured["diagnostics"]["continue_polling"] is False
    assert captured["diagnostics"]["terminal_state"] == "failed_no_charge"
    assert captured["diagnostics"]["provider_error"] == (
        "all_scene_providers_exhausted_no_charge"
    )


def test_job28_fail_api_persists_running_authority_not_stale_terminal() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        project = video_project_queue.create_video_project(
            conn,
            user_id=28,
            profile_id="video_trend",
            topic="job 28 provider polling",
            asset_pack={
                "source": "product_video",
                "render_mode": "real",
                "provider_call": True,
                "product_type": "video_trend",
                "public_user": True,
            },
        )
        video_project_queue.update_video_project(
            conn,
            int(project["project_id"]),
            status="queued_for_worker",
            total_xu_estimated=144,
            is_confirmed=1,
            scene_count=2,
        )
        job = video_project_queue.enqueue_video_render_job(
            conn,
            project_id=int(project["project_id"]),
            user_id=28,
        )
        claimed = video_project_queue.claim_next_video_job(
            conn,
            worker_id="job28-owner-worker",
        )

        result = remote_worker_api.fail_remote_worker_job(
            conn,
            worker_id="job28-owner-worker",
            job_id=int(claimed["id"]),
            safe_error="RuntimeError:provider_in_progress",
            retryable=True,
            diagnostics=_job28_pending_diagnostics(),
        )
        persisted = json.loads(result["job"]["result_json"])

        assert result["deferred"] is True
        assert result["continue_polling"] is True
        assert result["job"]["status"] == "queued"
        assert result["project"]["status"] == "processing"
        assert result["project"]["video_terminal_state"] == "final_rendering"
        assert persisted["continue_polling"] is True
        assert persisted["terminal_state"] == "final_rendering"
        assert persisted["final_decision"] == "continue_polling"
        assert persisted["provider_task_ids"] == ["existing-scene-task-1"]
        assert [
            item["provider_task_id"] for item in persisted["scene_tasks"]
        ] == ["existing-scene-task-1", "existing-scene-task-2"]
        assert persisted["no_charge"] is True
        assert int(result["project"].get("total_xu_charged") or 0) == 0
    finally:
        conn.close()


def test_scene_running_authority_does_not_revive_non_pending_terminal() -> None:
    payload = _job28_pending_diagnostics()
    payload.update(
        {
            "terminal_state": "cancelled",
            "final_decision": "cancelled",
            "continue_polling": True,
            "provider_error": "provider_in_progress",
            "blocker": "provider_in_progress",
        }
    )

    assert video_project_queue.provider_task_alive(payload) is False


def test_explicit_scene_exhaustion_reason_wins_over_stale_running_snapshot() -> None:
    payload = _job28_pending_diagnostics()
    payload["scene_forensic_terminal_reason"] = (
        "all_scene_providers_exhausted_no_charge"
    )

    assert video_project_queue.provider_task_alive(payload) is False


def _recovery_project() -> dict:
    return {
        "project_id": 32,
        "status": "failed",
        "is_confirmed": 1,
        "scene_count": 2,
        "invoice_json": json.dumps({"scene_count": 2}),
    }


def _recovery_result() -> dict:
    payload = _job28_pending_diagnostics()
    payload.update(
        {
            "source": "product_video",
            "product_video": True,
            "scene_count": 2,
            "public_user_confirmed": True,
            "invoice_confirmed": True,
            "charged_xu": 0,
            "task_scene_index_map": {
                "existing-scene-task-1": 1,
                "existing-scene-task-2": 2,
            },
            "scene_active_task_by_index": {
                "1": "existing-scene-task-1",
                "2": "existing-scene-task-2",
            },
        }
    )
    return payload


def test_job28_existing_running_tasks_are_recoverable_without_new_submit() -> None:
    state = video_project_queue.product_video_existing_task_recovery_state(
        {"id": 28, "project_id": 32, "status": "failed"},
        _recovery_project(),
        _recovery_result(),
        {"outbox_id": 27, "dispatch_status": "terminal_failed"},
    )

    assert state["existing_task_recovery_recoverable"] is True
    assert state["task_scene_index_map"] == {
        "existing-scene-task-1": 1,
        "existing-scene-task-2": 2,
    }
    assert state["provider_submit_allowed"] is False
    assert state["automatic_resubmit_allowed"] is False
    assert state["automatic_fallback_allowed"] is False


def test_job27_explicit_scene_exhaustion_is_never_recovered() -> None:
    result = _recovery_result()
    result["scene_forensic_terminal_reason"] = (
        "all_scene_providers_exhausted_no_charge"
    )
    for item in result["scene_tasks"]:
        item.update(
            {
                "status": "failed",
                "failure_reason": "provider_failed_result_url_invalid",
                "exhausted": True,
            }
        )

    state = video_project_queue.product_video_existing_task_recovery_state(
        {"id": 27, "project_id": 31, "status": "failed"},
        {**_recovery_project(), "project_id": 31},
        result,
        {"outbox_id": 26, "dispatch_status": "terminal_failed"},
    )

    assert state["existing_task_recovery_recoverable"] is False
    assert state["existing_task_recovery_block_reason"] == (
        "existing_provider_tasks_explicitly_terminal"
    )
