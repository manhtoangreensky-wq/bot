import asyncio
import inspect
import subprocess
from types import SimpleNamespace

import bot
from aiedit1_scope_guard import arch1_scope_active, without_aiedit1_scope, _current_branch


def _patch_settings(monkeypatch):
    store = {}

    def get_setting(key, default=""):
        return store.get(key, default)

    def set_setting(key, value, note="", updated_by=""):
        store[key] = str(value)

    monkeypatch.setattr(bot, "get_system_setting", get_setting)
    monkeypatch.setattr(bot, "set_system_setting", set_setting)
    return store


def _usage():
    return {
        "total": 261,
        "used": 238.5,
        "balance": 22.5,
        "remaining": 22.5,
        "remaining_percent": 8.62,
        "group_name": "cheap",
        "token_name": "masked-token",
    }


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))
        return SimpleNamespace(message_id=len(self.replies))


def _update(user_id=1):
    return SimpleNamespace(effective_user=SimpleNamespace(id=user_id), message=FakeMessage())


def _source_between(source: str, start: str, end: str) -> str:
    assert start in source
    chunk = source.split(start, 1)[1]
    if end in chunk:
        chunk = chunk.split(end, 1)[0]
    return start + chunk


def test_cost2_quota_cycle_baseline_persists(monkeypatch):
    _patch_settings(monkeypatch)
    baseline = bot.set_provider_quota_cycle_baseline("shopaikey", 100, "nap_100_usd_2026_07_07", "admin")

    loaded = bot.provider_quota_cycle_baseline("shopaikey")

    assert baseline["enabled"] is True
    assert loaded["enabled"] is True
    assert loaded["cycle_total_usd"] == 100
    assert loaded["cycle_note"] == "nap_100_usd_2026_07_07"
    assert loaded["created_by_admin"] == "admin"


def test_cost2_quota_cycle_percent_uses_cycle_total(monkeypatch):
    _patch_settings(monkeypatch)
    bot.set_provider_quota_cycle_baseline("shopaikey", 100, "topup", "admin")

    payload = bot.provider_quota_usage_payload("shopaikey", _usage())

    assert payload["baseline_active"] is True
    assert payload["denominator"] == 100
    assert payload["remaining_percent"] == 22.5


def test_cost2_quota_without_baseline_preserves_legacy_behavior(monkeypatch):
    _patch_settings(monkeypatch)

    payload = bot.provider_quota_usage_payload("shopaikey", _usage())

    assert payload["baseline_active"] is False
    assert payload["denominator"] == 261
    assert payload["remaining_percent"] == 8.62


def test_cost2_does_not_modify_provider_balance(monkeypatch):
    _patch_settings(monkeypatch)
    usage = _usage()
    bot.set_provider_quota_cycle_baseline("shopaikey", 100, "topup", "admin")

    payload = bot.provider_quota_usage_payload("shopaikey", usage)

    assert usage["balance"] == 22.5
    assert payload["provider_balance"] == 22.5
    assert payload["provider_total"] == 261


def test_cost2_provider_quota_status_command(monkeypatch):
    store = _patch_settings(monkeypatch)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    store.update({
        "shopaikey_usage_total": "261",
        "shopaikey_usage_used": "238.5",
        "shopaikey_usage_balance": "22.5",
        "shopaikey_usage_remaining": "22.5",
        "shopaikey_usage_remaining_percent": "8.62",
        "shopaikey_usage_group_name": "cheap",
    })
    update = _update()

    asyncio.run(bot.cmd_provider_quota_status(update, SimpleNamespace(args=[])))

    text = "\n".join(reply[0] for reply in update.message.replies)
    assert "SHOPAIKEY QUOTA STATUS" in text
    assert "Provider lifetime total" in text
    assert "No local quota cycle baseline set." in text


def test_cost2_provider_quota_reset_admin_only(monkeypatch):
    store = _patch_settings(monkeypatch)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    update = _update(user_id=2)

    asyncio.run(bot.cmd_provider_quota_reset(update, SimpleNamespace(args=["shopaikey", "100"])))

    assert update.message.replies[-1][0] == "⛔ Bạn không có quyền dùng lệnh này."
    assert store == {}


def test_cost2_provider_quota_reset_sets_100_baseline(monkeypatch):
    _patch_settings(monkeypatch)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    update = _update()

    asyncio.run(bot.cmd_provider_quota_reset(update, SimpleNamespace(args=["shopaikey", "100", "note=nap_100_usd_2026_07_07"])))
    baseline = bot.provider_quota_cycle_baseline("shopaikey")

    assert baseline["enabled"] is True
    assert baseline["cycle_total_usd"] == 100
    assert baseline["cycle_note"] == "nap_100_usd_2026_07_07"
    assert "Đã đặt quota cycle baseline" in update.message.replies[-1][0]


def test_cost2_provider_quota_clear_disables_baseline(monkeypatch):
    _patch_settings(monkeypatch)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    bot.set_provider_quota_cycle_baseline("shopaikey", 100, "topup", "admin")
    update = _update()

    asyncio.run(bot.cmd_provider_quota_clear(update, SimpleNamespace(args=["shopaikey"])))

    assert bot.provider_quota_cycle_baseline("shopaikey")["enabled"] is False
    assert "Alert quay về cách tính legacy" in update.message.replies[-1][0]


def test_cost2_warning_copy_suggests_reset_command(monkeypatch):
    _patch_settings(monkeypatch)

    text = bot.provider_quota_alert_text("shopaikey", _usage())

    assert "/provider_quota_reset shopaikey 100" in text


