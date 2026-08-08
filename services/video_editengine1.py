"""Persistent contract for the canonical local Video Edit engine.

The bot owns admission and billing.  The local worker owns FFmpeg rendering and
Telegram delivery.  This module keeps those two sides joined by an idempotent
job/outbox record without importing Telegram, wallet, or provider code.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any

from services import (
    video_edit_cleanup_audit,
    video_edit_long_media,
    video_edit_media_transport,
)


PRODUCT_TYPE = "video_edit"
WORKER_JOB_TYPE = "video_local_edit"
VIDEO_LOCAL_EDIT_RESUME_SCHEMA = "video-local-edit-receipt-prefix-resume"
VIDEO_LOCAL_EDIT_RESUME_VERSION = 1
ENGINE_ROUTE = "local_worker_ffmpeg"
OUTBOX_OWNER = "local_video_edit"
WORKER_CAPABILITY = "video_edit"
HEARTBEAT_TTL_SECONDS = 90
IDEMPOTENCY_SCHEMA_VERSION = "video-edit-job-identity-v4"
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

    return _valid_ffprobe_receipt(value) and dict(value or {}).get("full_decode") is True


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
    audio_sources: Any = _MISSING,
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
        audio_sources,
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
            "audio_sources": [] if audio_sources is _MISSING else audio_sources or [],
            "local1_mode": str("" if local1_mode is _MISSING else local1_mode or ""),
            "split_mode": str("" if split_mode is _MISSING else split_mode or ""),
            "split_ranges": [] if split_ranges is _MISSING else split_ranges or [],
            "coverage_required": (
                None if coverage_required is _MISSING else bool(coverage_required)
            ),
        })
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _historic_pre_audio_plan(plan: dict) -> dict[str, Any]:
    """Treat only the new empty audio container as absent in old identities."""

    historic_plan = dict(plan or {})
    if isinstance(historic_plan.get("audio_tracks"), list) and not historic_plan["audio_tracks"]:
        historic_plan.pop("audio_tracks", None)
    return historic_plan


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
    audio_sources: Any = _MISSING,
) -> str:
    """Reproduce the immutable identity written by the historic v2 lane."""

    material = _json({
        "user_id": str(user_id or ""),
        "edit_session_id": str(edit_session_id or ""),
        "plan": _historic_pre_audio_plan(plan),
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


def _historic_v3_idempotency_key(
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
    local1_mode: Any,
    split_mode: Any,
    split_ranges: Any,
    coverage_required: Any,
) -> str:
    """Reproduce deployed v3 identity material before audio assets were bound."""

    material = _json({
        "user_id": str(user_id or ""),
        "edit_session_id": str(edit_session_id or ""),
        "plan": _historic_pre_audio_plan(plan),
        "quality_tier_id": str(quality_tier_id or ""),
        "idempotency_schema_version": "video-edit-job-identity-v3",
        "plan_schema_version": str(plan_schema_version or PLAN_SCHEMA_VERSION),
        "source_file_id": str(source_file_id or ""),
        "source_video_hash": str(source_video_hash or ""),
        "source_manifest": source_manifest or {},
        "concat_sources": concat_sources or [],
        "logo_source": logo_source or {},
        "subtitle_source": subtitle_source or {},
        "local1_mode": str(local1_mode or ""),
        "split_mode": str(split_mode or ""),
        "split_ranges": split_ranges or [],
        "coverage_required": bool(coverage_required),
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
        raw_delivery_method = item.get("delivery_method", _MISSING)
        delivery_method = (
            "" if raw_delivery_method is _MISSING else raw_delivery_method
        )
        raw_bytes_sent = item.get("bytes_sent", _MISSING)
        try:
            bytes_sent = (
                0
                if raw_bytes_sent is _MISSING
                else _strict_nonnegative_int(
                    raw_bytes_sent,
                    reason="artifact_bytes_sent_invalid",
                )
            )
        except ValueError:
            return []
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
            or (
                raw_delivery_method is not _MISSING
                and delivery_method not in {"sendVideo", "sendDocument"}
            )
            or (
                raw_bytes_sent is not _MISSING
                and bytes_sent != size
            )
        ):
            return []
        message_ids.add(message_id)
        file_ids.add(file_id)
        receipt = {
            "index": index,
            "message_id": message_id,
            "file_id": file_id,
            "size": size,
            "sha256": sha256,
            "ffprobe": ffprobe,
        }
        if raw_delivery_method is not _MISSING:
            receipt["delivery_method"] = delivery_method
        if raw_bytes_sent is not _MISSING:
            receipt["bytes_sent"] = bytes_sent
        normalized.append(receipt)
    return normalized


def _artifact_receipts_valid(value: Any) -> bool:
    return isinstance(value, list) and (not value or bool(_artifact_receipts(value)))


def normalize_artifact_receipt_prefix(
    value: Any,
    *,
    expected_output_count: Any,
) -> list[dict[str, Any]]:
    """Return one complete, ordered, bounded durable Telegram receipt prefix."""

    try:
        expected = _strict_nonnegative_int(
            expected_output_count,
            reason="expected_output_count_invalid",
        )
    except ValueError:
        raise ValueError("artifact_receipt_prefix_invalid") from None
    normalized = _artifact_receipts(value)
    if (
        expected <= 0
        or not _artifact_receipts_valid(value)
        or len(normalized) > expected
    ):
        raise ValueError("artifact_receipt_prefix_invalid")
    return normalized


def _validate_delivery_cursor_receipt_prefix(
    cursor: video_edit_long_media.DeliveryCursor,
    receipts: list[dict[str, Any]],
) -> video_edit_long_media.DeliveryCursor:
    """Bind one active strict cursor to an already-normalized receipt prefix."""

    if not isinstance(cursor, video_edit_long_media.DeliveryCursor):
        raise ValueError("delivery_cursor_invalid")
    if not isinstance(receipts, list) or any(
        not isinstance(receipt, dict) for receipt in receipts
    ):
        raise ValueError("delivery_cursor_invalid")
    receipt_count = len(receipts)
    if cursor.state == "not_started":
        raise ValueError("delivery_cursor_invalid")
    if cursor.state in {"sending", "unknown", "rejected"}:
        if cursor.output_index != receipt_count + 1:
            raise ValueError("delivery_cursor_invalid")
        return cursor
    if cursor.state in {"accepted", "delivered"}:
        if receipt_count <= 0 or cursor.output_index != receipt_count:
            raise ValueError("delivery_cursor_invalid")
        last_receipt = receipts[-1]
        if (
            cursor.message_id != last_receipt.get("message_id")
            or cursor.file_id != last_receipt.get("file_id")
        ):
            raise ValueError("delivery_cursor_invalid")
        return cursor
    raise ValueError("delivery_cursor_invalid")


def normalize_video_local_edit_resume_contract(value: Any) -> dict[str, Any]:
    """Validate and normalize the complete worker-facing receipt-prefix contract."""

    if not isinstance(value, dict) or set(value) != {
        "schema",
        "version",
        "expected_output_count",
        "artifact_receipt_prefix",
        "prefix_count",
        "prefix_digest",
        "compatibility",
        "delivery_cursor",
    }:
        raise ValueError("video_local_edit_resume_contract_invalid")
    if (
        value.get("schema") != VIDEO_LOCAL_EDIT_RESUME_SCHEMA
        or type(value.get("version")) is not int
        or value.get("version") != VIDEO_LOCAL_EDIT_RESUME_VERSION
    ):
        raise ValueError("video_local_edit_resume_contract_invalid")
    try:
        expected = _strict_nonnegative_int(
            value.get("expected_output_count"),
            reason="expected_output_count_invalid",
        )
        prefix_count = _strict_nonnegative_int(
            value.get("prefix_count"),
            reason="prefix_count_invalid",
        )
        receipts = normalize_artifact_receipt_prefix(
            value.get("artifact_receipt_prefix"),
            expected_output_count=expected,
        )
    except ValueError:
        raise ValueError("video_local_edit_resume_contract_invalid") from None
    digest = hashlib.sha256(
        json.dumps(
            receipts,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    if (
        prefix_count != len(receipts)
        or value.get("prefix_digest") != digest
        or value.get("compatibility") not in {"strict", "legacy_receipt_only"}
    ):
        raise ValueError("video_local_edit_resume_contract_invalid")
    raw_cursor = value.get("delivery_cursor")
    normalized_cursor = None
    if value["compatibility"] == "strict":
        try:
            cursor = video_edit_long_media.DeliveryCursor.from_mapping(raw_cursor)
            _validate_delivery_cursor_receipt_prefix(cursor, receipts)
        except (TypeError, ValueError):
            raise ValueError("video_local_edit_resume_contract_invalid") from None
        if cursor.state not in {
            "sending",
            "unknown",
            "accepted",
            "delivered",
        }:
            raise ValueError("video_local_edit_resume_contract_invalid")
        normalized_cursor = cursor.to_mapping()
    elif raw_cursor is not None:
        raise ValueError("video_local_edit_resume_contract_invalid")
    return {
        "schema": VIDEO_LOCAL_EDIT_RESUME_SCHEMA,
        "version": VIDEO_LOCAL_EDIT_RESUME_VERSION,
        "expected_output_count": expected,
        "artifact_receipt_prefix": receipts,
        "prefix_count": len(receipts),
        "prefix_digest": digest,
        "compatibility": value["compatibility"],
        "delivery_cursor": normalized_cursor,
    }


def _positive_capacity_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _preflight_capacity_evidence(
    current: dict[str, Any],
    metadata: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    source_sizes = [
        _positive_capacity_int(current.get("source_file_size")),
        _positive_capacity_int(metadata.get("actual_bytes")),
        _positive_capacity_int(metadata.get("bytes")),
    ]
    known_source_sizes = [value for value in source_sizes if value is not None]
    if not known_source_sizes:
        return {"ok": False, "reason": "local_worker_source_size_missing"}
    source_bytes = max(known_source_sizes)

    asset_sizes: list[int] = []
    concat_sources = current.get("concat_sources") or []
    if not isinstance(concat_sources, list):
        return {"ok": False, "reason": "local_worker_asset_size_missing"}
    asset_records: list[Any] = list(concat_sources)
    for key in ("logo_source", "subtitle_source", "audio_sources"):
        record = current.get(key)
        if key == "audio_sources":
            if record is None:
                record = []
            if not isinstance(record, list):
                return {"ok": False, "reason": "local_worker_asset_size_missing"}
            asset_records.extend(record)
        elif record:
            asset_records.append(record)
    for record in asset_records:
        if not isinstance(record, dict):
            return {"ok": False, "reason": "local_worker_asset_size_missing"}
        size = _positive_capacity_int(
            record.get("file_size")
            if record.get("file_size") is not None
            else record.get("bytes")
        )
        if size is None:
            return {"ok": False, "reason": "local_worker_asset_size_missing"}
        asset_sizes.append(size)

    split_ranges = current.get("split_ranges") or []
    split_selected = bool(
        str(current.get("selected_tool") or "").strip().lower() == "split"
        and isinstance(split_ranges, list)
        and split_ranges
    )
    output_count = len(split_ranges) if split_selected else 1
    execution_class = video_edit_long_media.classify_plan_execution(plan)
    if split_selected:
        operations = ["split"]
    else:
        operations: list[str] = []
        if concat_sources:
            operations.append("concat")
        if (
            current.get("logo_source")
            or current.get("subtitle_source")
            or plan.get("text_overlay")
            or plan.get("watermark_overlay")
            or plan.get("logo_overlay")
            or plan.get("subtitle_file")
        ):
            operations.append("overlay")
        if execution_class == video_edit_long_media.WHOLE_TIMELINE_REQUIRED:
            operations.append("transcode")
        if not operations:
            operations.append("manual")

    estimates = [
        video_edit_long_media.estimate_workspace(
            operation=operation,
            source_bytes=source_bytes,
            asset_bytes=asset_sizes,
            output_count=output_count,
        )
        for operation in operations
    ]
    required_bytes = max(estimate.required_bytes for estimate in estimates)
    declared_input_bytes = source_bytes + sum(asset_sizes)
    duration_seconds = metadata.get("duration")
    if duration_seconds is None or duration_seconds == "":
        duration_ms = metadata.get("duration_ms")
        duration_seconds = (
            float(duration_ms) / 1000.0
            if isinstance(duration_ms, int)
            and not isinstance(duration_ms, bool)
            and duration_ms > 0
            else None
        )
    adaptive_deadline = video_edit_long_media.adaptive_deadline_seconds(
        source_bytes=declared_input_bytes,
        duration_seconds=duration_seconds,
        width=metadata.get("width"),
        height=metadata.get("height"),
        output_count=output_count,
        operation_class=execution_class,
    )
    persisted_lane = str(
        current.get("media_lane")
        or metadata.get("media_lane")
        or "large_media"
    ).strip()
    evidence_lane = video_edit_media_transport.select_media_lane(
        duration_seconds=duration_seconds,
        size_bytes=source_bytes,
    )
    concat_requires_large = False
    for record, size in zip(concat_sources, asset_sizes[: len(concat_sources)]):
        nested_metadata = (
            record.get("metadata")
            if isinstance(record.get("metadata"), dict)
            else {}
        )
        concat_duration = record.get(
            "duration_seconds",
            record.get(
                "duration",
                nested_metadata.get("duration_seconds", nested_metadata.get("duration")),
            ),
        )
        if concat_duration is None or concat_duration == "":
            duration_ms = record.get(
                "duration_ms",
                nested_metadata.get("duration_ms"),
            )
            concat_duration = (
                float(duration_ms) / 1000.0
                if isinstance(duration_ms, int)
                and not isinstance(duration_ms, bool)
                and duration_ms > 0
                else 0
            )
        if (
            video_edit_media_transport.select_media_lane(
                duration_seconds=concat_duration,
                size_bytes=size,
            )
            == "large_media"
        ):
            concat_requires_large = True
            break
    oversized_asset = any(
        size > video_edit_media_transport.SHORT_MEDIA_MAX_BYTES
        for size in asset_sizes
    )
    lane = (
        "short_media"
        if persisted_lane == "short_media"
        and evidence_lane == "short_media"
        and not concat_requires_large
        and not oversized_asset
        else "large_media"
    )
    return {
        "ok": True,
        "reason": "ok",
        "declared_input_bytes": declared_input_bytes,
        "workspace_required_bytes": required_bytes,
        "adaptive_deadline_seconds": adaptive_deadline,
        "media_lane": lane,
    }


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
            audio_sources=current.get("audio_sources") or [],
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
    capacity_evidence: dict[str, Any] = {
        "ok": not canonical_contract_required,
        "reason": "ok" if not canonical_contract_required else "local_worker_capacity_contract_invalid",
    }
    if canonical_contract_required and not plan_error:
        try:
            capacity_evidence = _preflight_capacity_evidence(
                current,
                metadata,
                plan,
            )
        except (TypeError, ValueError, OverflowError):
            capacity_evidence = {
                "ok": False,
                "reason": "local_worker_capacity_contract_invalid",
            }
    workspace_free_bytes = _positive_capacity_int(
        worker.get("workspace_free_bytes")
    )
    deadline_ceiling = _positive_capacity_int(
        worker.get("video_edit_max_deadline_seconds")
    )
    required_workspace = _positive_capacity_int(
        capacity_evidence.get("workspace_required_bytes")
    )
    adaptive_deadline = _positive_capacity_int(
        capacity_evidence.get("adaptive_deadline_seconds")
    )
    if canonical_contract_required:
        checks.update(
            {
                "capacity_evidence": capacity_evidence.get("ok") is True,
                "worker_token_ready": worker.get("worker_token_ready") is True,
                "workspace_ready": worker.get("workspace_ready") is True,
                "workspace_capacity_present": workspace_free_bytes is not None,
                "workspace_capacity": bool(
                    workspace_free_bytes is not None
                    and required_workspace is not None
                    and workspace_free_bytes >= required_workspace
                ),
                "deadline_capacity_present": deadline_ceiling is not None,
                "deadline_capacity": bool(
                    deadline_ceiling is not None
                    and adaptive_deadline is not None
                    and deadline_ceiling >= adaptive_deadline
                ),
                "local_bot_api": bool(
                    capacity_evidence.get("media_lane") == "short_media"
                    or worker.get("local_bot_api_ready") is True
                ),
            }
        )
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
            ("capacity_evidence", str(capacity_evidence.get("reason") or "local_worker_capacity_contract_invalid")),
            ("worker_token_ready", "local_worker_token_not_ready"),
            ("workspace_ready", "local_worker_workspace_not_ready"),
            ("workspace_capacity_present", "local_worker_workspace_capacity_missing"),
            ("workspace_capacity", "local_worker_workspace_insufficient"),
            ("deadline_capacity_present", "local_worker_deadline_capacity_missing"),
            ("deadline_capacity", "local_worker_deadline_ceiling_insufficient"),
            ("local_bot_api", "local_worker_local_bot_api_not_ready"),
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
    if canonical_contract_required and capacity_evidence.get("ok") is True:
        result.update(
            {
                "declared_input_bytes": int(capacity_evidence["declared_input_bytes"]),
                "workspace_required_bytes": int(capacity_evidence["workspace_required_bytes"]),
                "workspace_free_bytes": int(workspace_free_bytes or 0),
                "adaptive_deadline_seconds": int(capacity_evidence["adaptive_deadline_seconds"]),
                "video_edit_max_deadline_seconds": int(deadline_ceiling or 0),
                "media_lane": str(capacity_evidence["media_lane"]),
            }
        )
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
            raw_audio_sources = worker_payload.get("audio_sources") or []
            if (
                not isinstance(raw_concat_sources, list)
                or any(
                    not isinstance(item, dict) or not str(item.get("file_id") or "").strip()
                    for item in raw_concat_sources
                )
                or not isinstance(raw_logo_source, dict)
                or not isinstance(raw_subtitle_source, dict)
                or not isinstance(raw_audio_sources, list)
                or len(raw_audio_sources) > 4
                or (raw_logo_source and not str(raw_logo_source.get("file_id") or "").strip())
                or (raw_subtitle_source and not str(raw_subtitle_source.get("file_id") or "").strip())
                or any(
                    not isinstance(item, dict)
                    or not str(item.get("file_id") or "").strip()
                    or str(item.get("kind") or "music").strip().lower() not in {"music", "voice", "sfx"}
                    for item in raw_audio_sources
                )
            ):
                raise ValueError("local_free_asset_contract_invalid")
            if not video_local_editing.manual_plan_assets_match(
                plan,
                concat_sources=raw_concat_sources,
                logo_source=raw_logo_source,
                subtitle_source=raw_subtitle_source,
                audio_sources=raw_audio_sources,
            ):
                raise ValueError("local_free_asset_contract_invalid")
            asset_operation = bool(
                raw_concat_sources
                or raw_logo_source.get("file_id")
                or raw_subtitle_source.get("file_id")
                or raw_audio_sources
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
                audio_sources=raw_audio_sources,
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
    audio_sources = list(worker_payload.get("audio_sources") or [])
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
        audio_sources=audio_sources,
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
    historic_candidates = (
        (
            "v3",
            _historic_v3_idempotency_key(
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
            ),
        ),
        (
            "v2",
            _historic_v2_idempotency_key(
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
                audio_sources=audio_sources,
            ),
        ),
    )
    legacy_version = ""
    legacy_token = ""
    legacy = None
    for candidate_version, candidate_token in historic_candidates:
        candidate = conn.execute(
            """SELECT id,idempotency_key,local_worker_job_id,status,user_id,chat_id,
                      edit_session_id,source_file_id,source_metadata_json,plan_json,
                      tail_json,quality_tier_id,price_xu,product_type,worker_job_type,
                      engine_route,worker_owner
               FROM video_edit_jobs WHERE idempotency_key=?""",
            (candidate_token,),
        ).fetchone()
        if candidate:
            legacy_version = candidate_version
            legacy_token = candidate_token
            legacy = candidate
            break
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
        historic_requested_plan = _historic_pre_audio_plan(plan)
        historic_legacy_plan = _historic_pre_audio_plan(legacy_plan)
        canonical_expected = {
            "idempotency_key": legacy_token,
            "user_id": str(user_id or ""),
            "chat_id": str(chat_id or ""),
            "edit_session_id": str(edit_session_id or ""),
            "source_file_id": str(source_file_id or ""),
            "source_metadata": dict(source_metadata or {}),
            "plan": historic_requested_plan,
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
            "plan": historic_legacy_plan,
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
            "manual_edit_plan": historic_requested_plan,
            "local1_contract": 1,
            "price_xu": normalized_price,
            "quoted_price_xu": normalized_price,
            "provider_call": False,
            "charge_policy": (
                "free_local_tool" if normalized_price == 0 else "after_valid_mp4_delivery"
            ),
        }
        for field, expected_value in queued_contract.items():
            actual_value = queued.get(field, _MISSING)
            if field == "manual_edit_plan":
                if not isinstance(actual_value, dict):
                    raise ValueError(
                        "legacy_idempotency_identity_unverifiable:manual_edit_plan"
                    )
                actual_value = _historic_pre_audio_plan(actual_value)
            if actual_value != expected_value:
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
        queued_audio_sources = queued.get("audio_sources", [])
        if not isinstance(queued_audio_sources, list) or any(
            not isinstance(item, dict) for item in queued_audio_sources
        ):
            raise ValueError(
                "legacy_idempotency_identity_unverifiable:audio_sources"
            )
        queued_concat_sources = list(queued.get("concat_sources") or [])
        queued_logo_source = dict(queued.get("logo_source") or {})
        queued_subtitle_source = dict(queued.get("subtitle_source") or {})
        queued_local1_mode = str(queued.get("local1_mode") or "manual")
        queued_split_mode = str(
            queued.get("split_mode") or legacy_plan.get("split_mode") or ""
        )
        queued_split_ranges = list(
            queued.get("split_ranges") or legacy_plan.get("split_ranges") or []
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
            concat_sources=queued_concat_sources,
            logo_source=queued_logo_source,
            subtitle_source=queued_subtitle_source,
        )
        recomputed_v3 = _historic_v3_idempotency_key(
            user_id=legacy[4],
            edit_session_id=legacy[6],
            plan=legacy_plan,
            quality_tier_id=legacy[11],
            plan_schema_version=queued_schema,
            source_file_id=legacy[7],
            source_video_hash=queued_hash,
            source_manifest=queued_manifest,
            concat_sources=queued_concat_sources,
            logo_source=queued_logo_source,
            subtitle_source=queued_subtitle_source,
            local1_mode=queued_local1_mode,
            split_mode=queued_split_mode,
            split_ranges=queued_split_ranges,
            coverage_required=queued_coverage,
        )
        recomputed_current = stable_idempotency_key(
            user_id=legacy[4],
            edit_session_id=legacy[6],
            plan=plan,
            quality_tier_id=legacy[11],
            plan_schema_version=queued_schema,
            source_file_id=legacy[7],
            source_video_hash=queued_hash,
            source_manifest=queued_manifest,
            concat_sources=queued_concat_sources,
            logo_source=queued_logo_source,
            subtitle_source=queued_subtitle_source,
            audio_sources=queued_audio_sources,
            local1_mode=queued_local1_mode,
            split_mode=queued_split_mode,
            split_ranges=queued_split_ranges,
            coverage_required=queued_coverage,
        )
        expected_historic = recomputed_v3 if legacy_version == "v3" else recomputed_v2
        if expected_historic != legacy_token:
            raise ValueError(
                f"legacy_idempotency_identity_mismatch:{legacy_version}_key"
            )
        if recomputed_current != token:
            raise ValueError("legacy_idempotency_identity_mismatch:v4_key")
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


def _canonical_timestamp(value: Any) -> str:
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


def _valid_lease_owner(value: Any) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > 120
        or any(ord(char) < 33 or ord(char) > 126 for char in value)
    ):
        return ""
    return value


def _cleanup_delivery_binding(conn, worker_job_id: Any) -> tuple[str, int]:
    try:
        job_id = _strict_nonnegative_int(
            worker_job_id,
            reason="worker_job_id_invalid",
        )
    except ValueError:
        return "", 0
    row = conn.execute(
        """SELECT COALESCE(lease_owner,''),attempt_count
             FROM video_edit_outbox
            WHERE local_worker_job_id=? AND owner=? AND status='running'""",
        (job_id, OUTBOX_OWNER),
    ).fetchone()
    if not row:
        return "", 0
    owner = _valid_lease_owner(row[0])
    try:
        attempt = _strict_nonnegative_int(
            row[1],
            reason="claim_attempt_invalid",
        )
    except ValueError:
        attempt = 0
    return owner, attempt if attempt > 0 else 0


def _seed_cleanup_audit(
    canonical_tail: dict[str, Any],
    *,
    worker_job_id: Any,
    terminal_status: str,
    delivery_owner: str,
    delivery_claim_attempt: int,
    cleanup_intent: Any,
    now: str,
) -> dict[str, Any]:
    """Derive canonical cleanup state without trusting worker path material."""

    tail = dict(canonical_tail)
    try:
        job_id = _strict_nonnegative_int(
            worker_job_id,
            reason="worker_job_id_invalid",
        )
    except ValueError:
        job_id = 0
    binding_valid = bool(
        job_id > 0
        and _valid_lease_owner(delivery_owner)
        and isinstance(delivery_claim_attempt, int)
        and not isinstance(delivery_claim_attempt, bool)
        and delivery_claim_attempt > 0
    )
    key = (
        video_edit_cleanup_audit.workspace_key(
            job_id,
            delivery_claim_attempt,
        )
        if binding_valid
        else ""
    )
    evidence = cleanup_intent if isinstance(cleanup_intent, dict) else {}
    workspace_present = evidence.get("workspace_present")
    workspace_presence_valid = isinstance(workspace_present, bool)
    persisted_valid = bool(
        binding_valid
        and workspace_present is True
        and evidence.get("persisted") is True
        and evidence.get("intent_key") == f"{key}.json"
        and evidence.get("workspace_key") == key
        and evidence.get("tombstone_key") == key
    )
    terminal = str(terminal_status or "").strip().lower()
    if terminal == "delivery_unknown":
        state = "retained_delivery_unknown"
        reason = "delivery_outcome_uncertain"
    elif workspace_presence_valid and workspace_present is False:
        state = "succeeded"
        reason = "workspace_not_created"
    elif persisted_valid and terminal in {"delivered", "failed_no_charge"}:
        state = "pending"
        reason = ""
    else:
        state = "failed_exhausted"
        reason = "cleanup_intent_not_persisted"
    tail["cleanup_audit"] = {
        "schema": video_edit_cleanup_audit.CLEANUP_AUDIT_SCHEMA,
        "version": video_edit_cleanup_audit.CLEANUP_AUDIT_VERSION,
        "state": state,
        "job_id": job_id,
        "delivery_owner": delivery_owner if binding_valid else "",
        "delivery_claim_attempt": (
            delivery_claim_attempt if binding_valid else 0
        ),
        "workspace_present": bool(workspace_present)
        if workspace_presence_valid
        else True,
        "workspace_key": key,
        "tombstone_key": key,
        "intent_key": f"{key}.json" if key else "",
        "audit_owner": "",
        "audit_attempt": 0,
        "lease_expires_at": "",
        "reason": reason,
        "updated_at": now,
    }
    return tail


def _cleanup_positive_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return 0
    return value


def _cleanup_nonnegative_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return -1
    return value


def _cleanup_audit_record(
    value: Any,
    *,
    worker_job_id: int,
) -> dict[str, Any] | None:
    """Validate canonical cleanup authority without accepting path material."""

    expected_fields = {
        "schema",
        "version",
        "state",
        "job_id",
        "delivery_owner",
        "delivery_claim_attempt",
        "workspace_present",
        "workspace_key",
        "tombstone_key",
        "intent_key",
        "audit_owner",
        "audit_attempt",
        "lease_expires_at",
        "reason",
        "updated_at",
    }
    if not isinstance(value, dict) or set(value) != expected_fields:
        return None
    job_id = _cleanup_positive_int(value.get("job_id"))
    delivery_claim_attempt = _cleanup_positive_int(
        value.get("delivery_claim_attempt")
    )
    delivery_owner = _valid_lease_owner(value.get("delivery_owner"))
    audit_attempt = _cleanup_nonnegative_int(value.get("audit_attempt"))
    audit_owner_value = value.get("audit_owner")
    audit_owner = (
        "" if audit_owner_value == "" else _valid_lease_owner(audit_owner_value)
    )
    lease_value = value.get("lease_expires_at")
    lease_expires_at = (
        "" if lease_value == "" else _canonical_timestamp(lease_value)
    )
    updated_at = _canonical_timestamp(value.get("updated_at"))
    if (
        value.get("schema")
        != video_edit_cleanup_audit.CLEANUP_AUDIT_SCHEMA
        or value.get("version")
        != video_edit_cleanup_audit.CLEANUP_AUDIT_VERSION
        or job_id != worker_job_id
        or not delivery_owner
        or delivery_claim_attempt <= 0
        or audit_attempt < 0
        or audit_attempt > video_edit_cleanup_audit.MAX_CLEANUP_ATTEMPTS
        or not isinstance(value.get("workspace_present"), bool)
        or not updated_at
    ):
        return None
    try:
        key = video_edit_cleanup_audit.workspace_key(
            job_id,
            delivery_claim_attempt,
        )
    except ValueError:
        return None
    if (
        value.get("workspace_key") != key
        or value.get("tombstone_key") != key
        or value.get("intent_key") != f"{key}.json"
        or value.get("state")
        not in {
            "pending",
            "failed_retryable",
            "succeeded",
            "failed_exhausted",
            "retained_delivery_unknown",
        }
        or (audit_owner_value != "" and not audit_owner)
        or (lease_value != "" and not lease_expires_at)
        or bool(audit_owner) != bool(lease_expires_at)
        or (audit_owner and audit_attempt <= 0)
    ):
        return None
    state = str(value["state"])
    reason_value = value.get("reason")
    reason = reason_value if isinstance(reason_value, str) else ""
    reason_valid = bool(
        isinstance(reason_value, str)
        and len(reason) <= 120
        and (
            not reason
            or (
                _cleanup_result_reason(reason) == reason
                and all(33 <= ord(char) <= 126 for char in reason)
            )
        )
    )
    workspace_present = bool(value["workspace_present"])
    leased = bool(audit_owner)
    if not reason_valid:
        return None
    if state == "pending" and not (
        workspace_present
        and reason == ""
        and (
            (audit_attempt == 0 and not leased)
            or (1 <= audit_attempt <= video_edit_cleanup_audit.MAX_CLEANUP_ATTEMPTS and leased)
        )
    ):
        return None
    if state == "failed_retryable" and not (
        workspace_present
        and bool(reason)
        and 1 <= audit_attempt <= video_edit_cleanup_audit.MAX_CLEANUP_ATTEMPTS
        and (
            audit_attempt < video_edit_cleanup_audit.MAX_CLEANUP_ATTEMPTS
            or leased
        )
    ):
        return None
    if state == "succeeded" and not (
        not workspace_present
        and not leased
        and (
            (audit_attempt == 0 and reason == "workspace_not_created")
            or (audit_attempt > 0 and reason == "")
        )
    ):
        return None
    if state == "failed_exhausted" and not (
        workspace_present
        and bool(reason)
        and not leased
        and audit_attempt in {0, video_edit_cleanup_audit.MAX_CLEANUP_ATTEMPTS}
    ):
        return None
    if state == "retained_delivery_unknown" and not (
        reason == "delivery_outcome_uncertain"
        and audit_attempt == 0
        and not leased
    ):
        return None
    return dict(value)


def _cleanup_result_reason(value: Any) -> str:
    """Keep only bounded diagnostic tokens, never paths or control data."""

    if not isinstance(value, str):
        return "cleanup_failed"
    token = value.strip()
    if (
        not token
        or any(ord(char) < 33 or ord(char) > 126 for char in token)
        or "/" in token
        or "\\" in token
    ):
        return "cleanup_failed"
    return token[:120]


def claim_cleanup_audit(
    conn,
    *,
    worker_job_id: Any,
    delivery_owner: Any,
    delivery_claim_attempt: Any,
    audit_owner: Any,
    now: Any,
    lease_seconds: Any,
) -> dict[str, Any]:
    """Atomically lease one terminal job's audit-only workspace cleanup."""

    job_id = _cleanup_positive_int(worker_job_id)
    bound_delivery_owner = _valid_lease_owner(delivery_owner)
    bound_delivery_attempt = _cleanup_positive_int(delivery_claim_attempt)
    claimant = _valid_lease_owner(audit_owner)
    current = _canonical_timestamp(now)
    duration = _cleanup_positive_int(lease_seconds)
    if (
        job_id <= 0
        or not bound_delivery_owner
        or bound_delivery_attempt <= 0
        or not claimant
        or not current
        or duration <= 0
        or duration > 86_400
    ):
        return {
            "ok": False,
            "action": "defer",
            "reason": "cleanup_audit_claim_invalid",
        }
    expires_at = (
        datetime.strptime(current, "%Y-%m-%d %H:%M:%S")
        + timedelta(seconds=duration)
    ).strftime("%Y-%m-%d %H:%M:%S")

    ensure_schema(conn)
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    row = conn.execute(
        """SELECT id,status,price_xu,charge_state,tail_json
             FROM video_edit_jobs
            WHERE local_worker_job_id=? AND product_type=?
              AND worker_job_type=? AND engine_route=? AND worker_owner=?""",
        (
            job_id,
            PRODUCT_TYPE,
            WORKER_JOB_TYPE,
            ENGINE_ROUTE,
            OUTBOX_OWNER,
        ),
    ).fetchone()
    if not row:
        return {
            "ok": False,
            "action": "orphan_retained",
            "reason": "cleanup_job_missing",
        }
    status = str(row[1] or "")
    if status not in TERMINAL_JOB_STATES:
        return {
            "ok": False,
            "action": "retain_nonterminal",
            "reason": "cleanup_job_nonterminal",
        }
    try:
        canonical_tail = json.loads(str(row[4]))
    except (TypeError, ValueError, json.JSONDecodeError):
        canonical_tail = None
    if not isinstance(canonical_tail, dict):
        canonical_tail = None
    audit = _cleanup_audit_record(
        canonical_tail.get("cleanup_audit") if canonical_tail is not None else None,
        worker_job_id=job_id,
    )
    if (
        audit is None
        or audit.get("delivery_owner") != bound_delivery_owner
        or audit.get("delivery_claim_attempt") != bound_delivery_attempt
    ):
        return {
            "ok": False,
            "action": "orphan_retained",
            "reason": "cleanup_delivery_binding_mismatch",
        }

    state = str(audit.get("state") or "")
    if status == "delivery_unknown":
        if state != "retained_delivery_unknown":
            return {
                "ok": False,
                "action": "orphan_retained",
                "reason": "cleanup_terminal_state_invalid",
            }
        return {
            "ok": True,
            "action": "remove_intent",
            "state": state,
        }
    try:
        price_xu = _strict_nonnegative_int(
            row[2], reason="canonical_price_invalid"
        )
    except ValueError:
        return {
            "ok": False,
            "action": "defer",
            "reason": "cleanup_charge_not_terminal",
        }
    charge_state = str(row[3] or "")
    if status in {"delivered", "charged"} and (
        (price_xu > 0 and charge_state not in {"charged", "charge_failed"})
        or (status == "charged" and charge_state != "charged")
    ):
        return {
            "ok": False,
            "action": "defer",
            "reason": "cleanup_charge_not_terminal",
        }
    if state in {"succeeded", "failed_exhausted"}:
        return {
            "ok": True,
            "action": "remove_intent",
            "state": state,
        }
    if state not in {"pending", "failed_retryable"}:
        return {
            "ok": False,
            "action": "orphan_retained",
            "reason": "cleanup_terminal_state_invalid",
        }

    prior_attempt = _cleanup_nonnegative_int(audit.get("audit_attempt"))
    prior_owner = str(audit.get("audit_owner") or "")
    prior_expiry = str(audit.get("lease_expires_at") or "")
    if prior_owner and prior_expiry > current:
        return {
            "ok": False,
            "action": "defer",
            "reason": "cleanup_audit_lease_active",
        }
    if prior_attempt == video_edit_cleanup_audit.MAX_CLEANUP_ATTEMPTS:
        exhausted_audit = dict(audit)
        exhausted_audit.update(
            {
                "state": "failed_exhausted",
                "audit_owner": "",
                "lease_expires_at": "",
                "reason": "cleanup_audit_attempts_exhausted",
                "updated_at": current,
            }
        )
        exhausted_tail = dict(canonical_tail)
        exhausted_tail["cleanup_audit"] = exhausted_audit
        cursor = conn.execute(
            """UPDATE video_edit_jobs SET tail_json=?
                WHERE id=? AND local_worker_job_id=? AND status=?
                  AND price_xu=? AND charge_state=? AND tail_json=?""",
            (
                _json(exhausted_tail),
                int(row[0]),
                job_id,
                status,
                row[2],
                row[3],
                str(row[4]),
            ),
        )
        if int(cursor.rowcount or 0) != 1:
            return {
                "ok": False,
                "action": "defer",
                "reason": "cleanup_audit_claim_conflict",
            }
        return {
            "ok": True,
            "action": "remove_intent",
            "state": "failed_exhausted",
        }
    if prior_attempt < 0 or prior_attempt > video_edit_cleanup_audit.MAX_CLEANUP_ATTEMPTS:
        return {
            "ok": False,
            "action": "orphan_retained",
            "reason": "cleanup_audit_attempt_invalid",
        }

    claimed_audit = dict(audit)
    claimed_audit.update(
        {
            "audit_owner": claimant,
            "audit_attempt": prior_attempt + 1,
            "lease_expires_at": expires_at,
            "updated_at": current,
        }
    )
    claimed_tail = dict(canonical_tail)
    claimed_tail["cleanup_audit"] = claimed_audit
    prior_tail_json = str(row[4])
    cursor = conn.execute(
        """UPDATE video_edit_jobs SET tail_json=?
            WHERE id=? AND local_worker_job_id=? AND status=?
              AND price_xu=? AND charge_state=? AND tail_json=?""",
        (
            _json(claimed_tail),
            int(row[0]),
            job_id,
            status,
            row[2],
            row[3],
            prior_tail_json,
        ),
    )
    if int(cursor.rowcount or 0) != 1:
        return {
            "ok": False,
            "action": "defer",
            "reason": "cleanup_audit_claim_conflict",
        }
    return {
        "ok": True,
        "action": "cleanup",
        "job_id": job_id,
        "delivery_owner": bound_delivery_owner,
        "delivery_claim_attempt": bound_delivery_attempt,
        "workspace_key": claimed_audit["workspace_key"],
        "tombstone_key": claimed_audit["tombstone_key"],
        "intent_key": claimed_audit["intent_key"],
        "audit_owner": claimant,
        "audit_attempt": claimed_audit["audit_attempt"],
        "lease_expires_at": expires_at,
        "cleanup_audit": claimed_audit,
    }


