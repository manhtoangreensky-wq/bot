import tempfile
from datetime import datetime, timezone
from pathlib import Path

from services import video_project_queue
from services import video_provider_router
from services import video_real_render_connector as connector
from services.video_provider_base import VideoGenerationRequest, VideoPollResult, VideoSubmitResult


TMP_ROOT = Path(__file__).resolve().parents[1] / ".pytest_tmp"
TMP_ROOT.mkdir(exist_ok=True)


def _job(*, scene_tasks=None, elapsed: int = 59, provider_order: str = "shopaikey_video,key4u_video", **extra) -> dict:
    data = {
        "job_id": "107",
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "product_type": "video_trend",
        "scene_count": 2,
        "orchestration_mode": "per_scene_8s",
        "provider_order": provider_order,
        "configured_provider_chain": provider_order,
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


def _live_107_debug(scene_index: int = 1, *, elapsed: int = 59) -> dict:
    return {
        "scene_index": scene_index,
        "request_job_id": f"107-{scene_index}",
        "provider": "shopaikey_video",
        "selected_provider": "shopaikey_video",
        "provider_task_id": f"task-r18f-{scene_index}",
        "provider_video_id": f"video-r18f-{scene_index}",
        "provider_task_ids": [f"task-r18f-{scene_index}"],
        "provider_video_ids": [f"video-r18f-{scene_index}"],
        "status": "running",
        "provider_status": "running",
        "normalized_provider_status": "running",
        "provider_status_raw": "NOT_START",
        "raw_provider_status": "NOT_START",
        "nonterminal_provider_status": "NOT_START",
        "provider_progress_raw": 0,
        "provider_progress_normalized": 0,
        "provider_elapsed_seconds": elapsed,
        "provider_wait_elapsed_seconds": elapsed,
        "scene_not_start_elapsed": 0,
        "provider_stalled_not_start": False,
        "fallback_allowed": False,
        "fallback_block_reason": "primary_provider_in_progress",
        "fallback_blocked_reason": "primary_provider_in_progress",
        "primary_provider_task_alive": True,
        "key4u_submit_suppressed": True,
        "continue_polling": True,
        "selected_model": "veo3.1-fast",
    }


def test_job_107_raw_not_start_beats_running_under_threshold():
    debug = connector.product_video_scene_tasks_debug(
        _job(elapsed=59),
        debug_results=[_live_107_debug(1, elapsed=59), _live_107_debug(2, elapsed=59)],
        scene_count=2,
    )

    assert debug[0]["status"] == "provider_not_start"
    assert debug[0]["scene_not_start_elapsed"] >= 59
    assert debug[0]["provider_elapsed_seconds"] >= 59
    assert debug[0]["provider_stalled_not_start"] is False
    assert debug[0]["fallback_allowed"] is False
    assert debug[0]["fallback_block_reason"] == "not_start_under_threshold"
    assert debug[0]["source_of_truth"] == "scene_provider_task"


def test_pending_provider_dominance_preserves_not_start_status():
    payload = {
        **_live_107_debug(1, elapsed=59),
        "provider_pending_provider": "shopaikey_video",
        "provider_pending_task_id": "task-r18f-1",
        "provider_pending_video_id": "video-r18f-1",
        "provider_pending_request_job_id": "107-1",
    }

    result = connector._apply_pending_provider_dominance(payload, job=_job(elapsed=59))

    assert result["normalized_provider_status"] == "not_start"
    assert result["provider_status"] == "not_start"
    assert result["provider_error"] == "provider_not_start"
    assert result["not_start_override_applied"] is True
    assert result["fallback_block_reason"] == "not_start_under_threshold"
    assert result["key4u_submit_suppressed"] is True
    assert result["key4u_submit_suppressed_reason"] == "not_start_under_threshold"


def test_progress_reconcile_uses_raw_not_start_over_stale_running():
    telemetry = video_project_queue.reconcile_provider_progress_telemetry(
        {"status": "queued", "progress_percent": 65, "updated_at": "2026-07-09T00:00:00+00:00"},
        {
            **_live_107_debug(1, elapsed=59),
            "provider_started_at": "2026-07-09T00:00:00+00:00",
            "provider_wait_max_seconds": 600,
        },
        now=datetime(2026, 7, 9, 0, 1, 0, tzinfo=timezone.utc),
    )

    assert telemetry["provider_task_alive"] is True
    assert telemetry["provider_status_for_progress"] == "not_start"
    assert telemetry["provider_task_status"] == "not_start"
    assert telemetry["provider_status_normalized"] == "not_start"
    assert telemetry["provider_elapsed_seconds"] >= 59


def test_not_start_over_threshold_allows_key4u_scene_fallback():
    debug = connector.product_video_scene_tasks_debug(
        _job(elapsed=666),
        debug_results=[_live_107_debug(1, elapsed=666), _live_107_debug(2, elapsed=666)],
        scene_count=2,
    )

    assert debug[0]["status"] == "provider_stalled_not_start"
    assert debug[0]["provider_stalled_not_start"] is True
    assert debug[0]["fallback_allowed"] is True
    assert debug[0]["fallback_block_reason"] == ""
    assert debug[0]["fallback_provider_order"][0] == "key4u_video"
    assert debug[0]["fallback_provider_candidate"] == "key4u_video"


def test_not_start_over_threshold_without_fallback_fails_no_charge():
    with tempfile.TemporaryDirectory(dir=TMP_ROOT) as tmp_dir:
        result = connector._run_per_scene_provider_orchestrator(
            _job(
                elapsed=666,
                provider_order="shopaikey_video",
                scene_tasks=[_live_107_debug(1, elapsed=666), _live_107_debug(2, elapsed=666)],
            ),
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


class _NotStartProvider:
    provider_name = "shopaikey_video"

    def capabilities(self):
        return {
            "provider": self.provider_name,
            "enabled": True,
            "configured": True,
            "public_enabled": True,
            "credit_ok": True,
            "capabilities": ["text_to_video", "scene_video", "multi_scene_video"],
            "submit_url_configured": True,
            "poll_url_configured": True,
            "auth_configured": True,
            "model_configured": True,
            "provider_payload_model": "veo3.1-fast",
        }

    def submit_video_job(self, request):
        return VideoSubmitResult(
            ok=True,
            provider_name=self.provider_name,
            provider_task_id="task-r18f-router",
            provider_video_id="video-r18f-router",
            provider_status="submitted",
            raw={"submit_http_status": 200, "task_id_field_path": "data.id"},
        )

    def poll_video_job(self, provider_task_id: str):
        return VideoPollResult(
            ok=True,
            status="NOT_START",
            provider_name=self.provider_name,
            provider_task_id=provider_task_id,
            raw_status="NOT_START",
            raw={"poll_http_status": 200, "provider_status_raw": "NOT_START", "shopaikey_raw_status": "NOT_START"},
        )

    def materialize_result(self, result, job_id):
        raise AssertionError("NOT_START must not materialize without result_url")


def test_router_pending_payload_keeps_not_start_instead_of_running(monkeypatch, tmp_path):
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [_NotStartProvider()])

    request = VideoGenerationRequest(
        job_id="107-1",
        product_type="video_trend",
        prompt="Scene prompt",
        duration_seconds=8,
        required_capability="text_to_video_or_scene_video",
        metadata={
            "product_video": True,
            "allow_provider_pending": True,
            "submit_source": "public_user_final_confirm",
            "provider_submit_source": "public_user_final_confirm",
            "original_submit_source": "public_user_final_confirm",
            "public_user_confirmed": True,
            "invoice_confirmed": True,
        },
    )
    result = video_provider_router.run_provider_generation(
        request,
        output_dir=str(tmp_path),
        environ={
            "VIDEO_PROVIDER_CHAIN": "shopaikey_video,key4u_video",
            "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1",
            "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS": "0",
            "PRODUCT_VIDEO_PROVIDER_SUBMIT_ENABLED": "1",
        },
        sleep_func=lambda _seconds: None,
    )

    assert result["continue_polling"] is True
    assert result["normalized_provider_status"] == "not_start"
    assert result["provider_status"] == "not_start"
    assert result["provider_error"] == "provider_not_start"
    assert result["fallback_block_reason"] == "not_start_under_threshold"
    assert result["key4u_submit_suppressed"] is True


def test_real_running_status_still_remains_running():
    policy = connector.product_video_scene_stall_policy(
        _job(elapsed=59),
        {
            "scene_index": 1,
            "provider": "shopaikey_video",
            "provider_task_id": "task-running",
            "status": "IN_PROGRESS",
            "provider_status_raw": "IN_PROGRESS",
            "provider_wait_elapsed_seconds": 59,
        },
        1,
    )

    assert policy["current_scene_status"] == "provider_running"
    assert policy["provider_stalled_not_start"] is False
    assert policy["fallback_allowed"] is False


def test_no_real_provider_calls_in_r18f_tests():
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "provider" + "_smoke",
        "submit_url" + "_thật",
    )
    assert all(token not in source for token in forbidden)


def test_product_video_debug_exposes_not_start_and_fallback_fields():
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")

    for label in (
        "raw provider status:",
        "canonical status before NOT_START override:",
        "NOT_START override applied:",
        "scene NOT_START elapsed/threshold:",
        "provider stalled NOT_START:",
        "fallback provider candidate:",
        "key4u submit suppressed reason:",
    ):
        assert label in source
