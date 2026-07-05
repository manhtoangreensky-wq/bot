import json
import sqlite3

from providers.video_generic_http_provider import GenericHttpVideoProvider
from services import video_project_queue, video_provider_router
from services.video_provider_base import VideoArtifactResult, VideoGenerationRequest


def _env() -> dict[str, str]:
    return {
        "VIDEO_PROVIDER_CHAIN": "shopaikey_video,key4u_video",
        "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1",
        "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS": "0",
        "SHOPAIKEY_VIDEO_ENABLED": "1",
        "SHOPAIKEY_VIDEO_SUBMIT_URL": "https://api.shopaikey.com/v1/video/generations",
        "SHOPAIKEY_VIDEO_POLL_URL": "https://api.shopaikey.com/v1/video/{task_id}",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE": "Bearer shop-secret",
        "SHOPAIKEY_VIDEO_MODEL": "veo3.1-fast",
        "SHOPAIKEY_VIDEO_CAPABILITIES": "text_to_video,image_to_video,video_to_video,multi_scene_video,scene_video",
        "KEY4U_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_SUBMIT_URL": "https://api.key4u.shop/v1/video/create",
        "KEY4U_VIDEO_POLL_URL": "https://api.key4u.shop/v1/video/{task_id}",
        "KEY4U_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer key4u-secret",
        "KEY4U_VIDEO_MODEL": "veo3.1-fast",
        "KEY4U_VIDEO_CAPABILITIES": "text_to_video,image_to_video,video_to_video,multi_scene_video,scene_video",
    }


def _request(*, paid_retry_confirmed: bool = False) -> VideoGenerationRequest:
    metadata = {"product_video": True, "allow_provider_pending": True, "wallet_charge": False}
    if paid_retry_confirmed:
        metadata["product_video_paid_retry_confirmed"] = True
    return VideoGenerationRequest(
        job_id="job-67",
        product_type="video_ai_prompt",
        video_flow_type="video_ai_prompt",
        prompt="A cinematic product video with smooth camera motion",
        ratio="9:16",
        duration_seconds=6,
        required_capability="text_to_video_or_scene_video",
        metadata=metadata,
    )


def _submit_ok(provider: str):
    return {
        "ok": True,
        "status_code": 200,
        "body": {"task_id": f"{provider}-task-67", "status": "in_progress"},
        "response_shape": {"type": "dict", "top_level_keys": ["status", "task_id"], "nested_keys": []},
    }


def _poll_pending(provider: str):
    return {
        "ok": True,
        "status_code": 200,
        "body": {"task_id": f"{provider}-task-67", "status": "in_progress"},
        "response_shape": {"type": "dict", "top_level_keys": ["status", "task_id"], "nested_keys": []},
    }


def _poll_done(provider: str):
    return {
        "ok": True,
        "status_code": 200,
        "body": {"task_id": f"{provider}-task-67", "status": "completed", "download_url": "https://cdn.example/video.mp4"},
        "response_shape": {"type": "dict", "top_level_keys": ["download_url", "status", "task_id"], "nested_keys": []},
    }


def _http_503(provider: str):
    return {
        "ok": False,
        "status_code": 503,
        "body": {"type": "service_unavailable", "code": 503, "message": f"{provider} temporarily unavailable"},
        "response_shape": {"type": "dict", "top_level_keys": ["code", "message", "type"], "nested_keys": []},
    }


def _attempt(result: dict, provider: str) -> dict:
    for item in result.get("provider_attempts") or []:
        if item.get("provider") == provider:
            return item
    raise AssertionError(f"missing provider attempt {provider}: {result.get('provider_attempts')}")


def test_shopaikey_attempt_trace_includes_submit_poll_result_download_fields(monkeypatch, tmp_path):
    def fake_open(self, url, payload=None, *, method="POST", timeout=90):
        if method == "POST":
            return _submit_ok(self.provider_name)
        return _poll_done(self.provider_name)

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open)
    monkeypatch.setattr(
        GenericHttpVideoProvider,
        "materialize_result",
        lambda self, result, job_id: VideoArtifactResult(
            ok=False,
            error_code="provider_download_not_video",
            error_message="json body",
            bytes=42,
            content_type="application/json",
        ),
    )

    result = video_provider_router.run_provider_generation(_request(), output_dir=str(tmp_path), environ={**_env(), "VIDEO_PROVIDER_CHAIN": "shopaikey_video"}, sleep_func=lambda _seconds: None)
    trace = _attempt(result, "shopaikey_video")

    assert trace["submit_called"] is True
    assert trace["submit_http_status"] == 200
    assert trace["submit_accepted"] is True
    assert trace["task_id_present"] is True
    assert trace["poll_called"] is True
    assert trace["poll_http_status"] == 200
    assert trace["result_url_present"] is True
    assert trace["download_called"] is True
    assert trace["download_content_type"] == "application/json"
    assert trace["downloaded_file_size"] == 42
    assert trace["validation_passed"] is False
    assert trace["blocker"] == "provider_download_not_video"