def record_cleanup_audit_result(
    conn,
    *,
    worker_job_id: Any,
    delivery_owner: Any,
    delivery_claim_attempt: Any,
    audit_owner: Any,
    audit_attempt: Any,
    now: Any,
    outcome: Any,
    reason: Any,
) -> dict[str, Any]:
    """CAS one leased cleanup result without changing delivery or billing truth."""

    job_id = _cleanup_positive_int(worker_job_id)
    bound_delivery_owner = _valid_lease_owner(delivery_owner)
    bound_delivery_attempt = _cleanup_positive_int(delivery_claim_attempt)
    claimant = _valid_lease_owner(audit_owner)
    claimed_attempt = _cleanup_positive_int(audit_attempt)
    current = _canonical_timestamp(now)
    result_outcome = outcome if isinstance(outcome, str) else ""
    if (
        job_id <= 0
        or not bound_delivery_owner
        or bound_delivery_attempt <= 0
        or not claimant
        or claimed_attempt <= 0
        or not current
        or result_outcome not in {"succeeded", "failed_retryable"}
    ):
        return {"ok": False, "reason": "cleanup_audit_result_invalid"}

    ensure_schema(conn)
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    row = conn.execute(
        """SELECT id,status,price_xu,charge_state,tail_json
             FROM video_edit_jobs
            WHERE local_worker_job_id=? AND product_type=?
              AND worker_job_type=? AND engine_route=? AND worker_owner=?""",
        (
            job_id,
            PRODUCT_TYPE,
            WORKER_JOB_TYPE,
            ENGINE_ROUTE,
            OUTBOX_OWNER,
        ),
    ).fetchone()
    if not row or str(row[1] or "") not in TERMINAL_JOB_STATES:
        return {"ok": False, "reason": "cleanup_audit_lease_conflict"}
    try:
        canonical_tail = json.loads(str(row[4]))
    except (TypeError, ValueError, json.JSONDecodeError):
        canonical_tail = None
    if not isinstance(canonical_tail, dict):
        canonical_tail = None
    audit = _cleanup_audit_record(
        canonical_tail.get("cleanup_audit") if canonical_tail is not None else None,
        worker_job_id=job_id,
    )
    lease_expires_at = (
        str(audit.get("lease_expires_at") or "") if audit is not None else ""
    )
    if (
        audit is None
        or audit.get("delivery_owner") != bound_delivery_owner
        or audit.get("delivery_claim_attempt") != bound_delivery_attempt
        or audit.get("audit_owner") != claimant
        or audit.get("audit_attempt") != claimed_attempt
        or audit.get("state") not in {"pending", "failed_retryable"}
        or not lease_expires_at
        or lease_expires_at <= current
    ):
        return {"ok": False, "reason": "cleanup_audit_lease_conflict"}

    status = str(row[1] or "")
    try:
        price_xu = _strict_nonnegative_int(
            row[2], reason="canonical_price_invalid"
        )
    except ValueError:
        return {"ok": False, "reason": "cleanup_audit_lease_conflict"}
    charge_state = str(row[3] or "")
    if (
        status == "delivery_unknown"
        or (
            status in {"delivered", "charged"}
            and (
                (price_xu > 0 and charge_state not in {"charged", "charge_failed"})
                or (status == "charged" and charge_state != "charged")
            )
        )
    ):
        return {"ok": False, "reason": "cleanup_audit_lease_conflict"}

    completed_audit = dict(audit)
    if result_outcome == "succeeded":
        completed_audit.update(
            {
                "state": "succeeded",
                "workspace_present": False,
                "audit_owner": "",
                "lease_expires_at": "",
                "reason": "",
                "updated_at": current,
            }
        )
    else:
        exhausted = (
            claimed_attempt
            >= video_edit_cleanup_audit.MAX_CLEANUP_ATTEMPTS
        )
        completed_audit.update(
            {
                "state": "failed_exhausted" if exhausted else "failed_retryable",
                "audit_owner": "",
                "lease_expires_at": "",
                "reason": _cleanup_result_reason(reason),
                "updated_at": current,
            }
        )
    completed_tail = dict(canonical_tail)
    completed_tail["cleanup_audit"] = completed_audit
    prior_tail_json = str(row[4])
    cursor = conn.execute(
        """UPDATE video_edit_jobs SET tail_json=?
            WHERE id=? AND local_worker_job_id=? AND status=?
              AND price_xu=? AND charge_state=? AND tail_json=?""",
        (
            _json(completed_tail),
            int(row[0]),
            job_id,
            status,
            row[2],
            row[3],
            prior_tail_json,
        ),
    )
    if int(cursor.rowcount or 0) != 1:
        return {"ok": False, "reason": "cleanup_audit_lease_conflict"}
    return {"ok": True, "cleanup_audit": completed_audit}


