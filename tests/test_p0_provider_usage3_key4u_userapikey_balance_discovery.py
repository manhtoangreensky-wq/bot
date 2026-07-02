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


def test_key4u_bearer_403_then_x_api_key_success_no_token_leak():
    provider = Key4UProvider(
        Key4UConfig(
            enabled=True,
            usage_auth_header_value="k4u-user-api-secret",
            usage_auth_mode="authorization_bearer",
            balance_endpoint="/user/wallet/balance",
            usage_discovery_enabled=True,
        )
    )
    calls = []

    async def fake_request_json(method, endpoint_path, payload=None, **kwargs):
        calls.append((endpoint_path, dict(kwargs["headers"])))
        headers = kwargs["headers"]
        if endpoint_path == "/user/wallet/balance" and headers.get("Authorization") == "Bearer k4u-user-api-secret":
            return {"ok": False, "status": "FAIL", "http_status": 403, "error_class": "FAIL_AUTH", "error_message_safe": "forbidden", "data": {"error": "forbidden"}}
        if endpoint_path == "/user/wallet/balance" and headers.get("x-api-key") == "k4u-user-api-secret":
            return {"ok": True, "status": "PASS", "http_status": 200, "data": {"data": {"wallet": {"balance": "12.25"}}}}
        return {"ok": False, "status": "FAIL", "http_status": 403, "error_class": "FAIL_AUTH", "error_message_safe": "forbidden", "data": {"error": "forbidden"}}

    provider.request_json = fake_request_json
    result = asyncio.run(provider.get_balance())
    diagnostic = bot.key4u_credit_diagnostic_from_results({}, result)

    assert result["ok"] is True
    assert diagnostic["balance_usd"] == 12.25
    assert diagnostic["usage_success_auth_mode"] == "x_api_key"
    assert diagnostic["usage_success_endpoint_host_path"] == "api.key4u.shop/user/wallet/balance"
    assert any(headers.get("Authorization") == "Bearer k4u-user-api-secret" for _, headers in calls)
    assert any(headers.get("x-api-key") == "k4u-user-api-secret" for _, headers in calls)
    assert "k4u-user-api-secret" not in str(result)
    assert "k4u-user-api-secret" not in str(diagnostic)


def test_key4u_x_api_key_403_then_another_endpoint_success():
    provider = Key4UProvider(
        Key4UConfig(
            enabled=True,
            usage_auth_header_value="k4u-user-api-secret",
            usage_auth_mode="x_api_key",
            balance_endpoint="/user/wallet/balance",
            usage_discovery_enabled=True,
        )
    )

    async def fake_request_json(method, endpoint_path, payload=None, **kwargs):
        headers = kwargs["headers"]
        if endpoint_path == "/wallet/balance" and headers.get("x-api-key") == "k4u-user-api-secret":
            return {"ok": True, "status": "PASS", "http_status": 200, "data": {"data": {"credit": "9.75"}}}
        return {"ok": False, "status": "FAIL", "http_status": 403, "error_class": "FAIL_AUTH", "error_message_safe": "forbidden", "data": {"error": "forbidden"}}

    provider.request_json = fake_request_json
    result = asyncio.run(provider.get_balance())
    diagnostic = bot.key4u_credit_diagnostic_from_results({}, result)

    assert result["ok"] is True
    assert diagnostic["balance_usd"] == 9.75
    assert diagnostic["usage_success_endpoint_host_path"] == "api.key4u.shop/wallet/balance"
    assert diagnostic["usage_success_auth_mode"] == "x_api_key"
    assert "api.key4u.shop/user/wallet/balance|x_api_key|403" in diagnostic["usage_endpoint_candidates_tried"]
    assert any("api.key4u.shop/wallet/balance" in item for item in diagnostic["usage_endpoint_candidates_tried"])


def test_key4u_all_candidates_fail_safe_unknown_and_render_unblocked(monkeypatch):
    provider = Key4UProvider(
        Key4UConfig(
            enabled=True,
            usage_auth_header_value="k4u-user-api-secret",
            usage_auth_mode="authorization_bearer",
            balance_endpoint="/user/wallet/balance",
            usage_discovery_enabled=True,
        )
    )

    async def fake_request_json(method, endpoint_path, payload=None, **kwargs):
        return {"ok": False, "status": "FAIL", "http_status": 403, "error_class": "FAIL_AUTH", "error_message_safe": "forbidden", "data": {"error": "forbidden"}}

    provider.request_json = fake_request_json
    result = asyncio.run(provider.get_balance())
    monkeypatch.setattr(bot, "KEY4U_BALANCE_ENDPOINT", "https://api.key4u.shop/user/wallet/balance")
    monkeypatch.setattr(bot, "KEY4U_USAGE_URL", "")
    monkeypatch.setattr(bot, "KEY4U_USAGE_CHECK_URL", "")
    monkeypatch.setattr(bot, "KEY4U_USAGE_ENDPOINT", "")
    monkeypatch.setattr(bot, "KEY4U_USAGE_AUTH_HEADER_VALUE", "k4u-user-api-secret")

    diagnostic = bot.key4u_credit_diagnostic_from_results({}, result)
    adapter, status = video_provider_router.select_video_provider("text_to_video", _key4u_video_env())

    assert result["error_class"] == "KEY4U_USERAPIKEY_ENDPOINT_NOT_FOUND_OR_FORBIDDEN"
    assert diagnostic["credit"] == "unknown"
    assert diagnostic["reason"] == "KEY4U_USERAPIKEY_ENDPOINT_NOT_FOUND_OR_FORBIDDEN"
    assert diagnostic["usage_last_http_status"] == 403
    assert len(diagnostic["usage_endpoint_candidates_tried"]) >= 10
    assert "k4u-user-api-secret" not in str(diagnostic)
    assert adapter is not None
    assert adapter.provider_name == "key4u_video"
    assert status["selection_reason"] == "provider_ready_and_has_credit"


def test_key4u_balance_parses_common_response_shapes():
    cases = [
        ({"balance": 1}, 1.0),
        ({"data": {"balance": 2}}, 2.0),
        ({"data": {"credit": "3.5"}}, 3.5),
        ({"data": {"amount": "4"}}, 4.0),
        ({"data": {"wallet": {"balance": "5"}}}, 5.0),
        ({"data": {"usd": "6"}}, 6.0),
        ({"credit": 7}, 7.0),
        ({"remaining": "8"}, 8.0),
        ({"amount": "9"}, 9.0),
    ]
    for payload, expected in cases:
        assert bot.key4u_extract_balance_usd({"ok": True, "data": payload}) == expected


def test_key4u_authorization_raw_mode_sends_raw_key():
    provider = Key4UProvider(
        Key4UConfig(
            enabled=True,
            usage_auth_header_value="k4u-user-api-secret",
            usage_auth_mode="authorization_raw",
            balance_endpoint="/user/wallet/balance",
        )
    )

    async def fake_request_json(method, endpoint_path, payload=None, **kwargs):
        assert kwargs["headers"]["Authorization"] == "k4u-user-api-secret"
        return {"ok": True, "status": "PASS", "http_status": 200, "data": {"balance": 1}}

    provider.request_json = fake_request_json
    result = asyncio.run(provider.get_balance())

    assert result["ok"] is True
    assert result["raw_debug_admin_only"]["usage_auth_mode"] == "authorization_raw"
    assert result["raw_debug_admin_only"]["usage_auth_scheme_prefix"] == "raw"
    assert "k4u-user-api-secret" not in str(result)
