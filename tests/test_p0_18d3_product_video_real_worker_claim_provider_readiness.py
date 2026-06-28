import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import bot
import remote_worker
from services import remote_worker_api
from services import video_project_queue as queue
from services.video_real_render_connector import real_video_provider_readiness


ADMIN_UID = int(bot.ADMIN_ID)
PUBLIC_UID = 918403


def _conn(tmp_path):
    conn = sqlite3.connect(tmp_path / "p0_18d3_product_worker.db")
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _seed_product_video_job(conn, *, user_id=ADMIN_UID, admin=True, scene_count=3, asset_overrides=None, addon_plan=None):
    asset_pack = {
        "source": "product_video",
        "render_mode": "real",
        "test_pattern": False,
        "admin_video_delivery": False,
        "owner_admin_test_mode": False,
        "safe_output_delivery_test": False,
        "fake_renderer_allowed": False,
        "real_renderer_required": True,
        "provider_call": True,
        "public_user": not admin,
        "admin_only": bool(admin),
        "created_by_admin": bool(admin),
        "no_charge": bool(admin),
        "admin_no_charge": bool(admin),
        "scene_count": scene_count,
        "duration_seconds": scene_count * 6,
        "original_user_prompt": "video sản phẩm thật, không test pattern",
        "provider_order": "shopaikey,key4u",
    }
    asset_pack.update(dict(asset_overrides or {}))
    project = queue.create_video_project(
        conn,
        user_id=user_id,
        profile_id="product_review",
        topic="Product real worker route",
        ratio="9:16",
        asset_pack=asset_pack,
    )
    queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="queued_for_worker",
        is_confirmed=1,
        confirmed_at=queue.now_text(),
        invoice_json={**asset_pack, "total_xu": 0 if admin else 900},
        addon_plan_json=addon_plan or {},
        total_xu_estimated=0 if admin else 900,
        scene_count=scene_count,
    )
    job = queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=user_id, max_attempts=1)
    queue.update_video_project(conn, int(project["project_id"]), job_id=int(job["id"]))
    return queue.get_video_project(conn, int(project["project_id"])), job


def test_admin_video_worker_does_not_claim_product_job(tmp_path):
    conn = _conn(tmp_path)
    try:
        project, job = _seed_product_video_job(conn, admin=True)
        claim = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-admin-video",
            capabilities=["admin_video", "ffmpeg"],
            admin_video_only=True,
        )
        assert claim["ok"] is True
        assert claim["job"] is None
        assert claim["reason"] == "no_admin_video_job"
        row = queue.get_video_render_job(conn, int(job["id"]))
        assert row["status"] == "queued"
        assert remote_worker_api.is_remote_worker_product_video_job(row, project) is True
    finally:
        conn.close()


def test_owner_product_worker_claims_admin_no_charge_product_job(tmp_path):
    conn = _conn(tmp_path)
    try:
        _project, job = _seed_product_video_job(conn, admin=True)
        claim = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-owner-product",
            capabilities=["owner_product_video", "product_video", "ffmpeg"],
            owner_product_video_only=True,
        )
        assert claim["ok"] is True
        assert claim["owner_product_video_only"] is True
        assert claim["job"]["job_id"] == str(job["id"])
        assert claim["job"]["source"] == "product_video"
        assert claim["job"]["product_video"] is True
        assert claim["job"]["render_mode"] == "real"
        assert claim["job"]["test_pattern"] is False
        assert claim["job"]["admin_video_delivery"] is False
        assert claim["job"]["provider_call"] is True
        assert claim["job"]["admin_only"] is True
        assert claim["job"]["no_charge"] is True
    finally:
        conn.close()


def test_product_worker_does_not_claim_test_pattern_job(tmp_path):
    conn = _conn(tmp_path)
    try:
        _seed_product_video_job(
            conn,
            admin=True,
            asset_overrides={
                "render_mode": "admin_test_pattern",
                "test_pattern": True,
                "provider_call": False,
            },
        )
        claim = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-product",
            capabilities=["owner_product_video", "product_video", "ffmpeg"],
            owner_product_video_only=True,
        )
        assert claim["job"] is None
        assert claim["reason"] == "no_owner_product_video_job"
    finally:
        conn.close()


