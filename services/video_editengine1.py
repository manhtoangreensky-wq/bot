"""Persistent contract for the canonical local Video Edit engine.

The bot owns admission and billing.  The local worker owns FFmpeg rendering and
Telegram delivery.  This module keeps those two sides joined by an idempotent
job/outbox record without importing Telegram, wallet, or provider code.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime
from typing import Any


PRODUCT_TYPE = "video_edit"
WORKER_JOB_TYPE = "video_local_edit"
ENGINE_ROUTE = "local_worker_ffmpeg"
OUTBOX_OWNER = "local_video_edit"
WORKER_CAPABILITY = "video_edit"
HEARTBEAT_TTL_SECONDS = 90
IDEMPOTENCY_SCHEMA_VERSION = "video-edit-job-identity-v3"
PLAN_SCHEMA_VERSION = "video-edit-plan-v1"
TERMINAL_JOB_STATES = frozenset({"delivered", "charged", "failed_no_charge", "delivery_unknown"})


_MISSING = object()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _load(value: Any, default: Any) -> Any:
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return deepcopy(default)


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or value != value.strip():
        return False
    token = value.lower()
    return len(token) == 64 and all(char in "0123456789abcdef" for char in token)


def _valid_mp4_path_list(value: Any, *, output_count: int) -> bool:
    paths = [item.strip() for item in str(value or "").split(",") if item.strip()]
    return bool(paths) and len(paths) == int(output_count) and all(
        item.lower().endswith(".mp4") for item in paths
    )


def _valid_ffprobe_receipt(value: Any) -> bool:
    probe = dict(value or {}) if isinstance(value, dict) else {}
    try:
        duration_ms = _strict_nonnegative_int(
            probe.get("duration_ms"), reason="ffprobe_duration_invalid"
        )
        width = _strict_nonnegative_int(
            probe.get("width"), reason="ffprobe_width_invalid"
        )
        height = _strict_nonnegative_int(
            probe.get("height"), reason="ffprobe_height_invalid"
        )
    except ValueError:
        return False
    format_tokens = {
        token.strip().lower()
        for token in str(probe.get("format_name") or "").split(",")
        if token.strip()
    }
    return bool(
        probe.get("ok") is True
        and probe.get("has_video") is True
        and str(probe.get("video_codec") or "").lower() == "h264"
        and duration_ms > 0
        and width > 0
        and height > 0
        and "mp4" in format_tokens
    )


def valid_mp4_delivery_probe(value: Any) -> bool:
    """Public worker/server boundary check for one rendered MP4 probe."""

    return _valid_ffprobe_receipt(value)


def _path_identity(value: Any) -> str:
    return str(value or "").strip().replace("\\", "/").rstrip("/").lower()


def _strict_nonnegative_int(value: Any, *, reason: str) -> int:
    if isinstance(value, bool):
        raise ValueError(reason)
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        token = value.strip()
        digits = token[1:] if token[:1] in {"+", "-"} else token
        if not digits or not digits.isdigit():
            raise ValueError(reason)
        try:
            parsed = int(token)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(reason) from exc
    else:
        raise ValueError(reason)
    if parsed < 0:
        raise ValueError(reason)
    return parsed


def valid_local_free_rights_confirmation(
    value: Any,
    *,
    user_id: Any,
    expected_review_revision: Any,
) -> bool:
    """Validate the durable evidence produced by the final confirm edge."""

    if not isinstance(value, dict):
        return False
    expected_keys = {
        "confirmed",
        "policy",
        "user_id",
        "review_revision",
        "confirmed_at_unix",
    }
    if set(value) != expected_keys:
        return False
    review_revision = value.get("review_revision")
    confirmed_at = value.get("confirmed_at_unix")
    expected_revision_valid = bool(
        isinstance(expected_review_revision, int)
        and not isinstance(expected_review_revision, bool)
        and expected_review_revision > 0
    )
    return bool(
        value.get("confirmed") is True
        and str(value.get("policy") or "") == "video_edit_rights_v1"
        and str(value.get("user_id") or "") == str(user_id or "")
        and isinstance(review_revision, int)
        and not isinstance(review_revision, bool)
        and review_revision > 0
        and expected_revision_valid
        and review_revision == expected_review_revision
        and isinstance(confirmed_at, int)
        and not isinstance(confirmed_at, bool)
        and confirmed_at > 0
    )


def _telegram_message_id(value: Any) -> str:
    """Return one canonical positive Telegram message ID or an empty token."""

    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(value) if value > 0 else ""
    if not isinstance(value, str):
        return ""
    token = value.strip()
    if (
        token != value
        or not token
        or token.startswith("0")
        or any(char < "0" or char > "9" for char in token)
    ):
        return ""
    try:
        return token if int(token) > 0 else ""
    except (TypeError, ValueError, OverflowError):
        return ""


def _telegram_file_id(value: Any) -> str:
    """Return one bounded Telegram file ID without coercing foreign types."""

    if not isinstance(value, str):
        return ""
    token = value.strip()
    if (
        token != value
        or not token
        or len(token) > 512
        or any(ord(char) < 33 or ord(char) > 126 for char in token)
    ):
        return ""
    return token


def telegram_delivery_identity(value: Any) -> tuple[str, str]:
    """Normalize one accepted Telegram delivery result without coercion."""

    delivery = value if isinstance(value, dict) else {}
    if delivery.get("sent") is not True:
        return "", ""
    return (
        _telegram_message_id(delivery.get("message_id")),
        _telegram_file_id(delivery.get("file_id")),
    )


def _ensure_column(conn, table: str, column: str, definition: str) -> None:
    columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def ensure_schema(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS video_edit_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            idempotency_key TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            product_type TEXT NOT NULL DEFAULT 'video_edit',
            worker_job_type TEXT NOT NULL DEFAULT 'video_local_edit',
            engine_route TEXT NOT NULL DEFAULT 'local_worker_ffmpeg',
            worker_owner TEXT NOT NULL DEFAULT 'local_video_edit',
            edit_session_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            source_file_id TEXT NOT NULL,
            source_video_path TEXT NOT NULL DEFAULT '',
            source_sha256 TEXT NOT NULL DEFAULT '',
            source_metadata_json TEXT NOT NULL DEFAULT '{}',
            plan_json TEXT NOT NULL DEFAULT '{}',
            tail_json TEXT NOT NULL DEFAULT '{}',
            quality_tier_id TEXT NOT NULL DEFAULT '',
            price_xu INTEGER NOT NULL DEFAULT 0,
            local_worker_job_id INTEGER NOT NULL UNIQUE,
            progress_percent INTEGER NOT NULL DEFAULT 0,
            blocker TEXT NOT NULL DEFAULT '',
            output_file_id TEXT NOT NULL DEFAULT '',
            output_path TEXT NOT NULL DEFAULT '',
            output_sha256 TEXT NOT NULL DEFAULT '',
            output_size_bytes INTEGER NOT NULL DEFAULT 0,
            ffprobe_json TEXT NOT NULL DEFAULT '{}',
            delivery_message_id TEXT NOT NULL DEFAULT '',
            delivery_file_id TEXT NOT NULL DEFAULT '',
            artifact_receipts_json TEXT NOT NULL DEFAULT '[]',
            delivery_cursor INTEGER NOT NULL DEFAULT 0,
            receipt_state TEXT NOT NULL DEFAULT 'not_created',
            charge_state TEXT NOT NULL DEFAULT 'not_charged',
            charged_xu INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            started_at TEXT NOT NULL DEFAULT '',
            delivered_at TEXT NOT NULL DEFAULT '',
            charged_at TEXT NOT NULL DEFAULT '',
            finished_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        )"""
    )
    _ensure_column(conn, "video_edit_jobs", "worker_job_type", "TEXT NOT NULL DEFAULT 'video_local_edit'")
    _ensure_column(conn, "video_edit_jobs", "worker_owner", "TEXT NOT NULL DEFAULT 'local_video_edit'")
    _ensure_column(conn, "video_edit_jobs", "source_video_path", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "video_edit_jobs", "source_sha256", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "video_edit_jobs", "output_path", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "video_edit_jobs", "artifact_receipts_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "video_edit_jobs", "delivery_cursor", "INTEGER NOT NULL DEFAULT 0")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS video_edit_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            edit_job_id INTEGER NOT NULL UNIQUE,
            local_worker_job_id INTEGER NOT NULL UNIQUE,
            owner TEXT NOT NULL DEFAULT 'local_video_edit',
            status TEXT NOT NULL DEFAULT 'pending',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            available_at TEXT NOT NULL,
            lease_owner TEXT NOT NULL DEFAULT '',
            lease_expires_at TEXT NOT NULL DEFAULT '',
            terminal_reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_edit_jobs_user_status ON video_edit_jobs(user_id,status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_edit_outbox_owner_status ON video_edit_outbox(owner,status,available_at)")


def stable_idempotency_key(
    *,
    user_id: Any,
    edit_session_id: Any,
    plan: dict,
    quality_tier_id: Any,
    plan_schema_version: Any = _MISSING,
    source_file_id: Any = _MISSING,
    source_video_hash: Any = _MISSING,
    source_manifest: Any = _MISSING,
    concat_sources: Any = _MISSING,
    logo_source: Any = _MISSING,
    subtitle_source: Any = _MISSING,
    local1_mode: Any = _MISSING,
    split_mode: Any = _MISSING,
    split_ranges: Any = _MISSING,
    coverage_required: Any = _MISSING,
) -> str:
    legacy_material = {
        "user_id": str(user_id or ""),
        "edit_session_id": str(edit_session_id or ""),
        "plan": dict(plan or {}),
        "quality_tier_id": str(quality_tier_id or ""),
    }
    identity_values = (
        plan_schema_version,
        source_file_id,
        source_video_hash,
        source_manifest,
        concat_sources,
        logo_source,
        subtitle_source,
        local1_mode,
        split_mode,
        split_ranges,
        coverage_required,
    )
    if all(value is _MISSING for value in identity_values):
        material = _json(legacy_material)
    else:
        material = _json({
            **legacy_material,
            "idempotency_schema_version": IDEMPOTENCY_SCHEMA_VERSION,
            "plan_schema_version": str(
                PLAN_SCHEMA_VERSION if plan_schema_version is _MISSING else plan_schema_version or PLAN_SCHEMA_VERSION
            ),
            "source_file_id": str("" if source_file_id is _MISSING else source_file_id or ""),
            "source_video_hash": str("" if source_video_hash is _MISSING else source_video_hash or ""),
            "source_manifest": {} if source_manifest is _MISSING else source_manifest or {},
            "concat_sources": [] if concat_sources is _MISSING else concat_sources or [],
            "logo_source": {} if logo_source is _MISSING else logo_source or {},
            "subtitle_source": {} if subtitle_source is _MISSING else subtitle_source or {},
            "local1_mode": str("" if local1_mode is _MISSING else local1_mode or ""),
            "split_mode": str("" if split_mode is _MISSING else split_mode or ""),
            "split_ranges": [] if split_ranges is _MISSING else split_ranges or [],
            "coverage_required": (
                None if coverage_required is _MISSING else bool(coverage_required)
            ),
        })
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _historic_v2_idempotency_key(
    *,
    user_id: Any,
    edit_session_id: Any,
    plan: dict,
    quality_tier_id: Any,
    plan_schema_version: Any,
    source_file_id: Any,
    source_video_hash: Any,
    source_manifest: Any,
    concat_sources: Any,
    logo_source: Any,
    subtitle_source: Any,
) -> str:
    """Reproduce the immutable identity written by the historic v2 lane."""

    material = _json({
        "user_id": str(user_id or ""),
        "edit_session_id": str(edit_session_id or ""),
        "plan": dict(plan or {}),
        "quality_tier_id": str(quality_tier_id or ""),
        "idempotency_schema_version": "video-edit-job-identity-v2",
        "plan_schema_version": str(plan_schema_version or PLAN_SCHEMA_VERSION),
        "source_file_id": str(source_file_id or ""),
        "source_video_hash": str(source_video_hash or ""),
        "source_manifest": source_manifest or {},
        "concat_sources": concat_sources or [],
        "logo_source": logo_source or {},
        "subtitle_source": subtitle_source or {},
    })
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _strict_identity_dict(value: Any, *, field: str) -> dict[str, Any]:
    """Parse persisted identity JSON without silently replacing corruption."""

    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"legacy_idempotency_identity_unverifiable:{field}"
        ) from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"legacy_idempotency_identity_unverifiable:{field}")
    return parsed


