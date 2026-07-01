import os
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path

import pytest

import bot
import remote_worker
from services import remote_worker_api
from services import video_final_output
from services import video_project_queue as queue
from services import video_real_render_connector as connector


ADMIN_UID = int(bot.ADMIN_ID)


def _conn(tmp_path):
    conn = sqlite3.connect(tmp_path / "p0_18g_video_mp4.db")
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _seed_product_job(conn, *, admin=True, scene_count=3, addon_plan=None, asset_overrides=None):
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
        "product_type": "script_to_video",
        "public_user": not admin,
        "admin_only": bool(admin),
        "created_by_admin": bool(admin),
        "no_charge": bool(admin),
        "admin_no_charge": bool(admin),
        "scene_count": scene_count,
        "duration_seconds": scene_count * 6,
        "original_user_prompt": "video giới thiệu sản phẩm thật, dựng thành MP4 cuối",
        "cleaned_user_prompt": "video giới thiệu sản phẩm thật, dựng thành MP4 cuối",
        "provider_order": "shopaikey,key4u",
    }
    asset_pack.update(dict(asset_overrides or {}))
    project = queue.create_video_project(
        conn,
        user_id=ADMIN_UID if admin else 918181,
        profile_id="product_review",
        topic=asset_pack["original_user_prompt"],
        ratio="9:16",
        asset_pack=asset_pack,
    )
    scene_cards = [
        {
            "scene_index": index,
            "title": f"Cảnh {index}",
            "narration_line": f"Cảnh {index} giới thiệu điểm nổi bật của sản phẩm.",
            "subtitle_line": f"Cảnh {index} giới thiệu điểm nổi bật.",
            "visual_goal": f"Cảnh {index} quay sản phẩm rõ, đẹp và liền mạch.",
            "provider_prompt": f"Scene {index}: polished product video shot, smooth motion, real MP4 output.",
        }
        for index in range(1, scene_count + 1)
    ]
    queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="queued_for_worker",
        is_confirmed=1,
        confirmed_at=queue.now_text(),
        invoice_json={**asset_pack, "total_xu": 0 if admin else 900},
        addon_plan_json=addon_plan or {},
        scene_cards_json=scene_cards,
        prompt_text=asset_pack["original_user_prompt"],
        total_xu_estimated=0 if admin else 900,
        scene_count=scene_count,
    )
    job = queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=ADMIN_UID if admin else 918181, max_attempts=1)
    queue.update_video_project(conn, int(project["project_id"]), job_id=int(job["id"]))
    return queue.get_video_project(conn, int(project["project_id"])), job


def _product_job_payload(conn, job):
    return remote_worker_api.build_worker_job_payload(queue.hydrate_video_job_payload(conn, job))


def _ffmpeg_required():
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg missing in test environment")


def _short_workspace(prefix: str) -> str:
    root = Path(".pytest_tmp")
    root.mkdir(exist_ok=True)
    return tempfile.mkdtemp(prefix=f"{prefix}_", dir=str(root))


def test_product_video_payload_required_fields_and_not_admin_test(tmp_path):
    conn = _conn(tmp_path)
    try:
        _project, job = _seed_product_job(conn, admin=True, scene_count=3)
        payload = _product_job_payload(conn, job)
        assert payload["source"] == "product_video"
        assert payload["render_mode"] == "real"
        assert payload["test_pattern"] is False
        assert payload["admin_video_delivery"] is False
        assert payload["product_video"] is True
        assert payload["provider_call"] is True
        assert payload["scene_count"] == 3
        assert payload["output_requirements"]["container"] == "mp4"
    finally:
        conn.close()


def test_worker_claims_product_job_and_does_not_skip_source(tmp_path):
    conn = _conn(tmp_path)
    try:
        _seed_product_job(conn, admin=True, scene_count=3)
        claim = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-owner-product",
            capabilities=["owner_product_video", "product_video", "ffmpeg"],
            owner_product_video_only=True,
        )
        assert claim["ok"] is True
        assert claim["job"]["source"] == "product_video"
        assert claim["job"]["product_video"] is True
        assert remote_worker.product_video_job_allowed(claim["job"]) is True
    finally:
        conn.close()


