from __future__ import annotations

import json
import os
import time
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx


BUSINESS_UPDATE_TYPES = (
    "business_connection",
    "business_message",
    "edited_business_message",
    "deleted_business_messages",
)
DEFAULT_MODE = "rules_only"
VALID_MODES = {"off", "rules_only", "rules_plus_ai_draft"}
DEFAULT_COOLDOWN_SECONDS = 60
STATE_VERSION = 1


@dataclass
class BusinessMessageEvent:
    update_type: str
    business_connection_id: str
    chat_id: str
    from_user_id: str
    from_is_bot: bool
    text: str
    caption: str
    message_id: str
    timestamp: float
    media_type: str
    is_edited: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def default_state_path() -> Path:
    configured = os.getenv("CSKH_BUSINESS_STATE_FILE", "").strip()
    return Path(configured) if configured else Path("data") / "cskh_business_state.json"


def default_knowledge_base_path() -> Path:
    configured = os.getenv("CSKH_KNOWLEDGE_BASE_FILE", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "config" / "cskh_knowledge_base.json"


def default_state() -> dict:
    return {
        "version": STATE_VERSION,
        "enabled": False,
        "mode": DEFAULT_MODE,
        "handoff_chats": {},
        "connections": {},
        "processed_messages": {},
        "deleted_messages": {},
        "last_auto_reply_at": {},
        "last_intent": {},
        "last_business_update_at": None,
        "last_business_message_at": None,
        "last_debug": {},
    }


def normalize_state(state: dict | None) -> dict:
    clean = default_state()
    if isinstance(state, dict):
        clean.update(state)
    clean["version"] = STATE_VERSION
    clean["enabled"] = bool(clean.get("enabled"))
    mode = str(clean.get("mode") or DEFAULT_MODE).strip()
    clean["mode"] = mode if mode in VALID_MODES - {"off"} else DEFAULT_MODE
    for key in (
        "handoff_chats",
        "connections",
        "processed_messages",
        "deleted_messages",
        "last_auto_reply_at",
        "last_intent",
        "last_debug",
    ):
        if not isinstance(clean.get(key), dict):
            clean[key] = {}
    return clean


def load_state(path: str | Path | None = None) -> dict:
    target = Path(path) if path else default_state_path()
    try:
        if target.exists():
            return normalize_state(json.loads(target.read_text(encoding="utf-8")))
    except Exception:
        return default_state()
    return default_state()


def save_state(state: dict, path: str | Path | None = None) -> dict:
    target = Path(path) if path else default_state_path()
    clean = normalize_state(state)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(target)
    return clean


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _timestamp(value: Any = None) -> float:
    if value is None:
        return time.time()
    if hasattr(value, "timestamp"):
        try:
            return float(value.timestamp())
        except Exception:
            return time.time()
    try:
        return float(value)
    except Exception:
        return time.time()


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFD", str(value or "").lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.replace("đ", "d").split())


def _media_type(message: Any) -> str:
    for attr in (
        "photo",
        "video",
        "animation",
        "audio",
        "voice",
        "video_note",
        "document",
        "sticker",
    ):
        if _get(message, attr):
            return attr
    return ""


def mask_business_connection_id(connection_id: str | None) -> str:
    raw = str(connection_id or "").strip()
    if not raw:
        return "-"
    if len(raw) <= 8:
        return raw[:2] + "..." + raw[-2:]
    return raw[:4] + "..." + raw[-4:]


def is_business_update(update: Any) -> bool:
    return any(bool(_get(update, name)) for name in BUSINESS_UPDATE_TYPES)


def business_message_key(event: BusinessMessageEvent | dict) -> str:
    payload = event.to_dict() if isinstance(event, BusinessMessageEvent) else dict(event or {})
    return ":".join(
        [
            str(payload.get("business_connection_id") or "-"),
            str(payload.get("chat_id") or "-"),
            str(payload.get("message_id") or "-"),
        ]
    )


def extract_business_message(update: Any, *, edited: bool = False) -> BusinessMessageEvent | None:
    update_type = "edited_business_message" if edited else "business_message"
    message = _get(update, update_type)
    if not message:
        return None
    chat = _get(message, "chat") or {}
    user = _get(message, "from_user") or _get(message, "from") or {}
    text = str(_get(message, "text") or "")
    caption = str(_get(message, "caption") or "")
    return BusinessMessageEvent(
        update_type=update_type,
        business_connection_id=str(_get(message, "business_connection_id") or ""),
        chat_id=str(_get(chat, "id") or _get(message, "chat_id") or ""),
        from_user_id=str(_get(user, "id") or ""),
        from_is_bot=bool(_get(user, "is_bot") or False),
        text=text,
        caption=caption,
        message_id=str(_get(message, "message_id") or ""),
        timestamp=_timestamp(_get(message, "date")),
        media_type=_media_type(message),
        is_edited=bool(edited),
    )


def extract_deleted_business_messages(update: Any) -> dict:
    deleted = _get(update, "deleted_business_messages") or {}
    chat = _get(deleted, "chat") or {}
    ids = _get(deleted, "message_ids") or []
    return {
        "business_connection_id": str(_get(deleted, "business_connection_id") or ""),
        "chat_id": str(_get(chat, "id") or _get(deleted, "chat_id") or ""),
        "message_ids": [str(item) for item in ids],
    }


def normalize_business_connection(connection: Any) -> dict:
    user = _get(connection, "user") or {}
    rights = _get(connection, "rights") or {}
    connection_id = str(_get(connection, "id") or _get(connection, "business_connection_id") or "")
    return {
        "id": connection_id,
        "masked_id": mask_business_connection_id(connection_id),
        "user_id": str(_get(user, "id") or ""),
        "username": str(_get(user, "username") or ""),
        "user_chat_id": str(_get(connection, "user_chat_id") or ""),
        "is_enabled": bool(_get(connection, "is_enabled", True)),
        "can_reply": bool(_get(rights, "can_reply") or _get(connection, "can_reply") or False),
        "updated_at": time.time(),
    }


def upsert_business_connection(state: dict, connection: Any) -> dict:
    clean = normalize_state(state)
    payload = normalize_business_connection(connection)
    if payload["id"]:
        clean["connections"][payload["id"]] = payload
    clean["last_business_update_at"] = time.time()
    return clean


def mark_deleted_business_messages(state: dict, deleted_payload: dict) -> dict:
    clean = normalize_state(state)
    bcid = str(deleted_payload.get("business_connection_id") or "")
    chat_id = str(deleted_payload.get("chat_id") or "")
    now = time.time()
    for message_id in deleted_payload.get("message_ids") or []:
        key = ":".join([bcid or "-", chat_id or "-", str(message_id or "-")])
        clean["deleted_messages"][key] = {"at": now}
    clean["last_business_update_at"] = now
    clean["last_debug"] = {
        "deleted_business_messages": len(deleted_payload.get("message_ids") or []),
        "reply_sent": False,
    }
    return clean


def record_business_message_received(state: dict, event: BusinessMessageEvent) -> dict:
    clean = normalize_state(state)
    now = time.time()
    clean["last_business_update_at"] = now
    clean["last_business_message_at"] = event.timestamp or now
    clean["last_message"] = {
        "business_connection_id_masked": mask_business_connection_id(event.business_connection_id),
        "chat_id": event.chat_id,
        "message_id": event.message_id,
        "media_type": event.media_type,
        "edited": event.is_edited,
        "at": event.timestamp or now,
    }
    return clean


def set_enabled(state: dict, enabled: bool) -> dict:
    clean = normalize_state(state)
    clean["enabled"] = bool(enabled)
    if clean["mode"] == "off":
        clean["mode"] = DEFAULT_MODE
    return clean


def set_mode(state: dict, mode: str) -> dict:
    clean = normalize_state(state)
    requested = str(mode or "").strip()
    if requested == "off":
        clean["enabled"] = False
    elif requested in VALID_MODES:
        clean["mode"] = requested
    return clean


def set_handoff(state: dict, chat_ref: str, enabled: bool, reason: str = "") -> dict:
    clean = normalize_state(state)
    key = str(chat_ref or "").strip()
    if not key:
        return clean
    if enabled:
        clean["handoff_chats"][key] = {
            "enabled": True,
            "reason": str(reason or "admin_handoff"),
            "updated_at": time.time(),
        }
    else:
        clean["handoff_chats"].pop(key, None)
    return clean


def handoff_required(state: dict, chat_id: str) -> bool:
    entry = normalize_state(state)["handoff_chats"].get(str(chat_id))
    return bool(entry and entry.get("enabled", True))


def load_knowledge_base(path: str | Path | None = None) -> dict:
    target = Path(path) if path else default_knowledge_base_path()
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {
            "version": 1,
            "intents": [
                {
                    "id": "out_of_scope",
                    "keywords": [],
                    "reply": "TOAN AAS đã nhận tin nhắn. Mình sẽ chuyển admin kiểm tra và phản hồi sớm.",
                    "handoff": True,
                }
            ],
        }


INTENT_PRIORITY = (
    "payment_issue",
    "refund",
    "technical_error",
    "admin_handoff",
    "pricing",
    "premium_private_bot",
    "greeting",
    "media_unknown",
    "out_of_scope",
)


def classify_cskh_message(text: str = "", *, media_type: str = "", kb: dict | None = None) -> dict:
    base = kb or load_knowledge_base()
    intents = list(base.get("intents") or [])
    query = _fold(text)
    if not query and media_type:
        query = "media file tep anh video audio"
    matches = []
    by_id = {str(item.get("id") or ""): item for item in intents}
    for item in intents:
        keywords = [_fold(keyword) for keyword in item.get("keywords") or []]
        if keywords and any(keyword and keyword in query for keyword in keywords):
            matches.append(item)
    if not matches and media_type and by_id.get("media_unknown"):
        matches = [by_id["media_unknown"]]
    if not matches:
        fallback = by_id.get("out_of_scope") or (intents[-1] if intents else {})
        matches = [fallback]
    selected = matches[0]
    matched_ids = {str(item.get("id") or "") for item in matches}
    for intent_id in INTENT_PRIORITY:
        if intent_id in matched_ids:
            selected = by_id[intent_id]
            break
    intent_id = str(selected.get("id") or "out_of_scope")
    reply = str(selected.get("reply") or "").strip()
    handoff = bool(selected.get("handoff"))
    return {
        "intent_id": intent_id,
        "reply": reply,
        "handoff": handoff,
        "ticket": bool(selected.get("ticket") or handoff),
        "confidence": "rules",
        "public_safe": public_reply_is_safe(reply),
    }


def classify_business_event(event: BusinessMessageEvent, kb: dict | None = None) -> dict:
    return classify_cskh_message(event.text or event.caption, media_type=event.media_type, kb=kb)


def public_reply_is_safe(reply: str) -> bool:
    folded = _fold(reply)
    forbidden = ("provider", "api", "env", "debug", "traceback", "endpoint", "secret", "internal")
    return not any(term in folded for term in forbidden)


def evaluate_auto_reply_guard(
    state: dict,
    event: BusinessMessageEvent,
    *,
    bot_user_id: str | int | None = None,
    now: float | None = None,
    cooldown_seconds: int | None = None,
) -> dict:
    clean = normalize_state(state)
    current = time.time() if now is None else float(now)
    cooldown = int(cooldown_seconds or os.getenv("CSKH_AUTO_REPLY_COOLDOWN_SECONDS") or DEFAULT_COOLDOWN_SECONDS)
    key = business_message_key(event)
    chat_id = str(event.chat_id or "")
    debug = {
        "allowed": True,
        "disabled_suppressed": False,
        "duplicate_suppressed": False,
        "cooldown_suppressed": False,
        "handoff_suppressed": False,
        "self_message_suppressed": False,
        "admin_manual_suppressed": False,
        "command_suppressed": False,
        "deleted_suppressed": False,
    }
    if not clean.get("enabled"):
        debug["disabled_suppressed"] = True
    if key in clean["processed_messages"]:
        debug["duplicate_suppressed"] = True
    if key in clean["deleted_messages"]:
        debug["deleted_suppressed"] = True
    if handoff_required(clean, chat_id):
        debug["handoff_suppressed"] = True
    if event.from_is_bot or (bot_user_id and str(event.from_user_id or "") == str(bot_user_id)):
        debug["self_message_suppressed"] = True
    connection = clean["connections"].get(str(event.business_connection_id or "")) or {}
    if event.from_user_id and str(event.from_user_id) == str(connection.get("user_id") or ""):
        debug["admin_manual_suppressed"] = True
    if str(event.text or event.caption or "").strip().startswith("/"):
        debug["command_suppressed"] = True
    last_reply = float(clean["last_auto_reply_at"].get(chat_id) or 0)
    if last_reply and current - last_reply < cooldown:
        debug["cooldown_suppressed"] = True
    debug["allowed"] = not any(value for key_name, value in debug.items() if key_name.endswith("_suppressed"))
    debug["message_key"] = key
    debug["cooldown_seconds"] = cooldown
    return debug


def record_auto_reply(state: dict, event: BusinessMessageEvent, classification: dict, send_result: dict | None = None) -> dict:
    clean = normalize_state(state)
    now = time.time()
    key = business_message_key(event)
    clean["processed_messages"][key] = {"at": now, "intent_id": classification.get("intent_id")}
    clean["last_auto_reply_at"][str(event.chat_id)] = now
    clean["last_intent"][str(event.chat_id)] = str(classification.get("intent_id") or "")
    clean["last_debug"] = {
        "classified_intent": classification.get("intent_id"),
        "reply_sent": True,
        "reply_method_business_connection_id_present": bool(
            (send_result or {}).get("payload", {}).get("business_connection_id")
        ),
    }
    _prune_dict(clean["processed_messages"], 500)
    return clean


def record_suppressed(state: dict, event: BusinessMessageEvent | None, classification: dict | None, guard: dict) -> dict:
    clean = normalize_state(state)
    clean["last_debug"] = {
        **dict(guard or {}),
        "classified_intent": (classification or {}).get("intent_id"),
        "reply_sent": False,
        "reply_method_business_connection_id_present": bool(event and event.business_connection_id),
    }
    if event and classification:
        clean["last_intent"][str(event.chat_id)] = str(classification.get("intent_id") or "")
    return clean


def _prune_dict(payload: dict, max_items: int) -> None:
    if len(payload) <= max_items:
        return
    sortable = sorted(payload.items(), key=lambda item: float((item[1] or {}).get("at") or 0))
    for key, _value in sortable[: max(0, len(payload) - max_items)]:
        payload.pop(key, None)


def allowed_updates_include_business(allowed_updates: Any) -> bool:
    updates = list(allowed_updates or [])
    return all(item in updates for item in BUSINESS_UPDATE_TYPES)


def status_payload(state: dict, *, bot_status: dict | None = None, allowed_updates: Any = None) -> dict:
    clean = normalize_state(state)
    connections = list(clean["connections"].values())
    latest = max(connections, key=lambda item: float(item.get("updated_at") or 0), default={})
    return {
        "enabled": bool(clean.get("enabled")),
        "bot_can_connect_to_business": (bot_status or {}).get("can_connect_to_business", "unknown"),
        "active_connection_count": len([item for item in connections if item.get("is_enabled", True)]),
        "latest_connection_id_masked": latest.get("masked_id") or "-",
        "allowed_updates_include_business": allowed_updates_include_business(allowed_updates),
        "auto_reply_mode": clean.get("mode") if clean.get("enabled") else "off",
        "handoff_count": len(clean["handoff_chats"]),
        "last_business_update_at": clean.get("last_business_update_at"),
        "last_business_message_at": clean.get("last_business_message_at"),
        "receiving_business_updates": bool(clean.get("last_business_update_at")),
        "receiving_business_messages": bool(clean.get("last_business_message_at")),
        "last_debug": dict(clean.get("last_debug") or {}),
    }


async def get_business_status(bot: Any) -> dict:
    try:
        me = await bot.get_me()
        return {
            "ok": True,
            "bot_id": str(_get(me, "id") or ""),
            "username": str(_get(me, "username") or ""),
            "can_connect_to_business": _get(me, "can_connect_to_business", None),
        }
    except Exception as exc:
        return {
            "ok": False,
            "bot_id": "",
            "username": "",
            "can_connect_to_business": "unknown",
            "error": type(exc).__name__,
        }


async def raw_bot_api_request(bot: Any, method: str, payload: dict) -> dict:
    if hasattr(bot, "raw_bot_api_request"):
        return await bot.raw_bot_api_request(method, payload)
    token = str(_get(bot, "token") or "").strip()
    if not token:
        raise RuntimeError("bot_token_unavailable_for_raw_business_send")
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(f"https://api.telegram.org/bot{token}/{method}", json=payload)
        response.raise_for_status()
        return response.json()


async def send_business_message(
    bot: Any,
    business_connection_id: str,
    chat_id: str | int,
    text: str,
    *,
    reply_to_message_id: str | int | None = None,
) -> dict:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "business_connection_id": business_connection_id,
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = int(reply_to_message_id)
        payload["allow_sending_without_reply"] = True
    try:
        message = await bot.send_message(**payload)
        return {"ok": True, "method": "ptb", "message": message, "payload": payload}
    except TypeError:
        raw = await raw_bot_api_request(bot, "sendMessage", payload)
        return {"ok": bool(raw.get("ok", True)), "method": "raw", "message": raw, "payload": payload}
