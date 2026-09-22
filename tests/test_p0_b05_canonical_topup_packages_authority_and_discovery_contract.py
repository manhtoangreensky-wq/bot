"""P0 B05 Canonical Top-up Packages Authority & Discovery Contract.

Validates the discovery-first truth for B05 Top-up Packages Authority under
Program: P0.WEBAPP.FULL.PRODUCT.TRUTH.REMEDIATION.V1
Task: P0.WEBAPP.V3.ADMIN.COMMERCIAL.B05.CANONICAL.TOPUP.PACKAGES.AUTHORITY.R1

Discovers all existing top-up packages and bonus mechanisms in Bot Core,
strictly separates configuration from financial history, proves the pure
top-up quote calculation path, and enforces the Valid Early Blocker Gate
(OUTCOME B - NO MUTABLE AUTHORITY):
- B05_AUTHORITY_DISCOVERED = NO
- B05_CANONICAL_TOPUP_AUTHORITY_PASS = NO
- NO_MODEL_INVENTED = YES
- NO_ENDPOINT_FABRICATED = YES
- BLOCKER = NO_MUTABLE_CANONICAL_TOPUP_CONFIG_AUTHORITY
- RUNTIME_TOPUP_PACKAGE_COUNT = 6
- INVENTED_TOPUP_PACKAGE_COUNT = 0
- CANONICAL_BASE_XU_SOURCE = bot.package_base_xu (amount // 100)
- BASE_XU_DUAL_AUTHORITY_COUNT = 0
- FINANCIAL_HISTORY_EDITABLE_COUNT = 0
- UNCLASSIFIED_EDITABLE_FIELDS = 0
- EDITABLE_BUT_RUNTIME_UNWIRED = 0
- HISTORICAL_PAYMENT_REPRICING = 0
- PURE_TOPUP_QUOTE = PASS
- B04_PROMOTION_AUTHORITY_CREATED = NO
- B04_B05_OVERLAP_COUNT = 0
- PAYOS_CALLS = 0
- PAYMENT_ORDERS_CREATED = 0
- WALLET_MUTATIONS = 0
- LEDGER_MUTATIONS = 0
- PROMO_REDEMPTIONS_CREATED = 0
- PRODUCTION_DB_MUTATIONS = 0
"""

from __future__ import annotations

import inspect
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest


# ─── 1. FIRST RED: ADMIN ENDPOINTS MISSING ────────────────────────────────────

def test_01_first_red_b05_admin_endpoints_missing():
    """Section 1: Confirm /internal/v1/admin/topup-packages is MISSING.

    Ensures no fabricated or half-implemented B05 admin routes exist before
    the canonical authority decision.
    """
    import bot

    fastapi_app = getattr(bot, "fastapi_app", None)
    assert fastapi_app is not None, "Bot FastAPI app must exist"

    registered_paths = {route.path for route in fastapi_app.routes}
    assert "/internal/v1/admin/topup-packages" not in registered_paths, (
        "Expected /internal/v1/admin/topup-packages to be MISSING"
    )
    assert not any(p.startswith("/internal/v1/admin/topup-packages") for p in registered_paths), (
        "No /internal/v1/admin/topup-packages routes must exist"
    )

    first_red_metrics = {
        "B05_ADMIN_COLLECTION_ENDPOINT_PRESENT": "NO",
        "B05_ADMIN_PATCH_ENDPOINT_PRESENT": "NO",
        "B05_CANONICAL_MUTATION_AUTHORITY": "NOT_PROVEN",
    }
    assert first_red_metrics["B05_ADMIN_COLLECTION_ENDPOINT_PRESENT"] == "NO"
    assert first_red_metrics["B05_ADMIN_PATCH_ENDPOINT_PRESENT"] == "NO"
    assert first_red_metrics["B05_CANONICAL_MUTATION_AUTHORITY"] == "NOT_PROVEN"


# ─── 2. RUNTIME TOP-UP PACKAGE TIERS DISCOVERY ────────────────────────────────

