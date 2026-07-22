"""Small, idempotent admin broadcast outbox.

This module owns notification composition, eligibility snapshots, schedules, and delivery state.
It may read settled top-up state, but never mutates billing, products, providers, or balances.
"""

from __future__ import annotations

import asyncio
import calendar
import hashlib
import inspect
import json
import re
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from zoneinfo import ZoneInfo


MAX_MESSAGE_LENGTH = 4000
MAX_CAPTION_LENGTH = 1024
MAX_CTA_COUNT = 4
DEFAULT_BATCH_SIZE = 20
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_DELAY = 15.0
DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"
DEFAULT_PROMO_LIMIT_24H = 1
DEFAULT_PROMO_LIMIT_7D = 3
CHAT_ID_RE = re.compile(r"^-?\d{1,30}$")

CTA_REGISTRY: dict[str, dict[str, str]] = {
    "topup": {"label": "💳 Nạp ngay", "callback_data": "menu|main_topup"},
    "video": {"label": "🎬 Tạo video ngay", "callback_data": "menu|main_video"},
    "image": {"label": "🖼️ Tạo ảnh ngay", "callback_data": "menu|main_image"},
    "support": {"label": "🆘 Hỗ trợ ngay", "callback_data": "menu|support"},
    # Curated public callbacks only. Admins never enter callback_data themselves.
    "f_ai": {"label": "🤖 Mở Bot AI", "callback_data": "menu|main_ai"},
    "f_account": {"label": "👤 Tài khoản", "callback_data": "menu|main_profile"},
    "f_memory": {"label": "📝 Ghi chú & nhắc hẹn", "callback_data": "menu|main_memory"},
    "f_docs": {"label": "🧰 Công cụ tài liệu", "callback_data": "menu|main_docs"},
}

CORE_CTA_KEYS = ("topup", "video", "image", "support")
SPECIAL_FEATURE_CTA_KEYS = ("f_ai", "f_account", "f_memory", "f_docs")

MEMBER_TIER_ORDER = ("newbie", "silver", "gold", "platinum", "diamond", "vip")
MEMBER_TIER_REGISTRY: dict[str, dict[str, Any]] = {
    "newbie": {"label": "🌱 Chưa hạng / chưa đạt Bạc", "short_label": "Chưa hạng"},
    "silver": {"label": "🥈 Bạc", "short_label": "Bạc"},
    "gold": {"label": "🥇 Vàng", "short_label": "Vàng"},
    "platinum": {"label": "💠 Bạch kim", "short_label": "Bạch kim"},
    "diamond": {"label": "💎 Kim cương", "short_label": "Kim cương"},
    "vip": {"label": "👑 VIP", "short_label": "VIP"},
}
MEMBER_TIER_THRESHOLDS = {
    "newbie": 0,
    "silver": 100_000,
    "gold": 1_000_000,
    "platinum": 10_000_000,
    "diamond": 50_000_000,
    "vip": 100_000_000,
}

TEMPLATES: dict[str, dict[str, Any]] = {
    "first_topup": {
        "label": "Mẫu 1 · Nạp Xu lần đầu",
        "message": (
            "🎁 ƯU ĐÃI NẠP XU LẦN ĐẦU\n\n"
            "Nạp Xu lần đầu được tặng thêm 30% Xu.\n"
            "Không cần mã giảm giá."
        ),
        "ctas": [],
    },
    "second_topup": {
        "label": "Mẫu 2 · Nạp Xu lần hai",
        "message": (
            "🎁 ƯU ĐÃI NẠP XU LẦN HAI\n\n"
            "Nạp Xu lần thứ hai được tặng thêm 20% Xu.\n"
            "Không cần mã giảm giá."
        ),
        "ctas": [],
    },
    "video": {
        "label": "Mẫu 3 · Tạo video AI",
        "message": (
            "🎬 TẠO VIDEO AI CÙNG TOAN AAS\n\n"
            "Chọn loại video và bắt đầu tạo video ngay trên bot."
        ),
        "ctas": [],
    },
    "image": {
        "label": "Mẫu 4 · Tạo ảnh AI",
        "message": (
            "🖼️ TẠO ẢNH AI CÙNG TOAN AAS\n\n"
            "Tạo ảnh sản phẩm, người mẫu và quảng cáo ngay trên bot."
        ),
        "ctas": [],
    },
    "support": {
        "label": "Mẫu 5 · Hỗ trợ khách hàng",
        "message": (
            "🆘 HỖ TRỢ TOAN AAS\n\n"
            "Anh/chị cần hỗ trợ sử dụng tính năng hoặc kiểm tra đơn hàng? "
            "Hãy mở Menu Hỗ trợ để được hướng dẫn."
        ),
        "ctas": [],
    },
    "saved_custom": {
        "label": "Mẫu 6 · Nội dung tùy chỉnh đã lưu",
        "message": "",
        "ctas": [],
        "dynamic": True,
    },
}

AUTO_NOTICE_CONTENT: dict[str, dict[str, Any]] = {
    "first_topup_30": {
        "title": "Ưu đãi nạp Xu lần đầu",
        "message": (
            "🎁 ƯU ĐÃI NẠP XU LẦN ĐẦU\n\n"
            "Nạp Xu lần đầu được tặng thêm 30% Xu.\n"
            "Không cần mã giảm giá."
        ),
        "ctas": ["topup"],
        "source": "first_start",
        "priority": 90,
    },
    "second_topup_20": {
        "title": "Ưu đãi nạp Xu lần hai",
        "message": (
            "🎁 ƯU ĐÃI NẠP XU LẦN HAI\n\n"
            "Lần nạp Xu tiếp theo, anh/chị được tặng thêm 20% Xu.\n"
            "Không cần mã giảm giá."
        ),
        "ctas": ["topup"],
        "source": "after_first_topup",
        "priority": 100,
    },
}

CAMPAIGN_PRIORITY = {
    "after_first_topup": 100,
    "first_start": 90,
    "manual": 70,
    "monthly_schedule": 60,
    "weekly_schedule": 50,
    "daily_schedule": 40,
    "one_time_schedule": 65,
}


class FrequencyCapWarning(ValueError):
    """Manual send requires an explicit second confirmation."""

    def __init__(self, affected: int, total: int):
        self.affected = max(0, int(affected))
        self.total = max(0, int(total))
        super().__init__(
            f"Có {self.affected}/{self.total} khách đang trong giới hạn chống spam. "
            "Admin cần xác nhận gửi vượt giới hạn."
        )


def now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _connect(db: str | Path | sqlite3.Connection) -> tuple[sqlite3.Connection, bool]:
    if isinstance(db, sqlite3.Connection):
        conn = db
        if conn.row_factory is None:
            conn.row_factory = sqlite3.Row
        return conn, False
    conn = sqlite3.connect(str(db), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    return conn, True


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _ensure_column(conn: sqlite3.Connection, table: str, name: str, definition: str) -> None:
    if name not in _table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create only the notification tables; safe to call during every startup."""
    had_transaction = bool(conn.in_transaction)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS broadcast_lite_drafts (
            draft_id TEXT PRIMARY KEY,
            admin_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            message_text TEXT NOT NULL DEFAULT '',
            media_file_id TEXT NOT NULL DEFAULT '',
            media_type TEXT NOT NULL DEFAULT '',
            keyboard_json TEXT NOT NULL DEFAULT '[]',
            audience_kind TEXT NOT NULL DEFAULT '',
            audience_value TEXT NOT NULL DEFAULT '',
            state TEXT NOT NULL DEFAULT 'draft',
            campaign_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS broadcast_lite_campaigns (
            campaign_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '',
            message_text TEXT NOT NULL DEFAULT '',
            media_file_id TEXT NOT NULL DEFAULT '',
            media_type TEXT NOT NULL DEFAULT '',
            keyboard_json TEXT NOT NULL DEFAULT '[]',
            audience_kind TEXT NOT NULL,
            audience_value TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'queued',
            created_by TEXT NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE,
            total_targets INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS broadcast_lite_deliveries (
            delivery_id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL,
            telegram_chat_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT '',
            telegram_message_id TEXT NOT NULL DEFAULT '',
            sent_at TEXT,
            next_retry_at REAL NOT NULL DEFAULT 0,
            last_attempt_at TEXT,
            worker_heartbeat_at TEXT,
            UNIQUE(campaign_id, telegram_chat_id),
            FOREIGN KEY(campaign_id) REFERENCES broadcast_lite_campaigns(campaign_id)
        );
        CREATE INDEX IF NOT EXISTS idx_broadcast_lite_delivery_queue
            ON broadcast_lite_deliveries(status, next_retry_at, campaign_id);
        CREATE TABLE IF NOT EXISTS broadcast_lite_blocked_users (
            user_id TEXT PRIMARY KEY,
            blocked_at TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS broadcast_lite_worker_heartbeats (
            worker_name TEXT PRIMARY KEY,
            heartbeat_at TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS broadcast_lite_auto_notices (
            auto_notice_id INTEGER PRIMARY KEY AUTOINCREMENT,
            auto_notice_type TEXT NOT NULL,
            user_id TEXT NOT NULL,
            eligibility_snapshot TEXT NOT NULL DEFAULT '{}',
            queued_at TEXT,
            sent_at TEXT,
            telegram_message_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            idempotency_key TEXT NOT NULL UNIQUE,
            campaign_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_broadcast_lite_auto_notice_user
            ON broadcast_lite_auto_notices(user_id, auto_notice_type, status);
        CREATE TABLE IF NOT EXISTS broadcast_lite_schedules (
            schedule_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            message_text TEXT NOT NULL,
            media_file_id TEXT NOT NULL DEFAULT '',
            media_type TEXT NOT NULL DEFAULT '',
            cta_json TEXT NOT NULL DEFAULT '[]',
            audience_kind TEXT NOT NULL,
            audience_filter TEXT NOT NULL DEFAULT '',
            cadence TEXT NOT NULL,
            timezone TEXT NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
            send_time TEXT NOT NULL DEFAULT '09:00',
            day_of_week INTEGER,
            day_of_month INTEGER,
            starts_at TEXT,
            expires_at TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            priority INTEGER NOT NULL DEFAULT 0,
            created_by TEXT NOT NULL,
            last_enqueued_at TEXT,
            next_run_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_broadcast_lite_schedule_due
            ON broadcast_lite_schedules(is_active, next_run_at, priority);
        CREATE TABLE IF NOT EXISTS broadcast_lite_frequency_log (
            frequency_log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            campaign_id INTEGER,
            delivery_id INTEGER,
            schedule_id INTEGER,
            source TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 0,
            content_hash TEXT NOT NULL,
            cta_hash TEXT NOT NULL,
            promotion_id TEXT NOT NULL DEFAULT '',
            idempotency_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'reserved',
            reserved_at TEXT NOT NULL,
            sent_at TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_broadcast_lite_frequency_user
            ON broadcast_lite_frequency_log(user_id, reserved_at, status);
        CREATE TABLE IF NOT EXISTS broadcast_lite_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by TEXT NOT NULL DEFAULT 'system'
        );
        """
    )
    for table, columns in {
        "broadcast_lite_drafts": {
            "revision": "INTEGER NOT NULL DEFAULT 1",
            "draft_kind": "TEXT NOT NULL DEFAULT 'manual'",
            "schedule_cadence": "TEXT NOT NULL DEFAULT ''",
            "schedule_config_json": "TEXT NOT NULL DEFAULT '{}'",
            "schedule_id": "INTEGER",
            "template_key": "TEXT NOT NULL DEFAULT ''",
            "cap_acknowledged": "INTEGER NOT NULL DEFAULT 0",
        },
        "broadcast_lite_campaigns": {
            "source": "TEXT NOT NULL DEFAULT 'manual'",
            "schedule_id": "INTEGER",
            "trigger_type": "TEXT NOT NULL DEFAULT 'manual'",
            "content_hash": "TEXT NOT NULL DEFAULT ''",
            "cta_hash": "TEXT NOT NULL DEFAULT ''",
            "promotion_id": "TEXT NOT NULL DEFAULT ''",
            "priority": "INTEGER NOT NULL DEFAULT 0",
            "frequency_override": "INTEGER NOT NULL DEFAULT 0",
        },
        "broadcast_lite_deliveries": {
            "schedule_id": "INTEGER",
            "trigger_type": "TEXT NOT NULL DEFAULT 'manual'",
            "user_id": "TEXT NOT NULL DEFAULT ''",
            "content_hash": "TEXT NOT NULL DEFAULT ''",
            "frequency_log_id": "INTEGER",
        },
    }.items():
        for name, definition in columns.items():
            _ensure_column(conn, table, name, definition)
    stamp = now_text()
    conn.execute(
        "INSERT OR IGNORE INTO broadcast_lite_settings(setting_key,setting_value,updated_at,updated_by) VALUES (?,?,?,?)",
        ("promo_limits", json.dumps({"max_24h": DEFAULT_PROMO_LIMIT_24H, "max_7d": DEFAULT_PROMO_LIMIT_7D, "weekly_then_daily": False}, separators=(",", ":")), stamp, "system"),
    )
    if not had_transaction and conn.in_transaction:
        conn.commit()


