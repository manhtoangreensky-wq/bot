from __future__ import annotations

import json
import hashlib
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
STATE_VERSION = 1
TRAINING_DATA_VERSION_FALLBACK = "0"
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


def _next_step_hint(intent: dict) -> str:
    steps = intent.get("safe_next_steps") or []
    if isinstance(steps, str):
        return steps
    return str(steps[0]) if steps else "Hỏi thêm thông tin còn thiếu"


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
    "product_video_how_to",
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
    "greeting",
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
                "description": f"Legacy CSKH.1 intent {intent_id}",
                "priority": 10,
                "confidence_keywords": list(item.get("keywords") or []),
                "example_user_messages": list(item.get("keywords") or [])[:8],
                "required_context_fields": [],
                "reply_templates": [str(item.get("reply") or "")],
                "handoff_required": bool(item.get("handoff")),
                "ticket_required": bool(item.get("ticket") or item.get("handoff")),
                "safe_next_steps": ["Hỏi thêm thông tin còn thiếu"],
                "forbidden_claims": [],
                "severity": "urgent" if intent_id in URGENT_INTENTS else "normal",
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


def _select_intent(text: str, media_type: str, training_data: dict, kb: dict) -> tuple[dict, int, list[str]]:
    query = _fold(text)
    if not query and media_type:
        query = "media file tep anh video audio"
    intents = _intent_lookup(training_data, kb)
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
    if intent_id.startswith("product_video"):
        return "product_video"
    if intent_id.startswith("subdub"):
        return "subdub"
    if intent_id.startswith("music"):
        return "music"
    if intent_id.startswith("voice"):
        return "voice"
    if intent_id.startswith("image"):
        return "image_ai"
    if intent_id in {"premium_private_bot"}:
        return "premium_private_bot"
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
    result = {
        "intent": intent_id,
        "intent_id": intent_id,
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
    if last_reply and current - last_reply < cooldown:
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
