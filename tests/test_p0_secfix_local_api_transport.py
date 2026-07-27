"""Focused, import-light regression tests for Telegram Local API transport.

These tests intentionally avoid importing the 12 MB ``bot.py`` monolith.  The
shared policy and raw request boundary are exercised directly, while a small
source contract proves that ``bot.py`` delegates configuration and media fetch
validation to the same helper.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import telegram_business_support, telegram_transport


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_remote_http_is_rejected_but_loopback_http_is_explicitly_allowed():
    with pytest.raises(ValueError, match="HTTPS"):
        telegram_transport.normalize_api_root("http://tg.example.com")

    for value in (
        "http://127.0.0.1:8081",
        "http://[::1]:8081",
        "http://localhost:8081",
    ):
        assert telegram_transport.normalize_api_root(value) == value


@pytest.mark.parametrize(
    "value",
    (
        "http://localhost.example.com",
        "ftp://tg.example.com",
        "https://user:pass@tg.example.com",
        "https://tg.example.com?token=leak",
        "https://tg.example.com#fragment",
    ),
)
def test_ambiguous_or_credential_bearing_base_components_are_rejected(value):
    with pytest.raises(ValueError):
        telegram_transport.normalize_api_root(value)


def test_raw_business_request_rejects_http_before_custom_transport_runs():
    class UnsafeBot:
        base_url = "http://tg.example.com/botDUMMY"
        token = "DUMMY"
        called = False

        async def raw_bot_api_request(self, method, payload):
            self.called = True
            return {"ok": True}

    bot = UnsafeBot()
    with pytest.raises(ValueError, match="HTTPS"):
        asyncio.run(telegram_business_support.raw_bot_api_request(bot, "sendMessage", {"text": "probe"}))
    assert bot.called is False


def test_https_business_request_keeps_the_existing_endpoint_shape():
    bot = SimpleNamespace(base_url="https://tg.example.com/botDUMMY", token="DUMMY")
    assert telegram_business_support.raw_bot_api_endpoint(bot, "getMe") == (
        "https://tg.example.com/botDUMMY/getMe"
    )


def test_bot_configuration_and_media_fetch_use_the_shared_policy():
    source = (REPO_ROOT / "bot.py").read_text(encoding="utf-8", errors="strict")
    assert "from services import ai_chatbot_copilot, telegram_business_support, telegram_transport" in source
    assert "return telegram_transport.normalize_api_root(value)" in source
    media_guard = source.index("telegram_transport.validate_api_url(url)")
    media_client = source.index("httpx.AsyncClient", media_guard)
    assert media_guard < media_client
