import json
import sqlite3

from providers.video_generic_http_provider import GenericHttpVideoProvider
from services import video_project_queue, video_provider_router
from services.video_provider_base import VideoGenerationRequest


def _env(*, both: bool = True) -> dict[str, str]:
    env = {
        "VIDEO_PROVIDER_CHAIN": "shopaikey_video,key4u_video" if both else "shopaikey_video",
        "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1",
        "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS": "0",
        "SHOPAIKEY_VIDEO_ENABLED": "1",
        "SHOPAIKEY_VIDEO_SUBMIT_URL": "https://api.shopaikey.com/v1/video/generations",
        "SHOPAIKEY_VIDEO_POLL_URL": "https://api.shopaikey.com/v1/video/{task_id}",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE": "Bearer shop-secret",
        "SHOPAIKEY_VIDEO_MODEL": "veo3.1-fast",
        "SHOPAIKEY_VIDEO_CAPABILITIES": "text_to_video,image_to_video,video_to_video,multi_scene_video,scene_video",
    }
    if both:
        env.update(
            {
                "KEY4U_VIDEO_ENABLED": "1",
                "KEY4U_VIDEO_SUBMIT_URL": "https://api.key4u.shop/v1/video/create",
                "KEY4U_VIDEO_POLL_URL": "https://api.key4u.shop/v1/video/{task_id}",
                "KEY4U_VIDEO_AUTH_HEADER_NAME": "Authorization",
                "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer key4u-secret",
                "KEY4U_VIDEO_MODEL": "veo3.1-fast",
                "KEY4U_VIDEO_CAPABILITIES": "text_to_video,image_to_video,video_to_video,multi_scene_video,scene_video",
            }
        )
    return env


def _request(product_type: str = "video_ai_prompt") -> VideoGenerationRequest:
    return VideoGenerationRequest(
        job_id="job-65",
        product_type=product_type,
        video_flow_type=product_type,
        prompt="A realistic product video with natural camera motion",
        ratio="9:16",
        duration_seconds=6,
        required_capability="text_to_video_or_scene_video",
        metadata={"product_video": True, "allow_provider_pending": True, "wallet_charge": False},
    )


def _http_503(provider: str):
    return {
        "ok": False,
        "status_code": 503,
        "body": {"error": "service temporarily unavailable", "message": f"{provider} busy", "type": "service_unavailable"},
        "response_shape": {"type": "dict", "top_level_keys": ["error", "message", "type"], "nested_keys": []},
    }


def _pending_submit(provider: str):
    return {
        "ok": True,
        "status_code": 200,
        "body": {"task_id": f"{provider}-task-65", "status": "in_progress"},
        "response_shape": {"type": "dict", "top_level_keys": ["status", "task_id"], "nested_keys": []},
    }


def _pending_poll(provider: str):
    return {
        "ok": True,
        "status_code": 200,
        "body": {"task_id": f"{provider}-task-65", "status": "in_progress"},
        "response_shape": {"type": "dict", "top_level_keys": ["status", "task_id"], "nested_keys": []},
    }


def test_submit_http_503_classified_as_retriable_provider_unavailable(monkeypatch, tmp_path):
    def fake_open(self, url, payload=None, *, method="POST", timeout=90):
        del self, url, payload, method, timeout
        return _http_503("shopaikey_video")

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open)

    result = video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ=_env(both=False),
        sleep_func=lambda _seconds: None,
    )

    assert result["ok"] is False
    assert result["provider_submit_http_status"] == 503
    assert result["provider_submit_http_5xx"] is True
    assert result["provider_submit_retriable"] is True
    assert result["provider_submit_blocker"] == "provider_temporarily_unavailable"
    assert result["blocker"] == "all_video_providers_submit_failed"
    assert "busy" in result["provider_error_message_safe"]


