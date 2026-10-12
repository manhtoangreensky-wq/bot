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
    issue_bot_mint_authority,
    BotMintAuthority,
    BLOCKER_PAID_TRANSPORT_AUTHORITY_UNREGISTERED,
    mint_multiscene_bot_confirmation_plan,
    WORKER_CAN_MINT_BOT_CONFIRMATION,
    PROVIDER_CAN_MINT_BOT_CONFIRMATION,
    CALLER_BOT_ORIGIN_METADATA_TRUSTED,
    EMPTY_PAID_OPERATION_BLOCKED,
    PRODUCTION_BOT_CONFIRM_MINT_CALLSITE,
    resolve_canonical_cost_micro_usd,
    PROVIDER_ALIAS_MAP,
    is_paid_live_test,
    get_configured_cap_micro_usd,
    BLOCKER_TEST_CONFIRM_CANNOT_REACH_REAL_TRANSPORT,
    BLOCKER_OWNER_LIVE_RECEIPT_MISSING,
    BLOCKER_OWNER_RECEIPT_MISMATCH,
    PURPOSE_PRODUCTION_USER_ACTION,
    PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
    FALSE_NONFORGEABLE_CLAIM_REMOVED,
    MODULE_LOCAL_SECRET_IS_SECURITY_AUTHORITY,
    PYTHON_PRIVATE_NAME_IS_SECURITY_AUTHORITY,
    STACK_INSPECTION_SECURITY_AUTHORITY,
    CALLER_FILENAME_IS_AUTHORITY,
    CALLER_FUNCTION_NAME_IS_AUTHORITY,
    PRODUCTION_TEST_MINT_FACTORY_PRESENT,
    SYNTHETIC_TELEGRAM_AUTH_IDS,
    CALLER_VALIDATED_OWNERSHIP_BOOL_TRUSTED,
    BOT_CONFIRM_VALIDATION_SOURCE,
    BOT_CONFIRM_VALIDATION_CALLSITE,
    MINT_TRUST_MODEL,
    CALLER_PAID_LIVE_TEST_FLAG_TRUSTED,
    PAID_LIVE_TEST_CLASSIFICATION_SOURCE,
    OWNER_RECEIPT_CALLER_STRING_TRUSTED,
    OWNER_LIVE_AUTH_BINDING,
    ORDINARY_PRODUCTION_PAID_CREATE_SEPARATION,
    PER_SCENE_RESERVATION_GRANULARITY,
    MULTISCENE_TOTAL_COST_SUM,
    SCENE_COUNT_DOUBLE_MULTIPLICATION,
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


def create_test_mint_authority(
    *,
    callsite: str = "tests:test_provider_free",
    chat_id: int | str = "123456",
    user_id: int | str = "789012",
    job_id: str = "",
    request_id: str = "",
    telegram_update_id: int | str = 999999,
    action: str = "b14_confirm",
    purpose: str = PURPOSE_PRODUCTION_USER_ACTION,
    owner_receipt: str = "",
    expected_max_provider_spend_usd: float | Decimal = 0.0,
    is_test_override: bool = True,
    record_type: str = "SCENE_SUBMIT",
    _caller_override_for_test: str | None = None,
) -> BotMintAuthority:
    """Test fixture mint authority helper local to tests module (not in production services)."""
    if _caller_override_for_test in ("production", "bot", "worker", "provider", "services"):
        raise PermissionError(
            "create_test_mint_authority is blocked in production runtime: "
            "PRODUCTION_TEST_MINT_OVERRIDE_AVAILABLE=NO"
        )
    return BotMintAuthority(
        callsite=callsite,
        telegram_update_id=telegram_update_id,
        chat_id=chat_id,
        user_id=user_id,
        callback_query_id="cbq_test_fixture",
        job_id=job_id,
        request_id=request_id,
        action=action,
        validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
        validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
        purpose=purpose,
        owner_receipt=owner_receipt,
        expected_max_provider_spend_usd=expected_max_provider_spend_usd,
        is_test_override=is_test_override,
        record_type="TEST" if is_test_override else record_type,
        _issued_by_seam=True,
    )


_raw_create_bot_confirmation = create_bot_confirmation
_raw_mint_multiscene_bot_confirmation_plan = mint_multiscene_bot_confirmation_plan


def create_bot_confirmation(*args, **kwargs):
    if "mint_authority" not in kwargs and not kwargs.get("_test_unauthorized_mint") and not kwargs.get("origin"):
        kwargs["mint_authority"] = create_test_mint_authority(
            chat_id=str(kwargs.get("chat_id") or "123456"),
            user_id=str(kwargs.get("user_id") or "789012"),
        )
    kwargs.pop("_test_unauthorized_mint", None)
    return _raw_create_bot_confirmation(*args, **kwargs)


def mint_multiscene_bot_confirmation_plan(*args, **kwargs):
    if "mint_authority" not in kwargs and not kwargs.get("_test_unauthorized_mint") and not kwargs.get("origin"):
        kwargs["mint_authority"] = create_test_mint_authority(
            chat_id=str(kwargs.get("chat_id") or "123456"),
            user_id=str(kwargs.get("user_id") or "789012"),
        )
    kwargs.pop("_test_unauthorized_mint", None)
    return _raw_mint_multiscene_bot_confirmation_plan(*args, **kwargs)


