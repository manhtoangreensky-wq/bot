from types import SimpleNamespace

import pytest

from services import video_provider_router
from services import video_real_render_connector as connector
from services.video_provider_base import VideoArtifactResult, VideoGenerationRequest, VideoPollResult, VideoSubmitResult


class _AliasProvider:
    provider_name = "shopaikey_video"

    def __init__(self, capabilities):
        self._capabilities = list(capabilities)
        self.submitted_capabilities: list[str] = []

    def capabilities(self):
        return {
            "provider": self.provider_name,
            "enabled": True,
            "configured": True,
            "missing": [],
            "capabilities": self._capabilities,
            "endpoint_configured": True,
            "submit_url_configured": True,
            "poll_url_configured": True,
            "auth_configured": True,
            "model_configured": True,
        }

    def submit_video_job(self, request: VideoGenerationRequest):
        self.submitted_capabilities.append(request.required_capability)
        return VideoSubmitResult(
            ok=True,
            provider_name=self.provider_name,
            provider_task_id="shop-task-49",
            provider_status="MEDIA_GENERATION_STATUS_PENDING",
            raw={"http_status": 200, "task_id_field_path": "data.id_base"},
        )

    def poll_video_job(self, provider_task_id: str):
        return VideoPollResult(
            ok=True,
            status="MEDIA_GENERATION_STATUS_IN_PROGRESS",
            provider_name=self.provider_name,
            provider_task_id=provider_task_id,
            raw={"poll_http_status": 200, "provider_status_raw": "MEDIA_GENERATION_STATUS_IN_PROGRESS"},
        )

    def materialize_result(self, result: VideoPollResult, job_id: str):
        return VideoArtifactResult(ok=False, error_code="pending_should_not_download")


def _request(required_capability: str = "text_to_video_or_scene_video") -> VideoGenerationRequest:
    return VideoGenerationRequest(
        job_id="job-49",
        product_type="video_trend",
        video_flow_type="video_trend",
        prompt="A friendly product trend video",
        ratio="9:16",
        duration_seconds=6,
        required_capability=required_capability,
        metadata={"product_video": True, "allow_provider_pending": True, "wallet_charge": False},
    )


def _job(**overrides):
    payload = {
        "id": 49,
        "job_id": "49",
        "job_type": "video_render",
        "user_id": "123",
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "test_pattern": False,
        "admin_video_delivery": False,
        "public_user": True,
        "no_charge": False,
        "product_type": "video_trend",
        "engine_adapter": "text_to_video_or_scene_engine",
        "scene_count": 3,
        "expected_duration_seconds": 18,
        "aspect_ratio": "9:16",
        "prompt_text": "friendly trend video",
        "asset_pack": {
            "source": "product_video",
            "render_mode": "real",
            "provider_call": True,
            "product_type": "video_trend",
            "engine_adapter": "text_to_video_or_scene_engine",
            "public_user": True,
        },
        "addon_plan": {},
    }
    payload.update(overrides)
    return payload


def _readiness(capabilities):
    return {
        "ok": True,
        "ready_provider_order": ["shopaikey_video"],
        "first_ready_provider": "shopaikey_video",
        "enabled_count": 1,
        "configured_count": 1,
        "enabled_providers": ["shopaikey_video"],
        "configured_providers": ["shopaikey_video"],
        "providers": [
            {
                "provider": "shopaikey_video",
                "enabled": True,
                "configured": True,
                "capabilities": list(capabilities),
            }
        ],
        "missing_env": {},
    }


def _pipeline_calls_renderer(tmp_path):
    def fake_pipeline(**kwargs):
        scene = SimpleNamespace(
            scene_id=1,
            video_prompt="provider trend scene prompt",
            visual_prompt="provider trend scene prompt",
            target_duration_sec=6,
            aspect_ratio="9:16",
        )
        raw_path = tmp_path / "scene_001_raw.mp4"
        render_result = kwargs["render_video_func"](scene, str(raw_path))
        return {
            "ok": True,
            "final_video_path": render_result["output_path"],
            "created_files": [render_result["output_path"]],
            "scene_count": kwargs["max_scenes"],
        }

    return fake_pipeline


@pytest.mark.parametrize("provider_capability", ["text_to_video", "scene_video", "multi_scene_video"])
def test_alias_text_to_video_or_scene_video_matches_supported_provider(provider_capability):
    provider = _AliasProvider([provider_capability])

    assert video_provider_router.provider_supports(provider, "text_to_video_or_scene_video") is True
    assert video_provider_router.provider_supports(provider, "text_to_video_or_scene_engine") is True


