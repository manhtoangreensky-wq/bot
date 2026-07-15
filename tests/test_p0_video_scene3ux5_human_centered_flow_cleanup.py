from __future__ import annotations

from pathlib import Path

import pytest

from services import video_scene3_flow


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    start = BOT_SOURCE.index(f"def {name}(")
    candidates = [
        position
        for marker in ("\ndef ", "\nasync def ")
        if (position := BOT_SOURCE.find(marker, start + 1)) >= 0
    ]
    return BOT_SOURCE[start:min(candidates) if candidates else len(BOT_SOURCE)]


def _state(profile_id: str = "product_3d_showcase", scene_count: int = 3) -> dict:
    state = video_scene3_flow.default_state(
        product_type="video_ai_real",
        subject="Giới thiệu một sản phẩm thật rõ lợi ích và kết quả",
    )
    state = video_scene3_flow.invalidate_scene_outputs(state, scene_count)
    state.update({
        "content_type": video_scene3_flow.content_type_for_profile(profile_id, state),
        "technical_profile": profile_id,
        "context": "Mỗi cảnh giải quyết một ý, mạch kể liên tục và kết thúc tự nhiên",
    })
    state = video_scene3_flow.refresh_suggestions(state)
    state = video_scene3_flow.select_suggestion(state, 1)
    return state


@pytest.mark.parametrize("key", [key for key, _label in video_scene3_flow.PUBLIC_REQUIREMENT_CATEGORIES])
def test_each_public_requirement_has_five_specific_choices_and_optional_image_path(key: str):
    suggestions = video_scene3_flow.requirement_suggestions(_state(), key)
    assert len(suggestions) == 5
    assert len(set(suggestions)) == 5
    assert all("{subject}" not in item and "{profile}" not in item for item in suggestions)
    assert key in video_scene3_flow.REQUIREMENT_UPLOAD_TYPES


def test_all_fourteen_profiles_change_creative_guidance_without_public_taxonomy_leak():
    profile_ids = [key for key, _label in video_scene3_flow.TECHNICAL_PROFILES]
    assert len(profile_ids) == 14
    outputs = {}
    for profile_id in profile_ids:
        suggestions = video_scene3_flow.creative_suggestions(_state(profile_id), "camera")
        assert len(suggestions) == 5
        assert all("Giới thiệu một sản phẩm" in item for item in suggestions)
        outputs[profile_id] = tuple(suggestions)
    assert len(set(outputs.values())) == 14
    assert "CONTENT_TYPES" not in _function_source("video_scene3_profile_keyboard")


def test_content_suggestions_are_item_specific_and_profile_aware():
    product_state = _state("product_3d_showcase")
    architecture_state = _state("architecture_interior")
    for key, _label in video_scene3_flow.PUBLIC_CONTENT_ADDONS:
        product = video_scene3_flow.content_addon_suggestions(product_state, key)
        architecture = video_scene3_flow.content_addon_suggestions(architecture_state, key)
        assert len(product) == 5
        assert len(set(product)) == 5
        assert all(product_state["subject"] in item for item in product)
        assert product != architecture


def test_materials_main_screen_is_compact_and_management_is_separate():
    main_keyboard = _function_source("video_scene3_materials_keyboard")
    manage_keyboard = _function_source("video_scene3_materials_manage_keyboard")
    assert "material_prev" not in main_keyboard
    assert "material_edit" not in main_keyboard
    assert "material_remove" not in main_keyboard
    assert "material_view" in main_keyboard
    assert "material_prev" in manage_keyboard
    assert "material_edit" in manage_keyboard
    assert "material_remove" in manage_keyboard
    assert "material_manage_done" in manage_keyboard
    assert "materials_manage" in _function_source("video_profile_scene1_render")


def test_public_keyboards_remove_duplicate_and_aggregate_controls():
    public_functions = {
        "requirements": _function_source("video_scene3_requirements_keyboard"),
        "materials": _function_source("video_scene3_materials_keyboard"),
        "creative": _function_source("video_scene3_creative_keyboard"),
        "content": _function_source("video_scene3_content_addon_keyboard"),
        "scene_plan": _function_source("video_scene3_scene_plan_keyboard"),
        "review": _function_source("video_scene3_full_review_keyboard"),
        "post": _function_source("video_scene3_post_keyboard"),
    }
    combined = "\n".join(public_functions.values())
    for forbidden in (
        "req_suggest", "ai_image_plan", "layout_ideas", "storyboard_prompt",
        "material|logo", "material|voice_audio", "material|music",
        "creative_quick", "creative_default", "creative_disable_all",
        "content_suggest", "content_accept_suggestion", "content_disable_all",
        "content|logo_safe_zone", "content|watermark_safe_zone", "content|transition_style",
        "regen_scene", "reorder", "change_count", "review_requirements",
        "post_suggest", "post_accept_suggestion", "post_disable_all",
    ):
        assert forbidden not in combined
    assert "vprofile|req|" in public_functions["requirements"]
    assert "vprofile|review_transitions" in public_functions["review"]
    assert "vprofile|post_toggle" in public_functions["post"]
    assert "transitions_skip" in _function_source("video_scene3_transitions_keyboard")


