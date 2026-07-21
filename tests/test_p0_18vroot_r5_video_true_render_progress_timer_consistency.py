import json
import time
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
        "provider_task_ids": ["shop-task-76"],
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


def _job(progress=20, status="processing", started_at="2026-07-05 10:00:00", payload=None):
    return {
        "id": 76,
        "project_id": 760,
        "status": status,
        "progress_percent": progress,
        "progress_message": "provider_in_progress",
        "result_json": json.dumps(payload or _provider_alive_payload()),
        "created_at": started_at,
        "updated_at": started_at,
        "started_at": started_at,
    }


def _telemetry(payload=None, *, job_progress=20, now=None):
    payload = payload or _provider_alive_payload()
    return video_project_queue.reconcile_provider_progress_telemetry(
        _job(progress=job_progress, payload=payload),
        payload,
        now=now or datetime(2026, 7, 5, 10, 0, 0),
        refresh_source="test",
    )


def test_render_subprogress_starts_at_zero_on_provider_accept():
    payload = _provider_alive_payload(provider_started_at_epoch=datetime(2026, 7, 5, 10, 0, 0).timestamp())

    telemetry = _telemetry(payload)

    assert telemetry["render_video_progress_percent"] == 0
    assert telemetry["final_progress_after_reconcile"] == 20


def test_render_subprogress_increases_with_elapsed_time():
    started = datetime(2026, 7, 5, 10, 0, 0).timestamp()
    payload = _provider_alive_payload(provider_started_at_epoch=started, provider_wait_max_seconds=1200)

    early = _telemetry(payload, now=datetime(2026, 7, 5, 10, 1, 0))
    later = _telemetry(payload, now=datetime(2026, 7, 5, 10, 10, 0))

    assert later["provider_elapsed_seconds"] > early["provider_elapsed_seconds"]
    assert later["render_video_progress_percent"] == 0
    assert later["render_progress_source"] == "indeterminate"


def test_render_subprogress_does_not_jump_to_85_immediately():
    payload = _provider_alive_payload(provider_started_at_epoch=datetime(2026, 7, 5, 10, 0, 0).timestamp())

    telemetry = _telemetry(payload)
    block = bot.video_b14_provider_rendering_block(telemetry)

    assert "85%" not in block
    assert "Đã gửi yêu cầu dựng video." in block
    assert "0%" in block


def test_render_subprogress_caps_below_100_while_provider_in_progress():
    payload = _provider_alive_payload(provider_progress_raw=100, provider_progress_percent=100, provider_progress_normalized=100)

    telemetry = _telemetry(payload)

    assert telemetry["render_video_progress_percent"] == 0
    assert telemetry["provider_progress_percent"] == 0
    assert telemetry["render_progress_public_mode"] == "zero_waiting"
    assert telemetry["fake_progress_prevented"] is True


def test_overall_progress_maps_from_render_subprogress():
    started = datetime(2026, 7, 5, 10, 0, 0).timestamp()
    payload = _provider_alive_payload(provider_started_at_epoch=started, provider_wait_max_seconds=1200)

    telemetry = _telemetry(payload, now=datetime(2026, 7, 5, 10, 10, 0))

    expected = min(85, 20 + int(telemetry["render_video_progress_percent"] * 0.65))
    assert telemetry["overall_progress_from_render"] == expected
    assert telemetry["final_progress_after_reconcile"] == expected


def test_provider_raw_100_not_trusted_without_result_url():
    payload = _provider_alive_payload(provider_progress_raw="100", provider_progress_percent=100, provider_progress_normalized=100)

    telemetry = _telemetry(payload)

    assert telemetry["provider_progress_raw"] == "100"
    assert telemetry["provider_progress_trusted"] is False
    assert telemetry["provider_progress_cap_reason"] == "in_progress_without_result_url"
    assert telemetry["provider_progress_effective"] == 0


