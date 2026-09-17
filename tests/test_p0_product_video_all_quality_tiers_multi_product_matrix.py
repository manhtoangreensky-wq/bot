from __future__ import annotations

import hashlib
import re
from pathlib import Path
import pytest

from services import video_ai_real_pricing, video_tail9, video_uifreeze1


ALL_CANONICAL_TIERS = (400, 500, 600, 200, 300, 700, 800, 1000, 1200, 1500)
TREND_SUPPORTED_TIERS = ALL_CANONICAL_TIERS

LOCKED_UI_FUNCTION_HASHES = {
    "main_video_keyboard": "54d1b1cc1ea8d5a60b45005cc3ce13703f9a3da9f4c4d207cf31f5094f452ffa",
    "menu_text_main_video_i18n": "43945a07f7680b612def8a7b5f9b38f8412cf048775f775847ea10ae07f02931",
    "video_tail9_addon_text": "6b406611841bc16e30fc6a497f625034b9b2d1281437b9bee6a6c272135165e5",
    "video_tail9_addon_keyboard": "d7bc422fec98528121ec77406ab99027fd45663429e2dd6e7aa4c85fa6439ee7",
    "video_tail9_review_text": "27ec69d92c8c044422199c9107f8ab575a2ad23b3ec5bfcfd96334015de30127",
    "video_tail9_review_keyboard": "b47e3173a3d3c177eb22d205bbaa45dd561196c38806ce2a1f1db24e8037623a",
    "video_tail9_quality_text": "163bdaa0efd2c81ddcd03643ddb909c9007e52fd467960a4050cf651d1a6b676",
    "video_tail9_quality_keyboard": "a0bc0dba9e4419992a6f7fa0298fea935508891196fd9ecd28f4a1c5901bdc3e",
    "video_tail9_invoice_text": "975d244430c7f4e7ef6897d70a9cc53c001a5d5ae87e390fc40d157c87213bde",
    "video_tail9_invoice_keyboard": "fc65e49bca1942bfe5487f8e1ec1775db95fa4e09fa3df7b377c42a103fefedb",
    "video_tail9_confirm_text": "c68ffa14a128510d1c4900fcb5766af4de542c7d2298bb304f14e71fa9c27466",
    "video_tail9_confirm_keyboard": "d5739136ec3bfb266710de01c4479b3082e162bdb68a07583e8ad2312ef00252",
    "video_tail9_status_recovery_text": "21ebd133e413234485c64953ee433618dfcbe4c6d6262b599da7c0a84322928d",
    "video_tail9_status_recovery_keyboard": "59911e71764d07aaf1ce77bd7251237c385cb83a32fb7e08738c9184347b577f",
}


def _pricing_snapshot(tier_id: int, scene_count: int = 2) -> dict[str, int]:
    tier_spec = video_uifreeze1.tier_spec(tier_id)
    unit_xu = int(tier_spec["unit_xu"])
    quote = video_ai_real_pricing.video_multiscene_price(unit_xu, scene_count)
    return {
        "routing_quality_tier": tier_id,
        "quality_xu": unit_xu,
        "subtotal_xu": quote["subtotal_xu"],
        "discount_percent": quote["discount_percent"],
        "discount_xu": quote["discount_xu"],
        "total_xu": quote["total_xu"],
    }


# ==============================================================================
# LANE 1: video_trend - Complete Support of All 10 Tiers (Including 80 Xu Tier 400)
# ==============================================================================


