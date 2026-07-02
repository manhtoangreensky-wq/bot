import json
import sqlite3
from types import SimpleNamespace

import pytest

import remote_worker
from services import remote_worker_api, video_project_queue
from services import video_real_render_connector as connector


def _product_job(**overrides):
    job = {
        "id": 48,
        "job_id": "48",
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
        "engine_adapter": "text_to_video",
        "scene_count": 3,
        "expected_duration_seconds": 18,
        "aspect_ratio": "9:16",
        "prompt_text": "real AI video for a product launch",
        "asset_pack": {
            "source": "product_video",
            "render_mode": "real",
            "provider_call": True,
            "product_type": "video_ai_prompt",
            "engine_adapter": "text_to_video",
            "public_user": True,
        },
        "addon_plan": {},
    }
    job.update(overrides)
    return job


def _ready_readiness():
    return {
        "ok": True,
        "ready_provider_order": ["shopaikey_video"],
        "first_ready_provider": "shopaikey_video",
        "enabled_count": 1,
        "configured_count": 1,
        "enabled_providers": ["shopaikey_video"],
        "configured_providers": ["shopaikey_video"],
        "providers": [
            {"provider": "shopaikey_video", "enabled": True, "configured": True, "capabilities": ["text_to_video"]},
        ],
        "missing_env": {},
    }


def _pipeline_calls_renderer(tmp_path):
    def fake_pipeline(**kwargs):
        scene = SimpleNamespace(
            scene_id=1,
            video_prompt="provider scene prompt",
            visual_prompt="provider scene prompt",
            target_duration_sec=6,
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


def test_product_video_text_to_video_selects_provider_router_not_local_composer(monkeypatch, tmp_path):
    calls = {"count": 0, "requests": []}

    def fake_provider(request, *, output_dir, environ=None, sleep_func=None):
        del output_dir, environ, sleep_func
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
            "provider_candidates_count": 1,
            "provider_submit_called": True,
            "provider_submit_http_status": 200,
            "provider_task_id_saved": True,
            "provider_poll_called": True,
            "provider_result_url_present": True,
            "provider_task_ids": ["shop-task-48"],
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
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("local_scene_composer must not run")),
    )
    monkeypatch.setattr(connector.video_final_output, "probe_video", lambda _path: {"ok": True, "bytes": 2048, "duration": 6, "has_video": True, "has_audio": False})

    result = connector.render_real_video_job(_product_job(), str(tmp_path / "work"))

    assert calls["count"] == 1
    assert calls["requests"][0].metadata["product_video"] is True
    assert calls["requests"][0].metadata["allow_provider_pending"] is True
    assert result["route_requires_provider"] is True
    assert result["provider_router_called"] is True
    assert result["provider_attempted"] is True
    assert result["provider_submit_called"] is True
    assert result["provider_task_id_saved"] is True
    assert result["connector_renderer"] == connector.PROVIDER_BRIDGE_RENDERER
    assert result["connector_renderer"] != connector.LOCAL_PLACEHOLDER_RENDERER
    assert result["visual_source"] == connector.VISUAL_SOURCE_PROVIDER_MP4
    assert result["base_video_source"] == "provider"
    assert result["placeholder_detected"] is False


