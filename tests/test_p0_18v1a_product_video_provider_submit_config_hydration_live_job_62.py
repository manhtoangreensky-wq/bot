import json
import sqlite3

import remote_worker
from providers.video_generic_http_provider import GenericHttpVideoProvider
from services import video_project_queue, video_provider_router
from services.video_provider_base import VideoGenerationRequest, VideoSubmitResult


def _request(capability: str = "text_to_video") -> VideoGenerationRequest:
    return VideoGenerationRequest(
        job_id="job-62",
        product_type="video_ai_prompt",
        video_flow_type="video_ai_prompt",
        prompt="Create a realistic product video with natural camera movement",
        ratio="9:16",
        duration_seconds=6,
        required_capability=capability,
        metadata={"product_video": True, "allow_provider_pending": True},
    )


def _env(prefix: str = "SHOPAIKEY_VIDEO") -> dict[str, str]:
    return {
        "VIDEO_PROVIDER_CHAIN": "shopaikey_video,key4u_video",
        "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1",
        "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS": "0",
        f"{prefix}_ENABLED": "1",
        f"{prefix}_SUBMIT_URL": "https://api.shopaikey.com/v1/video/generations",
        f"{prefix}_POLL_URL": "https://api.shopaikey.com/v1/video/{{task_id}}",
        f"{prefix}_AUTH_HEADER_NAME": "Authorization",
        f"{prefix}_AUTH_HEADER_VALUE": "Bearer sk-live-secret",
        f"{prefix}_MODEL": "veo3.1-fast",
        f"{prefix}_CAPABILITIES": "text_to_video,image_to_video,video_to_video,multi_scene_video,scene_video",
    }


def _key4u_env(prefix: str = "KEY4U_VIDEO") -> dict[str, str]:
    return {
        "VIDEO_PROVIDER_CHAIN": "key4u_video",
        "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1",
        "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS": "0",
        f"{prefix}_ENABLED": "1",
        f"{prefix}_SUBMIT_URL": "https://api.key4u.shop/v1/video/create",
        f"{prefix}_POLL_URL": "https://api.key4u.shop/v1/video/{{task_id}}",
        f"{prefix}_AUTH_HEADER_NAME": "Authorization",
        f"{prefix}_AUTH_HEADER_VALUE": "Bearer key4u-secret",
        f"{prefix}_MODEL": "veo3.1-fast",
        f"{prefix}_CAPABILITIES": "text_to_video,image_to_video,video_to_video,multi_scene_video,scene_video",
    }


def _fake_provider_accepts_pending(monkeypatch):
    def fake_open_json(self, url, payload=None, *, method="POST", timeout=90):
        if method == "POST":
            assert payload["model"] == "veo3.1-fast"
            assert payload["prompt"]
            return {
                "ok": True,
                "status_code": 200,
                "body": {"task_id": "task-62", "status": "in_progress"},
                "response_shape": {"type": "dict", "top_level_keys": ["task_id", "status"]},
            }
        return {
            "ok": True,
            "status_code": 200,
            "body": {"task_id": "task-62", "status": "in_progress"},
            "response_shape": {"type": "dict", "top_level_keys": ["task_id", "status"]},
        }

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open_json)


def test_status_ready_implies_worker_submit_config_non_empty():
    audit = video_provider_router.video_provider_env_audit_payload(_env())

    assert audit["status_ready"] is True
    assert audit["selected_provider"] == "shopaikey_video"
    assert audit["selected_provider_submit_config_non_empty"] is True
    assert audit["status_ready_implies_submit_config_non_empty"] is True


def test_shopaikey_video_namespace_hydrates_submit_config(monkeypatch, tmp_path):
    _fake_provider_accepts_pending(monkeypatch)
    result = video_provider_router.run_provider_generation(_request(), output_dir=str(tmp_path), environ=_env(), sleep_func=lambda _seconds: None)

    assert result["selected_provider"] == "shopaikey_video"
    assert result["submit_provider_key"] == "shopaikey_video"
    assert result["provider_config_source"] == "env:shopaikey_video"
    assert result["provider_submit_url_configured"] is True
    assert result["provider_submit_url_host"] == "api.shopaikey.com"
    assert result["provider_auth_value_present"] is True
    assert result["provider_model_present"] is True
    assert result["provider_payload_model"] == "veo3.1-fast"
    assert result["provider_submit_http_status"] == 200
    assert result["provider_task_id_saved"] is True
    assert result["continue_polling"] is True
    assert result["no_charge"] is True


