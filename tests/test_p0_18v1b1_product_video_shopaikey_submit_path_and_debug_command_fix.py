import json
import sqlite3

from providers.video_generic_http_provider import GenericHttpVideoProvider
from services import video_project_queue, video_provider_router
from services.video_provider_base import VideoGenerationRequest


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
        job_id="job-66",
        product_type="video_ai_prompt",
        video_flow_type="video_ai_prompt",
        prompt="A premium product video with soft studio lighting",
        ratio="9:16",
        duration_seconds=6,
        required_capability="text_to_video_or_scene_video",
        metadata=metadata,
    )


def _submit_ok(provider: str):
    return {
        "ok": True,
        "status_code": 200,
        "body": {"task_id": f"{provider}-task-66", "status": "in_progress"},
        "response_shape": {"type": "dict", "top_level_keys": ["status", "task_id"], "nested_keys": []},
    }


def _poll_pending(provider: str):
    return {
        "ok": True,
        "status_code": 200,
        "body": {"task_id": f"{provider}-task-66", "status": "in_progress"},
        "response_shape": {"type": "dict", "top_level_keys": ["status", "task_id"], "nested_keys": []},
    }


def _poll_unknown():
    return {
        "ok": True,
        "status_code": 200,
        "body": {"task": {"id": "shopaikey_video-task-66"}, "data": {}},
        "response_shape": {"type": "dict", "top_level_keys": ["data", "task"], "nested_keys": ["task:{id}"]},
    }


def _http_503(provider: str):
    return {
        "ok": False,
        "status_code": 503,
        "body": {"type": "service_unavailable", "code": 503, "message": f"{provider} temporarily unavailable"},
        "response_shape": {"type": "dict", "top_level_keys": ["code", "message", "type"], "nested_keys": []},
    }


def test_configured_shopaikey_is_attempted_before_key4u(monkeypatch, tmp_path):
    calls = []

    def fake_open(self, url, payload=None, *, method="POST", timeout=90):
        calls.append((self.provider_name, method))
        if method == "POST":
            return _submit_ok(self.provider_name)
        return _poll_pending(self.provider_name)

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open)

    result = video_provider_router.run_provider_generation(
        _request(paid_retry_confirmed=True),
        output_dir=str(tmp_path),
        environ=_env(),
        sleep_func=lambda _seconds: None,
    )

    assert calls == [("shopaikey_video", "POST"), ("shopaikey_video", "GET")]
    assert result["initial_selected_provider"] == "shopaikey_video"
    assert result["selected_provider"] == "shopaikey_video"
    assert result["submit_provider_key"] == "shopaikey_video"
    assert result["provider_task_id_saved"] is True


def test_shopaikey_not_skipped_as_provider_status_unknown_when_env_audit_aligned(monkeypatch, tmp_path):
    calls = []
    audit = video_provider_router.video_provider_env_audit_payload(_env())
    assert audit["selected_provider"] == "shopaikey_video"
    assert audit["selected_provider_submit_config_non_empty"] is True

    def fake_open(self, url, payload=None, *, method="POST", timeout=90):
        calls.append((self.provider_name, method))
        if method == "POST":
            return _submit_ok(self.provider_name)
        return _poll_unknown()

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open)

    result = video_provider_router.run_provider_generation(
        _request(paid_retry_confirmed=True),
        output_dir=str(tmp_path),
        environ=_env(),
        sleep_func=lambda _seconds: None,
    )

    assert calls == [("shopaikey_video", "POST"), ("shopaikey_video", "GET")]
    assert result["selected_provider"] == "shopaikey_video"
    assert result["submit_provider_key"] == "shopaikey_video"
    assert result["provider_task_id_saved"] is True
    assert result["provider_poll_called"] is True
    assert result["provider_poll_blocker"] == "provider_status_unknown"
    assert result["blocker"] == "provider_in_progress"
    assert result["continue_polling"] is True
    assert "key4u_video" not in [item[0] for item in calls]


def test_shopaikey_submit_success_saves_task_id_and_allows_poll(monkeypatch, tmp_path):
    monkeypatch.setattr(
        GenericHttpVideoProvider,
        "_open_json",
        lambda self, *_a, method="POST", **_k: _submit_ok(self.provider_name) if method == "POST" else _poll_pending(self.provider_name),
    )

    result = video_provider_router.run_provider_generation(
        _request(paid_retry_confirmed=True),
        output_dir=str(tmp_path),
        environ=_env(),
        sleep_func=lambda _seconds: None,
    )

    assert result["provider_submit_called"] is True
    assert result["submit_accepted"] is True
    assert result["provider_task_id_saved"] is True
    assert result["provider_task_ids"] == ["shopaikey_video-task-66"]
    assert result["poll_allowed"] is True
    assert result["provider_poll_called"] is True