@pytest.mark.parametrize("tier_id", TREND_SUPPORTED_TIERS)
def test_video_trend_supports_all_ten_quality_tiers(tier_id: int) -> None:
    """video_trend handles all 10 quality tiers including 80 Xu (Tier 400)."""
    contract = video_tail9.commercial_contract("video_trend")
    assert tier_id in contract["supported_quality_tiers"]

    # UI Catalog check
    catalog = video_uifreeze1.catalog_report("video_trend", scene_count=2, ratio="9:16")
    assert catalog["ok"] is True
    assert tier_id in catalog["tier_ids"]

    # Tail state lifecycle through invoice & confirmation
    state = video_tail9.new_state(
        product_type="video_trend",
        execution_product_type="video_trend",
        session_id=f"trend-tier-{tier_id}",
        scene_count=2,
        ratio="9:16",
    )
    # Content must reflect trend search & hook synthesis
    state = video_tail9.apply_content_contract(
        state,
        {
            "content_source": "trend",
            "selected_prompt_text": "Viral TikTok Trend: AI Video Editing Hack",
            "per_scene_content": [
                {"scene_index": 1, "provider_prompt": "Trend scene 1 hook"},
                {"scene_index": 2, "provider_prompt": "Trend scene 2 climax"},
            ],
            "plan_status": "ready",
        },
    )
    pricing = _pricing_snapshot(tier_id, scene_count=2)
    invoiced = video_tail9.select_package(
        state,
        quality_tier_id=str(tier_id),
        package_id=f"product_video_{tier_id}",
        pricing_snapshot=pricing,
        capability_snapshot={"ok": True, "required_capability": "text_to_video"},
    )
    assert invoiced["status_stage"] == "invoice"
    assert invoiced["quality_tier_id"] == str(tier_id)
    assert invoiced["pricing_snapshot"]["total_xu"] == pricing["total_xu"]

    allowed, reason = video_tail9.invoice_allowed(invoiced)
    assert allowed is True
    assert reason == "ok"

    confirmed, created = video_tail9.confirm_once(invoiced, f"confirm-trend-{tier_id}")
    replayed, created_again = video_tail9.confirm_once(confirmed, f"confirm-trend-{tier_id}")
    assert created is True
    assert created_again is False
    assert confirmed["final_confirmed"] is True


def test_video_trend_supports_tier_400_80xu() -> None:
    """video_trend supports Tier 400 (80 Xu) canonically."""
    contract = video_tail9.commercial_contract("video_trend")
    assert 400 in contract["supported_quality_tiers"]

    # Catalog offers Tier 400
    catalog = video_uifreeze1.catalog_report("video_trend", scene_count=2, ratio="9:16")
    assert 400 in catalog["tier_ids"]

    # package_compatibility returns ok
    compat = video_tail9.package_compatibility("video_trend", scene_count=2, ratio="9:16", quality_tier_id=400)
    assert compat["ok"] is True
    assert not compat["blockers"]

    # select_package succeeds
    state = video_tail9.new_state(
        product_type="video_trend",
        execution_product_type="video_trend",
        session_id="trend-tier-400-supported",
        scene_count=2,
        ratio="9:16",
    )
    state = video_tail9.apply_content_contract(
        state,
        {
            "content_source": "trend",
            "selected_prompt_text": "Viral trend prompt",
            "per_scene_content": [{"scene_index": 1, "provider_prompt": "Scene 1"}],
            "plan_status": "ready",
        },
    )
    invoiced = video_tail9.select_package(
        state,
        quality_tier_id="400",
        package_id="product_video_400",
        pricing_snapshot=_pricing_snapshot(400, scene_count=2),
        capability_snapshot={"ok": True, "required_capability": "text_to_video"},
    )
    assert invoiced["status_stage"] == "invoice"
    assert invoiced["quality_tier_id"] == "400"


# ==============================================================================
# LANE 2A: video_ai_real -> video_ai_prompt (Text Prompt -> Video AI) All 10 Tiers
# ==============================================================================