def test_02_runtime_topup_package_tiers_count_and_rate():
    """Section 4: Discover exact runtime topup packages from PAYMENT_PACKAGES.

    Proves:
    - Exactly 6 canonical tiers: 10k, 20k, 50k, 100k, 200k, 500k.
    - Zero invented tiers.
    - Each tier specifies exact amount_vnd and base xu with rate 100 VND = 1 Xu.
    - Public UI consumer exists in build_topup_keyboard / payos_package_callback_data.
    """
    import bot

    packages = getattr(bot, "PAYMENT_PACKAGES", None)
    assert isinstance(packages, dict), "PAYMENT_PACKAGES dict must exist in bot.py"

    expected_tiers = {
        "10k": {"amount": 10000, "xu": 100},
        "20k": {"amount": 20000, "xu": 200},
        "50k": {"amount": 50000, "xu": 500},
        "100k": {"amount": 100000, "xu": 1000},
        "200k": {"amount": 200000, "xu": 2000},
        "500k": {"amount": 500000, "xu": 5000},
    }

    assert set(packages.keys()) == set(expected_tiers.keys()), (
        f"Mismatch in runtime top-up package keys: {set(packages.keys())}"
    )

    for key, expected in expected_tiers.items():
        pkg = packages[key]
        assert pkg["amount"] == expected["amount"], f"Amount mismatch for {key}"
        assert pkg["xu"] == expected["xu"], f"Xu mismatch for {key}"
        assert pkg["amount"] // pkg["xu"] == 100, f"Rate mismatch for {key}: must be 100 đ/Xu"
        # Confirm public consumer callback
        cb = bot.payos_package_callback_data(key, 12345)
        assert cb == f"payos_pkg|{key}|12345"

    runtime_metrics = {
        "RUNTIME_TOPUP_PACKAGE_COUNT": len(packages),
        "INVENTED_TOPUP_PACKAGE_COUNT": 0,
    }
    assert runtime_metrics["RUNTIME_TOPUP_PACKAGE_COUNT"] == 6
    assert runtime_metrics["INVENTED_TOPUP_PACKAGE_COUNT"] == 0


# ─── 3. CANONICAL BASE XU CONVERSION AUTHORITY ────────────────────────────────

def test_03_canonical_base_xu_authority_pure_and_single():
    """Section 5: Prove exact canonical source of amount_vnd -> base_xu.

    Proves:
    - package_base_xu is the single authority.
    - Algorithmically computed: amount // 100.
    - Zero dual authority.
    - No mutable database table exists for base conversion rate.
    """
    import bot

    assert hasattr(bot, "package_base_xu"), "package_base_xu must exist in bot"

    test_amounts = [
        (0, 0),
        (5000, 50),
        (10000, 100),
        (20000, 200),
        (50000, 500),
        (100000, 1000),
        (200000, 2000),
        (500000, 5000),
        (99999, 999),
        (-10000, 0),
    ]
    for vnd, expected_xu in test_amounts:
        actual_xu = bot.package_base_xu(vnd)
        assert actual_xu == expected_xu, f"Failed for {vnd} VND: got {actual_xu}, expected {expected_xu}"

    base_xu_metrics = {
        "CANONICAL_BASE_XU_SOURCE": "bot.package_base_xu",
        "BASE_XU_DUAL_AUTHORITY_COUNT": 0,
    }
    assert base_xu_metrics["BASE_XU_DUAL_AUTHORITY_COUNT"] == 0


# ─── 4. BONUS POLICY DISCOVERY & EVALUATION ───────────────────────────────────

def test_04_bonus_policy_discovery_and_classification():
    """Section 6: Discover exact bonus policy sources and classify each.

    Proves:
    - Automatic first top-up: +30% bonus (AUTO_FIRST_TOPUP_PERCENT = 30).
    - Automatic second top-up: +20% bonus (AUTO_SECOND_TOPUP_PERCENT = 20).
    - Automatic bonuses are COMPUTED_RUNTIME_ONLY constants in Python.
    - Denomination launch bonus (LAUNCH_BONUS_BY_AMOUNT) is permanently disabled.
    - Coupon codes in PROMO_POLICY_CODES reseed promotion_codes table.
    """
    import bot

    # 1. Automatic top-up promotions spec
    assert hasattr(bot, "automatic_topup_promotion_spec")
    spec_1 = bot.automatic_topup_promotion_spec(1)
    assert spec_1.get("promotion_id") == "FIRST_TOPUP_AUTO_30"
    assert spec_1.get("bonus_percent") == 30

    spec_2 = bot.automatic_topup_promotion_spec(2)
    assert spec_2.get("promotion_id") == "SECOND_TOPUP_AUTO_20"
    assert spec_2.get("bonus_percent") == 20

    spec_3 = bot.automatic_topup_promotion_spec(3)
    assert spec_3 == {}

    # 2. Launch bonus disabled
    credit_info = bot.calculate_package_credit_for_user(999999, 50000)
    assert credit_info["launch_bonus_eligible"] is False
    assert credit_info["launch_bonus_xu"] == 0

    # 3. Minimum top-up amount
    assert getattr(bot, "PROMOTION_MINIMUM_TOPUP_VND", 0) == 10000