def test_public_product_worker_requires_public_enabled(monkeypatch, tmp_path):
    conn = _conn(tmp_path)
    try:
        _project, first_job = _seed_product_video_job(conn, user_id=PUBLIC_UID, admin=False)
        monkeypatch.delenv(remote_worker_api.REMOTE_WORKER_PUBLIC_ENABLED_ENV, raising=False)
        disabled = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-product",
            capabilities=["product_video", "ffmpeg"],
            product_video_only=True,
        )
        assert disabled["job"] is None
        assert disabled["reason"] == "public_product_worker_disabled_or_no_owner_job"
        queue.fail_video_job(conn, job_id=int(first_job["id"]), error="test_done", retry=False)
    finally:
        conn.close()

    conn = _conn(tmp_path)
    try:
        _project, job = _seed_product_video_job(conn, user_id=PUBLIC_UID, admin=False)
        monkeypatch.setenv(remote_worker_api.REMOTE_WORKER_PUBLIC_ENABLED_ENV, "1")
        enabled = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-product",
            capabilities=["product_video", "ffmpeg"],
            product_video_only=True,
        )
        assert enabled["job"]["job_id"] == str(job["id"])
        assert enabled["job"]["public_user"] is True
        assert enabled["job"]["no_charge"] is False
    finally:
        conn.close()


def test_product_job_payload_preserves_addons_prompt_scene_count(tmp_path):
    conn = _conn(tmp_path)
    try:
        addon_plan = {
            "voice_enabled": True,
            "voice_source": "default_male",
            "music_enabled": True,
            "music_source": "default",
            "music_volume_percent": 10,
            "subtitle_enabled": True,
            "subtitle_source": "voice_script",
            "logo_enabled": True,
            "logo_source": "text",
            "logo_text": "TOAN AAS",
            "logo_position": "top_center",
        }
        _project, job = _seed_product_video_job(conn, admin=True, scene_count=3, addon_plan=addon_plan)
        payload = remote_worker_api.build_worker_job_payload(queue.hydrate_video_job_payload(conn, job))
        assert payload["original_user_prompt"]
        assert payload["scene_count"] == 3
        assert payload["expected_duration_seconds"] == 18
        assert payload["addon_plan"]["voice_enabled"] is True
        assert payload["addon_plan"]["voice_source"] == "default_male"
        assert payload["addon_plan"]["music_enabled"] is True
        assert payload["addon_plan"]["music_volume_percent"] == 10
        assert payload["addon_plan"]["subtitle_enabled"] is True
        assert payload["addon_plan"]["logo_text"] == "TOAN AAS"
        assert payload["addon_plan"]["logo_position"] == "top_center"
    finally:
        conn.close()


def test_remote_worker_owner_product_mode_claims_product_route(monkeypatch):
    calls = []
    processed = []

    def fake_http_json(method, path, payload=None, timeout=30):
        calls.append((method, path, payload))
        return {
            "ok": True,
            "job": {
                "job_id": "88",
                "job_type": "video_render",
                "source": "product_video",
                "product_video": True,
                "render_mode": "real",
                "test_pattern": False,
                "admin_video_delivery": False,
                "provider_call": True,
            },
        }

    monkeypatch.setattr(remote_worker, "http_json", fake_http_json)
    monkeypatch.setattr(remote_worker, "process_admin_video_job", lambda _job: (_ for _ in ()).throw(AssertionError("admin route must not run")))
    monkeypatch.setattr(remote_worker, "process_claimed_job", lambda job: processed.append(job) or {"ok": True})
    assert remote_worker.run_once(owner_product_video_only=True) == "completed"
    assert calls[0][1] == "/api/v1/worker/claim"
    assert calls[0][2]["owner_product_video_only"] is True
    assert "owner_product_video" in calls[0][2]["capabilities"]
    assert processed and processed[0]["source"] == "product_video"


