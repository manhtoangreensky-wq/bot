"""Focused provider-free test suite for Provider Spend Guard, Hard Weekly Cap, Bot-Only Paid Origin, and Ambiguous Submit Safety.

TASK_ID: P0.PRODUCT_VIDEO_R16_10B14N21P_KEY4U_ACCOUNT_SPEND_FORENSIC_DEFECT_CORRECTION_AND_PAID_SPEND_GUARD_PR
TRACKER: manhtoangreensky-wq/bot#1155
GLOBAL_DIRECTIVE: manhtoangreensky-wq/bot#1422

Invariants verified:
1. BOT paid live origin valid -> guard can proceed.
2. Shell script paid test -> BLOCKED.
3. Python script / manual script paid test -> BLOCKED.
4. Worker injection paid test -> BLOCKED.
5. Direct provider / internal API bypass -> BLOCKED.
6. CI paid test -> BLOCKED.
7. Pytest with production credentials -> BLOCKED from network / real calls.
8. Below weekly cap -> PASS reservation.
9. Exactly at cap -> next submit BLOCKED.
10. Over cap -> BLOCKED.
11. Concurrent requests racing -> atomic lock guarantees total reserved + settled cannot exceed $200.00.
12. Ambiguous submit -> reservation retained in weekly spend.
13. Ambiguous submit -> retry BLOCKED.
14. Duplicate submit (same idempotency key / job) -> BLOCKED.
15. Fallback after ambiguous submit -> BLOCKED.
16. Usage / spend authority unavailable -> fail closed.
17. Central kill switch active -> NEW paid submits BLOCKED, read-only status allowed.
18. Canonical Product Video credential missing -> BLOCKED.
19. Sanitized audit record contains required fields and 0 secret leaks.
"""

from __future__ import annotations

import concurrent.futures
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.provider_spend_guard import (
    BLOCKER_AMBIGUOUS_RETRY_BLOCKED,
    BLOCKER_BOT_ORIGIN_PROOF_MISSING,
    BLOCKER_DUPLICATE_PAID_SUBMIT,
    BLOCKER_KILL_SWITCH_ACTIVE,
    BLOCKER_PAID_LIVE_TEST_BOT_ONLY,
    BLOCKER_SPEND_GUARD_AUTHORITY_UNAVAILABLE,
    BLOCKER_TEST_NETWORK_ISOLATION,
    BLOCKER_WEEKLY_SPEND_CAP_EXCEEDED,
    DEFAULT_WEEKLY_PROVIDER_SPEND_CAP_USD,
    SpendGuardContext,
    build_sanitized_audit_record,
    get_weekly_spend_summary,
    init_spend_guard_db,
    is_kill_switch_active,
    release_provider_spend_no_charge,
    reserve_provider_spend,
    retain_ambiguous_provider_spend,
    set_kill_switch,
    settle_provider_spend,
    validate_bot_paid_live_origin,
)
from services.video_provider_catalog import (
    KEY4U_VIDEO_AUTH_MISSING,
    resolve_product_video_key4u_auth,
)
from services.video_provider_router import (
    product_video_provider_submit_source_policy,
)


