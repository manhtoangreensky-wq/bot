"""Bridge an approved UIFLOW3 plan into the durable Video RouteEngine.

The bridge is intentionally UI- and transport-free. Compiling a handoff has
zero side effects. Preparing a commercial project persists only the immutable
draft; provider submit, job creation, outbox creation, delivery, and charging
remain behind the existing explicit final-confirm boundary.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import sqlite3
from typing import Any, Mapping
import uuid

from services import video_engine_contract
from services import video_project_queue


BRIDGE_VERSION = "video_uiflow3_routeengine_v1"
SUPPORTED_FLOW_SCHEMA_VERSION = 3
ZERO_SIDE_EFFECTS = {
    "provider_calls": 0,
    "jobs": 0,
    "outbox": 0,
    "wallet_mutations": 0,
    "charges": 0,
}
RATIO_GEOMETRY = {
    "9:16": {"width": 1080, "height": 1920},
    "16:9": {"width": 1920, "height": 1080},
    "1:1": {"width": 1080, "height": 1080},
    "4:5": {"width": 1080, "height": 1350},
}
BRAND_POSITIONS = frozenset(
    {
        "top_left",
        "top_center",
        "top_right",
        "center_left",
        "center",
        "center_right",
        "bottom_left",
        "bottom_center",
        "bottom_right",
    }
)
PRODUCT_TYPE_BY_PARENT = {
    "video_trend": "video_trend",
    "script_image_video": "script_to_video",
    "frame_video_local": "image_to_video",
    "self_shot_scene_change": "self_shot_scene_change",
    "storyboard_prompt": "storyboard_prompt",
    "multi_scene_film": "multi_scene_film",
}
ACTIVE_DRAFT_STATUSES = (
    "draft_planning",
    "draft_assets",
    "draft_prompt",
    "draft_addons",
    "draft_quality",
    "draft_scene_count",
    "draft_invoice",
    "queued_for_worker",
    "processing",
)


def _clean(value: Any, limit: int = 12000) -> str:
    return str(value or "").strip()[: max(0, int(limit))]


def _positive_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        result = int(value)
    except (TypeError, ValueError):
        return 0
    return result if result > 0 else 0


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _json_copy(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _failure(blocker: str, **extra: Any) -> dict[str, Any]:
    return {
        "ok": False,
        "commercial_ready": False,
        "blocker": _clean(blocker, 240) or "uiflow3_routeengine_bridge_blocked",
        "side_effects": dict(ZERO_SIDE_EFFECTS),
        **extra,
    }


def _snapshot_hash_valid(snapshot: Mapping[str, Any]) -> bool:
    expected = _clean(snapshot.get("config_hash"), 64).lower()
    if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
        return False
    material = deepcopy(dict(snapshot))
    material.pop("config_hash", None)
    return _sha256(material) == expected


def _public_product_type(snapshot: Mapping[str, Any]) -> str:
    parent = _clean(snapshot.get("parent_product"), 80)
    if parent == "video_ai_real":
        mode = _clean(snapshot.get("entry_mode"), 80)
        if mode == "image_video":
            return "video_ai_image"
        if mode == "video_video":
            return "video_ai_video_reference"
        return "video_ai_prompt"
    return PRODUCT_TYPE_BY_PARENT.get(parent, "")


def _brand_position(value: Any, default: str = "bottom_right") -> str:
    position = _clean(value, 40).lower()
    return position if position in BRAND_POSITIONS else default


def _branding_worker_contract(branding: Mapping[str, Any] | None) -> dict[str, Any]:
    value = deepcopy(dict(branding or {}))
    logo = dict(value.get("logo") or {})
    watermark = dict(value.get("watermark") or {})
    logo_file_id = _clean(logo.get("telegram_file_id") or logo.get("file_id"), 1024)
    logo_position = _brand_position(logo.get("position"), "top_right")
    watermark_text = _clean(watermark.get("text"), 240)
    watermark_position = _brand_position(watermark.get("position"), "bottom_right")
    asset_pack: dict[str, Any] = {}
    if logo_file_id:
        asset_pack["logo_material"] = {
            "logo_enabled": True,
            "logo_file_id": logo_file_id,
            "logo_path": "",
            "logo_position": logo_position,
            "logo_width_ratio": 0.12,
            "logo_max_width_ratio": 0.18,
            "logo_margin_x_ratio": 0.035,
            "logo_margin_y_ratio": 0.035,
            "logo_preserve_aspect_ratio": True,
            "logo_material_only": True,
            "logo_overlay_applied": False,
        }
    if watermark_text:
        asset_pack["watermark_config"] = {
            "enabled": True,
            "text": watermark_text,
            "position": watermark_position,
        }
    if logo_file_id and watermark_text:
        source = "image_and_text"
    elif logo_file_id:
        source = "telegram_image"
    elif watermark_text:
        source = "text"
    else:
        source = "none"
    return {
        "asset_pack": asset_pack,
        "addon_plan": {
            "voice_enabled": False,
            "voice_source": "none",
            "music_enabled": False,
            "music_source": "none",
            "sfx_enabled": False,
            "subtitle_enabled": False,
            "subtitle_source": "none",
            "dub_enabled": False,
            "dub_source": "none",
            "logo_enabled": bool(logo_file_id or watermark_text),
            "logo_source": source,
            "logo_text": watermark_text,
            "logo_file_id": logo_file_id,
            "logo_position": watermark_position if watermark_text else logo_position,
        },
        "logo_file_id": logo_file_id,
        "watermark_text": watermark_text,
    }


def _scene_dialogue(
    scene_id: str,
    dialogue_segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = [
        deepcopy(item)
        for item in dialogue_segments
        if _clean(item.get("scene_id"), 80) == scene_id
    ]
    rows.sort(key=lambda item: (_positive_int(item.get("order")), _clean(item.get("dialogue_id"), 80)))
    return rows


def _entity_index(bible: Mapping[str, Any], key: str, id_key: str) -> dict[str, dict[str, Any]]:
    return {
        _clean(item.get(id_key), 120): deepcopy(item)
        for item in bible.get(key) or []
        if isinstance(item, Mapping) and _clean(item.get(id_key), 120)
    }


def _scene_prompt(
    scene: Mapping[str, Any],
    *,
    scene_count: int,
    ratio: str,
    geometry: Mapping[str, Any],
    content: Mapping[str, Any],
    bible: Mapping[str, Any],
    references: list[dict[str, Any]],
    dialogue: list[dict[str, Any]],
    voice_cast: Mapping[str, Any],
) -> tuple[str, str]:
    characters = _entity_index(bible, "characters", "character_id")
    locations = _entity_index(bible, "locations", "location_id")
    products = _entity_index(bible, "products", "product_id")
    props = _entity_index(bible, "props", "prop_id")
    character_rows = [
        characters[item]
        for item in scene.get("character_ids") or []
        if item in characters
    ]
    product_rows = [
        products[item]
        for item in scene.get("product_ids") or []
        if item in products
    ]
    prop_rows = [
        props[item]
        for item in scene.get("prop_ids") or []
        if item in props
    ]
    location = locations.get(_clean(scene.get("location_id"), 120), {})
    scene_reference_ids = set(scene.get("reference_asset_ids") or [])
    scoped_references = [
        item
        for item in references
        if _clean(item.get("asset_id"), 120) in scene_reference_ids
        or _clean(scene.get("scene_id"), 120) in set(item.get("allowed_scene_ids") or [])
        or (
            _clean(item.get("owner_type"), 80) == "character"
            and _clean(item.get("owner_id"), 120) in set(scene.get("character_ids") or [])
        )
        or (
            _clean(item.get("owner_type"), 80) == "location"
            and _clean(item.get("owner_id"), 120) == _clean(scene.get("location_id"), 120)
        )
    ]
    prompt_material = {
        "scene_index": _positive_int(scene.get("scene_index")),
        "scene_count": scene_count,
        "scene_id": _clean(scene.get("scene_id"), 80),
        "scene_role": _clean(scene.get("scene_role"), 80),
        "content_intent": _clean(content.get("original_intent")),
        "approved_brief": deepcopy(dict(content.get("approved_brief") or {})),
        "semantic_beat": _clean(scene.get("semantic_beat"), 1600),
        "start_state": _clean(scene.get("start_state"), 1600),
        "main_action": _clean(scene.get("main_action"), 1600),
        "completion_state": _clean(scene.get("completion_state"), 1600),
        "characters": character_rows,
        "location": location,
        "products": product_rows,
        "props": prop_rows,
        "dialogue": dialogue,
        "voice_bindings": {
            owner_id: deepcopy(dict(voice_cast.get(owner_id) or {}))
            for owner_id in {
                *[str(item.get("speaker_id") or "") for item in dialogue],
                *[str(item.get("character_id") or "") for item in character_rows],
            }
            if owner_id
        },
        "reference_assets": scoped_references,
        "camera": _clean(scene.get("camera"), 800),
        "framing": _clean(scene.get("framing"), 240),
        "movement": _clean(scene.get("movement"), 240),
        "lighting": _clean(scene.get("lighting"), 240),
        "mood": _clean(scene.get("mood"), 240),
        "continuity_from_scene_id": _clean(scene.get("continuity_from_scene_id"), 80),
        "continuity_to_scene_id": _clean(scene.get("continuity_to_scene_id"), 80),
        "duration_seconds": _positive_int(scene.get("duration_target")),
        "aspect_ratio": ratio,
        "output_geometry": dict(geometry),
    }
    prompt = " | ".join(
        (
            f"Scene {prompt_material['scene_index']}/{scene_count} ({prompt_material['scene_id']})",
            f"Aspect ratio {ratio}; output {geometry['width']}x{geometry['height']}",
            f"Duration {prompt_material['duration_seconds']} seconds",
            f"Content lock: {_canonical_json(prompt_material['approved_brief'])}",
            f"Beat: {prompt_material['semantic_beat']}",
            f"Start state: {prompt_material['start_state']}",
            f"One complete action: {prompt_material['main_action']}",
            f"Completed end state: {prompt_material['completion_state']}",
            f"Characters: {_canonical_json(character_rows)}",
            f"Location: {_canonical_json(location)}",
            f"Products and props: {_canonical_json([*product_rows, *prop_rows])}",
            f"Dialogue and voices: {_canonical_json({'dialogue': dialogue, 'voices': prompt_material['voice_bindings']})}",
            f"Camera: {prompt_material['camera']}; framing={prompt_material['framing']}; movement={prompt_material['movement']}",
            f"Light and mood: {prompt_material['lighting']}; {prompt_material['mood']}",
            f"References: {_canonical_json(scoped_references)}",
            "Preserve stable character, product, location, wardrobe, logo, color, and continuity IDs",
            "Finish every spoken line, action, and camera movement before the scene boundary",
        )
    )
    image_prompt = " | ".join(
        (
            f"Keyframe for scene {prompt_material['scene_index']}/{scene_count}",
            f"Canvas {geometry['width']}x{geometry['height']} ({ratio})",
            f"Beat: {prompt_material['semantic_beat']}",
            f"Characters: {_canonical_json(character_rows)}",
            f"Location: {_canonical_json(location)}",
            f"Products and props: {_canonical_json([*product_rows, *prop_rows])}",
            f"Camera and light: {prompt_material['camera']}; {prompt_material['lighting']}",
            "Preserve exact identity, brand, wardrobe, product geometry, and reference ownership",
        )
    )
    return prompt, image_prompt


def _scene_cards(snapshot: Mapping[str, Any], *, ratio: str, geometry: Mapping[str, Any]) -> list[dict[str, Any]]:
    content = dict(snapshot.get("content") or {})
    bible = dict(snapshot.get("production_bible") or {})
    references = [deepcopy(dict(item)) for item in snapshot.get("references") or [] if isinstance(item, Mapping)]
    audio = dict(snapshot.get("audio") or {})
    dialogue_segments = [
        deepcopy(dict(item))
        for item in audio.get("dialogue_segments") or []
        if isinstance(item, Mapping)
    ]
    voice_cast = dict(audio.get("voice_cast") or {})
    scenes = [deepcopy(dict(item)) for item in snapshot.get("scenes") or [] if isinstance(item, Mapping)]
    result: list[dict[str, Any]] = []
    for scene in scenes:
        scene_id = _clean(scene.get("scene_id"), 80)
        dialogue = _scene_dialogue(scene_id, dialogue_segments)
        provider_prompt, image_prompt = _scene_prompt(
            scene,
            scene_count=len(scenes),
            ratio=ratio,
            geometry=geometry,
            content=content,
            bible=bible,
            references=references,
            dialogue=dialogue,
            voice_cast=voice_cast,
        )
        dialogue_text = " ".join(_clean(item.get("text"), 4000) for item in dialogue if _clean(item.get("text"), 4000))
        result.append(
            {
                **scene,
                "scene_id": scene_id,
                "scene_index": _positive_int(scene.get("scene_index")),
                "role": _clean(scene.get("scene_role"), 80),
                "script_text": dialogue_text or _clean(scene.get("semantic_beat"), 4000),
                "narration_line": dialogue_text,
                "subtitle_line": dialogue_text,
                "image_prompt": image_prompt,
                "video_prompt": provider_prompt,
                "provider_prompt": provider_prompt,
                "negative_prompt": (
                    "no identity drift, no gender or voice swap, no wardrobe drift, "
                    "no product or logo change, no wrong aspect ratio, no unfinished action, "
                    "no unfinished sentence, no mid-motion cut"
                ),
                "dialogue_segments": dialogue,
                "voice_bindings": {
                    owner_id: deepcopy(dict(voice_cast.get(owner_id) or {}))
                    for owner_id in {
                        *[str(item.get("speaker_id") or "") for item in dialogue],
                        *[str(item or "") for item in scene.get("character_ids") or []],
                    }
                    if owner_id
                },
                "aspect_ratio": ratio,
                "output_geometry": dict(geometry),
                "duration_seconds": _positive_int(scene.get("duration_target")),
                "prompt_sha256": hashlib.sha256(provider_prompt.encode("utf-8")).hexdigest(),
            }
        )
    return result


def _route_selection(
    *,
    public_product_type: str,
    scene_count: int,
    story_bible: Mapping[str, Any],
    scene_cards: list[dict[str, Any]],
) -> dict[str, Any]:
    shared = {
        "source": "product_video",
        "product_type": public_product_type,
        "public_product_type": public_product_type,
        "scene_count": scene_count,
    }
    return video_engine_contract.durable_video_product_route_selection(
        {
            "scene_count": scene_count,
            "asset_pack_json": _canonical_json(shared),
            "invoice_json": _canonical_json(shared),
            "story_bible_json": _canonical_json(dict(story_bible)),
            "scene_cards_json": _canonical_json(scene_cards),
        }
    )


def _handoff_hash(handoff: Mapping[str, Any]) -> str:
    material = deepcopy(dict(handoff))
    material.pop("handoff_sha256", None)
    return _sha256(material)


def compile_routeengine_handoff(
    approved_snapshot: Mapping[str, Any] | None,
    *,
    owner_user_id: int,
    owner_chat_id: int,
) -> dict[str, Any]:
    """Compile one immutable, side-effect-free RouteEngine handoff."""

    if not isinstance(approved_snapshot, Mapping):
        return _failure("uiflow3_approved_snapshot_required")
    if _positive_int(owner_user_id) <= 0 or _positive_int(owner_chat_id) <= 0:
        return _failure("uiflow3_owner_required")
    if int(owner_user_id) != int(owner_chat_id):
        return _failure("uiflow3_private_chat_required")
    snapshot = _json_copy(dict(approved_snapshot))
    if _positive_int(snapshot.get("flow_schema_version")) != SUPPORTED_FLOW_SCHEMA_VERSION:
        return _failure("uiflow3_snapshot_schema_unsupported")
    if not _snapshot_hash_valid(snapshot):
        return _failure("uiflow3_snapshot_hash_mismatch")
    draft_id = _clean(snapshot.get("draft_id"), 160)
    if not draft_id:
        return _failure("uiflow3_draft_id_required")
    public_product_type = _public_product_type(snapshot)
    if not public_product_type:
        return _failure("uiflow3_parent_product_unsupported")
    fmt = dict(snapshot.get("format") or {})
    ratio = _clean(fmt.get("ratio"), 20)
    geometry = RATIO_GEOMETRY.get(ratio)
    if not geometry:
        return _failure("uiflow3_aspect_ratio_unsupported")
    scenes = [dict(item) for item in snapshot.get("scenes") or [] if isinstance(item, Mapping)]
    scene_count = _positive_int(fmt.get("scene_count"))
    if scene_count <= 0 or scene_count != len(scenes):
        return _failure("uiflow3_scene_count_mismatch")
    expected_indexes = list(range(1, scene_count + 1))
    scene_indexes = [_positive_int(item.get("scene_index")) for item in scenes]
    scene_ids = [_clean(item.get("scene_id"), 80) for item in scenes]
    if scene_indexes != expected_indexes or any(not item for item in scene_ids) or len(set(scene_ids)) != scene_count:
        return _failure("uiflow3_scene_identity_invalid")
    if any(_clean(item.get("ratio"), 20) != ratio for item in scenes):
        return _failure("uiflow3_scene_ratio_mismatch")

    content = deepcopy(dict(snapshot.get("content") or {}))
    production_bible = deepcopy(dict(snapshot.get("production_bible") or {}))
    story_bible = {
        **production_bible,
        "primary_profile": _clean(content.get("profile_id"), 160),
        "technical_profile": _clean((content.get("approved_brief") or {}).get("technical_profile"), 160),
        "uiflow3_content": content,
        "uiflow3_series": deepcopy(dict(snapshot.get("series") or {})),
        "uiflow3_episode": deepcopy(dict(snapshot.get("episode") or {})),
        "uiflow3_effective_episode": deepcopy(snapshot.get("effective_episode")),
        "uiflow3_snapshot_config_hash": _clean(snapshot.get("config_hash"), 64),
    }
    cards = _scene_cards(snapshot, ratio=ratio, geometry=geometry)
    selection = _route_selection(
        public_product_type=public_product_type,
        scene_count=scene_count,
        story_bible=story_bible,
        scene_cards=cards,
    )
    if not selection.get("selection_ok"):
        return _failure(
            _clean(selection.get("blocker"), 240) or "uiflow3_route_selection_failed",
            route_selection=selection,
        )
    audio = deepcopy(dict(snapshot.get("audio") or {}))
    voice_policy = {
        "voice_cast": deepcopy(dict(audio.get("voice_cast") or {})),
        "narrator": deepcopy(dict(production_bible.get("narrator") or {})),
        "dialogue_owner": "stable_character_or_narrator_id",
        "distinct_voice_required": True,
    }
    audio_policy = {
        "dialogue_segments": deepcopy(list(audio.get("dialogue_segments") or [])),
        "music_scope": _clean(audio.get("music_scope"), 40) or "none",
        "music_plan": deepcopy(dict(audio.get("music_plan") or {})),
        "sfx_plan": deepcopy(dict(audio.get("sfx_plan") or {})),
        "ambient_plan": deepcopy(dict(audio.get("ambient_plan") or {})),
        "voice_cast": deepcopy(dict(audio.get("voice_cast") or {})),
    }
    branding = deepcopy(dict(snapshot.get("branding") or {}))
    branding_worker_contract = _branding_worker_contract(branding)
    addon_plan = {
        "voice": deepcopy(voice_policy),
        "music": {
            "scope": audio_policy["music_scope"],
            "plan": deepcopy(audio_policy["music_plan"]),
        },
        "sfx": deepcopy(audio_policy["sfx_plan"]),
        "ambient": deepcopy(audio_policy["ambient_plan"]),
        "branding": branding,
        "materialization_policy": "worker_must_materialize_and_validate_before_apply",
        "silent_drop_allowed": False,
        **deepcopy(dict(branding_worker_contract["addon_plan"])),
    }
    references = [deepcopy(dict(item)) for item in snapshot.get("references") or [] if isinstance(item, Mapping)]
    source = deepcopy(dict(snapshot.get("source") or {}))
    render_blockers = [_clean(item, 240) for item in snapshot.get("render_blockers") or [] if _clean(item, 240)]
    bridge_blockers: list[str] = []
    if selection.get("engine_product") != video_engine_contract.VideoProduct.PRODUCT_VIDEO.value:
        bridge_blockers.append("uiflow3_engine_route_delegated")
    if selection.get("engine_product") == video_engine_contract.VideoProduct.PRODUCT_VIDEO.value:
        expected_scene_seconds = int(video_project_queue.PRODUCT_VIDEO_SCENE_SECONDS)
        scene_durations = [_positive_int(item.get("duration_seconds")) for item in cards]
        if (
            target_duration := _positive_int(fmt.get("target_duration_seconds"))
        ) != scene_count * expected_scene_seconds or any(
            item != expected_scene_seconds for item in scene_durations
        ):
            bridge_blockers.append("uiflow3_product_duration_contract_mismatch")
        if audio.get("voice_cast") or audio.get("dialogue_segments"):
            bridge_blockers.append("uiflow3_voice_materialization_missing")
        if _clean(audio.get("music_scope"), 40) not in {"", "none"}:
            bridge_blockers.append("uiflow3_music_materialization_missing")
        if audio.get("sfx_plan") or audio.get("ambient_plan"):
            bridge_blockers.append("uiflow3_scene_audio_materialization_missing")
        if references:
            bridge_blockers.append("uiflow3_reference_materialization_missing")
        if branding_worker_contract.get("logo_file_id") and branding_worker_contract.get("watermark_text"):
            bridge_blockers.append("uiflow3_dual_branding_materialization_missing")
    bridge_blockers = list(dict.fromkeys(bridge_blockers))
    commercial_ready = not render_blockers and not bridge_blockers
    target_duration = _positive_int(fmt.get("target_duration_seconds"))
    result = {
        "ok": True,
        "bridge_version": BRIDGE_VERSION,
        "commercial_ready": commercial_ready,
        "commercial_blocker": (
            "uiflow3_render_blockers_present"
            if render_blockers
            else bridge_blockers[0]
            if bridge_blockers
            else ""
        ),
        "blocker": "",
        "draft_id": draft_id,
        "owner_user_id": int(owner_user_id),
        "owner_chat_id": int(owner_chat_id),
        "parent_product": _clean(snapshot.get("parent_product"), 80),
        "public_product_type": public_product_type,
        "render_family": _clean(snapshot.get("render_family"), 80),
        "route_selection": selection,
        "snapshot_config_hash": _clean(snapshot.get("config_hash"), 64).lower(),
        "approved_snapshot": snapshot,
        "source": source,
        "content": content,
        "story_bible": story_bible,
        "references": references,
        "scene_cards": cards,
        "scene_count": scene_count,
        "aspect_ratio": ratio,
        "output_geometry": dict(geometry),
        "target_duration_seconds": target_duration,
        "scene_duration_seconds": [int(item.get("duration_seconds") or 0) for item in cards],
        "audio_policy": audio_policy,
        "voice_policy": voice_policy,
        "addon_plan": addon_plan,
        "branding_worker_contract": branding_worker_contract,
        "creative_controls": {
            "continuity": deepcopy(dict(production_bible.get("continuity") or {})),
            "references": references,
            "scene_directions": [
                {
                    key: deepcopy(item.get(key))
                    for key in (
                        "scene_id",
                        "scene_index",
                        "camera",
                        "framing",
                        "movement",
                        "lighting",
                        "mood",
                        "start_state",
                        "completion_state",
                    )
                }
                for item in cards
            ],
        },
        "render_blockers": render_blockers,
        "bridge_blockers": bridge_blockers,
        "prompt_text": _clean(content.get("original_intent"), 8000),
        "side_effects": dict(ZERO_SIDE_EFFECTS),
    }
    result["handoff_sha256"] = _handoff_hash(result)
    return result


def _quote_state(quote: Mapping[str, Any] | None, *, scene_count: int) -> dict[str, Any]:
    if not isinstance(quote, Mapping):
        return _failure("uiflow3_commercial_quote_required")
    value = deepcopy(dict(quote))
    quoted_scene_count = _positive_int(value.get("scene_count"))
    if quoted_scene_count and quoted_scene_count != scene_count:
        return _failure("uiflow3_commercial_quote_scene_count_mismatch")
    user_visible = _positive_int(
        value.get("user_visible_price_xu")
        or value.get("package_xu")
        or value.get("total_xu")
    )
    persisted = _positive_int(value.get("persisted_quoted_price_xu") or user_visible)
    customer_charge = _positive_int(value.get("customer_charge_planned_xu") or user_visible)
    if user_visible <= 0 or persisted != user_visible or customer_charge != user_visible:
        return _failure("uiflow3_commercial_quote_mismatch")
    value.update(
        {
            "scene_count": scene_count,
            "user_visible_price_xu": user_visible,
            "persisted_quoted_price_xu": persisted,
            "customer_charge_planned_xu": customer_charge,
            "wallet_charge_amount_xu": customer_charge,
            "total_xu": _positive_int(value.get("total_xu")) or user_visible,
            "quality_tier": _positive_int(value.get("quality_tier")) or 300,
        }
    )
    return {
        "ok": True,
        "quote": value,
        "quote_sha256": _sha256(value),
        "side_effects": dict(ZERO_SIDE_EFFECTS),
    }


def _existing_project_for_snapshot(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    snapshot_hash: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    placeholders = ",".join("?" for _ in ACTIVE_DRAFT_STATUSES)
    rows = conn.execute(
        f"""SELECT project_id,asset_pack_json
              FROM video_projects
             WHERE user_id=? AND status IN ({placeholders})
             ORDER BY project_id DESC LIMIT 100""",
        (int(user_id), *ACTIVE_DRAFT_STATUSES),
    ).fetchall()
    for row in rows:
        project_id = int(row[0])
        try:
            asset_pack = json.loads(str(row[1] or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(asset_pack, dict):
            continue
        if _clean(asset_pack.get("uiflow3_snapshot_config_hash"), 64).lower() != snapshot_hash:
            continue
        return video_project_queue.get_video_project(conn, project_id), asset_pack
    return {}, {}


def prepare_commercial_project(
    conn: sqlite3.Connection,
    handoff: Mapping[str, Any] | None,
    *,
    quote: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Persist one immutable draft; explicit confirm remains the first job edge."""

    if not isinstance(conn, sqlite3.Connection):
        return _failure("uiflow3_database_connection_required")
    video_project_queue.ensure_video_project_queue_schema(conn)
    if not isinstance(handoff, Mapping) or not handoff.get("ok"):
        return _failure("uiflow3_routeengine_handoff_required")
    handoff_value = _json_copy(dict(handoff))
    if _clean(handoff_value.get("handoff_sha256"), 64).lower() != _handoff_hash(handoff_value):
        return _failure("uiflow3_routeengine_handoff_hash_mismatch")
    if not handoff_value.get("commercial_ready"):
        blocker = (
            "uiflow3_render_blockers_present"
            if handoff_value.get("render_blockers")
            else _clean(handoff_value.get("commercial_blocker"), 240)
            or "uiflow3_commercial_route_not_ready"
        )
        return _failure(blocker)
    route_selection = dict(handoff_value.get("route_selection") or {})
    if route_selection.get("engine_product") != video_engine_contract.VideoProduct.PRODUCT_VIDEO.value:
        return _failure("uiflow3_commercial_engine_route_unsupported")
    user_id = _positive_int(handoff_value.get("owner_user_id"))
    chat_id = _positive_int(handoff_value.get("owner_chat_id"))
    if user_id <= 0 or chat_id != user_id:
        return _failure("uiflow3_owner_required")
    scene_count = _positive_int(handoff_value.get("scene_count"))
    quote_state = _quote_state(quote, scene_count=scene_count)
    if not quote_state.get("ok"):
        return quote_state
    quote_value = dict(quote_state["quote"])
    quote_hash = str(quote_state["quote_sha256"])
    public_product_type = _clean(handoff_value.get("public_product_type"), 80)
    engine_contract = video_project_queue.product_video_engine_contract(public_product_type)
    if not engine_contract.get("execution_enabled", True):
        return _failure(
            _clean(engine_contract.get("execution_blocker"), 240)
            or "uiflow3_product_engine_disabled"
        )
    provider_chain = quote_value.get("provider_chain") or video_project_queue.resolve_product_video_provider_chain()
    if isinstance(provider_chain, str):
        provider_chain = video_project_queue.normalize_product_video_provider_chain(provider_chain)
    else:
        provider_chain = [
            _clean(item, 80)
            for item in provider_chain or []
            if _clean(item, 80)
        ]
    orchestration_mode = (
        video_project_queue.PRODUCT_VIDEO_ORCHESTRATION_MODE_RAW_DELIVERY
        if scene_count == 1
        else video_project_queue.PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE
    )
    snapshot_hash = _clean(handoff_value.get("snapshot_config_hash"), 64).lower()
    handoff_hash = _clean(handoff_value.get("handoff_sha256"), 64).lower()
    shared = {
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "public_user_confirmed": False,
        "invoice_confirmed": False,
        "submit_source": "",
        "provider_submit_source": "",
        "public_product_type": public_product_type,
        "video_product_type": public_product_type,
        "product_type": public_product_type,
        "engine_route": _clean(engine_contract.get("engine_route"), 160),
        "engine_adapter": _clean(engine_contract.get("engine_adapter"), 160),
        "required_capability": _clean(engine_contract.get("required_capability"), 160),
        "worker_owner": _clean(engine_contract.get("worker_owner"), 160),
        "orchestration_mode": orchestration_mode,
        "provider_orchestration_mode": orchestration_mode,
        "provider_chain": provider_chain,
        "provider_order": ",".join(provider_chain),
        "scene_count": scene_count,
        "duration_seconds": _positive_int(handoff_value.get("target_duration_seconds")),
        "expected_duration_seconds": _positive_int(handoff_value.get("target_duration_seconds")),
        "scene_duration_seconds": _positive_int((handoff_value.get("scene_duration_seconds") or [0])[0]),
        "aspect_ratio": _clean(handoff_value.get("aspect_ratio"), 20),
        "output_geometry": deepcopy(dict(handoff_value.get("output_geometry") or {})),
        "charge_policy": "after_valid_mp4_delivery",
        "no_charge_before_final_mp4": True,
        "uiflow3_bridge_version": BRIDGE_VERSION,
        "uiflow3_draft_id": _clean(handoff_value.get("draft_id"), 160),
        "uiflow3_owner_user_id": user_id,
        "uiflow3_owner_chat_id": chat_id,
        "uiflow3_snapshot_config_hash": snapshot_hash,
        "uiflow3_handoff_sha256": handoff_hash,
        "uiflow3_quote_sha256": quote_hash,
        "uiflow3_route_selection_sha256": _clean(route_selection.get("route_selection_sha256"), 64),
    }
    branding_worker_contract = deepcopy(dict(handoff_value.get("branding_worker_contract") or {}))
    asset_pack = {
        **shared,
        **deepcopy(dict(branding_worker_contract.get("asset_pack") or {})),
        "original_user_prompt": _clean(handoff_value.get("prompt_text"), 8000),
        "cleaned_user_prompt": " ".join(_clean(handoff_value.get("prompt_text"), 8000).split()),
        "uiflow3_approved_snapshot": deepcopy(dict(handoff_value.get("approved_snapshot") or {})),
        "uiflow3_source": deepcopy(dict(handoff_value.get("source") or {})),
        "uiflow3_references": deepcopy(list(handoff_value.get("references") or [])),
        "audio_policy": deepcopy(dict(handoff_value.get("audio_policy") or {})),
        "voice_policy": deepcopy(dict(handoff_value.get("voice_policy") or {})),
        "addon_plan": deepcopy(dict(handoff_value.get("addon_plan") or {})),
        "route_selection": route_selection,
        "side_effects_before_confirm": dict(ZERO_SIDE_EFFECTS),
    }
    invoice = {
        **quote_value,
        **shared,
        "uiflow3_quote_sha256": quote_hash,
        "customer_charge_planned_xu": int(quote_value["customer_charge_planned_xu"]),
        "wallet_charge_amount_xu": int(quote_value["wallet_charge_amount_xu"]),
    }
    story_bible = deepcopy(dict(handoff_value.get("story_bible") or {}))
    scene_cards = deepcopy(list(handoff_value.get("scene_cards") or []))
    addon_plan = deepcopy(dict(handoff_value.get("addon_plan") or {}))
    creative_controls = deepcopy(dict(handoff_value.get("creative_controls") or {}))
    now = video_project_queue.now_text()
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing, existing_asset = _existing_project_for_snapshot(
            conn,
            user_id=user_id,
            snapshot_hash=snapshot_hash,
        )
        if existing:
            if _clean(existing_asset.get("uiflow3_handoff_sha256"), 64).lower() != handoff_hash:
                conn.rollback()
                return _failure("uiflow3_routeengine_handoff_conflict")
            if _clean(existing_asset.get("uiflow3_quote_sha256"), 64).lower() != quote_hash:
                conn.rollback()
                return _failure("uiflow3_commercial_quote_conflict")
            conn.commit()
            return {
                "ok": True,
                "project": existing,
                "duplicate_prevented": True,
                "job_created": False,
                "outbox_created": False,
                "side_effects": dict(ZERO_SIDE_EFFECTS),
            }
        project_uuid = f"vprj_{uuid.uuid4().hex}"
        cursor = conn.execute(
            """INSERT INTO video_projects
               (project_uuid,user_id,status,profile_id,topic,ratio,
                selected_suggestion_json,asset_pack_json,story_bible_json,scene_cards_json,
                prompt_text,addon_plan_json,creative_control_json,quality_tier,scene_count,
                addons_disabled_by_package,invoice_json,total_xu_estimated,is_confirmed,
                created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                project_uuid,
                user_id,
                "draft_invoice",
                _clean(story_bible.get("primary_profile"), 160) or public_product_type,
                _clean(handoff_value.get("prompt_text"), 8000),
                _clean(handoff_value.get("aspect_ratio"), 20),
                _canonical_json(dict((handoff_value.get("content") or {}).get("approved_brief") or {})),
                _canonical_json(asset_pack),
                _canonical_json(story_bible),
                _canonical_json(scene_cards),
                _clean(handoff_value.get("prompt_text"), 8000),
                _canonical_json(addon_plan),
                _canonical_json(creative_controls),
                int(quote_value["quality_tier"]),
                scene_count,
                1 if quote_value.get("addons_disabled_by_package") else 0,
                _canonical_json(invoice),
                int(quote_value["user_visible_price_xu"]),
                0,
                now,
                now,
            ),
        )
        project_id = int(cursor.lastrowid or 0)
        for fallback_index, card in enumerate(scene_cards, start=1):
            conn.execute(
                """INSERT INTO video_scenes
                   (project_id,scene_index,role,script_text,subtitle_line,image_prompt,
                    video_prompt,reference_asset_ids_json,scene_status)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    project_id,
                    _positive_int(card.get("scene_index")) or fallback_index,
                    _clean(card.get("role"), 120),
                    _clean(card.get("script_text"), 8000),
                    _clean(card.get("subtitle_line"), 4000),
                    _clean(card.get("image_prompt"), 12000),
                    _clean(card.get("provider_prompt") or card.get("video_prompt"), 12000),
                    _canonical_json(list(card.get("reference_asset_ids") or [])),
                    "pending",
                ),
            )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    project = video_project_queue.get_video_project(conn, project_id)
    return {
        "ok": True,
        "project": project,
        "duplicate_prevented": False,
        "job_created": False,
        "outbox_created": False,
        "side_effects": dict(ZERO_SIDE_EFFECTS),
    }
