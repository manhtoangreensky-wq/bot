from services import video_provider_router
from services.video_provider_base import VideoArtifactResult, VideoGenerationRequest, VideoPollResult, VideoSubmitResult


class _PendingProvider:
    provider_name = "shopaikey_video"

    def capabilities(self):
        return {
            "provider": self.provider_name,
            "enabled": True,
            "configured": True,
            "capabilities": ["text_to_video"],
            "endpoint_configured": True,
            "submit_url_configured": True,
            "poll_url_configured": True,
            "auth_configured": True,
        }

    def submit_video_job(self, request):
        return VideoSubmitResult(
            ok=True,
            provider_name=self.provider_name,
            provider_task_id="shop-task-47",
            provider_status="MEDIA_GENERATION_STATUS_PENDING",
            raw={"http_status": 200, "task_id_field_path": "data.id"},
        )

    def poll_video_job(self, provider_task_id: str):
        return VideoPollResult(
            ok=True,
            status="MEDIA_GENERATION_STATUS_IN_PROGRESS",
            provider_name=self.provider_name,
            provider_task_id=provider_task_id,
            raw={"poll_http_status": 200, "provider_status_raw": "MEDIA_GENERATION_STATUS_IN_PROGRESS"},
        )

    def materialize_result(self, result, job_id: str):
        return VideoArtifactResult(ok=False, error_code="should_not_download_pending")


def _request(*, product_video: bool) -> VideoGenerationRequest:
    metadata = {"wallet_charge": False}
    if product_video:
        metadata.update({"product_video": True, "allow_provider_pending": True})
    return VideoGenerationRequest(
        job_id="job-47",
        product_type="video_ai_prompt",
        video_flow_type="video_ai_prompt",
        prompt="A real AI product video",
        ratio="9:16",
        duration_seconds=4,
        required_capability="text_to_video",
        metadata=metadata,
    )


def test_shopaikey_in_progress_keeps_provider_job_non_terminal(monkeypatch, tmp_path):
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [_PendingProvider()])
    env = {"VIDEO_PROVIDER_CHAIN": "shopaikey_video", "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1"}

    result = video_provider_router.run_provider_generation(
        _request(product_video=True),
        output_dir=str(tmp_path),
        environ=env,
        sleep_func=lambda _seconds: None,
    )

    assert result["ok"] is False
    assert result["provider_router_called"] is True
    assert result["provider_attempted"] is True
    assert result["provider_submit_called"] is True
    assert result["provider_task_id_saved"] is True
    assert result["provider_poll_called"] is True
    assert result["provider_task_ids"] == ["shop-task-47"]
    assert result["blocker"] == "provider_in_progress"
    assert result["continue_polling"] is True
    assert result["normalized_provider_status"] == "running"
    assert not result.get("output_path")
    assert result["no_charge"] is True


def test_non_product_smoke_pending_keeps_timeout_semantics(monkeypatch, tmp_path):
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [_PendingProvider()])
    env = {"VIDEO_PROVIDER_CHAIN": "shopaikey_video", "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1"}

    result = video_provider_router.run_provider_generation(
        _request(product_video=False),
        output_dir=str(tmp_path),
        environ=env,
        sleep_func=lambda _seconds: None,
    )

    assert result["ok"] is False
    assert result["blocker"] == "provider_timeout"
    assert result.get("continue_polling") is not True
