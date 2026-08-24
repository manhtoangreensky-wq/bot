"""Provider-neutral content-first state for the public Video creation UI.

This module owns planning state only. It never calls a provider, creates a job,
writes a database row, mutates a wallet, or executes a renderer.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from math import ceil
import re
from typing import Any, Iterable, Mapping
import unicodedata
from uuid import uuid4

from services import video_profile_context_engine
from services import video_profile_catalog
from services import video_product_profiles as video_profiles
from services import video_script_product


FLOW_SCHEMA_VERSION = 3
MIN_CHARACTERS = 0
MAX_CHARACTERS = 20
MIN_LOCATIONS = 0
MAX_LOCATIONS = 20
MAX_SCENES = 20
SUPPORTED_RATIOS = frozenset({"9:16", "16:9", "1:1", "4:5", "keep"})
NEED_VALUES = frozenset({"REQUIRED", "AUTO", "OPTIONAL", "SKIP", "UNSUPPORTED"})
GENDERS = frozenset({"male", "female", "unspecified"})
MUSIC_SCOPES = frozenset({"none", "whole_video", "per_scene"})
MUSIC_SCENE_POLICIES = frozenset({"inherit", "track", "off"})
ID_COUNTER_PREFIXES = ("source", "asset", "char", "loc", "prod", "prop", "rel", "scene", "dlg")
DEFAULT_CONTINUITY = {
    "identity": True,
    "wardrobe": True,
    "product": True,
    "location": True,
}
VIDEO_AI_REAL_PRODUCT_FIRST_MODES = frozenset({"prompt_video", "image_video"})
_SCENE_PLAN_MARKER_RE = re.compile(
    r"(?i)\b(?:cảnh|scene)\s*(\d{1,2})\s*[:.\-)–—]?\s*"
)


ENTRY_ADAPTERS: dict[str, dict[str, Any]] = {
    "video_trend": {
        "render_family": "product_video",
        "initial_step": "source",
        "source_kind": "trend",
        "source_required": True,
        "seconds_per_scene": 8,
        "minimum_scene_count": 1,
        "maximum_scene_count": 20,
        "public_submit_enabled": True,
    },
    "video_ai_real": {
        "render_family": "product_video",
        "initial_step": "entry",
        "source_kind": "prompt_or_reference",
        "source_required": False,
        "seconds_per_scene": 8,
        "minimum_scene_count": 1,
        "maximum_scene_count": 20,
        "public_submit_enabled": True,
    },
    "script_image_video": {
        "render_family": "product_video",
        "initial_step": "source",
        "source_kind": "script",
        "source_required": True,
        "seconds_per_scene": 8,
        "minimum_scene_count": 5,
        "maximum_scene_count": 20,
        "public_submit_enabled": True,
    },
    "frame_video_local": {
        "render_family": "frame_video",
        "initial_step": "source",
        "source_kind": "raw_images",
        "source_required": True,
        "seconds_per_scene": 3,
        "minimum_scene_count": 1,
        "maximum_scene_count": 20,
        "public_submit_enabled": True,
    },
    "self_shot_scene_change": {
        "render_family": "self_shot",
        "initial_step": "source",
        "source_kind": "source_video",
        "source_required": True,
        "seconds_per_scene": 8,
        "minimum_scene_count": 1,
        "maximum_scene_count": 20,
        "public_submit_enabled": True,
    },
    "storyboard_prompt": {
        "render_family": "storyboard",
        "initial_step": "entry",
        "source_kind": "generated_or_uploaded_storyboard",
        "source_required": False,
        "seconds_per_scene": 8,
        "minimum_scene_count": 2,
        "maximum_scene_count": 20,
        "public_submit_enabled": True,
    },
    "multi_scene_film": {
        "render_family": "long_video",
        "initial_step": "entry",
        "source_kind": "series_content",
        "source_required": False,
        "seconds_per_scene": 300,
        "minimum_scene_count": 1,
        "maximum_scene_count": 20,
        "public_submit_enabled": True,
    },
}


CANONICAL_VISIBLE_STEPS = (
    "entry",
    "series_goal",
    "source",
    "format",
    "content_hub",
    "content_lock",
    "production_bible",
    "references",
    "continuity",
    "episode",
    "scene_count",
    "scene_plan",
    "scene_assignment",
    "prompts",
    "branding",
    "summary",
    "package",
    "invoice",
    "confirmation",
    "status",
)


DEFAULT_CAPABILITIES = {
    "image_to_video": True,
    "video_to_video": False,
    "multi_character_planning": True,
    "role_mapped_references": True,
    "scene_cast_planning": True,
    "dialogue_speaker_planning": True,
    "multi_voice_render": False,
    "whole_video_music": False,
    "per_scene_music": False,
    "scene_sfx": False,
    "scene_ambient": False,
    "continuity_planning": True,
}


CONTENT_DIRTY_DEPENDENCIES = (
    "needs",
    "production_bible",
    "scene_plan",
    "dialogue",
    "prompts",
    "summary",
)
SUMMARY_EDIT_STEPS = frozenset({
    "format",
    "content_lock",
    "production_bible",
    "scene_count",
    "scene_plan",
    "scene_assignment",
    "prompts",
    "branding",
})


def _text(value: Any, limit: int = 4000) -> str:
    return str(value or "").strip()[:limit]


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _adapter(product: str) -> dict[str, Any]:
    product_id = _text(product, 80)
    if product_id not in ENTRY_ADAPTERS:
        raise ValueError("unsupported_video_uiflow3_product")
    return deepcopy(ENTRY_ADAPTERS[product_id])


def _stable_id(prefix: str, ordinal: int) -> str:
    return f"{prefix}_{max(1, int(ordinal)):02d}"


def _next_ordinal(prefix: str, values: Iterable[Any]) -> int:
    """Return the next numeric ordinal without assuming the current list order."""

    marker = f"{_text(prefix, 40)}_"
    highest = 0
    for value in values:
        token = _text(value, 120)
        if not token.startswith(marker):
            continue
        try:
            highest = max(highest, int(token[len(marker):]))
        except (TypeError, ValueError):
            continue
    return highest + 1


def _allocate_id(state: dict[str, Any], prefix: str, values: Iterable[Any]) -> str:
    """Allocate a draft-scoped ID without resurrecting a removed entity."""

    counters = dict(state.get("id_counters") or {})
    ordinal = max(
        _integer(counters.get(prefix), 0),
        _next_ordinal(prefix, values) - 1,
    ) + 1
    counters[prefix] = ordinal
    state["id_counters"] = counters
    return _stable_id(prefix, ordinal)


def _dedupe(values: Iterable[Any]) -> list[str]:
    return list(dict.fromkeys(_text(value, 120) for value in values if _text(value, 120)))


def infer_explicit_character_identity(value: Any) -> dict[str, str]:
    """Extract only character identity that is explicit in a Vietnamese brief."""

    text = _text(value, 4000)
    if not text:
        return {}
    name_token = r"[A-ZÀ-ỴĐ][A-Za-zÀ-ỹĐđ'-]*"
    full_name = rf"{name_token}(?:\s+{name_token}){{0,3}}"
    person_roles = (
        r"nghệ\s+nhân|diễn\s+viên|người\s+mẫu|bác\s+sĩ|đầu\s+bếp|"
        r"giáo\s+viên|chuyên\s+gia|người\s+dẫn|kiến\s+trúc\s+sư|"
        r"kỹ\s+sư|doanh\s+nhân"
    )
    name_match = None
    for pattern in (
        rf"(?i:\bnhân\s+vật)\s+(?P<name>{full_name})(?=\s*(?:[,;:.]|(?i:\blà\b)|$))",
        rf"(?P<name>{full_name})\s*,\s*(?i:(?:một\s+)?(?:nữ|nam)\b)",
        rf"(?i:\b(?:nữ|nam)\s+(?:{person_roles}))\s+(?P<name>{full_name})"
        rf"(?=\s*(?:[,;:.]|(?i:\b(?:là|làm|đang|tạo|giới\s+thiệu)\b)|$))",
    ):
        name_match = re.search(pattern, text)
        if name_match:
            break

    folded = "".join(
        character
        for character in unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
        if unicodedata.category(character) != "Mn"
    )
    role_pattern = (
        r"nghe\s+nhan|dien\s+vien|nguoi\s+mau|bac\s+si|dau\s+bep|"
        r"giao\s+vien|chuyen\s+gia|nguoi\s+dan|kien\s+truc\s+su|"
        r"ky\s+su|doanh\s+nhan"
    )
    female = bool(re.search(
        rf"\b(?:nhan\s+vat\s+nu|nu\s+(?:{role_pattern})|nguoi\s+phu\s+nu|co\s+gai|be\s+gai|nu\s+chinh)\b",
        folded,
    ))
    male = bool(re.search(
        rf"\b(?:nhan\s+vat\s+nam|nam\s+(?:{role_pattern})|nguoi\s+dan\s+ong|chang\s+trai|be\s+trai|nam\s+chinh)\b",
        folded,
    ))
    if name_match and female == male:
        tail = text[name_match.end() : name_match.end() + 80]
        folded_tail = "".join(
            character
            for character in unicodedata.normalize("NFD", tail.lower().replace("đ", "d"))
            if unicodedata.category(character) != "Mn"
        )
        direct_gender = re.match(r"\s*,?\s*(?:la\s+|mot\s+)?(nu|nam)\b", folded_tail)
        if direct_gender:
            female = direct_gender.group(1) == "nu"
            male = direct_gender.group(1) == "nam"

    result = {}
    if name_match:
        result["display_name"] = name_match.group("name").strip()
    if female != male:
        result["gender"] = "female" if female else "male"
    return result


def _character(ordinal: int) -> dict[str, Any]:
    return {
        "character_id": _stable_id("char", ordinal),
        "display_name": f"Nhan vat {ordinal}",
        "role": "",
        "gender": "unspecified",
        "age_band": "",
        "description": "",
        "face": "",
        "hair": "",
        "body": "",
        "wardrobe": "",
        "personality": "",
        "behavior": "",
        "relationship_hints": [],
        "continuity_lock": True,
        "reference_asset_ids": [],
        "voice_id": "",
        "voice_policy": {
            "mode": "auto_gender_distinct",
            "gender": "unspecified",
            "distinct_from": [],
        },
        "suggestion_source": "",
        "suggestion_confidence": 0.0,
        "locked_by_user": False,
    }


def _location(ordinal: int) -> dict[str, Any]:
    return {
        "location_id": _stable_id("loc", ordinal),
        "name": f"Boi canh {ordinal}",
        "description": "",
        "indoor_outdoor": "",
        "time_of_day": "",
        "weather": "",
        "lighting": "",
        "mood": "",
        "reference_asset_ids": [],
        "suggestion_source": "",
        "suggestion_confidence": 0.0,
        "locked_by_user": False,
    }


def _scene(ordinal: int, *, seconds: int, ratio: str) -> dict[str, Any]:
    return {
        "scene_id": _stable_id("scene", ordinal),
        "scene_index": ordinal,
        "scene_role": "",
        "goal": "",
        "semantic_beat": "",
        "start_state": "",
        "main_action": "",
        "completion_state": "",
        "duration_target": max(1, int(seconds)),
        "ratio": ratio,
        "character_ids": [],
        "narrator_enabled": False,
        "product_ids": [],
        "prop_ids": [],
        "location_id": "",
        "reference_asset_ids": [],
        "wardrobe_overrides": {},
        "dialogue_segment_ids": [],
        "camera": "",
        "framing": "",
        "movement": "",
        "lighting": "",
        "mood": "",
        "transition_in": "",
        "transition_out": "",
        "music_policy": "inherit",
        "sfx_ids": [],
        "ambient_id": "",
        "continuity_from_scene_id": "",
        "continuity_to_scene_id": "",
        "original_scene_intent": "",
        "compiled_prompt_status": "not_compiled",
        "planning_source": "",
        "planning_confidence": 0.0,
        "locked_by_user": False,
        "assignment_source": "unassigned",
        "assignment_confidence": 0.0,
    }


def new_state(
    product: str,
    *,
    draft_id: str = "",
    entry_mode: str = "",
    capabilities: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    product_id = _text(product, 80)
    adapter = _adapter(product_id)
    capability_state = dict(DEFAULT_CAPABILITIES)
    capability_state.update({str(key): bool(value) for key, value in dict(capabilities or {}).items()})
    initial_step = str(adapter["initial_step"])
    return normalize_state({
        "flow_schema_version": FLOW_SCHEMA_VERSION,
        "draft_id": _text(draft_id, 120) or uuid4().hex,
        "parent_product": product_id,
        "entry_mode": _text(entry_mode, 80),
        "render_family": str(adapter["render_family"]),
        "source": {
            "kind": str(adapter["source_kind"]),
            "required": bool(adapter["source_required"]),
            "complete": not bool(adapter["source_required"]),
            "assets": [],
            "asset_ids": [],
            "metadata": {},
        },
        "format": {
            "ratio": "",
            "target_duration_seconds": 0,
            "seconds_per_scene": int(adapter["seconds_per_scene"]),
            "scene_count_policy": "auto",
            "scene_count": 0,
            "scene_count_confirmed": False,
        },
        "content": {
            "source": "",
            "profile_id": "",
            "idea_id": "",
            "original_intent": "",
            "approved_brief": {},
            "candidate_ready": False,
            "revision": 0,
            "locked": False,
        },
        "series": {
            "series_id": "",
            "goal": "",
            "revision": 0,
        },
        "episode": {
            "episode_id": "episode_01",
            "number": 1,
            "title": "",
            "content": {
                "original_intent": "",
                "candidate_ready": False,
                "locked": False,
                "revision": 0,
            },
            "entity_overrides": {},
            "continuity_overrides": {},
        },
        "needs": {},
        "bible": {
            "characters": [],
            "character_count_confirmed": False,
            "narrator": None,
            "products": [],
            "locations": [],
            "location_count_confirmed": False,
            "props": [],
            "relationships": [],
            "continuity": deepcopy(DEFAULT_CONTINUITY),
        },
        "references": [],
        "scenes": [],
        "audio": {
            "dialogue_segments": [],
            "voice_cast": {},
            "music_scope": "none",
            "music_plan": {},
            "sfx_plan": [],
            "ambient_plan": [],
        },
        "branding": {},
        "capabilities": capability_state,
        "navigation": {
            "current_step": initial_step,
            "visible_step_stack": [],
            "completed_steps": [],
            "return_to": None,
            "dirty_sections": [],
        },
        "legacy_compat": {},
        "id_counters": {prefix: 0 for prefix in ID_COUNTER_PREFIXES},
        "ui_revision": 0,
        "handled_callback_ids": [],
        "side_effects": {
            "provider_calls": 0,
            "jobs": 0,
            "outbox": 0,
            "wallet_mutations": 0,
            "xu_charged": 0,
        },
    })


def normalize_state(value: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = deepcopy(dict(value or {}))
    product = _text(raw.get("parent_product"), 80)
    if product not in ENTRY_ADAPTERS:
        raise ValueError("unsupported_video_uiflow3_product")
    adapter = _adapter(product)
    base = new_state(product, draft_id=_text(raw.get("draft_id"), 120) or uuid4().hex) if not raw.get("flow_schema_version") else {}
    if base:
        base.update(raw)
        raw = base
    raw["flow_schema_version"] = FLOW_SCHEMA_VERSION
    raw["draft_id"] = _text(raw.get("draft_id"), 120) or uuid4().hex
    raw["parent_product"] = product
    raw["entry_mode"] = _text(raw.get("entry_mode"), 80)
    raw["render_family"] = str(adapter["render_family"])

    source = {
        "kind": str(adapter["source_kind"]),
        "required": bool(adapter["source_required"]),
        "complete": not bool(adapter["source_required"]),
        "assets": [],
        "asset_ids": [],
        "metadata": {},
        **dict(raw.get("source") or {}),
    }
    source["assets"] = [dict(item) for item in source.get("assets") or [] if isinstance(item, Mapping)][:100]
    source["asset_ids"] = _dedupe(source.get("asset_ids") or [])
    source["metadata"] = dict(source.get("metadata") or {})
    source["complete"] = bool(source.get("complete") or (source["assets"] and source["required"]))
    raw["source"] = source

    format_state = {
        "ratio": "",
        "target_duration_seconds": 0,
        "seconds_per_scene": int(adapter["seconds_per_scene"]),
        "scene_count_policy": "auto",
        "scene_count": 0,
        "scene_count_confirmed": False,
        **dict(raw.get("format") or {}),
    }
    if str(format_state.get("ratio") or "") not in SUPPORTED_RATIOS:
        format_state["ratio"] = ""
    format_state["target_duration_seconds"] = max(0, _integer(format_state.get("target_duration_seconds"), 0))
    if product == "video_ai_real" and raw["entry_mode"] in VIDEO_AI_REAL_PRODUCT_FIRST_MODES:
        format_state["seconds_per_scene"] = max(
            1,
            min(60, _integer(format_state.get("seconds_per_scene"), int(adapter["seconds_per_scene"]))),
        )
    else:
        format_state["seconds_per_scene"] = int(adapter["seconds_per_scene"])
    format_state["scene_count"] = max(0, min(int(adapter["maximum_scene_count"]), _integer(format_state.get("scene_count"), 0)))
    format_state["scene_count_confirmed"] = bool(format_state.get("scene_count_confirmed"))
    raw["format"] = format_state

    content = {
        "source": "",
        "profile_id": "",
        "idea_id": "",
        "original_intent": "",
        "approved_brief": {},
        "candidate_ready": False,
        "revision": 0,
        "locked": False,
        **dict(raw.get("content") or {}),
    }
    for field in ("source", "profile_id", "idea_id", "original_intent"):
        content[field] = _text(content.get(field), 8000 if field == "original_intent" else 160)
    content["approved_brief"] = dict(content.get("approved_brief") or {})
    content["candidate_ready"] = bool(content.get("candidate_ready"))
    content["revision"] = max(0, _integer(content.get("revision"), 0))
    content["locked"] = bool(content.get("locked"))
    raw["content"] = content

    series = {
        "series_id": "",
        "goal": "",
        "revision": 0,
        **dict(raw.get("series") or {}),
    }
    series["series_id"] = (
        _text(series.get("series_id"), 120)
        or f"series_{sha256(raw['draft_id'].encode('utf-8')).hexdigest()[:12]}"
    )
    series["goal"] = _text(series.get("goal"), 4000)
    series["revision"] = max(0, _integer(series.get("revision"), 0))
    raw["series"] = series

    episode = {
        "episode_id": "episode_01",
        "number": 1,
        "title": "",
        "content": {},
        "entity_overrides": {},
        "continuity_overrides": {},
        **dict(raw.get("episode") or {}),
    }
    episode["episode_id"] = _text(episode.get("episode_id"), 120) or "episode_01"
    episode["number"] = max(1, min(9999, _integer(episode.get("number"), 1)))
    episode["title"] = _text(episode.get("title"), 500)
    episode_content = {
        "original_intent": "",
        "candidate_ready": False,
        "locked": False,
        "revision": 0,
        **dict(episode.get("content") or {}),
    }
    episode_content["original_intent"] = _text(episode_content.get("original_intent"), 12000)
    episode_content["candidate_ready"] = bool(
        episode_content.get("candidate_ready")
        and episode_content["original_intent"]
    )
    episode_content["locked"] = bool(
        episode_content.get("locked")
        and episode_content["candidate_ready"]
    )
    episode_content["revision"] = max(0, _integer(episode_content.get("revision"), 0))
    episode["content"] = episode_content
    raw_overrides = dict(episode.get("entity_overrides") or {})
    episode["entity_overrides"] = {
        key: _dedupe(raw_overrides[key] or [])
        for key in ("characters", "locations", "products", "props")
        if key in raw_overrides and raw_overrides[key] is not None
    }
    episode["continuity_overrides"] = {
        key: bool(value)
        for key, value in dict(episode.get("continuity_overrides") or {}).items()
        if key in DEFAULT_CONTINUITY
    }
    raw["episode"] = episode

    raw["needs"] = {
        _text(key, 80): str(value).upper()
        for key, value in dict(raw.get("needs") or {}).items()
        if _text(key, 80) and str(value).upper() in NEED_VALUES
    }
    bible = {
        "characters": [],
        "character_count_confirmed": False,
        "narrator": None,
        "products": [],
        "locations": [],
        "location_count_confirmed": False,
        "props": [],
        "relationships": [],
        "continuity": deepcopy(DEFAULT_CONTINUITY),
        **dict(raw.get("bible") or {}),
    }
    bible["characters"] = [dict(item) for item in bible.get("characters") or [] if isinstance(item, Mapping)][:MAX_CHARACTERS]
    bible["character_count_confirmed"] = bool(bible.get("character_count_confirmed"))
    character_ids = [str(item.get("character_id") or "") for item in bible["characters"] if str(item.get("character_id") or "")]
    for item in bible["characters"]:
        character_id = str(item.get("character_id") or "")
        voice_id = str(item.get("voice_id") or "")
        item["voice_policy"] = {
            "mode": "explicit" if voice_id else "auto_gender_distinct",
            "gender": str(item.get("gender") or "unspecified"),
            "distinct_from": [other for other in character_ids if other != character_id],
        }
    bible["locations"] = [dict(item) for item in bible.get("locations") or [] if isinstance(item, Mapping)][:MAX_LOCATIONS]
    bible["location_count_confirmed"] = bool(bible.get("location_count_confirmed"))
    bible["products"] = [dict(item) for item in bible.get("products") or [] if isinstance(item, Mapping)][:20]
    bible["props"] = [dict(item) for item in bible.get("props") or [] if isinstance(item, Mapping)][:40]
    bible["relationships"] = [dict(item) for item in bible.get("relationships") or [] if isinstance(item, Mapping)][:80]
    bible["narrator"] = dict(bible["narrator"]) if isinstance(bible.get("narrator"), Mapping) else None
    bible["continuity"] = {
        **DEFAULT_CONTINUITY,
        **dict(bible.get("continuity") or {}),
    }
    raw["bible"] = bible
    raw["references"] = [dict(item) for item in raw.get("references") or [] if isinstance(item, Mapping)][:200]
    raw_scenes = [dict(item) for item in raw.get("scenes") or [] if isinstance(item, Mapping)]
    scene_rows: list[dict[str, Any]] = []
    used_scene_ids: set[str] = set()
    default_seconds = int(adapter["seconds_per_scene"])
    default_ratio = str(format_state.get("ratio") or "9:16")
    for index, item in enumerate(raw_scenes[: int(adapter["maximum_scene_count"])], 1):
        ordinal = max(1, _integer(item.get("scene_index"), index))
        scene = _scene(ordinal, seconds=default_seconds, ratio=default_ratio)
        scene.update(item)
        scene_id = _text(scene.get("scene_id"), 80)
        if not scene_id or scene_id in used_scene_ids:
            scene_id = _stable_id("scene", _next_ordinal("scene", used_scene_ids))
        used_scene_ids.add(scene_id)
        scene["scene_id"] = scene_id
        scene["scene_index"] = index
        scene["duration_target"] = max(1, _integer(scene.get("duration_target"), default_seconds))
        scene["ratio"] = str(scene.get("ratio") or default_ratio)
        scene["character_ids"] = _dedupe(scene.get("character_ids") or [])
        scene["product_ids"] = _dedupe(scene.get("product_ids") or [])
        scene["prop_ids"] = _dedupe(scene.get("prop_ids") or [])
        scene["reference_asset_ids"] = _dedupe(scene.get("reference_asset_ids") or [])
        scene["dialogue_segment_ids"] = _dedupe(scene.get("dialogue_segment_ids") or [])
        scene["sfx_ids"] = _dedupe(scene.get("sfx_ids") or [])
        scene["narrator_enabled"] = bool(scene.get("narrator_enabled"))
        scene["ambient_id"] = _text(scene.get("ambient_id"), 160)
        scene["planning_source"] = _text(scene.get("planning_source"), 80)
        scene["planning_confidence"] = max(0.0, min(1.0, _number(scene.get("planning_confidence"), 0.0)))
        scene["locked_by_user"] = bool(scene.get("locked_by_user"))
        scene["assignment_source"] = _text(scene.get("assignment_source"), 40) or "unassigned"
        scene["assignment_confidence"] = max(0.0, min(1.0, _number(scene.get("assignment_confidence"), 0.0)))
        scene_rows.append(scene)
    raw["scenes"] = scene_rows

    audio = {
        "dialogue_segments": [],
        "voice_cast": {},
        "music_scope": "none",
        "music_plan": {},
        "sfx_plan": [],
        "ambient_plan": [],
        **dict(raw.get("audio") or {}),
    }
    audio["dialogue_segments"] = [dict(item) for item in audio.get("dialogue_segments") or [] if isinstance(item, Mapping)][:400]
    audio["voice_cast"] = {str(key): dict(item) for key, item in dict(audio.get("voice_cast") or {}).items() if isinstance(item, Mapping)}
    if str(audio.get("music_scope") or "none") not in MUSIC_SCOPES:
        audio["music_scope"] = "none"
    audio["music_plan"] = dict(audio.get("music_plan") or {})
    audio["sfx_plan"] = [dict(item) for item in audio.get("sfx_plan") or [] if isinstance(item, Mapping)][:200]
    audio["ambient_plan"] = [dict(item) for item in audio.get("ambient_plan") or [] if isinstance(item, Mapping)][:200]
    raw["audio"] = audio
    raw["branding"] = dict(raw.get("branding") or {})
    capabilities = dict(DEFAULT_CAPABILITIES)
    capabilities.update({str(key): bool(item) for key, item in dict(raw.get("capabilities") or {}).items()})
    raw["capabilities"] = capabilities

    navigation = {
        "current_step": str(adapter["initial_step"]),
        "visible_step_stack": [],
        "completed_steps": [],
        "return_to": None,
        "dirty_sections": [],
        **dict(raw.get("navigation") or {}),
    }
    current_step = _text(navigation.get("current_step"), 80)
    navigation["current_step"] = current_step if current_step in CANONICAL_VISIBLE_STEPS else str(adapter["initial_step"])
    navigation["visible_step_stack"] = [
        str(item) for item in navigation.get("visible_step_stack") or []
        if str(item) in CANONICAL_VISIBLE_STEPS
    ][-40:]
    navigation["completed_steps"] = [item for item in _dedupe(navigation.get("completed_steps") or []) if item in CANONICAL_VISIBLE_STEPS]
    navigation["return_to"] = _text(navigation.get("return_to"), 80) or None
    navigation["dirty_sections"] = _dedupe(navigation.get("dirty_sections") or [])
    if product != "multi_scene_film":
        navigation["visible_step_stack"] = [
            item for item in navigation["visible_step_stack"] if item != "episode"
        ]
        navigation["completed_steps"] = [
            item for item in navigation["completed_steps"] if item != "episode"
        ]
        if navigation["return_to"] == "episode":
            navigation["return_to"] = None
        if navigation["current_step"] == "episode":
            if content.get("locked"):
                navigation["current_step"] = "production_bible"
            elif content.get("candidate_ready"):
                navigation["current_step"] = "content_lock"
            elif format_state.get("ratio") and format_state.get("target_duration_seconds"):
                navigation["current_step"] = "content_hub"
            else:
                navigation["current_step"] = str(adapter["initial_step"])
    raw["navigation"] = navigation
    raw["legacy_compat"] = dict(raw.get("legacy_compat") or {})
    counter_sources = {
        "source": [item.get("asset_id") for item in source["assets"]],
        "asset": [item.get("asset_id") for item in raw["references"]],
        "char": [item.get("character_id") for item in bible["characters"]],
        "loc": [item.get("location_id") for item in bible["locations"]],
        "prod": [item.get("product_id") for item in bible["products"]],
        "prop": [item.get("prop_id") for item in bible["props"]],
        "rel": [item.get("relationship_id") for item in bible["relationships"]],
        "scene": [item.get("scene_id") for item in raw["scenes"]],
        "dlg": [item.get("dialogue_id") for item in audio["dialogue_segments"]],
    }
    stored_counters = dict(raw.get("id_counters") or {})
    raw["id_counters"] = {
        prefix: max(
            _integer(stored_counters.get(prefix), 0),
            _next_ordinal(prefix, counter_sources[prefix]) - 1,
        )
        for prefix in ID_COUNTER_PREFIXES
    }
    raw["ui_revision"] = max(0, _integer(raw.get("ui_revision"), 0))
    raw["handled_callback_ids"] = _dedupe(raw.get("handled_callback_ids") or [])[-100:]
    raw["side_effects"] = {
        "provider_calls": 0,
        "jobs": 0,
        "outbox": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }
    return raw


def set_entry_mode(state: Mapping[str, Any], mode: str) -> dict[str, Any]:
    current = normalize_state(state)
    selected = _text(mode, 80)
    product = current["parent_product"]
    allowed_modes = {
        "video_ai_real": {"prompt_video", "image_video", "video_video"},
        "storyboard_prompt": {"storyboard_generate", "storyboard_upload"},
        "multi_scene_film": {"series_plan"},
    }
    if product in allowed_modes and selected not in allowed_modes[product]:
        raise ValueError("entry_mode_unsupported")
    if product == "video_ai_real" and selected == "video_video" and not current["capabilities"].get("video_to_video"):
        raise ValueError("entry_mode_unsupported")
    if product == "video_ai_real":
        current["source"]["required"] = selected in {"image_video", "video_video"}
        current["source"]["kind"] = "raw_images" if selected == "image_video" else "source_video" if selected == "video_video" else "prompt"
    elif product == "storyboard_prompt":
        current["source"]["required"] = True
        current["source"]["kind"] = "storyboard_panels" if selected == "storyboard_upload" else "generated_storyboard"
    current["source"]["complete"] = bool(current["source"].get("assets")) if current["source"]["required"] else True
    current["entry_mode"] = selected
    if product == "multi_scene_film":
        target_step = "series_goal"
    elif product == "video_ai_real" and selected in VIDEO_AI_REAL_PRODUCT_FIRST_MODES:
        target_step = "scene_count"
    else:
        target_step = "source" if current["source"]["required"] else "format"
    return navigate(current, target_step)


def image_source_follows_format(state: Mapping[str, Any]) -> bool:
    current = normalize_state(state)
    return bool(
        current["parent_product"] == "video_ai_real"
        and current["entry_mode"] == "image_video"
        and current["format"].get("ratio")
        and _integer(current["format"].get("scene_count"), 0) > 0
    )


def _require_series_state(state: Mapping[str, Any]) -> dict[str, Any]:
    current = normalize_state(state)
    if current["parent_product"] != "multi_scene_film":
        raise ValueError("series_step_not_supported")
    return current


def set_series_goal(state: Mapping[str, Any], goal: str) -> dict[str, Any]:
    current = _require_series_state(state)
    value = _text(goal, 4000)
    if not value:
        raise ValueError("series_goal_required")
    if value != str(current["series"].get("goal") or ""):
        current["series"]["revision"] = max(1, _integer(current["series"].get("revision"), 0) + 1)
        current["navigation"]["dirty_sections"] = _dedupe(
            list(current["navigation"].get("dirty_sections") or [])
            + ["scene_plan", "prompts", "summary"]
        )
    current["series"]["goal"] = value
    current["navigation"]["current_step"] = "series_goal"
    return normalize_state(current)


def set_source_metadata(state: Mapping[str, Any], **metadata: Any) -> dict[str, Any]:
    current = normalize_state(state)
    if current["parent_product"] == "storyboard_prompt" and "detected_panel_count" in metadata:
        panel_count = _integer(metadata.get("detected_panel_count"), 0)
        if panel_count > int(_adapter(current["parent_product"])["maximum_scene_count"]):
            raise ValueError("source_scene_limit_exceeded")
    current["source"]["metadata"].update(deepcopy(metadata))
    if any(value not in (None, "", [], {}) for value in metadata.values()):
        current["source"]["complete"] = True
        current["navigation"]["current_step"] = "format"
    return normalize_state(current)


def add_source_asset(
    state: Mapping[str, Any],
    *,
    asset_type: str,
    telegram_file_id: str,
    fingerprint: str,
    **metadata: Any,
) -> dict[str, Any]:
    current = normalize_state(state)
    file_id = _text(telegram_file_id, 512)
    identity = _text(fingerprint, 256)
    if not file_id or not identity:
        raise ValueError("source_asset_identity_required")
    assets = list(current["source"]["assets"])
    if any(str(item.get("fingerprint") or "") == identity for item in assets):
        return current
    if (
        current["parent_product"] == "frame_video_local"
        and len(assets) >= int(_adapter(current["parent_product"])["maximum_scene_count"])
    ):
        raise ValueError("source_scene_limit_exceeded")
    asset_id = _allocate_id(current, "source", [item.get("asset_id") for item in assets])
    assets.append({
        "asset_id": asset_id,
        "asset_type": _text(asset_type, 80),
        "owner_type": "raw_source",
        "owner_id": "",
        "role": "source",
        "telegram_file_id": file_id,
        "fingerprint": identity,
        "metadata": deepcopy(metadata),
    })
    current["source"]["assets"] = assets
    current["source"]["asset_ids"] = [item["asset_id"] for item in assets]
    current["source"]["complete"] = True
    current["navigation"]["current_step"] = "source" if image_source_follows_format(current) else "format"
    return normalize_state(current)


def set_format(
    state: Mapping[str, Any],
    *,
    ratio: str | None = None,
    target_duration_seconds: int | None = None,
    seconds_per_scene: int | None = None,
) -> dict[str, Any]:
    current = normalize_state(state)
    previous_ratio = str(current["format"].get("ratio") or "")
    previous_duration = _integer(current["format"].get("target_duration_seconds"), 0)
    previous_scene_duration = _integer(current["format"].get("seconds_per_scene"), 0)
    content_locked = bool(current["content"].get("locked"))
    if ratio is not None:
        aspect = _text(ratio, 20)
        if aspect not in SUPPORTED_RATIOS:
            raise ValueError("aspect_ratio_unsupported")
        current["format"]["ratio"] = aspect
    if target_duration_seconds is not None:
        duration = _integer(target_duration_seconds, 0)
        if duration <= 0:
            raise ValueError("target_duration_invalid")
        current["format"]["target_duration_seconds"] = duration
    if seconds_per_scene is not None:
        if (
            current["parent_product"] != "video_ai_real"
            or current["entry_mode"] not in VIDEO_AI_REAL_PRODUCT_FIRST_MODES
        ):
            raise ValueError("scene_duration_invalid")
        scene_duration = _integer(seconds_per_scene, 0)
        if scene_duration < 1 or scene_duration > 60:
            raise ValueError("scene_duration_invalid")
        current["format"]["seconds_per_scene"] = scene_duration

    ratio_changed = str(current["format"].get("ratio") or "") != previous_ratio
    duration_changed = _integer(current["format"].get("target_duration_seconds"), 0) != previous_duration
    scene_duration_changed = _integer(current["format"].get("seconds_per_scene"), 0) != previous_scene_duration
    if content_locked:
        dirty = list(current["navigation"].get("dirty_sections") or [])
        if ratio_changed:
            for scene in current["scenes"]:
                scene["ratio"] = current["format"]["ratio"]
            dirty.extend(["prompts", "summary"])
        if duration_changed or scene_duration_changed:
            current["format"]["scene_count_confirmed"] = False
            dirty.extend(["scene_plan", "dialogue", "prompts", "summary"])
        current["navigation"]["dirty_sections"] = _dedupe(dirty)
    elif current["format"]["ratio"] and current["format"]["target_duration_seconds"]:
        current["navigation"]["current_step"] = "content_hub"
    return normalize_state(current)


def set_content_candidate(
    state: Mapping[str, Any],
    *,
    source: str,
    original_intent: str,
    profile_id: str = "",
    idea_id: str = "",
    approved_brief: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    current = normalize_state(state)
    intent = _text(original_intent, 12000)
    brief = deepcopy(dict(approved_brief or {}))
    if not intent and not brief:
        raise ValueError("content_candidate_required")
    current["source"]["complete"] = True
    current["content"].update({
        "source": _text(source, 80),
        "profile_id": _text(profile_id, 120),
        "idea_id": _text(idea_id, 120),
        "original_intent": intent,
        "approved_brief": brief,
        "candidate_ready": True,
        "locked": False,
    })
    current["navigation"]["current_step"] = "content_lock"
    return normalize_state(current)


def resolve_needs(state: Mapping[str, Any]) -> dict[str, str]:
    current = normalize_state(state)
    brief = dict(current["content"].get("approved_brief") or {})
    profile = str(current["content"].get("profile_id") or "").lower()
    product = current["parent_product"]
    defaults = {
        "characters": "OPTIONAL",
        "narrator": "OPTIONAL",
        "product": "OPTIONAL",
        "locations": "AUTO",
        "reference_assets": "OPTIONAL",
        "dialogue": "OPTIONAL",
        "voice": "AUTO",
        "music": "OPTIONAL",
        "sfx": "OPTIONAL",
        "ambient": "OPTIONAL",
        "continuity": "AUTO",
        "scene_planning": "REQUIRED",
    }
    if "lofi" in profile or "visualizer" in profile:
        defaults.update({"characters": "SKIP", "narrator": "SKIP", "dialogue": "SKIP", "voice": "SKIP", "music": "REQUIRED"})
    if product == "frame_video_local":
        defaults.update({"characters": "OPTIONAL", "reference_assets": "AUTO"})
    if product == "script_image_video":
        defaults.update({"characters": "AUTO", "narrator": "AUTO", "dialogue": "REQUIRED", "voice": "AUTO"})
    if product == "multi_scene_film":
        defaults["continuity"] = "REQUIRED"
    flag_map = {
        "characters": "needs_characters",
        "narrator": "needs_narrator",
        "product": "needs_product",
        "locations": "needs_locations",
        "reference_assets": "needs_reference_assets",
        "dialogue": "needs_dialogue",
        "voice": "needs_voice",
        "music": "needs_music",
        "sfx": "needs_sfx",
        "ambient": "needs_ambient",
        "continuity": "needs_continuity",
        "scene_planning": "needs_scene_planning",
    }
    for key, flag in flag_map.items():
        if flag in brief:
            defaults[key] = "REQUIRED" if bool(brief[flag]) else "SKIP"
    return defaults


def lock_content(state: Mapping[str, Any]) -> dict[str, Any]:
    current = normalize_state(state)
    if not current["content"].get("candidate_ready"):
        raise ValueError("content_candidate_required")
    current["content"]["locked"] = True
    current["content"]["revision"] = max(1, _integer(current["content"].get("revision"), 0) + 1)
    current["needs"] = resolve_needs(current)
    current["navigation"]["current_step"] = "content_lock"
    current = mark_sections_complete(current, "content_lock")
    return normalize_state(current)


def revise_content(state: Mapping[str, Any], *, original_intent: str) -> dict[str, Any]:
    current = normalize_state(state)
    value = _text(original_intent, 12000)
    if not value:
        raise ValueError("content_intent_required")
    current["content"]["original_intent"] = value
    current["content"]["revision"] = max(1, _integer(current["content"].get("revision"), 1) + 1)
    current["content"]["locked"] = False
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or []) + list(CONTENT_DIRTY_DEPENDENCIES)
    )
    current["navigation"]["current_step"] = "content_lock"
    return normalize_state(current)


def _require_content_lock(state: Mapping[str, Any]) -> dict[str, Any]:
    current = normalize_state(state)
    if current["parent_product"] == "multi_scene_film":
        if not bool(current["content"].get("locked")):
            current["content"]["locked"] = True
            current["content"]["original_intent"] = str(current["series"].get("goal") or "Phim dài tập")
        return current
    if not current["content"].get("locked"):
        raise ValueError("content_lock_required")
    return current


def set_episode_identity(
    state: Mapping[str, Any],
    *,
    number: int | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    current = _require_content_lock(_require_series_state(state))
    existing_episode = dict(current.get("episode") or {})
    existing_num = _integer(existing_episode.get("number"), 1)
    if existing_num <= 0:
        existing_num = 1
    existing_title = _text(existing_episode.get("title") or f"Tập {existing_num}", 500)

    if number is not None:
        episode_number = _integer(number, existing_num)
        if episode_number <= 0 or episode_number > 9999:
            episode_number = existing_num
    else:
        episode_number = existing_num

    if title is not None:
        episode_title = _text(title, 500)
        if not episode_title:
            episode_title = f"Tập {episode_number}"
    else:
        episode_title = existing_title or f"Tập {episode_number}"

    current["episode"]["number"] = episode_number
    current["episode"]["title"] = episode_title
    current["navigation"]["current_step"] = "episode"
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or [])
        + ["scene_plan", "prompts", "summary"]
    )
    return normalize_state(current)


def set_episode_content(state: Mapping[str, Any], original_intent: str) -> dict[str, Any]:
    current = _require_content_lock(_require_series_state(state))
    value = _text(original_intent, 12000)
    if not value:
        raise ValueError("episode_content_required")
    content = current["episode"]["content"]
    content["original_intent"] = value
    content["candidate_ready"] = True
    content["locked"] = False
    current["navigation"]["current_step"] = "episode"
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or [])
        + ["scene_plan", "dialogue", "prompts", "summary"]
    )
    return normalize_state(current)


def lock_episode_content(state: Mapping[str, Any]) -> dict[str, Any]:
    current = _require_content_lock(_require_series_state(state))
    content = current["episode"]["content"]
    if not content.get("candidate_ready") or not _text(content.get("original_intent"), 12000):
        raise ValueError("episode_content_required")
    content["locked"] = True
    content["revision"] = max(1, _integer(content.get("revision"), 0) + 1)
    current["navigation"]["current_step"] = "episode"
    return normalize_state(current)


def set_episode_entity_override(
    state: Mapping[str, Any],
    entity_type: str,
    entity_ids: Iterable[str],
) -> dict[str, Any]:
    current = _require_content_lock(_require_series_state(state))
    kind = _text(entity_type, 40)
    fields = {
        "characters": ("characters", "character_id"),
        "locations": ("locations", "location_id"),
        "products": ("products", "product_id"),
        "props": ("props", "prop_id"),
    }
    if kind not in fields:
        raise ValueError("episode_entity_type_invalid")
    field, id_field = fields[kind]
    valid_ids = {
        str(item.get(id_field) or "")
        for item in current["bible"].get(field) or []
        if str(item.get(id_field) or "")
    }
    selected = _dedupe(entity_ids)
    if any(item not in valid_ids for item in selected):
        raise ValueError("episode_entity_invalid")
    current["episode"]["entity_overrides"][kind] = selected
    current["navigation"]["current_step"] = "episode"
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or [])
        + ["scene_assignment", "dialogue", "prompts", "summary"]
    )
    return normalize_state(current)


def set_episode_continuity_override(
    state: Mapping[str, Any],
    key: str,
    enabled: bool,
) -> dict[str, Any]:
    current = _require_content_lock(_require_series_state(state))
    token = _text(key, 40)
    if token not in DEFAULT_CONTINUITY:
        raise ValueError("continuity_key_invalid")
    current["episode"]["continuity_overrides"][token] = bool(enabled)
    current["navigation"]["current_step"] = "episode"
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or [])
        + ["continuity", "prompts", "summary"]
    )
    return normalize_state(current)


def reset_episode_overrides(state: Mapping[str, Any]) -> dict[str, Any]:
    """Restore all Episode-level choices to the current Series defaults."""

    current = _require_content_lock(_require_series_state(state))
    current["episode"]["entity_overrides"] = {}
    current["episode"]["continuity_overrides"] = {}
    current["navigation"]["current_step"] = "episode"
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or [])
        + ["scene_assignment", "dialogue", "continuity", "prompts", "summary"]
    )
    return normalize_state(current)


def effective_episode_contract(state: Mapping[str, Any]) -> dict[str, Any]:
    current = _require_series_state(state)
    bible = current["bible"]
    overrides = dict(current["episode"].get("entity_overrides") or {})
    fields = {
        "characters": ("characters", "character_id", "character_ids"),
        "locations": ("locations", "location_id", "location_ids"),
        "products": ("products", "product_id", "product_ids"),
        "props": ("props", "prop_id", "prop_ids"),
    }
    result: dict[str, Any] = {
        "series_id": str(current["series"].get("series_id") or ""),
        "series_goal": str(current["series"].get("goal") or ""),
        "episode_id": str(current["episode"].get("episode_id") or "episode_01"),
        "episode_number": _integer(current["episode"].get("number"), 1),
        "episode_title": str(current["episode"].get("title") or ""),
        "episode_content": deepcopy(current["episode"].get("content") or {}),
        "continuity": {
            **dict(bible.get("continuity") or {}),
            **dict(current["episode"].get("continuity_overrides") or {}),
        },
        "music_scope": str(current["audio"].get("music_scope") or "none"),
        "music_plan": deepcopy(current["audio"].get("music_plan") or {}),
        "branding": deepcopy(current.get("branding") or {}),
    }
    for kind, (field, id_field, output_field) in fields.items():
        inherited = [
            str(item.get(id_field) or "")
            for item in bible.get(field) or []
            if str(item.get(id_field) or "")
        ]
        result[output_field] = list(overrides[kind]) if kind in overrides else inherited
    voice_owners = set(result["character_ids"])
    narrator_id = str((bible.get("narrator") or {}).get("narrator_id") or "")
    if narrator_id:
        voice_owners.add(narrator_id)
    result["voice_cast"] = {
        owner_id: deepcopy(voice)
        for owner_id, voice in current["audio"].get("voice_cast", {}).items()
        if owner_id in voice_owners
    }
    return result


def set_character_count(state: Mapping[str, Any], count: int) -> dict[str, Any]:
    current = _require_content_lock(state)
    target = _integer(count, -1)
    if target < MIN_CHARACTERS or target > MAX_CHARACTERS:
        raise ValueError("character_count_out_of_range")
    existing = list(current["bible"]["characters"])
    if target < len(existing):
        removed = {str(item.get("character_id") or "") for item in existing[target:]}
        episode_overrides = (
            set((current.get("episode") or {}).get("entity_overrides", {}).get("characters") or [])
            if current["parent_product"] == "multi_scene_film"
            else set()
        )
        referenced = any(str(item.get("owner_type") or "") == "character" and str(item.get("owner_id") or "") in removed for item in current["references"])
        assigned = any(removed.intersection(scene.get("character_ids") or []) for scene in current["scenes"])
        dialogue = any(str(item.get("speaker_id") or "") in removed for item in current["audio"]["dialogue_segments"])
        voices = any(character_id in current["audio"]["voice_cast"] for character_id in removed)
        relationships = any(
            removed.intersection(item.get("character_ids") or [])
            for item in current["bible"].get("relationships") or []
        )
        if removed.intersection(episode_overrides) or referenced or assigned or dialogue or voices or relationships:
            raise ValueError("character_reassignment_required")
    roster = [deepcopy(item) for item in existing[:target]]
    for _ in range(len(roster), target):
        ordinal_id = _allocate_id(current, "char", [item.get("character_id") for item in roster])
        ordinal = _integer(ordinal_id.rsplit("_", 1)[-1], len(roster) + 1)
        roster.append(_character(ordinal))
        roster[-1]["character_id"] = ordinal_id
        roster[-1]["display_name"] = f"Nhan vat {len(roster)}"
    current["bible"]["characters"] = roster
    current["bible"]["character_count_confirmed"] = True
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or [])
        + ["scene_assignment", "voice_cast", "continuity", "prompts", "summary"]
    )
    current["navigation"]["current_step"] = "production_bible"
    return normalize_state(current)


def update_character(state: Mapping[str, Any], character_id: str, **changes: Any) -> dict[str, Any]:
    current = _require_content_lock(state)
    target = _text(character_id, 80)
    roster = list(current["bible"]["characters"])
    index = next((idx for idx, item in enumerate(roster) if str(item.get("character_id") or "") == target), -1)
    if index < 0:
        raise ValueError("character_not_found")
    item = dict(roster[index])
    text_fields = (
        "display_name", "role", "age_band", "description", "face", "hair",
        "body", "wardrobe", "personality", "behavior", "voice_id",
    )
    for field in text_fields:
        if field in changes:
            item[field] = _text(changes[field], 1600 if field in {"description", "behavior"} else 240)
    if "gender" in changes:
        gender = _text(changes["gender"], 40)
        if gender not in GENDERS:
            raise ValueError("character_gender_invalid")
        item["gender"] = gender
    if "continuity_lock" in changes:
        item["continuity_lock"] = bool(changes["continuity_lock"])
    item["locked_by_user"] = True
    roster[index] = item
    current["bible"]["characters"] = roster
    voice_id = str(item.get("voice_id") or "")
    if voice_id:
        current["audio"]["voice_cast"][target] = {
            "voice_id": voice_id,
            "gender": str(item.get("gender") or "unspecified"),
            "server_renderable": False,
            "source": "user_selection_unverified",
        }
    elif "voice_id" in changes:
        current["audio"]["voice_cast"].pop(target, None)
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or [])
        + ["scene_assignment", "voice_cast", "continuity", "prompts", "summary"]
    )
    return normalize_state(current)


def set_location_count(state: Mapping[str, Any], count: int) -> dict[str, Any]:
    current = _require_content_lock(state)
    target = _integer(count, -1)
    if target < MIN_LOCATIONS or target > MAX_LOCATIONS:
        raise ValueError("location_count_out_of_range")
    existing = list(current["bible"]["locations"])
    if target < len(existing):
        removed = {str(item.get("location_id") or "") for item in existing[target:]}
        episode_overrides = (
            set((current.get("episode") or {}).get("entity_overrides", {}).get("locations") or [])
            if current["parent_product"] == "multi_scene_film"
            else set()
        )
        if removed.intersection(episode_overrides):
            raise ValueError("location_reassignment_required")
        if any(str(scene.get("location_id") or "") in removed for scene in current["scenes"]):
            raise ValueError("location_reassignment_required")
        if any(str(item.get("owner_type") or "") == "location" and str(item.get("owner_id") or "") in removed for item in current["references"]):
            raise ValueError("location_reassignment_required")
    locations = [deepcopy(item) for item in existing[:target]]
    for _ in range(len(locations), target):
        ordinal_id = _allocate_id(current, "loc", [item.get("location_id") for item in locations])
        ordinal = _integer(ordinal_id.rsplit("_", 1)[-1], len(locations) + 1)
        locations.append(_location(ordinal))
        locations[-1]["location_id"] = ordinal_id
        locations[-1]["name"] = f"Boi canh {len(locations)}"
    current["bible"]["locations"] = locations
    current["bible"]["location_count_confirmed"] = True
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or []) + ["scene_assignment", "continuity", "prompts", "summary"]
    )
    return normalize_state(current)


def update_location(state: Mapping[str, Any], location_id: str, **changes: Any) -> dict[str, Any]:
    current = _require_content_lock(state)
    target = _text(location_id, 80)
    locations = list(current["bible"]["locations"])
    index = next((idx for idx, item in enumerate(locations) if str(item.get("location_id") or "") == target), -1)
    if index < 0:
        raise ValueError("location_not_found")
    item = dict(locations[index])
    for field in ("name", "description", "indoor_outdoor", "time_of_day", "weather", "lighting", "mood"):
        if field in changes:
            item[field] = _text(changes[field], 1600 if field == "description" else 240)
    item["locked_by_user"] = True
    locations[index] = item
    current["bible"]["locations"] = locations
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or []) + ["scene_assignment", "continuity", "prompts", "summary"]
    )
    return normalize_state(current)


def set_narrator(
    state: Mapping[str, Any],
    *,
    display_name: str,
    style: str = "",
    voice_id: str = "",
    gender: str = "unspecified",
    narrator_id: str = "",
) -> dict[str, Any]:
    current = _require_content_lock(state)
    name = _text(display_name, 240)
    if not name:
        raise ValueError("narrator_name_required")
    selected_gender = _text(gender, 40) or "unspecified"
    if selected_gender not in GENDERS:
        raise ValueError("narrator_gender_invalid")
    existing = dict(current["bible"].get("narrator") or {})
    previous_id = _text(existing.get("narrator_id"), 32)
    target_id = _text(narrator_id, 32) or _text(existing.get("narrator_id"), 32) or "narrator_01"
    if "|" in target_id:
        raise ValueError("narrator_id_invalid")
    narrator = {
        **existing,
        "narrator_id": target_id,
        "display_name": name,
        "style": _text(style, 240),
        "gender": selected_gender,
        "voice_id": _text(voice_id, 240),
    }
    current["bible"]["narrator"] = narrator
    if previous_id and previous_id != target_id:
        current["audio"]["voice_cast"].pop(previous_id, None)
    if narrator["voice_id"]:
        current["audio"]["voice_cast"][target_id] = {
            "voice_id": narrator["voice_id"],
            "gender": selected_gender,
            "server_renderable": False,
            "source": "user_selection_unverified",
        }
    else:
        current["audio"]["voice_cast"].pop(target_id, None)
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or []) + ["production_bible", "scene_assignment", "voice_cast", "prompts", "summary"]
    )
    return normalize_state(current)


def clear_narrator(state: Mapping[str, Any]) -> dict[str, Any]:
    current = _require_content_lock(state)
    narrator_id = str((current["bible"].get("narrator") or {}).get("narrator_id") or "")
    if narrator_id and (
        any(bool(scene.get("narrator_enabled")) for scene in current["scenes"])
        or any(str(item.get("speaker_id") or "") == narrator_id for item in current["audio"]["dialogue_segments"])
    ):
        raise ValueError("narrator_reassignment_required")
    current["bible"]["narrator"] = None
    if narrator_id:
        current["audio"]["voice_cast"].pop(narrator_id, None)
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or []) + ["production_bible", "scene_assignment", "voice_cast", "prompts", "summary"]
    )
    return normalize_state(current)


def add_product(
    state: Mapping[str, Any],
    *,
    name: str,
    category: str = "",
    description: str = "",
    product_id: str = "",
) -> dict[str, Any]:
    current = _require_content_lock(state)
    label = _text(name, 240)
    if not label:
        raise ValueError("product_name_required")
    products = list(current["bible"].get("products") or [])
    if len(products) >= 20:
        raise ValueError("product_limit_reached")
    target_id = _text(product_id, 32) or _allocate_id(
        current, "prod", [item.get("product_id") for item in products]
    )
    if "|" in target_id:
        raise ValueError("product_id_invalid")
    if any(str(item.get("product_id") or "") == target_id for item in products):
        raise ValueError("product_id_exists")
    products.append({
        "product_id": target_id,
        "name": label,
        "category": _text(category, 160),
        "type": _text(category, 160),
        "description": _text(description, 1600),
        "geometry_shape_constraints": "",
        "colors": [],
        "logo_text_constraints": "",
        "must_preserve": [_text(description, 1600)] if _text(description, 1600) else [],
        "reference_asset_ids": [],
        "locked_by_user": True,
    })
    current["bible"]["products"] = products[:20]
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or []) + ["production_bible", "scene_assignment", "continuity", "prompts", "summary"]
    )
    return normalize_state(current)


def add_prop(
    state: Mapping[str, Any],
    *,
    name: str,
    description: str = "",
    prop_id: str = "",
) -> dict[str, Any]:
    current = _require_content_lock(state)
    label = _text(name, 240)
    if not label:
        raise ValueError("prop_name_required")
    props = list(current["bible"].get("props") or [])
    if len(props) >= 40:
        raise ValueError("prop_limit_reached")
    target_id = _text(prop_id, 32) or _allocate_id(
        current, "prop", [item.get("prop_id") for item in props]
    )
    if "|" in target_id:
        raise ValueError("prop_id_invalid")
    if any(str(item.get("prop_id") or "") == target_id for item in props):
        raise ValueError("prop_id_exists")
    props.append({
        "prop_id": target_id,
        "name": label,
        "description": _text(description, 1600),
        "owner_hints": [],
        "scene_hints": [],
        "reference_asset_ids": [],
        "locked_by_user": True,
    })
    current["bible"]["props"] = props[:40]
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or []) + ["production_bible", "scene_assignment", "continuity", "prompts", "summary"]
    )
    return normalize_state(current)


def add_relationship(
    state: Mapping[str, Any],
    *,
    character_ids: Iterable[str] | str,
    relation: str = "",
    relationship_type: str = "",
    description: str = "",
    relationship_id: str = "",
) -> dict[str, Any]:
    current = _require_content_lock(state)
    if isinstance(character_ids, str):
        raw_ids = [item.strip() for item in character_ids.replace(",", "|").split("|")]
    else:
        raw_ids = list(character_ids or [])
    selected_ids = _dedupe(raw_ids)
    valid_ids = {str(item.get("character_id") or "") for item in current["bible"].get("characters") or []}
    if len(selected_ids) < 2 or any(item not in valid_ids for item in selected_ids):
        raise ValueError("relationship_characters_invalid")
    label = _text(relation or relationship_type, 160)
    if not label:
        raise ValueError("relationship_type_required")
    relationships = list(current["bible"].get("relationships") or [])
    if len(relationships) >= 80:
        raise ValueError("relationship_limit_reached")
    target_id = _text(relationship_id, 32) or _allocate_id(
        current, "rel", [item.get("relationship_id") for item in relationships]
    )
    if "|" in target_id:
        raise ValueError("relationship_id_invalid")
    if any(str(item.get("relationship_id") or "") == target_id for item in relationships):
        raise ValueError("relationship_id_exists")
    relationships.append({
        "relationship_id": target_id,
        "character_ids": selected_ids,
        "relation": label,
        "description": _text(description, 1000),
    })
    current["bible"]["relationships"] = relationships[:80]
    for character in current["bible"].get("characters") or []:
        character_id = str(character.get("character_id") or "")
        if character_id in selected_ids:
            hints = list(character.get("relationship_hints") or [])
            if target_id not in hints:
                hints.append(target_id)
            character["relationship_hints"] = hints[:40]
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or []) + ["production_bible", "continuity", "prompts", "summary"]
    )
    return normalize_state(current)


def _owner_exists(state: Mapping[str, Any], owner_type: str, owner_id: str) -> bool:
    bible = dict(state.get("bible") or {})
    field_map = {
        "character": ("characters", "character_id"),
        "location": ("locations", "location_id"),
        "product": ("products", "product_id"),
        "prop": ("props", "prop_id"),
    }
    if owner_type not in field_map:
        return owner_type in {"legacy_unassigned", "source_video", "storyboard_panel", "frame"}
    field, id_field = field_map[owner_type]
    return any(str(item.get(id_field) or "") == owner_id for item in bible.get(field) or [])


def add_reference(
    state: Mapping[str, Any],
    *,
    asset_type: str,
    owner_type: str,
    owner_id: str,
    role: str,
    telegram_file_id: str,
    fingerprint: str,
    allowed_scene_ids: Iterable[str] | None = None,
    **metadata: Any,
) -> dict[str, Any]:
    current = _require_content_lock(state)
    owner_kind = _text(owner_type, 80)
    owner = _text(owner_id, 120)
    reference_role = _text(role, 80)
    identity = _text(fingerprint, 256)
    file_id = _text(telegram_file_id, 512)
    if not identity or not file_id:
        raise ValueError("reference_asset_identity_required")
    if not _owner_exists(current, owner_kind, owner):
        raise ValueError("reference_owner_invalid")
    scene_scope = _dedupe(allowed_scene_ids or [])
    valid_scene_ids = {str(item.get("scene_id") or "") for item in current["scenes"]}
    if any(scene_id not in valid_scene_ids for scene_id in scene_scope):
        raise ValueError("reference_scene_invalid")
    existing = next(
        (
            item for item in current["references"]
            if str(item.get("fingerprint") or "") == identity
            and str(item.get("owner_type") or "") == owner_kind
            and str(item.get("owner_id") or "") == owner
            and str(item.get("role") or "") == reference_role
        ),
        None,
    )
    if existing:
        return current
    asset_id = _allocate_id(
        current, "asset", [item.get("asset_id") for item in current["references"]]
    )
    record = {
        "asset_id": asset_id,
        "asset_type": _text(asset_type, 80),
        "owner_type": owner_kind,
        "owner_id": owner,
        "role": reference_role,
        "angle": _text(metadata.pop("angle", ""), 80),
        "priority": max(0, _integer(metadata.pop("priority", 0), 0)),
        "fingerprint": identity,
        "source": "telegram",
        "telegram_file_id": file_id,
        "allowed_scene_ids": scene_scope,
        "metadata": deepcopy(metadata),
    }
    current["references"].append(record)
    field_map = {
        "character": ("characters", "character_id"),
        "location": ("locations", "location_id"),
        "product": ("products", "product_id"),
        "prop": ("props", "prop_id"),
    }
    if owner_kind in field_map:
        field, id_field = field_map[owner_kind]
        for item in current["bible"][field]:
            if str(item.get(id_field) or "") == owner:
                item["reference_asset_ids"] = _dedupe(list(item.get("reference_asset_ids") or []) + [asset_id])
                break
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or []) + ["references", "continuity", "prompts", "summary"]
    )
    return normalize_state(current)


def suggest_scene_count(state: Mapping[str, Any]) -> dict[str, Any]:
    current = _require_content_lock(state)
    adapter = _adapter(current["parent_product"])
    metadata = dict(current["source"].get("metadata") or {})
    if current["parent_product"] == "storyboard_prompt" and _integer(metadata.get("detected_panel_count"), 0) > 0:
        count = _integer(metadata.get("detected_panel_count"), 1)
        source = "storyboard_panel_count"
    elif current["parent_product"] == "frame_video_local" and current["source"]["assets"]:
        count = len(current["source"]["assets"])
        source = "frame_asset_count"
    else:
        seconds_per_scene = max(
            1,
            _integer(current["format"].get("seconds_per_scene"), int(adapter["seconds_per_scene"])),
        )
        duration = max(1, _integer(current["format"].get("target_duration_seconds"), seconds_per_scene))
        count = ceil(duration / seconds_per_scene)
        source = "duration_and_content"
    count = max(int(adapter["minimum_scene_count"]), min(int(adapter["maximum_scene_count"]), count))
    return {
        "count": count,
        "seconds_per_scene": max(
            1,
            _integer(current["format"].get("seconds_per_scene"), int(adapter["seconds_per_scene"])),
        ),
        "source": source,
    }


def set_scene_count_preference(state: Mapping[str, Any], count: int) -> dict[str, Any]:
    current = normalize_state(state)
    if (
        current["parent_product"] != "video_ai_real"
        or current["entry_mode"] not in VIDEO_AI_REAL_PRODUCT_FIRST_MODES
    ):
        raise ValueError("scene_count_out_of_range")
    if current["content"].get("locked") or current["scenes"]:
        raise ValueError("scene_content_reconcile_required")
    adapter = _adapter(current["parent_product"])
    target = _integer(count, 0)
    if target < int(adapter["minimum_scene_count"]) or target > int(adapter["maximum_scene_count"]):
        raise ValueError("scene_count_out_of_range")
    seconds = max(1, _integer(current["format"].get("seconds_per_scene"), int(adapter["seconds_per_scene"])))
    current["format"].update({
        "scene_count_policy": "user",
        "scene_count": target,
        "scene_count_confirmed": False,
        "target_duration_seconds": target * seconds,
    })
    current["navigation"]["current_step"] = "format"
    return normalize_state(current)


def _link_scene_states(scenes: list[dict[str, Any]]) -> None:
    for index, scene in enumerate(scenes):
        scene["continuity_from_scene_id"] = scenes[index - 1]["scene_id"] if index > 0 else ""
        scene["continuity_to_scene_id"] = scenes[index + 1]["scene_id"] if index + 1 < len(scenes) else ""
        if index > 0:
            scene["start_state"] = _text(scenes[index - 1].get("completion_state"), 800)


def scene_plan_complete(state: Mapping[str, Any]) -> bool:
    current = normalize_state(state)
    scenes = list(current.get("scenes") or [])
    return bool(
        current["format"].get("scene_count_confirmed")
        and scenes
        and all(
            all(_text(scene.get(field), 800) for field in ("semantic_beat", "main_action", "completion_state"))
            for scene in scenes
        )
    )


def _scene_plan_intent(state: Mapping[str, Any]) -> str:
    content = dict(state.get("content") or {})
    brief = dict(content.get("approved_brief") or {})
    episode = dict((state.get("episode") or {}).get("content") or {})
    candidates = []
    if str(state.get("parent_product") or "") == "multi_scene_film":
        candidates.extend((episode.get("original_intent"), (state.get("series") or {}).get("goal")))
    candidates.extend((
        content.get("original_intent"),
        brief.get("prompt"),
        brief.get("visual_prompt"),
        brief.get("title"),
    ))
    return _text(next((item for item in candidates if _text(item, 1200)), "Nội dung đã khóa"), 1200)


def _scene_plan_selected_fields(state: Mapping[str, Any], group: str) -> dict[str, str]:
    selected: dict[str, str] = {}
    for key, raw in dict(state.get(group) or {}).items():
        item = dict(raw) if isinstance(raw, Mapping) else {"enabled": True, "value": raw}
        value = _text(item.get("value"), 240)
        if bool(item.get("enabled")) and value:
            selected[_text(key, 80)] = value
    return selected


def _scene_plan_profile_context(state: Mapping[str, Any], scene_count: int):
    intent = _scene_plan_intent(state)
    requested = _text((state.get("content") or {}).get("profile_id"), 120)
    try:
        profile = (
            video_profiles.get_video_profile(requested)
            if requested
            else video_profiles.resolve_profile_for_menu_product(
                str(state.get("parent_product") or ""),
                user_text=intent,
            )
        )
    except KeyError:
        profile = video_profiles.resolve_profile_for_menu_product(
            str(state.get("parent_product") or ""),
            user_text=intent,
        )
    context = video_profile_context_engine.select_prompt_context(
        profile.profile_id,
        user_idea=intent,
        creative_controls=_scene_plan_selected_fields(state, "creative_controls"),
        scene_count=max(1, scene_count),
        language="vi",
    )
    return profile, context


def _scene_plan_reference_context(state: Mapping[str, Any]) -> tuple[int, str]:
    rows = [
        dict(item)
        for item in list((state.get("source") or {}).get("assets") or [])
        + list(state.get("references") or [])
        if isinstance(item, Mapping)
    ]
    image_types = {"image", "frame", "photo", "storyboard", "storyboard_frame", "raw_image"}
    images = [item for item in rows if str(item.get("asset_type") or "").lower() in image_types]
    notes = []
    for item in images[:5]:
        metadata = dict(item.get("metadata") or {})
        note = _text(
            metadata.get("caption")
            or metadata.get("description")
            or item.get("role"),
            120,
        )
        if note and note not in notes:
            notes.append(note)
    return len(images), "; ".join(notes)


def build_scene_plan_ai_prompt(state: Mapping[str, Any], scenes: Iterable[Mapping[str, Any]]) -> str:
    """Build a compact, product-aware Gemini instruction from existing planning state."""

    current = normalize_state(state)
    scene_rows = [dict(item) for item in scenes if isinstance(item, Mapping)]
    product = str(current.get("parent_product") or "")
    scene_count = max(1, len(scene_rows))
    seconds = max(
        1,
        _integer(
            (current.get("format") or {}).get("seconds_per_scene"),
            _integer((scene_rows[0] if scene_rows else {}).get("duration_target"), 8),
        ),
    )
    profile, context = _scene_plan_profile_context(current, scene_count)
    intent = _scene_plan_intent(current)
    brief = dict((current.get("content") or {}).get("approved_brief") or {})

    if product == "video_ai_real":
        product_rule = (
            f"Video AI chân thật ngắn. Mỗi cảnh dài đúng {seconds} giây; mỗi cảnh chỉ một hành động cụ thể "
            "có thể hoàn tất trong thời lượng đó; không viết thành kịch bản dài và không nhồi nhiều diễn biến."
        )
    elif product == "video_trend":
        product_rule = "Bám dữ liệu trend đã phân tích và nội dung đầu vào đã khóa; không tự thêm một tuyến truyện khác."
    elif product == "script_image_video":
        product_rule = "Bám sát kịch bản đã khóa, chia đúng ý kịch bản vào từng cảnh và không tự đổi cốt truyện."
    elif product == "multi_scene_film":
        product_rule = "Giữ mạch liên tục của series và tập; bám nhân vật, bối cảnh, tình tiết và trạng thái nối tiếp."
    elif product == "storyboard_prompt":
        product_rule = "Bám đúng thứ tự và nội dung các khung storyboard đã có; không đảo hoặc phát minh khung mới."
    elif product == "frame_video_local":
        product_rule = "Bám thứ tự ảnh nguồn; mỗi cảnh chỉ mô tả chuyển động phù hợp với đúng ảnh của cảnh đó."
    elif product == "self_shot_scene_change":
        product_rule = "Bám chủ thể và chuyển động của video tự quay; chỉ thay đổi theo lựa chọn đã khóa."
    else:
        product_rule = f"Video ngắn; mỗi cảnh hoàn tất một hành động rõ ràng trong khoảng {seconds} giây."

    characters = []
    voice_cast = dict((current.get("audio") or {}).get("voice_cast") or {})
    for item in list((current.get("bible") or {}).get("characters") or [])[:5]:
        character_id = str(item.get("character_id") or "")
        details = [
            _text(item.get("display_name") or item.get("name") or "Nhân vật", 80),
            _text(item.get("wardrobe") or item.get("appearance") or item.get("body"), 120),
        ]
        has_voice = bool(item.get("voice_id") or (voice_cast.get(character_id) or {}).get("voice_id"))
        if has_voice:
            details.append("giọng đã gán")
        characters.append(" (".join([details[0], ", ".join(value for value in details[1:] if value)]) + ")" if any(details[1:]) else details[0])

    locations = [
        _text(item.get("name") or item.get("description"), 140)
        for item in list((current.get("bible") or {}).get("locations") or [])[:5]
        if _text(item.get("name") or item.get("description"), 140)
    ]
    image_count, image_notes = _scene_plan_reference_context(current)
    audio = dict(current.get("audio") or {})
    dialogue = [
        _text(item.get("text"), 160)
        for item in list(audio.get("dialogue_segments") or [])[:4]
        if _text(item.get("text"), 160)
    ]
    music_plan = dict(audio.get("music_plan") or {})
    music_detail = _text(
        music_plan.get("track_id") or music_plan.get("prompt") or music_plan.get("title"),
        120,
    )
    source_metadata = dict((current.get("source") or {}).get("metadata") or {})
    source_analysis = _text(
        source_metadata.get("trend_analysis")
        or source_metadata.get("video_analysis")
        or source_metadata.get("analysis")
        or source_metadata.get("transcript"),
        500,
    )
    selected_context = _text(
        brief.get("selected_context_prompt")
        or brief.get("prompt")
        or brief.get("visual_prompt")
        or brief.get("context_guidance"),
        700,
    )
    creative = _scene_plan_selected_fields(current, "creative_controls")
    requirements = _scene_plan_selected_fields(current, "preservation_requirements")

    lines = [
        "Bạn là đạo diễn lập kế hoạch cảnh video AI.",
        f"Sản phẩm: {product}. {product_rule}",
        f"Nội dung: {intent}",
        f"Kho nội bộ: {profile.profile_id}; phong cách={context.selected_visual_style}; máy quay={context.selected_camera_language}; chuyển động={context.selected_motion_language}.",
        f"Ảnh tham chiếu: {image_count}" + (f"; {image_notes}" if image_notes else "") + ". Giữ nhận dạng và bối cảnh theo ảnh đã gắn.",
    ]
    if product != "video_ai_real" and context.selected_script_formula:
        lines.append(f"Cấu trúc phù hợp: {context.selected_script_formula}.")
    if source_analysis:
        lines.append(f"Phân tích nguồn: {source_analysis}")
    if selected_context:
        lines.append(f"Ngữ cảnh triển khai đã chọn: {selected_context}")
    if creative:
        lines.append("Phong cách đã chọn: " + "; ".join(f"{key}={value}" for key, value in creative.items()))
    if requirements:
        lines.append("Yêu cầu giữ nguyên: " + "; ".join(f"{key}={value}" for key, value in requirements.items()))
    if characters:
        lines.append("Nhân vật: " + "; ".join(characters))
    if locations:
        lines.append("Bối cảnh: " + "; ".join(locations))
    if dialogue or str(audio.get("subtitle_mode") or ""):
        lines.append(
            "Lời thoại/phụ đề: "
            + (" | ".join(dialogue) if dialogue else "theo nội dung đã chọn")
            + f"; chế độ={str(audio.get('subtitle_mode') or 'theo dữ liệu hiện có')}. Mọi câu phải nói xong trong thời lượng cảnh."
        )
    if str(audio.get("music_scope") or "none") != "none":
        lines.append(
            f"Nhạc: {str(audio.get('music_scope') or 'none')}"
            + (f"; {music_detail}" if music_detail else "")
            + ". Giữ nhịp cảnh khớp nhạc đã chọn."
        )
    lines.extend([
        f"Trả về JSON array đúng {scene_count} object, theo thứ tự cảnh.",
        "Mỗi object chỉ có semantic_beat, main_action, completion_state; viết tiếng Việt có dấu, ngắn, cụ thể và khả thi.",
        "Chỉ trả JSON thuần, không codeblock.",
    ])
    return "\n".join(lines)


def suggest_scene_plan(state: Mapping[str, Any]) -> dict[str, Any]:
    """Fill only missing scene semantics with a provider-free content outline."""

    current = _require_content_lock(state)
    scenes = list(current.get("scenes") or [])
    if not scenes:
        raise ValueError("scene_plan_missing")
    brief = dict(current["content"].get("approved_brief") or {})
    episode_intent = ""
    if current["parent_product"] == "multi_scene_film":
        episode_content = dict(current["episode"].get("content") or {})
        if episode_content.get("locked"):
            episode_intent = _text(episode_content.get("original_intent"), 12000)
    topic = _text(
        episode_intent
        or brief.get("title")
        or current["content"].get("original_intent")
        or "noi dung da khoa",
        240,
    )
    selected_context = str(brief.get("prompt") or brief.get("visual_prompt") or "").strip()
    context_blueprint = dict(brief.get("prompt_blueprint") or {})
    context_sequence = [
        _text(item, 240)
        for item in str(context_blueprint.get("sequence") or "").split("→")
        if _text(item, 240)
    ]
    context_focus = _text(context_blueprint.get("focus"), 800)
    total = len(scenes)
    for index, scene in enumerate(scenes, 1):
        if total == 1:
            role = "complete"
            defaults = {
                "semantic_beat": f"Trinh bay tron ven: {topic}",
                "main_action": "Thuc hien mot hanh dong day du theo noi dung da khoa.",
                "completion_state": "Thong diep chinh da duoc truyen dat tron ven.",
            }
        elif index == 1:
            role = "hook"
            defaults = {
                "semantic_beat": f"Mo dau thu hut cho: {topic}",
                "main_action": "Gioi thieu boi canh va dat van de chinh.",
                "completion_state": "Nguoi xem da hieu boi canh va muon theo doi tiep.",
            }
        elif index == total:
            role = "resolution"
            defaults = {
                "semantic_beat": f"Ket lai thong diep cua: {topic}",
                "main_action": "Hoan tat hanh dong chinh va tong ket noi dung.",
                "completion_state": "Thong diep cuoi cung va trang thai ket thuc da ro rang.",
            }
        else:
            role = "development"
            defaults = {
                "semantic_beat": f"Phat trien y {index - 1} cua: {topic}",
                "main_action": "Tiep noi ket qua canh truoc va phat trien mot y chinh.",
                "completion_state": f"Y phat trien {index - 1} da hoan tat de chuyen sang canh tiep.",
            }
        if selected_context and str(brief.get("context_suggestion_key") or "").startswith("product_context_"):
            beat = context_sequence[(index - 1) % len(context_sequence)] if context_sequence else topic
            defaults.update({
                "semantic_beat": f"{beat}: {topic}",
                "main_action": f"{context_focus or 'Thực hiện đúng ý chính'} Tập trung vào {beat.lower()}.",
                "completion_state": f"{beat} đã hoàn tất và sẵn sàng nối sang cảnh kế tiếp.",
            })
        filled = False
        if not _text(scene.get("scene_role"), 80):
            scene["scene_role"] = role
        for field, value in defaults.items():
            if not _text(scene.get(field), 800):
                scene[field] = value
                filled = True
        if filled and str(scene.get("planning_source") or "") != "user":
            scene["planning_source"] = "rule_content_outline"
            scene["planning_confidence"] = 0.55
    _link_scene_states(scenes)
    current["scenes"] = scenes
    current["navigation"]["current_step"] = "scene_plan"
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or [])
        + ["scene_plan", "scene_assignment", "dialogue", "prompts", "summary"]
    )
    return normalize_state(current)


def _scene_plan_marked_actions(value: Any, scene_count: int) -> list[str]:
    text = str(value or "").strip()
    matches = list(_SCENE_PLAN_MARKER_RE.finditer(text))
    expected = list(range(1, max(1, int(scene_count or 1)) + 1))
    if [int(match.group(1)) for match in matches] != expected:
        return []
    actions = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        action = _text(text[match.end():end].strip(" \t\r\n:;|,-–—"), 800)
        if not action:
            return []
        actions.append(action)
    return actions


def _scene_plan_profile_beats(state: Mapping[str, Any], scene_count: int) -> list[dict[str, Any]]:
    requested = _text((state.get("content") or {}).get("profile_id"), 120)
    profile_key = video_profile_catalog.canonical_profile_key(requested)
    if not profile_key:
        profile, _context = _scene_plan_profile_context(state, scene_count)
        profile_key = video_profile_catalog.canonical_profile_key(profile.profile_id)
    return video_profile_catalog.semantic_beats_for_bundle(
        profile_key or "storytelling_life",
        (),
        scene_count,
    )


def _scene_plan_vault_actions(state: Mapping[str, Any], scene_count: int) -> list[str]:
    count = max(1, int(scene_count or 1))
    scene_intents = [
        _text(item.get("original_scene_intent"), 800)
        for item in list(state.get("scenes") or [])
        if str(item.get("planning_source") or "") != "local_prompt_vault"
    ]
    if len(scene_intents) == count and all(scene_intents) and len(set(scene_intents)) == count:
        return scene_intents

    content = dict(state.get("content") or {})
    brief = dict(content.get("approved_brief") or {})
    source_metadata = dict((state.get("source") or {}).get("metadata") or {})
    if str(state.get("parent_product") or "") == "script_image_video":
        source_text = _text(source_metadata.get("source_text") or content.get("original_intent"), 12000)
        parsed = video_script_product.semantic_beats(source_text, count) if source_text else {}
        actions = [
            _text(item.get("action"), 800)
            for item in list(parsed.get("semantic_beats") or [])
            if isinstance(item, Mapping)
        ]
        if len(actions) == count and all(actions):
            return actions

    candidates = [
        _scene_plan_intent(state),
        source_metadata.get("source_text"),
        source_metadata.get("trend_analysis"),
        source_metadata.get("video_analysis"),
        source_metadata.get("analysis"),
        source_metadata.get("transcript"),
    ]
    for candidate in candidates:
        actions = _scene_plan_marked_actions(candidate, count)
        if actions:
            return actions

    sequence = str((brief.get("prompt_blueprint") or {}).get("sequence") or "")
    for candidate in [sequence, *candidates]:
        parts = [
            _text(item, 800)
            for item in re.split(r"\s*(?:→|->|;|\r?\n)\s*", str(candidate or ""))
            if _text(item, 800)
        ]
        if len(parts) == count:
            return parts
    return []


def suggest_scene_plan_from_vault(state: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the existing local prompt vault when Gemini is unavailable."""

    current = suggest_scene_plan(state)
    scenes = list(current.get("scenes") or [])
    _profile, context = _scene_plan_profile_context(current, len(scenes))
    templates = list(context.selected_scene_role_templates or [])
    intent = _scene_plan_intent(current)
    product = str(current.get("parent_product") or "")
    total = len(scenes)
    scene_actions = _scene_plan_vault_actions(current, total)
    profile_beats = _scene_plan_profile_beats(current, total)
    subject = _text(intent.split("|", 1)[0], 180) or "Nội dung đã khóa"
    for index, scene in enumerate(scenes, 1):
        if bool(scene.get("locked_by_user")) or str(scene.get("planning_source") or "") == "user":
            continue
        template: dict[str, Any] = {}
        if templates:
            template_index = 0 if total <= 1 else round((index - 1) * (len(templates) - 1) / (total - 1))
            template = dict(templates[template_index])
            scene["scene_role"] = _text(template.get("role"), 80) or str(scene.get("scene_role") or "complete")
            scene["original_scene_intent"] = _text(
                f"{template.get('purpose') or template.get('title') or scene['scene_role']}: {intent}",
                1600,
            )
        action = scene_actions[index - 1] if index <= len(scene_actions) else ""
        profile_beat = (
            dict(profile_beats[index - 1])
            if not action and index <= len(profile_beats)
            else {}
        )
        beat_idea = _text(profile_beat.get("main_idea"), 300)
        beat_action = _text(profile_beat.get("action"), 500)
        beat_completion = _text(profile_beat.get("completion"), 500)
        if profile_beat.get("role"):
            scene["scene_role"] = _text(profile_beat.get("role"), 80)
        scene["original_scene_intent"] = _text(action or beat_idea or scene.get("original_scene_intent"), 1600)
        if product == "video_ai_real":
            duration = max(1, _integer(scene.get("duration_target"), _integer(current["format"].get("seconds_per_scene"), 8)))
            scene["semantic_beat"] = _text(action or (f"{beat_idea}: {subject}" if beat_idea else f"{subject} · Cảnh {index}"), 800)
            scene["main_action"] = _text(
                (
                    f"{action}. Hoàn tất trọn hành động trong {duration} giây."
                    if action
                    else (
                        f"{beat_action} cho {subject}; hoàn tất trong {duration} giây."
                        if beat_action
                        else f"Thực hiện một hành động duy nhất cho Cảnh {index} và hoàn tất trong {duration} giây."
                    )
                ),
                800,
            )
            scene["completion_state"] = _text(
                (
                    f"{beat_completion} Hành động Cảnh {index} hoàn tất rõ ràng trong {duration} giây."
                    if beat_completion
                    else f"Hành động Cảnh {index} đã hoàn tất rõ ràng trong {duration} giây."
                ),
                800,
            )
        else:
            purpose = _text(template.get("purpose") or template.get("title"), 240) or f"Phát triển nội dung Cảnh {index}"
            scene["semantic_beat"] = _text(action or (f"{beat_idea}: {subject}" if beat_idea else f"{purpose}: {subject}"), 800)
            scene["main_action"] = _text(
                (
                    f"Thể hiện trọn vẹn: {action}."
                    if action
                    else (
                        f"{beat_action}; bám trực tiếp nội dung {subject}."
                        if beat_action
                        else f"Thể hiện {purpose.lower()} bằng một hành động rõ ràng, bám nội dung đã khóa."
                    )
                ),
                800,
            )
            scene["completion_state"] = _text(
                beat_completion or f"Ý {purpose.lower()} đã hoàn tất và tạo trạng thái nối sang cảnh kế tiếp.",
                800,
            )
        scene["planning_source"] = "local_prompt_vault"
        scene["planning_confidence"] = 0.7
    _link_scene_states(scenes)
    current["scenes"] = scenes
    return normalize_state(current)


