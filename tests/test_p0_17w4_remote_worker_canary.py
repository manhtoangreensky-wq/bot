import asyncio
import inspect
import json
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

import bot
import remote_worker
from services import remote_worker_api
from services import video_project_queue as queue


WORKER_TOKEN = "worker-canary-secret-token"


def _headers(token: str = WORKER_TOKEN) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _conn(tmp_path):
    conn = sqlite3.connect(tmp_path / "remote_worker_canary.db")
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _prepare_bot_db(monkeypatch, tmp_path):
    db_path = tmp_path / "bot_worker_canary.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", WORKER_TOKEN)
    monkeypatch.setattr(bot, "WORKER_RESULT_UPLOAD_DIR", str(tmp_path / "worker_results"))
    monkeypatch.setattr(bot, "LOCAL_WORKER_ENABLED", False)
    monkeypatch.setattr(bot, "LOCAL_WORKER_POLL_ENABLED", True)
    monkeypatch.setattr(bot, "tg_app", None)
    bot.init_db()
    return db_path


def _create_canary(conn, admin_id=123):
    return remote_worker_api.create_remote_worker_canary_job(conn, admin_user_id=admin_id)


class CaptureMessage:
    def __init__(self):
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"text": text, **kwargs})


class CaptureQuery:
    def __init__(self, user_id=123, data="remote_worker_canary_status|last"):
        self.from_user = SimpleNamespace(id=user_id)
        self.data = data
        self.outputs = []
        self.answers = []

    async def answer(self, text=None, **kwargs):
        self.answers.append({"text": text or "", **kwargs})

    async def edit_message_text(self, text, **kwargs):
        self.outputs.append({"text": text, **kwargs})


def test_canary_job_admin_only_no_charge_not_public_no_provider_call(tmp_path):
    conn = _conn(tmp_path)
    result = _create_canary(conn, admin_id=123)
    assert result["ok"] is True
    job = result["job"]
    project = result["project"]
    assert job["job_type"] == remote_worker_api.REMOTE_WORKER_CANARY_JOB_TYPE
    assert job["status"] == "queued"
    assert int(project["total_xu_estimated"]) == 0
    asset = json.loads(project["asset_pack_json"])
    invoice = json.loads(project["invoice_json"])
    for payload in (asset, invoice):
        assert payload["admin_only"] is True
        assert payload["no_charge"] is True
        assert payload["provider_call"] is False
        assert payload["public_user"] is False


