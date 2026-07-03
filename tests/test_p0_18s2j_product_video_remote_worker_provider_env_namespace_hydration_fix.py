import json
import os
import subprocess

import pytest

import pytest

from providers.video_generic_http_provider import GenericHttpVideoProvider
from services import video_provider_router
from services.video_provider_base import VideoGenerationRequest, VideoSubmitResult


def _request(provider: str = "shopaikey_video") -> VideoGenerationRequest:
    return VideoGenerationRequest(
        job_id="job-s2j",
        product_type="video_ai_prompt",
        video_flow_type="video_ai_prompt",
        prompt="Create a short realistic vertical product video",
        ratio="9:16",
        duration_seconds=6,
        required_capability="text_to_video",
        metadata={"product_video": True, "allow_provider_pending": True, "claim_payload_provider_key": provider},
    )


def _current_branch_name() -> str:
    for key in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME", "BRANCH_NAME"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return subprocess.check_output(
        ["git", "branch", "--show-current"],
        text=True,
        encoding="utf-8",
    ).strip()


def _is_product_video_s2j_scope() -> bool:
    branch = _current_branch_name().lower()
    branch_tokens = (
        "p0-18s2j",
        "s2j-product-video",
        "product-video-remote-worker-provider",
        "remote-worker-provider-env",
        "provider-env-namespace-hydration",
        "video-provider-submit-config-hydration",
    )
    return any(token in branch for token in branch_tokens)


def _shopaikey_env(prefix: str = "SHOPAIKEY_VIDEO") -> dict[str, str]:
    return {
        "VIDEO_PROVIDER_CHAIN": "shopaikey_video",
        f"{prefix}_ENABLED": "1",
        f"{prefix}_SUBMIT_URL": "https://api.shopaikey.com/v1/video/generations",
        f"{prefix}_POLL_URL": "https://api.shopaikey.com/v1/video/{task_id}",
        f"{prefix}_AUTH_HEADER_NAME": "Authorization",
        f"{prefix}_AUTH_HEADER_VALUE": "Bearer sk-shopaikey-secret",
        f"{prefix}_MODEL": "veo3.1-fast",
        f"{prefix}_CAPABILITIES": "text_to_video,image_to_video,video_to_video,multi_scene_video,scene_video",
        "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1",
        "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS": "0",
    }


def _key4u_env(prefix: str = "KEY4U_VIDEO") -> dict[str, str]:
    return {
        "VIDEO_PROVIDER_CHAIN": "key4u_video",
        f"{prefix}_ENABLED": "1",
        f"{prefix}_SUBMIT_URL": "https://api.key4u.shop/v1/video/create",
        f"{prefix}_POLL_URL": "https://api.key4u.shop/v1/video/{task_id}",
        f"{prefix}_AUTH_HEADER_NAME": "Authorization",
        f"{prefix}_AUTH_HEADER_VALUE": "Bearer key4u-secret",
        f"{prefix}_MODEL": "veo3.1-fast",
        f"{prefix}_CAPABILITIES": "text_to_video,image_to_video,video_to_video,multi_scene_video,scene_video",
        "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1",
        "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS": "0",
    }


def _fake_pending_open_json(self, url, payload=None, *, method="POST", timeout=90):
    assert self.provider_name in {"shopaikey_video", "key4u_video"}
    assert url.startswith("https://")
    if method == "POST":
        assert payload["prompt"]
        assert payload["model"] == "veo3.1-fast"
        return {
            "ok": True,
            "status_code": 200,
            "body": {"task_id": f"{self.provider_name}-task", "status": "in_progress"},
            "response_shape": {"type": "dict", "top_level_keys": ["status", "task_id"]},
        }
    return {
        "ok": True,
        "status_code": 200,
        "body": {"task_id": f"{self.provider_name}-task", "status": "in_progress"},
        "response_shape": {"type": "dict", "top_level_keys": ["status", "task_id"]},
    }


def _run(env: dict[str, str], monkeypatch, tmp_path, provider: str = "shopaikey_video") -> dict:
    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", _fake_pending_open_json)
    return video_provider_router.run_provider_generation(
        _request(provider),
        output_dir=str(tmp_path),
        environ=env,
        sleep_func=lambda _seconds: None,
    )


def test_shopaikey_video_namespace_hydrates_submit_config(monkeypatch, tmp_path):
    result = _run(_shopaikey_env("SHOPAIKEY_VIDEO"), monkeypatch, tmp_path)

    assert result["selected_provider"] == "shopaikey_video"
    assert result["submit_provider_key"] == "shopaikey_video"
    assert result["provider_submit_url_configured"] is True
    assert result["provider_submit_url_host"] == "api.shopaikey.com"
    assert result["provider_auth_value_present"] is True
    assert result["provider_model_present"] is True
    assert result["provider_payload_model"] == "veo3.1-fast"
    assert result["worker_local_hydration_success"] is True
    assert result["provider_task_id_saved"] is True
    assert result["continue_polling"] is True


