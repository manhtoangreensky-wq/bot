import asyncio
import json
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

import bot
import remote_worker
from services import remote_worker_api
from services import video_project_queue as queue


ADMIN_UID = int(bot.ADMIN_ID)
PUBLIC_UID = 918402


def _setup_bot_db(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "p0_18d2_bot.db"))
    bot.init_db()


def _product_session(topic="video quảng cáo nước hoa nam sang trọng đăng TikTok", *, addon_plan=None):
    return {
        "product_id": "multi_scene_film",
        "topic": topic,
        "original_user_prompt": topic,
        "draft": {
            "topic": topic,
            "b14_profile_id": "product_review",
            "b14_quality_xu": 300,
            "b14_scene_count": 3,
            "b14_scene_count_selected": True,
            "b14_storyboard_plan": {
                "preview_text": "Storyboard sản phẩm",
                "scene_cards": [
                    {"scene_index": 1, "provider_prompt": "Luxury perfume hero shot"},
                    {"scene_index": 2, "provider_prompt": "Close-up product detail"},
                    {"scene_index": 3, "provider_prompt": "TikTok call to action"},
                ],
            },
            "b14_addon_plan": addon_plan or bot.video_b14_default_addon_plan("product_review"),
        },
    }


def _confirmed_product_payload(monkeypatch, tmp_path, uid, *, addon_plan=None):
    _setup_bot_db(monkeypatch, tmp_path)
    session = _product_session(addon_plan=addon_plan)
    bot.save_video_session(uid, session)
    project = bot.video_b14_prepare_project_for_invoice(uid, session)
    result = bot.confirm_video_project_invoice(int(project["project_id"]), uid, balance_xu=None, use_wallet=False)
    assert result["ok"] is True
    conn = bot.db_connect()
    try:
        hydrated = queue.hydrate_video_job_payload(conn, result["job"])
        payload = remote_worker_api.build_worker_job_payload(hydrated)
        project = queue.get_video_project(conn, int(project["project_id"]))
        job = queue.get_video_render_job(conn, int(result["job"]["id"]))
        return conn, project, job, payload
    except Exception:
        conn.close()
        raise


def _conn(tmp_path):
    conn = sqlite3.connect(tmp_path / "p0_18d2_worker.db")
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _seed_worker_product(conn, *, user_id=PUBLIC_UID, admin=False):
    asset_pack = {
        "source": "product_video",
        "render_mode": "real",
        "test_pattern": False,
        "admin_video_delivery": False,
        "provider_call": True,
        "public_user": not admin,
        "admin_only": bool(admin),
        "no_charge": bool(admin),
        "original_user_prompt": "video sản phẩm thật",
    }
    project = queue.create_video_project(
        conn,
        user_id=user_id,
        profile_id="product_review",
        topic="Product route",
        ratio="9:16",
        asset_pack=asset_pack,
    )
    project = queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="queued_for_worker",
        is_confirmed=1,
        confirmed_at=queue.now_text(),
        invoice_json={**asset_pack, "total_xu": 0 if admin else 900},
        total_xu_estimated=0 if admin else 900,
        scene_count=3,
    )
    job = queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=user_id)
    queue.update_video_project(conn, int(project["project_id"]), job_id=int(job["id"]))
    return project, job


def test_admin_product_video_job_is_not_admin_video_delivery(monkeypatch, tmp_path):
    conn, project, job, payload = _confirmed_product_payload(monkeypatch, tmp_path, ADMIN_UID)
    try:
        assert payload["source"] == "product_video"
        assert payload["admin_video_delivery"] is False
        assert remote_worker_api.is_remote_worker_admin_video_job(job, project) is False
        assert payload["admin_only"] is True
        assert payload["no_charge"] is True
        assert payload["provider_call"] is True
        assert payload["public_user"] is False
    finally:
        conn.close()


def test_admin_product_video_job_render_mode_real(monkeypatch, tmp_path):
    conn, _project, _job, payload = _confirmed_product_payload(monkeypatch, tmp_path, ADMIN_UID)
    try:
        assert payload["render_mode"] == "real"
        assert payload["test_pattern"] is False
    finally:
        conn.close()


def test_public_product_video_job_render_mode_real(monkeypatch, tmp_path):
    conn, _project, _job, payload = _confirmed_product_payload(monkeypatch, tmp_path, PUBLIC_UID)
    try:
        assert payload["source"] == "product_video"
        assert payload["render_mode"] == "real"
        assert payload["test_pattern"] is False
        assert payload["admin_video_delivery"] is False
        assert payload["provider_call"] is True
        assert payload["public_user"] is True
    finally:
        conn.close()


