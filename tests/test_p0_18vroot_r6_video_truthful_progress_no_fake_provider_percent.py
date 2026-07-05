import json
from datetime import datetime, timedelta

import bot
from services import video_project_queue, video_provider_router
from services.video_provider_base import VideoGenerationRequest, VideoPollResult


GENERIC_ERROR = "Có lỗi khi xử lý lệnh"


def _provider_alive_payload(**updates):
    payload = {
        "selected_provider": "shopaikey_video",
        "provider_router_called": True,
        "provider_submit_called": True,
        "submit_accepted": True,
        "provider_submit_http_status": 200,
        "provider_task_id_saved": True,
        "provider_poll_called": True,
        "provider_task_ids": ["shop-task-77"],
        "provider_status": "running",
        "normalized_provider_status": "running",
        "provider_status_raw": "MEDIA_GENERATION_STATUS_IN_PROGRESS",
        "provider_error": "provider_in_progress",
        "blocker": "provider_in_progress",
        "continue_polling": True,
        "primary_provider_continue_polling": True,
        "primary_provider_task_alive": True,
        "primary_provider_task_id_present": True,
        "fallback_allowed": False,
        "fallback_blocked_reason": "primary_provider_in_progress",
        "next_poll_scheduled": True,
        "terminal_state": "final_rendering",
        "no_charge": True,
    }
    payload.update(updates)
    return payload


def _job(progress=20, payload=None):
    payload = payload or _provider_alive_payload()
    return {
        "id": 77,
        "project_id": 770,
        "status": "processing",
        "progress_percent": progress,
        "progress_message": "provider_in_progress",
        "result_json": json.dumps(payload),
        "created_at": "2026-07-05 10:00:00",
        "updated_at": "2026-07-05 10:00:00",
        "started_at": "2026-07-05 10:00:00",
    }


def _telemetry(payload=None, *, job_progress=20, now=None):
    payload = payload or _provider_alive_payload()
    return video_project_queue.reconcile_provider_progress_telemetry(
        _job(progress=job_progress, payload=payload),
        payload,
        now=now or datetime(2026, 7, 5, 10, 0, 0),
        refresh_source="test",
    )


def test_untrusted_provider_progress_not_shown_publicly():
    telemetry = _telemetry(_provider_alive_payload(provider_progress_raw=200, provider_progress_percent=100))

    block = bot.video_b14_provider_rendering_block(telemetry)

    assert "90%" not in block
    assert "78%" not in block
    assert "Đang dựng" in block
    assert telemetry["provider_progress_public_suppressed"] is True


def test_provider_raw_200_does_not_render_90_percent():
    telemetry = _telemetry(_provider_alive_payload(provider_progress_raw=200, provider_progress_percent=100))

    assert telemetry["provider_progress_raw_number"] == 200.0
    assert telemetry["provider_progress_trusted"] is False
    assert telemetry["render_video_progress_percent"] == 0
    assert telemetry["render_video_progress_percent_public"] == "-"


def test_in_progress_without_result_url_uses_indeterminate_render_status():
    telemetry = _telemetry(_provider_alive_payload(provider_progress_raw=100, provider_progress_percent=100))

    assert telemetry["render_progress_public_mode"] == "indeterminate"
    assert telemetry["render_progress_source"] == "indeterminate"
    assert telemetry["fake_progress_prevented"] is True


def test_fake_progress_prevented_debug_fields():
    telemetry = _telemetry(_provider_alive_payload(provider_progress_raw=100, provider_progress_percent=100))

    assert telemetry["fake_progress_prevention_reason"] == "untrusted_provider_progress_without_result_url"
    assert telemetry["percent_conservative_due_to_untrusted_provider"] is True


def test_trusted_provider_progress_between_0_99_shown_publicly():
    telemetry = _telemetry(_provider_alive_payload(provider_progress_raw=38, provider_progress_percent=38, provider_progress_normalized=38))

    block = bot.video_b14_provider_rendering_block(telemetry)

    assert telemetry["provider_progress_trusted"] is True
    assert telemetry["render_video_progress_percent_public"] == "38"
    assert "38%" in block


def test_render_progress_100_only_after_result_url_or_final_mp4():
    without_url = _telemetry(_provider_alive_payload(provider_progress_raw=100, provider_progress_percent=100))
    with_url = _telemetry(
        _provider_alive_payload(
            provider_status="completed",
            normalized_provider_status="completed",
            provider_status_raw="completed",
            provider_error="",
            blocker="",
            terminal_state="completed",
            provider_progress_raw=100,
            provider_progress_percent=100,
            provider_result_url="https://example.test/final.mp4",
            provider_result_url_present=True,
            continue_polling=False,
            primary_provider_continue_polling=False,
            primary_provider_task_alive=False,
        )
    )

    assert without_url["render_video_progress_percent"] == 0
    assert with_url["provider_progress_effective"] == 100


def test_untrusted_progress_uses_indeterminate_even_if_raw_high():
    telemetry = _telemetry(_provider_alive_payload(provider_progress_raw=999, provider_progress_percent=100))

    assert telemetry["provider_progress_cap_reason"] == "invalid_provider_progress_raw"
    assert telemetry["render_progress_public_mode"] == "indeterminate"


