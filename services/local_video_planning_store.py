from __future__ import annotations

import copy
import hashlib
import html
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone

from services import video_planning_assistant as planner


MAX_ACTIVE_PLANS = 20
MAX_SUMMARY_SOURCE_LENGTH = 16_384
MAX_TELEGRAM_VISIBLE_LENGTH = 4_096
_PLAN_KEY_RE = re.compile(r"^[a-f0-9]{12}$")
_PLAN_FIELDS = {
    "plan_schema_version",
    "plan_id",
    "title",
    "goal",
    "editing_brief",
    "platform_ratio",
    "source_duration",
    "target_duration",
    "available_assets",
    "priorities",
    "selected_operations",
    "ordered_steps",
    "rights_notes",
    "created_at",
    "updated_at",
}
_GOAL_IDS = frozenset(value for value, _label in planner.GOAL_OPTIONS)
_PLATFORM_IDS = frozenset(value for value, _label in planner.PLATFORM_OPTIONS)
_SOURCE_IDS = frozenset(value for value, _label in planner.SOURCE_DURATION_OPTIONS)
_TARGET_IDS = frozenset(value for value, _label in planner.TARGET_DURATION_OPTIONS)
_ASSET_IDS = frozenset(value for value, _label in planner.ASSET_OPTIONS)
_PRIORITY_IDS = frozenset(value for value, _label in planner.PRIORITY_OPTIONS)
_OPERATION_IDS = frozenset(value for value, _label in planner.OPERATION_OPTIONS)


class PlanStoreError(RuntimeError):
    pass


class PlanValidationError(PlanStoreError):
    pass


class PlanNotFoundError(PlanStoreError):
    pass


class PlanConflictError(PlanStoreError):
    pass


class PlanLimitError(PlanStoreError):
    pass


def _now_text(value: object | None = None) -> str:
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    text = str(value).strip()
    if not text or len(text) > 40:
        raise PlanValidationError("timestamp_invalid")
    return text


