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


WORKER_TOKEN = "worker-admin-prod-canary-secret"


def _headers(token: str = WORKER_TOKEN) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _conn(tmp_path):
    conn = sqlite3.connect(tmp_path / "remote_worker_admin_prod_canary.db")
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _prepare_bot_db(monkeypatch, tmp_path):
    monkeypatch.delenv("REMOTE_WORKER_PUBLIC_ENABLED", raising=False)
    monkeypatch.delenv("REMOTE_WORKER_PRODUCTION_ENABLED", raising=False)
    monkeypatch.delenv("REMOTE_WORKER_ADMIN_CANARY_ENABLED", raising=False)
    monkeypatch.delenv("REMOTE_WORKER_MAX_ADMIN_CANARY_ACTIVE", raising=False)
    db_path = tmp_path / "bot_worker_admin_prod_canary.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", WORKER_TOKEN)
    monkeypatch.setattr(bot, "WORKER_RESULT_UPLOAD_DIR", str(tmp_path / "worker_results"))
    monkeypatch.setattr(bot, "LOCAL_WORKER_ENABLED", False)
    monkeypatch.setattr(bot, "LOCAL_WORKER_POLL_ENABLED", True)
    monkeypatch.setattr(bot, "tg_app", None)
    bot.init_db()
    return db_path


def _create_admin_canary(conn, admin_id=123):
    return remote_worker_api.create_remote_worker_admin_canary_job(conn, admin_user_id=admin_id)


def _seed_public_video_job(conn, user_id=456):
    now = queue.now_text()
    project = queue.create_video_project(
        conn,
        user_id=user_id,
        profile_id="public_video",
        topic="Public/customer video job",
        ratio="9:16",
        asset_pack={"source": "public_video", "public_user": True, "admin_only": False},
    )
    project = queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="queued_for_worker",
        is_confirmed=1,
        confirmed_at=now,
        invoice_json={"total_xu": 0, "public_user": True, "admin_only": False},
        total_xu_estimated=0,
        scene_count=1,
    )
    job = queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=user_id)
    queue.update_video_project(conn, int(project["project_id"]), job_id=int(job["id"]))
    return {"project": project, "job": job}


class CaptureMessage:
    def __init__(self):
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"text": text, **kwargs})


class CaptureQuery:
    def __init__(self, user_id=123, data="remote_worker_prod_canary_status|last"):
        self.from_user = SimpleNamespace(id=user_id)
        self.data = data
        self.outputs = []
        self.answers = []

    async def answer(self, text=None, **kwargs):
        self.answers.append({"text": text or "", **kwargs})

    async def edit_message_text(self, text, **kwargs):
        self.outputs.append({"text": text, **kwargs})


def test_remote_worker_public_enabled_false_by_default(monkeypatch):
    monkeypatch.delenv("REMOTE_WORKER_PUBLIC_ENABLED", raising=False)
    config = remote_worker_api.remote_worker_production_guard_config()
    assert config["public_enabled"] is False
    assert config["admin_canary_enabled"] is True
    assert config["max_admin_canary_active"] == 1


def test_remote_worker_public_jobs_not_claimed_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("REMOTE_WORKER_PUBLIC_ENABLED", raising=False)
    conn = _conn(tmp_path)
    seeded = _seed_public_video_job(conn)
    claim = remote_worker_api.claim_remote_worker_job(conn, worker_id="vps-1", capabilities=["ffmpeg"])
    assert claim["ok"] is True
    assert claim["job"] is None
    assert claim["reason"] == "public_worker_disabled"
    row = conn.execute("SELECT status, locked_by FROM video_jobs WHERE id=?", (int(seeded["job"]["id"]),)).fetchone()
    assert row[0] == "queued"
    assert not row[1]


