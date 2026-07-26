from __future__ import annotations

import re
from pathlib import Path

import pytest

from services import video_idea_handoff, video_idea_prompt


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")

PARENT_PRODUCTS = (
    "video_ai_real",
    "video_trend",
    "script_image_video",
    "storyboard_prompt",
    "self_shot_scene_change",
    "self_shot_cinematic_transform",
    "multi_scene_film",
)


def _function_source(name: str) -> str:
    pattern = re.compile(rf"^(?:async )?def {re.escape(name)}\(", re.MULTILINE)
    match = pattern.search(BOT_SOURCE)
    assert match, f"missing function: {name}"
    next_match = re.search(r"\n(?:async )?def [A-Za-z_]", BOT_SOURCE[match.end() :])
    end = match.end() + next_match.start() if next_match else len(BOT_SOURCE)
    return BOT_SOURCE[match.start() : end]


def _parent_state(product: str, *, session_id: str | None = None) -> dict:
    state = {
        "flow_session_id": session_id or f"session-{product}",
        "flow_revision": 3,
        "flow_kind": f"flow-{product}",
        "scene_count": 3,
        "aspect_ratio": "16:9",
        "subject": f"Chủ đề {product}",
        "idea_return_step": video_idea_handoff.NEXT_STEPS[product],
        "reference_assets": {},
    }
    if product == "video_trend":
        state["trend_source"] = {
            "trend_id": "trend-media-01",
            "title": "Nhịp reveal sản phẩm đang thịnh hành",
        }
    if product in {"self_shot_scene_change", "self_shot_cinematic_transform"}:
        state["reference_assets"] = {
            "source_media_ref": f"telegram-source-{product}",
            "source_media_refs": [f"telegram-source-{product}"],
            "items": [{"file_id": f"telegram-source-{product}", "media_kind": "video"}],
        }
    if product == "storyboard_prompt":
        state["storyboard_session_id"] = "storyboard-session-01"
    return state


def _idea_state(product: str) -> tuple[dict, dict]:
    parent = _parent_state(product)
    handoff = video_idea_handoff.build_parent_handoff(
        parent,
        product_id=product,
        return_callback=f"vproduct|idea_back|{product}",
    )
    state = {
        "idea2": True,
        "idea_origin_product": product,
        "idea_preset_id": 91,
        "idea_preset_version": 4,
        "idea_preset": {
            "id": 91,
            "title": "Mở vấn đề, giải pháp và kết quả",
            "description": "Ba cảnh cùng một mạch, không đổi chủ thể.",
            "recommended_profile_id": "cinematic_product",
            "visual_plan": "điện ảnh chân thật, ánh sáng sạch",
        },
        "subject": "Mở vấn đề, giải pháp và kết quả",
        "idea_content": "Ba cảnh cùng một mạch, không đổi chủ thể.",
        "scene_count": 3,
        "recommended_aspect_ratio": "16:9",
        "scene_drafts": [
            {"scene_index": 1, "content": "Mở vấn đề bằng tình huống thật."},
            {"scene_index": 2, "content": "Thể hiện giải pháp bằng một hành động hoàn chỉnh."},
            {"scene_index": 3, "content": "Khép bằng kết quả nhìn thấy được."},
        ],
        "trend_source": dict(parent.get("trend_source") or {}),
        "source_video_id": str(handoff.get("source_video_id") or ""),
        "storyboard_session_id": str(parent.get("storyboard_session_id") or ""),
        "idea_parent_handoff": handoff,
    }
    return state, handoff