def _persisted_video_edit_expected_output_count(value: Any) -> int:
    if not isinstance(value, dict):
        raise ValueError("video_local_edit_worker_payload_invalid")
    mode = value.get("local1_mode")
    if not isinstance(mode, str) or mode != mode.strip().lower():
        raise ValueError("video_local_edit_worker_payload_invalid")
    if mode == "manual":
        return 1
    if mode != "split":
        raise ValueError("video_local_edit_worker_payload_invalid")
    ranges = value.get("split_ranges")
    if not isinstance(ranges, list) or not ranges:
        raise ValueError("video_local_edit_worker_payload_invalid")
    previous_end = 0
    for position, item in enumerate(ranges, start=1):
        if not isinstance(item, dict):
            raise ValueError("video_local_edit_worker_payload_invalid")
        try:
            index = _strict_nonnegative_int(
                item.get("index"), reason="split_index_invalid"
            )
            start_ms = _strict_nonnegative_int(
                item.get("start_ms"), reason="split_range_invalid"
            )
            end_ms = _strict_nonnegative_int(
                item.get("end_ms"), reason="split_range_invalid"
            )
        except ValueError:
            raise ValueError("video_local_edit_worker_payload_invalid") from None
        if index != position or end_ms <= start_ms or start_ms < previous_end:
            raise ValueError("video_local_edit_worker_payload_invalid")
        previous_end = end_ms
    return len(ranges)