@pytest.mark.parametrize("tier_id", ALL_CANONICAL_TIERS)
def test_video_ai_prompt_lane_supports_all_ten_tiers(tier_id: int) -> None:
    contract = video_tail9.commercial_contract("video_ai_prompt")
    assert tier_id in contract["supported_quality_tiers"]

    catalog = video_uifreeze1.catalog_report("video_ai_prompt", scene_count=2, ratio="9:16")
    assert catalog["ok"] is True
    assert tier_id in catalog["tier_ids"]

    state = video_tail9.new_state(
        product_type="video_ai_real",
        execution_product_type="video_ai_prompt",
        session_id=f"ai-prompt-tier-{tier_id}",
        scene_count=2,
        ratio="9:16",
    )
    state = video_tail9.apply_content_contract(
        state,
        {
            "content_source": "manual",
            "selected_prompt_text": "Cinematic 8k realistic documentary scene, golden hour lighting",
            "per_scene_content": [
                {"scene_index": 1, "provider_prompt": "Prompt scene 1 wide shot"},
                {"scene_index": 2, "provider_prompt": "Prompt scene 2 close up"},
            ],
            "plan_status": "ready",
        },
    )
    pricing = _pricing_snapshot(tier_id, scene_count=2)
    invoiced = video_tail9.select_package(
        state,
        quality_tier_id=str(tier_id),
        package_id=f"product_video_{tier_id}",
        pricing_snapshot=pricing,
        capability_snapshot={"ok": True, "required_capability": "text_to_video"},
    )
    assert invoiced["status_stage"] == "invoice"
    assert video_tail9.invoice_allowed(invoiced) == (True, "ok")
    confirmed, created = video_tail9.confirm_once(invoiced, f"confirm-prompt-{tier_id}")
    assert created is True
    assert confirmed["final_confirmed"] is True


# ==============================================================================
# LANE 2B: video_ai_real -> video_ai_image (Keyframe Image -> Video AI) All 10 Tiers
# ==============================================================================


@pytest.mark.parametrize("tier_id", ALL_CANONICAL_TIERS)
def test_video_ai_image_lane_supports_all_ten_tiers(tier_id: int) -> None:
    contract = video_tail9.commercial_contract("video_ai_image")
    assert tier_id in contract["supported_quality_tiers"]

    catalog = video_uifreeze1.catalog_report("video_ai_image", scene_count=2, ratio="9:16")
    assert catalog["ok"] is True
    assert tier_id in catalog["tier_ids"]

    state = video_tail9.new_state(
        product_type="video_ai_real",
        execution_product_type="video_ai_image",
        session_id=f"ai-image-tier-{tier_id}",
        scene_count=2,
        ratio="9:16",
    )
    state = video_tail9.apply_content_contract(
        state,
        {
            "content_source": "scene_images",
            "selected_prompt_text": "Keyframe reference image with fluid dynamic motion",
            "per_scene_content": [
                {"scene_index": 1, "provider_prompt": "Motion from keyframe 1", "image_url": "img1.png"},
                {"scene_index": 2, "provider_prompt": "Motion from keyframe 2", "image_url": "img2.png"},
            ],
            "plan_status": "ready",
        },
    )
    pricing = _pricing_snapshot(tier_id, scene_count=2)
    invoiced = video_tail9.select_package(
        state,
        quality_tier_id=str(tier_id),
        package_id=f"product_video_{tier_id}",
        pricing_snapshot=pricing,
        capability_snapshot={"ok": True, "required_capability": "image_to_video"},
    )
    assert invoiced["status_stage"] == "invoice"
    assert video_tail9.invoice_allowed(invoiced) == (True, "ok")
    confirmed, created = video_tail9.confirm_once(invoiced, f"confirm-image-{tier_id}")
    assert created is True
    assert confirmed["final_confirmed"] is True


# ==============================================================================
# LANE 2C: video_ai_real -> video_ai_video_reference (Video-to-Video) All 10 Tiers
# ==============================================================================


