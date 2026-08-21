"""Durable SQLite authority for public-chat quota and request lifecycle.

The legacy ``users.free_chat_count/free_chat_date`` columns are deliberately
never read or written.  Free quota is derived only from request rows reserved
or consumed for the Vietnam calendar day.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Iterator, Mapping
import uuid
from zoneinfo import ZoneInfo

from services.chat_pro_pricing import (
    DEFAULT_USD_FIXED_RATE_VND,
    DEFAULT_XU_TO_VND,
    OPUS_MODEL_ID,
    OpusUsage,
    calculate_opus_charge_xu,
)


FREE_DAILY_LIMIT = 20
PUBLIC_CONTEXT_HOURS = 48
DEFAULT_CONTEXT_TURNS = 12
DEFAULT_CONTEXT_CHARACTERS = 6_000
DEFAULT_RESERVATION_TTL_SECONDS = 15 * 60
VIETNAM_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")

_REQUEST_COLUMNS = (
    "request_id", "owner_id", "chat_id", "source_message_id", "mode", "quota_date", "session_id",
    "status", "is_admin", "reserved_xu", "actual_xu", "settled_xu", "refunded_xu",
    "uncollected_xu", "input_tokens", "output_tokens", "cache_read_tokens", "provider", "model",
    "provider_request_id", "wallet_reservation_id", "reason", "result_json", "created_at", "updated_at",
)
_SELECT = ", ".join(_REQUEST_COLUMNS)
_REDACTED = "[đã ẩn thông tin nhạy cảm]"
_SENSITIVE = (
    # Whole signed/private URLs must be removed before a generic key/value
    # pattern can redact only the query fragment.
    re.compile(r"https?://[^\s<>\"']*[?&](?:token|access_token|api_key|key|sig|signature|x-amz-signature|x-amz-credential|x-amz-security-token)=[^\s<>\"']+", re.I),
    re.compile(r"\bAuthorization\s*:\s*(?:Basic|Bearer)\s+[^\s;]+|\bAuthorization\s*:\s*Digest\s+(?:[A-Za-z][A-Za-z0-9_-]*=(?:\"[^\"]*\"|[^,\s;]+)(?:\s*,\s*[A-Za-z][A-Za-z0-9_-]*=(?:\"[^\"]*\"|[^,\s;]+))*)", re.I),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", re.I),
    re.compile(r"\b(?:api[_-]?key|token|secret|password|passwd)\s*[:=]\s*[^\s,;]+", re.I),
    re.compile(r"(?<!\w)\\\\[^\\\r\n<>:\"|?*;,]+\\[^\r\n<>:\"|?*;,]+"),
    re.compile(r"(?<!\w)[A-Za-z]:[\\/](?:[^\\/\r\n<>:\"|?*;,]+[\\/])+[^\r\n<>:\"|?*;,]+"),
    re.compile(r"(?<!\w)[A-Za-z]:[\\/](?:[^\s<>:\"|?*]+[\\/])*[^\s<>:\"|?*]+"),
    re.compile(r"(?<!\w)/(?:etc|home|root|var|usr|opt|tmp|private|workspace|app|data|mnt|srv|run|Users)(?:/[^\s\"'<>|?*;,!?)]*)+", re.I),
)
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")


@dataclass(frozen=True)
class RequestDecision:
    status: str
    request_id: str
    accepted: bool = False
    duplicate: bool = False
    result: dict[str, Any] | None = None


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS public_chat_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id TEXT NOT NULL, chat_id TEXT NOT NULL, session_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user','assistant')),
            mode TEXT NOT NULL CHECK(mode IN ('free','pro')),
            content TEXT NOT NULL, source_message_id TEXT NOT NULL,
            content_hash TEXT NOT NULL, redaction_applied INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            UNIQUE(owner_id, chat_id, role, source_message_id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS public_chat_requests (
            request_id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL, chat_id TEXT NOT NULL, source_message_id TEXT NOT NULL,
            mode TEXT NOT NULL CHECK(mode IN ('free','pro')), quota_date TEXT NOT NULL DEFAULT '',
            session_id TEXT NOT NULL, status TEXT NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0,
            reserved_xu INTEGER NOT NULL DEFAULT 0, actual_xu INTEGER NOT NULL DEFAULT 0,
            settled_xu INTEGER NOT NULL DEFAULT 0, refunded_xu INTEGER NOT NULL DEFAULT 0,
            uncollected_xu INTEGER NOT NULL DEFAULT 0, input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0, cache_read_tokens INTEGER NOT NULL DEFAULT 0,
            provider TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '',
            provider_request_id TEXT NOT NULL DEFAULT '', wallet_reservation_id TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '', result_json TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL, updated_at REAL NOT NULL,
            UNIQUE(owner_id, chat_id, source_message_id)
        )"""
    )
    existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(public_chat_requests)")}
    for name in ("provider_request_id", "wallet_reservation_id", "result_json"):
        if name not in existing:
            conn.execute(f"ALTER TABLE public_chat_requests ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_public_chat_free_quota ON public_chat_requests(owner_id, quota_date, mode, is_admin, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_public_chat_turns_context ON public_chat_turns(owner_id, chat_id, created_at, id)")


