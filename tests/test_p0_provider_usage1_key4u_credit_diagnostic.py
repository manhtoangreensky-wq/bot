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
        "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer key4u-secret-token",
        "KEY4U_VIDEO_MODEL": "veo3.1-fast",
        "KEY4U_VIDEO_CAPABILITIES": "text_to_video,image_to_video,scene_video",
    }


def test_key4u_provider_ready_without_usage_url():
    status = video_provider_router.provider_status_payload(_key4u_video_env())
    key4u = next(item for item in status["providers"] if item["provider"] == "key4u_video")

    assert key4u["enabled"] is True
    assert key4u["configured"] is True
    assert key4u["credit_ok"] is True
    assert "KEY4U_USAGE_URL" not in key4u["missing"]
    assert "KEY4U_USAGE_CHECK_URL" not in key4u["missing"]


def test_key4u_usage_shows_unknown_when_missing(monkeypatch):
    monkeypatch.setattr(bot, "KEY4U_USAGE_ENDPOINT", "")
    monkeypatch.setattr(bot, "KEY4U_USAGE_URL", "")
    monkeypatch.setattr(bot, "KEY4U_USAGE_CHECK_URL", "")
    monkeypatch.setattr(bot, "KEY4U_BALANCE_ENDPOINT", "")

    diagnostic = bot.key4u_credit_diagnostic_from_results()

    assert diagnostic["credit"] == "unknown"
    assert diagnostic["endpoint_configured"] is False
    assert diagnostic["reason"] == "key4u_usage_url_missing"


def test_key4u_usage_parses_balance_when_configured():
    result = {
        "ok": True,
        "status": "PASS",
        "data": {"data": {"credit": "14.101"}},
    }

    diagnostic = bot.key4u_credit_diagnostic_from_results(result, {})

    assert diagnostic["balance_usd"] == 14.101
    assert diagnostic["credit"] == "14.101 USD"
    assert diagnostic["reason"] == "key4u_usage_balance_ok"


def test_key4u_usage_provider_uses_video_auth_header_without_token_leak():
    provider = Key4UProvider(
        Key4UConfig(
            enabled=True,
            api_key="",
            video_auth_header_value="Bearer key4u-secret-token",
            usage_endpoint="https://key4u.example/usage",
        )
    )

    async def fake_request_json(method, endpoint_path, payload=None, **kwargs):
        assert method == "GET"
        assert endpoint_path == "https://key4u.example/usage"
        assert provider._headers()["Authorization"] == "Bearer key4u-secret-token"
        return {"ok": True, "status": "PASS", "data": {"balance": 8.5}}

    provider.request_json = fake_request_json
    usage = asyncio.run(provider.get_usage())
    diagnostic = bot.key4u_credit_diagnostic_from_results(usage, {})
    status_text = bot.video_provider_status_text(
        video_provider_router.provider_status_payload(_key4u_video_env()),
        {"credit": diagnostic["credit"], "reason": diagnostic["reason"]},
    )

    assert diagnostic["credit"] == "8.5 USD"
    assert "key4u-secret-token" not in status_text
    assert "Bearer " not in status_text


def test_video_provider_selection_unaffected_by_usage_missing():
    env = _key4u_video_env()
    env.pop("KEY4U_USAGE_URL", None)
    env.pop("KEY4U_USAGE_CHECK_URL", None)

    adapter, status = video_provider_router.select_video_provider("text_to_video", env)

    assert adapter is not None
    assert adapter.provider_name == "key4u_video"
    assert status["selected_provider"] == "key4u_video"
    assert status["selection_reason"] == "provider_ready_and_has_credit"
