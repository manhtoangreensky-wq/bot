from __future__ import annotations

import hashlib
import json
import sqlite3

from services import product_video_owner_recovery
from services import video_uiflow3_execution_contract


USER_ID = 3901
PRE_SUBMIT_ERROR = "RuntimeError:uiflow3_approved_snapshot_hash_mismatch"


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
                PRE_SUBMIT_ERROR,
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
    job_id = int(
        conn.execute(
            """INSERT INTO video_jobs
               (project_id,user_id,job_type,status,attempts,max_attempts,last_error,
                result_json,progress_percent,progress_message,completed_at)
               VALUES (?,?,'video_render','failed',1,3,?,?,10,'scene_dispatch_claimed',CURRENT_TIMESTAMP)""",
            (project_id, USER_ID, PRE_SUBMIT_ERROR, json.dumps(result)),
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
           VALUES (?,?,?,'acknowledged',1,'vps-toanaas-01',CURRENT_TIMESTAMP)""",
        (job_id, project_id, "[1,2]"),
    )
    conn.commit()
    worker_payload = {
        "job_id": str(job_id),
        "project_id": str(project_id),
        "user_id": str(USER_ID),
        "asset_pack": asset_pack,
        **identity,
    }
    return conn, job_id, worker_payload


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