@pytest.mark.parametrize("tier_id", ALL_CANONICAL_TIERS)
def test_video_ai_video_reference_lane_supports_all_ten_tiers(tier_id: int) -> None:
    contract = video_tail9.commercial_contract("video_ai_video_reference")
    assert tier_id in contract["supported_quality_tiers"]

    catalog = video_uifreeze1.catalog_report("video_ai_video_reference", scene_count=2, ratio="9:16")
    assert catalog["ok"] is True
    assert tier_id in catalog["tier_ids"]

    state = video_tail9.new_state(
        product_type="video_ai_real",
        execution_product_type="video_ai_video_reference",
        session_id=f"ai-ref-tier-{tier_id}",
        scene_count=2,
        ratio="9:16",
    )
    state = video_tail9.apply_content_contract(
        state,
        {
            "content_source": "source_video",
            "selected_prompt_text": "Reference video style transfer and motion replication",
            "per_scene_content": [
                {"scene_index": 1, "provider_prompt": "Reference motion transfer 1"},
                {"scene_index": 2, "provider_prompt": "Reference motion transfer 2"},
            ],
            "plan_status": "ready",
        },
    )
    pricing = _pricing_snapshot(tier_id, scene_count=2)
    invoiced = video_tail9.select_package(
        state,
        quality_tier_id=str(tier_id),
        package_id=f"product_video_{tier_id}",
        pricing_snapshot=pricing,
        capability_snapshot={"ok": True, "required_capability": "video_to_video"},
    )
    assert invoiced["status_stage"] == "invoice"
    assert video_tail9.invoice_allowed(invoiced) == (True, "ok")
    confirmed, created = video_tail9.confirm_once(invoiced, f"confirm-ref-{tier_id}")
    assert created is True
    assert confirmed["final_confirmed"] is True


# ==============================================================================
# LANE 3: script_image_video (Kịch bản -> Ảnh -> Video) All 10 Tiers
# ==============================================================================


@pytest.mark.parametrize("tier_id", ALL_CANONICAL_TIERS)
def test_script_image_video_supports_all_ten_tiers(tier_id: int) -> None:
    contract = video_tail9.commercial_contract("script_image_video")
    assert tier_id in contract["supported_quality_tiers"]

    catalog = video_uifreeze1.catalog_report("script_image_video", scene_count=5, ratio="9:16")
    assert catalog["ok"] is True
    assert tier_id in catalog["tier_ids"]

    state = video_tail9.new_state(
        product_type="script_image_video",
        execution_product_type="script_to_video",
        session_id=f"script-tier-{tier_id}",
        scene_count=5,
        ratio="9:16",
    )
    state = video_tail9.apply_content_contract(
        state,
        {
            "content_source": "script",
            "selected_prompt_text": "5-scene master commercial script",
            "per_scene_content": [
                {"scene_index": i, "provider_prompt": f"Script scene {i} production shot"}
                for i in range(1, 6)
            ],
            "plan_status": "ready",
        },
    )
    pricing = _pricing_snapshot(tier_id, scene_count=5)
    invoiced = video_tail9.select_package(
        state,
        quality_tier_id=str(tier_id),
        package_id=f"product_video_{tier_id}",
        pricing_snapshot=pricing,
        capability_snapshot={"ok": True, "required_capability": "text_to_video"},
    )
    assert invoiced["status_stage"] == "invoice"
    assert video_tail9.invoice_allowed(invoiced) == (True, "ok")
    confirmed, created = video_tail9.confirm_once(invoiced, f"confirm-script-{tier_id}")
    assert created is True
    assert confirmed["final_confirmed"] is True


# ==============================================================================
# LANE 4: storyboard_prompt (Storyboard + Prompt điện ảnh) All 10 Tiers
# ==============================================================================


@pytest.mark.parametrize("tier_id", ALL_CANONICAL_TIERS)
def test_storyboard_prompt_supports_all_ten_tiers(tier_id: int) -> None:
    contract = video_tail9.commercial_contract("storyboard_prompt")
    assert tier_id in contract["supported_quality_tiers"]

    catalog = video_uifreeze1.catalog_report(
        "storyboard_prompt",
        scene_count=2,
        ratio="9:16",
        required_capability="image_to_video",
    )
    assert catalog["ok"] is True
    assert tier_id in catalog["tier_ids"]

    state = video_tail9.new_state(
        product_type="storyboard_prompt",
        execution_product_type="storyboard_prompt",
        session_id=f"storyboard-tier-{tier_id}",
        scene_count=2,
        ratio="9:16",
    )
    state = video_tail9.apply_content_contract(
        state,
        {
            "content_source": "storyboard",
            "selected_prompt_text": "Cinematic storyboard with panel breakdown",
            "per_scene_content": [
                {"scene_index": 1, "provider_prompt": "Frame 1 panel prompt", "asset_id": "img1"},
                {"scene_index": 2, "provider_prompt": "Frame 2 panel prompt", "asset_id": "img2"},
            ],
            "plan_status": "ready",
        },
    )
    pricing = _pricing_snapshot(tier_id, scene_count=2)
    invoiced = video_tail9.select_package(
        state,
        quality_tier_id=str(tier_id),
        package_id=f"product_video_{tier_id}",
        pricing_snapshot=pricing,
        capability_snapshot={"ok": True, "required_capability": "image_to_video"},
    )
    assert invoiced["status_stage"] == "invoice"
    assert video_tail9.invoice_allowed(invoiced) == (True, "ok")
    confirmed, created = video_tail9.confirm_once(invoiced, f"confirm-sb-{tier_id}")
    assert created is True
    assert confirmed["final_confirmed"] is True


