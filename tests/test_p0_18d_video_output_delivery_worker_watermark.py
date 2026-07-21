import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import bot
import remote_worker
from services import remote_worker_api
from services import video_project_queue as queue


def _conn(tmp_path):
    conn = sqlite3.connect(tmp_path / "p0_18d_video_delivery.db")
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _seed_public_video_job(conn, user_id=456):
    now = queue.now_text()
    project = queue.create_video_project(
        conn,
        user_id=user_id,
        profile_id="public_video",
        topic="Public customer video",
        ratio="9:16",
        asset_pack={"source": "public_video", "public_user": True, "admin_only": False},
    )
    project = queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="queued_for_worker",
        is_confirmed=1,
        confirmed_at=now,
        invoice_json={"total_xu": 900, "public_user": True, "admin_only": False, "no_charge": False},
        total_xu_estimated=900,
        scene_count=3,
    )
    job = queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=user_id)
    queue.update_video_project(conn, int(project["project_id"]), job_id=int(job["id"]))
    return {"project": project, "job": job}


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def test_p0_18d_audit_report_exists():
    report = Path("docs/reports/P0_18D_VIDEO_OUTPUT_DELIVERY_AUDIT.md")
    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    assert "admin-video" in text
    assert "logo/watermark" in text
    assert "Scene 20" in text


def test_admin_video_claim_skips_public_customer_job(tmp_path):
    conn = _conn(tmp_path)
    public = _seed_public_video_job(conn)
    admin = remote_worker_api.create_admin_video_delivery_test_job(conn, admin_user_id=123, scene_count=3, duration_seconds=18)
    claim = remote_worker_api.claim_remote_worker_job(
        conn,
        worker_id="vps-admin-video",
        capabilities=["admin_video", "ffmpeg"],
        admin_video_only=True,
    )
    assert admin["ok"] is True
    assert claim["ok"] is True
    assert claim["admin_video_only"] is True
    assert claim["job"]["job_id"] == str(admin["job"]["id"])
    assert claim["job"]["admin_video_delivery"] is True
    assert claim["job"]["admin_only"] is True
    assert claim["job"]["no_charge"] is True
    assert claim["job"]["public_user"] is False
    row = conn.execute("SELECT status, locked_by FROM video_jobs WHERE id=?", (int(public["job"]["id"]),)).fetchone()
    assert row[0] == "queued"
    assert not row[1]


def test_admin_video_complete_requires_real_mp4(tmp_path):
    conn = _conn(tmp_path)
    remote_worker_api.create_admin_video_delivery_test_job(conn, admin_user_id=123)
    claim = remote_worker_api.claim_remote_worker_job(
        conn,
        worker_id="vps-admin-video",
        capabilities=["admin_video", "ffmpeg"],
        admin_video_only=True,
    )
    missing = remote_worker_api.complete_remote_worker_job(
        conn,
        worker_id="vps-admin-video",
        job_id=int(claim["job"]["job_id"]),
        result={"ok": True, "admin_video_delivery": True},
        final_video_path="",
    )
    assert missing["ok"] is False
    assert missing["reason"] == "admin_video_result_file_missing"

    output = tmp_path / "admin-video.mp4"
    output.write_bytes(b"real-mp4")
    completed = remote_worker_api.complete_remote_worker_job(
        conn,
        worker_id="vps-admin-video",
        job_id=int(claim["job"]["job_id"]),
        result={"ok": True, "admin_video_delivery": True},
        final_video_path=str(output),
        uploaded_file=True,
    )
    assert completed["ok"] is True
    assert completed["job"]["status"] == "completed"
    assert completed["project"]["final_video_path"] == str(output)


