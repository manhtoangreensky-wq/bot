import hashlib
import hmac
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

import bot


PAYOS_TEST_CHECKSUM_KEY = "checksum-test-c1"


def _sign(data: dict, key: str = PAYOS_TEST_CHECKSUM_KEY) -> str:
    raw = "&".join(f"{k}={data[k]}" for k in sorted(data.keys()))
    return hmac.new(key.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()


def _webhook_data(
    order_code: str,
    amount: int = 10000,
    status: str | None = bot.PAYOS_STATUS_PAID,
    payment_link_id: str = "plink-c1",
    transaction_id: str = "tx-c1",
    currency: str = "VND",
) -> dict:
    data = {
        "orderCode": order_code,
        "amount": amount,
        "currency": currency,
        "paymentLinkId": payment_link_id,
        "reference": transaction_id,
    }
    if status is not None:
        data["status"] = status
    return data


def _post_payos(client: TestClient, data: dict, signature: str | None = None, success: bool = True):
    payload = {"success": success, "data": data}
    if signature is not None:
        payload["signature"] = signature
    return client.post("/webhook/payos", json=payload)


def _create_order(user_id: str, order_code: str, amount: int = 10000, xu: int = 100, payment_link_id: str = "") -> int:
    before_credits, _, _ = bot.get_user(user_id, f"user-{user_id}")
    bot.create_order(order_code, user_id, amount, xu)
    if payment_link_id:
        conn = bot.db_connect()
        try:
            conn.execute("UPDATE payos_orders SET payment_link_id=? WHERE order_code=?", (payment_link_id, order_code))
            conn.commit()
        finally:
            conn.close()
    return int(before_credits or 0)


def _credits(user_id: str) -> int:
    credits, _, _ = bot.get_user(user_id)
    return int(credits or 0)


def _order_status(order_code: str) -> str:
    conn = bot.db_connect()
    try:
        row = conn.execute("SELECT status FROM payos_orders WHERE order_code=?", (order_code,)).fetchone()
    finally:
        conn.close()
    return str(row[0] if row else "")


def _event_row(order_code: str):
    conn = bot.db_connect()
    try:
        return conn.execute(
            """SELECT event_key, order_code, payment_link_id, transaction_id, credited
               FROM payos_processed_events WHERE order_code=?""",
            (order_code,),
        ).fetchone()
    finally:
        conn.close()


def test_payos_webhook_rejects_missing_signature(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "missing-signature.db"))
    monkeypatch.setattr(bot, "PAYOS_CHECKSUM_KEY", PAYOS_TEST_CHECKSUM_KEY)
    monkeypatch.setattr(bot, "tg_app", None)
    bot.init_db()
    before = _create_order("payos-missing-sig", "171001", payment_link_id="plink-missing")

    client = TestClient(bot.fastapi_app)
    response = _post_payos(client, _webhook_data("171001", payment_link_id="plink-missing"), signature=None)

    assert response.status_code == 400
    assert _credits("payos-missing-sig") == before
    assert _order_status("171001") == bot.PAYOS_STATUS_PENDING


def test_payos_webhook_rejects_invalid_signature(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "invalid-signature.db"))
    monkeypatch.setattr(bot, "PAYOS_CHECKSUM_KEY", PAYOS_TEST_CHECKSUM_KEY)
    monkeypatch.setattr(bot, "tg_app", None)
    bot.init_db()
    before = _create_order("payos-invalid-sig", "171002", payment_link_id="plink-invalid")

    client = TestClient(bot.fastapi_app)
    response = _post_payos(client, _webhook_data("171002", payment_link_id="plink-invalid"), signature="bad")

    assert response.status_code == 400
    assert _credits("payos-invalid-sig") == before
    assert _order_status("171002") == bot.PAYOS_STATUS_PENDING


