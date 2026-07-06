import json
from datetime import datetime

import bot
from services import video_project_queue, video_provider_router
from services.video_provider_base import VideoGenerationRequest, VideoPollResult, VideoSubmitResult


class _ShopAIKeyProvider:
    provider_name = "shopaikey_video"

    def __init__(self, poll_status="running", raw_status="IN_PROGRESS", progress="30%", result_url="", error_code=""):
        self.submit_calls = 0
        self.poll_calls = 0
        self.poll_status = poll_status
        self.raw_status = raw_status
        self.progress = progress
        self.result_url = result_url
        self.error_code = error_code

    def capabilities(self):
        return {
            "provider": self.provider_name,
            "enabled": True,
            "configured": True,
            "missing": [],
            "capabilities": ["text_to_video", "scene_video", "multi_scene_video"],
            "submit_url_configured": True,
            "poll_url_configured": True,
            "auth_configured": True,
            "model_configured": True,
            "provider_auth_value_present": True,
            "provider_model_present": True,
            "provider_payload_model": "veo3.1-fast",
        }

    def submit_video_job(self, request):
        self.submit_calls += 1
        return VideoSubmitResult(
            ok=True,
            provider_name=self.provider_name,
            provider_task_id="shop-task-r8c",
            provider_status="IN_PROGRESS",
            raw={"http_status": 200, "task_id_field_path": "data.id_base"},
        )

    def poll_video_job(self, provider_task_id):
        self.poll_calls += 1
        result_url_present = bool(self.result_url)
        return VideoPollResult(
            ok=True,
            status=self.poll_status,
            provider_name=self.provider_name,
            provider_task_id=provider_task_id,
            raw_status=self.raw_status,
            progress_percent=30 if self.progress == "30%" else 100 if self.progress == "100%" else None,
            result_url=self.result_url,
            file_url=self.result_url,
            error_code=self.error_code,
            raw={
                "smoke_stage": "poll_response_parse",
                "poll_http_status": 200,
                "provider_status_raw": self.raw_status,
                "result_url_present": result_url_present,
                "result_url_source_path": "data.result_url" if result_url_present else "none",
                "provider_progress_raw": self.progress,
                "provider_progress_raw_number": 30 if self.progress == "30%" else 100,
                "provider_progress_source": "data.progress",
                "http_200_not_used_as_progress": True,
                "shopaikey_status_endpoint_exact": True,
                "shopaikey_status_http_code": 200,
                "shopaikey_raw_status": self.raw_status,
                "shopaikey_normalized_status": self.poll_status,
                "shopaikey_data_progress_raw": self.progress,
                "shopaikey_progress_source": "data.progress",
                "shopaikey_result_url_from_data": result_url_present,
                "shopaikey_data_result_url_present": result_url_present,
            },
        )


def _request(metadata=None):
    return VideoGenerationRequest(
        job_id="81",
        product_type="video_trend",
        video_flow_type="video_trend",
        prompt="A real product video",
        ratio="9:16",
        duration_seconds=18,
        required_capability="text_to_video_or_scene_video",
        metadata={
            "product_video": True,
            "allow_provider_pending": True,
            "wallet_charge": False,
            **(metadata or {}),
        },
    )


def _env():
    return {
        "VIDEO_PROVIDER_CHAIN": "shopaikey_video",
        "PRODUCT_VIDEO_PROVIDER_SUBMIT_ENABLED": "true",
        "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1",
        "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS": "0",
    }


def _run_provider(monkeypatch, tmp_path, provider, metadata=None):
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [provider])
    return video_provider_router.run_provider_generation(
        _request(metadata),
        output_dir=str(tmp_path),
        environ=_env(),
        sleep_func=lambda _seconds: None,
    )


def _job(result, *, status="processing", progress=20):
    return {
        "id": 81,
        "project_id": 810,
        "status": status,
        "progress_percent": progress,
        "progress_message": "provider_in_progress",
        "result_json": json.dumps(result),
        "created_at": "2026-07-05 10:00:00",
        "updated_at": "2026-07-05 10:00:00",
        "started_at": "2026-07-05 10:00:00",
    }


def test_runtime_poller_promotes_r8b_shopaikey_parser_fields(monkeypatch, tmp_path):
    provider = _ShopAIKeyProvider()
    result = _run_provider(monkeypatch, tmp_path, provider)

    assert provider.submit_calls == 1
    assert provider.poll_calls == 1
    assert result["provider_submit_called"] is True
    assert result["provider_poll_called"] is True
    assert result["shopaikey_status_endpoint_exact"] is True
    assert result["shopaikey_status_http_code"] == 200
    assert result["shopaikey_raw_status"] == "IN_PROGRESS"
    assert result["shopaikey_data_progress_raw"] == "30%"
    assert result["provider_progress_raw"] == "30%"
    assert result["provider_progress_source"] == "data.progress"
    assert result["http_200_not_used_as_progress"] is True
    assert result["continue_polling"] is True
    assert result["no_charge"] is True


def test_provider_attempts_record_exact_endpoint_data_status_and_progress(monkeypatch, tmp_path):
    result = _run_provider(monkeypatch, tmp_path, _ShopAIKeyProvider())
    attempts = result["provider_attempts"]
    poll_attempt = next(item for item in attempts if item.get("poll_called"))

    assert poll_attempt["shopaikey_status_endpoint_exact"] is True
    assert poll_attempt["shopaikey_status_http_code"] == 200
    assert poll_attempt["shopaikey_raw_status"] == "IN_PROGRESS"
    assert poll_attempt["shopaikey_data_progress_raw"] == "30%"
    assert poll_attempt["provider_progress_source"] == "data.progress"
    assert poll_attempt["http_200_not_used_as_progress"] is True


