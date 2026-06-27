import asyncio
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import bot


BASE_TIME = datetime(2026, 6, 27, 12, 0, 0)


def _init_db(monkeypatch, tmp_path, name="p0_17c3.db"):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / name))
    bot.USER_BILL_STATE.clear()
    bot.init_db()


def _credits(user_id: str) -> int:
    credits, _, _ = bot.get_user(user_id, f"user-{user_id}")
    return int(credits or 0)


def _order_status(order_code: str) -> str:
    conn = bot.db_connect()
    try:
        row = conn.execute("SELECT status FROM payos_orders WHERE order_code=?", (order_code,)).fetchone()
        return str(row[0] or "") if row else ""
    finally:
        conn.close()


def _order_metadata(order_code: str) -> dict:
    conn = bot.db_connect()
    try:
        row = conn.execute("SELECT metadata_json FROM payos_orders WHERE order_code=?", (order_code,)).fetchone()
    finally:
        conn.close()
    return json.loads(row[0] or "{}") if row else {}


def _audit_actions(action: str) -> list[tuple]:
    conn = bot.db_connect()
    try:
        return conn.execute(
            "SELECT actor_id,action,object_type,object_id,note FROM audit_logs WHERE action=? ORDER BY id",
            (action,),
        ).fetchall()
    finally:
        conn.close()


def _seed_auto_order(
    user_id: str,
    order_code: str,
    amount: int = 10_000,
    created_at: datetime | None = None,
    status: str = bot.PAYOS_STATUS_PENDING,
) -> None:
    created_at = created_at or datetime.now()
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
            (status, bot._payos_datetime_text(created_at), f"https://pay.example/{order_code}", f"plink-{order_code}", order_code),
        )
        conn.commit()
    finally:
        conn.close()


def _keyboard_labels(markup) -> list[list[str]]:
    return [[button.text for button in row] for row in markup.inline_keyboard]


class FakeQuery:
    def __init__(self, uid: int, data: str):
        self.data = data
        self.from_user = SimpleNamespace(id=uid, username="user", first_name="User")
        self.message = SimpleNamespace(chat_id=uid)
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


def test_admin_risk_menu_visible_to_admin():
    rows = _keyboard_labels(bot.menu_nav_keyboard("admin", True))
    assert ["💰 Tài chính", "🧊 Freeze / Queue"] in rows
    assert ["🛡 Rủi ro nạp tiền"] in rows


def test_admin_risk_menu_hidden_from_public():
    labels = [label for row in _keyboard_labels(bot.menu_nav_keyboard("admin", False)) for label in row]
    assert "🛡 Rủi ro nạp tiền" not in labels


def test_admin_risk_menu_vietnamese_copy():
    text = bot.payos_risk_menu_text()
    labels = [label for row in _keyboard_labels(bot.payos_risk_menu_keyboard()) for label in row]
    assert "Rủi ro nạp tiền PayOS" in text
    assert "Mở khóa review sau khi kiểm tra" in text
    assert "🔒 DS khóa review" in labels
    assert "📊 Báo cáo rủi ro" in labels


def test_admin_finance_freeze_queue_row_not_broken_if_touched():
    rows = _keyboard_labels(bot.menu_nav_keyboard("admin", True))
    assert rows.index(["💰 Tài chính", "🧊 Freeze / Queue"]) < rows.index(["🛡 Rủi ro nạp tiền"])


