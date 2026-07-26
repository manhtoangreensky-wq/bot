from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path

import pytest

from services import video_idea_handoff, video_idea_prompt


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")

PARENT_CONTRACTS = {
    "video_ai_real": {
        "public_product_type": "video_ai_realistic",
        "continuation": "full_review",
        "flow_owner": "scene3",
        "engine_route": "video_ai_canonical",
    },
    "video_trend": {
        "public_product_type": "trend_video",
        "continuation": "full_review",
        "flow_owner": "trend",
        "engine_route": "trend_video",
    },
    "script_image_video": {
        "public_product_type": "script_to_video",
        "continuation": "full_review",
        "flow_owner": "scene3",
        "engine_route": "script_to_video",
    },
    "storyboard_prompt": {
        "public_product_type": "storyboard_to_video",
        "continuation": "scene_review",
        "flow_owner": "storyboard",
        "engine_route": "storyboard_to_video",
    },
    "self_shot_scene_change": {
        "public_product_type": "self_shot_scene_change",
        "continuation": "scene_plan",
        "flow_owner": "selfshot2",
        "engine_route": "self_shot_scene_change",
    },
    "self_shot_cinematic_transform": {
        "public_product_type": "self_shot_cinematic_transform",
        "continuation": "timeline",
        "flow_owner": "selfshot3",
        "engine_route": "self_shot_cinematic_transform",
    },
    "multi_scene_film": {
        "public_product_type": "long_video",
        "continuation": "full_review",
        "flow_owner": "scene3",
        "engine_route": "multi_scene_film",
    },
}


def _function_source(name: str) -> str:
    pattern = re.compile(rf"^(?:async )?def {re.escape(name)}\(", re.MULTILINE)
    match = pattern.search(BOT_SOURCE)
    assert match, f"missing function: {name}"
    next_match = re.search(r"\n(?:async )?def [A-Za-z_]", BOT_SOURCE[match.end() :])
    end = match.end() + next_match.start() if next_match else len(BOT_SOURCE)
    return BOT_SOURCE[match.start() : end]


def _parent_state(product: str) -> dict:
    state = {
        "flow_session_id": f"parent-{product}",
        "flow_revision": 11,
        "flow_kind": f"flow-{product}",
        "scene_count": 6 if product == "script_image_video" else 3,
        "aspect_ratio": "16:9",
        "subject": f"Ý tưởng của {product}",
        "selected_profile": "cinematic_product",
        "idea_return_step": video_idea_handoff.NEXT_STEPS[product],
        "trend_source": {},
        "reference_assets": {},
    }
    if product == "video_trend":
        state.update({
            "trend_id": "trend-media-17",
            "trend_title": "Một ngày sử dụng sản phẩm",
            "trend_context": "Video social chân thật, mở nhanh và kết bằng bằng chứng.",
            "trend_source": {
                "trend_id": "trend-media-17",
                "title": "Một ngày sử dụng sản phẩm",
                "summary": "Video social chân thật, mở nhanh và kết bằng bằng chứng.",
            },
        })
    if product == "script_image_video":
        state.update({
            "script_session_id": "script-session-17",
            "long_script_revision": 4,
            "manual_script_raw": "Kịch bản dài đã được khách chuẩn bị.",
        })
    if product == "storyboard_prompt":
        state.update({
            "storyboard_session_id": "storyboard-session-17",
            "storyboard2": {"session_id": "storyboard-session-17", "scene_count": 3},
        })
    if product in {"self_shot_scene_change", "self_shot_cinematic_transform"}:
        state.update({
            "selfshot_mode": product,
            "identity_lock": {"enabled": True},
            "relationship_lock": {"enabled": True},
            "motion_analysis": {"camera": "source"},
            "reference_assets": {
                "source_media_ref": f"telegram-{product}",
                "source_media_refs": [f"telegram-{product}"],
                "items": [{"file_id": f"telegram-{product}", "media_kind": "video"}],
            },
        })
    if product == "self_shot_cinematic_transform":
        state.update({
            "environment": "khu vườn điện ảnh",
            "wardrobe": "trang phục biến đổi liên tục",
            "effects": ["ánh sáng", "cánh hoa"],
            "timeline": [{"stage": 1}, {"stage": 2}],
        })
    if product == "multi_scene_film":
        state["long_video_mode"] = "chapter_5_minutes"
    return state


def _selected_state(product: str) -> tuple[dict, dict]:
    parent = _parent_state(product)
    handoff = video_idea_handoff.build_parent_handoff(
        parent,
        product_id=product,
        return_callback=f"vproduct|idea_back|{product}",
    )
    state = {
        "idea_preset_id": 496,
        "idea_id": "preset-proof-before-after",
        "idea_title": "Trước và sau có bằng chứng",
        "idea_preset_content": {
            "preset_key": "preset-proof-before-after",
            "title": "Trước và sau có bằng chứng",
            "description": "Mở vấn đề, thực hiện giải pháp và khép bằng kết quả.",
            "recommended_profile_id": "cinematic_product",
        },
        "idea_content": "Mở vấn đề, thực hiện giải pháp và khép bằng kết quả.",
        "scene_count": parent["scene_count"],
        "ratio": "16:9",
        "trend_source": deepcopy(parent.get("trend_source") or {}),
        "idea_parent_handoff": handoff,
    }
    selected = video_idea_prompt.select_prompt(
        video_idea_prompt.prepare_prompt_selection(state, handoff),
        2,
    )
    return selected, handoff


