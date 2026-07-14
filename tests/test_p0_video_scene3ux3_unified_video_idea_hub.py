from __future__ import annotations

import ast
from pathlib import Path

import pytest

from services import video_idea_catalog


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _between(start: str, end: str) -> str:
    left = BOT_SOURCE.index(start)
    right = BOT_SOURCE.index(end, left + len(start))
    return BOT_SOURCE[left:right]


def _literal_assignment(name: str, next_name: str):
    block = _between(f"{name} = ", f"\n\n{next_name}")
    return ast.literal_eval(block.split("=", 1)[1].strip())


def test_public_video_menu_has_new_names_swapped_idea_storyboard_and_full_width_downloader():
    rows = _literal_assignment("VIDEO_PUBLIC_MENU_ROWS", "VIDEO_PUBLIC_ROUTE_MATRIX")
    assert rows == (
        ("video_trend", "video_ai_real"),
        ("script_image_video", "frame_video_local"),
        ("self_shot_scene_change", "multi_scene_film"),
        ("profile_studio", "storyboard_prompt"),
        ("video_idea", "video_local_edit"),
        ("video_downloader",),
        ("main_menu", "video_guide"),
    )
    assert "(\"video_local_edit\", \"prompt_library\")" not in BOT_SOURCE
    matrix = _between("VIDEO_PUBLIC_ROUTE_MATRIX = {", "\n\n\ndef video_public_route_for_tool")
    assert '"label_vi": "🎬 Video dài tập"' in matrix
    assert '"entry_callback": "longvideo|public_guard"' in matrix
    assert '"label_vi": "🎞 Storyboard"' in matrix
    assert '"entry_callback": "videoidea|start"' in matrix


def test_video_ideas_is_the_only_public_entry_for_the_integrated_prompt_vault():
    menu = _between("def video_idea_menu_keyboard", "\n\ndef video_idea_catalog_categories_text")
    assert '"videoidea|explore"' in menu
    assert '"vpromptlib|start"' in menu
    assert '"videoidea|catalog|sales"' in menu
    assert '"videoidea|catalog|story"' in menu
    assert '"videoidea|source_start"' in menu
    assert '"videoidea|kind|custom"' in menu
    prompt_menu = _between("def video_prompt_library_keyboard", "\n\ndef video_prompt_library_guard_text")
    assert '("⬅️ Ý tưởng video" if is_vi else "⬅️ Video ideas", "videoidea|start")' in prompt_menu


