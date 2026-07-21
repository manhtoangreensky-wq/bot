import json
import os
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
    conn = sqlite3.connect(tmp_path / "p0_18h_job30.db")
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _short_workspace(prefix: str) -> str:
    root = Path(".pytest_tmp")
    root.mkdir(exist_ok=True)
    return tempfile.mkdtemp(prefix=f"{prefix}_", dir=str(root))


def _ffmpeg_required():
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg missing")


def _job30_addons(**overrides):
    data = {
        "voice_enabled": True,
        "voice_source": "default_male",
        "voice_label": "Nam mặc định",
        "voice_volume_percent": 120,
        "music_enabled": True,
        "music_source": "default",
        "music_volume_percent": 30,
        "subtitle_enabled": True,
        "subtitle_source": "voice_script",
        "logo_enabled": True,
        "logo_source": "text",
        "logo_text": "TOAN AAS",
        "logo_position": "top_right",
        "dub_enabled": False,
    }
    data.update(overrides)
    return data


def _product_job(addon_plan=None, **overrides):
    job = {
        "job_id": "30",
        "job_type": "video_render",
        "user_id": str(ADMIN_UID),
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "test_pattern": False,
        "admin_video_delivery": False,
        "provider_call": True,
        "public_user": False,
        "admin_only": True,
        "no_charge": True,
        "product_type": "script_to_video",
        "scene_count": 3,
        "expected_duration_seconds": 3,
        "aspect_ratio": "9:16",
        "original_user_prompt": "job 30 equivalent product video with voice music subtitle logo",
        "addon_plan": addon_plan if addon_plan is not None else _job30_addons(),
    }
    job.update(overrides)
    return job


def _seed_job30(conn, *, addon_plan=None, scene_count=3):
    asset_pack = {
        "source": "product_video",
        "render_mode": "real",
        "test_pattern": False,
        "admin_video_delivery": False,
        "fake_renderer_allowed": False,
        "real_renderer_required": True,
        "provider_call": True,
        "public_user": False,
        "admin_only": True,
        "created_by_admin": True,
        "no_charge": True,
        "scene_count": scene_count,
        "duration_seconds": scene_count * 6,
        "original_user_prompt": "job 30 equivalent product video",
    }
    project = queue.create_video_project(conn, user_id=ADMIN_UID, profile_id="product_review", topic="job30", ratio="9:16", asset_pack=asset_pack)
    queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="queued_for_worker",
        is_confirmed=1,
        confirmed_at=queue.now_text(),
        invoice_json={**asset_pack, "total_xu": 0},
        addon_plan_json=addon_plan if addon_plan is not None else _job30_addons(),
        scene_cards_json=[
            {
                "scene_index": index,
                "narration_line": f"Scene {index} narration for job 30.",
                "subtitle_line": f"Scene {index} subtitle.",
                "provider_prompt": f"Scene {index} product video prompt.",
            }
            for index in range(1, scene_count + 1)
        ],
        prompt_text="job 30 equivalent product video",
        total_xu_estimated=0,
        scene_count=scene_count,
    )
    job = queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=ADMIN_UID, max_attempts=1)
    queue.update_video_project(conn, int(project["project_id"]), job_id=int(job["id"]))
    return queue.get_video_project(conn, int(project["project_id"])), job


def test_p0_18h_job30_payload_voice_music_subtitle_logo_does_not_crash(monkeypatch):
    _ffmpeg_required()
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_args, **_kwargs: {"ok": False, "ready_provider_order": [], "providers": []})
    result = connector.render_real_video_job(_product_job(expected_duration_seconds=3), _short_workspace("p018h_job30"))
    final_path = Path(result["final_video_path"])
    assert result["ok"] is True
    assert final_path.is_file()
    assert final_path.stat().st_size > 0
    assert result["renderer"] == "local_scene_card_engine"
    assert result["visual_classification"] == "final_ai_video"
    assert result["placeholder_detected"] is False
    assert result["no_charge"] is True
    assert result["partial_addons"] is True
    assert any(item.get("addon") == "voice" and item.get("reason") == "voice_addon_not_available_in_video_composer" for item in result["addon_degrade_notes"])


def test_product_video_live_path_calls_local_composer_fallback(monkeypatch, tmp_path):
    captured = {}
    output = tmp_path / "fallback.mp4"

    def fake_pipeline(**kwargs):
        captured.update(kwargs)
        output.write_bytes(b"mp4")
        return {"ok": True, "final_video_path": str(output), "scene_count": kwargs["max_scenes"]}

    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_args, **_kwargs: {"ok": False, "ready_provider_order": [], "providers": []})
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", fake_pipeline)
    result = connector.render_real_video_job(_product_job(addon_plan=_job30_addons(voice_enabled=False)), str(tmp_path))
    assert result["ok"] is True
    assert result["renderer"] == "local_scene_card_engine"
    assert result["visual_classification"] == "final_ai_video"
    assert captured["render_video_func"].__name__ == "_render"


