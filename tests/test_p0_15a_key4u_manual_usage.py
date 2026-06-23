import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

import bot


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


def _fake_update(user_id=1):
    message = FakeMessage()
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        message=message,
    )


def _patch_settings(monkeypatch):
    store = {}

    def get_setting(key, default=""):
        return store.get(key, default)

    def set_setting(key, value, note="", updated_by=""):
        store[str(key)] = str(value or "")

    monkeypatch.setattr(bot, "get_system_setting", get_setting)
    monkeypatch.setattr(bot, "set_system_setting", set_setting)
    return store


def _patch_usage(monkeypatch, estimated_cost_usd=0.0):
    monkeypatch.setattr(
        bot,
        "provider_usage_summary",
        lambda *_args, **_kwargs: {
            "total_calls": 0,
            "success_count": 0,
            "fail_count": 0,
            "estimated_cost_usd": estimated_cost_usd,
            "last_event_at": "",
            "by_capability": {},
        },
    )


def _source():
    return Path(bot.__file__).read_text(encoding="utf-8")


def test_key4u_usage_set_manual_command_supported():
    source = _source()
    assert 'CommandHandler("key4u_usage_set_manual", cmd_key4u_usage_set_manual)' in source
    assert '"key4u_usage_set_manual"' in source


def test_key4u_usage_manual_alias_supported():
    source = _source()
    assert 'CommandHandler("key4u_usage_manual", cmd_key4u_usage_set_manual)' in source
    assert '"key4u_usage_manual"' in source


def test_key4u_usage_status_shows_manual_balance(monkeypatch):
    _patch_settings(monkeypatch)
    _patch_usage(monkeypatch, estimated_cost_usd=1.101)
    monkeypatch.setattr(bot, "KEY4U_USAGE_ENDPOINT", "")
    bot.set_key4u_manual_balance_usd(bot.key4u_parse_usage_amount("14.101"), "1")

    text = "\n".join(bot.key4u_usage_status_lines())

    assert "Dashboard balance thủ công" in text
    assert "14.101 USD" in text
    assert "manual_admin" in text
    assert "13.0000 USD" in text
    assert "Groups/routes" in text


def test_key4u_usage_clear_manual(monkeypatch):
    store = _patch_settings(monkeypatch)
    bot.set_key4u_manual_balance_usd(bot.key4u_parse_usage_amount("14.101"), "1")

    bot.clear_key4u_manual_balance_usd("1")

    assert store["key4u_manual_balance_usd"] == ""
    assert store["key4u_manual_balance_source"] == ""
    assert bot.key4u_manual_balance_usd() is None


def test_key4u_usage_refresh_unknown_endpoint_clear_message(monkeypatch):
    _patch_settings(monkeypatch)
    _patch_usage(monkeypatch)
    monkeypatch.setattr(bot, "KEY4U_USAGE_ENDPOINT", "")
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)

    def fail_provider_call():
        raise AssertionError("provider should not be called without a verified usage endpoint")

    monkeypatch.setattr(bot, "key4u_provider_instance", fail_provider_call)
    update = _fake_update()

    asyncio.run(bot.cmd_key4u_usage_refresh(update, SimpleNamespace(args=[])))

    assert update.message.replies
    assert update.message.replies[-1][0] == (
        "Key4U chưa có endpoint usage đã xác minh. "
        "Dùng /key4u_usage_set_manual <amount> để cập nhật số dư theo dashboard."
    )


def test_key4u_usage_no_secret_leak(monkeypatch):
    _patch_settings(monkeypatch)
    _patch_usage(monkeypatch)
    bot.set_key4u_manual_balance_usd(bot.key4u_parse_usage_amount("14.101"), "1")

    text = "\n".join(bot.key4u_usage_status_lines()).lower()

    for forbidden in ("api_key", "token", "secret", "authorization", "bearer"):
        assert forbidden not in text


def test_key4u_usage_admin_only(monkeypatch):
    _patch_settings(monkeypatch)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    update = _fake_update(user_id=2)

    asyncio.run(bot.cmd_key4u_usage_set_manual(update, SimpleNamespace(args=["14.101"])))

    assert update.message.replies[-1][0] == "⛔ Bạn không có quyền dùng lệnh này."
    assert bot.key4u_manual_balance_usd() is None


def test_provider_usage_screen_shows_key4u_manual_balance(monkeypatch):
    _patch_settings(monkeypatch)
    _patch_usage(monkeypatch, estimated_cost_usd=0.101)
    monkeypatch.setattr(bot, "KEY4U_USAGE_ENDPOINT", "")
    monkeypatch.setattr(bot, "shopaikey_last_usage_snapshot", lambda: {})
    bot.set_key4u_manual_balance_usd(bot.key4u_parse_usage_amount("14.101"), "1")

    text = bot.admin_provider_usage_text_v2()

    assert "<b>ShopAIKey</b>" in text
    assert "<b>Key4U</b>" in text
    assert "Dashboard balance thủ công" in text
    assert "14.101 USD" in text
    assert "14.0000 USD" in text
    assert "/key4u_usage_set_manual 14.101" in text
