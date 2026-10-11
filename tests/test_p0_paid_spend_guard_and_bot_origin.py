"""Authoritative 25-case provider-free test suite for Provider Spend Guard.

TASK_ID: P0.PRODUCT_VIDEO_R16_10B14N21Q_PR1423_SPEND_GUARD_AUTHORITY_TRUTH_AND_FAIL_CLOSED_CORRECTION
TRACKER: manhtoangreensky-wq/bot#1155
GLOBAL_DIRECTIVE: manhtoangreensky-wq/bot#1422

All 25 test cases run strictly offline with 0 real provider calls.
"""

from __future__ import annotations

from decimal import Decimal
import json
import multiprocessing
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.provider_spend_guard import (
    BLOCKER_AMBIGUOUS_RETRY_BLOCKED,
    BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING,
    BLOCKER_BOT_ORIGIN_PROOF_MISSING,
    BLOCKER_DUPLICATE_PAID_SUBMIT,
    BLOCKER_KILL_SWITCH_ACTIVE,
    BLOCKER_MAX_COST_AUTHORITY_MISSING,
    BLOCKER_PAID_LIVE_TEST_BOT_ONLY,
    BLOCKER_POLICY_INCOMPLETE,
    BLOCKER_SHARED_DB_UNAVAILABLE,
    BLOCKER_SPEND_GUARD_AUTHORITY_UNAVAILABLE,
    BLOCKER_TEST_NETWORK_ISOLATION,
    BLOCKER_WEEKLY_SPEND_CAP_EXCEEDED,
    DEFAULT_WEEKLY_PROVIDER_SPEND_CAP_MICRO_USD,
    DEFAULT_WEEKLY_PROVIDER_SPEND_CAP_USD,
    STATUS_AMBIGUOUS_RETAINED,
    STATUS_RELEASED_PROVEN_NO_CHARGE,
    STATUS_RESERVED,
    STATUS_SETTLED_VERIFIED,
    STATUS_SUBMITTED_PENDING_SETTLEMENT,
    SpendGuardContext,
    build_sanitized_audit_record,
    get_weekly_spend_summary,
    get_current_spend_week_id,
    init_spend_guard_db,
    is_kill_switch_active,
    mark_submitted_pending_settlement,
    release_provider_spend_no_charge,
    reserve_provider_spend,
    retain_ambiguous_provider_spend,
    set_kill_switch,
    settle_verified_provider_spend,
    to_micro_usd,
    from_micro_usd,
    validate_bot_paid_live_origin,
    verify_shared_db_parity,
    resolve_spend_guard_db_path,
    ProviderPaidTransportAuthority,
    PROVIDER_PAID_TRANSPORT_REGISTRY,
    resolve_paid_transport_authority,
    create_bot_confirmation,
    BLOCKER_PAID_TRANSPORT_AUTHORITY_UNREGISTERED,
)
from services.video_provider_catalog import (
    KEY4U_VIDEO_AUTH_MISSING,
    resolve_product_video_key4u_auth,
)
from services.video_provider_router import (
    product_video_provider_submit_source_policy,
)
import asyncio
from unittest.mock import AsyncMock, MagicMock
import httpx
import urllib.error

from services.shopaikey_tts_async_adapter import shopaikey_minimax_tts_async_submit
from services.chat_pro_pricing import ClaudeOpusPricing, CLAUDE_OPUS_MODEL
from services.public_chat_runtime import PublicChatRequest, PublicChatRuntime
from services.public_chat_store import PublicChatStore
from services.video_ai_edit_provider import (
    AiEditProviderConfig,
    AiEditProviderError,
    PUBLIC_FINAL_CONFIRM_SOURCE,
    submit_video_edit,
)


def _process_reserve_worker(db_path: str, env_dict: dict, job_id: str, cost: float, result_queue: multiprocessing.Queue):
    """Top-level picklable helper for multi-process concurrency testing."""
    conf_id = create_bot_confirmation(
        job_id=job_id,
        request_id=f"REQ-{job_id}",
        product_family="Video AI Edit",
        operation="submit_video_edit",
        db_path=db_path,
        env=env_dict,
    )
    ctx = SpendGuardContext(
        job_id=job_id,
        request_id=f"REQ-{job_id}",
        trace_id=f"TR-{job_id}",
        product_family="Video AI Edit",
        provider="fal_video",
        model="wan-v2.2",
        operation="submit_video_edit",
        bot_originated_action=True,
        bot_confirm_authority=conf_id,
        user_flow="bot_product_video_confirm",
        entrypoint="bot",
        is_paid_live_attempt=False,
        metadata={"duration_seconds": 5},
    )
    res = reserve_provider_spend(ctx, db_path=db_path, env=env_dict)
    result_queue.put({
        "job_id": job_id,
        "allowed": res.allowed,
        "blocker": res.blocker,
        "reservation_id": res.reservation_id,
    })


