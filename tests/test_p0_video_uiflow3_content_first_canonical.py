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


def test_invalid_parent_product_never_normalizes_into_another_video_flow() -> None:
    with pytest.raises(ValueError, match="unsupported_video_uiflow3_product"):
        video_uiflow3.normalize_state({
            "flow_schema_version": 3,
            "draft_id": "corrupt-draft",
            "parent_product": "video_idea",
        })
    with pytest.raises(ValueError, match="unsupported_video_uiflow3_product"):
        video_uiflow3.from_legacy_state(
            {"product_type": "video_idea"},
            draft_id="catalog-is-not-a-creation-draft",
        )


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

    relationship_state = video_uiflow3.set_character_count(_locked_state(), 2)
    relationship_state = video_uiflow3.add_relationship(
        relationship_state,
        character_ids=["char_01", "char_02"],
        relation="colleague",
    )
    with pytest.raises(ValueError, match="character_reassignment_required"):
        video_uiflow3.set_character_count(relationship_state, 1)


def test_same_source_image_can_have_distinct_explicit_reference_owners() -> None:
    state = video_uiflow3.set_character_count(_locked_state(), 2)
    state = video_uiflow3.add_reference(
        state,
        asset_type="image",
        owner_type="character",
        owner_id="char_01",
        role="front_face",
        telegram_file_id="shared-photo",
        fingerprint="telegram:shared-photo",
    )
    state = video_uiflow3.add_reference(
        state,
        asset_type="image",
        owner_type="character",
        owner_id="char_02",
        role="front_face",
        telegram_file_id="shared-photo",
        fingerprint="telegram:shared-photo",
    )
    assert [(item["asset_id"], item["owner_id"]) for item in state["references"]] == [
        ("asset_01", "char_01"),
        ("asset_02", "char_02"),
    ]


def test_scene_count_is_suggested_only_after_content_and_respects_product_constraints() -> None:
    state = _locked_state(product="video_ai_real")
    suggestion = video_uiflow3.suggest_scene_count(state)
    assert suggestion == {"count": 3, "seconds_per_scene": 8, "source": "duration_and_content"}

    script = _locked_state(product="script_image_video")
    assert video_uiflow3.suggest_scene_count(video_uiflow3.set_format(script, target_duration_seconds=8))["count"] == 2

    storyboard = _locked_state(product="storyboard_prompt")
    storyboard = video_uiflow3.set_source_metadata(storyboard, detected_panel_count=6)
    assert video_uiflow3.suggest_scene_count(storyboard)["count"] == 6


def test_format_revision_updates_scene_ratio_and_reopens_duration_dependent_scene_count() -> None:
    state = video_uiflow3.confirm_scene_count(_locked_state(), 3)
    original_scene_ids = [item["scene_id"] for item in state["scenes"]]

    ratio_changed = video_uiflow3.set_format(state, ratio="16:9")
    assert [item["scene_id"] for item in ratio_changed["scenes"]] == original_scene_ids
    assert {item["ratio"] for item in ratio_changed["scenes"]} == {"16:9"}
    assert ratio_changed["format"]["scene_count_confirmed"] is True
    assert "prompts" in ratio_changed["navigation"]["dirty_sections"]
    assert "summary" in ratio_changed["navigation"]["dirty_sections"]

    duration_changed = video_uiflow3.set_format(
        ratio_changed,
        target_duration_seconds=40,
    )
    assert [item["scene_id"] for item in duration_changed["scenes"]] == original_scene_ids
    assert duration_changed["format"]["scene_count_confirmed"] is False
    assert "scene_plan" in duration_changed["navigation"]["dirty_sections"]
    assert "prompts" in duration_changed["navigation"]["dirty_sections"]
    assert duration_changed["navigation"]["current_step"] == state["navigation"]["current_step"]


