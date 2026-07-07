from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

from services import telegram_business_support as cskh


STATE_VERSION = 1
TRACE_LIMIT = 10
DEFAULT_REPLY = (
    "Dạ em chưa hiểu rõ ý mình. Anh/chị nói rõ hơn muốn hỏi về giá, cách dùng, "
    "tạo prompt, ảnh, video, voice, nhạc hay SubDub ạ?"
)
CONSENT_TEXT = (
    "Bạn đồng ý cho AAS ONE AI Chatbot đọc ngữ cảnh trò chuyện trong bot, dùng dữ liệu "
    "sản phẩm/tính năng/bảng giá của TOAN AAS, và hỗ trợ bạn thao tác trong bot. Với tác vụ "
    "tốn Xu như tạo ảnh/video/voice/nhạc, bot chỉ chuẩn bị quy trình và vẫn phải hỏi xác nhận "
    "trước khi trừ Xu hoặc gọi provider."
)
INTERNAL_BLOCK_REPLY = (
    "Dạ phần kỹ thuật nội bộ em không mở ra trong chat. Nếu anh/chị cần kiểm tra lỗi, "
    "mình gửi mô tả vấn đề hoặc mã đơn/task công khai, em sẽ hướng dẫn theo luồng hỗ trợ an toàn ạ."
)
POLICY_GUARD_REPLY = (
    "Dạ phần này cần admin kiểm tra trước nên em không tự hứa hoàn Xu, cộng Xu hay ưu đãi thay admin. "
    "Anh/chị gửi giúp mã giao dịch/task và mô tả lỗi, em ghi nhận vào hướng hỗ trợ để admin xem ạ."
)


def default_state_path() -> Path:
    configured = os.getenv("AICHAT_COPILOT_STATE_FILE", "").strip()
    return Path(configured) if configured else Path("data") / "aichat_copilot_state.json"


def default_state() -> dict:
    return {
        "version": STATE_VERSION,
        "users": {},
        "traces": {},
        "last_debug": {},
    }


def normalize_state(state: dict | None) -> dict:
    clean = default_state()
    if isinstance(state, dict):
        clean.update(state)
    clean["version"] = STATE_VERSION
    for key in ("users", "traces", "last_debug"):
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


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFD", str(value or "").lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.replace("đ", "d").split())


def _safe_text(text: str, limit: int = 1800) -> str:
    clean = re.sub(r"\s+", " ", str(text or "").strip())
    return clean[:limit]


def _hash_text(text: str) -> str:
    folded = _fold(text)[:500]
    return hashlib.sha1(folded.encode("utf-8")).hexdigest()[:12] if folded else "empty"


def user_state(state: dict, user_id: str | int) -> dict:
    clean = normalize_state(state)
    return dict(clean["users"].get(str(user_id)) or {})


def is_enabled(state: dict, user_id: str | int) -> bool:
    return bool(user_state(state, user_id).get("enabled"))


def was_explicitly_disabled(state: dict, user_id: str | int) -> bool:
    user = user_state(state, user_id)
    return bool(user) and not bool(user.get("enabled"))


def action_permission_enabled(state: dict, user_id: str | int) -> bool:
    return bool(user_state(state, user_id).get("assist_actions"))


def request_enable(state: dict, user_id: str | int, *, now: float | None = None) -> tuple[dict, dict]:
    clean = normalize_state(state)
    uid = str(user_id)
    current = time.time() if now is None else float(now)
    user = dict(clean["users"].get(uid) or {})
    user["pending_consent"] = True
    user["updated_at"] = current
    clean["users"][uid] = user
    result = {
        "enabled": False,
        "consent_required": True,
        "reply": CONSENT_TEXT,
        "action_guard": "consent_required",
    }
    clean = record_trace(clean, uid, text="/aichat_on", result=result, replied=True)
    return clean, result


def enable_with_consent(state: dict, user_id: str | int, *, now: float | None = None) -> tuple[dict, dict]:
    clean = normalize_state(state)
    uid = str(user_id)
    current = time.time() if now is None else float(now)
    user = dict(clean["users"].get(uid) or {})
    user.update(
        {
            "enabled": True,
            "consented": True,
            "pending_consent": False,
            "consent_at": user.get("consent_at") or current,
            "updated_at": current,
            "assist_actions": bool(user.get("assist_actions")),
        }
    )
    clean["users"][uid] = user
    result = {
        "enabled": True,
        "reply": "✅ Đã bật AAS ONE AI Chatbot. Mình có thể hỏi giá, cách dùng, tạo prompt hoặc nhờ em chuẩn bị flow trong bot.",
        "action_guard": "enabled_after_consent",
    }
    clean = record_trace(clean, uid, text="consent_on", result=result, replied=True)
    return clean, result


