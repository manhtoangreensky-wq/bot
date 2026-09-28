# -*- coding: utf-8 -*-
"""P0 test suite for Storyboard queue-confirm multi-provider closure (R13.4).

Verifies that Storyboard Tier 400 queue-confirm and kickoff payload construction
preserves provider/model authority for ShopAIKey (veo3.1-fast / google_veo / image_to_video)
while maintaining 100% backward compatibility for Key4U (kling-v3 / kling-3.0-turbo).
Also validates that invalid/mismatched combinations fail closed with zero charge,
no hidden fallback, and dynamic diagnostics.
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

import bot
from services import remote_worker_api
from services import video_project_queue as queue
from services.video_real_render_connector import (
    STORYBOARD_DEFAULT_I2V_MODEL_BY_PROVIDER,
    STORYBOARD_I2V_MODEL_NOT_PROVEN_BLOCKER,
    STORYBOARD_PROVEN_I2V_MODELS_BY_PROVIDER,
    RealVideoRenderError,
    _resolve_storyboard_i2v_model,
)


@pytest.fixture
def sample_panels(tmp_path):
    p1 = tmp_path / "panel_01.png"
    p2 = tmp_path / "panel_02.png"
    p1.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4")
    p2.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4")
    return str(p1), str(p2)


def _make_session(
    sample_panels,
    *,
    selected_provider="shopaikey_video",
    selected_model="veo3.1-fast",
    user_id=8840,
):
    panel1, panel2 = sample_panels
    draft = {
        "product_id": "storyboard_prompt",
        "b14_scene_count": 2,
        "b14_scene_seconds": 8,
        "b14_aspect_ratio": "9:16",
        "b14_quality_xu": 668,
        "b14_profile_id": "storytelling",
        "scene_cards": [
            {"scene_index": 1, "image_path": panel1, "prompt": "Scene 1: Introduction"},
            {"scene_index": 2, "image_path": panel2, "prompt": "Scene 2: Climax"},
        ],
        "storyboard_panels": [
            {"scene_index": 1, "local_path": panel1},
            {"scene_index": 2, "local_path": panel2},
        ],
    }
    if selected_provider is not None:
        draft["selected_provider"] = selected_provider
        draft["provider_order"] = selected_provider
        draft["provider_chain"] = [selected_provider]
    if selected_model is not None:
        draft["selected_model"] = selected_model

    session = {
        "user_id": user_id,
        "product": "storyboard_prompt",
        "aspect_ratio": "9:16",
        "draft": draft,
    }
    bot.save_video_session(user_id, session)
    return session


def _setup_db(tmp_path):
    db_file = tmp_path / "test_queue_confirm_r13_4.sqlite"
    conn = sqlite3.connect(str(db_file))
    queue.ensure_video_project_queue_schema(conn)
    return conn, str(db_file)


# ==============================================================================
# 1. ShopAIKey + Veo Queue-Confirm Acceptance
# ==============================================================================


def test_storyboard_queue_confirm_shopaikey_veo31_fast(sample_panels, tmp_path, monkeypatch):
    """ShopAIKey + veo3.1-fast preserves authority end-to-end through queue confirm."""
    conn, db_path = _setup_db(tmp_path)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("SHOPAIKEY_VIDEO_API_KEY", "test_key_veo")
    monkeypatch.setenv("SHOPAIKEY_VIDEO_BASE_URL", "https://api.shopaikey.com/v1")

    user_id = 8841
    session = _make_session(sample_panels, selected_provider="shopaikey_video", selected_model="veo3.1-fast", user_id=user_id)

    # Prepare project
    project = bot.video_b14_prepare_project_for_invoice(user_id=user_id, session=session)
    project_id = int(project["project_id"])

    # Confirm invoice
    confirm_res = queue.confirm_video_project_invoice(conn, project_id=project_id, user_id=user_id, billing_exempt=True)
    assert confirm_res["ok"] is True
    job_id = int(confirm_res["job"]["id"])

    # Verify persisted job fields in database
    job_row = queue.get_video_render_job(conn, job_id)
    assert job_row is not None
    result_json = json.loads(str(job_row.get("result_json") or "{}"))

    assert result_json.get("selected_provider") == "shopaikey_video"
    assert result_json.get("selected_model") == "veo3.1-fast"
    assert result_json.get("pinned_wire_model") == "veo3.1-fast"
    assert result_json.get("model") == "veo3.1-fast"
    assert result_json.get("selected_family") == "google_veo"
    assert result_json.get("provider_chain") == ["shopaikey_video"]
    assert result_json.get("provider_order") == ["shopaikey_video"]
    assert result_json.get("effective_primary_for_low_basic") == "shopaikey_video"

    # Verify zero Key4U / Kling contamination in authoritative routing fields
    assert result_json.get("selected_provider") != "key4u_video"
    assert "key4u_video" not in (result_json.get("provider_chain") or [])
    assert "key4u_video" not in (result_json.get("provider_order") or [])
    assert "key4u_video" not in (result_json.get("configured_provider_chain") or [])
    assert "key4u_video" not in (result_json.get("effective_provider_chain") or [])
    assert "key4u_video" not in (result_json.get("provider_model_map") or {})
    assert result_json.get("selected_family") != "kling"

    # Verify scene tasks authority preservation
    scene_tasks = result_json.get("scene_tasks") or []
    assert len(scene_tasks) == 2
    for task in scene_tasks:
        assert task.get("selected_provider") == "shopaikey_video"
        assert task.get("selected_model") == "veo3.1-fast"
        assert task.get("selected_family") == "google_veo"
        assert task.get("model_used") == "veo3.1-fast"
        assert task.get("provider_model_map", {}).get("shopaikey_video") == "veo3.1-fast"
        assert "key4u_video" not in (task.get("provider_model_map") or {})

    # Verify hydrated and worker payload
    hydrated = queue.hydrate_video_job_payload(conn, job_row)
    assert hydrated.get("selected_provider") == "shopaikey_video"
    assert hydrated.get("selected_model") == "veo3.1-fast"
    assert hydrated.get("selected_family") == "google_veo"

    worker_payload = remote_worker_api.build_worker_job_payload(hydrated)
    assert worker_payload.get("selected_provider") == "shopaikey_video"
    assert worker_payload.get("selected_model") == "veo3.1-fast"
    assert worker_payload.get("selected_family") == "google_veo"


def test_storyboard_queue_confirm_shopaikey_veo_alias(sample_panels, tmp_path, monkeypatch):
    """ShopAIKey + veo_3_1-fast alias preserves authority end-to-end through queue confirm."""
    conn, db_path = _setup_db(tmp_path)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("SHOPAIKEY_VIDEO_API_KEY", "test_key_veo")

    user_id = 8842
    session = _make_session(sample_panels, selected_provider="shopaikey_video", selected_model="veo_3_1-fast", user_id=user_id)

    project = bot.video_b14_prepare_project_for_invoice(user_id=user_id, session=session)
    project_id = int(project["project_id"])

    confirm_res = queue.confirm_video_project_invoice(conn, project_id=project_id, user_id=user_id, billing_exempt=True)
    assert confirm_res["ok"] is True
    job_id = int(confirm_res["job"]["id"])

    job_row = queue.get_video_render_job(conn, job_id)
    result_json = json.loads(str(job_row.get("result_json") or "{}"))
    assert result_json.get("selected_provider") == "shopaikey_video"
    assert result_json.get("selected_model") == "veo_3_1-fast"
    assert result_json.get("selected_family") == "google_veo"


# ==============================================================================
# 2. Key4U + Kling Backward Compatibility
# ==============================================================================


def test_storyboard_queue_confirm_key4u_kling_v3_backcompat(sample_panels, tmp_path, monkeypatch):
    """Key4U + kling-v3 retains Key4U/Kling authority without disruption."""
    conn, db_path = _setup_db(tmp_path)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("KEY4U_VIDEO_ENABLED", "1")
    monkeypatch.setenv("KEY4U_VIDEO_API_KEY", "test_key_kling")
    monkeypatch.setenv("KEY4U_VIDEO_AUTH_HEADER_VALUE", "Bearer test_token")
    monkeypatch.setenv("KEY4U_VIDEO_MODEL", "kling-v3")
    monkeypatch.setenv("KEY4U_KLING_I2V_ENDPOINT", "https://api.key4u.shop/kling/v1/videos/image2video")
    monkeypatch.setenv("KEY4U_KLING_VIDEO_POLL_URL", "https://api.key4u.shop/kling/v1/videos/image2video/{task_id}")
    monkeypatch.setenv("KEY4U_VIDEO_SUBMIT_URL", "https://api.key4u.shop/kling/v1/videos/image2video")
    monkeypatch.setenv("KEY4U_VIDEO_POLL_URL", "https://api.key4u.shop/kling/v1/videos/image2video/{task_id}")
    monkeypatch.setenv("KEY4U_VIDEO_ENDPOINT", "https://api.key4u.shop/kling/v1/videos/image2video")

    user_id = 8843
    session = _make_session(sample_panels, selected_provider="key4u_video", selected_model="kling-v3", user_id=user_id)

    project = bot.video_b14_prepare_project_for_invoice(user_id=user_id, session=session)
    project_id = int(project["project_id"])

    confirm_res = queue.confirm_video_project_invoice(conn, project_id=project_id, user_id=user_id, billing_exempt=True)
    assert confirm_res["ok"] is True
    job_id = int(confirm_res["job"]["id"])

    job_row = queue.get_video_render_job(conn, job_id)
    result_json = json.loads(str(job_row.get("result_json") or "{}"))
    assert result_json.get("selected_provider") == "key4u_video"
    assert result_json.get("selected_model") == "kling-v3"
    assert result_json.get("selected_family") == "kling"
    assert result_json.get("provider_chain") == ["key4u_video"]


def test_storyboard_queue_confirm_key4u_kling_turbo_backcompat(sample_panels, tmp_path, monkeypatch):
    """Key4U + kling-3.0-turbo retains Key4U/Kling authority without disruption."""
    conn, db_path = _setup_db(tmp_path)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("KEY4U_VIDEO_ENABLED", "1")
    monkeypatch.setenv("KEY4U_VIDEO_API_KEY", "test_key_kling")
    monkeypatch.setenv("KEY4U_VIDEO_AUTH_HEADER_VALUE", "Bearer test_token")
    monkeypatch.setenv("KEY4U_VIDEO_MODEL", "kling-3.0-turbo")
    monkeypatch.setenv("KEY4U_KLING_I2V_ENDPOINT", "https://api.key4u.shop/kling/v1/videos/image2video")
    monkeypatch.setenv("KEY4U_KLING_VIDEO_POLL_URL", "https://api.key4u.shop/kling/v1/videos/image2video/{task_id}")
    monkeypatch.setenv("KEY4U_VIDEO_SUBMIT_URL", "https://api.key4u.shop/kling/v1/videos/image2video")
    monkeypatch.setenv("KEY4U_VIDEO_POLL_URL", "https://api.key4u.shop/kling/v1/videos/image2video/{task_id}")
    monkeypatch.setenv("KEY4U_VIDEO_ENDPOINT", "https://api.key4u.shop/kling/v1/videos/image2video")

    user_id = 8844
    session = _make_session(sample_panels, selected_provider="key4u_video", selected_model="kling-3.0-turbo", user_id=user_id)

    project = bot.video_b14_prepare_project_for_invoice(user_id=user_id, session=session)
    project_id = int(project["project_id"])

    confirm_res = queue.confirm_video_project_invoice(conn, project_id=project_id, user_id=user_id, billing_exempt=True)
    assert confirm_res["ok"] is True
    job_id = int(confirm_res["job"]["id"])

    job_row = queue.get_video_render_job(conn, job_id)
    result_json = json.loads(str(job_row.get("result_json") or "{}"))
    assert result_json.get("selected_provider") == "key4u_video"
    assert result_json.get("selected_model") == "kling-3.0-turbo"
    assert result_json.get("selected_family") == "kling"


# ==============================================================================
# 3. Invalid Combination Matrix (Phase G & Dynamic Diagnostics Phase D)
# ==============================================================================


@pytest.mark.parametrize("mismatched_model", ["kling-v3", "kling-3.0-turbo"])
def test_storyboard_reject_shopaikey_with_kling_models(mismatched_model):
    """shopaikey_video + Kling model fails closed with dynamic diagnostics reflecting shopaikey_video."""
    with pytest.raises(RealVideoRenderError) as exc_info:
        _resolve_storyboard_i2v_model(
            {"selected_model": mismatched_model},
            provider="shopaikey_video",
        )
    assert exc_info.value.args[0] == STORYBOARD_I2V_MODEL_NOT_PROVEN_BLOCKER
    diag = exc_info.value.diagnostics
    assert diag.get("provider") == "shopaikey_video"
    assert diag.get("model") == mismatched_model
    assert diag.get("allowed_models") == sorted(STORYBOARD_PROVEN_I2V_MODELS_BY_PROVIDER["shopaikey_video"])
    assert diag.get("no_charge") is True


@pytest.mark.parametrize("mismatched_model", ["veo3.1-fast", "veo_3_1-fast"])
def test_storyboard_reject_key4u_with_veo_models(mismatched_model):
    """key4u_video + Veo model fails closed with dynamic diagnostics reflecting key4u_video."""
    with pytest.raises(RealVideoRenderError) as exc_info:
        _resolve_storyboard_i2v_model(
            {"selected_model": mismatched_model},
            provider="key4u_video",
        )
    assert exc_info.value.args[0] == STORYBOARD_I2V_MODEL_NOT_PROVEN_BLOCKER
    diag = exc_info.value.diagnostics
    assert diag.get("provider") == "key4u_video"
    assert diag.get("model") == mismatched_model
    assert diag.get("allowed_models") == sorted(STORYBOARD_PROVEN_I2V_MODELS_BY_PROVIDER["key4u_video"])
    assert diag.get("no_charge") is True


def test_storyboard_reject_unknown_provider():
    """unknown provider fails closed with allowed_models=[] and dynamic provider name."""
    with pytest.raises(RealVideoRenderError) as exc_info:
        _resolve_storyboard_i2v_model(
            {"selected_model": "some-model"},
            provider="unsupported_diffusion_v9",
        )
    assert exc_info.value.args[0] == STORYBOARD_I2V_MODEL_NOT_PROVEN_BLOCKER
    diag = exc_info.value.diagnostics
    assert diag.get("provider") == "unsupported_diffusion_v9"
    assert diag.get("allowed_models") == []
    assert diag.get("no_charge") is True


@pytest.mark.parametrize("provider", ["shopaikey_video", "key4u_video"])
def test_storyboard_reject_known_provider_unknown_model(provider):
    """Known provider with unknown model fails closed with that provider's allowed models."""
    with pytest.raises(RealVideoRenderError) as exc_info:
        _resolve_storyboard_i2v_model(
            {"selected_model": "totally-fake-model-xyz"},
            provider=provider,
        )
    assert exc_info.value.args[0] == STORYBOARD_I2V_MODEL_NOT_PROVEN_BLOCKER
    diag = exc_info.value.diagnostics
    assert diag.get("provider") == provider
    assert diag.get("model") == "totally-fake-model-xyz"
    assert diag.get("allowed_models") == sorted(STORYBOARD_PROVEN_I2V_MODELS_BY_PROVIDER[provider])
    assert diag.get("no_charge") is True


