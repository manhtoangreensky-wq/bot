import json
import sqlite3

import remote_worker
from providers.video_generic_http_provider import GenericHttpVideoProvider
from services import video_project_queue, video_provider_router
from services.video_provider_base import VideoGenerationRequest, VideoSubmitResult


def _request() -> VideoGenerationRequest:
    return VideoGenerationRequest(
        job_id="job-56",
        product_type="video_ai_prompt",
        video_flow_type="video_ai_prompt",
        prompt="Create a cinematic product video with natural movement",
        ratio="9:16",
        duration_seconds=6,
        required_capability="text_to_video",
        metadata={"product_video": True, "allow_provider_pending": True},
    )


def _valid_env() -> dict[str, str]:
    return {
        "VIDEO_PROVIDER_CHAIN": "shopaikey_video,key4u_video",
        "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1",
        "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS": "0",
        "SHOPAIKEY_VIDEO_ENABLED": "1",
        "SHOPAIKEY_VIDEO_SUBMIT_URL": "https://api.shopaikey.com/v1/video/generations",
        "SHOPAIKEY_VIDEO_POLL_URL": "https://api.shopaikey.com/v1/video/{task_id}",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE": "Bearer sk-live-secret",
        "SHOPAIKEY_VIDEO_MODEL": "veo3.1-fast",
        "SHOPAIKEY_VIDEO_CAPABILITIES": "text_to_video,image_to_video,video_to_video,multi_scene_video,scene_video",
        "KEY4U_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_SUBMIT_URL": "https://api.key4u.shop/v1/video/create",
        "KEY4U_VIDEO_POLL_URL": "https://api.key4u.shop/v1/video/{task_id}",
        "KEY4U_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer key4u-secret",
        "KEY4U_VIDEO_MODEL": "veo3.1-fast",
    }


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _product_project(conn):
    project = video_project_queue.create_video_project(
        conn,
        user_id=123,
        profile_id="video_ai_prompt",
        topic="video prompt",
        asset_pack={
            "source": "product_video",
            "render_mode": "real",
            "provider_call": True,
            "real_renderer_required": True,
            "product_type": "video_ai_prompt",
            "engine_adapter": "text_to_video",
            "admin_only": True,
            "no_charge": True,
            "public_user": False,
        },
    )
    video_project_queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="queued_for_worker",
        total_xu_estimated=0,
        is_confirmed=1,
    )
    job = video_project_queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=123)
    return project, job


def test_product_video_provider_submit_hydrates_shopaikey_env(monkeypatch, tmp_path):
    env = _valid_env()

    def fake_open_json(self, url, payload=None, *, method="POST", timeout=90):
        assert self.provider_name == "shopaikey_video"
        assert url.startswith("https://api.shopaikey.com/")
        if method == "POST":
            assert payload["model"] == "veo3.1-fast"
            assert payload["prompt"]
            return {
                "ok": True,
                "status_code": 200,
                "body": {"task_id": "task-56", "status": "in_progress"},
                "response_shape": {"type": "dict", "top_level_keys": ["status", "task_id"]},
            }
        return {
            "ok": True,
            "status_code": 200,
            "body": {"task_id": "task-56", "status": "in_progress"},
            "response_shape": {"type": "dict", "top_level_keys": ["status", "task_id"]},
        }

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open_json)
    result = video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ=env,
        sleep_func=lambda _seconds: None,
    )

    assert result["provider_router_called"] is True
    assert result["selected_provider"] == "shopaikey_video"
    assert result["selected_provider_before_submit"] == "shopaikey_video"
    assert result["submit_provider_key"] == "shopaikey_video"
    assert result["provider_config_source"] == "env:shopaikey_video"
    assert result["provider_submit_url_configured"] is True
    assert result["provider_submit_url_host"] == "api.shopaikey.com"
    assert result["provider_auth_header_name"] == "Authorization"
    assert result["provider_auth_value_present"] is True
    assert result["provider_auth_scheme_prefix"] == "Bearer"
    assert result["provider_model_present"] is True
    assert result["provider_payload_model"] == "veo3.1-fast"
    assert "prompt" in result["provider_payload_keys"]
    assert result["provider_submit_http_status"] == 200
    assert result["provider_task_id_saved"] is True
    assert result["provider_task_ids"] == ["task-56"]
    assert result["continue_polling"] is True
    assert result["no_charge"] is True
    assert result.get("fallback_used") is False