def test_multi_scene_scene_text_preference_order():
    provider = _AliasProvider(["text_to_video", "scene_video", "multi_scene_video"])

    assert video_provider_router.capability_options("text_to_video_or_scene_video") == [
        "multi_scene_video",
        "scene_video",
        "text_to_video",
    ]
    assert video_provider_router.preferred_provider_capability(provider, "text_to_video_or_scene_video") == "multi_scene_video"


def test_product_video_trend_selects_provider_instead_of_capability_missing(monkeypatch, tmp_path):
    provider = _AliasProvider(["text_to_video"])
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [provider])
    env = {"VIDEO_PROVIDER_CHAIN": "shopaikey_video", "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1"}

    result = video_provider_router.run_provider_generation(
        _request("text_to_video_or_scene_video"),
        output_dir=str(tmp_path),
        environ=env,
        sleep_func=lambda _seconds: None,
    )

    assert result["ok"] is False
    assert result["required_capability_original"] == "text_to_video_or_scene_video"
    assert result["normalized_capability_candidates"] == ["multi_scene_video", "scene_video", "text_to_video"]
    assert result["provider_candidates_count"] == 1
    assert result["selected_provider"] == "shopaikey_video"
    assert result["selected_capability"] == "text_to_video"
    assert result["provider_selection_blocker"] == ""
    assert result["provider_submit_called"] is True
    assert result["provider_task_id_saved"] is True
    assert result["provider_task_ids"] == ["shop-task-49"]
    assert result["blocker"] == "provider_in_progress"
    assert result["continue_polling"] is True
    assert result["no_charge"] is True
    assert provider.submitted_capabilities == ["text_to_video"]


def test_provider_required_connector_never_falls_back_to_local_scene_composer_for_alias(monkeypatch, tmp_path):
    requests = []

    def pending_provider(request, *, output_dir, environ=None, sleep_func=None):
        del output_dir, environ, sleep_func
        requests.append(request)
        return {
            "ok": False,
            "provider_attempted": True,
            "provider_router_called": True,
            "provider": "shopaikey_video",
            "selected_provider": "shopaikey_video",
            "required_capability_original": "text_to_video_or_scene_video",
            "normalized_capability_candidates": ["multi_scene_video", "scene_video", "text_to_video"],
            "provider_candidates_count": 1,
            "provider_selection_blocker": "",
            "provider_submit_called": True,
            "provider_submit_http_status": 200,
            "provider_task_id_saved": True,
            "provider_poll_called": True,
            "provider_result_url_present": False,
            "provider_task_ids": ["shop-task-49"],
            "provider_status": "running",
            "normalized_provider_status": "running",
            "blocker": "provider_in_progress",
            "provider_error": "provider_in_progress",
            "continue_polling": True,
            "no_charge": True,
        }

    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_a, **_k: _readiness(["scene_video"]))
    monkeypatch.setattr(connector, "run_provider_generation", pending_provider)
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", _pipeline_calls_renderer(tmp_path))
    monkeypatch.setattr(
        connector,
        "build_local_scene_composer",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("local_scene_composer must not run")),
    )

    with pytest.raises(connector.RealVideoRenderError) as exc:
        connector.render_real_video_job(_job(), str(tmp_path / "work"))

    diagnostics = exc.value.diagnostics
    assert requests[0].required_capability == "text_to_video_or_scene_video"
    assert diagnostics["route_requires_provider"] is True
    assert diagnostics["provider_router_called"] is True
    assert diagnostics["provider_submit_called"] is True
    assert diagnostics["provider_task_id_saved"] is True
    assert diagnostics["provider_task_ids"] == ["shop-task-49"]
    assert diagnostics["provider_candidates_count"] == 1
    assert diagnostics["provider_selection_blocker"] == ""
    assert diagnostics["required_capability_original"] == "text_to_video_or_scene_video"
    assert diagnostics["normalized_capability_candidates"] == ["multi_scene_video", "scene_video", "text_to_video"]
    assert diagnostics["continue_polling"] is True
    assert diagnostics["connector_renderer"] == connector.PROVIDER_BRIDGE_RENDERER
    assert diagnostics["connector_renderer"] != connector.LOCAL_PLACEHOLDER_RENDERER
    assert diagnostics["fallback_used"] is False
    assert diagnostics["placeholder_forbidden"] is True
    assert diagnostics["placeholder_detected"] is False
    assert diagnostics["no_charge"] is True
