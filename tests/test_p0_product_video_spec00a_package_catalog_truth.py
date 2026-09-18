from __future__ import annotations

import pytest
from services import video_ai_real_pricing, video_tail9, video_uifreeze1, video_flow6


PRODUCT_FAMILIES = (
    "video_trend",
    "video_ai_real",
    "video_ai_prompt",
    "video_ai_image",
    "video_ai_video_reference",
    "script_image_video",
    "storyboard_prompt",
    "self_shot_scene_change",
    "self_shot_cinematic_transform",
    "video_idea",
)

ALL_CANONICAL_TIERS = (400, 500, 600, 200, 300, 700, 800, 1000, 1200, 1500)


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


def test_video_trend_80xu_canonical_catalog_present() -> None:
    contract = video_tail9.commercial_contract("video_trend")
    assert 400 in contract["supported_quality_tiers"]

    cat = video_uifreeze1.catalog_report("video_trend", scene_count=2, ratio="9:16")
    assert cat["ok"] is True
    assert 400 in cat["tier_ids"]
    assert cat["tier_ids"][0] == 400

    tier400 = next(o for o in cat["offers"] if o["tier_id"] == 400)
    assert tier400["unit_xu"] == 80
    assert tier400["seconds"] == 8


@pytest.mark.parametrize("product", PRODUCT_FAMILIES)
def test_no_hide_to_pass_invariant_catalog_ignores_runtime_outages(product: str) -> None:
    count = 5 if product == "script_image_video" else 2
    cat = video_uifreeze1.catalog_report(product, scene_count=count, ratio="9:16")
    assert cat["ok"] is True
    assert len(cat["offers"]) > 0
    if product in {"video_ai_video_reference", "self_shot_scene_change", "self_shot_cinematic_transform"}:
        assert 500 in cat["tier_ids"]
        assert 400 not in cat["tier_ids"]
    else:
        assert 400 in cat["tier_ids"]


@pytest.mark.parametrize("tier_id", ALL_CANONICAL_TIERS)
def test_video_trend_all_tiers_reach_confirmed_state(tier_id: int) -> None:
    state = video_tail9.new_state(
        product_type="video_trend",
        execution_product_type="video_trend",
        session_id=f"trend-test-{tier_id}",
        scene_count=2,
        ratio="9:16",
    )
    state = video_tail9.apply_content_contract(
        state,
        {
            "content_source": "trend",
            "selected_prompt_text": "Sample trend prompt",
            "per_scene_content": [
                {"scene_index": 1, "provider_prompt": "Scene 1 prompt"},
                {"scene_index": 2, "provider_prompt": "Scene 2 prompt"},
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

    allowed, reason = video_tail9.invoice_allowed(invoiced)
    assert allowed is True
    assert reason == "ok"

    confirmed, created = video_tail9.confirm_once(invoiced, f"confirm-token-{tier_id}")
    assert created is True
    assert confirmed["final_confirmed"] is True

    replayed, created_again = video_tail9.confirm_once(confirmed, f"confirm-token-{tier_id}")
    assert created_again is False


def test_preflight_fail_closed_when_execution_owner_unavailable() -> None:
    context_state = {
        "product_type": "video_trend",
        "flow_kind": "trend_video",
        "content_mode": "prompt",
        "scene_count": 2,
        "aspect_ratio": "9:16",
        "trend_source": {
            "source_type": "user_topic",
        },
    }
    result = video_flow6.preflight(
        context_state,
        package_available=True,
        engine_ready=False,
        worker_ready=False,
        capability_ready=True,
    )
    assert result["ok"] is False
    assert "execution_owner_unavailable" in result["blockers"]
    assert "worker_runtime_unavailable" in result["blockers"]


def test_premium_packages_and_prices_strictly_preserved() -> None:
    expected_tiers = {
        400: 80,
        500: 110,
        600: 160,
        200: 200,
        300: 220,
        700: 220,
        800: 370,
        1000: 370,
        1200: 1260,
        1500: 2360,
    }
    for tier_id, expected_price in expected_tiers.items():
        spec = video_uifreeze1.tier_spec(tier_id)
        assert spec["unit_xu"] == expected_price
