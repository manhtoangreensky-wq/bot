"""Provider-free add-on planning for semantic video scenes."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


CONTENT_AFFECTING_ADDONS = (
    "voiceover",
    "dialogue",
    "captions",
    "cta",
    "subtitle_required",
    "logo_safe_zone",
    "watermark_safe_zone",
    "preserve_source_audio",
    "aspect_ratio",
    "target_duration_seconds",
    "music_mood",
    "transition_style",
)

POST_PRODUCTION_ADDONS = (
    "logo_burn_in",
    "watermark_burn_in",
    "subtitle_rendering",
    "dubbing_mix",
    "music_mix",
    "final_audio_mix",
    "output_packaging",
)

DEFAULT_CONTENT_ADDONS: dict[str, Any] = {
    "voiceover": False,
    "dialogue": False,
    "captions": False,
    "cta": True,
    "subtitle_required": False,
    "logo_safe_zone": "none",
    "watermark_safe_zone": "none",
    "preserve_source_audio": False,
    "aspect_ratio": "9:16",
    "target_duration_seconds": 8,
    "music_mood": "theo mạch cảm xúc của nội dung",
    "transition_style": "tự nhiên",
}

DEFAULT_POST_ADDONS: dict[str, bool] = {
    "logo_burn_in": False,
    "watermark_burn_in": False,
    "subtitle_rendering": False,
    "dubbing_mix": False,
    "music_mix": False,
    "final_audio_mix": True,
    "output_packaging": True,
}


def _ratio(value: Any) -> str:
    cleaned = str(value or "9:16").strip()
    return cleaned if cleaned in {"9:16", "16:9", "1:1", "4:5"} else "9:16"


def normalize_addon_plan(
    content: dict[str, Any] | None = None,
    post: dict[str, Any] | None = None,
    *,
    scene_count: int = 1,
    seconds_per_scene: int = 8,
) -> dict[str, Any]:
    """Return planning metadata; this function never executes an add-on."""

    count = max(1, min(20, int(scene_count or 1)))
    seconds = max(1, int(seconds_per_scene or 8))
    content_plan = deepcopy(DEFAULT_CONTENT_ADDONS)
    for key, value in dict(content or {}).items():
        if key in CONTENT_AFFECTING_ADDONS:
            content_plan[key] = value
    content_plan["aspect_ratio"] = _ratio(content_plan.get("aspect_ratio"))
    content_plan["target_duration_seconds"] = count * seconds

    post_plan = deepcopy(DEFAULT_POST_ADDONS)
    for key, value in dict(post or {}).items():
        if key in POST_PRODUCTION_ADDONS:
            post_plan[key] = bool(value)

    if content_plan.get("subtitle_required") or content_plan.get("captions"):
        post_plan["subtitle_rendering"] = True
    if str(content_plan.get("logo_safe_zone") or "none") != "none":
        post_plan["logo_burn_in"] = bool(post_plan.get("logo_burn_in"))
    if str(content_plan.get("watermark_safe_zone") or "none") != "none":
        post_plan["watermark_burn_in"] = bool(post_plan.get("watermark_burn_in"))

    subtitle_safe = bool(content_plan.get("subtitle_required") or content_plan.get("captions"))
    logo_zone = str(content_plan.get("logo_safe_zone") or "none")
    watermark_zone = str(content_plan.get("watermark_safe_zone") or "none")
    composition = {
        "subtitle_safe_area": "lower_22_percent_clear" if subtitle_safe else "not_reserved",
        "logo_safe_area": logo_zone,
        "watermark_safe_area": watermark_zone,
        "subject_safe_area": "center_56_percent" if subtitle_safe else "center_72_percent",
        "voiceover_max_words_per_scene": max(1, int(seconds * 2.2)),
        "cta_reserved_scene": count if content_plan.get("cta") else 0,
        "audio_transition_points": [index * seconds for index in range(1, count)],
    }
    return {
        "content_affecting": content_plan,
        "post_production": post_plan,
        "composition_constraints": composition,
        "scene_count": count,
        "seconds_per_scene": seconds,
        "duration_seconds": count * seconds,
        "planning_complete": True,
        "execution_started": False,
        "provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "xu_charged": 0,
    }


def content_addon_summary(plan: dict[str, Any] | None) -> list[str]:
    content = dict((plan or {}).get("content_affecting") or {})
    labels = {
        "voiceover": "Lời dẫn",
        "dialogue": "Lời thoại",
        "captions": "Chữ theo cảnh",
        "cta": "CTA",
        "subtitle_required": "Vùng phụ đề",
        "preserve_source_audio": "Giữ âm thanh gốc",
    }
    enabled = [label for key, label in labels.items() if bool(content.get(key))]
    if str(content.get("logo_safe_zone") or "none") != "none":
        enabled.append(f"Vùng logo {content['logo_safe_zone']}")
    if str(content.get("watermark_safe_zone") or "none") != "none":
        enabled.append(f"Vùng watermark {content['watermark_safe_zone']}")
    enabled.append(f"Khung {content.get('aspect_ratio') or '9:16'}")
    return enabled


def post_addon_summary(plan: dict[str, Any] | None) -> list[str]:
    post = dict((plan or {}).get("post_production") or {})
    labels = {
        "logo_burn_in": "Gắn logo",
        "watermark_burn_in": "Gắn watermark",
        "subtitle_rendering": "Render phụ đề",
        "dubbing_mix": "Ghép lồng tiếng",
        "music_mix": "Ghép nhạc",
        "final_audio_mix": "Cân âm thanh",
        "output_packaging": "Đóng gói MP4",
    }
    return [label for key, label in labels.items() if bool(post.get(key))]
