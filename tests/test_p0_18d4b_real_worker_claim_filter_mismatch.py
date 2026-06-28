import asyncio
import json
import os
import sqlite3
from types import SimpleNamespace

import bot
import remote_worker
from services import remote_worker_api
from services import video_project_queue as queue


ADMIN_UID = int(bot.ADMIN_ID)


class CaptureMessage:
    def __init__(self):
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"text": text, **kwargs})


def _conn(tmp_path):
    conn = sqlite3.connect(tmp_path / "p0_18d4b_claim_filter.db")
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _install_worker_api_loop(monkeypatch, conn):
    def fake_http_json(method, path, payload=None, timeout=30):
        payload = dict(payload or {})
        if path == "/api/v1/worker/claim":
            return remote_worker_api.claim_remote_worker_job(
                conn,
                worker_id=payload.get("worker_id") or "vps-toanaas-01",
                capabilities=payload.get("capabilities") or [],
                max_jobs=payload.get("max_jobs") or 1,
                canary_only=bool(payload.get("canary_only")),
                admin_canary_only=bool(payload.get("admin_canary_only")),
                admin_video_only=bool(payload.get("admin_video_only")),
                product_video_only=bool(payload.get("product_video_only")),
                owner_product_video_only=bool(payload.get("owner_product_video_only")),
            )
        if path == "/api/v1/worker/heartbeat":
            return remote_worker_api.heartbeat_remote_worker_job(
                conn,
                worker_id=payload.get("worker_id") or "vps-toanaas-01",
                job_id=int(payload.get("job_id") or 0),
                progress_percent=int(payload.get("progress_percent") or 0),
                message=str(payload.get("message") or ""),
            )
        if path == "/api/v1/worker/complete":
            return remote_worker_api.complete_remote_worker_job(
                conn,
                worker_id=payload.get("worker_id") or "vps-toanaas-01",
                job_id=int(payload.get("job_id") or 0),
                result=payload.get("result") or {},
                final_video_path=str((payload.get("result") or {}).get("final_video_path") or ""),
            )
        if path == "/api/v1/worker/fail":
            return remote_worker_api.fail_remote_worker_job(
                conn,
                worker_id=payload.get("worker_id") or "vps-toanaas-01",
                job_id=int(payload.get("job_id") or 0),
                safe_error=str(payload.get("safe_error") or ""),
                retryable=bool(payload.get("retryable")),
            )
        return {"ok": True}

    def fake_http_multipart(path, fields, files, timeout=120):
        metadata = json.loads(str(fields.get("metadata") or "{}"))
        file_info = next(iter(files.values()))
        output = os.path.join(os.getcwd(), f"d4b-upload-{metadata.get('job_id')}.mp4")
        with open(output, "wb") as handle:
            handle.write(file_info[1])
        try:
            return remote_worker_api.complete_remote_worker_job(
                conn,
                worker_id=metadata.get("worker_id") or "vps-toanaas-01",
                job_id=int(metadata.get("job_id") or 0),
                result=metadata.get("result") or {},
                final_video_path=output,
                uploaded_file=True,
            )
        finally:
            try:
                os.remove(output)
            except OSError:
                pass

    monkeypatch.setattr(remote_worker, "http_json", fake_http_json)
    monkeypatch.setattr(remote_worker, "http_multipart", fake_http_multipart)


def test_admin_canary_created_job_matches_admin_canary_claim_filter(tmp_path):
    conn = _conn(tmp_path)
    try:
        created = remote_worker_api.create_remote_worker_admin_canary_job(conn, admin_user_id=ADMIN_UID)
        claim = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-toanaas-01",
            capabilities=["admin_canary", "ffmpeg"],
            admin_canary_only=True,
        )
        assert claim["job"]["job_id"] == str(created["job"]["id"])
        assert claim["job"]["worker_admin_canary"] is True
        assert claim["job"]["source"] == "admin_prod_canary"
    finally:
        conn.close()


def test_admin_canary_once_claims_fresh_job(monkeypatch, tmp_path):
    conn = _conn(tmp_path)
    try:
        created = remote_worker_api.create_remote_worker_admin_canary_job(conn, admin_user_id=ADMIN_UID)
        _install_worker_api_loop(monkeypatch, conn)

        def fake_render(_job, work_dir):
            path = os.path.join(work_dir, "admin-canary.mp4")
            with open(path, "wb") as handle:
                handle.write(b"mp4")
            return path

        monkeypatch.setattr(remote_worker, "render_admin_canary_video", fake_render)
        assert remote_worker.main(["--admin-canary", "--once"]) == 0
        row = queue.get_video_render_job(conn, int(created["job"]["id"]))
        assert row["status"] == "completed"
        assert row["locked_by"] == "vps-1"
        assert row["locked_at"]
    finally:
        conn.close()


