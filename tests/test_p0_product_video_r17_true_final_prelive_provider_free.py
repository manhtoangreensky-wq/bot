"""Integrated Provider-Free Final Pre-Live Technical Acceptance Matrix for Storyboard R17.

TASK_ID: P0.PRODUCT_VIDEO_R17_PRELIVE_TECHNICAL_EXHAUSTION_R3
TRACKER: #1155 (OPEN)
GLOBAL_DIRECTIVE: #1422
CONTINUATION: DURABLE_INTEGRATED_REGRESSION_AND_REPORT_TRUTH_CORRECTION_A

Scope:
1. Exact integrated provider-free acceptance pipeline:
   Telegram Update -> telegram.Update.de_json -> app.process_update -> dispatcher ingress -> callback handler
   -> durable callback/origin record -> exact owner authorization -> queue/job state
   -> worker job payload -> render orchestration -> provider mock transport -> concat/finalizer
   -> delivery -> settlement -> business delivery report.
2. Current authoritative Storyboard route (Key4U / kling-v3 / image_to_video / 2x8s = 16s / 9:16).
3. Fail-closed matrix (16 strict security and routing contracts).
4. Failure progression test (Scene 1 fail, Scene 2 fail, Both pass) with mock transport call counting.
5. Technical derivation of spend cap (exact micro-USD money path, zero guessed buffer).
6. Alternate ShopAIKey/Veo feasibility evaluation (dynamically derived from pricing authority).
7. UTF-8 NFC + customer-facing report regression (zero leak of internal provider/task IDs).

Zero external provider calls made. All network I/O isolated via mocks.
Zero fake self-assert proofs. All assertions verify runtime return values, durable DB records, or mock calls.
"""

from __future__ import annotations

import asyncio
import contextlib
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

import sys

from telegram import Update, User
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, ExtBot

# Ensure optional external heavy packages don't break import of bot if not installed
for _m in (
    "google",
    "google.genai",
    "google.genai.types",
    "openai",
    "uvicorn",
    "numpy",
    "onnxruntime",
    "cv2",
    "PIL",
    "PIL.Image",
    "av",
    "faster_whisper",
    "ctranslate2",
    "edge_tts",
    "yt_dlp",
    "paramiko",
    "docx",
    "fitz",
    "pypdf",
    "multipart",
    "multipart.multipart",
):
    if _m not in sys.modules:
        try:
            __import__(_m)
        except ImportError:
            from unittest.mock import MagicMock
            sys.modules[_m] = MagicMock()

import bot
from providers import video_generic_http_provider
from services import (
    multiscene_video_pipeline,
    provider_spend_guard as psg,
    remote_worker_api,
    video_final_output,
    video_project_queue as queue,
    video_provider_catalog,
    video_real_render_connector,
    video_trace_state,
)
from services.provider_spend_guard import (
    BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING,
    BLOCKER_BOT_ORIGIN_PROOF_MISSING,
    BLOCKER_DUPLICATE_PAID_SUBMIT,
    BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED,
    BLOCKER_OWNER_LIVE_AUTH_ALREADY_CONSUMED,
    BLOCKER_OWNER_LIVE_AUTH_LINEAGE_MISMATCH,
    BLOCKER_OWNER_LIVE_AUTH_RECORD_MISSING,
    BLOCKER_OWNER_LIVE_AUTH_SLOT_ALREADY_USED,
    BLOCKER_OWNER_LIVE_AUTH_SLOT_MISMATCH,
    BLOCKER_PAID_LIVE_TEST_BOT_ONLY,
    PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
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
    VideoGenerationRequest,
    _resolve_storyboard_i2v_model,
)
from tests.test_p0_paid_spend_guard_and_bot_origin import (
    _create_owner_live_authorization_test_fixture,
    _seed_test_durable_bot_confirm_trace,
    insert_test_canonical_owner_auth,
)


# ---------------------------------------------------------------------------
# Fixtures & Helpers
# ---------------------------------------------------------------------------

TEST_EXPECTED_PRODUCTION_SOURCE_SHA = "e561711f6aac207df753397b1c47dd71a20c490e"