def test_provider_in_progress_keeps_polling_and_forbids_local_placeholder(monkeypatch, tmp_path):
    def pending_provider(request, *, output_dir, environ=None, sleep_func=None):
        del request, output_dir, environ, sleep_func
        return {
            "ok": False,
            "provider_attempted": True,
            "provider_router_called": True,
            "provider": "shopaikey_video",
            "selected_provider": "shopaikey_video",
            "provider_candidates_count": 1,
            "provider_submit_called": True,
            "provider_submit_http_status": 200,
            "provider_task_id_saved": True,
            "provider_poll_called": True,
            "provider_result_url_present": False,
            "provider_task_ids": ["shop-task-48"],
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
    assert diagnostics["provider_router_called"] is True
    assert diagnostics["provider_attempted"] is True
    assert diagnostics["provider_submit_called"] is True
    assert diagnostics["provider_task_id_saved"] is True
    assert diagnostics["provider_task_ids"] == ["shop-task-48"]
    assert diagnostics["continue_polling"] is True
    assert diagnostics["connector_renderer"] == connector.PROVIDER_BRIDGE_RENDERER
    assert diagnostics["connector_renderer"] != connector.LOCAL_PLACEHOLDER_RENDERER
    assert diagnostics["visual_source"] == "provider_pending"
    assert diagnostics["base_video_source"] == "provider"
    assert diagnostics["placeholder_detected"] is False
    assert diagnostics["no_charge"] is True


def test_remote_worker_provider_pending_returns_pending_not_failed(monkeypatch):
    captured = {}
    job = _product_job(job_id="48")

    monkeypatch.setattr(remote_worker, "claim_job", lambda **_kwargs: job)
    monkeypatch.setattr(remote_worker, "product_video_job_allowed", lambda _job: True)

    def fake_process(_job):
        remote_worker.LAST_REAL_VIDEO_RENDER_RESULT = {
            "continue_polling": True,
            "provider_error": "provider_in_progress",
            "provider_router_called": True,
            "provider_task_ids": ["shop-task-48"],
        }
        raise RuntimeError("provider_in_progress")

    def fake_fail(job_id, safe_error, retryable=True, partial_artifacts=None):
        captured.update({"job_id": job_id, "safe_error": safe_error, "retryable": retryable, "partial_artifacts": partial_artifacts})
        return {"ok": True, "deferred": True, "continue_polling": True, "status": "queued"}

    monkeypatch.setattr(remote_worker, "process_claimed_job", fake_process)
    monkeypatch.setattr(remote_worker, "fail_job", fake_fail)

    assert remote_worker.run_once(product_video_only=True) == "pending"
    assert captured["job_id"] == "48"
    assert captured["retryable"] is True
    assert "provider_in_progress" in captured["safe_error"]


def test_worker_fail_provider_pending_requeues_without_terminal_failure():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        project = video_project_queue.create_video_project(
            conn,
            user_id=123,
            profile_id="video_ai_prompt",
            topic="provider pending video",
            asset_pack={
                "source": "product_video",
                "render_mode": "real",
                "provider_call": True,
                "product_type": "video_ai_prompt",
                "public_user": True,
            },
        )
        video_project_queue.update_video_project(
            conn,
            int(project["project_id"]),
            status="queued_for_worker",
            total_xu_estimated=300,
            is_confirmed=1,
        )
        job = video_project_queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=123)
        claimed = video_project_queue.claim_next_video_job(conn, worker_id="vps-toanaas-01")
        assert int(claimed["id"]) == int(job["id"])

        result = remote_worker_api.fail_remote_worker_job(
            conn,
            worker_id="vps-toanaas-01",
            job_id=int(job["id"]),
            safe_error="RuntimeError:provider_in_progress",
            retryable=True,
            diagnostics={
                "continue_polling": True,
                "provider_router_called": True,
                "provider_submit_called": True,
                "provider_task_id_saved": True,
                "provider_task_ids": ["shop-task-48-secret"],
                "provider_error": "provider_in_progress",
                "provider_status": "running",
                "normalized_provider_status": "running",
                "no_charge": True,
            },
        )

        updated_job = result["job"]
        updated_project = result["project"]
        payload = json.loads(updated_job["result_json"])

        assert result["ok"] is True
        assert result["deferred"] is True
        assert result["continue_polling"] is True
        assert updated_job["status"] == "queued"
        assert updated_project["status"] == "processing"
        assert updated_project["video_terminal_state"] == "final_rendering"
        assert payload["provider_router_called"] is True
        assert payload["provider_submit_called"] is True
        assert payload["provider_task_id_saved"] is True
        assert payload["provider_task_ids"] == ["shop-task-48-secret"]
        assert payload["continue_polling"] is True
        assert payload["no_charge"] is True
        assert updated_job["last_error"] == "provider_in_progress"
    finally:
        conn.close()
