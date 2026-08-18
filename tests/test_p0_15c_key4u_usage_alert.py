import asyncio
from pathlib import Path
from types import SimpleNamespace

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


def _patch_usage(monkeypatch, estimated_cost_usd=0.0, unknown_cost_count=0):
    monkeypatch.setattr(
        bot,
        "provider_usage_summary",
        lambda *_args, **_kwargs: {
            "total_calls": 1 if estimated_cost_usd or unknown_cost_count else 0,
            "success_count": 1 if estimated_cost_usd else 0,
            "fail_count": 0,
            "estimated_cost_usd": estimated_cost_usd,
            "estimated_cost_xu": 0,
            "unknown_cost_count": unknown_cost_count,
            "last_event_at": "",
            "by_capability": {},
        },
    )


def _patch_freeze(monkeypatch, frozen=False):
    monkeypatch.setattr(bot, "provider_freeze_display", lambda _provider="key4u": {"frozen": frozen, "reason": "-"})


def _set_manual(monkeypatch, amount, estimated_cost_usd=0.0, unknown_cost_count=0):
    _patch_settings(monkeypatch)
    _patch_usage(monkeypatch, estimated_cost_usd=estimated_cost_usd, unknown_cost_count=unknown_cost_count)
    _patch_freeze(monkeypatch)
    monkeypatch.setattr(bot, "KEY4U_USAGE_ENDPOINT", "")
    if amount is not None:
        bot.set_key4u_manual_balance_usd(bot.key4u_parse_usage_amount(str(amount)), "1")


def _source():
    return Path(bot.__file__).read_text(encoding="utf-8")


def _button_labels(markup):
    return [button.text for row in getattr(markup, "inline_keyboard", []) for button in row]


def test_key4u_alert_ok(monkeypatch):
    _set_manual(monkeypatch, "10", estimated_cost_usd=1)

    snapshot = bot.key4u_usage_alert_snapshot()

    assert snapshot["alert_level"] == "OK"
    assert snapshot["estimated_remaining"] == "9.0000 USD"


def test_key4u_alert_warn(monkeypatch):
    _set_manual(monkeypatch, "5", estimated_cost_usd=0)

    assert bot.key4u_usage_alert_snapshot()["alert_level"] == "WARN"


def test_key4u_alert_critical(monkeypatch):
    _set_manual(monkeypatch, "2", estimated_cost_usd=0)

    assert bot.key4u_usage_alert_snapshot()["alert_level"] == "CRITICAL"


def test_key4u_alert_freeze_threshold(monkeypatch):
    _set_manual(monkeypatch, "1", estimated_cost_usd=0)

    assert bot.key4u_usage_alert_snapshot()["alert_level"] == "FREEZE_RECOMMENDED"


def test_key4u_alert_unknown_balance(monkeypatch):
    _set_manual(monkeypatch, None, estimated_cost_usd=0)

    snapshot = bot.key4u_usage_alert_snapshot()

    assert snapshot["alert_level"] == "UNKNOWN_BALANCE"
    assert snapshot["estimated_remaining"] == "unknown"


def test_key4u_alert_uses_manual_minus_local_estimate(monkeypatch):
    _set_manual(monkeypatch, "14.101", estimated_cost_usd=1.101)

    snapshot = bot.key4u_usage_alert_snapshot()

    assert snapshot["remaining_source"] == "manual_admin_minus_local_estimate"
    assert snapshot["estimated_remaining"] == "13.0000 USD"


def test_key4u_usage_alert_command(monkeypatch):
    _set_manual(monkeypatch, "14.101", estimated_cost_usd=0.101)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    update = _fake_update()

    asyncio.run(bot.cmd_key4u_usage_alert(update, SimpleNamespace(args=[])))

    assert update.message.replies
    text = update.message.replies[-1][0]
    assert "Key4U Usage Alert" in text
    assert "Alert level" in text
    assert "14.0000 USD" in text


def test_key4u_usage_alert_set_command(monkeypatch):
    store = _patch_settings(monkeypatch)
    _patch_usage(monkeypatch)
    _patch_freeze(monkeypatch)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    update = _fake_update()

    asyncio.run(bot.cmd_key4u_usage_alert_set(update, SimpleNamespace(args=["6", "3", "1"])))

    assert store["key4u_usage_alert_warn_usd"] == "6"
    assert store["key4u_usage_alert_critical_usd"] == "3"
    assert store["key4u_usage_alert_freeze_usd"] == "1"
    assert "warn <= 6 USD" in update.message.replies[-1][0]


