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


PRODUCT_ID = "self_shot_scene_change"
JOB_TYPE = "self_shot_scene_change"
MODE = "person_object_cinematic"
MIN_SCENES = 1
MAX_SCENES = 20
SCENE_SECONDS = 8
SUPPORTED_RATIOS = frozenset({"9:16", "16:9", "1:1", "4:5"})
SUBJECT_MODES = frozenset({"person", "object", "person_object", "motion_only", "custom"})

CONTENT_PROFILES = (
    "Ban hang / quang cao", "Review / demo san pham", "Affiliate / UGC",
    "Testimonial / case study", "Thuong hieu / doanh nghiep", "Social creator / bat trend",
    "Meme / parody / hai", "Su kien / highlight", "Kien truc ngoai that", "Noi that",
    "Cai tao khong gian", "Bat dong san", "Video tham quan kien truc", "Hieu ung dien anh",
    "Hoat hinh 2D/3D", "Nhan vat", "Thoi trang / trinh dien", "Trung bay san pham / 3D",
    "Ung dung / tro choi", "Website / phan mem", "Huong dan / giai thich",
    "Noi dung nguoi dung / mang xa hoi", "Lich su / van hoa", "The thao / eSports",
    "Du lich / dia phuong", "Ky thuat / cong nghiep", "Tin tuc / du lieu",
    "Dong luc / phat trien ban than", "Am thuc", "Giao duc / kien thuc",
    "Am nhac / su kien", "ASMR / thu gian",
)

CONTENT_DIRECTIONS = (
    ("future_world", "Thanh pho tuong lai", "Doi the gioi xung quanh sang mot thanh pho tuong lai lien mach."),
    ("ancient_world", "The gioi co dai", "Giu chu the va hanh dong, thay kien truc va anh sang thanh boi canh co dai."),
    ("fantasy_world", "The gioi gia tuong", "Mo rong khong gian thanh mot the gioi gia tuong co chieu sau dien anh."),
    ("space_world", "Khong gian vu tru", "Dat chu the vao tau vu tru hoac hanh tinh moi ma khong mat tuong tac goc."),
    ("post_apocalyptic", "Hau tan the", "Giu nguoi/vat va chuyen dong, thay moi truong thanh hau tan the co nguyen nhan ro."),
    ("nature_cinema", "Thien nhien dien anh", "Mo rong canh quan, thoi tiet va anh sang tu nhien quanh chu the."),
    ("action_story", "Phim hanh dong", "Bien hanh dong goc thanh mot nhip phim hanh dong co mo dau va ket thuc tron ven."),
    ("mystery_story", "Phim trinh tham", "Bien cac chi tiet trong video nguon thanh manh moi va cau chuyen trinh tham."),
    ("adventure_story", "Phim phieu luu", "Dung chuyen dong nguon lam diem bat dau cho hanh trinh kham pha."),
    ("romance_story", "Phim lang man", "Giu bieu cam va khoang cach chu the, thay doi khong gian theo mach cam xuc."),
    ("light_comedy", "Hai tinh huong", "Giu hanh dong that va tao tinh huong hai ro rang, khong che nhan vat."),
    ("light_horror", "Kinh di nhe", "Them anh sang, am thanh va chi tiet hoi hop ma khong bien dang chu the."),
    ("character_trailer", "Trailer nhan vat", "Gioi thieu chu the qua nhieu canh lien quan, giu nhan dien xuyen suot."),
    ("same_action_new_world", "Giu hanh dong, doi boi canh", "Dung dung hanh dong nguon trong moi boi canh moi."),
    ("world_expansion", "Mo rong the gioi", "Them kien truc, phuong tien, quan chung va thoi tiet quanh chu the."),
    ("product_hero", "San pham lam trung tam", "Giu hinh dang, logo va cach cam/su dung san pham trong khong gian cao cap."),
    ("product_demo", "Quang cao cach su dung", "Theo sat thao tac that va lam ro cong dung cua san pham."),
    ("before_after", "Truoc va sau", "Giu cung chu the de thay doi boi canh hoac trang thai duoc nhin thay ro."),
    ("person_object_story", "Nguoi va vat cung ke chuyen", "Giu diem tiep xuc va vai tro cua vat trong cau chuyen quanh nguoi."),
    ("fashion_character", "Thoi trang / nhan vat", "Doi cach trinh bay, boi canh va anh sang trong khi giu chu the da xac nhan."),
)

