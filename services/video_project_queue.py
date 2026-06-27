"""SQLite-backed video project state machine and worker queue.

This module is intentionally provider-free. It stores planning state, creates a
persistent render job after final confirmation, and lets a worker claim jobs
atomically from SQLite.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable


PROJECT_STATUSES = (
    "draft_planning",
    "draft_assets",
    "draft_prompt",
    "draft_addons",
    "draft_quality",
    "draft_scene_count",
    "draft_invoice",
    "queued_for_worker",
    "processing",
    "completed",
    "failed",
    "cancelled",
)
PROJECT_DRAFT_STATUSES = tuple(status for status in PROJECT_STATUSES if status.startswith("draft_"))
SCENE_STATUSES = ("pending", "gen_audio", "gen_image", "gen_video", "postprocess", "done", "failed")
JOB_STATUSES = ("queued", "processing", "completed", "failed", "cancelled")
VIDEO_RENDER_JOB_TYPE = "video_render"


def now_text(moment: datetime | None = None) -> str:
    return (moment or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, separators=(",", ":"))


def _json_loads(value: str | None, fallback: Any = None) -> Any:
    if not value:
        return {} if fallback is None else fallback
    try:
        return json.loads(value)
    except Exception:
        return {} if fallback is None else fallback


def _columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _add_column_if_missing(conn: sqlite3.Connection, table_name: str, column_name: str, column_sql: str) -> None:
    if column_name not in _columns(conn, table_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")


def ensure_video_project_queue_schema(conn: sqlite3.Connection) -> None:
    """Create/adapt queue tables without dropping or deleting existing data."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS video_projects (
            project_id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_uuid TEXT UNIQUE,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft_planning',
            profile_id TEXT,
            topic TEXT,
            ratio TEXT DEFAULT '9:16',
            selected_suggestion_json TEXT,
            asset_pack_json TEXT,
            story_bible_json TEXT,
            scene_cards_json TEXT,
            prompt_text TEXT,
            addon_plan_json TEXT,
            quality_tier INTEGER DEFAULT 200,
            scene_count INTEGER DEFAULT 1,
            addons_disabled_by_package INTEGER DEFAULT 0,
            invoice_json TEXT,
            total_xu_estimated INTEGER DEFAULT 0,
            is_confirmed INTEGER DEFAULT 0,
            job_id INTEGER,
            final_video_file_id TEXT,
            final_video_path TEXT,
            error_log TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            confirmed_at DATETIME,
            completed_at DATETIME,
            cancelled_at DATETIME
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS video_scenes (
            scene_id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            scene_index INTEGER NOT NULL,
            role TEXT,
            script_text TEXT DEFAULT '',
            subtitle_line TEXT DEFAULT '',
            image_prompt TEXT DEFAULT '',
            video_prompt TEXT DEFAULT '',
            reference_asset_ids_json TEXT,
            image_file_path TEXT DEFAULT '',
            audio_file_path TEXT DEFAULT '',
            video_file_path TEXT DEFAULT '',
            scene_status TEXT DEFAULT 'pending',
            UNIQUE(project_id, scene_index)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS video_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            user_id INTEGER,
            job_type TEXT NOT NULL DEFAULT 'video_render',
            status TEXT NOT NULL DEFAULT 'queued',
            priority INTEGER DEFAULT 100,
            attempts INTEGER DEFAULT 0,
            max_attempts INTEGER DEFAULT 3,
            locked_by TEXT,
            locked_at DATETIME,
            lease_expires_at DATETIME,
            last_error TEXT,
            result_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            started_at DATETIME,
            completed_at DATETIME
        )"""
    )
    for column_name, column_sql in [
        ("project_uuid", "project_uuid TEXT"),
        ("profile_id", "profile_id TEXT"),
        ("topic", "topic TEXT"),
        ("ratio", "ratio TEXT DEFAULT '9:16'"),
        ("selected_suggestion_json", "selected_suggestion_json TEXT"),
        ("asset_pack_json", "asset_pack_json TEXT"),
        ("story_bible_json", "story_bible_json TEXT"),
        ("scene_cards_json", "scene_cards_json TEXT"),
        ("prompt_text", "prompt_text TEXT"),
        ("addon_plan_json", "addon_plan_json TEXT"),
        ("quality_tier", "quality_tier INTEGER DEFAULT 200"),
        ("scene_count", "scene_count INTEGER DEFAULT 1"),
        ("addons_disabled_by_package", "addons_disabled_by_package INTEGER DEFAULT 0"),
        ("invoice_json", "invoice_json TEXT"),
        ("total_xu_estimated", "total_xu_estimated INTEGER DEFAULT 0"),
        ("is_confirmed", "is_confirmed INTEGER DEFAULT 0"),
        ("job_id", "job_id INTEGER"),
        ("final_video_file_id", "final_video_file_id TEXT"),
        ("final_video_path", "final_video_path TEXT"),
        ("error_log", "error_log TEXT"),
        ("updated_at", "updated_at DATETIME"),
        ("confirmed_at", "confirmed_at DATETIME"),
        ("completed_at", "completed_at DATETIME"),
        ("cancelled_at", "cancelled_at DATETIME"),
    ]:
        _add_column_if_missing(conn, "video_projects", column_name, column_sql)
    for column_name, column_sql in [
        ("role", "role TEXT"),
        ("script_text", "script_text TEXT DEFAULT ''"),
        ("subtitle_line", "subtitle_line TEXT DEFAULT ''"),
        ("image_prompt", "image_prompt TEXT DEFAULT ''"),
        ("video_prompt", "video_prompt TEXT DEFAULT ''"),
        ("reference_asset_ids_json", "reference_asset_ids_json TEXT"),
        ("image_file_path", "image_file_path TEXT DEFAULT ''"),
        ("audio_file_path", "audio_file_path TEXT DEFAULT ''"),
        ("video_file_path", "video_file_path TEXT DEFAULT ''"),
        ("scene_status", "scene_status TEXT DEFAULT 'pending'"),
    ]:
        _add_column_if_missing(conn, "video_scenes", column_name, column_sql)
    for column_name, column_sql in [
        ("project_id", "project_id INTEGER"),
        ("user_id", "user_id INTEGER"),
        ("job_type", "job_type TEXT DEFAULT 'video_render'"),
        ("priority", "priority INTEGER DEFAULT 100"),
        ("attempts", "attempts INTEGER DEFAULT 0"),
        ("max_attempts", "max_attempts INTEGER DEFAULT 3"),
        ("locked_by", "locked_by TEXT"),
        ("locked_at", "locked_at DATETIME"),
        ("lease_expires_at", "lease_expires_at DATETIME"),
        ("last_error", "last_error TEXT"),
        ("result_json", "result_json TEXT"),
        ("updated_at", "updated_at DATETIME"),
        ("started_at", "started_at DATETIME"),
        ("completed_at", "completed_at DATETIME"),
    ]:
        _add_column_if_missing(conn, "video_jobs", column_name, column_sql)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_projects_user_status ON video_projects(user_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_projects_project_uuid ON video_projects(project_uuid)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_scenes_project ON video_scenes(project_id, scene_index)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_jobs_status_priority ON video_jobs(status, priority, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_jobs_project ON video_jobs(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_jobs_user ON video_jobs(user_id)")
    conn.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_video_jobs_active_render_project
           ON video_jobs(project_id, job_type)
           WHERE project_id IS NOT NULL
             AND job_type='video_render'
             AND status IN ('queued','processing')"""
    )
    conn.commit()