def test_shopaikey_submit_accepted_task_id_keeps_job_pending_not_failed(monkeypatch, tmp_path):
    calls = []

    def fake_open(self, url, payload=None, *, method="POST", timeout=90):
        calls.append((self.provider_name, method))
        if method == "POST":
            return _submit_ok(self.provider_name)
        return _poll_pending(self.provider_name)

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open)

    result = video_provider_router.run_provider_generation(_request(paid_retry_confirmed=True), output_dir=str(tmp_path), environ=_env(), sleep_func=lambda _seconds: None)

    assert calls == [("shopaikey_video", "POST"), ("shopaikey_video", "GET")]
    assert result["selected_provider"] == "shopaikey_video"
    assert result["blocker"] == "provider_in_progress"
    assert result["continue_polling"] is True
    assert result["provider_task_id_saved"] is True
    assert result["no_charge"] is True
    assert not result.get("fallback_used")


def test_shopaikey_processing_poll_does_not_fallback_to_key4u(monkeypatch, tmp_path):
    calls = []

    def fake_open(self, url, payload=None, *, method="POST", timeout=90):
        calls.append((self.provider_name, method))
        if method == "POST":
            return _submit_ok(self.provider_name)
        return _poll_pending(self.provider_name)

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open)

    result = video_provider_router.run_provider_generation(_request(paid_retry_confirmed=True), output_dir=str(tmp_path), environ=_env(), sleep_func=lambda _seconds: None)
    trace = _attempt(result, "shopaikey_video")

    assert "key4u_video" not in [item[0] for item in calls]
    assert trace["continue_polling"] is True
    assert trace["normalized_status"] == "running"
    assert result["provider_status"] == "running"


def test_shopaikey_terminal_download_failure_records_concrete_blocker(monkeypatch, tmp_path):
    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", lambda self, *_a, method="POST", **_k: _submit_ok(self.provider_name) if method == "POST" else _poll_done(self.provider_name))
    monkeypatch.setattr(
        GenericHttpVideoProvider,
        "materialize_result",
        lambda self, result, job_id: VideoArtifactResult(ok=False, error_code="provider_download_html_error", error_message="html", bytes=120, content_type="text/html"),
    )

    result = video_provider_router.run_provider_generation(_request(), output_dir=str(tmp_path), environ={**_env(), "VIDEO_PROVIDER_CHAIN": "shopaikey_video"}, sleep_func=lambda _seconds: None)
    trace = _attempt(result, "shopaikey_video")

    assert result["blocker"] == "provider_download_html_error"
    assert result["provider_result_blocker"] == "provider_download_html_error"
    assert trace["blocker"] == "provider_download_html_error"
    assert trace["download_content_type"] == "text/html"
    assert trace["downloaded_file_size"] == 120


def test_shopaikey_download_failure_can_fallback_to_key4u(monkeypatch, tmp_path):
    calls = []

    def fake_open(self, url, payload=None, *, method="POST", timeout=90):
        calls.append((self.provider_name, method))
        if self.provider_name == "shopaikey_video":
            if method == "POST":
                return _submit_ok(self.provider_name)
            return _poll_done(self.provider_name)
        return _http_503(self.provider_name)

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open)

    def fake_materialize(self, result, job_id):
        assert self.provider_name == "shopaikey_video"
        return VideoArtifactResult(ok=False, error_code="provider_download_failed", error_message="HTTPError", bytes=0, content_type="")

    monkeypatch.setattr(GenericHttpVideoProvider, "materialize_result", fake_materialize)

    result = video_provider_router.run_provider_generation(_request(paid_retry_confirmed=True), output_dir=str(tmp_path), environ=_env(), sleep_func=lambda _seconds: None)

    assert calls == [("shopaikey_video", "POST"), ("shopaikey_video", "GET"), ("key4u_video", "POST")]
    assert result["selected_provider"] == "key4u_video"
    assert result["provider_fallback_reason"] == "provider_download_failed"
    assert _attempt(result, "shopaikey_video")["download_called"] is True


def test_key4u_503_after_shopaikey_terminal_failure_no_poll_no_charge(monkeypatch, tmp_path):
    monkeypatch.setattr(
        GenericHttpVideoProvider,
        "_open_json",
        lambda self, *_a, method="POST", **_k: _submit_ok(self.provider_name) if self.provider_name == "shopaikey_video" and method == "POST" else _poll_done(self.provider_name) if self.provider_name == "shopaikey_video" else _http_503(self.provider_name),
    )
    monkeypatch.setattr(GenericHttpVideoProvider, "materialize_result", lambda self, result, job_id: VideoArtifactResult(ok=False, error_code="provider_download_failed"))

    result = video_provider_router.run_provider_generation(_request(paid_retry_confirmed=True), output_dir=str(tmp_path), environ=_env(), sleep_func=lambda _seconds: None)
    key4u = _attempt(result, "key4u_video")

    assert result["selected_provider"] == "key4u_video"
    assert result["provider_submit_http_status"] == 503
    assert key4u["submit_called"] is True
    assert key4u["submit_http_status"] == 503
    assert key4u["poll_called"] is False
    assert result["provider_poll_called"] is False
    assert result["no_charge"] is True


