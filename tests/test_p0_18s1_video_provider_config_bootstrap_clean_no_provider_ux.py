import inspect

import bot
from services import video_provider_router
from services import video_real_render_connector as connector


def _provider(payload: dict, name: str) -> dict:
    for item in payload.get("providers") or []:
        if item.get("provider") == name:
            return item
    raise AssertionError(f"provider not found: {name}")


def _no_provider_readiness() -> dict:
    return video_provider_router.provider_status_payload(
        {
            "VIDEO_PROVIDER_CHAIN": "toanaas_video,key4u_video,shopaikey_video,veo,kling,generic_http",
            "APP_ENV": "production",
        }
    )


def _product_job() -> dict:
    return {
        "id": 42,
        "job_id": "42",
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "test_pattern": False,
        "admin_video_delivery": False,
        "product_type": "video_ai_prompt",
        "scene_count": 3,
        "expected_duration_seconds": 18,
        "prompt_text": "cinematic AI video product job",
        "addon_plan": {},
    }


def test_video_provider_setup_command_lists_required_env():
    text = bot.video_provider_setup_text(_no_provider_readiness())
    assert "Cấu hình nhà cung cấp dựng video" in text
    for name in [
        "VIDEO_TOANAAS_ENABLED=true",
        "VIDEO_TOANAAS_SUBMIT_URL",
        "VIDEO_TOANAAS_POLL_URL",
        "SHOPAIKEY_VIDEO_ENABLED=true",
        "SHOPAIKEY_VIDEO_SUBMIT_URL",
        "SHOPAIKEY_VIDEO_POLL_URL",
        "KEY4U_VIDEO_ENABLED=true",
        "KEY4U_VIDEO_SUBMIT_URL",
        "KEY4U_VIDEO_POLL_URL",
        "VIDEO_GENERIC_HTTP_ENABLED=true",
        "VIDEO_GENERIC_HTTP_RESULT_FIELD=result_url",
    ]:
        assert name in text
    source = inspect.getsource(bot)
    assert 'CommandHandler("video_provider_setup", cmd_video_provider_setup)' in source


def test_video_provider_setup_masks_secrets():
    env = {
        "VIDEO_PROVIDER_CHAIN": "generic_http",
        "VIDEO_GENERIC_HTTP_ENABLED": "true",
        "VIDEO_GENERIC_HTTP_SUBMIT_URL": "https://example.invalid/submit",
        "VIDEO_GENERIC_HTTP_POLL_URL": "https://example.invalid/poll/{task_id}",
        "VIDEO_GENERIC_HTTP_AUTH_HEADER_NAME": "Authorization",
        "VIDEO_GENERIC_HTTP_AUTH_HEADER_VALUE": "Bearer real-secret-token",
    }
    payload = video_provider_router.provider_status_payload(env)
    assert "real-secret-token" not in str(payload)
    text = bot.video_provider_setup_text(payload)
    assert "real-secret-token" not in text
    assert "&lt;token&gt;" in text


def test_video_provider_status_summary_when_none_ready():
    payload = _no_provider_readiness()
    text = bot.video_provider_status_text(payload)
    assert payload["ready"] is False
    assert payload["enabled_count"] == 0
    assert "Sẵn sàng" in text
    assert "chưa bật provider nào" in text
    assert "provider_capability_missing" in text


def test_key4u_alias_env_detected():
    payload = video_provider_router.provider_status_payload(
        {
            "VIDEO_PROVIDER_CHAIN": "key4u_video",
            "KEY4U_VIDEO_ENABLED": "true",
            "KEY4U_BASE_URL": "https://key4u.example",
            "KEY4U_VIDEO_ENDPOINT": "/submit",
            "KEY4U_VIDEO_POLL_ENDPOINT": "/poll/{task_id}",
            "KEY4U_API_KEY": "key4u-secret",
        }
    )
    item = _provider(payload, "key4u_video")
    assert item["configured"] is True
    assert item["submit_url_present"] is True
    assert item["poll_url_present"] is True
    assert item["auth_present"] is True
    assert "key4u-secret" not in str(payload)


def test_shopaikey_alias_env_detected():
    payload = video_provider_router.provider_status_payload(
        {
            "VIDEO_PROVIDER_CHAIN": "shopaikey_video",
            "SHOPAIKEY_VIDEO_ENABLED": "true",
            "SHOPAIKEY_BASE_URL": "https://shopaikey.example",
            "SHOPAIKEY_VIDEO_ENDPOINT": "/video/submit",
            "SHOPAIKEY_VIDEO_POLL_ENDPOINT": "/video/poll/{task_id}",
            "SHOPAIKEY_API_KEY": "shop-secret",
        }
    )
    item = _provider(payload, "shopaikey_video")
    assert item["configured"] is True
    assert item["endpoint_present"] is True
    assert item["auth_present"] is True
    assert "shop-secret" not in str(payload)


def test_base_url_without_submit_poll_not_configured():
    payload = video_provider_router.provider_status_payload(
        {
            "VIDEO_PROVIDER_CHAIN": "shopaikey_video,key4u_video",
            "SHOPAIKEY_VIDEO_ENABLED": "true",
            "SHOPAIKEY_BASE_URL": "https://shopaikey.example",
            "SHOPAIKEY_API_KEY": "shop-secret",
            "KEY4U_VIDEO_ENABLED": "true",
            "KEY4U_BASE_URL": "https://key4u.example",
            "KEY4U_API_KEY": "key-secret",
        }
    )
    shop = _provider(payload, "shopaikey_video")
    key4u = _provider(payload, "key4u_video")
    assert shop["configured"] is False
    assert "SHOPAIKEY_VIDEO_SUBMIT_URL" in shop["missing"]
    assert "SHOPAIKEY_VIDEO_POLL_URL" in shop["missing"]
    assert key4u["configured"] is False
    assert "KEY4U_VIDEO_SUBMIT_URL" in key4u["missing"]
    assert "KEY4U_VIDEO_POLL_URL" in key4u["missing"]


