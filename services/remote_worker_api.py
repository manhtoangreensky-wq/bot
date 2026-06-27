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
REMOTE_WORKER_CAPABILITIES = ("ffmpeg", "video_postprocess", "local_render_helpers")


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
    quality_tier = _safe_int(project.get("quality_tier") or hydrated_job.get("quality_tier"), 200)
    scene_count = max(1, _safe_int(project.get("scene_count") or len(scene_cards) or 1, 1))
    ratio = str(project.get("ratio") or "9:16")
    return {
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


def claim_remote_worker_job(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    capabilities: list[str] | None = None,
    max_jobs: int = 1,
    lease_seconds: int = 600,
) -> dict:
    worker = sanitize_worker_id(worker_id)
    requested = {str(item).strip().lower() for item in (capabilities or []) if str(item).strip()}
    if requested and not (requested & set(REMOTE_WORKER_CAPABILITIES)):
        return {"ok": True, "job": None, "reason": "capability_not_supported"}
    if _safe_int(max_jobs, 1) < 1:
        return {"ok": False, "reason": "max_jobs_must_be_positive"}
    job = video_project_queue.claim_next_video_job(conn, worker_id=worker, lease_seconds=lease_seconds)
    hydrated = video_project_queue.hydrate_video_job_payload(conn, job) if job else {}
    return {"ok": True, "job": build_worker_job_payload(hydrated) if hydrated else None}


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
    payload = dict(result or {})
    if uploaded_file:
        payload["uploaded_file_bytes"] = os.path.getsize(final_video_path)
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
    if not clean_name.lower().endswith(".mp4"):
        clean_name += ".mp4"
    destination = root / f"worker_job_{int(job_id)}_{clean_name}"
    destination.write_bytes(content)
    return str(destination)


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
