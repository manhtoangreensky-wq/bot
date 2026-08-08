from __future__ import annotations

from copy import deepcopy

import pytest

from services import video_uiflow3


CREATION_PRODUCTS = (
    "video_trend",
    "video_ai_real",
    "script_image_video",
    "frame_video_local",
    "self_shot_scene_change",
    "storyboard_prompt",
    "multi_scene_film",
)


def _locked_state(*, product: str = "video_ai_real", profile: str = "storytelling") -> dict:
    state = video_uiflow3.new_state(product, draft_id=f"draft-{product}")
    state = video_uiflow3.set_format(state, ratio="9:16", target_duration_seconds=24)
    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Lan va Minh cung gioi thieu mot san pham moi.",
        profile_id=profile,
        approved_brief={
            "title": "Gioi thieu san pham",
            "goal": "Giai thich ngan gon",
            "audience": "Nguoi moi",
            "main_message": "Hai nhan vat trinh bay san pham theo tung canh.",
            "needs_characters": True,
            "needs_dialogue": True,
            "needs_voice": True,
            "needs_locations": True,
        },
    )
    return video_uiflow3.lock_content(state)


def _planned_state() -> dict:
    state = _locked_state()
    state = video_uiflow3.set_character_count(state, 2)
    state = video_uiflow3.update_character(
        state,
        "char_01",
        display_name="Lan",
        gender="female",
        description="Nguoi dan chu tu tin, ao xanh.",
    )
    state = video_uiflow3.update_character(
        state,
        "char_02",
        display_name="Minh",
        gender="male",
        description="Nguoi tu van than thien, ao trang.",
    )
    state = video_uiflow3.set_location_count(state, 2)
    state = video_uiflow3.update_location(state, "loc_01", name="Quan ca phe")
    state = video_uiflow3.update_location(state, "loc_02", name="Goc san pham")
    state = video_uiflow3.confirm_scene_count(state, 3)
    return video_uiflow3.auto_assign_scenes(state)


def test_all_seven_creation_products_use_one_content_first_controller() -> None:
    assert tuple(video_uiflow3.ENTRY_ADAPTERS) == CREATION_PRODUCTS
    assert video_uiflow3.CANONICAL_VISIBLE_STEPS.index("content_lock") < video_uiflow3.CANONICAL_VISIBLE_STEPS.index("production_bible")
    assert video_uiflow3.CANONICAL_VISIBLE_STEPS.index("production_bible") < video_uiflow3.CANONICAL_VISIBLE_STEPS.index("scene_count")
    assert video_uiflow3.CANONICAL_VISIBLE_STEPS.index("scene_plan") < video_uiflow3.CANONICAL_VISIBLE_STEPS.index("scene_assignment")
    for product in CREATION_PRODUCTS:
        state = video_uiflow3.new_state(product, draft_id=f"draft-{product}")
        assert state["flow_schema_version"] == 3
        assert state["parent_product"] == product
        assert state["navigation"]["current_step"] in {"entry", "source", "format"}
        assert video_uiflow3.next_required_step(state) not in {
            "production_bible",
            "scene_count",
            "scene_plan",
            "scene_assignment",
        }


def test_video_idea_remains_catalog_only_outside_uiflow3_controller() -> None:
    assert "video_idea" not in video_uiflow3.ENTRY_ADAPTERS
    with pytest.raises(ValueError, match="unsupported_video_uiflow3_product"):
        video_uiflow3.new_state("video_idea", draft_id="catalog-must-not-become-a-flow")


def test_raw_source_can_arrive_early_but_entities_and_scenes_wait_for_content_lock() -> None:
    state = video_uiflow3.new_state("frame_video_local", draft_id="frame-draft")
    state = video_uiflow3.add_source_asset(
        state,
        asset_type="frame",
        telegram_file_id="frame-1",
        fingerprint="sha256:frame-1",
    )
    assert state["source"]["assets"][0]["owner_type"] == "raw_source"
    assert state["bible"]["characters"] == []
    assert state["scenes"] == []
    assert video_uiflow3.next_required_step(state) in {"format", "content_hub"}


def test_character_count_creates_stable_compact_roster_with_gender_description_voice_and_images() -> None:
    state = video_uiflow3.set_character_count(_locked_state(), 2)
    assert [item["character_id"] for item in state["bible"]["characters"]] == ["char_01", "char_02"]
    state = video_uiflow3.update_character(
        state,
        "char_01",
        display_name="Lan",
        gender="female",
        description="Ao xanh, toc dai.",
        voice_id="vi-female-a",
    )
    state = video_uiflow3.add_reference(
        state,
        asset_type="image",
        owner_type="character",
        owner_id="char_01",
        role="front_face",
        telegram_file_id="lan-front",
        fingerprint="sha256:lan-front",
    )
    character = state["bible"]["characters"][0]
    assert character["display_name"] == "Lan"
    assert character["gender"] == "female"
    assert character["voice_id"] == "vi-female-a"
    assert character["reference_asset_ids"] == ["asset_01"]

    renamed = video_uiflow3.update_character(state, "char_01", display_name="Lan Anh")
    assert renamed["bible"]["characters"][0]["character_id"] == "char_01"
    assert renamed["references"][0]["owner_id"] == "char_01"


