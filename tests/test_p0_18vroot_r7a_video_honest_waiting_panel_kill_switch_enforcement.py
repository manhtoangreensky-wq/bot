from datetime import datetime

import bot
from services import video_project_queue, video_provider_router
from services.video_provider_base import VideoGenerationRequest, VideoPollResult, VideoSubmitResult


class _Provider:
    provider_name = "shopaikey_video"

    def __init__(self):
        self.submit_calls = 0
        self.poll_calls = 0

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
        }

    def submit_video_job(self, request):
        self.submit_calls += 1
        return VideoSubmitResult(
            ok=True,
            provider_name=self.provider_name,
            provider_task_id="shop-task-r7a",
            provider_status="in_progress",
            raw={"http_status": 200, "task_id_field_path": "data.id_base"},
        )

    def poll_video_job(self, provider_task_id):
        self.poll_calls += 1
        return VideoPollResult(ok=True, status="running", provider_task_id=provider_task_id)


def _request():
    return VideoGenerationRequest(
        job_id="79",
        product_type="video_trend",
        video_flow_type="video_trend",
        prompt="A real product video",
        ratio="9:16",
        duration_seconds=18,
        required_capability="text_to_video_or_scene_video",
        metadata={"product_video": True, "allow_provider_pending": True, "wallet_charge": False},
    )


def _env(**updates):
    data = {
        "VIDEO_PROVIDER_CHAIN": "shopaikey_video",
        "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1",
        "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS": "0",
    }
    data.update({key: str(value) for key, value in updates.items()})
    return data


def _run(monkeypatch, tmp_path, provider, *, env):
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [provider])
    return video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ=env,
        sleep_func=lambda _seconds: None,
    )


def _provider_alive_payload(**updates):
    payload = {
        "selected_provider": "shopaikey_video",
        "provider_router_called": True,
        "provider_submit_called": True,
        "submit_accepted": True,
        "provider_submit_http_status": 200,
        "provider_task_id_saved": True,
        "provider_task_ids": ["shop-task-r7a"],
        "provider_poll_called": True,
        "provider_status": "running",
        "normalized_provider_status": "running",
        "provider_error": "provider_in_progress",
        "blocker": "provider_in_progress",
        "continue_polling": True,
        "primary_provider_continue_polling": True,
        "primary_provider_task_alive": True,
        "primary_provider_task_id_present": True,
        "terminal_state": "final_rendering",
    }
    payload.update(updates)
    return payload


def _telemetry(payload):
    return video_project_queue.reconcile_provider_progress_telemetry(
        {
            "id": 79,
            "status": "processing",
            "progress_percent": 20,
            "started_at": "2026-07-05 10:00:00",
            "updated_at": "2026-07-05 10:00:00",
            "created_at": "2026-07-05 10:00:00",
        },
        payload,
        now=datetime(2026, 7, 5, 10, 0, 32),
        refresh_source="test",
    )


def test_kill_switch_false_blocks_before_any_provider_http(monkeypatch, tmp_path):
    provider = _Provider()
    result = _run(monkeypatch, tmp_path, provider, env=_env(PRODUCT_VIDEO_PROVIDER_SUBMIT_ENABLED="false"))

    assert provider.submit_calls == 0
    assert provider.poll_calls == 0
    assert result["provider_submit_called"] is False
    assert result["provider_submit_blocked_by_kill_switch"] is True
    assert result["external_provider_spend_prevented"] is True
    assert result["provider_task_id_saved"] is False
    assert result["charge"] == 0
    assert result["no_charge"] is True


def test_kill_switch_process_env_fallback_blocks_provider_config_payload(monkeypatch, tmp_path):
    monkeypatch.setenv("PRODUCT_VIDEO_PROVIDER_SUBMIT_ENABLED", "false")
    provider = _Provider()
    result = _run(monkeypatch, tmp_path, provider, env=_env())

    assert provider.submit_calls == 0
    assert result["product_video_provider_submit_enabled_raw"] == "false"
    assert result["product_video_provider_submit_enabled_resolved"] is False
    assert result["product_video_provider_submit_enabled_source"] == "process_env"
    assert result["kill_switch_checked_before_submit"] is True


def test_kill_switch_debug_shows_raw_resolved_source(monkeypatch, tmp_path):
    provider = _Provider()
    result = _run(monkeypatch, tmp_path, provider, env=_env(PRODUCT_VIDEO_PROVIDER_SUBMIT_ENABLED="no"))

    assert result["product_video_provider_submit_enabled_raw"] == "no"
    assert result["product_video_provider_submit_enabled_resolved"] is False
    assert result["product_video_provider_submit_enabled_source"] == "environ"
    assert result["provider_submit_blocked_by_kill_switch"] is True


def test_public_hides_poll_count_from_provider_attempts():
    block = bot.video_b14_provider_rendering_block(
        _telemetry(
            _provider_alive_payload(
                provider_progress_raw=200,
                provider_poll_count=13,
                provider_poll_count_source="provider_attempts",
            )
        )
    )

    assert "Đã kiểm tra" not in block
    assert "13 lần" not in block
    assert "Đang chờ kết quả dựng video" in block


def test_public_hides_poll_count_when_registry_missing_after_restart():
    block = bot.video_b14_provider_rendering_block(
        _telemetry(
            _provider_alive_payload(
                provider_progress_raw=200,
                provider_poll_count=13,
                provider_poll_count_source="provider_attempts",
                status_registry_missing_after_restart=True,
            )
        )
    )

    assert "Đã kiểm tra" not in block
    assert "Đã xử lý" not in block
    assert "Đã gửi yêu cầu dựng video." in block


def test_public_shows_poll_count_only_for_live_worker_source():
    block = bot.video_b14_provider_rendering_block(
        _telemetry(
            _provider_alive_payload(
                provider_progress_raw=12,
                provider_progress_percent=12,
                provider_poll_count=2,
                provider_poll_count_source="live_worker",
            )
        )
    )

    assert "Đã kiểm tra: <b>2 lần</b>" in block


def test_public_elapsed_hidden_when_registry_missing():
    block = bot.video_b14_provider_rendering_block(
        _telemetry(
            _provider_alive_payload(
                provider_progress_raw=200,
                status_registry_missing_after_restart=True,
            )
        )
    )

    assert "Đã xử lý" not in block
    assert "Đang chờ kết quả dựng video." in block


def test_elapsed_debug_source_present():
    telemetry = _telemetry(_provider_alive_payload(provider_progress_raw=200, status_registry_missing_after_restart=True))

    assert telemetry["elapsed_public_mode"] == "hidden"
    assert telemetry["elapsed_public_source"]
    assert telemetry["status_registry_missing_after_restart"] is True


def test_zero_waiting_public_copy_honest_short():
    block = bot.video_b14_provider_rendering_block(_telemetry(_provider_alive_payload(provider_progress_raw=200)))

    assert "<b>Dựng video:</b>" in block
    assert "▱▱▱▱▱▱▱▱▱▱ <b>0%</b>" in block
    assert "Đã gửi yêu cầu dựng video." in block
    assert "Đang chờ kết quả dựng video." in block
    assert "Đã xử lý" not in block
    assert "Đã kiểm tra" not in block


def test_video_debug_explains_zero_bar_reason():
    telemetry = _telemetry(_provider_alive_payload(provider_progress_raw=200))

    assert telemetry["provider_task_alive"] is True
    assert telemetry["provider_task_status"] == "running"
    assert telemetry["trusted_render_progress_available"] is False
    assert telemetry["why_render_bar_stays_zero"] == "provider_progress_untrusted_no_result_url"
    assert telemetry["result_url_present"] is False
