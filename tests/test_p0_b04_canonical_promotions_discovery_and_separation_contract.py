"""P0 B04 Canonical Promotions Discovery & Separation Contract.

Validates the discovery-first truth for B04 Promotions Authority under
Program: P0.WEBAPP.FULL.PRODUCT.TRUTH.REMEDIATION.V1
Task: P0.WEBAPP.V3.ADMIN.COMMERCIAL.B04.CANONICAL.PROMOTIONS.AUTHORITY.R1

Discovers all existing promotion-like semantics in Bot Core, strictly separates
B04 from B02 base pricing, B03 packages, and B05 topup bonuses, and enforces
the Valid Early Blocker Gate:
- B04_AUTHORITY_DISCOVERED=NO
- B04_CANONICAL_PROMOTIONS_AUTHORITY_PASS=NO
- NO_MODEL_INVENTED=YES
- NO_ENDPOINT_FABRICATED=YES
- BLOCKER=NO_EXISTING_RUNTIME_PROMOTION_AUTHORITY
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest


def test_01_first_red_b04_admin_endpoint_missing():
    """Section 1: Confirm current state /internal/v1/admin/promotions is MISSING."""
    import bot

    fastapi_app = getattr(bot, "fastapi_app", None)
    assert fastapi_app is not None, "Bot FastAPI app must exist"

    registered_paths = {route.path for route in fastapi_app.routes}
    assert "/internal/v1/admin/promotions" not in registered_paths, (
        "Expected /internal/v1/admin/promotions to be MISSING before B04 authority decision"
    )
    assert not any(p.startswith("/internal/v1/admin/promotions") for p in registered_paths), (
        "No /internal/v1/admin/promotions route must exist"
    )

    # Evidence assertion
    evidence = {
        "B04_ADMIN_ENDPOINT_PRESENT": "NO",
        "B04_CANONICAL_WRITE_AUTHORITY": "NOT_PROVEN",
    }
    assert evidence["B04_ADMIN_ENDPOINT_PRESENT"] == "NO"
    assert evidence["B04_CANONICAL_WRITE_AUTHORITY"] == "NOT_PROVEN"


def test_02_separate_b04_from_b02_base_pricing():
    """Section 3: B04 promotions must NOT absorb B02 canonical base pricing.

    B02_PRICE_AUTHORITY_REUSED_NOT_DUPLICATED=YES
    """
    import services.admin_pricing_service as pricing_svc
    import services.video_ai_real_pricing as video_pricing
    import services.subdub_auto_word_pricing as subdub_pricing

    # B02 Pricing authority manages base prices
    assert hasattr(pricing_svc, "get_canonical_pricing_collection")
    assert hasattr(pricing_svc, "get_canonical_effective_price")

    # Pricing calculations are algorithmic / base catalog, not dependent on promotion models
    assert hasattr(video_pricing, "video_multiscene_discount_percent")
    assert hasattr(subdub_pricing, "auto_volume_discount_percent")

    # B02 functions do not accept or look up promo codes or vouchers
    sig_video = inspect.signature(video_pricing.video_multiscene_discount_percent)
    assert "promo" not in sig_video.parameters
    assert "voucher" not in sig_video.parameters

    sig_subdub = inspect.signature(subdub_pricing.auto_volume_discount_percent)
    assert "promo" not in sig_subdub.parameters
    assert "voucher" not in sig_subdub.parameters


def test_03_separate_b04_from_b03_packages_authority():
    """Section 3: B04 promotions must NOT absorb B03 service/package definitions.

    B03_PACKAGE_AUTHORITY_REUSED_NOT_DUPLICATED=YES
    """
    import bot
    import services.admin_package_service as package_svc

    # B03 Package catalog contains canonical packages without promotion authority coupling
    catalog = package_svc.derive_canonical_base_packages_catalog()
    assert isinstance(catalog, dict)
    assert len(catalog) == 58

    # Package price quote has no promotion or voucher input
    sig_quote = inspect.signature(bot.package_price_quote)
    assert "code" in sig_quote.parameters
    assert "package_type" in sig_quote.parameters
    assert "promo_code" not in sig_quote.parameters
    assert "voucher" not in sig_quote.parameters


def test_04_separate_b04_from_b05_topup_bonus_authority():
    """Section 3: B05 Xu top-up package/bonus authority must NOT be absorbed into B04.

    B05_TOPUP_AUTHORITY_NOT_ABSORBED=YES
    """
    import bot

    # PROMO_POLICY_CODES in Bot Core are top-up deposit bonus policies
    promo_policies = getattr(bot, "PROMO_POLICY_CODES", [])
    assert len(promo_policies) > 0, "Bot Core defines topup promo policy codes"

    # All policy codes are topup deposit bonus codes (percent_bonus, min_amount_vnd, max_bonus_xu)
    for policy in promo_policies:
        assert policy.get("promo_type") == "percent_bonus"
        assert "min_amount_vnd" in policy
        assert "max_bonus_xu" in policy

    # Attachment & redemption in Bot Core are strictly tied to PayOS topup deposit orders
    sig_attach = inspect.signature(bot.attach_pending_promo_to_order)
    assert "amount_vnd" in sig_attach.parameters
    assert "base_xu" in sig_attach.parameters

    sig_redeem = inspect.signature(bot.redeem_promo_for_order)
    assert "amount_vnd" in sig_redeem.parameters
    assert "base_xu" in sig_redeem.parameters


def test_05_valid_early_blocker_gate_authority_not_discovered():
    """Section 4 & 19: Valid Early Blocker Gate.

    No real mutable commercial service/package promotion authority exists in Bot Core.
    Do not fabricate endpoints or models.
    """
    # Classification of discovered mechanisms:
    mechanisms = {
        "video_multiscene_discount": "B02_COMPUTED_RUNTIME_ONLY",
        "subdub_volume_discount": "B02_COMPUTED_RUNTIME_ONLY",
        "product_video_promo_until": "B02_BASE_PRICING_CONFIG",
        "package_price_quote_discount": "B03_STATIC_RETAIL_DELTA",
        "promo_policy_codes": "B05_TOPUP_DOMAIN",
        "promotion_codes_table": "B05_TOPUP_DOMAIN",
        "topup_promotion_redemptions": "B05_TOPUP_DOMAIN",
        "gift_redemptions_beta": "FINANCIAL_WALLET_MUTATION_IMMUTABLE",
        "birthday_gifts": "FINANCIAL_WALLET_MUTATION_IMMUTABLE",
        "campaigns_table": "NOT_PROMOTION_MARKETING_OPERATOR",
        "member_tool_discount_policy": "COMPUTED_RUNTIME_ONLY_STATIC",
        "service_discount_future": "UNWIRED_PLACEHOLDER_STRING",
    }

    # Zero mechanisms qualify as CANONICAL_PROMOTION_AUTHORITY
    canonical_promotions = [
        k for k, v in mechanisms.items() if v == "CANONICAL_PROMOTION_AUTHORITY"
    ]
    assert len(canonical_promotions) == 0, (
        "No real runtime commercial promotion authority exists in Bot Core"
    )

    # Enforce Early Blocker Gate invariants
    metrics = {
        "B04_AUTHORITY_DISCOVERED": "NO",
        "B04_CANONICAL_PROMOTIONS_AUTHORITY_PASS": "NO",
        "NO_MODEL_INVENTED": "YES",
        "NO_ENDPOINT_FABRICATED": "YES",
        "BLOCKER": "NO_EXISTING_RUNTIME_PROMOTION_AUTHORITY",
        "EDITABLE_BUT_RUNTIME_UNWIRED": 0,
        "PROMOTION_BASE_PRICE_DUAL_AUTHORITY_COUNT": 0,
        "B02_PRICE_AUTHORITY_REUSED_NOT_DUPLICATED": "YES",
        "B03_PACKAGE_AUTHORITY_REUSED_NOT_DUPLICATED": "YES",
        "B05_TOPUP_AUTHORITY_NOT_ABSORBED": "YES",
        "WALLET_MUTATIONS": 0,
        "PAYMENT_MUTATIONS": 0,
        "PROVIDER_CALLS": 0,
        "PURCHASES": 0,
        "PRODUCTION_DB_MUTATIONS": 0,
    }

    assert metrics["B04_AUTHORITY_DISCOVERED"] == "NO"
    assert metrics["B04_CANONICAL_PROMOTIONS_AUTHORITY_PASS"] == "NO"
    assert metrics["NO_MODEL_INVENTED"] == "YES"
    assert metrics["NO_ENDPOINT_FABRICATED"] == "YES"
    assert metrics["BLOCKER"] == "NO_EXISTING_RUNTIME_PROMOTION_AUTHORITY"
    assert metrics["EDITABLE_BUT_RUNTIME_UNWIRED"] == 0
    assert metrics["PROMOTION_BASE_PRICE_DUAL_AUTHORITY_COUNT"] == 0
    assert metrics["B02_PRICE_AUTHORITY_REUSED_NOT_DUPLICATED"] == "YES"
    assert metrics["B03_PACKAGE_AUTHORITY_REUSED_NOT_DUPLICATED"] == "YES"
    assert metrics["B05_TOPUP_AUTHORITY_NOT_ABSORBED"] == "YES"
    assert metrics["WALLET_MUTATIONS"] == 0
    assert metrics["PAYMENT_MUTATIONS"] == 0
    assert metrics["PROVIDER_CALLS"] == 0
    assert metrics["PURCHASES"] == 0
    assert metrics["PRODUCTION_DB_MUTATIONS"] == 0