def test_render_creates_mp4_artifact_3_scenes_with_music_subtitle_logo(monkeypatch, tmp_path):
    _ffmpeg_required()
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_args, **_kwargs: {"ok": False, "ready_provider_order": [], "providers": []})
    job = {
        "job_id": "p0-18g-3-scenes",
        "user_id": str(ADMIN_UID),
        "source": "product_video",
        "render_mode": "real",
        "provider_call": True,
        "product_type": "script_to_video",
        "no_charge": True,
        "scene_count": 3,
        "expected_duration_seconds": 3,
        "aspect_ratio": "9:16",
        "original_user_prompt": "video quảng cáo sản phẩm cao cấp, có nhạc, phụ đề và logo",
        "addon_plan": {
            "music_enabled": True,
            "music_source": "default",
            "music_volume_percent": 30,
            "subtitle_enabled": True,
            "logo_enabled": True,
            "logo_source": "text",
            "logo_text": "TOAN AAS",
            "logo_position": "top_right",
        },
    }
    result = connector.render_real_video_job(job, _short_workspace("p018g3"))
    final_path = Path(result["final_video_path"])
    assert result["ok"] is True
    assert final_path.is_file()
    assert final_path.stat().st_size > 0
    assert result["scene_count"] == 3
    assert result["visual_classification"] == "final_ai_video"
    assert result["no_charge"] is True
    assert "test" not in str(result.get("renderer", "")).lower()
    assert "fake" not in str(result.get("renderer", "")).lower()


def test_artifact_exists_before_worker_success(monkeypatch, tmp_path):
    _ffmpeg_required()
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_args, **_kwargs: {"ok": False, "ready_provider_order": [], "providers": []})
    monkeypatch.setattr(remote_worker, "WORKER_TMP_DIR", _short_workspace("p018gw"))
    heartbeats = []
    completed = {}

    def fake_complete(job_id, result, final_video_path=""):
        assert os.path.isfile(final_video_path)
        assert os.path.getsize(final_video_path) > 0
        completed.update({"job_id": job_id, "result": result, "final_video_path": final_video_path})
        return {"ok": True, "job_id": job_id}

    monkeypatch.setattr(remote_worker, "send_heartbeat", lambda *args, **_kwargs: heartbeats.append(args))
    monkeypatch.setattr(remote_worker, "complete_job", fake_complete)
    job = {
        "job_id": "p0-18g-worker",
        "job_type": "video_render",
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "test_pattern": False,
        "admin_video_delivery": False,
        "provider_call": True,
        "product_type": "script_to_video",
        "public_user": False,
        "admin_only": True,
        "no_charge": True,
        "scene_count": 1,
        "expected_duration_seconds": 1,
        "original_user_prompt": "video sản phẩm một cảnh",
        "addon_plan": {"subtitle_enabled": True},
    }
    assert remote_worker.process_claimed_job(job)["ok"] is True
    assert completed["result"]["source"] == "product_video"
    assert completed["result"]["test_pattern"] is False
    assert completed["result"]["admin_video_delivery"] is False
    assert completed["result"]["visual_classification"] == "final_ai_video"
    assert completed["result"]["no_charge"] is True
    progress_points = {int(item[1]) for item in heartbeats if len(item) > 1}
    assert progress_points >= {5, 20, 80, 88, 90}
    assert 95 not in progress_points


def test_no_charge_before_artifact_product_complete_requires_mp4(tmp_path):
    conn = _conn(tmp_path)
    try:
        _project, job = _seed_product_job(conn, admin=True, scene_count=1)
        claim = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-owner-product",
            capabilities=["owner_product_video", "product_video", "ffmpeg"],
            owner_product_video_only=True,
        )
        missing = remote_worker_api.complete_remote_worker_job(
            conn,
            worker_id="vps-owner-product",
            job_id=int(claim["job"]["job_id"]),
            result={"ok": True, "render_mode": "real", "renderer": "remote_worker_real_render_route"},
            final_video_path="",
        )
        assert missing["ok"] is False
        assert missing["reason"] == "product_result_file_missing"
        row = queue.get_video_render_job(conn, int(job["id"]))
        assert row["status"] == "processing"
    finally:
        conn.close()


