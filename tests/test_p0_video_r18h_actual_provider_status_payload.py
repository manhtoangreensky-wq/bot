from pathlib import Path

from providers.video_generic_http_provider import GenericHttpVideoProvider
from services import video_real_render_connector as connector
from services.video_provider_base import VideoPollResult


ROOT = Path(__file__).resolve().parents[1]


def _shopaikey_env() -> dict[str, str]:
    return {
        "SHOPAIKEY_VIDEO_ENABLED": "1",
        "SHOPAIKEY_VIDEO_SUBMIT_URL": "https://api.shopaikey.test/v1/video/generations",
        "SHOPAIKEY_VIDEO_POLL_URL": "https://api.shopaikey.test/v1/video/generations/{task_id}",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE": "Bearer test-token",
        "SHOPAIKEY_VIDEO_MODEL": "veo3.1-fast",
        "SHOPAIKEY_VIDEO_CAPABILITIES": "text_to_video,scene_video,multi_scene_video",
    }


def _shopaikey_provider(env: dict[str, str] | None = None) -> GenericHttpVideoProvider:
    return GenericHttpVideoProvider(
        provider_name="shopaikey_video",
        enabled_env="SHOPAIKEY_VIDEO_ENABLED",
        submit_url_env="SHOPAIKEY_VIDEO_SUBMIT_URL",
        poll_url_env="SHOPAIKEY_VIDEO_POLL_URL",
        auth_header_name_env="SHOPAIKEY_VIDEO_AUTH_HEADER_NAME",
        auth_header_value_env="SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE",
        result_field_env="SHOPAIKEY_VIDEO_RESULT_FIELD",
        model_env="SHOPAIKEY_VIDEO_MODEL",
        capabilities_env="SHOPAIKEY_VIDEO_CAPABILITIES",
        environ=env or _shopaikey_env(),
    )


def _job(elapsed: int = 56) -> dict:
    return {
        "job_id": "109",
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "product_type": "video_trend",
        "scene_count": 2,
        "orchestration_mode": "per_scene_8s",
        "provider_order": "shopaikey_video,key4u_video",
        "configured_provider_chain": "shopaikey_video,key4u_video",
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "original_submit_source": "public_user_final_confirm",
        "provider_elapsed_seconds": elapsed,
        "provider_wait_elapsed_seconds": elapsed,
        "selected_provider": "shopaikey_video",
        "selected_model": "veo3.1-fast",
        "provider_model_map": {"shopaikey_video": "veo3.1-fast", "key4u_video": "kling-3.0-turbo"},
    }


def _job_109_payload(elapsed: int = 56) -> dict:
    return {
        "scene_index": 1,
        "request_job_id": "109-1",
        "provider": "shopaikey_video",
        "selected_provider": "shopaikey_video",
        "provider_task_id": "task-r18h-1",
        "provider_video_id": "video-r18h-1",
        "provider_task_ids": ["task-r18h-1"],
        "provider_video_ids": ["video-r18h-1"],
        "status": "running",
        "provider_status": "running",
        "normalized_provider_status": "running",
        "provider_status_raw": "IN_PROGRESS",
        "raw_provider_status": "IN_PROGRESS",
        "raw_provider_status_before_source_fix": "IN_PROGRESS",
        "provider_status_payload_source": "shopaikey.data.status",
        "shopaikey_raw_status": "NOT_START",
        "shopaikey_data_status": "NOT_START",
        "nonterminal_provider_status": "IN_PROGRESS",
        "provider_progress_raw": 0,
        "shopaikey_data_progress_raw": 0,
        "provider_progress_normalized": 0,
        "provider_elapsed_seconds": elapsed,
        "provider_wait_elapsed_seconds": elapsed,
        "scene_not_start_elapsed": 0,
        "provider_stalled_not_start": False,
        "fallback_allowed": False,
        "fallback_block_reason": "primary_provider_in_progress",
        "fallback_blocked_reason": "primary_provider_in_progress",
        "primary_provider_task_alive": True,
        "key4u_submit_suppressed": True,
        "continue_polling": True,
        "selected_model": "veo3.1-fast",
    }


def test_job_109_shopaikey_data_status_beats_top_level_in_progress(monkeypatch):
    provider = _shopaikey_provider()

    def fake_open(url, payload=None, **kwargs):
        return {
            "ok": True,
            "status_code": 200,
            "body": {"status": "IN_PROGRESS", "data": {"status": "NOT_START", "progress": "0%"}},
            "response_shape": {"type": "dict"},
        }

    monkeypatch.setattr(provider, "_open_json", fake_open)

    result = provider.poll_video_job("task-r18h-1")

    assert result.ok is True
    assert result.raw_status == "NOT_START"
    assert result.status == "not_start"
    assert result.raw["provider_status_payload_source"] == "shopaikey.data.status"
    assert result.raw["raw_provider_status_before_source_fix"] == "IN_PROGRESS"
    assert result.raw["shopaikey_raw_status"] == "NOT_START"
    assert result.raw["provider_progress_raw"] == "0%"