def test_catalog_is_broad_profile_aware_and_provider_free():
    status = video_idea_catalog.catalog_status()
    assert status["categories"] == 8
    assert status["ideas"] >= 24
    assert status == {
        "categories": 8,
        "ideas": len(video_idea_catalog.IDEAS),
        "duration_options": [8, 16, 24, 40, 80, 160],
        "provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }
    profile_ids = {item["recommended_profile_id"] for item in video_idea_catalog.IDEAS}
    assert {
        "architecture_walkthrough", "space_renovation", "real_estate_property",
        "cinematic_vfx", "character", "fashion_lookbook", "product_3d_showcase",
        "app_game_demo", "website_saas_demo", "tutorial_explainer", "ugc_social_creator",
    }.issubset(profile_ids)
    source = (ROOT / "services" / "video_idea_catalog.py").read_text(encoding="utf-8").lower()
    for forbidden in ("requests.", "httpx.", "aiohttp.", "create_job(", "debit_wallet", "charge_xu"):
        assert forbidden not in source


def test_each_catalog_category_always_has_five_unique_numbered_choices():
    for category, _label in video_idea_catalog.list_categories():
        first_page = video_idea_catalog.ideas_for_category(category, limit=5)
        second_page = video_idea_catalog.ideas_for_category(category, offset=5, limit=5)
        assert len(first_page) == 5
        assert len({item["idea_id"] for item in first_page}) == 5
        assert {item["idea_id"] for item in first_page}.isdisjoint(
            {item["idea_id"] for item in second_page}
        )


@pytest.mark.parametrize(
    ("duration", "scenes"),
    [(8, 1), (16, 2), (24, 3), (40, 5), (80, 10), (160, 20)],
)
def test_duration_maps_to_exact_eight_second_scene_units(duration: int, scenes: int):
    assert video_idea_catalog.scene_count_for_duration(duration) == scenes
    idea = video_idea_catalog.ideas_for_category("sales", limit=1)[0]
    plan = video_idea_catalog.build_plan(idea, duration_seconds=duration, source_mode="reference_image")
    assert plan["duration_seconds"] == duration
    assert plan["scene_count"] == scenes
    assert plan["source_mode"] == "reference_image"
    assert plan["provider_called"] is False
    assert plan["image_provider_called"] is False
    assert plan["job_created"] is False
    assert plan["outbox_created"] is False
    assert plan["wallet_mutations"] == 0
    assert plan["xu_charged"] == 0


def test_quick_edit_updates_final_image_and_video_prompts_without_mutating_seeds():
    idea = video_idea_catalog.ideas_for_category("story", limit=1)[0]
    original_image = idea["image_prompt_seed"]
    original_video = idea["video_prompt_seed"]
    edited = video_idea_catalog.build_plan(
        idea,
        duration_seconds=24,
        custom_note="quay lúc hoàng hôn, giữ áo màu xanh và kết bằng CTA nhẹ",
    )
    assert edited["image_prompt_seed"] == original_image
    assert edited["video_prompt_seed"] == original_video
    assert "quay lúc hoàng hôn" in edited["image_prompt_final"]
    assert "quay lúc hoàng hôn" in edited["video_prompt_final"]
    edited_again = video_idea_catalog.apply_custom_note(edited, "chuyển sang bình minh")
    assert "chuyển sang bình minh" in edited_again["video_prompt_final"]
    assert "quay lúc hoàng hôn" not in edited_again["video_prompt_final"]


def test_catalog_number_buttons_are_one_compact_row_and_flow_is_editable():
    keyboard = _between("def video_idea_catalog_options_keyboard", "\n\ndef video_idea_catalog_detail_text")
    assert "for index in range(1, 6)" in keyboard
    assert '"videoidea|catalog_refresh"' in keyboard
    assert '"videoidea|kind|custom"' in keyboard
    handler = _between("async def handle_video_idea_callback", "\n\ndef menu_text_main_ai")
    for action in (
        "explore", "catalog", "catalog_refresh", "catalog_choose", "catalog_duration",
        "source_start", "catalog_source", "catalog_edit", "catalog_image_prompt",
        "catalog_video_prompt", "routes", "handoff",
    ):
        assert f'"{action}"' in handler


def test_catalog_save_and_legacy_entry_return_to_the_canonical_idea_hub():
    idea_handler = _between("async def handle_video_idea_callback", "\n\ndef menu_text_main_ai")
    reference_handler = _between("async def handle_video_reference_callback", "\n\nasync def handle_self_scene_ai_callback")
    product_handler = _between("async def handle_video_product_callback", "\n\ndef video_ai_true_text")
    assert 'plan.get("catalog_idea_id")' in idea_handler
    assert "video_idea_catalog_result_keyboard(plan, lang)" in idea_handler
    assert 'plan.get("catalog_idea_id")' not in reference_handler
    assert 'if value == "video_idea":' in product_handler
    assert "video_idea_menu_keyboard(lang)" in product_handler


def test_handoff_preserves_plan_but_has_no_preconfirm_job_provider_or_wallet_side_effect():
    handoff = _between('    if action == "handoff":', '    if action == "kind":')
    assert "selected_scene_count" in handoff
    assert "duration_seconds" in handoff
    assert "image_prompt_seed" in handoff
    assert "video_prompt_seed" in handoff
    assert "provider_called=False" in handoff
    assert "xu_charged=0" in handoff
    for forbidden in (
        "create_product_video_job", "enqueue", "provider.submit", "submit_provider",
        "wallet_debit", "charge_wallet", "deduct_xu",
    ):
        assert forbidden not in handoff


def test_long_video_public_entry_is_development_guard_not_normal_multiscene_flow():
    handler = _between("async def handle_long_video_callback", "\n\nasync def handle_video_idea_callback")
    assert 'action == "public_guard" or not is_admin_user(uid)' in handler
    assert "MULTISCENE_LONG_VIDEO_GUARD_TEXT" in handler
    assert "Video dài tập 1–2 giờ đang phát triển" in BOT_SOURCE
    assert '"multi_scene_film",\n})' not in _between(
        "VIDEO_SCENE2_PUBLIC_PRODUCTS = frozenset({",
        "\n\nVIDEO_SCENE2_LEGACY_PRICE_KEYS",
    )
