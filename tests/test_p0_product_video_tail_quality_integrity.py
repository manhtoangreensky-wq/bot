from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from services import video_ai_real_pricing
from services import video_tail9
from services import video_uiflow3
from services import video_uiflow3_routeengine


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _source(name: str) -> str:
    for marker in (f"\ndef {name}(", f"\nasync def {name}("):
        marker_at = BOT_SOURCE.find(marker)
        if marker_at >= 0:
            break
    assert marker_at >= 0, name
    start = marker_at + 1
    next_sync = BOT_SOURCE.find("\ndef ", start + len(marker))
    next_async = BOT_SOURCE.find("\nasync def ", start + len(marker))
    ends = [offset + 1 for offset in (next_sync, next_async) if offset >= 0]
    return BOT_SOURCE[start : min(ends) if ends else len(BOT_SOURCE)]


def _safe_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return int(default)


def _apply_ai_quality(raw_state: dict, tier_id: int) -> dict:
    state = video_uiflow3.normalize_state(raw_state)
    quality = video_ai_real_pricing.public_quality_by_tier(tier_id)
    seconds = int(quality["seconds"])
    scene_count = len(state["scenes"])
    state["format"]["seconds_per_scene"] = seconds
    state["format"]["target_duration_seconds"] = scene_count * seconds
    for scene in state["scenes"]:
        scene["duration_target"] = seconds
    return video_uiflow3.normalize_state(state)


NAMESPACE = {
    "deepcopy": deepcopy,
    "hashlib": hashlib,
    "json": json,
    "safe_int": _safe_int,
    "video_ai_real_apply_quality_product": _apply_ai_quality,
    "video_ai_real_pricing": video_ai_real_pricing,
    "video_tail9": video_tail9,
    "video_uiflow3": video_uiflow3,
    "VIDEO_TAIL9_STATE_KEY": "video_tail9",
}
for FUNCTION_NAME in (
    "video_tail9_parse_quality_tier",
    "video_uiflow3_snapshot_revision",
    "video_uiflow3_apply_tail_quality_contract",
):
    exec(compile(_source(FUNCTION_NAME), str(ROOT / "bot.py"), "exec"), NAMESPACE)

parse_quality = NAMESPACE["video_tail9_parse_quality_tier"]
apply_quality_contract = NAMESPACE["video_uiflow3_apply_tail_quality_contract"]


def _ready_state(product: str, scene_count: int) -> dict:
    state = video_uiflow3.new_state(product, draft_id=f"tail-quality-{product}")
    if product == "video_ai_real":
        state = video_uiflow3.set_entry_mode(state, "prompt_video")
    elif product == "storyboard_prompt":
        state = video_uiflow3.set_entry_mode(state, "storyboard_upload")
        for index in range(1, scene_count + 1):
            state = video_uiflow3.add_source_asset(
                state,
                asset_type="frame",
                telegram_file_id=f"storyboard-{index}",
                fingerprint=f"telegram:storyboard-{index}",
            )
        state = video_uiflow3.set_source_metadata(
            state,
            detected_panel_count=scene_count,
        )
    elif product in {"video_trend", "script_image_video"}:
        state = video_uiflow3.set_source_metadata(
            state,
            text=f"Source content for {product}",
        )
    state = video_uiflow3.set_format(
        state,
        ratio="9:16",
        target_duration_seconds=scene_count * 8,
        **({"seconds_per_scene": 8} if product == "video_ai_real" else {}),
    )
    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent=f"Approved content for {product}",
        approved_brief={
            "title": f"Approved {product}",
            "needs_characters": False,
            "needs_locations": False,
            "needs_dialogue": False,
            "needs_voice": False,
            "needs_music": False,
        },
    )
    state = video_uiflow3.lock_content(state)
    state = video_uiflow3.set_character_count(state, 0)
    state = video_uiflow3.set_location_count(state, 0)
    state = video_uiflow3.confirm_scene_count(state, scene_count)
    state = video_uiflow3.suggest_scene_plan(state)
    state = video_uiflow3.auto_assign_scenes(state)
    state = video_uiflow3.mark_sections_complete(
        state,
        "production_bible",
        "references",
        "continuity",
        "scene_plan",
        "scene_assignment",
        "dialogue",
        "prompts",
        "branding",
        "summary",
    )
    state["navigation"]["dirty_sections"] = []
    return video_uiflow3.normalize_state(state)


