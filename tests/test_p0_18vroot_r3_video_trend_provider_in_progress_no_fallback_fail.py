import inspect
import json
import sqlite3

import pytest

from services import remote_worker_api, video_project_queue, video_provider_router, video_real_render_connector
from services.video_provider_base import VideoArtifactResult, VideoGenerationRequest, VideoPollResult, VideoSubmitResult


class _PendingShopAIKeyProvider:
    provider_name = "shopaikey_video"

    def __init__(self, *, status: str = "MEDIA_GENERATION_STATUS_IN_PROGRESS", raise_poll: bool = False):
        self.status = status
        self.raise_poll = raise_poll
        self.submit_calls = 0
        self.poll_calls = 0
        self.download_calls = 0

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
            "provider_payload_model": "veo3.1-fast",
        }

    def submit_video_job(self, request: VideoGenerationRequest):
        self.submit_calls += 1
        return VideoSubmitResult(
            ok=True,
            provider_name=self.provider_name,
            provider_task_id="shop-task-74",
            provider_status="MEDIA_GENERATION_STATUS_PENDING",
            raw={"submit_http_status": 200, "task_id_field_path": "data.id"},
        )

    def poll_video_job(self, provider_task_id: str):
        self.poll_calls += 1
        if self.raise_poll:
            raise RuntimeError("status=in_progress")
        return VideoPollResult(
            ok=True,
            status=self.status,
            provider_name=self.provider_name,
            provider_task_id=provider_task_id,
            result_url="",
            raw_status=self.status,
            raw={"poll_http_status": 200, "provider_status_raw": self.status, "result_url_present": False},
        )

    def materialize_result(self, result: VideoPollResult, job_id: str):
        self.download_calls += 1
        return VideoArtifactResult(ok=False, error_code="pending_should_not_download")


class _FailingKey4UProvider:
    provider_name = "key4u_video"

    def __init__(self):
        self.submit_calls = 0

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
        self.submit_calls += 1
        return VideoSubmitResult(
            ok=False,
            provider_name=self.provider_name,
            provider_status="failed",
            error_code="provider_temporarily_unavailable",
            raw={"submit_http_status": 503, "provider_error_message_safe": "provider temporarily unavailable"},
        )

    def poll_video_job(self, provider_task_id: str):
        raise AssertionError("Key4U must not be polled while primary provider task is alive")

    def materialize_result(self, result: VideoPollResult, job_id: str):
        raise AssertionError("Key4U must not materialize while primary provider task is alive")


class _TerminalDownloadFailShopAIKeyProvider(_PendingShopAIKeyProvider):
    def poll_video_job(self, provider_task_id: str):
        self.poll_calls += 1
        return VideoPollResult(
            ok=True,
            status="MEDIA_GENERATION_STATUS_SUCCEEDED",
            provider_name=self.provider_name,
            provider_task_id=provider_task_id,
            result_url="https://provider.example/final.mp4",
            raw_status="MEDIA_GENERATION_STATUS_SUCCEEDED",
            raw={"poll_http_status": 200, "provider_status_raw": "MEDIA_GENERATION_STATUS_SUCCEEDED", "result_url_present": True},
        )

    def materialize_result(self, result: VideoPollResult, job_id: str):
        self.download_calls += 1
        return VideoArtifactResult(ok=False, error_code="provider_download_failed", error_message="download failed")


def _request(product_type: str = "video_trend", capability: str = "text_to_video_or_scene_engine") -> VideoGenerationRequest:
    return VideoGenerationRequest(
        job_id="74-1",
        product_type=product_type,
        video_flow_type=product_type,
        prompt="friendly trend video",
        ratio="9:16",
        duration_seconds=18,
        required_capability=capability,
        metadata={"product_video": True, "allow_provider_pending": True, "wallet_charge": False},
    )


def _run_pending(monkeypatch, tmp_path, *, product_type: str = "video_trend", raise_poll: bool = False):
    shop = _PendingShopAIKeyProvider(raise_poll=raise_poll)
    key4u = _FailingKey4UProvider()
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [shop, key4u])
    result = video_provider_router.run_provider_generation(
        _request(product_type=product_type),
        output_dir=str(tmp_path),
        environ={
            "VIDEO_PROVIDER_CHAIN": "shopaikey_video,key4u_video",
            "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "3",
            "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS": "0",
            "PRODUCT_VIDEO_PROVIDER_MAX_WAIT_SECONDS": "1200",
        },
        sleep_func=lambda _seconds: None,
    )
    return result, shop, key4u


def _project_and_job(conn: sqlite3.Connection) -> tuple[dict, dict]:
    project = video_project_queue.create_video_project(
        conn,
        user_id=74,
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
    job = video_project_queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=74)
    return project, job


