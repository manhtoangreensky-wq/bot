"""Remote VPS worker API bridge for confirmed video render jobs.

The bridge deliberately exposes a sanitized job contract instead of raw DB rows.
Payment, wallet, PayOS, Telegram webhook ownership, and direct SQLite access
stay on the Railway bot side.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from services import video_project_queue


SECRET_KEY_MARKERS = (
    "token",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "password",
    "checksum",
    "payos",
    "wallet",
)
REMOTE_WORKER_CANARY_JOB_TYPE = "remote_worker_canary"
REMOTE_WORKER_CANARY_SOURCE = "admin_canary"
REMOTE_WORKER_CANARY_CAPABILITY = "canary"
REMOTE_WORKER_ADMIN_CANARY_SOURCE = "admin_prod_canary"
REMOTE_WORKER_ADMIN_CANARY_CAPABILITY = "admin_canary"
REMOTE_WORKER_ADMIN_CANARY_REF_PREFIX = "RW-PROD-CANARY"
REMOTE_WORKER_ADMIN_VIDEO_SOURCE = "admin_video_delivery"
REMOTE_WORKER_ADMIN_VIDEO_CAPABILITY = "admin_video"
REMOTE_WORKER_ADMIN_VIDEO_QUEUE_LABEL = "OWNER/ADMIN TEST MODE — video delivery, không trừ Xu"
REMOTE_WORKER_RENDER_CAPABILITIES = ("ffmpeg", "video_postprocess", "local_render_helpers")
REMOTE_WORKER_CAPABILITIES = (
    *REMOTE_WORKER_RENDER_CAPABILITIES,
    REMOTE_WORKER_CANARY_CAPABILITY,
    REMOTE_WORKER_ADMIN_CANARY_CAPABILITY,
    REMOTE_WORKER_ADMIN_VIDEO_CAPABILITY,
)
REMOTE_WORKER_PRODUCTION_ENABLED_ENV = "REMOTE_WORKER_PRODUCTION_ENABLED"
REMOTE_WORKER_ADMIN_CANARY_ENABLED_ENV = "REMOTE_WORKER_ADMIN_CANARY_ENABLED"
REMOTE_WORKER_PUBLIC_ENABLED_ENV = "REMOTE_WORKER_PUBLIC_ENABLED"
REMOTE_WORKER_MAX_ADMIN_CANARY_ACTIVE_ENV = "REMOTE_WORKER_MAX_ADMIN_CANARY_ACTIVE"
REMOTE_WORKER_ADMIN_CANARY_DEFAULT_DURATION_SECONDS = 3
REMOTE_WORKER_ADMIN_CANARY_QUEUE_LABEL = "OWNER/ADMIN WORKER CANARY — không trừ Xu"


def _json_loads(value: Any, fallback: Any = None) -> Any:
    if value in (None, ""):
        return {} if fallback is None else fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return {} if fallback is None else fallback


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _env_bool(environ: dict[str, str], name: str, default: bool = False) -> bool:
    if name not in environ:
        return bool(default)
    return _safe_bool(environ.get(name))


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, separators=(",", ":"))


def remote_worker_production_guard_config(environ: dict[str, str] | None = None) -> dict:
    env = environ or os.environ
    max_active = _safe_int(env.get(REMOTE_WORKER_MAX_ADMIN_CANARY_ACTIVE_ENV), 1)
    return {
        "production_enabled": _env_bool(env, REMOTE_WORKER_PRODUCTION_ENABLED_ENV, False),
        "admin_canary_enabled": _env_bool(env, REMOTE_WORKER_ADMIN_CANARY_ENABLED_ENV, True),
        "public_enabled": _env_bool(env, REMOTE_WORKER_PUBLIC_ENABLED_ENV, False),
        "max_admin_canary_active": max(1, max_active),
    }


def sanitize_worker_id(worker_id: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.:-]+", "-", str(worker_id or "").strip())
    return (clean or "remote-worker")[:120]


def mask_worker_id(worker_id: str) -> str:
    clean = sanitize_worker_id(worker_id)
    if len(clean) <= 4:
        return clean[:1] + "***"
    return clean[:2] + "***" + clean[-2:]


def sanitize_capabilities(capabilities: list[str] | tuple[str, ...] | None = None) -> list[str]:
    result: list[str] = []
    for item in capabilities or []:
        value = re.sub(r"[^A-Za-z0-9_.:-]+", "-", str(item or "").strip().lower())[:80]
        if value and value not in result:
            result.append(value)
    return result[:20]


def build_worker_ping_payload(
    *,
    worker_id: str,
    capabilities: list[str] | tuple[str, ...] | None = None,
    server_time: str = "",
    build: str = "",
    public_version: str = "",
    worker_api_enabled: bool = True,
    remote_worker_mode_supported: bool = True,
    dry_run: bool = True,
) -> dict:
    return {
        "ok": True,
        "worker_api_enabled": bool(worker_api_enabled),
        "worker_id": sanitize_worker_id(worker_id),
        "server_time": str(server_time or ""),
        "build": str(build or ""),
        "public_version": str(public_version or ""),
        "remote_worker_mode_supported": bool(remote_worker_mode_supported),
        "can_claim_jobs": False,
        "dry_run": bool(dry_run),
        "capabilities": sanitize_capabilities(capabilities),
    }


def strip_secret_fields(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if any(marker in lowered for marker in SECRET_KEY_MARKERS):
                continue
            safe[key_text] = strip_secret_fields(item)
        return safe
    if isinstance(value, list):
        return [strip_secret_fields(item) for item in value]
    return value


def scrub_secret_text(value: Any) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    text = re.sub(r"(?i)(bearer|authorization)\s+[A-Za-z0-9._~+/=-]+", r"\1 <redacted>", text)
    for marker in SECRET_KEY_MARKERS:
        text = re.sub(rf"(?i){re.escape(marker)}[A-Za-z0-9_.:/=+\-]*", f"{marker}=<redacted>", text)
    text = re.sub(r"[A-Za-z0-9_-]{24,}", "<redacted>", text)
    return text[:500]


def is_remote_worker_canary_job(job: dict | None = None, project: dict | None = None) -> bool:
    job = job or {}
    project = project or {}
    if str(job.get("job_type") or "") == REMOTE_WORKER_CANARY_JOB_TYPE:
        return True
    asset_pack = _json_loads(project.get("asset_pack_json"), {})
    return str(asset_pack.get("source") or "") == REMOTE_WORKER_CANARY_SOURCE


def is_remote_worker_admin_canary_job(job: dict | None = None, project: dict | None = None) -> bool:
    job = job or {}
    project = project or {}
    if str(job.get("job_type") or video_project_queue.VIDEO_RENDER_JOB_TYPE) != video_project_queue.VIDEO_RENDER_JOB_TYPE:
        return False
    asset_pack = _json_loads(project.get("asset_pack_json"), {})
    return str(asset_pack.get("source") or "") == REMOTE_WORKER_ADMIN_CANARY_SOURCE and _safe_bool(
        asset_pack.get("worker_admin_canary")
    )


def _canary_safety_flags(project: dict) -> dict:
    asset_pack = _json_loads(project.get("asset_pack_json"), {})
    invoice = _json_loads(project.get("invoice_json"), {})
    return {
        "admin_only": _safe_bool(asset_pack.get("admin_only") or invoice.get("admin_only")),
        "no_charge": _safe_bool(asset_pack.get("no_charge") or invoice.get("no_charge")) or _safe_int(project.get("total_xu_estimated"), 0) == 0,
        "provider_call": _safe_bool(asset_pack.get("provider_call") or invoice.get("provider_call")),
        "public_user": _safe_bool(asset_pack.get("public_user") or invoice.get("public_user")),
        "source": str(asset_pack.get("source") or ""),
    }


def _admin_canary_safety_flags(project: dict) -> dict:
    asset_pack = _json_loads(project.get("asset_pack_json"), {})
    invoice = _json_loads(project.get("invoice_json"), {})
    return {
        "admin_only": _safe_bool(asset_pack.get("admin_only") or invoice.get("admin_only")),
        "no_charge": _safe_bool(asset_pack.get("no_charge") or invoice.get("no_charge")) or _safe_int(project.get("total_xu_estimated"), 0) == 0,
        "provider_call": _safe_bool(asset_pack.get("provider_call") or invoice.get("provider_call")),
        "public_user": _safe_bool(asset_pack.get("public_user") or invoice.get("public_user")),
        "worker_admin_canary": _safe_bool(asset_pack.get("worker_admin_canary") or invoice.get("worker_admin_canary")),
        "created_by_admin": _safe_bool(asset_pack.get("created_by_admin") or invoice.get("created_by_admin") or asset_pack.get("owner")),
        "source": str(asset_pack.get("source") or ""),
        "duration_seconds": max(1, _safe_int(asset_pack.get("duration_seconds") or invoice.get("duration_seconds"), REMOTE_WORKER_ADMIN_CANARY_DEFAULT_DURATION_SECONDS)),
        "scene_count": max(1, _safe_int(asset_pack.get("scene_count") or invoice.get("scene_count"), 1)),
    }


def _admin_video_safety_flags(project: dict) -> dict:
    asset_pack = _json_loads(project.get("asset_pack_json"), {})
    invoice = _json_loads(project.get("invoice_json"), {})
    source = str(asset_pack.get("source") or invoice.get("source") or "")
    return {
        "source": source,
        "admin_video_delivery": _safe_bool(
            asset_pack.get("admin_video_delivery")
            or invoice.get("admin_video_delivery")
            or asset_pack.get("owner_admin_test_mode")
            or invoice.get("owner_admin_test_mode")
            or asset_pack.get("admin_test")
            or invoice.get("admin_test")
        ),
        "admin_only": _safe_bool(
            asset_pack.get("admin_only")
            or invoice.get("admin_only")
            or asset_pack.get("created_by_admin")
            or invoice.get("created_by_admin")
            or asset_pack.get("owner")
        ),
        "created_by_admin": _safe_bool(asset_pack.get("created_by_admin") or invoice.get("created_by_admin") or asset_pack.get("owner")),
        "no_charge": _safe_bool(
            asset_pack.get("no_charge")
            or invoice.get("no_charge")
            or asset_pack.get("admin_no_charge")
            or invoice.get("admin_no_charge")
        ) or _safe_int(project.get("total_xu_estimated"), 0) == 0,
        "provider_call": _safe_bool(asset_pack.get("provider_call") or invoice.get("provider_call")),
        "public_user": _safe_bool(asset_pack.get("public_user") or invoice.get("public_user")),
        "duration_seconds": max(1, _safe_int(asset_pack.get("duration_seconds") or invoice.get("duration_seconds"), 6)),
        "scene_count": max(1, min(20, _safe_int(asset_pack.get("scene_count") or invoice.get("scene_count"), 1))),
    }


def _is_admin_fake_video_job(project: dict) -> bool:
    asset_pack = _json_loads(project.get("asset_pack_json"), {})
    if str(asset_pack.get("source") or "") == "admin_fake_job" and _safe_bool(asset_pack.get("no_charge")):
        return True
    return str(project.get("profile_id") or "") == "remote_worker_api_admin_test" or "ADMIN TEST MODE" in str(project.get("topic") or "")


def _admin_canary_is_safe(project: dict) -> bool:
    flags = _admin_canary_safety_flags(project)
    return bool(
        flags["source"] == REMOTE_WORKER_ADMIN_CANARY_SOURCE
        and flags["worker_admin_canary"]
        and flags["admin_only"]
        and flags["no_charge"]
        and flags["created_by_admin"]
        and not flags["provider_call"]
        and not flags["public_user"]
    )


def is_remote_worker_admin_video_job(job: dict | None = None, project: dict | None = None) -> bool:
    job = job or {}
    project = project or {}
    if str(job.get("job_type") or video_project_queue.VIDEO_RENDER_JOB_TYPE) != video_project_queue.VIDEO_RENDER_JOB_TYPE:
        return False
    if is_remote_worker_admin_canary_job(job, project):
        return False
    flags = _admin_video_safety_flags(project)
    return bool(
        flags["admin_video_delivery"]
        and flags["admin_only"]
        and flags["no_charge"]
        and not flags["provider_call"]
        and not flags["public_user"]
    )


def _admin_video_is_safe(project: dict) -> bool:
    if _is_admin_fake_video_job(project):
        return True
    return is_remote_worker_admin_video_job({"job_type": video_project_queue.VIDEO_RENDER_JOB_TYPE}, project)


def _scene_cards_from_project(project: dict, scenes: list[dict]) -> list[dict]:
    cards = _json_loads(project.get("scene_cards_json"), [])
    if isinstance(cards, list) and cards:
        return strip_secret_fields(cards)
    result = []
    for scene in scenes or []:
        result.append(
            {
                "scene_index": _safe_int(scene.get("scene_index"), len(result) + 1),
                "role": scene.get("role") or "",
                "script_text": scene.get("script_text") or "",
                "subtitle_line": scene.get("subtitle_line") or "",
                "image_prompt": scene.get("image_prompt") or "",
                "video_prompt": scene.get("video_prompt") or "",
                "reference_asset_ids": _json_loads(scene.get("reference_asset_ids_json"), []),
            }
        )
    return strip_secret_fields(result)


def build_worker_job_payload(hydrated_job: dict) -> dict:
    if not hydrated_job:
        return {}
    project = dict(hydrated_job.get("project") or {})
    scenes = list(hydrated_job.get("scenes") or [])
    scene_cards = _scene_cards_from_project(project, scenes)
    asset_pack = strip_secret_fields(_json_loads(project.get("asset_pack_json"), {}))
    addon_plan = strip_secret_fields(_json_loads(project.get("addon_plan_json"), {}))
    quality_source = project.get("quality_tier")
    if quality_source in (None, ""):
        quality_source = hydrated_job.get("quality_tier")
    quality_tier = _safe_int(quality_source, 200)
    scene_count = max(1, _safe_int(project.get("scene_count") or len(scene_cards) or 1, 1))
    ratio = str(project.get("ratio") or "9:16")
    payload = {
        "job_id": str(hydrated_job.get("id") or hydrated_job.get("job_id") or ""),
        "project_id": str(project.get("project_id") or hydrated_job.get("project_id") or ""),
        "user_id": str(project.get("user_id") or hydrated_job.get("user_id") or ""),
        "job_type": str(hydrated_job.get("job_type") or video_project_queue.VIDEO_RENDER_JOB_TYPE),
        "status": str(hydrated_job.get("status") or ""),
        "locked_by": str(hydrated_job.get("locked_by") or ""),
        "lease_expires_at": str(hydrated_job.get("lease_expires_at") or ""),
        "attempts": _safe_int(hydrated_job.get("attempts"), 0),
        "max_attempts": _safe_int(hydrated_job.get("max_attempts"), 3),
        "profile_id": str(project.get("profile_id") or ""),
        "topic": str(project.get("topic") or "")[:500],
        "prompt_text": str(project.get("prompt_text") or "")[:8000],
        "scene_cards": scene_cards,
        "asset_pack": asset_pack,
        "addon_plan": addon_plan,
        "quality_tier": quality_tier,
        "scene_count": scene_count,
        "aspect_ratio": ratio,
        "expected_duration_seconds": max(1, scene_count * 6),
        "output_requirements": {
            "container": "mp4",
            "mime": "video/mp4",
            "aspect_ratio": ratio,
            "quality_tier": quality_tier,
            "scene_count": scene_count,
            "final_video_bytes_gt_zero": True,
        },
    }
    if is_remote_worker_canary_job(hydrated_job, project):
        safety = _canary_safety_flags(project)
        payload.update(
            {
                "canary": True,
                "admin_only": bool(safety["admin_only"]),
                "no_charge": bool(safety["no_charge"]),
                "provider_call": bool(safety["provider_call"]),
                "public_user": bool(safety["public_user"]),
                "source": safety["source"],
                "expected_duration_seconds": 2,
            }
        )
        payload["output_requirements"].update(
            {
                "aspect_ratio": "16:9",
                "canary_mp4": True,
                "duration_seconds_max": 2,
                "resolution": "320x180",
                "provider_call": False,
                "no_charge": True,
            }
        )
    if is_remote_worker_admin_canary_job(hydrated_job, project):
        safety = _admin_canary_safety_flags(project)
        payload.update(
            {
                "admin_canary": True,
                "worker_admin_canary": True,
                "admin_only": bool(safety["admin_only"]),
                "no_charge": bool(safety["no_charge"]),
                "provider_call": bool(safety["provider_call"]),
                "public_user": bool(safety["public_user"]),
                "source": safety["source"],
                "queue_label": REMOTE_WORKER_ADMIN_CANARY_QUEUE_LABEL,
                "expected_duration_seconds": safety["duration_seconds"],
                "scene_count": safety["scene_count"],
            }
        )
        payload["output_requirements"].update(
            {
                "aspect_ratio": "16:9",
                "admin_canary_mp4": True,
                "duration_seconds_max": safety["duration_seconds"],
                "resolution": "320x180",
                "provider_call": False,
                "no_charge": True,
            }
        )
    if is_remote_worker_admin_video_job(hydrated_job, project) or _is_admin_fake_video_job(project):
        safety = _admin_video_safety_flags(project)
        payload.update(
            {
                "admin_video_delivery": True,
                "admin_only": True,
                "no_charge": True,
                "provider_call": False,
                "public_user": False,
                "source": safety["source"] or REMOTE_WORKER_ADMIN_VIDEO_SOURCE,
                "queue_label": REMOTE_WORKER_ADMIN_VIDEO_QUEUE_LABEL,
                "expected_duration_seconds": max(1, min(120, safety["duration_seconds"] or scene_count * 6)),
                "scene_count": max(1, min(20, safety["scene_count"] or scene_count)),
            }
        )
        payload["output_requirements"].update(
            {
                "admin_video_mp4": True,
                "provider_call": False,
                "no_charge": True,
                "final_video_bytes_gt_zero": True,
            }
        )
    return payload


def create_remote_worker_canary_job(conn: sqlite3.Connection, *, admin_user_id: int | str) -> dict:
    admin_id = _safe_int(admin_user_id, 0)
    if admin_id <= 0:
        return {"ok": False, "reason": "admin_user_id_required"}
    video_project_queue.ensure_video_project_queue_schema(conn)
    now = video_project_queue.now_text()
    asset_pack = {
        "source": REMOTE_WORKER_CANARY_SOURCE,
        "admin_only": True,
        "no_charge": True,
        "provider_call": False,
        "public_user": False,
    }
    invoice = {
        "total_xu": 0,
        "admin_only": True,
        "no_charge": True,
        "provider_call": False,
        "public_user": False,
        "source": REMOTE_WORKER_CANARY_SOURCE,
    }
    project = video_project_queue.create_video_project(
        conn,
        user_id=admin_id,
        profile_id="remote_worker_canary",
        topic="REMOTE WORKER CANARY - safe staging job",
        ratio="16:9",
        asset_pack=asset_pack,
    )
    project_id = int(project["project_id"])
    scene_cards = [
        {
            "scene_index": 1,
            "role": "remote_worker_canary",
            "narration_line": "Remote Worker Canary safe test.",
            "subtitle_line": "REMOTE WORKER CANARY",
            "visual_goal": "Tiny local MP4 generated by VPS worker.",
            "provider_prompt": "Do not call provider. Generate local testsrc MP4.",
        }
    ]
    project = video_project_queue.update_video_project(
        conn,
        project_id,
        status="queued_for_worker",
        asset_pack_json=asset_pack,
        scene_cards_json=scene_cards,
        prompt_text="Remote Worker Canary safe staging test. No customer job, no Xu, no provider call.",
        addon_plan_json={"source": REMOTE_WORKER_CANARY_SOURCE, "provider_call": False, "no_charge": True},
        creative_control_json={"canary": True, "safe_staging": True},
        quality_tier=0,
        scene_count=1,
        invoice_json=invoice,
        total_xu_estimated=0,
        is_confirmed=1,
        confirmed_at=now,
    )
    cursor = conn.execute(
        """INSERT INTO video_jobs
           (project_id,user_id,job_type,status,priority,attempts,max_attempts,result_json,progress_percent,progress_message,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            project_id,
            admin_id,
            REMOTE_WORKER_CANARY_JOB_TYPE,
            "queued",
            10,
            0,
            1,
            _json_dumps({"canary": True, "admin_only": True, "no_charge": True, "provider_call": False}),
            0,
            "canary_queued",
            now,
            now,
        ),
    )
    conn.commit()
    job_id = int(cursor.lastrowid)
    project = video_project_queue.update_video_project(conn, project_id, job_id=job_id)
    job = video_project_queue.get_video_render_job(conn, job_id)
    return {"ok": True, "project": project, "job": job, "canary_ref": f"RW-CANARY-{job_id}"}