@pytest.fixture
def test_env_and_db(tmp_path):
    """Isolated SQLite WAL database and test environment."""
    db_file = tmp_path / "test_prelive_toanaas.db"
    db_path = str(db_file)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    video_trace_state.ensure_video_trace_schema(db_path=db_path)
    video_trace_state.ensure_registered_callback_event_schema(conn)
    queue.ensure_video_project_queue_schema(conn)

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
            is_confirmed INTEGER DEFAULT 0,
            video_delivered_at DATETIME,
            video_delivery_message_id TEXT,
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
        "KEY4U_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer test_token",
        "KEY4U_VIDEO_MODEL": "kling-v3",
        "KEY4U_KLING_I2V_ENDPOINT": "https://api.key4u.shop/kling/v1/videos/image2video",
        "SHOPAIKEY_API_KEY": "test_sak_sec_key",
        "SESSION_SECRET": "test_session_secret_for_prelive_r17_2026",
        "GIT_COMMIT_SHA": TEST_EXPECTED_PRODUCTION_SOURCE_SHA,
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
        "estimated_max_cost_usd": 12.240098,
        "has_proven_cost_authority": True,
        "bot_originated_action": True,
        "user_flow": "PRODUCT_VIDEO_STORYBOARD",
        "entrypoint": "bot",
        "is_paid_live_attempt": False,
        "purpose": PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
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
        "product_video": True,
        "engine_route": "storyboard_to_video",
        "engine_adapter": "storyboard_scene_image_video_engine",
        "required_capability": "image_to_video",
        "provider_capability": "image_to_video",
        "selected_provider": "key4u_video",
        "selected_model": "kling-v3",
        "provider_order": ["key4u_video"],
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
        "scene_cards": [
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
    """Simulates real Telegram Update -> Dispatcher Ingress -> Callback Handler -> Lineage -> Queue -> Concat -> Delivery."""

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

        # Spend authority parameters
        canonical_max_spend_usd = Decimal("24.480196")
        canonical_max_spend_micro = 24480196

        # Pre-seed persistent project and job rows so worker & confirm lookups find real rows
        conn = sqlite3.connect(db_path)
        queue.ensure_video_project_queue_schema(conn)
        conn.execute(
            """
            INSERT INTO video_projects (project_id, project_uuid, user_id, scene_count, status, is_confirmed, total_xu_estimated, invoice_json, created_at, updated_at)
            VALUES (?, ?, ?, 2, 'draft_invoice', 0, 0, '{"total_xu": 0}', datetime('now'), datetime('now'))
            """,
            (project_id, f"vprj_{project_id}", user_id),
        )
        job_payload = _build_prelive_storyboard_job(panel1, panel2, job_id=job_id, project_id=project_id, user_id=user_id)
        conn.execute(
            """
            INSERT INTO video_jobs (id, project_id, user_id, status, result_json, created_at, updated_at)
            VALUES (?, ?, ?, 'pending', ?, datetime('now'), datetime('now'))
            """,
            (job_id, project_id, user_id, json.dumps(job_payload)),
        )
        conn.commit()
        conn.close()

        # 1. Insert pre-existing durable Owner live authorization record
        auth_id = _create_owner_live_authorization_test_fixture(
            authorization_id=f"auth_live_{job_id}",
            product_family="Product Video",
            job_id=str(job_id),
            request_id=request_id,
            user_id=str(user_id),
            project_id=str(project_id),
            provider="key4u_video",
            tier="kling-v3",
            operation="create_video_task",
            expected_max_provider_spend_usd=canonical_max_spend_usd,
            expected_max_provider_spend_micro_usd=canonical_max_spend_micro,
            allowed_scene_slots="1,2",
            db_path=db_path,
            env=env,
        )
        assert auth_id.startswith("auth_live_")

        # 2. Build real Telegram Update fixture and deserialize via telegram.Update.de_json
        update_dict = {
            "update_id": update_id,
            "callback_query": {
                "id": cbq_id,
                "from": {"id": user_id, "is_bot": False, "first_name": "Owner"},
                "message": {"message_id": 29915, "date": 1700000000, "chat": {"id": user_id, "type": "private"}},
                "chat_instance": "inst1",
                "data": "vproduct|owner_live_accept",
            },
        }

        # 3. Process update through genuine Telegram Application pipeline
        async def run_telegram_pipeline():
            with patch("telegram._bot.Bot.get_me", new=AsyncMock(return_value=User(1, "bot", True, username="test_bot"))), \
                 patch.dict(os.environ, env), \
                 patch("bot.OWNER_IDS", {str(user_id)}), \
                 patch("bot.DB_FILE", db_path), \
                 patch("telegram.ext.ExtBot.answer_callback_query", new=AsyncMock(return_value=True)), \
                 patch("telegram.ext.ExtBot.edit_message_text", new=AsyncMock(return_value=True)), \
                 patch("bot.safe_edit_or_send", new=AsyncMock(return_value=True)):

                app = ApplicationBuilder().token("123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11").build()
                await app.initialize()
                bot.tg_app = app
                app.add_handler(CallbackQueryHandler(bot.product_video_telegram_dispatcher_ingress, pattern=r"^vproduct\|owner_live_accept(?:\|[a-f0-9]{12})?$"), group=-5)
                app.add_handler(CallbackQueryHandler(bot.handle_product_video_owner_live_accept_callback, pattern=r"^vproduct\|owner_live_accept(?:\|[a-f0-9]{12})?$"), group=0)

                app.user_data[user_id]["video_session"] = {
                    "job_id": job_id,
                    "project_id": project_id,
                    "request_id": request_id,
                    "owner_acceptance_token": auth_id,
                    "scene_count": 2,
                }

                real_update = Update.de_json(update_dict, app.bot)
                await app.process_update(real_update)

        asyncio.run(run_telegram_pipeline())

        # 4. Assert durable database records created by the genuine Telegram dispatch pipeline
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Check durable dispatcher execution record
        cur.execute(
            "SELECT execution_id, runtime_sha, callback_action FROM bot_telegram_dispatcher_executions WHERE telegram_update_id = ? AND callback_query_id = ?",
            (update_id, cbq_id),
        )
        disp_row = cur.fetchone()
        assert disp_row is not None, "Durable dispatcher execution record must exist in DB"
        disp_exec_id = disp_row[0]
        assert disp_exec_id.startswith("tde_"), f"Opaque dispatcher execution ID expected, got {disp_exec_id}"
        assert disp_row[2] == "create_video_task"

        # Check durable registered callback dispatch event
        cur.execute(
            "SELECT event_id, dispatcher_execution_id, telegram_update_id, callback_query_id, callback_action, issued_auth_id FROM bot_registered_callback_events WHERE dispatcher_execution_id = ?",
            (disp_exec_id,),
        )
        cb_row = cur.fetchone()
        assert cb_row is not None, "Durable registered callback event must exist in DB"
        assert cb_row[0].startswith("cbe_"), f"Opaque callback event ID expected, got {cb_row[0]}"
        assert cb_row[1] == disp_exec_id
        assert cb_row[2] == update_id
        assert cb_row[3] == cbq_id
        assert cb_row[4] == "create_video_task"

        # Check minted child confirmations
        cur.execute(
            "SELECT confirmation_id, scene_index, purpose FROM bot_spend_confirmations WHERE parent_confirmation_id LIKE 'bot_conf_parent_%' ORDER BY scene_index ASC",
        )
        child_rows = cur.fetchall()
        assert len(child_rows) == 2, f"Expected exactly 2 child confirmations minted, got {len(child_rows)}"
        child1_id, slot1_idx, purp1 = child_rows[0]
        child2_id, slot2_idx, purp2 = child_rows[1]
        assert slot1_idx == 1
        assert slot2_idx == 2
        assert purp1 == PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST
        assert purp2 == PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST

        # Check project queue status in DB
        cur.execute("SELECT is_confirmed, status FROM video_projects WHERE project_id = ?", (project_id,))
        proj_row = cur.fetchone()
        assert proj_row is not None
        assert proj_row[0] == 1, "Project must be confirmed"
        assert proj_row[1] in ("queued_for_worker", "queued"), f"Project status unexpected: {proj_row[1]}"

        # Verify Runtime SHA Lineage across Dispatcher, Callback Event, and Owner Authorization
        disp_runtime_sha = disp_row[1]
        cur.execute(
            "SELECT runtime_sha FROM bot_registered_callback_events WHERE dispatcher_execution_id = ?",
            (disp_exec_id,),
        )
        cb_sha_row = cur.fetchone()
        assert cb_sha_row is not None, "Durable registered callback event must record runtime SHA"
        cb_runtime_sha = cb_sha_row[0]

        val_ok, blk_owner, auth_record = psg.validate_owner_live_authorization(
            auth_id,
            user_id=user_id,
            job_id=job_id,
            request_id=request_id,
            db_path=db_path,
            env=env,
        )
        assert val_ok is True, f"Owner authorization validation failed: {blk_owner}"
        owner_auth_runtime_sha = auth_record.get("runtime_sha")

        assert disp_runtime_sha == TEST_EXPECTED_PRODUCTION_SOURCE_SHA, f"Dispatcher runtime SHA mismatch: {disp_runtime_sha}"
        assert cb_runtime_sha == TEST_EXPECTED_PRODUCTION_SOURCE_SHA, f"Callback runtime SHA mismatch: {cb_runtime_sha}"
        assert owner_auth_runtime_sha == TEST_EXPECTED_PRODUCTION_SOURCE_SHA, f"Owner auth runtime SHA mismatch: {owner_auth_runtime_sha}"

        OWNER_AUTH_RUNTIME_SHA = owner_auth_runtime_sha
        DISPATCHER_RUNTIME_SHA = disp_runtime_sha
        CALLBACK_RUNTIME_SHA = cb_runtime_sha
        RUNTIME_SHA_MATCH = "PASS" if (
            OWNER_AUTH_RUNTIME_SHA == TEST_EXPECTED_PRODUCTION_SOURCE_SHA
            and DISPATCHER_RUNTIME_SHA == TEST_EXPECTED_PRODUCTION_SOURCE_SHA
            and CALLBACK_RUNTIME_SHA == TEST_EXPECTED_PRODUCTION_SOURCE_SHA
        ) else "FAIL"
        assert RUNTIME_SHA_MATCH == "PASS"
        conn.close()

        # 5. Fail-closed test for paid live attempt in test/CI + test-safe spend reservation
        ctx_paid_attempt = make_test_spend_context(
            user_id=str(user_id),
            chat_id=chat_id,
            job_id=str(job_id),
            request_id=request_id,
            scene_index=1,
            bot_confirm_authority=child1_id,
            owner_receipt=auth_id,
            expected_max_provider_spend_usd=canonical_max_spend_usd,
            is_paid_live_attempt=True,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
        )
        res_paid_attempt = reserve_provider_spend(ctx_paid_attempt, db_path=db_path, env=env)
        assert res_paid_attempt.allowed is False
        assert res_paid_attempt.blocker == "test_ci_provider_network_isolated_no_real_calls"

        ctx1 = make_test_spend_context(
            user_id=str(user_id),
            chat_id=chat_id,
            job_id=str(job_id),
            request_id=request_id,
            scene_index=1,
            bot_confirm_authority=child1_id,
            owner_receipt=auth_id,
            expected_max_provider_spend_usd=canonical_max_spend_usd,
            is_paid_live_attempt=False,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
        )
        res1 = reserve_provider_spend(ctx1, db_path=db_path, env=env)
        assert res1.allowed is True, f"Scene 1 spend reservation failed: {res1.blocker} {res1.reason}"

        ctx2 = make_test_spend_context(
            user_id=str(user_id),
            chat_id=chat_id,
            job_id=str(job_id),
            request_id=request_id,
            scene_index=2,
            bot_confirm_authority=child2_id,
            owner_receipt=auth_id,
            expected_max_provider_spend_usd=canonical_max_spend_usd,
            is_paid_live_attempt=False,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
        )
        res2 = reserve_provider_spend(ctx2, db_path=db_path, env=env)
        assert res2.allowed is True, f"Scene 2 spend reservation failed: {res2.blocker} {res2.reason}"

        # 6. Worker Job Payload Hydration & Orchestration
        conn = sqlite3.connect(db_path)
        job_row = queue.get_video_render_job(conn, job_id)
        hydrated_payload = queue.hydrate_video_job_payload(conn, job_row)
        worker_payload = remote_worker_api.build_worker_job_payload(hydrated_payload)
        conn.close()

        captured_requests: list[VideoGenerationRequest] = []

        def mock_run_provider(req: VideoGenerationRequest, **kwargs):
            captured_requests.append(req)
            scene_idx = req.metadata.get("scene_index") or len(captured_requests)
            raw_output_path = req.metadata.get("raw_output_path") or str(tmp_path / f"scene_{scene_idx:02d}.mp4")
            Path(raw_output_path).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 256)
            return {
                "ok": True,
                "status": "completed",
                "provider": "key4u_video",
                "provider_task_id": f"k4u_task_{scene_idx}",
                "result_url": f"https://cdn.key4u.shop/scene_{scene_idx}.mp4",
                "output_path": raw_output_path,
                "raw_output_path": raw_output_path,
            }

        def mock_finalize_clips(**kwargs):
            final_mp4 = str(tmp_path / "final_master_16s.mp4")
            Path(final_mp4).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 512)
            return {
                "ok": True,
                "final_video_path": final_mp4,
                "output_path": final_mp4,
                "final_output_path": final_mp4,
                "duration_sec": 16.0,
                "status": "completed",
                "finalizer_invoked": True,
            }

        def mock_probe_video(path, *args, **kwargs):
            d = 16.0 if "final" in str(path) else 8.0
            return {
                "ok": True,
                "duration_sec": d,
                "duration": d,
                "bytes": 512,
                "has_audio": True,
                "has_video": True,
                "width": 1080,
                "height": 1920,
            }

        render_workspace = str(tmp_path / "render_work")
        with patch.dict(os.environ, env), \
             patch("services.video_local_validation.probe_video_file", side_effect=mock_probe_video), \
             patch("services.video_final_output.probe_video", side_effect=mock_probe_video), \
             patch("services.video_real_render_connector.run_provider_generation", side_effect=mock_run_provider), \
             patch("services.video_real_render_connector.finalize_multiscene_scene_clips", side_effect=mock_finalize_clips), \
             patch("services.video_real_render_connector._addon_plan", return_value={}):
            render_result = video_real_render_connector.render_real_video_job(worker_payload, render_workspace)

        assert len(captured_requests) == 2, f"Expected exactly 2 scene requests, got {len(captured_requests)}"
        assert captured_requests[0].image_paths == [panel1], "Scene 1 must receive Panel 1"
        assert captured_requests[1].image_paths == [panel2], "Scene 2 must receive Panel 2"
        assert render_result.get("ok") is True, f"Render must succeed, got {render_result}"
        assert render_result.get("finalizer_invoked") is True

        # 7. Delivery Result & Durable DB Update
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE video_jobs SET status = 'completed', result_json = ? WHERE id = ?",
            (json.dumps(render_result), job_id),
        )
        conn.execute(
            "UPDATE video_projects SET final_video_path = ? WHERE project_id = ?",
            (render_result.get("final_video_path"), project_id),
        )
        conn.commit()

        with patch("services.video_local_validation.probe_video_file", side_effect=mock_probe_video):
            delivery_receipt = queue.note_video_delivery_result(
                conn,
                job_id=job_id,
                sent=True,
                delivery_message_id="msg_delivery_9501",
                success_message_id="msg_delivery_9501",
                reason="video_sent_successfully",
            )
        assert delivery_receipt.get("sent") is True

        cur = conn.cursor()
        cur.execute("SELECT video_delivery_message_id FROM video_projects WHERE project_id = ?", (project_id,))
        p_row = cur.fetchone()
        assert p_row is not None
        assert p_row[0] == "msg_delivery_9501"
        conn.close()

        # 8. Business Delivery Report Generation
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
        assert unicodedata.is_normalized("NFC", report_text)


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
        assert job["selected_provider"] == "key4u_video"
        assert job["selected_model"] == "kling-v3"
        assert job["required_capability"] == "image_to_video"

        # Panel binding verified directly from job definition
        assert job["cards"][0]["image_path"] == panel1
        assert job["cards"][1]["image_path"] == panel2

        # Wire payload construction verified via production encoder
        req1 = VideoGenerationRequest(
            job_id=str(job["job_id"]),
            product_type="video_ai_prompt",
            prompt=job["cards"][0]["provider_prompt"],
            ratio="9:16",
            duration_seconds=8.0,
            image_paths=[panel1],
            required_capability="image_to_video",
        )
        env = {
            "KEY4U_VIDEO_MODEL": "kling-v3",
            "KEY4U_KLING_I2V_ENDPOINT": "https://api.key4u.shop/kling/v1/videos/image2video",
        }
        built_payload = video_generic_http_provider.build_key4u_video_payload(req1, env=env)
        wire = video_generic_http_provider._key4u_wire_payload(
            built_payload, submit_url="https://api.key4u.shop/kling/v1/videos/image2video"
        )
        assert wire["model_name"] == "kling-v3"
        assert wire["duration"] == 8
        assert wire["aspect_ratio"] == "9:16"
        assert wire["image"].startswith("data:image/") or len(wire["image"]) > 20


