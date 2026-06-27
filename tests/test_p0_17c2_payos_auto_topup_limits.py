import asyncio
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import bot


BASE_TIME = datetime(2026, 6, 27, 12, 0, 0)


def _init_db(monkeypatch, tmp_path, name="p0_17c2.db"):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / name))
    bot.USER_BILL_STATE.clear()
    bot.init_db()


def _credits(user_id: str) -> int:
    credits, _, _ = bot.get_user(user_id, f"user-{user_id}")
    return int(credits or 0)


def _order_count() -> int:
    conn = bot.db_connect()
    try:
        row = conn.execute("SELECT COUNT(*) FROM payos_orders").fetchone()
        return int(row[0] or 0)
    finally:
        conn.close()


def _manual_deposit_count() -> int:
    conn = bot.db_connect()
    try:
        row = conn.execute("SELECT COUNT(*) FROM pending_deposits").fetchone()
        return int(row[0] or 0)
    finally:
        conn.close()


def _manual_deposit_status(deposit_id: int) -> str:
    conn = bot.db_connect()
    try:
        row = conn.execute("SELECT status FROM pending_deposits WHERE id=?", (int(deposit_id),)).fetchone()
        return str(row[0] or "") if row else ""
    finally:
        conn.close()


def _seed_auto_order(
    user_id: str,
    order_code: str,
    amount: int,
    created_at: datetime,
    status: str = bot.PAYOS_STATUS_PENDING,
) -> None:
    xu = max(1, int(amount) // 100)
    bot.create_order(
        order_code,
        user_id,
        int(amount),
        xu,
        base_xu=xu,
        launch_bonus_xu=0,
        package_amount_vnd=int(amount),
        metadata_json=bot.payos_auto_topup_order_metadata("seed", int(amount), xu, 0, xu),
    )
    conn = bot.db_connect()
    try:
        conn.execute(
            """UPDATE payos_orders
               SET status=?, created_at=?, checkout_url=?, payment_link_id=?
               WHERE order_code=?""",
            (
                status,
                bot._payos_datetime_text(created_at),
                f"https://pay.example/{order_code}",
                f"plink-{order_code}",
                order_code,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_many(user_id: str, amount: int, minute_offsets: list[int]) -> None:
    for index, offset in enumerate(minute_offsets, start=1):
        _seed_auto_order(user_id, f"{user_id}-{index:03d}", amount, BASE_TIME - timedelta(minutes=offset))


class FakeQuery:
    def __init__(self, uid: int, data: str):
        self.data = data
        self.from_user = SimpleNamespace(id=uid, first_name="Customer", username="customer")
        self.message = SimpleNamespace(chat_id=uid)
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class FakeBot:
    async def send_photo(self, **_kwargs):
        raise AssertionError("blocked auto top-up must not send manual QR")


async def _payos_api_must_not_be_called(_body, **_kwargs):
    raise AssertionError("blocked auto top-up must not call PayOS API")


def _blocked_callback_context(uid: int, pkg_key: str):
    query = FakeQuery(uid, f"payos_pkg|{pkg_key}|{uid}")
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(bot=FakeBot())
    return update, context, query


def test_payos_auto_order_max_500k_allowed(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)

    result = bot.payos_auto_topup_guard("auto-max-ok", 500_000, "VND", BASE_TIME)

    assert result["ok"] is True
    assert bot.PAYOS_AUTO_TOPUP_MAX_VND == 500_000


def test_payos_auto_order_rejects_above_500k(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)

    result = bot.payos_auto_topup_guard("auto-max-block", 500_001, "VND", BASE_TIME)

    assert result["ok"] is False
    assert result["reason"] == "amount_cap_vnd"
    assert "500.000" in result["message"]


def test_payos_auto_order_above_500k_does_not_call_payos_api_or_credit(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    uid = 170201
    before = _credits(str(uid))
    packages = dict(bot.PAYMENT_PACKAGES)
    packages["600k"] = {"amount": 600_000, "xu": 6000, "text": "600k = 6000 Xu"}
    monkeypatch.setattr(bot, "PAYMENT_PACKAGES", packages)
    monkeypatch.setattr(bot, "create_payos_payment_request", _payos_api_must_not_be_called)
    update, context, query = _blocked_callback_context(uid, "600k")

    asyncio.run(bot.handle_package_choice(update, context))

    assert _credits(str(uid)) == before
    assert _order_count() == 0
    assert query.edits
    assert "500.000" in query.edits[0][0]


def test_payos_auto_cooldown_blocks_second_order(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    _seed_auto_order("cooldown-user", "cooldown-001", 10_000, BASE_TIME - timedelta(minutes=2))

    result = bot.payos_auto_topup_guard("cooldown-user", 10_000, "VND", BASE_TIME)

    assert result["ok"] is False
    assert result["reason"] == "cooldown_5m"


def test_payos_auto_cooldown_does_not_call_payos_api_or_create_second_order(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    uid = 170202
    _seed_auto_order(str(uid), "cooldown-callback-001", 10_000, datetime.now() - timedelta(minutes=2))
    before_count = _order_count()
    before_credits = _credits(str(uid))
    monkeypatch.setattr(bot, "create_payos_payment_request", _payos_api_must_not_be_called)
    update, context, query = _blocked_callback_context(uid, "10k")

    asyncio.run(bot.handle_package_choice(update, context))

    assert _order_count() == before_count
    assert _credits(str(uid)) == before_credits
    assert query.edits


def test_payos_auto_cooldown_allows_after_5_minutes(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    _seed_auto_order("cooldown-expired", "cooldown-expired-001", 10_000, BASE_TIME - timedelta(minutes=6))

    result = bot.payos_auto_topup_guard("cooldown-expired", 10_000, "VND", BASE_TIME)

    assert result["ok"] is True


def test_payos_auto_limit_3m_per_60m_locks_1h(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    _seed_many("limit-60m", 500_000, [10, 15, 20, 25, 30, 35])

    result = bot.payos_auto_topup_guard("limit-60m", 10_000, "VND", BASE_TIME)

    assert result["ok"] is False
    assert result["reason"] == "limit_3m_60m"
    assert result["lock"]["review_required"] is False
    assert result["lock"]["locked_until"]


def test_payos_auto_limit_3m_lock_blocks_new_order(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    bot.create_payos_auto_topup_lock("lock-60m", "limit_3m_60m", {}, duration_seconds=3600, now_dt=BASE_TIME)

    result = bot.payos_auto_topup_guard("lock-60m", 10_000, "VND", BASE_TIME + timedelta(minutes=10))

    assert result["ok"] is False
    assert result["reason"] == "auto_topup_locked"


def test_payos_auto_limit_3m_lock_auto_expires_after_1h(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    bot.create_payos_auto_topup_lock("lock-expire", "limit_3m_60m", {}, duration_seconds=3600, now_dt=BASE_TIME)

    result = bot.payos_auto_topup_guard("lock-expire", 10_000, "VND", BASE_TIME + timedelta(minutes=61))

    assert result["ok"] is True


def test_payos_auto_limit_9m_per_12h_locks_review(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    _seed_many("limit-12h", 500_000, [120 + index * 30 for index in range(18)])

    result = bot.payos_auto_topup_guard("limit-12h", 10_000, "VND", BASE_TIME)

    assert result["ok"] is False
    assert result["reason"] == "limit_9m_12h"
    assert result["lock"]["review_required"] is True


def test_payos_auto_limit_15m_per_24h_locks_review(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    _seed_many("limit-24h", 500_000, [13 * 60 + index * 20 for index in range(30)])

    result = bot.payos_auto_topup_guard("limit-24h", 10_000, "VND", BASE_TIME)

    assert result["ok"] is False
    assert result["reason"] == "limit_15m_24h"
    assert result["lock"]["review_required"] is True


def test_payos_auto_review_lock_does_not_auto_expire(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    bot.create_payos_auto_topup_lock("review-lock", "limit_9m_12h", {}, review_required=True, now_dt=BASE_TIME)

    result = bot.payos_auto_topup_guard("review-lock", 10_000, "VND", BASE_TIME + timedelta(days=2))

    assert result["ok"] is False
    assert result["reason"] == "auto_topup_locked"


def test_payos_auto_rolling_limit_does_not_call_payos_api(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    uid = 170203
    _seed_many(str(uid), 500_000, [10, 15, 20, 25, 30, 35])
    before_count = _order_count()
    before_credits = _credits(str(uid))
    monkeypatch.setattr(bot, "create_payos_payment_request", _payos_api_must_not_be_called)
    update, context, query = _blocked_callback_context(uid, "10k")

    asyncio.run(bot.handle_package_choice(update, context))

    assert _order_count() == before_count
    assert _credits(str(uid)) == before_credits
    assert query.edits


def test_manual_topup_large_amount_allowed_while_auto_locked_but_pending_only(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    user = SimpleNamespace(id="manual-large", first_name="Manual Large")
    before = _credits("manual-large")
    bot.create_payos_auto_topup_lock("manual-large", "limit_15m_24h", {}, review_required=True, now_dt=BASE_TIME)

    result = bot.create_manual_pending_deposit(
        user,
        {
            "currency": "VND",
            "method": "bank_acb",
            "amount": 5_000_000,
            "amount_vnd": 5_000_000,
            "base_xu": 50_000,
            "expected_xu": 50_000,
            "xu": 50_000,
            "transfer_content": "AAS manual-large MANUAL",
        },
        tx_hash="manual-large-c2",
    )

    assert result["ok"] is True
    assert _manual_deposit_status(result["id"]) == "pending_admin_review"
    assert _manual_deposit_count() == 1
    assert _credits("manual-large") == before


def test_usd_is_manual_only_and_manual_usd_does_not_auto_credit(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    assert all(str(package.get("currency", "VND")).upper() != "USD" for package in bot.PAYMENT_PACKAGES.values())
    user = SimpleNamespace(id="manual-usd", first_name="Manual USD")
    before = _credits("manual-usd")
    preview = bot.foreign_topup_preview("USD", 120, "usdt_trc20")
    result = bot.create_manual_pending_deposit(user, preview, tx_hash="manual-usd-c2")

    assert result["ok"] is True
    assert result["foreign_manual"] is True
    assert _manual_deposit_status(result["id"]) == "pending_admin_review"
    assert _credits("manual-usd") == before


def test_payos_usd_auto_cap_helper_exists_if_usd_auto_is_added(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)

    result = bot.payos_auto_topup_guard("usd-auto", 101, "USD", BASE_TIME)

    assert result["ok"] is False
    assert result["reason"] == "amount_cap_usd"
    assert bot.PAYOS_AUTO_TOPUP_MAX_USD == 100


def test_public_topup_rules_text_documents_limits_and_manual_review():
    auto_text = bot.payos_auto_topup_rules_text()
    manual_text = bot.manual_topup_rules_text()
    menu_text = bot.manual_payment_menu_text()

    assert "500.000" in auto_text
    assert "3.000.000" in auto_text
    assert "15.000.000" in auto_text
    assert "USD/CNY" in manual_text
    assert "Không cộng Xu tự động" in manual_text
    assert "Không cộng Xu tự động" in menu_text
    assert "PAYOS_CLIENT_ID" not in auto_text + manual_text + menu_text
    assert "Traceback" not in auto_text + manual_text + menu_text


def test_payos_limit_event_logged(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    _seed_many("event-log", 500_000, [10, 15, 20, 25, 30, 35])

    result = bot.payos_auto_topup_guard("event-log", 10_000, "VND", BASE_TIME)

    assert result["reason"] == "limit_3m_60m"
    conn = bot.db_connect()
    try:
        rows = conn.execute(
            "SELECT event_type, user_id, severity FROM security_events WHERE event_type=? AND user_id=?",
            ("payos_auto_topup_limit", "event-log"),
        ).fetchall()
    finally:
        conn.close()
    assert rows
    assert rows[-1] == ("payos_auto_topup_limit", "event-log", "medium")


def test_payos_auto_topup_orders_exclude_manual_orders_from_rolling_limits(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    user_id = "manual-filter"
    for index in range(20):
        bot.create_order(
            f"manual-filter-{index:03d}",
            user_id,
            500_000,
            5000,
            order_type="manual_topup",
            metadata_json=bot.payos_manual_topup_order_metadata("manual_bank_acb_vnd", "VND"),
        )
    result = bot.payos_auto_topup_guard(user_id, 10_000, "VND", BASE_TIME)

    assert result["ok"] is True


def test_p0_17c2_static_guard_no_unrelated_files_touched():
    repo = Path(bot.__file__).resolve().parent
    result = subprocess.run(["git", "diff", "--name-only", "origin/main"], cwd=repo, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    changed = {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}
    allowed = {
        "bot.py",
        "docs/reports/P0_17C2_PAYOS_AUTO_TOPUP_LIMITS.md",
        "tests/test_p0_4_hard_reset_audio_video_flow.py",
        "tests/test_p0_5_audio_video_addon_button_logic.py",
        "tests/test_p0_17c1_payos_signature_idempotency.py",
        "tests/test_p0_17c2_payos_auto_topup_limits.py",
    }
    assert changed <= allowed
