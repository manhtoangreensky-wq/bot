"""Explicit, same-job recovery for an Owner-authorized pre-submit failure."""

from __future__ import annotations

from datetime import datetime
import json
import sqlite3
from typing import Any, Mapping

from services import video_uiflow3_execution_contract


RECOVERABLE_ERRORS = frozenset(
    {"RuntimeError:uiflow3_approved_snapshot_hash_mismatch"}
)
TASK_ID_KEYS = (
    "provider_task_id",
    "provider_video_id",
    "task_id",
    "video_id",
    "active_task_id",
    "winning_task_id",
    "primary_task_id",
)


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _json_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _fetch_mapping(
    conn: sqlite3.Connection,
    statement: str,
    parameters: tuple[Any, ...],
) -> dict[str, Any]:
    cursor = conn.execute(statement, parameters)
    row = cursor.fetchone()
    if row is None:
        return {}
    if isinstance(row, Mapping):
        return dict(row)
    columns = [str(column[0]) for column in (cursor.description or ())]
    return dict(zip(columns, row))


def _has_provider_task(result: Mapping[str, Any]) -> bool:
    if any(str(result.get(key) or "").strip() for key in TASK_ID_KEYS):
        return True
    if any(str(item or "").strip() for item in result.get("provider_task_ids") or []):
        return True
    for collection in (
        result.get("scene_tasks"),
        result.get("provider_scene_tasks"),
        result.get("provider_events"),
    ):
        for raw in collection or []:
            if isinstance(raw, Mapping) and any(
                str(raw.get(key) or "").strip() for key in TASK_ID_KEYS
            ):
                return True
    return False


def _blocked(reason: str) -> dict[str, Any]:
    return {
        "owner_pre_submit_recovered": False,
        "owner_pre_submit_recovery_block_reason": str(reason or "recovery_blocked"),
        "jobs_created": 0,
        "outboxes_created": 0,
        "provider_calls": 0,
        "wallet_mutations": 0,
    }