def count_active_remote_worker_admin_canary_jobs(conn: sqlite3.Connection) -> int:
    video_project_queue.ensure_video_project_queue_schema(conn)
    row = conn.execute(
        """SELECT COUNT(*)
           FROM video_jobs j
           JOIN video_projects p ON p.project_id=j.project_id
           WHERE j.job_type=? AND j.status IN ('queued','processing')
             AND COALESCE(p.asset_pack_json,'') LIKE ?""",
        (video_project_queue.VIDEO_RENDER_JOB_TYPE, f"%{REMOTE_WORKER_ADMIN_CANARY_SOURCE}%"),
    ).fetchone()
    return int(row[0] if row else 0)


def create_remote_worker_admin_canary_job(
    conn: sqlite3.Connection,
    *,
    admin_user_id: int | str,
    profile: str = "simple",
    duration_seconds: int = REMOTE_WORKER_ADMIN_CANARY_DEFAULT_DURATION_SECONDS,
    scene_count: int = 1,
    provider_smoke: bool = False,
    confirm_provider_cost: bool = False,
    environ: dict[str, str] | None = None,
) -> dict:
    admin_id = _safe_int(admin_user_id, 0)
    if admin_id <= 0:
        return {"ok": False, "reason": "admin_user_id_required"}
    if provider_smoke:
        if not confirm_provider_cost:
            return {"ok": False, "reason": "confirm_provider_cost_required"}
        return {"ok": False, "reason": "provider_smoke_deferred_to_later_phase"}
    config = remote_worker_production_guard_config(environ)
    if not config["admin_canary_enabled"]:
        return {"ok": False, "reason": "admin_canary_disabled"}
    active = count_active_remote_worker_admin_canary_jobs(conn)
    if active >= int(config["max_admin_canary_active"]):
        return {"ok": False, "reason": "max_active_admin_canary_reached", "active": active}
    video_project_queue.ensure_video_project_queue_schema(conn)
    now = video_project_queue.now_text()
    safe_duration = max(1, min(10, _safe_int(duration_seconds, REMOTE_WORKER_ADMIN_CANARY_DEFAULT_DURATION_SECONDS)))
    safe_scene_count = max(1, min(3, _safe_int(scene_count, 1)))
    safe_profile = re.sub(r"[^A-Za-z0-9_.:-]+", "-", str(profile or "simple").strip().lower())[:60] or "simple"
    asset_pack = {
        "source": REMOTE_WORKER_ADMIN_CANARY_SOURCE,
        "worker_admin_canary": True,
        "created_by_admin": True,
        "owner": True,
        "admin_only": True,
        "no_charge": True,
        "provider_call": False,
        "public_user": False,
        "duration_seconds": safe_duration,
        "scene_count": safe_scene_count,
        "queue_label": REMOTE_WORKER_ADMIN_CANARY_QUEUE_LABEL,
        "renderer": "remote_worker_admin_canary_local_ffmpeg",
    }
    invoice = {
        "total_xu": 0,
        "worker_admin_canary": True,
        "created_by_admin": True,
        "admin_only": True,
        "no_charge": True,
        "provider_call": False,
        "public_user": False,
        "invoice_disabled": True,
        "source": REMOTE_WORKER_ADMIN_CANARY_SOURCE,
        "queue_label": REMOTE_WORKER_ADMIN_CANARY_QUEUE_LABEL,
    }
    project = video_project_queue.create_video_project(
        conn,
        user_id=admin_id,
        profile_id=f"remote_worker_admin_canary_{safe_profile}",
        topic="OWNER/ADMIN WORKER CANARY - VPS production-like test",
        ratio="16:9",
        asset_pack=asset_pack,
    )
    project_id = int(project["project_id"])
    scene_cards = [
        {
            "scene_index": 1,
            "role": "owner_admin_worker_canary",
            "narration_line": "VPS worker admin production canary.",
            "subtitle_line": "OWNER/ADMIN WORKER CANARY",
            "visual_goal": "Tiny local MP4 generated by VPS worker through normal video_render job type.",
            "provider_prompt": "Do not call provider. Generate local testsrc MP4.",
        }
    ][:safe_scene_count]
    video_project_queue.save_video_project_storyboard(conn, project_id, {"scene_cards": scene_cards})
    project = video_project_queue.update_video_project(
        conn,
        project_id,
        status="queued_for_worker",
        asset_pack_json=asset_pack,
        scene_cards_json=scene_cards,
        prompt_text="Admin-only VPS production canary. No customer job, no Xu, no provider call.",
        addon_plan_json={"source": REMOTE_WORKER_ADMIN_CANARY_SOURCE, "provider_call": False, "no_charge": True},
        creative_control_json={"worker_admin_canary": True, "safe_production_canary": True},
        quality_tier=0,
        scene_count=safe_scene_count,
        invoice_json=invoice,
        total_xu_estimated=0,
        is_confirmed=1,
        confirmed_at=now,
    )
    cursor = conn.execute(
        """INSERT INTO video_jobs
           (project_id,user_id,job_type,status,priority,attempts,max_attempts,result_json,progress_percent,progress_message,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            project_id,
            admin_id,
            video_project_queue.VIDEO_RENDER_JOB_TYPE,
            "queued",
            5,
            0,
            1,
            _json_dumps(
                {
                    "worker_admin_canary": True,
                    "admin_only": True,
                    "no_charge": True,
                    "provider_call": False,
                    "public_user": False,
                    "queue_label": REMOTE_WORKER_ADMIN_CANARY_QUEUE_LABEL,
                }
            ),
            0,
            "admin_canary_queued",
            now,
            now,
        ),
    )
    conn.commit()
    job_id = int(cursor.lastrowid)
    project = video_project_queue.update_video_project(conn, project_id, job_id=job_id)
    job = video_project_queue.get_video_render_job(conn, job_id)
    return {"ok": True, "project": project, "job": job, "canary_ref": f"{REMOTE_WORKER_ADMIN_CANARY_REF_PREFIX}-{job_id}"}


def _requeue_stale_canary_jobs(conn: sqlite3.Connection, *, now: datetime | None = None) -> int:
    current = video_project_queue.now_text(now)
    cursor = conn.execute(
        """UPDATE video_jobs
           SET status='queued', locked_by='', locked_at=NULL, lease_expires_at=NULL, updated_at=?, last_error='lease_expired_requeued'
           WHERE job_type=? AND status='processing'
             AND lease_expires_at IS NOT NULL
             AND lease_expires_at < ?
             AND COALESCE(attempts,0) < COALESCE(max_attempts,1)""",
        (current, REMOTE_WORKER_CANARY_JOB_TYPE, current),
    )
    conn.commit()
    return int(cursor.rowcount or 0)


def claim_remote_worker_canary_job(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    lease_seconds: int = 600,
    now: datetime | None = None,
) -> dict:
    video_project_queue.ensure_video_project_queue_schema(conn)
    _requeue_stale_canary_jobs(conn, now=now)
    current_dt = now or datetime.now()
    current = video_project_queue.now_text(current_dt)
    lease_expires = video_project_queue.now_text(current_dt + timedelta(seconds=max(30, int(lease_seconds or 600))))
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """SELECT j.id,j.project_id,p.asset_pack_json,p.invoice_json,p.total_xu_estimated
               FROM video_jobs j
               JOIN video_projects p ON p.project_id=j.project_id
               WHERE j.job_type=? AND j.status='queued'
                 AND COALESCE(p.is_confirmed,0)=1
                 AND p.status IN ('queued_for_worker','processing')
                 AND COALESCE(p.asset_pack_json,'') LIKE ?
               ORDER BY j.priority ASC, j.created_at ASC, j.id ASC
               LIMIT 1""",
            (REMOTE_WORKER_CANARY_JOB_TYPE, f"%{REMOTE_WORKER_CANARY_SOURCE}%"),
        ).fetchone()
        if not row:
            conn.commit()
            return {}
        job_id = int(row[0])
        project_id = int(row[1])
        safety = _canary_safety_flags(
            {
                "asset_pack_json": row[2],
                "invoice_json": row[3],
                "total_xu_estimated": row[4],
            }
        )
        if (
            str(safety["source"]) != REMOTE_WORKER_CANARY_SOURCE
            or not safety["admin_only"]
            or not safety["no_charge"]
            or safety["provider_call"]
            or safety["public_user"]
        ):
            conn.commit()
            return {}
        cursor = conn.execute(
            """UPDATE video_jobs
               SET status='processing', attempts=COALESCE(attempts,0)+1, locked_by=?, locked_at=?,
                   lease_expires_at=?, started_at=COALESCE(started_at, ?), updated_at=?,
                   progress_percent=10, progress_message='claimed'
               WHERE id=? AND status='queued' AND job_type=?""",
            (
                sanitize_worker_id(worker_id),
                current,
                lease_expires,
                current,
                current,
                job_id,
                REMOTE_WORKER_CANARY_JOB_TYPE,
            ),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return {}
        conn.execute("UPDATE video_projects SET status='processing', updated_at=? WHERE project_id=?", (current, project_id))
        conn.commit()
        return video_project_queue.get_video_render_job(conn, job_id)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


def _claim_video_render_candidate(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    lease_seconds: int = 600,
    now: datetime | None = None,
    admin_canary_only: bool = False,
    admin_video_only: bool = False,
    public_enabled: bool = False,
) -> dict:
    video_project_queue.ensure_video_project_queue_schema(conn)
    video_project_queue.requeue_stale_video_jobs(conn, now=now)
    current_dt = now or datetime.now()
    current = video_project_queue.now_text(current_dt)
    lease_expires = video_project_queue.now_text(current_dt + timedelta(seconds=max(30, int(lease_seconds or 600))))
    try:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            """SELECT j.id,j.project_id,j.user_id,j.job_type,j.status,j.priority,j.attempts,j.max_attempts,j.locked_by,j.locked_at,
                      j.lease_expires_at,j.last_error,j.result_json,j.created_at,j.updated_at,j.started_at,j.completed_at,
                      j.progress_percent,j.progress_message,
                      p.asset_pack_json,p.invoice_json,p.total_xu_estimated,p.profile_id,p.topic
               FROM video_jobs j
               JOIN video_projects p ON p.project_id=j.project_id
               WHERE j.job_type=? AND j.status='queued'
                 AND COALESCE(p.is_confirmed,0)=1
                 AND p.status IN ('queued_for_worker','processing')
               ORDER BY j.priority ASC, j.created_at ASC, j.id ASC
               LIMIT 25""",
            (video_project_queue.VIDEO_RENDER_JOB_TYPE,),
        ).fetchall()
        chosen: dict | None = None
        chosen_project: dict | None = None
        for row in rows:
            job = {
                "id": row[0],
                "project_id": row[1],
                "user_id": row[2],
                "job_type": row[3],
            }
            project = {
                "project_id": row[1],
                "user_id": row[2],
                "asset_pack_json": row[19],
                "invoice_json": row[20],
                "total_xu_estimated": row[21],
                "profile_id": row[22],
                "topic": row[23],
            }
            if admin_canary_only:
                if _admin_canary_is_safe(project):
                    chosen = job
                    chosen_project = project
                    break
                continue
            if admin_video_only:
                if _admin_video_is_safe(project):
                    chosen = job
                    chosen_project = project
                    break
                continue
            if is_remote_worker_admin_canary_job(job, project):
                continue
            if _is_admin_fake_video_job(project) or public_enabled:
                chosen = job
                chosen_project = project
                break
        if not chosen or not chosen_project:
            conn.commit()
            return {}
        if admin_canary_only:
            progress_message = "admin canary claimed"
        elif admin_video_only:
            progress_message = "admin video claimed"
        else:
            progress_message = "claimed"
        cursor = conn.execute(
            """UPDATE video_jobs
               SET status='processing', attempts=COALESCE(attempts,0)+1, locked_by=?, locked_at=?,
                   lease_expires_at=?, started_at=COALESCE(started_at, ?), updated_at=?,
                   progress_percent=10, progress_message=?
               WHERE id=? AND status='queued' AND job_type=?""",
            (
                sanitize_worker_id(worker_id),
                current,
                lease_expires,
                current,
                current,
                progress_message,
                int(chosen["id"]),
                video_project_queue.VIDEO_RENDER_JOB_TYPE,
            ),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return {}
        conn.execute("UPDATE video_projects SET status='processing', updated_at=? WHERE project_id=?", (current, int(chosen["project_id"])))
        conn.commit()
        return video_project_queue.get_video_render_job(conn, int(chosen["id"]))
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


def claim_remote_worker_admin_canary_job(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    lease_seconds: int = 600,
    now: datetime | None = None,
) -> dict:
    return _claim_video_render_candidate(
        conn,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
        now=now,
        admin_canary_only=True,
        admin_video_only=False,
        public_enabled=False,
    )


def claim_remote_worker_admin_video_job(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    lease_seconds: int = 600,
    now: datetime | None = None,
) -> dict:
    return _claim_video_render_candidate(
        conn,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
        now=now,
        admin_canary_only=False,
        admin_video_only=True,
        public_enabled=False,
    )


def claim_remote_worker_render_job(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    lease_seconds: int = 600,
    public_enabled: bool = False,
    now: datetime | None = None,
) -> dict:
    return _claim_video_render_candidate(
        conn,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
        now=now,
        admin_canary_only=False,
        admin_video_only=False,
        public_enabled=public_enabled,
    )


def claim_remote_worker_job(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    capabilities: list[str] | None = None,
    max_jobs: int = 1,
    lease_seconds: int = 600,
    canary_only: bool = False,
    admin_canary_only: bool = False,
    admin_video_only: bool = False,
) -> dict:
    worker = sanitize_worker_id(worker_id)
    requested = {str(item).strip().lower() for item in (capabilities or []) if str(item).strip()}
    if requested and not (requested & set(REMOTE_WORKER_CAPABILITIES)):
        return {"ok": True, "job": None, "reason": "capability_not_supported"}
    if _safe_int(max_jobs, 1) < 1:
        return {"ok": False, "reason": "max_jobs_must_be_positive"}
    if canary_only:
        if requested and REMOTE_WORKER_CANARY_CAPABILITY not in requested:
            return {"ok": True, "job": None, "reason": "canary_capability_required"}
        job = claim_remote_worker_canary_job(conn, worker_id=worker, lease_seconds=lease_seconds)
        hydrated = video_project_queue.hydrate_video_job_payload(conn, job) if job else {}
        return {"ok": True, "job": build_worker_job_payload(hydrated) if hydrated else None, "canary_only": True}
    if admin_canary_only:
        if requested and REMOTE_WORKER_ADMIN_CANARY_CAPABILITY not in requested:
            return {"ok": True, "job": None, "reason": "admin_canary_capability_required"}
        config = remote_worker_production_guard_config()
        if not config["admin_canary_enabled"]:
            return {"ok": True, "job": None, "reason": "admin_canary_disabled", "admin_canary_only": True}
        job = claim_remote_worker_admin_canary_job(conn, worker_id=worker, lease_seconds=lease_seconds)
        hydrated = video_project_queue.hydrate_video_job_payload(conn, job) if job else {}
        return {"ok": True, "job": build_worker_job_payload(hydrated) if hydrated else None, "admin_canary_only": True}
    if admin_video_only:
        if requested and REMOTE_WORKER_ADMIN_VIDEO_CAPABILITY not in requested:
            return {"ok": True, "job": None, "reason": "admin_video_capability_required"}
        job = claim_remote_worker_admin_video_job(conn, worker_id=worker, lease_seconds=lease_seconds)
        hydrated = video_project_queue.hydrate_video_job_payload(conn, job) if job else {}
        return {"ok": True, "job": build_worker_job_payload(hydrated) if hydrated else None, "admin_video_only": True, "reason": "" if hydrated else "no_admin_video_job"}
    if requested and not (requested & set(REMOTE_WORKER_RENDER_CAPABILITIES)):
        return {"ok": True, "job": None, "reason": "capability_not_supported"}
    config = remote_worker_production_guard_config()
    job = claim_remote_worker_render_job(
        conn,
        worker_id=worker,
        lease_seconds=lease_seconds,
        public_enabled=bool(config["public_enabled"]),
    )
    hydrated = video_project_queue.hydrate_video_job_payload(conn, job) if job else {}
    reason = "" if hydrated else ("no_job" if config["public_enabled"] else "public_worker_disabled")
    return {"ok": True, "job": build_worker_job_payload(hydrated) if hydrated else None, "reason": reason}


def heartbeat_remote_worker_job(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    job_id: int,
    progress_percent: int = 0,
    message: str = "",
    lease_seconds: int = 600,
) -> dict:
    return video_project_queue.heartbeat_video_job(
        conn,
        job_id=int(job_id),
        worker_id=sanitize_worker_id(worker_id),
        progress_percent=progress_percent,
        message=message,
        lease_seconds=lease_seconds,
    )


def worker_owns_job(job: dict, worker_id: str) -> bool:
    return bool(job and str(job.get("locked_by") or "") == sanitize_worker_id(worker_id))


def validate_uploaded_result_file(path: str) -> dict:
    if not path:
        return {"ok": False, "reason": "result_file_missing"}
    try:
        size = os.path.getsize(path)
    except OSError:
        return {"ok": False, "reason": "result_file_missing"}
    if size <= 0:
        return {"ok": False, "reason": "result_file_empty"}
    return {"ok": True, "bytes": int(size)}


def complete_remote_worker_job(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    job_id: int,
    result: dict | None = None,
    final_video_path: str = "",
    final_video_file_id: str = "",
    uploaded_file: bool = False,
) -> dict:
    worker = sanitize_worker_id(worker_id)
    job = video_project_queue.get_video_render_job(conn, int(job_id))
    if not job:
        return {"ok": False, "reason": "job_not_found"}
    project = video_project_queue.get_video_project(conn, int(job.get("project_id") or 0))
    is_canary = is_remote_worker_canary_job(job, project)
    is_admin_canary = is_remote_worker_admin_canary_job(job, project)
    is_admin_video = is_remote_worker_admin_video_job(job, project) or _is_admin_fake_video_job(project)
    if str(job.get("status") or "") == "completed":
        if not worker_owns_job(job, worker):
            return {"ok": False, "reason": "job_already_completed_by_other_worker"}
        return {"ok": True, "duplicate": True, "job": job}
    if str(job.get("status") or "") != "processing":
        return {"ok": False, "reason": "job_not_processing", "job": job}
    if not worker_owns_job(job, worker):
        return {"ok": False, "reason": "job_not_owned_by_worker", "job": job}
    if uploaded_file:
        validation = validate_uploaded_result_file(final_video_path)
        if not validation.get("ok"):
            return validation
    if is_canary:
        validation = validate_uploaded_result_file(final_video_path)
        if not validation.get("ok"):
            return {"ok": False, "reason": "canary_result_file_missing"}
    if is_admin_canary:
        validation = validate_uploaded_result_file(final_video_path)
        if not validation.get("ok"):
            return {"ok": False, "reason": "admin_canary_result_file_missing"}
    if is_admin_video:
        validation = validate_uploaded_result_file(final_video_path)
        if not validation.get("ok"):
            return {"ok": False, "reason": "admin_video_result_file_missing"}
    payload = dict(result or {})
    if uploaded_file:
        payload["uploaded_file_bytes"] = os.path.getsize(final_video_path)
    if is_canary:
        payload.update(
            {
                "canary": True,
                "admin_only": True,
                "no_charge": True,
                "provider_call": False,
                "public_user": False,
            }
        )
    if is_admin_canary:
        payload.update(
            {
                "admin_canary": True,
                "worker_admin_canary": True,
                "admin_only": True,
                "no_charge": True,
                "provider_call": False,
                "public_user": False,
                "queue_label": REMOTE_WORKER_ADMIN_CANARY_QUEUE_LABEL,
            }
        )
    if is_admin_video:
        payload.update(
            {
                "admin_video_delivery": True,
                "admin_only": True,
                "no_charge": True,
                "provider_call": False,
                "public_user": False,
                "queue_label": REMOTE_WORKER_ADMIN_VIDEO_QUEUE_LABEL,
            }
        )
    completed = video_project_queue.complete_video_job(
        conn,
        job_id=int(job_id),
        final_video_path=str(final_video_path or payload.get("final_video_path") or ""),
        final_video_file_id=str(final_video_file_id or payload.get("final_video_file_id") or ""),
        result=strip_secret_fields(payload),
    )
    completed["duplicate"] = False
    return completed


def fail_remote_worker_job(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    job_id: int,
    safe_error: str = "",
    retryable: bool = True,
    partial_artifacts: list | None = None,
) -> dict:
    worker = sanitize_worker_id(worker_id)
    job = video_project_queue.get_video_render_job(conn, int(job_id))
    if not job:
        return {"ok": False, "reason": "job_not_found"}
    if str(job.get("status") or "") != "processing":
        return {"ok": False, "reason": "job_not_processing", "job": job}
    if not worker_owns_job(job, worker):
        return {"ok": False, "reason": "job_not_owned_by_worker", "job": job}
    error = str(safe_error or "remote_worker_failed").replace("\n", " ")[:1000]
    if partial_artifacts:
        error = f"{error}; partial_artifacts={len(partial_artifacts)}"[:1000]
    return video_project_queue.fail_video_job(conn, job_id=int(job_id), error=error, retry=bool(retryable))


def save_uploaded_result(upload_root: str | Path, *, job_id: int, filename: str, content: bytes) -> str:
    if not content:
        raise ValueError("result_file_empty")
    root = Path(upload_root)
    root.mkdir(parents=True, exist_ok=True)
    clean_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(filename or "result.mp4"))[:120] or "result.mp4"
    while ".." in clean_name:
        clean_name = clean_name.replace("..", ".")
    clean_name = clean_name.lstrip(".-") or "result.mp4"
    if not clean_name.lower().endswith(".mp4"):
        clean_name += ".mp4"
    destination = root / f"worker_job_{int(job_id)}_{clean_name}"
    destination.write_bytes(content)
    return str(destination)


def note_remote_worker_canary_delivery(conn: sqlite3.Connection, *, job_id: int, sent: bool, reason: str = "") -> dict:
    job = video_project_queue.get_video_render_job(conn, int(job_id))
    if not job:
        return {"ok": False, "reason": "job_not_found"}
    project = video_project_queue.get_video_project(conn, int(job.get("project_id") or 0))
    if not (is_remote_worker_canary_job(job, project) or is_remote_worker_admin_canary_job(job, project)):
        return {"ok": False, "reason": "not_canary"}
    payload = _json_loads(job.get("result_json"), {})
    if not isinstance(payload, dict):
        payload = {}
    payload["sent_to_admin"] = bool(sent)
    if reason:
        payload["admin_delivery_reason"] = scrub_secret_text(reason)[:120]
    conn.execute("UPDATE video_jobs SET result_json=? WHERE id=?", (_json_dumps(payload), int(job_id)))
    conn.commit()
    return {"ok": True, "sent_to_admin": bool(sent)}


def get_remote_worker_canary_status(
    conn: sqlite3.Connection,
    *,
    job_id: int | str = 0,
    admin_user_id: int | str | None = None,
) -> dict:
    video_project_queue.ensure_video_project_queue_schema(conn)
    wanted_job_id = _safe_int(job_id, 0)
    admin_id = _safe_int(admin_user_id, 0) if admin_user_id is not None else 0
    if wanted_job_id:
        job = video_project_queue.get_video_render_job(conn, wanted_job_id)
        if not job or str(job.get("job_type") or "") != REMOTE_WORKER_CANARY_JOB_TYPE:
            return {"ok": False, "reason": "canary_not_found"}
        if admin_id and _safe_int(job.get("user_id"), 0) != admin_id:
            return {"ok": False, "reason": "canary_not_found"}
    else:
        params: list[Any] = [REMOTE_WORKER_CANARY_JOB_TYPE]
        where_admin = ""
        if admin_id:
            where_admin = " AND user_id=?"
            params.append(admin_id)
        row = conn.execute(
            f"""SELECT id FROM video_jobs
                WHERE job_type=?{where_admin}
                ORDER BY id DESC LIMIT 1""",
            params,
        ).fetchone()
        if not row:
            return {"ok": False, "reason": "canary_not_found"}
        job = video_project_queue.get_video_render_job(conn, int(row[0]))
    project = video_project_queue.get_video_project(conn, int(job.get("project_id") or 0))
    if not is_remote_worker_canary_job(job, project):
        return {"ok": False, "reason": "canary_not_found"}
    result = _json_loads(job.get("result_json"), {})
    if not isinstance(result, dict):
        result = {}
    final_path = str(project.get("final_video_path") or result.get("final_video_path") or "")
    uploaded_bytes = _safe_int(result.get("uploaded_file_bytes") or result.get("bytes"), 0)
    if final_path and uploaded_bytes <= 0:
        try:
            uploaded_bytes = os.path.getsize(final_path)
        except OSError:
            uploaded_bytes = 0
    result_uploaded = bool(uploaded_bytes > 0 or final_path or project.get("final_video_file_id"))
    return {
        "ok": True,
        "job_id": int(job.get("id") or 0),
        "canary_ref": f"RW-CANARY-{int(job.get('id') or 0)}",
        "status": str(job.get("status") or ""),
        "worker_id": sanitize_worker_id(str(job.get("locked_by") or "")) if job.get("locked_by") else "",
        "claimed_at": str(job.get("locked_at") or ""),
        "last_heartbeat_at": str(job.get("updated_at") or ""),
        "progress_percent": _safe_int(job.get("progress_percent"), 0),
        "progress_message": scrub_secret_text(job.get("progress_message") or ""),
        "result_uploaded": result_uploaded,
        "result_file_size": int(uploaded_bytes or 0),
        "sent_to_admin": bool(result.get("sent_to_admin")),
        "safe_failure_reason": scrub_secret_text(job.get("last_error") or project.get("error_log") or ""),
        "admin_only": True,
        "no_charge": True,
        "provider_call": False,
        "public_user": False,
    }


def get_remote_worker_admin_canary_status(
    conn: sqlite3.Connection,
    *,
    job_id: int | str = 0,
    admin_user_id: int | str | None = None,
) -> dict:
    video_project_queue.ensure_video_project_queue_schema(conn)
    wanted_job_id = _safe_int(job_id, 0)
    admin_id = _safe_int(admin_user_id, 0) if admin_user_id is not None else 0
    if wanted_job_id:
        job = video_project_queue.get_video_render_job(conn, wanted_job_id)
        if not job:
            return {"ok": False, "reason": "admin_canary_not_found"}
        if admin_id and _safe_int(job.get("user_id"), 0) != admin_id:
            return {"ok": False, "reason": "admin_canary_not_found"}
    else:
        params: list[Any] = [video_project_queue.VIDEO_RENDER_JOB_TYPE, f"%{REMOTE_WORKER_ADMIN_CANARY_SOURCE}%"]
        where_admin = ""
        if admin_id:
            where_admin = " AND j.user_id=?"
            params.append(admin_id)
        row = conn.execute(
            f"""SELECT j.id
                FROM video_jobs j
                JOIN video_projects p ON p.project_id=j.project_id
                WHERE j.job_type=? AND COALESCE(p.asset_pack_json,'') LIKE ?{where_admin}
                ORDER BY j.id DESC LIMIT 1""",
            params,
        ).fetchone()
        if not row:
            return {"ok": False, "reason": "admin_canary_not_found"}
        job = video_project_queue.get_video_render_job(conn, int(row[0]))
    project = video_project_queue.get_video_project(conn, int(job.get("project_id") or 0))
    if not is_remote_worker_admin_canary_job(job, project):
        return {"ok": False, "reason": "admin_canary_not_found"}
    result = _json_loads(job.get("result_json"), {})
    if not isinstance(result, dict):
        result = {}
    flags = _admin_canary_safety_flags(project)
    final_path = str(project.get("final_video_path") or result.get("final_video_path") or "")
    uploaded_bytes = _safe_int(result.get("uploaded_file_bytes") or result.get("bytes"), 0)
    if final_path and uploaded_bytes <= 0:
        try:
            uploaded_bytes = os.path.getsize(final_path)
        except OSError:
            uploaded_bytes = 0
    result_uploaded = bool(uploaded_bytes > 0 or final_path or project.get("final_video_file_id"))
    progress_message = scrub_secret_text(job.get("progress_message") or "")
    return {
        "ok": True,
        "job_id": int(job.get("id") or 0),
        "canary_ref": f"{REMOTE_WORKER_ADMIN_CANARY_REF_PREFIX}-{int(job.get('id') or 0)}",
        "status": str(job.get("status") or ""),
        "stage": progress_message or str(job.get("status") or ""),
        "worker_id": sanitize_worker_id(str(job.get("locked_by") or "")) if job.get("locked_by") else "",
        "claimed_at": str(job.get("locked_at") or ""),
        "last_heartbeat_at": str(job.get("updated_at") or ""),
        "progress_percent": _safe_int(job.get("progress_percent"), 0),
        "progress_message": progress_message,
        "result_uploaded": result_uploaded,
        "result_file_size": int(uploaded_bytes or 0),
        "sent_to_admin": bool(result.get("sent_to_admin")),
        "safe_failure_reason": scrub_secret_text(job.get("last_error") or project.get("error_log") or ""),
        "admin_only": bool(flags["admin_only"]),
        "no_charge": bool(flags["no_charge"]),
        "provider_call": bool(flags["provider_call"]),
        "public_user": bool(flags["public_user"]),
        "worker_admin_canary": bool(flags["worker_admin_canary"]),
        "queue_label": REMOTE_WORKER_ADMIN_CANARY_QUEUE_LABEL,
    }


def remote_worker_admin_canary_queue_snapshot(conn: sqlite3.Connection) -> dict:
    video_project_queue.ensure_video_project_queue_schema(conn)
    rows = conn.execute(
        """SELECT j.id,j.status,j.locked_by,j.updated_at,j.progress_percent,j.progress_message
           FROM video_jobs j
           JOIN video_projects p ON p.project_id=j.project_id
           WHERE j.job_type=? AND COALESCE(p.asset_pack_json,'') LIKE ?
           ORDER BY j.id DESC LIMIT 5""",
        (video_project_queue.VIDEO_RENDER_JOB_TYPE, f"%{REMOTE_WORKER_ADMIN_CANARY_SOURCE}%"),
    ).fetchall()
    active = count_active_remote_worker_admin_canary_jobs(conn)
    items = [
        {
            "job_id": int(row[0]),
            "canary_ref": f"{REMOTE_WORKER_ADMIN_CANARY_REF_PREFIX}-{int(row[0])}",
            "status": str(row[1] or ""),
            "worker_id": sanitize_worker_id(str(row[2] or "")) if row[2] else "",
            "updated_at": str(row[3] or ""),
            "progress_percent": _safe_int(row[4], 0),
            "progress_message": scrub_secret_text(row[5] or ""),
        }
        for row in rows
    ]
    return {
        "ok": True,
        "queue_label": REMOTE_WORKER_ADMIN_CANARY_QUEUE_LABEL,
        "active": active,
        "last": items[0] if items else {},
        "items": items,
        "invoice": False,
        "wallet": False,
    }


def create_admin_video_delivery_test_job(
    conn: sqlite3.Connection,
    *,
    admin_user_id: int | str,
    scene_count: int = 3,
    duration_seconds: int = 18,
) -> dict:
    admin_id = _safe_int(admin_user_id, 0)
    if admin_id <= 0:
        return {"ok": False, "reason": "admin_user_id_required"}
    video_project_queue.ensure_video_project_queue_schema(conn)
    safe_scene_count = max(1, min(20, _safe_int(scene_count, 3)))
    safe_duration = max(1, min(120, _safe_int(duration_seconds, safe_scene_count * 6)))
    now = video_project_queue.now_text()
    asset_pack = {
        "source": REMOTE_WORKER_ADMIN_VIDEO_SOURCE,
        "admin_video_delivery": True,
        "owner_admin_test_mode": True,
        "created_by_admin": True,
        "owner": True,
        "admin_only": True,
        "no_charge": True,
        "admin_no_charge": True,
        "provider_call": False,
        "public_user": False,
        "scene_count": safe_scene_count,
        "duration_seconds": safe_duration,
        "queue_label": REMOTE_WORKER_ADMIN_VIDEO_QUEUE_LABEL,
    }
    invoice = {
        "total_xu": 0,
        "admin_video_delivery": True,
        "owner_admin_test_mode": True,
        "created_by_admin": True,
        "admin_only": True,
        "no_charge": True,
        "admin_no_charge": True,
        "provider_call": False,
        "public_user": False,
        "invoice_disabled": True,
        "scene_count": safe_scene_count,
        "duration_seconds": safe_duration,
        "source": REMOTE_WORKER_ADMIN_VIDEO_SOURCE,
        "queue_label": REMOTE_WORKER_ADMIN_VIDEO_QUEUE_LABEL,
    }
    project = video_project_queue.create_video_project(
        conn,
        user_id=admin_id,
        profile_id="admin_video_delivery_test",
        topic="OWNER/ADMIN TEST MODE - video delivery output test",
        ratio="9:16",
        asset_pack=asset_pack,
    )
    project_id = int(project["project_id"])
    scene_cards = [
        {
            "scene_index": index,
            "role": "admin_video_delivery",
            "narration_line": f"OWNER/ADMIN TEST MODE cảnh {index}.",
            "subtitle_line": f"OWNER/ADMIN TEST MODE {index}",
            "visual_goal": "Kiểm tra hệ thống nhận xử lý và xuất MP4 thật.",
            "provider_prompt": "Do not call provider. Generate a local admin test MP4.",
        }
        for index in range(1, safe_scene_count + 1)
    ]
    video_project_queue.save_video_project_storyboard(conn, project_id, {"scene_cards": scene_cards})
    project = video_project_queue.update_video_project(
        conn,
        project_id,
        status="draft_invoice",
        asset_pack_json=asset_pack,
        scene_cards_json=scene_cards,
        prompt_text="OWNER/ADMIN TEST MODE video delivery output test. No customer job, no Xu, no provider call.",
        addon_plan_json={"source": REMOTE_WORKER_ADMIN_VIDEO_SOURCE, "provider_call": False, "no_charge": True},
        creative_control_json={"admin_video_delivery": True, "safe_output_delivery_test": True},
        quality_tier=0,
        scene_count=safe_scene_count,
        invoice_json=invoice,
        total_xu_estimated=0,
    )
    result = video_project_queue.confirm_video_project_invoice(
        conn,
        project_id=project_id,
        user_id=admin_id,
        balance_xu=0,
        deduct_func=lambda _uid, _amount: {"ok": True, "final_cost": 0, "no_charge": True},
    )
    if result.get("ok"):
        job = result.get("job") or {}
        video_project_queue.update_video_project(conn, project_id, job_id=int(job.get("id") or 0), invoice_json=invoice)
    return {"ok": bool(result.get("ok")), "project": result.get("project") or project, "job": result.get("job") or {}, "reason": result.get("reason") or ""}


def create_fake_video_job_for_admin_test(conn: sqlite3.Connection, *, user_id: int | str) -> dict:
    project = video_project_queue.create_video_project(
        conn,
        user_id=_safe_int(user_id, 0),
        profile_id="remote_worker_api_admin_test",
        topic="ADMIN TEST MODE - Remote Worker API Bridge",
        ratio="9:16",
        asset_pack={"source": "admin_fake_job", "no_charge": True},
    )
    project_id = int(project["project_id"])
    video_project_queue.advance_video_project_state(conn, project_id, "draft_assets")
    video_project_queue.advance_video_project_state(conn, project_id, "draft_prompt")
    video_project_queue.handle_video_project_text(conn, project_id, "Fake scene for remote worker API bridge test.")
    video_project_queue.save_video_project_storyboard(
        conn,
        project_id,
        {
            "scene_cards": [
                {
                    "scene_index": 1,
                    "role": "admin_test",
                    "narration_line": "Remote Worker API Bridge fake job.",
                    "subtitle_line": "ADMIN TEST MODE",
                    "visual_goal": "Simple fake render validation",
                    "provider_prompt": "Render a short test clip.",
                }
            ]
        },
    )
    video_project_queue.advance_video_project_state(conn, project_id, "draft_addons")
    video_project_queue.advance_video_project_state(conn, project_id, "draft_quality")
    video_project_queue.advance_video_project_state(conn, project_id, "draft_scene_count")
    video_project_queue.advance_video_project_state(conn, project_id, "draft_invoice")
    video_project_queue.update_video_project(
        conn,
        project_id,
        total_xu_estimated=0,
        invoice_json={"total_xu": 0, "admin_test": True, "no_charge": True},
    )
    return video_project_queue.confirm_video_project_invoice(
        conn,
        project_id=project_id,
        user_id=_safe_int(user_id, 0),
        balance_xu=0,
        deduct_func=lambda _uid, _amount: {"ok": True, "final_cost": 0, "no_charge": True},
    )
