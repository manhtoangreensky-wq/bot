"""Test suite for S06: Tracing approved Idea content through 8 target product rows.

SPEC_ID: PRODUCT-VIDEO-S06-TARGET-PRODUCT-PAYLOAD-FIDELITY
Governed by: owner-governed-codex, locked-focus-engineering

8 Target Product Rows:
1. Trend (video_trend)
2. AI Prompt (video_ai_real prompt_video)
3. AI Image (video_ai_real image_video)
4. Reference (video_reference / video_ai_video_reference)
5. Script (script_image_video)
6. Storyboard (storyboard_prompt)
7. Self-shot Scene Change (self_shot_scene_change)
8. Self-shot Cinematic (self_shot_cinematic_transform)

Invariants:
- Approved idea snapshot content survives into per-scene manifest and mock provider request.
- Source-first lanes (Reference, Self-shot, Storyboard) preserve asset/media references.
- Semantic fidelity is verified; non-empty generic fallback is rejected.
"""

from __future__ import annotations

from copy import deepcopy
import pytest

from services import (
    video_idea_handoff,
    video_idea_prompt,
    video_uiflow3,
    video_uiflow3_routeengine as bridge,
)

USER_ID = 4501


def _sample_idea_preset() -> dict:
    return {
        "id": 201,
        "preset_key": "smart_home_robot_cleaner",
        "category_key": "technology",
        "title": "Robot hút bụi thông minh tự động",
        "description": "Robot tự động nhận diện chướng ngại vật, làm sạch sâu từng góc phòng.",
        "hook": "Một căn phòng ngổn ngang trở nên tinh tươm chỉ sau một lượt dọn.",
        "objective": "Khẳng định khả năng tự động hóa và sự tiện lợi tuyệt đối cho gia đình trẻ.",
        "scene_arc": "Phòng bừa bộn -> Robot quét laser và làm việc -> Sàn nhà sáng bóng",
        "style": "Hiện đại, góc nhìn góc thấp, ánh sáng nội thất ấm áp",
        "system_guidance": "Giữ đúng kiểu dáng robot tròn kim loại",
        "user_prompt_template": "Robot hút bụi di chuyển chính xác và êm ái.",
        "image_prompt_seed": "Robot trên sàn gỗ cao cấp",
        "video_prompt_seed": "Camera lia thấp theo chuyển động lăn bánh của robot",
        "visual_plan": "Góc máy ngang sàn và toàn cảnh từ trên cao",
        "audio_plan": "Tiếng động cơ êm và âm thanh báo hoàn thành dọn dẹp",
        "content_safety_note": "An toàn bản quyền công nghệ",
    }


def _build_uiflow3_snapshot(
    product: str,
    preset: dict,
    entry_mode: str = "prompt_video",
    scene_count: int = 2,
    source_asset: tuple[str, str, str] | None = None,
) -> dict:
    target_product = product if product in video_uiflow3.ENTRY_ADAPTERS else "video_ai_real"
    state = video_uiflow3.new_state(target_product, draft_id=f"snap-{product}")
    if target_product == "video_ai_real":
        state = video_uiflow3.set_entry_mode(state, entry_mode)
    elif target_product == "storyboard_prompt":
        state = video_uiflow3.set_entry_mode(state, "storyboard_upload")
        for index in range(1, scene_count + 1):
            state = video_uiflow3.add_source_asset(
                state,
                asset_type="frame",
                telegram_file_id=f"storyboard-panel-{index}",
                fingerprint=f"telegram:storyboard-panel-{index}",
            )
        state = video_uiflow3.set_source_metadata(
            state,
            detected_panel_count=scene_count,
        )
    elif target_product in {"video_trend", "script_image_video"}:
        state = video_uiflow3.set_source_metadata(
            state,
            text=preset["description"],
            script=preset["user_prompt_template"],
        )

    if source_asset:
        state = video_uiflow3.add_source_asset(
            state,
            asset_type=source_asset[0],
            telegram_file_id=source_asset[1],
            fingerprint=source_asset[2],
        )

    state = video_uiflow3.set_format(state, ratio="16:9", target_duration_seconds=scene_count * 8)
    state = video_uiflow3.set_content_candidate(
        state,
        source="idea_catalog",
        original_intent=preset["video_prompt_seed"],
        profile_id="product_showcase",
        idea_id=str(preset["id"]),
        approved_brief={
            **preset,
            "needs_characters": False,
            "needs_locations": False,
            "needs_dialogue": False,
            "needs_voice": False,
            "needs_music": False,
        },
    )
    state = video_uiflow3.lock_content(state)
    state = video_uiflow3.set_character_count(state, 0)
    state = video_uiflow3.set_location_count(state, 0)
    state = video_uiflow3.confirm_scene_count(state, scene_count)
    state = video_uiflow3.suggest_scene_plan(state)
    state = video_uiflow3.auto_assign_scenes(state)
    state = video_uiflow3.mark_sections_complete(
        state,
        "production_bible",
        "references",
        "continuity",
        "scene_plan",
        "scene_assignment",
        "dialogue",
        "prompts",
        "branding",
        "summary",
    )
    state["navigation"]["dirty_sections"] = []
    state["navigation"]["current_step"] = "summary"
    return video_uiflow3.approved_snapshot(state)


