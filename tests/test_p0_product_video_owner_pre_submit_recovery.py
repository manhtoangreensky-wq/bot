from __future__ import annotations

import hashlib
import json
import sqlite3

from services import product_video_owner_recovery
from services import video_uiflow3_execution_contract


USER_ID = 3901
PRE_SUBMIT_ERROR = "RuntimeError:uiflow3_approved_snapshot_hash_mismatch"
ADDON_SUBTITLE_ERROR = "RuntimeError:addon_material_missing:subtitle"
POST_POLL_FINALIZER_ERROR = "RuntimeError:provider_render_failed:RuntimeError"


def _hash_bound_snapshot() -> dict:
    snapshot = {
        "draft_id": "snapshot-owner-recovery",
        "format": {"ratio": "9:16", "scene_count": 2},
        "scenes": [{"scene_id": "scene_01"}, {"scene_id": "scene_02"}],
        "side_effects": {
            "provider_calls": 0,
            "jobs_created": 0,
            "wallet_mutations": 0,
        },
    }
    encoded = json.dumps(
        snapshot,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    snapshot["config_hash"] = hashlib.sha256(encoded).hexdigest()
    return snapshot


def _failed_pre_submit_job(
    tmp_path,
    *,
    sqlite_rows: bool = True,
    error: str = PRE_SUBMIT_ERROR,
    attempts: int = 1,
    outbox_attempts: int = 1,
    result_updates: dict | None = None,
    worker_compatibility: dict | None = None,
) -> tuple[sqlite3.Connection, int, dict]:
    conn = sqlite3.connect(tmp_path / "uiflow3-owner-recovery.db")
    if sqlite_rows:
        conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE video_projects (
            project_id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_uuid TEXT,
            user_id INTEGER,
            status TEXT,
            profile_id TEXT,
            topic TEXT,
            ratio TEXT,
            asset_pack_json TEXT,
            scene_count INTEGER,
            is_confirmed INTEGER,
            job_id INTEGER,
            video_terminal_state TEXT,
            video_terminal_locked_at TEXT,
            error_log TEXT,
            completed_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE video_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            user_id INTEGER,
            job_type TEXT,
            status TEXT,
            attempts INTEGER,
            max_attempts INTEGER,
            locked_by TEXT,
            locked_at TEXT,
            lease_expires_at TEXT,
            last_error TEXT,
            result_json TEXT,
            progress_percent INTEGER,
            progress_message TEXT,
            completed_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE video_dispatch_outbox (
            outbox_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            project_id INTEGER,
            scene_indexes_json TEXT,
            dispatch_status TEXT,
            attempt_count INTEGER,
            lease_owner TEXT,
            acknowledged_at TEXT
        );
        CREATE TABLE video_scenes (
            scene_id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            scene_index INTEGER,
            scene_status TEXT
        );
        """
    )
    snapshot = _hash_bound_snapshot()
    identity = {
        "uiflow3_bridge_version": video_uiflow3_execution_contract.BRIDGE_VERSION,
        "uiflow3_draft_id": snapshot["draft_id"],
        "uiflow3_owner_user_id": USER_ID,
        "uiflow3_owner_chat_id": USER_ID,
        "uiflow3_snapshot_config_hash": snapshot["config_hash"],
        "uiflow3_handoff_sha256": "b" * 64,
        "uiflow3_quote_sha256": "c" * 64,
        "uiflow3_route_selection_sha256": "d" * 64,
    }
    asset_pack = {
        "source": "product_video",
        "product_video": True,
        "public_user": True,
        "provider_call": True,
        "public_product_type": "video_ai_prompt",
        "product_type": "video_ai_prompt",
        "aspect_ratio": "9:16",
        "output_geometry": {"width": 1080, "height": 1920},
        "uiflow3_approved_snapshot": snapshot,
        "route_selection": {"route_selection_sha256": "d" * 64},
        **identity,
    }
    project_id = int(
        conn.execute(
            """INSERT INTO video_projects
               (project_uuid,user_id,status,profile_id,topic,ratio,asset_pack_json,
                scene_count,is_confirmed,video_terminal_state,error_log)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "vprj-owner-recovery",
                USER_ID,
                "failed",
                "video_ai_prompt",
                "Owner recovery",
                "9:16",
                json.dumps(asset_pack),
                2,
                1,
                "failed_no_charge",
                error,
            ),
        ).lastrowid
    )
    result = {
        **identity,
        "scene_count": 2,
        "submit_source": "public_user_final_confirm",
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "provider_submit_called": False,
        "provider_http_request_sent": False,
        "provider_task_id": None,
        "provider_task_ids": [],
        "submit_count": 0,
        "charge_count": 0,
        "charged_xu": 0,
        "wallet_charge_recorded": False,
        "terminal_state": "failed_no_charge",
        "final_decision": "failed_no_charge",
        "automatic_retry_allowed": False,
    }
    result.update(result_updates or {})
    job_id = int(
        conn.execute(
            """INSERT INTO video_jobs
               (project_id,user_id,job_type,status,attempts,max_attempts,last_error,
                result_json,progress_percent,progress_message,completed_at)
               VALUES (?,?,'video_render','failed',?,3,?,?,10,'scene_dispatch_claimed',CURRENT_TIMESTAMP)""",
            (project_id, USER_ID, attempts, error, json.dumps(result)),
        ).lastrowid
    )
    conn.execute(
        "UPDATE video_projects SET job_id=? WHERE project_id=?",
        (job_id, project_id),
    )
    conn.executemany(
        "INSERT INTO video_scenes (project_id,scene_index,scene_status) VALUES (?,?,'pending')",
        [(project_id, 1), (project_id, 2)],
    )
    conn.execute(
        """INSERT INTO video_dispatch_outbox
           (job_id,project_id,scene_indexes_json,dispatch_status,attempt_count,
            lease_owner,acknowledged_at)
           VALUES (?,?,?,'acknowledged',?,'vps-toanaas-01',CURRENT_TIMESTAMP)""",
        (job_id, project_id, "[1,2]", outbox_attempts),
    )
    conn.commit()
    worker_payload = {
        "job_id": str(job_id),
        "project_id": str(project_id),
        "user_id": str(USER_ID),
        "asset_pack": asset_pack,
        "worker_compatibility": dict(worker_compatibility or {}),
        **identity,
    }
    return conn, job_id, worker_payload