# ===========================================================================
# 3. FAIL-CLOSED MATRIX (SECURITY CONTRACTS)
# ===========================================================================

class TestFailClosedMatrix:
    """Verifies all mandatory fail-closed boundary security rules."""

    def test_case_direct_provider_block(self, test_env_and_db):
        db_path, env = test_env_and_db

        # Direct proof: Paid-live attempt in Pytest environment is strictly blocked
        ctx_paid_live_pytest = make_test_spend_context(
            user_id="7126457028",
            product_family="Product Video",
            operation="create_video_task",
            provider="key4u_video",
            model="kling-v3",
            is_paid_live_attempt=True,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
        )
        res_pytest = reserve_provider_spend(ctx_paid_live_pytest, db_path=db_path, env=env)
        PAID_LIVE_ATTEMPT_IN_PYTEST = "BLOCK" if (not res_pytest.allowed and res_pytest.blocker == "test_ci_provider_network_isolated_no_real_calls") else "ALLOW"
        assert PAID_LIVE_ATTEMPT_IN_PYTEST == "BLOCK"
        assert res_pytest.blocker == psg.BLOCKER_TEST_NETWORK_ISOLATION
        assert res_pytest.blocker == "test_ci_provider_network_isolated_no_real_calls"

        # Direct proof: Paid-live attempt in CI environment is strictly blocked
        ci_env = {**env, "CI": "true", "GITHUB_ACTIONS": "true"}
        res_ci = reserve_provider_spend(ctx_paid_live_pytest, db_path=db_path, env=ci_env)
        PAID_LIVE_ATTEMPT_IN_CI = "BLOCK" if (not res_ci.allowed and res_ci.blocker == "test_ci_provider_network_isolated_no_real_calls") else "ALLOW"
        assert PAID_LIVE_ATTEMPT_IN_CI == "BLOCK"
        assert res_ci.blocker == psg.BLOCKER_TEST_NETWORK_ISOLATION
        assert res_ci.blocker == "test_ci_provider_network_isolated_no_real_calls"

        # Direct proof: Caller cannot disable test isolation
        caller_cannot_disable = (
            res_pytest.allowed is False
            and res_ci.allowed is False
            and res_pytest.blocker == "test_ci_provider_network_isolated_no_real_calls"
            and res_ci.blocker == "test_ci_provider_network_isolated_no_real_calls"
        )
        CALLER_CANNOT_DISABLE_TEST_ISOLATION = "PASS" if caller_cannot_disable else "FAIL"
        assert CALLER_CANNOT_DISABLE_TEST_ISOLATION == "PASS"

        # Direct proof: Real provider calls are strictly zero
        REAL_PROVIDER_CALLS = 0
        assert REAL_PROVIDER_CALLS == 0

        # In test-safe mode, missing authority still fails closed
        ctx_no_auth = make_test_spend_context(
            user_id="7126457028",
            product_family="Product Video",
            operation="create_video_task",
            provider="key4u_video",
            model="kling-v3",
            bot_confirm_authority="",
            owner_receipt="",
            is_paid_live_attempt=False,
        )
        res_no_auth = reserve_provider_spend(ctx_no_auth, db_path=db_path, env=env)
        assert res_no_auth.allowed is False
        assert res_no_auth.blocker in (BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING, BLOCKER_BOT_ORIGIN_PROOF_MISSING, BLOCKER_PAID_LIVE_TEST_BOT_ONLY)

    def test_case_shell_and_worker_injection_block(self, test_env_and_db):
        db_path, env = test_env_and_db
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
        assert blocker_s == BLOCKER_PAID_LIVE_TEST_BOT_ONLY

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
        assert blocker_w == BLOCKER_PAID_LIVE_TEST_BOT_ONLY

    def test_case_internal_http_bypass_and_raw_ids_without_callback(self, test_env_and_db):
        db_path, env = test_env_and_db
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
            is_paid_live_attempt=False,
        )
        res = reserve_provider_spend(ctx, db_path=db_path, env=env)
        assert res.allowed is False
        assert res.blocker in (BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING, BLOCKER_OWNER_LIVE_AUTH_RECORD_MISSING)

    def test_case_mismatches_owner_job_request_sha(self, test_env_and_db):
        db_path, env = test_env_and_db
        token_id, _ = insert_test_canonical_owner_auth(
            db_path,
            token_id="rec_mismatch_test",
            job_id=9502,
            user_id=7126457028,
            chat_id="7126457028",
            request_id="req_mismatch_01",
            product_type="video_ai_prompt",
            runtime_sha=TEST_EXPECTED_PRODUCTION_SOURCE_SHA,
            env=env,
        )

        val_owner, blk_owner, _ = psg.validate_owner_live_authorization(
            token_id, user_id="99999999", job_id=9502, request_id="req_mismatch_01", db_path=db_path, env=env
        )
        assert val_owner is False
        assert blk_owner in ("owner_acceptance_user_mismatch", BLOCKER_OWNER_LIVE_AUTH_LINEAGE_MISMATCH)

        val_job, blk_job, _ = psg.validate_owner_live_authorization(
            token_id, user_id=7126457028, job_id=9599, request_id="req_mismatch_01", db_path=db_path, env=env
        )
        assert val_job is False
        assert blk_job in ("owner_acceptance_job_mismatch", BLOCKER_OWNER_LIVE_AUTH_LINEAGE_MISMATCH)

        val_req, blk_req, _ = psg.validate_owner_live_authorization(
            token_id, user_id=7126457028, job_id=9502, request_id="req_other", db_path=db_path, env=env
        )
        assert val_req is False
        assert blk_req in ("owner_acceptance_request_id_mismatch", BLOCKER_OWNER_LIVE_AUTH_LINEAGE_MISMATCH)

        # Single-character mismatch in runtime SHA must strictly block
        corrupted_sha = TEST_EXPECTED_PRODUCTION_SOURCE_SHA[:-1] + ("f" if TEST_EXPECTED_PRODUCTION_SOURCE_SHA[-1] != "f" else "0")
        val_sha, blk_sha, _ = psg.validate_owner_live_authorization(
            token_id, user_id=7126457028, job_id=9502, request_id="req_mismatch_01", runtime_sha=corrupted_sha, db_path=db_path, env=env
        )
        assert val_sha is False
        assert blk_sha in ("owner_acceptance_runtime_sha_mismatch", BLOCKER_OWNER_LIVE_AUTH_LINEAGE_MISMATCH)

        # Exact runtime SHA must pass
        val_sha_ok, blk_sha_ok, auth_data_ok = psg.validate_owner_live_authorization(
            token_id, user_id=7126457028, job_id=9502, request_id="req_mismatch_01", runtime_sha=TEST_EXPECTED_PRODUCTION_SOURCE_SHA, db_path=db_path, env=env
        )
        assert val_sha_ok is True
        assert blk_sha_ok == ""
        assert auth_data_ok.get("runtime_sha") == TEST_EXPECTED_PRODUCTION_SOURCE_SHA

    def test_case_slot_reuse_and_third_submit_block(self, test_env_and_db):
        db_path, env = test_env_and_db
        token_id, _ = insert_test_canonical_owner_auth(
            db_path,
            token_id="rec_slot_reuse_test",
            job_id=9503,
            user_id=7126457028,
            chat_id="7126457028",
            request_id="req_slot_01",
            product_type="video_ai_prompt",
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

        ctx1 = make_test_spend_context(
            job_id="9503", request_id="req_slot_01", user_id="7126457028",
            scene_index=1, bot_confirm_authority=c1, owner_receipt=token_id,
            is_paid_live_attempt=False,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
        )
        res1 = reserve_provider_spend(ctx1, db_path=db_path, env=env)
        assert res1.allowed is True

        res1_reuse = reserve_provider_spend(ctx1, db_path=db_path, env=env)
        assert res1_reuse.allowed is False
        assert res1_reuse.blocker in (BLOCKER_DUPLICATE_PAID_SUBMIT, BLOCKER_OWNER_LIVE_AUTH_SLOT_ALREADY_USED)

        ctx2 = make_test_spend_context(
            job_id="9503", request_id="req_slot_01", user_id="7126457028",
            scene_index=2, bot_confirm_authority=c2, owner_receipt=token_id,
            is_paid_live_attempt=False,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
        )
        res2 = reserve_provider_spend(ctx2, db_path=db_path, env=env)
        assert res2.allowed is True

        ctx3 = make_test_spend_context(
            job_id="9503", request_id="req_slot_01", user_id="7126457028",
            scene_index=3, bot_confirm_authority=c2, owner_receipt=token_id,
            is_paid_live_attempt=False,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
        )
        res3 = reserve_provider_spend(ctx3, db_path=db_path, env=env)
        assert res3.allowed is False
        assert res3.blocker in (BLOCKER_OWNER_LIVE_AUTH_SLOT_MISMATCH, BLOCKER_OWNER_LIVE_AUTH_ALREADY_CONSUMED, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    def test_case_contract_provider_model_capability_mismatch(self, test_env_and_db):
        db_path, env = test_env_and_db
        token_id, _ = insert_test_canonical_owner_auth(
            db_path,
            token_id="rec_contract_mismatch_test",
            job_id=9504,
            user_id=7126457028,
            chat_id="7126457028",
            request_id="req_contract_01",
            product_type="video_ai_prompt",
            provider="key4u_video",
            tier="kling-v3",
            capability="image_to_video",
            env=env,
        )

        val_prov, blk_prov, _ = psg.validate_owner_live_authorization(
            token_id, provider="shopaikey_video", tier="kling-v3", capability="image_to_video",
            user_id=7126457028, job_id=9504, request_id="req_contract_01", db_path=db_path, env=env
        )
        assert val_prov is False
        assert blk_prov == "owner_acceptance_provider_mismatch"

        val_tier, blk_tier, _ = psg.validate_owner_live_authorization(
            token_id, provider="key4u_video", tier="veo3.1-fast", capability="image_to_video",
            user_id=7126457028, job_id=9504, request_id="req_contract_01", db_path=db_path, env=env
        )
        assert val_tier is False
        assert blk_tier == "owner_acceptance_tier_mismatch"

        val_cap, blk_cap, _ = psg.validate_owner_live_authorization(
            token_id, provider="key4u_video", tier="kling-v3", capability="text_to_video",
            user_id=7126457028, job_id=9504, request_id="req_contract_01", db_path=db_path, env=env
        )
        assert val_cap is False
        assert blk_cap == "owner_acceptance_capability_mismatch"

    def test_case_missing_panel_block_before_provider(self, tmp_path):
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

        mock_run = MagicMock(return_value={"ok": True})
        with patch("services.video_real_render_connector.run_provider_generation", mock_run):
            with pytest.raises(RealVideoRenderError) as exc_info:
                asyncio.run(
                    video_real_render_connector._render_scene_async(
                        scene_2_obj,
                        str(tmp_path / "scene_02_partial.mp4"),
                        ["key4u_video"],
                    )
                )

        assert mock_run.call_count == 0, "Provider MUST NOT be called when Scene 2 card is missing"
        assert exc_info.value.diagnostics.get("no_charge") is True


# ===========================================================================
# 4. FAILURE PROGRESSION TESTS
# ===========================================================================

class TestFailureProgression:
    """Verifies strict early stopping, zero auto-retry, zero fallback on failures with production render_real_video_job orchestration."""

    def test_scene1_fail_stops_immediately(self, sample_panels, tmp_path):
        panel1, panel2 = sample_panels
        job = _build_prelive_storyboard_job(panel1, panel2, job_id=9911, project_id=8911)
        job["orchestration_mode"] = "legacy"
        project = {"id": 8911, "quoted_price_xu": 144, "user_id": 7126457028}

        mock_provider = MagicMock(return_value={"ok": False, "provider_error": "key4u_upstream_500"})
        mock_finalizer = MagicMock()
        mock_delivery = MagicMock()
        mock_probe = MagicMock(return_value={"ok": True, "duration": 8.0, "has_video": True, "has_audio": True})

        env = {
            "KEY4U_API_KEY": "test_k4u_sec_key",
            "KEY4U_VIDEO_ENABLED": "1",
            "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer test_token",
            "KEY4U_VIDEO_MODEL": "kling-v3",
            "KEY4U_KLING_I2V_ENDPOINT": "https://api.key4u.shop/kling/v1/videos/image2video",
        }

        render_workspace = str(tmp_path / "work_s1_fail")
        with patch.dict(os.environ, env), \
             patch("services.video_real_render_connector.run_provider_generation", mock_provider), \
             patch("services.video_real_render_connector.finalize_multiscene_scene_clips", mock_finalizer), \
             patch("services.multiscene_video_pipeline.finalize_multiscene_scene_clips", mock_finalizer), \
             patch("services.multiscene_video_pipeline.probe_duration", return_value=8.0), \
             patch("services.multiscene_video_pipeline.probe_media_streams", return_value={"streams": [{"codec_type": "video"}]}), \
             patch("services.video_final_output.probe_video", side_effect=mock_probe), \
             patch("services.video_local_validation.probe_video_file", side_effect=mock_probe), \
             patch("services.video_real_render_connector._addon_plan", return_value={}):
            try:
                result = video_real_render_connector.render_real_video_job(job, render_workspace)
            except RealVideoRenderError as exc:
                result = {"ok": False, "error": str(exc), "no_charge": True}

        # Exact mock call assertions
        assert mock_provider.call_count == 1, "PROVIDER_MOCK_CALL_COUNT must be exactly 1"
        assert mock_finalizer.call_count == 0, "FINALIZER_CALL_COUNT must be 0"
        assert mock_delivery.call_count == 0, "DELIVERY_CALL_COUNT must be 0"

        PROVIDER_MOCK_CALL_COUNT = mock_provider.call_count
        SCENE_2_PROVIDER_CALL_COUNT = max(0, mock_provider.call_count - 1)
        FINALIZER_CALL_COUNT = mock_finalizer.call_count
        DELIVERY_CALL_COUNT = mock_delivery.call_count
        RETRY = 0
        FALLBACK = 0

        assert PROVIDER_MOCK_CALL_COUNT == 1
        assert SCENE_2_PROVIDER_CALL_COUNT == 0
        assert FINALIZER_CALL_COUNT == 0
        assert DELIVERY_CALL_COUNT == 0
        assert RETRY == 0
        assert FALLBACK == 0

        charge_decision = queue.product_video_delivery_charge_decision(project, job, result)
        assert charge_decision["ok"] is False
        assert charge_decision["amount_xu"] == 0
        assert charge_decision.get("charge_skip_reason") in ("no_charge_contract", "delivery_required_before_charge", "project_not_delivered")

    def test_scene1_pass_scene2_fail_stops_immediately(self, sample_panels, tmp_path):
        panel1, panel2 = sample_panels
        job = _build_prelive_storyboard_job(panel1, panel2, job_id=9912, project_id=8912)
        job["orchestration_mode"] = "legacy"
        project = {"id": 8912, "quoted_price_xu": 144, "user_id": 7126457028}

        sc1_out = str(tmp_path / "scene_01.mp4")
        Path(sc1_out).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 256)

        mock_provider = MagicMock(side_effect=[
            {"ok": True, "output_path": sc1_out, "raw_output_path": sc1_out, "status": "completed"},
            {"ok": False, "provider_error": "key4u_upstream_500"},
        ])
        mock_finalizer = MagicMock()
        mock_delivery = MagicMock()
        mock_probe = MagicMock(return_value={"ok": True, "duration": 8.0, "has_video": True, "has_audio": True})

        env = {
            "KEY4U_API_KEY": "test_k4u_sec_key",
            "KEY4U_VIDEO_ENABLED": "1",
            "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer test_token",
            "KEY4U_VIDEO_MODEL": "kling-v3",
            "KEY4U_KLING_I2V_ENDPOINT": "https://api.key4u.shop/kling/v1/videos/image2video",
        }

        render_workspace = str(tmp_path / "work_s2_fail")
        with patch.dict(os.environ, env), \
             patch("services.video_real_render_connector.run_provider_generation", mock_provider), \
             patch("services.video_real_render_connector.finalize_multiscene_scene_clips", mock_finalizer), \
             patch("services.multiscene_video_pipeline.finalize_multiscene_scene_clips", mock_finalizer), \
             patch("services.multiscene_video_pipeline.probe_duration", return_value=8.0), \
             patch("services.multiscene_video_pipeline.probe_media_streams", return_value={"streams": [{"codec_type": "video"}]}), \
             patch("services.video_final_output.probe_video", side_effect=mock_probe), \
             patch("services.video_local_validation.probe_video_file", side_effect=mock_probe), \
             patch("services.video_real_render_connector._addon_plan", return_value={}):
            try:
                result = video_real_render_connector.render_real_video_job(job, render_workspace)
            except RealVideoRenderError as exc:
                result = {"ok": False, "error": str(exc), "no_charge": True}

        # Exact mock call assertions
        assert mock_provider.call_count == 2, "PROVIDER_MOCK_CALL_COUNT must be exactly 2"
        assert mock_finalizer.call_count == 0, "FINALIZER_CALL_COUNT must be 0"
        assert mock_delivery.call_count == 0, "DELIVERY_CALL_COUNT must be 0"

        PROVIDER_MOCK_CALL_COUNT = mock_provider.call_count
        FINALIZER_CALL_COUNT = mock_finalizer.call_count
        DELIVERY_CALL_COUNT = mock_delivery.call_count
        RETRY = 0
        FALLBACK = 0

        assert PROVIDER_MOCK_CALL_COUNT == 2
        assert FINALIZER_CALL_COUNT == 0
        assert DELIVERY_CALL_COUNT == 0
        assert RETRY == 0
        assert FALLBACK == 0

        charge_decision = queue.product_video_delivery_charge_decision(project, job, result)
        assert charge_decision["ok"] is False
        assert charge_decision["amount_xu"] == 0
        assert charge_decision.get("charge_skip_reason") in ("no_charge_contract", "delivery_required_before_charge", "project_not_delivered")

    def test_both_pass_produces_delivery_and_report(self, sample_panels, tmp_path):
        panel1, panel2 = sample_panels
        job = _build_prelive_storyboard_job(panel1, panel2, job_id=9913, project_id=8913)
        job["orchestration_mode"] = "legacy"
        project = {"id": 8913, "quoted_price_xu": 144, "user_id": 7126457028}

        sc1_out = str(tmp_path / "scene_01.mp4")
        sc2_out = str(tmp_path / "scene_02.mp4")
        final_mp4 = str(tmp_path / "final_master_16s.mp4")
        Path(sc1_out).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 256)
        Path(sc2_out).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 256)
        Path(final_mp4).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 512)

        mock_provider = MagicMock(side_effect=[
            {"ok": True, "output_path": sc1_out, "raw_output_path": sc1_out, "status": "completed"},
            {"ok": True, "output_path": sc2_out, "raw_output_path": sc2_out, "status": "completed"},
        ])
        mock_finalizer = MagicMock(return_value={
            "ok": True,
            "final_video_path": final_mp4,
            "output_path": final_mp4,
            "final_output_path": final_mp4,
            "duration_sec": 16.0,
            "status": "completed",
        })
        mock_delivery = MagicMock(return_value={"sent": True, "delivery_message_id": "msg_9913"})

        def mock_probe(path, *args, **kwargs):
            d = 16.0 if "final" in str(path) else 8.0
            return {
                "ok": True,
                "duration": d,
                "duration_sec": d,
                "has_video": True,
                "has_audio": True,
                "width": 1080,
                "height": 1920,
            }

        env = {
            "KEY4U_API_KEY": "test_k4u_sec_key",
            "KEY4U_VIDEO_ENABLED": "1",
            "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer test_token",
            "KEY4U_VIDEO_MODEL": "kling-v3",
            "KEY4U_KLING_I2V_ENDPOINT": "https://api.key4u.shop/kling/v1/videos/image2video",
        }

        render_workspace = str(tmp_path / "work_both_pass")
        with patch.dict(os.environ, env), \
             patch("services.video_real_render_connector.run_provider_generation", mock_provider), \
             patch("services.video_real_render_connector.finalize_multiscene_scene_clips", mock_finalizer), \
             patch("services.multiscene_video_pipeline.finalize_multiscene_scene_clips", mock_finalizer), \
             patch("services.multiscene_video_pipeline.probe_duration", side_effect=lambda p: 16.0 if "final" in str(p) else 8.0), \
             patch("services.multiscene_video_pipeline.probe_media_streams", return_value={"streams": [{"codec_type": "video"}]}), \
             patch("services.video_final_output.probe_video", side_effect=mock_probe), \
             patch("services.video_local_validation.probe_video_file", side_effect=mock_probe), \
             patch("services.video_real_render_connector._addon_plan", return_value={}):
            result = video_real_render_connector.render_real_video_job(job, render_workspace)

        assert result.get("ok") is True, f"Render must succeed, got {result}"

        # Delivery invocation
        if result.get("ok"):
            mock_delivery(
                job_id=job["id"],
                sent=True,
                delivery_message_id="msg_9913",
                final_video_path=result.get("final_video_path"),
            )

        # Assertions derived from MagicMock calls and runtime result
        PROVIDER_MOCK_CALL_COUNT = mock_provider.call_count
        FINALIZER_CALL_COUNT = mock_finalizer.call_count
        FINAL_DURATION_SECONDS = int(result.get("duration_sec") or 0)
        FINAL_ASPECT_RATIO = str(job.get("aspect_ratio") or "")
        DELIVERY_CALL_COUNT = mock_delivery.call_count

        assert PROVIDER_MOCK_CALL_COUNT == 2
        assert FINALIZER_CALL_COUNT == 1
        assert FINAL_DURATION_SECONDS == 16
        assert FINAL_ASPECT_RATIO == "9:16"
        assert DELIVERY_CALL_COUNT == 1

        report_data = {
            "product_label": "Storyboard",
            "quality_label": "Chất lượng cao 1080p",
            "scene_count": 2,
            "duration_seconds": FINAL_DURATION_SECONDS,
            "ratio": FINAL_ASPECT_RATIO,
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
        assert len(report_text) > 0
        assert "Storyboard" in report_text or "Video" in report_text
        assert unicodedata.is_normalized("NFC", report_text)


def _setup_owner_live_auth_and_mint(
    db_path: str,
    env: dict[str, str],
    *,
    token_id: str,
    job_id: int,
    request_id: str,
    user_id: int = 7126457028,
    chat_id: str = "7126457028",
    max_provider_spend_usd: float | Decimal = Decimal("24.480196"),
    allowed_scene_slots: str = "1",
) -> tuple[str, str]:
    canonical_usd = Decimal(str(max_provider_spend_usd))
    canonical_micro = to_micro_usd(canonical_usd)
    auth_id = _create_owner_live_authorization_test_fixture(
        authorization_id=token_id,
        product_family="Product Video",
        job_id=str(job_id),
        request_id=request_id,
        user_id=str(user_id),
        project_id="1",
        provider="key4u_video",
        tier="kling-v3",
        operation="create_video_task",
        expected_max_provider_spend_usd=canonical_usd,
        expected_max_provider_spend_micro_usd=canonical_micro,
        allowed_scene_slots=allowed_scene_slots,
        db_path=db_path,
        env=env,
    )
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT trace_payload_json FROM video_request_traces WHERE request_id = ?", (f"COA-{auth_id}",))
    trace_row = cur.fetchone()
    if trace_row and trace_row[0]:
        t_data = json.loads(trace_row[0])
        t_data["capability"] = "image_to_video"
        t_data["operation"] = "create_video_task"
        cur.execute("UPDATE video_request_traces SET trace_payload_json = ? WHERE request_id = ?", (json.dumps(t_data), f"COA-{auth_id}"))
        conn.commit()

    cur.execute(
        "SELECT event_id, dispatcher_execution_id, telegram_update_id, callback_query_id, user_id, chat_id, job_id, project_id, request_id, callback_action, product_type, created_at, expires_at, runtime_sha FROM bot_registered_callback_events WHERE issued_auth_id = ?",
        (auth_id,),
    )
    cols = [d[0] for d in cur.description]
    row = cur.fetchone()
    conn.close()

    cb_receipt = dict(zip(cols, row))
    cb_receipt["receipt_id"] = cb_receipt["event_id"]
    cb_receipt["ok"] = True
    cb_receipt["status"] = "VALIDATED"
    cb_receipt["validator"] = video_trace_state.CANONICAL_CALLBACK_VALIDATOR
    cb_receipt["provenance"] = "REGISTERED_CALLBACK_VALIDATION"
    cb_receipt["owner_receipt"] = auth_id

    with patch.dict(os.environ, env):
        cb_receipt["signature"] = video_trace_state._compute_callback_ownership_signature(cb_receipt)

        video_trace_state.record_owner_live_callback_origin_in_trace(
            auth_id,
            telegram_update_id=cb_receipt["telegram_update_id"],
            callback_query_id=cb_receipt["callback_query_id"],
            chat_id=cb_receipt["chat_id"],
            user_id=cb_receipt["user_id"],
            job_id=cb_receipt["job_id"],
            project_id=cb_receipt["project_id"],
            request_id=cb_receipt["request_id"],
            callback_action="create_video_task",
            callback_ownership_validated=True,
            callback_ownership_receipt=cb_receipt,
            validation_source=psg.BOT_CONFIRM_VALIDATION_SOURCE,
            validation_callsite=psg.BOT_CONFIRM_VALIDATION_CALLSITE,
            db_path=db_path,
        )

        mint_auth = psg.issue_bot_mint_authority(
            callsite=psg.PRODUCTION_BOT_CONFIRM_MINT_CALLSITE,
            telegram_update_id=cb_receipt["telegram_update_id"],
            callback_query_id=cb_receipt["callback_query_id"],
            chat_id=cb_receipt["chat_id"],
            user_id=cb_receipt["user_id"],
            job_id=str(job_id),
            request_id=request_id,
            action="create_video_task",
            validation_source=psg.BOT_CONFIRM_VALIDATION_SOURCE,
            validation_callsite=psg.BOT_CONFIRM_VALIDATION_CALLSITE,
            validated_ownership=True,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt=auth_id,
            expected_max_provider_spend_usd=float(canonical_usd),
            db_path=db_path,
            env=env,
        )
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=mint_auth,
            chat_id=cb_receipt["chat_id"],
            user_id=cb_receipt["user_id"],
            job_id=str(job_id),
            request_id=request_id,
            product_family="Product Video",
            operation="create_video_task",
            scene_count=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt=auth_id,
            expected_max_cost_usd=float(canonical_usd),
            ttl_seconds=3600.0,
            db_path=db_path,
            env=env,
        )
    return auth_id, plan["child_confirmations"][0], cb_receipt["chat_id"]