def initialize_database(db: str | Path) -> None:
    conn, owned = _connect(db)
    try:
        ensure_schema(conn)
        conn.commit()
    finally:
        if owned:
            conn.close()


def is_authorized_admin(user_id: Any, admin_ids: Iterable[Any]) -> bool:
    candidate = str(user_id).strip()
    return bool(candidate) and candidate in {str(value).strip() for value in admin_ids}


def _json_ctas(ctas: Iterable[str]) -> str:
    return json.dumps(normalize_ctas(ctas), ensure_ascii=False, separators=(",", ":"))


def normalize_ctas(ctas: Iterable[str] | None) -> list[str]:
    result: list[str] = []
    for key in ctas or []:
        key = str(key or "").strip()
        if key in CTA_REGISTRY and key not in result:
            result.append(key)
        if len(result) == MAX_CTA_COUNT:
            break
    return result


def normalize_member_tier(value: Any) -> str:
    raw = str(value or "").strip().lower().replace(" ", "_")
    aliases = {
        "none": "newbie", "no_tier": "newbie", "new": "newbie", "tan_thu": "newbie",
        "bạc": "silver", "bac": "silver", "vàng": "gold", "vang": "gold",
        "bạch_kim": "platinum", "bach_kim": "platinum", "kim_cương": "diamond", "kim_cuong": "diamond",
    }
    raw = aliases.get(raw, raw)
    return raw if raw in MEMBER_TIER_ORDER else ""


def normalize_member_tiers(values: Any) -> list[str]:
    if isinstance(values, str):
        try:
            decoded = json.loads(values)
            values = decoded if isinstance(decoded, list) else re.split(r"[\s,;]+", values)
        except (TypeError, ValueError, json.JSONDecodeError):
            values = re.split(r"[\s,;]+", values)
    result: list[str] = []
    for value in values or []:
        tier = normalize_member_tier(value)
        if tier and tier not in result:
            result.append(tier)
    return [tier for tier in MEMBER_TIER_ORDER if tier in result]


