import bot
from services import video_provider_router
from services.video_provider_base import VideoGenerationRequest


def _provider(payload: dict, name: str) -> dict:
    for item in payload.get("providers") or []:
        if item.get("provider") == name:
            return item
    raise AssertionError(f"provider not found: {name}")


def _request() -> VideoGenerationRequest:
    return VideoGenerationRequest(
        job_id="s2c",
        product_type="video_ai_prompt",
        video_flow_type="video_ai_prompt",
        prompt="A clean product video with real AI visuals",
        ratio="9:16",
        duration_seconds=4,
        required_capability="text_to_video",
        metadata={"wallet_charge": False},
    )


def _placeholder_env(provider: str = "shopaikey_video") -> dict[str, str]:
    prefix = "SHOPAIKEY" if provider == "shopaikey_video" else "KEY4U"
    return {
        "VIDEO_PROVIDER_CHAIN": provider,
        f"{prefix}_VIDEO_ENABLED": "true",
        f"{prefix}_VIDEO_SUBMIT_URL": "submit_url_th\u1eadt",
        f"{prefix}_VIDEO_POLL_URL": "poll_url_th\u1eadt",
        f"{prefix}_VIDEO_AUTH_HEADER_NAME": "Authorization",
        f"{prefix}_VIDEO_AUTH_HEADER_VALUE": "changeme",
    }


def _valid_env(provider: str = "shopaikey_video") -> dict[str, str]:
    prefix = "SHOPAIKEY" if provider == "shopaikey_video" else "KEY4U"
    return {
        "VIDEO_PROVIDER_CHAIN": provider,
        f"{prefix}_VIDEO_ENABLED": "true",
        f"{prefix}_VIDEO_SUBMIT_URL": f"https://{provider}.invalid/submit",
        f"{prefix}_VIDEO_POLL_URL": f"https://{provider}.invalid/poll/{{task_id}}",
        f"{prefix}_VIDEO_AUTH_HEADER_NAME": "Authorization",
        f"{prefix}_VIDEO_AUTH_HEADER_VALUE": "Bearer real-token",
    }


def test_provider_with_submit_url_placeholder_is_not_configured():
    payload = video_provider_router.provider_status_payload(_placeholder_env("shopaikey_video"))
    item = _provider(payload, "shopaikey_video")
    assert item["configured"] is False
    assert item["blocker"] == "provider_config_placeholder_or_invalid_url"
    assert "submit_url" in item["invalid_fields"]
    assert "poll_url" in item["invalid_fields"]
    assert "auth" in item["invalid_fields"]
    assert "SHOPAIKEY_VIDEO_SUBMIT_URL" in item["invalid_env"]
    assert payload["ready"] is False


def test_provider_with_missing_scheme_is_not_configured():
    env = _valid_env("key4u_video")
    env["KEY4U_VIDEO_SUBMIT_URL"] = "video-provider.invalid/submit"
    payload = video_provider_router.provider_status_payload(env)
    item = _provider(payload, "key4u_video")
    assert item["configured"] is False
    assert item["blocker"] == "provider_config_placeholder_or_invalid_url"
    assert item["invalid_fields"] == ["submit_url"]
    assert payload["first_ready_provider"] == ""


def test_provider_with_https_submit_poll_auth_is_configured():
    payload = video_provider_router.provider_status_payload(_valid_env("shopaikey_video"))
    item = _provider(payload, "shopaikey_video")
    assert item["configured"] is True
    assert item["submit_url_configured"] is True
    assert item["poll_url_configured"] is True
    assert item["auth_configured"] is True
    assert payload["first_ready_provider"] == "shopaikey_video"


def test_video_provider_status_does_not_report_ready_for_placeholder_config():
    payload = video_provider_router.provider_status_payload(_placeholder_env("shopaikey_video"))
    text = bot.video_provider_status_text(payload)
    assert payload["ready"] is False
    assert payload["configured_count"] == 0
    assert "Provider đầu tiên: <code>-</code>" in text
    assert "configured=<code>no</code>" in text
    assert "blocker=<code>provider_config_placeholder_or_invalid_url</code>" in text
    assert "invalid_fields=<code>submit_url,poll_url,auth</code>" in text


def test_video_provider_smoke_returns_config_validation_blocker_not_valueerror(tmp_path):
    result = video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ=_placeholder_env("shopaikey_video"),
        sleep_func=lambda _seconds: None,
    )
    assert result["ok"] is False
    assert result["smoke_stage"] == "config_validation"
    assert result["blocker"] == "provider_config_invalid_submit_url"
    assert result["exception_class"] == ""
    assert result["exception_message_safe"] == ""
    assert result["provider_attempted"] is False
    text = bot.video_provider_smoke_debug_text("shopaikey_video", "text_to_video", result)
    assert "config_validation" in text
    assert "provider_config_invalid_submit_url" in text
    assert "ValueError" not in text
    assert "charge: <code>no</code>" in text


def test_video_provider_setup_reports_invalid_env_names_without_secret_values():
    payload = video_provider_router.provider_status_payload(_placeholder_env("shopaikey_video"))
    text = bot.video_provider_setup_text(payload)
    assert "SHOPAIKEY_VIDEO_SUBMIT_URL" in text
    assert "SHOPAIKEY_VIDEO_POLL_URL" in text
    assert "SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE" in text
    assert "submit_url_th" not in text
    assert "changeme" not in text


def test_public_video_fails_clean_no_charge_when_providers_invalid(tmp_path):
    result = video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ=_placeholder_env("key4u_video"),
        sleep_func=lambda _seconds: None,
    )
    assert result["ok"] is False
    assert result["no_charge"] is True
    assert result["public_message"] == "Hiện hệ thống dựng video AI chưa sẵn sàng. Bot chưa trừ Xu."
    assert result["blocker"] == "provider_config_invalid_submit_url"
    assert not result.get("output_path")
    assert not result.get("local_path")


def test_payos_guard_unchanged_by_video_provider_config_fix():
    source = open("bot.py", "r", encoding="utf-8").read()
    assert "payos_auto_topup_order_filter_sql" in source