def test_remote_worker_admin_video_once_claims_only_admin_video(monkeypatch):
    calls = []

    def fake_http_json(method, path, payload=None, timeout=30):
        calls.append((method, path, payload))
        return {
            "ok": True,
            "job": {
                "job_id": "88",
                "job_type": "video_render",
                "admin_video_delivery": True,
                "admin_only": True,
                "no_charge": True,
                "provider_call": False,
                "public_user": False,
                "source": remote_worker.REMOTE_WORKER_ADMIN_VIDEO_SOURCE,
            },
        }

    monkeypatch.setattr(remote_worker, "http_json", fake_http_json)
    monkeypatch.setattr(remote_worker, "process_admin_video_job", lambda job: {"ok": True})
    assert remote_worker.run_once(admin_video_only=True) == "completed"
    assert calls[0][1] == "/api/v1/worker/claim"
    assert calls[0][2]["admin_video_only"] is True
    assert calls[0][2]["capabilities"] == ["admin_video", "ffmpeg"]


def test_remote_worker_admin_video_dry_run_does_not_claim(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(remote_worker, "LOCAL_WORKER_TOKEN", "dry-run-admin-video-token")
    monkeypatch.setattr(remote_worker, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(
        remote_worker,
        "ping_server",
        lambda canary=False, admin_canary=False, admin_video=False: calls.append((canary, admin_canary, admin_video))
        or {"ok": True, "dry_run": True, "can_claim_jobs": False, "remote_worker_mode_supported": True},
    )

    def forbidden_claim(*_args, **_kwargs):
        raise AssertionError("dry-run must not claim jobs")

    monkeypatch.setattr(remote_worker, "claim_job", forbidden_claim)
    assert remote_worker.main(["--dry-run", "--admin-video", "--once"]) == 0
    assert calls == [(False, False, True)]
    assert "claim skipped because dry-run: yes" in capsys.readouterr().out


def test_admin_video_renderer_writes_mp4(monkeypatch, tmp_path):
    monkeypatch.setattr(remote_worker, "local_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(remote_worker.shutil, "which", lambda name: "ffmpeg" if name == "ffmpeg" else None)

    def fake_run(command, capture_output=True, text=True, timeout=180, check=False):
        Path(command[-1]).write_bytes(b"admin-video-mp4")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(remote_worker.subprocess, "run", fake_run)
    path = remote_worker.render_admin_video_delivery({"job_id": "123", "expected_duration_seconds": 6}, str(tmp_path))
    assert path.endswith(".mp4")
    assert os.path.getsize(path) > 0


def test_watermark_menu_restored():
    callbacks = _callbacks(bot.video_b14_logo_keyboard("vi"))
    labels = [button.text for row in bot.video_b14_logo_keyboard("vi").inline_keyboard for button in row]
    assert "vproduct|b14_logo_text_start" in callbacks
    assert "vproduct|b14_logo_source|default_watermark" not in callbacks
    assert "vproduct|b14_logo_source|uploaded" not in callbacks
    assert any("Nhập chữ logo/watermark" in label for label in labels)


def test_scene_buttons_public_include_10_20_and_20_discount():
    callbacks = _callbacks(bot.video_b14_scene_count_keyboard(user_id=999, lang="vi"))
    for count in (1, 3, 5, 10, 20):
        assert f"vproduct|b14_scene_count|{count}" in callbacks
    assert bot.video_b14_invoice_breakdown(300, 20)["discount_percent"] == 30


def test_public_status_copy_hides_technical_words():
    session = {
        "draft": {
            "b14_queue_job": {"id": 1, "status": "queued", "locked_by": "vps-secret"},
            "b14_invoice": {"scene_count": 3, "duration_seconds": 18, "package_label": "Cơ bản"},
        }
    }
    text = bot.video_b14_queue_status_text(session, None, user_id=999, lang="vi")
    lowered = text.lower()
    for forbidden in ("worker", "queue", "provider", "api", "ffmpeg", "lease", "traceback", "vps-secret"):
        assert forbidden not in lowered
    assert "tiến trình" in lowered
    assert "video hoàn chỉnh" in lowered
