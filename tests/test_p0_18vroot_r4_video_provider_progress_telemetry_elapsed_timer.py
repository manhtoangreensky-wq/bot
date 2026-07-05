import json
import sqlite3
import time

import bot
from services import remote_worker_api, video_project_queue, video_provider_router
from services.video_provider_base import VideoArtifactResult, VideoGenerationRequest, VideoPollResult, VideoSubmitResult


def _provider_alive_payload(**updates):
    payload = {
        "selected_provider": "shopaikey_video",
        "provider_router_called": True,
        "provider_submit_called": True,
        "submit_accepted": True,
        "provider_submit_http_status": 200,
        "provider_task_id_saved": True,
        "provider_poll_called": True,
        "provider_task_ids": ["shop-task-75"],
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


def _panel_job(progress=65, status="queued", payload=None):
    return {
        "id": 75,
        "project_id": 750,
        "status": status,
        "progress_percent": progress,
        "progress_message": "provider_in_progress",
        "result_json": json.dumps(payload or _provider_alive_payload()),
        "created_at": "2026-07-05 08:00:00",
        "updated_at": "2026-07-05 08:15:00",
        "started_at": "2026-07-05 08:01:00",
    }


def _panel_project():
    return {
        "project_id": 750,
        "status": "processing",
        "video_terminal_state": "final_rendering",
        "scene_count": 3,
        "charged_xu": 0,
    }


def _create_project_job(conn: sqlite3.Connection, *, progress: int = 5, payload: dict | None = None):
    project = video_project_queue.create_video_project(
        conn,
        user_id=75,
        profile_id="video_trend",
        topic="trend video",
        asset_pack={
            "source": "product_video",
            "render_mode": "real",
            "provider_call": True,
            "product_type": "video_trend",
            "admin_only": True,
            "no_charge": True,
        },
    )
    video_project_queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="queued_for_worker",
        is_confirmed=1,
        total_xu_estimated=300,
        scene_count=3,
    )
    job = video_project_queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=75)
    if payload is not None or progress != 5:
        conn.execute(
            "UPDATE video_jobs SET result_json=?, progress_percent=?, progress_message=? WHERE id=?",
            (json.dumps(payload or {}), int(progress), "provider_in_progress", int(job["id"])),
        )
        conn.commit()
        job = video_project_queue.get_video_render_job(conn, int(job["id"]))
    return project, job


def test_product_video_progress_never_decreases():
    payload = _provider_alive_payload(provider_progress_percent=20)
    job = _panel_job(progress=65, payload=payload)
    telemetry = bot.video_b14_provider_telemetry(job, payload)

    assert telemetry["final_progress_after_reconcile"] == 65
    assert telemetry["progress_monotonic_applied"] is True


def test_provider_accepted_minimum_progress_20():
    payload = _provider_alive_payload()
    job = _panel_job(progress=5, payload=payload)

    telemetry = bot.video_b14_provider_telemetry(job, payload)

    assert telemetry["final_progress_after_reconcile"] >= 20
    assert telemetry["final_status_after_reconcile"] == "processing"


def test_refresh_after_provider_pending_does_not_reset_to_5(monkeypatch):
    payload = _provider_alive_payload(provider_progress_percent=20)
    job = _panel_job(progress=65, status="queued", payload=payload)
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: job)
    monkeypatch.setattr(bot, "video_b14_fail_stale_product_job_for_status", lambda _job_id: 0)

    text = bot.video_b14_queue_status_text(
        {"draft": {"b14_queue_job_id": 75, "b14_queue_job": job, "b14_invoice": {"scene_count": 3, "duration_seconds": 18}}},
        {"job": job, "project": _panel_project()},
        user_id=0,
    )

    assert "Tiến độ: <b>65%</b>" in text
    assert "Trạng thái: <b>Đang dựng video</b>" in text
    assert "Nhận yêu cầu" in text
    assert "received_request" not in text