def test_product_video_fallback_runs_when_provider_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_args, **_kwargs: {"ok": False, "ready_provider_order": [], "providers": []})
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", lambda **kwargs: {"ok": True, "final_video_path": str((tmp_path / "ok.mp4")), "scene_count": kwargs["max_scenes"]})
    (tmp_path / "ok.mp4").write_bytes(b"ok")
    result = connector.render_real_video_job(_product_job(addon_plan={}), str(tmp_path))
    assert result["ok"] is True
    assert result["provider_attempted"] is False
    assert result["renderer"] == "local_scene_card_engine"
    assert result["visual_classification"] == "final_ai_video"
    assert result["no_charge"] is True


def test_music_default_missing_does_not_kill_video(monkeypatch, tmp_path):
    output = tmp_path / "music-missing.mp4"
    output.write_bytes(b"mp4")
    monkeypatch.setattr(connector, "_ffmpeg_binary", lambda: "")
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_args, **_kwargs: {"ok": False, "ready_provider_order": [], "providers": []})
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", lambda **_kwargs: {"ok": True, "final_video_path": str(output), "scene_count": 3})
    result = connector.render_real_video_job(_product_job(addon_plan=_job30_addons(voice_enabled=False, subtitle_enabled=False, logo_enabled=False)), str(tmp_path))
    assert result["ok"] is True
    assert result["visual_classification"] == "final_ai_video"
    assert any(item.get("addon") == "music" and item.get("applied") is False for item in result["addon_degrade_notes"])


def test_voice_addon_failure_diagnostic_and_safe_handling(monkeypatch, tmp_path):
    output = tmp_path / "voice.mp4"
    output.write_bytes(b"mp4")
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_args, **_kwargs: {"ok": False, "ready_provider_order": [], "providers": []})
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", lambda **_kwargs: {"ok": True, "final_video_path": str(output), "scene_count": 3})
    result = connector.render_real_video_job(_product_job(addon_plan=_job30_addons(music_enabled=False, subtitle_enabled=False, logo_enabled=False)), str(tmp_path))
    assert result["ok"] is True
    assert result["visual_classification"] == "final_ai_video"
    assert result["partial_addons"] is True
    assert any(item.get("addon") == "voice" and item.get("applied") is False for item in result["addon_degrade_notes"])


def test_subtitle_from_voice_missing_data_does_not_crash_composer(monkeypatch):
    _ffmpeg_required()
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_args, **_kwargs: {"ok": False, "ready_provider_order": [], "providers": []})
    addon = _job30_addons(voice_enabled=False, music_enabled=False, logo_enabled=False, subtitle_enabled=True, subtitle_source="voice_script")
    result = connector.render_real_video_job(_product_job(addon_plan=addon, expected_duration_seconds=3), _short_workspace("p018h_sub"))
    assert result["ok"] is True
    assert result["visual_classification"] == "final_ai_video"
    assert Path(result["final_video_path"]).is_file()


def test_logo_overlay_failure_does_not_crash_composer(monkeypatch, tmp_path):
    output = tmp_path / "logo-copy.mp4"
    output.write_bytes(b"mp4")
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_args, **_kwargs: {"ok": False, "ready_provider_order": [], "providers": []})
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", lambda **_kwargs: {"ok": True, "final_video_path": str(output), "scene_count": 3})
    result = connector.render_real_video_job(_product_job(addon_plan=_job30_addons(voice_enabled=False, music_enabled=False, subtitle_enabled=False, logo_text="")), str(tmp_path))
    assert result["ok"] is True
    assert result["visual_classification"] == "final_ai_video"
    assert result["logo_requested"] is True


def test_artifact_saved_and_exists_before_success(monkeypatch):
    _ffmpeg_required()
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_args, **_kwargs: {"ok": False, "ready_provider_order": [], "providers": []})
    completed = {}
    monkeypatch.setattr(remote_worker, "WORKER_TMP_DIR", _short_workspace("p018hw"))
    monkeypatch.setattr(remote_worker, "send_heartbeat", lambda *_args, **_kwargs: None)

    def fake_complete(job_id, result, final_video_path=""):
        assert os.path.isfile(final_video_path)
        assert os.path.getsize(final_video_path) > 0
        completed.update({"job_id": job_id, "result": result, "path": final_video_path})
        return {"ok": True}

    monkeypatch.setattr(remote_worker, "complete_job", fake_complete)
    assert remote_worker.process_claimed_job(_product_job(expected_duration_seconds=3))["ok"] is True
    assert completed["result"]["partial_addons"] is True
    assert completed["result"]["visual_classification"] == "final_ai_video"
    assert completed["result"]["no_charge"] is True
    assert completed["result"]["addon_degrade_notes"]


def test_render_output_path_persisted_to_job(monkeypatch, tmp_path):
    conn = _conn(tmp_path)
    try:
        _project, _job = _seed_job30(conn)
        claim = remote_worker_api.claim_remote_worker_job(conn, worker_id="vps-owner", capabilities=["owner_product_video", "product_video"], owner_product_video_only=True)
        output = tmp_path / "final.mp4"
        output.write_bytes(b"mp4")
        monkeypatch.setattr(
            video_final_output,
            "validate_final_video_output",
            lambda **_kwargs: {"ok": True, "bytes": output.stat().st_size, "duration": 6.0, "has_video": True, "has_audio": False},
        )
        completed = remote_worker_api.complete_remote_worker_job(
            conn,
            worker_id="vps-owner",
            job_id=int(claim["job"]["job_id"]),
            result={"ok": True, "render_mode": "real", "renderer": "remote_worker_real_render_route"},
            final_video_path=str(output),
            uploaded_file=True,
        )
        assert completed["ok"] is True
        assert completed["project"]["final_video_path"] == str(output)
    finally:
        conn.close()