# ==============================================================================
# LANE 5A: self_shot_scene_change (Tự quay & đổi cảnh AI - ss2) All 10 Tiers
# ==============================================================================


@pytest.mark.parametrize("tier_id", ALL_CANONICAL_TIERS)
def test_self_shot_scene_change_supports_all_ten_tiers(tier_id: int) -> None:
    contract = video_tail9.commercial_contract("self_shot_scene_change")
    assert tier_id in contract["supported_quality_tiers"]

    catalog = video_uifreeze1.catalog_report(
        "self_shot_scene_change",
        scene_count=2,
        ratio="keep",
        required_capability="video_to_video",
    )
    assert catalog["ok"] is True
    assert tier_id in catalog["tier_ids"]

    state = video_tail9.new_state(
        product_type="self_shot_scene_change",
        execution_product_type="self_shot_scene_change",
        session_id=f"selfshot2-tier-{tier_id}",
        scene_count=2,
        ratio="keep",
    )
    state = video_tail9.apply_content_contract(
        state,
        {
            "content_source": "source_video",
            "selected_prompt_text": "Preserve speaker, change background to cyberpunk street",
            "per_scene_content": [
                {"scene_index": 1, "provider_prompt": "Scene 1 cyberpunk change"},
                {"scene_index": 2, "provider_prompt": "Scene 2 neon cafe change"},
            ],
            "plan_status": "ready",
        },
    )
    pricing = _pricing_snapshot(tier_id, scene_count=2)
    invoiced = video_tail9.select_package(
        state,
        quality_tier_id=str(tier_id),
        package_id=f"product_video_{tier_id}",
        pricing_snapshot=pricing,
        capability_snapshot={"ok": True, "required_capability": "video_to_video"},
    )
    assert invoiced["status_stage"] == "invoice"
    assert video_tail9.invoice_allowed(invoiced) == (True, "ok")
    confirmed, created = video_tail9.confirm_once(invoiced, f"confirm-ss2-{tier_id}")
    assert created is True
    assert confirmed["final_confirmed"] is True


# ==============================================================================
# LANE 5B: self_shot_cinematic_transform (Tự quay & biến đổi điện ảnh - ss3) All 10 Tiers
# ==============================================================================


@pytest.mark.parametrize("tier_id", ALL_CANONICAL_TIERS)
def test_self_shot_cinematic_transform_supports_all_ten_tiers(tier_id: int) -> None:
    contract = video_tail9.commercial_contract("self_shot_cinematic_transform")
    assert tier_id in contract["supported_quality_tiers"]

    catalog = video_uifreeze1.catalog_report(
        "self_shot_cinematic_transform",
        scene_count=2,
        ratio="keep",
        required_capability="video_to_video",
    )
    assert catalog["ok"] is True
    assert tier_id in catalog["tier_ids"]

    state = video_tail9.new_state(
        product_type="self_shot_cinematic_transform",
        execution_product_type="self_shot_cinematic_transform",
        session_id=f"selfshot3-tier-{tier_id}",
        scene_count=2,
        ratio="keep",
    )
    state = video_tail9.apply_content_contract(
        state,
        {
            "content_source": "source_video",
            "selected_prompt_text": "One-take cinematic transformation with evolving wardrobe and scene",
            "per_scene_content": [
                {"scene_index": 1, "provider_prompt": "Stage 1 medieval armor transform"},
                {"scene_index": 2, "provider_prompt": "Stage 2 sci-fi exosuit transform"},
            ],
            "plan_status": "ready",
        },
    )
    pricing = _pricing_snapshot(tier_id, scene_count=2)
    invoiced = video_tail9.select_package(
        state,
        quality_tier_id=str(tier_id),
        package_id=f"product_video_{tier_id}",
        pricing_snapshot=pricing,
        capability_snapshot={"ok": True, "required_capability": "video_to_video"},
    )
    assert invoiced["status_stage"] == "invoice"
    assert video_tail9.invoice_allowed(invoiced) == (True, "ok")
    confirmed, created = video_tail9.confirm_once(invoiced, f"confirm-ss3-{tier_id}")
    assert created is True
    assert confirmed["final_confirmed"] is True


