"""Canonical Storyboard planning contract.

This module is deliberately provider-free.  It owns the Storyboard state shape,
scene/image mapping, prompt compilation and preflight truth; Telegram rendering
and paid execution remain in ``bot.py`` and the Product Video pipeline.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SCHEMA_VERSION = 3
MIN_SCENES = 1
MIN_PUBLIC_SCENES = 2
MAX_SCENES = 20
SCENE_SECONDS = 8
SUPPORTED_RATIOS = ("9:16", "16:9", "1:1", "4:5")
VALID_SLOTS = frozenset({"start", "end"})


STORYBOARD_SUGGESTIONS = (
    ("Mở bằng vấn đề thật", "Giới thiệu vấn đề, cho thấy nguyên nhân, giải pháp và kết quả rõ ràng."),
    ("Thành quả trước, hành trình sau", "Mở bằng kết quả đáng nhớ rồi dẫn lại quá trình tạo nên kết quả đó."),
    ("Một ngày cùng sản phẩm", "Theo sản phẩm qua các tình huống sử dụng tự nhiên và kết bằng lợi ích thật."),
    ("Mở hộp và khám phá", "Dẫn từ bao bì, chi tiết, thao tác dùng đến khung hình sản phẩm hoàn chỉnh."),
    ("Trước và sau", "Giữ cùng chủ thể, bối cảnh và góc nhìn để thay đổi được nhìn thấy rõ."),
    ("Hành trình của nhân vật", "Mỗi cảnh là một hành động trọn vẹn, nối tiếp tới thay đổi cuối cùng."),
    ("Khám phá một không gian", "Dẫn người xem theo một hướng liên tục qua các khu vực và điểm nhấn."),
    ("Ba bước dễ làm", "Chia quy trình thành các bước hoàn chỉnh, không cắt giữa thao tác."),
    ("Câu hỏi và lời giải", "Mở bằng câu hỏi, mỗi cảnh trả lời một phần, cảnh cuối chốt điều cần nhớ."),
    ("Chi tiết tạo khác biệt", "Đi từ cận cảnh vật liệu tới công dụng, trải nghiệm và kết luận."),
    ("Một lựa chọn có căn cứ", "Đặt hai lựa chọn trong cùng điều kiện, thử nghiệm rồi chốt kết quả."),
    ("Góc nhìn người dùng", "Đi từ nhu cầu, trải nghiệm thực tế tới nhận xét cuối có bằng chứng."),
    ("Câu chuyện nguồn gốc", "Nối nguồn gốc, quá trình hình thành và giá trị ở hiện tại."),
    ("Một thử thách", "Thiết lập mục tiêu, thực hiện đủ hành động và xác nhận kết quả."),
    ("Khoảnh khắc đời thường", "Kể bằng các hành động gần gũi, giữ nhân vật và không gian liền mạch."),
    ("Từ bản vẽ tới thực tế", "Đi từ ý tưởng, từng bước hoàn thiện đến thành phẩm cuối."),
    ("Tính năng trong tình huống thật", "Mỗi cảnh chứng minh một lợi ích bằng hành động cụ thể."),
    ("Một ngày trước và sau thay đổi", "Theo cùng nhân vật qua thời gian để kết quả có nguyên nhân rõ."),
    ("Mở bằng chi tiết bí ẩn", "Mở rộng dần bối cảnh, hé lộ chủ thể và khép bằng toàn cảnh."),
    ("Kết nối ba góc nhìn", "Nối toàn cảnh, hành động và cận cảnh thành một câu chuyện thống nhất."),
)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean_text(value: Any, limit: int = 4000) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def _empty_image(slot: str) -> dict[str, Any]:
    return {
        "slot": slot,
        "status": "missing" if slot == "start" else "not_selected",
        "image_id": "",
        "file_id": "",
        "result_url": "",
        "source_type": "",
        "artifact_receipt": {},
        "prompt_version": 0,
        "prompt": "",
        "negative_prompt": "",
    }


def _empty_scene(index: int) -> dict[str, Any]:
    return {
        "scene_id": f"scene_{index}",
        "scene_index": index,
        "content": "",
        "content_approved": False,
        "start_state": "",
        "main_action": "",
        "end_state": "",
        "camera_motion": "",
        "subject_motion": "",
        "negative_constraints": "",
        "duration_seconds": SCENE_SECONDS,
        "start_image": _empty_image("start"),
        "end_image": _empty_image("end"),
        "end_image_mode": "optional",
        "video_prompt_version": 0,
        "video_prompt": "",
        "video_negative_prompt": "",
    }


def default_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "storyboard_session_id": "",
        "flow": "storyboard",
        "owner": "storyboard",
        "revision": 0,
        "return_to": "menu|main_video",
        "screen": "entry",
        "history": [],
        "entry_mode": "",
        "scene_count": 0,
        "aspect_ratio": "",
        "content_mode": "",
        "content_source": "",
        "content": "",
        "profile_page": 1,
        "suggestion_offset": 0,
        "scenes": [],
        "active_scene_index": 1,
        "active_slot": "start",
        "asset_mode": "start_only",
        "awaiting_input": "",
        "processed_callback_ids": [],
        "processed_text_message_ids": [],
        "processed_media_message_ids": [],
        "image_prompt_offset": 0,
        "transition_index": 1,
        "transitions": [],
        "continuity": {},
        "profile": {},
        "style": {},
        "entity_bible": {},
        "entity_references": [],
        "entity_needs": {},
        "entity_summary": "",
        "reference_source_assets": [],
        "reference_gate_complete": False,
        "creative_controls": {},
        "preservation_requirements": {},
        "middle_complete": False,
        "entity_return_screen": "",
        "entity_bridge_key": "",
        "addons": {},
        "addons_ready": False,
        "image_generation": {},
        "generation_state": "planning",
        "uploaded_storyboard_files": [],
        "detected_panel_count": 0,
        "upload_confirmed": False,
        "upload_panel_index": 1,
        "manifest": {},
    }


def ensure_session(value: dict[str, Any] | None, session_id: str) -> dict[str, Any]:
    """Return a normalized board with one stable, non-empty session owner."""
    state = normalize_state(value)
    if not state.get("storyboard_session_id"):
        normalized_session_id = _clean_text(session_id, 80)
        if not normalized_session_id:
            raise ValueError("storyboard_session_id_required")
        state["storyboard_session_id"] = normalized_session_id
    state["revision"] = max(1, _safe_int(state.get("revision"), 1))
    return state


def normalize_state(value: dict[str, Any] | None) -> dict[str, Any]:
    raw = deepcopy(value or {})
    state = default_state()
    state.update(raw)
    state["schema_version"] = SCHEMA_VERSION
    state["storyboard_session_id"] = _clean_text(state.get("storyboard_session_id"), 80)
    state["flow"] = "storyboard"
    state["owner"] = "storyboard"
    state["revision"] = max(0, _safe_int(state.get("revision"), 0))
    state["return_to"] = _clean_text(state.get("return_to") or "menu|main_video", 120)
    state["generation_state"] = _clean_text(state.get("generation_state") or "planning", 40)
    count = max(0, min(MAX_SCENES, _safe_int(state.get("scene_count"), 0)))
    state["scene_count"] = count
    if state.get("aspect_ratio") not in SUPPORTED_RATIOS:
        state["aspect_ratio"] = ""
    scenes_by_index = {
        _safe_int(item.get("scene_index"), 0): dict(item)
        for item in state.get("scenes") or []
        if isinstance(item, dict) and _safe_int(item.get("scene_index"), 0) > 0
    }
    scenes = []
    for index in range(1, count + 1):
        scene = _empty_scene(index)
        scene.update(scenes_by_index.get(index) or {})
        scene["scene_id"] = f"scene_{index}"
        scene["scene_index"] = index
        for slot in VALID_SLOTS:
            image = _empty_image(slot)
            image.update(dict(scene.get(f"{slot}_image") or {}))
            image["slot"] = slot
            scene[f"{slot}_image"] = image
        if scene.get("end_image_mode") not in {"optional", "required", "none"}:
            scene["end_image_mode"] = "optional"
        scenes.append(scene)
    state["scenes"] = scenes
    state["active_scene_index"] = max(1, min(max(1, count), _safe_int(state.get("active_scene_index"), 1)))
    state["active_slot"] = str(state.get("active_slot") or "start") if str(state.get("active_slot") or "start") in VALID_SLOTS else "start"
    state["history"] = [str(item) for item in state.get("history") or [] if str(item or "")][-40:]
    state["processed_callback_ids"] = [str(item) for item in state.get("processed_callback_ids") or [] if str(item or "")][-100:]
    state["processed_text_message_ids"] = [
        _safe_int(item, 0) for item in state.get("processed_text_message_ids") or [] if _safe_int(item, 0) > 0
    ][-100:]
    state["processed_media_message_ids"] = [
        _safe_int(item, 0) for item in state.get("processed_media_message_ids") or [] if _safe_int(item, 0) > 0
    ][-100:]
    state["image_prompt_offset"] = max(0, min(15, _safe_int(state.get("image_prompt_offset"), 0)))
    state["profile_page"] = max(1, _safe_int(state.get("profile_page"), 1))
    state["profile"] = dict(state.get("profile") or {})
    state["continuity"] = dict(state.get("continuity") or {})
    state["style"] = dict(state.get("style") or {})
    state["entity_bible"] = dict(state.get("entity_bible") or {})
    state["entity_references"] = [
        dict(item)
        for item in state.get("entity_references") or []
        if isinstance(item, dict)
    ][:100]
    state["entity_needs"] = dict(state.get("entity_needs") or {})
    state["entity_summary"] = _clean_text(state.get("entity_summary"), 800)
    state["reference_source_assets"] = [
        deepcopy(dict(item))
        for item in state.get("reference_source_assets") or []
        if isinstance(item, dict)
        and _clean_text(
            item.get("telegram_file_id") or item.get("file_id") or item.get("result_url"),
            1000,
        )
    ][:100]
    state["reference_gate_complete"] = bool(
        state.get("reference_gate_complete")
        and state["reference_source_assets"]
    )
    state["creative_controls"] = {
        str(key): dict(item)
        for key, item in dict(state.get("creative_controls") or {}).items()
        if isinstance(item, dict)
    }
    state["preservation_requirements"] = {
        str(key): dict(item)
        for key, item in dict(state.get("preservation_requirements") or {}).items()
        if isinstance(item, dict)
    }
    state["middle_complete"] = bool(state.get("middle_complete"))
    state["entity_return_screen"] = _clean_text(state.get("entity_return_screen"), 80)
    state["entity_bridge_key"] = _clean_text(state.get("entity_bridge_key"), 80)
    if state.get("asset_mode") not in {"start_only", "start_end"}:
        state["asset_mode"] = "start_only"
    state["addons"] = dict(state.get("addons") or {})
    state["image_generation"] = dict(state.get("image_generation") or {})
    uploaded_files = []
    for item in state.get("uploaded_storyboard_files") or []:
        if not isinstance(item, dict):
            continue
        file_id = _clean_text(item.get("file_id"), 512)
        if not file_id:
            continue
        uploaded_files.append({
            "file_id": file_id,
            "file_unique_id": _clean_text(item.get("file_unique_id"), 256),
            "file_name": _clean_text(item.get("file_name"), 320),
            "mime_type": _clean_text(item.get("mime_type"), 160),
            "caption": _clean_text(item.get("caption"), 1200),
            "message_id": max(0, _safe_int(item.get("message_id"), 0)),
            "panel_count": max(1, min(MAX_SCENES, _safe_int(item.get("panel_count"), 1))),
        })
    state["uploaded_storyboard_files"] = uploaded_files[:MAX_SCENES]
    detected = _safe_int(state.get("detected_panel_count"), 0)
    if uploaded_files and detected <= 0:
        detected = sum(_safe_int(item.get("panel_count"), 1) for item in uploaded_files)
    state["detected_panel_count"] = max(0, min(MAX_SCENES, detected))
    state["upload_confirmed"] = bool(state.get("upload_confirmed"))
    state["upload_panel_index"] = max(
        1,
        min(max(1, len(uploaded_files)), _safe_int(state.get("upload_panel_index"), 1)),
    )
    state["manifest"] = dict(state.get("manifest") or {})
    state["transitions"] = [dict(item) for item in state.get("transitions") or [] if isinstance(item, dict)][: max(0, count - 1)]
    return state


def move(state: dict[str, Any], screen: str, *, push: bool = True, **fields: Any) -> dict[str, Any]:
    current = normalize_state(state)
    history = list(current.get("history") or [])
    if push and current.get("screen") != screen:
        history.append(str(current.get("screen") or "entry"))
    current.update(fields)
    current["screen"] = str(screen)
    current["history"] = history[-40:]
    return normalize_state(current)


def back(state: dict[str, Any]) -> dict[str, Any]:
    current = normalize_state(state)
    history = list(current.get("history") or [])
    target = history.pop() if history else "entry"
    current["screen"] = target
    current["history"] = history
    current["awaiting_input"] = ""
    return normalize_state(current)


def set_scene_count(state: dict[str, Any], count: int) -> dict[str, Any]:
    count = _safe_int(count, 0)
    if count < MIN_SCENES or count > MAX_SCENES:
        raise ValueError("scene_count_out_of_range")
    current = normalize_state({**state, "scene_count": count})
    return current


def set_ratio(state: dict[str, Any], ratio: str) -> dict[str, Any]:
    if ratio not in SUPPORTED_RATIOS:
        raise ValueError("aspect_ratio_unsupported")
    return normalize_state({**state, "aspect_ratio": ratio})


def storyboard_upload_record(
    *,
    file_id: str,
    file_unique_id: str = "",
    file_name: str = "",
    mime_type: str = "",
    caption: str = "",
    message_id: int = 0,
    panel_count: int = 1,
) -> dict[str, Any]:
    clean_file_id = _clean_text(file_id, 512)
    if not clean_file_id:
        raise ValueError("storyboard_upload_file_missing")
    return {
        "file_id": clean_file_id,
        "file_unique_id": _clean_text(file_unique_id, 256),
        "file_name": _clean_text(file_name, 320),
        "mime_type": _clean_text(mime_type, 160),
        "caption": _clean_text(caption, 1200),
        "message_id": max(0, _safe_int(message_id, 0)),
        "panel_count": max(1, min(MAX_SCENES, _safe_int(panel_count, 1))),
    }


def add_uploaded_storyboard(state: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    current = normalize_state(state)
    clean = storyboard_upload_record(**dict(record or {}))
    identity = clean.get("file_unique_id") or clean.get("file_id")
    files = list(current.get("uploaded_storyboard_files") or [])
    if any((item.get("file_unique_id") or item.get("file_id")) == identity for item in files):
        return current
    files.append(clean)
    current["uploaded_storyboard_files"] = files[:MAX_SCENES]
    current["detected_panel_count"] = min(
        MAX_SCENES,
        sum(_safe_int(item.get("panel_count"), 1) for item in current["uploaded_storyboard_files"]),
    )
    current["upload_panel_index"] = len(current["uploaded_storyboard_files"])
    current["upload_confirmed"] = False
    return normalize_state(current)


def clear_uploaded_storyboard(state: dict[str, Any]) -> dict[str, Any]:
    current = normalize_state(state)
    current.update({
        "uploaded_storyboard_files": [],
        "detected_panel_count": 0,
        "upload_confirmed": False,
        "upload_panel_index": 1,
    })
    return normalize_state(current)


def set_detected_panel_count(state: dict[str, Any], count: int) -> dict[str, Any]:
    value = _safe_int(count, 0)
    if value < MIN_PUBLIC_SCENES or value > MAX_SCENES:
        raise ValueError("storyboard_panel_count_out_of_range")
    current = set_scene_count(state, value)
    current["detected_panel_count"] = value
    current["upload_confirmed"] = False
    return normalize_state(current)


def apply_uploaded_storyboard(state: dict[str, Any]) -> dict[str, Any]:
    current = normalize_state(state)
    files = list(current.get("uploaded_storyboard_files") or [])
    if not files:
        raise ValueError("storyboard_upload_missing")
    count = _safe_int(current.get("scene_count"), 0) or _safe_int(current.get("detected_panel_count"), 0)
    if count < MIN_PUBLIC_SCENES or count > MAX_SCENES:
        raise ValueError("storyboard_panel_count_out_of_range")
    current = set_scene_count(current, count)
    labels = []
    for item in files:
        labels.append(
            _clean_text(item.get("caption"), 600)
            or _clean_text(item.get("file_name"), 240)
            or "panel storyboard đã gửi"
        )
    summary = "; ".join(labels[:6])
    current = apply_content(
        current,
        f"Storyboard có sẵn gồm {count} cảnh. Tư liệu nguồn: {summary}",
        mode="existing_upload",
    )
    for index, scene in enumerate(current.get("scenes") or [], start=1):
        source = labels[min(index - 1, len(labels) - 1)]
        scene["content"] = f"Cảnh {index}: triển khai trọn vẹn panel {index} từ {source}"
        scene["main_action"] = f"Hoàn thành diễn biến của panel {index} trước khi chuyển cảnh"
    current["content_source"] = "uploaded_storyboard"
    current["upload_confirmed"] = True
    return normalize_state(current)


def set_profile(state: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    current = normalize_state(state)
    clean = dict(profile or {})
    if not _clean_text(clean.get("profile_key"), 80) or not _clean_text(clean.get("public_name"), 160):
        raise ValueError("storyboard_profile_invalid")
    current["profile"] = {
        "key": _clean_text(clean.get("profile_key"), 80),
        "label": _clean_text(clean.get("public_name"), 160),
        "description": _clean_text(clean.get("description"), 600),
        "default_scene_pattern": [
            _clean_text(item, 240)
            for item in clean.get("default_scene_pattern") or []
            if _clean_text(item, 240)
        ][:12],
    }
    current["suggestion_offset"] = 0
    return normalize_state(current)


def suggestion_page(state: dict[str, Any]) -> list[dict[str, Any]]:
    current = normalize_state(state)
    profile = dict(current.get("profile") or {})
    profile_label = _clean_text(profile.get("label"), 160) or "loại nội dung đã chọn"
    profile_description = _clean_text(profile.get("description"), 360)
    pattern = [
        _clean_text(item, 160)
        for item in profile.get("default_scene_pattern") or []
        if _clean_text(item, 160)
    ]
    pattern_copy = " → ".join(pattern[:5])
    offset = _safe_int(current.get("suggestion_offset"), 0) % len(STORYBOARD_SUGGESTIONS)
    rows = []
    for step in range(5):
        title, structure = STORYBOARD_SUGGESTIONS[(offset + step) % len(STORYBOARD_SUGGESTIONS)]
        related = f"{structure} Triển khai theo {profile_label}"
        if profile_description:
            related += f": {profile_description}"
        if pattern_copy:
            related += f". Nhịp nội dung: {pattern_copy}"
        rows.append({
            "index": step + 1,
            "title": title,
            "content": related + ".",
        })
    return rows


def rotate_suggestions(state: dict[str, Any]) -> dict[str, Any]:
    current = normalize_state(state)
    current["suggestion_offset"] = (_safe_int(current.get("suggestion_offset"), 0) + 5) % len(STORYBOARD_SUGGESTIONS)
    return current


def _scene_beat(content: str, index: int, count: int, pattern: list[str] | None = None) -> tuple[str, str, str]:
    pattern = [item for item in (pattern or []) if item]
    pattern_hint = pattern[min(index - 1, len(pattern) - 1)] if pattern else ""
    action_hint = f" theo nhịp ‘{pattern_hint}’" if pattern_hint else ""
    if count == 1:
        return (
            f"Mở rõ chủ thể và mục tiêu: {content}",
            f"Thực hiện một hành động chính trọn vẹn liên quan trực tiếp tới {content}{action_hint}",
            "Khép bằng kết quả rõ và camera đã hoàn tất chuyển động",
        )
    if index == 1:
        return (
            f"Giới thiệu chủ thể, bối cảnh và vấn đề của {content}",
            f"Mở câu chuyện bằng một hành động có đầu và có đích{action_hint}",
            "Kết ở trạng thái đã sẵn sàng cho bước phát triển tiếp theo",
        )
    if index == count:
        return (
            "Tiếp nhận đúng trạng thái cuối của cảnh trước",
            f"Hoàn tất ý cuối cùng của {content} bằng một hành động cụ thể{action_hint}",
            "Khép câu chuyện tự nhiên bằng kết quả hoặc lời mời rõ ràng",
        )
    return (
        "Tiếp nhận trạng thái và hướng chuyển động của cảnh trước",
        f"Phát triển ý {index}/{count} của {content} bằng một hành động duy nhất{action_hint}",
        "Hoàn tất hành động rồi để lại trạng thái nối cảnh rõ ràng",
    )


def apply_content(state: dict[str, Any], content: str, *, mode: str) -> dict[str, Any]:
    value = _clean_text(content, 3000)
    if not value:
        raise ValueError("storyboard_content_missing")
    current = normalize_state(state)
    current.update({
        "content": value,
        "content_mode": str(mode or "manual"),
        "middle_complete": False,
        "reference_gate_complete": False,
    })
    profile_pattern = [
        _clean_text(item, 160)
        for item in dict(current.get("profile") or {}).get("default_scene_pattern") or []
        if _clean_text(item, 160)
    ]
    scenes = []
    for index in range(1, current["scene_count"] + 1):
        old = current["scenes"][index - 1]
        start_state, action, end_state = _scene_beat(value, index, current["scene_count"], profile_pattern)
        scene = dict(old)
        scene.update({
            "content": f"Cảnh {index}: {action}",
            "content_approved": False,
            "start_state": start_state,
            "main_action": action,
            "end_state": end_state,
            "camera_motion": "Camera chuyển động có chủ đích và dừng tự nhiên trước điểm cắt",
            "subject_motion": action,
            "negative_constraints": "không cắt giữa hành động, không đổi nhận diện, không tạo chữ giả",
        })
        scenes.append(scene)
    current["scenes"] = scenes
    current["active_scene_index"] = 1
    return normalize_state(current)


def set_scene_content(state: dict[str, Any], scene_index: int, content: str) -> dict[str, Any]:
    current = normalize_state(state)
    index = _safe_int(scene_index, 0)
    if index < 1 or index > current["scene_count"]:
        raise ValueError("scene_index_out_of_range")
    value = _clean_text(content, 1800)
    if not value:
        raise ValueError("scene_content_missing")
    scene = dict(current["scenes"][index - 1])
    scene.update({"content": value, "main_action": value, "content_approved": False})
    current["scenes"][index - 1] = scene
    return normalize_state(current)


def approve_content(state: dict[str, Any]) -> dict[str, Any]:
    current = normalize_state(state)
    if not current.get("content") or any(not _clean_text(item.get("content")) for item in current["scenes"]):
        raise ValueError("scene_content_incomplete")
    for scene in current["scenes"]:
        scene["content_approved"] = True
    return current


def set_reference_source_assets(
    state: dict[str, Any],
    assets: list[dict[str, Any]],
    *,
    complete: bool,
) -> dict[str, Any]:
    """Persist the mandatory pre-entity reference intake without assigning owners."""

    current = normalize_state(state)
    clean_assets = [
        deepcopy(dict(item))
        for item in assets or []
        if isinstance(item, dict)
        and _clean_text(
            item.get("telegram_file_id") or item.get("file_id") or item.get("result_url"),
            1000,
        )
    ][:100]
    if complete and not clean_assets:
        raise ValueError("storyboard_reference_image_required")
    current["reference_source_assets"] = clean_assets
    current["reference_gate_complete"] = bool(complete and clean_assets)
    return normalize_state(current)


def apply_middle_contract(
    state: dict[str, Any],
    *,
    bible: dict[str, Any],
    references: list[dict[str, Any]],
    needs: dict[str, Any],
    entity_summary: str,
    creative_controls: dict[str, Any],
    preservation_requirements: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist the Storyboard-only entity and creative middle contract."""

    current = normalize_state(state)
    clean_bible = deepcopy(dict(bible or {}))
    clean_references = [
        deepcopy(dict(item))
        for item in references or []
        if isinstance(item, dict)
    ][:100]
    clean_creative = {
        str(key): deepcopy(dict(item))
        for key, item in dict(creative_controls or {}).items()
        if isinstance(item, dict)
    }
    clean_requirements = {
        str(key): deepcopy(dict(item))
        for key, item in dict(preservation_requirements or {}).items()
        if isinstance(item, dict)
    }
    selected = {
        key: _clean_text(item.get("value"), 1200)
        for key, item in clean_creative.items()
        if bool(item.get("enabled")) and _clean_text(item.get("value"), 1200)
    }

    current.update({
        "entity_bible": clean_bible,
        "entity_references": clean_references,
        "entity_needs": deepcopy(dict(needs or {})),
        "entity_summary": _clean_text(entity_summary, 800),
        "creative_controls": clean_creative,
        "preservation_requirements": clean_requirements,
        "middle_complete": True,
    })

    style = dict(current.get("style") or {})
    style_mapping = {
        "context": "context",
        "colors": "colors",
        "visual_style": "visual",
        "pacing": "pacing",
        "emotion": "emotion",
    }
    for source_key, target_key in style_mapping.items():
        if selected.get(source_key):
            style[target_key] = selected[source_key]
        elif source_key in clean_creative:
            style.pop(target_key, None)
    current["style"] = style

    continuity = dict(clean_bible.get("continuity") or current.get("continuity") or {})
    entity_fields = (
        ("characters", "display_name", "characters"),
        ("locations", "name", "locations"),
        ("products", "name", "products"),
        ("props", "name", "props"),
    )
    for source_field, label_field, target_field in entity_fields:
        labels = [
            _clean_text(item.get(label_field), 240)
            for item in clean_bible.get(source_field) or []
            if isinstance(item, dict) and _clean_text(item.get(label_field), 240)
        ]
        if labels:
            continuity[target_field] = labels
    current["continuity"] = continuity

    selected_requirements = [
        _clean_text(item.get("value"), 1200)
        for item in clean_requirements.values()
        if bool(item.get("enabled")) and _clean_text(item.get("value"), 1200)
    ]
    if selected_requirements:
        continuity["requirements"] = selected_requirements
    else:
        continuity.pop("requirements", None)
    current["continuity"] = continuity

    camera = selected.get("camera", "")
    motion = selected.get("motion", "")
    negative = selected.get("negative", "")
    requirement_copy = "; ".join(selected_requirements)
    for scene in current.get("scenes") or []:
        scene["camera_motion"] = camera or "Camera chuyển động có chủ đích và dừng tự nhiên trước điểm cắt"
        scene["subject_motion"] = motion or str(scene.get("main_action") or "")
        scene["negative_constraints"] = "; ".join(
            item
            for item in (
                negative or "không cắt giữa hành động, không đổi nhận diện, không tạo chữ giả",
                requirement_copy,
            )
            if item
        )
    return normalize_state(current)


