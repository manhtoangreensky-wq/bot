from __future__ import annotations

import bot
from services import (
    video_project_queue,
    video_provider_catalog,
    video_real_render_connector,
    video_tail9,
    video_uiflow3,
)


SYNCED_PRODUCTS = (
    "video_ai_real",
    "script_image_video",
    "self_shot_scene_change",
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


def _content_lock_state(product: str) -> dict:
    state = video_uiflow3.new_state(product, draft_id=f"sync-{product}")
    return video_uiflow3.set_content_candidate(
        state,
        source="content_catalog",
        profile_id="sales_ads",
        original_intent=f"Nội dung gốc của {product} phải được giữ nguyên.",
        approved_brief={
            "title": "Bán hàng / quảng cáo",
            "goal": "Giới thiệu giá trị rõ ràng",
        },
    )


def test_approved_products_use_exact_uiflow3_entry_owner_and_menu_back() -> None:
    expected_children = {
        "video_ai_real": ("vid3|mode|prompt_video", "vid3|mode|image_video"),
        "script_image_video": ("vid3|source_text",),
        "self_shot_scene_change": ("vid3|source_media", "vid3|source_status"),
    }
    for product in SYNCED_PRODUCTS:
        route = bot.VIDEO_PUBLIC_ROUTE_MATRIX[product]
        assert route["entry_callback"] == f"vid3|entry|{product}"
        assert route["handler"] == "handle_video_uiflow3_callback"
        assert route["flow_type"] == "content_first_canonical"
        assert tuple(route["expected_children"]) == expected_children[product]
        state = video_uiflow3.new_state(product, draft_id=f"entry-{product}")
        _text, markup = bot.video_uiflow3_screen_payload(state)
        callbacks = _callbacks(markup)
        assert tuple(item for item in callbacks if item != "menu|main_video") == expected_children[product]
        assert callbacks.count("menu|main_video") == 1


def test_locked_video_routes_remain_on_their_existing_owners() -> None:
    assert bot.VIDEO_PUBLIC_ROUTE_MATRIX["video_trend"]["entry_callback"] == "vproduct|open|video_trend"
    assert bot.VIDEO_PUBLIC_ROUTE_MATRIX["video_idea"]["entry_callback"] == "videoidea|start"
    assert bot.VIDEO_PUBLIC_ROUTE_MATRIX["multi_scene_film"]["entry_callback"] == "longvideo|public_guard"
    assert bot.VIDEO_PUBLIC_ROUTE_MATRIX["video_local_edit"]["entry_callback"] == "videoedit|hub"
    assert bot.VIDEO_PUBLIC_ROUTE_MATRIX["frame_video_local"]["entry_callback"] == "vproduct|open|frame_video_local"
    assert bot.VIDEO_PUBLIC_ROUTE_MATRIX["storyboard_prompt"]["entry_callback"] == "vproduct|open|storyboard_prompt"


def test_each_synced_non_pilot_product_has_five_ordered_specific_suggestions() -> None:
    prompts: dict[str, str] = {}
    for product in SYNCED_PRODUCTS[1:]:
        state = _content_lock_state(product)
        suggestions = bot.video_uiflow3_profile_context_prompts(state)
        assert [item["key"] for item in suggestions] == [
            "product_context_01",
            "product_context_02",
            "product_context_03",
            "product_context_04",
            "product_context_05",
        ]
        _text, markup = bot.video_uiflow3_screen_payload(state)
        context_rows = [
            row for row in _rows(markup)
            if any(callback.startswith("vid3|context|") for _label, callback in row)
        ]
        assert [len(row) for row in context_rows] == [2, 2, 1]
        assert [
            callback for row in context_rows for _label, callback in row
        ] == [f"vid3|context|product_context_{index:02d}" for index in range(1, 6)]

        selected = bot.video_uiflow3_apply_context_prompt(state, "product_context_03")
        brief = dict(selected["content"]["approved_brief"])
        assert selected["content"]["original_intent"] == state["content"]["original_intent"]
        assert brief["context_suggestion_key"] == "product_context_03"
        assert brief["prompt"] == suggestions[2]["prompt"]
        assert brief["prompt"] in bot.video_uiflow3_screen_payload(selected)[0]
        prompts[product] = brief["prompt"]
    assert len(set(prompts.values())) == len(prompts)


def test_selfshot_source_intake_is_product_specific_and_has_no_skip_before_media() -> None:
    selfshot_text, selfshot_markup = bot.video_uiflow3_screen_payload(
        video_uiflow3.new_state("self_shot_scene_change", draft_id="selfshot-source")
    )
    assert "VIDEO TỰ QUAY ĐẦU VÀO" in selfshot_text
    assert "vid3|source_media" in _callbacks(selfshot_markup)
    assert "vid3|image_ai|source" not in _callbacks(selfshot_markup)
    assert "vid3|source_done" not in _callbacks(selfshot_markup)


def test_non_pilot_branding_shows_positions_and_returns_to_branding_parent() -> None:
    state = video_uiflow3.new_state("script_image_video", draft_id="brand-position")
    state["navigation"]["current_step"] = "branding"
    state["branding"] = {
        "logo": {
            "telegram_file_id": "logo-file",
            "file_name": "logo.png",
            "position": "top_right",
        },
        "watermark": {
            "text": "TOAN AAS",
            "position": "bottom_right",
        },
    }
    text, markup = bot.video_uiflow3_screen_payload(state)
    assert "Vị trí" in text
    assert "vid3|brand_position_view|logo" in _callbacks(markup)
    assert "vid3|brand_position_view|watermark" in _callbacks(markup)

    state["ui_view"] = "branding_logo_position"
    position_text, position_markup = bot.video_uiflow3_screen_payload(state)
    callbacks = _callbacks(position_markup)
    assert "Trên phải" in position_text
    assert callbacks.count("vid3|view|branding") == 1
    assert len([item for item in callbacks if item.startswith("vid3|brand_position|logo|")]) == 9


def test_synced_products_keep_distinct_execution_adapters() -> None:
    expected = {
        "script_image_video": "product_tail",
        "self_shot_scene_change": "selfshot2",
    }
    for product, kind in expected.items():
        state = video_uiflow3.new_state(product, draft_id=f"adapter-{product}")
        assert bot.video_uiflow3_execution_adapter(state)["kind"] == kind


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


def test_verified_uiflow3_fifteen_second_duration_is_not_clamped_by_queue_or_worker() -> None:
    identity = "a" * 64
    tasks = video_project_queue.product_video_initial_scene_tasks(
        "job-15s",
        2,
        15,
    )
    assert [item["scene_duration_seconds"] for item in tasks] == [15, 15]

    assert video_real_render_connector.product_video_scene_duration_seconds({
        "source": "product_video",
        "uiflow3_handoff_sha256": identity,
        "scene_duration_seconds": 15,
    }) == 15
    assert video_real_render_connector.product_video_scene_duration_seconds({
        "source": "product_video",
        "scene_duration_seconds": 15,
    }) == 8


def test_fifteen_second_tier_selects_the_real_long_scene_provider_contract() -> None:
    resolved = video_provider_catalog.resolve_product_video_model(
        tier=700,
        provider_chain=["key4u_video"],
        scene_count=2,
        required_capability="text_to_video",
        requires_concat=True,
        env={
            "VIDEO_PROVIDER_CHAIN": "key4u_video",
            "KEY4U_KLING_VIDEO_ENDPOINT": "https://provider.invalid/submit",
            "KEY4U_KLING_VIDEO_POLL_URL": "https://provider.invalid/poll",
        },
    )

    assert resolved["ok"] is True
    assert resolved["selected_provider"] == "key4u_video"
    assert resolved["selected_model"] == "kling-video"
    assert resolved["selected_clip_seconds"] == 15