def _artifact_receipts(value: Any) -> list[dict[str, Any]]:
    """Normalize complete per-artifact Telegram receipts in delivery order."""

    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    message_ids: set[str] = set()
    file_ids: set[str] = set()
    for position, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            return []
        try:
            index = _strict_nonnegative_int(
                item.get("index", position), reason="artifact_index_invalid"
            )
            size = _strict_nonnegative_int(
                item.get("size", item.get("output_size_bytes", 0)),
                reason="artifact_size_invalid",
            )
        except ValueError:
            return []
        raw_message_id = item.get("message_id", _MISSING)
        raw_legacy_message_id = item.get("delivery_message_id", _MISSING)
        message_id = _telegram_message_id(
            raw_legacy_message_id if raw_message_id is _MISSING else raw_message_id
        )
        legacy_message_id = (
            ""
            if raw_legacy_message_id is _MISSING
            else _telegram_message_id(raw_legacy_message_id)
        )
        raw_file_id = item.get("file_id", _MISSING)
        raw_legacy_file_id = item.get("delivery_file_id", _MISSING)
        file_id = _telegram_file_id(
            raw_legacy_file_id if raw_file_id is _MISSING else raw_file_id
        )
        legacy_file_id = (
            ""
            if raw_legacy_file_id is _MISSING
            else _telegram_file_id(raw_legacy_file_id)
        )
        sha256 = item.get("sha256", item.get("output_sha256", ""))
        raw_ffprobe = item.get("ffprobe")
        if not isinstance(raw_ffprobe, dict):
            return []
        ffprobe = dict(raw_ffprobe)
        if (
            index != position
            or not message_id
            or not file_id
            or (
                raw_message_id is not _MISSING
                and raw_legacy_message_id is not _MISSING
                and legacy_message_id != message_id
            )
            or (
                raw_file_id is not _MISSING
                and raw_legacy_file_id is not _MISSING
                and legacy_file_id != file_id
            )
            or message_id in message_ids
            or file_id in file_ids
            or size <= 0
            or not _is_sha256(sha256)
            or not _valid_ffprobe_receipt(ffprobe)
        ):
            return []
        message_ids.add(message_id)
        file_ids.add(file_id)
        normalized.append(
            {
                "index": index,
                "message_id": message_id,
                "file_id": file_id,
                "size": size,
                "sha256": sha256,
                "ffprobe": ffprobe,
            }
        )
    return normalized


def _artifact_receipts_valid(value: Any) -> bool:
    return isinstance(value, list) and (not value or bool(_artifact_receipts(value)))