def test_rule_scene_draft_fills_only_missing_fields_and_links_adjacent_scenes() -> None:
    state = video_uiflow3.confirm_scene_count(_locked_state(), 2)
    state["scenes"][0]["semantic_beat"] = "Y chinh do nguoi dung khoa"
    state["scenes"][0]["planning_source"] = "user"
    state["scenes"][0]["locked_by_user"] = True

    drafted = video_uiflow3.suggest_scene_plan(state)

    assert drafted["scenes"][0]["semantic_beat"] == "Y chinh do nguoi dung khoa"
    assert drafted["scenes"][0]["main_action"]
    assert drafted["scenes"][0]["completion_state"]
    assert drafted["scenes"][1]["semantic_beat"]
    assert drafted["scenes"][1]["main_action"]
    assert drafted["scenes"][1]["completion_state"]
    assert drafted["scenes"][1]["start_state"] == drafted["scenes"][0]["completion_state"]
    assert drafted["scenes"][1]["continuity_from_scene_id"] == "scene_01"
    assert video_uiflow3.scene_plan_complete(drafted) is True
    assert drafted["side_effects"] == state["side_effects"]


def test_user_scene_plan_update_relinks_the_following_scene_without_provider_side_effects() -> None:
    state = video_uiflow3.suggest_scene_plan(
        video_uiflow3.confirm_scene_count(_locked_state(), 2)
    )

    updated = video_uiflow3.update_scene_plan(
        state,
        "scene_01",
        semantic_beat="Mo dau moi",
        main_action="Lan mo hop san pham",
        completion_state="Hop da mo va san pham xuat hien ro",
        original_scene_intent="Mo dau moi | Lan mo hop san pham | Hop da mo va san pham xuat hien ro",
    )

    assert updated["scenes"][0]["planning_source"] == "user"
    assert updated["scenes"][0]["locked_by_user"] is True
    assert updated["scenes"][1]["start_state"] == "Hop da mo va san pham xuat hien ro"
    assert updated["side_effects"] == state["side_effects"]


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


def test_explicit_empty_scene_cast_clears_auto_assignment() -> None:
    state = _planned_state()
    assert state["scenes"][0]["character_ids"] == ["char_01"]

    cleared = video_uiflow3.assign_scene(state, "scene_01", character_ids=[])

    assert cleared["scenes"][0]["character_ids"] == []
    assert cleared["scenes"][0]["assignment_source"] == "user"


def test_readiness_rejects_dialogue_speaker_outside_scene_cast_but_allows_narrator() -> None:
    state = _planned_state()
    state = video_uiflow3.set_dialogue(
        state,
        "scene_01",
        speaker_id="char_02",
        text="Nhan vat nay khong co mat trong canh.",
    )
    assert "dlg_01_speaker_not_in_scene" in video_uiflow3.readiness_errors(state)

    narrator_state = deepcopy(state)
    narrator_state["audio"]["dialogue_segments"] = []
    narrator_state["scenes"][0]["dialogue_segment_ids"] = []
    narrator_state["bible"]["narrator"] = {
        "narrator_id": "narrator_01",
        "display_name": "Nguoi dan chuyen",
    }
    narrator_state = video_uiflow3.set_dialogue(
        narrator_state,
        "scene_01",
        speaker_id="narrator_01",
        text="Loi dan khong can xuat hien trong cast.",
    )
    assert "dlg_01_speaker_not_in_scene" not in video_uiflow3.readiness_errors(narrator_state)


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


def test_scene_reduction_uses_current_order_and_never_discards_a_retained_reordered_scene() -> None:
    state = _planned_state()
    state = video_uiflow3.reorder_scenes(state, ["scene_03", "scene_01", "scene_02"])
    state = video_uiflow3.set_dialogue(
        state,
        "scene_03",
        speaker_id="char_01",
        text="Canh dau sau khi sap xep lai phai duoc giu nguyen.",
    )

    reduced = video_uiflow3.confirm_scene_count(state, 2)

    assert [scene["scene_id"] for scene in reduced["scenes"]] == ["scene_03", "scene_01"]
    assert reduced["audio"]["dialogue_segments"][0]["scene_id"] == "scene_03"