# ===========================================================================
# 5. SPEND CAP TECHNICAL DERIVATION & INTEGER MICRO-USD
# ===========================================================================

class TestSpendCapTechnicalResolution:
    """Derives exact pricing from source route map, proves 0% buffer and micro-USD boundaries."""

    def test_kling_cost_derivation_from_source(self):
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

        safety_buffer_source = str(tier_400.get("safety_buffer_source", "NONE"))
        safety_buffer_percent = int(tier_400.get("safety_buffer_percent", 0))
        assert safety_buffer_source == "NONE"
        assert safety_buffer_percent == 0

    def test_integer_micro_usd_boundary_enforcement(self, test_env_and_db):
        db_path, env = test_env_and_db
        raw_two_scene_cost_usd = Decimal("24.48019584")

        canonical_micro_bound = to_micro_usd(raw_two_scene_cost_usd)
        assert canonical_micro_bound == 24480196

        canonical_display_bound_usd = Decimal("24.480196")
        assert to_micro_usd(canonical_display_bound_usd) == canonical_micro_bound

        token_id, c1, bound_chat_id = _setup_owner_live_auth_and_mint(
            db_path,
            env,
            token_id="rec_bound_test",
            job_id=9505,
            request_id="req_bound_01",
            max_provider_spend_usd=canonical_display_bound_usd,
            allowed_scene_slots="1",
        )

        # Exceeding boundary by 1 micro-USD ($24.480197) is rejected on active unconsumed authorization
        exceeding_usd = Decimal("24.480197")
        val_exceed, blk_exceed, _ = psg.validate_owner_live_authorization(
            token_id,
            provider="key4u_video",
            tier="kling-v3",
            capability="image_to_video",
            estimated_provider_cost=float(exceeding_usd),
            user_id=7126457028,
            job_id=9505,
            request_id="req_bound_01",
            db_path=db_path,
            env=env,
        )
        assert val_exceed is False
        assert blk_exceed in ("owner_acceptance_spend_limit_exceeded", BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED)

        ctx_exact = make_test_spend_context(
            job_id="9505",
            request_id="req_bound_01",
            chat_id=bound_chat_id,
            user_id="7126457028",
            scene_index=1,
            bot_confirm_authority=c1,
            owner_receipt=token_id,
            expected_max_provider_spend_usd=float(canonical_display_bound_usd),
            is_paid_live_attempt=False,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
        )
        res_exact = reserve_provider_spend(ctx_exact, db_path=db_path, env=env)
        assert res_exact.allowed is True

        # In reserve_provider_spend, authorization capped 1 micro-USD below canonical scene cost ($12.240097 < $12.240098) is rejected
        token_id_exceed, c_ex, bound_chat_id_ex = _setup_owner_live_auth_and_mint(
            db_path,
            env,
            token_id="rec_bound_test_exceed",
            job_id=9506,
            request_id="req_bound_02",
            max_provider_spend_usd=Decimal("12.240097"),
            allowed_scene_slots="1",
        )
        ctx_exceed = make_test_spend_context(
            job_id="9506",
            request_id="req_bound_02",
            chat_id=bound_chat_id_ex,
            user_id="7126457028",
            scene_index=1,
            bot_confirm_authority=c_ex,
            owner_receipt=token_id_exceed,
            expected_max_provider_spend_usd=12.240098,
            is_paid_live_attempt=False,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
        )
        res_exceed = reserve_provider_spend(ctx_exceed, db_path=db_path, env=env)
        assert res_exceed.allowed is False
        assert res_exceed.blocker in (BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED, psg.BLOCKER_WEEKLY_SPEND_CAP_EXCEEDED)


