from __future__ import annotations

from pathlib import Path

import pytest

from services import video_idea_catalog


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _between(start: str, end: str) -> str:
    left = BOT_SOURCE.index(start)
    right = BOT_SOURCE.index(end, left + len(start))
    return BOT_SOURCE[left:right]


def _sample_plan(scene_count: int = 3) -> dict:
    return video_idea_catalog.build_plan(
        video_idea_catalog.IDEAS[0],
        scene_count=scene_count,
        source_mode="text_prompt",
    )


def _assert_preconfirm_zero(state: dict) -> None:
    assert state["provider_called"] is False
    assert state["image_provider_called"] is False
    assert state["music_provider_calls"] == 0
    assert state["voice_provider_calls"] == 0
    assert state["files_generated"] == 0
    assert state["job_created"] is False
    assert state["outbox_created"] is False
    assert state["wallet_mutations"] == 0
    assert state["xu_charged"] == 0
    assert state["final_confirmed"] is False


def test_product_idea_lane_scope_is_explicit_and_excludes_unrelated_products():
    assert video_idea_catalog.IDEA_PRODUCT_HANDOFFS == {
        "video_trend",
        "video_ai_real",
        "script_image_video",
        "storyboard_prompt",
        "self_shot_scene_change",
    }
    assert "frame_video_local" not in video_idea_catalog.IDEA_PRODUCT_HANDOFFS
    assert "multi_scene_film" not in video_idea_catalog.IDEA_PRODUCT_HANDOFFS


@pytest.mark.parametrize(
    "product_id",
    ["video_trend", "video_ai_real", "script_image_video"],
)
def test_regular_product_handoff_keeps_exact_scene_count_and_editable_prompts(product_id: str):
    state = video_idea_catalog.build_scene3_handoff_state(
        _sample_plan(5),
        product_id_override=product_id,
    )
    assert state["product_type"] == product_id
    assert state["source_product_id"] == product_id
    assert state["scene_count"] == 5
    assert state["step"] == "video_prompts"
    assert set(state["video_prompt_versions"]) == {"1", "2", "3", "4", "5"}
    assert all(not row["approved"] for row in state["video_prompt_versions"].values())
    _assert_preconfirm_zero(state)


def test_storyboard_idea_handoff_requires_an_image_source_for_every_scene():
    state = video_idea_catalog.build_scene3_handoff_state(
        _sample_plan(3),
        product_id_override="storyboard_prompt",
    )
    assert state["step"] == "image_strategy"
    assert state["storyboard_image_required"] is True
    assert state["storyboard_allowed_image_strategies"] == ["uploaded_image", "ai_image"]
    assert set(state["video_prompt_versions"]) == {"1", "2", "3"}
    _assert_preconfirm_zero(state)


def test_self_shot_idea_handoff_blocks_without_source_video_and_preserves_one_when_present():
    with pytest.raises(ValueError, match="self_shot_source_video_required"):
        video_idea_catalog.build_scene3_handoff_state(
            _sample_plan(2),
            product_id_override="self_shot_scene_change",
        )

    plan = _sample_plan(2)
    plan["source_media_refs"] = ["telegram-video-file-id"]
    state = video_idea_catalog.build_scene3_handoff_state(
        plan,
        product_id_override="self_shot_scene_change",
    )
    assert state["step"] == "video_prompts"
    assert state["source_media_ref"] == "telegram-video-file-id"
    assert state["source_media_refs"] == ["telegram-video-file-id"]
    assert state["source_media_type"] == "video"
    _assert_preconfirm_zero(state)


def test_public_entries_use_prompt_wording_and_only_show_idea_lane_at_the_right_time():
    intro = _between("def task3d_product_intro_keyboard", "\n\nVIDEO_B14_PUBLIC_UNSTABLE_TOOL_MESSAGE")
    ai_prompt = _between("def video_microflow_keyboard", "\n\ndef video_microflow_normalize_topic")

    assert '("✨ Prompt AI → Video", "vproduct|ai_prompt_menu|video_ai_real")' in intro
    assert '"vproduct|idea_library|video_trend"' in intro
    assert '"vproduct|idea_library|script_image_video"' in intro
    assert '"vproduct|idea_library|storyboard_prompt"' in intro
    assert '"vproduct|idea_library|video_ai_real"' in ai_prompt
    assert '"vproduct|idea_library|self_shot_scene_change"' in ai_prompt

    self_shot_intro = intro.split('"self_shot_scene_change": [', 1)[1].split('"multi_scene_film": [', 1)[0]
    assert '"vproduct|selfshot_source|upload"' in self_shot_intro
    assert "idea_library" not in self_shot_intro

    assert "Nhập chủ đề riêng" not in intro
    assert "Nhập chủ đề riêng" not in ai_prompt


def test_frame_slideshow_and_long_form_guard_do_not_receive_the_scene3_idea_lane():
    intro = _between("def task3d_product_intro_keyboard", "\n\nVIDEO_B14_PUBLIC_UNSTABLE_TOOL_MESSAGE")
    frame = intro.split('"frame_video_local": [', 1)[1].split('"video_ai_real": [', 1)[0]
    long_form = intro.split('"multi_scene_film": [', 1)[1].split('"video_reference": [', 1)[0]
    assert "idea_library" not in frame
    assert "idea_library" not in long_form

    matrix = _between("VIDEO_PUBLIC_ROUTE_MATRIX = {", "\n\n\ndef video_public_route_for_tool")
    assert '"entry_callback": "longvideo|public_guard"' in matrix
    assert '"flow_type": "development_guard"' in matrix


def test_product_catalog_back_stack_and_legacy_guards_are_source_bound_and_read_only():
    callback = _between("async def handle_video_product_callback", "\n\nasync def handle_video_product_pending_text")
    dynamic = _between("async def handle_video_idea_dynamic_callback", "\n\ndef video_idea_admin_main_text")
    image_strategy = _between("def video_scene3_image_strategy_text", "\n\ndef video_scene3_prompt_text")
    image_source = _between("def video_scene3_image_source_keyboard", "\n\ndef video_scene3_image_assets_text")

    assert 'requested_product != product_id' in callback
    assert 'requested_product not in VIDEO_IDEA_PRODUCT_LANE_PRODUCTS' in callback
    assert 'back_callback=f"vproduct|idea_back|{requested_product}"' in callback
    assert 'context.user_data.pop("video_idea_origin_product", None)' in callback
    assert 'context.user_data.pop("video_idea_source_media_refs", None)' in callback
    assert 'action == "selfshot_continue"' in callback
    assert 'if not source_refs:' in callback

    assert 'product_id_override=lane_product' in BOT_SOURCE
    assert '"origin": "video_idea_product_lane" if lane_product' in BOT_SOURCE
    assert 'video_idea_dynamic_scene3_state(state)' in dynamic
    assert "create_product_video_job" not in dynamic
    assert "provider.submit" not in dynamic

    assert 'if bool((state or {}).get("storyboard_image_required"))' in image_strategy
    assert "video_scene3_image_source_keyboard(state)" in image_strategy
    assert "Gửi ảnh có sẵn" in image_source
    assert "Tạo ảnh mới" in image_source
    assert "image_strategy_upload" not in image_strategy


def test_public_idea_lane_never_enters_legacy_planning_interceptor():
    legacy = _between("VIDEO_SCENE2_LEGACY_PLANNING_CALLBACKS =", "\n\n\ndef video_profile_studio_state")
    for action in ("idea_library", "idea_back", "selfshot_continue"):
        assert f'"{action}"' not in legacy
