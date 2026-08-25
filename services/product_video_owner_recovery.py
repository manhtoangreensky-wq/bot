"""Explicit, same-job recovery for an Owner-authorized pre-submit failure."""

from __future__ import annotations

from datetime import datetime
import json
import os
import sqlite3
from typing import Any, Mapping

from services import video_uiflow3_execution_contract


ADDON_SUBTITLE_ERROR = "RuntimeError:addon_material_missing:subtitle"
ADDON_DUBBING_ERROR = "RuntimeError:addon_material_missing:dubbing"
POST_POLL_FINALIZER_ERROR = "RuntimeError:provider_render_failed:RuntimeError"
COMPLETION_409_ERROR = "HTTPError:HTTP Error 409: Conflict"
RECOVERABLE_ERRORS = frozenset(
    {
        "RuntimeError:uiflow3_approved_snapshot_hash_mismatch",
        ADDON_SUBTITLE_ERROR,
        ADDON_DUBBING_ERROR,
        POST_POLL_FINALIZER_ERROR,
        COMPLETION_409_ERROR,
    }
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


def _post_poll_finalizer_block_reason(
    result: Mapping[str, Any],
    *,
    job_id: int,
    user_id: int,
) -> str:
    if not result.get("recovery_existing_tasks_only"):
        return "post_poll_existing_task_mode_required"
    if not result.get("provider_poll_called"):
        return "post_poll_evidence_missing"
    if _integer(result.get("provider_poll_http_status")) != 200:
        return "post_poll_http_success_required"
    if not result.get("no_new_submit") or not result.get("no_new_paid_submit"):
        return "post_poll_no_new_submit_guard_missing"
    if _integer(result.get("submit_count")) != 0:
        return "post_poll_new_submit_detected"
    if not _has_provider_task(result):
        return "post_poll_provider_tasks_missing"
    if (
        result.get("final_mp4_valid")
        or result.get("final_delivered")
        or result.get("delivery_succeeded")
    ):
        return "post_poll_final_output_already_exists"

    scene_count = _integer(result.get("scene_count"))
    if scene_count <= 0 or not result.get("scene_clip_coverage_complete"):
        return "post_poll_scene_coverage_incomplete"
    if (
        _integer(result.get("valid_scene_clip_count")) < scene_count
        or _integer(result.get("completed_scene_count")) < scene_count
    ):
        return "post_poll_scene_coverage_incomplete"

    manifest_path = str(
        result.get("canonical_multiscene_manifest_path")
        or result.get("manifest_path")
        or ""
    ).strip()
    if not manifest_path or not os.path.isabs(manifest_path):
        return "post_poll_manifest_missing"
    try:
        with open(manifest_path, encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return "post_poll_manifest_unreadable"
    if not isinstance(manifest, Mapping):
        return "post_poll_manifest_invalid"
    if (
        _integer(manifest.get("job_id")) != _integer(job_id)
        or _integer(manifest.get("user_id")) != _integer(user_id)
    ):
        return "post_poll_manifest_identity_mismatch"
    if (
        str(manifest.get("concat_state") or "") != "normalizing"
        or str(manifest.get("delivery_state") or "") != "pending"
        or str(manifest.get("charge_state") or "") != "pending"
        or str(manifest.get("final_video_path") or "").strip()
    ):
        return "post_poll_manifest_not_recoverable"

    workspace = os.path.realpath(str(manifest.get("workspace_dir") or ""))
    resolved_manifest = os.path.realpath(manifest_path)
    if not workspace or os.path.dirname(resolved_manifest) != workspace:
        return "post_poll_workspace_binding_mismatch"
    result_workspace = str(result.get("canonical_multiscene_workspace") or "").strip()
    if result_workspace and os.path.realpath(result_workspace) != workspace:
        return "post_poll_workspace_binding_mismatch"

    expected_indexes = list(range(1, scene_count + 1))
    if list(manifest.get("required_scene_indexes") or []) != expected_indexes:
        return "post_poll_scene_index_mismatch"
    manifest_tasks = _json_mapping(manifest.get("task_ids_by_scene"))
    result_tasks = _json_mapping(result.get("scene_task_map"))
    provider_statuses = _json_mapping(manifest.get("provider_status_by_scene"))
    raw_paths = _json_mapping(manifest.get("raw_clip_paths_by_scene"))
    clip_validation = _json_mapping(result.get("scene_clip_validation_by_index"))
    for index in expected_indexes:
        key = str(index)
        task_ids = [str(item or "").strip() for item in manifest_tasks.get(key) or []]
        result_task_ids = [
            str(item or "").strip() for item in result_tasks.get(key) or []
        ]
        if not task_ids or task_ids != result_task_ids:
            return "post_poll_task_map_mismatch"
        if str(provider_statuses.get(key) or "") != "scene_clip_validated":
            return "post_poll_scene_not_validated"
        validation = _json_mapping(clip_validation.get(key))
        if (
            not validation.get("ok")
            or not validation.get("path_present")
            or _integer(validation.get("bytes")) <= 0
        ):
            return "post_poll_scene_not_validated"
        clip_path = os.path.realpath(str(raw_paths.get(key) or ""))
        try:
            path_inside_workspace = os.path.commonpath([workspace, clip_path]) == workspace
        except ValueError:
            path_inside_workspace = False
        if (
            not path_inside_workspace
            or not os.path.isfile(clip_path)
            or os.path.getsize(clip_path) <= 0
        ):
            return "post_poll_local_clip_missing"
    return ""


def _completion_409_block_reason(result: Mapping[str, Any]) -> str:
    if not result.get("recovery_existing_tasks_only"):
        return "completion_409_existing_task_mode_required"
    if not result.get("owner_post_poll_finalizer_recovery_used"):
        return "completion_409_post_poll_recovery_required"
    if not result.get("no_new_submit") or not result.get("no_new_paid_submit"):
        return "completion_409_no_new_submit_guard_missing"
    if _integer(result.get("submit_count")) != 0 or result.get("provider_submit_allowed"):
        return "completion_409_new_submit_detected"
    if not _has_provider_task(result):
        return "completion_409_provider_tasks_missing"
    if (
        result.get("final_delivered")
        or result.get("delivery_succeeded")
        or result.get("final_mp4_delivered")
    ):
        return "completion_409_final_output_already_delivered"

    scene_count = _integer(result.get("scene_count"))
    if (
        scene_count <= 0
        or not result.get("scene_clip_coverage_complete")
        or _integer(result.get("valid_scene_clip_count")) < scene_count
        or _integer(result.get("completed_scene_count")) < scene_count
        or list(result.get("unresolved_scene_indexes") or [])
    ):
        return "completion_409_scene_coverage_incomplete"
    if not result.get("final_mp4_valid"):
        return "completion_409_final_mp4_invalid"
    duration_contract = _json_mapping(result.get("final_duration_contract"))
    try:
        actual_duration = float(duration_contract.get("actual_duration_seconds") or 0)
    except (TypeError, ValueError):
        actual_duration = 0.0
    if not duration_contract.get("ok") or actual_duration <= 0:
        return "completion_409_duration_contract_invalid"

    raw_workspace = str(result.get("canonical_multiscene_workspace") or "").strip()
    raw_final_path = str(result.get("final_video_path") or "").strip()
    if not os.path.isabs(raw_workspace) or not os.path.isabs(raw_final_path):
        return "completion_409_final_artifact_missing"
    workspace = os.path.realpath(raw_workspace)
    final_path = os.path.realpath(raw_final_path)
    try:
        path_inside_workspace = os.path.commonpath([workspace, final_path]) == workspace
    except ValueError:
        path_inside_workspace = False
    if (
        not workspace
        or not path_inside_workspace
        or not os.path.isfile(final_path)
        or os.path.getsize(final_path) <= 0
    ):
        return "completion_409_final_artifact_missing"
    return ""


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
    """Requeue one failed job after a verified internal render defect.

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
    job_status = str(job.get("status") or "").strip()
    project_status = str(project.get("status") or "").strip()
    worker_poll_source = "worker_poll_existing_task"
    stale_poll_only_mode = bool(
        result.get("recovery_existing_tasks_only")
        or str(result.get("submit_source") or "").strip() == worker_poll_source
        or str(result.get("provider_submit_source") or "").strip()
        == worker_poll_source
    )
    max_attempts = max(1, _integer(job.get("max_attempts")))
    post_poll_finalizer_recovery = error == POST_POLL_FINALIZER_ERROR
    completion_409_recovery = error == COMPLETION_409_ERROR
    addon_subtitle_poll_only_repair = bool(
        job_status in {"queued", "processing"}
        and project_status in {"queued_for_worker", "processing"}
        and _integer(job.get("attempts")) > max_attempts
        and result.get("owner_addon_subtitle_recovery_used")
        and not result.get("owner_addon_subtitle_poll_only_repair_used")
        and stale_poll_only_mode
        and error in {"", "provider_in_progress", "provider_stalled_not_start"}
    )
    if str(job.get("job_type") or "") != "video_render":
        return _blocked("job_type_mismatch")
    if job_status != "failed" and not addon_subtitle_poll_only_repair:
        return _blocked("job_not_failed")
    if project_status != "failed" and not addon_subtitle_poll_only_repair:
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
    if error not in RECOVERABLE_ERRORS and not addon_subtitle_poll_only_repair:
        return _blocked("failure_reason_not_recoverable")
    addon_subtitle_recovery = bool(
        error in {ADDON_SUBTITLE_ERROR, ADDON_DUBBING_ERROR}
        or addon_subtitle_poll_only_repair
    )
    recovery_kind = (
        "completion_409"
        if completion_409_recovery
        else "post_poll_finalizer"
        if post_poll_finalizer_recovery
        else "addon_subtitle_poll_only_repair"
        if addon_subtitle_poll_only_repair
        else "addon_subtitle_materialization"
        if addon_subtitle_recovery
        else "approved_snapshot_hash"
    )
    if completion_409_recovery:
        if result.get("owner_completion_409_recovery_used"):
            return _blocked("completion_409_recovery_already_used")
    elif post_poll_finalizer_recovery:
        if result.get("owner_post_poll_finalizer_recovery_used"):
            return _blocked("post_poll_finalizer_recovery_already_used")
    elif addon_subtitle_poll_only_repair:
        if result.get("owner_addon_subtitle_poll_only_repair_used"):
            return _blocked("addon_subtitle_poll_only_repair_already_used")
    elif addon_subtitle_recovery:
        if result.get("owner_addon_subtitle_recovery_used"):
            return _blocked("addon_subtitle_recovery_already_used")
    elif result.get("owner_pre_submit_recovery_used"):
        return _blocked("recovery_already_used")
    if (
        not addon_subtitle_poll_only_repair
        and not post_poll_finalizer_recovery
        and not completion_409_recovery
        and _integer(job.get("attempts")) >= max_attempts
    ):
        return _blocked("job_attempts_exhausted")
    provider_attempted = bool(
        result.get("provider_submit_called")
        or result.get("provider_http_request_sent")
        or _integer(result.get("provider_http_status")) > 0
        or _integer(result.get("submit_count")) > 0
    )
    if not post_poll_finalizer_recovery and not completion_409_recovery and (
        provider_attempted or _has_provider_task(result)
    ):
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
    worker_compatibility = _json_mapping(payload.get("worker_compatibility"))
    if (
        addon_subtitle_recovery
        or post_poll_finalizer_recovery
        or completion_409_recovery
    ) and not worker_compatibility.get("compatible"):
        return _blocked(
            str(
                worker_compatibility.get("block_reason")
                or worker_compatibility.get("worker_admission_block_reason")
                or "worker_compatibility_required"
            )
        )
    if post_poll_finalizer_recovery:
        post_poll_blocker = _post_poll_finalizer_block_reason(
            result,
            job_id=_integer(job_id),
            user_id=_integer(project.get("user_id")),
        )
        if post_poll_blocker:
            return _blocked(post_poll_blocker)
    if completion_409_recovery:
        completion_blocker = _completion_409_block_reason(result)
        if completion_blocker:
            return _blocked(completion_blocker)
    execution = video_uiflow3_execution_contract.validate_execution_contract(
        project,
        payload,
        require_payload_identity=True,
    )
    if not execution.get("applies") or not execution.get("ok"):
        return _blocked(
            str(execution.get("blocker") or "worker_payload_execution_contract_invalid")
        )

    if addon_subtitle_recovery:
        if stale_poll_only_mode:
            resume_submit_source = str(
                result.get("original_submit_source") or ""
            ).strip()
            if not resume_submit_source or resume_submit_source == worker_poll_source:
                if result.get("public_user_confirmed") and result.get("invoice_confirmed"):
                    resume_submit_source = "public_user_final_confirm"
                else:
                    return _blocked("owner_recovery_original_submit_source_missing")
            result.update(
                {
                    "recovery_existing_tasks_only": False,
                    "provider_poll_existing_task": False,
                    "poll_existing_task_allowed": False,
                    "submit_source": resume_submit_source,
                    "provider_submit_source": resume_submit_source,
                    "original_submit_source": resume_submit_source,
                    "provider_stalled_not_start": False,
                    "error": "",
                    "owner_addon_subtitle_recovery_cleared_stale_poll_only_mode": True,
                }
            )

    current = (now or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    recovery_metadata = (
        {
            "owner_completion_409_recovery_used": True,
            "owner_completion_409_recovery_count": 1,
            "owner_completion_409_recovered_at": current,
            "owner_completion_409_recovered_reason": error,
            "owner_completion_409_recovery_source": "explicit_owner_authorization",
            "owner_completion_409_recovery_worker_compatible": True,
        }
        if completion_409_recovery
        else
        {
            "owner_post_poll_finalizer_recovery_used": True,
            "owner_post_poll_finalizer_recovery_count": 1,
            "owner_post_poll_finalizer_recovered_at": current,
            "owner_post_poll_finalizer_recovered_reason": error,
            "owner_post_poll_finalizer_recovery_source": "explicit_owner_authorization",
            "owner_post_poll_finalizer_recovery_worker_compatible": True,
        }
        if post_poll_finalizer_recovery
        else
        {
            "owner_addon_subtitle_poll_only_repair_used": True,
            "owner_addon_subtitle_poll_only_repair_count": 1,
            "owner_addon_subtitle_poll_only_repaired_at": current,
            "owner_addon_subtitle_poll_only_repair_source": "explicit_owner_authorization",
            "owner_addon_subtitle_recovery_worker_compatible": True,
        }
        if addon_subtitle_poll_only_repair
        else
        {
            "owner_addon_subtitle_recovery_used": True,
            "owner_addon_subtitle_recovery_count": 1,
            "owner_addon_subtitle_recovered_at": current,
            "owner_addon_subtitle_recovered_reason": error,
            "owner_addon_subtitle_recovery_source": "explicit_owner_authorization",
            "owner_addon_subtitle_recovery_worker_compatible": True,
        }
        if addon_subtitle_recovery
        else {
            "owner_pre_submit_recovery_used": True,
            "owner_pre_submit_recovery_count": 1,
            "owner_pre_submit_recovered_at": current,
            "owner_pre_submit_recovered_reason": error,
            "owner_pre_submit_recovery_source": "explicit_owner_authorization",
        }
    )
    result.update(
        {
            "status": "queued",
            "canonical_status": (
                "queued_existing_task_recovery"
                if post_poll_finalizer_recovery or completion_409_recovery
                else "queued_waiting_for_dispatch"
            ),
            "terminal_state": "",
            "final_decision": "continue_polling",
            "terminal": False,
            "continue_polling": True,
            "next_poll_scheduled": True,
            **recovery_metadata,
            "worker_claim_result": (
                "owner_completion_409_recovery_queued"
                if completion_409_recovery
                else "owner_post_poll_finalizer_recovery_queued"
                if post_poll_finalizer_recovery
                else "owner_addon_subtitle_poll_only_repair_queued"
                if addon_subtitle_poll_only_repair
                else "owner_addon_subtitle_recovery_queued"
                if addon_subtitle_recovery
                else "owner_pre_submit_recovery_queued"
            ),
            "worker_claim_block_reason": "",
            "provider_submit_allowed": False,
            "submit_count": 0,
            "charge": 0,
            "charged_xu": 0,
            "charge_count": 0,
            "wallet_charge_recorded": False,
        }
    )
    if post_poll_finalizer_recovery or completion_409_recovery:
        result.update(
            {
                "recovery_existing_tasks_only": True,
                "provider_poll_existing_task": True,
                "poll_existing_task_allowed": True,
                "submit_source": worker_poll_source,
                "provider_submit_source": worker_poll_source,
                "provider_submit_block_reason": (
                    "completion_409_recovery_read_only"
                    if completion_409_recovery
                    else "post_poll_finalizer_recovery_read_only"
                ),
                "no_new_submit": True,
                "no_new_paid_submit": True,
                "error": "",
            }
        )
    else:
        result.update(
            {
                "provider_submit_block_reason": "owner_recovery_awaiting_worker_revalidation",
                "provider_submit_called": False,
                "provider_http_request_sent": False,
                "provider_task_id": None,
            }
        )
    original_result_json = str(job.get("result_json") or "")
    try:
        conn.execute("BEGIN IMMEDIATE")
        encoded_result = json.dumps(
            result, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        )
        if (
            addon_subtitle_poll_only_repair
            or post_poll_finalizer_recovery
            or completion_409_recovery
        ):
            cursor = conn.execute(
                """UPDATE video_jobs
                      SET status='queued',attempts=?,result_json=?,last_error='',
                          progress_percent=10,progress_message='queued_waiting_for_dispatch',
                          locked_by='',locked_at=NULL,lease_expires_at=NULL,
                          completed_at=NULL,updated_at=?
                    WHERE id=? AND status=? AND attempts=? AND last_error=?
                      AND result_json=?""",
                (
                    max_attempts - 1,
                    encoded_result,
                    current,
                    _integer(job_id),
                    job_status,
                    _integer(job.get("attempts")),
                    error,
                    original_result_json,
                ),
            )
        else:
            cursor = conn.execute(
                """UPDATE video_jobs
                      SET status='queued',result_json=?,last_error='',progress_percent=10,
                          progress_message='queued_waiting_for_dispatch',locked_by='',locked_at=NULL,
                          lease_expires_at=NULL,completed_at=NULL,updated_at=?
                    WHERE id=? AND status='failed' AND last_error=? AND result_json=?""",
                (
                    encoded_result,
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
                WHERE project_id=? AND status=? AND job_id=?""",
            (
                current,
                _integer(project.get("project_id")),
                project_status,
                _integer(job_id),
            ),
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
        "recovery_kind": recovery_kind,
        "jobs_created": 0,
        "outboxes_created": 0,
        "provider_calls": 0,
        "wallet_mutations": 0,
    }