def test_provider_raw_progress_used_when_available():
    payload = _provider_alive_payload(provider_progress_raw="42", provider_progress_normalized=42, provider_progress_percent=42)
    telemetry = bot.video_b14_provider_telemetry(_panel_job(progress=20, payload=payload), payload)

    assert telemetry["provider_progress_normalized"] == 42
    assert telemetry["render_video_progress_percent"] == 42
    assert telemetry["final_progress_after_reconcile"] == 47
    assert telemetry["provider_progress_estimated"] is False


def test_provider_progress_estimated_when_raw_missing():
    started = time.time() - 600
    payload = _provider_alive_payload(provider_started_at_epoch=started, provider_wait_max_seconds=1200)
    telemetry = bot.video_b14_provider_telemetry(_panel_job(progress=20, payload=payload), payload)

    assert telemetry["provider_progress_estimated"] is True
    assert 20 < telemetry["final_progress_after_reconcile"] < 85


def test_provider_progress_estimate_caps_below_final():
    started = time.time() - 7200
    payload = _provider_alive_payload(provider_started_at_epoch=started, provider_wait_max_seconds=1200)
    telemetry = bot.video_b14_provider_telemetry(_panel_job(progress=20, payload=payload), payload)

    assert telemetry["render_video_progress_percent"] == 90
    assert telemetry["final_progress_after_reconcile"] == 78


def test_provider_poll_count_displayed():
    payload = _provider_alive_payload(provider_poll_count=8, provider_elapsed_seconds=754, provider_progress_percent=38)
    block = bot.video_b14_provider_rendering_block(bot.video_b14_provider_telemetry(_panel_job(payload=payload), payload))

    assert "Đã kiểm tra: <b>8 lần</b>" in block
    assert "provider" not in block.lower()


def test_elapsed_seconds_displayed():
    payload = _provider_alive_payload(provider_started_at_epoch=time.time() - 754, provider_elapsed_seconds=754, provider_progress_percent=38)
    block = bot.video_b14_provider_rendering_block(bot.video_b14_provider_telemetry(_panel_job(payload=payload), payload))

    assert "12 phút 34 giây" in block


def test_elapsed_timer_uses_provider_started_at():
    started = time.time() - 754
    payload = _provider_alive_payload(provider_started_at_epoch=started, provider_wait_elapsed_seconds=0)
    telemetry = bot.video_b14_provider_telemetry(_panel_job(payload=payload), payload)

    assert telemetry["provider_elapsed_seconds"] >= 700
    assert telemetry["provider_started_at_source"] == "payload"


def test_provider_timeout_clean_failed_no_charge():
    payload = _provider_alive_payload(provider_started_at_epoch=time.time() - 1300, provider_wait_max_seconds=1200)
    telemetry = bot.video_b14_provider_telemetry(_panel_job(payload=payload), payload)

    assert telemetry["provider_wait_elapsed_seconds"] >= 1200
    assert payload["no_charge"] is True


def test_no_charge_on_provider_timeout():
    project = _panel_project()
    project["charged_xu"] = 0

    assert int(project["charged_xu"]) == 0


def test_public_provider_pending_copy_has_no_debug_terms(monkeypatch):
    payload = _provider_alive_payload(provider_poll_count=8, provider_elapsed_seconds=754, provider_progress_percent=38)
    job = _panel_job(progress=38, status="processing", payload=payload)
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: job)
    monkeypatch.setattr(bot, "video_b14_fail_stale_product_job_for_status", lambda _job_id: 0)

    text = bot.video_b14_queue_status_text(
        {"draft": {"b14_queue_job_id": 75, "b14_queue_job": job, "b14_invoice": {"scene_count": 3, "duration_seconds": 18}}},
        {"job": job, "project": _panel_project()},
        user_id=0,
    ).lower()

    for forbidden in ("provider", "api", "task id", "shopaikey", "key4u", "debug"):
        assert forbidden not in text
    assert "hệ thống" in text


def test_public_panel_says_self_update_when_rendering():
    text = bot.video_b14_provider_rendering_block({"provider_task_alive": True, "final_progress_after_reconcile": 42})

    assert "TOAN AAS sẽ tự cập nhật khi có video hoàn chỉnh." in text