def image_record(
    *,
    scene_index: int,
    slot: str,
    file_id: str = "",
    result_url: str = "",
    source_type: str,
    artifact_receipt: dict[str, Any] | None = None,
    prompt: str = "",
    negative_prompt: str = "",
    prompt_version: int = 0,
) -> dict[str, Any]:
    if slot not in VALID_SLOTS:
        raise ValueError("storyboard_image_slot_invalid")
    if not _clean_text(file_id, 500) and not _clean_text(result_url, 1500):
        raise ValueError("storyboard_image_reference_missing")
    return {
        "slot": slot,
        "status": "ready",
        "image_id": f"scene_{scene_index}_{slot}",
        "file_id": _clean_text(file_id, 500),
        "result_url": _clean_text(result_url, 1500),
        "source_type": _clean_text(source_type, 80),
        "artifact_receipt": deepcopy(artifact_receipt or {}),
        "prompt_version": max(0, _safe_int(prompt_version, 0)),
        "prompt": _clean_text(prompt, 5000),
        "negative_prompt": _clean_text(negative_prompt, 2500),
    }


def assign_image(state: dict[str, Any], scene_index: int, slot: str, record: dict[str, Any]) -> dict[str, Any]:
    current = normalize_state(state)
    index = _safe_int(scene_index, 0)
    if index < 1 or index > current["scene_count"] or slot not in VALID_SLOTS:
        raise ValueError("storyboard_image_target_invalid")
    image = _empty_image(slot)
    image.update(dict(record or {}))
    image["slot"] = slot
    if not image.get("file_id") and not image.get("result_url"):
        raise ValueError("storyboard_image_reference_missing")
    image["status"] = "ready"
    image["image_id"] = str(image.get("image_id") or f"scene_{index}_{slot}")
    scene = dict(current["scenes"][index - 1])
    scene[f"{slot}_image"] = image
    if slot == "end" and scene.get("end_image_mode") == "none":
        scene["end_image_mode"] = "optional"
    current["scenes"][index - 1] = scene
    current["active_scene_index"] = index
    current["active_slot"] = slot
    return normalize_state(current)