def member_tier_display(tier: str) -> str:
    return str(MEMBER_TIER_REGISTRY.get(normalize_member_tier(tier), {}).get("label") or tier)


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _draft_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    value = _row_to_dict(row)
    if value is None:
        return None
    try:
        value["ctas"] = normalize_ctas(json.loads(value.get("keyboard_json") or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        value["ctas"] = []
    value["tiers"] = normalize_member_tiers(value.get("audience_value")) if value.get("audience_kind") == "tiers" else []
    try:
        schedule_config = json.loads(value.get("schedule_config_json") or "{}")
        value["schedule_config"] = schedule_config if isinstance(schedule_config, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        value["schedule_config"] = {}
    return value


def _new_draft(conn: sqlite3.Connection, admin_id: Any, **values: Any) -> str:
    draft_id = uuid.uuid4().hex
    stamp = now_text()
    conn.execute(
        """INSERT INTO broadcast_lite_drafts
        (draft_id, admin_id, title, message_text, media_file_id, media_type,
         keyboard_json, audience_kind, audience_value, state, revision, draft_kind,
         schedule_cadence, schedule_config_json, template_key, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            draft_id,
            str(admin_id),
            str(values.get("title") or ""),
            str(values.get("message_text") or ""),
            str(values.get("media_file_id") or ""),
            str(values.get("media_type") or ""),
            _json_ctas(values.get("ctas") or []),
            str(values.get("audience_kind") or ""),
            str(values.get("audience_value") or ""),
            str(values.get("state") or "draft"),
            max(1, int(values.get("revision") or 1)),
            str(values.get("draft_kind") or "manual"),
            str(values.get("schedule_cadence") or ""),
            json.dumps(values.get("schedule_config") or {}, ensure_ascii=False, separators=(",", ":")),
            str(values.get("template_key") or ""),
            stamp,
            stamp,
        ),
    )
    return draft_id


def create_empty_draft(
    db: str | Path,
    admin_id: Any,
    *,
    state: str = "awaiting_message",
    draft_kind: str = "manual",
    schedule_cadence: str = "",
) -> dict[str, Any]:
    conn, owned = _connect(db)
    try:
        ensure_schema(conn)
        draft_id = _new_draft(
            conn,
            admin_id,
            state=state,
            draft_kind=str(draft_kind or "manual"),
            schedule_cadence=str(schedule_cadence or ""),
        )
        conn.commit()
        return get_draft(db, draft_id, admin_id) or {}
    finally:
        if owned:
            conn.close()


def create_template_draft(db: str | Path, admin_id: Any, template_key: str) -> dict[str, Any]:
    template_key = str(template_key)
    template = TEMPLATES.get(template_key)
    if not template:
        raise ValueError("Mẫu thông báo không tồn tại")
    conn, owned = _connect(db)
    try:
        ensure_schema(conn)
        message = str(template.get("message") or "")
        if template_key == "saved_custom":
            row = conn.execute(
                "SELECT message_text FROM broadcast_lite_campaigns WHERE created_by=? AND source='manual' AND TRIM(message_text)<>'' ORDER BY campaign_id DESC LIMIT 1",
                (str(admin_id),),
            ).fetchone()
            if not row:
                raise ValueError("Chưa có nội dung tùy chỉnh đã lưu")
            message = str(row["message_text"] or "")
        draft_id = _new_draft(
            conn,
            admin_id,
            title=template["label"],
            message_text=message,
            ctas=template["ctas"],
            state="draft",
            template_key=template_key,
        )
        conn.commit()
        return get_draft(db, draft_id, admin_id) or {}
    finally:
        if owned:
            conn.close()


def apply_template_to_draft(
    db: str | Path,
    draft_id: str,
    admin_id: Any,
    template_key: str,
) -> dict[str, Any]:
    """Apply content only; CTA selection stays independent from promotion copy."""
    template_key = str(template_key or "").strip()
    template = TEMPLATES.get(template_key)
    if not template:
        raise ValueError("Mẫu thông báo không tồn tại")
    conn, owned = _connect(db)
    try:
        ensure_schema(conn)
        message = str(template.get("message") or "")
        if template_key == "saved_custom":
            row = conn.execute(
                "SELECT message_text FROM broadcast_lite_campaigns WHERE created_by=? AND source='manual' AND TRIM(message_text)<>'' ORDER BY campaign_id DESC LIMIT 1",
                (str(admin_id),),
            ).fetchone()
            if not row:
                raise ValueError("Chưa có nội dung tùy chỉnh đã lưu")
            message = str(row["message_text"] or "")
    finally:
        if owned:
            conn.close()
    return _update_draft(
        db,
        draft_id,
        admin_id,
        title=str(template.get("label") or ""),
        message_text=message,
        template_key=template_key,
        state="template_review",
    )


def get_draft(db: str | Path, draft_id: str, admin_id: Any | None = None) -> dict[str, Any] | None:
    conn, owned = _connect(db)
    try:
        query = "SELECT * FROM broadcast_lite_drafts WHERE draft_id=?"
        params: list[Any] = [str(draft_id)]
        if admin_id is not None:
            query += " AND admin_id=?"
            params.append(str(admin_id))
        return _draft_row(conn.execute(query, params).fetchone())
    finally:
        if owned:
            conn.close()


def get_latest_draft(db: str | Path, admin_id: Any, *, states: Iterable[str] | None = None) -> dict[str, Any] | None:
    conn, owned = _connect(db)
    try:
        query = "SELECT * FROM broadcast_lite_drafts WHERE admin_id=?"
        params: list[Any] = [str(admin_id)]
        wanted = [str(state) for state in (states or []) if str(state)]
        if wanted:
            query += " AND state IN (" + ",".join("?" for _ in wanted) + ")"
            params.extend(wanted)
        query += " ORDER BY updated_at DESC, created_at DESC, rowid DESC LIMIT 1"
        return _draft_row(conn.execute(query, params).fetchone())
    finally:
        if owned:
            conn.close()


def clear_pending_drafts(db: str | Path, admin_id: Any) -> int:
    pending_states = (
        "awaiting_message",
        "awaiting_content",
        "awaiting_photo",
        "awaiting_caption",
        "awaiting_audience_user",
        "awaiting_audience_test_list",
        "awaiting_schedule_time",
    )
    conn, owned = _connect(db)
    try:
        ensure_schema(conn)
        placeholders = ",".join("?" for _ in pending_states)
        cursor = conn.execute(
            f"UPDATE broadcast_lite_drafts SET state='draft',updated_at=? "
            f"WHERE admin_id=? AND state IN ({placeholders})",
            (now_text(), str(admin_id), *pending_states),
        )
        conn.commit()
        return max(0, int(cursor.rowcount or 0))
    finally:
        if owned:
            conn.close()


def _update_draft(db: str | Path, draft_id: str, admin_id: Any, **values: Any) -> dict[str, Any]:
    if not values:
        return get_draft(db, draft_id, admin_id) or {}
    conn, owned = _connect(db)
    try:
        ensure_schema(conn)
        assignments: list[str] = []
        params: list[Any] = []
        for key, value in values.items():
            if key == "ctas":
                key, value = "keyboard_json", _json_ctas(value)
            if key == "schedule_config":
                key, value = "schedule_config_json", json.dumps(value or {}, ensure_ascii=False, separators=(",", ":"))
            if key not in {
                "title", "message_text", "media_file_id", "media_type", "keyboard_json",
                "audience_kind", "audience_value", "state", "campaign_id",
                "draft_kind", "schedule_cadence", "schedule_config_json", "template_key",
                "schedule_id", "cap_acknowledged",
            }:
                raise ValueError("Trường draft không hợp lệ")
            assignments.append(f"{key}=?")
            params.append(value)
        assignments.append("revision=revision+1")
        assignments.append("updated_at=?")
        params.extend([now_text(), str(draft_id), str(admin_id)])
        conn.execute(
            f"UPDATE broadcast_lite_drafts SET {', '.join(assignments)} WHERE draft_id=? AND admin_id=?",
            params,
        )
        conn.commit()
        result = get_draft(db, draft_id, admin_id)
        if result is None:
            raise ValueError("Không tìm thấy bản nháp")
        return result
    finally:
        if owned:
            conn.close()


def set_draft_message(db: str | Path, draft_id: str, admin_id: Any, message_text: str) -> dict[str, Any]:
    text = str(message_text or "").strip()
    if not text:
        raise ValueError("Nội dung thông báo không được để trống")
    draft = get_draft(db, draft_id, admin_id)
    limit = MAX_CAPTION_LENGTH if (draft or {}).get("media_file_id") else MAX_MESSAGE_LENGTH
    if len(text) > limit:
        raise ValueError(f"Nội dung tối đa {limit} ký tự")
    return _update_draft(db, draft_id, admin_id, message_text=text, state="draft")


def set_draft_media(
    db: str | Path,
    draft_id: str,
    admin_id: Any,
    file_id: str,
    *,
    media_type: str = "photo",
    caption: str = "",
) -> dict[str, Any]:
    file_id = str(file_id or "").strip()
    if not file_id:
        raise ValueError("Thiếu file ảnh")
    caption = str(caption or "").strip()
    if len(caption) > MAX_CAPTION_LENGTH:
        raise ValueError(f"Caption tối đa {MAX_CAPTION_LENGTH} ký tự")
    return _update_draft(
        db,
        draft_id,
        admin_id,
        media_file_id=file_id,
        media_type=str(media_type or "photo"),
        message_text=caption,
        state="draft" if caption else "awaiting_caption",
    )


def set_draft_ctas(db: str | Path, draft_id: str, admin_id: Any, ctas: Iterable[str]) -> dict[str, Any]:
    return _update_draft(db, draft_id, admin_id, ctas=normalize_ctas(ctas), state="draft")


def set_draft_state(db: str | Path, draft_id: str, admin_id: Any, state: str) -> dict[str, Any]:
    return _update_draft(db, draft_id, admin_id, state=str(state or "draft"))


def toggle_draft_cta(db: str | Path, draft_id: str, admin_id: Any, cta_key: str) -> dict[str, Any]:
    draft = get_draft(db, draft_id, admin_id)
    if not draft:
        raise ValueError("Không tìm thấy bản nháp")
    key = str(cta_key or "").strip()
    ctas = list(draft.get("ctas") or [])
    if key not in CTA_REGISTRY:
        raise ValueError("Nút hành động không hợp lệ")
    if key in ctas:
        ctas.remove(key)
    elif len(ctas) < MAX_CTA_COUNT:
        ctas.append(key)
    else:
        raise ValueError("Tối đa 4 nút hành động")
    return set_draft_ctas(db, draft_id, admin_id, ctas)


def set_draft_audience(db: str | Path, draft_id: str, admin_id: Any, kind: str, value: str = "") -> dict[str, Any]:
    kind = str(kind or "").strip()
    if kind not in {"all", "tiers", "user", "test_list"}:
        raise ValueError("Nhóm người nhận không hợp lệ")
    value = str(value or "").strip()
    if kind == "tiers":
        tiers = normalize_member_tiers(value)
        if not tiers:
            raise ValueError("Cần chọn ít nhất một hạng thành viên")
        value = json.dumps(tiers, ensure_ascii=False, separators=(",", ":"))
    if kind == "user" and not valid_chat_id(value):
        raise ValueError("User ID không hợp lệ")
    if kind == "test_list" and not parse_chat_ids(value):
        raise ValueError("Danh sách user test không có chat ID hợp lệ")
    return _update_draft(db, draft_id, admin_id, audience_kind=kind, audience_value=value, state="draft")


def toggle_draft_tier(db: str | Path, draft_id: str, admin_id: Any, tier: str) -> dict[str, Any]:
    draft = get_draft(db, draft_id, admin_id)
    if not draft:
        raise ValueError("Không tìm thấy bản nháp")
    key = str(tier or "").strip().lower()
    selected = normalize_member_tiers(draft.get("audience_value") if draft.get("audience_kind") == "tiers" else [])
    if key == "all":
        selected = [] if len(selected) == len(MEMBER_TIER_ORDER) else list(MEMBER_TIER_ORDER)
    else:
        key = normalize_member_tier(key)
        if not key:
            raise ValueError("Hạng thành viên không hợp lệ")
        if key in selected:
            selected.remove(key)
        else:
            selected.append(key)
    if not selected:
        return _update_draft(db, draft_id, admin_id, audience_kind="", audience_value="", state="draft")
    return _update_draft(
        db,
        draft_id,
        admin_id,
        audience_kind="tiers",
        audience_value=json.dumps(normalize_member_tiers(selected), ensure_ascii=False, separators=(",", ":")),
        state="draft",
    )


def valid_chat_id(value: Any) -> bool:
    return bool(CHAT_ID_RE.fullmatch(str(value or "").strip()))


def parse_chat_ids(value: str) -> list[str]:
    result: list[str] = []
    for item in re.split(r"[\s,;]+", str(value or "").strip()):
        item = item.strip()
        if valid_chat_id(item) and item not in result:
            result.append(item)
    return result


def _blocked_ids(conn: sqlite3.Connection) -> set[str]:
    return {str(row["user_id"]) for row in conn.execute("SELECT user_id FROM broadcast_lite_blocked_users")}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def _utc_now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).replace(microsecond=0)


def _parse_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def notification_content_hash(message_text: str, media_file_id: str = "") -> str:
    payload = f"{str(message_text or '').strip()}\nmedia:{str(media_file_id or '').strip()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def notification_cta_hash(ctas: Iterable[str] | None) -> str:
    payload = json.dumps(normalize_ctas(ctas), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _promo_limits_conn(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute(
        "SELECT setting_value FROM broadcast_lite_settings WHERE setting_key='promo_limits'"
    ).fetchone()
    try:
        value = json.loads(row["setting_value"] if row else "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        value = {}
    return {
        "max_24h": max(1, int(value.get("max_24h") or DEFAULT_PROMO_LIMIT_24H)),
        "max_7d": max(1, int(value.get("max_7d") or DEFAULT_PROMO_LIMIT_7D)),
        "weekly_then_daily": bool(value.get("weekly_then_daily", False)),
    }


def get_promo_limits(db: str | Path | sqlite3.Connection) -> dict[str, Any]:
    conn, owned = _connect(db)
    try:
        if owned:
            ensure_schema(conn)
        return _promo_limits_conn(conn)
    finally:
        if owned:
            conn.close()


def set_promo_limits(
    db: str | Path,
    *,
    max_24h: int = DEFAULT_PROMO_LIMIT_24H,
    max_7d: int = DEFAULT_PROMO_LIMIT_7D,
    weekly_then_daily: bool = False,
    updated_by: Any = "system",
) -> dict[str, Any]:
    value = {
        "max_24h": max(1, min(int(max_24h), 10)),
        "max_7d": max(1, min(int(max_7d), 30)),
        "weekly_then_daily": bool(weekly_then_daily),
    }
    conn, owned = _connect(db)
    try:
        ensure_schema(conn)
        conn.execute(
            "INSERT INTO broadcast_lite_settings(setting_key,setting_value,updated_at,updated_by) VALUES ('promo_limits',?,?,?) "
            "ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value,updated_at=excluded.updated_at,updated_by=excluded.updated_by",
            (json.dumps(value, separators=(",", ":")), now_text(), str(updated_by)),
        )
        conn.commit()
        return value
    finally:
        if owned:
            conn.close()


def _frequency_decision_conn(
    conn: sqlite3.Connection,
    user_id: Any,
    *,
    source: str,
    content_hash: str,
    cta_hash: str,
    promotion_id: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _utc_now(now)
    limits = _promo_limits_conn(conn)
    since_7d = (current - timedelta(days=7)).isoformat()
    rows = [dict(row) for row in conn.execute(
        "SELECT f.*,d.next_retry_at AS delivery_next_retry_at FROM broadcast_lite_frequency_log f "
        "LEFT JOIN broadcast_lite_deliveries d ON d.delivery_id=f.delivery_id "
        "WHERE f.user_id=? AND f.status IN ('reserved','sent') AND f.reserved_at>=? ORDER BY f.reserved_at DESC",
        (str(user_id), since_7d),
    ).fetchall()]
    for row in rows:
        same_content = bool(content_hash) and row.get("content_hash") == content_hash
        if same_content:
            return {"allowed": False, "reason": "duplicate_7d", "retry_at": None}

    source = str(source or "manual")
    local_zone = ZoneInfo(DEFAULT_TIMEZONE)
    local_day = current.astimezone(local_zone).date()
    weekly_today: list[datetime] = []
    for row in rows:
        reserved = _parse_datetime(row.get("reserved_at"))
        if reserved and str(row.get("source") or "") == "weekly_schedule" and reserved.astimezone(local_zone).date() == local_day:
            effective = reserved
            try:
                retry_epoch = float(row.get("delivery_next_retry_at") or 0)
            except (TypeError, ValueError):
                retry_epoch = 0
            if retry_epoch > 0:
                effective = max(effective, datetime.fromtimestamp(retry_epoch, tz=timezone.utc))
            weekly_today.append(effective)
    max_24h = int(limits["max_24h"])
    if source == "daily_schedule" and weekly_today:
        latest_weekly = max(weekly_today)
        if not limits.get("weekly_then_daily"):
            tomorrow = datetime.combine(local_day + timedelta(days=1), datetime.min.time(), tzinfo=local_zone)
            retry_at = max(tomorrow.astimezone(timezone.utc), latest_weekly + timedelta(minutes=1))
            return {"allowed": False, "reason": "daily_after_weekly", "retry_at": retry_at}
        earliest = latest_weekly + timedelta(hours=6)
        if current < earliest:
            return {"allowed": False, "reason": "weekly_then_daily_6h", "retry_at": earliest}
        max_24h = max(max_24h, 2)

    in_24h: list[datetime] = []
    in_7d: list[datetime] = []
    for row in rows:
        reserved = _parse_datetime(row.get("reserved_at"))
        if not reserved:
            continue
        in_7d.append(reserved)
        if reserved >= current - timedelta(hours=24):
            in_24h.append(reserved)
    if len(in_24h) >= max_24h:
        return {
            "allowed": False,
            "reason": "cap_24h",
            "retry_at": min(in_24h) + timedelta(hours=24),
        }
    if len(in_7d) >= int(limits["max_7d"]):
        return {
            "allowed": False,
            "reason": "cap_7d",
            "retry_at": min(in_7d) + timedelta(days=7),
        }
    return {"allowed": True, "reason": "ok", "retry_at": current}


def frequency_cap_summary(
    db: str | Path,
    user_ids: Iterable[Any],
    *,
    source: str,
    message_text: str,
    media_file_id: str = "",
    ctas: Iterable[str] | None = None,
    promotion_id: str = "",
    now: datetime | None = None,
) -> dict[str, int]:
    conn, owned = _connect(db)
    try:
        if owned:
            ensure_schema(conn)
        content_hash = notification_content_hash(message_text, media_file_id)
        cta_hash = notification_cta_hash(ctas)
        total = affected = duplicate = capped = 0
        for user_id in dict.fromkeys(str(value) for value in user_ids if valid_chat_id(value)):
            total += 1
            decision = _frequency_decision_conn(
                conn,
                user_id,
                source=source,
                content_hash=content_hash,
                cta_hash=cta_hash,
                promotion_id=promotion_id,
                now=now,
            )
            if not decision["allowed"]:
                affected += 1
                if decision["reason"] == "duplicate_7d":
                    duplicate += 1
                else:
                    capped += 1
        return {"total": total, "affected": affected, "duplicate": duplicate, "capped": capped}
    finally:
        if owned:
            conn.close()


def _reserve_frequency_conn(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    campaign_id: int,
    delivery_id: int,
    schedule_id: int | None,
    source: str,
    priority: int,
    content_hash: str,
    cta_hash: str,
    promotion_id: str,
    idempotency_key: str,
    reserved_at: datetime | None = None,
) -> int:
    stamp = _utc_now(reserved_at).isoformat()
    conn.execute(
        """INSERT OR IGNORE INTO broadcast_lite_frequency_log
        (user_id,campaign_id,delivery_id,schedule_id,source,priority,content_hash,cta_hash,promotion_id,
         idempotency_key,status,reserved_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?, 'reserved',?,?)""",
        (
            str(user_id), int(campaign_id), int(delivery_id), schedule_id, str(source), int(priority),
            str(content_hash), str(cta_hash), str(promotion_id or ""), str(idempotency_key), stamp, stamp,
        ),
    )
    row = conn.execute(
        "SELECT frequency_log_id FROM broadcast_lite_frequency_log WHERE idempotency_key=?",
        (str(idempotency_key),),
    ).fetchone()
    return int(row["frequency_log_id"]) if row else 0


def _member_user_candidates(conn: sqlite3.Connection, selected_tiers: Iterable[str]) -> tuple[list[str], int]:
    selected = set(normalize_member_tiers(selected_tiers))
    if not selected:
        return [], 0
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(users)")}
    paid_expr = "COALESCE(u.total_paid_vnd,0)" if "total_paid_vnd" in columns else "0"
    vip_expr = "COALESCE(u.is_vip,0)" if "is_vip" in columns else "0"
    user_override_expr = "COALESCE(u.vip_tier_override,'')" if "vip_tier_override" in columns else "''"
    override_join = ""
    table_override_expr = "''"
    if _table_exists(conn, "member_tier_overrides"):
        override_join = "LEFT JOIN member_tier_overrides mto ON mto.user_id=CAST(u.user_id AS TEXT)"
        table_override_expr = "COALESCE(mto.tier,'')"
    rows = conn.execute(
        f"SELECT u.user_id AS user_id,{paid_expr} AS total_paid_vnd,{vip_expr} AS is_vip,{user_override_expr} AS user_override,{table_override_expr} AS table_override FROM users u {override_join} ORDER BY u.user_id"
    ).fetchall()
    candidates: list[str] = []
    invalid = 0
    for row in rows:
        chat_id = str(row["user_id"] or "").strip()
        if not valid_chat_id(chat_id):
            invalid += 1
            continue
        override = normalize_member_tier(row["table_override"]) or normalize_member_tier(row["user_override"])
        if override:
            tier = override
        elif int(row["is_vip"] or 0) == 1:
            tier = "vip"
        else:
            paid = int(row["total_paid_vnd"] or 0)
            tier = "newbie"
            for candidate in reversed(MEMBER_TIER_ORDER[1:]):
                if paid >= MEMBER_TIER_THRESHOLDS[candidate]:
                    tier = candidate
                    break
        if tier in selected and chat_id not in candidates:
            candidates.append(chat_id)
    return candidates, invalid


def _raw_audience_candidates(conn: sqlite3.Connection, kind: str, value: str) -> tuple[list[str], int]:
    invalid = 0
    if kind == "all":
        candidates = [str(row["user_id"]) for row in conn.execute("SELECT user_id FROM users ORDER BY user_id")]
    elif kind == "tiers":
        return _member_user_candidates(conn, normalize_member_tiers(value))
    elif kind == "user":
        candidates = [str(value).strip()]
    elif kind == "test_list":
        raw = re.split(r"[\s,;]+", str(value or "").strip())
        candidates = [item.strip() for item in raw if item.strip()]
    else:
        candidates = []
    invalid = sum(1 for item in candidates if not valid_chat_id(item))
    return candidates, invalid


def _audience_ids(conn: sqlite3.Connection, kind: str, value: str) -> tuple[list[str], int]:
    blocked = _blocked_ids(conn)
    candidates, invalid = _raw_audience_candidates(conn, kind, value)
    if kind != "tiers":
        invalid = 0
    result: list[str] = []
    for item in candidates:
        if not valid_chat_id(item):
            invalid += 1
        elif item not in blocked and item not in result:
            result.append(item)
    return result, invalid


def preview_audience(db: str | Path, kind: str, value: str = "") -> dict[str, int]:
    conn, owned = _connect(db)
    try:
        ensure_schema(conn)
        raw, invalid = _raw_audience_candidates(conn, str(kind), str(value or ""))
        blocked_ids = _blocked_ids(conn)
        valid = {item for item in raw if valid_chat_id(item)}
        blocked = len(valid & blocked_ids)
        eligible = len(valid - blocked_ids)
        return {"total": eligible + blocked, "eligible": eligible, "invalid": invalid, "blocked": blocked}
    finally:
        if owned:
            conn.close()


def _campaign_keyboard(ctas: Iterable[str]) -> list[list[dict[str, str]]]:
    buttons = [
        {"text": CTA_REGISTRY[key]["label"], "callback_data": CTA_REGISTRY[key]["callback_data"]}
        for key in normalize_ctas(ctas)
    ]
    return [buttons[index:index + 2] for index in range(0, len(buttons), 2)]


def render_preview_text(draft: Mapping[str, Any]) -> str:
    message = str(draft.get("message_text") or "").strip() or "(chưa có nội dung)"
    ctas = normalize_ctas(draft.get("ctas") or [])
    buttons = ", ".join(CTA_REGISTRY[key]["label"] for key in ctas) or "(không có)"
    if draft.get("audience_kind") == "tiers":
        audience = ", ".join(member_tier_display(tier) for tier in normalize_member_tiers(draft.get("audience_value"))) or "chưa chọn"
    else:
        audience = str(draft.get("audience_kind") or "chưa chọn")
    return f"👀 Xem trước\n\n{message}\n\n🔘 Nút: {buttons}\n👥 Người nhận: {audience}"


def preview_draft(db: str | Path, draft_id: str, admin_id: Any) -> dict[str, Any]:
    draft = get_draft(db, draft_id, admin_id)
    if not draft:
        raise ValueError("Không tìm thấy bản nháp")
    if not str(draft.get("message_text") or "").strip() and not draft.get("media_file_id"):
        raise ValueError("Cần nhập nội dung trước khi xem trước")
    if not draft.get("audience_kind"):
        raise ValueError("Cần chọn người nhận trước khi xem trước")
    return {**draft, "preview_text": render_preview_text(draft), "audience": preview_audience(db, draft["audience_kind"], draft["audience_value"])}


def _campaign_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    value = _row_to_dict(row)
    if value is None:
        return None
    try:
        value["ctas"] = normalize_ctas(json.loads(value.get("keyboard_json") or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        value["ctas"] = []
    return value


def _insert_campaign_conn(
    conn: sqlite3.Connection,
    *,
    title: str,
    message_text: str,
    media_file_id: str,
    media_type: str,
    ctas: Iterable[str],
    audience_kind: str,
    audience_value: str,
    created_by: Any,
    idempotency_key: str,
    targets: Iterable[str],
    source: str,
    trigger_type: str,
    schedule_id: int | None = None,
    promotion_id: str = "",
    priority: int = 0,
    frequency_override: bool = False,
    next_retry_by_user: Mapping[str, float] | None = None,
    reserve_frequency: bool = True,
    reserved_at: datetime | None = None,
) -> dict[str, Any]:
    existing = conn.execute(
        "SELECT * FROM broadcast_lite_campaigns WHERE idempotency_key=?",
        (str(idempotency_key),),
    ).fetchone()
    if existing:
        return _campaign_dict(existing) or {}
    normalized_ctas = normalize_ctas(ctas)
    unique_targets = list(dict.fromkeys(str(value) for value in targets if valid_chat_id(value)))
    stamp = _utc_now(reserved_at).isoformat()
    content_hash = notification_content_hash(message_text, media_file_id)
    cta_hash = notification_cta_hash(normalized_ctas)
    conn.execute(
        """INSERT INTO broadcast_lite_campaigns
        (title,message_text,media_file_id,media_type,keyboard_json,audience_kind,audience_value,
         status,created_by,idempotency_key,total_targets,created_at,updated_at,source,schedule_id,
         trigger_type,content_hash,cta_hash,promotion_id,priority,frequency_override)
         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            str(title or "Thông báo khách hàng"), str(message_text or ""), str(media_file_id or ""),
            str(media_type or ""), _json_ctas(normalized_ctas), str(audience_kind), str(audience_value or ""),
            "queued", str(created_by), str(idempotency_key), len(unique_targets), stamp, stamp,
            str(source or "manual"), schedule_id, str(trigger_type or source or "manual"), content_hash,
            cta_hash, str(promotion_id or ""), int(priority), int(bool(frequency_override)),
        ),
    )
    campaign_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    retry_map = {str(key): float(value) for key, value in (next_retry_by_user or {}).items()}
    for user_id in unique_targets:
        conn.execute(
            """INSERT INTO broadcast_lite_deliveries
            (campaign_id,telegram_chat_id,status,next_retry_at,schedule_id,trigger_type,user_id,content_hash)
            VALUES (?,?,'pending',?,?,?,?,?)""",
            (
                campaign_id, user_id, retry_map.get(user_id, 0.0), schedule_id,
                str(trigger_type or source or "manual"), user_id, content_hash,
            ),
        )
        delivery_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        if reserve_frequency:
            frequency_log_id = _reserve_frequency_conn(
                conn,
                user_id=user_id,
                campaign_id=campaign_id,
                delivery_id=delivery_id,
                schedule_id=schedule_id,
                source=str(source or "manual"),
                priority=int(priority),
                content_hash=content_hash,
                cta_hash=cta_hash,
                promotion_id=str(promotion_id or ""),
                idempotency_key=f"{idempotency_key}:{user_id}",
                reserved_at=reserved_at,
            )
            conn.execute(
                "UPDATE broadcast_lite_deliveries SET frequency_log_id=? WHERE delivery_id=?",
                (frequency_log_id or None, delivery_id),
            )
    if not unique_targets:
        conn.execute(
            "UPDATE broadcast_lite_campaigns SET status='completed',completed_at=?,updated_at=? WHERE campaign_id=?",
            (stamp, stamp, campaign_id),
        )
    return _campaign_dict(
        conn.execute("SELECT * FROM broadcast_lite_campaigns WHERE campaign_id=?", (campaign_id,)).fetchone()
    ) or {}


def confirm_draft(
    db: str | Path,
    draft_id: str,
    admin_id: Any,
    *,
    override_frequency_cap: bool = False,
) -> dict[str, Any]:
    conn, owned = _connect(db)
    try:
        ensure_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        draft = _draft_row(conn.execute(
            "SELECT * FROM broadcast_lite_drafts WHERE draft_id=? AND admin_id=?", (str(draft_id), str(admin_id))
        ).fetchone())
        if not draft:
            raise ValueError("Không tìm thấy bản nháp")
        if draft.get("campaign_id"):
            row = conn.execute("SELECT * FROM broadcast_lite_campaigns WHERE campaign_id=?", (draft["campaign_id"],)).fetchone()
            conn.commit()
            return _campaign_dict(row) or {}
        if not str(draft.get("message_text") or "").strip() and not draft.get("media_file_id"):
            raise ValueError("Cần nhập nội dung trước khi gửi")
        if draft.get("audience_kind") not in {"all", "tiers", "user", "test_list"}:
            raise ValueError("Cần chọn người nhận trước khi gửi")
        targets, _invalid = _audience_ids(conn, draft["audience_kind"], draft.get("audience_value") or "")
        cap = frequency_cap_summary(
            conn,
            targets,
            source="manual",
            message_text=str(draft.get("message_text") or ""),
            media_file_id=str(draft.get("media_file_id") or ""),
            ctas=draft.get("ctas") or [],
        )
        if int(cap.get("affected", 0)) and not override_frequency_cap and not int(draft.get("cap_acknowledged") or 0):
            raise FrequencyCapWarning(int(cap["affected"]), len(targets))
        stamp = now_text()
        key = f"broadcast-lite:{admin_id}:{draft_id}"
        campaign = _insert_campaign_conn(
            conn,
            title=str(draft.get("title") or "Thông báo khách hàng"),
            message_text=str(draft.get("message_text") or ""),
            media_file_id=str(draft.get("media_file_id") or ""),
            media_type=str(draft.get("media_type") or ""),
            ctas=draft.get("ctas") or [],
            audience_kind=str(draft["audience_kind"]),
            audience_value=str(draft.get("audience_value") or ""),
            created_by=admin_id,
            idempotency_key=key,
            targets=targets,
            source="manual",
            trigger_type="manual",
            priority=CAMPAIGN_PRIORITY["manual"],
            frequency_override=bool(override_frequency_cap),
        )
        campaign_id = int(campaign["campaign_id"])
        conn.execute(
            "UPDATE broadcast_lite_drafts SET campaign_id=?, state='confirmed', cap_acknowledged=?, updated_at=? WHERE draft_id=? AND admin_id=?",
            (campaign_id, int(bool(override_frequency_cap)), stamp, str(draft_id), str(admin_id)),
        )
        conn.commit()
        return _campaign_dict(conn.execute("SELECT * FROM broadcast_lite_campaigns WHERE campaign_id=?", (campaign_id,)).fetchone()) or {}
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        if owned:
            conn.close()


def settled_topup_count_conn(conn: sqlite3.Connection, user_id: Any) -> int:
    """Read-only compatibility query for successful top-ups; never mutates billing."""
    candidate = str(user_id or "").strip()
    if not candidate:
        return 0
    count = 0
    if _table_exists(conn, "payos_orders"):
        columns = _table_columns(conn, "payos_orders")
        if {"user_id", "status"}.issubset(columns):
            order_type_filter = ""
            if "order_type" in columns:
                order_type_filter = (
                    " AND LOWER(COALESCE(order_type,'topup')) NOT IN "
                    "('package_purchase','plan_purchase','storage_addon')"
                )
            row = conn.execute(
                "SELECT COUNT(*) FROM payos_orders WHERE CAST(user_id AS TEXT)=? "
                "AND UPPER(COALESCE(status,'')) IN ('PAID','SETTLED','SUCCESS','SUCCEEDED')"
                + order_type_filter,
                (candidate,),
            ).fetchone()
            count = int(row[0] or 0) if row else 0
    if count:
        return count
    if _table_exists(conn, "users"):
        columns = _table_columns(conn, "users")
        if {"user_id", "has_deposited"}.issubset(columns):
            row = conn.execute(
                "SELECT COALESCE(has_deposited,0) FROM users WHERE CAST(user_id AS TEXT)=?",
                (candidate,),
            ).fetchone()
            if row and int(row[0] or 0) > 0:
                return 1
    return 0


def settled_topup_count(db: str | Path, user_id: Any) -> int:
    conn, owned = _connect(db)
    try:
        ensure_schema(conn)
        return settled_topup_count_conn(conn, user_id)
    finally:
        if owned:
            conn.close()


def _supersede_pending_first_start_conn(conn: sqlite3.Connection, user_id: str, *, now: datetime | None = None) -> bool:
    """Cancel an obsolete first-topup promo only while it is still safely pending."""
    row = conn.execute(
        "SELECT campaign_id FROM broadcast_lite_auto_notices "
        "WHERE user_id=? AND auto_notice_type='first_topup_30' AND status IN ('queued','pending')",
        (str(user_id),),
    ).fetchone()
    campaign_id = int(row["campaign_id"] or 0) if row else 0
    if not campaign_id:
        return False
    pending = conn.execute(
        "SELECT delivery_id,frequency_log_id FROM broadcast_lite_deliveries "
        "WHERE campaign_id=? AND user_id=? AND status='pending'",
        (campaign_id, str(user_id)),
    ).fetchall()
    if not pending:
        return False
    stamp = _utc_now(now).isoformat()
    delivery_ids = [int(item["delivery_id"]) for item in pending]
    placeholders = ",".join("?" for _ in delivery_ids)
    conn.execute(
        f"UPDATE broadcast_lite_deliveries SET status='suppressed',last_error='superseded after first settled top-up',next_retry_at=0 "
        f"WHERE delivery_id IN ({placeholders}) AND status='pending'",
        delivery_ids,
    )
    frequency_ids = [int(item["frequency_log_id"] or 0) for item in pending if int(item["frequency_log_id"] or 0)]
    if frequency_ids:
        frequency_placeholders = ",".join("?" for _ in frequency_ids)
        conn.execute(
            f"UPDATE broadcast_lite_frequency_log SET status='suppressed',updated_at=? "
            f"WHERE frequency_log_id IN ({frequency_placeholders}) AND status='reserved'",
            (stamp, *frequency_ids),
        )
    conn.execute(
        "UPDATE broadcast_lite_auto_notices SET status='superseded',updated_at=? "
        "WHERE campaign_id=? AND user_id=? AND status IN ('queued','pending')",
        (stamp, campaign_id, str(user_id)),
    )
    conn.execute(
        "UPDATE broadcast_lite_campaigns SET status='completed',completed_at=?,updated_at=? "
        "WHERE campaign_id=? AND NOT EXISTS (SELECT 1 FROM broadcast_lite_deliveries "
        "WHERE campaign_id=? AND status IN ('pending','sending'))",
        (stamp, stamp, campaign_id, campaign_id),
    )
    return True


def _enqueue_auto_notice(
    db: str | Path,
    user_id: Any,
    notice_type: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    user_id = str(user_id or "").strip()
    notice_type = str(notice_type or "").strip()
    spec = AUTO_NOTICE_CONTENT.get(notice_type)
    if not valid_chat_id(user_id):
        return {"queued": False, "reason": "invalid_chat_id", "notice_type": notice_type, "user_id": user_id}
    if not spec:
        raise ValueError("Loại thông báo tự động không hợp lệ")
    conn, owned = _connect(db)
    try:
        ensure_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        idempotency_key = f"auto:{notice_type}:{user_id}"
        existing = conn.execute(
            "SELECT * FROM broadcast_lite_auto_notices WHERE idempotency_key=?",
            (idempotency_key,),
        ).fetchone()
        if existing:
            conn.commit()
            return {
                "queued": False,
                "reason": "duplicate",
                "notice_type": notice_type,
                "user_id": user_id,
                "campaign_id": int(existing["campaign_id"] or 0),
                "status": str(existing["status"] or ""),
            }
        topup_count = settled_topup_count_conn(conn, user_id)
        eligible = (notice_type == "first_topup_30" and topup_count == 0) or (
            notice_type == "second_topup_20" and topup_count == 1
        )
        snapshot = {
            "settled_topup_count": topup_count,
            "eligible": bool(eligible),
            "checked_at": _utc_now(now).isoformat(),
        }
        if not eligible:
            conn.rollback()
            return {
                "queued": False,
                "reason": "not_eligible",
                "notice_type": notice_type,
                "user_id": user_id,
                "eligibility_snapshot": snapshot,
            }
        if user_id in _blocked_ids(conn):
            conn.rollback()
            return {"queued": False, "reason": "blocked", "notice_type": notice_type, "user_id": user_id}
        if notice_type == "second_topup_20":
            _supersede_pending_first_start_conn(conn, user_id, now=now)
        message = str(spec["message"])
        ctas = normalize_ctas(spec.get("ctas") or [])
        source = str(spec["source"])
        content_hash = notification_content_hash(message)
        cta_hash = notification_cta_hash(ctas)
        decision = _frequency_decision_conn(
            conn,
            user_id,
            source=source,
            content_hash=content_hash,
            cta_hash=cta_hash,
            promotion_id=notice_type,
            now=now,
        )
        if not decision["allowed"] and decision.get("retry_at") is None:
            stamp = _utc_now(now).isoformat()
            conn.execute(
                """INSERT INTO broadcast_lite_auto_notices
                (auto_notice_type,user_id,eligibility_snapshot,status,idempotency_key,created_at,updated_at)
                VALUES (?,?,?,'suppressed',?,?,?)""",
                (notice_type, user_id, json.dumps(snapshot, separators=(",", ":")), idempotency_key, stamp, stamp),
            )
            conn.commit()
            return {"queued": False, "reason": str(decision["reason"]), "notice_type": notice_type, "user_id": user_id}
        retry_at = decision.get("retry_at")
        retry_epoch = retry_at.timestamp() if isinstance(retry_at, datetime) and retry_at > _utc_now(now) else 0.0
        campaign = _insert_campaign_conn(
            conn,
            title=str(spec["title"]),
            message_text=message,
            media_file_id="",
            media_type="",
            ctas=ctas,
            audience_kind="user",
            audience_value=user_id,
            created_by="system",
            idempotency_key=idempotency_key,
            targets=[user_id],
            source=source,
            trigger_type=notice_type,
            promotion_id=notice_type,
            priority=int(spec["priority"]),
            next_retry_by_user={user_id: retry_epoch} if retry_epoch else None,
            reserved_at=now,
        )
        stamp = _utc_now(now).isoformat()
        conn.execute(
            """INSERT INTO broadcast_lite_auto_notices
            (auto_notice_type,user_id,eligibility_snapshot,queued_at,status,idempotency_key,campaign_id,created_at,updated_at)
            VALUES (?,?,?,?,'queued',?,?,?,?)""",
            (
                notice_type, user_id, json.dumps(snapshot, separators=(",", ":")), stamp,
                idempotency_key, int(campaign["campaign_id"]), stamp, stamp,
            ),
        )
        conn.commit()
        return {
            "queued": True,
            "reason": "queued" if not retry_epoch else "deferred",
            "notice_type": notice_type,
            "user_id": user_id,
            "campaign_id": int(campaign["campaign_id"]),
            "next_retry_at": retry_epoch,
        }
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        if owned:
            conn.close()


def enqueue_first_start_notice(db: str | Path, user_id: Any, *, now: datetime | None = None) -> dict[str, Any]:
    return _enqueue_auto_notice(db, user_id, "first_topup_30", now=now)


def enqueue_after_first_topup_notice(db: str | Path, user_id: Any, *, now: datetime | None = None) -> dict[str, Any]:
    return _enqueue_auto_notice(db, user_id, "second_topup_20", now=now)


def normalize_cadence(value: Any) -> str:
    cadence = str(value or "").strip().lower().replace("-", "_")
    aliases = {"once": "one_time", "one_time_scheduled": "one_time", "month": "monthly", "week": "weekly", "day": "daily"}
    cadence = aliases.get(cadence, cadence)
    if cadence not in {"monthly", "weekly", "daily", "one_time"}:
        raise ValueError("Chu kỳ lịch thông báo không hợp lệ")
    return cadence


def _schedule_zone(value: Any) -> ZoneInfo:
    try:
        return ZoneInfo(str(value or DEFAULT_TIMEZONE))
    except Exception:
        return ZoneInfo(DEFAULT_TIMEZONE)


def _parse_send_time(value: Any) -> tuple[int, int]:
    raw = str(value or "09:00").strip()
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", raw)
    if not match:
        raise ValueError("Giờ gửi phải có dạng HH:MM")
    hour, minute = int(match.group(1)), int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Giờ gửi không hợp lệ")
    return hour, minute


def _coerce_schedule_datetime(value: Any, zone: ZoneInfo) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        local = value if isinstance(value, datetime) else datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Thời điểm phải có dạng YYYY-MM-DD HH:MM") from error
    if local.tzinfo is None:
        local = local.replace(tzinfo=zone)
    return local.astimezone(timezone.utc)


def next_schedule_run(
    *,
    cadence: str,
    timezone_name: str = DEFAULT_TIMEZONE,
    send_time: str = "09:00",
    day_of_week: int | None = None,
    day_of_month: int | None = None,
    starts_at: Any = None,
    after: datetime | None = None,
) -> datetime | None:
    cadence = normalize_cadence(cadence)
    zone = _schedule_zone(timezone_name)
    current_utc = _utc_now(after)
    current = current_utc.astimezone(zone)
    starts = _coerce_schedule_datetime(starts_at, zone)
    if cadence == "one_time":
        return starts if starts and starts >= current_utc else None
    hour, minute = _parse_send_time(send_time)
    if cadence == "daily":
        candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= current:
            candidate += timedelta(days=1)
    elif cadence == "weekly":
        target = max(1, min(int(day_of_week or 1), 7)) - 1
        delta = (target - current.weekday()) % 7
        candidate = (current + timedelta(days=delta)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= current:
            candidate += timedelta(days=7)
    else:
        target_day = max(1, min(int(day_of_month or 1), 31))
        year, month = current.year, current.month
        candidate_day = min(target_day, calendar.monthrange(year, month)[1])
        candidate = current.replace(day=candidate_day, hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= current:
            month = 1 if month == 12 else month + 1
            year = year + 1 if current.month == 12 else year
            candidate_day = min(target_day, calendar.monthrange(year, month)[1])
            candidate = candidate.replace(year=year, month=month, day=candidate_day)
    candidate_utc = candidate.astimezone(timezone.utc)
    if starts and candidate_utc < starts:
        return next_schedule_run(
            cadence=cadence,
            timezone_name=timezone_name,
            send_time=send_time,
            day_of_week=day_of_week,
            day_of_month=day_of_month,
            starts_at=None,
            after=starts - timedelta(seconds=1),
        )
    return candidate_utc


def _schedule_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    value = _row_to_dict(row)
    if value is None:
        return None
    try:
        value["ctas"] = normalize_ctas(json.loads(value.get("cta_json") or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        value["ctas"] = []
    return value


def create_schedule(
    db: str | Path,
    *,
    name: str,
    message_text: str,
    audience_kind: str,
    audience_filter: str = "",
    cadence: str,
    created_by: Any,
    media_file_id: str = "",
    media_type: str = "",
    ctas: Iterable[str] | None = None,
    timezone_name: str = DEFAULT_TIMEZONE,
    send_time: str = "09:00",
    day_of_week: int | None = None,
    day_of_month: int | None = None,
    starts_at: Any = None,
    expires_at: Any = None,
    is_active: bool = True,
    priority: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    cadence = normalize_cadence(cadence)
    message_text = str(message_text or "").strip()
    if not message_text and not str(media_file_id or "").strip():
        raise ValueError("Lịch thông báo cần có nội dung")
    if len(message_text) > MAX_MESSAGE_LENGTH:
        raise ValueError(f"Nội dung tối đa {MAX_MESSAGE_LENGTH} ký tự")
    audience_kind = str(audience_kind or "").strip()
    if audience_kind not in {"all", "tiers", "user", "test_list"}:
        raise ValueError("Nhóm người nhận không hợp lệ")
    zone = _schedule_zone(timezone_name)
    timezone_name = str(getattr(zone, "key", DEFAULT_TIMEZONE))
    starts = _coerce_schedule_datetime(starts_at, zone)
    expires = _coerce_schedule_datetime(expires_at, zone)
    if expires and starts and expires <= starts:
        raise ValueError("Thời điểm hết hạn phải sau thời điểm bắt đầu")
    next_run = next_schedule_run(
        cadence=cadence,
        timezone_name=timezone_name,
        send_time=send_time,
        day_of_week=day_of_week,
        day_of_month=day_of_month,
        starts_at=starts,
        after=now,
    )
    if bool(is_active) and next_run is None:
        raise ValueError("Không xác định được lần chạy tiếp theo")
    if expires and next_run and next_run > expires:
        is_active = False
        next_run = None
    source = f"{cadence}_schedule"
    if cadence == "one_time":
        source = "one_time_schedule"
    resolved_priority = int(priority if priority is not None else CAMPAIGN_PRIORITY[source])
    conn, owned = _connect(db)
    try:
        ensure_schema(conn)
        stamp = _utc_now(now).isoformat()
        conn.execute(
            """INSERT INTO broadcast_lite_schedules
            (name,message_text,media_file_id,media_type,cta_json,audience_kind,audience_filter,cadence,
             timezone,send_time,day_of_week,day_of_month,starts_at,expires_at,is_active,priority,created_by,
             next_run_at,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                str(name or f"Lịch {cadence}"), message_text, str(media_file_id or ""), str(media_type or ""),
                _json_ctas(ctas or []), audience_kind, str(audience_filter or ""), cadence, timezone_name,
                f"{_parse_send_time(send_time)[0]:02d}:{_parse_send_time(send_time)[1]:02d}",
                day_of_week, day_of_month, starts.isoformat() if starts else None,
                expires.isoformat() if expires else None, int(bool(is_active)), resolved_priority, str(created_by),
                next_run.isoformat() if next_run else None, stamp, stamp,
            ),
        )
        schedule_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.commit()
        return _schedule_dict(conn.execute("SELECT * FROM broadcast_lite_schedules WHERE schedule_id=?", (schedule_id,)).fetchone()) or {}
    finally:
        if owned:
            conn.close()


def list_schedules(db: str | Path, created_by: Any | None = None, limit: int = 20) -> list[dict[str, Any]]:
    conn, owned = _connect(db)
    try:
        ensure_schema(conn)
        query = "SELECT * FROM broadcast_lite_schedules"
        params: list[Any] = []
        if created_by is not None:
            query += " WHERE created_by=?"
            params.append(str(created_by))
        query += " ORDER BY schedule_id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 100)))
        return [_schedule_dict(row) or {} for row in conn.execute(query, params).fetchall()]
    finally:
        if owned:
            conn.close()


def set_schedule_active(db: str | Path, schedule_id: int, active: bool, *, now: datetime | None = None) -> dict[str, Any]:
    conn, owned = _connect(db)
    try:
        ensure_schema(conn)
        row = conn.execute("SELECT * FROM broadcast_lite_schedules WHERE schedule_id=?", (int(schedule_id),)).fetchone()
        schedule = _schedule_dict(row)
        if not schedule:
            raise ValueError("Không tìm thấy lịch thông báo")
        next_run = None
        if active:
            next_run = next_schedule_run(
                cadence=schedule["cadence"], timezone_name=schedule["timezone"], send_time=schedule["send_time"],
                day_of_week=schedule.get("day_of_week"), day_of_month=schedule.get("day_of_month"),
                starts_at=schedule.get("starts_at"), after=now,
            )
        conn.execute(
            "UPDATE broadcast_lite_schedules SET is_active=?,next_run_at=?,updated_at=? WHERE schedule_id=?",
            (int(bool(active and next_run)), next_run.isoformat() if next_run else None, _utc_now(now).isoformat(), int(schedule_id)),
        )
        conn.commit()
        return _schedule_dict(conn.execute("SELECT * FROM broadcast_lite_schedules WHERE schedule_id=?", (int(schedule_id),)).fetchone()) or {}
    finally:
        if owned:
            conn.close()


def set_draft_schedule_config(
    db: str | Path,
    draft_id: str,
    admin_id: Any,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    draft = get_draft(db, draft_id, admin_id)
    if not draft or str(draft.get("draft_kind") or "") != "schedule":
        raise ValueError("Không tìm thấy bản nháp lịch")
    cadence = normalize_cadence(draft.get("schedule_cadence"))
    normalized = dict(config or {})
    normalized["timezone"] = str(normalized.get("timezone") or DEFAULT_TIMEZONE)
    if cadence != "one_time":
        hour, minute = _parse_send_time(normalized.get("send_time") or "09:00")
        normalized["send_time"] = f"{hour:02d}:{minute:02d}"
    return _update_draft(db, draft_id, admin_id, schedule_config=normalized, state="draft")


def create_schedule_from_draft(db: str | Path, draft_id: str, admin_id: Any, *, now: datetime | None = None) -> dict[str, Any]:
    draft = get_draft(db, draft_id, admin_id)
    if not draft:
        raise ValueError("Không tìm thấy bản nháp")
    if int(draft.get("schedule_id") or 0):
        conn, owned = _connect(db)
        try:
            return _schedule_dict(conn.execute(
                "SELECT * FROM broadcast_lite_schedules WHERE schedule_id=?", (int(draft["schedule_id"]),)
            ).fetchone()) or {}
        finally:
            if owned:
                conn.close()
    if str(draft.get("draft_kind") or "") != "schedule":
        raise ValueError("Bản nháp này không phải lịch thông báo")
    if not draft.get("audience_kind"):
        raise ValueError("Cần chọn người nhận cho lịch")
    config = dict(draft.get("schedule_config") or {})
    cadence = normalize_cadence(draft.get("schedule_cadence"))
    schedule = create_schedule(
        db,
        name=str(config.get("name") or draft.get("title") or f"Lịch {cadence}"),
        message_text=str(draft.get("message_text") or ""),
        media_file_id=str(draft.get("media_file_id") or ""),
        media_type=str(draft.get("media_type") or ""),
        ctas=draft.get("ctas") or [],
        audience_kind=str(draft["audience_kind"]),
        audience_filter=str(draft.get("audience_value") or ""),
        cadence=cadence,
        timezone_name=str(config.get("timezone") or DEFAULT_TIMEZONE),
        send_time=str(config.get("send_time") or "09:00"),
        day_of_week=config.get("day_of_week"),
        day_of_month=config.get("day_of_month"),
        starts_at=config.get("starts_at"),
        expires_at=config.get("expires_at"),
        created_by=admin_id,
        now=now,
    )
    return _update_draft(
        db,
        draft_id,
        admin_id,
        schedule_id=int(schedule["schedule_id"]),
        state="scheduled",
    ) | {"schedule": schedule}


def _schedule_source(cadence: str) -> str:
    return "one_time_schedule" if cadence == "one_time" else f"{cadence}_schedule"


def _schedule_period_key(schedule: Mapping[str, Any], current: datetime) -> str:
    zone = _schedule_zone(schedule.get("timezone"))
    local = current.astimezone(zone)
    cadence = str(schedule.get("cadence") or "")
    if cadence == "monthly":
        return local.strftime("%Y-%m")
    if cadence == "weekly":
        iso = local.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    if cadence == "daily":
        return local.strftime("%Y-%m-%d")
    return "once"


def run_due_schedules(db: str | Path, *, now: datetime | None = None, limit: int = 20) -> dict[str, int]:
    current = _utc_now(now)
    conn, owned = _connect(db)
    queued = duplicate = disabled = suppressed = deferred = 0
    try:
        ensure_schema(conn)
        rows = conn.execute(
            """SELECT * FROM broadcast_lite_schedules
            WHERE is_active=1 AND next_run_at IS NOT NULL AND next_run_at<=?
            ORDER BY priority DESC,schedule_id LIMIT ?""",
            (current.isoformat(), max(1, min(int(limit), 100))),
        ).fetchall()
        for row in rows:
            schedule = _schedule_dict(row) or {}
            conn.execute("BEGIN IMMEDIATE")
            try:
                expires = _parse_datetime(schedule.get("expires_at"))
                if expires and expires < current:
                    conn.execute(
                        "UPDATE broadcast_lite_schedules SET is_active=0,next_run_at=NULL,updated_at=? WHERE schedule_id=?",
                        (current.isoformat(), int(schedule["schedule_id"])),
                    )
                    conn.commit()
                    disabled += 1
                    continue
                cadence = normalize_cadence(schedule.get("cadence"))
                source = _schedule_source(cadence)
                period_key = _schedule_period_key(schedule, current)
                idempotency_key = f"schedule:{int(schedule['schedule_id'])}:{period_key}"
                existing = conn.execute(
                    "SELECT campaign_id FROM broadcast_lite_campaigns WHERE idempotency_key=?",
                    (idempotency_key,),
                ).fetchone()
                next_run = next_schedule_run(
                    cadence=cadence,
                    timezone_name=str(schedule.get("timezone") or DEFAULT_TIMEZONE),
                    send_time=str(schedule.get("send_time") or "09:00"),
                    day_of_week=schedule.get("day_of_week"),
                    day_of_month=schedule.get("day_of_month"),
                    starts_at=schedule.get("starts_at"),
                    after=current + timedelta(seconds=1),
                )
                if existing:
                    conn.execute(
                        "UPDATE broadcast_lite_schedules SET last_enqueued_at=COALESCE(last_enqueued_at,?),next_run_at=?,is_active=?,updated_at=? WHERE schedule_id=?",
                        (
                            current.isoformat(), next_run.isoformat() if next_run else None,
                            int(cadence != "one_time" and bool(next_run)), current.isoformat(), int(schedule["schedule_id"]),
                        ),
                    )
                    conn.commit()
                    duplicate += 1
                    continue
                targets, _invalid = _audience_ids(
                    conn, str(schedule.get("audience_kind") or ""), str(schedule.get("audience_filter") or "")
                )
                ctas = normalize_ctas(schedule.get("ctas") or [])
                content_hash = notification_content_hash(str(schedule.get("message_text") or ""), str(schedule.get("media_file_id") or ""))
                cta_hash = notification_cta_hash(ctas)
                accepted: list[str] = []
                retry_map: dict[str, float] = {}
                for user_id in targets:
                    decision = _frequency_decision_conn(
                        conn,
                        user_id,
                        source=source,
                        content_hash=content_hash,
                        cta_hash=cta_hash,
                        promotion_id=f"schedule:{int(schedule['schedule_id'])}",
                        now=current,
                    )
                    if decision["allowed"]:
                        accepted.append(user_id)
                    elif decision.get("retry_at") is not None and decision.get("reason") != "duplicate_7d":
                        accepted.append(user_id)
                        retry_map[user_id] = decision["retry_at"].timestamp()
                        deferred += 1
                    else:
                        suppressed += 1
                campaign = _insert_campaign_conn(
                    conn,
                    title=str(schedule.get("name") or "Thông báo tự động"),
                    message_text=str(schedule.get("message_text") or ""),
                    media_file_id=str(schedule.get("media_file_id") or ""),
                    media_type=str(schedule.get("media_type") or ""),
                    ctas=ctas,
                    audience_kind=str(schedule.get("audience_kind") or ""),
                    audience_value=str(schedule.get("audience_filter") or ""),
                    created_by=str(schedule.get("created_by") or "system"),
                    idempotency_key=idempotency_key,
                    targets=accepted,
                    source=source,
                    trigger_type=source,
                    schedule_id=int(schedule["schedule_id"]),
                    promotion_id=f"schedule:{int(schedule['schedule_id'])}",
                    priority=int(schedule.get("priority") or CAMPAIGN_PRIORITY[source]),
                    next_retry_by_user=retry_map,
                    reserved_at=current,
                )
                if not accepted:
                    conn.execute(
                        "UPDATE broadcast_lite_campaigns SET status='completed',completed_at=?,updated_at=? WHERE campaign_id=?",
                        (current.isoformat(), current.isoformat(), int(campaign["campaign_id"])),
                    )
                active = cadence != "one_time" and bool(next_run)
                if expires and next_run and next_run > expires:
                    active = False
                    next_run = None
                conn.execute(
                    "UPDATE broadcast_lite_schedules SET last_enqueued_at=?,next_run_at=?,is_active=?,updated_at=? WHERE schedule_id=?",
                    (
                        current.isoformat(), next_run.isoformat() if next_run else None, int(active),
                        current.isoformat(), int(schedule["schedule_id"]),
                    ),
                )
                conn.commit()
                queued += 1
            except Exception:
                conn.rollback()
                raise
        return {
            "inspected": len(rows), "queued": queued, "duplicate": duplicate, "disabled": disabled,
            "suppressed": suppressed, "deferred": deferred,
        }
    finally:
        if owned:
            conn.close()


def campaign_stats(db: str | Path, campaign_id: int) -> dict[str, int | str]:
    conn, owned = _connect(db)
    try:
        ensure_schema(conn)
        campaign = conn.execute("SELECT status,total_targets FROM broadcast_lite_campaigns WHERE campaign_id=?", (int(campaign_id),)).fetchone()
        if not campaign:
            raise ValueError("Không tìm thấy đợt gửi")
        counts = {str(row["status"]): int(row["count"]) for row in conn.execute(
            "SELECT status, COUNT(*) AS count FROM broadcast_lite_deliveries WHERE campaign_id=? GROUP BY status",
            (int(campaign_id),),
        )}
        sent = counts.get("success", 0)
        blocked = counts.get("blocked", 0)
        failed = counts.get("failed", 0)
        waiting = counts.get("pending", 0) + counts.get("sending", 0)
        return {
            "campaign_id": int(campaign_id),
            "status": str(campaign["status"]),
            "total": int(campaign["total_targets"]),
            "sent": sent,
            "failed": failed,
            "blocked": blocked,
            "waiting": waiting,
        }
    finally:
        if owned:
            conn.close()


def list_campaigns(db: str | Path, admin_id: Any, limit: int = 10) -> list[dict[str, Any]]:
    conn, owned = _connect(db)
    try:
        ensure_schema(conn)
        rows = conn.execute(
            "SELECT * FROM broadcast_lite_campaigns WHERE created_by=? ORDER BY campaign_id DESC LIMIT ?",
            (str(admin_id), max(1, min(int(limit), 50))),
        ).fetchall()
        result = []
        for row in rows:
            item = _campaign_dict(row) or {}
            item["stats"] = campaign_stats(conn, int(item["campaign_id"]))
            result.append(item)
        return result
    finally:
        if owned:
            conn.close()


def _is_blocked_error(error: Any) -> bool:
    code = getattr(error, "status_code", None) or getattr(error, "error_code", None)
    text = str(error or "").lower()
    blocked_text = any(token in text for token in ("bot was blocked", "chat not found", "user is deactivated", "forbidden"))
    if str(code or "").isdigit() and int(code) == 403:
        return True
    return blocked_text


def _retry_after(error: Any) -> float | None:
    value = getattr(error, "retry_after", None)
    if value is None and isinstance(error, Mapping):
        value = error.get("retry_after")
    if isinstance(value, timedelta):
        return max(0.0, value.total_seconds())
    try:
        return max(0.0, float(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _is_transient_error(error: Any) -> bool:
    if _retry_after(error) is not None:
        return True
    code = getattr(error, "status_code", None) or getattr(error, "error_code", None)
    if str(code or "").isdigit() and int(code) in {408, 425, 429, 500, 502, 503, 504}:
        return True
    text = str(error or "").lower()
    return any(token in text for token in ("timeout", "temporarily", "connection", "network", "try again", "429"))


def _safe_error(error: Any) -> str:
    text = str(error or "error").replace("\n", " ").strip()
    return text[:240]


def _claim_batch(conn: sqlite3.Connection, batch_size: int, worker_name: str) -> list[dict[str, Any]]:
    stamp = now_text()
    stale_before = (datetime.now(timezone.utc) - timedelta(minutes=10)).replace(microsecond=0).isoformat()
    conn.execute(
        "UPDATE broadcast_lite_deliveries SET status='pending',next_retry_at=0,last_error='resumed after stale worker claim' "
        "WHERE status='sending' AND last_attempt_at IS NOT NULL AND last_attempt_at<?",
        (stale_before,),
    )
    conn.execute(
        "INSERT INTO broadcast_lite_worker_heartbeats(worker_name,heartbeat_at,detail) VALUES (?,?,?) "
        "ON CONFLICT(worker_name) DO UPDATE SET heartbeat_at=excluded.heartbeat_at,detail=excluded.detail",
        (worker_name, stamp, "claim"),
    )
    rows = conn.execute(
        """SELECT d.*, c.message_text, c.media_file_id, c.media_type, c.keyboard_json, c.status AS campaign_status
        FROM broadcast_lite_deliveries d JOIN broadcast_lite_campaigns c ON c.campaign_id=d.campaign_id
        WHERE d.status='pending' AND d.next_retry_at<=? AND c.status IN ('queued','running')
        ORDER BY c.priority DESC,d.delivery_id LIMIT ?""",
        (time.time(), max(1, int(batch_size))),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        conn.execute(
            "UPDATE broadcast_lite_deliveries SET status='sending',attempt_count=attempt_count+1,last_attempt_at=?,worker_heartbeat_at=? WHERE delivery_id=? AND status='pending'",
            (stamp, stamp, int(row["delivery_id"])),
        )
        claimed = conn.execute("SELECT * FROM broadcast_lite_deliveries WHERE delivery_id=? AND status='sending'", (int(row["delivery_id"]),)).fetchone()
        if claimed:
            result.append({**dict(row), **dict(claimed)})
    if rows:
        conn.execute(
            "UPDATE broadcast_lite_campaigns SET status='running',started_at=COALESCE(started_at,?),updated_at=? WHERE campaign_id IN (SELECT campaign_id FROM broadcast_lite_deliveries WHERE status='sending')",
            (stamp, stamp),
        )
    return result


def _finish_campaigns(conn: sqlite3.Connection) -> None:
    stamp = now_text()
    rows = conn.execute("SELECT campaign_id FROM broadcast_lite_campaigns WHERE status IN ('queued','running')").fetchall()
    for row in rows:
        open_count = int(conn.execute(
            "SELECT COUNT(*) FROM broadcast_lite_deliveries WHERE campaign_id=? AND status IN ('pending','sending')",
            (int(row["campaign_id"]),),
        ).fetchone()[0])
        if open_count == 0:
            conn.execute(
                "UPDATE broadcast_lite_campaigns SET status='completed',completed_at=COALESCE(completed_at,?),updated_at=? WHERE campaign_id=?",
                (stamp, stamp, int(row["campaign_id"])),
            )


def _mark_delivery_success_conn(conn: sqlite3.Connection, delivery: Mapping[str, Any], message_id: str) -> None:
    stamp = now_text()
    delivery_id = int(delivery["delivery_id"])
    conn.execute(
        "UPDATE broadcast_lite_deliveries SET status='success',telegram_message_id=?,sent_at=?,last_error='' WHERE delivery_id=? AND status='sending'",
        (str(message_id or ""), stamp, delivery_id),
    )
    frequency_log_id = int(delivery.get("frequency_log_id") or 0)
    if frequency_log_id:
        conn.execute(
            "UPDATE broadcast_lite_frequency_log SET status='sent',sent_at=?,updated_at=? WHERE frequency_log_id=?",
            (stamp, stamp, frequency_log_id),
        )
    conn.execute(
        """UPDATE broadcast_lite_auto_notices
        SET status='sent',sent_at=?,telegram_message_id=?,updated_at=?
        WHERE campaign_id=? AND user_id=? AND status IN ('queued','pending')""",
        (
            stamp, str(message_id or ""), stamp, int(delivery["campaign_id"]),
            str(delivery.get("user_id") or delivery.get("telegram_chat_id") or ""),
        ),
    )


def _mark_delivery_terminal_conn(
    conn: sqlite3.Connection,
    delivery: Mapping[str, Any],
    *,
    status: str,
    error: Any,
) -> None:
    delivery_id = int(delivery["delivery_id"])
    stamp = now_text()
    conn.execute(
        "UPDATE broadcast_lite_deliveries SET status=?,last_error=?,next_retry_at=0 WHERE delivery_id=? AND status='sending'",
        (str(status), _safe_error(error), delivery_id),
    )
    frequency_log_id = int(delivery.get("frequency_log_id") or 0)
    if frequency_log_id:
        conn.execute(
            "UPDATE broadcast_lite_frequency_log SET status=?,updated_at=? WHERE frequency_log_id=?",
            (str(status), stamp, frequency_log_id),
        )
    conn.execute(
        """UPDATE broadcast_lite_auto_notices SET status=?,updated_at=?
        WHERE campaign_id=? AND user_id=? AND status IN ('queued','pending')""",
        (
            str(status), stamp, int(delivery["campaign_id"]),
            str(delivery.get("user_id") or delivery.get("telegram_chat_id") or ""),
        ),
    )


def run_outbox_once(
    db: str | Path,
    send_delivery: Callable[[Mapping[str, Any]], Any],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_delay: float = DEFAULT_RETRY_DELAY,
    worker_name: str = "broadcast-lite",
) -> dict[str, int]:
    """Claim and deliver one bounded batch. ``send_delivery`` is injected for tests."""
    conn, owned = _connect(db)
    success = failed = blocked = retried = 0
    try:
        ensure_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        batch = _claim_batch(conn, batch_size, worker_name)
        conn.commit()
        for delivery in batch:
            try:
                result = send_delivery(delivery)
                if inspect.isawaitable(result):
                    raise RuntimeError("async sender requires an async worker adapter")
                message_id = ""
                if isinstance(result, Mapping):
                    message_id = str(result.get("message_id") or result.get("id") or "")
                _mark_delivery_success_conn(conn, delivery, message_id)
                success += 1
            except Exception as error:
                attempt = int(delivery.get("attempt_count") or 0)
                if _is_blocked_error(error):
                    conn.execute(
                        "INSERT INTO broadcast_lite_blocked_users(user_id,blocked_at,reason) VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET blocked_at=excluded.blocked_at,reason=excluded.reason",
                        (str(delivery["telegram_chat_id"]), now_text(), _safe_error(error)),
                    )
                    _mark_delivery_terminal_conn(conn, delivery, status="blocked", error=error)
                    blocked += 1
                elif _is_transient_error(error) and attempt < max(1, int(max_attempts)):
                    delay = _retry_after(error)
                    conn.execute(
                        "UPDATE broadcast_lite_deliveries SET status='pending',last_error=?,next_retry_at=? WHERE delivery_id=? AND status='sending'",
                        (_safe_error(error), time.time() + (delay if delay is not None else max(0.0, float(retry_delay))), int(delivery["delivery_id"])),
                    )
                    retried += 1
                else:
                    _mark_delivery_terminal_conn(conn, delivery, status="failed", error=error)
                    failed += 1
            conn.commit()
        conn.execute(
            "INSERT INTO broadcast_lite_worker_heartbeats(worker_name,heartbeat_at,detail) VALUES (?,?,?) ON CONFLICT(worker_name) DO UPDATE SET heartbeat_at=excluded.heartbeat_at,detail=excluded.detail",
            (worker_name, now_text(), f"success={success};failed={failed};blocked={blocked};retried={retried}"),
        )
        _finish_campaigns(conn)
        conn.commit()
        return {"claimed": len(batch), "success": success, "failed": failed, "blocked": blocked, "retried": retried}
    finally:
        if owned:
            conn.close()


async def run_outbox_once_async(
    db: str | Path,
    send_delivery: Callable[[Mapping[str, Any]], Any],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_delay: float = DEFAULT_RETRY_DELAY,
    worker_name: str = "broadcast-lite",
) -> dict[str, int]:
    """Async counterpart used by the Telegram worker; sender may be async."""
    conn, owned = _connect(db)
    success = failed = blocked = retried = 0
    try:
        ensure_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        batch = _claim_batch(conn, batch_size, worker_name)
        conn.commit()
        for delivery in batch:
            try:
                result = send_delivery(delivery)
                if inspect.isawaitable(result):
                    result = await result
                message_id = ""
                if isinstance(result, Mapping):
                    message_id = str(result.get("message_id") or result.get("id") or "")
                _mark_delivery_success_conn(conn, delivery, message_id)
                success += 1
            except Exception as error:
                attempt = int(delivery.get("attempt_count") or 0)
                if _is_blocked_error(error):
                    conn.execute(
                        "INSERT INTO broadcast_lite_blocked_users(user_id,blocked_at,reason) VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET blocked_at=excluded.blocked_at,reason=excluded.reason",
                        (str(delivery["telegram_chat_id"]), now_text(), _safe_error(error)),
                    )
                    _mark_delivery_terminal_conn(conn, delivery, status="blocked", error=error)
                    blocked += 1
                elif _is_transient_error(error) and attempt < max(1, int(max_attempts)):
                    delay = _retry_after(error)
                    conn.execute(
                        "UPDATE broadcast_lite_deliveries SET status='pending',last_error=?,next_retry_at=? WHERE delivery_id=? AND status='sending'",
                        (_safe_error(error), time.time() + (delay if delay is not None else max(0.0, float(retry_delay))), int(delivery["delivery_id"])),
                    )
                    retried += 1
                else:
                    _mark_delivery_terminal_conn(conn, delivery, status="failed", error=error)
                    failed += 1
            conn.commit()
        conn.execute(
            "INSERT INTO broadcast_lite_worker_heartbeats(worker_name,heartbeat_at,detail) VALUES (?,?,?) ON CONFLICT(worker_name) DO UPDATE SET heartbeat_at=excluded.heartbeat_at,detail=excluded.detail",
            (worker_name, now_text(), f"success={success};failed={failed};blocked={blocked};retried={retried}"),
        )
        _finish_campaigns(conn)
        conn.commit()
        return {"claimed": len(batch), "success": success, "failed": failed, "blocked": blocked, "retried": retried}
    finally:
        if owned:
            conn.close()