def _tail(state: dict, tier_id: int) -> dict:
    snapshot = video_uiflow3.approved_snapshot(state)
    tail = video_tail9.new_state(
        product_type=state["parent_product"],
        session_id=state["draft_id"],
        plan_revision=NAMESPACE["video_uiflow3_snapshot_revision"](snapshot),
        scene_count=len(state["scenes"]),
        ratio=state["format"]["ratio"],
        estimated_duration=state["format"]["target_duration_seconds"],
    )
    tail["quality_tier_id"] = str(tier_id)
    tail["package_id"] = f"product_video_{tier_id}"
    tail["capability_snapshot"] = {"ok": True}
    return video_tail9.normalize_state(tail)


@pytest.mark.parametrize(
    ("product", "scene_count", "tier_id", "seconds"),
    (
        ("video_ai_real", 2, 400, 8),
        ("video_trend", 2, 300, 5),
        ("script_image_video", 5, 400, 8),
        ("storyboard_prompt", 2, 500, 5),
    ),
)
def test_selected_quality_builds_one_hashed_execution_snapshot(
    product: str,
    scene_count: int,
    tier_id: int,
    seconds: int,
) -> None:
    planning_state = _ready_state(product, scene_count)
    planning_seconds = planning_state["format"]["seconds_per_scene"]

    prepared, tail, snapshot = apply_quality_contract(
        planning_state,
        _tail(planning_state, tier_id),
    )
    handoff = video_uiflow3_routeengine.compile_routeengine_handoff(
        snapshot,
        owner_user_id=7001,
        owner_chat_id=7001,
        tail_state=tail,
    )

    assert snapshot["format"]["seconds_per_scene"] == seconds
    assert snapshot["format"]["target_duration_seconds"] == scene_count * seconds
    assert [item["duration_target"] for item in snapshot["scenes"]] == [seconds] * scene_count
    assert tail["estimated_duration"] == scene_count * seconds
    assert (prepared["legacy_compat"] or {})["approved_snapshot"]["config_hash"] == snapshot["config_hash"]
    assert handoff["commercial_ready"] is True, handoff
    assert handoff["commercial_blocker"] == ""
    assert handoff["target_duration_seconds"] == scene_count * seconds
    assert handoff["scene_duration_seconds"] == [seconds] * scene_count
    if product != "video_ai_real":
        assert prepared["format"]["seconds_per_scene"] == planning_seconds == 8


def test_tier_400_repairs_the_exact_live_drift_without_weakening_the_gate() -> None:
    state = _ready_state("video_ai_real", 2)
    state["format"]["seconds_per_scene"] = 5
    state["format"]["target_duration_seconds"] = 16
    for scene in state["scenes"]:
        scene["duration_target"] = 5
    state = video_uiflow3.normalize_state(state)

    _prepared, tail, snapshot = apply_quality_contract(state, _tail(state, 400))
    handoff = video_uiflow3_routeengine.compile_routeengine_handoff(
        snapshot,
        owner_user_id=7002,
        owner_chat_id=7002,
        tail_state=tail,
    )

    assert snapshot["format"]["seconds_per_scene"] == 8
    assert snapshot["format"]["target_duration_seconds"] == 16
    assert handoff["commercial_ready"] is True

    forged = deepcopy(snapshot)
    forged["scenes"][0]["duration_target"] = 5
    forged_material = deepcopy(forged)
    forged_material.pop("config_hash", None)
    forged["config_hash"] = hashlib.sha256(
        json.dumps(
            forged_material,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    blocked = video_uiflow3_routeengine.compile_routeengine_handoff(
        forged,
        owner_user_id=7002,
        owner_chat_id=7002,
        tail_state=tail,
    )
    assert blocked["commercial_ready"] is False
    assert blocked["commercial_blocker"] == "uiflow3_product_duration_contract_mismatch"


@pytest.mark.parametrize("value", ("", "abc", "0400", "1501", "2360"))
def test_forged_quality_is_rejected_instead_of_clamped(value: str) -> None:
    with pytest.raises(ValueError, match="quality_tier_not_supported"):
        parse_quality(value)


def test_tail_handler_validates_exact_tier_and_current_catalog_without_ui_changes() -> None:
    handler = _source("handle_video_tail_callback")
    assert "quality = video_tail9_parse_quality_tier(argument)" in handler
    assert "if quality not in available_tiers:" in handler
    assert "quality = max(200, min(1500" not in handler
    assert "calculated_scene_count * scene_seconds" in handler
    assert "video_tail9.set_capability(selection_tail, capability)" in handler


def test_non_uiflow3_session_persists_selected_quality_seconds() -> None:
    session_handoff = _source("video_tail9_apply_to_session")
    assert 'clean_product not in {"multi_scene_film", "video_long"}' in session_handoff
    assert "selected_tier = video_tail9_parse_quality_tier" in session_handoff
    assert '"b14_scene_seconds": max(' in session_handoff