def remove_image(state: dict[str, Any], scene_index: int, slot: str) -> dict[str, Any]:
    current = normalize_state(state)
    index = _safe_int(scene_index, 0)
    if index < 1 or index > current["scene_count"] or slot not in VALID_SLOTS:
        raise ValueError("storyboard_image_target_invalid")
    scene = dict(current["scenes"][index - 1])
    scene[f"{slot}_image"] = _empty_image(slot)
    current["scenes"][index - 1] = scene
    return normalize_state(current)


def move_image_to_scene(
    state: dict[str, Any],
    scene_index: int,
    target_scene_index: int,
    slot: str,
) -> dict[str, Any]:
    current = normalize_state(state)
    source_index = _safe_int(scene_index, 0)
    target_index = _safe_int(target_scene_index, 0)
    if (
        source_index < 1
        or source_index > current["scene_count"]
        or target_index < 1
        or target_index > current["scene_count"]
        or slot not in VALID_SLOTS
    ):
        raise ValueError("storyboard_image_target_invalid")
    if source_index == target_index:
        return current
    source_scene = dict(current["scenes"][source_index - 1])
    target_scene = dict(current["scenes"][target_index - 1])
    source_image = dict(source_scene.get(f"{slot}_image") or _empty_image(slot))
    target_image = dict(target_scene.get(f"{slot}_image") or _empty_image(slot))
    source_image["slot"] = slot
    target_image["slot"] = slot
    if target_image.get("status") == "ready":
        target_image["image_id"] = f"scene_{source_index}_{slot}"
    if source_image.get("status") == "ready":
        source_image["image_id"] = f"scene_{target_index}_{slot}"
    source_scene[f"{slot}_image"] = target_image
    target_scene[f"{slot}_image"] = source_image
    current["scenes"][source_index - 1] = source_scene
    current["scenes"][target_index - 1] = target_scene
    current["active_scene_index"] = target_index
    current["active_slot"] = slot
    return normalize_state(current)


