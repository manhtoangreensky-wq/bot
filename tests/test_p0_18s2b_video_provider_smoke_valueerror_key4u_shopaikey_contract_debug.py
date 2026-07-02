from pathlib import Path

import bot
from providers import video_generic_http_provider as generic
from providers.video_generic_http_provider import GenericHttpVideoProvider, VideoProviderContractError
from services import video_provider_router
from services.video_provider_base import VideoArtifactResult, VideoGenerationRequest, VideoPollResult, VideoSubmitResult


def _env(provider: str = "key4u_video") -> dict[str, str]:
    if provider == "shopaikey_video":
        return {
            "SHOPAIKEY_VIDEO_ENABLED": "1",
            "SHOPAIKEY_VIDEO_SUBMIT_URL": "https://video-provider.invalid/submit?token=secret",
            "SHOPAIKEY_VIDEO_POLL_URL": "https://video-provider.invalid/poll/{task_id}?token=secret",
            "SHOPAIKEY_VIDEO_AUTH_HEADER_NAME": "Authorization",
            "SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE": "Bearer secret",
        }
    return {
        "KEY4U_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_SUBMIT_URL": "https://video-provider.invalid/submit?token=secret",
        "KEY4U_VIDEO_POLL_URL": "https://video-provider.invalid/poll/{task_id}?token=secret",
        "KEY4U_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer secret",
    }


def _provider(provider: str = "key4u_video") -> GenericHttpVideoProvider:
    if provider == "shopaikey_video":
        return video_provider_router._generic_adapter_for("shopaikey_video", _env("shopaikey_video"))
    return video_provider_router._generic_adapter_for("key4u_video", _env("key4u_video"))


def _request(**overrides) -> VideoGenerationRequest:
    data = {
        "job_id": "smoke",
        "product_type": "video_ai_prompt",
        "video_flow_type": "video_ai_prompt",
        "prompt": "Short vertical product video",
        "ratio": "9:16",
        "duration_seconds": 4,
        "quality": "basic",
        "metadata": {"admin_smoke": True, "wallet_charge": False},
        "required_capability": "text_to_video",
    }
    data.update(overrides)
    return VideoGenerationRequest(**data)


def test_smoke_does_not_return_raw_valueerror_only():
    result = video_provider_router.provider_exception_result(ValueError("bad body token=secret"), provider="key4u_video", stage="submit_response_parse")
    text = bot.video_provider_smoke_debug_text("key4u_video", "text_to_video", result)
    assert "ValueError" in text
    assert "smoke_stage" in text
    assert "provider_unhandled_exception" in text
    assert "token=secret" not in text


def test_valueerror_payload_stage_classified():
    exc = VideoProviderContractError("provider_payload_missing_prompt", stage="payload_build", debug={"payload_has_prompt": False})
    result = video_provider_router.provider_exception_result(exc, provider="key4u_video", stage="payload_build")
    assert result["blocker"] == "provider_payload_missing_prompt"
    assert result["smoke_stage"] == "payload_build"


def test_missing_prompt_blocker():
    try:
        generic.build_key4u_video_payload(_request(prompt=""), _env())
    except VideoProviderContractError as exc:
        assert exc.blocker == "provider_payload_missing_prompt"
    else:
        raise AssertionError("missing prompt should fail")


def test_missing_duration_blocker():
    try:
        generic.build_key4u_video_payload(_request(duration_seconds=None), _env())
    except VideoProviderContractError as exc:
        assert exc.blocker == "provider_payload_missing_duration"
    else:
        raise AssertionError("missing duration should fail")


def test_missing_ratio_blocker():
    try:
        generic.build_key4u_video_payload(_request(ratio=""), _env())
    except VideoProviderContractError as exc:
        assert exc.blocker == "provider_payload_missing_ratio"
    else:
        raise AssertionError("missing ratio should fail")


def test_submit_response_task_id_top_level(monkeypatch):
    provider = _provider("key4u_video")
    monkeypatch.setattr(provider, "_open_json", lambda *_a, **_k: {"ok": True, "status_code": 200, "body": {"task_id": "task-1", "status": "pending"}})
    result = provider.submit_video_job(_request())
    assert result.ok is True
    assert result.provider_task_id == "task-1"
    assert result.raw["task_id_field_path"] == "task_id"


def test_submit_response_task_id_nested_data(monkeypatch):
    provider = _provider("shopaikey_video")
    monkeypatch.setattr(provider, "_open_json", lambda *_a, **_k: {"ok": True, "status_code": 200, "body": {"data": {"id": "task-2", "status": "pending"}}})
    result = provider.submit_video_job(_request())
    assert result.ok is True
    assert result.provider_task_id == "task-2"
    assert result.raw["task_id_field_path"] == "data.id"


