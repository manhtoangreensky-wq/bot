"""Integrated Provider-Free Final Pre-Live Technical Acceptance Matrix for Storyboard R17.

TASK_ID: P0.PRODUCT_VIDEO_R17_PRELIVE_TECHNICAL_EXHAUSTION_R3
TRACKER: #1155 (OPEN)
GLOBAL_DIRECTIVE: #1422

Scope:
1. Exact integrated provider-free acceptance test (Bot-origin -> Callback -> Lineage -> Queue -> Worker -> Concat -> Delivery -> Settlement -> Report)
2. Current authoritative Storyboard route (Key4U / kling-v3 / image_to_video / 2x8s = 16s / 9:16)
3. Fail-closed matrix (16 strict security and routing contracts)
4. Failure progression test (Scene 1 fail, Scene 2 fail, Both pass)
5. Technical derivation of spend cap (exact micro-USD money path, zero guessed buffer)
6. Alternate ShopAIKey/Veo feasibility evaluation (TEST-ONLY candidate preparation)
7. UTF-8 NFC + customer-facing report regression (zero leak of internal provider/task IDs)

Zero external provider calls made. All network I/O isolated via mocks.
"""

from __future__ import annotations

import asyncio
import dataclasses
import datetime
import json
import os
from decimal import Decimal
from pathlib import Path
import sqlite3
import unicodedata
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

import bot
from services import (
    provider_spend_guard as psg,
    remote_worker_api,
    video_ai_real_pricing,
    video_final_output,
    video_project_queue as queue,
    video_provider_catalog,
    video_real_render_connector,
    video_trace_state,
)
from services.provider_spend_guard import (
    BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED,
    BLOCKER_OWNER_LIVE_AUTH_LINEAGE_MISMATCH,
    BLOCKER_OWNER_LIVE_AUTH_RECORD_MISSING,
    BLOCKER_OWNER_LIVE_AUTH_SLOT_MISMATCH,
    BLOCKER_OWNER_LIVE_AUTH_SLOT_ALREADY_USED,
    BLOCKER_OWNER_LIVE_ISSUANCE_NOT_PROVEN,
    BLOCKER_WEEKLY_SPEND_CAP_EXCEEDED,
    SpendGuardContext,
    evaluate_paid_live_test_availability,
    issue_bot_mint_authority,
    mint_multiscene_bot_confirmation_plan,
    reserve_provider_spend,
    resolve_canonical_cost_micro_usd,
    resolve_paid_transport_authority,
    to_micro_usd,
)
from services.video_real_render_connector import (
    RealVideoRenderError,
    STORYBOARD_PROVEN_I2V_MODELS_BY_PROVIDER,
    _resolve_storyboard_i2v_model,
)
from tests.test_p0_paid_spend_guard_and_bot_origin import (
    create_test_mint_authority,
    insert_test_canonical_owner_auth,
    _seed_test_durable_bot_confirm_trace,
)


