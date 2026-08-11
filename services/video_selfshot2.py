"""Canonical person/object-aware flow for Self-shot Scene Change.

This module owns planning and validation only. It never creates projects,
provider tasks, files, invoices, wallet mutations, or delivery receipts.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping

from services import video_ai_real_pricing


PRODUCT_ID = "self_shot_scene_change"
JOB_TYPE = "self_shot_scene_change"
MODE = "person_object_cinematic"
MIN_SCENES = 1
MAX_SCENES = 20
SCENE_SECONDS = 8
SUPPORTED_RATIOS = frozenset({"9:16", "16:9", "1:1", "4:5"})
SUBJECT_MODES = frozenset({"person", "object", "person_object", "motion_only", "custom"})

CONTENT_PROFILES = (
    "Bán hàng / quảng cáo", "Đánh giá / giới thiệu sản phẩm", "Tiếp thị liên kết / nội dung người dùng",
    "Cảm nhận khách hàng / câu chuyện thực tế", "Thương hiệu / doanh nghiệp", "Nhà sáng tạo / bắt xu hướng",
    "Meme / nhại vui / hài", "Sự kiện / khoảnh khắc nổi bật", "Kiến trúc ngoại thất", "Nội thất",
    "Cải tạo không gian", "Bất động sản", "Tham quan kiến trúc", "Hiệu ứng điện ảnh",
    "Hoạt hình 2D/3D", "Nhân vật", "Thời trang / trình diễn", "Trưng bày sản phẩm / 3D",
    "Ứng dụng / trò chơi", "Website / phần mềm", "Hướng dẫn / giải thích",
    "Nội dung mạng xã hội", "Lịch sử / văn hóa", "Thể thao / thể thao điện tử",
    "Du lịch / địa phương", "Kỹ thuật / công nghiệp", "Tin tức / dữ liệu",
    "Động lực / phát triển bản thân", "Ẩm thực", "Giáo dục / kiến thức",
    "Âm nhạc / sự kiện", "Âm thanh thư giãn",
)

CONTENT_DIRECTIONS = (
    ("future_world", "Thành phố tương lai", "Đổi thế giới xung quanh sang một thành phố tương lai liền mạch."),
    ("ancient_world", "Thế giới cổ đại", "Giữ chủ thể và hành động, thay kiến trúc và ánh sáng thành bối cảnh cổ đại."),
    ("fantasy_world", "Thế giới giả tưởng", "Mở rộng không gian thành một thế giới giả tưởng có chiều sâu điện ảnh."),
    ("space_world", "Không gian vũ trụ", "Đặt chủ thể vào tàu vũ trụ hoặc hành tinh mới mà không mất tương tác gốc."),
    ("post_apocalyptic", "Hậu tận thế", "Giữ người, vật và chuyển động, thay môi trường thành hậu tận thế có nguyên nhân rõ."),
    ("nature_cinema", "Thiên nhiên điện ảnh", "Mở rộng cảnh quan, thời tiết và ánh sáng tự nhiên quanh chủ thể."),
    ("action_story", "Phim hành động", "Biến hành động gốc thành một nhịp phim có mở đầu và kết thúc trọn vẹn."),
    ("mystery_story", "Phim trinh thám", "Biến các chi tiết trong video nguồn thành manh mối và câu chuyện trinh thám."),
    ("adventure_story", "Phim phiêu lưu", "Dùng chuyển động nguồn làm điểm bắt đầu cho hành trình khám phá."),
    ("romance_story", "Phim lãng mạn", "Giữ biểu cảm và khoảng cách chủ thể, thay đổi không gian theo mạch cảm xúc."),
    ("light_comedy", "Hài tình huống", "Giữ hành động thật và tạo tình huống hài rõ ràng, không chế giễu nhân vật."),
    ("light_horror", "Kinh dị nhẹ", "Thêm ánh sáng, âm thanh và chi tiết hồi hộp mà không biến dạng chủ thể."),
    ("character_trailer", "Giới thiệu nhân vật", "Giới thiệu chủ thể qua nhiều cảnh liên quan, giữ nhận diện xuyên suốt."),
    ("same_action_new_world", "Giữ hành động, đổi bối cảnh", "Dùng đúng hành động nguồn trong mỗi bối cảnh mới."),
    ("world_expansion", "Mở rộng thế giới", "Thêm kiến trúc, phương tiện, quần chúng và thời tiết quanh chủ thể."),
    ("product_hero", "Sản phẩm làm trung tâm", "Giữ hình dáng, logo và cách cầm hoặc sử dụng sản phẩm trong không gian cao cấp."),
    ("product_demo", "Quảng cáo cách sử dụng", "Theo sát thao tác thật và làm rõ công dụng của sản phẩm."),
    ("before_after", "Trước và sau", "Giữ cùng chủ thể để thay đổi bối cảnh hoặc trạng thái được nhìn thấy rõ."),
    ("person_object_story", "Người và vật cùng kể chuyện", "Giữ điểm tiếp xúc và vai trò của vật trong câu chuyện quanh người."),
    ("fashion_character", "Thời trang / nhân vật", "Đổi cách trình bày, bối cảnh và ánh sáng trong khi giữ chủ thể đã xác nhận."),
)

DIRECTION_OPTIONS = (
    ("environment", "🌍 Đổi bối cảnh", ("video_to_video", "environment_replacement")),
    ("new_story", "🎬 Tạo câu chuyện mới", ("video_to_video", "video_reference")),
    ("cinematic_effects", "✨ Thêm hiệu ứng điện ảnh", ("video_to_video", "video_reference")),
    ("world_expand", "🏙️ Mở rộng không gian", ("video_to_video", "environment_replacement")),
    ("product_focus", "📦 Làm nổi bật sản phẩm", ("video_to_video", "object_reference", "product_logo_preservation")),
    ("character_transform", "👤 Biến đổi nhân vật", ("video_to_video", "person_identity_preservation")),
    ("source_camera", "🎥 Giữ máy quay nguồn", ("video_to_video", "camera_motion_transfer")),
    ("redirect_camera", "🎞️ Đạo diễn lại máy quay", ("video_to_video", "video_reference")),
)

PRESERVE_LABELS = {
    "person_identity": "👤 Nhận diện người",
    "object_identity": "📦 Nhận diện vật",
    "wardrobe_color": "👕 Trang phục / màu sắc",
    "action_expression": "🎭 Hành động / biểu cảm",
    "person_object_relation": "🔗 Quan hệ người - vật",
    "custom": "✍️ Yêu cầu khác",
}

AUDIO_LABELS = {
    "source": "🔊 Âm thanh gốc",
    "voice": "🎙️ Lồng tiếng",
    "music": "🎵 Nhạc nền",
    "sfx": "💥 Hiệu ứng âm thanh",
    "subtitle": "💬 Phụ đề",
}

ADDON_POSITIONS = (
    ("top_left", "Trên trái"),
    ("top_center", "Trên giữa"),
    ("top_right", "Trên phải"),
    ("center_left", "Giữa trái"),
    ("center", "Chính giữa"),
    ("center_right", "Giữa phải"),
    ("bottom_left", "Dưới trái"),
    ("bottom_center", "Dưới giữa"),
    ("bottom_right", "Dưới phải"),
)

ADDON_POSITION_LABELS = {
    **dict(ADDON_POSITIONS),
    "middle_left": "Giữa trái",
    "middle_right": "Giữa phải",
}

PRESERVE_BLOCKER_MESSAGES = {
    "subject_manifest_missing": "Chưa xác nhận người, vật hoặc chuyển động cần giữ.",
    "person_identity_lock_missing": "Cần bật giữ nhận diện người trước khi tiếp tục.",
    "object_identity_lock_missing": "Cần bật giữ nhận diện vật hoặc sản phẩm trước khi tiếp tục.",
    "person_object_relationship_lock_missing": "Cần bật giữ quan hệ giữa người và vật trước khi tiếp tục.",
    "source_action_lock_missing": "Cần bật giữ hành động và biểu cảm nguồn trước khi tiếp tục.",
}

SCREEN_PARENTS = {
    "intro": "hub",
    "help": "intro",
    "project": "intro",
    "analysis": "intro",
    "subject": "analysis",
    "detected": "subject",
    "preserve": "subject",
    "scene_count": "preserve",
    "ratio": "scene_count",
    "content_source": "ratio",
    "suggestions": "content_source",
    "profiles": "content_source",
    "ideas": "content_source",
    "direction": "content_source",
    "scene_plan": "direction",
    "prompts": "scene_plan",
    "audio": "prompts",
    "volume": "audio",
    "addons": "audio",
    "addon_position": "addons",
    "review": "addons",
    "finish": "review",
}


def _safe(value: Any) -> str:
    return str(value or "").strip()


def ratio_valid(value: Any) -> bool:
    text = _safe(value)
    if text in SUPPORTED_RATIOS:
        return True
    match = re.fullmatch(r"(\d{1,3})\s*:\s*(\d{1,3})", text)
    if not match:
        return False
    width, height = (int(item) for item in match.groups())
    return 0 < width <= 100 and 0 < height <= 100


def _nav(back_screen: str) -> list[tuple[str, str]]:
    callback = "vproduct|selfshot_hub" if back_screen == "hub" else f"vproduct|ss2|show|{back_screen}"
    return [("⬅️ Quay lại", callback), ("🎬 Menu Video", "menu|main_video")]


def initial_draft() -> dict[str, Any]:
    return {
        "product_id": PRODUCT_ID,
        "job_type": JOB_TYPE,
        "selfshot_mode": MODE,
        "selfshot2_screen": "intro",
        "source_video": {},
        "source_analysis": {},
        "subject_manifest": {},
        "preserve_constraints": {},
        "scene_count": 0,
        "aspect_ratio": "",
        "content_source": "",
        "suggestion_page": 1,
        "profile_page": 1,
        "idea_page": 1,
        "selected_content": {},
        "selected_direction": "",
        "scene_plan": [],
        "video_prompts": [],
        "audio_plan": {
            "source": {"enabled": True, "volume": 100, "policy": "keep_original_mix"},
            "voice": {"enabled": False, "volume": 100, "duck_source": True},
            "music": {"enabled": False, "volume": 20},
            "sfx": {"enabled": False, "volume": 35},
            "subtitle": {"enabled": False, "position": "bottom_center"},
        },
        "visual_addons": {
            "logo": {
                "enabled": False,
                "file_id": "",
                "file_unique_id": "",
                "position": "top_right",
            },
            "watermark": {
                "enabled": False,
                "text": "",
                "position": "bottom_right",
            },
        },
        "provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "generated_files": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
        "charge_policy": "after_valid_mp4_delivery",
    }


def source_fingerprint(source: Mapping[str, Any] | None) -> str:
    row = dict(source or {})
    stable = {
        "file_unique_id": _safe(row.get("file_unique_id")),
        "file_id": _safe(row.get("file_id")),
        "file_size": int(row.get("file_size") or 0),
        "duration_seconds": float(row.get("duration_seconds") or 0),
        "width": int(row.get("width") or 0),
        "height": int(row.get("height") or 0),
    }
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode("utf-8")).hexdigest()


def _normalize_track(item: Mapping[str, Any], kind: str, index: int) -> dict[str, Any]:
    row = dict(item or {})
    track_id = _safe(row.get("subject_id") or row.get("track_id") or f"{kind}_{index}")
    description = _safe(row.get("description") or row.get("label") or f"{kind} {index}")
    return {
        "subject_id": track_id,
        "track_id": track_id,
        "subject_type": kind,
        "description": description,
        "confidence": float(row.get("confidence") or 0),
        "provenance": _safe(row.get("provenance") or "local_analysis"),
        "thumbnail_ref": _safe(row.get("thumbnail_ref")),
    }


def analyze_source(source: Mapping[str, Any] | None) -> dict[str, Any]:
    row = dict(source or {})
    width = int(row.get("width") or 0)
    height = int(row.get("height") or 0)
    duration = float(row.get("duration_seconds") or 0)
    person_rows = list(row.get("person_candidates") or row.get("person_tracks") or [])
    object_rows = list(row.get("object_candidates") or row.get("object_tracks") or [])
    persons = [_normalize_track(item, "person", index) for index, item in enumerate(person_rows, 1) if isinstance(item, Mapping)]
    objects = [_normalize_track(item, "object", index) for index, item in enumerate(object_rows, 1) if isinstance(item, Mapping)]
    shot_rows = list(row.get("shot_boundaries") or [])
    if not shot_rows and duration > 0:
        shot_rows = [{"shot_id": "shot_1", "start_seconds": 0.0, "end_seconds": duration, "provenance": "metadata_default_single_shot"}]
    audio_streams = int(row.get("audio_streams") or 0)
    frame_rate_mode = _safe(row.get("frame_rate_mode") or row.get("fps_mode")).lower()
    if frame_rate_mode not in {"cfr", "vfr"}:
        if row.get("is_vfr") is True:
            frame_rate_mode = "vfr"
        elif row.get("is_vfr") is False:
            frame_rate_mode = "cfr"
        else:
            frame_rate_mode = "unknown"
    return {
        "source_video_id": _safe(row.get("file_id")),
        "source_hash": source_fingerprint(row),
        "duration_seconds": duration,
        "width": width,
        "height": height,
        "fps": float(row.get("fps") or 0),
        "frame_rate_mode": frame_rate_mode,
        "aspect_ratio": "9:16" if height > width else ("16:9" if width > height else "1:1"),
        "format": _safe(row.get("format") or row.get("mime_type") or "video/mp4"),
        "camera_movement": _safe(row.get("camera_movement") or "not_measured"),
        "main_actions": list(row.get("main_actions") or []),
        "person_tracks": persons,
        "face_tracks": list(row.get("face_tracks") or []),
        "object_tracks": objects,
        "logo_text_candidates": list(row.get("logo_text_candidates") or []),
        "interaction_graph": list(row.get("interaction_graph") or []),
        "shot_manifest": shot_rows,
        "audio_manifest": {
            "stream_count": audio_streams,
            "speech_present": row.get("speech_present") if "speech_present" in row else None,
            "music_present": row.get("music_present") if "music_present" in row else None,
            "ambient_present": row.get("ambient_present") if "ambient_present" in row else None,
            "stem_separation_available": bool(row.get("stem_separation_available")),
        },
        "analysis_version": "selfshot2-local-v1",
        "analysis_truth": "metadata_and_available_local_tracks_only",
    }


def source_gate(source: Mapping[str, Any] | None, analysis: Mapping[str, Any] | None) -> dict[str, Any]:
    media = dict(source or {})
    report = dict(analysis or {})
    has_source = bool(_safe(media.get("file_id") or media.get("path")))
    complete = (
        float(report.get("duration_seconds") or 0) > 0
        and int(report.get("width") or 0) > 0
        and int(report.get("height") or 0) > 0
        and bool(_safe(report.get("source_hash")))
    )
    blocker = "" if has_source and complete else ("source_video_missing" if not has_source else "source_video_probe_missing")
    return {"ok": has_source and complete, "source_received": has_source, "probe_complete": complete, "blocker": blocker}


def detected_subjects(analysis: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    report = dict(analysis or {})
    return [deepcopy(item) for item in [*(report.get("person_tracks") or []), *(report.get("object_tracks") or [])] if isinstance(item, Mapping)]


def _user_confirmed_subject(kind: str, description: str = "") -> dict[str, Any]:
    label = description or ("nguoi duoc khach xac nhan trong video nguon" if kind == "person" else "vat/san pham duoc khach xac nhan trong video nguon")
    return {
        "subject_id": f"{kind}_user_confirmed_1",
        "track_id": f"{kind}_user_confirmed_1",
        "subject_type": kind,
        "description": label,
        "confidence": 1.0,
        "provenance": "user_confirmed_source_bound",
        "thumbnail_ref": "",
    }


def select_subjects(
    analysis: Mapping[str, Any] | None,
    mode: str,
    *,
    selected_ids: Iterable[str] | None = None,
    custom_description: str = "",
) -> dict[str, Any]:
    choice = _safe(mode)
    if choice not in SUBJECT_MODES:
        raise ValueError("subject_mode_invalid")
    report = dict(analysis or {})
    persons = [deepcopy(item) for item in report.get("person_tracks") or []]
    objects = [deepcopy(item) for item in report.get("object_tracks") or []]
    requested = {_safe(item) for item in (selected_ids or []) if _safe(item)}
    all_rows = persons + objects
    if requested:
        selected = [item for item in all_rows if _safe(item.get("subject_id")) in requested]
        if len(selected) != len(requested):
            raise ValueError("subject_id_not_found")
    elif choice == "person":
        if len(persons) > 1:
            raise ValueError("person_subject_choice_required")
        selected = persons or [_user_confirmed_subject("person")]
    elif choice == "object":
        if len(objects) > 1:
            raise ValueError("object_subject_choice_required")
        selected = objects or [_user_confirmed_subject("object")]
    elif choice == "person_object":
        if len(persons) > 1 or len(objects) > 1:
            raise ValueError("person_object_subject_choice_required")
        selected = (persons or [_user_confirmed_subject("person")]) + (objects or [_user_confirmed_subject("object")])
    elif choice == "motion_only":
        selected = []
    else:
        if not _safe(custom_description):
            raise ValueError("custom_subject_description_required")
        selected = [_user_confirmed_subject("object", _safe(custom_description))]
    selected_types = {str(item.get("subject_type") or "") for item in selected}
    if choice == "person" and selected_types != {"person"}:
        raise ValueError("wrong_subject_selection")
    if choice == "object" and selected_types != {"object"}:
        raise ValueError("wrong_subject_selection")
    if choice == "person_object" and not {"person", "object"}.issubset(selected_types):
        raise ValueError("person_object_pair_required")
    selected_ids_set = {_safe(item.get("subject_id")) for item in selected}
    interactions = []
    for item in report.get("interaction_graph") or []:
        if not isinstance(item, Mapping):
            continue
        relation = deepcopy(dict(item))
        person_id = _safe(relation.get("person_id") or relation.get("source_subject_id"))
        object_id = _safe(relation.get("object_id") or relation.get("target_subject_id"))
        if person_id in selected_ids_set and object_id in selected_ids_set:
            relation["person_id"] = person_id
            relation["object_id"] = object_id
            relation["relationship_type"] = _safe(relation.get("relationship_type") or "interacting")
            interactions.append(relation)
    return {
        "selection_mode": choice,
        "subject_ids": [_safe(item.get("subject_id")) for item in selected],
        "subjects": selected,
        "person_subject_ids": [_safe(item.get("subject_id")) for item in selected if item.get("subject_type") == "person"],
        "object_subject_ids": [_safe(item.get("subject_id")) for item in selected if item.get("subject_type") == "object"],
        "interaction_graph": interactions,
        "motion_only": choice == "motion_only",
        "confirmed": True,
    }


def default_preserve_constraints(subject_manifest: Mapping[str, Any] | None) -> dict[str, Any]:
    manifest = dict(subject_manifest or {})
    has_person = bool(manifest.get("person_subject_ids"))
    has_object = bool(manifest.get("object_subject_ids"))
    return {
        "person_identity": has_person,
        "object_identity": has_object,
        "wardrobe_color": has_person or has_object,
        "action_expression": True,
        "person_object_relation": has_person and has_object,
        "custom": "",
        "confirmed": True,
    }


def preserve_gate(subject_manifest: Mapping[str, Any] | None, constraints: Mapping[str, Any] | None) -> dict[str, Any]:
    manifest = dict(subject_manifest or {})
    rules = dict(constraints or {})
    blockers = []
    if not manifest.get("confirmed"):
        blockers.append("subject_manifest_missing")
    if manifest.get("person_subject_ids") and not rules.get("person_identity"):
        blockers.append("person_identity_lock_missing")
    if manifest.get("object_subject_ids") and not rules.get("object_identity"):
        blockers.append("object_identity_lock_missing")
    if manifest.get("person_subject_ids") and manifest.get("object_subject_ids") and not rules.get("person_object_relation"):
        blockers.append("person_object_relationship_lock_missing")
    if not rules.get("action_expression"):
        blockers.append("source_action_lock_missing")
    return {"ok": not blockers, "blockers": blockers, "blocker": blockers[0] if blockers else ""}


def suggestion_catalog(
    analysis: Mapping[str, Any] | None,
    subject_manifest: Mapping[str, Any] | None,
    *,
    scene_count: int,
    aspect_ratio: str,
    profile: str = "",
) -> list[dict[str, Any]]:
    report = dict(analysis or {})
    manifest = dict(subject_manifest or {})
    subject_text = ", ".join(_safe(item.get("description")) for item in manifest.get("subjects") or []) or "chuyển động nguồn"
    action_text = ", ".join(_safe(item) for item in report.get("main_actions") or []) or "hành động đang có trong video"
    count = max(MIN_SCENES, min(MAX_SCENES, int(scene_count or 1)))
    ratio = aspect_ratio if ratio_valid(aspect_ratio) else "9:16"
    profile_text = _safe(profile) or "nội dung phù hợp video nguồn"
    items = []
    for index, (item_id, title, summary) in enumerate(CONTENT_DIRECTIONS, 1):
        items.append({
            "id": item_id,
            "index": index,
            "title": title,
            "summary": f"{summary} Giữ {subject_text}; bám {action_text}; dùng {count} cảnh {ratio}; theo {profile_text}.",
        })
    return items


def suggestion_page(items: Iterable[Mapping[str, Any]], page: int = 1) -> list[dict[str, Any]]:
    rows = [deepcopy(dict(item)) for item in items]
    page_number = max(1, min(4, int(page or 1)))
    return rows[(page_number - 1) * 5:page_number * 5]


def idea_presets() -> list[dict[str, Any]]:
    return [
        {"id": item_id, "title": title, "summary": summary, "profile": CONTENT_PROFILES[(index - 1) % len(CONTENT_PROFILES)]}
        for index, (item_id, title, summary) in enumerate(CONTENT_DIRECTIONS, 1)
    ]


def direction_contract(direction_id: str) -> dict[str, Any]:
    row = next((item for item in DIRECTION_OPTIONS if item[0] == direction_id), None)
    if not row:
        raise ValueError("direction_invalid")
    return {
        "direction_id": row[0],
        "label": row[1],
        "required_capabilities": list(row[2]),
        "keeps": "confirmed subjects, source action and person-object contact points",
        "changes": "approved environment, supporting elements, light, weather and cinematic treatment",
        "fallback": "controlled_keyframe_fallback_or_block_no_charge",
    }


def build_scene_plan(
    *,
    analysis: Mapping[str, Any],
    subject_manifest: Mapping[str, Any],
    constraints: Mapping[str, Any],
    scene_count: int,
    content: Mapping[str, Any],
    direction: Mapping[str, Any],
) -> list[dict[str, Any]]:
    count = max(MIN_SCENES, min(MAX_SCENES, int(scene_count or 1)))
    duration = max(0.1, float((analysis or {}).get("duration_seconds") or 0))
    segment_span = duration / count
    rows = []
    for index in range(1, count + 1):
        start = round((index - 1) * segment_span, 3)
        end = round(min(duration, index * segment_span), 3)
        rows.append({
            "scene_id": index,
            "scene_index": index,
            "source_segment_start": start,
            "source_segment_end": end,
            "source_segment_reused": False,
            "person_subject_ids": list(subject_manifest.get("person_subject_ids") or []),
            "object_subject_ids": list(subject_manifest.get("object_subject_ids") or []),
            "person_object_interactions": deepcopy(list(subject_manifest.get("interaction_graph") or [])),
            "preserve_constraints": deepcopy(dict(constraints or {})),
            "environment_before": "source_environment",
            "environment_after": _safe(content.get("title") or content.get("summary")),
            "main_action": f"Complete source action beat {index} without truncation",
            "camera_motion": "source_camera" if direction.get("direction_id") == "source_camera" else "directed_camera_with_source_continuity",
            "subject_motion": "transfer_source_motion_and_contact_points",
            "start_state": "inherits_previous_end" if index > 1 else "source_segment_start",
            "end_state": "natural_completed_action_ready_for_next_scene" if index < count else "closed_story_state",
            "duration": SCENE_SECONDS,
            "audio_policy": "configured_in_audio_plan",
            "prompt_version": 1,
        })
    return rows


def compile_scene_prompts(
    scene_plan: Iterable[Mapping[str, Any]],
    *,
    subject_manifest: Mapping[str, Any],
    content: Mapping[str, Any],
    direction: Mapping[str, Any],
) -> list[dict[str, Any]]:
    subjects = ", ".join(_safe(item.get("description")) for item in subject_manifest.get("subjects") or []) or "source motion"
    interaction_labels = []
    for item in subject_manifest.get("interaction_graph") or []:
        if not isinstance(item, Mapping):
            continue
        relation = _safe(item.get("relationship_type") or "interacting")
        person_id = _safe(item.get("person_id") or item.get("source_subject_id"))
        object_id = _safe(item.get("object_id") or item.get("target_subject_id"))
        interaction_labels.append(f"{person_id} {relation} {object_id}".strip())
    interactions = "; ".join(interaction_labels) or "source person-object contact points"
    result = []
    for row in scene_plan:
        scene = dict(row)
        prompt = (
            f"Scene {scene.get('scene_index')}: preserve locked source subjects [{subjects}], exact identity, body/product shape, "
            f"logo/text/color, source action and person-object contact points with exact relationship [{interactions}]. "
            f"{content.get('summary') or content.get('title')}. "
            f"Direction: {direction.get('label')}; environment changes only as approved. Transfer person, object, camera and environment motion "
            f"from {scene.get('source_segment_start')}s to {scene.get('source_segment_end')}s; begin {scene.get('start_state')} and end {scene.get('end_state')}."
        )
        negative = (
            "no face drift, no body drift, no product shape drift, no logo or printed-text mutation, no extra limbs, "
            "no duplicated person or object, no lost held object, no broken contact point, no unrelated clip, no slideshow"
        )
        result.append({
            "scene_id": int(scene.get("scene_id") or 0),
            "scene_index": int(scene.get("scene_index") or 0),
            "prompt": prompt,
            "negative_prompt": negative,
            "source_segment_start": scene.get("source_segment_start"),
            "source_segment_end": scene.get("source_segment_end"),
            "prompt_version": int(scene.get("prompt_version") or 1),
        })
    return result


def capability_route(
    *,
    capabilities: Iterable[str],
    subject_manifest: Mapping[str, Any],
    direction: Mapping[str, Any],
    reference_keyframes_ready: bool = False,
) -> dict[str, Any]:
    available = {_safe(item) for item in capabilities if _safe(item)}
    manifest = dict(subject_manifest or {})
    required = set(direction.get("required_capabilities") or [])
    if manifest.get("person_subject_ids"):
        required.add("person_identity_preservation")
    if manifest.get("object_subject_ids"):
        required.add("object_reference")
    if manifest.get("person_subject_ids") and manifest.get("object_subject_ids"):
        required.add("person_object_relationship")
    missing = sorted(required - available)
    if not missing:
        return {"ok": True, "route": "direct_video_to_video", "truth": "direct_video_to_video", "required": sorted(required), "missing": []}
    performance_required = {item for item in required if item not in {"video_to_video", "environment_replacement"}}
    if "performance_capture" in available and performance_required.issubset(available):
        return {"ok": True, "route": "performance_capture_reference", "truth": "performance_capture", "required": sorted(required), "missing": missing}
    if "image_to_video" in available and reference_keyframes_ready:
        return {
            "ok": True,
            "route": "controlled_keyframe_image_to_video",
            "truth": "image_to_video_fallback_not_direct_v2v",
            "required": sorted(required),
            "missing": missing,
            "continuity_validation_required": True,
        }
    return {"ok": False, "route": "", "truth": "blocked_before_invoice", "required": sorted(required), "missing": missing, "blocker": "selfshot2_required_capability_unavailable"}


def preflight(
    state: Mapping[str, Any] | None,
    *,
    capabilities: Iterable[str],
    owner_ready: bool,
    package_available: bool,
    storage_ready: bool,
    delivery_ready: bool,
) -> dict[str, Any]:
    draft = dict(state or {})
    blockers = []
    source_report = source_gate(draft.get("source_video"), draft.get("source_analysis"))
    if not source_report.get("ok"):
        blockers.append(source_report.get("blocker"))
    preserve_report = preserve_gate(draft.get("subject_manifest"), draft.get("preserve_constraints"))
    if not preserve_report.get("ok"):
        blockers.extend(preserve_report.get("blockers") or [])
    scene_count = int(draft.get("scene_count") or 0)
    if not MIN_SCENES <= scene_count <= MAX_SCENES:
        blockers.append("scene_count_invalid")
    if not ratio_valid(draft.get("aspect_ratio")):
        blockers.append("aspect_ratio_invalid")
    if not dict(draft.get("selected_content") or {}):
        blockers.append("content_choice_missing")
    direction = dict(draft.get("direction_contract") or {})
    if not direction:
        blockers.append("transformation_direction_missing")
    if len(draft.get("scene_plan") or []) != scene_count:
        blockers.append("scene_plan_incomplete")
    if len(draft.get("video_prompts") or []) != scene_count:
        blockers.append("scene_prompts_incomplete")
    route = capability_route(
        capabilities=capabilities,
        subject_manifest=draft.get("subject_manifest") or {},
        direction=direction,
        reference_keyframes_ready=bool(draft.get("reference_keyframes_ready")),
    ) if direction else {"ok": False, "blocker": "transformation_direction_missing", "route": "", "missing": []}
    if not route.get("ok"):
        blockers.append(route.get("blocker") or "selfshot2_required_capability_unavailable")
    readiness = {
        "execution_owner_unavailable": owner_ready,
        "package_unavailable": package_available,
        "storage_route_unavailable": storage_ready,
        "delivery_route_unavailable": delivery_ready,
    }
    blockers.extend(reason for reason, ready in readiness.items() if not ready)
    blockers = [str(item) for item in dict.fromkeys(item for item in blockers if item)]
    return {
        "ok": not blockers,
        "blockers": blockers,
        "blocker": blockers[0] if blockers else "",
        "engine_route": route,
        "side_effects": {"job": 0, "outbox": 0, "invoice": 0, "provider_calls": 0, "generated_files": 0, "wallet_mutations": 0, "xu_charged": 0},
    }


def continuity_validation(
    metrics: Mapping[str, Any] | None,
    subject_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate only the continuity evidence required by the selected subjects."""

    row = dict(metrics or {})
    manifest = dict(subject_manifest or {})
    person_required = bool(manifest.get("person_subject_ids"))
    object_required = bool(manifest.get("object_subject_ids"))
    relationship_required = person_required and object_required

    normalized = {
        "final_mp4_valid": bool(row.get("final_mp4_valid")),
        "scene_coverage_complete": bool(row.get("scene_coverage_complete")),
        "person_identity": bool(
            row.get("person_identity")
            or row.get("person_identity_preserved")
            or row.get("person_continuity")
            or row.get("subject_continuity")
        ),
        "object_identity": bool(
            row.get("object_identity")
            or row.get("object_identity_preserved")
            or row.get("object_continuity")
            or row.get("product_identity_preserved")
        ),
        "person_object_relationship": bool(
            row.get("person_object_relationship")
            or row.get("person_object_relationship_preserved")
            or row.get("relationship_continuity")
        ),
    }
    required = ["final_mp4_valid", "scene_coverage_complete"]
    if person_required:
        required.append("person_identity")
    if object_required:
        required.append("object_identity")
    if relationship_required:
        required.append("person_object_relationship")
    failed = [key for key in required if not normalized.get(key)]
    return {
        "ok": not failed,
        "required": required,
        "failed": failed,
        "blocker": failed[0] if failed else "",
        "metrics": normalized,
    }


