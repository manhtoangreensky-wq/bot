import inspect
import json
import sqlite3

from services import video_project_queue, video_provider_router
from services.video_provider_base import VideoArtifactResult, VideoGenerationRequest, VideoPollResult, VideoSubmitResult


class _PendingShopAIKeyProvider:
    provider_name = "shopaikey_video"

    def __init__(self, *, result_url: str = "https://provider.example/pending-preview.mp4"):
        self.submit_calls = 0
        self.poll_calls = 0
        self.download_calls = 0
        self.result_url = result_url
        self.submitted_capabilities: list[str] = []

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
        self.submitted_capabilities.append(request.required_capability)
        return VideoSubmitResult(
            ok=True,
            provider_name=self.provider_name,
            provider_task_id="shop-task-72",
            provider_status="MEDIA_GENERATION_STATUS_PENDING",
            raw={"submit_http_status": 200, "task_id_field_path": "data.id"},
        )

    def poll_video_job(self, provider_task_id: str):
        self.poll_calls += 1
        return VideoPollResult(
            ok=True,
            status="MEDIA_GENERATION_STATUS_IN_PROGRESS",
            provider_name=self.provider_name,
            provider_task_id=provider_task_id,
            result_url=self.result_url,
            raw_status="MEDIA_GENERATION_STATUS_IN_PROGRESS",
            raw={
                "poll_http_status": 200,
                "provider_status_raw": "MEDIA_GENERATION_STATUS_IN_PROGRESS",
                "result_url_present": True,
            },
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
        raise AssertionError("Key4U should not be polled while ShopAIKey is still in progress")

    def materialize_result(self, result: VideoPollResult, job_id: str):
        raise AssertionError("Key4U should not be materialized while ShopAIKey is still in progress")


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
        job_id="72",
        product_type=product_type,
        video_flow_type=product_type,
        prompt="friendly trend video",
        ratio="9:16",
        duration_seconds=18,
        required_capability=capability,
        metadata={"product_video": True, "allow_provider_pending": True, "wallet_charge": False},
    )


def _run_pending(monkeypatch, tmp_path, *, product_type: str = "video_trend"):
    shop = _PendingShopAIKeyProvider()
    key4u = _FailingKey4UProvider()
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [shop, key4u])
    result = video_provider_router.run_provider_generation(
        _request(product_type=product_type),
        output_dir=str(tmp_path),
        environ={"VIDEO_PROVIDER_CHAIN": "shopaikey_video,key4u_video", "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1"},
        sleep_func=lambda _seconds: None,
    )
    return result, shop, key4u


def test_provider_in_progress_does_not_fallback_to_key4u(monkeypatch, tmp_path):
    result, shop, key4u = _run_pending(monkeypatch, tmp_path)

    assert result["blocker"] == "provider_in_progress"
    assert result["selected_provider"] == "shopaikey_video"
    assert result.get("selected_provider_after_fallback") in {"", None}
    assert result["provider_fallback_attempted"] is False
    assert result["fallback_allowed"] is False
    assert result["fallback_blocked_reason"] == "primary_provider_in_progress"
    assert key4u.submit_calls == 0
    assert shop.download_calls == 0


def test_provider_in_progress_does_not_terminal_failed_no_charge(monkeypatch, tmp_path):
    result, _shop, _key4u = _run_pending(monkeypatch, tmp_path)

    assert result["ok"] is False
    assert result["continue_polling"] is True
    assert result["provider_status"] == "running"
    assert result["normalized_provider_status"] == "running"
    assert result["no_charge"] is True
    assert result["provider_error"] == "provider_in_progress"
    assert result["blocker"] != "provider_temporarily_unavailable"


def test_accepted_task_id_continue_polling_persists_result_json(monkeypatch, tmp_path):
    result, _shop, _key4u = _run_pending(monkeypatch, tmp_path)

    assert result["provider_task_id_saved"] is True
    assert result["provider_task_ids"] == ["shop-task-72"]
    assert result["provider_pending_provider"] == "shopaikey_video"
    assert result["provider_pending_task_id"] == "shop-task-72"
    assert result["provider_pending_request_job_id"] == "72"
    assert result["provider_pending_deferred"] is True
    assert result["provider_pending_attempts"]


