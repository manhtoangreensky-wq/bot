from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from services import video_idea_catalog, video_scene3_flow


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
CATALOG_SOURCE = (ROOT / "services" / "video_idea_catalog.py").read_text(encoding="utf-8").lower()


def _between(start: str, end: str) -> str:
    left = BOT_SOURCE.index(start)
    right = BOT_SOURCE.index(end, left + len(start))
    return BOT_SOURCE[left:right]


def test_reference_catalog_has_six_ideas_per_group_and_covers_all_public_profiles():
    counts = Counter(str(item["category"]) for item in video_idea_catalog.IDEAS)
    assert counts == {key: 6 for key, _label in video_idea_catalog.CATEGORIES}
    assert len(video_idea_catalog.IDEAS) == 48
    catalog_profiles = {str(item["recommended_profile_id"]) for item in video_idea_catalog.IDEAS}
    public_profiles = {key for key, _label in video_scene3_flow.TECHNICAL_PROFILES}
    assert len(public_profiles) == 14
    assert catalog_profiles == public_profiles
    for item in video_idea_catalog.IDEAS:
        assert item["reference_only"] is True
        assert item["planning_only"] is True
        assert item["platform_fit"]
        assert item["variation_axes"]
        assert item["scene_arc"]


def test_public_root_removes_duplicate_ad_story_source_and_custom_routes():
    menu = _between("def video_idea_menu_keyboard", "\n\ndef video_idea_catalog_categories_text")
    assert menu.count('"videoidea|explore"') == 1
    for removed in (
        "Ý tưởng quảng cáo", "Ý tưởng điện ảnh", "Từ ảnh/video có sẵn",
        "Tự nhập & chỉnh nhanh", "vpromptlib|start", "videoidea|source_start",
        "videoidea|kind|custom",
    ):
        assert removed not in menu
    categories = _between("def video_idea_catalog_categories_text", "\n\ndef video_idea_catalog_categories_keyboard")
    assert "Ý tưởng quảng cáo và điện ảnh đã nằm trong các nhóm bên dưới" in categories


def test_scene_count_is_selected_directly_without_public_source_screen():
    keyboard = _between("def video_idea_catalog_duration_keyboard", "\n\nVIDEO_IDEA_SOURCE_LABELS")
    assert "SCENE_COUNT_OPTIONS" in keyboard
    assert "catalog_scene_count" in keyboard
    for count in (1, 2, 3, 5, 10, 20):
        assert count in video_idea_catalog.SCENE_COUNT_OPTIONS
    handler = _between("async def handle_video_idea_callback", "\n\ndef menu_text_main_ai")
    canonical = _between('    if action in {"catalog_scene_count", "catalog_duration"}:', '    if action == "source_start":')
    assert 'source_mode="text_prompt"' in canonical
    assert "video_idea_catalog_result_text(plan, lang)" in canonical
    assert "video_idea_source_text" not in canonical
    assert "video_idea_source_keyboard" not in canonical
    assert "legacy_callback_target(action, value, legacy_state)" in handler


@pytest.mark.parametrize("scene_count", [1, 2, 3, 5, 10, 20])
def test_handoff_builds_exact_n_complete_editable_scene_prompts(scene_count: int):
    idea = video_idea_catalog.idea_by_id("story_three_act")
    plan = video_idea_catalog.build_plan(idea, scene_count=scene_count)
    state = video_idea_catalog.build_scene3_handoff_state(plan)
    scenes = list(state["plan"]["scenes"])
    prompts = dict(state["video_prompt_versions"])
    assert state["step"] == "video_prompts"
    assert state["history"] == ["video_idea_result"]
    assert state["idea_return_callback"] == "videoidea|catalog_result"
    assert len(scenes) == scene_count
    assert len(prompts) == scene_count
    assert len({scene["main_idea"] for scene in scenes}) == scene_count
    assert state["plan"]["quality_gate"]["ok"] is True
    assert state["plan"]["semantic_beats_source"] == "curated_idea_catalog"
    for index in range(1, scene_count + 1):
        prompt = prompts[str(index)]["versions"][0]
        for field in (
            "main_idea", "start_state", "action", "development", "end_state",
            "subject", "environment", "camera", "lighting", "transition_in",
            "transition_out", "prompt", "negative_prompt",
        ):
            assert prompt[field]
        assert prompt["duration_seconds"] == 8


def test_twenty_scene_arcs_are_semantically_distinct_for_every_idea_group():
    for category, _label in video_idea_catalog.CATEGORIES:
        idea = video_idea_catalog.ideas_for_category(category, limit=1)[0]
        beats = video_idea_catalog.semantic_beats_for_idea(idea, 20)
        assert len(beats) == 20
        assert len({beat["main_idea"] for beat in beats}) == 20
        assert "conclusion" in beats[-1]["role"]
        assert all("/20" not in beat["main_idea"] for beat in beats)


