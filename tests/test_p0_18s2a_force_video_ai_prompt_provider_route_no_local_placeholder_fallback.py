import asyncio
import inspect
from types import SimpleNamespace

import pytest

import bot
from services import video_real_render_connector as connector


def _product_job(**overrides):
    job = {
        "id": 43,
        "job_id": "43",
        "job_type": "video_render",
        "user_id": "1",
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "test_pattern": False,
        "admin_video_delivery": False,
        "provider_call": True,
        "public_user": False,
        "admin_only": True,
        "no_charge": True,
        "product_type": "video_ai_prompt",
        "scene_count": 1,
        "expected_duration_seconds": 4,
        "aspect_ratio": "9:16",
        "prompt_text": "short jade green product video",
        "addon_plan": {},
    }
    job.update(overrides)
    return job


def _ready_readiness():
    return {
        "ok": True,
        "ready_provider_order": ["key4u_video", "shopaikey_video"],
        "first_ready_provider": "key4u_video",
        "enabled_count": 2,
        "configured_count": 2,
        "enabled_providers": ["key4u_video", "shopaikey_video"],
        "configured_providers": ["key4u_video", "shopaikey_video"],
        "providers": [
            {"provider": "key4u_video", "enabled": True, "configured": True, "capabilities": ["text_to_video"]},
            {"provider": "shopaikey_video", "enabled": True, "configured": True, "capabilities": ["text_to_video"]},
        ],
        "missing_env": {},
    }


def _missing_readiness():
    return {
        "ok": False,
        "ready_provider_order": [],
        "enabled_count": 0,
        "configured_count": 0,
        "enabled_providers": [],
        "configured_providers": [],
        "providers": [],
        "missing_env": {"key4u_video": ["KEY4U_VIDEO_SUBMIT_URL"]},
    }


def _pipeline_calls_renderer(tmp_path):
    def fake_pipeline(**kwargs):
        scene = SimpleNamespace(
            scene_id=1,
            video_prompt="provider scene prompt",
            visual_prompt="provider scene prompt",
            target_duration_sec=4,
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


def _provider_success(tmp_path):
    calls = {"count": 0, "requests": []}

    def fake_run(request, *, output_dir, environ=None, sleep_func=None):
        del environ, sleep_func
        calls["count"] += 1
        calls["requests"].append(request)
        output = tmp_path / f"provider_{calls['count']}.mp4"
        output.write_bytes(b"provider mp4 bytes")
        return {
            "ok": True,
            "provider_attempted": True,
            "provider_router_called": True,
            "provider": "key4u_video",
            "selected_provider": "key4u_video",
            "provider_submit_called": True,
            "provider_submit_http_status": 200,
            "provider_task_id_saved": True,
            "provider_poll_called": True,
            "provider_result_url_present": True,
            "provider_task_ids": ["task-43"],
            "provider_video_ids": ["video-43"],
            "provider_status": "downloaded",
            "result_url_present": True,
            "output_path": str(output),
            "local_path": str(output),
            "artifact_hash": "a" * 64,
        }

    return calls, fake_run


def _install_success(monkeypatch, tmp_path):
    calls, fake_run = _provider_success(tmp_path)
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_a, **_k: _ready_readiness())
    monkeypatch.setattr(connector, "run_provider_generation", fake_run)
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", _pipeline_calls_renderer(tmp_path))
    monkeypatch.setattr(
        connector,
        "build_local_scene_composer",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("local_scene_composer must not run")),
    )
    return calls


def test_video_ai_prompt_requires_provider_route():
    route = connector.video_final_output.route_for_product_type("video_ai_prompt")
    assert connector._route_requires_provider(
        "video_ai_prompt",
        route["provider_capability"],
        route["fallback_capability"],
        provider_ready=True,
    ) is True


def test_video_ai_prompt_calls_provider_router_when_provider_ready(monkeypatch, tmp_path):
    calls = _install_success(monkeypatch, tmp_path)
    result = connector.render_real_video_job(_product_job(), str(tmp_path / "work"))

    assert calls["count"] == 1
    assert calls["requests"][0].required_capability == "text_to_video"
    assert result["provider_router_called"] is True
    assert result["provider_attempted"] is True