def recover_product_video_owner_pre_submit_failure(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    worker_payload: Mapping[str, Any] | None,
    owner_authorized: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Requeue one failed job after a verified internal pre-submit defect.

    This is a one-time manual recovery edge. It never creates a job/outbox,
    submits to a provider, or mutates the wallet.
    """

    if not owner_authorized:
        return _blocked("owner_authorization_required")
    if not isinstance(conn, sqlite3.Connection) or _integer(job_id) <= 0:
        return _blocked("recovery_identity_invalid")
    job = _fetch_mapping(
        conn,
        """SELECT id,project_id,user_id,job_type,status,attempts,max_attempts,
                  last_error,result_json
             FROM video_jobs WHERE id=?""",
        (_integer(job_id),),
    )
    if not job:
        return _blocked("job_not_found")
    project = _fetch_mapping(
        conn,
        """SELECT project_id,user_id,status,ratio,asset_pack_json,is_confirmed,
                  job_id,video_terminal_state
             FROM video_projects WHERE project_id=?""",
        (_integer(job.get("project_id")),),
    )
    outbox = _fetch_mapping(
        conn,
        """SELECT outbox_id,job_id,project_id,dispatch_status,attempt_count
             FROM video_dispatch_outbox WHERE job_id=?""",
        (_integer(job_id),),
    )
    if not project or not outbox:
        return _blocked("durable_job_scope_missing")
    result = _json_mapping(job.get("result_json"))
    error = str(job.get("last_error") or "").strip()
    if str(job.get("job_type") or "") != "video_render":
        return _blocked("job_type_mismatch")
    if str(job.get("status") or "") != "failed":
        return _blocked("job_not_failed")
    if str(project.get("status") or "") != "failed":
        return _blocked("project_not_failed")
    if not _integer(project.get("is_confirmed")):
        return _blocked("public_confirmation_missing")
    if _integer(project.get("job_id")) != _integer(job_id):
        return _blocked("project_job_mismatch")
    if _integer(project.get("user_id")) != _integer(job.get("user_id")):
        return _blocked("owner_identity_mismatch")
    if (
        _integer(outbox.get("job_id")) != _integer(job_id)
        or _integer(outbox.get("project_id")) != _integer(project.get("project_id"))
        or str(outbox.get("dispatch_status") or "") != "acknowledged"
    ):
        return _blocked("acknowledged_outbox_required")
    if error not in RECOVERABLE_ERRORS:
        return _blocked("failure_reason_not_recoverable")
    if result.get("owner_pre_submit_recovery_used"):
        return _blocked("recovery_already_used")
    if _integer(job.get("attempts")) >= max(1, _integer(job.get("max_attempts"))):
        return _blocked("job_attempts_exhausted")
    provider_attempted = bool(
        result.get("provider_submit_called")
        or result.get("provider_http_request_sent")
        or _integer(result.get("provider_http_status")) > 0
        or _integer(result.get("submit_count")) > 0
    )
    if provider_attempted or _has_provider_task(result):
        return _blocked("provider_already_attempted")
    charged = bool(
        _integer(result.get("charge")) > 0
        or _integer(result.get("charged_xu")) > 0
        or _integer(result.get("charge_count")) > 0
        or result.get("wallet_charge_recorded")
    )
    if charged:
        return _blocked("wallet_charge_already_recorded")
    payload = dict(worker_payload or {})
    if any(
        (
            _integer(payload.get("job_id")) != _integer(job_id),
            _integer(payload.get("project_id")) != _integer(project.get("project_id")),
            _integer(payload.get("user_id")) != _integer(project.get("user_id")),
        )
    ):
        return _blocked("worker_payload_identity_mismatch")
    execution = video_uiflow3_execution_contract.validate_execution_contract(
        project,
        payload,
        require_payload_identity=True,
    )
    if not execution.get("applies") or not execution.get("ok"):
        return _blocked(
            str(execution.get("blocker") or "worker_payload_execution_contract_invalid")
        )

    current = (now or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    result.update(
        {
            "status": "queued",
            "canonical_status": "queued_waiting_for_dispatch",
            "terminal_state": "",
            "final_decision": "continue_polling",
            "terminal": False,
            "continue_polling": True,
            "next_poll_scheduled": True,
            "owner_pre_submit_recovery_used": True,
            "owner_pre_submit_recovery_count": 1,
            "owner_pre_submit_recovered_at": current,
            "owner_pre_submit_recovered_reason": error,
            "owner_pre_submit_recovery_source": "explicit_owner_authorization",
            "worker_claim_result": "owner_pre_submit_recovery_queued",
            "worker_claim_block_reason": "",
            "provider_submit_allowed": False,
            "provider_submit_block_reason": "owner_recovery_awaiting_worker_revalidation",
            "provider_submit_called": False,
            "provider_http_request_sent": False,
            "provider_task_id": None,
            "submit_count": 0,
            "charge": 0,
            "charged_xu": 0,
            "charge_count": 0,
            "wallet_charge_recorded": False,
        }
    )
    original_result_json = str(job.get("result_json") or "")
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            """UPDATE video_jobs
                  SET status='queued',result_json=?,last_error='',progress_percent=10,
                      progress_message='queued_waiting_for_dispatch',locked_by='',locked_at=NULL,
                      lease_expires_at=NULL,completed_at=NULL,updated_at=?
                WHERE id=? AND status='failed' AND last_error=? AND result_json=?""",
            (
                json.dumps(result, ensure_ascii=True, separators=(",", ":"), sort_keys=True),
                current,
                _integer(job_id),
                error,
                original_result_json,
            ),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return _blocked("recovery_claim_lost")
        project_cursor = conn.execute(
            """UPDATE video_projects
                  SET status='queued_for_worker',video_terminal_state='',
                      video_terminal_locked_at=NULL,error_log='',completed_at=NULL,updated_at=?
                WHERE project_id=? AND status='failed' AND job_id=?""",
            (current, _integer(project.get("project_id")), _integer(job_id)),
        )
        if project_cursor.rowcount != 1:
            conn.rollback()
            return _blocked("project_recovery_claim_lost")
        conn.execute(
            """UPDATE video_scenes SET scene_status='pending'
                WHERE project_id=? AND scene_status!='done'""",
            (_integer(project.get("project_id")),),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {
        "owner_pre_submit_recovered": True,
        "owner_pre_submit_recovery_block_reason": "",
        "job_id": _integer(job_id),
        "project_id": _integer(project.get("project_id")),
        "outbox_id": _integer(outbox.get("outbox_id")),
        "outbox_status": str(outbox.get("dispatch_status") or ""),
        "jobs_created": 0,
        "outboxes_created": 0,
        "provider_calls": 0,
        "wallet_mutations": 0,
    }
