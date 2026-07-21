import json
import os
import tempfile

import bot


def _fresh_db(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    bot.init_db()
    return db_path


def test_p0_21c_public_monthly_package_prices_use_nice_8_tail(monkeypatch):
    db_path = _fresh_db(monkeypatch)
    try:
        catalog = bot.package_catalog_payload()
        public_monthly = {
            code: entry
            for code, entry in catalog["monthly"].items()
            if entry.get("public") is not False
        }
        public_combos = {
            code: entry
            for code, entry in catalog["combos"].items()
            if entry.get("public") is not False
        }
        assert "starter_monthly" in public_monthly
        assert catalog["monthly"]["starter_monthly"]["public"] is True
        assert public_monthly
        assert public_combos
        for code, entry in list(public_monthly.items()) + list(public_combos.items()):
            price = int(entry["price_vnd"])
            if price <= 0:
                assert entry.get("manual") is True, code
                continue
            assert price > 0
            assert price % 10000 == 8000
            assert int(entry.get("max_per_month") or 0) == 1
            assert entry.get("rank_points") is False
    finally:
        os.remove(db_path)


def test_p0_21c_group_discounts_increase_for_larger_monthly_packages(monkeypatch):
    db_path = _fresh_db(monkeypatch)
    try:
        catalog = bot.package_catalog_payload()["monthly"]
        codes = [
            "starter_monthly",
            "creator_monthly",
            "shop_monthly",
            "pro_monthly",
            "small_business_monthly",
        ]
        discounts = [int(catalog[code]["discount_percent"]) for code in codes]
        assert discounts == sorted(discounts)
        assert discounts[-1] > discounts[0]
    finally:
        os.remove(db_path)


def test_p0_21c_public_auto_checkout_only_for_ready_payos_packages(monkeypatch):
    db_path = _fresh_db(monkeypatch)
    try:
        auto_entry = bot.package_catalog_entry("starter_monthly", "monthly")
        manual_entry = bot.package_catalog_entry("combo_song_visual_888k", "combo")
        assert bot.package_entry_auto_checkout_enabled(auto_entry) is True
        assert bot.package_entry_auto_checkout_enabled(manual_entry) is False
        auto_detail = "\n".join(bot.package_purchase_detail_lines("monthly", "starter_monthly"))
        manual_detail = "\n".join(bot.package_purchase_detail_lines("combo", "combo_song_visual_888k"))
        assert "PayOS" in auto_detail
        assert "chưa mở checkout tự động" in manual_detail
        assert "Bot chưa tạo đơn" in manual_detail
    finally:
        os.remove(db_path)


def test_p0_21c_same_package_only_once_per_month(monkeypatch):
    db_path = _fresh_db(monkeypatch)
    try:
        user_id = "p0_21c_user"
        bot.get_user(user_id, "Package User")
        granted = bot.grant_user_package(user_id, "combo_ad_video_588k", "combo", "admin", 0, "pytest")
        assert granted["ok"] is True
        assert bot.user_bought_package_this_month(user_id, "combo_ad_video_588k", "combo") is True
        assert "1 lần/tháng" in bot.package_same_month_guard_text()
        assert "admin" in bot.package_same_month_guard_text()
    finally:
        os.remove(db_path)


def test_p0_21c_package_payos_amount_mismatch_flags_admin_review(monkeypatch):
    db_path = _fresh_db(monkeypatch)
    try:
        user_id = "p0_21c_mismatch"
        order_code = "210300001"
        metadata = {
            "type": "package_purchase",
            "payment_type": "combo_purchase",
            "package_type": "combo",
            "package_code": "combo_ad_video_588k",
            "package_label": "Combo Video Quảng Cáo",
        }
        bot.create_order(
            order_code,
            user_id,
            588000,
            0,
            order_type="package_purchase",
            plan_id="combo_ad_video_588k",
            plan_name="Combo Video Quảng Cáo",
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        )
        processed, desc, info = bot.process_payos_paid_order(order_code, 123000, webhook_currency="VND")
        assert processed is False
        assert desc == "package_order_flagged"
        assert info["flagged"] is True
        conn = bot.db_connect()
        try:
            row = conn.execute("SELECT status, metadata_json FROM payos_orders WHERE order_code=?", (order_code,)).fetchone()
            assert row[0] == bot.PAYOS_STATUS_PENDING_ADMIN_REVIEW
            saved_meta = json.loads(row[1])
            assert saved_meta["package_admin_reason"] == "amount_mismatch"
            assert conn.execute("SELECT COUNT(*) FROM user_packages WHERE user_id=?", (user_id,)).fetchone()[0] == 0
        finally:
            conn.close()
    finally:
        os.remove(db_path)


def test_p0_21c_admin_can_approve_flagged_package_after_review(monkeypatch):
    db_path = _fresh_db(monkeypatch)
    try:
        user_id = "p0_21c_approve"
        order_code = "210300002"
        metadata = {
            "type": "package_purchase",
            "payment_type": "combo_purchase",
            "package_type": "combo",
            "package_code": "combo_ad_video_588k",
        }
        bot.create_order(
            order_code,
            user_id,
            588000,
            0,
            order_type="package_purchase",
            plan_id="combo_ad_video_588k",
            plan_name="Combo Video Quảng Cáo",
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        )
        conn = bot.db_connect()
        try:
            bot.flag_package_order_for_admin_conn(conn, order_code, metadata, "manual_paid_admin_review", paid_amount_vnd=588000)
            conn.commit()
        finally:
            conn.close()
        result = bot.admin_approve_package_order(order_code, "admin")
        assert result["ok"] is True
        assert bot.active_package_item_for_user(user_id, "video_standard") is not None
    finally:
        os.remove(db_path)


def test_p0_21c_need_larger_creates_admin_order_request(monkeypatch):
    db_path = _fresh_db(monkeypatch)
    try:
        request = bot.create_package_order_request(
            "need_larger_user",
            username="buyer",
            source="pytest",
            package_type="combo",
            package_code="combo_small_business_2888k",
            need_text="need bigger monthly volume",
        )
        assert request["ok"] is True
        text = bot.package_order_request_text(request)
        assert "Order riêng" in text
        assert str(request["request_id"]) in text
        admin_text = bot.admin_package_orders_text()
        assert "need_larger_user" in admin_text
        assert "combo_small_business_2888k" in admin_text
    finally:
        os.remove(db_path)


def test_p0_21c_commands_registered_and_no_engine_provider_checkout(monkeypatch):
    db_path = _fresh_db(monkeypatch)
    try:
        source = open("bot.py", encoding="utf-8").read()
        assert 'CommandHandler("package_orders", cmd_package_orders)' in source
        assert 'CommandHandler("package_order_approve", cmd_package_order_approve)' in source
        assert 'CommandHandler("package_order_reject", cmd_package_order_reject)' in source
        checkout_source = source[source.index("async def start_package_purchase"):source.index("async def start_plan_purchase")]
        assert "create_payos_payment_request" in checkout_source
        assert "AgentGemini" not in checkout_source
        assert "create_shopaikey_job" not in checkout_source
        assert "charge_user_credit" not in checkout_source
    finally:
        os.remove(db_path)