def test_submit_response_missing_task_id_blocker(monkeypatch):
    provider = _provider("key4u_video")
    monkeypatch.setattr(provider, "_open_json", lambda *_a, **_k: {"ok": True, "status_code": 200, "body": {"status": "pending"}})
    result = provider.submit_video_job(_request())
    assert result.ok is False
    assert result.error_code == "provider_task_id_missing"
    assert result.raw["provider_submit_blocker"] == "provider_task_id_missing"


def test_poll_status_normalized_success(monkeypatch):
    provider = _provider("key4u_video")
    monkeypatch.setattr(provider, "_open_json", lambda *_a, **_k: {"ok": True, "status_code": 200, "body": {"status": "MEDIA_GENERATION_STATUS_SUCCEEDED", "download_url": "https://cdn.example/video.mp4"}})
    result = provider.poll_video_job("task-1")
    assert result.ok is True
    assert result.status == "succeeded"
    assert result.result_url.endswith(".mp4")


def test_poll_status_normalized_running(monkeypatch):
    provider = _provider("key4u_video")
    monkeypatch.setattr(provider, "_open_json", lambda *_a, **_k: {"ok": True, "status_code": 200, "body": {"state": "MEDIA_GENERATION_STATUS_PENDING"}})
    result = provider.poll_video_job("task-1")
    assert result.ok is True
    assert result.status == "queued"


def test_poll_status_unknown_blocker(monkeypatch):
    provider = _provider("key4u_video")
    monkeypatch.setattr(provider, "_open_json", lambda *_a, **_k: {"ok": True, "status_code": 200, "body": {"status": "WEIRD_STATE"}})
    result = provider.poll_video_job("task-1")
    assert result.ok is False
    assert result.error_code == "provider_status_unknown"
    assert result.raw["provider_poll_blocker"] == "provider_status_unknown"


def test_result_url_nested_extracted():
    url, path = generic.parse_result_url({"result": {"download_url": "https://cdn.example/final.mp4"}})
    assert url.endswith("final.mp4")
    assert path == "result.download_url"


def test_result_url_missing_blocker():
    url, path = generic.parse_result_url({"thumbnail": "https://cdn.example/frame.jpg"})
    assert url == ""
    assert path == ""


def test_smoke_debug_masks_auth_and_url_tokens():
    result = {
        "blocker": "provider_submit_http_error",
        "smoke_stage": "submit_request",
        "exception_class": "ValueError",
        "exception_message_safe": "Bearer=***",
        "submit_response_shape": {"top_level_keys": ["error"]},
    }
    text = bot.video_provider_smoke_debug_text("key4u_video", "text_to_video", result)
    assert "secret" not in text
    assert "https://example.invalid" not in text
    assert "charge: <code>no</code>" in text


def test_key4u_payload_builder_has_required_fields():
    payload = generic.build_key4u_video_payload(_request(), _env())
    assert payload["prompt"]
    assert payload["duration"] == 4
    assert payload["ratio"] == "9:16"
    assert payload["quality"] == "basic"
    assert payload["wallet_charge"] is False


def test_shopaikey_payload_builder_has_required_fields():
    payload = generic.build_shopaikey_video_payload(_request(), _env("shopaikey_video"))
    assert payload["prompt"]
    assert payload["duration"] == 4
    assert payload["ratio"] == "9:16"
    assert payload["quality"] == "basic"
    assert payload["wallet_charge"] is False


class _FailingProvider:
    provider_name = "key4u_video"

    def capabilities(self):
        return {"provider": self.provider_name, "enabled": True, "configured": True, "missing": [], "capabilities": ["text_to_video"], "endpoint_configured": True, "auth_configured": True}

    def submit_video_job(self, request):
        return VideoSubmitResult(ok=False, provider_name=self.provider_name, error_code="provider_task_id_missing", raw={"provider_submit_blocker": "provider_task_id_missing", "smoke_stage": "submit_response_parse"})

    def poll_video_job(self, provider_task_id: str):
        return VideoPollResult(ok=False, status="failed", error_code="should_not_poll")

    def materialize_result(self, result, job_id: str):
        return VideoArtifactResult(ok=False, error_code="should_not_download")


def test_product_job_uses_provider_blocker_not_placeholder(monkeypatch, tmp_path):
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [_FailingProvider()])
    env = {"VIDEO_PROVIDER_CHAIN": "key4u_video"}
    result = video_provider_router.run_provider_generation(_request(), output_dir=str(tmp_path), environ=env)
    assert result["ok"] is False
    assert result["provider_router_called"] is True
    assert result["provider_submit_blocker"] == "provider_task_id_missing"
    assert result.get("visual_source") != "local_placeholder"


def test_no_wallet_charge_in_provider_smoke():
    source = Path("bot.py").read_text(encoding="utf-8")
    assert 'metadata={"admin_smoke": True, "no_wallet_charge": True}' in source
