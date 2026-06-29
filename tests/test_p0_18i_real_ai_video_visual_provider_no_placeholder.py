import json
import os
import sqlite3
from pathlib import Path

import bot
import remote_worker
from services import remote_worker_api
from services import video_project_queue as queue
from services import video_real_render_connector as connector


ADMIN_UID = int(bot.ADMIN_ID)


def _conn(tmp_path):
    db_path = tmp_path / "p0_18i_video_visual.db"
    conn = sqlite3.connect(db_path)
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _product_job(**overrides):
    job = {
        "job_id": "31",
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
        "scene_count": 3,
        "expected_duration_seconds": 18,
        "aspect_ratio": "9:16",
        "original_user_prompt": "video AI chân thật cho sản phẩm mới",
        "addon_plan": {"subtitle_enabled": True, "music_enabled": True, "music_source": "default", "logo_enabled": True, "logo_text": "TOAN AAS"},
        "scene_cards": [
            {
                "scene_index": index,
                "narration_line": f"Lời đọc sạch cảnh {index}.",
                "subtitle_line": f"Phụ đề sạch cảnh {index}.",
                "provider_prompt": f"Scene {index}: cinematic product visual, no text in frame.",
            }
            for index in range(1, 4)
        ],
    }
    job.update(overrides)
    return job


def _seed_product_job(conn, *, result=None, final_video_path=""):
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
        "scene_count": 3,
        "duration_seconds": 18,
        "original_user_prompt": "job 31 product video",
    }
    project = queue.create_video_project(conn, user_id=ADMIN_UID, profile_id="product_review", topic="job31", ratio="9:16", asset_pack=asset_pack)
    queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="queued_for_worker",
        is_confirmed=1,
        confirmed_at=queue.now_text(),
        invoice_json={**asset_pack, "total_xu": 0},
        addon_plan_json={"subtitle_enabled": True, "music_enabled": True, "logo_enabled": True},
        scene_cards_json=_product_job()["scene_cards"],
        prompt_text="job 31 product video",
        total_xu_estimated=0,
        scene_count=3,
    )
    job = queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=ADMIN_UID, max_attempts=1)
    queue.update_video_project(conn, int(project["project_id"]), job_id=int(job["id"]))
    if result is not None:
        claim = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-owner",
            capabilities=["owner_product_video", "product_video", "ffmpeg"],
            owner_product_video_only=True,
        )
        assert claim.get("ok") is True
        return remote_worker_api.complete_remote_worker_job(
            conn,
            worker_id="vps-owner",
            job_id=int(job["id"]),
            result=result,
            final_video_path=final_video_path,
            uploaded_file=bool(final_video_path),
        )
    return queue.get_video_project(conn, int(project["project_id"])), job


def test_product_video_provider_attempted_when_ready(monkeypatch, tmp_path):
    output = tmp_path / "provider.mp4"
    output.write_bytes(b"provider mp4")
    provider_builder_called = {"ok": False}

    def fake_builder(job, events=None):
        provider_builder_called["ok"] = True

        def _render(_scene, _raw_path):
            return {"ok": True, "provider": "shopaikey", "task_id": "task-31", "output_path": str(output)}

        return _render

    def fake_pipeline(**kwargs):
        assert kwargs["render_video_func"].__name__ == "_render"
        return {"ok": True, "final_video_path": str(output), "scene_count": kwargs["max_scenes"], "duration_sec": 18}

    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_args, **_kwargs: {"ok": True, "ready_provider_order": ["shopaikey"], "providers": []})
    monkeypatch.setattr(connector, "build_real_scene_renderer", fake_builder)
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", fake_pipeline)
    result = connector.render_real_video_job(_product_job(), str(tmp_path))
    assert provider_builder_called["ok"] is True
    assert result["provider_attempted"] is True
    assert result["provider_route_selected"] is True
    assert result["renderer"] == "provider_scene_video"
    assert result["visual_classification"] == "final_ai_video"
    assert result["visual_source"] == "provider_mp4"


def test_product_video_does_not_skip_provider_to_local_placeholder(monkeypatch, tmp_path):
    output = tmp_path / "provider-only.mp4"
    output.write_bytes(b"provider mp4")
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_args, **_kwargs: {"ok": True, "ready_provider_order": ["key4u"], "providers": []})
    monkeypatch.setattr(connector, "build_local_scene_composer", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("local composer must not run when provider is ready")))
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", lambda **kwargs: {"ok": True, "final_video_path": str(output), "scene_count": kwargs["max_scenes"]})
    result = connector.render_real_video_job(_product_job(), str(tmp_path))
    assert result["renderer"] == "provider_scene_video"
    assert result["visual_classification"] == "final_ai_video"