def test_api_claim_canary_only_filters_jobs(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    conn = bot.db_connect()
    try:
        regular = remote_worker_api.create_fake_video_job_for_admin_test(conn, user_id=456)
        regular_job_id = int(regular["job"]["id"])
        _create_canary(conn, admin_id=123)
    finally:
        conn.close()
    client = TestClient(bot.fastapi_app)
    response = client.post(
        "/api/v1/worker/claim",
        headers=_headers(),
        json={"worker_id": "vps-canary", "capabilities": ["canary", "ffmpeg"], "canary_only": True},
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["job"]["job_type"] == remote_worker_api.REMOTE_WORKER_CANARY_JOB_TYPE
    assert payload["job"]["canary"] is True
    conn = bot.db_connect()
    try:
        row = conn.execute("SELECT status, locked_by FROM video_jobs WHERE id=?", (regular_job_id,)).fetchone()
    finally:
        conn.close()
    assert row[0] == "queued"
    assert not row[1]


def test_remote_worker_canary_does_not_claim_customer_job(tmp_path):
    conn = _conn(tmp_path)
    remote_worker_api.create_fake_video_job_for_admin_test(conn, user_id=456)
    claim = remote_worker_api.claim_remote_worker_job(
        conn,
        worker_id="vps-canary",
        capabilities=["canary", "ffmpeg"],
        canary_only=True,
    )
    assert claim["ok"] is True
    assert claim["job"] is None


def test_remote_worker_canary_once_claims_only_canary(monkeypatch):
    calls = []

    def fake_http_json(method, path, payload=None, timeout=30):
        calls.append((method, path, payload))
        return {
            "ok": True,
            "job": {
                "job_id": "77",
                "job_type": remote_worker_api.REMOTE_WORKER_CANARY_JOB_TYPE,
                "canary": True,
                "admin_only": True,
                "no_charge": True,
                "provider_call": False,
                "public_user": False,
            },
        }

    monkeypatch.setattr(remote_worker, "http_json", fake_http_json)
    monkeypatch.setattr(remote_worker, "process_canary_job", lambda job: {"ok": True})
    assert remote_worker.run_once(canary_only=True) == "completed"
    assert calls[0][1] == "/api/v1/worker/claim"
    assert calls[0][2]["canary_only"] is True
    assert calls[0][2]["capabilities"] == ["canary", "ffmpeg"]


def test_remote_worker_canary_dry_run_does_not_claim(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(remote_worker, "LOCAL_WORKER_TOKEN", "dry-run-canary-token")
    monkeypatch.setattr(remote_worker, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(
        remote_worker,
        "ping_server",
        lambda canary=False: calls.append(canary)
        or {"ok": True, "dry_run": True, "can_claim_jobs": False, "remote_worker_mode_supported": True},
    )

    def forbidden_claim(*_args, **_kwargs):
        raise AssertionError("dry-run must not claim jobs")

    monkeypatch.setattr(remote_worker, "claim_job", forbidden_claim)
    assert remote_worker.main(["--dry-run", "--canary", "--once"]) == 0
    assert calls == [True]
    assert "claim skipped because dry-run: yes" in capsys.readouterr().out


def test_canary_generates_nonzero_mp4(monkeypatch, tmp_path):
    monkeypatch.setattr(remote_worker, "local_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(remote_worker.shutil, "which", lambda name: "ffmpeg" if name == "ffmpeg" else None)

    def fake_run(command, capture_output=True, text=True, timeout=120, check=False):
        Path(command[-1]).write_bytes(b"fake-mp4-bytes")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(remote_worker.subprocess, "run", fake_run)
    path = remote_worker.render_canary_video({"job_id": "123"}, str(tmp_path))
    assert path.endswith(".mp4")
    assert os.path.getsize(path) > 0


def test_canary_missing_ffmpeg_safe_fail(monkeypatch):
    failures = []
    monkeypatch.setattr(
        remote_worker,
        "claim_job",
        lambda canary_only=False: {
            "job_id": "88",
            "job_type": remote_worker_api.REMOTE_WORKER_CANARY_JOB_TYPE,
            "canary": True,
            "admin_only": True,
            "no_charge": True,
            "provider_call": False,
            "public_user": False,
        },
    )
    monkeypatch.setattr(remote_worker, "send_heartbeat", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(remote_worker, "local_ffmpeg_path", lambda: "missing-ffmpeg")
    monkeypatch.setattr(remote_worker.shutil, "which", lambda _name: None)
    monkeypatch.setattr(remote_worker, "fail_job", lambda *args, **kwargs: failures.append((args, kwargs)) or {"ok": True})
    assert remote_worker.run_once(canary_only=True) == "failed"
    assert failures
    assert "ffmpeg_missing" in failures[0][0][1]
    assert failures[0][1]["retryable"] is False


def test_canary_complete_upload_marks_completed_and_duplicate(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    conn = bot.db_connect()
    try:
        _create_canary(conn, admin_id=123)
    finally:
        conn.close()
    client = TestClient(bot.fastapi_app)
    job = client.post(
        "/api/v1/worker/claim",
        headers=_headers(),
        json={"worker_id": "vps-canary", "capabilities": ["canary", "ffmpeg"], "canary_only": True},
    ).json()["job"]
    metadata = {
        "worker_id": "vps-canary",
        "job_id": job["job_id"],
        "result": {"ok": True, "canary": True, "no_charge": True, "provider_call": False},
    }
    first = client.post(
        "/api/v1/worker/complete",
        headers=_headers(),
        data={"metadata": json.dumps(metadata)},
        files={"file": ("canary.mp4", b"canary-mp4-bytes", "video/mp4")},
    )
    second = client.post(
        "/api/v1/worker/complete",
        headers=_headers(),
        data={"metadata": json.dumps(metadata)},
        files={"file": ("canary.mp4", b"canary-mp4-bytes", "video/mp4")},
    )
    assert first.status_code == 200
    assert first.json()["result"]["job"]["status"] == "completed"
    assert first.json()["result"]["project"]["status"] == "completed"
    assert first.json()["result"]["job"]["job_type"] == remote_worker_api.REMOTE_WORKER_CANARY_JOB_TYPE
    assert second.status_code == 200
    assert second.json()["result"]["duplicate"] is True


def test_canary_result_path_safe(tmp_path):
    path = remote_worker_api.save_uploaded_result(
        tmp_path / "worker_results",
        job_id=7,
        filename="../bad\\name.txt",
        content=b"canary",
    )
    assert Path(path).parent == tmp_path / "worker_results"
    assert Path(path).suffix == ".mp4"
    assert ".." not in Path(path).name


def test_canary_sends_admin_if_tg_available(monkeypatch, tmp_path):
    sent = {}
    final_path = tmp_path / "canary.mp4"
    final_path.write_bytes(b"canary-mp4")

    class FakeBot:
        async def send_video(self, chat_id, video, caption):
            sent["chat_id"] = chat_id
            sent["caption"] = caption
            sent["bytes"] = len(video.read())

    monkeypatch.setattr(bot, "tg_app", SimpleNamespace(bot=FakeBot()))
    result = {
        "ok": True,
        "job": {"id": 9, "job_type": remote_worker_api.REMOTE_WORKER_CANARY_JOB_TYPE},
        "project": {"user_id": "123", "final_video_path": str(final_path), "asset_pack_json": json.dumps({"source": "admin_canary"})},
    }
    delivery = asyncio.run(bot.maybe_send_remote_worker_final_video(result))
    assert delivery["sent"] is True
    assert sent["chat_id"] == 123
    assert "Canary" in sent["caption"]
    assert sent["bytes"] > 0


def test_remote_worker_canary_command_admin_only(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", {"123"})
    message = CaptureMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id="456"), message=message)
    context = SimpleNamespace(args=["--no-charge"])
    asyncio.run(bot.cmd_remote_worker_canary(update, context))
    assert "chỉ dành cho Admin" in message.outputs[-1]["text"]


def test_remote_worker_canary_requires_no_charge_arg(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", {"123"})
    message = CaptureMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id="123"), message=message)
    context = SimpleNamespace(args=[])
    asyncio.run(bot.cmd_remote_worker_canary(update, context))
    assert "/remote_worker_canary --no-charge" in message.outputs[-1]["text"]


def test_remote_worker_canary_creates_safe_job_no_secret_leak(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "ADMIN_IDS", {"123"})
    message = CaptureMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id="123"), message=message)
    context = SimpleNamespace(args=["--no-charge"])
    asyncio.run(bot.cmd_remote_worker_canary(update, context))
    text = message.outputs[-1]["text"]
    assert "RW-CANARY-" in text
    assert "Trừ Xu: Không" in text
    assert "Gọi provider: Không" in text
    assert WORKER_TOKEN not in text
    conn = bot.db_connect()
    try:
        status = remote_worker_api.get_remote_worker_canary_status(conn, admin_user_id=123)
    finally:
        conn.close()
    assert status["ok"] is True
    assert status["no_charge"] is True
    assert status["provider_call"] is False


def test_remote_worker_canary_status_admin_only(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", {"123"})
    message = CaptureMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id="456"), message=message)
    context = SimpleNamespace(args=["RW-CANARY-1"])
    asyncio.run(bot.cmd_remote_worker_canary_status(update, context))
    assert "chỉ dành cho Admin" in message.outputs[-1]["text"]


def test_remote_worker_canary_status_shows_progress_no_secret_leak(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "ADMIN_IDS", {"123"})
    conn = bot.db_connect()
    try:
        created = _create_canary(conn, admin_id=123)
        claim = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-canary",
            capabilities=["canary", "ffmpeg"],
            canary_only=True,
        )
        job_id = int(claim["job"]["job_id"])
        remote_worker_api.heartbeat_remote_worker_job(conn, worker_id="vps-canary", job_id=job_id, progress_percent=70, message="canary uploading")
    finally:
        conn.close()
    message = CaptureMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id="123"), message=message)
    context = SimpleNamespace(args=[created["canary_ref"]])
    asyncio.run(bot.cmd_remote_worker_canary_status(update, context))
    text = message.outputs[-1]["text"]
    assert "70%" in text
    assert "vps-canary" in text
    assert WORKER_TOKEN not in text
    assert "final_video_path" not in text