def test_key4u_usage_alert_on_off(monkeypatch):
    store = _patch_settings(monkeypatch)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    update = _fake_update()

    asyncio.run(bot.cmd_key4u_usage_alert_off(update, SimpleNamespace(args=[])))
    assert store["key4u_usage_alert_enabled"] == "0"
    asyncio.run(bot.cmd_key4u_usage_alert_on(update, SimpleNamespace(args=[])))
    assert store["key4u_usage_alert_enabled"] == "1"


def test_key4u_freeze_if_low(monkeypatch):
    _set_manual(monkeypatch, "1", estimated_cost_usd=0)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    calls = []
    monkeypatch.setattr(bot, "set_provider_freeze_state", lambda *args, **kwargs: calls.append((args, kwargs)))
    update = _fake_update()

    asyncio.run(bot.cmd_key4u_usage_freeze_if_low(update, SimpleNamespace(args=[])))

    assert calls
    assert calls[-1][0][0] == "key4u"
    assert calls[-1][0][1] is True
    assert "Đã freeze Key4U" in update.message.replies[-1][0]


def test_key4u_unfreeze_after_manual_balance(monkeypatch):
    _set_manual(monkeypatch, "10", estimated_cost_usd=0)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    calls = []
    monkeypatch.setattr(bot, "set_provider_freeze_state", lambda *args, **kwargs: calls.append((args, kwargs)))
    update = _fake_update()

    asyncio.run(bot.cmd_key4u_usage_unfreeze(update, SimpleNamespace(args=[])))

    assert calls
    assert calls[-1][0][0] == "key4u"
    assert calls[-1][0][1] is False
    assert "Đã unfreeze Key4U" in update.message.replies[-1][0]


def test_key4u_alert_no_secret_leak(monkeypatch):
    _set_manual(monkeypatch, "14.101", estimated_cost_usd=0.101)

    text = "\n".join(bot.key4u_usage_alert_lines()).lower()

    for forbidden in ("api_key", "token", "secret", "authorization", "bearer"):
        assert forbidden not in text


def test_provider_usage_key4u_alert_visible(monkeypatch):
    _set_manual(monkeypatch, "14.101", estimated_cost_usd=0.101)
    monkeypatch.setattr(bot, "shopaikey_last_usage_snapshot", lambda: {})

    text = bot.admin_provider_usage_text_v2()

    assert "<b>Key4U</b>" in text
    assert "Alert level" in text
    assert "14.0000 USD" in text


def test_provider_usage_key4u_thresholds_visible(monkeypatch):
    _set_manual(monkeypatch, "14.101", estimated_cost_usd=0)
    monkeypatch.setattr(bot, "shopaikey_last_usage_snapshot", lambda: {})

    text = bot.admin_provider_usage_text_v2()

    assert "Thresholds" in text
    assert "warn &lt;= 5 USD" in text
    assert "/key4u_usage_alert_set &lt;warn_usd&gt; &lt;critical_usd&gt; &lt;freeze_usd&gt;" in text


def test_provider_usage_key4u_no_secret(monkeypatch):
    _set_manual(monkeypatch, "14.101", estimated_cost_usd=0)
    monkeypatch.setattr(bot, "shopaikey_last_usage_snapshot", lambda: {})

    text = bot.admin_provider_usage_text_v2().lower()

    for forbidden in ("api_key", "token", "secret", "authorization", "bearer"):
        assert forbidden not in text


def test_key4u_usage_event_recorded(monkeypatch):
    calls = []
    monkeypatch.setattr(bot, "record_provider_usage_event", lambda **kwargs: calls.append(kwargs))

    bot.record_key4u_usage_event(
        capability="chat",
        user_id="1",
        result={"status": "SUCCESS", "estimated_cost_usd": 0.123, "model": "qwen-plus"},
        note="known_cost",
    )

    assert calls
    assert calls[-1]["provider"] == "key4u"
    assert calls[-1]["estimated_cost_usd"] == 0.123
    assert "cost_unverified" not in calls[-1]["note"]


def test_key4u_unknown_cost_not_subtracted(monkeypatch):
    calls = []
    monkeypatch.setattr(bot, "record_provider_usage_event", lambda **kwargs: calls.append(kwargs))

    bot.record_key4u_usage_event(capability="chat", user_id="1", result={"status": "SUCCESS"}, note="unknown_cost")

    assert calls[-1]["estimated_cost_usd"] == 0.0
    assert "cost_unverified" in calls[-1]["note"]