def _compatible_worker() -> dict:
    return {
        "compatible": True,
        "block_reason": "",
        "authoritative_worker_generation_id": "owner-product-video-generation-job19",
        "worker_sha": "e" * 40,
    }


def test_owner_recovery_requeues_the_same_pre_submit_job_once(tmp_path) -> None:
    conn, job_id, worker_payload = _failed_pre_submit_job(tmp_path)

    unauthorized = product_video_owner_recovery.recover_product_video_owner_pre_submit_failure(
        conn,
        job_id=job_id,
        worker_payload=worker_payload,
    )
    assert unauthorized["owner_pre_submit_recovered"] is False
    assert unauthorized["owner_pre_submit_recovery_block_reason"] == "owner_authorization_required"
    assert conn.execute(
        "SELECT status FROM video_jobs WHERE id=?",
        (job_id,),
    ).fetchone()[0] == "failed"

    recovered = product_video_owner_recovery.recover_product_video_owner_pre_submit_failure(
        conn,
        job_id=job_id,
        worker_payload=worker_payload,
        owner_authorized=True,
    )

    assert recovered["owner_pre_submit_recovered"] is True
    job = dict(conn.execute("SELECT * FROM video_jobs WHERE id=?", (job_id,)).fetchone())
    project = dict(
        conn.execute(
            "SELECT * FROM video_projects WHERE project_id=?",
            (int(job["project_id"]),),
        ).fetchone()
    )
    outbox = dict(
        conn.execute(
            "SELECT * FROM video_dispatch_outbox WHERE job_id=?",
            (job_id,),
        ).fetchone()
    )
    result = json.loads(job["result_json"])
    assert job["status"] == "queued"
    assert int(job["attempts"]) == 1
    assert project["status"] == "queued_for_worker"
    assert project["video_terminal_state"] == ""
    assert outbox["dispatch_status"] == "acknowledged"
    assert int(outbox["attempt_count"]) == 1
    assert result["provider_submit_called"] is False
    assert int(result["submit_count"]) == 0
    assert int(result["charge_count"]) == 0
    assert int(result["charged_xu"]) == 0
    assert conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox").fetchone()[0] == 1
    repeated = product_video_owner_recovery.recover_product_video_owner_pre_submit_failure(
        conn,
        job_id=job_id,
        worker_payload=worker_payload,
        owner_authorized=True,
    )
    assert repeated["owner_pre_submit_recovered"] is False
    assert repeated["owner_pre_submit_recovery_block_reason"] == "job_not_failed"


