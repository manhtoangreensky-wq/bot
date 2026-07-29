from __future__ import annotations

import copy
import html
import inspect
import math
import re
import time
import uuid
from typing import Any, Awaitable, Callable

from services import local_video_studio_preview as catalog_source


CALLBACK_PREFIX = "lvs27b"
STATE_KEY = "local_video_studio27b_public"
PREVIEW_VERSION = "27B"
SESSION_TTL_SECONDS = 30 * 60
CATALOG_PAGE_SIZE = 4
DETAIL_PAGE_SIZE = 6
MAX_STORED_SESSIONS = 32
MAX_SELECTED_CAPABILITIES = 24
PUBLIC_READINESS_STATES = (
    "CONTRACT_ONLY",
    "LOCAL_PLANNING_READY",
    "REQUIRES_RUNTIME",
    "REQUIRES_PLANNED_SHOOT",
    "NOT_SUPPORTED",
)
PLANNING_LOCKS = {
    "planning_only": True,
    "runtime_registered": False,
    "provider_executable": False,
    "public_ui": False,
}

# The canonical IDs and validator remain owned by the 27A pure catalog service.
LOCAL_RECORD_IDS = catalog_source.LOCAL_RECORD_IDS
PAID_RECORD_IDS = catalog_source.PAID_RECORD_IDS
RECORD_IDS = catalog_source.RECORD_IDS
QA_CAPABILITY_IDS = catalog_source.QA_CAPABILITY_IDS
load_capability_index = catalog_source.load_capability_index
validate_capability_index = catalog_source.validate_capability_index
capability_coverage = catalog_source.capability_coverage
paginate = catalog_source.paginate
PreviewDataError = catalog_source.PreviewDataError
PreviewActionError = catalog_source.PreviewActionError

PUBLIC_RECORD_LABELS_VI = {
    "openmontage_local": "Dựng video cục bộ",
    "editing_grammar": "Kỹ thuật cắt dựng",
    "framing_composition": "Khung hình và bố cục",
    "pacing_storytelling": "Nhịp dựng và kể chuyện",
    "camera_movement": "Chuyển động máy quay",
    "rights_requirements": "Quyền sử dụng nội dung",
    "transition_motion_pack": "Chuyển cảnh và đồ họa chuyển động",
    "sound_design_pack": "Thiết kế âm thanh và hậu kỳ",
    "viral_effects": "Hiệu ứng video sáng tạo",
    "local_free_capabilities": "Công cụ dựng video cục bộ",
    "video_qa": "Kiểm tra chất lượng video",
}


GOAL_OPTIONS = (
    ("cut_pacing", "✂️ Cắt dựng và nhịp"),
    ("reframe", "🎯 Điều chỉnh khung hình và bố cục"),
    ("transition_motion", "✨ Chuyển cảnh và đồ họa chuyển động"),
    ("sound_post", "🎧 Âm thanh và hậu kỳ"),
)
_GOAL_IDS = frozenset(item[0] for item in GOAL_OPTIONS)
_ALLOWED_VERBS = frozenset(
    {"open", "goal", "catalog", "detail", "select", "safety", "summary", "save", "back", "close"}
)
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{4,12}$")
_SCREEN_HISTORY = {
    "goal": (),
    "catalog": ("goal",),
    "detail": ("goal", "catalog"),
    "safety": ("goal", "catalog", "detail"),
    "summary": ("goal", "catalog", "detail", "safety"),
}
_SESSION_FIELDS = frozenset({
    "version", "session_id", "created_at", "updated_at", "screen", "history",
    "goal", "record_id", "selected_ids", "catalog_page", "detail_page",
    "processed_callback_ids",
})


class PublicSessionExpired(PreviewActionError):
    """The public session is no longer fresh."""


def _timestamp(value: object | None = None) -> int:
    if value is None:
        return int(time.time())
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise PreviewActionError("session_timestamp_invalid")
    if not math.isfinite(number) or number < 0:
        raise PreviewActionError("session_timestamp_invalid")
    return int(number)


def _valid_session_id(value: object) -> bool:
    return isinstance(value, str) and bool(_SESSION_ID_RE.fullmatch(value))


def _new_session_id() -> str:
    return uuid.uuid4().hex[:10]