class TestProviderSpendGuardAndBotOrigin(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_spend_guard_")
        self.db_path = os.path.join(self.temp_dir, "test_spend.db")
        init_spend_guard_db(db_path=self.db_path)
        set_kill_switch(None)

    def tearDown(self):
        set_kill_switch(None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_bot_paid_live_origin_valid_passes(self):
        ctx = SpendGuardContext(
            job_id="job_101",
            request_id="VID-20261011-000101",
            trace_id="tr_001",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            estimated_max_cost_usd=1.50,
            bot_originated_action=True,
            user_flow="bot_product_video_confirm",
            entrypoint="bot",
            is_paid_live_attempt=True,
        )
        env = {"REAL_PROVIDER_CALLS_ALLOWED": "1"}
        valid, blocker = validate_bot_paid_live_origin(ctx, env)
        self.assertTrue(valid)
        self.assertEqual(blocker, "")

        res = reserve_provider_spend(ctx, db_path=self.db_path, env=env)
        self.assertTrue(res.allowed)
        self.assertNotEqual(res.reservation_id, "")
        self.assertEqual(res.week_spend_after_usd, 1.50)

    def test_02_shell_paid_test_blocked(self):
        ctx = SpendGuardContext(
            job_id="job_shell_01",
            request_id="VID-SHELL-001",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            estimated_max_cost_usd=1.00,
            bot_originated_action=False,
            user_flow="manual_cli",
            entrypoint="shell",
            is_paid_live_attempt=True,
        )
        env = {"REAL_PROVIDER_CALLS_ALLOWED": "1"}
        valid, blocker = validate_bot_paid_live_origin(ctx, env)
        self.assertFalse(valid)
        self.assertEqual(blocker, BLOCKER_PAID_LIVE_TEST_BOT_ONLY)

        res = reserve_provider_spend(ctx, db_path=self.db_path, env=env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_PAID_LIVE_TEST_BOT_ONLY)

    def test_03_script_paid_test_blocked(self):
        ctx = SpendGuardContext(
            job_id="job_script_01",
            request_id="VID-SCRIPT-001",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            estimated_max_cost_usd=1.00,
            bot_originated_action=False,
            user_flow="adhoc_script",
            entrypoint="script",
            is_paid_live_attempt=True,
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env={"REAL_PROVIDER_CALLS_ALLOWED": "1"})
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_PAID_LIVE_TEST_BOT_ONLY)

    def test_04_worker_injection_paid_test_blocked(self):
        ctx = SpendGuardContext(
            job_id="job_worker_inj_01",
            request_id="VID-INJ-001",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            estimated_max_cost_usd=1.00,
            bot_originated_action=False,
            user_flow="worker_direct",
            entrypoint="worker_injection",
            is_paid_live_attempt=True,
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env={"REAL_PROVIDER_CALLS_ALLOWED": "1"})
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_PAID_LIVE_TEST_BOT_ONLY)

    def test_05_direct_provider_bypass_blocked(self):
        ctx = SpendGuardContext(
            job_id="job_direct_01",
            request_id="VID-DIRECT-001",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            estimated_max_cost_usd=1.00,
            bot_originated_action=False,
            user_flow="raw_provider_call",
            entrypoint="direct_provider",
            is_paid_live_attempt=True,
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env={"REAL_PROVIDER_CALLS_ALLOWED": "1"})
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_PAID_LIVE_TEST_BOT_ONLY)

    def test_06_ci_paid_test_blocked(self):
        ctx = SpendGuardContext(
            job_id="job_ci_01",
            request_id="VID-CI-001",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            estimated_max_cost_usd=1.00,
            bot_originated_action=True,
            user_flow="ci_workflow",
            entrypoint="ci",
            is_paid_live_attempt=True,
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env={"REAL_PROVIDER_CALLS_ALLOWED": "1"})
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_PAID_LIVE_TEST_BOT_ONLY)

    def test_07_pytest_with_real_calls_blocked(self):
        ctx = SpendGuardContext(
            job_id="job_test_01",
            request_id="VID-TEST-001",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            estimated_max_cost_usd=1.00,
            bot_originated_action=True,
            user_flow="bot_product_video_confirm",
            entrypoint="bot",
            is_paid_live_attempt=True,
        )
        # In test env with REAL_PROVIDER_CALLS_ALLOWED=0
        env = {"REAL_PROVIDER_CALLS_ALLOWED": "0"}
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_TEST_NETWORK_ISOLATION)

    def test_08_below_weekly_cap_passes(self):
        # Settle $180.00 first
        ctx_prev = SpendGuardContext(
            job_id="job_prev_01",
            request_id="VID-PREV-001",
            trace_id="tr_prev",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            estimated_max_cost_usd=180.00,
            bot_originated_action=True,
            user_flow="bot_confirm",
            entrypoint="bot",
            is_paid_live_attempt=False,
        )
        res_prev = reserve_provider_spend(ctx_prev, db_path=self.db_path)
        self.assertTrue(res_prev.allowed)
        settle_provider_spend(res_prev.reservation_id, actual_cost_usd=180.00, db_path=self.db_path)

        # Now attempt $15.00 (180 + 15 = 195 <= 200)
        ctx_new = SpendGuardContext(
            job_id="job_new_01",
            request_id="VID-NEW-001",
            trace_id="tr_new",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            estimated_max_cost_usd=15.00,
            bot_originated_action=True,
            user_flow="bot_confirm",
            entrypoint="bot",
            is_paid_live_attempt=False,
        )
        res_new = reserve_provider_spend(ctx_new, db_path=self.db_path)
        self.assertTrue(res_new.allowed)
        self.assertEqual(res_new.week_spend_before_usd, 180.00)
        self.assertEqual(res_new.week_spend_after_usd, 195.00)

    def test_09_exactly_at_cap_next_submit_blocked(self):
        # Settle up to $200.00 exactly
        ctx_fill = SpendGuardContext(
            job_id="job_fill_01",
            request_id="VID-FILL-001",
            trace_id="tr_fill",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            estimated_max_cost_usd=200.00,
            bot_originated_action=True,
            user_flow="bot_confirm",
            entrypoint="bot",
            is_paid_live_attempt=False,
        )
        res_fill = reserve_provider_spend(ctx_fill, db_path=self.db_path)
        self.assertTrue(res_fill.allowed)
        settle_provider_spend(res_fill.reservation_id, actual_cost_usd=200.00, db_path=self.db_path)

        # Next submit of even $0.01 must be BLOCKED
        ctx_over = SpendGuardContext(
            job_id="job_over_01",
            request_id="VID-OVER-001",
            trace_id="tr_over",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            estimated_max_cost_usd=0.01,
            bot_originated_action=True,
            user_flow="bot_confirm",
            entrypoint="bot",
            is_paid_live_attempt=False,
        )
        res_over = reserve_provider_spend(ctx_over, db_path=self.db_path)
        self.assertFalse(res_over.allowed)
        self.assertEqual(res_over.blocker, BLOCKER_WEEKLY_SPEND_CAP_EXCEEDED)

    def test_10_over_cap_blocked(self):
        # Attempting single request over $200.00
        ctx_huge = SpendGuardContext(
            job_id="job_huge_01",
            request_id="VID-HUGE-001",
            trace_id="tr_huge",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            estimated_max_cost_usd=205.00,
            bot_originated_action=True,
            user_flow="bot_confirm",
            entrypoint="bot",
            is_paid_live_attempt=False,
        )
        res_huge = reserve_provider_spend(ctx_huge, db_path=self.db_path)
        self.assertFalse(res_huge.allowed)
        self.assertEqual(res_huge.blocker, BLOCKER_WEEKLY_SPEND_CAP_EXCEEDED)

    def test_11_concurrent_reservations_cannot_exceed_cap(self):
        # Starting with $150.00 settled
        ctx_base = SpendGuardContext(
            job_id="job_base_01",
            request_id="VID-BASE-001",
            trace_id="tr_base",
            estimated_max_cost_usd=150.00,
            bot_originated_action=True,
            user_flow="bot_confirm",
            entrypoint="bot",
        )
        res_base = reserve_provider_spend(ctx_base, db_path=self.db_path)
        self.assertTrue(res_base.allowed)
        settle_provider_spend(res_base.reservation_id, actual_cost_usd=150.00, db_path=self.db_path)

        # Remaining budget is $50.00.
        # Launch 8 concurrent threads, each requesting $15.00 (8 * 15 = $120 total requested).
        # At most 3 can succeed (3 * 15 = $45 <= $50; 4 * 15 = $60 > $50).
        def attempt_reserve(i: int):
            ctx = SpendGuardContext(
                job_id=f"job_concurrent_{i}",
                request_id=f"VID-CONC-{i}",
                trace_id=f"tr_conc_{i}",
                estimated_max_cost_usd=15.00,
                bot_originated_action=True,
                user_flow="bot_confirm",
                entrypoint="bot",
            )
            return reserve_provider_spend(ctx, db_path=self.db_path)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(attempt_reserve, i) for i in range(8)]
            results = [f.result() for f in futures]

        allowed_count = sum(1 for r in results if r.allowed)
        blocked_count = sum(1 for r in results if not r.allowed and r.blocker == BLOCKER_WEEKLY_SPEND_CAP_EXCEEDED)

        self.assertLessEqual(allowed_count, 3)
        self.assertEqual(allowed_count + blocked_count, 8)

        # Verify summary reflects at most $200.00 total active spend
        summary = get_weekly_spend_summary(db_path=self.db_path)
        self.assertLessEqual(summary["total_active_week_spend_usd"], DEFAULT_WEEKLY_PROVIDER_SPEND_CAP_USD)

    def test_12_ambiguous_submit_retains_reservation(self):
        ctx = SpendGuardContext(
            job_id="job_ambig_01",
            request_id="VID-AMBIG-001",
            trace_id="tr_ambig_01",
            estimated_max_cost_usd=25.00,
            bot_originated_action=True,
            user_flow="bot_confirm",
            entrypoint="bot",
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path)
        self.assertTrue(res.allowed)

        # Mark ambiguous outcome
        retained = retain_ambiguous_provider_spend(
            res.reservation_id,
            error_code="provider_submit_outcome_ambiguous_no_charge",
            provider_task_id="task_maybe_received_123",
            db_path=self.db_path,
        )
        self.assertTrue(retained)

        # The $25.00 MUST remain counted in pending_reserved_spend
        summary = get_weekly_spend_summary(db_path=self.db_path)
        self.assertEqual(summary["pending_reserved_spend_usd"], 25.00)
        self.assertEqual(summary["total_active_week_spend_usd"], 25.00)

    def test_13_ambiguous_submit_retry_blocked(self):
        ctx = SpendGuardContext(
            job_id="job_retry_01",
            request_id="VID-RETRY-001",
            trace_id="tr_retry_01",
            estimated_max_cost_usd=20.00,
            bot_originated_action=True,
            user_flow="bot_confirm",
            entrypoint="bot",
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path)
        self.assertTrue(res.allowed)

        retain_ambiguous_provider_spend(
            res.reservation_id,
            error_code="provider_submit_timeout",
            db_path=self.db_path,
        )

        # Attempt to retry the same job/idempotency key
        res_retry = reserve_provider_spend(ctx, db_path=self.db_path)
        self.assertFalse(res_retry.allowed)
        self.assertEqual(res_retry.blocker, BLOCKER_AMBIGUOUS_RETRY_BLOCKED)

    def test_14_duplicate_paid_submit_blocked(self):
        ctx = SpendGuardContext(
            job_id="job_dup_01",
            request_id="VID-DUP-001",
            trace_id="tr_dup_01",
            estimated_max_cost_usd=10.00,
            bot_originated_action=True,
            user_flow="bot_confirm",
            entrypoint="bot",
        )
        res1 = reserve_provider_spend(ctx, db_path=self.db_path)
        self.assertTrue(res1.allowed)

        # Duplicate submit with same job/idempotency key while first is RESERVED
        res2 = reserve_provider_spend(ctx, db_path=self.db_path)
        self.assertFalse(res2.allowed)
        self.assertEqual(res2.blocker, BLOCKER_DUPLICATE_PAID_SUBMIT)

    def test_15_fallback_after_ambiguous_blocked_policy(self):
        # Test product_video_provider_submit_source_policy blocks hidden / unconfirmed fallbacks
        policy = product_video_provider_submit_source_policy(
            metadata={
                "submit_source": "fallback",
                "is_paid_live": True,
                "bot_originated_action": False,
            }
        )
        self.assertFalse(policy["provider_submit_allowed"])

    def test_16_usage_authority_unavailable_fails_closed(self):
        ctx = SpendGuardContext(
            job_id="job_err_01",
            request_id="VID-ERR-001",
            estimated_max_cost_usd=5.00,
        )
        # Non-existent directory path
        bad_path = os.path.join(self.temp_dir, "nonexistent_dir", "sub", "bad.db")
        res = reserve_provider_spend(ctx, db_path=bad_path)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_SPEND_GUARD_AUTHORITY_UNAVAILABLE)

    def test_17_kill_switch_blocks_new_submits_allows_polling(self):
        set_kill_switch(True)
        self.assertTrue(is_kill_switch_active())

        ctx = SpendGuardContext(
            job_id="job_ks_01",
            request_id="VID-KS-001",
            estimated_max_cost_usd=5.00,
            bot_originated_action=True,
            user_flow="bot_confirm",
            entrypoint="bot",
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_KILL_SWITCH_ACTIVE)

        # Polling policy check
        policy = product_video_provider_submit_source_policy(
            metadata={"submit_source": "worker_poll_existing_task"},
            poll_existing_task=True,
        )
        self.assertFalse(policy["provider_submit_allowed"])
        self.assertTrue(policy["poll_existing_task_allowed"])

    def test_18_canonical_product_video_credential_missing_fails_closed(self):
        env = {
            "KEY4U_API_KEY": "some-key",
            "KEY4U_TOKEN": "some-token",
        }
        auth_decision = resolve_product_video_key4u_auth(env)
        self.assertFalse(auth_decision["ready"])
        self.assertEqual(auth_decision["blocker"], KEY4U_VIDEO_AUTH_MISSING)

    def test_19_sanitized_audit_record_no_secret_leaks(self):
        ctx = SpendGuardContext(
            job_id="job_audit_01",
            request_id="VID-AUDIT-001",
            trace_id="tr_audit_01",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            estimated_max_cost_usd=2.50,
            bot_originated_action=True,
            user_flow="bot_confirm",
            entrypoint="bot",
        )
        raw_secret_task_id = "task_secret_sk_live_1234567890abcdef"
        audit = build_sanitized_audit_record(
            ctx,
            week_spend_before_usd=10.00,
            week_spend_after_usd=12.50,
            reserved_cost_usd=2.50,
            actual_settled_cost_usd=2.50,
            provider_task_id=raw_secret_task_id,
        )
        # Check required fields
        expected_keys = {
            "BOT_ORIGINATED_ACTION",
            "BOT_REQUEST_OR_TRACE_ID",
            "BOT_JOB_ID",
            "PRODUCT_FAMILY",
            "PROVIDER",
            "MODEL",
            "ESTIMATED_MAX_COST_USD",
            "RESERVED_COST_USD",
            "WEEK_SPEND_BEFORE_USD",
            "WEEK_SPEND_AFTER_RESERVATION_USD",
            "PROVIDER_TASK_ID_SAFE",
            "ACTUAL_SETTLED_COST_USD",
        }
        self.assertTrue(expected_keys.issubset(audit.keys()))
        self.assertNotIn("sk_live", str(audit))
        self.assertNotIn("1234567890", str(audit))
        self.assertIn("...", audit["PROVIDER_TASK_ID_SAFE"])


if __name__ == "__main__":
    unittest.main()