def test_progress_status_uses_provider_alive_state_over_stale_registry(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    payload = _provider_alive_payload(provider_progress_percent=65)
    _project, job = _create_project_job(conn, progress=65, payload=payload)
    conn.execute("UPDATE video_jobs SET status='queued' WHERE id=?", (int(job["id"]),))
    conn.commit()
    monkeypatch.setattr(bot, "db_connect", lambda: conn)

    recovered, _ptype = bot._video_progress_debug_recover_job_from_db(str(job["id"]))

    assert recovered["status"] == "processing"
    assert recovered["stage"] == "generating_video"
    assert recovered["terminal_state"] == "final_rendering"
    assert recovered["provider_state_overrode_persisted_status"] is True


def test_progress_status_does_not_show_received_request_when_provider_running(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    payload = _provider_alive_payload(provider_progress_percent=65)
    _project, job = _create_project_job(conn, progress=65, payload=payload)
    monkeypatch.setattr(bot, "db_connect", lambda: conn)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {})

    text = bot.product_progress_debug_text(str(job["id"]))

    assert "generating_video" in text
    assert "received_request" not in text
    assert "final_progress_after_reconcile" in text


def test_persisted_queued_status_reconciled_to_final_rendering_when_task_alive():
    payload = _provider_alive_payload()
    telemetry = bot.video_b14_provider_telemetry(_panel_job(status="queued", progress=65, payload=payload), payload)

    assert telemetry["persisted_status_before_reconcile"] == "queued"
    assert telemetry["final_status_after_reconcile"] == "processing"
    assert telemetry["status_source_priority_used"] == "provider_task_alive"


def test_progress_uses_max_of_previous_and_persisted_progress():
    payload = _provider_alive_payload(provider_progress_percent=20)
    telemetry = bot.video_b14_provider_telemetry(_panel_job(progress=65, payload=payload), payload)

    assert telemetry["final_progress_after_reconcile"] == 65


def test_provider_wait_elapsed_does_not_reset_to_zero():
    started = time.time() - 900
    payload = _provider_alive_payload(provider_started_at_epoch=started, provider_wait_elapsed_seconds=0)
    telemetry = bot.video_b14_provider_telemetry(_panel_job(payload=payload), payload)

    assert telemetry["provider_wait_elapsed_seconds"] >= 850
    assert telemetry["provider_elapsed_estimated"] is False


def test_submit_summary_not_5xx_when_primary_task_accepted_200():
    payload = _provider_alive_payload(
        provider_submit_http_status=0,
        provider_submit_http_5xx=True,
        provider_attempts=[
            {"provider": "shopaikey_video", "phase": "poll", "submit_called": True, "submit_http_status": 200, "submit_accepted": True, "task_id_present": True, "poll_called": True, "normalized_status": "running", "continue_polling": True},
            {"provider": "key4u_video", "phase": "submit", "submit_called": True, "submit_http_status": 503, "blocker": "provider_temporarily_unavailable"},
        ],
    )
    result = bot.video_b14_reconciled_provider_debug(_panel_job(payload=payload), _panel_project(), payload)

    assert result["provider_submit_http_status"] == 200
    assert result["provider_submit_http_5xx"] is False
    assert result["summary_fields_from_primary_alive_task"] is True


def test_summary_ignores_stale_key4u_when_primary_shopaikey_alive():
    payload = _provider_alive_payload(
        provider_attempts=[
            {"provider": "shopaikey_video", "phase": "poll", "submit_http_status": 200, "submit_accepted": True, "task_id_present": True, "continue_polling": True, "normalized_status": "running"},
            {"provider": "key4u_video", "phase": "submit", "submit_http_status": 503, "blocker": "provider_temporarily_unavailable"},
        ],
    )
    result = bot.video_b14_reconciled_provider_debug(_panel_job(payload=payload), _panel_project(), payload)

    assert result["summary_provider_attempt_source"] == "shopaikey_video"
    assert result["stale_failed_attempt_ignored"] is True


def test_video_debug_includes_provider_progress_telemetry(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    payload = _provider_alive_payload(provider_progress_percent=38, provider_poll_count=8, provider_elapsed_seconds=754)
    _project, job = _create_project_job(conn, progress=38, payload=payload)
    monkeypatch.setattr(bot, "db_connect", lambda: conn)

    text = bot.video_provider_job_debug_text(int(job["id"]), conn=conn)

    assert "provider progress percent" in text
    assert "provider elapsed/max" in text
    assert "progress_monotonic_applied" in text


def test_video_debug_no_badrequest_with_progress_telemetry(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    payload = _provider_alive_payload(
        provider_progress_percent=38,
        provider_attempts=[
            {"provider": "shopaikey_video", "phase": "poll", "submit_http_status": 200, "submit_accepted": True, "task_id_present": True, "continue_polling": True, "safe_error": "in_progress " * 100}
            for _ in range(80)
        ],
    )
    _project, job = _create_project_job(conn, progress=38, payload=payload)
    monkeypatch.setattr(bot, "db_connect", lambda: conn)

    text = bot.video_provider_job_debug_text(int(job["id"]), conn=conn)

    assert "debug_reply_error" not in text
    assert len(text) <= bot.VIDEO_DEBUG_REPLY_LIMIT


def test_no_subdub_music_payos_pricing_db_changes():
    assert hasattr(bot, "video_b14_queue_status_text")
    assert hasattr(bot, "cmd_progress_status_debug")


def test_no_fake_placeholder_success():
    payload = _provider_alive_payload()

    assert payload.get("ok") is not True
    assert payload.get("visual_source") not in {"local_placeholder", "placeholder"}
    assert payload["no_charge"] is True


class _ProgressProvider:
    provider_name = "shopaikey_video"

    def capabilities(self):
        return {
            "provider": self.provider_name,
            "enabled": True,
            "configured": True,
            "capabilities": ["text_to_video", "scene_video", "multi_scene_video"],
            "endpoint_configured": True,
            "submit_url_configured": True,
            "poll_url_configured": True,
            "auth_configured": True,
            "model_configured": True,
        }

    def submit_video_job(self, request: VideoGenerationRequest):
        return VideoSubmitResult(ok=True, provider_name=self.provider_name, provider_task_id="shop-task-r4", provider_status="pending", raw={"submit_http_status": 200})

    def poll_video_job(self, provider_task_id: str):
        return VideoPollResult(
            ok=True,
            status="running",
            provider_name=self.provider_name,
            provider_task_id=provider_task_id,
            progress_percent=42,
            raw_status="running",
            raw={"poll_http_status": 200, "progress": 42, "provider_status_raw": "running"},
        )

    def materialize_result(self, result: VideoPollResult, job_id: str):
        return VideoArtifactResult(ok=False, error_code="pending_should_not_download")


def test_no_provider_logic_regression_for_in_progress_no_fallback(monkeypatch, tmp_path):
    provider = _ProgressProvider()
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [provider])

    result = video_provider_router.run_provider_generation(
        VideoGenerationRequest(
            job_id="75-1",
            product_type="video_trend",
            video_flow_type="video_trend",
            prompt="trend video",
            duration_seconds=6,
            metadata={"product_video": True, "allow_provider_pending": True, "provider_started_at_epoch": time.time() - 120},
            required_capability="text_to_video_or_scene_engine",
        ),
        output_dir=str(tmp_path),
        environ={"VIDEO_PROVIDER_CHAIN": "shopaikey_video", "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1", "PRODUCT_VIDEO_PROVIDER_MAX_WAIT_SECONDS": "1200"},
        sleep_func=lambda _seconds: None,
    )

    assert result["continue_polling"] is True
    assert result["fallback_allowed"] is False
    assert result["provider_progress_percent"] == 42
    assert result["provider_poll_count"] >= 1


def test_remote_worker_claim_preserves_provider_progress():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        payload = _provider_alive_payload(provider_progress_percent=65)
        _project, job = _create_project_job(conn, progress=65, payload=payload)
        claimed = remote_worker_api.claim_remote_worker_product_video_job(conn, worker_id="worker-r4", owner_only=True)

        assert claimed
        assert int(claimed["progress_percent"]) == 65
        assert claimed["progress_message"] == "provider_in_progress"
    finally:
        conn.close()