def test_video_shopaikey_alias_namespace_hydrates_submit_config(monkeypatch, tmp_path):
    result = _run(_shopaikey_env("VIDEO_SHOPAIKEY"), monkeypatch, tmp_path)

    assert result["selected_provider"] == "shopaikey_video"
    assert result["submit_provider_key"] == "shopaikey_video"
    assert result["provider_submit_url_host"] == "api.shopaikey.com"
    assert result["provider_auth_value_present"] is True
    assert result["provider_model_present"] is True
    assert "VIDEO_SHOPAIKEY" in result["selected_provider_alias_prefixes_checked"]


def test_key4u_video_namespace_hydrates_submit_config(monkeypatch, tmp_path):
    result = _run(_key4u_env("KEY4U_VIDEO"), monkeypatch, tmp_path, provider="key4u_video")

    assert result["selected_provider"] == "key4u_video"
    assert result["submit_provider_key"] == "key4u_video"
    assert result["provider_submit_url_host"] == "api.key4u.shop"
    assert result["provider_auth_value_present"] is True
    assert result["provider_model_present"] is True


def test_video_key4u_alias_namespace_hydrates_submit_config(monkeypatch, tmp_path):
    result = _run(_key4u_env("VIDEO_KEY4U"), monkeypatch, tmp_path, provider="key4u_video")

    assert result["selected_provider"] == "key4u_video"
    assert result["submit_provider_key"] == "key4u_video"
    assert result["provider_submit_url_host"] == "api.key4u.shop"
    assert result["provider_auth_value_present"] is True
    assert result["provider_model_present"] is True
    assert "VIDEO_KEY4U" in result["selected_provider_alias_prefixes_checked"]


def test_provider_status_ready_implies_submit_config_non_empty():
    status = video_provider_router.provider_status_payload(_shopaikey_env("VIDEO_SHOPAIKEY"))
    provider = next(item for item in status["providers"] if item["provider"] == "shopaikey_video")

    assert provider["configured"] is True
    assert provider["submit_url_configured"] is True
    assert provider["auth_present"] is True
    assert provider["model_present"] is True
    assert provider["provider_submit_url_host"] == "api.shopaikey.com"


def test_remote_worker_submit_uses_same_provider_registry_as_status(monkeypatch, tmp_path):
    env = _shopaikey_env("VIDEO_SHOPAIKEY")
    status = video_provider_router.provider_status_payload(env)
    result = _run(env, monkeypatch, tmp_path)

    assert status["first_ready_provider"] == result["selected_provider"]
    assert result["selected_provider_config_source"]
    assert result["provider_submit_url_configured"] is True


def test_worker_hydrates_config_locally_when_claim_payload_lacks_config(monkeypatch, tmp_path):
    env = _shopaikey_env("VIDEO_SHOPAIKEY")
    result = _run(env, monkeypatch, tmp_path)

    assert result["claim_payload_has_provider_config"] is False
    assert result["worker_local_hydration_attempted"] is True
    assert result["worker_local_hydration_success"] is True


def test_no_v1_v1_when_joining_shopaikey_base_and_endpoint():
    env = {
        "VIDEO_PROVIDER_CHAIN": "shopaikey_video",
        "SHOPAIKEY_VIDEO_ENABLED": "1",
        "SHOPAIKEY_BASE_URL": "https://api.shopaikey.com/v1",
        "SHOPAIKEY_VIDEO_ENDPOINT": "/v1/video/generations",
        "SHOPAIKEY_VIDEO_POLL_ENDPOINT": "/v1/video/{task_id}",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE": "Bearer sk-shopaikey-secret",
        "SHOPAIKEY_VIDEO_MODEL": "veo3.1-fast",
    }
    status = video_provider_router.provider_status_payload(env)
    provider = next(item for item in status["providers"] if item["provider"] == "shopaikey_video")

    assert provider["provider_submit_url_host"] == "api.shopaikey.com"
    assert "/v1/v1" not in provider["provider_submit_url_path"]
    assert provider["provider_submit_url_path"] == "/v1/video/generations"


def test_submit_debug_shows_provider_key_and_config_source(monkeypatch, tmp_path):
    result = _run(_shopaikey_env("VIDEO_SHOPAIKEY"), monkeypatch, tmp_path)
    raw = json.dumps(result, ensure_ascii=False)

    assert result["submit_provider_key"] == "shopaikey_video"
    assert result["selected_provider_config_source"]
    assert result["provider_config_namespaces_checked"] == ["SHOPAIKEY_VIDEO", "VIDEO_SHOPAIKEY"]
    assert "sk-shopaikey-secret" not in raw