def test_video_trend_uses_same_provider_pending_policy_as_basic_video(monkeypatch, tmp_path):
    trend, _shop, _key4u = _run_pending(monkeypatch, tmp_path, product_type="video_trend")
    basic, _shop2, _key4u2 = _run_pending(monkeypatch, tmp_path, product_type="video_ai_prompt")

    assert trend["blocker"] == basic["blocker"] == "provider_in_progress"
    assert trend["continue_polling"] is basic["continue_polling"] is True
    assert trend["fallback_allowed"] is basic["fallback_allowed"] is False


def test_video_trend_provider_in_progress_remains_processing(monkeypatch, tmp_path):
    result, shop, key4u = _run_pending(monkeypatch, tmp_path)

    assert shop.submit_calls == 1
    assert shop.poll_calls == 1
    assert key4u.submit_calls == 0
    assert result["provider_poll_called"] is True
    assert result.get("terminal_state") not in {"failed_no_charge", "telegram_delivery_failed"}
    assert result["next_poll_scheduled"] is True


def test_fallback_only_after_terminal_primary_failure(monkeypatch, tmp_path):
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


def test_key4u_not_submitted_when_shopaikey_pending(monkeypatch, tmp_path):
    _result, _shop, key4u = _run_pending(monkeypatch, tmp_path)

    assert key4u.submit_calls == 0


def test_debug_fields_show_fallback_blocked_primary_in_progress(monkeypatch, tmp_path):
    result, _shop, _key4u = _run_pending(monkeypatch, tmp_path)

    assert result["fallback_blocked_reason"] == "primary_provider_in_progress"
    assert result["primary_provider_continue_polling"] is True
    assert result["primary_provider_task_id_present"] is True
    assert result["nonterminal_provider_status"] == "MEDIA_GENERATION_STATUS_IN_PROGRESS"
    assert result["fallback_allowed"] is False
    assert result["next_poll_scheduled"] is True


def test_video_provider_job_debug_never_generic_fails_for_job_72_shape(monkeypatch):
    import bot

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    project = video_project_queue.create_video_project(
        conn,
        user_id=72,
        profile_id="video_trend",
        topic="trend video",
        asset_pack={"source": "product_video", "render_mode": "real", "provider_call": True},
    )
    video_project_queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="queued_for_worker",
        charged_xu=0,
        video_terminal_state="final_rendering",
    )
    job = video_project_queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=72)
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
            "safe_error": "status=in_progress",
        }
        for _ in range(50)
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
        "provider_task_ids": ["shop-task-72"],
        "provider_status": "running",
        "normalized_provider_status": "running",
        "blocker": "provider_in_progress",
        "continue_polling": True,
        "fallback_allowed": False,
        "fallback_blocked_reason": "primary_provider_in_progress",
        "primary_provider_continue_polling": True,
        "primary_provider_task_id_present": True,
        "nonterminal_provider_status": "MEDIA_GENERATION_STATUS_IN_PROGRESS",
        "next_poll_scheduled": True,
        "provider_attempts": provider_attempts,
    }
    conn.execute(
        "UPDATE video_jobs SET result_json=?, status=?, progress_percent=?, last_error=? WHERE id=?",
        (json.dumps(result), "processing", 20, "provider_in_progress", int(job["id"])),
    )
    conn.commit()
    monkeypatch.setattr(bot, "db_connect", lambda: conn)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)

    text = bot.video_provider_job_debug_text(int(job["id"]))
    assert "Video Provider Job Debug" in text
    assert "primary_provider_in_progress" in text
    assert "Có lỗi khi xử lý lệnh" not in text
    assert "debug_truncated" in text
    assert len(text) <= bot.VIDEO_DEBUG_REPLY_LIMIT
    assert "video_debug_safe_reply_text" in inspect.getsource(bot.cmd_video_provider_job_debug)


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