def _project_from_row(row: sqlite3.Row | tuple | None) -> dict[str, Any]:
    if not row:
        return {}
    keys = [
        "project_id",
        "project_uuid",
        "user_id",
        "status",
        "profile_id",
        "topic",
        "ratio",
        "selected_suggestion_json",
        "asset_pack_json",
        "story_bible_json",
        "scene_cards_json",
        "prompt_text",
        "addon_plan_json",
        "quality_tier",
        "scene_count",
        "addons_disabled_by_package",
        "invoice_json",
        "total_xu_estimated",
        "is_confirmed",
        "job_id",
        "final_video_file_id",
        "final_video_path",
        "error_log",
        "created_at",
        "updated_at",
        "confirmed_at",
        "completed_at",
        "cancelled_at",
    ]
    return {key: row[idx] for idx, key in enumerate(keys) if idx < len(row)}


def _scene_from_row(row: sqlite3.Row | tuple | None) -> dict[str, Any]:
    if not row:
        return {}
    keys = [
        "scene_id",
        "project_id",
        "scene_index",
        "role",
        "script_text",
        "subtitle_line",
        "image_prompt",
        "video_prompt",
        "reference_asset_ids_json",
        "image_file_path",
        "audio_file_path",
        "video_file_path",
        "scene_status",
    ]
    return {key: row[idx] for idx, key in enumerate(keys) if idx < len(row)}