def test_tool_test_video_delivery_worker_is_only_test_pattern_route(tmp_path):
    conn = _conn(tmp_path)
    try:
        created = remote_worker_api.create_admin_video_delivery_test_job(conn, admin_user_id=ADMIN_UID)
        claim = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-admin-video",
            capabilities=["admin_video", "ffmpeg"],
            admin_video_only=True,
        )
        assert created["ok"] is True
        assert claim["job"]["source"] == remote_worker_api.REMOTE_WORKER_ADMIN_VIDEO_SOURCE
        assert claim["job"]["admin_video_delivery"] is True
        assert claim["job"]["render_mode"] == "admin_test_pattern"
        assert claim["job"]["test_pattern"] is True
        assert claim["job"]["provider_call"] is False
    finally:
        conn.close()


def test_product_video_does_not_call_create_admin_video_delivery_test_job(monkeypatch, tmp_path):
    monkeypatch.setattr(
        remote_worker_api,
        "create_admin_video_delivery_test_job",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("product flow must not create admin delivery test job")),
    )
    conn, _project, _job, payload = _confirmed_product_payload(monkeypatch, tmp_path, ADMIN_UID)
    try:
        assert payload["source"] == "product_video"
    finally:
        conn.close()


@pytest.mark.parametrize(
    "result,reason",
    [
        ({"ok": True, "render_mode": "admin_test_pattern", "test_pattern": True}, "test_pattern_not_allowed_for_normal_video"),
        ({"ok": True, "render_mode": "real", "renderer": "remote_worker_fake_admin_test"}, "test_pattern_not_allowed_for_normal_video"),
        ({"ok": True, "render_mode": "real", "admin_video_delivery": True}, "admin_video_delivery_not_allowed_for_product_video"),
    ],
)
def test_product_delivery_rejects_test_or_admin_metadata(tmp_path, result, reason):
    conn = _conn(tmp_path)
    try:
        _seed_worker_product(conn)
        raw_claim = remote_worker_api.claim_remote_worker_render_job(conn, worker_id="vps-1", public_enabled=True)
        output = tmp_path / "bad.mp4"
        output.write_bytes(b"mp4")
        completed = remote_worker_api.complete_remote_worker_job(
            conn,
            worker_id="vps-1",
            job_id=int(raw_claim["id"]),
            result=result,
            final_video_path=str(output),
            uploaded_file=True,
        )
        assert completed["ok"] is False
        assert completed["reason"] == reason
        job = queue.get_video_render_job(conn, int(raw_claim["id"]))
        project = queue.get_video_project(conn, int(raw_claim["project_id"]))
        assert job["status"] == "failed"
        assert project["status"] == "failed"
    finally:
        conn.close()


def test_product_status_does_not_send_test_pattern_mp4(monkeypatch):
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: {})
    session = {
        "draft": {
            "b14_queue_job": {
                "id": 1,
                "status": "completed",
                "final_video_path": "test.mp4",
                "result_json": json.dumps({"render_mode": "admin_test_pattern", "test_pattern": True, "renderer": "testsrc"}),
            },
            "b14_invoice": {"scene_count": 3},
        }
    }
    text = bot.video_b14_queue_status_text(session, None, ADMIN_UID, "vi")
    assert bot.VIDEO_B14_PRODUCT_CLEAN_FAIL_MESSAGE in text
    for forbidden in ("OWNER/ADMIN TEST MODE", "ADMIN TEST MODE", "TEST PATTERN", "test pattern", "renderer", "provider", "worker"):
        assert forbidden.lower() not in text.lower()


def test_product_video_status_no_owner_admin_test_mode(monkeypatch):
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: {})
    monkeypatch.setattr(bot, "now_text", lambda *_args, **_kwargs: "2026-06-28 10:00:00")
    session = {"draft": {"b14_queue_job": {"id": 12, "status": "queued"}, "b14_invoice": {"scene_count": 3}}}
    admin_text = bot.video_b14_queue_status_text(session, None, ADMIN_UID, "vi")
    public_text = bot.video_b14_queue_status_text(session, None, PUBLIC_UID, "vi")
    assert admin_text == public_text
    for forbidden in ("OWNER/ADMIN TEST MODE", "ADMIN TEST MODE", "TEST PATTERN", "không trừ Xu", "provider", "worker", "render_mode"):
        assert forbidden.lower() not in admin_text.lower()


def test_product_result_no_renderer_provider_worker_words(monkeypatch):
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: {})
    session = {
        "draft": {
            "b14_queue_job": {"id": 9, "status": "completed", "final_video_path": "final.mp4", "result_json": json.dumps({"render_mode": "real", "renderer": "remote_worker_real_render_route"})},
            "b14_invoice": {"scene_count": 3},
        }
    }
    text = bot.video_b14_queue_status_text(session, None, ADMIN_UID, "vi")
    assert "hệ thống đã dựng video thật" in text
    for forbidden in ("renderer", "provider", "worker", "render_mode"):
        assert forbidden not in text.lower()


