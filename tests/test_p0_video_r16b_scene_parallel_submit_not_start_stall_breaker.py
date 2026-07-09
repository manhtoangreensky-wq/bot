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
        "provider_order": "shopaikey_video,key4u_video",
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
    }
    return {
        "id": 99,
        "job_id": 99,
        "job_type": "video_render",
        "status": "queued",
        "quality_tier": 300,
        "started_at": "2026-07-08 10:00:00",
        "updated_at": "2026-07-08 10:02:00",
        "result_json": json.dumps(persisted_result or {}, ensure_ascii=False),
        "project": {
            "project_id": 999,
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


def _job(scene_tasks=None, **extra):
    data = {
        "job_id": "job-r16b",
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "product_type": "video_trend",
        "scene_count": 2,
        "orchestration_mode": "per_scene_8s",
        "provider_order": "shopaikey_video,key4u_video",
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "original_user_prompt": "make a product trend video",
    }
    if scene_tasks is not None:
        data["scene_tasks"] = scene_tasks
        data["provider_scene_tasks"] = scene_tasks
    data.update(extra)
    return data


def test_scene_count_2_creates_two_scene_task_records_with_pending_scene_2():
    persisted = {
        "continue_polling": True,
        "provider_pending_deferred": True,
        "provider_error": "provider_in_progress",
        "selected_provider": "shopaikey_video",
        "provider_events": [
            {
                "scene_index": 1,
                "request_job_id": "99-1",
                "provider": "shopaikey_video",
                "task_id": "scene-task-1",
                "video_id": "scene-video-1",
                "status": "NOT_START",
                "provider_progress_raw": 0,
            }
        ],
    }

    payload = remote_worker_api.build_worker_job_payload(_hydrated_job(scene_count=2, persisted_result=persisted))

    assert len(payload["provider_scene_tasks"]) == 2
    assert payload["provider_scene_tasks"][0]["provider_task_id"] == "scene-task-1"
    assert payload["provider_scene_tasks"][0]["request_job_id"] == "99-1"
    assert payload["provider_scene_tasks"][1]["status"] == "pending_submit"
    assert payload["provider_scene_tasks"][1]["request_job_id"] == "99-2"


def test_not_start_under_threshold_waits_no_fallback_no_charge():
    task = {
        "scene_index": 1,
        "request_job_id": "job-r16b-1",
        "provider": "shopaikey_video",
        "provider_task_id": "task-1",
        "provider_video_id": "video-1",
        "status": "NOT_START",
        "provider_progress_raw": 0,
        "provider_wait_elapsed_seconds": 30,
    }

    policy = connector.product_video_scene_stall_policy(_job([task]), task, 1)

    assert policy["provider_stalled_not_start"] is False
    assert policy["fallback_allowed"] is False
    assert policy["fallback_block_reason"] == "not_start_under_threshold"


def test_not_start_over_threshold_marks_stalled_and_allows_public_fallback_once():
    task = {
        "scene_index": 1,
        "request_job_id": "job-r16b-1",
        "provider": "shopaikey_video",
        "provider_task_id": "task-1",
        "provider_video_id": "video-1",
        "status": "NOT_START",
        "provider_progress_raw": 0,
        "provider_wait_elapsed_seconds": 120,
        "fallback_count": 0,
    }

    policy = connector.product_video_scene_stall_policy(_job([task]), task, 1)

    assert policy["provider_stalled_not_start"] is True
    assert policy["fallback_allowed"] is True
    assert policy["fallback_scene_index"] == 1
    assert policy["fallback_provider_order"][0] == "key4u_video"
    assert policy["stall_threshold"] == 120


def test_hidden_or_debug_source_does_not_allow_scene_fallback_submit():
    task = {
        "scene_index": 1,
        "request_job_id": "job-r16b-1",
        "provider": "shopaikey_video",
        "provider_task_id": "task-1",
        "status": "NOT_START",
        "provider_progress_raw": 0,
        "provider_wait_elapsed_seconds": 120,
    }
    hidden_job = _job([task], public_user_confirmed=False, invoice_confirmed=False, submit_source="debug", provider_submit_source="debug")

    policy = connector.product_video_scene_stall_policy(hidden_job, task, 1)

    assert policy["provider_stalled_not_start"] is True
    assert policy["fallback_allowed"] is False
    assert policy["fallback_block_reason"] == "not_public_user_final_confirm"


def test_stalled_scene_fallback_uses_next_provider_chain_and_fallback_source(monkeypatch):
    captured = {}

    def fake_run_provider_generation(request, *, output_dir, environ):
        captured["metadata"] = dict(request.metadata)
        captured["chain"] = environ.get("VIDEO_PROVIDER_CHAIN")
        output_path = Path(output_dir) / "scene_1_fallback.mp4"
        output_path.write_bytes(b"fake-mp4")
        return {
            "ok": True,
            "provider": "key4u_video",
            "output_path": str(output_path),
            "provider_task_ids": ["task-fallback-1"],
            "provider_video_ids": ["video-fallback-1"],
            "result_url_present": True,
            "output_duration": 8,
        }

    monkeypatch.setattr(connector, "run_provider_generation", fake_run_provider_generation)
    monkeypatch.setattr(connector, "ensure_video_output", lambda path: str(path))
    stalled_task = {
        "scene_index": 1,
        "request_job_id": "job-r16b-1",
        "provider": "shopaikey_video",
        "provider_task_id": "task-1",
        "provider_video_id": "video-1",
        "status": "NOT_START",
        "provider_progress_raw": 0,
        "provider_wait_elapsed_seconds": 120,
    }
    scene = SimpleNamespace(
        scene_id=1,
        video_prompt="Scene 1 opening",
        visual_prompt="Scene 1 opening",
        aspect_ratio="9:16",
        target_duration_sec=8,
        _toan_aas_job=_job([stalled_task]),
    )

    tmp_root = ROOT / ".pytest_tmp"
    tmp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=tmp_root) as tmp_dir:
        result = asyncio.run(connector._render_scene_async(scene, str(Path(tmp_dir) / "raw_scene_1.mp4"), []))

    assert result["ok"] is True
    assert captured["metadata"]["submit_source"] == "public_confirmed_scene_fallback_once"
    assert captured["metadata"]["fallback_count"] == 1
    assert captured["metadata"]["fallback_scene_index"] == 1
    assert captured["chain"].split(",")[0] == "key4u_video"


def test_per_scene_orchestrator_submits_scene_2_even_when_scene_1_pending(monkeypatch):
    calls = []

    def fake_run_provider_generation(request, *, output_dir, environ):
        calls.append(request.job_id)
        scene_index = int(str(request.job_id).rsplit("-", 1)[-1])
        return {
            "ok": False,
            "provider": "shopaikey_video",
            "selected_provider": "shopaikey_video",
            "provider_task_ids": [f"task-{scene_index}"],
            "provider_video_ids": [f"video-{scene_index}"],
            "provider_task_id_saved": True,
            "provider_submit_called": True,
            "provider_poll_called": True,
            "submit_accepted": True,
            "continue_polling": True,
            "provider_error": "provider_in_progress",
            "blocker": "provider_in_progress",
            "provider_status": "running",
            "normalized_provider_status": "running",
            "scene_index": scene_index,
            "request_job_id": request.job_id,
            "provider_progress_raw": 0,
        }

    monkeypatch.setattr(connector, "run_provider_generation", fake_run_provider_generation)
    tmp_root = ROOT / ".pytest_tmp"
    tmp_root.mkdir(exist_ok=True)
    events: list[dict] = []
    debug: list[dict] = []
    with tempfile.TemporaryDirectory(dir=tmp_root) as tmp_dir:
        result = connector._run_per_scene_provider_orchestrator(
            _job(),
            tmp_dir,
            provider_order=["shopaikey_video", "key4u_video"],
            provider_events=events,
            debug_results=debug,
        )

    assert calls == ["job-r16b-1", "job-r16b-2"]
    assert result["ok"] is False
    assert result["continue_polling"] is True
    assert result["scene_tasks_created_count"] == 2
    assert result["scene_tasks_submitted_count"] == 2
    assert result["scenes_running"] == 2
    assert result["scenes_pending"] == 0
    assert result["no_charge"] is True


def test_debug_status_and_finance_fields_are_registered_in_source():
    assert "scene_tasks_created_count" in REMOTE_WORKER_SOURCE
    assert "scene_success_count" in BOT_SOURCE
    assert "charge after final delivery" in BOT_SOURCE
    assert "provider_stalled_not_start" in BOT_SOURCE
    assert "Đang chờ hệ thống bắt đầu cảnh" in BOT_SOURCE
    assert "Hệ thống đang chuyển cảnh" in BOT_SOURCE


def test_codex_tests_use_fixtures_only_without_paid_calls():
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "gh pr " + "merge",
        "provider" + "_smoke",
        "submit_url" + "_thật",
    )
    assert all(token not in source for token in forbidden)