def _job_from_row(row: sqlite3.Row | tuple | None) -> dict[str, Any]:
    if not row:
        return {}
    keys = [
        "id",
        "project_id",
        "user_id",
        "job_type",
        "status",
        "priority",
        "attempts",
        "max_attempts",
        "locked_by",
        "locked_at",
        "lease_expires_at",
        "last_error",
        "result_json",
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
    ]
    data = {key: row[idx] for idx, key in enumerate(keys) if idx < len(row)}
    data["job_id"] = data.get("id")
    return data


def get_video_project(conn: sqlite3.Connection, project_id: int | None = None, project_uuid: str = "") -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    if project_id:
        row = conn.execute(
            """SELECT project_id,project_uuid,user_id,status,profile_id,topic,ratio,selected_suggestion_json,
                      asset_pack_json,story_bible_json,scene_cards_json,prompt_text,addon_plan_json,
                      quality_tier,scene_count,addons_disabled_by_package,invoice_json,total_xu_estimated,
                      is_confirmed,job_id,final_video_file_id,final_video_path,error_log,created_at,updated_at,
                      confirmed_at,completed_at,cancelled_at
               FROM video_projects WHERE project_id=?""",
            (int(project_id),),
        ).fetchone()
        return _project_from_row(row)
    if project_uuid:
        row = conn.execute(
            """SELECT project_id,project_uuid,user_id,status,profile_id,topic,ratio,selected_suggestion_json,
                      asset_pack_json,story_bible_json,scene_cards_json,prompt_text,addon_plan_json,
                      quality_tier,scene_count,addons_disabled_by_package,invoice_json,total_xu_estimated,
                      is_confirmed,job_id,final_video_file_id,final_video_path,error_log,created_at,updated_at,
                      confirmed_at,completed_at,cancelled_at
               FROM video_projects WHERE project_uuid=?""",
            (str(project_uuid),),
        ).fetchone()
        return _project_from_row(row)
    return {}


