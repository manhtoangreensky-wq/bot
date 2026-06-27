import asyncio
import json
import logging
import sqlite3
from types import SimpleNamespace

from fastapi.testclient import TestClient

import bot
import remote_worker
from services import remote_worker_api
from services import video_project_queue as queue


WORKER_TOKEN = "worker-staging-secret-token"


def _headers(token: str = WORKER_TOKEN) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _prepare_bot_db(monkeypatch, tmp_path):
    db_path = tmp_path / "w3_worker_ping.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", WORKER_TOKEN)
    monkeypatch.setattr(bot, "WORKER_RESULT_UPLOAD_DIR", str(tmp_path / "worker_results"))
    bot.init_db()
    return db_path


def _seed_confirmed_job(conn, user_id=1703):
    result = remote_worker_api.create_fake_video_job_for_admin_test(conn, user_id=user_id)
    return int(result["job"]["id"])


def test_worker_ping_requires_token(monkeypatch):
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", WORKER_TOKEN)
    client = TestClient(bot.fastapi_app)
    response = client.post("/api/v1/worker/ping", json={"worker_id": "vps-1", "dry_run": True})
    assert response.status_code == 401


def test_worker_ping_accepts_valid_token(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    client = TestClient(bot.fastapi_app)
    response = client.post(
        "/api/v1/worker/ping",
        headers=_headers(),
        json={"worker_id": "vps-1", "capabilities": ["ffmpeg"], "dry_run": True},
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["worker_api_enabled"] is True
    assert payload["worker_id"] == "vps-1"
    assert payload["remote_worker_mode_supported"] is True
    assert payload["can_claim_jobs"] is False
    assert payload["dry_run"] is True


def test_worker_ping_does_not_claim_job(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    conn = bot.db_connect()
    try:
        job_id = _seed_confirmed_job(conn)
    finally:
        conn.close()
    client = TestClient(bot.fastapi_app)
    response = client.post("/api/v1/worker/ping", headers=_headers(), json={"worker_id": "vps-1", "dry_run": True})
    assert response.status_code == 200
    conn = bot.db_connect()
    try:
        row = conn.execute("SELECT status, locked_by FROM video_jobs WHERE id=?", (job_id,)).fetchone()
    finally:
        conn.close()
    assert row[0] == "queued"
    assert not row[1]


def test_worker_ping_no_secret_leak(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    client = TestClient(bot.fastapi_app)
    response = client.get("/api/v1/worker/ping?worker_id=vps-1&dry_run=true", headers=_headers())
    text = json.dumps(response.json(), ensure_ascii=False)
    assert WORKER_TOKEN not in text
    assert "authorization" not in text.lower()
    assert "db_file" not in text.lower()


def test_worker_ping_bad_token_safe_log(monkeypatch, caplog):
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", WORKER_TOKEN)
    caplog.set_level(logging.WARNING, logger="TOAN_AAS")
    bad = "bad-worker-staging-secret-token"
    client = TestClient(bot.fastapi_app)
    response = client.post("/api/v1/worker/ping", headers=_headers(bad), json={"worker_id": "vps-1"})
    assert response.status_code == 403
    assert bad not in caplog.text
    assert "invalid_token" in caplog.text


def test_remote_worker_ping_mode_masks_token(monkeypatch, capsys):
    secret = "super-secret-worker-token-value"
    monkeypatch.setattr(remote_worker, "LOCAL_WORKER_TOKEN", secret)
    monkeypatch.setattr(remote_worker, "BOT_API_URL", "https://railway.example")
    monkeypatch.setattr(remote_worker, "WORKER_ID", "vps-1")
    monkeypatch.setattr(remote_worker, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(
        remote_worker,
        "ping_server",
        lambda: {
            "ok": True,
            "dry_run": True,
            "can_claim_jobs": False,
            "build": "abc1234",
            "remote_worker_mode_supported": True,
        },
    )
    assert remote_worker.main(["--ping"]) == 0
    out = capsys.readouterr().out
    assert secret not in out
    assert "supe...alue" in out
    assert "ping: OK" in out


def test_remote_worker_dry_run_does_not_claim(monkeypatch, capsys):
    monkeypatch.setattr(remote_worker, "LOCAL_WORKER_TOKEN", "dry-run-secret-token")
    monkeypatch.setattr(remote_worker, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(
        remote_worker,
        "ping_server",
        lambda: {"ok": True, "dry_run": True, "can_claim_jobs": False, "remote_worker_mode_supported": True},
    )

    def forbidden_claim():
        raise AssertionError("dry-run must not claim jobs")

    monkeypatch.setattr(remote_worker, "claim_job", forbidden_claim)
    assert remote_worker.main(["--dry-run", "--once"]) == 0
    out = capsys.readouterr().out
    assert "claim skipped because dry-run: yes" in out


def test_remote_worker_doctor_exit_codes(monkeypatch):
    monkeypatch.setattr(remote_worker, "LOCAL_WORKER_TOKEN", "")
    monkeypatch.setattr(remote_worker, "ffmpeg_available", lambda: True)
    assert remote_worker.main(["--doctor"]) == 1
    monkeypatch.setattr(remote_worker, "LOCAL_WORKER_TOKEN", "configured-token")
    assert remote_worker.main(["--doctor"]) == 0


class CaptureMessage:
    def __init__(self):
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"text": text, **kwargs})


def test_remote_worker_status_admin_only(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", {"123"})
    message = CaptureMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id="456"), message=message)
    context = SimpleNamespace(args=[])
    asyncio.run(bot.cmd_remote_worker_status(update, context))
    assert "chỉ dành cho admin" in message.outputs[-1]["text"]


def test_remote_worker_status_no_secret_leak(monkeypatch):
    secret = "status-worker-secret-token"
    monkeypatch.setattr(bot, "ADMIN_IDS", {"123"})
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", secret)
    monkeypatch.setattr(
        bot,
        "get_system_settings",
        lambda _keys: {"remote_worker:last_heartbeat": "2026-06-27 10:00:00", "remote_worker:worker_id": "vps-1"},
    )
    message = CaptureMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id="123"), message=message)
    context = SimpleNamespace(args=[])
    asyncio.run(bot.cmd_remote_worker_status(update, context))
    text = message.outputs[-1]["text"]
    assert secret not in text
    assert "python remote_worker.py --ping" in text
    assert "LOCAL_WORKER_TOKEN configured" in text


def test_admin_provider_worker_has_remote_worker_status_button_if_supported():
    labels = [button.text for row in bot.admin_module_keyboard("provider_worker").inline_keyboard for button in row]
    assert "🤖 Remote Worker Status" in labels
    assert "🧪 Test worker API" in labels
    assert "📘 Hướng dẫn VPS" in labels


def test_tool_test_remote_worker_ping_admin_only(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", {"123"})
    message = CaptureMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id="456"), message=message)
    context = SimpleNamespace(args=["--no-charge"])
    asyncio.run(bot.cmd_tool_test_remote_worker_ping(update, context))
    assert "chỉ dành cho admin" in message.outputs[-1]["text"]