# ==============================================================================
# LANE 6: multi_scene_film (Video dài tập) All 10 Tiers
# ==============================================================================


@pytest.mark.parametrize("tier_id", ALL_CANONICAL_TIERS)
def test_multi_scene_film_supports_all_ten_tiers(tier_id: int) -> None:
    contract = video_tail9.commercial_contract("multi_scene_film")
    assert tier_id in contract["supported_quality_tiers"]

    catalog = video_uifreeze1.catalog_report("multi_scene_film", scene_count=2, ratio="9:16")
    assert catalog["ok"] is True
    assert tier_id in catalog["tier_ids"]

    state = video_tail9.new_state(
        product_type="multi_scene_film",
        execution_product_type="multi_scene_film",
        session_id=f"film-tier-{tier_id}",
        scene_count=2,
        ratio="9:16",
    )
    state = video_tail9.apply_content_contract(
        state,
        {
            "content_source": "manual",
            "selected_prompt_text": "Multi-scene dramatic film script",
            "per_scene_content": [
                {"scene_index": 1, "provider_prompt": "Film scene 1 introduction"},
                {"scene_index": 2, "provider_prompt": "Film scene 2 climax"},
            ],
            "plan_status": "ready",
        },
    )
    pricing = _pricing_snapshot(tier_id, scene_count=2)
    invoiced = video_tail9.select_package(
        state,
        quality_tier_id=str(tier_id),
        package_id=f"product_video_{tier_id}",
        pricing_snapshot=pricing,
        capability_snapshot={"ok": True, "required_capability": "text_to_video"},
    )
    assert invoiced["status_stage"] == "invoice"
    assert video_tail9.invoice_allowed(invoiced) == (True, "ok")
    confirmed, created = video_tail9.confirm_once(invoiced, f"confirm-film-{tier_id}")
    assert created is True
    assert confirmed["final_confirmed"] is True


# ==============================================================================
# LANE 7: video_long (Phim dài tập) All 10 Tiers
# ==============================================================================


@pytest.mark.parametrize("tier_id", ALL_CANONICAL_TIERS)
def test_video_long_supports_all_ten_tiers(tier_id: int) -> None:
    contract = video_tail9.commercial_contract("video_long")
    assert tier_id in contract["supported_quality_tiers"]

    catalog = video_uifreeze1.catalog_report("video_long", scene_count=2, ratio="9:16")
    assert catalog["ok"] is True
    assert tier_id in catalog["tier_ids"]

    state = video_tail9.new_state(
        product_type="video_long",
        execution_product_type="multi_scene_film",
        session_id=f"vlong-tier-{tier_id}",
        scene_count=2,
        ratio="9:16",
    )
    state = video_tail9.apply_content_contract(
        state,
        {
            "content_source": "manual",
            "selected_prompt_text": "Episodic narrative long video plan",
            "per_scene_content": [
                {"scene_index": 1, "provider_prompt": "Episode 1 opening scene"},
                {"scene_index": 2, "provider_prompt": "Episode 1 resolution scene"},
            ],
            "plan_status": "ready",
        },
    )
    pricing = _pricing_snapshot(tier_id, scene_count=2)
    invoiced = video_tail9.select_package(
        state,
        quality_tier_id=str(tier_id),
        package_id=f"product_video_{tier_id}",
        pricing_snapshot=pricing,
        capability_snapshot={"ok": True, "required_capability": "text_to_video"},
    )
    assert invoiced["status_stage"] == "invoice"
    assert video_tail9.invoice_allowed(invoiced) == (True, "ok")