# ==============================================================================
# 4. Kickoff Payload Construction Unit Assertions
# ==============================================================================


def test_build_product_video_confirm_kickoff_payload_shopaikey_authority():
    """Direct kickoff payload construction for shopaikey_video retains authoritative fields."""
    job_seed = {"id": 901, "job_id": 901, "status": "queued"}
    project = {
        "project_id": 1001,
        "product_type": "storyboard_prompt",
        "engine_adapter": "storyboard_scene_image_video_engine",
        "scene_count": 2,
        "invoice_json": json.dumps({
            "product_type": "storyboard_prompt",
            "selected_provider": "shopaikey_video",
            "selected_model": "veo3.1-fast",
            "model": "veo3.1-fast",
            "pinned_wire_model": "veo3.1-fast",
            "provider_chain": ["shopaikey_video"],
            "provider_order": ["shopaikey_video"],
        }),
        "asset_pack_json": json.dumps({
            "product_type": "storyboard_prompt",
            "selected_provider": "shopaikey_video",
            "selected_model": "veo3.1-fast",
            "model": "veo3.1-fast",
            "pinned_wire_model": "veo3.1-fast",
            "provider_chain": ["shopaikey_video"],
            "provider_order": ["shopaikey_video"],
            "preconfirm_candidate_keys": ["shopaikey_video"],
        }),
    }
    payload = queue.build_product_video_confirm_kickoff_payload(
        job_seed,
        project,
        provider_chain=["shopaikey_video"],
    )

    assert payload.get("selected_provider") == "shopaikey_video"
    assert payload.get("selected_model") == "veo3.1-fast"
    assert payload.get("pinned_wire_model") == "veo3.1-fast"
    assert payload.get("model") == "veo3.1-fast"
    assert payload.get("selected_family") == "google_veo"
    assert payload.get("provider_chain") == ["shopaikey_video"]
    assert payload.get("provider_order") == ["shopaikey_video"]
    assert payload.get("configured_provider_chain") == ["shopaikey_video"]
    assert payload.get("effective_provider_chain") == ["shopaikey_video"]
    assert payload.get("effective_primary_for_low_basic") == "shopaikey_video"
    assert payload.get("provider_model_map", {}).get("shopaikey_video") == "veo3.1-fast"

    # Zero Key4U / Kling references in active route fields
    assert payload.get("selected_provider") != "key4u_video"
    assert "key4u_video" not in (payload.get("provider_chain") or [])
    assert "key4u_video" not in (payload.get("provider_order") or [])
    assert "key4u_video" not in (payload.get("configured_provider_chain") or [])
    assert "key4u_video" not in (payload.get("effective_provider_chain") or [])
    assert "key4u_video" not in (payload.get("provider_model_map") or {})
    assert payload.get("selected_family") != "kling"