def test_remote_worker_canary_buttons_create_and_status(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "ADMIN_IDS", {"123"})
    create_query = CaptureQuery(data="remote_worker_canary_create")
    asyncio.run(bot.handle_remote_worker_canary_callback(SimpleNamespace(callback_query=create_query), SimpleNamespace()))
    create_text = create_query.outputs[-1]["text"]
    assert "RW-CANARY-" in create_text
    assert "Trừ Xu: Không" in create_text
    assert WORKER_TOKEN not in create_text

    status_query = CaptureQuery(data="remote_worker_canary_status|last")
    asyncio.run(bot.handle_remote_worker_canary_callback(SimpleNamespace(callback_query=status_query), SimpleNamespace()))
    status_text = status_query.outputs[-1]["text"]
    assert "Remote Worker Canary Status" in status_text
    assert "RW-CANARY-" in status_text
    assert WORKER_TOKEN not in status_text


def test_remote_worker_status_includes_canary_and_production_jobs_not_enabled(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "ADMIN_IDS", {"123"})
    conn = bot.db_connect()
    try:
        created = _create_canary(conn, admin_id=123)
    finally:
        conn.close()
    bot.set_system_setting("remote_worker:last_canary_job_id", str(created["job"]["id"]), "test", "123")
    message = CaptureMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id="123"), message=message)
    context = SimpleNamespace(args=[])
    asyncio.run(bot.cmd_remote_worker_status(update, context))
    text = message.outputs[-1]["text"]
    assert "Canary" in text
    assert created["canary_ref"] in text
    assert "Production jobs enabled: <code>no</code>" in text
    assert WORKER_TOKEN not in text


def test_canary_no_wallet_payment_or_provider_paths():
    block = "\n".join(
        inspect.getsource(item)
        for item in [
            remote_worker_api.create_remote_worker_canary_job,
            remote_worker_api.claim_remote_worker_canary_job,
            bot.cmd_remote_worker_canary,
            bot.cmd_remote_worker_canary_status,
        ]
    ).lower()
    for forbidden in ("spend_fixed_credit", "payos", "wallet", "naptien", "topup", "shopaikey", "key4u", "suno"):
        assert forbidden not in block


def test_canary_no_provider_env_used():
    block = (
        inspect.getsource(remote_worker.process_canary_job)
        + inspect.getsource(remote_worker.render_canary_video)
    ).lower()
    for forbidden in ("shopaikey", "key4u", "suno", "api_key", "provider_task"):
        assert forbidden not in block


def test_canary_does_not_expose_token(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    client = TestClient(bot.fastapi_app)
    response = client.post(
        "/api/v1/worker/claim",
        headers=_headers(),
        json={"worker_id": "vps-canary", "capabilities": ["canary", "ffmpeg"], "canary_only": True},
    )
    assert WORKER_TOKEN not in json.dumps(response.json(), ensure_ascii=False)