def test_no_provider_fails_early_not_85_percent(monkeypatch, tmp_path):
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda job=None, environ=None: _no_provider_readiness())
    try:
        connector.render_real_video_job(_product_job(), str(tmp_path))
    except connector.RealVideoRenderError as exc:
        diagnostics = dict(exc.diagnostics)
    else:
        raise AssertionError("expected RealVideoRenderError")
    assert diagnostics["blocker"] == "provider_capability_missing"
    assert int(diagnostics.get("progress_percent") or 0) <= 45
    assert diagnostics["provider_attempted"] is False


def test_no_provider_sets_provider_capability_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda job=None, environ=None: _no_provider_readiness())
    try:
        connector.render_real_video_job(_product_job(), str(tmp_path))
    except connector.RealVideoRenderError as exc:
        diagnostics = dict(exc.diagnostics)
    assert diagnostics["provider_error"] == "provider_capability_missing"
    assert diagnostics["required_capability"] == "text_to_video"


def test_no_provider_public_copy_clean_no_charge(monkeypatch, tmp_path):
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda job=None, environ=None: _no_provider_readiness())
    try:
        connector.render_real_video_job(_product_job(), str(tmp_path))
    except connector.RealVideoRenderError as exc:
        diagnostics = dict(exc.diagnostics)
    assert diagnostics["no_charge"] is True
    assert diagnostics["public_message"] == video_provider_router.PUBLIC_NO_VIDEO_PROVIDER_COPY
    assert "Xu" in diagnostics["public_message"]
    assert "provider" not in diagnostics["public_message"].lower()


def test_no_provider_debug_shows_missing_env(monkeypatch, tmp_path):
    readiness = _no_provider_readiness()
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda job=None, environ=None: readiness)
    try:
        connector.render_real_video_job(_product_job(), str(tmp_path))
    except connector.RealVideoRenderError as exc:
        diagnostics = dict(exc.diagnostics)
    assert diagnostics["provider_order"]
    assert diagnostics["enabled_providers"] == []
    assert diagnostics["configured_providers"] == []
    assert diagnostics["missing_env"]


def test_ready_provider_count_when_enabled_configured():
    payload = video_provider_router.provider_status_payload(
        {
            "VIDEO_PROVIDER_CHAIN": "generic_http",
            "VIDEO_GENERIC_HTTP_ENABLED": "true",
            "VIDEO_GENERIC_HTTP_SUBMIT_URL": "https://example.invalid/submit",
            "VIDEO_GENERIC_HTTP_POLL_URL": "https://example.invalid/poll/{task_id}",
            "VIDEO_GENERIC_HTTP_AUTH_HEADER_NAME": "Authorization",
            "VIDEO_GENERIC_HTTP_AUTH_HEADER_VALUE": "Bearer token",
        }
    )
    assert payload["ready"] is True
    assert payload["first_ready_provider"] == "generic_http"
    assert payload["enabled_count"] == 1
    assert payload["configured_count"] == 1


def test_generic_http_provider_configured_with_submit_poll_auth():
    item = _provider(
        video_provider_router.provider_status_payload(
            {
                "VIDEO_PROVIDER_CHAIN": "generic_http",
                "VIDEO_GENERIC_HTTP_ENABLED": "1",
                "VIDEO_GENERIC_HTTP_SUBMIT_URL": "https://example.invalid/submit",
                "VIDEO_GENERIC_HTTP_POLL_URL": "https://example.invalid/poll/{task_id}",
                "VIDEO_GENERIC_HTTP_AUTH_HEADER_NAME": "Authorization",
                "VIDEO_GENERIC_HTTP_AUTH_HEADER_VALUE": "Bearer token",
            }
        ),
        "generic_http",
    )
    assert item["configured"] is True
    assert item["submit_url_present"] is True
    assert item["poll_url_present"] is True
    assert item["auth_present"] is True


def test_stub_provider_disabled_in_production():
    payload = video_provider_router.provider_status_payload(
        {
            "VIDEO_PROVIDER_CHAIN": "stub_video",
            "VIDEO_STUB_PROVIDER_ENABLED": "true",
            "APP_ENV": "production",
        }
    )
    item = _provider(payload, "stub_video")
    assert item["enabled"] is True
    assert item["configured"] is False
    assert item["production_disabled"] is True
    assert "non_production_env" in item["missing"]


def test_stub_provider_admin_only():
    payload = video_provider_router.provider_status_payload(
        {
            "VIDEO_PROVIDER_CHAIN": "stub_video",
            "VIDEO_STUB_PROVIDER_ENABLED": "true",
            "APP_ENV": "admin",
        }
    )
    item = _provider(payload, "stub_video")
    assert item["configured"] is True
    assert item["stub_test_only"] is True


def test_video_provider_audit_passes():
    source = inspect.getsource(bot.cmd_video_provider_audit)
    assert "cmd_video_provider_status" in source
    assert "video_provider_status_text" in inspect.getsource(bot)