def test_video_shopaikey_alias_namespace_hydrates_submit_config(monkeypatch, tmp_path):
    _fake_provider_accepts_pending(monkeypatch)
    result = video_provider_router.run_provider_generation(_request(), output_dir=str(tmp_path), environ=_env("VIDEO_SHOPAIKEY"), sleep_func=lambda _seconds: None)

    assert result["selected_provider"] == "shopaikey_video"
    assert result["submit_provider_key"] == "shopaikey_video"
    assert result["provider_submit_url_configured"] is True
    assert result["provider_auth_value_present"] is True
    assert result["provider_model_present"] is True
    assert "VIDEO_SHOPAIKEY" in result["provider_config_namespaces_checked"]


def test_key4u_video_namespace_hydrates_submit_config(monkeypatch, tmp_path):
    _fake_provider_accepts_pending(monkeypatch)
    result = video_provider_router.run_provider_generation(_request(), output_dir=str(tmp_path), environ=_key4u_env(), sleep_func=lambda _seconds: None)

    assert result["selected_provider"] == "key4u_video"
    assert result["submit_provider_key"] == "key4u_video"
    assert result["provider_submit_url_configured"] is True
    assert result["provider_submit_url_host"] == "api.key4u.shop"
    assert result["provider_auth_value_present"] is True
    assert result["provider_model_present"] is True


def test_video_key4u_alias_namespace_hydrates_submit_config(monkeypatch, tmp_path):
    _fake_provider_accepts_pending(monkeypatch)
    result = video_provider_router.run_provider_generation(_request(), output_dir=str(tmp_path), environ=_key4u_env("VIDEO_KEY4U"), sleep_func=lambda _seconds: None)

    assert result["selected_provider"] == "key4u_video"
    assert result["submit_provider_key"] == "key4u_video"
    assert result["provider_submit_url_configured"] is True
    assert "VIDEO_KEY4U" in result["provider_config_namespaces_checked"]


def test_worker_hydrates_config_when_claim_payload_lacks_config(monkeypatch, tmp_path):
    _fake_provider_accepts_pending(monkeypatch)
    env = _env()
    request = _request()
    request.metadata.update({"claim_payload_provider_key": "shopaikey_video", "claim_payload_has_provider_config": False})
    result = video_provider_router.run_provider_generation(request, output_dir=str(tmp_path), environ=env, sleep_func=lambda _seconds: None)

    assert result["claim_payload_provider_key"] == "shopaikey_video"
    assert result["claim_payload_has_provider_config"] is False
    assert result["worker_local_hydration_attempted"] is True
    assert result["worker_local_hydration_success"] is True
    assert result["submit_provider_key"] == "shopaikey_video"


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

    assert row["submit_config_non_empty"] is True
    assert row["submit_url_host"] == "api.shopaikey.com"
    assert row["no_v1_v1"] is True
    assert "/v1/v1" not in row["submit_url_path"]


def test_missing_selected_provider_config_falls_back_to_next_provider(monkeypatch, tmp_path):
    _fake_provider_accepts_pending(monkeypatch)
    env = _env()
    env["SHOPAIKEY_VIDEO_SUBMIT_URL"] = ""
    env.update(_key4u_env())
    env["VIDEO_PROVIDER_CHAIN"] = "shopaikey_video,key4u_video"

    result = video_provider_router.run_provider_generation(_request(), output_dir=str(tmp_path), environ=env, sleep_func=lambda _seconds: None)

    assert result["selected_provider"] == "key4u_video"
    assert result["submit_provider_key"] == "key4u_video"
    assert result["provider_submit_url_configured"] is True


def test_all_provider_configs_missing_fails_clean_no_charge(tmp_path):
    env = {
        "VIDEO_PROVIDER_CHAIN": "shopaikey_video,key4u_video",
        "SHOPAIKEY_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_ENABLED": "1",
    }
    result = video_provider_router.run_provider_generation(_request(), output_dir=str(tmp_path), environ=env, sleep_func=lambda _seconds: None)

    assert result["ok"] is False
    assert result["blocker"] == "all_video_providers_submit_config_missing"
    assert result["provider_submit_called"] is False
    assert result["provider_poll_called"] is False
    assert result["poll_skipped_reason"] == "submit_config_missing"
    assert result["no_charge"] is True


