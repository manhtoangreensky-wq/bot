from __future__ import annotations

import bot
from services import (
    video_script_product,
    video_selfshot2,
    video_selfshot3,
    video_tail9,
    video_uiflow3,
)


def _rows(markup) -> list[list[tuple[str, str]]]:
    def logical(value: str) -> str:
        parts = str(value or "").split("|")
        if len(parts) >= 4 and parts[:2] == ["vid3", "d"]:
            return "|".join(("vid3", *parts[3:]))
        return str(value or "")

    return [
        [(button.text, logical(button.callback_data)) for button in row]
        for row in markup.inline_keyboard
    ]


def _callbacks(markup) -> list[str]:
    return [callback for row in _rows(markup) for _label, callback in row if callback]


def test_video_ai_real_keeps_its_approved_uiflow3_owner_and_menu_back() -> None:
    product = "video_ai_real"
    route = bot.VIDEO_PUBLIC_ROUTE_MATRIX[product]
    expected_children = ("vid3|mode|prompt_video", "vid3|mode|image_video")
    assert route["entry_callback"] == "vid3|entry|video_ai_real"
    assert route["handler"] == "handle_video_uiflow3_callback"
    assert route["flow_type"] == "content_first_canonical"
    assert tuple(route["expected_children"]) == expected_children
    state = video_uiflow3.new_state(product, draft_id="entry-video-ai-real")
    _text, markup = bot.video_uiflow3_screen_payload(state)
    callbacks = _callbacks(markup)
    assert tuple(item for item in callbacks if item != "menu|main_video") == expected_children
    assert callbacks.count("menu|main_video") == 1


def test_script_and_selfshot_entries_keep_distinct_product_owners() -> None:
    script_route = bot.VIDEO_PUBLIC_ROUTE_MATRIX["script_image_video"]
    assert script_route["entry_callback"] == "vproduct|open|script_image_video"
    assert script_route["handler"] == "handle_video_product_callback"
    assert tuple(script_route["expected_children"]) == (
        "vproduct|script_ai",
        "vproduct|script_manual",
        "vproduct|script_upload",
        "menu|main_video",
    )
    assert _callbacks(bot.video_script_hub_keyboard()) == list(script_route["expected_children"])

    hub_route = bot.VIDEO_PUBLIC_ROUTE_MATRIX["self_shot_scene_change"]
    assert hub_route["entry_callback"] == "vproduct|open|self_shot_scene_change"
    assert hub_route["handler"] == "handle_video_product_callback"
    assert tuple(hub_route["expected_children"]) == (
        "vproduct|selfshot_product|scene_change",
        "vproduct|selfshot_product|cinematic",
    )
    hub_callbacks = _callbacks(bot.video_selfshot_product_hub_keyboard())
    assert hub_callbacks[:2] == list(hub_route["expected_children"])
    assert hub_callbacks[-2:] == ["menu|main_video", "menu|main"]

    cinematic_route = bot.VIDEO_PUBLIC_ROUTE_MATRIX["self_shot_cinematic_transform"]
    assert cinematic_route["entry_callback"] == "vproduct|selfshot_product|cinematic"
    assert cinematic_route["handler"] == "handle_video_product_callback"


def test_locked_video_routes_remain_on_their_existing_owners() -> None:
    assert bot.VIDEO_PUBLIC_ROUTE_MATRIX["video_trend"]["entry_callback"] == "vproduct|open|video_trend"
    assert bot.VIDEO_PUBLIC_ROUTE_MATRIX["video_idea"]["entry_callback"] == "videoidea|start"
    assert bot.VIDEO_PUBLIC_ROUTE_MATRIX["multi_scene_film"]["entry_callback"] == "longvideo|public_guard"
    assert bot.VIDEO_PUBLIC_ROUTE_MATRIX["video_local_edit"]["entry_callback"] == "videoedit|hub"
    assert bot.VIDEO_PUBLIC_ROUTE_MATRIX["frame_video_local"]["entry_callback"] == "vproduct|open|frame_video_local"
    assert bot.VIDEO_PUBLIC_ROUTE_MATRIX["storyboard_prompt"]["entry_callback"] == "vproduct|open|storyboard_prompt"