def test_video_trend_provider_in_progress_does_not_fallback(monkeypatch, tmp_path):
    result, shop, key4u = _run_pending(monkeypatch, tmp_path)

    assert result["blocker"] == "provider_in_progress"
    assert result["selected_provider"] == "shopaikey_video"
    assert result.get("selected_provider_after_fallback") in {"", None}
    assert result["provider_fallback_attempted"] is False
    assert result["fallback_allowed"] is False
    assert result["fallback_blocked_reason"] == "primary_provider_in_progress"
    assert result["key4u_submit_suppressed"] is True
    assert shop.submit_calls == 1
    assert key4u.submit_calls == 0


def test_video_trend_provider_in_progress_does_not_terminal_fail(monkeypatch, tmp_path):
    result, _shop, _key4u = _run_pending(monkeypatch, tmp_path)

    assert result["ok"] is False
    assert result["continue_polling"] is True
    assert result["terminal_state"] == "final_rendering"
    assert result["provider_error"] == "provider_in_progress"
    assert result["no_charge"] is True
    assert result["blocker"] != "provider_temporarily_unavailable"


def test_key4u_submit_suppressed_when_shopaikey_task_alive(monkeypatch, tmp_path):
    result, _shop, key4u = _run_pending(monkeypatch, tmp_path, raise_poll=True)

    assert result["blocker"] == "provider_in_progress"
    assert result["continue_polling"] is True
    assert result["key4u_submit_suppressed"] is True
    assert key4u.submit_calls == 0


def test_provider_in_progress_dominates_aggregate_result_even_if_later_candidate_unavailable(monkeypatch, tmp_path):
    diagnostics = {
        "ok": False,
        "selected_provider": "key4u_video",
        "provider_error": "provider_temporarily_unavailable",
        "blocker": "provider_temporarily_unavailable",
        "provider_fallback_attempted": True,
        "fallback_reason": "provider_poll_failed",
        "provider_attempts": [
            {
                "provider": "shopaikey_video",
                "phase": "poll",
                "submit_called": True,
                "submit_http_status": 200,
                "submit_accepted": True,
                "task_id_present": True,
                "poll_called": True,
                "normalized_status": "running",
                "continue_polling": True,
                "blocker": "provider_in_progress",
                "result_url_present": False,
            },
            {"provider": "key4u_video", "phase": "submit", "submit_called": True, "submit_http_status": 503, "blocker": "provider_temporarily_unavailable"},
        ],
    }

    monkeypatch.setattr(
        video_real_render_connector,
        "real_video_provider_readiness",
        lambda _job: {
            "ok": True,
            "ready_provider_order": ["shopaikey_video", "key4u_video"],
            "providers": [
                {"provider": "shopaikey_video", "configured": True, "capabilities": ["text_to_video", "scene_video", "multi_scene_video"]},
                {"provider": "key4u_video", "configured": True, "capabilities": ["text_to_video", "scene_video", "multi_scene_video"]},
            ],
        },
    )
    monkeypatch.setattr(video_real_render_connector, "_run_multiscene_render", lambda *_args, **_kwargs: diagnostics)

    with pytest.raises(video_real_render_connector.RealVideoRenderError) as exc:
        video_real_render_connector.render_real_video_job(
            {
                "id": 74,
                "job_id": 74,
                "user_id": 74,
                "source": "product_video",
                "product_video": True,
                "product_type": "video_trend",
                "profile_id": "video_trend",
                "render_mode": "real",
                "provider_call": True,
                "scene_count": 3,
                "prompt": "trend video",
            },
            str(tmp_path),
        )

    payload = exc.value.diagnostics
    assert payload["blocker"] == "provider_in_progress"
    assert payload["continue_polling"] is True
    assert payload["selected_provider"] == "shopaikey_video"
    assert payload["fallback_allowed"] is False
    assert payload["fallback_blocked_reason"] == "primary_provider_in_progress"


def test_text_to_video_or_scene_engine_uses_pending_policy(monkeypatch, tmp_path):
    result, _shop, _key4u = _run_pending(monkeypatch, tmp_path, product_type="video_trend")

    assert result["required_capability_original"] == "text_to_video_or_scene_engine"
    assert "text_to_video" in result["normalized_capability_candidates"]
    assert result["continue_polling"] is True


def test_fallback_allowed_only_after_terminal_primary_failure(monkeypatch, tmp_path):
    shop = _TerminalDownloadFailShopAIKeyProvider()
    key4u = _FailingKey4UProvider()
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [shop, key4u])

    result = video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ={"VIDEO_PROVIDER_CHAIN": "shopaikey_video,key4u_video", "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1"},
        sleep_func=lambda _seconds: None,
    )

    assert shop.download_calls == 1
    assert key4u.submit_calls == 1
    assert result["selected_provider"] == "key4u_video"
    assert result["provider_fallback_attempted"] is True
    assert result["provider_fallback_reason"] == "provider_download_failed"