@pytest.mark.parametrize("product", PARENT_PRODUCTS)
def test_all_seven_parent_products_get_isolated_complete_prompt_state(product: str) -> None:
    state, handoff = _idea_state(product)
    prepared = video_idea_prompt.prepare_prompt_selection(state, handoff)

    assert prepared["idea_parent_product"] == product
    assert prepared["idea_parent_flow"] == f"flow-{product}"
    assert prepared["idea_parent_session_id"] == f"session-{product}"
    assert prepared["idea_parent_revision"] == 3
    assert prepared["idea_return_step"] == video_idea_handoff.NEXT_STEPS[product]
    assert prepared["idea_preset_id"] == 91
    assert prepared["scene_count"] == 3
    assert prepared["ratio"] == "16:9"
    assert len(prepared["idea_scene_content"]) == 3
    assert len(prepared["idea_prompt_candidates"]) == 5
    assert prepared["idea_session_key"] == f"{product}:session-{product}:3"
    assert prepared["idea_selected_prompt"] == ""
    assert video_idea_prompt.safety_report(prepared) == {
        "job": 0,
        "outbox": 0,
        "provider_calls": 0,
        "image_provider_calls": 0,
        "generated_files": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }


def test_prompt_candidates_keep_scene_ratio_profile_continuity_trend_and_source_video() -> None:
    trend_state, trend_handoff = _idea_state("video_trend")
    trend = video_idea_prompt.prepare_prompt_selection(trend_state, trend_handoff)
    trend_prompt = trend["idea_prompt_candidates"][0]["prompt"]
    assert "Nhịp reveal sản phẩm đang thịnh hành" in trend_prompt
    assert "Tỉ lệ: 16:9" in trend_prompt
    assert "Profile/phong cách: cinematic_product" in trend_prompt
    for scene in trend_state["scene_drafts"]:
        assert scene["content"] in trend_prompt

    source_state, source_handoff = _idea_state("self_shot_scene_change")
    source = video_idea_prompt.prepare_prompt_selection(source_state, source_handoff)
    source_prompt = source["idea_prompt_candidates"][0]["prompt"]
    assert source["source_video_id"] == "telegram-source-self_shot_scene_change"
    assert "Dùng đúng video nguồn" in source_prompt
    assert "Giữ đúng người/vật và video nguồn" in source_prompt


def test_select_refresh_edit_and_skip_never_leave_an_empty_prompt() -> None:
    state, handoff = _idea_state("video_ai_real")
    prepared = video_idea_prompt.prepare_prompt_selection(state, handoff)

    selected = video_idea_prompt.select_prompt(prepared, 3)
    assert selected["idea_selected_prompt"]
    assert selected["idea_selected_prompt_record"]["button_index"] == 3
    assert video_idea_prompt.validate_return_state(selected)["ok"] is True

    refreshed = video_idea_prompt.refresh_prompt_candidates(prepared)
    assert refreshed["idea_prompt_offset"] == 5
    assert refreshed["idea_prompt_candidates"][0]["variant_index"] == 6

    edited = video_idea_prompt.set_custom_prompt(prepared, "Prompt riêng giữ ba cảnh nối tiếp tự nhiên.")
    assert edited["idea_selected_prompt"] == "Prompt riêng giữ ba cảnh nối tiếp tự nhiên."
    assert edited["idea_selected_prompt_record"]["title"] == "Prompt đã sửa"

    skipped = video_idea_prompt.skip_prompt(prepared)
    assert skipped["idea_prompt_skipped"] is True
    assert skipped["idea_selected_prompt"]
    assert video_idea_prompt.validate_return_state(skipped)["ok"] is True


def test_storyboard_requires_a_prompt_and_other_supported_parents_can_skip() -> None:
    storyboard_state, storyboard_handoff = _idea_state("storyboard_prompt")
    storyboard = video_idea_prompt.prepare_prompt_selection(storyboard_state, storyboard_handoff)
    with pytest.raises(ValueError, match="storyboard_prompt_required"):
        video_idea_prompt.skip_prompt(storyboard)

    for product in set(PARENT_PRODUCTS) - {"storyboard_prompt"}:
        state, handoff = _idea_state(product)
        skipped = video_idea_prompt.skip_prompt(
            video_idea_prompt.prepare_prompt_selection(state, handoff)
        )
        assert skipped["idea_selected_prompt"]