def test_tool_test_remote_worker_ping_no_charge_no_job(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", {"123"})
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", WORKER_TOKEN)
    message = CaptureMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id="123"), message=message)
    context = SimpleNamespace(args=["--no-charge"])
    asyncio.run(bot.cmd_tool_test_remote_worker_ping(update, context))
    text = message.outputs[-1]["text"]
    assert "ping: OK" in text
    assert "job claimed: NO" in text
    assert "charge: NO" in text
    assert WORKER_TOKEN not in text


def test_no_local_worker_token_literal_in_outputs(monkeypatch, tmp_path):
    secret = "literal-worker-token-never-output"
    _prepare_bot_db(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", secret)
    client = TestClient(bot.fastapi_app)
    api_text = json.dumps(
        client.post("/api/v1/worker/ping", headers={"Authorization": f"Bearer {secret}"}, json={"worker_id": "vps-1"}).json(),
        ensure_ascii=False,
    )
    monkeypatch.setattr(bot, "ADMIN_IDS", {"123"})
    message = CaptureMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id="123"), message=message)
    context = SimpleNamespace(args=["--no-charge"])
    asyncio.run(bot.cmd_tool_test_remote_worker_ping(update, context))
    assert secret not in api_text
    assert secret not in message.outputs[-1]["text"]
