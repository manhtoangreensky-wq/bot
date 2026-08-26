"""Distinct public Video product contracts for FLOW7.

The public products deliberately keep separate step graphs.  This module only
shares the small pieces that are genuinely common: keyboard shape, suggestions,
preflight truth, execution ownership and delivery-before-charge policy.  It is
provider-free and has no database, wallet or filesystem side effects.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import re
from typing import Any, Iterable

from services import video_script_product


MIN_SCENES = 1
MAX_SCENES = 20
SCENE_SECONDS = 8
SUPPORTED_RATIOS = frozenset({"9:16", "16:9", "1:1", "4:5"})
VIDEO_DOCUMENT_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".webm"})


def video_document_is_supported(mime_type: str, file_name: str) -> bool:
    """Recognize Telegram video documents before the bounded media probe."""

    mime = str(mime_type or "").strip().casefold().split(";", 1)[0]
    if mime.startswith("video/"):
        return True
    if mime.startswith(("image/", "audio/", "text/")) or mime == "application/pdf":
        return False
    name = str(file_name or "").strip().casefold()
    suffix = f".{name.rsplit('.', 1)[-1]}" if "." in name else ""
    return suffix in VIDEO_DOCUMENT_EXTENSIONS and (
        not mime or mime == "application/octet-stream" or mime.startswith("application/")
    )

PRODUCT_KIND_BY_ID = {
    "video_ai_real": "ai_real",
    "video_reference": "ai_real",
    "motion_prompt": "ai_real",
    "video_idea": "idea_video",
    "script_image_video": "script_to_video",
    "storyboard_prompt": "storyboard",
    "self_shot_scene_change": "self_shot",
    "self_shot_cinematic_transform": "self_shot_cinematic",
    "multi_scene_film": "long_series",
    "video_trend": "trend_video",
}

PRODUCT_SPECS = {
    "ai_real": {
        "sequence": (
            "scene_count", "aspect_ratio", "ai_input_type", "content_source",
            "technical_profile_if_selected", "content_choice", "character", "reference_assets", "style",
            "audio", "scene_plan", "image_prompts_if_needed", "video_prompts",
            "addons", "finish", "invoice", "confirm",
        ),
        "required_assets": "optional",
        "job_type": "product_video",
        "execution_owner": "owner_product_video",
        "capability_requirements": ("per_scene_8s", "text_or_image_to_video", "final_mp4"),
        "route": "product_video_catalog",
        "fallback": "next_contract_valid_product_video_candidate",
    },
    "idea_video": {
        "sequence": (
            "scene_count", "aspect_ratio", "idea_category", "idea_preset",
            "short_edit", "addons", "finish", "invoice", "confirm",
        ),
        "required_assets": "preset_dependent",
        "job_type": "product_video",
        "execution_owner": "owner_product_video",
        "capability_requirements": ("preset_scene_plan", "per_scene_8s", "final_mp4"),
        "route": "preset_planner_to_product_video",
        "fallback": "next_contract_valid_product_video_candidate",
    },
    "script_to_video": {
        "sequence": (
            "script_source", "content_setup_if_ai", "full_script_review",
            "scene_boundary_review", "aspect_ratio", "scene_plan", "scene_review",
            "image_prompts_if_needed", "video_prompts", "addons", "finish",
            "invoice", "confirm",
        ),
        "required_assets": "script_dependent",
        "job_type": "product_video",
        "execution_owner": "owner_product_video",
        "capability_requirements": ("parsed_scene_plan", "per_scene_8s", "final_mp4"),
        "route": "parsed_scene_plan_to_product_video",
        "fallback": "next_contract_valid_product_video_candidate",
    },
    "storyboard": {
        "sequence": (
            "panel_count", "aspect_ratio", "storyboard_source", "panel_images",
            "panel_mapping", "panel_motion_prompts", "transitions", "addons",
            "finish", "invoice", "confirm",
        ),
        "required_assets": "one_image_per_panel",
        "job_type": "storyboard_to_video",
        "execution_owner": "owner_product_video",
        "capability_requirements": ("image_to_video", "scene_image_mapping", "per_scene_8s", "final_mp4"),
        "route": "storyboard_to_video",
        "fallback": "block_no_charge",
    },
    "self_shot": {
        "sequence": (
            "source_video", "source_analysis", "subject_selection",
            "preserve_constraints", "scene_count", "aspect_ratio",
            "content_source", "content_choice", "transformation_direction",
            "scene_plan", "video_prompts", "audio", "review", "finish",
            "package", "invoice", "confirm",
        ),
        "required_assets": "source_video",
        "job_type": "self_shot_scene_change",
        "execution_owner": "owner_product_video",
        "capability_requirements": (
            "video_to_video", "source_video_probe", "person_object_continuity",
            "per_scene_source_mapping", "final_mp4",
        ),
        "route": "self_shot_scene_change",
        "fallback": "block_no_charge",
    },
    "self_shot_cinematic": {
        "sequence": (
            "source_video", "source_probe", "source_segment", "subject_selection",
            "layer_rules", "transformation_type", "stage_structure", "content",
            "transformation_timeline", "wardrobe", "world", "effects", "audio",
            "review", "finish", "package", "invoice", "confirm",
        ),
        "required_assets": "source_video",
        "job_type": "self_shot_cinematic_transform",
        "execution_owner": "owner_product_video",
        "capability_requirements": (
            "video_to_video", "source_video_probe", "identity_continuity",
            "motion_continuity", "final_mp4",
        ),
        "route": "self_shot_cinematic_transform",
        "fallback": "block_no_charge",
    },
    "long_series": {
        "sequence": (
            "series_bible", "episode_count", "scenes_per_episode", "aspect_ratio",
            "continuity", "episode_outlines", "asset_strategy", "addons",
            "finish_series", "invoice", "confirm",
        ),
        "required_assets": "series_dependent",
        "job_type": "long_series_project",
        "execution_owner": "owner_long_video",
        "capability_requirements": ("episode_queue", "continuity_store", "final_mp4"),
        "route": "long_series_episode_queue",
        "fallback": "block_no_charge",
        "public_ready": False,
    },
    "trend_video": {
        "sequence": (
            "trend_source", "scene_count", "aspect_ratio", "character",
            "reference_assets", "style", "preservation", "scene_plan",
            "image_prompts_if_needed", "video_prompts", "addons", "review",
            "quality", "invoice", "confirm", "status",
        ),
        "required_assets": "optional",
        "job_type": "product_video",
        "execution_owner": "owner_product_video",
        "capability_requirements": ("trend_or_sample_source", "per_scene_8s", "final_mp4"),
        "route": "trend_preset_to_product_video",
        "fallback": "next_contract_valid_product_video_candidate",
    },
}

ENTRY_ROWS = {
    "video_ai_real": (
        (("✨ Prompt → Video", "vprofile|ai_input|prompt_video"),
         ("🖼 Ảnh → Video", "vprofile|ai_input|image_video")),
        (("🎞 Video → Video", "vprofile|ai_input|video_video"),
         ("🔄 Chọn lại từ đầu", "vproduct|open|video_ai_real")),
    ),
    "video_trend": (
        (("🔥 Trend mới nhất", "vtrend|catalog|latest"),
         ("✍️ Tự nhập trend", "vtrend|manual_trend")),
        (("🔎 Tìm kiếm trend", "vtrend|search"),
         ("📹 Gửi video trend", "vtrend|video_upload")),
    ),
    "script_image_video": (
        (("🎬 Bắt đầu lập kịch bản", "vproduct|open|script_image_video"),
         ("📖 Hướng dẫn", "menu|guide_video_ai")),
    ),
    "storyboard_prompt": (
        (("✨ Tạo storyboard AI", "vstory|ai"),
         ("📎 Gửi storyboard có sẵn", "vstory|upload")),
    ),
    "self_shot_scene_change": (
        (("📎 Gửi video nguồn", "vproduct|ss2|source"),
         ("ℹ️ Cách hoạt động", "vproduct|ss2|show|help")),
        (("👁️ Dự án đang làm", "vproduct|ss2|show|project"),
         ("🗑️ Xóa phiên hiện tại", "vproduct|ss2|reset")),
    ),
    "self_shot_cinematic_transform": (
        (("📎 Gửi video nguồn", "vproduct|ss3|source"),
         ("✨ Xem kiểu biến đổi", "vproduct|ss3|show|types")),
        (("📁 Dự án đang làm", "vproduct|ss3|show|project"),
         ("ℹ️ Cách hoạt động", "vproduct|ss3|show|help")),
    ),
    "video_idea": (
        (("💡 Khám phá ý tưởng", "vproduct|scene3_mode|video_idea|suggestions"),
         ("📖 Hướng dẫn", "menu|guide_video_ai")),
    ),
    "multi_scene_film": (
        (("ℹ️ Đang phát triển", "longvideo|public_guard"),
         ("📖 Hướng dẫn", "menu|guide_video_ai")),
    ),
}

REVIEW_ROWS = (
    (("👁️ Xem cảnh", "vprofile|scene_view|1"), ("✍️ Sửa cảnh", "vprofile|edit_scene")),
    (("🎬 Prompt video", "vprofile|review_video_prompts"), ("🔗 Chuyển cảnh", "vprofile|review_transitions")),
    (("📝 Chữ", "vprofile|review_text"), ("🎚️ Âm thanh", "vprofile|review_audio")),
    (("🖼️ Logo/Watermark", "vprofile|review_post"), ("⭐ Hoàn thiện video", "vprofile|review_continue")),
)

_SUGGESTION_PATTERNS = (
    ("Mở bằng vấn đề", "nêu vấn đề thật, chứng minh nguyên nhân và chốt giải pháp"),
    ("Mở bằng kết quả", "cho xem thành quả trước rồi kể lại quá trình"),
    ("Khoảnh khắc đời thường", "đưa chủ thể vào tình huống gần gũi và khép tự nhiên"),
    ("Câu hỏi ngắn", "mỗi cảnh trả lời một phần, cảnh cuối chốt điều cần nhớ"),
    ("Trước và sau", "giữ cùng chủ thể để thay đổi được nhìn thấy rõ"),
    ("Chi tiết cận cảnh", "mở rộng sang bối cảnh, công dụng và kết luận"),
    ("Một hành động", "theo hành động đến khi hoàn tất rồi nối sang ý kế tiếp"),
    ("Phản ứng nhân vật", "giải thích nguyên nhân, diễn biến và trạng thái cuối"),
    ("Hành trình không gian", "dẫn người xem qua từng điểm theo một hướng liên tục"),
    ("Lời hứa giá trị", "chứng minh lời hứa bằng hình ảnh rồi kết bằng bằng chứng"),
    ("Sai lầm thường gặp", "chỉ ra hậu quả, cách sửa và kết quả sau khi sửa"),
    ("Ba bước rõ ràng", "chia bước theo số cảnh mà không cắt giữa hành động"),
    ("Một lựa chọn khó", "so sánh, thử nghiệm và chốt lựa chọn có căn cứ"),
    ("Góc nhìn người dùng", "đi từ nhu cầu, trải nghiệm đến nhận xét cuối"),
    ("Câu chuyện nguồn gốc", "nối quá khứ, hiện tại và giá trị còn lại"),
    ("Một thử thách", "thiết lập mục tiêu, thực hiện và xác nhận kết quả"),
    ("Con số đáng chú ý", "giải thích ý nghĩa, minh họa và nêu giới hạn số liệu"),
    ("Một ngày sử dụng", "đi theo thời gian và kết bằng thay đổi thực tế"),
    ("Lời nhận xét", "đưa bằng chứng trực quan để củng cố nhận xét"),
    ("Mở bằng cảnh kết", "quay lại nguyên nhân rồi trở về điểm kết trọn vẹn"),
)


def product_kind(product_id: str) -> str:
    return PRODUCT_KIND_BY_ID.get(str(product_id or "").strip(), "ai_real")


def product_spec(product_id_or_kind: str) -> dict[str, Any]:
    key = str(product_id_or_kind or "").strip()
    kind = key if key in PRODUCT_SPECS else product_kind(key)
    return deepcopy(PRODUCT_SPECS[kind])


def product_sequence(product_id: str) -> tuple[str, ...]:
    return tuple(product_spec(product_id)["sequence"])


def entry_rows(product_id: str) -> list[list[tuple[str, str]]]:
    rows = ENTRY_ROWS.get(str(product_id or ""))
    if rows is None:
        rows = ENTRY_ROWS["video_ai_real"]
    return [[tuple(button) for button in row] for row in rows]


def review_rows() -> list[list[tuple[str, str]]]:
    return [[tuple(button) for button in row] for row in REVIEW_ROWS]


def bottom_navigation(back_callback: str) -> list[tuple[str, str]]:
    return [("⬅️ Quay lại", str(back_callback or "menu|main_video")), ("🏠 Menu chính", "menu|main")]


def suggestion_catalog(
    product_id: str,
    *,
    profile_label: str = "",
    scene_count: int = 1,
    aspect_ratio: str = "9:16",
) -> list[dict[str, Any]]:
    kind = product_kind(product_id)
    profile = str(profile_label or "profile đã chọn")
    count = max(MIN_SCENES, min(MAX_SCENES, int(scene_count or 1)))
    ratio = aspect_ratio if aspect_ratio in SUPPORTED_RATIOS else "9:16"
    focus = {
        "ai_real": "hình ảnh chân thật và continuity",
        "idea_video": "preset đã chọn và mạch ý ngắn",
        "script_to_video": "toàn bộ nội dung kịch bản, không cắt mất ý",
        "storyboard": "đúng ảnh và chuyển động của từng panel",
        "self_shot": "video nguồn, nhân vật và sản phẩm phải được giữ nguyên",
        "trend_video": "nguồn trend có ngày hoặc preset mẫu được ghi rõ",
        "long_series": "series bible và continuity giữa các tập",
    }[kind]
    return [
        {
            "id": f"{kind}:{index:02d}",
            "title": title,
            "content": (
                f"{title}: {structure}. Dùng đúng {count} cảnh {ratio}; mỗi cảnh trọn một ý, "
                f"bám {profile}, ưu tiên {focus}."
            ),
            "selected": False,
        }
        for index, (title, structure) in enumerate(_SUGGESTION_PATTERNS, 1)
    ]


def suggestion_page(items: Iterable[dict[str, Any]], page: int = 1) -> list[dict[str, Any]]:
    rows = [deepcopy(item) for item in items]
    page_number = max(1, min(4, int(page or 1)))
    return rows[(page_number - 1) * 5:page_number * 5]


def select_single(items: Iterable[dict[str, Any]], selected_id: str) -> list[dict[str, Any]]:
    token = str(selected_id or "")
    result = []
    for item in items:
        row = deepcopy(item)
        row["selected"] = str(row.get("id") or "") == token
        result.append(row)
    return result


def parse_script_proposal(script: str) -> dict[str, Any]:
    """Propose 5-20 contiguous scene ranges with exact source coverage."""

    return video_script_product.parse_script(str(script or ""))


def script_contract_gate(context: dict[str, Any] | None) -> dict[str, Any]:
    """Validate the approved script without normalizing or dropping one byte."""

    def as_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    state = dict(context or {})
    source = str(state.get("manual_script_raw") or state.get("script_text") or "")
    scenes = [str(item) for item in state.get("parsed_script_scenes") or []]
    ranges = [
        dict(item)
        for item in state.get("parsed_script_ranges") or []
        if isinstance(item, dict)
    ]
    coverage = dict(state.get("script_coverage") or {})
    scene_count = as_int(state.get("scene_count"), 0)
    if not source.strip():
        return {"ok": False, "blocker": "script_missing"}
    if not video_script_product.MIN_SCENES <= scene_count <= video_script_product.MAX_SCENES:
        return {"ok": False, "blocker": "script_scene_count_invalid"}
    if not bool(state.get("scene_count_confirmed")):
        return {"ok": False, "blocker": "script_scene_count_not_confirmed"}
    if len(scenes) != scene_count or len(ranges) != scene_count:
        return {"ok": False, "blocker": "script_coverage_incomplete"}

    cursor = 0
    for index, item in enumerate(ranges, 1):
        start = as_int(item.get("start"), -1)
        end = as_int(item.get("end"), -1)
        if (
            as_int(item.get("scene_index"), index) != index
            or start != cursor
            or end < start
            or source[start:end] != scenes[index - 1]
        ):
            return {"ok": False, "blocker": "script_coverage_incomplete"}
        cursor = end

    joined = "".join(scenes)
    source_sha256 = hashlib.sha256(source.encode("utf-8")).hexdigest()
    joined_sha256 = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    exact = bool(
        cursor == len(source)
        and joined == source
        and coverage.get("no_truncation")
        and coverage.get("exact_match")
        and as_int(coverage.get("coverage_percent"), 0) == 100
        and str(coverage.get("source_sha256") or "").lower() == source_sha256
        and str(coverage.get("joined_sha256") or "").lower() == joined_sha256
    )
    return {
        "ok": exact,
        "blocker": "" if exact else "script_coverage_incomplete",
        "scene_count": scene_count,
        "source_sha256": source_sha256,
    }


def storyboard_asset_gate(panel_count: int, items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    required = max(MIN_SCENES, min(MAX_SCENES, int(panel_count or 0)))
    images = [deepcopy(item) for item in items if str(item.get("file_id") or item.get("path") or "")]
    mapped = {
        int(item.get("scene_index") or item.get("panel_index") or 0)
        for item in images
        if str(item.get("scene_index") or item.get("panel_index") or "").isdigit()
    }
    missing = [index for index in range(1, required + 1) if index not in mapped]
    return {
        "ok": len(images) >= required and not missing,
        "required": required,
        "received": len(images),
        "mapped": len(mapped),
        "missing_panels": missing,
        "blocker": "" if len(images) >= required and not missing else (
            "storyboard_panel_images_missing" if len(images) < required else "storyboard_panel_mapping_incomplete"
        ),
    }


def self_shot_asset_gate(source_video: dict[str, Any] | None, probe: dict[str, Any] | None) -> dict[str, Any]:
    source = dict(source_video or {})
    media_probe = dict(probe or {})
    has_source = bool(str(source.get("file_id") or source.get("path") or ""))
    required_probe = (
        float(media_probe.get("duration_seconds") or 0) > 0
        and int(media_probe.get("width") or 0) > 0
        and int(media_probe.get("height") or 0) > 0
        and str(media_probe.get("format") or "").strip() != ""
    )
    blocker = "" if has_source and required_probe else ("source_video_missing" if not has_source else "source_video_probe_missing")
    return {"ok": has_source and required_probe, "source_received": has_source, "probe_complete": required_probe, "blocker": blocker}


def execution_route(product_id: str) -> dict[str, Any]:
    kind = product_kind(product_id)
    spec = product_spec(kind)
    return {
        "product_kind": kind,
        "job_type": spec["job_type"],
        "execution_owner": spec["execution_owner"],
        "required_assets": spec["required_assets"],
        "capability_requirements": list(spec["capability_requirements"]),
        "provider_or_local_route": spec["route"],
        "preflight": "required_before_invoice",
        "fallback": spec["fallback"],
        "delivery_contract": "valid_final_mp4_and_real_telegram_message_id",
        "charge_contract": "charge_once_after_delivery_receipt",
    }


def preflight(
    product_id: str,
    context: dict[str, Any] | None,
    *,
    owner_ready: bool,
    worker_ready: bool,
    capability_ready: bool,
    package_available: bool,
    provider_healthy: bool,
    storage_ready: bool,
    delivery_ready: bool,
) -> dict[str, Any]:
    state = dict(context or {})
    kind = product_kind(product_id)
    blockers: list[str] = []
    scene_count = int(state.get("scene_count") or state.get("panel_count") or 0)
    minimum_scene_count = video_script_product.MIN_SCENES if kind == "script_to_video" else MIN_SCENES
    if kind != "long_series" and not minimum_scene_count <= scene_count <= MAX_SCENES:
        blockers.append(
            "script_scene_count_invalid" if kind == "script_to_video" else "scene_count_invalid"
        )
    if str(state.get("aspect_ratio") or "") not in SUPPORTED_RATIOS:
        blockers.append("aspect_ratio_invalid")
    if kind == "ai_real":
        if not str(state.get("primary_profile_key") or state.get("primary_profile") or ""):
            blockers.append("primary_profile_missing")
        if not dict(state.get("content_choice") or state.get("selected_suggestion") or {}):
            blockers.append("content_choice_missing")
    elif kind == "idea_video":
        if not str(state.get("idea_preset_id") or ""):
            blockers.append("idea_preset_missing")
    elif kind == "script_to_video":
        script_gate = script_contract_gate(state)
        if not script_gate["ok"]:
            blockers.append(str(script_gate["blocker"]))
    elif kind == "storyboard":
        gate = storyboard_asset_gate(scene_count, state.get("asset_items") or [])
        if not gate["ok"]:
            blockers.append(str(gate["blocker"]))
        transitions = list(state.get("transitions") or [])
        if len(transitions) != max(0, scene_count - 1):
            blockers.append("storyboard_transition_count_invalid")
    elif kind == "self_shot":
        gate = self_shot_asset_gate(state.get("source_video"), state.get("source_probe"))
        if not gate["ok"]:
            blockers.append(str(gate["blocker"]))
    elif kind == "trend_video":
        source = dict(state.get("trend_source") or {})
        uploaded_source_ready = bool(
            str(source.get("intake_lane") or "") == "video_upload"
            and str(source.get("source_video_id") or "")
            and dict(source.get("source_analysis") or {})
        )
        if (
            not (source.get("source_url") and source.get("observed_at"))
            and not source.get("sample_preset")
            and source.get("source_type") != "user_topic"
            and not uploaded_source_ready
        ):
            blockers.append("trend_source_or_sample_missing")
    elif kind == "long_series" and not bool(product_spec(kind).get("public_ready", True)):
        blockers.append("long_series_public_not_ready")
    readiness = {
        "execution_owner_unavailable": owner_ready,
        "worker_runtime_unavailable": worker_ready,
        "required_capability_unavailable": capability_ready,
        "package_unavailable": package_available,
        "provider_unhealthy": provider_healthy,
        "storage_route_unavailable": storage_ready,
        "delivery_route_unavailable": delivery_ready,
    }
    blockers.extend(reason for reason, ok in readiness.items() if not ok)
    blockers = list(dict.fromkeys(blockers))
    return {
        "ok": not blockers,
        "blockers": blockers,
        "blocker": blockers[0] if blockers else "",
        "route": execution_route(product_id),
        "side_effects": {
            "job": 0,
            "outbox": 0,
            "invoice": 0,
            "provider_calls": 0,
            "generated_files": 0,
            "wallet_mutations": 0,
            "xu_charged": 0,
        },
    }


def record_delivery(context: dict[str, Any] | None, *, message_id: int, receipt_key: str) -> dict[str, Any]:
    state = deepcopy(context or {})
    delivery = dict(state.get("delivery") or {})
    actual_message_id = int(message_id or 0)
    key = str(receipt_key or "").strip()
    if actual_message_id <= 0 or not key:
        raise ValueError("valid_delivery_receipt_required")
    if delivery.get("recorded"):
        if int(delivery.get("message_id") or 0) != actual_message_id or str(delivery.get("receipt_key") or "") != key:
            raise ValueError("delivery_receipt_conflict")
        return state
    state["delivery"] = {"recorded": True, "message_id": actual_message_id, "receipt_key": key}
    return state


def charge_allowed(context: dict[str, Any] | None) -> bool:
    delivery = dict((context or {}).get("delivery") or {})
    return bool(delivery.get("recorded") and int(delivery.get("message_id") or 0) > 0 and str(delivery.get("receipt_key") or ""))


def back_matrix(product_id: str) -> dict[str, str]:
    sequence = product_sequence(product_id)
    result = {sequence[0]: "product_intro"}
    for index in range(1, len(sequence)):
        result[sequence[index]] = sequence[index - 1]
    return result


def validate_rows(rows: Iterable[Iterable[tuple[str, str]]], *, expected_back: str) -> dict[str, Any]:
    normalized = [[tuple(button) for button in row] for row in rows]
    errors: list[str] = []
    if not normalized:
        errors.append("keyboard_empty")
    for index, row in enumerate(normalized):
        if len(row) != 2 and not (len(row) == 5 and all(str(button[0]).strip("✅ ") in {"1", "2", "3", "4", "5"} for button in row)):
            errors.append(f"row_{index + 1}_invalid_width")
    expected_nav = bottom_navigation(expected_back)
    if not normalized or normalized[-1] != expected_nav:
        errors.append("bottom_navigation_invalid")
    callbacks = [callback for row in normalized for _label, callback in row]
    if len(callbacks) != len(set(callbacks)):
        errors.append("duplicate_callback")
    return {"ok": not errors, "errors": errors, "callbacks": callbacks}