def test_submit_config_missing_uses_config_blocker_not_http_error():
    env = {
        "SHOPAIKEY_VIDEO_ENABLED": "1",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE": "Bearer sk-live-secret",
        "SHOPAIKEY_VIDEO_MODEL": "veo3.1-fast",
    }
    provider = GenericHttpVideoProvider(
        provider_name="shopaikey_video",
        environ=env,
        enabled_env="SHOPAIKEY_VIDEO_ENABLED",
        submit_url_env="SHOPAIKEY_VIDEO_SUBMIT_URL",
        poll_url_env="SHOPAIKEY_VIDEO_POLL_URL",
        auth_header_name_env="SHOPAIKEY_VIDEO_AUTH_HEADER_NAME",
        auth_header_value_env="SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE",
        model_env="SHOPAIKEY_VIDEO_MODEL",
    )

    submit = provider.submit_video_job(_request())

    assert submit.ok is False
    assert submit.error_code == "provider_config_missing_at_submit"
    assert submit.raw["provider_submit_blocker"] == "provider_config_missing_at_submit"
    assert submit.raw["selected_provider_before_submit"] == "shopaikey_video"
    assert submit.raw["submit_provider_key"] == "shopaikey_video"
    assert submit.raw["provider_submit_url_configured"] is False
    assert submit.raw["provider_auth_value_present"] is True
    assert submit.raw["provider_payload_model"] == "veo3.1-fast"


class _ConfigMissingAtSubmitProvider:
    provider_name = "shopaikey_video"

    def capabilities(self):
        return {
            "provider": self.provider_name,
            "enabled": True,
            "configured": True,
            "capabilities": ["text_to_video"],
            "submit_url_configured": True,
            "poll_url_configured": True,
            "auth_configured": True,
            "provider_config_source": "env:shopaikey_video",
            "provider_submit_url_host": "api.shopaikey.com",
            "provider_auth_header_name": "Authorization",
            "provider_auth_value_present": True,
            "provider_auth_scheme_prefix": "Bearer",
            "provider_model_present": True,
            "provider_payload_model": "veo3.1-fast",
        }

    def submit_video_job(self, request):
        return VideoSubmitResult(
            ok=False,
            provider_name=self.provider_name,
            provider_status="config_invalid",
            error_code="provider_config_missing_at_submit",
            raw={
                "provider_config_source": "env:shopaikey_video",
                "selected_provider_before_submit": "shopaikey_video",
                "submit_provider_key": "shopaikey_video",
                "provider_submit_url_configured": False,
                "provider_submit_url_host": "",
                "provider_auth_value_present": False,
                "provider_model_present": False,
                "provider_submit_blocker": "provider_config_missing_at_submit",
            },
        )

    def poll_video_job(self, provider_task_id):
        raise AssertionError("poll should not run when config is missing at submit")

    def materialize_result(self, result, job_id):
        raise AssertionError("download should not run when config is missing at submit")


def test_router_preserves_provider_config_missing_at_submit(monkeypatch, tmp_path):
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [_ConfigMissingAtSubmitProvider()])

    result = video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ={"VIDEO_PROVIDER_CHAIN": "shopaikey_video"},
        sleep_func=lambda _seconds: None,
    )

    assert result["ok"] is False
    assert result["blocker"] == "provider_config_missing_at_submit"
    assert result["provider_error"] == "provider_config_missing_at_submit"
    assert result["selected_provider"] == "shopaikey_video"
    assert result["selected_provider_before_submit"] == "shopaikey_video"
    assert result["submit_provider_key"] == "shopaikey_video"
    assert result["provider_submit_called"] is True
    assert result["provider_task_id_saved"] is False
    assert result["no_charge"] is True