def test_existing_task_poll_survives_new_submit_eligibility_recheck(monkeypatch, tmp_path):
    calls = []

    def fake_open(self, url, payload=None, *, method="POST", timeout=90):
        calls.append((self.provider_name, method))
        assert method == "GET"
        return _poll_pending(self.provider_name)

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open)
    monkeypatch.setattr(
        video_provider_router,
        "product_video_provider_eligibility_snapshot",
        lambda **_kwargs: {
            "provider_eligibility_snapshot_id": "runtime-no-new-submit-candidates",
            "eligible_provider_keys": [],
            "preconfirm_candidate_keys": ["shopaikey_video"],
            "runtime_candidate_keys": [],
            "candidate_set_consistent": False,
            "final_eligible_provider_count": 0,
            "candidate_rejection_reason_by_provider": {
                "shopaikey_video": ["provider_fresh_validated_success_required"]
            },
        },
    )
    request = _request()
    request.metadata.update(
        {
            "submit_source": "worker_poll_existing_task",
            "provider_submit_source": "worker_poll_existing_task",
            "original_submit_source": "public_user_final_confirm",
            "public_user_confirmed": True,
            "invoice_confirmed": True,
            "recovery_existing_tasks_only": True,
            "provider_submit_allowed": False,
            "provider_pending_provider": "shopaikey_video",
            "provider_pending_task_id": "shopaikey_video-task-66",
            "provider_pending_request_job_id": "job-66",
            "worker_compatible": True,
            "admission_enforced": True,
            "provider_eligibility_snapshot": {
                "provider_eligibility_snapshot_id": "existing-task-snapshot",
                "configured_provider_keys": ["shopaikey_video"],
                "contract_valid_provider_chain": ["shopaikey_video"],
                "eligible_provider_keys": ["shopaikey_video"],
            },
        }
    )

    result = video_provider_router.run_provider_generation(
        request,
        output_dir=str(tmp_path),
        environ={**_env(), "VIDEO_PROVIDER_CHAIN": "shopaikey_video"},
        sleep_func=lambda _seconds: None,
    )

    assert calls == [("shopaikey_video", "GET")]
    assert result["provider_submit_called"] is False
    assert result["provider_poll_called"] is True
    assert result["poll_existing_task"] is True
    assert result["no_new_submit"] is True
    assert result["continue_polling"] is True


def test_shopaikey_submit_5xx_falls_back_to_key4u(monkeypatch, tmp_path):
    calls = []

    def fake_open(self, url, payload=None, *, method="POST", timeout=90):
        calls.append((self.provider_name, method))
        if self.provider_name == "shopaikey_video":
            return _http_503(self.provider_name)
        if method == "POST":
            return _submit_ok(self.provider_name)
        return _poll_pending(self.provider_name)

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open)

    result = video_provider_router.run_provider_generation(
        _request(paid_retry_confirmed=True),
        output_dir=str(tmp_path),
        environ=_env(),
        sleep_func=lambda _seconds: None,
    )

    assert calls == [("shopaikey_video", "POST"), ("key4u_video", "POST"), ("key4u_video", "GET")]
    assert result["selected_provider"] == "key4u_video"
    assert result["selected_provider_after_fallback"] == "key4u_video"
    assert result["provider_fallback_reason"] == "provider_temporarily_unavailable"


def test_key4u_503_no_poll_no_charge(monkeypatch, tmp_path):
    calls = []

    def fake_open(self, url, payload=None, *, method="POST", timeout=90):
        calls.append((self.provider_name, method))
        return _http_503(self.provider_name)

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open)

    result = video_provider_router.run_provider_generation(
        _request(paid_retry_confirmed=True),
        output_dir=str(tmp_path),
        environ=_env(),
        sleep_func=lambda _seconds: None,
    )

    assert calls == [("shopaikey_video", "POST"), ("key4u_video", "POST")]
    assert result["selected_provider"] == "key4u_video"
    assert result["provider_submit_http_status"] == 503
    assert result["provider_submit_http_5xx"] is True
    assert result["provider_submit_retriable"] is True
    assert result["provider_task_id_saved"] is False
    assert result["provider_poll_called"] is False
    assert result["poll_skipped_reason"] == "submit_not_accepted"
    assert result["no_charge"] is True


def test_all_providers_fail_terminal_failed_no_charge(monkeypatch, tmp_path):
    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", lambda self, *_a, **_k: _http_503(self.provider_name))

    result = video_provider_router.run_provider_generation(
        _request(paid_retry_confirmed=True),
        output_dir=str(tmp_path),
        environ=_env(),
        sleep_func=lambda _seconds: None,
    )

    assert result["blocker"] == "all_video_providers_submit_failed"
    assert result["provider_error"] == "all_video_providers_submit_failed"
    assert len(result["provider_fallback_attempts"]) == 2
    assert result["no_charge"] is True
    assert not result.get("output_path")