def test_reducing_character_count_never_silently_orphans_scene_or_reference() -> None:
    state = _planned_state()
    state = video_uiflow3.add_reference(
        state,
        asset_type="image",
        owner_type="character",
        owner_id="char_02",
        role="full_body",
        telegram_file_id="minh-full",
        fingerprint="sha256:minh-full",
    )
    with pytest.raises(ValueError, match="character_reassignment_required"):
        video_uiflow3.set_character_count(state, 1)


def test_scene_count_is_suggested_only_after_content_and_respects_product_constraints() -> None:
    state = _locked_state(product="video_ai_real")
    suggestion = video_uiflow3.suggest_scene_count(state)
    assert suggestion == {"count": 3, "seconds_per_scene": 8, "source": "duration_and_content"}

    script = _locked_state(product="script_image_video")
    assert video_uiflow3.suggest_scene_count(video_uiflow3.set_format(script, target_duration_seconds=8))["count"] == 2

    storyboard = _locked_state(product="storyboard_prompt")
    storyboard = video_uiflow3.set_source_metadata(storyboard, detected_panel_count=6)
    assert video_uiflow3.suggest_scene_count(storyboard)["count"] == 6


def test_unassigned_scenes_use_deterministic_round_robin_not_hidden_randomness() -> None:
    state = _planned_state()
    assert [scene["character_ids"] for scene in state["scenes"]] == [
        ["char_01"],
        ["char_02"],
        ["char_01"],
    ]
    assert [scene["location_id"] for scene in state["scenes"]] == [
        "loc_01",
        "loc_02",
        "loc_01",
    ]
    assert all(scene["assignment_source"] == "auto_round_robin" for scene in state["scenes"])

    explicit = video_uiflow3.assign_scene(
        state,
        "scene_02",
        character_ids=["char_01", "char_02"],
        location_id="loc_02",
    )
    assert explicit["scenes"][1]["character_ids"] == ["char_01", "char_02"]
    assert explicit["scenes"][1]["assignment_source"] == "user"


def test_scene_reorder_keeps_ids_and_reduction_never_drops_dialogue_silently() -> None:
    state = _planned_state()
    reordered = video_uiflow3.reorder_scenes(state, ["scene_03", "scene_01", "scene_02"])
    assert [scene["scene_id"] for scene in reordered["scenes"]] == ["scene_03", "scene_01", "scene_02"]
    assert [scene["scene_index"] for scene in reordered["scenes"]] == [1, 2, 3]
    assert reordered["scenes"][0]["continuity_to_scene_id"] == "scene_01"
    assert reordered["scenes"][1]["continuity_from_scene_id"] == "scene_03"

    with_dialogue = video_uiflow3.set_dialogue(
        state,
        "scene_03",
        speaker_id="char_01",
        text="Cau ket khong duoc phep mat im lang.",
    )
    with pytest.raises(ValueError, match="scene_content_reconcile_required"):
        video_uiflow3.confirm_scene_count(with_dialogue, 2)


def test_combined_scene_editor_groups_cast_voice_dialogue_and_music_without_flat_complexity() -> None:
    state = _planned_state()
    state = video_uiflow3.set_dialogue(
        state,
        "scene_01",
        speaker_id="char_01",
        text="Xin chao, day la san pham moi.",
    )
    state = video_uiflow3.set_music_scope(state, "per_scene")
    state = video_uiflow3.set_scene_music(state, "scene_01", policy="track", track_id="music-01")
    model = video_uiflow3.scene_assignment_model(state, "scene_01")
    assert model["scene_id"] == "scene_01"
    assert model["characters"][0]["character_id"] == "char_01"
    assert model["dialogue"][0]["speaker_id"] == "char_01"
    assert model["music"] == {"policy": "track", "track_id": "music-01"}
    assert model["advanced_collapsed"] is True


def test_voice_auto_assignment_is_gender_aware_unique_and_never_silently_reuses() -> None:
    state = video_uiflow3.set_character_count(_locked_state(), 2)
    state = video_uiflow3.update_character(state, "char_01", gender="male")
    state = video_uiflow3.update_character(state, "char_02", gender="male")
    voices = [
        {"voice_id": "male-a", "gender": "male", "server_renderable": True},
        {"voice_id": "male-b", "gender": "male", "server_renderable": True},
        {"voice_id": "female-a", "gender": "female", "server_renderable": True},
    ]
    assigned = video_uiflow3.auto_assign_voices(state, voices)
    assert assigned["audio"]["voice_cast"]["char_01"]["voice_id"] == "male-a"
    assert assigned["audio"]["voice_cast"]["char_02"]["voice_id"] == "male-b"

    with pytest.raises(ValueError, match="distinct_server_voice_required"):
        video_uiflow3.auto_assign_voices(state, voices[:1])


