import asyncio
import os
import json
from pathlib import Path
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
        ok, msg = asyncio.run(bot.confirm_webapp_telegram_link("  aB12CdEfGh  ", 123456789))
        assert ok is True
        assert "thành công" in msg.lower()
        assert mock_post.called
        call_kwargs = mock_post.call_args
        body = json.loads(call_kwargs[1]["content"].decode("utf-8"))
        assert body["code"] == "aB12CdEfGh"
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


def test_webapp_deep_link_prefix_is_consumed_by_cmd_start(monkeypatch):
    captured = []

    class StopAfterConfirmation(Exception):
        pass

    async def confirm(code, uid, role="user"):
        captured.append((code, uid, role))
        return True, "Xác thực thành công!"

    async def stop_after_reply(*_args, **_kwargs):
        raise StopAfterConfirmation

    monkeypatch.setattr(bot, "log_command_received", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bot, "user_exists", lambda _uid: False)
    monkeypatch.setattr(bot, "get_user", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bot, "record_usage_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bot, "confirm_webapp_telegram_link", confirm)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123456789, first_name="Test", username="test"),
        message=SimpleNamespace(reply_text=AsyncMock(side_effect=stop_after_reply)),
    )
    context = SimpleNamespace(args=["web_AB12CD"])

    with pytest.raises(StopAfterConfirmation):
        asyncio.run(bot.cmd_start(update, context))

    assert captured == [("AB12CD", 123456789, "user")]


def test_linkweb_command_is_registered():
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")

    assert source.count('tg_app.add_handler(CommandHandler("linkweb", cmd_linkweb))') == 1