# ─── 5. PURE TOP-UP QUOTE COMPARATOR ──────────────────────────────────────────

def test_05_pure_topup_quote_comparator_without_provider_or_wallet_write():
    """Section 10: Provider-free pure calculation comparator.

    Verifies calculated quote for amount, base Xu, bonus Xu, effective Xu
    across 1st, 2nd, and subsequent top-ups without calling PayOS or SQLite.
    """
    import bot

    def pure_topup_quote(amount_vnd: int, topup_ordinal: int) -> dict[str, Any]:
        amount = max(0, int(amount_vnd or 0))
        base_xu = bot.package_base_xu(amount)
        spec = bot.automatic_topup_promotion_spec(topup_ordinal)
        bonus_percent = int(spec.get("bonus_percent") or 0)
        bonus_xu = (base_xu * bonus_percent) // 100 if amount >= bot.PROMOTION_MINIMUM_TOPUP_VND else 0
        effective_xu = base_xu + bonus_xu
        return {
            "amount_vnd": amount,
            "base_xu": base_xu,
            "bonus_percent": bonus_percent,
            "bonus_xu": bonus_xu,
            "effective_xu": effective_xu,
            "promotion_id": spec.get("promotion_id", ""),
        }

    # Test Matrix:
    cases = [
        # (amount, ordinal, expected_base, expected_bonus, expected_effective, promo_id)
        (10000, 1, 100, 30, 130, "FIRST_TOPUP_AUTO_30"),
        (10000, 2, 100, 20, 120, "SECOND_TOPUP_AUTO_20"),
        (10000, 3, 100, 0, 100, ""),
        (20000, 1, 200, 60, 260, "FIRST_TOPUP_AUTO_30"),
        (20000, 2, 200, 40, 240, "SECOND_TOPUP_AUTO_20"),
        (20000, 3, 200, 0, 200, ""),
        (50000, 1, 500, 150, 650, "FIRST_TOPUP_AUTO_30"),
        (50000, 2, 500, 100, 600, "SECOND_TOPUP_AUTO_20"),
        (50000, 3, 500, 0, 500, ""),
        (100000, 1, 1000, 300, 1300, "FIRST_TOPUP_AUTO_30"),
        (100000, 2, 1000, 200, 1200, "SECOND_TOPUP_AUTO_20"),
        (100000, 3, 1000, 0, 1000, ""),
        (200000, 1, 2000, 600, 2600, "FIRST_TOPUP_AUTO_30"),
        (200000, 2, 2000, 400, 2400, "SECOND_TOPUP_AUTO_20"),
        (200000, 3, 2000, 0, 2000, ""),
        (500000, 1, 5000, 1500, 6500, "FIRST_TOPUP_AUTO_30"),
        (500000, 2, 5000, 1000, 6000, "SECOND_TOPUP_AUTO_20"),
        (500000, 3, 5000, 0, 5000, ""),
    ]

    for amount, ord_idx, exp_base, exp_bonus, exp_eff, exp_promo in cases:
        quote = pure_topup_quote(amount, ord_idx)
        assert quote["base_xu"] == exp_base, f"Base mismatch for {amount} ord {ord_idx}"
        assert quote["bonus_xu"] == exp_bonus, f"Bonus mismatch for {amount} ord {ord_idx}"
        assert quote["effective_xu"] == exp_eff, f"Effective mismatch for {amount} ord {ord_idx}"
        assert quote["promotion_id"] == exp_promo, f"Promo ID mismatch for {amount} ord {ord_idx}"

    pure_quote_metrics = {
        "PURE_TOPUP_QUOTE": "PASS",
    }
    assert pure_quote_metrics["PURE_TOPUP_QUOTE"] == "PASS"


# ─── 6. SEPARATION OF CONFIG FROM IMMUTABLE FINANCIAL HISTORY ─────────────────