def test_job_109_pending_dominance_uses_actual_status_payload():
    payload = {
        **_job_109_payload(elapsed=56),
        "provider_pending_provider": "shopaikey_video",
        "provider_pending_task_id": "task-r18h-1",
        "provider_pending_video_id": "video-r18h-1",
        "provider_pending_request_job_id": "109-1",
    }

    result = connector._apply_pending_provider_dominance(payload, job=_job(elapsed=56))

    assert result["raw_provider_status_before_source_fix"] == "IN_PROGRESS"
    assert result["provider_status_payload_source"] == "shopaikey.data.status"
    assert result["raw_provider_status"] == "NOT_START"
    assert result["provider_status_raw"] == "NOT_START"
    assert result["normalized_provider_status"] == "not_start"
    assert result["provider_status"] == "not_start"
    assert result["provider_error"] == "provider_not_start"
    assert result["not_start_override_applied"] is True
    assert result["fallback_block_reason"] == "not_start_under_threshold"
    assert result["key4u_submit_suppressed_reason"] == "not_start_under_threshold"


def test_job_109_scene_debug_uses_actual_status_payload_under_threshold():
    debug = connector.product_video_scene_tasks_debug(
        _job(elapsed=56),
        debug_results=[_job_109_payload(elapsed=56)],
        scene_count=2,
    )

    assert debug[0]["provider_status_payload_source"] == "shopaikey.data.status"
    assert debug[0]["raw_provider_status_before_source_fix"] == "IN_PROGRESS"
    assert debug[0]["provider_status_raw"] == "NOT_START"
    assert debug[0]["status"] == "provider_not_start"
    assert debug[0]["scene_not_start_elapsed"] >= 56
    assert debug[0]["provider_stalled_not_start"] is False
    assert debug[0]["fallback_allowed"] is False
    assert debug[0]["fallback_block_reason"] == "not_start_under_threshold"


def test_not_start_threshold_env_is_exposed(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", "120")

    policy = connector.product_video_scene_stall_policy(
        _job(elapsed=119),
        _job_109_payload(elapsed=119),
        1,
    )

    assert policy["not_start_threshold_seconds"] == 120
    assert policy["not_start_threshold_source"] == "env:VIDEO_PROVIDER_NOT_START_STALL_SECONDS"
    assert policy["provider_stalled_not_start"] is False
    assert policy["fallback_block_reason"] == "not_start_under_threshold"


def test_not_start_over_threshold_allows_key4u_candidate(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", "90")

    policy = connector.product_video_scene_stall_policy(
        _job(elapsed=121),
        _job_109_payload(elapsed=121),
        1,
    )

    assert policy["current_scene_status"] == "provider_stalled_not_start"
    assert policy["provider_stalled_not_start"] is True
    assert policy["fallback_allowed"] is True
    assert policy["fallback_block_reason"] == ""
    assert policy["fallback_provider_order"][0] == "key4u_video"


def test_real_running_status_is_not_false_not_start():
    policy = connector.product_video_scene_stall_policy(
        _job(elapsed=56),
        {
            "scene_index": 1,
            "provider": "shopaikey_video",
            "provider_task_id": "task-running",
            "status": "IN_PROGRESS",
            "provider_status_raw": "IN_PROGRESS",
            "provider_status_payload_source": "shopaikey.status",
            "provider_wait_elapsed_seconds": 56,
        },
        1,
    )

    assert policy["current_scene_status"] == "provider_running"
    assert policy["provider_stalled_not_start"] is False
    assert policy["fallback_allowed"] is False


def test_debug_source_contract_exposes_r18h_fields():
    bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")
    progress_source = (ROOT / "services" / "product_progress_status.py").read_text(encoding="utf-8")

    for token in (
        "provider status payload source:",
        "raw provider status before source fix:",
        "NOT_START threshold source:",
    ):
        assert token in bot_source
    for token in (
        "provider_status_payload_source",
        "shopaikey_data_status",
        "raw_provider_status_before_source_fix",
        "not_start_threshold_source",
    ):
        assert token in progress_source


def test_no_real_provider_calls_in_r18h_tests():
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "urllib.request." + "urlopen",
        "provider" + "_smoke",
    )
    assert all(token not in source for token in forbidden)
