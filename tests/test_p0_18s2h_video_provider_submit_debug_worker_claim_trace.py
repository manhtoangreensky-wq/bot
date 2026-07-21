import json
import sqlite3

from providers.video_generic_http_provider import GenericHttpVideoProvider
from services import remote_worker_api, video_project_queue, video_provider_router
from services.video_provider_base import VideoGenerationRequest, VideoSubmitResult


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _product_project(conn):
    project = video_project_queue.create_video_project(
        conn,
        user_id=123,
        profile_id="video_trend",
        topic="trend video",
        asset_pack={
            "source": "product_video",
            "render_mode": "real",
            "provider_call": True,
            "real_renderer_required": True,
            "product_type": "video_trend",
            "engine_adapter": "text_to_video_or_scene_engine",
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


def _request() -> VideoGenerationRequest:
    return VideoGenerationRequest(
        job_id="job-55",
        product_type="video_trend",
        video_flow_type="video_trend",
        prompt="A clean trend video",
        ratio="9:16",
        duration_seconds=6,
        required_capability="text_to_video",
        metadata={"product_video": True, "allow_provider_pending": True},
    )


def test_worker_claim_trace_persists_to_job_result_json():
    conn = _conn()
    try:
        _project, job = _product_project(conn)
        result = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-toanaas-01",
            capabilities=["owner_product_video"],
            owner_product_video_only=True,
        )

        payload = result["job"]
        saved_job = video_project_queue.get_video_render_job(conn, int(job["id"]))
        saved = json.loads(saved_job["result_json"])

        assert payload["actual_processor"] == "remote_worker"
        assert payload["worker_service_mode"] == "owner_product_video"
        assert payload["claimed_by_service_mode"] == "owner_product_video"
        assert payload["worker_claim_route"] == "/api/v1/worker/claim"
        assert payload["worker_claim_status"] == "claimed"
        assert saved["actual_processor"] == "remote_worker"
        assert saved["worker_id"] == "vps-toanaas-01"
        assert saved["worker_service_mode"] == "owner_product_video"
    finally:
        conn.close()


def test_inline_processing_reports_railway_bot_processor():
    conn = _conn()
    try:
        _project, job = _product_project(conn)
        claimed = video_project_queue.claim_next_video_job(conn, worker_id="railway-inline")

        def runner(_project, _scenes):
            return {"ok": True, "final_video_file_id": "telegram-file-id", "final_video_path": ""}

        result = video_project_queue.process_claimed_video_job(conn, claimed, runner)
        saved_job = result["job"]
        saved = json.loads(saved_job["result_json"])

        assert saved["actual_processor"] == "railway_bot"
        assert saved["worker_service_mode"] == "inline_video_job"
        assert saved["worker_claim_route"] == "inline"
        assert saved["process_pid"] > 0
    finally:
        conn.close()


class _BoomProvider:
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
        raise RuntimeError("submit failed with Bearer sk-secret-token-should-not-leak")

    def poll_video_job(self, provider_task_id):
        raise AssertionError("poll should not run")

    def materialize_result(self, result, job_id):
        raise AssertionError("download should not run")


def test_submit_http_exception_records_safe_exception_without_token(monkeypatch, tmp_path):
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [_BoomProvider()])

    result = video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ={"VIDEO_PROVIDER_CHAIN": "shopaikey_video"},
        sleep_func=lambda _seconds: None,
    )
    raw_text = json.dumps(result, ensure_ascii=False)

    assert result["ok"] is False
    assert result["provider_submit_called"] is True
    assert result["provider_submit_exception_class"] == "RuntimeError"
    assert "Bearer ***" in result["provider_submit_exception_message_safe"]
    assert "sk-secret-token-should-not-leak" not in raw_text
    assert result["no_charge"] is not False