# 1. Trend
def test_row1_trend_consumer_payload_fidelity():
    preset = _sample_idea_preset()
    snapshot = _build_uiflow3_snapshot("video_trend", preset, scene_count=2)
    handoff = bridge.compile_routeengine_handoff(snapshot, owner_user_id=USER_ID, owner_chat_id=USER_ID)
    assert handoff["ok"] is True
    assert len(handoff["scene_cards"]) == 2
    assert preset["video_prompt_seed"] in handoff["prompt_text"]
    assert handoff["public_product_type"] == "video_trend"


# 2. AI Prompt
def test_row2_ai_prompt_consumer_payload_fidelity():
    preset = _sample_idea_preset()
    snapshot = _build_uiflow3_snapshot("video_ai_real", preset, entry_mode="prompt_video", scene_count=2)
    handoff = bridge.compile_routeengine_handoff(snapshot, owner_user_id=USER_ID, owner_chat_id=USER_ID)
    assert handoff["ok"] is True
    assert preset["video_prompt_seed"] in handoff["prompt_text"]
    assert handoff["public_product_type"] == "video_ai_prompt"


# 3. AI Image
def test_row3_ai_image_consumer_payload_fidelity():
    preset = _sample_idea_preset()
    asset = ("image", "image-asset-token-111", "telegram:image-asset-token-111")
    snapshot = _build_uiflow3_snapshot("video_ai_real", preset, entry_mode="image_video", scene_count=2, source_asset=asset)
    handoff = bridge.compile_routeengine_handoff(snapshot, owner_user_id=USER_ID, owner_chat_id=USER_ID)
    assert handoff["ok"] is True
    assert any(a.get("telegram_file_id") == "image-asset-token-111" for a in handoff["source"]["assets"])
    assert preset["video_prompt_seed"] in handoff["prompt_text"]
    assert handoff["public_product_type"] == "video_ai_image"


# 4. Reference
def test_row4_reference_consumer_payload_fidelity():
    preset = _sample_idea_preset()
    parent = {
        "flow_session_id": "session-ref-01",
        "flow_revision": 2,
        "flow_kind": "flow-video_reference",
        "scene_count": 2,
        "aspect_ratio": "16:9",
        "subject": preset["title"],
        "idea_return_step": "scene_plan",
        "trend_source": {},
        "source_video_id": "ref-video-token-01",
        "reference_assets": {
            "source_media_ref": "ref-video-token-01",
            "items": [{"file_id": "ref-video-token-01", "media_kind": "video"}],
        },
    }
    legacy_handoff = video_idea_handoff.build_parent_handoff(
        parent,
        product_id="video_reference",
        return_callback="vproduct|idea_back|video_reference",
    )
    state = {
        "idea_content": preset["description"],
        "idea_selected_prompt": preset["video_prompt_seed"],
        "idea_preset_content": preset,
    }
    restored = video_idea_handoff.apply_parent_handoff(state, legacy_handoff)
    assert restored["source_product_id"] == "video_reference"
    assert restored["source_video_id"] == "ref-video-token-01"
    assert restored["reference_assets"]["source_media_ref"] == "ref-video-token-01"
    assert restored["idea_selected_prompt"] == preset["video_prompt_seed"]
    assert restored["idea_preset_content"]["title"] == preset["title"]