# ==============================================================================
# LANE 8: video_idea (Ý tưởng video) All 10 Tiers
# ==============================================================================


@pytest.mark.parametrize("tier_id", ALL_CANONICAL_TIERS)
def test_video_idea_supports_all_ten_tiers(tier_id: int) -> None:
    contract = video_tail9.commercial_contract("video_idea")
    assert tier_id in contract["supported_quality_tiers"]

    catalog = video_uifreeze1.catalog_report("video_idea", scene_count=2, ratio="9:16")
    assert catalog["ok"] is True
    assert tier_id in catalog["tier_ids"]

    state = video_tail9.new_state(
        product_type="video_idea",
        execution_product_type="video_idea_to_product",
        session_id=f"idea-tier-{tier_id}",
        scene_count=2,
        ratio="9:16",
    )
    state = video_tail9.apply_content_contract(
        state,
        {
            "content_source": "idea_preset",
            "selected_prompt_text": "High converting e-commerce video idea with curiosity hook",
            "per_scene_content": [
                {"scene_index": 1, "provider_prompt": "Problem presentation scene"},
                {"scene_index": 2, "provider_prompt": "Solution reveal scene"},
            ],
            "plan_status": "ready",
        },
    )
    pricing = _pricing_snapshot(tier_id, scene_count=2)
    invoiced = video_tail9.select_package(
        state,
        quality_tier_id=str(tier_id),
        package_id=f"product_video_{tier_id}",
        pricing_snapshot=pricing,
        capability_snapshot={"ok": True, "required_capability": "text_to_video"},
    )
    assert invoiced["status_stage"] == "invoice"
    assert video_tail9.invoice_allowed(invoiced) == (True, "ok")
    confirmed, created = video_tail9.confirm_once(invoiced, f"confirm-idea-{tier_id}")
    assert created is True
    assert confirmed["final_confirmed"] is True


# ==============================================================================
# LANE 9: video_local_edit / AI Edit All 10 Tiers
# ==============================================================================


@pytest.mark.parametrize("tier_id", ALL_CANONICAL_TIERS)
def test_video_local_edit_supports_all_ten_tiers(tier_id: int) -> None:
    contract = video_tail9.commercial_contract("video_local_edit")
    assert tier_id in contract["supported_quality_tiers"]

    catalog = video_uifreeze1.catalog_report("video_local_edit", scene_count=2, ratio="keep")
    assert catalog["ok"] is True
    assert tier_id in catalog["tier_ids"]

    state = video_tail9.new_state(
        product_type="video_local_edit",
        execution_product_type="video_local_edit",
        session_id=f"edit-tier-{tier_id}",
        scene_count=2,
        ratio="keep",
    )
    state = video_tail9.apply_content_contract(
        state,
        {
            "content_source": "source_video",
            "selected_prompt_text": "Local editing instructions: trim first 2s, crop 9:16",
            "per_scene_content": [
                {"scene_index": 1, "provider_prompt": "Trim segment 1"},
                {"scene_index": 2, "provider_prompt": "Trim segment 2"},
            ],
            "plan_status": "ready",
        },
    )
    pricing = _pricing_snapshot(tier_id, scene_count=2)
    invoiced = video_tail9.select_package(
        state,
        quality_tier_id=str(tier_id),
        package_id=f"product_video_{tier_id}",
        pricing_snapshot=pricing,
        capability_snapshot={"ok": True, "required_capability": "video_to_video"},
    )
    assert invoiced["status_stage"] == "invoice"
    assert video_tail9.invoice_allowed(invoiced) == (True, "ok")
    confirmed, created = video_tail9.confirm_once(invoiced, f"confirm-edit-{tier_id}")
    assert created is True
    assert confirmed["final_confirmed"] is True


# ==============================================================================
# LANE 10: frame_video_local Preserves Dedicated Local Pricing
# ==============================================================================


