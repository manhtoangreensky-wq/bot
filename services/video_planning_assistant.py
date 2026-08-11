from __future__ import annotations

import asyncio
import copy
import hashlib
import html
import inspect
import re
import time
import uuid
import weakref
from typing import Awaitable, Callable


CALLBACK_PREFIX = "lvs27b"
STATE_KEY = "local_video_studio27b_public"
PREVIEW_VERSION = "27B"
PLAN_SCHEMA_VERSION = 1
SESSION_TTL_SECONDS = 30 * 60
MAX_STORED_SESSIONS = 32
MAX_BRIEF_LENGTH = 600

GOAL_OPTIONS = (
    ("cut_pacing", "✂️ Cắt dựng và nhịp"),
    ("reframe", "🎯 Điều chỉnh khung hình và bố cục"),
    ("transition_motion", "✨ Chuyển cảnh và chuyển động"),
    ("sound_post", "🎧 Âm thanh và hậu kỳ"),
)
PLATFORM_OPTIONS = (
    ("tiktok_9x16", "TikTok · 9:16"),
    ("reels_9x16", "Facebook/Instagram Reels · 9:16"),
    ("shorts_9x16", "YouTube Shorts · 9:16"),
    ("youtube_16x9", "YouTube · 16:9"),
    ("square_1x1", "Bài đăng vuông · 1:1"),
)
SOURCE_DURATION_OPTIONS = (
    ("under30", "Dưới 30 giây"),
    ("30_60", "Khoảng 30–60 giây"),
    ("60_120", "Khoảng 1–2 phút"),
    ("over120", "Trên 2 phút"),
)
TARGET_DURATION_OPTIONS = (
    ("15", "Khoảng 15 giây"),
    ("30", "Khoảng 30 giây"),
    ("60", "Khoảng 60 giây"),
    ("keep", "Giữ gần thời lượng hiện tại"),
)
ASSET_OPTIONS = (
    ("video", "🎞 Video nguồn"),
    ("logo", "🏷 Logo"),
    ("watermark", "✍️ Watermark"),
    ("subtitles", "💬 Phụ đề"),
    ("music", "🎵 Nhạc"),
    ("none", "Chưa có tài nguyên bổ sung"),
)
PRIORITY_OPTIONS = (
    ("pace", "⚡ Nhanh và gọn hơn"),
    ("product_focus", "📦 Nổi bật sản phẩm/chủ thể"),
    ("brightness", "☀️ Hình ảnh sáng và rõ hơn"),
    ("speech_clarity", "🔊 Lời nói dễ nghe hơn"),
    ("branding", "🏷 Nhận diện thương hiệu"),
    ("vertical", "📱 Tối ưu khung dọc"),
)
OPERATION_OPTIONS = (
    ("cut", "Cắt các đoạn thừa"),
    ("best_segment", "Chọn đoạn sản phẩm/chủ thể tốt nhất"),
    ("pace", "Tăng nhịp dựng"),
    ("reframe", "Chỉnh khung hình theo nền tảng"),
    ("brightness", "Chỉnh sáng nhẹ"),
    ("audio", "Cân âm lượng lời nói"),
    ("logo", "Thêm logo"),
    ("watermark", "Thêm watermark"),
    ("subtitles", "Bổ sung phụ đề"),
    ("music", "Bổ sung hoặc cân nhạc nền"),
    ("transitions", "Bổ sung chuyển cảnh tiết chế"),
    ("qa", "Kiểm tra thành phẩm"),
)

PUBLIC_OPERATION_STEPS = {
    "cut": "Cắt các đoạn thừa và giữ nội dung phục vụ mục tiêu chính.",
    "best_segment": "Chọn và giữ đoạn sản phẩm hoặc chủ thể rõ nhất; chưa có mốc thời gian nên cần chọn khi thực thi.",
    "pace": "Sắp xếp lại nhịp dựng theo thời lượng thành phẩm đã chọn.",
    "reframe": "Chỉnh khung hình và vùng an toàn theo nền tảng đích.",
    "brightness": "Tăng sáng nhẹ, giữ màu sắc và chi tiết tự nhiên.",
    "audio": "Cân âm lượng để phần lời nói rõ và dễ nghe.",
    "logo": "Đặt logo ở vị trí không che khuôn mặt hoặc sản phẩm.",
    "watermark": "Đặt watermark ở vùng dễ đọc nhưng không che nội dung chính.",
    "subtitles": "Bổ sung phụ đề ngắn, rõ và nằm trong vùng an toàn.",
    "music": "Bổ sung hoặc cân nhạc nền để không lấn át lời nói.",
    "transitions": "Dùng chuyển cảnh tiết chế giữa các đoạn phù hợp.",
    "qa": "Kiểm tra hình, tiếng, tỷ lệ và thời lượng trước khi xuất.",
}

BASE_RIGHTS_NOTES = (
    "Chỉ sử dụng video, hình ảnh, âm thanh và nhận diện thương hiệu bạn có quyền sử dụng.",
)