def preflight(state: dict, runtime: dict) -> dict[str, Any]:
    """Return exact admission truth; this function has no side effects."""
    current = dict(state or {})
    metadata = current.get("source_metadata") if isinstance(current.get("source_metadata"), dict) else {}
    worker = dict(runtime or {})
    plan = current.get("manual_edit_plan") if isinstance(current.get("manual_edit_plan"), dict) else {}
    brightness = plan.get("brightness_percent", 100)
    try:
        brightness_valid = 20 <= int(brightness) <= 200
    except (TypeError, ValueError):
        brightness_valid = False
    try:
        heartbeat_contract_version = worker.get("heartbeat_contract_version")
        contract_enabled = (
            not isinstance(heartbeat_contract_version, bool)
            and int(heartbeat_contract_version or 0) >= 1
        )
    except (TypeError, ValueError):
        contract_enabled = False
    canonical_contract_required = not bool(plan.get("source"))
    capabilities = worker.get("capabilities")
    if isinstance(capabilities, str):
        capabilities = [item.strip() for item in capabilities.split(",") if item.strip()]
    capabilities = {str(item).strip() for item in capabilities or [] if str(item).strip()}
    heartbeat_age = worker.get("heartbeat_age_seconds", worker.get("age_seconds"))
    try:
        heartbeat_fresh = (
            heartbeat_age is not None
            and not isinstance(heartbeat_age, bool)
            and 0 <= int(heartbeat_age) <= HEARTBEAT_TTL_SECONDS
        )
    except (TypeError, ValueError):
        heartbeat_fresh = False
    checks = {
        "source_file": bool(str(current.get("source_file_id") or "").strip()),
        "source_probe": bool(current.get("inspection_complete") and metadata.get("ok")),
        "operation": bool(
            str(current.get("selected_tool") or "").strip()
            and (plan or list(current.get("split_ranges") or []))
        ),
        "brightness": brightness_valid,
        "worker_enabled": bool(worker.get("enabled")),
        "poll_enabled": bool(worker.get("poll_enabled")),
        "token_configured": bool(worker.get("token_configured")),
        "heartbeat": bool(worker.get("connected")),
        "ffmpeg": bool(worker.get("ffmpeg_path_configured") or worker.get("ffmpeg_seen")),
        "ffprobe": bool(worker.get("ffprobe_path_configured")),
        "delivery": bool(worker.get("delivery_configured", True)),
    }
    contract_checks = {
        "worker_owner": str(worker.get("worker_owner") or "") == OUTBOX_OWNER,
        "engine_route": str(worker.get("engine_route") or "") == ENGINE_ROUTE,
        "capability": WORKER_CAPABILITY in capabilities,
        "heartbeat_ttl": heartbeat_fresh,
    }
    plan_error = ""
    try:
        from services import video_local_editing
    except Exception:
        video_local_editing = None
    if video_local_editing is None:
        required_filters = set()
        plan_error = "video_local_editing_unavailable"
    else:
        try:
            source_duration_ms = int(
                metadata.get("duration_ms")
                or round(float(metadata.get("duration") or 0) * 1000)
            )
        except (TypeError, ValueError, OverflowError):
            source_duration_ms = 0
        if source_duration_ms <= 0:
            trim = plan.get("trim") if isinstance(plan.get("trim"), dict) else {}
            try:
                source_duration_ms = int(trim.get("end_ms") or 0)
            except (TypeError, ValueError, OverflowError):
                source_duration_ms = 0
        try:
            source_width = int(metadata.get("width") or 0)
            source_height = int(metadata.get("height") or 0)
        except (TypeError, ValueError, OverflowError):
            source_width = source_height = 0
        contract = video_local_editing.validate_manual_edit_plan_contract(
            plan,
            source_duration_ms=source_duration_ms,
            has_audio=bool(metadata.get("has_audio")),
            allow_empty=bool(current.get("split_ranges")),
            source_width=source_width,
            source_height=source_height,
            logo_source_present=bool(current.get("logo_source")),
            concat_sources_present=bool(current.get("concat_sources")),
        )
        required_filters = set(contract.get("required_filters") or [])
        split_selected = bool(
            str(current.get("selected_tool") or "").strip().lower() == "split"
            and current.get("split_ranges")
        )
        split_conflict = bool(
            split_selected
            and video_local_editing.split_plan_has_manual_conflict(
                plan,
                source_duration_ms=source_duration_ms,
                concat_sources=current.get("concat_sources") or [],
                logo_source=current.get("logo_source") or {},
                subtitle_source=current.get("subtitle_source") or {},
            )
        )
        if split_conflict:
            plan_error = "local_free_split_manual_conflict"
        elif split_selected:
            try:
                from services.video_smart_splitter import SplitRange

                ranges = []
                for position, item in enumerate(list(current.get("split_ranges") or []), start=1):
                    if not isinstance(item, dict):
                        raise ValueError
                    raw_index = item.get("index", position)
                    raw_start = item.get("start_ms")
                    raw_end = item.get("end_ms")
                    if any(isinstance(value, bool) for value in (raw_index, raw_start, raw_end)):
                        raise ValueError
                    ranges.append(
                        SplitRange(
                            index=int(raw_index),
                            start_ms=int(raw_start),
                            end_ms=int(raw_end),
                        )
                    )
                video_local_editing.validate_split_ranges(
                    ranges,
                    source_duration_ms=source_duration_ms,
                    coverage_required=bool(current.get("coverage_required", True)),
                )
            except Exception:
                plan_error = "local_free_split_plan_invalid"
        if plan.get("source") and not plan.get("input_video"):
            # Legacy tail-era preflight is retained for compatibility; the
            # canonical local lane carries an explicit plan and is gated by
            # the complete worker filter snapshot below.
            required_filters = set()
        if split_selected:
            required_filters.update({"format", "scale", "setsar"})
        checks["operation"] = bool(
            str(current.get("selected_tool") or "").strip()
            and (
                bool(plan.get("source"))
                or video_local_editing.plan_has_effective_operation(
                    plan,
                    source_duration_ms=source_duration_ms,
                    split_ranges=current.get("split_ranges"),
                )
            )
        )
        if not contract.get("ok") and not plan_error:
            plan_error = str(contract.get("reason") or "edit_plan_invalid")
    filter_snapshot_known = bool(worker.get("video_edit_filters_known"))
    available_filters = {
        str(item).strip()
        for item in (worker.get("video_edit_filters") or [])
        if str(item).strip()
    }
    snapshot_owner = str(worker.get("video_edit_filter_worker_id") or "").strip()
    worker_id = str(worker.get("worker_id") or "").strip()
    snapshot_owner_mismatch = bool(
        filter_snapshot_known
        and required_filters
        and (
            not worker_id
            or not snapshot_owner
            or snapshot_owner != worker_id
        )
    )
    snapshot_path = _path_identity(worker.get("video_edit_filter_ffmpeg_path"))
    worker_path = _path_identity(worker.get("ffmpeg_path") or worker.get("ffmpeg_path_seen"))
    snapshot_path_mismatch = bool(
        filter_snapshot_known
        and required_filters
        and (
            not worker_path
            or not snapshot_path
            or snapshot_path != worker_path
        )
    )
    filter_missing = sorted(required_filters - available_filters) if filter_snapshot_known else sorted(required_filters)
    new_contract_surface = bool(
        canonical_contract_required
        or "heartbeat_contract_version" in worker
        or "video_edit_filters_known" in worker
        or required_filters
        or plan_error
    )
    if new_contract_surface:
        checks["plan"] = not bool(plan_error)
        checks["filter_snapshot"] = bool(
            not required_filters
            or (
                filter_snapshot_known
                and not filter_missing
                and not snapshot_owner_mismatch
                and not snapshot_path_mismatch
            )
        )
    if required_filters:
        contract_checks["filter_snapshot"] = bool(
            filter_snapshot_known
            and not filter_missing
            and not snapshot_owner_mismatch
            and not snapshot_path_mismatch
        )
    if canonical_contract_required:
        checks["heartbeat_contract"] = contract_enabled
        checks.update(contract_checks)
    reason_order = [
        ("source_file", "source_file_missing"),
        ("source_probe", "source_probe_missing"),
        ("operation", "edit_operation_missing"),
        ("brightness", "brightness_invalid"),
        ("worker_enabled", "local_worker_disabled"),
        ("poll_enabled", "local_worker_poll_disabled"),
        ("token_configured", "local_worker_token_missing"),
        ("heartbeat", "local_worker_heartbeat_stale"),
        ("ffmpeg", "ffmpeg_missing"),
        ("ffprobe", "ffprobe_missing"),
        ("delivery", "telegram_delivery_unavailable"),
    ]
    if new_contract_surface:
        reason_order.insert(0, ("plan", plan_error or "edit_plan_invalid"))
        reason_order.insert(
            reason_order.index(("ffprobe", "ffprobe_missing")) + 1,
            ("filter_snapshot", "local_worker_filter_snapshot_missing"),
        )
    if canonical_contract_required:
        heartbeat_index = reason_order.index(("heartbeat", "local_worker_heartbeat_stale")) + 1
        reason_order[heartbeat_index:heartbeat_index] = [
            ("heartbeat_contract", "local_worker_contract_missing"),
            ("worker_owner", "local_worker_owner_mismatch"),
            ("engine_route", "local_worker_route_mismatch"),
            ("capability", "local_worker_capability_missing"),
            ("heartbeat_ttl", "local_worker_heartbeat_stale"),
        ]
    reason = next((code for key, code in reason_order if not checks[key]), "ok")
    if reason == "local_worker_filter_snapshot_missing":
        if snapshot_owner_mismatch:
            reason = "local_worker_filter_snapshot_owner_mismatch"
        elif snapshot_path_mismatch:
            reason = "local_worker_filter_snapshot_path_mismatch"
    audio = dict((current.get("video_tail9") or {}).get("audio_config") or {})
    unsupported = [key for key in ("dubbing", "music", "sfx", "subtitles") if audio.get(key)]
    if reason == "ok" and unsupported:
        reason = "local_edit_addon_runtime_unavailable"
    result = {
        "ok": reason == "ok",
        "ready": reason == "ok",
        "reason": reason,
        "blocker": "" if reason == "ok" else reason,
        "checks": checks,
        "unsupported_addons": unsupported,
        "product_type": PRODUCT_TYPE,
        "worker_job_type": WORKER_JOB_TYPE,
        "engine_route": ENGINE_ROUTE,
        "owner": OUTBOX_OWNER,
        "queue": "local_worker_jobs",
        "worker_id": str(worker.get("worker_id") or ""),
        "heartbeat_age_seconds": heartbeat_age,
    }
    if new_contract_surface:
        result["required_filters"] = sorted(required_filters)
        result["missing_filters"] = filter_missing
        if snapshot_owner_mismatch:
            result["filter_snapshot_reason"] = "local_worker_filter_snapshot_owner_mismatch"
        elif snapshot_path_mismatch:
            result["filter_snapshot_reason"] = "local_worker_filter_snapshot_path_mismatch"
    return result