def test_remote_worker_provider_hint_reads_first_ready_provider(monkeypatch):
    for key, value in _valid_env().items():
        monkeypatch.setenv(key, value)

    assert remote_worker.product_video_provider_hint({"source": "product_video", "provider_call": True}) == "shopaikey_video"


def test_video_render_debug_shows_submit_hydration_fields_without_secret(monkeypatch):
    import bot

    conn = _conn()
    try:
        _project, job = _product_project(conn)
        trace = {
            "provider_attempted": True,
            "provider_router_called": True,
            "provider_submit_called": True,
            "selected_provider": "shopaikey_video",
            "selected_provider_before_submit": "shopaikey_video",
            "submit_provider_key": "shopaikey_video",
            "provider_config_source": "env:shopaikey_video",
            "provider_submit_url_configured": True,
            "provider_submit_url_host": "api.shopaikey.com",
            "provider_auth_header_name": "Authorization",
            "provider_auth_value_present": True,
            "provider_auth_scheme_prefix": "Bearer",
            "provider_model_present": True,
            "provider_payload_model": "veo3.1-fast",
            "provider_payload_keys": ["prompt", "duration", "ratio", "model"],
            "provider_task_id_saved": True,
            "provider_task_ids": ["task-56"],
            "continue_polling": True,
            "no_charge": True,
        }
        conn.execute("UPDATE video_jobs SET result_json=? WHERE id=?", (json.dumps(trace), int(job["id"])))
        conn.commit()
        monkeypatch.setattr(bot, "db_connect", lambda: conn)

        text = bot.video_render_debug_text(int(job["id"]))

        assert "selected provider before submit: <code>shopaikey_video</code>" in text
        assert "submit provider key: <code>shopaikey_video</code>" in text
        assert "provider config source: <code>env:shopaikey_video</code>" in text
        assert "provider model present: <code>yes</code>" in text
        assert "provider payload model: <code>veo3.1-fast</code>" in text
        assert "sk-live-secret" not in text
    finally:
        conn.close()


def test_video_provider_job_debug_shows_submit_hydration_fields_without_secret():
    import bot

    conn = _conn()
    try:
        _project, job = _product_project(conn)
        trace = {
            "selected_provider": "shopaikey_video",
            "selected_provider_before_submit": "shopaikey_video",
            "submit_provider_key": "shopaikey_video",
            "provider_config_source": "env:shopaikey_video",
            "provider_submit_called": True,
            "provider_submit_url_configured": True,
            "provider_submit_url_host": "api.shopaikey.com",
            "provider_auth_header_name": "Authorization",
            "provider_auth_value_present": True,
            "provider_auth_scheme_prefix": "Bearer",
            "provider_model_present": True,
            "provider_payload_model": "veo3.1-fast",
            "provider_payload_keys": ["prompt", "duration", "ratio", "model"],
            "provider_task_id_saved": True,
            "provider_task_ids": ["task-56"],
            "continue_polling": True,
            "no_charge": True,
        }
        conn.execute("UPDATE video_jobs SET result_json=? WHERE id=?", (json.dumps(trace), int(job["id"])))
        conn.commit()

        text = bot.video_provider_job_debug_text(int(job["id"]), conn=conn)

        assert "selected provider before submit: <code>shopaikey_video</code>" in text
        assert "submit provider key: <code>shopaikey_video</code>" in text
        assert "provider config source: <code>env:shopaikey_video</code>" in text
        assert "provider model present: <code>yes</code>" in text
        assert "payload model: <code>veo3.1-fast</code>" in text
        assert "sk-live-secret" not in text
    finally:
        conn.close()
