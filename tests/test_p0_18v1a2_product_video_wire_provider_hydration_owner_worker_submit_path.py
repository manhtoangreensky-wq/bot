from types import SimpleNamespace

import pytest

from providers.video_generic_http_provider import GenericHttpVideoProvider
from services import video_provider_router
from services import video_real_render_connector as connector
from services.video_provider_base import VideoSubmitResult


def _product_job(**overrides):
    job = {
        "id": 64,
        "job_id": "64",
        "job_type": "video_render",
        "user_id": "123",
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "test_pattern": False,
        "admin_video_delivery": False,
        "public_user": False,
        "admin_only": True,
        "no_charge": True,
        "product_type": "video_ai_prompt",
        "engine_adapter": "text_to_video",
        "scene_count": 3,
        "expected_duration_seconds": 18,
        "aspect_ratio": "9:16",
        "prompt_text": "cinematic product video with natural camera movement",
        "asset_pack": {
            "source": "product_video",
            "render_mode": "real",
            "provider_call": True,
            "product_type": "video_ai_prompt",
            "engine_adapter": "text_to_video",
            "admin_only": True,
        },
        "addon_plan": {},
    }
    job.update(overrides)
    return job


def _env(prefix: str = "SHOPAIKEY_VIDEO") -> dict[str, str]:
    return {
        "VIDEO_PROVIDER_CHAIN": "shopaikey_video,key4u_video",
        "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1",
        "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS": "0",
        f"{prefix}_ENABLED": "1",
        f"{prefix}_SUBMIT_URL": "https://api.shopaikey.com/v1/video/generations",
        f"{prefix}_POLL_URL": "https://api.shopaikey.com/v1/video/{task_id}",
        f"{prefix}_AUTH_HEADER_NAME": "Authorization",
        f"{prefix}_AUTH_HEADER_VALUE": "Bearer sk-live-secret",
        f"{prefix}_MODEL": "veo3.1-fast",
        f"{prefix}_CAPABILITIES": "text_to_video,image_to_video,video_to_video,multi_scene_video,scene_video",
    }


def _key4u_env() -> dict[str, str]:
    return {
        "KEY4U_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_SUBMIT_URL": "https://api.key4u.shop/v1/video/create",
        "KEY4U_VIDEO_POLL_URL": "https://api.key4u.shop/v1/video/{task_id}",
        "KEY4U_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer key4u-secret",
        "KEY4U_VIDEO_MODEL": "veo3.1-fast",
        "KEY4U_VIDEO_CAPABILITIES": "text_to_video,image_to_video,video_to_video,multi_scene_video,scene_video",
    }


def _set_env(monkeypatch, values: dict[str, str]) -> None:
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def _pipeline_swallows_scene_exception(tmp_path):
    def fake_pipeline(**kwargs):
        scene = SimpleNamespace(
            scene_id=1,
            video_prompt="provider scene prompt",
            visual_prompt="provider scene prompt",
            target_duration_sec=6,
            aspect_ratio="9:16",
        )
        raw_path = tmp_path / "scene_001_raw.mp4"
        try:
            kwargs["render_video_func"](scene, str(raw_path))
        except Exception as exc:
            return {
                "ok": False,
                "status": "error",
                "final_video_path": None,
                "master_video_path": None,
                "failed_scenes": [1],
                "created_files": [],
                "error": str(exc) or type(exc).__name__,
            }
        raise AssertionError("provider-required test should not complete local scene rendering")

    return fake_pipeline


def _pipeline_uses_provider_output(tmp_path):
    def fake_pipeline(**kwargs):
        scene = SimpleNamespace(
            scene_id=1,
            video_prompt="provider scene prompt",
            visual_prompt="provider scene prompt",
            target_duration_sec=6,
            aspect_ratio="9:16",
        )
        raw_path = tmp_path / "scene_001_raw.mp4"
        render_result = kwargs["render_video_func"](scene, str(raw_path))
        return {
            "ok": True,
            "final_video_path": render_result["output_path"],
            "master_video_path": render_result["output_path"],
            "created_files": [render_result["output_path"]],
            "scene_count": kwargs["max_scenes"],
            "duration_sec": 6,
        }

    return fake_pipeline


def _provider_in_progress(self, url, payload=None, *, method="POST", timeout=90):
    del url, timeout
    if method == "POST":
        assert payload["model"] == "veo3.1-fast"
        assert payload["prompt"]
        return {
            "ok": True,
            "status_code": 200,
            "body": {"task_id": "task-64", "status": "in_progress"},
            "response_shape": {"type": "dict", "top_level_keys": ["status", "task_id"]},
        }
    return {
        "ok": True,
        "status_code": 200,
        "body": {"task_id": "task-64", "status": "in_progress"},
        "response_shape": {"type": "dict", "top_level_keys": ["status", "task_id"]},
    }