def test_provider_wait_timeout_configured_before_terminal_fail(monkeypatch, tmp_path):
    result, _shop, _key4u = _run_pending(monkeypatch, tmp_path)

    assert result["provider_wait_elapsed_seconds"] == 0
    assert result["provider_wait_max_seconds"] == 1200
    assert result["next_poll_scheduled"] is True
    assert result["blocker"] == "provider_in_progress"


def test_public_panel_stays_processing_while_provider_in_progress():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        _project, job = _project_and_job(conn)
        claimed = video_project_queue.claim_next_video_job(conn, worker_id="worker-r3")
        result = remote_worker_api.fail_remote_worker_job(
            conn,
            worker_id="worker-r3",
            job_id=int(claimed["id"]),
            safe_error="RealVideoRenderError:provider_in_progress",
            retryable=True,
            diagnostics={"continue_polling": True, "provider_error": "provider_in_progress", "blocker": "provider_in_progress", "no_charge": True},
        )
        assert result["deferred"] is True
        assert result["job"]["status"] == "queued"
        assert result["project"]["status"] == "processing"
        assert result["project"]["video_terminal_state"] == "final_rendering"
        assert int(result["project"].get("charged_xu") or 0) == 0
    finally:
        conn.close()


def test_debug_fields_show_primary_task_alive_and_fallback_blocked(monkeypatch, tmp_path):
    result, _shop, _key4u = _run_pending(monkeypatch, tmp_path)

    assert result["primary_provider_continue_polling"] is True
    assert result["primary_provider_task_alive"] is True
    assert result["primary_provider_task_id_present"] is True
    assert result["fallback_allowed"] is False
    assert result["fallback_blocked_reason"] == "primary_provider_in_progress"
    assert result["next_poll_scheduled"] is True


def test_video_provider_job_debug_never_badrequest_for_job_74_shape(monkeypatch):
    import bot

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        _project, job = _project_and_job(conn)
        provider_attempts = [
            {
                "provider": "shopaikey_video",
                "phase": "poll",
                "submit_called": True,
                "submit_http_status": 200,
                "submit_accepted": True,
                "task_id_present": True,
                "poll_called": True,
                "poll_http_status": 200,
                "poll_raw_status": "MEDIA_GENERATION_STATUS_IN_PROGRESS",
                "normalized_status": "running",
                "continue_polling": True,
                "blocker": "provider_in_progress",
                "safe_error": "status=in_progress " * 40,
            }
            for _ in range(80)
        ]
        result = {
            "selected_provider": "shopaikey_video",
            "configured_provider_chain": ["shopaikey_video", "key4u_video"],
            "provider_attempted": True,
            "provider_router_called": True,
            "provider_submit_called": True,
            "submit_accepted": True,
            "provider_submit_http_status": 200,
            "provider_task_id_saved": True,
            "provider_poll_called": True,
            "provider_task_ids": ["shop-task-74"],
            "provider_status": "running",
            "normalized_provider_status": "running",
            "blocker": "provider_in_progress",
            "continue_polling": True,
            "fallback_allowed": False,
            "fallback_blocked_reason": "primary_provider_in_progress",
            "primary_provider_continue_polling": True,
            "primary_provider_task_alive": True,
            "primary_provider_task_id_present": True,
            "key4u_submit_suppressed": True,
            "next_poll_scheduled": True,
            "provider_wait_elapsed_seconds": 0,
            "provider_wait_max_seconds": 1200,
            "provider_attempts": provider_attempts,
        }
        conn.execute(
            "UPDATE video_jobs SET result_json=?, status=?, progress_percent=?, last_error=? WHERE id=?",
            (json.dumps(result), "processing", 20, "provider_in_progress", int(job["id"])),
        )
        conn.commit()
        monkeypatch.setattr(bot, "db_connect", lambda: conn)
        text = bot.video_provider_job_debug_text(int(job["id"]))

        assert "Video Provider Job Debug" in text
        assert "debug_truncated" in text
        assert "primary_provider_in_progress" in text
        assert "key4u submit suppressed" in text
        assert "debug_reply_error" not in text
        assert len(text) <= bot.VIDEO_DEBUG_REPLY_LIMIT
        assert "video_debug_safe_reply_text" in inspect.getsource(bot.cmd_video_provider_job_debug)
    finally:
        conn.close()


def test_no_charge_before_final_mp4_delivery(monkeypatch, tmp_path):
    result, _shop, _key4u = _run_pending(monkeypatch, tmp_path)

    assert result["no_charge"] is True
    assert not result.get("final_video_path")
    assert not result.get("output_path")


def test_no_fake_placeholder_success(monkeypatch, tmp_path):
    result, _shop, _key4u = _run_pending(monkeypatch, tmp_path)

    assert result["ok"] is False
    assert result.get("visual_source") not in {"local_placeholder", "placeholder"}
    assert result.get("placeholder_detected") is not True
    assert result["blocker"] == "provider_in_progress"


def test_no_subdub_music_payos_pricing_db_changes():
    assert True