def test_owner_recovery_requeues_same_job_after_fixed_subtitle_materialization_once(
    tmp_path,
) -> None:
    conn, job_id, worker_payload = _failed_pre_submit_job(
        tmp_path,
        error=ADDON_SUBTITLE_ERROR,
        attempts=2,
        outbox_attempts=2,
        result_updates={
            "owner_pre_submit_recovery_used": True,
            "owner_pre_submit_recovery_count": 1,
            "owner_pre_submit_recovered_reason": PRE_SUBMIT_ERROR,
        },
        worker_compatibility=_compatible_worker(),
    )

    recovered = product_video_owner_recovery.recover_product_video_owner_pre_submit_failure(
        conn,
        job_id=job_id,
        worker_payload=worker_payload,
        owner_authorized=True,
    )

    assert recovered["owner_pre_submit_recovered"] is True
    assert recovered["recovery_kind"] == "addon_subtitle_materialization"
    job = dict(conn.execute("SELECT * FROM video_jobs WHERE id=?", (job_id,)).fetchone())
    project = dict(
        conn.execute(
            "SELECT * FROM video_projects WHERE project_id=?",
            (int(job["project_id"]),),
        ).fetchone()
    )
    outbox = dict(
        conn.execute(
            "SELECT * FROM video_dispatch_outbox WHERE job_id=?",
            (job_id,),
        ).fetchone()
    )
    result = json.loads(job["result_json"])
    assert job["status"] == "queued"
    assert int(job["attempts"]) == 2
    assert project["status"] == "queued_for_worker"
    assert outbox["dispatch_status"] == "acknowledged"
    assert int(outbox["attempt_count"]) == 2
    assert result["owner_pre_submit_recovery_used"] is True
    assert result["owner_pre_submit_recovered_reason"] == PRE_SUBMIT_ERROR
    assert result["owner_addon_subtitle_recovery_used"] is True
    assert result["owner_addon_subtitle_recovery_count"] == 1
    assert result["owner_addon_subtitle_recovered_reason"] == ADDON_SUBTITLE_ERROR
    assert result["provider_submit_called"] is False
    assert int(result["submit_count"]) == 0
    assert int(result["charge_count"]) == 0
    assert int(result["charged_xu"]) == 0
    assert conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox").fetchone()[0] == 1

    conn.execute(
        "UPDATE video_jobs SET status='failed',last_error=? WHERE id=?",
        (ADDON_SUBTITLE_ERROR, job_id),
    )
    conn.execute(
        "UPDATE video_projects SET status='failed' WHERE project_id=?",
        (int(job["project_id"]),),
    )
    conn.commit()
    repeated = product_video_owner_recovery.recover_product_video_owner_pre_submit_failure(
        conn,
        job_id=job_id,
        worker_payload=worker_payload,
        owner_authorized=True,
    )
    assert repeated["owner_pre_submit_recovered"] is False
    assert (
        repeated["owner_pre_submit_recovery_block_reason"]
        == "addon_subtitle_recovery_already_used"
    )


def test_owner_addon_recovery_clears_stale_existing_task_poll_only_mode(
    tmp_path,
) -> None:
    conn, job_id, worker_payload = _failed_pre_submit_job(
        tmp_path,
        error=ADDON_SUBTITLE_ERROR,
        attempts=2,
        outbox_attempts=2,
        result_updates={
            "owner_pre_submit_recovery_used": True,
            "recovery_existing_tasks_only": True,
            "existing_task_recovery_recovered": True,
            "existing_task_recovery_count": 1,
            "submit_source": "worker_poll_existing_task",
            "provider_submit_source": "worker_poll_existing_task",
            "original_submit_source": "public_user_final_confirm",
            "provider_poll_existing_task": True,
            "provider_submit_block_reason": "existing_task_recovery_read_only",
            "provider_stalled_not_start": True,
            "error": "provider_stalled_not_start",
        },
        worker_compatibility=_compatible_worker(),
    )

    recovered = product_video_owner_recovery.recover_product_video_owner_pre_submit_failure(
        conn,
        job_id=job_id,
        worker_payload=worker_payload,
        owner_authorized=True,
    )

    assert recovered["owner_pre_submit_recovered"] is True
    job = dict(conn.execute("SELECT * FROM video_jobs WHERE id=?", (job_id,)).fetchone())
    result = json.loads(job["result_json"])
    assert result.get("recovery_existing_tasks_only") is False
    assert result.get("provider_poll_existing_task") is False
    assert result["submit_source"] == "public_user_final_confirm"
    assert result["provider_submit_source"] == "public_user_final_confirm"
    assert result["provider_submit_block_reason"] == "owner_recovery_awaiting_worker_revalidation"
    assert result.get("provider_stalled_not_start") is False
    assert result.get("error") == ""
    assert int(job["attempts"]) == 2
    assert conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox").fetchone()[0] == 1