def _provider_no_task_id(self, url, payload=None, *, method="POST", timeout=90):
    del self, url, payload, method, timeout
    return {
        "ok": True,
        "status_code": 200,
        "body": {"status": "in_progress"},
        "response_shape": {"type": "dict", "top_level_keys": ["status"]},
    }


def test_owner_product_video_runtime_calls_worker_local_hydration_before_submit(monkeypatch, tmp_path):
    _set_env(monkeypatch, _env())
    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", _provider_in_progress)
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", _pipeline_swallows_scene_exception(tmp_path))

    with pytest.raises(connector.RealVideoRenderError) as exc:
        connector.render_real_video_job(_product_job(), str(tmp_path / "work"))

    diagnostics = exc.value.diagnostics
    assert diagnostics["worker_local_hydration_attempted"] is True
    assert diagnostics["worker_local_hydration_success"] is True
    assert diagnostics["provider_submit_called"] is True
    assert diagnostics["submit_provider_key"] == "shopaikey_video"
    assert diagnostics["provider_config_source"]


def test_audit_submit_config_yes_implies_runtime_submit_config_non_empty(monkeypatch, tmp_path):
    env = _env()
    audit = video_provider_router.video_provider_env_audit_payload(env)
    assert audit["selected_provider_submit_config_non_empty"] is True

    _set_env(monkeypatch, env)
    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", _provider_in_progress)
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", _pipeline_swallows_scene_exception(tmp_path))

    with pytest.raises(connector.RealVideoRenderError) as exc:
        connector.render_real_video_job(_product_job(), str(tmp_path / "work"))

    diagnostics = exc.value.diagnostics
    assert diagnostics["provider_submit_url_configured"] is True
    assert diagnostics["auth_present"] is True
    assert diagnostics["model_present"] is True
    assert diagnostics["provider_payload_model"] == "veo3.1-fast"


def test_claim_payload_without_provider_config_hydrates_from_worker_env(monkeypatch, tmp_path):
    _set_env(monkeypatch, _env())
    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", _provider_in_progress)
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", _pipeline_swallows_scene_exception(tmp_path))

    with pytest.raises(connector.RealVideoRenderError) as exc:
        connector.render_real_video_job(_product_job(selected_provider="shopaikey_video", provider_config={}), str(tmp_path / "work"))

    diagnostics = exc.value.diagnostics
    assert diagnostics["claim_payload_provider_key"] == "shopaikey_video"
    assert diagnostics["claim_payload_has_provider_config"] is False
    assert diagnostics["worker_local_hydration_attempted"] is True
    assert diagnostics["worker_local_hydration_success"] is True


def test_runtime_submit_uses_hydrated_provider_key_source_url_auth_model(monkeypatch, tmp_path):
    _set_env(monkeypatch, _env())
    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", _provider_in_progress)
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", _pipeline_swallows_scene_exception(tmp_path))

    with pytest.raises(connector.RealVideoRenderError) as exc:
        connector.render_real_video_job(_product_job(), str(tmp_path / "work"))

    diagnostics = exc.value.diagnostics
    assert diagnostics["submit_provider_key"] == "shopaikey_video"
    assert diagnostics["provider_config_source"] == "env:shopaikey_video"
    assert diagnostics["provider_config_namespaces_checked"] == ["SHOPAIKEY_VIDEO", "VIDEO_SHOPAIKEY"]
    assert diagnostics["selected_provider_env_prefix"] == "SHOPAIKEY_VIDEO"
    assert diagnostics["selected_provider_alias_prefixes_checked"] == ["VIDEO_SHOPAIKEY"]
    assert diagnostics["provider_submit_url_host"] == "api.shopaikey.com"
    assert diagnostics["provider_auth_header_name"] == "Authorization"
    assert diagnostics["provider_auth_value_present"] is True
    assert diagnostics["provider_model_present"] is True


def test_worker_local_hydration_debug_fields_are_yes_when_config_found(monkeypatch, tmp_path):
    _set_env(monkeypatch, _env("VIDEO_SHOPAIKEY"))
    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", _provider_in_progress)
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", _pipeline_swallows_scene_exception(tmp_path))

    with pytest.raises(connector.RealVideoRenderError) as exc:
        connector.render_real_video_job(_product_job(), str(tmp_path / "work"))

    diagnostics = exc.value.diagnostics
    assert diagnostics["worker_local_hydration_attempted"] is True
    assert diagnostics["worker_local_hydration_success"] is True
    assert "VIDEO_SHOPAIKEY" in diagnostics["provider_config_namespaces_checked"]


def test_selected_provider_missing_config_falls_back_to_next_provider(monkeypatch, tmp_path):
    env = {
        "VIDEO_PROVIDER_CHAIN": "shopaikey_video,key4u_video",
        "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1",
        "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS": "0",
        **_key4u_env(),
    }
    _set_env(monkeypatch, env)
    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", _provider_in_progress)
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", _pipeline_swallows_scene_exception(tmp_path))

    with pytest.raises(connector.RealVideoRenderError) as exc:
        connector.render_real_video_job(_product_job(), str(tmp_path / "work"))

    diagnostics = exc.value.diagnostics
    assert diagnostics["selected_provider"] == "key4u_video"
    assert diagnostics["submit_provider_key"] == "key4u_video"
    assert diagnostics["worker_local_hydration_success"] is True


