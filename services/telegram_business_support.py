from __future__ import annotations

import json
import hashlib
import html
import asyncio
import os
import re
import time
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

from services import aas_shared_knowledge


BUSINESS_UPDATE_TYPES = (
    "business_connection",
    "business_message",
    "edited_business_message",
    "deleted_business_messages",
)
DEFAULT_MODE = "rules_only"
VALID_MODES = {"off", "rules_only", "rules_plus_ai_draft"}
DEFAULT_COOLDOWN_SECONDS = 60
DEFAULT_CONVERSATION_TTL_SECONDS = 24 * 60 * 60
DEFAULT_MESSAGE_DEBOUNCE_SECONDS = 3
STATE_VERSION = 1
TRAINING_DATA_VERSION_FALLBACK = "0"
PLAYBOOK_VERSION_FALLBACK = "0"
CONVERSATION_MEMORY_LIMIT = 500
LEARNING_QUEUE_LIMIT = 200
BUSINESS_TRACE_LIMIT = 10
PUBLIC_FORBIDDEN_TERMS = (
    "provider",
    "api",
    "webhook",
    "worker",
    "traceback",
    "database",
    "internal error",
    "route",
    "parser",
    "debug",
    "stack",
    "exception",
    "raw payload",
    "task id provider",
    "token",
    "secret",
    "key",
    "endpoint",
)
UNSAFE_PROMISE_TERMS = (
    "da hoan tien",
    "da hoan xu",
    "da cong xu",
    "em da hoan",
    "em da cong",
    "chac chan hoan",
    "tu dong cong xu",
)
POLICY_CLAIM_TYPES = {
    "safe_public_fact",
    "config_priced_fact",
    "admin_action_required",
    "policy_confirm_required",
    "never_auto_promise",
}
TRUSTED_PRICING_SOURCES = {"config", "pricing_doc", "guide_doc", "context_file"}
URGENT_INTENTS = {
    "payment_xu_not_received",
    "payment_wrong_amount",
    "payment_duplicate",
    "payment_issue",
    "refund_request",
    "refund",
    "angry_scam_accusation",
    "product_video_stuck",
    "product_video_failed_no_file",
    "subdub_subtitle_error",
    "subdub_dubbing_error",
    "complaint_after_resolution",
    "public_negative_comment",
}
LEGACY_INTENT_ALIASES = {
    "payment_issue": "payment_issue",
    "refund": "refund",
    "technical_error": "technical_error",
    "admin_handoff": "admin_handoff",
    "pricing": "pricing",
    "premium_private_bot": "premium_private_bot",
    "greeting": "greeting",
    "media_unknown": "media_unknown",
    "out_of_scope": "out_of_scope",
}
_REPLY_VARIATION_COUNTER: dict[str, int] = {}


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
    update_id: str = ""
    from_username: str = ""
    sender_business_bot_id: str = ""
    sender_business_bot_username: str = ""
    via_bot_id: str = ""
    via_bot_username: str = ""
    reply_to_message_id: str = ""
    reply_to_from_user_id: str = ""
    reply_to_from_is_bot: bool = False
    reply_to_from_username: str = ""
    author_signature: str = ""
    is_from_offline: bool = False
    has_service_payload: bool = False
    direction_guess: str = "unknown"

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


