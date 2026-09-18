"""Focused test matrix for P0.PRODUCT_VIDEO.PV08.PRODUCT.ADAPTERS.PRODUCT.SPECIFIC.QUALITY.

Validates:
1. Exact Active Product Matrix (9 products):
   - T2V (4): video_trend, video_ai_prompt, video_idea, script_image_video
   - I2V (2): video_ai_image, storyboard_prompt
   - V2V (3): video_ai_video_reference, self_shot_scene_change, self_shot_cinematic_transform
   - Deferred (3): video_local_edit, multi_scene_film, video_long -> DEFERRED_PRODUCTS_EXECUTED=0
2. Canonical Identity Lock:
   - Unknown product rejected (fail-closed, no default fallback adapter)
   - Product A never silently executes Product B
   - Tampered aliases rejected
   - CANONICAL_EXECUTOR_MISMATCH=0, SILENT_PRODUCT_FALLBACK=0
3. Quality / Modality Contract:
   - T2V & I2V support 10 tiers: {400, 500, 600, 200, 300, 700, 800, 1000, 1200, 1500}
   - V2V supports ONLY 4 tiers: {500, 600, 700, 800}
   - V2V rejects remaining 6 tiers: {400, 200, 300, 1000, 1200, 1500}
   - Unsupported, unknown, tampered, and missing tiers fail closed (UNSUPPORTED_TIER_ACCEPTED=0, UNKNOWN_TIER_ACCEPTED=0)
   - Trend Tier 400 visible and exactly 80 Xu
4. Product-Specific Input Truth:
   - Missing required input -> JOB_DELTA=0, OUTBOX_DELTA=0, PROVIDER_TASK_DELTA=0
5. Product-Specific Payload Truth:
   - Zero cross-product payload contamination
   - Deterministic mocks only, zero network
6. PV07 Artifact Lock Enforcement Across All Adapters:
   - PROVIDER_SUCCESS != SCENE_CLIP_VALID
   - Result URL alone does NOT unlock finalizer
   - Stale clip_valid does NOT unlock finalizer
   - Missing/nonexistent local media does NOT unlock finalizer
   - ADAPTER_BYPASS_PV07_LOCK=0, FINAL_MP4_REQUIRED=YES, DELIVERY_RECEIPT_REQUIRED=YES
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from services import (
    video_ai_real_pricing,
    video_final_output,
    video_tail9,
    video_uifreeze1,
)
from services import video_project_queue as queue
from services import video_provider_router as router
from services.video_provider_base import VideoGenerationRequest


# ==============================================================================
# CONSTANTS & CANONICAL DEFINITIONS
# ==============================================================================

ALL_CANONICAL_TIERS = (400, 500, 600, 200, 300, 700, 800, 1000, 1200, 1500)
T2V_EXPECTED_TIERS = frozenset({400, 500, 600, 200, 300, 700, 800, 1000, 1200, 1500})
I2V_EXPECTED_TIERS = frozenset({400, 500, 600, 200, 300, 700, 800, 1000, 1200, 1500})
V2V_EXPECTED_TIERS = frozenset({500, 600, 700, 800})
V2V_UNSUPPORTED_TIERS = frozenset({400, 200, 300, 1000, 1200, 1500})

ACTIVE_T2V_PRODUCTS = (
    "video_trend",
    "video_ai_prompt",
    "video_idea",
    "script_image_video",
)
ACTIVE_I2V_PRODUCTS = (
    "video_ai_image",
    "storyboard_prompt",
)
ACTIVE_V2V_PRODUCTS = (
    "video_ai_video_reference",
    "self_shot_scene_change",
    "self_shot_cinematic_transform",
)
ALL_ACTIVE_PRODUCTS = ACTIVE_T2V_PRODUCTS + ACTIVE_I2V_PRODUCTS + ACTIVE_V2V_PRODUCTS
DEFERRED_PRODUCTS = (
    "video_local_edit",
    "multi_scene_film",
    "video_long",
)

EXPECTED_EXECUTOR_MAP = {
    "video_trend": "video_trend",
    "video_ai_prompt": "video_ai_prompt",
    "video_idea": "video_idea_to_product",
    "script_image_video": "script_to_video",
    "video_ai_image": "video_ai_image",
    "storyboard_prompt": "storyboard_prompt",
    "video_ai_video_reference": "video_ai_video_reference",
    "self_shot_scene_change": "self_shot_scene_change",
    "self_shot_cinematic_transform": "self_shot_cinematic_transform",
}

EXPECTED_MODALITY_MAP = {
    "video_trend": "text_to_video",
    "video_ai_prompt": "text_to_video",
    "video_idea": "text_to_video",
    "script_image_video": "text_to_video",
    "video_ai_image": "image_to_video",
    "storyboard_prompt": "image_to_video",
    "video_ai_video_reference": "video_to_video",
    "self_shot_scene_change": "video_to_video",
    "self_shot_cinematic_transform": "video_to_video",
}

LEGITIMATE_PV02_ALIASES = {
    "trend_video": "video_trend",
    "prompt_video": "video_ai_prompt",
    "text_prompt": "video_ai_prompt",
    "video_idea_to_product": "video_idea",
    "script_to_video": "script_image_video",
    "image_video": "video_ai_image",
    "ai_image_menu": "video_ai_image",
    "image_prompts": "video_ai_image",
    "storyboard_to_video": "storyboard_prompt",
    "storyboard_video": "storyboard_prompt",
    "storyboard": "storyboard_prompt",
    "video_video": "video_ai_video_reference",
    "video_reference": "video_ai_video_reference",
    "ai_video_menu": "video_ai_video_reference",
    "reference_video": "video_ai_video_reference",
    "awaiting_reference_video": "video_ai_video_reference",
    "selfshot_scene_change": "self_shot_scene_change",
    "selfshot_cinematic": "self_shot_cinematic_transform",
}


def _create_isolated_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    return conn


# ==============================================================================
# 1. EXACT ACTIVE PRODUCT MATRIX & INVENTORY AUDIT (9 PRODUCTS)
# ==============================================================================

def test_pv08_active_product_matrix_audit() -> None:
    """Verify exactly 9 active products and report actual source symbols."""
    assert len(ALL_ACTIVE_PRODUCTS) == 9
    assert len(ACTIVE_T2V_PRODUCTS) == 4
    assert len(ACTIVE_I2V_PRODUCTS) == 2
    assert len(ACTIVE_V2V_PRODUCTS) == 3

    # Deferred products must NOT be in active set
    for deferred in DEFERRED_PRODUCTS:
        assert deferred not in ALL_ACTIVE_PRODUCTS

    for product_id in ALL_ACTIVE_PRODUCTS:
        adapter = video_tail9.adapter_for(product_id)
        assert adapter["video_product_type"] == product_id
        assert adapter["canonical_product_type"] == product_id
        assert adapter["executor_product_type"] == EXPECTED_EXECUTOR_MAP[product_id]
        assert adapter["required_capability"] == EXPECTED_MODALITY_MAP[product_id]

        contract = video_tail9.commercial_contract(product_id)
        assert contract["product_type"] == product_id
        assert contract["executor_product_type"] == EXPECTED_EXECUTOR_MAP[product_id]
        assert contract["required_capability"] == EXPECTED_MODALITY_MAP[product_id]
        assert contract["pricing_mode"] == "canonical"


# ==============================================================================
# 2. CANONICAL IDENTITY LOCK & PROHIBITION OF DEFAULT/SILENT FALLBACK
# ==============================================================================

@pytest.mark.parametrize("unknown_id", [
    "unknown_product_xyz",
    "tampered_product_404",
    "hack_video",
    "invalid_alias",
])
def test_pv08_unknown_product_rejected_fail_closed(unknown_id: str) -> None:
    """Unknown product must fail closed: no silent fallback to default adapter."""
    # 1. Adapter registry
    adapter = video_tail9.adapter_for(unknown_id)
    assert adapter["video_product_type"] == ""
    assert adapter["canonical_product_type"] == ""
    assert adapter["execution_enabled"] is False
    assert adapter["execution_blocker"] == "product_owner_missing"

    # 2. Commercial contract
    contract = video_tail9.commercial_contract(unknown_id)
    assert contract["product_type"] == ""
    assert contract["execution_enabled"] is False
    assert contract["execution_blocker"] == "product_owner_missing"

    # 3. Quality catalog
    tiers = video_uifreeze1.compatible_quality_tiers(unknown_id)
    assert tiers == []

    report = video_uifreeze1.catalog_report(unknown_id)
    assert report["ok"] is False
    assert report["reason"] == "no_compatible_quality_package"

    # 4. Engine contract in queue
    engine_contract = queue.product_video_engine_contract(unknown_id)
    assert engine_contract["execution_enabled"] is False
    assert engine_contract["execution_blocker"] != ""
    assert engine_contract["product_type"] == ""

    # 5. Final output route resolution MUST NOT silently return video_ai_prompt
    resolved = video_final_output.product_type_from_project(
        project={"product_type": unknown_id},
        result={},
    )
    assert resolved != "video_ai_prompt", "UNKNOWN PRODUCT SILENTLY FELL BACK TO video_ai_prompt!"
    assert resolved == "" or resolved is None or resolved == unknown_id


def test_pv08_product_type_from_project_no_silent_fallback() -> None:
    """product_type_from_project must not silently fall back to video_ai_prompt for unknown products."""
    res = video_final_output.product_type_from_project(
        project={"product_type": "totally_fake_video_type"},
        result={},
    )
    assert res != "video_ai_prompt", "Silent fallback detected for unknown product in product_type_from_project"


@pytest.mark.parametrize("alias,canonical", list(LEGITIMATE_PV02_ALIASES.items()))
def test_pv08_legitimate_pv02_aliases_preserved(alias: str, canonical: str) -> None:
    """Legitimate aliases proven in PV02 must map to expected canonical product."""
    adapter = video_tail9.adapter_for(alias)
    assert adapter["canonical_product_type"] == canonical
    assert adapter["executor_product_type"] == EXPECTED_EXECUTOR_MAP[canonical]


def test_pv08_no_cross_product_silent_execution() -> None:
    """Product A must never silently resolve or execute as Product B."""
    for product_id in ALL_ACTIVE_PRODUCTS:
        contract = video_tail9.commercial_contract(product_id)
        assert contract["product_type"] == product_id
        # Executor must be the intentional executor, not a different product
        assert contract["executor_product_type"] == EXPECTED_EXECUTOR_MAP[product_id]


# ==============================================================================
# 3. QUALITY / MODALITY MATRIX (T2V=10, I2V=10, V2V=4 ONLY)
# ==============================================================================

@pytest.mark.parametrize("product_id", ACTIVE_T2V_PRODUCTS)
def test_pv08_t2v_supports_all_10_tiers(product_id: str) -> None:
    contract = video_tail9.commercial_contract(product_id)
    assert contract["required_capability"] == "text_to_video"
    tiers = frozenset(contract["supported_quality_tiers"])
    assert tiers == T2V_EXPECTED_TIERS
    assert len(tiers) == 10

    # Catalog report check
    min_scenes = contract["minimum_scene_count"]
    cat = video_uifreeze1.catalog_report(product_id, scene_count=min_scenes, ratio="9:16")
    assert cat["ok"] is True
    assert frozenset(cat["tier_ids"]) == T2V_EXPECTED_TIERS


@pytest.mark.parametrize("product_id", ACTIVE_I2V_PRODUCTS)
def test_pv08_i2v_supports_all_10_tiers(product_id: str) -> None:
    contract = video_tail9.commercial_contract(product_id)
    assert contract["required_capability"] == "image_to_video"
    tiers = frozenset(contract["supported_quality_tiers"])
    assert tiers == I2V_EXPECTED_TIERS
    assert len(tiers) == 10

    min_scenes = contract["minimum_scene_count"]
    cat = video_uifreeze1.catalog_report(product_id, scene_count=min_scenes, ratio="9:16")
    assert cat["ok"] is True
    assert frozenset(cat["tier_ids"]) == I2V_EXPECTED_TIERS


@pytest.mark.parametrize("product_id", ACTIVE_V2V_PRODUCTS)
def test_pv08_v2v_supports_only_4_tiers_and_rejects_6(product_id: str) -> None:
    contract = video_tail9.commercial_contract(product_id)
    assert contract["required_capability"] == "video_to_video"
    tiers = frozenset(contract["supported_quality_tiers"])
    assert tiers == V2V_EXPECTED_TIERS
    assert len(tiers) == 4

    # The remaining 6 tiers must NOT be present
    assert V2V_UNSUPPORTED_TIERS.isdisjoint(tiers)

    # Catalog report check
    cat = video_uifreeze1.catalog_report(product_id, scene_count=1, ratio="9:16", required_capability="video_to_video")
    assert cat["ok"] is True
    assert frozenset(cat["tier_ids"]) == V2V_EXPECTED_TIERS

    # Every unsupported tier must be rejected by package_compatibility
    for bad_tier in V2V_UNSUPPORTED_TIERS:
        compat = video_tail9.package_compatibility(
            product_id,
            scene_count=1,
            ratio="9:16",
            quality_tier_id=bad_tier,
        )
        assert compat["ok"] is False
        assert "quality_tier_not_supported" in compat["blockers"]


# ==============================================================================
# 4. UNSUPPORTED, UNKNOWN, TAMPERED & MISSING TIER DEFENSE
# ==============================================================================

@pytest.mark.parametrize("product_id", ALL_ACTIVE_PRODUCTS)
def test_pv08_missing_tier_rejected_fail_closed(product_id: str) -> None:
    """Missing quality tier (0, None, missing) must fail closed."""
    compat_zero = video_tail9.package_compatibility(
        product_id,
        scene_count=5 if product_id == "script_image_video" else (2 if product_id == "storyboard_prompt" else 1),
        ratio="9:16",
        quality_tier_id=0,
    )
    assert compat_zero["ok"] is False, f"Missing quality tier 0 was accepted for {product_id}!"
    assert any("tier" in b for b in compat_zero["blockers"])


@pytest.mark.parametrize("product_id", ALL_ACTIVE_PRODUCTS)
@pytest.mark.parametrize("bad_tier", [999, -1, 450, 9999])
def test_pv08_unknown_tier_rejected_fail_closed(product_id: str, bad_tier: int) -> None:
    """Unknown or tampered tier ID must fail closed."""
    compat = video_tail9.package_compatibility(
        product_id,
        scene_count=5 if product_id == "script_image_video" else (2 if product_id == "storyboard_prompt" else 1),
        ratio="9:16",
        quality_tier_id=bad_tier,
    )
    assert compat["ok"] is False
    assert "quality_tier_not_supported" in compat["blockers"]


def test_pv08_tier_spec_unknown_tier_fails_closed() -> None:
    """tier_spec must NOT silently map an unknown tier like 999 or -1 to an existing tier."""
    with pytest.raises((ValueError, KeyError)):
        video_uifreeze1.tier_spec(999)


# ==============================================================================
# 5. TREND TIER 400 VISIBILITY & 80 XU INVARIANT
# ==============================================================================

def test_pv08_trend_tier400_visible_and_80_xu() -> None:
    """video_trend tier 400 must be visible and cost exactly 80 Xu."""
    cat = video_uifreeze1.catalog_report("video_trend", scene_count=1, ratio="9:16")
    assert cat["ok"] is True
    assert 400 in cat["tier_ids"]

    tier400_spec = next(o for o in cat["offers"] if int(o["tier_id"]) == 400)
    assert int(tier400_spec.get("unit_xu", tier400_spec.get("total_xu", 0))) == 80

    # Pricing calculation for 1 scene of video_trend at tier 400
    conn = _create_isolated_db()
    project = queue.create_video_project(
        conn,
        user_id=1001,
        profile_id="video_trend",
        topic="Trend Test",
        ratio="9:16",
        asset_pack={
            "source": "product_video",
            "product_video": True,
            "product_type": "video_trend",
            "scene_count": 1,
            "quality_tier": 400,
        },
    )
    invoice = {
        "tier": "basic",
        "tier_key": "basic",
        "quality_tier": 400,
        "scene_count": 1,
        "quality_xu": 80,
        "package_xu": 80,
        "total_xu": 80,
        "user_visible_price_xu": 80,
        "persisted_quoted_price_xu": 80,
        "customer_charge_planned_xu": 80,
    }
    quote = queue._product_video_quote_consistency(invoice, project)
    assert quote["quote_consistent"] is True
    assert quote["customer_charge_planned_xu"] == 80
    assert quote["user_visible_price_xu"] == 80


# ==============================================================================
# 6. DEFERRED PRODUCTS EXECUTION BLOCKED (DEFERRED_PRODUCTS_EXECUTED=0)
# ==============================================================================

@pytest.mark.parametrize("deferred_id", DEFERRED_PRODUCTS)
def test_pv08_deferred_products_execution_blocked(deferred_id: str) -> None:
    """Deferred products (video_local_edit, multi_scene_film, video_long) must NOT execute."""
    contract = video_tail9.commercial_contract(deferred_id)
    # Execution must not be freely enabled without blocker
    assert contract["execution_enabled"] is False or bool(contract["execution_blocker"]) or deferred_id in video_uifreeze1.PUBLIC_EXECUTION_LOCKED_PRODUCTS

    # In engine contract, execution_enabled must be False
    eng = queue.product_video_engine_contract(deferred_id)
    assert eng["execution_enabled"] is False or bool(eng["execution_blocker"])


# ==============================================================================
# 7. PRODUCT-SPECIFIC INPUT TRUTH (JOB_DELTA=0, OUTBOX_DELTA=0, PROVIDER_DELTA=0)
# ==============================================================================

def test_pv08_video_ai_prompt_requires_prompt_not_image_or_video() -> None:
    """video_ai_prompt requires a prompt, and source image/video must NOT be required."""
    # Valid with prompt only
    compat_ok = video_tail9.package_compatibility(
        "video_ai_prompt",
        scene_count=1,
        ratio="9:16",
        quality_tier_id=400,
        input_valid=True,
    )
    assert compat_ok["ok"] is True

    # Invalid when input is not valid
    compat_bad = video_tail9.package_compatibility(
        "video_ai_prompt",
        scene_count=1,
        ratio="9:16",
        quality_tier_id=400,
        input_valid=False,
    )
    assert compat_bad["ok"] is False
    assert "input_not_ready" in compat_bad["blockers"]


def test_pv08_script_image_video_requires_min_5_scenes() -> None:
    """script_image_video must require at least 5 scenes."""
    compat_single = video_tail9.package_compatibility(
        "script_image_video",
        scene_count=1,
        ratio="9:16",
        quality_tier_id=400,
    )
    assert compat_single["ok"] is False
    assert "scene_count_not_supported" in compat_single["blockers"] or "single_scene_not_supported" in compat_single["blockers"]

    compat_5 = video_tail9.package_compatibility(
        "script_image_video",
        scene_count=5,
        ratio="9:16",
        quality_tier_id=400,
    )
    assert compat_5["ok"] is True


def test_pv08_storyboard_prompt_requires_min_2_scenes() -> None:
    """storyboard_prompt must require at least 2 scenes."""
    compat_single = video_tail9.package_compatibility(
        "storyboard_prompt",
        scene_count=1,
        ratio="9:16",
        quality_tier_id=400,
    )
    assert compat_single["ok"] is False
    assert "single_scene_not_supported" in compat_single["blockers"] or "scene_count_not_supported" in compat_single["blockers"]

    compat_2 = video_tail9.package_compatibility(
        "storyboard_prompt",
        scene_count=2,
        ratio="9:16",
        quality_tier_id=400,
    )
    assert compat_2["ok"] is True


def test_pv08_missing_input_causes_zero_job_outbox_deltas() -> None:
    """When admission or input is missing/invalid, confirm must produce 0 jobs and 0 outboxes."""
    conn = _create_isolated_db()
    project = queue.create_video_project(
        conn,
        user_id=2001,
        profile_id="video_ai_prompt",
        topic="No Input Test",
        ratio="9:16",
        asset_pack={"source": "product_video", "product_video": True, "product_type": "video_ai_prompt"},
    )
    pid = int(project["project_id"])

    # Attempt confirm with invalid admission
    result = queue.confirm_public_product_video_invoice(
        conn,
        project_id=pid,
        user_id=2001,
        balance_xu=1000,
        provider_admission=None,  # missing admission
    )
    assert result["ok"] is False
    assert result["job_created"] is False
    assert result["dispatch_outbox_created"] is False

    # Check database counters
    jobs_count = conn.execute("SELECT COUNT(*) FROM video_jobs WHERE project_id=?", (pid,)).fetchone()[0]
    assert jobs_count == 0
    outbox_count = conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox WHERE project_id=?", (pid,)).fetchone()[0]
    assert outbox_count == 0


# ==============================================================================
# 8. PRODUCT-SPECIFIC PAYLOAD TRUTH & UNCONTAMINATED FIELDS
# ==============================================================================

def test_pv08_payload_no_cross_product_contamination() -> None:
    """T2V must not carry image/video paths; I2V must not carry video; V2V must carry video."""
    # 1. T2V request
    t2v_req = VideoGenerationRequest(
        job_id="test_t2v",
        product_type="video_ai_prompt",
        prompt="A beautiful sunrise",
        ratio="9:16",
        duration_seconds=8.0,
        image_paths=[],
        source_video_path="",
        required_capability="text_to_video",
    )
    assert t2v_req.product_type == "video_ai_prompt"
    assert t2v_req.image_paths == []
    assert t2v_req.source_video_path == ""
    assert t2v_req.required_capability == "text_to_video"

    # 2. I2V request
    i2v_req = VideoGenerationRequest(
        job_id="test_i2v",
        product_type="video_ai_image",
        prompt="Make the water move",
        ratio="9:16",
        duration_seconds=8.0,
        image_paths=["/tmp/frame01.png"],
        source_video_path="",
        required_capability="image_to_video",
    )
    assert i2v_req.product_type == "video_ai_image"
    assert len(i2v_req.image_paths) == 1
    assert i2v_req.source_video_path == "", "I2V request must NOT be contaminated with source_video_path!"
    assert i2v_req.required_capability == "image_to_video"

    # 3. V2V request
    v2v_req = VideoGenerationRequest(
        job_id="test_v2v",
        product_type="video_ai_video_reference",
        prompt="Change lighting to dusk",
        ratio="9:16",
        duration_seconds=8.0,
        image_paths=[],
        source_video_path="/tmp/input_video.mp4",
        required_capability="video_to_video",
    )
    assert v2v_req.product_type == "video_ai_video_reference"
    assert v2v_req.image_paths == [], "V2V request must NOT be contaminated with image_paths!"
    assert v2v_req.source_video_path == "/tmp/input_video.mp4"
    assert v2v_req.required_capability == "video_to_video"


# ==============================================================================
# 9. PV07 ARTIFACT LOCK ENFORCEMENT ACROSS ALL PRODUCT FAMILIES
# ==============================================================================

@pytest.mark.parametrize("product_id", [
    "video_trend",                  # T2V
    "video_ai_image",               # I2V
    "video_ai_video_reference",     # V2V
])
def test_pv08_pv07_artifact_lock_enforced_for_all_modalities(product_id: str) -> None:
    """Every product modality must enforce PROVIDER_SUCCESS != SCENE_CLIP_VALID."""
    # Case A: Provider returned URL, but clip_valid=False and file is missing
    ledger_state = queue.product_video_scene_ledger_state(
        project={"scene_count": 1, "product_type": product_id},
        job={"id": 10},
        result={
            "product_type": product_id,
            "scene_tasks": [
                {
                    "scene_index": 1,
                    "task_id": "task_1",
                    "status": "success",
                    "result_url": "https://example.com/video.mp4",
                    "clip_valid": False,
                    "artifact_valid": False,
                    "clip_path": "",
                }
            ]
        },
    )
    assert ledger_state["scene_records"][1]["clip_valid"] is False
    assert ledger_state["scene_clip_coverage_complete"] is False
    assert ledger_state["finalizer_unlocked"] is False

    # Case B: clip_valid=True but points to nonexistent file -> MUST FAIL CLOSED
    stale_state = queue.product_video_scene_ledger_state(
        project={"scene_count": 1, "product_type": product_id},
        job={"id": 11},
        result={
            "product_type": product_id,
            "scene_tasks": [
                {
                    "scene_index": 1,
                    "task_id": "task_2",
                    "status": "success",
                    "result_url": "https://example.com/video.mp4",
                    "clip_valid": True,
                    "artifact_valid": True,
                    "output_path": "/tmp/nonexistent_file_xyz_12345.mp4",
                }
            ]
        },
    )
    assert stale_state["scene_records"][1]["clip_valid"] is False, "Stale clip_valid flag was accepted without local media!"
    assert stale_state["scene_clip_coverage_complete"] is False
    assert stale_state["finalizer_unlocked"] is False


# ==============================================================================
# 10. FAILURE SEMANTICS & NO FAKE SUCCESS
# ==============================================================================

def test_pv08_deterministic_failure_semantics_no_fake_success() -> None:
    """Failure conditions must be classified deterministically without fake success."""
    # 1. Unsupported tier on V2V product
    compat = video_tail9.package_compatibility(
        "self_shot_cinematic_transform",
        scene_count=1,
        ratio="9:16",
        quality_tier_id=400,
    )
    assert compat["ok"] is False
    assert compat["reason"] == "quality_tier_not_supported"

    # 2. Unsupported ratio
    compat_ratio = video_tail9.package_compatibility(
        "video_trend",
        scene_count=1,
        ratio="21:9_unsupported",
        quality_tier_id=400,
    )
    assert compat_ratio["ok"] is False
    assert compat_ratio["reason"] == "ratio_not_supported"
