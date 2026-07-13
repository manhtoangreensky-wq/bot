from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.video_addon_planner import normalize_addon_plan
from services.video_prompt_pattern_library import load_approved_patterns, select_approved_pattern
from services.video_scene_continuity import build_continuity_contract
from services.video_scene_prompt_builder import build_prompt_package, regenerate_scene_prompt
from services.video_semantic_scene_planner import (
    SCENE_REQUIRED_FIELDS,
    build_semantic_scene_plan,
    rebuild_for_scene_count,
    reorder_scenes,
    replace_scene_idea,
)


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _package(scene_count: int = 3, profile_id: str = "product_3d_showcase", **content):
    addons = normalize_addon_plan(
        {"cta": True, "aspect_ratio": "9:16", **content},
        {"subtitle_rendering": bool(content.get("subtitle_required"))},
        scene_count=scene_count,
    )
    return build_prompt_package(build_semantic_scene_plan(
        subject="Sản phẩm TOAN AAS",
        scene_count=scene_count,
        profile_id=profile_id,
        context="giới thiệu rõ lợi ích và kết quả",
        requirements={"preserve_constraints": ["giữ đúng sản phẩm", "không đổi màu"]},
        assets={"products": ["Sản phẩm TOAN AAS"], "logos": ["TOAN AAS"]},
        addon_plan=addons,
    ))


def test_canonical_wizard_is_scene_first_and_price_is_near_end():
    order = [
        "subject", "scene_count", "profile", "profile_context", "requirements",
        "reference_assets", "content_addons", "scene_plan", "prompt_preview",
        "post_addons", "quality", "final_report", "final_confirmation",
    ]
    positions = [BOT_SOURCE.index(f'    "{step}",', BOT_SOURCE.index("VIDEO_SCENE1_CANONICAL_STEPS")) for step in order]
    assert positions == sorted(positions)
    handler = BOT_SOURCE[BOT_SOURCE.index("async def handle_video_profile_studio_pending_text"):BOT_SOURCE.index("async def handle_video_profile_studio_callback")]
    assert handler.index('if step == "await_subject"') < handler.index('if step == "await_count_custom"')
    assert '"scene_count",\n    "profile"' in BOT_SOURCE
    assert '"prompt_preview",\n    "post_addons",\n    "quality"' in BOT_SOURCE
    assert 'callback_data="vprofile|invoice_back"' in BOT_SOURCE
    assert 'if action == "invoice_back"' in BOT_SOURCE
    assert 'current = str(state.get("step") or "menu")' in BOT_SOURCE
    assert 'step = history.pop() if history else "menu"' in BOT_SOURCE


@pytest.mark.parametrize("scene_count", [1, 3, 5, 20])
def test_exact_scene_count_and_complete_semantic_contract(scene_count: int):
    package = _package(scene_count)
    assert package["scene_count"] == scene_count
    assert len(package["scenes"]) == scene_count
    assert len(package["scene_prompts"]) == scene_count
    assert package["quality_gate"]["ok"] is True
    ideas = []
    for index, scene in enumerate(package["scenes"], 1):
        assert scene["scene_index"] == index
        assert all(field in scene for field in SCENE_REQUIRED_FIELDS)
        assert scene["start_state"]
        assert scene["primary_action"]
        assert scene["completion_state"]
        assert scene["semantic_complete"] is True
        assert scene["action_completed"] is True
        assert scene["camera_motion_completed"] is True
        assert scene["provider_prompt"]
        assert scene["negative_prompt"]
        ideas.append(scene["main_idea"])
    assert len(ideas) == len(set(ideas))
    assert package["quality_gate"]["final_conclusion_complete"] is True


@pytest.mark.parametrize(
    ("profile_id", "expected_role"),
    [
        ("architecture_interior", "establish_space"),
        ("real_estate_property", "exterior_entry"),
        ("product_3d_showcase", "problem_context"),
        ("fashion_virtual_model", "look_introduction"),
        ("cinematic_vfx", "normal_state"),
        ("animation_character", "character_setup"),
        ("creator_tutorial_ugc", "problem"),
    ],
)
def test_profile_specific_scene_templates(profile_id: str, expected_role: str):
    package = _package(5, profile_id)
    assert package["scenes"][0]["scene_role"] == expected_role
    assert package["scenes"][-1]["completion_state"]