def test_video_ai_prompt_does_not_select_local_scene_composer(monkeypatch, tmp_path):
    _install_success(monkeypatch, tmp_path)
    result = connector.render_real_video_job(_product_job(), str(tmp_path / "work"))

    assert result["connector_renderer"] == connector.PROVIDER_BRIDGE_RENDERER
    assert result["renderer"] != connector.LOCAL_PLACEHOLDER_RENDERER


def test_video_ai_prompt_forbids_local_placeholder_final(monkeypatch, tmp_path):
    _install_success(monkeypatch, tmp_path)
    result = connector.render_real_video_job(_product_job(), str(tmp_path / "work"))

    assert result["visual_source"] == connector.VISUAL_SOURCE_PROVIDER_MP4
    assert result["base_video_source"] == "provider"
    assert result["placeholder_forbidden"] is True
    assert result["placeholder_detected"] is False


def test_video_ai_prompt_provider_selected_key4u_first(monkeypatch, tmp_path):
    _install_success(monkeypatch, tmp_path)
    result = connector.render_real_video_job(_product_job(), str(tmp_path / "work"))

    assert result["provider_route_selected"] is True
    assert result["selected_provider"] == "key4u_video"
    assert result["provider_candidates_count"] == 2


def test_provider_task_id_saved_after_submit(monkeypatch, tmp_path):
    _install_success(monkeypatch, tmp_path)
    result = connector.render_real_video_job(_product_job(), str(tmp_path / "work"))

    assert result["provider_submit_called"] is True
    assert result["provider_task_id_saved"] is True
    assert result["provider_task_ids"] == ["task-43"]
    assert result["provider_poll_called"] is True
    assert result["provider_result_url_present"] is True


def test_provider_missing_fails_provider_capability_missing_early(monkeypatch, tmp_path):
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_a, **_k: _missing_readiness())
    monkeypatch.setattr(
        connector,
        "build_local_scene_composer",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("local_scene_composer must not run")),
    )

    with pytest.raises(connector.RealVideoRenderError) as exc:
        connector.render_real_video_job(_product_job(), str(tmp_path / "work"))

    assert str(exc.value) == "provider_capability_missing"
    assert exc.value.diagnostics["provider_attempted"] is False
    assert exc.value.diagnostics["route_requires_provider"] is True
    assert exc.value.diagnostics["local_fallback_allowed"] is False
    assert exc.value.diagnostics["no_charge"] is True


def test_provider_submit_failed_no_local_placeholder_fallback(monkeypatch, tmp_path):
    def fail_run(request, *, output_dir, environ=None, sleep_func=None):
        del request, output_dir, environ, sleep_func
        return {
            "ok": False,
            "provider_attempted": True,
            "provider_router_called": True,
            "provider": "key4u_video",
            "selected_provider": "key4u_video",
            "provider_submit_called": True,
            "provider_error": "provider_submit_failed",
            "blocker": "provider_submit_failed",
            "provider_status": "failed",
        }

    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_a, **_k: _ready_readiness())
    monkeypatch.setattr(connector, "run_provider_generation", fail_run)
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", _pipeline_calls_renderer(tmp_path))
    monkeypatch.setattr(
        connector,
        "build_local_scene_composer",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("local_scene_composer must not run")),
    )

    with pytest.raises(connector.RealVideoRenderError) as exc:
        connector.render_real_video_job(_product_job(), str(tmp_path / "work"))

    diagnostics = exc.value.diagnostics
    assert diagnostics["provider_attempted"] is True
    assert diagnostics["provider_error"] == "provider_submit_failed"
    assert diagnostics["fallback_used"] is False
    assert diagnostics["base_video_source"] != "placeholder"