def record_delivery(
    state: Mapping[str, Any] | None,
    *,
    message_id: int,
    receipt_key: str,
    artifact: Mapping[str, Any] | None = None,
    continuity_metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    draft = deepcopy(dict(state or {}))
    message = int(message_id or 0)
    receipt = _safe(receipt_key)
    if message <= 0 or not receipt:
        raise ValueError("valid_delivery_receipt_required")
    final_artifact = dict(artifact or {})
    artifact_ok = bool(
        final_artifact.get("final_mp4_valid")
        and int(final_artifact.get("bytes") or 0) > 0
        and float(final_artifact.get("duration_seconds") or 0) > 0
        and _safe(final_artifact.get("mime_type") or "video/mp4").lower() == "video/mp4"
    )
    continuity = continuity_validation(continuity_metrics, draft.get("subject_manifest"))
    if not artifact_ok:
        raise ValueError("valid_final_mp4_required")
    if not continuity.get("ok"):
        raise ValueError(continuity.get("blocker") or "continuity_validation_required")
    existing = dict(draft.get("delivery") or {})
    if existing:
        if int(existing.get("message_id") or 0) != message or _safe(existing.get("receipt_key")) != receipt:
            raise ValueError("delivery_receipt_conflict")
        return draft
    draft["delivery"] = {
        "recorded": True,
        "message_id": message,
        "receipt_key": receipt,
        "final_mp4_valid": True,
        "continuity_valid": True,
    }
    draft["receipt_state"] = "recorded_once"
    return draft


def charge_allowed(state: Mapping[str, Any] | None) -> bool:
    delivery = dict((state or {}).get("delivery") or {})
    return bool(
        delivery.get("recorded")
        and delivery.get("final_mp4_valid")
        and delivery.get("continuity_valid")
        and int(delivery.get("message_id") or 0) > 0
        and _safe(delivery.get("receipt_key"))
    )


PENDING_INPUTS = {
    "subject": ("selfshot2_subject_input", "subject"),
    "preserve": ("selfshot2_preserve_input", "preserve"),
    "scene_count": ("selfshot2_scene_count_input", "scene_count"),
    "ratio": ("selfshot2_ratio_input", "ratio"),
    "content": ("selfshot2_content_input", "content_source"),
    "prompt": ("selfshot2_prompt_input", "prompts"),
    "volume": ("selfshot2_volume_input", "volume"),
    "watermark": ("selfshot2_watermark_input", "addons"),
}


def apply_action(state: Mapping[str, Any] | None, operation: str, argument: str = "") -> dict[str, Any]:
    """Apply one canonical callback without side effects or route fall-through."""

    draft = {**initial_draft(), **deepcopy(dict(state or {}))}
    op = _safe(operation)
    arg = _safe(argument)
    current_screen = _safe(draft.get("selfshot2_screen")) or "intro"
    result = {"state": draft, "screen": current_screen, "pending": "", "back": current_screen}
    if op == "subject":
        if arg == "custom":
            result.update({"pending": "subject", "back": "subject"})
            return result
        draft["selfshot2_pending_subject_mode"] = arg
        try:
            manifest = select_subjects(draft.get("source_analysis"), arg)
        except ValueError as exc:
            if str(exc) not in {"person_subject_choice_required", "object_subject_choice_required", "person_object_subject_choice_required"}:
                raise
            draft["selfshot2_selected_subject_ids"] = []
            result["screen"] = "detected"
            return result
        draft["subject_manifest"] = manifest
        draft["preserve_constraints"] = default_preserve_constraints(manifest)
        result["screen"] = "preserve"
        return result
    if op == "subject_id":
        known = {_safe(item.get("subject_id")) for item in detected_subjects(draft.get("source_analysis"))}
        if arg not in known:
            result["screen"] = "detected"
            return result
        selected = list(draft.get("selfshot2_selected_subject_ids") or [])
        selected.remove(arg) if arg in selected else selected.append(arg)
        draft["selfshot2_selected_subject_ids"] = selected
        result["screen"] = "detected"
        return result
    if op == "clear_subject_ids":
        draft["selfshot2_selected_subject_ids"] = []
        result["screen"] = "detected"
        return result
    if op == "confirm_subject_ids":
        manifest = select_subjects(
            draft.get("source_analysis"),
            _safe(draft.get("selfshot2_pending_subject_mode")) or "custom",
            selected_ids=draft.get("selfshot2_selected_subject_ids") or [],
        )
        draft["subject_manifest"] = manifest
        draft["preserve_constraints"] = default_preserve_constraints(manifest)
        result["screen"] = "preserve"
        return result
    if op == "preserve":
        if arg == "custom":
            result.update({"pending": "preserve", "back": "preserve"})
            return result
        if arg in PRESERVE_LABELS:
            rules = dict(draft.get("preserve_constraints") or {})
            rules[arg] = not bool(rules.get(arg))
            draft["preserve_constraints"] = rules
        result["screen"] = "preserve"
        return result
    if op == "preserve_default":
        draft["preserve_constraints"] = default_preserve_constraints(draft.get("subject_manifest"))
        draft.pop("selfshot2_preserve_blocker", None)
        result["screen"] = "review" if screen_parent("preserve", draft) == "review" else "scene_count"
        return result
    if op == "preserve_done":
        gate = preserve_gate(draft.get("subject_manifest"), draft.get("preserve_constraints"))
        if not gate.get("ok"):
            draft["selfshot2_preserve_blocker"] = gate.get("blocker")
            result["screen"] = "preserve"
            return result
        draft.pop("selfshot2_preserve_blocker", None)
        result["screen"] = "review" if screen_parent("preserve", draft) == "review" else "scene_count"
        return result
    if op == "scene_count":
        if arg == "custom":
            result.update({"pending": "scene_count", "back": "scene_count"})
            return result
        if arg == "help":
            result.update({"screen": "scene_count", "notice": "scene_count_help"})
            return result
        count = int(arg or 0)
        if not MIN_SCENES <= count <= MAX_SCENES:
            raise ValueError("scene_count_invalid")
        draft["scene_count"] = count
        result["screen"] = "ratio"
        return result
    if op == "ratio":
        if arg == "custom":
            result.update({"pending": "ratio", "back": "ratio"})
            return result
        if not ratio_valid(arg):
            raise ValueError("aspect_ratio_invalid")
        draft["aspect_ratio"] = arg
        result["screen"] = "content_source"
        return result
    if op == "content_source":
        if arg == "custom":
            draft["content_return_screen"] = current_screen if current_screen in {"scene_plan", "review"} else "content_source"
            result.update({"pending": "content", "back": current_screen})
            return result
        if arg not in {"suggestions", "profiles", "ideas"}:
            raise ValueError("content_source_invalid")
        draft["content_source"] = arg
        if arg == "suggestions":
            # Direct suggestions are a sibling of profiles/ideas. A stale
            # profile parent must not hijack their Back route.
            draft["suggestions_parent"] = "content_source"
        result["screen"] = arg
        return result
    if op in {"profile_page", "suggestion_page", "idea_page"}:
        key = op
        draft[key] = 1 + (int(draft.get(key) or 1) % 4)
        result["screen"] = {"profile_page": "profiles", "suggestion_page": "suggestions", "idea_page": "ideas"}[op]
        return result
    if op == "profile":
        index = int(arg or 0)
        if not 1 <= index <= len(CONTENT_PROFILES):
            raise ValueError("content_profile_invalid")
        draft["selected_profile"] = CONTENT_PROFILES[index - 1]
        draft["suggestion_page"] = 1
        draft["suggestions_parent"] = "profiles"
        result["screen"] = "suggestions"
        return result
    if op == "suggestion":
        catalog = suggestion_catalog(
            draft.get("source_analysis"),
            draft.get("subject_manifest"),
            scene_count=int(draft.get("scene_count") or 1),
            aspect_ratio=_safe(draft.get("aspect_ratio")) or "9:16",
            profile=_safe(draft.get("selected_profile")),
        )
        selected = next((deepcopy(item) for item in catalog if _safe(item.get("id")) == arg), None)
        if not selected:
            raise ValueError("content_suggestion_invalid")
        draft["selected_content"] = selected
        draft["content_return_screen"] = "suggestions"
        result["screen"] = "direction"
        return result
    if op == "idea":
        selected = next((deepcopy(item) for item in idea_presets() if _safe(item.get("id")) == arg), None)
        if not selected:
            raise ValueError("idea_preset_invalid")
        draft["selected_content"] = selected
        draft["selected_profile"] = _safe(selected.get("profile"))
        draft["content_return_screen"] = "ideas"
        result["screen"] = "direction"
        return result
    if op == "direction":
        draft["direction_contract"] = direction_contract(arg)
        draft["selected_direction"] = arg
        draft["scene_plan"] = build_scene_plan(
            analysis=draft.get("source_analysis") or {},
            subject_manifest=draft.get("subject_manifest") or {},
            constraints=draft.get("preserve_constraints") or {},
            scene_count=int(draft.get("scene_count") or 1),
            content=draft.get("selected_content") or {},
            direction=draft.get("direction_contract") or {},
        )
        draft["video_prompts"] = []
        result["screen"] = "scene_plan"
        return result
    if op in {"plan_view", "rebuild_plan"}:
        if op == "plan_view" and current_screen == "review":
            overrides = dict(draft.get("screen_return_overrides") or {})
            overrides["scene_plan"] = "review"
            draft["screen_return_overrides"] = overrides
        if op == "rebuild_plan":
            draft["scene_plan"] = build_scene_plan(
                analysis=draft.get("source_analysis") or {},
                subject_manifest=draft.get("subject_manifest") or {},
                constraints=draft.get("preserve_constraints") or {},
                scene_count=int(draft.get("scene_count") or 1),
                content=draft.get("selected_content") or {},
                direction=draft.get("direction_contract") or {},
            )
            draft["video_prompts"] = []
        result["screen"] = "scene_plan"
        return result
    if op == "compile_prompts":
        draft["video_prompts"] = compile_scene_prompts(
            draft.get("scene_plan") or [],
            subject_manifest=draft.get("subject_manifest") or {},
            content=draft.get("selected_content") or {},
            direction=draft.get("direction_contract") or {},
        )
        result["screen"] = "prompts"
        return result
    if op == "prompt":
        if arg.startswith("edit_"):
            prompt_index = int(arg.replace("edit_", "", 1) or 0)
            prompts = list(draft.get("video_prompts") or [])
            if not 1 <= prompt_index <= len(prompts):
                raise ValueError("selfshot2_prompt_index_invalid")
            draft["prompt_edit_index"] = prompt_index
            result.update({"pending": "prompt", "back": "prompts"})
            return result
        if arg == "custom":
            result.update({"pending": "prompt", "back": "prompts"})
            return result
        result["screen"] = "prompts"
        return result
    if op == "audio_review":
        result["screen"] = "audio"
        return result
    if op == "audio":
        plan = deepcopy(dict(draft.get("audio_plan") or initial_draft()["audio_plan"]))
        if arg == "skip":
            for key in plan:
                plan[key] = {**dict(plan.get(key) or {}), "enabled": False}
            draft["audio_plan"] = plan
            result["screen"] = "addons"
            return result
        if arg not in AUDIO_LABELS:
            raise ValueError("audio_option_invalid")
        plan[arg] = {**dict(plan.get(arg) or {}), "enabled": not bool((plan.get(arg) or {}).get("enabled"))}
        draft["audio_plan"] = plan
        result["screen"] = "audio"
        return result
    if op == "addon":
        addons = deepcopy(dict(draft.get("visual_addons") or initial_draft()["visual_addons"]))
        if arg == "logo":
            result.update({"pending_media": "logo", "back": "addons"})
            return result
        if arg == "watermark":
            result.update({"pending": "watermark", "back": "addons"})
            return result
        if arg == "clear_logo":
            addons["logo"] = deepcopy(initial_draft()["visual_addons"]["logo"])
        elif arg == "clear_watermark":
            addons["watermark"] = deepcopy(initial_draft()["visual_addons"]["watermark"])
        elif arg == "skip":
            addons = deepcopy(initial_draft()["visual_addons"])
        else:
            raise ValueError("selfshot2_addon_invalid")
        draft["visual_addons"] = addons
        result["screen"] = "review" if arg == "skip" else "addons"
        return result
    if op == "addon_position":
        if arg not in {"logo", "watermark"}:
            raise ValueError("selfshot2_addon_position_target_invalid")
        draft["selfshot2_addon_position_target"] = arg
        result["screen"] = "addon_position"
        return result
    if op == "addon_position_set":
        target, separator, position = arg.partition(".")
        valid_positions = {item[0] for item in ADDON_POSITIONS}
        if not separator or target not in {"logo", "watermark"} or position not in valid_positions:
            raise ValueError("selfshot2_addon_position_invalid")
        addons = deepcopy(dict(draft.get("visual_addons") or initial_draft()["visual_addons"]))
        addons[target] = {**dict(addons.get(target) or {}), "position": position}
        draft["visual_addons"] = addons
        result["screen"] = "addons"
        return result
    if op == "volume":
        draft["audio_volume_target"] = arg if arg in AUDIO_LABELS else "source"
        result["screen"] = "volume"
        return result
    if op == "volume_set":
        if arg == "custom":
            result.update({"pending": "volume", "back": "volume"})
            return result
        value = max(0, min(200, int(arg or 100)))
        target = _safe(draft.get("audio_volume_target")) or "source"
        plan = deepcopy(dict(draft.get("audio_plan") or initial_draft()["audio_plan"]))
        plan[target] = {**dict(plan.get(target) or {}), "volume": value}
        draft["audio_plan"] = plan
        result["screen"] = "audio"
        return result
    raise ValueError("selfshot2_operation_invalid")


def _page_rows(items: list[dict[str, Any]], callback: str) -> list[list[tuple[str, str]]]:
    rows = []
    for offset in range(0, len(items), 2):
        rows.append([(str(item["title"]), f"vproduct|ss2|{callback}|{item['id']}") for item in items[offset:offset + 2]])
    return rows


def screen_parent(screen: str, state: Mapping[str, Any] | None = None) -> str:
    name = _safe(screen)
    draft = dict(state or {})
    override = _safe((draft.get("screen_return_overrides") or {}).get(name))
    if override in set(SCREEN_PARENTS) | {"hub"}:
        return override
    if name == "suggestions":
        parent = _safe(draft.get("suggestions_parent"))
        return parent if parent in {"content_source", "profiles"} else "content_source"
    if name == "direction":
        parent = _safe(draft.get("content_return_screen"))
        return parent if parent in {"content_source", "suggestions", "ideas", "scene_plan", "review"} else "content_source"
    return SCREEN_PARENTS.get(name, "intro")


def screen_model(screen: str, state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    draft = {**initial_draft(), **deepcopy(dict(state or {}))}
    name = _safe(screen) or "intro"
    rows: list[list[tuple[str, str]]] = []
    if name == "intro":
        text = (
            "🎥 <b>Video tự quay và đổi cảnh AI</b>\n\nGửi video thật để giữ đúng người, vật, sản phẩm hoặc quan hệ người - vật, "
            "sau đó phát triển thành nhiều cảnh điện ảnh mới. Đây là quy trình dùng video nguồn, không phải chỉ thay nền hoặc tạo từ chữ.\n\n"
            "Chưa có video nguồn thì hệ thống không mở hóa đơn, không tạo tác vụ và không trừ Xu."
        )
        rows = [
            [("📎 Gửi video nguồn", "vproduct|ss2|source"), ("ℹ️ Cách hoạt động", "vproduct|ss2|show|help")],
            [("👁️ Xem dự án đang làm", "vproduct|ss2|show|project"), ("🗑️ Xóa phiên hiện tại", "vproduct|ss2|reset")],
            _nav("hub"),
        ]
    elif name == "help":
        text = "ℹ️ <b>Cách hoạt động</b>\n\nVideo nguồn → chọn người hoặc vật → xác nhận điều cần giữ → chọn số cảnh và tỉ lệ → chọn nội dung → rà câu lệnh từng cảnh → thêm âm thanh, logo hoặc watermark → chọn chất lượng → xem hóa đơn → xác nhận tạo video → theo dõi trạng thái. Chỉ trừ Xu sau khi video hợp lệ đã được gửi thành công."
        rows = [_nav("intro")]
    elif name == "project":
        source = bool(draft.get("source_video"))
        text = f"👁️ <b>Dự án đang làm</b>\n\nVideo nguồn: {'Đã nhận' if source else 'Chưa có'}\nSố cảnh: {draft.get('scene_count') or 'Chưa chọn'}\nTỉ lệ: {draft.get('aspect_ratio') or 'Chưa chọn'}\nChủ thể: {len((draft.get('subject_manifest') or {}).get('subject_ids') or [])} đã xác nhận."
        rows = [_nav("intro")]
    elif name == "analysis":
        report = dict(draft.get("source_analysis") or {})
        text = (
            "🔎 <b>Phân tích video nguồn</b>\n\n"
            f"Thời lượng: {report.get('duration_seconds') or 0:g} giây · Kích thước: {report.get('width') or 0}×{report.get('height') or 0} · Tốc độ hình: {report.get('fps') or 'chưa đọc'}\n"
            f"Người phát hiện: {len(report.get('person_tracks') or [])} · Vật/sản phẩm: {len(report.get('object_tracks') or [])} · Luồng âm thanh: {(report.get('audio_manifest') or {}).get('stream_count') or 0}\n\n"
            "Hệ thống chỉ hiển thị thông tin thực sự đọc được từ video, không tự nhận diện giả."
        )
        rows = [[("✅ Chọn chủ thể", "vproduct|ss2|show|subject"), ("👁️ Xem chủ thể phát hiện", "vproduct|ss2|show|detected")], _nav(screen_parent("analysis", draft))]
    elif name == "subject":
        text = "🎯 <b>Chọn chủ thể cần giữ</b>\n\nNếu video có nhiều người hoặc vật, hãy chọn rõ chủ thể cần theo dõi để giữ nhận diện và mối quan hệ xuyên suốt."
        rows = [
            [("👤 Giữ người", "vproduct|ss2|subject|person"), ("📦 Giữ vật / sản phẩm", "vproduct|ss2|subject|object")],
            [("👤📦 Giữ người và vật", "vproduct|ss2|subject|person_object"), ("🎬 Chỉ giữ chuyển động", "vproduct|ss2|subject|motion_only")],
            [("✍️ Tự mô tả chủ thể", "vproduct|ss2|subject|custom"), ("👁️ Xem chủ thể phát hiện", "vproduct|ss2|show|detected")],
            _nav("analysis"),
        ]
    elif name == "detected":
        items = detected_subjects(draft.get("source_analysis"))
        selected_ids = {_safe(item) for item in draft.get("selfshot2_selected_subject_ids") or []}
        if items:
            lines = [
                f"{index}. {item.get('description') or 'Chủ thể được phát hiện'}"
                for index, item in enumerate(items, 1)
            ]
            text = "👁️ <b>Chủ thể phát hiện</b>\n\n" + "\n".join(lines)
            rows = _page_rows([
                {
                    "id": item.get("subject_id"),
                    "title": f"{'✅' if _safe(item.get('subject_id')) in selected_ids else '□'} {str(item.get('description') or item.get('subject_id'))[:36]}",
                }
                for item in items
            ], "subject_id")
            rows.append([("✅ Dùng chủ thể đã chọn", "vproduct|ss2|confirm_subject_ids"), ("🔄 Chọn lại", "vproduct|ss2|clear_subject_ids")])
        else:
            text = "👁️ <b>Chủ thể phát hiện</b>\n\nHệ thống chưa xác định được người hoặc vật riêng biệt trong video này. Anh/chị có thể chọn một chủ thể gắn với video nguồn hoặc tự mô tả; hệ thống không giả vờ đã nhận diện."
        rows.append(_nav(screen_parent("detected", draft)))
    elif name == "preserve":
        rules = dict(draft.get("preserve_constraints") or {})
        blocker = _safe(draft.get("selfshot2_preserve_blocker"))
        blocker_text = (
            f"\n\n⚠️ {PRESERVE_BLOCKER_MESSAGES.get(blocker, 'Chưa đủ lựa chọn bắt buộc để tiếp tục.')}"
            if blocker else ""
        )
        text = (
            "🔒 <b>Điều phải giữ nguyên</b>\n\n"
            "Nhận diện và quan hệ đã xác nhận phải được giữ xuyên suốt khi các chủ thể xuất hiện cùng nhau."
            f"{blocker_text}"
        )
        keys = list(PRESERVE_LABELS)
        for offset in range(0, len(keys), 2):
            rows.append([(f"{'✅' if rules.get(key) else '□'} {PRESERVE_LABELS[key]}", f"vproduct|ss2|preserve|{key}") for key in keys[offset:offset + 2]])
        rows.extend([[('✅ Hoàn tất lựa chọn', 'vproduct|ss2|preserve_done'), ('⏭️ Dùng mặc định', 'vproduct|ss2|preserve_default')], _nav(screen_parent("preserve", draft))])
    elif name == "scene_count":
        text = "🎬 <b>Chọn số cảnh đầu ra</b>\n\nSố cảnh đầu ra không nhất thiết bằng số đoạn trong video nguồn; mỗi cảnh sẽ ghi rõ đoạn nguồn được dùng."
        rows = [
            [("1 cảnh", "vproduct|ss2|scene_count|1"), ("2 cảnh", "vproduct|ss2|scene_count|2")],
            [("3 cảnh", "vproduct|ss2|scene_count|3"), ("5 cảnh", "vproduct|ss2|scene_count|5")],
            [("10 cảnh", "vproduct|ss2|scene_count|10"), ("✍️ Nhập số khác", "vproduct|ss2|scene_count|custom")],
            [("ℹ️ Lưu ý số cảnh", "vproduct|ss2|scene_count|help"), ("👁️ Xem video nguồn", "vproduct|ss2|show|analysis")],
            _nav("preserve"),
        ]
    elif name == "ratio":
        text = f"📐 <b>Chọn tỉ lệ</b>\n\nĐang chọn: {draft.get('aspect_ratio') or 'Chưa chọn'}."
        rows = [
            [("Dọc 9:16", "vproduct|ss2|ratio|9:16"), ("Ngang 16:9", "vproduct|ss2|ratio|16:9")],
            [("Vuông 1:1", "vproduct|ss2|ratio|1:1"), ("Dọc 4:5", "vproduct|ss2|ratio|4:5")],
            [("✍️ Tự nhập", "vproduct|ss2|ratio|custom"), ("👁️ Xem video nguồn", "vproduct|ss2|show|analysis")],
            _nav("scene_count"),
        ]
    elif name == "content_source":
        text = "🧭 <b>Chọn cách xây nội dung</b>\n\nMỗi nhánh đều giữ nguyên chủ thể đã xác nhận từ video nguồn."
        rows = [
            [("💡 5 gợi ý quanh video", "vproduct|ss2|content_source|suggestions"), ("🎯 Chọn loại nội dung", "vproduct|ss2|content_source|profiles")],
            [("🗂️ Kho Ý tưởng video", "vproduct|ss2|content_source|ideas"), ("✍️ Tự nhập nội dung", "vproduct|ss2|content_source|custom")],
            _nav("ratio"),
        ]
    elif name == "suggestions":
        items = suggestion_catalog(draft.get("source_analysis"), draft.get("subject_manifest"), scene_count=int(draft.get("scene_count") or 1), aspect_ratio=_safe(draft.get("aspect_ratio")) or "9:16", profile=_safe(draft.get("selected_profile")))
        page = max(1, min(4, int(draft.get("suggestion_page") or 1)))
        shown = suggestion_page(items, page)
        text = "💡 <b>5 gợi ý quanh video</b>\n\n" + "\n".join(f"{index}. {item['title']}: {item['summary']}" for index, item in enumerate(shown, 1))
        rows = [[(str(index), f"vproduct|ss2|suggestion|{item['id']}") for index, item in enumerate(shown, 1)]]
        rows.extend([
            [('🔄 Đổi 5 gợi ý', 'vproduct|ss2|suggestion_page'), ('✍️ Tự nhập', 'vproduct|ss2|content_source|custom')],
            _nav(screen_parent("suggestions", draft)),
        ])
    elif name == "profiles":
        page = max(1, min(4, int(draft.get("profile_page") or 1)))
        chunk = CONTENT_PROFILES[(page - 1) * 8:page * 8]
        text = f"🎯 <b>Chọn loại nội dung</b>\n\nTrang {page}/4 trong 32 loại. Chọn một loại để nhận 5 gợi ý bám sát video nguồn."
        rows = _page_rows([{"id": str((page - 1) * 8 + index), "title": title} for index, title in enumerate(chunk, 1)], "profile")
        rows.extend([[('➡️ Nhóm sau', 'vproduct|ss2|profile_page'), ('✍️ Tự nhập nội dung', 'vproduct|ss2|content_source|custom')], _nav("content_source")])
    elif name == "ideas":
        page = max(1, min(4, int(draft.get("idea_page") or 1)))
        chunk = idea_presets()[(page - 1) * 5:page * 5]
        text = f"🗂️ <b>Kho Ý tưởng video</b>\n\nTrang {page}/4. Mỗi ý tưởng sẽ kết hợp với người, vật và chuyển động nguồn; không hỏi lại loại nội dung đã có."
        rows = _page_rows(chunk, "idea")
        rows.extend([[('➡️ Nhóm sau', 'vproduct|ss2|idea_page'), ('✍️ Tự nhập nội dung', 'vproduct|ss2|content_source|custom')], _nav("content_source")])
    elif name == "direction":
        text = "✨ <b>Chọn hướng biến đổi</b>\n\nMỗi hướng cần khả năng xử lý khác nhau. Nếu hệ thống chưa đáp ứng, video sẽ được chặn trước hóa đơn và không trừ Xu."
        for offset in range(0, len(DIRECTION_OPTIONS), 2):
            rows.append([(item[1], f"vproduct|ss2|direction|{item[0]}") for item in DIRECTION_OPTIONS[offset:offset + 2]])
        rows.append(_nav(screen_parent("direction", draft)))
    elif name == "scene_plan":
        plan = list(draft.get("scene_plan") or [])
        lines = [f"Cảnh {item.get('scene_index')}: dùng đoạn {item.get('source_segment_start')}–{item.get('source_segment_end')} giây · {item.get('end_state')}" for item in plan]
        text = "🎬 <b>Kế hoạch cảnh</b>\n\n" + ("\n".join(lines) if lines else "Chưa có kế hoạch.")
        rows = [[('👁️ Xem từng cảnh', 'vproduct|ss2|plan_view'), ('✍️ Sửa nội dung', 'vproduct|ss2|content_source|custom')], [('✅ Tạo câu lệnh từng cảnh', 'vproduct|ss2|compile_prompts'), ('🔄 Lập lại kế hoạch', 'vproduct|ss2|rebuild_plan')], _nav(screen_parent("scene_plan", draft))]
    elif name == "prompts":
        prompts = list(draft.get("video_prompts") or [])
        text = "📝 Câu lệnh video từng cảnh\n\n" + "\n\n".join(f"Cảnh {item.get('scene_index')}:\n{item.get('prompt')}\nĐiều cần tránh:\n{item.get('negative_prompt')}" for item in prompts)
        prompt_buttons = [
            (str(item.get("scene_index") or index), f"vproduct|ss2|prompt|edit_{index}")
            for index, item in enumerate(prompts, 1)
        ]
        rows = [prompt_buttons[offset:offset + 2] for offset in range(0, len(prompt_buttons), 2)]
        if rows and len(rows[-1]) == 1:
            rows[-1].append(('↩️ Tạo lại tất cả', 'vproduct|ss2|compile_prompts'))
            rows.append([('✅ Hoàn tất câu lệnh', 'vproduct|ss2|show|audio'), ('🎬 Menu Video', 'menu|main_video')])
        else:
            rows.append([('↩️ Tạo lại tất cả', 'vproduct|ss2|compile_prompts'), ('✅ Hoàn tất câu lệnh', 'vproduct|ss2|show|audio')])
        rows.append(_nav(screen_parent("prompts", draft)))
    elif name == "audio":
        plan = dict(draft.get("audio_plan") or {})
        text = "🎚️ <b>Âm thanh và phần bổ sung</b>\n\nMỗi mục có thể đặt âm lượng từ 0–200%. Hệ thống chỉ áp dụng những mục anh/chị bật."
        keys = list(AUDIO_LABELS)
        for offset in range(0, len(keys), 2):
            rows.append([(f"{'✅' if (plan.get(key) or {}).get('enabled') else '□'} {AUDIO_LABELS[key]}", f"vproduct|ss2|audio|{key}") for key in keys[offset:offset + 2]])
        if len(rows[-1]) == 1:
            rows[-1].append(("👁️ Xem cấu hình", "vproduct|ss2|audio_review"))
        rows.extend([
            [('🔊 Âm lượng gốc', 'vproduct|ss2|volume|source'), ('🎙️ Âm lượng lồng tiếng', 'vproduct|ss2|volume|voice')],
            [('🎵 Âm lượng nhạc', 'vproduct|ss2|volume|music'), ('💥 Âm lượng hiệu ứng', 'vproduct|ss2|volume|sfx')],
            [('✅ Hoàn tất âm thanh', 'vproduct|ss2|show|addons'), ('⏭️ Bỏ qua', 'vproduct|ss2|audio|skip')],
            _nav(screen_parent("audio", draft)),
        ])
    elif name == "volume":
        target = _safe(draft.get("audio_volume_target")) or "source"
        text = f"🔊 <b>Âm lượng {AUDIO_LABELS.get(target, target)}</b>\n\nChọn mức từ 0–200%. Hệ thống sẽ giữ âm thanh trong ngưỡng an toàn khi hậu kỳ."
        rows = [[(f"{value}%", f"vproduct|ss2|volume_set|{value}") for value in (0, 50)], [(f"{value}%", f"vproduct|ss2|volume_set|{value}") for value in (100, 150)], [("200%", "vproduct|ss2|volume_set|200"), ("✍️ Tự nhập", "vproduct|ss2|volume_set|custom")], _nav("audio")]
    elif name == "addons":
        addons = dict(draft.get("visual_addons") or {})
        logo = dict(addons.get("logo") or {})
        watermark = dict(addons.get("watermark") or {})
        text = (
            "🖼️ <b>Logo và watermark</b>\n\n"
            f"Logo: {'Đã nhận' if logo.get('enabled') and logo.get('file_id') else 'Tắt'} · vị trí {ADDON_POSITION_LABELS.get(logo.get('position') or '', 'Chưa chọn')}\n"
            f"Watermark: {'Đã có nội dung' if watermark.get('enabled') and watermark.get('text') else 'Tắt'} · vị trí {ADDON_POSITION_LABELS.get(watermark.get('position') or '', 'Chưa chọn')}\n\n"
            "Màn này chỉ lưu cấu hình; chưa tạo tệp, chưa xử lý video và chưa trừ Xu."
        )
        rows = [
            [("📎 Gửi logo hình ảnh", "vproduct|ss2|addon|logo"), ("✍️ Watermark chữ", "vproduct|ss2|addon|watermark")],
            [("📍 Vị trí logo", "vproduct|ss2|addon_position|logo"), ("📍 Vị trí watermark", "vproduct|ss2|addon_position|watermark")],
            [("🗑️ Xóa logo", "vproduct|ss2|addon|clear_logo"), ("🗑️ Xóa watermark", "vproduct|ss2|addon|clear_watermark")],
        ]
        if screen_parent("addons", draft) != "review":
            rows.append([("✅ Hoàn tất bổ sung", "vproduct|ss2|show|review"), ("⏭️ Bỏ qua", "vproduct|ss2|addon|skip")])
        rows.append(_nav(screen_parent("addons", draft)))
    elif name == "addon_position":
        target = _safe(draft.get("selfshot2_addon_position_target")) or "logo"
        label = "logo" if target == "logo" else "watermark"
        text = f"📍 <b>Vị trí {label}</b>\n\nChọn một vị trí cố định, an toàn trong khung hình."
        rows = []
        for offset in range(0, len(ADDON_POSITIONS), 2):
            rows.append([
                (position_label, f"vproduct|ss2|addon_position_set|{target}.{position_id}")
                for position_id, position_label in ADDON_POSITIONS[offset:offset + 2]
            ])
        rows.append(_nav("addons"))
    elif name == "review":
        text = (
            "👁️ <b>Xem lại Video tự quay và đổi cảnh AI</b>\n\n"
            f"Chủ thể: {len((draft.get('subject_manifest') or {}).get('subject_ids') or [])} · Cảnh: {draft.get('scene_count') or 0} · Tỉ lệ: {draft.get('aspect_ratio') or '-'}\n"
            f"Nội dung: {(draft.get('selected_content') or {}).get('title') or '-'} · Hướng: {(draft.get('direction_contract') or {}).get('label') or '-'}\n\n"
            "Chưa tạo tác vụ, chưa xử lý video và chưa trừ Xu."
        )
        rows = [
            [('👁️ Xem từng cảnh', 'vproduct|ss2|plan_view'), ('✍️ Sửa nội dung cảnh', 'vproduct|ss2|content_source|custom')],
            [('👤 Người / vật giữ nguyên', 'vproduct|ss2|show|preserve'), ('🎬 Câu lệnh video', 'vproduct|ss2|show|prompts')],
            [('🎚️ Âm thanh', 'vproduct|ss2|show|audio'), ('✨ Hiệu ứng', 'vproduct|ss2|show|direction')],
            [('🖼️ Logo / Watermark', 'vproduct|ss2|review_addons'), ('⭐ Chọn chất lượng', 'vproduct|ss2|finish')],
            _nav("addons"),
        ]
    elif name == "finish":
        report = dict(draft.get("selfshot2_preflight") or {})
        scene_count = max(1, int(draft.get("scene_count") or 1))
        if report.get("ok"):
            status_text = "Kế hoạch đã đủ điều kiện. Chọn một gói để xem hóa đơn."
        else:
            status_text = "Kế hoạch còn thiếu dữ liệu bắt buộc. Vui lòng quay lại kiểm tra trước khi mở hóa đơn."
        quality_rows = video_ai_real_pricing.public_quality_catalog()
        lines = [
            "⭐ <b>Chọn chất lượng video</b>",
            "",
            status_text,
            f"Sản phẩm dùng video nguồn · <b>{scene_count} cảnh</b>.",
            "Khuyến mãi Video nhiều cảnh: 1 cảnh không giảm; 2–5 cảnh giảm 10%; 6–10 cảnh giảm 15%; 11–20 cảnh giảm 20%; add-on tính riêng.",
        ]
        buttons: list[tuple[str, str]] = []
        for quality in quality_rows:
            scene_price = video_ai_real_pricing.video_multiscene_price(quality["unit_xu"], scene_count)
            discount_note = (
                f" · giảm {scene_price['discount_percent']}% (-{scene_price['discount_xu']} Xu)"
                if scene_price["discount_percent"]
                else ""
            )
            lines.extend([
                "",
                f"{quality['icon']} <b>{quality['name']}</b> · <b>{quality['seconds']} giây/cảnh</b> · <b>{quality['unit_xu']} Xu/cảnh</b>",
                f"• Chất lượng: {quality['public_level']} · {quality['resolution']}",
                f"• Đặc điểm: {quality['public_detail']}",
                f"• Phù hợp: {quality['use_case']}",
                f"• Tạm tính {scene_count} cảnh: <b>{scene_price['subtotal_xu']} Xu</b>"
                f"{discount_note} · còn <b>{scene_price['total_xu']} Xu</b>",
            ])
            buttons.append((
                f"{quality['icon']} {quality['name']} · {quality['unit_xu']} Xu",
                f"vproduct|ss2|quality|{quality['tier_id']}",
            ))
        lines.extend(["", "Màn này chưa tạo tác vụ và chưa trừ Xu."])
        text = "\n".join(lines)
        rows = [buttons[offset:offset + 2] for offset in range(0, len(buttons), 2)]
        if len(rows[-1]) == 1:
            rows[-1].append(("🔄 Kiểm tra lại", "vproduct|ss2|finish"))
        rows.append(_nav("review"))
    else:
        return screen_model("intro", draft)
    return {"screen": name, "text": text, "rows": rows, "parent": screen_parent(name, draft)}


def callback_allowed(screen: str, callback_data: str, state: Mapping[str, Any] | None = None) -> bool:
    """Return whether a callback belongs to the currently rendered screen."""

    model = screen_model(screen, state)
    allowed = {
        _safe(callback)
        for row in model.get("rows") or []
        for _label, callback in row
    }
    return _safe(callback_data) in allowed


def validate_rows(rows: Iterable[Iterable[tuple[str, str]]], *, back_callback: str) -> dict[str, Any]:
    callbacks = []
    errors = []
    for row_index, row in enumerate(rows):
        buttons = list(row)
        if len(buttons) > 2 and not (len(buttons) == 5 and all(str(label).isdigit() for label, _ in buttons)):
            errors.append(f"row_{row_index}_layout_invalid")
        for label, callback in buttons:
            if not _safe(label) or not _safe(callback):
                errors.append(f"row_{row_index}_button_invalid")
            callbacks.append(_safe(callback))
    if back_callback not in callbacks:
        errors.append("exact_back_missing")
    if len(callbacks) != len(set(callbacks)):
        errors.append("duplicate_callback")
    return {"ok": not errors, "errors": errors, "callbacks": callbacks}


def route_matrix() -> dict[str, dict[str, str]]:
    return {
        screen: {
            "owner": "selfshot2",
            "back": "vproduct|selfshot_hub" if parent == "hub" else f"vproduct|ss2|show|{parent}",
        }
        for screen, parent in SCREEN_PARENTS.items()
    }