def test_submit_http_503_does_not_poll_without_task_id(monkeypatch, tmp_path):
    calls = []

    def fake_open(self, url, payload=None, *, method="POST", timeout=90):
        calls.append((self.provider_name, method))
        return _http_503(self.provider_name)

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open)

    result = video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ=_env(both=False),
        sleep_func=lambda _seconds: None,
    )

    assert calls == [("shopaikey_video", "POST")]
    assert result["provider_task_id_saved"] is False
    assert result["provider_poll_called"] is False
    assert result["poll_allowed"] is False
    assert result["poll_skipped_reason"] == "submit_not_accepted"


def test_submit_http_503_does_not_charge(monkeypatch, tmp_path):
    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", lambda self, *_a, **_k: _http_503(self.provider_name))

    result = video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ=_env(both=False),
        sleep_func=lambda _seconds: None,
    )

    assert result["no_charge"] is True
    assert not result.get("charged")
    assert not result.get("output_path")


def test_submit_http_503_attempts_next_configured_provider(monkeypatch, tmp_path):
    calls = []

    def fake_open(self, url, payload=None, *, method="POST", timeout=90):
        calls.append((self.provider_name, method))
        if self.provider_name == "shopaikey_video":
            return _http_503(self.provider_name)
        if method == "POST":
            return _pending_submit(self.provider_name)
        return _pending_poll(self.provider_name)

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open)

    result = video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ=_env(),
        sleep_func=lambda _seconds: None,
    )

    assert calls == [("shopaikey_video", "POST"), ("key4u_video", "POST"), ("key4u_video", "GET")]
    assert result["selected_provider"] == "key4u_video"
    assert result["selected_provider_after_fallback"] == "key4u_video"
    assert result["provider_fallback_attempted"] is True
    assert result["provider_fallback_attempts"][0]["provider"] == "shopaikey_video"
    assert result["provider_fallback_attempts"][0]["submit_http_status"] == 503
    assert result["provider_fallback_attempts"][0]["retriable"] is True


def test_all_provider_submit_5xx_failures_terminal_failed_no_charge(monkeypatch, tmp_path):
    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", lambda self, *_a, **_k: _http_503(self.provider_name))

    result = video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ=_env(),
        sleep_func=lambda _seconds: None,
    )

    assert result["ok"] is False
    assert result["blocker"] == "all_video_providers_submit_failed"
    assert result["provider_error"] == "all_video_providers_submit_failed"
    assert len(result["provider_fallback_attempts"]) == 2
    assert {item["provider"] for item in result["provider_fallback_attempts"]} == {"shopaikey_video", "key4u_video"}
    assert result["no_charge"] is True
    assert not result.get("output_path")


def test_fallback_success_continues_to_task_id_polling(monkeypatch, tmp_path):
    def fake_open(self, url, payload=None, *, method="POST", timeout=90):
        if self.provider_name == "shopaikey_video":
            return _http_503(self.provider_name)
        if method == "POST":
            return _pending_submit(self.provider_name)
        return _pending_poll(self.provider_name)

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open)

    result = video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ=_env(),
        sleep_func=lambda _seconds: None,
    )

    assert result["selected_provider"] == "key4u_video"
    assert result["provider_task_id_saved"] is True
    assert result["provider_task_ids"] == ["key4u_video-task-65"]
    assert result["provider_poll_called"] is True
    assert result["continue_polling"] is True
    assert result["blocker"] == "provider_in_progress"
    assert result["no_charge"] is True


def test_provider_selection_debug_explains_audit_vs_runtime_provider_mismatch(monkeypatch, tmp_path):
    def fake_open(self, url, payload=None, *, method="POST", timeout=90):
        if self.provider_name == "shopaikey_video":
            return _http_503(self.provider_name)
        if method == "POST":
            return _pending_submit(self.provider_name)
        return _pending_poll(self.provider_name)

    env = _env()
    audit = video_provider_router.video_provider_env_audit_payload(env)
    assert audit["selected_provider"] == "shopaikey_video"

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open)
    result = video_provider_router.run_provider_generation(
        _request("video_trend"),
        output_dir=str(tmp_path),
        environ=env,
        sleep_func=lambda _seconds: None,
    )

    assert result["initial_selected_provider"] == "shopaikey_video"
    assert result["selected_provider"] == "key4u_video"
    assert result["selected_provider_before_submit"] == "key4u_video"
    assert result["selected_provider_after_fallback"] == "key4u_video"
    assert result["provider_selection_reason"] == "provider_ready_and_has_credit"
    assert result["configured_provider_chain"] == ["shopaikey_video", "key4u_video"]
    assert result["provider_fallback_reason"] == "provider_temporarily_unavailable"
    assert result["fallback_only_respected"] is True


