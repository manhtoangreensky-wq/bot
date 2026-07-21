import asyncio
import inspect
import json
import logging
import os
import sqlite3
from types import SimpleNamespace

from fastapi.testclient import TestClient

import bot
import remote_worker
from services import remote_worker_api
from services import video_project_queue as queue
from services import worker_auth


WORKER_TOKEN = "worker-secret-token"


def _headers(token: str = WORKER_TOKEN) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _conn(tmp_path):
    conn = sqlite3.connect(tmp_path / "remote_worker_api.db")
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _seed_confirmed_job(conn, user_id=1701, max_attempts=3):
    result = remote_worker_api.create_fake_video_job_for_admin_test(conn, user_id=user_id)
    job_id = int(result["job"]["id"])
    conn.execute("UPDATE video_jobs SET max_attempts=? WHERE id=?", (int(max_attempts), job_id))
    conn.commit()
    return result


def _prepare_bot_db(monkeypatch, tmp_path):
    db_path = tmp_path / "bot_worker_api.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", WORKER_TOKEN)
    monkeypatch.setattr(bot, "WORKER_RESULT_UPLOAD_DIR", str(tmp_path / "worker_results"))
    bot.init_db()
    return db_path


def test_worker_api_requires_token(monkeypatch):
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", WORKER_TOKEN)
    client = TestClient(bot.fastapi_app)
    response = client.post("/api/v1/worker/claim", json={"worker_id": "vps-1"})
    assert response.status_code == 401


def test_worker_api_rejects_wrong_token(monkeypatch):
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", WORKER_TOKEN)
    client = TestClient(bot.fastapi_app)
    response = client.post("/api/v1/worker/claim", headers=_headers("wrong-token"), json={"worker_id": "vps-1"})
    assert response.status_code == 403