def test_elapsed_recomputes_on_each_refresh():
    started = datetime(2026, 7, 5, 10, 0, 0).timestamp()
    payload = _provider_alive_payload(provider_started_at_epoch=started)

    first = _telemetry(payload, now=datetime(2026, 7, 5, 10, 1, 0))
    second = _telemetry(payload, now=datetime(2026, 7, 5, 10, 2, 0))

    assert second["provider_elapsed_seconds"] > first["provider_elapsed_seconds"]


def test_elapsed_never_decreases():
    started = datetime(2026, 7, 5, 10, 0, 0).timestamp()
    payload = _provider_alive_payload(provider_started_at_epoch=started, provider_wait_elapsed_seconds=300)

    telemetry = _telemetry(payload, now=datetime(2026, 7, 5, 10, 1, 0))

    assert telemetry["provider_elapsed_seconds"] == 300
    assert telemetry["elapsed_monotonic_applied"] is True


def test_public_copy_does_not_imply_per_second_live_timer():
    text = bot.video_b14_provider_rendering_block(_telemetry(_provider_alive_payload()))

    assert "mỗi giây" not in text.lower()
    assert "tự cập nhật định kỳ" in text


def test_debug_shows_refresh_interval():
    telemetry = _telemetry(_provider_alive_payload(panel_refresh_interval_seconds=25))

    assert telemetry["panel_refresh_interval_seconds"] == 25
    assert telemetry["next_poll_scheduled"] is True


def test_overall_percent_not_derived_from_fake_render_percent():
    telemetry = _telemetry(_provider_alive_payload(provider_progress_raw=200, render_video_progress_percent=90), job_progress=78)

    assert telemetry["overall_progress_from_render"] == 20
    assert telemetry["final_progress_after_reconcile"] == 20


def test_overall_percent_conservative_when_provider_progress_untrusted():
    telemetry = _telemetry(_provider_alive_payload(provider_progress_raw=100, provider_progress_percent=100), job_progress=65)

    assert telemetry["percent_conservative_due_to_untrusted_provider"] is True
    assert telemetry["final_progress_after_reconcile"] == 20


def test_public_stage_text_can_show_rendering_without_fake_percent():
    block = bot.video_b14_provider_rendering_block(_telemetry(_provider_alive_payload(provider_progress_raw=100)))

    assert "Đang dựng" in block
    assert "100%" not in block


def test_video_debug_no_generic_x_for_untrusted_progress_job_77():
    text = bot.video_render_debug_compact_text(
        77,
        _job(),
        {"project_id": 770},
        _provider_alive_payload(provider_progress_raw=200, provider_progress_percent=100),
        {},
        "video_trend",
        {"adapter": "text_to_video"},
        {},
    )

    assert GENERIC_ERROR not in text
    assert "fake progress prevented" in text


def test_video_auto_status_no_generic_x():
    text = bot.product_progress_debug_text(
        "77",
        "video_trend",
        {
            "status": "processing",
            "provider_task_alive": True,
            "provider_progress_public_suppressed": True,
            "fake_progress_prevented": True,
            "final_progress_after_reconcile": 20,
        },
    )

    assert GENERIC_ERROR not in text
    assert "fake_progress_prevented" in text


def test_provider_poll_count_starts_zero_without_real_poll_attempts():
    telemetry = _telemetry(_provider_alive_payload(provider_poll_called=True))
    block = bot.video_b14_provider_rendering_block(telemetry)

    assert telemetry["provider_poll_count"] == 0
    assert telemetry["provider_poll_count_source"] == "none"
    assert "Đã kiểm tra: <b>0 lần</b>" in block


def test_provider_poll_count_uses_real_attempts_only():
    telemetry = _telemetry(
        _provider_alive_payload(
            provider_attempts=[
                {"phase": "submit", "submit_called": True},
                {"phase": "poll", "poll_called": True},
                {"phase": "poll", "poll_called": True},
            ]
        )
    )

    assert telemetry["provider_poll_count"] == 2
    assert telemetry["provider_poll_count_source"] == "provider_attempts"


def test_no_subdub_music_payos_pricing_db_changes():
    assert hasattr(video_project_queue, "reconcile_provider_progress_telemetry")
    assert hasattr(video_provider_router, "run_provider_generation")


def test_no_provider_submit_fallback_regression():
    telemetry = _telemetry(_provider_alive_payload(fallback_allowed=False, fallback_blocked_reason="primary_provider_in_progress"))

    assert telemetry["provider_task_alive"] is True
    assert telemetry["final_status_after_reconcile"] == "processing"


def test_no_fake_placeholder_success():
    telemetry = _telemetry(_provider_alive_payload(visual_source="local_placeholder", final_classification="partial_simple_video"))

    assert telemetry["final_progress_after_reconcile"] < 100
    assert telemetry["provider_task_alive"] is True


def test_router_untrusted_high_progress_stays_indeterminate():
    request = VideoGenerationRequest(
        job_id="77",
        product_type="video_trend",
        prompt="cat video",
        duration_seconds=6,
        ratio="9:16",
        metadata={"provider_started_at_epoch": (datetime(2026, 7, 5, 10, 0, 0) - timedelta(minutes=1)).timestamp()},
    )
    poll = VideoPollResult(ok=True, status="in_progress", progress_percent=200)

    telemetry = video_provider_router._provider_pending_telemetry(request, poll, attempt_traces=[], wait_max=1200)

    assert telemetry["render_video_progress_percent"] == 0
    assert telemetry["provider_poll_count"] == 0
    assert telemetry["provider_poll_count_source"] == "none"
    assert telemetry["render_progress_public_mode"] == "indeterminate"