def set_end_mode(state: dict[str, Any], scene_index: int, mode: str) -> dict[str, Any]:
    if mode not in {"optional", "required", "none"}:
        raise ValueError("storyboard_end_mode_invalid")
    current = normalize_state(state)
    index = _safe_int(scene_index, 0)
    if index < 1 or index > current["scene_count"]:
        raise ValueError("scene_index_out_of_range")
    current["scenes"][index - 1]["end_image_mode"] = mode
    if mode == "none":
        current["scenes"][index - 1]["end_image"] = _empty_image("end")
        current["scenes"][index - 1]["end_image"]["status"] = "not_used"
    return normalize_state(current)


def set_asset_mode(state: dict[str, Any], mode: str) -> dict[str, Any]:
    if mode not in {"start_only", "start_end"}:
        raise ValueError("storyboard_asset_mode_invalid")
    current = normalize_state(state)
    current["asset_mode"] = mode
    for scene in current["scenes"]:
        if mode == "start_end":
            scene["end_image_mode"] = "required"
        else:
            scene["end_image_mode"] = "none"
            scene["end_image"] = _empty_image("end")
            scene["end_image"]["status"] = "not_used"
    return normalize_state(current)


def image_targets(state: dict[str, Any], *, missing_only: bool = False) -> list[dict[str, Any]]:
    """Return the deterministic batch order: every start frame, then every end frame."""

    current = normalize_state(state)
    slots = ["start"]
    if current.get("asset_mode") == "start_end":
        slots.append("end")
    targets = []
    for slot in slots:
        for scene in current["scenes"]:
            image = dict(scene.get(f"{slot}_image") or {})
            if missing_only and image.get("status") == "ready":
                continue
            targets.append({
                "scene_index": int(scene["scene_index"]),
                "slot": slot,
                "status": str(image.get("status") or "missing"),
            })
    return targets