def test_provider_failure_in_product_worker_mode_is_final_clean_failure(monkeypatch):
    failures = []
    monkeypatch.setattr(
        remote_worker,
        "claim_job",
        lambda **_kwargs: {
            "job_id": "91",
            "job_type": "video_render",
            "source": "product_video",
            "product_video": True,
            "render_mode": "real",
            "test_pattern": False,
            "admin_video_delivery": False,
            "provider_call": True,
        },
    )
    monkeypatch.setattr(remote_worker, "send_heartbeat", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(remote_worker, "render_admin_video_delivery", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("test pattern must not run")))
    monkeypatch.setattr(remote_worker, "render_real_video", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(remote_worker.REAL_VIDEO_RENDER_UNAVAILABLE)))
    monkeypatch.setattr(remote_worker, "fail_job", lambda job_id, safe_error, retryable=True, partial_artifacts=None: failures.append((job_id, safe_error, retryable)) or {"ok": True})
    assert remote_worker.run_once(owner_product_video_only=True) == "failed"
    assert failures
    assert failures[0][0] == "91"
    assert failures[0][2] is False
    assert remote_worker.REAL_VIDEO_RENDER_UNAVAILABLE in failures[0][1]


def test_product_status_clean_when_provider_missing(monkeypatch):
    monkeypatch.setattr(bot, "video_b14_fail_stale_product_job_for_status", lambda _job_id: 0)
    monkeypatch.setattr(
        bot,
        "video_b14_render_job_by_id",
        lambda _job_id: {
            "id": 15,
            "status": "failed",
            "last_error": "RuntimeError:real_video_renderer_unavailable",
            "result_json": "{}",
            "progress_percent": 10,
        },
    )
    session = {"draft": {"b14_queue_job": {"id": 15, "status": "queued"}, "b14_invoice": {"scene_count": 3, "duration_seconds": 18}}}
    text = bot.video_b14_queue_status_text(session, None, ADMIN_UID, "vi")
    assert bot.VIDEO_B14_PRODUCT_CLEAN_FAIL_MESSAGE in text
    for forbidden in ("provider", "worker", "render_mode", "test pattern", "canary", "traceback"):
        assert forbidden not in text.lower()


def test_stale_product_video_job_fails_cleanly(tmp_path):
    conn = _conn(tmp_path)
    try:
        _project, job = _seed_product_video_job(conn, admin=True)
        old = queue.now_text(datetime.now() - timedelta(hours=2))
        conn.execute("UPDATE video_jobs SET created_at=?, updated_at=? WHERE id=?", (old, old, int(job["id"])))
        conn.commit()
        failed = remote_worker_api.fail_stale_product_video_jobs(conn, max_wait_seconds=60, now=datetime.now(), job_id=int(job["id"]))
        assert failed == 1
        row = queue.get_video_render_job(conn, int(job["id"]))
        project = queue.get_video_project(conn, int(row["project_id"]))
        assert row["status"] == "failed"
        assert project["status"] == "failed"
        assert "product_video_worker_unavailable" in row["last_error"]
    finally:
        conn.close()


def test_product_worker_diagnostic_creates_product_video_real_job(tmp_path):
    conn = _conn(tmp_path)
    try:
        created = remote_worker_api.create_product_video_worker_claim_test_job(conn, admin_user_id=ADMIN_UID)
        assert created["ok"] is True
        project = created["project"]
        job = created["job"]
        payload = remote_worker_api.build_worker_job_payload(queue.hydrate_video_job_payload(conn, job))
        assert remote_worker_api.is_remote_worker_product_video_job(job, project) is True
        assert payload["source"] == "product_video"
        assert payload["render_mode"] == "real"
        assert payload["test_pattern"] is False
        assert payload["admin_video_delivery"] is False
        assert payload["provider_call"] is True
        assert payload["no_charge"] is True
    finally:
        conn.close()


def test_real_provider_readiness_reports_missing_without_secrets(monkeypatch):
    for key in list(os.environ):
        if key.startswith("SHOPAIKEY_") or key.startswith("KEY4U_"):
            monkeypatch.delenv(key, raising=False)
    readiness = real_video_provider_readiness(environ={})
    text = str(readiness).lower()
    assert readiness["ok"] is False
    assert "api_key" in text or "video_config" in text
    assert "secret" not in text
    assert "bearer" not in text


def test_key4u_url_join_does_not_double_v1():
    from providers.key4u_provider import join_provider_url

    url = join_provider_url("https://api.key4u.shop/v1", "/v1/video/create")
    assert url == "https://api.key4u.shop/v1/video/create"
    assert "/v1/v1/" not in url


def test_admin_product_worker_commands_registered_and_documented():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert 'CommandHandler("video_worker_status", cmd_video_worker_status)' in source
    assert 'tool_test_video_product_worker_claim' in source
    assert "MessageHandler(filters.Regex" in source
    assert "python remote_worker.py --owner-product-video" in source