def create_video_project(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    profile_id: str = "storytelling",
    topic: str = "",
    ratio: str = "9:16",
    selected_suggestion: dict | None = None,
    asset_pack: dict | None = None,
) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    project_uuid = f"vprj_{uuid.uuid4().hex}"
    now = now_text()
    cursor = conn.execute(
        """INSERT INTO video_projects
           (project_uuid,user_id,status,profile_id,topic,ratio,selected_suggestion_json,asset_pack_json,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            project_uuid,
            int(user_id),
            "draft_planning",
            str(profile_id or "storytelling"),
            str(topic or ""),
            str(ratio or "9:16"),
            _json_dumps(selected_suggestion or {}),
            _json_dumps(asset_pack or {}),
            now,
            now,
        ),
    )
    conn.commit()
    return get_video_project(conn, int(cursor.lastrowid))


PROJECT_UPDATE_FIELDS = {
    "status",
    "profile_id",
    "topic",
    "ratio",
    "selected_suggestion_json",
    "asset_pack_json",
    "story_bible_json",
    "scene_cards_json",
    "prompt_text",
    "addon_plan_json",
    "quality_tier",
    "scene_count",
    "addons_disabled_by_package",
    "invoice_json",
    "total_xu_estimated",
    "is_confirmed",
    "job_id",
    "final_video_file_id",
    "final_video_path",
    "error_log",
    "confirmed_at",
    "completed_at",
    "cancelled_at",
}


def update_video_project(conn: sqlite3.Connection, project_id: int, **fields: Any) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    updates = []
    values: list[Any] = []
    for key, value in fields.items():
        if key not in PROJECT_UPDATE_FIELDS:
            continue
        if key == "status" and value not in PROJECT_STATUSES:
            raise ValueError("invalid_project_status")
        if key.endswith("_json") and not isinstance(value, str):
            value = _json_dumps(value)
        updates.append(f"{key}=?")
        values.append(value)
    updates.append("updated_at=?")
    values.append(now_text())
    values.append(int(project_id))
    conn.execute(f"UPDATE video_projects SET {', '.join(updates)} WHERE project_id=?", values)
    conn.commit()
    return get_video_project(conn, int(project_id))


def advance_video_project_state(conn: sqlite3.Connection, project_id: int, next_status: str, *, strict: bool = True) -> dict[str, Any]:
    project = get_video_project(conn, int(project_id))
    if not project:
        raise ValueError("project_not_found")
    if next_status not in PROJECT_STATUSES:
        raise ValueError("invalid_project_status")
    current = str(project.get("status") or "draft_planning")
    current_index = PROJECT_STATUSES.index(current)
    next_index = PROJECT_STATUSES.index(next_status)
    if strict and next_index != current_index + 1:
        raise ValueError("invalid_project_state_transition")
    if not strict and next_index < current_index and next_status != "cancelled":
        raise ValueError("invalid_project_state_transition")
    return update_video_project(conn, int(project_id), status=next_status)


def handle_video_project_text(conn: sqlite3.Connection, project_id: int, text: str) -> dict[str, Any]:
    project = get_video_project(conn, int(project_id))
    if not project:
        raise ValueError("project_not_found")
    if str(project.get("status") or "") != "draft_prompt":
        return {"ok": False, "changed": False, "project": project}
    updated = update_video_project(conn, int(project_id), prompt_text=str(text or "")[:8000])
    return {"ok": True, "changed": True, "project": updated}


def get_active_video_project(conn: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    row = conn.execute(
        """SELECT project_id,project_uuid,user_id,status,profile_id,topic,ratio,selected_suggestion_json,
                  asset_pack_json,story_bible_json,scene_cards_json,prompt_text,addon_plan_json,
                  quality_tier,scene_count,addons_disabled_by_package,invoice_json,total_xu_estimated,
                  is_confirmed,job_id,final_video_file_id,final_video_path,error_log,created_at,updated_at,
                  confirmed_at,completed_at,cancelled_at
           FROM video_projects
           WHERE user_id=? AND status IN ('draft_planning','draft_assets','draft_prompt','draft_addons','draft_quality','draft_scene_count','draft_invoice','queued_for_worker','processing')
           ORDER BY project_id DESC
           LIMIT 1""",
        (int(user_id),),
    ).fetchone()
    return _project_from_row(row)


def menu_main_keeps_video_draft(conn: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    return {"ok": True, "active_project": get_active_video_project(conn, int(user_id)), "deleted": False}


def save_video_project_storyboard(conn: sqlite3.Connection, project_id: int, storyboard: Any) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    data = storyboard.to_dict() if hasattr(storyboard, "to_dict") else dict(storyboard or {})
    bible = data.get("story_bible") or {}
    cards = list(data.get("scene_cards") or [])
    conn.execute("DELETE FROM video_scenes WHERE project_id=?", (int(project_id),))
    for index, card in enumerate(cards, start=1):
        conn.execute(
            """INSERT OR REPLACE INTO video_scenes
               (project_id,scene_index,role,script_text,subtitle_line,image_prompt,video_prompt,reference_asset_ids_json,scene_status)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                int(project_id),
                int(card.get("scene_index") or index),
                str(card.get("role") or ""),
                str(card.get("narration_line") or card.get("script_text") or ""),
                str(card.get("subtitle_line") or ""),
                str(card.get("image_prompt") or card.get("visual_goal") or ""),
                str(card.get("provider_prompt") or card.get("video_prompt") or ""),
                _json_dumps(card.get("reference_asset_ids") or []),
                "pending",
            ),
        )
    return update_video_project(
        conn,
        int(project_id),
        story_bible_json=bible,
        scene_cards_json=cards,
        scene_count=max(1, len(cards)),
    )


