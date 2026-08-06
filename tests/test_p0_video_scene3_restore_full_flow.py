from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

from services import (
    video_edit_state_machine,
    video_flow6,
    video_flow7,
    video_profile_catalog,
    video_scene3_flow,
    video_uifreeze1,
)


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
SCENE3_SOURCE = (ROOT / "services" / "video_scene3_flow.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    declaration = re.search(rf"^(async )?def {re.escape(name)}\(", BOT_SOURCE, re.MULTILINE)
    assert declaration, f"missing function: {name}"
    start = declaration.start()
    next_declaration = re.search(r"^(?:async )?def [A-Za-z_]\w*\(", BOT_SOURCE[declaration.end() :], re.MULTILINE)
    if not next_declaration:
        return BOT_SOURCE[start:]
    end = declaration.end() + next_declaration.start()
    # A decorator belongs to the following top-level handler, not to the
    # isolated source being compiled. Trim it when it sits between functions.
    decorator = BOT_SOURCE.rfind("\n\n@", start, end)
    if decorator >= start:
        end = decorator
    return BOT_SOURCE[start:end]


class _Button:
    def __init__(self, text: str, *, callback_data: str):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


def _keyboard_namespace(*names: str) -> dict:
    namespace = {
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "video_flow7": video_flow7,
        "video_edit_state_machine": video_edit_state_machine,
        "video_scene3_flow": video_scene3_flow,
        "video_uifreeze1": video_uifreeze1,
        "video_ai_edit_entry_back": lambda *_args, **_kwargs: "videoedit|ai",
        "local_video_studio_public_enabled": lambda: False,
        "ui_text": lambda _lang, key: "⬅️ Quay lại" if key == "common.back" else "🏠 Menu chính",
        "VIDEO_B14_2_QUALITY_OPTIONS": (200, 300, 400, 500, 600, 800, 1000, 1200, 1500),
        "VIDEO_SCENE3_CANONICAL_PUBLIC_PRODUCTS": frozenset({
            "video_trend", "video_ai_real", "script_image_video", "video_reference", "motion_prompt",
        }),
        "video_provider_catalog": SimpleNamespace(
            resolve_product_video_model=lambda **_kwargs: {
                "ok": True,
                "provider": "fixture_video",
                "model": "fixture_scene_model",
            },
            model_metadata_from_resolution=lambda resolution: {
                "provider": resolution.get("provider"),
                "model": resolution.get("model"),
            },
        ),
        "video_b14_package_button_label": lambda value: f"{value} Xu",
        "safe_int": lambda value, default=0: int(value) if str(value or "").isdigit() else default,
        "env_flag": lambda _name, default="0": str(default).strip().lower() in {"1", "true", "yes", "on"},
        "normalize_user_language": lambda lang: str(lang or "vi"),
        "VIDEO_PRODUCT_REGISTRY": {
            product_id: {"parent_menu_callback": "menu|main_video"}
            for product_id in (
                "video_trend", "video_ai_real", "script_image_video", "self_shot_scene_change",
                "multi_scene_film", "video_idea", "storyboard_prompt", "video_reference", "audio_addons",
            )
        },
        "re": re,
        "VIDEO_AI_EDIT_PRESERVE_LABELS": tuple((f"field_{index}", f"Mục {index}") for index in range(10)),
        "VIDEO_NUMBER_BUTTON_LABELS": ("1", "2", "3", "4", "5"),
        "VIDEO_MICROFLOW_MEDIA_INPUT_STEPS": set(),
        "VIDEO_B14_3_PROFILE_BUTTONS": tuple((f"Loại {index}", f"type_{index}") for index in range(12)),
        "VIDEO_B14_3_CREATIVE_CHOICES": {
            "visual_style": tuple((f"Phong cách {index}", f"style_{index}") for index in range(5)),
        },
        "VIDEO_B14_2_SCENE_OPTIONS": (1, 2, 3, 5, 10, 20),
        "PRODUCT_VIDEO_TRIAL_FIXED_SCENE_COUNT": 1,
        "TASK3D_COLOR_MOOD_SUGGESTIONS": tuple((f"color_{index}", f"Màu {index}") for index in range(4)),
        "TASK3D_SUBJECT_SUGGESTIONS": tuple((f"subject_{index}", f"Chủ thể {index}") for index in range(4)),
        "TASK3D_SCENE_IDEA_SUGGESTIONS": tuple((f"scene_{index}", f"Bối cảnh {index}") for index in range(4)),
        "TASK3D_CAMERA_SUGGESTIONS": tuple((f"camera_{index}", f"Góc máy {index}") for index in range(4)),
        "TASK3D_PACE_SUGGESTIONS": tuple((f"pace_{index}", f"Nhịp {index}") for index in range(4)),
        "TASK3D_MOTION_SUGGESTIONS": tuple((f"motion_{index}", f"Chuyển động {index}") for index in range(5)),
        "TASK3D_VIDEO_PROMPT_OUTPUT_PRODUCTS": {"video_ai_real", "video_trend"},
        "TASK3D_SAMPLE_TOPICS": {},
        "profile_router": SimpleNamespace(STUDIO_PROFILE_OPTIONS=[
            {"selection_id": f"profile_{index}", "label_vi": f"Mẫu {index}"}
            for index in range(5)
        ]),
        "architecture_profile_router": SimpleNamespace(ARCHITECTURE_PROFILE_MENU=[
            (f"architecture_{index}", f"Kiến trúc {index}") for index in range(6)
        ] + [("auto", "Tự động đề xuất")]),
    }
    for name in names:
        source = "from __future__ import annotations\n" + _function_source(name)
        exec(compile(source, f"<scene3-keyboard:{name}>", "exec"), namespace)
    return namespace


def _state(scene_count: int = 3) -> dict:
    state = video_scene3_flow.default_state(
        product_type="video_ai_real",
        subject="Giới thiệu căn hộ nhiều ánh sáng tự nhiên",
    )
    state = video_scene3_flow.invalidate_scene_outputs(state, scene_count)
    state.update({
        "content_type": "real_estate_fpv",
        "technical_profile": "architecture_interior",
        "context": "Đi từ cửa vào phòng khách, bếp, phòng ngủ và ban công",
    })
    state = video_scene3_flow.refresh_suggestions(state)
    state = video_scene3_flow.select_suggestion(state, 1)
    for key, value in video_scene3_flow.creative_defaults(state).items():
        state = video_scene3_flow.set_entry(state, "creative_controls", key, value)
    return state


def _planned(scene_count: int = 3) -> dict:
    state = video_scene3_flow.set_image_source_mode(_state(scene_count), "create")
    return video_scene3_flow.build_planning_package(state)


def test_scene3_canonical_order_and_back_stack_are_complete():
    assert video_scene3_flow.CANONICAL_STEPS == (
        "content_mode", "scene_count", "aspect_ratio", "asset_gate", "technical_profile", "content_choice",
        "character", "image_source", "image_assets", "creative_controls", "requirements", "audio_plan",
        "scene_plan", "image_prompts", "video_prompts", "full_review", "quality", "final_report",
        "final_confirmation",
    )
    routed = video_scene3_flow.set_image_source_mode(video_scene3_flow.default_state(), "create")
    routed["asset_requirement"] = "images_required"
    for previous, current in zip(video_scene3_flow.CANONICAL_STEPS, video_scene3_flow.CANONICAL_STEPS[1:]):
        assert video_scene3_flow.canonical_back_step({**routed, "step": current}) == previous
    assert video_scene3_flow.BACK_STEP["content_mode"] == "menu"


def test_scene3_keeps_content_taxonomy_internal_and_exposes_fourteen_profiles():
    assert len(video_scene3_flow.CONTENT_TYPES) == 12
    assert len({item["id"] for item in video_scene3_flow.CONTENT_TYPES}) == 12
    assert len(video_scene3_flow.TECHNICAL_PROFILES) == 14
    assert len({key for key, _label in video_scene3_flow.TECHNICAL_PROFILES}) == 14
    assert video_scene3_flow.CONTENT_TYPES is not video_scene3_flow.TECHNICAL_PROFILES
    assert isinstance(video_scene3_flow.CONTENT_TYPES[0], dict)
    assert isinstance(video_scene3_flow.TECHNICAL_PROFILES[0], tuple)
    state = video_scene3_flow.default_state()
    state.update({"content_type": "fashion_lookbook", "technical_profile": "fashion_lookbook"})
    assert state["content_type"] == "fashion_lookbook"
    assert state["technical_profile"] == "fashion_lookbook"
    assert "content_type" not in video_scene3_flow.CANONICAL_STEPS
    assert video_scene3_flow.content_type_for_profile("fashion_lookbook", state) == "fashion_lookbook"


def test_content_type_and_profile_suggestions_are_deterministic_and_optional():
    state = _state(2)
    assert video_scene3_flow.suggested_content_type(state) == "real_estate_fpv"
    assert video_scene3_flow.suggested_technical_profile("real_estate_fpv") == "real_estate_property"
    relevant = video_scene3_flow.technical_profiles_for_content("real_estate_fpv")
    assert 2 <= len(relevant) < len(video_scene3_flow.TECHNICAL_PROFILES)
    assert len(video_scene3_flow.technical_profiles_for_content("real_estate_fpv", show_all=True)) == 14
    assert video_scene3_flow.suggested_technical_profile("real_estate_fpv", 1) != "real_estate_property"
    assert video_scene3_flow.technical_profile_label("") == "Không dùng mẫu chuyên ngành"
    assert video_scene3_flow.technical_profile_label("unknown_enum") == "Mẫu chuyên ngành chưa xác định"


def test_exactly_five_refreshable_restorable_suggestions():
    state = _state(5)
    first = deepcopy(state["suggestions"])
    assert len(first) == 5
    assert len({item["title"] for item in first}) == 5
    refreshed = video_scene3_flow.refresh_suggestions(state)
    assert len(refreshed["suggestions"]) == 5
    assert refreshed["suggestions"] != first
    restored = video_scene3_flow.restore_suggestions(refreshed)
    assert restored["suggestions"] == first


@pytest.mark.parametrize("scene_count", [1, 3, 20])
def test_exact_n_semantic_scenes_image_plans_and_video_prompts(scene_count: int):
    state = _planned(scene_count)
    counts = video_scene3_flow.scene_contract_counts(state)
    assert counts == {
        "expected": scene_count,
        "scenes": scene_count,
        "image_strategies": scene_count,
        "image_prompts": scene_count,
        "image_prompts_expected": scene_count,
        "video_prompts": scene_count,
    }
    for index, scene in enumerate(state["plan"]["scenes"], 1):
        assert scene["scene_index"] == index
        assert scene["main_idea"]
        assert scene["start_state"]
        assert scene["primary_action"]
        assert scene["completion_state"]
        assert scene["semantic_complete"] is True
        public_prompt = video_scene3_flow.active_prompt(state["video_prompt_versions"][str(index)])
        assert public_prompt["prompt"].startswith(f"Cảnh {index}.")
        assert "Scene " not in public_prompt["prompt"]
        assert public_prompt["provider_prompt"]
        assert public_prompt["negative_prompt"].startswith("không đổi nhận diện")


def test_prompt_edit_regenerate_restore_and_scene_isolation():
    state = _planned(3)
    untouched = deepcopy(state["video_prompt_versions"]["2"])
    first = video_scene3_flow.active_prompt(state["video_prompt_versions"]["1"])
    edited = video_scene3_flow.update_prompt(
        state,
        kind="video",
        scene_index=1,
        field="prompt",
        value="Cảnh 1 mở đầu và kết thúc hành động trọn vẹn.",
    )
    assert edited["video_prompt_versions"]["1"]["active_version"] == 2
    assert edited["video_prompt_versions"]["2"] == untouched
    regenerated = video_scene3_flow.regenerate_prompt(edited, kind="video", scene_index=1)
    assert regenerated["video_prompt_versions"]["1"]["active_version"] == 3
    restored = video_scene3_flow.restore_prompt(regenerated, kind="video", scene_index=1)
    assert restored["video_prompt_versions"]["1"]["active_version"] == 2
    restored_again = video_scene3_flow.restore_prompt(restored, kind="video", scene_index=1)
    assert video_scene3_flow.active_prompt(restored_again["video_prompt_versions"]["1"])["prompt"] == first["prompt"]
    assert restored_again["video_prompt_versions"]["2"] == untouched


def test_scene_count_change_invalidates_plans_but_preserves_uploaded_assets():
    state = _planned(3)
    state["reference_assets"] = {
        "items": [{"type": "logo", "file_id": "telegram-logo", "provider_uploaded": False}]
    }
    state["assets"] = deepcopy(state["reference_assets"])
    state["voice_timing_by_scene"] = {"1": {"start_seconds": 0, "end_seconds": 8}}
    state["cta_placement_by_scene"] = {"3": {"placement": "cuối cảnh"}}
    state["duration_estimate"] = {"total_seconds": 24}
    state["price_estimate"] = {"total_xu": 900}
    changed = video_scene3_flow.invalidate_scene_outputs(state, 5)
    assert changed["scene_count"] == 5
    assert changed["plan"] == {}
    assert changed["image_strategy_per_scene"] == {}
    assert changed["image_prompt_versions"] == {}
    assert changed["video_prompt_versions"] == {}
    assert changed["transition_plan"] == []
    assert changed["voice_timing_by_scene"] == {}
    assert changed["cta_placement_by_scene"] == {}
    assert changed["duration_estimate"] == {}
    assert changed["price_estimate"] == {}
    assert changed["quality_xu"] == 0
    assert changed["reference_assets"]["items"][0]["file_id"] == "telegram-logo"


def test_content_and_post_addons_default_off_and_support_history():
    state = video_scene3_flow.default_state()
    assert all(not item["enabled"] for item in state["content_affecting_addons"].values())
    assert all(not item["enabled"] for item in state["postproduction_addons"].values())
    added = video_scene3_flow.set_entry(state, "postproduction_addons", "logo_image", video_scene3_flow.post_addon_default("logo_image"))
    assert added["postproduction_addons"]["logo_image"]["enabled"] is True
    assert added["postproduction_addons"]["logo_image"]["value"]["width_ratio"] == 0.12
    assert added["postproduction_addons"]["logo_image"]["value"]["preserve_aspect_ratio"] is True
    removed = video_scene3_flow.remove_entry(added, "postproduction_addons", "logo_image")
    assert removed["postproduction_addons"]["logo_image"]["enabled"] is False
    restored = video_scene3_flow.restore_entry(removed, "postproduction_addons", "logo_image")
    assert restored["postproduction_addons"]["logo_image"]["enabled"] is True


def test_logo_reference_has_nine_positions_safe_size_and_never_claims_mp4_overlay():
    assert len(video_scene3_flow.LOGO_POSITIONS) == 9
    state = video_scene3_flow.configure_logo_reference(_state(2), position="top_right", enabled=True)
    config = state["reference_assets"]["logo_config"]
    assert config == {
        "logo_enabled": True,
        "logo_position": "top_right",
        "logo_width_ratio": 0.12,
        "logo_max_width_ratio": 0.18,
        "logo_margin_x_ratio": 0.04,
        "logo_margin_y_ratio": 0.035,
        "logo_preserve_aspect_ratio": True,
        "applied_to_mp4": False,
    }
    assert video_scene3_flow.logo_position_label("top_right") == "↗️ Trên phải"


def test_legacy_voice_is_migrated_into_one_canonical_dubbing_owner():
    assert "voice" not in dict(video_scene3_flow.PUBLIC_POST_ADDONS)
    assert "dubbing" not in dict(video_scene3_flow.PUBLIC_POST_ADDONS)
    assert "dubbing" in dict(video_scene3_flow.PUBLIC_CONFIGURABLE_POST_ADDONS)
    assert "dubbing" in dict(video_scene3_flow.AUDIO_PLANNING_ADDONS)
    state = video_scene3_flow.default_state()
    state["postproduction_addons"]["voice"] = {
        "enabled": True,
        "value": {"voice_type": "female", "script_note": "Lời giới thiệu"},
        "history": [],
    }
    migrated = video_scene3_flow.normalize_state(state)
    dubbing = migrated["postproduction_addons"]["dubbing"]
    assert dubbing["enabled"] is True
    assert dubbing["value"]["voice_type"] == "female"
    assert dubbing["value"]["dialogue_text"] == "Lời giới thiệu"
    assert dubbing["value"]["applied_to_mp4"] is False
    dubbing_languages = {preset[1]["language"] for preset in video_scene3_flow.POST_ADDON_PRESETS["dubbing"]}
    assert dubbing_languages == {"vi", "en", "ja", "ko", "zh", "other"}


def test_quick_creative_presets_cycle_without_external_generation():
    state = _state(2)
    first = video_scene3_flow.cycle_creative_quick_preset(state)
    second = video_scene3_flow.cycle_creative_quick_preset(first)
    assert first["creative_quick_name"] == "Chân thật tự nhiên"
    assert second["creative_quick_name"] == "Điện ảnh cảm xúc"
    assert first["creative_quick_index"] == 0
    assert second["creative_quick_index"] == 1
    assert video_scene3_flow.preconfirm_side_effects(second)["provider_called"] is False


def test_transition_change_and_restore_are_scene_isolated_and_version_safe():
    state = _planned(3)
    original_scene_3 = deepcopy(state["plan"]["scenes"][2])
    original_prompt_3 = deepcopy(state["video_prompt_versions"]["3"])
    original_transition = state["plan"]["scenes"][0]["transition_out"]
    changed = video_scene3_flow.set_scene_transition(state, scene_index=1, transition="match cut")
    assert changed["plan"]["scenes"][0]["transition_out"] == "match cut"
    assert changed["plan"]["scenes"][1]["transition_in"] == "match cut"
    assert changed["plan"]["scenes"][2] == original_scene_3
    assert changed["video_prompt_versions"]["3"] == original_prompt_3
    restored = video_scene3_flow.restore_scene_transition(changed, scene_index=1)
    assert restored["plan"]["scenes"][0]["transition_out"] == original_transition


def test_content_addons_create_scene_dependent_timing_only_when_plan_is_built():
    state = _state(3)
    state = video_scene3_flow.configure_voice_choice(state, "default_female")
    state = video_scene3_flow.upsert_automatic_text_item(
        state,
        item_type="cta",
        text="Xem thêm thông tin",
        scene_scope="3",
        timing="scene_end",
    )
    planned = video_scene3_flow.build_planning_package(state)
    assert list(planned["voice_timing_by_scene"]) == ["1", "2", "3"]
    assert planned["cta_placement_by_scene"] == {"3": {"placement": "cuối cảnh", "approved": False}}
    assert planned["duration_estimate"] == {"scene_count": 3, "seconds_per_scene": 8, "total_seconds": 24}
    assert planned["price_estimate"] == {}


def test_post_addon_suggestion_does_not_enable_or_execute_any_addon():
    state = _state(2)
    state["reference_assets"] = {"items": [{"type": "logo", "file_id": "logo-1"}]}
    state = video_scene3_flow.set_entry(state, "content_affecting_addons", "captions", "Theo lời dẫn")
    suggestions = video_scene3_flow.post_addon_suggestions(state)
    assert suggestions == ["logo_image"]
    assert all(not item["enabled"] for item in state["postproduction_addons"].values())
    assert all(not config.get("applied_to_mp4") for config in video_scene3_flow.POST_ADDON_DEFAULTS.values() if "applied_to_mp4" in config)


def test_transitions_are_public_vietnamese_with_explanations():
    for internal_name in video_scene3_flow.TRANSITIONS:
        public = video_scene3_flow.transition_public(internal_name)
        assert public["label"]
        assert public["description"]
        assert public["label"] != internal_name or internal_name in {"mở trực tiếp", "kết thúc trọn vẹn"}


def test_public_planning_copy_hides_internal_enums():
    public = video_scene3_flow.public_planning_text(
        "character_setup (opening), development, resolution, cut on action"
    )
    for internal in ("character_setup", "opening", "development", "resolution", "cut on action"):
        assert internal not in public
    assert "giới thiệu nhân vật" in public
    assert "hoàn tất câu chuyện" in public


def test_adaptive_keyboard_contract_allows_one_to_five_and_rejects_invalid_rows():
    rows = video_scene3_flow.validate_adaptive_rows([
        [("Một", "scene3|one")],
        [(str(index), f"scene3|pick|{index}") for index in range(1, 6)],
        [("Quay lại", "scene3|back"), ("Menu chính", "scene3|main")],
    ])
    assert [len(row) for row in rows] == [1, 5, 2]
    with pytest.raises(ValueError):
        video_scene3_flow.validate_adaptive_rows([[]])
    with pytest.raises(ValueError):
        video_scene3_flow.validate_adaptive_rows([
            [(str(index), f"scene3|pick|{index}") for index in range(1, 7)]
        ])
    with pytest.raises(ValueError):
        video_scene3_flow.validate_adaptive_rows([
            [("Một", "scene3|same"), ("Hai", "scene3|two")],
            [("Ba", "scene3|same"), ("Bốn", "scene3|four")],
        ])


@pytest.mark.parametrize(
    ("suggestion_count", "requires_source_info_fallback"),
    [(0, True), (1, False), (2, True), (3, False), (4, True), (5, False)],
)
def test_video_ai_edit_suggestions_keyboard_pairs_every_row_with_odd_count_fallback(
    suggestion_count: int,
    requires_source_info_fallback: bool,
) -> None:
    namespace = _keyboard_namespace(
        "video_scene3_keyboard",
        "video_ai_edit_suggestions_keyboard",
    )
    markup = namespace["video_ai_edit_suggestions_keyboard"]({
        "ai_suggestions": [
            {"title": f"Gợi ý {index + 1}"}
            for index in range(suggestion_count)
        ],
    })
    callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    ]

    assert all(len(row) == 2 for row in markup.inline_keyboard)
    assert len(callbacks) == len(set(callbacks))
    assert callbacks.count("videoedit|source_info") == int(
        requires_source_info_fallback
    )


def test_actual_scene3_and_local_editor_keyboards_have_adaptive_unique_real_buttons():
    scene3_names = (
        "video_scene3_keyboard",
        "video_scene3_nav_rows",
        "video_scene3_field_editor_keyboard",
        "video_scene3_profile_keyboard",
        "video_scene3_suggestion_keyboard",
        "video_scene3_requirements_keyboard",
        "video_scene3_materials_keyboard",
        "video_scene3_creative_keyboard",
        "video_scene3_creative_detail_keyboard",
        "video_scene3_creative_suggestions_keyboard",
        "video_scene3_audio_plan_keyboard",
        "video_scene3_content_addon_keyboard",
        "video_scene3_content_detail_keyboard",
        "video_scene3_content_suggestions_keyboard",
        "video_scene3_content_position_keyboard",
        "video_scene3_scene_plan_keyboard",
        "video_scene3_scene_detail_keyboard",
        "video_scene3_transition_keyboard",
        "video_scene3_image_source_keyboard",
        "video_scene3_image_strategy_keyboard",
        "video_scene3_prompt_keyboard",
        "video_scene3_full_review_keyboard",
        "video_scene3_post_keyboard",
        "video_scene3_post_detail_keyboard",
        "video_scene3_post_position_keyboard",
        "video_scene3_logo_position_keyboard",
        "video_scene3_aspect_keyboard",
        "video_scene3_quality_keyboard",
        "video_scene3_quality_guide_keyboard",
        "video_scene3_final_keyboard",
        "video_scene3_invoice_keyboard",
        "video_edit_hub_keyboard",
        "video_scene3_canonical_entry_keyboard",
        "task3d_product_intro_keyboard",
        "video_ai_edit_intro_keyboard",
        "video_ai_edit_upload_keyboard",
        "video_ai_edit_source_summary_keyboard",
        "video_ai_edit_intent_keyboard",
        "video_ai_edit_suggestions_keyboard",
        "video_ai_edit_settings_keyboard",
        "video_ai_edit_intensity_keyboard",
        "video_ai_edit_preserve_keyboard",
        "video_ai_edit_aspect_keyboard",
        "video_ai_edit_duration_keyboard",
        "video_ai_edit_text_keyboard",
        "video_ai_edit_motion_keyboard",
        "video_ai_edit_prompt_keyboard",
        "video_ai_edit_invoice_keyboard",
        "video_ai_edit_status_keyboard",
    )
    local_names = (
        "video_local_tool_keyboard",
        "video_local_upload_keyboard",
        "video_local_source_summary_keyboard",
        "video_local_manual_options_keyboard",
        "video_local_split_options_keyboard",
        "video_local_choice_keyboard",
        "video_local_input_keyboard",
        "video_local_custom_input_keyboard",
        "video_local_concat_keyboard",
        "video_local_logo_keyboard",
        "video_local_confirmation_keyboard",
    )
    namespace = _keyboard_namespace(*(scene3_names + local_names))
    state = _planned(2)
    state["show_all_technical_profiles"] = True
    markups = [
        namespace["video_scene3_profile_keyboard"](state),
        namespace["video_scene3_suggestion_keyboard"](),
        namespace["video_scene3_requirements_keyboard"](state),
        namespace["video_scene3_materials_keyboard"](),
        namespace["video_scene3_creative_keyboard"](state),
        namespace["video_scene3_creative_detail_keyboard"]({**state, "active_creative": "visual_style"}),
        namespace["video_scene3_creative_suggestions_keyboard"]({**state, "active_creative": "visual_style"}),
        namespace["video_scene3_content_addon_keyboard"](state),
        namespace["video_scene3_content_detail_keyboard"]({**state, "active_content_addon": "captions"}),
        namespace["video_scene3_content_suggestions_keyboard"]({**state, "active_content_addon": "captions"}),
        namespace["video_scene3_content_position_keyboard"](),
        namespace["video_scene3_scene_plan_keyboard"](),
        namespace["video_scene3_scene_detail_keyboard"](),
        namespace["video_scene3_transition_keyboard"](state),
        namespace["video_scene3_image_strategy_keyboard"](),
        namespace["video_scene3_prompt_keyboard"]("image"),
        namespace["video_scene3_prompt_keyboard"]("video"),
        namespace["video_scene3_full_review_keyboard"](state),
        namespace["video_scene3_post_keyboard"](state),
        namespace["video_scene3_post_detail_keyboard"]({**state, "active_post_addon": "voice"}),
        namespace["video_scene3_post_position_keyboard"](),
        namespace["video_scene3_logo_position_keyboard"](),
        namespace["video_scene3_aspect_keyboard"](),
        namespace["video_scene3_quality_keyboard"](),
        namespace["video_scene3_quality_guide_keyboard"](),
        namespace["video_scene3_final_keyboard"](),
        namespace["video_scene3_invoice_keyboard"](),
        namespace["video_edit_hub_keyboard"](),
        *[
            namespace["task3d_product_intro_keyboard"](product_id)
            for product_id in (
                "video_trend", "video_ai_real", "script_image_video", "self_shot_scene_change",
                "multi_scene_film", "video_idea", "storyboard_prompt", "video_reference", "audio_addons",
            )
        ],
        namespace["video_ai_edit_intro_keyboard"](),
        namespace["video_ai_edit_upload_keyboard"](),
        namespace["video_ai_edit_source_summary_keyboard"](),
        namespace["video_ai_edit_intent_keyboard"](),
        namespace["video_ai_edit_suggestions_keyboard"]({"ai_suggestions": []}),
        namespace["video_ai_edit_suggestions_keyboard"]({
            "ai_suggestions": [{"title": f"Gợi ý {index}"} for index in range(1, 6)]
        }),
        namespace["video_ai_edit_settings_keyboard"](),
        namespace["video_ai_edit_intensity_keyboard"](),
        namespace["video_ai_edit_preserve_keyboard"]({}),
        namespace["video_ai_edit_aspect_keyboard"](),
        namespace["video_ai_edit_duration_keyboard"]({"source_metadata": {"duration": 18}}),
        namespace["video_ai_edit_text_keyboard"](),
        namespace["video_ai_edit_motion_keyboard"](),
        namespace["video_ai_edit_prompt_keyboard"](),
        namespace["video_ai_edit_invoice_keyboard"]({"ready": True}),
        namespace["video_ai_edit_invoice_keyboard"]({"ready": False}),
        namespace["video_ai_edit_status_keyboard"](123),
        namespace["video_local_tool_keyboard"]("manual"),
        namespace["video_local_upload_keyboard"]("manual"),
        namespace["video_local_source_summary_keyboard"]("manual"),
        namespace["video_local_manual_options_keyboard"](),
        namespace["video_local_split_options_keyboard"]({}),
        namespace["video_local_split_options_keyboard"]({"split_ranges": [{"start_ms": 0, "end_ms": 8000}]}),
        namespace["video_local_input_keyboard"]("manual"),
        namespace["video_local_custom_input_keyboard"](False),
        namespace["video_local_custom_input_keyboard"](True),
        namespace["video_local_concat_keyboard"](),
        namespace["video_local_logo_keyboard"](),
        namespace["video_local_confirmation_keyboard"]("manual"),
        namespace["video_local_confirmation_keyboard"]("split"),
    ]
    for kind in ("aspect", "resolution", "rotation", "flip", "speed", "volume", "color_preset"):
        markups.append(namespace["video_local_choice_keyboard"](kind))

    for markup_index, markup in enumerate(markups):
        callbacks = []
        for row in markup.inline_keyboard:
            assert 1 <= len(row) <= 5, (markup_index, [button.text for button in row])
            for button in row:
                assert str(button.text).strip()
                assert str(button.callback_data).strip()
                callbacks.append(button.callback_data)
        assert len(callbacks) == len(set(callbacks)), (markup_index, callbacks)

    suggestion_markup = namespace["video_scene3_suggestion_keyboard"]()
    assert [[button.text for button in row] for row in suggestion_markup.inline_keyboard[:3]] == [
        ["1", "2", "3", "4", "5"],
        ["🔄 Đổi 5 gợi ý", "✍️ Tự nhập nội dung"],
        ["⬅️ Quay lại", "🏠 Menu chính"],
    ]
    assert sum(
        "|suggest|" in str(button.callback_data)
        for row in suggestion_markup.inline_keyboard
        for button in row
    ) == 5
    creative_markup = namespace["video_scene3_creative_suggestions_keyboard"]({**state, "active_creative": "visual_style"})
    assert [button.text for button in creative_markup.inline_keyboard[0]] == ["1", "2", "3", "4", "5"]
    content_markup = namespace["video_scene3_content_suggestions_keyboard"]({**state, "active_content_addon": "captions"})
    assert [button.text for button in content_markup.inline_keyboard[0]] == ["1", "2", "3", "4", "5"]

    microflow_namespace = _keyboard_namespace(
        "video_scene3_keyboard",
        "video_microflow_option_display_limit",
        "video_microflow_select_label",
        "video_microflow_options_keyboard",
    )
    microflow_markup = microflow_namespace["video_microflow_options_keyboard"](
        "video_ai_real",
        options=[{}] * 5,
        kind="prompt",
    )
    assert [[button.text for button in row] for row in microflow_markup.inline_keyboard[:3]] == [
        ["1", "2"],
        ["3", "4"],
        ["5", "🔄 Gợi ý lại"],
    ]
    assert [
        button.callback_data
        for row in microflow_markup.inline_keyboard[:3]
        for button in row
        if button.callback_data.startswith("vproduct|microflow_choose|")
    ] == [f"vproduct|microflow_choose|{index}" for index in range(5)]
    assert [[button.text for button in row] for row in microflow_markup.inline_keyboard[3:5]] == [
        ["✍️ Sửa nội dung", "📖 Xem hướng dẫn"],
        ["⬅️ Quay lại", "🏠 Menu chính"],
    ]

    profile_markup = namespace["video_scene3_profile_keyboard"](state)
    public_profile_callbacks = [
        button.callback_data
        for row in profile_markup.inline_keyboard
        for button in row
        if button.callback_data.startswith("vprofile|profile_select|")
    ]
    assert len(public_profile_callbacks) == 10
    assert len(public_profile_callbacks) == len(set(public_profile_callbacks))
    assert len(video_profile_catalog.PROFILE_SEEDS) == 32
    assert "vprofile|profile_none" not in {
        button.callback_data for row in profile_markup.inline_keyboard for button in row
    }

    optional_callbacks = set()
    for markup in (
        namespace["video_scene3_suggestion_keyboard"](),
        namespace["video_scene3_requirements_keyboard"](state),
        namespace["video_scene3_materials_keyboard"](),
        namespace["video_scene3_creative_keyboard"](state),
        namespace["video_scene3_content_addon_keyboard"](state),
        namespace["video_scene3_post_keyboard"](state),
    ):
        optional_callbacks.update(
            button.callback_data for row in markup.inline_keyboard for button in row
        )
    assert {
        "vprofile|req_none",
        "vprofile|material_skip",
        "vprofile|creative_skip",
        "vprofile|audio_skip",
        "vprofile|post_skip",
    } <= optional_callbacks

    handler_source = _function_source("handle_video_editor_callback")
    assert "logo_scale" not in namespace["video_local_logo_keyboard"]().inline_keyboard[3][1].callback_data
    assert 'kind in {"logo_position", "logo_opacity"}' in handler_source


def test_reachable_video_legacy_and_studio_keyboards_keep_adaptive_one_to_five_contract():
    names = (
        "video_scene3_keyboard", "video_ui_back_label", "build_2col_keyboard", "video_v6_keyboard",
        "main_video_keyboard", "video_prompt_library_keyboard",
        "video_profile_studio_profile_keyboard", "architecture_profile_menu_keyboard",
        "architecture_question_keyboard", "architecture_asset_menu_keyboard",
        "architecture_preview_keyboard", "architecture_output_keyboard",
        "video_microflow_media_keyboard", "video_microflow_scene_count_keyboard",
        "video_microflow_select_label", "video_microflow_options_keyboard", "video_microflow_keyboard",
        "video_idea_development_keyboard", "video_storyboard_image_scenes_keyboard",
        "video_storyboard_final_video_scenes_keyboard", "video_image_prompt_set_keyboard",
        "video_b14_profile_selection_keyboard", "video_b14_idea_suggestions_keyboard",
        "video_asset_intake_keyboard", "video_asset_classify_keyboard", "video_asset_scene_order_keyboard",
        "video_b14_prompt_video_keyboard", "video_b14_storyboard_keyboard",
        "video_b14_missing_session_keyboard", "video_b14_creative_controls_keyboard",
        "video_b14_creative_choice_keyboard", "product_video_logo_position_keyboard",
        "video_b14_logo_keyboard", "video_b14_logo_position_keyboard", "video_b14_logo_confirm_keyboard",
        "video_b14_addon_keyboard", "video_b14_choice_keyboard", "video_b14_aspect_ratio_keyboard",
        "video_b14_quality_keyboard", "video_b14_scene_count_keyboard", "video_b14_invoice_keyboard",
        "video_b14_subtitle_keyboard", "video_b14_subtitle_language_keyboard", "video_b14_dub_keyboard",
        "video_b14_voice_keyboard", "video_b14_voice_edit_keyboard", "video_b14_volume_input_keyboard",
        "video_b14_music_keyboard", "video_b14_voice_select_keyboard", "video_b14_queue_status_keyboard",
        "product_video_public_preflight_panel_keyboard", "task3d_idea_suggestions_keyboard",
        "task3d_color_mood_keyboard", "task3d_subject_keyboard", "task3d_scene_idea_keyboard",
        "task3d_camera_keyboard", "task3d_pace_keyboard", "task3d_detail_keyboard",
        "task3d_image_plan_keyboard", "task3d_format_keyboard", "task3d_motion_keyboard",
        "task3d_extra_scene_keyboard", "task3d_platform_keyboard", "task3d_aspect_keyboard",
        "task3d_panel_keyboard", "task3d_style_keyboard", "task3d_output_target_keyboard",
        "task3d_result_keyboard", "task3d_prompt_number_rows", "task3d_prompt_image_scene_keyboard",
        "task3d_prompt_image_detail_keyboard", "task3d_prompt_image_logo_choice_keyboard",
        "task3d_prompt_image_logo_input_keyboard", "task3d_prompt_image_logo_position_keyboard",
        "task3d_prompt_image_logo_confirm_keyboard", "task3d_prompt_image_package_keyboard",
        "task3d_prompt_image_confirm_keyboard", "task3d_prompt_video_selector_keyboard",
        "task3d_prompt_video_batch_keyboard", "task3d_prompt_video_detail_keyboard",
        "task3d_prompt_export_done_keyboard", "task3d_trend_ideas_keyboard",
    )
    namespace = _keyboard_namespace(*names)
    namespace.update({
        "VIDEO_PUBLIC_MENU_ROWS": (
            ("video_trend", "video_ai_real"), ("script_image_video", "frame_video_local"),
            ("self_shot_scene_change", "multi_scene_film"), ("profile_studio", "video_idea"),
            ("storyboard_prompt", "video_downloader"), ("video_local_edit", "prompt_library"),
            ("main_menu", "video_guide"),
        ),
        "video_public_route_for_tool": lambda tool_id: {"entry_callback": f"menu|{tool_id}"},
        "video_public_menu_label": lambda tool_id, _lang: tool_id,
        "video_microflow_option_display_limit": lambda _kind, _product, count: min(5, int(count)),
        "video_b14_quality_for_session": lambda _session: 300,
        "video_b14_is_trial_quality": lambda quality: int(quality or 0) == 200,
        "get_video_session": lambda _uid: {},
        "video_b14_saved_voice_profiles": lambda _uid, _limit: [
            {"id": index, "display_name": f"Giọng {index}"} for index in range(1, 6)
        ],
        "minimax_voice_adapter": SimpleNamespace(
            friendly_voice_name=lambda profile, fallback: profile.get("display_name") or fallback
        ),
        "video_b14_delivered_video_artifact": lambda jid: {"ok": bool(jid)},
        "product_video_public_preflight_public_kind": lambda state: str(state),
        "task3d_idea_suggestions": lambda *_args: [f"Ý tưởng {index}" for index in range(1, 6)],
        "task3d_video_prompt_entries": lambda session, _kind: ["câu lệnh"] * int(session.get("count", 5)),
        "task3d_video_prompt_selection": lambda session, _kind: list(range(1, int(session.get("count", 1)) + 1)),
        "logo_watermark_position_label": lambda value, _lang: {
            "top_left": "Trên trái", "top_center": "Trên giữa", "top_right": "Trên phải",
            "bottom_left": "Dưới trái", "bottom_center": "Dưới giữa", "bottom_right": "Dưới phải",
        }.get(value, value),
    })
    markups = [
        namespace["main_video_keyboard"](), namespace["video_prompt_library_keyboard"](),
        namespace["video_profile_studio_profile_keyboard"](),
        namespace["architecture_profile_menu_keyboard"](), namespace["architecture_question_keyboard"](),
        namespace["architecture_asset_menu_keyboard"](), namespace["architecture_preview_keyboard"](),
        namespace["architecture_output_keyboard"](), namespace["video_microflow_media_keyboard"](),
        namespace["video_microflow_scene_count_keyboard"]("storyboard"),
        namespace["video_microflow_options_keyboard"]("video_idea", options=[{}] * 5, kind="video_idea"),
        namespace["video_microflow_keyboard"]("ai_prompt_menu", "video_ai_real"),
        namespace["video_microflow_keyboard"]("ai_image_menu", "video_ai_real"),
        namespace["video_microflow_keyboard"]("ai_video_menu", "video_ai_real"),
        namespace["video_idea_development_keyboard"](), namespace["video_storyboard_image_scenes_keyboard"](),
        namespace["video_storyboard_final_video_scenes_keyboard"](), namespace["video_image_prompt_set_keyboard"](),
        namespace["video_b14_profile_selection_keyboard"](), namespace["video_b14_idea_suggestions_keyboard"](),
        namespace["video_asset_intake_keyboard"](), namespace["video_asset_classify_keyboard"](),
        namespace["video_asset_scene_order_keyboard"](), namespace["video_b14_prompt_video_keyboard"](),
        namespace["video_b14_storyboard_keyboard"](), namespace["video_b14_missing_session_keyboard"](),
        namespace["video_b14_creative_controls_keyboard"](),
        namespace["video_b14_creative_choice_keyboard"]("visual_style"),
        namespace["product_video_logo_position_keyboard"](), namespace["video_b14_logo_keyboard"](),
        namespace["video_b14_logo_position_keyboard"](), namespace["video_b14_logo_confirm_keyboard"](),
        namespace["video_b14_addon_keyboard"](),
        namespace["video_b14_choice_keyboard"]("choice", [("Một", "one"), ("Hai", "two"), ("Ba", "three")]),
        namespace["video_b14_aspect_ratio_keyboard"](), namespace["video_b14_quality_keyboard"](),
        namespace["video_b14_scene_count_keyboard"](session={"draft": {}}), namespace["video_b14_invoice_keyboard"](),
        namespace["video_b14_subtitle_keyboard"](), namespace["video_b14_subtitle_language_keyboard"](),
        namespace["video_b14_dub_keyboard"](), namespace["video_b14_voice_keyboard"](),
        namespace["video_b14_voice_edit_keyboard"](), namespace["video_b14_volume_input_keyboard"]("voice"),
        namespace["video_b14_music_keyboard"](), namespace["video_b14_voice_select_keyboard"](1),
        namespace["video_b14_queue_status_keyboard"](job_id=123),
        namespace["product_video_public_preflight_panel_keyboard"](resolved_state="ready"),
        namespace["product_video_public_preflight_panel_keyboard"](resolved_state="ready_try"),
        namespace["product_video_public_preflight_panel_keyboard"](resolved_state="blocked"),
        namespace["task3d_idea_suggestions_keyboard"]({"product_id": "video_idea", "draft": {}}),
        namespace["task3d_color_mood_keyboard"](), namespace["task3d_subject_keyboard"](),
        namespace["task3d_scene_idea_keyboard"](), namespace["task3d_camera_keyboard"](),
        namespace["task3d_pace_keyboard"](), namespace["task3d_detail_keyboard"](),
        namespace["task3d_image_plan_keyboard"](), namespace["task3d_format_keyboard"](),
        namespace["task3d_motion_keyboard"](), namespace["task3d_extra_scene_keyboard"](),
        namespace["task3d_platform_keyboard"](), namespace["task3d_aspect_keyboard"](),
        namespace["task3d_panel_keyboard"](), namespace["task3d_style_keyboard"](),
        namespace["task3d_output_target_keyboard"](), namespace["task3d_result_keyboard"]("video_ai_real"),
        namespace["task3d_result_keyboard"]("video_idea"),
        namespace["task3d_prompt_image_scene_keyboard"]({"count": 5}),
        namespace["task3d_prompt_image_detail_keyboard"](), namespace["task3d_prompt_image_logo_choice_keyboard"](),
        namespace["task3d_prompt_image_logo_input_keyboard"](), namespace["task3d_prompt_image_logo_position_keyboard"](),
        namespace["task3d_prompt_image_logo_confirm_keyboard"](), namespace["task3d_prompt_image_package_keyboard"](),
        namespace["task3d_prompt_image_confirm_keyboard"]("token", {"count": 1}),
        namespace["task3d_prompt_video_selector_keyboard"]({"count": 5}),
        namespace["task3d_prompt_video_batch_keyboard"]({"count": 9}),
        namespace["task3d_prompt_video_detail_keyboard"](),
        namespace["task3d_prompt_export_done_keyboard"]("video_ai_real"),
        namespace["task3d_prompt_export_done_keyboard"]("video_idea"),
        namespace["task3d_trend_ideas_keyboard"]({"draft": {"trend_ideas": [{}] * 5}}),
    ]
    for markup_index, markup in enumerate(markups):
        callbacks = []
        for row in markup.inline_keyboard:
            assert 1 <= len(row) <= 5, (markup_index, [button.text for button in row])
            callbacks.extend(button.callback_data for button in row)
        assert len(callbacks) == len(set(callbacks)), (markup_index, callbacks)


def test_preconfirm_contract_has_zero_side_effects():
    state = _planned(5)
    assert video_scene3_flow.preconfirm_side_effects(state) == {
        "provider_called": False,
        "image_provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "xu_charged": 0,
        "wallet_mutations": 0,
    }
    forbidden = (
        "video_provider_router", "create_video_project", "create_outbox", "charge_wallet",
        "ShopAIKey", "Key4U", "requests.post", "httpx.post",
    )
    assert all(marker not in SCENE3_SOURCE for marker in forbidden)


def test_bot_source_uses_scene3_order_menu_order_and_final_confirm_boundary():
    assert 'VIDEO_SCENE1_CANONICAL_STEPS = video_scene3_flow.CANONICAL_STEPS' in BOT_SOURCE
    assert 'VIDEO_SCENE2_CANONICAL_STEPS = video_scene3_flow.CANONICAL_STEPS' in BOT_SOURCE
    expected_rows = (
        '("video_trend", "video_ai_real")',
        '("script_image_video", "frame_video_local")',
        '("self_shot_scene_change", "multi_scene_film")',
        '("storyboard_prompt", "video_idea")',
        '("video_local_edit", "video_downloader")',
        '("main_menu", "video_guide")',
    )
    menu_block = BOT_SOURCE[BOT_SOURCE.index("VIDEO_PUBLIC_MENU_ROWS = ("):BOT_SOURCE.index("VIDEO_PUBLIC_ROUTE_MATRIX = {")]
    positions = [menu_block.index(row) for row in expected_rows]
    assert positions == sorted(positions)
    handler = BOT_SOURCE[BOT_SOURCE.index("async def handle_video_profile_studio_callback"):BOT_SOURCE.index("async def handle_video_editor_callback")]
    assert "provider_router" not in handler
    assert "create_video_project" not in handler
    assert '"vproduct|b14_confirm"' in BOT_SOURCE
    assert '"vprofile|handoff"' in BOT_SOURCE
    assert "def video_scene3_content_type_text" not in BOT_SOURCE
    assert "def video_scene3_content_type_keyboard" not in BOT_SOURCE
    assert '"content_type": lambda: (video_scene3_profile_text(state), video_scene3_profile_keyboard(state))' in BOT_SOURCE


def test_changed_scene3_bot_functions_compile_in_isolation():
    names = (
        "video_scene2_reconcile_state",
        "video_scene3_keyboard",
        "video_scene3_profile_text",
        "video_scene3_profile_keyboard",
        "video_scene3_suggestion_text",
        "video_scene3_suggestion_keyboard",
        "video_scene3_requirements_keyboard",
        "video_scene3_materials_keyboard",
        "video_scene3_creative_keyboard",
        "video_scene3_content_addon_keyboard",
        "video_scene3_scene_plan_text",
        "video_scene3_full_review_text",
        "video_scene3_post_keyboard",
        "video_scene3_final_text",
        "handle_video_profile_studio_pending_text",
        "handle_video_profile_studio_callback",
        "video_profile_scene1_render",
    )
    for name in names:
        source = _function_source(name)
        compile("from __future__ import annotations\n" + source, f"<scene3ux1:{name}>", "exec")


def test_callback_registration_has_one_authoritative_final_confirm_and_no_legacy_override():
    definitions = (
        "handle_product_video_public_confirm_callback",
        "handle_video_product_callback",
        "handle_video_profile_studio_callback",
    )
    for name in definitions:
        assert BOT_SOURCE.count(f"async def {name}(") == 1
        assert BOT_SOURCE.count(f"CallbackQueryHandler({name},") == 1

    assert BOT_SOURCE.count(
        'CallbackQueryHandler(handle_product_video_public_confirm_callback, pattern=r"^vproduct\\|b14_confirm$")'
    ) == 1
    assert BOT_SOURCE.count(
        'CallbackQueryHandler(handle_video_product_callback, pattern=r"^vproduct\\|(?!b14_confirm(?:\\||$))")'
    ) == 1
    assert BOT_SOURCE.count(
        'CallbackQueryHandler(handle_video_profile_studio_callback, pattern=r"^vprofile\\|")'
    ) == 1

    confirm_handler = _function_source("handle_product_video_public_confirm_callback")
    assert "_product_video_authoritative_confirm" in confirm_handler
    assert "return await handle_video_product_callback(update, context)" in confirm_handler

    profile_handler = _function_source("handle_video_profile_studio_callback")
    guard_position = profile_handler.index("if not video_scene2_action_allowed(state, action):")
    for guarded_action in (
        'if action == "mode":',
        'if action == "count":',
        'if action in {"ctype", "ctype_suggest", "ctype_accept", "ctype_restore", "ctype_view"}:',
        'if action == "select":',
        'if action == "profile_select":',
        'if action == "suggest":',
        'if action == "handoff":',
    ):
        assert profile_handler.index(guarded_action) > guard_position


def test_scene3_public_handlers_wire_logo_transition_post_detail_and_real_local_editor_choices():
    scene3_handler = _function_source("handle_video_profile_studio_callback")
    media_handler = _function_source("handle_video_scene3_pending_media")
    editor_handler = _function_source("handle_video_editor_callback")
    assert 'if action == "creative_quick"' in scene3_handler
    assert 'if action == "post_preview_toggle"' in scene3_handler
    assert '"transition_picker"' in scene3_handler
    assert '"post_detail"' in scene3_handler
    assert '"step": "logo_position"' in media_handler
    assert "video_provider_router" not in media_handler
    assert "requests." not in media_handler
    assert "httpx." not in media_handler
    assert "create_video_project" not in media_handler
    assert 'requested_action not in {"concat", "aspect", "compress", "audio", "subtitle"}' in editor_handler
    assert '"await_video"' in editor_handler
    assert "requested_action=requested_action" in editor_handler


def test_public_product_microflows_use_clean_vietnamese_labels():
    intro = _function_source("task3d_product_intro_keyboard")
    microflow_text = _function_source("video_microflow_text")
    microflow_keyboard = _function_source("video_microflow_keyboard")
    assert "Prompt AI → Video" in intro
    assert "Gửi bảng phân cảnh sẵn" in intro
    assert "Gửi prompt có sẵn" in microflow_keyboard
    assert "Gợi ý prompt" in microflow_keyboard
    assert "Prompt → Video AI" not in intro
    assert "Gửi prompt sẵn" not in microflow_keyboard
    assert "awaiting_prompt_text" in microflow_text
    assert "Gửi prompt video có sẵn" in microflow_text


def test_data_contract_contains_b14_and_scene_first_fields():
    handoff = BOT_SOURCE[BOT_SOURCE.index("def video_profile_scene1_handoff"):BOT_SOURCE.index("async def video_profile_scene1_render")]
    expected = {
        "product_type", "subject", "scene_count", "content_type", "technical_profile", "context",
        "suggestion_version", "preservation_requirements", "reference_assets", "creative_controls",
        "content_affecting_addons", "scene_plan", "continuity_contract", "image_strategy_per_scene",
        "image_prompt_versions", "video_prompt_versions", "transition_plan", "postproduction_addons",
        "aspect_ratio", "quality_tier", "estimate", "final_report", "final_confirmed",
    }
    assert all(f'"{field}"' in handoff for field in expected)


def test_actual_public_callback_runs_scene_first_to_final_report_without_side_effects():
    handler_source = BOT_SOURCE[
        BOT_SOURCE.index("async def handle_video_profile_studio_callback"):
        BOT_SOURCE.index("async def handle_video_editor_callback")
    ]
    rendered_steps: list[str] = []
    invoice_seen: list[dict] = []

    def safe_int(value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def save_state(context, state):
        clean = video_scene3_flow.normalize_state(state)
        context.user_data["video_profile_studio"] = clean
        return clean

    def read_state(context):
        return video_scene3_flow.normalize_state(context.user_data.get("video_profile_studio") or {})

    def step_state(context, state, step, *, push=True, **fields):
        history = list(state.get("history") or [])
        current = str(state.get("step") or "menu")
        if push and current != step:
            history.append(current)
        return save_state(context, {**state, **fields, "step": step, "history": history[-40:]})

    def pop_state(context, state):
        history = list(state.get("history") or [])
        step = history.pop() if history else "menu"
        return save_state(context, {**state, "step": step, "history": history})

    def return_parent(context, state, parent, **fields):
        history = list(state.get("history") or [])
        if history and history[-1] == parent:
            history.pop()
        return save_state(context, {**state, **fields, "step": parent, "history": history})

    async def render(_query, state, _lang):
        rendered_steps.append(str(state.get("step") or ""))
        return state

    async def edit_or_send(_query, text, **kwargs):
        return {"text": text, **kwargs}

    def invoice_breakdown(quality, count):
        subtotal = int(quality) * int(count)
        return {"subtotal_xu": subtotal, "discount_percent": 0, "total_xu": subtotal}

    def handoff(_uid, state):
        snapshot = deepcopy(state)
        invoice_seen.append(snapshot)
        return snapshot

    def prepare_content_choices(state, *, rotate=False):
        flow_context = video_flow6.context_from_scene_state(state)
        if rotate:
            flow_context = video_flow6.rotate_suggestion_page(flow_context)
        suggestions = video_flow6.suggestion_page(
            flow_context,
            profile_label=video_profile_catalog.profile_label(
                str(state.get("primary_profile") or state.get("technical_profile") or "")
            ),
        )
        return video_flow6.sync_scene_state({
            **state,
            "suggestions": [dict(item) for item in suggestions],
            "video_flow_context": flow_context,
        })

    def flow6_preflight(_uid, state, _quality):
        flow_context = video_flow6.context_from_scene_state(state)
        return {
            "ok": True,
            "route": video_flow6.execution_route_for(flow_context),
            "route_selection": {
                "ok": True,
                "provider": "fixture_video",
                "model": "fixture_scene_model",
            },
            "required_capability": "text_to_video_or_scene_video",
        }

    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "get_user_language": lambda _uid: "vi",
        "video_profile_studio_state": read_state,
        "save_video_profile_studio_state": save_state,
        "video_profile_studio_step": step_state,
        "video_profile_studio_pop_step": pop_state,
        "video_scene3_return_to_parent": return_parent,
        "video_profile_studio_option": lambda selection_id: (
            {"selection_id": selection_id}
            if selection_id in dict(video_scene3_flow.TECHNICAL_PROFILES)
            else {}
        ),
        "video_scene3_prepare_content_choices": prepare_content_choices,
        "video_flow6_preflight_for_state": flow6_preflight,
        "video_scene2_action_allowed": lambda _state, _action: True,
        "video_scene2_reconcile_state": lambda _context, state: state,
        "video_profile_scene1_render": render,
        "safe_edit_or_send": edit_or_send,
        "safe_int": safe_int,
        "video_flow6": video_flow6,
        "video_profile_catalog": video_profile_catalog,
        "video_provider_catalog": SimpleNamespace(
            resolve_product_video_model=lambda **_kwargs: {
                "ok": True,
                "provider": "fixture_video",
                "model": "fixture_scene_model",
            },
            model_metadata_from_resolution=lambda resolution: {
                "provider": resolution.get("provider"),
                "model": resolution.get("model"),
            },
        ),
        "video_profile_catalog_record": lambda selection_id: dict(
            video_profile_catalog.PROFILE_BY_KEY.get(selection_id) or {}
        ),
        "video_scene3_flow": video_scene3_flow,
        "video_scene3_active_scene": lambda state: max(1, min(int(state.get("scene_count") or 1), int(state.get("active_scene_index") or 1))),
        "VIDEO_PRODUCT_REGISTRY": {},
        "VIDEO_B14_2_QUALITY_OPTIONS": (200, 300, 400, 500, 600, 800, 1000, 1200, 1500),
        "video_b14_trial_scene_policy": lambda _quality, _count: {"clamped": False},
        "video_b14_invoice_breakdown": invoice_breakdown,
        "video_profile_scene1_handoff": handoff,
        "video_b14_invoice_text": lambda session, _uid, _lang: f"Hoa don {session.get('scene_count')}",
        "video_scene3_invoice_keyboard": lambda _lang: object(),
        "video_profile_scene1_count_text": lambda _state, _lang: "count",
        "video_profile_scene1_count_keyboard": lambda _lang: object(),
        "video_profile_scene1_subject_text": lambda _lang: "subject",
        "video_profile_scene1_subject_keyboard": lambda _lang: object(),
        "video_profile_studio_menu_text": lambda _lang: "menu",
        "video_profile_studio_menu_keyboard": lambda _lang: object(),
        "set_video_route_session": lambda *_args, **_kwargs: None,
        "html": __import__("html"),
    }
    exec(compile("from __future__ import annotations\n" + handler_source, "<scene3-handler>", "exec"), namespace)
    handler = namespace["handle_video_profile_studio_callback"]

    class Query:
        def __init__(self):
            self.data = ""
            self.from_user = SimpleNamespace(id=123)

        async def answer(self, *_args, **_kwargs):
            return None

    query = Query()
    context = SimpleNamespace(user_data={})
    initial = video_scene3_flow.default_state(product_type="video_ai_real")
    initial.update({"step": "content_mode", "history": ["menu"], "source_product_id": "video_ai_real"})
    save_state(context, initial)
    update = SimpleNamespace(callback_query=query)

    async def run_action(callback: str):
        query.data = callback
        await handler(update, context)
        return read_state(context)

    async def advance_with_exact_back(callback: str, expected_step: str, previous_step: str):
        state = await run_action(callback)
        assert state["step"] == expected_step
        state = await run_action("vprofile|back")
        assert state["step"] == previous_step
        state = await run_action(callback)
        assert state["step"] == expected_step
        return state

    async def run_flow():
        state = await advance_with_exact_back("vprofile|mode|suggestions", "scene_count", "content_mode")
        state = await advance_with_exact_back("vprofile|count|2", "aspect_ratio", "scene_count")
        assert state["scene_count"] == 2
        assert state["quality_xu"] == 0
        state = await advance_with_exact_back("vprofile|ratio|16x9", "technical_profile", "aspect_ratio")
        assert state["aspect_ratio"] == "16:9"
        assert state["content_addons"]["aspect_ratio"] == "16:9"
        internal_type = state["content_type"]
        state = await run_action("vprofile|ctype|fashion_lookbook")
        assert state["step"] == "technical_profile"
        assert state["content_type"] == internal_type
        state = await run_action("vprofile|profile_none")
        assert state["step"] == "technical_profile"
        assert not state.get("technical_profile")
        state = await run_action("vprofile|select|architecture_interior")
        assert state["step"] == "technical_profile"
        assert not state.get("primary_profile")
        state = await advance_with_exact_back(
            "vprofile|profile_select|architecture_interior_renovation",
            "content_choice",
            "technical_profile",
        )
        assert state["content_type"] == "real_estate_fpv"
        state = await advance_with_exact_back("vprofile|suggest|1", "character", "content_choice")
        assert state["subject"]
        state = await advance_with_exact_back("vprofile|character|none", "image_source", "character")
        state = await advance_with_exact_back("vprofile|image_source|description", "creative_controls", "image_source")
        for callback, expected_step, previous_step in (
            ("vprofile|creative_skip", "requirements", "creative_controls"),
            ("vprofile|req_none", "audio_plan", "requirements"),
            ("vprofile|audio_skip", "scene_plan", "audio_plan"),
            ("vprofile|scene_done", "video_prompts", "scene_plan"),
            ("vprofile|video_prompt_done", "full_review", "video_prompts"),
            ("vprofile|review_continue", "quality", "full_review"),
            ("vprofile|tier|300", "final_report", "quality"),
        ):
            if callback == "vprofile|video_prompt_done":
                state = await run_action("vprofile|video_prompt_approve_all")
            state = await advance_with_exact_back(callback, expected_step, previous_step)
            assert video_scene3_flow.preconfirm_side_effects(state) == {
                "provider_called": False,
                "image_provider_called": False,
                "job_created": False,
                "outbox_created": False,
                "xu_charged": 0,
                "wallet_mutations": 0,
            }
        state = await run_action("vprofile|handoff")
        assert state["step"] == "final_confirmation"
        state = await run_action("vprofile|invoice_back")
        assert state["step"] == "final_report"
        await run_action("vprofile|handoff")

    asyncio.run(run_flow())
    final_state = read_state(context)
    assert final_state["step"] == "final_confirmation"
    assert final_state["scene_count"] == 2
    assert final_state["quality_xu"] == 300
    assert invoice_seen and invoice_seen[-1]["final_confirmed"] is False
    assert "content_type" not in rendered_steps
    assert "quality" in rendered_steps
