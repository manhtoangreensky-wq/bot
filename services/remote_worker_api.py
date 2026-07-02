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
SAFE_DIAGNOSTIC_CODES = (
    "real_video_renderer_unavailable",
    "product_video_worker_unavailable",
    "not_claimed_timeout",
    "provider_submit_failed",
    "missing_config",
    "worker_api_disabled",
    "claim_route_missing",
    "no_owner_product_video_job",
    "no_admin_canary_job",
)
REMOTE_WORKER_CANARY_JOB_TYPE = "remote_worker_canary"
REMOTE_WORKER_CANARY_SOURCE = "admin_canary"
REMOTE_WORKER_CANARY_CAPABILITY = "canary"
REMOTE_WORKER_ADMIN_CANARY_SOURCE = "admin_prod_canary"
REMOTE_WORKER_ADMIN_CANARY_CAPABILITY = "admin_canary"
REMOTE_WORKER_ADMIN_CANARY_REF_PREFIX = "RW-PROD-CANARY"
REMOTE_WORKER_ADMIN_VIDEO_SOURCE = "admin_video_delivery"
REMOTE_WORKER_ADMIN_VIDEO_CAPABILITY = "admin_video"
REMOTE_WORKER_ADMIN_VIDEO_QUEUE_LABEL = "OWNER/ADMIN TEST PATTERN — kiểm tra gửi MP4, không trừ Xu"
REMOTE_WORKER_PRODUCT_VIDEO_SOURCE = "product_video"
REMOTE_WORKER_PRODUCT_VIDEO_CAPABILITY = "product_video"
REMOTE_WORKER_OWNER_PRODUCT_VIDEO_CAPABILITY = "owner_product_video"
RENDER_MODE_REAL = "real"
RENDER_MODE_ADMIN_TEST_PATTERN = "admin_test_pattern"
RENDER_MODE_UNAVAILABLE = "unavailable"
REAL_RENDER_UNAVAILABLE_REASON = "real_video_renderer_unavailable"
REMOTE_WORKER_RENDER_CAPABILITIES = ("ffmpeg", "video_postprocess", "local_render_helpers")
REMOTE_WORKER_CAPABILITIES = (
    *REMOTE_WORKER_RENDER_CAPABILITIES,
    REMOTE_WORKER_CANARY_CAPABILITY,
    REMOTE_WORKER_ADMIN_CANARY_CAPABILITY,
    REMOTE_WORKER_ADMIN_VIDEO_CAPABILITY,
    REMOTE_WORKER_PRODUCT_VIDEO_CAPABILITY,
    REMOTE_WORKER_OWNER_PRODUCT_VIDEO_CAPABILITY,
)
REMOTE_WORKER_PRODUCTION_ENABLED_ENV = "REMOTE_WORKER_PRODUCTION_ENABLED"
REMOTE_WORKER_ADMIN_CANARY_ENABLED_ENV = "REMOTE_WORKER_ADMIN_CANARY_ENABLED"
REMOTE_WORKER_PUBLIC_ENABLED_ENV = "REMOTE_WORKER_PUBLIC_ENABLED"
REMOTE_WORKER_MAX_ADMIN_CANARY_ACTIVE_ENV = "REMOTE_WORKER_MAX_ADMIN_CANARY_ACTIVE"
REMOTE_WORKER_PRODUCT_VIDEO_QUEUE_TIMEOUT_SECONDS_ENV = "REMOTE_WORKER_PRODUCT_VIDEO_QUEUE_TIMEOUT_SECONDS"
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
    product_queue_timeout = _safe_int(env.get(REMOTE_WORKER_PRODUCT_VIDEO_QUEUE_TIMEOUT_SECONDS_ENV), 1800)
    return {
        "production_enabled": _env_bool(env, REMOTE_WORKER_PRODUCTION_ENABLED_ENV, False),
        "admin_canary_enabled": _env_bool(env, REMOTE_WORKER_ADMIN_CANARY_ENABLED_ENV, True),
        "public_enabled": _env_bool(env, REMOTE_WORKER_PUBLIC_ENABLED_ENV, False),
        "max_admin_canary_active": max(1, max_active),
        "product_video_queue_timeout_seconds": max(0, product_queue_timeout),
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
    safe_placeholders: dict[str, str] = {}
    for index, code in enumerate(SAFE_DIAGNOSTIC_CODES):
        placeholder = f"SAFE_DIAG_CODE_{index}"
        text = re.sub(re.escape(code), placeholder, text, flags=re.IGNORECASE)
        safe_placeholders[placeholder] = code
    text = re.sub(r"(?i)(bearer|authorization)\s+[A-Za-z0-9._~+/=-]+", r"\1 <redacted>", text)
    for marker in SECRET_KEY_MARKERS:
        text = re.sub(rf"(?i){re.escape(marker)}[A-Za-z0-9_.:/=+\-]*", f"{marker}=<redacted>", text)
    text = re.sub(r"[A-Za-z0-9_-]{24,}", "<redacted>", text)
    for placeholder, code in safe_placeholders.items():
        text = text.replace(placeholder, code)
    return text[:500]


def safe_worker_reason_code(value: Any, fallback: str = "-") -> str:
    text = scrub_secret_text(value).strip()
    if not text or text == "-":
        return fallback
    lowered = text.lower()
    known_codes = (
        "product_video_worker_unavailable",
        "real_video_renderer_unavailable",
        "not_claimed_timeout",
        "admin_canary_disabled",
        "no_admin_canary_job",
        "no_owner_product_video_job",
        "no_product_video_job",
        "public_product_worker_disabled_or_no_owner_job",
        "capability_not_supported",
        "product_video_capability_required",
        "admin_canary_capability_required",
        "admin_video_capability_required",
        "ffmpeg_missing",
        "upload_failed",
        "lease_expired_requeued",
    )
    for code in known_codes:
        if code in lowered:
            return code
    if "runtimeerror" in lowered and "redacted" in lowered:
        return "runtime_error_redacted"
    if lowered.strip("<>:_- ") == "redacted":
        return "redacted_error"
    if "httperror" in lowered or "http " in lowered:
        match = re.search(r"\b(401|403|404|429|500|502|503|504)\b", lowered)
        return f"http_{match.group(1)}" if match else "http_error"
    if "urlerror" in lowered or "timeout" in lowered:
        return "network_or_timeout"
    cleaned = re.sub(r"[^a-z0-9_.:-]+", "_", lowered).strip("_")
    return (cleaned[:100] or fallback)


def _parse_queue_time(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for parser in (
        lambda item: datetime.fromisoformat(item.replace("Z", "+00:00")),
        lambda item: datetime.strptime(item[:19], "%Y-%m-%d %H:%M:%S"),
        lambda item: datetime.strptime(item[:19], "%Y-%m-%dT%H:%M:%S"),
    ):
        try:
            parsed = parser(raw)
            if parsed.tzinfo is not None:
                parsed = parsed.replace(tzinfo=None)
            return parsed
        except Exception:
            continue
    return None

def classify_remote_worker_error(value: Any, *, status: str = "", worker_id: str = "") -> dict[str, str]:
    raw = scrub_secret_text(value)
    lowered = raw.lower()
    status_text = str(status or "").strip().lower()
    if status_text == "failed" and not str(worker_id or "").strip() and not raw:
        return {
            "error_type": "worker_not_claimed",
            "reason_code": "not_claimed_timeout",
            "stage": "waiting_worker",
            "raw": "",
        }
    if not raw:
        return {"error_type": "", "reason_code": "", "stage": "", "raw": ""}
    head = re.split(r"[:;\s]+", raw, maxsplit=1)[0].strip().lower()
    error_type = re.sub(r"[^a-z0-9_]+", "_", head) or "worker_error"
    if "runtimeerror" in error_type:
        error_type = "worker_runtime_error"
    elif "sqlite" in error_type or "database" in lowered:
        error_type = "db_error"
    elif "provider" in lowered or "renderer" in lowered or "submit" in lowered:
        error_type = "provider_error"
    elif "ffmpeg" in lowered:
        error_type = "ffmpeg_error"
    elif "timeout" in lowered or "unavailable" in lowered:
        error_type = "worker_runtime_error"

    stage = ""
    if "not_claimed" in lowered or "worker_unavailable" in lowered:
        stage = "waiting_worker"
    elif "provider_submit" in lowered or "submit" in lowered:
        stage = "provider_submit_failed"
    elif "real_video_renderer_unavailable" in lowered or "renderer_unavailable" in lowered:
        stage = "provider_not_ready"
    elif "config" in lowered or "missing" in lowered:
        stage = "missing_config"
    elif "upload" in lowered or "result_file" in lowered:
        stage = "output_validation_failed"
    elif "ffmpeg" in lowered:
        stage = "ffmpeg_failed"
    elif "diagnostic" in lowered:
        stage = "diagnostic"
    elif "<redacted>" in lowered and len(lowered) <= 40:
        stage = error_type
    else:
        stage = error_type

    tail = raw.split(":", 1)[1].strip() if ":" in raw else raw
    reason = re.sub(r"[^A-Za-z0-9_.:-]+", "_", tail.lower()).strip("_")[:80]
    if not reason or reason in {"redacted", "redacted_"} or "<redacted>" in reason:
        reason = stage or error_type
    return {"error_type": error_type, "reason_code": reason, "stage": stage, "raw": raw}


def _result_file_exists(project: dict, result: dict | None = None) -> bool:
    payload = result if isinstance(result, dict) else {}
    artifact_meta = payload.get("artifact_storage") if isinstance(payload.get("artifact_storage"), dict) else {}
    if artifact_meta and (artifact_meta.get("recoverable") or artifact_meta.get("public_url") or artifact_meta.get("remote_path")):
        return True
    path = str(project.get("final_video_path") or payload.get("final_video_path") or "")
    if path:
        try:
            return os.path.exists(path) and os.path.getsize(path) > 0
        except OSError:
            return False
    return bool(project.get("final_video_file_id") or _safe_int(payload.get("uploaded_file_bytes") or payload.get("bytes"), 0) > 0)


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
    explicit_admin_video_delivery = source == REMOTE_WORKER_ADMIN_VIDEO_SOURCE
    render_mode = str(asset_pack.get("render_mode") or invoice.get("render_mode") or "").strip().lower().replace("-", "_")
    if render_mode in {"test_pattern", "admin_test"}:
        render_mode = RENDER_MODE_ADMIN_TEST_PATTERN
    elif render_mode not in {RENDER_MODE_REAL, RENDER_MODE_ADMIN_TEST_PATTERN, RENDER_MODE_UNAVAILABLE}:
        render_mode = RENDER_MODE_ADMIN_TEST_PATTERN if source == REMOTE_WORKER_ADMIN_VIDEO_SOURCE else RENDER_MODE_REAL
    return {
        "source": source,
        "render_mode": render_mode,
        "test_pattern": _safe_bool(asset_pack.get("test_pattern") or invoice.get("test_pattern")),
        "admin_video_delivery": explicit_admin_video_delivery
        and _safe_bool(
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


def _product_video_safety_flags(project: dict) -> dict:
    asset_pack = _json_loads(project.get("asset_pack_json"), {})
    invoice = _json_loads(project.get("invoice_json"), {})
    source = str(asset_pack.get("source") or invoice.get("source") or "")
    render_mode = str(asset_pack.get("render_mode") or invoice.get("render_mode") or "").strip().lower().replace("-", "_")
    if render_mode in {"test_pattern", "admin_test"}:
        render_mode = RENDER_MODE_ADMIN_TEST_PATTERN
    elif render_mode not in {RENDER_MODE_REAL, RENDER_MODE_ADMIN_TEST_PATTERN, RENDER_MODE_UNAVAILABLE}:
        render_mode = RENDER_MODE_REAL if source == REMOTE_WORKER_PRODUCT_VIDEO_SOURCE else ""
    return {
        "source": source,
        "render_mode": render_mode,
        "test_pattern": _safe_bool(
            asset_pack.get("test_pattern")
            or invoice.get("test_pattern")
            or asset_pack.get("safe_output_delivery_test")
            or invoice.get("safe_output_delivery_test")
        ),
        "admin_video_delivery": _safe_bool(
            asset_pack.get("admin_video_delivery")
            or invoice.get("admin_video_delivery")
            or asset_pack.get("owner_admin_test_mode")
            or invoice.get("owner_admin_test_mode")
        ),
        "admin_only": _safe_bool(asset_pack.get("admin_only") or invoice.get("admin_only")),
        "created_by_admin": _safe_bool(asset_pack.get("created_by_admin") or invoice.get("created_by_admin") or asset_pack.get("owner")),
        "no_charge": _safe_bool(asset_pack.get("no_charge") or invoice.get("no_charge") or asset_pack.get("admin_no_charge") or invoice.get("admin_no_charge"))
        or _safe_int(project.get("total_xu_estimated"), 0) == 0,
        "provider_call": _safe_bool(asset_pack.get("provider_call") or invoice.get("provider_call")),
        "public_user": _safe_bool(asset_pack.get("public_user") or invoice.get("public_user")),
        "fake_renderer_allowed": _safe_bool(asset_pack.get("fake_renderer_allowed") or invoice.get("fake_renderer_allowed")),
        "real_renderer_required": _safe_bool(asset_pack.get("real_renderer_required") or invoice.get("real_renderer_required")),
        "claim_only_diagnostic": _safe_bool(
            asset_pack.get("claim_only_diagnostic")
            or invoice.get("claim_only_diagnostic")
            or asset_pack.get("diagnostic_claim_only")
            or invoice.get("diagnostic_claim_only")
        ),
        "duration_seconds": max(1, _safe_int(asset_pack.get("duration_seconds") or invoice.get("duration_seconds"), 6)),
        "scene_count": max(1, min(20, _safe_int(asset_pack.get("scene_count") or invoice.get("scene_count") or project.get("scene_count"), 1))),
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


def is_remote_worker_product_video_job(job: dict | None = None, project: dict | None = None) -> bool:
    job = job or {}
    project = project or {}
    if str(job.get("job_type") or video_project_queue.VIDEO_RENDER_JOB_TYPE) != video_project_queue.VIDEO_RENDER_JOB_TYPE:
        return False
    if is_remote_worker_canary_job(job, project) or is_remote_worker_admin_canary_job(job, project):
        return False
    if is_remote_worker_admin_video_job(job, project) or _is_admin_fake_video_job(project):
        return False
    flags = _product_video_safety_flags(project)
    return bool(
        flags["source"] == REMOTE_WORKER_PRODUCT_VIDEO_SOURCE
        and flags["render_mode"] == RENDER_MODE_REAL
        and not flags["test_pattern"]
        and not flags["admin_video_delivery"]
        and not flags["fake_renderer_allowed"]
        and (flags["provider_call"] or flags["claim_only_diagnostic"])
    )


def _product_video_is_claimable(project: dict, *, owner_only: bool = False, public_enabled: bool = False) -> bool:
    if not is_remote_worker_product_video_job({"job_type": video_project_queue.VIDEO_RENDER_JOB_TYPE}, project):
        return False
    flags = _product_video_safety_flags(project)
    owner_product = bool(flags["admin_only"] and flags["no_charge"] and not flags["public_user"])
    if owner_only:
        return owner_product
    return bool(flags["public_user"] and public_enabled)


def explain_admin_canary_claimability(conn: sqlite3.Connection, job_id: int | str) -> dict:
    wanted = _safe_int(job_id, 0)
    if wanted <= 0:
        return {"ok": False, "claimable": False, "reason": "job_id_required"}
    job = video_project_queue.get_video_render_job(conn, wanted)
    if not job:
        return {"ok": False, "claimable": False, "reason": "job_not_found"}
    project = video_project_queue.get_video_project(conn, int(job.get("project_id") or 0))
    if not project:
        return {"ok": False, "claimable": False, "reason": "project_not_found", "job_id": wanted}
    flags = _admin_canary_safety_flags(project)
    status = str(job.get("status") or "")
    project_status = str(project.get("status") or "")
    reason = ""
    if str(job.get("job_type") or "") != video_project_queue.VIDEO_RENDER_JOB_TYPE:
        reason = "job_type_not_video_render"
    elif status != "queued":
        reason = f"job_status_{status or 'missing'}"
    elif _safe_int(project.get("is_confirmed"), 0) != 1:
        reason = "project_not_confirmed"
    elif project_status not in {"queued_for_worker", "processing"}:
        reason = f"project_status_{project_status or 'missing'}"
    elif not is_remote_worker_admin_canary_job(job, project):
        reason = "not_admin_canary_payload"
    elif not _admin_canary_is_safe(project):
        reason = "admin_canary_safety_mismatch"
    claimable = not bool(reason)
    return {
        "ok": True,
        "claimable": claimable,
        "reason": "" if claimable else reason,
        "job_id": wanted,
        "project_id": int(project.get("project_id") or 0),
        "job_status": status,
        "project_status": project_status,
        "worker_claimed": bool(job.get("locked_by")),
        "worker_id": sanitize_worker_id(str(job.get("locked_by") or "")) if job.get("locked_by") else "",
        "flags": flags,
    }


def explain_product_video_claimability(
    conn: sqlite3.Connection,
    job_id: int | str,
    *,
    owner_only: bool = False,
    public_enabled: bool = False,
) -> dict:
    wanted = _safe_int(job_id, 0)
    if wanted <= 0:
        return {"ok": False, "claimable": False, "reason": "job_id_required"}
    job = video_project_queue.get_video_render_job(conn, wanted)
    if not job:
        return {"ok": False, "claimable": False, "reason": "job_not_found"}
    project = video_project_queue.get_video_project(conn, int(job.get("project_id") or 0))
    if not project:
        return {"ok": False, "claimable": False, "reason": "project_not_found", "job_id": wanted}
    flags = _product_video_safety_flags(project)
    status = str(job.get("status") or "")
    project_status = str(project.get("status") or "")
    owner_product = bool(flags["admin_only"] and flags["no_charge"] and not flags["public_user"])
    reason = ""
    if str(job.get("job_type") or "") != video_project_queue.VIDEO_RENDER_JOB_TYPE:
        reason = "job_type_not_video_render"
    elif status != "queued":
        reason = f"job_status_{status or 'missing'}"
    elif _safe_int(project.get("is_confirmed"), 0) != 1:
        reason = "project_not_confirmed"
    elif project_status not in {"queued_for_worker", "processing"}:
        reason = f"project_status_{project_status or 'missing'}"
    elif not is_remote_worker_product_video_job(job, project):
        reason = "not_product_video_real_payload"
    elif owner_only and not owner_product:
        reason = "owner_product_filter_mismatch"
    elif not owner_only and not owner_product and not (flags["public_user"] and public_enabled):
        reason = "public_product_worker_disabled_or_no_owner_job"
    claimable = not bool(reason)
    return {
        "ok": True,
        "claimable": claimable,
        "reason": "" if claimable else reason,
        "job_id": wanted,
        "project_id": int(project.get("project_id") or 0),
        "job_status": status,
        "project_status": project_status,
        "worker_claimed": bool(job.get("locked_by")),
        "worker_id": sanitize_worker_id(str(job.get("locked_by") or "")) if job.get("locked_by") else "",
        "owner_only": bool(owner_only),
        "public_enabled": bool(public_enabled),
        "flags": flags,
    }


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
    invoice = strip_secret_fields(_json_loads(project.get("invoice_json"), {}))
    addon_plan = strip_secret_fields(_json_loads(project.get("addon_plan_json"), {}))
    quality_source = project.get("quality_tier")
    if quality_source in (None, ""):
        quality_source = hydrated_job.get("quality_tier")
    quality_tier = _safe_int(quality_source, 200)
    scene_count = max(1, _safe_int(project.get("scene_count") or len(scene_cards) or 1, 1))
    ratio = str(project.get("ratio") or "9:16")
    render_mode = str(asset_pack.get("render_mode") or invoice.get("render_mode") or RENDER_MODE_REAL).strip().lower().replace("-", "_")
    if render_mode in {"test_pattern", "admin_test"}:
        render_mode = RENDER_MODE_ADMIN_TEST_PATTERN
    if render_mode not in {RENDER_MODE_REAL, RENDER_MODE_ADMIN_TEST_PATTERN, RENDER_MODE_UNAVAILABLE}:
        render_mode = RENDER_MODE_REAL
    original_user_prompt = str(
        asset_pack.get("original_user_prompt")
        or asset_pack.get("cleaned_user_prompt")
        or project.get("prompt_text")
        or project.get("topic")
        or ""
    )[:8000]
    cleaned_user_prompt = re.sub(r"\s+", " ", str(asset_pack.get("cleaned_user_prompt") or original_user_prompt or "")).strip()[:8000]
    provider_order = asset_pack.get("provider_order") or invoice.get("provider_order") or "shopaikey,key4u"
    source = str(asset_pack.get("source") or invoice.get("source") or REMOTE_WORKER_PRODUCT_VIDEO_SOURCE)
    product_type = str(
        asset_pack.get("product_type")
        or asset_pack.get("video_product_type")
        or invoice.get("product_type")
        or project.get("profile_id")
        or ""
    )
    engine_adapter = str(asset_pack.get("engine_adapter") or invoice.get("engine_adapter") or "")
    admin_only = _safe_bool(asset_pack.get("admin_only") or invoice.get("admin_only"))
    no_charge = _safe_bool(asset_pack.get("no_charge") or invoice.get("no_charge"))
    public_user = _safe_bool(asset_pack.get("public_user") or invoice.get("public_user"))
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
        "product_type": product_type,
        "video_flow": product_type,
        "engine_adapter": engine_adapter,
        "topic": str(project.get("topic") or "")[:500],
        "prompt_text": str(project.get("prompt_text") or "")[:8000],
        "original_user_prompt": original_user_prompt,
        "cleaned_user_prompt": cleaned_user_prompt,
        "scene_cards": scene_cards,
        "asset_pack": asset_pack,
        "addon_plan": addon_plan,
        "quality_tier": quality_tier,
        "package_xu": quality_tier,
        "scene_count": scene_count,
        "aspect_ratio": ratio,
        "expected_duration_seconds": max(1, scene_count * 6),
        "provider_order": provider_order,
        "render_mode": render_mode,
        "test_pattern": False,
        "admin_video_delivery": False,
        "admin_only": bool(admin_only),
        "no_charge": bool(no_charge),
        "provider_call": render_mode == RENDER_MODE_REAL,
        "public_user": bool(public_user),
        "source": source,
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
    if is_remote_worker_product_video_job(hydrated_job, project):
        safety = _product_video_safety_flags(project)
        claim_only = bool(safety["claim_only_diagnostic"])
        payload.update(
            {
                "product_video": True,
                "claim_only_diagnostic": claim_only,
                "diagnostic_claim_only": claim_only,
                "render_mode": RENDER_MODE_REAL,
                "test_pattern": False,
                "admin_video_delivery": False,
                "admin_only": bool(safety["admin_only"]),
                "no_charge": bool(safety["no_charge"]),
                "provider_call": bool(safety["provider_call"]) and not claim_only,
                "public_user": bool(safety["public_user"]),
                "source": REMOTE_WORKER_PRODUCT_VIDEO_SOURCE,
                "expected_duration_seconds": max(1, min(120, safety["duration_seconds"] or scene_count * 6)),
                "scene_count": max(1, min(20, safety["scene_count"] or scene_count)),
            }
        )
        payload["output_requirements"].update(
            {
                "product_video_mp4": True,
                "real_renderer_required": True,
                "provider_call": bool(safety["provider_call"]) and not claim_only,
                "final_video_bytes_gt_zero": not claim_only,
                "claim_only_diagnostic": claim_only,
            }
        )
    if is_remote_worker_admin_video_job(hydrated_job, project) or _is_admin_fake_video_job(project):
        safety = _admin_video_safety_flags(project)
        admin_render_mode = RENDER_MODE_ADMIN_TEST_PATTERN if (_is_admin_fake_video_job(project) or safety["test_pattern"]) else (safety["render_mode"] or RENDER_MODE_REAL)
        payload.update(
            {
                "admin_video_delivery": True,
                "render_mode": admin_render_mode,
                "test_pattern": bool(safety["test_pattern"] or admin_render_mode == RENDER_MODE_ADMIN_TEST_PATTERN),
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
    product_video_only: bool = False,
    owner_product_video_only: bool = False,
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
            if product_video_only or owner_product_video_only:
                if _product_video_is_claimable(
                    project,
                    owner_only=bool(owner_product_video_only),
                    public_enabled=bool(public_enabled),
                ):
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
        elif product_video_only or owner_product_video_only:
            progress_message = "product video claimed"
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
        product_video_only=False,
        owner_product_video_only=False,
        public_enabled=False,
    )


def claim_remote_worker_product_video_job(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    lease_seconds: int = 600,
    public_enabled: bool = False,
    owner_only: bool = False,
    now: datetime | None = None,
) -> dict:
    return _claim_video_render_candidate(
        conn,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
        now=now,
        admin_canary_only=False,
        admin_video_only=False,
        product_video_only=True,
        owner_product_video_only=bool(owner_only),
        public_enabled=bool(public_enabled),
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
        product_video_only=False,
        owner_product_video_only=False,
        public_enabled=public_enabled,
    )


def _queued_video_render_candidates(conn: sqlite3.Connection) -> list[tuple[dict, dict]]:
    video_project_queue.ensure_video_project_queue_schema(conn)
    rows = conn.execute(
        """SELECT j.id,j.project_id,j.user_id,j.job_type,
                  p.asset_pack_json,p.invoice_json,p.total_xu_estimated,p.profile_id,p.topic,p.status
           FROM video_jobs j
           JOIN video_projects p ON p.project_id=j.project_id
           WHERE j.job_type=? AND j.status='queued'
             AND COALESCE(p.is_confirmed,0)=1
             AND p.status IN ('queued_for_worker','processing')
           ORDER BY j.priority ASC, j.created_at ASC, j.id ASC
           LIMIT 100""",
        (video_project_queue.VIDEO_RENDER_JOB_TYPE,),
    ).fetchall()
    result: list[tuple[dict, dict]] = []
    for row in rows:
        job = {"id": row[0], "project_id": row[1], "user_id": row[2], "job_type": row[3]}
        project = {
            "project_id": row[1],
            "user_id": row[2],
            "asset_pack_json": row[4],
            "invoice_json": row[5],
            "total_xu_estimated": row[6],
            "profile_id": row[7],
            "topic": row[8],
            "status": row[9],
        }
        result.append((job, project))
    return result


def remote_worker_claim_lane_counts(conn: sqlite3.Connection, *, public_enabled: bool = False) -> dict:
    counts = {
        "admin_canary": 0,
        "owner_product_video": 0,
        "admin_video": 0,
        "public_product_video": 0,
        "public_gate_blocked": 0,
        "filter_mismatch": 0,
        "queued_total": 0,
    }
    for job, project in _queued_video_render_candidates(conn):
        counts["queued_total"] += 1
        if _admin_canary_is_safe(project):
            counts["admin_canary"] += 1
            continue
        if _admin_video_is_safe(project):
            counts["admin_video"] += 1
            continue
        if is_remote_worker_product_video_job(job, project):
            flags = _product_video_safety_flags(project)
            owner_product = bool(flags["admin_only"] and flags["no_charge"] and not flags["public_user"])
            if owner_product:
                counts["owner_product_video"] += 1
            elif flags["public_user"] and public_enabled:
                counts["public_product_video"] += 1
            elif flags["public_user"] and not public_enabled:
                counts["public_gate_blocked"] += 1
            else:
                counts["filter_mismatch"] += 1
            continue
        counts["filter_mismatch"] += 1
    return counts


def _latest_video_claim_summary(conn: sqlite3.Connection, *, source: str, claim_lane: str) -> dict:
    video_project_queue.ensure_video_project_queue_schema(conn)
    row = conn.execute(
        """SELECT j.id,j.project_id,j.status,j.locked_by,j.locked_at,j.updated_at,j.progress_percent,j.progress_message,j.last_error,
                  p.asset_pack_json,p.invoice_json,p.total_xu_estimated,p.status
           FROM video_jobs j
           JOIN video_projects p ON p.project_id=j.project_id
           WHERE j.job_type=? AND COALESCE(p.asset_pack_json,'') LIKE ?
           ORDER BY j.id DESC LIMIT 1""",
        (video_project_queue.VIDEO_RENDER_JOB_TYPE, f"%{source}%"),
    ).fetchone()
    if not row:
        return {"ok": False, "reason": "not_found", "claim_lane": claim_lane}
    project = {
        "project_id": row[1],
        "asset_pack_json": row[9],
        "invoice_json": row[10],
        "total_xu_estimated": row[11],
        "status": row[12],
    }
    status = str(row[2] or "").strip().lower()
    locked_by = sanitize_worker_id(str(row[3] or "")) if row[3] else ""
    reason_code = safe_worker_reason_code(row[8])
    flags = _admin_canary_safety_flags(project) if source == REMOTE_WORKER_ADMIN_CANARY_SOURCE else _product_video_safety_flags(project)
    if source == REMOTE_WORKER_ADMIN_CANARY_SOURCE:
        claimable = bool(_admin_canary_is_safe(project) and status == "queued")
    else:
        claimable = bool(_product_video_is_claimable(project, owner_only=True, public_enabled=False) and status == "queued")
    mismatch = "-" if claimable else ("not_queued" if status != "queued" else "filter_mismatch")
    return {
        "ok": True,
        "job_id": int(row[0]),
        "status": status,
        "worker_id": locked_by,
        "claimed_at": str(row[4] or ""),
        "updated_at": str(row[5] or ""),
        "progress_percent": _safe_int(row[6], 0),
        "progress_message": scrub_secret_text(row[7] or ""),
        "reason_code": reason_code,
        "claim_lane": claim_lane,
        "claimable": claimable,
        "not_claimable_reason": mismatch,
        "flags": strip_secret_fields(flags),
    }


def remote_worker_claim_debug_snapshot(
    conn: sqlite3.Connection,
    *,
    claim_route: str = "",
    public_enabled: bool | None = None,
) -> dict:
    config = remote_worker_production_guard_config()
    public_gate = bool(config["public_enabled"] if public_enabled is None else public_enabled)
    return {
        "claim_route": str(claim_route or ""),
        "public_worker_enabled": public_gate,
        "lane_counts": remote_worker_claim_lane_counts(conn, public_enabled=public_gate),
        "latest_admin_canary": _latest_video_claim_summary(conn, source=REMOTE_WORKER_ADMIN_CANARY_SOURCE, claim_lane="admin_canary"),
        "latest_product_diagnostic": _latest_video_claim_summary(conn, source=REMOTE_WORKER_PRODUCT_VIDEO_SOURCE, claim_lane="owner_product_video"),
    }


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
    product_video_only: bool = False,
    owner_product_video_only: bool = False,
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
        return {
            "ok": True,
            "job": build_worker_job_payload(hydrated) if hydrated else None,
            "admin_canary_only": True,
            "reason": "" if hydrated else "no_admin_canary_job",
            "debug": {} if hydrated else remote_worker_claim_debug_snapshot(conn, claim_route="admin_canary"),
        }
    if admin_video_only:
        if requested and REMOTE_WORKER_ADMIN_VIDEO_CAPABILITY not in requested:
            return {"ok": True, "job": None, "reason": "admin_video_capability_required"}
        job = claim_remote_worker_admin_video_job(conn, worker_id=worker, lease_seconds=lease_seconds)
        hydrated = video_project_queue.hydrate_video_job_payload(conn, job) if job else {}
        return {
            "ok": True,
            "job": build_worker_job_payload(hydrated) if hydrated else None,
            "admin_video_only": True,
            "reason": "" if hydrated else "no_admin_video_job",
            "debug": {} if hydrated else remote_worker_claim_debug_snapshot(conn, claim_route="admin_video"),
        }
    if product_video_only or owner_product_video_only:
        product_caps = {REMOTE_WORKER_PRODUCT_VIDEO_CAPABILITY, REMOTE_WORKER_OWNER_PRODUCT_VIDEO_CAPABILITY}
        if requested and not (requested & product_caps):
            return {"ok": True, "job": None, "reason": "product_video_capability_required"}
        config = remote_worker_production_guard_config()
        public_enabled = bool(config["public_enabled"]) and not bool(owner_product_video_only)
        job = claim_remote_worker_product_video_job(
            conn,
            worker_id=worker,
            lease_seconds=lease_seconds,
            public_enabled=public_enabled,
            owner_only=bool(owner_product_video_only),
        )
        hydrated = video_project_queue.hydrate_video_job_payload(conn, job) if job else {}
        if hydrated:
            reason = ""
        elif owner_product_video_only:
            reason = "no_owner_product_video_job"
        elif not public_enabled:
            reason = "public_product_worker_disabled_or_no_owner_job"
        else:
            reason = "no_product_video_job"
        return {
            "ok": True,
            "job": build_worker_job_payload(hydrated) if hydrated else None,
            "product_video_only": bool(product_video_only),
            "owner_product_video_only": bool(owner_product_video_only),
            "reason": reason,
            "debug": {} if hydrated else remote_worker_claim_debug_snapshot(
                conn,
                claim_route="owner_product_video" if owner_product_video_only else "product_video",
                public_enabled=public_enabled,
            ),
        }
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
    return {
        "ok": True,
        "job": build_worker_job_payload(hydrated) if hydrated else None,
        "reason": reason,
        "debug": {} if hydrated else remote_worker_claim_debug_snapshot(conn, claim_route="default_render", public_enabled=bool(config["public_enabled"])),
    }


def fail_stale_product_video_jobs(
    conn: sqlite3.Connection,
    *,
    max_wait_seconds: int | None = None,
    now: datetime | None = None,
    job_id: int | str = 0,
    reason: str = "product_video_worker_unavailable",
) -> int:
    video_project_queue.ensure_video_project_queue_schema(conn)
    timeout = _safe_int(max_wait_seconds, -1)
    if timeout < 0:
        timeout = _safe_int(remote_worker_production_guard_config().get("product_video_queue_timeout_seconds"), 1800)
    if timeout <= 0:
        return 0
    current_dt = now or datetime.now()
    cutoff = video_project_queue.now_text(current_dt - timedelta(seconds=timeout))
    params: list[Any] = [video_project_queue.VIDEO_RENDER_JOB_TYPE, cutoff]
    where_job = ""
    wanted_job_id = _safe_int(job_id, 0)
    if wanted_job_id:
        where_job = " AND j.id=?"
        params.append(wanted_job_id)
    rows = conn.execute(
        f"""SELECT j.id,j.project_id
            FROM video_jobs j
            JOIN video_projects p ON p.project_id=j.project_id
            WHERE j.job_type=? AND j.status='queued'
              AND COALESCE(p.is_confirmed,0)=1
              AND p.status IN ('queued_for_worker','processing')
              AND COALESCE(j.created_at,j.updated_at,'') < ?{where_job}
            ORDER BY j.created_at ASC, j.id ASC
            LIMIT 50""",
        params,
    ).fetchall()
    failed = 0
    for row in rows:
        job = video_project_queue.get_video_render_job(conn, int(row[0]))
        project = video_project_queue.get_video_project(conn, int(row[1]))
        if not is_remote_worker_product_video_job({"job_type": video_project_queue.VIDEO_RENDER_JOB_TYPE}, project):
            continue
        video_project_queue.fail_video_job(conn, job_id=int(job["id"]), error=reason, retry=False)
        failed += 1
    return failed


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


def _normalize_render_mode(value: Any, default: str = RENDER_MODE_REAL) -> str:
    mode = str(value or default or "").strip().lower().replace("-", "_")
    if mode in {"test_pattern", "admin_test"}:
        return RENDER_MODE_ADMIN_TEST_PATTERN
    if mode in {RENDER_MODE_REAL, RENDER_MODE_ADMIN_TEST_PATTERN, RENDER_MODE_UNAVAILABLE}:
        return mode
    return default


def _renderer_has_test_marker(renderer: str) -> bool:
    value = str(renderer or "").strip().lower()
    return any(marker in value for marker in ("fake", "test", "testsrc", "test_pattern", "canary"))


def _renderer_has_placeholder_marker(renderer: str) -> bool:
    value = str(renderer or "").strip().lower()
    return any(marker in value for marker in ("local_scene_composer", "local_placeholder", "text_slide", "color_slide", "placeholder"))


def _visual_classification(payload: dict) -> str:
    explicit = str(payload.get("visual_classification") or payload.get("final_classification") or "").strip()
    if explicit in {"final_ai_video", "partial_simple_video", "failed_no_real_visual"}:
        return explicit
    connector = str(payload.get("connector_renderer") or payload.get("renderer") or "")
    if _safe_bool(payload.get("raw_prompt_burned_into_frame")):
        return "failed_no_real_visual"
    if _safe_bool(payload.get("placeholder_detected") or payload.get("placeholder_visual")) or _renderer_has_placeholder_marker(connector):
        return "partial_simple_video"
    if _safe_bool(payload.get("provider_attempted")) or str(payload.get("visual_source") or "") in {"provider_mp4", "generated_scene_video", "generated_scene_image", "uploaded_image", "local_image_sequence"}:
        return "final_ai_video"
    return ""


def _fail_product_fake_output(conn: sqlite3.Connection, job_id: int, reason: str) -> dict:
    try:
        video_project_queue.fail_video_job(conn, job_id=int(job_id), error=reason, retry=False)
    except Exception:
        pass
    return {"ok": False, "reason": reason}


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
    payload = dict(result or {})
    project_render_mode = RENDER_MODE_ADMIN_TEST_PATTERN if _is_admin_fake_video_job(project) else (_admin_video_safety_flags(project)["render_mode"] if is_admin_video else RENDER_MODE_REAL)
    render_mode = _normalize_render_mode(payload.get("render_mode"), project_render_mode)
    renderer = str(payload.get("renderer") or "").strip().lower()
    connector_renderer = str(payload.get("connector_renderer") or renderer).strip().lower()
    product_admin_video_leak = _safe_bool(payload.get("admin_video_delivery")) and not is_admin_video
    test_pattern = _safe_bool(payload.get("test_pattern")) or render_mode == RENDER_MODE_ADMIN_TEST_PATTERN or _renderer_has_test_marker(renderer)
    classification = _visual_classification(payload)
    placeholder_visual = _safe_bool(payload.get("placeholder_detected") or payload.get("placeholder_visual")) or _renderer_has_placeholder_marker(connector_renderer)
    raw_prompt_burned = _safe_bool(payload.get("raw_prompt_burned_into_frame"))
    claim_only_diagnostic = bool(
        _safe_bool(payload.get("claim_only_diagnostic") or payload.get("diagnostic_claim_only"))
        and _safe_bool(payload.get("no_charge"))
        and not _safe_bool(payload.get("provider_call"))
        and not _safe_bool(payload.get("public_user"))
    )
    special_safe_job = bool(is_canary or is_admin_canary or is_admin_video or claim_only_diagnostic)
    if product_admin_video_leak and not special_safe_job:
        return _fail_product_fake_output(conn, int(job_id), "admin_video_delivery_not_allowed_for_product_video")
    if test_pattern and not special_safe_job:
        return _fail_product_fake_output(conn, int(job_id), "test_pattern_not_allowed_for_normal_video")
    if not special_safe_job and render_mode != RENDER_MODE_REAL:
        return _fail_product_fake_output(conn, int(job_id), "normal_video_requires_real_render_mode")
    if not special_safe_job and raw_prompt_burned:
        return _fail_product_fake_output(conn, int(job_id), "raw_prompt_text_not_allowed_in_product_video")
    if not special_safe_job and classification == "failed_no_real_visual":
        return _fail_product_fake_output(conn, int(job_id), "real_ai_visual_required_for_product_video")
    if not special_safe_job and placeholder_visual:
        partial_no_charge = classification == "partial_simple_video" and _safe_bool(payload.get("no_charge"))
        if not partial_no_charge:
            return _fail_product_fake_output(conn, int(job_id), "placeholder_video_not_final_product_video")
    if is_admin_video and render_mode not in {RENDER_MODE_REAL, RENDER_MODE_ADMIN_TEST_PATTERN}:
        return {"ok": False, "reason": "admin_video_invalid_render_mode"}
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
    if not special_safe_job:
        if final_video_file_id or str(payload.get("final_video_file_id") or "").strip():
            pass
        elif final_video_path:
            validation = validate_uploaded_result_file(final_video_path)
            if not validation.get("ok"):
                return {"ok": False, "reason": "product_result_file_missing"}
        else:
            return {"ok": False, "reason": "product_result_file_missing"}
    payload["render_mode"] = render_mode
    payload["test_pattern"] = bool(test_pattern)
    if classification:
        payload["visual_classification"] = classification
        payload["final_classification"] = classification
    if placeholder_visual:
        payload["placeholder_detected"] = True
        payload["placeholder_visual"] = True
    if classification == "partial_simple_video":
        payload["no_charge"] = True
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
    diagnostics: dict | None = None,
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
    if isinstance(diagnostics, dict) and diagnostics:
        existing = _json_loads(job.get("result_json"), {})
        if not isinstance(existing, dict):
            existing = {}
        diagnostic_payload = strip_secret_fields(dict(diagnostics or {}))
        diagnostic_payload["ok"] = False
        diagnostic_payload["worker_failed"] = True
        diagnostic_payload["worker_safe_error"] = scrub_secret_text(error)[:500]
        existing.update(diagnostic_payload)
        conn.execute("UPDATE video_jobs SET result_json=? WHERE id=?", (_json_dumps(existing), int(job_id)))
    pending_provider = bool(
        retryable
        and isinstance(diagnostics, dict)
        and (
            diagnostics.get("continue_polling")
            or str(diagnostics.get("blocker") or diagnostics.get("provider_error") or "").strip() == "provider_in_progress"
            or "provider_in_progress" in error
        )
    )
    if pending_provider:
        return video_project_queue.defer_video_job_for_provider_polling(
            conn,
            job_id=int(job_id),
            reason=str(diagnostics.get("provider_error") or diagnostics.get("blocker") or error or "provider_in_progress"),
            diagnostics=diagnostics,
        )
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
    status = str(job.get("status") or "")
    worker_id = sanitize_worker_id(str(job.get("locked_by") or "")) if job.get("locked_by") else ""
    claimed_at = str(job.get("locked_at") or job.get("started_at") or "")
    worker_had_claim = bool(worker_id or claimed_at or _safe_int(job.get("attempts"), 0) > 0)
    failure_diag = classify_remote_worker_error(job.get("last_error") or project.get("error_log") or "", status=status, worker_id=worker_id)
    progress_message = scrub_secret_text(job.get("progress_message") or "")
    stage = progress_message or status
    safe_failure = failure_diag["raw"]
    if status == "failed":
        if not worker_had_claim and not safe_failure:
            stage = "waiting_worker"
            safe_failure = "not_claimed_timeout"
            failure_diag = classify_remote_worker_error(safe_failure, status=status, worker_id=worker_id)
        elif failure_diag["stage"]:
            stage = failure_diag["stage"] or "worker_failed"
    return {
        "ok": True,
        "job_id": int(job.get("id") or 0),
        "canary_ref": f"RW-CANARY-{int(job.get('id') or 0)}",
        "status": status,
        "stage": stage,
        "worker_id": worker_id,
        "claimed_at": claimed_at,
        "last_heartbeat_at": str(job.get("updated_at") or ""),
        "progress_percent": _safe_int(job.get("progress_percent"), 0),
        "progress_message": progress_message,
        "result_uploaded": result_uploaded,
        "result_file_size": int(uploaded_bytes or 0),
        "sent_to_admin": bool(result.get("sent_to_admin")),
        "safe_failure_reason": safe_failure,
        "safe_error_type": failure_diag["error_type"],
        "safe_reason_code": failure_diag["reason_code"],
        "result_file_exists": _result_file_exists(project, result),
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
    worker_id = sanitize_worker_id(str(job.get("locked_by") or "")) if job.get("locked_by") else ""
    raw_status = str(job.get("status") or "").strip().lower()
    claimed_at = str(job.get("locked_at") or job.get("started_at") or "")
    worker_had_claim = bool(worker_id or claimed_at or _safe_int(job.get("attempts"), 0) > 0)
    safe_failure = scrub_secret_text(job.get("last_error") or project.get("error_log") or "")
    failure_diag = classify_remote_worker_error(safe_failure, status=raw_status, worker_id=worker_id)
    reason_code = safe_worker_reason_code(safe_failure)
    created_at = _parse_queue_time(job.get("created_at") or job.get("updated_at"))
    age_seconds = 0
    if created_at:
        age_seconds = max(0, int((datetime.now() - created_at).total_seconds()))
    never_claimed = not worker_id and not str(job.get("locked_at") or "").strip()
    timed_out_without_claim = bool(never_claimed and age_seconds >= 120)
    if timed_out_without_claim:
        display_status = "failed"
        stage = "not_claimed_timeout"
        reason_code = "not_claimed_timeout"
    elif raw_status in {"failed", "error"}:
        display_status = "failed"
        if not worker_had_claim and not safe_failure:
            stage = "waiting_worker"
            safe_failure = "not_claimed_timeout"
            failure_diag = classify_remote_worker_error(safe_failure, status=raw_status, worker_id=worker_id)
            reason_code = "not_claimed_timeout"
        elif not worker_had_claim:
            stage = "not_claimed_timeout"
            safe_failure = "not_claimed_timeout"
            failure_diag = classify_remote_worker_error(safe_failure, status=raw_status, worker_id=worker_id)
            reason_code = "not_claimed_timeout"
        elif failure_diag["stage"]:
            stage = reason_code if reason_code == "runtime_error_redacted" else failure_diag["stage"]
        else:
            stage = reason_code if reason_code != "-" else "failed"
    elif raw_status in {"completed", "done", "success"}:
        display_status = "completed"
        stage = "completed"
    elif raw_status in {"processing", "running"} or worker_id:
        display_status = "claimed"
        progress_stage = progress_message.strip().lower()
        stage = progress_message if progress_stage and progress_stage not in {"completed", "complete", "done", "success"} else "claimed"
    else:
        display_status = "queued"
        stage = "not_claimed_timeout" if age_seconds >= 120 and not worker_id else "queued"
        if stage == "not_claimed_timeout" and not safe_failure:
            safe_failure = "not_claimed_timeout"
            failure_diag = classify_remote_worker_error(safe_failure, status=raw_status, worker_id=worker_id)
            reason_code = "not_claimed_timeout"
    return {
        "ok": True,
        "job_id": int(job.get("id") or 0),
        "canary_ref": f"{REMOTE_WORKER_ADMIN_CANARY_REF_PREFIX}-{int(job.get('id') or 0)}",
        "raw_status": raw_status,
        "status": display_status,
        "stage": stage,
        "worker_id": worker_id,
        "claimed_at": claimed_at,
        "last_heartbeat_at": str(job.get("updated_at") or ""),
        "progress_percent": 0 if timed_out_without_claim else _safe_int(job.get("progress_percent"), 0),
        "progress_message": "" if timed_out_without_claim else progress_message,
        "result_uploaded": False if timed_out_without_claim else result_uploaded,
        "result_file_size": int(uploaded_bytes or 0),
        "sent_to_admin": bool(result.get("sent_to_admin")),
        "safe_failure_reason": safe_failure,
        "safe_failure_reason_code": reason_code,
        "reason_code": reason_code,
        "not_claimed_timeout": bool(timed_out_without_claim or reason_code == "not_claimed_timeout"),
        "age_seconds": age_seconds,
        "safe_error_type": failure_diag["error_type"],
        "safe_reason_code": failure_diag["reason_code"] or reason_code,
        "result_file_exists": _result_file_exists(project, result),
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


def remote_worker_product_video_queue_snapshot(conn: sqlite3.Connection) -> dict:
    video_project_queue.ensure_video_project_queue_schema(conn)
    rows = conn.execute(
        """SELECT j.id,j.status,j.locked_by,j.updated_at,j.progress_percent,j.progress_message,j.last_error,j.project_id,
                  j.result_json,p.final_video_path,p.error_log,j.started_at,j.attempts
           FROM video_jobs j
           JOIN video_projects p ON p.project_id=j.project_id
           WHERE j.job_type=? AND COALESCE(p.asset_pack_json,'') LIKE ?
           ORDER BY j.id DESC LIMIT 10""",
        (video_project_queue.VIDEO_RENDER_JOB_TYPE, f"%{REMOTE_WORKER_PRODUCT_VIDEO_SOURCE}%"),
    ).fetchall()
    items = []
    active = 0
    queued = 0
    for row in rows:
        project = video_project_queue.get_video_project(conn, int(row[7]))
        if not is_remote_worker_product_video_job({"job_type": video_project_queue.VIDEO_RENDER_JOB_TYPE}, project):
            continue
        status = str(row[1] or "")
        if status == "processing":
            active += 1
        if status == "queued":
            queued += 1
        flags = _product_video_safety_flags(project)
        status_lower = status.strip().lower()
        worker_id = sanitize_worker_id(str(row[2] or "")) if row[2] else ""
        worker_had_claim = bool(worker_id or row[11] or _safe_int(row[12], 0) > 0)
        error_text = scrub_secret_text(row[6] or project.get("error_log") or row[10] or "")
        failure_diag = classify_remote_worker_error(error_text, status=status, worker_id=worker_id)
        reason_code = safe_worker_reason_code(error_text)
        result = _json_loads(row[8], {})
        if not isinstance(result, dict):
            result = {}
        stage = scrub_secret_text(row[5] or "") or status
        if status == "failed":
            if not worker_had_claim and not error_text:
                stage = "waiting_worker"
                error_text = "not_claimed_timeout"
                failure_diag = classify_remote_worker_error(error_text, status=status, worker_id=worker_id)
            elif failure_diag["stage"]:
                stage = failure_diag["stage"] or "worker_failed"
        provider_route_attempted = bool(
            flags["provider_call"]
            and any(marker in f"{row[5] or ''} {error_text} {row[8] or ''}".lower() for marker in ("provider", "shopaikey", "key4u", "real_video", "submit"))
        )
        result_file_exists = _result_file_exists({**project, "final_video_path": row[9] or project.get("final_video_path")}, result)
        if status == "queued" and not worker_id:
            next_action = "run_owner_product_video_once"
        elif failure_diag["stage"] in {"provider_not_ready", "missing_config", "provider_submit_failed"}:
            next_action = "check_real_provider_config"
        elif worker_id:
            next_action = "check_owner_product_video_journal"
        else:
            next_action = "create_fresh_diagnostic_job"
        items.append(
            {
                "job_id": int(row[0]),
                "project_id": int(row[7]),
                "status": status,
                "stage": stage,
                "worker_claimed": bool(worker_id),
                "worker_id": worker_id,
                "updated_at": str(row[3] or ""),
                "progress_percent": _safe_int(row[4], 0),
                "progress_message": scrub_secret_text(row[5] or ""),
                "safe_failure_reason": error_text,
                "safe_failure_reason_code": reason_code,
                "reason_code": reason_code,
                "age_state": "old_failure" if status_lower in {"failed", "error"} else "",
                "safe_error_type": failure_diag["error_type"],
                "safe_reason_code": failure_diag["reason_code"] or reason_code,
                "provider_route_attempted": provider_route_attempted,
                "result_file_exists": result_file_exists,
                "next_action": next_action,
                "admin_only": bool(flags["admin_only"]),
                "no_charge": bool(flags["no_charge"]),
                "public_user": bool(flags["public_user"]),
                "provider_call": bool(flags["provider_call"]),
            }
        )
    return {
        "ok": True,
        "active": active,
        "queued": queued,
        "last": items[0] if items else {},
        "items": items,
    }


def create_product_video_worker_claim_test_job(
    conn: sqlite3.Connection,
    *,
    admin_user_id: int | str,
    scene_count: int = 1,
    duration_seconds: int = 6,
) -> dict:
    admin_id = _safe_int(admin_user_id, 0)
    if admin_id <= 0:
        return {"ok": False, "reason": "admin_user_id_required"}
    video_project_queue.ensure_video_project_queue_schema(conn)
    count = max(1, min(3, _safe_int(scene_count, 1)))
    duration = max(1, min(30, _safe_int(duration_seconds, count * 6)))
    now = video_project_queue.now_text()
    asset_pack = {
        "source": REMOTE_WORKER_PRODUCT_VIDEO_SOURCE,
        "render_mode": RENDER_MODE_REAL,
        "test_pattern": False,
        "admin_video_delivery": False,
        "owner_admin_test_mode": False,
        "safe_output_delivery_test": False,
        "fake_renderer_allowed": False,
        "real_renderer_required": True,
        "provider_call": False,
        "claim_only_diagnostic": True,
        "diagnostic_claim_only": True,
        "admin_only": True,
        "created_by_admin": True,
        "no_charge": True,
        "admin_no_charge": True,
        "public_user": False,
        "scene_count": count,
        "duration_seconds": duration,
        "original_user_prompt": "Admin diagnostic product video worker claim only.",
        "cleaned_user_prompt": "Admin diagnostic product video worker claim only.",
        "provider_order": "shopaikey,key4u",
    }
    project = video_project_queue.create_video_project(
        conn,
        user_id=admin_id,
        profile_id="product_video_worker_claim_test",
        topic="Product video worker claim diagnostic",
        ratio="9:16",
        asset_pack=asset_pack,
    )
    scene_cards = [
        {
            "scene_index": index,
            "role": "diagnostic",
            "script_text": f"Product worker claim diagnostic scene {index}.",
            "subtitle_line": "",
            "image_prompt": "",
            "video_prompt": "Simple product diagnostic scene, no test pattern, real provider route only.",
        }
        for index in range(1, count + 1)
    ]
    video_project_queue.save_video_project_storyboard(conn, int(project["project_id"]), {"scene_cards": scene_cards})
    video_project_queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="queued_for_worker",
        is_confirmed=1,
        confirmed_at=now,
        scene_count=count,
        prompt_text=asset_pack["original_user_prompt"],
        invoice_json={**asset_pack, "total_xu": 0},
        addon_plan_json={"source": REMOTE_WORKER_PRODUCT_VIDEO_SOURCE, "provider_call": False, "no_charge": True, "claim_only_diagnostic": True},
        total_xu_estimated=0,
    )
    job = video_project_queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=admin_id, max_attempts=1)
    video_project_queue.update_video_project(conn, int(project["project_id"]), job_id=int(job.get("id") or 0))
    return {"ok": True, "project": video_project_queue.get_video_project(conn, int(project["project_id"])), "job": job}


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
        "render_mode": RENDER_MODE_ADMIN_TEST_PATTERN,
        "test_pattern": True,
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
        "render_mode": RENDER_MODE_ADMIN_TEST_PATTERN,
        "test_pattern": True,
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
            "visual_goal": "Kiểm tra đường gửi file MP4 bằng test pattern kỹ thuật.",
            "provider_prompt": "Do not call provider. Generate an ADMIN TEST PATTERN local MP4.",
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
        prompt_text="OWNER/ADMIN TEST PATTERN video delivery output test. No customer job, no Xu, no provider call.",
        addon_plan_json={"source": REMOTE_WORKER_ADMIN_VIDEO_SOURCE, "provider_call": False, "no_charge": True, "render_mode": RENDER_MODE_ADMIN_TEST_PATTERN, "test_pattern": True},
        creative_control_json={"admin_video_delivery": True, "safe_output_delivery_test": True, "render_mode": RENDER_MODE_ADMIN_TEST_PATTERN, "test_pattern": True},
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