def test_key4u_known_cost_subtracted(monkeypatch):
    _set_manual(monkeypatch, "10", estimated_cost_usd=3)

    assert bot.key4u_usage_alert_snapshot()["estimated_remaining"] == "7.0000 USD"


def test_key4u_estimated_remaining_recomputed(monkeypatch):
    _set_manual(monkeypatch, "10", estimated_cost_usd=0.5)
    first = bot.key4u_usage_alert_snapshot()["estimated_remaining"]
    _patch_usage(monkeypatch, estimated_cost_usd=2.5)

    second = bot.key4u_usage_alert_snapshot()["estimated_remaining"]

    assert first == "9.5000 USD"
    assert second == "7.5000 USD"


def test_key4u_refresh_unknown_endpoint_keeps_manual_alert(monkeypatch):
    _set_manual(monkeypatch, "14.101", estimated_cost_usd=0.101)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "key4u_provider_instance", lambda: (_ for _ in ()).throw(AssertionError("provider should not be called")))
    update = _fake_update()

    asyncio.run(bot.cmd_key4u_usage_refresh(update, SimpleNamespace(args=[])))

    text = update.message.replies[-1][0]
    assert "Key4U chưa có endpoint usage đã xác minh" in text
    assert "số dư thủ công + local estimate" in text


def test_key4u_no_dashboard_scrape():
    import inspect
    key4u_funcs = [
        bot.key4u_usage_alert_snapshot,
        bot.set_key4u_manual_balance_usd,
        bot.key4u_manual_balance_usd,
    ]
    source = "\n".join(inspect.getsource(f) for f in key4u_funcs).lower()

    for forbidden in ("dashboard_scrape", "selenium", "playwright", "cookie", "cookies"):
        assert forbidden not in source


def test_key4u_no_fake_remote_success(monkeypatch):
    _set_manual(monkeypatch, "14.101", estimated_cost_usd=0)

    snapshot = bot.key4u_usage_alert_snapshot()

    assert "chưa xác minh endpoint" in snapshot["remote_usage"]
    assert snapshot["source"] == "manual_admin"
    assert snapshot["remaining_source"] == "manual_admin_minus_local_estimate"


def test_key4u_alert_button_exists(monkeypatch):
    _set_manual(monkeypatch, "14.101", estimated_cost_usd=0)

    labels = _button_labels(bot.admin_provider_child_keyboard("admin_provider_usage"))

    assert "🚨 Key4U cảnh báo" in labels


def test_key4u_manual_balance_button_exists(monkeypatch):
    _set_manual(monkeypatch, "14.101", estimated_cost_usd=0)

    labels = _button_labels(bot.admin_provider_child_keyboard("admin_provider_usage"))

    assert "✍️ Cập nhật số dư Key4U" in labels


def test_key4u_freeze_button_exists(monkeypatch):
    _set_manual(monkeypatch, "14.101", estimated_cost_usd=0)

    labels = _button_labels(bot.admin_provider_child_keyboard("admin_provider_usage"))

    assert "🧊 Freeze Key4U nếu thấp" in labels


def test_key4u_usage_alert_admin_only(monkeypatch):
    _patch_settings(monkeypatch)
    _patch_usage(monkeypatch)
    _patch_freeze(monkeypatch)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    update = _fake_update(user_id=2)

    asyncio.run(bot.cmd_key4u_usage_alert(update, SimpleNamespace(args=[])))

    assert update.message.replies[-1][0] == "⛔ Bạn không có quyền dùng lệnh này."


def test_key4u_usage_alert_commands_registered():
    source = _source()

    assert 'CommandHandler("key4u_usage_alert", cmd_key4u_usage_alert)' in source
    assert 'CommandHandler("key4u_usage_alert_set", cmd_key4u_usage_alert_set)' in source
    assert 'CommandHandler("key4u_usage_alert_on", cmd_key4u_usage_alert_on)' in source
    assert 'CommandHandler("key4u_usage_alert_off", cmd_key4u_usage_alert_off)' in source
    assert 'CommandHandler("key4u_usage_freeze_if_low", cmd_key4u_usage_freeze_if_low)' in source
    assert 'CommandHandler("key4u_usage_unfreeze", cmd_key4u_usage_unfreeze)' in source