def disable_user(state: dict, user_id: str | int, *, now: float | None = None) -> tuple[dict, dict]:
    clean = normalize_state(state)
    uid = str(user_id)
    current = time.time() if now is None else float(now)
    user = dict(clean["users"].get(uid) or {})
    user.update({"enabled": False, "pending_consent": False, "updated_at": current})
    clean["users"][uid] = user
    result = {
        "enabled": False,
        "reply": "✅ Đã tắt AI Chatbot. CSKH/Business CSKH không bị thay đổi.",
        "action_guard": "disabled_by_user",
    }
    clean = record_trace(clean, uid, text="/aichat_off", result=result, replied=True)
    return clean, result


def set_action_permission(state: dict, user_id: str | int, enabled: bool, *, now: float | None = None) -> tuple[dict, dict]:
    clean = normalize_state(state)
    uid = str(user_id)
    current = time.time() if now is None else float(now)
    user = dict(clean["users"].get(uid) or {})
    if not user.get("enabled"):
        clean, consent = request_enable(clean, uid, now=current)
        consent["needs_enable_first"] = True
        return clean, consent
    user["assist_actions"] = bool(enabled)
    user["updated_at"] = current
    clean["users"][uid] = user
    result = {
        "enabled": True,
        "assist_actions": bool(enabled),
        "reply": "✅ AI được phép hỗ trợ dẫn vào flow và chuẩn bị nội dung. Tác vụ tốn Xu vẫn dừng ở màn xác nhận.",
        "action_guard": "assist_actions_enabled" if enabled else "assist_actions_disabled",
    }
    clean = record_trace(clean, uid, text="assist_on" if enabled else "assist_off", result=result, replied=True)
    return clean, result


def status_payload(state: dict, user_id: str | int) -> dict:
    clean = normalize_state(state)
    user = user_state(clean, user_id)
    trace = list(clean["traces"].get(str(user_id)) or [])
    return {
        "enabled": bool(user.get("enabled")),
        "consented": bool(user.get("consented")),
        "pending_consent": bool(user.get("pending_consent")),
        "assist_actions": bool(user.get("assist_actions")),
        "updated_at": user.get("updated_at"),
        "last_trace": trace[-1] if trace else {},
        "trace": trace[-TRACE_LIMIT:],
        "state_source": str(default_state_path()),
    }


def _flow_for_text(text: str, classification: dict | None = None) -> dict:
    folded = _fold(text)
    intent_id = str((classification or {}).get("intent_id") or "")
    product = str((classification or {}).get("primary_product") or (classification or {}).get("product") or "")
    if any(term in folded for term in ("anh", "hinh", "tao anh", "sua anh", "prompt anh")) or product in {"image_ai", "image_to_video"}:
        return {"kind": "image", "label": "Mở tạo ảnh AI", "callback": "menu|main_image"}
    if any(term in folded for term in ("video", "clip", "product video", "ghep anh")) or "video" in intent_id or product in {"product_video", "image_to_video"}:
        return {"kind": "video", "label": "Mở tạo video AI", "callback": "menu|main_video"}
    if any(term in folded for term in ("subdub", "phu de", "long tieng", "subtitle", "dub")):
        return {"kind": "subdub", "label": "Mở dịch/phụ đề/lồng tiếng", "callback": "menu|translate"}
    if any(term in folded for term in ("voice", "tts", "giong doc", "giong nam", "giong nu")):
        return {"kind": "voice", "label": "Mở voice/audio", "callback": "menu|main_music"}
    if any(term in folded for term in ("nhac", "music", "sfx", "bai hat")):
        return {"kind": "music", "label": "Mở nhạc/SFX", "callback": "menu|main_music"}
    return {"kind": "general", "label": "Mở Công cụ miễn phí", "callback": "freehub|main"}


def _is_internal_question(text: str) -> bool:
    folded = _fold(text)
    return any(term in folded for term in ("provider", "api", "debug", "traceback", "stack", "key4u", "shopaikey", "gemini", "openai", "suno"))


def _is_refund_or_credit_request(text: str, classification: dict | None = None) -> bool:
    folded = _fold(text)
    intent_id = str((classification or {}).get("intent_id") or "")
    return intent_id in {"refund", "refund_request"} or any(term in folded for term in ("hoan xu", "hoan tien", "cong xu", "cong tien", "voucher", "vip"))