def test_no_fake_test_pattern_and_delivery_single_mp4(monkeypatch, tmp_path):
    conn = _conn(tmp_path)
    try:
        _project, _job = _seed_product_job(conn, admin=True, scene_count=1)
        claim = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-owner-product",
            capabilities=["owner_product_video", "product_video", "ffmpeg"],
            owner_product_video_only=True,
        )
        output = tmp_path / "final.mp4"
        output.write_bytes(b"real mp4 bytes")
        monkeypatch.setattr(
            video_final_output,
            "validate_final_video_output",
            lambda **_kwargs: {"ok": True, "bytes": output.stat().st_size, "duration": 6.0, "has_video": True, "has_audio": False},
        )
        completed = remote_worker_api.complete_remote_worker_job(
            conn,
            worker_id="vps-owner-product",
            job_id=int(claim["job"]["job_id"]),
            result={"ok": True, "render_mode": "real", "renderer": "remote_worker_real_render_route", "test_pattern": False},
            final_video_path=str(output),
            uploaded_file=True,
        )
        assert completed["ok"] is True
        assert completed["duplicate"] is False
        duplicate = remote_worker_api.complete_remote_worker_job(
            conn,
            worker_id="vps-owner-product",
            job_id=int(claim["job"]["job_id"]),
            result={"ok": True, "render_mode": "real", "renderer": "remote_worker_real_render_route", "test_pattern": False},
            final_video_path=str(output),
            uploaded_file=True,
        )
        assert duplicate["ok"] is True
        assert duplicate["duplicate"] is True
        payload = json.loads(completed["job"]["result_json"])
        assert payload["renderer"] == "remote_worker_real_render_route"
        assert payload["test_pattern"] is False
        assert payload["render_mode"] == "real"
        assert "testsrc" not in str(payload.get("renderer", "")).lower()
        assert "fake" not in str(payload.get("renderer", "")).lower()
    finally:
        conn.close()


def test_status_progress_real_stages_and_clean_public_failure(monkeypatch):
    monkeypatch.setattr(bot, "video_b14_fail_stale_product_job_for_status", lambda _job_id: 0)
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: {})
    session = {"draft": {"b14_queue_job": {"id": 55, "status": "processing", "progress_percent": 60}, "b14_invoice": {"scene_count": 3}}}
    text = bot.video_b14_queue_status_text(session, None, ADMIN_UID, "vi")
    assert "✅ Chuẩn bị dựng" in text
    assert "⏳ Dựng video" in text
    failed = {
        "draft": {
            "b14_queue_job": {"id": 56, "status": "failed", "progress_percent": 35, "last_error": "provider worker render_mode test_pattern traceback"},
            "b14_invoice": {"scene_count": 3},
        }
    }
    clean = bot.video_b14_queue_status_text(failed, None, ADMIN_UID, "vi")
    assert bot.VIDEO_B14_PRODUCT_CLEAN_FAIL_MESSAGE in clean
    for forbidden in ("provider", "worker", "render_mode", "test_pattern", "traceback"):
        assert forbidden not in clean.lower()


def test_status_back_returns_video_menu_and_debug_commands_registered():
    callbacks = [button.callback_data for row in bot.video_b14_queue_status_keyboard("vi").inline_keyboard for button in row]
    assert "menu|main_video" in callbacks
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert 'CommandHandler("video_job_debug", cmd_video_render_debug)' in source
    assert 'CommandHandler("video_render_debug", cmd_video_render_debug)' in source
    assert 'CommandHandler("video_worker_debug", cmd_video_worker_claim_debug)' in source


def test_twenty_scenes_path_not_broken_if_supported(monkeypatch, tmp_path):
    captured = {}
    output = tmp_path / "twenty-scenes.mp4"

    def fake_pipeline(**kwargs):
        captured.update(kwargs)
        output.write_bytes(b"twenty scene mp4")
        return {"ok": True, "final_video_path": str(output), "scene_count": kwargs["max_scenes"]}

    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_args, **_kwargs: {"ok": False, "ready_provider_order": [], "providers": []})
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", fake_pipeline)
    result = connector.render_real_video_job(
        {
            "job_id": "p0-18g-20",
            "user_id": str(ADMIN_UID),
            "scene_count": 20,
            "expected_duration_seconds": 120,
            "original_user_prompt": "phim AI nhiều cảnh 20 cảnh",
            "addon_plan": {"subtitle_enabled": True},
        },
        str(tmp_path),
    )
    assert result["ok"] is True
    assert captured["max_scenes"] == 20
    assert result["scene_count"] == 20
