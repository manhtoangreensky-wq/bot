import tempfile
from pathlib import Path

from services import video_real_render_connector as connector


TMP_ROOT = Path(__file__).resolve().parents[1] / ".pytest_tmp"
TMP_ROOT.mkdir(exist_ok=True)


def _scene_task(index: int, *, status: str = "provider_running", raw_status: str = "NOT_START", elapsed: int = 0, fallback_count: int = 0) -> dict:
    return {
        "scene_index": index,
        "request_job_id": f"106-{index}",
        "provider": "shopaikey_video",
        "provider_task_id": f"task-r18e-{index}",
        "provider_video_id": f"video-r18e-{index}",
        "status": status,
        "provider_status_raw": raw_status,
        "provider_progress_raw": 0,
        "provider_progress_normalized": 0,
        "provider_wait_elapsed_seconds": elapsed,
        "scene_not_start_elapsed": 0,
        "fallback_count": fallback_count,
        "selected_model": "veo3.1-fast",
    }


def _job(*, scene_tasks=None, elapsed: int = 59, provider_order: str = "shopaikey_video,key4u_video", **extra) -> dict:
    data = {
        "job_id": "106",
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "product_type": "video_trend",
        "scene_count": 2,
        "orchestration_mode": "per_scene_8s",
        "provider_order": provider_order,
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "original_submit_source": "public_user_final_confirm",
        "provider_elapsed_seconds": elapsed,
        "provider_wait_elapsed_seconds": elapsed,
        "selected_provider": "shopaikey_video",
        "selected_model": "veo3.1-fast",
        "selected_family": "google_veo",
        "selected_payload_adapter": "shopaikey_veo_small_clip",
        "provider_model_map": {"shopaikey_video": "veo3.1-fast", "key4u_video": "kling-3.0-turbo"},
    }
    if scene_tasks is not None:
        data["scene_tasks"] = scene_tasks
        data["provider_scene_tasks"] = scene_tasks
    data.update(extra)
    return data


def test_job_106_not_start_elapsed_uses_provider_elapsed_without_fallback_under_threshold():
    tasks = [_scene_task(1, elapsed=0), _scene_task(2, elapsed=0)]
    debug = connector.product_video_scene_tasks_debug(_job(scene_tasks=tasks, elapsed=59), scene_count=2)

    assert len(debug) == 2
    assert debug[0]["status"] == "provider_not_start"
    assert debug[0]["scene_not_start_elapsed"] >= 59
    assert debug[0]["provider_elapsed_seconds"] >= 59
    assert debug[0]["provider_stalled_not_start"] is False
    assert debug[0]["fallback_allowed"] is False
    assert debug[0]["fallback_block_reason"] == "scene_not_stalled"
    assert debug[0]["not_start_threshold_seconds"] == 90


def test_not_start_over_threshold_marks_stalled_and_fallback_candidate_from_job_elapsed():
    tasks = [_scene_task(1, elapsed=0), _scene_task(2, elapsed=0)]
    debug = connector.product_video_scene_tasks_debug(_job(scene_tasks=tasks, elapsed=666), scene_count=2)

    assert debug[0]["status"] == "provider_stalled_not_start"
    assert debug[0]["scene_not_start_elapsed"] >= 666
    assert debug[0]["provider_stalled_not_start"] is True
    assert debug[0]["fallback_allowed"] is True
    assert debug[0]["fallback_provider_order"][0] == "key4u_video"
    assert debug[0]["fallback_eligibility_reason"] == "eligible"


def test_not_start_over_threshold_without_fallback_provider_fails_no_charge():
    tasks = [_scene_task(1, elapsed=0), _scene_task(2, elapsed=0)]
    with tempfile.TemporaryDirectory(dir=TMP_ROOT) as tmp_dir:
        result = connector._run_per_scene_provider_orchestrator(
            _job(scene_tasks=tasks, elapsed=666, provider_order="shopaikey_video"),
            tmp_dir,
            provider_order=["shopaikey_video"],
            provider_events=[],
            debug_results=[],
        )

    assert result["ok"] is False
    assert result["terminal_state"] == "failed_no_charge"
    assert result["continue_polling"] is False
    assert result["provider_error"] == "provider_stalled_not_start"
    assert result["fallback_allowed"] is False
    assert result["fallback_block_reason"] == "no_fallback_provider"
    assert result["no_charge"] is True


def test_scene_debug_maps_status_fallback_reason_and_selected_model_by_scene():
    tasks = [_scene_task(1, elapsed=0), _scene_task(2, elapsed=0)]
    debug = connector.product_video_scene_tasks_debug(_job(scene_tasks=tasks, elapsed=59), scene_count=2)
    scene_status_by_scene = {str(item["scene_index"]): item["status"] for item in debug}
    fallback_eligible_by_scene = {str(item["scene_index"]): item["fallback_allowed"] for item in debug}
    fallback_reason_by_scene = {str(item["scene_index"]): item["fallback_block_reason"] for item in debug}
    selected_model_by_scene = {str(item["scene_index"]): item.get("selected_model") or item.get("model") or "" for item in debug}

    assert scene_status_by_scene["1"] == "provider_not_start"
    assert fallback_eligible_by_scene["1"] is False
    assert fallback_reason_by_scene["1"] == "scene_not_stalled"
    assert selected_model_by_scene["1"] == "veo3.1-fast"
    assert debug[0]["fallback_provider_order"][0] == "key4u_video"


def test_hidden_debug_status_recover_do_not_submit_provider_in_r18e_source_contract():
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "provider" + "_smoke",
        "submit_url" + "_thật",
    )
    assert all(token not in source for token in forbidden)
