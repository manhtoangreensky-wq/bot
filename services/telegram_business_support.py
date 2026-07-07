from __future__ import annotations

import json
import hashlib
import html
import asyncio
import os
import re
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
DEFAULT_CONVERSATION_TTL_SECONDS = 24 * 60 * 60
DEFAULT_MESSAGE_DEBOUNCE_SECONDS = 3
STATE_VERSION = 1
TRAINING_DATA_VERSION_FALLBACK = "0"
CONVERSATION_MEMORY_LIMIT = 500
LEARNING_QUEUE_LIMIT = 200
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
    "gia",
    "bao nhieu",
    "nhieu tien",
    "nhieu xu",
    "phi",
    "goi",
    "re nhat",
    "mien phi",
    "xu",
)


def _is_pricing_question(folded: str) -> bool:
    return any(term in folded for term in PRICING_SIGNAL_TERMS)


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
    }:
        return "pricing"
    if intent in {"vague_or_unclear", "out_of_scope", "product_video_consulting", "product_video_how_to"}:
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
        "last_intent": intent_id,
        "last_product": product,
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
            "message_id": str(event.message_id or ""),
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
    if len(folded.split()) < 3:
        return False
    signals = (
        "gia",
        "bao nhieu",
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


def _intent_lookup(training_data: dict, kb: dict) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for item in _legacy_intents_from_kb(kb):
        merged[_intent_id(item)] = item
    for item in training_data.get("intents") or []:
        merged[_intent_id(item)] = item
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


def classify_cskh_message(
    text: str = "",
    *,
    media_type: str = "",
    kb: dict | None = None,
    training_data: dict | None = None,
    variation_seed: str | int | None = None,
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
    result["would_queue_learning"] = should_queue_learning(result, text)
    if ticket or handoff:
        result["ticket_preview"] = build_ticket_draft(result, text=text)
    return result


def classify_business_event(event: BusinessMessageEvent, kb: dict | None = None) -> dict:
    result = classify_cskh_message(event.text or event.caption, media_type=event.media_type, kb=kb)
    if result.get("ticket") or result.get("handoff"):
        result["ticket_preview"] = build_ticket_draft(result, event, text=event.text or event.caption)
    return result


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
    allow_debounce: bool = True,
    schedule_buffer_fn: Any = None,
    notify_admin_fn: Any = None,
) -> dict:
    clean = record_business_message_received(state, event)
    if clean.get("enabled"):
        clean = upsert_business_connection_from_message(clean, event)
    classification = classify_business_event(event)
    chat_id = str(event.chat_id or "")
    if str(classification.get("severity") or "") == "urgent" and clean.get("message_buffers", {}).get(chat_id):
        clean, _dropped = pop_message_buffer(clean, chat_id, force=True)
    guard = evaluate_auto_reply_guard(clean, event, bot_user_id=bot_user_id)
    if not guard.get("allowed"):
        clean = record_suppressed(clean, event, classification, guard)
        clean = update_conversation_memory(clean, event, classification)
        save_state_fn(clean)
        return {"sent": False, "classification": classification, "guard": guard}
    if allow_debounce and should_debounce_message(clean, event, classification):
        clean = append_message_buffer(clean, event)
        clean = update_conversation_memory(clean, event, classification)
        save_state_fn(clean)
        if schedule_buffer_fn:
            schedule_buffer_fn(event.chat_id, context)
        return {"sent": False, "buffered": True, "classification": classification, "guard": guard}
    reply = str(classification.get("reply") or "").strip()
    if not reply or not classification.get("public_safe", True):
        classification["intent_id"] = "out_of_scope"
        classification["handoff"] = True
        classification["handoff_required"] = True
        classification["ticket"] = True
        classification["ticket_required"] = True
        reply = "TOAN AAS đã nhận tin nhắn. Nội dung này cần admin xem thêm để tránh trả lời sai."
    send_result = await send_business_message(
        context.bot,
        event.business_connection_id,
        event.chat_id,
        reply,
        reply_to_message_id=event.message_id,
    )
    clean = record_auto_reply(clean, event, classification, send_result)
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
        "missing_business_connection_id_suppressed": False,
    }
    if not clean.get("enabled"):
        debug["disabled_suppressed"] = True
    if not str(event.business_connection_id or "").strip():
        debug["missing_business_connection_id_suppressed"] = True
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
    if last_reply and current - last_reply < cooldown and not is_distinct_followup_question(event):
        debug["cooldown_suppressed"] = True
    debug["allowed"] = not any(value for key_name, value in debug.items() if key_name.endswith("_suppressed"))
    debug["message_key"] = key
    debug["cooldown_seconds"] = cooldown
    debug["block_reason"] = guard_block_reason(debug)
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
        "confidence": classification.get("confidence"),
        "severity": classification.get("severity"),
        "ticket_required": bool(classification.get("ticket") or classification.get("ticket_required")),
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


def guard_block_reason(debug: dict | None) -> str:
    payload = dict(debug or {})
    reasons = (
        ("disabled_suppressed", "disabled"),
        ("missing_business_connection_id_suppressed", "missing_business_connection_id"),
        ("duplicate_suppressed", "duplicate"),
        ("cooldown_suppressed", "cooldown"),
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
