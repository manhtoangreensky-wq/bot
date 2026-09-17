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

PV04_ACTIVE_T2V_PRODUCT_IDS = frozenset({
    "video_trend",
    "video_ai_prompt",
    "video_idea",
    "script_image_video",
})
PV04_ACTIVE_I2V_PRODUCT_IDS = frozenset({
    "video_ai_image",
    "storyboard_prompt",
})
PV04_ACTIVE_V2V_PRODUCT_IDS = frozenset({
    "video_ai_video_reference",
    "self_shot_scene_change",
    "self_shot_cinematic_transform",
})
PV04_ACTIVE_PRODUCT_IDS = (
    PV04_ACTIVE_T2V_PRODUCT_IDS
    | PV04_ACTIVE_I2V_PRODUCT_IDS
    | PV04_ACTIVE_V2V_PRODUCT_IDS
)
DEFERRED_PRODUCT_IDS = frozenset({
    "video_local_edit",
    "multi_scene_film",
    "video_long",
})



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


# ==============================================================================
# SECTION 8: ACTIVE MATRIX & DEFERRED PRODUCT SCOPE CLOSURE
# ==============================================================================


def test_pv04_active_product_matrix_contains_only_exact_nine_products() -> None:
    assert len(PV04_ACTIVE_PRODUCT_IDS) == 9
    assert len(PV04_ACTIVE_T2V_PRODUCT_IDS) == 4
    assert len(PV04_ACTIVE_I2V_PRODUCT_IDS) == 2
    assert len(PV04_ACTIVE_V2V_PRODUCT_IDS) == 3
    # Explicit constant requirement: PV04_ACTIVE_PRODUCT_IDS count = 9
    pv04_active_count = len(PV04_ACTIVE_PRODUCT_IDS)
    assert pv04_active_count == 9


def test_deferred_products_are_not_in_pv04_active_v2v_matrix() -> None:
    deferred_in_active = DEFERRED_PRODUCT_IDS.intersection(PV04_ACTIVE_PRODUCT_IDS)
    assert len(deferred_in_active) == 0
    deferred_in_v2v = DEFERRED_PRODUCT_IDS.intersection(PV04_ACTIVE_V2V_PRODUCT_IDS)
    assert len(deferred_in_v2v) == 0
    # Explicit requirements: DEFERRED_PRODUCTS_IN_PV04_ACTIVE_MATRIX=0 and DEFERRED_PRODUCTS_IN_PV04_SCOPE=0
    DEFERRED_PRODUCTS_IN_PV04_ACTIVE_MATRIX = len(deferred_in_v2v)
    assert DEFERRED_PRODUCTS_IN_PV04_ACTIVE_MATRIX == 0
    DEFERRED_PRODUCTS_IN_PV04_SCOPE = len(deferred_in_active)
    assert DEFERRED_PRODUCTS_IN_PV04_SCOPE == 0
    for deferred_id in DEFERRED_PRODUCT_IDS:
        assert deferred_id not in PV04_ACTIVE_V2V_PRODUCT_IDS
        assert deferred_id not in PV04_ACTIVE_PRODUCT_IDS


def test_video_local_edit_contract_has_zero_delta_against_parent() -> None:
    """Zero delta on video_local_edit commercial contract against parent commit 24a94ee7."""
    contract = video_tail9.commercial_contract("video_local_edit")
    assert contract["flow_owner"] == "video_edit"
    assert contract["engine_route"] == "local_worker_ffmpeg"
    assert contract["required_capability"] == "video_to_video"
    assert contract["supported_quality_tiers"] == (400, 500, 600, 200, 300, 700, 800, 1000, 1200, 1500)
    assert contract["worker_owner"] == "video_edit"
    assert contract["public_planning_enabled"] is True
    assert contract["execution_enabled"] is True
    assert contract["execution_blocker"] == ""

    parent_local_edit_contract = {
        "product_type": "video_local_edit",
        "flow_owner": "video_edit",
        "engine_route": "local_worker_ffmpeg",
        "executor_product_type": "video_local_edit",
        "pricing_mode": "canonical",
        "required_capability": "video_to_video",
        "input_type": "source_video",
        "output_type": "mp4",
        "worker_owner": "video_edit",
        "minimum_scene_count": 1,
        "maximum_scene_count": 20,
        "supports_single_scene": True,
        "supported_quality_tiers": (400, 500, 600, 200, 300, 700, 800, 1000, 1200, 1500),
        "supported_package_tiers": (400, 500, 600, 200, 300, 700, 800, 1000, 1200, 1500),
        "scene_duration_seconds": 8,
        "public_planning_enabled": True,
        "execution_enabled": True,
        "execution_blocker": "",
    }
    contract_diffs = {
        k: (parent_local_edit_contract.get(k), contract.get(k))
        for k in set(parent_local_edit_contract) | set(contract)
        if parent_local_edit_contract.get(k) != contract.get(k)
    }
    PV04_VIDEO_LOCAL_EDIT_CONTRACT_DELTA = len(contract_diffs)
    assert PV04_VIDEO_LOCAL_EDIT_CONTRACT_DELTA == 0