def _is_prompt_request(text: str) -> bool:
    folded = _fold(text)
    return any(term in folded for term in ("tao prompt", "viet prompt", "prompt anh", "prompt video", "caption", "hashtag", "y tuong", "kich ban"))


def _is_real_creation_request(text: str) -> bool:
    folded = _fold(text)
    if any(term in folded for term in ("bi ket", "ket file", "khong ra file", "chua ra file", "chua thay file", "loi", "fail", "hong file")):
        return False
    real_terms = ("tao that", "lam that", "render", "xuat file", "ra file", "tao anh", "tao video", "tao nhac", "long tieng", "phu de", "doc voice")
    return any(term in folded for term in real_terms) and not any(term in folded for term in ("prompt", "y tuong", "caption", "huong dan"))


def _prompt_reply(text: str) -> str:
    brief = _safe_text(text, 500)
    return (
        "Dạ được ạ. Đây là prompt miễn phí để mình dùng làm nháp:\n\n"
        f"<code>{html.escape(brief)}\n\n"
        "Mục tiêu: tạo nội dung rõ sản phẩm, bối cảnh, phong cách, tỉ lệ khung hình và CTA. "
        "Phong cách: tự nhiên, sạch, dễ hiểu, không phóng đại. "
        "Nếu dùng cho ảnh/video thật, hãy kiểm tra lại trước màn xác nhận.</code>"
    )


def _flow_reply(flow: dict, *, allowed_to_assist: bool) -> str:
    if allowed_to_assist:
        return (
            f"Dạ em có thể chuẩn bị giúp và dẫn mình tới flow <b>{flow['label']}</b>. "
            "Em chỉ chuẩn bị nội dung/luồng thao tác; tác vụ tốn Xu vẫn dừng ở màn báo giá hoặc xác nhận chuẩn để anh/chị tự bấm."
        )
    return (
        f"Dạ mình nên đi theo flow <b>{flow['label']}</b>. Hiện AI Chatbot mới được phép tư vấn, chưa được hỗ trợ thao tác trong bot. "
        "Nếu muốn em dẫn vào flow và chuẩn bị prompt/session, hãy bấm nút cấp quyền hỗ trợ thao tác. Tác vụ tốn Xu vẫn phải dừng ở màn xác nhận."
    )


def _sources_for_classification(classification: dict, *, fallback: bool = False, learning: bool = False) -> list[str]:
    sources = ["aichat"]
    intent_id = str(classification.get("intent_id") or "")
    if classification.get("knowledge_entry_id") or classification.get("training_data_version"):
        sources.append("cskh_knowledge")
    if classification.get("playbook_scenario_id"):
        sources.append("cskh_playbook")
    if classification.get("pricing_source") == "config" or classification.get("price_text") or "pricing" in intent_id:
        sources.append("pricing")
    if fallback:
        sources.append("fallback")
    if learning:
        sources.append("learning_queue")
    return list(dict.fromkeys(sources))


def _safe_reply(reply: str) -> str:
    clean = str(reply or "").strip() or DEFAULT_REPLY
    if not cskh.public_reply_is_safe(clean):
        return DEFAULT_REPLY
    unsafe_success = ("đã tạo xong", "da tao xong", "đã hoàn xu", "da hoan xu", "đã cộng xu", "da cong xu")
    folded = _fold(clean)
    if any(term in folded for term in unsafe_success):
        return DEFAULT_REPLY
    return clean


def _queue_learning(text: str, classification: dict, reply: str, user_id: str | int) -> dict:
    event = cskh.BusinessMessageEvent(
        update_type="aichat_message",
        business_connection_id="",
        chat_id=str(user_id),
        from_user_id=str(user_id),
        from_is_bot=False,
        text=text,
        caption="",
        message_id=_hash_text(text),
        timestamp=time.time(),
        media_type="",
    )
    shared_state = cskh.load_state()
    shared_state, candidate = cskh.add_learning_candidate(
        shared_state,
        event,
        classification,
        text=text,
        reply_sent=reply,
        reason="aichat_unknown_needs_admin_review",
    )
    cskh.save_state(shared_state)
    return candidate


def classify_message(text: str, *, user_id: str | int = "", conversation_memory: dict | None = None) -> dict:
    clean_text = _safe_text(text, 2000)
    classification = cskh.classify_cskh_message(
        clean_text,
        variation_seed=f"aichat:{user_id}:{_hash_text(clean_text)}",
        conversation_memory=conversation_memory,
    )
    classification["entry"] = "aichat"
    return classification