def test_continuation_registry_has_one_exact_contract_for_every_parent_product() -> None:
    assert set(PARENT_CONTRACTS) <= set(video_idea_handoff.CONTINUATION_REGISTRY)
    for product, expected in PARENT_CONTRACTS.items():
        assert video_idea_handoff.continuation_contract(product) == {
            "product_id": product,
            **expected,
        }


@pytest.mark.parametrize("product", PARENT_CONTRACTS)
def test_prompt_selection_round_trip_keeps_exact_parent_contract(product: str) -> None:
    selected, handoff = _selected_state(product)

    assert video_idea_prompt.validate_return_state(selected)["ok"] is True
    assert video_idea_handoff.parent_session_matches(selected, handoff) is True

    restored = video_idea_handoff.apply_parent_handoff(selected, handoff)
    expected = PARENT_CONTRACTS[product]
    assert restored["source_product_id"] == product
    assert restored["product_type"] == expected["public_product_type"]
    assert restored["flow_owner"] == expected["flow_owner"]
    assert restored["engine_route"] == expected["engine_route"]
    assert restored["idea_parent_continuation"] == expected["continuation"]
    assert restored["idea_parent_session_id"] == f"parent-{product}"
    assert restored["idea_parent_revision"] == 11
    assert restored["content_source"] == "idea_catalog"
    assert restored["idea_id"] == "preset-proof-before-after"
    assert restored["selected_prompt_id"]
    assert restored["selected_prompt_text"] == restored["idea_selected_prompt"]
    assert restored["selected_prompt_revision"] == 11
    assert restored["prompt_style"]
    assert video_idea_prompt.safety_report(restored) == {
        "job": 0,
        "outbox": 0,
        "provider_calls": 0,
        "image_provider_calls": 0,
        "generated_files": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }


def test_product_specific_context_survives_the_idea_catalog_round_trip() -> None:
    trend, trend_handoff = _selected_state("video_trend")
    trend_restored = video_idea_handoff.apply_parent_handoff(trend, trend_handoff)
    assert trend_restored["trend_id"] == "trend-media-17"
    assert trend_restored["trend_title"] == "Một ngày sử dụng sản phẩm"
    assert "social chân thật" in trend_restored["trend_context"]

    script, script_handoff = _selected_state("script_image_video")
    script_restored = video_idea_handoff.apply_parent_handoff(script, script_handoff)
    assert script_restored["script_session_id"] == "script-session-17"
    assert script_restored["long_script_revision"] == 4
    assert script_restored["manual_script_raw"] == "Kịch bản dài đã được khách chuẩn bị."

    storyboard, storyboard_handoff = _selected_state("storyboard_prompt")
    storyboard_restored = video_idea_handoff.apply_parent_handoff(
        storyboard, storyboard_handoff
    )
    assert storyboard_restored["storyboard_session_id"] == "storyboard-session-17"

    for product in ("self_shot_scene_change", "self_shot_cinematic_transform"):
        selected, handoff = _selected_state(product)
        restored = video_idea_handoff.apply_parent_handoff(selected, handoff)
        assert restored["source_video_id"] == f"telegram-{product}"
        assert restored["reference_assets"]["source_media_ref"] == f"telegram-{product}"
        assert restored["identity_lock"] == {"enabled": True}
        assert restored["relationship_lock"] == {"enabled": True}

    long_video, long_handoff = _selected_state("multi_scene_film")
    long_restored = video_idea_handoff.apply_parent_handoff(long_video, long_handoff)
    assert long_restored["product_type"] == "long_video"
    assert long_restored["duration_per_scene"] == 600
    assert long_restored["scene_duration_seconds"] == 600
    assert long_restored["long_video_mode"] == "chapter_5_minutes"


def test_parent_match_rejects_cross_product_revision_and_continuation_reuse() -> None:
    selected, handoff = _selected_state("video_ai_real")
    assert video_idea_handoff.parent_session_matches(selected, handoff) is True

    wrong_product = {**selected, "idea_parent_product": "video_trend"}
    wrong_revision = {**selected, "idea_parent_revision": 12}
    wrong_continuation = {**selected, "idea_parent_continuation": "timeline"}
    assert video_idea_handoff.parent_session_matches(wrong_product, handoff) is False
    assert video_idea_handoff.parent_session_matches(wrong_revision, handoff) is False
    assert video_idea_handoff.parent_session_matches(wrong_continuation, handoff) is False


