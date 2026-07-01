import inspect
import json
import os
import sqlite3
from pathlib import Path

import pytest

import bot
import remote_worker
from services import remote_worker_api
from services import video_project_queue as queue


def _conn(tmp_path):
    conn = sqlite3.connect(tmp_path / "p0_18d1_video_render.db")
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _admin_video_job(render_mode="real"):
    return {
        "job_id": "88",
        "job_type": "video_render",
        "admin_video_delivery": True,
        "admin_only": True,
        "no_charge": True,
        "provider_call": False,
        "public_user": False,
        "source": remote_worker.REMOTE_WORKER_ADMIN_VIDEO_SOURCE,
        "render_mode": render_mode,
    }


def _seed_video_job(conn, *, admin=False, render_mode="real", user_id=777):
    flags = {
        "render_mode": render_mode,
        "test_pattern": render_mode == "admin_test_pattern",
        "fake_renderer_allowed": False,
        "real_renderer_required": render_mode == "real",
        "admin_only": bool(admin),
        "no_charge": bool(admin),
        "provider_call": False,
        "public_user": not admin,
    }
    if admin:
        flags["admin_video_delivery"] = True
    project = queue.create_video_project(
        conn,
        user_id=user_id,
        profile_id="admin_video" if admin else "public_video",
        topic="Real render metadata test",
        ratio="9:16",
        asset_pack=flags,
    )
    project = queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="queued_for_worker",
        is_confirmed=1,
        confirmed_at=queue.now_text(),
        invoice_json={**flags, "total_xu": 0 if admin else 900},
        total_xu_estimated=0 if admin else 900,
        scene_count=3,
    )
    job = queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=user_id)
    queue.update_video_project(conn, int(project["project_id"]), job_id=int(job["id"]))
    return project, job


def test_video_logo_default_off():
    plan = bot.video_b14_addon_plan_from_session({"draft": {}})
    assert plan["logo_enabled"] is False
    assert plan["logo_source"] == "none"
    assert plan["logo_position"] == "bottom_right"


def test_watermark_not_auto_enabled():
    session = {"draft": {"b14_addon_plan": bot.video_b14_default_addon_plan("storytelling")}}
    text = bot.video_b14_addon_text(session, "vi")
    assert "Logo: <b>Tắt</b> · không dùng" in text
    assert "Watermark TOAN AAS mặc định" not in text


def test_legacy_uploaded_logo_plan_is_not_shown_in_text_addon():
    session = {
        "draft": {
            "b14_addon_plan": {
                **bot.video_b14_default_addon_plan("storytelling"),
                "logo_enabled": True,
                "logo_source": "uploaded",
                "logo_file_id": "old-file-id",
            }
        }
    }
    plan = bot.video_b14_addon_plan_from_session(session)
    text = bot.video_b14_addon_text(session, "vi")
    assert plan["logo_enabled"] is False
    assert plan["logo_source"] == "none"
    assert plan["logo_file_id"] == ""
    assert "logo đã gửi" not in text.lower()


def test_watermark_enables_only_after_text_confirm():
    plan = bot.video_b14_default_addon_plan("storytelling")
    session = {"draft": {"b14_addon_plan": {**plan, "logo_enabled": True, "logo_source": "text", "logo_text": "TOAN AAS"}}}
    text = bot.video_b14_addon_text(session, "vi")
    assert "Logo: <b>Bật</b> · chữ logo/watermark · TOAN AAS · góc phải dưới" in text


def test_invoice_logo_default_off(monkeypatch):
    monkeypatch.setattr(bot, "get_user", lambda _uid: (9999, None, None))
    session = {"topic": "video test", "draft": {"b14_quality_xu": 300, "b14_scene_count": 3, "b14_addon_plan": bot.video_b14_default_addon_plan("storytelling")}}
    text = bot.video_b14_invoice_text(session, 123, "vi")
    assert "• Logo: Tắt" in text
    assert "Watermark TOAN AAS mặc định" not in text


def test_status_logo_default_off(monkeypatch):
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: {})
    session = {"draft": {"b14_queue_job": {"id": 1, "status": "queued"}, "b14_invoice": {"scene_count": 3}, "b14_addon_plan": bot.video_b14_default_addon_plan("storytelling")}}
    text = bot.video_b14_queue_status_text(session, None, 123, "vi")
    assert "Hậu kỳ:" in text
    assert "logo" not in text.lower()
    assert "Logo:" not in text
    assert "Watermark TOAN AAS mặc định" not in text


def test_logo_addon_is_text_flow_not_default_or_image_buttons():
    callbacks = [button.callback_data for row in bot.video_b14_logo_keyboard("vi").inline_keyboard for button in row if button.callback_data]
    labels = [button.text for row in bot.video_b14_logo_keyboard("vi").inline_keyboard for button in row]
    assert "vproduct|b14_logo_text_start" in callbacks
    assert "vproduct|b14_logo_source|default_watermark" not in callbacks
    assert "vproduct|b14_logo_source|uploaded" not in callbacks
    assert "vproduct|b14_logo_upload" not in callbacks
    assert any("Nhập chữ" in label for label in labels)


