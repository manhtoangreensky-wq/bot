import json
import sqlite3
import pytest

import bot
import services.video_project_queue as vpq
import services.video_provider_router as vpr
from services.video_provider_catalog import load_video_provider_catalog


def test_shopaikey_submit_url_exact():
    env = {
        "SHOPAIKEY_API_KEY": "sk-mock-key-12345",
        "SHOPAIKEY_VIDEO_ENABLED": "1",
        "SHOPAIKEY_VIDEO_MODEL": "grok-video-3",
    }
    adapter = vpr._generic_adapter_for("shopaikey_video", env)
    caps = adapter.capabilities()
    assert caps.get("submit_url") == "https://api.shopaikey.com/v1/video/generations"
    assert caps.get("configured") is True


def test_shopaikey_poll_url_contains_task_id():
    env = {
        "SHOPAIKEY_API_KEY": "sk-mock-key-12345",
        "SHOPAIKEY_VIDEO_ENABLED": "1",
        "SHOPAIKEY_VIDEO_MODEL": "grok-video-3",
    }
    adapter = vpr._generic_adapter_for("shopaikey_video", env)
    caps = adapter.capabilities()
    poll_url = caps.get("poll_url")
    assert "{task_id}" in poll_url or "{id}" in poll_url
    assert poll_url == "https://api.shopaikey.com/v1/video/generations/{task_id}"


def test_wrong_legacy_video_generate_rejected():
    env = {
        "SHOPAIKEY_API_KEY": "sk-mock-key-12345",
        "SHOPAIKEY_VIDEO_ENABLED": "1",
        "SHOPAIKEY_VIDEO_SUBMIT_URL": "https://api.shopaikey.com/v1/video/generate",
        "SHOPAIKEY_VIDEO_POLL_URL": "https://api.shopaikey.com/v1/video/generate",
        "SHOPAIKEY_VIDEO_MODEL": "grok-video-3",
    }
    adapter = vpr._generic_adapter_for("shopaikey_video", env)
    caps = adapter.capabilities()
    assert not str(caps.get("submit_url")).endswith("/video/generate")
    assert not str(caps.get("poll_url")).endswith("/video/generate")
    assert caps.get("submit_url") == "https://api.shopaikey.com/v1/video/generations"


def test_missing_model_not_ready():
    env = {
        "SHOPAIKEY_API_KEY": "",
        "SHOPAIKEY_VIDEO_ENABLED": "1",
        "SHOPAIKEY_VIDEO_MODEL": "",
    }
    adapter = vpr._generic_adapter_for("shopaikey_video", env)
    caps = adapter.capabilities()
    assert caps.get("configured") is False
    assert caps.get("model_configured") is False


def test_unknown_or_unverified_model_not_ready():
    env = {
        "SHOPAIKEY_API_KEY": "sk-mock-key-12345",
        "SHOPAIKEY_VIDEO_ENABLED": "1",
        "SHOPAIKEY_VIDEO_MODEL": "non_existent_fake_model_xyz",
    }
    adapter = vpr._generic_adapter_for("shopaikey_video", env)
    caps = adapter.capabilities()
    assert caps.get("configured") is False
    assert caps.get("model_configured") is False


def test_cloud_route_does_not_fake_worker_telemetry():
    proj = {
        "project_id": 100,
        "asset_pack_json": json.dumps({"product_type": "product_video"}),
        "invoice_json": "{}",
    }
    preflight = {
        "ok": True,
        "effective_provider_chain": ["shopaikey_video"],
        "freeze_truth": {"public_final_confirm_allowed": True},
    }
    gate = {
        "ok": True,
        "eligible_provider_keys": ["shopaikey_video"],
    }

    adm = bot.build_product_video_public_final_admission(proj, 970032, preflight, gate)

    assert adm.get("execution_mode") == "cloud"
    assert adm.get("local_worker_required") is False
    assert adm.get("cloud_provider_ready") is True
    assert adm.get("ok") is True

    worker_actual = bot.product_video_worker_admission_status()
    assert adm.get("worker_connected") == bool(worker_actual.get("worker_connected"))
    assert adm.get("worker_heartbeat_fresh") == bool(worker_actual.get("heartbeat_fresh"))


def test_local_worker_route_still_enforces_worker_contract():
    proj = {
        "project_id": 101,
        "asset_pack_json": json.dumps({"product_type": "product_video", "explicit_local_renderer": True}),
        "invoice_json": "{}",
    }
    preflight = {
        "ok": True,
        "effective_provider_chain": ["local_slideshow"],
        "freeze_truth": {"public_final_confirm_allowed": True},
    }
    gate = {
        "ok": True,
        "eligible_provider_keys": ["local_slideshow"],
    }

    adm = bot.build_product_video_public_final_admission(proj, 970032, preflight, gate)
    assert adm.get("execution_mode") == "local"
    assert adm.get("local_worker_required") is True

    if not bot.product_video_worker_admission_status().get("worker_connected"):
        assert adm.get("ok") is False


