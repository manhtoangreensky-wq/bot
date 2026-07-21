import asyncio
import json
import sqlite3
from types import SimpleNamespace

import bot
import remote_worker
from services import remote_worker_api
from services import video_project_queue as queue


ADMIN_UID = 123
WORKER_TOKEN = "p0-18d4a-worker-token"


class CaptureMessage:
    def __init__(self):
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"text": text, **kwargs})


def _prepare_bot_db(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "p0_18d4a_bot.db"))
    monkeypatch.setattr(bot, "ADMIN_IDS", {str(ADMIN_UID)})
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", WORKER_TOKEN)
    monkeypatch.delenv(remote_worker_api.REMOTE_WORKER_PUBLIC_ENABLED_ENV, raising=False)
    monkeypatch.delenv(remote_worker_api.REMOTE_WORKER_ADMIN_CANARY_ENABLED_ENV, raising=False)
    bot.init_db()


def _admin_update():
    return SimpleNamespace(effective_user=SimpleNamespace(id=ADMIN_UID), message=CaptureMessage())


def _ctx(args=None):
    return SimpleNamespace(args=list(args or []))


def test_tool_test_video_product_worker_claim_no_generic_error(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)

    def raise_db_error(*_args, **_kwargs):
        raise sqlite3.Error("db unavailable token_should_not_leak_12345678901234567890")

    monkeypatch.setattr(remote_worker_api, "create_product_video_worker_claim_test_job", raise_db_error)
    update = _admin_update()
    asyncio.run(bot.cmd_tool_test_video_product_worker_claim(update, _ctx(["--no-charge"])))

    text = update.message.outputs[-1]["text"]
    assert "Có lỗi khi xử lý lệnh" not in text
    assert "db_error" in text
    assert "token_should_not_leak" not in text


def test_tool_test_video_product_worker_claim_creates_product_video_real_payload(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "services.video_real_render_connector.real_video_provider_readiness",
        lambda: {"ok": False, "providers": [{"provider": "shopaikey", "configured": False, "missing": ["api_key"]}]},
    )
    update = _admin_update()
    asyncio.run(bot.cmd_tool_test_video_product_worker_claim(update, _ctx(["--no-charge"])))

    text = update.message.outputs[-1]["text"]
    assert "Claimable by --owner-product-video: <code>YES</code>" in text
    assert "Job left queued for VPS: <code>YES</code>" in text
    assert "test_pattern: <code>false</code>" in text
    assert "admin_video_delivery: <code>false</code>" in text
    assert "Có lỗi khi xử lý lệnh" not in text

    conn = bot.db_connect()
    try:
        row = conn.execute("SELECT id,status,locked_by,last_error,result_json FROM video_jobs ORDER BY id DESC LIMIT 1").fetchone()
        assert row[1] == "queued"
        assert not row[2]
        assert not row[3]
        project = queue.get_video_project(conn, int(queue.get_video_render_job(conn, int(row[0]))["project_id"]))
        job = queue.get_video_render_job(conn, int(row[0]))
        payload = remote_worker_api.build_worker_job_payload(queue.hydrate_video_job_payload(conn, job))
        assert remote_worker_api.is_remote_worker_product_video_job(job, project) is True
        assert payload["source"] == "product_video"
        assert payload["render_mode"] == "real"
        assert payload["test_pattern"] is False
        assert payload["admin_video_delivery"] is False
    finally:
        conn.close()


def test_owner_product_claim_allowed_when_public_worker_off(tmp_path, monkeypatch):
    monkeypatch.delenv(remote_worker_api.REMOTE_WORKER_PUBLIC_ENABLED_ENV, raising=False)
    conn = sqlite3.connect(tmp_path / "claim_allowed.db")
    try:
        queue.ensure_video_project_queue_schema(conn)
        created = remote_worker_api.create_product_video_worker_claim_test_job(conn, admin_user_id=ADMIN_UID)
        claim = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-toanaas-01",
            capabilities=["owner_product_video", "product_video", "ffmpeg"],
            owner_product_video_only=True,
        )
        assert created["ok"] is True
        assert claim["ok"] is True
        assert claim["job"]["job_id"] == str(created["job"]["id"])
        assert claim["job"]["product_video"] is True
    finally:
        conn.close()


def test_video_worker_status_sanitized_error_reason_not_redacted_only(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "services.video_real_render_connector.real_video_provider_readiness",
        lambda: {"ok": False, "providers": [{"provider": "key4u", "configured": False, "missing": ["api_key"]}]},
    )
    conn = bot.db_connect()
    try:
        created = remote_worker_api.create_product_video_worker_claim_test_job(conn, admin_user_id=ADMIN_UID)
        job_id = int(created["job"]["id"])
        conn.execute(
            """UPDATE video_jobs
               SET status='failed', locked_by='vps-toanaas-01', progress_message='provider submit',
                   last_error=?, updated_at=?
               WHERE id=?""",
            ("RuntimeError:real_video_renderer_unavailable secret_123456789012345678901234", "2026-06-28 07:55:01", job_id),
        )
        conn.execute(
            "UPDATE video_projects SET status='failed', error_log=?, updated_at=? WHERE project_id=?",
            ("RuntimeError:real_video_renderer_unavailable secret_123456789012345678901234", "2026-06-28 07:55:01", int(created["project"]["project_id"])),
        )
        conn.commit()
    finally:
        conn.close()
    bot.set_system_setting("remote_worker:last_heartbeat", "2026-06-28 07:55:01", "test heartbeat", ADMIN_UID)
    bot.set_system_setting("remote_worker:worker_id", "vps-toanaas-01", "test worker", ADMIN_UID)

    update = _admin_update()
    asyncio.run(bot.cmd_video_worker_status(update, _ctx()))
    text = update.message.outputs[-1]["text"]
    assert "worker_runtime_error" in text
    assert "provider_not_ready" in text
    assert "RuntimeError:&lt;redacted&gt;" not in text
    assert "secret_123" not in text