def test_logo_position_has_six_points():
    callbacks = [button.callback_data for row in bot.video_b14_logo_position_keyboard("vi").inline_keyboard for button in row if button.callback_data]
    for pos in ("top_left", "top_center", "top_right", "bottom_left", "bottom_center", "bottom_right"):
        assert f"vproduct|b14_logo_position|{pos}" in callbacks


def test_fake_renderer_only_allowed_for_tool_test(monkeypatch, tmp_path):
    monkeypatch.setattr(remote_worker, "send_heartbeat", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(remote_worker, "render_real_video", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(remote_worker.REAL_VIDEO_RENDER_UNAVAILABLE)))
    monkeypatch.setattr(remote_worker, "render_admin_video_delivery", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("fake renderer used outside test pattern")))
    with pytest.raises(RuntimeError, match=remote_worker.REAL_VIDEO_RENDER_UNAVAILABLE):
        remote_worker.process_admin_video_job(_admin_video_job("real"))

    output = tmp_path / "test-pattern.mp4"

    def fake_test_pattern(_job, _work_dir):
        output.write_bytes(b"test-pattern")
        return str(output)

    completed = {}
    monkeypatch.setattr(remote_worker, "render_admin_video_delivery", fake_test_pattern)
    monkeypatch.setattr(remote_worker, "complete_job", lambda _job_id, result, _path: completed.update(result) or {"ok": True})
    remote_worker.process_admin_video_job(_admin_video_job("admin_test_pattern"))
    assert completed["render_mode"] == "admin_test_pattern"
    assert completed["test_pattern"] is True


def test_normal_video_flow_does_not_use_test_pattern(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "bot.db"))
    bot.init_db()
    uid = 180181
    session = {
        "product_id": "multi_scene_film",
        "topic": "video quảng cáo sản phẩm",
        "draft": {
            "b14_profile_id": "product_review",
            "b14_quality_xu": 300,
            "b14_scene_count": 3,
            "b14_scene_count_selected": True,
            "b14_storyboard_plan": {"preview_text": "storyboard", "scene_cards": [{"scene_index": 1, "provider_prompt": "real scene"}]},
            "b14_addon_plan": bot.video_b14_default_addon_plan("product_review"),
        },
    }
    bot.save_video_session(uid, session)
    bot.video_b14_prepare_project_for_invoice(uid, session)
    draft = bot.get_video_session(uid)["draft"]
    assert draft["asset_pack"]["render_mode"] == "real"
    assert draft["asset_pack"]["test_pattern"] is False
    assert draft["asset_pack"]["admin_video_delivery"] is False
    assert draft["asset_pack"]["fake_renderer_allowed"] is False


def test_admin_normal_video_no_fake_success(monkeypatch):
    monkeypatch.setattr(remote_worker, "send_heartbeat", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(remote_worker, "render_admin_video_delivery", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("test pattern must not run")))
    monkeypatch.setattr(remote_worker, "render_real_video", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(remote_worker.REAL_VIDEO_RENDER_UNAVAILABLE)))
    with pytest.raises(RuntimeError, match=remote_worker.REAL_VIDEO_RENDER_UNAVAILABLE):
        remote_worker.process_admin_video_job(_admin_video_job("real"))


def test_public_video_no_fake_success(tmp_path):
    conn = _conn(tmp_path)
    _project, _job = _seed_video_job(conn, admin=False, render_mode="real", user_id=991)
    raw_claim = remote_worker_api.claim_remote_worker_render_job(conn, worker_id="vps-1", public_enabled=True)
    claim = remote_worker_api.build_worker_job_payload(queue.hydrate_video_job_payload(conn, raw_claim))
    output = tmp_path / "fake.mp4"
    output.write_bytes(b"fake")
    completed = remote_worker_api.complete_remote_worker_job(
        conn,
        worker_id="vps-1",
        job_id=int(claim["job_id"]),
        result={"ok": True, "render_mode": "admin_test_pattern", "test_pattern": True, "renderer": "testsrc_fake"},
        final_video_path=str(output),
        uploaded_file=True,
    )
    assert completed["ok"] is False
    assert completed["reason"] == "test_pattern_not_allowed_for_normal_video"


def test_missing_real_renderer_fails_no_charge(monkeypatch):
    failures = []
    monkeypatch.setattr(remote_worker, "claim_job", lambda **_kwargs: _admin_video_job("real"))
    monkeypatch.setattr(remote_worker, "send_heartbeat", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(remote_worker, "render_real_video", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(remote_worker.REAL_VIDEO_RENDER_UNAVAILABLE)))
    monkeypatch.setattr(remote_worker, "render_admin_video_delivery", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("test pattern must not run")))
    monkeypatch.setattr(remote_worker, "fail_job", lambda job_id, safe_error, retryable=True, partial_artifacts=None: failures.append((job_id, safe_error, retryable)) or {"ok": True})
    assert remote_worker.run_once(admin_video_only=True) == "failed"
    assert failures and failures[0][2] is False
    assert remote_worker.REAL_VIDEO_RENDER_UNAVAILABLE in failures[0][1]