def test_payos_webhook_credits_only_after_valid_signature(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "valid-signature.db"))
    monkeypatch.setattr(bot, "PAYOS_CHECKSUM_KEY", PAYOS_TEST_CHECKSUM_KEY)
    monkeypatch.setattr(bot, "tg_app", None)
    bot.init_db()
    before = _create_order("payos-valid-sig", "171003", payment_link_id="plink-valid")
    data = _webhook_data("171003", payment_link_id="plink-valid", transaction_id="tx-valid")
    client = TestClient(bot.fastapi_app)

    invalid_response = _post_payos(client, data, signature="bad")
    assert invalid_response.status_code == 400
    assert _credits("payos-valid-sig") == before

    valid_response = _post_payos(client, data, signature=_sign(data))
    assert valid_response.status_code == 200
    assert valid_response.json()["desc"] == "success"
    assert _credits("payos-valid-sig") == before + 100
    assert _order_status("171003") == bot.PAYOS_STATUS_PAID


def test_payos_webhook_duplicate_does_not_credit_twice(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "duplicate.db"))
    monkeypatch.setattr(bot, "PAYOS_CHECKSUM_KEY", PAYOS_TEST_CHECKSUM_KEY)
    monkeypatch.setattr(bot, "tg_app", None)
    bot.init_db()
    before = _create_order("payos-duplicate", "171004", payment_link_id="plink-duplicate")
    data = _webhook_data("171004", payment_link_id="plink-duplicate", transaction_id="tx-duplicate")
    client = TestClient(bot.fastapi_app)

    first = _post_payos(client, data, signature=_sign(data))
    after_first = _credits("payos-duplicate")
    second = _post_payos(client, data, signature=_sign(data))

    assert first.status_code == 200
    assert first.json()["desc"] == "success"
    assert second.status_code == 200
    assert second.json()["desc"] == "already_paid"
    assert after_first == before + 100
    assert _credits("payos-duplicate") == after_first
    assert _event_row("171004") == ("transaction:tx-duplicate", "171004", "plink-duplicate", "tx-duplicate", 1)


def test_payos_webhook_invalid_amount_does_not_credit(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "amount-mismatch.db"))
    monkeypatch.setattr(bot, "PAYOS_CHECKSUM_KEY", PAYOS_TEST_CHECKSUM_KEY)
    monkeypatch.setattr(bot, "tg_app", None)
    bot.init_db()
    before = _create_order("payos-amount", "171005", amount=10000, xu=100, payment_link_id="plink-amount")
    data = _webhook_data("171005", amount=20000, payment_link_id="plink-amount", transaction_id="tx-amount")
    client = TestClient(bot.fastapi_app)

    response = _post_payos(client, data, signature=_sign(data))

    assert response.status_code == 200
    assert response.json()["desc"] == "amount_mismatch"
    assert _credits("payos-amount") == before
    assert _order_status("171005") == bot.PAYOS_STATUS_PENDING_ADMIN_REVIEW


def test_payos_webhook_currency_mismatch_does_not_credit(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "currency-mismatch.db"))
    monkeypatch.setattr(bot, "PAYOS_CHECKSUM_KEY", PAYOS_TEST_CHECKSUM_KEY)
    monkeypatch.setattr(bot, "tg_app", None)
    bot.init_db()
    before = _create_order("payos-currency", "171011", amount=10000, xu=100, payment_link_id="plink-currency")
    data = _webhook_data("171011", payment_link_id="plink-currency", transaction_id="tx-currency", currency="USD")
    client = TestClient(bot.fastapi_app)

    response = _post_payos(client, data, signature=_sign(data))

    assert response.status_code == 200
    assert response.json()["desc"] == "currency_mismatch"
    assert _credits("payos-currency") == before
    assert _order_status("171011") == bot.PAYOS_STATUS_PENDING_ADMIN_REVIEW