def test_scene_ids_are_not_reused_after_a_reduction_and_expansion() -> None:
    state = video_uiflow3.confirm_scene_count(_locked_state(), 3)
    original_ids = [scene["scene_id"] for scene in state["scenes"]]

    reduced = video_uiflow3.confirm_scene_count(state, 2)
    expanded = video_uiflow3.confirm_scene_count(reduced, 3)

    assert original_ids == ["scene_01", "scene_02", "scene_03"]
    assert [scene["scene_id"] for scene in expanded["scenes"]] == [
        "scene_01", "scene_02", "scene_04",
    ]


def test_scene_reduction_never_discards_advanced_direction_work() -> None:
    state = video_uiflow3.confirm_scene_count(_locked_state(), 2)
    state = video_uiflow3.update_scene_direction(
        state,
        "scene_02",
        framing="Medium close-up",
        movement="Dolly cham",
        lighting="Anh sang cua so",
        mood="Am ap",
    )

    with pytest.raises(ValueError, match="scene_content_reconcile_required"):
        video_uiflow3.confirm_scene_count(state, 1)


def test_character_and_location_ids_are_not_reused_after_count_changes() -> None:
    state = video_uiflow3.set_character_count(_locked_state(), 2)
    state = video_uiflow3.set_location_count(state, 2)

    state = video_uiflow3.set_character_count(state, 1)
    state = video_uiflow3.set_location_count(state, 1)
    state = video_uiflow3.set_character_count(state, 2)
    state = video_uiflow3.set_location_count(state, 2)

    assert [item["character_id"] for item in state["bible"]["characters"]] == ["char_01", "char_03"]
    assert [item["location_id"] for item in state["bible"]["locations"]] == ["loc_01", "loc_03"]
    assert [item["display_name"] for item in state["bible"]["characters"]] == ["Nhan vat 1", "Nhan vat 2"]
    assert [item["name"] for item in state["bible"]["locations"]] == ["Boi canh 1", "Boi canh 2"]


def test_scene_count_never_blindly_drops_frame_or_storyboard_source_units() -> None:
    frame = video_uiflow3.new_state("frame_video_local", draft_id="frame-coverage")
    frame = video_uiflow3.add_source_asset(
        frame,
        asset_type="frame",
        telegram_file_id="frame-1",
        fingerprint="sha256:frame-1",
    )
    frame = video_uiflow3.add_source_asset(
        frame,
        asset_type="frame",
        telegram_file_id="frame-2",
        fingerprint="sha256:frame-2",
    )
    frame = video_uiflow3.set_format(frame, ratio="9:16", target_duration_seconds=6)
    frame = video_uiflow3.set_content_candidate(
        frame,
        source="source",
        original_intent="Hai anh theo dung thu tu.",
        approved_brief={"title": "Hai anh"},
    )
    frame = video_uiflow3.lock_content(frame)
    with pytest.raises(ValueError, match="scene_content_reconcile_required"):
        video_uiflow3.confirm_scene_count(frame, 1)
    assert [item["scene_id"] for item in video_uiflow3.confirm_scene_count(frame, 2)["scenes"]] == [
        "scene_01",
        "scene_02",
    ]

    storyboard = _locked_state(product="storyboard_prompt")
    storyboard = video_uiflow3.set_source_metadata(storyboard, detected_panel_count=3)
    with pytest.raises(ValueError, match="scene_content_reconcile_required"):
        video_uiflow3.confirm_scene_count(storyboard, 2)


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


def test_narrator_auto_voice_is_server_renderable_and_distinct_from_cast() -> None:
    state = video_uiflow3.set_character_count(_locked_state(), 2)
    state = video_uiflow3.update_character(state, "char_01", gender="female")
    state = video_uiflow3.update_character(state, "char_02", gender="male")
    state = video_uiflow3.set_narrator(state, display_name="Nguoi dan")
    inventory = [
        {"voice_id": "female-a", "gender": "female", "server_renderable": True},
        {"voice_id": "male-a", "gender": "male", "server_renderable": True},
        {"voice_id": "narrator-a", "gender": "unspecified", "server_renderable": True},
    ]

    assigned = video_uiflow3.auto_assign_voices(state, inventory)

    cast = assigned["audio"]["voice_cast"]
    assert cast["narrator_01"]["voice_id"] == "narrator-a"
    assert cast["narrator_01"]["server_renderable"] is True
    assert len({item["voice_id"] for item in cast.values()}) == 3

    with pytest.raises(ValueError, match="distinct_server_voice_required"):
        video_uiflow3.auto_assign_voices(state, inventory[:2])


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