def test_unresolved_voice_policy_records_gender_and_distinct_cast_requirement() -> None:
    state = video_uiflow3.set_character_count(_locked_state(), 2)
    state = video_uiflow3.update_character(state, "char_01", gender="male")
    state = video_uiflow3.update_character(state, "char_02", gender="male")
    first, second = state["bible"]["characters"]
    assert first["voice_policy"] == {
        "mode": "auto_gender_distinct",
        "gender": "male",
        "distinct_from": ["char_02"],
    }
    assert second["voice_policy"] == {
        "mode": "auto_gender_distinct",
        "gender": "male",
        "distinct_from": ["char_01"],
    }

    explicit = video_uiflow3.update_character(state, "char_01", voice_id="verified-male-a")
    assert explicit["bible"]["characters"][0]["voice_policy"]["mode"] == "explicit"
    automatic = video_uiflow3.update_character(explicit, "char_01", voice_id="")
    assert automatic["bible"]["characters"][0]["voice_policy"]["mode"] == "auto_gender_distinct"


def test_voice_readiness_rejects_duplicate_or_unmaterialized_speaker_voices() -> None:
    state = _planned_state()
    state = video_uiflow3.set_dialogue(state, "scene_01", speaker_id="char_01", text="Lan noi.")
    state = video_uiflow3.set_dialogue(state, "scene_02", speaker_id="char_02", text="Minh noi.")
    state["capabilities"]["multi_voice_render"] = True
    state["audio"]["voice_cast"] = {
        "char_01": {"voice_id": "same", "server_renderable": True},
        "char_02": {"voice_id": "same", "server_renderable": True},
    }
    assert "voice_cast_not_distinct" in video_uiflow3.readiness_errors(state)

    state["audio"]["voice_cast"]["char_02"] = {"voice_id": "other", "server_renderable": False}
    assert "char_02_voice_not_server_renderable" in video_uiflow3.readiness_errors(state)


def test_dialogue_budget_warns_without_cutting_the_sentence() -> None:
    state = _planned_state()
    long_sentence = "Mot cau thoai rat dai can duoc canh bao nhung tuyet doi khong bi cat giua cau. " * 4
    state = video_uiflow3.set_dialogue(state, "scene_01", speaker_id="char_01", text=long_sentence)
    dialogue = state["audio"]["dialogue_segments"][0]
    assert dialogue["text"] == long_sentence.strip()
    assert dialogue["budget_warning"] is True
    assert dialogue["estimated_seconds"] > dialogue["scene_budget_seconds"]


@pytest.mark.parametrize("scope", ["none", "whole_video", "per_scene"])
def test_music_scope_supports_none_whole_or_scene_plan(scope: str) -> None:
    state = video_uiflow3.set_music_scope(_planned_state(), scope)
    assert state["audio"]["music_scope"] == scope
    if scope == "none":
        assert state["audio"]["music_plan"] == {}
    elif scope == "whole_video":
        state = video_uiflow3.set_whole_video_music(state, track_id="whole-01", volume=25)
        assert state["audio"]["music_plan"]["track_id"] == "whole-01"
    else:
        state = video_uiflow3.set_scene_music(state, "scene_02", policy="off")
        assert state["audio"]["music_plan"]["scene_02"]["policy"] == "off"


def test_capability_gate_keeps_planning_contract_but_blocks_fake_final_controls() -> None:
    state = _planned_state()
    state = video_uiflow3.set_music_scope(state, "per_scene")
    controls = video_uiflow3.public_controls(state)
    assert controls["per_scene_music"] == {
        "supported": False,
        "planned": True,
        "hidden_reason": "renderer_not_connected",
    }
    assert controls["multi_voice_render"]["supported"] is False
    assert "per_scene_music_renderer_missing" in video_uiflow3.readiness_errors(state)

    capable = deepcopy(state)
    capable["capabilities"].update({"per_scene_music": True, "multi_voice_render": True})
    assert video_uiflow3.public_controls(capable)["per_scene_music"]["supported"] is True


