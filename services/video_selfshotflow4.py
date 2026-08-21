"""Canonical planning routes for the two Self-shot video products.

This module owns only the public planning state machine.  It does not create
jobs, call providers, render files, charge a wallet, or change Tail9's shared
commercial screens.  Keeping the route contract here prevents the legacy
SelfShot2 and SelfShot3 callback maps from handling the same session.
"""

from __future__ import annotations

from copy import deepcopy
from html import escape
from math import ceil
from typing import Any, Mapping

from . import video_idea_catalog, video_profile_catalog, video_selfshot2, video_selfshot3


FLOW_SS2 = "ss2"
FLOW_SS3 = "ss3"
FLOWS = frozenset({FLOW_SS2, FLOW_SS3})
FLOW_PRODUCT_IDS = {
    FLOW_SS2: video_selfshot2.PRODUCT_ID,
    FLOW_SS3: video_selfshot3.PRODUCT_ID,
}
FLOW_FLAGS = {
    FLOW_SS2: "selfshot2_canonical_flow",
    FLOW_SS3: "selfshot3_canonical_flow",
}
FLOW_SCREEN_KEYS = {
    FLOW_SS2: "selfshot2_screen",
    FLOW_SS3: "selfshot3_screen",
}

SCREENS = frozenset({
    "segment",
    "segment_preview",
    "analysis",
    "mode",
    "subject",
    "subject_multiple",
    "content_source",
    "profiles",
    "idea_groups",
    "ideas",
    "prompt",
    "content_view",
})

# SelfShot2 never exposes the one-take transformation stage. Keeping the
# allowed screen set per product makes a stale or hand-crafted callback
# harmless instead of letting it enter a screen from the other product.
FLOW_SCREENS = {
    FLOW_SS2: frozenset(SCREENS - {"mode"}),
    FLOW_SS3: SCREENS,
}

PARENTS = {
    "segment": "hub",
    "segment_preview": "segment",
    "analysis": "segment",
    "mode": "analysis",
    "subject": "segment",
    "subject_multiple": "subject",
    "content_source": "subject",
    "profiles": "content_source",
    "idea_groups": "content_source",
    "ideas": "idea_groups",
    "prompt": "content_source",
    "content_view": "prompt",
}

SELF_SHOT_2_GOLDEN_FLOW = (
    "source_upload",
    "segment",
    "local_analysis",
    "subject",
    "content_source",
    "content_selection",
    "prompt",
    "addon",
    "review",
    "quality",
    "invoice",
    "confirm",
    "status",
)

SELF_SHOT_3_GOLDEN_FLOW = (
    "source_upload",
    "segment",
    "local_analysis",
    "one_take_mode",
    "subject",
    "content_source",
    "content_selection",
    "prompt",
    "addon",
    "review",
    "quality",
    "invoice",
    "confirm",
    "status",
)

PROMPT_STYLES = (
    ("clear", "Mạch kể rõ và liền cảnh", "Camera chuyển động có động cơ, nhịp kể tự nhiên, kết cảnh trọn ý."),
    ("cinematic", "Điện ảnh giàu cảm xúc", "Bố cục điện ảnh, ánh sáng có chủ đích, chuyển tiếp mềm giữa trạng thái."),
    ("real", "Chân thật và gần gũi", "Chuyển động đời thường, vật liệu chân thật, camera ổn định và dễ tin."),
    ("social", "Nhịp mạng xã hội", "Hook rõ, tiết tấu gọn, điểm nhấn thị giác nhưng không cắt cụt hành động."),
    ("premium", "Cao cấp và tối giản", "Khung hình sạch, chuyển động tiết chế, chủ thể nổi bật và kết thúc tinh tế."),
)

PROMPT_CAMERA_VARIATIONS = (
    "mở bằng toàn cảnh rồi tiến gần chủ thể",
    "mở bằng cận cảnh chi tiết nhận dạng rồi mở rộng bối cảnh",
    "camera đi song song theo đúng hướng chuyển động nguồn",
    "camera giữ trục ổn định và chuyển tiêu điểm theo hành động",
    "camera vòng nhẹ nhưng không phá hướng nhìn và điểm tiếp xúc",
)

PROMPT_RHYTHM_VARIATIONS = (
    "chuyển tiếp theo nhịp hoàn thành hành động",
    "đặt điểm nhấn ở thay đổi môi trường chính",
    "giữ nhịp tự nhiên và dành thời gian cho trạng thái cuối",
    "tăng dần cường độ hình ảnh nhưng không tăng tốc chuyển động nguồn",
    "kết bằng một khung ổn định có thể nối tiếp",
)

PROMPT_CONTINUITY_VARIATIONS = (
    "ưu tiên độ ổn định khuôn mặt",
    "ưu tiên hình dáng và màu sắc đặc trưng",
    "ưu tiên quan hệ người-vật-thú cưng",
    "ưu tiên điểm tiếp xúc và hướng chuyển động",
    "ưu tiên liên tục ánh sáng trên chủ thể",
    "ưu tiên trạng thái đầu-cuối giữa các nhịp",
    "ưu tiên tương thích camera với video nguồn",
)

ANALYSIS_RESULT_FIELDS = (
    "person_tracks",
    "face_tracks",
    "object_tracks",
    "product_tracks",
    "pet_tracks",
    "subject_candidates",
    "relationship_candidates",
    "interaction_graph",
    "motion_summary",
    "camera_summary",
    "track_confidence",
    "track_stability",
    "source_reference_frames",
    "tracking_source",
    "sample_count",
    "analysis_version",
    "analysis_engine",
    "analysis_error",
)

SEGMENT_DEPENDENT_FIELDS = (
    "subject_candidates",
    "relationship_candidates",
    "motion_summary",
    "camera_summary",
    "track_confidence",
    "source_reference_frames",
    "analysis_error",
    "subject_manifest",
    "selected_subject_ids",
    "selected_subject_type",
    "subject_description",
    "identity_lock",
    "relationship_lock",
    "relationship_locks",
    "appearance_lock",
    "motion_lock",
    "preserve_constraints",
    "selfshotflow4_multi_subject_ids",
    "selected_content",
    "selected_profile",
    "content_profile_id",
    "content_profile_name",
    "selected_preset",
    "content_source",
    "content_mode",
    "canonical_content_mode",
    "content_semantic_mode",
    "content_choice",
    "content_description",
    "manual_content",
    "content_revision",
    "idea_group_id",
    "idea_id",
    "idea_preset_id",
    "idea_title",
    "idea_selected_prompt",
    "idea_parent_product",
    "idea_parent_flow",
    "idea_parent_session_id",
    "idea_parent_revision",
    "idea_return_step",
    "selfshotflow4_profile_page",
    "selfshotflow4_idea_page",
    "selfshotflow4_prompt_parent",
    "selfshotflow4_prompt_candidates",
    "selfshotflow4_prompt_generation",
    "selected_prompt",
    "selected_prompt_choice",
    "selected_prompt_text",
    "selected_prompt_revision",
    "selected_video_prompt",
    "prompt_style_note",
    "planning_shot_count",
    "scene_count_deferred_to_quality",
    "scene_plan",
    "scene_change_plan",
    "source_motion_map",
    "per_scene_background",
    "per_scene_content",
    "video_prompts",
    "direction_contract",
    "cinematic_timeline",
    "transformation_content",
    "transformation_stages",
    "transformation_stage_count",
    "environment_transformation",
    "wardrobe_transformation",
    "lighting_transformation",
    "effects_plan",
    "compiled_prompt",
    "continuity_rules",
    "wardrobe",
    "world",
    "selected_effects",
    "plan_status",
    "plan_approved",
    "quality_tier_id",
    "package_id",
    "pricing_snapshot",
    "capability_snapshot",
    "invoice_id",
    "final_confirmed",
    "confirm_token",
    "job_id",
    "delivery_message_id",
    "receipt_state",
    "charge_state",
    "audio_config",
    "logo_config",
    "watermark_config",
    "video_tail9",
)

COMMERCIAL_COMMITMENT_FIELDS = (
    "video_tail9",
    "quality_tier_id",
    "package_id",
    "pricing_snapshot",
    "capability_snapshot",
    "invoice_id",
    "final_confirmed",
    "confirm_token",
    "job_id",
    "delivery_message_id",
    "receipt_state",
    "charge_state",
    "b14_quality_xu",
    "b14_scene_count",
    "b14_scene_count_selected",
    "b14_aspect_ratio",
    "b14_addon_plan",
    "video_tail_engine_route",
    "video_tail_executor_product_type",
    "product_video_logo_material",
)

OPERATION_SCREENS = {
    "c4upload": frozenset({"segment", "analysis", "mode"}),
    "c4segment": frozenset({"segment", "segment_preview", "mode"}),
    "c4mode": frozenset({"mode"}),
    "c4subject": frozenset({"subject"}),
    "c4multi": frozenset({"subject_multiple"}),
    "c4source": frozenset({"content_source"}),
    "c4profile_page": frozenset({"profiles"}),
    "c4profile": frozenset({"profiles"}),
    "c4idea_group": frozenset({"idea_groups"}),
    "c4idea_page": frozenset({"ideas"}),
    "c4idea": frozenset({"ideas"}),
    "c4prompt": frozenset({"prompt"}),
}

FORWARD_SCREENS = {
    "segment": frozenset({"analysis"}),
    "analysis": frozenset({"mode", "subject"}),
    "mode": frozenset({"subject"}),
    "subject": frozenset({"analysis", "subject_multiple", "content_source"}),
    "segment_preview": frozenset({"analysis"}),
    "content_source": frozenset({"profiles", "idea_groups"}),
    "idea_groups": frozenset({"ideas"}),
    "profiles": frozenset({"prompt"}),
    "ideas": frozenset({"prompt"}),
    "prompt": frozenset({"content_view"}),
}


