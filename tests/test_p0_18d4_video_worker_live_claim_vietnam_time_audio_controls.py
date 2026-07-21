import inspect
import sqlite3
from datetime import datetime, timedelta

import bot
from services import remote_worker_api
from services import video_project_queue as queue


ADMIN_UID = int(bot.ADMIN_ID)
PUBLIC_UID = 918403


def _conn(tmp_path):
    conn = sqlite3.connect(tmp_path / "p0_18d4_video_worker.db")
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
        "original_user_prompt": "video product worker live claim",
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


def test_owner_product_worker_claims_admin_product_video_when_public_worker_off(monkeypatch, tmp_path):
    conn = _conn(tmp_path)
    try:
        monkeypatch.delenv(remote_worker_api.REMOTE_WORKER_PUBLIC_ENABLED_ENV, raising=False)
        _project, job = _seed_product_video_job(conn, admin=True)
        claim = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-toanaas-01",
            capabilities=["owner_product_video", "product_video", "ffmpeg"],
            owner_product_video_only=True,
        )
        assert claim["ok"] is True
        assert claim["job"]["job_id"] == str(job["id"])
        assert claim["job"]["source"] == "product_video"
        assert claim["job"]["render_mode"] == "real"
        assert claim["job"]["test_pattern"] is False
        assert claim["job"]["admin_video_delivery"] is False
        assert claim["job"]["admin_only"] is True
        assert claim["job"]["no_charge"] is True
    finally:
        conn.close()


def test_public_product_worker_respects_public_worker_gate(monkeypatch, tmp_path):
    conn = _conn(tmp_path)
    try:
        _project, first_job = _seed_product_video_job(conn, user_id=PUBLIC_UID, admin=False)
        monkeypatch.delenv(remote_worker_api.REMOTE_WORKER_PUBLIC_ENABLED_ENV, raising=False)
        disabled = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-public-product",
            capabilities=["product_video", "ffmpeg"],
            product_video_only=True,
        )
        assert disabled["job"] is None
        assert disabled["reason"] == "public_product_worker_disabled_or_no_owner_job"
        queue.fail_video_job(conn, job_id=int(first_job["id"]), error="test_done", retry=False)
        _project, second_job = _seed_product_video_job(conn, user_id=PUBLIC_UID, admin=False)
        monkeypatch.setenv(remote_worker_api.REMOTE_WORKER_PUBLIC_ENABLED_ENV, "true")
        enabled = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-public-product",
            capabilities=["product_video", "ffmpeg"],
            product_video_only=True,
        )
        assert enabled["job"]["job_id"] == str(second_job["id"])
        assert enabled["job"]["public_user"] is True
        assert enabled["job"]["no_charge"] is False
    finally:
        conn.close()


def test_admin_video_worker_does_not_claim_product_video(tmp_path):
    conn = _conn(tmp_path)
    try:
        _project, job = _seed_product_video_job(conn, admin=True)
        claim = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-admin-video",
            capabilities=["admin_video", "ffmpeg"],
            admin_video_only=True,
        )
        assert claim["job"] is None
        assert claim["reason"] == "no_admin_video_job"
        assert queue.get_video_render_job(conn, int(job["id"]))["status"] == "queued"
    finally:
        conn.close()


def test_admin_canary_worker_claims_rw_prod_canary(tmp_path):
    conn = _conn(tmp_path)
    try:
        created = remote_worker_api.create_remote_worker_admin_canary_job(conn, admin_user_id=ADMIN_UID)
        claim = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-toanaas-01",
            capabilities=["admin_canary", "ffmpeg"],
            admin_canary_only=True,
        )
        assert claim["ok"] is True
        assert claim["job"]["job_id"] == str(created["job"]["id"])
        assert claim["job"]["asset_pack"]["worker_admin_canary"] is True
    finally:
        conn.close()


def test_remote_worker_prod_canary_status_shows_claimed_worker(tmp_path):
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
        assert status["ok"] is True
        assert status["worker_id"] == "vps-toanaas-01"
        assert status["canary_ref"].startswith("RW-PROD-CANARY-")
    finally:
        conn.close()