def test_provider_result_missing_no_placeholder_delivery(monkeypatch, tmp_path):
    def missing_result(request, *, output_dir, environ=None, sleep_func=None):
        del request, output_dir, environ, sleep_func
        return {
            "ok": False,
            "provider_attempted": True,
            "provider_router_called": True,
            "provider": "key4u_video",
            "provider_submit_called": True,
            "provider_task_id_saved": True,
            "provider_poll_called": True,
            "provider_task_ids": ["task-43"],
            "provider_error": "provider_result_url_missing",
            "blocker": "provider_result_url_missing",
            "provider_status": "succeeded",
            "provider_result_url_present": False,
        }

    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_a, **_k: _ready_readiness())
    monkeypatch.setattr(connector, "run_provider_generation", missing_result)
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", _pipeline_calls_renderer(tmp_path))

    with pytest.raises(connector.RealVideoRenderError) as exc:
        connector.render_real_video_job(_product_job(), str(tmp_path / "work"))

    assert exc.value.diagnostics["provider_error"] == "provider_result_url_missing"
    assert exc.value.diagnostics["placeholder_detected"] is not True
    assert exc.value.diagnostics["fallback_used"] is False


def test_addons_run_only_after_base_provider_mp4_valid(monkeypatch, tmp_path):
    calls = _install_success(monkeypatch, tmp_path)
    result = connector.render_real_video_job(
        _product_job(addon_plan={"music_enabled": True, "subtitle_enabled": True, "logo_enabled": True, "logo_text": "TOAN AAS"}),
        str(tmp_path / "work"),
    )

    assert calls["count"] == 1
    assert result["base_video_source"] == "provider"
    assert result["visual_classification"] == connector.FINAL_AI_VIDEO
    assert result["partial_addons"] in {True, False}


def test_placeholder_partial_simple_video_not_delivered():
    assert connector.classify_visual_result(
        {
            "ok": True,
            "renderer": connector.LOCAL_PLACEHOLDER_RENDERER,
            "visual_source": connector.VISUAL_SOURCE_LOCAL_PLACEHOLDER,
            "placeholder_detected": True,
        }
    ) == connector.PARTIAL_SIMPLE_VIDEO


def test_video_render_debug_shows_route_requires_provider():
    source = inspect.getsource(bot.video_render_debug_text)
    for needle in [
        "required capability",
        "route requires provider",
        "local fallback allowed",
        "provider router called",
        "provider candidates",
        "selected provider",
        "provider submit called",
        "provider task id saved",
        "provider result url present",
        "base video source",
        "placeholder forbidden",
        "fallback policy",
    ]:
        assert needle in source


def test_video_provider_smoke_uses_provider_no_wallet_charge():
    source = inspect.getsource(bot.cmd_video_provider_smoke)
    assert "run_provider_generation" in source
    assert "VideoGenerationRequest" in source
    assert "VIDEO_PROVIDER_CHAIN" in source
    assert "duration_seconds=4.0" in source
    assert "validate_final_video_output" in source
    assert "no_wallet_charge" in source
    assert "wallet" not in source.lower().replace("no_wallet_charge", "")
    lifespan = inspect.getsource(bot.lifespan)
    assert 'CommandHandler("video_provider_smoke", cmd_video_provider_smoke)' in lifespan


class _FakeMessage:
    def __init__(self):
        self.texts = []
        self.videos = []

    async def reply_text(self, text, **kwargs):
        self.texts.append((text, kwargs))
        return SimpleNamespace(message_id=1)

    async def reply_video(self, **kwargs):
        self.videos.append(kwargs)
        return SimpleNamespace(message_id=2)


def test_video_provider_smoke_alias_calls_same_provider_router(monkeypatch, tmp_path):
    message = _FakeMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=int(bot.ADMIN_ID)), message=message)
    context = SimpleNamespace(args=["key4u", "text_to_video"])
    calls = {"count": 0}

    def fake_run(request, *, output_dir, environ=None, sleep_func=None):
        del sleep_func
        calls["count"] += 1
        assert environ["VIDEO_PROVIDER_CHAIN"] == "key4u_video"
        output = tmp_path / "smoke.mp4"
        output.write_bytes(b"provider smoke mp4")
        return {
            "ok": True,
            "provider_attempted": True,
            "provider_task_ids": [f"task-{request.job_id}"],
            "provider": "key4u_video",
            "output_path": str(output),
            "local_path": str(output),
        }

    monkeypatch.setattr(bot.video_provider_router, "run_provider_generation", fake_run)
    monkeypatch.setattr(bot.video_final_output, "validate_final_video_output", lambda path="", result=None, **_k: {"ok": True})

    asyncio.run(bot.cmd_video_provider_smoke(update, context))

    assert calls["count"] == 1
    assert message.videos
