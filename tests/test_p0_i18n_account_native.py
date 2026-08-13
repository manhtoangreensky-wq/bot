"""Focused source-only contract for native account and promotion copy.

The checks intentionally avoid importing ``bot`` so Telegram, providers,
payments, the wallet, workers, and the database remain untouched.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COPY_SOURCE = (ROOT / "services" / "pricing_guide_content.py").read_text(encoding="utf-8")
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
LOCALES = {
    "vi", "en", "zh", "ja", "ko", "th", "ar", "es", "pt", "fr", "de",
    "hi", "ru", "tr", "fil", "it", "id",
}
SECONDARY = LOCALES - {"vi", "en"}
PROMO_COMMANDS = ("/promo", "/khuyenmai", "/magiamgia", "/uudai")
ACCOUNT_EXTRA_KEYS = (
    "referral_link", "referral_stats", "referral_status_pending",
    "referral_status_rewarded", "referral_status_qualified_no_reward",
    "promo_neutral_title", "promo_neutral_body", "birthday_gift_title",
    "birthday_gift_received", "new_balance", "birthday_wish",
)


def _module_literals(source: str) -> dict[str, object]:
    values: dict[str, object] = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            try:
                value = ast.literal_eval(node.value)
            except (TypeError, ValueError):
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    values[target.id] = value
            continue
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not (
            isinstance(call.func, ast.Attribute)
            and call.func.attr == "update"
            and isinstance(call.func.value, ast.Name)
            and len(call.args) == 1
            and isinstance(values.get(call.func.value.id), dict)
        ):
            continue
        values[call.func.value.id].update(ast.literal_eval(call.args[0]))
    return values


def _function_source(name: str) -> str:
    match = re.search(
        rf"^(?:async\s+)?def\s+{re.escape(name)}\b.*?(?=^(?:async\s+)?def\s+|^class\s+|^@|\Z)",
        BOT_SOURCE,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, name
    return match.group(0)


def test_account_copy_has_direct_complete_native_rows_for_all_17_locales():
    from services.pricing_guide_content import PUBLIC_COPY_LOCALES, public_account_flow_copy

    rendered = {locale: public_account_flow_copy(locale) for locale in PUBLIC_COPY_LOCALES}
    assert set(rendered) == LOCALES
    assert "def _account_flow_generic" not in COPY_SOURCE
    assert "_PUBLIC_ACCOUNT_FLOW_COPY[_locale] = _account_flow_generic" not in COPY_SOURCE
    expected_keys = set(rendered["en"])
    assert set(ACCOUNT_EXTRA_KEYS) <= set(rendered["en"])
    assert all(set(row) == expected_keys for row in rendered.values())
    for locale in SECONDARY:
        assert all(str(value).strip() for value in rendered[locale].values()), locale
        assert rendered[locale]["profile_policy_note"] != rendered["en"]["profile_policy_note"]
        assert rendered[locale]["profile_policy_note"] != rendered["vi"]["profile_policy_note"]
        assert rendered[locale]["topup_verified_base"] != rendered["en"]["topup_verified_base"]
        assert rendered[locale]["topup_verified_base"] != rendered["vi"]["topup_verified_base"]


def test_account_renderers_use_native_copy_and_localize_referral_rows_and_statuses():
    for name in (
        "cmd_profile", "cmd_naptien", "cmd_ref", "cmd_ref_link", "cmd_ref_stats",
        "cmd_member", "cmd_birthday", "cmd_set_birthday", "format_birthday_gift_message",
    ):
        assert "public_account_flow_copy" in _function_source(name), name
    ref_source = _function_source("cmd_ref")
    assert "copy['ref_reward_formula'].format" in ref_source
    assert "of eligible base Xu, up to" not in ref_source
    stats_source = _function_source("cmd_ref_stats")
    assert "referral_status_labels" in stats_source
    international_branch = stats_source.split('if requested_locale != "vi":', 1)[1].split('    lines = [', 1)[0]
    assert "html.escape(str(status))" not in international_branch


def test_international_promo_surfaces_use_neutral_native_copy_and_hide_topup_commands():
    for name in ("billing_promotions_lines", "billing_promo_apply_lines"):
        source = _function_source(name)
        assert "public_account_flow_copy(requested_locale)" in source, name
        assert "public_pricing_lines(\"member\"" not in source, name
        assert "Tài khoản quốc tế" not in source, name
    keyboard = _function_source("billing_promotions_keyboard")
    assert "public_account_flow_copy(requested_locale)" in keyboard
    for name in ("_cmd_promo_impl", "cmd_promo_guide", "cmd_my_promos"):
        source = _function_source(name)
        assert "show_domestic_topup_promotion" in source, name
        assert "billing_promo_apply_lines" in source, name
    from services.pricing_guide_content import public_account_flow_copy

    table = {locale: public_account_flow_copy(locale) for locale in LOCALES}
    for locale in LOCALES - {"vi"}:
        neutral = "\n".join(table[locale][key] for key in ("promo_neutral_title", "promo_neutral_body", "topup_verified_base"))
        assert not any(command in neutral for command in PROMO_COMMANDS), locale


def test_account_copy_changes_do_not_change_callbacks_or_handlers():
    assert 'CommandHandler("promo",       cmd_promo)' in BOT_SOURCE
    assert 'CommandHandler("magiamgia",   cmd_promo)' in BOT_SOURCE
    assert 'CommandHandler("khuyenmai",   cmd_promo_guide)' in BOT_SOURCE
    assert 'CommandHandler("uudai",       cmd_promo_guide)' in BOT_SOURCE
    keyboard = _function_source("billing_promotions_keyboard")
    for callback in ("pricing|catalog", "menu|main_topup", "pricing|main", "menu|main"):
        assert callback in keyboard


def test_member_and_apply_surfaces_keep_referral_birthday_loyalty_for_en_zh():
    member = _function_source("cmd_member")
    apply_lines = _function_source("billing_promo_apply_lines")
    # English and Chinese use the same direct native account renderer as every
    # other international locale; no separate binary branch may omit benefits.
    assert 'if requested_locale != "vi":' in member
    assert "copy['referral_benefit']" in member
    assert "copy['birthday_loyalty']" in member
    assert 'copy["topup_boundary"]' in member or "copy['topup_boundary']" in member
    assert 'copy["topup_benefits_remain"]' in apply_lines or "copy['topup_benefits_remain']" in apply_lines
    assert 'public_account_flow_copy(requested_locale)' in apply_lines