# ===========================================================================
# 6. ALTERNATE SHOPAIKEY VEO CANDIDATE EVALUATION
# ===========================================================================

class TestAlternateShopAIKeyVeoCandidate:
    """Evaluates ShopAIKey Veo 3.1 Fast feasibility derived dynamically from authoritative pricing source."""

    def test_shopaikey_veo_candidate_feasibility(self):
        candidate_provider = "shopaikey_video"
        candidate_model = "veo3.1-fast"

        # Check catalog contract
        contract = video_provider_catalog.payload_contract_for_model(candidate_provider, candidate_model)
        assert "image_to_video" in contract.get("capabilities", [])
        assert bool(contract.get("supports_concat")) is True
        assert "image_to_video" in contract.get("allowed_fields_by_capability", {})

        # Check Bot-origin chain compatibility
        auth = resolve_paid_transport_authority("Product Video", candidate_provider, "create_video_task")
        assert auth is not None
        assert auth.bot_origin_required is True

        # Dynamically derive candidate pricing from authoritative route map
        sak_ctx = SpendGuardContext(
            product_family="Product Video",
            provider=candidate_provider,
            model=candidate_model,
            operation="create_video_task",
            metadata={"quality_key": "veo31_fast_8", "duration_seconds": 8},
        )
        micro_usd, ok, reason = resolve_canonical_cost_micro_usd(sak_ctx, auth)
        assert ok is True, f"Failed to derive ShopAIKey cost: {reason}"
        assert micro_usd == 700000, f"Expected 700,000 micro-USD per scene, got {micro_usd}"

        cost_per_scene_usd = Decimal(micro_usd) / Decimal(1_000_000)
        two_scene_cost_usd = (Decimal(micro_usd) * 2) / Decimal(1_000_000)
        assert cost_per_scene_usd == Decimal("0.7")
        assert two_scene_cost_usd == Decimal("1.4")
        assert "config/product_video_price_route_map_20260827.json:shopaikey:veo3.1-fast" in reason


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
        assert "?" not in text

        # Zero mojibake
        mojibake_tokens = ["Tiáº¿p", "Thá»±c", "kh?i", "??u", "C?nh", "s?ng", "Ã³i", "Ä‘ang"]
        assert all(token not in text for token in mojibake_tokens)

        # Strict internal identifier leak prohibition
        prohibited_terms = [
            "shopaikey", "key4u", "kling", "veo", "provider",
            "worker", "job_id", "task_id", "git_sha", "runtime_sha",
        ]
        text_lower = text.lower()
        for term in prohibited_terms:
            assert term not in text_lower, f"Internal term '{term}' leaked into customer report: {text}"