def test_build_product_video_confirm_kickoff_payload_rejects_unproven_model():
    """Kickoff payload construction directly raises RealVideoRenderError when model is unproven."""
    job_seed = {"id": 902, "job_id": 902, "status": "queued"}
    project = {
        "project_id": 1002,
        "product_type": "storyboard_prompt",
        "engine_adapter": "storyboard_scene_image_video_engine",
        "scene_count": 2,
        "invoice_json": json.dumps({
            "product_type": "storyboard_prompt",
            "selected_provider": "shopaikey_video",
            "selected_model": "kling-v3",
        }),
        "asset_pack_json": json.dumps({
            "product_type": "storyboard_prompt",
            "selected_provider": "shopaikey_video",
            "selected_model": "kling-v3",
        }),
    }
    with pytest.raises(RealVideoRenderError) as exc_info:
        queue.build_product_video_confirm_kickoff_payload(
            job_seed,
            project,
            provider_chain=["shopaikey_video"],
        )
    assert exc_info.value.args[0] == STORYBOARD_I2V_MODEL_NOT_PROVEN_BLOCKER
    assert exc_info.value.diagnostics["provider"] == "shopaikey_video"
    assert exc_info.value.diagnostics["model"] == "kling-v3"
    assert exc_info.value.diagnostics["no_charge"] is True