def test_payos_webhook_pending_or_cancelled_does_not_credit(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "non-paid-status.db"))
    monkeypatch.setattr(bot, "PAYOS_CHECKSUM_KEY", PAYOS_TEST_CHECKSUM_KEY)
    monkeypatch.setattr(bot, "tg_app", None)
    bot.init_db()
    client = TestClient(bot.fastapi_app)

    for index, status in enumerate([bot.PAYOS_STATUS_PENDING, bot.PAYOS_STATUS_CANCELLED, "FAILED", "UNKNOWN", None], start=1):
        order_code = f"17110{index}"
        user_id = f"payos-status-{index}"
        before = _create_order(user_id, order_code, payment_link_id=f"plink-status-{index}")
        data = _webhook_data(
            order_code,
            status=status,
            payment_link_id=f"plink-status-{index}",
            transaction_id=f"tx-status-{index}",
        )
        response = _post_payos(client, data, signature=_sign(data), success=True)

        assert response.status_code == 200
        assert response.json()["desc"] == "status_not_paid"
        assert _credits(user_id) == before
        assert _order_status(order_code) == bot.PAYOS_STATUS_PENDING


def test_payos_webhook_no_fake_success(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "fake-success.db"))
    monkeypatch.setattr(bot, "PAYOS_CHECKSUM_KEY", PAYOS_TEST_CHECKSUM_KEY)
    monkeypatch.setattr(bot, "tg_app", None)
    bot.init_db()
    before = _create_order("payos-fake-success", "171006", payment_link_id="plink-fake")
    data = _webhook_data("171006", status=bot.PAYOS_STATUS_PENDING, payment_link_id="plink-fake", transaction_id="tx-fake")
    client = TestClient(bot.fastapi_app)

    response = _post_payos(client, data, signature=_sign(data), success=True)

    assert response.status_code == 200
    assert response.json()["desc"] == "status_not_paid"
    assert _credits("payos-fake-success") == before
    assert _order_status("171006") == bot.PAYOS_STATUS_PENDING


def test_payos_webhook_order_not_found_does_not_credit(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "order-not-found.db"))
    monkeypatch.setattr(bot, "PAYOS_CHECKSUM_KEY", PAYOS_TEST_CHECKSUM_KEY)
    monkeypatch.setattr(bot, "tg_app", None)
    bot.init_db()
    data = _webhook_data("179999", payment_link_id="plink-missing-order", transaction_id="tx-missing-order")
    client = TestClient(bot.fastapi_app)

    response = _post_payos(client, data, signature=_sign(data))

    assert response.status_code == 200
    assert response.json()["desc"] == "order_not_found"
    assert _event_row("179999") is None


def test_payos_webhook_same_transaction_different_order_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "transaction-conflict.db"))
    monkeypatch.setattr(bot, "PAYOS_CHECKSUM_KEY", PAYOS_TEST_CHECKSUM_KEY)
    monkeypatch.setattr(bot, "tg_app", None)
    bot.init_db()
    client = TestClient(bot.fastapi_app)
    first_before = _create_order("payos-tx-first", "171007", payment_link_id="plink-tx-first")
    second_before = _create_order("payos-tx-second", "171008", payment_link_id="plink-tx-second")
    first_data = _webhook_data("171007", payment_link_id="plink-tx-first", transaction_id="tx-conflict")
    second_data = _webhook_data("171008", payment_link_id="plink-tx-second", transaction_id="tx-conflict")

    first = _post_payos(client, first_data, signature=_sign(first_data))
    second = _post_payos(client, second_data, signature=_sign(second_data))

    assert first.status_code == 200
    assert first.json()["desc"] == "success"
    assert second.status_code == 200
    assert second.json()["desc"] == "transaction_conflict"
    assert _credits("payos-tx-first") == first_before + 100
    assert _credits("payos-tx-second") == second_before
    assert _order_status("171008") == bot.PAYOS_STATUS_PENDING