def test_public_cannot_open_payos_risk_menu(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    query = FakeQuery(12345, "payrisk|report")
    asyncio.run(bot.handle_payos_risk_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert query.answers[-1][1].get("show_alert") is True
    assert "Admin" in query.answers[-1][0][0]
    assert not query.edits


def test_public_cannot_unlock_user(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    query = FakeQuery(12345, "payrisk|unlockuser|target-user")
    asyncio.run(bot.handle_payos_risk_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert not query.edits


def test_public_cannot_block_user(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    message = FakeMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=12345), message=message)
    asyncio.run(bot.cmd_payos_risk_block(update, SimpleNamespace(args=["target-user"])))
    assert message.replies and "không có quyền" in message.replies[0][0]


def test_public_cannot_cancel_order(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    message = FakeMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=12345), message=message)
    asyncio.run(bot.cmd_payos_risk_cancel(update, SimpleNamespace(args=["C3001"])))
    assert message.replies and "không có quyền" in message.replies[0][0]


def test_public_cannot_view_risk_report(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    message = FakeMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=12345), message=message)
    asyncio.run(bot.cmd_payos_risk(update, SimpleNamespace(args=[])))
    assert message.replies and "không có quyền" in message.replies[0][0]


def test_admin_list_review_locks(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    bot.create_payos_auto_topup_lock("review-user", "limit_9m_12h", {"amount_12h": 9_000_000, "trigger_order_amount": 10_000}, review_required=True, now_dt=BASE_TIME)
    text = bot.payos_risk_lock_list_text(True)
    assert "review-user" in text
    assert "limit_9m_12h" in text


def test_admin_list_review_locks_shows_reason_amounts(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    bot.create_payos_auto_topup_lock("review-amount", "limit_15m_24h", {"amount_60m": 1_000_000, "amount_12h": 9_500_000, "amount_24h": 15_000_000}, review_required=True, now_dt=BASE_TIME)
    text = bot.payos_risk_lock_list_text(True)
    assert "limit_15m_24h" in text
    assert "1.000.000đ" in text
    assert "15.000.000đ" in text


def test_admin_list_review_locks_no_secret_payload(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    bot.create_payos_auto_topup_lock(
        "review-secret",
        "limit_9m_12h",
        {"checksum": "c3-secret-value", "signature": "c3-signature-value", "amount_12h": 9_000_000},
        review_required=True,
        now_dt=BASE_TIME,
    )
    text = bot.payos_risk_lock_list_text(True).lower()
    assert "c3-secret-value" not in text
    assert "c3-signature-value" not in text
    assert "checksum" in text


def test_admin_list_one_hour_locks(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    bot.create_payos_auto_topup_lock("hour-user", "limit_3m_60m", {"amount_60m": 3_000_000}, duration_seconds=3600, now_dt=datetime.now())
    text = bot.payos_risk_lock_list_text(False)
    assert "hour-user" in text
    assert "3.000.000đ" in text


def test_admin_unlock_one_hour_lock_early(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    lock = bot.create_payos_auto_topup_lock("hour-unlock", "limit_3m_60m", {}, duration_seconds=3600, now_dt=datetime.now())
    result = bot.payos_risk_resolve_lock("999", lock["id"], "checked")
    assert result["ok"] is True
    assert bot.active_payos_auto_topup_lock("hour-unlock") is None


def test_one_hour_lock_still_auto_expires_without_admin(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    bot.create_payos_auto_topup_lock("hour-expire", "limit_3m_60m", {}, duration_seconds=3600, now_dt=BASE_TIME)
    assert bot.active_payos_auto_topup_lock("hour-expire", BASE_TIME + timedelta(minutes=61)) is None


def test_admin_user_risk_detail_by_user_id(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    _seed_auto_order("detail-user", "C3D001", 500_000, BASE_TIME - timedelta(minutes=10))
    text = bot.payos_risk_user_detail_text("detail-user")
    assert "detail-user" in text
    assert "C3D001" in text


def test_admin_user_risk_detail_shows_active_lock(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    bot.payos_risk_manual_block_user("999", "detail-lock", "manual review")
    text = bot.payos_risk_user_detail_text("detail-lock")
    assert "manual_admin_block" in text


def test_admin_user_risk_detail_shows_rolling_sums(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    _seed_auto_order("detail-roll", "C3R001", 500_000, datetime.now() - timedelta(minutes=10))
    text = bot.payos_risk_user_detail_text("detail-roll")
    assert "500.000đ" in text
    assert "60m" in text and "12h" in text and "24h" in text


def test_admin_user_risk_detail_no_public_access(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    query = FakeQuery(12345, "payrisk|user|detail-roll")
    asyncio.run(bot.handle_payos_risk_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert not query.edits


def test_admin_manual_block_user_auto_topup(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    result = bot.payos_risk_manual_block_user("999", "blocked-user", "risk review")
    assert result["ok"] is True
    lock = bot.active_payos_auto_topup_lock("blocked-user")
    assert lock and lock["reason"] == "manual_admin_block"


def test_admin_manual_block_prevents_payos_auto_order(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    bot.payos_risk_manual_block_user("999", "blocked-auto", "risk review")
    result = bot.payos_auto_topup_guard("blocked-auto", 10_000, "VND", BASE_TIME)
    assert result["ok"] is False
    assert result["reason"] == "auto_topup_locked"
    assert "tạm khóa nạp tự động để kiểm tra" in result["message"]


def test_admin_manual_block_allows_manual_topup(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    bot.payos_risk_manual_block_user("999", "manual-allowed", "risk review")
    before = _credits("manual-allowed")
    result = bot.create_manual_pending_deposit(
        SimpleNamespace(id="manual-allowed", first_name="Manual"),
        {"currency": "VND", "method": "bank_acb", "amount": 2_000_000, "amount_vnd": 2_000_000, "base_xu": 20_000, "expected_xu": 20_000, "xu": 20_000},
        tx_hash="manual-allowed-c3",
    )
    assert result["ok"] is True
    assert _credits("manual-allowed") == before


def test_admin_unblock_review_lock(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    bot.payos_risk_manual_block_user("999", "unlock-review", "risk review")
    result = bot.payos_risk_unlock_user("999", "unlock-review", "checked ok")
    assert result["ok"] is True
    assert bot.active_payos_auto_topup_lock("unlock-review") is None


def test_admin_unblock_records_admin_id(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    bot.payos_risk_manual_block_user("999", "unlock-audit", "risk review")
    bot.payos_risk_unlock_user("888", "unlock-audit", "checked ok")
    conn = bot.db_connect()
    try:
        row = conn.execute("SELECT resolved_by,resolved_note FROM payos_topup_locks WHERE user_id=?", ("unlock-audit",)).fetchone()
    finally:
        conn.close()
    assert row == ("admin:888", "checked ok")
    assert _audit_actions("unlock_auto_topup")


def test_admin_cancel_pending_payos_order(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    _seed_auto_order("cancel-user", "C3C001", 10_000)
    result = bot.payos_risk_cancel_order("999", "C3C001", "risk")
    assert result["ok"] is True
    assert _order_status("C3C001") == bot.PAYOS_STATUS_CANCELLED


def test_admin_cancel_pending_order_blocks_later_credit(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    before = _credits("cancel-credit")
    _seed_auto_order("cancel-credit", "C3C002", 10_000)
    assert bot.payos_risk_cancel_order("999", "C3C002", "risk")["ok"] is True
    processed, desc, _info = bot.process_payos_paid_order("C3C002", 10_000, webhook_status=bot.PAYOS_STATUS_PAID)
    assert processed is False
    assert desc == "cancelled"
    assert _credits("cancel-credit") == before


def test_admin_cannot_cancel_already_credited_order(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    _seed_auto_order("paid-user", "C3P001", 10_000, status=bot.PAYOS_STATUS_PAID)
    result = bot.payos_risk_cancel_order("999", "C3P001", "risk")
    assert result["ok"] is False
    assert result["reason"] == "already_credited"


def test_admin_mark_order_suspicious(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    _seed_auto_order("mark-user", "C3M001", 10_000)
    result = bot.payos_risk_mark_order_suspicious("999", "C3M001", "needs review")
    assert result["ok"] is True
    assert _order_metadata("C3M001")["admin_risk_status"] == "suspicious"


def test_cancelled_order_later_paid_webhook_no_credit(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    before = _credits("cancel-webhook")
    _seed_auto_order("cancel-webhook", "C3C003", 10_000)
    bot.payos_risk_cancel_order("999", "C3C003", "risk")
    processed, _desc, _info = bot.process_payos_paid_order("C3C003", 10_000, webhook_status=bot.PAYOS_STATUS_PAID, transaction_id="tx-c3")
    assert processed is False
    assert _credits("cancel-webhook") == before


def test_admin_risk_report_counts_locks(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    bot.payos_risk_manual_block_user("999", "report-review", "risk")
    bot.create_payos_auto_topup_lock("report-hour", "limit_3m_60m", {}, duration_seconds=3600, now_dt=datetime.now())
    payload = bot.payos_risk_report_payload()
    assert payload["active_review_locks"] == 1
    assert payload["active_one_hour_locks"] == 1


def test_admin_risk_report_top_users(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    _seed_auto_order("top-user", "C3T001", 500_000, datetime.now() - timedelta(minutes=10))
    text = bot.payos_risk_report_text()
    assert "top-user" in text
    assert "500.000đ" in text


def test_admin_risk_report_no_secrets(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    bot.record_anomaly("payos_invalid_signature", "medium", "signature=secret checksum=super-secret", auto_lock=False)
    text = bot.payos_risk_report_text().lower()
    assert "super-secret" not in text
    assert "raw webhook payload" in text


def test_admin_risk_report_hidden_from_public(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    query = FakeQuery(12345, "payrisk|report")
    asyncio.run(bot.handle_payos_risk_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert not query.edits


def test_manual_topup_admin_review_copy():
    text = bot.manual_pending_admin_text({
        "id": 1,
        "user_id": "u",
        "username": "name",
        "method": "bank_acb",
        "currency": "VND",
        "amount_vnd": 100_000,
        "base_xu": 1000,
        "expected_xu": 1000,
        "submitted_at": "2026-06-27 12:00:00",
    })
    assert "Nạp thủ công không tự cộng Xu" in text
    assert "Chỉ duyệt sau khi xác nhận tiền đã vào" in text


def test_public_cannot_approve_manual_topup(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    query = FakeQuery(12345, "manual|approve_expected|1")
    asyncio.run(bot.handle_manual_package_choice(SimpleNamespace(callback_query=query), SimpleNamespace(args=[], bot=SimpleNamespace())))
    assert query.answers[-1][1].get("show_alert") is True


def test_admin_block_action_logged(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    bot.payos_risk_manual_block_user("999", "log-block", "risk")
    assert _audit_actions("manual_block_auto_topup")


def test_admin_unlock_action_logged(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    bot.payos_risk_manual_block_user("999", "log-unlock", "risk")
    bot.payos_risk_unlock_user("999", "log-unlock", "ok")
    assert _audit_actions("unlock_auto_topup")


def test_admin_cancel_order_action_logged(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    _seed_auto_order("log-cancel", "C3L001", 10_000)
    bot.payos_risk_cancel_order("999", "C3L001", "risk")
    assert _audit_actions("cancel_payos_order")


def test_admin_mark_suspicious_action_logged(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    _seed_auto_order("log-mark", "C3L002", 10_000)
    bot.payos_risk_mark_order_suspicious("999", "C3L002", "risk")
    assert _audit_actions("mark_payos_order_suspicious")


def test_public_copy_no_signature_checksum_webhook():
    text = "\n".join([
        bot.PAYOS_ADMIN_MANUAL_LOCK_MESSAGE,
        bot.payos_auto_topup_lock_message({"reason": "manual_admin_block"}),
    ]).lower()
    assert "signature" not in text
    assert "checksum" not in text
    assert "webhook" not in text


def test_public_copy_no_traceback():
    assert "traceback" not in bot.PAYOS_ADMIN_MANUAL_LOCK_MESSAGE.lower()


def test_public_copy_clean_locked_message():
    assert "Tài khoản đang tạm khóa nạp tự động để kiểm tra" in bot.PAYOS_ADMIN_MANUAL_LOCK_MESSAGE
    assert "nạp thủ công" in bot.PAYOS_ADMIN_MANUAL_LOCK_MESSAGE


def test_p0_17c3_command_handlers_registered():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert 'CommandHandler("payos_risk", cmd_payos_risk)' in source
    assert 'CallbackQueryHandler(handle_payos_risk_callback, pattern=r"^payrisk\\|")' in source


def test_p0_17c3_static_guard_no_unrelated_files_touched():
    repo = Path(bot.__file__).resolve().parent
    result = subprocess.run(["git", "diff", "--name-only", "origin/main"], cwd=repo, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    changed = {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}
    allowed = {
        "bot.py",
        "docs/reports/P0_17C3_PAYOS_ADMIN_RISK_LOCK_REVIEW.md",
        "docs/reports/P0_17C4_WEBHOOK_DB_HTML_SECURITY_EVENTS.md",
        "tests/test_p0_4_hard_reset_audio_video_flow.py",
        "tests/test_p0_5_audio_video_addon_button_logic.py",
        "tests/test_p0_17c1_payos_signature_idempotency.py",
        "tests/test_p0_17c2_payos_auto_topup_limits.py",
        "tests/test_p0_17c3_payos_admin_risk_lock_review.py",
        "tests/test_p0_17c4_webhook_db_html_security_events.py",
    }
    assert changed <= allowed