def default_training_data_path() -> Path:
    configured = os.getenv("CSKH_TRAINING_DATA_FILE", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "config" / "cskh_training_data.json"


def default_playbook_path() -> Path:
    configured = os.getenv("CSKH_PLAYBOOK_FILE", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "config" / "cskh_playbook.json"


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
        "conversations": {},
        "message_buffers": {},
        "learning_queue": {},
        "last_business_update_at": None,
        "last_business_message_at": None,
        "last_debug": {},
        "business_trace": [],
        "last_business_message": {},
        "last_eligible_message": {},
        "last_ignored_message": {},
        "last_reply": {},
        "last_debounce_buffer_summary": {},
        "recent_message_keys": {},
        "replied_event_keys": {},
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
        "conversations",
        "message_buffers",
        "learning_queue",
        "last_debug",
        "last_business_message",
        "last_eligible_message",
        "last_ignored_message",
        "last_reply",
        "last_debounce_buffer_summary",
        "recent_message_keys",
        "replied_event_keys",
    ):
        if not isinstance(clean.get(key), dict):
            clean[key] = {}
    if not isinstance(clean.get("business_trace"), list):
        clean["business_trace"] = []
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


def _user_id(value: Any) -> str:
    return str(_get(value, "id") or "").strip()


def _username(value: Any) -> str:
    return str(_get(value, "username") or "").strip().lstrip("@").lower()


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


def _fold_contains(text: str, needle: str) -> bool:
    return bool(needle and needle in text)


def _clean_reply_text(reply: str, *, severity: str = "normal") -> str:
    clean = "\n".join(line.strip() for line in str(reply or "").splitlines()).strip()
    limit = 1200 if severity == "urgent" else 900
    if len(clean) > limit:
        clean = clean[: limit - 1].rstrip() + "…"
    return clean


def _intent_id(intent: dict) -> str:
    return str(intent.get("id") or intent.get("intent_id") or "").strip()


def _intent_templates(intent: dict) -> list[str]:
    templates = intent.get("reply_templates") or intent.get("safe_reply_templates") or []
    if isinstance(templates, str):
        templates = [templates]
    templates = [str(item).strip() for item in templates if str(item or "").strip()]
    single = str(intent.get("reply") or "").strip()
    if single and single not in templates:
        templates.append(single)
    return templates


PRICING_SIGNAL_TERMS = (
    "bang gia",
    "gia",
    "bao nhieu",
    "nhieu tien",
    "nhieu xu",
    "phi",
    "goi",
    "tien",
    "re nhat",
    "mien phi",
    "xu",
)


def _is_pricing_question(folded: str) -> bool:
    return any(term in folded for term in PRICING_SIGNAL_TERMS)


def _event_public_text(event: BusinessMessageEvent | None) -> str:
    if not event:
        return ""
    return str(event.text or event.caption or "").strip()


def _has_customer_text_signal(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    if re.fullmatch(r"[\?\s]{1,3}", raw):
        return True
    folded = _fold(raw)
    service_text = re.sub(r"[^a-z0-9]+", " ", folded).strip()
    service_compact = service_text.replace(" ", "")
    if service_text in {"dan nhan", "dan da nhan", "tin nhan moi", "new message"}:
        return False
    if service_text.endswith(" dan nhan") and len(service_text.split()) <= 4:
        return False
    if service_compact in {"dannhan", "dannhantin", "dnnhn"}:
        return False
    return bool(re.search(r"[0-9A-Za-zÀ-ỹ]", raw))


def business_event_has_meaningful_text(event: BusinessMessageEvent | None) -> bool:
    return bool(event and _has_customer_text_signal(_event_public_text(event)))


def business_event_has_actionable_media(event: BusinessMessageEvent | None) -> bool:
    media_type = _fold(event.media_type if event else "")
    return bool(event and media_type in aas_shared_knowledge.ACTIONABLE_MEDIA_TYPES and not event.has_service_payload)


def business_message_idempotency_key(event: BusinessMessageEvent | dict | None) -> str:
    payload = event.to_dict() if isinstance(event, BusinessMessageEvent) else dict(event or {})
    text = str(payload.get("text") or payload.get("caption") or "").strip()
    identity = str(payload.get("message_id") or "").strip()
    if not identity:
        identity = f"update:{payload.get('update_id') or '-'}"
    return ":".join(
        [
            "replied",
            str(payload.get("business_connection_id") or "-"),
            str(payload.get("chat_id") or "-"),
            identity or "-",
            _message_text_hash(text),
        ]
    )


def _same_username(left: str | None, right: str | None) -> bool:
    return bool(str(left or "").strip() and str(left or "").strip().lstrip("@").lower() == str(right or "").strip().lstrip("@").lower())


def business_event_self_or_outbound_reasons(
    event: BusinessMessageEvent | None,
    *,
    bot_user_id: str | int | None = None,
    bot_username: str | None = None,
    connection: dict | None = None,
) -> list[str]:
    if not event:
        return []
    bot_id = str(bot_user_id or "").strip()
    bot_name = str(bot_username or "").strip().lstrip("@").lower()
    connection_user_id = str((connection or {}).get("user_id") or "").strip()
    connection_username = str((connection or {}).get("username") or "").strip().lstrip("@").lower()
    reasons: list[str] = []
    if event.from_is_bot:
        reasons.append("from_is_bot")
    if bot_id and str(event.from_user_id or "") == bot_id:
        reasons.append("from_user_id_is_bot")
    if bot_name and _same_username(event.from_username, bot_name):
        reasons.append("from_username_is_bot")
    if event.sender_business_bot_id:
        reasons.append("sender_business_bot_present")
        if bot_id and str(event.sender_business_bot_id) == bot_id:
            reasons.append("sender_business_bot_id_is_bot")
    if bot_name and _same_username(event.sender_business_bot_username, bot_name):
        reasons.append("sender_business_bot_username_is_bot")
    if bot_id and str(event.via_bot_id or "") == bot_id:
        reasons.append("via_bot_id_is_bot")
    if bot_name and _same_username(event.via_bot_username, bot_name):
        reasons.append("via_bot_username_is_bot")
    if connection_user_id and str(event.from_user_id or "") == connection_user_id:
        reasons.append("from_user_id_is_business_owner")
    if connection_username and _same_username(event.from_username, connection_username):
        reasons.append("from_username_is_business_owner")
    if event.is_from_offline and (connection_user_id and str(event.from_user_id or "") == connection_user_id):
        reasons.append("offline_business_owner_message")
    return list(dict.fromkeys(reasons))


def business_event_direction_guess(
    event: BusinessMessageEvent | None,
    *,
    bot_user_id: str | int | None = None,
    bot_username: str | None = None,
    connection: dict | None = None,
) -> str:
    if not event:
        return "unknown"
    if business_event_self_or_outbound_reasons(
        event,
        bot_user_id=bot_user_id,
        bot_username=bot_username,
        connection=connection,
    ):
        return "outbound_or_self"
    if event.has_service_payload or (not business_event_has_meaningful_text(event) and not business_event_has_actionable_media(event)):
        return "non_text_or_service"
    if event.from_user_id:
        return "inbound_customer"
    return "unknown"


def _normalized_message_text(text: str) -> str:
    return _fold(_redact_sensitive_text(text))[:300]


def _message_text_hash(text: str) -> str:
    normalized = _normalized_message_text(text)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12] if normalized else "empty"


def _classification_intent_id(classification: dict | None) -> str:
    return str((classification or {}).get("intent_id") or (classification or {}).get("intent") or "unknown").strip() or "unknown"


def business_message_cooldown_key(event: BusinessMessageEvent, classification: dict | None = None) -> str:
    text = _event_public_text(event)
    return ":".join(
        [
            "cooldown",
            str(event.chat_id or "-"),
            _classification_intent_id(classification),
            _message_text_hash(text),
        ]
    )


def business_message_duplicate_key(event: BusinessMessageEvent, classification: dict | None = None) -> str:
    text = _event_public_text(event)
    return ":".join(
        [
            "duplicate",
            str(event.chat_id or "-"),
            str(event.from_user_id or "-"),
            _classification_intent_id(classification),
            _message_text_hash(text),
        ]
    )


def has_pricing_keyword(text: str) -> bool:
    return _is_pricing_question(_fold(text))


def _next_step_hint(intent: dict) -> str:
    steps = intent.get("safe_next_steps") or []
    if isinstance(steps, str):
        return steps
    return str(steps[0]) if steps else "Hỏi thêm thông tin còn thiếu"


def conversation_ttl_seconds() -> int:
    try:
        return max(60, int(os.getenv("CSKH_CONVERSATION_TTL_SECONDS") or DEFAULT_CONVERSATION_TTL_SECONDS))
    except Exception:
        return DEFAULT_CONVERSATION_TTL_SECONDS


def message_debounce_seconds() -> int:
    try:
        return max(1, min(10, int(os.getenv("CSKH_MESSAGE_DEBOUNCE_SECONDS") or DEFAULT_MESSAGE_DEBOUNCE_SECONDS)))
    except Exception:
        return DEFAULT_MESSAGE_DEBOUNCE_SECONDS


def _redact_sensitive_text(text: str) -> str:
    clean = str(text or "")
    clean = re.sub(
        r"(?i)\b(token|secret|api[_\s-]*key|password|mật khẩu|mat khau)\b\s*[:=]?\s*\S+",
        r"\1=[redacted]",
        clean,
    )
    clean = re.sub(r"\b\d{12,19}\b", "[redacted-number]", clean)
    return clean[:700]


def mask_chat_id(chat_id: str | int | None) -> str:
    raw = str(chat_id or "").strip()
    if not raw:
        return "-"
    if len(raw) <= 4:
        return raw[:1] + "..." + raw[-1:]
    return raw[:2] + "..." + raw[-2:]


def mask_user_id(user_id: str | int | None) -> str:
    raw = str(user_id or "").strip()
    if not raw:
        return "-"
    if len(raw) <= 4:
        return raw[:1] + "..." + raw[-1:]
    return raw[:2] + "..." + raw[-2:]


def _short_message_snapshot(event: BusinessMessageEvent | None, classification: dict | None = None) -> dict:
    text = _event_public_text(event)
    return {
        "update_type": str(event.update_type if event else ""),
        "chat_id_masked": mask_chat_id(event.chat_id if event else ""),
        "business_connection_id_masked": mask_business_connection_id(event.business_connection_id if event else ""),
        "from_user_id_masked": mask_user_id(event.from_user_id if event else ""),
        "from_is_bot": bool(event.from_is_bot if event else False),
        "message_id": str(event.message_id if event else ""),
        "direction_guess": str(event.direction_guess if event else "unknown"),
        "text": _redact_sensitive_text(text)[:180],
        "text_hash": _message_text_hash(text),
        "idempotency_key": business_message_idempotency_key(event) if event else "",
        "intent_id": _classification_intent_id(classification),
        "at": float(event.timestamp or time.time()) if event else time.time(),
    }


def _brain_path_for_classification(classification: dict | None) -> str:
    payload = classification or {}
    if payload.get("playbook_scenario_id") or payload.get("knowledge_entry_id") or payload.get("training_data_version"):
        return "cskh4_cskh6"
    if str(payload.get("intent_id") or "") == "out_of_scope":
        return "fallback"
    return "old_template"


def debounce_buffer_summary(state: dict, chat_id: str | int | None = None) -> dict:
    clean = normalize_state(state)
    buffers = clean.get("message_buffers") or {}
    selected = {}
    if chat_id is not None:
        selected = dict(buffers.get(str(chat_id)) or {})
    elif buffers:
        selected = dict(max(buffers.values(), key=lambda item: float((item or {}).get("last_at") or 0)))
    messages = list(selected.get("messages") or [])
    return {
        "chat_id_masked": mask_chat_id(selected.get("chat_id") or chat_id or ""),
        "count": len(messages),
        "texts": [_redact_sensitive_text(str(item.get("text") or ""))[:80] for item in messages[-5:]],
        "ready_at": selected.get("ready_at"),
    }


def _record_business_trace(
    state: dict,
    *,
    event: BusinessMessageEvent | None,
    classification: dict | None,
    replied: bool,
    block_reason: str = "",
    block_reason_detail: str = "",
    reply_preview: str = "",
    handler_path: str = "business_message",
    brain_path: str | None = None,
    cooldown_key: str = "",
    duplicate_key: str = "",
    idempotency_key: str = "",
    self_outbound_detection: str = "",
    eligible: bool = True,
) -> dict:
    clean = normalize_state(state)
    snapshot = _short_message_snapshot(event, classification)
    entry = {
        **snapshot,
        "eligible": bool(eligible),
        "replied": bool(replied),
        "block_reason": str(block_reason or ""),
        "block_reason_detail": str(block_reason_detail or ""),
        "reply_preview": _redact_sensitive_text(reply_preview)[:240],
        "handler_path": handler_path,
        "brain_path": brain_path or _brain_path_for_classification(classification),
        "cooldown_key": cooldown_key,
        "duplicate_key": duplicate_key,
        "idempotency_key": idempotency_key or snapshot.get("idempotency_key") or "",
        "self_outbound_detection": self_outbound_detection,
    }
    trace = list(clean.get("business_trace") or [])
    trace.append(entry)
    clean["business_trace"] = trace[-BUSINESS_TRACE_LIMIT:]
    clean["last_business_message"] = snapshot
    if eligible:
        clean["last_eligible_message"] = snapshot
    if replied:
        clean["last_reply"] = entry
    elif block_reason:
        clean["last_ignored_message"] = entry
    return clean


def prune_conversation_memory(state: dict, *, now: float | None = None, ttl_seconds: int | None = None) -> dict:
    if not isinstance(state, dict):
        return {}
    current = time.time() if now is None else float(now)
    ttl = int(ttl_seconds or conversation_ttl_seconds())
    conversations = state.get("conversations")
    if isinstance(conversations, dict):
        expired = []
        for chat_id, memory in conversations.items():
            if not isinstance(memory, dict):
                expired.append(chat_id)
                continue
            updated = float(memory.get("updated_at") or memory.get("last_reply_at") or 0)
            expires_at = float(memory.get("expires_at") or (updated + ttl if updated else 0))
            if expires_at and expires_at < current:
                expired.append(chat_id)
        for chat_id in expired:
            conversations.pop(chat_id, None)
        _prune_dict(conversations, CONVERSATION_MEMORY_LIMIT)
    buffers = state.get("message_buffers")
    if isinstance(buffers, dict):
        stale = []
        for chat_id, buffer in buffers.items():
            if not isinstance(buffer, dict):
                stale.append(chat_id)
                continue
            last_at = float(buffer.get("last_at") or 0)
            if last_at and current - last_at > max(60, ttl):
                stale.append(chat_id)
        for chat_id in stale:
            buffers.pop(chat_id, None)
    return state


def conversation_stage_for_intent(intent_id: str) -> str:
    intent = str(intent_id or "")
    if intent in {"greeting", "greeting_ping", "repeated_ping", "new_user_what_is_toan_aas"}:
        return "greeting"
    if intent in {
        "pricing",
        "pricing_general",
        "pricing_topup",
        "product_video_pricing",
        "image_ai_pricing",
        "image_to_video_pricing",
        "subdub_pricing",
        "subtitle_pricing",
        "dub_pricing",
        "voice_pricing",
        "music_pricing",
        "bot_private_pricing",
        "mixed_product_pricing",
        "unknown_pricing_product",
        "pricing_table_general",
    }:
        return "pricing"
    if intent in {"customer_confused_or_what", "vague_or_unclear", "out_of_scope", "product_video_consulting", "product_video_how_to"}:
        return "discovering_need"
    if intent in URGENT_INTENTS or intent.endswith("_error") or "stuck" in intent or "failed" in intent:
        return "troubleshooting"
    if intent in {"admin_handoff"}:
        return "handoff_pending"
    return "discovering_need"


def user_tone_for_text(text: str, *, repeated: bool = False) -> str:
    folded = _fold(text)
    if any(term in folded for term in ("lua dao", "scam", "boc phot", "kien", "buc", "chan", "khong tra loi")):
        return "angry"
    if repeated:
        return "repeated_ping"
    if any(term in folded for term in ("khong hieu", "sao vay", "bi gi", "lam sao", "ua")):
        return "confused"
    return "neutral"


def update_conversation_memory(
    state: dict,
    event: BusinessMessageEvent,
    classification: dict | None = None,
    *,
    reply: str = "",
    now: float | None = None,
    ttl_seconds: int | None = None,
) -> dict:
    clean = normalize_state(state)
    current = time.time() if now is None else float(now)
    ttl = int(ttl_seconds or conversation_ttl_seconds())
    chat_id = str(event.chat_id or "")
    if not chat_id:
        return clean
    conversations = clean["conversations"]
    memory = dict(conversations.get(chat_id) or {})
    messages = list(memory.get("last_messages") or [])
    text = _redact_sensitive_text(event.text or event.caption)
    if text:
        messages.append(
            {
                "message_id": str(event.message_id or ""),
                "text": text,
                "at": event.timestamp or current,
            }
        )
    messages = messages[-5:]
    bot_replies = list(memory.get("last_bot_replies") or [])
    if reply:
        bot_replies.append({"text": _redact_sensitive_text(reply), "at": current})
    bot_replies = bot_replies[-3:]
    intent_id = str((classification or {}).get("intent_id") or memory.get("last_intent") or "")
    product = str((classification or {}).get("product") or memory.get("last_product") or _infer_product(intent_id))
    topic = str(
        (classification or {}).get("previous_topic")
        or (classification or {}).get("last_product_type")
        or ("image" if product == "image_ai" else ("video" if product == "product_video" else product))
        or memory.get("previous_topic")
        or ""
    )
    last_subject = str(
        (classification or {}).get("last_subject")
        or (classification or {}).get("last_requested_asset")
        or memory.get("last_subject")
        or ""
    ).strip()
    generated_prompt = str(
        (classification or {}).get("last_generated_prompt")
        or (classification or {}).get("last_prompt")
        or memory.get("last_generated_prompt")
        or memory.get("last_prompt")
        or ""
    ).strip()
    missing = list((classification or {}).get("missing_fields") or memory.get("last_missing_fields") or [])
    repeated = bool(intent_id == "repeated_ping" or len([item for item in messages if _fold(item.get("text", "")) in {"alo", "hi", "hello", "co ai khong"}]) >= 2)
    unresolved = str(memory.get("unresolved_question") or "")
    if intent_id in {"vague_or_unclear", "out_of_scope", "repeated_ping"}:
        unresolved = text[:240]
    elif reply and intent_id:
        unresolved = ""
    conversations[chat_id] = {
        "chat_id": chat_id,
        "business_connection_id": str(event.business_connection_id or memory.get("business_connection_id") or ""),
        "business_connection_id_masked": mask_business_connection_id(event.business_connection_id or memory.get("business_connection_id") or ""),
        "last_messages": messages,
        "last_bot_replies": bot_replies,
        "previous_intent": memory.get("last_intent") or memory.get("previous_intent") or "",
        "previous_topic": topic or memory.get("previous_topic") or "",
        "last_intent": intent_id,
        "last_product": product,
        "last_product_type": topic or product,
        "last_requested_asset": str((classification or {}).get("last_requested_asset") or last_subject or memory.get("last_requested_asset") or ""),
        "last_subject": last_subject,
        "last_flow_suggestion": str((classification or {}).get("last_flow_suggestion") or memory.get("last_flow_suggestion") or ""),
        "last_prompt": generated_prompt,
        "last_generated_prompt": generated_prompt,
        "last_offered_action": str((classification or {}).get("last_offered_action") or memory.get("last_offered_action") or ""),
        "last_flow": str((classification or {}).get("last_flow") or memory.get("last_flow") or ""),
        "last_action_button": str((classification or {}).get("last_action_button") or memory.get("last_action_button") or ""),
        "last_missing_fields": missing,
        "last_ticket_required": bool((classification or {}).get("ticket_required", memory.get("last_ticket_required", False))),
        "last_handoff_required": bool((classification or {}).get("handoff_required", memory.get("last_handoff_required", False))),
        "last_reply_at": current if reply else float(memory.get("last_reply_at") or 0),
        "unresolved_question": unresolved,
        "user_tone": user_tone_for_text(text, repeated=repeated),
        "conversation_stage": conversation_stage_for_intent(intent_id),
        "updated_at": current,
        "expires_at": current + ttl,
    }
    prune_conversation_memory(clean, now=current, ttl_seconds=ttl)
    return clean


def get_conversation_memory(state: dict, chat_id: str | int, *, now: float | None = None, ttl_seconds: int | None = None) -> dict:
    clean = normalize_state(state)
    prune_conversation_memory(clean, now=now, ttl_seconds=ttl_seconds)
    return dict(clean["conversations"].get(str(chat_id)) or {})


def append_message_buffer(
    state: dict,
    event: BusinessMessageEvent,
    *,
    now: float | None = None,
    debounce_seconds: int | None = None,
) -> dict:
    clean = normalize_state(state)
    current = time.time() if now is None else float(now)
    debounce = int(debounce_seconds or message_debounce_seconds())
    chat_id = str(event.chat_id or "")
    if not chat_id:
        return clean
    existing = dict(clean["message_buffers"].get(chat_id) or {})
    messages = list(existing.get("messages") or [])
    messages.append(
        {
            "business_connection_id": str(event.business_connection_id or ""),
            "chat_id": chat_id,
            "from_user_id": str(event.from_user_id or ""),
            "from_username": str(event.from_username or ""),
            "message_id": str(event.message_id or ""),
            "update_id": str(event.update_id or ""),
            "text": _redact_sensitive_text(event.text or event.caption),
            "media_type": str(event.media_type or ""),
            "at": event.timestamp or current,
        }
    )
    messages = messages[-5:]
    clean["message_buffers"][chat_id] = {
        "chat_id": chat_id,
        "business_connection_id": str(event.business_connection_id or existing.get("business_connection_id") or ""),
        "from_user_id": str(event.from_user_id or existing.get("from_user_id") or ""),
        "from_username": str(event.from_username or existing.get("from_username") or ""),
        "first_at": float(existing.get("first_at") or current),
        "last_at": current,
        "ready_at": current + debounce,
        "messages": messages,
    }
    return clean


def message_buffer_ready(state: dict, chat_id: str | int, *, now: float | None = None) -> bool:
    clean = normalize_state(state)
    buffer = clean["message_buffers"].get(str(chat_id)) or {}
    if not buffer:
        return False
    current = time.time() if now is None else float(now)
    return current >= float(buffer.get("ready_at") or 0)


def pop_message_buffer(
    state: dict,
    chat_id: str | int,
    *,
    now: float | None = None,
    force: bool = False,
) -> tuple[dict, dict]:
    clean = normalize_state(state)
    key = str(chat_id or "")
    buffer = dict(clean["message_buffers"].get(key) or {})
    if not buffer:
        return clean, {}
    if not force and not message_buffer_ready(clean, key, now=now):
        return clean, {}
    clean["message_buffers"].pop(key, None)
    return clean, buffer


def combined_text_from_buffer(buffer: dict) -> str:
    parts = []
    for item in buffer.get("messages") or []:
        text = str(item.get("text") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def event_from_buffer(buffer: dict) -> BusinessMessageEvent | None:
    messages = list(buffer.get("messages") or [])
    if not messages:
        return None
    last = messages[-1]
    return BusinessMessageEvent(
        update_type="business_message",
        business_connection_id=str(buffer.get("business_connection_id") or last.get("business_connection_id") or ""),
        chat_id=str(buffer.get("chat_id") or last.get("chat_id") or ""),
        from_user_id=str(buffer.get("from_user_id") or last.get("from_user_id") or ""),
        from_is_bot=False,
        text=combined_text_from_buffer(buffer),
        caption="",
        message_id=str(last.get("message_id") or ""),
        timestamp=float(last.get("at") or time.time()),
        media_type=str(last.get("media_type") or ""),
        update_id=str(last.get("update_id") or ""),
        from_username=str(buffer.get("from_username") or last.get("from_username") or ""),
    )


def should_debounce_message(state: dict, event: BusinessMessageEvent, classification: dict, *, now: float | None = None) -> bool:
    clean = normalize_state(state)
    if event.is_edited or event.media_type:
        return False
    if str(classification.get("severity") or "") == "urgent":
        return False
    chat_id = str(event.chat_id or "")
    if chat_id and clean["message_buffers"].get(chat_id):
        return True
    folded = _fold(event.text or event.caption)
    intent_id = str(classification.get("intent_id") or "")
    if intent_id in {"greeting", "greeting_ping", "repeated_ping"}:
        return True
    if len(folded.split()) <= 4 and not any(term in folded for term in ("gia", "bao nhieu", "xu", "video", "nap", "loi")):
        return True
    return False


def classify_thread_messages(messages: list[str], *, variation_seed: str | int | None = None) -> dict:
    cleaned = [str(item or "").strip() for item in messages if str(item or "").strip()]
    combined = "\n".join(cleaned)
    result = classify_cskh_message(combined, variation_seed=variation_seed or combined)
    result["combined_text"] = combined
    result["buffered"] = len(cleaned) > 1
    result["conversation_stage"] = conversation_stage_for_intent(str(result.get("intent_id") or ""))
    result["would_queue_learning"] = should_queue_learning(result, combined)
    return result


def should_queue_learning(classification: dict, text: str = "") -> bool:
    intent_id = str(classification.get("intent_id") or "")
    confidence = str(classification.get("confidence") or "")
    folded = _fold(text)
    if confidence == "low":
        return True
    if _is_pricing_question(folded) and not classification.get("primary_product"):
        return True
    if intent_id in {"out_of_scope", "vague_or_unclear"}:
        return True
    if intent_id == "repeated_ping" and any(term in folded for term in ("khong tra loi", "sao khong", "co ai khong")):
        return True
    if any(term in folded for term in ("khong dung", "khong hieu", "tra loi sai", "khong huu ich", "bot ngu")):
        return True
    return False


def is_distinct_followup_question(event: BusinessMessageEvent) -> bool:
    folded = _fold(event.text or event.caption)
    if not folded:
        return False
    if has_pricing_keyword(event.text or event.caption):
        return True
    signals = (
        "bang gia",
        "gia",
        "bao nhieu",
        "nhieu xu",
        "phi",
        "goi",
        "tien",
        "re nhat",
        "mien phi",
        "xu",
        "video",
        "nap",
        "loi",
        "khong duoc",
        "ho tro",
        "subdub",
        "nhac",
        "voice",
        "anh",
        "bot rieng",
    )
    return "?" in str(event.text or event.caption or "") or any(term in folded for term in signals)


def learning_reason(classification: dict, text: str = "") -> str:
    if str(classification.get("confidence") or "") == "low":
        return "low_confidence"
    intent_id = str(classification.get("intent_id") or "")
    if intent_id in {"out_of_scope", "vague_or_unclear"}:
        return "unclear_or_unanswered"
    if intent_id == "repeated_ping":
        return "repeated_ping"
    if any(term in _fold(text) for term in ("khong dung", "khong hieu", "tra loi sai", "khong huu ich", "bot ngu")):
        return "customer_said_not_helpful"
    return "review"


def _learning_detected_keywords(text: str, classification: dict) -> list[str]:
    existing = list(classification.get("matched_aliases") or classification.get("matched_keyword_groups") or [])
    folded = _fold(text)
    signals = (
        "video",
        "anh",
        "hinh",
        "ghep anh",
        "phu de",
        "long tieng",
        "nhac",
        "voice",
        "bot rieng",
        "nap",
        "xu",
        "gia",
        "bao nhieu",
        "combo",
        "loai kia",
        "mau nay",
    )
    combined = existing + [term for term in signals if term in folded]
    deduped: list[str] = []
    for term in combined:
        if term and term not in deduped:
            deduped.append(term)
    return deduped[:10]


def add_learning_candidate(
    state: dict,
    event: BusinessMessageEvent | None,
    classification: dict,
    *,
    text: str = "",
    reply_sent: str = "",
    reason: str = "",
    now: float | None = None,
) -> tuple[dict, dict]:
    clean = normalize_state(state)
    current = time.time() if now is None else float(now)
    source_text = text or (event.text if event else "") or (event.caption if event else "")
    digest = hashlib.sha1(f"{source_text}:{current}:{(event.chat_id if event else '')}".encode("utf-8")).hexdigest()[:10]
    candidate_id = f"learn-{digest}"
    candidate = {
        "id": candidate_id,
        "customer_message": _redact_sensitive_text(source_text),
        "chat_id_masked": mask_chat_id(event.chat_id if event else ""),
        "business_connection_id_masked": mask_business_connection_id(event.business_connection_id if event else ""),
        "detected_intent": str(classification.get("intent_id") or "out_of_scope"),
        "confidence": str(classification.get("confidence") or ""),
        "detected_keywords": _learning_detected_keywords(source_text, classification),
        "suggested_product": str(classification.get("primary_product") or classification.get("product") or ""),
        "reply_sent": _redact_sensitive_text(reply_sent or classification.get("reply") or classification.get("reply_preview") or ""),
        "why_queued": reason or learning_reason(classification, source_text),
        "suggested_better_intent": str(classification.get("suggested_better_intent") or ""),
        "status": "open",
        "created_at": current,
        "updated_at": current,
    }
    clean["learning_queue"][candidate_id] = candidate
    _prune_dict(clean["learning_queue"], LEARNING_QUEUE_LIMIT)
    return clean, candidate


def list_learning_candidates(state: dict, *, status: str = "open", limit: int = 10) -> list[dict]:
    clean = normalize_state(state)
    rows = [dict(item) for item in clean["learning_queue"].values() if not status or str(item.get("status") or "") == status]
    rows.sort(key=lambda item: float(item.get("created_at") or 0), reverse=True)
    return rows[: max(1, int(limit or 10))]


def get_learning_candidate(state: dict, candidate_id: str) -> dict:
    clean = normalize_state(state)
    return dict(clean["learning_queue"].get(str(candidate_id or "").strip()) or {})


def mark_learning_candidate(state: dict, candidate_id: str, status: str, *, now: float | None = None) -> tuple[dict, bool]:
    clean = normalize_state(state)
    key = str(candidate_id or "").strip()
    if key not in clean["learning_queue"]:
        return clean, False
    clean["learning_queue"][key]["status"] = str(status or "resolved").strip() or "resolved"
    clean["learning_queue"][key]["updated_at"] = time.time() if now is None else float(now)
    return clean, True


def thread_preview_text(messages: list[str], classification: dict) -> str:
    combined = str(classification.get("combined_text") or "\n".join(messages))
    return (
        "🧪 <b>CSKH thread test</b>\n\n"
        f"Buffered: <code>{'yes' if classification.get('buffered') else 'no'}</code>\n"
        f"Combined text:\n<code>{html.escape(combined[:1000])}</code>\n\n"
        f"Intent: <code>{html.escape(str(classification.get('intent_id') or '-'))}</code>\n"
        f"Primary product: <code>{html.escape(str(classification.get('primary_product') or '-'))}</code>\n"
        f"Secondary products: <code>{html.escape(', '.join(map(str, classification.get('secondary_products') or [])) or '-')}</code>\n"
        f"Mixed intent: <code>{'yes' if classification.get('mixed_intent') else 'no'}</code>\n"
        f"Pricing source: <code>{html.escape(str(classification.get('pricing_source') or '-'))}</code>\n"
        f"Matched aliases: <code>{html.escape(', '.join(map(str, classification.get('matched_aliases') or [])) or '-')}</code>\n"
        f"Knowledge entry: <code>{html.escape(str(classification.get('knowledge_entry_id') or '-'))}</code>\n"
        f"Next question: <code>{html.escape(str(classification.get('next_question') or '-'))}</code>\n"
        f"Confidence: <code>{html.escape(str(classification.get('confidence') or '-'))}</code>\n"
        f"Severity: <code>{html.escape(str(classification.get('severity') or '-'))}</code>\n"
        f"Conversation stage: <code>{html.escape(str(classification.get('conversation_stage') or '-'))}</code>\n"
        f"Would queue learning: <code>{'yes' if classification.get('would_queue_learning') else 'no'}</code>\n\n"
        f"Reply preview:\n{html.escape(str(classification.get('reply_preview') or classification.get('reply') or '')[:1200])}"
    )


def learning_queue_text(state: dict) -> str:
    rows = list_learning_candidates(state, limit=10)
    lines = ["🧠 <b>CSKH learning queue</b>", "", "Auto-learning: <code>off / admin review only</code>"]
    if not rows:
        lines.append("Chưa có case cần review.")
        return "\n".join(lines)
    for item in rows:
        lines.append(
            f"• <code>{html.escape(str(item.get('id') or '-'))}</code> "
            f"| intent=<code>{html.escape(str(item.get('detected_intent') or '-'))}</code> "
            f"| chat=<code>{html.escape(str(item.get('chat_id_masked') or '-'))}</code> "
            f"| reason=<code>{html.escape(str(item.get('why_queued') or '-'))}</code>"
        )
    return "\n".join(lines)


def learning_show_text(item: dict) -> str:
    if not item:
        return "\n".join(["🧠 <b>CSKH learning item</b>", "", "Không tìm thấy case."])
    lines = [
        "🧠 <b>CSKH learning item</b>",
        "",
        f"ID: <code>{html.escape(str(item.get('id') or '-'))}</code>",
        f"Status: <code>{html.escape(str(item.get('status') or '-'))}</code>",
        f"Chat: <code>{html.escape(str(item.get('chat_id_masked') or '-'))}</code>",
        f"Intent: <code>{html.escape(str(item.get('detected_intent') or '-'))}</code>",
        f"Confidence: <code>{html.escape(str(item.get('confidence') or '-'))}</code>",
        f"Why queued: <code>{html.escape(str(item.get('why_queued') or '-'))}</code>",
        "",
        f"Customer:\n<code>{html.escape(str(item.get('customer_message') or '-')[:1200])}</code>",
        "",
        f"Reply sent:\n<code>{html.escape(str(item.get('reply_sent') or '-')[:1200])}</code>",
    ]
    return "\n".join(lines)


def _training_fallback() -> dict:
    return {
        "version": TRAINING_DATA_VERSION_FALLBACK,
        "brand": "TOAN AAS",
        "language": "vi",
        "forbidden_phrases": [],
        "preferred_phrases": [],
        "ticket_fields": {},
        "intents": [],
        "conversation_scenarios": [],
    }


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


def _has_service_payload(message: Any) -> bool:
    for attr in (
        "new_chat_members",
        "left_chat_member",
        "new_chat_title",
        "new_chat_photo",
        "delete_chat_photo",
        "group_chat_created",
        "supergroup_chat_created",
        "channel_chat_created",
        "message_auto_delete_timer_changed",
        "forum_topic_created",
        "forum_topic_edited",
        "forum_topic_closed",
        "forum_topic_reopened",
        "general_forum_topic_hidden",
        "general_forum_topic_unhidden",
        "pinned_message",
        "proximity_alert_triggered",
        "video_chat_scheduled",
        "video_chat_started",
        "video_chat_ended",
        "video_chat_participants_invited",
        "web_app_data",
        "contact",
        "location",
        "venue",
        "poll",
        "dice",
        "game",
        "invoice",
        "successful_payment",
    ):
        if _get(message, attr):
            return True
    return False


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
    sender_business_bot = _get(message, "sender_business_bot") or {}
    via_bot = _get(message, "via_bot") or {}
    reply_to_message = _get(message, "reply_to_message") or {}
    reply_to_user = _get(reply_to_message, "from_user") or _get(reply_to_message, "from") or {}
    text = str(_get(message, "text") or "")
    caption = str(_get(message, "caption") or "")
    return BusinessMessageEvent(
        update_type=update_type,
        business_connection_id=str(_get(message, "business_connection_id") or ""),
        chat_id=str(_get(chat, "id") or _get(message, "chat_id") or ""),
        from_user_id=_user_id(user),
        from_is_bot=bool(_get(user, "is_bot") or False),
        text=text,
        caption=caption,
        message_id=str(_get(message, "message_id") or ""),
        timestamp=_timestamp(_get(message, "date")),
        media_type=_media_type(message),
        is_edited=bool(edited),
        update_id=str(_get(update, "update_id") or ""),
        from_username=_username(user),
        sender_business_bot_id=_user_id(sender_business_bot),
        sender_business_bot_username=_username(sender_business_bot),
        via_bot_id=_user_id(via_bot),
        via_bot_username=_username(via_bot),
        reply_to_message_id=str(_get(reply_to_message, "message_id") or ""),
        reply_to_from_user_id=_user_id(reply_to_user),
        reply_to_from_is_bot=bool(_get(reply_to_user, "is_bot") or False),
        reply_to_from_username=_username(reply_to_user),
        author_signature=str(_get(message, "author_signature") or ""),
        is_from_offline=bool(_get(message, "is_from_offline") or _get(message, "from_offline") or False),
        has_service_payload=_has_service_payload(message),
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


def upsert_business_connection_from_message(state: dict, event: BusinessMessageEvent) -> dict:
    clean = normalize_state(state)
    connection_id = str(event.business_connection_id or "").strip()
    if not connection_id:
        clean["last_debug"] = {
            **dict(clean.get("last_debug") or {}),
            "missing_business_connection_id": True,
            "reply_sent": False,
        }
        return clean
    now = time.time()
    existing = dict(clean["connections"].get(connection_id) or {})
    payload = {
        "id": connection_id,
        "masked_id": mask_business_connection_id(connection_id),
        "user_id": str(existing.get("user_id") or ""),
        "username": str(existing.get("username") or ""),
        "user_chat_id": str(existing.get("user_chat_id") or ""),
        "is_enabled": bool(existing.get("is_enabled", True)),
        "can_reply": bool(existing.get("can_reply", True)),
        "updated_at": now,
        "source": existing.get("source") or "business_message",
        "last_chat_id": str(event.chat_id or ""),
        "last_message_id": str(event.message_id or ""),
        "last_message_at": event.timestamp or now,
    }
    clean["connections"][connection_id] = payload
    clean["last_business_update_at"] = now
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


def has_active_business_connection(state: dict) -> bool:
    clean = normalize_state(state)
    return any(bool(item.get("is_enabled", True)) for item in clean["connections"].values())


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


def load_training_data(path: str | Path | None = None) -> dict:
    target = Path(path) if path else default_training_data_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        data = _training_fallback()
    clean = _training_fallback()
    if isinstance(data, dict):
        clean.update(data)
    clean["version"] = str(clean.get("version") or TRAINING_DATA_VERSION_FALLBACK)
    clean["intents"] = [item for item in clean.get("intents") or [] if isinstance(item, dict) and _intent_id(item)]
    clean["conversation_scenarios"] = [item for item in clean.get("conversation_scenarios") or [] if isinstance(item, dict)]
    return clean


def _playbook_fallback() -> dict:
    return {
        "version": PLAYBOOK_VERSION_FALLBACK,
        "raw_script_auto_ingest": False,
        "response_framework": {
            "steps": ["acknowledge", "mirror", "verified_answer", "next_action", "handoff_if_needed"],
            "default_max_sentences": 5,
        },
        "policy_claim_categories": {claim: {"auto_reply": claim in {"safe_public_fact", "config_priced_fact"}} for claim in POLICY_CLAIM_TYPES},
        "reply_slots": {
            "quote_before_confirm_text": "Em sẽ báo đúng gói/Xu trước khi mình xác nhận.",
            "handoff_line": "Em sẽ chuyển admin kiểm tra giúp mình.",
            "admin_check_line": "Admin sẽ kiểm tra theo dữ liệu thực tế trước khi phản hồi hướng xử lý.",
        },
        "scenarios": [],
        "unsafe_reference_claim_patterns": [],
    }


def load_playbook(path: str | Path | None = None) -> dict:
    target = Path(path) if path else default_playbook_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        data = _playbook_fallback()
    clean = _playbook_fallback()
    if isinstance(data, dict):
        clean.update(data)
    clean["version"] = str(clean.get("version") or PLAYBOOK_VERSION_FALLBACK)
    clean["raw_script_auto_ingest"] = bool(clean.get("raw_script_auto_ingest", False))
    categories = clean.get("policy_claim_categories") if isinstance(clean.get("policy_claim_categories"), dict) else {}
    for claim_type in POLICY_CLAIM_TYPES:
        categories.setdefault(claim_type, {"auto_reply": claim_type in {"safe_public_fact", "config_priced_fact"}})
    clean["policy_claim_categories"] = categories
    clean["reply_slots"] = clean.get("reply_slots") if isinstance(clean.get("reply_slots"), dict) else {}
    clean["scenarios"] = [item for item in clean.get("scenarios") or [] if isinstance(item, dict) and str(item.get("id") or "").strip()]
    clean["unsafe_reference_claim_patterns"] = [
        item for item in clean.get("unsafe_reference_claim_patterns") or [] if isinstance(item, dict)
    ]
    return clean


def playbook_policy_claim_categories(playbook: dict | None = None) -> set[str]:
    data = playbook or load_playbook()
    return set((data.get("policy_claim_categories") or {}).keys())


def _contains_any(folded: str, terms: tuple[str, ...] | list[str]) -> bool:
    return any(term and term in folded for term in terms)


def detect_policy_claims(
    text: str,
    *,
    pricing_source: str = "unknown",
    playbook: dict | None = None,
) -> dict:
    data = playbook or load_playbook()
    folded = _fold(text)
    claim_types: set[str] = {"safe_public_fact"}
    blocked: list[str] = []
    requires_admin_review = False

    completed_refund_terms = (
        "da hoan",
        "da refund",
        "da tra tien",
        "da tra xu",
        "da cong xu",
        "cong xu roi",
        "hoan xong",
        "hoan thanh cong",
    )
    voucher_terms = ("voucher", "ma giam gia", "coupon", "tang ma", "tang voucher")
    bonus_terms = ("bonus", "tang xu", "cong them xu", "khuyen mai nap", "thuong nap")
    vip_terms = ("vip", "khach than thiet", "giam gia rieng", "chiet khau", "uu dai rieng")
    negated_policy_terms = (
        "khong tu hua",
        "chua tu hua",
        "khong hua",
        "chua hua",
        "chua co chinh sach",
        "can admin xac nhan",
    )
    is_negated_policy_statement = _contains_any(folded, negated_policy_terms)
    hard_price = bool(re.search(r"\b\d+[\d.,]*(?:\s*(?:xu|vnd|dong|đ|k|tr|trieu|triệu))\b", folded, re.IGNORECASE))

    if _contains_any(folded, completed_refund_terms):
        claim_types.add("never_auto_promise")
        blocked.append("refund_or_xu_completed_without_record")
    if _contains_any(folded, voucher_terms) and not is_negated_policy_statement:
        claim_types.add("policy_confirm_required")
        blocked.append("voucher_policy_unverified")
        requires_admin_review = True
    if _contains_any(folded, bonus_terms) and not is_negated_policy_statement:
        claim_types.add("policy_confirm_required")
        blocked.append("bonus_policy_unverified")
        requires_admin_review = True
    if _contains_any(folded, vip_terms) and not is_negated_policy_statement:
        claim_types.add("policy_confirm_required")
        blocked.append("vip_or_discount_policy_unverified")
        requires_admin_review = True
    if hard_price and str(pricing_source or "unknown") not in TRUSTED_PRICING_SOURCES:
        claim_types.add("config_priced_fact")
        blocked.append("hardcoded_price_without_config_source")
        requires_admin_review = True

    for item in data.get("unsafe_reference_claim_patterns") or []:
        pattern = _fold(str(item.get("pattern") or ""))
        if pattern and pattern in folded:
            claim_type = str(item.get("claim_type") or "policy_confirm_required")
            if claim_type in POLICY_CLAIM_TYPES:
                claim_types.add(claim_type)
            blocked.append(str(item.get("id") or pattern))
            requires_admin_review = True

    unsafe = bool(blocked) or "never_auto_promise" in claim_types
    safe_replacement = str((data.get("reply_slots") or {}).get("handoff_line") or "Em sẽ chuyển admin kiểm tra giúp mình.")
    return {
        "claim_types": sorted(claim_types),
        "unsafe": unsafe,
        "requires_admin_review": requires_admin_review or unsafe,
        "blocked_claims": blocked,
        "safe_replacement": safe_replacement,
    }


def playbook_status(playbook: dict | None = None, kb: dict | None = None) -> dict:
    data = playbook or load_playbook()
    base = kb or load_knowledge_base()
    claim_counter: Counter[str] = Counter()
    policy_confirm_scenarios = 0
    unsafe_template_count = 0
    pricing_sources = Counter(str(item.get("source") or "unknown") for item in (_pricing_matrix(base) or {}).values() if isinstance(item, dict))
    for scenario in data.get("scenarios") or []:
        for claim in scenario.get("policy_claim_types") or []:
            claim_counter[str(claim)] += 1
        if any(claim in {"policy_confirm_required", "never_auto_promise"} for claim in scenario.get("policy_claim_types") or []):
            policy_confirm_scenarios += 1
        for template in scenario.get("safe_reply_templates") or []:
            if detect_policy_claims(str(template), playbook=data).get("unsafe"):
                unsafe_template_count += 1
                break
    return {
        "version": str(data.get("version") or PLAYBOOK_VERSION_FALLBACK),
        "scenario_count": len(data.get("scenarios") or []),
        "policy_claim_counts": dict(claim_counter),
        "policy_confirm_scenario_count": policy_confirm_scenarios,
        "unsafe_unverified_claims_count": unsafe_template_count,
        "pricing_source_count": dict(pricing_sources),
        "raw_script_auto_ingest": bool(data.get("raw_script_auto_ingest")),
        "last_updated": str(data.get("last_updated") or ""),
    }


def _playbook_slots(playbook: dict, classification: dict | None = None, scenario: dict | None = None) -> dict[str, str]:
    classification = classification or {}
    scenario = scenario or {}
    slots = {str(key): str(value) for key, value in (playbook.get("reply_slots") or {}).items()}
    slots.update({str(key): str(value) for key, value in (scenario.get("reply_slots") or {}).items()})
    slots.setdefault("quote_before_confirm_text", "Em sẽ báo đúng gói/Xu trước khi mình xác nhận.")
    slots.setdefault("handoff_line", "Em sẽ chuyển admin kiểm tra giúp mình.")
    slots.setdefault("admin_check_line", "Admin sẽ kiểm tra theo dữ liệu thực tế trước khi phản hồi hướng xử lý.")
    slots["product_name"] = str(scenario.get("product_name") or classification.get("primary_product") or classification.get("product") or "TOAN AAS")
    price_text = str(classification.get("price_text") or "").strip()
    rendered_price = price_text[:1].lower() + price_text[1:] if price_text else ""
    slots["price_text_if_configured"] = rendered_price if str(classification.get("pricing_source") or "") == "config" else ""
    slots["next_question"] = str(scenario.get("next_question") or classification.get("next_question") or "Anh/chị muốn làm phần nào trước ạ?")
    slots["handoff_line"] = str(slots.get("handoff_line") or "Em sẽ chuyển admin kiểm tra giúp mình.")
    return slots


def _format_playbook_template(template: str, slots: dict[str, str]) -> str:
    def repl(match: re.Match) -> str:
        return str(slots.get(match.group(1), ""))

    rendered = re.sub(r"\{([A-Za-z0-9_]+)\}", repl, str(template or ""))
    rendered = re.sub(r"[ \t]+", " ", rendered)
    rendered = re.sub(r"\n{3,}", "\n\n", rendered).strip()
    return rendered


def _scenario_score(scenario: dict, text: str, classification: dict) -> tuple[int, list[str]]:
    folded = _fold(text)
    intent_id = str(classification.get("intent_id") or "")
    score = 0
    matches: list[str] = []
    if intent_id and intent_id in [str(item) for item in (scenario.get("intent_ids") or [])]:
        score += 5
        matches.append(intent_id)
    for key in ("signals", "examples"):
        for signal in scenario.get(key) or []:
            term = _fold(str(signal or ""))
            if term and term in folded:
                score += 4 if key == "signals" else 3
                matches.append(term)
            elif term and len(term.split()) >= 3 and all(part in folded for part in term.split()[:3]):
                score += 2
                matches.append(term)
    return score, matches[:8]


def select_playbook_scenario(text: str, classification: dict | None = None, playbook: dict | None = None) -> dict:
    data = playbook or load_playbook()
    current = classification or {}
    candidates: list[tuple[int, int, dict, list[str]]] = []
    for idx, scenario in enumerate(data.get("scenarios") or []):
        score, matches = _scenario_score(scenario, text, current)
        if score:
            candidates.append((score, int(scenario.get("priority") or 0), scenario, matches))
    if not candidates:
        return {}
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    score, _priority, scenario, matches = candidates[0]
    selected = dict(scenario)
    selected["_match_score"] = score
    selected["_matched_terms"] = matches
    return selected


def build_human_touch_reply(
    text: str,
    classification: dict | None = None,
    *,
    playbook: dict | None = None,
    kb: dict | None = None,
    variation_seed: str | int | None = None,
) -> dict:
    data = playbook or load_playbook()
    base = kb or load_knowledge_base()
    current = dict(classification or {})
    scenario = select_playbook_scenario(text, current, data)
    if not scenario:
        return {"matched": False}
    templates = [str(item).strip() for item in scenario.get("safe_reply_templates") or [] if str(item or "").strip()]
    if not templates:
        return {"matched": False, "scenario_id": str(scenario.get("id") or "")}
    scenario_id = str(scenario.get("id") or "unknown")
    template_key = f"playbook:{scenario_id}"
    if variation_seed is None:
        current_index = _REPLY_VARIATION_COUNTER.get(template_key, 0)
        _REPLY_VARIATION_COUNTER[template_key] = current_index + 1
        template_index = current_index % len(templates)
    else:
        digest = hashlib.sha256(f"{template_key}:{variation_seed}".encode("utf-8")).hexdigest()
        template_index = int(digest[:8], 16) % len(templates)
    template = templates[template_index]
    slots = _playbook_slots(data, current, scenario)
    reply = _clean_reply_text(_format_playbook_template(template, slots), severity=str(current.get("severity") or scenario.get("severity") or "normal"))
    pricing_source = str(current.get("pricing_source") or "unknown")
    if slots.get("price_text_if_configured"):
        pricing_source = "config"
    policy = detect_policy_claims(reply, pricing_source=pricing_source, playbook=data)
    handoff = bool(scenario.get("handoff_required") or policy.get("requires_admin_review"))
    ticket = bool(scenario.get("ticket_required") or handoff)
    return {
        "matched": True,
        "playbook_version": str(data.get("version") or PLAYBOOK_VERSION_FALLBACK),
        "scenario_id": scenario_id,
        "scenario_group": str(scenario.get("group") or ""),
        "reply_template_id": f"{template_key}:{template_index + 1}",
        "reply": reply,
        "policy_claims": policy,
        "handoff_required": handoff,
        "ticket_required": ticket,
        "matched_terms": list(scenario.get("_matched_terms") or []),
        "status": playbook_status(data, base),
    }


def _knowledge_products(kb: dict) -> dict[str, dict]:
    products = kb.get("products") or kb.get("product_knowledge") or {}
    if isinstance(products, list):
        return {
            str(item.get("canonical_product_id") or item.get("id") or "").strip(): item
            for item in products
            if isinstance(item, dict) and str(item.get("canonical_product_id") or item.get("id") or "").strip()
        }
    if isinstance(products, dict):
        clean: dict[str, dict] = {}
        for key, value in products.items():
            if isinstance(value, dict):
                product_id = str(value.get("canonical_product_id") or key).strip()
                clean[product_id] = value
        return clean
    return {}


def _pricing_matrix(kb: dict) -> dict[str, dict]:
    matrix = kb.get("pricing_matrix") or kb.get("pricing") or {}
    return matrix if isinstance(matrix, dict) else {}


def _product_alias_terms(product: dict) -> list[str]:
    terms: list[str] = []
    for key in ("aliases", "synonyms", "typical_user_questions", "display_name"):
        values = product.get(key) or []
        if isinstance(values, str):
            values = [values]
        for value in values:
            folded = _fold(str(value or ""))
            if folded and folded not in terms:
                terms.append(folded)
    return terms


def detect_product_context(text: str, kb: dict | None = None) -> dict:
    base = kb or load_knowledge_base()
    folded = _fold(text)
    products = _knowledge_products(base)
    matched: list[tuple[str, list[str]]] = []
    for product_id, product in products.items():
        aliases = [term for term in _product_alias_terms(product) if _fold_contains(folded, term)]
        if aliases:
            matched.append((product_id, aliases[:5]))

    # Keep payment/support issues first when they are mixed with product asks.
    priority = {
        "payment_xu": 100,
        "product_video": 80,
        "image_to_video": 78,
        "image_ai": 76,
        "subdub": 74,
        "voice": 70,
        "music": 68,
        "premium_private_bot": 66,
        "free_tools": 60,
    }
    matched.sort(key=lambda item: priority.get(item[0], 0), reverse=True)
    product_ids = [product_id for product_id, _aliases in matched]
    matched_aliases = [alias for _product_id, aliases in matched for alias in aliases]

    secondary = product_ids[1:]
    sub_products: list[str] = []
    if any(term in folded for term in ("phu de", "subtitle", "sub", "srt", "dich chu", "dich video")):
        sub_products.append("subtitle")
    if any(term in folded for term in ("long tieng", "dub", "voice over", "doc tieng viet")):
        sub_products.append("dub")
    if len(sub_products) > 1:
        secondary = list(dict.fromkeys(secondary + sub_products))

    primary = product_ids[0] if product_ids else ""
    if any(term in folded for term in ("ghep anh", "anh thanh video", "video tu anh", "slideshow", "ghep hinh", "anh roi ghep video")):
        previous_primary = primary
        primary = "image_to_video"
        secondary = [item for item in secondary if item != "image_to_video"]
        if previous_primary and previous_primary != "image_to_video" and previous_primary not in secondary:
            secondary.insert(0, previous_primary)
        if "image_ai" not in secondary:
            secondary.insert(0, "image_ai")

    product_count = len(set(product_ids + sub_products))
    mixed = product_count > 1 or any(term in folded for term in (" va ", " voi ", " + ", " roi ", "kem", "cung luc"))
    entry = products.get(primary) or {}
    pricing = _pricing_matrix(base).get(str(entry.get("pricing_source_key") or primary), {})
    pricing_source = str(pricing.get("source") or ("config" if pricing else "unknown"))
    if not pricing:
        pricing_source = "unknown"
    return {
        "primary_product": primary,
        "secondary_products": secondary[:5],
        "mixed_intent": bool(primary and mixed and secondary),
        "matched_aliases": matched_aliases[:10],
        "knowledge_entry_id": primary,
        "next_question": str(entry.get("next_question") or ""),
        "pricing_source": pricing_source,
        "price_text": str(pricing.get("price_text") or ""),
    }


def _pricing_source_for_intent(kb: dict, intent_id: str, product_id: str) -> str:
    if intent_id not in {
        "product_video_pricing",
        "image_ai_pricing",
        "image_to_video_pricing",
        "subdub_pricing",
        "subtitle_pricing",
        "dub_pricing",
        "voice_pricing",
        "music_pricing",
        "bot_private_pricing",
        "mixed_product_pricing",
        "unknown_pricing_product",
        "pricing_general",
        "pricing_table_general",
        "pricing",
    }:
        return "unknown"
    products = _knowledge_products(kb)
    product = products.get(product_id) or {}
    key = str(product.get("pricing_source_key") or product_id or intent_id).strip()
    pricing = _pricing_matrix(kb).get(key) or {}
    if pricing:
        return str(pricing.get("source") or "config")
    return "unknown"


INTENT_PRIORITY = (
    "angry_scam_accusation",
    "public_negative_comment",
    "payment_xu_not_received",
    "payment_duplicate",
    "payment_wrong_amount",
    "payment_issue",
    "refund_request",
    "refund",
    "product_video_failed_no_file",
    "product_video_stuck",
    "subdub_subtitle_error",
    "subdub_dubbing_error",
    "music_wrong_voice_or_duplicate_file",
    "voice_tts_error",
    "technical_error",
    "admin_handoff",
    "premium_private_bot",
    "job_status_check",
    "account_or_usage_limit",
    "product_video_quality_issue",
    "mixed_product_pricing",
    "image_to_video_pricing",
    "image_ai_pricing",
    "subdub_pricing",
    "subtitle_pricing",
    "dub_pricing",
    "voice_pricing",
    "music_pricing",
    "bot_private_pricing",
    "unknown_pricing_product",
    "product_video_pricing",
    "product_video_how_to",
    "product_video_consulting",
    "subdub_file_too_large",
    "subdub_how_to",
    "music_how_to",
    "voice_tts_how_to",
    "image_prompt_help",
    "free_tools_help",
    "pricing_topup",
    "pricing_table_general",
    "pricing_general",
    "pricing",
    "new_user_what_is_toan_aas",
    "repeated_ping",
    "greeting_ping",
    "greeting",
    "vague_or_unclear",
    "media_unknown",
    "out_of_scope",
)


def _legacy_intents_from_kb(kb: dict) -> list[dict]:
    intents = []
    for item in kb.get("intents") or []:
        if not isinstance(item, dict):
            continue
        intent_id = str(item.get("id") or "").strip()
        if not intent_id:
            continue
        intents.append(
            {
                "id": intent_id,
                "description": str(item.get("description") or f"Knowledge base intent {intent_id}"),
                "priority": int(item.get("priority") or 10),
                "confidence_keywords": list(item.get("confidence_keywords") or item.get("keywords") or []),
                "example_user_messages": list(item.get("example_user_messages") or item.get("keywords") or [])[:12],
                "required_context_fields": list(item.get("required_context_fields") or []),
                "reply_templates": _intent_templates(item),
                "handoff_required": bool(item.get("handoff_required", item.get("handoff", False))),
                "ticket_required": bool(item.get("ticket_required", item.get("ticket", item.get("handoff", False)))),
                "safe_next_steps": list(item.get("safe_next_steps") or ["Hỏi thêm thông tin còn thiếu"]),
                "forbidden_claims": list(item.get("forbidden_claims") or []),
                "severity": str(item.get("severity") or ("urgent" if intent_id in URGENT_INTENTS else "normal")),
            }
        )
    return intents


def _builtin_live_intents() -> list[dict]:
    return [
        {
            "id": "customer_confused_or_what",
            "description": "Khách hỏi lại vì bot vừa trả lời sai hoặc lệch ngữ cảnh.",
            "priority": 98,
            "confidence_keywords": [
                "?",
                "??",
                "gì vậy",
                "gi vay",
                "là sao",
                "la sao",
                "sao vậy",
                "sao vay",
                "không hiểu",
                "khong hieu",
                "nói gì vậy",
                "noi gi vay",
            ],
            "example_user_messages": ["?", "??", "gì vậy?", "là sao", "không hiểu"],
            "required_context_fields": [],
            "reply_templates": [
                "Dạ xin lỗi anh/chị, em vừa trả lời chưa đúng ngữ cảnh. Mình muốn hỏi về video, ảnh, SubDub hay bảng giá ạ?"
            ],
            "handoff_required": False,
            "ticket_required": False,
            "safe_next_steps": ["Hỏi lại nhu cầu theo nhóm sản phẩm chính"],
            "forbidden_claims": ["tự nhận lỗi hệ thống", "hứa hoàn tiền", "hứa cộng Xu"],
            "severity": "normal",
        },
        {
            "id": "pricing_table_general",
            "description": "Khách hỏi bảng giá tổng quát TOAN AAS.",
            "priority": 86,
            "confidence_keywords": [
                "bảng giá",
                "bang gia",
                "cho em bảng giá",
                "gửi bảng giá",
                "bảng giá dịch vụ",
                "giá tổng",
                "có bảng giá không",
                "giá các dịch vụ",
            ],
            "example_user_messages": [
                "bảng giá",
                "cho em bảng giá",
                "gửi bảng giá",
                "bảng giá dịch vụ",
                "giá tổng",
                "có bảng giá không",
                "giá các dịch vụ sao",
            ],
            "required_context_fields": [],
            "reply_templates": [
                "Dạ em gửi mình hướng bảng giá tổng quát ạ: TOAN AAS có Video AI, tạo ảnh/ghép ảnh thành video, SubDub phụ đề-lồng tiếng, voice/nhạc và bot riêng. Mỗi phần bot sẽ báo gói/Xu trước khi mình xác nhận, nên không bị trừ nhầm. Anh/chị muốn xem giá phần video, ảnh hay SubDub trước ạ?"
            ],
            "handoff_required": False,
            "ticket_required": False,
            "safe_next_steps": ["Hỏi khách muốn xem giá phần video, ảnh hay SubDub trước"],
            "forbidden_claims": ["báo giá bịa", "cam kết giảm giá", "tự hứa miễn phí"],
            "severity": "normal",
        }
    ]


def _intent_lookup(training_data: dict, kb: dict) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for item in _builtin_live_intents():
        merged[_intent_id(item)] = item
    for item in _legacy_intents_from_kb(kb):
        merged[_intent_id(item)] = item
    for item in training_data.get("intents") or []:
        intent_id = _intent_id(item)
        if intent_id:
            existing = merged.get(intent_id)
            merged[intent_id] = {**existing, **item} if isinstance(existing, dict) else item
    return merged


def _intent_signal_terms(intent: dict) -> list[str]:
    terms: list[str] = []
    for key in ("confidence_keywords", "keywords", "signals", "example_user_messages", "user_samples"):
        values = intent.get(key) or []
        if isinstance(values, str):
            values = [values]
        for value in values:
            folded = _fold(str(value or ""))
            if folded and folded not in terms:
                terms.append(folded)
    return terms


def _score_intent(intent: dict, query: str) -> tuple[int, list[str]]:
    score = 0
    matches: list[str] = []
    for term in _intent_signal_terms(intent):
        if _fold_contains(query, term):
            score += 4 + min(4, len(term.split()))
            matches.append(term)
        elif len(term.split()) >= 3 and all(part in query for part in term.split()[:3]):
            score += 2
            matches.append(term)
    if score:
        score += int(intent.get("priority") or 0) // 20
    return score, matches


def _heuristic_intent_id(query: str) -> str:
    folded = _fold(query)
    if not folded:
        return ""
    price_question = _is_pricing_question(folded)
    payment_terms = ("nap", "chuyen khoan", "thanh toan", "bill", "hoa don", "chua cong", "chua thay xu", "mat xu", "tru xu")
    video_terms = ("video", "clip", "mp4", "quang cao", "san pham", "tiktok", "reels", "short", "trailer", "phim")
    image_terms = ("anh", "hinh", "hinh anh", "tao hinh", "avatar", "logo", "nhan vat", "boi canh")
    img2vid_terms = ("ghep anh", "anh thanh video", "video tu anh", "anh chay", "ghep hinh", "slideshow", "anh roi ghep video")
    subtitle_terms = ("phu de", "subtitle", "sub", "srt", "dich chu", "dich video")
    dub_terms = ("long tieng", "dub", "voice over", "doc tieng viet")
    voice_terms = ("voice", "tts", "giong doc", "giong nam", "giong nu")
    music_terms = ("nhac", "music", "bai hat", "suno", "nhac nen")
    private_bot_terms = ("bot rieng", "premium", "he thong rieng", "cskh tu dong", "shop", "doanh nghiep")
    has_specific_product_word = any(term in folded for term in video_terms + image_terms + img2vid_terms + subtitle_terms + dub_terms + voice_terms + music_terms + private_bot_terms)

    if re.fullmatch(r"[\?\s]{1,3}", str(query or "")) or any(
        term in folded
        for term in ("gi vay", "la sao", "sao vay", "noi gi vay", "khong hieu", "ua la sao", "bot noi gi vay")
    ):
        return "customer_confused_or_what"
    if any(term in folded for term in ("nay su dung sao", "bot nay dung sao", "dung kieu gi", "huong dan", "moi vao", "bat dau tu dau", "su dung sao anh")):
        return "new_user_what_is_toan_aas"
    if not has_specific_product_word and "xu" not in folded and (
        folded in {"bang gia", "cho em bang gia", "gui bang gia", "bang gia dich vu", "gia tong"}
        or "bang gia" in folded
        or any(term in folded for term in ("co bang gia khong", "gia cac dich vu", "bang gia tong", "xem bang gia"))
    ):
        return "pricing_table_general"
    if any(term in folded for term in ("xu bang", "bang gia xu", "quy doi xu", "xu tinh sao", "1 xu", "1000 xu")):
        return "pricing_general"
    if any(term in folded for term in ("bam nham", "co mat xu", "co tru tien truoc", "tru tien truoc", "bao gia truoc", "tru xu truoc")):
        return "pricing_general"
    if any(term in folded for term in ("dat qua", "mac qua", "ben khac free", "de suy nghi", "co giam gia", "giam gia khong")):
        return "pricing_general"
    if any(term in folded for term in ("clone giong", "giong cua toi", "giong cua minh", "voice rieng", "file ghi am")):
        return "voice_tts_how_to"
    if any(term in folded for term in ("khong nhan bonus", "bonus chua vao", "khuyen mai chua co", "voucher", "ma giam gia")):
        return "payment_issue"
    if any(term in folded for term in ("goi quan ly", "gap quan ly", "quan ly dau", "khong noi chuyen voi bot")):
        return "admin_handoff"
    if any(term in folded for term in video_terms) and any(
        term in folded
        for term in ("chua thay file", "chua co file", "khong thay file", "khong ra file", "chua ra file", "video fail", "bi tru xu")
    ):
        return "product_video_failed_no_file"
    if any(term in folded for term in payment_terms) and any(term in folded for term in video_terms + image_terms):
        if any(term in folded for term in ("roi", "xong", "chua", "da thanh toan", "chuyen khoan")):
            return "payment_xu_not_received"
        return "pricing_topup"
    urgent_terms = (
        "chua thay xu",
        "chua nhan xu",
        "chua cong",
        "da thanh toan",
        "chuyen khoan",
        "hoan xu",
        "hoan tien",
        "refund",
        "lua dao",
        "scam",
        "boc phot",
        "khong ra file",
        "bi tru xu",
        "ket",
        "treo",
        "fail",
    )
    if any(term in folded for term in urgent_terms):
        return ""
    if price_question and any(term in folded for term in private_bot_terms):
        return "bot_private_pricing"
    if any(term in folded for term in img2vid_terms):
        return "image_to_video_pricing"
    has_video = any(term in folded for term in video_terms)
    has_image = any(term in folded for term in image_terms)
    if has_video and has_image:
        return "mixed_product_pricing"
    if price_question and has_image:
        return "image_ai_pricing"
    if price_question and any(term in folded for term in subtitle_terms) and any(term in folded for term in dub_terms):
        return "subdub_pricing"
    if price_question and any(term in folded for term in subtitle_terms):
        return "subtitle_pricing"
    if price_question and any(term in folded for term in dub_terms):
        return "dub_pricing"
    if price_question and any(term in folded for term in voice_terms):
        return "voice_pricing"
    if price_question and any(term in folded for term in music_terms):
        return "music_pricing"
    if price_question and has_video:
        return "product_video_pricing"
    if price_question and any(term in folded for term in ("cai kia", "loai kia", "combo nay", "dich vu kia")):
        return "unknown_pricing_product"
    if any(term in folded for term in ("video ban hang", "video san pham", "video quang cao", "lam clip", "muon tao video", "muon lam video")):
        return "product_video_consulting"
    ping_count = sum(folded.count(term) for term in ("alo", "hi", "hello", "co ai khong"))
    if ping_count >= 2 or any(term in folded for term in ("sao khong tra loi", "co ai khong vay", "sao im vay")):
        return "repeated_ping"
    greeting_terms = ("alo", "hi", "hello", "co ai khong", "co ho tro khong", "cho minh hoi voi")
    if folded in greeting_terms or (len(folded.split()) <= 5 and any(term in folded for term in greeting_terms)):
        return "greeting_ping"
    vague_terms = ("loi roi", "khong duoc", "sao vay", "bi gi roi", "ua", "lam sao day", "khong hieu")
    if folded in vague_terms or (len(folded.split()) <= 4 and any(term in folded for term in vague_terms)):
        return "vague_or_unclear"
    return ""


def _select_intent(text: str, media_type: str, training_data: dict, kb: dict) -> tuple[dict, int, list[str]]:
    query = _fold(text)
    if not query and media_type:
        query = "media file tep anh video audio"
    intents = _intent_lookup(training_data, kb)
    heuristic = _heuristic_intent_id(query)
    if heuristic and heuristic in intents:
        score = max(8, int(intents[heuristic].get("priority") or 0) // 8)
        return intents[heuristic], score, [heuristic]
    candidates: list[tuple[int, int, dict, list[str]]] = []
    for intent_id, intent in intents.items():
        score, matches = _score_intent(intent, query)
        if score:
            priority_rank = len(INTENT_PRIORITY) - INTENT_PRIORITY.index(intent_id) if intent_id in INTENT_PRIORITY else 0
            candidates.append((score, priority_rank, intent, matches))
    if candidates:
        candidates.sort(key=lambda item: (item[0], item[1], int(item[2].get("priority") or 0)), reverse=True)
        score, _priority_rank, selected, matches = candidates[0]
        return selected, score, matches
    if media_type and "media_unknown" in intents:
        return intents["media_unknown"], 1, [media_type]
    return intents.get("out_of_scope") or {"id": "out_of_scope", "reply_templates": ["Dạ em cần thêm thông tin để hỗ trợ đúng ạ."]}, 0, []


def _classification_confidence(intent_id: str, score: int) -> str:
    if intent_id == "out_of_scope" or score <= 1:
        return "low"
    if score >= 8:
        return "high"
    return "medium"


def _classification_severity(intent: dict, intent_id: str) -> str:
    configured = str(intent.get("severity") or "").strip().lower()
    if configured in {"normal", "warning", "urgent"}:
        return configured
    return "urgent" if intent_id in URGENT_INTENTS else ("warning" if bool(intent.get("handoff_required") or intent.get("handoff")) else "normal")


def _extract_context_fields(text: str) -> dict:
    raw = str(text or "")
    folded = _fold(raw)
    fields: dict[str, str] = {}
    job_match = re.search(r"(?:#|job|ma xu ly|mã xử lý|ma job|mã job)\s*[:#-]?\s*([A-Za-z0-9_-]{2,})", raw, re.IGNORECASE)
    if job_match:
        fields["job_code"] = job_match.group(1)
        fields["music_job_id"] = job_match.group(1)
    amount_match = re.search(r"(\d+(?:[.,]\d+)?\s*(?:k|nghin|nghìn|tr|triệu|vnd|đ|dong|đồng))", raw, re.IGNORECASE)
    if amount_match:
        fields["payment_amount"] = amount_match.group(1)
        fields["amount"] = amount_match.group(1)
    if any(term in folded for term in ("bill", "anh chuyen khoan", "anh giao dich", "bien lai", "chup giao dich", "screenshot")):
        fields["screenshot_or_bill"] = "yes"
    if any(term in folded for term in ("luc", "hom nay", "sang nay", "chieu nay", "toi qua", "buoi toi", "ngay", "vua", "xong")) or re.search(r"\d{1,2}:\d{2}", raw):
        fields["payment_time"] = "mentioned"
        fields["time_created"] = "mentioned"
    duration_match = re.search(r"(\d+\s*(?:giay|giây|phut|phút|s|p|min|minute))", folded)
    if duration_match:
        fields["video_duration"] = duration_match.group(1)
    if any(term in folded for term in ("giong nam", "giong nu", "giọng nam", "giọng nữ", "voice")):
        fields["voice_selected"] = "mentioned"
    if any(term in folded for term in ("tru xu", "trừ xu", "mat xu", "mất xu", "charged")):
        fields["charged_xu"] = "mentioned"
    if len(raw.strip()) > 0:
        fields["issue_detail"] = raw.strip()[:240]
        fields["user_message_summary"] = raw.strip()[:240]
    return fields


def _missing_fields(intent: dict, text: str) -> list[str]:
    extracted = _extract_context_fields(text)
    missing = []
    for field in intent.get("required_context_fields") or []:
        if field in {"customer_chat_id", "business_connection_id"}:
            continue
        if field not in extracted:
            missing.append(str(field))
    return missing


def _infer_product(intent_id: str) -> str:
    if intent_id.startswith("payment") or intent_id in {"refund", "refund_request"}:
        return "payment_xu"
    if intent_id in {"mixed_product_pricing"}:
        return "mixed"
    if intent_id in {"image_to_video_pricing"}:
        return "image_to_video"
    if intent_id in {"image_ai_pricing"}:
        return "image_ai"
    if intent_id.startswith("product_video"):
        return "product_video"
    if intent_id.startswith("subdub") or intent_id in {"subtitle_pricing", "dub_pricing"}:
        return "subdub"
    if intent_id.startswith("music"):
        return "music"
    if intent_id.startswith("voice"):
        return "voice"
    if intent_id.startswith("image"):
        return "image_ai"
    if intent_id in {"premium_private_bot", "bot_private_pricing"}:
        return "premium_private_bot"
    if intent_id == "free_tools_help":
        return "free_tools"
    return "general"


def _select_reply_template(intent: dict, text: str, *, severity: str, variation_seed: str | int | None = None) -> tuple[str, str]:
    intent_id = _intent_id(intent) or "out_of_scope"
    templates = _intent_templates(intent)
    if not templates:
        templates = ["Dạ em cần thêm thông tin để hỗ trợ đúng cho mình ạ. Anh/chị gửi mã xử lý hoặc mô tả vấn đề giúp em nhé."]
    if variation_seed is None:
        current = _REPLY_VARIATION_COUNTER.get(intent_id, 0)
        _REPLY_VARIATION_COUNTER[intent_id] = current + 1
        index = current % len(templates)
    else:
        digest = hashlib.sha256(f"{intent_id}:{variation_seed}".encode("utf-8")).hexdigest()
        index = int(digest[:8], 16) % len(templates)
    reply = _clean_reply_text(templates[index], severity=severity)
    return reply, f"{intent_id}:{index + 1}"


def build_ticket_draft(
    classification: dict,
    event: BusinessMessageEvent | None = None,
    *,
    text: str = "",
) -> dict:
    source_text = text or (event.text if event else "") or (event.caption if event else "")
    extracted = _extract_context_fields(source_text)
    intent_id = str(classification.get("intent_id") or "out_of_scope")
    return {
        "customer_chat_id": str(event.chat_id if event else ""),
        "business_connection_id": mask_business_connection_id(event.business_connection_id if event else ""),
        "intent": intent_id,
        "severity": str(classification.get("severity") or "normal"),
        "product": _infer_product(intent_id),
        "job_code": extracted.get("job_code", ""),
        "payment_amount": extracted.get("payment_amount", ""),
        "payment_time": extracted.get("payment_time", ""),
        "user_message_summary": extracted.get("user_message_summary", source_text[:240]),
        "missing_fields": list(classification.get("missing_fields") or []),
        "suggested_admin_action": "Kiểm tra ca theo thông tin khách gửi và phản hồi theo chính sách TOAN AAS.",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "handoff_required": bool(classification.get("handoff_required") or classification.get("handoff")),
    }


def _is_simple_greeting_text(text: str) -> bool:
    folded = _fold(text)
    return folded in {
        "alo",
        "hi",
        "hello",
        "em oi",
        "shop oi",
        "co ai khong",
        "co ho tro khong",
        "cho minh hoi voi",
    }


def _context_aware_greeting_reply(text: str, classification: dict, conversation_memory: dict | None = None) -> dict:
    intent_id = str(classification.get("intent_id") or "")
    if intent_id not in {"greeting", "greeting_ping", "repeated_ping"} or not _is_simple_greeting_text(text):
        return classification
    memory = conversation_memory or {}
    last_stage = str(memory.get("conversation_stage") or "")
    last_intent = str(memory.get("last_intent") or "")
    last_product = str(memory.get("last_product") or "")
    pricing_context = last_stage == "pricing" or last_intent.endswith("_pricing") or last_intent in {
        "pricing",
        "pricing_general",
        "pricing_table_general",
        "pricing_topup",
    }
    if pricing_context:
        reply = "Dạ em đây ạ. Mình muốn xem giá phần video, ảnh hay bảng giá tổng ạ?"
        template_id = "context_greeting:pricing"
    elif last_product and last_product not in {"general", ""}:
        reply = "Dạ em đây ạ. Mình cần em hỗ trợ tiếp phần đó hay muốn hỏi thêm bảng giá ạ?"
        template_id = "context_greeting:product"
    else:
        reply = "Dạ em đây ạ. Anh/chị muốn hỏi về video, ảnh, SubDub hay nạp Xu ạ?"
        template_id = "context_greeting:new"
    classification = dict(classification)
    classification["reply"] = reply
    classification["reply_preview"] = reply
    classification["reply_template_id"] = template_id
    classification["playbook_scenario_id"] = classification.get("playbook_scenario_id") or ""
    classification["public_safe"] = public_reply_is_safe(reply)
    return classification


def _apply_pricing_table_thread_hint(text: str, classification: dict) -> dict:
    folded = _fold(text)
    intent_id = str(classification.get("intent_id") or "")
    if "bang gia" not in folded or intent_id != "product_video_pricing":
        return classification
    reply = (
        "Dạ em ưu tiên phần giá video trước ạ. Video AI sẽ tùy loại video, độ dài và tư liệu đầu vào; bot sẽ báo gói/Xu trước khi mình xác nhận. "
        "Nếu mình muốn xem bảng giá tổng quát thì TOAN AAS có Video AI, ảnh/ghép ảnh thành video, SubDub phụ đề-lồng tiếng, voice/nhạc và bot riêng. "
        "Anh/chị muốn xem kỹ phần video sản phẩm, video quảng cáo hay video từ ảnh trước ạ?"
    )
    classification = dict(classification)
    classification["reply"] = reply
    classification["reply_preview"] = reply
    classification["reply_template_id"] = "pricing_thread:video_plus_table"
    classification["public_safe"] = public_reply_is_safe(reply)
    return classification


def _result_sources_from_classification(classification: dict, *, fallback: bool = False) -> list[str]:
    sources = list(classification.get("source") or [])
    if classification.get("context_file_version") or classification.get("source_file_version") or classification.get("context_section_used"):
        sources.append("context_file")
    if classification.get("knowledge_entry_id") or classification.get("training_data_version"):
        sources.append("cskh_knowledge")
    if classification.get("playbook_scenario_id"):
        sources.append("playbook")
    pricing_source = str(classification.get("pricing_source") or "")
    if pricing_source == "pricing_doc":
        sources.append("pricing_doc")
        sources.append("pricing")
    elif pricing_source == "guide_doc":
        sources.append("guide_doc")
    elif pricing_source in {"config", "runtime"} or classification.get("price_text"):
        sources.append("pricing")
    if fallback or str(classification.get("confidence") or "") == "low":
        sources.append("fallback")
    return list(dict.fromkeys(str(item) for item in sources if str(item or "").strip()))


def _apply_shared_doc_answer(
    text: str,
    classification: dict,
    conversation_memory: dict | None = None,
    *,
    media_type: str = "",
) -> dict:
    shared = aas_shared_knowledge.classify_shared_answer(text, conversation_memory=conversation_memory, media_type=media_type)
    if not shared.get("matched"):
        classification = dict(classification)
        classification["source"] = _result_sources_from_classification(
            classification,
            fallback=str(classification.get("intent_id") or "") in {"out_of_scope", "vague_or_unclear"},
        )
        classification["learning_queue"] = bool(classification.get("would_queue_learning"))
        return classification
    original_intent = str(classification.get("intent_id") or "")
    original_confidence = str(classification.get("confidence") or "")
    shared_intent = str(shared.get("intent_id") or "")
    if shared_intent == "out_of_scope" and original_intent not in {"out_of_scope", "vague_or_unclear"} and original_confidence != "low":
        classification = dict(classification)
        classification["source"] = _result_sources_from_classification(
            classification,
            fallback=original_intent in {"out_of_scope", "vague_or_unclear"},
        )
        classification["learning_queue"] = bool(classification.get("would_queue_learning"))
        return classification
    result = dict(classification)
    intent_id = str(shared.get("intent_id") or result.get("intent_id") or "pricing_general")
    product = str(shared.get("primary_product") or shared.get("product") or result.get("primary_product") or result.get("product") or "general")
    result.update(
        {
            "intent": intent_id,
            "intent_id": intent_id,
            "product": product,
            "primary_product": product,
            "knowledge_entry_id": str(shared.get("knowledge_entry_id") or (product if product != "general" else "")),
            "pricing_source": str(shared.get("pricing_source") or "pricing_doc"),
            "price_text": str(shared.get("price_text") or result.get("price_text") or ""),
            "reply": str(shared.get("reply") or result.get("reply") or ""),
            "reply_preview": str(shared.get("reply_preview") or shared.get("reply") or result.get("reply_preview") or ""),
            "reply_template_id": str(shared.get("reply_template_id") or f"shared_knowledge:{intent_id}"),
            "confidence": str(shared.get("confidence") or "high"),
            "handoff": bool(shared.get("handoff", result.get("handoff", False))),
            "handoff_required": bool(shared.get("handoff_required", result.get("handoff_required", False))),
            "ticket": bool(shared.get("ticket", result.get("ticket", False))),
            "ticket_required": bool(shared.get("ticket_required", result.get("ticket_required", False))),
            "shared_docs": dict(shared.get("shared_docs") or {}),
            "context_file_path": str(shared.get("context_file_path") or result.get("context_file_path") or ""),
            "context_file_version": str(shared.get("context_file_version") or result.get("context_file_version") or ""),
            "context_file_used": bool(shared.get("context_file_used", result.get("context_file_used", False))),
            "context_version": str(shared.get("context_version") or shared.get("context_file_version") or result.get("context_version") or ""),
            "source_file_version": str(shared.get("source_file_version") or result.get("source_file_version") or ""),
            "context_section_used": str(shared.get("context_section_used") or result.get("context_section_used") or ""),
            "context_sections": list(shared.get("context_sections") or result.get("context_sections") or []),
            "retrieval": dict(shared.get("retrieval") or result.get("retrieval") or {}),
            "human_last_reply_required": bool(shared.get("human_last_reply_required", result.get("human_last_reply_required", True))),
            "would_queue_learning": bool(shared.get("would_queue_learning", result.get("would_queue_learning", False))),
            "learning_queue": bool(shared.get("learning_queue", result.get("learning_queue", False))),
            "previous_topic": str(shared.get("previous_topic") or result.get("previous_topic") or ""),
            "last_product_type": str(shared.get("last_product_type") or result.get("last_product_type") or ""),
            "last_requested_asset": str(shared.get("last_requested_asset") or result.get("last_requested_asset") or ""),
            "last_subject": str(shared.get("last_subject") or result.get("last_subject") or ""),
            "last_flow_suggestion": str(shared.get("last_flow_suggestion") or result.get("last_flow_suggestion") or ""),
            "last_prompt": str(shared.get("last_prompt") or result.get("last_prompt") or ""),
            "last_generated_prompt": str(shared.get("last_generated_prompt") or result.get("last_generated_prompt") or ""),
            "last_offered_action": str(shared.get("last_offered_action") or result.get("last_offered_action") or ""),
            "last_flow": str(shared.get("last_flow") or result.get("last_flow") or ""),
            "last_action_button": str(shared.get("last_action_button") or result.get("last_action_button") or ""),
            "context_carry_used": bool(shared.get("context_carry_used", result.get("context_carry_used", False))),
            "conversation_stage": conversation_stage_for_intent(intent_id),
        }
    )
    result["source"] = _result_sources_from_classification({**result, "source": list(shared.get("source") or [])})
    policy = detect_policy_claims(result.get("reply") or "", pricing_source=str(result.get("pricing_source") or "unknown"))
    result["playbook_policy_claims"] = policy
    result["public_safe"] = public_reply_is_safe(result["reply"]) and not bool(policy.get("unsafe"))
    return result


def classify_cskh_message(
    text: str = "",
    *,
    media_type: str = "",
    kb: dict | None = None,
    training_data: dict | None = None,
    variation_seed: str | int | None = None,
    conversation_memory: dict | None = None,
) -> dict:
    base = kb or load_knowledge_base()
    training = training_data or load_training_data()
    selected, score, matched_terms = _select_intent(text, media_type, training, base)
    intent_id = _intent_id(selected) or "out_of_scope"
    confidence = _classification_confidence(intent_id, score)
    severity = _classification_severity(selected, intent_id)
    reply, template_id = _select_reply_template(selected, text, severity=severity, variation_seed=variation_seed)
    handoff = bool(selected.get("handoff_required", selected.get("handoff", False)))
    ticket = bool(selected.get("ticket_required", selected.get("ticket", handoff)))
    if confidence == "low" and intent_id != "out_of_scope":
        intent_id = "out_of_scope"
        fallback = _intent_lookup(training, base).get("out_of_scope") or selected
        severity = "normal"
        reply, template_id = _select_reply_template(fallback, text, severity=severity, variation_seed=variation_seed)
        handoff = bool(fallback.get("handoff_required", fallback.get("handoff", False)))
        ticket = bool(fallback.get("ticket_required", fallback.get("ticket", handoff)))
        selected = fallback
    missing = _missing_fields(selected, text)
    product_context = detect_product_context(text, base)
    inferred_product = _infer_product(intent_id)
    primary_product = product_context.get("primary_product") or ("" if inferred_product == "general" else inferred_product)
    secondary_products = list(product_context.get("secondary_products") or [])
    if inferred_product not in {"general", "mixed"} and inferred_product != primary_product and inferred_product not in secondary_products:
        if primary_product:
            secondary_products.append(inferred_product)
        else:
            primary_product = inferred_product
    next_question = str(product_context.get("next_question") or _next_step_hint(selected))
    pricing_source = _pricing_source_for_intent(base, intent_id, primary_product or inferred_product)
    if pricing_source == "unknown" and product_context.get("pricing_source") == "config":
        pricing_source = "config"
    result = {
        "intent": intent_id,
        "intent_id": intent_id,
        "product": _infer_product(intent_id),
        "primary_product": primary_product or _infer_product(intent_id),
        "secondary_products": secondary_products[:5],
        "mixed_intent": bool(product_context.get("mixed_intent") or (intent_id == "mixed_product_pricing")),
        "matched_aliases": list(product_context.get("matched_aliases") or []),
        "next_question": next_question,
        "knowledge_entry_id": str(product_context.get("knowledge_entry_id") or primary_product or ""),
        "pricing_source": pricing_source,
        "price_text": str(product_context.get("price_text") or ""),
        "conversation_stage": conversation_stage_for_intent(intent_id),
        "reply": reply,
        "reply_preview": reply,
        "reply_template_id": template_id,
        "handoff": handoff,
        "handoff_required": handoff,
        "ticket": ticket,
        "ticket_required": ticket,
        "confidence": confidence,
        "severity": severity,
        "missing_fields": missing,
        "matched_keyword_groups": matched_terms,
        "training_data_version": str(training.get("version") or TRAINING_DATA_VERSION_FALLBACK),
        "public_safe": public_reply_is_safe(reply),
        "safe_next_step": _next_step_hint(selected),
        "forbidden_claims": list(selected.get("forbidden_claims") or []),
    }
    playbook_reply = build_human_touch_reply(text, result, kb=base, variation_seed=variation_seed)
    if playbook_reply.get("matched"):
        policy = playbook_reply.get("policy_claims") or {}
        result["playbook_version"] = str(playbook_reply.get("playbook_version") or "")
        result["playbook_scenario_id"] = str(playbook_reply.get("scenario_id") or "")
        result["playbook_scenario_group"] = str(playbook_reply.get("scenario_group") or "")
        result["playbook_policy_claims"] = policy
        result["playbook_status"] = playbook_reply.get("status") or {}
        result["playbook_matched_terms"] = list(playbook_reply.get("matched_terms") or [])
        if not policy.get("unsafe") and str(playbook_reply.get("reply") or "").strip():
            result["reply"] = str(playbook_reply.get("reply") or "").strip()
            result["reply_preview"] = result["reply"]
            result["reply_template_id"] = str(playbook_reply.get("reply_template_id") or f"playbook:{result['playbook_scenario_id']}")
        else:
            result["reply"] = "Dạ phần này cần admin xác nhận chính sách trước để tránh em trả lời sai. Anh/chị gửi giúp thông tin liên quan, em chuyển admin kiểm tra ngay ạ."
            result["reply_preview"] = result["reply"]
            result["reply_template_id"] = f"playbook_policy_guard:{result['playbook_scenario_id']}"
        if playbook_reply.get("handoff_required"):
            result["handoff"] = True
            result["handoff_required"] = True
        if playbook_reply.get("ticket_required"):
            result["ticket"] = True
            result["ticket_required"] = True
        result["public_safe"] = public_reply_is_safe(result["reply"]) and not bool(policy.get("unsafe"))
    else:
        result["playbook_policy_claims"] = detect_policy_claims(result.get("reply") or "", pricing_source=pricing_source)
        result["public_safe"] = public_reply_is_safe(result["reply"]) and not bool(result["playbook_policy_claims"].get("unsafe"))
    result = _apply_shared_doc_answer(text, result, conversation_memory, media_type=media_type)
    result["would_queue_learning"] = bool(result.get("would_queue_learning") or result.get("learning_queue") or should_queue_learning(result, text))
    result["learning_queue"] = bool(result["would_queue_learning"])
    result["source"] = _result_sources_from_classification(
        result,
        fallback=str(result.get("intent_id") or "") in {"out_of_scope", "vague_or_unclear"},
    )
    if ticket or handoff:
        result["ticket_preview"] = build_ticket_draft(result, text=text)
    elif result.get("ticket") or result.get("handoff"):
        result["ticket_preview"] = build_ticket_draft(result, text=text)
    result = _apply_pricing_table_thread_hint(text, result)
    return _context_aware_greeting_reply(text, result, conversation_memory)


def classify_business_event(event: BusinessMessageEvent, kb: dict | None = None, conversation_memory: dict | None = None) -> dict:
    result = classify_cskh_message(event.text or event.caption, media_type=event.media_type, kb=kb, conversation_memory=conversation_memory)
    if result.get("ticket") or result.get("handoff"):
        result["ticket_preview"] = build_ticket_draft(result, event, text=event.text or event.caption)
    return result


def ignored_business_event_classification(event: BusinessMessageEvent | None, reason: str) -> dict:
    return {
        "matched": False,
        "intent_id": "ignored_business_event",
        "reply": "",
        "reply_preview": "",
        "handoff": False,
        "handoff_required": False,
        "ticket": False,
        "ticket_required": False,
        "confidence": 0.0,
        "severity": "normal",
        "public_safe": True,
        "block_reason": str(reason or ""),
        "media_type": str(event.media_type if event else ""),
    }


def playbook_test_message(text: str) -> dict:
    classification = classify_cskh_message(text, variation_seed=text)
    return {
        "input": str(text or ""),
        "intent_id": str(classification.get("intent_id") or ""),
        "reply": str(classification.get("reply") or ""),
        "playbook_scenario_id": str(classification.get("playbook_scenario_id") or ""),
        "policy_claims": classification.get("playbook_policy_claims") or {},
        "would_handoff": bool(classification.get("handoff_required") or classification.get("handoff")),
        "would_queue_learning": bool(classification.get("would_queue_learning")),
        "status": playbook_status(),
    }


def public_reply_is_safe(reply: str) -> bool:
    folded = _fold(reply)
    hard_forbidden = tuple(_fold(term) for term in PUBLIC_FORBIDDEN_TERMS + UNSAFE_PROMISE_TERMS)
    return not any(term and term in folded for term in hard_forbidden)


async def process_business_event_runtime(
    event: BusinessMessageEvent,
    context: Any,
    *,
    state: dict,
    save_state_fn: Any,
    bot_user_id: str = "",
    bot_username: str = "",
    allow_debounce: bool = True,
    schedule_buffer_fn: Any = None,
    notify_admin_fn: Any = None,
) -> dict:
    clean = record_business_message_received(state, event)
    if clean.get("enabled"):
        clean = upsert_business_connection_from_message(clean, event)
    chat_id = str(event.chat_id or "")
    preliminary_guard = evaluate_auto_reply_guard(
        clean,
        event,
        bot_user_id=bot_user_id,
        bot_username=bot_username,
        classification=None,
    )
    preliminary_block = preliminary_guard.get("block_reason") or ""
    if preliminary_block in {
        "self_or_outbound_message",
        "non_text_or_service_event",
        "already_replied_event",
        "command",
        "deleted",
        "missing_business_connection_id",
    }:
        classification = ignored_business_event_classification(event, preliminary_block)
        clean = record_suppressed(clean, event, classification, preliminary_guard)
        save_state_fn(clean)
        return {"sent": False, "classification": classification, "guard": preliminary_guard}
    memory = get_conversation_memory(clean, chat_id)
    classification = classify_business_event(event, conversation_memory=memory)
    if str(classification.get("severity") or "") == "urgent" and clean.get("message_buffers", {}).get(chat_id):
        clean, _dropped = pop_message_buffer(clean, chat_id, force=True)
    guard = evaluate_auto_reply_guard(clean, event, bot_user_id=bot_user_id, bot_username=bot_username, classification=classification)
    if not guard.get("allowed"):
        clean = record_suppressed(clean, event, classification, guard)
        clean = update_conversation_memory(clean, event, classification)
        save_state_fn(clean)
        return {"sent": False, "classification": classification, "guard": guard}
    if allow_debounce and should_debounce_message(clean, event, classification):
        clean = append_message_buffer(clean, event)
        debounce_guard = {
            **guard,
            "allowed": False,
            "debounce_pending": True,
            "block_reason": "debounce_pending",
            "block_reason_detail": "waiting for quick follow-up messages before replying",
        }
        clean["last_debounce_buffer_summary"] = debounce_buffer_summary(clean, chat_id)
        clean = record_suppressed(clean, event, classification, debounce_guard)
        clean = update_conversation_memory(clean, event, classification)
        save_state_fn(clean)
        if schedule_buffer_fn:
            schedule_buffer_fn(event.chat_id, context)
        return {"sent": False, "buffered": True, "classification": classification, "guard": debounce_guard}
    reply = str(classification.get("reply") or "").strip()
    if not reply or not classification.get("public_safe", True):
        classification["intent_id"] = "out_of_scope"
        classification["handoff"] = True
        classification["handoff_required"] = True
        classification["ticket"] = True
        classification["ticket_required"] = True
        reply = "TOAN AAS đã nhận tin nhắn. Nội dung này cần admin xem thêm để tránh trả lời sai."
    try:
        send_result = await send_business_message(
            context.bot,
            event.business_connection_id,
            event.chat_id,
            reply,
            reply_to_message_id=event.message_id,
        )
    except Exception as exc:
        failure_guard = {
            **guard,
            "allowed": False,
            "send_failed": True,
            "block_reason": "send_failed",
            "block_reason_detail": type(exc).__name__,
        }
        clean = record_suppressed(clean, event, classification, failure_guard)
        clean = update_conversation_memory(clean, event, classification)
        save_state_fn(clean)
        return {"sent": False, "classification": classification, "guard": failure_guard, "error": type(exc).__name__}
    clean = record_auto_reply(clean, event, classification, send_result, guard=guard)
    clean = update_conversation_memory(clean, event, classification, reply=reply)
    if should_queue_learning(classification, event.text or event.caption):
        clean, _candidate = add_learning_candidate(
            clean,
            event,
            classification,
            text=event.text or event.caption,
            reply_sent=reply,
        )
    if classification.get("handoff"):
        clean = set_handoff(clean, event.chat_id, True, str(classification.get("intent_id") or "handoff"))
    save_state_fn(clean)
    if classification.get("handoff") and notify_admin_fn:
        await notify_admin_fn(
            context,
            "🎧 <b>CSKH business handoff required</b>",
            [
                f"• Chat: <code>{html.escape(str(event.chat_id))}</code>",
                f"• Connection: <code>{html.escape(mask_business_connection_id(event.business_connection_id))}</code>",
                f"• Intent: <code>{html.escape(str(classification.get('intent_id') or '-'))}</code>",
                f"• Message id: <code>{html.escape(str(event.message_id or '-'))}</code>",
                "• Auto-reply sent once, handoff guard is now active.",
            ],
        )
    return {"sent": True, "classification": classification, "guard": guard, "send_result": send_result}


def evaluate_auto_reply_guard(
    state: dict,
    event: BusinessMessageEvent,
    *,
    bot_user_id: str | int | None = None,
    bot_username: str | None = None,
    now: float | None = None,
    cooldown_seconds: int | None = None,
    classification: dict | None = None,
) -> dict:
    clean = normalize_state(state)
    current = time.time() if now is None else float(now)
    cooldown = int(cooldown_seconds or os.getenv("CSKH_AUTO_REPLY_COOLDOWN_SECONDS") or DEFAULT_COOLDOWN_SECONDS)
    key = business_message_key(event)
    idempotency_key = business_message_idempotency_key(event)
    chat_id = str(event.chat_id or "")
    cooldown_key = business_message_cooldown_key(event, classification)
    duplicate_key = business_message_duplicate_key(event, classification)
    recent_duplicate = clean.get("recent_message_keys", {}).get(duplicate_key) or {}
    recent_duplicate_at = float((recent_duplicate or {}).get("at") or 0)
    pricing_bypass = has_pricing_keyword(event.text or event.caption)
    connection = clean["connections"].get(str(event.business_connection_id or "")) or {}
    self_outbound_reasons = business_event_self_or_outbound_reasons(
        event,
        bot_user_id=bot_user_id,
        bot_username=bot_username,
        connection=connection,
    )
    event.direction_guess = business_event_direction_guess(
        event,
        bot_user_id=bot_user_id,
        bot_username=bot_username,
        connection=connection,
    )
    meaningful_text = business_event_has_meaningful_text(event)
    actionable_media = business_event_has_actionable_media(event)
    debug = {
        "allowed": True,
        "disabled_suppressed": False,
        "already_replied_event_suppressed": False,
        "duplicate_suppressed": False,
        "cooldown_suppressed": False,
        "handoff_suppressed": False,
        "self_or_outbound_suppressed": False,
        "self_message_suppressed": False,
        "admin_manual_suppressed": False,
        "non_text_or_service_suppressed": False,
        "command_suppressed": False,
        "deleted_suppressed": False,
        "missing_business_connection_id_suppressed": False,
        "pricing_cooldown_bypass": pricing_bypass,
        "direction_guess": event.direction_guess,
        "idempotency_key": idempotency_key,
        "self_outbound_detection": ",".join(self_outbound_reasons),
        "actionable_media": actionable_media,
    }
    if not clean.get("enabled"):
        debug["disabled_suppressed"] = True
    if not str(event.business_connection_id or "").strip():
        debug["missing_business_connection_id_suppressed"] = True
    if self_outbound_reasons:
        debug["self_or_outbound_suppressed"] = True
        debug["block_reason_detail"] = ",".join(self_outbound_reasons)
    if event.from_is_bot or (bot_user_id and str(event.from_user_id or "") == str(bot_user_id)):
        debug["self_message_suppressed"] = True
    if (event.has_service_payload or event.media_type or not meaningful_text) and not meaningful_text and not actionable_media:
        debug["non_text_or_service_suppressed"] = True
        debug.setdefault("block_reason_detail", "no useful customer text in business event")
    if key in clean["processed_messages"] or idempotency_key in clean.get("replied_event_keys", {}):
        debug["already_replied_event_suppressed"] = True
        debug["duplicate_suppressed"] = True
        debug.setdefault("block_reason_detail", "same Telegram business message key was already processed")
    elif recent_duplicate_at and current - recent_duplicate_at < cooldown:
        debug["duplicate_suppressed"] = True
        debug.setdefault("block_reason_detail", "same normalized message and intent was already answered recently")
    if key in clean["deleted_messages"]:
        debug["deleted_suppressed"] = True
    if handoff_required(clean, chat_id):
        debug["handoff_suppressed"] = True
    if event.from_user_id and str(event.from_user_id) == str(connection.get("user_id") or ""):
        debug["admin_manual_suppressed"] = True
    if str(event.text or event.caption or "").strip().startswith("/"):
        debug["command_suppressed"] = True
    last_reply = float(clean["last_auto_reply_at"].get(cooldown_key) or 0)
    if last_reply and current - last_reply < cooldown and not pricing_bypass:
        debug["cooldown_suppressed"] = True
        debug.setdefault("block_reason_detail", "same normalized message and intent is still inside cooldown window")
    debug["allowed"] = not any(value for key_name, value in debug.items() if key_name.endswith("_suppressed"))
    debug["message_key"] = key
    debug["cooldown_key"] = cooldown_key
    debug["duplicate_key"] = duplicate_key
    debug["cooldown_seconds"] = cooldown
    debug["block_reason"] = guard_block_reason(debug)
    debug.setdefault("block_reason_detail", "")
    return debug


def record_auto_reply(state: dict, event: BusinessMessageEvent, classification: dict, send_result: dict | None = None, guard: dict | None = None) -> dict:
    clean = normalize_state(state)
    now = time.time()
    key = business_message_key(event)
    idempotency_key = business_message_idempotency_key(event)
    cooldown_key = business_message_cooldown_key(event, classification)
    duplicate_key = business_message_duplicate_key(event, classification)
    clean["processed_messages"][key] = {"at": now, "intent_id": classification.get("intent_id")}
    clean["replied_event_keys"][idempotency_key] = {"at": now, "intent_id": classification.get("intent_id")}
    clean["last_auto_reply_at"][cooldown_key] = now
    clean["recent_message_keys"][duplicate_key] = {"at": now, "intent_id": classification.get("intent_id")}
    clean["last_intent"][str(event.chat_id)] = str(classification.get("intent_id") or "")
    clean["last_debug"] = {
        **dict(guard or {}),
        "classified_intent": classification.get("intent_id"),
        "confidence": classification.get("confidence"),
        "severity": classification.get("severity"),
        "ticket_required": bool(classification.get("ticket") or classification.get("ticket_required")),
        "reply_sent": True,
        "reply_method_business_connection_id_present": bool(
            (send_result or {}).get("payload", {}).get("business_connection_id")
        ),
        "block_reason": "",
        "block_reason_detail": "",
        "cooldown_key": cooldown_key,
        "duplicate_key": duplicate_key,
        "idempotency_key": idempotency_key,
        "handler_path": "business_message_runtime",
        "brain_path": _brain_path_for_classification(classification),
        "self_outbound_detection": str((guard or {}).get("self_outbound_detection") or ""),
    }
    clean = _record_business_trace(
        clean,
        event=event,
        classification=classification,
        replied=True,
        reply_preview=str(classification.get("reply") or ""),
        handler_path="business_message_runtime",
        brain_path=_brain_path_for_classification(classification),
        cooldown_key=cooldown_key,
        duplicate_key=duplicate_key,
        idempotency_key=idempotency_key,
        self_outbound_detection=str((guard or {}).get("self_outbound_detection") or ""),
        eligible=True,
    )
    _prune_dict(clean["processed_messages"], 500)
    _prune_timestamp_dict(clean["last_auto_reply_at"], 500)
    _prune_dict(clean["recent_message_keys"], 500)
    _prune_dict(clean["replied_event_keys"], 500)
    return clean


def record_suppressed(state: dict, event: BusinessMessageEvent | None, classification: dict | None, guard: dict) -> dict:
    clean = normalize_state(state)
    block_reason = str((guard or {}).get("block_reason") or guard_block_reason(guard) or "no_reply_generated")
    eligible = block_reason not in {
        "disabled",
        "handoff",
        "self_message",
        "admin_manual",
        "self_or_outbound_message",
        "non_text_or_service_event",
        "already_replied_event",
        "command",
        "deleted",
        "missing_business_connection_id",
    }
    clean["last_debug"] = {
        **dict(guard or {}),
        "classified_intent": (classification or {}).get("intent_id"),
        "reply_sent": False,
        "reply_method_business_connection_id_present": bool(event and event.business_connection_id),
        "block_reason": block_reason,
        "block_reason_detail": str((guard or {}).get("block_reason_detail") or ""),
        "cooldown_key": str((guard or {}).get("cooldown_key") or (business_message_cooldown_key(event, classification) if event else "")),
        "duplicate_key": str((guard or {}).get("duplicate_key") or (business_message_duplicate_key(event, classification) if event else "")),
        "idempotency_key": str((guard or {}).get("idempotency_key") or (business_message_idempotency_key(event) if event else "")),
        "handler_path": "business_message_runtime",
        "brain_path": _brain_path_for_classification(classification),
        "self_outbound_detection": str((guard or {}).get("self_outbound_detection") or ""),
    }
    if event and classification:
        clean["last_intent"][str(event.chat_id)] = str(classification.get("intent_id") or "")
    clean = _record_business_trace(
        clean,
        event=event,
        classification=classification,
        replied=False,
        block_reason=block_reason,
        block_reason_detail=str((guard or {}).get("block_reason_detail") or ""),
        reply_preview=str((classification or {}).get("reply") or ""),
        handler_path="business_message_runtime",
        brain_path=_brain_path_for_classification(classification),
        cooldown_key=clean["last_debug"].get("cooldown_key") or "",
        duplicate_key=clean["last_debug"].get("duplicate_key") or "",
        idempotency_key=clean["last_debug"].get("idempotency_key") or "",
        self_outbound_detection=clean["last_debug"].get("self_outbound_detection") or "",
        eligible=eligible,
    )
    return clean


def _prune_dict(payload: dict, max_items: int) -> None:
    if len(payload) <= max_items:
        return
    sortable = sorted(payload.items(), key=lambda item: float((item[1] or {}).get("at") or 0))
    for key, _value in sortable[: max(0, len(payload) - max_items)]:
        payload.pop(key, None)


def _prune_timestamp_dict(payload: dict, max_items: int) -> None:
    if len(payload) <= max_items:
        return
    sortable = sorted(payload.items(), key=lambda item: float(item[1] or 0))
    for key, _value in sortable[: max(0, len(payload) - max_items)]:
        payload.pop(key, None)


def allowed_updates_include_business(allowed_updates: Any) -> bool:
    updates = list(allowed_updates or [])
    return all(item in updates for item in BUSINESS_UPDATE_TYPES)


def guard_block_reason(debug: dict | None) -> str:
    payload = dict(debug or {})
    reasons = (
        ("disabled_suppressed", "disabled"),
        ("self_or_outbound_suppressed", "self_or_outbound_message"),
        ("non_text_or_service_suppressed", "non_text_or_service_event"),
        ("missing_business_connection_id_suppressed", "missing_business_connection_id"),
        ("already_replied_event_suppressed", "already_replied_event"),
        ("duplicate_suppressed", "exact_duplicate"),
        ("cooldown_suppressed", "cooldown_same_intent"),
        ("debounce_pending", "debounce_pending"),
        ("send_failed", "send_failed"),
        ("exception", "exception"),
        ("handoff_suppressed", "handoff"),
        ("self_message_suppressed", "self_message"),
        ("admin_manual_suppressed", "admin_manual"),
        ("command_suppressed", "command"),
        ("deleted_suppressed", "deleted"),
    )
    for key, label in reasons:
        if payload.get(key):
            return label
    return ""


def status_payload(state: dict, *, bot_status: dict | None = None, allowed_updates: Any = None) -> dict:
    clean = normalize_state(state)
    connections = list(clean["connections"].values())
    latest = max(connections, key=lambda item: float(item.get("updated_at") or 0), default={})
    active_connection_count = len([item for item in connections if item.get("is_enabled", True)])
    enabled = bool(clean.get("enabled"))
    auto_reply_mode = "off"
    if enabled:
        auto_reply_mode = "on" if active_connection_count else "armed"
    last_debug = dict(clean.get("last_debug") or {})
    return {
        "enabled": enabled,
        "bot_can_connect_to_business": (bot_status or {}).get("can_connect_to_business", "unknown"),
        "active_connection_count": active_connection_count,
        "latest_connection_id_masked": latest.get("masked_id") or "-",
        "allowed_updates_include_business": allowed_updates_include_business(allowed_updates),
        "auto_reply_mode": auto_reply_mode,
        "waiting_for_first_business_message": bool(enabled and not active_connection_count),
        "handoff_count": len(clean["handoff_chats"]),
        "last_business_update_at": clean.get("last_business_update_at"),
        "last_business_message_at": clean.get("last_business_message_at"),
        "receiving_business_updates": bool(clean.get("last_business_update_at")),
        "receiving_business_messages": bool(clean.get("last_business_message_at")),
        "last_debug": last_debug,
        "last_block_reason": last_debug.get("block_reason") or guard_block_reason(last_debug),
        "last_block_reason_detail": last_debug.get("block_reason_detail") or "",
        "last_business_message": dict(clean.get("last_business_message") or {}),
        "last_eligible_message": dict(clean.get("last_eligible_message") or {}),
        "last_ignored_message": dict(clean.get("last_ignored_message") or {}),
        "last_reply": dict(clean.get("last_reply") or {}),
        "last_reply_sent": bool(last_debug.get("reply_sent")),
        "last_intent": last_debug.get("classified_intent") or "",
        "last_cooldown_key": last_debug.get("cooldown_key") or "",
        "last_duplicate_key": last_debug.get("duplicate_key") or "",
        "last_ignored_reason": (clean.get("last_ignored_message") or {}).get("block_reason") or "",
        "last_idempotency_key": last_debug.get("idempotency_key") or "",
        "last_self_outbound_detection": last_debug.get("self_outbound_detection") or "",
        "last_handler_path": last_debug.get("handler_path") or "",
        "last_brain_path": last_debug.get("brain_path") or "",
        "last_debounce_buffer_summary": dict(clean.get("last_debounce_buffer_summary") or debounce_buffer_summary(clean)),
        "business_trace": list(clean.get("business_trace") or [])[-BUSINESS_TRACE_LIMIT:],
        "state_source": str(default_state_path()),
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
