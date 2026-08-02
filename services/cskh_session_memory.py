"""Owner-isolated recent CSKH conversation storage.

This module intentionally owns only the authorised ``conversation_turns``
schema and pure SQLite operations. Telegram transport and runtime settings stay
in ``bot.py`` so storage never performs a provider call or customer send.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re
import sqlite3
import time
import uuid
from typing import Any, Mapping


DEFAULT_SESSION_WINDOW_HOURS = 48
DEFAULT_RETENTION_DAYS = 30
DEFAULT_RECENT_TURN_LIMIT = 12
DEFAULT_CHARACTER_BUDGET = 6000
MAX_STORED_CONTENT = 4000
ALLOWED_SURFACES = {"bot_menu", "cskh", "aichat"}
ALLOWED_ROLES = {"user", "assistant", "context_event"}
REDACTION_MARKER = "[đã ẩn thông tin nhạy cảm]"
CLOSING_NOTICE_DELAY_SECONDS = 5 * 60

_BEARER_PATTERN = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}\b", re.IGNORECASE)
_API_KEY_PATTERN = re.compile(
    r"\b(?:sk|rk|pk)[_-][A-Za-z0-9_-]{6,}\b|\b(?:AIza|ghp|xox[baprs])[-_A-Za-z0-9]{8,}\b",
    re.IGNORECASE,
)
_CREDENTIAL_ASSIGNMENT_PATTERN = re.compile(
    r"\b(?:api[_-]?key|token|secret|password|passwd|authorization)\s*[:=]\s*[^\s,;]{6,}",
    re.IGNORECASE,
)
_LONG_RANDOM_PATTERN = re.compile(r"\b[A-Za-z0-9_-]{32,}\b")
# Quoted paths are handled separately so spaces inside a Windows/UNC path are
# removed as one unit.  The unquoted forms intentionally stop at normal prose
# punctuation; they still consume every path component rather than only the
# drive/root prefix.
_QUOTED_PRIVATE_PATH_PATTERNS = (
    re.compile(
        r"(?P<quote>['\"])(?:[a-z]:[\\/][^'\"]+|\\\\[^'\"]+|/(?:etc|home|root|var|usr|opt|tmp|private)(?:/[^'\"]+)+)(?P=quote)",
        re.IGNORECASE,
    ),
)
_PRIVATE_PATH_PATTERNS = (
    re.compile(
        r"(?<![\w])(?:[a-z]:[\\/](?:[^<>:\"|?*\r\n,;!?)]*[\\/])+[^<>:\"|?*\r\n,;!?)]*)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?<![\w])(?:\\\\[^\\/\"'<>|?*;,!?]+(?:\\[^\\/\"'<>|?*;,!?]+)+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?<![\w])/(?:etc|home|root|var|usr|opt|tmp|private)(?:/[^\"'<>|?*;,!?)]*)+",
        re.IGNORECASE,
    ),
)
_CARD_CANDIDATE_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")

# Telegram message/update ids fit comfortably in ten decimal digits.  Keeping
# this narrow makes a raw card/account-looking number invalid as a source key.
_NUMERIC_SOURCE_PATTERN = re.compile(r"^(?:tg:)?\d{1,10}$")
_INTERNAL_SOURCE_PATTERN = re.compile(r"^(?:reply|context):(?:tg:)?\d{1,10}$")
_NOTICE_SOURCE_PATTERN = re.compile(r"^closing-(?:notice|claim):[0-9a-f]{32}$")
_SESSION_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_OPT_OUT_PATTERN = re.compile(
    r"(?:\b(?:đừng|dung|không|khong|ko)\s+(?:nhắc|nhac|gửi|gui|báo|bao)(?:\s+(?:lại|lai|nữa|nua))?\b|"
    r"\b(?:không|khong|ko)\s+cần\s+(?:nhắc|nhac|gửi|gui|báo|bao)\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TurnWrite:
    """Outcome of one idempotent turn write."""

    inserted: bool
    session_id: str
    content: str
    redacted: bool
    created_at: float


def _as_text(value: Any, *, maximum: int = 200) -> str:
    return str(value or "").strip()[:maximum]


def _as_timestamp(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return time.time()


def _bounded_positive_int(value: Any, default: int, *, minimum: int = 1, maximum: int = 100_000) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _safe_session_id(value: Any) -> str:
    candidate = _as_text(value, maximum=80).lower()
    return candidate if _SESSION_ID_PATTERN.fullmatch(candidate) else ""


def _safe_source_message_id(value: Any, *, allow_notice_marker: bool = True) -> str:
    """Accept only opaque update ids or service-generated keys.

    Telegram callback payloads and credential strings are deliberately not a
    supported source identity.  Callers must pass the numeric message/update
    id (or one of the narrow internal keys generated below).
    """
    source = _as_text(value, maximum=180)
    if not source or any(char.isspace() for char in source):
        return ""
    if _NUMERIC_SOURCE_PATTERN.fullmatch(source) or _INTERNAL_SOURCE_PATTERN.fullmatch(source):
        return source
    if allow_notice_marker and _NOTICE_SOURCE_PATTERN.fullmatch(source):
        return source
    return ""


def _valid_created_at(value: Any) -> float | None:
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    return timestamp if math.isfinite(timestamp) else None


def _valid_turn_row(row) -> dict | None:
    """Parse a row defensively; malformed legacy rows never enter context."""
    try:
        row_id = int(row[0])
        surface = str(row[1])
        role = str(row[2])
        content = row[3]
        source = str(row[4])
        redaction_applied = int(row[5])
        created_at = _valid_created_at(row[6])
    except (TypeError, ValueError, IndexError):
        return None
    if row_id <= 0 or surface not in ALLOWED_SURFACES or role not in ALLOWED_ROLES:
        return None
    if not isinstance(content, str) or not source or not _safe_source_message_id(source):
        return None
    if created_at is None or redaction_applied not in (0, 1):
        return None
    return {
        "id": row_id,
        "surface": surface,
        "role": role,
        "content": content,
        "source_message_id": source,
        "redaction_applied": bool(redaction_applied),
        "created_at": created_at,
    }


def ensure_schema(conn) -> None:
    """Create the single authorised table plus its two query indexes."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            telegram_user_id TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            surface TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            source_message_id TEXT NOT NULL,
            content_hash TEXT NOT NULL DEFAULT '',
            redaction_applied INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            UNIQUE (telegram_user_id, chat_id, role, source_message_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_conversation_turns_owner_chat_session_created
        ON conversation_turns (telegram_user_id, chat_id, session_id, created_at, id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_conversation_turns_created_at
        ON conversation_turns (created_at, id)
        """
    )


def _passes_luhn(digits: str) -> bool:
    if not 13 <= len(digits) <= 19 or not digits.isdigit():
        return False
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _replace_card_numbers(value: str) -> tuple[str, bool]:
    redacted = False

    def replace(match: re.Match) -> str:
        nonlocal redacted
        digits = re.sub(r"\D", "", match.group(0))
        if _passes_luhn(digits):
            redacted = True
            return REDACTION_MARKER
        return match.group(0)

    return _CARD_CANDIDATE_PATTERN.sub(replace, value), redacted


def _replace_long_random(value: str) -> tuple[str, bool]:
    redacted = False

    def replace(match: re.Match) -> str:
        nonlocal redacted
        candidate = match.group(0)
        has_lower = any(char.islower() for char in candidate)
        has_upper = any(char.isupper() for char in candidate)
        has_digit = any(char.isdigit() for char in candidate)
        if sum((has_lower, has_upper, has_digit)) >= 2:
            redacted = True
            return REDACTION_MARKER
        return candidate

    return _LONG_RANDOM_PATTERN.sub(replace, value), redacted


def sanitize_content(value: str) -> tuple[str, bool]:
    """Best-effort redact secrets before persistent storage.

    This is deliberately conservative: ordinary Vietnamese text, Xu prices and
    short public support codes remain readable. It is not a claim that arbitrary
    user text can be perfectly classified as secret.
    """
    clean = " ".join(str(value or "").replace("\x00", " ").split()).strip()
    redacted = False
    for pattern in (_BEARER_PATTERN, _API_KEY_PATTERN, _CREDENTIAL_ASSIGNMENT_PATTERN):
        clean, count = pattern.subn(REDACTION_MARKER, clean)
        redacted = redacted or bool(count)
    for pattern in (*_QUOTED_PRIVATE_PATH_PATTERNS, *_PRIVATE_PATH_PATTERNS):
        clean, count = pattern.subn(REDACTION_MARKER, clean)
        redacted = redacted or bool(count)
    clean, card_redacted = _replace_card_numbers(clean)
    clean, random_redacted = _replace_long_random(clean)
    redacted = redacted or card_redacted or random_redacted
    if len(clean) > MAX_STORED_CONTENT:
        clean = clean[:MAX_STORED_CONTENT].rstrip() + "…"
    return clean, redacted


def closing_notice_text(window_hours: int = DEFAULT_SESSION_WINDOW_HOURS) -> str:
    """Build a plain-language note without internal storage terminology."""
    hours = _bounded_positive_int(window_hours, DEFAULT_SESSION_WINDOW_HOURS, maximum=24 * 31)
    return (
        "Dạ em tạm chốt phần hỗ trợ tại đây nhé. "
        f"Nội dung mình trao đổi được giữ trong {hours} giờ để em nối tiếp khi anh/chị nhắn lại. "
        "Qua thời gian đó, nếu hỏi lại việc cũ hoặc có việc mới, anh/chị nhắc ngắn nội dung giúp em để em hỗ trợ đúng hơn ạ."
    )


def _latest_session(conn, owner_id: str, chat_id: str) -> tuple[str, float] | None:
    rows = conn.execute(
        """
        SELECT id, surface, role, content, source_message_id, redaction_applied, created_at, session_id
        FROM conversation_turns
        WHERE telegram_user_id=? AND chat_id=?
        ORDER BY created_at DESC, id DESC
        """,
        (owner_id, chat_id),
    ).fetchall()
    for row in rows:
        parsed = _valid_turn_row(row[:7])
        session = _safe_session_id(row[7]) if len(row) > 7 else ""
        if parsed and session and not parsed["source_message_id"].startswith("closing-claim:"):
            return session, parsed["created_at"]
    return None


def _session_for_write(
    conn,
    *,
    owner_id: str,
    chat_id: str,
    now: float,
    session_window_hours: int,
    requested_session_id: str = "",
) -> str:
    latest = _latest_session(conn, owner_id, chat_id)
    requested = _safe_session_id(requested_session_id)
    if requested and latest and latest[0] == requested:
        return requested
    if latest:
        session_id, last_at = latest
        if now >= last_at and now - last_at <= session_window_hours * 60 * 60:
            return session_id
    return uuid.uuid4().hex


def record_turn(
    conn,
    *,
    owner_id,
    chat_id,
    surface,
    role,
    content,
    source_message_id,
    now,
    session_window_hours: int = DEFAULT_SESSION_WINDOW_HOURS,
    session_id: str = "",
) -> TurnWrite:
    """Store one sanitized turn exactly once for its owner and chat."""
    owner = _as_text(owner_id)
    chat = _as_text(chat_id)
    clean_surface = _as_text(surface, maximum=40)
    clean_role = _as_text(role, maximum=40)
    source = _safe_source_message_id(source_message_id)
    if not owner or not chat or not source:
        if not source:
            raise ValueError("unsafe source_message_id")
        raise ValueError("owner_id, chat_id and source_message_id are required")
    if clean_surface not in ALLOWED_SURFACES:
        raise ValueError("unsupported conversation surface")
    if clean_role not in ALLOWED_ROLES:
        raise ValueError("unsupported conversation role")
    if clean_role == "assistant" and source.startswith("closing-notice:"):
        raise ValueError("closing notice requires a confirmed delivery claim")
    timestamp = _as_timestamp(now)
    window = _bounded_positive_int(session_window_hours, DEFAULT_SESSION_WINDOW_HOURS, maximum=24 * 31)
    selected_session = _session_for_write(
        conn,
        owner_id=owner,
        chat_id=chat,
        now=timestamp,
        session_window_hours=window,
        requested_session_id=session_id,
    )
    sanitized, redacted = sanitize_content(str(content or ""))
    digest = hashlib.sha256(sanitized.encode("utf-8")).hexdigest()
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO conversation_turns
        (session_id, telegram_user_id, chat_id, surface, role, content,
         source_message_id, content_hash, redaction_applied, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            selected_session,
            owner,
            chat,
            clean_surface,
            clean_role,
            sanitized,
            source,
            digest,
            int(redacted),
            timestamp,
        ),
    )
    inserted = cursor.rowcount == 1
    if not inserted:
        existing = conn.execute(
            """
            SELECT session_id, content, redaction_applied, created_at
            FROM conversation_turns
            WHERE telegram_user_id=? AND chat_id=? AND role=? AND source_message_id=?
            """,
            (owner, chat, clean_role, source),
        ).fetchone()
        if existing:
            return TurnWrite(
                inserted=False,
                session_id=str(existing[0]),
                content=str(existing[1]),
                redacted=bool(existing[2]),
                created_at=_as_timestamp(existing[3]),
            )
    return TurnWrite(
        inserted=inserted,
        session_id=selected_session,
        content=sanitized,
        redacted=redacted,
        created_at=timestamp,
    )


def load_recent_session(
    conn,
    *,
    owner_id,
    chat_id,
    now,
    session_window_hours: int = DEFAULT_SESSION_WINDOW_HOURS,
    recent_turn_limit: int = DEFAULT_RECENT_TURN_LIMIT,
    character_budget: int = DEFAULT_CHARACTER_BUDGET,
) -> dict:
    """Load only the active owner-scoped session as explicitly untrusted text."""
    owner = _as_text(owner_id)
    chat = _as_text(chat_id)
    timestamp = _as_timestamp(now)
    window = _bounded_positive_int(session_window_hours, DEFAULT_SESSION_WINDOW_HOURS, maximum=24 * 31)
    limit = _bounded_positive_int(recent_turn_limit, DEFAULT_RECENT_TURN_LIMIT, maximum=100)
    budget = _bounded_positive_int(character_budget, DEFAULT_CHARACTER_BUDGET, maximum=40_000)
    latest = _latest_session(conn, owner, chat) if owner and chat else None
    if not latest or timestamp < latest[1] or timestamp - latest[1] > window * 60 * 60:
        return {"session_id": "", "turns": [], "history_text": "", "truncated": False, "active": False}
    session_id, _last_at = latest
    rows = conn.execute(
        """
        SELECT id, surface, role, content, source_message_id, redaction_applied, created_at
        FROM conversation_turns
        WHERE telegram_user_id=? AND chat_id=? AND session_id=?
        ORDER BY created_at ASC, id ASC
        """,
        (owner, chat, session_id),
    ).fetchall()
    selected: list[dict] = []
    used = 0
    truncated = False
    for row in reversed(rows):
        turn = _valid_turn_row(row)
        if not turn:
            truncated = True
            continue
        if turn["source_message_id"].startswith("closing-claim:"):
            continue
        formatted = f"[UNTRUSTED {turn['role']}/{turn['surface']}] {turn['content']}"
        if len(selected) >= limit:
            truncated = True
            break
        if used + len(formatted) > budget:
            truncated = True
            if not selected:
                prefix = f"[UNTRUSTED {turn['role']}/{turn['surface']}] "
                available = max(0, budget - len(prefix) - 1)
                clipped = turn["content"][:available].rstrip()
                turn = {**turn, "content": f"{clipped}…"}
                selected.append(turn)
            break
        selected.append(turn)
        used += len(formatted)
    selected.reverse()
    history_text = "\n".join(f"[UNTRUSTED {turn['role']}/{turn['surface']}] {turn['content']}" for turn in selected)
    return {
        "session_id": session_id,
        "turns": [
            {"surface": turn["surface"], "role": turn["role"], "content": turn["content"]}
            for turn in selected
        ],
        "history_text": history_text,
        "truncated": truncated,
        "active": True,
    }


def purge_expired_turns(conn, *, now, retention_days: int = DEFAULT_RETENTION_DAYS, batch_size: int = 500) -> int:
    """Delete a bounded batch of raw turns beyond the configured retention."""
    timestamp = _as_timestamp(now)
    days = _bounded_positive_int(retention_days, DEFAULT_RETENTION_DAYS, minimum=0, maximum=3650)
    batch = _bounded_positive_int(batch_size, 500, maximum=5000)
    cutoff = timestamp - days * 24 * 60 * 60
    cursor = conn.execute(
        """
        DELETE FROM conversation_turns
        WHERE id IN (
            SELECT id FROM conversation_turns
            WHERE created_at < ?
            ORDER BY created_at ASC, id ASC
            LIMIT ?
        )
        """,
        (cutoff, batch),
    )
    return max(0, int(cursor.rowcount or 0))


def _closing_notice_marker(session_id: str) -> str:
    return f"closing-notice:{session_id}"


def _closing_claim_marker(session_id: str) -> str:
    return f"closing-claim:{session_id}"


def closing_notice_opted_out(conn, *, owner_id, chat_id, session_id) -> bool:
    """Honor a customer's plain-language request not to receive the note."""
    owner = _as_text(owner_id)
    chat = _as_text(chat_id)
    session = _safe_session_id(session_id)
    if not owner or not chat or not session:
        return True
    rows = conn.execute(
        """
        SELECT content
        FROM conversation_turns
        WHERE telegram_user_id=? AND chat_id=? AND session_id=? AND role='user'
        ORDER BY created_at ASC, id ASC
        """,
        (owner, chat, session),
    ).fetchall()
    return any(isinstance(row[0], str) and _OPT_OUT_PATTERN.search(row[0]) for row in rows)


def _latest_customer_turn(conn, *, owner_id: str, chat_id: str, session_id: str):
    rows = conn.execute(
        """
        SELECT id, surface, role, content, source_message_id, redaction_applied, created_at
        FROM conversation_turns
        WHERE telegram_user_id=? AND chat_id=? AND session_id=? AND role='user'
        ORDER BY created_at DESC, id DESC
        """,
        (owner_id, chat_id, session_id),
    ).fetchall()
    for row in rows:
        turn = _valid_turn_row(row)
        if turn and turn["role"] == "user":
            return turn["source_message_id"], turn["created_at"]
    return None


def _closing_marker_exists(conn, *, owner_id: str, chat_id: str, role: str, marker: str) -> bool:
    return bool(
        conn.execute(
            """
            SELECT 1
            FROM conversation_turns
            WHERE telegram_user_id=? AND chat_id=? AND role=? AND source_message_id=?
            LIMIT 1
            """,
            (owner_id, chat_id, role, marker),
        ).fetchone()
    )


def closing_notice_needed(
    conn,
    *,
    owner_id,
    chat_id,
    session_id,
    source_message_id,
    now,
    delay_seconds: int = CLOSING_NOTICE_DELAY_SECONDS,
    opt_out: bool = False,
) -> bool:
    """Return true only after 300 idle seconds for the latest customer turn.

    This is a pure eligibility check.  A caller must make an atomic durable
    claim before sending, then complete it only after confirmed transport
    success.
    """
    owner = _as_text(owner_id)
    chat = _as_text(chat_id)
    session = _safe_session_id(session_id)
    source = _safe_source_message_id(source_message_id, allow_notice_marker=False)
    timestamp = _valid_created_at(now)
    delay = _bounded_positive_int(delay_seconds, CLOSING_NOTICE_DELAY_SECONDS, minimum=0, maximum=24 * 60 * 60)
    if not owner or not chat or not session or not source or timestamp is None or opt_out:
        return False
    latest_user = _latest_customer_turn(conn, owner_id=owner, chat_id=chat, session_id=session)
    if not latest_user or latest_user[0] != source:
        return False
    latest_at = latest_user[1]
    if timestamp < latest_at or timestamp - latest_at < delay:
        return False
    if closing_notice_opted_out(conn, owner_id=owner, chat_id=chat, session_id=session):
        return False
    if _closing_marker_exists(
        conn,
        owner_id=owner,
        chat_id=chat,
        role="assistant",
        marker=_closing_notice_marker(session),
    ):
        return False
    return not _closing_marker_exists(
        conn,
        owner_id=owner,
        chat_id=chat,
        role="context_event",
        marker=_closing_claim_marker(session),
    )


def claim_closing_notice(
    conn,
    *,
    owner_id,
    chat_id,
    session_id,
    source_message_id,
    surface,
    now,
    delay_seconds: int = CLOSING_NOTICE_DELAY_SECONDS,
    opt_out: bool = False,
) -> bool:
    """Atomically reserve one notice send across surfaces and restarts.

    A claim is not customer-visible notice content.  It is removed for a known
    failed delivery and replaced by the final assistant turn only after a
    confirmed successful send.
    """
    owner = _as_text(owner_id)
    chat = _as_text(chat_id)
    session = _safe_session_id(session_id)
    clean_surface = _as_text(surface, maximum=40)
    timestamp = _valid_created_at(now)
    if clean_surface not in ALLOWED_SURFACES or timestamp is None:
        return False
    if not closing_notice_needed(
        conn,
        owner_id=owner,
        chat_id=chat,
        session_id=session,
        source_message_id=source_message_id,
        now=timestamp,
        delay_seconds=delay_seconds,
        opt_out=opt_out,
    ):
        return False
    marker = _closing_claim_marker(session)
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO conversation_turns
        (session_id, telegram_user_id, chat_id, surface, role, content,
         source_message_id, content_hash, redaction_applied, created_at)
        VALUES (?, ?, ?, ?, 'context_event', ?, ?, ?, 0, ?)
        """,
        (
            session,
            owner,
            chat,
            clean_surface,
            "closing notice delivery claim",
            marker,
            hashlib.sha256(marker.encode("utf-8")).hexdigest(),
            timestamp,
        ),
    )
    return cursor.rowcount == 1


def release_closing_notice_claim(conn, *, owner_id, chat_id, session_id) -> bool:
    """Remove only an unsent claim after a known failed/cancelled transport."""
    owner = _as_text(owner_id)
    chat = _as_text(chat_id)
    session = _safe_session_id(session_id)
    if not owner or not chat or not session:
        return False
    cursor = conn.execute(
        """
        DELETE FROM conversation_turns
        WHERE telegram_user_id=? AND chat_id=? AND role='context_event' AND source_message_id=?
        """,
        (owner, chat, _closing_claim_marker(session)),
    )
    return cursor.rowcount == 1


def notice_delivery_confirmed(value: Any) -> bool:
    """Accept only an explicit send confirmation, never ``None``/truthiness."""
    if value is True:
        return True
    if isinstance(value, Mapping):
        message_id = value.get("message_id")
    else:
        message_id = getattr(value, "message_id", None)
    return isinstance(message_id, int) and message_id > 0


def complete_closing_notice_claim(
    conn,
    *,
    owner_id,
    chat_id,
    session_id,
    surface,
    content,
    now,
    confirmed_success: bool = False,
) -> bool:
    """Persist the customer-visible note only after an explicit send success."""
    owner = _as_text(owner_id)
    chat = _as_text(chat_id)
    session = _safe_session_id(session_id)
    clean_surface = _as_text(surface, maximum=40)
    timestamp = _valid_created_at(now)
    if confirmed_success is not True or not owner or not chat or not session or clean_surface not in ALLOWED_SURFACES or timestamp is None:
        return False
    claim_marker = _closing_claim_marker(session)
    if not _closing_marker_exists(
        conn,
        owner_id=owner,
        chat_id=chat,
        role="context_event",
        marker=claim_marker,
    ):
        return False
    notice_marker = _closing_notice_marker(session)
    sanitized, redacted = sanitize_content(str(content or ""))
    if not sanitized:
        return False
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO conversation_turns
        (session_id, telegram_user_id, chat_id, surface, role, content,
         source_message_id, content_hash, redaction_applied, created_at)
        VALUES (?, ?, ?, ?, 'assistant', ?, ?, ?, ?, ?)
        """,
        (
            session,
            owner,
            chat,
            clean_surface,
            sanitized,
            notice_marker,
            hashlib.sha256(sanitized.encode("utf-8")).hexdigest(),
            int(redacted),
            timestamp,
        ),
    )
    # If a prior successful completion is already present, removing a residual
    # claim remains safe and avoids a later retry.  The send itself was already
    # made by the claimant, never by this data layer.
    if cursor.rowcount != 1 and not _closing_marker_exists(
        conn,
        owner_id=owner,
        chat_id=chat,
        role="assistant",
        marker=notice_marker,
    ):
        return False
    release_closing_notice_claim(conn, owner_id=owner, chat_id=chat, session_id=session)
    return True