def test_back_resume_and_summary_edit_are_exact_and_skip_invisible_steps() -> None:
    state = _locked_state(profile="lofi_visualizer")
    state["navigation"].update({"current_step": "entry", "visible_step_stack": []})
    state = video_uiflow3.navigate(state, "content_lock")
    state = video_uiflow3.navigate(state, "production_bible", visible=False)
    state = video_uiflow3.navigate(state, "scene_count")
    assert state["navigation"]["visible_step_stack"] == ["entry", "content_lock"]
    backed = video_uiflow3.back(state)
    assert backed["navigation"]["current_step"] == "content_lock"
    assert video_uiflow3.resume_step(backed) == "content_lock"

    summary = video_uiflow3.navigate(backed, "summary")
    editor = video_uiflow3.begin_summary_edit(summary, "production_bible")
    assert editor["navigation"]["return_to"] == "summary"
    saved = video_uiflow3.finish_editor(editor)
    assert saved["navigation"]["current_step"] == "summary"
    assert saved["navigation"]["return_to"] is None


def test_content_change_marks_only_downstream_dirty_and_keeps_uploaded_assets() -> None:
    state = _planned_state()
    state = video_uiflow3.add_reference(
        state,
        asset_type="image",
        owner_type="character",
        owner_id="char_01",
        role="front_face",
        telegram_file_id="lan",
        fingerprint="sha256:lan",
    )
    changed = video_uiflow3.revise_content(state, original_intent="Noi dung moi")
    assert changed["references"] == state["references"]
    assert set(changed["navigation"]["dirty_sections"]) >= {
        "needs",
        "production_bible",
        "scene_plan",
        "dialogue",
        "prompts",
        "summary",
    }


def test_dirty_downstream_sections_block_snapshot_until_reconciled() -> None:
    state = _planned_state()
    state = video_uiflow3.mark_sections_complete(
        state,
        "production_bible",
        "references",
        "continuity",
        "scene_plan",
        "scene_assignment",
        "prompts",
        "branding",
        "summary",
    )
    changed = video_uiflow3.revise_content(state, original_intent="Noi dung thay doi lon")
    changed = video_uiflow3.lock_content(changed)
    errors = video_uiflow3.readiness_errors(changed)
    assert "production_bible_reconcile_required" in errors
    assert "scene_plan_reconcile_required" in errors
    assert "dialogue_reconcile_required" in errors
    assert "prompts_reconcile_required" in errors
    with pytest.raises(ValueError, match="approved_snapshot_not_ready"):
        video_uiflow3.approved_snapshot(changed)

    reconciled = video_uiflow3.mark_sections_complete(
        changed,
        "production_bible",
        "scene_plan",
        "scene_assignment",
        "prompts",
        "summary",
    )
    assert not any(error.endswith("_reconcile_required") for error in video_uiflow3.readiness_errors(reconciled))


def test_legacy_mapping_preserves_singletons_without_guessing_flat_asset_owner() -> None:
    mapped = video_uiflow3.from_legacy_state(
        {
            "product_type": "video_ai_real",
            "character_config": {"mode": "female", "description": "Lan"},
            "postproduction_addons": {
                "dubbing": {"enabled": True, "value": {"voice_choice": "default_female"}},
                "music": {"enabled": True, "value": {"music_request": "Nhe nhang"}},
            },
            "reference_assets": {"items": [{"file_id": "legacy-image", "type": "character_person"}]},
        },
        draft_id="legacy-draft",
    )
    assert mapped["bible"]["characters"][0]["character_id"] == "char_01"
    assert mapped["audio"]["music_scope"] == "whole_video"
    assert mapped["references"][0]["owner_type"] == "legacy_unassigned"
    assert mapped["legacy_compat"]["migrated"] is True


def test_snapshot_is_provider_neutral_and_has_zero_side_effect_truth() -> None:
    state = _planned_state()
    state["capabilities"].update({"multi_voice_render": True, "per_scene_music": True})
    state = video_uiflow3.set_music_scope(state, "none")
    state = video_uiflow3.mark_sections_complete(
        state,
        "production_bible",
        "references",
        "continuity",
        "scene_plan",
        "scene_assignment",
        "audio",
        "prompts",
        "branding",
    )
    snapshot = video_uiflow3.approved_snapshot(state)
    assert snapshot["flow_schema_version"] == 3
    assert snapshot["parent_product"] == "video_ai_real"
    assert [item["character_id"] for item in snapshot["production_bible"]["characters"]] == ["char_01", "char_02"]
    assert snapshot["side_effects"] == {
        "provider_calls": 0,
        "jobs": 0,
        "outbox": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }


def test_callbacks_are_short_namespaced_and_stable() -> None:
    callbacks = [
        video_uiflow3.callback("entry", "video_ai_real"),
        video_uiflow3.callback("character", "char_01"),
        video_uiflow3.callback("scene", "scene_20"),
        video_uiflow3.callback("back"),
        video_uiflow3.callback("resume"),
    ]
    assert all(item.startswith("vid3|") for item in callbacks)
    assert all(len(item.encode("utf-8")) <= 64 for item in callbacks)
    assert len(callbacks) == len(set(callbacks))
