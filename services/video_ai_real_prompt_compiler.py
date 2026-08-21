"""Deterministic render contract for Video AI Real prompt/image products.

Creative selections are compiled into visual prompts. Dialogue, voices, music,
captions, sound effects and branding remain in a separate post-production plan.
This module is side-effect free and never calls a provider or mutates a wallet.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "video-ai-real-render-v1"
VISUAL_VERSION = "visual-prompt-v1"
POST_VERSION = "post-production-v1"


def _text(value: Any, fallback: str = "") -> str:
    return " ".join(str(value or fallback).strip().split())


def _unique(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        item = _text(value)
        if item and item not in result:
            result.append(item)
    return result


def _hash_payload(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _rows_by_id(rows: Iterable[Mapping[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {
        _text(row.get(key)): dict(row)
        for row in rows
        if isinstance(row, Mapping) and _text(row.get(key))
    }


def _entity_text(label: str, rows: list[dict[str, Any]], fields: tuple[str, ...]) -> str:
    if not rows:
        return f"{label}: tự động theo nội dung đã khóa"
    details: list[str] = []
    for index, row in enumerate(rows, 1):
        values = _unique(row.get(field) for field in fields)
        details.append(f"{label} {index}: " + "; ".join(values or [f"{label} {index}"]))
    return " | ".join(details)


def _scene_reference_ids(
    scene: Mapping[str, Any],
    *,
    characters: list[dict[str, Any]],
    location: dict[str, Any],
    products: list[dict[str, Any]],
    props: list[dict[str, Any]],
) -> list[str]:
    return _unique([
        *(scene.get("reference_asset_ids") or []),
        *(asset for row in characters for asset in row.get("reference_asset_ids") or []),
        *(location.get("reference_asset_ids") or []),
        *(asset for row in products for asset in row.get("reference_asset_ids") or []),
        *(asset for row in props for asset in row.get("reference_asset_ids") or []),
    ])


def _global_scene_references(
    state: Mapping[str, Any],
    scene: Mapping[str, Any],
) -> dict[str, list[str]]:
    scene_id = _text(scene.get("scene_id"))
    scene_index = max(1, int(scene.get("scene_index") or 1))
    by_role = {
        "visual_style_reference": [],
        "storyboard_frames": [],
    }
    unscoped_storyboard: list[str] = []
    for item in state.get("references") or []:
        if not isinstance(item, Mapping):
            continue
        role = _text(item.get("role"))
        if role not in by_role:
            continue
        allowed_scene_ids = {
            _text(value) for value in item.get("allowed_scene_ids") or []
        }
        if allowed_scene_ids and scene_id not in allowed_scene_ids:
            continue
        asset_id = _text(item.get("asset_id"))
        if not asset_id:
            continue
        if role == "storyboard_frames" and not allowed_scene_ids:
            unscoped_storyboard.append(asset_id)
        else:
            by_role[role].append(asset_id)
    if unscoped_storyboard:
        storyboard_index = min(scene_index - 1, len(unscoped_storyboard) - 1)
        by_role["storyboard_frames"].append(
            unscoped_storyboard[storyboard_index]
        )
    return {role: _unique(asset_ids) for role, asset_ids in by_role.items()}


def _visual_scene(
    state: Mapping[str, Any],
    scene: Mapping[str, Any],
    *,
    character_map: Mapping[str, dict[str, Any]],
    location_map: Mapping[str, dict[str, Any]],
    product_map: Mapping[str, dict[str, Any]],
    prop_map: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    content = dict(state.get("content") or {})
    brief = dict(content.get("approved_brief") or {})
    bible = dict(state.get("bible") or {})
    fmt = dict(state.get("format") or {})
    commercial = dict((state.get("legacy_compat") or {}).get("pilot_commercial") or {})

    characters = [
        deepcopy(character_map[item])
        for item in scene.get("character_ids") or []
        if item in character_map
    ]
    location = deepcopy(location_map.get(_text(scene.get("location_id"))) or {})
    products = [
        deepcopy(product_map[item])
        for item in scene.get("product_ids") or []
        if item in product_map
    ]
    props = [
        deepcopy(prop_map[item])
        for item in scene.get("prop_ids") or []
        if item in prop_map
    ]
    references = _scene_reference_ids(
        scene,
        characters=characters,
        location=location,
        products=products,
        props=props,
    )
    global_references = _global_scene_references(state, scene)
    references = _unique([
        *references,
        *global_references["visual_style_reference"],
        *global_references["storyboard_frames"],
    ])
    if _text(state.get("entry_mode")) == "image_video":
        references = _unique([
            *references,
            *(
                item.get("asset_id")
                for item in dict(state.get("source") or {}).get("assets") or []
                if isinstance(item, Mapping)
            ),
        ])

    scene_index = max(1, int(scene.get("scene_index") or 1))
    duration = max(1, int(scene.get("duration_target") or fmt.get("seconds_per_scene") or 8))
    ratio = _text(scene.get("ratio") or fmt.get("ratio"), "9:16")
    content_intent = _text(content.get("original_intent"), _text(brief.get("title"), "Nội dung đã khóa"))
    context_label = _text(commercial.get("context_label"), "Theo nội dung đã chọn")
    action = _text(
        scene.get("main_action") or scene.get("semantic_beat"),
        "Thực hiện trọn một hành động phù hợp nội dung",
    )
    raw_override = scene.get("prompt_override")
    override = str(raw_override) if raw_override is not None else ""
    override_present = bool(override.strip())
    raw_negative_override = scene.get("negative_prompt_override")
    negative_override = (
        str(raw_negative_override) if raw_negative_override is not None else ""
    )
    negative_override_present = bool(negative_override.strip())
    visual_direction = _unique([
        scene.get("framing") or scene.get("camera") or "Khung hình chân thật, chủ thể rõ",
        scene.get("movement") or "Chuyển động có chủ đích và kết thúc trọn vẹn",
        scene.get("lighting") or location.get("lighting") or "Ánh sáng tự nhiên, vật liệu trung thực",
        scene.get("mood") or location.get("mood") or "Cảm xúc phù hợp nội dung",
    ])
    enabled_continuity = [
        key
        for key, enabled in dict(bible.get("continuity") or {}).items()
        if bool(enabled)
    ]
    wardrobe = dict(scene.get("wardrobe_overrides") or {})

    prompt_parts = [
        f"Cảnh {scene_index}, tỉ lệ {ratio}, thời lượng {duration} giây",
        f"Nội dung và mục tiêu: {content_intent}",
        f"Ngữ cảnh triển khai: {context_label}",
        _entity_text("Nhân vật", characters, ("display_name", "gender", "description")),
        _entity_text(
            "Bối cảnh",
            [location] if location else [],
            ("name", "description", "indoor_outdoor", "time_of_day", "weather"),
        ),
        _entity_text("Sản phẩm", products, ("name", "category", "description", "logo_text_constraints")),
        _entity_text("Đạo cụ", props, ("name", "description")),
        f"Tình tiết chính: {_text(scene.get('semantic_beat'), action)}",
        f"Trạng thái mở đầu: {_text(scene.get('start_state'), 'Nối tiếp hợp lý từ cảnh trước')}",
        f"Hành động phải hoàn thành: {action}",
        f"Trạng thái kết cảnh: {_text(scene.get('completion_state'), 'Hành động hoàn tất rõ ràng')}",
        "Máy quay, chuyển động, ánh sáng và biểu cảm: " + "; ".join(visual_direction),
        "Giữ nhất quán: " + ", ".join(enabled_continuity or ["các yếu tố người dùng đã khóa"]),
    ]
    if wardrobe:
        prompt_parts.append(
            "Trang phục riêng trong cảnh: "
            + "; ".join(f"{key}={_text(value)}" for key, value in sorted(wardrobe.items()))
        )
    if references:
        prompt_parts.append("Dùng đúng các ảnh tham chiếu đã gắn cho nhận diện và bối cảnh; không tự thay thế chủ thể")
    if global_references["visual_style_reference"]:
        prompt_parts.append(
            "Dùng ảnh phong cách làm chuẩn cho bảng màu, ánh sáng, chất liệu và ngôn ngữ hình ảnh; "
            "không sao chép nhầm nhân vật hoặc sản phẩm từ ảnh phong cách"
        )
    if global_references["storyboard_frames"]:
        prompt_parts.append(
            "Dùng ảnh Storyboard làm chuẩn cho bố cục, vị trí chủ thể và diễn tiến hành động của cảnh"
        )
    prompt_parts.extend([
        "Một cảnh chỉ có một nhịp nội dung chính; hoàn tất hành động và chuyển động camera trước khi cắt",
        "Không chèn lời thoại, giọng đọc, phụ đề, nhạc, hiệu ứng âm thanh, logo hoặc watermark trong lần dựng hình",
    ])
    generated_visual_prompt = " | ".join(item for item in prompt_parts if item)
    generated_negative_prompt = (
        "sai nhận diện, đổi khuôn mặt, đổi trang phục ngoài chỉ dẫn, đổi hình dáng hoặc nhãn sản phẩm, "
        "biến dạng tay, thừa ngón, vật thể nhân đôi, chữ ngẫu nhiên, logo giả, watermark giả, "
        "chuyển động giật, hành động dang dở, cắt giữa chuyển động camera"
    )
    visual_prompt = override if override_present else generated_visual_prompt
    negative_prompt = (
        negative_override if negative_override_present else generated_negative_prompt
    )
    scene_payload = {
        "scene_id": _text(scene.get("scene_id"), f"scene_{scene_index:02d}"),
        "scene_index": scene_index,
        "duration_seconds": duration,
        "aspect_ratio": ratio,
        "visual_prompt": visual_prompt,
        "negative_prompt": negative_prompt,
        "reference_asset_ids": references,
        "transition_in": _text(scene.get("transition_in")),
        "transition_out": _text(scene.get("transition_out")),
        "user_override_applied": override_present,
        "negative_override_applied": negative_override_present,
    }
    scene_payload["visual_prompt_hash"] = _hash_payload(scene_payload)
    return scene_payload


def build_post_production_manifest(state: Mapping[str, Any]) -> dict[str, Any]:
    audio = dict(state.get("audio") or {})
    scenes = [dict(item) for item in state.get("scenes") or [] if isinstance(item, Mapping)]
    scene_ids = {_text(scene.get("scene_id")) for scene in scenes if _text(scene.get("scene_id"))}
    music_plan = dict(audio.get("music_plan") or {})
    music_scene_assignments = {
        _text(scene_id): deepcopy(dict(assignment))
        for scene_id, assignment in music_plan.items()
        if _text(audio.get("music_scope"), "none") == "per_scene"
        and _text(scene_id) in scene_ids
        and isinstance(assignment, Mapping)
    }
    payload = {
        "schema_version": POST_VERSION,
        "execute_after_visual_validation": True,
        "dialogue": deepcopy(list(audio.get("dialogue_segments") or [])),
        "voice_cast": deepcopy(dict(audio.get("voice_cast") or {})),
        "music": {
            "scope": _text(audio.get("music_scope"), "none"),
            "source": _text(audio.get("music_source"), "none"),
            "plan": deepcopy(music_plan),
            "scene_assignments": music_scene_assignments,
        },
        "subtitles": {"mode": _text(audio.get("subtitle_mode"), "none")},
        "dubbing": {"mode": _text(audio.get("dubbing_mode"), "none")},
        "sfx": {
            "mode": _text(audio.get("sfx_mode"), "none"),
            "plan": deepcopy(list(audio.get("sfx_plan") or [])),
            "scene_assignments": {
                _text(scene.get("scene_id")): deepcopy(list(scene.get("sfx_ids") or []))
                for scene in scenes
                if scene.get("sfx_ids")
            },
        },
        "ambient": {
            "plan": deepcopy(list(audio.get("ambient_plan") or [])),
            "scene_assignments": {
                _text(scene.get("scene_id")): _text(scene.get("ambient_id"))
                for scene in scenes
                if _text(scene.get("ambient_id"))
            },
        },
        "branding": deepcopy(dict(state.get("branding") or {})),
    }
    payload["post_hash"] = _hash_payload(payload)
    return payload


def compile_render_contract(state: Mapping[str, Any]) -> dict[str, Any]:
    if _text(state.get("parent_product")) != "video_ai_real":
        raise ValueError("video_ai_real_prompt_contract_required")
    if _text(state.get("entry_mode")) not in {"prompt_video", "image_video"}:
        raise ValueError("video_ai_real_prompt_contract_required")
    scenes = [dict(item) for item in state.get("scenes") or [] if isinstance(item, Mapping)]
    if not scenes:
        raise ValueError("scene_plan_missing")

    bible = dict(state.get("bible") or {})
    character_map = _rows_by_id(bible.get("characters") or [], "character_id")
    location_map = _rows_by_id(bible.get("locations") or [], "location_id")
    product_map = _rows_by_id(bible.get("products") or [], "product_id")
    prop_map = _rows_by_id(bible.get("props") or [], "prop_id")
    scene_rows = [
        _visual_scene(
            state,
            scene,
            character_map=character_map,
            location_map=location_map,
            product_map=product_map,
            prop_map=prop_map,
        )
        for scene in scenes
    ]
    fmt = dict(state.get("format") or {})
    content = dict(state.get("content") or {})
    visual = {
        "schema_version": VISUAL_VERSION,
        "entry_mode": _text(state.get("entry_mode")),
        "profile_id": _text(content.get("profile_id"), "general"),
        "content_revision": max(0, int(content.get("revision") or 0)),
        "aspect_ratio": _text(fmt.get("ratio"), "9:16"),
        "seconds_per_scene": max(1, int(fmt.get("seconds_per_scene") or 8)),
        "scene_count": len(scene_rows),
        "scenes": scene_rows,
    }
    visual["visual_hash"] = _hash_payload(visual)
    post = build_post_production_manifest(state)
    contract = {
        "schema_version": SCHEMA_VERSION,
        "visual": visual,
        "post_production": post,
        "contract_hash": _hash_payload({"visual": visual, "post_production": post}),
        "provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }
    return contract
