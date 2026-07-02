import inspect
import json
import sqlite3
from types import SimpleNamespace

import pytest

import bot
import remote_worker
from services import video_project_queue
from services import video_real_render_connector as connector


def _product_job(**overrides):
    job = {
        "id": 47,
        "job_id": "47",
        "job_type": "video_render",
        "user_id": "123",
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "test_pattern": False,
        "admin_video_delivery": False,
        "provider_call": True,
        "public_user": True,
        "admin_only": False,
        "no_charge": False,
        "product_type": "video_ai_prompt",
        "video_flow": "video_ai_prompt",
        "scene_count": 1,
        "expected_duration_seconds": 4,
        "aspect_ratio": "9:16",
        "prompt_text": "real AI prompt video for a clean product demo",
        "addon_plan": {},
    }
    job.update(overrides)
    return job


def _ready_readiness():
    return {
        "ok": True,
        "ready_provider_order": ["shopaikey_video", "key4u_video"],
        "first_ready_provider": "shopaikey_video",
        "enabled_count": 2,
        "configured_count": 2,
        "enabled_providers": ["shopaikey_video", "key4u_video"],
        "configured_providers": ["shopaikey_video", "key4u_video"],
        "providers": [
            {"provider": "shopaikey_video", "enabled": True, "configured": True, "capabilities": ["text_to_video"]},
            {"provider": "key4u_video", "enabled": True, "configured": True, "capabilities": ["text_to_video"]},
        ],
        "missing_env": {},
    }


def _pipeline_calls_renderer(tmp_path):
    def fake_pipeline(**kwargs):
        scene = SimpleNamespace(
            scene_id=1,
            video_prompt="provider scene prompt",
            visual_prompt="provider scene prompt",
            target_duration_sec=4,
            aspect_ratio="9:16",
        )
        raw_path = tmp_path / "scene_001_raw.mp4"
        render_result = kwargs["render_video_func"](scene, str(raw_path))
        return {
            "ok": True,
            "final_video_path": render_result["output_path"],
            "created_files": [render_result["output_path"]],
            "scene_count": kwargs["max_scenes"],
        }

    return fake_pipeline


def test_public_video_ai_prompt_product_job_forces_provider_router(monkeypatch, tmp_path):
    calls = {"count": 0, "requests": []}

    def fake_provider(request, *, output_dir, environ=None, sleep_func=None):
        del environ, sleep_func
        calls["count"] += 1
        calls["requests"].append(request)
        output = tmp_path / "provider_output.mp4"
        output.write_bytes(b"provider mp4 bytes")
        return {
            "ok": True,
            "provider_attempted": True,
            "provider_router_called": True,
            "provider": "shopaikey_video",
            "selected_provider": "shopaikey_video",
            "provider_candidates_count": 2,
            "provider_submit_called": True,
            "provider_submit_http_status": 200,
            "provider_task_id_saved": True,
            "provider_poll_called": True,
            "provider_result_url_present": True,
            "provider_task_ids": ["shop-task-47"],
            "provider_video_ids": ["shop-video-47"],
            "provider_status": "downloaded",
            "normalized_provider_status": "succeeded",
            "output_path": str(output),
            "local_path": str(output),
        }

    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_a, **_k: _ready_readiness())
    monkeypatch.setattr(connector, "run_provider_generation", fake_provider)
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", _pipeline_calls_renderer(tmp_path))
    monkeypatch.setattr(
        connector,
        "build_local_scene_composer",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("local_scene_composer must not run for public product video")),
    )

    result = connector.render_real_video_job(_product_job(), str(tmp_path / "work"))

    assert calls["count"] == 1
    assert calls["requests"][0].metadata["product_video"] is True
    assert calls["requests"][0].metadata["allow_provider_pending"] is True
    assert result["route_requires_provider"] is True
    assert result["local_fallback_allowed"] is False
    assert result["provider_router_called"] is True
    assert result["provider_attempted"] is True
    assert result["provider_submit_called"] is True
    assert result["provider_task_id_saved"] is True
    assert result["provider_poll_called"] is True
    assert result["selected_provider"] == "shopaikey_video"
    assert result["provider_candidates_count"] == 2
    assert result["connector_renderer"] == connector.PROVIDER_BRIDGE_RENDERER
    assert result["visual_source"] == connector.VISUAL_SOURCE_PROVIDER_MP4
    assert result["base_video_source"] == "provider"
    assert result["placeholder_forbidden"] is True
    assert result["placeholder_detected"] is False


