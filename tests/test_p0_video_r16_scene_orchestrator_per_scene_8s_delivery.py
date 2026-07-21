import asyncio
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from services import remote_worker_api
from services import video_real_render_connector as connector


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
REMOTE_WORKER_SOURCE = (ROOT / "remote_worker.py").read_text(encoding="utf-8")
REMOTE_WORKER_API_SOURCE = (ROOT / "services" / "remote_worker_api.py").read_text(encoding="utf-8")
CONNECTOR_SOURCE = (ROOT / "services" / "video_real_render_connector.py").read_text(encoding="utf-8")


def _hydrated_job(*, scene_count=2, persisted_result=None):
    asset_pack = {
        "source": "product_video",
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "product_type": "video_trend",
        "video_product_type": "video_trend",
        "original_user_prompt": "video theo trend ve san pham",
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "public_user_confirmed": True,
        "orchestration_mode": "per_scene_8s",
        "provider_orchestration_mode": "per_scene_8s",
    }
    invoice = {
        "source": "product_video",
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "scene_count": scene_count,
        "duration_seconds": scene_count * 8,
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "public_user_confirmed": True,
        "orchestration_mode": "per_scene_8s",
        "provider_orchestration_mode": "per_scene_8s",
    }
    return {
        "id": 87,
        "job_id": 87,
        "job_type": "video_render",
        "status": "queued",
        "quality_tier": 300,
        "result_json": json.dumps(persisted_result or {}, ensure_ascii=False),
        "project": {
            "project_id": 987,
            "user_id": 123,
            "profile_id": "video_trend",
            "topic": "trend product",
            "prompt_text": "make a product trend video",
            "ratio": "9:16",
            "scene_count": scene_count,
            "quality_tier": 300,
            "asset_pack_json": json.dumps(asset_pack, ensure_ascii=False),
            "invoice_json": json.dumps(invoice, ensure_ascii=False),
            "addon_plan_json": "{}",
            "total_xu_estimated": 400,
        },
        "scenes": [
            {"scene_index": index, "video_prompt": f"Scene {index} prompt"}
            for index in range(1, scene_count + 1)
        ],
    }


def test_product_video_worker_payload_honors_explicit_per_scene_8s():
    payload = remote_worker_api.build_worker_job_payload(_hydrated_job(scene_count=3))

    assert payload["source"] == "product_video"
    assert payload["product_video"] is True
    assert payload["orchestration_mode"] == "per_scene_8s"
    assert payload["provider_orchestration_mode"] == "per_scene_8s"
    assert payload["scene_count"] == 3
    assert payload["scene_duration_seconds"] == 8
    assert payload["duration_seconds"] == 24
    assert payload["expected_duration_seconds"] == 24
    assert payload["test_pattern"] is False
    assert payload["admin_video_delivery"] is False


def test_pending_scene_task_is_rehydrated_for_worker_poll_not_new_single_task():
    persisted = {
        "continue_polling": True,
        "provider_pending_deferred": True,
        "provider_error": "provider_in_progress",
        "selected_provider": "shopaikey_video",
        "provider_events": [
            {
                "scene_index": 1,
                "request_job_id": "87-1",
                "provider": "shopaikey_video",
                "task_id": "scene-task-1",
                "video_id": "scene-video-1",
                "status": "provider_in_progress",
            }
        ],
    }
    payload = remote_worker_api.build_worker_job_payload(_hydrated_job(scene_count=2, persisted_result=persisted))

    assert payload["continue_polling"] is True
    assert payload["provider_pending_task_id"] == "scene-task-1"
    assert payload["provider_pending_request_job_id"] == "87-1"
    assert payload["provider_scene_tasks"][0]["provider_task_id"] == "scene-task-1"
    assert payload["provider_scene_tasks"][0]["request_job_id"] == "87-1"


def test_connector_duration_contract_uses_scene_count_times_8_for_new_jobs():
    job = {"source": "product_video", "orchestration_mode": "per_scene_8s", "scene_count": 2, "duration_seconds": 999}

    assert connector.product_video_orchestration_mode(job) == "per_scene_8s"
    assert connector.product_video_expected_duration_seconds(job) == 16
    contract = connector.product_video_duration_contract(job, 8.1)
    assert contract["ok"] is False
    assert contract["expected_duration_seconds"] == 16
    assert contract["reason"] == "final_duration_short_scene_coverage_missing"


def test_legacy_pending_single_task_keeps_existing_duration_path():
    job = {
        "source": "product_video",
        "provider_pending_task_id": "old-single-task",
        "expected_duration_seconds": 16,
        "scene_count": 2,
    }

    assert connector.product_video_orchestration_mode(job) == "single_task_legacy"
    assert connector.product_video_expected_duration_seconds(job) == 16