def test_frame_video_local_keeps_dedicated_pricing_flow() -> None:
    contract = video_tail9.commercial_contract("frame_video_local")
    assert contract["pricing_mode"] == "frame_video"
    catalog = video_uifreeze1.catalog_report("frame_video_local", scene_count=2)
    assert catalog["ok"] is False
    assert catalog["framevideo_excluded"] is True
    assert catalog["uses_canonical_pricing"] is False


# ==============================================================================
# CONTENT INVARIANT: Content Semantics Matches Product & Lane Natures
# ==============================================================================


def test_product_semantic_content_and_stage_distinctness() -> None:
    """Owner mandate: Content in UI/UX must match the nature of each product without generic drift."""
    products_and_nature = {
        "video_trend": ("trend_prompt", "searching_viral_trends", "locking_trend"),
        "video_ai_prompt": ("text_prompt", "refining_prompt", "rendering_scenes"),
        "video_ai_image": ("scene_images", "analyzing_keyframe_images", "planning_motion"),
        "video_ai_video_reference": ("source_video", "analyzing_reference_video", "extracting_motion_style"),
        "script_image_video": ("long_script", "locking_script", "rendering_scenes"),
        "storyboard_prompt": ("storyboard_frames", "locking_storyboard", "animating_scenes"),
        "self_shot_scene_change": ("source_video", "planning_scene_change", "changing_each_scene"),
        "self_shot_cinematic_transform": ("source_video", "planning_cinematic_timeline", "transforming_environment"),
        "multi_scene_film": ("long_form_plan", "locking_long_plan", "rendering_chapters"),
        "video_idea": ("idea_preset", "synthesizing_hook_ideas", "scripting_scenes"),
        "video_local_edit": ("source_video", "analyzing_source_video", "processing_ffmpeg_operations"),
    }
    for product, (expected_input, expected_stage1, expected_stage2) in products_and_nature.items():
        adapter = video_tail9.adapter_for(product)
        assert adapter["input_type"] == expected_input, f"{product} input_type mismatch: expected {expected_input}, got {adapter['input_type']}"
        contract = video_tail9.status_contract(product)
        stages = contract["product_stages"]
        assert expected_stage1 in stages, f"{product} missing stage {expected_stage1}"
        assert expected_stage2 in stages, f"{product} missing stage {expected_stage2}"


# ==============================================================================
# UI/UX INVARIANT: Zero Byte Modifications to 14 Locked UI Functions
# ==============================================================================


@pytest.mark.parametrize(
    ("function_name", "expected_sha256"),
    tuple(LOCKED_UI_FUNCTION_HASHES.items()),
)
def test_ui_ux_locked_function_hashes_remain_unchanged(
    function_name: str,
    expected_sha256: str,
) -> None:
    """Owner mandate: Completed UI/UX structure is immutable; 14/14 hashes must match."""
    bot_source = Path("bot.py").read_text(encoding="utf-8")
    match = re.search(
        rf"(?ms)^def {re.escape(function_name)}\(.*?(?=^(?:async )?def [A-Za-z_]|\Z)",
        bot_source,
    )
    assert match is not None, f"Function {function_name} not found in bot.py"
    actual_sha = hashlib.sha256(match.group(0).rstrip().encode("utf-8")).hexdigest()
    assert actual_sha == expected_sha256, f"Function {function_name} hash mutated!"


# ==============================================================================
# ZERO SIDE EFFECTS INVARIANT
# ==============================================================================


def test_zero_side_effects_on_all_catalog_reports() -> None:
    products = (
        "video_trend",
        "video_ai_real",
        "video_ai_prompt",
        "video_ai_image",
        "video_ai_video_reference",
        "script_image_video",
        "storyboard_prompt",
        "multi_scene_film",
        "video_long",
        "video_idea",
        "self_shot_scene_change",
        "self_shot_cinematic_transform",
        "video_local_edit",
    )
    for product in products:
        report = video_uifreeze1.catalog_report(product, scene_count=2)
        assert report["side_effects"] == {
            "job": 0,
            "outbox": 0,
            "provider_calls": 0,
            "generated_files": 0,
            "wallet_mutations": 0,
            "xu_charged": 0,
        }, product