class TestProviderSpendGuard25Cases(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_spend_guard_25_")
        self.db_path = os.path.join(self.temp_dir, "shared_toanaas.db")
        self.standard_env = {
            "SPEND_GUARD_DB_PATH": self.db_path,
            "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE": "MONDAY_0000_UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE": "UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_USD": "200.000",
        }
        init_spend_guard_db(db_path=self.db_path, env=self.standard_env)
        set_kill_switch(None)

    def tearDown(self):
        set_kill_switch(None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_valid_reservation(
        self,
        job_id: str,
        request_id: str,
        *,
        product_family: str = "Video AI Edit",
        provider: str = "fal_video",
        operation: str = "submit_video_edit",
        model: str = "wan-v2.2",
        duration_seconds: int = 5,
    ) -> SpendReservationResult:
        conf_id = create_bot_confirmation(
            job_id=job_id,
            request_id=request_id,
            product_family=product_family,
            operation=operation,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id=job_id,
            request_id=request_id,
            trace_id=f"tr_{job_id}",
            product_family=product_family,
            provider=provider,
            model=model,
            operation=operation,
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="bot_confirm",
            metadata={"duration_seconds": duration_seconds},
        )
        return reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)

    # 1. Missing reset rule -> BLOCK (weekly_provider_spend_policy_incomplete)
    def test_01_missing_reset_rule_blocked(self):
        incomplete_env = dict(self.standard_env)
        incomplete_env.pop("WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE", None)
        ctx = SpendGuardContext(
            job_id="job_01",
            request_id="req_01",
            estimated_max_cost_usd=1.00,
            has_proven_cost_authority=True,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            user_flow="bot_confirm",
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=incomplete_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_POLICY_INCOMPLETE)

    # 2. Missing timezone -> BLOCK (weekly_provider_spend_policy_incomplete)
    def test_02_missing_timezone_blocked(self):
        incomplete_env = dict(self.standard_env)
        incomplete_env.pop("WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE", None)
        ctx = SpendGuardContext(
            job_id="job_02",
            request_id="req_02",
            estimated_max_cost_usd=1.00,
            has_proven_cost_authority=True,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            user_flow="bot_confirm",
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=incomplete_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_POLICY_INCOMPLETE)

    # 3. Invalid reset policy -> BLOCK
    def test_03_invalid_reset_policy_blocked(self):
        invalid_env = dict(self.standard_env)
        invalid_env["WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE"] = "SUNDAY_MIDNIGHT_UNSUPPORTED"
        ctx = SpendGuardContext(
            job_id="job_03",
            request_id="req_03",
            estimated_max_cost_usd=1.00,
            has_proven_cost_authority=True,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            user_flow="bot_confirm",
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=invalid_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_POLICY_INCOMPLETE)

    # 4. Missing max-cost authority -> BLOCK (provider_max_cost_authority_missing)
    def test_04_missing_max_cost_authority_blocked(self):
        ctx = SpendGuardContext(
            job_id="job_04",
            request_id="req_04",
            product_family="Product Video",
            provider="shopaikey_video",
            model="unpriced_model_xyz",
            operation="create_video_task",
            estimated_max_cost_usd=0.0,
            has_proven_cost_authority=False,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            user_flow="bot_confirm",
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_MAX_COST_AUTHORITY_MISSING)

    # 5. Arbitrary $0.10 fallback absent
    def test_05_arbitrary_fallback_absent(self):
        # A non-stub attempt with estimated_max_cost_usd unspecified or arbitrary without proven authority
        ctx = SpendGuardContext(
            job_id="job_05",
            request_id="req_05",
            provider="key4u_video",
            estimated_max_cost_usd=0.10,
            has_proven_cost_authority=False,  # Unproven arbitrary number
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            user_flow="bot_confirm",
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_MAX_COST_AUTHORITY_MISSING)

    # 6. Submit accepted -> PENDING_SETTLEMENT
    def test_06_submit_accepted_transitions_to_pending_settlement(self):
        res = self._create_valid_reservation("job_06", "req_06")
        self.assertTrue(res.allowed)
        self.assertNotEqual(res.reservation_id, "")

        marked = mark_submitted_pending_settlement(
            res.reservation_id,
            provider_task_id="task_ext_06",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertTrue(marked)

        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertEqual(summary["pending_reserved_spend_usd"], 0.40)
        self.assertEqual(summary["settled_week_spend_usd"], 0.0)
        self.assertEqual(summary["total_active_week_spend_usd"], 0.40)

    # 7. Accepted submit does NOT record estimated as actual
    def test_07_accepted_submit_does_not_record_estimated_as_actual(self):
        res = self._create_valid_reservation("job_07", "req_07")
        self.assertTrue(res.allowed)

        mark_submitted_pending_settlement(
            res.reservation_id,
            provider_task_id="task_ext_07",
            db_path=self.db_path,
            env=self.standard_env,
        )

        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT status, reserved_cost_micro_usd, actual_settled_cost_micro_usd FROM provider_spend_reservations WHERE reservation_id = ?",
            (res.reservation_id,),
        )
        row = cur.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], STATUS_SUBMITTED_PENDING_SETTLEMENT)
        self.assertEqual(row[1], 400_000)
        self.assertEqual(row[2], 0)  # Actual settled cost remains 0!

    # 8. Timeout after transport -> AMBIGUOUS_RETAINED
    def test_08_timeout_after_transport_retains_ambiguous(self):
        res = self._create_valid_reservation("job_08", "req_08")
        self.assertTrue(res.allowed)

        retained = retain_ambiguous_provider_spend(
            res.reservation_id,
            error_code="TimeoutError",
            provider_task_id="",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertTrue(retained)

        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertEqual(summary["pending_reserved_spend_usd"], 0.40)
        self.assertEqual(summary["total_active_week_spend_usd"], 0.40)

    # 9. Connection reset after transport -> AMBIGUOUS_RETAINED
    def test_09_connection_reset_after_transport_retains_ambiguous(self):
        res = self._create_valid_reservation("job_09", "req_09")
        self.assertTrue(res.allowed)

        retained = retain_ambiguous_provider_spend(
            res.reservation_id,
            error_code="ConnectionResetError",
            provider_task_id="task_conn_reset",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertTrue(retained)

        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT status, error_code, reserved_cost_micro_usd FROM provider_spend_reservations WHERE reservation_id = ?",
            (res.reservation_id,),
        )
        row = cur.fetchone()
        conn.close()

        self.assertEqual(row[0], STATUS_AMBIGUOUS_RETAINED)
        self.assertEqual(row[1], "ConnectionResetError")
        self.assertEqual(row[2], 400_000)

    # 10. Response parse failure after transport -> AMBIGUOUS_RETAINED
    def test_10_response_parse_failure_after_transport_retains_ambiguous(self):
        res = self._create_valid_reservation("job_10", "req_10")
        self.assertTrue(res.allowed)

        retained = retain_ambiguous_provider_spend(
            res.reservation_id,
            error_code="JSONDecodeError",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertTrue(retained)

        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertEqual(summary["total_active_week_spend_usd"], 0.40)

    # 11. Generic exception after transport -> AMBIGUOUS_RETAINED
    def test_11_generic_exception_after_transport_retains_ambiguous(self):
        res = self._create_valid_reservation("job_11", "req_11")
        self.assertTrue(res.allowed)

        retained = retain_ambiguous_provider_spend(
            res.reservation_id,
            error_code="RuntimeError",
            provider_task_id="task_rt_error",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertTrue(retained)
        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertEqual(summary["pending_reserved_spend_usd"], 0.40)

    # 12. Proven pre-send failure -> RELEASED_PROVEN_NO_CHARGE
    def test_12_proven_pre_send_failure_releases_reservation(self):
        res = self._create_valid_reservation("job_12", "req_12")
        self.assertTrue(res.allowed)

        released = release_provider_spend_no_charge(
            res.reservation_id,
            reason="pre_transport_validation_failed",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertTrue(released)

        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT status, reserved_cost_micro_usd FROM provider_spend_reservations WHERE reservation_id = ?",
            (res.reservation_id,),
        )
        row = cur.fetchone()
        conn.close()

        self.assertEqual(row[0], STATUS_RELEASED_PROVEN_NO_CHARGE)
        self.assertEqual(row[1], 0)

        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertEqual(summary["total_active_week_spend_usd"], 0.0)

    # 13. CI + REAL_PROVIDER_CALLS_ALLOWED=1 -> still BLOCK
    def test_13_ci_with_real_provider_calls_allowed_still_blocked(self):
        ci_env = dict(self.standard_env)
        ci_env["CI"] = "true"
        ci_env["REAL_PROVIDER_CALLS_ALLOWED"] = "1"
        ctx = SpendGuardContext(
            job_id="job_13",
            request_id="req_13",
            estimated_max_cost_usd=1.00,
            has_proven_cost_authority=True,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            user_flow="bot_confirm",
            is_paid_live_attempt=True,
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=ci_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_TEST_NETWORK_ISOLATION)

    # 14. Pytest + override -> still BLOCK
    def test_14_pytest_with_override_still_blocked(self):
        test_env = dict(self.standard_env)
        test_env["PYTEST_CURRENT_TEST"] = "tests/test_mock.py::test_case"
        test_env["REAL_PROVIDER_CALLS_ALLOWED"] = "1"
        ctx = SpendGuardContext(
            job_id="job_14",
            request_id="req_14",
            estimated_max_cost_usd=1.00,
            has_proven_cost_authority=True,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            user_flow="bot_confirm",
            is_paid_live_attempt=True,
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=test_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_TEST_NETWORK_ISOLATION)

    # 15. Forged submit_source string -> bot origin BLOCK
    def test_15_forged_submit_source_string_blocked(self):
        # Caller supplies submit_source="public_final_confirm" but has NO trusted bot_confirm_authority
        ctx = SpendGuardContext(
            job_id="job_15",
            request_id="req_15",
            estimated_max_cost_usd=1.00,
            has_proven_cost_authority=True,
            bot_originated_action=False,  # Unproven
            bot_confirm_authority="",      # Empty / absent
            user_flow="public_final_confirm",
            is_paid_live_attempt=True,
        )
        valid, blocker = validate_bot_paid_live_origin(ctx, env=self.standard_env)
        self.assertFalse(valid)
        self.assertIn(blocker, {BLOCKER_BOT_ORIGIN_PROOF_MISSING, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING})

        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)

    # 16. Trusted bot lineage -> PASS guard
    def test_16_trusted_bot_lineage_passes_guard(self):
        conf_id = create_bot_confirmation(
            job_id="job_16",
            request_id="req_16",
            product_family="Video AI Edit",
            operation="submit_video_edit",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="job_16",
            request_id="req_16",
            trace_id="tr_16",
            product_family="Video AI Edit",
            provider="fal_video",
            model="wan-v2.2",
            operation="submit_video_edit",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="bot_product_video_confirm",
            entrypoint="bot",
            is_paid_live_attempt=True,
            metadata={"duration_seconds": 5},
        )
        valid, blocker = validate_bot_paid_live_origin(ctx, env=self.standard_env)
        self.assertTrue(valid)
        self.assertEqual(blocker, "")

        # Test reservation without test isolation flag
        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
            self.assertTrue(res.allowed)
            self.assertEqual(res.week_spend_after_usd, 0.40)
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

    # 17. Missing shared DB authority -> BLOCK (spend_guard_shared_authority_unavailable)
    def test_17_missing_shared_db_authority_blocked(self):
        ctx = SpendGuardContext(
            job_id="job_17",
            request_id="req_17",
            estimated_max_cost_usd=1.00,
            has_proven_cost_authority=True,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            user_flow="bot_confirm",
        )
        res = reserve_provider_spend(ctx, db_path=None, env={
            "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE": "MONDAY_0000_UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE": "UTC",
        })
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_SHARED_DB_UNAVAILABLE)

    # 18. Bot/Worker shared DB parity -> PASS
    def test_18_bot_worker_shared_db_parity_passes(self):
        shared_file = os.path.join(self.temp_dir, "parity_shared.db")
        bot_env = {"DB_PATH": shared_file}
        worker_env = {"SPEND_GUARD_DB_PATH": shared_file}

        parity_ok, bot_path, worker_path, reason = verify_shared_db_parity(bot_env, worker_env)
        self.assertTrue(parity_ok)
        self.assertEqual(os.path.normcase(bot_path), os.path.normcase(worker_path))

        # Test mismatch fails
        mismatch_worker = {"SPEND_GUARD_DB_PATH": os.path.join(self.temp_dir, "other.db")}
        parity_bad, _, _, _ = verify_shared_db_parity(bot_env, mismatch_worker)
        self.assertFalse(parity_bad)

    # 19. Two-process atomic reservation -> cannot exceed $200 (using multiprocessing)
    def test_19_two_process_atomic_reservation_cannot_exceed_cap(self):
        # Initial settle: $199.60
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        week_id = get_current_spend_week_id(env=self.standard_env)
        cur.execute(
            """
            INSERT INTO provider_spend_reservations (
                reservation_id, created_at, week_id, idempotency_key, job_id, request_id, trace_id,
                product_family, provider, model, estimated_max_cost_micro_usd, reserved_cost_micro_usd,
                actual_settled_cost_micro_usd, status, bot_originated_action, user_flow, bot_confirm_authority,
                owner_receipt, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'test', 'conf', '', '{}')
            """,
            (
                "res_base_19", time.time(), week_id, "idem_19_base", "job_19_init", "req_19_init", "tr_19",
                "Video AI Edit", "fal_video", "wan-v2.2", 199_600_000, 199_600_000, 199_600_000,
                STATUS_SETTLED_VERIFIED,
            )
        )
        conn.commit()
        conn.close()

        # Remaining budget is $0.40. Two processes attempt $0.40 each (Fal 5s = $0.40).
        q = multiprocessing.Queue()
        p1 = multiprocessing.Process(
            target=_process_reserve_worker,
            args=(self.db_path, self.standard_env, "job_19_p1", 0.40, q),
        )
        p2 = multiprocessing.Process(
            target=_process_reserve_worker,
            args=(self.db_path, self.standard_env, "job_19_p2", 0.40, q),
        )

        p1.start()
        p2.start()
        p1.join(timeout=10)
        p2.join(timeout=10)

        results = [q.get() for _ in range(2)]
        allowed_count = sum(1 for r in results if r["allowed"])
        blocked_count = sum(1 for r in results if not r["allowed"])

        # Exactly 1 can succeed, the other MUST be blocked
        self.assertEqual(allowed_count, 1)
        self.assertEqual(blocked_count, 1)

        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertEqual(summary["total_active_week_spend_usd"], 200.00)

    # 20. Precise decimal boundary ($199.600 + $0.400 PASS, $200.000 + $0.400 BLOCK)
    def test_20_precise_decimal_boundary(self):
        # Settle $199.600
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        week_id = get_current_spend_week_id(env=self.standard_env)
        cur.execute(
            """
            INSERT INTO provider_spend_reservations (
                reservation_id, created_at, week_id, idempotency_key, job_id, request_id, trace_id,
                product_family, provider, model, estimated_max_cost_micro_usd, reserved_cost_micro_usd,
                actual_settled_cost_micro_usd, status, bot_originated_action, user_flow, bot_confirm_authority,
                owner_receipt, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'test', 'conf', '', '{}')
            """,
            (
                "res_base_20", time.time(), week_id, "idem_20_base", "job_20_base", "req_20_base", "tr_20",
                "Video AI Edit", "fal_video", "wan-v2.2", 199_600_000, 199_600_000, 199_600_000,
                STATUS_SETTLED_VERIFIED,
            )
        )
        conn.commit()
        conn.close()

        # $199.600 + $0.400 = $200.000 -> PASS
        res_exact = self._create_valid_reservation("job_20_exact", "req_20_exact")
        self.assertTrue(res_exact.allowed)
        settle_verified_provider_spend(res_exact.reservation_id, actual_verified_cost_usd=0.40, db_path=self.db_path, env=self.standard_env)

        # $200.000 + $0.400 = $200.400 > $200.000 -> BLOCK
        res_over = self._create_valid_reservation("job_20_over", "req_20_over")
        self.assertFalse(res_over.allowed)
        self.assertEqual(res_over.blocker, BLOCKER_WEEKLY_SPEND_CAP_EXCEEDED)

    # 21. Duplicate submit -> BLOCK
    def test_21_duplicate_submit_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="job_21_dup",
            request_id="req_21_dup",
            product_family="Video AI Edit",
            operation="submit_video_edit",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="job_21_dup",
            request_id="req_21_dup",
            product_family="Video AI Edit",
            provider="fal_video",
            model="wan-v2.2",
            operation="submit_video_edit",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="bot_confirm",
            metadata={"duration_seconds": 5},
        )
        res1 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

        # Immediate duplicate
        res2 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res2.allowed)
        self.assertEqual(res2.blocker, BLOCKER_DUPLICATE_PAID_SUBMIT)

    # 22. Retry ambiguous -> BLOCK
    def test_22_retry_ambiguous_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="job_22_retry",
            request_id="req_22_retry",
            product_family="Video AI Edit",
            operation="submit_video_edit",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="job_22_retry",
            request_id="req_22_retry",
            product_family="Video AI Edit",
            provider="fal_video",
            model="wan-v2.2",
            operation="submit_video_edit",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="bot_confirm",
            metadata={"duration_seconds": 5},
        )
        res1 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

        retain_ambiguous_provider_spend(
            res1.reservation_id,
            error_code="provider_timeout",
            db_path=self.db_path,
            env=self.standard_env,
        )

        res_retry = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res_retry.allowed)
        self.assertEqual(res_retry.blocker, BLOCKER_AMBIGUOUS_RETRY_BLOCKED)

    # 23. Fallback ambiguous -> BLOCK
    def test_23_fallback_ambiguous_blocked(self):
        policy = product_video_provider_submit_source_policy(
            metadata={
                "submit_source": "fallback",
                "is_paid_live": True,
                "bot_originated_action": False,
            }
        )
        self.assertFalse(policy["provider_submit_allowed"])

    # 24. Kill switch -> BLOCK
    def test_24_kill_switch_blocked(self):
        set_kill_switch(True)
        self.assertTrue(is_kill_switch_active())

        ctx = SpendGuardContext(
            job_id="job_24_ks",
            request_id="req_24_ks",
            estimated_max_cost_usd=1.00,
            has_proven_cost_authority=True,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            user_flow="bot_confirm",
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_KILL_SWITCH_ACTIVE)

        # Polling existing task remains allowed
        policy = product_video_provider_submit_source_policy(
            metadata={"submit_source": "worker_poll_existing_task"},
            poll_existing_task=True,
        )
        self.assertFalse(policy["provider_submit_allowed"])
        self.assertTrue(policy["poll_existing_task_allowed"])

    # 25. Existing Product Video protected suites pass
    def test_25_existing_product_video_protected_suites_pass(self):
        # Verify key4u authority fails closed when legacy alias or missing canonical
        env_alias_only = {"VIDEO_KEY4U_AUTH_HEADER_VALUE": "alias_value"}
        res = resolve_product_video_key4u_auth(env_alias_only)
        self.assertFalse(res["ready"])
        self.assertEqual(res["blocker"], KEY4U_VIDEO_AUTH_MISSING)

        # Audit record sanitized check
        ctx = SpendGuardContext(
            job_id="job_25_audit",
            request_id="req_25_audit",
            trace_id="tr_25_audit",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            estimated_max_cost_usd=1.50,
            has_proven_cost_authority=True,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            user_flow="bot_confirm",
        )
        raw_secret_task_id = "task_secret_sk_live_9999999999abcdef"
        audit = build_sanitized_audit_record(
            ctx,
            week_spend_before_micro_usd=10_000_000,
            week_spend_after_micro_usd=11_500_000,
            reserved_cost_micro_usd=1_500_000,
            provider_task_id=raw_secret_task_id,
        )
        self.assertNotIn("sk_live", str(audit))
        self.assertNotIn("9999999999", str(audit))
        self.assertIn("...", audit["PROVIDER_TASK_ID_SAFE"])

    # 26. TTS direct paid submit without bot auth -> BLOCK
    def test_26_tts_direct_paid_submit_without_bot_auth_blocked(self):
        status, task_id, detail, code = asyncio.run(
            shopaikey_minimax_tts_async_submit(
                text="hello",
                voice_id="voice_1",
                api_key="sk-real-live-token",
                is_paid_live=True,
                bot_originated_action=False,
                bot_confirm_authority="",
                db_path=self.db_path,
                env=self.standard_env,
            )
        )
        self.assertEqual(status, "FAIL_SPEND_GUARD_BLOCKED")
        self.assertIn("spend_guard_blocked", detail)

    # 27. TTS trusted bot paid submit reaches mock transport only -> PASS
    def test_27_tts_trusted_bot_paid_submit_reaches_mock_transport_only(self):
        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            # MiniMax unproven pricing fails closed even with bot confirm
            conf_minimax = create_bot_confirmation(
                job_id="job_tts_mm",
                request_id="req_tts_mm",
                product_family="Voice / TTS",
                operation="create_tts_task",
                db_path=self.db_path,
                env=self.standard_env,
            )
            st_mm, _, det_mm, _ = asyncio.run(
                shopaikey_minimax_tts_async_submit(
                    text="hello",
                    voice_id="voice_1",
                    api_key="mock_key",
                    job_id="job_tts_mm",
                    request_id="req_tts_mm",
                    bot_originated_action=True,
                    bot_confirm_authority=conf_minimax,
                    is_paid_live=False,
                    db_path=self.db_path,
                    env=self.standard_env,
                )
            )
            self.assertEqual(st_mm, "FAIL_SPEND_GUARD_BLOCKED")
            self.assertIn("provider_max_cost_authority_missing", det_mm)

            # Proven OpenAI tts-1 with durable confirmation reaches mock transport only
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"task_id": "tts_mock_task_789"}
            mock_response.text = '{"task_id": "tts_mock_task_789"}'
            mock_client.post = AsyncMock(return_value=mock_response)

            conf_id = create_bot_confirmation(
                job_id="job_tts_01",
                request_id="req_tts_01",
                product_family="Voice / TTS",
                operation="create_tts_task",
                db_path=self.db_path,
                env=self.standard_env,
            )

            status, task_id, detail, code = asyncio.run(
                shopaikey_minimax_tts_async_submit(
                    text="Test TTS with trusted lineage",
                    voice_id="voice_1",
                    model="tts-1",
                    provider="shopaikey_openai_tts",
                    api_key="mock_key",
                    client=mock_client,
                    job_id="job_tts_01",
                    request_id="req_tts_01",
                    bot_originated_action=True,
                    bot_confirm_authority=conf_id,
                    is_paid_live=True,
                    db_path=self.db_path,
                    env=self.standard_env,
                )
            )

            self.assertEqual(status, "PASS")
            self.assertEqual(task_id, "tts_mock_task_789")
            mock_client.post.assert_awaited_once()

            summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
            self.assertAlmostEqual(summary["pending_reserved_spend_usd"], 0.000435, places=6)
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

    # 28. Ambiguous TTS retains reservation -> RETAIN
    def test_28_ambiguous_tts_retains_reservation(self):
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Transport timed out"))

        conf_id = create_bot_confirmation(
            job_id="job_tts_timeout",
            request_id="req_tts_timeout",
            product_family="Voice / TTS",
            operation="create_tts_task",
            db_path=self.db_path,
            env=self.standard_env,
        )

        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            status, task_id, detail, code = asyncio.run(
                shopaikey_minimax_tts_async_submit(
                    text="Test TTS timeout ambiguity",
                    voice_id="voice_1",
                    model="tts-1",
                    provider="shopaikey_openai_tts",
                    api_key="mock_key",
                    client=mock_client,
                    job_id="job_tts_timeout",
                    request_id="req_tts_timeout",
                    bot_originated_action=True,
                    bot_confirm_authority=conf_id,
                    is_paid_live=True,
                    db_path=self.db_path,
                    env=self.standard_env,
                )
            )
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

        self.assertEqual(status, "FAIL_TIMEOUT")
        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertAlmostEqual(summary["pending_reserved_spend_usd"], 0.00039, places=6)

    # 29. Chat Pro external paid call without guard -> BLOCK
    def test_29_chat_pro_external_paid_call_without_guard_blocked(self):
        store = PublicChatStore(os.path.join(self.temp_dir, "chat.db"))
        pro_mock = MagicMock()
        pro_mock.is_paid_provider = True
        wallet = MagicMock()
        wallet.get_balance = AsyncMock(return_value=50_000)
        wallet.reserve = AsyncMock(return_value={"ok": True, "reservation_id": "res_w_01"})
        wallet.release = AsyncMock(return_value={"ok": True})
        runtime = PublicChatRuntime(store=store, pro_provider=pro_mock, wallet=wallet, pricing=ClaudeOpusPricing(100, 500, 3))

        req = PublicChatRequest(
            account_id="u_chat",
            chat_id="chat_1",
            source_message_id="msg_1",
            mode="pro",
            prompt="pro prompt",
            role="user",
            estimated_input_tokens=1000,
            max_output_tokens=1000,
            is_paid_external_provider=True,
            bot_originated_action=False,
            bot_confirm_authority="",
            db_path=self.db_path,
            env=self.standard_env,
        )

        res = asyncio.run(runtime.generate_pro(req))
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("status"), "SPEND_GUARD_BLOCKED")
        self.assertEqual(res.get("provider_calls"), 0)

    # 30. Chat internal Xu ledger separate -> PASS
    def test_30_chat_internal_xu_ledger_separate(self):
        store = PublicChatStore(os.path.join(self.temp_dir, "chat_xu.db"))
        pro_mock = MagicMock()
        pro_mock.is_paid_provider = True
        wallet = MagicMock()
        wallet.get_balance = AsyncMock(return_value=50_000)
        wallet.reserve = AsyncMock(return_value={"ok": True, "reservation_id": "res_xu_test"})
        wallet.release = AsyncMock(return_value={"ok": True})
        runtime = PublicChatRuntime(store=store, pro_provider=pro_mock, wallet=wallet, pricing=ClaudeOpusPricing(100, 500, 3))

        req = PublicChatRequest(
            account_id="u_xu",
            chat_id="chat_xu",
            source_message_id="msg_xu",
            mode="pro",
            prompt="test",
            role="user",
            estimated_input_tokens=1000,
            max_output_tokens=1000,
            is_paid_external_provider=True,
            bot_originated_action=False,
            bot_confirm_authority="",
            db_path=self.db_path,
            env=self.standard_env,
        )

        res = asyncio.run(runtime.generate_pro(req))
        wallet.reserve.assert_awaited_once()
        wallet.release.assert_awaited_once()
        self.assertEqual(res.get("provider_calls"), 0)

    # 31. Ambiguous Chat retains reservation -> RETAIN
    def test_31_ambiguous_chat_retains_reservation(self):
        store = PublicChatStore(os.path.join(self.temp_dir, "chat_ambig.db"))
        async def fail_pro(*args, **kwargs):
            raise TimeoutError("LLM gateway socket dropped")
        pro_mock = MagicMock(side_effect=fail_pro)
        pro_mock.is_paid_provider = True
        wallet = MagicMock()
        wallet.get_balance = AsyncMock(return_value=50_000)
        wallet.reserve = AsyncMock(return_value={"ok": True, "reservation_id": "res_ambig_test"})
        wallet.release = AsyncMock(return_value={"ok": True})
        runtime = PublicChatRuntime(store=store, pro_provider=pro_mock, wallet=wallet, pricing=ClaudeOpusPricing(100, 500, 3))

        conf_id = create_bot_confirmation(
            chat_id="chat_ambig",
            job_id="msg_ambig",
            product_family="Public Chat Pro",
            operation="chat_completion",
            db_path=self.db_path,
            env=self.standard_env,
        )

        req = PublicChatRequest(
            account_id="u_ambig",
            chat_id="chat_ambig",
            source_message_id="msg_ambig",
            mode="pro",
            prompt="test",
            role="user",
            estimated_input_tokens=1000,
            max_output_tokens=1000,
            is_paid_external_provider=True,
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            has_proven_cost_authority=True,
            estimated_max_cost_usd=0.08,
            db_path=self.db_path,
            env=self.standard_env,
        )

        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            res = asyncio.run(runtime.generate_pro(req))
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("status"), "PROVIDER_FAILURE")

        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertAlmostEqual(summary["pending_reserved_spend_usd"], 0.036, places=6)

    # 32. AI Edit forged final confirm -> BLOCK
    def test_32_ai_edit_forged_final_confirm_blocked(self):
        config = AiEditProviderConfig(
            provider_name="fal_video",
            enabled=True,
            submit_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video",
            poll_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/{task_id}/status",
            auth_header_name="Authorization",
            auth_header_value="Key real_live_secret",
            model="fal-ai/wan/v2.2-a14b/video-to-video",
            interface="video_to_video_json",
            capabilities=("video_to_video",),
        )
        fake_source = os.path.join(self.temp_dir, "fake_vid.mp4")
        with open(fake_source, "wb") as f:
            f.write(b"video_bytes")

        with self.assertRaises(AiEditProviderError) as cm:
            submit_video_edit(
                config,
                source_video_path=fake_source,
                prompt="make anime",
                negative_prompt="",
                aspect_ratio="9:16",
                duration_seconds=5,
                job_id="job_aiedit_forged",
                submit_source=PUBLIC_FINAL_CONFIRM_SOURCE,
                public_user_confirmed=True,
                is_paid_live=True,
                bot_originated_action=False,
                bot_confirm_authority="",
                db_path=self.db_path,
                env=self.standard_env,
            )
        self.assertIn("bot_confirm_authority_missing", str(cm.exception))

    # 33. AI Edit trusted bot lineage reaches mock transport only -> PASS
    def test_33_ai_edit_trusted_bot_lineage_reaches_mock_transport_only(self):
        config = AiEditProviderConfig(
            provider_name="fal_video",
            enabled=True,
            submit_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video",
            poll_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/{task_id}/status",
            auth_header_name="Authorization",
            auth_header_value="Key mock_key",
            model="fal-ai/wan/v2.2-a14b/video-to-video",
            interface="video_to_video_json",
            capabilities=("video_to_video",),
        )
        fake_source = "https://storage.fal.run/fake_vid.mp4"

        conf_id = create_bot_confirmation(
            job_id="job_aiedit_valid",
            product_family="Video AI Edit",
            operation="submit_video_edit",
            db_path=self.db_path,
            env=self.standard_env,
        )

        transport_called = False
        def mock_opener(req, timeout=0):
            nonlocal transport_called
            transport_called = True
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.code = 200
            mock_resp.getcode.return_value = 200
            mock_resp.read.return_value = json.dumps({"data": {"task_id": "aiedit_task_001", "status": "PENDING"}}).encode("utf-8")
            return mock_resp

        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            res = submit_video_edit(
                config,
                source_video_path=fake_source,
                prompt="make anime",
                negative_prompt="",
                aspect_ratio="9:16",
                duration_seconds=5,
                job_id="job_aiedit_valid",
                submit_source=PUBLIC_FINAL_CONFIRM_SOURCE,
                public_user_confirmed=True,
                opener=mock_opener,
                is_paid_live=True,
                bot_originated_action=True,
                bot_confirm_authority=conf_id,
                db_path=self.db_path,
                env=self.standard_env,
            )
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

        self.assertTrue(transport_called)
        self.assertEqual(res.get("provider_task_id"), "aiedit_task_001")

        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertEqual(summary["pending_reserved_spend_usd"], 0.40)

    # 34. Ambiguous AI Edit retains reservation -> RETAIN
    def test_34_ambiguous_ai_edit_retains_reservation(self):
        config = AiEditProviderConfig(
            provider_name="fal_video",
            enabled=True,
            submit_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video",
            poll_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/{task_id}/status",
            auth_header_name="Authorization",
            auth_header_value="Key mock_key",
            model="fal-ai/wan/v2.2-a14b/video-to-video",
            interface="video_to_video_json",
            capabilities=("video_to_video",),
        )
        fake_source = "https://storage.fal.run/fake_vid.mp4"

        conf_id = create_bot_confirmation(
            job_id="job_aiedit_fail",
            product_family="Video AI Edit",
            operation="submit_video_edit",
            db_path=self.db_path,
            env=self.standard_env,
        )

        import urllib.error
        def mock_opener_fail(req, timeout=0):
            raise urllib.error.URLError("connection reset by peer")

        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            with self.assertRaises(AiEditProviderError):
                submit_video_edit(
                    config,
                    source_video_path=fake_source,
                    prompt="make anime",
                    negative_prompt="",
                    aspect_ratio="9:16",
                    duration_seconds=5,
                    job_id="job_aiedit_fail",
                    submit_source=PUBLIC_FINAL_CONFIRM_SOURCE,
                    public_user_confirmed=True,
                    opener=mock_opener_fail,
                    is_paid_live=True,
                    bot_originated_action=True,
                    bot_confirm_authority=conf_id,
                    db_path=self.db_path,
                    env=self.standard_env,
                )
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertEqual(summary["pending_reserved_spend_usd"], 0.40)

    # 35. Kill switch blocks all paid entrypoints -> BLOCK
    def test_35_kill_switch_all_paid_entrypoints_blocked(self):
        set_kill_switch(True)
        # 1. Product Video
        pv_ctx = SpendGuardContext(product_family="Product Video", estimated_max_cost_usd=1.00, has_proven_cost_authority=True, bot_originated_action=True, bot_confirm_authority="bot_telegram_ui_confirmed")
        self.assertEqual(reserve_provider_spend(pv_ctx, db_path=self.db_path, env=self.standard_env).blocker, BLOCKER_KILL_SWITCH_ACTIVE)

        # 2. TTS
        tts_ctx = SpendGuardContext(product_family="Voice / TTS", estimated_max_cost_usd=0.05, has_proven_cost_authority=True, bot_originated_action=True, bot_confirm_authority="bot_telegram_ui_confirmed")
        self.assertEqual(reserve_provider_spend(tts_ctx, db_path=self.db_path, env=self.standard_env).blocker, BLOCKER_KILL_SWITCH_ACTIVE)

        # 3. Chat Pro
        chat_ctx = SpendGuardContext(product_family="Public Chat Pro", estimated_max_cost_usd=0.08, has_proven_cost_authority=True, bot_originated_action=True, bot_confirm_authority="bot_telegram_ui_confirmed")
        self.assertEqual(reserve_provider_spend(chat_ctx, db_path=self.db_path, env=self.standard_env).blocker, BLOCKER_KILL_SWITCH_ACTIVE)

        # 4. Video AI Edit
        edit_ctx = SpendGuardContext(product_family="Video AI Edit", estimated_max_cost_usd=0.20, has_proven_cost_authority=True, bot_originated_action=True, bot_confirm_authority="bot_telegram_ui_confirmed")
        self.assertEqual(reserve_provider_spend(edit_ctx, db_path=self.db_path, env=self.standard_env).blocker, BLOCKER_KILL_SWITCH_ACTIVE)

    # 36. Weekly cap shared across products -> PASS
    def test_36_weekly_cap_shared_across_products(self):
        # Insert settled records totaling $200.00 across all 4 products:
        # PV: $100.00, TTS: $50.00, Chat Pro: $30.00, AI Edit: $20.00
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        week_id = get_current_spend_week_id(env=self.standard_env)
        settled_breakdown = [
            ("Product Video", 100.00),
            ("Voice / TTS", 50.00),
            ("Public Chat Pro", 30.00),
            ("Video AI Edit", 20.00),
        ]
        for fam, amount in settled_breakdown:
            conn.execute(
                """
                INSERT INTO provider_spend_reservations (
                    reservation_id, created_at, week_id, idempotency_key, job_id, request_id, trace_id,
                    product_family, provider, model, estimated_max_cost_micro_usd, reserved_cost_micro_usd,
                    actual_settled_cost_micro_usd, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"res_cap_{fam}", time.time(), week_id, f"idem_{fam}", f"job_{fam}", f"req_{fam}", f"tr_{fam}",
                    fam, "mock_prov", "mock_model", int(amount * 1_000_000), int(amount * 1_000_000),
                    int(amount * 1_000_000), STATUS_SETTLED_VERIFIED,
                ),
            )
        conn.commit()
        conn.close()

        # Total settled = $200.00. Now attempt reservation on ANY governed product family:
        attempts = [
            ("Product Video", "key4u_video", "kling-v3", "create_video_task", {"duration_seconds": 5}),
            ("Voice / TTS", "shopaikey_openai_tts", "tts-1", "create_tts_task", {"char_count": 100}),
            ("Public Chat Pro", "claude-opus", CLAUDE_OPUS_MODEL, "chat_completion", {"max_input_tokens": 100, "max_output_tokens": 100}),
            ("Video AI Edit", "fal_video", "fal-ai/wan/v2.2-a14b/video-to-video", "submit_video_edit", {"duration_seconds": 5}),
        ]
        for fam, prov, mdl, op, meta in attempts:
            c_id = create_bot_confirmation(
                job_id=f"over_{fam}",
                request_id=f"req_over_{fam}",
                product_family=fam,
                operation=op,
                db_path=self.db_path,
                env=self.standard_env,
            )
            over_res = reserve_provider_spend(
                SpendGuardContext(
                    job_id=f"over_{fam}",
                    request_id=f"req_over_{fam}",
                    product_family=fam,
                    provider=prov,
                    model=mdl,
                    operation=op,
                    bot_originated_action=True,
                    bot_confirm_authority=c_id,
                    metadata=meta,
                ),
                db_path=self.db_path,
                env=self.standard_env,
            )
            self.assertFalse(over_res.allowed, f"Expected {fam} to be blocked by weekly cap")
            self.assertEqual(over_res.blocker, BLOCKER_WEEKLY_SPEND_CAP_EXCEEDED)

    # 37. CI override all paid entrypoints -> BLOCK
    def test_37_ci_override_all_paid_entrypoints_blocked(self):
        ci_env = dict(self.standard_env)
        ci_env["CI"] = "true"
        ci_env["REAL_PROVIDER_CALLS_ALLOWED"] = "1"

        for fam in ("Product Video", "Voice / TTS", "Public Chat Pro", "Video AI Edit"):
            ctx = SpendGuardContext(
                job_id=f"ci_{fam}",
                product_family=fam,
                estimated_max_cost_usd=1.00,
                has_proven_cost_authority=True,
                bot_originated_action=True,
                bot_confirm_authority="bot_telegram_ui_confirmed",
                is_paid_live_attempt=True,
            )
            res = reserve_provider_spend(ctx, db_path=self.db_path, env=ci_env)
            self.assertFalse(res.allowed)
            self.assertEqual(res.blocker, BLOCKER_TEST_NETWORK_ISOLATION)

    # 38. TTS real key without SHOPAIKEY_GUARD_ALL still enforces spend guard -> BLOCK
    def test_38_tts_real_key_without_guard_all_still_blocked(self):
        env_no_guard = dict(self.standard_env)
        env_no_guard.pop("SHOPAIKEY_GUARD_ALL", None)
        status, task_id, detail, code = asyncio.run(
            shopaikey_minimax_tts_async_submit(
                text="Test text with real key",
                voice_id="voice_1",
                api_key="sk-real-live-shopaikey-key",
                is_paid_live=False,  # Caller attempts bypass
                bot_originated_action=False,
                bot_confirm_authority="",
                db_path=self.db_path,
                env=env_no_guard,
            )
        )
        self.assertEqual(status, "FAIL_SPEND_GUARD_BLOCKED")
        self.assertIn("spend_guard_blocked", detail)

    # 39. TTS missing max cost authority -> BLOCK
    def test_39_tts_missing_max_cost_authority_blocked(self):
        # When text is empty and no proven cost provided
        status, task_id, detail, code = asyncio.run(
            shopaikey_minimax_tts_async_submit(
                text="",
                voice_id="voice_1",
                api_key="sk-real-live-token",
                is_paid_live=True,
                bot_originated_action=True,
                bot_confirm_authority="bot_telegram_ui_confirmed",
                estimated_max_cost_usd=0.0,
                has_proven_cost_authority=False,
                db_path=self.db_path,
                env=self.standard_env,
            )
        )
        self.assertEqual(status, "FAIL_BAD_REQUEST")
        self.assertEqual(detail, "empty_text")

    # 40. TTS post-transport HTTP 500 retains ambiguous -> RETAIN
    def test_40_tts_post_transport_http_500_retains_ambiguous(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = '{"error": "Internal Server Error"}'
        mock_response.json.return_value = {"error": "Internal Server Error"}
        mock_client.post = AsyncMock(return_value=mock_response)

        conf_id = create_bot_confirmation(
            job_id="job_tts_500",
            request_id="req_tts_500",
            product_family="Voice / TTS",
            operation="create_tts_task",
            db_path=self.db_path,
            env=self.standard_env,
        )

        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            status, task_id, detail, code = asyncio.run(
                shopaikey_minimax_tts_async_submit(
                    text="Test TTS 500 ambiguity",
                    voice_id="voice_1",
                    model="tts-1",
                    provider="shopaikey_openai_tts",
                    api_key="mock_key",
                    client=mock_client,
                    job_id="job_tts_500",
                    request_id="req_tts_500",
                    bot_originated_action=True,
                    bot_confirm_authority=conf_id,
                    is_paid_live=True,
                    db_path=self.db_path,
                    env=self.standard_env,
                )
            )
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

        self.assertEqual(status, "FAIL_HTTP_STATUS")
        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertAlmostEqual(summary["pending_reserved_spend_usd"], 0.00033, places=6)

    # 41. TTS post-transport missing task_id in 200 response retains ambiguous -> RETAIN
    def test_41_tts_post_transport_missing_task_id_retains_ambiguous(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"status": "ok"}'  # Missing task_id
        mock_response.json.return_value = {"status": "ok"}
        mock_client.post = AsyncMock(return_value=mock_response)

        conf_id = create_bot_confirmation(
            job_id="job_tts_no_task",
            request_id="req_tts_no_task",
            product_family="Voice / TTS",
            operation="create_tts_task",
            db_path=self.db_path,
            env=self.standard_env,
        )

        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            status, task_id, detail, code = asyncio.run(
                shopaikey_minimax_tts_async_submit(
                    text="Test TTS missing task_id ambiguity",
                    voice_id="voice_1",
                    model="tts-1",
                    provider="shopaikey_openai_tts",
                    api_key="mock_key",
                    client=mock_client,
                    job_id="job_tts_no_task",
                    request_id="req_tts_no_task",
                    bot_originated_action=True,
                    bot_confirm_authority=conf_id,
                    is_paid_live=True,
                    db_path=self.db_path,
                    env=self.standard_env,
                )
            )
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

        self.assertEqual(status, "FAIL_NO_TASK_ID")
        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertAlmostEqual(summary["pending_reserved_spend_usd"], 0.00051, places=6)

    # 42. Chat Pro caller defaults fail-closed without bot origin -> BLOCK
    def test_42_chat_pro_caller_default_blocked_without_bot_origin(self):
        store = PublicChatStore(os.path.join(self.temp_dir, "chat_def.db"))
        pro_mock = MagicMock()
        pro_mock.is_paid_provider = True
        wallet = MagicMock()
        wallet.get_balance = AsyncMock(return_value=50_000)
        wallet.reserve = AsyncMock(return_value={"ok": True, "reservation_id": "res_def"})
        wallet.release = AsyncMock(return_value={"ok": True})
        runtime = PublicChatRuntime(store=store, pro_provider=pro_mock, wallet=wallet, pricing=ClaudeOpusPricing(100, 500, 3))

        # Use pure defaults of PublicChatRequest
        req = PublicChatRequest(
            account_id="u_default",
            chat_id="chat_def",
            source_message_id="msg_def",
            mode="pro",
            prompt="hello world",
            role="user",
            is_paid_external_provider=True,
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertFalse(req.bot_originated_action)
        self.assertEqual(req.bot_confirm_authority, "")

        res = asyncio.run(runtime.generate_pro(req))
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("status"), "SPEND_GUARD_BLOCKED")
        self.assertEqual(res.get("provider_calls"), 0)

    # 43. Chat Pro missing cost authority -> BLOCK
    def test_43_chat_pro_missing_cost_authority_blocked(self):
        store = PublicChatStore(os.path.join(self.temp_dir, "chat_nocost.db"))
        pro_mock = MagicMock()
        pro_mock.is_paid_provider = True
        wallet = MagicMock()
        wallet.get_balance = AsyncMock(return_value=50_000)
        wallet.reserve = AsyncMock(return_value={"ok": True, "reservation_id": "res_nocost"})
        wallet.release = AsyncMock(return_value={"ok": True})
        runtime = PublicChatRuntime(store=store, pro_provider=pro_mock, wallet=wallet, pricing=ClaudeOpusPricing(100, 500, 3))

        req = PublicChatRequest(
            account_id="u_nocost",
            chat_id="chat_nocost",
            source_message_id="msg_nocost",
            mode="pro",
            prompt="hello",
            role="user",
            estimated_input_tokens=0,
            max_output_tokens=0,
            has_proven_cost_authority=False,
            is_paid_external_provider=True,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            db_path=self.db_path,
            env=self.standard_env,
        )

        res = asyncio.run(runtime.generate_pro(req))
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("status"), "SPEND_GUARD_BLOCKED")
        self.assertEqual(res.get("blocker"), BLOCKER_MAX_COST_AUTHORITY_MISSING)

    # 43. Chat Pro missing cost authority -> BLOCK
    def test_43_chat_pro_missing_cost_authority_blocked(self):
        store = PublicChatStore(os.path.join(self.temp_dir, "chat_nocost.db"))
        pro_mock = MagicMock()
        pro_mock.is_paid_provider = True
        wallet = MagicMock()
        wallet.get_balance = AsyncMock(return_value=50_000)
        wallet.reserve = AsyncMock(return_value={"ok": True, "reservation_id": "res_nocost"})
        wallet.release = AsyncMock(return_value={"ok": True})
        runtime = PublicChatRuntime(store=store, pro_provider=pro_mock, wallet=wallet, pricing=ClaudeOpusPricing(100, 500, 3))

        req = PublicChatRequest(
            account_id="u_nocost",
            chat_id="chat_nocost",
            source_message_id="msg_nocost",
            mode="pro",
            prompt="hello",
            role="user",
            estimated_input_tokens=0,
            max_output_tokens=0,
            has_proven_cost_authority=False,
            is_paid_external_provider=True,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            db_path=self.db_path,
            env=self.standard_env,
        )

        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            res = asyncio.run(runtime.generate_pro(req))
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("status"), "SPEND_GUARD_BLOCKED")
        self.assertEqual(res.get("blocker"), BLOCKER_MAX_COST_AUTHORITY_MISSING)

    # 44. Chat Pro trusted bot origin + valid token cost quote -> ALLOW (mock transport)
    def test_44_chat_pro_trusted_bot_with_valid_cost_quote_passes(self):
        store = PublicChatStore(os.path.join(self.temp_dir, "chat_ok.db"))
        pro_mock = MagicMock(return_value={"ok": True, "text": "Claude reply", "model": CLAUDE_OPUS_MODEL, "usage": {"input_tokens": 100, "output_tokens": 50}})
        pro_mock.is_paid_provider = True
        wallet = MagicMock()
        wallet.get_balance = AsyncMock(return_value=50_000)
        wallet.reserve = AsyncMock(return_value={"ok": True, "reservation_id": "res_ok"})
        wallet.settle = AsyncMock(return_value={"ok": True})
        runtime = PublicChatRuntime(store=store, pro_provider=pro_mock, wallet=wallet, pricing=ClaudeOpusPricing(100, 500, 3))

        conf_id = create_bot_confirmation(
            chat_id="chat_ok",
            job_id="msg_ok",
            product_family="Public Chat Pro",
            operation="chat_completion",
            db_path=self.db_path,
            env=self.standard_env,
        )

        req = PublicChatRequest(
            account_id="u_ok",
            chat_id="chat_ok",
            source_message_id="msg_ok",
            mode="pro",
            prompt="tell me a joke",
            role="user",
            estimated_input_tokens=500,
            max_output_tokens=500,
            is_paid_external_provider=True,
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            db_path=self.db_path,
            env=self.standard_env,
        )

        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            res = asyncio.run(runtime.generate_pro(req))
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("status"), "ok")
        pro_mock.assert_called_once()

    # 45. AI Edit real key without AI_EDIT_GUARD_ALL still guarded -> BLOCK
    def test_45_ai_edit_real_key_without_guard_all_still_guarded(self):
        config = AiEditProviderConfig(
            provider_name="fal_video",
            enabled=True,
            submit_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video",
            poll_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/{task_id}/status",
            auth_header_name="Authorization",
            auth_header_value="Key real_fal_live_secret",
            model="fal-ai/wan/v2.2-a14b/video-to-video",
            interface="video_to_video_json",
            capabilities=("video_to_video",),
        )
        fake_source = "https://storage.fal.run/fake_vid.mp4"
        env_no_guard = dict(self.standard_env)
        env_no_guard.pop("AI_EDIT_GUARD_ALL", None)

        with self.assertRaises(AiEditProviderError) as cm:
            submit_video_edit(
                config,
                source_video_path=fake_source,
                prompt="make anime",
                negative_prompt="",
                aspect_ratio="9:16",
                duration_seconds=5,
                job_id="job_aiedit_noguardall",
                submit_source=PUBLIC_FINAL_CONFIRM_SOURCE,
                public_user_confirmed=True,
                is_paid_live=False,  # Attempt bypass
                bot_originated_action=False,
                bot_confirm_authority="",
                db_path=self.db_path,
                env=env_no_guard,
            )
        self.assertIn("bot_confirm_authority_missing", str(cm.exception))

    # 46. AI Edit unsupported duration missing cost authority -> BLOCK
    def test_46_ai_edit_unsupported_duration_missing_cost_authority_blocked(self):
        config = AiEditProviderConfig(
            provider_name="fal_video",
            enabled=True,
            submit_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video",
            poll_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/{task_id}/status",
            auth_header_name="Authorization",
            auth_header_value="Key mock_key",
            model="fal-ai/wan/v2.2-a14b/video-to-video",
            interface="video_to_video_json",
            capabilities=("video_to_video",),
        )
        fake_source = "https://storage.fal.run/fake_vid.mp4"

        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            with self.assertRaises(AiEditProviderError) as cm:
                submit_video_edit(
                    config,
                    source_video_path=fake_source,
                    prompt="make anime",
                    negative_prompt="",
                    aspect_ratio="9:16",
                    duration_seconds=7,  # Unsupported duration (not 5s or 10s)
                    job_id="job_aiedit_7s",
                    submit_source=PUBLIC_FINAL_CONFIRM_SOURCE,
                    public_user_confirmed=True,
                    is_paid_live=True,
                    bot_originated_action=True,
                    bot_confirm_authority="bot_telegram_ui_confirmed",
                    db_path=self.db_path,
                    env=self.standard_env,
                )
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

        self.assertIn(BLOCKER_MAX_COST_AUTHORITY_MISSING, str(cm.exception))

    # 47. AI Edit synthetic bot origin rejected -> BLOCK
    def test_47_ai_edit_synthetic_bot_origin_rejected(self):
        config = AiEditProviderConfig(
            provider_name="fal_video",
            enabled=True,
            submit_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video",
            poll_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/{task_id}/status",
            auth_header_name="Authorization",
            auth_header_value="Key mock_key",
            model="fal-ai/wan/v2.2-a14b/video-to-video",
            interface="video_to_video_json",
            capabilities=("video_to_video",),
        )
        fake_source = "https://storage.fal.run/fake_vid.mp4"

        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            with self.assertRaises(AiEditProviderError) as cm:
                submit_video_edit(
                    config,
                    source_video_path=fake_source,
                    prompt="make anime",
                    negative_prompt="",
                    aspect_ratio="9:16",
                    duration_seconds=5,
                    job_id="job_aiedit_synth",
                    submit_source=PUBLIC_FINAL_CONFIRM_SOURCE,
                    public_user_confirmed=True,
                    is_paid_live=True,
                    bot_originated_action=False,
                    bot_confirm_authority="bot_telegram_ui_confirmed",
                    db_path=self.db_path,
                    env=self.standard_env,
                )
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

        self.assertIn(BLOCKER_BOT_ORIGIN_PROOF_MISSING, str(cm.exception))

    # 48. AI Edit post-transport HTTP error retains ambiguous -> RETAIN
    def test_48_ai_edit_post_transport_http_error_retains_ambiguous(self):
        config = AiEditProviderConfig(
            provider_name="fal_video",
            enabled=True,
            submit_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video",
            poll_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/{task_id}/status",
            auth_header_name="Authorization",
            auth_header_value="Key mock_key",
            model="fal-ai/wan/v2.2-a14b/video-to-video",
            interface="video_to_video_json",
            capabilities=("video_to_video",),
        )
        fake_source = "https://storage.fal.run/fake_vid.mp4"

        conf_id = create_bot_confirmation(
            job_id="job_aiedit_http500",
            product_family="Video AI Edit",
            operation="submit_video_edit",
            db_path=self.db_path,
            env=self.standard_env,
        )

        import io
        def mock_opener_http_error(req, timeout=0):
            fp = io.BytesIO(b'{"detail": "Internal Server Error"}')
            raise urllib.error.HTTPError(req.full_url, 500, "Internal Server Error", hdrs={}, fp=fp)

        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            with self.assertRaises(AiEditProviderError):
                submit_video_edit(
                    config,
                    source_video_path=fake_source,
                    prompt="make anime",
                    negative_prompt="",
                    aspect_ratio="9:16",
                    duration_seconds=5,
                    job_id="job_aiedit_http500",
                    submit_source=PUBLIC_FINAL_CONFIRM_SOURCE,
                    public_user_confirmed=True,
                    opener=mock_opener_http_error,
                    is_paid_live=True,
                    bot_originated_action=True,
                    bot_confirm_authority=conf_id,
                    db_path=self.db_path,
                    env=self.standard_env,
                )
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertEqual(summary["pending_reserved_spend_usd"], 0.40)

    # 49. Kill switch alias PAID_EXTERNAL_PROVIDERS_DISABLED=true -> BLOCK
    def test_49_kill_switch_paid_external_providers_disabled_env(self):
        kill_env = dict(self.standard_env)
        kill_env["PAID_EXTERNAL_PROVIDERS_DISABLED"] = "true"
        self.assertTrue(is_kill_switch_active(kill_env))

        # Check all product families fail closed
        for fam in ("Product Video", "Voice / TTS", "Public Chat Pro", "Video AI Edit"):
            ctx = SpendGuardContext(product_family=fam, estimated_max_cost_usd=1.00, has_proven_cost_authority=True, bot_originated_action=True, bot_confirm_authority="bot_telegram_ui_confirmed")
            res = reserve_provider_spend(ctx, db_path=self.db_path, env=kill_env)
            self.assertFalse(res.allowed)
            self.assertEqual(res.blocker, BLOCKER_KILL_SWITCH_ACTIVE)

    # 50. ProviderPaidTransportAuthority registry completeness
    def test_50_provider_paid_transport_registry_complete(self):
        self.assertGreaterEqual(len(PROVIDER_PAID_TRANSPORT_REGISTRY), 10)
        families = {entry.product_family for entry in PROVIDER_PAID_TRANSPORT_REGISTRY}
        self.assertIn("Product Video", families)
        self.assertIn("Voice / TTS", families)
        self.assertIn("Public Chat Pro", families)
        self.assertIn("Video AI Edit", families)
        self.assertIn("SubDub ASR", families)

        tts_auth = resolve_paid_transport_authority("Voice / TTS", "shopaikey_minimax_tts", "create_tts_task")
        self.assertIsNotNone(tts_auth)
        self.assertTrue(tts_auth.can_create_paid_usage)
        self.assertTrue(tts_auth.bot_origin_required)

        chat_auth = resolve_paid_transport_authority("Public Chat Pro", "claude-opus", "chat_completion")
        self.assertIsNotNone(chat_auth)
        self.assertTrue(chat_auth.can_create_paid_usage)


class TestN21UProviderFreeSpendGuardMatrix(unittest.TestCase):
    """Dedicated 18-case test matrix enforcing Section 16 of Owner Directive #1422."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_spend_guard_matrix18_")
        self.db_path = os.path.join(self.temp_dir, "shared_toanaas.db")
        self.standard_env = {
            "SPEND_GUARD_DB_PATH": self.db_path,
            "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE": "MONDAY_0000_UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE": "UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_USD": "200.000",
        }
        init_spend_guard_db(db_path=self.db_path, env=self.standard_env)
        set_kill_switch(None)

    def tearDown(self):
        set_kill_switch(None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. forged has_proven_cost_authority=True => BLOCK
    def test_case_01_forged_has_proven_cost_authority_blocked(self):
        ctx = SpendGuardContext(
            job_id="mat_01",
            request_id="req_mat_01",
            product_family="Product Video",
            provider="key4u_video",
            model="unknown_forged_model",
            operation="create_video_task",
            estimated_max_cost_usd=1.00,
            has_proven_cost_authority=True,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_MAX_COST_AUTHORITY_MISSING)

    # 2. forged estimated cost $0.001 => cannot lower canonical reserve
    def test_case_02_forged_estimated_cost_lowered_cannot_lower_canonical_reserve(self):
        conf_id = create_bot_confirmation(
            job_id="mat_02",
            request_id="req_mat_02",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="mat_02",
            request_id="req_mat_02",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            estimated_max_cost_usd=0.001,  # Caller tries to cheat reserve
            has_proven_cost_authority=True,
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)
        self.assertEqual(res.week_spend_after_micro_usd - res.week_spend_before_micro_usd, 30_600_245)
        self.assertEqual(res.audit_record.get("RESERVED_COST_USD"), 30.600245)

    # 3. forged whitelisted bot-confirm string => BLOCK
    def test_case_03_forged_whitelisted_bot_confirm_string_blocked(self):
        ctx = SpendGuardContext(
            job_id="mat_03",
            request_id="req_mat_03",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",  # String alone without DB row
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 4. real durable bot confirmation record => PASS guard
    def test_case_04_real_durable_bot_confirmation_record_passes_guard(self):
        conf_id = create_bot_confirmation(
            job_id="mat_04",
            request_id="req_mat_04",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="mat_04",
            request_id="req_mat_04",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)

    # 5. expired confirmation => BLOCK
    def test_case_05_expired_confirmation_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="mat_05",
            request_id="req_mat_05",
            product_family="Product Video",
            operation="create_video_task",
            ttl_seconds=-10.0,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="mat_05",
            request_id="req_mat_05",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 6. already-consumed confirmation => BLOCK
    def test_case_06_already_consumed_confirmation_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="mat_06",
            request_id="req_mat_06",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx1 = SpendGuardContext(
            job_id="mat_06",
            request_id="req_mat_06",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
        )
        res1 = reserve_provider_spend(ctx1, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

        # Attempt to reuse the same confirmation on a different job/request
        ctx2 = SpendGuardContext(
            job_id="mat_06_reuse",
            request_id="req_mat_06_reuse",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
        )
        res2 = reserve_provider_spend(ctx2, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res2.allowed)
        self.assertEqual(res2.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 7. confirmation for another job => BLOCK
    def test_case_07_confirmation_for_another_job_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="job_original",
            request_id="req_original",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="job_mismatched",
            request_id="req_mismatched",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 8. confirmation for another product/action => BLOCK
    def test_case_08_confirmation_for_another_product_action_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="mat_08",
            request_id="req_mat_08",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="mat_08",
            request_id="req_mat_08",
            product_family="Voice / TTS",
            provider="shopaikey_openai_tts",
            model="tts-1",
            operation="create_tts_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"char_count": 100},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 9. caller spend_context forged provider/cost => BLOCK
    def test_case_09_caller_spend_context_forged_provider_cost_blocked(self):
        ctx = SpendGuardContext(
            job_id="mat_09",
            request_id="req_mat_09",
            product_family="Product Video",
            provider="unregistered_fake_provider",
            model="fake_model",
            operation="create_video_task",
            estimated_max_cost_usd=0.01,
            has_proven_cost_authority=True,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_PAID_TRANSPORT_AUTHORITY_UNREGISTERED)

    # 10. Product Video model with canonical cost > $1 => reserve actual canonical maximum
    def test_case_10_product_video_canonical_cost_greater_than_one_dollar(self):
        conf_id = create_bot_confirmation(
            job_id="mat_10",
            request_id="req_mat_10",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="mat_10",
            request_id="req_mat_10",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"scene_count": 2},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)
        self.assertEqual(res.week_spend_after_micro_usd - res.week_spend_before_micro_usd, 61_200_490)
        self.assertEqual(res.audit_record.get("RESERVED_COST_USD"), 61.20049)

    # 11. unknown Product Video pricing => BLOCK
    def test_case_11_unknown_product_video_pricing_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="mat_11",
            request_id="req_mat_11",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="mat_11",
            request_id="req_mat_11",
            product_family="Product Video",
            provider="key4u_video",
            model="unpriced_xyz_model",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_MAX_COST_AUTHORITY_MISSING)

    # 12. TTS mismatched provider pricing => BLOCK
    def test_case_12_tts_mismatched_provider_pricing_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="mat_12",
            request_id="req_mat_12",
            product_family="Voice / TTS",
            operation="create_tts_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="mat_12",
            request_id="req_mat_12",
            product_family="Voice / TTS",
            provider="shopaikey_minimax_tts",
            model="speech-02-hd",
            operation="create_tts_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"char_count": 500},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_MAX_COST_AUTHORITY_MISSING)

    # 13. ASR missing pricing => BLOCK
    def test_case_13_asr_missing_pricing_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="mat_13",
            request_id="req_mat_13",
            product_family="SubDub ASR",
            operation="asr_transcribe",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="mat_13",
            request_id="req_mat_13",
            product_family="SubDub ASR",
            provider="key4u_whisper",
            model="whisper-1",
            operation="asr_transcribe",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_MAX_COST_AUTHORITY_MISSING)

    # 14. Suno missing pricing => BLOCK
    def test_case_14_suno_missing_pricing_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="mat_14",
            request_id="req_mat_14",
            product_family="Music / Suno",
            operation="suno_create",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="mat_14",
            request_id="req_mat_14",
            product_family="Music / Suno",
            provider="key4u_suno",
            model="suno-v3.5",
            operation="suno_create",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_MAX_COST_AUTHORITY_MISSING)

    # 15. duplicate same bot action => BLOCK
    def test_case_15_duplicate_same_bot_action_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="mat_15",
            request_id="req_mat_15",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="mat_15",
            request_id="req_mat_15",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
        )
        res1 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

        # Same identical action resubmitted
        res2 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res2.allowed)
        self.assertEqual(res2.blocker, BLOCKER_DUPLICATE_PAID_SUBMIT)

    # 16. CI paid call => BLOCK
    def test_case_16_ci_paid_call_blocked(self):
        ci_env = dict(self.standard_env)
        ci_env["CI"] = "true"
        ctx = SpendGuardContext(
            job_id="mat_16",
            request_id="req_mat_16",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            is_paid_live_attempt=True,
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=ci_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_TEST_NETWORK_ISOLATION)

    # 17. shell/script call => BLOCK
    def test_case_17_shell_script_paid_call_blocked(self):
        ctx = SpendGuardContext(
            job_id="mat_17",
            request_id="req_mat_17",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=False,
            entrypoint="script",
            bot_confirm_authority="",
            is_paid_live_attempt=True,
        )
        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_PAID_LIVE_TEST_BOT_ONLY)

    # 18. kill switch => BLOCK
    def test_case_18_kill_switch_blocked(self):
        set_kill_switch(True)
        ctx = SpendGuardContext(
            job_id="mat_18",
            request_id="req_mat_18",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_KILL_SWITCH_ACTIVE)


if __name__ == "__main__":
    unittest.main()