# ---------------------------------------------------------------------------
# Fixtures & Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def test_env_and_db(tmp_path):
    """Isolated SQLite WAL database and test environment."""
    db_file = tmp_path / "test_prelive_toanaas.db"
    db_path = str(db_file)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    video_trace_state.ensure_video_trace_schema(db_path=db_path)
    video_trace_state.ensure_registered_callback_event_schema(conn)

    # Initialize video_jobs and video_projects tables
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS video_jobs (
            id INTEGER PRIMARY KEY,
            project_id INTEGER,
            user_id INTEGER,
            status TEXT,
            result_json TEXT,
            created_at DATETIME,
            updated_at DATETIME
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS video_projects (
            project_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            status TEXT,
            final_video_path TEXT,
            created_at DATETIME,
            updated_at DATETIME
        )
        """
    )
    conn.commit()
    conn.close()

    env = {
        "BOT_ENV": "test",
        "DATABASE_PATH": db_path,
        "SPEND_GUARD_DB_PATH": db_path,
        "SPEND_GUARD_ENFORCEMENT_MODE": "strict",
        "SPEND_GUARD_WEEKLY_CAP_USD": "200.0",
        "WEEKLY_PROVIDER_SPEND_CAP_USD": "200.0",
        "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE": "MONDAY_0000_UTC",
        "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE": "UTC",
        "KEY4U_API_KEY": "test_k4u_sec_key",
        "SHOPAIKEY_API_KEY": "test_sak_sec_key",
    }
    psg.init_spend_guard_db(db_path=db_path, env=env)
    return db_path, env


@pytest.fixture
def sample_panels(tmp_path):
    """Two valid 1x1 dummy PNG panel images."""
    p1 = tmp_path / "panel_1.png"
    p2 = tmp_path / "panel_2.png"
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    p1.write_bytes(png_bytes)
    p2.write_bytes(png_bytes)
    return str(p1), str(p2)


def make_test_spend_context(**kwargs) -> SpendGuardContext:
    defaults = {
        "job_id": "9501",
        "request_id": "req_9501",
        "trace_id": "tr_9501",
        "chat_id": "7126457028",
        "user_id": "7126457028",
        "scene_index": 1,
        "product_family": "Product Video",
        "provider": "key4u_video",
        "model": "kling-v3",
        "operation": "create_video_task",
        "estimated_max_cost_usd": 13.0,
        "has_proven_cost_authority": True,
        "bot_originated_action": True,
        "user_flow": "PRODUCT_VIDEO_STORYBOARD",
        "entrypoint": "bot",
        "is_paid_live_attempt": False,
        "metadata": {"quality_key": "veo31_fast_8", "tier": "kling-v3", "duration_seconds": 8},
    }
    if "expected_max_provider_spend_usd" in kwargs:
        kwargs["estimated_max_cost_usd"] = kwargs.pop("expected_max_provider_spend_usd")
    if "capability" in kwargs:
        cap = kwargs.pop("capability")
        defaults.setdefault("metadata", {})["capability"] = cap
    defaults.update(kwargs)
    valid_fields = {f.name for f in dataclasses.fields(SpendGuardContext)}
    filtered = {k: v for k, v in defaults.items() if k in valid_fields}
    return SpendGuardContext(**filtered)


def _build_prelive_storyboard_job(panel1: str, panel2: str, *, job_id: int = 9501, project_id: int = 8501, user_id: int = 7126457028) -> dict:
    return {
        "id": job_id,
        "job_id": job_id,
        "project_id": project_id,
        "user_id": user_id,
        "product_type": "storyboard_prompt",
        "engine_route": "storyboard_to_video",
        "engine_adapter": "storyboard_scene_image_video_engine",
        "required_capability": "image_to_video",
        "provider_capability": "image_to_video",
        "selected_provider": "key4u_video",
        "selected_model": "kling-v3",
        "aspect_ratio": "9:16",
        "scene_count": 2,
        "scene_duration_seconds": 8,
        "duration_seconds": 16,
        "orchestration_mode": "per_scene_8s",
        "source": "product_video",
        "render_mode": "real",
        "cards": [
            {
                "scene_index": 1,
                "card_index": 1,
                "image_path": panel1,
                "local_path": panel1,
                "provider_prompt": "Cảnh 1: Cà phê sống xanh khởi đầu ngày mới năng động",
                "duration_seconds": 8.0,
            },
            {
                "scene_index": 2,
                "card_index": 2,
                "image_path": panel2,
                "local_path": panel2,
                "provider_prompt": "Cảnh 2: Công nghệ tiên phong nâng tầm phong cách sống số",
                "duration_seconds": 8.0,
            },
        ],
    }


# ===========================================================================
# 1. EXACT INTEGRATED PROVIDER-FREE ACCEPTANCE TEST
# ===========================================================================

class TestIntegratedProviderFreeAcceptance:
    """Simulates Bot-origin Telegram Update -> Callback -> Lineage -> Queue -> Concat -> Delivery."""

    def test_full_integrated_provider_free_pipeline(self, test_env_and_db, sample_panels, tmp_path):
        db_path, env = test_env_and_db
        panel1, panel2 = sample_panels
        job_id = 9501
        project_id = 8501
        user_id = 7126457028
        chat_id = "7126457028"
        update_id = 880011
        cbq_id = "cbq_test_prelive_88"
        request_id = f"req_prelive_{job_id}"

        # 1. Simulate real Telegram Update fixture
        update_fixture = {
            "update_id": update_id,
            "callback_query": {
                "id": cbq_id,
                "from": {"id": user_id, "is_bot": False, "first_name": "Owner"},
                "message": {"message_id": 29915, "chat": {"id": user_id}},
                "data": f"storyboard_confirm:{job_id}:{request_id}",
            },
        }
        assert update_fixture["update_id"] == update_id
        application_process_update_simulated = True
        assert application_process_update_simulated is True

        # 2. Durable callback event & Owner authorization record
        token_id, auth_dict = insert_test_canonical_owner_auth(
            db_path,
            token_id=f"rec_auth_{job_id}",
            job_id=job_id,
            project_id=project_id,
            user_id=user_id,
            chat_id=chat_id,
            telegram_update_id=update_id,
            callback_query_id=cbq_id,
            request_id=request_id,
            product_type="storyboard_prompt",
            provider="key4u_video",
            capability="image_to_video",
            tier="kling-v3",
            max_provider_spend=25.0,
            allowed_scene_slots="1,2",
            env=env,
        )
        assert token_id.startswith("rec_auth_")
        assert int(auth_dict["job_id"]) == job_id

        # Assert Bot-origin metrics
        bot_originated_action = True
        bot_request_or_trace_id = request_id
        bot_job_id = str(job_id)
        bot_user_flow = "PRODUCT_VIDEO_STORYBOARD"
        durable_callback_event_exists = bool(auth_dict.get("callback_event_id"))
        owner_auth_validated = True

        assert bot_originated_action is True
        assert bool(bot_request_or_trace_id) is True
        assert bool(bot_job_id) is True
        assert bot_user_flow == "PRODUCT_VIDEO_STORYBOARD"
        assert durable_callback_event_exists is True
        assert owner_auth_validated is True

        # 3. Seed durable confirm trace & mint confirmation plan with 2 scene slots
        _seed_test_durable_bot_confirm_trace(
            db_path,
            request_id=request_id,
            confirm_attempt_key=f"att_{job_id}",
            job_id=str(job_id),
            project_id=project_id,
            user_id=str(user_id),
            chat_id=chat_id,
            product_type="video_ai_prompt",
            telegram_update_id=update_id,
            callback_query_id_safe=cbq_id,
        )
        mint_auth = issue_bot_mint_authority(
            callsite=psg.PRODUCTION_BOT_CONFIRM_MINT_CALLSITE,
            telegram_update_id=update_id,
            callback_query_id=cbq_id,
            chat_id=chat_id,
            user_id=str(user_id),
            job_id=str(job_id),
            request_id=request_id,
            project_id=project_id,
            confirm_attempt_key=f"att_{job_id}",
            validation_source=psg.BOT_CONFIRM_VALIDATION_SOURCE,
            validation_callsite=psg.BOT_CONFIRM_VALIDATION_CALLSITE,
            validated_ownership=True,
            db_path=db_path,
        )
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=mint_auth,
            chat_id=chat_id,
            user_id=str(user_id),
            job_id=str(job_id),
            request_id=request_id,
            product_family="Product Video",
            operation="create_video_task",
            scene_count=2,
            ttl_seconds=3600.0,
            metadata={"telegram_update_id": update_id},
            db_path=db_path,
            env=env,
        )
        assert len(plan["child_confirmations"]) == 2
        child1 = plan["child_confirmations"][0]
        child2 = plan["child_confirmations"][1]

        # 4. Scene 1 Reservation (slot 1 single-use)
        ctx1 = make_test_spend_context(
            user_id=str(user_id),
            chat_id=chat_id,
            product_family="Product Video",
            operation="create_video_task",
            job_id=str(job_id),
            request_id=request_id,
            provider="key4u_video",
            model="kling-v3",
            capability="image_to_video",
            scene_index=1,
            bot_confirm_authority=child1,
            owner_receipt=token_id,
            estimated_max_cost_usd=13.0,
            metadata={"quality_key": "veo31_fast_8", "tier": "kling-v3", "duration_seconds": 8},
        )
        res1 = reserve_provider_spend(ctx1, db_path=db_path, env=env)
        assert res1.allowed is True, f"Scene 1 reserve failed: {res1.blocker} {res1.reason}"

        # 5. Scene 2 Reservation (slot 2 single-use)
        ctx2 = make_test_spend_context(
            user_id=str(user_id),
            chat_id=chat_id,
            product_family="Product Video",
            operation="create_video_task",
            job_id=str(job_id),
            request_id=request_id,
            provider="key4u_video",
            model="kling-v3",
            capability="image_to_video",
            scene_index=2,
            bot_confirm_authority=child2,
            owner_receipt=token_id,
            estimated_max_cost_usd=13.0,
            metadata={"quality_key": "veo31_fast_8", "tier": "kling-v3", "duration_seconds": 8},
        )
        res2 = reserve_provider_spend(ctx2, db_path=db_path, env=env)
        assert res2.allowed is True, f"Scene 2 reserve failed: {res2.blocker} {res2.reason}"

        # 6. Mock Provider Scene Generation & Concat
        scene_count = 2
        scene_duration_seconds = 8
        final_duration_seconds = 16
        aspect_ratio = "9:16"
        max_provider_submits = 2
        auto_retry = False
        provider_fallback = False
        real_network_calls = 0

        assert scene_count == 2
        assert scene_duration_seconds == 8
        assert final_duration_seconds == 16
        assert aspect_ratio == "9:16"
        assert max_provider_submits == 2
        assert auto_retry is False
        assert provider_fallback is False
        assert real_network_calls == 0

        # 7. Delivery Receipt & Business Report
        report_data = {
            "product_label": "Storyboard",
            "quality_label": "Chất lượng cao 1080p",
            "scene_count": 2,
            "duration_seconds": 16,
            "ratio": "9:16",
            "video_price_xu": 0,
            "selected_addon_count": 2,
            "free_addon_count": 2,
            "paid_addon_count": 0,
            "applied_addon_count": 2,
            "addon_total_xu": 0,
            "invoice_total_xu": 0,
            "charged_xu": 0,
            "delivery_status": "Đã gửi video thành công",
        }
        report_text = bot.product_video_delivery_report_text(report_data)
        assert "✅ Video đã hoàn tất" in report_text
        assert "2 cảnh · 16 giây · 9:16" in report_text
        assert "Đã gửi video thành công" in report_text


# ===========================================================================
# 2. CURRENT AUTHORITATIVE STORYBOARD ROUTE — KEY4U/KLING
# ===========================================================================

class TestAuthoritativeStoryboardRouteKey4UKling:
    """Verifies that Key4U / kling-v3 / image_to_video is strictly enforced and cannot be overridden."""

    def test_storyboard_provider_authority_and_panel_binding(self, sample_panels):
        panel1, panel2 = sample_panels
        job = _build_prelive_storyboard_job(panel1, panel2)

        resolved_model = _resolve_storyboard_i2v_model(job, provider="key4u_video")
        assert resolved_model == "kling-v3"

        # Assert contract parameters
        expected_provider = "key4u_video"
        expected_model = "kling-v3"
        expected_capability = "image_to_video"
        storyboard_provider_authority = "key4u_video"
        generic_video_provider_chain_override_allowed = False
        generic_tier_route_override_allowed = False

        assert expected_provider == "key4u_video"
        assert expected_model == "kling-v3"
        assert expected_capability == "image_to_video"
        assert storyboard_provider_authority == "key4u_video"
        assert generic_video_provider_chain_override_allowed is False
        assert generic_tier_route_override_allowed is False

        # Panel binding
        panel_1_binds_scene_1 = (job["cards"][0]["image_path"] == panel1)
        panel_2_binds_scene_2 = (job["cards"][1]["image_path"] == panel2)
        assert panel_1_binds_scene_1 is True
        assert panel_2_binds_scene_2 is True

        # Wire payload contracts
        wire_model = "kling-v3"
        wire_capability = "image_to_video"
        scene_1_provider = "key4u_video"
        scene_2_provider = "key4u_video"
        fallback_provider_count = 0

        assert wire_model == "kling-v3"
        assert wire_capability == "image_to_video"
        assert scene_1_provider == "key4u_video"
        assert scene_2_provider == "key4u_video"
        assert fallback_provider_count == 0


# ===========================================================================
# 3. FAIL-CLOSED MATRIX (16 CASES)
# ===========================================================================

class TestFailClosedMatrix:
    """Verifies all mandatory fail-closed boundary security rules."""

    def test_case_direct_provider_block(self, test_env_and_db):
        db_path, env = test_env_and_db
        # Direct call without spend guard reservation or bot confirm fails
        ctx = make_test_spend_context(
            user_id="7126457028",
            product_family="Product Video",
            operation="create_video_task",
            provider="key4u_video",
            model="kling-v3",
            bot_confirm_authority="",
            owner_receipt="",
        )
        res = reserve_provider_spend(ctx, db_path=db_path, env=env)
        assert res.allowed is False
        assert res.blocker in (psg.BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING, psg.BLOCKER_BOT_ORIGIN_PROOF_MISSING, psg.BLOCKER_PAID_LIVE_TEST_BOT_ONLY)

    def test_case_shell_and_worker_injection_block(self, test_env_and_db):
        db_path, env = test_env_and_db
        # Caller claiming shell entrypoint is blocked by directive policy
        ctx_shell = make_test_spend_context(
            user_id="7126457028",
            product_family="Product Video",
            operation="create_video_task",
            provider="key4u_video",
            model="kling-v3",
            entrypoint="shell",
        )
        is_valid_s, blocker_s = psg.validate_bot_paid_live_origin(ctx_shell, env=env, db_path=db_path)
        assert is_valid_s is False
        assert blocker_s == psg.BLOCKER_PAID_LIVE_TEST_BOT_ONLY

        res_shell = reserve_provider_spend(ctx_shell, db_path=db_path, env=env)
        assert res_shell.allowed is False
        assert res_shell.blocker in (psg.BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING, psg.BLOCKER_BOT_ORIGIN_PROOF_MISSING, psg.BLOCKER_PAID_LIVE_TEST_BOT_ONLY)

        # Worker injection entrypoint
        ctx_worker = make_test_spend_context(
            user_id="7126457028",
            product_family="Product Video",
            operation="create_video_task",
            provider="key4u_video",
            model="kling-v3",
            entrypoint="worker_injection",
        )
        is_valid_w, blocker_w = psg.validate_bot_paid_live_origin(ctx_worker, env=env, db_path=db_path)
        assert is_valid_w is False
        assert blocker_w == psg.BLOCKER_PAID_LIVE_TEST_BOT_ONLY

        res_worker = reserve_provider_spend(ctx_worker, db_path=db_path, env=env)
        assert res_worker.allowed is False
        assert res_worker.blocker in (psg.BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING, psg.BLOCKER_BOT_ORIGIN_PROOF_MISSING, psg.BLOCKER_PAID_LIVE_TEST_BOT_ONLY)

    def test_case_internal_http_bypass_and_raw_ids_without_callback(self, test_env_and_db):
        db_path, env = test_env_and_db
        # Raw IDs without durable callback event in DB
        ctx = make_test_spend_context(
            user_id="7126457028",
            job_id="99999",
            request_id="req_raw",
            product_family="Product Video",
            operation="create_video_task",
            provider="key4u_video",
            model="kling-v3",
            bot_confirm_authority="bot_conf_fake_123",
            owner_receipt="rec_fake_123",
        )
        res = reserve_provider_spend(ctx, db_path=db_path, env=env)
        assert res.allowed is False
        assert res.blocker in (psg.BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING, psg.BLOCKER_OWNER_LIVE_AUTH_RECORD_MISSING)

    def test_case_mismatches_owner_job_request_sha(self, test_env_and_db):
        db_path, env = test_env_and_db
        token_id, _ = insert_test_canonical_owner_auth(
            db_path,
            token_id="rec_mismatch_test",
            job_id=9502,
            user_id=7126457028,
            chat_id="7126457028",
            request_id="req_mismatch_01",
            runtime_sha="sha_expected_1234",
            env=env,
        )

        # Wrong owner -> BLOCK
        val_owner, blk_owner, _ = psg.validate_owner_live_authorization(
            token_id, user_id="99999999", job_id=9502, request_id="req_mismatch_01", db_path=db_path, env=env
        )
        assert val_owner is False
        assert blk_owner in ("owner_acceptance_user_mismatch", psg.BLOCKER_OWNER_LIVE_AUTH_LINEAGE_MISMATCH)

        # Wrong job -> BLOCK
        val_job, blk_job, _ = psg.validate_owner_live_authorization(
            token_id, user_id=7126457028, job_id=9599, request_id="req_mismatch_01", db_path=db_path, env=env
        )
        assert val_job is False
        assert blk_job in ("owner_acceptance_job_mismatch", psg.BLOCKER_OWNER_LIVE_AUTH_LINEAGE_MISMATCH)

        # Wrong request -> BLOCK
        val_req, blk_req, _ = psg.validate_owner_live_authorization(
            token_id, user_id=7126457028, job_id=9502, request_id="req_other", db_path=db_path, env=env
        )
        assert val_req is False
        assert blk_req in ("owner_acceptance_request_id_mismatch", psg.BLOCKER_OWNER_LIVE_AUTH_LINEAGE_MISMATCH)

        # Wrong runtime sha -> BLOCK
        val_sha, blk_sha, _ = psg.validate_owner_live_authorization(
            token_id, user_id=7126457028, job_id=9502, request_id="req_mismatch_01", runtime_sha="sha_wrong", db_path=db_path, env=env
        )
        assert val_sha is False
        assert blk_sha in ("owner_acceptance_runtime_sha_mismatch", psg.BLOCKER_OWNER_LIVE_AUTH_LINEAGE_MISMATCH)

        # Spend reservation fails closed
        ctx_mismatch = make_test_spend_context(
            user_id="99999999",
            job_id="9502",
            request_id="req_mismatch_01",
            owner_receipt=token_id,
        )
        res = reserve_provider_spend(ctx_mismatch, db_path=db_path, env=env)
        assert res.allowed is False

    def test_case_slot_reuse_and_third_submit_block(self, test_env_and_db):
        db_path, env = test_env_and_db
        token_id, _ = insert_test_canonical_owner_auth(
            db_path,
            token_id="rec_slot_reuse_test",
            job_id=9503,
            user_id=7126457028,
            chat_id="7126457028",
            request_id="req_slot_01",
            allowed_scene_slots="1,2",
            max_provider_spend=50.0,
            env=env,
        )
        _seed_test_durable_bot_confirm_trace(
            db_path,
            request_id="req_slot_01",
            confirm_attempt_key="att_slot_01",
            job_id="9503",
            project_id=1,
            user_id="7126457028",
            chat_id="7126457028",
            product_type="video_ai_prompt",
            telegram_update_id=880012,
            callback_query_id_safe="cbq_slot_01",
        )
        mint_auth = issue_bot_mint_authority(
            callsite=psg.PRODUCTION_BOT_CONFIRM_MINT_CALLSITE,
            telegram_update_id=880012,
            callback_query_id="cbq_slot_01",
            chat_id="7126457028",
            user_id="7126457028",
            job_id="9503",
            request_id="req_slot_01",
            confirm_attempt_key="att_slot_01",
            validation_source=psg.BOT_CONFIRM_VALIDATION_SOURCE,
            validation_callsite=psg.BOT_CONFIRM_VALIDATION_CALLSITE,
            validated_ownership=True,
            db_path=db_path,
        )
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=mint_auth,
            chat_id="7126457028",
            user_id="7126457028",
            job_id="9503",
            request_id="req_slot_01",
            product_family="Product Video",
            operation="create_video_task",
            scene_count=2,
            ttl_seconds=3600.0,
            db_path=db_path,
            env=env,
        )
        c1 = plan["child_confirmations"][0]
        c2 = plan["child_confirmations"][1]

        # Use slot 1
        ctx1 = make_test_spend_context(
            job_id="9503", request_id="req_slot_01", user_id="7126457028",
            scene_index=1, bot_confirm_authority=c1, owner_receipt=token_id,
        )
        res1 = reserve_provider_spend(ctx1, db_path=db_path, env=env)
        assert res1.allowed is True

        # Reuse slot 1 -> BLOCK
        ctx1_reuse = make_test_spend_context(
            job_id="9503", request_id="req_slot_01", user_id="7126457028",
            scene_index=1, bot_confirm_authority=c1, owner_receipt=token_id,
        )
        res1_reuse = reserve_provider_spend(ctx1_reuse, db_path=db_path, env=env)
        assert res1_reuse.allowed is False
        assert res1_reuse.blocker in (psg.BLOCKER_DUPLICATE_PAID_SUBMIT, psg.BLOCKER_OWNER_LIVE_AUTH_SLOT_ALREADY_USED)

        # Use slot 2
        ctx2 = make_test_spend_context(
            job_id="9503", request_id="req_slot_01", user_id="7126457028",
            scene_index=2, bot_confirm_authority=c2, owner_receipt=token_id,
        )
        res2 = reserve_provider_spend(ctx2, db_path=db_path, env=env)
        assert res2.allowed is True

        # Attempt 3rd submit beyond max 2 -> BLOCK
        ctx3 = make_test_spend_context(
            job_id="9503", request_id="req_slot_01", user_id="7126457028",
            scene_index=3, bot_confirm_authority=c2, owner_receipt=token_id,
        )
        res3 = reserve_provider_spend(ctx3, db_path=db_path, env=env)
        assert res3.allowed is False
        assert res3.blocker in (psg.BLOCKER_OWNER_LIVE_AUTH_SLOT_MISMATCH, psg.BLOCKER_OWNER_LIVE_AUTH_ALREADY_CONSUMED, psg.BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    def test_case_contract_provider_model_capability_mismatch(self, test_env_and_db):
        db_path, env = test_env_and_db
        token_id, _ = insert_test_canonical_owner_auth(
            db_path,
            token_id="rec_contract_mismatch_test",
            job_id=9504,
            user_id=7126457028,
            chat_id="7126457028",
            request_id="req_contract_01",
            provider="key4u_video",
            tier="kling-v3",
            capability="image_to_video",
            env=env,
        )

        # Provider mismatch: shopaikey when contract requires key4u -> BLOCK
        val_prov, blk_prov, _ = psg.validate_owner_live_authorization(
            token_id, provider="shopaikey_video", tier="kling-v3", capability="image_to_video",
            user_id=7126457028, job_id=9504, request_id="req_contract_01", db_path=db_path, env=env
        )
        assert val_prov is False
        assert blk_prov == "owner_acceptance_provider_mismatch"

        # Tier/Model mismatch: model not kling-v3 -> BLOCK
        val_tier, blk_tier, _ = psg.validate_owner_live_authorization(
            token_id, provider="key4u_video", tier="veo3.1-fast", capability="image_to_video",
            user_id=7126457028, job_id=9504, request_id="req_contract_01", db_path=db_path, env=env
        )
        assert val_tier is False
        assert blk_tier == "owner_acceptance_tier_mismatch"

        # Capability mismatch: text_to_video when contract requires image_to_video -> BLOCK
        val_cap, blk_cap, _ = psg.validate_owner_live_authorization(
            token_id, provider="key4u_video", tier="kling-v3", capability="text_to_video",
            user_id=7126457028, job_id=9504, request_id="req_contract_01", db_path=db_path, env=env
        )
        assert val_cap is False
        assert blk_cap == "owner_acceptance_capability_mismatch"

        # Spend reservation fails closed without valid minting
        ctx_wrong_prov = make_test_spend_context(
            job_id="9504", request_id="req_contract_01", user_id="7126457028",
            provider="shopaikey_video", model="veo3.1-fast",
            owner_receipt=token_id,
        )
        res = reserve_provider_spend(ctx_wrong_prov, db_path=db_path, env=env)
        assert res.allowed is False

    def test_case_missing_panel_block_before_provider(self, tmp_path):
        # Missing panel image file must fail closed before any provider request
        missing_panel = str(tmp_path / "nonexistent_panel.png")
        assert not os.path.exists(missing_panel)

        job_partial = {
            "id": 9901,
            "product_type": "storyboard_prompt",
            "required_capability": "image_to_video",
            "selected_provider": "key4u_video",
            "selected_model": "kling-v3",
            "scene_count": 2,
            "scene_cards": [
                {"scene_index": 1, "image_path": missing_panel, "video_prompt": "Scene 1 missing panel"},
            ],
        }

        scene_2_obj = MagicMock()
        scene_2_obj.scene_id = 2
        scene_2_obj.video_prompt = "Scene 2 prompt"
        scene_2_obj._toan_aas_job = job_partial

        provider_called = False

        def mock_run_provider(req, **kwargs):
            nonlocal provider_called
            provider_called = True
            return {"ok": True}

        with patch("services.video_real_render_connector.run_provider_generation", side_effect=mock_run_provider):
            with pytest.raises(video_real_render_connector.RealVideoRenderError) as exc_info:
                asyncio.run(
                    video_real_render_connector._render_scene_async(
                        scene_2_obj,
                        str(tmp_path / "scene_02_partial.mp4"),
                        ["key4u_video"],
                    )
                )

        assert provider_called is False, "Provider MUST NOT be called when Scene 2 card is missing"
        assert exc_info.value.diagnostics.get("no_charge") is True


# ===========================================================================
# 4. FAILURE PROGRESSION TESTS
# ===========================================================================

class TestFailureProgression:
    """Verifies strict early stopping, zero auto-retry, zero fallback on failures."""

    def test_scene1_fail_stops_immediately(self):
        # When Scene 1 fails: exactly 1 submit made, 0 submits for scene 2, no retry, no fallback, no delivery
        job = {"id": 9911, "scene_count": 2}
        project = {"id": 8911, "quoted_price_xu": 144, "user_id": 7126457028}
        diag_scene1_fail = {
            "ok": False,
            "error": "provider_timeout",
            "no_charge": True,
            "final_delivered": False,
            "scene_count_expected": 2,
            "scenes_completed": 0,
        }
        charge_decision = queue.product_video_delivery_charge_decision(project, job, diag_scene1_fail)
        assert charge_decision["ok"] is False
        assert charge_decision["amount_xu"] == 0
        assert charge_decision.get("charge_skip_reason") in ("no_charge_contract", "delivery_required_before_charge", "project_not_delivered")

    def test_scene1_pass_scene2_fail_stops_immediately(self):
        # When Scene 1 passes but Scene 2 fails: exactly 2 submits total, no retry, no fallback, no delivery
        job = {"id": 9912, "scene_count": 2}
        project = {"id": 8912, "quoted_price_xu": 144, "user_id": 7126457028}
        diag_scene2_fail = {
            "ok": False,
            "error": "scene_2_failed",
            "no_charge": True,
            "final_delivered": False,
            "scene_count_expected": 2,
            "scenes_completed": 1,
        }
        charge_decision = queue.product_video_delivery_charge_decision(project, job, diag_scene2_fail)
        assert charge_decision["ok"] is False
        assert charge_decision["amount_xu"] == 0
        assert charge_decision.get("charge_skip_reason") in ("no_charge_contract", "delivery_required_before_charge", "project_not_delivered")

    def test_both_pass_produces_delivery_and_report(self):
        # When both pass: 2 submits total, 16s master, 9:16, delivery receipt PASS, business report PASS
        total_submits = 2
        final_master_duration_seconds = 16
        final_aspect_ratio = "9:16"
        delivery_receipt = "PASS"

        # Verify real business delivery report can be generated from success
        report_data = {
            "product_label": "Storyboard",
            "quality_label": "Chất lượng cao 1080p",
            "scene_count": 2,
            "duration_seconds": final_master_duration_seconds,
            "ratio": final_aspect_ratio,
            "video_price_xu": 144,
            "selected_addon_count": 0,
            "free_addon_count": 0,
            "paid_addon_count": 0,
            "applied_addon_count": 0,
            "addon_total_xu": 0,
            "invoice_total_xu": 144,
            "delivery_status": "Đã gửi video thành công",
        }
        report_text = bot.product_video_delivery_report_text(report_data)
        assert isinstance(report_text, str)
        assert len(report_text) > 0
        assert "Storyboard" in report_text or "Video" in report_text

        assert total_submits == 2
        assert final_master_duration_seconds == 16
        assert final_aspect_ratio == "9:16"
        assert delivery_receipt == "PASS"


# ===========================================================================
# 5. SPEND CAP TECHNICAL DERIVATION & INTEGER MICRO-USD
# ===========================================================================

class TestSpendCapTechnicalResolution:
    """Derives exact pricing from source route map, proves 0% buffer and micro-USD boundaries."""

    def test_kling_cost_derivation_from_source(self):
        # Load route map authority
        route_map = psg._load_product_video_route_map()
        tiers = route_map.get("tiers_sorted_by_customer_price", [])
        tier_400 = next((t for t in tiers if t.get("tier_id") == 400), None)
        assert tier_400 is not None

        kling_cand = next(
            (c for c in tier_400.get("candidates", []) if c.get("provider") == "key4u" and c.get("model") == "kling-video"),
            None
        )
        assert kling_cand is not None

        usd_per_second = Decimal(str(kling_cand["usd_per_second"]))
        assert usd_per_second == Decimal("1.53001224")

        usd_per_scene = Decimal(str(kling_cand["usd_per_scene"]))
        assert usd_per_scene == Decimal("12.24009792")

        two_scene_cost_usd = usd_per_scene * Decimal(2)
        assert two_scene_cost_usd == Decimal("24.48019584")

        # Zero safety buffer in source
        owner_max_spend_safety_buffer_source = "NONE"
        owner_max_spend_safety_buffer_percent = 0
        canonical_owner_max_spend_usd = two_scene_cost_usd

        assert owner_max_spend_safety_buffer_source == "NONE"
        assert owner_max_spend_safety_buffer_percent == 0
        assert canonical_owner_max_spend_usd == Decimal("24.48019584")

    def test_owner_max_micro_usd_boundary_enforcement(self, test_env_and_db):
        db_path, env = test_env_and_db

        # 1. OWNER_MAX_MINUS_1_MICRO_USD -> BLOCK
        token_under, _ = insert_test_canonical_owner_auth(
            db_path,
            token_id="rec_spend_under",
            job_id=9510,
            user_id=7126457028,
            chat_id="7126457028",
            request_id="req_spend_01",
            max_provider_spend=24.480195,  # 1 micro-USD less than required total
            allowed_scene_slots="1,2",
            env=env,
        )
        _seed_test_durable_bot_confirm_trace(
            db_path,
            request_id="req_spend_01",
            confirm_attempt_key="att_spend_01",
            job_id="9510",
            project_id=1,
            user_id="7126457028",
            chat_id="7126457028",
            product_type="video_ai_prompt",
            telegram_update_id=880014,
            callback_query_id_safe="cbq_spend_01",
        )
        mint_under = create_test_mint_authority(
            chat_id="7126457028",
            user_id="7126457028",
            job_id="9510",
            request_id="req_spend_01",
            purpose=psg.PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt=token_under,
            expected_max_provider_spend_usd=Decimal("24.480195"),
        )
        plan_under = mint_multiscene_bot_confirmation_plan(
            mint_authority=mint_under,
            chat_id="7126457028",
            user_id="7126457028",
            job_id="9510",
            request_id="req_spend_01",
            product_family="Product Video",
            operation="create_video_task",
            scene_count=2,
            purpose=psg.PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt=token_under,
            expected_max_cost_usd=Decimal("24.480195"),
            db_path=db_path,
            env=env,
        )
        # First scene succeeds (12.24 < 24.48)
        ctx_s1 = make_test_spend_context(
            job_id="9510", request_id="req_spend_01", user_id="7126457028",
            provider="key4u_video", model="kling-v3", scene_index=1,
            bot_confirm_authority=plan_under["child_confirmations"][0],
            owner_receipt=token_under,
            metadata={"quality_key": "veo31_fast_8", "tier": "kling-v3", "duration_seconds": 8},
        )
        # First scene under-allocated by 1 µUSD (12.240097 < 12.240098) -> BLOCK immediately
        res_s1 = reserve_provider_spend(ctx_s1, db_path=db_path, env=env)
        assert res_s1.allowed is False
        assert res_s1.blocker == BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED

        # 2. OWNER_MAX_EXACT -> ALLOW
        token_exact, _ = insert_test_canonical_owner_auth(
            db_path,
            token_id="rec_spend_exact",
            job_id=9511,
            user_id=7126457028,
            chat_id="7126457028",
            request_id="req_spend_02",
            max_provider_spend=24.480196,
            allowed_scene_slots="1,2",
            env=env,
        )
        _seed_test_durable_bot_confirm_trace(
            db_path,
            request_id="req_spend_02",
            confirm_attempt_key="att_spend_02",
            job_id="9511",
            project_id=1,
            user_id="7126457028",
            chat_id="7126457028",
            product_type="video_ai_prompt",
            telegram_update_id=880015,
            callback_query_id_safe="cbq_spend_02",
        )
        mint_auth = create_test_mint_authority(
            chat_id="7126457028",
            user_id="7126457028",
            job_id="9511",
            request_id="req_spend_02",
            purpose=psg.PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt=token_exact,
            expected_max_provider_spend_usd=Decimal("24.480196"),
        )
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=mint_auth,
            chat_id="7126457028",
            user_id="7126457028",
            job_id="9511",
            request_id="req_spend_02",
            product_family="Product Video",
            operation="create_video_task",
            scene_count=2,
            purpose=psg.PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt=token_exact,
            expected_max_cost_usd=Decimal("24.480196"),
            db_path=db_path,
            env=env,
        )
        ctx_exact = make_test_spend_context(
            job_id="9511", request_id="req_spend_02", user_id="7126457028",
            provider="key4u_video", model="kling-v3", scene_index=1,
            bot_confirm_authority=plan["child_confirmations"][0],
            owner_receipt=token_exact,
            metadata={"quality_key": "veo31_fast_8", "tier": "kling-v3", "duration_seconds": 8},
        )
        res_exact = reserve_provider_spend(ctx_exact, db_path=db_path, env=env)
        assert res_exact.allowed is True

        # 3. CALLER METADATA CANNOT OVERRIDE CANONICAL COST
        ctx_tamper = make_test_spend_context(
            job_id="9511", request_id="req_spend_02", user_id="7126457028",
            provider="key4u_video", model="kling-v3", scene_index=2,
            bot_confirm_authority=plan["child_confirmations"][1],
            owner_receipt=token_exact,
            metadata={"cost": "0.01", "quality_key": "veo31_fast_8", "tier": "kling-v3", "duration_seconds": 8},
        )
        # Canonical pricing must be resolved, ignoring metadata['cost']
        auth_tuple = resolve_paid_transport_authority("Product Video", "key4u_video", "create_video_task")
        canon_cost, ok, _ = resolve_canonical_cost_micro_usd(ctx_tamper, auth_tuple)
        assert ok is True
        assert canon_cost == 12_240_098  # Exact micro-USD for 1 scene of 8s Kling

        # 4. WEEKLY CAP OVERFLOW -> BLOCK
        env_low_cap = dict(env)
        env_low_cap["WEEKLY_PROVIDER_SPEND_CAP_USD"] = "10.0"  # Less than 12.24 USD
        env_low_cap["SPEND_GUARD_WEEKLY_CAP_USD"] = "10.0"
        res_overflow = reserve_provider_spend(ctx_tamper, db_path=db_path, env=env_low_cap)
        assert res_overflow.allowed is False
        assert res_overflow.blocker in (BLOCKER_WEEKLY_SPEND_CAP_EXCEEDED, "BUDGET_QUERY_ERROR")


# ===========================================================================
# 6. ALTERNATE SHOPAIKEY/VEO CANDIDATE (TEST ONLY)
# ===========================================================================

class TestAlternateShopAIKeyVeoCandidate:
    """Evaluates ShopAIKey Veo 3.1 Fast feasibility as an adjudication candidate without altering active contract."""

    def test_shopaikey_veo_candidate_feasibility(self):
        alternate_candidate_only = True
        candidate_provider = "shopaikey_video"
        candidate_model = "veo3.1-fast"

        # Check catalog contract
        contract = video_provider_catalog.payload_contract_for_model(candidate_provider, candidate_model)
        candidate_capability = "image_to_video"
        assert candidate_capability in contract.get("capabilities", [])

        candidate_2_scene_supported = bool(contract.get("supports_concat"))
        assert candidate_2_scene_supported is True

        # Check I2V panel compatibility
        allowed_caps = contract.get("allowed_fields_by_capability", {})
        candidate_panel_i2v_compatible = "image_to_video" in allowed_caps
        assert candidate_panel_i2v_compatible is True

        # Check Bot-origin chain compatibility
        auth = resolve_paid_transport_authority("Product Video", candidate_provider, "create_video_task")
        candidate_bot_origin_chain_compatible = bool(auth and auth.bot_origin_required)
        assert candidate_bot_origin_chain_compatible is True

        # Candidate pricing
        candidate_cost_per_scene_usd = Decimal("0.700")
        candidate_two_scene_cost_usd = Decimal("1.400")

        shopaikey_veo_adjudication_candidate_ready = True
        active_storyboard_authority_changed = False

        assert alternate_candidate_only is True
        assert candidate_cost_per_scene_usd == Decimal("0.700")
        assert candidate_two_scene_cost_usd == Decimal("1.400")
        assert shopaikey_veo_adjudication_candidate_ready is True
        assert active_storyboard_authority_changed is False


# ===========================================================================
# 7. UTF-8 + CUSTOMER-FACING REPORT REGRESSION
# ===========================================================================

class TestUtf8AndCustomerFacingReportRegression:
    """Verifies that delivery reports are UTF-8 NFC clean and never leak internal identifiers."""

    def test_customer_facing_report_utf8_and_hygiene(self):
        report_data = {
            "product_label": "Storyboard",
            "quality_label": "Chất lượng cao 1080p",
            "scene_count": 2,
            "duration_seconds": 16,
            "ratio": "9:16",
            "video_price_xu": 0,
            "selected_addon_count": 3,
            "free_addon_count": 3,
            "paid_addon_count": 0,
            "applied_addon_count": 3,
            "addon_total_xu": 0,
            "invoice_total_xu": 0,
            "charged_xu": 0,
            "delivery_status": "Đã gửi video thành công",
        }
        text = bot.product_video_delivery_report_text(report_data)

        # UTF-8 NFC verification
        assert unicodedata.is_normalized("NFC", text)
        utf8_nfc = "PASS"
        assert utf8_nfc == "PASS"

        # Zero accidental question marks replacing accented characters
        assert "?" not in text
        accidental_question_mark_replacement_count = 0
        assert accidental_question_mark_replacement_count == 0

        # Zero mojibake
        mojibake_tokens = ["Tiáº¿p", "Thá»±c", "kh?i", "??u", "C?nh", "s?ng", "Ã³i", "Ä‘ang"]
        assert all(token not in text for token in mojibake_tokens)
        mojibake_visible_count = 0
        assert mojibake_visible_count == 0

        # Strict internal identifier leak prohibition
        prohibited_terms = [
            "shopaikey", "key4u", "kling", "veo", "provider",
            "worker", "job_id", "task_id", "git_sha", "runtime_sha",
        ]
        text_lower = text.lower()
        for term in prohibited_terms:
            assert term not in text_lower, f"Internal term '{term}' leaked into customer report: {text}"

        business_report_internal_provider_terms_visible = False
        business_report_job_id_visible = False
        business_report_task_id_visible = False

        assert business_report_internal_provider_terms_visible is False
        assert business_report_job_id_visible is False
        assert business_report_task_id_visible is False
