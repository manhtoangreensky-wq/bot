from __future__ import annotations

import copy
import html
import json
from functools import lru_cache
from pathlib import Path
from typing import Any


CALLBACK_PREFIX = "lvs27a"
STATE_KEY = "local_video_studio27a_preview"
PREVIEW_VERSION = "27A"
CATALOG_PAGE_SIZE = 6
PACK_PAGE_SIZE = 8

LOCAL_RECORD_IDS = (
    "openmontage_local",
    "editing_grammar",
    "framing_composition",
    "pacing_storytelling",
    "camera_movement",
    "rights_requirements",
    "transition_motion_pack",
    "sound_design_pack",
    "viral_effects",
    "local_free_capabilities",
    "video_qa",
)
PAID_RECORD_IDS = ("mosaic_motion", "higgsfield", "suno")
RECORD_IDS = LOCAL_RECORD_IDS + PAID_RECORD_IDS
ALLOWED_VERBS = ("open", "pick", "catalog", "pack", "qa", "back", "home", "close")
SAFE_READINESS_STATES = (
    "NOT_INSTALLED",
    "INSTALLED",
    "CONTRACT_PASS",
    "LOCAL_DEMO_PASS",
    "PAID_SMOKE_REQUIRED",
)
EXECUTION_COUNTER_IDS = (
    "provider_calls",
    "paid_provider_calls",
    "paid_generations",
    "motion_calls",
    "higgsfield_generation_calls",
    "wallet_mutations",
    "telegram_deliveries",
    "production_deploys",
    "vps_updates",
)
QA_CAPABILITY_IDS = (
    "video_qa.file_exists",
    "video_qa.file_size_minimum",
    "video_qa.container_valid",
    "video_qa.video_stream_exists",
    "video_qa.duration_positive",
    "video_qa.dimensions_valid",
    "video_qa.frame_rate_valid",
    "video_qa.audio_stream_when_promised",
    "video_qa.audio_loudness_valid",
    "video_qa.true_peak_valid",
    "video_qa.black_frame_detection",
    "video_qa.frozen_frame_detection",
    "video_qa.duplicated_scene_warning",
    "video_qa.subtitle_safe_area",
    "video_qa.subtitle_readability",
    "video_qa.aspect_ratio",
    "video_qa.delivery_filename",
    "video_qa.output_size",
    "video_qa.render_promise_verification",
)

FLOW_STEPS = {
    "create": (
        ("create_goal", "goal"),
        ("create_format", "format"),
        ("create_style", "style"),
        ("create_audio", "audio"),
        ("create_review", ""),
        ("create_qa", ""),
        ("complete", ""),
    ),
    "edit": (
        ("edit_goal", "goal"),
        ("edit_source", "source"),
        ("edit_delivery", "delivery"),
        ("edit_review", ""),
        ("edit_qa", ""),
        ("complete", ""),
    ),
}

FLOW_OPTIONS = {
    "create_goal": (
        ("ad", "Quảng cáo / bán hàng"),
        ("story", "Kể chuyện thương hiệu"),
        ("explainer", "Giải thích / hướng dẫn"),
        ("social", "Nội dung social ngắn"),
    ),
    "create_format": (
        ("9x16", "9:16 · Video dọc"),
        ("16x9", "16:9 · Video ngang"),
        ("1x1", "1:1 · Hình vuông"),
        ("4x5", "4:5 · Social feed"),
    ),
    "create_style": (
        ("cinematic", "Điện ảnh"),
        ("documentary", "Phóng sự"),
        ("kinetic", "Kinetic typography"),
        ("clean", "Tối giản / sạch"),
    ),
    "create_audio": (
        ("owner_licensed", "Audio có quyền của owner"),
        ("local_sfx", "Sound design local"),
        ("silence", "Không dùng nhạc"),
    ),
    "edit_goal": (
        ("cut_pacing", "Cắt dựng & nhịp"),
        ("reframe", "Reframe & bố cục"),
        ("transition_motion", "Transition & motion"),
        ("sound_post", "Sound & audio post"),
    ),
    "edit_source": (
        ("owner_footage", "Footage do owner sở hữu"),
        ("licensed_local", "Asset local có license"),
        ("planned_shoot", "Footage quay theo kế hoạch"),
    ),
    "edit_delivery": (
        ("9x16", "9:16 · Video dọc"),
        ("16x9", "16:9 · Video ngang"),
        ("1x1", "1:1 · Hình vuông"),
        ("4x5", "4:5 · Social feed"),
    ),
}

