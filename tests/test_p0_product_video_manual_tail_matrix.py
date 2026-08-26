from __future__ import annotations

from pathlib import Path

import pytest

import bot
from services import video_tail9


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    starts = [
        BOT_SOURCE.find(marker)
        for marker in (f"def {name}(", f"async def {name}(")
    ]
    start = min(position for position in starts if position >= 0)
    ends = [
        position
        for marker in ("\ndef ", "\nasync def ")
        if (position := BOT_SOURCE.find(marker, start + 1)) >= 0
    ]
    return BOT_SOURCE[start:min(ends) if ends else len(BOT_SOURCE)]


MANUAL_LANES = (
    ("trend_manual_input", "video_trend", (), ()),
    ("awaiting_prompt_text", "video_ai_real", (), ()),
    ("awaiting_existing_script", "script_image_video", (), ()),
    ("script_manual_topic", "script_image_video", (), ()),
    (
        "storyboard_manual_input",
        "storyboard_prompt",
        ("storyboard-frame-1", "storyboard-frame-2"),
        (
            {
                "file_id": "storyboard-frame-1",
                "media_kind": "image",
                "scene_index": 1,
                "slot": "start",
            },
            {
                "file_id": "storyboard-frame-2",
                "media_kind": "image",
                "scene_index": 2,
                "slot": "start",
            },
        ),
    ),
    ("film_manual_topic", "multi_scene_film", (), ()),
    ("film_script_input", "multi_scene_film", (), ()),
    ("video_idea_manual_topic", "video_idea", (), ()),
    (
        "image_to_video_custom_topic",
        "frame_video_local",
        ("frame-image-1", "frame-image-2"),
        (
            {"file_id": "frame-image-1", "media_kind": "image"},
            {"file_id": "frame-image-2", "media_kind": "image"},
        ),
    ),
    (
        "self_shot_custom_topic",
        "self_shot_scene_change",
        ("selfshot-video-1",),
        ({"file_id": "selfshot-video-1", "media_kind": "video"},),
    ),
)


@pytest.mark.parametrize(
    ("origin_step", "product_id", "source_media_refs", "source_asset_items"),
    MANUAL_LANES,
)
def test_manual_lane_builds_provider_free_two_scene_shared_tail_contract(
    origin_step: str,
    product_id: str,
    source_media_refs: tuple[str, ...],
    source_asset_items: tuple[dict, ...],
) -> None:
    manual_text = f"Kich ban rieng cho {product_id}: canh mot mo dau, canh hai ket qua."

    result = bot.video_manual_lane_shared_tail_contract(
        product_id,
        manual_text,
        origin_step=origin_step,
        source_media_refs=list(source_media_refs),
        source_asset_items=[dict(item) for item in source_asset_items],
    )

    state = result["state"]
    tail = result["tail"]
    contract = result["content_contract"]
    minimum = max(
        2,
        int(video_tail9.commercial_contract(product_id)["minimum_scene_count"]),
    )

    assert result["origin_step"] == origin_step
    assert result["manual_text"] == manual_text
    assert result["provider_calls"] == 0
    assert result["jobs_created"] == 0
    assert result["outboxes_created"] == 0
    assert result["wallet_mutations"] == 0
    assert result["xu_charged"] == 0
    assert result["asset_gate"]["ok"] is True
    assert state["content_mode"] == "manual"
    assert state["content_source"] == "manual"
    assert state["manual_content"] == manual_text
    assert state["scene_count"] == minimum
    assert len((state.get("plan") or {}).get("scenes") or []) == minimum
    assert contract["manual_content"] == manual_text
    assert contract["canonical_content_mode"]
    assert tail["video_product_type"] == product_id
    assert tail["scene_count"] == minimum
    assert video_tail9.next_required_screen(tail) == "addon"
    assert tuple(result["tail_order"]) == (
        "addon",
        "review",
        "quality",
        "invoice",
        "confirm",
        "status",
    )
    assert tuple(tail.get("source_asset_ids") or ()) == source_media_refs


def test_manual_lane_matrix_is_wired_to_both_real_pending_text_owners() -> None:
    product_pending = _function_source("handle_video_product_pending_text")
    uiflow3_pending = _function_source("handle_video_uiflow3_pending_text")
    trend_pending = _function_source("handle_video_trend2_pending_text")
    profile_pending = _function_source("handle_video_profile_studio_pending_text")
    tail_callback = _function_source("handle_video_tail_callback")

    assert "VIDEO_MANUAL_DIRECT_TAIL_STEPS" in product_pending
    assert "video_manual_lane_open_shared_tail" in product_pending
    assert 'kind == "manual_content"' in uiflow3_pending
    assert "video_manual_lane_open_shared_tail" in uiflow3_pending
    assert 'pending in {"manual_trend", "manual_content", "edit_content"}' in trend_pending
    assert "video_manual_lane_open_shared_tail" in trend_pending
    assert 'step == "await_suggestion"' in profile_pending
    assert "VIDEO_PROFILE_MANUAL_DIRECT_TAIL_PRODUCTS" in profile_pending
    assert "video_manual_lane_open_shared_tail" in profile_pending
    assert 'tail.get("manual_direct_tail")' in tail_callback
    assert 'tail.get("manual_origin_step")' in tail_callback
    assert 'origin_step == "scene3_await_suggestion"' in tail_callback
    assert 'current["step"] = "await_suggestion"' in tail_callback
    open_tail = _function_source("video_manual_lane_open_shared_tail")
    assert "video_profile_scene1_handoff" in open_tail
    assert 'VIDEO_TAIL9_STATE_KEY: tail' in open_tail
    assert '"provider_called": False' in open_tail
    assert '"job_created": False' in open_tail
    assert '"wallet_mutations": 0' in open_tail
    assert 'draft["manual_owner_snapshot"] = owner_state' in open_tail


