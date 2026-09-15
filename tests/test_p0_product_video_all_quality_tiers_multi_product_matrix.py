from __future__ import annotations

import pytest

from services import video_ai_real_pricing, video_tail9, video_uifreeze1


ALL_CANONICAL_TIERS = (400, 500, 600, 200, 300, 700, 800, 1000, 1200, 1500)
TREND_SUPPORTED_TIERS = (500, 600, 200, 300, 700, 800, 1000, 1200, 1500)


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
# SCENARIO 1: video_trend - Strict Exclusion of Tier 400 (80 Xu) & All 9 Other Tiers
# ==============================================================================


@pytest.mark.parametrize("tier_id", TREND_SUPPORTED_TIERS)
def test_video_trend_supports_all_nine_non_80xu_quality_tiers(tier_id: int) -> None:
    """Owner mandate: video_trend handles all quality tiers except 80 Xu (Tier 400)."""
    contract = video_tail9.commercial_contract("video_trend")
    assert 400 not in contract["supported_quality_tiers"]
    assert tier_id in contract["supported_quality_tiers"]

    # UI Catalog check
    catalog = video_uifreeze1.catalog_report("video_trend", scene_count=2, ratio="9:16")
    assert catalog["ok"] is True
    assert 400 not in catalog["tier_ids"]
    assert tier_id in catalog["tier_ids"]

    # Tail state lifecycle through invoice & confirmation
    state = video_tail9.new_state(
        product_type="video_trend",
        execution_product_type="video_trend",
        session_id=f"trend-tier-{tier_id}",
        scene_count=2,
        ratio="9:16",
    )
    state = video_tail9.apply_content_contract(
        state,
        {
            "content_source": "trend",
            "selected_prompt_text": "Approved viral trend prompt",
            "per_scene_content": [
                {"scene_index": 1, "provider_prompt": "Trend scene 1"},
                {"scene_index": 2, "provider_prompt": "Trend scene 2"},
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


def test_video_trend_strictly_blocks_tier_400_80xu() -> None:
    """Owner mandate: video_trend must strictly reject Tier 400 (80 Xu)."""
    contract = video_tail9.commercial_contract("video_trend")
    assert 400 not in contract["supported_quality_tiers"]

    # Catalog does not offer Tier 400
    catalog = video_uifreeze1.catalog_report("video_trend", scene_count=2, ratio="9:16")
    assert 400 not in catalog["tier_ids"]

    # package_compatibility returns quality_tier_not_supported
    compat = video_tail9.package_compatibility("video_trend", scene_count=2, ratio="9:16", quality_tier_id=400)
    assert compat["ok"] is False
    assert "quality_tier_not_supported" in compat["blockers"]

    # select_package raises ValueError
    state = video_tail9.new_state(
        product_type="video_trend",
        execution_product_type="video_trend",
        session_id="trend-tier-400-blocked",
        scene_count=2,
        ratio="9:16",
    )
    state = video_tail9.apply_content_contract(
        state,
        {
            "content_source": "trend",
            "selected_prompt_text": "Approved viral trend prompt",
            "per_scene_content": [{"scene_index": 1, "provider_prompt": "Scene 1"}],
            "plan_status": "ready",
        },
    )
    with pytest.raises(ValueError, match="quality_tier_not_supported"):
        video_tail9.select_package(
            state,
            quality_tier_id="400",
            package_id="product_video_400",
            pricing_snapshot=_pricing_snapshot(400, scene_count=2),
            capability_snapshot={"ok": True, "required_capability": "text_to_video"},
        )


# ==============================================================================
# SCENARIO 2: multi_scene_film (Video dài tập) Across Diverse Quality Tiers
# ==============================================================================


@pytest.mark.parametrize("tier_id", (400, 500, 700, 1500))
def test_multi_scene_film_supports_full_canonical_tiers_including_80xu_and_700(tier_id: int) -> None:
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
            "selected_prompt_text": "Multi-scene film script",
            "per_scene_content": [
                {"scene_index": 1, "provider_prompt": "Film scene 1"},
                {"scene_index": 2, "provider_prompt": "Film scene 2"},
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
# SCENARIO 3: script_image_video Across Diverse Quality Tiers (including 200, 300, 600, 1200)
# ==============================================================================


@pytest.mark.parametrize("tier_id", (200, 300, 600, 1200))
def test_script_image_video_supports_extended_tiers_including_200(tier_id: int) -> None:
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
            "selected_prompt_text": "5-scene master script",
            "per_scene_content": [
                {"scene_index": i, "provider_prompt": f"Script scene {i}"}
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


# ==============================================================================
# SCENARIO 4: storyboard_prompt Across Diverse Quality Tiers (including 200, 700, 800, 1000)
# ==============================================================================


@pytest.mark.parametrize("tier_id", (200, 700, 800, 1000))
def test_storyboard_prompt_supports_extended_tiers_including_200_and_700(tier_id: int) -> None:
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
            "selected_prompt_text": "Storyboard prompts with images",
            "per_scene_content": [
                {"scene_index": 1, "provider_prompt": "Frame 1 prompt", "asset_id": "img1"},
                {"scene_index": 2, "provider_prompt": "Frame 2 prompt", "asset_id": "img2"},
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


# ==============================================================================
# SCENARIO 5: self_shot_scene_change Across Tiers (300, 500, 800)
# ==============================================================================


@pytest.mark.parametrize("tier_id", (300, 500, 800))
def test_self_shot_scene_change_across_tiers(tier_id: int) -> None:
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
        session_id=f"selfshot-tier-{tier_id}",
        scene_count=2,
        ratio="keep",
    )
    state = video_tail9.apply_content_contract(
        state,
        {
            "content_source": "source_video",
            "selected_prompt_text": "Change background for selfshot",
            "per_scene_content": [
                {"scene_index": 1, "provider_prompt": "Scene 1 change"},
                {"scene_index": 2, "provider_prompt": "Scene 2 change"},
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


# ==============================================================================
# SCENARIO 6: video_ai_real Across All 10 Quality Tiers
# ==============================================================================


@pytest.mark.parametrize("tier_id", ALL_CANONICAL_TIERS)
def test_video_ai_real_supports_all_ten_canonical_tiers(tier_id: int) -> None:
    catalog = video_uifreeze1.catalog_report("video_ai_real", scene_count=2, ratio="9:16")
    assert catalog["ok"] is True
    assert tier_id in catalog["tier_ids"]

    pricing = _pricing_snapshot(tier_id, scene_count=2)
    assert pricing["total_xu"] > 0
    assert pricing["discount_percent"] == 10


# ==============================================================================
# SCENARIO 7: video_idea Across Tiers (400, 600, 1000)
# ==============================================================================


@pytest.mark.parametrize("tier_id", (400, 600, 1000))
def test_video_idea_supports_canonical_tiers(tier_id: int) -> None:
    contract = video_tail9.commercial_contract("video_idea")
    assert tier_id in contract["supported_quality_tiers"]

    catalog = video_uifreeze1.catalog_report("video_idea", scene_count=2, ratio="9:16")
    assert catalog["ok"] is True
    assert tier_id in catalog["tier_ids"]


# ==============================================================================
# SCENARIO 8: video_local_edit & AI Edit Contract Transparency
# ==============================================================================


def test_video_local_edit_and_ai_edit_contract_safety() -> None:
    contract = video_tail9.commercial_contract("video_local_edit")
    assert contract["pricing_mode"] == "canonical"
    assert set(ALL_CANONICAL_TIERS) <= set(contract["supported_quality_tiers"])

    catalog = video_uifreeze1.catalog_report("video_local_edit", scene_count=2, ratio="keep")
    assert catalog["ok"] is True
    assert set(ALL_CANONICAL_TIERS) <= set(catalog["tier_ids"])
    assert catalog["uses_canonical_pricing"] is True


# ==============================================================================
# SCENARIO 9: frame_video_local Preserves Specialized Pricing
# ==============================================================================


def test_frame_video_local_keeps_dedicated_pricing_flow() -> None:
    contract = video_tail9.commercial_contract("frame_video_local")
    assert contract["pricing_mode"] == "frame_video"
    catalog = video_uifreeze1.catalog_report("frame_video_local", scene_count=2)
    assert catalog["ok"] is False
    assert catalog["framevideo_excluded"] is True
    assert catalog["uses_canonical_pricing"] is False


# ==============================================================================
# SCENARIO 10: Zero Side Effects Invariant on All Catalog Reports
# ==============================================================================


def test_zero_side_effects_on_all_catalog_reports() -> None:
    products = (
        "video_trend",
        "video_ai_real",
        "script_image_video",
        "storyboard_prompt",
        "multi_scene_film",
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
