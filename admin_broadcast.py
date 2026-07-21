"""Small, idempotent admin broadcast outbox.

This module deliberately owns only notification composition and delivery state.
It has no knowledge of billing, products, providers, or customer balances.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import re
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping


MAX_MESSAGE_LENGTH = 4000
MAX_CTA_COUNT = 4
DEFAULT_BATCH_SIZE = 20
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_DELAY = 15.0
CHAT_ID_RE = re.compile(r"^-?\d{1,30}$")

CTA_REGISTRY: dict[str, dict[str, str]] = {
    "topup": {"label": "💳 Nạp ngay", "callback_data": "menu|main_topup"},
    "video": {"label": "🎬 Tạo video ngay", "callback_data": "menu|main_video"},
    "image": {"label": "🖼️ Tạo ảnh ngay", "callback_data": "menu|main_image"},
    "support": {"label": "🆘 Hỗ trợ ngay", "callback_data": "menu|support"},
}

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
        "ctas": ["topup"],
    },
    "second_topup": {
        "label": "Mẫu 2 · Nạp Xu lần hai",
        "message": (
            "🎁 ƯU ĐÃI NẠP XU LẦN HAI\n\n"
            "Nạp Xu lần thứ hai được tặng thêm 20% Xu.\n"
            "Không cần mã giảm giá."
        ),
        "ctas": ["topup"],
    },
    "video": {
        "label": "Mẫu 3 · Tạo video AI",
        "message": (
            "🎬 TẠO VIDEO AI CÙNG TOAN AAS\n\n"
            "Chọn loại video và bắt đầu tạo video ngay trên bot."
        ),
        "ctas": ["video"],
    },
    "image": {
        "label": "Mẫu 4 · Tạo ảnh AI",
        "message": (
            "🖼️ TẠO ẢNH AI CÙNG TOAN AAS\n\n"
            "Tạo ảnh sản phẩm, người mẫu và quảng cáo ngay trên bot."
        ),
        "ctas": ["image"],
    },
}


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


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create only the notification tables; safe to call during every startup."""
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
        """
    )


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
    return value


def _new_draft(conn: sqlite3.Connection, admin_id: Any, **values: Any) -> str:
    draft_id = uuid.uuid4().hex
    stamp = now_text()
    conn.execute(
        """INSERT INTO broadcast_lite_drafts
        (draft_id, admin_id, title, message_text, media_file_id, media_type,
         keyboard_json, audience_kind, audience_value, state, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
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
            stamp,
            stamp,
        ),
    )
    return draft_id


def create_empty_draft(db: str | Path, admin_id: Any, *, state: str = "awaiting_message") -> dict[str, Any]:
    conn, owned = _connect(db)
    try:
        ensure_schema(conn)
        draft_id = _new_draft(conn, admin_id, state=state)
        conn.commit()
        return get_draft(db, draft_id, admin_id) or {}
    finally:
        if owned:
            conn.close()


def create_template_draft(db: str | Path, admin_id: Any, template_key: str) -> dict[str, Any]:
    template = TEMPLATES.get(str(template_key))
    if not template:
        raise ValueError("Mẫu thông báo không tồn tại")
    conn, owned = _connect(db)
    try:
        ensure_schema(conn)
        draft_id = _new_draft(
            conn,
            admin_id,
            title=template["label"],
            message_text=template["message"],
            ctas=template["ctas"],
            state="draft",
        )
        conn.commit()
        return get_draft(db, draft_id, admin_id) or {}
    finally:
        if owned:
            conn.close()


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
        "awaiting_photo",
        "awaiting_caption",
        "awaiting_audience_user",
        "awaiting_audience_test_list",
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
            if key not in {
                "title", "message_text", "media_file_id", "media_type", "keyboard_json",
                "audience_kind", "audience_value", "state", "campaign_id",
            }:
                raise ValueError("Trường draft không hợp lệ")
            assignments.append(f"{key}=?")
            params.append(value)
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
    if len(text) > MAX_MESSAGE_LENGTH:
        raise ValueError(f"Nội dung tối đa {MAX_MESSAGE_LENGTH} ký tự")
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
    if len(caption) > MAX_MESSAGE_LENGTH:
        raise ValueError(f"Nội dung tối đa {MAX_MESSAGE_LENGTH} ký tự")
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