def test_worker_api_accepts_valid_token(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    client = TestClient(bot.fastapi_app)
    response = client.post("/api/v1/worker/claim", headers=_headers(), json={"worker_id": "vps-1"})
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_worker_token_not_logged(monkeypatch, caplog):
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", WORKER_TOKEN)
    caplog.set_level(logging.WARNING, logger="TOAN_AAS")
    client = TestClient(bot.fastapi_app)
    client.post("/api/v1/worker/claim", headers=_headers("very-wrong-secret-token"), json={"worker_id": "vps-1"})
    assert "very-wrong-secret-token" not in caplog.text
    assert "invalid_token" in caplog.text


def test_runtime_worker_token_masked_or_boolean_only(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "OPERATOR_API_TOKEN", "runtime-token")
    client = TestClient(bot.fastapi_app)
    payload = client.get("/runtime?token=runtime-token").json()
    assert payload["worker_api_enabled"] is True
    assert payload["local_worker_token_configured"] is True
    assert payload["remote_worker_mode_supported"] is True
    assert WORKER_TOKEN not in json.dumps(payload)


def test_worker_claim_returns_queued_job(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    conn = bot.db_connect()
    try:
        _seed_confirmed_job(conn)
    finally:
        conn.close()
    client = TestClient(bot.fastapi_app)
    response = client.post(
        "/api/v1/worker/claim",
        headers=_headers(),
        json={"worker_id": "vps-1", "capabilities": ["ffmpeg", "video_postprocess"], "max_jobs": 1},
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["job"]["job_type"] == "video_render"
    assert payload["job"]["locked_by"] == "vps-1"
    assert payload["job"]["scene_cards"]
    assert payload["job"]["addon_plan"] == {}


def test_worker_claim_atomic_no_double_claim(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    conn = bot.db_connect()
    try:
        _seed_confirmed_job(conn)
    finally:
        conn.close()
    client = TestClient(bot.fastapi_app)
    first = client.post("/api/v1/worker/claim", headers=_headers(), json={"worker_id": "vps-1"}).json()
    second = client.post("/api/v1/worker/claim", headers=_headers(), json={"worker_id": "vps-2"}).json()
    assert first["job"]
    assert second["job"] is None


def test_worker_heartbeat_extends_lease(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    conn = bot.db_connect()
    try:
        _seed_confirmed_job(conn)
    finally:
        conn.close()
    client = TestClient(bot.fastapi_app)
    job = client.post("/api/v1/worker/claim", headers=_headers(), json={"worker_id": "vps-1", "lease_seconds": 60}).json()["job"]
    response = client.post(
        "/api/v1/worker/heartbeat",
        headers=_headers(),
        json={"worker_id": "vps-1", "job_id": job["job_id"], "progress_percent": 35, "message": "rendering scene 2"},
    )
    assert response.status_code == 200
    assert response.json()["job"]["progress_percent"] == 35
    assert response.json()["job"]["progress_message"] == "rendering scene 2"


def test_worker_complete_marks_job_and_project_completed(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    conn = bot.db_connect()
    try:
        _seed_confirmed_job(conn)
    finally:
        conn.close()
    client = TestClient(bot.fastapi_app)
    job = client.post("/api/v1/worker/claim", headers=_headers(), json={"worker_id": "vps-1"}).json()["job"]
    metadata = {"worker_id": "vps-1", "job_id": job["job_id"], "result": {"ok": True}}
    response = client.post(
        "/api/v1/worker/complete",
        headers=_headers(),
        data={"metadata": json.dumps(metadata)},
        files={"file": ("result.mp4", b"fake-mp4-bytes", "video/mp4")},
    )
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["job"]["status"] == "completed"
    assert result["project"]["status"] == "completed"
    assert os.path.exists(result["project"]["final_video_path"])


def test_worker_complete_idempotent(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    conn = bot.db_connect()
    try:
        _seed_confirmed_job(conn)
    finally:
        conn.close()
    client = TestClient(bot.fastapi_app)
    job = client.post("/api/v1/worker/claim", headers=_headers(), json={"worker_id": "vps-1"}).json()["job"]
    metadata = {"worker_id": "vps-1", "job_id": job["job_id"], "result": {"ok": True}}
    first = client.post(
        "/api/v1/worker/complete",
        headers=_headers(),
        data={"metadata": json.dumps(metadata)},
        files={"file": ("result.mp4", b"fake-mp4-bytes", "video/mp4")},
    )
    second = client.post(
        "/api/v1/worker/complete",
        headers=_headers(),
        data={"metadata": json.dumps(metadata)},
        files={"file": ("result.mp4", b"fake-mp4-bytes", "video/mp4")},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["result"]["duplicate"] is True


def test_worker_fail_retries_when_retryable(tmp_path):
    conn = _conn(tmp_path)
    _seed_confirmed_job(conn, max_attempts=2)
    claim = remote_worker_api.claim_remote_worker_job(conn, worker_id="vps-1")
    result = remote_worker_api.fail_remote_worker_job(
        conn,
        worker_id="vps-1",
        job_id=int(claim["job"]["job_id"]),
        safe_error="ffmpeg failed",
        retryable=True,
    )
    assert result["status"] == "queued"


def test_worker_fail_marks_failed_after_max_attempts(tmp_path):
    conn = _conn(tmp_path)
    _seed_confirmed_job(conn, max_attempts=1)
    claim = remote_worker_api.claim_remote_worker_job(conn, worker_id="vps-1")
    result = remote_worker_api.fail_remote_worker_job(
        conn,
        worker_id="vps-1",
        job_id=int(claim["job"]["job_id"]),
        safe_error="ffmpeg failed",
        retryable=True,
    )
    assert result["status"] == "failed"


def test_worker_payload_excludes_secrets(tmp_path):
    conn = _conn(tmp_path)
    result = _seed_confirmed_job(conn)
    project_id = result["project"]["project_id"]
    queue.update_video_project(
        conn,
        project_id,
        asset_pack_json={"telegram_file_id": "file-ok", "api_key": "must-not-leak", "nested": {"token": "hidden"}},
        addon_plan_json={"voice": "off", "secret_note": "hidden"},
    )
    claim = remote_worker_api.claim_remote_worker_job(conn, worker_id="vps-1", capabilities=["ffmpeg"])
    text = json.dumps(claim["job"], ensure_ascii=False)
    assert "file-ok" in text
    assert "must-not-leak" not in text
    assert "hidden" not in text


def test_worker_only_claims_confirmed_jobs(tmp_path):
    conn = _conn(tmp_path)
    project = queue.create_video_project(conn, user_id=1777)
    queue.enqueue_video_render_job(conn, project_id=project["project_id"], user_id=1777)
    claim = remote_worker_api.claim_remote_worker_job(conn, worker_id="vps-1")
    assert claim["job"] is None


def test_worker_asset_download_requires_token(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    client = TestClient(bot.fastapi_app)
    assert client.get("/api/v1/worker/assets/demo.mp4").status_code == 401


def test_worker_cannot_access_admin_endpoint(monkeypatch):
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", WORKER_TOKEN)
    monkeypatch.setattr(bot, "OPERATOR_API_TOKEN", "operator-token")
    client = TestClient(bot.fastapi_app)
    response = client.get("/api/operator/status", headers=_headers())
    assert response.status_code in {401, 403}


def test_worker_api_does_not_touch_payos_wallet_or_public_buttons():
    block = "\n".join(
        inspect.getsource(item)
        for item in [
            bot.api_worker_claim,
            bot.api_worker_heartbeat,
            bot.api_worker_complete,
            bot.api_worker_fail,
            bot.api_worker_asset_download,
        ]
    ).lower()
    for forbidden in ("spend_fixed_credit", "payos", "wallet", "naptien", "inlinekeyboardbutton"):
        assert forbidden not in block


class CaptureMessage:
    def __init__(self):
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"text": text, **kwargs})


def test_admin_remote_worker_api_test_command(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "ADMIN_IDS", {"123"})
    monkeypatch.setattr(bot, "WORKER_RESULT_UPLOAD_DIR", str(tmp_path / "worker_results"))
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "admin_cmd.db"))
    message = CaptureMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id="123"), message=message)
    context = SimpleNamespace(args=["--fake-job", "--no-charge"])
    asyncio.run(bot.cmd_tool_test_remote_worker_api(update, context))
    assert "ADMIN TEST MODE — Remote Worker API Bridge" in message.outputs[-1]["text"]
    assert "no charge: OK" in message.outputs[-1]["text"]


def test_public_cannot_run_remote_worker_api_test(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", {"123"})
    message = CaptureMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id="456"), message=message)
    context = SimpleNamespace(args=["--fake-job", "--no-charge"])
    asyncio.run(bot.cmd_tool_test_remote_worker_api(update, context))
    assert "chỉ dành cho admin" in message.outputs[-1]["text"]


def test_remote_worker_loads_env():
    payload = remote_worker.remote_worker_config()
    assert payload["bot_api_url"]
    assert payload["worker_id"]
    assert payload["direct_sqlite_required"] is False
    assert "local_worker_token_configured" in payload


def test_remote_worker_claims_fake_job(monkeypatch):
    calls = []

    def fake_http_json(method, path, payload=None, timeout=30):
        calls.append((method, path, payload))
        return {"ok": True, "job": {"job_id": "fake-1"}}

    monkeypatch.setattr(remote_worker, "http_json", fake_http_json)
    assert remote_worker.claim_job()["job_id"] == "fake-1"
    assert calls[0][1] == "/api/v1/worker/claim"


def test_remote_worker_processes_fake_job(monkeypatch, tmp_path):
    completed = {}
    monkeypatch.setattr(remote_worker, "LOCAL_VIDEO_FAKE_RENDERER_ENABLED", True)
    monkeypatch.setattr(remote_worker, "send_heartbeat", lambda *_args, **_kwargs: None)

    def fake_render(job, work_dir):
        path = os.path.join(work_dir, "fake.mp4")
        with open(path, "wb") as handle:
            handle.write(b"fake")
        return path

    def fake_complete(job_id, result, final_video_path=""):
        completed.update({"job_id": job_id, "result": result, "path": final_video_path})
        return {"ok": True}

    monkeypatch.setattr(remote_worker, "render_fake_video", fake_render)
    monkeypatch.setattr(remote_worker, "complete_job", fake_complete)
    result = remote_worker.process_claimed_job({
        "job_id": "fake-job",
        "render_mode": "admin_test_pattern",
        "admin_video_delivery": True,
        "admin_only": True,
        "no_charge": True,
        "provider_call": False,
        "public_user": False,
        "source": remote_worker.REMOTE_WORKER_ADMIN_VIDEO_SOURCE,
    })
    assert result["ok"] is True
    assert completed["job_id"] == "fake-job"
    assert completed["result"]["bytes"] == 4


def test_remote_worker_fails_safely(monkeypatch):
    failures = []
    monkeypatch.setattr(remote_worker, "LOCAL_VIDEO_FAKE_RENDERER_ENABLED", False)
    monkeypatch.setattr(remote_worker, "claim_job", lambda: {"job_id": "fake-fail"})
    monkeypatch.setattr(remote_worker, "send_heartbeat", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(remote_worker, "fail_job", lambda *args, **kwargs: failures.append((args, kwargs)) or {"ok": True})
    assert remote_worker.run_once() == "failed"
    assert failures
    assert "shopaikey_video_config_missing" in failures[0][0][1]
    assert "key4u_video_config_missing" in failures[0][0][1]


def test_remote_worker_does_not_require_sqlite_db():
    source = inspect.getsource(remote_worker).lower()
    assert "sqlite3" not in source
    assert "db_connect" not in source
    assert "/api/v1/worker/claim" in source


def test_worker_auth_runtime_flags_boolean_only():
    flags = worker_auth.worker_api_runtime_flags("secret-value")
    assert flags == {
        "worker_api_enabled": True,
        "local_worker_token_configured": True,
        "remote_worker_mode_supported": True,
    }
