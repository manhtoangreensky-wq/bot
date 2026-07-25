"""Canonical planning routes for the two Self-shot video products.

This module owns only the public planning state machine.  It does not create
jobs, call providers, render files, charge a wallet, or change Tail9's shared
commercial screens.  Keeping the route contract here prevents the legacy
SelfShot2 and SelfShot3 callback maps from handling the same session.
"""

from __future__ import annotations

from copy import deepcopy
from html import escape
from typing import Any, Mapping

from . import video_selfshot2, video_selfshot3


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
    "analysis",
    "mode",
    "subject",
    "content_source",
    "profiles",
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
    "analysis": "segment",
    "mode": "analysis",
    "subject": "analysis",
    "content_source": "subject",
    "profiles": "content_source",
    "ideas": "content_source",
    "prompt": "content_source",
    "content_view": "prompt",
}

PROMPT_STYLES = (
    ("clear", "Mạch kể rõ và liền cảnh", "Camera chuyển động có động cơ, nhịp kể tự nhiên, kết cảnh trọn ý."),
    ("cinematic", "Điện ảnh giàu cảm xúc", "Bố cục điện ảnh, ánh sáng có chủ đích, chuyển tiếp mềm giữa trạng thái."),
    ("real", "Chân thật và gần gũi", "Chuyển động đời thường, vật liệu chân thật, camera ổn định và dễ tin."),
    ("social", "Nhịp mạng xã hội", "Hook rõ, tiết tấu gọn, điểm nhấn thị giác nhưng không cắt cụt hành động."),
    ("premium", "Cao cấp và tối giản", "Khung hình sạch, chuyển động tiết chế, chủ thể nổi bật và kết thúc tinh tế."),
)