def test_each_content_profile_has_five_specific_suggestions_in_each_distinct_flow() -> None:
    script_signatures = set()
    selfshot2_signatures = set()
    selfshot3_signatures = set()
    for index, profile in enumerate(video_selfshot2.CONTENT_PROFILE_ROWS, 1):
        profile_key = str(profile["profile_key"])
        profile_name = str(profile["public_name"])

        script_rows = video_script_product.profile_content_suggestions(profile_key)[:5]
        assert len(script_rows) == 5
        script_signatures.add(tuple(str(item["brief"]) for item in script_rows))

        selfshot2_rows = video_selfshot2.suggestion_catalog(
            {},
            {},
            scene_count=2,
            aspect_ratio="9:16",
            profile=profile_name,
        )[:5]
        assert len(selfshot2_rows) == 5
        selfshot2_signatures.add(tuple(str(item["summary"]) for item in selfshot2_rows))

        group = video_selfshot3.transformation_group_for_content_profile(index)
        selfshot3_rows = video_selfshot3.contextual_preset_page({
            "selected_group_id": group["group_id"],
            "preset_page": 1,
            "preset_source": "content_profile",
            "content_profile_key": profile_key,
        })
        assert len(selfshot3_rows) == 5
        selfshot3_signatures.add(tuple(str(item["summary"]) for item in selfshot3_rows))

    profile_count = len(video_selfshot2.CONTENT_PROFILE_ROWS)
    assert profile_count == 32
    assert len(script_signatures) == profile_count
    assert len(selfshot2_signatures) == profile_count
    assert len(selfshot3_signatures) == profile_count


def test_selfshot_source_intake_is_product_specific_and_has_no_skip_before_media() -> None:
    scene_change = video_selfshot2.screen_model("intro", video_selfshot2.initial_draft())
    cinematic = video_selfshot3.screen_model("intro", video_selfshot3.initial_draft())
    scene_callbacks = [callback for row in scene_change["rows"] for _label, callback in row]
    cinematic_callbacks = [callback for row in cinematic["rows"] for _label, callback in row]
    assert "vproduct|ss2|source" in scene_callbacks
    assert "vproduct|ss3|source" in cinematic_callbacks
    assert all("image_ai" not in item for item in [*scene_callbacks, *cinematic_callbacks])
    assert all("source_done" not in item for item in [*scene_callbacks, *cinematic_callbacks])


def test_cinematic_selfshot_every_screen_has_exact_back_and_professional_rows() -> None:
    state = video_selfshot3.initial_draft()
    for screen, parent in video_selfshot3.SCREEN_PARENTS.items():
        model = video_selfshot3.screen_model(screen, state)
        back_callback = (
            "vproduct|selfshot_hub"
            if parent == "hub"
            else f"vproduct|ss3|show|{parent}"
        )
        result = video_selfshot3.validate_rows(
            model["rows"],
            back_callback=back_callback,
        )
        assert result["ok"] is True, (screen, result["errors"])


def test_shared_tail_branding_has_all_positions_and_returns_to_branding_parent() -> None:
    position_text = bot.video_tail9_position_text("logo")
    callbacks = _callbacks(bot.video_tail9_position_keyboard("logo"))
    assert "Chọn vị trí logo" in position_text
    assert len([item for item in callbacks if item.startswith("video_tail|logo|setpos|logo|")]) == 9
    assert callbacks[-2:] == ["video_tail|logo|open", "menu|main_video"]


def test_distinct_products_keep_distinct_execution_adapters() -> None:
    expected = {
        "script_image_video": ("scene3", "script_to_video", "product_video"),
        "self_shot_scene_change": ("selfshot2", "self_shot_scene_change", "selfshot2"),
        "self_shot_cinematic_transform": ("selfshot3", "self_shot_cinematic_transform", "selfshot3"),
    }
    for product, values in expected.items():
        adapter = video_tail9.adapter_for(product)
        assert (
            adapter["flow_owner"],
            adapter["engine_route"],
            adapter["worker_owner"],
        ) == values


def test_fifteen_second_quality_is_selective_and_does_not_unlock_protected_products() -> None:
    extended = (
        "video_ai_real",
        "video_ai_prompt",
        "video_ai_image",
        "script_image_video",
        "self_shot_scene_change",
        "self_shot_cinematic_transform",
    )
    protected = ("video_trend", "video_idea", "multi_scene_film", "video_long")

    for product in extended:
        assert 700 in video_tail9.commercial_contract(product)["supported_quality_tiers"]
    for product in protected:
        assert 700 not in video_tail9.commercial_contract(product)["supported_quality_tiers"]