def _timestamp(value: Any = None) -> float:
    if value is None:
        return time.time()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=VIETNAM_TIMEZONE)
        return value.timestamp()
    if isinstance(value, date):
        return datetime.combine(value, datetime_time.min, tzinfo=VIETNAM_TIMEZONE).timestamp()
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("now must be a finite timestamp") from exc
    if not math.isfinite(parsed):
        raise ValueError("now must be a finite timestamp")
    return parsed


def vietnam_quota_date(now: Any = None) -> str:
    return datetime.fromtimestamp(_timestamp(now), tz=VIETNAM_TIMEZONE).date().isoformat()


def _identity(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} is required")
    return text[:180]


def _request_id(owner: str, chat: str, source: str) -> str:
    digest = hashlib.sha256("\0".join((owner, chat, source)).encode()).hexdigest()
    return f"public-chat-{digest}"


def _row(row: Any) -> dict[str, Any] | None:
    return None if row is None else {name: row[index] for index, name in enumerate(_REQUEST_COLUMNS)}


def _by_id(conn: sqlite3.Connection, request_id: str) -> dict[str, Any] | None:
    return _row(conn.execute(f"SELECT {_SELECT} FROM public_chat_requests WHERE request_id=?", (request_id,)).fetchone())


def _by_identity(conn: sqlite3.Connection, owner: str, chat: str, source: str) -> dict[str, Any] | None:
    return _row(conn.execute(
        f"SELECT {_SELECT} FROM public_chat_requests WHERE owner_id=? AND chat_id=? AND source_message_id=?",
        (owner, chat, source),
    ).fetchone())


def _begin(conn: sqlite3.Connection) -> None:
    ensure_schema(conn)
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")


@contextmanager
def _savepoint(conn: sqlite3.Connection) -> Iterator[None]:
    name = "public_chat_" + uuid.uuid4().hex
    conn.execute(f"SAVEPOINT {name}")
    try:
        yield
    except Exception:
        conn.execute(f"ROLLBACK TO {name}")
        conn.execute(f"RELEASE {name}")
        raise
    else:
        conn.execute(f"RELEASE {name}")


def _session(conn: sqlite3.Connection, owner: str, chat: str, timestamp: float) -> str:
    cutoff = timestamp - PUBLIC_CONTEXT_HOURS * 3600
    row = conn.execute(
        "SELECT session_id FROM public_chat_turns WHERE owner_id=? AND chat_id=? AND created_at>=? ORDER BY created_at DESC,id DESC LIMIT 1",
        (owner, chat, cutoff),
    ).fetchone()
    return str(row[0]) if row and row[0] else uuid.uuid4().hex


def _luhn(digits: str) -> bool:
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for index, character in enumerate(reversed(digits)):
        number = int(character)
        if index % 2:
            number = number * 2 - (9 if number * 2 > 9 else 0)
        total += number
    return total % 10 == 0


def sanitize_public_chat_content(value: Any) -> tuple[str, bool]:
    text = " ".join(str(value or "").replace("\0", " ").split()).strip()
    redacted = False
    for pattern in _SENSITIVE:
        text, count = pattern.subn(_REDACTED, text)
        redacted = redacted or bool(count)

    def card(match: re.Match[str]) -> str:
        nonlocal redacted
        digits = re.sub(r"\D", "", match.group())
        if _luhn(digits):
            redacted = True
            return _REDACTED
        return match.group()

    return _CARD.sub(card, text)[:4_000], redacted


def _free_count(conn: sqlite3.Connection, owner: str, quota_date: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM public_chat_requests WHERE owner_id=? AND quota_date=? AND mode='free' AND is_admin=0 AND status IN ('reserved','consumed')",
        (owner, quota_date),
    ).fetchone()
    return int(row[0] if row else 0)


def free_quota_status(conn: sqlite3.Connection, owner_id: Any, *, now: Any = None, daily_limit: int = FREE_DAILY_LIMIT, is_admin: bool = False) -> dict[str, Any]:
    ensure_schema(conn)
    owner = _identity(owner_id, "owner_id")
    limit = max(1, int(daily_limit))
    day = vietnam_quota_date(now)
    used = 0 if is_admin else _free_count(conn, owner, day)
    return {"quota_date": day, "limit": limit, "used": used, "remaining": limit if is_admin else max(0, limit - used), "is_admin": bool(is_admin)}