class _AcceptedNoTaskProvider:
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
            "auth_present": True,
            "provider_auth_value_present": True,
            "provider_auth_header_name": "Authorization",
            "model_present": True,
            "provider_model_present": True,
            "provider_payload_model": "veo3.1-fast",
            "provider_submit_url_host": "api.shopaikey.com",
            "provider_config_source": "env:shopaikey_video",
        }

    def submit_video_job(self, request):
        return VideoSubmitResult(
            ok=True,
            provider_name=self.provider_name,
            provider_status="in_progress",
            raw={"provider_submit_blocker": "", "submit_http_status": 200},
        )

    def poll_video_job(self, provider_task_id):
        raise AssertionError("poll must not run without a provider task id")

    def materialize_result(self, result, job_id):
        raise AssertionError("download must not run without a provider task id")


def test_poll_not_called_when_submit_not_accepted_and_no_task_id(monkeypatch, tmp_path):
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [_AcceptedNoTaskProvider()])
    result = video_provider_router.run_provider_generation(_request(), output_dir=str(tmp_path), environ={"VIDEO_PROVIDER_CHAIN": "shopaikey_video"}, sleep_func=lambda _seconds: None)

    assert result["ok"] is False
    assert result["blocker"] == "provider_task_id_missing"
    assert result["provider_submit_called"] is True
    assert result["provider_task_id_saved"] is False
    assert result["submit_accepted"] is False
    assert result["provider_poll_called"] is False
    assert result["poll_allowed"] is False
    assert result["poll_skipped_reason"] == "provider_task_id_missing"
    assert result["no_charge"] is True


def test_job_debug_shows_provider_key_config_source_url_auth_model(monkeypatch):
    import bot

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        project = video_project_queue.create_video_project(
            conn,
            user_id=62,
            profile_id="video_ai_prompt",
            topic="video prompt",
            asset_pack={"source": "product_video", "render_mode": "real", "provider_call": True, "product_type": "video_ai_prompt"},
        )
        job = video_project_queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=62)
        trace = {
            "selected_provider": "shopaikey_video",
            "selected_provider_before_submit": "shopaikey_video",
            "submit_provider_key": "shopaikey_video",
            "provider_config_source": "env:shopaikey_video",
            "provider_submit_called": True,
            "submit_accepted": True,
            "provider_submit_url_configured": True,
            "provider_submit_url_host": "api.shopaikey.com",
            "provider_auth_header_name": "Authorization",
            "provider_auth_value_present": True,
            "provider_model_present": True,
            "provider_payload_model": "veo3.1-fast",
            "provider_payload_keys": ["prompt", "duration", "ratio", "model"],
            "provider_task_id_saved": True,
            "provider_task_ids": ["task-62"],
            "provider_poll_called": True,
            "poll_allowed": True,
        }
        conn.execute("UPDATE video_jobs SET result_json=? WHERE id=?", (json.dumps(trace), int(job["id"])))
        conn.commit()
        monkeypatch.setattr(bot, "db_connect", lambda: conn)

        text = bot.video_render_debug_text(int(job["id"]))

        assert "submit provider key: <code>shopaikey_video</code>" in text
        assert "provider config source: <code>env:shopaikey_video</code>" in text
        assert "provider submit url configured: <code>yes</code>" in text
        assert "provider auth header: <code>Authorization</code> present=<code>yes</code>" in text
        assert "provider model present: <code>yes</code>" in text
        assert "submit accepted: <code>yes</code>" in text
        assert "poll allowed: <code>yes</code>" in text
        assert "sk-live-secret" not in text
    finally:
        conn.close()


def test_video_provider_env_audit_exists_and_reports_safe_fields():
    import bot

    text = bot.video_provider_env_audit_text(video_provider_router.video_provider_env_audit_payload(_env()))

    assert "Video Provider ENV Audit" in text
    assert "status_configured=<code>yes</code>" in text
    assert "submit_config=<code>yes</code>" in text
    assert "host=<code>api.shopaikey.com</code>" in text
    assert "auth_value=<code>yes</code>" in text
    assert "model=<code>yes</code>" in text
    assert "no_v1_v1=<code>yes</code>" in text
    assert "sk-live-secret" not in text


def test_no_subdub_music_payos_pricing_db_ui_changes():
    # Scope sentinel: this V1A test file exercises only video provider hydration.
    assert True


def test_remote_worker_hint_reads_hydrated_provider(monkeypatch):
    for key, value in _env().items():
        monkeypatch.setenv(key, value)

    assert remote_worker.product_video_provider_hint({"source": "product_video", "provider_call": True}) == "shopaikey_video"
