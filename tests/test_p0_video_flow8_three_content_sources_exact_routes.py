from __future__ import annotations

import re
from pathlib import Path

from services import video_flow6, video_flow7, video_scene3_flow


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    markers = (f"def {name}(", f"async def {name}(")
    starts = [BOT_SOURCE.find(marker) for marker in markers]
    start = min(position for position in starts if position >= 0)
    next_def = re.search(r"\n(?:async )?def [A-Za-z_]", BOT_SOURCE[start + 1 :])
    end = start + 1 + next_def.start() if next_def else len(BOT_SOURCE)
    return BOT_SOURCE[start:end]


def _state(input_type: str, *, assets: dict | None = None) -> dict:
    return {
        "source_product_id": "video_ai_real",
        "product_type": "video_ai_real",
        "flow8_direct_entry": True,
        "step": "asset_gate",
        "scene_count": 3,
        "aspect_ratio": "9:16",
        "ai_input_type": input_type,
        "reference_assets": dict(assets or {}),
        "provider_called": False,
        "image_provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "files_generated": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }


def test_ai_real_uses_scene_ratio_input_then_three_content_sources() -> None:
    assert video_flow7.product_sequence("video_ai_real")[:4] == (
        "scene_count",
        "aspect_ratio",
        "ai_input_type",
        "content_source",
    )
    callbacks = [
        callback
        for row in video_flow7.entry_rows("video_ai_real")
        for _label, callback in row
    ]
    assert callbacks == [
        "vprofile|ai_input|prompt_video",
        "vprofile|ai_input|image_video",
        "vprofile|ai_input|video_video",
        "vproduct|open|video_ai_real",
    ]


def test_prompt_image_and_video_have_distinct_asset_requirements() -> None:
    prompt = video_flow6.context_from_scene_state(_state("prompt_video"))
    image = video_flow6.context_from_scene_state(_state("image_video"))
    video = video_flow6.context_from_scene_state(_state("video_video"))

    assert video_flow6.asset_gate_status(prompt) == {
        "ok": True,
        "requirement": "optional",
        "required": 0,
        "received": 0,
        "blocker": "",
    }
    assert video_flow6.asset_gate_status(image)["blocker"] == "reference_image_missing"
    assert video_flow6.asset_gate_status(image)["required"] == 1
    assert video_flow6.asset_gate_status(video)["blocker"] == "source_video_missing"
    assert video_flow6.asset_gate_status(video)["required"] == 1


def test_only_the_matching_reference_type_unlocks_each_gate() -> None:
    image_asset = {"items": [{"file_id": "image-1", "media_kind": "image"}]}
    video_asset = {
        "items": [{"file_id": "video-1", "media_kind": "video"}],
        "source_media_ref": "video-1",
    }

    assert video_flow6.asset_gate_status(
        video_flow6.context_from_scene_state(_state("image_video", assets=image_asset))
    )["ok"] is True
    assert video_flow6.asset_gate_status(
        video_flow6.context_from_scene_state(_state("image_video", assets=video_asset))
    )["ok"] is False
    assert video_flow6.asset_gate_status(
        video_flow6.context_from_scene_state(_state("video_video", assets=video_asset))
    )["ok"] is True
    assert video_flow6.asset_gate_status(
        video_flow6.context_from_scene_state(_state("video_video", assets=image_asset))
    )["ok"] is False


def test_flow8_asset_back_is_exact_and_does_not_open_another_product() -> None:
    for input_type in ("image_video", "video_video"):
        assert video_scene3_flow.canonical_back_step(_state(input_type)) == "ai_input_type"
    assert video_scene3_flow.canonical_back_step(
        {**_state("prompt_video"), "step": "content_source"}
    ) == "ai_input_type"
    assert video_scene3_flow.canonical_back_step(
        {**_state("prompt_video"), "step": "technical_profile", "content_source": "profiles"}
    ) == "content_source"
    assert video_scene3_flow.canonical_back_step(
        {**_state("prompt_video"), "step": "await_suggestion", "content_source": "manual"}
    ) == "content_source"


def test_scene_state_sync_preserves_input_and_content_source_truth() -> None:
    state = {
        **_state("image_video", assets={"items": [{"file_id": "image-1", "media_kind": "image"}]}),
        "content_source": "profiles",
        "content_mode": "suggestions",
    }
    synced = video_flow6.sync_scene_state(state)
    assert synced["ai_input_type"] == "image_video"
    assert synced["content_source"] == "profiles"
    assert synced["asset_requirement"] == "single_image_required"
    assert synced["video_flow_context"]["source_fields"]["ai_input_type"] == "image_video"
    assert synced["video_flow_context"]["source_fields"]["content_source"] == "profiles"


def test_public_input_source_ratio_and_suggestion_keyboards_match_contract() -> None:
    input_keyboard = _function_source("video_scene3_ai_input_keyboard")
    source_keyboard = _function_source("video_scene3_content_source_keyboard")
    ratio_keyboard = _function_source("video_scene3_aspect_keyboard")
    suggestion_keyboard = _function_source("video_scene3_suggestion_keyboard")

    for callback in (
        "vprofile|ai_input|prompt_video",
        "vprofile|ai_input|image_video",
        "vprofile|ai_input|video_video",
    ):
        assert input_keyboard.count(callback) == 1
    for callback in (
        "vprofile|source|profiles",
        "vprofile|source|idea",
        "vprofile|source|manual",
    ):
        assert source_keyboard.count(callback) == 1
    assert "ratio_custom" not in ratio_keyboard
    assert "ratio_suggest" not in ratio_keyboard
    assert "number_buttons," in suggestion_keyboard
    assert "number_buttons[:2]" not in suggestion_keyboard
    assert "number_buttons[2:4]" not in suggestion_keyboard


def test_callback_owner_routes_required_assets_before_content_source() -> None:
    handler = _function_source("handle_video_profile_studio_callback")
    assert handler.count('if action == "ai_input":') == 1
    assert handler.count('if action == "source":') == 1
    assert '"ai_input": {"ai_input_type"}' in BOT_SOURCE
    assert '"source": {"content_source"}' in BOT_SOURCE
    assert '"ai_input": {"ai_input_type", "aspect_ratio"}' not in BOT_SOURCE
    assert '"source": {"content_source", "ai_input_type"}' not in BOT_SOURCE
    assert 'next_step = "asset_gate" if selected in {"image_video", "video_video"} else "content_source"' in handler
    assert 'flow8_asset_return_step="content_source" if next_step == "asset_gate" else ""' in handler
    assert 'and str(state.get("flow8_asset_return_step") or "") == "content_source"' in handler
    assert '"content_source",' in handler


def test_media_intake_accepts_one_reference_and_deduplicates_message_id() -> None:
    intake = _function_source("handle_video_scene3_pending_media")
    assert 'if message_id and message_id in processed_message_ids:' in intake
    assert 'if requirement == "single_image_required"' in intake
    assert '"reference_image" if requirement == "single_image_required"' in intake
    assert '1\n                if requirement == "single_image_required"' in intake
    assert "một video tham chiếu" in intake
    assert "một ảnh tham chiếu" in intake
    assert "provider_called" not in intake


def test_planning_gate_has_zero_side_effects_before_final_confirmation() -> None:
    context = video_flow6.context_from_scene_state(_state("image_video"))
    result = video_flow6.preflight(
        context,
        package_available=True,
        engine_ready=True,
        worker_ready=True,
        capability_ready=True,
    )
    assert result["ok"] is False
    assert result["side_effects"] == {
        "job": 0,
        "outbox": 0,
        "invoice": 0,
        "provider_calls": 0,
        "rendered_files": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }


def test_script_storyboard_long_video_and_excluded_flows_remain_distinct() -> None:
    assert "scene_count_confirm" in video_flow7.product_sequence("script_image_video")
    assert video_flow7.product_sequence("storyboard_prompt")[0] == "panel_count"
    assert video_flow7.product_sequence("self_shot_scene_change")[0] == "source_video"
    assert video_flow7.product_sequence("multi_scene_film")[0] == "series_bible"
    storyboard_callbacks = [
        callback
        for row in video_flow7.entry_rows("storyboard_prompt")
        for _label, callback in row
    ]
    assert storyboard_callbacks == ["vstory|ai", "vstory|upload"]