def test_scene_request_metadata_is_one_provider_task_per_8s_scene(monkeypatch):
    captured = {}

    def fake_run_provider_generation(request, *, output_dir, environ):
        captured["job_id"] = request.job_id
        captured["duration_seconds"] = request.duration_seconds
        captured["metadata"] = dict(request.metadata)
        output_path = Path(output_dir) / "scene_2.mp4"
        output_path.write_bytes(b"fake-mp4")
        return {
            "ok": True,
            "provider": "mock_video",
            "output_path": str(output_path),
            "provider_task_ids": ["task-scene-2"],
            "provider_video_ids": ["video-scene-2"],
            "result_url_present": True,
            "output_duration": 8,
        }

    monkeypatch.setattr(connector, "run_provider_generation", fake_run_provider_generation)
    monkeypatch.setattr(connector, "ensure_video_output", lambda path: str(path))
    scene = SimpleNamespace(
        scene_id=2,
        video_prompt="Scene 2 action shot",
        visual_prompt="Scene 2 action shot",
        aspect_ratio="9:16",
        target_duration_sec=8,
        _toan_aas_job={
            "job_id": "job-r16",
            "source": "product_video",
            "product_video": True,
            "render_mode": "real",
            "provider_call": True,
            "product_type": "video_trend",
            "scene_count": 3,
            "orchestration_mode": "per_scene_8s",
            "public_user_confirmed": True,
            "submit_source": "public_user_final_confirm",
        },
    )

    tmp_root = ROOT / ".pytest_tmp"
    tmp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=tmp_root) as tmp_dir:
        result = asyncio.run(connector._render_scene_async(scene, str(Path(tmp_dir) / "raw_scene_2.mp4"), []))

    assert result["ok"] is True
    assert captured["job_id"] == "job-r16-2"
    assert captured["duration_seconds"] == 8
    assert captured["metadata"]["scene_index"] == 2
    assert captured["metadata"]["scene_count"] == 3
    assert captured["metadata"]["orchestration_mode"] == "per_scene_8s"
    assert captured["metadata"]["provider_scene_request_id"] == "job-r16-2"


def test_scene_request_polls_existing_scene_task_without_public_submit_source(monkeypatch):
    captured = {}

    def fake_run_provider_generation(request, *, output_dir, environ):
        captured["metadata"] = dict(request.metadata)
        output_path = Path(output_dir) / "scene_1.mp4"
        output_path.write_bytes(b"fake-mp4")
        return {
            "ok": True,
            "provider": "mock_video",
            "output_path": str(output_path),
            "provider_task_ids": ["scene-task-1"],
            "provider_video_ids": ["scene-video-1"],
            "result_url_present": True,
            "output_duration": 8,
        }

    monkeypatch.setattr(connector, "run_provider_generation", fake_run_provider_generation)
    monkeypatch.setattr(connector, "ensure_video_output", lambda path: str(path))
    scene = SimpleNamespace(
        scene_id=1,
        video_prompt="Scene 1 opening",
        visual_prompt="Scene 1 opening",
        aspect_ratio="9:16",
        target_duration_sec=8,
        _toan_aas_job={
            "job_id": "job-r16",
            "source": "product_video",
            "product_video": True,
            "render_mode": "real",
            "provider_call": True,
            "product_type": "video_trend",
            "scene_count": 2,
            "orchestration_mode": "per_scene_8s",
            "scene_tasks": [
                {
                    "scene_index": 1,
                    "request_job_id": "job-r16-1",
                    "provider": "shopaikey_video",
                    "provider_task_id": "scene-task-1",
                    "provider_video_id": "scene-video-1",
                    "status": "provider_in_progress",
                }
            ],
            "public_user_confirmed": True,
            "submit_source": "public_user_final_confirm",
        },
    )

    tmp_root = ROOT / ".pytest_tmp"
    tmp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=tmp_root) as tmp_dir:
        asyncio.run(connector._render_scene_async(scene, str(Path(tmp_dir) / "raw_scene_1.mp4"), []))

    assert captured["metadata"]["submit_source"] == "worker_poll_existing_task"
    assert captured["metadata"]["provider_pending_task_id"] == "scene-task-1"
    assert captured["metadata"]["provider_pending_video_id"] == "scene-video-1"
    assert captured["metadata"]["provider_pending_request_job_id"] == "job-r16-1"


def test_debug_and_public_status_include_scene_orchestrator_fields():
    assert '"per_scene_8s"' in REMOTE_WORKER_API_SOURCE
    assert '"provider_scene_tasks": scene_tasks' in REMOTE_WORKER_API_SOURCE
    assert '"provider_scene_tasks": connector_result.get("scene_tasks")' in REMOTE_WORKER_SOURCE
    assert "Đang dựng cảnh <b>{current_scene}/{scene_total}</b>" in BOT_SOURCE
    assert "• orchestration mode:" in BOT_SOURCE
    assert "• scene tasks:" in BOT_SOURCE
    assert "• concat ready:" in BOT_SOURCE


def test_no_test_introduces_real_provider_smoke_or_hidden_submit_loop():
    self_source = Path(__file__).read_text(encoding="utf-8")
    assert "video_provider" + "_smoke" not in self_source
    assert "submit_video" + "_job(" not in self_source
    assert "run_provider_generation(" in CONNECTOR_SOURCE
    assert "provider_pending_request_job_id" in CONNECTOR_SOURCE