def test_remote_worker_admin_canary_claim_allowed(monkeypatch, tmp_path):
    monkeypatch.delenv("REMOTE_WORKER_PUBLIC_ENABLED", raising=False)
    conn = _conn(tmp_path)
    _create_admin_canary(conn, admin_id=123)
    claim = remote_worker_api.claim_remote_worker_job(
        conn,
        worker_id="vps-admin",
        capabilities=["admin_canary", "ffmpeg"],
        admin_canary_only=True,
    )
    assert claim["ok"] is True
    assert claim["admin_canary_only"] is True
    assert claim["job"]["job_type"] == "video_render"
    assert claim["job"]["worker_admin_canary"] is True
    assert claim["job"]["admin_only"] is True
    assert claim["job"]["no_charge"] is True
    assert claim["job"]["public_user"] is False
    assert claim["job"]["provider_call"] is False


def test_remote_worker_admin_canary_max_one_active(tmp_path):
    conn = _conn(tmp_path)
    first = _create_admin_canary(conn, admin_id=123)
    second = _create_admin_canary(conn, admin_id=123)
    assert first["ok"] is True
    assert second["ok"] is False
    assert second["reason"] == "max_active_admin_canary_reached"


def test_claim_admin_canary_filter_does_not_claim_customer_job(monkeypatch, tmp_path):
    monkeypatch.delenv("REMOTE_WORKER_PUBLIC_ENABLED", raising=False)
    _prepare_bot_db(monkeypatch, tmp_path)
    conn = bot.db_connect()
    try:
        public = _seed_public_video_job(conn)
        _create_admin_canary(conn, admin_id=123)
    finally:
        conn.close()
    client = TestClient(bot.fastapi_app)
    response = client.post(
        "/api/v1/worker/claim",
        headers=_headers(),
        json={"worker_id": "vps-admin", "capabilities": ["admin_canary", "ffmpeg"], "admin_canary_only": True},
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["job"]["worker_admin_canary"] is True
    conn = bot.db_connect()
    try:
        row = conn.execute("SELECT status, locked_by FROM video_jobs WHERE id=?", (int(public["job"]["id"]),)).fetchone()
    finally:
        conn.close()
    assert row[0] == "queued"
    assert not row[1]


def test_remote_worker_prod_canary_admin_only(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", {"123"})
    message = CaptureMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id="456"), message=message)
    context = SimpleNamespace(args=["--no-charge"])
    asyncio.run(bot.cmd_remote_worker_prod_canary(update, context))
    assert "chỉ dành cho Admin" in message.outputs[-1]["text"]


def test_remote_worker_prod_canary_no_charge_required(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", {"123"})
    message = CaptureMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id="123"), message=message)
    context = SimpleNamespace(args=[])
    asyncio.run(bot.cmd_remote_worker_prod_canary(update, context))
    assert "/remote_worker_prod_canary --no-charge" in message.outputs[-1]["text"]


def test_remote_worker_prod_canary_creates_one_job_no_provider_not_public(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "ADMIN_IDS", {"123"})
    message = CaptureMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id="123"), message=message)
    context = SimpleNamespace(args=["--no-charge"])
    asyncio.run(bot.cmd_remote_worker_prod_canary(update, context))
    text = message.outputs[-1]["text"]
    assert "RW-PROD-CANARY-" in text
    assert "Trừ Xu: Không" in text
    assert "Provider: Không" in text
    assert "Public: Không" in text
    assert WORKER_TOKEN not in text
    conn = bot.db_connect()
    try:
        status = remote_worker_api.get_remote_worker_admin_canary_status(conn, admin_user_id=123)
        job = queue.get_video_render_job(conn, int(status["job_id"]))
        project = queue.get_video_project(conn, project_id=int(job["project_id"]))
    finally:
        conn.close()
    assert status["ok"] is True
    assert status["no_charge"] is True
    assert status["provider_call"] is False
    assert status["public_user"] is False
    invoice = json.loads(project["invoice_json"])
    assert invoice["total_xu"] == 0
    assert invoice["invoice_disabled"] is True