def _video_local_edit_resume_contract(
    *,
    receipts: list[dict[str, Any]],
    expected_output_count: int,
    strict_cursor: video_edit_long_media.DeliveryCursor | None,
) -> dict[str, Any]:
    normalized = normalize_artifact_receipt_prefix(
        receipts,
        expected_output_count=expected_output_count,
    )
    digest = hashlib.sha256(
        json.dumps(
            normalized,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    contract = {
        "schema": VIDEO_LOCAL_EDIT_RESUME_SCHEMA,
        "version": VIDEO_LOCAL_EDIT_RESUME_VERSION,
        "expected_output_count": expected_output_count,
        "artifact_receipt_prefix": normalized,
        "prefix_count": len(normalized),
        "prefix_digest": digest,
        "compatibility": "strict" if strict_cursor is not None else "legacy_receipt_only",
        "delivery_cursor": strict_cursor.to_mapping() if strict_cursor is not None else None,
    }
    return normalize_video_local_edit_resume_contract(contract)


def claim_next_video_local_edit(
    conn,
    *,
    lease_owner: Any,
    now: Any,
    lease_seconds: Any,
    blank_lease_grace_cutoff: Any = None,
    supports_receipt_prefix_resume: bool = False,
) -> dict[str, Any]:
    """Atomically claim queued or safely recoverable local Video Edit work."""

    owner = _valid_lease_owner(lease_owner)
    resume_capable = supports_receipt_prefix_resume is True
    current = _canonical_timestamp(now)
    grace_cutoff = (
        "" if blank_lease_grace_cutoff is None else _canonical_timestamp(blank_lease_grace_cutoff)
    )
    try:
        lease_duration = _strict_nonnegative_int(
            lease_seconds, reason="lease_seconds_invalid"
        )
    except ValueError:
        return {}
    if (
        not owner
        or not current
        or lease_duration <= 0
        or lease_duration > 86_400
        or (blank_lease_grace_cutoff is not None and not grace_cutoff)
        or (grace_cutoff and grace_cutoff > current)
    ):
        return {}
    expires = (
        datetime.strptime(current, "%Y-%m-%d %H:%M:%S")
        + timedelta(seconds=lease_duration)
    ).strftime("%Y-%m-%d %H:%M:%S")

    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    conn.execute("SAVEPOINT video_edit_claim")
    try:
        candidates = conn.execute(
            """SELECT l.id,l.user_id,l.command,l.job_type,l.provider,l.input_file_id,
                      l.output_file_id,l.output_url,l.error_short,l.created_at,l.finished_at,
                      l.xu_cost,l.admin_only,
                      j.id,j.source_sha256,j.artifact_receipts_json,j.delivery_cursor,
                      j.receipt_state,j.tail_json,o.id,o.attempt_count,l.status,j.status,o.status,
                      COALESCE(o.lease_owner,''),COALESCE(o.lease_expires_at,''),o.updated_at,
                      l.started_at
                 FROM local_worker_jobs AS l
                 JOIN video_edit_jobs AS j ON j.local_worker_job_id=l.id
                 JOIN video_edit_outbox AS o
                   ON o.local_worker_job_id=l.id AND o.edit_job_id=j.id
                WHERE l.command='video_editengine1'
                  AND l.job_type=? AND l.provider=?
                  AND j.product_type=? AND j.worker_job_type=?
                  AND j.engine_route=? AND j.worker_owner=?
                  AND o.owner=? AND o.attempt_count>=0
                  AND (
                    (l.status='queued' AND j.status='queued' AND o.status='pending'
                     AND o.available_at<=?
                     AND COALESCE(o.lease_owner,'')=''
                     AND COALESCE(o.lease_expires_at,'')='')
                    OR
                    (l.status='running' AND j.status='rendering' AND o.status='running'
                     AND (
                       (COALESCE(o.lease_owner,'')<>''
                        AND COALESCE(o.lease_expires_at,'')<>''
                        AND o.lease_expires_at<=?)
                       OR
                       (COALESCE(o.lease_owner,'')=''
                        AND COALESCE(o.lease_expires_at,'')=''
                        AND ?<>'' AND o.updated_at<=?)
                     ))
                  )
                ORDER BY o.available_at ASC,o.id ASC""",
            (
                WORKER_JOB_TYPE,
                ENGINE_ROUTE,
                PRODUCT_TYPE,
                WORKER_JOB_TYPE,
                ENGINE_ROUTE,
                OUTBOX_OWNER,
                OUTBOX_OWNER,
                current,
                current,
                grace_cutoff,
                grace_cutoff,
            ),
        ).fetchall()
        for row in candidates:
            try:
                persisted_worker_payload = json.loads(str(row[5] or ""))
                expected_output_count = _persisted_video_edit_expected_output_count(
                    persisted_worker_payload
                )
                persisted_receipts = json.loads(str(row[15] or ""))
                delivery_cursor = _strict_nonnegative_int(
                    row[16], reason="delivery_cursor_invalid"
                )
                persisted_tail = json.loads(str(row[18] or ""))
                if not isinstance(persisted_tail, dict):
                    continue
                strict_cursor = None
                if "delivery_cursor" in persisted_tail:
                    strict_cursor = video_edit_long_media.DeliveryCursor.from_mapping(
                        persisted_tail["delivery_cursor"]
                    )
                attempt_count = _strict_nonnegative_int(
                    row[20], reason="claim_attempt_invalid"
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            receipts = _artifact_receipts(persisted_receipts)
            source_sha256 = row[14]
            receipt_state = str(row[17] or "")
            empty_source_without_reuse = bool(
                source_sha256 == "" and delivery_cursor == 0 and receipts == []
            )
            if (
                not _artifact_receipts_valid(persisted_receipts)
                or delivery_cursor != len(receipts)
                or len(receipts) > expected_output_count
                or not (_is_sha256(source_sha256) or empty_source_without_reuse)
                or receipt_state != "not_created"
            ):
                continue
            if strict_cursor is not None:
                try:
                    _validate_delivery_cursor_receipt_prefix(
                        strict_cursor,
                        receipts,
                    )
                except ValueError:
                    continue

            worker_job_id = int(row[0])
            edit_job_id = int(row[13])
            outbox_id = int(row[19])
            local_status = str(row[21] or "")
            edit_status = str(row[22] or "")
            outbox_status = str(row[23] or "")
            old_lease_owner = str(row[24] or "")
            old_lease_expires = str(row[25] or "")
            old_outbox_updated = str(row[26] or "")
            persisted_started_at = str(row[27] or "")
            if local_status == "running":
                if old_lease_owner:
                    canonical_old_expiry = _canonical_timestamp(old_lease_expires)
                    if not canonical_old_expiry or canonical_old_expiry > current:
                        continue
                else:
                    canonical_old_updated = _canonical_timestamp(old_outbox_updated)
                    if (
                        not grace_cutoff
                        or not canonical_old_updated
                        or canonical_old_updated > grace_cutoff
                    ):
                        continue
            if (
                local_status == "running"
                and strict_cursor is not None
                and strict_cursor.state == "rejected"
            ):
                reason = str(
                    strict_cursor.rejection_code or "delivery_rejected"
                )[:180]
                terminal_detail = _json(
                    {
                        "stage": "failed_no_charge",
                        "reason": reason,
                        "artifact_receipts": receipts,
                        "delivery_cursor": strict_cursor.to_mapping(),
                        "charge": 0,
                        "charged_xu": 0,
                    }
                )
                conn.execute("SAVEPOINT video_edit_rejected_terminal")
                outbox_terminal = conn.execute(
                    """UPDATE video_edit_outbox
                          SET status='terminal_failed',terminal_reason=?,updated_at=?
                        WHERE id=? AND local_worker_job_id=? AND edit_job_id=? AND owner=?
                          AND status='running' AND attempt_count=?
                          AND COALESCE(lease_owner,'')=?
                          AND COALESCE(lease_expires_at,'')=? AND updated_at=?""",
                    (
                        reason,
                        current,
                        outbox_id,
                        worker_job_id,
                        edit_job_id,
                        OUTBOX_OWNER,
                        attempt_count,
                        old_lease_owner,
                        old_lease_expires,
                        old_outbox_updated,
                    ),
                )
                local_terminal = conn.execute(
                    """UPDATE local_worker_jobs
                          SET status='failed',error_short=?,finished_at=?,updated_at=?
                        WHERE id=? AND command='video_editengine1' AND job_type=?
                          AND provider=? AND status='running'""",
                    (
                        terminal_detail,
                        current,
                        current,
                        worker_job_id,
                        WORKER_JOB_TYPE,
                        ENGINE_ROUTE,
                    ),
                )
                edit_terminal = conn.execute(
                    """UPDATE video_edit_jobs
                          SET status='failed_no_charge',progress_percent=0,blocker=?,
                              charge_state='not_charged',charged_xu=0,
                              finished_at=?,updated_at=?
                        WHERE id=? AND local_worker_job_id=? AND product_type=?
                          AND worker_job_type=? AND engine_route=? AND worker_owner=?
                          AND status='rendering'""",
                    (
                        reason,
                        current,
                        current,
                        edit_job_id,
                        worker_job_id,
                        PRODUCT_TYPE,
                        WORKER_JOB_TYPE,
                        ENGINE_ROUTE,
                        OUTBOX_OWNER,
                    ),
                )
                if any(
                    int(cursor.rowcount or 0) != 1
                    for cursor in (outbox_terminal, local_terminal, edit_terminal)
                ):
                    conn.execute("ROLLBACK TO SAVEPOINT video_edit_rejected_terminal")
                conn.execute("RELEASE SAVEPOINT video_edit_rejected_terminal")
                continue
            if (
                local_status == "running"
                and strict_cursor is not None
                and strict_cursor.state in {"sending", "unknown"}
            ):
                reason = "delivery_cursor_expired_ambiguous"
                terminal_detail = _json(
                    {
                        "stage": "delivery_unknown",
                        "reason": reason,
                        "artifact_receipts": receipts,
                        "delivery_cursor": strict_cursor.to_mapping(),
                    }
                )
                conn.execute("SAVEPOINT video_edit_ambiguous_terminal")
                outbox_terminal = conn.execute(
                    """UPDATE video_edit_outbox
                          SET status='terminal_delivery_unknown',terminal_reason=?,updated_at=?
                        WHERE id=? AND local_worker_job_id=? AND edit_job_id=? AND owner=?
                          AND status='running' AND attempt_count=?
                          AND COALESCE(lease_owner,'')=?
                          AND COALESCE(lease_expires_at,'')=? AND updated_at=?""",
                    (
                        reason,
                        current,
                        outbox_id,
                        worker_job_id,
                        edit_job_id,
                        OUTBOX_OWNER,
                        attempt_count,
                        old_lease_owner,
                        old_lease_expires,
                        old_outbox_updated,
                    ),
                )
                local_terminal = conn.execute(
                    """UPDATE local_worker_jobs
                          SET status='failed',error_short=?,finished_at=?,updated_at=?
                        WHERE id=? AND command='video_editengine1' AND job_type=?
                          AND provider=? AND status='running'""",
                    (
                        terminal_detail,
                        current,
                        current,
                        worker_job_id,
                        WORKER_JOB_TYPE,
                        ENGINE_ROUTE,
                    ),
                )
                edit_terminal = conn.execute(
                    """UPDATE video_edit_jobs
                          SET status='delivery_unknown',blocker=?,receipt_state='delivery_unknown',
                              charge_state='not_charged',charged_xu=0,finished_at=?,updated_at=?
                        WHERE id=? AND local_worker_job_id=? AND product_type=?
                          AND worker_job_type=? AND engine_route=? AND worker_owner=?
                          AND status='rendering'""",
                    (
                        reason,
                        current,
                        current,
                        edit_job_id,
                        worker_job_id,
                        PRODUCT_TYPE,
                        WORKER_JOB_TYPE,
                        ENGINE_ROUTE,
                        OUTBOX_OWNER,
                    ),
                )
                if any(
                    int(cursor.rowcount or 0) != 1
                    for cursor in (outbox_terminal, local_terminal, edit_terminal)
                ):
                    conn.execute("ROLLBACK TO SAVEPOINT video_edit_ambiguous_terminal")
                conn.execute("RELEASE SAVEPOINT video_edit_ambiguous_terminal")
                continue
            if receipts and not resume_capable:
                continue
            break
        else:
            conn.execute("RELEASE SAVEPOINT video_edit_claim")
            return {}
        next_attempt = attempt_count + 1

        outbox_update = conn.execute(
            """UPDATE video_edit_outbox
                  SET status='running',attempt_count=?,lease_owner=?,lease_expires_at=?,updated_at=?
                WHERE id=? AND local_worker_job_id=? AND edit_job_id=? AND owner=?
                  AND status=? AND attempt_count=?
                  AND COALESCE(lease_owner,'')=?
                  AND COALESCE(lease_expires_at,'')=? AND updated_at=?""",
            (
                next_attempt,
                owner,
                expires,
                current,
                outbox_id,
                worker_job_id,
                edit_job_id,
                OUTBOX_OWNER,
                outbox_status,
                attempt_count,
                old_lease_owner,
                old_lease_expires,
                old_outbox_updated,
            ),
        )
        local_update = conn.execute(
            """UPDATE local_worker_jobs
                  SET status='running',started_at=CASE WHEN COALESCE(started_at,'')=''
                       THEN ? ELSE started_at END,worker_id=?,updated_at=?
                WHERE id=? AND command='video_editengine1' AND job_type=?
                  AND provider=? AND status=?""",
            (current, owner, current, worker_job_id, WORKER_JOB_TYPE, ENGINE_ROUTE, local_status),
        )
        edit_update = conn.execute(
            """UPDATE video_edit_jobs
                  SET status='rendering',started_at=CASE WHEN started_at=''
                       THEN ? ELSE started_at END,updated_at=?
                WHERE id=? AND local_worker_job_id=? AND product_type=?
                  AND worker_job_type=? AND engine_route=? AND worker_owner=? AND status=?""",
            (
                current,
                current,
                edit_job_id,
                worker_job_id,
                PRODUCT_TYPE,
                WORKER_JOB_TYPE,
                ENGINE_ROUTE,
                OUTBOX_OWNER,
                edit_status,
            ),
        )
        if any(int(cursor.rowcount or 0) != 1 for cursor in (outbox_update, local_update, edit_update)):
            conn.execute("ROLLBACK TO SAVEPOINT video_edit_claim")
            conn.execute("RELEASE SAVEPOINT video_edit_claim")
            return {}
        conn.execute("RELEASE SAVEPOINT video_edit_claim")
        claimed_job = {
            "id": worker_job_id,
            "user_id": str(row[1] or ""),
            "command": str(row[2] or ""),
            "job_type": str(row[3] or ""),
            "status": "running",
            "provider": str(row[4] or ""),
            "input_file_id": str(row[5] or ""),
            "output_file_id": str(row[6] or ""),
            "output_url": str(row[7] or ""),
            "error_short": str(row[8] or ""),
            "created_at": str(row[9] or ""),
            "started_at": persisted_started_at or current,
            "finished_at": str(row[10] or ""),
            "xu_cost": int(row[11] or 0),
            "admin_only": int(row[12] or 0),
            "worker_id": owner,
            "updated_at": current,
            "edit_job_id": edit_job_id,
            "outbox_id": outbox_id,
            "artifact_receipt_prefix": receipts[:delivery_cursor],
            "delivery_cursor": delivery_cursor,
            "source_sha256": source_sha256.lower(),
            "receipt_state": receipt_state,
            "claim_attempt": next_attempt,
            "lease_owner": owner,
            "lease_expires_at": expires,
        }
        if resume_capable:
            claimed_job["resume_contract"] = _video_local_edit_resume_contract(
                receipts=receipts,
                expected_output_count=expected_output_count,
                strict_cursor=strict_cursor,
            )
        return claimed_job
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT video_edit_claim")
        conn.execute("RELEASE SAVEPOINT video_edit_claim")
        raise


def renew_worker_lease(
    conn,
    *,
    worker_job_id: Any,
    lease_owner: Any,
    now: Any,
    lease_expires_at: Any,
    claim_attempt: Any = None,
) -> bool:
    """Strictly renew one live lease owned by the exact claim attempt."""

    try:
        job_id = _strict_nonnegative_int(worker_job_id, reason="worker_job_id_invalid")
    except ValueError:
        return False
    if job_id <= 0:
        return False
    owner = _valid_lease_owner(lease_owner)
    try:
        attempt = _strict_nonnegative_int(claim_attempt, reason="claim_attempt_invalid")
    except ValueError:
        return False
    current = _canonical_timestamp(now)
    expires = _canonical_timestamp(lease_expires_at)
    if not owner or attempt <= 0 or not current or not expires or expires <= current:
        return False
    active = conn.execute(
        """SELECT o.lease_expires_at
             FROM video_edit_outbox AS o
             JOIN video_edit_jobs AS j
               ON j.id=o.edit_job_id AND j.local_worker_job_id=o.local_worker_job_id
             JOIN local_worker_jobs AS l ON l.id=o.local_worker_job_id
            WHERE o.local_worker_job_id=? AND o.owner=? AND o.status='running'
              AND o.lease_owner=? AND o.attempt_count=?
              AND j.product_type=? AND j.worker_job_type=? AND j.engine_route=?
              AND j.worker_owner=? AND j.status='rendering'
              AND l.command='video_editengine1' AND l.job_type=? AND l.provider=?
              AND l.status='running' AND l.worker_id=?""",
        (
            job_id,
            OUTBOX_OWNER,
            owner,
            attempt,
            PRODUCT_TYPE,
            WORKER_JOB_TYPE,
            ENGINE_ROUTE,
            OUTBOX_OWNER,
            WORKER_JOB_TYPE,
            ENGINE_ROUTE,
            owner,
        ),
    ).fetchone()
    active_expiry = _canonical_timestamp(active[0]) if active else ""
    if not active_expiry or active_expiry <= current:
        return False
    cursor = conn.execute(
        """UPDATE video_edit_outbox
              SET lease_expires_at=?,updated_at=?
            WHERE local_worker_job_id=? AND owner=? AND status='running'
              AND lease_owner=? AND attempt_count=? AND lease_expires_at=?""",
        (expires, current, job_id, OUTBOX_OWNER, owner, attempt, active_expiry),
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
    delivery_owner, delivery_claim_attempt = _cleanup_delivery_binding(
        conn,
        worker_job_id,
    )
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
    current_tail = current.get("tail")
    if not isinstance(current_tail, dict):
        raise ValueError("delivery_cursor_invalid")
    canonical_tail = dict(current_tail)
    current_strict_cursor = None
    if "delivery_cursor" in canonical_tail:
        try:
            current_strict_cursor = video_edit_long_media.DeliveryCursor.from_mapping(
                canonical_tail["delivery_cursor"]
            )
            _validate_delivery_cursor_receipt_prefix(
                current_strict_cursor,
                current_artifacts,
            )
        except (TypeError, ValueError):
            raise ValueError("delivery_cursor_invalid") from None
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
            if current_strict_cursor is not None or "delivery_cursor" in detail:
                raise ValueError("delivery_cursor_invalid")
            status = "delivery_unknown"
            detail = {**detail, "reason": "artifact_receipt_history_mismatch"}
            incoming_artifacts = current_artifacts
    effective_artifacts = incoming_artifacts or current_artifacts
    canonical_strict_cursor = current_strict_cursor
    if "delivery_cursor" in detail:
        try:
            incoming_strict_cursor = video_edit_long_media.DeliveryCursor.from_mapping(
                detail["delivery_cursor"]
            )
            transition_start = current_strict_cursor
            if transition_start is None:
                next_output_index = len(current_artifacts) + 1
                if (
                    incoming_strict_cursor.state != "sending"
                    or incoming_strict_cursor.output_index != next_output_index
                ):
                    raise ValueError("delivery cursor transition rejected")
                transition_start = video_edit_long_media.DeliveryCursor(
                    output_index=next_output_index
                )
            elif transition_start.output_index != incoming_strict_cursor.output_index:
                completed_previous_output = bool(
                    transition_start.state == "delivered"
                    and incoming_strict_cursor.state == "sending"
                    and incoming_strict_cursor.output_index
                    == transition_start.output_index + 1
                    and len(current_artifacts) >= transition_start.output_index
                )
                if not completed_previous_output:
                    raise ValueError("delivery cursor transition rejected")
                transition_start = video_edit_long_media.DeliveryCursor(
                    output_index=incoming_strict_cursor.output_index
                )
            canonical_strict_cursor = video_edit_long_media.advance_delivery_cursor(
                transition_start,
                incoming_strict_cursor,
            )
            _validate_delivery_cursor_receipt_prefix(
                canonical_strict_cursor,
                effective_artifacts,
            )
            canonical_tail["delivery_cursor"] = canonical_strict_cursor.to_mapping()
        except (TypeError, ValueError):
            raise ValueError("delivery_cursor_invalid") from None
    elif canonical_strict_cursor is not None:
        _validate_delivery_cursor_receipt_prefix(
            canonical_strict_cursor,
            effective_artifacts,
        )
    tail_json = _json(canonical_tail)
    artifact_json = json.dumps(
        effective_artifacts,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    artifact_cursor = len(effective_artifacts)
    if status == "running":
        stage = str(detail.get("stage") or "rendering")
        current_progress = int(current.get("progress_percent") or 0)
        stage_progress = {"inspecting_input": 25, "preparing_plan": 35, "processing_video": 55, "validating_output": 80, "delivering": 90}.get(stage)
        progress = max(current_progress, stage_progress) if stage_progress is not None else current_progress
        cursor = conn.execute(
            """UPDATE video_edit_jobs SET status='rendering',progress_percent=?,
               artifact_receipts_json=?,delivery_cursor=?,tail_json=?,
               started_at=CASE WHEN started_at='' THEN ? ELSE started_at END,updated_at=?
               WHERE id=? AND status NOT IN ('delivered','charged','failed_no_charge','delivery_unknown')""",
            (progress, artifact_json, artifact_cursor, tail_json, now, now, int(current["id"])),
        )
        if cursor.rowcount != 1:
            return get_job_by_worker_id(conn, worker_job_id)
        conn.execute(
            "UPDATE video_edit_outbox SET status='running',attempt_count=CASE WHEN attempt_count=0 THEN 1 ELSE attempt_count END,updated_at=? WHERE edit_job_id=?",
            (now, int(current["id"])),
        )
    elif status == "delivery_unknown":
        reason = str(detail.get("reason") or "telegram_delivery_receipt_commit_uncertain")[:180]
        canonical_tail = _seed_cleanup_audit(
            canonical_tail,
            worker_job_id=worker_job_id,
            terminal_status="delivery_unknown",
            delivery_owner=delivery_owner,
            delivery_claim_attempt=delivery_claim_attempt,
            cleanup_intent=detail.get("cleanup_intent"),
            now=now,
        )
        tail_json = _json(canonical_tail)
        cursor = conn.execute(
            """UPDATE video_edit_jobs SET status='delivery_unknown',blocker=?,
               artifact_receipts_json=?,delivery_cursor=?,tail_json=?,
               receipt_state='delivery_unknown',charge_state='not_charged',charged_xu=0,
               finished_at=?,updated_at=?
               WHERE id=? AND status NOT IN ('delivered','charged','failed_no_charge','delivery_unknown')""",
            (reason, artifact_json, artifact_cursor, tail_json, now, now, int(current["id"])),
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
        if canonical_strict_cursor is not None:
            strict_terminal_valid = bool(
                canonical_strict_cursor.state == "delivered"
                and canonical_strict_cursor.output_index == output_count
                and artifacts_declared
                and len(receipt_artifacts) == output_count
                and receipt_artifacts == effective_artifacts
                and receipt_artifacts
                and delivery_message_id == receipt_artifacts[-1]["message_id"]
                and delivery_file_id == receipt_artifacts[-1]["file_id"]
                and canonical_strict_cursor.message_id
                == receipt_artifacts[-1]["message_id"]
                and canonical_strict_cursor.file_id
                == receipt_artifacts[-1]["file_id"]
            )
            if not strict_terminal_valid:
                raise ValueError("delivery_cursor_invalid")
        artifact_identity_valid = bool(
            not artifacts_declared
            or (
                receipt_artifacts
                and delivery_message_id
                == receipt_artifacts[-1 if canonical_strict_cursor is not None else 0][
                    "message_id"
                ]
                and delivery_file_id
                == receipt_artifacts[-1 if canonical_strict_cursor is not None else 0][
                    "file_id"
                ]
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
            canonical_tail = _seed_cleanup_audit(
                canonical_tail,
                worker_job_id=worker_job_id,
                terminal_status="delivered",
                delivery_owner=delivery_owner,
                delivery_claim_attempt=delivery_claim_attempt,
                cleanup_intent=detail.get("cleanup_intent"),
                now=now,
            )
            tail_json = _json(canonical_tail)
            cursor = conn.execute(
                """UPDATE video_edit_jobs SET status='delivered',progress_percent=100,blocker='',
                   source_video_path=?,source_sha256=?,output_file_id=?,output_path=?,output_sha256=?,output_size_bytes=?,ffprobe_json=?,
                   delivery_message_id=?,delivery_file_id=?,artifact_receipts_json=?,delivery_cursor=?,tail_json=?,receipt_state='created',
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
                    tail_json,
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
        if (
            canonical_strict_cursor is not None
            and canonical_strict_cursor.state != "rejected"
        ):
            raise ValueError("delivery_cursor_invalid")
        reason = str(detail.get("reason") or "local_edit_failed_no_charge")[:180]
        canonical_tail = _seed_cleanup_audit(
            canonical_tail,
            worker_job_id=worker_job_id,
            terminal_status="failed_no_charge",
            delivery_owner=delivery_owner,
            delivery_claim_attempt=delivery_claim_attempt,
            cleanup_intent=detail.get("cleanup_intent"),
            now=now,
        )
        tail_json = _json(canonical_tail)
        cursor = conn.execute(
            """UPDATE video_edit_jobs SET status='failed_no_charge',progress_percent=0,blocker=?,
               tail_json=?,charge_state='not_charged',charged_xu=0,finished_at=?,updated_at=?
               WHERE id=? AND status NOT IN ('delivered','charged','failed_no_charge','delivery_unknown')""",
            (reason, tail_json, now, now, int(current["id"])),
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
                  artifact_receipts_json,delivery_cursor,tail_json
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
        canonical_tail = json.loads(str(row[14]))
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(canonical_tail, dict):
        return False
    artifacts = _artifact_receipts(artifact_value)
    if not _artifact_receipts_valid(artifact_value):
        return False
    delivery_message_id = _telegram_message_id(row[10])
    delivery_file_id = _telegram_file_id(row[11])
    output_file_id = _telegram_file_id(row[5])
    output_count = len(artifacts) if artifacts else 1
    strict_cursor = None
    if "delivery_cursor" in canonical_tail:
        try:
            strict_cursor = video_edit_long_media.DeliveryCursor.from_mapping(
                canonical_tail["delivery_cursor"]
            )
            _validate_delivery_cursor_receipt_prefix(strict_cursor, artifacts)
        except (TypeError, ValueError):
            return False
        if strict_cursor.state != "delivered":
            return False
    bound_artifact = (
        artifacts[-1]
        if artifacts and strict_cursor is not None
        else artifacts[0] if artifacts else None
    )
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
            bound_artifact is None
            or (
                delivery_message_id == bound_artifact["message_id"]
                and delivery_file_id == bound_artifact["file_id"]
                and output_size_bytes == sum(int(item["size"]) for item in artifacts)
                and (
                    strict_cursor is None
                    or (
                        strict_cursor.message_id == bound_artifact["message_id"]
                        and strict_cursor.file_id == bound_artifact["file_id"]
                    )
                )
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
              AND delivery_cursor=?
              AND tail_json=?""",
        (
            _now(),
            int(worker_job_id or 0),
            row[3], row[4], row[5], row[6], row[7], row[8], row[9],
            row[10], row[11], row[12], row[13], row[14],
        ),
    )
    return int(cursor.rowcount or 0) == 1