def test_admin_canary_not_auto_failed_before_claim_timeout(tmp_path):
    conn = _conn(tmp_path)
    try:
        created = remote_worker_api.create_remote_worker_admin_canary_job(conn, admin_user_id=ADMIN_UID)
        row = queue.get_video_render_job(conn, int(created["job"]["id"]))
        assert row["status"] == "queued"
        assert not row["locked_by"]
        assert not row["last_error"]
    finally:
        conn.close()


def test_admin_canary_failed_not_completed_stage(tmp_path):
    conn = _conn(tmp_path)
    try:
        created = remote_worker_api.create_remote_worker_admin_canary_job(conn, admin_user_id=ADMIN_UID)
        claim = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-toanaas-01",
            capabilities=["admin_canary", "ffmpeg"],
            admin_canary_only=True,
        )
        remote_worker_api.fail_remote_worker_job(
            conn,
            worker_id="vps-toanaas-01",
            job_id=int(claim["job"]["job_id"]),
            safe_error="RuntimeError:<redacted>",
            retryable=False,
        )
        status = remote_worker_api.get_remote_worker_admin_canary_status(conn, job_id=int(created["job"]["id"]), admin_user_id=ADMIN_UID)
        assert status["status"] == "failed"
        assert status["stage"] == "runtime_error_redacted"
        assert status["worker_id"] == "vps-toanaas-01"
        assert status["claimed_at"]
        assert status["stage"] != "completed"
    finally:
        conn.close()


def test_admin_canary_not_claimed_timeout_reason_clear(tmp_path):
    conn = _conn(tmp_path)
    try:
        created = remote_worker_api.create_remote_worker_admin_canary_job(conn, admin_user_id=ADMIN_UID)
        old = queue.now_text()
        conn.execute(
            "UPDATE video_jobs SET created_at=datetime(?, '-10 minutes'), updated_at=datetime(?, '-10 minutes') WHERE id=?",
            (old, old, int(created["job"]["id"])),
        )
        conn.commit()
        status = remote_worker_api.get_remote_worker_admin_canary_status(conn, job_id=int(created["job"]["id"]), admin_user_id=ADMIN_UID)
        assert status["status"] == "failed"
        assert status["stage"] == "not_claimed_timeout"
        assert status["reason_code"] == "not_claimed_timeout"
        assert status["worker_id"] == ""
        assert status["progress_percent"] == 0
    finally:
        conn.close()


def test_product_diagnostic_created_job_matches_owner_product_claim_filter(tmp_path):
    conn = _conn(tmp_path)
    try:
        created = remote_worker_api.create_product_video_worker_claim_test_job(conn, admin_user_id=ADMIN_UID)
        payload = remote_worker_api.build_worker_job_payload(queue.hydrate_video_job_payload(conn, created["job"]))
        assert payload["source"] == "product_video"
        assert payload["render_mode"] == "real"
        assert payload["test_pattern"] is False
        assert payload["admin_video_delivery"] is False
        assert payload["no_charge"] is True
        assert payload["public_user"] is False
        assert payload["provider_call"] is False
        assert payload["claim_only_diagnostic"] is True
        claim = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-toanaas-01",
            capabilities=["owner_product_video", "product_video", "ffmpeg"],
            owner_product_video_only=True,
        )
        assert claim["job"]["job_id"] == str(created["job"]["id"])
    finally:
        conn.close()


def test_owner_product_once_claims_fresh_diagnostic_when_public_worker_off(monkeypatch, tmp_path):
    conn = _conn(tmp_path)
    try:
        created = remote_worker_api.create_product_video_worker_claim_test_job(conn, admin_user_id=ADMIN_UID)
        _install_worker_api_loop(monkeypatch, conn)
        monkeypatch.delenv(remote_worker_api.REMOTE_WORKER_PUBLIC_ENABLED_ENV, raising=False)
        monkeypatch.setattr(remote_worker, "render_real_video", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("render_real_video_called")))
        assert remote_worker.main(["--owner-product-video", "--once"]) == 0
        row = queue.get_video_render_job(conn, int(created["job"]["id"]))
        result = json.loads(row["result_json"])
        assert row["status"] == "completed"
        assert row["locked_by"] == "vps-1"
        assert result["claim_only_diagnostic"] is True
        assert "final_video_path" not in result
    finally:
        conn.close()


def test_owner_product_diagnostic_not_claimed_by_admin_video(tmp_path):
    conn = _conn(tmp_path)
    try:
        created = remote_worker_api.create_product_video_worker_claim_test_job(conn, admin_user_id=ADMIN_UID)
        claim = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-admin-video",
            capabilities=["admin_video", "ffmpeg"],
            admin_video_only=True,
        )
        assert claim["job"] is None
        assert claim["reason"] == "no_admin_video_job"
        assert queue.get_video_render_job(conn, int(created["job"]["id"]))["status"] == "queued"
    finally:
        conn.close()