def test_admin_video_worker_prefers_real_render(monkeypatch, tmp_path):
    monkeypatch.setattr(remote_worker, "send_heartbeat", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(remote_worker, "render_admin_video_delivery", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("test pattern must not run")))
    output = tmp_path / "real.mp4"

    def fake_real(_job, _work_dir):
        output.write_bytes(b"real-video")
        return str(output)

    completed = {}
    monkeypatch.setattr(remote_worker, "render_real_video", fake_real)
    monkeypatch.setattr(remote_worker, "complete_job", lambda _job_id, result, _path: completed.update(result) or {"ok": True})
    remote_worker.process_admin_video_job(_admin_video_job("real"))
    assert completed["render_mode"] == "real"
    assert completed["test_pattern"] is False


def test_admin_video_worker_marks_unavailable_without_fake(monkeypatch):
    monkeypatch.setattr(remote_worker, "send_heartbeat", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(remote_worker, "render_admin_video_delivery", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("test pattern must not run")))
    monkeypatch.setattr(remote_worker, "render_real_video", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(remote_worker.REAL_VIDEO_RENDER_UNAVAILABLE)))
    with pytest.raises(RuntimeError, match=remote_worker.REAL_VIDEO_RENDER_UNAVAILABLE):
        remote_worker.process_admin_video_job(_admin_video_job("real"))


def test_video_status_shows_real_render_mode_internal_only(monkeypatch):
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: {})
    session = {
        "draft": {
            "b14_queue_job": {"id": 1, "status": "completed", "final_video_path": "final.mp4", "result_json": json.dumps({"render_mode": "real"})},
            "b14_invoice": {"scene_count": 3},
        }
    }
    text = bot.video_b14_queue_status_text(session, None, bot.ADMIN_ID, "vi")
    assert "✅ Video đã sẵn sàng." in text
    assert "render_mode" not in text


def test_completed_video_not_test_pattern_for_normal_flow(tmp_path):
    conn = _conn(tmp_path)
    _project, _job = _seed_video_job(conn, admin=False, render_mode="real", user_id=992)
    raw_claim = remote_worker_api.claim_remote_worker_render_job(conn, worker_id="vps-1", public_enabled=True)
    claim = remote_worker_api.build_worker_job_payload(queue.hydrate_video_job_payload(conn, raw_claim))
    output = tmp_path / "testsrc.mp4"
    output.write_bytes(b"mp4")
    result = remote_worker_api.complete_remote_worker_job(
        conn,
        worker_id="vps-1",
        job_id=int(claim["job_id"]),
        result={"ok": True, "render_mode": "admin_test_pattern", "renderer": "remote_worker_fake_admin_test"},
        final_video_path=str(output),
        uploaded_file=True,
    )
    assert result["ok"] is False


def test_delivery_worker_tool_labels_test_pattern():
    source = inspect.getsource(bot.cmd_tool_test_video_delivery_worker)
    assert "ADMIN TEST PATTERN" in source
    assert "không phải video dựng thật" in source


def test_delivery_worker_tool_not_counted_live_pass():
    source = inspect.getsource(bot.cmd_tool_test_video_delivery_worker)
    assert "không tính là LIVE PASS video thật" in source


def test_status_does_not_call_test_pattern_real_video(monkeypatch):
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: {})
    session = {
        "draft": {
            "b14_queue_job": {"id": 1, "status": "completed", "final_video_path": "test.mp4", "result_json": json.dumps({"render_mode": "admin_test_pattern", "test_pattern": True})},
            "b14_invoice": {"scene_count": 3},
        }
    }
    text = bot.video_b14_queue_status_text(session, None, bot.ADMIN_ID, "vi")
    assert bot.VIDEO_B14_PRODUCT_CLEAN_FAIL_MESSAGE in text
    assert "video test kỹ thuật" not in text
    assert "không phải video dựng thật" not in text
    assert "hệ thống đã dựng video thật" not in text


def test_status_completed_requires_real_render_or_test_label(monkeypatch):
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: {})
    session = {
        "draft": {
            "b14_queue_job": {"id": 1, "status": "completed", "final_video_path": "unknown.mp4"},
            "b14_invoice": {"scene_count": 3},
        }
    }
    text = bot.video_b14_queue_status_text(session, None, bot.ADMIN_ID, "vi")
    assert "hệ thống đã dựng video thật" not in text
    assert "renderer" not in text.lower()
    assert "✅ Video đã sẵn sàng." in text