def test_owner_repair_requeues_same_job_after_stale_poll_only_claim_loop(
    tmp_path,
) -> None:
    conn, job_id, worker_payload = _failed_pre_submit_job(
        tmp_path,
        error=ADDON_SUBTITLE_ERROR,
        attempts=2,
        outbox_attempts=2,
        result_updates={
            "owner_pre_submit_recovery_used": True,
            "owner_addon_subtitle_recovery_used": True,
            "owner_addon_subtitle_recovery_count": 1,
            "recovery_existing_tasks_only": True,
            "existing_task_recovery_recovered": True,
            "submit_source": "worker_poll_existing_task",
            "provider_submit_source": "worker_poll_existing_task",
            "original_submit_source": "public_user_final_confirm",
            "provider_poll_existing_task": True,
            "provider_stalled_not_start": True,
            "error": "provider_stalled_not_start",
        },
        worker_compatibility=_compatible_worker(),
    )
    stuck_job = dict(conn.execute("SELECT * FROM video_jobs WHERE id=?", (job_id,)).fetchone())
    stuck_result = json.loads(stuck_job["result_json"])
    conn.execute(
        """UPDATE video_jobs
              SET status='queued',attempts=11,last_error='provider_in_progress',
                  result_json=?,progress_percent=60,progress_message='provider_in_progress'
            WHERE id=?""",
        (json.dumps(stuck_result), job_id),
    )
    conn.execute(
        """UPDATE video_projects
              SET status='processing',video_terminal_state='final_rendering'
            WHERE project_id=?""",
        (int(stuck_job["project_id"]),),
    )
    conn.commit()

    repaired = product_video_owner_recovery.recover_product_video_owner_pre_submit_failure(
        conn,
        job_id=job_id,
        worker_payload=worker_payload,
        owner_authorized=True,
    )

    assert repaired["owner_pre_submit_recovered"] is True
    assert repaired["recovery_kind"] == "addon_subtitle_poll_only_repair"
    job = dict(conn.execute("SELECT * FROM video_jobs WHERE id=?", (job_id,)).fetchone())
    project = dict(
        conn.execute(
            "SELECT * FROM video_projects WHERE project_id=?",
            (int(job["project_id"]),),
        ).fetchone()
    )
    result = json.loads(job["result_json"])
    assert job["status"] == "queued"
    assert int(job["attempts"]) == 2
    assert project["status"] == "queued_for_worker"
    assert project["video_terminal_state"] == ""
    assert result["owner_addon_subtitle_poll_only_repair_used"] is True
    assert result.get("recovery_existing_tasks_only") is False
    assert result.get("provider_poll_existing_task") is False
    assert result["submit_source"] == "public_user_final_confirm"
    assert result["provider_submit_source"] == "public_user_final_confirm"
    assert result["provider_submit_called"] is False
    assert int(result["submit_count"]) == 0
    assert int(result["charged_xu"]) == 0
    assert repaired["jobs_created"] == 0
    assert repaired["outboxes_created"] == 0
    assert repaired["provider_calls"] == 0
    assert repaired["wallet_mutations"] == 0