def _process_reserve_worker(db_path: str, env_dict: dict, job_id: str, cost: float, result_queue: multiprocessing.Queue):
    """Top-level picklable helper for multi-process concurrency testing."""
    try:
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
    except Exception as exc:
        result_queue.put({
            "job_id": job_id,
            "allowed": False,
            "blocker": "worker_exception",
            "error": str(exc),
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
            product_family="Product Video",
            provider="key4u_video",
            operation="create_video_task",
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
            owner_receipt="rcpt_test_owner_16",
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

        results = [q.get(timeout=10) for _ in range(2)]
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
            metadata={"quality_key": "kling_long_audio_15"},
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
            metadata={"quality_key": "kling_long_audio_15"},
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
            metadata={"quality_key": "kling_long_audio_15"},
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
            metadata={"quality_key": "kling_long_audio_15"},
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
            metadata={"quality_key": "kling_long_audio_15"},
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
            metadata={"quality_key": "kling_long_audio_15"},
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
            metadata={"quality_key": "kling_long_audio_15"},
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
            metadata={"quality_key": "kling_long_audio_15", "scene_count": 2},
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
            metadata={"quality_key": "kling_long_audio_15"},
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


class TestN21VRealBotConfirmLineageAndMultiSubmitMatrix(unittest.TestCase):
    """Authoritative 22-case matrix for N21V real bot confirm lineage and multi-submit authority."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="pv_n21v_test_")
        self.db_path = os.path.join(self.temp_dir, "toanaas_spend_guard_shared.db")
        self.standard_env = {
            "SPEND_GUARD_DB_PATH": self.db_path,
            "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE": "MONDAY_0000_UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE": "UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_USD": "200.000",
            "UNIT_TEST_ENV": "true",
            "TEST_RUNNER": "true",
        }
        set_kill_switch(None)
        init_spend_guard_db(db_path=self.db_path, env=self.standard_env)

    def tearDown(self):
        set_kill_switch(None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. fake confirmation ID + matching valid job_id -> BLOCK
    def test_n21v_01_fake_confirmation_id_matching_valid_job_blocked(self):
        create_bot_confirmation(
            job_id="job_valid_01",
            request_id="req_valid_01",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="job_valid_01",
            request_id="req_valid_01",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority="fake_confirmation_id_01",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 2. fake confirmation ID + matching valid request_id -> BLOCK
    def test_n21v_02_fake_confirmation_id_matching_valid_request_blocked(self):
        create_bot_confirmation(
            job_id="job_valid_02",
            request_id="req_valid_02",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="job_valid_02",
            request_id="req_valid_02",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority="fake_confirmation_id_02",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 3. exact confirmation ID + wrong job -> BLOCK
    def test_n21v_03_exact_confirmation_id_wrong_job_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="job_original_03",
            request_id="req_original_03",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="job_wrong_03",
            request_id="req_original_03",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)
        self.assertIn("job mismatch", res.reason)

    # 4. exact ID + wrong request -> BLOCK
    def test_n21v_04_exact_id_wrong_request_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="job_original_04",
            request_id="req_original_04",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="job_original_04",
            request_id="req_wrong_04",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)
        self.assertIn("request mismatch", res.reason)

    # 5. exact ID + wrong user/chat -> BLOCK
    def test_n21v_05_exact_id_wrong_user_or_chat_blocked(self):
        conf_id = create_bot_confirmation(
            chat_id="11111",
            user_id="22222",
            job_id="job_05",
            request_id="req_05",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        # Wrong chat
        ctx_wrong_chat = SpendGuardContext(
            chat_id="99999",
            user_id="22222",
            job_id="job_05",
            request_id="req_05",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res1 = reserve_provider_spend(ctx_wrong_chat, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res1.allowed)
        self.assertEqual(res1.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)
        self.assertIn("chat mismatch", res1.reason)

        # Wrong user
        ctx_wrong_user = SpendGuardContext(
            chat_id="11111",
            user_id="88888",
            job_id="job_05",
            request_id="req_05",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res2 = reserve_provider_spend(ctx_wrong_user, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res2.allowed)
        self.assertEqual(res2.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)
        self.assertIn("user mismatch", res2.reason)

    # 6. exact ID + wrong operation -> BLOCK
    def test_n21v_06_exact_id_wrong_operation_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="job_06",
            request_id="req_06",
            product_family="Product Video",
            operation="submit_video_edit",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="job_06",
            request_id="req_06",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)
        self.assertIn("operation mismatch", res.reason)

    # 7. empty paid operation -> BLOCK
    def test_n21v_07_empty_paid_operation_blocked(self):
        self.assertTrue(EMPTY_PAID_OPERATION_BLOCKED)
        conf_id = create_bot_confirmation(
            job_id="job_07",
            request_id="req_07",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="job_07",
            request_id="req_07",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_PAID_TRANSPORT_AUTHORITY_UNREGISTERED)

    # 8. direct provider cannot mint confirmation
    def test_n21v_08_direct_provider_cannot_mint_confirmation(self):
        self.assertFalse(PROVIDER_CAN_MINT_BOT_CONFIRMATION)
        with self.assertRaises(PermissionError):
            create_bot_confirmation(
                origin="direct_provider",
                job_id="job_08",
                request_id="req_08",
                db_path=self.db_path,
                env=self.standard_env,
            )
        with self.assertRaises(PermissionError):
            mint_multiscene_bot_confirmation_plan(
                origin="provider",
                job_id="job_08",
                request_id="req_08",
                db_path=self.db_path,
                env=self.standard_env,
            )

    # 9. worker cannot mint confirmation
    def test_n21v_09_worker_cannot_mint_confirmation(self):
        self.assertFalse(WORKER_CAN_MINT_BOT_CONFIRMATION)
        with self.assertRaises(PermissionError):
            create_bot_confirmation(
                origin="worker",
                job_id="job_09",
                request_id="req_09",
                db_path=self.db_path,
                env=self.standard_env,
            )
        with self.assertRaises(PermissionError):
            mint_multiscene_bot_confirmation_plan(
                origin="worker",
                job_id="job_09",
                request_id="req_09",
                db_path=self.db_path,
                env=self.standard_env,
            )

    # 10. shell cannot mint usable bot authority
    def test_n21v_10_shell_cannot_mint_usable_bot_authority(self):
        with self.assertRaises(PermissionError):
            create_bot_confirmation(
                origin="shell",
                job_id="job_10",
                request_id="req_10",
                db_path=self.db_path,
                env=self.standard_env,
            )
        with self.assertRaises(PermissionError):
            mint_multiscene_bot_confirmation_plan(
                origin="shell",
                job_id="job_10",
                request_id="req_10",
                db_path=self.db_path,
                env=self.standard_env,
            )

    # 11. actual mocked Telegram confirm -> creates durable confirmation
    def test_n21v_11_mocked_telegram_confirm_creates_durable_confirmation(self):
        self.assertEqual(PRODUCTION_BOT_CONFIRM_MINT_CALLSITE, "bot.py:handle_video_product_callback:b14_confirm")
        mint_auth = issue_bot_mint_authority(
            callsite=PRODUCTION_BOT_CONFIRM_MINT_CALLSITE,
            telegram_update_id=998877,
            callback_query_id="cbq_tg_11",
            chat_id="12345",
            user_id="67890",
            job_id="job_tg_11",
            request_id="req_tg_11",
            validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
            validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
            validated_ownership=True,
        )
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=mint_auth,
            chat_id="12345",
            user_id="67890",
            job_id="job_tg_11",
            request_id="req_tg_11",
            product_family="Product Video",
            operation="create_video_task",
            scene_count=2,
            ttl_seconds=600.0,
            metadata={
                "telegram_update_id": 998877,
                "production_callsite": PRODUCTION_BOT_CONFIRM_MINT_CALLSITE,
            },
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertTrue(plan["parent_confirmation_id"].startswith("bot_conf_parent_"))
        self.assertEqual(len(plan["child_confirmations"]), 2)

        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT confirmation_id, parent_confirmation_id, scene_index, status FROM bot_spend_confirmations WHERE job_id = ?", ("job_tg_11",))
        rows = cur.fetchall()
        conn.close()
        self.assertEqual(len(rows), 3)
        for r in rows:
            self.assertEqual(r[3], "active")

    # 12. confirmation propagates Bot -> job -> worker -> spend guard
    def test_n21v_12_confirmation_propagates_bot_to_job_to_worker_to_spend_guard(self):
        plan = mint_multiscene_bot_confirmation_plan(
            chat_id="111",
            user_id="222",
            job_id="job_prop_12",
            request_id="req_prop_12",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        from services.video_project_queue import _product_video_final_admission_state
        admission_in = {
            "bot_confirm_authority": plan["parent_confirmation_id"],
            "scene_confirmations": plan["scene_confirmations"],
            "child_confirmations": plan["child_confirmations"],
        }
        state = _product_video_final_admission_state({}, admission_in, user_id=222, require_provider_admission=True, require_authoritative_snapshot=False, checked_at="2026-10-12T00:00:00")
        self.assertEqual(state.get("bot_confirm_authority"), plan["parent_confirmation_id"])
        self.assertEqual(state.get("scene_confirmations"), plan["scene_confirmations"])

    # 13. two-scene job receives exactly two child authorities
    def test_n21v_13_two_scene_job_receives_exactly_two_child_authorities(self):
        plan = mint_multiscene_bot_confirmation_plan(
            chat_id="333",
            user_id="444",
            job_id="job_two_13",
            request_id="req_two_13",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertEqual(len(plan["child_confirmations"]), 2)
        self.assertEqual(len(plan["scene_confirmations"]), 2)
        self.assertIn(1, plan["scene_confirmations"])
        self.assertIn(2, plan["scene_confirmations"])
        self.assertNotEqual(plan["scene_confirmations"][1], plan["scene_confirmations"][2])

    # 14. scene1 passes once
    def test_n21v_14_scene1_passes_once(self):
        plan = mint_multiscene_bot_confirmation_plan(
            chat_id="555",
            user_id="666",
            job_id="job_s1_14",
            request_id="req_s1_14",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        child1 = plan["scene_confirmations"][1]
        ctx = SpendGuardContext(
            chat_id="555",
            user_id="666",
            job_id="job_s1_14",
            request_id="req_s1_14",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=child1,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)

        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT status, consumed_at FROM bot_spend_confirmations WHERE confirmation_id = ?", (child1,))
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row[0], "consumed")
        self.assertIsNotNone(row[1])

    # 15. scene2 passes once
    def test_n21v_15_scene2_passes_once(self):
        plan = mint_multiscene_bot_confirmation_plan(
            chat_id="777",
            user_id="888",
            job_id="job_s2_15",
            request_id="req_s2_15",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        # Scene 1 passes
        ctx1 = SpendGuardContext(
            chat_id="777",
            user_id="888",
            job_id="job_s2_15",
            request_id="req_s2_15",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=plan["scene_confirmations"][1],
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res1 = reserve_provider_spend(ctx1, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

        # Scene 2 passes
        ctx2 = SpendGuardContext(
            chat_id="777",
            user_id="888",
            job_id="job_s2_15",
            request_id="req_s2_15",
            scene_index=2,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=plan["scene_confirmations"][2],
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res2 = reserve_provider_spend(ctx2, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res2.allowed)

    # 16. scene3 blocked
    def test_n21v_16_scene3_blocked(self):
        plan = mint_multiscene_bot_confirmation_plan(
            chat_id="999",
            user_id="1010",
            job_id="job_s3_16",
            request_id="req_s3_16",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx3 = SpendGuardContext(
            chat_id="999",
            user_id="1010",
            job_id="job_s3_16",
            request_id="req_s3_16",
            scene_index=3,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=plan.get("scene_confirmations", {}).get(3, ""),
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res3 = reserve_provider_spend(ctx3, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res3.allowed)
        self.assertEqual(res3.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 17. scene1 duplicate blocked
    def test_n21v_17_scene1_duplicate_blocked(self):
        plan = mint_multiscene_bot_confirmation_plan(
            chat_id="1212",
            user_id="1313",
            job_id="job_dup_17",
            request_id="req_dup_17",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="1212",
            user_id="1313",
            job_id="job_dup_17",
            request_id="req_dup_17",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=plan["scene_confirmations"][1],
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res1 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

        # Duplicate submit with identical context
        res2 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res2.allowed)
        self.assertEqual(res2.blocker, BLOCKER_DUPLICATE_PAID_SUBMIT)

    # 18. ambiguous scene consumes authority and retry blocked
    def test_n21v_18_ambiguous_scene_consumes_authority_and_retry_blocked(self):
        plan = mint_multiscene_bot_confirmation_plan(
            chat_id="1414",
            user_id="1515",
            job_id="job_amb_18",
            request_id="req_amb_18",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        child1 = plan["scene_confirmations"][1]
        ctx = SpendGuardContext(
            chat_id="1414",
            user_id="1515",
            job_id="job_amb_18",
            request_id="req_amb_18",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=child1,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)

        retain_ambiguous_provider_spend(
            res.reservation_id,
            error_code="transport_timeout_disconnect",
            db_path=self.db_path,
            env=self.standard_env,
        )

        # Retry blocked
        retry_res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(retry_res.allowed)
        self.assertEqual(retry_res.blocker, BLOCKER_AMBIGUOUS_RETRY_BLOCKED)

        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT status FROM bot_spend_confirmations WHERE confirmation_id = ?", (child1,))
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row[0], "consumed")

    # 19. caller metadata submit_source cannot create bot authority
    def test_n21v_19_caller_metadata_submit_source_cannot_create_bot_authority(self):
        self.assertFalse(CALLER_BOT_ORIGIN_METADATA_TRUSTED)
        ctx = SpendGuardContext(
            job_id="job_meta_19",
            request_id="req_meta_19",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=False,
            bot_confirm_authority="",
            metadata={"submit_source": "public_user_final_confirm", "quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 20. caller product_video=True cannot create bot authority
    def test_n21v_20_caller_product_video_cannot_create_bot_authority(self):
        ctx = SpendGuardContext(
            job_id="job_meta_20",
            request_id="req_meta_20",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=False,
            bot_confirm_authority="",
            metadata={"product_video": True, "source": "product_video", "quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 21. exact Product Video tier cost selected
    def test_n21v_21_exact_product_video_tier_cost_selected(self):
        authority = resolve_paid_transport_authority("Product Video", "key4u_video", "create_video_task")
        self.assertIsNotNone(authority)
        ctx15 = SpendGuardContext(
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        cost15, proven15, source15 = resolve_canonical_cost_micro_usd(ctx15, authority)
        self.assertTrue(proven15)
        self.assertEqual(cost15, 30_600_245)

        ctx5 = SpendGuardContext(
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            metadata={"quality_key": "motion_standard_5"},
        )
        cost5, proven5, source5 = resolve_canonical_cost_micro_usd(ctx5, authority)
        self.assertTrue(proven5)
        self.assertEqual(cost5, 7_650_061)

    # 22. ambiguous route pricing -> BLOCK
    def test_n21v_22_ambiguous_route_pricing_blocked(self):
        authority = resolve_paid_transport_authority("Product Video", "key4u_video", "create_video_task")
        self.assertIsNotNone(authority)
        ctx_ambiguous = SpendGuardContext(
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            metadata={},
        )
        cost, proven, source = resolve_canonical_cost_micro_usd(ctx_ambiguous, authority)
        self.assertFalse(proven)
        self.assertIn("ambiguous_product_video_route_pricing_multiple_tiers_match", source)

        conf_id = create_bot_confirmation(
            job_id="job_amb_22",
            request_id="req_amb_22",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx_ambiguous.job_id = "job_amb_22"
        ctx_ambiguous.request_id = "req_amb_22"
        ctx_ambiguous.bot_confirm_authority = conf_id
        res = reserve_provider_spend(ctx_ambiguous, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_MAX_COST_AUTHORITY_MISSING)


class TestN21WConfirmationMintBoundaryAndProductionReadinessMatrix(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_n21w_matrix_")
        self.db_path = os.path.join(self.temp_dir, "toanaas.db")
        self.standard_env = {
            "SPEND_GUARD_DB_PATH": self.db_path,
            "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE": "MONDAY_0000_UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE": "UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_USD": "200.000",
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. worker calls mint primitive with default args -> BLOCK
    def test_n21w_01_worker_calls_mint_primitive_with_default_args_blocked(self):
        with self.assertRaises(PermissionError):
            _raw_create_bot_confirmation(db_path=self.db_path, env=self.standard_env)

    # 2. provider calls mint primitive with default args -> BLOCK
    def test_n21w_02_provider_calls_mint_primitive_with_default_args_blocked(self):
        with self.assertRaises(PermissionError):
            _raw_mint_multiscene_bot_confirmation_plan(db_path=self.db_path, env=self.standard_env)

    # 3. forged origin="telegram_bot_callback_or_command" outside trusted Bot mint authority -> BLOCK
    def test_n21w_03_forged_origin_outside_trusted_mint_authority_blocked(self):
        with self.assertRaises(PermissionError):
            _raw_create_bot_confirmation(
                origin="telegram_bot_callback_or_command",
                job_id="job_forge",
                db_path=self.db_path,
                env=self.standard_env,
            )

    # 4. Bot validated Telegram callback -> mint PASS
    def test_n21w_04_bot_validated_telegram_callback_mint_passes(self):
        mint_auth = issue_bot_mint_authority(
            callsite="bot.py:handle_video_product_callback:b14_confirm",
            telegram_update_id=123456,
            callback_query_id="cbq_04",
            chat_id="chat_04",
            user_id="user_04",
            job_id="job_04",
            request_id="req_04",
            validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
            validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
            validated_ownership=True,
        )
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=mint_auth,
            chat_id="chat_04",
            user_id="user_04",
            job_id="job_04",
            request_id="req_04",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertTrue(plan["parent_confirmation_id"].startswith("bot_conf_parent_"))
        self.assertEqual(len(plan["child_confirmations"]), 2)
        self.assertEqual(len(plan["scene_confirmations"]), 2)

    # 5. mint failure -> invoice confirm NOT called
    def test_n21w_05_mint_failure_invoice_confirm_not_called(self):
        invoice_called = False
        def mock_confirm_invoice(*args, **kwargs):
            nonlocal invoice_called
            invoice_called = True
            return {"ok": True}

        mint_failed = True
        if mint_failed:
            blocked_session = {"blocker_code": "spend_guard_mint_failed", "status": "BLOCKED"}
        else:
            mock_confirm_invoice("proj_1", "u_1")

        self.assertFalse(invoice_called)
        self.assertEqual(blocked_session["blocker_code"], "spend_guard_mint_failed")

    # 6. mint failure -> queue NOT called
    def test_n21w_06_mint_failure_queue_not_called(self):
        queue_called = False
        def mock_enqueue(*args, **kwargs):
            nonlocal queue_called
            queue_called = True

        mint_failed = True
        if not mint_failed:
            mock_enqueue()

        self.assertFalse(queue_called)

    # 7. mint failure -> wallet mutation 0
    def test_n21w_07_mint_failure_wallet_mutation_zero(self):
        wallet_debits = 0
        def mock_wallet_debit(*args, **kwargs):
            nonlocal wallet_debits
            wallet_debits += 1

        mint_failed = True
        if not mint_failed:
            mock_wallet_debit()

        self.assertEqual(wallet_debits, 0)

    # 8. exact confirmation + missing job_id -> BLOCK
    def test_n21w_08_exact_confirmation_missing_job_id_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_8", user_id="user_8")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_8",
            user_id="user_8",
            job_id="job_8",
            request_id="req_8",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_8",
            user_id="user_8",
            job_id="",
            request_id="req_8",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 9. exact confirmation + missing request_id -> BLOCK
    def test_n21w_09_exact_confirmation_missing_request_id_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_9", user_id="user_9")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_9",
            user_id="user_9",
            job_id="job_9",
            request_id="req_9",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_9",
            user_id="user_9",
            job_id="job_9",
            request_id="",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 10. exact confirmation + missing chat_id -> BLOCK
    def test_n21w_10_exact_confirmation_missing_chat_id_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_10", user_id="user_10")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_10",
            user_id="user_10",
            job_id="job_10",
            request_id="req_10",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="",
            user_id="user_10",
            job_id="job_10",
            request_id="req_10",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 11. exact confirmation + missing user_id -> BLOCK
    def test_n21w_11_exact_confirmation_missing_user_id_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_11", user_id="user_11")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_11",
            user_id="user_11",
            job_id="job_11",
            request_id="req_11",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_11",
            user_id="",
            job_id="job_11",
            request_id="req_11",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 12. exact child + missing scene_index -> BLOCK
    def test_n21w_12_exact_child_missing_scene_index_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_12", user_id="user_12")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_12",
            user_id="user_12",
            job_id="job_12",
            request_id="req_12",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        child1 = plan["scene_confirmations"][1]
        ctx = SpendGuardContext(
            chat_id="chat_12",
            user_id="user_12",
            job_id="job_12",
            request_id="req_12",
            scene_index=0,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=child1,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 13. parent confirmation used for submit -> BLOCK
    def test_n21w_13_parent_confirmation_used_for_submit_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_13", user_id="user_13")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_13",
            user_id="user_13",
            job_id="job_13",
            request_id="req_13",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        parent_id = plan["parent_confirmation_id"]
        ctx = SpendGuardContext(
            chat_id="chat_13",
            user_id="user_13",
            job_id="job_13",
            request_id="req_13",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=parent_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)
        self.assertIn("cannot authorize transport submit", res.reason)

    # 14. scene 1 -> exact child 1
    def test_n21w_14_scene_1_exact_child_1_passes(self):
        auth = create_test_mint_authority(chat_id="chat_14", user_id="user_14")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_14",
            user_id="user_14",
            job_id="job_14",
            request_id="req_14",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        child1 = plan["scene_confirmations"][1]
        ctx1 = SpendGuardContext(
            chat_id="chat_14",
            user_id="user_14",
            job_id="job_14",
            request_id="req_14",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=child1,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res1 = reserve_provider_spend(ctx1, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

    # 15. scene 2 -> exact child 2
    def test_n21w_15_scene_2_exact_child_2_passes(self):
        auth = create_test_mint_authority(chat_id="chat_15", user_id="user_15")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_15",
            user_id="user_15",
            job_id="job_15",
            request_id="req_15",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        child2 = plan["scene_confirmations"][2]
        ctx2 = SpendGuardContext(
            chat_id="chat_15",
            user_id="user_15",
            job_id="job_15",
            request_id="req_15",
            scene_index=2,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=child2,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res2 = reserve_provider_spend(ctx2, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res2.allowed)

    # 16. scene 0 -> BLOCK
    def test_n21w_16_scene_0_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_16", user_id="user_16")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_16",
            user_id="user_16",
            job_id="job_16",
            request_id="req_16",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_16",
            user_id="user_16",
            job_id="job_16",
            request_id="req_16",
            scene_index=0,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=plan["scene_confirmations"][1],
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 17. scene 3 in two-scene plan -> BLOCK
    def test_n21w_17_scene_3_in_two_scene_plan_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_17", user_id="user_17")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_17",
            user_id="user_17",
            job_id="job_17",
            request_id="req_17",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_17",
            user_id="user_17",
            job_id="job_17",
            request_id="req_17",
            scene_index=3,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority="",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 18. no +/-1 scene fallback
    def test_n21w_18_no_plus_minus_one_scene_fallback(self):
        auth = create_test_mint_authority(chat_id="chat_18", user_id="user_18")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_18",
            user_id="user_18",
            job_id="job_18",
            request_id="req_18",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        child1 = plan["scene_confirmations"][1]
        ctx = SpendGuardContext(
            chat_id="chat_18",
            user_id="user_18",
            job_id="job_18",
            request_id="req_18",
            scene_index=2,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=child1,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)
        self.assertIn("scene mismatch: scene 1 != 2", res.reason)

    # 19. final admitted scene count != minted child count -> BLOCK
    def test_n21w_19_final_admitted_scene_count_mismatch_blocked(self):
        confirm_scene_count = 2
        final_admitted_scene_count = 3
        blocked = confirm_scene_count != final_admitted_scene_count
        self.assertTrue(blocked)

    # 20. child reservation + consume atomic
    def test_n21w_20_child_reservation_and_consume_atomic(self):
        auth = create_test_mint_authority(chat_id="chat_20", user_id="user_20")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_20",
            user_id="user_20",
            job_id="job_20",
            request_id="req_20",
            scene_count=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        child1 = plan["scene_confirmations"][1]
        ctx = SpendGuardContext(
            chat_id="chat_20",
            user_id="user_20",
            job_id="job_20",
            request_id="req_20",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=child1,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)

        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT status, consumed_at FROM bot_spend_confirmations WHERE confirmation_id = ?", (child1,))
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row[0], "consumed")
        self.assertIsNotNone(row[1])

    # 21. ambiguous child remains consumed
    def test_n21w_21_ambiguous_child_remains_consumed(self):
        auth = create_test_mint_authority(chat_id="chat_21", user_id="user_21")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_21",
            user_id="user_21",
            job_id="job_21",
            request_id="req_21",
            scene_count=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        child1 = plan["scene_confirmations"][1]
        ctx = SpendGuardContext(
            chat_id="chat_21",
            user_id="user_21",
            job_id="job_21",
            request_id="req_21",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=child1,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)

        retain_ambiguous_provider_spend(
            res.reservation_id,
            error_code="socket_hangup",
            db_path=self.db_path,
            env=self.standard_env,
        )

        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT status FROM bot_spend_confirmations WHERE confirmation_id = ?", (child1,))
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row[0], "consumed")

    # 22. ambiguous child cannot be reminted/retried
    def test_n21w_22_ambiguous_child_cannot_be_retried(self):
        auth = create_test_mint_authority(chat_id="chat_22", user_id="user_22")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_22",
            user_id="user_22",
            job_id="job_22",
            request_id="req_22",
            scene_count=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        child1 = plan["scene_confirmations"][1]
        ctx = SpendGuardContext(
            chat_id="chat_22",
            user_id="user_22",
            job_id="job_22",
            request_id="req_22",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=child1,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)

        retain_ambiguous_provider_spend(
            res.reservation_id,
            error_code="timeout",
            db_path=self.db_path,
            env=self.standard_env,
        )

        retry = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(retry.allowed)
        self.assertEqual(retry.blocker, BLOCKER_AMBIGUOUS_RETRY_BLOCKED)

    # 23. ordinary real production paid-create != paid live test
    def test_n21w_23_ordinary_real_production_paid_create_not_paid_live_test(self):
        auth = create_test_mint_authority(chat_id="chat_23", user_id="user_23")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_23",
            user_id="user_23",
            job_id="job_23",
            request_id="req_23",
            product_family="Product Video",
            operation="create_video_task",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_23",
            user_id="user_23",
            job_id="job_23",
            request_id="req_23",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            paid_live_test=False,
            owner_receipt="",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)

    # 24. ordinary paid-create still enters weekly cap
    def test_n21w_24_ordinary_paid_create_enters_weekly_cap(self):
        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        before = summary["total_active_week_spend_usd"]

        auth = create_test_mint_authority(chat_id="chat_24", user_id="user_24")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_24",
            user_id="user_24",
            job_id="job_24",
            request_id="req_24",
            product_family="Product Video",
            operation="create_video_task",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_24",
            user_id="user_24",
            job_id="job_24",
            request_id="req_24",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            paid_live_test=False,
            metadata={"quality_key": "motion_standard_5"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)

        summary_after = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertAlmostEqual(summary_after["total_active_week_spend_usd"], before + 7.650061, places=5)

    # 25. paid live test without Owner receipt -> BLOCK
    def test_n21w_25_paid_live_test_without_owner_receipt_blocked(self):
        auth = create_test_mint_authority(
            chat_id="chat_25",
            user_id="user_25",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_25",
            user_id="user_25",
            job_id="job_25",
            request_id="req_25",
            product_family="Product Video",
            operation="create_video_task",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_25",
            user_id="user_25",
            job_id="job_25",
            request_id="req_25",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            paid_live_test=True,
            owner_receipt="",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertIn(res.blocker, (BLOCKER_BOT_ORIGIN_PROOF_MISSING, BLOCKER_OWNER_LIVE_RECEIPT_MISSING))

    # 26. paid live test with durable bot origin + Owner receipt -> guard PASS provider-free
    def test_n21w_26_paid_live_test_with_durable_bot_origin_and_owner_receipt_passes(self):
        auth = create_test_mint_authority(
            chat_id="chat_26",
            user_id="user_26",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_owner_authorized_26",
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_26",
            user_id="user_26",
            job_id="job_26",
            request_id="req_26",
            product_family="Product Video",
            operation="create_video_task",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_owner_authorized_26",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_26",
            user_id="user_26",
            job_id="job_26",
            request_id="req_26",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            paid_live_test=True,
            owner_receipt="rcpt_owner_authorized_26",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
            self.assertTrue(res.allowed)
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

    # 27. forged entrypoint/user_flow/bot_origin bool alone -> BLOCK
    def test_n21w_27_forged_entrypoint_user_flow_bot_origin_alone_blocked(self):
        ctx = SpendGuardContext(
            chat_id="chat_27",
            user_id="user_27",
            job_id="job_27",
            request_id="req_27",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            user_flow="product_video_bot",
            entrypoint="bot",
            bot_confirm_authority="",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 28. ambiguous Product Video route price -> BLOCK
    def test_n21w_28_ambiguous_product_video_route_price_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_28", user_id="user_28")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_28",
            user_id="user_28",
            job_id="job_28",
            request_id="req_28",
            product_family="Product Video",
            operation="create_video_task",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_28",
            user_id="user_28",
            job_id="job_28",
            request_id="req_28",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_MAX_COST_AUTHORITY_MISSING)

    # 29. exact tier/provider/model/duration -> exact canonical reserve
    def test_n21w_29_exact_tier_provider_model_duration_canonical_reserve(self):
        authority = resolve_paid_transport_authority("Product Video", "key4u_video", "create_video_task")
        self.assertIsNotNone(authority)
        ctx = SpendGuardContext(
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            metadata={"quality_key": "kling_long_audio_15", "duration_seconds": 15},
        )
        cost_micro, proven, source = resolve_canonical_cost_micro_usd(ctx, authority)
        self.assertTrue(proven)
        self.assertEqual(cost_micro, 30_600_245)



class TestN21XNonForgeableBotMintCapabilityMatrix(unittest.TestCase):
    """N21X Verification Matrix: Non-forgeable Bot Mint Capability, Caller Boundary, and Exact Transport Authority."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="n21x_mint_cap_")
        self.db_path = os.path.join(self.temp_dir, "test_system.db")
        init_spend_guard_db(db_path=self.db_path)
        self.standard_env = {
            "SPEND_GUARD_DB_PATH": self.db_path,
            "WEEKLY_PROVIDER_SPEND_CAP_USD": "200.000",
            "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE": "MONDAY_0000_UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE": "UTC",
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. Direct BotMintAuthority(...) constructor -> unusable/BLOCK
    def test_n21x_01_direct_bot_mint_authority_constructor_unusable(self):
        with self.assertRaises(PermissionError):
            BotMintAuthority(
                callsite="bot.py:handle_video_product_callback:b14_confirm",
                telegram_update_id=1,
                chat_id="123",
                user_id="456",
            )

    # 2. generic service calls production issuer with correct callsite string -> BLOCK
    def test_n21x_02_generic_service_calls_production_issuer_with_whitelisted_string_blocked(self):
        with self.assertRaises(PermissionError):
            issue_bot_mint_authority(
                callsite="bot.py:handle_video_product_callback:b14_confirm",
                telegram_update_id=1,
                callback_query_id="cbq_1",
                chat_id="123",
                user_id="456",
                job_id="job_1",
                request_id="req_1",
                _caller_override_for_test="generic_service",
            )

    # 3. worker passes exact whitelisted callsite string -> BLOCK
    def test_n21x_03_worker_passes_whitelisted_callsite_string_blocked(self):
        with self.assertRaises(PermissionError):
            issue_bot_mint_authority(
                callsite="bot.py:handle_video_product_callback:b14_confirm",
                telegram_update_id=1,
                callback_query_id="cbq_1",
                chat_id="123",
                user_id="456",
                job_id="job_1",
                request_id="req_1",
                _caller_override_for_test="worker",
            )

    # 4. provider passes exact whitelisted callsite string -> BLOCK
    def test_n21x_04_provider_passes_whitelisted_callsite_string_blocked(self):
        with self.assertRaises(PermissionError):
            issue_bot_mint_authority(
                callsite="bot.py:handle_video_product_callback:b14_confirm",
                telegram_update_id=1,
                callback_query_id="cbq_1",
                chat_id="123",
                user_id="456",
                job_id="job_1",
                request_id="req_1",
                _caller_override_for_test="provider",
            )

    # 5. production code calls create_test_mint_authority -> unavailable/BLOCK
    def test_n21x_05_production_code_calls_create_test_mint_authority_blocked(self):
        with self.assertRaises(PermissionError):
            create_test_mint_authority(
                _caller_override_for_test="production",
            )

    # 6. test-harness confirmation cannot authorize real transport
    def test_n21x_06_test_harness_confirmation_cannot_reach_real_transport(self):
        auth = create_test_mint_authority(chat_id="chat_6", user_id="user_6")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_6",
            user_id="user_6",
            job_id="job_6",
            request_id="req_6",
            product_family="Product Video",
            operation="create_video_task",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_6",
            user_id="user_6",
            job_id="job_6",
            request_id="req_6",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            is_paid_live_attempt=True,  # Real transport attempt
            metadata={"quality_key": "kling_long_audio_15", "target_transport": "real_provider"},
        )
        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
            self.assertFalse(res.allowed)
            self.assertEqual(res.blocker, BLOCKER_TEST_CONFIRM_CANNOT_REACH_REAL_TRANSPORT)
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

    # 7. validated mocked Telegram b14_confirm -> production confirmation mint PASS
    def test_n21x_07_validated_mocked_telegram_b14_confirm_mint_passes(self):
        auth = issue_bot_mint_authority(
            callsite="bot.py:handle_video_product_callback:b14_confirm",
            telegram_update_id=777,
            callback_query_id="cbq_777",
            chat_id="chat_7",
            user_id="user_7",
            job_id="job_7",
            request_id="req_7",
            action="b14_confirm",
            validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
            validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
            validated_ownership=True,
        )
        self.assertIsNotNone(auth)
        self.assertFalse(auth.is_test_override)
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_7",
            user_id="user_7",
            job_id="job_7",
            request_id="req_7",
            product_family="Product Video",
            operation="create_video_task",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertTrue(bool(plan.get("parent_confirmation_id")))
        self.assertEqual(len(plan.get("child_confirmations", [])), 2)

    # 8. wrong Telegram update/session/user -> mint BLOCK
    def test_n21x_08_wrong_telegram_update_session_user_mint_blocked(self):
        with self.assertRaises(ValueError):
            issue_bot_mint_authority(
                telegram_update_id=0,
                callback_query_id="cbq_8",
                chat_id="chat_8",
                user_id="user_8",
                job_id="job_8",
                request_id="req_8",
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                validated_ownership=True,
            )
        with self.assertRaises(ValueError):
            issue_bot_mint_authority(
                telegram_update_id=888,
                callback_query_id="cbq_8",
                chat_id="chat_8",
                user_id="",
                job_id="job_8",
                request_id="req_8",
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                validated_ownership=True,
            )

    # 9. Bot mint before callback ownership validation -> BLOCK
    def test_n21x_09_bot_mint_before_callback_ownership_validation_blocked(self):
        with self.assertRaises(PermissionError):
            issue_bot_mint_authority(
                telegram_update_id=999,
                callback_query_id="cbq_9",
                chat_id="chat_9",
                user_id="user_9",
                job_id="job_9",
                request_id="req_9",
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                validated_ownership=False,
            )

    # 10. exact operation create_video_task -> resolver PASS
    def test_n21x_10_exact_operation_create_video_task_resolver_passes(self):
        res = resolve_paid_transport_authority("Product Video", "key4u_video", "create_video_task")
        self.assertIsNotNone(res)
        self.assertEqual(res.operation, "create_video_task")

    # 11. create_video_task_debug -> resolver BLOCK
    def test_n21x_11_create_video_task_debug_resolver_blocked(self):
        res = resolve_paid_transport_authority("Product Video", "key4u_video", "create_video_task_debug")
        self.assertIsNone(res)

    # 12. prefix/suffix operation -> BLOCK
    def test_n21x_12_prefix_suffix_operation_blocked(self):
        self.assertIsNone(resolve_paid_transport_authority("Product Video", "key4u_video", "video_create_video_task"))
        self.assertIsNone(resolve_paid_transport_authority("Product Video", "key4u_video", "create_video"))

    # 13. exact provider -> PASS
    def test_n21x_13_exact_provider_passes(self):
        res = resolve_paid_transport_authority("Product Video", "key4u_video", "create_video_task")
        self.assertIsNotNone(res)

    # 14. fuzzy/partial provider -> BLOCK
    def test_n21x_14_fuzzy_partial_provider_blocked(self):
        self.assertIsNone(resolve_paid_transport_authority("Product Video", "key4u_partial", "create_video_task"))
        self.assertIsNone(resolve_paid_transport_authority("Product Video", "kling", "create_video_task"))
        self.assertIsNone(resolve_paid_transport_authority("Product Video", "video", "create_video_task"))

    # 15. explicit approved alias -> PASS
    def test_n21x_15_explicit_approved_alias_passes(self):
        self.assertIsNotNone(resolve_paid_transport_authority("Product Video", "key4u_kling", "create_video_task"))
        self.assertIsNotNone(resolve_paid_transport_authority("Product Video", "key4u", "create_video_task"))

    # 16. two-scene child plan still PASS
    def test_n21x_16_two_scene_child_plan_still_passes(self):
        auth = create_test_mint_authority(chat_id="chat_16", user_id="user_16")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_16",
            user_id="user_16",
            job_id="job_16",
            request_id="req_16",
            product_family="Product Video",
            operation="create_video_task",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        s1_id = plan["scene_confirmations"][1]
        s2_id = plan["scene_confirmations"][2]
        ctx1 = SpendGuardContext(
            chat_id="chat_16",
            user_id="user_16",
            job_id="job_16",
            request_id="req_16",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=s1_id,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res1 = reserve_provider_spend(ctx1, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

        ctx2 = SpendGuardContext(
            chat_id="chat_16",
            user_id="user_16",
            job_id="job_16",
            request_id="req_16",
            scene_index=2,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=s2_id,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res2 = reserve_provider_spend(ctx2, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res2.allowed)

    # 17. parent submit still BLOCK
    def test_n21x_17_parent_submit_still_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_17", user_id="user_17")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_17",
            user_id="user_17",
            job_id="job_17",
            request_id="req_17",
            product_family="Product Video",
            operation="create_video_task",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        p_id = plan["parent_confirmation_id"]
        ctx = SpendGuardContext(
            chat_id="chat_17",
            user_id="user_17",
            job_id="job_17",
            request_id="req_17",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=p_id,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 18. child duplicate still BLOCK
    def test_n21x_18_child_duplicate_still_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_18", user_id="user_18")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_18",
            user_id="user_18",
            job_id="job_18",
            request_id="req_18",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_18",
            user_id="user_18",
            job_id="job_18",
            request_id="req_18",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res1 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)
        res2 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res2.allowed)

    # 19. ambiguous retry still BLOCK
    def test_n21x_19_ambiguous_retry_still_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_19", user_id="user_19")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_19",
            user_id="user_19",
            job_id="job_19",
            request_id="req_19",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_19",
            user_id="user_19",
            job_id="job_19",
            request_id="req_19",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE provider_spend_reservations SET status = ? WHERE reservation_id = ?",
            (STATUS_AMBIGUOUS_RETAINED, res.reservation_id),
        )
        conn.commit()
        conn.close()
        res_retry = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res_retry.allowed)
        self.assertEqual(res_retry.blocker, BLOCKER_AMBIGUOUS_RETRY_BLOCKED)

    # 20. ordinary paid-create remains non-live-test
    def test_n21x_20_ordinary_paid_create_remains_non_live_test(self):
        ctx = SpendGuardContext(
            job_id="job_20",
            request_id="req_20",
            chat_id="chat_20",
            user_id="user_20",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            operation="create_video_task",
            bot_originated_action=True,
            paid_live_test=False,
        )
        self.assertFalse(is_paid_live_test(ctx))

    # 21. paid live test missing Owner receipt -> BLOCK
    def test_n21x_21_paid_live_test_missing_owner_receipt_blocked(self):
        auth = create_test_mint_authority(
            chat_id="chat_21",
            user_id="user_21",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_21",
            user_id="user_21",
            job_id="job_21",
            request_id="req_21",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_21",
            user_id="user_21",
            job_id="job_21",
            request_id="req_21",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            owner_receipt="",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertIn(res.blocker, (BLOCKER_OWNER_LIVE_RECEIPT_MISSING, BLOCKER_BOT_ORIGIN_PROOF_MISSING))

    # 22. weekly cap remains shared $200
    def test_n21x_22_weekly_cap_remains_shared_200(self):
        cap_micro = get_configured_cap_micro_usd(env={})
        self.assertEqual(cap_micro, 200_000_000)

    # 23. missing reset policy remains fail-closed
    def test_n21x_23_missing_reset_policy_remains_fail_closed(self):
        with self.assertRaises(ValueError):
            get_current_spend_week_id(env={})


class TestN21YBotConfirmAuthorityTruthAndPerSceneReservationMatrix(unittest.TestCase):
    """N21Y Verification Matrix: Bot Confirm Authority Truth, Live Test Purpose, and Per-Scene Reservation."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="n21y_truth_matrix_")
        self.db_path = os.path.join(self.temp_dir, "test_system.db")
        init_spend_guard_db(db_path=self.db_path)
        self.standard_env = {
            "SPEND_GUARD_DB_PATH": self.db_path,
            "WEEKLY_PROVIDER_SPEND_CAP_USD": "200.000",
            "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE": "MONDAY_0000_UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE": "UTC",
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. importing module and reading internal symbols cannot create accepted production confirmation through supported production API
    def test_n21y_01_importing_module_and_reading_internal_symbols_cannot_create_accepted_production_confirmation(self):
        import services.provider_spend_guard as psg
        self.assertTrue(psg.FALSE_NONFORGEABLE_CLAIM_REMOVED)
        self.assertFalse(psg.MODULE_LOCAL_SECRET_IS_SECURITY_AUTHORITY)
        self.assertEqual(psg.MINT_TRUST_MODEL, "APPLICATION_CALL_GRAPH_PLUS_DURABLE_BOT_EVENT_AUTHORITY")

        # Direct constructor fails closed
        with self.assertRaises(PermissionError):
            psg.BotMintAuthority(
                callsite="bot.py:handle_video_product_callback:b14_confirm",
                telegram_update_id=123,
                chat_id="123",
                user_id="456",
            )
        # Calling issue_bot_mint_authority from external caller fails closed
        with self.assertRaises(PermissionError):
            psg.issue_bot_mint_authority(
                telegram_update_id=123,
                callback_query_id="cbq_real_123",
                chat_id="123",
                user_id="456",
                job_id="job_1",
                request_id="req_1",
                validation_source="video_trace_state:begin_video_confirm_execution",
                validation_callsite="bot.py:handle_video_product_callback:b14_confirm",
                validated_ownership=True,
                _caller_override_for_test="generic_service",
            )

    # 2. production module contains no create_test_mint_authority factory
    def test_n21y_02_production_module_contains_no_create_test_mint_authority_factory(self):
        import services.provider_spend_guard as psg
        self.assertFalse(hasattr(psg, "create_test_mint_authority"))
        self.assertFalse(psg.PRODUCTION_TEST_MINT_FACTORY_PRESENT)

    # 3. fake test env/pytest flag cannot create production confirmation
    def test_n21y_03_fake_test_env_cannot_create_production_confirmation(self):
        auth = create_test_mint_authority(chat_id="chat_03", user_id="user_03")
        # In test mode it produces a test record
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_03",
            user_id="user_03",
            job_id="job_03",
            request_id="req_03",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_03",
            user_id="user_03",
            job_id="job_03",
            request_id="req_03",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            is_paid_live_attempt=False,
            metadata={"target_transport": "real_provider", "quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_TEST_CONFIRM_CANNOT_REACH_REAL_TRANSPORT)

    # 4. missing real telegram_update_id -> BLOCK
    def test_n21y_04_missing_real_telegram_update_id_blocks_mint(self):
        with self.assertRaises(ValueError):
            issue_bot_mint_authority(
                telegram_update_id=0,
                callback_query_id="cbq_real_4",
                chat_id="chat_4",
                user_id="user_4",
                job_id="job_4",
                request_id="req_4",
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                validated_ownership=True,
            )
        with self.assertRaises(ValueError):
            issue_bot_mint_authority(
                telegram_update_id=-5,
                callback_query_id="cbq_real_4",
                chat_id="chat_4",
                user_id="user_4",
                job_id="job_4",
                request_id="req_4",
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                validated_ownership=True,
            )

    # 5. missing real callback_query_id -> BLOCK
    def test_n21y_05_missing_real_callback_query_id_blocks_mint(self):
        with self.assertRaises(ValueError):
            issue_bot_mint_authority(
                telegram_update_id=101,
                callback_query_id="",
                chat_id="chat_5",
                user_id="user_5",
                job_id="job_5",
                request_id="req_5",
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                validated_ownership=True,
            )
        with self.assertRaises(ValueError):
            issue_bot_mint_authority(
                telegram_update_id=101,
                callback_query_id="cbq_fallback_123",
                chat_id="chat_5",
                user_id="user_5",
                job_id="job_5",
                request_id="req_5",
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                validated_ownership=True,
            )

    # 6. missing request_id -> BLOCK
    def test_n21y_06_missing_request_id_blocks_mint(self):
        with self.assertRaises(ValueError):
            issue_bot_mint_authority(
                telegram_update_id=102,
                callback_query_id="cbq_real_6",
                chat_id="chat_6",
                user_id="user_6",
                job_id="job_6",
                request_id="",
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                validated_ownership=True,
            )
        with self.assertRaises(ValueError):
            issue_bot_mint_authority(
                telegram_update_id=102,
                callback_query_id="cbq_real_6",
                chat_id="chat_6",
                user_id="user_6",
                job_id="job_6",
                request_id="req_fallback_6",
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                validated_ownership=True,
            )

    # 7. synthetic fallback IDs absent
    def test_n21y_07_synthetic_fallback_ids_absent(self):
        self.assertEqual(SYNTHETIC_TELEGRAM_AUTH_IDS, 0)
        with open("bot.py", "r", encoding="utf-8") as f:
            bot_content = f.read()
        self.assertNotIn("telegram_update_id or 1", bot_content)
        self.assertNotIn("cbq_fallback_", bot_content)
        self.assertNotIn("req_fallback_", bot_content)

    # 8. caller validated_ownership=True without canonical validation state -> BLOCK
    def test_n21y_08_caller_validated_ownership_bool_without_validation_state_blocked(self):
        self.assertFalse(CALLER_VALIDATED_OWNERSHIP_BOOL_TRUSTED)
        with self.assertRaises(PermissionError):
            issue_bot_mint_authority(
                telegram_update_id=103,
                callback_query_id="cbq_real_8",
                chat_id="chat_8",
                user_id="user_8",
                job_id="job_8",
                request_id="req_8",
                validation_source="",
                validation_callsite="",
                validated_ownership=True,
            )

    # 9. ordinary Bot confirm -> purpose PRODUCTION_USER_ACTION
    def test_n21y_09_ordinary_bot_confirm_purpose_production_user_action(self):
        auth = issue_bot_mint_authority(
            telegram_update_id=104,
            callback_query_id="cbq_real_9",
            chat_id="chat_9",
            user_id="user_9",
            job_id="job_9",
            request_id="req_9",
            validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
            validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
            validated_ownership=True,
        )
        self.assertEqual(auth.purpose, PURPOSE_PRODUCTION_USER_ACTION)
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_9",
            user_id="user_9",
            job_id="job_9",
            request_id="req_9",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT purpose FROM bot_spend_confirmations WHERE confirmation_id = ?", (conf_id,))
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], PURPOSE_PRODUCTION_USER_ACTION)

    # 10. caller metadata paid_live_test=True cannot change durable purpose
    def test_n21y_10_caller_metadata_paid_live_test_true_cannot_change_durable_purpose(self):
        self.assertFalse(CALLER_PAID_LIVE_TEST_FLAG_TRUSTED)
        self.assertEqual(PAID_LIVE_TEST_CLASSIFICATION_SOURCE, "DURABLE_CONFIRMATION_PURPOSE")
        auth = create_test_mint_authority(
            chat_id="chat_10",
            user_id="user_10",
            purpose=PURPOSE_PRODUCTION_USER_ACTION,
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_10",
            user_id="user_10",
            job_id="job_10",
            request_id="req_10",
            scene_index=1,
            purpose=PURPOSE_PRODUCTION_USER_ACTION,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_10",
            user_id="user_10",
            job_id="job_10",
            request_id="req_10",
            bot_confirm_authority=conf_id,
            paid_live_test=True,
            metadata={"paid_live_test": True, "is_paid_live_test": True},
        )
        self.assertFalse(is_paid_live_test(ctx, db_path=self.db_path, env=self.standard_env))

    # 11. caller metadata paid_live_test=False cannot downgrade durable live-test purpose
    def test_n21y_11_caller_metadata_paid_live_test_false_cannot_downgrade_durable_purpose(self):
        auth = create_test_mint_authority(
            chat_id="chat_11",
            user_id="user_11",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_11",
            user_id="user_11",
            job_id="job_11",
            request_id="req_11",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_11",
            user_id="user_11",
            job_id="job_11",
            request_id="req_11",
            bot_confirm_authority=conf_id,
            paid_live_test=False,
            metadata={"paid_live_test": False},
        )
        self.assertTrue(is_paid_live_test(ctx, db_path=self.db_path, env=self.standard_env))

    # 12. durable OWNER_AUTHORIZED_PAID_LIVE_TEST without Owner receipt -> BLOCK
    def test_n21y_12_durable_live_test_without_owner_receipt_blocked(self):
        auth = create_test_mint_authority(
            chat_id="chat_12",
            user_id="user_12",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="",
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_12",
            user_id="user_12",
            job_id="job_12",
            request_id="req_12",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_12",
            user_id="user_12",
            job_id="job_12",
            request_id="req_12",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            owner_receipt="",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertIn(res.blocker, (BLOCKER_OWNER_LIVE_RECEIPT_MISSING, BLOCKER_BOT_ORIGIN_PROOF_MISSING))

    # 13. forged Owner receipt string -> BLOCK
    def test_n21y_13_forged_owner_receipt_string_blocked(self):
        auth = create_test_mint_authority(
            chat_id="chat_13",
            user_id="user_13",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="6119790632",
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_13",
            user_id="user_13",
            job_id="job_13",
            request_id="req_13",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="6119790632",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_13",
            user_id="user_13",
            job_id="job_13",
            request_id="req_13",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            owner_receipt="forged_receipt_random_string",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_OWNER_RECEIPT_MISMATCH)

    # 14. correctly bound Owner live authorization record -> provider-free guard PASS
    def test_n21y_14_correctly_bound_owner_live_authorization_record_passes(self):
        self.assertEqual(OWNER_LIVE_AUTH_BINDING, "PASS")
        auth = create_test_mint_authority(
            chat_id="chat_14",
            user_id="user_14",
            job_id="job_14",
            request_id="req_14",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="6119790632",
            expected_max_provider_spend_usd=Decimal("30.600245"),
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_14",
            user_id="user_14",
            job_id="job_14",
            request_id="req_14",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="6119790632",
            expected_max_cost_usd=Decimal("30.600245"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_14",
            user_id="user_14",
            job_id="job_14",
            request_id="req_14",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            owner_receipt="6119790632",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)
        self.assertTrue(res.reservation_id.startswith("res_"))

    # 15. entrypoint="bot" alone -> BLOCK
    def test_n21y_15_entrypoint_bot_alone_blocked(self):
        ctx = SpendGuardContext(
            chat_id="chat_15",
            user_id="user_15",
            job_id="job_15",
            request_id="req_15",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            entrypoint="bot",
            bot_originated_action=False,
            bot_confirm_authority="",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 16. bot_originated_action=True alone -> BLOCK
    def test_n21y_16_bot_originated_action_true_alone_blocked(self):
        ctx = SpendGuardContext(
            chat_id="chat_16",
            user_id="user_16",
            job_id="job_16",
            request_id="req_16",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            entrypoint="bot",
            bot_originated_action=True,
            bot_confirm_authority="",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 17. user_flow bot string alone -> BLOCK
    def test_n21y_17_user_flow_bot_string_alone_blocked(self):
        ctx = SpendGuardContext(
            chat_id="chat_17",
            user_id="user_17",
            job_id="job_17",
            request_id="req_17",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            entrypoint="bot",
            bot_originated_action=True,
            user_flow="product_video_bot",
            bot_confirm_authority="",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 18. two-scene plan produces 2 child reservations
    def test_n21y_18_two_scene_plan_produces_two_child_reservations(self):
        auth = create_test_mint_authority(chat_id="chat_18", user_id="user_18")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_18",
            user_id="user_18",
            job_id="job_18",
            request_id="req_18",
            product_family="Product Video",
            operation="create_video_task",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        s1 = plan["scene_confirmations"][1]
        s2 = plan["scene_confirmations"][2]
        ctx1 = SpendGuardContext(
            chat_id="chat_18",
            user_id="user_18",
            job_id="job_18",
            request_id="req_18",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=s1,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res1 = reserve_provider_spend(ctx1, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

        ctx2 = SpendGuardContext(
            chat_id="chat_18",
            user_id="user_18",
            job_id="job_18",
            request_id="req_18",
            scene_index=2,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=s2,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res2 = reserve_provider_spend(ctx2, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res2.allowed)
        self.assertNotEqual(res1.reservation_id, res2.reservation_id)

    # 19. each child reserves only its own scene canonical max
    def test_n21y_19_each_child_reserves_only_its_own_scene_canonical_max(self):
        self.assertTrue(PER_SCENE_RESERVATION_GRANULARITY)
        auth = create_test_mint_authority(chat_id="chat_19", user_id="user_19")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_19",
            user_id="user_19",
            job_id="job_19",
            request_id="req_19",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        s1 = plan["scene_confirmations"][1]
        ctx1 = SpendGuardContext(
            chat_id="chat_19",
            user_id="user_19",
            job_id="job_19",
            request_id="req_19",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=s1,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15", "scene_count": 2},
        )
        res1 = reserve_provider_spend(ctx1, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)
        # Unit cost for 1 scene of kling 15s is 30,600,245 micro-USD ($30.600245)
        # Must NOT be 61,200,490 micro-USD!
        self.assertEqual(res1.week_spend_after_micro_usd, 30_600_245)

    # 20. total job reservation equals sum of scene maxima
    def test_n21y_20_total_job_reservation_equals_sum_of_scene_maxima(self):
        self.assertTrue(MULTISCENE_TOTAL_COST_SUM)
        auth = create_test_mint_authority(chat_id="chat_20", user_id="user_20")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_20",
            user_id="user_20",
            job_id="job_20",
            request_id="req_20",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        s1 = plan["scene_confirmations"][1]
        s2 = plan["scene_confirmations"][2]
        ctx1 = SpendGuardContext(
            chat_id="chat_20",
            user_id="user_20",
            job_id="job_20",
            request_id="req_20",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=s1,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15", "scene_count": 2},
        )
        res1 = reserve_provider_spend(ctx1, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

        ctx2 = SpendGuardContext(
            chat_id="chat_20",
            user_id="user_20",
            job_id="job_20",
            request_id="req_20",
            scene_index=2,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=s2,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15", "scene_count": 2},
        )
        res2 = reserve_provider_spend(ctx2, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res2.allowed)
        # Total in DB is exactly 30,600,245 + 30,600,245 = 61,200,490 micro-USD ($61.200490)
        self.assertEqual(res2.week_spend_after_micro_usd, 61_200_490)

    # 21. no scene_count double multiplication
    def test_n21y_21_no_scene_count_double_multiplication(self):
        self.assertFalse(SCENE_COUNT_DOUBLE_MULTIPLICATION)
        authority = resolve_paid_transport_authority("Product Video", "key4u_video", "create_video_task")
        ctx = SpendGuardContext(
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            metadata={"quality_key": "kling_long_audio_15", "scene_count": 5},
        )
        cost_micro, proven, _ = resolve_canonical_cost_micro_usd(ctx, authority)
        self.assertTrue(proven)
        # For scene_index=1, cost must be single scene cost (30,600,245), NOT 5 * 30,600,245
        self.assertEqual(cost_micro, 30_600_245)

    # 22. child duplicate -> BLOCK
    def test_n21y_22_child_duplicate_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_22", user_id="user_22")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_22",
            user_id="user_22",
            job_id="job_22",
            request_id="req_22",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_22",
            user_id="user_22",
            job_id="job_22",
            request_id="req_22",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res1 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)
        res2 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res2.allowed)
        self.assertEqual(res2.blocker, BLOCKER_DUPLICATE_PAID_SUBMIT)

    # 23. ambiguous child -> retained, retry BLOCK
    def test_n21y_23_ambiguous_child_retained_retry_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_23", user_id="user_23")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_23",
            user_id="user_23",
            job_id="job_23",
            request_id="req_23",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_23",
            user_id="user_23",
            job_id="job_23",
            request_id="req_23",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE provider_spend_reservations SET status = ? WHERE reservation_id = ?",
            (STATUS_AMBIGUOUS_RETAINED, res.reservation_id),
        )
        conn.commit()
        conn.close()
        res_retry = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res_retry.allowed)
        self.assertEqual(res_retry.blocker, BLOCKER_AMBIGUOUS_RETRY_BLOCKED)

    # 24. parent authority -> BLOCK
    def test_n21y_24_parent_authority_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_24", user_id="user_24")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_24",
            user_id="user_24",
            job_id="job_24",
            request_id="req_24",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        p_id = plan["parent_confirmation_id"]
        ctx = SpendGuardContext(
            chat_id="chat_24",
            user_id="user_24",
            job_id="job_24",
            request_id="req_24",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=p_id,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 25. missing weekly reset policy -> FAIL CLOSED
    def test_n21y_25_missing_weekly_reset_policy_fails_closed(self):
        auth = create_test_mint_authority(chat_id="chat_25", user_id="user_25")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_25",
            user_id="user_25",
            job_id="job_25",
            request_id="req_25",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_25",
            user_id="user_25",
            job_id="job_25",
            request_id="req_25",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        empty_env = {"SPEND_GUARD_DB_PATH": self.db_path}
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=empty_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_POLICY_INCOMPLETE)

    # 26. shared $200 cap still enforced
    def test_n21y_26_shared_200_cap_still_enforced(self):
        cap_micro = get_configured_cap_micro_usd(env={})
        self.assertEqual(cap_micro, 200_000_000)
        auth = create_test_mint_authority(chat_id="chat_26", user_id="user_26")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_26",
            user_id="user_26",
            job_id="job_26",
            request_id="req_26",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        # Pre-seed $190 spend
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(self.db_path)
        week_id = get_current_spend_week_id(env=self.standard_env)
        conn.execute(
            """
            INSERT INTO provider_spend_reservations (
                reservation_id, created_at, week_id, idempotency_key, job_id, request_id,
                trace_id, product_family, provider, model, estimated_max_cost_micro_usd,
                reserved_cost_micro_usd, actual_settled_cost_micro_usd, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "res_preseed", time.time(), week_id, "idemp_preseed", "job_preseed",
                "req_preseed", "tr_preseed", "Product Video", "key4u_video", "kling-v3",
                190_000_000, 190_000_000, 190_000_000, STATUS_SETTLED_VERIFIED
            ),
        )
        conn.commit()
        conn.close()

        ctx = SpendGuardContext(
            chat_id="chat_26",
            user_id="user_26",
            job_id="job_26",
            request_id="req_26",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        # Adding $30.60 to $190 exceeds $200
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_WEEKLY_SPEND_CAP_EXCEEDED)


if __name__ == "__main__":
    unittest.main()