def test_video_worker_status_shows_vietnam_time(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    conn = bot.db_connect()
    try:
        created = remote_worker_api.create_product_video_worker_claim_test_job(conn, admin_user_id=ADMIN_UID)
        conn.execute("UPDATE video_jobs SET updated_at=? WHERE id=?", ("2026-06-28 07:55:01", int(created["job"]["id"])))
        conn.commit()
    finally:
        conn.close()
    bot.set_system_setting("remote_worker:last_heartbeat", "2026-06-28 07:55:01", "test heartbeat", ADMIN_UID)

    update = _admin_update()
    asyncio.run(bot.cmd_video_worker_status(update, _ctx()))
    text = update.message.outputs[-1]["text"]
    assert "2026-06-28 14:55:01" in text


def test_canary_failed_status_not_completed_stage(tmp_path):
    conn = sqlite3.connect(tmp_path / "canary_failed.db")
    try:
        queue.ensure_video_project_queue_schema(conn)
        created = remote_worker_api.create_remote_worker_admin_canary_job(conn, admin_user_id=ADMIN_UID)
        job_id = int(created["job"]["id"])
        conn.execute(
            "UPDATE video_jobs SET status='failed', locked_by='', progress_message='admin canary completed', last_error='', updated_at=? WHERE id=?",
            ("2026-06-28 07:55:01", job_id),
        )
        conn.commit()
        status = remote_worker_api.get_remote_worker_admin_canary_status(conn, job_id=job_id)
    finally:
        conn.close()

    text = bot._format_remote_worker_prod_canary_status(status)
    assert "Stage: <code>waiting_worker</code>" in text
    assert "Failure: <code>not_claimed_timeout</code>" in text
    assert "Stage: <code>admin canary completed</code>" not in text


def test_canary_not_claimed_timeout_has_clear_reason(tmp_path):
    conn = sqlite3.connect(tmp_path / "canary_timeout.db")
    try:
        queue.ensure_video_project_queue_schema(conn)
        created = remote_worker_api.create_remote_worker_admin_canary_job(conn, admin_user_id=ADMIN_UID)
        job_id = int(created["job"]["id"])
        conn.execute("UPDATE video_jobs SET status='failed', locked_by='', last_error='', updated_at=? WHERE id=?", ("2026-06-28 07:55:01", job_id))
        conn.commit()
        status = remote_worker_api.get_remote_worker_admin_canary_status(conn, job_id=job_id)
    finally:
        conn.close()

    assert status["stage"] == "waiting_worker"
    assert status["safe_failure_reason"] == "not_claimed_timeout"
    assert status["safe_reason_code"] == "not_claimed_timeout"


def test_remote_worker_once_idle_logs_reason(monkeypatch, capsys):
    def fake_http_json(method, path, payload=None, timeout=30):
        return {"ok": True, "job": None, "reason": "no_owner_product_video_job"}

    monkeypatch.setattr(remote_worker, "http_json", fake_http_json)
    assert remote_worker.run_once(owner_product_video_only=True) == "idle"
    out = capsys.readouterr().out
    assert "mode=owner_product_video" in out
    assert "route=/api/v1/worker/claim" in out
    assert "reason=no_owner_product_video_job" in out


def test_no_secrets_in_worker_status(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    conn = bot.db_connect()
    try:
        created = remote_worker_api.create_product_video_worker_claim_test_job(conn, admin_user_id=ADMIN_UID)
        secret = "provider_key_should_not_leak"
        conn.execute("UPDATE video_jobs SET status='failed', locked_by='vps', last_error=? WHERE id=?", (f"RuntimeError:{secret}", int(created["job"]["id"])))
        conn.commit()
    finally:
        conn.close()

    update = _admin_update()
    asyncio.run(bot.cmd_video_worker_status(update, _ctx()))
    text = update.message.outputs[-1]["text"]
    assert "provider_key_should_not_leak" not in text


def test_product_video_diagnostic_no_test_pattern(tmp_path):
    conn = sqlite3.connect(tmp_path / "diagnostic_no_test_pattern.db")
    try:
        queue.ensure_video_project_queue_schema(conn)
        created = remote_worker_api.create_product_video_worker_claim_test_job(conn, admin_user_id=ADMIN_UID)
        project = created["project"]
        job = created["job"]
        asset = json.loads(project["asset_pack_json"])
        payload = remote_worker_api.build_worker_job_payload(queue.hydrate_video_job_payload(conn, job))
        assert asset["source"] == "product_video"
        assert asset["render_mode"] == "real"
        assert asset["test_pattern"] is False
        assert asset["admin_video_delivery"] is False
        assert payload["test_pattern"] is False
        assert payload["admin_video_delivery"] is False
    finally:
        conn.close()