DIRECTION_OPTIONS = (
    ("environment", "🌍 Doi boi canh", ("video_to_video", "environment_replacement")),
    ("new_story", "🎬 Tao cau chuyen moi", ("video_to_video", "video_reference")),
    ("cinematic_effects", "✨ Them hieu ung dien anh", ("video_to_video", "video_reference")),
    ("world_expand", "🏙️ Mo rong khong gian", ("video_to_video", "environment_replacement")),
    ("product_focus", "📦 Lam noi bat san pham", ("video_to_video", "object_reference", "product_logo_preservation")),
    ("character_transform", "👤 Bien doi nhan vat", ("video_to_video", "person_identity_preservation")),
    ("source_camera", "🎥 Giu may quay nguon", ("video_to_video", "camera_motion_transfer")),
    ("redirect_camera", "🎞️ Dao dien lai camera", ("video_to_video", "video_reference")),
)

PRESERVE_LABELS = {
    "person_identity": "👤 Nhan dien nguoi",
    "object_identity": "📦 Nhan dien vat",
    "wardrobe_color": "👕 Trang phuc/mau",
    "action_expression": "🎭 Hanh dong/bieu cam",
    "person_object_relation": "🔗 Quan he nguoi-vat",
    "custom": "✍️ Yeu cau khac",
}

AUDIO_LABELS = {
    "source": "🔊 Am thanh goc",
    "voice": "🎙️ Long tieng",
    "music": "🎵 Nhac nen",
    "sfx": "💥 Hieu ung am thanh",
    "subtitle": "💬 Phu de",
}

