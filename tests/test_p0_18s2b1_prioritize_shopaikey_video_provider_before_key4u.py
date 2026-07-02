from pathlib import Path

from services import video_provider_router
from services.video_provider_base import VideoArtifactResult, VideoGenerationRequest, VideoPollResult, VideoSubmitResult


def _provider_env(chain: str = "") -> dict[str, str]:
    env = {
        "SHOPAIKEY_VIDEO_ENABLED": "1",
        "SHOPAIKEY_VIDEO_SUBMIT_URL": "https://example.invalid/shop/submit",
        "SHOPAIKEY_VIDEO_POLL_URL": "https://example.invalid/shop/poll/{task_id}",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE": "Bearer shop",
        "KEY4U_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_SUBMIT_URL": "https://example.invalid/key4u/submit",
        "KEY4U_VIDEO_POLL_URL": "https://example.invalid/key4u/poll/{task_id}",
        "KEY4U_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer key4u",
    }
    if chain:
        env["VIDEO_PROVIDER_CHAIN"] = chain
    return env


def _request() -> VideoGenerationRequest:
    return VideoGenerationRequest(
        job_id="s2b1",
        product_type="video_ai_prompt",
        prompt="A cinematic product video",
        duration_seconds=1,
        required_capability="text_to_video",
    )


class _FakeVideoProvider:
    def __init__(self, name: str, *, fail_submit: bool = False):
        self.provider_name = name
        self.fail_submit = fail_submit
        self.calls = {"submit": 0, "poll": 0, "materialize": 0}

    def capabilities(self):
        return {
            "provider": self.provider_name,
            "enabled": True,
            "configured": True,
            "missing": [],
            "capabilities": ["text_to_video", "scene_video"],
            "endpoint_configured": True,
            "submit_url_present": True,
            "poll_url_present": True,
            "auth_configured": True,
            "model_configured": True,
        }

    def submit_video_job(self, request: VideoGenerationRequest):
        self.calls["submit"] += 1
        if self.fail_submit:
            return VideoSubmitResult(ok=False, provider_name=self.provider_name, error_code="quota_exhausted", raw={"status_code": 402})
        return VideoSubmitResult(ok=True, provider_name=self.provider_name, provider_task_id=f"{self.provider_name}-task", provider_status="succeeded", result_url="memory://video.mp4")

    def poll_video_job(self, provider_task_id: str):
        self.calls["poll"] += 1
        return VideoPollResult(ok=True, provider_name=self.provider_name, provider_task_id=provider_task_id, status="succeeded", result_url="memory://video.mp4")

    def materialize_result(self, result: VideoPollResult, job_id: str):
        self.calls["materialize"] += 1
        return VideoArtifactResult(ok=True, local_path=f"/tmp/{self.provider_name}_{job_id}.mp4", bytes=2048, duration=1.0, has_video_stream=True)

    def cancel_video_job(self, provider_task_id: str):
        return {"ok": False}


def test_default_video_provider_chain_shopaikey_first():
    assert video_provider_router.configured_provider_chain({})[:3] == ["shopaikey_video", "key4u_video", "toanaas_video"]
    assert video_provider_router.DEFAULT_VIDEO_PROVIDER_CHAIN.startswith("shopaikey_video,key4u_video")


def test_env_video_provider_chain_respected():
    env = _provider_env("key4u_video,shopaikey_video,toanaas_video")
    assert video_provider_router.configured_provider_chain(env)[:2] == ["key4u_video", "shopaikey_video"]


def test_shopaikey_selected_before_key4u_when_both_ready():
    env = _provider_env()
    adapter, status = video_provider_router.select_video_provider("text_to_video", env)
    assert adapter is not None
    assert adapter.provider_name == "shopaikey_video"
    assert status["first_ready_provider"] == "shopaikey_video"
    assert status["selection_reason"] == "provider_ready_and_has_credit"
    assert status["fallback_order"][0] == "key4u_video"


def test_key4u_used_only_when_shopaikey_unavailable():
    env = _provider_env("shopaikey_video,key4u_video")
    env["SHOPAIKEY_VIDEO_ENABLED"] = "0"
    adapter, status = video_provider_router.select_video_provider("text_to_video", env)
    assert adapter is not None
    assert adapter.provider_name == "key4u_video"
    assert status["first_ready_provider"] == "key4u_video"


def test_low_credit_key4u_not_selected_first():
    env = _provider_env("key4u_video,shopaikey_video")
    env["KEY4U_VIDEO_CREDIT_STATUS"] = "low_credit"
    adapter, status = video_provider_router.select_video_provider("text_to_video", env)
    assert adapter is not None
    assert adapter.provider_name == "shopaikey_video"
    key4u = next(item for item in status["providers"] if item["provider"] == "key4u_video")
    assert key4u["credit_status"] == "low_credit"
    assert key4u["fallback_only"] is True
    assert {"provider": "key4u_video", "reason": "credit_low_credit"} in status["skipped_providers"]


def test_video_provider_status_shows_effective_order():
    status = video_provider_router.provider_status_payload(_provider_env())
    assert status["effective_provider_chain"][:2] == ["shopaikey_video", "key4u_video"]
    assert status["first_ready_provider"] == "shopaikey_video"
    assert status["selection_reason"] == "provider_ready_and_has_credit"
    assert status["fallback_order"][0] == "key4u_video"
    bot_source = Path("bot.py").read_text(encoding="utf-8")
    assert "Thứ tự provider" in bot_source
    assert "Lý do chọn" in bot_source
    assert "Fallback tiếp theo" in bot_source
    assert "credit=" in bot_source


def test_video_render_debug_shows_selected_provider_and_fallback(monkeypatch, tmp_path):
    shop = _FakeVideoProvider("shopaikey_video", fail_submit=True)
    key4u = _FakeVideoProvider("key4u_video")
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [shop, key4u])
    result = video_provider_router.run_provider_generation(_request(), output_dir=str(tmp_path), environ=_provider_env(), sleep_func=lambda _seconds: None)
    assert result["ok"] is True
    assert result["selected_provider"] == "key4u_video"
    assert result["fallback_used"] is True
    assert result["fallback_reason"] == "quota_exhausted"
    assert result["provider_chain"][0] == "shopaikey_video"
    assert shop.calls["submit"] == 1
    assert key4u.calls["submit"] == 1

    source = Path("bot.py").read_text(encoding="utf-8")
    assert "provider chain" in source
    assert "fallback order" in source
    assert "skipped providers" in source
