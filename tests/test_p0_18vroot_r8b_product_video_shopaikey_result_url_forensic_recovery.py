from pathlib import Path

from providers.video_generic_http_provider import GenericHttpVideoProvider
from services import video_provider_router


def _shopaikey_env(**updates):
    data = {
        "VIDEO_PROVIDER_CHAIN": "shopaikey_video",
        "SHOPAIKEY_VIDEO_ENABLED": "1",
        "SHOPAIKEY_VIDEO_SUBMIT_URL": "https://api.shopaikey.com/v1/video/generations",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE": "Bearer secret",
        "SHOPAIKEY_VIDEO_MODEL": "veo3.1-fast",
        "SHOPAIKEY_VIDEO_CAPABILITIES": "text_to_video,scene_video,multi_scene_video",
    }
    data.update(updates)
    return data


def _provider(env=None):
    return video_provider_router._generic_adapter_for("shopaikey_video", env or _shopaikey_env())


def _response(body, *, status_code=200):
    return {
        "ok": status_code < 400,
        "status_code": status_code,
        "body": body,
        "response_shape": {"type": "dict", "top_level_keys": sorted(body.keys()), "nested_keys": []},
    }


def _bot_source() -> str:
    return Path("bot.py").read_text(encoding="utf-8")


def _function_source(source: str, name: str) -> str:
    marker = f"def {name}("
    start = source.index(marker)
    next_def = source.find("\ndef ", start + len(marker))
    next_async = source.find("\nasync def ", start + len(marker))
    candidates = [idx for idx in (next_def, next_async) if idx != -1]
    end = min(candidates) if candidates else len(source)
    return source[start:end]


def test_shopaikey_exact_status_endpoint(monkeypatch):
    provider = _provider()
    called = {}

    def fake_open(self, url, payload=None, *, method="GET", timeout=60):
        called["url"] = url
        called["method"] = method
        return _response({"code": "success", "data": {"task_id": "task-r8b", "status": "processing", "progress": "50%"}})

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open)

    result = provider.poll_video_job("task-r8b")

    assert called["method"] == "GET"
    assert called["url"] == "https://api.shopaikey.com/v1/video/generations/task-r8b"
    assert result.raw["shopaikey_status_endpoint_exact"] is True
    assert result.raw["shopaikey_status_http_code"] == 200


def test_http_200_never_used_as_progress(monkeypatch):
    provider = _provider()
    monkeypatch.setattr(
        GenericHttpVideoProvider,
        "_open_json",
        lambda self, *_a, **_k: _response({"code": "success", "data": {"task_id": "task-r8b", "status": "processing"}}),
    )

    result = provider.poll_video_job("task-r8b")

    assert result.progress_percent is None
    assert result.raw["poll_http_status"] == 200
    assert result.raw["http_200_not_used_as_progress"] is True
    assert video_provider_router._progress_from_raw(result.raw) is None


def test_data_progress_string_50_parsed_to_50(monkeypatch):
    provider = _provider()
    monkeypatch.setattr(
        GenericHttpVideoProvider,
        "_open_json",
        lambda self, *_a, **_k: _response({"code": "success", "data": {"task_id": "task-r8b", "status": "processing", "progress": "50%"}}),
    )

    result = provider.poll_video_job("task-r8b")

    assert result.progress_percent == 50
    assert result.raw["provider_progress_raw"] == "50%"
    assert result.raw["provider_progress_raw_number"] == 50
    assert result.raw["provider_progress_source"] == "data.progress"


def test_uppercase_success_maps_completed_and_uses_data_result_url(monkeypatch):
    provider = _provider()
    monkeypatch.setattr(
        GenericHttpVideoProvider,
        "_open_json",
        lambda self, *_a, **_k: _response({"code": "success", "data": {"task_id": "task-r8b", "status": "SUCCESS", "progress": "100%", "result_url": "https://cdn.example/final.mp4"}}),
    )

    result = provider.poll_video_job("task-r8b")

    assert result.status == "succeeded"
    assert result.result_url == "https://cdn.example/final.mp4"
    assert result.raw["shopaikey_result_url_from_data"] is True
    assert result.raw["result_url_source_path"] == "data.result_url"


def test_uppercase_failure_maps_failed(monkeypatch):
    provider = _provider()
    monkeypatch.setattr(
        GenericHttpVideoProvider,
        "_open_json",
        lambda self, *_a, **_k: _response({"code": "success", "data": {"task_id": "task-r8b", "status": "FAILURE", "progress": "0%", "fail_reason": "model failed"}}),
    )

    result = provider.poll_video_job("task-r8b")

    assert result.status == "failed"
    assert result.raw_status == "FAILURE"
    assert result.progress_percent == 0


def test_processing_maps_continue_polling(monkeypatch):
    provider = _provider()
    monkeypatch.setattr(
        GenericHttpVideoProvider,
        "_open_json",
        lambda self, *_a, **_k: _response({"code": "success", "data": {"task_id": "task-r8b", "status": "processing", "progress": "30%"}}),
    )

    result = provider.poll_video_job("task-r8b")

    assert result.status == "running"
    assert result.progress_percent == 30
    assert not result.result_url


def test_recover_command_registered_and_raw_status_registered():
    source = _bot_source()
    assert 'CommandHandler("video_provider_recover", cmd_video_provider_recover)' in source
    assert 'CommandHandler("video_provider_raw_status", cmd_video_provider_raw_status)' in source


def test_recover_function_polls_existing_task_and_never_submits():
    source = _bot_source()
    func = _function_source(source, "video_provider_recover_existing_task")
    assert "adapter.poll_video_job(task_id)" in func
    assert "adapter.materialize_result(poll_result" in func
    assert ".submit_video_job(" not in func
    assert "run_provider_generation(" not in func
    assert '"no_new_paid_submit": True' in func
    assert '"paid_fallback_not_used": True' in func
    assert '"recovery_charge_xu": 0' in func


def test_raw_status_does_not_download_or_submit():
    source = _bot_source()
    func = _function_source(source, "video_provider_raw_status_text")
    assert "download=False" in func
    assert ".submit_video_job(" not in func
    assert "materialize_result" not in func


def test_recover_command_downloads_raw_provider_video_once():
    source = _bot_source()
    func = _function_source(source, "cmd_video_provider_recover")
    assert "video_provider_recover_existing_task(job_id, download=True)" in func
    assert "send_generated_video_artifact_for_delivery" in func
    assert "toan_aas_raw_provider_video_" in func
    assert "recovery_raw_video_sent" in func
    assert ".submit_video_job(" not in func


def test_debug_text_includes_shopaikey_r8b_fields():
    source = _bot_source()
    assert "ShopAIKey exact status endpoint" in source
    assert "HTTP 200 ignored as progress" in source
    assert "ShopAIKey data.result_url" in source
    assert "result URL source path" in source