def test_transition_is_one_dedicated_step_for_each_scene_boundary():
    state = video_scene3_flow.build_planning_package(_state(scene_count=4))
    assert video_scene3_flow.CANONICAL_STEPS.index("transitions") == (
        video_scene3_flow.CANONICAL_STEPS.index("video_prompts") + 1
    )
    assert video_scene3_flow.BACK_STEP["transitions"] == "video_prompts"
    assert video_scene3_flow.BACK_STEP["full_review"] == "transitions"
    for boundary in range(1, 4):
        suggestions = video_scene3_flow.transition_suggestions(state, boundary)
        assert len(suggestions) == 5
        state = video_scene3_flow.set_scene_transition(
            state,
            scene_index=boundary,
            transition=suggestions[0],
        )
    scenes = state["plan"]["scenes"]
    assert len(scenes) == 4
    assert all(scenes[index]["transition_out"] for index in range(3))
    assert scenes[-1]["transition_out"] == "kết thúc trọn vẹn"


def test_postproduction_keeps_logo_text_watermark_positions_and_audio_volume_concrete():
    public_keys = {key for key, _label in video_scene3_flow.PUBLIC_POST_ADDONS}
    assert {"logo_image", "watermark_text", "subtitles", "text_overlay"} <= public_keys
    assert video_scene3_flow.AUDIO_POST_ADDONS == {"voice", "dubbing", "music", "sfx"}
    assert video_scene3_flow.AUDIO_VOLUME_LEVELS == (20, 40, 60, 80, 100)
    state = video_scene3_flow.configure_post_asset(_state(), "logo_image", file_id="logo-file")
    state = video_scene3_flow.configure_post_position(state, "logo_image", "top_right")
    state = video_scene3_flow.configure_watermark_text(state, "© Thương hiệu")
    state = video_scene3_flow.configure_post_position(state, "watermark_text", "bottom_right")
    state = video_scene3_flow.configure_post_position(state, "subtitles", "bottom_center")
    for key in video_scene3_flow.AUDIO_POST_ADDONS:
        state = video_scene3_flow.configure_audio_volume(state, key, 60)
    assert state["postproduction_addons"]["logo_image"]["value"]["asset_file_id"] == "logo-file"
    assert state["postproduction_addons"]["watermark_text"]["value"]["text"] == "© Thương hiệu"
    assert state["postproduction_addons"]["subtitles"]["value"]["position"] == "bottom_center"
    assert all(state["postproduction_addons"][key]["value"]["volume_percent"] == 60 for key in video_scene3_flow.AUDIO_POST_ADDONS)


def test_legacy_aggregate_callbacks_are_present_only_as_non_mutating_compatibility_routes():
    handler = _function_source("handle_video_profile_studio_callback")
    assert 'if action == "req_suggest"' in handler
    assert "must not silently enable every requirement" in handler
    assert 'if action == "creative_quick"' in handler
    assert 'if action == "content_suggest"' in handler
    assert 'if action == "post_suggest"' in handler
    assert "Removed aggregate action from public UX" in handler
    assert "cycle_creative_quick_preset(state)" not in handler
    assert 'state["content_addon_suggestion"] =' not in handler
    assert 'state["post_addon_suggestion"] =' not in handler


def test_every_preconfirm_planning_path_stays_side_effect_free():
    state = _state(scene_count=20)
    state = video_scene3_flow.build_planning_package(state)
    state = video_scene3_flow.set_entry(
        state,
        "content_affecting_addons",
        "voiceover",
        "Mỗi cảnh một câu trọn ý",
    )
    state = video_scene3_flow.configure_music_source(state, "create_new")
    state = video_scene3_flow.configure_music_vocal_mode(state, "with_lyrics")
    assert video_scene3_flow.preconfirm_side_effects(state) == {
        "provider_called": False,
        "image_provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "xu_charged": 0,
        "wallet_mutations": 0,
    }
    assert video_scene3_flow.preconfirm_audio_side_effects(state) == {
        "music_provider_calls": 0,
        "voice_provider_calls": 0,
        "files_generated": 0,
    }