def test_parent_handoff_round_trip_preserves_prompt_context_without_cross_product_reuse() -> None:
    keys = set()
    for product in PARENT_PRODUCTS:
        state, handoff = _idea_state(product)
        prepared = video_idea_prompt.select_prompt(
            video_idea_prompt.prepare_prompt_selection(state, handoff),
            1,
        )
        restored = video_idea_handoff.apply_parent_handoff(
            {
                "idea_scene_content": prepared["idea_scene_content"],
                "idea_prompt_candidates": prepared["idea_prompt_candidates"],
                "idea_selected_prompt": prepared["idea_selected_prompt"],
            },
            handoff,
        )
        assert restored["source_product_id"] == product
        assert restored["idea_parent_session_id"] == f"session-{product}"
        assert restored["aspect_ratio"] == "16:9"
        assert restored["idea_selected_prompt"]
        keys.add(prepared["idea_session_key"])
    assert len(keys) == len(PARENT_PRODUCTS)


def test_prompt_screen_and_callbacks_match_the_public_contract() -> None:
    keyboard = _function_source("video_idea_prompt_selection_keyboard")
    handler = _function_source("handle_video_idea_prompt_callback")
    pending = _function_source("handle_video_idea_dynamic_pending_text")
    approve = _function_source("handle_video_idea_dynamic_callback")

    assert "for index in range(1, 6)" in keyboard
    assert "1–5" not in keyboard  # buttons are real callbacks, not a text placeholder
    assert keyboard.count('InlineKeyboardButton("⏭️ Bỏ qua"') == 1
    assert '== "storyboard_prompt"' in keyboard
    assert 'callback_data="idea_video|prompt|back"' in keyboard
    assert 'callback_data="menu|main"' in keyboard

    for action in ("select", "refresh", "edit", "skip", "view", "continue", "back"):
        assert handler.count(f'if action == "{action}":') == 1
    assert "video_idea_processed_callback_ids" in handler
    assert "generic X" not in handler
    assert "create_product_video_job" not in handler
    assert "provider.submit" not in handler
    assert 'step == "idea2_prompt_edit"' in pending
    assert "video_idea_prompt.set_custom_prompt" in pending
    assert "video_idea_prompt.prepare_prompt_selection" in approve
    assert 'restore_developing_video_pending(uid, "videoidea", state, "idea2_prompt")' in approve


def test_prompt_namespace_has_one_owner_and_is_registered_before_dynamic_catalog() -> None:
    owner = '("idea_video|", "handle_video_idea_prompt_callback")'
    registration = (
        'CallbackQueryHandler(handle_video_idea_prompt_callback, '
        'pattern=r"^idea_video\\|")'
    )
    assert BOT_SOURCE.count(owner) == 1
    assert BOT_SOURCE.count(registration) == 1
    prompt_position = BOT_SOURCE.index(registration)
    dynamic_position = BOT_SOURCE.index(
        'CallbackQueryHandler(handle_video_idea_dynamic_callback, pattern=r"^videa\\|")'
    )
    assert prompt_position < dynamic_position


def test_exact_parent_render_map_uses_existing_product_owners_and_long_prompt_shell() -> None:
    renderer = _function_source("video_idea_render_exact_parent")
    continuation = _function_source("video_idea_continue_to_exact_parent")

    assert 'product_id == "storyboard_prompt"' in renderer
    assert "save_storyboard2_state" in renderer
    assert "video_selfshot2_render" in renderer
    assert "video_selfshot3_render" in renderer
    assert 'product_id == "multi_scene_film"' in renderer
    assert 'handoff["step"] = "full_review"' in renderer
    assert "save_video_profile_studio_state" in renderer
    assert 'video_tail9_render(query, user_id, context, "logo")' in renderer

    assert "video_idea_prompt.validate_return_state" in continuation
    assert "video_idea_render_exact_parent" in continuation
    assert "video_idea_parent_handoff" in continuation
    assert "clear_developing_video_pending" in continuation
    assert "frame_video_local" not in continuation


def test_scope_excludes_framevideo_and_keeps_standalone_idea_hub_outside_prompt_service() -> None:
    assert "frame_video_local" not in video_idea_prompt.SUPPORTED_PARENT_PRODUCTS
    assert "video_idea" not in video_idea_prompt.SUPPORTED_PARENT_PRODUCTS
    assert "frame_video_local" not in video_idea_handoff.NEXT_STEPS
    assert "video_idea" in video_idea_handoff.NEXT_STEPS