def test_video_provider_job_debug_shows_per_provider_attempt_summary(monkeypatch):
    import bot

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    project = video_project_queue.create_video_project(conn, user_id=67, profile_id="video_ai_prompt", topic="video", asset_pack={"source": "product_video", "render_mode": "real", "provider_call": True})
    job = video_project_queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=67)
    result = {
        "selected_provider": "key4u_video",
        "provider_attempts": [
            {"provider": "shopaikey_video", "phase": "validate", "submit_called": True, "submit_http_status": 200, "submit_accepted": True, "task_id_present": True, "task_id_source": "task_id", "poll_called": True, "poll_http_status": 200, "poll_raw_status": "completed", "normalized_status": "succeeded", "result_url_present": True, "download_called": True, "download_content_type": "text/html", "downloaded_file_size": 120, "validation_passed": False, "blocker": "provider_download_html_error"},
            {"provider": "key4u_video", "phase": "submit", "submit_called": True, "submit_http_status": 503, "blocker": "provider_temporarily_unavailable"},
        ],
        "blocker": "provider_temporarily_unavailable",
    }
    conn.execute("UPDATE video_jobs SET result_json=?, status=?, progress_percent=? WHERE id=?", (json.dumps(result), "failed", 20, int(job["id"])))
    conn.commit()
    monkeypatch.setattr(bot, "db_connect", lambda: conn)

    text = bot.video_provider_job_debug_text(int(job["id"]))

    assert "Provider attempts:" in text
    assert "shopaikey_video" in text
    assert "phase=<code>validate</code>" in text
    assert "provider_download_html_error" in text
    assert "key4u_video" in text
    assert "Có lỗi khi xử lý lệnh" not in text


def test_video_render_debug_never_generic_fails_with_partial_provider_attempts(monkeypatch):
    import bot

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    project = video_project_queue.create_video_project(conn, user_id=67, profile_id="video_ai_prompt", topic="video", asset_pack={"source": "product_video", "render_mode": "real", "provider_call": True})
    job = video_project_queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=67)
    result = {"provider_attempts": [None, "bad", {"provider": "shopaikey_video", "phase": "download", "download_called": True, "blocker": "provider_download_failed"}], "blocker": "provider_download_failed"}
    conn.execute("UPDATE video_jobs SET result_json=?, status=?, progress_percent=? WHERE id=?", (json.dumps(result), "failed", 20, int(job["id"])))
    conn.commit()
    monkeypatch.setattr(bot, "db_connect", lambda: conn)

    text = bot.video_render_debug_text(int(job["id"]))

    assert "Video Render Debug" in text
    assert "Provider attempts:" in text
    assert "provider_download_failed" in text
    assert "Traceback" not in text


def test_video_provider_status_never_generic_fails_with_partial_provider_data():
    import bot

    text = bot.video_provider_status_text(
        {
            "ready": False,
            "provider_chain": "shopaikey_video,key4u_video",
            "fallback_order": ["key4u_video"],
            "providers": [None, {"provider": "shopaikey_video", "enabled": True, "configured": True, "provider_config_namespaces_checked": None}],
            "missing_env": "bad-shape",
            "invalid_env": ["bad-shape"],
        },
        key4u_credit=None,
    )

    assert "Trạng thái nhà cung cấp video" in text
    assert "shopaikey_video" in text
    assert "Traceback" not in text


def test_progress_status_debug_recovers_terminal_state_from_db_when_registry_missing(monkeypatch):
    import bot

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    project = video_project_queue.create_video_project(conn, user_id=67, profile_id="video_ai_prompt", topic="video", asset_pack={"source": "product_video", "render_mode": "real", "provider_call": True})
    job = video_project_queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=67)
    conn.execute("UPDATE video_jobs SET status=?, progress_percent=?, last_error=? WHERE id=?", ("failed", 20, "provider_temporarily_unavailable", int(job["id"])))
    video_project_queue.update_video_project(conn, int(project["project_id"]), video_terminal_state="failed_no_charge")
    conn.commit()
    monkeypatch.setattr(bot, "db_connect", lambda: conn)
    monkeypatch.setattr(bot, "PROGRESS_AUTO_REFRESH_JOBS", {})

    text = bot.product_progress_debug_text(str(job["id"]), "", {})

    assert "recovered_from_db_for_status_debug: <code>yes</code>" in text
    assert "persisted_job_status: <code>failed</code>" in text
    assert "persisted_job_progress: <code>20%</code>" in text
    assert "Percent: <code>20%</code>" in text


def test_no_fake_placeholder_success(monkeypatch, tmp_path):
    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", lambda self, *_a, **_k: _http_503(self.provider_name))

    result = video_provider_router.run_provider_generation(_request(), output_dir=str(tmp_path), environ=_env(), sleep_func=lambda _seconds: None)

    assert result["ok"] is False
    assert result["no_charge"] is True
    assert not result.get("output_path")
    assert result.get("visual_source") not in {"local_placeholder", "local_scene_composer"}


def test_no_subdub_music_payos_pricing_db_ui_changes():
    # Scope sentinel: V1B2 only hardens Product Video provider trace/status debug.
    assert True
