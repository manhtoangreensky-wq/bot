import asyncio
import json
import sqlite3
from datetime import datetime, timedelta
from types import SimpleNamespace

import bot
import remote_worker
from services import remote_worker_api
from services import video_project_queue as queue


ADMIN_UID = int(bot.ADMIN_ID)


class CaptureMessage:
    def __init__(self, text=""):
        self.text = text
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"text": text, **kwargs})


def _conn(tmp_path):
    conn = sqlite3.connect(tmp_path / "p0_18d4a_diagnostic.db")
    queue.ensure_video_project_queue_schema(conn)
    return conn


def test_product_worker_claim_messagehandler_args_none_creates_safe_diagnostic(monkeypatch, tmp_path):
    db_path = tmp_path / "bot_product_worker_claim.db"

    def db_connect():
        return sqlite3.connect(db_path)

    monkeypatch.setattr(bot, "db_connect", db_connect)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "set_system_setting", lambda *args, **kwargs: None)
    monkeypatch.setattr(bot.worker_auth, "worker_api_runtime_flags", lambda _token: {"worker_api_enabled": True})

    from services import video_real_render_connector

    monkeypatch.setattr(
        video_real_render_connector,
        "real_video_provider_readiness",
        lambda: {"ok": True, "providers": [{"provider": "shopaikey", "configured": True}]},
    )

    message = CaptureMessage("/tool_test_video_product_worker_claim --no-charge")
    update = SimpleNamespace(effective_user=SimpleNamespace(id=ADMIN_UID), message=message)
    context = SimpleNamespace(args=None)

    asyncio.run(bot.cmd_tool_test_video_product_worker_claim(update, context))

    assert message.outputs
    text = message.outputs[-1]["text"]
    assert "Product video worker claim diagnostic" in text
    assert "Có lỗi khi xử lý lệnh" not in text
    assert "Đã tạo job kiểm tra video thật" in text

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """SELECT p.asset_pack_json,p.invoice_json,j.status
               FROM video_jobs j
               JOIN video_projects p ON p.project_id=j.project_id
               ORDER BY j.id DESC LIMIT 1"""
        ).fetchone()
    finally:
        conn.close()
    asset_pack = json.loads(row[0])
    invoice = json.loads(row[1])
    assert row[2] == "queued"
    assert asset_pack["source"] == "product_video"
    assert asset_pack["render_mode"] == "real"
    assert asset_pack["test_pattern"] is False
    assert asset_pack["admin_video_delivery"] is False
    assert asset_pack["no_charge"] is True
    assert asset_pack["public_user"] is False
    assert invoice["total_xu"] == 0


def test_video_worker_status_uses_reason_code_and_old_failed_job_note():
    text = bot.video_worker_status_text(
        {"worker_api_enabled": True, "last_remote_worker_heartbeat": "2026-06-28 07:27:16"},
        {
            "queued": 0,
            "active": 0,
            "last": {
                "job_id": 17,
                "status": "failed",
                "updated_at": "2026-06-28 07:24:42",
                "safe_failure_reason": "RuntimeError:<redacted>",
            },
        },
        {"ok": True, "providers": []},
    )
    assert "Last reason code: <code>runtime_error_redacted</code>" in text
    assert "Last note: <code>old_failed_job</code>" in text
    assert "Tạo diagnostic mới; không dùng job cũ để QA." in text
    assert "Last error:" not in text


def test_remote_worker_prod_canary_status_reports_not_claimed_timeout(tmp_path):
    conn = _conn(tmp_path)
    try:
        created = remote_worker_api.create_remote_worker_admin_canary_job(conn, admin_user_id=ADMIN_UID)
        old = queue.now_text(datetime.now() - timedelta(minutes=10))
        conn.execute(
            "UPDATE video_jobs SET created_at=?, updated_at=? WHERE id=?",
            (old, old, int(created["job"]["id"])),
        )
        conn.commit()
        status = remote_worker_api.get_remote_worker_admin_canary_status(conn, job_id=int(created["job"]["id"]), admin_user_id=ADMIN_UID)
    finally:
        conn.close()
    assert status["status"] == "queued"
    assert status["stage"] == "not_claimed_timeout"
    text = bot._format_remote_worker_prod_canary_status(status)
    assert "not_claimed_timeout" in text
    assert "admin-canary --once" in text


def test_remote_worker_prod_canary_failed_never_shows_completed_stage(tmp_path):
    conn = _conn(tmp_path)
    try:
        created = remote_worker_api.create_remote_worker_admin_canary_job(conn, admin_user_id=ADMIN_UID)
        conn.execute(
            "UPDATE video_jobs SET status='failed', progress_message='completed', last_error=? WHERE id=?",
            ("RuntimeError:<redacted>", int(created["job"]["id"])),
        )
        conn.commit()
        status = remote_worker_api.get_remote_worker_admin_canary_status(conn, job_id=int(created["job"]["id"]), admin_user_id=ADMIN_UID)
    finally:
        conn.close()
    assert status["status"] == "failed"
    assert status["stage"] == "runtime_error_redacted"
    text = bot._format_remote_worker_prod_canary_status(status)
    assert "Stage: <code>completed</code>" not in text
    assert "Reason code: <code>runtime_error_redacted</code>" in text


def test_remote_worker_prod_canary_processing_displays_claimed(tmp_path):
    conn = _conn(tmp_path)
    try:
        created = remote_worker_api.create_remote_worker_admin_canary_job(conn, admin_user_id=ADMIN_UID)
        remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-toanaas-01",
            capabilities=["admin_canary", "ffmpeg"],
            admin_canary_only=True,
        )
        status = remote_worker_api.get_remote_worker_admin_canary_status(conn, job_id=int(created["job"]["id"]), admin_user_id=ADMIN_UID)
    finally:
        conn.close()
    assert status["raw_status"] == "processing"
    assert status["status"] == "claimed"
    assert status["worker_id"] == "vps-toanaas-01"


def test_remote_worker_admin_canary_once_logs_idle_reason(monkeypatch, capsys):
    monkeypatch.setattr(
        remote_worker,
        "http_json",
        lambda _method, _path, payload=None, timeout=30: {"ok": True, "job": None, "reason": "no_admin_canary_job"},
    )
    assert remote_worker.main(["--admin-canary", "--once"]) == 0
    output = capsys.readouterr().out
    assert "once status=idle" in output
    assert "once idle_reason=no_admin_canary_job" in output


def test_remote_worker_owner_product_once_logs_idle_reason(monkeypatch, capsys):
    monkeypatch.setattr(
        remote_worker,
        "http_json",
        lambda _method, _path, payload=None, timeout=30: {"ok": True, "job": None, "reason": "no_owner_product_video_job"},
    )
    assert remote_worker.main(["--owner-product-video", "--once"]) == 0
    output = capsys.readouterr().out
    assert "once status=idle" in output
    assert "once idle_reason=no_owner_product_video_job" in output
