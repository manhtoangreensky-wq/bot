import hmac
import hashlib
import os
import tempfile

from fastapi.testclient import TestClient

import bot


def test_env_loader_default(monkeypatch):
    monkeypatch.delenv("TOAN_AAS_TEST_MISSING", raising=False)
    assert bot._env("TOAN_AAS_TEST_MISSING", "fallback") == "fallback"


def test_health_status_and_runtime_endpoints(monkeypatch):
    client = TestClient(bot.fastapi_app)
    assert client.get("/").status_code == 200
    status = client.get("/status")
    assert status.status_code == 200
    assert status.json()["health"] == "/health"
    health = client.get("/health")
    assert health.status_code == 200
    health_payload = health.json()
    assert health_payload["service"] == "TOAN AAS"
    assert "db_ok" in health_payload
    assert "db_file" in health_payload
    assert "payos_configured" in health_payload
    assert "telegram_configured" in health_payload
    assert "public_base_url_configured" in health_payload
    runtime = client.get("/runtime")
    assert runtime.status_code == 403
    monkeypatch.setattr(bot, "OPERATOR_API_TOKEN", "runtime-test-token")
    runtime = client.get("/runtime?token=runtime-test-token")
    assert runtime.status_code == 200
    assert runtime.json()["service"].startswith("TOAN AAS")


def test_public_start_menu_does_not_leak_admin_commands():
    text = bot.build_start_message_text("customer-test")
    forbidden = ["/operator_menu", "/telegram_takeover", "/runtime", "/dashboard", "/stats", "/pending", "/duyet", "/tuchoi", "/add", "/setvip"]
    assert "TOAN AAS" in text
    assert not any(item in text for item in forbidden)
    keyboard = bot.main_menu_keyboard(False)
    button_texts = [button.text for row in keyboard.inline_keyboard for button in row]
    assert "🧠 Operator" not in button_texts
    assert "📊 Quản Trị" not in button_texts


def test_admin_menu_contains_grouped_operator_and_system():
    text = bot.build_start_message_text(bot.ADMIN_ID)
    assert "Runtime" in text
    keyboard = bot.main_menu_keyboard(True)
    button_texts = [button.text for row in keyboard.inline_keyboard for button in row]
    assert "🧠 Operator" in button_texts
    assert "⚙️ Hệ Thống" in button_texts


def test_topup_keyboard_preserves_package_callbacks():
    keyboard = bot.build_topup_keyboard(123)
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "pkg|50k|123" in callbacks
    assert "pkg|100k|123" in callbacks
    assert "pkg|200k|123" in callbacks
    assert "menu|billing" in callbacks


def test_lifespan_keeps_api_alive_without_telegram_token(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "TELEGRAM_TOKEN", "")
    monkeypatch.setattr(bot, "TELEGRAM_STARTUP_ERROR", "")
    monkeypatch.setattr(bot, "OPERATOR_API_TOKEN", "runtime-test-token")
    try:
        with TestClient(bot.fastapi_app) as client:
            runtime = client.get("/runtime?token=runtime-test-token")
            assert runtime.status_code == 200
            payload = runtime.json()
            assert payload["status"] == "ok"
            assert "TELEGRAM_TOKEN" in payload["telegram_startup_error"]
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_lifespan_keeps_api_alive_when_telegram_builder_fails(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "TELEGRAM_TOKEN", "token-that-builder-rejects")
    monkeypatch.setattr(bot, "TELEGRAM_STARTUP_ERROR", "")
    monkeypatch.setattr(bot, "OPERATOR_API_TOKEN", "runtime-test-token")

    class BrokenBuilder:
        def token(self, _token):
            return self

        def build(self):
            raise RuntimeError("builder failed")

    monkeypatch.setattr(bot.Application, "builder", staticmethod(lambda: BrokenBuilder()))
    try:
        with TestClient(bot.fastapi_app) as client:
            runtime = client.get("/runtime?token=runtime-test-token")
            assert runtime.status_code == 200
            payload = runtime.json()
            assert payload["status"] == "ok"
            assert "builder failed" in payload["telegram_startup_error"]
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_cost_and_discount_rules():
    assert bot.calculate_dynamic_cost("chat", 0) == 2
    assert bot.calculate_dynamic_cost("download", 0) == 5
    assert bot.apply_discount(0, 100) == (100, 0.0)
    assert bot.apply_discount(5000, 100) == (90, 0.10)
    assert bot.apply_discount(20000, 100) == (80, 0.20)