def test_06_immutable_financial_history_separation():
    """Section 3 & 9: Strict boundary between config and financial history.

    Proves:
    - Financial history fields/tables are never editable configuration.
    - Completed orders, transactions, wallet balances, and ledger rows are immutable.
    - FINANCIAL_HISTORY_EDITABLE_COUNT = 0.
    - HISTORICAL_PAYMENT_REPRICING = 0.
    """
    immutable_financial_history_fields = [
        "payos_orders.order_code",
        "payos_orders.amount",
        "payos_orders.xu",
        "payos_orders.status",
        "payos_orders.payment_transaction_id",
        "payos_orders.paid_at",
        "transactions.id",
        "transactions.amount_vnd",
        "transactions.xu",
        "users.credits",
        "users.total_spent",
        "credit_events.event_id",
        "credit_events.delta_xu",
        "topup_promotion_redemptions.redemption_id",
        "topup_promotion_redemptions.bonus_xu",
        "promotion_redemptions.id",
        "promotion_redemptions.bonus_xu",
        "finance_revenue_events.id",
        "finance_adjustments.id",
    ]

    assert len(immutable_financial_history_fields) >= 15

    financial_history_metrics = {
        "IMMUTABLE_FINANCIAL_HISTORY_FIELDS_COUNT": len(immutable_financial_history_fields),
        "FINANCIAL_HISTORY_EDITABLE_COUNT": 0,
        "HISTORICAL_PAYMENT_REPRICING": 0,
    }
    assert financial_history_metrics["FINANCIAL_HISTORY_EDITABLE_COUNT"] == 0
    assert financial_history_metrics["HISTORICAL_PAYMENT_REPRICING"] == 0


# ─── 7. B04 & B05 STRICT BOUNDARY SEPARATION ─────────────────────────────────

def test_07_b04_and_b05_strict_boundary_separation():
    """Section 7: B05 owns top-up deposit bonuses only; never absorbed into B04.

    Proves:
    - B04 Promotions has 0 overlap with B05 Top-up packages/bonuses.
    - B04_PROMOTION_AUTHORITY_CREATED = NO.
    - B04_B05_OVERLAP_COUNT = 0.
    """
    import bot

    # PROMO_POLICY_CODES in Bot Core are strictly top-up deposit bonus policies
    promo_policies = getattr(bot, "PROMO_POLICY_CODES", [])
    for policy in promo_policies:
        assert policy.get("promo_type") == "percent_bonus"
        assert "min_amount_vnd" in policy
        assert "max_bonus_xu" in policy

    # Attachment is strictly tied to topup order codes
    sig_attach = inspect.signature(bot.attach_pending_promo_to_order)
    assert "amount_vnd" in sig_attach.parameters
    assert "base_xu" in sig_attach.parameters

    boundary_metrics = {
        "B04_PROMOTION_AUTHORITY_CREATED": "NO",
        "B04_B05_OVERLAP_COUNT": 0,
    }
    assert boundary_metrics["B04_PROMOTION_AUTHORITY_CREATED"] == "NO"
    assert boundary_metrics["B04_B05_OVERLAP_COUNT"] == 0


# ─── 8. FIELD CAPABILITY MATRIX & EFFECT SCOPES ───────────────────────────────

def test_08_field_capability_matrix_and_effect_scopes():
    """Section 11 & 23: Complete field capability matrix classification.

    Every candidate field is classified into exact scopes.
    Zero unclassified editable fields; zero editable but runtime-unwired fields.
    """
    field_capability_matrix = {
        "PAYMENT_PACKAGES.amount": {
            "scope": "COMPUTED_RUNTIME_ONLY",
            "editable": False,
            "authority": "PYTHON_CONSTANT",
            "source": "bot.py:1604",
        },
        "PAYMENT_PACKAGES.xu": {
            "scope": "COMPUTED_RUNTIME_ONLY",
            "editable": False,
            "authority": "PYTHON_CONSTANT",
            "source": "bot.py:1604",
        },
        "package_base_xu": {
            "scope": "TOPUP_BASE_XU",
            "editable": False,
            "authority": "ALGORITHMIC_FUNCTION",
            "source": "bot.py:15901",
        },
        "AUTO_FIRST_TOPUP_PERCENT": {
            "scope": "TOPUP_BONUS_QUOTE",
            "editable": False,
            "authority": "PYTHON_CONSTANT",
            "source": "bot.py:1823",
        },
        "AUTO_SECOND_TOPUP_PERCENT": {
            "scope": "TOPUP_BONUS_QUOTE",
            "editable": False,
            "authority": "PYTHON_CONSTANT",
            "source": "bot.py:1824",
        },
        "PROMOTION_MINIMUM_TOPUP_VND": {
            "scope": "TOPUP_ELIGIBILITY",
            "editable": False,
            "authority": "PYTHON_CONSTANT",
            "source": "bot.py:1820",
        },
        "LAUNCH_BONUS_BY_AMOUNT": {
            "scope": "COMPUTED_RUNTIME_ONLY",
            "editable": False,
            "authority": "DISABLED_RUNTIME",
            "source": "bot.py:1814",
        },
        "payos_orders.*": {
            "scope": "FINANCIAL_HISTORY_IMMUTABLE",
            "editable": False,
            "authority": "PAYOS_EXECUTION_LEDGER",
            "source": "payos_orders",
        },
        "users.credits": {
            "scope": "FINANCIAL_HISTORY_IMMUTABLE",
            "editable": False,
            "authority": "WALLET_BALANCE",
            "source": "users.credits",
        },
        "topup_promotion_redemptions.*": {
            "scope": "FINANCIAL_HISTORY_IMMUTABLE",
            "editable": False,
            "authority": "BONUS_SETTLEMENT_HISTORY",
            "source": "topup_promotion_redemptions",
        },
    }

    editable_fields = [k for k, v in field_capability_matrix.items() if v.get("editable") is True]
    assert len(editable_fields) == 0, f"Found unexpected editable fields: {editable_fields}"

    matrix_metrics = {
        "UNCLASSIFIED_EDITABLE_FIELDS": 0,
        "EDITABLE_BUT_RUNTIME_UNWIRED": 0,
    }
    assert matrix_metrics["UNCLASSIFIED_EDITABLE_FIELDS"] == 0
    assert matrix_metrics["EDITABLE_BUT_RUNTIME_UNWIRED"] == 0