def _safe(value: Any) -> str:
    return str(value or "").strip()


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _display(value: Any) -> str:
    return escape(_safe(value), quote=False)


def _flow(flow: str) -> str:
    value = _safe(flow)
    if value not in FLOWS:
        raise ValueError("selfshotflow4_unknown_flow")
    return value


def flow_label(flow: str) -> str:
    return "Tự quay & đổi cảnh AI" if _flow(flow) == FLOW_SS2 else "Tự quay & biến đổi điện ảnh"


def enabled(flow: str, state: Mapping[str, Any] | None) -> bool:
    return bool(dict(state or {}).get(FLOW_FLAGS[_flow(flow)]))


def current_screen(flow: str, state: Mapping[str, Any] | None) -> str:
    active_flow = _flow(flow)
    value = _safe(dict(state or {}).get(FLOW_SCREEN_KEYS[active_flow]))
    return value if value in FLOW_SCREENS[active_flow] else "segment"


def screen_parent(_flow_name: str, screen: str, state: Mapping[str, Any] | None = None) -> str:
    name = _safe(screen)
    if name == "analysis":
        parent = _safe(dict(state or {}).get("selfshotflow4_analysis_parent"))
        if parent in {"segment", "subject"}:
            return parent
    if name == "prompt":
        parent = _safe(dict(state or {}).get("selfshotflow4_prompt_parent"))
        if parent in {"profiles", "ideas", "content_source"}:
            return parent
    return PARENTS.get(name, "hub")


def callback(flow: str, operation: str, argument: str = "") -> str:
    parts = ["vproduct", _flow(flow), _safe(operation)]
    if _safe(argument):
        parts.append(_safe(argument))
    return "|".join(parts)


def back_callback(flow: str, screen: str, state: Mapping[str, Any] | None = None) -> str:
    if _safe(screen) == "segment":
        return callback(flow, "c4upload")
    parent = screen_parent(flow, screen, state)
    return "vproduct|selfshot_hub" if parent == "hub" else callback(flow, "c4show", parent)


def _nav(flow: str, screen: str, state: Mapping[str, Any] | None = None) -> list[tuple[str, str]]:
    return [("⬅️ Quay lại", back_callback(flow, screen, state)), ("🎬 Menu Video", "menu|main_video")]


def validate_rows(rows: list[list[tuple[str, str]]], *, back_callback: str) -> dict[str, Any]:
    errors: list[str] = []
    callbacks: list[str] = []
    if not rows:
        errors.append("rows_missing")
    for index, row in enumerate(rows):
        if len(row) not in {2, 5}:
            errors.append(f"row_{index}_invalid_width")
        for label, callback_data in row:
            if not _safe(label) or not _safe(callback_data):
                errors.append(f"row_{index}_button_invalid")
            callbacks.append(_safe(callback_data))
    if not rows or len(rows[-1]) != 2:
        errors.append("navigation_row_missing")
    elif rows[-1][0][1] != back_callback or rows[-1][1][1] != "menu|main_video":
        errors.append("navigation_row_invalid")
    if len(callbacks) != len(set(callbacks)):
        errors.append("duplicate_callback")
    return {"ok": not errors, "errors": errors}


def source_ratio(state: Mapping[str, Any] | None) -> str:
    source = dict((state or {}).get("source_asset") or (state or {}).get("source_video") or {})
    width = _as_int(source.get("width"))
    height = _as_int(source.get("height"))
    if width > height:
        return "16:9"
    if width == height and width:
        return "1:1"
    return "9:16"


def _segment_selection(analysis: Mapping[str, Any] | None, start_ms: int = 0, end_ms: int | None = None) -> dict[str, Any]:
    duration_ms = max(0, _as_int(_as_float(dict(analysis or {}).get("duration_seconds")) * 1000))
    start = _as_int(start_ms)
    end = duration_ms if end_ms is None else _as_int(end_ms)
    if duration_ms <= 0 or start < 0 or end <= start or start >= duration_ms or end > duration_ms:
        raise ValueError("selfshotflow4_valid_source_segment_required")
    return {
        "start_ms": start,
        "end_ms": end,
        "duration_ms": end - start,
        "start_seconds": round(start / 1000, 3),
        "end_seconds": round(end / 1000, 3),
        "duration_seconds": round((end - start) / 1000, 3),
        "whole_source": start == 0 and end == duration_ms,
    }