_GOAL_IDS = frozenset(value for value, _label in GOAL_OPTIONS)
_PLATFORM_IDS = frozenset(value for value, _label in PLATFORM_OPTIONS)
_SOURCE_IDS = frozenset(value for value, _label in SOURCE_DURATION_OPTIONS)
_TARGET_IDS = frozenset(value for value, _label in TARGET_DURATION_OPTIONS)
_ASSET_IDS = frozenset(value for value, _label in ASSET_OPTIONS)
_PRIORITY_IDS = frozenset(value for value, _label in PRIORITY_OPTIONS)
_OPERATION_IDS = frozenset(value for value, _label in OPERATION_OPTIONS)
_OPERATION_ORDER = {
    value: index for index, (value, _label) in enumerate(OPERATION_OPTIONS)
}
_SCREENS = (
    "goal",
    "brief",
    "platform",
    "source_duration",
    "target_duration",
    "assets",
    "priorities",
    "operations",
    "safety",
    "summary",
)
_SESSION_FIELDS = frozenset(
    {
        "version",
        "plan_schema_version",
        "session_id",
        "plan_id",
        "created_at",
        "updated_at",
        "screen",
        "history",
        "goal",
        "editing_brief",
        "platform_ratio",
        "source_duration",
        "target_duration",
        "available_assets",
        "priorities",
        "selected_operations",
        "processed_callback_ids",
        "sent_summary_fingerprint",
    }
)
_ALLOWED_VERBS = frozenset(
    {
        "open",
        "goal",
        "brief_skip",
        "platform",
        "source",
        "target",
        "asset",
        "assets_done",
        "priority",
        "priorities_done",
        "op",
        "operations_done",
        "safety_done",
        "persist",
        "send",
        "plans",
        "library",
        "current",
        "view",
        "edit",
        "delete",
        "delete_confirm",
        "back",
        "close",
    }
)
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{4,12}$")
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
_TIME_RANGE_RE = re.compile(r"\b\d{1,2}:\d{2}\s*[–—-]\s*\d{1,2}:\d{2}\b")
_SESSION_TRANSACTION_LOCKS: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()


class PreviewDataError(ValueError):
    pass


class PreviewActionError(ValueError):
    pass


class PublicSessionExpired(PreviewActionError):
    pass


def _timestamp(value: object | None = None) -> int:
    raw = time.time() if value is None else value
    if isinstance(raw, bool):
        raise PreviewActionError("timestamp_invalid")
    try:
        stamp = int(float(raw))
    except (TypeError, ValueError, OverflowError) as exc:
        raise PreviewActionError("timestamp_invalid") from exc
    if stamp < 0:
        raise PreviewActionError("timestamp_invalid")
    return stamp


def _new_session_id() -> str:
    return uuid.uuid4().hex[:8]


def _valid_session_id(value: object) -> bool:
    return isinstance(value, str) and bool(_SESSION_ID_RE.fullmatch(value))


def _label(options: tuple[tuple[str, str], ...], value: object) -> str:
    key = str(value or "")
    return next((label for option_id, label in options if option_id == key), key)


def public_entry_rows(enabled: object) -> tuple[tuple[str, str], ...]:
    if isinstance(enabled, str):
        active = enabled.strip().lower() in {"1", "true", "yes", "on"}
    else:
        active = bool(enabled)
    return (("🧭 Lên kế hoạch chỉnh sửa", callback_data("open")),) if active else ()


def new_session(session_id: str | None = None, *, now: object | None = None) -> dict[str, object]:
    sid = str(session_id or _new_session_id()).strip()
    if not _valid_session_id(sid):
        raise PreviewActionError("session_id_invalid")
    stamp = _timestamp(now)
    return {
        "version": PREVIEW_VERSION,
        "plan_schema_version": PLAN_SCHEMA_VERSION,
        "session_id": sid,
        "plan_id": "",
        "created_at": stamp,
        "updated_at": stamp,
        "screen": "goal",
        "history": [],
        "goal": "",
        "editing_brief": "",
        "platform_ratio": "",
        "source_duration": "",
        "target_duration": "",
        "available_assets": [],
        "priorities": [],
        "selected_operations": [],
        "processed_callback_ids": [],
        "sent_summary_fingerprint": "",
    }