OPERATION_SCREENS = {
    "c4segment": frozenset({"segment"}),
    "c4mode": frozenset({"mode"}),
    "c4subject": frozenset({"subject"}),
    "c4source": frozenset({"content_source"}),
    "c4profile_page": frozenset({"profiles"}),
    "c4profile": frozenset({"profiles"}),
    "c4idea_page": frozenset({"ideas"}),
    "c4idea": frozenset({"ideas"}),
    "c4prompt": frozenset({"prompt"}),
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
    if name == "subject" and _flow(_flow_name) == FLOW_SS3:
        return "mode"
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


def _nav(flow: str, screen: str, state: Mapping[str, Any] | None = None) -> list[tuple[str, str]]:
    parent = screen_parent(flow, screen, state)
    back = "vproduct|selfshot_hub" if parent == "hub" else callback(flow, "c4show", parent)
    return [("⬅️ Quay lại", back), ("🏠 Menu chính", "menu|main")]


def validate_rows(rows: list[list[tuple[str, str]]], *, back_callback: str) -> dict[str, Any]:
    errors: list[str] = []
    if not rows:
        errors.append("rows_missing")
    for index, row in enumerate(rows):
        if len(row) not in {2, 5}:
            errors.append(f"row_{index}_invalid_width")
        for label, callback_data in row:
            if not _safe(label) or not _safe(callback_data):
                errors.append(f"row_{index}_button_invalid")
    if not rows or len(rows[-1]) != 2:
        errors.append("navigation_row_missing")
    elif rows[-1][0][1] != back_callback or rows[-1][1][1] != "menu|main":
        errors.append("navigation_row_invalid")
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
    start = max(0, min(_as_int(start_ms), duration_ms))
    end = duration_ms if end_ms is None else max(start, min(_as_int(end_ms), duration_ms))
    if duration_ms <= 0 or end <= start:
        raise ValueError("selfshotflow4_valid_source_segment_required")
    return {"start_ms": start, "end_ms": end, "duration_ms": end - start, "whole_source": start == 0 and end == duration_ms}


def _subject_rows(flow: str, state: Mapping[str, Any]) -> list[list[tuple[str, str]]]:
    analysis = dict(state.get("source_analysis") or {})
    detected = []
    if flow == FLOW_SS2:
        detected = video_selfshot2.detected_subjects(analysis)
    else:
        detected = [
            *list(analysis.get("person_tracks") or []),
            *list(analysis.get("object_tracks") or []),
            *list(analysis.get("product_tracks") or []),
            *list(analysis.get("pet_tracks") or []),
        ]
    buttons: list[tuple[str, str]] = []
    for item in detected[:4]:
        subject_id = _safe(item.get("subject_id") or item.get("track_id"))
        label = _display(item.get("description") or item.get("label") or "Chủ thể")[:28]
        buttons.append((f"🎯 {label}", callback(flow, "c4subject", f"track:{subject_id}")))
    if len(buttons) % 2:
        buttons.append(("🚫 Không có nhân vật chính", callback(flow, "c4subject", "none")))
    buttons.extend([
        ("👤 Người trong video", callback(flow, "c4subject", "person")),
        ("📦 Vật/sản phẩm", callback(flow, "c4subject", "object")),
        ("🎞️ Giữ chuyển động", callback(flow, "c4subject", "motion")),
        ("✍️ Tự mô tả", callback(flow, "c4subject", "custom")),
    ])
    return [buttons[index:index + 2] for index in range(0, len(buttons), 2)]


def _profile_catalog(flow: str) -> list[str]:
    if flow == FLOW_SS2:
        return list(video_selfshot2.CONTENT_PROFILES)
    return list(video_selfshot3.CONTENT_PROFILES)


def _idea_catalog(flow: str) -> list[dict[str, Any]]:
    if flow == FLOW_SS2:
        return [dict(item) for item in video_selfshot2.idea_presets()]
    rows: list[dict[str, Any]] = []
    for group in video_selfshot3.transformation_catalog():
        rows.extend(dict(item) for item in list(group.get("presets") or []))
    return rows


def _page_rows(flow: str, state: Mapping[str, Any], *, kind: str) -> list[list[tuple[str, str]]]:
    page_key = f"selfshotflow4_{kind}_page"
    page = max(1, _as_int(state.get(page_key), 1))
    if kind == "profile":
        catalog = _profile_catalog(flow)
        selected = _safe(state.get("selected_profile"))
        start = (page - 1) * 8
        chunk = catalog[start:start + 8]
        rows = []
        for offset in range(0, len(chunk), 2):
            pair = []
            for local_index, item in enumerate(chunk[offset:offset + 2], start + offset):
                prefix = "✅ " if item == selected else ""
                pair.append((f"{prefix}{item}", callback(flow, "c4profile", str(local_index))))
            rows.append(pair)
    else:
        catalog = _idea_catalog(flow)
        selected = dict(state.get("selected_preset") or {})
        selected_id = _safe(selected.get("id") or selected.get("preset_id"))
        start = (page - 1) * 8
        chunk = catalog[start:start + 8]
        rows = []
        for offset in range(0, len(chunk), 2):
            pair = []
            for local_index, item in enumerate(chunk[offset:offset + 2], start + offset):
                item_id = _safe(item.get("id") or item.get("preset_id"))
                prefix = "✅ " if item_id and item_id == selected_id else ""
                pair.append((f"{prefix}{_display(item.get('title'))[:27]}", callback(flow, "c4idea", str(local_index))))
            rows.append(pair)
    total = max(1, (len(catalog) + 7) // 8)
    rows.append([
        ("⬅️ Trang trước", callback(flow, f"c4{kind}_page", str(max(1, page - 1)))),
        ("➡️ Trang sau", callback(flow, f"c4{kind}_page", str(min(total, page + 1)))),
    ])
    return rows


def _content_summary(state: Mapping[str, Any]) -> str:
    content = dict(state.get("selected_content") or {})
    if content:
        return _safe(content.get("summary") or content.get("title"))
    preset = dict(state.get("selected_preset") or {})
    return _safe(preset.get("title") or preset.get("summary")) or "Chưa chọn"


def _prompt_candidates(flow: str, state: Mapping[str, Any]) -> list[dict[str, str]]:
    content = _content_summary(state)
    analysis = dict(state.get("source_analysis") or {})
    ratio = _safe(state.get("source_ratio") or source_ratio(state))
    segment = dict(state.get("source_segment") or {})
    seconds = max(
        1,
        _as_int((_as_int(segment.get("end_ms")) - _as_int(segment.get("start_ms"))) / 1000)
        or _as_int(analysis.get("duration_seconds"), 1),
    )
    noun = "người/vật đã xác nhận" if flow == FLOW_SS2 else "chủ thể trong một cú máy"
    return [
        {
            "id": style_id,
            "title": title,
            "text": (
                f"{title}. {summary} Giữ {noun}, nhận diện, tỷ lệ cơ thể, thao tác và chuyển động nguồn. "
                f"Nội dung: {content}. Khung {ratio}, đoạn nguồn khoảng {seconds}s; không cắt sang clip khác, "
                "không đổi chủ thể, giữ liên tục giữa mọi nhịp."
            ),
        }
        for style_id, title, summary in PROMPT_STYLES
    ]


def _prepare_ss2(state: dict[str, Any]) -> None:
    analysis = dict(state.get("source_analysis") or {})
    manifest = dict(state.get("subject_manifest") or {})
    constraints = dict(state.get("preserve_constraints") or video_selfshot2.default_preserve_constraints(manifest))
    content = dict(state.get("selected_content") or {})
    if not content:
        preset = dict(state.get("selected_preset") or {})
        content = {"id": _safe(preset.get("id")), "title": _safe(preset.get("title")), "summary": _safe(preset.get("summary"))}
        state["selected_content"] = content
    state["preserve_constraints"] = constraints
    state["scene_count"] = max(1, _as_int(state.get("scene_count"), 1))
    state["aspect_ratio"] = _safe(state.get("source_ratio") or source_ratio(state))
    state["direction_contract"] = video_selfshot2.direction_contract("new_story")
    selected_segment = dict(state.get("source_segment") or {})
    segment_duration = float(_as_int(selected_segment.get("duration_ms")) / 1000)
    plan_analysis = dict(analysis)
    if segment_duration > 0:
        plan_analysis["duration_seconds"] = segment_duration
    state["scene_plan"] = video_selfshot2.build_scene_plan(
        analysis=plan_analysis,
        subject_manifest=manifest,
        constraints=constraints,
        scene_count=int(state["scene_count"]),
        content=content,
        direction=dict(state["direction_contract"]),
    )
    offset = float(_as_int(selected_segment.get("start_ms")) / 1000)
    if offset or segment_duration:
        for scene in state["scene_plan"]:
            scene["source_segment_start"] = round(float(scene.get("source_segment_start") or 0) + offset, 3)
            scene["source_segment_end"] = round(float(scene.get("source_segment_end") or 0) + offset, 3)
            scene["source_segment_selected"] = True
    state["video_prompts"] = video_selfshot2.compile_scene_prompts(
        state["scene_plan"],
        subject_manifest=manifest,
        content=content,
        direction=dict(state["direction_contract"]),
    )
    state["scene_change_plan"] = deepcopy(state["scene_plan"])
    state["continuity_rules"] = "Giữ cùng chủ thể, hành động nguồn và mạch chuyển cảnh liên tục."


def _prepare_ss3(state: dict[str, Any]) -> None:
    segment = dict(state.get("source_segment") or {})
    preset = dict(state.get("selected_preset") or {})
    if not preset:
        content = dict(state.get("selected_content") or {})
        preset = {
            "preset_id": _safe(content.get("id") or "custom"),
            "title": _safe(content.get("title") or "Biến đổi điện ảnh"),
            "summary": _safe(content.get("summary")),
        }
        state["selected_preset"] = preset
    state["transformation_stage_count"] = 4
    state.setdefault("layer_rules", video_selfshot3.default_layer_rules())
    state.setdefault("relationship_locks", [])
    state.setdefault("wardrobe", "biến đổi dần theo nhịp")
    state.setdefault("world", _safe(preset.get("summary") or preset.get("title")))
    state.setdefault("selected_effects", ["ánh sáng", "hiệu ứng nhẹ"])
    state["transformation_content"] = _safe(state.get("transformation_content") or preset.get("summary") or preset.get("title"))
    state["transformation_stages"] = video_selfshot3.build_timeline(
        segment=segment,
        stage_count=4,
        preset=preset,
        wardrobe=_safe(state.get("wardrobe")),
        world=_safe(state.get("world")),
        effects=list(state.get("selected_effects") or []),
    )
    state["compiled_prompt"] = video_selfshot3.compile_prompt(
        mode=video_selfshot3.MODE_ONE_TAKE,
        subject_manifest=dict(state.get("subject_manifest") or {}),
        relationship_locks=list(state.get("relationship_locks") or []),
        layer_rules=dict(state.get("layer_rules") or {}),
        segment=segment,
        stages=list(state["transformation_stages"]),
        wardrobe=_safe(state.get("wardrobe")),
        world=_safe(state.get("world")),
        effects=list(state.get("selected_effects") or []),
        content=_safe(state.get("transformation_content")),
    )
    state["video_prompts"] = list(dict(state["compiled_prompt"]).get("stage_prompts") or [])
    state["scene_plan"] = [
        {
            "scene_index": 1,
            "title": "Biến đổi liên tục một cú máy",
            "duration": max(1, _as_int((_as_int(segment.get("end_ms")) - _as_int(segment.get("start_ms"))) / 1000)),
            "stages": deepcopy(state["transformation_stages"]),
        }
    ]
    state["scene_count"] = 1
    state["aspect_ratio"] = _safe(state.get("source_ratio") or source_ratio(state))
    state["continuity_rules"] = "Giữ khuôn mặt, vóc dáng và chuyển động gốc qua bốn giai đoạn biến đổi liên tục."


def _prepare_tail(flow: str, state: dict[str, Any]) -> None:
    if flow == FLOW_SS2:
        _prepare_ss2(state)
    else:
        _prepare_ss3(state)
    selected = dict(state.get("selected_prompt") or {})
    note = _safe(selected.get("text"))
    if note:
        state["selected_video_prompt"] = note
        if flow == FLOW_SS2:
            for item in list(state.get("video_prompts") or []):
                item["prompt"] = f"{_safe(item.get('prompt'))} Style: {note}"
        else:
            state["prompt_style_note"] = note
    state.update({
        "provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "generated_files": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    })


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
            "Chọn toàn bộ hoặc một đoạn liên tục. Bước này chỉ lưu kế hoạch, chưa tạo video và chưa trừ Xu.",
        ]
        rows = [
            [("🎬 Dùng toàn bộ", callback(active_flow, "c4segment", "whole")), ("✂️ Chọn đoạn", callback(active_flow, "c4segment", "custom"))],
            [("👁️ Xem đoạn đã chọn", callback(active_flow, "c4segment", "preview")), ("🔄 Chọn lại", callback(active_flow, "c4segment", "reset"))],
        ]
    elif name == "analysis":
        tracks = len(list(analysis.get("person_tracks") or [])) + len(list(analysis.get("object_tracks") or []))
        lines = [
            "🔎 <b>Phân tích video nguồn</b>",
            f"Đoạn đã chọn: <b>{_safe(data.get('source_segment') and 'Đã có' or 'Chưa có')}</b> · tỉ lệ nguồn: <b>{source_ratio(data)}</b>",
            f"Dữ liệu cục bộ nhận được: {tracks} track; âm thanh: {'có' if _as_int((analysis.get('audio_manifest') or {}).get('stream_count') or source.get('audio_streams')) else 'không rõ'}.",
            "Nếu chưa có track, anh/chị vẫn có thể tự xác nhận người hoặc vật trong video; hệ thống không giả vờ đã nhận diện được.",
        ]
        rows = [[
            (
                "✨ Biến đổi liên tục một cú máy" if active_flow == FLOW_SS3 else "➡️ Chọn chủ thể",
                callback(active_flow, "c4show", "mode" if active_flow == FLOW_SS3 else "subject"),
            ),
            ("👁️ Xem đoạn", callback(active_flow, "c4show", "segment")),
        ]]
    elif name == "mode":
        lines = [
            "✨ <b>Biến đổi liên tục một cú máy</b>",
            "Giữ khuôn mặt, vóc dáng và chuyển động nguồn liên tục. Trang phục, bối cảnh, ánh sáng và hiệu ứng sẽ thay đổi dần qua bốn giai đoạn, không cắt sang clip không liên quan.",
            "Bước tiếp theo là xác nhận chủ thể cần giữ.",
        ]
        rows = [[
            ("✅ Biến đổi liên tục một cú máy", callback(active_flow, "c4mode", "one_take")),
            ("👁️ Xem phân tích", callback(active_flow, "c4show", "analysis")),
        ]]
    elif name == "subject":
        manifest = dict(data.get("subject_manifest") or {})
        selected = ", ".join(_display(item.get("description") or item.get("label")) for item in manifest.get("subjects") or []) or "Chưa chọn"
        lines = [
            "🎯 <b>Chọn chủ thể cần giữ</b>",
            f"Hiện tại: <b>{selected}</b>",
            "Chọn đúng người/vật trong video hoặc tự mô tả. Khi tracker chưa có dữ liệu, lựa chọn của anh/chị được lưu là xác nhận từ video nguồn, không phải kết quả nhận diện tự động.",
        ]
        rows = _subject_rows(active_flow, data)
    elif name == "content_source":
        lines = [
            "🧩 <b>Chọn cách xây nội dung</b>",
            "Chọn một nguồn nội dung cho đúng video nguồn. Ba đường này độc lập; Kho Ý tưởng đã có cấu trúc sẵn, còn 32 loại nội dung và Tự nhập sẽ tạo prompt từ lựa chọn của anh/chị.",
        ]
        rows = [[
            ("🎯 32 loại nội dung", callback(active_flow, "c4source", "profiles")),
            ("💡 Kho Ý tưởng video", callback(active_flow, "c4source", "ideas")),
        ], [
            ("✍️ Tự nhập nội dung", callback(active_flow, "c4source", "custom")),
            ("🔎 Xem phân tích", callback(active_flow, "c4source", "analysis")),
        ]]
    elif name == "profiles":
        page = max(1, _as_int(data.get("selfshotflow4_profile_page"), 1))
        lines = [
            "🎯 <b>Chọn loại nội dung</b>",
            f"Trang {page}/4 trong 32 loại nội dung. Chọn một loại để tạo đúng 5 prompt dựa trên video nguồn.",
        ]
        rows = _page_rows(active_flow, data, kind="profile")
    elif name == "ideas":
        page = max(1, _as_int(data.get("selfshotflow4_idea_page"), 1))
        lines = [
            "💡 <b>Kho Ý tưởng video</b>",
            f"Trang {page}. Mỗi ý tưởng đã có chủ đề, nhịp và hướng hình ảnh; sau khi chọn sẽ mở 5 prompt phù hợp với video nguồn.",
        ]
        rows = _page_rows(active_flow, data, kind="idea")
    elif name == "prompt":
        candidates = list(data.get("selfshotflow4_prompt_candidates") or _prompt_candidates(active_flow, data))
        lines = [
            "🎬 <b>Chọn prompt video</b>",
            f"Sản phẩm: <b>{flow_label(active_flow)}</b> · Nội dung: <b>{_display(_content_summary(data))}</b>",
            "Mỗi prompt giữ video nguồn liên tục, chỉ đổi cách kể, camera và nhịp chuyển tiếp.",
        ]
        lines.extend(f"{index}. <b>{_display(item.get('title'))}</b>\n{_display(item.get('text'))}" for index, item in enumerate(candidates, 1))
        rows = [
            [(str(index), callback(active_flow, "c4prompt", str(index))) for index in range(1, 6)],
            [("🔄 Đổi 5 prompt", callback(active_flow, "c4prompt", "refresh")), ("✍️ Sửa prompt", callback(active_flow, "c4prompt", "edit"))],
            [("⏭️ Bỏ qua", callback(active_flow, "c4prompt", "skip")), ("👁️ Xem nội dung", callback(active_flow, "c4prompt", "content"))],
        ]
    else:
        lines = [
            "📋 <b>Nội dung đã chọn</b>",
            f"Nguồn nội dung: <b>{_display(_content_summary(data))}</b>",
            "Quay lại để chọn hoặc sửa prompt. Bước này chưa tạo tác vụ và chưa trừ Xu.",
        ]
        rows = [[("🎬 Chọn prompt", callback(active_flow, "c4show", "prompt")), ("✍️ Tự nhập lại", callback(active_flow, "c4source", "custom"))]]

    rows.append(_nav(active_flow, name, data))
    return {"text": "\n\n".join(lines), "rows": rows}


def _set_subject(flow: str, state: dict[str, Any], choice: str, *, custom_text: str = "") -> None:
    analysis = dict(state.get("source_analysis") or {})
    if flow == FLOW_SS2:
        mapping = {
            "person": "person",
            "object": "object",
            "motion": "motion_only",
            "none": "motion_only",
            "custom": "custom",
        }
        manifest = video_selfshot2.select_subjects(analysis, mapping[choice], custom_description=custom_text)
        state["subject_manifest"] = manifest
        state["preserve_constraints"] = video_selfshot2.default_preserve_constraints(manifest)
        return
    source_bound = bool(_safe(analysis.get("source_hash"))) and bool(float(analysis.get("duration_seconds") or 0) > 0)
    if choice == "custom":
        if not _safe(custom_text):
            raise ValueError("selfshotflow4_subject_required")
        subject_label = _safe(custom_text)
        subject_type = "custom"
    elif choice in {"motion", "none"}:
        subject_label = "Giữ chuyển động nguồn"
        subject_type = "custom"
    else:
        subject_label = "Người do khách xác nhận trong video nguồn" if choice == "person" else "Vật/sản phẩm do khách xác nhận trong video nguồn"
        subject_type = choice
    subject_id = f"user-confirmed-{choice}"
    state["subject_manifest"] = {
        "selection_type": subject_type,
        "subjects": [{"subject_id": subject_id, "subject_type": choice, "label": subject_label, "provenance": "user_confirmed_source_bound"}],
        "selected_ids": [subject_id],
        "stable_ids": True,
        "description": subject_label,
        "source_bound": source_bound,
        "user_confirmed_source_bound": True,
    }
    state["relationship_locks"] = []


def _set_track(flow: str, state: dict[str, Any], track_id: str) -> None:
    analysis = dict(state.get("source_analysis") or {})
    if flow == FLOW_SS2:
        detected = video_selfshot2.detected_subjects(analysis)
        item = next((row for row in detected if _safe(row.get("subject_id")) == track_id), None)
        if not item:
            raise ValueError("selfshotflow4_track_missing")
        kind = _safe(item.get("subject_type"))
        manifest = video_selfshot2.select_subjects(analysis, kind, selected_ids=[track_id])
        state["subject_manifest"] = manifest
        state["preserve_constraints"] = video_selfshot2.default_preserve_constraints(manifest)
        return
    rows = [*list(analysis.get("person_tracks") or []), *list(analysis.get("object_tracks") or []), *list(analysis.get("product_tracks") or []), *list(analysis.get("pet_tracks") or [])]
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
    }
    state["relationship_locks"] = video_selfshot3.build_interaction_lock(state["subject_manifest"], analysis)


def _set_profile(flow: str, state: dict[str, Any], index: int) -> None:
    catalog = _profile_catalog(flow)
    if not 0 <= index < len(catalog):
        raise ValueError("selfshotflow4_profile_missing")
    title = catalog[index]
    state["selected_profile"] = title
    state["selected_content"] = {
        "id": f"profile-{index + 1}",
        "title": title,
        "summary": f"Nội dung {title.lower()} bám vào hành động và chủ thể trong video nguồn.",
    }
    state["content_source"] = "profile"
    state["selfshotflow4_prompt_parent"] = "profiles"


def _set_idea(flow: str, state: dict[str, Any], index: int) -> None:
    catalog = _idea_catalog(flow)
    if not 0 <= index < len(catalog):
        raise ValueError("selfshotflow4_idea_missing")
    preset = deepcopy(catalog[index])
    state["selected_preset"] = preset
    state["selected_content"] = {
        "id": _safe(preset.get("id") or preset.get("preset_id")),
        "title": _safe(preset.get("title")),
        "summary": _safe(preset.get("summary")),
    }
    state["content_source"] = "idea"
    state["selfshotflow4_prompt_parent"] = "ideas"


def _refresh_prompts(flow: str, state: dict[str, Any]) -> None:
    candidates = _prompt_candidates(flow, state)
    offset = _as_int(state.get("selfshotflow4_prompt_offset")) % len(candidates)
    state["selfshotflow4_prompt_candidates"] = candidates[offset:] + candidates[:offset]
    state["selfshotflow4_prompt_offset"] = offset + 1


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

    if op == "c4show":
        target = arg if arg in FLOW_SCREENS[active_flow] else active_screen
        parent = screen_parent(active_flow, active_screen, current)
        if target != parent and target != active_screen and screen_parent(active_flow, target, current) != active_screen:
            # A stale button can only redisplay its existing parent/child state.
            target = active_screen
        current[FLOW_SCREEN_KEYS[active_flow]] = target
        return {"state": current, "screen": target}

    if op == "c4segment":
        if arg == "whole":
            analysis = dict(current.get("source_analysis") or {})
            try:
                current["source_segment"] = _segment_selection(analysis)
            except ValueError:
                current[FLOW_SCREEN_KEYS[active_flow]] = "segment"
                return {"state": current, "screen": "segment"}
            target = "analysis"
        elif arg == "custom":
            return {"state": current, "pending": "segment", "back": "segment"}
        elif arg == "preview":
            target = "segment"
        elif arg == "reset":
            current.pop("source_segment", None)
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

    if op == "c4source":
        if arg == "profiles":
            target = "profiles"
        elif arg == "ideas":
            target = "ideas"
        elif arg == "custom":
            return {"state": current, "pending": "content", "back": "content_source"}
        elif arg == "analysis":
            target = "analysis"
        else:
            target = "content_source"
        current[FLOW_SCREEN_KEYS[active_flow]] = target
        return {"state": current, "screen": target}

    if op == "c4profile_page":
        current["selfshotflow4_profile_page"] = max(1, min(4, _as_int(arg, 1)))
        current[FLOW_SCREEN_KEYS[active_flow]] = "profiles"
        return {"state": current, "screen": "profiles"}

    if op == "c4idea_page":
        pages = max(1, (len(_idea_catalog(active_flow)) + 7) // 8)
        current["selfshotflow4_idea_page"] = max(1, min(pages, _as_int(arg, 1)))
        current[FLOW_SCREEN_KEYS[active_flow]] = "ideas"
        return {"state": current, "screen": "ideas"}

    if op == "c4profile":
        index = _as_int(arg, -1)
        if not 0 <= index < len(_profile_catalog(active_flow)):
            current[FLOW_SCREEN_KEYS[active_flow]] = "profiles"
            return {"state": current, "screen": "profiles"}
        _set_profile(active_flow, current, index)
        _refresh_prompts(active_flow, current)
        current[FLOW_SCREEN_KEYS[active_flow]] = "prompt"
        return {"state": current, "screen": "prompt"}

    if op == "c4idea":
        index = _as_int(arg, -1)
        if not 0 <= index < len(_idea_catalog(active_flow)):
            current[FLOW_SCREEN_KEYS[active_flow]] = "ideas"
            return {"state": current, "screen": "ideas"}
        _set_idea(active_flow, current, index)
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
    value = _safe(text)[:5000]
    purpose = _safe(pending)
    if purpose == "segment":
        values = value.replace("–", "-").replace("—", "-").split("-", 1)
        if len(values) != 2:
            raise ValueError("selfshotflow4_segment_invalid")
        start_ms = int(float(values[0].strip()) * 1000)
        end_ms = int(float(values[1].strip()) * 1000)
        current["source_segment"] = _segment_selection(dict(current.get("source_analysis") or {}), start_ms, end_ms)
        target = "analysis"
    elif purpose == "subject":
        if not value:
            raise ValueError("selfshotflow4_subject_required")
        _set_subject(active_flow, current, "custom", custom_text=value)
        target = "content_source"
    elif purpose == "content":
        if not value:
            raise ValueError("selfshotflow4_content_required")
        current["selected_content"] = {"id": "custom", "title": "Nội dung tự nhập", "summary": value}
        current["content_source"] = "custom"
        current["selfshotflow4_prompt_parent"] = "content_source"
        _refresh_prompts(active_flow, current)
        target = "prompt"
    elif purpose == "prompt":
        if not value:
            raise ValueError("selfshotflow4_prompt_required")
        current["selected_prompt"] = {"id": "custom", "title": "Prompt đã chỉnh", "text": value}
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
        "prompt": "✍️ <b>Sửa prompt video</b>\n\nGửi yêu cầu chỉnh. Hệ thống giữ khóa chủ thể và chuyển động nguồn.",
    }
    return copies.get(_safe(pending), f"✍️ <b>{flow_label(active_flow)}</b>\n\nNhập nội dung cần tiếp tục.")