def next_missing_image_target(state: dict[str, Any]) -> dict[str, Any] | None:
    targets = image_targets(state, missing_only=True)
    return dict(targets[0]) if targets else None


def assign_next_image(state: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    target = next_missing_image_target(state)
    if not target:
        raise ValueError("storyboard_image_batch_complete")
    normalized_record = dict(record or {})
    normalized_record["slot"] = target["slot"]
    normalized_record["image_id"] = f"scene_{target['scene_index']}_{target['slot']}"
    return assign_image(
        state,
        int(target["scene_index"]),
        str(target["slot"]),
        normalized_record,
    )


def asset_summary(state: dict[str, Any]) -> dict[str, Any]:
    current = normalize_state(state)
    ready_start = sum(1 for scene in current["scenes"] if scene["start_image"].get("status") == "ready")
    ready_end = sum(1 for scene in current["scenes"] if scene["end_image"].get("status") == "ready")
    missing_required_end = [
        scene["scene_index"] for scene in current["scenes"]
        if scene.get("end_image_mode") == "required" and scene["end_image"].get("status") != "ready"
    ]
    return {
        "minimum_images": current["scene_count"],
        "maximum_images": current["scene_count"] * 2,
        "required_images": current["scene_count"] * (2 if current.get("asset_mode") == "start_end" else 1),
        "ready_images": ready_start + ready_end,
        "ready_start": ready_start,
        "ready_end": ready_end,
        "missing_start": [scene["scene_index"] for scene in current["scenes"] if scene["start_image"].get("status") != "ready"],
        "missing_required_end": missing_required_end,
        "ok": ready_start == current["scene_count"] and not missing_required_end,
    }


def image_prompt(state: dict[str, Any], scene_index: int, slot: str, variant: int = 0) -> dict[str, str]:
    current = normalize_state(state)
    index = _safe_int(scene_index, 0)
    if index < 1 or index > current["scene_count"] or slot not in VALID_SLOTS:
        raise ValueError("storyboard_image_target_invalid")
    scene = current["scenes"][index - 1]
    continuity = dict(current.get("continuity") or {})
    profile = dict(current.get("profile") or {})
    style = dict(current.get("style") or {})
    state_text = scene.get("start_state") if slot == "start" else scene.get("end_state")
    slot_copy = "khung mở đầu" if slot == "start" else "khung kết thúc"
    relation = (
        "thiết lập rõ trạng thái trước hành động"
        if slot == "start"
        else "cho thấy hành động đã hoàn tất và chuẩn bị nối cảnh kế tiếp"
    )
    prompt = (
        f"Storyboard cảnh {index}/{current['scene_count']}, {slot_copy}. "
        f"Ý tưởng chung: {current.get('content')}. Nội dung cảnh: {scene.get('content')}. "
        f"Trạng thái cần thể hiện: {state_text}. {relation}. "
        f"Tỉ lệ khung hình {current.get('aspect_ratio')}; profile {profile.get('label') or profile.get('key') or 'phù hợp nội dung'}; "
        f"phong cách {style.get('visual') or 'nhất quán điện ảnh'}; camera {scene.get('camera_motion')}; "
        f"giữ nguyên nhân vật, sản phẩm, bối cảnh, màu nhận diện và tỉ lệ từ continuity: {continuity or 'theo cảnh trước'}. "
        f"Biến thể bố cục {max(1, variant + 1)}; hình sạch, không chữ giả, không watermark."
    )
    negative = (
        "không đổi khuôn mặt, không đổi trang phục hoặc sản phẩm, không sai màu nhận diện, "
        "không méo hình, không thêm nhân vật hay thông tin chưa được cung cấp, không chữ giả, không watermark"
    )
    return {"prompt": _clean_text(prompt, 5000), "negative_prompt": negative}


def compile_video_prompts(state: dict[str, Any]) -> dict[str, Any]:
    current = normalize_state(state)
    if not asset_summary(current)["ok"]:
        raise ValueError("storyboard_assets_incomplete")
    for scene in current["scenes"]:
        start_image = scene["start_image"]
        end_image = scene["end_image"]
        end_copy = (
            f"Chuyển chính xác từ ảnh đầu {start_image.get('image_id')} tới ảnh cuối {end_image.get('image_id')}."
            if end_image.get("status") == "ready"
            else "Phát triển tự nhiên từ ảnh đầu và tự khép hành động, không tạo cú cắt cụt."
        )
        prompt = (
            f"Storyboard cảnh {scene['scene_index']}/{current['scene_count']}, {SCENE_SECONDS} giây, tỉ lệ {current.get('aspect_ratio')}. "
            f"Ý tưởng: {current.get('content')}. Nội dung cảnh: {scene.get('content')}. "
            f"Trạng thái đầu: {scene.get('start_state')}. Hành động chính: {scene.get('main_action')}. "
            f"Trạng thái cuối: {scene.get('end_state')}. Camera: {scene.get('camera_motion')}. "
            f"Chuyển động chủ thể: {scene.get('subject_motion')}. {end_copy} "
            "Giữ continuity nhân vật, sản phẩm, kiến trúc, màu sắc và hướng chuyển động; hoàn tất hành động trước khi nối cảnh."
        )
        scene["video_prompt_version"] = max(1, _safe_int(scene.get("video_prompt_version"), 0) + 1)
        scene["video_prompt"] = _clean_text(prompt, 6000)
        scene["video_negative_prompt"] = _clean_text(scene.get("negative_constraints"), 2500)
    return normalize_state(current)


def set_video_prompt(state: dict[str, Any], scene_index: int, prompt: str) -> dict[str, Any]:
    current = normalize_state(state)
    index = _safe_int(scene_index, 0)
    if index < 1 or index > current["scene_count"]:
        raise ValueError("scene_index_out_of_range")
    value = _clean_text(prompt, 6000)
    if not value:
        raise ValueError("video_prompt_missing")
    scene = current["scenes"][index - 1]
    scene["video_prompt"] = value
    scene["video_prompt_version"] = max(1, _safe_int(scene.get("video_prompt_version"), 0) + 1)
    return normalize_state(current)


def build_transitions(state: dict[str, Any], transition: str = "Cắt theo hành động") -> dict[str, Any]:
    current = normalize_state(state)
    current["transitions"] = [
        {
            "from_scene_id": f"scene_{index}",
            "to_scene_id": f"scene_{index + 1}",
            "transition": str(transition or "Cắt theo hành động"),
        }
        for index in range(1, current["scene_count"])
    ]
    current["transition_index"] = 1
    return normalize_state(current)


def set_transition(state: dict[str, Any], index: int, transition: str) -> dict[str, Any]:
    current = normalize_state(state)
    if not current["transitions"]:
        current = build_transitions(current)
    position = _safe_int(index, 0)
    if position < 1 or position > len(current["transitions"]):
        raise ValueError("transition_index_out_of_range")
    current["transitions"][position - 1]["transition"] = _clean_text(transition, 120)
    current["transition_index"] = position
    return normalize_state(current)


def required_capability(state: dict[str, Any]) -> str:
    current = normalize_state(state)
    return (
        "first_last_frame_video"
        if any(scene["end_image"].get("status") == "ready" for scene in current["scenes"])
        else "image_to_video"
    )


def build_manifest(state: dict[str, Any]) -> dict[str, Any]:
    current = normalize_state(state)
    summary = asset_summary(current)
    scenes = []
    for scene in current["scenes"]:
        scenes.append({
            "scene_id": scene["scene_id"],
            "scene_index": scene["scene_index"],
            "duration_seconds": SCENE_SECONDS,
            "content": scene.get("content"),
            "start_state": scene.get("start_state"),
            "main_action": scene.get("main_action"),
            "end_state": scene.get("end_state"),
            "camera_motion": scene.get("camera_motion"),
            "subject_motion": scene.get("subject_motion"),
            "negative_constraints": scene.get("negative_constraints"),
            "start_image_id": scene["start_image"].get("image_id"),
            "start_image_file_id": scene["start_image"].get("file_id"),
            "start_image_url": scene["start_image"].get("result_url"),
            "end_image_id": scene["end_image"].get("image_id") if scene["end_image"].get("status") == "ready" else None,
            "end_image_file_id": scene["end_image"].get("file_id") if scene["end_image"].get("status") == "ready" else None,
            "end_image_url": scene["end_image"].get("result_url") if scene["end_image"].get("status") == "ready" else None,
            "end_image_mode": str(scene.get("end_image_mode") or "optional"),
            "input_mode": (
                "first_last_frame_video"
                if scene["end_image"].get("status") == "ready"
                else "image_to_video"
            ),
            "start_image_prompt": scene["start_image"].get("prompt"),
            "start_image_negative_prompt": scene["start_image"].get("negative_prompt"),
            "end_image_prompt": scene["end_image"].get("prompt") if scene["end_image"].get("status") == "ready" else None,
            "end_image_negative_prompt": scene["end_image"].get("negative_prompt") if scene["end_image"].get("status") == "ready" else None,
            "source_type": {
                "start": scene["start_image"].get("source_type"),
                "end": scene["end_image"].get("source_type"),
            },
            "artifact_receipt": {
                "start": deepcopy(scene["start_image"].get("artifact_receipt") or {}),
                "end": deepcopy(scene["end_image"].get("artifact_receipt") or {}),
            },
            "prompt_version": scene.get("video_prompt_version"),
            "provider_prompt": scene.get("video_prompt"),
            "negative_prompt": scene.get("video_negative_prompt"),
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "job_type": "storyboard_to_video",
        "execution_owner": "owner_product_video",
        "route": "storyboard_to_video",
        "scene_count": current["scene_count"],
        "scene_duration_seconds": SCENE_SECONDS,
        "aspect_ratio": current.get("aspect_ratio"),
        "content": current.get("content"),
        "required_capability": required_capability(current),
        "asset_summary": summary,
        "scenes": scenes,
        "transitions": deepcopy(current.get("transitions") or []),
    }


def preflight(state: dict[str, Any]) -> dict[str, Any]:
    current = normalize_state(state)
    blockers = []
    if current["scene_count"] < MIN_SCENES:
        blockers.append("storyboard_scene_count_missing")
    if current.get("aspect_ratio") not in SUPPORTED_RATIOS:
        blockers.append("storyboard_aspect_ratio_missing")
    if not current.get("content"):
        blockers.append("storyboard_content_missing")
    if not current.get("reference_gate_complete"):
        blockers.append("storyboard_reference_image_missing")
    if not current.get("middle_complete"):
        blockers.append("storyboard_middle_incomplete")
    if any(not scene.get("content_approved") for scene in current["scenes"]):
        blockers.append("storyboard_scene_content_not_approved")
    summary = asset_summary(current)
    if summary["missing_start"]:
        blockers.append("storyboard_start_images_missing")
    if summary["missing_required_end"]:
        blockers.append("storyboard_required_end_images_missing")
    if any(not scene.get("video_prompt") for scene in current["scenes"]):
        blockers.append("storyboard_video_prompts_missing")
    if len(current.get("transitions") or []) != max(0, current["scene_count"] - 1):
        blockers.append("storyboard_transition_count_mismatch")
    if not current.get("addons_ready"):
        blockers.append("storyboard_addons_not_reviewed")
    manifest = build_manifest(current) if not blockers else {}
    return {
        "ok": not blockers,
        "blockers": blockers,
        "block_reason": blockers[0] if blockers else "",
        "required_capability": required_capability(current),
        "job_type": "storyboard_to_video",
        "execution_owner": "owner_product_video",
        "manifest": manifest,
        "side_effects": {
            "job": 0,
            "outbox": 0,
            "provider_calls": 0,
            "generated_files": 0,
            "wallet_mutations": 0,
            "xu_charged": 0,
        },
    }