def test_skip_uses_a_nonempty_compiled_prompt_and_storyboard_cannot_skip() -> None:
    for product in set(PARENT_CONTRACTS) - {"storyboard_prompt"}:
        state, handoff = _selected_state(product)
        prepared = video_idea_prompt.prepare_prompt_selection(state, handoff)
        skipped = video_idea_prompt.skip_prompt(prepared)
        assert skipped["idea_prompt_skipped"] is True
        assert skipped["selected_prompt_id"]
        assert skipped["selected_prompt_text"]
        assert skipped["selected_prompt_text"] == skipped["idea_selected_prompt"]
        assert video_idea_prompt.validate_return_state(skipped)["ok"] is True

    storyboard, handoff = _selected_state("storyboard_prompt")
    with pytest.raises(ValueError, match="storyboard_prompt_required"):
        video_idea_prompt.skip_prompt(
            video_idea_prompt.prepare_prompt_selection(storyboard, handoff)
        )


def test_parent_owner_and_back_routes_do_not_infer_from_legacy_or_global_state() -> None:
    origin = _function_source("video_idea_product_lane_origin")
    back = _function_source("video_idea_catalog_back_callback")
    continuation = _function_source("video_idea_continue_to_exact_parent")

    for forbidden in (
        "idea_origin_product",
        "video_idea_origin_product",
        "message.text",
        "query.data",
    ):
        assert forbidden not in origin
    assert "normalize_parent_handoff" in origin

    assert "return_callback" in back
    assert 'or "videoidea|start"' in back
    assert "vproduct|idea_back|" not in back

    assert "video_idea_prompt.hydrate_parent_state" in continuation
    assert "video_idea_handoff.parent_session_matches" in continuation
    assert "video_idea_prompt.validate_return_state" in continuation
    assert "video_idea_handoff.apply_parent_handoff" in continuation
    assert "video_idea_render_exact_parent" in continuation
    assert "build_parent_handoff" not in continuation
    assert "clear_video_idea_parent_context" not in continuation
    assert 'context.user_data.pop("video_idea_parent_handoff"' not in continuation
    assert "Chưa thể trả prompt về đúng sản phẩm" not in continuation
    assert "frame_video_local" not in continuation


def test_exact_parent_renderer_keeps_distinct_product_continuations() -> None:
    renderer = _function_source("video_idea_render_exact_parent")

    assert 'product_id == "storyboard_prompt"' in renderer
    assert "save_storyboard2_state" in renderer
    assert 'move(board, "scene_review"' in renderer
    assert "video_selfshot2_render" in renderer
    assert '"selfshot2:scene_plan"' in renderer
    assert "video_selfshot3_render" in renderer
    assert 'target_screen = "timeline"' in renderer
    assert 'product_id == "script_image_video"' in renderer
    assert '"long_script_mode": True' in renderer
    assert 'product_id == "multi_scene_film"' in renderer
    assert '"duration_per_scene": 600' in renderer
    assert 'handoff["step"] = "full_review"' in renderer
    assert 'video_tail9_render(query, user_id, context, "logo")' in renderer
    assert "frame_video_local" not in renderer


def test_embedded_preset_goes_directly_to_prompt_and_prompt_callbacks_have_one_owner() -> None:
    dynamic = _function_source("handle_video_idea_dynamic_callback")
    preset_start = dynamic.index('if action == "preset":')
    preset_end = dynamic.index(
        '\n    state = video_idea_dynamic_state(uid)\n'
        '    preset = dict(state.get("idea_preset") or {})',
        preset_start,
    )
    preset_branch = dynamic[preset_start:preset_end]
    prompt_handler = _function_source("handle_video_idea_prompt_callback")
    keyboard = _function_source("video_idea_prompt_selection_keyboard")

    assert "video_idea_prompt.prepare_prompt_selection" in preset_branch
    assert "video_idea_prompt_selection_text" in preset_branch
    assert "video_idea_dynamic_preview_text" not in preset_branch
    assert "video_idea_dynamic_build_drafts" not in preset_branch

    assert BOT_SOURCE.count('("idea_video|", "handle_video_idea_prompt_callback")') == 1
    assert BOT_SOURCE.count(
        'CallbackQueryHandler(handle_video_idea_prompt_callback, pattern=r"^idea_video\\|")'
    ) == 1
    assert "video_idea_processed_callback_ids" in prompt_handler
    assert "Có lỗi khi xử lý lệnh" not in prompt_handler
    assert "for index in range(1, 6)" in keyboard
    assert '== "storyboard_prompt"' in keyboard


def test_scope_keeps_catalog_framevideo_edit_and_paid_execution_outside_ideatail3() -> None:
    changed_services = (
        (ROOT / "services" / "video_idea_handoff.py").read_text(encoding="utf-8")
        + (ROOT / "services" / "video_idea_prompt.py").read_text(encoding="utf-8")
    )
    for forbidden in (
        "frame_video_local",
        "video_edit",
        "provider.submit",
        "create_product_video_job",
        "wallet_debit",
        "charge_xu",
    ):
        assert forbidden not in changed_services
    assert set(PARENT_CONTRACTS) <= set(video_idea_prompt.SUPPORTED_PARENT_PRODUCTS)
    assert "frame_video_local" not in video_idea_prompt.SUPPORTED_PARENT_PRODUCTS
    assert "video_edit" not in video_idea_prompt.SUPPORTED_PARENT_PRODUCTS
    assert "video_idea" not in video_idea_prompt.SUPPORTED_PARENT_PRODUCTS