def confirm_draft(db: str | Path, draft_id: str, admin_id: Any) -> dict[str, Any]:
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
        stamp = now_text()
        key = f"broadcast-lite:{admin_id}:{draft_id}"
        conn.execute(
            """INSERT INTO broadcast_lite_campaigns
            (title,message_text,media_file_id,media_type,keyboard_json,audience_kind,audience_value,
             status,created_by,idempotency_key,total_targets,created_at,updated_at)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                draft.get("title") or "Thông báo khách hàng",
                draft.get("message_text") or "",
                draft.get("media_file_id") or "",
                draft.get("media_type") or "",
                draft.get("keyboard_json") or "[]",
                draft["audience_kind"],
                draft.get("audience_value") or "",
                "queued",
                str(admin_id),
                key,
                len(targets),
                stamp,
                stamp,
            ),
        )
        campaign_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.executemany(
            "INSERT INTO broadcast_lite_deliveries(campaign_id,telegram_chat_id) VALUES (?,?)",
            [(campaign_id, chat_id) for chat_id in targets],
        )
        conn.execute(
            "UPDATE broadcast_lite_drafts SET campaign_id=?, state='confirmed', updated_at=? WHERE draft_id=? AND admin_id=?",
            (campaign_id, stamp, str(draft_id), str(admin_id)),
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
    return int(code) in {400, 403} if str(code or "").isdigit() else any(token in text for token in ("bot was blocked", "chat not found", "user is deactivated", "forbidden"))


def _retry_after(error: Any) -> float | None:
    value = getattr(error, "retry_after", None)
    if value is None and isinstance(error, Mapping):
        value = error.get("retry_after")
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
        ORDER BY d.delivery_id LIMIT ?""",
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
                conn.execute(
                    "UPDATE broadcast_lite_deliveries SET status='success',telegram_message_id=?,sent_at=?,last_error='' WHERE delivery_id=? AND status='sending'",
                    (message_id, now_text(), int(delivery["delivery_id"])),
                )
                success += 1
            except Exception as error:
                attempt = int(delivery.get("attempt_count") or 0)
                if _is_blocked_error(error):
                    conn.execute(
                        "INSERT INTO broadcast_lite_blocked_users(user_id,blocked_at,reason) VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET blocked_at=excluded.blocked_at,reason=excluded.reason",
                        (str(delivery["telegram_chat_id"]), now_text(), _safe_error(error)),
                    )
                    conn.execute(
                        "UPDATE broadcast_lite_deliveries SET status='blocked',last_error=?,next_retry_at=0 WHERE delivery_id=? AND status='sending'",
                        (_safe_error(error), int(delivery["delivery_id"])),
                    )
                    blocked += 1
                elif _is_transient_error(error) and attempt < max(1, int(max_attempts)):
                    delay = _retry_after(error)
                    conn.execute(
                        "UPDATE broadcast_lite_deliveries SET status='pending',last_error=?,next_retry_at=? WHERE delivery_id=? AND status='sending'",
                        (_safe_error(error), time.time() + (delay if delay is not None else max(0.0, float(retry_delay))), int(delivery["delivery_id"])),
                    )
                    retried += 1
                else:
                    conn.execute(
                        "UPDATE broadcast_lite_deliveries SET status='failed',last_error=?,next_retry_at=0 WHERE delivery_id=? AND status='sending'",
                        (_safe_error(error), int(delivery["delivery_id"])),
                    )
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
                conn.execute(
                    "UPDATE broadcast_lite_deliveries SET status='success',telegram_message_id=?,sent_at=?,last_error='' WHERE delivery_id=? AND status='sending'",
                    (message_id, now_text(), int(delivery["delivery_id"])),
                )
                success += 1
            except Exception as error:
                attempt = int(delivery.get("attempt_count") or 0)
                if _is_blocked_error(error):
                    conn.execute(
                        "INSERT INTO broadcast_lite_blocked_users(user_id,blocked_at,reason) VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET blocked_at=excluded.blocked_at,reason=excluded.reason",
                        (str(delivery["telegram_chat_id"]), now_text(), _safe_error(error)),
                    )
                    conn.execute(
                        "UPDATE broadcast_lite_deliveries SET status='blocked',last_error=?,next_retry_at=0 WHERE delivery_id=? AND status='sending'",
                        (_safe_error(error), int(delivery["delivery_id"])),
                    )
                    blocked += 1
                elif _is_transient_error(error) and attempt < max(1, int(max_attempts)):
                    delay = _retry_after(error)
                    conn.execute(
                        "UPDATE broadcast_lite_deliveries SET status='pending',last_error=?,next_retry_at=? WHERE delivery_id=? AND status='sending'",
                        (_safe_error(error), time.time() + (delay if delay is not None else max(0.0, float(retry_delay))), int(delivery["delivery_id"])),
                    )
                    retried += 1
                else:
                    conn.execute(
                        "UPDATE broadcast_lite_deliveries SET status='failed',last_error=?,next_retry_at=0 WHERE delivery_id=? AND status='sending'",
                        (_safe_error(error), int(delivery["delivery_id"])),
                    )
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