def list_video_project_scenes(conn: sqlite3.Connection, project_id: int) -> list[dict[str, Any]]:
    ensure_video_project_queue_schema(conn)
    rows = conn.execute(
        """SELECT scene_id,project_id,scene_index,role,script_text,subtitle_line,image_prompt,video_prompt,
                  reference_asset_ids_json,image_file_path,audio_file_path,video_file_path,scene_status
           FROM video_scenes WHERE project_id=? ORDER BY scene_index ASC""",
        (int(project_id),),
    ).fetchall()
    return [_scene_from_row(row) for row in rows]


def get_active_video_render_job(conn: sqlite3.Connection, project_id: int) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    row = conn.execute(
        """SELECT id,project_id,user_id,job_type,status,priority,attempts,max_attempts,locked_by,locked_at,
                  lease_expires_at,last_error,result_json,created_at,updated_at,started_at,completed_at
           FROM video_jobs
           WHERE project_id=? AND job_type=? AND status IN ('queued','processing')
           ORDER BY id ASC LIMIT 1""",
        (int(project_id), VIDEO_RENDER_JOB_TYPE),
    ).fetchone()
    return _job_from_row(row)


def get_video_render_job(conn: sqlite3.Connection, job_id: int) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    row = conn.execute(
        """SELECT id,project_id,user_id,job_type,status,priority,attempts,max_attempts,locked_by,locked_at,
                  lease_expires_at,last_error,result_json,created_at,updated_at,started_at,completed_at
           FROM video_jobs WHERE id=?""",
        (int(job_id),),
    ).fetchone()
    return _job_from_row(row)