def _validate_unique_list(value: object, allowed: frozenset[str], field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise PreviewActionError(f"session_{field}_invalid")
    if len(value) != len(set(value)) or any(item not in allowed for item in value):
        raise PreviewActionError(f"session_{field}_invalid")
    return list(value)


def _validate_state_shape(state: dict[str, object]) -> None:
    if frozenset(state) != _SESSION_FIELDS:
        raise PreviewActionError("session_fields_invalid")
    if state["version"] != PREVIEW_VERSION or state["plan_schema_version"] != PLAN_SCHEMA_VERSION:
        raise PreviewActionError("session_version_invalid")
    if not _valid_session_id(state["session_id"]):
        raise PreviewActionError("session_id_invalid")
    if not isinstance(state["plan_id"], str) or len(state["plan_id"]) > 24:
        raise PreviewActionError("session_plan_id_invalid")
    if state["screen"] not in _SCREENS:
        raise PreviewActionError("session_screen_invalid")
    history = state["history"]
    if not isinstance(history, list) or any(screen not in _SCREENS for screen in history):
        raise PreviewActionError("session_history_invalid")
    if not isinstance(state["goal"], str) or (state["goal"] and state["goal"] not in _GOAL_IDS):
        raise PreviewActionError("session_goal_invalid")
    brief = state["editing_brief"]
    if not isinstance(brief, str) or len(brief) > MAX_BRIEF_LENGTH:
        raise PreviewActionError("session_brief_invalid")
    for field, allowed in (
        ("platform_ratio", _PLATFORM_IDS),
        ("source_duration", _SOURCE_IDS),
        ("target_duration", _TARGET_IDS),
    ):
        value = state[field]
        if not isinstance(value, str) or (value and value not in allowed):
            raise PreviewActionError(f"session_{field}_invalid")
    _validate_unique_list(state["available_assets"], _ASSET_IDS, "assets")
    _validate_unique_list(state["priorities"], _PRIORITY_IDS, "priorities")
    _validate_unique_list(state["selected_operations"], _OPERATION_IDS, "operations")
    callbacks = state["processed_callback_ids"]
    if not isinstance(callbacks, list) or not all(isinstance(item, str) and item for item in callbacks):
        raise PreviewActionError("session_callbacks_invalid")
    fingerprint = state["sent_summary_fingerprint"]
    if not isinstance(fingerprint, str) or (fingerprint and not _FINGERPRINT_RE.fullmatch(fingerprint)):
        raise PreviewActionError("session_fingerprint_invalid")
    created = _timestamp(state["created_at"])
    updated = _timestamp(state["updated_at"])
    if updated < created:
        raise PreviewActionError("session_timestamp_order_invalid")


def normalize_session(session: object, *, now: object | None = None) -> dict[str, object]:
    if not isinstance(session, dict):
        raise PreviewActionError("session_invalid")
    state = copy.deepcopy(session)
    _validate_state_shape(state)
    if now is not None and not session_is_fresh(state, now=now):
        raise PublicSessionExpired("session_stale")
    state["created_at"] = _timestamp(state["created_at"])
    state["updated_at"] = _timestamp(state["updated_at"])
    return state


def session_is_fresh(session: object, *, now: object | None = None) -> bool:
    if not isinstance(session, dict):
        return False
    try:
        created = _timestamp(session.get("created_at"))
        updated = _timestamp(session.get("updated_at"))
        current = _timestamp(now)
    except PreviewActionError:
        return False
    return updated >= created and current - updated <= SESSION_TTL_SECONDS


def callback_data(*parts: object) -> str:
    values = [str(part) for part in parts]
    if not values or any(not value or "|" in value for value in values):
        raise PreviewActionError("callback_part_invalid")
    value = "|".join((CALLBACK_PREFIX, *values))
    if len(value.encode("utf-8")) > 64:
        raise PreviewActionError("callback_too_long")
    return value


def parse_callback(value: object) -> tuple[str, str, tuple[str, ...]]:
    if not isinstance(value, str) or len(value.encode("utf-8")) > 64:
        raise PreviewActionError("callback_invalid")
    parts = value.split("|")
    if parts == [CALLBACK_PREFIX, "open"]:
        return "", "open", ()
    if len(parts) < 3 or parts[0] != CALLBACK_PREFIX or not _valid_session_id(parts[1]):
        raise PreviewActionError("callback_namespace_or_session_invalid")
    sid, verb, args = parts[1], parts[2], tuple(parts[3:])
    if verb not in _ALLOWED_VERBS - {"open"}:
        raise PreviewActionError("callback_verb_invalid")
    no_args = {
        "brief_skip",
        "assets_done",
        "priorities_done",
        "operations_done",
        "safety_done",
        "persist",
        "send",
        "plans",
        "library",
        "current",
        "back",
        "close",
    }
    one_arg_allowed = {
        "goal": _GOAL_IDS,
        "platform": _PLATFORM_IDS,
        "source": _SOURCE_IDS,
        "target": _TARGET_IDS,
        "asset": _ASSET_IDS,
        "priority": _PRIORITY_IDS,
        "op": _OPERATION_IDS,
    }
    if verb in no_args and args:
        raise PreviewActionError("callback_shape_invalid")
    if verb in one_arg_allowed and (len(args) != 1 or args[0] not in one_arg_allowed[verb]):
        raise PreviewActionError("callback_value_invalid")
    if verb in {"view", "edit", "delete", "delete_confirm"} and (
        len(args) != 1 or not re.fullmatch(r"[a-f0-9]{12}", args[0])
    ):
        raise PreviewActionError("callback_plan_key_invalid")
    return sid, verb, args


def _touch(state: dict[str, object], now: object | None = None) -> None:
    state["updated_at"] = _timestamp(now)


def _navigate(state: dict[str, object], target: str) -> None:
    current = str(state["screen"])
    if current != target:
        state["history"] = [*state["history"], current]
        state["screen"] = target


def _toggle(values: list[str], value: str) -> list[str]:
    return [item for item in values if item != value] if value in values else [*values, value]


def _ordered_operation_ids(values: list[str]) -> list[str]:
    return sorted(values, key=_OPERATION_ORDER.__getitem__)


def suggest_operations(session: object) -> list[str]:
    state = normalize_session(session)
    ordered: list[str] = []
    available_assets = set(state["available_assets"])
    available_assets.discard("none")

    def add(*values: str) -> None:
        for value in values:
            if value in _OPERATION_IDS and value not in ordered:
                ordered.append(value)

    goal_map = {
        "cut_pacing": ("cut", "best_segment", "pace"),
        "reframe": ("reframe",),
        "transition_motion": ("transitions", "pace"),
        "sound_post": ("audio", "music"),
    }
    add(*goal_map.get(str(state["goal"]), ()))
    priority_map = {
        "pace": ("cut", "pace"),
        "product_focus": ("best_segment",),
        "brightness": ("brightness",),
        "speech_clarity": ("audio",),
        "vertical": ("reframe",),
    }
    for priority in state["priorities"]:
        add(*priority_map.get(priority, ()))
        if priority == "branding":
            if "logo" in available_assets:
                add("logo")
            if "watermark" in available_assets:
                add("watermark")
    lowered = str(state["editing_brief"]).casefold()
    keyword_map = (
        (("nhanh", "gọn"), ("cut", "pace")),
        (("sản phẩm", "chủ thể"), ("best_segment",)),
        (("sáng", "tối"), ("brightness",)),
        (("âm lượng", "âm thanh", "lời nói"), ("audio",)),
        (("phụ đề",), ("subtitles",)),
        (("9:16", "khung dọc", "video dọc"), ("reframe",)),
    )
    for keywords, operations in keyword_map:
        if any(keyword in lowered for keyword in keywords):
            add(*operations)
    if "logo" in lowered:
        add("logo")
    if "watermark" in lowered:
        add("watermark")
    add("qa")
    return ordered


def _base_result(state: dict[str, object]) -> dict[str, object]:
    return {
        "session": state,
        "closed": False,
        "exit_parent": False,
        "duplicate": False,
        "persist_plan": None,
        "send_text": "",
        "open_saved_plans": False,
        "saved_plan_action": "",
        "saved_plan_key": "",
        "saved_text": "",
        "saved_fingerprint": "",
        "feedback": "Đã cập nhật kế hoạch.",
    }


def apply_text_input(session: object, text: object, *, now: object | None = None) -> dict[str, object]:
    state = normalize_session(session, now=now)
    if state["screen"] != "brief":
        raise PreviewActionError("brief_step_invalid")
    value = str(text or "").strip()
    if not value or len(value) > MAX_BRIEF_LENGTH:
        raise PreviewActionError("brief_text_invalid")
    state["editing_brief"] = value
    _navigate(state, "platform")
    _touch(state, now)
    result = _base_result(state)
    result["feedback"] = "Đã ghi nhận mong muốn chỉnh sửa."
    return result


def apply_callback(
    session: object,
    callback_value: str,
    *,
    now: object | None = None,
    callback_id: str | None = None,
) -> dict[str, object]:
    sid, verb, args = parse_callback(callback_value)
    if verb == "open":
        result = _base_result(new_session(now=now))
        result["feedback"] = "Đã mở Trợ lý lên kế hoạch chỉnh sửa."
        return result
    state = normalize_session(session, now=now)
    if sid != state["session_id"]:
        raise PublicSessionExpired("session_id_mismatch")
    callback_key = str(callback_id or "").strip()
    if callback_key and callback_key in state["processed_callback_ids"]:
        result = _base_result(state)
        result["duplicate"] = True
        result["feedback"] = "Thao tác này đã được nhận."
        return result
    result = _base_result(state)
    if verb == "close":
        result["closed"] = True
        result["feedback"] = "Đã đóng trợ lý."
        return result
    if verb == "back":
        history = list(state["history"])
        if not history:
            if state["screen"] != "goal":
                raise PreviewActionError("back_history_empty")
            result["exit_parent"] = True
            result["feedback"] = "Đã quay lại Menu Video."
            return result
        state["screen"] = history.pop()
        state["history"] = history
        _touch(state, now)
        result["session"] = state
        result["feedback"] = "Đã quay lại đúng bước trước."
        return result
    if verb == "goal":
        if state["screen"] != "goal":
            raise PreviewActionError("goal_step_invalid")
        state["goal"] = args[0]
        _navigate(state, "brief")
    elif verb == "brief_skip":
        if state["screen"] != "brief":
            raise PreviewActionError("brief_step_invalid")
        state["editing_brief"] = ""
        _navigate(state, "platform")
    elif verb == "platform":
        if state["screen"] != "platform":
            raise PreviewActionError("platform_step_invalid")
        state["platform_ratio"] = args[0]
        _navigate(state, "source_duration")
    elif verb == "source":
        if state["screen"] != "source_duration":
            raise PreviewActionError("source_step_invalid")
        state["source_duration"] = args[0]
        _navigate(state, "target_duration")
    elif verb == "target":
        if state["screen"] != "target_duration":
            raise PreviewActionError("target_step_invalid")
        state["target_duration"] = args[0]
        _navigate(state, "assets")
    elif verb == "asset":
        if state["screen"] != "assets":
            raise PreviewActionError("asset_step_invalid")
        value = args[0]
        if value == "none":
            state["available_assets"] = [] if state["available_assets"] == ["none"] else ["none"]
        else:
            state["available_assets"] = [item for item in state["available_assets"] if item != "none"]
            state["available_assets"] = _toggle(state["available_assets"], value)
    elif verb == "assets_done":
        if state["screen"] != "assets" or not state["available_assets"]:
            raise PreviewActionError("assets_required")
        _navigate(state, "priorities")
    elif verb == "priority":
        if state["screen"] != "priorities":
            raise PreviewActionError("priority_step_invalid")
        state["priorities"] = _toggle(state["priorities"], args[0])
    elif verb == "priorities_done":
        if state["screen"] != "priorities" or not state["priorities"]:
            raise PreviewActionError("priorities_required")
        state["selected_operations"] = suggest_operations(state)
        _navigate(state, "operations")
    elif verb == "op":
        if state["screen"] != "operations":
            raise PreviewActionError("operation_step_invalid")
        state["selected_operations"] = _toggle(state["selected_operations"], args[0])
    elif verb == "operations_done":
        if state["screen"] != "operations" or not state["selected_operations"]:
            raise PreviewActionError("operations_required")
        _navigate(state, "safety")
    elif verb == "safety_done":
        if state["screen"] != "safety":
            raise PreviewActionError("safety_step_invalid")
        _navigate(state, "summary")
    elif verb == "persist":
        if state["screen"] != "summary":
            raise PreviewActionError("persist_step_invalid")
        result["persist_plan"] = serialize_plan(state)
        result["feedback"] = "Đang lưu kế hoạch."
        return result
    elif verb == "send":
        if state["screen"] != "summary":
            raise PreviewActionError("send_step_invalid")
        text = planning_summary_text(state)
        fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if state["sent_summary_fingerprint"] == fingerprint:
            result["duplicate"] = True
            result["feedback"] = "Kế hoạch này đã được gửi vào chat."
            return result
        result["send_text"] = text
        result["saved_text"] = text
        result["saved_fingerprint"] = fingerprint
        result["feedback"] = "Đã chuẩn bị kế hoạch để gửi vào chat."
        return result
    elif verb == "plans":
        if state["screen"] != "summary":
            raise PreviewActionError("plans_step_invalid")
        result["open_saved_plans"] = True
        result["saved_plan_action"] = "library"
        result["feedback"] = "Đang mở Kế hoạch của tôi."
        return result
    elif verb == "library":
        if state["screen"] != "summary":
            raise PreviewActionError("library_step_invalid")
        result["open_saved_plans"] = True
        result["saved_plan_action"] = "library"
        result["feedback"] = "Đang mở Kế hoạch của tôi."
        return result
    elif verb == "current":
        if state["screen"] != "summary":
            raise PreviewActionError("current_step_invalid")
        result["saved_plan_action"] = "current"
        result["feedback"] = "Đã quay lại bản kế hoạch hiện tại."
        return result
    elif verb in {"view", "edit", "delete", "delete_confirm"}:
        if state["screen"] != "summary":
            raise PreviewActionError("saved_plan_step_invalid")
        result["saved_plan_action"] = verb
        result["saved_plan_key"] = args[0]
        result["feedback"] = "Đã nhận thao tác với kế hoạch đã lưu."
        return result
    else:
        raise PreviewActionError("callback_not_implemented")
    _touch(state, now)
    result["session"] = state
    return result


def _plan_title(state: dict[str, object]) -> str:
    goal = _label(GOAL_OPTIONS, state["goal"]).lstrip("✂️🎯✨🎧 ")
    platform = _label(PLATFORM_OPTIONS, state["platform_ratio"])
    return f"{goal} · {platform}"[:120]


def _has_time_range(text: str) -> bool:
    return bool(_TIME_RANGE_RE.search(text))


def rights_notes(session: object) -> list[str]:
    state = normalize_session(session)
    notes = list(BASE_RIGHTS_NOTES)
    assets = set(state["available_assets"])
    assets.discard("none")
    selected = set(state["selected_operations"])
    missing_branding = [
        asset
        for asset in ("logo", "watermark")
        if asset in selected and asset not in assets
    ]
    for asset in missing_branding:
        notes.append(f"Cần chuẩn bị {asset} có quyền sử dụng trước khi thực thi kế hoạch.")
    if (
        "branding" in state["priorities"]
        and not ({"logo", "watermark"} & assets)
        and not missing_branding
    ):
        notes.append("Cần chuẩn bị logo hoặc watermark có quyền sử dụng trước khi thực thi kế hoạch.")
    return notes


def ordered_steps(session: object) -> list[str]:
    state = normalize_session(session)
    source_label = _label(SOURCE_DURATION_OPTIONS, state["source_duration"]).lower()
    target_label = _label(TARGET_DURATION_OPTIONS, state["target_duration"])
    if state["target_duration"] == "keep":
        duration_step = f"Giữ thành phẩm gần thời lượng nguồn ({source_label})."
    else:
        duration_step = f"Hướng thành phẩm tới {target_label} từ video nguồn {source_label}."
    steps = [duration_step]
    brief = str(state["editing_brief"]).strip()
    if brief:
        if _has_time_range(brief):
            steps.append(f"Thực hiện đúng các mốc người dùng đã ghi: {brief}")
        else:
            steps.append(f"Giữ yêu cầu của người dùng làm tiêu chí: {brief}")
    for operation in _ordered_operation_ids(state["selected_operations"]):
        sentence = PUBLIC_OPERATION_STEPS[operation]
        if operation == "best_segment" and _has_time_range(brief):
            sentence = "Giữ đúng các đoạn đã nêu trong yêu cầu và ưu tiên phần sản phẩm rõ nhất."
        if sentence not in steps:
            steps.append(sentence)
    return steps


def serialize_plan(session: object) -> dict[str, object]:
    state = normalize_session(session)
    required = (
        state["goal"],
        state["platform_ratio"],
        state["source_duration"],
        state["target_duration"],
        state["available_assets"],
        state["priorities"],
        state["selected_operations"],
    )
    if not all(required):
        raise PreviewActionError("plan_incomplete")
    return {
        "plan_schema_version": PLAN_SCHEMA_VERSION,
        "plan_id": str(state["plan_id"]),
        "title": _plan_title(state),
        "goal": str(state["goal"]),
        "editing_brief": str(state["editing_brief"]),
        "platform_ratio": str(state["platform_ratio"]),
        "source_duration": str(state["source_duration"]),
        "target_duration": str(state["target_duration"]),
        "available_assets": list(state["available_assets"]),
        "priorities": list(state["priorities"]),
        "selected_operations": _ordered_operation_ids(state["selected_operations"]),
        "ordered_steps": ordered_steps(state),
        "rights_notes": rights_notes(state),
        "created_at": int(state["created_at"]),
        "updated_at": int(state["updated_at"]),
    }


def session_from_plan(plan: object, *, session_id: str | None = None, now: object | None = None) -> dict[str, object]:
    if not isinstance(plan, dict):
        raise PreviewActionError("plan_invalid")
    expected = {
        "plan_schema_version",
        "plan_id",
        "title",
        "goal",
        "editing_brief",
        "platform_ratio",
        "source_duration",
        "target_duration",
        "available_assets",
        "priorities",
        "selected_operations",
        "ordered_steps",
        "rights_notes",
        "created_at",
        "updated_at",
    }
    if set(plan) != expected or plan.get("plan_schema_version") != PLAN_SCHEMA_VERSION:
        raise PreviewActionError("plan_fields_invalid")
    created_at = _timestamp(plan.get("created_at"))
    updated_at = _timestamp(plan.get("updated_at"))
    if updated_at < created_at:
        raise PreviewActionError("plan_timestamp_order_invalid")
    plan_rights = plan.get("rights_notes")
    if (
        not isinstance(plan_rights, list)
        or not plan_rights
        or len(plan_rights) > 8
        or not all(isinstance(note, str) and note.strip() and len(note) <= 500 for note in plan_rights)
    ):
        raise PreviewActionError("plan_rights_invalid")
    state = new_session(session_id, now=now)
    state.update(
        {
            "plan_id": str(plan.get("plan_id") or "")[:24],
            "goal": plan.get("goal"),
            "editing_brief": plan.get("editing_brief"),
            "platform_ratio": plan.get("platform_ratio"),
            "source_duration": plan.get("source_duration"),
            "target_duration": plan.get("target_duration"),
            "available_assets": copy.deepcopy(plan.get("available_assets")),
            "priorities": copy.deepcopy(plan.get("priorities")),
            "selected_operations": copy.deepcopy(plan.get("selected_operations")),
            "screen": "summary",
            "history": list(_SCREENS[:-1]),
        }
    )
    normalized = normalize_session(state)
    regenerated = serialize_plan(normalized)
    for field in expected - {"created_at", "updated_at"}:
        if regenerated[field] != copy.deepcopy(plan[field]):
            raise PreviewActionError("plan_content_invalid")
    return normalized


def planning_summary_text(session: object) -> str:
    state = normalize_session(session)
    plan = serialize_plan(state)
    assets = [
        _label(ASSET_OPTIONS, value)
        for value in state["available_assets"]
        if value != "none"
    ] or ["Chưa có tài nguyên bổ sung"]
    brief = html.escape(str(state["editing_brief"])) if state["editing_brief"] else "Chưa nhập; dùng lựa chọn hướng dẫn bên dưới."
    step_lines = "\n".join(
        f"{index}. {html.escape(step)}"
        for index, step in enumerate(plan["ordered_steps"], 1)
    )
    rights_lines = "\n".join(f"• {html.escape(note)}" for note in plan["rights_notes"])
    return (
        "🧭 <b>KẾ HOẠCH CHỈNH SỬA</b>\n\n"
        f"<b>{html.escape(str(plan['title']))}</b>\n\n"
        f"• Mục tiêu: {_label(GOAL_OPTIONS, state['goal'])}\n"
        f"• Video nguồn: {_label(SOURCE_DURATION_OPTIONS, state['source_duration'])}\n"
        f"• Thành phẩm: {_label(TARGET_DURATION_OPTIONS, state['target_duration'])}\n"
        f"• Nền tảng/tỷ lệ: {_label(PLATFORM_OPTIONS, state['platform_ratio'])}\n"
        f"• Tài nguyên đang có: {html.escape(', '.join(assets))}\n"
        f"• Yêu cầu cụ thể: {brief}\n\n"
        "<b>Các bước đề xuất</b>\n"
        f"{step_lines}\n\n"
        "🛡 <b>Quyền và tài nguyên</b>\n"
        f"{rights_lines}\n"
        "Đây chỉ là kế hoạch: không xử lý media, không tạo tác vụ, không xuất video và không trừ Xu."
    )


def _option_rows(
    state: dict[str, object],
    options: tuple[tuple[str, str], ...],
    verb: str,
    *,
    selected: list[str] | None = None,
) -> list[tuple[tuple[str, str], ...]]:
    rows: list[tuple[tuple[str, str], ...]] = []
    selected_values = set(selected or ())
    buttons = [
        (
            ("☑️ " if value in selected_values else "") + label,
            callback_data(str(state["session_id"]), verb, value),
        )
        for value, label in options
    ]
    for start in range(0, len(buttons), 2):
        rows.append(tuple(buttons[start : start + 2]))
    return rows


def _nav_rows(state: dict[str, object], *, close: bool = False) -> list[tuple[tuple[str, str], ...]]:
    label = "⬅️ Menu Video" if state["screen"] == "goal" else "⬅️ Quay lại"
    rows = [((label, callback_data(str(state["session_id"]), "back")),)]
    if close:
        rows.append((("✖️ Đóng", callback_data(str(state["session_id"]), "close")),))
    return rows


def render_view(session: object) -> dict[str, object]:
    state = normalize_session(session)
    screen = str(state["screen"])
    if screen == "goal":
        rows = _option_rows(state, GOAL_OPTIONS, "goal") + _nav_rows(state)
        text = "🧭 <b>LÊN KẾ HOẠCH CHỈNH SỬA</b>\n\nBạn muốn video sau khi chỉnh đạt mục tiêu gì?"
    elif screen == "brief":
        rows = [(("Bỏ qua, dùng lựa chọn hướng dẫn", callback_data(str(state["session_id"]), "brief_skip")),), *_nav_rows(state)]
        text = "✍️ <b>MÔ TẢ MONG MUỐN</b>\n\nHãy nhắn điều bạn muốn thay đổi. Có thể ghi rõ đoạn cần giữ/bỏ và vị trí nhận diện nếu đã biết."
    elif screen == "platform":
        rows = _option_rows(state, PLATFORM_OPTIONS, "platform") + _nav_rows(state)
        text = "📱 <b>NỀN TẢNG VÀ TỶ LỆ</b>\n\nChọn nơi đăng thành phẩm."
    elif screen == "source_duration":
        rows = _option_rows(state, SOURCE_DURATION_OPTIONS, "source") + _nav_rows(state)
        text = "⏱ <b>THỜI LƯỢNG VIDEO NGUỒN</b>\n\nChọn khoảng gần nhất."
    elif screen == "target_duration":
        rows = _option_rows(state, TARGET_DURATION_OPTIONS, "target") + _nav_rows(state)
        text = "🎯 <b>THỜI LƯỢNG THÀNH PHẨM</b>\n\nBạn muốn video sau khi chỉnh dài khoảng bao lâu?"
    elif screen == "assets":
        rows = _option_rows(state, ASSET_OPTIONS, "asset", selected=state["available_assets"])
        rows.append((("Tiếp tục ➡️", callback_data(str(state["session_id"]), "assets_done")),))
        rows.extend(_nav_rows(state))
        text = "📦 <b>TÀI NGUYÊN ĐANG CÓ</b>\n\nChọn những gì bạn đã chuẩn bị."
    elif screen == "priorities":
        rows = _option_rows(state, PRIORITY_OPTIONS, "priority", selected=state["priorities"])
        rows.append((("Xem đề xuất ➡️", callback_data(str(state["session_id"]), "priorities_done")),))
        rows.extend(_nav_rows(state))
        text = "⭐ <b>ƯU TIÊN CHỈNH SỬA</b>\n\nChọn một hoặc nhiều điều quan trọng nhất."
    elif screen == "operations":
        rows = _option_rows(state, OPERATION_OPTIONS, "op", selected=state["selected_operations"])
        rows.append((("Xác nhận hạng mục ➡️", callback_data(str(state["session_id"]), "operations_done")),))
        rows.extend(_nav_rows(state))
        text = "🧩 <b>HẠNG MỤC ĐỀ XUẤT</b>\n\nTrợ lý đã sắp đề xuất từ mục tiêu và ưu tiên. Bạn có thể bật/tắt trước khi tiếp tục."
    elif screen == "safety":
        rows = [(("Tạo bản kế hoạch ➡️", callback_data(str(state["session_id"]), "safety_done")),), *_nav_rows(state)]
        text = "🛡 <b>QUYỀN VÀ LƯU Ý</b>\n\nHãy bảo đảm bạn có quyền sử dụng video, logo, watermark, phụ đề và nhạc đã chọn."
    elif screen == "summary":
        rows = [
            (("💾 Lưu kế hoạch", callback_data(str(state["session_id"]), "persist")),),
            (("💬 Gửi kế hoạch vào chat", callback_data(str(state["session_id"]), "send")),),
            (("📂 Kế hoạch của tôi", callback_data(str(state["session_id"]), "plans")),),
            *_nav_rows(state, close=True),
        ]
        text = planning_summary_text(state)
    else:
        raise PreviewDataError("screen_unrenderable")
    return {"screen": screen, "text": text, "rows": tuple(rows)}


def new_store() -> dict[str, object]:
    return {"sessions": {}, "active_by_chat": {}}


def session_store_key(user_id: object, chat_id: object, session_id: object) -> str:
    uid, cid, sid = str(user_id or "").strip(), str(chat_id or "").strip(), str(session_id or "").strip()
    if not uid or not cid or not _valid_session_id(sid):
        raise PreviewActionError("session_store_key_invalid")
    return f"{uid}:{cid}:{sid}"


def _active_chat_key(user_id: object, chat_id: object) -> str:
    uid, cid = str(user_id or "").strip(), str(chat_id or "").strip()
    if not uid or not cid:
        raise PreviewActionError("chat_key_invalid")
    return f"{uid}:{cid}"


def _transaction_lock(key: str) -> asyncio.Lock:
    lock = _SESSION_TRANSACTION_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _SESSION_TRANSACTION_LOCKS[key] = lock
    return lock


def open_transaction_lock(user_id: object, chat_id: object) -> asyncio.Lock:
    return _transaction_lock(f"open:{_active_chat_key(user_id, chat_id)}")


def session_transaction_lock(user_id: object, chat_id: object, session_id: object) -> asyncio.Lock:
    return _transaction_lock(f"session:{session_store_key(user_id, chat_id, session_id)}")


def prune_store(store: dict[str, object], *, now: object | None = None) -> dict[str, object]:
    if not isinstance(store, dict) or not isinstance(store.get("sessions"), dict) or not isinstance(store.get("active_by_chat"), dict):
        raise PreviewActionError("session_store_invalid")
    current = _timestamp(now)
    ranked: list[tuple[int, str]] = []
    for key, value in list(store["sessions"].items()):
        if not isinstance(key, str) or not session_is_fresh(value, now=current):
            continue
        try:
            state = normalize_session(value)
        except PreviewActionError:
            continue
        ranked.append((int(state["updated_at"]), key))
    retained = {key for _stamp, key in sorted(ranked, reverse=True)[:MAX_STORED_SESSIONS]}
    store["sessions"] = {key: value for key, value in store["sessions"].items() if key in retained}
    store["active_by_chat"] = {
        key: sid
        for key, sid in store["active_by_chat"].items()
        if f"{key}:{sid}" in store["sessions"]
    }
    return store


def put_session(store: dict[str, object], user_id: object, chat_id: object, session: dict[str, object]) -> dict[str, object]:
    state = normalize_session(session)
    store.setdefault("sessions", {})
    store.setdefault("active_by_chat", {})
    key = session_store_key(user_id, chat_id, state["session_id"])
    store["sessions"][key] = copy.deepcopy(state)
    store["active_by_chat"][_active_chat_key(user_id, chat_id)] = state["session_id"]
    prune_store(store, now=state["updated_at"])
    return copy.deepcopy(state)


save_session = put_session


def get_session(store: dict[str, object], user_id: object, chat_id: object, session_id: object, *, now: object | None = None) -> dict[str, object] | None:
    if not isinstance(store, dict) or not isinstance(store.get("sessions"), dict):
        return None
    try:
        key = session_store_key(user_id, chat_id, session_id)
    except PreviewActionError:
        return None
    raw = store["sessions"].get(key)
    if not isinstance(raw, dict) or (now is not None and not session_is_fresh(raw, now=now)):
        delete_session(store, user_id, chat_id, session_id)
        return None
    try:
        return normalize_session(raw)
    except PreviewActionError:
        delete_session(store, user_id, chat_id, session_id)
        return None


def delete_session(store: dict[str, object], user_id: object, chat_id: object, session_id: object) -> bool:
    if not isinstance(store, dict) or not isinstance(store.get("sessions"), dict):
        return False
    try:
        key = session_store_key(user_id, chat_id, session_id)
    except PreviewActionError:
        return False
    removed = store["sessions"].pop(key, None) is not None
    active_key = _active_chat_key(user_id, chat_id)
    if isinstance(store.get("active_by_chat"), dict) and store["active_by_chat"].get(active_key) == str(session_id):
        store["active_by_chat"].pop(active_key, None)
    return removed


def store_has_callback_id(store: object, callback_id: object, *, now: object | None = None) -> bool:
    if not isinstance(store, dict) or not isinstance(store.get("sessions"), dict):
        return False
    prune_store(store, now=now)
    value = str(callback_id or "").strip()
    return bool(value) and any(value in (session.get("processed_callback_ids") or ()) for session in store["sessions"].values() if isinstance(session, dict))


def commit_callback_id(session: object, callback_id: object, *, now: object | None = None) -> dict[str, object]:
    state = normalize_session(session)
    value = str(callback_id or "").strip()
    if value and value not in state["processed_callback_ids"]:
        state["processed_callback_ids"] = [*state["processed_callback_ids"], value][-64:]
        _touch(state, now)
    return normalize_session(state)


def commit_sent_summary_delivery(session: object, callback_id: object, fingerprint: object, *, now: object | None = None) -> dict[str, object]:
    state = normalize_session(session)
    value = str(fingerprint or "").strip()
    if state["screen"] != "summary" or not _FINGERPRINT_RE.fullmatch(value):
        raise PreviewActionError("summary_delivery_invalid")
    state = commit_callback_id(state, callback_id, now=now)
    state["sent_summary_fingerprint"] = value
    _touch(state, now)
    return normalize_session(state)


commit_saved_summary_delivery = commit_sent_summary_delivery


async def _invoke_callback(callback: Callable[[], object]) -> bool:
    value = callback()
    if inspect.isawaitable(value):
        value = await value
    return value is not False


async def deliver_then_commit(
    edit: Callable[[], Awaitable[object]],
    reply: Callable[[], Awaitable[object]],
    commit: Callable[[], object],
    answer: Callable[[], Awaitable[object]],
) -> bool:
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
        value = commit()
        if inspect.isawaitable(value):
            await value
    except Exception:
        return False
    try:
        await _invoke_callback(answer)
    except Exception:
        pass
    return True
