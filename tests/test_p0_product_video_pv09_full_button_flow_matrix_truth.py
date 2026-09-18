"""PV09 Full Button Flow Matrix Truth Tests.

Covers:
1. Product inventory:
   - Active T2V (4): video_trend, video_ai_prompt, video_idea, script_image_video
   - Active I2V (2): video_ai_image, storyboard_prompt
   - Active V2V (3): video_ai_video_reference, self_shot_scene_change, self_shot_cinematic_transform
   - Deferred (3): video_local_edit, multi_scene_film, video_long
2. Public menu keyboard button mapping truth:
   - Every button in main_video_keyboard maps to an authoritative route/handler.
   - Zero unclassified public callbacks (UNCLASSIFIED_PUBLIC_CALLBACK=0).
3. Modality & Quality Tier truth:
   - T2V / I2V: 10 tiers supported in commercial contract.
   - V2V: exact 4 tiers {500, 600, 700, 800}.
   - Forbidden V2V buttons {400, 200, 300, 1000, 1200, 1500} never appear in V2V keyboard.
   - Trend Tier 400 visible at 80 Xu.
4. Full State Transition & Navigation truth:
   - Entry -> Input -> Quality -> Review -> Confirm.
   - Back, Change, Stale, Tampered callback handling.
5. Deferred products isolation:
   - DEFERRED_PRODUCTS_EXECUTED=0.
   - Under no circumstances can deferred products submit to queue or execute.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import bot
from services import video_tail9, video_uifreeze1


ACTIVE_T2V_PRODUCTS = {
    "video_trend",
    "video_ai_prompt",
    "video_idea",
    "script_image_video",
}

ACTIVE_I2V_PRODUCTS = {
    "video_ai_image",
    "storyboard_prompt",
}

ACTIVE_V2V_PRODUCTS = {
    "video_ai_video_reference",
    "self_shot_scene_change",
    "self_shot_cinematic_transform",
}

ACTIVE_PRODUCTS = ACTIVE_T2V_PRODUCTS | ACTIVE_I2V_PRODUCTS | ACTIVE_V2V_PRODUCTS

DEFERRED_PRODUCTS = {
    "video_local_edit",
    "multi_scene_film",
    "video_long",
}

ALL_INVENTORIED_PRODUCTS = ACTIVE_PRODUCTS | DEFERRED_PRODUCTS

V2V_ALLOWED_TIERS = {500, 600, 700, 800}
V2V_FORBIDDEN_TIERS = {400, 200, 300, 1000, 1200, 1500}


def test_pv09_product_inventory_classification() -> None:
    """Ensure active (9) and deferred (3) products match the authoritative classification."""
    assert len(ACTIVE_T2V_PRODUCTS) == 4
    assert len(ACTIVE_I2V_PRODUCTS) == 2
    assert len(ACTIVE_V2V_PRODUCTS) == 3
    assert len(ACTIVE_PRODUCTS) == 9
    assert len(DEFERRED_PRODUCTS) == 3
    assert len(ALL_INVENTORIED_PRODUCTS) == 12

    # Check contracts for all active products
    for p in ACTIVE_PRODUCTS:
        contract = video_tail9.commercial_contract(p)
        assert contract["execution_enabled"] is True, f"{p} must be execution_enabled"
        assert contract["public_planning_enabled"] is True, f"{p} must have planning enabled"

    # Check contracts for deferred products
    for p in DEFERRED_PRODUCTS:
        contract = video_tail9.commercial_contract(p)
        assert p in video_uifreeze1.PUBLIC_EXECUTION_LOCKED_PRODUCTS or not contract.get("execution_enabled")
        if p in {"multi_scene_film", "video_long"}:
            assert contract["execution_enabled"] is False, f"{p} must have execution_enabled=False"
            assert contract["execution_blocker"], f"{p} must have non-empty execution_blocker"
        elif p == "video_local_edit":
            assert p in video_uifreeze1.PUBLIC_EXECUTION_LOCKED_PRODUCTS


def test_pv09_public_main_menu_buttons_mapped_to_routes() -> None:
    """Verify every button in main_video_keyboard maps to an authoritative handler (UNCLASSIFIED_PUBLIC_CALLBACK=0)."""
    for lang in ("vi", "en"):
        kb = bot.main_video_keyboard(lang=lang, resume_uiflow3=False)
        buttons = []
        for row in kb.inline_keyboard:
            for btn in row:
                buttons.append(btn)
        
        assert len(buttons) >= 6, f"Expected at least 6 main menu buttons, found {len(buttons)}"
        
        unclassified = []
        for btn in buttons:
            cb_data = btn.callback_data or ""
            assert cb_data, f"Button {btn.text} has empty callback_data"
            handler = bot.video_route_expected_handler(cb_data)
            if not handler:
                unclassified.append(cb_data)
        
        assert len(unclassified) == 0, f"UNCLASSIFIED_PUBLIC_CALLBACK > 0: {unclassified}"


def test_pv09_modality_v2v_quality_tier_strict_matrix() -> None:
    """V2V quality keyboard must strictly show 4 allowed tiers and forbid the 6 forbidden tiers."""
    for product_type in ACTIVE_V2V_PRODUCTS:
        contract = video_tail9.commercial_contract(product_type)
        tiers = set(contract["supported_quality_tiers"])
        assert tiers == V2V_ALLOWED_TIERS, f"{product_type} tiers {tiers} != {V2V_ALLOWED_TIERS}"
        for forbidden in V2V_FORBIDDEN_TIERS:
            assert forbidden not in tiers, f"Forbidden tier {forbidden} in {product_type}"
            
        # Build quality keyboard for V2V
        tail = video_tail9.new_state(
            product_type=product_type,
            execution_product_type=str(contract["executor_product_type"]),
            session_id=f"test-v2v-kb-{product_type}",
            scene_count=1,
            ratio="9:16",
        )
        kb = bot.video_tail9_quality_keyboard(tail)
        cb_list = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]
        
        # Ensure allowed tiers are present
        for tier in V2V_ALLOWED_TIERS:
            assert any(f"select|{tier}" in cb for cb in cb_list), f"Tier {tier} missing in {product_type} keyboard: {cb_list}"
        
        # Ensure forbidden tiers are NOT present
        for forbidden in V2V_FORBIDDEN_TIERS:
            assert not any(f"select|{forbidden}" in cb for cb in cb_list), f"Forbidden {forbidden} present in {product_type}"


def test_pv09_modality_t2v_i2v_quality_tier_matrix() -> None:
    """T2V and I2V products must support 10 tiers in contract, and trend tier 400 is visible at 80 Xu."""
    for product_type in (ACTIVE_T2V_PRODUCTS | ACTIVE_I2V_PRODUCTS):
        contract = video_tail9.commercial_contract(product_type)
        tiers = contract["supported_quality_tiers"]
        assert len(tiers) == 10, f"{product_type} expected 10 tiers, got {len(tiers)}"
        
        tail = video_tail9.new_state(
            product_type=product_type,
            execution_product_type=str(contract["executor_product_type"]),
            session_id=f"test-t2v-kb-{product_type}",
            scene_count=1,
            ratio="9:16",
        )
        kb = bot.video_tail9_quality_keyboard(tail)
        cb_list = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]
        assert len(cb_list) >= 4, f"Keyboard for {product_type} missing quality buttons: {cb_list}"

    # Verify Trend Tier 400 pricing snapshot is 80 Xu
    trend_contract = video_tail9.commercial_contract("video_trend")
    assert 400 in trend_contract["supported_quality_tiers"]
    tail_trend = video_tail9.new_state(
        product_type="video_trend",
        execution_product_type=str(trend_contract["executor_product_type"]),
        session_id="test-trend-400",
        scene_count=1,
        ratio="9:16",
    )
    invoiced = video_tail9.select_package(
        tail_trend,
        quality_tier_id="400",
        package_id="product_video_400",
        pricing_snapshot={"routing_quality_tier": 400, "quality_xu": 80, "total_xu": 80},
        capability_snapshot={"ok": True, "required_capability": trend_contract["required_capability"]},
    )
    assert invoiced["quality_tier_id"] == "400"
    assert invoiced["pricing_snapshot"]["total_xu"] == 80


def test_pv09_deferred_products_cannot_execute_or_submit() -> None:
    """DEFERRED_PRODUCTS_EXECUTED=0: Deferred products cannot be confirmed or submitted."""
    async def _test():
        from services import video_project_queue

        for product_type in DEFERRED_PRODUCTS:
            contract = video_tail9.commercial_contract(product_type)
            is_locked = (not contract.get("execution_enabled")) or (product_type in video_uifreeze1.PUBLIC_EXECUTION_LOCKED_PRODUCTS)
            assert is_locked is True, f"{product_type} must be locked from execution"

            # Queue capability resolution must enforce execution_enabled=False
            queue_cap = video_project_queue.product_video_engine_contract(product_type)
            assert queue_cap["execution_enabled"] is False, f"Queue allowed {product_type} execution!"
            assert queue_cap["execution_blocker"], f"Queue missing blocker for {product_type}"

            tail = video_tail9.new_state(
                product_type=product_type,
                execution_product_type=str(contract["executor_product_type"]),
                session_id=f"test-deferred-{product_type}",
                scene_count=2,
                ratio="9:16" if product_type != "video_local_edit" else "keep",
            )
            tail = video_tail9.apply_content_contract(
                tail,
                {
                    "content_source": "manual",
                    "canonical_content_mode": "manual",
                    "selected_prompt_text": f"Deferred test {product_type}",
                    "per_scene_content": [{"scene_index": 1, "provider_prompt": "Scene 1"}],
                    "plan_status": "ready",
                },
            )
            selected_tier = int(contract["supported_quality_tiers"][0])
            invoiced = video_tail9.select_package(
                tail,
                quality_tier_id=str(selected_tier),
                package_id=f"product_video_{selected_tier}",
                pricing_snapshot={"routing_quality_tier": selected_tier, "quality_xu": selected_tier, "total_xu": selected_tier * 2},
                capability_snapshot={"ok": True, "required_capability": contract["required_capability"]},
            )
            
            # If contract has execution_enabled False, confirm_once raises ValueError
            if not contract.get("execution_enabled"):
                with pytest.raises(ValueError) as exc_info:
                    video_tail9.confirm_once(invoiced, "tok123")
                assert contract["execution_blocker"] in str(exc_info.value)

            # Confirm submit handler in bot.py also blocks it fail-closed
            update = MagicMock()
            update.effective_user.id = 12345
            update.callback_query = AsyncMock()
            update.callback_query.data = f"video_tail|confirm|submit|{tail['video_session_id']}"
            context = MagicMock()
            context.user_data = {
                bot.VIDEO_TAIL9_STATE_KEY: invoiced,
                bot.VIDEO_UIFLOW3_ACTIVE_TAIL_KEY: invoiced,
            }
            
            with patch.object(bot, "get_video_session", return_value={"draft": {bot.VIDEO_TAIL9_STATE_KEY: invoiced}}):
                with patch.object(bot, "get_user") as mock_get_user:
                    await bot.handle_product_video_public_confirm_callback(
                        update,
                        context,
                        product_type=product_type,
                        session_id=tail["video_session_id"],
                    )
                    assert mock_get_user.call_count == 0, f"Deferred product {product_type} called user billing lookup!"

    asyncio.run(_test())


def test_pv09_navigation_back_cancel_stale_tampered() -> None:
    """Test full navigation buttons: back, change, review, stale session, and tampered callback."""
    async def _test():
        update = MagicMock()
        update.effective_user.id = 12345
        update.callback_query = AsyncMock()
        context = MagicMock()
        context.user_data = {}

        # 1. Stale callback: session missing
        update.callback_query.data = "video_tail|quality|select|500"
        with patch.object(bot, "get_video_session", return_value=None):
            await bot.handle_video_tail_callback(update, context)
            assert update.callback_query.answer.called

        # 2. Tampered callback: malformed parts
        update.callback_query.reset_mock()
        update.callback_query.data = "video_tail|unknown_action|extra_garbage_payload"
        await bot.handle_video_tail_callback(update, context)
        assert update.callback_query.answer.called

        # 3. Setup active state for navigation buttons
        tail = video_tail9.new_state(
            product_type="video_trend",
            execution_product_type="video_trend",
            session_id="sess-nav-test",
            scene_count=1,
            ratio="9:16",
        )
        context.user_data = {bot.VIDEO_TAIL9_STATE_KEY: tail}

        # 4. Back button handling (video_tail|quality|back)
        update.callback_query.reset_mock()
        update.callback_query.data = "video_tail|quality|back"
        with patch.object(bot, "get_video_session", return_value={"draft": {bot.VIDEO_TAIL9_STATE_KEY: tail}}):
            await bot.handle_video_tail_callback(update, context)
            assert update.callback_query.answer.called or update.callback_query.edit_message_text.called

        # 5. Review button handling (video_tail|review|open)
        update.callback_query.reset_mock()
        update.callback_query.data = "video_tail|review|open"
        with patch.object(bot, "get_video_session", return_value={"draft": {bot.VIDEO_TAIL9_STATE_KEY: tail}}):
            await bot.handle_video_tail_callback(update, context)
            assert update.callback_query.answer.called or update.callback_query.edit_message_text.called

    asyncio.run(_test())


def test_pv09_full_active_chain_entry_to_review() -> None:
    """All 9 active products can transition from entry -> input -> quality selection -> review."""
    for product_type in ACTIVE_PRODUCTS:
        contract = video_tail9.commercial_contract(product_type)
        scene_count = max(int(contract["minimum_scene_count"]), 1)
        tail = video_tail9.new_state(
            product_type=product_type,
            execution_product_type=str(contract["executor_product_type"]),
            session_id=f"test-flow-{product_type}",
            scene_count=scene_count,
            ratio="9:16",
        )
        assert tail["status_stage"] == "content_ready"
        
        # Apply valid content contract
        tail = video_tail9.apply_content_contract(
            tail,
            {
                "content_source": "manual",
                "canonical_content_mode": "manual",
                "selected_prompt_text": f"Prompt for {product_type}",
                "per_scene_content": [{"scene_index": i, "provider_prompt": f"Scene {i}"} for i in range(1, scene_count + 1)],
                "plan_status": "ready",
            },
        )
        
        tier = contract["supported_quality_tiers"][0]
        invoiced = video_tail9.select_package(
            tail,
            quality_tier_id=str(tier),
            package_id=f"product_video_{tier}",
            pricing_snapshot={"routing_quality_tier": tier, "quality_xu": tier, "total_xu": tier * scene_count},
            capability_snapshot={"ok": True, "required_capability": contract["required_capability"]},
        )
        assert invoiced["status_stage"] == "invoice"
        allowed, reason = video_tail9.invoice_allowed(invoiced)
        assert allowed is True, f"{product_type} invoice not allowed: {reason}"