def enqueue_video_render_job(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    user_id: int,
    priority: int = 100,
    max_attempts: int = 3,
) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    active = get_active_video_render_job(conn, int(project_id))
    if active:
        return {**active, "duplicate_prevented": True}
    now = now_text()
    try:
        cursor = conn.execute(
            """INSERT INTO video_jobs
               (project_id,user_id,job_type,status,priority,attempts,max_attempts,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (int(project_id), int(user_id), VIDEO_RENDER_JOB_TYPE, "queued", int(priority), 0, int(max_attempts), now, now),
        )
        conn.commit()
        job = get_video_render_job(conn, int(cursor.lastrowid))
        return {**job, "duplicate_prevented": False}
    except sqlite3.IntegrityError:
        conn.rollback()
        active = get_active_video_render_job(conn, int(project_id))
        if active:
            return {**active, "duplicate_prevented": True}
        raise


def confirm_video_project_invoice(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    user_id: int,
    balance_xu: int | None = None,
    deduct_func: Callable[[int, int], Any] | None = None,
) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    project = get_video_project(conn, int(project_id))
    if not project:
        return {"ok": False, "reason": "project_not_found"}
    if int(project.get("user_id") or 0) != int(user_id):
        return {"ok": False, "reason": "project_user_mismatch"}
    if str(project.get("status") or "") not in {"draft_invoice", "queued_for_worker"}:
        return {"ok": False, "reason": "project_not_at_invoice"}
    active = get_active_video_render_job(conn, int(project_id))
    if active:
        return {"ok": True, "project": project, "job": active, "duplicate_prevented": True}
    total_xu = int(project.get("total_xu_estimated") or 0)
    if total_xu <= 0:
        invoice = _json_loads(str(project.get("invoice_json") or ""), {})
        total_xu = int(invoice.get("total_xu") or invoice.get("total") or 0)
    if balance_xu is not None and int(balance_xu) < total_xu:
        return {"ok": False, "reason": "insufficient_balance", "required_xu": total_xu}
    if deduct_func is not None:
        charge = deduct_func(int(user_id), total_xu)
        if isinstance(charge, dict) and not charge.get("ok", True):
            return {"ok": False, "reason": "deduct_failed", "charge": charge}
        if charge is False:
            return {"ok": False, "reason": "deduct_failed", "charge": charge}
    confirmed_at = now_text()
    update_video_project(
        conn,
        int(project_id),
        status="queued_for_worker",
        is_confirmed=1,
        confirmed_at=confirmed_at,
    )
    job = enqueue_video_render_job(conn, project_id=int(project_id), user_id=int(user_id))
    update_video_project(conn, int(project_id), job_id=int(job.get("id") or 0))
    return {"ok": True, "project": get_video_project(conn, int(project_id)), "job": job, "duplicate_prevented": bool(job.get("duplicate_prevented"))}


def requeue_stale_video_jobs(conn: sqlite3.Connection, *, now: datetime | None = None) -> int:
    ensure_video_project_queue_schema(conn)
    current = now_text(now)
    cursor = conn.execute(
        """UPDATE video_jobs
           SET status='queued', locked_by='', locked_at=NULL, lease_expires_at=NULL, updated_at=?, last_error='lease_expired_requeued'
           WHERE job_type=? AND status='processing'
             AND lease_expires_at IS NOT NULL
             AND lease_expires_at < ?
             AND COALESCE(attempts,0) < COALESCE(max_attempts,3)""",
        (current, VIDEO_RENDER_JOB_TYPE, current),
    )
    conn.commit()
    return int(cursor.rowcount or 0)


def claim_next_video_job(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    lease_seconds: int = 600,
    now: datetime | None = None,
) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    requeue_stale_video_jobs(conn, now=now)
    current_dt = now or datetime.now()
    current = now_text(current_dt)
    lease_expires = now_text(current_dt + timedelta(seconds=max(30, int(lease_seconds or 600))))
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """SELECT id,project_id,user_id,job_type,status,priority,attempts,max_attempts,locked_by,locked_at,
                      lease_expires_at,last_error,result_json,created_at,updated_at,started_at,completed_at
               FROM video_jobs
               WHERE job_type=? AND status='queued'
               ORDER BY priority ASC, created_at ASC, id ASC
               LIMIT 1""",
            (VIDEO_RENDER_JOB_TYPE,),
        ).fetchone()
        if not row:
            conn.commit()
            return {}
        job = _job_from_row(row)
        cursor = conn.execute(
            """UPDATE video_jobs
               SET status='processing', attempts=COALESCE(attempts,0)+1, locked_by=?, locked_at=?,
                   lease_expires_at=?, started_at=COALESCE(started_at, ?), updated_at=?
               WHERE id=? AND status='queued'""",
            (str(worker_id or "local_worker")[:120], current, lease_expires, current, current, int(job["id"])),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return {}
        conn.execute("UPDATE video_projects SET status='processing', updated_at=? WHERE project_id=?", (current, int(job["project_id"])))
        conn.commit()
        return get_video_render_job(conn, int(job["id"]))
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


def video_worker_poll_queued_job(conn: sqlite3.Connection, worker_id: str = "local_worker") -> dict[str, Any]:
    return claim_next_video_job(conn, worker_id=worker_id)


def complete_video_job(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    final_video_path: str = "",
    final_video_file_id: str = "",
    result: dict | None = None,
) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    job = get_video_render_job(conn, int(job_id))
    if not job:
        return {"ok": False, "reason": "job_not_found"}
    current = now_text()
    payload = dict(result or {})
    if final_video_path:
        payload["final_video_path"] = final_video_path
    if final_video_file_id:
        payload["final_video_file_id"] = final_video_file_id
    conn.execute(
        """UPDATE video_jobs
           SET status='completed', result_json=?, completed_at=?, updated_at=?, lease_expires_at=NULL
           WHERE id=?""",
        (_json_dumps(payload), current, current, int(job_id)),
    )
    conn.execute(
        """UPDATE video_projects
           SET status='completed', final_video_path=?, final_video_file_id=?, completed_at=?, updated_at=?
           WHERE project_id=?""",
        (str(final_video_path or ""), str(final_video_file_id or ""), current, current, int(job["project_id"])),
    )
    conn.commit()
    return {"ok": True, "job": get_video_render_job(conn, int(job_id)), "project": get_video_project(conn, int(job["project_id"]))}


def fail_video_job(conn: sqlite3.Connection, *, job_id: int, error: str, retry: bool = True) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    job = get_video_render_job(conn, int(job_id))
    if not job:
        return {"ok": False, "reason": "job_not_found"}
    attempts = int(job.get("attempts") or 0)
    max_attempts = int(job.get("max_attempts") or 3)
    current = now_text()
    if retry and attempts < max_attempts:
        conn.execute(
            """UPDATE video_jobs
               SET status='queued', locked_by='', locked_at=NULL, lease_expires_at=NULL,
                   last_error=?, updated_at=?
               WHERE id=?""",
            (str(error or "")[:1000], current, int(job_id)),
        )
        conn.execute("UPDATE video_projects SET status='queued_for_worker', error_log=?, updated_at=? WHERE project_id=?", (str(error or "")[:2000], current, int(job["project_id"])))
        final_status = "queued"
    else:
        conn.execute(
            """UPDATE video_jobs
               SET status='failed', locked_by='', locked_at=NULL, lease_expires_at=NULL,
                   last_error=?, completed_at=?, updated_at=?
               WHERE id=?""",
            (str(error or "")[:1000], current, current, int(job_id)),
        )
        conn.execute("UPDATE video_projects SET status='failed', error_log=?, updated_at=? WHERE project_id=?", (str(error or "")[:2000], current, int(job["project_id"])))
        final_status = "failed"
    conn.commit()
    return {"ok": True, "status": final_status, "job": get_video_render_job(conn, int(job_id)), "project": get_video_project(conn, int(job["project_id"]))}


def process_claimed_video_job(
    conn: sqlite3.Connection,
    job: dict[str, Any],
    runner: Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any]],
) -> dict[str, Any]:
    project = get_video_project(conn, int(job.get("project_id") or 0))
    scenes = list_video_project_scenes(conn, int(job.get("project_id") or 0))
    try:
        result = runner(project, scenes)
        if not result or not result.get("ok"):
            raise RuntimeError(str((result or {}).get("error") or "video_render_failed"))
        return complete_video_job(
            conn,
            job_id=int(job.get("id") or job.get("job_id")),
            final_video_path=str(result.get("final_video_path") or ""),
            final_video_file_id=str(result.get("final_video_file_id") or ""),
            result=result,
        )
    except Exception as exc:
        return fail_video_job(conn, job_id=int(job.get("id") or job.get("job_id")), error=f"{type(exc).__name__}:{exc}")


def hydrate_video_job_payload(conn: sqlite3.Connection, job: dict[str, Any]) -> dict[str, Any]:
    if not job:
        return {}
    project_id = int(job.get("project_id") or 0)
    return {
        **job,
        "project": get_video_project(conn, project_id),
        "scenes": list_video_project_scenes(conn, project_id),
    }