def test_summary_readiness_enforces_required_locations_dialogue_and_each_character_voice() -> None:
    locked = _locked_state()
    initial_errors = video_uiflow3.readiness_errors(locked)
    assert "characters_required" in initial_errors
    assert "locations_required" in initial_errors
    assert "dialogue_required" in initial_errors

    planned = _planned_state()
    planned_errors = video_uiflow3.readiness_errors(planned)
    assert "dialogue_required" in planned_errors
    assert "char_01_voice_missing" in planned_errors
    assert "char_02_voice_missing" in planned_errors

    missing_location = video_uiflow3.assign_scene(planned, "scene_02", location_id="")
    assert "scene_02_location_missing" in video_uiflow3.readiness_errors(missing_location)


def test_readiness_requires_confirmed_counts_and_complete_required_character_location_profiles() -> None:
    locked = _locked_state()
    assert "character_count_unconfirmed" in video_uiflow3.readiness_errors(locked)
    assert "location_count_unconfirmed" in video_uiflow3.readiness_errors(locked)

    state = video_uiflow3.set_character_count(locked, 1)
    state = video_uiflow3.set_location_count(state, 1)
    assert state["bible"]["character_count_confirmed"] is True
    assert state["bible"]["location_count_confirmed"] is True
    errors = video_uiflow3.readiness_errors(state)
    assert "char_01_gender_missing" in errors
    assert "char_01_description_missing" in errors
    assert "loc_01_description_missing" in errors

    state["needs"]["reference_assets"] = "REQUIRED"
    errors = video_uiflow3.readiness_errors(state)
    assert "char_01_reference_missing" in errors
    assert "loc_01_reference_missing" in errors

    state = video_uiflow3.update_character(
        state,
        "char_01",
        gender="female",
        description="Nhan vat chinh mac ao xanh.",
    )
    state = video_uiflow3.update_location(
        state,
        "loc_01",
        description="Quan ca phe sang, anh sang tu nhien.",
    )
    state = video_uiflow3.add_reference(
        state,
        asset_type="image",
        owner_type="character",
        owner_id="char_01",
        role="front_face",
        telegram_file_id="char-image",
        fingerprint="sha256:char-image",
    )
    state = video_uiflow3.add_reference(
        state,
        asset_type="image",
        owner_type="location",
        owner_id="loc_01",
        role="location_reference",
        telegram_file_id="location-image",
        fingerprint="sha256:location-image",
    )
    errors = video_uiflow3.readiness_errors(state)
    assert "char_01_gender_missing" not in errors
    assert "char_01_description_missing" not in errors
    assert "char_01_reference_missing" not in errors
    assert "loc_01_description_missing" not in errors
    assert "loc_01_reference_missing" not in errors


def test_readiness_requires_a_meaningful_semantic_contract_for_every_scene() -> None:
    state = _planned_state()
    errors = video_uiflow3.readiness_errors(state)
    assert "scene_01_semantic_beat_missing" in errors
    assert "scene_01_main_action_missing" in errors
    assert "scene_01_completion_state_missing" in errors

    for scene in state["scenes"]:
        scene["semantic_beat"] = f"Y chinh canh {scene['scene_index']}"
        scene["main_action"] = f"Hanh dong canh {scene['scene_index']}"
        scene["completion_state"] = f"Ket qua canh {scene['scene_index']}"
    errors = video_uiflow3.readiness_errors(state)
    assert not any(
        item.endswith(("_semantic_beat_missing", "_main_action_missing", "_completion_state_missing"))
        for item in errors
    )


def test_readiness_enforces_reference_music_and_continuity_only_when_required() -> None:
    state = _planned_state()
    optional_errors = video_uiflow3.readiness_errors(state)
    assert "reference_assets_required" not in optional_errors
    assert "music_required" not in optional_errors
    assert "continuity_required" not in optional_errors

    state["needs"].update({
        "reference_assets": "REQUIRED",
        "music": "REQUIRED",
        "continuity": "REQUIRED",
    })
    required_errors = video_uiflow3.readiness_errors(state)
    assert "reference_assets_required" in required_errors
    assert "music_required" in required_errors
    assert "continuity_required" in required_errors