def test_handoff_is_one_route_and_back_stack_returns_to_the_selected_idea():
    result_keyboard = _between("def video_idea_catalog_result_keyboard", "\n\ndef video_idea_route_choice_text")
    assert result_keyboard.count("videoidea|handoff|") == 1
    assert "Chọn sản phẩm khác" not in result_keyboard
    assert "Chỉnh nhanh" not in result_keyboard
    assert 'callback_data="videoidea|catalog_back_detail"' in result_keyboard
    prompt_keyboard = _between("def video_scene3_prompt_keyboard", "\n\ndef video_scene3_full_review_text")
    assert "idea_return_callback" in prompt_keyboard
    assert "videoidea|catalog_result" in prompt_keyboard
    categories_keyboard = _between("def video_idea_catalog_categories_keyboard", "\n\ndef video_idea_catalog_options")
    options_keyboard = _between("def video_idea_catalog_options_keyboard", "\n\ndef video_idea_catalog_detail_text")
    detail_keyboard = _between("def video_idea_catalog_duration_keyboard", "\n\nVIDEO_IDEA_SOURCE_LABELS")
    assert 'callback_data="videoidea|start"' in categories_keyboard
    assert 'callback_data="videoidea|explore"' in options_keyboard
    assert 'callback_data="videoidea|catalog_back_options"' in detail_keyboard


def test_legacy_ad_and_cinema_buttons_return_to_their_canonical_parent_group():
    assert video_idea_catalog.legacy_callback_target("kind", "ad") == {
        "screen": "options", "category": "sales",
    }
    assert video_idea_catalog.legacy_callback_target("kind", "cinema") == {
        "screen": "options", "category": "story",
    }
    assert video_idea_catalog.legacy_callback_target("cinema_refresh") == {
        "screen": "options", "category": "story",
    }
    assert video_idea_catalog.legacy_callback_target(
        "back_choices", state={"idea_kind": "cinema"}
    ) == {"screen": "options", "category": "story"}
    assert video_idea_catalog.legacy_callback_target(
        "back_choices", state={"idea_kind": "ad"}
    ) == {"screen": "options", "category": "sales"}
    assert video_idea_catalog.legacy_callback_target("source_start") == {
        "screen": "categories", "category": "",
    }


def test_retired_result_actions_cannot_reopen_old_or_paid_paths():
    plan = video_idea_catalog.build_plan(
        video_idea_catalog.idea_by_id("story_three_act"), scene_count=3
    )
    for action in (
        "catalog_source", "routes", "finalization", "frame_video", "render_ai",
        "storyboard", "image_prompts", "video_prompts", "music",
    ):
        target = video_idea_catalog.legacy_callback_target(action, state=plan)
        assert target == {"screen": "result", "category": "story"}
    handler = _between("async def handle_video_idea_callback", "\n\ndef menu_text_main_ai")
    redirect_at = handler.index("legacy_callback_target")
    old_finalization_at = handler.index('if action == "finalization"')
    assert redirect_at < old_finalization_at


def test_scene_prompt_can_be_viewed_copied_edited_restored_and_regenerated_without_submit():
    keyboard = _between("def video_scene3_prompt_keyboard", "\n\ndef video_scene3_full_review_text")
    for action in (
        "prompt_regen", "prompt_edit", "negative_edit", "prompt_restore",
        "prompt_approve", "prompt_copy", "prompt_prev", "prompt_next",
    ):
        assert action in keyboard
    handler = _between("async def handle_video_profile_studio_callback", "\n\nasync def handle_video_editor_callback")
    assert 'action in {"image_prompt_copy", "video_prompt_copy"}' in handler
    copy_block = _between("def video_scene3_prompt_copy_text", "\n\ndef video_scene3_prompt_keyboard")
    assert "Chạm giữ phần câu lệnh để sao chép" in copy_block
    for forbidden in ("provider.submit", "submit_provider", "create_product_video_job", "wallet_debit"):
        assert forbidden not in copy_block


def test_idea_handoff_has_zero_preconfirm_side_effects_and_no_network_client():
    idea = video_idea_catalog.idea_by_id("sales_testimonial_proof")
    state = video_idea_catalog.build_scene3_handoff_state(
        video_idea_catalog.build_plan(idea, scene_count=5)
    )
    assert state["provider_called"] is False
    assert state["image_provider_called"] is False
    assert state["music_provider_calls"] == 0
    assert state["voice_provider_calls"] == 0
    assert state["files_generated"] == 0
    assert state["job_created"] is False
    assert state["outbox_created"] is False
    assert state["wallet_mutations"] == 0
    assert state["xu_charged"] == 0
    for forbidden in (
        "requests.", "httpx.", "aiohttp.", "provider.submit", "create_job(",
        "debit_wallet", "charge_xu", "shopaikey", "key4u",
    ):
        assert forbidden not in CATALOG_SOURCE