def test_owner_recovery_requeues_same_job_once_after_post_poll_finalizer_failure(
    tmp_path,
) -> None:
    workspace = tmp_path / "product-video-19-existing-clips"
    workspace.mkdir()
    scene_paths = {
        "1": str(workspace / "provider_scene_001.mp4"),
        "2": str(workspace / "provider_scene_002.mp4"),
    }
    for index, path in scene_paths.items():
        (workspace / f"provider_scene_{int(index):03d}.mp4").write_bytes(
            f"validated-scene-{index}".encode("ascii")
        )
    task_ids_by_scene = {
        "1": ["task_existing_scene_1"],
        "2": ["task_existing_scene_2"],
    }
    manifest_path = workspace / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "job_id": "1",
                "user_id": str(USER_ID),
                "workspace_dir": str(workspace),
                "required_scene_indexes": [1, 2],
                "task_ids_by_scene": task_ids_by_scene,
                "provider_status_by_scene": {
                    "1": "scene_clip_validated",
                    "2": "scene_clip_validated",
                },
                "raw_clip_paths_by_scene": scene_paths,
                "normalized_clip_paths_by_scene": {},
                "scene_order": [1, 2],
                "concat_state": "normalizing",
                "delivery_state": "pending",
                "charge_state": "pending",
                "final_video_path": None,
                "status": "normalizing_scenes",
            }
        ),
        encoding="utf-8",
    )
    conn, job_id, worker_payload = _failed_pre_submit_job(
        tmp_path,
        error=POST_POLL_FINALIZER_ERROR,
        attempts=3107,
        outbox_attempts=3,
        result_updates={
            "recovery_existing_tasks_only": True,
            "existing_task_recovery_recovered": True,
            "submit_source": "worker_poll_existing_task",
            "provider_submit_source": "worker_poll_existing_task",
            "original_submit_source": "public_user_final_confirm",
            "provider_poll_called": True,
            "provider_poll_http_status": 200,
            "provider_submit_called": True,
            "provider_submit_allowed": False,
            "provider_submit_block_reason": "existing_task_recovery_read_only",
            "submit_count": 0,
            "no_new_submit": True,
            "no_new_paid_submit": True,
            "provider_task_ids": ["task_existing_scene_2"],
            "scene_task_map": task_ids_by_scene,
            "result_task_id_by_scene": {
                "1": "task_existing_scene_1",
                "2": "task_existing_scene_2",
            },
            "manifest_path": str(manifest_path),
            "canonical_multiscene_manifest_path": str(manifest_path),
            "canonical_multiscene_workspace": str(workspace),
            "scene_clip_coverage_complete": True,
            "scene_clip_valid_by_index": {"1": True, "2": True},
            "scene_clip_validation_by_index": {
                "1": {"ok": True, "path_present": True, "bytes": 17},
                "2": {"ok": True, "path_present": True, "bytes": 17},
            },
            "valid_scene_clip_count": 2,
            "completed_scene_count": 2,
            "final_mp4_valid": False,
            "final_delivered": False,
            "delivery_succeeded": False,
            "charged_xu": 0,
            "charge_count": 0,
        },
        worker_compatibility=_compatible_worker(),
    )
    before = json.loads(
        conn.execute(
            "SELECT result_json FROM video_jobs WHERE id=?",
            (job_id,),
        ).fetchone()[0]
    )

    recovered = product_video_owner_recovery.recover_product_video_owner_pre_submit_failure(
        conn,
        job_id=job_id,
        worker_payload=worker_payload,
        owner_authorized=True,
    )

    assert recovered["owner_pre_submit_recovered"] is True
    assert recovered["recovery_kind"] == "post_poll_finalizer"
    job = dict(conn.execute("SELECT * FROM video_jobs WHERE id=?", (job_id,)).fetchone())
    project = dict(
        conn.execute(
            "SELECT * FROM video_projects WHERE project_id=?",
            (int(job["project_id"]),),
        ).fetchone()
    )
    outbox = dict(
        conn.execute(
            "SELECT * FROM video_dispatch_outbox WHERE job_id=?",
            (job_id,),
        ).fetchone()
    )
    result = json.loads(job["result_json"])
    assert job["status"] == "queued"
    assert int(job["attempts"]) == 2
    assert project["status"] == "queued_for_worker"
    assert outbox["dispatch_status"] == "acknowledged"
    assert int(outbox["attempt_count"]) == 3
    assert result["owner_post_poll_finalizer_recovery_used"] is True
    assert result["owner_post_poll_finalizer_recovery_count"] == 1
    assert result["recovery_existing_tasks_only"] is True
    assert result["provider_poll_existing_task"] is True
    assert result["poll_existing_task_allowed"] is True
    assert result["no_new_submit"] is True
    assert result["no_new_paid_submit"] is True
    assert result["provider_submit_allowed"] is False
    assert result["provider_submit_block_reason"] == "post_poll_finalizer_recovery_read_only"
    assert result["provider_submit_called"] is before["provider_submit_called"]
    assert result["provider_task_ids"] == before["provider_task_ids"]
    assert result["scene_task_map"] == before["scene_task_map"]
    assert result["result_task_id_by_scene"] == before["result_task_id_by_scene"]
    assert result["manifest_path"] == before["manifest_path"]
    assert int(result["submit_count"]) == 0
    assert int(result["charged_xu"]) == 0
    assert int(result["charge_count"]) == 0
    assert recovered["jobs_created"] == 0
    assert recovered["outboxes_created"] == 0
    assert recovered["provider_calls"] == 0
    assert recovered["wallet_mutations"] == 0
    assert conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox").fetchone()[0] == 1

    conn.execute(
        "UPDATE video_jobs SET status='failed',last_error=? WHERE id=?",
        (POST_POLL_FINALIZER_ERROR, job_id),
    )
    conn.execute(
        "UPDATE video_projects SET status='failed' WHERE project_id=?",
        (int(job["project_id"]),),
    )
    conn.commit()
    repeated = product_video_owner_recovery.recover_product_video_owner_pre_submit_failure(
        conn,
        job_id=job_id,
        worker_payload=worker_payload,
        owner_authorized=True,
    )
    assert repeated["owner_pre_submit_recovered"] is False
    assert (
        repeated["owner_pre_submit_recovery_block_reason"]
        == "post_poll_finalizer_recovery_already_used"
    )