def create_job(
    conn,
    *,
    user_id: Any,
    chat_id: Any,
    edit_session_id: str,
    source_file_id: str,
    source_metadata: dict,
    plan: dict,
    tail: dict,
    quality_tier_id: str,
    price_xu: int,
    worker_payload: dict,
) -> dict[str, Any]:
    """Create edit job, persistent outbox and worker queue row atomically."""
    ensure_schema(conn)
    normalized_price = _strict_nonnegative_int(price_xu, reason="price_xu_invalid")
    plan = deepcopy(dict(plan or {}))
    worker_payload = dict(worker_payload or {})
    if normalized_price > 0:
        paid_mode = worker_payload.get("local1_mode", _MISSING)
        split_intent = bool(
            worker_payload.get("split_ranges")
            or str(worker_payload.get("split_mode") or "").strip()
        )
        if paid_mode is _MISSING:
            if split_intent:
                raise ValueError("paid_local_mode_missing_with_split")
            # Historic paid writers predated the explicit mode field and only
            # supported the manual executor.  Stamp that one exact compatible
            # interpretation before identity generation and queue insertion.
            worker_payload["local1_mode"] = "manual"
        elif str(paid_mode or "").strip().lower() not in {"manual", "split"}:
            raise ValueError("paid_local_mode_invalid")
        else:
            worker_payload["local1_mode"] = str(paid_mode).strip().lower()
    submitted_plan = worker_payload.get("manual_edit_plan", _MISSING)
    identity_mode = str(worker_payload.get("local1_mode") or "").strip().lower()
    if normalized_price == 0 and identity_mode == "split":
        from services import video_local_editing

        if not video_local_editing.split_plan_has_manual_conflict(plan):
            plan = video_local_editing.neutral_split_manual_plan()
        if (
            isinstance(submitted_plan, dict)
            and not video_local_editing.split_plan_has_manual_conflict(submitted_plan)
        ):
            submitted_plan = video_local_editing.neutral_split_manual_plan()
    if submitted_plan is not _MISSING:
        if not isinstance(submitted_plan, dict):
            raise ValueError("worker_payload_identity_mismatch:manual_edit_plan")
        # The worker always replaces input_video with the downloaded path.
        # Bind every user-visible operation while treating that executor-owned
        # placeholder as outside the plan identity.
        submitted_identity = deepcopy(submitted_plan)
        canonical_identity = deepcopy(plan)
        submitted_identity.pop("input_video", None)
        canonical_identity.pop("input_video", None)
        if submitted_identity != canonical_identity:
            raise ValueError("worker_payload_identity_mismatch:manual_edit_plan")
    worker_payload["manual_edit_plan"] = deepcopy(plan)

    submitted_contract = worker_payload.get("local1_contract", _MISSING)
    if submitted_contract is not _MISSING:
        try:
            contract_version = _strict_nonnegative_int(
                submitted_contract, reason="local1_contract_invalid"
            )
        except ValueError as exc:
            raise ValueError("worker_payload_identity_mismatch:local1_contract") from exc
        if contract_version != 1:
            raise ValueError("worker_payload_identity_mismatch:local1_contract")
    worker_payload["local1_contract"] = 1

    canonical_tier = str(quality_tier_id or "")
    submitted_tier = worker_payload.get("quality_tier_id", _MISSING)
    if submitted_tier is not _MISSING and str(submitted_tier or "") != canonical_tier:
        raise ValueError("worker_payload_identity_mismatch:quality_tier_id")
    worker_payload["quality_tier_id"] = canonical_tier

    identity_bindings = {
        "user_id": str(user_id or ""),
        "chat_id": str(chat_id or ""),
        "edit_session_id": str(edit_session_id or ""),
        "source_file_id": str(source_file_id or ""),
    }
    for key, expected in identity_bindings.items():
        if key in worker_payload and str(worker_payload.get(key) or "") != expected:
            raise ValueError(f"worker_payload_identity_mismatch:{key}")
        worker_payload[key] = expected
    try:
        payload_price = _strict_nonnegative_int(
            worker_payload.get("price_xu", 0),
            reason="worker_price_invalid",
        )
        payload_quote = _strict_nonnegative_int(
            worker_payload.get("quoted_price_xu", 0),
            reason="worker_quote_invalid",
        )
    except ValueError:
        payload_price = payload_quote = -1
    # A zero-priced row is a local-free contract, never an incomplete paid
    # quote. Positive legacy rows remain writable only when every billing field
    # carries the same post-delivery truth; the public path never creates them.
    if normalized_price == 0 and (
        str(quality_tier_id or "") != "local-free"
        or dict(tail or {})
        or worker_payload.get("provider_call") is not False
        or str(worker_payload.get("charge_policy") or "") != "free_local_tool"
        or payload_price != 0
        or payload_quote != 0
    ):
        raise ValueError("local_free_contract_invalid")
    if normalized_price > 0:
        tail_data = dict(tail or {})
        pricing_snapshot = dict(tail_data.get("pricing_snapshot") or {})
        try:
            snapshot_total = _strict_nonnegative_int(
                pricing_snapshot.get("total_xu", normalized_price),
                reason="pricing_snapshot_total_invalid",
            )
        except ValueError:
            snapshot_total = -1
        if (
            str(quality_tier_id or "") in {"", "local-free"}
            or not tail_data
            or worker_payload.get("provider_call") is not False
            or str(worker_payload.get("charge_policy") or "") != "after_valid_mp4_delivery"
            or payload_price != normalized_price
            or payload_quote != normalized_price
            or snapshot_total != normalized_price
        ):
            raise ValueError("paid_local_contract_invalid")
    if normalized_price == 0:
        mode = str(worker_payload.get("local1_mode") or "").strip().lower()
        if mode not in {"manual", "split"}:
            raise ValueError("local_free_mode_invalid")
        if not valid_local_free_rights_confirmation(
            worker_payload.get("rights_confirmation"),
            user_id=user_id,
            expected_review_revision=worker_payload.get("state_revision"),
        ):
            raise ValueError("local_free_rights_confirmation_invalid")
        from services import video_local_editing

        try:
            source_duration_ms = int(
                dict(source_metadata or {}).get("duration_ms")
                or round(float(dict(source_metadata or {}).get("duration") or 0) * 1000)
            )
        except (TypeError, ValueError, OverflowError):
            source_duration_ms = 0
        if mode == "manual":
            if "source" in plan:
                raise ValueError("local_free_legacy_plan_invalid")

            raw_concat_sources = worker_payload.get("concat_sources") or []
            raw_logo_source = worker_payload.get("logo_source") or {}
            raw_subtitle_source = worker_payload.get("subtitle_source") or {}
            if (
                not isinstance(raw_concat_sources, list)
                or any(
                    not isinstance(item, dict) or not str(item.get("file_id") or "").strip()
                    for item in raw_concat_sources
                )
                or not isinstance(raw_logo_source, dict)
                or not isinstance(raw_subtitle_source, dict)
                or (raw_logo_source and not str(raw_logo_source.get("file_id") or "").strip())
                or (raw_subtitle_source and not str(raw_subtitle_source.get("file_id") or "").strip())
            ):
                raise ValueError("local_free_asset_contract_invalid")
            if not video_local_editing.manual_plan_assets_match(
                plan,
                concat_sources=raw_concat_sources,
                logo_source=raw_logo_source,
                subtitle_source=raw_subtitle_source,
            ):
                raise ValueError("local_free_asset_contract_invalid")
            asset_operation = bool(
                raw_concat_sources
                or raw_logo_source.get("file_id")
                or raw_subtitle_source.get("file_id")
            )
            contract = video_local_editing.validate_manual_edit_plan_contract(
                plan,
                source_duration_ms=source_duration_ms,
                has_audio=bool(dict(source_metadata or {}).get("has_audio")),
                allow_empty=asset_operation,
                source_width=int(dict(source_metadata or {}).get("width") or 0),
                source_height=int(dict(source_metadata or {}).get("height") or 0),
                logo_source_present=bool(raw_logo_source.get("file_id")),
                concat_sources_present=bool(raw_concat_sources),
            )
            if not contract.get("ok"):
                contract_reason = str(contract.get("reason") or "edit_plan_invalid")
                if contract_reason == "edit_operation_missing":
                    raise ValueError("local_free_edit_operation_missing")
                raise ValueError(f"local_free_edit_plan_invalid:{contract_reason}")
            if not asset_operation and not video_local_editing.plan_has_effective_operation(
                plan,
                source_duration_ms=source_duration_ms,
            ):
                raise ValueError("local_free_edit_operation_missing")
        else:
            if video_local_editing.split_plan_has_manual_conflict(
                plan,
                source_duration_ms=source_duration_ms,
                concat_sources=worker_payload.get("concat_sources") or [],
                logo_source=worker_payload.get("logo_source") or {},
                subtitle_source=worker_payload.get("subtitle_source") or {},
            ):
                raise ValueError("local_free_split_manual_conflict")
            try:
                from services.video_local_editing import validate_split_ranges
                from services.video_smart_splitter import SplitRange

                submitted_ranges = worker_payload.get("split_ranges")
                if not isinstance(submitted_ranges, list):
                    raise ValueError
                ranges = []
                for position, item in enumerate(submitted_ranges, start=1):
                    if not isinstance(item, dict):
                        raise ValueError
                    raw_index = item.get("index", position)
                    raw_start = item.get("start_ms")
                    raw_end = item.get("end_ms")
                    if any(isinstance(value, bool) for value in (raw_index, raw_start, raw_end)):
                        raise ValueError
                    ranges.append(
                        SplitRange(
                            index=int(raw_index),
                            start_ms=int(raw_start),
                            end_ms=int(raw_end),
                        )
                    )
                coverage_required = worker_payload.get("coverage_required", True)
                if not isinstance(coverage_required, bool):
                    raise ValueError
                validate_split_ranges(
                    ranges,
                    source_duration_ms=source_duration_ms,
                    coverage_required=coverage_required,
                )
            except Exception as exc:
                raise ValueError("local_free_split_plan_invalid") from exc
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    source_manifest = worker_payload.get("source_manifest")
    if source_manifest is None:
        source_manifest = dict(source_metadata or {}).get("source_manifest") or dict(source_metadata or {})
    source_video_hash = (
        worker_payload.get("source_video_hash")
        or worker_payload.get("source_sha256")
        or dict(source_metadata or {}).get("source_video_hash")
        or dict(source_metadata or {}).get("source_sha256")
        or dict(source_metadata or {}).get("sha256")
        or ""
    )
    plan_schema_version = (
        worker_payload.get("plan_schema_version")
        or worker_payload.get("schema_version")
        or dict(plan or {}).get("schema_version")
        or dict(plan or {}).get("plan_version")
        or (
            f"local1-contract-{worker_payload.get('local1_contract')}"
            if worker_payload.get("local1_contract") is not None
            else PLAN_SCHEMA_VERSION
        )
    )
    coverage_required = worker_payload.get("coverage_required", True)
    if not isinstance(coverage_required, bool):
        raise ValueError("worker_payload_identity_mismatch:coverage_required")
    concat_sources = list(worker_payload.get("concat_sources") or [])
    logo_source = dict(worker_payload.get("logo_source") or {})
    subtitle_source = dict(worker_payload.get("subtitle_source") or {})
    local1_mode = str(worker_payload.get("local1_mode") or "manual")
    split_mode = str(
        worker_payload.get("split_mode") or dict(plan or {}).get("split_mode") or ""
    )
    split_ranges = list(
        worker_payload.get("split_ranges")
        or dict(plan or {}).get("split_ranges")
        or []
    )
    token = stable_idempotency_key(
        user_id=user_id,
        edit_session_id=edit_session_id,
        plan=plan,
        quality_tier_id=quality_tier_id,
        plan_schema_version=plan_schema_version,
        source_file_id=source_file_id,
        source_video_hash=source_video_hash,
        source_manifest=source_manifest,
        concat_sources=concat_sources,
        logo_source=logo_source,
        subtitle_source=subtitle_source,
        local1_mode=local1_mode,
        split_mode=split_mode,
        split_ranges=split_ranges,
        coverage_required=coverage_required,
    )
    existing = conn.execute(
        """SELECT id,local_worker_job_id,status,user_id,chat_id,price_xu,quality_tier_id,tail_json
           FROM video_edit_jobs WHERE idempotency_key=?""",
        (token,),
    ).fetchone()
    if existing:
        existing_identity = {
            "user_id": str(existing[3] or ""),
            "chat_id": str(existing[4] or ""),
            "price_xu": int(existing[5] or 0),
            "quality_tier_id": str(existing[6] or ""),
            "tail": _load(existing[7], {}),
        }
        requested_identity = {
            "user_id": str(user_id or ""),
            "chat_id": str(chat_id or ""),
            "price_xu": normalized_price,
            "quality_tier_id": str(quality_tier_id or ""),
            "tail": dict(tail or {}),
        }
        for field in ("user_id", "chat_id", "price_xu", "quality_tier_id", "tail"):
            if existing_identity[field] != requested_identity[field]:
                raise ValueError(f"idempotency_identity_mismatch:{field}")
        outbox = conn.execute(
            "SELECT id FROM video_edit_outbox WHERE edit_job_id=?",
            (int(existing[0]),),
        ).fetchone()
        return {
            "created": False,
            "edit_job_id": int(existing[0]),
            "local_worker_job_id": int(existing[1]),
            "outbox_id": int(outbox[0]) if outbox else 0,
            "status": str(existing[2] or "queued"),
            "idempotency_key": token,
        }
    legacy_token = _historic_v2_idempotency_key(
        user_id=user_id,
        edit_session_id=edit_session_id,
        plan=plan,
        quality_tier_id=quality_tier_id,
        plan_schema_version=plan_schema_version,
        source_file_id=source_file_id,
        source_video_hash=source_video_hash,
        source_manifest=source_manifest,
        concat_sources=concat_sources,
        logo_source=logo_source,
        subtitle_source=subtitle_source,
    )
    legacy = conn.execute(
        """SELECT id,idempotency_key,local_worker_job_id,status,user_id,chat_id,
                  edit_session_id,source_file_id,source_metadata_json,plan_json,
                  tail_json,quality_tier_id,price_xu,product_type,worker_job_type,
                  engine_route,worker_owner
           FROM video_edit_jobs WHERE idempotency_key=?""",
        (legacy_token,),
    ).fetchone()
    if legacy:
        legacy_metadata = _strict_identity_dict(
            legacy[8], field="source_metadata_json"
        )
        legacy_plan = _strict_identity_dict(legacy[9], field="plan_json")
        legacy_tail = _strict_identity_dict(legacy[10], field="tail_json")
        try:
            legacy_edit_id = int(legacy[0])
            legacy_worker_id = int(legacy[2])
            legacy_price = _strict_nonnegative_int(
                legacy[12], reason="legacy_idempotency_identity_unverifiable:price_xu"
            )
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                "legacy_idempotency_identity_unverifiable:canonical_row"
            ) from exc
        canonical_expected = {
            "idempotency_key": legacy_token,
            "user_id": str(user_id or ""),
            "chat_id": str(chat_id or ""),
            "edit_session_id": str(edit_session_id or ""),
            "source_file_id": str(source_file_id or ""),
            "source_metadata": dict(source_metadata or {}),
            "plan": dict(plan or {}),
            "tail": dict(tail or {}),
            "quality_tier_id": str(quality_tier_id or ""),
            "price_xu": normalized_price,
            "product_type": PRODUCT_TYPE,
            "worker_job_type": WORKER_JOB_TYPE,
            "engine_route": ENGINE_ROUTE,
            "worker_owner": OUTBOX_OWNER,
        }
        canonical_actual = {
            "idempotency_key": str(legacy[1] or ""),
            "user_id": str(legacy[4] or ""),
            "chat_id": str(legacy[5] or ""),
            "edit_session_id": str(legacy[6] or ""),
            "source_file_id": str(legacy[7] or ""),
            "source_metadata": legacy_metadata,
            "plan": legacy_plan,
            "tail": legacy_tail,
            "quality_tier_id": str(legacy[11] or ""),
            "price_xu": legacy_price,
            "product_type": str(legacy[13] or ""),
            "worker_job_type": str(legacy[14] or ""),
            "engine_route": str(legacy[15] or ""),
            "worker_owner": str(legacy[16] or ""),
        }
        for field, expected_value in canonical_expected.items():
            if canonical_actual[field] != expected_value:
                raise ValueError(f"legacy_idempotency_identity_mismatch:{field}")

        worker = conn.execute(
            """SELECT id,user_id,command,job_type,provider,input_file_id,xu_cost,admin_only
               FROM local_worker_jobs WHERE id=?""",
            (legacy_worker_id,),
        ).fetchone()
        if not worker or int(worker[0]) != legacy_worker_id:
            raise ValueError("legacy_idempotency_identity_unverifiable:worker_row")
        try:
            worker_price = _strict_nonnegative_int(
                worker[6], reason="legacy_idempotency_identity_unverifiable:worker_price"
            )
            worker_admin = _strict_nonnegative_int(
                worker[7], reason="legacy_idempotency_identity_unverifiable:worker_admin"
            )
        except ValueError as exc:
            raise ValueError("legacy_idempotency_identity_unverifiable:worker_row") from exc
        worker_row_expected = (
            str(user_id or ""),
            "video_editengine1",
            WORKER_JOB_TYPE,
            ENGINE_ROUTE,
            normalized_price,
            0,
        )
        worker_row_actual = (
            str(worker[1] or ""),
            str(worker[2] or ""),
            str(worker[3] or ""),
            str(worker[4] or ""),
            worker_price,
            worker_admin,
        )
        if worker_row_actual != worker_row_expected:
            raise ValueError("legacy_idempotency_identity_mismatch:worker_row")
        queued = _strict_identity_dict(worker[5], field="worker_payload")
        queued_contract = {
            "edit_idempotency_key": legacy_token,
            "product_type": PRODUCT_TYPE,
            "worker_job_type": WORKER_JOB_TYPE,
            "engine_route": ENGINE_ROUTE,
            "worker_owner": OUTBOX_OWNER,
            "worker_capability": WORKER_CAPABILITY,
            "user_id": str(user_id or ""),
            "chat_id": str(chat_id or ""),
            "edit_session_id": str(edit_session_id or ""),
            "source_file_id": str(source_file_id or ""),
            "quality_tier_id": str(quality_tier_id or ""),
            "manual_edit_plan": dict(plan or {}),
            "local1_contract": 1,
            "price_xu": normalized_price,
            "quoted_price_xu": normalized_price,
            "provider_call": False,
            "charge_policy": (
                "free_local_tool" if normalized_price == 0 else "after_valid_mp4_delivery"
            ),
        }
        for field, expected_value in queued_contract.items():
            if queued.get(field, _MISSING) != expected_value:
                raise ValueError(f"legacy_idempotency_identity_mismatch:{field}")
        queued_coverage = queued.get("coverage_required", True)
        if not isinstance(queued_coverage, bool):
            raise ValueError(
                "legacy_idempotency_identity_unverifiable:coverage_required"
            )
        queued_manifest = queued.get("source_manifest")
        if queued_manifest is None:
            queued_manifest = legacy_metadata.get("source_manifest") or legacy_metadata
        queued_hash = (
            queued.get("source_video_hash")
            or queued.get("source_sha256")
            or legacy_metadata.get("source_video_hash")
            or legacy_metadata.get("source_sha256")
            or legacy_metadata.get("sha256")
            or ""
        )
        queued_schema = (
            queued.get("plan_schema_version")
            or queued.get("schema_version")
            or legacy_plan.get("schema_version")
            or legacy_plan.get("plan_version")
            or f"local1-contract-{queued.get('local1_contract')}"
        )
        recomputed_v2 = _historic_v2_idempotency_key(
            user_id=legacy[4],
            edit_session_id=legacy[6],
            plan=legacy_plan,
            quality_tier_id=legacy[11],
            plan_schema_version=queued_schema,
            source_file_id=legacy[7],
            source_video_hash=queued_hash,
            source_manifest=queued_manifest,
            concat_sources=list(queued.get("concat_sources") or []),
            logo_source=dict(queued.get("logo_source") or {}),
            subtitle_source=dict(queued.get("subtitle_source") or {}),
        )
        recomputed_v3 = stable_idempotency_key(
            user_id=legacy[4],
            edit_session_id=legacy[6],
            plan=legacy_plan,
            quality_tier_id=legacy[11],
            plan_schema_version=queued_schema,
            source_file_id=legacy[7],
            source_video_hash=queued_hash,
            source_manifest=queued_manifest,
            concat_sources=list(queued.get("concat_sources") or []),
            logo_source=dict(queued.get("logo_source") or {}),
            subtitle_source=dict(queued.get("subtitle_source") or {}),
            local1_mode=str(queued.get("local1_mode") or "manual"),
            split_mode=str(queued.get("split_mode") or legacy_plan.get("split_mode") or ""),
            split_ranges=list(queued.get("split_ranges") or legacy_plan.get("split_ranges") or []),
            coverage_required=queued_coverage,
        )
        if recomputed_v2 != legacy_token:
            raise ValueError("legacy_idempotency_identity_mismatch:v2_key")
        if recomputed_v3 != token:
            raise ValueError("legacy_idempotency_identity_mismatch:v3_key")
        outbox = conn.execute(
            """SELECT id FROM video_edit_outbox
               WHERE edit_job_id=? AND local_worker_job_id=?""",
            (legacy_edit_id, legacy_worker_id),
        ).fetchone()
        if not outbox:
            raise ValueError("legacy_idempotency_identity_unverifiable:outbox")
        return {
            "created": False,
            "edit_job_id": legacy_edit_id,
            "local_worker_job_id": legacy_worker_id,
            "outbox_id": int(outbox[0]),
            "status": str(legacy[3] or "queued"),
            "idempotency_key": legacy_token,
        }
    now = _now()
    worker_payload["edit_idempotency_key"] = token
    worker_payload["product_type"] = PRODUCT_TYPE
    worker_payload["worker_job_type"] = WORKER_JOB_TYPE
    worker_payload["engine_route"] = ENGINE_ROUTE
    worker_payload["worker_owner"] = OUTBOX_OWNER
    worker_payload["worker_capability"] = WORKER_CAPABILITY
    cursor = conn.execute(
        """INSERT INTO local_worker_jobs
           (user_id,command,job_type,status,provider,input_file_id,created_at,xu_cost,admin_only,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            str(user_id or ""), "video_editengine1", WORKER_JOB_TYPE, "queued", ENGINE_ROUTE,
            _json(worker_payload), now, normalized_price, 0, now,
        ),
    )
    worker_job_id = int(cursor.lastrowid)
    cursor = conn.execute(
        """INSERT INTO video_edit_jobs
           (idempotency_key,user_id,chat_id,product_type,worker_job_type,engine_route,worker_owner,
            edit_session_id,status,source_file_id,source_video_path,source_sha256,source_metadata_json,plan_json,
            tail_json,quality_tier_id,price_xu,local_worker_job_id,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            token, str(user_id or ""), str(chat_id or ""), PRODUCT_TYPE, WORKER_JOB_TYPE,
            ENGINE_ROUTE, OUTBOX_OWNER, str(edit_session_id or ""), "queued",
            str(source_file_id or ""), str(worker_payload.get("source_file_name") or "")[:240],
            str(worker_payload.get("source_video_hash") or worker_payload.get("source_sha256") or "")[:128],
             _json(source_metadata or {}), _json(plan or {}), _json(tail or {}),
             str(quality_tier_id or ""), normalized_price, worker_job_id, now, now,
        ),
    )
    edit_job_id = int(cursor.lastrowid)
    outbox_cursor = conn.execute(
        """INSERT INTO video_edit_outbox
           (edit_job_id,local_worker_job_id,owner,status,attempt_count,available_at,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (edit_job_id, worker_job_id, OUTBOX_OWNER, "pending", 0, now, now, now),
    )
    return {
        "created": True,
        "edit_job_id": edit_job_id,
        "local_worker_job_id": worker_job_id,
        "outbox_id": int(outbox_cursor.lastrowid),
        "status": "queued",
        "idempotency_key": token,
    }


def get_job_by_worker_id_readonly(conn, worker_job_id: Any) -> dict[str, Any]:
    """Read one canonical Video Edit receipt without performing schema writes."""

    row = conn.execute(
        """SELECT id,idempotency_key,user_id,chat_id,product_type,worker_job_type,engine_route,
                  worker_owner,status,edit_session_id,quality_tier_id,price_xu,local_worker_job_id,
                  progress_percent,blocker,source_video_path,source_sha256,output_file_id,output_path,output_sha256,
                  output_size_bytes,ffprobe_json,delivery_message_id,delivery_file_id,
                  artifact_receipts_json,delivery_cursor,receipt_state,charge_state,charged_xu,tail_json
           FROM video_edit_jobs WHERE local_worker_job_id=?""",
        (int(worker_job_id or 0),),
    ).fetchone()
    if not row:
        return {}
    fields = (
        "id", "idempotency_key", "user_id", "chat_id", "product_type", "worker_job_type",
        "engine_route", "worker_owner", "status", "edit_session_id", "quality_tier_id",
        "price_xu", "local_worker_job_id", "progress_percent", "blocker", "source_video_path",
        "source_sha256", "output_file_id", "output_path", "output_sha256", "output_size_bytes", "ffprobe_json",
        "delivery_message_id", "delivery_file_id", "artifact_receipts_json", "delivery_cursor",
        "receipt_state", "charge_state", "charged_xu", "tail_json",
    )
    result = dict(zip(fields, row))
    result["ffprobe"] = _load(result.pop("ffprobe_json"), {})
    result["artifact_receipts"] = _load(result.pop("artifact_receipts_json"), [])
    result["tail"] = _load(result.pop("tail_json"), {})
    return result


def get_job_by_worker_id(conn, worker_job_id: Any) -> dict[str, Any]:
    ensure_schema(conn)
    return get_job_by_worker_id_readonly(conn, worker_job_id)


def renew_worker_lease(
    conn,
    *,
    worker_job_id: Any,
    lease_owner: Any,
    now: Any,
    lease_expires_at: Any,
) -> bool:
    """Atomically acquire or renew one eligible local-worker lease."""

    try:
        job_id = _strict_nonnegative_int(worker_job_id, reason="worker_job_id_invalid")
    except ValueError:
        return False
    if job_id <= 0:
        return False
    if (
        not isinstance(lease_owner, str)
        or lease_owner != lease_owner.strip()
        or not lease_owner
        or len(lease_owner) > 120
        or any(ord(char) < 33 or ord(char) > 126 for char in lease_owner)
    ):
        return False

    def canonical_timestamp(value: Any) -> str:
        if isinstance(value, datetime):
            if value.tzinfo is not None or value.microsecond:
                return ""
            return value.strftime("%Y-%m-%d %H:%M:%S")
        if not isinstance(value, str) or value != value.strip():
            return ""
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            return ""
        return value if parsed.strftime("%Y-%m-%d %H:%M:%S") == value else ""

    current = canonical_timestamp(now)
    expires = canonical_timestamp(lease_expires_at)
    if not current or not expires or expires <= current:
        return False
    cursor = conn.execute(
        """UPDATE video_edit_outbox AS o
           SET lease_owner=?,lease_expires_at=?,updated_at=?
           WHERE o.local_worker_job_id=?
             AND o.status IN ('pending','running')
             AND EXISTS (
                 SELECT 1 FROM video_edit_jobs AS j
                  WHERE j.id=o.edit_job_id
                    AND j.local_worker_job_id=o.local_worker_job_id
                    AND j.local_worker_job_id=?
                    AND j.status IN ('queued','rendering')
             )
             AND (
                 COALESCE(o.lease_owner,'')=''
                 OR o.lease_owner=?
                 OR COALESCE(o.lease_expires_at,'')=''
                 OR o.lease_expires_at<=?
             )""",
        (lease_owner, expires, current, job_id, job_id, lease_owner, current),
    )
    return int(cursor.rowcount or 0) == 1


def record_worker_update(conn, *, worker_job_id: Any, worker_status: str, detail: dict, receipt: dict) -> dict[str, Any]:
    ensure_schema(conn)
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    current = get_job_by_worker_id(conn, worker_job_id)
    if not current:
        return {}
    if str(current.get("status") or "") in TERMINAL_JOB_STATES:
        return current
    now = _now()
    status = str(worker_status or "").lower()
    detail = dict(detail or {})
    receipt = dict(receipt or {})
    detail_artifacts_declared = "artifact_receipts" in detail
    receipt_artifacts_declared = "artifacts" in receipt
    detail_artifacts = _artifact_receipts(detail.get("artifact_receipts"))
    receipt_artifacts = _artifact_receipts(receipt.get("artifacts"))
    incoming_artifacts = receipt_artifacts or detail_artifacts
    current_artifacts = _artifact_receipts(current.get("artifact_receipts"))
    malformed_checkpoint = bool(
        status in {"running", "delivery_unknown"}
        and (
            (
                detail_artifacts_declared
                and not _artifact_receipts_valid(detail.get("artifact_receipts"))
            )
            or (
                receipt_artifacts_declared
                and not _artifact_receipts_valid(receipt.get("artifacts"))
            )
        )
    )
    if malformed_checkpoint:
        status = "delivery_unknown"
        detail = {**detail, "reason": "artifact_receipt_invalid"}
        incoming_artifacts = current_artifacts
    if incoming_artifacts and current_artifacts:
        if incoming_artifacts[: len(current_artifacts)] != current_artifacts:
            status = "delivery_unknown"
            detail = {**detail, "reason": "artifact_receipt_history_mismatch"}
            incoming_artifacts = current_artifacts
    artifact_json = _json(incoming_artifacts or current_artifacts)
    artifact_cursor = len(incoming_artifacts or current_artifacts)
    if status == "running":
        stage = str(detail.get("stage") or "rendering")
        current_progress = int(current.get("progress_percent") or 0)
        stage_progress = {"inspecting_input": 25, "preparing_plan": 35, "processing_video": 55, "validating_output": 80, "delivering": 90}.get(stage)
        progress = max(current_progress, stage_progress) if stage_progress is not None else current_progress
        cursor = conn.execute(
            """UPDATE video_edit_jobs SET status='rendering',progress_percent=?,
               artifact_receipts_json=?,delivery_cursor=?,
               started_at=CASE WHEN started_at='' THEN ? ELSE started_at END,updated_at=?
               WHERE id=? AND status NOT IN ('delivered','charged','failed_no_charge','delivery_unknown')""",
            (progress, artifact_json, artifact_cursor, now, now, int(current["id"])),
        )
        if cursor.rowcount != 1:
            return get_job_by_worker_id(conn, worker_job_id)
        conn.execute(
            "UPDATE video_edit_outbox SET status='running',attempt_count=CASE WHEN attempt_count=0 THEN 1 ELSE attempt_count END,updated_at=? WHERE edit_job_id=?",
            (now, int(current["id"])),
        )
    elif status == "delivery_unknown":
        reason = str(detail.get("reason") or "telegram_delivery_receipt_commit_uncertain")[:180]
        cursor = conn.execute(
            """UPDATE video_edit_jobs SET status='delivery_unknown',blocker=?,
               artifact_receipts_json=?,delivery_cursor=?,
               receipt_state='delivery_unknown',charge_state='not_charged',charged_xu=0,
               finished_at=?,updated_at=?
               WHERE id=? AND status NOT IN ('delivered','charged','failed_no_charge','delivery_unknown')""",
            (reason, artifact_json, artifact_cursor, now, now, int(current["id"])),
        )
        if cursor.rowcount != 1:
            return get_job_by_worker_id(conn, worker_job_id)
        conn.execute(
            """UPDATE video_edit_outbox SET status='terminal_delivery_unknown',
               terminal_reason=?,updated_at=? WHERE edit_job_id=?""",
            (reason, now, int(current["id"])),
        )
    elif status == "succeeded":
        delivery_message_id = _telegram_message_id(
            receipt.get("delivery_message_id")
        )
        delivery_file_id = _telegram_file_id(receipt.get("delivery_file_id"))
        try:
            raw_output_count = receipt.get("output_count")
            if isinstance(raw_output_count, bool) or not isinstance(raw_output_count, int):
                raise ValueError
            output_count = int(raw_output_count)
        except (TypeError, ValueError):
            output_count = 0
        try:
            output_size_bytes = _strict_nonnegative_int(
                receipt.get("output_size_bytes"), reason="output_size_invalid"
            )
        except ValueError:
            output_size_bytes = 0
        try:
            receipt_charged_xu = _strict_nonnegative_int(
                receipt.get("charged_xu"), reason="receipt_charged_xu_invalid"
            )
        except ValueError:
            receipt_charged_xu = -1
        is_free_job = int(current.get("price_xu") or 0) == 0
        if is_free_job:
            charge_receipt_valid = bool(
                str(current.get("quality_tier_id") or "") == "local-free"
                and str(receipt.get("charge_policy") or "") == "free_local_tool"
                and str(receipt.get("charge_status") or "") == "not_required_free"
                and receipt_charged_xu == 0
            )
        else:
            charge_receipt_valid = bool(
                str(receipt.get("charge_policy") or "") == "after_valid_mp4_delivery"
                and str(receipt.get("charge_status") or "") == "pending_post_delivery"
                and receipt_charged_xu == 0
            )
        artifacts_declared = receipt_artifacts_declared
        artifacts_complete = (
            output_count == 1
            and ((not artifacts_declared) or len(receipt_artifacts) == 1)
        ) or (output_count > 1 and len(receipt_artifacts) == output_count)
        artifact_identity_valid = bool(
            not artifacts_declared
            or (
                receipt_artifacts
                and delivery_message_id == receipt_artifacts[0]["message_id"]
                and delivery_file_id == receipt_artifacts[0]["file_id"]
                and output_size_bytes
                == sum(int(item["size"]) for item in receipt_artifacts)
            )
        )
        source_sha256 = receipt.get("source_sha256")
        source_identity_valid = bool(
            _is_sha256(source_sha256)
            and (
                not current.get("source_sha256")
                or str(source_sha256).lower()
                == str(current.get("source_sha256") or "").lower()
            )
        )
        valid = bool(
            output_count > 0
            and artifacts_complete
            and artifact_identity_valid
            and detail.get("validation") == "passed"
            and delivery_message_id
            and delivery_file_id
            and _is_sha256(receipt.get("output_sha256"))
            and source_identity_valid
            and _valid_mp4_path_list(receipt.get("output_path"), output_count=output_count)
            and output_size_bytes > 0
            and _valid_ffprobe_receipt(receipt.get("ffprobe"))
            and charge_receipt_valid
        )
        if valid:
            cursor = conn.execute(
                """UPDATE video_edit_jobs SET status='delivered',progress_percent=100,blocker='',
                   source_video_path=?,source_sha256=?,output_file_id=?,output_path=?,output_sha256=?,output_size_bytes=?,ffprobe_json=?,
                   delivery_message_id=?,delivery_file_id=?,artifact_receipts_json=?,delivery_cursor=?,receipt_state='created',
                   delivered_at=?,finished_at=?,updated_at=?
                   WHERE id=? AND status NOT IN ('delivered','charged','failed_no_charge','delivery_unknown')""",
                (
                    str(receipt.get("source_video_path") or current.get("source_video_path") or "")[:240],
                    str(receipt.get("source_sha256") or "")[:128],
                    delivery_file_id,
                    str(receipt.get("output_path") or "")[:500],
                    str(receipt.get("output_sha256") or "")[:128],
                    output_size_bytes,
                    _json(receipt.get("ffprobe") or {}),
                    delivery_message_id,
                    delivery_file_id,
                    artifact_json,
                    artifact_cursor,
                    now, now, now, int(current["id"]),
                ),
            )
            if cursor.rowcount != 1:
                return get_job_by_worker_id(conn, worker_job_id)
            conn.execute(
                "UPDATE video_edit_outbox SET status='delivered',terminal_reason='',updated_at=? WHERE edit_job_id=?",
                (now, int(current["id"])),
            )
        else:
            status = "failed"
            detail = {**detail, "reason": "delivery_receipt_invalid"}
    if status in {"failed", "cancelled"}:
        reason = str(detail.get("reason") or "local_edit_failed_no_charge")[:180]
        cursor = conn.execute(
            """UPDATE video_edit_jobs SET status='failed_no_charge',progress_percent=0,blocker=?,
               charge_state='not_charged',charged_xu=0,finished_at=?,updated_at=?
               WHERE id=? AND status NOT IN ('delivered','charged','failed_no_charge','delivery_unknown')""",
            (reason, now, now, int(current["id"])),
        )
        if cursor.rowcount != 1:
            return get_job_by_worker_id(conn, worker_job_id)
        conn.execute(
            "UPDATE video_edit_outbox SET status='terminal_failed',terminal_reason=?,updated_at=? WHERE edit_job_id=?",
            (reason, now, int(current["id"])),
        )
    return get_job_by_worker_id(conn, worker_job_id)


def mark_charge_result(conn, *, worker_job_id: Any, ok: bool, charged_xu: int = 0, reason: str = "") -> dict[str, Any]:
    current = get_job_by_worker_id(conn, worker_job_id)
    if not current or current.get("receipt_state") != "created":
        return current
    price_xu = _strict_nonnegative_int(
        current.get("price_xu", 0), reason="canonical_price_invalid"
    )
    if price_xu <= 0:
        return current
    now = _now()
    if current.get("charge_state") == "charged":
        return current
    if current.get("charge_state") != "charging":
        return current
    if ok:
        try:
            charged_amount = _strict_nonnegative_int(
                charged_xu, reason="charged_xu_invalid"
            )
        except ValueError:
            charged_amount = -1
        if charged_amount != price_xu:
            conn.execute(
                "UPDATE video_edit_jobs SET charge_state='charge_failed',charged_xu=0,blocker='charge_amount_mismatch',updated_at=? WHERE id=?",
                (now, int(current["id"])),
            )
        else:
            conn.execute(
                "UPDATE video_edit_jobs SET status='charged',charge_state='charged',charged_xu=?,blocker='',charged_at=?,updated_at=? WHERE id=?",
                (charged_amount, now, now, int(current["id"])),
            )
    else:
        conn.execute(
            "UPDATE video_edit_jobs SET charge_state='charge_failed',blocker=?,updated_at=? WHERE id=?",
            (str(reason or "charge_failed_after_delivery")[:180], now, int(current["id"])),
        )
    return get_job_by_worker_id(conn, worker_job_id)


def claim_charge(conn, *, worker_job_id: Any) -> bool:
    """Atomically grant one post-delivery charge attempt."""

    ensure_schema(conn)
    row = conn.execute(
        """SELECT status,receipt_state,charge_state,price_xu,source_sha256,
                  output_file_id,output_path,output_sha256,output_size_bytes,
                  ffprobe_json,delivery_message_id,delivery_file_id,
                  artifact_receipts_json,delivery_cursor
           FROM video_edit_jobs WHERE local_worker_job_id=?""",
        (int(worker_job_id or 0),),
    ).fetchone()
    if not row:
        return False
    try:
        price_xu = _strict_nonnegative_int(row[3], reason="canonical_price_invalid")
        output_size_bytes = _strict_nonnegative_int(
            row[8], reason="output_size_invalid"
        )
        delivery_cursor = _strict_nonnegative_int(
            row[13], reason="delivery_cursor_invalid"
        )
        ffprobe = json.loads(str(row[9]))
        artifact_value = json.loads(str(row[12]))
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    artifacts = _artifact_receipts(artifact_value)
    if not _artifact_receipts_valid(artifact_value):
        return False
    delivery_message_id = _telegram_message_id(row[10])
    delivery_file_id = _telegram_file_id(row[11])
    output_file_id = _telegram_file_id(row[5])
    output_count = len(artifacts) if artifacts else 1
    evidence_valid = bool(
        str(row[0] or "") == "delivered"
        and str(row[1] or "") == "created"
        and str(row[2] or "") == "not_charged"
        and price_xu > 0
        and _is_sha256(row[4])
        and _is_sha256(row[7])
        and output_size_bytes > 0
        and isinstance(ffprobe, dict)
        and _valid_ffprobe_receipt(ffprobe)
        and delivery_message_id
        and delivery_file_id
        and output_file_id == delivery_file_id
        and _valid_mp4_path_list(row[6], output_count=output_count)
        and delivery_cursor == len(artifacts)
        and (
            not artifacts
            or (
                delivery_message_id == artifacts[0]["message_id"]
                and delivery_file_id == artifacts[0]["file_id"]
                and output_size_bytes == sum(int(item["size"]) for item in artifacts)
            )
        )
    )
    if not evidence_valid:
        return False
    cursor = conn.execute(
        """UPDATE video_edit_jobs
           SET charge_state='charging',updated_at=?
           WHERE local_worker_job_id=?
             AND status='delivered'
             AND receipt_state='created'
              AND charge_state='not_charged'
              AND price_xu=?
              AND source_sha256=?
              AND output_file_id=?
              AND output_path=?
              AND output_sha256=?
              AND output_size_bytes=?
              AND ffprobe_json=?
              AND delivery_message_id=?
              AND delivery_file_id=?
              AND artifact_receipts_json=?
              AND delivery_cursor=?""",
        (
            _now(),
            int(worker_job_id or 0),
            row[3], row[4], row[5], row[6], row[7], row[8], row[9],
            row[10], row[11], row[12], row[13],
        ),
    )
    return int(cursor.rowcount or 0) == 1