SCREEN_TITLES = {
    "create_goal": "Mục tiêu video mới",
    "create_format": "Định dạng giao",
    "create_style": "Phong cách hình ảnh",
    "create_audio": "Phương án âm thanh",
    "edit_goal": "Mục tiêu chỉnh footage",
    "edit_source": "Nguồn và quyền sử dụng",
    "edit_delivery": "Định dạng giao",
}

FLOW_NEXT = {
    "create_goal": "create_format",
    "create_format": "create_style",
    "create_style": "create_audio",
    "create_audio": "create_review",
    "edit_goal": "edit_source",
    "edit_source": "edit_delivery",
    "edit_delivery": "edit_review",
}

FLOW_BACK_TARGETS = {
    "create": {
        "create_goal": "home",
        "create_format": "create_goal",
        "create_style": "create_format",
        "create_audio": "create_style",
        "create_review": "create_audio",
        "create_qa": "create_review",
        "complete": "create_qa",
    },
    "edit": {
        "edit_goal": "home",
        "edit_source": "edit_goal",
        "edit_delivery": "edit_source",
        "edit_review": "edit_delivery",
        "edit_qa": "edit_review",
        "complete": "edit_qa",
    },
}
SCREEN_BACK_TARGETS = {
    "catalog": "home",
    "pack": "catalog",
    "safety": "home",
    "qa": "safety",
}
SCREEN_MODES = {
    "home": "",
    "catalog": "catalog",
    "pack": "catalog",
    "safety": "safety",
    "qa": "safety",
    **{
        screen: mode
        for mode, steps in FLOW_STEPS.items()
        for screen, _ in steps
        if screen != "complete"
    },
}

KNOWN_SCREENS = {
    "home",
    "catalog",
    "pack",
    "safety",
    "qa",
    *(screen for steps in FLOW_STEPS.values() for screen, _ in steps),
}

INDEX_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "video"
    / "local-video-codex-index"
    / "capability_index.json"
)


class PreviewDataError(ValueError):
    """The 26I index cannot safely back the preview."""


class PreviewActionError(ValueError):
    """A callback is malformed, stale, or tries to skip a required step."""