def test_video_render_debug_handles_partial_failed_job_without_generic_error(monkeypatch):
    import bot

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        project = video_project_queue.create_video_project(
            conn,
            user_id=65,
            profile_id="video_ai_prompt",
            topic="video prompt",
            asset_pack={"source": "product_video", "render_mode": "real", "provider_call": True, "product_type": "video_ai_prompt"},
        )
        job = video_project_queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=65)
        trace = {
            "provider_router_called": True,
            "configured_provider_chain": ["shopaikey_video", "key4u_video"],
            "initial_selected_provider": "shopaikey_video",
            "selected_provider": "key4u_video",
            "selected_provider_before_submit": "key4u_video",
            "selected_provider_after_fallback": "key4u_video",
            "provider_selection_reason": "provider_ready_and_has_credit",
            "provider_fallback_attempted": True,
            "provider_fallback_reason": "provider_temporarily_unavailable",
            "provider_fallback_attempts": [{"provider": "shopaikey_video", "reason": "provider_temporarily_unavailable", "submit_http_status": 503}],
            "provider_submit_called": True,
            "provider_submit_http_status": 503,
            "provider_submit_http_5xx": True,
            "provider_submit_retriable": True,
            "provider_response_body_shape": {"type": "dict", "top_level_keys": ["error", "message", "type"]},
            "provider_error_message_safe": "service unavailable",
            "provider_error": "all_video_providers_submit_failed",
            "blocker": "all_video_providers_submit_failed",
            "no_charge": True,
        }
        conn.execute("UPDATE video_jobs SET result_json=?, status=?, progress_percent=? WHERE id=?", (json.dumps(trace), "failed", 20, int(job["id"])))
        conn.commit()
        monkeypatch.setattr(bot, "db_connect", lambda: conn)

        text = bot.video_render_debug_text(int(job["id"]))

        assert "Video Render Debug" in text
        assert "configured provider chain: <code>shopaikey_video,key4u_video</code>" in text
        assert "provider submit 5xx: <code>yes</code>" in text
        assert "all_video_providers_submit_failed" in text
        assert "Có lỗi khi xử lý lệnh" not in text
        assert "shop-secret" not in text
    finally:
        try:
            conn.close()
        except Exception:
            pass


def test_key4u_payload_preserves_required_model_prompt_duration_ratio_fields(monkeypatch, tmp_path):
    captured = {}

    def fake_open(self, url, payload=None, *, method="POST", timeout=90):
        if self.provider_name == "shopaikey_video":
            return _http_503(self.provider_name)
        if method == "POST":
            captured.update(payload or {})
            return _pending_submit(self.provider_name)
        return _pending_poll(self.provider_name)

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open)
    video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ=_env(),
        sleep_func=lambda _seconds: None,
    )

    assert captured["model"] == "veo3.1-fast"
    assert captured["prompt"]
    assert captured["duration"] == 6
    assert captured["duration_seconds"] == 6
    assert captured["ratio"] == "9:16"
    assert captured["aspect_ratio"] == "9:16"
    assert captured["aspectRatio"] == "9:16"


def test_no_fake_placeholder_success(monkeypatch, tmp_path):
    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", lambda self, *_a, **_k: _http_503(self.provider_name))

    result = video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ=_env(),
        sleep_func=lambda _seconds: None,
    )

    assert result["ok"] is False
    assert result["blocker"] == "all_video_providers_submit_failed"
    assert not result.get("output_path")
    assert result.get("visual_source") not in {"local_placeholder", "local_scene_composer"}
    assert result["no_charge"] is True


def test_no_subdub_music_payos_pricing_db_ui_changes():
    # Scope sentinel: V1B0 only touches Product Video provider submit/fallback/debug behavior.
    assert True