def _clear_segment_dependents(state: dict[str, Any], *, analysis_status: str = "pending") -> None:
    for field in SEGMENT_DEPENDENT_FIELDS:
        state.pop(field, None)
    analysis = dict(state.get("source_analysis") or {})
    for field in ANALYSIS_RESULT_FIELDS:
        analysis.pop(field, None)
    analysis["analysis_status"] = analysis_status
    analysis["tracking_ready"] = False
    state["source_analysis"] = analysis
    state["analysis_status"] = analysis_status
    state.update({
        "provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "generated_files": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    })


def reset_for_new_source(flow: str, state: Mapping[str, Any] | None) -> dict[str, Any]:
    active_flow = _flow(flow)
    previous = dict(state or {})
    fresh = (
        video_selfshot2.initial_draft()
        if active_flow == FLOW_SS2
        else video_selfshot3.initial_draft()
    )
    for field in ("session_id", "revision", "source_revision"):
        if previous.get(field) not in {None, ""}:
            fresh[field] = previous[field]
    fresh.update({
        FLOW_FLAGS[active_flow]: True,
        FLOW_SCREEN_KEYS[active_flow]: "segment",
        "product_id": FLOW_PRODUCT_IDS[active_flow],
        "product_type": FLOW_PRODUCT_IDS[active_flow],
        "engine_route": FLOW_PRODUCT_IDS[active_flow],
        "flow": f"selfshot{active_flow[-1]}",
        "flow_owner": f"selfshot{active_flow[-1]}",
        "owner": f"selfshot{active_flow[-1]}",
        "selfshotflow4_owner": active_flow,
        "selfshotflow4_session_id": _safe(previous.get("session_id")),
        "selfshotflow4_revision": max(1, _as_int(previous.get("revision"), 1)),
        "source_analysis": {
            "analysis_status": "awaiting_segment",
            "analysis_revision": 0,
            "tracking_ready": False,
        },
        "analysis_status": "awaiting_segment",
        "analysis_revision": 0,
        "provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "generated_files": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    })
    return fresh


def _persist_segment(state: dict[str, Any], segment: Mapping[str, Any]) -> None:
    if state.get("source_segment") or any(state.get(field) for field in SEGMENT_DEPENDENT_FIELDS):
        _clear_segment_dependents(state)
    selected = dict(segment or {})
    source = dict(state.get("source_asset") or state.get("source_video") or {})
    analysis = dict(state.get("source_analysis") or {})
    duration = _as_float(analysis.get("duration_seconds") or source.get("duration_seconds"))
    state["source_segment"] = selected
    state["selected_start_seconds"] = _as_float(selected.get("start_seconds"))
    state["selected_end_seconds"] = _as_float(selected.get("end_seconds"))
    state["selected_duration"] = _as_float(selected.get("duration_seconds"))
    state["source_duration"] = duration
    state["source_has_audio"] = bool(
        _as_int((analysis.get("audio_manifest") or {}).get("stream_count"))
        or _as_int(analysis.get("audio_streams"))
        or _as_int(source.get("audio_streams"))
    )
    state["source_ratio"] = _safe(state.get("source_ratio") or source_ratio(state))
    state["source_revision"] = max(1, _as_int(state.get("source_revision"), 1))
    signature = ":".join((
        _safe(state.get("source_video_hash") or analysis.get("source_hash")),
        str(selected.get("start_ms") or 0),
        str(selected.get("end_ms") or 0),
        str(state["source_revision"]),
    ))
    state["analysis_signature"] = signature
    state["analysis_status"] = "pending"
    analysis["analysis_status"] = "pending"
    state["source_analysis"] = analysis


def _persist_derived_scene_count(flow: str, state: dict[str, Any]) -> None:
    if _flow(flow) == FLOW_SS3:
        state.pop("scene_count", None)
        state["scene_count_deferred_to_quality"] = True
        return
    state.pop("scene_count_deferred_to_quality", None)
    selected_duration = max(1.0, _as_float(state.get("selected_duration"), 1.0))
    state["scene_count"] = max(1, min(20, ceil(selected_duration / video_selfshot2.SCENE_SECONDS)))


def _all_subject_candidates(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    analysis = dict(state.get("source_analysis") or {})
    rows: list[dict[str, Any]] = []
    for key, kind in (
        ("person_tracks", "person"),
        ("object_tracks", "object"),
        ("product_tracks", "object"),
        ("pet_tracks", "pet"),
    ):
        for value in list(analysis.get(key) or []):
            item = deepcopy(dict(value or {}))
            item["subject_type"] = _safe(item.get("subject_type") or kind)
            item["subject_id"] = _safe(item.get("subject_id") or item.get("track_id"))
            if item["subject_id"]:
                rows.append(item)
    unique: dict[str, dict[str, Any]] = {}
    for item in rows:
        unique.setdefault(item["subject_id"], item)
    return list(unique.values())


def _subject_button(item: Mapping[str, Any], flow: str, operation: str = "c4subject") -> tuple[str, str]:
    kind = _safe(item.get("subject_type"))
    icon = {"person": "👤", "pet": "🐾", "object": "📦", "product": "📦"}.get(kind, "🎯")
    label = _display(item.get("label") or item.get("description") or "Chủ thể")[:20]
    start = _as_float(item.get("appearance_start_seconds") or item.get("first_seen_seconds"))
    end = _as_float(item.get("appearance_end_seconds") or item.get("last_seen_seconds"))
    timing = f" · {start:g}–{end:g}s" if end > start or end > 0 else ""
    subject_id = _safe(item.get("subject_id") or item.get("track_id"))
    argument = f"track:{subject_id}" if operation == "c4subject" else subject_id
    return (f"{icon} {label}{timing}", callback(flow, operation, argument))


def _subject_rows(flow: str, state: Mapping[str, Any]) -> list[list[tuple[str, str]]]:
    detected = _all_subject_candidates(state)
    buttons = [_subject_button(item, flow) for item in detected]
    if len(detected) >= 2:
        buttons.append(("➕ Giữ nhiều chủ thể", callback(flow, "c4subject", "multiple")))
    elif not detected:
        buttons.extend([
            ("👤 Xác nhận có người", callback(flow, "c4subject", "person")),
            ("📦 Xác nhận có vật", callback(flow, "c4subject", "object")),
        ])
    buttons.extend([
        ("✍️ Tự mô tả", callback(flow, "c4subject", "custom")),
        ("🔎 Xem phân tích", callback(flow, "c4show", "analysis")),
    ])
    if len(buttons) % 2:
        buttons.append(("🎞️ Giữ chuyển động", callback(flow, "c4subject", "motion")))
    return [buttons[index:index + 2] for index in range(0, len(buttons), 2)]


def _subject_multiple_rows(flow: str, state: Mapping[str, Any]) -> list[list[tuple[str, str]]]:
    selected = {_safe(item) for item in state.get("selfshotflow4_multi_subject_ids") or []}
    buttons = []
    for item in _all_subject_candidates(state):
        label, cb = _subject_button(item, flow, "c4multi")
        if _safe(item.get("subject_id")) in selected:
            label = f"✅ {label}"
        buttons.append((label, cb))
    rows = [buttons[index:index + 2] for index in range(0, len(buttons), 2)]
    rows.append([
        ("✅ Xác nhận chủ thể", callback(flow, "c4multi", "done")),
        ("🗑️ Xóa lựa chọn", callback(flow, "c4multi", "clear")),
    ])
    return rows


def content_profiles() -> list[dict[str, Any]]:
    return [deepcopy(dict(item)) for item in video_profile_catalog.PROFILE_SEEDS]


def _profile_catalog(_flow_name: str = "") -> list[dict[str, Any]]:
    return content_profiles()


def idea_groups() -> list[dict[str, Any]]:
    return [
        {
            "category_id": _safe(item.get("category_key")),
            "icon": _safe(item.get("icon")),
            "title": _safe(item.get("public_name")),
            "short_title": _safe(item.get("short_button_name") or item.get("public_name")),
            "description": _safe(item.get("description")),
        }
        for item in video_idea_catalog.dynamic_category_seeds()
    ]


def ideas_for_group(category_id: str) -> list[dict[str, Any]]:
    key = _safe(category_id)
    if key not in {item["category_id"] for item in idea_groups()}:
        return []
    return [deepcopy(dict(item)) for item in video_idea_catalog.IDEAS if _safe(item.get("category")) == key]


def _idea_catalog(flow: str) -> list[dict[str, Any]]:
    del flow
    return [deepcopy(dict(item)) for item in video_idea_catalog.IDEAS]


def _idea_group_rows(flow: str) -> list[list[tuple[str, str]]]:
    buttons = [
        (
            f"{item['icon']} {_display(item['short_title'])}".strip(),
            callback(flow, "c4idea_group", item["category_id"]),
        )
        for item in idea_groups()
    ]
    return [buttons[index:index + 2] for index in range(0, len(buttons), 2)]


def _page_rows(flow: str, state: Mapping[str, Any], *, kind: str) -> list[list[tuple[str, str]]]:
    page_key = f"selfshotflow4_{kind}_page"
    page = max(1, _as_int(state.get(page_key), 1))
    if kind == "profile":
        catalog = _profile_catalog(flow)
        selected = _safe(state.get("content_profile_id") or state.get("selected_profile"))
        start = (page - 1) * 8
        chunk = catalog[start:start + 8]
        rows = []
        for offset in range(0, len(chunk), 2):
            pair = []
            for local_index, item in enumerate(chunk[offset:offset + 2], start + offset):
                item_id = _safe(item.get("profile_key"))
                prefix = "✅ " if item_id == selected else ""
                label = f"{_safe(item.get('icon'))} {_display(item.get('short_name') or item.get('public_name'))}".strip()
                pair.append((f"{prefix}{label}", callback(flow, "c4profile", item_id)))
            rows.append(pair)
    else:
        catalog = ideas_for_group(_safe(state.get("idea_group_id")))
        selected = dict(state.get("selected_preset") or {})
        selected_id = _safe(selected.get("idea_id") or selected.get("id") or selected.get("preset_id"))
        start = (page - 1) * 6
        chunk = catalog[start:start + 6]
        rows = []
        for offset in range(0, len(chunk), 2):
            pair = []
            for local_index, item in enumerate(chunk[offset:offset + 2], start + offset):
                item_id = _safe(item.get("idea_id") or item.get("id") or item.get("preset_id"))
                prefix = "✅ " if item_id and item_id == selected_id else ""
                pair.append((f"{prefix}💡 {_display(item.get('title'))[:27]}", callback(flow, "c4idea", item_id)))
            rows.append(pair)
        if rows and len(rows[-1]) == 1:
            rows[-1].append(("💡 Nhóm khác", callback(flow, "c4show", "idea_groups")))
    page_size = 8 if kind == "profile" else 6
    total = max(1, (len(catalog) + page_size - 1) // page_size)
    if total > 1:
        previous_page = total if page <= 1 else page - 1
        next_page = 1 if page >= total else page + 1
        rows.append([
            ("⬅️ Trang trước", callback(flow, f"c4{kind}_page", str(previous_page))),
            ("➡️ Trang sau", callback(flow, f"c4{kind}_page", str(next_page))),
        ])
    return rows


def _content_summary(state: Mapping[str, Any]) -> str:
    content = dict(state.get("selected_content") or {})
    if content:
        return _safe(content.get("summary") or content.get("title"))
    preset = dict(state.get("selected_preset") or {})
    return _safe(preset.get("title") or preset.get("summary")) or "Chưa chọn"


def normalize_subject_locks(flow: str, state: Mapping[str, Any] | None) -> dict[str, Any]:
    active_flow = _flow(flow)
    current = deepcopy(dict(state or {}))
    analysis = dict(current.get("source_analysis") or {})
    manifest = dict(current.get("subject_manifest") or {})
    subjects = [deepcopy(dict(item)) for item in list(manifest.get("subjects") or []) if isinstance(item, Mapping)]
    selected_ids = [
        _safe(value)
        for value in (manifest.get("selected_ids") or manifest.get("subject_ids") or [])
        if _safe(value)
    ]
    if not selected_ids:
        selected_ids = [_safe(item.get("subject_id")) for item in subjects if _safe(item.get("subject_id"))]
    selected_types = {_safe(item.get("subject_type")) for item in subjects if _safe(item.get("subject_type"))}
    selection_type = _safe(manifest.get("selection_type") or manifest.get("selection_mode"))
    if len(selected_ids) > 1:
        selection_type = "multiple"
    elif not selection_type and selected_types:
        selection_type = next(iter(selected_types))
    description = _safe(manifest.get("description")) or ", ".join(
        _safe(item.get("description") or item.get("label")) for item in subjects
    )
    relationship_rows = [
        deepcopy(dict(item))
        for item in list(manifest.get("interaction_graph") or current.get("relationship_locks") or analysis.get("relationship_candidates") or analysis.get("interaction_graph") or [])
        if isinstance(item, Mapping)
    ]
    manifest.update({
        "selection_type": selection_type or "custom",
        "selection_mode": selection_type or "custom",
        "subjects": subjects,
        "selected_ids": selected_ids,
        "subject_ids": selected_ids,
        "person_subject_ids": [_safe(item.get("subject_id")) for item in subjects if _safe(item.get("subject_type")) == "person"],
        "object_subject_ids": [_safe(item.get("subject_id")) for item in subjects if _safe(item.get("subject_type")) in {"object", "product"}],
        "pet_subject_ids": [_safe(item.get("subject_id")) for item in subjects if _safe(item.get("subject_type")) == "pet"],
        "interaction_graph": relationship_rows,
        "description": description,
        "stable_ids": bool(selected_ids),
        "source_bound": bool(_safe(current.get("source_video_id") or analysis.get("source_hash"))),
        "confirmed": True,
    })
    current["subject_manifest"] = manifest
    current["selected_subject_ids"] = selected_ids
    current["selected_subject_type"] = selection_type or "custom"
    current["subject_description"] = description
    current["identity_lock"] = {
        "enabled": bool(selected_ids or description),
        "subject_ids": selected_ids,
        "preserve": ["face", "body_shape", "primary_colors", "distinctive_objects", "pet_identity"],
        "source_bound": bool(manifest.get("source_bound")),
    }
    current["relationship_lock"] = {
        "enabled": True,
        "relationships": relationship_rows,
        "rule": "preserve detected person-object-pet contact, spacing and relative position",
    }
    current["relationship_locks"] = relationship_rows
    current["appearance_lock"] = {
        "enabled": True,
        "preserve": ["face", "body_proportions", "primary_colors", "distinctive_marks"],
    }
    current["motion_lock"] = {
        "enabled": True,
        "summary": _safe(analysis.get("motion_summary") or ", ".join(analysis.get("main_actions") or [])),
        "camera": _safe(analysis.get("camera_summary") or analysis.get("camera_motion")),
        "rule": "preserve source direction, timing and contact points",
    }
    current["source_reference_frames"] = deepcopy(list(analysis.get("source_reference_frames") or []))
    if active_flow == FLOW_SS2:
        current["preserve_constraints"] = video_selfshot2.default_preserve_constraints(manifest)
    else:
        current.setdefault("layer_rules", video_selfshot3.default_layer_rules())
    return current


def prompt_candidates(flow: str, state: Mapping[str, Any]) -> list[dict[str, str]]:
    active_flow = _flow(flow)
    content = _content_summary(state)
    analysis = dict(state.get("source_analysis") or {})
    ratio = _safe(state.get("source_ratio") or source_ratio(state))
    segment = dict(state.get("source_segment") or {})
    seconds = max(
        1,
        _as_int((_as_int(segment.get("end_ms")) - _as_int(segment.get("start_ms"))) / 1000)
        or _as_int(analysis.get("duration_seconds"), 1),
    )
    subject = _safe(state.get("subject_description")) or ", ".join(
        _safe(item.get("description") or item.get("label"))
        for item in (state.get("subject_manifest") or {}).get("subjects") or []
    ) or "chủ thể đã chọn"
    if active_flow == FLOW_SS2:
        lock_clause = (
            "Giữ nguyên chủ thể và nhận dạng; giữ nguyên quan hệ người-vật-thú cưng; bám chuyển động nguồn. "
            "Thực hiện đổi cảnh theo nội dung đã chọn, giữ continuity đầu-cuối và camera compatibility; "
            "không đổi người, không làm mất vật hoặc thú cưng."
        )
    else:
        lock_clause = (
            "Giữ nguyên chủ thể và chuyển động nguồn trong một cú máy. Thực hiện biến đổi điện ảnh theo timeline: "
            "trang phục, môi trường, ánh sáng và hiệu ứng thay đổi dần; giữ continuity khuôn mặt, vóc dáng và quan hệ; "
            "không cắt sang clip không liên quan."
        )
    return [
        {
            "id": style_id,
            "title": title,
            "text": (
                f"{title}. {summary} {lock_clause} Chủ thể: {subject}. Nội dung: {content}. "
                f"Khung {ratio}, đoạn nguồn khoảng {seconds}s."
            ),
            "product_type": FLOW_PRODUCT_IDS[active_flow],
        }
        for style_id, title, summary in PROMPT_STYLES
    ]


def _prompt_candidates(flow: str, state: Mapping[str, Any]) -> list[dict[str, str]]:
    return prompt_candidates(flow, state)


def _canonical_content_contract(state: dict[str, Any]) -> None:
    raw_source = _safe(state.get("content_source"))
    source = {
        "profile": "content_profiles",
        "profiles": "content_profiles",
        "content_profiles": "content_profiles",
        "idea": "idea_catalog",
        "ideas": "idea_catalog",
        "idea_catalog": "idea_catalog",
        "custom": "manual",
        "manual": "manual",
    }.get(raw_source, raw_source or "manual")
    content = dict(state.get("selected_content") or {})
    state["content_source"] = source
    state["content_mode"] = "manual" if source == "manual" else "suggestions"
    state["canonical_content_mode"] = state["content_mode"]
    state["content_semantic_mode"] = source
    state["content_choice"] = {
        "id": _safe(content.get("id") or state.get("content_profile_id") or state.get("idea_id") or "manual"),
        "title": _safe(content.get("title") or "Nội dung đã chọn"),
        "concept": _safe(content.get("summary") or content.get("description")),
    }
    state["content_revision"] = max(1, _as_int(state.get("content_revision"), 1))
    if source == "manual":
        state["manual_content"] = _safe(content.get("summary") or content.get("title"))


def compile_selfshot2_content(state: Mapping[str, Any]) -> dict[str, Any]:
    current = normalize_subject_locks(FLOW_SS2, state)
    analysis = dict(current.get("source_analysis") or {})
    manifest = dict(current.get("subject_manifest") or {})
    constraints = dict(current.get("preserve_constraints") or video_selfshot2.default_preserve_constraints(manifest))
    content = dict(current.get("selected_content") or {})
    if not content:
        preset = dict(current.get("selected_preset") or {})
        content = {"id": _safe(preset.get("id")), "title": _safe(preset.get("title")), "summary": _safe(preset.get("summary"))}
        current["selected_content"] = content
    current["preserve_constraints"] = constraints
    selected_segment = dict(current.get("source_segment") or {})
    segment_duration = float(_as_int(selected_segment.get("duration_ms")) / 1000)
    requested_scene_count = _as_int(current.get("scene_count"))
    current["scene_count"] = max(1, min(20, requested_scene_count or ceil(max(1.0, segment_duration) / video_selfshot2.SCENE_SECONDS)))
    current.pop("scene_count_deferred_to_quality", None)
    current["aspect_ratio"] = _safe(current.get("source_ratio") or source_ratio(current))
    current["direction_contract"] = video_selfshot2.direction_contract("new_story")
    plan_analysis = dict(analysis)
    if segment_duration > 0:
        plan_analysis["duration_seconds"] = segment_duration
    current["scene_plan"] = video_selfshot2.build_scene_plan(
        analysis=plan_analysis,
        subject_manifest=manifest,
        constraints=constraints,
        scene_count=int(current["scene_count"]),
        content=content,
        direction=dict(current["direction_contract"]),
    )
    offset = float(_as_int(selected_segment.get("start_ms")) / 1000)
    if offset or segment_duration:
        for scene in current["scene_plan"]:
            scene["source_segment_start"] = round(float(scene.get("source_segment_start") or 0) + offset, 3)
            scene["source_segment_end"] = round(float(scene.get("source_segment_end") or 0) + offset, 3)
            scene["source_segment_selected"] = True
    current["video_prompts"] = video_selfshot2.compile_scene_prompts(
        current["scene_plan"],
        subject_manifest=manifest,
        content=content,
        direction=dict(current["direction_contract"]),
    )
    prompt_by_scene = {int(item.get("scene_index") or 0): dict(item) for item in current["video_prompts"]}
    current["scene_change_plan"] = deepcopy(current["scene_plan"])
    current["source_motion_map"] = {
        "summary": _safe(analysis.get("motion_summary") or ", ".join(analysis.get("main_actions") or [])),
        "camera": _safe(analysis.get("camera_summary") or analysis.get("camera_motion")),
        "segments": [
            {
                "scene_index": item.get("scene_index"),
                "start_seconds": item.get("source_segment_start"),
                "end_seconds": item.get("source_segment_end"),
            }
            for item in current["scene_plan"]
        ],
    }
    current["per_scene_background"] = [
        {"scene_index": item.get("scene_index"), "from": item.get("environment_before"), "to": item.get("environment_after")}
        for item in current["scene_plan"]
    ]
    current["per_scene_content"] = [
        {
            "scene_index": item.get("scene_index"),
            "title": f"Cảnh {item.get('scene_index')}: {_safe(content.get('title'))}",
            "summary": _safe(content.get("summary") or content.get("title")),
            "source_start_seconds": item.get("source_segment_start"),
            "source_end_seconds": item.get("source_segment_end"),
            "background": item.get("environment_after"),
            "prompt": _safe(prompt_by_scene.get(int(item.get("scene_index") or 0), {}).get("prompt")),
        }
        for item in current["scene_plan"]
    ]
    current["continuity_rules"] = [
        "Giữ cùng khuôn mặt, vóc dáng, màu sắc và vật/thú cưng đã chọn.",
        "Giữ hướng chuyển động, điểm tiếp xúc và trạng thái cuối-đầu giữa các cảnh.",
        "Camera mới phải tương thích với camera và chuyển động nguồn.",
    ]
    _canonical_content_contract(current)
    current.update({
        "product_type": video_selfshot2.PRODUCT_ID,
        "product_id": video_selfshot2.PRODUCT_ID,
        "engine_route": video_selfshot2.PRODUCT_ID,
        "flow_owner": "selfshot2",
        "owner": "selfshot2",
        "plan_status": "ready",
        "plan_approved": True,
    })
    return current


def compile_selfshot3_content(state: Mapping[str, Any]) -> dict[str, Any]:
    current = normalize_subject_locks(FLOW_SS3, state)
    segment = dict(current.get("source_segment") or {})
    if _as_int(segment.get("end_ms")) <= _as_int(segment.get("start_ms")):
        segment = _segment_selection(dict(current.get("source_analysis") or {}))
        current["source_segment"] = segment
    preset = dict(current.get("selected_preset") or {})
    if not preset:
        content = dict(current.get("selected_content") or {})
        preset = {
            "preset_id": _safe(content.get("id") or "custom"),
            "title": _safe(content.get("title") or "Biến đổi điện ảnh"),
            "summary": _safe(content.get("summary")),
        }
        current["selected_preset"] = preset
    current["transformation_stage_count"] = 4
    current.setdefault("layer_rules", video_selfshot3.default_layer_rules())
    current.setdefault("relationship_locks", [])
    current.setdefault("wardrobe", "biến đổi dần theo bốn nhịp")
    current.setdefault("world", _safe(preset.get("summary") or preset.get("title")))
    current.setdefault("selected_effects", ["ánh sáng điện ảnh", "hiệu ứng chuyển hóa"])
    current["transformation_content"] = _safe(current.get("transformation_content") or preset.get("summary") or preset.get("title"))
    current["transformation_stages"] = video_selfshot3.build_timeline(
        segment=segment,
        stage_count=4,
        preset=preset,
        wardrobe=_safe(current.get("wardrobe")),
        world=_safe(current.get("world")),
        effects=list(current.get("selected_effects") or []),
    )
    current["compiled_prompt"] = video_selfshot3.compile_prompt(
        mode=video_selfshot3.MODE_ONE_TAKE,
        subject_manifest=dict(current.get("subject_manifest") or {}),
        relationship_locks=list(current.get("relationship_locks") or []),
        layer_rules=dict(current.get("layer_rules") or {}),
        segment=segment,
        stages=list(current["transformation_stages"]),
        wardrobe=_safe(current.get("wardrobe")),
        world=_safe(current.get("world")),
        effects=list(current.get("selected_effects") or []),
        content=_safe(current.get("transformation_content")),
    )
    current["video_prompts"] = list(dict(current["compiled_prompt"]).get("stage_prompts") or [])
    current["scene_plan"] = [
        {
            "scene_index": 1,
            "title": "Biến đổi liên tục một cú máy",
            "duration": max(1, _as_int((_as_int(segment.get("end_ms")) - _as_int(segment.get("start_ms"))) / 1000)),
            "stages": deepcopy(current["transformation_stages"]),
        }
    ]
    current.pop("scene_count", None)
    current["planning_shot_count"] = 1
    current["scene_count_deferred_to_quality"] = True
    current["aspect_ratio"] = _safe(current.get("source_ratio") or source_ratio(current))
    current["cinematic_timeline"] = deepcopy(current["transformation_stages"])
    current["environment_transformation"] = {
        "from": "môi trường nguồn",
        "to": _safe(current.get("world")),
        "stages": deepcopy(current["transformation_stages"]),
    }
    current["wardrobe_transformation"] = {
        "rule": _safe(current.get("wardrobe")),
        "preserve_body_and_identity": True,
    }
    current["lighting_transformation"] = {
        "rule": "Ánh sáng thay đổi theo từng giai đoạn nhưng giữ liên tục trên khuôn mặt và cơ thể.",
        "stages": [dict(item).get("lighting") or dict(item).get("light") or "cinematic progression" for item in current["transformation_stages"]],
    }
    current["effects_plan"] = {
        "effects": list(current.get("selected_effects") or []),
        "timeline_bound": True,
    }
    stage_contents = []
    for index, item in enumerate(current["transformation_stages"], 1):
        raw_prompt = current["video_prompts"][index - 1] if index <= len(current["video_prompts"]) else ""
        prompt_text = _safe(raw_prompt.get("prompt")) if isinstance(raw_prompt, Mapping) else _safe(raw_prompt)
        stage_contents.append({
            "scene_index": index,
            "title": _safe(item.get("title") or f"Giai đoạn {index}"),
            "summary": _safe(item.get("description") or item.get("world") or current.get("transformation_content")),
            "timeline": deepcopy(dict(item)),
            "prompt": prompt_text,
        })
    current["per_scene_content"] = stage_contents
    current["continuity_rules"] = [
        "Giữ khuôn mặt, vóc dáng, chuyển động và quan hệ nguồn qua bốn giai đoạn.",
        "Trang phục, môi trường, ánh sáng và hiệu ứng chỉ biến đổi dần theo timeline.",
        "Không cắt sang clip khác và không thay thế chủ thể.",
    ]
    _canonical_content_contract(current)
    current.update({
        "product_type": video_selfshot3.PRODUCT_ID,
        "product_id": video_selfshot3.PRODUCT_ID,
        "engine_route": video_selfshot3.PRODUCT_ID,
        "flow_owner": "selfshot3",
        "owner": "selfshot3",
        "plan_status": "ready",
        "plan_approved": True,
    })
    return current


def _prepare_tail(flow: str, state: dict[str, Any]) -> None:
    for field in COMMERCIAL_COMMITMENT_FIELDS:
        state.pop(field, None)
    compiled = compile_selfshot2_content(state) if flow == FLOW_SS2 else compile_selfshot3_content(state)
    state.clear()
    state.update(compiled)
    raw_selected = state.get("selected_prompt")
    if isinstance(raw_selected, Mapping):
        selected = dict(raw_selected)
    elif isinstance(state.get("selected_prompt_choice"), Mapping):
        selected = dict(state.get("selected_prompt_choice") or {})
    else:
        selected = {"id": "saved", "title": "Câu lệnh đã chọn", "text": _safe(raw_selected)}
    note = str(selected.get("text") or "")
    if note.strip():
        state["selected_prompt_choice"] = selected
        state["selected_prompt"] = note
        state["selected_prompt_text"] = note
        state["idea_selected_prompt"] = note if state.get("content_source") == "idea_catalog" else ""
        state["selected_prompt_revision"] = max(1, _as_int(state.get("selected_prompt_revision"), 1))
        state["selected_video_prompt"] = note
        if flow == FLOW_SS2:
            for item in list(state.get("video_prompts") or []):
                item["prompt"] = f"{_safe(item.get('prompt'))} Style: {note}"
        else:
            state["prompt_style_note"] = note
    state["content_revision"] = max(1, _as_int(state.get("content_revision"), 1))
    state["plan_status"] = "ready"
    state["plan_approved"] = True
    state.update({
        "provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "generated_files": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    })


def review_text(flow: str, state: Mapping[str, Any] | None) -> str:
    active_flow = _flow(flow)
    data = dict(state or {})
    segment = dict(data.get("source_segment") or {})
    start = _as_float(segment.get("start_seconds") or data.get("selected_start_seconds"))
    end = _as_float(segment.get("end_seconds") or data.get("selected_end_seconds"))
    subject = _display(data.get("subject_description") or "Chủ thể đã chọn")
    content = _display(_content_summary(data))
    identity = "Đã khóa" if (data.get("identity_lock") or {}).get("enabled") else "Chưa khóa"
    relationship = "Đã khóa" if (data.get("relationship_lock") or {}).get("enabled") else "Chưa khóa"
    if active_flow == FLOW_SS2:
        lines = [
            "🎬 <b>Xem lại — Tự quay và đổi cảnh AI</b>",
            f"• Đoạn nguồn: <b>{start:g}–{end:g} giây</b>",
            f"• Chủ thể giữ lại: <b>{subject}</b>",
            f"• Nội dung: <b>{content}</b>",
            f"• Số cảnh: <b>{max(1, _as_int(data.get('scene_count'), 1))}</b>",
            f"• Tỉ lệ: <b>{_display(data.get('aspect_ratio') or data.get('source_ratio') or '9:16')}</b>",
            "• Kiểu đổi cảnh: <b>Đổi bối cảnh theo chuyển động nguồn</b>",
            f"• Giữ nhận diện: <b>{identity}</b>",
            f"• Giữ quan hệ: <b>{relationship}</b>",
        ]
    else:
        lines = [
            "🎬 <b>Xem lại — Biến đổi điện ảnh</b>",
            f"• Đoạn nguồn: <b>{start:g}–{end:g} giây</b>",
            f"• Chủ thể giữ lại: <b>{subject}</b>",
            f"• Nội dung: <b>{content}</b>",
            f"• Mạch biến đổi: <b>{len(list(data.get('cinematic_timeline') or data.get('transformation_stages') or []))} giai đoạn</b>",
            f"• Môi trường: <b>{_display(data.get('world') or 'Biến đổi theo lựa chọn')}</b>",
            f"• Trang phục: <b>{_display(data.get('wardrobe') or 'Giữ nguyên')}</b>",
            f"• Hiệu ứng: <b>{_display(', '.join(data.get('selected_effects') or []) or 'Theo mạch biến đổi')}</b>",
            f"• Giữ nhận diện / quan hệ: <b>{identity} / {relationship}</b>",
        ]
    selected_prompt = str(data.get("selected_prompt_text") or data.get("selected_prompt") or "")
    if selected_prompt.strip():
        lines.extend(["", "<b>Câu lệnh đã chọn</b>", _display(selected_prompt)])
    lines.extend(["", "Tiếp tục tới Add-on, Rà soát, Chất lượng, Hóa đơn, Xác nhận và Bảng trạng thái."])
    return "\n".join(lines)


def screen_model(flow: str, screen: str, state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    active_flow = _flow(flow)
    name = _safe(screen) if _safe(screen) in FLOW_SCREENS[active_flow] else current_screen(active_flow, state)
    data = dict(state or {})
    source = dict(data.get("source_asset") or data.get("source_video") or {})
    analysis = dict(data.get("source_analysis") or {})
    lines: list[str]
    rows: list[list[tuple[str, str]]]

    if name == "segment":
        segment = dict(data.get("source_segment") or {})
        duration = _as_int(analysis.get("duration_seconds") or source.get("duration_seconds"))
        selected = f"{_as_int(segment.get('start_ms')) // 1000}–{_as_int(segment.get('end_ms')) // 1000} giây" if segment else "Chưa chọn"
        lines = [
            f"🎬 <b>Chọn đoạn video nguồn</b>",
            f"Sản phẩm: <b>{flow_label(active_flow)}</b>",
            f"Video nguồn: khoảng {duration} giây · đoạn đang dùng: <b>{selected}</b>",
            "Chọn toàn bộ hoặc một đoạn liên tục để phân tích chủ thể và chuyển động nguồn.",
        ]
        rows = [
            [("🎬 Dùng toàn bộ", callback(active_flow, "c4segment", "whole")), ("✂️ Chọn đoạn", callback(active_flow, "c4segment", "custom"))],
            [("👁️ Xem đoạn đã chọn", callback(active_flow, "c4segment", "preview")), ("🔄 Chọn lại", callback(active_flow, "c4segment", "reset"))],
        ]
    elif name == "segment_preview":
        segment = dict(data.get("source_segment") or {})
        start = _as_float(segment.get("start_seconds"))
        end = _as_float(segment.get("end_seconds"))
        duration = _as_float(segment.get("duration_seconds"))
        lines = [
            "▶️ <b>Đoạn video đã chọn</b>",
            f"• Bắt đầu: <b>{start:g} giây</b>",
            f"• Kết thúc: <b>{end:g} giây</b>",
            f"• Thời lượng: <b>{duration:g} giây</b>",
            "Đoạn này sẽ được dùng nguyên vẹn cho phân tích chủ thể và chuyển động.",
        ]
        rows = [[
            ("➡️ Phân tích chủ thể", callback(active_flow, "c4show", "analysis")),
            ("✂️ Chọn lại đoạn", callback(active_flow, "c4segment", "reset")),
        ]]
    elif name == "analysis":
        status = _safe(data.get("analysis_status") or analysis.get("analysis_status") or "awaiting_segment")
        counts = {
            "person": len(list(analysis.get("person_tracks") or [])),
            "object": len(list(analysis.get("object_tracks") or [])) + len(list(analysis.get("product_tracks") or [])),
            "pet": len(list(analysis.get("pet_tracks") or [])),
        }
        status_copy = {
            "pending": "Đang chuẩn bị phân tích đoạn đã chọn",
            "running": "Đang phân tích cục bộ",
            "ready": "Đã phân tích xong",
            "ready_no_tracks": "Đã phân tích xong, chưa có chủ thể đủ tin cậy",
            "failed": "Chưa hoàn tất phân tích; vẫn có thể tự xác nhận chủ thể",
        }.get(status, "Chờ chọn đoạn video")
        lines = [
            "🔎 <b>Phân tích video nguồn</b>",
            f"Trạng thái: <b>{status_copy}</b>",
            f"Đoạn đã chọn: <b>{_safe(data.get('source_segment') and 'Đã có' or 'Chưa có')}</b> · tỉ lệ nguồn: <b>{source_ratio(data)}</b>",
            f"Chủ thể tìm thấy: <b>{counts['person']} người · {counts['object']} vật · {counts['pet']} thú cưng</b>.",
            f"Chuyển động: <b>{_display(analysis.get('motion_summary') or 'Chưa phân loại')}</b>",
            f"Camera: <b>{_display(analysis.get('camera_summary') or analysis.get('camera_motion') or 'Chưa phân loại')}</b>",
        ]
        if status in {"ready_no_tracks", "failed"}:
            lines.append("Chưa có chủ thể đủ tin cậy. Anh/chị vẫn có thể tự mô tả hoặc xác nhận chủ thể trong chính video đã gửi.")
        rows = [[
            (
                "✨ Biến đổi liên tục một cú máy" if active_flow == FLOW_SS3 else "➡️ Chọn chủ thể",
                callback(active_flow, "c4show", "mode" if active_flow == FLOW_SS3 else "subject"),
            ),
            ("📎 Gửi video khác", callback(active_flow, "c4upload")),
        ]]
    elif name == "mode":
        lines = [
            "✨ <b>Biến đổi liên tục một cú máy</b>",
            "Giữ khuôn mặt, vóc dáng và chuyển động nguồn liên tục. Trang phục, bối cảnh, ánh sáng và hiệu ứng sẽ thay đổi dần qua bốn giai đoạn, không cắt sang clip không liên quan.",
            "Bước tiếp theo là xác nhận chủ thể cần giữ.",
        ]
        rows = [[
            ("✅ Biến đổi liên tục một cú máy", callback(active_flow, "c4mode", "one_take")),
            ("📎 Gửi video khác", callback(active_flow, "c4upload")),
        ]]
    elif name == "subject":
        manifest = dict(data.get("subject_manifest") or {})
        selected = ", ".join(_display(item.get("description") or item.get("label")) for item in manifest.get("subjects") or []) or "Chưa chọn"
        lines = [
            "🎯 <b>Chọn chủ thể cần giữ</b>",
            f"Hiện tại: <b>{selected}</b>",
            "Chọn người, vật hoặc thú cưng đã tìm thấy. Có thể giữ nhiều chủ thể hoặc tự mô tả khi video chưa xác định được chủ thể đủ tin cậy.",
        ]
        rows = _subject_rows(active_flow, data)
    elif name == "subject_multiple":
        selected_ids = list(data.get("selfshotflow4_multi_subject_ids") or [])
        lines = [
            "➕ <b>Giữ nhiều chủ thể</b>",
            f"Đã chọn: <b>{len(selected_ids)} chủ thể</b>",
            "Chọn ít nhất hai chủ thể. Hệ thống sẽ khóa cả nhận dạng, khoảng cách và quan hệ giữa các chủ thể.",
        ]
        rows = _subject_multiple_rows(active_flow, data)
    elif name == "content_source":
        lines = [
            "📝 <b>Chọn nguồn nội dung</b>",
            "Chọn một nguồn nội dung cho đúng video nguồn. Ba đường này độc lập; Kho Ý tưởng đã có cấu trúc sẵn, còn 32 loại nội dung và Tự nhập sẽ tạo câu lệnh từ lựa chọn của anh/chị.",
        ]
        rows = [[
            ("🗂️ 32 loại nội dung", callback(active_flow, "c4source", "profiles")),
            ("💡 Kho Ý tưởng video", callback(active_flow, "c4source", "ideas")),
        ], [
            ("✍️ Tự nhập nội dung", callback(active_flow, "c4source", "custom")),
            ("👁️ Xem phân tích", callback(active_flow, "c4show", "analysis")),
        ]]
    elif name == "profiles":
        page = max(1, _as_int(data.get("selfshotflow4_profile_page"), 1))
        lines = [
            "🎯 <b>Chọn loại nội dung</b>",
            f"Trang {page}/4 trong 32 loại nội dung. Chọn một loại để tạo đúng 5 câu lệnh dựa trên video nguồn.",
        ]
        rows = _page_rows(active_flow, data, kind="profile")
    elif name == "idea_groups":
        lines = [
            "💡 <b>Chọn nhóm ý tưởng</b>",
            "Kho hiện có 16 nhóm và 72 ý tưởng. Chọn một nhóm để xem đúng các preset có sẵn.",
        ]
        rows = _idea_group_rows(active_flow)
    elif name == "ideas":
        page = max(1, _as_int(data.get("selfshotflow4_idea_page"), 1))
        group_id = _safe(data.get("idea_group_id"))
        group = next((item for item in idea_groups() if item["category_id"] == group_id), {})
        total = max(1, ceil(len(ideas_for_group(group_id)) / 6))
        lines = [
            "💡 <b>Kho Ý tưởng video</b>",
            f"Nhóm: <b>{_display(group.get('title') or group_id)}</b> · Trang {page}/{total}.",
            "Mỗi ý tưởng đã có chủ đề, nhịp và hướng hình ảnh; sau khi chọn sẽ mở ngay 5 câu lệnh phù hợp với video nguồn.",
        ]
        rows = _page_rows(active_flow, data, kind="idea")
    elif name == "prompt":
        candidates = list(data.get("selfshotflow4_prompt_candidates") or _prompt_candidates(active_flow, data))
        lines = [
            "🎬 <b>Chọn câu lệnh video</b>",
            f"Sản phẩm: <b>{flow_label(active_flow)}</b> · Nội dung: <b>{_display(_content_summary(data))}</b>",
            "Mỗi câu lệnh giữ video nguồn liên tục, chỉ đổi cách kể, máy quay và nhịp chuyển tiếp.",
        ]
        lines.extend(f"{index}. <b>{_display(item.get('title'))}</b>\n{_display(item.get('text'))}" for index, item in enumerate(candidates, 1))
        rows = [
            [(str(index), callback(active_flow, "c4prompt", str(index))) for index in range(1, 6)],
            [("🔄 Đổi 5 câu lệnh", callback(active_flow, "c4prompt", "refresh")), ("✍️ Tự viết câu lệnh", callback(active_flow, "c4prompt", "edit"))],
            [("⏭️ Bỏ qua", callback(active_flow, "c4prompt", "skip")), ("👁️ Xem nội dung", callback(active_flow, "c4prompt", "content"))],
        ]
    else:
        lines = [
            "📋 <b>Nội dung đã chọn</b>",
            f"Nguồn nội dung: <b>{_display(_content_summary(data))}</b>",
            "Quay lại để chọn hoặc sửa câu lệnh trước khi tiếp tục.",
        ]
        rows = []

    rows.append(_nav(active_flow, name, data))
    return {"text": "\n\n".join(lines), "rows": rows}


def _set_subject(flow: str, state: dict[str, Any], choice: str, *, custom_text: str = "") -> None:
    analysis = dict(state.get("source_analysis") or {})
    source_bound = bool(_safe(analysis.get("source_hash"))) and bool(float(analysis.get("duration_seconds") or 0) > 0)
    if choice == "custom":
        if not _safe(custom_text):
            raise ValueError("selfshotflow4_subject_required")
        subject_label = _safe(custom_text)
        subject_type = "custom"
    elif choice in {"motion", "none"}:
        subject_label = "Giữ chuyển động nguồn"
        subject_type = "motion_only"
    else:
        subject_label = "Người do khách xác nhận trong video nguồn" if choice == "person" else "Vật/sản phẩm do khách xác nhận trong video nguồn"
        subject_type = choice
    subject_id = f"user-confirmed-{choice or 'custom'}"
    state["subject_manifest"] = {
        "selection_type": subject_type,
        "subjects": [{
            "subject_id": subject_id,
            "subject_type": choice if choice not in {"motion", "none"} else "custom",
            "label": subject_label,
            "description": subject_label,
            "provenance": "user_confirmed_source_bound",
        }],
        "selected_ids": [subject_id],
        "stable_ids": True,
        "description": subject_label,
        "source_bound": source_bound,
        "user_confirmed_source_bound": True,
    }
    normalized = normalize_subject_locks(flow, state)
    state.clear()
    state.update(normalized)


def _set_track(flow: str, state: dict[str, Any], track_id: str) -> None:
    analysis = dict(state.get("source_analysis") or {})
    rows = _all_subject_candidates(state)
    item = next((row for row in rows if _safe(row.get("subject_id")) == track_id), None)
    if not item:
        raise ValueError("selfshotflow4_track_missing")
    kind = _safe(item.get("subject_type")) or "custom"
    state["subject_manifest"] = {
        "selection_type": kind,
        "subjects": [deepcopy(item)],
        "selected_ids": [track_id],
        "stable_ids": True,
        "description": _safe(item.get("label")),
        "source_bound": True,
        "confirmed": True,
    }
    selected = {track_id}
    state["subject_manifest"]["interaction_graph"] = [
        deepcopy(dict(row))
        for row in list(analysis.get("relationship_candidates") or analysis.get("interaction_graph") or [])
        if _safe(row.get("person_id") or row.get("source_subject_id")) in selected
        or _safe(row.get("object_id") or row.get("target_subject_id")) in selected
    ]
    normalized = normalize_subject_locks(flow, state)
    state.clear()
    state.update(normalized)


def _set_multiple_tracks(flow: str, state: dict[str, Any], selected_ids: list[str]) -> None:
    ordered = [item for item in _all_subject_candidates(state) if _safe(item.get("subject_id")) in set(selected_ids)]
    if len(ordered) < 2:
        raise ValueError("selfshotflow4_multiple_subjects_required")
    analysis = dict(state.get("source_analysis") or {})
    ids = [_safe(item.get("subject_id")) for item in ordered]
    selected = set(ids)
    relationships = [
        deepcopy(dict(row))
        for row in list(analysis.get("relationship_candidates") or analysis.get("interaction_graph") or [])
        if (
            _safe(row.get("person_id") or row.get("source_subject_id")) in selected
            and _safe(row.get("object_id") or row.get("target_subject_id")) in selected
        )
    ]
    state["subject_manifest"] = {
        "selection_type": "multiple",
        "subjects": deepcopy(ordered),
        "selected_ids": ids,
        "stable_ids": True,
        "description": ", ".join(_safe(item.get("description") or item.get("label")) for item in ordered),
        "source_bound": True,
        "confirmed": True,
        "interaction_graph": relationships,
    }
    normalized = normalize_subject_locks(flow, state)
    state.clear()
    state.update(normalized)


def _set_profile(flow: str, state: dict[str, Any], selector: str | int) -> None:
    catalog = _profile_catalog(flow)
    raw = _safe(selector)
    if raw.isdigit():
        index = _as_int(raw, -1)
        item = catalog[index] if 0 <= index < len(catalog) else None
    else:
        item = next((row for row in catalog if _safe(row.get("profile_key")) == raw), None)
    if not item:
        raise ValueError("selfshotflow4_profile_missing")
    item = deepcopy(dict(item))
    for field in ("selected_preset", "idea_id", "idea_preset_id", "idea_title", "idea_selected_prompt", "manual_content"):
        state.pop(field, None)
    profile_id = _safe(item.get("profile_key"))
    title = _safe(item.get("public_name"))
    state["selected_profile"] = title
    state["content_profile_id"] = profile_id
    state["content_profile_name"] = title
    state["selected_content"] = {
        "id": profile_id,
        "title": title,
        "summary": f"{_safe(item.get('description'))} Bám vào chủ thể, quan hệ và chuyển động trong video nguồn.",
        "default_scene_pattern": deepcopy(item.get("default_scene_pattern") or []),
    }
    state["content_source"] = "content_profiles"
    state["content_revision"] = max(1, _as_int(state.get("content_revision"), 0) + 1)
    state["selfshotflow4_prompt_parent"] = "profiles"


def _set_idea(flow: str, state: dict[str, Any], selector: str | int) -> None:
    catalog = ideas_for_group(_safe(state.get("idea_group_id")))
    raw = _safe(selector)
    if raw.isdigit():
        index = _as_int(raw, -1)
        preset = deepcopy(catalog[index]) if 0 <= index < len(catalog) else {}
    else:
        preset = next((deepcopy(item) for item in catalog if _safe(item.get("idea_id")) == raw), {})
    if not preset:
        raise ValueError("selfshotflow4_idea_missing")
    for field in ("selected_profile", "content_profile_id", "content_profile_name", "manual_content"):
        state.pop(field, None)
    idea_id = _safe(preset.get("idea_id"))
    state["selected_preset"] = preset
    state["selected_content"] = {
        "id": idea_id,
        "title": _safe(preset.get("title")),
        "summary": _safe(preset.get("summary")),
        "scene_arc": _safe(preset.get("scene_arc")),
        "style": _safe(preset.get("style")),
        "video_prompt_seed": _safe(preset.get("video_prompt_seed")),
    }
    state["content_source"] = "idea_catalog"
    state["idea_id"] = idea_id
    state["idea_preset_id"] = idea_id
    state["idea_title"] = _safe(preset.get("title"))
    state["idea_parent_product"] = FLOW_PRODUCT_IDS[flow]
    state["idea_parent_flow"] = flow
    state["idea_parent_session_id"] = _safe(state.get("session_id"))
    state["idea_parent_revision"] = max(1, _as_int(state.get("revision"), 1))
    state["idea_return_step"] = "prompt"
    state["content_revision"] = max(1, _as_int(state.get("content_revision"), 0) + 1)
    state["selfshotflow4_prompt_parent"] = "ideas"


def _refresh_prompts(flow: str, state: dict[str, Any]) -> None:
    candidates = _prompt_candidates(flow, state)
    generation = max(1, _as_int(state.get("selfshotflow4_prompt_generation"), 0) + 1)
    refreshed = []
    for index, item in enumerate(candidates):
        candidate = deepcopy(item)
        camera = PROMPT_CAMERA_VARIATIONS[(index + generation) % len(PROMPT_CAMERA_VARIATIONS)]
        rhythm = PROMPT_RHYTHM_VARIATIONS[(index + generation * 2) % len(PROMPT_RHYTHM_VARIATIONS)]
        continuity = PROMPT_CONTINUITY_VARIATIONS[(index + generation * 3) % len(PROMPT_CONTINUITY_VARIATIONS)]
        candidate["id"] = f"{candidate['id']}-g{generation}"
        candidate["text"] = f"{candidate['text']} Nhấn mạnh: {camera}; {rhythm}; {continuity}."
        refreshed.append(candidate)
    state["selfshotflow4_prompt_candidates"] = refreshed
    state["selfshotflow4_prompt_generation"] = generation


def apply_action(flow: str, state: Mapping[str, Any] | None, operation: str, argument: str = "") -> dict[str, Any]:
    active_flow = _flow(flow)
    current = deepcopy(dict(state or {}))
    current[FLOW_FLAGS[active_flow]] = True
    current.setdefault("source_ratio", source_ratio(current))
    active_screen = current_screen(active_flow, current)
    op = _safe(operation)
    arg = _safe(argument)

    if op in OPERATION_SCREENS and active_screen not in OPERATION_SCREENS[op]:
        # Do not allow an older button to mutate a newer SelfShot session.
        return {"state": current, "screen": active_screen}

    if op == "c4upload":
        return {"state": current, "screen": "segment", "pending_media": "source_upload"}

    if op == "c4show":
        target = arg if arg in FLOW_SCREENS[active_flow] else active_screen
        if active_screen == "subject" and target == "analysis":
            current["selfshotflow4_analysis_parent"] = "subject"
        elif target == "analysis" and active_screen in {"segment", "segment_preview"}:
            current["selfshotflow4_analysis_parent"] = "segment"
        parent = screen_parent(active_flow, active_screen, current)
        forward = FORWARD_SCREENS.get(active_screen, frozenset())
        if target != parent and target != active_screen and target not in forward and screen_parent(active_flow, target, current) != active_screen:
            # A stale button can only redisplay its existing parent/child state.
            target = active_screen
        current[FLOW_SCREEN_KEYS[active_flow]] = target
        return {"state": current, "screen": target}

    if op == "c4segment":
        if arg == "whole":
            analysis = dict(current.get("source_analysis") or {})
            try:
                _persist_segment(current, _segment_selection(analysis))
                _persist_derived_scene_count(active_flow, current)
                current["selfshotflow4_analysis_parent"] = "segment"
            except ValueError:
                current[FLOW_SCREEN_KEYS[active_flow]] = "segment"
                return {"state": current, "screen": "segment"}
            target = "analysis"
        elif arg == "custom":
            return {"state": current, "pending": "segment", "back": "segment"}
        elif arg == "preview":
            target = "segment_preview" if current.get("source_segment") else "segment"
        elif arg == "reset":
            _clear_segment_dependents(current, analysis_status="awaiting_segment")
            current.pop("source_segment", None)
            for field in ("selected_start_seconds", "selected_end_seconds", "selected_duration", "analysis_signature"):
                current.pop(field, None)
            current["analysis_status"] = "awaiting_segment"
            target = "segment"
        else:
            target = "segment"
        current[FLOW_SCREEN_KEYS[active_flow]] = target
        return {"state": current, "screen": target}

    if op == "c4mode":
        if active_flow != FLOW_SS3 or arg != "one_take":
            return {"state": current, "screen": active_screen}
        current["selfshot3_transform_mode"] = "one_take_cinematic"
        current["selfshot3_continuity_locked"] = True
        current[FLOW_SCREEN_KEYS[active_flow]] = "subject"
        return {"state": current, "screen": "subject"}

    if op == "c4subject":
        if arg == "custom":
            return {"state": current, "pending": "subject", "back": "subject"}
        if arg == "multiple":
            if len(_all_subject_candidates(current)) < 2:
                current[FLOW_SCREEN_KEYS[active_flow]] = "subject"
                return {"state": current, "screen": "subject"}
            current["selfshotflow4_multi_subject_ids"] = []
            current[FLOW_SCREEN_KEYS[active_flow]] = "subject_multiple"
            return {"state": current, "screen": "subject_multiple"}
        try:
            if arg.startswith("track:"):
                _set_track(active_flow, current, arg.split(":", 1)[1])
            elif arg in {"person", "object", "motion", "none"}:
                _set_subject(active_flow, current, arg)
            else:
                return {"state": current, "screen": "subject"}
        except ValueError:
            return {"state": current, "screen": "subject"}
        current[FLOW_SCREEN_KEYS[active_flow]] = "content_source"
        return {"state": current, "screen": "content_source"}

    if op == "c4multi":
        selected = [_safe(value) for value in current.get("selfshotflow4_multi_subject_ids") or [] if _safe(value)]
        available = {_safe(item.get("subject_id")) for item in _all_subject_candidates(current)}
        if arg == "clear":
            selected = []
        elif arg == "done":
            try:
                _set_multiple_tracks(active_flow, current, selected)
            except ValueError:
                current[FLOW_SCREEN_KEYS[active_flow]] = "subject_multiple"
                return {"state": current, "screen": "subject_multiple"}
            current.pop("selfshotflow4_multi_subject_ids", None)
            current[FLOW_SCREEN_KEYS[active_flow]] = "content_source"
            return {"state": current, "screen": "content_source"}
        elif arg in available:
            if arg in selected:
                selected.remove(arg)
            else:
                selected.append(arg)
        current["selfshotflow4_multi_subject_ids"] = selected
        current[FLOW_SCREEN_KEYS[active_flow]] = "subject_multiple"
        return {"state": current, "screen": "subject_multiple"}

    if op == "c4source":
        if arg == "profiles":
            target = "profiles"
        elif arg == "ideas":
            current.update({
                "idea_parent_product": FLOW_PRODUCT_IDS[active_flow],
                "idea_parent_flow": active_flow,
                "idea_parent_session_id": _safe(current.get("session_id")),
                "idea_parent_revision": max(1, _as_int(current.get("revision"), 1)),
                "idea_return_step": "prompt",
            })
            target = "idea_groups"
        elif arg == "custom":
            return {"state": current, "pending": "content", "back": "content_source"}
        else:
            target = "content_source"
        current[FLOW_SCREEN_KEYS[active_flow]] = target
        return {"state": current, "screen": target}

    if op == "c4profile_page":
        pages = max(1, ceil(len(_profile_catalog(active_flow)) / 8))
        current["selfshotflow4_profile_page"] = max(1, min(pages, _as_int(arg, 1)))
        current[FLOW_SCREEN_KEYS[active_flow]] = "profiles"
        return {"state": current, "screen": "profiles"}

    if op == "c4idea_group":
        if arg not in {item["category_id"] for item in idea_groups()}:
            current[FLOW_SCREEN_KEYS[active_flow]] = "idea_groups"
            return {"state": current, "screen": "idea_groups"}
        current["idea_group_id"] = arg
        current["selfshotflow4_idea_page"] = 1
        current[FLOW_SCREEN_KEYS[active_flow]] = "ideas"
        return {"state": current, "screen": "ideas"}

    if op == "c4idea_page":
        pages = max(1, ceil(len(ideas_for_group(_safe(current.get("idea_group_id")))) / 6))
        current["selfshotflow4_idea_page"] = max(1, min(pages, _as_int(arg, 1)))
        current[FLOW_SCREEN_KEYS[active_flow]] = "ideas"
        return {"state": current, "screen": "ideas"}

    if op == "c4profile":
        try:
            _set_profile(active_flow, current, arg)
        except ValueError:
            current[FLOW_SCREEN_KEYS[active_flow]] = "profiles"
            return {"state": current, "screen": "profiles"}
        _refresh_prompts(active_flow, current)
        current[FLOW_SCREEN_KEYS[active_flow]] = "prompt"
        return {"state": current, "screen": "prompt"}

    if op == "c4idea":
        try:
            _set_idea(active_flow, current, arg)
        except ValueError:
            current[FLOW_SCREEN_KEYS[active_flow]] = "ideas"
            return {"state": current, "screen": "ideas"}
        _refresh_prompts(active_flow, current)
        current[FLOW_SCREEN_KEYS[active_flow]] = "prompt"
        return {"state": current, "screen": "prompt"}

    if op == "c4prompt":
        if arg == "refresh":
            _refresh_prompts(active_flow, current)
            current[FLOW_SCREEN_KEYS[active_flow]] = "prompt"
            return {"state": current, "screen": "prompt"}
        if arg == "edit":
            return {"state": current, "pending": "prompt", "back": "prompt"}
        if arg == "content":
            current[FLOW_SCREEN_KEYS[active_flow]] = "content_view"
            return {"state": current, "screen": "content_view"}
        candidates = list(current.get("selfshotflow4_prompt_candidates") or _prompt_candidates(active_flow, current))
        if arg == "skip":
            current["selected_prompt"] = deepcopy(candidates[0])
        else:
            index = _as_int(arg, 0) - 1
            if not 0 <= index < len(candidates):
                current[FLOW_SCREEN_KEYS[active_flow]] = "prompt"
                return {"state": current, "screen": "prompt"}
            current["selected_prompt"] = deepcopy(candidates[index])
        _prepare_tail(active_flow, current)
        current[FLOW_SCREEN_KEYS[active_flow]] = "prompt"
        return {"state": current, "screen": "tail_review"}

    return {"state": current, "screen": active_screen}


def apply_text(flow: str, state: Mapping[str, Any] | None, pending: str, text: str) -> dict[str, Any]:
    active_flow = _flow(flow)
    current = deepcopy(dict(state or {}))
    current[FLOW_FLAGS[active_flow]] = True
    purpose = _safe(pending)
    value = str(text or "") if purpose == "prompt" else _safe(text)[:5000]
    if purpose == "segment":
        values = value.replace("–", "-").replace("—", "-").split("-", 1)
        if len(values) != 2:
            raise ValueError("selfshotflow4_segment_invalid")
        start_ms = int(float(values[0].strip()) * 1000)
        end_ms = int(float(values[1].strip()) * 1000)
        _persist_segment(
            current,
            _segment_selection(dict(current.get("source_analysis") or {}), start_ms, end_ms),
        )
        _persist_derived_scene_count(active_flow, current)
        target = "analysis"
    elif purpose == "subject":
        if not value:
            raise ValueError("selfshotflow4_subject_required")
        _set_subject(active_flow, current, "custom", custom_text=value)
        target = "content_source"
    elif purpose == "content":
        if not value:
            raise ValueError("selfshotflow4_content_required")
        for field in ("selected_preset", "idea_id", "idea_preset_id", "idea_title", "idea_selected_prompt", "selected_profile", "content_profile_id", "content_profile_name"):
            current.pop(field, None)
        current["selected_content"] = {"id": "custom", "title": "Nội dung tự nhập", "summary": value}
        current["content_source"] = "manual"
        current["content_description"] = value
        current["manual_content"] = value
        current["content_revision"] = max(1, _as_int(current.get("content_revision"), 0) + 1)
        current["selfshotflow4_prompt_parent"] = "content_source"
        _refresh_prompts(active_flow, current)
        target = "prompt"
    elif purpose == "prompt":
        if not value.strip():
            raise ValueError("selfshotflow4_prompt_required")
        current["selected_prompt"] = {"id": "custom", "title": "Câu lệnh tự viết", "text": value}
        _prepare_tail(active_flow, current)
        return {"state": current, "screen": "tail_review"}
    else:
        raise ValueError("selfshotflow4_pending_unknown")
    current[FLOW_SCREEN_KEYS[active_flow]] = target
    return {"state": current, "screen": target}


def pending_copy(flow: str, pending: str) -> str:
    active_flow = _flow(flow)
    copies = {
        "segment": "✂️ <b>Nhập đoạn video</b>\n\nGhi giây bắt đầu-kết thúc, ví dụ: <b>2-12</b>. Đoạn phải nằm trong video nguồn.",
        "subject": "✍️ <b>Mô tả chủ thể cần giữ</b>\n\nGhi rõ người, vật hoặc sản phẩm trong video nguồn. Hệ thống sẽ lưu đây là xác nhận của anh/chị, không giả vờ đã nhận diện tự động.",
        "content": "✍️ <b>Nhập nội dung</b>\n\nMô tả câu chuyện hoặc thay đổi mong muốn nhưng vẫn giữ chủ thể và chuyển động nguồn.",
        "prompt": "✍️ <b>Tự viết câu lệnh video</b>\n\nGửi toàn bộ câu lệnh mới. Hệ thống lưu đúng nguyên văn nội dung anh/chị gửi và vẫn giữ chủ thể cùng chuyển động nguồn.",
    }
    return copies.get(_safe(pending), f"✍️ <b>{flow_label(active_flow)}</b>\n\nNhập nội dung cần tiếp tục.")