def test_owner_product_diagnostic_not_claimed_by_public_worker_when_public_off(monkeypatch, tmp_path):
    conn = _conn(tmp_path)
    try:
        created = remote_worker_api.create_product_video_worker_claim_test_job(conn, admin_user_id=ADMIN_UID)
        monkeypatch.delenv(remote_worker_api.REMOTE_WORKER_PUBLIC_ENABLED_ENV, raising=False)
        claim = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-public-product",
            capabilities=["product_video", "ffmpeg"],
            product_video_only=True,
        )
        assert claim["job"] is None
        assert claim["reason"] == "public_product_worker_disabled_or_no_owner_job"
        assert queue.get_video_render_job(conn, int(created["job"]["id"]))["status"] == "queued"
    finally:
        conn.close()


def test_product_diagnostic_does_not_use_test_pattern(tmp_path):
    conn = _conn(tmp_path)
    try:
        created = remote_worker_api.create_product_video_worker_claim_test_job(conn, admin_user_id=ADMIN_UID)
        project = created["project"]
        asset_pack = json.loads(project["asset_pack_json"])
        assert asset_pack["test_pattern"] is False
        assert asset_pack["admin_video_delivery"] is False
        assert asset_pack["claim_only_diagnostic"] is True
    finally:
        conn.close()


def test_product_diagnostic_claim_pass_without_mp4_render(monkeypatch, tmp_path):
    conn = _conn(tmp_path)
    try:
        created = remote_worker_api.create_product_video_worker_claim_test_job(conn, admin_user_id=ADMIN_UID)
        _install_worker_api_loop(monkeypatch, conn)
        monkeypatch.setattr(remote_worker, "render_real_video", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("render_real_video_called")))
        assert remote_worker.run_once(owner_product_video_only=True) == "completed"
        row = queue.get_video_render_job(conn, int(created["job"]["id"]))
        result = json.loads(row["result_json"])
        assert row["status"] == "completed"
        assert result["claim_only_diagnostic"] is True
        assert int(result["bytes"] or 0) == 0
    finally:
        conn.close()


def test_remote_worker_admin_canary_idle_reason_includes_lane_summary(monkeypatch, capsys):
    monkeypatch.setattr(
        remote_worker,
        "http_json",
        lambda *_args, **_kwargs: {
            "ok": True,
            "job": None,
            "reason": "no_admin_canary_job",
            "debug": {"claim_route": "admin_canary", "public_worker_enabled": False, "lane_counts": {"admin_canary": 0, "owner_product_video": 1, "admin_video": 0}},
        },
    )
    assert remote_worker.main(["--admin-canary", "--once"]) == 0
    output = capsys.readouterr().out
    assert "once claim_route=admin_canary" in output
    assert "admin_canary=0" in output
    assert "owner_product_video=1" in output


def test_remote_worker_owner_product_idle_reason_includes_lane_summary(monkeypatch, capsys):
    monkeypatch.setattr(
        remote_worker,
        "http_json",
        lambda *_args, **_kwargs: {
            "ok": True,
            "job": None,
            "reason": "no_owner_product_video_job",
            "debug": {"claim_route": "owner_product_video", "public_worker_enabled": False, "lane_counts": {"admin_canary": 1, "owner_product_video": 0, "admin_video": 0}},
        },
    )
    assert remote_worker.main(["--owner-product-video", "--once"]) == 0
    output = capsys.readouterr().out
    assert "once claim_route=owner_product_video" in output
    assert "public_worker_enabled=no" in output
    assert "owner_product_video=0" in output


def test_video_worker_claim_debug_admin_only(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    message = CaptureMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=123), message=message)
    asyncio.run(bot.cmd_video_worker_claim_debug(update, SimpleNamespace()))
    assert "chỉ dành cho admin" in message.outputs[-1]["text"].lower()


def test_video_worker_claim_debug_shows_mismatch_reason(monkeypatch, tmp_path):
    db_path = tmp_path / "claim_debug.db"

    def db_connect():
        conn = sqlite3.connect(db_path)
        queue.ensure_video_project_queue_schema(conn)
        return conn

    conn = db_connect()
    try:
        remote_worker_api.create_remote_worker_admin_canary_job(conn, admin_user_id=ADMIN_UID)
        remote_worker_api.create_product_video_worker_claim_test_job(conn, admin_user_id=ADMIN_UID)
    finally:
        conn.close()
    monkeypatch.setattr(bot, "db_connect", db_connect)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    message = CaptureMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=ADMIN_UID), message=message)
    asyncio.run(bot.cmd_video_worker_claim_debug(update, SimpleNamespace()))
    text = message.outputs[-1]["text"]
    assert "Video Worker Claim Debug" in text
    assert "admin_canary" in text
    assert "owner_product_video" in text
    assert "claimable" in text
    assert "PayOS" not in text


def test_no_redacted_only_reason_code():
    assert remote_worker_api.safe_worker_reason_code("redacted") != "redacted"
    assert remote_worker_api.safe_worker_reason_code("<redacted>") != "redacted"