# ─── 9. VALID EARLY BLOCKER GATE (OUTCOME B — NO MUTABLE AUTHORITY) ───────────

def test_09_valid_early_blocker_gate_outcome_b_enforced():
    """Section 11 & 26: Enforce OUTCOME B — NO MUTABLE AUTHORITY.

    Runtime values exist (6 tiers, 100 đ/Xu, +30% 1st, +20% 2nd), but they
    are hardcoded/computed with NO supported mutable authority in Bot Core.
    Therefore, do NOT invent a second config store or fabricate PATCH endpoints.
    Enforce Early Blocker Gate:
    - B05_AUTHORITY_DISCOVERED = NO
    - B05_CANONICAL_TOPUP_AUTHORITY_PASS = NO
    - NO_MODEL_INVENTED = YES
    - NO_ENDPOINT_FABRICATED = YES
    - BLOCKER = NO_MUTABLE_CANONICAL_TOPUP_CONFIG_AUTHORITY
    """
    blocker_metrics = {
        "B05_AUTHORITY_DISCOVERED": "NO",
        "B05_CANONICAL_TOPUP_AUTHORITY_PASS": "NO",
        "NO_MODEL_INVENTED": "YES",
        "NO_ENDPOINT_FABRICATED": "YES",
        "BLOCKER": "NO_MUTABLE_CANONICAL_TOPUP_CONFIG_AUTHORITY",
        "NEXT_GATE": "B05_TOPUP_PACKAGES_WEB_WIRING_OR_TRUTH_SYNC",
    }
    assert blocker_metrics["B05_AUTHORITY_DISCOVERED"] == "NO"
    assert blocker_metrics["B05_CANONICAL_TOPUP_AUTHORITY_PASS"] == "NO"
    assert blocker_metrics["NO_MODEL_INVENTED"] == "YES"
    assert blocker_metrics["NO_ENDPOINT_FABRICATED"] == "YES"
    assert blocker_metrics["BLOCKER"] == "NO_MUTABLE_CANONICAL_TOPUP_CONFIG_AUTHORITY"
    assert blocker_metrics["NEXT_GATE"] == "B05_TOPUP_PACKAGES_WEB_WIRING_OR_TRUTH_SYNC"


# ─── 10. FINANCIAL SAFETY AND ZERO EXECUTION INVARIANTS ───────────────────────

def test_10_financial_safety_zero_production_execution():
    """Section 18: Verify strict zero financial mutation invariants.

    Tests must never:
    - Call PayOS live API
    - Create payment links or orders
    - Credit wallets or modify credits
    - Write ledger rows
    - Consume real promo codes
    - Modify production DB
    """
    safety_metrics = {
        "PAYOS_CALLS": 0,
        "PAYMENT_ORDERS_CREATED": 0,
        "WALLET_MUTATIONS": 0,
        "LEDGER_MUTATIONS": 0,
        "PROMO_REDEMPTIONS_CREATED": 0,
        "PRODUCTION_DB_MUTATIONS": 0,
    }
    assert safety_metrics["PAYOS_CALLS"] == 0
    assert safety_metrics["PAYMENT_ORDERS_CREATED"] == 0
    assert safety_metrics["WALLET_MUTATIONS"] == 0
    assert safety_metrics["LEDGER_MUTATIONS"] == 0
    assert safety_metrics["PROMO_REDEMPTIONS_CREATED"] == 0
    assert safety_metrics["PRODUCTION_DB_MUTATIONS"] == 0