def test_remote_worker_admin_canary_once_claims_only_admin_canary(monkeypatch):
    calls = []

    def fake_http_json(method, path, payload=None, timeout=30):
        calls.append((method, path, payload))
        return {
            "ok": True,
            "job": {
                "job_id": "77",
                "job_type": "video_render",
                "worker_admin_canary": True,
                "admin_only": True,
                "no_charge": True,
                "provider_call": False,
                "public_user": False,
            },
        }

    monkeypatch.setattr(remote_worker, "http_json", fake_http_json)
    monkeypatch.setattr(remote_worker, "process_admin_canary_job", lambda job: {"ok": True})
    assert remote_worker.run_once(admin_canary_only=True) == "completed"
    assert calls[0][1] == "/api/v1/worker/claim"
    assert calls[0][2]["admin_canary_only"] is True
    assert calls[0][2]["capabilities"] == ["admin_canary", "ffmpeg"]


def test_remote_worker_admin_canary_dry_run_no_claim(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(remote_worker, "LOCAL_WORKER_TOKEN", "dry-run-admin-canary-token")
    monkeypatch.setattr(remote_worker, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(
        remote_worker,
        "ping_server",
        lambda canary=False, admin_canary=False: calls.append((canary, admin_canary))
        or {"ok": True, "dry_run": True, "can_claim_jobs": False, "remote_worker_mode_supported": True},
    )

    def forbidden_claim(*_args, **_kwargs):
        raise AssertionError("dry-run must not claim jobs")

    monkeypatch.setattr(remote_worker, "claim_job", forbidden_claim)
    assert remote_worker.main(["--dry-run", "--admin-canary", "--once"]) == 0
    assert calls == [(False, True)]
    assert "claim skipped because dry-run: yes" in capsys.readouterr().out


def test_admin_canary_generates_mp4(monkeypatch, tmp_path):
    monkeypatch.setattr(remote_worker, "local_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(remote_worker.shutil, "which", lambda name: "ffmpeg" if name == "ffmpeg" else None)

    def fake_run(command, capture_output=True, text=True, timeout=180, check=False):
        Path(command[-1]).write_bytes(b"admin-canary-mp4")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(remote_worker.subprocess, "run", fake_run)
    path = remote_worker.render_admin_canary_video({"job_id": "123", "expected_duration_seconds": 3}, str(tmp_path))
    assert path.endswith(".mp4")
    assert os.path.getsize(path) > 0


def test_admin_canary_heartbeat_progress_and_complete(monkeypatch, tmp_path):
    heartbeats = []
    completed = {}
    monkeypatch.setattr(remote_worker, "send_heartbeat", lambda job_id, progress, message="": heartbeats.append((progress, message)))

    def fake_render(job, work_dir):
        path = os.path.join(work_dir, "admin-canary.mp4")
        with open(path, "wb") as handle:
            handle.write(b"mp4")
        return path

    def fake_complete(job_id, result, final_video_path=""):
        completed.update({"job_id": job_id, "result": result, "path": final_video_path})
        return {"ok": True}

    monkeypatch.setattr(remote_worker, "render_admin_canary_video", fake_render)
    monkeypatch.setattr(remote_worker, "complete_job", fake_complete)
    result = remote_worker.process_admin_canary_job(
        {
            "job_id": "prod-canary",
            "job_type": "video_render",
            "worker_admin_canary": True,
            "admin_only": True,
            "no_charge": True,
            "provider_call": False,
            "public_user": False,
        }
    )
    assert result["ok"] is True
    assert [item[0] for item in heartbeats] == [10, 30, 60, 85, 100]
    assert completed["result"]["worker_admin_canary"] is True
    assert completed["result"]["bytes"] == 3


def test_admin_canary_complete_upload_and_duplicate(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    conn = bot.db_connect()
    try:
        _create_admin_canary(conn, admin_id=123)
    finally:
        conn.close()
    client = TestClient(bot.fastapi_app)
    job = client.post(
        "/api/v1/worker/claim",
        headers=_headers(),
        json={"worker_id": "vps-admin", "capabilities": ["admin_canary", "ffmpeg"], "admin_canary_only": True},
    ).json()["job"]
    metadata = {
        "worker_id": "vps-admin",
        "job_id": job["job_id"],
        "result": {"ok": True, "worker_admin_canary": True, "no_charge": True, "provider_call": False},
    }
    first = client.post(
        "/api/v1/worker/complete",
        headers=_headers(),
        data={"metadata": json.dumps(metadata)},
        files={"file": ("admin-canary.mp4", b"admin-canary-mp4", "video/mp4")},
    )
    second = client.post(
        "/api/v1/worker/complete",
        headers=_headers(),
        data={"metadata": json.dumps(metadata)},
        files={"file": ("admin-canary.mp4", b"admin-canary-mp4", "video/mp4")},
    )
    assert first.status_code == 200
    assert first.json()["result"]["job"]["status"] == "completed"
    assert first.json()["result"]["job"]["job_type"] == "video_render"
    assert first.json()["result"]["project"]["status"] == "completed"
    assert second.status_code == 200
    assert second.json()["result"]["duplicate"] is True


def test_admin_canary_missing_output_fails_not_success(tmp_path):
    conn = _conn(tmp_path)
    _create_admin_canary(conn, admin_id=123)
    claim = remote_worker_api.claim_remote_worker_job(
        conn,
        worker_id="vps-admin",
        capabilities=["admin_canary", "ffmpeg"],
        admin_canary_only=True,
    )
    result = remote_worker_api.complete_remote_worker_job(
        conn,
        worker_id="vps-admin",
        job_id=int(claim["job"]["job_id"]),
        result={"ok": True},
        final_video_path="",
    )
    assert result["ok"] is False
    assert result["reason"] == "admin_canary_result_file_missing"


def test_remote_worker_prod_canary_status_admin_only(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", {"123"})
    message = CaptureMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id="456"), message=message)
    context = SimpleNamespace(args=["RW-PROD-CANARY-1"])
    asyncio.run(bot.cmd_remote_worker_prod_canary_status(update, context))
    assert "chỉ dành cho Admin" in message.outputs[-1]["text"]


def test_remote_worker_prod_canary_status_shows_result_no_secret(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "ADMIN_IDS", {"123"})
    conn = bot.db_connect()
    try:
        created = _create_admin_canary(conn, admin_id=123)
        claim = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-admin",
            capabilities=["admin_canary", "ffmpeg"],
            admin_canary_only=True,
        )
        job_id = int(claim["job"]["job_id"])
        output = tmp_path / "done.mp4"
        output.write_bytes(b"mp4")
        remote_worker_api.complete_remote_worker_job(
            conn,
            worker_id="vps-admin",
            job_id=job_id,
            result={"ok": True},
            final_video_path=str(output),
            uploaded_file=True,
        )
    finally:
        conn.close()
    message = CaptureMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id="123"), message=message)
    context = SimpleNamespace(args=[created["canary_ref"]])
    asyncio.run(bot.cmd_remote_worker_prod_canary_status(update, context))
    text = message.outputs[-1]["text"]
    assert "VPS Worker Production Canary Status" in text
    assert "Result uploaded: <code>yes</code>" in text
    assert "No-charge: <code>yes</code>" in text
    assert WORKER_TOKEN not in text
    assert "final_video_path" not in text
    assert str(output) not in text


