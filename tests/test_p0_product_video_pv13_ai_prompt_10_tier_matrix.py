# -*- coding: utf-8 -*-
"""Deterministic unit test suite for P0.PRODUCT_VIDEO.PV13.AI.PROMPT.10.TIER.LIVE.MATRIX.PREFLIGHT.

Verifies:
1. Canonical 10-tier catalog completeness and pricing for product video_ai_prompt.
2. Protection of Tier 400 (visible and 80 Xu).
3. Exact adapter, router, finalizer, and delivery symbol contracts.
4. Input contract truth (valid prompt, empty prompt fail-closed, ratio selection, tampered tier rejection).
5. Per-tier admission preflight across all 10 canonical tiers in isolation.
6. Probation lock truth (probation-blocked admission with zero provider calls and zero mutations).
7. Zero provider submission and zero wallet mutation invariants.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from services import video_ai_real_pricing
from services import video_final_output
from services import video_project_queue as queue
from services import video_provider_router as router
from services import video_tail9
from services import video_uifreeze1


CANONICAL_10_TIERS = (400, 500, 600, 200, 300, 700, 800, 1000, 1200, 1500)

EXPECTED_TIER_PRICES = {
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

EXPECTED_TIER_SECONDS = {
    400: 8,
    500: 5,
    600: 5,
    200: 5,
    300: 5,
    700: 15,
    800: 10,
    1000: 6,
    1200: 8,
    1500: 10,
}

PUBLIC_RATIOS = ("9:16", "16:9", "1:1", "4:5")
INTERNAL_COMPAT_TOKEN = "keep"


def _pricing_snapshot(tier_id: int, scene_count: int = 1) -> dict[str, Any]:
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


def _create_probation_job(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    project_id: int,
    user_id: int = 7126457028,
    status: str = "queued",
    probation_result: str = "pending",
    probation_started_at: str = "",
    probation_lock_expires_at: str = "",
    probation_delivery_expires_at: str = "",
    completed_at: str = "",
    delivery_state: str = "pending",
    final_delivered: bool = False,
    delivery_succeeded: bool = False,
    admission_mode: str = queue.PRODUCT_VIDEO_PROBATION_ADMISSION_MODE,
) -> None:
    shared = {
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "product_type": "video_ai_prompt",
        "engine_adapter": "text_to_video",
        "orchestration_mode": "single_scene",
        "scene_count": 1,
        "duration_seconds": 8,
    }
    project = queue.create_video_project(
        conn,
        user_id=user_id,
        profile_id="video_ai_prompt",
        topic=f"PV13 project {project_id}",
        ratio="9:16",
        asset_pack=shared,
    )
    orig_pid = int(project["project_id"])
    conn.execute("UPDATE video_projects SET project_id=? WHERE project_id=?", (project_id, orig_pid))
    queue.update_video_project(
        conn,
        project_id,
        status="completed" if status == "completed" else "processing",
        invoice_json={
            **shared,
            "package_xu": 80,
            "user_visible_price_xu": 80,
            "persisted_quoted_price_xu": 80,
            "customer_charge_planned_xu": 80,
            "wallet_charge_amount_xu": 80,
        },
        scene_count=1,
        total_xu_estimated=80,
        is_confirmed=1,
    )
    job = queue.enqueue_video_render_job(conn, project_id=project_id, user_id=user_id, max_attempts=3)
    orig_jid = int(job["id"])
    conn.execute("UPDATE video_jobs SET id=? WHERE id=?", (job_id, orig_jid))
    conn.execute("UPDATE video_projects SET job_id=? WHERE project_id=?", (job_id, project_id))

    payload = {
        **shared,
        "admission_mode": admission_mode,
        "provider": "shopaikey_video",
        "probation_candidate_key": "shopaikey_video",
        "probation_job_id": job_id,
        "probation_result": probation_result,
        "probation_started_at": probation_started_at,
        "probation_lock_expires_at": probation_lock_expires_at,
        "probation_delivery_expires_at": probation_delivery_expires_at,
        "delivery_state": delivery_state,
        "final_delivered": final_delivered,
        "delivery_succeeded": delivery_succeeded,
    }
    conn.execute(
        """UPDATE video_jobs
           SET status=?, priority=10, progress_percent=70, progress_message='provider_in_progress',
               result_json=?, completed_at=?
           WHERE id=?""",
        (status, json.dumps(payload), completed_at or None, job_id),
    )
    conn.commit()


# ==============================================================================
# 1. TEN-TIER CATALOG MATRIX & TIER 400 PROTECTION
# ==============================================================================

def test_ten_tier_catalog_completeness_and_uniqueness() -> None:
    """Audit that all 10 canonical tiers exist without omission or duplication."""
    catalog = video_ai_real_pricing.public_quality_catalog()
    catalog_tier_ids = tuple(item["tier_id"] for item in catalog)
    assert catalog_tier_ids == CANONICAL_10_TIERS, (
        f"Catalog tier order mismatch: expected {CANONICAL_10_TIERS}, got {catalog_tier_ids}"
    )
    assert len(set(catalog_tier_ids)) == 10, "Duplicate tier IDs detected in catalog"

    price_route_map = video_ai_real_pricing.product_video_price_route_map()
    route_tier_ids = tuple(
        item["tier_id"] for item in price_route_map["tiers_sorted_by_customer_price"]
    )
    assert route_tier_ids == CANONICAL_10_TIERS, (
        f"Price-route map tier order mismatch: expected {CANONICAL_10_TIERS}, got {route_tier_ids}"
    )


def test_tier_400_visible_and_80_xu_protected() -> None:
    """Tier 400 must remain strictly visible with unit_xu == 80 and 8 seconds."""
    catalog = video_ai_real_pricing.public_quality_catalog()
    tier_400 = next((row for row in catalog if row["tier_id"] == 400), None)
    assert tier_400 is not None, "Tier 400 must be visible in public catalog"
    assert tier_400["unit_xu"] == 80, f"Tier 400 unit_xu must be 80, got {tier_400['unit_xu']}"
    assert tier_400["seconds"] == 8, f"Tier 400 seconds must be 8, got {tier_400['seconds']}"

    two_scene_quote = video_ai_real_pricing.video_multiscene_price(80, scene_count=2)
    assert two_scene_quote["subtotal_xu"] == 160
    assert two_scene_quote["discount_percent"] == 10
    assert two_scene_quote["discount_xu"] == 16
    assert two_scene_quote["total_xu"] == 144


@pytest.mark.parametrize("tier_id", CANONICAL_10_TIERS)
def test_all_ten_tiers_prices_and_seconds_match_canonical_spec(tier_id: int) -> None:
    """Every tier in the canonical 10-tier matrix matches expected price and duration."""
    spec = video_uifreeze1.tier_spec(tier_id)
    assert spec["unit_xu"] == EXPECTED_TIER_PRICES[tier_id], (
        f"Tier {tier_id} unit_xu mismatch: expected {EXPECTED_TIER_PRICES[tier_id]}, got {spec['unit_xu']}"
    )
    assert spec["seconds"] == EXPECTED_TIER_SECONDS[tier_id], (
        f"Tier {tier_id} seconds mismatch: expected {EXPECTED_TIER_SECONDS[tier_id]}, got {spec['seconds']}"
    )
    assert "text_to_video" in spec["capabilities"], (
        f"Tier {tier_id} capabilities missing text_to_video: {spec['capabilities']}"
    )


def test_ten_tier_pricing_aggregate_truth() -> None:
    """Canonical one-scene total across 10 tiers is 5350 Xu; 2-scene aggregate is 9630 Xu.

    The 2-scene aggregate is calculated from source pricing (video_multiscene_price),
    not hardcoded prose.
    """
    assert sum(EXPECTED_TIER_PRICES.values()) == 5350

    two_scene_aggregate = sum(
        video_ai_real_pricing.video_multiscene_price(EXPECTED_TIER_PRICES[tier_id], scene_count=2)["total_xu"]
        for tier_id in CANONICAL_10_TIERS
    )
    assert two_scene_aggregate == 9630


# ==============================================================================
# 2. PRODUCT ADAPTER TRUTH
# ==============================================================================

def test_video_ai_prompt_adapter_symbols_truth() -> None:
    """Trace exact symbols for product video_ai_prompt."""
    # 1. Commercial adapter
    adapter = video_tail9.adapter_for("video_ai_prompt")
    assert adapter["canonical_product_type"] == "video_ai_prompt"
    assert adapter["executor_product_type"] == "video_ai_prompt"
    assert adapter["flow_owner"] == "scene3"
    assert adapter["engine_route"] == "video_ai_canonical"
    assert adapter["required_capability"] == "text_to_video"
    assert adapter["input_type"] == "text_prompt"
    assert adapter["pricing_mode"] == "canonical"
    assert adapter["public_enabled"] is True
    assert adapter["execution_enabled"] is True
    assert adapter["supported_quality_tiers"] == CANONICAL_10_TIERS

    # 2. Final output routing spec
    assert "video_ai_prompt" in video_final_output.REQUIRED_VIDEO_PRODUCT_TYPES
    route_spec = video_final_output.VIDEO_PRODUCT_ENGINE_ROUTES.get("video_ai_prompt")
    assert route_spec is not None, "video_ai_prompt missing from VIDEO_PRODUCT_ENGINE_ROUTES"
    assert route_spec["adapter"] == "text_to_video"
    assert route_spec["engine_family"] == "single_video"

    # 3. Router acceptance product type
    assert router.CANONICAL_ACCEPTANCE_PRODUCT_TYPE == "video_ai_prompt"


# ==============================================================================
# 3. INPUT CONTRACT TRUTH
# ==============================================================================

def test_input_contract_valid_prompt_passes() -> None:
    """Valid text prompt completes content contract and marks ready."""
    state = video_tail9.new_state(
        product_type="video_ai_prompt",
        execution_product_type="video_ai_prompt",
        session_id="pv13-valid-prompt-test",
        scene_count=1,
        ratio="9:16",
    )
    valid_contract = {
        "content_source": "manual",
        "selected_prompt_text": "Cinematic 8k hyperrealistic product video, golden hour lighting",
        "plan_status": "ready",
    }
    updated_state = video_tail9.apply_content_contract(state, valid_contract)
    assert updated_state["selected_prompt"] == "Cinematic 8k hyperrealistic product video, golden hour lighting"
    assert video_tail9.content_contract_ready(updated_state) is True


def test_input_contract_empty_prompt_fails_closed() -> None:
    """Empty or whitespace prompt must fail-closed (EMPTY_PROMPT_FAIL_CLOSED=YES)."""
    state = video_tail9.new_state(
        product_type="video_ai_prompt",
        execution_product_type="video_ai_prompt",
        session_id="pv13-empty-prompt-test",
        scene_count=1,
        ratio="9:16",
    )
    # 1. None/empty contract
    empty_contract = {
        "content_source": "manual",
        "selected_prompt_text": "",
        "plan_status": "ready",
    }
    updated_state = video_tail9.apply_content_contract(state, empty_contract)
    assert not updated_state.get("selected_prompt")
    assert video_tail9.content_contract_ready(updated_state) is False

    # 2. Whitespace only contract
    ws_contract = {
        "content_source": "manual",
        "selected_prompt_text": "   \n\t  ",
        "plan_status": "ready",
    }
    updated_state_ws = video_tail9.apply_content_contract(state, ws_contract)
    assert not updated_state_ws.get("selected_prompt")
    assert video_tail9.content_contract_ready(updated_state_ws) is False


def test_input_contract_public_ratios_pass() -> None:
    """All 4 public customer ratios (9:16, 16:9, 1:1, 4:5) pass package compatibility."""
    for valid_ratio in PUBLIC_RATIOS:
        compat = video_tail9.package_compatibility(
            "video_ai_prompt",
            scene_count=1,
            ratio=valid_ratio,
            quality_tier_id=400,
        )
        assert compat["ok"] is True, f"Public ratio {valid_ratio} failed: {compat}"


def test_input_contract_internal_compat_token_keep() -> None:
    """Internal compatibility token 'keep' is accepted by engine layer, but is NOT in PUBLIC_RATIOS."""
    assert INTERNAL_COMPAT_TOKEN not in PUBLIC_RATIOS, "keep must not be exposed as a public user ratio"
    compat = video_tail9.package_compatibility(
        "video_ai_prompt",
        scene_count=1,
        ratio=INTERNAL_COMPAT_TOKEN,
        quality_tier_id=400,
    )
    assert compat["ok"] is True, f"Internal compat token {INTERNAL_COMPAT_TOKEN} failed: {compat}"


def test_input_contract_invalid_ratios_fail_closed() -> None:
    """Non-supported ratios fail closed with ratio_not_supported."""
    for invalid_ratio in ("21:9", "invalid", "1080x1920", ""):
        compat_inv = video_tail9.package_compatibility(
            "video_ai_prompt",
            scene_count=1,
            ratio=invalid_ratio,
            quality_tier_id=400,
        )
        assert compat_inv["ok"] is False
        assert "ratio_not_supported" in compat_inv["blockers"]


def test_input_contract_tampered_and_unsupported_tier_fail_closed() -> None:
    """Tampered or non-existent tier IDs must fail closed with zero fake success."""
    state = video_tail9.new_state(
        product_type="video_ai_prompt",
        execution_product_type="video_ai_prompt",
        session_id="pv13-tampered-tier-test",
        scene_count=1,
        ratio="9:16",
    )
    state = video_tail9.apply_content_contract(
        state,
        {
            "content_source": "manual",
            "selected_prompt_text": "A majestic eagle soaring over foggy mountain peaks",
            "plan_status": "ready",
        },
    )

    tampered_tiers = (9999, 999, 0, -1, 100, 450)
    for bad_tier in tampered_tiers:
        compat = video_tail9.package_compatibility(
            "video_ai_prompt",
            scene_count=1,
            ratio="9:16",
            quality_tier_id=bad_tier,
        )
        assert compat["ok"] is False
        expected_blocker = "quality_tier_missing" if bad_tier == 0 else "quality_tier_not_supported"
        assert expected_blocker in compat["blockers"]

        with pytest.raises(ValueError) as excinfo:
            video_tail9.select_package(
                state,
                quality_tier_id=str(bad_tier),
                package_id=f"package_{bad_tier}",
                pricing_snapshot={"price_xu": 100},
                capability_snapshot={"ok": True},
            )
        assert expected_blocker in str(excinfo.value)


# ==============================================================================
# 4. PER-TIER ADMISSION PREFLIGHT IN ISOLATION (ALL 10 TIERS)
# ==============================================================================

@pytest.mark.parametrize("tier_id", CANONICAL_10_TIERS)
def test_all_ten_tiers_admission_preflight_in_isolation(tier_id: int) -> None:
    """Run the complete end-to-end admission and preflight path for each of the 10 tiers."""
    state = video_tail9.new_state(
        product_type="video_ai_prompt",
        execution_product_type="video_ai_prompt",
        session_id=f"pv13-preflight-tier-{tier_id}",
        scene_count=1,
        ratio="9:16",
    )

    state = video_tail9.apply_content_contract(
        state,
        {
            "content_source": "manual",
            "selected_prompt_text": f"High production cinematic video for tier {tier_id}, crisp 4k detail",
            "plan_status": "ready",
        },
    )
    assert video_tail9.content_contract_ready(state) is True

    pricing = _pricing_snapshot(tier_id, scene_count=1)
    assert pricing["quality_xu"] == EXPECTED_TIER_PRICES[tier_id]

    invoiced = video_tail9.select_package(
        state,
        quality_tier_id=str(tier_id),
        package_id=f"product_video_{tier_id}",
        pricing_snapshot=pricing,
        capability_snapshot={"ok": True, "required_capability": "text_to_video"},
    )
    assert invoiced["status_stage"] == "invoice"
    allowed, reason = video_tail9.invoice_allowed(invoiced)
    assert allowed is True
    assert reason == "ok"

    preflight = video_tail9.evaluate_submit_preflight(
        invoiced,
        available_xu=50000,
        provider_ready=True,
        worker_ready=True,
        is_admin_or_owner=False,
    )
    assert preflight["allowed"] is True
    assert preflight["blocker_code"] == ""
    assert preflight["required_xu"] == EXPECTED_TIER_PRICES[tier_id]

    confirmed, created = video_tail9.confirm_once(invoiced, f"confirm-token-{tier_id}")
    assert created is True
    assert confirmed["final_confirmed"] is True

    compat = video_tail9.package_compatibility(
        "video_ai_prompt",
        scene_count=1,
        ratio="9:16",
        quality_tier_id=tier_id,
    )
    assert compat["side_effects"]["provider_calls"] == 0
    assert compat["side_effects"]["wallet_mutations"] == 0
    assert compat["side_effects"]["job"] == 0


# ==============================================================================
# 5. PROBATION LOCK TRUTH (PROBATION-BLOCKED ADMISSION)
# ==============================================================================

def test_probation_lock_blocked_admission_when_held_by_other_job(tmp_path: Path) -> None:
    """When probation lock is owned by another job, new admission is strictly blocked with 0 provider calls."""
    db_path = tmp_path / "pv13_probation_test.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)

    now_vn = datetime.now(timezone(timedelta(hours=7)))
    started_at = (now_vn - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    expires_at = (now_vn + timedelta(minutes=25)).strftime("%Y-%m-%d %H:%M:%S")

    _create_probation_job(
        conn,
        job_id=28,
        project_id=32,
        user_id=7126457028,
        status="queued",
        probation_result="pending",
        probation_started_at=started_at,
        probation_lock_expires_at=expires_at,
    )

    # Initial isolated SQLite table counts
    projects_before = conn.execute("SELECT COUNT(*) FROM video_projects").fetchone()[0]
    jobs_before = conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0]
    outbox_before = conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox").fetchone()[0]

    lock_state = queue.product_video_probation_lock_state(
        conn,
        provider_key="shopaikey_video",
        current_job_id=999,
        current_project_id=100,
        now=now_vn,
    )
    assert lock_state["probation_active"] is True
    assert lock_state["probation_lock_clear"] is False
    assert lock_state["probation_lock_clear_for_current_job"] is False
    assert lock_state["probation_lock_owner_job"] == 28
    assert lock_state["probation_lock_owner_project"] == 32
    assert lock_state["probation_lock_owned_by_other_job"] is True
    assert lock_state["probation_lock_reject_reason"] == "probation_lock_owned_by_other_job"

    # Verify zero side-effect mutations occurred
    projects_after = conn.execute("SELECT COUNT(*) FROM video_projects").fetchone()[0]
    jobs_after = conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0]
    outbox_after = conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox").fetchone()[0]

    VIDEO_PROJECT_DELTA = projects_after - projects_before
    VIDEO_JOB_DELTA = jobs_after - jobs_before
    OUTBOX_DELTA = outbox_after - outbox_before

    assert VIDEO_PROJECT_DELTA == 0
    assert VIDEO_JOB_DELTA == 0
    assert OUTBOX_DELTA == 0

    conn.close()


# ==============================================================================
# 6. ZERO MUTATION / ZERO PROVIDER SUBMISSION INVARIANTS (SPIES & DELTAS)
# ==============================================================================

def test_zero_mutation_and_zero_provider_calls_with_canonical_spies(tmp_path: Path) -> None:
    """Enforce runtime safety invariants with real spies/mocks around canonical seams and SQLite table deltas.

    Verifies:
    - PROVIDER_SUBMIT_CALLS = 0 (run_provider_generation)
    - JOB_CREATION_DELTA = 0 (video_jobs table delta)
    - OUTBOX_DELTA = 0 (video_dispatch_outbox table delta)
    - WALLET_MUTATION_CALLS = 0 (product_video_delivery_charge_decision + deduct_dynamic_credit)
    """
    import bot

    db_path = tmp_path / "pv13_zero_mutation_spies.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)

    now_vn = datetime.now(timezone(timedelta(hours=7)))
    started_at = (now_vn - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    expires_at = (now_vn + timedelta(minutes=25)).strftime("%Y-%m-%d %H:%M:%S")

    _create_probation_job(
        conn,
        job_id=28,
        project_id=32,
        user_id=7126457028,
        status="queued",
        probation_result="pending",
        probation_started_at=started_at,
        probation_lock_expires_at=expires_at,
    )

    projects_before = conn.execute("SELECT COUNT(*) FROM video_projects").fetchone()[0]
    jobs_before = conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0]
    outbox_before = conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox").fetchone()[0]

    with patch("services.video_provider_router.run_provider_generation") as spy_provider_submit, \
         patch("services.video_project_queue.enqueue_video_render_job") as spy_job_create, \
         patch("services.video_project_queue._insert_product_video_dispatch_outbox_record") as spy_outbox_create, \
         patch("services.video_project_queue.product_video_delivery_charge_decision") as spy_delivery_charge, \
         patch("bot.deduct_dynamic_credit") as spy_wallet_deduct:

        # 1. Run probation lock precheck
        lock_state = queue.product_video_probation_lock_state(
            conn,
            provider_key="shopaikey_video",
            current_job_id=999,
            current_project_id=100,
            now=now_vn,
        )
        assert lock_state["probation_active"] is True
        assert lock_state["probation_lock_clear"] is False
        assert lock_state["probation_lock_reject_reason"] == "probation_lock_owned_by_other_job"

        # 2. Run package compatibility checks across all 10 tiers in preflight
        for tier_id in CANONICAL_10_TIERS:
            compat = video_tail9.package_compatibility(
                "video_ai_prompt",
                scene_count=1,
                ratio="9:16",
                quality_tier_id=tier_id,
            )
            assert compat["ok"] is True
            assert compat["side_effects"]["provider_calls"] == 0
            assert compat["side_effects"]["wallet_mutations"] == 0
            assert compat["side_effects"]["job"] == 0

        # Assert spies confirm ZERO calls made to canonical seams
        PROVIDER_SUBMIT_CALLS = spy_provider_submit.call_count
        WALLET_MUTATION_CALLS = spy_delivery_charge.call_count + spy_wallet_deduct.call_count

        assert PROVIDER_SUBMIT_CALLS == 0
        assert spy_job_create.call_count == 0
        assert spy_outbox_create.call_count == 0
        assert WALLET_MUTATION_CALLS == 0

    # Assert isolated SQLite table deltas remain strictly 0
    projects_after = conn.execute("SELECT COUNT(*) FROM video_projects").fetchone()[0]
    jobs_after = conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0]
    outbox_after = conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox").fetchone()[0]

    VIDEO_PROJECT_DELTA = projects_after - projects_before
    VIDEO_JOB_DELTA = jobs_after - jobs_before
    OUTBOX_DELTA = outbox_after - outbox_before

    assert VIDEO_PROJECT_DELTA == 0
    assert VIDEO_JOB_DELTA == 0
    assert OUTBOX_DELTA == 0

    conn.close()