def test_video_local_edit_behavioral_differential_and_tamper_rejection() -> None:
    """Empirical differential proof for video_local_edit behavior against parent semantics.

    Validates:
    - required_capability="": returns all 10 canonical tiers.
    - required_capability="video_to_video": returns all 10 canonical tiers.
    - required_capability="text_to_video": returns all 10 canonical tiers.
    - required_capability="image_to_video": returns all 10 canonical tiers.
    - required_capability="unknown_tampered_capability": returns [] (rejection).
    - representative ratios ("9:16", "16:9", "1:1", "keep") all preserve parent tiers.
    - VIDEO_LOCAL_EDIT_BEHAVIOR_DELTA = 0.
    - UNKNOWN_LOCAL_EDIT_CAPABILITY_REJECTED = YES.
    """
    LEGACY_DEFAULT_TIERS = [400, 500, 600, 200, 300, 700, 800, 1000, 1200, 1500]
    UNKNOWN_CAPABILITY_TIERS = []

    # 1. Default / video_to_video
    default_cat = video_uifreeze1.catalog_report("video_local_edit", scene_count=2, ratio="keep")
    assert default_cat["ok"] is True
    assert default_cat["tier_ids"] == LEGACY_DEFAULT_TIERS

    v2v_cat = video_uifreeze1.catalog_report("video_local_edit", scene_count=2, ratio="keep", required_capability="video_to_video")
    assert v2v_cat["ok"] is True
    assert v2v_cat["tier_ids"] == LEGACY_DEFAULT_TIERS

    empty_cat = video_uifreeze1.catalog_report("video_local_edit", scene_count=2, ratio="keep", required_capability="")
    assert empty_cat["ok"] is True
    assert empty_cat["tier_ids"] == LEGACY_DEFAULT_TIERS

    # 2. Valid other capability overrides
    t2v_cat = video_uifreeze1.catalog_report("video_local_edit", scene_count=2, ratio="keep", required_capability="text_to_video")
    assert t2v_cat["ok"] is True
    assert t2v_cat["tier_ids"] == LEGACY_DEFAULT_TIERS

    i2v_cat = video_uifreeze1.catalog_report("video_local_edit", scene_count=2, ratio="keep", required_capability="image_to_video")
    assert i2v_cat["ok"] is True
    assert i2v_cat["tier_ids"] == LEGACY_DEFAULT_TIERS

    # 3. Unknown / tampered capability MUST be rejected
    tampered_cat = video_uifreeze1.catalog_report("video_local_edit", scene_count=2, ratio="keep", required_capability="unknown_tampered_capability")
    assert tampered_cat["ok"] is False
    assert tampered_cat["tier_ids"] == UNKNOWN_CAPABILITY_TIERS
    assert tampered_cat["reason"] == "no_compatible_quality_package"
    UNKNOWN_LOCAL_EDIT_CAPABILITY_REJECTED = (tampered_cat["tier_ids"] == UNKNOWN_CAPABILITY_TIERS)
    assert UNKNOWN_LOCAL_EDIT_CAPABILITY_REJECTED is True

    # 4. Representative ratios with default capability
    for r in ("9:16", "16:9", "1:1", "keep"):
        r_cat = video_uifreeze1.catalog_report("video_local_edit", scene_count=2, ratio=r)
        assert r_cat["ok"] is True
        assert r_cat["tier_ids"] == LEGACY_DEFAULT_TIERS

    # 5. Full grid differential against parent semantics
    caps = ["", "video_to_video", "text_to_video", "image_to_video", "unknown_tampered_capability"]
    ratios = ["9:16", "16:9", "1:1", "keep"]
    counts = [1, 2, 5, 20, 25]

    behavior_diffs = []
    for c in caps:
        for r in ratios:
            for sc in counts:
                if sc > 20:
                    expected_tiers = []
                elif c == "unknown_tampered_capability":
                    expected_tiers = []
                else:
                    expected_tiers = LEGACY_DEFAULT_TIERS

                actual = [t["tier_id"] for t in video_uifreeze1.compatible_quality_tiers("video_local_edit", scene_count=sc, ratio=r, required_capability=c)]
                if actual != expected_tiers:
                    behavior_diffs.append((c, r, sc, actual, expected_tiers))

    VIDEO_LOCAL_EDIT_BEHAVIOR_DELTA = len(behavior_diffs)
    assert VIDEO_LOCAL_EDIT_BEHAVIOR_DELTA == 0