ADDON_POSITIONS = (
    ("top_left", "Tren trai"),
    ("top_right", "Tren phai"),
    ("middle_left", "Giua trai"),
    ("middle_right", "Giua phai"),
    ("bottom_left", "Duoi trai"),
    ("bottom_right", "Duoi phai"),
)

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
    return [("⬅️ Quay lai", callback), ("🏠 Menu chinh", "menu|main")]


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
    subject_text = ", ".join(_safe(item.get("description")) for item in manifest.get("subjects") or []) or "chuyen dong nguon"
    action_text = ", ".join(_safe(item) for item in report.get("main_actions") or []) or "hanh dong dang co trong video"
    count = max(MIN_SCENES, min(MAX_SCENES, int(scene_count or 1)))
    ratio = aspect_ratio if ratio_valid(aspect_ratio) else "9:16"
    profile_text = _safe(profile) or "noi dung phu hop video nguon"
    items = []
    for index, (item_id, title, summary) in enumerate(CONTENT_DIRECTIONS, 1):
        items.append({
            "id": item_id,
            "index": index,
            "title": title,
            "summary": f"{summary} Giu {subject_text}; bam {action_text}; dung {count} canh {ratio}; theo {profile_text}.",
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
            "🎥 <b>Tu quay & doi canh AI</b>\n\nGui video that de giu dung nguoi, vat/san pham hoac quan he nguoi-vat, "
            "sau do phat trien nhieu canh dien anh moi. Khong phai thay nen don gian va khong dung flow text-only.\n\n"
            "Chua co video thi khong tao hoa don, tac vu hay tru Xu."
        )
        rows = [
            [("📎 Gui video nguon", "vproduct|ss2|source"), ("ℹ️ Cach hoat dong", "vproduct|ss2|show|help")],
            [("👁️ Xem du an dang lam", "vproduct|ss2|show|project"), ("🗑️ Xoa phien hien tai", "vproduct|ss2|reset")],
            _nav("hub"),
        ]
    elif name == "help":
        text = "ℹ️ <b>Cach hoat dong</b>\n\nVideo nguon → chon nguoi/vat → khoa dieu can giu → chia canh → noi dung → prompt → engine phu hop → MP4 → gui thanh cong → moi tru Xu."
        rows = [_nav("intro")]
    elif name == "project":
        source = bool(draft.get("source_video"))
        text = f"👁️ <b>Du an dang lam</b>\n\nVideo nguon: {'Da nhan' if source else 'Chua co'}\nSo canh: {draft.get('scene_count') or 'Chua chon'}\nTi le: {draft.get('aspect_ratio') or 'Chua chon'}\nChu the: {len((draft.get('subject_manifest') or {}).get('subject_ids') or [])} da xac nhan."
        rows = [_nav("intro")]
    elif name == "analysis":
        report = dict(draft.get("source_analysis") or {})
        text = (
            "🔎 <b>Phan tich video nguon</b>\n\n"
            f"Thoi luong: {report.get('duration_seconds') or 0:g}s · Khung: {report.get('width') or 0}x{report.get('height') or 0} · FPS: {report.get('fps') or 'chua doc'}\n"
            f"Nguoi tim thay: {len(report.get('person_tracks') or [])} · Vat/san pham: {len(report.get('object_tracks') or [])} · Am thanh: {(report.get('audio_manifest') or {}).get('stream_count') or 0} stream\n\n"
            "Chi hien thong tin local/metadata thuc su co; khong bia nhan dien."
        )
        rows = [[("✅ Chon chu the", "vproduct|ss2|show|subject"), ("👁️ Xem chu the phat hien", "vproduct|ss2|show|detected")], _nav(screen_parent("analysis", draft))]
    elif name == "subject":
        text = "🎯 <b>Chon chu the can giu</b>\n\nNeu video co nhieu nguoi/vat, he thong bat buoc chon subject_id ro rang; khong ghi chung chung 'theo nguoi'."
        rows = [
            [("👤 Giu nguoi", "vproduct|ss2|subject|person"), ("📦 Giu vat/san pham", "vproduct|ss2|subject|object")],
            [("👤📦 Giu ca nguoi va vat", "vproduct|ss2|subject|person_object"), ("🎬 Chi giu chuyen dong", "vproduct|ss2|subject|motion_only")],
            [("✍️ Tu mo ta chu the", "vproduct|ss2|subject|custom"), ("👁️ Xem chu the phat hien", "vproduct|ss2|show|detected")],
            _nav("analysis"),
        ]
    elif name == "detected":
        items = detected_subjects(draft.get("source_analysis"))
        selected_ids = {_safe(item) for item in draft.get("selfshot2_selected_subject_ids") or []}
        if items:
            lines = [f"{index}. {item.get('subject_id')} — {item.get('description')}" for index, item in enumerate(items, 1)]
            text = "👁️ <b>Chu the phat hien</b>\n\n" + "\n".join(lines)
            rows = _page_rows([
                {
                    "id": item.get("subject_id"),
                    "title": f"{'✅' if _safe(item.get('subject_id')) in selected_ids else '□'} {str(item.get('description') or item.get('subject_id'))[:36]}",
                }
                for item in items
            ], "subject_id")
            rows.append([("✅ Dung chu the da chon", "vproduct|ss2|confirm_subject_ids"), ("🔄 Chon lai", "vproduct|ss2|clear_subject_ids")])
        else:
            text = "👁️ <b>Chu the phat hien</b>\n\nRuntime local chua co track nguoi/vat. Anh/chi co the xac nhan mot chu the gan voi video nguon hoac tu mo ta; he thong khong gia vo da nhan dien."
        rows.append(_nav(screen_parent("detected", draft)))
    elif name == "preserve":
        rules = dict(draft.get("preserve_constraints") or {})
        blocker = _safe(draft.get("selfshot2_preserve_blocker"))
        blocker_text = f"\n\n⚠️ Chua the tiep tuc: <code>{blocker}</code>." if blocker else ""
        text = (
            "🔒 <b>Dieu phai giu nguyen</b>\n\n"
            "Cac khoa nhan dien va quan he bat buoc khong the tat neu chu the dang dung chung."
            f"{blocker_text}"
        )
        keys = list(PRESERVE_LABELS)
        for offset in range(0, len(keys), 2):
            rows.append([(f"{'✅' if rules.get(key) else '□'} {PRESERVE_LABELS[key]}", f"vproduct|ss2|preserve|{key}") for key in keys[offset:offset + 2]])
        rows.extend([[('✅ Xong giu nguyen', 'vproduct|ss2|preserve_done'), ('⏭️ Dung mac dinh', 'vproduct|ss2|preserve_default')], _nav(screen_parent("preserve", draft))])
    elif name == "scene_count":
        text = "🎬 <b>Chon so canh dau ra</b>\n\nSo canh dau ra khong nhat thiet bang so shot nguon; moi canh ghi ro doan nguon duoc dung."
        rows = [
            [("1 canh", "vproduct|ss2|scene_count|1"), ("2 canh", "vproduct|ss2|scene_count|2")],
            [("3 canh", "vproduct|ss2|scene_count|3"), ("5 canh", "vproduct|ss2|scene_count|5")],
            [("10 canh", "vproduct|ss2|scene_count|10"), ("✍️ Nhap so khac", "vproduct|ss2|scene_count|custom")],
            [("ℹ️ Luu y so canh", "vproduct|ss2|scene_count|help"), ("👁️ Xem video nguon", "vproduct|ss2|show|analysis")],
            _nav("preserve"),
        ]
    elif name == "ratio":
        text = f"📐 <b>Chon ti le</b>\n\nDang chon: {draft.get('aspect_ratio') or 'Chua chon'}. Khong co nut goi y ti le."
        rows = [
            [("Doc 9:16", "vproduct|ss2|ratio|9:16"), ("Ngang 16:9", "vproduct|ss2|ratio|16:9")],
            [("Vuong 1:1", "vproduct|ss2|ratio|1:1"), ("Doc 4:5", "vproduct|ss2|ratio|4:5")],
            [("✍️ Tu nhap", "vproduct|ss2|ratio|custom"), ("👁️ Xem video nguon", "vproduct|ss2|show|analysis")],
            _nav("scene_count"),
        ]
    elif name == "content_source":
        text = "🧭 <b>Chon cach xay noi dung</b>\n\nMoi nhanh giu nguyen subject lock da xac nhan."
        rows = [
            [("💡 5 goi y quanh video", "vproduct|ss2|content_source|suggestions"), ("🎯 Chon loai noi dung", "vproduct|ss2|content_source|profiles")],
            [("🗂️ Kho Y tuong video", "vproduct|ss2|content_source|ideas"), ("✍️ Tu nhap noi dung", "vproduct|ss2|content_source|custom")],
            _nav("ratio"),
        ]
    elif name == "suggestions":
        items = suggestion_catalog(draft.get("source_analysis"), draft.get("subject_manifest"), scene_count=int(draft.get("scene_count") or 1), aspect_ratio=_safe(draft.get("aspect_ratio")) or "9:16", profile=_safe(draft.get("selected_profile")))
        page = max(1, min(4, int(draft.get("suggestion_page") or 1)))
        shown = suggestion_page(items, page)
        text = "💡 <b>5 goi y quanh video</b>\n\n" + "\n".join(f"{index}. {item['title']}: {item['summary']}" for index, item in enumerate(shown, 1))
        rows = [[(str(index), f"vproduct|ss2|suggestion|{item['id']}") for index, item in enumerate(shown, 1)]]
        rows.extend([
            [('🔄 Doi 5 goi y', 'vproduct|ss2|suggestion_page'), ('✍️ Tu nhap', 'vproduct|ss2|content_source|custom')],
            _nav(screen_parent("suggestions", draft)),
        ])
    elif name == "profiles":
        page = max(1, min(4, int(draft.get("profile_page") or 1)))
        chunk = CONTENT_PROFILES[(page - 1) * 8:page * 8]
        text = f"🎯 <b>Chon loai noi dung</b>\n\nTrang {page}/4 trong 32 loai. Chon dung mot loai de nhan 5 goi y bam video nguon."
        rows = _page_rows([{"id": str((page - 1) * 8 + index), "title": title} for index, title in enumerate(chunk, 1)], "profile")
        rows.extend([[('➡️ Nhom sau', 'vproduct|ss2|profile_page'), ('✍️ Tu nhap noi dung', 'vproduct|ss2|content_source|custom')], _nav("content_source")])
    elif name == "ideas":
        page = max(1, min(4, int(draft.get("idea_page") or 1)))
        chunk = idea_presets()[(page - 1) * 5:page * 5]
        text = f"🗂️ <b>Kho Y tuong video</b>\n\nTrang {page}/4. Preset se ket hop voi nguoi/vat va chuyen dong nguon; khong hoi lai profile co san."
        rows = _page_rows(chunk, "idea")
        rows.extend([[('➡️ Nhom sau', 'vproduct|ss2|idea_page'), ('✍️ Tu nhap noi dung', 'vproduct|ss2|content_source|custom')], _nav("content_source")])
    elif name == "direction":
        text = "✨ <b>Chon huong bien doi</b>\n\nMoi huong ghi ro capability can co. Thieu engine phu hop se chan truoc hoa don."
        for offset in range(0, len(DIRECTION_OPTIONS), 2):
            rows.append([(item[1], f"vproduct|ss2|direction|{item[0]}") for item in DIRECTION_OPTIONS[offset:offset + 2]])
        rows.append(_nav(screen_parent("direction", draft)))
    elif name == "scene_plan":
        plan = list(draft.get("scene_plan") or [])
        lines = [f"Canh {item.get('scene_index')}: nguon {item.get('source_segment_start')}–{item.get('source_segment_end')}s · {item.get('end_state')}" for item in plan]
        text = "🎬 <b>Ke hoach canh</b>\n\n" + ("\n".join(lines) if lines else "Chua co ke hoach.")
        rows = [[('👁️ Xem tung canh', 'vproduct|ss2|plan_view'), ('✍️ Sua noi dung', 'vproduct|ss2|content_source|custom')], [('✅ Tao prompt tung canh', 'vproduct|ss2|compile_prompts'), ('🔄 Lap lai ke hoach', 'vproduct|ss2|rebuild_plan')], _nav(screen_parent("scene_plan", draft))]
    elif name == "prompts":
        prompts = list(draft.get("video_prompts") or [])
        text = "📝 <b>Prompt video tung canh</b>\n\n" + "\n\n".join(f"Canh {item.get('scene_index')}: {item.get('prompt')}\nLoai tru: {item.get('negative_prompt')}" for item in prompts[:3])
        if len(prompts) > 3:
            text += f"\n\n... con {len(prompts) - 3} canh."
        rows = [[('👁️ Xem day du', 'vproduct|ss2|prompt|full'), ('✍️ Sua noi dung', 'vproduct|ss2|prompt|custom')], [('✅ Xong prompt', 'vproduct|ss2|show|audio'), ('↩️ Tao lai prompt', 'vproduct|ss2|compile_prompts')], _nav(screen_parent("prompts", draft))]
    elif name == "audio":
        plan = dict(draft.get("audio_plan") or {})
        text = "🎚️ <b>Am thanh va add-on</b>\n\nMoi muc am luong 0–200%. Khong tuy bo tach stem neu runtime khong co."
        keys = list(AUDIO_LABELS)
        for offset in range(0, len(keys), 2):
            rows.append([(f"{'✅' if (plan.get(key) or {}).get('enabled') else '□'} {AUDIO_LABELS[key]}", f"vproduct|ss2|audio|{key}") for key in keys[offset:offset + 2]])
        if len(rows[-1]) == 1:
            rows[-1].append(("👁️ Xem cau hinh", "vproduct|ss2|audio_review"))
        rows.extend([
            [('🔊 Am luong goc', 'vproduct|ss2|volume|source'), ('🎙️ Am luong long tieng', 'vproduct|ss2|volume|voice')],
            [('🎵 Am luong nhac', 'vproduct|ss2|volume|music'), ('💥 Am luong hieu ung', 'vproduct|ss2|volume|sfx')],
            [('✅ Xong am thanh', 'vproduct|ss2|show|addons'), ('⏭️ Bo qua', 'vproduct|ss2|audio|skip')],
            _nav(screen_parent("audio", draft)),
        ])
    elif name == "volume":
        target = _safe(draft.get("audio_volume_target")) or "source"
        text = f"🔊 <b>Am luong {AUDIO_LABELS.get(target, target)}</b>\n\nChon 0–200%. Runtime phai clamp va chan clipping khi hau ky."
        rows = [[(f"{value}%", f"vproduct|ss2|volume_set|{value}") for value in (0, 50)], [(f"{value}%", f"vproduct|ss2|volume_set|{value}") for value in (100, 150)], [("200%", "vproduct|ss2|volume_set|200"), ("✍️ Tu nhap", "vproduct|ss2|volume_set|custom")], _nav("audio")]
    elif name == "addons":
        addons = dict(draft.get("visual_addons") or {})
        logo = dict(addons.get("logo") or {})
        watermark = dict(addons.get("watermark") or {})
        text = (
            "🖼️ <b>Logo va watermark</b>\n\n"
            f"Logo: {'Da nhan' if logo.get('enabled') and logo.get('file_id') else 'Tat'} · vi tri {logo.get('position') or 'top_right'}\n"
            f"Watermark: {'Da co noi dung' if watermark.get('enabled') and watermark.get('text') else 'Tat'} · vi tri {watermark.get('position') or 'bottom_right'}\n\n"
            "Chi luu cau hinh; chua tao file, chua goi provider va chua tru Xu."
        )
        rows = [
            [("📎 Gui logo hinh anh", "vproduct|ss2|addon|logo"), ("✍️ Watermark chu", "vproduct|ss2|addon|watermark")],
            [("📍 Vi tri logo", "vproduct|ss2|addon_position|logo"), ("📍 Vi tri watermark", "vproduct|ss2|addon_position|watermark")],
            [("🗑️ Xoa logo", "vproduct|ss2|addon|clear_logo"), ("🗑️ Xoa watermark", "vproduct|ss2|addon|clear_watermark")],
        ]
        if screen_parent("addons", draft) != "review":
            rows.append([("✅ Xong bo sung", "vproduct|ss2|show|review"), ("⏭️ Bo qua", "vproduct|ss2|addon|skip")])
        rows.append(_nav(screen_parent("addons", draft)))
    elif name == "addon_position":
        target = _safe(draft.get("selfshot2_addon_position_target")) or "logo"
        label = "logo" if target == "logo" else "watermark"
        text = f"📍 <b>Vi tri {label}</b>\n\nChon vi tri co dinh, an toan trong khung hinh."
        rows = []
        for offset in range(0, len(ADDON_POSITIONS), 2):
            rows.append([
                (position_label, f"vproduct|ss2|addon_position_set|{target}.{position_id}")
                for position_id, position_label in ADDON_POSITIONS[offset:offset + 2]
            ])
        rows.append(_nav("addons"))
    elif name == "review":
        text = (
            "👁️ <b>Review Tu quay & doi canh AI</b>\n\n"
            f"Chu the: {len((draft.get('subject_manifest') or {}).get('subject_ids') or [])} · Canh: {draft.get('scene_count') or 0} · Ti le: {draft.get('aspect_ratio') or '-'}\n"
            f"Noi dung: {(draft.get('selected_content') or {}).get('title') or '-'} · Huong: {(draft.get('direction_contract') or {}).get('label') or '-'}\n\n"
            "Chua tao tac vu, chua goi provider va chua tru Xu."
        )
        rows = [
            [('👁️ Xem tung canh', 'vproduct|ss2|plan_view'), ('✍️ Sua noi dung canh', 'vproduct|ss2|content_source|custom')],
            [('👤 Nguoi/vat giu nguyen', 'vproduct|ss2|show|preserve'), ('🎬 Prompt video', 'vproduct|ss2|show|prompts')],
            [('🎚️ Am thanh', 'vproduct|ss2|show|audio'), ('✨ Hieu ung', 'vproduct|ss2|show|direction')],
            [('🖼️ Logo/Watermark', 'vproduct|ss2|review_addons'), ('⭐ Hoan thien video', 'vproduct|ss2|finish')],
            _nav("addons"),
        ]
    elif name == "finish":
        report = dict(draft.get("selfshot2_preflight") or {})
        if report.get("ok"):
            text = "⭐ <b>Hoan thien video</b>\n\nPreflight da dat. Chon goi de xem hoa don; chua goi provider va chua tru Xu."
        else:
            blocker = _safe(report.get("blocker") or "preflight_chua_chay")
            text = f"⭐ <b>Hoan thien video</b>\n\nChua the mo hoa don. Ly do: <code>{blocker}</code>. Job=0, outbox=0, provider=0, Xu=0."
        rows = [[('200 Trai nghiem', 'vproduct|ss2|quality|200'), ('300 Co ban', 'vproduct|ss2|quality|300')], [('400 Tot', 'vproduct|ss2|quality|400'), ('500 Dep', 'vproduct|ss2|quality|500')], [('600 Nang cao', 'vproduct|ss2|quality|600'), ('800 Premium', 'vproduct|ss2|quality|800')], [('1000 Pro', 'vproduct|ss2|quality|1000'), ('1200 Studio', 'vproduct|ss2|quality|1200')], [('1500 Max', 'vproduct|ss2|quality|1500'), ('🔄 Kiem tra lai', 'vproduct|ss2|finish')], _nav("review")]
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