def test_continuity_transitions_and_addon_safe_zones_are_planning_inputs():
    package = _package(
        5,
        "architecture_interior",
        voiceover=True,
        captions=True,
        subtitle_required=True,
        logo_safe_zone="top_right",
        watermark_safe_zone="bottom_right",
        music_mood="êm và cao trào dần",
    )
    constraints = package["addon_plan"]["composition_constraints"]
    assert constraints["subtitle_safe_area"] == "lower_22_percent_clear"
    assert constraints["logo_safe_area"] == "top_right"
    assert constraints["watermark_safe_area"] == "bottom_right"
    assert package["addon_plan"]["execution_started"] is False
    assert len(package["transitions"]) == 4
    assert len({item["transition_type"] for item in package["transitions"]}) > 1
    for previous, current in zip(package["scenes"], package["scenes"][1:]):
        assert current["inherited_from_previous"] == previous["completion_state"]
        assert len(current["dialogue_or_voiceover"].split()) <= constraints["voiceover_max_words_per_scene"]


def test_scene_edit_regenerate_reorder_and_count_rebuild_invalidate_dependents():
    package = _package(3)
    edited = replace_scene_idea(package, 2, "Chứng minh khả năng tiết kiệm thời gian bằng một thao tác hoàn chỉnh")
    edited = build_prompt_package(edited)
    assert "tiết kiệm thời gian" in edited["scenes"][1]["main_idea"]
    regenerated = regenerate_scene_prompt(edited, 2)
    assert regenerated["scene_prompts"][1]["provider_prompt"] == regenerated["scenes"][1]["provider_prompt"]
    reordered = reorder_scenes(regenerated, [2, 1, 3])
    reordered = build_prompt_package(reordered)
    assert [item["scene_index"] for item in reordered["scenes"]] == [1, 2, 3]
    rebuilt = rebuild_for_scene_count(reordered, 5)
    rebuilt = build_prompt_package(rebuilt)
    assert rebuilt["scene_count"] == 5
    assert len(rebuilt["scene_prompts"]) == 5
    assert rebuilt["duration_seconds"] == 40


def test_controlled_pattern_library_uses_only_approved_isolated_patterns(tmp_path: Path):
    payload = {
        "patterns": [
            {
                "pattern_id": "private_unapproved",
                "profile": "product_3d_showcase",
                "scene_counts": [3],
                "version": "9.0.0",
                "evaluation_score": 99,
                "admin_approved": False,
                "source_type": "customer_edit",
                "contains_private_assets": True,
                "status": "active",
            },
            {
                "pattern_id": "approved_curated",
                "profile": "product_3d_showcase",
                "scene_counts": [3],
                "version": "1.1.0",
                "evaluation_score": 1,
                "admin_approved": True,
                "source_type": "curated_default",
                "contains_private_assets": False,
                "status": "active",
            },
        ]
    }
    (tmp_path / "patterns.json").write_text(json.dumps(payload), encoding="utf-8")
    assert [item["pattern_id"] for item in load_approved_patterns(tmp_path)] == ["approved_curated"]
    assert select_approved_pattern("product_3d_showcase", 3, tmp_path)["pattern_id"] == "approved_curated"


def test_planning_and_handoff_source_have_no_provider_job_outbox_or_charge():
    package = _package(3)
    assert package["provider_called"] is False
    assert package["job_created"] is False
    assert package["outbox_created"] is False
    assert package["xu_charged"] == 0
    handler_start = BOT_SOURCE.index("async def handle_video_profile_studio_callback")
    handler_end = BOT_SOURCE.index("async def handle_video_editor_callback", handler_start)
    handler = BOT_SOURCE[handler_start:handler_end]
    assert "provider_router" not in handler
    assert "create_video_project" not in handler
    assert "confirm_video_project_invoice" not in handler
    assert 'callback_data="vproduct|b14_confirm"' in BOT_SOURCE


def test_scene_planner_capability_copy_is_truthful():
    package = _package(20)
    assert package["planner_max_scenes"] == 20
    assert package["planner_theoretical_max_seconds"] == 160
    assert package["live_capability_requires_validation"] is True
    assert "Khả năng tạo thật được kiểm tra" in BOT_SOURCE


def test_continuity_contract_allows_declared_location_and_time_change():
    contract = build_continuity_contract(
        subject="nhân vật chính",
        profile_id="animation_character",
        requirements={"intentional_location_change": True, "intentional_time_jump": True},
    )
    assert contract["intentional_location_change"] is True
    assert contract["intentional_time_jump"] is True
    assert contract["identity"] == ["nhân vật chính"]