def test_payos_webhook_duplicate_payment_link_does_not_credit_twice(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "payment-link-conflict.db"))
    monkeypatch.setattr(bot, "PAYOS_CHECKSUM_KEY", PAYOS_TEST_CHECKSUM_KEY)
    monkeypatch.setattr(bot, "tg_app", None)
    bot.init_db()
    client = TestClient(bot.fastapi_app)
    first_before = _create_order("payos-link-first", "171009", payment_link_id="plink-conflict")
    second_before = _create_order("payos-link-second", "171010", payment_link_id="plink-conflict")
    first_data = _webhook_data("171009", payment_link_id="plink-conflict", transaction_id="tx-link-first")
    second_data = _webhook_data("171010", payment_link_id="plink-conflict", transaction_id="tx-link-second")

    first = _post_payos(client, first_data, signature=_sign(first_data))
    second = _post_payos(client, second_data, signature=_sign(second_data))

    assert first.status_code == 200
    assert first.json()["desc"] == "success"
    assert second.status_code == 200
    assert second.json()["desc"] == "payment_link_conflict"
    assert _credits("payos-link-first") == first_before + 100
    assert _credits("payos-link-second") == second_before
    assert _order_status("171010") == bot.PAYOS_STATUS_PENDING


def test_p0_17c1_static_guard_no_unrelated_files_touched():
    repo = Path(bot.__file__).resolve().parent
    result = subprocess.run(["git", "diff", "--name-only", "origin/main"], cwd=repo, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    changed = {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}
    allowed = {
        "bot.py",
        "services/aas_shared_knowledge.py",
        "services/ai_chatbot_copilot.py",
        "services/telegram_business_support.py",
        "docs/reports/P0_17C1_PAYOS_SIGNATURE_IDEMPOTENCY.md",
        "docs/reports/P0_17C2_PAYOS_AUTO_TOPUP_LIMITS.md",
        "docs/reports/P0_17C3_PAYOS_ADMIN_RISK_LOCK_REVIEW.md",
        "docs/reports/P0_17C4_WEBHOOK_DB_HTML_SECURITY_EVENTS.md",
        "tests/test_core.py",
        "tests/test_p0_17a1_admin_control_center_handbook.py",
        "tests/test_p0_4_hard_reset_audio_video_flow.py",
        "tests/test_p0_5_audio_video_addon_button_logic.py",
        "tests/test_p0_17c1_payos_signature_idempotency.py",
        "tests/test_p0_17c2_payos_auto_topup_limits.py",
        "tests/test_p0_17c3_payos_admin_risk_lock_review.py",
        "tests/test_p0_17c4_webhook_db_html_security_events.py",
        "tests/test_p0_aichat1_copilot_consent.py",
        "tests/test_p0_aichat1b_free_tools_menu_cleanup.py",
        "tests/test_p0_aichat2_natural_context_pricing.py",
        "tests/test_p0_aichat4_smart_intent_context_backstack.py",
        "tests/test_p0_aichat5_live_context_action_trace.py",
        "tests/test_p0_aichat6_open_public_live_flows.py",
        "tests/test_p0_image_live1_public_image_generation.py",
        "tests/test_p0_cskh1_telegram_business_auto_support_bot.py",
        "tests/test_p0_cskh5b_live_business_followup_pricing_runtime.py",
        "tests/test_p0_cskh5c_business_self_echo_duplicate_guard.py",
        "tests/test_p0_cskh6_human_touch_playbook_safe_training_pack.py",
        "tests/test_p0_cskh_aichat3_context_brain_retrieval.py",
        "services/video_idea_catalog.py",
        "services/video_idea_script_intake.py",
        "services/video_idea_store.py",
        "tests/test_p0_video_idea2_dynamic_presets_admin_script_intake.py",
        "tests/test_p0_video_knowledge1_profile_router_and_studio_menu.py",
        "tests/test_p0_video_scene3ux3_unified_video_idea_hub.py",
        "tests/test_p0_video_scene3ux4_reference_only_idea_hub.py",
        "tests/test_p0_17b7_1_video_menu_cleanup.py",
        "tests/test_p0_18f_video_menu_route_audit_fix_only.py",
    }
    assert changed <= allowed
