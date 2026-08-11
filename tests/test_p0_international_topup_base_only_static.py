from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "bot.py"
PUBLIC_POLICY = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "public"
    / "TOAN_AAS_DIEU_KHOAN_CHINH_SACH_DICH_VU_V2.md"
)


def _between(source: str, start: str, end: str) -> str:
    left = source.index(start)
    right = source.index(end, left)
    return source[left:right]


def _function_source(source: str, name: str) -> str:
    start = source.index(f"def {name}(")
    right = source.find("\ndef ", start + 1)
    return source[start:] if right < 0 else source[start:right]


def test_payos_and_manual_topups_gate_all_international_additive_xu_before_credit():
    source = SOURCE.read_text(encoding="utf-8")
    payos = _between(source, "def process_payos_paid_order(", "# ─── ADMIN ALERT")
    manual = _between(source, "async def cmd_duyet(", "async def cmd_billing_bridge_status(")
    admin_tier_grant = _between(source, "async def cmd_grant_tier_promo(", "async def cmd_set_vip(")
    tier_reward = _between(source, "def create_member_tier_reward(", "def member_tiers_crossed(")

    assert "eligible_for_additive_rewards = is_topup_bonus_allowed(topup_payment_context)" in payos
    assert "if eligible_for_additive_rewards:" in payos
    assert "grant_topup_rewards=eligible_for_additive_rewards" in payos

    assert "verified_base_xu" in manual
    assert "int(amount) > verified_base_xu" in manual
    assert manual.index("int(amount) > verified_base_xu") < manual.index("UPDATE users SET credits=credits+")
    assert "canonical_user_market_snapshot_conn" in admin_tier_grant
    assert "international_account" in admin_tier_grant
    assert "international_topup_reward_disabled" in tier_reward


def test_manual_pending_snapshot_drives_international_bonus_copy_fail_closed():
    source = SOURCE.read_text(encoding="utf-8")
    creation = _between(source, "def create_manual_pending_deposit(", "def manual_pending_admin_text(")
    helper = _between(source, "def manual_pending_bonus_allowed(", "def manual_pending_admin_text(")
    admin_copy = _between(source, "def manual_pending_admin_text(", "def manual_pending_admin_keyboard(")
    user_copy = _between(source, "def manual_pending_user_text(", "async def notify_manual_pending_deposit(")

    assert "user_market_snapshot" in creation
    assert "payment_market" in creation
    assert "domestic_eligibility" in creation
    assert "user_market_snapshot" in helper
    assert "user_market_snapshot" in admin_copy
    assert "manual_pending_bonus_allowed(deposit)" in admin_copy
    assert "manual_pending_bonus_allowed(deposit)" in user_copy


def test_international_topup_copy_uses_the_authorized_channels_and_base_xu_only_policy():
    source = SOURCE.read_text(encoding="utf-8")
    pricing_xu = _between(source, "def pricing_xu_lines_i18n(", "def pricing_plans_lines_i18n(")
    guide_i18n = _between(source, "def guide_section_text_i18n(", "async def reply_internal_customer_feature(")

    assert "USD top-up: USDT TRC20 only." in pricing_xu
    assert "CNY 充值可使用 ZaloPay/manual 或 Binance / USDT TRC20。" in pricing_xu
    assert "International top-ups receive only verified base Xu" in guide_i18n
    assert "国际充值只获得经核验的基础 Xu" in guide_i18n


def test_topup_presentation_uses_account_market_not_interface_language():
    source = SOURCE.read_text(encoding="utf-8")
    topup_menu = _between(source, "def menu_text_main_topup_i18n(", "def menu_text_main_profile_i18n(")
    pricing_hub = _between(source, "def pricing_hub_lines(", "def billing_promotions_lines(")
    pricing_keyboard = _between(source, "def pricing_main_keyboard(", "def pricing_catalog_keyboard(")

    assert "international_account = user_id is not None and not user_is_vietnam_market(user_id)" in topup_menu
    assert "international_account = user_id is not None and not user_is_vietnam_market(user_id)" in pricing_hub
    assert "🎁 View offers" in pricing_keyboard
    assert "🎁 查看优惠" in pricing_keyboard
    assert "pricing_main_keyboard(lang, uid)" in source
    assert "pricing_main_keyboard(lang, update.effective_user.id if update.effective_user else None)" in source


def test_public_manual_approval_policy_forbids_international_topup_over_credit():
    policy = PUBLIC_POLICY.read_text(encoding="utf-8")

    assert "Tài khoản quốc tế chỉ được duyệt đúng Xu gốc đã xác minh" in policy
    assert "Không dùng duyệt bill quốc tế để cộng bonus, mã nạp, referral Xu hoặc Xu điều chỉnh vượt mức." in policy


def test_manual_topup_copy_hides_domestic_bonus_when_the_interface_is_not_vietnamese():
    source = SOURCE.read_text(encoding="utf-8")
    namespace = {
        "__builtins__": __builtins__,
        "user_is_vietnam_market": lambda user_id: str(user_id) == "vn-user",
        "manual_topup_rules_text": lambda: "rules",
        "public_copy_locale": lambda lang: str(lang or "vi").lower(),
        "international_topup_policy_lines": lambda lang: [f"{lang} base Xu only"],
        "html": type("Html", (), {"escape": staticmethod(str)}),
    }
    exec(_function_source(source, "manual_payment_menu_text"), namespace)

    vietnamese = namespace["manual_payment_menu_text"]("vn-user", "vi")
    english = namespace["manual_payment_menu_text"]("vn-user", "en")

    assert "+30%" in vietnamese
    assert "+20%" in vietnamese
    assert "+30%" not in english
    assert "+20%" not in english
    assert "Khách Việt Nam nạp VND" not in english
    assert "en base Xu only" in english