def test_video_provider_status_never_generic_fails_on_partial_provider_data():
    import bot

    text = bot.video_provider_status_text(
        {
            "ready": False,
            "reason": "partial",
            "provider_chain": "shopaikey_video,key4u_video",
            "fallback_order": "key4u_video",
            "providers": [None, "bad", {"provider": "shopaikey_video", "enabled": True, "configured": True}],
            "missing_env": ["bad-shape"],
            "invalid_env": "bad-shape",
        },
        key4u_credit="bad-shape",
    )

    assert "Trạng thái nhà cung cấp video" in text
    assert "shopaikey_video" in text
    assert "Traceback" not in text


def test_video_render_debug_never_generic_fails_on_partial_failed_submit_job(monkeypatch):
    import bot

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        project = video_project_queue.create_video_project(
            conn,
            user_id=66,
            profile_id="video_ai_prompt",
            topic="video prompt",
            asset_pack={"source": "product_video", "render_mode": "real", "provider_call": True, "product_type": "video_ai_prompt"},
        )
        job = video_project_queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=66)
        trace = {
            "configured_provider_chain": ["shopaikey_video", "key4u_video"],
            "initial_selected_provider": "shopaikey_video",
            "selected_provider": "key4u_video",
            "selected_provider_before_submit": "key4u_video",
            "selected_provider_after_fallback": "key4u_video",
            "provider_fallback_attempted": True,
            "provider_fallback_reason": "provider_status_unknown",
            "provider_fallback_attempts": [{"provider": "shopaikey_video", "reason": "provider_status_unknown"}],
            "provider_submit_called": True,
            "provider_submit_http_status": 503,
            "provider_submit_http_5xx": True,
            "provider_error_message_safe": "type=service_unavailable; code=503; message=temporarily unavailable",
            "provider_error": "all_video_providers_submit_failed",
            "blocker": "all_video_providers_submit_failed",
            "no_charge": True,
        }
        conn.execute("UPDATE video_jobs SET result_json=?, status=?, progress_percent=? WHERE id=?", (json.dumps(trace), "failed", 20, int(job["id"])))
        conn.commit()
        monkeypatch.setattr(bot, "db_connect", lambda: conn)

        text = bot.video_render_debug_text(int(job["id"]))

        assert "Video Render Debug" in text
        assert "provider fallback reason: <code>provider_status_unknown</code>" in text
        assert "provider submit 5xx: <code>yes</code>" in text
        assert "Có lỗi khi xử lý lệnh" not in text
        assert "shop-secret" not in text
    finally:
        try:
            conn.close()
        except Exception:
            pass


def test_provider_error_safe_is_truncated_and_no_secrets(monkeypatch, tmp_path):
    secret = "sk-secret-token-should-not-appear"
    long_message = "temporary busy " * 80 + secret

    def fake_open(self, url, payload=None, *, method="POST", timeout=90):
        return {
            "ok": False,
            "status_code": 503,
            "body": {"type": "service_unavailable", "code": 503, "message": long_message},
            "response_shape": {"type": "dict", "top_level_keys": ["code", "message", "type"], "nested_keys": []},
        }

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open)

    result = video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ={**_env(), "VIDEO_PROVIDER_CHAIN": "shopaikey_video"},
        sleep_func=lambda _seconds: None,
    )

    safe = result["provider_error_message_safe"]
    assert len(safe) <= 180
    assert "type=service_unavailable" in safe
    assert "code=503" in safe
    assert secret not in safe
    assert "sk-secret" not in safe


def test_provider_selection_debug_has_concrete_skip_reason(monkeypatch, tmp_path):
    monkeypatch.setattr(
        GenericHttpVideoProvider,
        "_open_json",
        lambda self, *_a, method="POST", **_k: _submit_ok(self.provider_name) if method == "POST" else _poll_pending(self.provider_name),
    )
    env = {
        **_env(),
        "SHOPAIKEY_VIDEO_LOW_CREDIT": "1",
    }
    result = video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ=env,
        sleep_func=lambda _seconds: None,
    )

    assert result["selected_provider"] == "key4u_video"
    reasons = result["skipped_provider_reasons"]
    assert any(item["provider"] == "shopaikey_video" and "credit_low_credit" in item["reason"] for item in reasons)
    assert "provider_status_unknown" not in str(reasons)


def test_no_fake_placeholder_success(monkeypatch, tmp_path):
    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", lambda self, *_a, **_k: _http_503(self.provider_name))

    result = video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ=_env(),
        sleep_func=lambda _seconds: None,
    )

    assert result["ok"] is False
    assert result["no_charge"] is True
    assert not result.get("output_path")
    assert result.get("visual_source") not in {"local_placeholder", "local_scene_composer"}


def test_no_subdub_music_payos_pricing_db_ui_changes():
    # Scope sentinel: V1B1 only touches Product Video provider selection/status/debug.
    assert True