def test_product_real_mode_calls_video_real_render_connector(monkeypatch, tmp_path):
    output = tmp_path / "real.mp4"
    calls = {"real": 0}
    monkeypatch.setattr(remote_worker, "send_heartbeat", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(remote_worker, "render_fake_video", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("fake renderer must not run")))
    monkeypatch.setattr(remote_worker, "render_admin_video_delivery", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("admin video delivery must not run")))

    def fake_real(_job, _work_dir):
        calls["real"] += 1
        output.write_bytes(b"real-video")
        return str(output)

    completed = {}
    monkeypatch.setattr(remote_worker, "render_real_video", fake_real)
    monkeypatch.setattr(remote_worker, "complete_job", lambda _job_id, result, _path: completed.update(result) or {"ok": True})
    remote_worker.process_claimed_job({"job_id": "44", "job_type": "video_render", "source": "product_video", "render_mode": "real", "admin_video_delivery": False})
    assert calls["real"] == 1
    assert completed["render_mode"] == "real"
    assert completed.get("test_pattern") is not True


def test_real_provider_config_missing_fails_clean_no_fake(monkeypatch):
    monkeypatch.setattr(remote_worker, "send_heartbeat", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(remote_worker, "render_fake_video", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("fake renderer must not run")))
    monkeypatch.setattr(remote_worker, "render_admin_video_delivery", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("admin video delivery must not run")))
    monkeypatch.setattr(remote_worker, "render_real_video", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(remote_worker.REAL_VIDEO_RENDER_UNAVAILABLE)))
    with pytest.raises(RuntimeError, match=remote_worker.REAL_VIDEO_RENDER_UNAVAILABLE):
        remote_worker.process_claimed_job({"job_id": "45", "job_type": "video_render", "source": "product_video", "render_mode": "real"})


def test_real_provider_download_mp4_bytes_required(monkeypatch, tmp_path):
    import services.video_real_render_connector as connector

    monkeypatch.setattr(connector, "render_real_video_job", lambda _job, _work_dir: {"final_video_path": str(tmp_path / "missing.mp4")})
    with pytest.raises(RuntimeError, match=remote_worker.REAL_VIDEO_RENDER_UNAVAILABLE):
        remote_worker.render_real_video({"job_id": "46"}, str(tmp_path))


def test_product_job_payload_preserves_original_prompt_and_addon_plan(monkeypatch, tmp_path):
    plan = bot.video_b14_default_addon_plan("product_review")
    plan.update({
        "logo_enabled": True,
        "logo_source": "text",
        "logo_text": "TOAN AAS",
        "logo_position": "top_center",
        "music_enabled": True,
        "music_source": "default",
        "music_volume_percent": 12,
    })
    conn, _project, _job, payload = _confirmed_product_payload(monkeypatch, tmp_path, ADMIN_UID, addon_plan=plan)
    try:
        assert "nước hoa nam" in payload["original_user_prompt"]
        assert payload["addon_plan"]["music_volume_percent"] == 12
        assert payload["addon_plan"]["logo_enabled"] is True
        assert payload["addon_plan"]["logo_source"] == "text"
        assert payload["addon_plan"]["logo_text"] == "TOAN AAS"
        assert payload["addon_plan"]["logo_position"] == "top_center"
    finally:
        conn.close()


def test_logo_text_default_off(monkeypatch, tmp_path):
    conn, _project, _job, payload = _confirmed_product_payload(monkeypatch, tmp_path, PUBLIC_UID)
    try:
        assert payload["addon_plan"]["logo_enabled"] is False
        assert payload["addon_plan"]["logo_source"] == "none"
    finally:
        conn.close()


def test_bot_delivery_rejects_product_fake_metadata(monkeypatch, tmp_path):
    _setup_bot_db(monkeypatch, tmp_path)
    conn = bot.db_connect()
    try:
        _project, _job = _seed_worker_product(conn, user_id=PUBLIC_UID)
        raw_claim = remote_worker_api.claim_remote_worker_render_job(conn, worker_id="vps-1", public_enabled=True)
        output = tmp_path / "bad.mp4"
        output.write_bytes(b"bad-mp4")
        completed = queue.complete_video_job(
            conn,
            job_id=int(raw_claim["id"]),
            final_video_path=str(output),
            result={"ok": True, "render_mode": "real", "renderer": "testsrc_fake"},
        )
    finally:
        conn.close()

    sent = []

    class FakeBot:
        async def send_video(self, **_kwargs):
            raise AssertionError("product fake MP4 must not be sent")

        async def send_message(self, **kwargs):
            sent.append(kwargs)

    monkeypatch.setattr(bot, "tg_app", SimpleNamespace(bot=FakeBot()))
    delivery = asyncio.run(bot.maybe_send_remote_worker_final_video(completed))
    assert delivery["sent"] is False
    assert delivery["message_sent"] is True
    assert sent and bot.VIDEO_B14_PRODUCT_CLEAN_FAIL_MESSAGE in sent[0]["text"]