def test_tool_test_video_product_worker_claim_no_generic_error():
    source = inspect.getsource(bot.cmd_tool_test_video_product_worker_claim)
    assert "Có lỗi khi xử lý lệnh" not in source
    assert "diagnostic_product_worker_claim_only_no_render" not in source
    assert "toanaas-worker-owner-product-video" in source
    assert "Đã tạo job kiểm tra claim product_video" in source


def test_product_video_queue_not_stuck_when_worker_missing(tmp_path):
    conn = _conn(tmp_path)
    try:
        _project, job = _seed_product_video_job(conn, admin=True)
        old = queue.now_text(datetime.now() - timedelta(hours=2))
        conn.execute("UPDATE video_jobs SET created_at=?, updated_at=? WHERE id=?", (old, old, int(job["id"])))
        conn.commit()
        failed = remote_worker_api.fail_stale_product_video_jobs(conn, max_wait_seconds=60, now=datetime.now(), job_id=int(job["id"]))
        row = queue.get_video_render_job(conn, int(job["id"]))
        assert failed == 1
        assert row["status"] == "failed"
        assert row["progress_message"] != "hệ thống đang xếp lịch dựng video"
    finally:
        conn.close()


def test_product_video_stale_timeout_clean_no_charge(tmp_path):
    conn = _conn(tmp_path)
    try:
        _project, job = _seed_product_video_job(conn, admin=True)
        old = queue.now_text(datetime.now() - timedelta(hours=2))
        conn.execute("UPDATE video_jobs SET created_at=?, updated_at=? WHERE id=?", (old, old, int(job["id"])))
        conn.commit()
        assert remote_worker_api.fail_stale_product_video_jobs(conn, max_wait_seconds=60, now=datetime.now(), job_id=int(job["id"])) == 1
        row = queue.get_video_render_job(conn, int(job["id"]))
        project = queue.get_video_project(conn, int(row["project_id"]))
        assert project["status"] == "failed"
        assert int(project["total_xu_estimated"] or 0) == 0
        assert "product_video_worker_unavailable" in str(row["last_error"])
        assert "chưa trừ Xu" in bot.VIDEO_B14_PRODUCT_CLEAN_FAIL_MESSAGE
    finally:
        conn.close()


def test_video_worker_status_shows_vietnam_time():
    text = bot.video_worker_status_text(
        {
            "worker_api_enabled": True,
            "last_remote_worker_heartbeat": "2026-06-28 07:27:16",
            "last_worker_id": "vps-toanaas-01",
            "public_worker_enabled": False,
        },
        {
            "queued": 1,
            "active": 0,
            "last": {"job_id": 17, "status": "queued", "updated_at": "2026-06-28 07:24:42"},
        },
        {"ok": True, "providers": [{"provider": "shopaikey", "configured": True}]},
    )
    assert "2026-06-28 14:27:16" in text
    assert "2026-06-28 14:24:42" in text
    assert "2026-06-28 07:27:16" not in text


def test_video_status_last_update_shows_vietnam_time(monkeypatch):
    monkeypatch.setattr(bot, "video_b14_fail_stale_product_job_for_status", lambda _job_id: 0)
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: {})
    session = {
        "draft": {
            "b14_queue_job": {"id": 17, "status": "queued", "updated_at": "2026-06-28 07:27:16"},
            "b14_invoice": {"scene_count": 3, "duration_seconds": 18},
        }
    }
    text = bot.video_b14_queue_status_text(session, None, ADMIN_UID, "vi")
    assert "<b>Tiến trình:</b>" in text
    assert "Cập nhật lần cuối" not in text
    assert "2026-06-28 07:27:16" not in text


def test_video_voice_speed_accepts_0_1_to_2_0():
    assert bot.parse_video_audio_speed("0.1") == (True, 0.1, "")
    assert bot.parse_video_audio_speed("2.0") == (True, 2.0, "")


def test_video_voice_speed_accepts_vietnamese_comma():
    assert bot.parse_video_audio_speed("1,2") == (True, 1.2, "")


def test_video_voice_speed_rejects_invalid_clean():
    ok, _value, message = bot.parse_video_audio_speed("2.5")
    assert ok is False
    assert message == bot.VIDEO_AUDIO_SPEED_ERROR_VI


