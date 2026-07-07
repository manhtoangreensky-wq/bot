from datetime import datetime

import bot
from services import video_project_queue, video_provider_router
from services.video_provider_base import VideoGenerationRequest, VideoPollResult


def _provider_alive_payload(**updates):
    payload = {
        "selected_provider": "shopaikey_video",
        "provider_router_called": True,
        "provider_submit_called": True,
        "submit_accepted": True,
        "provider_submit_http_status": 200,
        "provider_task_id_saved": True,
        "provider_poll_called": True,
        "provider_task_ids": ["shop-task-r6a"],
        "provider_status": "running",
        "normalized_provider_status": "running",
        "provider_error": "provider_in_progress",
        "blocker": "provider_in_progress",
        "continue_polling": True,
        "primary_provider_continue_polling": True,
        "primary_provider_task_alive": True,
        "primary_provider_task_id_present": True,
        "fallback_allowed": False,
        "fallback_blocked_reason": "primary_provider_in_progress",
        "terminal_state": "final_rendering",
        "no_charge": True,
    }
    payload.update(updates)
    return payload


def _job(payload, progress=20):
    return {
        "id": 78,
        "status": "processing",
        "progress_percent": progress,
        "result_json": "{}",
        "created_at": "2026-07-05 10:00:00",
        "updated_at": "2026-07-05 10:00:00",
        "started_at": "2026-07-05 10:00:00",
        "payload": payload,
    }


def _telemetry(payload, *, progress=20):
    return video_project_queue.reconcile_provider_progress_telemetry(
        _job(payload, progress=progress),
        payload,
        now=datetime(2026, 7, 5, 10, 1, 0),
        refresh_source="test",
    )


def test_untrusted_provider_progress_shows_zero_public_render_bar():
    telemetry = _telemetry(_provider_alive_payload(provider_progress_raw=100, provider_progress_percent=100), progress=78)
    block = bot.video_b14_provider_rendering_block(telemetry)

    assert telemetry["render_progress_public_mode"] == "zero_waiting"
    assert telemetry["render_video_progress_percent_public"] == "0"
    assert "▱▱▱▱▱▱▱▱▱▱ <b>0%</b>" in block
    assert "Đã gửi yêu cầu dựng video, đang chờ kết quả." in block
    assert "Hệ thống đang dựng video" in block
    assert "78%" not in block
    assert "90%" not in block


def test_provider_raw_200_public_bar_is_zero_not_hidden_not_90():
    telemetry = _telemetry(_provider_alive_payload(provider_progress_raw=200, provider_progress_percent=100), progress=85)
    block = bot.video_b14_provider_rendering_block(telemetry)

    assert telemetry["public_zero_bar_due_to_untrusted_provider"] is True
    assert telemetry["fake_progress_prevented"] is True
    assert telemetry["render_video_progress_percent_public"] == "0"
    assert "0%" in block
    assert "85%" not in block
    assert "90%" not in block


def test_untrusted_progress_does_not_move_public_bar_above_zero():
    telemetry = _telemetry(_provider_alive_payload(provider_progress_raw=999, provider_progress_percent=100), progress=65)

    assert telemetry["provider_progress_trusted"] is False
    assert telemetry["final_progress_after_reconcile"] == 20
    assert telemetry["render_video_progress_percent_public"] == "0"


def test_trusted_progress_moves_public_bar():
    telemetry = _telemetry(_provider_alive_payload(provider_progress_raw=12, provider_progress_percent=12), progress=20)
    block = bot.video_b14_provider_rendering_block(telemetry)

    assert telemetry["provider_progress_trusted"] is True
    assert telemetry["render_progress_public_mode"] == "percent"
    assert telemetry["render_video_progress_percent_public"] == "12"
    assert "12%" in block


def test_result_url_allows_transition_out_of_zero_waiting():
    telemetry = _telemetry(
        _provider_alive_payload(
            provider_progress_raw=100,
            provider_progress_percent=100,
            provider_result_url="https://example.test/video.mp4",
            provider_result_url_present=True,
            result_url_present=True,
            provider_status="completed",
            normalized_provider_status="completed",
            continue_polling=False,
        ),
        progress=20,
    )

    assert telemetry["render_progress_public_mode"] == "percent"
    assert telemetry["render_video_progress_percent_public"] != "0"


def test_public_render_copy_short_no_internal_terms():
    block = bot.video_b14_provider_rendering_block(_telemetry(_provider_alive_payload(provider_progress_raw=100)))

    assert "provider" not in block.lower()
    assert "api" not in block.lower()
    assert "debug" not in block.lower()
    assert "payload" not in block.lower()
    assert "TOAN AAS sẽ tự cập nhật khi có video hoàn chỉnh." in block


def test_public_hides_poll_count_when_source_payload():
    block = bot.video_b14_provider_rendering_block(
        _telemetry(_provider_alive_payload(provider_poll_count=13, provider_poll_count_source="payload"))
    )

    assert "đang chờ kết quả" in block
    assert "13 lần" not in block


def test_public_shows_poll_count_only_when_internal_worker_source_and_progress_trusted():
    block = bot.video_b14_provider_rendering_block(
        _telemetry(
            _provider_alive_payload(
                provider_progress_raw=12,
                provider_progress_percent=12,
                provider_poll_count=2,
                provider_poll_count_source="internal_worker",
            )
        )
    )

    assert "Đã kiểm tra" not in block
    assert "2 lần" not in block
    assert "Hệ thống đang dựng video" in block


def test_router_pending_telemetry_uses_zero_waiting_debug_fields():
    request = VideoGenerationRequest(
        job_id="r6a",
        product_type="video_trend",
        video_flow_type="video_trend",
        prompt="cat video",
        duration_seconds=6,
        ratio="9:16",
        metadata={"product_video": True, "allow_provider_pending": True},
    )
    poll = VideoPollResult(ok=True, status="in_progress", progress_percent=100)

    telemetry = video_provider_router._provider_pending_telemetry(request, poll, attempt_traces=[], wait_max=1200)

    assert telemetry["render_video_progress_percent"] == 0
    assert telemetry["render_video_progress_percent_public"] == "0"
    assert telemetry["render_progress_public_mode"] == "zero_waiting"
    assert telemetry["public_zero_bar_due_to_untrusted_provider"] is True
    assert telemetry["provider_progress_public_suppressed"] is True