def _record_map(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    validated = validate_capability_index(payload)
    return {str(record["capability_id"]): record for record in validated["capabilities"]}


def _all_capability_to_record(payload: dict[str, object]) -> dict[str, str]:
    result: dict[str, str] = {}
    for record in validate_capability_index(payload)["capabilities"]:
        record_id = str(record["capability_id"])
        for capability_id in record["capability_ids"]:
            result[str(capability_id)] = record_id
    return result


def _public_record_labels_vi() -> dict[str, str]:
    labels = PUBLIC_RECORD_LABELS_VI
    if not isinstance(labels, dict) or tuple(labels) != tuple(LOCAL_RECORD_IDS):
        raise PreviewDataError("public_record_labels_incomplete")
    if len(set(labels.values())) != len(labels) or any(
        not isinstance(label, str) or not label.strip()
        for label in labels.values()
    ):
        raise PreviewDataError("public_record_labels_invalid")
    return labels


def public_readiness(record: dict[str, object]) -> str:
    if not isinstance(record, dict):
        return "NOT_SUPPORTED"
    if str(record.get("requires_planned_shoot") or "").strip().upper() == "REQUIRED":
        return "REQUIRES_PLANNED_SHOOT"
    raw = str(record.get("highest_readiness") or "").strip().upper()
    return {
        "CONTRACT_PASS": "CONTRACT_ONLY",
        "LOCAL_DEMO_PASS": "LOCAL_PLANNING_READY",
        "INSTALLED": "LOCAL_PLANNING_READY",
        "PAID_SMOKE_REQUIRED": "REQUIRES_RUNTIME",
        "NOT_INSTALLED": "NOT_SUPPORTED",
    }.get(raw, "NOT_SUPPORTED")


def public_entry_rows(enabled: object) -> tuple[tuple[str, str], ...]:
    if isinstance(enabled, str):
        is_enabled = enabled.strip().lower() in {"1", "true", "yes", "on"}
    else:
        is_enabled = bool(enabled)
    if not is_enabled:
        return ()
    return (("🧭 Lập kế hoạch dựng video", callback_data("open")),)


def new_session(session_id: str | None = None, *, now: object | None = None) -> dict[str, object]:
    sid = str(session_id or _new_session_id()).strip()
    if not _valid_session_id(sid):
        raise PreviewActionError("session_id_invalid")
    stamp = _timestamp(now)
    return {
        "version": PREVIEW_VERSION,
        "session_id": sid,
        "created_at": stamp,
        "updated_at": stamp,
        "screen": "goal",
        "history": [],
        "goal": "",
        "record_id": "",
        "selected_ids": [],
        "catalog_page": 0,
        "detail_page": 0,
        "processed_callback_ids": [],
    }


def new_store() -> dict[str, object]:
    return {"sessions": {}, "active_by_chat": {}}


def session_store_key(user_id: object, chat_id: object, session_id: object) -> str:
    uid = str(user_id or "").strip()
    cid = str(chat_id or "").strip()
    sid = str(session_id or "").strip()
    if not uid or not cid or not _valid_session_id(sid):
        raise PreviewActionError("session_store_key_invalid")
    return f"{uid}:{cid}:{sid}"


def _active_chat_key(user_id: object, chat_id: object) -> str:
    uid = str(user_id or "").strip()
    cid = str(chat_id or "").strip()
    if not uid or not cid:
        raise PreviewActionError("chat_key_invalid")
    return f"{uid}:{cid}"


def prune_store(
    store: dict[str, object],
    *,
    now: object | None = None,
) -> dict[str, object]:
    if not isinstance(store, dict):
        raise PreviewActionError("session_store_invalid")
    sessions = store.get("sessions")
    active = store.get("active_by_chat")
    if not isinstance(sessions, dict) or not isinstance(active, dict):
        raise PreviewActionError("session_store_invalid")

    current = _timestamp(now)
    valid_keys: list[str] = []
    ranked_keys: list[tuple[int, int, int, str]] = []
    for position, (key, raw) in enumerate(sessions.items()):
        if not isinstance(key, str) or not session_is_fresh(raw, now=current):
            continue
        try:
            state = normalize_session(raw, now=current)
        except PreviewActionError:
            continue
        parts = key.rsplit(":", 2)
        if len(parts) != 3 or not parts[0] or not parts[1]:
            continue
        try:
            expected_key = session_store_key(parts[0], parts[1], state["session_id"])
        except PreviewActionError:
            continue
        if key != expected_key:
            continue
        valid_keys.append(key)
        ranked_keys.append((
            int(state["updated_at"]),
            int(state["created_at"]),
            position,
            key,
        ))

    ranked_keys.sort(reverse=True)
    retained = {item[-1] for item in ranked_keys[:MAX_STORED_SESSIONS]}
    pruned_sessions = {
        key: value
        for key, value in sessions.items()
        if key in retained and key in valid_keys
    }
    pruned_active = {
        chat_key: session_id
        for chat_key, session_id in active.items()
        if isinstance(chat_key, str)
        and isinstance(session_id, str)
        and f"{chat_key}:{session_id}" in pruned_sessions
    }
    store["sessions"] = pruned_sessions
    store["active_by_chat"] = pruned_active
    return store


def put_session(
    store: dict[str, object],
    user_id: object,
    chat_id: object,
    session: dict[str, object],
) -> dict[str, object]:
    if not isinstance(store, dict):
        raise PreviewActionError("session_store_invalid")
    state = normalize_session(session)
    sessions = store.setdefault("sessions", {})
    active = store.setdefault("active_by_chat", {})
    if not isinstance(sessions, dict) or not isinstance(active, dict):
        raise PreviewActionError("session_store_invalid")
    key = session_store_key(user_id, chat_id, state["session_id"])
    sessions[key] = copy.deepcopy(state)
    active[_active_chat_key(user_id, chat_id)] = state["session_id"]
    prune_store(store, now=state["updated_at"])
    return copy.deepcopy(state)


save_session = put_session


def get_session(
    store: dict[str, object],
    user_id: object,
    chat_id: object,
    session_id: object,
    *,
    now: object | None = None,
) -> dict[str, object] | None:
    if not isinstance(store, dict) or not isinstance(store.get("sessions"), dict):
        return None
    try:
        key = session_store_key(user_id, chat_id, session_id)
    except PreviewActionError:
        return None
    raw = store["sessions"].get(key)
    if not isinstance(raw, dict):
        return None
    if now is not None and not session_is_fresh(raw, now=now):
        store["sessions"].pop(key, None)
        active = store.get("active_by_chat")
        chat_key = _active_chat_key(user_id, chat_id)
        if isinstance(active, dict) and active.get(chat_key) == str(session_id):
            active.pop(chat_key, None)
        return None
    try:
        return normalize_session(raw, now=now)
    except PreviewActionError:
        delete_session(store, user_id, chat_id, session_id)
        return None


def delete_session(
    store: dict[str, object],
    user_id: object,
    chat_id: object,
    session_id: object,
) -> bool:
    if not isinstance(store, dict) or not isinstance(store.get("sessions"), dict):
        return False
    try:
        key = session_store_key(user_id, chat_id, session_id)
    except PreviewActionError:
        return False
    removed = store["sessions"].pop(key, None) is not None
    active = store.get("active_by_chat")
    if isinstance(active, dict) and active.get(_active_chat_key(user_id, chat_id)) == str(session_id):
        active.pop(_active_chat_key(user_id, chat_id), None)
    return removed


def store_has_callback_id(
    store: object,
    callback_id: object,
    *,
    now: object | None = None,
) -> bool:
    value = str(callback_id or "").strip()
    if not isinstance(store, dict) or not isinstance(store.get("sessions"), dict):
        return False
    prune_store(store, now=now)
    if not value:
        return False
    return any(
        isinstance(session, dict)
        and value in (session.get("processed_callback_ids") or ())
        for session in store["sessions"].values()
    )


def session_is_fresh(session: object, *, now: object | None = None) -> bool:
    if not isinstance(session, dict):
        return False
    try:
        created = _timestamp(session.get("created_at"))
        updated = _timestamp(session.get("updated_at"))
        current = _timestamp(now)
    except PreviewActionError:
        return False
    if updated < created:
        return False
    return current - updated <= SESSION_TTL_SECONDS


def _validate_state_shape(state: dict[str, object]) -> None:
    if frozenset(state) != _SESSION_FIELDS:
        raise PreviewActionError("session_fields_invalid")
    if state.get("version") != PREVIEW_VERSION or not _valid_session_id(state.get("session_id")):
        raise PreviewActionError("session_version_or_id_invalid")
    screen = state.get("screen")
    if screen not in _SCREEN_HISTORY:
        raise PreviewActionError("session_screen_invalid")
    history = state.get("history")
    if not isinstance(history, list) or tuple(history) != _SCREEN_HISTORY[screen]:
        raise PreviewActionError("session_history_invalid")
    if not isinstance(state.get("goal"), str) or state["goal"] not in ({"", *_GOAL_IDS}):
        raise PreviewActionError("session_goal_invalid")
    if not isinstance(state.get("record_id"), str) or state["record_id"] not in ({"", *LOCAL_RECORD_IDS}):
        raise PreviewActionError("session_record_invalid")
    selected = state.get("selected_ids")
    if not isinstance(selected, list) or len(selected) > MAX_SELECTED_CAPABILITIES:
        raise PreviewActionError("session_selection_invalid")
    if any(not isinstance(item, str) or not item.strip() for item in selected):
        raise PreviewActionError("session_selection_invalid")
    if len(set(selected)) != len(selected):
        raise PreviewActionError("session_selection_duplicate")
    for field in ("catalog_page", "detail_page"):
        value = state.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise PreviewActionError("session_page_invalid")
    processed = state.get("processed_callback_ids")
    if not isinstance(processed, list) or len(processed) > 64:
        raise PreviewActionError("session_callback_history_invalid")
    if any(not isinstance(item, str) or not item.strip() for item in processed):
        raise PreviewActionError("session_callback_history_invalid")
    if len(set(processed)) != len(processed):
        raise PreviewActionError("session_callback_history_duplicate")
    created_at = _timestamp(state.get("created_at"))
    updated_at = _timestamp(state.get("updated_at"))
    if updated_at < created_at:
        raise PreviewActionError("session_timestamp_order_invalid")
    if state["screen"] == "goal":
        if state["history"] or state["goal"] or state["record_id"] or state["selected_ids"]:
            raise PreviewActionError("session_goal_state_invalid")
    elif state["screen"] == "catalog":
        if not state["goal"] or state["record_id"] or state["selected_ids"]:
            raise PreviewActionError("session_catalog_state_invalid")
    elif state["screen"] == "detail":
        if not state["goal"] or not state["record_id"]:
            raise PreviewActionError("session_detail_state_invalid")
    elif state["screen"] == "safety":
        if not state["goal"] or not state["record_id"] or not state["selected_ids"]:
            raise PreviewActionError("session_safety_state_invalid")
    elif state["screen"] == "summary":
        if not state["goal"] or not state["record_id"] or not state["selected_ids"]:
            raise PreviewActionError("session_summary_state_invalid")


def normalize_session(session: object, *, now: object | None = None) -> dict[str, object]:
    if not isinstance(session, dict):
        raise PreviewActionError("session_invalid")
    state = copy.deepcopy(session)
    _validate_state_shape(state)
    if now is not None and not session_is_fresh(state, now=now):
        raise PublicSessionExpired("session_stale")
    payload = load_capability_index()
    capability_to_record = _all_capability_to_record(payload)
    selected = state["selected_ids"]
    for capability_id in selected:
        if capability_id not in capability_to_record:
            raise PreviewActionError("session_selection_unknown")
        if state["record_id"] and capability_to_record[capability_id] != state["record_id"]:
            raise PreviewActionError("session_selection_wrong_record")
    if state["screen"] in {"safety", "summary"} and not selected:
        raise PreviewActionError("session_selection_required")
    _, state["catalog_page"], _ = paginate(
        LOCAL_RECORD_IDS,
        int(state["catalog_page"]),
        CATALOG_PAGE_SIZE,
    )
    if state["record_id"]:
        record = _record_map(payload)[str(state["record_id"])]
        _, state["detail_page"], _ = paginate(
            tuple(record["capability_ids"]),
            int(state["detail_page"]),
            DETAIL_PAGE_SIZE,
        )
    state["created_at"] = _timestamp(state["created_at"])
    state["updated_at"] = _timestamp(state["updated_at"])
    return state


def callback_data(*parts: object) -> str:
    values = [str(part) for part in parts]
    if values and values[0] == "":
        values = values[1:]
    if not values or any(not value or "|" in value for value in values):
        raise PreviewActionError("callback_part_invalid")
    value = "|".join((CALLBACK_PREFIX, *values))
    if len(value.encode("utf-8")) > 64:
        raise PreviewActionError("callback_too_long")
    return value


def _parse_page(value: str) -> int:
    if isinstance(value, str) and value.startswith("-") and value[1:].isdigit():
        return 0
    if not isinstance(value, str) or not value.isdigit():
        raise PreviewActionError("page_invalid")
    return int(value)


def _parse_index(value: str) -> int:
    if not isinstance(value, str) or not value.isdigit():
        raise PreviewActionError("index_invalid")
    return int(value)


def parse_callback(value: object) -> tuple[str, str, tuple[str, ...]]:
    if not isinstance(value, str) or len(value.encode("utf-8")) > 64:
        raise PreviewActionError("callback_invalid")
    parts = value.split("|")
    if len(parts) == 2 and parts == [CALLBACK_PREFIX, "open"]:
        return "", "open", ()
    if len(parts) < 3 or parts[0] != CALLBACK_PREFIX or not _valid_session_id(parts[1]):
        raise PreviewActionError("callback_namespace_or_session_invalid")
    sid = parts[1]
    verb = parts[2]
    args = tuple(parts[3:])
    if verb not in _ALLOWED_VERBS - {"open"}:
        raise PreviewActionError("callback_verb_invalid")
    if verb in {"back", "close", "safety", "summary", "save"}:
        if args:
            raise PreviewActionError("callback_shape_invalid")
    elif verb == "goal":
        if len(args) != 1 or args[0] not in _GOAL_IDS:
            raise PreviewActionError("goal_invalid")
    elif verb == "catalog":
        if len(args) != 1:
            raise PreviewActionError("catalog_shape_invalid")
        _parse_page(args[0])
    elif verb == "detail":
        if len(args) != 2 or args[0] not in LOCAL_RECORD_IDS:
            raise PreviewActionError("detail_target_invalid")
        _parse_page(args[1])
    elif verb == "select":
        if len(args) != 2 or args[0] not in LOCAL_RECORD_IDS:
            raise PreviewActionError("select_target_invalid")
        _parse_index(args[1])
    return sid, verb, args


def _touch(state: dict[str, object], now: object | None = None) -> None:
    state["updated_at"] = _timestamp(now)


def _navigate(state: dict[str, object], screen: str) -> None:
    current = str(state["screen"])
    if current != screen:
        state["history"] = [*state["history"], current]
    state["screen"] = screen


def _records_for(payload: dict[str, object], record_id: str) -> dict[str, object]:
    records = _record_map(payload)
    record = records.get(record_id)
    if not record or record_id not in LOCAL_RECORD_IDS:
        raise PreviewActionError("record_not_available")
    return record


def _summary_payload(state: dict[str, object], payload: dict[str, object]) -> str:
    return planning_summary_text(state, payload)


def apply_callback(
    session: object,
    callback_value: str,
    *,
    payload: dict[str, object] | None = None,
    now: object | None = None,
    callback_id: str | None = None,
) -> dict[str, object]:
    sid, verb, args = parse_callback(callback_value)
    if verb == "open":
        opened = new_session(now=now)
        return {
            "session": opened,
            "closed": False,
            "exit_parent": False,
            "duplicate": False,
            "saved_text": "",
            "feedback": "Đã mở công cụ lập kế hoạch dựng video.",
        }
    state = normalize_session(session, now=now)
    if sid != state["session_id"]:
        raise PublicSessionExpired("session_id_mismatch")
    callback_id_text = str(callback_id or "").strip()
    if callback_id_text and callback_id_text in state["processed_callback_ids"]:
        return {
            "session": state,
            "closed": False,
            "exit_parent": False,
            "duplicate": True,
            "saved_text": "",
            "feedback": "Thao tác này đã được nhận.",
        }
    data = validate_capability_index(payload) if payload is not None else load_capability_index()
    result = {
        "session": state,
        "closed": False,
        "exit_parent": False,
        "duplicate": False,
        "saved_text": "",
        "feedback": "Đã cập nhật kế hoạch.",
    }
    if verb == "close":
        result["closed"] = True
        result["feedback"] = "Đã đóng bản lập kế hoạch."
        return result
    if verb == "back":
        history = list(state["history"])
        if not history:
            if state["screen"] == "goal":
                result["exit_parent"] = True
                result["feedback"] = "Đã quay lại Chỉnh sửa video."
                return result
            raise PreviewActionError("back_history_empty")
        target = history.pop()
        state["history"] = history
        state["screen"] = target
        if target == "goal":
            state["goal"] = ""
            state["record_id"] = ""
            state["selected_ids"] = []
            state["catalog_page"] = 0
            state["detail_page"] = 0
        elif target == "catalog":
            state["record_id"] = ""
            state["selected_ids"] = []
            state["detail_page"] = 0
        _touch(state, now)
        result["session"] = state
        result["feedback"] = "Đã quay lại đúng màn hình trước."
        return result
    if verb == "goal":
        if state["screen"] != "goal":
            raise PreviewActionError("goal_step_invalid")
        state["goal"] = args[0]
        _navigate(state, "catalog")
        _touch(state, now)
        result["session"] = state
        result["feedback"] = "Đã chọn mục tiêu; tiếp tục chọn capability."
        return result
    if verb == "catalog":
        if state["screen"] != "catalog":
            raise PreviewActionError("catalog_step_invalid")
        _, state["catalog_page"], _ = paginate(LOCAL_RECORD_IDS, _parse_page(args[0]), CATALOG_PAGE_SIZE)
        _touch(state, now)
        result["session"] = state
        result["feedback"] = "Đã chuyển trang capability."
        return result
    if verb == "detail":
        record_id, page_text = args
        if state["screen"] == "catalog":
            state = _navigate(state, "detail") or state
            state["record_id"] = record_id
            state["selected_ids"] = []
        elif state["screen"] == "detail" and state["record_id"] == record_id:
            pass
        else:
            raise PreviewActionError("detail_step_invalid")
        record = _records_for(data, record_id)
        _, state["detail_page"], _ = paginate(tuple(record["capability_ids"]), _parse_page(page_text), DETAIL_PAGE_SIZE)
        _touch(state, now)
        result["session"] = state
        result["feedback"] = "Đã mở chi tiết capability."
        return result
    if verb == "select":
        if state["screen"] != "detail":
            raise PreviewActionError("select_step_invalid")
        record_id, index_text = args
        if state["record_id"] != record_id:
            raise PreviewActionError("select_record_invalid")
        record = _records_for(data, record_id)
        index = _parse_index(index_text)
        capability_ids = tuple(record["capability_ids"])
        if index >= len(capability_ids):
            raise PreviewActionError("select_index_invalid")
        capability_id = str(capability_ids[index])
        if capability_id not in state["selected_ids"]:
            if len(state["selected_ids"]) >= MAX_SELECTED_CAPABILITIES:
                raise PreviewActionError("selection_limit_reached")
            state["selected_ids"] = [*state["selected_ids"], capability_id]
            _touch(state, now)
            result["feedback"] = "Đã thêm capability vào kế hoạch."
        else:
            result["feedback"] = "Capability đã có trong kế hoạch."
        result["session"] = state
        return result
    if verb == "safety":
        if state["screen"] != "detail" or not state["selected_ids"]:
            raise PreviewActionError("safety_requires_selection")
        _navigate(state, "safety")
        _touch(state, now)
        result["session"] = state
        result["feedback"] = "Đã mở quyền và an toàn."
        return result
    if verb == "summary":
        if state["screen"] != "safety":
            raise PreviewActionError("summary_step_invalid")
        _navigate(state, "summary")
        _touch(state, now)
        result["session"] = state
        result["feedback"] = "Đã tạo planning summary dạng text."
        return result
    if verb == "save":
        if state["screen"] != "summary":
            raise PreviewActionError("save_step_invalid")
        result["saved_text"] = _summary_payload(state, data)
        result["session"] = state
        result["feedback"] = "Đã gửi bản tóm tắt dạng text vào chat."
        return result
    raise PreviewActionError("callback_not_implemented")


def commit_callback_id(
    session: object,
    callback_id: object,
    *,
    now: object | None = None,
) -> dict[str, object]:
    state = normalize_session(session)
    value = str(callback_id or "").strip()
    if not value:
        return state
    if value not in state["processed_callback_ids"]:
        state["processed_callback_ids"] = [*state["processed_callback_ids"], value][-64:]
        _touch(state, now)
    return state


def _label_for_goal(goal: str) -> str:
    return next((label for option_id, label in GOAL_OPTIONS if option_id == goal), goal)


def _public_asset_lines(records: dict[str, dict[str, object]], record_ids: set[str]) -> list[str]:
    lines: list[str] = []
    if any(str(records[r].get("requires_planned_shoot") or "").upper() == "REQUIRED" for r in record_ids):
        lines.append("• Cảnh quay theo kế hoạch và ghi chú bảo đảm tính liên tục")
    if any(str(records[r].get("requires_explicit_confirmation") or "").lower() == "true" for r in record_ids):
        lines.append("• Xác nhận quyền sử dụng trước khi áp dụng")
    if "rights_requirements" in records:
        lines.append("• Bằng chứng quyền sử dụng cho nguồn và tài nguyên")
    if not lines:
        lines.append("• Cảnh quay hoặc tài nguyên do người dùng có quyền sử dụng")
    return lines


def planning_summary_text(state: dict[str, object], payload: dict[str, object] | None = None) -> str:
    data = validate_capability_index(payload) if payload is not None else load_capability_index()
    normalized = normalize_session(state)
    records = _record_map(data)
    selected_ids = [str(item) for item in normalized["selected_ids"]]
    selected_record_ids = {str(records_by_id) for records_by_id in (
        next((record_id for record_id, record in records.items() if capability_id in record["capability_ids"]), "")
        for capability_id in selected_ids
    ) if records_by_id}
    readiness = sorted({public_readiness(records[record_id]) for record_id in selected_record_ids})
    rights_record = records.get("rights_requirements", {})
    rights_ids = tuple(str(item) for item in rights_record.get("capability_ids") or ())
    sequence = "Mục tiêu → hạng mục đã chọn → rà quyền và an toàn → bước thủ công tiếp theo"
    blockers: list[str] = []
    if any(value == "REQUIRES_PLANNED_SHOOT" for value in readiness):
        blockers.append("Cần cảnh quay theo kế hoạch trước khi áp dụng.")
    if any(value == "REQUIRES_RUNTIME" for value in readiness):
        blockers.append("Hạng mục này cần một bước xử lý riêng được phê duyệt trước.")
    if not blockers:
        blockers.append("Chưa có trở ngại kỹ thuật trong bản lập kế hoạch.")
    asset_lines = _public_asset_lines(records, selected_record_ids)
    selected_text = "\n".join(f"• {html.escape(value)}" for value in selected_ids)
    rights_text = "\n".join(f"• {html.escape(value)}" for value in rights_ids)
    return (
        "🧾 <b>BẢN TÓM TẮT KẾ HOẠCH DỰNG VIDEO</b>\n\n"
        "Đây là công cụ lập kế hoạch dựng video.\n"
        "Công cụ chưa tạo hoặc render video.\n\n"
        f"• Mục tiêu: <b>{html.escape(_label_for_goal(str(normalized['goal'])))}</b>\n"
        "• Mã hạng mục đã chọn:\n"
        f"{selected_text}\n\n"
        f"• Mức sẵn sàng: <code>{html.escape(', '.join(readiness))}</code>\n"
        "• Tài nguyên cần chuẩn bị:\n"
        f"{chr(10).join(asset_lines)}\n\n"
        "• Quyền tham chiếu:\n"
        f"{rights_text}\n\n"
        f"• Trình tự: {sequence}\n"
        "• Trở ngại và an toàn:\n"
        + "\n".join(f"• {html.escape(item)}" for item in blockers)
        + "\n• Bước tiếp theo: rà quyền và chuẩn bị cảnh quay hoặc tài nguyên phù hợp.\n\n"
        "• Chỉ lưu/gửi nội dung kế hoạch dạng chữ; không tạo tệp video hoặc âm thanh."
    )


def _nav_rows(state: dict[str, object], *, include_close: bool = False) -> list[tuple[tuple[str, str], ...]]:
    sid = str(state["session_id"])
    rows: list[tuple[tuple[str, str], ...]] = []
    if state["screen"] == "goal":
        rows.append((("⬅️ Chỉnh sửa video", callback_data(sid, "back")),))
    else:
        rows.append((("⬅️ Quay lại", callback_data(sid, "back")),))
    if include_close:
        rows.append((("✖️ Đóng", callback_data(sid, "close")),))
    return rows


def _page_buttons(
    sid: str,
    current: int,
    total: int,
    previous: str,
    following: str,
) -> tuple[tuple[str, str], ...]:
    buttons: list[tuple[str, str]] = []
    if current > 0:
        buttons.append(("⬅️ Trang trước", previous))
    if current + 1 < total:
        buttons.append(("Trang sau ➡️", following))
    return tuple(buttons)


def _public_capability_label(capability_id: object, position: int) -> str:
    suffix = str(capability_id or "").rsplit(".", 1)[-1].strip().lower()
    words = suffix.replace("_", " ").replace("-", " ")
    blocked_tokens = {"command", "debug", "endpoint", "job", "path", "provider", "secret", "sha", "task", "token", "version"}
    if not words or any(token in blocked_tokens for token in words.split()):
        return f"Hạng mục {position}"
    return f"{position} · {words}"


def _render_goal(state: dict[str, object]) -> dict[str, object]:
    rows: list[tuple[tuple[str, str], ...]] = []
    for start in range(0, len(GOAL_OPTIONS), 2):
        rows.append(tuple(
            (label, callback_data(str(state["session_id"]), "goal", option_id))
            for option_id, label in GOAL_OPTIONS[start : start + 2]
        ))
    rows.extend(_nav_rows(state))
    return {
        "screen": "goal",
        "text": (
            "🎬 <b>LẬP KẾ HOẠCH DỰNG VIDEO</b>\n\n"
            "Đây là công cụ lập kế hoạch dựng video.\n"
            "Công cụ chưa tạo hoặc render video.\n\n"
            "Chọn mục tiêu trước để mở danh mục công cụ cục bộ. "
            "Mọi lựa chọn chỉ tạo nội dung kế hoạch dạng chữ."
        ),
        "rows": tuple(rows),
    }


def _render_catalog(state: dict[str, object], payload: dict[str, object]) -> dict[str, object]:
    _record_map(payload)
    labels = _public_record_labels_vi()
    visible, page, total = paginate(LOCAL_RECORD_IDS, int(state["catalog_page"]), CATALOG_PAGE_SIZE)
    rows = [
        tuple((labels[record_id], callback_data(str(state["session_id"]), "detail", record_id, "0")) for record_id in visible[index : index + 2])
        for index in range(0, len(visible), 2)
    ]
    page_row = _page_buttons(
        str(state["session_id"]),
        page,
        total,
        callback_data(str(state["session_id"]), "catalog", str(max(0, page - 1))),
        callback_data(str(state["session_id"]), "catalog", str(min(total - 1, page + 1))),
    )
    if page_row:
        rows.append(page_row)
    rows.extend(_nav_rows(state))
    return {
        "screen": "catalog",
        "text": (
            "🧰 <b>DANH MỤC LẬP KẾ HOẠCH CỤC BỘ</b>\n\n"
            f"11 nhóm công cụ · Trang {page + 1}/{total}.\n"
            "Chọn một nhóm để xem các hạng mục và mức sẵn sàng."
        ),
        "rows": tuple(rows),
    }


def _render_detail(state: dict[str, object], payload: dict[str, object]) -> dict[str, object]:
    records = _record_map(payload)
    labels = _public_record_labels_vi()
    record = records[str(state["record_id"])]
    ids = tuple(str(item) for item in record["capability_ids"])
    visible, page, total = paginate(ids, int(state["detail_page"]), DETAIL_PAGE_SIZE)
    start_index = page * DETAIL_PAGE_SIZE
    rows = [
        ((
            f"➕ {html.escape(_public_capability_label(capability_id, start_index + index + 1))}",
            callback_data(str(state["session_id"]), "select", str(state["record_id"]), str(start_index + index)),
        ),)
        for index, capability_id in enumerate(visible)
    ]
    page_row = _page_buttons(
        str(state["session_id"]),
        page,
        total,
        callback_data(str(state["session_id"]), "detail", str(state["record_id"]), str(max(0, page - 1))),
        callback_data(str(state["session_id"]), "detail", str(state["record_id"]), str(min(total - 1, page + 1))),
    )
    if page_row:
        rows.append(page_row)
    if state["selected_ids"]:
        rows.append((("🛡 Quyền và an toàn", callback_data(str(state["session_id"]), "safety")),))
    rows.extend(_nav_rows(state))
    selected_text = f"{len(state['selected_ids'])} hạng mục" if state["selected_ids"] else "Chưa chọn"
    return {
        "screen": "detail",
        "text": (
            f"🧰 <b>{html.escape(labels[str(state['record_id'])])}</b>\n\n"
            f"• Mức sẵn sàng: <code>{html.escape(public_readiness(record))}</code>\n"
            f"• Hạng mục: {len(ids)} · Trang {page + 1}/{total}\n"
            f"• Đã chọn: {selected_text}\n\n"
            "Chọn một hoặc nhiều hạng mục để đưa vào bản tóm tắt; chưa có xử lý tệp."
        ),
        "rows": tuple(rows),
    }


def _render_safety(state: dict[str, object], payload: dict[str, object]) -> dict[str, object]:
    records = _record_map(payload)
    labels = _public_record_labels_vi()
    rights = records["rights_requirements"]
    selected_record_ids = {
        record_id
        for record_id, record in records.items()
        if any(item in record["capability_ids"] for item in state["selected_ids"])
    }
    selected_labels = ", ".join(labels[item] for item in sorted(selected_record_ids))
    return {
        "screen": "safety",
        "text": (
            "🛡 <b>QUYỀN VÀ AN TOÀN</b>\n\n"
            "Đây là công cụ lập kế hoạch dựng video.\n"
            "Công cụ chưa tạo hoặc render video.\n\n"
            f"• Hạng mục đã chọn: {len(state['selected_ids'])}\n"
            f"• Nhóm liên quan: {html.escape(selected_labels)}\n"
            f"• Mức sẵn sàng: <code>{html.escape(', '.join(sorted(public_readiness(records[item]) for item in selected_record_ids)))}</code>\n"
            f"• Tiêu chí quyền tham chiếu: {len(rights.get('capability_ids') or ())}\n"
            "• Cần xác nhận quyền sở hữu hoặc giấy phép phù hợp trước khi áp dụng.\n"
            "• Không có bước thực thi hoặc tạo tệp."
        ),
        "rows": (
            (("📋 Bản tóm tắt kế hoạch", callback_data(str(state["session_id"]), "summary")),),
            *_nav_rows(state),
        ),
    }


def _render_summary(state: dict[str, object], payload: dict[str, object]) -> dict[str, object]:
    return {
        "screen": "summary",
        "text": planning_summary_text(state, payload),
        "rows": (
            (("📝 Gửi bản tóm tắt vào chat", callback_data(str(state["session_id"]), "save")),),
            *_nav_rows(state, include_close=True),
        ),
    }


def render_view(
    session: object,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    state = normalize_session(session)
    data = validate_capability_index(payload) if payload is not None else load_capability_index()
    screen = str(state["screen"])
    if screen == "goal":
        return _render_goal(state)
    if screen == "catalog":
        return _render_catalog(state, data)
    if screen == "detail":
        return _render_detail(state, data)
    if screen == "safety":
        return _render_safety(state, data)
    if screen == "summary":
        return _render_summary(state, data)
    raise PreviewDataError("public_screen_unrenderable")


async def _invoke_callback(callback: Callable[[], object]) -> bool:
    result = callback()
    if inspect.isawaitable(result):
        result = await result
    return result is not False


async def deliver_then_commit(
    edit: Callable[[], Awaitable[object]],
    reply: Callable[[], Awaitable[object]],
    commit: Callable[[], object],
    answer: Callable[[], Awaitable[object]],
) -> bool:
    delivered = False
    try:
        delivered = await _invoke_callback(edit)
    except Exception:
        delivered = False
    if not delivered:
        try:
            delivered = await _invoke_callback(reply)
        except Exception:
            delivered = False
    if not delivered:
        return False
    try:
        commit_result = commit()
        if inspect.isawaitable(commit_result):
            await commit_result
    except Exception:
        return False
    try:
        answer_result = answer()
        if inspect.isawaitable(answer_result):
            await answer_result
    except Exception:
        pass
    return True
