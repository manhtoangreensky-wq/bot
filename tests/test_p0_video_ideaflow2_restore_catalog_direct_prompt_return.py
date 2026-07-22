from __future__ import annotations

import re
from pathlib import Path

from services import video_idea_handoff, video_idea_prompt


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    pattern = re.compile(rf"^(?:async )?def {re.escape(name)}\(", re.MULTILINE)
    match = pattern.search(BOT_SOURCE)
    assert match, f"missing function: {name}"
    next_match = re.search(r"\n(?:async )?def [A-Za-z_]", BOT_SOURCE[match.end() :])
    end = match.end() + next_match.start() if next_match else len(BOT_SOURCE)
    return BOT_SOURCE[match.start() : end]


def _embedded_state(product: str = "video_ai_real") -> tuple[dict, dict]:
    parent = {
        "flow_session_id": f"session-{product}",
        "flow_revision": 7,
        "flow_kind": f"flow-{product}",
        "scene_count": 3,
        "aspect_ratio": "16:9",
        "subject": "Ra mắt máy lọc không khí trong căn hộ nhỏ",
        "idea_return_step": video_idea_handoff.NEXT_STEPS[product],
        "trend_source": {
            "trend_id": "trend-clean-home",
            "title": "Không gian sống sạch đang được quan tâm",
        },
        "reference_assets": {},
    }
    if product in {"self_shot_scene_change", "self_shot_cinematic_transform"}:
        parent["reference_assets"] = {
            "source_media_ref": "telegram-source-video-01",
            "source_media_refs": ["telegram-source-video-01"],
            "items": [{"file_id": "telegram-source-video-01", "media_kind": "video"}],
        }
    if product == "storyboard_prompt":
        parent["storyboard_session_id"] = "storyboard-session-01"

    handoff = video_idea_handoff.build_parent_handoff(
        parent,
        product_id=product,
        return_callback=f"vproduct|idea_back|{product}",
    )
    preset = {
        "id": 108,
        "preset_key": "clean_air_small_home",
        "category_key": "sales",
        "category_id": 4,
        "title": "Ra mắt máy lọc không khí trong căn hộ nhỏ",
        "description": (
            "Theo một gia đình trong căn hộ nhỏ nhận ra bụi mịn, bật máy lọc "
            "và thấy chất lượng không khí cải thiện rõ ràng."
        ),
        "hook": "Một vệt nắng làm lộ bụi mịn trong phòng khách.",
        "objective": "Khép bằng căn phòng trong lành và lợi ích dễ nhận thấy.",
        "scene_arc": "Phát hiện bụi mịn -> Bật máy lọc -> Không khí trong lành",
        "video_prompt_seed": "Giữ máy lọc, căn hộ và gia đình nhất quán qua mọi cảnh.",
        "style": "đời thường cao cấp, ánh sáng tự nhiên, chuyển động camera mềm",
        "recommended_profile_id": "product_demo_realistic",
        "variation_axes": ["camera", "ánh sáng", "nhịp kể", "chuyển tiếp"],
    }
    state = {
        "idea2": True,
        "idea_origin_product": product,
        "idea_category_id": 4,
        "catalog_page": 1,
        "preset_offset": 0,
        "idea_preset_id": 108,
        "idea_preset_version": 2,
        "idea_preset": dict(preset),
        "idea_preset_content": dict(preset),
        "subject": preset["title"],
        "idea_content": preset["description"],
        "scene_count": 3,
        "ratio": "16:9",
        "recommended_aspect_ratio": "16:9",
        "trend_source": dict(parent["trend_source"]),
        "source_video_id": str(handoff.get("source_video_id") or ""),
        "storyboard_session_id": str(parent.get("storyboard_session_id") or ""),
        "idea_parent_handoff": handoff,
    }
    return state, handoff


def test_curated_preset_opens_five_prompts_directly_without_generic_scene_copy() -> None:
    state, handoff = _embedded_state()
    prepared = video_idea_prompt.prepare_prompt_selection(state, handoff)

    assert len(prepared["idea_prompt_candidates"]) == 5
    assert len(prepared["idea_scene_content"]) == 3
    assert prepared["idea_preset_content"]["preset_key"] == "clean_air_small_home"
    assert prepared["idea_scene_content"][0]["preset_stage"] == "Phát hiện bụi mịn"
    assert prepared["idea_scene_content"][-1]["preset_stage"] == "Không khí trong lành"
    joined = "\n".join(row["content"] for row in prepared["idea_scene_content"])
    assert "bụi mịn" in joined
    assert "máy lọc" in joined
    assert "Thể hiện trọn vẹn" not in joined


def test_all_prompt_variants_keep_preset_context_trend_ratio_profile_and_continuity() -> None:
    state, handoff = _embedded_state()
    prepared = video_idea_prompt.prepare_prompt_selection(state, handoff)
    prompts = [item["prompt"] for item in prepared["idea_prompt_candidates"]]

    assert len(set(prompts)) == 5
    for prompt in prompts:
        assert "Ra mắt máy lọc không khí trong căn hộ nhỏ" in prompt
        assert "Không gian sống sạch đang được quan tâm" in prompt
        assert "Tỉ lệ: 16:9" in prompt
        assert "product_demo_realistic" in prompt
        assert "Giữ máy lọc, căn hộ và gia đình nhất quán" in prompt


def test_parent_handoff_round_trip_preserves_real_preset_and_source_context() -> None:
    state, handoff = _embedded_state("self_shot_scene_change")
    selected = video_idea_prompt.select_prompt(
        video_idea_prompt.prepare_prompt_selection(state, handoff),
        2,
    )
    restored = video_idea_handoff.apply_parent_handoff(selected, handoff)

    assert restored["idea_preset_content"]["preset_key"] == "clean_air_small_home"
    assert restored["source_video_id"] == "telegram-source-video-01"
    assert restored["idea_selected_prompt"]
    assert video_idea_prompt.safety_report(restored) == {
        "job": 0,
        "outbox": 0,
        "provider_calls": 0,
        "image_provider_calls": 0,
        "generated_files": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }


