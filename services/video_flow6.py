"""Canonical public Video intake and execution-route contract.

This module is deliberately provider-free.  It owns the shared planning
context, asset gates, suggestion paging, route selection and the preflight
truth used before an invoice is opened.  Rendering, delivery and wallet
mutation remain with their established owners.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from services import video_flow7


MIN_SCENES = 1
MAX_SCENES = 20
SCENE_SECONDS = 8
SUPPORTED_RATIOS = frozenset({"9:16", "16:9", "1:1", "4:5"})
CONTENT_MODES = frozenset({"manual", "suggestions"})

FLOW_KIND_BY_PRODUCT = {
    **video_flow7.PRODUCT_KIND_BY_ID,
    "frame_video_local": "frame_video",
}

FLOW_SPECS = {
    "ai_real": {
        "asset_requirement": "optional",
        "default_content_mode": "manual",
        "input_mode": "text_or_reference",
    },
    "idea_video": {
        "asset_requirement": "optional",
        "default_content_mode": "suggestions",
        "input_mode": "idea_preset_or_text",
    },
    "trend_video": {
        "asset_requirement": "optional",
        "default_content_mode": "suggestions",
        "input_mode": "sourced_trend_or_named_sample",
    },
    "script_to_video": {
        "asset_requirement": "optional",
        "default_content_mode": "manual",
        "input_mode": "confirmed_script_scene_plan",
    },
    "frame_video": {
        "asset_requirement": "images_required",
        "default_content_mode": "manual",
        "input_mode": "ordered_images",
    },
    "storyboard": {
        "asset_requirement": "images_required",
        "default_content_mode": "manual",
        "input_mode": "storyboard_images",
    },
    "self_shot": {
        "asset_requirement": "video_required",
        "default_content_mode": "manual",
        "input_mode": "source_video",
    },
    "long_series": {
        "asset_requirement": "series_dependent",
        "default_content_mode": "manual",
        "input_mode": "series_bible",
    },
}

EXECUTION_ROUTES = {
    "ai_real": {
        "job_type": "product_video",
        "execution_owner": "owner_product_video",
        "provider_family": "product_video_catalog",
        "local_renderer": "",
        "capability_requirements": ["text_to_video_or_scene_video", "per_scene_8s", "final_mp4"],
        "fallback": "next_contract_valid_product_video_candidate",
    },
    "idea_video": {
        "job_type": "product_video",
        "execution_owner": "owner_product_video",
        "provider_family": "product_video_catalog",
        "local_renderer": "",
        "capability_requirements": ["text_to_video_or_scene_video", "per_scene_8s", "final_mp4"],
        "fallback": "next_contract_valid_product_video_candidate",
    },
    "trend_video": {
        "job_type": "product_video",
        "execution_owner": "owner_product_video",
        "provider_family": "trend_preset_to_product_video",
        "local_renderer": "",
        "capability_requirements": ["trend_or_sample_source", "per_scene_8s", "final_mp4"],
        "fallback": "next_contract_valid_product_video_candidate",
    },
    "script_to_video": {
        "job_type": "product_video",
        "execution_owner": "owner_product_video",
        "provider_family": "parsed_scene_plan_to_product_video",
        "local_renderer": "",
        "capability_requirements": ["parsed_scene_plan", "per_scene_8s", "final_mp4"],
        "fallback": "next_contract_valid_product_video_candidate",
    },
    "frame_video": {
        "job_type": "frame_video_local",
        "mapped_job_type": "frame_video_render",
        "execution_owner": "local_worker",
        "provider_family": "",
        "local_renderer": "ffmpeg",
        "capability_requirements": ["ordered_images", "ffmpeg", "ffprobe", "final_mp4"],
        "fallback": "block_no_charge",
    },
    "frame_video_ai": {
        "job_type": "frame_video_ai",
        "execution_owner": "owner_product_video",
        "provider_family": "product_video_catalog",
        "local_renderer": "ffmpeg",
        "capability_requirements": ["image_to_video", "ordered_images", "final_mp4"],
        "fallback": "frame_video_local",
    },
    "storyboard": {
        "job_type": "storyboard_to_video",
        "execution_owner": "owner_product_video",
        "provider_family": "product_video_catalog",
        "local_renderer": "ffmpeg",
        "capability_requirements": ["image_to_video", "scene_image_mapping", "final_mp4"],
        "fallback": "block_no_charge",
    },
    "self_shot": {
        "job_type": "self_shot_scene_change",
        "execution_owner": "owner_product_video",
        "provider_family": "product_video_catalog",
        "local_renderer": "ffmpeg",
        "capability_requirements": ["video_to_video", "source_video_probe", "final_mp4"],
        "fallback": "block_no_charge",
    },
    "long_series": {
        "job_type": "long_series_project",
        "execution_owner": "owner_long_video",
        "provider_family": "long_series_episode_queue",
        "local_renderer": "",
        "capability_requirements": ["episode_queue", "continuity_store", "final_mp4"],
        "fallback": "block_no_charge",
    },
}

_CONTENT_PATTERNS = (
    ("Mở bằng vấn đề thật", "đặt vấn đề, chứng minh nguyên nhân và khép bằng kết quả rõ"),
    ("Mở bằng kết quả nổi bật", "cho xem thành quả trước rồi kể lại quá trình tạo nên thành quả"),
    ("Mở bằng khoảnh khắc đời thường", "đưa chủ thể vào tình huống gần gũi và kết thúc tự nhiên"),
    ("Mở bằng câu hỏi ngắn", "mỗi cảnh trả lời một phần và cảnh cuối chốt điều cần nhớ"),
    ("Mở bằng tương phản trước-sau", "giữ cùng chủ thể để thay đổi được nhìn thấy rõ ràng"),
    ("Mở bằng chi tiết cận cảnh", "mở rộng dần sang bối cảnh, công dụng và kết luận"),
    ("Mở bằng một hành động", "theo hành động đến khi hoàn tất rồi nối sang ý kế tiếp"),
    ("Mở bằng phản ứng của nhân vật", "giải thích nguyên nhân, diễn biến và trạng thái cuối"),
    ("Mở bằng không gian", "dẫn người xem qua từng điểm nổi bật theo một hướng liên tục"),
    ("Mở bằng lời hứa giá trị", "chứng minh lời hứa bằng hình ảnh và kết bằng bằng chứng"),
    ("Mở bằng sai lầm thường gặp", "chỉ ra hậu quả, cách sửa và kết quả sau khi sửa"),
    ("Mở bằng ba bước rõ ràng", "phân bổ các bước theo số cảnh mà không cắt giữa hành động"),
    ("Mở bằng một lựa chọn khó", "so sánh ngắn, thử nghiệm và chốt lựa chọn có căn cứ"),
    ("Mở bằng góc nhìn người dùng", "đi từ nhu cầu, trải nghiệm đến nhận xét cuối"),
    ("Mở bằng câu chuyện nguồn gốc", "nối quá khứ, hiện tại và giá trị còn lại"),
    ("Mở bằng thử thách", "thiết lập mục tiêu, thực hiện và xác nhận kết quả"),
    ("Mở bằng con số đáng chú ý", "giải thích ý nghĩa, minh họa và nêu giới hạn của số liệu"),
    ("Mở bằng một ngày sử dụng", "đi theo trình tự thời gian và kết bằng thay đổi thực tế"),
    ("Mở bằng lời nhận xét", "đưa bằng chứng trực quan để củng cố nhận xét"),
    ("Mở bằng khung hình kết", "quay lại nguyên nhân và diễn biến rồi trở về điểm kết trọn vẹn"),
)


def flow_kind_for_product(product_id: str) -> str:
    return FLOW_KIND_BY_PRODUCT.get(str(product_id or "").strip(), "ai_real")


def flow_spec(flow_kind: str) -> dict[str, Any]:
    return deepcopy(FLOW_SPECS.get(str(flow_kind or ""), FLOW_SPECS["ai_real"]))


def new_context(
    *,
    product_id: str,
    content_mode: str = "",
    source_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    flow_kind = flow_kind_for_product(product_id)
    spec = flow_spec(flow_kind)
    mode = str(content_mode or "").strip()
    if mode not in CONTENT_MODES:
        mode = ""
    return {
        "flow_kind": flow_kind,
        "product_id": str(product_id or ""),
        "content_mode": mode,
        "scene_count": 0,
        "aspect_ratio": "",
        "asset_requirement": str(spec["asset_requirement"]),
        "primary_profile_key": "",
        "content_choice": {},
        "asset_manifest": {"items": [], "source_video": {}, "probe": {}},
        "character_config": {},
        "style_config": {},
        "audio_config": {},
        "scene_plan": {},
        "prompt_plan": {},
        "execution_route": {},
        "return_stack": [],
        "source_fields": dict(source_fields or {}),
        "suggestion_page": 1,
        "suggestion_seen_ids": [],
        "preflight": {},
        "delivery": {"artifact_message_id": 0, "receipt_key": "", "receipt_recorded": False},
    }


def normalize_context(value: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(value or {})
    product_id = str(raw.get("product_id") or raw.get("source_product_id") or raw.get("product_type") or "video_ai_real")
    base = new_context(
        product_id=product_id,
        content_mode=str(raw.get("content_mode") or ""),
        source_fields=dict(raw.get("source_fields") or {}),
    )
    base.update(raw)
    flow_kind = flow_kind_for_product(product_id)
    base["flow_kind"] = flow_kind
    base["product_id"] = product_id
    base["asset_requirement"] = str(flow_spec(flow_kind)["asset_requirement"])
    if str(base.get("content_mode") or "") not in CONTENT_MODES:
        base["content_mode"] = ""
    try:
        base["scene_count"] = max(0, min(MAX_SCENES, int(base.get("scene_count") or 0)))
    except (TypeError, ValueError):
        base["scene_count"] = 0
    ratio = str(base.get("aspect_ratio") or "")
    base["aspect_ratio"] = ratio if ratio in SUPPORTED_RATIOS else ""
    base["primary_profile_key"] = str(
        base.get("primary_profile_key") or base.get("primary_profile") or base.get("technical_profile") or ""
    )
    base["content_choice"] = dict(base.get("content_choice") or base.get("selected_suggestion") or {})
    manifest = dict(base.get("asset_manifest") or {})
    # Storyboard keeps one required opening frame and an optional closing
    # frame per scene.  The shared 20-scene limit must therefore not discard
    # the second frame of a 20-scene board.
    item_limit = MAX_SCENES * 2 if flow_kind == "storyboard" else MAX_SCENES
    manifest["items"] = [
        dict(item) for item in manifest.get("items") or [] if isinstance(item, dict)
    ][:item_limit]
    manifest["source_video"] = dict(manifest.get("source_video") or {})
    manifest["probe"] = dict(manifest.get("probe") or {})
    base["asset_manifest"] = manifest
    for key in ("character_config", "style_config", "audio_config", "scene_plan", "prompt_plan", "execution_route", "preflight", "delivery"):
        base[key] = dict(base.get(key) or {})
    base["return_stack"] = [str(item) for item in base.get("return_stack") or [] if str(item)][-40:]
    base["suggestion_page"] = max(1, min(4, int(base.get("suggestion_page") or 1)))
    base["suggestion_seen_ids"] = [str(item) for item in base.get("suggestion_seen_ids") or [] if str(item)][-20:]
    return base


def context_from_scene_state(state: dict[str, Any] | None) -> dict[str, Any]:
    source = dict(state or {})
    context = dict(source.get("video_flow_context") or {})
    source_fields = dict(source.get("source_fields") or context.get("source_fields") or {})
    context.update({
        "product_id": str(source.get("source_product_id") or source.get("product_type") or context.get("product_id") or "video_ai_real"),
        "content_mode": str(source.get("content_mode") or context.get("content_mode") or ""),
        "scene_count": source.get("scene_count", context.get("scene_count", 0)),
        "aspect_ratio": str(source.get("aspect_ratio") or context.get("aspect_ratio") or ""),
        "primary_profile_key": str(source.get("primary_profile_key") or source.get("primary_profile") or context.get("primary_profile_key") or ""),
        "content_choice": dict(source.get("content_choice") or source.get("selected_suggestion") or context.get("content_choice") or {}),
        "character_config": dict(source.get("character_config") or context.get("character_config") or {}),
        "style_config": dict(source.get("creative_controls") or context.get("style_config") or {}),
        "audio_config": dict(source.get("postproduction_addons") or context.get("audio_config") or {}),
        "scene_plan": dict(source.get("scene_plan") or context.get("scene_plan") or {}),
        "prompt_plan": {
            "image": dict(source.get("image_prompt_versions") or {}),
            "video": dict(source.get("video_prompt_versions") or {}),
        },
        "idea_preset_id": source.get("idea_preset_id") or context.get("idea_preset_id") or "",
        "script_text": str(source.get("script_text") or source.get("manual_script_raw") or context.get("script_text") or ""),
        "scene_count_confirmed": bool(source.get("scene_count_confirmed") or context.get("scene_count_confirmed")),
        "trend_source": dict(
            source.get("selected_trend_source")
            or source.get("trend_source")
            or source_fields.get("selected_trend_source")
            or source_fields.get("trend_source")
            or context.get("trend_source")
            or {}
        ),
        "required_capability": str(
            source.get("required_capability")
            or context.get("required_capability")
            or ""
        ),
        "storyboard_manifest": dict(
            source.get("storyboard_manifest")
            or context.get("storyboard_manifest")
            or {}
        ),
        "source_fields": source_fields,
        "transitions": list(
            source.get("transitions")
            or source.get("transition_plan")
            or context.get("transitions")
            or []
        ),
        "return_stack": list(source.get("history") or context.get("return_stack") or []),
    })
    assets = dict(source.get("reference_assets") or source.get("assets") or {})
    manifest = dict(context.get("asset_manifest") or {})
    storyboard_manifest = dict(
        assets.get("storyboard_manifest")
        or context.get("storyboard_manifest")
        or source.get("storyboard_manifest")
        or {}
    )
    if storyboard_manifest:
        context["storyboard_manifest"] = storyboard_manifest
    if assets:
        asset_items = [dict(item) for item in assets.get("items") or [] if isinstance(item, dict)]
        manifest["items"] = asset_items
        source_video = str(assets.get("source_media_ref") or "")
        if not source_video:
            source_video = next(
                (
                    str(item.get("file_id") or item.get("path") or "")
                    for item in asset_items
                    if str(item.get("media_kind") or "").lower() in {"video", "animation"}
                ),
                "",
            )
        if source_video:
            manifest["source_video"] = {"file_id": source_video}
        refs = [str(item) for item in assets.get("source_media_refs") or [] if str(item)]
        if refs and not manifest.get("items"):
            manifest["items"] = [{"file_id": item, "media_kind": "image"} for item in refs]
    video_item = next(
        (
            item for item in manifest.get("items") or []
            if str(item.get("media_kind") or "").lower() in {"video", "animation"}
        ),
        {},
    )
    if video_item:
        manifest["source_video"] = {
            "file_id": str(video_item.get("file_id") or manifest.get("source_video", {}).get("file_id") or ""),
            "file_unique_id": str(video_item.get("file_unique_id") or ""),
        }
        manifest["probe"] = {
            "duration_seconds": float(video_item.get("duration_seconds") or 0),
            "width": int(video_item.get("width") or 0),
            "height": int(video_item.get("height") or 0),
            "format": str(video_item.get("mime_type") or video_item.get("file_name") or ""),
            "audio_streams": int(video_item.get("audio_streams") or 0),
        }
    context["asset_manifest"] = manifest
    context["asset_items"] = list(manifest.get("items") or [])
    context["source_video"] = dict(manifest.get("source_video") or {})
    context["source_probe"] = dict(manifest.get("probe") or {})
    return normalize_context(context)


def sync_scene_state(state: dict[str, Any]) -> dict[str, Any]:
    updated = dict(state or {})
    context = context_from_scene_state(updated)
    updated.update({
        "flow_kind": context["flow_kind"],
        "content_mode": context["content_mode"],
        "asset_requirement": context["asset_requirement"],
        "primary_profile_key": context["primary_profile_key"],
        "content_choice": dict(context["content_choice"]),
        "asset_manifest": deepcopy(context["asset_manifest"]),
        "execution_route": deepcopy(context["execution_route"]),
        "video_flow_context": context,
    })
    return updated


def asset_gate_status(value: dict[str, Any] | None) -> dict[str, Any]:
    context = normalize_context(value)
    requirement = str(context["asset_requirement"])
    manifest = dict(context["asset_manifest"])
    items = [
        item for item in manifest.get("items") or []
        if str(item.get("file_id") or item.get("path") or item.get("result_url") or "").strip()
    ]
    source_video = dict(manifest.get("source_video") or {})
    if requirement in {"optional", "preset_dependent", "script_dependent", "series_dependent"}:
        return {"ok": True, "requirement": requirement, "required": 0, "received": len(items), "blocker": ""}
    if requirement == "images_required":
        if str(context.get("flow_kind") or "") == "storyboard":
            storyboard_manifest = dict(context.get("storyboard_manifest") or {})
            def scene_index_of(item: dict[str, Any]) -> int:
                try:
                    return int(item.get("scene_index") or 0)
                except (TypeError, ValueError):
                    return 0

            manifest_scenes = {
                scene_index_of(item): dict(item)
                for item in storyboard_manifest.get("scenes") or []
                if isinstance(item, dict) and scene_index_of(item) > 0
            }
            by_scene_slot = {
                (scene_index_of(item), str(item.get("slot") or "start")): item
                for item in items
                if scene_index_of(item) > 0
            }

            def ready(item: dict[str, Any] | None) -> bool:
                current_item = dict(item or {})
                return bool(
                    str(
                        current_item.get("file_id")
                        or current_item.get("path")
                        or current_item.get("result_url")
                        or ""
                    ).strip()
                )

            scene_count = max(1, int(context.get("scene_count") or 0))
            missing_start = [
                scene_index
                for scene_index in range(1, scene_count + 1)
                if not ready(by_scene_slot.get((scene_index, "start")))
            ]
            missing_required_end = [
                scene_index
                for scene_index in range(1, scene_count + 1)
                if str(manifest_scenes.get(scene_index, {}).get("end_image_mode") or "optional") == "required"
                and not ready(by_scene_slot.get((scene_index, "end")))
            ]
            mapped = all(
                ready(by_scene_slot.get((scene_index, "start")))
                for scene_index in range(1, scene_count + 1)
            )
            received = sum(1 for item in items if ready(item))
            blockers = []
            if missing_start:
                blockers.append("storyboard_start_images_missing")
            if missing_required_end:
                blockers.append("storyboard_required_end_images_missing")
            if not mapped:
                blockers.append("storyboard_scene_asset_mapping_incomplete")
            return {
                "ok": not blockers,
                "requirement": requirement,
                "required": scene_count + len(missing_required_end),
                "received": received,
                "mapped_scene_count": scene_count - len(missing_start),
                "missing_start": missing_start,
                "missing_required_end": missing_required_end,
                "blocker": blockers[0] if blockers else "",
                "blockers": blockers,
            }
        required = max(1, int(context.get("scene_count") or 0))
        image_items = [
            item
            for item in items
            if str(item.get("media_kind") or "image").lower() in {"image", "photo", "storyboard"}
        ]
        received = len(image_items)
        indexed = {
            int(item.get("scene_index") or 0)
            for item in image_items
            if str(item.get("scene_index") or "").isdigit() and int(item.get("scene_index") or 0) > 0
        }
        mapped = not indexed or all(scene_index in indexed for scene_index in range(1, required + 1))
        return {
            "ok": received >= required and mapped,
            "requirement": requirement,
            "required": required,
            "received": received,
            "mapped_scene_count": len(indexed),
            "blocker": "" if received >= required and mapped else (
                "required_scene_images_missing" if received < required else "scene_image_mapping_incomplete"
            ),
        }
    has_video = bool(str(source_video.get("file_id") or source_video.get("path") or ""))
    return {
        "ok": has_video,
        "requirement": requirement,
        "required": 1,
        "received": 1 if has_video else 0,
        "blocker": "" if has_video else "source_video_missing",
    }


def next_after_ratio(value: dict[str, Any] | None) -> str:
    return "technical_profile" if asset_gate_status(value)["requirement"] == "optional" else "asset_gate"


def content_suggestion_catalog(value: dict[str, Any] | None, *, profile_label: str = "") -> list[dict[str, Any]]:
    context = normalize_context(value)
    profile = str(profile_label or context.get("primary_profile_key") or "profile đã chọn")
    count = max(1, int(context.get("scene_count") or 1))
    ratio = str(context.get("aspect_ratio") or "9:16")
    flow_kind = str(context.get("flow_kind") or "ai_real")
    asset_status = asset_gate_status(context)
    character = dict(context.get("character_config") or {})
    character_note = str(character.get("description") or character.get("mode") or "chủ thể phù hợp nội dung")
    rows = []
    for index, (hook, structure) in enumerate(_CONTENT_PATTERNS, 1):
        suggestion_id = f"{context['primary_profile_key'] or 'profile'}:{index:02d}"
        rows.append({
            "id": suggestion_id,
            "index": index,
            "title": hook,
            "hook": f"{hook}, bám đúng {profile}.",
            "concept": (
                f"Dùng {count} cảnh, tỉ lệ {ratio}, loại {flow_kind}; {structure}. "
                f"Giữ {character_note} nhất quán."
            ),
            "flow": (
                f"Phân bổ đúng {count} ý/cảnh trọn vẹn; trạng thái cuối cảnh trước nối tự nhiên sang cảnh sau. "
                f"Tài nguyên hiện có {asset_status['received']}/{asset_status['required']}."
            ),
            "reason": f"Khớp profile {profile}, số cảnh {count} và tỉ lệ {ratio}.",
        })
    return rows


def suggestion_page(value: dict[str, Any] | None, *, page: int | None = None, profile_label: str = "") -> list[dict[str, Any]]:
    context = normalize_context(value)
    page_number = max(1, min(4, int(page or context.get("suggestion_page") or 1)))
    start = (page_number - 1) * 5
    return content_suggestion_catalog(context, profile_label=profile_label)[start:start + 5]


def rotate_suggestion_page(value: dict[str, Any] | None) -> dict[str, Any]:
    context = normalize_context(value)
    current = int(context.get("suggestion_page") or 1)
    page_items = suggestion_page(context, page=current)
    seen = list(context.get("suggestion_seen_ids") or [])
    for item in page_items:
        item_id = str(item.get("id") or "")
        if item_id and item_id not in seen:
            seen.append(item_id)
    context["suggestion_seen_ids"] = seen[-20:]
    context["suggestion_page"] = 1 if current >= 4 else current + 1
    return context


def select_content(value: dict[str, Any] | None, selection: int | dict[str, Any]) -> dict[str, Any]:
    context = normalize_context(value)
    if isinstance(selection, dict):
        chosen = dict(selection)
    else:
        page = suggestion_page(context)
        index = int(selection or 0)
        if index < 1 or index > len(page):
            return context
        chosen = dict(page[index - 1])
    context["content_choice"] = chosen
    return context


def execution_route_for(value: dict[str, Any] | None, *, prefer_ai_motion: bool = False, ai_motion_available: bool = False) -> dict[str, Any]:
    context = normalize_context(value)
    route_key = str(context["flow_kind"])
    if route_key == "frame_video" and prefer_ai_motion and ai_motion_available:
        route_key = "frame_video_ai"
    route = deepcopy(EXECUTION_ROUTES[route_key])
    route.update({
        "flow_kind": str(context["flow_kind"]),
        "input_mode": str(flow_spec(context["flow_kind"])["input_mode"]),
        "required_assets": str(context["asset_requirement"]),
        "preflight": "required_before_invoice",
        "delivery_contract": "valid_mp4_and_telegram_artifact_message_id",
        "charge_contract": "charge_once_after_successful_delivery_receipt",
    })
    if route_key == "storyboard":
        capability = str(context.get("required_capability") or "image_to_video")
        route["required_capability"] = capability
        route["capability_requirements"] = [
            capability,
            "scene_image_mapping",
            "final_mp4",
        ]
    return route


def preflight(
    value: dict[str, Any] | None,
    *,
    package_available: bool,
    engine_ready: bool,
    worker_ready: bool,
    capability_ready: bool,
    duration_seconds: int | None = None,
    resolution_valid: bool = True,
) -> dict[str, Any]:
    context = normalize_context(value)
    route = execution_route_for(context)
    blockers: list[str] = []
    if not context.get("content_mode"):
        blockers.append("content_mode_missing")
    if not (MIN_SCENES <= int(context.get("scene_count") or 0) <= MAX_SCENES):
        blockers.append("scene_count_invalid")
    if str(context.get("aspect_ratio") or "") not in SUPPORTED_RATIOS:
        blockers.append("aspect_ratio_invalid")
    gate = asset_gate_status(context)
    if not gate["ok"]:
        blockers.append(str(gate["blocker"]))
    flow_kind = str(context.get("flow_kind") or "ai_real")
    if flow_kind == "ai_real":
        if not str(context.get("primary_profile_key") or ""):
            blockers.append("primary_profile_missing")
        if not dict(context.get("content_choice") or {}):
            blockers.append("content_choice_missing")
    elif flow_kind == "idea_video":
        if not str(context.get("idea_preset_id") or ""):
            blockers.append("idea_preset_missing")
    elif flow_kind == "script_to_video":
        if not str(context.get("script_text") or "").strip():
            blockers.append("script_missing")
        if not bool(context.get("scene_count_confirmed")):
            blockers.append("script_scene_count_not_confirmed")
    elif flow_kind == "storyboard":
        transitions = list(context.get("transitions") or [])
        if len(transitions) != max(0, int(context.get("scene_count") or 0) - 1):
            blockers.append("storyboard_transition_count_invalid")
    elif flow_kind == "self_shot":
        source_probe = dict(context.get("source_probe") or {})
        if not (
            float(source_probe.get("duration_seconds") or 0) > 0
            and int(source_probe.get("width") or 0) > 0
            and int(source_probe.get("height") or 0) > 0
            and str(source_probe.get("format") or "").strip()
        ):
            blockers.append("source_video_probe_missing")
    elif flow_kind == "trend_video":
        trend_source = dict(context.get("trend_source") or {})
        if not (
            (trend_source.get("source_url") and trend_source.get("observed_at"))
            or trend_source.get("sample_preset")
            or trend_source.get("source_type") == "user_topic"
        ):
            blockers.append("trend_source_or_sample_missing")
    elif flow_kind == "long_series":
        blockers.append("long_series_public_not_ready")
    if not package_available:
        blockers.append("package_unavailable")
    if not engine_ready:
        blockers.append("execution_owner_unavailable")
    if not worker_ready:
        blockers.append("worker_runtime_unavailable")
    if not capability_ready:
        blockers.append("required_capability_unavailable")
    expected_duration = int(context.get("scene_count") or 0) * SCENE_SECONDS
    actual_duration = expected_duration if duration_seconds is None else int(duration_seconds or 0)
    if actual_duration <= 0:
        blockers.append("duration_invalid")
    if not resolution_valid:
        blockers.append("resolution_invalid")
    result = {
        "ok": not blockers,
        "blockers": blockers,
        "blocker": blockers[0] if blockers else "",
        "route": route,
        "scene_count": int(context.get("scene_count") or 0),
        "duration_seconds": actual_duration,
        "aspect_ratio": str(context.get("aspect_ratio") or ""),
        "asset_gate": gate,
        "side_effects": {
            "job": 0,
            "outbox": 0,
            "invoice": 0,
            "provider_calls": 0,
            "rendered_files": 0,
            "wallet_mutations": 0,
            "xu_charged": 0,
        },
    }
    return result


def record_delivery(value: dict[str, Any] | None, *, artifact_message_id: int, receipt_key: str) -> dict[str, Any]:
    context = normalize_context(value)
    message_id = int(artifact_message_id or 0)
    key = str(receipt_key or "").strip()
    if message_id <= 0 or not key:
        raise ValueError("valid_telegram_delivery_receipt_required")
    delivery = dict(context.get("delivery") or {})
    if delivery.get("receipt_recorded"):
        if int(delivery.get("artifact_message_id") or 0) != message_id or str(delivery.get("receipt_key") or "") != key:
            raise ValueError("delivery_receipt_already_recorded")
        return context
    delivery.update({
        "artifact_message_id": message_id,
        "receipt_key": key,
        "receipt_recorded": True,
    })
    context["delivery"] = delivery
    return context


def charge_allowed(value: dict[str, Any] | None) -> bool:
    delivery = dict(normalize_context(value).get("delivery") or {})
    return bool(
        delivery.get("receipt_recorded")
        and int(delivery.get("artifact_message_id") or 0) > 0
        and str(delivery.get("receipt_key") or "")
    )
