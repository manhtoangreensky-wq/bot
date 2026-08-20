import pytest
import bot


def test_admin_control_center_keyboard_has_marketing_button():
    kb = bot.admin_control_center_keyboard()
    all_buttons = [btn for row in kb.inline_keyboard for btn in row]
    marketing_btns = [btn for btn in all_buttons if "Marketing" in btn.text or btn.callback_data == "admin_growth|main"]
    assert len(marketing_btns) == 1
    assert marketing_btns[0].callback_data == "admin_growth|main"


def test_admin_growth_marketing_keyboard_buttons():
    kb = bot.admin_growth_marketing_keyboard()
    all_callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "admin_growth|affiliates" in all_callbacks
    assert "admin_growth|ideas" in all_callbacks
    assert "admin_growth|calendar" in all_callbacks
    assert "admin_growth|cockpit" in all_callbacks
    assert "admin_growth|channels" in all_callbacks
    assert "admin_growth|packages" in all_callbacks
    assert "menu|admin" in all_callbacks


def test_slash_commands_remain_registered():
    assert callable(bot.cmd_affiliate_import)
    assert callable(bot.cmd_campaign)
    assert callable(bot.cmd_addcal)
    assert callable(bot.cmd_calendar)
    assert callable(bot.cmd_affiliate_cockpit)
    assert callable(bot.cmd_growth_ai)
    assert callable(bot.cmd_growth_loop)
    assert callable(bot.cmd_growth)


def test_social_channel_tiktok_unverified_manual_mode():
    row = (1, "tiktok", "TikTok Channel", "creator", "active", "manual", "", "")
    status_code, msg = bot.channel_publish_readiness(row)
    assert status_code == "manual_ready"


def test_affiliate_cockpit_data_truthful_without_fabrication():
    pack = bot.affiliate_campaign_cockpit_data("admin_test_user", days=30, limit=5)
    assert "summary" in pack
    assert "winners" in pack
    assert "bottlenecks" in pack
    summary = pack["summary"]
    assert "affiliate_views" in summary
    assert "affiliate_clicks" in summary
    assert "affiliate_conversions" in summary
