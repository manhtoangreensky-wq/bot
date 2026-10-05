"""Test suite for S03: Snapshot and detail fidelity across idea lifecycle.

SPEC_ID: PRODUCT-VIDEO-S03-IDEA-SNAPSHOT-FIDELITY
Governed by: owner-governed-codex, locked-focus-engineering

Invariants:
1. Every accepted preset and customer field survives:
   prepare -> select/edit -> restore -> content lock
2. No silent loss or omission of safety notes, plans, seeds, hooks, objectives.
3. No shared mutable objects between state and return handoffs.
4. Deep equality and immutability of approved snapshot.
"""

from __future__ import annotations

from copy import deepcopy
import pytest

from services import video_idea_handoff, video_idea_prompt, video_idea_store


def _full_sentinel_preset() -> dict:
    return {
        "id": 501,
        "preset_key": "sentinel_commercial_launch_v1",
        "category_key": "sales",
        "title": "SENTINEL_TITLE_Ra mắt sản phẩm cao cấp",
        "description": "SENTINEL_DESC_Mô tả chi tiết giải quyết vấn đề khách hàng.",
        "hook": "SENTINEL_HOOK_Khoảnh khắc mở đầu gây chú ý mạnh.",
        "objective": "SENTINEL_OBJ_Thuyết phục người xem hành động ngay.",
        "scene_arc": "Mở đầu vấn đề -> Chứng minh giải pháp -> Kêu gọi hành động",
        "style": "SENTINEL_STYLE_Cinematic 4k realism",
        "system_guidance": "SENTINEL_GUIDANCE_Không thêm logo hoặc text giả mạo.",
        "user_prompt_template": "SENTINEL_TEMPLATE_Sản phẩm trong bối cảnh thực tế.",
        "image_prompt_seed": "SENTINEL_IMG_SEED_Ảnh tĩnh chuẩn mực.",
        "video_prompt_seed": "SENTINEL_VID_SEED_Chuyển động mượt mà và liền mạch.",
        "visual_plan": "SENTINEL_VISUAL_Bố cục 1/3 và ánh sáng tự nhiên.",
        "audio_plan": "SENTINEL_AUDIO_Âm thanh môi trường chân thực.",
        "voice_plan": "SENTINEL_VOICE_Giọng đọc truyền cảm và rõ ràng.",
        "music_plan": "SENTINEL_MUSIC_Nhạc nền hiện đại nâng dần cảm xúc.",
        "content_safety_note": "SENTINEL_SAFETY_Tuân thủ tiêu chuẩn an toàn nội dung.",
        "recommended_profile_id": "product_demo_realistic",
        "recommended_product_id": "video_ai_real",
        "recommended_aspect_ratio": "16:9",
        "recommended_scene_count": 3,
        "scene_duration_sec": 5,
        "platform_fit": ["tiktok", "facebook", "youtube_shorts"],
        "variation_axes": ["camera_angle", "lighting_mood", "pacing"],
    }


def _embedded_parent_context(product: str = "video_ai_real") -> dict:
    return {
        "flow_session_id": "session-sentinel-01",
        "flow_revision": 12,
        "flow_kind": f"flow-{product}",
        "scene_count": 3,
        "aspect_ratio": "16:9",
        "subject": "SENTINEL_SUBJECT",
        "idea_return_step": video_idea_handoff.NEXT_STEPS.get(product, "content_lock"),
        "trend_source": {"trend_id": "trend-sentinel-01", "title": "SENTINEL_TREND"},
        "reference_assets": {},
    }


def test_prepare_prompt_selection_preserves_all_sentinel_fields():
    preset = _full_sentinel_preset()
    parent = _embedded_parent_context("video_ai_real")
    handoff = video_idea_handoff.build_parent_handoff(
        parent,
        product_id="video_ai_real",
        return_callback="vproduct|idea_back|video_ai_real",
    )

    state = {
        "idea2": True,
        "idea_origin_product": "video_ai_real",
        "idea_preset_id": 501,
        "idea_preset_version": 3,
        "idea_preset": deepcopy(preset),
        "idea_preset_content": deepcopy(preset),
        "scene_count": 3,
        "ratio": "16:9",
        "idea_parent_handoff": handoff,
    }

    prepared = video_idea_prompt.prepare_prompt_selection(state, handoff)
    preset_content = prepared.get("idea_preset_content") or {}

    # Check every critical planning and safety field
    assert preset_content.get("preset_key") == preset["preset_key"]
    assert preset_content.get("title") == preset["title"]
    assert preset_content.get("description") == preset["description"]
    assert preset_content.get("hook") == preset["hook"]
    assert preset_content.get("objective") == preset["objective"]
    assert preset_content.get("system_guidance") == preset["system_guidance"]
    assert preset_content.get("user_prompt_template") == preset["user_prompt_template"]
    assert preset_content.get("image_prompt_seed") == preset["image_prompt_seed"]
    assert preset_content.get("video_prompt_seed") == preset["video_prompt_seed"]
    assert preset_content.get("visual_plan") == preset["visual_plan"]
    assert preset_content.get("audio_plan") == preset["audio_plan"]
    assert preset_content.get("voice_plan") == preset["voice_plan"]
    assert preset_content.get("music_plan") == preset["music_plan"]
    assert preset_content.get("content_safety_note") == preset["content_safety_note"], \
        "content_safety_note must not be dropped in prepare_prompt_selection"


def test_select_and_custom_edit_fidelity_and_immutability():
    preset = _full_sentinel_preset()
    parent = _embedded_parent_context("video_ai_real")
    handoff = video_idea_handoff.build_parent_handoff(
        parent,
        product_id="video_ai_real",
        return_callback="vproduct|idea_back|video_ai_real",
    )

    state = {
        "idea2": True,
        "idea_origin_product": "video_ai_real",
        "idea_preset_id": 501,
        "idea_preset_version": 3,
        "idea_preset": deepcopy(preset),
        "idea_preset_content": deepcopy(preset),
        "scene_count": 3,
        "ratio": "16:9",
        "idea_parent_handoff": handoff,
    }

    prepared = video_idea_prompt.prepare_prompt_selection(state, handoff)

    # 1. Test Option Selection
    selected = video_idea_prompt.select_prompt(prepared, 1)
    assert selected["selected_prompt_text"] == selected["idea_selected_prompt"]
    assert len(selected["selected_prompt_text"]) > 0

    # 2. Test Custom Customer Edit
    custom_text = "CUSTOM_CUSTOMER_EDIT: Khách hàng yêu cầu tập trung vào bao bì tái chế và màu xanh ngọc bích."
    edited = video_idea_prompt.set_custom_prompt(selected, custom_text)
    assert edited["idea_selected_prompt"] == custom_text
    assert edited["selected_prompt_text"] == custom_text
    assert edited["prompt_style"] == "Prompt đã sửa"

    # 3. Verify object independence (mutating edited does not corrupt prepared)
    assert prepared["idea_preset_content"]["title"] == preset["title"]
    assert edited["idea_preset_content"] is not prepared["idea_preset_content"]