def test_local_placeholder_not_final_ai_video(monkeypatch, tmp_path):
    output = tmp_path / "partial.mp4"
    output.write_bytes(b"partial mp4")
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_args, **_kwargs: {"ok": False, "ready_provider_order": [], "providers": []})
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", lambda **kwargs: {"ok": True, "final_video_path": str(output), "scene_count": kwargs["max_scenes"]})
    result = connector.render_real_video_job(_product_job(), str(tmp_path))
    assert result["renderer"] == "local_scene_composer"
    assert result["visual_classification"] == "partial_simple_video"
    assert result["placeholder_detected"] is True
    assert result["no_charge"] is True


def test_text_slide_prompt_not_final_success(tmp_path):
    assert connector.classify_visual_result({"ok": True, "renderer": "local_scene_composer", "placeholder_detected": True}) == "partial_simple_video"
    assert connector.classify_visual_result({"ok": True, "renderer": "provider_scene_video", "raw_prompt_burned_into_frame": True}) == "failed_no_real_visual"


def test_raw_prompt_not_used_as_subtitle(monkeypatch, tmp_path):
    output = tmp_path / "no-subtitle.mp4"
    output.write_bytes(b"partial mp4")
    captured = {}

    def fake_pipeline(**kwargs):
        captured["enable_subtitle"] = kwargs["enable_subtitle"]
        return {"ok": True, "final_video_path": str(output), "scene_count": kwargs["max_scenes"], "subtitle_path": None}

    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_args, **_kwargs: {"ok": False, "ready_provider_order": [], "providers": []})
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", fake_pipeline)
    job = _product_job(scene_cards=[], addon_plan={"subtitle_enabled": True}, original_user_prompt="chủ thể chính: POV trải nghiệm thật: Add one subtle visual")
    result = connector.render_real_video_job(job, str(tmp_path))
    assert captured["enable_subtitle"] is False
    assert result["subtitle_user_facing_source"] is False
    assert result["raw_prompt_burned_into_frame"] is False


def test_scene_prompt_not_burned_into_frame_text(monkeypatch, tmp_path):
    output = tmp_path / "clean-subtitle.mp4"
    output.write_bytes(b"provider mp4")
    captured = {}

    def fake_pipeline(**kwargs):
        captured["enable_subtitle"] = kwargs["enable_subtitle"]
        return {"ok": True, "final_video_path": str(output), "scene_count": kwargs["max_scenes"], "subtitle_path": None}

    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_args, **_kwargs: {"ok": True, "ready_provider_order": ["shopaikey"], "providers": []})
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", fake_pipeline)
    result = connector.render_real_video_job(_product_job(scene_cards=[], addon_plan={"subtitle_enabled": True}), str(tmp_path))
    assert captured["enable_subtitle"] is False
    assert result["visual_classification"] == "final_ai_video"


def test_final_ai_video_requires_provider_or_real_visual_asset():
    assert connector.classify_visual_result({"ok": True, "renderer": "provider_scene_video", "provider_attempted": True}) == "final_ai_video"
    assert connector.classify_visual_result({"ok": True, "renderer": "local_scene_composer"}) == "partial_simple_video"
    assert connector.classify_visual_result({"ok": False, "renderer": "provider_scene_video"}) == "failed_no_real_visual"


def test_partial_simple_video_charges_zero(monkeypatch, tmp_path):
    completed = {}

    def fake_render(job, work_dir):
        output = Path(work_dir) / "partial.mp4"
        output.write_bytes(b"partial mp4")
        remote_worker.LAST_REAL_VIDEO_RENDER_RESULT = {
            "renderer": "local_scene_composer",
            "provider_attempted": False,
            "provider_route_selected": False,
            "fallback_used": True,
            "fallback_reason": "real_video_renderer_unavailable",
            "visual_source": "local_placeholder",
            "visual_classification": "partial_simple_video",
            "final_classification": "partial_simple_video",
            "placeholder_detected": True,
            "raw_prompt_burned_into_frame": False,
        }
        return str(output)

    monkeypatch.setattr(remote_worker, "render_real_video", fake_render)
    monkeypatch.setattr(remote_worker, "send_heartbeat", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(remote_worker, "complete_job", lambda job_id, result, final_video_path="": completed.update({"job_id": job_id, "result": result, "path": final_video_path}) or {"ok": True})
    assert remote_worker.process_claimed_job(_product_job(no_charge=False))["ok"] is True
    assert completed["result"]["visual_classification"] == "partial_simple_video"
    assert completed["result"]["no_charge"] is True


def test_partial_simple_video_public_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: {})
    monkeypatch.setattr(bot, "video_b14_fail_stale_product_job_for_status", lambda _job_id: 0)
    conn = _conn(tmp_path)
    try:
        output = tmp_path / "partial.mp4"
        output.write_bytes(b"partial mp4")
        completed = _seed_product_job(
            conn,
            result={"ok": True, "render_mode": "real", "renderer": "remote_worker_real_render_route", "connector_renderer": "local_scene_composer", "visual_classification": "partial_simple_video", "no_charge": True, "placeholder_detected": True},
            final_video_path=str(output),
        )
        text = bot.video_b14_queue_status_text({"draft": {"b14_queue_job": completed["job"], "b14_invoice": {"scene_count": 3}}}, completed, ADMIN_UID, "vi")
        assert bot.VIDEO_B14_PARTIAL_SIMPLE_MESSAGE in text
        assert "hệ thống đã dựng video thật" not in text
    finally:
        conn.close()