def reserve_free_request(
    conn: sqlite3.Connection,
    *, owner_id: Any, chat_id: Any, source_message_id: Any, now: Any = None,
    daily_limit: int = FREE_DAILY_LIMIT, is_admin: bool = False,
    reservation_ttl_seconds: int = DEFAULT_RESERVATION_TTL_SECONDS, quota_date: str | None = None,
) -> dict[str, Any]:
    owner, chat, source = (_identity(owner_id, "owner_id"), _identity(chat_id, "chat_id"), _identity(source_message_id, "source_message_id"))
    timestamp = _timestamp(now)
    day = str(quota_date or vietnam_quota_date(timestamp))
    limit = max(1, min(int(daily_limit), 10_000))
    ttl = max(30, min(int(reservation_ttl_seconds), 86_400))
    identifier = _request_id(owner, chat, source)
    _begin(conn)
    with _savepoint(conn):
        existing = _by_identity(conn, owner, chat, source)
        if existing:
            return {"accepted": False, "duplicate": True, "exhausted": existing["status"] == "rejected", "request_id": existing["request_id"], "status": existing["status"], "remaining": max(0, limit - _free_count(conn, owner, day))}
        if not is_admin:
            conn.execute(
                "UPDATE public_chat_requests SET status='released',reason='stale_reservation',updated_at=? WHERE owner_id=? AND quota_date=? AND mode='free' AND status='reserved' AND updated_at<?",
                (timestamp, owner, day, timestamp - ttl),
            )
        used = 0 if is_admin else _free_count(conn, owner, day)
        status = "reserved" if is_admin or used < limit else "rejected"
        conn.execute(
            """INSERT INTO public_chat_requests(request_id,owner_id,chat_id,source_message_id,mode,quota_date,session_id,status,is_admin,provider,model,reason,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (identifier, owner, chat, source, "free", day, _session(conn, owner, chat, timestamp), status, int(is_admin), "google", "gemini-3.6-flash", "" if status == "reserved" else "daily_limit", timestamp, timestamp),
        )
        return {"accepted": status == "reserved", "duplicate": False, "exhausted": status == "rejected", "request_id": identifier, "status": status, "remaining": limit if is_admin else max(0, limit - used - (status == "reserved"))}


def _insert_turns(conn: sqlite3.Connection, request: Mapping[str, Any], user_content: Any, assistant_content: Any, timestamp: float) -> None:
    user, user_redacted = sanitize_public_chat_content(user_content)
    answer, answer_redacted = sanitize_public_chat_content(assistant_content)
    if not user or not answer:
        raise ValueError("successful chat needs non-empty text")
    for role, content, source, redacted in (
        ("user", user, str(request["source_message_id"]), user_redacted),
        ("assistant", answer, "reply:" + str(request["source_message_id"]), answer_redacted),
    ):
        conn.execute(
            "INSERT OR IGNORE INTO public_chat_turns(owner_id,chat_id,session_id,role,mode,content,source_message_id,content_hash,redaction_applied,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (request["owner_id"], request["chat_id"], request["session_id"], role, request["mode"], content, source, hashlib.sha256(content.encode()).hexdigest(), int(redacted), timestamp),
        )


def _delivery_json(request: Mapping[str, Any], assistant_content: Any, **metadata: Any) -> str:
    text, _ = sanitize_public_chat_content(assistant_content)
    if not text:
        raise ValueError("delivery text is required")
    payload = {
        "ok": True,
        "status": "ok",
        "mode": str(request["mode"]),
        "text": text,
        "request_id": str(request["request_id"]),
        "delivery_cursor": 0,
        **metadata,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _decode_delivery(value: Any) -> dict[str, Any] | None:
    try:
        payload = json.loads(str(value or ""))
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("ok") is not True or not isinstance(payload.get("text"), str) or not payload["text"].strip():
        return None
    cursor = payload.get("delivery_cursor", 0)
    if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0:
        return None
    total = payload.get("delivery_total_chunks")
    if total is not None:
        if isinstance(total, bool) or not isinstance(total, int) or not 1 <= total <= 100 or cursor > total:
            return None
        payload["delivery_total_chunks"] = total
    payload["delivery_cursor"] = cursor
    return payload


def complete_free_request(conn: sqlite3.Connection, request_id: Any, *, user_content: Any, assistant_content: Any, now: Any = None, daily_limit: int = FREE_DAILY_LIMIT) -> dict[str, Any]:
    identifier, timestamp = _identity(request_id, "request_id"), _timestamp(now)
    _begin(conn)
    with _savepoint(conn):
        request = _by_id(conn, identifier)
        if not request or request["mode"] != "free":
            return {"consumed": False, "duplicate": False, "unknown_request": True}
        if request["status"] != "reserved":
            return {"consumed": False, "duplicate": True, "request_id": identifier, "status": request["status"]}
        user, _ = sanitize_public_chat_content(user_content)
        answer, _ = sanitize_public_chat_content(assistant_content)
        if not user or not answer:
            conn.execute("UPDATE public_chat_requests SET status='released',reason='empty_response',updated_at=? WHERE request_id=?", (timestamp, identifier))
            return {"consumed": False, "duplicate": False, "released": True, "request_id": identifier, "status": "released"}
        _insert_turns(conn, request, user, answer, timestamp)
        delivery = _delivery_json(request, answer, model="gemini-3.6-flash")
        conn.execute("UPDATE public_chat_requests SET status='consumed',result_json=?,updated_at=? WHERE request_id=? AND status='reserved'", (delivery, timestamp, identifier))
        used = 0 if request["is_admin"] else _free_count(conn, str(request["owner_id"]), str(request["quota_date"]))
        return {"consumed": True, "duplicate": False, "request_id": identifier, "status": "consumed", "remaining": int(daily_limit) if request["is_admin"] else max(0, int(daily_limit) - used), "delivery": _decode_delivery(delivery)}


def release_request(conn: sqlite3.Connection, request_id: Any, *, reason: Any = "provider_failure", now: Any = None) -> dict[str, Any]:
    identifier, timestamp = _identity(request_id, "request_id"), _timestamp(now)
    _begin(conn)
    with _savepoint(conn):
        request = _by_id(conn, identifier)
        if not request:
            return {"released": False, "duplicate": False, "unknown_request": True}
        if request["mode"] != "free" or request["status"] != "reserved":
            return {"released": False, "duplicate": True, "request_id": identifier, "status": request["status"]}
        conn.execute("UPDATE public_chat_requests SET status='released',reason=?,updated_at=? WHERE request_id=? AND status='reserved'", (str(reason)[:120], timestamp, identifier))
        return {"released": True, "duplicate": False, "request_id": identifier, "status": "released"}


def _wallet_balance(conn: sqlite3.Connection, owner: str) -> int | None:
    try:
        row = conn.execute("SELECT credits FROM users WHERE CAST(user_id AS TEXT)=?", (owner,)).fetchone()
    except sqlite3.OperationalError:
        return None
    return None if row is None else max(0, int(row[0] or 0))


def _wallet_has_total_spent(conn: sqlite3.Connection) -> bool:
    try:
        return "total_spent" in {str(row[1]) for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    except sqlite3.OperationalError:
        return False


def reserve_pro_request(conn: sqlite3.Connection, *, owner_id: Any, chat_id: Any, source_message_id: Any, reserved_xu: Any, now: Any = None, is_admin: bool = False) -> dict[str, Any]:
    owner, chat, source = (_identity(owner_id, "owner_id"), _identity(chat_id, "chat_id"), _identity(source_message_id, "source_message_id"))
    reserve = 0 if is_admin else int(reserved_xu)
    if reserve <= 0 and not is_admin:
        raise ValueError("reserved_xu must be positive")
    identifier, timestamp = _request_id(owner, chat, source), _timestamp(now)
    _begin(conn)
    with _savepoint(conn):
        existing = _by_identity(conn, owner, chat, source)
        if existing:
            return {"accepted": False, "duplicate": True, "insufficient_balance": False, "request_id": existing["request_id"], "status": existing["status"], "reserved_xu": int(existing["reserved_xu"])}
        if not is_admin:
            balance = _wallet_balance(conn, owner)
            if balance is None or balance < reserve or conn.execute("UPDATE users SET credits=credits-? WHERE CAST(user_id AS TEXT)=? AND credits>=?", (reserve, owner, reserve)).rowcount != 1:
                return {"accepted": False, "duplicate": False, "insufficient_balance": True, "request_id": identifier, "status": "insufficient_balance", "required_xu": reserve, "balance_xu": int(balance or 0)}
        conn.execute(
            "INSERT INTO public_chat_requests(request_id,owner_id,chat_id,source_message_id,mode,session_id,status,is_admin,reserved_xu,provider,model,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (identifier, owner, chat, source, "pro", _session(conn, owner, chat, timestamp), "reserved", int(is_admin), reserve, "key4u", OPUS_MODEL_ID, timestamp, timestamp),
        )
        return {"accepted": True, "duplicate": False, "insufficient_balance": False, "request_id": identifier, "status": "reserved", "reserved_xu": reserve, "balance_xu": int(_wallet_balance(conn, owner) or 0), "is_admin": bool(is_admin)}


def _usage(usage: OpusUsage | Mapping[str, Any] | None, input_tokens: Any, output_tokens: Any, cache_read_tokens: Any) -> OpusUsage:
    if isinstance(usage, OpusUsage):
        base = usage
    elif isinstance(usage, Mapping):
        base = OpusUsage(usage.get("input_tokens", usage.get("prompt_tokens", 0)), usage.get("output_tokens", usage.get("completion_tokens", 0)), usage.get("cache_read_tokens", usage.get("cache_read_input_tokens", 0)))
    else:
        base = OpusUsage()
    return OpusUsage(base.input_tokens if input_tokens is None else input_tokens, base.output_tokens if output_tokens is None else output_tokens, base.cache_read_tokens if cache_read_tokens is None else cache_read_tokens)


def settle_pro_request(
    conn: sqlite3.Connection, request_id: Any, usage: OpusUsage | Mapping[str, Any] | None = None, *,
    input_tokens: Any = None, output_tokens: Any = None, cache_read_tokens: Any = None,
    usd_fixed_rate_vnd: int = DEFAULT_USD_FIXED_RATE_VND, xu_to_vnd: int = DEFAULT_XU_TO_VND,
    user_content: Any = None, assistant_content: Any = None, provider_request_id: Any = None, now: Any = None,
) -> dict[str, Any]:
    identifier, timestamp = _identity(request_id, "request_id"), _timestamp(now)
    normalized = _usage(usage, input_tokens, output_tokens, cache_read_tokens)
    actual = calculate_opus_charge_xu(normalized.input_tokens, normalized.output_tokens, normalized.cache_read_tokens, usd_fixed_rate_vnd=usd_fixed_rate_vnd, xu_to_vnd=xu_to_vnd)
    provider_id = _identity(provider_request_id, "provider_request_id")
    _begin(conn)
    with _savepoint(conn):
        request = _by_id(conn, identifier)
        if not request or request["mode"] != "pro":
            return {"settled": False, "duplicate": False, "unknown_request": True}
        if request["status"] != "reserved":
            return {"settled": False, "duplicate": True, "request_id": identifier, "status": request["status"], "actual_xu": int(request["actual_xu"]), "charged_xu": int(request["settled_xu"]), "refunded_xu": int(request["refunded_xu"]), "uncollected_xu": int(request["uncollected_xu"]), "provider_request_id": str(request["provider_request_id"])}
        reserve, admin = int(request["reserved_xu"]), bool(request["is_admin"])
        charged = 0 if admin else min(actual, reserve)
        refunded = uncollected = 0
        status = "settled"
        reason = ""
        if not admin and actual <= reserve:
            refunded = reserve - actual
            charged = actual
            if not _wallet_has_total_spent(conn):
                raise RuntimeError("users.total_spent column is required for Pro settlement")
            if conn.execute("UPDATE users SET credits=credits+?,total_spent=COALESCE(total_spent,0)+? WHERE CAST(user_id AS TEXT)=?", (refunded, charged, request["owner_id"])).rowcount != 1:
                raise RuntimeError("wallet row missing")
        elif not admin:
            if not _wallet_has_total_spent(conn):
                raise RuntimeError("users.total_spent column is required for Pro settlement")
            additional = actual - reserve
            cursor = conn.execute("UPDATE users SET credits=credits-?,total_spent=COALESCE(total_spent,0)+? WHERE CAST(user_id AS TEXT)=? AND credits>=?", (additional, actual, request["owner_id"], additional))
            if cursor.rowcount == 1:
                charged = actual
            else:
                status = "under_reserved_refunded"
                reason = "insufficient_balance_after_usage"
                charged, refunded, uncollected = 0, reserve, actual
                if conn.execute("UPDATE users SET credits=credits+? WHERE CAST(user_id AS TEXT)=?", (refunded, request["owner_id"])).rowcount != 1:
                    raise RuntimeError("wallet row missing")
        delivery = ""
        if status == "settled" and (user_content is not None or assistant_content is not None):
            if user_content is None or assistant_content is None:
                raise ValueError("both contents are required")
            _insert_turns(conn, request, user_content, assistant_content, timestamp)
            delivery = _delivery_json(
                request,
                assistant_content,
                model=OPUS_MODEL_ID,
                actual_xu=actual,
                charged_xu=charged,
                refunded_xu=refunded,
                provider_request_id=provider_id,
            )
        conn.execute(
            "UPDATE public_chat_requests SET status=?,actual_xu=?,settled_xu=?,refunded_xu=?,uncollected_xu=?,input_tokens=?,output_tokens=?,cache_read_tokens=?,provider_request_id=?,reason=?,result_json=?,updated_at=? WHERE request_id=? AND status='reserved'",
            (status, actual, charged, refunded, uncollected, normalized.input_tokens, normalized.output_tokens, normalized.cache_read_tokens, provider_id, reason, delivery, timestamp, identifier),
        )
        return {"settled": True, "duplicate": False, "request_id": identifier, "status": status, "actual_xu": actual, "charged_xu": charged, "refunded_xu": refunded, "uncollected_xu": uncollected, "provider_request_id": provider_id, "balance_xu": int(_wallet_balance(conn, str(request["owner_id"])) or 0), "is_admin": admin, "delivery": _decode_delivery(delivery)}


def refund_pro_request(conn: sqlite3.Connection, request_id: Any, *, reason: Any = "provider_failure", now: Any = None) -> dict[str, Any]:
    identifier, timestamp = _identity(request_id, "request_id"), _timestamp(now)
    _begin(conn)
    with _savepoint(conn):
        request = _by_id(conn, identifier)
        if not request or request["mode"] != "pro":
            return {"refunded": False, "duplicate": False, "unknown_request": True}
        if request["status"] != "reserved":
            return {"refunded": False, "duplicate": True, "request_id": identifier, "status": request["status"], "refunded_xu": int(request["refunded_xu"])}
        amount = 0 if request["is_admin"] else int(request["reserved_xu"])
        if amount and conn.execute("UPDATE users SET credits=credits+? WHERE CAST(user_id AS TEXT)=?", (amount, request["owner_id"])).rowcount != 1:
            raise RuntimeError("wallet row missing")
        conn.execute("UPDATE public_chat_requests SET status='refunded',refunded_xu=?,reason=?,updated_at=? WHERE request_id=?", (amount, str(reason)[:120], timestamp, identifier))
        return {"refunded": True, "duplicate": False, "request_id": identifier, "status": "refunded", "refunded_xu": amount, "balance_xu": int(_wallet_balance(conn, str(request["owner_id"])) or 0)}


def reconcile_stale_pro_reservations(
    conn: sqlite3.Connection,
    owner_id: Any,
    now: Any = None,
    reservation_ttl_seconds: int = DEFAULT_RESERVATION_TTL_SECONDS,
    batch_size: int = 200,
) -> list[dict]:
    owner, timestamp = _identity(owner_id, "owner_id"), _timestamp(now)
    ttl = max(30, min(int(reservation_ttl_seconds), 86_400))
    limit = max(1, min(int(batch_size), 1_000))
    refunds: list[dict[str, Any]] = []
    _begin(conn)
    with _savepoint(conn):
        rows = conn.execute(
            """SELECT request_id,is_admin,reserved_xu
               FROM public_chat_requests
               WHERE owner_id=? AND mode='pro' AND status='reserved' AND updated_at<?
               ORDER BY updated_at,request_id
               LIMIT ?""",
            (owner, timestamp - ttl, limit),
        ).fetchall()
        for request_id, is_admin, reserved_xu in rows:
            amount = 0 if is_admin else max(0, int(reserved_xu or 0))
            cursor = conn.execute(
                """UPDATE public_chat_requests
                   SET status='refunded',refunded_xu=?,reason='stale_reservation',updated_at=?
                   WHERE request_id=? AND owner_id=? AND mode='pro' AND status='reserved'""",
                (amount, timestamp, request_id, owner),
            )
            if cursor.rowcount != 1:
                continue
            if amount and conn.execute(
                "UPDATE users SET credits=credits+? WHERE CAST(user_id AS TEXT)=?",
                (amount, owner),
            ).rowcount != 1:
                raise RuntimeError("wallet row missing")
            refunds.append({"request_id": str(request_id), "refunded_xu": amount})
    return refunds


def load_public_context(conn: sqlite3.Connection, owner_id: Any, chat_id: Any, *, now: Any = None, max_turns: int = DEFAULT_CONTEXT_TURNS, character_budget: int = DEFAULT_CONTEXT_CHARACTERS) -> dict[str, Any]:
    ensure_schema(conn)
    owner, chat, timestamp = _identity(owner_id, "owner_id"), _identity(chat_id, "chat_id"), _timestamp(now)
    cutoff = timestamp - PUBLIC_CONTEXT_HOURS * 3600
    rows = conn.execute("SELECT session_id,role,mode,content,source_message_id,redaction_applied,created_at FROM public_chat_turns WHERE owner_id=? AND chat_id=? AND created_at>=? ORDER BY created_at DESC,id DESC LIMIT ?", (owner, chat, cutoff, max(1, min(int(max_turns), 100)))).fetchall()
    if not rows:
        return {"session_id": uuid.uuid4().hex, "turns": [], "history_text": ""}
    session_id = str(rows[0][0])
    selected, used = [], 0
    for row in rows:
        if str(row[0]) != session_id or used >= character_budget:
            continue
        content = str(row[3])[-(int(character_budget) - used):]
        selected.append({"role": str(row[1]), "mode": str(row[2]), "content": content, "source_message_id": str(row[4]), "redaction_applied": bool(row[5]), "created_at": float(row[6])})
        used += len(content)
    selected.reverse()
    return {"session_id": session_id, "turns": selected, "history_text": "\n".join(f"{item['role']}: {item['content']}" for item in selected)}


def load_pending_public_chat_delivery(
    conn: sqlite3.Connection,
    *,
    owner_id: Any,
    chat_id: Any,
    request_id: Any = None,
    now: Any = None,
) -> dict[str, Any] | None:
    ensure_schema(conn)
    owner, chat = _identity(owner_id, "owner_id"), _identity(chat_id, "chat_id")
    params: list[Any] = [owner, chat]
    request_clause = ""
    if request_id is not None:
        request_clause = " AND request_id=?"
        params.append(_identity(request_id, "request_id"))
    row = conn.execute(
        f"""SELECT request_id,source_message_id,result_json
            FROM public_chat_requests
            WHERE owner_id=? AND chat_id=?
              AND status IN ('consumed','settled') AND result_json<>''{request_clause}
            ORDER BY created_at,request_id LIMIT 1""",
        tuple(params),
    ).fetchone()
    if not row:
        return None
    payload = _decode_delivery(row[2])
    if payload is None:
        return None
    payload["request_id"] = str(row[0])
    payload["source_message_id"] = str(row[1])
    return payload


def advance_public_chat_delivery(
    conn: sqlite3.Connection,
    request_id: Any,
    *,
    next_cursor: Any,
    total_chunks: Any,
    now: Any = None,
) -> dict[str, Any]:
    identifier = _identity(request_id, "request_id")
    if isinstance(next_cursor, bool) or isinstance(total_chunks, bool):
        raise ValueError("delivery cursor must be an integer")
    cursor, total = int(next_cursor), int(total_chunks)
    if cursor < 0 or total < 1 or total > 100 or cursor > total:
        raise ValueError("delivery cursor is outside the allowed range")
    timestamp = _timestamp(now)
    _begin(conn)
    with _savepoint(conn):
        request = _by_id(conn, identifier)
        if not request or request["status"] not in {"consumed", "settled"}:
            return {"updated": False, "unknown_request": request is None}
        payload = _decode_delivery(request["result_json"])
        if payload is None:
            return {"updated": False, "delivered": True, "request_id": identifier}
        current = int(payload.get("delivery_cursor") or 0)
        known_total = payload.get("delivery_total_chunks")
        if known_total is not None and int(known_total) != total:
            return {"updated": False, "delivered": False, "request_id": identifier, "delivery_cursor": current, "reason": "total_chunks_mismatch"}
        if cursor != current + 1:
            return {"updated": False, "delivered": False, "request_id": identifier, "delivery_cursor": current, "reason": "cursor_gap"}
        if cursor >= total:
            conn.execute("UPDATE public_chat_requests SET result_json='',updated_at=? WHERE request_id=?", (timestamp, identifier))
            return {"updated": True, "delivered": True, "request_id": identifier, "delivery_cursor": total}
        payload["delivery_cursor"] = cursor
        payload["delivery_total_chunks"] = total
        conn.execute(
            "UPDATE public_chat_requests SET result_json=?,updated_at=? WHERE request_id=?",
            (json.dumps(payload, ensure_ascii=False, separators=(",", ":")), timestamp, identifier),
        )
        return {"updated": True, "delivered": False, "request_id": identifier, "delivery_cursor": cursor}


def purge_expired_public_turns(conn: sqlite3.Connection, *, now: Any = None, batch_size: int = 200) -> int:
    _begin(conn)
    cutoff = _timestamp(now) - PUBLIC_CONTEXT_HOURS * 3600
    cursor = conn.execute("DELETE FROM public_chat_turns WHERE id IN (SELECT id FROM public_chat_turns WHERE created_at<? ORDER BY created_at,id LIMIT ?)", (cutoff, max(1, min(int(batch_size), 1_000))))
    return max(0, int(cursor.rowcount or 0))


class PublicChatStore:
    """Connection-owning facade for provider/wallet dependency-injected runtimes."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        with self._connect() as conn:
            ensure_schema(conn)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    @staticmethod
    def _decode(value: str) -> dict[str, Any] | None:
        try:
            result = json.loads(value) if value else None
        except (TypeError, json.JSONDecodeError):
            return None
        return result if isinstance(result, dict) else None

    def reserve_free_request(self, account_id: Any, chat_id: Any, source_message_id: Any, *, quota_date: str | None = None, daily_limit: int = FREE_DAILY_LIMIT, is_admin: bool = False) -> RequestDecision:
        with self._connect() as conn:
            raw = reserve_free_request(conn, owner_id=account_id, chat_id=chat_id, source_message_id=source_message_id, quota_date=quota_date, daily_limit=daily_limit, is_admin=is_admin)
            row = _by_id(conn, raw["request_id"])
        if raw["accepted"]:
            status = "reserved"
        elif raw["exhausted"]:
            status = "quota_exhausted"
        else:
            status = "duplicate"
        return RequestDecision(status, raw["request_id"], bool(raw["accepted"]), bool(raw["duplicate"]), self._decode(str((row or {}).get("result_json") or "")))

    def free_usage_count(self, account_id: Any, quota_date: str) -> int:
        with self._connect() as conn:
            ensure_schema(conn)
            return _free_count(conn, str(account_id), str(quota_date))

    def finish_free(self, request_id: str, *, prompt: str, answer: str, result: Mapping[str, Any]) -> None:
        with self._connect() as conn:
            complete_free_request(conn, request_id, user_content=prompt, assistant_content=answer)
            conn.execute("UPDATE public_chat_requests SET result_json=? WHERE request_id=?", (json.dumps(dict(result), ensure_ascii=False, separators=(",", ":")), request_id))

    def fail_free(self, request_id: str, result: Mapping[str, Any], reason: str) -> None:
        with self._connect() as conn:
            release_request(conn, request_id, reason=reason)
            conn.execute("UPDATE public_chat_requests SET result_json=? WHERE request_id=?", (json.dumps(dict(result), ensure_ascii=False, separators=(",", ":")), request_id))

    def begin_pro(self, account_id: Any, chat_id: Any, source_message_id: Any, *, is_admin: bool = False) -> RequestDecision:
        owner, chat, source = _identity(account_id, "account_id"), _identity(chat_id, "chat_id"), _identity(source_message_id, "source_message_id")
        identifier, timestamp = _request_id(owner, chat, source), time.time()
        with self._connect() as conn:
            _begin(conn)
            existing = _by_identity(conn, owner, chat, source)
            if existing:
                return RequestDecision("duplicate", str(existing["request_id"]), False, True, self._decode(str(existing["result_json"])))
            conn.execute("INSERT INTO public_chat_requests(request_id,owner_id,chat_id,source_message_id,mode,session_id,status,is_admin,provider,model,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (identifier, owner, chat, source, "pro", _session(conn, owner, chat, timestamp), "preflight", int(is_admin), "key4u", OPUS_MODEL_ID, timestamp, timestamp))
        return RequestDecision("preflight", identifier, True, False, None)

    def mark_pro_reserved(self, request_id: str, reserved_xu: int, wallet_reservation_id: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE public_chat_requests SET status='reserved',reserved_xu=?,wallet_reservation_id=?,updated_at=? WHERE request_id=? AND status='preflight'", (int(reserved_xu), str(wallet_reservation_id), time.time(), request_id))

    def finish_pro(self, request_id: str, *, result: Mapping[str, Any], usage: OpusUsage, cost_xu: int, answer: str, prompt: str, provider_request_id: str = "") -> None:
        with self._connect() as conn:
            request = _by_id(conn, request_id)
            if request and request["status"] in {"reserved", "preflight"}:
                _insert_turns(conn, request, prompt, answer, time.time())
                conn.execute("UPDATE public_chat_requests SET status='settled',actual_xu=?,settled_xu=?,input_tokens=?,output_tokens=?,cache_read_tokens=?,provider_request_id=?,result_json=?,updated_at=? WHERE request_id=?", (int(cost_xu), int(cost_xu), usage.input_tokens, usage.output_tokens, usage.cache_read_tokens, str(provider_request_id), json.dumps(dict(result), ensure_ascii=False, separators=(",", ":")), time.time(), request_id))

    def fail_pro(self, request_id: str, *, result: Mapping[str, Any], reason: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE public_chat_requests SET status='refunded',reason=?,result_json=?,updated_at=? WHERE request_id=? AND status IN ('preflight','reserved')", (str(reason)[:120], json.dumps(dict(result), ensure_ascii=False, separators=(",", ":")), time.time(), request_id))


__all__ = [
    "DEFAULT_CONTEXT_CHARACTERS", "DEFAULT_CONTEXT_TURNS", "FREE_DAILY_LIMIT", "PUBLIC_CONTEXT_HOURS",
    "PublicChatStore", "RequestDecision", "complete_free_request", "ensure_schema", "free_quota_status",
    "advance_public_chat_delivery", "load_pending_public_chat_delivery", "load_public_context",
    "purge_expired_public_turns", "reconcile_stale_pro_reservations",
    "refund_pro_request", "release_request",
    "reserve_free_request", "reserve_pro_request", "sanitize_public_chat_content", "settle_pro_request",
    "vietnam_quota_date",
]