def _identity(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 80:
        raise PlanValidationError(f"{field}_invalid")
    return text


def _bounded_text(value: object, field: str, *, maximum: int, required: bool = True) -> str:
    if not isinstance(value, str):
        raise PlanValidationError(f"{field}_invalid")
    text = value.strip()
    if (required and not text) or len(text) > maximum:
        raise PlanValidationError(f"{field}_invalid")
    return text


def _summary_text(value: object) -> str:
    text = _bounded_text(
        value,
        "summary_text",
        maximum=MAX_SUMMARY_SOURCE_LENGTH,
    )
    visible_source = text.replace("<b>", "").replace("</b>", "")
    if "<" in visible_source or ">" in visible_source:
        raise PlanValidationError("summary_text_invalid")
    if len(html.unescape(visible_source)) > MAX_TELEGRAM_VISIBLE_LENGTH:
        raise PlanValidationError("summary_text_invalid")
    return text


def _validated_list(
    value: object,
    field: str,
    allowed: frozenset[str],
    *,
    maximum: int,
) -> list[str]:
    if not isinstance(value, list) or not value or len(value) > maximum:
        raise PlanValidationError(f"{field}_invalid")
    if not all(isinstance(item, str) for item in value):
        raise PlanValidationError(f"{field}_invalid")
    if len(value) != len(set(value)) or any(item not in allowed for item in value):
        raise PlanValidationError(f"{field}_invalid")
    return list(value)


def _validated_text_list(value: object, field: str, *, maximum: int, item_maximum: int) -> list[str]:
    if not isinstance(value, list) or not value or len(value) > maximum:
        raise PlanValidationError(f"{field}_invalid")
    items = [_bounded_text(item, field, maximum=item_maximum) for item in value]
    if len(items) != len(set(items)):
        raise PlanValidationError(f"{field}_invalid")
    return items


def _plan_timestamp(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise PlanValidationError(f"{field}_invalid")
    try:
        stamp = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise PlanValidationError(f"{field}_invalid") from exc
    if stamp < 0:
        raise PlanValidationError(f"{field}_invalid")
    return stamp


def normalize_plan(plan: object, *, plan_key: str | None = None) -> dict[str, object]:
    if not isinstance(plan, dict) or set(plan) != _PLAN_FIELDS:
        raise PlanValidationError("plan_fields_invalid")
    if plan.get("plan_schema_version") != planner.PLAN_SCHEMA_VERSION:
        raise PlanValidationError("plan_schema_invalid")
    key = str(plan_key if plan_key is not None else plan.get("plan_id") or "").strip()
    if key and not _PLAN_KEY_RE.fullmatch(key):
        raise PlanValidationError("plan_key_invalid")
    goal = str(plan.get("goal") or "")
    platform = str(plan.get("platform_ratio") or "")
    source = str(plan.get("source_duration") or "")
    target = str(plan.get("target_duration") or "")
    if goal not in _GOAL_IDS or platform not in _PLATFORM_IDS or source not in _SOURCE_IDS or target not in _TARGET_IDS:
        raise PlanValidationError("plan_choice_invalid")
    steps_raw = plan.get("ordered_steps")
    if not isinstance(steps_raw, list) or not steps_raw or len(steps_raw) > 32:
        raise PlanValidationError("ordered_steps_invalid")
    steps = [
        _bounded_text(step, "ordered_step", maximum=800)
        for step in steps_raw
    ]
    created_at = _plan_timestamp(plan.get("created_at"), "created_at")
    updated_at = _plan_timestamp(plan.get("updated_at"), "updated_at")
    if updated_at < created_at:
        raise PlanValidationError("plan_timestamp_order_invalid")
    return {
        "plan_schema_version": planner.PLAN_SCHEMA_VERSION,
        "plan_id": key,
        "title": _bounded_text(plan.get("title"), "title", maximum=120),
        "goal": goal,
        "editing_brief": _bounded_text(plan.get("editing_brief"), "editing_brief", maximum=planner.MAX_BRIEF_LENGTH, required=False),
        "platform_ratio": platform,
        "source_duration": source,
        "target_duration": target,
        "available_assets": _validated_list(plan.get("available_assets"), "available_assets", _ASSET_IDS, maximum=6),
        "priorities": _validated_list(plan.get("priorities"), "priorities", _PRIORITY_IDS, maximum=6),
        "selected_operations": _validated_list(plan.get("selected_operations"), "selected_operations", _OPERATION_IDS, maximum=16),
        "ordered_steps": steps,
        "rights_notes": _validated_text_list(plan.get("rights_notes"), "rights_notes", maximum=8, item_maximum=500),
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _canonical_payload(plan: dict[str, object]) -> str:
    return json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fingerprint(plan: dict[str, object], summary_text: str) -> str:
    semantic_plan = {
        key: value
        for key, value in plan.items()
        if key not in {"created_at", "updated_at"}
    }
    semantic_json = _canonical_payload(semantic_plan)
    return hashlib.sha256(f"{semantic_json}\0{summary_text}".encode("utf-8")).hexdigest()


def _new_plan_key() -> str:
    return uuid.uuid4().hex[:12]


def ensure_schema(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS local_video_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_key TEXT NOT NULL UNIQUE,
                owner_id TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                source_session_id TEXT NOT NULL,
                title TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                summary_text TEXT NOT NULL,
                content_fingerprint TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT NOT NULL DEFAULT '',
                UNIQUE(owner_id, chat_id, source_session_id)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_local_video_plans_owner_updated
            ON local_video_plans(owner_id, chat_id, deleted_at, updated_at DESC)
            """
        )


def _decode_row(row: sqlite3.Row | tuple | None) -> dict[str, object] | None:
    if row is None:
        return None
    values = dict(row) if isinstance(row, sqlite3.Row) else None
    if values is None:
        raise PlanValidationError("row_factory_required")
    try:
        payload = json.loads(str(values["plan_json"]))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PlanValidationError("stored_plan_invalid") from exc
    plan = normalize_plan(payload, plan_key=str(values["plan_key"]))
    return {
        "plan_key": str(values["plan_key"]),
        "owner_id": str(values["owner_id"]),
        "chat_id": str(values["chat_id"]),
        "source_session_id": str(values["source_session_id"]),
        "title": str(values["title"]),
        "plan": plan,
        "summary_text": str(values["summary_text"]),
        "content_fingerprint": str(values["content_fingerprint"]),
        "version": int(values["version"]),
        "created_at": str(values["created_at"]),
        "updated_at": str(values["updated_at"]),
    }


def _select_active_by_source(
    conn: sqlite3.Connection,
    owner_id: str,
    chat_id: str,
    source_session_id: str,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM local_video_plans
        WHERE owner_id=? AND chat_id=? AND source_session_id=? AND deleted_at=''
        """,
        (owner_id, chat_id, source_session_id),
    ).fetchone()


def _select_by_source(
    conn: sqlite3.Connection,
    owner_id: str,
    chat_id: str,
    source_session_id: str,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM local_video_plans
        WHERE owner_id=? AND chat_id=? AND source_session_id=?
        """,
        (owner_id, chat_id, source_session_id),
    ).fetchone()


def save_plan_from_session(
    conn: sqlite3.Connection,
    *,
    owner_id: object,
    chat_id: object,
    source_session_id: object,
    plan: object,
    summary_text: object,
    now: object | None = None,
) -> dict[str, object]:
    owner = _identity(owner_id, "owner_id")
    chat = _identity(chat_id, "chat_id")
    source_session = _identity(source_session_id, "source_session_id")
    summary = _summary_text(summary_text)
    stamp = _now_text(now)
    ensure_schema(conn)
    existing = _select_active_by_source(conn, owner, chat, source_session)
    source_row = existing if existing is not None else _select_by_source(conn, owner, chat, source_session)
    if existing is None:
        active_count = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM local_video_plans
                WHERE owner_id=? AND chat_id=? AND deleted_at=''
                """,
                (owner, chat),
            ).fetchone()[0]
        )
        if active_count >= MAX_ACTIVE_PLANS:
            raise PlanLimitError("active_plan_limit_reached")
    plan_key = str(source_row["plan_key"]) if source_row is not None else _new_plan_key()
    normalized = normalize_plan(plan, plan_key=plan_key)
    payload_json = _canonical_payload(normalized)
    fingerprint = _fingerprint(normalized, summary)

    if existing is not None and str(existing["content_fingerprint"]) == fingerprint:
        return copy.deepcopy(_decode_row(existing))
    with conn:
        if source_row is None:
            conn.execute(
                """
                INSERT INTO local_video_plans
                (plan_key,owner_id,chat_id,source_session_id,title,plan_json,summary_text,
                 content_fingerprint,version,created_at,updated_at,deleted_at)
                VALUES (?,?,?,?,?,?,?,?,1,?,?, '')
                """,
                (
                    plan_key,
                    owner,
                    chat,
                    source_session,
                    str(normalized["title"]),
                    payload_json,
                    summary,
                    fingerprint,
                    stamp,
                    stamp,
                ),
            )
        elif existing is None:
            conn.execute(
                """
                UPDATE local_video_plans
                SET title=?,plan_json=?,summary_text=?,content_fingerprint=?,
                    version=version+1,updated_at=?,deleted_at=''
                WHERE owner_id=? AND chat_id=? AND source_session_id=?
                """,
                (
                    str(normalized["title"]),
                    payload_json,
                    summary,
                    fingerprint,
                    stamp,
                    owner,
                    chat,
                    source_session,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE local_video_plans
                SET title=?,plan_json=?,summary_text=?,content_fingerprint=?,
                    version=version+1,updated_at=?
                WHERE owner_id=? AND chat_id=? AND source_session_id=? AND deleted_at=''
                """,
                (
                    str(normalized["title"]),
                    payload_json,
                    summary,
                    fingerprint,
                    stamp,
                    owner,
                    chat,
                    source_session,
                ),
            )
    row = _select_active_by_source(conn, owner, chat, source_session)
    result = _decode_row(row)
    if result is None:
        raise PlanStoreError("save_failed")
    return result


def get_plan(
    conn: sqlite3.Connection,
    *,
    owner_id: object,
    chat_id: object,
    plan_key: object,
) -> dict[str, object] | None:
    owner = _identity(owner_id, "owner_id")
    chat = _identity(chat_id, "chat_id")
    key = str(plan_key or "").strip()
    if not _PLAN_KEY_RE.fullmatch(key):
        return None
    row = conn.execute(
        """
        SELECT * FROM local_video_plans
        WHERE owner_id=? AND chat_id=? AND plan_key=? AND deleted_at=''
        """,
        (owner, chat, key),
    ).fetchone()
    return copy.deepcopy(_decode_row(row))


def list_plans(
    conn: sqlite3.Connection,
    *,
    owner_id: object,
    chat_id: object,
    limit: int = MAX_ACTIVE_PLANS,
    offset: int = 0,
) -> list[dict[str, object]]:
    owner = _identity(owner_id, "owner_id")
    chat = _identity(chat_id, "chat_id")
    bounded_limit = max(1, min(MAX_ACTIVE_PLANS, int(limit)))
    bounded_offset = max(0, int(offset))
    rows = conn.execute(
        """
        SELECT * FROM local_video_plans
        WHERE owner_id=? AND chat_id=? AND deleted_at=''
        ORDER BY updated_at DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        (owner, chat, bounded_limit, bounded_offset),
    ).fetchall()
    results: list[dict[str, object]] = []
    for row in rows:
        try:
            decoded = _decode_row(row)
        except PlanValidationError:
            continue
        if decoded is not None:
            results.append(copy.deepcopy(decoded))
    return results


def update_plan(
    conn: sqlite3.Connection,
    *,
    owner_id: object,
    chat_id: object,
    plan_key: object,
    expected_version: int,
    plan: object,
    summary_text: object,
    now: object | None = None,
) -> dict[str, object]:
    owner = _identity(owner_id, "owner_id")
    chat = _identity(chat_id, "chat_id")
    key = str(plan_key or "").strip()
    if not _PLAN_KEY_RE.fullmatch(key):
        raise PlanNotFoundError("plan_not_found")
    summary = _summary_text(summary_text)
    normalized = normalize_plan(plan, plan_key=key)
    payload_json = _canonical_payload(normalized)
    fingerprint = _fingerprint(normalized, summary)
    stamp = _now_text(now)
    row = conn.execute(
        """
        SELECT * FROM local_video_plans
        WHERE owner_id=? AND chat_id=? AND plan_key=? AND deleted_at=''
        """,
        (owner, chat, key),
    ).fetchone()
    if row is None:
        raise PlanNotFoundError("plan_not_found")
    if int(row["version"]) != int(expected_version):
        raise PlanConflictError("plan_version_conflict")
    if str(row["content_fingerprint"]) == fingerprint:
        result = _decode_row(row)
        if result is None:
            raise PlanStoreError("update_failed")
        return result
    with conn:
        cursor = conn.execute(
            """
            UPDATE local_video_plans
            SET title=?,plan_json=?,summary_text=?,content_fingerprint=?,
                version=version+1,updated_at=?
            WHERE owner_id=? AND chat_id=? AND plan_key=? AND version=? AND deleted_at=''
            """,
            (
                str(normalized["title"]),
                payload_json,
                summary,
                fingerprint,
                stamp,
                owner,
                chat,
                key,
                int(expected_version),
            ),
        )
    if cursor.rowcount != 1:
        raise PlanConflictError("plan_version_conflict")
    result = get_plan(conn, owner_id=owner, chat_id=chat, plan_key=key)
    if result is None:
        raise PlanStoreError("update_failed")
    return result


def soft_delete_plan(
    conn: sqlite3.Connection,
    *,
    owner_id: object,
    chat_id: object,
    plan_key: object,
    now: object | None = None,
) -> bool:
    owner = _identity(owner_id, "owner_id")
    chat = _identity(chat_id, "chat_id")
    key = str(plan_key or "").strip()
    if not _PLAN_KEY_RE.fullmatch(key):
        return False
    stamp = _now_text(now)
    with conn:
        cursor = conn.execute(
            """
            UPDATE local_video_plans
            SET deleted_at=?,updated_at=?,version=version+1
            WHERE owner_id=? AND chat_id=? AND plan_key=? AND deleted_at=''
            """,
            (stamp, stamp, owner, chat, key),
        )
    return cursor.rowcount == 1