def build_reply(state: dict, user_id: str | int, text: str, *, queue_unknown: bool = True) -> dict:
    clean_text = _safe_text(text, 2000)
    classification = classify_message(clean_text, user_id=user_id)
    intent_id = str(classification.get("intent_id") or "out_of_scope")
    assist_actions = action_permission_enabled(state, user_id)
    fallback = intent_id in {"out_of_scope", "vague_or_unclear"} or str(classification.get("confidence") or "") == "low"
    learning_candidate = {}
    action_guard = "answer_only"
    permission = "default_answer"
    flow = {}
    reply = str(classification.get("reply") or DEFAULT_REPLY)

    if _is_internal_question(clean_text):
        reply = INTERNAL_BLOCK_REPLY
        action_guard = "internal_info_blocked"
        fallback = True
    elif _is_refund_or_credit_request(clean_text, classification):
        reply = POLICY_GUARD_REPLY
        action_guard = "admin_review_required"
    elif _is_real_creation_request(clean_text):
        flow = _flow_for_text(clean_text, classification)
        permission = "assist_actions" if assist_actions else "default_answer"
        action_guard = "prepare_flow_stop_at_confirm" if assist_actions else "needs_action_permission"
        reply = _flow_reply(flow, allowed_to_assist=assist_actions)
    elif _is_prompt_request(clean_text):
        reply = _prompt_reply(clean_text)
        action_guard = "free_text_only"
        permission = "default_answer"
    elif fallback:
        reply = DEFAULT_REPLY

    reply = _safe_reply(reply)
    should_learn = bool(queue_unknown and (fallback or cskh.should_queue_learning(classification, clean_text)))
    if should_learn:
        learning_candidate = _queue_learning(clean_text, classification, reply, user_id)
    sources = _sources_for_classification(classification, fallback=fallback, learning=bool(learning_candidate))
    return {
        "entry": "aichat",
        "intent_id": intent_id,
        "classification": classification,
        "reply": reply,
        "source": sources,
        "permission": permission,
        "action_guard": action_guard,
        "target_flow": flow,
        "learning_candidate_id": learning_candidate.get("id") or "",
        "provider_call_allowed": False,
        "xu_charge_allowed": False,
        "invoice_confirm_allowed": False,
        "public_safe": cskh.public_reply_is_safe(reply),
    }


def process_message(state: dict, user_id: str | int, text: str, *, queue_unknown: bool = True) -> tuple[dict, dict]:
    clean = normalize_state(state)
    uid = str(user_id)
    if not is_enabled(clean, uid):
        result = {
            "entry": "aichat",
            "replied": False,
            "reply": "",
            "source": ["aichat"],
            "intent_id": "",
            "permission": "disabled",
            "action_guard": "disabled_no_reply",
        }
        if was_explicitly_disabled(clean, uid):
            clean = record_trace(clean, uid, text=text, result=result, replied=False)
        return clean, result
    result = build_reply(clean, uid, text, queue_unknown=queue_unknown)
    result["replied"] = True
    clean = record_trace(clean, uid, text=text, result=result, replied=True)
    return clean, result


def preview_message(text: str, *, user_id: str | int = "test") -> dict:
    state = default_state()
    state, _enabled = enable_with_consent(state, user_id)
    state, result = process_message(state, user_id, text, queue_unknown=False)
    return result


def record_trace(state: dict, user_id: str | int, *, text: str, result: dict, replied: bool) -> dict:
    clean = normalize_state(state)
    uid = str(user_id)
    entry = {
        "at": time.time(),
        "entry": "aichat",
        "text_hash": _hash_text(text),
        "text_preview": _safe_text(text, 180),
        "intent_id": str(result.get("intent_id") or ""),
        "source": list(result.get("source") or ["aichat"]),
        "permission": str(result.get("permission") or ""),
        "action_guard": str(result.get("action_guard") or ""),
        "target_flow": dict(result.get("target_flow") or {}),
        "learning_candidate_id": str(result.get("learning_candidate_id") or ""),
        "provider_call_allowed": False,
        "xu_charge_allowed": False,
        "replied": bool(replied),
        "reply_preview": _safe_text(result.get("reply") or "", 240),
    }
    trace = list(clean["traces"].get(uid) or [])
    trace.append(entry)
    clean["traces"][uid] = trace[-TRACE_LIMIT:]
    clean["last_debug"][uid] = entry
    return clean
