import asyncio

import bot
from providers.key4u_provider import Key4UConfig, Key4UProvider
from services import video_provider_router


def _key4u_video_env() -> dict[str, str]:
    return {
        "VIDEO_PROVIDER_CHAIN": "key4u_video",
        "KEY4U_VIDEO_ENABLED": "true",
        "KEY4U_VIDEO_SUBMIT_URL": "https://api.key4u.shop/video/submit",
        "KEY4U_VIDEO_POLL_URL": "https://api.key4u.shop/video/poll",
        "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer key4u-video-secret",
        "KEY4U_VIDEO_MODEL": "veo3.1-fast",
        "KEY4U_VIDEO_CAPABILITIES": "text_to_video,image_to_video,scene_video",
    }


def test_key4u_system_api_key_selected_before_api_key_for_usage():
    provider = Key4UProvider(
        Key4UConfig(
            enabled=True,
            api_key="sk-normal-provider-secret",
            system_api_key="k4u-system-usage-secret",
            usage_endpoint="https://api.key4u.shop/user/usage",
        )
    )

    async def fake_request_json(method, endpoint_path, payload=None, **kwargs):
        assert method == "GET"
        assert endpoint_path == "https://api.key4u.shop/user/usage"
        assert kwargs["headers"]["Authorization"] == "Bearer k4u-system-usage-secret"
        return {"ok": True, "status": "PASS", "data": {"balance": 14.101}}

    provider.request_json = fake_request_json
    usage = asyncio.run(provider.get_usage())
    debug = usage["raw_debug_admin_only"]

    assert usage["ok"] is True
    assert debug["usage_auth_source"] == "system_api_key"
    assert debug["usage_auth_header_name"] == "Authorization"
    assert debug["usage_auth_scheme_prefix"] == "Bearer"
    assert "k4u-system-usage-secret" not in str(usage)
    assert "sk-normal-provider-secret" not in str(usage)


def test_key4u_usage_auth_header_value_selected_before_system_key():
    provider = Key4UProvider(
        Key4UConfig(
            enabled=True,
            api_key="sk-normal-provider-secret",
            system_api_key="k4u-system-usage-secret",
            usage_auth_header_value="Bearer usage-header-secret",
            usage_endpoint="https://api.key4u.shop/user/usage",
        )
    )

    async def fake_request_json(method, endpoint_path, payload=None, **kwargs):
        assert kwargs["headers"]["Authorization"] == "Bearer usage-header-secret"
        return {"ok": True, "status": "PASS", "data": {"data": {"credit": "8.5"}}}

    provider.request_json = fake_request_json
    usage = asyncio.run(provider.get_usage())

    assert usage["raw_debug_admin_only"]["usage_auth_source"] == "usage_auth_header_value"
    assert "usage-header-secret" not in str(usage)
    assert "k4u-system-usage-secret" not in str(usage)


def test_key4u_raw_k4u_usage_key_sent_as_bearer():
    provider = Key4UProvider(
        Key4UConfig(
            enabled=True,
            system_api_key="k4u-raw-system-key",
            usage_endpoint="https://api.key4u.shop/user/usage",
        )
    )

    async def fake_request_json(method, endpoint_path, payload=None, **kwargs):
        assert kwargs["headers"]["Authorization"] == "Bearer k4u-raw-system-key"
        return {"ok": True, "status": "PASS", "data": {"remaining": 2}}

    provider.request_json = fake_request_json
    usage = asyncio.run(provider.get_usage())

    assert usage["raw_debug_admin_only"]["usage_auth_scheme_prefix"] == "Bearer"


def test_key4u_balance_parses_common_response_shapes():
    cases = [
        ({"balance": 1}, 1.0),
        ({"data": {"balance": 2}}, 2.0),
        ({"data": {"credit": "3.5"}}, 3.5),
        ({"data": {"amount": "4"}}, 4.0),
        ({"data": {"wallet": {"balance": "5"}}}, 5.0),
        ({"data": {"usd": "6"}}, 6.0),
        ({"remaining": 7}, 7.0),
        ({"credit": 8}, 8.0),
    ]
    for payload, expected in cases:
        assert bot.key4u_extract_balance_usd({"ok": True, "data": payload}) == expected


def test_key4u_fail_auth_debug_safe_no_key_leak(monkeypatch):
    monkeypatch.setattr(bot, "KEY4U_USAGE_ENDPOINT", "https://api.key4u.shop/user/usage")
    monkeypatch.setattr(bot, "KEY4U_USAGE_URL", "https://api.key4u.shop/user/usage")
    monkeypatch.setattr(bot, "KEY4U_USAGE_CHECK_URL", "")
    monkeypatch.setattr(bot, "KEY4U_BALANCE_ENDPOINT", "")
    monkeypatch.setattr(bot, "KEY4U_USAGE_AUTH_HEADER_VALUE", "")
    monkeypatch.setattr(bot, "KEY4U_SYSTEM_API_KEY", "k4u-system-usage-secret")
    monkeypatch.setattr(bot, "KEY4U_API_KEY", "sk-normal-provider-secret")
    monkeypatch.setattr(bot, "KEY4U_VIDEO_AUTH_HEADER_VALUE", "Bearer video-secret")

    remote_usage = {
        "ok": False,
        "status": "FAIL",
        "http_status": 403,
        "error_class": "FAIL_AUTH",
        "data": {"error": "forbidden"},
        "raw_debug_admin_only": {
            "usage_auth_source": "system_api_key",
            "usage_auth_header_name": "Authorization",
            "usage_auth_scheme_prefix": "Bearer",
            "usage_endpoint_host": "api.key4u.shop",
            "usage_endpoint_path": "/user/usage",
            "usage_http_status": 403,
            "usage_response_shape": "error",
            "usage_reason": "FAIL_AUTH",
        },
    }

    diagnostic = bot.key4u_credit_diagnostic_from_results(remote_usage, {})
    status_text = bot.video_provider_status_text(
        video_provider_router.provider_status_payload(_key4u_video_env()),
        diagnostic,
    )

    assert diagnostic["credit"] == "unknown"
    assert diagnostic["reason"] == "FAIL_AUTH"
    assert diagnostic["usage_auth_source"] == "system_api_key"
    assert diagnostic["usage_http_status"] == 403
    assert diagnostic["usage_endpoint_host"] == "api.key4u.shop"
    assert diagnostic["usage_endpoint_path"] == "/user/usage"
    assert diagnostic["usage_response_shape"] == "error"
    assert "k4u-system-usage-secret" not in str(diagnostic)
    assert "sk-normal-provider-secret" not in status_text
    assert "video-secret" not in status_text


def test_key4u_missing_usage_endpoint_unknown_does_not_block_video_render(monkeypatch):
    monkeypatch.setattr(bot, "KEY4U_USAGE_ENDPOINT", "")
    monkeypatch.setattr(bot, "KEY4U_USAGE_URL", "")
    monkeypatch.setattr(bot, "KEY4U_USAGE_CHECK_URL", "")
    monkeypatch.setattr(bot, "KEY4U_BALANCE_ENDPOINT", "")

    diagnostic = bot.key4u_credit_diagnostic_from_results()
    adapter, status = video_provider_router.select_video_provider("text_to_video", _key4u_video_env())

    assert diagnostic["credit"] == "unknown"
    assert diagnostic["reason"] == "key4u_usage_url_missing"
    assert adapter is not None
    assert adapter.provider_name == "key4u_video"
    assert status["selection_reason"] == "provider_ready_and_has_credit"