def test_admin_canary_queue_label(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    conn = bot.db_connect()
    try:
        _create_admin_canary(conn, admin_id=123)
    finally:
        conn.close()
    text = bot.freeze_queue_status_text()
    assert "OWNER/ADMIN WORKER CANARY" in text
    assert "Invoice: <code>no</code>" in text
    assert "Wallet/Xu: <code>no</code>" in text


def test_remote_worker_status_admin_canary_section(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "ADMIN_IDS", {"123"})
    conn = bot.db_connect()
    try:
        created = _create_admin_canary(conn, admin_id=123)
    finally:
        conn.close()
    bot.set_system_setting("remote_worker:last_admin_prod_canary_job_id", str(created["job"]["id"]), "test", "123")
    message = CaptureMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id="123"), message=message)
    context = SimpleNamespace(args=[])
    asyncio.run(bot.cmd_remote_worker_status(update, context))
    text = message.outputs[-1]["text"]
    assert "Admin production canary" in text
    assert created["canary_ref"] in text
    assert "Public worker enabled: <code>NO</code>" in text
    assert WORKER_TOKEN not in text


def test_admin_canary_fail_safe_reason_and_no_refund(tmp_path):
    conn = _conn(tmp_path)
    _create_admin_canary(conn, admin_id=123)
    claim = remote_worker_api.claim_remote_worker_job(
        conn,
        worker_id="vps-admin",
        capabilities=["admin_canary", "ffmpeg"],
        admin_canary_only=True,
    )
    result = remote_worker_api.fail_remote_worker_job(
        conn,
        worker_id="vps-admin",
        job_id=int(claim["job"]["job_id"]),
        safe_error="ffmpeg missing token_should_not_leak_12345678901234567890",
        retryable=False,
    )
    assert result["ok"] is True
    assert result["status"] == "failed"
    status = remote_worker_api.get_remote_worker_admin_canary_status(conn, job_id=claim["job"]["job_id"])
    assert "ffmpeg missing" in status["safe_failure_reason"]
    assert status["no_charge"] is True


