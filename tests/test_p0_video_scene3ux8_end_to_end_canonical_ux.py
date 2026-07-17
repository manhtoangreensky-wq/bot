from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from services import video_idea_catalog, video_idea_store, video_scene3_flow


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _base_state() -> dict:
    state = video_scene3_flow.default_state(
        product_type="video_ai_real",
        subject="Giới thiệu một sản phẩm bằng mạch cảnh liền nhau",
    )
    state["scene_count"] = 3
    state["aspect_ratio"] = "9:16"
    return video_scene3_flow.normalize_state(state)


def test_canonical_order_puts_ratio_after_scene_count_and_quality_near_the_end():
    steps = video_scene3_flow.CANONICAL_STEPS
    assert steps[:7] == (
        "content_mode",
        "scene_count",
        "aspect_ratio",
        "asset_gate",
        "technical_profile",
        "content_choice",
        "character",
    )
    assert steps.index("video_prompts") < steps.index("full_review")
    assert steps.index("full_review") < steps.index("quality")
    assert steps[-2:] == ("final_report", "final_confirmation")
    assert video_scene3_flow.BACK_STEP["aspect_ratio"] == "scene_count"
    assert video_scene3_flow.BACK_STEP["technical_profile"] == "aspect_ratio"


def test_every_unified_field_has_twenty_choices_in_four_non_overlapping_pages():
    for group, fields in (
        ("creative_controls", video_scene3_flow.CREATIVE_CONTROLS),
        ("preservation_requirements", video_scene3_flow.PUBLIC_REQUIREMENT_CATEGORIES),
    ):
        for key, _label in fields:
            state = _base_state()
            catalog = video_scene3_flow.unified_field_suggestion_catalog(state, group, key)
            assert len(catalog) == 20
            pages = []
            for expected_page in range(1, 5):
                assert video_scene3_flow.unified_field_suggestion_page(state, group, key) == expected_page
                page = video_scene3_flow.unified_field_suggestions(state, group, key)
                assert len(page) == 5
                pages.extend(page)
                state = video_scene3_flow.rotate_unified_field_suggestions(state, group, key)
            assert len(set(pages)) == 20
            assert video_scene3_flow.unified_field_suggestion_page(state, group, key) == 1


def test_visual_color_and_identity_color_remain_separate_through_planning():
    state = _base_state()
    state = video_scene3_flow.set_entry(
        state,
        "creative_controls",
        "colors",
        "Ánh sáng điện ảnh xanh lạnh cho bối cảnh",
        enabled=True,
    )
    state = video_scene3_flow.set_entry(
        state,
        "preservation_requirements",
        "colors",
        "Giữ chính xác đỏ nhận diện của sản phẩm",
        enabled=True,
    )
    planned = video_scene3_flow.build_planning_package(state)
    assert planned["creative_controls"]["colors"]["value"].startswith("Ánh sáng")
    assert planned["preservation_requirements"]["colors"]["value"].startswith("Giữ chính xác")
    assert planned["creative_controls"]["colors"] != planned["preservation_requirements"]["colors"]


@pytest.mark.parametrize("key", sorted(video_scene3_flow.AUDIO_POST_ADDONS))
@pytest.mark.parametrize("volume", [0, 20, 100, 200])
def test_audio_levels_are_planning_only_clamped_zero_to_two_hundred(key: str, volume: int):
    updated = video_scene3_flow.configure_audio_volume(_base_state(), key, volume)
    entry = updated["postproduction_addons"][key]
    assert entry["enabled"] is (volume > 0)
    assert entry["value"]["volume_percent"] == volume
    assert entry["value"]["peak_guard"] is True
    assert entry["value"]["clipping_guard"] == "limit_peak_before_mix"
    assert entry["value"]["applied_to_mp4"] is False
    assert video_scene3_flow.preconfirm_side_effects(updated) == {
        "provider_called": False,
        "image_provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "xu_charged": 0,
        "wallet_mutations": 0,
    }