def test_video_voice_volume_accepts_0_to_200_percent():
    assert bot.parse_video_audio_volume_percent("0") == (True, 0, "")
    assert bot.parse_video_audio_volume_percent("80%") == (True, 80, "")
    assert bot.parse_video_audio_volume_percent("200%") == (True, 200, "")
    assert bot.parse_video_audio_volume_percent("1.5")[0] is False


def test_video_voice_volume_zero_requires_confirm():
    ok, value, _message = bot.parse_video_audio_volume_percent("0%")
    keyboard = bot.video_audio_volume_zero_confirm_keyboard("voice", "vi")
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert ok is True and value == 0
    assert bot.VIDEO_AUDIO_VOLUME_ZERO_CONFIRM_VI.startswith("Âm lượng 0%")
    assert "vfinal|voice_volume_zero_confirm" in callbacks
    assert "vfinal|voice_volume_retry" in callbacks
    assert "✅ Vẫn tiếp tục" in labels
    assert "✏️ Nhập lại âm lượng" in labels


def test_video_music_speed_accepts_0_1_to_2_0():
    assert bot.parse_video_audio_speed("0.1")[1] == 0.1
    assert bot.parse_video_audio_speed("2")[1] == 2.0


def test_video_music_volume_preserves_existing_default_10_percent():
    settings = bot.video_audio_settings_from_state({})
    assert settings["video_music_volume_percent"] == 10
    assert settings["music_volume_percent"] == 10


def test_video_music_volume_accepts_custom_percent():
    ok, value, _message = bot.parse_video_audio_volume_percent("30%")
    updated = bot.video_audio_set_control({}, "music", "volume", value)
    assert ok is True
    assert updated["video_music_volume_percent"] == 30
    assert updated["music_volume_percent"] == 30


def test_video_audio_controls_preserve_video_draft_state():
    state = {
        "source": "promptvideo",
        "selected_video_tier": "basic",
        "source_payload": {"prompt": "video quảng cáo nước hoa", "duration_seconds": 18},
        "video_finalization": {"voice_enabled": True, "music_enabled": True, "voice_choice": "default_male"},
        "current_video_voice_choice": "default_male",
        "current_video_music_choice": "stock",
    }
    updated = bot.video_audio_set_control(state, "voice", "speed", 1.2)
    updated = bot.video_audio_set_control(updated, "music", "volume", 30)
    assert updated["source"] == "promptvideo"
    assert updated["selected_video_tier"] == "basic"
    assert updated["source_payload"]["prompt"] == "video quảng cáo nước hoa"
    assert updated["source_payload"]["duration_seconds"] == 18
    assert updated["current_video_voice_choice"] == "default_male"
    assert updated["current_video_music_choice"] == "stock"
    assert updated["video_voice_speed"] == 1.2
    assert updated["video_music_volume_percent"] == 30


def test_video_audio_controls_no_technical_words():
    state = {
        "video_finalization": {"voice_enabled": True, "music_enabled": True, "voice_choice": "default_male", "music_choice": "stock"},
    }
    text = "\n".join(
        [
            bot.video_finalization_voice_text(state, "vi"),
            bot.video_finalization_music_text(state, "vi"),
            bot.video_audio_input_text("voice", "speed", "vi"),
            bot.video_audio_input_text("music", "volume", "vi"),
            bot.VIDEO_AUDIO_VOLUME_ZERO_CONFIRM_VI,
            bot.video_audio_invoice_block(state, "vi"),
        ]
    ).lower()
    for forbidden in ("ffmpeg", "atempo", "volume_factor", "provider", "api", "debug"):
        assert forbidden not in text


def test_admin_video_audio_controls_same_clean_ui_as_user():
    admin_text = bot.video_finalization_voice_text({"user_id": ADMIN_UID}, "vi") + "\n" + bot.video_finalization_music_text({"user_id": ADMIN_UID}, "vi")
    user_text = bot.video_finalization_voice_text({"user_id": PUBLIC_UID}, "vi") + "\n" + bot.video_finalization_music_text({"user_id": PUBLIC_UID}, "vi")
    for text in (admin_text, user_text):
        lowered = text.lower()
        assert "tốc độ" in lowered
        assert "âm lượng" in lowered
        assert "owner/admin test mode" not in lowered
        assert "ffmpeg" not in lowered
        assert "provider" not in lowered