def map_source_asset_to_reference(
    state: Mapping[str, Any],
    *,
    source_asset_id: str,
    owner_type: str,
    owner_id: str,
    role: str,
    allowed_scene_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Map an intake asset by identity while preserving the original source row."""

    current = _require_content_lock(state)
    source_id = _text(source_asset_id, 120)
    source_asset = next(
        (
            item for item in current["source"].get("assets") or []
            if str(item.get("asset_id") or "") == source_id
        ),
        None,
    )
    if not source_asset:
        raise ValueError("source_asset_not_found")
    mapped = add_reference(
        current,
        asset_type=str(source_asset.get("asset_type") or "image"),
        owner_type=owner_type,
        owner_id=owner_id,
        role=role,
        telegram_file_id=str(source_asset.get("telegram_file_id") or ""),
        fingerprint=str(source_asset.get("fingerprint") or ""),
        allowed_scene_ids=allowed_scene_ids,
        source_asset_id=source_id,
    )
    for reference in mapped["references"]:
        if (
            str(reference.get("fingerprint") or "") == str(source_asset.get("fingerprint") or "")
            and str(reference.get("owner_type") or "") == _text(owner_type, 80)
            and str(reference.get("owner_id") or "") == _text(owner_id, 120)
            and str(reference.get("role") or "") == _text(role, 80)
        ):
            reference["source"] = "source_intake"
            reference["metadata"] = {
                **dict(reference.get("metadata") or {}),
                "source_asset_id": source_id,
            }
            break
    return normalize_state(mapped)


def update_scene_plan(
    state: Mapping[str, Any],
    scene_id: str,
    *,
    semantic_beat: str,
    main_action: str,
    completion_state: str,
    original_scene_intent: str = "",
) -> dict[str, Any]:
    current = _require_content_lock(state)
    scene = next(
        (item for item in current["scenes"] if str(item.get("scene_id") or "") == _text(scene_id, 80)),
        None,
    )
    if scene is None:
        raise ValueError("scene_not_found")
    values = {
        "semantic_beat": _text(semantic_beat, 800),
        "main_action": _text(main_action, 800),
        "completion_state": _text(completion_state, 800),
    }
    if not all(values.values()):
        raise ValueError("scene_plan_format_invalid")
    scene.update(values)
    scene["original_scene_intent"] = _text(original_scene_intent, 1600)
    scene["planning_source"] = "user"
    scene["planning_confidence"] = 1.0
    scene["locked_by_user"] = True
    _link_scene_states(current["scenes"])
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or [])
        + ["scene_plan", "scene_assignment", "dialogue", "prompts", "summary"]
    )
    return normalize_state(current)


def scene_count_floor(state: Mapping[str, Any]) -> int:
    current = _require_content_lock(state)
    adapter = _adapter(current["parent_product"])
    floor = int(adapter["minimum_scene_count"])
    metadata = dict(current["source"].get("metadata") or {})
    if current["parent_product"] == "storyboard_prompt":
        floor = max(floor, _integer(metadata.get("detected_panel_count"), 0))
    elif current["parent_product"] == "frame_video_local":
        floor = max(floor, len(current["source"].get("assets") or []))
    if floor > int(adapter["maximum_scene_count"]):
        raise ValueError("source_scene_limit_exceeded")
    return floor


def confirm_scene_count(state: Mapping[str, Any], count: int) -> dict[str, Any]:
    current = _require_content_lock(state)
    adapter = _adapter(current["parent_product"])
    target = _integer(count, 0)
    if not int(adapter["minimum_scene_count"]) <= target <= int(adapter["maximum_scene_count"]):
        raise ValueError("scene_count_out_of_range")
    if target < scene_count_floor(current):
        raise ValueError("scene_content_reconcile_required")
    existing_scenes = [deepcopy(item) for item in current["scenes"]]
    if target < len(existing_scenes):
        # Reduction is positional in the user's current order, never ordinal by ID.
        removed_scenes = existing_scenes[target:]
        removed_ids = {str(item.get("scene_id") or "") for item in removed_scenes}
        protected_scene_fields = (
            "scene_role", "goal", "semantic_beat", "start_state", "main_action",
            "completion_state", "original_scene_intent", "reference_asset_ids",
            "product_ids", "prop_ids", "dialogue_segment_ids", "narrator_enabled",
            "wardrobe_overrides", "camera", "framing", "movement", "lighting",
            "mood", "transition_in", "transition_out", "sfx_ids", "ambient_id",
        )
        has_user_scene_content = any(
            str(scene.get("assignment_source") or "") == "user"
            or any(bool(scene.get(field)) for field in protected_scene_fields)
            for scene in removed_scenes
        )
        has_dialogue = any(str(item.get("scene_id") or "") in removed_ids for item in current["audio"]["dialogue_segments"])
        has_music = any(scene_id in current["audio"]["music_plan"] for scene_id in removed_ids)
        has_effects = any(
            str(item.get("scene_id") or "") in removed_ids
            for item in current["audio"]["sfx_plan"] + current["audio"]["ambient_plan"]
        )
        has_reference_scope = any(
            removed_ids.intersection(item.get("allowed_scene_ids") or [])
            for item in current["references"]
        )
        if has_user_scene_content or has_dialogue or has_music or has_effects or has_reference_scope:
            raise ValueError("scene_content_reconcile_required")
    seconds = max(
        1,
        _integer(current["format"].get("seconds_per_scene"), int(adapter["seconds_per_scene"])),
    )
    ratio = str(current["format"].get("ratio") or "9:16")
    scenes = [deepcopy(item) for item in existing_scenes[:target]]
    while len(scenes) < target:
        scene_id = _allocate_id(current, "scene", [item.get("scene_id") for item in scenes])
        ordinal = _integer(scene_id.rsplit("_", 1)[-1], len(scenes) + 1)
        scene = _scene(ordinal, seconds=seconds, ratio=ratio)
        scene["scene_id"] = scene_id
        scenes.append(scene)
    product_first_uniform_duration = (
        current["parent_product"] == "video_ai_real"
        and current["entry_mode"] in VIDEO_AI_REAL_PRODUCT_FIRST_MODES
    )
    for index, scene in enumerate(scenes, 1):
        scene["scene_index"] = index
        scene["duration_target"] = (
            seconds
            if product_first_uniform_duration
            else max(1, _integer(scene.get("duration_target"), seconds))
        )
        scene["ratio"] = ratio
    _link_scene_states(scenes)
    removed_ids = {str(item.get("scene_id") or "") for item in existing_scenes[target:]}
    if removed_ids:
        current["audio"]["dialogue_segments"] = [
            item for item in current["audio"]["dialogue_segments"]
            if str(item.get("scene_id") or "") not in removed_ids
        ]
        current["audio"]["music_plan"] = {
            key: value for key, value in current["audio"]["music_plan"].items()
            if key not in removed_ids
        }
        current["audio"]["sfx_plan"] = [
            item for item in current["audio"]["sfx_plan"]
            if str(item.get("scene_id") or "") not in removed_ids
        ]
        current["audio"]["ambient_plan"] = [
            item for item in current["audio"]["ambient_plan"]
            if str(item.get("scene_id") or "") not in removed_ids
        ]
        for reference in current["references"]:
            reference["allowed_scene_ids"] = [
                scene_id for scene_id in reference.get("allowed_scene_ids") or []
                if str(scene_id) not in removed_ids
            ]
    current["format"].update({"scene_count": target, "scene_count_confirmed": True})
    current["scenes"] = scenes
    current["navigation"]["current_step"] = "scene_plan"
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or []) + ["scene_plan", "scene_assignment", "dialogue", "prompts", "summary"]
    )
    return normalize_state(current)


def reorder_scenes(state: Mapping[str, Any], ordered_scene_ids: Iterable[str]) -> dict[str, Any]:
    current = normalize_state(state)
    requested = [_text(item, 80) for item in ordered_scene_ids]
    existing_ids = [str(item.get("scene_id") or "") for item in current["scenes"]]
    if len(requested) != len(existing_ids) or len(set(requested)) != len(requested) or set(requested) != set(existing_ids):
        raise ValueError("scene_order_invalid")
    by_id = {str(item.get("scene_id") or ""): dict(item) for item in current["scenes"]}
    scenes = [by_id[scene_id] for scene_id in requested]
    for index, scene in enumerate(scenes):
        scene["scene_index"] = index + 1
    _link_scene_states(scenes)
    current["scenes"] = scenes
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or []) + ["scene_plan", "scene_assignment", "dialogue", "prompts", "summary"]
    )
    return normalize_state(current)


def auto_assign_scenes(state: Mapping[str, Any]) -> dict[str, Any]:
    current = normalize_state(state)
    if current["parent_product"] == "multi_scene_film":
        episode = effective_episode_contract(current)
        characters = list(episode["character_ids"])
        locations = list(episode["location_ids"])
    else:
        characters = [str(item.get("character_id") or "") for item in current["bible"]["characters"] if item.get("character_id")]
        locations = [str(item.get("location_id") or "") for item in current["bible"]["locations"] if item.get("location_id")]
    for index, scene in enumerate(current["scenes"]):
        if str(scene.get("assignment_source") or "") == "user":
            continue
        scene["character_ids"] = [characters[index % len(characters)]] if characters else []
        scene["location_id"] = locations[index % len(locations)] if locations else ""
        scene["assignment_source"] = "auto_round_robin"
        scene["assignment_confidence"] = 1.0
    current["navigation"]["current_step"] = "scene_assignment"
    return normalize_state(current)


def assign_scene(
    state: Mapping[str, Any],
    scene_id: str,
    *,
    character_ids: Iterable[str] | None = None,
    location_id: str | None = None,
    product_ids: Iterable[str] | None = None,
    prop_ids: Iterable[str] | None = None,
    narrator_enabled: bool | None = None,
    sfx_ids: Iterable[str] | None = None,
    ambient_id: str | None = None,
) -> dict[str, Any]:
    current = normalize_state(state)
    target = _text(scene_id, 80)
    scene = next((item for item in current["scenes"] if str(item.get("scene_id") or "") == target), None)
    if not scene:
        raise ValueError("scene_not_found")
    valid_characters = {str(item.get("character_id") or "") for item in current["bible"]["characters"]}
    selected = _dedupe(scene.get("character_ids") or [] if character_ids is None else character_ids)
    if any(item not in valid_characters for item in selected):
        raise ValueError("scene_character_invalid")
    valid_locations = {str(item.get("location_id") or "") for item in current["bible"]["locations"]}
    selected_location = str(scene.get("location_id") or "") if location_id is None else _text(location_id, 80)
    if selected_location and selected_location not in valid_locations:
        raise ValueError("scene_location_invalid")
    valid_products = {str(item.get("product_id") or "") for item in current["bible"].get("products") or []}
    selected_products = _dedupe(scene.get("product_ids") or [] if product_ids is None else product_ids)
    if any(item not in valid_products for item in selected_products):
        raise ValueError("scene_product_invalid")
    valid_props = {str(item.get("prop_id") or "") for item in current["bible"].get("props") or []}
    selected_props = _dedupe(scene.get("prop_ids") or [] if prop_ids is None else prop_ids)
    if any(item not in valid_props for item in selected_props):
        raise ValueError("scene_prop_invalid")
    selected_narrator = bool(scene.get("narrator_enabled")) if narrator_enabled is None else bool(narrator_enabled)
    if selected_narrator and not str((current["bible"].get("narrator") or {}).get("narrator_id") or ""):
        raise ValueError("scene_narrator_invalid")
    selected_sfx = _dedupe(scene.get("sfx_ids") or [] if sfx_ids is None else sfx_ids)
    selected_ambient = _text(scene.get("ambient_id"), 160) if ambient_id is None else _text(ambient_id, 160)
    scene["character_ids"] = selected
    scene["location_id"] = selected_location
    scene["product_ids"] = selected_products
    scene["prop_ids"] = selected_props
    scene["narrator_enabled"] = selected_narrator
    scene["sfx_ids"] = selected_sfx
    scene["ambient_id"] = selected_ambient
    scene["assignment_source"] = "user"
    scene["assignment_confidence"] = 1.0
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or []) + ["scene_assignment", "dialogue", "prompts", "summary"]
    )
    return normalize_state(current)


def set_dialogue(
    state: Mapping[str, Any],
    scene_id: str,
    *,
    speaker_id: str,
    text: str,
    emotion: str = "",
    delivery_style: str = "",
) -> dict[str, Any]:
    current = normalize_state(state)
    target_scene = next((item for item in current["scenes"] if str(item.get("scene_id") or "") == str(scene_id)), None)
    if not target_scene:
        raise ValueError("scene_not_found")
    valid_speakers = {str(item.get("character_id") or "") for item in current["bible"]["characters"]}
    narrator = current["bible"].get("narrator") or {}
    if narrator.get("narrator_id"):
        valid_speakers.add(str(narrator["narrator_id"]))
    speaker = _text(speaker_id, 80)
    if speaker not in valid_speakers:
        raise ValueError("dialogue_speaker_invalid")
    dialogue_text = _text(text, 4000)
    if not dialogue_text:
        raise ValueError("dialogue_text_required")
    dialogue_id = _allocate_id(
        current,
        "dlg",
        [item.get("dialogue_id") for item in current["audio"]["dialogue_segments"]],
    )
    estimated_seconds = max(1, ceil(len(dialogue_text) / 14))
    scene_budget_seconds = max(1, _integer(target_scene.get("duration_target"), 1))
    record = {
        "dialogue_id": dialogue_id,
        "scene_id": str(target_scene["scene_id"]),
        "speaker_id": speaker,
        "text": dialogue_text,
        "order": len(target_scene.get("dialogue_segment_ids") or []) + 1,
        "timing_hint": "",
        "emotion": _text(emotion, 120),
        "delivery_style": _text(delivery_style, 240),
        "estimated_seconds": estimated_seconds,
        "scene_budget_seconds": scene_budget_seconds,
        "budget_warning": estimated_seconds > scene_budget_seconds,
    }
    current["audio"]["dialogue_segments"].append(record)
    target_scene["dialogue_segment_ids"] = _dedupe(list(target_scene.get("dialogue_segment_ids") or []) + [dialogue_id])
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or []) + ["dialogue", "voice_cast", "prompts", "summary"]
    )
    return normalize_state(current)


def remove_dialogue(
    state: Mapping[str, Any],
    dialogue_id: str,
    *,
    scene_id: str,
) -> dict[str, Any]:
    current = normalize_state(state)
    target_id = _text(dialogue_id, 80)
    target_scene_id = _text(scene_id, 80)
    record = next(
        (
            item for item in current["audio"]["dialogue_segments"]
            if str(item.get("dialogue_id") or "") == target_id
        ),
        None,
    )
    if record is None:
        raise ValueError("dialogue_not_found")
    if str(record.get("scene_id") or "") != target_scene_id:
        raise ValueError("dialogue_scene_mismatch")
    scene = next(
        (item for item in current["scenes"] if str(item.get("scene_id") or "") == target_scene_id),
        None,
    )
    if scene is None:
        raise ValueError("scene_not_found")
    current["audio"]["dialogue_segments"] = [
        item for item in current["audio"]["dialogue_segments"]
        if str(item.get("dialogue_id") or "") != target_id
    ]
    scene["dialogue_segment_ids"] = [
        item for item in scene.get("dialogue_segment_ids") or []
        if str(item) != target_id
    ]
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or [])
        + ["dialogue", "voice_cast", "prompts", "summary"]
    )
    return normalize_state(current)


def update_scene_direction(
    state: Mapping[str, Any],
    scene_id: str,
    *,
    framing: str = "",
    movement: str = "",
    lighting: str = "",
    mood: str = "",
    camera: str = "",
) -> dict[str, Any]:
    """Persist the compact scene-direction editor without compiling a prompt."""

    current = normalize_state(state)
    target = _text(scene_id, 80)
    scene = next((item for item in current["scenes"] if str(item.get("scene_id") or "") == target), None)
    if not scene:
        raise ValueError("scene_not_found")
    for field, value in {
        "camera": camera,
        "framing": framing,
        "movement": movement,
        "lighting": lighting,
        "mood": mood,
    }.items():
        if value is not None:
            scene[field] = _text(value, 800 if field == "camera" else 240)
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or []) + ["prompts", "summary"]
    )
    return normalize_state(current)


def auto_assign_voices(state: Mapping[str, Any], inventory: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    current = normalize_state(state)
    voices = [dict(item) for item in inventory if isinstance(item, Mapping) and item.get("voice_id") and item.get("server_renderable")]
    used: set[str] = set()
    voice_cast: dict[str, dict[str, Any]] = {}
    for character in current["bible"]["characters"]:
        character_id = str(character.get("character_id") or "")
        gender = str(character.get("gender") or "unspecified")
        selected = next(
            (
                item for item in voices
                if str(item.get("voice_id") or "") not in used
                and (gender == "unspecified" or str(item.get("gender") or "unspecified") == gender)
            ),
            None,
        )
        if not selected:
            raise ValueError("distinct_server_voice_required")
        voice_id = str(selected["voice_id"])
        used.add(voice_id)
        character["voice_id"] = voice_id
        voice_cast[character_id] = {
            "voice_id": voice_id,
            "gender": str(selected.get("gender") or gender),
            "server_renderable": True,
            "source": _text(selected.get("source") or "verified_inventory", 80),
        }
    narrator = dict(current["bible"].get("narrator") or {})
    narrator_id = str(narrator.get("narrator_id") or "")
    if narrator_id:
        narrator_gender = str(narrator.get("gender") or "unspecified")
        preferred_voice_id = str(narrator.get("voice_id") or "")
        selected = next(
            (
                item for item in voices
                if str(item.get("voice_id") or "") == preferred_voice_id
                and preferred_voice_id not in used
            ),
            None,
        ) or next(
            (
                item for item in voices
                if str(item.get("voice_id") or "") not in used
                and (
                    narrator_gender == "unspecified"
                    or str(item.get("gender") or "unspecified") == narrator_gender
                )
            ),
            None,
        )
        if not selected:
            raise ValueError("distinct_server_voice_required")
        voice_id = str(selected["voice_id"])
        used.add(voice_id)
        narrator["voice_id"] = voice_id
        current["bible"]["narrator"] = narrator
        voice_cast[narrator_id] = {
            "voice_id": voice_id,
            "gender": str(selected.get("gender") or narrator_gender),
            "server_renderable": True,
            "source": _text(selected.get("source") or "verified_inventory", 80),
        }
    current["audio"]["voice_cast"] = voice_cast
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or []) + ["voice_cast", "audio", "summary"]
    )
    return normalize_state(current)


def set_music_scope(state: Mapping[str, Any], scope: str) -> dict[str, Any]:
    current = normalize_state(state)
    value = _text(scope, 40)
    if value not in MUSIC_SCOPES:
        raise ValueError("music_scope_invalid")
    current["audio"]["music_scope"] = value
    current["audio"]["music_plan"] = {}
    for scene in current["scenes"]:
        scene["music_policy"] = "off" if value == "none" else "inherit"
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or []) + ["audio", "prompts", "summary"]
    )
    return normalize_state(current)


def set_whole_video_music(
    state: Mapping[str, Any],
    *,
    track_id: str,
    volume: int = 20,
    start_offset: float = 0,
    fade_in: float = 0.25,
    fade_out: float = 0.25,
    ducking: bool = True,
) -> dict[str, Any]:
    current = normalize_state(state)
    if current["audio"]["music_scope"] != "whole_video":
        raise ValueError("whole_video_music_scope_required")
    track = _text(track_id, 240)
    if not track:
        raise ValueError("music_track_required")
    current["audio"]["music_plan"] = {
        "track_id": track,
        "volume": max(0, min(200, _integer(volume, 20))),
        "start_offset": max(0.0, _number(start_offset, 0.0)),
        "fade_in": max(0.0, _number(fade_in, 0.25)),
        "fade_out": max(0.0, _number(fade_out, 0.25)),
        "ducking": bool(ducking),
    }
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or []) + ["audio", "prompts", "summary"]
    )
    return normalize_state(current)


def set_scene_music(
    state: Mapping[str, Any],
    scene_id: str,
    *,
    policy: str,
    track_id: str = "",
    volume: int = 20,
) -> dict[str, Any]:
    current = normalize_state(state)
    if current["audio"]["music_scope"] != "per_scene":
        raise ValueError("per_scene_music_scope_required")
    target = _text(scene_id, 80)
    if not any(str(item.get("scene_id") or "") == target for item in current["scenes"]):
        raise ValueError("scene_not_found")
    mode = _text(policy, 40)
    if mode not in MUSIC_SCENE_POLICIES:
        raise ValueError("scene_music_policy_invalid")
    track = _text(track_id, 240)
    if mode == "track" and not track:
        raise ValueError("music_track_required")
    current["audio"]["music_plan"][target] = {
        "policy": mode,
        "track_id": track if mode == "track" else "",
        "volume": max(0, min(200, _integer(volume, 20))),
        "ducking": True,
        "fade": True,
    }
    for scene in current["scenes"]:
        if str(scene.get("scene_id") or "") == target:
            scene["music_policy"] = mode
            break
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or []) + ["audio", "prompts", "summary"]
    )
    return normalize_state(current)


def set_continuity(state: Mapping[str, Any], key: str, enabled: bool) -> dict[str, Any]:
    current = _require_content_lock(state)
    target = _text(key, 40)
    if target not in DEFAULT_CONTINUITY:
        raise ValueError("continuity_key_invalid")
    current["bible"]["continuity"][target] = bool(enabled)
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or []) + ["continuity", "prompts", "summary"]
    )
    return normalize_state(current)


def scene_assignment_model(state: Mapping[str, Any], scene_id: str) -> dict[str, Any]:
    current = normalize_state(state)
    target = next((item for item in current["scenes"] if str(item.get("scene_id") or "") == str(scene_id)), None)
    if not target:
        raise ValueError("scene_not_found")
    character_ids = set(target.get("character_ids") or [])
    characters = []
    for item in current["bible"]["characters"]:
        character_id = str(item.get("character_id") or "")
        if character_id not in character_ids:
            continue
        row = deepcopy(item)
        row["voice"] = deepcopy(current["audio"]["voice_cast"].get(character_id) or {})
        characters.append(row)
    product_ids = set(target.get("product_ids") or [])
    products = [
        deepcopy(item) for item in current["bible"].get("products") or []
        if str(item.get("product_id") or "") in product_ids
    ]
    prop_ids = set(target.get("prop_ids") or [])
    props = [
        deepcopy(item) for item in current["bible"].get("props") or []
        if str(item.get("prop_id") or "") in prop_ids
    ]
    narrator_id = str((current["bible"].get("narrator") or {}).get("narrator_id") or "")
    dialogue_ids = set(target.get("dialogue_segment_ids") or [])
    dialogue = [deepcopy(item) for item in current["audio"]["dialogue_segments"] if str(item.get("dialogue_id") or "") in dialogue_ids]
    if current["audio"]["music_scope"] == "per_scene":
        raw_music = dict(current["audio"]["music_plan"].get(str(target["scene_id"])) or {"policy": "inherit", "track_id": ""})
        music = {"policy": str(raw_music.get("policy") or "inherit"), "track_id": str(raw_music.get("track_id") or "")}
    elif current["audio"]["music_scope"] == "whole_video":
        music = {"policy": "inherit", "track_id": str(current["audio"]["music_plan"].get("track_id") or "")}
    else:
        music = {"policy": "off", "track_id": ""}
    return {
        "scene_id": str(target["scene_id"]),
        "scene_index": int(target.get("scene_index") or 0),
        "characters": characters,
        "narrator": {"enabled": bool(target.get("narrator_enabled")), "narrator_id": narrator_id},
        "products": products,
        "props": props,
        "location_id": str(target.get("location_id") or ""),
        "dialogue": dialogue,
        "music": music,
        "sfx_ids": _dedupe(target.get("sfx_ids") or []),
        "ambient_id": _text(target.get("ambient_id"), 160),
        "advanced_collapsed": True,
    }


def public_controls(state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    current = normalize_state(state)
    dialogue_speakers = {
        str(item.get("speaker_id") or "")
        for item in current["audio"]["dialogue_segments"]
        if str(item.get("speaker_id") or "")
    }
    planned_voice_owners = dialogue_speakers | {
        str(key) for key in current["audio"]["voice_cast"] if str(key)
    }
    planned_multi_voice = len(planned_voice_owners) > 1
    planned_per_scene = current["audio"]["music_scope"] == "per_scene"
    planned_sfx = bool(current["audio"]["sfx_plan"]) or any(scene.get("sfx_ids") for scene in current["scenes"])
    planned_ambient = bool(current["audio"]["ambient_plan"]) or any(scene.get("ambient_id") for scene in current["scenes"])

    def control(key: str, planned: bool) -> dict[str, Any]:
        supported = bool(current["capabilities"].get(key))
        return {
            "supported": supported,
            "planned": bool(planned),
            "hidden_reason": "" if supported else "renderer_not_connected",
        }

    return {
        "multi_voice_render": control("multi_voice_render", planned_multi_voice),
        "whole_video_music": control("whole_video_music", current["audio"]["music_scope"] == "whole_video"),
        "per_scene_music": control("per_scene_music", planned_per_scene),
        "scene_sfx": control("scene_sfx", planned_sfx),
        "scene_ambient": control("scene_ambient", planned_ambient),
    }


def readiness_errors(state: Mapping[str, Any]) -> list[str]:
    current = normalize_state(state)
    errors: list[str] = []
    needs = current["needs"]
    product = current["parent_product"]
    source = current["source"]
    source_assets = list(source.get("assets") or [])
    if product in {"video_trend", "script_image_video"} and not source.get("complete"):
        errors.append("source_content_required")
    elif product == "frame_video_local" and len(source_assets) < 2:
        errors.append("frame_images_required")
    elif product == "storyboard_prompt" and source.get("required") and len(source_assets) < 2:
        errors.append("storyboard_images_required")
    elif product == "self_shot_scene_change" and not source_assets:
        errors.append("source_video_required")
    elif source.get("required") and not source.get("complete"):
        errors.append("source_required")
    if current["parent_product"] == "multi_scene_film":
        if not _text(current["series"].get("goal"), 4000):
            errors.append("series_goal_required")
        if (
            _integer(current["episode"].get("number"), 0) <= 0
            or not _text(current["episode"].get("title"), 500)
        ):
            errors.append("episode_identity_required")
        if not bool((current["episode"].get("content") or {}).get("locked")):
            errors.append("episode_content_not_locked")
        if not current["scenes"]:
            errors.append("scene_plan_missing")
        return errors
    if not current["content"].get("locked"):
        errors.append("content_not_locked")
    if needs.get("characters") not in {"SKIP", "UNSUPPORTED"} and not current["bible"].get("character_count_confirmed"):
        errors.append("character_count_unconfirmed")
    if needs.get("locations") not in {"SKIP", "UNSUPPORTED"} and not current["bible"].get("location_count_confirmed"):
        errors.append("location_count_unconfirmed")
    if needs.get("characters") == "REQUIRED" and not current["bible"]["characters"]:
        errors.append("characters_required")
    if needs.get("locations") == "REQUIRED" and not current["bible"]["locations"]:
        errors.append("locations_required")
    narrator = dict(current["bible"].get("narrator") or {})
    narrator_id = str(narrator.get("narrator_id") or "")
    if needs.get("narrator") == "REQUIRED" and not narrator_id:
        errors.append("narrator_required")
    products = list(current["bible"].get("products") or [])
    product_ids_available = {str(item.get("product_id") or "") for item in products}
    if needs.get("product") == "REQUIRED" and not products:
        errors.append("products_required")
    prop_ids_available = {str(item.get("prop_id") or "") for item in current["bible"].get("props") or []}
    if not current["format"].get("scene_count_confirmed") or not current["scenes"]:
        errors.append("scene_plan_missing")
    character_id_order = [str(item.get("character_id") or "") for item in current["bible"]["characters"]]
    character_ids = set(character_id_order)
    location_ids = {str(item.get("location_id") or "") for item in current["bible"]["locations"]}
    reference_ids = {str(item.get("asset_id") or "") for item in current["references"]}
    references_required = needs.get("reference_assets") == "REQUIRED"
    if references_required and not reference_ids:
        errors.append("reference_assets_required")
    for character in current["bible"]["characters"]:
        character_id = str(character.get("character_id") or "")
        if str(character.get("gender") or "unspecified") == "unspecified":
            errors.append(f"{character_id}_gender_missing")
        if not str(character.get("description") or "").strip():
            errors.append(f"{character_id}_description_missing")
        if references_required and not reference_ids.intersection(character.get("reference_asset_ids") or []):
            errors.append(f"{character_id}_reference_missing")
    for location in current["bible"]["locations"]:
        location_id = str(location.get("location_id") or "")
        if not str(location.get("description") or "").strip():
            errors.append(f"{location_id}_description_missing")
        if references_required and not reference_ids.intersection(location.get("reference_asset_ids") or []):
            errors.append(f"{location_id}_reference_missing")
    for product in products:
        product_id = str(product.get("product_id") or "")
        if references_required and not reference_ids.intersection(product.get("reference_asset_ids") or []):
            errors.append(f"{product_id}_reference_missing")
    for prop in current["bible"].get("props") or []:
        prop_id = str(prop.get("prop_id") or "")
        if references_required and not reference_ids.intersection(prop.get("reference_asset_ids") or []):
            errors.append(f"{prop_id}_reference_missing")
    for scene in current["scenes"]:
        scene_id = str(scene.get("scene_id") or "")
        for field in ("semantic_beat", "main_action", "completion_state"):
            if needs.get("scene_planning") not in {"SKIP", "UNSUPPORTED"} and not str(scene.get(field) or "").strip():
                errors.append(f"{scene_id}_{field}_missing")
        if any(item not in character_ids for item in scene.get("character_ids") or []):
            errors.append(f"{scene.get('scene_id')}_character_invalid")
        if scene.get("location_id") and str(scene.get("location_id")) not in location_ids:
            errors.append(f"{scene.get('scene_id')}_location_invalid")
        if any(item not in product_ids_available for item in scene.get("product_ids") or []):
            errors.append(f"{scene_id}_product_invalid")
        if any(item not in prop_ids_available for item in scene.get("prop_ids") or []):
            errors.append(f"{scene_id}_prop_invalid")
        if scene.get("narrator_enabled") and not narrator_id:
            errors.append(f"{scene_id}_narrator_invalid")
        if needs.get("locations") == "REQUIRED" and not str(scene.get("location_id") or ""):
            errors.append(f"{scene.get('scene_id')}_location_missing")
    dialogue_segments = current["audio"]["dialogue_segments"]
    if needs.get("product") == "REQUIRED" and current["scenes"] and not any(
        scene.get("product_ids") for scene in current["scenes"]
    ):
        errors.append("product_scene_assignment_required")
    narrator_used = any(scene.get("narrator_enabled") for scene in current["scenes"]) or any(
        str(item.get("speaker_id") or "") == narrator_id for item in dialogue_segments
    )
    if needs.get("narrator") == "REQUIRED" and narrator_id and not narrator_used:
        errors.append("narrator_scene_assignment_required")
    if needs.get("dialogue") == "REQUIRED" and not dialogue_segments:
        errors.append("dialogue_required")
    scene_cast = {
        str(scene.get("scene_id") or ""): set(scene.get("character_ids") or [])
        for scene in current["scenes"]
    }
    for item in dialogue_segments:
        speaker_id = str(item.get("speaker_id") or "")
        if speaker_id not in character_ids and speaker_id != narrator_id:
            errors.append(f"{item.get('dialogue_id')}_speaker_invalid")
        elif speaker_id != narrator_id and speaker_id not in scene_cast.get(str(item.get("scene_id") or ""), set()):
            errors.append(f"{item.get('dialogue_id')}_speaker_not_in_scene")
    dialogue_speakers = list(dict.fromkeys(
        str(item.get("speaker_id") or "")
        for item in dialogue_segments
        if str(item.get("speaker_id") or "")
    ))
    voice_owners = list(dialogue_speakers)
    if needs.get("voice") == "REQUIRED":
        voice_owners = _dedupe([*character_id_order, narrator_id, *voice_owners])
    selected_voice_ids: list[str] = []
    for speaker_id in voice_owners:
        voice = dict(current["audio"]["voice_cast"].get(speaker_id) or {})
        voice_id = str(voice.get("voice_id") or "")
        if not voice_id:
            errors.append(f"{speaker_id}_voice_missing")
            continue
        selected_voice_ids.append(voice_id)
        if not voice.get("server_renderable"):
            errors.append(f"{speaker_id}_voice_not_server_renderable")
    if len(selected_voice_ids) != len(set(selected_voice_ids)):
        errors.append("voice_cast_not_distinct")
    controls = public_controls(current)
    if controls["multi_voice_render"]["planned"] and not controls["multi_voice_render"]["supported"]:
        errors.append("multi_voice_renderer_missing")
    if controls["whole_video_music"]["planned"] and not controls["whole_video_music"]["supported"]:
        errors.append("whole_video_music_renderer_missing")
    if controls["per_scene_music"]["planned"] and not controls["per_scene_music"]["supported"]:
        errors.append("per_scene_music_renderer_missing")
    if controls["scene_sfx"]["planned"] and not controls["scene_sfx"]["supported"]:
        errors.append("scene_sfx_renderer_missing")
    if controls["scene_ambient"]["planned"] and not controls["scene_ambient"]["supported"]:
        errors.append("scene_ambient_renderer_missing")
    if needs.get("music") == "REQUIRED":
        music_scope = str(current["audio"].get("music_scope") or "none")
        music_plan = dict(current["audio"].get("music_plan") or {})
        has_music = bool(music_plan.get("track_id")) if music_scope == "whole_video" else any(
            str(dict(item).get("track_id") or "")
            for item in music_plan.values()
            if isinstance(item, Mapping)
        ) if music_scope == "per_scene" else False
        if not has_music:
            errors.append("music_required")
    if needs.get("sfx") == "REQUIRED" and not (
        current["audio"].get("sfx_plan") or any(scene.get("sfx_ids") for scene in current["scenes"])
    ):
        errors.append("sfx_required")
    if needs.get("ambient") == "REQUIRED" and not (
        current["audio"].get("ambient_plan") or any(scene.get("ambient_id") for scene in current["scenes"])
    ):
        errors.append("ambient_required")
    if needs.get("continuity") == "REQUIRED" and "continuity" not in set(current["navigation"].get("completed_steps") or []):
        errors.append("continuity_required")
    if not bool(_adapter(current["parent_product"])["public_submit_enabled"]):
        errors.append("public_submit_locked")
    dirty = set(current["navigation"].get("dirty_sections") or [])
    for section in ("production_bible", "scene_plan", "dialogue", "prompts"):
        if section in dirty:
            errors.append(f"{section}_reconcile_required")
    return list(dict.fromkeys(errors))


def _is_render_readiness_error(error: str) -> bool:
    value = str(error or "")
    return (
        value == "public_submit_locked"
        or value.endswith("_renderer_missing")
        or value.endswith("_voice_not_server_renderable")
    )


def planning_readiness_errors(state: Mapping[str, Any]) -> list[str]:
    return [
        error for error in readiness_errors(state)
        if not _is_render_readiness_error(error)
    ]


def render_readiness_errors(state: Mapping[str, Any]) -> list[str]:
    return [
        error for error in readiness_errors(state)
        if _is_render_readiness_error(error)
    ]


def next_required_step(state: Mapping[str, Any]) -> str:
    current = normalize_state(state)
    source = current["source"]
    if source.get("required") and not source.get("complete"):
        return "source"
    if current["parent_product"] == "multi_scene_film" and not _text(current["series"].get("goal"), 4000):
        return "series_goal"
    if not current["format"].get("ratio") or not current["format"].get("target_duration_seconds"):
        return "format"
    if not current["content"].get("candidate_ready"):
        return "content_hub"
    if not current["content"].get("locked"):
        return "content_lock"
    completed = set(current["navigation"].get("completed_steps") or [])
    for step in (
        "production_bible",
        "references",
        "continuity",
        "episode",
        "scene_count",
        "scene_plan",
        "scene_assignment",
        "prompts",
        "branding",
        "summary",
    ):
        if step == "scene_count" and current["format"].get("scene_count_confirmed"):
            continue
        if step == "scene_plan" and current["scenes"]:
            continue
        if step == "episode" and current["parent_product"] != "multi_scene_film":
            continue
        if step == "episode" and (
            _text(current["episode"].get("title"), 500)
            and bool((current["episode"].get("content") or {}).get("locked"))
        ):
            continue
        if step not in completed:
            return step
    return "summary"


def navigate(state: Mapping[str, Any], step: str, *, visible: bool = True) -> dict[str, Any]:
    current = normalize_state(state)
    target = _text(step, 80)
    if target not in CANONICAL_VISIBLE_STEPS:
        raise ValueError("video_uiflow3_step_invalid")
    navigation = current["navigation"]
    if not visible:
        navigation["completed_steps"] = _dedupe(list(navigation.get("completed_steps") or []) + [target])
        return normalize_state(current)
    previous = str(navigation.get("current_step") or "entry")
    if previous != target:
        stack = list(navigation.get("visible_step_stack") or [])
        if not stack or stack[-1] != previous:
            stack.append(previous)
        navigation["visible_step_stack"] = stack[-40:]
    navigation["current_step"] = target
    return normalize_state(current)


def back(state: Mapping[str, Any]) -> dict[str, Any]:
    current = normalize_state(state)
    navigation = current["navigation"]
    stack = list(navigation.get("visible_step_stack") or [])
    if stack:
        navigation["current_step"] = stack.pop()
        navigation["visible_step_stack"] = stack
    return normalize_state(current)


def resume_step(state: Mapping[str, Any]) -> str:
    return str(normalize_state(state)["navigation"]["current_step"])


def begin_summary_edit(state: Mapping[str, Any], step: str) -> dict[str, Any]:
    current = normalize_state(state)
    if str(current["navigation"].get("current_step") or "") != "summary":
        raise ValueError("summary_edit_requires_summary")
    target = _text(step, 80)
    if target not in SUMMARY_EDIT_STEPS:
        raise ValueError("summary_edit_target_invalid")
    current["navigation"]["return_to"] = "summary"
    return navigate(current, target)


def finish_editor(state: Mapping[str, Any]) -> dict[str, Any]:
    current = normalize_state(state)
    target = str(current["navigation"].get("return_to") or "")
    if not target:
        return current
    stack = list(current["navigation"].get("visible_step_stack") or [])
    if target in stack:
        last_target = len(stack) - 1 - stack[::-1].index(target)
        stack = stack[:last_target]
    current["navigation"]["visible_step_stack"] = stack
    current["navigation"]["current_step"] = target
    current["navigation"]["return_to"] = None
    return normalize_state(current)


def mark_sections_complete(state: Mapping[str, Any], *sections: str) -> dict[str, Any]:
    current = normalize_state(state)
    valid = [str(item) for item in sections if str(item) in CANONICAL_VISIBLE_STEPS]
    current["navigation"]["completed_steps"] = _dedupe(list(current["navigation"].get("completed_steps") or []) + valid)
    resolved = set(valid)
    if "content_lock" in resolved:
        resolved.add("needs")
    if "scene_assignment" in resolved:
        resolved.add("dialogue")
    current["navigation"]["dirty_sections"] = [
        item for item in current["navigation"].get("dirty_sections") or [] if item not in resolved
    ]
    return normalize_state(current)


def claim_callback(state: Mapping[str, Any], callback_query_id: str) -> tuple[dict[str, Any], bool]:
    current = normalize_state(state)
    token = _text(callback_query_id, 160)
    if not token:
        return current, True
    handled = list(current.get("handled_callback_ids") or [])
    if token in handled:
        return current, False
    handled.append(token)
    current["handled_callback_ids"] = handled[-100:]
    return normalize_state(current), True


def from_legacy_state(
    legacy: Mapping[str, Any] | None,
    *,
    draft_id: str,
) -> dict[str, Any]:
    source = deepcopy(dict(legacy or {}))
    product = _text(source.get("source_product_id") or source.get("product_type"), 80)
    if product not in ENTRY_ADAPTERS:
        raise ValueError("unsupported_video_uiflow3_product")
    current = new_state(product, draft_id=draft_id)
    current["source"]["complete"] = True
    ratio = _text(source.get("aspect_ratio") or source.get("ratio"), 20)
    if ratio in SUPPORTED_RATIOS:
        current["format"]["ratio"] = ratio
    current["format"]["target_duration_seconds"] = max(1, _integer(source.get("estimated_duration") or 8, 8))
    character = dict(source.get("character_config") or {})
    if character and str(character.get("mode") or "") != "none":
        item = _character(1)
        item.update({
            "display_name": _text(character.get("display_name") or character.get("description") or "Nhan vat 1", 240),
            "description": _text(character.get("description"), 1600),
            "gender": str(character.get("gender") or character.get("mode") or "unspecified") if str(character.get("gender") or character.get("mode") or "") in GENDERS else "unspecified",
        })
        current["bible"]["characters"] = [item]
        current["bible"]["character_count_confirmed"] = True
    post = dict(source.get("postproduction_addons") or {})
    dubbing = dict(post.get("dubbing") or {})
    dubbing_value = dict(dubbing.get("value") or {}) if isinstance(dubbing.get("value"), Mapping) else {}
    if dubbing.get("enabled") and current["bible"]["characters"]:
        voice_id = _text(dubbing_value.get("voice_id") or dubbing_value.get("voice_choice"), 240)
        if voice_id:
            current["bible"]["characters"][0]["voice_id"] = voice_id
            current["audio"]["voice_cast"]["char_01"] = {
                "voice_id": voice_id,
                "gender": current["bible"]["characters"][0]["gender"],
                "server_renderable": False,
                "source": "legacy_unverified",
            }
    music = dict(post.get("music") or {})
    if music.get("enabled"):
        value = dict(music.get("value") or {}) if isinstance(music.get("value"), Mapping) else {}
        current["audio"]["music_scope"] = "whole_video"
        current["audio"]["music_plan"] = {
            "track_id": _text(value.get("track_id") or value.get("music_request") or "legacy_music", 240),
            "volume": max(0, min(200, _integer(value.get("volume_percent"), 20))),
        }
    for raw_asset in (source.get("reference_assets") or {}).get("items") or []:
        if not isinstance(raw_asset, Mapping):
            continue
        file_id = _text(raw_asset.get("file_id") or raw_asset.get("result_url"), 512)
        if not file_id:
            continue
        current["references"].append({
            "asset_id": _allocate_id(
                current,
                "asset",
                [item.get("asset_id") for item in current["references"]],
            ),
            "asset_type": _text(raw_asset.get("type") or "image", 80),
            "owner_type": "legacy_unassigned",
            "owner_id": "",
            "role": "legacy_unassigned",
            "angle": "",
            "priority": 0,
            "fingerprint": _text(raw_asset.get("fingerprint"), 256) or f"legacy:{file_id}",
            "source": "legacy",
            "telegram_file_id": file_id,
            "allowed_scene_ids": [],
            "metadata": deepcopy(dict(raw_asset)),
        })
    current["legacy_compat"] = {
        "migrated": True,
        "source_schema": _integer(source.get("flow_schema_version"), 0),
        "source_step": _text(source.get("step") or source.get("current_step"), 120),
    }
    return normalize_state(current)


def approved_snapshot(state: Mapping[str, Any]) -> dict[str, Any]:
    current = normalize_state(state)
    errors = readiness_errors(current)
    blocking = [item for item in errors if not _is_render_readiness_error(item)]
    render_blockers = [item for item in errors if _is_render_readiness_error(item)]
    if blocking:
        raise ValueError("approved_snapshot_not_ready:" + ",".join(blocking))
    payload = {
        "draft_id": current["draft_id"],
        "flow_schema_version": FLOW_SCHEMA_VERSION,
        "parent_product": current["parent_product"],
        "entry_mode": current["entry_mode"],
        "render_family": current["render_family"],
        "source": deepcopy(current["source"]),
        "format": deepcopy(current["format"]),
        "content": deepcopy(current["content"]),
        "series": deepcopy(current["series"]),
        "episode": deepcopy(current["episode"]),
        "effective_episode": (
            effective_episode_contract(current)
            if current["parent_product"] == "multi_scene_film"
            else None
        ),
        "production_bible": deepcopy(current["bible"]),
        "creative_controls": deepcopy(current.get("creative_controls") or {}),
        "preservation_requirements": deepcopy(
            current.get("preservation_requirements") or {}
        ),
        "references": deepcopy(current["references"]),
        "scenes": deepcopy(current["scenes"]),
        "audio": deepcopy(current["audio"]),
        "branding": deepcopy(current["branding"]),
        "capability_requirements": [
            key for key, item in public_controls(current).items() if item["planned"]
        ],
        "render_blockers": render_blockers,
        "side_effects": deepcopy(current["side_effects"]),
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload["config_hash"] = sha256(encoded).hexdigest()
    return payload


def callback(action: str, *parts: Any) -> str:
    tokens = ["vid3", _text(action, 24)] + [_text(item, 32) for item in parts]
    if not tokens[1] or any(not item or "|" in item for item in tokens[1:]):
        raise ValueError("video_uiflow3_callback_invalid")
    value = "|".join(tokens)
    if len(value.encode("utf-8")) > 64:
        raise ValueError("video_uiflow3_callback_too_long")
    return value


def draft_token(state: Mapping[str, Any]) -> str:
    current = normalize_state(state)
    draft_id = _text(current.get("draft_id"), 120)
    if not draft_id:
        raise ValueError("video_uiflow3_draft_id_required")
    return sha256(draft_id.encode("utf-8")).hexdigest()[:8]


def scope_callback(state: Mapping[str, Any], value: str) -> str:
    raw = str(value or "")
    parts = raw.split("|")
    if len(parts) < 2 or parts[0] != "vid3" or parts[1] in {"entry", "resume", "d"}:
        return raw
    scoped = "|".join(("vid3", "d", draft_token(state), *parts[1:]))
    if len(scoped.encode("utf-8")) > 64:
        raise ValueError("video_uiflow3_callback_too_long")
    return scoped