def test_generic_provider_submit_debug_has_host_auth_payload_shape_without_secret(monkeypatch):
    env = {
        "SHOPAIKEY_VIDEO_ENABLED": "1",
        "SHOPAIKEY_VIDEO_SUBMIT_URL": "https://api.shopaikey.com/v1/video/create",
        "SHOPAIKEY_VIDEO_POLL_URL": "https://api.shopaikey.com/v1/video/{task_id}",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE": "Bearer sk-live-secret-token",
        "SHOPAIKEY_VIDEO_MODEL": "kling-v1",
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
    monkeypatch.setattr(
        provider,
        "_open_json",
        lambda *_args, **_kwargs: {
            "ok": False,
            "status_code": 403,
            "body": {"error": {"code": "access_denied"}},
            "error": "http_error",
            "response_shape": {"type": "dict", "top_level_keys": ["error"], "nested_keys": ["error:{code}"]},
        },
    )

    submit: VideoSubmitResult = provider.submit_video_job(_request())
    raw = submit.raw
    raw_text = json.dumps(raw, ensure_ascii=False)

    assert submit.ok is False
    assert raw["provider_submit_url_configured"] is True
    assert raw["provider_submit_url_host"] == "api.shopaikey.com"
    assert raw["provider_auth_header_name"] == "Authorization"
    assert raw["provider_auth_value_present"] is True
    assert raw["provider_auth_scheme_prefix"] == "Bearer"
    assert "prompt" in raw["provider_payload_keys"]
    assert raw["provider_payload_model"] == "kling-v1"
    assert raw["provider_response_http_status"] == 403
    assert raw["provider_response_body_shape"]["top_level_keys"] == ["error"]
    assert "sk-live-secret-token" not in raw_text


def test_video_provider_job_debug_shows_trace_and_safe_submit_fields_without_token():
    import bot

    conn = _conn()
    try:
        _project, job = _product_project(conn)
        trace = {
            "actual_processor": "remote_worker",
            "worker_id": "vps-toanaas-01",
            "worker_service_mode": "owner_product_video",
            "worker_claim_route": "/api/v1/worker/claim",
            "worker_claim_status": "claimed",
            "process_hostname": "vps-host",
            "process_pid": 1234,
            "provider_attempted": True,
            "provider_router_called": True,
            "provider_submit_called": True,
            "provider_submit_http_status": 0,
            "provider_submit_exception_class": "URLError",
            "provider_submit_exception_message_safe": "timeout with Bearer ***",
            "provider_submit_url_configured": True,
            "provider_submit_url_host": "api.shopaikey.com",
            "provider_auth_header_name": "Authorization",
            "provider_auth_value_present": True,
            "provider_auth_scheme_prefix": "Bearer",
            "provider_payload_keys": ["prompt", "duration", "ratio"],
            "provider_payload_model": "kling-v1",
            "provider_response_http_status": 0,
            "provider_response_body_shape": {"type": "dict", "top_level_keys": []},
            "provider_error": "provider_submit_http_error",
            "no_charge": True,
        }
        conn.execute("UPDATE video_jobs SET result_json=? WHERE id=?", (json.dumps(trace), int(job["id"])))
        conn.commit()

        text = bot.video_provider_job_debug_text(int(job["id"]), conn=conn)

        assert "actual processor: <code>remote_worker</code>" in text
        assert "worker service mode: <code>owner_product_video</code>" in text
        assert "submit url host: <code>api.shopaikey.com</code>" in text
        assert "auth header: <code>Authorization</code> present=<code>yes</code> scheme=<code>Bearer</code>" in text
        assert "payload keys: <code>prompt,duration,ratio</code>" in text
        assert "sk-" not in text
        assert "secret" not in text
    finally:
        conn.close()


def test_no_charge_before_valid_mp4_is_preserved_in_trace_failure():
    conn = _conn()
    try:
        _project, job = _product_project(conn)
        claimed = video_project_queue.claim_next_video_job(conn, worker_id="local_worker")
        remote_worker_api.fail_remote_worker_job(
            conn,
            worker_id="local_worker",
            job_id=int(claimed["id"]),
            safe_error="provider_submit_http_error",
            retryable=False,
            diagnostics={
                "actual_processor": "remote_worker",
                "provider_submit_called": True,
                "provider_error": "provider_submit_http_error",
                "no_charge": True,
            },
        )
        project = video_project_queue.get_video_project(conn, int(_project["project_id"]))
        saved_job = video_project_queue.get_video_render_job(conn, int(job["id"]))
        saved = json.loads(saved_job["result_json"])

        assert saved["no_charge"] is True
        assert int(project.get("charged_xu") or project.get("total_xu_charged") or 0) == 0
    finally:
        conn.close()