def test_required_narrator_and_product_never_pass_readiness_without_bible_entities() -> None:
    state = _locked_state()
    state["needs"].update({"characters": "SKIP", "locations": "SKIP", "narrator": "REQUIRED", "product": "REQUIRED"})
    state = video_uiflow3.set_character_count(state, 0)
    state = video_uiflow3.set_location_count(state, 0)
    state = video_uiflow3.confirm_scene_count(state, 1)

    errors = video_uiflow3.readiness_errors(state)

    assert "narrator_required" in errors
    assert "products_required" in errors

    state = video_uiflow3.set_narrator(state, display_name="Nguoi dan")
    state = video_uiflow3.add_product(state, name="San pham mau")
    errors = video_uiflow3.readiness_errors(state)
    assert "narrator_scene_assignment_required" in errors
    assert "product_scene_assignment_required" in errors

    state = video_uiflow3.assign_scene(
        state,
        "scene_01",
        narrator_enabled=True,
        product_ids=["prod_01"],
    )
    errors = video_uiflow3.readiness_errors(state)
    assert "narrator_required" not in errors
    assert "products_required" not in errors
    assert "narrator_scene_assignment_required" not in errors
    assert "product_scene_assignment_required" not in errors


def test_scene_assignment_model_exposes_narrator_product_prop_and_scene_audio_contract() -> None:
    state = _planned_state()
    state["bible"]["narrator"] = {"narrator_id": "narrator_01", "style": "binh tinh", "voice_id": "narrator-a"}
    state["bible"]["products"] = [{"product_id": "prod_01", "name": "San pham mau"}]
    state["bible"]["props"] = [{"prop_id": "prop_01", "name": "Hop qua"}]
    state["scenes"][0]["narrator_enabled"] = True
    state["scenes"][0]["product_ids"] = ["prod_01"]
    state["scenes"][0]["prop_ids"] = ["prop_01"]
    state["scenes"][0]["sfx_ids"] = ["door-open"]
    state["scenes"][0]["ambient_id"] = "cafe"

    model = video_uiflow3.scene_assignment_model(state, "scene_01")

    assert model.get("narrator") == {"enabled": True, "narrator_id": "narrator_01"}
    assert model.get("products") == [{"product_id": "prod_01", "name": "San pham mau"}]
    assert model.get("props") == [{"prop_id": "prop_01", "name": "Hop qua"}]
    assert model.get("sfx_ids") == ["door-open"]
    assert model.get("ambient_id") == "cafe"


def test_dialogue_budget_warns_without_cutting_the_sentence() -> None:
    state = _planned_state()
    long_sentence = "Mot cau thoai rat dai can duoc canh bao nhung tuyet doi khong bi cat giua cau. " * 4
    state = video_uiflow3.set_dialogue(state, "scene_01", speaker_id="char_01", text=long_sentence)
    dialogue = state["audio"]["dialogue_segments"][0]
    assert dialogue["text"] == long_sentence.strip()
    assert dialogue["budget_warning"] is True
    assert dialogue["estimated_seconds"] > dialogue["scene_budget_seconds"]


def test_dialogue_removal_is_scene_owned_and_cleans_both_indexes() -> None:
    state = video_uiflow3.set_character_count(_locked_state(), 1)
    state = video_uiflow3.confirm_scene_count(state, 2)
    state = video_uiflow3.assign_scene(state, "scene_01", character_ids=["char_01"])
    state = video_uiflow3.assign_scene(state, "scene_02", character_ids=["char_01"])
    state = video_uiflow3.set_dialogue(state, "scene_01", speaker_id="char_01", text="Cau can xoa")
    state = video_uiflow3.set_dialogue(state, "scene_02", speaker_id="char_01", text="Cau phai giu")

    with pytest.raises(ValueError, match="dialogue_scene_mismatch"):
        video_uiflow3.remove_dialogue(state, "dlg_01", scene_id="scene_02")

    updated = video_uiflow3.remove_dialogue(state, "dlg_01", scene_id="scene_01")

    assert [item["dialogue_id"] for item in updated["audio"]["dialogue_segments"]] == ["dlg_02"]
    assert updated["scenes"][0]["dialogue_segment_ids"] == []
    assert updated["scenes"][1]["dialogue_segment_ids"] == ["dlg_02"]


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