def test_canonical_manual_owners_enter_the_same_asset_gated_tail() -> None:
    uiflow3_pending = _function_source("handle_video_uiflow3_pending_text")
    storyboard_callback = _function_source("_handle_storyboard2_callback_impl")
    selfshot_pending = _function_source("handle_video_product_pending_text")
    idea_pending = _function_source("handle_video_idea_dynamic_pending_text")

    assert 'str(state.get("parent_product") or "") == "multi_scene_film"' in uiflow3_pending
    assert 'origin_step="uiflow3_series_goal"' in uiflow3_pending
    assert 'if action == "assets_done"' in storyboard_callback
    assert 'origin_step="storyboard2_assets_done"' in storyboard_callback
    assert 'elif step == "selfshot2_content_input"' in selfshot_pending
    assert 'origin_step="selfshot2_content_input"' in selfshot_pending
    assert 'step == "idea2_custom_topic"' in idea_pending
    assert 'origin_step="videoidea_dynamic_custom_topic"' in idea_pending


def test_manual_lane_matrix_matches_the_owner_checklist_exactly() -> None:
    assert bot.VIDEO_MANUAL_DIRECT_TAIL_STEPS == {
        "trend_manual_input": "video_trend",
        "awaiting_prompt_text": "video_ai_real",
        "awaiting_existing_script": "script_image_video",
        "script_manual_topic": "script_image_video",
        "storyboard_manual_input": "storyboard_prompt",
        "film_manual_topic": "multi_scene_film",
        "film_script_input": "multi_scene_film",
        "video_idea_manual_topic": "video_idea",
        "image_to_video_custom_topic": "frame_video_local",
        "self_shot_custom_topic": "self_shot_scene_change",
    }


def test_uiflow3_manual_content_is_the_same_video_ai_real_direct_tail_lane() -> None:
    assert bot.VIDEO_UIFLOW3_MANUAL_DIRECT_TAIL_PRODUCTS == frozenset({"video_ai_real"})


@pytest.mark.parametrize(
    "product_id",
    ("frame_video_local", "storyboard_prompt", "self_shot_scene_change"),
)
def test_media_dependent_manual_lane_fails_closed_before_tail_without_source(
    product_id: str,
) -> None:
    with pytest.raises(ValueError, match="video_manual_direct_tail_source_required:"):
        bot.video_manual_lane_shared_tail_contract(
            product_id,
            f"Noi dung rieng cho {product_id}",
            origin_step="source_missing_regression",
        )


def test_video_ai_real_image_manual_lane_keeps_image_executor_and_source() -> None:
    result = bot.video_manual_lane_shared_tail_contract(
        "video_ai_real",
        "Hai canh san pham my pham tu anh tham chieu.",
        origin_step="uiflow3_manual_content",
        source_media_refs=["reference-image-1"],
        source_asset_items=[
            {"file_id": "reference-image-1", "media_kind": "image"},
        ],
        entry_mode="image_video",
    )

    assert result["entry_mode"] == "image_video"
    assert result["asset_gate"]["ok"] is True
    assert result["tail"]["video_product_type"] == "video_ai_real"
    assert result["tail"]["execution_product_type"] == "video_ai_image"
    assert result["tail"]["source_asset_ids"] == ["reference-image-1"]


def test_video_ai_real_image_manual_lane_fails_closed_without_image() -> None:
    with pytest.raises(ValueError, match="reference_image_missing"):
        bot.video_manual_lane_shared_tail_contract(
            "video_ai_real",
            "Hai canh phai bam sat anh tham chieu.",
            origin_step="uiflow3_manual_content",
            entry_mode="image_video",
        )


def test_frame_manual_tail_hands_quality_to_real_frame_catalog() -> None:
    result = bot.video_manual_lane_shared_tail_contract(
        "frame_video_local",
        "Hai anh san pham theo thu tu truoc va sau.",
        origin_step="scene3_await_suggestion",
        source_media_refs=["frame-1", "frame-2"],
        source_asset_items=[
            {"file_id": "frame-1", "media_kind": "image", "scene_index": 1},
            {"file_id": "frame-2", "media_kind": "image", "scene_index": 2},
        ],
    )
    frame_state = bot.video_flow6_frame_state_from_scene3(result["state"])
    assert [item["file_id"] for item in frame_state["photos"]] == ["frame-1", "frame-2"]

    quality_render = _function_source("video_tail9_render")
    quality_keyboard = _function_source("frame_video_quality_keyboard")
    assert 'tail.get("video_product_type") or "") == "frame_video_local"' in quality_render
    assert '"commercial_flow_version": "framevideo3"' in quality_render
    assert "frame_video_quality_text(frame_state)" in quality_render
    assert "frame_video_quality_keyboard(frame_state)" in quality_render
    assert 'tail_return.startswith("video_tail|")' in quality_keyboard


def test_manual_tail_restart_hydrates_exact_parent_snapshot_for_back() -> None:
    snapshot = {
        "screen": "content_source",
        "pending_input": "manual_content",
        "scene_count": 2,
    }
    hydrated = bot.video_tail9_hydrate_scene3_host(
        {},
        {
            "draft": {
                "product_id": "video_trend",
                "manual_direct_tail": True,
                "manual_origin_step": "trend2_manual_content",
                "manual_owner_snapshot": snapshot,
            }
        },
    )

    assert hydrated["manual_direct_tail"] is True
    assert hydrated["manual_origin_step"] == "trend2_manual_content"
    assert hydrated["manual_owner_snapshot"] == snapshot