def test_idea_store_adds_aspect_ratio_idempotently_and_round_trips_it():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE video_idea_categories "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, category_key TEXT NOT NULL UNIQUE)"
    )
    conn.execute(
        "CREATE TABLE video_idea_presets "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, preset_key TEXT NOT NULL UNIQUE, category_id INTEGER NOT NULL)"
    )
    video_idea_store.ensure_schema(conn)
    video_idea_store.ensure_schema(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(video_idea_presets)")}
    assert "recommended_aspect_ratio" in columns

    video_idea_store.seed_catalog(
        conn,
        video_idea_catalog.dynamic_category_seeds(),
        video_idea_catalog.dynamic_preset_seeds(),
    )
    row = video_idea_store.preset_by_key(conn, "sales_problem_solution")
    assert row["recommended_aspect_ratio"] == "9:16"
    updated = video_idea_store.update_preset(
        conn,
        row["id"],
        {"recommended_aspect_ratio": "16:9"},
        actor_id="test",
    )
    assert updated["recommended_aspect_ratio"] == "16:9"
    exported = video_idea_store.export_catalog(conn)
    exported_row = next(item for item in exported["presets"] if item["preset_key"] == row["preset_key"])
    assert exported_row["recommended_aspect_ratio"] == "16:9"
    with pytest.raises(ValueError, match="invalid_recommended_aspect_ratio"):
        video_idea_store.update_preset(
            conn,
            row["id"],
            {"recommended_aspect_ratio": "3:2"},
            actor_id="test",
        )


@pytest.mark.parametrize(
    "product_id",
    ["video_trend", "video_ai_real", "script_image_video", "video_reference", "motion_prompt"],
)
def test_idea_preset_keeps_scene_count_ratio_and_exact_product_handoff(product_id: str):
    preset = video_idea_catalog.dynamic_preset_seeds()[0]
    plan = video_idea_catalog.build_plan(preset, scene_count=5)
    handoff = video_idea_catalog.build_scene3_handoff_state(
        plan,
        product_id_override=product_id,
    )
    assert handoff["product_type"] == product_id
    assert handoff["scene_count"] == 5
    assert handoff["aspect_ratio"] == preset["recommended_aspect_ratio"]
    assert handoff["recommended_aspect_ratio"] == preset["recommended_aspect_ratio"]
    assert handoff["step"] == "video_prompts"
    assert len((handoff.get("plan") or {}).get("scenes") or []) == 5
    assert video_scene3_flow.preconfirm_side_effects(handoff) == {
        "provider_called": False,
        "image_provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "xu_charged": 0,
        "wallet_mutations": 0,
    }


def test_storyboard_and_self_shot_keep_their_required_media_contracts():
    preset = video_idea_catalog.dynamic_preset_seeds()[0]
    plan = video_idea_catalog.build_plan(preset, scene_count=2)
    storyboard = video_idea_catalog.build_scene3_handoff_state(
        plan,
        product_id_override="storyboard_prompt",
    )
    assert storyboard["product_type"] == "storyboard_prompt"
    assert storyboard["storyboard_image_required"] is True
    assert storyboard["step"] == "image_source"
    with pytest.raises(ValueError, match="self_shot_source_video_required"):
        video_idea_catalog.build_scene3_handoff_state(
            plan,
            product_id_override="self_shot_scene_change",
        )


def test_idea_and_storyboard_route_truth_reaches_invoice_only_after_scene3():
    matrix = BOT_SOURCE[
        BOT_SOURCE.index("VIDEO_PUBLIC_ROUTE_MATRIX = {"):
        BOT_SOURCE.index("\n\n\ndef video_public_route_for_tool")
    ]
    idea = matrix.split('"video_idea": {', 1)[1].split('"storyboard_prompt": {', 1)[0]
    storyboard = matrix.split('"storyboard_prompt": {', 1)[1].split('"prompt_library": {', 1)[0]
    for route in (idea, storyboard):
        assert '"invoice_reachable": True' in route
        assert '"job_reachable": True' in route


def test_quality_copy_resolves_checked_in_catalog_without_provider_http():
    helper = BOT_SOURCE[
        BOT_SOURCE.index("def video_scene3_public_quality_spec("):
        BOT_SOURCE.index("\nVIDEO_B14_3_CREATIVE_CHOICES =")
    ]
    quality_text = BOT_SOURCE[
        BOT_SOURCE.index("def video_profile_scene1_quality_text("):
        BOT_SOURCE.index("\ndef video_profile_scene1_quality_keyboard(")
    ]
    assert "video_provider_catalog.resolve_product_video_model" in helper
    assert 'required_capability="text_to_video_or_scene_video"' in helper
    assert "requires_concat=True" in helper
    assert "httpx" not in helper.lower()
    assert "requests." not in helper.lower()
    assert "video_scene3_public_quality_spec(price, scene_count=scene_count)" in quality_text


def test_bot_routes_compatible_products_to_one_scene3_entry_and_includes_flow6_special_modes():
    for product_id in (
        "video_trend",
        "video_ai_real",
        "script_image_video",
        "video_reference",
        "motion_prompt",
    ):
        assert f'"vproduct|scene3_start|{product_id}"' in BOT_SOURCE
        assert f'"vproduct|idea_library|{product_id}"' in BOT_SOURCE
    canonical_block = BOT_SOURCE[
        BOT_SOURCE.index("VIDEO_SCENE3_CANONICAL_PUBLIC_PRODUCTS ="):
        BOT_SOURCE.index("VIDEO_SCENE2_LEGACY_PRICE_KEYS =")
    ]
    assert '"frame_video_local"' in canonical_block
    assert '"storyboard_prompt"' in canonical_block
    assert '"self_shot_scene_change"' in canonical_block


def test_product_preset_click_opens_editable_scene_preview_without_provider_side_effects():
    handler = BOT_SOURCE[
        BOT_SOURCE.index("async def handle_video_idea_dynamic_callback"):
        BOT_SOURCE.index("def video_idea_admin_main_text")
    ]
    preset_branch = handler[handler.index('if action == "preset":'):handler.index('if action == "mode":')]
    assert "if origin_product:" in preset_branch
    assert "video_idea_dynamic_build_drafts(state)" in preset_branch
    assert '"idea2_preview"' in preset_branch
    assert "video_idea_dynamic_preview_text(state)" in preset_branch
    assert "provider.submit" not in handler
    assert "create_product_video_job" not in handler
    assert "open_video_finalization" not in handler