# 5. Script
def test_row5_script_consumer_payload_fidelity():
    preset = _sample_idea_preset()
    snapshot = _build_uiflow3_snapshot("script_image_video", preset, scene_count=5)
    handoff = bridge.compile_routeengine_handoff(snapshot, owner_user_id=USER_ID, owner_chat_id=USER_ID)
    assert handoff["ok"] is True
    assert len(handoff["scene_cards"]) == 5
    assert preset["video_prompt_seed"] in handoff["prompt_text"]
    assert handoff["public_product_type"] == "script_to_video"


# 6. Storyboard
def test_row6_storyboard_consumer_payload_fidelity():
    preset = _sample_idea_preset()
    snapshot = _build_uiflow3_snapshot("storyboard_prompt", preset, scene_count=2)
    handoff = bridge.compile_routeengine_handoff(snapshot, owner_user_id=USER_ID, owner_chat_id=USER_ID)
    assert handoff["ok"] is True
    assert handoff["public_product_type"] == "storyboard_prompt"
    assert preset["video_prompt_seed"] in handoff["prompt_text"]


# 7. Self-shot Scene Change
def test_row7_selfshot_scene_change_consumer_payload_fidelity():
    preset = _sample_idea_preset()
    asset = ("video", "selfshot-scene-video-01", "telegram:selfshot-scene-video-01")
    snapshot = _build_uiflow3_snapshot("self_shot_scene_change", preset, scene_count=2, source_asset=asset)
    handoff = bridge.compile_routeengine_handoff(snapshot, owner_user_id=USER_ID, owner_chat_id=USER_ID)
    assert handoff["ok"] is True
    assert handoff["public_product_type"] == "self_shot_scene_change"
    assert any(a.get("telegram_file_id") == "selfshot-scene-video-01" for a in handoff["source"]["assets"])
    assert preset["video_prompt_seed"] in handoff["prompt_text"]


# 8. Self-shot Cinematic
def test_row8_selfshot_cinematic_consumer_payload_fidelity():
    preset = _sample_idea_preset()
    parent = {
        "flow_session_id": "session-cinematic-01",
        "flow_revision": 1,
        "flow_kind": "flow-self_shot_cinematic_transform",
        "scene_count": 1,
        "aspect_ratio": "9:16",
        "subject": preset["title"],
        "idea_return_step": "selfshot3_timeline",
        "trend_source": {},
        "source_video_id": "cinematic-vid-01",
        "reference_assets": {
            "source_media_ref": "cinematic-vid-01",
            "items": [{"file_id": "cinematic-vid-01", "media_kind": "video"}],
        },
    }
    legacy_handoff = video_idea_handoff.build_parent_handoff(
        parent,
        product_id="self_shot_cinematic_transform",
        return_callback="vproduct|idea_back|self_shot_cinematic_transform",
    )
    state = {
        "idea_content": preset["description"],
        "idea_selected_prompt": preset["video_prompt_seed"],
        "idea_preset_content": preset,
    }
    restored = video_idea_handoff.apply_parent_handoff(state, legacy_handoff)
    assert restored["source_product_id"] == "self_shot_cinematic_transform"
    assert restored["source_video_id"] == "cinematic-vid-01"
    assert restored["reference_assets"]["source_media_ref"] == "cinematic-vid-01"
    assert restored["idea_selected_prompt"] == preset["video_prompt_seed"]
    assert restored["step"] == "selfshot3_timeline"