def test_music_revisions_dirty_prompts_and_keep_scene_policy_coherent() -> None:
    state = _planned_state()
    state["navigation"]["dirty_sections"] = []

    state = video_uiflow3.set_music_scope(state, "whole_video")
    assert {"audio", "prompts", "summary"}.issubset(state["navigation"]["dirty_sections"])

    state["navigation"]["dirty_sections"] = []
    state = video_uiflow3.set_whole_video_music(state, track_id="whole-01", volume=25)
    assert {"audio", "prompts", "summary"}.issubset(state["navigation"]["dirty_sections"])

    state = video_uiflow3.set_music_scope(state, "per_scene")
    state["navigation"]["dirty_sections"] = []
    state = video_uiflow3.set_scene_music(state, "scene_02", policy="track", track_id="scene-02")
    scene = next(item for item in state["scenes"] if item["scene_id"] == "scene_02")
    assert scene["music_policy"] == "track"
    assert state["audio"]["music_plan"]["scene_02"]["policy"] == "track"
    assert {"audio", "prompts", "summary"}.issubset(state["navigation"]["dirty_sections"])


def test_continuity_revision_dirties_prompts_and_summary() -> None:
    state = _planned_state()
    state["navigation"]["dirty_sections"] = []

    state = video_uiflow3.set_continuity(state, "identity", False)

    assert state["bible"]["continuity"]["identity"] is False
    assert {"continuity", "prompts", "summary"}.issubset(state["navigation"]["dirty_sections"])


def test_source_units_over_product_scene_limit_are_rejected_before_planning() -> None:
    state = video_uiflow3.new_state("frame_video_local", draft_id="source-limit")
    for index in range(20):
        state = video_uiflow3.add_source_asset(
            state,
            asset_type="frame",
            telegram_file_id=f"frame-{index}",
            fingerprint=f"sha256:frame-{index}",
        )

    with pytest.raises(ValueError, match="source_scene_limit_exceeded"):
        video_uiflow3.add_source_asset(
            state,
            asset_type="frame",
            telegram_file_id="frame-21",
            fingerprint="sha256:frame-21",
        )

    storyboard = video_uiflow3.new_state("storyboard_prompt", draft_id="panel-limit")
    with pytest.raises(ValueError, match="source_scene_limit_exceeded"):
        video_uiflow3.set_source_metadata(storyboard, detected_panel_count=21)