def test_embedded_preset_callback_routes_directly_to_prompt_selection() -> None:
    handler = _function_source("handle_video_idea_dynamic_callback")
    start = handler.index('if action == "preset":')
    end_marker = (
        '\n    state = video_idea_dynamic_state(uid)\n'
        '    preset = dict(state.get("idea_preset") or {})'
    )
    end = handler.index(end_marker, start)
    preset_branch = handler[start:end]

    assert "video_idea_prompt.prepare_prompt_selection" in preset_branch
    assert "video_idea_prompt_selection_text" in preset_branch
    assert '"idea_preset_content": dict(preset)' in preset_branch
    assert "video_idea_dynamic_preview_text" not in preset_branch
    assert "video_idea_dynamic_build_drafts" not in preset_branch


def test_prompt_back_and_view_return_to_preset_context_not_intermediate_preview() -> None:
    handler = _function_source("handle_video_idea_prompt_callback")
    detail = _function_source("video_idea_prompt_preset_detail_text")
    preset_list = _function_source("video_idea_prompt_preset_list_payload")

    assert "video_idea_prompt_preset_detail_text" in handler
    assert "video_idea_prompt_preset_list_payload" in handler
    assert "video_idea_dynamic_preview_text" not in handler
    assert "Ý tưởng đã chọn" in detail
    assert "video_idea_dynamic_category_keyboard" in preset_list
    assert "safe_edit_or_send_long_html" in handler
    assert "Có lỗi khi xử lý lệnh" not in handler


def test_storyboard_is_mandatory_while_other_products_return_to_canonical_tail() -> None:
    keyboard = _function_source("video_idea_prompt_selection_keyboard")
    renderer = _function_source("video_idea_render_exact_parent")

    assert '== "storyboard_prompt"' in keyboard
    assert keyboard.count('InlineKeyboardButton("⏭️ Bỏ qua"') == 1
    assert "save_storyboard2_state" in renderer
    assert 'handoff["step"] = "full_review"' in renderer
    assert 'product_id == "script_image_video"' in renderer
    assert '"long_script_mode": True' in renderer
    assert '"chapter_duration_minutes": 5' in renderer


def test_standalone_idea_hub_has_one_complete_explore_entry() -> None:
    idea_menu = _function_source("video_idea_menu_keyboard")
    prompt_library = _function_source("video_prompt_library_keyboard")

    assert idea_menu.count("videoidea|explore") == 1
    for callback in (
        "vpromptlib|start",
        "videoidea|source_start",
        "videoidea|catalog|sales",
        "videoidea|catalog|story",
        "videoidea|kind|custom",
    ):
        assert callback not in idea_menu
    assert "videa|page|1" not in idea_menu
    # Legacy prompt-library routes remain owned by their original handler, but
    # are no longer duplicated on the public Idea Video hub.
    assert "vpromptlib|idea" in prompt_library
    assert "vpromptlib|cinematic" in prompt_library


def test_standalone_explore_uses_complete_catalog_without_scene_preview_continue() -> None:
    handler = _function_source("handle_video_idea_callback")
    explore_start = handler.index('if action == "explore":')
    catalog_start = handler.index('if action == "catalog":', explore_start)
    refresh_start = handler.index('if action == "catalog_refresh":', catalog_start)
    explore_branch = handler[explore_start:catalog_start]
    catalog_branch = handler[catalog_start:refresh_start]

    assert "video_idea_catalog_categories_text" in explore_branch
    assert "video_idea_catalog_categories_keyboard" in explore_branch
    assert "video_idea_dynamic_page_text" not in explore_branch
    assert "video_idea_catalog_options_text" in catalog_branch
    assert "video_idea_catalog_options_keyboard" in catalog_branch
    assert "video_idea_dynamic_preview_text" not in catalog_branch


def test_stale_standalone_dynamic_callbacks_redirect_read_only_to_complete_catalog() -> None:
    handler = _function_source("handle_video_idea_dynamic_callback")
    guard_at = handler.index("if not video_idea_product_lane_origin")
    page_at = handler.index('if action == "page":')
    guard = handler[guard_at:page_at]

    assert guard_at < page_at
    assert "video_idea_catalog_categories_text" in guard
    assert "video_idea_catalog_categories_keyboard" in guard
    assert "restore_developing_video_pending" not in guard
    assert "video_idea_dynamic_preview_text" not in guard


def test_standalone_entry_clears_every_embedded_parent_owner_field() -> None:
    helper = _function_source("clear_video_idea_parent_context")
    handler = _function_source("handle_video_idea_callback")

    for field in (
        "video_idea_flow7_intake",
        "video_idea_parent_handoff",
        "video_idea_origin_product",
        "video_idea_source_media_refs",
        "video_idea_return_callback",
    ):
        assert field in helper
    assert handler.count("clear_video_idea_parent_context(context)") >= 3


def test_prompt_namespace_has_one_owner_and_framevideo_remains_out_of_scope() -> None:
    owner = '("idea_video|", "handle_video_idea_prompt_callback")'
    registration = (
        'CallbackQueryHandler(handle_video_idea_prompt_callback, '
        'pattern=r"^idea_video\\|")'
    )
    assert BOT_SOURCE.count(owner) == 1
    assert BOT_SOURCE.count(registration) == 1
    assert "frame_video_local" not in video_idea_prompt.SUPPORTED_PARENT_PRODUCTS
    assert "frame_video_local" not in video_idea_handoff.NEXT_STEPS
