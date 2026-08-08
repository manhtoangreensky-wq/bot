"""Provider-neutral content-first state for the public Video creation UI.

This module owns planning state only. It never calls a provider, creates a job,
writes a database row, mutates a wallet, or executes a renderer.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from math import ceil
from typing import Any, Iterable, Mapping
from uuid import uuid4


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
        "minimum_scene_count": 2,
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
        "seconds_per_scene": 600,
        "minimum_scene_count": 1,
        "maximum_scene_count": 12,
        "public_submit_enabled": False,
    },
}


CANONICAL_VISIBLE_STEPS = (
    "entry",
    "source",
    "format",
    "content_hub",
    "content_lock",
    "production_bible",
    "references",
    "continuity",
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


def _dedupe(values: Iterable[Any]) -> list[str]:
    return list(dict.fromkeys(_text(value, 120) for value in values if _text(value, 120)))


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
        "assignment_source": "unassigned",
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
        "needs": {},
        "bible": {
            "characters": [],
            "narrator": None,
            "products": [],
            "locations": [],
            "props": [],
            "relationships": [],
            "continuity": {},
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
        product = "video_ai_real"
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
        "scene_count_policy": "auto",
        "scene_count": 0,
        "scene_count_confirmed": False,
        **dict(raw.get("format") or {}),
    }
    if str(format_state.get("ratio") or "") not in SUPPORTED_RATIOS:
        format_state["ratio"] = ""
    format_state["target_duration_seconds"] = max(0, _integer(format_state.get("target_duration_seconds"), 0))
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

    raw["needs"] = {
        _text(key, 80): str(value).upper()
        for key, value in dict(raw.get("needs") or {}).items()
        if _text(key, 80) and str(value).upper() in NEED_VALUES
    }
    bible = {
        "characters": [],
        "narrator": None,
        "products": [],
        "locations": [],
        "props": [],
        "relationships": [],
        "continuity": {},
        **dict(raw.get("bible") or {}),
    }
    bible["characters"] = [dict(item) for item in bible.get("characters") or [] if isinstance(item, Mapping)][:MAX_CHARACTERS]
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
    bible["products"] = [dict(item) for item in bible.get("products") or [] if isinstance(item, Mapping)][:20]
    bible["props"] = [dict(item) for item in bible.get("props") or [] if isinstance(item, Mapping)][:40]
    bible["relationships"] = [dict(item) for item in bible.get("relationships") or [] if isinstance(item, Mapping)][:80]
    bible["narrator"] = dict(bible["narrator"]) if isinstance(bible.get("narrator"), Mapping) else None
    bible["continuity"] = dict(bible.get("continuity") or {})
    raw["bible"] = bible
    raw["references"] = [dict(item) for item in raw.get("references") or [] if isinstance(item, Mapping)][:200]
    raw["scenes"] = [dict(item) for item in raw.get("scenes") or [] if isinstance(item, Mapping)][: int(adapter["maximum_scene_count"])]

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
    navigation["visible_step_stack"] = [item for item in _dedupe(navigation.get("visible_step_stack") or []) if item in CANONICAL_VISIBLE_STEPS][-40:]
    navigation["completed_steps"] = [item for item in _dedupe(navigation.get("completed_steps") or []) if item in CANONICAL_VISIBLE_STEPS]
    navigation["return_to"] = _text(navigation.get("return_to"), 80) or None
    navigation["dirty_sections"] = _dedupe(navigation.get("dirty_sections") or [])
    raw["navigation"] = navigation
    raw["legacy_compat"] = dict(raw.get("legacy_compat") or {})
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
        current["source"]["required"] = selected == "storyboard_upload"
        current["source"]["kind"] = "storyboard_panels" if selected == "storyboard_upload" else "generated_storyboard"
    current["source"]["complete"] = bool(current["source"].get("assets")) if current["source"]["required"] else True
    current["entry_mode"] = selected
    current["navigation"]["current_step"] = "source" if current["source"]["required"] else "format"
    return normalize_state(current)


def set_source_metadata(state: Mapping[str, Any], **metadata: Any) -> dict[str, Any]:
    current = normalize_state(state)
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
    asset_id = _stable_id("source", len(assets) + 1)
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
    current["navigation"]["current_step"] = "format"
    return normalize_state(current)


def set_format(
    state: Mapping[str, Any],
    *,
    ratio: str | None = None,
    target_duration_seconds: int | None = None,
) -> dict[str, Any]:
    current = normalize_state(state)
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
    if current["format"]["ratio"] and current["format"]["target_duration_seconds"]:
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
    if not current["content"].get("locked"):
        raise ValueError("content_lock_required")
    return current


def set_character_count(state: Mapping[str, Any], count: int) -> dict[str, Any]:
    current = _require_content_lock(state)
    target = _integer(count, -1)
    if target < MIN_CHARACTERS or target > MAX_CHARACTERS:
        raise ValueError("character_count_out_of_range")
    existing = list(current["bible"]["characters"])
    if target < len(existing):
        removed = {str(item.get("character_id") or "") for item in existing[target:]}
        referenced = any(str(item.get("owner_type") or "") == "character" and str(item.get("owner_id") or "") in removed for item in current["references"])
        assigned = any(removed.intersection(scene.get("character_ids") or []) for scene in current["scenes"])
        dialogue = any(str(item.get("speaker_id") or "") in removed for item in current["audio"]["dialogue_segments"])
        voices = any(character_id in current["audio"]["voice_cast"] for character_id in removed)
        if referenced or assigned or dialogue or voices:
            raise ValueError("character_reassignment_required")
    roster = [deepcopy(item) for item in existing[:target]]
    for ordinal in range(len(roster) + 1, target + 1):
        roster.append(_character(ordinal))
    current["bible"]["characters"] = roster
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
        if any(str(scene.get("location_id") or "") in removed for scene in current["scenes"]):
            raise ValueError("location_reassignment_required")
        if any(str(item.get("owner_type") or "") == "location" and str(item.get("owner_id") or "") in removed for item in current["references"]):
            raise ValueError("location_reassignment_required")
    locations = [deepcopy(item) for item in existing[:target]]
    for ordinal in range(len(locations) + 1, target + 1):
        locations.append(_location(ordinal))
    current["bible"]["locations"] = locations
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
    identity = _text(fingerprint, 256)
    file_id = _text(telegram_file_id, 512)
    if not identity or not file_id:
        raise ValueError("reference_asset_identity_required")
    if not _owner_exists(current, owner_kind, owner):
        raise ValueError("reference_owner_invalid")
    existing = next((item for item in current["references"] if str(item.get("fingerprint") or "") == identity), None)
    if existing:
        return current
    asset_id = _stable_id("asset", len(current["references"]) + 1)
    record = {
        "asset_id": asset_id,
        "asset_type": _text(asset_type, 80),
        "owner_type": owner_kind,
        "owner_id": owner,
        "role": _text(role, 80),
        "angle": _text(metadata.pop("angle", ""), 80),
        "priority": max(0, _integer(metadata.pop("priority", 0), 0)),
        "fingerprint": identity,
        "source": "telegram",
        "telegram_file_id": file_id,
        "allowed_scene_ids": _dedupe(allowed_scene_ids or []),
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
        duration = max(1, _integer(current["format"].get("target_duration_seconds"), int(adapter["seconds_per_scene"])))
        count = ceil(duration / int(adapter["seconds_per_scene"]))
        source = "duration_and_content"
    count = max(int(adapter["minimum_scene_count"]), min(int(adapter["maximum_scene_count"]), count))
    return {"count": count, "seconds_per_scene": int(adapter["seconds_per_scene"]), "source": source}


def confirm_scene_count(state: Mapping[str, Any], count: int) -> dict[str, Any]:
    current = _require_content_lock(state)
    adapter = _adapter(current["parent_product"])
    target = _integer(count, 0)
    if not int(adapter["minimum_scene_count"]) <= target <= int(adapter["maximum_scene_count"]):
        raise ValueError("scene_count_out_of_range")
    existing = {str(item.get("scene_id") or ""): dict(item) for item in current["scenes"]}
    if target < len(existing):
        removed_scenes = [dict(item) for item in current["scenes"][target:]]
        removed_ids = {str(item.get("scene_id") or "") for item in removed_scenes}
        protected_scene_fields = (
            "semantic_beat", "main_action", "completion_state", "original_scene_intent",
            "reference_asset_ids", "product_ids", "prop_ids", "dialogue_segment_ids",
        )
        has_user_scene_content = any(
            str(scene.get("assignment_source") or "") == "user"
            or any(scene.get(field) not in (None, "", [], {}) for field in protected_scene_fields)
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
    seconds = int(adapter["seconds_per_scene"])
    ratio = str(current["format"].get("ratio") or "9:16")
    scenes = []
    for ordinal in range(1, target + 1):
        scene_id = _stable_id("scene", ordinal)
        scene = _scene(ordinal, seconds=seconds, ratio=ratio)
        scene.update(existing.get(scene_id) or {})
        scene["scene_id"] = scene_id
        scene["scene_index"] = ordinal
        scene["duration_target"] = max(1, _integer(scene.get("duration_target"), seconds))
        scene["ratio"] = ratio
        scenes.append(scene)
    for index, scene in enumerate(scenes):
        scene["continuity_from_scene_id"] = scenes[index - 1]["scene_id"] if index > 0 else ""
        scene["continuity_to_scene_id"] = scenes[index + 1]["scene_id"] if index + 1 < len(scenes) else ""
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
        scene["continuity_from_scene_id"] = scenes[index - 1]["scene_id"] if index > 0 else ""
        scene["continuity_to_scene_id"] = scenes[index + 1]["scene_id"] if index + 1 < len(scenes) else ""
    current["scenes"] = scenes
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or []) + ["scene_plan", "scene_assignment", "dialogue", "prompts", "summary"]
    )
    return normalize_state(current)


def auto_assign_scenes(state: Mapping[str, Any]) -> dict[str, Any]:
    current = normalize_state(state)
    characters = [str(item.get("character_id") or "") for item in current["bible"]["characters"] if item.get("character_id")]
    locations = [str(item.get("location_id") or "") for item in current["bible"]["locations"] if item.get("location_id")]
    for index, scene in enumerate(current["scenes"]):
        if str(scene.get("assignment_source") or "") == "user":
            continue
        scene["character_ids"] = [characters[index % len(characters)]] if characters else []
        scene["location_id"] = locations[index % len(locations)] if locations else ""
        scene["assignment_source"] = "auto_round_robin"
    current["navigation"]["current_step"] = "scene_assignment"
    return normalize_state(current)


def assign_scene(
    state: Mapping[str, Any],
    scene_id: str,
    *,
    character_ids: Iterable[str] | None = None,
    location_id: str | None = None,
) -> dict[str, Any]:
    current = normalize_state(state)
    target = _text(scene_id, 80)
    scene = next((item for item in current["scenes"] if str(item.get("scene_id") or "") == target), None)
    if not scene:
        raise ValueError("scene_not_found")
    valid_characters = {str(item.get("character_id") or "") for item in current["bible"]["characters"]}
    selected = _dedupe(character_ids or scene.get("character_ids") or [])
    if any(item not in valid_characters for item in selected):
        raise ValueError("scene_character_invalid")
    valid_locations = {str(item.get("location_id") or "") for item in current["bible"]["locations"]}
    selected_location = str(scene.get("location_id") or "") if location_id is None else _text(location_id, 80)
    if selected_location and selected_location not in valid_locations:
        raise ValueError("scene_location_invalid")
    scene["character_ids"] = selected
    scene["location_id"] = selected_location
    scene["assignment_source"] = "user"
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
    dialogue_id = _stable_id("dlg", len(current["audio"]["dialogue_segments"]) + 1)
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
    current["navigation"]["dirty_sections"] = _dedupe(
        list(current["navigation"].get("dirty_sections") or []) + ["audio", "summary"]
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
        "location_id": str(target.get("location_id") or ""),
        "dialogue": dialogue,
        "music": music,
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
        "scene_sfx": control("scene_sfx", bool(current["audio"]["sfx_plan"])),
        "scene_ambient": control("scene_ambient", bool(current["audio"]["ambient_plan"])),
    }


def readiness_errors(state: Mapping[str, Any]) -> list[str]:
    current = normalize_state(state)
    errors: list[str] = []
    if not current["content"].get("locked"):
        errors.append("content_not_locked")
    if current["needs"].get("characters") == "REQUIRED" and not current["bible"]["characters"]:
        errors.append("characters_required")
    if not current["format"].get("scene_count_confirmed") or not current["scenes"]:
        errors.append("scene_plan_missing")
    character_ids = {str(item.get("character_id") or "") for item in current["bible"]["characters"]}
    location_ids = {str(item.get("location_id") or "") for item in current["bible"]["locations"]}
    for scene in current["scenes"]:
        if any(item not in character_ids for item in scene.get("character_ids") or []):
            errors.append(f"{scene.get('scene_id')}_character_invalid")
        if scene.get("location_id") and str(scene.get("location_id")) not in location_ids:
            errors.append(f"{scene.get('scene_id')}_location_invalid")
    for item in current["audio"]["dialogue_segments"]:
        if str(item.get("speaker_id") or "") not in character_ids and str(item.get("speaker_id") or "") != str((current["bible"].get("narrator") or {}).get("narrator_id") or ""):
            errors.append(f"{item.get('dialogue_id')}_speaker_invalid")
    dialogue_speakers = list(dict.fromkeys(
        str(item.get("speaker_id") or "")
        for item in current["audio"]["dialogue_segments"]
        if str(item.get("speaker_id") or "")
    ))
    selected_voice_ids: list[str] = []
    for speaker_id in dialogue_speakers:
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
    if not bool(_adapter(current["parent_product"])["public_submit_enabled"]):
        errors.append("public_submit_locked")
    dirty = set(current["navigation"].get("dirty_sections") or [])
    for section in ("production_bible", "scene_plan", "dialogue", "prompts"):
        if section in dirty:
            errors.append(f"{section}_reconcile_required")
    return list(dict.fromkeys(errors))


def next_required_step(state: Mapping[str, Any]) -> str:
    current = normalize_state(state)
    source = current["source"]
    if source.get("required") and not source.get("complete"):
        return "source"
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
    current["navigation"]["return_to"] = "summary"
    return navigate(current, step)


def finish_editor(state: Mapping[str, Any]) -> dict[str, Any]:
    current = normalize_state(state)
    target = str(current["navigation"].get("return_to") or "")
    if not target:
        return current
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
        product = "video_ai_real"
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
            "asset_id": _stable_id("asset", len(current["references"]) + 1),
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
    blocking = [
        item for item in errors
        if item not in {"multi_voice_renderer_missing"}
    ]
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
        "production_bible": deepcopy(current["bible"]),
        "references": deepcopy(current["references"]),
        "scenes": deepcopy(current["scenes"]),
        "audio": deepcopy(current["audio"]),
        "branding": deepcopy(current["branding"]),
        "capability_requirements": [
            key for key, item in public_controls(current).items() if item["planned"]
        ],
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
