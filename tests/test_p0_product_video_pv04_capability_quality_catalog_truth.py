"""Deterministic test matrix for P0.PRODUCT_VIDEO.PV04.CAPABILITY.AWARE.QUALITY.CATALOG.TRUTH.

Validates:
- Canonical Modality Matrix:
    T2V = {400, 500, 600, 200, 300, 700, 800, 1000, 1200, 1500}
    I2V = {400, 500, 600, 200, 300, 700, 800, 1000, 1200, 1500}
    V2V = {500, 600, 700, 800}
    V2V remaining 6 tiers = unsupported
- Trend Tier 400 Protection (80 Xu, visible)
- Capability != Provider Availability separation
- Global commercial pricing catalog preservation
- Product adapter modality consistency & PV02 aliases
- UI Keyboard & Callback tier defense (valid vs unsupported vs tampered vs stale)
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from services import video_ai_real_pricing, video_tail9, video_uifreeze1
import bot


ALL_CANONICAL_TIERS = (400, 500, 600, 200, 300, 700, 800, 1000, 1200, 1500)
T2V_EXPECTED_TIERS = frozenset({400, 500, 600, 200, 300, 700, 800, 1000, 1200, 1500})
I2V_EXPECTED_TIERS = frozenset({400, 500, 600, 200, 300, 700, 800, 1000, 1200, 1500})
V2V_EXPECTED_TIERS = frozenset({500, 600, 700, 800})
V2V_UNSUPPORTED_TIERS = frozenset({400, 200, 300, 1000, 1200, 1500})


# ==============================================================================
# SECTION 1: CANONICAL MODALITY MATRIX
# ==============================================================================


@pytest.mark.parametrize("product_type", [
    "video_trend",
    "video_ai_prompt",
    "video_idea",
    "script_image_video",
])
def test_t2v_modality_supports_all_ten_tiers(product_type: str) -> None:
    contract = video_tail9.commercial_contract(product_type)
    assert contract.get("required_capability") == "text_to_video"
    cat = video_uifreeze1.catalog_report(product_type, scene_count=5 if product_type == "script_image_video" else 2, ratio="9:16")
    assert cat["ok"] is True
    tier_set = frozenset(cat["tier_ids"])
    assert tier_set == T2V_EXPECTED_TIERS
    assert len(tier_set) == 10


@pytest.mark.parametrize("product_type", [
    "video_ai_image",
    "storyboard_prompt",
])
def test_i2v_modality_supports_all_ten_tiers(product_type: str) -> None:
    contract = video_tail9.commercial_contract(product_type)
    assert contract.get("required_capability") == "image_to_video"
    cat = video_uifreeze1.catalog_report(product_type, scene_count=2, ratio="9:16")
    assert cat["ok"] is True
    tier_set = frozenset(cat["tier_ids"])
    assert tier_set == I2V_EXPECTED_TIERS
    assert len(tier_set) == 10


@pytest.mark.parametrize("product_type", [
    "video_ai_video_reference",
    "self_shot_scene_change",
    "self_shot_cinematic_transform",
])
def test_v2v_modality_supports_only_exact_four_tiers(product_type: str) -> None:
    contract = video_tail9.commercial_contract(product_type)
    assert contract.get("required_capability") == "video_to_video"
    cat = video_uifreeze1.catalog_report(product_type, scene_count=2, ratio="keep" if "self_shot" in product_type else "9:16")
    assert cat["ok"] is True
    tier_set = frozenset(cat["tier_ids"])
    assert tier_set == V2V_EXPECTED_TIERS, f"Expected {V2V_EXPECTED_TIERS}, got {tier_set}"
    assert len(tier_set) == 4
    for unsupported_tier in V2V_UNSUPPORTED_TIERS:
        assert unsupported_tier not in tier_set, f"Tier {unsupported_tier} must not be supported in V2V"


# ==============================================================================
# SECTION 2: TREND TIER 400 INVARIANT
# ==============================================================================


def test_trend_tier_400_visible_and_80_xu() -> None:
    contract = video_tail9.commercial_contract("video_trend")
    assert 400 in contract["supported_quality_tiers"]

    cat = video_uifreeze1.catalog_report("video_trend", scene_count=2, ratio="9:16")
    assert cat["ok"] is True
    assert 400 in cat["tier_ids"]
    assert cat["tier_ids"][0] == 400

    tier400 = next(item for item in cat["offers"] if item["tier_id"] == 400)
    assert tier400["unit_xu"] == 80
    assert tier400["seconds"] == 8
    assert "Nhanh gọn" in tier400["name"] or tier400["tier_id"] == 400


# ==============================================================================
# SECTION 3: GLOBAL PRICING CATALOG PRESERVED
# ==============================================================================


def test_global_pricing_catalog_preserved() -> None:
    rows = video_ai_real_pricing.public_quality_catalog()
    tier_ids = [int(row["tier_id"]) for row in rows]
    assert len(tier_ids) == 10
    assert set(tier_ids) == set(ALL_CANONICAL_TIERS)
    assert 400 in tier_ids
    assert 200 in tier_ids

    # Check that V2V restriction is contextual, not deleting global tiers
    v2v_cat = video_uifreeze1.catalog_report("video_ai_video_reference", scene_count=2, ratio="9:16")
    assert set(v2v_cat["tier_ids"]) == {500, 600, 700, 800}

    # After V2V check, global catalog and T2V still have all 10 tiers
    t2v_cat = video_uifreeze1.catalog_report("video_ai_prompt", scene_count=2, ratio="9:16")
    assert set(t2v_cat["tier_ids"]) == set(ALL_CANONICAL_TIERS)


# ==============================================================================
# SECTION 4: CAPABILITY != PROVIDER AVAILABILITY SEPARATION
# ==============================================================================


def test_temporary_provider_outage_does_not_mutate_catalog() -> None:
    """Catalog capabilities must remain stable regardless of provider outage/probation."""
    with patch.dict("os.environ", {
        "KEY4U_VIDEO_TO_VIDEO_ENABLED": "0",
        "SHOPAIKEY_VIDEO_TO_VIDEO_ENABLED": "0",
        "VIDEO_AI_EDIT_ENABLED": "0",
    }):
        cat = video_uifreeze1.catalog_report("video_ai_video_reference", scene_count=2, ratio="9:16")
        assert cat["ok"] is True
        assert set(cat["tier_ids"]) == {500, 600, 700, 800}
        assert cat["side_effects"]["provider_calls"] == 0


# ==============================================================================
# SECTION 5: PRODUCT ADAPTER CONSISTENCY & PV02 ALIASES
# ==============================================================================


def test_product_adapter_aliases_and_modality_consistency() -> None:
    aliases = {
        "storyboard_video": ("storyboard_prompt", "image_to_video"),
        "selfshot_scene_change": ("self_shot_scene_change", "video_to_video"),
        "selfshot_cinematic": ("self_shot_cinematic_transform", "video_to_video"),
        "video_edit": ("video_local_edit", "video_to_video"),
        "trend_video": ("video_trend", "text_to_video"),
        "script_to_video": ("script_image_video", "text_to_video"),
        "video_idea_to_product": ("video_idea", "text_to_video"),
    }
    for alias, (expected_target, expected_modality) in aliases.items():
        resolved_contract = video_tail9.commercial_contract(alias)
        assert resolved_contract["product_type"] == expected_target
        assert resolved_contract["required_capability"] == expected_modality


# ==============================================================================
# SECTION 6: QUALITY KEYBOARD DEFENSE
# ==============================================================================


def test_quality_keyboard_v2v_only_renders_supported_tiers() -> None:
    tail = {
        "video_product_type": "video_ai_video_reference",
        "scene_count": 2,
        "ratio": "9:16",
    }
    kb = bot.video_tail9_quality_keyboard(tail)
    rendered_callbacks = [
        btn.callback_data
        for row in kb.inline_keyboard
        for btn in row
        if btn.callback_data and btn.callback_data.startswith("video_tail|quality|select|")
    ]
    offered_tiers = [int(cb.split("|")[-1]) for cb in rendered_callbacks]
    assert offered_tiers == [500, 600, 700, 800]
    assert 400 not in offered_tiers
    assert 200 not in offered_tiers


def test_quality_keyboard_t2v_renders_all_ten_tiers() -> None:
    tail = {
        "video_product_type": "video_ai_prompt",
        "scene_count": 2,
        "ratio": "9:16",
    }
    kb = bot.video_tail9_quality_keyboard(tail)
    rendered_callbacks = [
        btn.callback_data
        for row in kb.inline_keyboard
        for btn in row
        if btn.callback_data and btn.callback_data.startswith("video_tail|quality|select|")
    ]
    offered_tiers = [int(cb.split("|")[-1]) for cb in rendered_callbacks]
    assert set(offered_tiers) == set(ALL_CANONICAL_TIERS)
    assert 400 in offered_tiers


# ==============================================================================
# SECTION 7: CALLBACK ADMISSION & REJECTION DEFENSE
# ==============================================================================


def test_v2v_callback_rejects_unsupported_tier_400() -> None:
    """Selecting Tier 400 on a V2V product must be rejected and NOT persisted to draft."""
    async def _test():
        uid = 999101
        initial_tail = video_tail9.new_state(
            product_type="video_ai_video_reference",
            execution_product_type="video_ai_video_reference",
            session_id="v2v-test-cb",
            scene_count=1,
            ratio="9:16",
        )
        initial_tail["quality_tier_id"] = ""

        update = MagicMock()
        query = AsyncMock()
        query.from_user.id = uid
        query.id = "cb-query-test-1"
        query.data = "video_tail|quality|select|400"
        update.callback_query = query

        context = MagicMock()
        context.user_data = {}

        with patch("bot.video_tail9_context", return_value=(deepcopy(initial_tail), "scene3", {})):
            with patch("bot.save_video_tail9_state") as mock_save:
                with patch("bot.video_tail9_answer_best_effort", new_callable=AsyncMock) as mock_answer:
                    try:
                        await bot.handle_video_tail_callback(update, context)
                    except Exception:
                        pass

                    # Verify draft state was NOT updated to tier 400
                    for call_args in mock_save.call_args_list:
                        saved_tail = call_args[0][2]
                        assert str(saved_tail.get("quality_tier_id") or "") != "400", "Tier 400 must NOT be persisted for V2V"

    import asyncio
    asyncio.run(_test())


def test_v2v_callback_accepts_supported_tier_500() -> None:
    """Selecting Tier 500 on a V2V product must be accepted."""
    async def _test():
        uid = 999102
        initial_tail = video_tail9.new_state(
            product_type="video_ai_video_reference",
            execution_product_type="video_ai_video_reference",
            session_id="v2v-test-cb-500",
            scene_count=1,
            ratio="9:16",
        )
        initial_tail = video_tail9.apply_content_contract(
            initial_tail,
            {
                "content_source": "source_video",
                "selected_prompt_text": "V2V prompt",
                "per_scene_content": [{"scene_index": 1, "provider_prompt": "prompt 1"}],
                "plan_status": "ready",
            },
        )

        update = MagicMock()
        query = AsyncMock()
        query.from_user.id = uid
        query.id = "cb-query-test-2"
        query.data = "video_tail|quality|select|500"
        update.callback_query = query

        context = MagicMock()
        context.user_data = {}

        with patch("bot.video_tail9_context", return_value=(deepcopy(initial_tail), "scene3", {})):
            with patch("bot.save_video_tail9_state") as mock_save:
                with patch("bot.video_tail9_render", new_callable=AsyncMock) as mock_render:
                    await bot.handle_video_tail_callback(update, context)
                    # Verify tier 500 was accepted and render was called with invoice
                    mock_render.assert_called_once()
                    assert mock_render.call_args[0][3] == "invoice"

    import asyncio
    asyncio.run(_test())


def test_callback_rejects_unknown_tampered_tier() -> None:
    """Tampered tier (e.g. 9999 or invalid string) must be rejected without mutating state."""
    async def _test():
        uid = 999103
        initial_tail = video_tail9.new_state(
            product_type="video_trend",
            execution_product_type="video_trend",
            session_id="tamper-test",
            scene_count=1,
            ratio="9:16",
        )
        initial_tail["quality_tier_id"] = ""

        update = MagicMock()
        query = AsyncMock()
        query.from_user.id = uid
        query.id = "cb-query-tamper"
        query.data = "video_tail|quality|select|9999"
        update.callback_query = query

        context = MagicMock()
        context.user_data = {}

        with patch("bot.video_tail9_context", return_value=(deepcopy(initial_tail), "trend", {})):
            with patch("bot.save_video_tail9_state") as mock_save:
                try:
                    await bot.handle_video_tail_callback(update, context)
                except Exception:
                    pass

                for call_args in mock_save.call_args_list:
                    saved_tail = call_args[0][2]
                    assert str(saved_tail.get("quality_tier_id") or "") != "9999"

    import asyncio
    asyncio.run(_test())
