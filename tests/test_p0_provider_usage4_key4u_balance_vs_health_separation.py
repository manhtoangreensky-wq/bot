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


def _provider(balance_endpoint: str = "/user/wallet/balance") -> Key4UProvider:
    return Key4UProvider(
        Key4UConfig(
            enabled=True,
            usage_auth_header_value="k4u-user-api-secret",
            usage_auth_mode="authorization_bearer",
            balance_endpoint=balance_endpoint,
            usage_discovery_enabled=True,
        )
    )


def test_key4u_health_200_is_connectivity_not_balance():
    provider = _provider()

    async def fake_request_json(method, endpoint_path, payload=None, **kwargs):
        if endpoint_path == "/health":
            return {"ok": True, "status": "PASS", "http_status": 200, "data": {"service": "key4u", "status": "ok"}}
        return {"ok": False, "status": "FAIL", "http_status": 403, "error_class": "FAIL_AUTH", "error_message_safe": "forbidden", "data": {"error": "forbidden"}}

    provider.request_json = fake_request_json
    result = asyncio.run(provider.get_balance())
    diagnostic = bot.key4u_credit_diagnostic_from_results({}, result)

    assert result["ok"] is False
    assert result["status"] == "UNKNOWN"
    assert diagnostic["credit"] == "unknown"
    assert diagnostic["usage_connectivity_status"] == "PASS"
    assert diagnostic["usage_balance_status"] == "UNKNOWN"
    assert diagnostic["usage_success_endpoint_type"] == "health"
    assert diagnostic["usage_health_http"] == 200
    assert diagnostic["reason"] == "KEY4U_HEALTH_OK_BALANCE_ENDPOINT_NOT_FOUND"


def test_key4u_health_200_then_balance_endpoint_success_parses_credit():
    provider = _provider(balance_endpoint="/health")

    async def fake_request_json(method, endpoint_path, payload=None, **kwargs):
        if endpoint_path == "/health":
            return {"ok": True, "status": "PASS", "http_status": 200, "data": {"service": "key4u", "status": "ok"}}
        if endpoint_path == "/user/wallet/balance":
            return {"ok": True, "status": "PASS", "http_status": 200, "data": {"data": {"wallet": {"balance": "14.101"}}}}
        return {"ok": False, "status": "FAIL", "http_status": 404, "error_class": "NOT_FOUND", "error_message_safe": "not_found", "data": {"error": "not_found"}}

    provider.request_json = fake_request_json
    result = asyncio.run(provider.get_balance())
    diagnostic = bot.key4u_credit_diagnostic_from_results({}, result)

    assert result["ok"] is True
    assert diagnostic["balance_usd"] == 14.101
    assert diagnostic["usage_connectivity_status"] == "PASS"
    assert diagnostic["usage_balance_status"] == "PASS"
    assert diagnostic["usage_success_endpoint_type"] == "balance"
    assert diagnostic["usage_health_http"] == 200
    assert diagnostic["usage_balance_parse_endpoint_host_path"] == "api.key4u.shop/user/wallet/balance"
    assert diagnostic["usage_balance_parse_fields"] == "data.wallet.balance"


def test_key4u_balance_forbidden_but_health_ok_reports_health_not_balance():
    provider = _provider()

    async def fake_request_json(method, endpoint_path, payload=None, **kwargs):
        if endpoint_path == "/health":
            return {"ok": True, "status": "PASS", "http_status": 200, "data": {"service": "key4u", "status": "ok"}}
        if "balance" in endpoint_path or "wallet" in endpoint_path:
            return {"ok": False, "status": "FAIL", "http_status": 403, "error_class": "FAIL_AUTH", "error_message_safe": "forbidden", "data": {"error": "forbidden"}}
        return {"ok": False, "status": "FAIL", "http_status": 404, "error_class": "NOT_FOUND", "error_message_safe": "not_found", "data": {"error": "not_found"}}

    provider.request_json = fake_request_json
    result = asyncio.run(provider.get_balance())
    diagnostic = bot.key4u_credit_diagnostic_from_results({}, result)
    status_text = bot.video_provider_status_text(
        {"providers": [{"provider": "key4u_video", "enabled": True, "configured": True, "endpoint_present": True, "submit_url_present": True, "poll_url_present": True, "auth_present": True, "model_present": True}]},
        diagnostic,
    )

    assert diagnostic["reason"] == "KEY4U_HEALTH_OK_BALANCE_ENDPOINT_NOT_FOUND"
    assert diagnostic["usage_balance_http"] in {403, 404}
    assert "usage_reason=<code>KEY4U_HEALTH_OK_BALANCE_ENDPOINT_NOT_FOUND</code>" in status_text
    assert "usage_health_http=<code>200</code>" in status_text
    assert "usage_success_type=<code>health</code>" in status_text


def test_key4u_usage_log_success_without_balance_keeps_balance_unknown():
    provider = _provider(balance_endpoint="/logs/usage")

    async def fake_request_json(method, endpoint_path, payload=None, **kwargs):
        if endpoint_path == "/logs/usage":
            return {"ok": True, "status": "PASS", "http_status": 200, "data": {"items": [], "total": 0}}
        return {"ok": False, "status": "FAIL", "http_status": 404, "error_class": "NOT_FOUND", "error_message_safe": "not_found", "data": {"error": "not_found"}}

    provider.request_json = fake_request_json
    result = asyncio.run(provider.get_balance())
    diagnostic = bot.key4u_credit_diagnostic_from_results({}, result)

    assert result["ok"] is False
    assert diagnostic["usage_log_status"] == "PASS"
    assert diagnostic["usage_balance_status"] == "UNKNOWN"
    assert diagnostic["credit"] == "unknown"


def test_key4u_usage4_no_token_leak_and_provider_readiness_unaffected():
    provider = _provider()

    async def fake_request_json(method, endpoint_path, payload=None, **kwargs):
        if endpoint_path == "/health":
            return {"ok": True, "status": "PASS", "http_status": 200, "data": {"service": "key4u", "status": "ok"}}
        return {"ok": False, "status": "FAIL", "http_status": 403, "error_class": "FAIL_AUTH", "error_message_safe": "forbidden", "data": {"error": "forbidden"}}

    provider.request_json = fake_request_json
    result = asyncio.run(provider.get_balance())
    diagnostic = bot.key4u_credit_diagnostic_from_results({}, result)
    adapter, status = video_provider_router.select_video_provider("text_to_video", _key4u_video_env())

    assert "k4u-user-api-secret" not in str(result)
    assert "k4u-user-api-secret" not in str(diagnostic)
    assert adapter is not None
    assert adapter.provider_name == "key4u_video"
    assert status["selection_reason"] == "provider_ready_and_has_credit"