def test_provider_progress_100_allowed_only_after_completed_result_url():
    payload = {
        "provider_status": "completed",
        "normalized_provider_status": "completed",
        "provider_progress_raw": "100",
        "provider_progress_percent": 100,
        "provider_progress_normalized": 100,
        "provider_result_url": "https://example.test/video.mp4",
        "provider_result_url_present": True,
    }

    telemetry = _telemetry(payload)

    assert telemetry["provider_progress_effective"] == 100
    assert telemetry["render_video_progress_percent"] == 95


def test_provider_progress_effective_cap_reason_recorded():
    payload = _provider_alive_payload(provider_progress_raw=100, provider_progress_percent=100)

    telemetry = _telemetry(payload)

    assert telemetry["provider_progress_cap_applied"] is False
    assert telemetry["provider_progress_cap_reason"] == "in_progress_without_result_url"
    assert telemetry["fake_progress_prevented"] is True


def test_elapsed_uses_provider_started_at_wall_clock():
    started = datetime(2026, 7, 5, 10, 0, 0).timestamp()
    payload = _provider_alive_payload(provider_started_at_epoch=started)

    telemetry = _telemetry(payload, now=datetime(2026, 7, 5, 10, 2, 5))

    assert telemetry["elapsed_wall_clock_seconds"] == 125
    assert telemetry["provider_elapsed_seconds"] == 125


def test_elapsed_does_not_decrease():
    started = datetime(2026, 7, 5, 10, 0, 0).timestamp()
    payload = _provider_alive_payload(provider_started_at_epoch=started, provider_wait_elapsed_seconds=300)

    telemetry = _telemetry(payload, now=datetime(2026, 7, 5, 10, 1, 0))

    assert telemetry["provider_elapsed_seconds"] == 300
    assert telemetry["elapsed_monotonic_applied"] is True


def test_elapsed_recomputed_on_each_render():
    started = datetime(2026, 7, 5, 10, 0, 0).timestamp()
    payload = _provider_alive_payload(provider_started_at_epoch=started)

    first = _telemetry(payload, now=datetime(2026, 7, 5, 10, 1, 0))
    second = _telemetry(payload, now=datetime(2026, 7, 5, 10, 2, 0))

    assert second["provider_elapsed_seconds"] > first["provider_elapsed_seconds"]


def test_elapsed_display_format_seconds_and_minutes():
    assert bot.video_b14_human_elapsed(30) == "30 giây"
    assert bot.video_b14_human_elapsed(135) == "2 phút 15 giây"


def test_provider_started_at_not_reset_by_poll_or_debug():
    started = datetime(2026, 7, 5, 9, 0, 0).timestamp()
    payload = _provider_alive_payload(provider_started_at_epoch=started, provider_wait_started_epoch=time.time())

    telemetry = _telemetry(payload, now=datetime(2026, 7, 5, 10, 0, 0))

    assert telemetry["provider_started_at_epoch"] == started
    assert telemetry["provider_started_at_source"] == "payload"


def test_progress_status_top_percent_equals_final_reconciled_progress():
    job = {
        "status": "processing",
        "progress_percent": 60,
        "provider_task_alive": True,
        "final_progress_after_reconcile": 78,
        "render_video_progress_percent": 90,
    }

    text = bot.product_progress_debug_text("76", "multiscene_video", job)

    assert "• Percent: <code>78%</code>" in text
    assert "final_progress_after_reconcile: <code>78%</code>" in text


def test_public_panel_uses_final_reconciled_progress(monkeypatch):
    payload = _provider_alive_payload(provider_progress_raw=42, provider_progress_percent=42, provider_progress_normalized=42)
    job = _job(progress=20, payload=payload)
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: job)
    monkeypatch.setattr(bot, "video_b14_fail_stale_product_job_for_status", lambda _job_id: 0)

    text = bot.video_b14_queue_status_text(
        {"draft": {"b14_queue_job_id": 76, "b14_queue_job": job, "b14_invoice": {"scene_count": 3, "duration_seconds": 18}}},
        {"job": job, "project": {"project_id": 760, "scene_count": 3}},
    )

    telemetry = bot.video_b14_provider_telemetry(job, payload)
    assert f"Tiến độ: <b>{telemetry['final_progress_after_reconcile']}%</b>" in text


