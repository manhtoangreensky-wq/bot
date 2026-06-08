import hmac
import hashlib
import os
import re
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

import bot


def bot_source_text() -> str:
    return Path(bot.__file__).resolve().read_text(encoding="utf-8")


def source_between(source: str, start_marker: str, end_marker: str) -> str:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


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


def test_data_persistence_guard_backup_and_status(monkeypatch, tmp_path):
    source = bot_source_text()
    init_source = source_between(source, "def init_db():", "def now_text():")
    assert "DROP TABLE" not in init_source.upper()
    assert "DELETE FROM USERS" not in init_source.upper()
    assert "UPDATE USERS SET CREDITS=0" not in init_source.upper()
    assert "prepare_sqlite_persistent_path_once" in source
    assert "ensure_startup_sqlite_backup_once()" in init_source
    assert 'CommandHandler("data_status", cmd_data_status)' in source
    data_status_source = source_between(source, "async def cmd_data_status", "async def cmd_legal_export")
    assert "is_admin_user" in data_status_source
    assert "DATABASE_URL" in data_status_source
    assert "Persistent path candidate" in data_status_source

    db_path = tmp_path / "existing.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """CREATE TABLE users (
                user_id TEXT PRIMARY KEY,
                username TEXT,
                credits INTEGER DEFAULT 0,
                is_vip INTEGER DEFAULT 0,
                join_date TEXT,
                total_spent INTEGER DEFAULT 0
            )"""
        )
        conn.execute(
            "INSERT INTO users (user_id, username, credits, is_vip, join_date, total_spent) VALUES (?,?,?,?,?,?)",
            ("existing-user", "Existing", 100, 0, "2026-01-01 00:00:00", 0),
        )
        conn.commit()
    finally:
        conn.close()

    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "DB_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(bot, "DATA_PERSISTENCE_MODE", "sqlite")
    monkeypatch.setattr(bot, "DB_STARTUP_BACKUP_ENABLED", True)
    monkeypatch.setattr(bot, "DB_MIGRATION_DRY_RUN", False)
    monkeypatch.setattr(bot, "DB_ALLOW_DESTRUCTIVE_MIGRATION", False)
    monkeypatch.setattr(bot, "DB_STARTUP_BACKUP_PATHS", set())
    monkeypatch.setattr(bot, "DB_STARTUP_PREP_RESULT", {"status": "not_run", "path": "", "created_at": "", "reason": ""})
    bot.init_db()
    backups = list(backup_dir.glob("toandaas_system_*_startup.db"))
    assert backups
    payload = bot.data_persistence_status_payload(include_counts=True)
    assert payload["db_exists"] is True
    assert payload["db_writable"] is True
    assert payload["users_count"] >= 1
    assert payload["backup_enabled"] is True
    assert payload["destructive_migration_allowed"] is False

    blocked = False
    try:
        bot.assert_safe_migration_sql("DROP TABLE users")
    except RuntimeError:
        blocked = True
    assert blocked is True

    assert "secret" not in bot.masked_database_url("postgresql://user:secret@db.example.com/toanaas")


def test_persistent_sqlite_volume_copy_backup_and_no_overwrite(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    volume_dir = tmp_path / "data"
    target_db = volume_dir / "toandaas_system.db"
    backup_dir = volume_dir / "backups"
    local_db = tmp_path / "toandaas_system.db"
    conn = sqlite3.connect(local_db)
    try:
        conn.execute(
            """CREATE TABLE users (
                user_id TEXT PRIMARY KEY,
                username TEXT,
                credits INTEGER DEFAULT 0,
                is_vip INTEGER DEFAULT 0,
                join_date TEXT,
                total_spent INTEGER DEFAULT 0
            )"""
        )
        conn.execute(
            "INSERT INTO users (user_id, username, credits, is_vip, join_date, total_spent) VALUES (?,?,?,?,?,?)",
            ("persistent-user", "Persistent", 777, 0, "2026-01-01 00:00:00", 0),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(volume_dir))
    monkeypatch.setattr(bot, "DB_FILE", str(target_db))
    monkeypatch.setattr(bot, "DB_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(bot, "DATA_PERSISTENCE_MODE", "sqlite")
    monkeypatch.setattr(bot, "REQUIRE_PERSISTENT_DB", True)
    monkeypatch.setattr(bot, "DB_STARTUP_BACKUP_ENABLED", True)
    monkeypatch.setattr(bot, "DB_ALLOW_DESTRUCTIVE_MIGRATION", False)
    monkeypatch.setattr(bot, "DATA_PERSISTENCE_WARNINGS", [])
    monkeypatch.setattr(bot, "DB_STARTUP_PREP_RESULT", {"status": "not_run", "path": "", "created_at": "", "reason": ""})
    monkeypatch.setattr(bot, "DB_STARTUP_BACKUP_RESULT", {"status": "not_run", "path": "", "created_at": "", "reason": ""})
    monkeypatch.setattr(bot, "DB_STARTUP_BACKUP_PATHS", set())

    bot.init_db()
    assert target_db.exists()
    assert bot.DB_STARTUP_PREP_RESULT["status"] == "copied_local_to_persistent"
    assert list(backup_dir.glob("toandaas_system_*_startup.db"))
    payload = bot.data_persistence_status_payload(include_counts=True)
    assert payload["persistent_path_candidate"] is True
    assert payload["db_writable"] is True
    assert payload["backup_dir_writable"] is True
    assert payload["data_loss_risk_level"] in {"NO", "LOW"}
    assert payload["users_count"] >= 1

    conn = sqlite3.connect(local_db)
    try:
        conn.execute("UPDATE users SET credits=1 WHERE user_id='persistent-user'")
        conn.commit()
    finally:
        conn.close()
    monkeypatch.setattr(bot, "DB_STARTUP_PREP_RESULT", {"status": "not_run", "path": "", "created_at": "", "reason": ""})
    result = bot.prepare_sqlite_persistent_path_once()
    assert result["status"] == "persistent_db_exists"
    conn = sqlite3.connect(target_db)
    try:
        row = conn.execute("SELECT credits FROM users WHERE user_id='persistent-user'").fetchone()
        assert row[0] == 777
    finally:
        conn.close()


def test_persistent_sqlite_path_and_relative_risk(monkeypatch, tmp_path):
    assert bot.is_persistent_sqlite_path("/data/toandaas_system.db") is True

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)
    monkeypatch.setattr(bot, "DB_FILE", "toandaas_system.db")
    monkeypatch.setattr(bot, "DB_BACKUP_DIR", "backups")
    monkeypatch.setattr(bot, "DATA_PERSISTENCE_MODE", "sqlite")
    monkeypatch.setattr(bot, "DATABASE_URL", "")
    monkeypatch.setattr(bot, "REQUIRE_PERSISTENT_DB", False)
    monkeypatch.setattr(bot, "DATA_PERSISTENCE_WARNINGS", [])
    monkeypatch.setattr(bot, "DB_STARTUP_PREP_RESULT", {"status": "not_run", "path": "", "created_at": "", "reason": ""})

    payload = bot.data_persistence_status_payload(include_counts=False)
    assert payload["persistent_path_candidate"] is False
    assert payload["data_loss_risk"] is True
    assert payload["data_loss_risk_level"] == "YES"


def test_data_persistence_warns_missing_railway_db(monkeypatch, tmp_path):
    missing_db = tmp_path / "missing.db"
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setattr(bot, "DB_FILE", str(missing_db))
    monkeypatch.setattr(bot, "DATA_PERSISTENCE_MODE", "sqlite")
    monkeypatch.setattr(bot, "DATABASE_URL", "")
    monkeypatch.setattr(bot, "DATA_PERSISTENCE_WARNINGS", [])
    monkeypatch.setattr(bot, "DB_STARTUP_PREP_RESULT", {"status": "not_run", "path": "", "created_at": "", "reason": ""})
    payload = bot.data_persistence_status_payload(include_counts=False)
    assert payload["db_exists"] is False
    assert payload["data_loss_risk"] is True
    assert any(item["code"] == "DATA_LOSS_RISK_DETECTED" for item in payload["warnings"])


def test_customer_guide_download_routes_are_word_only():
    client = TestClient(bot.fastapi_app)
    docx = client.get("/download/huong-dan-toan-aas.docx")
    md = client.get("/download/huong-dan-toan-aas.md")
    assert docx.status_code == 200
    assert md.status_code == 404
    assert "TOAN_AAS_HUONG_DAN_SU_DUNG_CHO_KHACH_V1.docx" in docx.headers["content-disposition"]


def test_public_branding_and_scope_static_guard():
    repo_root = Path(bot.__file__).resolve().parent
    bot_source = (repo_root / "bot.py").read_text(encoding="utf-8")
    index_html = (repo_root / "index.html").read_text(encoding="utf-8")
    public_surface = bot_source + "\n" + index_html

    assert bot.BOT_USERNAME == "toanaasbot"
    assert bot.make_payos_description("50k") == "AAS50K"
    assert bot.manual_qr_url(123, 50000, 999).find("AAS+123+999") >= 0
    assert "https://t.me/toanaasbot" in index_html
    assert "https://t.me/Httdhtoan" not in public_surface
    assert "@Httdhtoan" not in public_surface
    assert "TOAN DAAS" not in public_surface
    assert "DAAS10K" not in public_surface
    assert "DAAS50K" not in public_surface
    assert "affiliate_id=1" not in public_surface
    assert "kho affiliate" not in public_surface
    assert "Lưu link affiliate" not in public_surface


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


def test_provider_orchestrator_registry_is_admin_first(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "OPENROUTER_API_KEY", "openrouter-test-key")
    monkeypatch.setattr(bot, "KLING_ACCESS_KEY", "kling-access")
    monkeypatch.setattr(bot, "KLING_SECRET_KEY", "kling-secret")
    monkeypatch.setattr(bot, "REPLICATE_API_TOKEN", "replicate-token")
    monkeypatch.setattr(bot, "ELEVENLABS_API_KEY", "elevenlabs-key")
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "deepgram-key")
    monkeypatch.setattr(bot, "LOCAL_FFMPEG_PATH", r"C:\ffmpeg\bin\ffmpeg.exe")
    monkeypatch.setattr(bot, "SHOPAIKEY_ENABLED", False)
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "shopaikey-key")
    try:
        bot.init_db()
        registry = bot.provider_registry()
        expected = {
            "openrouter",
            "kling",
            "replicate",
            "elevenlabs",
            "deepgram",
            "local_worker_ffmpeg",
            "shopaikey",
        }
        assert expected.issubset(registry.keys())
        assert all(payload["admin_only"] is True for payload in registry.values())
        assert registry["openrouter"]["stage"] == "ready_for_smoke_test"
        assert registry["kling"]["stage"] == "admin_only"
        assert registry["replicate"]["stage"] == "admin_only"
        assert registry["shopaikey"]["stage"] == "disabled"
        assert "text_brain" in registry["openrouter"]["capabilities"]
        assert "video_generate" in registry["kling"]["capabilities"]
        assert "image_generate" in registry["replicate"]["capabilities"]
        assert "tts" in registry["elevenlabs"]["capabilities"]
        assert "stt" in registry["deepgram"]["capabilities"]
        assert "ffmpeg" in registry["local_worker_ffmpeg"]["capabilities"]
        matrix = "\n".join(bot.provider_matrix_lines())
        assert "Admin-first only" in matrix
        assert "Không mở public render" in matrix
        assert "không hiển thị secret" in matrix
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_shopaikey_smoke_test_is_admin_only_and_experimental():
    repo_root = Path(bot.__file__).resolve().parent
    source = bot_source_text()
    env_example = (repo_root / ".env.example").read_text(encoding="utf-8")
    command_source = source_between(source, "async def cmd_tool_test_shopaikey", "class TranslationProviderError")

    assert 'SHOPAIKEY_DEFAULT_MODEL = _env("SHOPAIKEY_DEFAULT_MODEL") or "gpt-4o-mini"' in source
    assert "SHOPAIKEY_ENABLED=false" in env_example
    assert "SHOPAIKEY_ADMIN_ONLY=true" in env_example
    assert "SHOPAIKEY_DEFAULT_MODEL=gpt-4o-mini" in env_example
    assert "SHOPAIKEY_USAGE_URL=https://api.shopaikey.com/usage" in env_example
    assert "SHOPAIKEY_USAGE_ALERT_PERCENT=10" in env_example
    assert "SHOPAIKEY_IMAGE_URL=https://api.shopaikey.com/images/google/generations" in env_example
    assert "SHOPAIKEY_IMAGE_MODEL=nano-banana" in env_example
    assert "SHOPAIKEY_VIDEO_URL=https://api.shopaikey.com/v1/video/generations" in env_example
    assert "SHOPAIKEY_VIDEO_MODEL=veo3.1-fast" in env_example
    assert "SHOPAIKEY_VIDEO_FALLBACK_MODELS=veo3.1,veo3.1-fast,veo3.1-pro" in env_example
    assert "SHOPAIKEY_PUBLIC_IMAGE_ENABLED=false" in env_example
    assert "SHOPAIKEY_PUBLIC_VIDEO_ENABLED=false" in env_example
    assert "IMAGE_BASE_COST_XU=50" in env_example
    assert "VIDEO_BASE_COST_XU=300" in env_example
    assert "MEDIA_PRICE_MULTIPLIER=2" in env_example
    assert "IMAGE_LOW_COST_XU=50" in env_example
    assert "IMAGE_STANDARD_COST_XU=300" in env_example
    assert "IMAGE_HIGH_COST_XU=500" in env_example
    assert "VIDEO_LOW_COST_XU=300" in env_example
    assert "VIDEO_STANDARD_COST_XU=600" in env_example
    assert "VIDEO_HIGH_COST_XU=1200" in env_example
    assert "VIDEO_PREMIUM_COST_XU=2000" in env_example
    assert "WORKFLOW_TREND_ANALYSIS_COST_XU=20" in env_example
    assert "WORKFLOW_SCRIPT_STORYBOARD_COST_XU=30" in env_example
    assert "WORKFLOW_PROMPT_PACK_COST_XU=20" in env_example
    assert "SHOPAIKEY_IMAGE_COST_XU=50" in env_example
    assert "SHOPAIKEY_VIDEO_COST_XU=200" in env_example
    assert "SHOPAIKEY_REFUND_ON_PROVIDER_FAIL=true" in env_example
    assert "SHOPAIKEY_REQUIRE_CONFIRM_BEFORE_DEDUCT=true" in env_example
    assert "SHOPAIKEY_PUBLIC_JOB_LOCK_ENABLED=true" in env_example
    assert "TREND_VIDEO_WORKFLOW_ENABLED=true" in env_example
    assert "TREND_VIDEO_WORKFLOW_ADMIN_ONLY=true" in env_example
    assert "TREND_PROMPT_COST_XU=0" in env_example
    assert "TREND_ANALYSIS_COST_XU=0" in env_example
    assert "TREND_WORKFLOW_PUBLIC_ENABLED=false" in env_example
    assert "TREND_WORKFLOW_BILLING_ENABLED=true" in env_example
    assert "TREND_WORKFLOW_REQUIRE_CONFIRM=true" in env_example
    assert "SYSTEM_MAINTENANCE_MODE=false" in env_example
    assert "PROVIDER_FREEZE_ENABLED=false" in env_example
    assert "TOOL_FREEZE_IMAGE=false" in env_example
    assert "SHOPAIKEY_AUTO_FREEZE_ENABLED=true" in env_example
    assert "SHOPAIKEY_LOW_CREDIT_FREEZE_PERCENT=5" in env_example
    assert "SHOPAIKEY_ERROR_FREEZE_THRESHOLD=5" in env_example
    assert "USER_WAIT_IMAGE_MESSAGE=" in env_example
    assert "USER_WAIT_VIDEO_MESSAGE=" in env_example
    assert "USER_JOB_LOCK_MESSAGE=" in env_example
    assert "if not is_admin_user(update.effective_user.id)" in command_source
    assert "Trả lời đúng một câu tiếng Việt có chữ TEST_OK." in source
    assert "TOAN AAS image smoke test: simple turquoise AI automation logo" in source
    assert "A short clean futuristic turquoise AI automation logo animation" in source
    assert "shopaikey_video_model_sequence" in source
    assert "FAIL_NO_AVAILABLE_CHANNEL" in source
    assert "provider/group has no available channel for selected model" in source
    assert "cmd_tool_test_shopaikey_image" in source
    assert "cmd_tool_test_shopaikey_video" in source
    assert "cmd_shopaikey_video_job" in source
    assert "shopaikey_image" in source
    assert "shopaikey_video" in source
    assert 'required_text="TEST_OK"' in source
    assert "Không log prompt/response/key" in command_source
    assert "Không trừ Xu" in command_source
    assert "add_credit(" not in command_source
    assert "deduct_dynamic_credit(" not in command_source
    assert "apiKey=***" in source
    assert "FAIL_CONTENT_EMPTY" in source


def test_provider_maintenance_error_classify_sanitize_and_freeze(monkeypatch):
    assert bot.classify_provider_error(401, "", "invalid token") == "AUTH_FAILED"
    assert bot.classify_provider_error(200, "", "no available channel for model") == "NO_CHANNEL"
    assert bot.classify_provider_error(429, "", "rate limit") == "RATE_LIMITED"
    assert bot.classify_provider_error(503, "", "provider down") == "PROVIDER_UNAVAILABLE"
    assert bot.classify_provider_error(0, "", "TimedOut: timed out") == "TIMEOUT"
    assert bot.classify_provider_error(200, "", "insufficient balance credit quota") == "CREDIT_LOW_OR_EMPTY"
    assert bot.classify_provider_error(400, "", "invalid params") == "BAD_REQUEST"

    sanitized = bot.sanitize_provider_error("sk-testsecret123456789 apiKey=secret Bearer tokenvalue https://example.com/private/path " + "x" * 500)
    assert "sk-testsecret" not in sanitized
    assert "secret" not in sanitized
    assert "tokenvalue" not in sanitized
    assert "https://example.com" not in sanitized
    assert len(sanitized) <= 300

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "SYSTEM_MAINTENANCE_MODE", False)
    monkeypatch.setattr(bot, "PROVIDER_FREEZE_ENABLED", False)
    monkeypatch.setattr(bot, "TOOL_FREEZE_IMAGE", False)
    monkeypatch.setattr(bot, "TOOL_FREEZE_VIDEO", False)
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_IMAGE_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_VIDEO_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "test-key")
    try:
        bot.init_db()
        assert bot.shopaikey_public_generation_guard("image")[0] is True
        bot.set_provider_freeze_state("shopaikey", True, "NO_CHANNEL", "no available channel sk-hidden", "test")
        ok, message = bot.shopaikey_public_generation_guard("image")
        assert ok is False
        assert "API" not in message
        assert bot.provider_freeze_row("shopaikey")["reason_code"] == "NO_CHANNEL"
        bot.set_provider_freeze_state("shopaikey", False, "manual_unfreeze", "ok", "test")
        assert bot.shopaikey_public_generation_guard("image")[0] is True
        monkeypatch.setattr(bot, "TOOL_FREEZE_IMAGE", True)
        assert bot.shopaikey_public_generation_guard("image")[0] is False
        monkeypatch.setattr(bot, "TOOL_FREEZE_IMAGE", False)
        monkeypatch.setattr(bot, "SYSTEM_MAINTENANCE_MODE", True)
        assert bot.shopaikey_public_generation_guard("image")[0] is False
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_provider_auto_freeze_and_status_commands(monkeypatch):
    source = bot_source_text()
    assert "async def cmd_maintenance_status" in source
    assert "async def cmd_provider_freeze" in source
    assert "async def cmd_provider_unfreeze" in source
    assert 'provider_freeze_display("shopaikey")' in source
    assert 'provider_freeze_runtime_on("shopaikey")' in source
    assert 'CommandHandler("maintenance_status", cmd_maintenance_status)' in source
    assert 'CommandHandler("provider_freeze", cmd_provider_freeze)' in source
    assert 'CommandHandler("provider_unfreeze", cmd_provider_unfreeze)' in source
    assert "No Xu deducted" in source or "Không trừ Xu" in source

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "SHOPAIKEY_AUTO_FREEZE_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_ERROR_FREEZE_THRESHOLD", 2)
    monkeypatch.setattr(bot, "SHOPAIKEY_ERROR_FREEZE_WINDOW_MINUTES", 15)
    monkeypatch.setattr(bot, "SHOPAIKEY_FREEZE_COOLDOWN_MINUTES", 1)
    try:
        bot.init_db()
        bot.record_provider_error("shopaikey", "image", "NO_CHANNEL", "first no available channel")
        assert int(bot.provider_freeze_row("shopaikey").get("is_frozen") or 0) == 0
        bot.record_provider_error("shopaikey", "image", "NO_CHANNEL", "second no available channel")
        row = bot.provider_freeze_row("shopaikey")
        assert int(row.get("is_frozen") or 0) == 1
        assert row["reason_code"] == "NO_CHANNEL"
        assert bot.provider_error_count("shopaikey", 15) >= 2
        bot.set_provider_freeze_state("shopaikey", True, "TEST_COOLDOWN", "cooldown", "test", cooldown_minutes=1)
        conn = bot.db_connect()
        try:
            conn.execute("UPDATE provider_freeze_state SET unfreeze_after=? WHERE provider='shopaikey'", ("2000-01-01 00:00:00",))
            conn.commit()
        finally:
            conn.close()
        assert bot.maybe_auto_unfreeze_provider("shopaikey") is True
        assert int(bot.provider_freeze_row("shopaikey").get("is_frozen") or 0) == 0
        events = bot.recent_system_events(5)
        assert any(event.get("event_type") == "provider_auto_unfreeze" for event in events)
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_provider_freeze_display_cleanup_after_unfreeze(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "PROVIDER_FREEZE_ENABLED", False)
    try:
        bot.init_db()
        assert bot.provider_freeze_runtime_on("shopaikey") is False
        display = bot.provider_freeze_display("shopaikey")
        assert display["frozen"] is False
        assert display["reason"] == "-"
        assert display["message"] == "-"
        assert display["unfreeze_after"] == "-"

        bot.set_provider_freeze_state("shopaikey", True, "test", "test freeze", "test")
        assert bot.provider_freeze_runtime_on("shopaikey") is True
        display = bot.provider_freeze_display("shopaikey")
        assert display["frozen"] is True
        assert display["reason"] == "test"
        assert display["message"] == "test freeze"

        bot.set_provider_freeze_state("shopaikey", False, "manual_unfreeze", "manual unfreeze", "test")
        assert bot.provider_freeze_runtime_on("shopaikey") is False
        display = bot.provider_freeze_display("shopaikey")
        assert display["frozen"] is False
        assert display["reason"] == "-"
        assert display["message"] == "-"
        assert display["unfreeze_after"] == "-"
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_shopaikey_public_billing_flow_guards_and_schema(monkeypatch):
    source = bot_source_text()
    image_source = source_between(source, "async def cmd_shopaikey_image_public", "async def cmd_shopaikey_video_public")
    callback_source = source_between(source, "async def handle_shopaikey_public_callback", "class TranslationProviderError")
    assert "shopaikey_public_generation_guard" in image_source
    assert "set_shopaikey_pending_confirmation" in image_source
    assert "spend_fixed_credit_info" not in image_source
    assert "spend_fixed_credit_info" in callback_source
    assert "refund_shopaikey_job_if_needed" in callback_source
    assert "record_shopaikey_billing_event" in callback_source
    assert "SHOPAIKEY_REQUIRE_CONFIRM_BEFORE_DEDUCT" in source
    assert "SHOPAIKEY_REFUND_ON_PROVIDER_FAIL" in source
    assert "Pricing mode:" in source and "tiered_media_pricing" in source
    assert "Image tiers:" in source
    assert "Video tiers:" in source
    assert "Price table source:" in source
    assert "deduct_dynamic_credit(" not in callback_source
    assert "add_credit(" not in callback_source

    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_IMAGE_ENABLED", False)
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_VIDEO_ENABLED", False)
    public_off_message = "🧪 Tính năng này đang thử nghiệm nội bộ, chưa mở công khai. TOAN AAS sẽ mở sau khi kiểm tra ổn định."
    assert bot.shopaikey_public_generation_guard("image") == (False, public_off_message)
    assert bot.shopaikey_public_generation_guard("video") == (False, public_off_message)
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_IMAGE_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "test-key")
    assert bot.shopaikey_public_generation_guard("image")[0] is True

    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_COST_XU", 200)
    monkeypatch.setattr(bot, "SHOPAIKEY_IMAGE_COST_XU", 50)
    monkeypatch.setattr(bot, "MEDIA_PRICE_MULTIPLIER", 2)
    monkeypatch.setattr(bot, "IMAGE_LOW_PROVIDER_COST_XU", 160)
    monkeypatch.setattr(bot, "VIDEO_LOW_PROVIDER_COST_XU", 320)
    monkeypatch.setattr(bot, "IMAGE_LOW_COST_XU", 320)
    monkeypatch.setattr(bot, "VIDEO_LOW_COST_XU", 640)
    monkeypatch.setattr(bot, "WORKFLOW_TREND_ANALYSIS_COST_XU", 11)
    monkeypatch.setattr(bot, "WORKFLOW_SCRIPT_STORYBOARD_COST_XU", 22)
    monkeypatch.setattr(bot, "WORKFLOW_PROMPT_PACK_COST_XU", 33)
    monkeypatch.setattr(bot, "SHOPAIKEY_REQUIRE_CONFIRM_BEFORE_DEDUCT", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_REFUND_ON_PROVIDER_FAIL", True)
    assert bot.image_base_cost_xu() == 320
    assert bot.video_base_cost_xu() == 640
    monkeypatch.setattr(bot, "IMAGE_LOW_COST_XU", 0)
    assert bot.image_base_cost_xu() == 320
    monkeypatch.setattr(bot, "IMAGE_LOW_COST_XU", 320)
    assert bot.shopaikey_video_cost_for_flow(False) == 640
    assert bot.shopaikey_video_cost_for_flow(True) == 640
    pricing = bot.media_workflow_pricing_payload()
    assert pricing["billing_mode"] == "tiered_media_pricing"
    assert pricing["price_table_source"] == "centralized_price_menu"
    assert pricing["media_price_multiplier"] == 2
    assert pricing["image_tiers"]["low"]["cost"] == 320
    assert pricing["video_tiers"]["low"]["cost"] == 640
    assert pricing["quick_image_cost"] == 320
    assert pricing["workflow_image_cost"] == 320
    assert pricing["quick_video_cost"] == 640
    assert pricing["workflow_video_cost"] == 640
    assert pricing["workflow_content_total_cost"] == 66
    assert pricing["legacy_shopaikey_image_fallback"] == 50
    assert pricing["legacy_shopaikey_video_fallback"] == 200
    assert bot.shopaikey_billing_flow_status_text().startswith("ready")

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    try:
        bot.init_db()
        conn = bot.db_connect()
        try:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(shopaikey_jobs)").fetchall()}
            billing_cols = {row[1] for row in conn.execute("PRAGMA table_info(shopaikey_billing_events)").fetchall()}
        finally:
            conn.close()
        assert {
            "xu_cost_planned",
            "xu_deducted",
            "refund_status",
            "refund_amount",
            "refund_reason",
            "billing_status",
            "confirm_required",
            "confirmed_at",
            "source_job_id",
        }.issubset(cols)
        assert {"user_id", "job_id", "event_type", "amount_xu", "balance_before", "balance_after", "reason", "created_at"}.issubset(billing_cols)
        job_id = bot.create_shopaikey_job("u2", "c2", "image", model="nano-banana", prompt="prompt", status="IN_PROGRESS", admin_only=False, xu_cost_planned=320)
        bot.update_shopaikey_job(job_id=job_id, xu_deducted=320, refund_status="pending", refund_reason="provider_fail")
        active = bot.shopaikey_active_job_for_user("u2", "image")
        assert active["xu_cost_planned"] == 320
        assert active["xu_deducted"] == 320
        assert active["refund_status"] == "pending"
        assert active["confirm_required"] == 1
        assert active["billing_status"] == "pending_confirm"
        bot.record_shopaikey_billing_event("u2", job_id, "confirm", 0, 100, 100, "test confirm")
        bot.record_shopaikey_billing_event("u2", job_id, "deduct", 320, 1000, 680, "test deduct")
        conn = bot.db_connect()
        try:
            billing_events = conn.execute("SELECT event_type, amount_xu FROM shopaikey_billing_events WHERE job_id=? ORDER BY id", (job_id,)).fetchall()
            assert [(row[0], row[1]) for row in billing_events] == [("confirm", 0), ("deduct", 320)]
        finally:
            conn.close()
        assert bot.shopaikey_video_cost_for_flow(True, "u2") == 640
        image_job_id = bot.create_shopaikey_job("u2", "c2", "image", model="nano-banana", prompt="prompt", status="SUCCESS", admin_only=False, xu_cost_planned=320)
        bot.update_shopaikey_job(job_id=image_job_id, xu_deducted=320)
        assert bot.shopaikey_paid_image_source_available("u2", str(image_job_id)) is True
        assert bot.shopaikey_video_cost_for_flow(True, "u2") == 640
        video_job_id = bot.create_shopaikey_job("u2", "c2", "video", model="veo3.1-fast", prompt="video", status="QUEUED", admin_only=False, xu_cost_planned=640, source_job_id=str(image_job_id))
        assert video_job_id > 0
        assert bot.shopaikey_paid_image_source_available("u2", str(image_job_id)) is False
        assert bot.shopaikey_video_cost_for_flow(True, "u2") == 640
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_shopaikey_status_persists_usage_and_chat_snapshots(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    try:
        bot.init_db()
        usage = {
            "total": 10,
            "used": 0,
            "balance": 10,
            "remaining": 10,
            "remaining_percent": 100,
            "group_name": "cheap,gemini,claude_code",
            "token_name": "cheap_4037_1780837250240",
        }
        bot.save_shopaikey_usage_snapshot(usage, "test")
        snapshot = bot.shopaikey_last_usage_snapshot()
        assert snapshot["total"] == "10"
        assert snapshot["remaining"] == "10"
        assert snapshot["remaining_percent"] == "100"
        assert snapshot["group_name"] == "cheap,gemini,claude_code"
        assert "remaining 10 / total 10 (100%)" in bot.shopaikey_usage_summary_text(snapshot)

        result = {"status": "PASS", "model": "gpt-4o-mini", "http_status": 200, "latency_ms": 123}
        detail = "model=gpt-4o-mini; http=200; latency_ms=123; error_class=-"
        bot.save_tool_test_result("shopaikey", "PASS", detail, "test")
        bot.save_tool_test_result("shopaikey_chat", "PASS", detail, "test")
        bot.save_shopaikey_chat_snapshot(result, detail, "test")
        bot.save_tool_test_result("shopaikey_tts", "PASS", "model=tts-1/alloy; http=200; output_sent=yes", "test")
        bot.save_shopaikey_component_snapshot(
            "tts",
            {"status": "PASS", "model": "tts-1/alloy", "http_status": 200, "latency_ms": 0},
            "model=tts-1/alloy; http=200; output_sent=yes",
            "test",
        )
        bot.save_tool_test_result("shopaikey_image", "PASS", "model=nano-banana; http=200; size=768x1344; output_sent=yes", "test")
        bot.save_shopaikey_component_snapshot(
            "image",
            {"status": "PASS", "model": "nano-banana", "http_status": 200, "latency_ms": 321},
            "model=nano-banana; http=200; size=768x1344; output_sent=yes",
            "test",
        )
        bot.save_tool_test_result("shopaikey_video", "PASS_SUBMITTED", "model=veo3.1-fast; http=200; task_id=task_1", "test")
        bot.save_shopaikey_component_snapshot(
            "video",
            {"status": "PASS_SUBMITTED", "model": "veo3.1-fast", "http_status": 200, "latency_ms": 444},
            "model=veo3.1-fast; http=200; task_id=task_1",
            "test",
        )
        chat_snapshot = bot.shopaikey_chat_status_snapshot()
        assert chat_snapshot["status"] == "PASS"
        assert chat_snapshot["model"] == "gpt-4o-mini"
        assert "PASS" in bot.shopaikey_chat_status_text()
        assert "gpt-4o-mini" in bot.shopaikey_chat_status_text()
        assert bot.shopaikey_tts_status_snapshot()["status"] == "PASS"
        assert "tts-1/alloy" in bot.shopaikey_tts_status_text()
        assert bot.shopaikey_image_status_snapshot()["status"] == "PASS"
        assert "nano-banana" in bot.shopaikey_image_status_text()
        assert bot.shopaikey_video_status_snapshot()["status"] == "PASS_SUBMITTED"
        assert "veo3.1-fast" in bot.shopaikey_video_status_text()

        bot.save_tool_test_result("shopaikey_image", "PASS", "model=nano-banana; http=200; size=768x1344; output_sent=yes", "test")
        bot.save_shopaikey_component_snapshot(
            "image",
            {"status": "PASS", "model": "nano-banana", "http_status": 200, "latency_ms": 555},
            "model=nano-banana; http=200; size=768x1344; output_sent=yes",
            "test",
        )
        assert bot.shopaikey_chat_status_snapshot()["status"] == "PASS"
        assert bot.shopaikey_tts_status_snapshot()["status"] == "PASS"
        assert bot.shopaikey_image_status_snapshot()["status"] == "PASS"
        assert bot.shopaikey_video_status_snapshot()["status"] == "PASS_SUBMITTED"
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_shopaikey_video_model_fallback_payload_and_reason(monkeypatch):
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_MODEL", "veo3.1-fast")
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_FALLBACK_MODELS", "veo3.1,veo3.1-fast,grok-video-3,grok-video-3-10s")
    assert bot.shopaikey_video_model_sequence() == ["veo3.1-fast", "veo3.1", "grok-video-3", "grok-video-3-10s"]
    assert bot.shopaikey_video_model_sequence("grok-video-3") == ["grok-video-3"]

    veo_payload = bot.shopaikey_video_request_payload("veo3.1")
    assert veo_payload["model"] == "veo3.1"
    assert veo_payload["metadata"]["aspect_ratio"] == "16:9"

    grok_payload = bot.shopaikey_video_request_payload("grok-video-3")
    assert grok_payload["model"] == "grok-video-3"
    assert "metadata" not in grok_payload

    grok_10s_payload = bot.shopaikey_video_request_payload("grok-video-3-10s")
    assert grok_10s_payload["metadata"]["quality"] == "720p"

    assert bot.shopaikey_classify_video_error(503, "No available channel for model veo3.1-fast") == "FAIL_NO_AVAILABLE_CHANNEL"
    assert bot.shopaikey_classify_video_error(401, "unauthorized") == "FAIL_AUTH"
    assert bot.shopaikey_classify_video_error(400, "bad request") == "FAIL_BAD_REQUEST"
    assert bot.shopaikey_video_reason_text({"status": "FAIL_NO_AVAILABLE_CHANNEL", "detail": ""}) == "provider/group has no available channel for selected model."


def test_shopaikey_video_status_extractors_job_lock_and_public_guard(monkeypatch):
    assert bot.normalize_shopaikey_video_status("queued") == "QUEUED"
    assert bot.normalize_shopaikey_video_status("processing") == "IN_PROGRESS"
    assert bot.normalize_shopaikey_video_status("IN_PROGRESS") == "IN_PROGRESS"
    assert bot.normalize_shopaikey_video_status("SUCCESS") == "SUCCESS"
    assert bot.normalize_shopaikey_video_status("succeeded") == "SUCCESS"
    assert bot.normalize_shopaikey_video_status("completed") == "SUCCESS"
    assert bot.normalize_shopaikey_video_status("FAILURE") == "FAILED"
    assert bot.normalize_shopaikey_video_status("failed") == "FAILED"
    assert bot.shopaikey_db_video_status("FAIL_NO_AVAILABLE_CHANNEL") == "FAILED"

    assert bot.shopaikey_extract_task_id({"task_id": "task_direct"}) == "task_direct"
    assert bot.shopaikey_extract_task_id({"data": {"task_id": "task_nested"}}) == "task_nested"
    assert bot.shopaikey_video_result_url({"data": {"result_url": "https://example.com/a.mp4"}}) == "https://example.com/a.mp4"
    nested_result = {
        "data": {
            "data": {
                "success": True,
                "data": [{"video_url": "https://example.com/nested.mp4", "state": "succeeded"}],
            }
        }
    }
    assert bot.shopaikey_video_result_url(nested_result) == "https://example.com/nested.mp4"
    assert "secret" not in bot.shopaikey_sanitize_error("https://x.test/usage?apiKey=secret")
    assert len(bot.shopaikey_sanitize_error("x" * 1000)) <= 500

    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_IMAGE_ENABLED", False)
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_VIDEO_ENABLED", False)
    assert bot.shopaikey_public_generation_guard("image")[0] is False
    assert bot.shopaikey_public_generation_guard("video")[0] is False
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_IMAGE_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "test-key")
    assert bot.shopaikey_public_generation_guard("image")[0] is True

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    try:
        bot.init_db()
        job_id = bot.create_shopaikey_job("u1", "c1", "video", model="veo3.1-fast", prompt="full prompt with sensitive details", status="IN_PROGRESS")
        monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_JOB_LOCK_ENABLED", True)
        active = bot.shopaikey_active_job_for_user("u1", "video")
        assert active
        assert active["id"] == job_id
        assert len(active["prompt_preview"]) <= 120
        monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_JOB_LOCK_ENABLED", False)
        assert bot.shopaikey_active_job_for_user("u1", "video") is None
        monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_JOB_LOCK_ENABLED", True)
        bot.update_shopaikey_job(job_id=job_id, task_id="task_abc", status="SUCCESS", result_url="https://example.com/video.mp4", result_sent=1, finished_at=bot.now_text())
        assert bot.shopaikey_active_job_for_user("u1", "video") is None
        saved = bot.shopaikey_job_by_task_id("task_abc")
        assert saved["status"] == "SUCCESS"
        assert saved["result_sent"] == 1
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_trend_video_flow_admin_first_prompt_only(monkeypatch):
    source = bot_source_text()
    shared_source = source_between(source, "async def send_trend_video_flow_for_topic", "async def cmd_trend_video_flow")
    command_source = source_between(source, "async def cmd_trend_video_flow", "async def handle_trend_video_flow_callback")
    callback_source = source_between(source, "async def handle_trend_video_flow_callback", "async def cmd_create_media")
    pending_source = source_between(source, "async def handle_trend_video_flow_pending_text", "async def cmd_cancel")
    message_source = source_between(source, "async def handle_message", "TELEGRAM_STARTUP_ERROR =")
    admin_smoke_source = source_between(source, "async def cmd_tool_test_workflow_image", "async def cmd_image_tools")
    shopai_callback_source = source_between(source, "async def handle_shopaikey_public_callback", "class TranslationProviderError")
    combined_source = shared_source + command_source + callback_source

    assert 'CommandHandler("trend_video_flow", cmd_trend_video_flow)' in source
    assert 'CommandHandler("cancel", cmd_cancel)' in source
    assert 'CallbackQueryHandler(handle_trend_video_flow_callback, pattern=r"^tvflow\\|")' in source
    assert 'CommandHandler("tool_test_workflow_image", cmd_tool_test_workflow_image)' in source
    assert "trend_video_workflow_status_text()" in source
    assert "trend_workflow_image_generation_status_text()" in source
    assert "trend_workflow_content_confirm_text" in source
    assert "TREND_WORKFLOW_BILLING_ENABLED" in source
    assert "TREND_WORKFLOW_REQUIRE_CONFIRM" in source
    assert "Trend video workflow:" in source
    assert "Workflow image generation:" in source
    assert "Bạn muốn tạo ảnh từ prompt nào" in source
    assert "tvflow|image_scene_1" in source
    assert "tvflow|image_scene_2" in source
    assert "tvflow|image_scene_3" in source
    assert "set_trend_video_flow_pending(uid)" in command_source
    assert "trend_video_pending_prompt_text()" in command_source
    assert "pending_action" in source and "trend_video_flow" in source
    assert "TREND_VIDEO_PENDING_TTL_SECONDS" in source
    assert "handle_trend_video_flow_pending_text(update, context)" in message_source
    assert message_source.index("handle_trend_video_flow_pending_text(update, context)") < message_source.index("is_probable_media_tags_text")
    assert "send_or_confirm_trend_video_flow(update, context, topic)" in pending_source
    assert "clear_trend_video_flow_pending(uid)" in pending_source
    assert "shopaikey_image_generate" not in combined_source
    assert "shopaikey_video_create" not in combined_source
    assert "spend_fixed_credit_info" in combined_source
    assert "trend_workflow_content" in combined_source
    assert "apply_member_discount_flag=False" in combined_source
    assert "record_trend_workflow_billing_event" in combined_source
    assert "deduct_dynamic_credit" not in combined_source
    assert "add_credit(" not in combined_source
    assert "shopaikey_public_generation_guard(\"image\")" in callback_source
    assert "trend_video_workflow_can_access(uid)" in callback_source
    assert "set_shopaikey_pending_confirmation" in callback_source
    assert "Bot chỉ trừ Xu sau khi bạn bấm xác nhận" in callback_source
    assert "shopaikey_image_generate" in admin_smoke_source
    assert "spend_fixed_credit_info" not in admin_smoke_source
    assert "deduct_dynamic_credit" not in admin_smoke_source
    assert "add_credit(" not in admin_smoke_source
    assert "update_trend_workflow_generated_image" in shopai_callback_source
    assert "trend_workflow_image_success_keyboard" in shopai_callback_source
    assert "Bạn hài lòng với ảnh này chưa" in shopai_callback_source
    assert "🎞 Tạo video từ ảnh này" in source

    monkeypatch.setattr(bot, "TREND_VIDEO_WORKFLOW_ENABLED", True)
    monkeypatch.setattr(bot, "TREND_VIDEO_WORKFLOW_ADMIN_ONLY", True)
    monkeypatch.setattr(bot, "TREND_WORKFLOW_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "TREND_WORKFLOW_BILLING_ENABLED", True)
    monkeypatch.setattr(bot, "TREND_WORKFLOW_REQUIRE_CONFIRM", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_IMAGE_ENABLED", False)
    assert bot.trend_video_workflow_status_text() == "enabled/admin-only"
    assert bot.trend_workflow_image_generation_status_text() == "guarded/public OFF"
    assert bot.trend_video_workflow_can_access(0) is False
    monkeypatch.setattr(bot, "TREND_WORKFLOW_PUBLIC_ENABLED", True)
    assert bot.trend_video_workflow_status_text() == "enabled/public_content_billing_guarded"
    assert bot.trend_video_workflow_can_access(0) is True
    monkeypatch.setattr(bot, "TREND_WORKFLOW_PUBLIC_ENABLED", False)
    key = bot.trend_video_pending_key("u4")
    bot.USER_PENDING.pop(key, None)
    bot.set_trend_video_flow_pending("u4")
    pending = bot.get_trend_video_flow_pending("u4")
    assert pending and pending["pending_action"] == "trend_video_flow"
    assert bot.clear_trend_video_flow_pending("u4") is True
    bot.set_trend_video_flow_pending("u4")
    bot.USER_PENDING[key]["created_at_ts"] = 0
    assert bot.get_trend_video_flow_pending("u4") is None
    assert key not in bot.USER_PENDING
    confirm_key = bot.trend_workflow_confirm_pending_key("u4")
    bot.USER_PENDING.pop(confirm_key, None)
    bot.set_trend_workflow_confirm_pending("u4", "affiliate AI tool cho người mới", "wf_1")
    confirm_pending = bot.get_trend_workflow_confirm_pending("u4")
    assert confirm_pending and confirm_pending["pending_action"] == "trend_workflow_confirm"
    assert int(confirm_pending["cost_total"]) == 70
    assert bot.clear_trend_workflow_confirm_pending("u4") is True
    bot.set_trend_workflow_confirm_pending("u4", "affiliate AI tool cho người mới", "wf_2")
    bot.USER_PENDING[confirm_key]["created_at_ts"] = 0
    assert bot.get_trend_workflow_confirm_pending("u4") is None

    sections = bot.trend_video_flow_sections("affiliate AI tool cho người mới")
    assert len(sections) >= 6
    assert all(len(section) <= 3900 for section in sections)
    joined = "\n".join(sections).lower()
    for marker in [
        "10 hook",
        "script 15",
        "script 30",
        "script 60",
        "storyboard",
        "prompt tạo ảnh",
        "prompt tạo video",
        "tts",
        "nhạc",
        "caption",
        "cta",
        "public image/video: off",
        "không tạo ảnh-video thật",
    ]:
        assert marker in joined
    assert "admin preview / content-only / no xu deducted" in joined
    billed_sections = bot.trend_video_flow_sections("affiliate AI tool cho người mới", billing_note=bot.trend_workflow_billed_note(70))
    billed_joined = "\n".join(billed_sections).lower()
    assert "70 xu" in billed_joined
    assert "tạo ảnh 50 xu" in billed_joined
    assert "tạo video 300 xu" in billed_joined
    assert "Bot chưa trừ Xu" in bot.TREND_VIDEO_WORKFLOW_PUBLIC_OFF_MESSAGE or "thử nghiệm nội bộ" in bot.TREND_VIDEO_WORKFLOW_PUBLIC_OFF_MESSAGE
    assert bot.TREND_VIDEO_WORKFLOW_PUBLIC_OFF_MESSAGE == "🧪 Tính năng tạo video theo trend đang thử nghiệm nội bộ, chưa mở công khai."
    breakdown = bot.trend_workflow_content_cost_breakdown()
    assert breakdown["trend_analysis"] == 20
    assert breakdown["script_storyboard"] == 30
    assert breakdown["prompt_pack"] == 20
    assert breakdown["total"] == 70
    assert breakdown["image_separate"] == 50
    assert breakdown["video_separate"] == 300
    assert "70 Xu" in bot.trend_workflow_content_confirm_text("affiliate AI", 200)
    assert "tvflow|confirm_content" in source
    assert "tvflow|cancel_content" in source

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    try:
        bot.init_db()
        conn = bot.db_connect()
        try:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(trend_workflow_outputs)").fetchall()}
        finally:
            conn.close()
        assert {
            "user_id",
            "workflow_id",
            "selected_scene",
            "image_prompt",
            "video_prompt",
            "generated_image_url",
            "created_at",
        }.issubset(cols)
        workflow_id = bot.trend_workflow_id("u3")
        scenes = bot.trend_video_scene_outputs("affiliate AI tool")
        bot.save_trend_workflow_outputs("u3", workflow_id, scenes)
        bot.cache_trend_workflow("u3", workflow_id, scenes)
        output = bot.trend_workflow_output_for_user("u3", 1)
        assert output
        assert output["workflow_id"] == workflow_id
        assert "image_prompt" in output and output["image_prompt"]
        bot.update_trend_workflow_generated_image(
            workflow_id=workflow_id,
            scene_index=1,
            user_id="u3",
            image_url="https://example.com/image.png",
            job_id=123,
        )
        bot.LAST_TREND_VIDEO_WORKFLOWS.pop("u3", None)
        output = bot.trend_workflow_output_for_user("u3", 1)
        assert output["generated_image_url"] == "https://example.com/image.png"
        assert int(output["shopaikey_job_id"]) == 123
        credits_before, _, _ = bot.get_user("u_billing", "Billing Test")
        charge = bot.spend_fixed_credit_info(
            "u_billing",
            breakdown["total"],
            "trend_workflow_content",
            "unit test",
            apply_member_discount_flag=False,
        )
        assert charge["ok"] is True
        assert int(charge["final_cost"]) == 70
        credits_after, _, _ = bot.get_user("u_billing")
        assert int(credits_before) - int(credits_after) == 70
        bot.record_trend_workflow_billing_event("u_billing", workflow_id, "deduct", 70, int(credits_before), int(credits_after), "unit")
        refunded = bot.refund_charged_credit("u_billing", 70, "trend_workflow_refund", workflow_id, "unit refund", True)
        assert refunded is True
        credits_refunded, _, _ = bot.get_user("u_billing")
        assert int(credits_refunded) == int(credits_before)
        bot.record_trend_workflow_billing_event("u_billing", workflow_id, "refund", 70, int(credits_after), int(credits_refunded), "unit")
        conn = bot.db_connect()
        try:
            events = conn.execute("SELECT event_type, amount_xu FROM shopaikey_billing_events WHERE user_id=? ORDER BY id", ("u_billing",)).fetchall()
        finally:
            conn.close()
        assert ("deduct", 70) in [(row[0], int(row[1])) for row in events]
        assert ("refund", 70) in [(row[0], int(row[1])) for row in events]
    finally:
        bot.LAST_TREND_VIDEO_WORKFLOWS.pop("u3", None)
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_create_media_menu_and_quick_pending_guards(monkeypatch):
    source = bot_source_text()
    helper_source = source_between(source, "def create_media_public_off_message", "def shopaikey_preview_final_cost")
    quick_source = source_between(source, "async def cmd_create_media", "async def cmd_tool_test_workflow_image")
    message_source = source_between(source, "async def handle_message", "TELEGRAM_STARTUP_ERROR =")

    assert 'CommandHandler("create_media", cmd_create_media)' in source
    assert 'CommandHandler("quick_image_test", cmd_quick_image_test)' in source
    assert 'CommandHandler("quick_video_test", cmd_quick_video_test)' in source
    assert 'CallbackQueryHandler(handle_create_media_callback, pattern=r"^create_media\\|")' in source
    assert "🎨 TOAN AAS Media Creator" in helper_source
    assert 'InlineKeyboardButton("🎨 Media Creator", callback_data="menu|create_media")' not in source_between(source, "def main_menu_keyboard", "def language_choice_text")
    assert 'InlineKeyboardButton("📞 Liên hệ admin", callback_data="menu|support")' in source
    assert 'InlineKeyboardButton("🎬 Tạo nội dung / Video", callback_data="menu|main_video")' in source
    assert 'InlineKeyboardButton("🖼 Hình ảnh", callback_data="menu|main_image")' in source
    assert 'InlineKeyboardButton("🖼 Tạo ảnh AI nhanh", callback_data="create_media|quick_image")' in source
    assert 'InlineKeyboardButton("🎞 Tạo video nhanh", callback_data="create_media|quick_video")' in source
    assert 'InlineKeyboardButton("🎬 Tạo video theo trend", callback_data="create_media|trend")' in source_between(source, "def main_video_keyboard", "def main_ai_keyboard")
    assert 'InlineKeyboardButton("📝 Viết hook/script/caption", callback_data="menu|hint_film")' in source_between(source, "def main_video_keyboard", "def main_ai_keyboard")
    assert "create_media_open_text(query.from_user.id)" in source
    assert "create_media_open_text(uid)" in quick_source
    for callback_data in [
        "create_media|quick_image",
        "create_media|quick_video",
        "create_media|main",
        "create_media|cancel",
    ]:
        assert callback_data in helper_source
    create_media_keyboard_source = source_between(source, "def create_media_menu_keyboard", "def create_media_pricing_text")
    assert "create_media|trend" not in create_media_keyboard_source
    assert "create_media|pricing" not in create_media_keyboard_source
    assert "support_contact_text()" in source
    assert "clear_pending_start_notice(uid)" in source_between(source, "async def cmd_start", "async def cmd_menu")
    assert "Mở menu chính bên dưới" in helper_source
    assert 'IMAGE_BASE_COST_XU = env_int("IMAGE_BASE_COST_XU", 50)' in source
    assert 'VIDEO_BASE_COST_XU = env_int("VIDEO_BASE_COST_XU", 300)' in source
    assert 'MEDIA_PRICE_MULTIPLIER = env_int("MEDIA_PRICE_MULTIPLIER", 2)' in source
    assert 'IMAGE_LOW_COST_XU = env_int("IMAGE_LOW_COST_XU"' in source
    assert 'VIDEO_LOW_COST_XU = env_int("VIDEO_LOW_COST_XU"' in source
    assert 'WORKFLOW_TREND_ANALYSIS_COST_XU = env_int("WORKFLOW_TREND_ANALYSIS_COST_XU", 20)' in source
    assert 'WORKFLOW_SCRIPT_STORYBOARD_COST_XU = env_int("WORKFLOW_SCRIPT_STORYBOARD_COST_XU", 30)' in source
    assert 'WORKFLOW_PROMPT_PACK_COST_XU = env_int("WORKFLOW_PROMPT_PACK_COST_XU", 20)' in source
    assert "Tính năng này đang thử nghiệm nội bộ, chưa mở công khai" in helper_source
    assert "Giá chính thức được gom về một nơi duy nhất" in helper_source
    assert "set_quick_media_pending(uid, action)" in source
    assert 'set_quick_media_pending(uid, "quick_image_prompt")' not in source  # action is centralized through start/callback helpers.
    assert "quick_image_prompt" in source and "quick_video_prompt" in source
    assert "handle_quick_media_pending_text(update, context)" in message_source
    assert message_source.index("handle_quick_media_pending_text(update, context)") < message_source.index("is_probable_media_tags_text")
    assert "clear_quick_media_pending(uid)" in quick_source
    assert "clear_media_creator_pending_states(uid)" in source_between(source, "async def cmd_cancel", "async def cmd_create_media")
    assert "run_quick_image_admin_smoke" in quick_source
    assert "run_quick_video_admin_smoke" in quick_source
    assert "shopaikey_image_generate(prompt)" in quick_source
    assert "shopaikey_video_create_smoke_test(model, prompt)" in quick_source
    assert "spend_fixed_credit_info" not in quick_source
    assert "deduct_dynamic_credit" not in quick_source
    assert "add_credit(" not in quick_source
    assert "PAYOS" not in quick_source.upper()
    assert "USER_JOB_LOCK_MESSAGE" in quick_source
    assert "/quick_image_test" in quick_source and "/quick_video_test" in quick_source
    assert "No Xu deducted" in quick_source or "Không trừ Xu" in quick_source
    assert "Quick media menu: <code>enabled/admin-only</code>" in source
    assert "Pricing mode: <code>{html.escape(pricing['billing_mode'])}</code>" in source
    assert "Price table source: <code>{html.escape(pricing['price_table_source'])}</code>" in source

    monkeypatch.setattr(bot, "MEDIA_PRICE_MULTIPLIER", 2)
    monkeypatch.setattr(bot, "IMAGE_LOW_PROVIDER_COST_XU", 161)
    monkeypatch.setattr(bot, "VIDEO_LOW_PROVIDER_COST_XU", 327)
    monkeypatch.setattr(bot, "IMAGE_LOW_COST_XU", 321)
    monkeypatch.setattr(bot, "VIDEO_LOW_COST_XU", 654)
    monkeypatch.setattr(bot, "IMAGE_STANDARD_COST_XU", 777)
    monkeypatch.setattr(bot, "IMAGE_HIGH_COST_XU", 888)
    monkeypatch.setattr(bot, "VIDEO_STANDARD_COST_XU", 999)
    monkeypatch.setattr(bot, "VIDEO_HIGH_COST_XU", 1111)
    monkeypatch.setattr(bot, "VIDEO_PREMIUM_COST_XU", 2222)
    monkeypatch.setattr(bot, "WORKFLOW_TREND_ANALYSIS_COST_XU", 7)
    monkeypatch.setattr(bot, "WORKFLOW_SCRIPT_STORYBOARD_COST_XU", 8)
    monkeypatch.setattr(bot, "WORKFLOW_PROMPT_PACK_COST_XU", 9)
    pricing = bot.media_workflow_pricing_payload()
    assert pricing["billing_mode"] == "tiered_media_pricing"
    assert pricing["image_tiers"]["low"]["cost"] == 321
    assert pricing["image_tiers"]["standard"]["cost"] == 777
    assert pricing["image_tiers"]["high"]["cost"] == 888
    assert pricing["video_tiers"]["low"]["cost"] == 654
    assert pricing["video_tiers"]["standard"]["cost"] == 999
    assert pricing["video_tiers"]["high"]["cost"] == 1111
    assert pricing["video_tiers"]["premium"]["cost"] == 2222
    assert pricing["quick_image_cost"] == 321
    assert pricing["quick_video_cost"] == 654
    assert "321 Xu" not in bot.create_media_pricing_text()
    assert "654 Xu" not in bot.create_media_pricing_text()
    pricing_text = "\n".join(bot.pricing_main_lines())
    assert "C. Hình ảnh AI" in pricing_text
    assert "D. Video AI" in pricing_text
    assert "E. Workflow nội dung theo trend" in pricing_text
    assert "Ảnh tiết kiệm: <b>321 Xu</b>" in pricing_text
    assert "Ảnh tiêu chuẩn: <b>777 Xu</b>" in pricing_text
    assert "Video tiết kiệm: <b>654 Xu</b>" in pricing_text
    assert "Video premium/admin-only: <b>2222 Xu</b>" in pricing_text
    assert "Tổng gói content-only: <b>24 Xu</b>" in pricing_text
    assert "provider cost" not in pricing_text.lower()
    assert "tiered_media_pricing" in pricing_text
    start_labels = [button.text for row in bot.localized_main_menu_keyboard(False, "vi").inline_keyboard for button in row]
    assert "🎨 Media Creator" not in start_labels
    assert "🎬 Tạo nội dung / Video" in start_labels
    assert "🖼 Hình ảnh" in start_labels
    assert "🎞 Video" not in start_labels
    assert "📞 Liên hệ admin" in start_labels
    assert "💳 Bảng giá" in start_labels
    for keyboard in [
        bot.main_menu_keyboard(False),
        bot.localized_main_menu_keyboard(False, "vi"),
        bot.localized_main_menu_keyboard(False, "en"),
        bot.localized_main_menu_keyboard(False, "zh"),
    ]:
        voice_rows = [row for row in keyboard.inline_keyboard if any(button.callback_data == "menu|main_audio" for button in row)]
        assert voice_rows and len(voice_rows[0]) == 2
    image_labels = [button.text for row in bot.main_image_keyboard("vi").inline_keyboard for button in row]
    assert "🖼 Tạo ảnh AI nhanh" in image_labels
    assert "💳 Xem bảng giá" not in image_labels
    assert "💰 Xem giá" not in image_labels
    assert "📞 Liên hệ admin" not in image_labels
    video_buttons = [button for row in bot.main_video_keyboard("vi").inline_keyboard for button in row]
    assert any(button.text == "🎞 Tạo video nhanh" and button.callback_data == "create_media|quick_video" for button in video_buttons)
    assert any(button.text == "🎬 Tạo video theo trend" and button.callback_data == "create_media|trend" for button in video_buttons)
    video_labels = [button.text for button in video_buttons]
    assert "🖼➡️🎞 Tạo video từ ảnh" in video_labels
    assert "✍️ Tạo prompt video" in video_labels
    assert "📝 Viết hook/script/caption" in video_labels
    assert "💳 Xem bảng giá" not in video_labels
    assert "💰 Xem giá" not in video_labels
    assert "📞 Liên hệ admin" not in video_labels
    docs_labels = [button.text for row in bot.main_docs_keyboard("vi").inline_keyboard for button in row]
    assert "💰 Xem giá" not in docs_labels
    topup_labels = [button.text for row in bot.main_topup_keyboard("vi").inline_keyboard for button in row]
    assert "💰 Xem giá" not in topup_labels
    guide_labels = [button.text for row in bot.main_guide_keyboard("vi").inline_keyboard for button in row]
    assert "💰 Bảng giá" not in guide_labels
    create_media_labels = [button.text for row in bot.create_media_menu_keyboard().inline_keyboard for button in row]
    assert "🖼 Tạo ảnh nhanh" in create_media_labels
    assert "🎞 Tạo video nhanh" in create_media_labels
    assert "🔙 Quay lại menu chính" in create_media_labels
    assert "📞 Liên hệ admin" not in create_media_labels
    assert "📌 Xem giá" not in create_media_labels
    assert "🎬 Tạo video theo trend" not in create_media_labels
    monkeypatch.setattr(bot, "SUPPORT_TELEGRAM_URL", "")
    assert "Admin chưa cấu hình link hỗ trợ" in bot.support_contact_text()

    key = bot.quick_media_pending_key("u6")
    bot.USER_PENDING.pop(key, None)
    bot.set_quick_media_pending("u6", "quick_image_prompt")
    pending = bot.get_quick_media_pending("u6")
    assert pending and pending["pending_action"] == "quick_image_prompt"
    assert bot.clear_quick_media_pending("u6") is True
    bot.set_quick_media_pending("u6", "quick_video_prompt")
    bot.USER_PENDING[key]["created_at_ts"] = 0
    assert bot.get_quick_media_pending("u6") is None
    assert key not in bot.USER_PENDING
    bot.set_quick_media_pending("u7", "quick_image_prompt")
    assert bot.create_media_open_text("u7").startswith("ℹ️ Đã hủy thao tác cũ")
    assert bot.get_quick_media_pending("u7") is None
    bot.set_trend_video_flow_pending("u7")
    assert bot.create_media_open_text("u7").startswith("ℹ️ Đã hủy thao tác cũ")
    assert bot.get_trend_video_flow_pending("u7") is None
    bot.set_quick_media_pending("u8", "quick_video_prompt")
    bot.set_trend_video_flow_pending("u8")
    assert bot.create_media_open_text("u8").startswith("ℹ️ Đã hủy thao tác cũ")
    assert bot.get_quick_media_pending("u8") is None
    assert bot.get_trend_video_flow_pending("u8") is None
    bot.set_quick_media_pending("u9", "quick_image_prompt")
    bot.set_trend_video_flow_pending("u9")
    assert bot.clear_pending_start_notice("u9").startswith("❌ Đã hủy thao tác đang chờ")
    assert bot.get_quick_media_pending("u9") is None
    assert bot.get_trend_video_flow_pending("u9") is None


def test_workflow_image_to_video_admin_guard_and_assets(monkeypatch):
    source = bot_source_text()
    command_source = source_between(source, "async def cmd_tool_test_workflow_image_to_video", "async def cmd_image_tools")
    callback_source = source_between(source, "async def handle_trend_video_flow_callback", "async def cmd_tool_test_workflow_image")
    create_source = source_between(source, "async def shopaikey_workflow_image_to_video_create", "async def shopaikey_video_create_smoke_test")

    assert 'CommandHandler("tool_test_wf_i2v", cmd_tool_test_workflow_image_to_video)' in source
    assert "workflow_image_assets" in source
    assert "LAST_WORKFLOW_IMAGES" in source
    assert "metadata" in source and '"images"' in source
    assert "shopaikey_workflow_image_to_video_create" in command_source
    assert "auto_poll_shopaikey_video_job" in command_source
    assert "No Xu deducted" in command_source
    assert "SHOPAIKEY_PUBLIC_VIDEO_ENABLED" in callback_source
    assert "Tính năng tạo video từ ảnh đang thử nghiệm nội bộ" in callback_source
    assert "spend_fixed_credit_info" not in command_source
    assert "deduct_dynamic_credit" not in command_source
    assert "add_credit(" not in command_source
    assert "PAYOS" not in command_source.upper()
    assert "metadata.images" not in create_source  # Keep provider response/detail free of raw image URL wording.

    payload = bot.shopaikey_workflow_image_to_video_payload(
        "veo3.1-fast",
        "https://example.com/workflow-image.png",
        "TOAN AAS workflow image to video test",
    )
    assert payload["model"] == "veo3.1-fast"
    assert payload["metadata"]["images"] == ["https://example.com/workflow-image.png"]
    assert payload["metadata"]["aspect_ratio"] == "9:16"
    assert payload["metadata"]["enhance_prompt"] is False
    assert payload["metadata"]["enable_upsample"] is False

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_JOB_LOCK_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_JOB_LOCK_ENABLED", True)
    try:
        bot.LAST_WORKFLOW_IMAGES.pop("u5", None)
        bot.init_db()
        conn = bot.db_connect()
        try:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(workflow_image_assets)").fetchall()}
        finally:
            conn.close()
        assert {
            "user_id",
            "image_url",
            "prompt_preview",
            "workflow_id",
            "scene_index",
            "source",
            "shopaikey_job_id",
            "created_at",
        }.issubset(cols)
        bot.save_latest_workflow_image(
            "u5",
            "https://example.com/workflow-image.png",
            prompt="very long workflow prompt " * 20,
            workflow_id="workflow_1",
            scene_index=2,
            source="unit_test",
            job_id=44,
        )
        asset = bot.latest_workflow_image_for_user("u5")
        assert asset
        assert asset["image_url"] == "https://example.com/workflow-image.png"
        assert asset["workflow_id"] == "workflow_1"
        assert int(asset["scene_index"]) == 2
        assert len(asset["prompt_preview"]) <= 120
        video_job_id = bot.create_shopaikey_job("u5", "chat", "video", model="veo3.1-fast", prompt="workflow image to video", status="QUEUED", admin_only=True, xu_cost_planned=0)
        active = bot.shopaikey_active_job_for_user("u5", "video")
        assert active and int(active["id"]) == video_job_id
        bot.update_shopaikey_job(job_id=video_job_id, status="SUCCESS", finished_at=bot.now_text())
        assert bot.shopaikey_active_job_for_user("u5", "video") is None
    finally:
        bot.LAST_WORKFLOW_IMAGES.pop("u5", None)
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_shopaikey_status_falls_back_to_api_debug_events(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    try:
        bot.init_db()
        bot.record_api_debug(
            "shopaikey",
            "usage",
            "PASS",
            200,
            "http=200; latency_ms=111; total=16; used=0.3; remaining=15.7; remaining_percent=98.12; group=cheap,gemini,claude_code; error_class=-",
        )
        usage = bot.shopaikey_last_usage_snapshot()
        assert usage["total"] == "16"
        assert usage["remaining"] == "15.7"
        assert usage["remaining_percent"] == "98.12"
        assert usage["group_name"] == "cheap,gemini,claude_code"
        assert "98.12%" in bot.shopaikey_usage_summary_text(usage)

        bot.record_api_debug(
            "shopaikey",
            "tool_test_shopaikey",
            "PASS",
            200,
            "model=gpt-4o-mini; http=200; latency_ms=222; error_class=-; attempts=gpt-4o-mini=PASS",
        )
        chat = bot.shopaikey_chat_status_snapshot()
        assert chat["status"] == "PASS"
        assert chat["model"] == "gpt-4o-mini"
        assert "PASS" in bot.shopaikey_chat_status_text()
        bot.record_api_debug(
            "shopaikey",
            "tool_test_shopaikey_tts",
            "PASS",
            200,
            "model=tts-1/alloy; http=200; output_sent=yes",
        )
        assert bot.shopaikey_tts_status_snapshot()["status"] == "PASS"
        bot.record_api_debug(
            "shopaikey",
            "tool_test_shopaikey_image",
            "PASS",
            200,
            "model=nano-banana; http=200; size=768x1344; output_sent=yes",
        )
        assert bot.shopaikey_image_status_snapshot()["status"] == "PASS"
        bot.record_api_debug(
            "shopaikey",
            "tool_test_shopaikey_video",
            "PASS_SUBMITTED",
            200,
            "model=veo3.1-fast; http=200; task_id=task_1; provider_status=queued",
        )
        assert bot.shopaikey_video_status_snapshot()["status"] == "PASS_SUBMITTED"
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_generation_waiting_duplicate_and_guidance_helpers():
    bot.GENERATION_PENDING_JOBS.clear()
    try:
        assert "Đang tạo ảnh" in bot.get_generation_wait_text("image")
        assert "Đang tạo video" in bot.get_generation_wait_text("video")
        assert "Đang tạo giọng nói" in bot.get_generation_wait_text("tts")
        assert "Đang tìm trend" in bot.get_generation_wait_text("trend")

        prompt_key = bot.normalize_generation_prompt("ShopAIKey image smoke test")
        assert bot.is_duplicate_pending_job("u1", "shopaikey_image", prompt_key) is None
        bot.start_generation_pending_job("u1", "shopaikey_image", prompt_key, provider="shopaikey", xu_cost=0, command="/tool_test_shopaikey_image")
        duplicate = bot.is_duplicate_pending_job("u1", "shopaikey_image", prompt_key)
        assert duplicate
        assert duplicate["xu_cost"] == 0
        bot.finish_generation_pending_job("u1", "shopaikey_image", prompt_key, "PASS")
        assert bot.is_duplicate_pending_job("u1", "shopaikey_image", prompt_key) is None

        trend_lines = "\n".join(bot.build_trend_prompt_suggestions({
            "title": "AI automation for small shops",
            "summary": "SMB owners are testing AI workflows.",
            "platform": "tiktok",
            "niche": "AI tools",
        }))
        assert "Bạn có thể copy" in trend_lines
        assert "Gợi ý video tiếp theo" in trend_lines
        assert "Risk/copyright" in trend_lines
    finally:
        bot.GENERATION_PENDING_JOBS.clear()


def test_critical_sales_ready_commands_remain_registered():
    source = bot_source_text()
    handler_lines = [line.strip() for line in source.splitlines() if "CommandHandler(" in line]
    literal_commands = re.findall(r'CommandHandler\("([^"]+)"', source)
    assert literal_commands
    assert all(len(command) <= 32 for command in literal_commands), [command for command in literal_commands if len(command) > 32]
    expected_handlers = {
        "start": "cmd_start",
        "language": "cmd_language",
        "lang": "cmd_language",
        "naptien": "cmd_naptien",
        "thucong": "cmd_thanhtoan_thucong",
        "duyet": "cmd_duyet",
        "pending": "cmd_pending",
        "sales_ready": "cmd_sales_ready",
        "backup_db": "cmd_backup_db",
        "data_status": "cmd_data_status",
        "providers": "cmd_providers",
        "film": "cmd_film",
        "growth_ai": "cmd_growth_ai",
        "campaign_report": "cmd_campaign_report",
        "promo": "cmd_promo",
        "khuyenmai": "cmd_promo_guide",
        "gift": "cmd_gift",
        "nhanqua": "cmd_gift",
        "trial_status": "cmd_trial_status",
        "image_to_pdf": "cmd_image_to_pdf",
        "translate_voice": "cmd_translate_voice",
        "local_status": "cmd_local_status",
        "local_worker_ping": "cmd_local_worker_ping",
        "tool_test_ffmpeg_local": "cmd_tool_test_ffmpeg_local",
        "orchestrator_status": "cmd_orchestrator_status",
        "provider_matrix": "cmd_provider_matrix",
        "tool_test_openrouter": "cmd_tool_test_openrouter",
        "tool_test_shopaikey": "cmd_tool_test_shopaikey",
        "tool_test_shopaikey_tts": "cmd_tool_test_shopaikey_tts",
        "tool_test_shopaikey_image": "cmd_tool_test_shopaikey_image",
        "tool_test_workflow_image": "cmd_tool_test_workflow_image",
        "tool_test_wf_i2v": "cmd_tool_test_workflow_image_to_video",
        "tool_test_shopaikey_video": "cmd_tool_test_shopaikey_video",
        "shopaikey_video_job": "cmd_shopaikey_video_job",
        "shopaikey_image": "cmd_shopaikey_image_public",
        "shopaikey_video": "cmd_shopaikey_video_public",
        "shopaikey_video_from_image": "cmd_shopaikey_video_from_image_public",
        "trend_video_flow": "cmd_trend_video_flow",
        "create_media": "cmd_create_media",
        "quick_image_test": "cmd_quick_image_test",
        "quick_video_test": "cmd_quick_video_test",
        "shopaikey_status": "cmd_shopaikey_status",
        "shopaikey_usage": "cmd_shopaikey_usage",
        "trial_bonus_status": "cmd_trial_bonus_status",
    }
    for command, handler in expected_handlers.items():
        assert any(f'CommandHandler("{command}"' in line and handler in line for line in handler_lines), command


def test_naptien_does_not_enable_manual_bill_state_by_default():
    source = bot_source_text()
    cmd_naptien_source = source_between(source, "async def cmd_naptien", "async def cmd_thanhtoan_thucong")
    assert "USER_BILL_STATE.pop(uid, None)" in cmd_naptien_source
    assert "set_manual_bill_state" not in cmd_naptien_source
    assert 'callback_data=payos_package_callback_data("50k", uid)' in cmd_naptien_source
    assert 'callback_data=manual_package_callback_data("manual_custom", uid)' in cmd_naptien_source


def test_sales_readiness_requires_payos_checkout_and_real_payment_marker(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "PAYOS_CLIENT_ID", "payos-client")
    monkeypatch.setattr(bot, "PAYOS_API_KEY", "payos-api")
    monkeypatch.setattr(bot, "PAYOS_CHECKSUM_KEY", "payos-checksum")
    monkeypatch.setattr(bot, "GEMINI_API_KEY", "gemini-key")
    try:
        bot.init_db()
        bot.set_system_setting("payos_debug_create_status", "PASS", "test", "pytest")
        bot.set_system_setting("payos_debug_create_checkout_url", "https://pay.payos.vn/test", "test", "pytest")
        payload = bot.sales_readiness_payload()
        assert payload["payos_debug_create"]["status"] == "PASS"
        assert payload["payos_debug_create"]["checkout_url"] == "https://pay.payos.vn/test"
        assert payload["payos_real_test"]["status"] == "NOT_TESTED"
        assert payload["status"] == "BETA READY"
        assert "SALES READY chỉ bật" in payload["note"]

        bot.set_system_setting("payos_real_payment_test_status", "PASS", "real payment confirmed", "pytest")
        payload = bot.sales_readiness_payload()
        assert payload["payos_real_test"]["status"] == "PASS"
        assert payload["status"] == "SALES READY"
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_topup_keyboard_preserves_package_callbacks():
    keyboard = bot.build_topup_keyboard(123)
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "payos_pkg|50k|123" in callbacks
    assert "payos_pkg|100k|123" in callbacks
    assert "payos_pkg|200k|123" in callbacks
    assert "menu|billing" in callbacks


def test_customer_guide_is_public_and_policy_aligned():
    guide_index = bot.guide_index_text()
    guide_credit = bot.guide_section_text("credits")
    keyboard = bot.main_menu_keyboard(False)
    button_texts = [button.text for row in keyboard.inline_keyboard for button in row]

    assert "/huongdan 1" in guide_index
    assert "📘 Hướng Dẫn" in button_texts
    assert "50.000đ → 500 Xu + 30 Xu Launch Bonus" in guide_credit
    assert "100.000đ → 1.000 Xu + 50 Xu Launch Bonus" in guide_credit
    assert bot.package_launch_bonus_xu(50000) == 30
    assert bot.package_launch_bonus_xu(100000) == 50


def test_launch_bonus_preview_once_per_user_package(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    try:
        bot.init_db()
        conn = bot.db_connect()
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(launch_bonus_redemptions)").fetchall()}
            assert {"base_xu", "bonus_xu", "launch_bonus_xu", "note"}.issubset(columns)
            payos_columns = {row[1] for row in conn.execute("PRAGMA table_info(payos_orders)").fetchall()}
            assert {"package_amount_vnd", "base_xu", "launch_bonus_xu"}.issubset(payos_columns)

            fifty = bot.calculate_package_credit_for_user("u1", 50000, conn=conn)
            assert fifty["base_xu"] == 500
            assert fifty["launch_bonus_xu"] == 30
            assert fifty["launch_bonus_eligible"] is True
            assert fifty["launch_bonus_available"] == 30
            bot.create_order("order-preview-50", "u1", 50000, fifty["total_xu"], base_xu=fifty["base_xu"], launch_bonus_xu=fifty["launch_bonus_xu"], package_amount_vnd=50000)
            row = conn.execute("SELECT xu, package_amount_vnd, base_xu, launch_bonus_xu FROM payos_orders WHERE order_code='order-preview-50'").fetchone()
            assert row == (530, 50000, 500, 30)
            assert bot.redeem_launch_bonus_for_order(conn, "u1", "order-50", 50000) == 30
            conn.commit()
            fifty_repeat = bot.calculate_package_credit_for_user("u1", 50000, conn=conn)
            assert fifty_repeat["launch_bonus_xu"] == 0
            assert fifty_repeat["launch_bonus_eligible"] is False

            first = bot.calculate_package_credit_for_user("u1", 100000, conn=conn)
            assert first["base_xu"] == 1000
            assert first["launch_bonus_xu"] == 50
            assert first["launch_bonus_eligible"] is True
            assert first["launch_bonus_available"] == 50
            bot.create_order("order-preview", "u1", 100000, first["total_xu"], base_xu=first["base_xu"], launch_bonus_xu=first["launch_bonus_xu"], package_amount_vnd=100000)
            row = conn.execute("SELECT xu, package_amount_vnd, base_xu, launch_bonus_xu FROM payos_orders WHERE order_code='order-preview'").fetchone()
            assert row == (1050, 100000, 1000, 50)

            assert bot.redeem_launch_bonus_for_order(conn, "u1", "order-1", 100000) == 50
            conn.commit()
            repeat = bot.calculate_package_credit_for_user("u1", 100000, conn=conn)
            assert repeat["launch_bonus_xu"] == 0
            assert repeat["launch_bonus_eligible"] is False
            assert bot.redeem_launch_bonus_for_order(conn, "u1", "order-dup", 100000) == 0

            other_package = bot.calculate_package_credit_for_user("u1", 200000, conn=conn)
            assert other_package["launch_bonus_xu"] == 150
        finally:
            conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


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
    assert bot.calculate_dynamic_cost("chat", 0) == bot.CHAT_SHORT_COST
    assert bot.calculate_dynamic_cost("download", 0) == bot.VIDEO_DOWNLOAD_MIN_COST
    assert bot.calculate_audio_cost(1) == bot.AUDIO_MIN_COST
    assert bot.calculate_video_download_cost(1) == bot.VIDEO_DOWNLOAD_MIN_COST
    assert bot.estimate_text_mb("") == 1
    assert bot.estimate_text_mb("x" * bot.CHAT_TEXT_MB_CHARS) == 1
    assert bot.estimate_text_mb("x" * (bot.CHAT_TEXT_MB_CHARS + 1)) == 2
    assert bot.calculate_chat_pro_cost("short") == bot.CHAT_PRO_STANDARD_COST
    assert bot.calculate_chat_pro_cost("short", tier="deep") == bot.CHAT_PRO_DEEP_COST
    assert bot.calculate_chat_pro_cost("short", model_level="sonnet") == bot.CHAT_PRO_DEEP_COST
    assert bot.calculate_chat_pro_cost("x" * (bot.CHAT_TEXT_MB_CHARS * 20)) == bot.CHAT_PRO_MAX_COST
    assert bot.calculate_film_cost() == bot.VIDEO_BASIC_COST
    assert bot.calculate_film_cost(episodes=3, scenes=5) == 400
    assert bot.calculate_film_cost(episodes=1, scenes=10) == 300
    assert bot.calculate_film_cost(tier="pro") == bot.VIDEO_PRO_COST
    assert bot.calculate_film_cost(tier="series") == bot.VIDEO_SERIES_COST
    assert bot.apply_discount(0, 100) == (100, 0.0)
    assert bot.apply_discount(5000, 100) == (90, 0.10)
    assert bot.apply_discount(20000, 100) == (80, 0.20)


def test_chat_provider_router(monkeypatch):
    monkeypatch.setattr(bot, "gemini_client", object())
    monkeypatch.setattr(bot, "openai_client", None)
    provider = bot.choose_chat_provider("pro", "auto")
    assert provider["ready"] is True
    assert provider["provider"] == "gemini"

    provider = bot.choose_chat_provider("pro", "openai")
    assert provider["ready"] is False
    assert provider["provider"] == "openai"

    provider = bot.choose_chat_provider("deep", "sonnet")
    assert provider["ready"] is False
    assert provider["provider"] == "claude"


def test_payos_signature_verification(monkeypatch):
    monkeypatch.setattr(bot, "PAYOS_CHECKSUM_KEY", "checksum-test")
    data = {"orderCode": 123, "amount": 10000, "status": "PAID"}
    raw = "&".join(f"{k}={data[k]}" for k in sorted(data.keys()))
    sig = hmac.new(b"checksum-test", raw.encode("utf-8"), hashlib.sha256).hexdigest()
    assert bot.verify_payos_signature(data, sig)
    assert not bot.verify_payos_signature(data, "bad-signature")


def test_payos_create_payment_signature_data_order(monkeypatch):
    monkeypatch.setattr(bot, "PAYOS_CHECKSUM_KEY", "checksum-test")
    payload = {
        "amount": 50000,
        "cancelUrl": "https://bot-production-2dd7.up.railway.app/landing",
        "description": "AAS50K",
        "orderCode": 178039665,
        "returnUrl": "https://bot-production-2dd7.up.railway.app/landing",
    }
    expected = (
        "amount=50000"
        "&cancelUrl=https://bot-production-2dd7.up.railway.app/landing"
        "&description=AAS50K"
        "&orderCode=178039665"
        "&returnUrl=https://bot-production-2dd7.up.railway.app/landing"
    )
    signature, raw = bot.sign_payos_payment_request(payload)
    assert raw == expected
    assert signature == hmac.new(b"checksum-test", expected.encode("utf-8"), hashlib.sha256).hexdigest()
    assert bot.get_payos_create_signature_variant() == "standard_sorted"
    assert bot.PAYOS_DEBUG_SIGNATURE_VARIANTS == ("standard_sorted",)
    assert bot.build_payos_signature_data(payload, "faq_order") == (
        "amount=50000"
        "&orderCode=178039665"
        "&description=AAS50K"
        "&returnUrl=https://bot-production-2dd7.up.railway.app/landing"
        "&cancelUrl=https://bot-production-2dd7.up.railway.app/landing"
    )
    assert bot.build_payos_signature_data(payload, "payload_order") == (
        "orderCode=178039665"
        "&amount=50000"
        "&description=AAS50K"
        "&cancelUrl=https://bot-production-2dd7.up.railway.app/landing"
        "&returnUrl=https://bot-production-2dd7.up.railway.app/landing"
    )
    assert bot.build_payos_signature_data(payload, "sorted_all_payload_keys") == expected


def test_resolve_payment_package_arg_for_payos_debug():
    assert bot.resolve_payment_package_arg("10k")[0] == "10k"
    assert bot.resolve_payment_package_arg("10000")[0] == "10k"
    assert bot.resolve_payment_package_arg("50k")[0] == "50k"
    assert bot.resolve_payment_package_arg("50000")[0] == "50k"
    assert bot.resolve_payment_package_arg(None)[0] == "50k"
    assert bot.resolve_payment_package_arg("99999") is None


def test_payos_paid_order_applies_first30_once(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "ADMIN_ID", "admin-only")
    try:
        bot.init_db()
        bot.seed_promotion_policy()
        user_id = "promo-user"
        initial_credits, _, _ = bot.get_user(user_id)

        ok, status, info = bot.activate_promo_for_user(user_id, "FIRST30")
        assert ok is True
        assert status == "activated"
        assert info["promo_type"] == "percent_bonus"
        assert info["value"] == 30

        bot.create_order("123456789", user_id, 50000, 500)
        processed, desc, paid_info = bot.process_payos_paid_order("123456789", 50000)
        assert processed is True
        assert desc == "success"
        assert paid_info["promo_bonus"] == 150
        assert paid_info["promo_code"] == "FIRST30"
        assert paid_info["launch_bonus"] == 30

        credits_after_paid, _, _ = bot.get_user(user_id)
        assert credits_after_paid == initial_credits + 680

        processed, desc, _paid_info = bot.process_payos_paid_order("123456789", 50000)
        assert processed is False
        assert desc == "already_paid"
        credits_after_replay, _, _ = bot.get_user(user_id)
        assert credits_after_replay == credits_after_paid
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_launch_bonus_once_per_user_package(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "ADMIN_ID", "admin-only")
    try:
        bot.init_db()
        user_id = "launch-user"
        initial_credits, _, _ = bot.get_user(user_id)

        bot.create_order("100001", user_id, 100000, 1000)
        processed, desc, paid_info = bot.process_payos_paid_order("100001", 100000)
        assert processed is True
        assert desc == "success"
        assert paid_info["launch_bonus"] == 50
        credits_after_first, _, _ = bot.get_user(user_id)
        assert credits_after_first == initial_credits + 1050

        bot.create_order("100002", user_id, 100000, 1000)
        processed, desc, paid_info = bot.process_payos_paid_order("100002", 100000)
        assert processed is True
        assert desc == "success"
        assert paid_info["launch_bonus"] == 0
        credits_after_second, _, _ = bot.get_user(user_id)
        assert credits_after_second == credits_after_first + 1000
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_beta_gift_requires_admin_assignment_and_grants_once(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "ADMIN_ID", "admin-only")
    try:
        bot.init_db()
        conn = bot.db_connect()
        try:
            ok, status = bot.create_gift_code_record(conn, "BETA100", 100, usage_limit=10, per_user_limit=1, note="test gift")
            assert ok is True
            assert status == "created"
            conn.commit()
        finally:
            conn.close()

        user_id = "gift-user"
        initial_credits, _, _ = bot.get_user(user_id)
        ok, status, info = bot.redeem_gift_code(user_id, "BETA100")
        assert ok is False
        assert status == "assignment_required"
        credits_locked, _, _ = bot.get_user(user_id)
        assert credits_locked == initial_credits

        ok, status, info = bot.grant_gift_code_to_user("admin-only", user_id, "BETA100")
        assert ok is True
        assert status == "redeemed"
        assert info["xu"] == 100
        credits_after, _, _ = bot.get_user(user_id)
        assert credits_after == initial_credits + 100

        ok, status, _info = bot.grant_gift_code_to_user("admin-only", user_id, "BETA100")
        assert ok is False
        assert status == "already_applied"
        credits_replay, _, _ = bot.get_user(user_id)
        assert credits_replay == credits_after
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_public_non_beta_gift_redeems_without_assignment(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "ADMIN_ID", "admin-only")
    try:
        bot.init_db()
        conn = bot.db_connect()
        try:
            ok, status = bot.create_gift_code_record(conn, "GIFT100", 100, usage_limit=10, per_user_limit=1, note="public gift")
            assert ok is True
            assert status == "created"
            promo = bot.get_promo_code_dict(conn, "GIFT100")
            assert bot.gift_requires_assignment(promo) is False
            conn.commit()
        finally:
            conn.close()

        user_id = "gift-public-user"
        initial_credits, _, _ = bot.get_user(user_id)
        ok, status, info = bot.redeem_gift_code(user_id, "GIFT100")
        assert ok is True
        assert status == "redeemed"
        assert info["xu"] == 100
        credits_after, _, _ = bot.get_user(user_id)
        assert credits_after == initial_credits + 100

        ok, status, _info = bot.redeem_gift_code(user_id, "GIFT100")
        assert ok is False
        assert status == "already_applied"
        credits_replay, _, _ = bot.get_user(user_id)
        assert credits_replay == credits_after
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_beta_gift_assignment_message_shows_contact_without_myid(monkeypatch):
    monkeypatch.setattr(bot, "SUPPORT_TELEGRAM_URL", "https://t.me/toanaas")
    user = SimpleNamespace(id=7817576663, username="martinss888", first_name="Martin", last_name="")
    message = bot.gift_needs_assignment_message(user, "BETA5")
    assert "BETA5" in message
    assert "7817576663" in message
    assert "@martinss888" in message
    assert "https://t.me/toanaas" in message
    assert "/myid" not in message
    assert "Lệnh xem ID" not in message

    no_username_user = SimpleNamespace(id=12345, username=None, first_name="No", last_name="User")
    no_username_message = bot.gift_needs_assignment_message(no_username_user, "BETA10")
    assert "Username: không có" in no_username_message


def test_trial_grant_locked_per_telegram_id(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    try:
        bot.init_db()
        credits, spent, vip = bot.get_user("trial-user", "First Name")
        assert (credits, spent, vip) == (bot.TRIAL_CREDITS, 0, 0)

        conn = bot.db_connect()
        try:
            c = conn.cursor()
            c.execute("SELECT granted_xu FROM trial_grants WHERE user_id=?", ("trial-user",))
            assert c.fetchone()[0] == bot.TRIAL_CREDITS
            c.execute("SELECT bonus_amount, status, claim_source FROM trial_bonus_claims WHERE telegram_user_id=? AND status='granted'", ("trial-user",))
            assert c.fetchone() == (bot.TRIAL_CREDITS, "granted", "telegram_start")
            c.execute("SELECT COUNT(*) FROM credit_events WHERE user_id=? AND event_type='trial_grant'", ("trial-user",))
            assert c.fetchone()[0] == 1
        finally:
            conn.close()

        credits_again, _, _ = bot.get_user("trial-user", "Changed Username")
        assert credits_again == bot.TRIAL_CREDITS
        conn = bot.db_connect()
        try:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM credit_events WHERE user_id=? AND event_type='trial_grant'", ("trial-user",))
            assert c.fetchone()[0] == 1
            c.execute("DELETE FROM users WHERE user_id=?", ("trial-user",))
            conn.commit()
        finally:
            conn.close()

        recreated_credits, recreated_spent, recreated_vip = bot.get_user("trial-user", "Recreated")
        assert (recreated_credits, recreated_spent, recreated_vip) == (0, 0, 0)
        conn = bot.db_connect()
        try:
            c = conn.cursor()
            c.execute("SELECT credits FROM users WHERE user_id=?", ("trial-user",))
            assert c.fetchone()[0] == 0
            c.execute(
                "SELECT delta FROM credit_events WHERE user_id=? AND event_type='trial_already_granted_recreated'",
                ("trial-user",),
            )
            assert c.fetchone()[0] == 0
            c.execute("SELECT COUNT(*) FROM trial_bonus_claims WHERE telegram_user_id=? AND status='blocked_duplicate_user'", ("trial-user",))
            assert c.fetchone()[0] >= 1
        finally:
            conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_trial_grants_backfill_existing_users(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """CREATE TABLE users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT,
                    credits INTEGER DEFAULT 0,
                    is_vip INTEGER DEFAULT 0,
                    join_date TEXT,
                    total_spent INTEGER DEFAULT 0
                )"""
            )
            conn.execute(
                "INSERT INTO users (user_id, username, credits, is_vip, join_date, total_spent) VALUES (?,?,?,?,?,?)",
                ("existing-user", "Existing", 75, 0, "2026-01-01 00:00:00", 0),
            )
            conn.commit()
        finally:
            conn.close()

        bot.init_db()
        conn = bot.db_connect()
        try:
            c = conn.cursor()
            c.execute("SELECT credits FROM users WHERE user_id=?", ("existing-user",))
            assert c.fetchone()[0] == 75
            c.execute("SELECT granted_xu, note FROM trial_grants WHERE user_id=?", ("existing-user",))
            row = c.fetchone()
            assert row[0] == bot.TRIAL_CREDITS
            assert row[1] == "Backfilled from existing users"
            c.execute("SELECT bonus_amount, status, claim_source FROM trial_bonus_claims WHERE telegram_user_id=? AND status='granted'", ("existing-user",))
            assert c.fetchone() == (bot.TRIAL_CREDITS, "granted", "legacy_trial_grants")
        finally:
            conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_trial_bonus_antispam_is_free_trial_only(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "ADMIN_ID", "admin-only")
    try:
        bot.init_db()
        user_id = "paid-user"
        initial_credits, _, _ = bot.get_user(user_id)
        bot.create_order("paid-50", user_id, 50000, 500)
        processed, desc, paid_info = bot.process_payos_paid_order("paid-50", 50000)
        assert processed is True
        assert desc == "success"
        assert paid_info["launch_bonus"] == 30
        credits_after_paid, _, _ = bot.get_user(user_id)
        assert credits_after_paid == initial_credits + 530

        conn = bot.db_connect()
        try:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM trial_bonus_claims WHERE telegram_user_id=? AND status='granted'", (user_id,))
            assert c.fetchone()[0] == 1
            c.execute("SELECT COUNT(*) FROM credit_events WHERE user_id=? AND event_type='trial_grant'", (user_id,))
            assert c.fetchone()[0] == 1
            c.execute("SELECT COUNT(*) FROM credit_events WHERE user_id=? AND event_type='payos_deposit'", (user_id,))
            assert c.fetchone()[0] == 1
        finally:
            conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


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


def test_head_brain_contract_keeps_review_and_publish_gates(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "ADMIN_ID", "admin-only")
    monkeypatch.setattr(bot, "PUBLIC_BASE_URL", "https://example.com")
    monkeypatch.setattr(bot, "OPERATOR_API_TOKEN", "operator-test-token")
    try:
        bot.init_db()
        assert bot.is_feature_enabled("auto_publish") is False

        cockpit = bot.operator_head_brain_cockpit_data("admin-only", days=1, platform="tiktok", limit=3)
        assert cockpit["ok"] is True
        assert cockpit["claude_next"]["read"].startswith("https://example.com/api/operator/head-brain")
        assert "review" in cockpit["operator_commands"]
        assert cockpit["operator_commands"]["approve"].startswith("/approve_publish")
        assert any(lane["phase"] == "publish" for lane in cockpit["lanes"])
        guardrails = "\n".join(cockpit["guardrails"]).lower()
        assert "không tự publish" in guardrails
        assert "admin chưa approve" in guardrails

        contract = bot.operator_control_contract_data("admin-only", days=1, platform="onlyfans", limit=3)
        gates = "\n".join(contract["non_negotiable_gates"]).lower()
        assert "không auto publish" in gates
        assert "consent" in gates
        assert "18+" in gates
        publish_phase = next(item for item in contract["lifecycle"] if item["phase"] == "publish")
        assert "manual" in publish_phase["telegram"].lower() or "handoff" in publish_phase["telegram"].lower()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_boss_video_launch_parser_clamps_and_keeps_manual_gate():
    plan = bot.parse_boss_video_launch_args(
        'topic="AI kiếm tiền affiliate" platform=onlyfans limit=99 duration=999 variants=1 build=0 run=1 tasks=100'
    )
    assert plan["topic"] == "AI kiếm tiền affiliate"
    assert plan["platform"] == "onlyfans"
    assert plan["limit"] == 8
    assert plan["duration"] == 120
    assert plan["variants"] == 3
    assert plan["build"] is False
    assert plan["autorun"] is True
    assert plan["autorun_max_tasks"] == 40
    assert "không tự đăng" in bot.boss_video_usage_text().lower()


def test_video_order_api_returns_machine_readable_handoff(monkeypatch):
    monkeypatch.setattr(bot, "OPERATOR_API_TOKEN", "operator-test-token")

    async def fake_launch(owner_id, topic, **kwargs):
        return True, "ok", {
            "target_platforms": [kwargs.get("platform")],
            "created_platforms": [kwargs.get("platform")],
            "created_jobs": [{"job_id": 101, "platform": kwargs.get("platform"), "title": topic, "score": 88}],
            "built_jobs": [{"job_id": 101}],
            "video_work_orders": {"orders": [{
                "job_id": 101,
                "task_id": 202,
                "platform": kwargs.get("platform"),
                "topic": topic,
                "scene_count": 5,
                "duration_sec": 45,
                "worker_prompt": "Create a compliant affiliate video with source tracking.",
                "complete_url": "/api/operator/tasks/202/complete",
                "upload_url": "/api/operator/tasks/202/upload",
                "acceptance_url": "/api/operator/output-acceptance?job_id=101&task_id=202",
                "review_url": "/api/operator/jobs/101/review-video",
                "telegram": {"video_brief": "/video_brief job=101", "worker_pack": "/worker_pack job=101 task=202"},
                "affiliate": {"product": "Test affiliate", "tracking_url": "https://example.com/r/7", "related_count": 2},
            }]},
            "automation_next": {"worker_autorun": "/worker_autorun jobs=101 execute=1"},
            "launch_next": {
                "first_job_id": 101,
                "telegram": {
                    "review": "/review_video job=101 send=1",
                    "approve": "/approve_publish job=101 queue=1 mode=manual",
                    "post_publish": "/post_publish job=101",
                },
                "api": {"review_video": "/api/operator/jobs/101/review-video"},
            },
            "affiliate": {"id": 7, "product": "Test affiliate"},
            "campaign": {"id": 3, "name": "Test campaign"},
        }

    monkeypatch.setattr(bot, "operator_launch_pipeline", fake_launch)
    client = TestClient(bot.fastapi_app)
    res = client.post(
        "/api/operator/video-order",
        headers={"Authorization": "Bearer operator-test-token"},
        json={"topic": "AI affiliate", "platform": "onlyfans", "limit": 1, "notify_admin": False},
    )
    assert res.status_code == 200
    payload = res.json()
    order = payload["video_order"]
    assert order["first_job_id"] == 101
    assert order["gate"]["auto_publish"] is False
    assert order["gate"]["onlyfans_manual"] is True
    assert order["telegram"]["worker"] == "/worker_autorun jobs=101 execute=1"
    assert order["telegram"]["review"] == "/review_video job=101 send=1"
    assert order["telegram"]["approve"] == "/approve_publish job=101 queue=1 mode=manual"
    assert order["telegram"]["work_orders"] == "/video_work_orders jobs=101 tool=claude"
    assert order["api"]["review_video"] == "/api/operator/jobs/101/review-video"
    assert order["api"]["work_orders"] == "/api/operator/video-work-orders?job_ids=101&tool=claude"
    assert order["work_orders"][0]["task_id"] == 202
    assert order["work_orders"][0]["submit"]["upload"] == "/api/operator/tasks/202/upload"
    assert order["work_orders"][0]["submit"]["complete"] == "/api/operator/tasks/202/complete"
    assert order["run_card"]["state"] == "VIDEO_ORDER_CREATED"
    assert order["run_card"]["sequence"][1]["action"] == "submit_real_video_or_scene_output"
    assert order["run_card"]["sequence"][3]["telegram"] == "/approve_publish job=101 queue=1 mode=manual"
