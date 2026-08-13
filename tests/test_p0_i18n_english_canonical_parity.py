"""Focused source-only contract for the international English canonical copy.

The checks deliberately avoid importing ``bot`` so they cannot start Telegram,
providers, payment services, workers, or database connections.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
GUIDE_SOURCE = (ROOT / "services" / "pricing_guide_content.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    match = re.search(
        rf"^(?:async\s+)?def\s+{re.escape(name)}\b.*?(?=^(?:async\s+)?def\s+|\Z)",
        BOT_SOURCE,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, name
    return match.group(0)


def test_english_topup_is_native_and_has_no_domestic_promo_commands():
    source = _function_source("cmd_naptien")
    for marker in (
        'requested_locale != "vi"', "public_account_flow_copy(requested_locale)",
        "topup_policy_title", "topup_verified_base", "manual_topup_section",
        "back_pricing", "main_menu",
    ):
        assert marker in source
    for marker in (
        "International Xu top-up policy", "verified base Xu only",
        "Manual top-up", "Back to pricing", "Main menu",
    ):
        assert marker in GUIDE_SOURCE
    for command in ("/promo", "/khuyenmai", "/magiamgia", "/uudai"):
        assert command not in source


def test_english_referral_commands_have_direct_complete_copy():
    expected = {
        "cmd_ref": ("ref_title_full", "ref_how", "quick_stats"),
        "cmd_ref_link": ("referral_link",),
        "cmd_ref_stats": ("referral_stats", "qualified_no_reward"),
    }
    for name, keys in expected.items():
        source = _function_source(name)
        assert "public_account_flow_copy(requested_locale)" in source
        assert 'requested_locale != "vi"' in source
        for key in keys:
            assert key in source
    for marker in (
        "REFER FRIENDS TO TOAN AAS", "How rewards work", "Quick statistics",
        "Referral link", "REFERRAL STATISTICS",
        "Eligible but current tier has no reward",
    ):
        assert marker in GUIDE_SOURCE


def test_english_birthday_commands_and_pricing_callback_are_native():
    birthday = _function_source("cmd_birthday")
    set_birthday = _function_source("cmd_set_birthday")
    pricing_callback = _function_source("handle_pricing_callback")
    gift_message = _function_source("format_birthday_gift_message")
    auto_gift = _function_source("maybe_auto_grant_birthday_gift")
    for marker in ("public_account_flow_copy(lang)", "birthday_title", "your_birthday", "birthday_manual_review"):
        assert marker in birthday
    for marker in ("public_account_flow_copy(lang)", "invalid_birthday", "review_pending", "birthday_saved"):
        assert marker in set_birthday
    assert "copy['save_birthday']" in pricing_callback
    assert "public_hub_copy(lang)['common_no_charge']" in pricing_callback
    assert "public_account_flow_copy(public_pricing_locale(lang))" in gift_message
    assert "birthday_gift_title" in gift_message
    assert "format_birthday_gift_message(result, lang)" in auto_gift
    for marker in (
        "TOAN AAS BIRTHDAY GIFT", "YOUR BIRTHDAY", "manual admin review",
        "Invalid birthday", "Your birthday review request", "Birthday saved",
        "HAPPY BIRTHDAY",
    ):
        assert marker in GUIDE_SOURCE


def test_english_profile_and_member_surfaces_keep_all_non_topup_benefits():
    profile = _function_source("cmd_profile")
    member = _function_source("cmd_member")
    policy = _function_source("member_policy_lines")
    for marker in (
        "public_account_flow_copy(lang)", "referral_link", "monthly_plan",
        "birthday_benefit", "profile_policy_note",
    ):
        assert marker in profile
    for marker in (
        "public_account_flow_copy(requested_locale)", "referral_benefit",
        "birthday_loyalty", "member_non_topup_note", "topup_boundary",
    ):
        assert marker in member
    for marker in ("member_service_discount", "birthday_loyalty", "referral_benefit", "member_non_topup_note"):
        assert marker in policy
    for marker in (
        "Referral link", "Monthly plan", "Birthday benefit",
        "Member service discount", "Birthday and loyalty",
        "Eligible birthday, loyalty, and referral benefits",
    ):
        assert marker in GUIDE_SOURCE
    for command in ("/promo", "/khuyenmai", "/magiamgia", "/uudai"):
        assert command not in policy


def test_international_guides_keep_referral_and_other_non_topup_benefits():
    for marker in (
        "birthday or loyalty benefits",
        "referral benefits",
        "other eligible non-top-up benefits",
    ):
        assert marker in GUIDE_SOURCE
    assert "birthday or loyalty benefits only" not in BOT_SOURCE
    assert "eligible member benefits only" not in BOT_SOURCE
