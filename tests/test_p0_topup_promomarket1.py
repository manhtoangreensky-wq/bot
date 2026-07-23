import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import admin_broadcast
import bot


def _isolated_db(monkeypatch, tmp_path):
    db_path = tmp_path / "promomarket1.sqlite3"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "ADMIN_ID", "admin-only")
    monkeypatch.setattr(bot, "enqueue_broadcast_after_first_topup_safe", lambda _user_id: {"queued": False, "reason": "test"})
    bot.init_db()
    return db_path


def _create_user(user_id, language="vi", *, market=None, international=None):
    user_id = str(user_id)
    bot.get_user(user_id, f"test-{user_id}")
    bot.set_user_language(user_id, language)
    if market is None and international is None:
        return
    normalized_market = market or ("INTL" if international else "VN")
    is_international = int(bool(international if international is not None else normalized_market == "INTL"))
    country = "VN" if normalized_market == "VN" else "US"
    region = "VIETNAM" if normalized_market == "VN" else "INTERNATIONAL"
    conn = bot.db_connect()
    try:
        conn.execute(
            """UPDATE users
               SET user_market=?,country_code=?,account_region=?,international_account=?
               WHERE user_id=?""",
            (normalized_market, country, region, is_international, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def _settle(user_id, order_code, amount=10_000, transaction_id="", *, metadata=None, status="PAID"):
    payment_metadata = {
        "payment_method": "payos",
        "currency": "VND",
    }
    payment_metadata.update(metadata or {})
    bot.create_order(
        order_code,
        str(user_id),
        amount,
        max(1, amount // 100),
        metadata_json=json.dumps(payment_metadata, ensure_ascii=False),
    )
    _, invoice_total = bot.payos_invoice_total_for_order(order_code, amount)
    return bot.process_payos_paid_order(
        order_code,
        invoice_total,
        transaction_id=transaction_id,
        webhook_status=status,
        webhook_currency=str(payment_metadata.get("currency") or "VND"),
    )


def _credits(user_id):
    return int(bot.get_user(str(user_id))[0])


def test_vietnam_first_second_third_and_duplicate_webhook_are_idempotent(monkeypatch, tmp_path):
    _isolated_db(monkeypatch, tmp_path)
    user_id = "10001"
    _create_user(user_id, "vi")
    initial = _credits(user_id)

    first = _settle(user_id, "promo-1", transaction_id="tx-promo-1")
    second = _settle(user_id, "promo-2", transaction_id="tx-promo-2")
    third = _settle(user_id, "promo-3", transaction_id="tx-promo-3")

    assert first[0:2] == (True, "success")
    assert second[0:2] == (True, "success")
    assert third[0:2] == (True, "success")
    assert first[2]["auto_bonus"] == 30
    assert first[2]["auto_bonus_percent"] == 30
    assert second[2]["auto_bonus"] == 20
    assert second[2]["auto_bonus_percent"] == 20
    assert third[2]["auto_bonus"] == 0
    assert third[2]["auto_promotion_id"] == ""
    assert bot.PROMOTION_MINIMUM_TOPUP_VND == 10_000
    assert _credits(user_id) - initial == 100 + 30 + 100 + 20 + 100

    replay = bot.process_payos_paid_order(
        "promo-1",
        10_000,
        transaction_id="tx-promo-1",
        webhook_status="PAID",
        webhook_currency="VND",
    )
    assert replay[0:2] == (False, "already_paid")
    assert _credits(user_id) == initial + 350

    conn = bot.db_connect()
    try:
        redemptions = conn.execute(
            """SELECT promotion_id,successful_topup_ordinal,bonus_xu,payment_transaction_id
               FROM topup_promotion_redemptions WHERE user_id=? ORDER BY redemption_id""",
            (user_id,),
        ).fetchall()
        assert [(row[0], row[1], row[2], row[3]) for row in redemptions] == [
            (bot.AUTO_FIRST_TOPUP_PROMOTION_ID, 1, 30, "tx-promo-1"),
            (bot.AUTO_SECOND_TOPUP_PROMOTION_ID, 2, 20, "tx-promo-2"),
        ]
        assert conn.execute(
            "SELECT COUNT(*) FROM credit_events WHERE user_id=? AND event_type LIKE 'auto_%'",
            (user_id,),
        ).fetchone()[0] == 2
        assert conn.execute(
            "SELECT COUNT(*) FROM payos_processed_events WHERE user_id=? AND credited=1",
            (user_id,),
        ).fetchone()[0] == 3
    finally:
        conn.close()


@pytest.mark.parametrize("payment_status", ["PENDING", "FAILED", "REFUNDED"])
def test_unsettled_status_does_not_advance_ordinal(monkeypatch, tmp_path, payment_status):
    _isolated_db(monkeypatch, tmp_path)
    user_id = "10002"
    _create_user(user_id, "vi")
    conn = bot.db_connect()
    try:
        result = bot.automatic_topup_promotion_eligibility_conn(
            conn,
            user_id,
            {
                "payment_status": payment_status,
                "transaction_id": f"tx-{payment_status.lower()}",
                "currency": "VND",
                "method": "payos",
                "amount_vnd": 10_000,
                "base_xu": 100,
                "amount_valid": True,
                "base_credit_success": True,
            },
        )
    finally:
        conn.close()
    assert result["successful_topup_ordinal"] == 1
    assert result["reason"] == "payment_not_settled"


def test_missing_transaction_and_refund_do_not_count_as_successful_ordinal(monkeypatch, tmp_path):
    _isolated_db(monkeypatch, tmp_path)
    user_id = "10003"
    _create_user(user_id, "vi")

    missing_tx = _settle(user_id, "promo-no-tx", transaction_id="")
    refund = _settle(
        user_id,
        "promo-refund",
        transaction_id="tx-refund",
        metadata={"is_refund": True},
    )
    assert missing_tx[2]["auto_bonus"] == 0
    assert refund[2]["auto_bonus"] == 0

    valid = _settle(user_id, "promo-valid-after-exclusions", transaction_id="tx-valid")
    assert valid[2]["auto_bonus"] == 30
    assert valid[2]["successful_topup_ordinal"] == 1


def test_below_minimum_and_non_domestic_payments_never_receive_auto_bonus(monkeypatch, tmp_path):
    _isolated_db(monkeypatch, tmp_path)
    user_id = "10009"
    _create_user(user_id, "vi")

    below_minimum = _settle(user_id, "promo-below-min", amount=9_999, transaction_id="tx-below-min")
    assert below_minimum[0:2] == (True, "success")
    assert below_minimum[2]["auto_bonus"] == 0
    assert below_minimum[2]["domestic_eligibility"] is False

    conn = bot.db_connect()
    try:
        base_context = {
            "payment_status": "SETTLED",
            "transaction_id": "tx-market-gate",
            "amount_vnd": 10_000,
            "base_xu": 100,
            "amount_valid": True,
            "base_credit_success": True,
        }
        usd = bot.automatic_topup_promotion_eligibility_conn(
            conn,
            user_id,
            {**base_context, "currency": "USD", "method": "usdt_trc20"},
        )
        international_channel = bot.automatic_topup_promotion_eligibility_conn(
            conn,
            user_id,
            {**base_context, "currency": "VND", "method": "zalopay_personal"},
        )
        assert usd["eligible"] is False
        assert international_channel["eligible"] is False
        assert usd["payment_market"] == "INTL"
        assert international_channel["payment_market"] == "INTL"
        assert conn.execute(
            "SELECT COUNT(*) FROM topup_promotion_redemptions WHERE user_id=?",
            (user_id,),
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_international_market_and_initial_language_gate_promotions_and_notices(monkeypatch, tmp_path):
    db_path = _isolated_db(monkeypatch, tmp_path)
    vn_user = "10004"
    intl_en_user = "10005"
    intl_vi_user = "10006"
    _create_user(vn_user, "vi")
    _create_user(intl_en_user, "en")
    _create_user(intl_vi_user, "vi", market="INTL", international=True)

    # A later language change must not rewrite the first language/market decision.
    bot.set_user_language(vn_user, "en")
    assert bot.user_selected_vietnamese_initially(vn_user) is True
    assert bot.user_is_vietnam_market(vn_user) is True
    assert bot.user_selected_vietnamese_initially(intl_en_user) is False
    assert bot.user_selected_vietnamese_initially(intl_vi_user) is False

    first_vn = admin_broadcast.enqueue_first_start_notice(db_path, vn_user)
    assert first_vn["queued"] is True
    assert admin_broadcast.enqueue_first_start_notice(db_path, vn_user)["reason"] == "duplicate"
    assert admin_broadcast.enqueue_first_start_notice(db_path, intl_en_user)["queued"] is False
    assert admin_broadcast.enqueue_first_start_notice(db_path, intl_vi_user)["queued"] is False

    settled = _settle(vn_user, "promo-vn-after-notice", transaction_id="tx-vn-after-notice")
    assert settled[2]["auto_bonus"] == 30
    second_vn = admin_broadcast.enqueue_after_first_topup_notice(db_path, vn_user)
    assert second_vn["queued"] is True

    intl_payment = _settle(intl_en_user, "promo-intl", transaction_id="tx-intl")
    intl_vi_payment = _settle(intl_vi_user, "promo-intl-vi", transaction_id="tx-intl-vi")
    assert intl_payment[2]["auto_bonus"] == 0
    assert intl_vi_payment[2]["auto_bonus"] == 0
    assert intl_payment[2]["domestic_eligibility"] is False
    assert intl_vi_payment[2]["domestic_eligibility"] is False

    domestic_copy = "\n".join(bot.billing_promotions_lines("vi", vn_user))
    intl_copy = "\n".join(bot.billing_promotions_lines("vi", intl_vi_user))
    assert "10.000đ" in domestic_copy
    assert "+30%" in domestic_copy and "+20%" in domestic_copy
    assert "+30%" not in intl_copy and "+20%" not in intl_copy
    assert "ưu đãi nạp nội địa Việt Nam" in intl_copy
    assert "10.000đ" in "\n".join(bot.pricing_xu_lines_i18n("vi", vn_user))
    assert "+30%" not in "\n".join(bot.pricing_xu_lines_i18n("vi", intl_vi_user))
    assert "10.000đ" in Path(bot.__file__).read_text(encoding="utf-8")


def test_legacy_first_second_codes_are_not_a_second_bonus_path(monkeypatch, tmp_path):
    _isolated_db(monkeypatch, tmp_path)
    user_id = "10007"
    _create_user(user_id, "vi")
    bot.seed_promotion_policy()

    first_ok, first_status, _ = bot.activate_promo_for_user(user_id, "FIRST30")
    second_ok, second_status, _ = bot.activate_promo_for_user(user_id, "SECOND15")
    assert first_ok is False and first_status == "automatic_no_code"
    assert second_ok is False and second_status == "automatic_no_code"

    policy = {item["code"]: item for item in bot.PROMO_POLICY_CODES}
    assert policy[bot.PROMO_FIRST_TOPUP_CODE]["min_amount_vnd"] == 10_000
    assert policy[bot.PROMO_SECOND_TOPUP_CODE]["min_amount_vnd"] == 10_000
    assert policy[bot.PROMO_WEEKLY_CODE]["min_amount_vnd"] == 50_000
    for code in (
        bot.PROMO_WEEKLY_CODE,
        bot.PROMO_MONTHLY_CODE,
        bot.PROMO_DAILY_CODE,
        bot.PROMO_BETA_LIMITED_CODE,
    ):
        assert policy[code]["code_required"] is True


def test_manual_deposit_credit_event_is_idempotent(monkeypatch, tmp_path):
    _isolated_db(monkeypatch, tmp_path)
    user_id = "10008"
    _create_user(user_id, "vi")
    initial = _credits(user_id)

    assert bot.add_credit(user_id, 500, "manual_deposit", "deposit-10008", "test approval") is True
    assert bot.add_credit(user_id, 500, "manual_deposit", "deposit-10008", "duplicate approval") is False
    assert _credits(user_id) == initial + 500

    conn = bot.db_connect()
    try:
        assert conn.execute(
            """SELECT COUNT(*) FROM credit_events
               WHERE user_id=? AND event_type='manual_deposit' AND ref_id=? AND delta>0""",
            (user_id, "deposit-10008"),
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_manual_domestic_approval_is_atomic_idempotent_and_uses_first_second_bonus(monkeypatch, tmp_path):
    _isolated_db(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "ADMIN_IDS", {"9001"})
    monkeypatch.setattr(bot, "OWNER_IDS", set())
    user_id = "10010"
    _create_user(user_id, "vi")
    initial = _credits(user_id)

    class Message:
        def __init__(self):
            self.replies = []

        async def reply_text(self, text, **kwargs):
            self.replies.append((text, kwargs))

    class FakeBot:
        def __init__(self):
            self.sent = []

        async def send_message(self, **kwargs):
            self.sent.append(kwargs)

    message = Message()
    fake_bot = FakeBot()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=9001), message=message)

    def insert_pending(tx_hash):
        conn = bot.db_connect()
        try:
            cursor = conn.execute(
                """INSERT INTO pending_deposits
                   (user_id,username,submitted_at,status,amount,xu,method,currency,
                    amount_vnd,base_xu,bonus_xu,expected_xu,foreign_manual,
                    member_points_eligible,rank_discount_percent_preserved,tx_hash)
                   VALUES (?,?,?,'pending',?,?,?,?,?,?,?,?,0,1,1,?)""",
                (
                    user_id,
                    "manual-test",
                    bot.now_text(),
                    10_000,
                    100,
                    "bank_acb",
                    "VND",
                    10_000,
                    100,
                    0,
                    100,
                    tx_hash,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    first_id = insert_pending("manual-tx-first")
    first_context = SimpleNamespace(args=[str(first_id), "100"], bot=fake_bot)
    asyncio.run(bot.cmd_duyet(update, first_context))
    assert _credits(user_id) == initial + 130

    # Repeating the same approval finds no pending bill and cannot credit again.
    asyncio.run(bot.cmd_duyet(update, first_context))
    assert _credits(user_id) == initial + 130

    second_id = insert_pending("manual-tx-second")
    second_context = SimpleNamespace(args=[str(second_id), "100"], bot=fake_bot)
    asyncio.run(bot.cmd_duyet(update, second_context))
    assert _credits(user_id) == initial + 130 + 120

    conn = bot.db_connect()
    try:
        rows = conn.execute(
            """SELECT id,status,successful_topup_ordinal,first_bonus_applied
               FROM pending_deposits WHERE id IN (?,?) ORDER BY id""",
            (first_id, second_id),
        ).fetchall()
        assert [tuple(row) for row in rows] == [
            (first_id, "approved", 1, 1),
            (second_id, "approved", 2, 0),
        ]
        assert conn.execute(
            """SELECT COUNT(*) FROM credit_events
               WHERE user_id=? AND event_type='manual_deposit' AND delta=100""",
            (user_id,),
        ).fetchone()[0] == 2
        assert conn.execute(
            """SELECT COUNT(*) FROM credit_events
               WHERE user_id=? AND event_type IN ('auto_first_topup_bonus','auto_second_topup_bonus')""",
            (user_id,),
        ).fetchone()[0] == 2
        redemptions = conn.execute(
            """SELECT promotion_id,successful_topup_ordinal,bonus_xu
               FROM topup_promotion_redemptions WHERE user_id=? ORDER BY redemption_id""",
            (user_id,),
        ).fetchall()
        assert [tuple(row) for row in redemptions] == [
            (bot.AUTO_FIRST_TOPUP_PROMOTION_ID, 1, 30),
            (bot.AUTO_SECOND_TOPUP_PROMOTION_ID, 2, 20),
        ]
    finally:
        conn.close()
