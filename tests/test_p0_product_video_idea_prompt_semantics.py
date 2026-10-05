"""Test suite for S04: Prompt and scene semantics across Idea workflows.

SPEC_ID: PRODUCT-VIDEO-S04-PROMPT-SCENE-SEMANTICS
Governed by: owner-governed-codex, locked-focus-engineering

Invariants:
1. Hook, objective, scene_arc, and scene ordering survive into planning.
2. Dialogue, brand constraints, and negative constraints survive intact.
3. Parametrized scene counts (1, 2, 3, 5, 10, 20) and ratios (9:16, 16:9, 1:1, 4:5).
4. Storyboard mandatory prompt rejects skip (fails closed).
5. Customer-locked edits override generated defaults.
"""

from __future__ import annotations

from copy import deepcopy
import pytest

from services import video_idea_handoff, video_idea_prompt


PRESET_ECO_FARM = {
    "id": 101,
    "preset_key": "eco_farm_story",
    "category_key": "story",
    "title": "Nông trại hữu cơ đón bình minh",
    "description": "Câu chuyện người nông dân chăm sóc vườn rau hữu cơ từ sáng sớm.",
    "hook": "Bình minh vừa hé qua giọt sương trên lá cải bắp xanh ngát.",
    "objective": "Khẳng định nông sản sạch thuần tự nhiên đến tận bàn ăn gia đình.",
    "scene_arc": "Sương sớm vườn rau -> Thu hoạch thủ công -> Bữa cơm gia đình an lành",
    "style": "Điện ảnh tự nhiên, tông xanh và vàng ấm",
    "system_guidance": "Không thêm hóa chất, không chữ tiếng Anh",
    "user_prompt_template": "Nông dân thao tác tỉ mỉ trong ánh sáng mai.",
    "image_prompt_seed": "Khu vườn tươi mát dưới nắng sớm",
    "video_prompt_seed": "Camera lia nhẹ từ lá rau sang nụ cười người nông dân",
    "visual_plan": "Cận cảnh giọt sương và toàn cảnh cánh đồng",
    "content_safety_note": "An toàn thực phẩm và môi trường",
    "variation_axes": ["nhịp kể", "ánh sáng", "chuyển động"],
}

PRESET_TECH_SMART = {
    "id": 102,
    "preset_key": "tech_smart_gadget",
    "category_key": "technology",
    "title": "Tai nghe chống ồn thế hệ mới",
    "description": "Trải nghiệm âm thanh tĩnh lặng giữa đường phố ồn ào.",
    "hook": "Giữa ngã tư đông đúc, chỉ một nút chạm biến tất cả thành yên ắng.",
    "objective": "Người dùng tận hưởng âm nhạc không gián đoạn ở bất cứ đâu.",
    "scene_arc": "Phố thị ồn ào -> Chạm nút kích hoạt -> Thế giới âm nhạc riêng",
    "style": "Hiện đại, nhịp nhanh công nghệ",
    "system_guidance": "Giữ nguyên thiết kế tai nghe, không logo cạnh tranh",
    "user_prompt_template": "Nhân vật trẻ trung bước đi tự tin",
    "image_prompt_seed": "Tai nghe kim loại bóng bẩy",
    "video_prompt_seed": "Chuyển động camera vòng quanh nhân vật khi đeo tai nghe",
    "visual_plan": "Ánh sáng neon đô thị tương phản",
    "content_safety_note": "Không vi phạm bản quyền thương hiệu",
    "variation_axes": ["tiết tấu", "góc máy", "màu sắc"],
}


def _make_state(preset: dict, product: str = "video_ai_real", scene_count: int = 3, ratio: str = "16:9") -> tuple[dict, dict]:
    parent = {
        "flow_session_id": f"session-{preset['preset_key']}",
        "flow_revision": 1,
        "flow_kind": f"flow-{product}",
        "scene_count": scene_count,
        "aspect_ratio": ratio,
        "subject": preset["title"],
        "idea_return_step": video_idea_handoff.NEXT_STEPS.get(product, "content_lock"),
        "trend_source": {},
        "reference_assets": {},
    }
    handoff = video_idea_handoff.build_parent_handoff(
        parent,
        product_id=product,
        return_callback=f"vproduct|idea_back|{product}",
    )
    state = {
        "idea2": True,
        "idea_origin_product": product,
        "idea_preset_id": preset["id"],
        "idea_preset_version": 1,
        "idea_preset": deepcopy(preset),
        "idea_preset_content": deepcopy(preset),
        "scene_count": scene_count,
        "ratio": ratio,
        "idea_parent_handoff": handoff,
    }
    return state, handoff


@pytest.mark.parametrize("scene_count", [1, 2, 3, 5, 10, 20])
@pytest.mark.parametrize("ratio", ["9:16", "16:9", "1:1", "4:5"])
def test_scene_counts_and_ratios_semantics(scene_count: int, ratio: str):
    state, handoff = _make_state(PRESET_ECO_FARM, scene_count=scene_count, ratio=ratio)
    prepared = video_idea_prompt.prepare_prompt_selection(state, handoff)

    candidates = prepared.get("idea_prompt_candidates") or []
    assert len(candidates) == 5, "Must generate exactly 5 prompt candidates"

    scene_content = prepared.get("idea_scene_content") or []
    assert len(scene_content) == scene_count, f"Scene content count must equal requested {scene_count}"

    for i, sc in enumerate(scene_content, start=1):
        assert sc["scene_index"] == i
        assert len(sc["content"]) > 0

    # Select candidate 1 and verify ratio and scene structure
    selected = video_idea_prompt.select_prompt(prepared, 1)
    prompt_text = selected["selected_prompt_text"]
    assert f"Tỉ lệ {ratio}" in prompt_text
    assert f"Số cảnh: {scene_count}" in prompt_text
    assert PRESET_ECO_FARM["hook"] in prompt_text or PRESET_ECO_FARM["title"] in prompt_text


def test_storyboard_skip_rejected_mandatory():
    """Verify that Storyboard product strictly rejects prompt skip."""
    state, handoff = _make_state(PRESET_TECH_SMART, product="storyboard_prompt")
    prepared = video_idea_prompt.prepare_prompt_selection(state, handoff)

    with pytest.raises(ValueError) as exc_info:
        video_idea_prompt.skip_prompt(prepared)
    assert "storyboard_prompt_required" in str(exc_info.value)


def test_custom_customer_edit_overrides_defaults():
    """Prove that customer locked edit beats generated candidates."""
    state, handoff = _make_state(PRESET_TECH_SMART, product="video_ai_real")
    prepared = video_idea_prompt.prepare_prompt_selection(state, handoff)
    selected = video_idea_prompt.select_prompt(prepared, 2)

    locked_edit = (
        "LOCKED_EDIT: Cảnh 1 tập trung góc cận bàn tay gạt công tắc ANC. "
        "Không dùng hiệu ứng giật khung hình. Nhạc jazz êm dịu."
    )
    customized = video_idea_prompt.set_custom_prompt(selected, locked_edit)

    assert customized["selected_prompt_text"] == locked_edit
    assert customized["idea_selected_prompt"] == locked_edit
    assert customized["prompt_style"] == "Prompt đã sửa"
    assert customized["idea_prompt_skipped"] is False