class _MissingConfigProvider:
    def __init__(self, provider_name: str):
        self.provider_name = provider_name

    def capabilities(self):
        return {
            "provider": self.provider_name,
            "enabled": True,
            "configured": True,
            "capabilities": ["text_to_video"],
            "submit_url_configured": True,
            "poll_url_configured": True,
            "auth_configured": True,
            "provider_config_source": f"env:{self.provider_name}",
        }

    def submit_video_job(self, request):
        return VideoSubmitResult(
            ok=False,
            provider_name=self.provider_name,
            provider_status="config_invalid",
            error_code="provider_config_missing_at_submit",
            raw={
                "selected_provider_before_submit": self.provider_name,
                "submit_provider_key": self.provider_name,
                "provider_submit_blocker": "provider_config_missing_at_submit",
                "provider_submit_url_configured": False,
                "provider_auth_value_present": False,
                "provider_model_present": False,
            },
        )

    def poll_video_job(self, provider_task_id):
        raise AssertionError("poll should not run")

    def materialize_result(self, result, job_id):
        raise AssertionError("download should not run")


class _PendingProvider(_MissingConfigProvider):
    def submit_video_job(self, request):
        return VideoSubmitResult(
            ok=True,
            provider_name=self.provider_name,
            provider_task_id=f"{self.provider_name}-task",
            provider_status="in_progress",
            raw={
                "selected_provider_before_submit": self.provider_name,
                "submit_provider_key": self.provider_name,
                "provider_submit_url_configured": True,
                "provider_submit_url_host": "api.key4u.shop",
                "provider_auth_value_present": True,
                "provider_model_present": True,
                "provider_payload_model": "veo3.1-fast",
                "submit_http_status": 200,
            },
        )

    def poll_video_job(self, provider_task_id):
        from services.video_provider_base import VideoPollResult

        return VideoPollResult(ok=True, provider_name=self.provider_name, provider_task_id=provider_task_id, status="running")


def test_selected_provider_config_missing_falls_back_to_next_provider(monkeypatch, tmp_path):
    monkeypatch.setattr(
        video_provider_router,
        "load_video_provider_adapters",
        lambda _env=None: [_MissingConfigProvider("shopaikey_video"), _PendingProvider("key4u_video")],
    )
    result = video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ={"VIDEO_PROVIDER_CHAIN": "shopaikey_video,key4u_video"},
        sleep_func=lambda _seconds: None,
    )

    assert result["selected_provider"] == "key4u_video"
    assert result["fallback_used"] is True
    assert result["fallback_reason"] == "provider_config_missing_at_submit"
    assert result["provider_chain_fallback_attempted"] is True
    assert result["continue_polling"] is True


def test_all_provider_config_missing_fails_clean_no_charge(monkeypatch, tmp_path):
    monkeypatch.setattr(
        video_provider_router,
        "load_video_provider_adapters",
        lambda _env=None: [_MissingConfigProvider("shopaikey_video"), _MissingConfigProvider("key4u_video")],
    )
    result = video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ={"VIDEO_PROVIDER_CHAIN": "shopaikey_video,key4u_video"},
        sleep_func=lambda _seconds: None,
    )

    assert result["ok"] is False
    assert result["blocker"] == "all_video_providers_submit_config_missing"
    assert result["no_charge"] is True


def test_video_provider_env_audit_passes():
    audit = video_provider_router.video_provider_env_audit_payload(_shopaikey_env("VIDEO_SHOPAIKEY"))

    assert audit["ok"] is True
    assert audit["selected_provider"] == "shopaikey_video"
    assert audit["selected_provider_submit_config_non_empty"] is True
    assert any(row["provider"] == "shopaikey_video" and row["submit_config_non_empty"] for row in audit["rows"])


def test_no_payos_music_subdub_voice_pricing_changes():
    import pathlib

    if not _is_product_video_s2j_scope():
        pytest.skip("Product Video S2J scope guard is not active for this branch")

    branch = subprocess.check_output(["git", "branch", "--show-current"], text=True).strip().lower()
    if "p0-18s2j" not in branch:
        pytest.skip("S2J diff scope guard only runs on the S2J branch")
    diff = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True)
    changed = {pathlib.PurePosixPath(line.strip()).as_posix() for line in diff.splitlines() if line.strip()}

    forbidden_markers = ("payos", "wallet", "music", "suno", "subtitle", "subdub", "voice", "pricing", "finance", "linkdl")
    assert not [path for path in changed if any(marker in path.lower() for marker in forbidden_markers)]