def test_long_video_series_episode_inheritance_keeps_stable_entity_and_voice_ids() -> None:
    state = video_uiflow3.new_state("multi_scene_film", draft_id="series-inheritance")
    state = video_uiflow3.set_entry_mode(state, "series_plan")
    assert state["navigation"]["current_step"] == "series_goal"
    state = video_uiflow3.set_series_goal(state, "Mot series huong dan ban hang ben vung.")
    state = video_uiflow3.set_format(state, ratio="16:9", target_duration_seconds=1200)
    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Tap mo dau gioi thieu hai nguoi dan.",
        profile_id="educational_series",
        approved_brief={"title": "Tap mo dau"},
    )
    state = video_uiflow3.lock_content(state)
    state = video_uiflow3.set_character_count(state, 2)
    state = video_uiflow3.update_character(
        state,
        "char_01",
        display_name="Lan",
        gender="female",
        description="Nguoi dan chinh",
        voice_id="voice-female-01",
    )
    state = video_uiflow3.update_character(
        state,
        "char_02",
        display_name="Minh",
        gender="male",
        description="Nguoi dan thu hai",
        voice_id="voice-male-01",
    )
    state = video_uiflow3.set_location_count(state, 1)
    state = video_uiflow3.update_location(state, "loc_01", name="Studio", description="Studio sang")
    state = video_uiflow3.set_episode_identity(state, number=2, title="Bat dau")
    state = video_uiflow3.set_episode_content(state, "Lan va Minh cung bat dau ke hoach.")
    state = video_uiflow3.lock_episode_content(state)

    inherited = video_uiflow3.effective_episode_contract(state)
    assert inherited["series_id"] == state["series"]["series_id"]
    assert inherited["character_ids"] == ["char_01", "char_02"]
    assert inherited["location_ids"] == ["loc_01"]
    assert set(inherited["voice_cast"]) == {"char_01", "char_02"}

    state = video_uiflow3.set_episode_entity_override(state, "characters", ["char_02"])
    state = video_uiflow3.set_episode_continuity_override(state, "identity", False)
    effective = video_uiflow3.effective_episode_contract(state)
    assert effective["character_ids"] == ["char_02"]
    assert effective["continuity"]["identity"] is False

    state = video_uiflow3.confirm_scene_count(state, 2)
    state = video_uiflow3.suggest_scene_plan(state)
    assert "Lan va Minh" in state["scenes"][0]["semantic_beat"]
    state = video_uiflow3.auto_assign_scenes(state)
    assert [scene["character_ids"] for scene in state["scenes"]] == [["char_02"], ["char_02"]]

    renamed = video_uiflow3.update_character(state, "char_02", display_name="Minh moi")
    assert video_uiflow3.effective_episode_contract(renamed)["character_ids"] == ["char_02"]


@pytest.mark.parametrize(
    ("entity_type", "removed_id", "reduce"),
    (
        ("characters", "char_02", lambda state: video_uiflow3.set_character_count(state, 1)),
        ("locations", "loc_02", lambda state: video_uiflow3.set_location_count(state, 1)),
    ),
)
def test_series_entity_reduction_requires_episode_override_reconciliation(
    entity_type: str,
    removed_id: str,
    reduce,
) -> None:
    state = _locked_state(product="multi_scene_film")
    state = video_uiflow3.set_series_goal(state, "Series co Bible dung chung.")
    state = video_uiflow3.set_character_count(state, 2)
    state = video_uiflow3.set_location_count(state, 2)
    state = video_uiflow3.set_episode_entity_override(state, entity_type, [removed_id])

    with pytest.raises(ValueError, match="reassignment_required"):
        reduce(state)


def test_corrupt_episode_lock_never_passes_without_candidate_and_content() -> None:
    state = _locked_state(product="multi_scene_film")
    state = video_uiflow3.set_series_goal(state, "Series co noi dung chung.")
    state["episode"]["title"] = "Tap loi du lieu"
    state["episode"]["content"] = {
        "original_intent": "",
        "candidate_ready": False,
        "locked": True,
        "revision": 9,
    }

    normalized = video_uiflow3.normalize_state(state)

    assert normalized["episode"]["content"]["locked"] is False
    assert "episode_content_not_locked" in video_uiflow3.readiness_errors(normalized)


def test_planning_snapshot_preserves_renderer_blockers_without_blocking_save() -> None:
    state = video_uiflow3.set_character_count(_locked_state(), 1)
    state = video_uiflow3.update_character(
        state,
        "char_01",
        display_name="Lan",
        gender="female",
        description="Nguoi dan chinh.",
        voice_id="plan-vi-female-02",
    )
    state = video_uiflow3.set_location_count(state, 0)
    state = video_uiflow3.confirm_scene_count(state, 1)
    state = video_uiflow3.suggest_scene_plan(state)
    state = video_uiflow3.auto_assign_scenes(state)
    state["needs"].update({
        "locations": "SKIP",
        "dialogue": "SKIP",
        "reference_assets": "SKIP",
        "music": "SKIP",
        "sfx": "SKIP",
        "ambient": "SKIP",
        "continuity": "SKIP",
    })
    state = video_uiflow3.mark_sections_complete(
        state,
        "production_bible",
        "scene_plan",
        "scene_assignment",
        "dialogue",
        "prompts",
    )

    assert "char_01_voice_not_server_renderable" in video_uiflow3.readiness_errors(state)
    assert video_uiflow3.planning_readiness_errors(state) == []
    snapshot = video_uiflow3.approved_snapshot(state)
    assert "char_01_voice_not_server_renderable" in snapshot["render_blockers"]


