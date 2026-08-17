import asyncio
import os
import json
import pytest
from unittest.mock import patch, AsyncMock
from types import SimpleNamespace

import bot

def test_confirm_webapp_telegram_link_success(monkeypatch):
    monkeypatch.setenv("WEBAPP_BASE_URL", "https://app.toanaas.vn")
    monkeypatch.setenv("WEBAPP_LINK_CALLBACK_TOKEN", "test-token")
    monkeypatch.setenv("WEBAPP_LINK_CALLBACK_HMAC_SECRET", "test-secret")

    class MockResponse:
        status_code = 200
        def json(self):
            return {"ok": True, "data": {"status": "confirmed"}}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MockResponse()
        ok, msg = asyncio.run(bot.confirm_webapp_telegram_link("AB12CD", 123456789))
        assert ok is True
        assert "thành công" in msg.lower()
        assert mock_post.called
        call_kwargs = mock_post.call_args
        headers = call_kwargs[1]["headers"]
        assert headers["X-TOAN-AAS-BRIDGE-TOKEN"] == "test-token"
        assert "X-TOAN-AAS-Signature" in headers

def test_confirm_webapp_telegram_link_missing_config(monkeypatch):
    monkeypatch.delenv("WEBAPP_LINK_CALLBACK_TOKEN", raising=False)
    monkeypatch.delenv("CORE_BRIDGE_CALLBACK_TOKEN", raising=False)
    monkeypatch.delenv("WEBAPP_LINK_CALLBACK_HMAC_SECRET", raising=False)
    monkeypatch.delenv("CORE_BRIDGE_CALLBACK_HMAC_SECRET", raising=False)

    ok, msg = asyncio.run(bot.confirm_webapp_telegram_link("AB12CD", 123456789))
    assert ok is False
    assert "chưa được cấu hình" in msg