def test_admin_canary_buttons_create_and_status(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "ADMIN_IDS", {"123"})
    create_query = CaptureQuery(data="remote_worker_prod_canary_create")
    asyncio.run(bot.handle_remote_worker_prod_canary_callback(SimpleNamespace(callback_query=create_query), SimpleNamespace()))
    create_text = create_query.outputs[-1]["text"]
    assert "RW-PROD-CANARY-" in create_text
    assert "Trừ Xu: Không" in create_text
    assert WORKER_TOKEN not in create_text
    status_query = CaptureQuery(data="remote_worker_prod_canary_status|last")
    asyncio.run(bot.handle_remote_worker_prod_canary_callback(SimpleNamespace(callback_query=status_query), SimpleNamespace()))
    status_text = status_query.outputs[-1]["text"]
    assert "VPS Worker Production Canary Status" in status_text
    assert "RW-PROD-CANARY-" in status_text
    assert WORKER_TOKEN not in status_text


def test_admin_canary_token_masked(monkeypatch, tmp_path):
    _prepare_bot_db(monkeypatch, tmp_path)
    client = TestClient(bot.fastapi_app)
    response = client.post(
        "/api/v1/worker/claim",
        headers=_headers(),
        json={"worker_id": "vps-admin", "capabilities": ["admin_canary", "ffmpeg"], "admin_canary_only": True},
    )
    assert WORKER_TOKEN not in json.dumps(response.json(), ensure_ascii=False)


def test_prod_canary_no_wallet_payos_or_provider_paths():
    block = "\n".join(
        inspect.getsource(item)
        for item in [
            remote_worker_api.create_remote_worker_admin_canary_job,
            remote_worker_api.claim_remote_worker_admin_canary_job,
            remote_worker_api.get_remote_worker_admin_canary_status,
            bot.cmd_remote_worker_prod_canary,
            bot.cmd_remote_worker_prod_canary_status,
            remote_worker.process_admin_canary_job,
            remote_worker.render_admin_canary_video,
        ]
    ).lower()
    for forbidden in ("spend_fixed_credit", "payos", "wallet_ledger", "naptien", "topup", "shopaikey", "key4u", "suno", "provider_task"):
        assert forbidden not in block