def test_existing_source_asset_can_be_mapped_without_reupload() -> None:
    state = video_uiflow3.new_state("frame_video_local", draft_id="source-reference-map")
    state = video_uiflow3.add_source_asset(
        state,
        asset_type="frame",
        telegram_file_id="source-frame-1",
        fingerprint="sha256:source-frame-1",
    )
    state = video_uiflow3.set_format(state, ratio="9:16", target_duration_seconds=8)
    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Nhan vat Lan gioi thieu san pham.",
        approved_brief={"title": "Lan gioi thieu"},
    )
    state = video_uiflow3.lock_content(state)
    state = video_uiflow3.set_character_count(state, 1)
    state = video_uiflow3.confirm_scene_count(state, 1)

    mapped = video_uiflow3.map_source_asset_to_reference(
        state,
        source_asset_id="source_01",
        owner_type="character",
        owner_id="char_01",
        role="primary_identity",
        allowed_scene_ids=["scene_01"],
    )

    assert [item["asset_id"] for item in mapped["source"]["assets"]] == ["source_01"]
    assert len(mapped["references"]) == 1
    reference = mapped["references"][0]
    assert reference["telegram_file_id"] == "source-frame-1"
    assert reference["fingerprint"] == "sha256:source-frame-1"
    assert reference["owner_type"] == "character"
    assert reference["owner_id"] == "char_01"
    assert reference["allowed_scene_ids"] == ["scene_01"]
    assert reference["source"] == "source_intake"


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


def test_scene_sfx_and_ambient_plans_are_capability_gated() -> None:
    state = video_uiflow3.assign_scene(
        _planned_state(),
        "scene_01",
        sfx_ids=["door", "footstep"],
        ambient_id="cafe",
    )
    controls = video_uiflow3.public_controls(state)
    assert controls["scene_sfx"]["planned"] is True
    assert controls["scene_ambient"]["planned"] is True
    assert "scene_sfx_renderer_missing" in video_uiflow3.readiness_errors(state)
    assert "scene_ambient_renderer_missing" in video_uiflow3.readiness_errors(state)

    state["capabilities"].update({"scene_sfx": True, "scene_ambient": True})
    errors = video_uiflow3.readiness_errors(state)
    assert "scene_sfx_renderer_missing" not in errors
    assert "scene_ambient_renderer_missing" not in errors


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
    assert saved["navigation"]["visible_step_stack"][-1] == "content_lock"
    assert video_uiflow3.back(saved)["navigation"]["current_step"] == "content_lock"

    repeated = deepcopy(saved)
    repeated["navigation"]["visible_step_stack"] = ["format", "content_hub", "format"]
    assert video_uiflow3.normalize_state(repeated)["navigation"]["visible_step_stack"] == [
        "format",
        "content_hub",
        "format",
    ]


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
    state = video_uiflow3.update_location(state, "loc_01", description="Quan ca phe sang, anh sang tu nhien.")
    state = video_uiflow3.update_location(state, "loc_02", description="Goc trung bay san pham ro rang.")
    for scene in state["scenes"]:
        scene["semantic_beat"] = f"Y chinh canh {scene['scene_index']}"
        scene["main_action"] = f"Hanh dong canh {scene['scene_index']}"
        scene["completion_state"] = f"Ket qua canh {scene['scene_index']}"
    state["capabilities"].update({"multi_voice_render": True, "per_scene_music": True})
    state = video_uiflow3.set_dialogue(state, "scene_01", speaker_id="char_01", text="Lan gioi thieu san pham.")
    state = video_uiflow3.set_dialogue(state, "scene_02", speaker_id="char_02", text="Minh noi ve loi ich.")
    state = video_uiflow3.auto_assign_voices(state, [
        {"voice_id": "female-a", "gender": "female", "server_renderable": True},
        {"voice_id": "male-a", "gender": "male", "server_renderable": True},
    ])
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