def test_failed_no_real_visual_no_charge(tmp_path):
    conn = _conn(tmp_path)
    try:
        _project, job = _seed_product_job(conn)
        claim = remote_worker_api.claim_remote_worker_job(conn, worker_id="vps-owner", capabilities=["owner_product_video", "product_video"], owner_product_video_only=True)
        output = tmp_path / "bad.mp4"
        output.write_bytes(b"bad mp4")
        failed = remote_worker_api.complete_remote_worker_job(
            conn,
            worker_id="vps-owner",
            job_id=int(claim["job"]["job_id"]),
            result={"ok": True, "render_mode": "real", "renderer": "remote_worker_real_render_route", "connector_renderer": "provider_scene_video", "visual_classification": "failed_no_real_visual"},
            final_video_path=str(output),
            uploaded_file=True,
        )
        assert failed["ok"] is False
        assert failed["reason"] == "real_ai_visual_required_for_product_video"
        row = queue.get_video_render_job(conn, int(job["id"]))
        assert row["status"] == "failed"
    finally:
        conn.close()


def test_admin_debug_reports_provider_attempted_and_fallback_reason(tmp_path, monkeypatch):
    db_path = tmp_path / "debug.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    conn = sqlite3.connect(db_path)
    queue.ensure_video_project_queue_schema(conn)
    try:
        output = tmp_path / "partial.mp4"
        output.write_bytes(b"partial mp4")
        completed = _seed_product_job(
            conn,
            result={
                "ok": True,
                "render_mode": "real",
                "renderer": "remote_worker_real_render_route",
                "connector_renderer": "local_scene_composer",
                "provider_attempted": False,
                "provider_route_selected": False,
                "fallback_used": True,
                "fallback_reason": "real_video_renderer_unavailable",
                "visual_source": "local_placeholder",
                "visual_classification": "partial_simple_video",
                "placeholder_detected": True,
                "no_charge": True,
            },
            final_video_path=str(output),
        )
        text = bot.video_render_debug_text(int(completed["job"]["id"]), mode="video_render_debug")
        assert "provider route selected" in text
        assert "provider attempted" in text
        assert "fallback reason" in text
        assert "local_placeholder" in text
        assert "partial_simple_video" in text
    finally:
        conn.close()


def test_renderer_classification_final_ai_video():
    payload = {"ok": True, "renderer": "provider_scene_video", "provider_attempted": True, "visual_source": "provider_mp4"}
    assert connector.classify_visual_result(payload) == "final_ai_video"


def test_renderer_classification_partial_placeholder():
    payload = {"ok": True, "renderer": "local_scene_composer", "visual_source": "local_placeholder"}
    assert connector.classify_visual_result(payload) == "partial_simple_video"


def test_job31_like_voice_music_subtitle_logo_does_not_use_prompt_text_subtitle(monkeypatch, tmp_path):
    output = tmp_path / "job31.mp4"
    output.write_bytes(b"partial mp4")
    captured = {}

    def fake_pipeline(**kwargs):
        captured["enable_subtitle"] = kwargs["enable_subtitle"]
        return {"ok": True, "final_video_path": str(output), "scene_count": kwargs["max_scenes"], "subtitle_path": None}

    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_args, **_kwargs: {"ok": False, "ready_provider_order": [], "providers": []})
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", fake_pipeline)
    job = _product_job(
        scene_cards=[{"scene_index": 1, "provider_prompt": "chủ thể chính: POV trải nghiệm thật: Add one subtle visual"}],
        addon_plan={"voice_enabled": True, "music_enabled": True, "subtitle_enabled": True, "logo_enabled": True, "logo_text": "TOAN AAS"},
    )
    result = connector.render_real_video_job(job, str(tmp_path))
    assert captured["enable_subtitle"] is False
    assert result["raw_prompt_burned_into_frame"] is False
    assert result["visual_classification"] == "partial_simple_video"


def test_success_copy_not_used_for_placeholder_video(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: {})
    monkeypatch.setattr(bot, "video_b14_fail_stale_product_job_for_status", lambda _job_id: 0)
    result = {
        "ok": True,
        "render_mode": "real",
        "renderer": "remote_worker_real_render_route",
        "connector_renderer": "local_scene_composer",
        "visual_classification": "partial_simple_video",
        "no_charge": True,
        "placeholder_detected": True,
    }
    session = {
        "draft": {
            "b14_queue_job": {"id": 0, "status": "completed", "result_json": json.dumps(result), "final_video_path": str(tmp_path / "partial.mp4")},
            "b14_invoice": {"scene_count": 3},
        }
    }
    text = bot.video_b14_queue_status_text(session, None, ADMIN_UID, "vi")
    assert bot.VIDEO_B14_PARTIAL_SIMPLE_MESSAGE in text
    assert "Hệ thống đã dựng video thật" not in text