def test_progress_status_reconcile_uses_data_progress_not_http_200():
    payload = {
        "selected_provider": "shopaikey_video",
        "provider_task_id_saved": True,
        "provider_task_ids": ["shop-task-r8c"],
        "provider_submit_called": True,
        "submit_accepted": True,
        "provider_poll_called": True,
        "continue_polling": True,
        "primary_provider_continue_polling": True,
        "primary_provider_task_alive": True,
        "primary_provider_task_id_present": True,
        "normalized_provider_status": "running",
        "provider_status": "running",
        "provider_progress_raw": 200,
        "provider_attempts": [
            {
                "provider": "shopaikey_video",
                "phase": "poll",
                "poll_called": True,
                "poll_http_status": 200,
                "shopaikey_status_endpoint_exact": True,
                "shopaikey_status_http_code": 200,
                "shopaikey_raw_status": "IN_PROGRESS",
                "shopaikey_normalized_status": "running",
                "shopaikey_data_progress_raw": "30%",
                "shopaikey_progress_source": "data.progress",
                "provider_progress_raw": "30%",
                "provider_progress_source": "data.progress",
                "http_200_not_used_as_progress": True,
                "continue_polling": True,
            }
        ],
    }

    telemetry = video_project_queue.reconcile_provider_progress_telemetry(
        _job(payload),
        payload,
        now=datetime(2026, 7, 5, 10, 1, 0),
        refresh_source="progress_status_debug",
    )

    assert telemetry["provider_progress_raw"] == "30%"
    assert telemetry["provider_progress_raw_number"] == 30
    assert telemetry["provider_progress_source"] == "data.progress"
    assert telemetry["http_200_not_used_as_progress"] is True
    assert telemetry["provider_progress_cap_reason"] != "invalid_provider_progress_raw"
    assert telemetry["shopaikey_status_endpoint_exact"] is True
    assert telemetry["shopaikey_data_progress_raw"] == "30%"
    assert telemetry["render_video_progress_percent_public"] == "0"
    assert telemetry["render_progress_public_mode"] == "zero_waiting"


def test_job_debug_reconciler_uses_primary_alive_attempt_parser_over_stale_summary():
    result = {
        "selected_provider": "shopaikey_video",
        "provider_task_id_saved": True,
        "provider_task_ids": ["shop-task-r8c"],
        "submit_accepted": True,
        "provider_submit_http_status": 0,
        "provider_submit_http_5xx": True,
        "provider_progress_raw": 200,
        "continue_polling": True,
        "primary_provider_continue_polling": True,
        "primary_provider_task_alive": True,
        "primary_provider_task_id_present": True,
        "normalized_provider_status": "running",
        "provider_attempts": [
            {
                "provider": "shopaikey_video",
                "phase": "poll",
                "submit_http_status": 200,
                "submit_accepted": True,
                "task_id_present": True,
                "poll_called": True,
                "shopaikey_status_endpoint_exact": True,
                "shopaikey_status_http_code": 200,
                "shopaikey_raw_status": "IN_PROGRESS",
                "shopaikey_normalized_status": "running",
                "shopaikey_data_progress_raw": "30%",
                "shopaikey_progress_source": "data.progress",
                "provider_progress_raw": "30%",
                "provider_progress_source": "data.progress",
                "http_200_not_used_as_progress": True,
                "continue_polling": True,
            }
        ],
    }

    debug = bot.video_b14_reconciled_provider_debug(_job(result), {}, result, refresh_source="video_provider_job_debug")

    assert debug["provider_submit_http_status"] == 200
    assert debug["provider_submit_http_5xx"] is False
    assert debug["shopaikey_status_endpoint_exact"] is True
    assert debug["shopaikey_status_http_code"] == 200
    assert debug["shopaikey_raw_status"] == "IN_PROGRESS"
    assert debug["shopaikey_data_progress_raw"] == "30%"
    assert debug["provider_progress_raw"] == "30%"
    assert debug["provider_progress_source"] == "data.progress"
    assert debug["http_200_not_used_as_progress"] is True


def test_provider_failure_stops_polling_no_charge_no_paid_fallback(monkeypatch, tmp_path):
    provider = _ShopAIKeyProvider(poll_status="failed", raw_status="FAILURE", progress="100%", result_url="https://cdn.example/not-video.json", error_code="failed")
    result = _run_provider(monkeypatch, tmp_path, provider)

    assert result["provider_status"] == "failed"
    assert result["blocker"] == "provider_failed_result_url_invalid"
    assert result["continue_polling"] is not True
    assert result["no_charge"] is True
    assert result.get("charge", 0) == 0
    assert result.get("fallback_used") is False
    assert result.get("provider_fallback_attempted") is False
    assert result.get("fallback_allowed") is False
    assert result["shopaikey_status_endpoint_exact"] is True
    assert result["shopaikey_data_progress_raw"] == "100%"
    assert result["result_url_source_path"] == "data.result_url"
    assert result["result_url_present"] is True
    assert result["result_url_host"] == "cdn.example"
    assert result["result_url_scheme"] == "https"
    assert result["result_url_ext"] == ".json"
    assert result["result_url_trusted"] is False
    assert result["download_http_status"] == 0
    assert result["download_bytes"] == 0
    assert result["download_error_class"] == "provider_terminal_failure"
    assert result["mp4_validator_result"] == "not_run_provider_terminal_failure"
    assert "provider" not in result["public_message"].lower()
    assert "api" not in result["public_message"].lower()
    assert "debug" not in result["public_message"].lower()