def test_owner_addon_subtitle_recovery_requires_compatible_worker(tmp_path) -> None:
    conn, job_id, worker_payload = _failed_pre_submit_job(
        tmp_path,
        error=ADDON_SUBTITLE_ERROR,
        attempts=2,
        result_updates={"owner_pre_submit_recovery_used": True},
        worker_compatibility={
            "compatible": False,
            "block_reason": "worker_sha_mismatch",
        },
    )

    recovery = product_video_owner_recovery.recover_product_video_owner_pre_submit_failure(
        conn,
        job_id=job_id,
        worker_payload=worker_payload,
        owner_authorized=True,
    )

    assert recovery["owner_pre_submit_recovered"] is False
    assert recovery["owner_pre_submit_recovery_block_reason"] == "worker_sha_mismatch"


def test_owner_addon_subtitle_recovery_rejects_exhausted_attempts(tmp_path) -> None:
    conn, job_id, worker_payload = _failed_pre_submit_job(
        tmp_path,
        error=ADDON_SUBTITLE_ERROR,
        attempts=3,
        result_updates={"owner_pre_submit_recovery_used": True},
        worker_compatibility=_compatible_worker(),
    )

    recovery = product_video_owner_recovery.recover_product_video_owner_pre_submit_failure(
        conn,
        job_id=job_id,
        worker_payload=worker_payload,
        owner_authorized=True,
    )

    assert recovery["owner_pre_submit_recovered"] is False
    assert recovery["owner_pre_submit_recovery_block_reason"] == "job_attempts_exhausted"


def test_owner_recovery_rejects_any_provider_attempt(tmp_path) -> None:
    conn, job_id, worker_payload = _failed_pre_submit_job(tmp_path)
    result = json.loads(
        conn.execute(
            "SELECT result_json FROM video_jobs WHERE id=?",
            (job_id,),
        ).fetchone()[0]
    )
    result["provider_submit_called"] = True
    conn.execute(
        "UPDATE video_jobs SET result_json=? WHERE id=?",
        (json.dumps(result), job_id),
    )
    conn.commit()

    recovery = product_video_owner_recovery.recover_product_video_owner_pre_submit_failure(
        conn,
        job_id=job_id,
        worker_payload=worker_payload,
        owner_authorized=True,
    )

    assert recovery["owner_pre_submit_recovered"] is False
    assert recovery["owner_pre_submit_recovery_block_reason"] == "provider_already_attempted"
    assert conn.execute(
        "SELECT status FROM video_jobs WHERE id=?",
        (job_id,),
    ).fetchone()[0] == "failed"


def test_owner_recovery_accepts_default_sqlite_tuple_rows(tmp_path) -> None:
    conn, job_id, worker_payload = _failed_pre_submit_job(
        tmp_path,
        sqlite_rows=False,
    )

    recovery = product_video_owner_recovery.recover_product_video_owner_pre_submit_failure(
        conn,
        job_id=job_id,
        worker_payload=worker_payload,
        owner_authorized=True,
    )

    assert recovery["owner_pre_submit_recovered"] is True
    assert conn.execute(
        "SELECT status FROM video_jobs WHERE id=?",
        (job_id,),
    ).fetchone()[0] == "queued"