def test_payos_signature_verification(monkeypatch):
    monkeypatch.setattr(bot, "PAYOS_CHECKSUM_KEY", "checksum-test")
    data = {"orderCode": 123, "amount": 10000, "status": "PAID"}
    raw = "&".join(f"{k}={data[k]}" for k in sorted(data.keys()))
    sig = hmac.new(b"checksum-test", raw.encode("utf-8"), hashlib.sha256).hexdigest()
    assert bot.verify_payos_signature(data, sig)
    assert not bot.verify_payos_signature(data, "bad-signature")


def test_payos_webhook_rejects_missing_checksum(monkeypatch):
    monkeypatch.setattr(bot, "PAYOS_CHECKSUM_KEY", "")
    client = TestClient(bot.fastapi_app)
    res = client.post(
        "/webhook/payos",
        json={"success": True, "data": {"orderCode": 123, "amount": 10000, "status": "PAID"}, "signature": ""},
    )
    assert res.status_code == 500


def test_foundation_tables_and_feature_flags(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    try:
        bot.init_db()
        conn = bot.db_connect()
        try:
            c = conn.cursor()
            for table in ["audit_logs", "system_events", "feature_flags"]:
                c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
                assert c.fetchone()[0] == table
            assert bot.is_feature_enabled("telegram_menu_v2") is True
            assert bot.is_feature_enabled("auto_publish") is False
        finally:
            conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_refund_charged_credit_restores_credit_and_total_spent(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "ADMIN_ID", "admin-only")
    try:
        bot.init_db()
        ok, cost, _ = bot.deduct_dynamic_credit("user-1", "download", 0)
        assert ok
        credits_after_spend, spent_after_spend, _ = bot.get_user("user-1")
        assert spent_after_spend == cost

        assert bot.refund_charged_credit("user-1", cost, "refund_test", "", "test", True)
        credits_after_refund, spent_after_refund, _ = bot.get_user("user-1")
        assert credits_after_refund == credits_after_spend + cost
        assert spent_after_refund == 0
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_ai_video_factory_prompt_gate_and_manifest_builder(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "ADMIN_ID", "admin-only")
    try:
        bot.init_db()
        character_bible = bot.build_character_bible("đạo lý gia đình")
        scene = bot.build_scene_manifest(
            "Series test",
            1,
            1,
            "đạo lý gia đình",
            character_bible,
            "tiktok",
            8,
        )
        assert scene["quality_score"]["decision"] in {"pass", "rewrite"}
        assert "visual_prompt" in scene and "video_prompt" in scene and "voice_line" in scene

        risky_scene = dict(scene)
        risky_scene["video_prompt"] = "clone real person celebrity likeness deepfake this exact person"
        assert bot.score_video_prompt_quality(risky_scene)["decision"] == "block"

        result = bot.build_film_series_manifest(
            "admin-only",
            "Người ăn xin trước nhà hàng",
            platform="tiktok",
            episodes=1,
            scenes_per_episode=8,
            duration=64,
        )
        assert result["ok"] is True
        assert len(result["created"]) == 1
        created = result["created"][0]
        assert created["manifest_id"] > 0
        assert len(created["task_ids"]) >= 8

        review = bot.film_review_pack_data("admin-only", created["job_id"])
        assert review["ok"] is True
        assert review["manifest_status"] == "ready_for_review"
        assert review["task_count"] >= 8
        assert review["commands"]["approve"].startswith("/film_approve")
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)