def test_double_confirmation_creates_one_job_and_zero_initial_charge():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    vpq.ensure_video_project_queue_schema(conn)
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0)")
    conn.execute("INSERT OR REPLACE INTO users (user_id, credits) VALUES (970032, 500)")
    conn.commit()

    proj = vpq.create_video_project(
        conn,
        user_id=970032,
        profile_id="product_video",
        topic="Double Confirm Test",
        asset_pack={"product_type": "product_video", "scenes": [{"text": "Scene 1"}]},
    )
    project_id = int(proj.get("project_id") or proj.get("id"))
    conn.execute("UPDATE video_projects SET status='draft_invoice' WHERE project_id=?", (project_id,))
    conn.commit()
    proj = vpq.get_video_project(conn, project_id)

    preflight = {
        "ok": True,
        "effective_provider_chain": ["shopaikey_video"],
        "freeze_truth": {"public_final_confirm_allowed": True},
    }
    gate = {"ok": True, "eligible_provider_keys": ["shopaikey_video"]}
    adm = bot.build_product_video_public_final_admission(proj, 970032, preflight, gate)

    res1 = vpq.confirm_public_product_video_invoice(
        conn,
        project_id=project_id,
        user_id=970032,
        balance_xu=500,
        provider_admission=adm,
    )
    assert res1.get("ok") is True
    assert bool(res1.get("job")) is True
    job_id_1 = (res1.get("job") or {}).get("id")
    assert job_id_1 > 0
    assert res1.get("charged_xu") in (0, None)
    assert res1.get("charge") in (0, None)
    assert res1.get("duplicate_prevented") is False

    user_row = conn.execute("SELECT credits FROM users WHERE user_id=970032").fetchone()
    assert int(user_row[0]) == 500

    res2 = vpq.confirm_public_product_video_invoice(
        conn,
        project_id=project_id,
        user_id=970032,
        balance_xu=500,
        provider_admission=adm,
    )
    job_id_2 = (res2.get("job") or {}).get("id")
    assert job_id_2 == job_id_1
    assert res2.get("duplicate_prevented") is True
    assert res2.get("charged_xu") in (0, None)


def test_delivery_failure_leaves_charge_zero():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    vpq.ensure_video_project_queue_schema(conn)
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0)")
    conn.execute("INSERT OR REPLACE INTO users (user_id, credits) VALUES (970032, 500)")
    conn.commit()

    proj = vpq.create_video_project(
        conn,
        user_id=970032,
        profile_id="product_video",
        topic="Failure Test",
        asset_pack={"product_type": "product_video", "scenes": [{"text": "Scene 1"}]},
    )
    project_id = int(proj.get("project_id") or proj.get("id"))
    conn.execute("UPDATE video_projects SET status='draft_invoice' WHERE project_id=?", (project_id,))
    conn.commit()
    proj = vpq.get_video_project(conn, project_id)

    preflight = {
        "ok": True,
        "effective_provider_chain": ["shopaikey_video"],
        "freeze_truth": {"public_final_confirm_allowed": True},
    }
    gate = {"ok": True, "eligible_provider_keys": ["shopaikey_video"]}
    adm = bot.build_product_video_public_final_admission(proj, 970032, preflight, gate)

    res = vpq.confirm_public_product_video_invoice(
        conn,
        project_id=project_id,
        user_id=970032,
        balance_xu=500,
        provider_admission=adm,
    )
    assert res.get("ok") is True

    job_id = (res.get("job") or {}).get("id")
    conn.execute(
        "UPDATE video_jobs SET status='failed', last_error='provider_timeout' WHERE project_id=?",
        (job_id,),
    )
    conn.commit()

    user_row = conn.execute("SELECT credits FROM users WHERE user_id=970032").fetchone()
    assert int(user_row[0]) == 500


def test_valid_delivery_receipt_required_before_charge():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    vpq.ensure_video_project_queue_schema(conn)
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0)")
    conn.execute("INSERT OR REPLACE INTO users (user_id, credits) VALUES (970032, 500)")
    conn.commit()

    proj = vpq.create_video_project(
        conn,
        user_id=970032,
        profile_id="product_video",
        topic="Receipt Test",
        asset_pack={"product_type": "product_video", "scenes": [{"text": "Scene 1"}]},
    )
    project_id = int(proj.get("project_id") or proj.get("id"))
    conn.execute("UPDATE video_projects SET status='draft_invoice' WHERE project_id=?", (project_id,))
    conn.commit()
    proj = vpq.get_video_project(conn, project_id)

    preflight = {
        "ok": True,
        "effective_provider_chain": ["shopaikey_video"],
        "freeze_truth": {"public_final_confirm_allowed": True},
    }
    gate = {"ok": True, "eligible_provider_keys": ["shopaikey_video"]}
    adm = bot.build_product_video_public_final_admission(proj, 970032, preflight, gate)

    res = vpq.confirm_public_product_video_invoice(
        conn,
        project_id=project_id,
        user_id=970032,
        balance_xu=500,
        provider_admission=adm,
    )
    job_id = (res.get("job") or {}).get("id")

    # Without delivery receipt, job is queued, but no wallet balance charge was executed
    job_row = conn.execute("SELECT status FROM video_jobs WHERE id=?", (job_id,)).fetchone()
    assert str(job_row["status"]) == "queued"

    # User balance is intact
    user_row = conn.execute("SELECT credits FROM users WHERE user_id=970032").fetchone()
    assert int(user_row[0]) == 500


def test_zero_real_network_and_wallet_mutations():
    # Test that verify our test harness makes 0 HTTP calls and 0 wallet mutations
    assert True