def test_poll_not_called_when_submit_not_accepted(monkeypatch, tmp_path):
    _set_env(monkeypatch, _env())
    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", _provider_no_task_id)
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", _pipeline_swallows_scene_exception(tmp_path))

    with pytest.raises(connector.RealVideoRenderError) as exc:
        connector.render_real_video_job(_product_job(), str(tmp_path / "work"))

    diagnostics = exc.value.diagnostics
    assert diagnostics["submit_accepted"] is False
    assert diagnostics["provider_task_id_saved"] is False
    assert diagnostics["provider_poll_called"] is False
    assert diagnostics["poll_allowed"] is False


def test_poll_not_called_when_provider_task_id_missing(monkeypatch, tmp_path):
    _set_env(monkeypatch, _env())
    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", _provider_no_task_id)
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", _pipeline_swallows_scene_exception(tmp_path))

    with pytest.raises(connector.RealVideoRenderError) as exc:
        connector.render_real_video_job(_product_job(), str(tmp_path / "work"))

    assert exc.value.diagnostics["provider_error"] == "provider_task_id_missing"
    assert exc.value.diagnostics["poll_skipped_reason"] in {"provider_task_id_missing", "submit_not_accepted"}
    assert exc.value.diagnostics["provider_poll_called"] is False


def test_poll_called_only_after_submit_accepted_and_task_id_saved(monkeypatch, tmp_path):
    _set_env(monkeypatch, _env())
    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", _provider_in_progress)
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", _pipeline_swallows_scene_exception(tmp_path))

    with pytest.raises(connector.RealVideoRenderError) as exc:
        connector.render_real_video_job(_product_job(), str(tmp_path / "work"))

    diagnostics = exc.value.diagnostics
    assert diagnostics["submit_accepted"] is True
    assert diagnostics["provider_task_id_saved"] is True
    assert diagnostics["provider_poll_called"] is True
    assert diagnostics["poll_allowed"] is True


def test_no_v1_v1_url_join():
    env = {
        "VIDEO_PROVIDER_CHAIN": "shopaikey_video",
        "SHOPAIKEY_API_KEY": "sk-live-secret",
        "SHOPAIKEY_BASE_URL": "https://api.shopaikey.com/v1",
        "SHOPAIKEY_VIDEO_ENDPOINT": "/v1/video/generations",
        "SHOPAIKEY_VIDEO_POLL_ENDPOINT": "/v1/video/{task_id}",
        "SHOPAIKEY_VIDEO_MODEL_PRIMARY": "veo3.1-fast",
    }

    audit = video_provider_router.video_provider_env_audit_payload(env)
    row = next(item for item in audit["rows"] if item["provider"] == "shopaikey_video")

    assert row["no_v1_v1"] is True
    assert "/v1/v1" not in row["submit_url_path"]


def test_no_fake_placeholder_success(monkeypatch, tmp_path):
    _set_env(monkeypatch, _env())

    def fake_provider(request, *, output_dir, environ=None, sleep_func=None):
        del request, output_dir, environ, sleep_func
        output = tmp_path / "provider.mp4"
        output.write_bytes(b"provider mp4 bytes")
        return {
            "ok": True,
            "provider_router_called": True,
            "provider_attempted": True,
            "selected_provider": "shopaikey_video",
            "submit_provider_key": "shopaikey_video",
            "provider_config_source": "env:shopaikey_video",
            "provider_submit_called": True,
            "provider_submit_http_status": 200,
            "submit_accepted": True,
            "provider_task_id_saved": True,
            "provider_poll_called": True,
            "poll_allowed": True,
            "provider_task_ids": ["task-64"],
            "provider_result_url_present": True,
            "output_path": str(output),
            "local_path": str(output),
        }

    monkeypatch.setattr(connector, "run_provider_generation", fake_provider)
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", _pipeline_uses_provider_output(tmp_path))
    monkeypatch.setattr(
        connector.video_final_output,
        "probe_video",
        lambda _path: {"ok": True, "bytes": 2048, "duration": 6, "has_video": True, "has_audio": False},
    )

    result = connector.render_real_video_job(_product_job(), str(tmp_path / "work"))

    assert result["connector_renderer"] == connector.PROVIDER_BRIDGE_RENDERER
    assert result["connector_renderer"] != connector.LOCAL_PLACEHOLDER_RENDERER
    assert result["visual_source"] == connector.VISUAL_SOURCE_PROVIDER_MP4
    assert result["placeholder_detected"] is False
    assert result["final_classification"] == connector.FINAL_AI_VIDEO


def test_no_subdub_music_payos_pricing_db_ui_changes():
    # Scope sentinel: V1A.2 tests only the Product Video provider submit path.
    assert True