def test_cost2_225_balance_over_100_not_low_at_20_percent(monkeypatch):
    _patch_settings(monkeypatch)
    monkeypatch.setattr(bot, "SHOPAIKEY_USAGE_ALERT_PERCENT", 20)
    bot.set_provider_quota_cycle_baseline("shopaikey", 100, "topup", "admin")

    payload = bot.provider_quota_usage_payload("shopaikey", _usage())

    assert payload["remaining_percent"] == 22.5
    assert payload["alert_state"] == "NORMAL"


def test_cost2_225_balance_over_261_is_low_without_baseline(monkeypatch):
    _patch_settings(monkeypatch)
    monkeypatch.setattr(bot, "SHOPAIKEY_USAGE_ALERT_PERCENT", 20)

    payload = bot.provider_quota_usage_payload("shopaikey", _usage())

    assert payload["remaining_percent"] == 8.62
    assert payload["alert_state"] == "LOW"


def test_cost2_alert_uses_cycle_percent_when_enabled(monkeypatch):
    _patch_settings(monkeypatch)
    monkeypatch.setattr(bot, "SHOPAIKEY_USAGE_ALERT_PERCENT", 20)
    bot.set_provider_quota_cycle_baseline("shopaikey", 100, "topup", "admin")

    assert bot.shopaikey_low_quota_alert_due(22.5, 20) is False
    assert bot.provider_quota_usage_payload("shopaikey", _usage())["alert_state"] == "NORMAL"


def test_cost2_alert_copy_shows_cycle_total_not_lifetime_total(monkeypatch):
    _patch_settings(monkeypatch)
    bot.set_provider_quota_cycle_baseline("shopaikey", 100, "topup", "admin")

    text = bot.provider_quota_alert_text("shopaikey", _usage())

    assert "Remaining: 22.5 / cycle 100 (22.50%)" in text
    assert "Provider lifetime total: 261" in text


def test_cost2_alert_copy_masks_secrets(monkeypatch):
    _patch_settings(monkeypatch)
    usage = _usage()
    usage["token_name"] = "sk-secret-token"

    text = bot.provider_quota_alert_text("shopaikey", usage).lower()

    for forbidden in ("sk-secret-token", "apikey=", "bearer ", "token="):
        assert forbidden not in text


def test_cost2_alert_copy_shows_cycle_when_active(monkeypatch):
    _patch_settings(monkeypatch)
    bot.set_provider_quota_cycle_baseline("shopaikey", 100, "topup", "admin")

    text = "\n".join(bot.provider_quota_status_lines("shopaikey", _usage()))

    assert "Baseline: <code>active</code>" in text
    assert "Cycle total: <code>100 USD</code>" in text


def test_cost2_alert_copy_shows_no_baseline_when_missing(monkeypatch):
    _patch_settings(monkeypatch)

    text = "\n".join(bot.provider_quota_status_lines("shopaikey", _usage()))

    assert "No local quota cycle baseline set." in text


def test_cost2_commands_registered():
    source = inspect.getsource(bot)

    assert 'CommandHandler("provider_quota_status", cmd_provider_quota_status)' in source
    assert 'CommandHandler("provider_quota_reset", cmd_provider_quota_reset)' in source
    assert 'CommandHandler("provider_quota_clear", cmd_provider_quota_clear)' in source


def _changed_paths():
    try:
        return subprocess.check_output(["git", "diff", "--name-only", "origin/main", "--"], text=True, encoding="utf-8").splitlines()
    except Exception:
        return []


def _bot_diff():
    try:
        return subprocess.check_output(["git", "diff", "origin/main", "--", "bot.py"], text=True, encoding="utf-8")
    except Exception:
        return ""


def test_cost2_no_music_changes():
    diff = _bot_diff().lower()
    assert "music_" not in diff
    assert "suno" not in diff


def test_cost2_no_product_video_submit_changes():
    diff = _bot_diff().replace("submit_video_ai_edit_job", "")
    forbidden = ("VideoSubmitRequest", "submit_video", "shopaikey_video_job_status", "cmd_tool_test_shopaikey_video")
    assert not any(item in diff for item in forbidden)


def test_cost2_no_img2vid_changes():
    assert "img2vid" not in _bot_diff().lower()


def test_cost2_no_subdub_changes():
    if arch1_scope_active(_changed_paths()):
        return
    if _current_branch().startswith("hotfix/p0-subdub"):
        # An active SubDub-scoped task legitimately edits SubDub handlers in
        # bot.py; this guard protects every other (non-SubDub) branch.
        return
    diff = _bot_diff().lower()
    assert "video_dubbing" not in diff
    assert "subdub" not in diff


def test_cost2_no_payos_wallet_finance_changes():
    diff = _bot_diff().lower()
    for forbidden in ("payos", "/naptien", "wallet", "finance_"):
        assert forbidden not in diff


def test_cost2_no_provider_paid_calls():
    source = inspect.getsource(bot)
    command_source = _source_between(source, "async def cmd_provider_quota_status", "async def cmd_tool_test_shopaikey")
    for forbidden in ("get_shopaikey_usage(", "tool_test_shopaikey", "create_shopaikey_job", "spend_fixed_credit_info"):
        assert forbidden not in command_source
    assert without_aiedit1_scope(_changed_paths()) <= {
        "bot.py",
        "tests/test_p0_cost2_provider_quota_cycle_reset_alert_baseline.py",
    }