# ==============================================================================
# 5. Transaction Safety & Fail-Closed Rollback (Phase K)
# ==============================================================================


def test_storyboard_confirm_atomic_transaction_rollback_on_invalid_route(tmp_path):
    """Corrupted / unproven model during confirm rolls back transaction with zero charge and no outbox."""
    conn, _ = _setup_db(tmp_path)

    # Insert a valid product video project structure with unproven model for shopaikey
    conn.execute(
        """INSERT INTO video_projects (
            project_id, user_id, status, total_xu_estimated, is_confirmed,
            invoice_json, asset_pack_json, created_at, updated_at
        ) VALUES (
            ?, ?, ?, ?, ?,
            ?, ?, datetime('now'), datetime('now')
        )""",
        (
            2001,
            8850,
            "draft_invoice",
            668,
            0,
            json.dumps({
                "source": "product_video",
                "render_mode": "real",
                "public_user": True,
                "provider_call": True,
                "product_type": "storyboard_prompt",
                "selected_provider": "shopaikey_video",
                "selected_model": "unproven-diffusion-v1",
                "total_xu": 668,
                "quote_sha256": "dummy",
                "customer_charge_planned_xu": 668,
            }),
            json.dumps({
                "source": "product_video",
                "render_mode": "real",
                "public_user": True,
                "provider_call": True,
                "product_type": "storyboard_prompt",
                "selected_provider": "shopaikey_video",
                "selected_model": "unproven-diffusion-v1",
                "preconfirm_candidate_keys": ["shopaikey_video"],
                "customer_charge_planned_xu": 668,
            }),
        ),
    )
    conn.commit()

    # Attempt to confirm invoice
    confirm_res = queue.confirm_video_project_invoice(
        conn,
        project_id=2001,
        user_id=8850,
        billing_exempt=True,
    )

    # Invariants verification
    assert confirm_res["ok"] is False
    assert confirm_res["reason"] == "dispatch_outbox_transaction_failed"
    assert confirm_res.get("blocker") == STORYBOARD_I2V_MODEL_NOT_PROVEN_BLOCKER
    assert confirm_res.get("charge") == 0
    assert confirm_res.get("charged_xu") == 0
    assert confirm_res.get("job_created") is False
    assert confirm_res.get("dispatch_outbox_created") is False

    # Diagnostics check
    diag = confirm_res.get("diagnostics") or {}
    assert diag.get("provider") == "shopaikey_video"
    assert diag.get("model") == "unproven-diffusion-v1"
    assert diag.get("no_charge") is True

    # Assert no video_jobs were created
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM video_jobs WHERE project_id = 2001")
    assert cursor.fetchone()[0] == 0

    # Assert no video_scenes were created
    cursor.execute("SELECT COUNT(*) FROM video_scenes WHERE project_id = 2001")
    assert cursor.fetchone()[0] == 0

    # Assert no dispatch_outbox records were created
    cursor.execute("SELECT COUNT(*) FROM video_dispatch_outbox WHERE project_id = 2001")
    assert cursor.fetchone()[0] == 0


def test_storyboard_default_resolution_per_provider():
    """When no explicit candidate model is provided, each provider receives its proven default."""
    assert _resolve_storyboard_i2v_model({}, provider="shopaikey_video") == "veo3.1-fast"
    assert _resolve_storyboard_i2v_model({}, provider="key4u_video") == "kling-v3"