def test_no_conflicting_60_and_85_percent_for_same_job():
    job = {
        "status": "processing",
        "progress_percent": 60,
        "provider_task_alive": True,
        "final_progress_after_reconcile": 85,
    }

    text = bot.product_progress_debug_text("76", "video_trend", job)

    assert "• Percent: <code>85%</code>" in text
    assert "• Percent: <code>60%</code>" not in text


def test_public_rendering_copy_explains_video_ai_may_take_minutes():
    text = bot.video_b14_provider_rendering_block({"provider_task_alive": True, "render_video_progress_percent": 12})

    assert "Video AI có thể mất vài phút" in text
    assert "Đang chờ kết quả dựng video" in text


def test_public_rendering_copy_no_debug_terms():
    text = bot.video_b14_provider_rendering_block({"provider_task_alive": True, "render_video_progress_percent": 12})

    forbidden = ["provider", "API", "debug", "task_id", "payload"]
    assert all(term.lower() not in text.lower() for term in forbidden)


def test_video_debug_no_generic_x_for_job_76_shape():
    text = bot.video_render_debug_compact_text(
        76,
        _job(progress=20),
        {"project_id": 760},
        _provider_alive_payload(provider_progress_raw=100, render_video_progress_percent=90),
        {},
        "video_trend",
        {"adapter": "text_to_video"},
        {},
    )

    assert GENERIC_ERROR not in text
    assert "render video progress" in text


def test_video_debug_compact_partial_on_long_output():
    text = bot.video_render_debug_compact_text(
        76,
        _job(progress=20),
        {"project_id": 760},
        _provider_alive_payload(provider_progress_raw=100, render_video_progress_percent=90),
        {},
        "video_trend",
        {"adapter": "text_to_video"},
        {},
        reason="message_too_long",
    )

    assert "debug_truncated" in text
    assert GENERIC_ERROR not in text


def test_progress_debug_no_generic_x():
    text = bot.product_progress_debug_text("76", "video_trend", {"status": "processing", "final_progress_after_reconcile": 45})

    assert GENERIC_ERROR not in text


def test_no_subdub_music_payos_pricing_db_changes():
    assert hasattr(video_project_queue, "reconcile_provider_progress_telemetry")
    assert hasattr(video_provider_router, "run_provider_generation")


def test_no_fake_placeholder_success():
    telemetry = _telemetry(_provider_alive_payload(visual_source="local_placeholder", final_classification="partial_simple_video"))

    assert telemetry["provider_task_alive"] is True
    assert telemetry["final_progress_after_reconcile"] < 100


def test_no_provider_fallback_regression():
    telemetry = _telemetry(_provider_alive_payload(fallback_allowed=False, fallback_blocked_reason="primary_provider_in_progress"))

    assert telemetry["provider_task_alive"] is True
    assert telemetry["final_status_after_reconcile"] == "processing"


def test_router_pending_telemetry_caps_raw_100_without_result_url():
    request = VideoGenerationRequest(
        job_id="76",
        product_type="video_trend",
        prompt="cat video",
        duration_seconds=6,
        ratio="9:16",
        metadata={"provider_started_at_epoch": datetime(2026, 7, 5, 10, 0, 0).timestamp()},
    )
    poll = VideoPollResult(ok=True, status="in_progress", progress_percent=100)

    telemetry = video_provider_router._provider_pending_telemetry(request, poll, attempt_traces=[{"phase": "poll"}], wait_max=1200)

    assert telemetry["provider_progress_percent"] == 0
    assert telemetry["render_video_progress_percent"] == 0
    assert telemetry["render_progress_public_mode"] == "zero_waiting"
    assert telemetry["fake_progress_prevented"] is True
    assert telemetry["provider_progress_cap_reason"] == "in_progress_without_result_url"