def test_public_video_pending_provider_keeps_polling_no_local_placeholder(monkeypatch, tmp_path):
    def pending_provider(request, *, output_dir, environ=None, sleep_func=None):
        del request, output_dir, environ, sleep_func
        return {
            "ok": False,
            "provider_attempted": True,
            "provider_router_called": True,
            "provider": "shopaikey_video",
            "selected_provider": "shopaikey_video",
            "provider_candidates_count": 2,
            "provider_submit_called": True,
            "provider_submit_http_status": 200,
            "provider_task_id_saved": True,
            "provider_poll_called": True,
            "provider_result_url_present": False,
            "provider_task_ids": ["shop-task-47"],
            "provider_video_ids": ["shop-video-47"],
            "provider_status": "running",
            "normalized_provider_status": "running",
            "blocker": "provider_in_progress",
            "provider_error": "provider_in_progress",
            "continue_polling": True,
            "no_charge": True,
        }

    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_a, **_k: _ready_readiness())
    monkeypatch.setattr(connector, "run_provider_generation", pending_provider)
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", _pipeline_calls_renderer(tmp_path))
    monkeypatch.setattr(
        connector,
        "build_local_scene_composer",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("local_scene_composer must not run while provider is pending")),
    )

    with pytest.raises(connector.RealVideoRenderError) as exc:
        connector.render_real_video_job(_product_job(), str(tmp_path / "work"))

    diagnostics = exc.value.diagnostics
    assert str(exc.value) == "provider_in_progress"
    assert diagnostics["route_requires_provider"] is True
    assert diagnostics["local_fallback_allowed"] is False
    assert diagnostics["provider_router_called"] is True
    assert diagnostics["provider_attempted"] is True
    assert diagnostics["provider_submit_called"] is True
    assert diagnostics["provider_task_id_saved"] is True
    assert diagnostics["provider_poll_called"] is True
    assert diagnostics["provider_task_ids"] == ["shop-task-47"]
    assert diagnostics["continue_polling"] is True
    assert diagnostics["normalized_provider_status"] == "running"
    assert diagnostics["placeholder_detected"] is False
    assert diagnostics["base_video_source"] != "placeholder"
    assert diagnostics["no_charge"] is True


def test_remote_worker_does_not_terminal_fail_provider_pending(monkeypatch):
    captured = {}
    job = _product_job(job_id="47")

    monkeypatch.setattr(remote_worker, "claim_job", lambda **_kwargs: job)
    monkeypatch.setattr(remote_worker, "product_video_job_allowed", lambda _job: True)

    def fake_process(_job):
        remote_worker.LAST_REAL_VIDEO_RENDER_RESULT = {"continue_polling": True, "provider_error": "provider_in_progress"}
        raise RuntimeError("provider_in_progress")

    def fake_fail(job_id, safe_error, retryable=True, partial_artifacts=None):
        captured.update({"job_id": job_id, "safe_error": safe_error, "retryable": retryable, "partial_artifacts": partial_artifacts})
        return {"ok": True}

    monkeypatch.setattr(remote_worker, "process_claimed_job", fake_process)
    monkeypatch.setattr(remote_worker, "fail_job", fake_fail)

    assert remote_worker.run_once(product_video_only=True) == "failed"
    assert captured["job_id"] == "47"
    assert captured["retryable"] is True
    assert "provider_in_progress" in captured["safe_error"]


def test_video_render_debug_mentions_provider_lifecycle_fields():
    source = inspect.getsource(bot.video_render_debug_text)
    for needle in [
        "route requires provider",
        "provider router called",
        "provider submit called",
        "provider task id saved",
        "provider poll called",
        "continue polling",
        "normalized provider status",
        "base video source",
        "placeholder forbidden",
    ]:
        assert needle in source


def test_video_provider_job_debug_masks_provider_ids_and_reports_pending_lifecycle():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        project = video_project_queue.create_video_project(
            conn,
            user_id=123,
            profile_id="video_ai_prompt",
            topic="clean product video",
            asset_pack={"source": "product_video", "render_mode": "real", "provider_call": True},
        )
        project = video_project_queue.update_video_project(
            conn,
            int(project["project_id"]),
            status="queued_for_worker",
            total_xu_estimated=300,
            is_confirmed=1,
        )
        job = video_project_queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=123)
        result = {
            "provider_attempted": True,
            "provider_router_called": True,
            "provider_submit_called": True,
            "provider_submit_http_status": 200,
            "provider_task_id_saved": True,
            "provider_poll_called": True,
            "provider_task_ids": ["shop-task-47-secret"],
            "provider_video_ids": ["shop-video-47-secret"],
            "selected_provider": "shopaikey_video",
            "provider_status": "running",
            "normalized_provider_status": "running",
            "provider_result_url_present": False,
            "continue_polling": True,
            "blocker": "provider_in_progress",
        }
        conn.execute(
            "UPDATE video_jobs SET status='processing', result_json=?, last_error=? WHERE id=?",
            (json.dumps(result), "provider_in_progress", int(job["id"])),
        )
        conn.commit()

        text = bot.video_provider_job_debug_text(int(job["id"]), conn=conn)

        assert "Video Provider Job Debug" in text
        assert "shopaikey_video" in text
        assert "continue polling: <code>yes</code>" in text
        assert "provider_in_progress" in text
        assert "shop-task-47-secret" not in text
        assert "shop***cret" in text
    finally:
        conn.close()


def test_video_provider_job_debug_command_registered():
    source = inspect.getsource(bot.lifespan)
    assert 'CommandHandler("video_provider_job_debug", cmd_video_provider_job_debug)' in source