def _is_non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def validate_capability_index(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise PreviewDataError("capability_index_not_object")
    for field, expected in (
        ("planning_only", True),
        ("runtime_registered", False),
        ("provider_executable", False),
        ("public_ui", False),
    ):
        if payload.get(field) is not expected:
            raise PreviewDataError(f"unsafe_index_{field}")
    records = payload.get("capabilities")
    if (
        not _is_non_negative_int(payload.get("capability_count"))
        or payload.get("capability_count") != 14
        or not isinstance(records, list)
        or len(records) != 14
    ):
        raise PreviewDataError("capability_record_count_invalid")
    if tuple(record.get("capability_id") for record in records if isinstance(record, dict)) != RECORD_IDS:
        raise PreviewDataError("capability_record_order_invalid")

    all_ids: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            raise PreviewDataError("capability_record_invalid")
        for field, expected in (
            ("planning_only", True),
            ("runtime_registered", False),
            ("provider_executable", False),
            ("public_ui", False),
            ("production_readiness", False),
        ):
            if record.get(field) is not expected:
                raise PreviewDataError(f"unsafe_{field}")
        display_name = record.get("display_name_vi")
        if not isinstance(display_name, str) or not display_name.strip():
            raise PreviewDataError("display_name_invalid")
        readiness = record.get("highest_readiness")
        if not isinstance(readiness, str) or readiness not in SAFE_READINESS_STATES:
            raise PreviewDataError("unsafe_readiness")
        capability_ids = record.get("capability_ids")
        if not isinstance(capability_ids, list) or not all(
            isinstance(item, str) and item.strip() for item in capability_ids
        ):
            raise PreviewDataError("capability_ids_invalid")
        if (
            not _is_non_negative_int(record.get("capability_count"))
            or record.get("capability_count") != len(capability_ids)
        ):
            raise PreviewDataError("record_capability_count_invalid")
        if len(set(capability_ids)) != len(capability_ids):
            raise PreviewDataError("record_capability_ids_duplicate")
        all_ids.extend(capability_ids)

    if len(all_ids) != 251 or len(set(all_ids)) != 251:
        raise PreviewDataError("global_capability_coverage_invalid")
    record_map = {record["capability_id"]: record for record in records}
    local_ids = [
        capability_id
        for record_id in LOCAL_RECORD_IDS
        for capability_id in record_map[record_id]["capability_ids"]
    ]
    paid_ids = [
        capability_id
        for record_id in PAID_RECORD_IDS
        for capability_id in record_map[record_id]["capability_ids"]
    ]
    qa_ids = tuple(record_map["video_qa"]["capability_ids"])
    if len(local_ids) != 248 or len(paid_ids) != 3 or qa_ids != QA_CAPABILITY_IDS:
        raise PreviewDataError("capability_partition_invalid")
    counters = payload.get("execution_counters")
    if not isinstance(counters, dict) or tuple(counters) != EXECUTION_COUNTER_IDS:
        raise PreviewDataError("execution_counter_schema_invalid")
    if any(not _is_non_negative_int(value) or value != 0 for value in counters.values()):
        raise PreviewDataError("execution_counter_nonzero")
    return copy.deepcopy(payload)


@lru_cache(maxsize=1)
def _cached_capability_index() -> dict[str, object]:
    try:
        payload = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PreviewDataError("capability_index_unavailable") from exc
    return validate_capability_index(payload)


def load_capability_index() -> dict[str, object]:
    return copy.deepcopy(_cached_capability_index())


def capability_coverage(payload: dict[str, object]) -> dict[str, tuple[str, ...]]:
    validated = validate_capability_index(payload)
    records = {record["capability_id"]: record for record in validated["capabilities"]}
    local = tuple(
        capability_id
        for record_id in LOCAL_RECORD_IDS
        for capability_id in records[record_id]["capability_ids"]
    )
    paid = tuple(
        capability_id
        for record_id in PAID_RECORD_IDS
        for capability_id in records[record_id]["capability_ids"]
    )
    qa = tuple(records["video_qa"]["capability_ids"])
    return {"local": local, "paid": paid, "all": local + paid, "qa": qa}


def new_session() -> dict[str, object]:
    return {
        "version": PREVIEW_VERSION,
        "screen": "home",
        "history": [],
        "mode": "",
        "selections": {},
        "catalog_page": 0,
        "pack_id": "",
        "pack_page": 0,
    }


def expected_history(screen: str, mode: str) -> list[str]:
    if screen == "home":
        return []
    if mode in FLOW_STEPS:
        screens = tuple(step_screen for step_screen, _ in FLOW_STEPS[mode])
        if screen not in screens:
            return []
        index = screens.index(screen)
        return ["home", *screens[:index]]
    if screen == "catalog" and mode == "catalog":
        return ["home"]
    if screen == "pack" and mode == "catalog":
        return ["home", "catalog"]
    if screen == "safety" and mode == "safety":
        return ["home"]
    if screen == "qa" and mode == "safety":
        return ["home", "safety"]
    return []


def _flow_fields(mode: str) -> tuple[str, ...]:
    return tuple(field for _, field in FLOW_STEPS[mode] if field)


def _max_selection_prefix(screen: str, mode: str) -> tuple[str, ...]:
    fields = _flow_fields(mode)
    if screen == "complete" or screen.endswith("_review") or screen.endswith("_qa"):
        return fields
    current_field = _step_field(screen)
    if not current_field or current_field not in fields:
        return ()
    return fields[: fields.index(current_field) + 1]


def _flow_selection_shape_valid(
    screen: str,
    mode: str,
    selections: dict[str, str],
) -> bool:
    if mode not in FLOW_STEPS:
        return not selections
    fields = _flow_fields(mode)
    if screen == "complete" or screen.endswith("_review") or screen.endswith("_qa"):
        expected_prefixes = (fields,)
    else:
        current_field = _step_field(screen)
        if not current_field or current_field not in fields:
            return False
        index = fields.index(current_field)
        expected_prefixes = (fields[:index], fields[: index + 1])
    if not any(set(selections) == set(prefix) for prefix in expected_prefixes):
        return False
    for field, value in selections.items():
        option_screen = next(
            (
                step_screen
                for step_screen, step_field in FLOW_STEPS[mode]
                if step_field == field
            ),
            "",
        )
        if not option_screen or value not in {item[0] for item in FLOW_OPTIONS[option_screen]}:
            return False
    return True


def normalize_session(session: object) -> dict[str, object]:
    if not isinstance(session, dict) or session.get("version") != PREVIEW_VERSION:
        return new_session()
    screen = str(session.get("screen") or "home")
    if screen not in KNOWN_SCREENS:
        return new_session()
    history_raw = session.get("history")
    history = [str(item) for item in history_raw] if isinstance(history_raw, list) else []
    if any(item not in KNOWN_SCREENS for item in history):
        history = []
    mode = str(session.get("mode") or "")
    if mode not in {"", "create", "edit", "catalog", "safety"}:
        mode = ""
    if screen == "complete":
        if mode not in {"create", "edit"}:
            return new_session()
    elif mode != SCREEN_MODES.get(screen):
        return new_session()
    if history != expected_history(screen, mode):
        return new_session()
    raw_selections = session.get("selections")
    if not isinstance(raw_selections, dict):
        return new_session()
    selections: dict[str, str] = {}
    for key, value in raw_selections.items():
        if not isinstance(key, str) or not isinstance(value, str):
            return new_session()
        if key not in {"goal", "format", "style", "audio", "source", "delivery"}:
            return new_session()
        if "|" in value or len(value) > 40:
            return new_session()
        selections[key] = value
    if not _flow_selection_shape_valid(screen, mode, selections):
        return new_session()
    catalog_page = session.get("catalog_page")
    pack_page = session.get("pack_page")
    pack_id = str(session.get("pack_id") or "")
    if pack_id not in {"", *LOCAL_RECORD_IDS}:
        pack_id = ""
    if screen == "pack" and not pack_id:
        return new_session()
    return {
        "version": PREVIEW_VERSION,
        "screen": screen,
        "history": history,
        "mode": mode,
        "selections": selections,
        "catalog_page": catalog_page if _is_non_negative_int(catalog_page) else 0,
        "pack_id": pack_id,
        "pack_page": pack_page if _is_non_negative_int(pack_page) else 0,
    }


def callback_data(*parts: object) -> str:
    values = [str(part) for part in parts]
    if not values or any(not value or "|" in value for value in values):
        raise PreviewActionError("callback_part_invalid")
    value = "|".join((CALLBACK_PREFIX, *values))
    if len(value.encode("utf-8")) > 64:
        raise PreviewActionError("callback_too_long")
    return value


def _parse_page(value: str) -> int:
    if value.startswith("-") and value[1:].isdigit():
        return 0
    if not value.isdigit():
        raise PreviewActionError("page_invalid")
    page = int(value)
    if page < 0:
        raise PreviewActionError("page_invalid")
    return page


def parse_callback(value: object) -> tuple[str, tuple[str, ...]]:
    if not isinstance(value, str) or len(value.encode("utf-8")) > 64:
        raise PreviewActionError("callback_invalid")
    parts = value.split("|")
    if len(parts) < 2 or parts[0] != CALLBACK_PREFIX or any(not part for part in parts):
        raise PreviewActionError("callback_namespace_invalid")
    verb = parts[1]
    args = tuple(parts[2:])
    if verb not in ALLOWED_VERBS:
        raise PreviewActionError("callback_verb_invalid")
    if verb in {"back", "home", "close"}:
        if args:
            raise PreviewActionError("callback_shape_invalid")
    elif verb == "open":
        if len(args) != 1 or args[0] not in {"create", "edit", "catalog", "safety"}:
            raise PreviewActionError("open_target_invalid")
    elif verb == "pick":
        if len(args) != 2:
            raise PreviewActionError("pick_shape_invalid")
        screen, selected = args
        if screen in FLOW_OPTIONS:
            if selected not in {item[0] for item in FLOW_OPTIONS[screen]}:
                raise PreviewActionError("pick_value_invalid")
        elif screen in {"create_qa", "edit_qa"}:
            if selected != "complete":
                raise PreviewActionError("pick_value_invalid")
        else:
            raise PreviewActionError("pick_screen_invalid")
    elif verb == "catalog":
        if len(args) != 1:
            raise PreviewActionError("catalog_shape_invalid")
        _parse_page(args[0])
    elif verb == "pack":
        if len(args) != 2 or args[0] not in LOCAL_RECORD_IDS:
            raise PreviewActionError("pack_target_invalid")
        _parse_page(args[1])
    elif verb == "qa":
        if len(args) != 1:
            raise PreviewActionError("qa_shape_invalid")
        if args[0] not in {"create", "edit"}:
            _parse_page(args[0])
    return verb, args


def _navigate(session: dict[str, object], screen: str, *, mode: str | None = None) -> dict[str, object]:
    current = str(session["screen"])
    if current != screen:
        session["history"] = [*session["history"], current]
    session["screen"] = screen
    if mode is not None:
        session["mode"] = mode
    return session


def _step_field(screen: str) -> str:
    for steps in FLOW_STEPS.values():
        for step_screen, field in steps:
            if step_screen == screen:
                return field
    return ""


def apply_callback(session: object, callback_value: str) -> dict[str, object]:
    state = copy.deepcopy(normalize_session(session))
    verb, args = parse_callback(callback_value)
    feedback = "Đã cập nhật preview."
    closed = False

    if verb == "home":
        state = new_session()
        feedback = "Đã về trang đầu preview."
    elif verb == "close":
        state = new_session()
        closed = True
        feedback = "Đã đóng Local Video Studio Preview."
    elif verb == "back":
        history = list(state["history"])
        if not history:
            raise PreviewActionError("back_history_empty")
        target = history.pop()
        if target == "home":
            state = new_session()
        else:
            state["history"] = history
            state["screen"] = target
            if state["mode"] in FLOW_STEPS:
                allowed_fields = _max_selection_prefix(target, str(state["mode"]))
                state["selections"] = {
                    key: value
                    for key, value in state["selections"].items()
                    if key in allowed_fields
                }
        feedback = "Đã quay lại đúng bước trước."
    elif verb == "open":
        if state["screen"] != "home":
            raise PreviewActionError("open_requires_home")
        target = args[0]
        if target in {"create", "edit"}:
            state["selections"] = {}
            state = _navigate(state, f"{target}_goal", mode=target)
        else:
            state = _navigate(state, target, mode=target)
        feedback = "Đã mở đúng quy trình preview."
    elif verb == "pick":
        screen, selected = args
        if state["screen"] != screen:
            raise PreviewActionError("mandatory_step_skipped")
        if screen in FLOW_OPTIONS:
            field = _step_field(screen)
            fields = _flow_fields(str(state["mode"]))
            field_index = fields.index(field)
            state["selections"] = {
                key: value
                for key, value in state["selections"].items()
                if key in fields[:field_index]
            }
            state["selections"] = {**state["selections"], field: selected}
            state = _navigate(state, FLOW_NEXT[screen])
        else:
            expected_mode = "create" if screen == "create_qa" else "edit"
            if state["mode"] != expected_mode or selected != "complete":
                raise PreviewActionError("complete_mode_invalid")
            state = _navigate(state, "complete")
        feedback = "Đã lưu lựa chọn preview."
    elif verb == "catalog":
        if state["screen"] != "catalog":
            raise PreviewActionError("catalog_page_requires_catalog")
        _, state["catalog_page"], _ = paginate(
            LOCAL_RECORD_IDS,
            _parse_page(args[0]),
            CATALOG_PAGE_SIZE,
        )
        feedback = "Đã chuyển trang capability."
    elif verb == "pack":
        record_id, page_text = args
        page = _parse_page(page_text)
        if state["screen"] == "catalog":
            state = _navigate(state, "pack", mode="catalog")
            state["pack_id"] = record_id
        elif state["screen"] == "pack" and state["pack_id"] == record_id:
            pass
        else:
            raise PreviewActionError("pack_navigation_invalid")
        record = _record_map(load_capability_index())[record_id]
        _, state["pack_page"], _ = paginate(
            tuple(record["capability_ids"]),
            page,
            PACK_PAGE_SIZE,
        )
        feedback = "Đã mở capability pack."
    elif verb == "qa":
        target = args[0]
        if target in {"create", "edit"}:
            expected_screen = f"{target}_review"
            if state["screen"] != expected_screen or state["mode"] != target:
                raise PreviewActionError("qa_required_steps_missing")
            state = _navigate(state, f"{target}_qa")
            feedback = "Đã mở QA trước khi hoàn tất preview."
        else:
            page = _parse_page(target)
            if state["screen"] == "safety":
                state = _navigate(state, "qa", mode="safety")
            elif state["screen"] != "qa" or state["mode"] != "safety":
                raise PreviewActionError("qa_catalog_navigation_invalid")
            qa_record = _record_map(load_capability_index())["video_qa"]
            _, state["pack_page"], _ = paginate(
                tuple(qa_record["capability_ids"]),
                page,
                PACK_PAGE_SIZE,
            )
            feedback = "Đã chuyển trang QA."
    return {"session": state, "closed": closed, "feedback": feedback}


def paginate(items: tuple[Any, ...], page: int, page_size: int) -> tuple[tuple[Any, ...], int, int]:
    if page_size <= 0:
        raise PreviewDataError("page_size_invalid")
    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    current = min(max(int(page or 0), 0), total_pages - 1)
    start = current * page_size
    return tuple(items[start : start + page_size]), current, total_pages


def _rows(*rows: tuple[tuple[str, str], ...]) -> tuple[tuple[tuple[str, str], ...], ...]:
    return tuple(row for row in rows if row)


def _nav_rows(session: dict[str, object], *, close: bool = False) -> tuple[tuple[tuple[str, str], ...], ...]:
    rows: list[tuple[tuple[str, str], ...]] = []
    if session["history"]:
        rows.append(
            (
                ("⬅️ Quay lại", callback_data("back")),
                ("🏠 Trang đầu preview", callback_data("home")),
            )
        )
    if close:
        rows.append((("✖️ Đóng preview", callback_data("close")),))
    return tuple(rows)


def _page_row(
    current: int,
    total: int,
    previous_callback: str,
    next_callback: str,
) -> tuple[tuple[str, str], ...]:
    buttons: list[tuple[str, str]] = []
    if current > 0:
        buttons.append(("⬅️ Trang trước", previous_callback))
    if current + 1 < total:
        buttons.append(("Trang sau ➡️", next_callback))
    return tuple(buttons)


def _record_map(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    return {record["capability_id"]: record for record in payload["capabilities"]}


def _option_label(screen: str, value: str) -> str:
    for option_id, label in FLOW_OPTIONS.get(screen, ()):
        if option_id == value:
            return label
    return value or "Chưa chọn"


def _selection_summary(session: dict[str, object]) -> str:
    mode = str(session["mode"])
    selections = session["selections"]
    if mode == "create":
        rows = (
            ("Mục tiêu", _option_label("create_goal", selections.get("goal", ""))),
            ("Định dạng", _option_label("create_format", selections.get("format", ""))),
            ("Phong cách", _option_label("create_style", selections.get("style", ""))),
            ("Âm thanh", _option_label("create_audio", selections.get("audio", ""))),
        )
    else:
        rows = (
            ("Mục tiêu", _option_label("edit_goal", selections.get("goal", ""))),
            ("Nguồn", _option_label("edit_source", selections.get("source", ""))),
            ("Định dạng", _option_label("edit_delivery", selections.get("delivery", ""))),
        )
    return "\n".join(f"• {label}: <b>{html.escape(value)}</b>" for label, value in rows)


def _render_home(payload: dict[str, object], session: dict[str, object]) -> dict[str, object]:
    coverage = capability_coverage(payload)
    text = (
        "🎬 <b>LOCAL VIDEO STUDIO — PREVIEW 27A</b>\n\n"
        "Sản phẩm thử nghiệm riêng cho owner/admin. Chọn đúng quy trình cần xem; "
        "mọi bước chỉ lập kế hoạch local.\n\n"
        f"• Capability local: <b>{len(coverage['local'])}</b>\n"
        f"• QA checks: <b>{len(coverage['qa'])}</b>\n"
        "• Provider/Xu/background job: <b>0</b>"
    )
    rows = _rows(
        (
            ("🎬 Tạo video mới", callback_data("open", "create")),
            ("🎞 Chỉnh footage có sẵn", callback_data("open", "edit")),
        ),
        (
            ("🧰 Kho capability", callback_data("open", "catalog")),
            ("🛡 QA & khóa an toàn", callback_data("open", "safety")),
        ),
        (("✖️ Đóng preview", callback_data("close")),),
    )
    return {"screen": "home", "text": text, "rows": rows}


def _render_option_screen(session: dict[str, object]) -> dict[str, object]:
    screen = str(session["screen"])
    mode = str(session["mode"])
    steps = FLOW_STEPS[mode]
    step_index = next(index for index, (step_screen, _) in enumerate(steps) if step_screen == screen)
    text = (
        f"🎬 <b>{html.escape(SCREEN_TITLES[screen])}</b>\n\n"
        f"Bước {step_index + 1}/{len(steps)} · Chỉ xem trước, chưa xử lý media.\n"
        "Chọn một phương án để đi đúng bước kế tiếp."
    )
    options = FLOW_OPTIONS[screen]
    option_rows = tuple(
        tuple(
            (label, callback_data("pick", screen, option_id))
            for option_id, label in options[index : index + 2]
        )
        for index in range(0, len(options), 2)
    )
    return {"screen": screen, "text": text, "rows": option_rows + _nav_rows(session)}


def _render_review(session: dict[str, object]) -> dict[str, object]:
    mode = str(session["mode"])
    label = "Tạo video mới" if mode == "create" else "Chỉnh footage có sẵn"
    text = (
        f"📋 <b>Xem lại · {label}</b>\n\n"
        f"{_selection_summary(session)}\n\n"
        "Đây là planning preview. Nhấn Rà QA để kiểm điều kiện; không render và không gọi provider."
    )
    rows = _rows((("🛡 Rà QA", callback_data("qa", mode)),)) + _nav_rows(session)
    return {"screen": str(session["screen"]), "text": text, "rows": rows}


def _render_flow_qa(session: dict[str, object], payload: dict[str, object]) -> dict[str, object]:
    coverage = capability_coverage(payload)
    text = (
        "🛡 <b>QA TRƯỚC KHI HOÀN TẤT PREVIEW</b>\n\n"
        f"• Contract QA: <b>{len(coverage['qa'])} checks</b>\n"
        "• Rights/source: bắt buộc\n"
        "• No-fake-success: bắt buộc\n"
        "• Motion/Higgsfield/Suno: disabled\n"
        "• Provider calls: 0 · Xu: 0\n\n"
        "Nút dưới chỉ hoàn tất bản xem trước, không tạo sản phẩm chạy ngầm."
    )
    finish = callback_data("pick", str(session["screen"]), "complete")
    rows = _rows((("✅ Hoàn tất preview", finish),)) + _nav_rows(session)
    return {"screen": str(session["screen"]), "text": text, "rows": rows}


def _render_complete(session: dict[str, object]) -> dict[str, object]:
    text = (
        "✅ <b>PREVIEW_COMPLETE</b>\n\n"
        f"{_selection_summary(session)}\n\n"
        "• Chỉ hoàn tất flow xem trước, không tạo MP4\n"
        "• Provider calls: 0\n"
        "• Xu: 0\n"
        "• Background jobs: 0\n"
        "• Production/public: chưa bật"
    )
    rows = _nav_rows(session, close=True)
    return {"screen": "complete", "text": text, "rows": rows}


def _render_catalog(session: dict[str, object], payload: dict[str, object]) -> dict[str, object]:
    records = _record_map(payload)
    visible, page, total = paginate(LOCAL_RECORD_IDS, int(session["catalog_page"]), CATALOG_PAGE_SIZE)
    text = (
        "🧰 <b>KHO CAPABILITY LOCAL</b>\n\n"
        f"11 pack · 248 capability planning/local · Trang {page + 1}/{total}.\n"
        "Chọn một pack để xem đúng IDs và readiness từ 26I."
    )
    buttons = tuple(
        (str(records[record_id]["display_name_vi"]), callback_data("pack", record_id, 0))
        for record_id in visible
    )
    rows = tuple((button,) for button in buttons)
    page_buttons = _page_row(
        page,
        total,
        callback_data("catalog", max(0, page - 1)),
        callback_data("catalog", min(total - 1, page + 1)),
    )
    if page_buttons:
        rows += (page_buttons,)
    rows += _nav_rows(session)
    return {"screen": "catalog", "text": text, "rows": rows}


def _render_pack(session: dict[str, object], payload: dict[str, object]) -> dict[str, object]:
    records = _record_map(payload)
    record_id = str(session["pack_id"])
    record = records[record_id]
    capability_ids = tuple(record["capability_ids"])
    visible, page, total = paginate(capability_ids, int(session["pack_page"]), PACK_PAGE_SIZE)
    ids_text = "\n".join(f"• <code>{html.escape(capability_id)}</code>" for capability_id in visible)
    text = (
        f"🧰 <b>{html.escape(str(record['display_name_vi']))}</b>\n\n"
        f"• Pack: <code>{html.escape(record_id)}</code>\n"
        f"• Readiness: <code>{html.escape(str(record['highest_readiness']))}</code>\n"
        f"• Tổng IDs: <b>{len(capability_ids)}</b> · Trang {page + 1}/{total}\n\n"
        f"{ids_text}"
    )
    page_buttons = _page_row(
        page,
        total,
        callback_data("pack", record_id, max(0, page - 1)),
        callback_data("pack", record_id, min(total - 1, page + 1)),
    )
    rows = (page_buttons,) if page_buttons else ()
    rows += _nav_rows(session)
    return {"screen": "pack", "text": text, "rows": rows}


def _render_safety(session: dict[str, object], payload: dict[str, object]) -> dict[str, object]:
    records = _record_map(payload)
    paid_lines = "\n".join(
        f"• <code>{record_id}</code> — <b>DISABLED</b> — "
        f"<code>{html.escape(records[record_id]['capability_ids'][0])}</code> · "
        f"readiness <code>{html.escape(str(records[record_id]['highest_readiness']))}</code>"
        for record_id in PAID_RECORD_IDS
    )
    counters = payload["execution_counters"]
    counter_lines = "\n".join(
        f"• <code>{html.escape(str(counter))}</code>: <b>{int(value)}</b>"
        for counter, value in counters.items()
    )
    text = (
        "🛡 <b>QA & KHÓA AN TOÀN</b>\n\n"
        f"{paid_lines}\n\n"
        f"{counter_lines}\n\n"
        "Không có nút paid smoke, generation, download hoặc credential."
    )
    rows = _rows((("🔎 Xem 19 QA checks", callback_data("qa", 0)),)) + _nav_rows(session)
    return {"screen": "safety", "text": text, "rows": rows}


def _render_qa_catalog(session: dict[str, object], payload: dict[str, object]) -> dict[str, object]:
    records = _record_map(payload)
    qa_ids = tuple(records["video_qa"]["capability_ids"])
    visible, page, total = paginate(qa_ids, int(session["pack_page"]), PACK_PAGE_SIZE)
    ids_text = "\n".join(f"• <code>{html.escape(capability_id)}</code>" for capability_id in visible)
    text = (
        "🛡 <b>19 VIDEO QA CHECKS</b>\n\n"
        f"Readiness: <code>{html.escape(str(records['video_qa']['highest_readiness']))}</code>\n"
        f"Trang {page + 1}/{total} · metadata/contract preview, không chạy renderer.\n\n"
        f"{ids_text}"
    )
    page_buttons = _page_row(
        page,
        total,
        callback_data("qa", max(0, page - 1)),
        callback_data("qa", min(total - 1, page + 1)),
    )
    rows = (page_buttons,) if page_buttons else ()
    rows += _nav_rows(session)
    return {"screen": "qa", "text": text, "rows": rows}


def render_failure_view() -> dict[str, object]:
    return {
        "screen": "error",
        "text": (
            "⚠️ <b>Không tải được capability index local</b>\n\n"
            "Preview đã dừng an toàn; không có tác vụ nào được chạy. "
            "Đóng preview rồi kiểm tra lại index 26I."
        ),
        "rows": ((("✖️ Đóng preview", callback_data("close")),),),
    }


def render_view(
    session: object,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    state = normalize_session(session)
    index = validate_capability_index(payload) if payload is not None else load_capability_index()
    screen = str(state["screen"])
    if screen == "home":
        return _render_home(index, state)
    if screen in FLOW_OPTIONS:
        return _render_option_screen(state)
    if screen in {"create_review", "edit_review"}:
        return _render_review(state)
    if screen in {"create_qa", "edit_qa"}:
        return _render_flow_qa(state, index)
    if screen == "complete":
        return _render_complete(state)
    if screen == "catalog":
        return _render_catalog(state, index)
    if screen == "pack":
        return _render_pack(state, index)
    if screen == "safety":
        return _render_safety(state, index)
    if screen == "qa":
        return _render_qa_catalog(state, index)
    raise PreviewDataError("preview_screen_unrenderable")