def test_no_success_without_mp4(tmp_path):
    conn = _conn(tmp_path)
    try:
        _seed_job30(conn)
        claim = remote_worker_api.claim_remote_worker_job(conn, worker_id="vps-owner", capabilities=["owner_product_video", "product_video"], owner_product_video_only=True)
        result = remote_worker_api.complete_remote_worker_job(
            conn,
            worker_id="vps-owner",
            job_id=int(claim["job"]["job_id"]),
            result={"ok": True, "render_mode": "real", "renderer": "remote_worker_real_render_route"},
        )
        assert result["ok"] is False
        assert result["reason"] == "product_result_file_missing"
    finally:
        conn.close()


def test_no_charge_when_render_fails(tmp_path):
    conn = _conn(tmp_path)
    try:
        project, _job = _seed_job30(conn)
        claim = remote_worker_api.claim_remote_worker_job(conn, worker_id="vps-owner", capabilities=["owner_product_video", "product_video"], owner_product_video_only=True)
        failed = remote_worker_api.fail_remote_worker_job(conn, worker_id="vps-owner", job_id=int(claim["job"]["job_id"]), safe_error="voice_addon_connector_missing", retryable=False)
        assert failed["ok"] is True
        project_after = queue.get_video_project(conn, int(project["project_id"]))
        assert int(project_after.get("total_xu_estimated") or 0) == 0
        assert not project_after.get("final_video_path")
    finally:
        conn.close()


def test_no_color_bars_or_testsrc_in_product(monkeypatch, tmp_path):
    output = tmp_path / "clean.mp4"
    output.write_bytes(b"mp4")
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_args, **_kwargs: {"ok": False, "ready_provider_order": [], "providers": []})
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", lambda **_kwargs: {"ok": True, "final_video_path": str(output), "scene_count": 3})
    result = connector.render_real_video_job(_product_job(addon_plan={}), str(tmp_path))
    assert "testsrc" not in str(result.get("renderer", "")).lower()
    assert "color bars" not in str(result.get("renderer", "")).lower()
    assert "fake" not in str(result.get("renderer", "")).lower()


def test_admin_video_debug_includes_artifact_and_addon_readiness(tmp_path):
    conn = _conn(tmp_path)
    try:
        _project, job = _seed_job30(conn)
        text = bot.video_render_debug_text(int(job["id"]), mode="video_render_debug")
        assert "artifact path" in text
        assert "voice:" in text
        assert "music:" in text
        assert "subtitle:" in text
        assert "logo:" in text
        assert "ffmpeg available" in text
    finally:
        conn.close()


def test_public_error_has_no_technical_words(monkeypatch):
    monkeypatch.setattr(bot, "video_b14_fail_stale_product_job_for_status", lambda _job_id: 0)
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: {})
    session = {"draft": {"b14_queue_job": {"id": 30, "status": "failed", "progress_percent": 35, "last_error": "RuntimeError:voice_addon_connector_missing provider ffmpeg traceback"}, "b14_invoice": {"scene_count": 3}}}
    text = bot.video_b14_queue_status_text(session, None, ADMIN_UID, "vi")
    assert bot.VIDEO_B14_PRODUCT_CLEAN_FAIL_MESSAGE in text
    for forbidden in ("worker", "provider", "ffmpeg", "traceback", "render_mode", "payload", "test_pattern"):
        assert forbidden not in text.lower()


def test_status_35_failure_reports_cleanly_but_debug_has_root_cause(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "p0_18h_job30.db"))
    conn = _conn(tmp_path)
    try:
        _project, job = _seed_job30(conn)
        queue.fail_video_job(conn, job_id=int(job["id"]), error="RuntimeError:voice_addon_connector_missing", retry=False)
        text = bot.video_render_debug_text(int(job["id"]), mode="video_job_debug")
        assert "voice_addon_connector_missing" in text
    finally:
        conn.close()
    monkeypatch.setattr(bot, "video_b14_fail_stale_product_job_for_status", lambda _job_id: 0)
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: {"id": 30, "status": "failed", "progress_percent": 35, "last_error": "RuntimeError:voice_addon_connector_missing"})
    public_text = bot.video_b14_queue_status_text({"draft": {"b14_queue_job": {"id": 30}, "b14_invoice": {"scene_count": 3}}}, None, ADMIN_UID, "vi")
    assert bot.VIDEO_B14_PRODUCT_CLEAN_FAIL_MESSAGE in public_text


def test_worker_runtime_version_check_present_if_supported():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert 'CommandHandler("video_worker_debug", cmd_video_worker_claim_debug)' in source
    assert 'CommandHandler("video_artifact_debug", cmd_video_render_debug)' in source
