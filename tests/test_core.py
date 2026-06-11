import asyncio
import hmac
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from datetime import datetime
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
    assert "🔐 Admin" in button_texts
    assert "🧠 Operator" not in button_texts
    assert "⚙️ Hệ Thống" not in button_texts
    admin_nav_labels = [button.text for row in bot.menu_nav_keyboard("admin", True).inline_keyboard for button in row]
    assert "🧠 Operator" in admin_nav_labels
    assert "⚙️ Hệ thống" in admin_nav_labels
    assert "🎁 Gói / Combo" in admin_nav_labels
    assert "🧊 Freeze / Queue" in admin_nav_labels
    assert "📊 Báo cáo tổng" in admin_nav_labels
    assert "🧪 Smoke Test" in admin_nav_labels
    admin_nav_rows = [[button.text for button in row] for row in bot.menu_nav_keyboard("admin", True).inline_keyboard]
    assert ["💰 Tài chính", "🧊 Freeze / Queue"] in admin_nav_rows
    finance_labels = [button.text for row in bot.finance_admin_keyboard().inline_keyboard for button in row]
    for label in ["📊 Tổng quan", "💵 Doanh thu", "📅 Doanh thu tháng", "📉 Chi phí tháng", "📈 Lãi / Lỗ", "📤 Xuất báo cáo", "➕ Thêm chi phí", "📚 Hướng dẫn lệnh"]:
        assert label in finance_labels
    freeze_labels = [button.text for row in bot.freeze_queue_keyboard().inline_keyboard for button in row]
    for label in ["📊 Queue Status", "🧊 Freeze Status", "🖼 Freeze Image", "🎬 Freeze Video", "🎞 Freeze Frame", "🤖 Freeze Provider", "✅ Unfreeze Tool", "🧹 Clear Stale Jobs"]:
        assert label in freeze_labels
    assert "Tài chính nội bộ TOAN AAS" in bot.finance_menu_text()
    assert "Mục này dùng để kiểm tra hàng đợi job" in bot.freeze_queue_menu_text()
    assert "Báo cáo tổng TOAN AAS" in bot.admin_overview_text()
    admin_menu = bot.menu_text_admin()
    for command in [
        "/add",
        "/setvip",
        "/pending",
        "/duyet",
        "/tuchoi",
        "/runtime",
        "/data_status",
        "/providers",
        "/shopaikey_status",
        "/shopaikey_usage",
        "/shopaikey_video_job",
        "/package_catalog",
        "/grant_combo",
        "/grant_monthly",
        "/user_packages",
        "/adjust_package",
        "/revoke_package",
        "/maintenance_status",
        "/freeze_status",
        "/freeze_video",
        "/unfreeze_video",
        "/queue_status",
        "/job_status",
        "/refund_job",
        "/clear_job_lock",
        "/provider_freeze",
        "/provider_unfreeze",
    ]:
        assert command in admin_menu
    assert "cộng Xu trực tiếp" in admin_menu
    assert "đối soát tiền thật" in admin_menu
    assert "kiểm tra job video" in admin_menu
    assert "hoàn Xu/lượt thủ công" in admin_menu
    system_menu = bot.menu_text_system()
    assert "/data_status" in system_menu and "persistent volume" in system_menu
    operator_menu = bot.menu_text_operator(True)
    assert "/mission_add &lt;mục_tiêu&gt;" in operator_menu
    assert "worker nhận tác vụ" in operator_menu
    registry = (Path(bot.__file__).resolve().parent / "docs" / "COMMAND_REGISTRY.md").read_text(encoding="utf-8")
    assert "| `/data_status` |" in registry
    assert "| `/shopaikey_status` |" in registry
    assert "| `/shopaikey_usage` |" in registry
    assert "| `/shopaikey_video_job` |" in registry
    assert "| `/package_catalog` |" in registry
    assert "| `/grant_combo` |" in registry
    assert "| `/grant_monthly` |" in registry
    assert "| `/user_packages` |" in registry
    assert "| `/adjust_package` |" in registry
    assert "| `/revoke_package` |" in registry
    assert "| `/freeze_status` |" in registry
    assert "| `/freeze_video` |" in registry
    assert "| `/unfreeze_video` |" in registry
    assert "| `/queue_status` |" in registry
    assert "| `/job_status` |" in registry
    assert "| `/refund_job` |" in registry
    assert "| `/clear_job_lock` |" in registry


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
    assert "SHOPAIKEY_IMAGE_MODEL_PRIMARY=nano-banana" in env_example
    assert "SHOPAIKEY_IMAGE_MODEL_FALLBACKS=gemini-2.5-flash-image,gemini-2.0-flash-preview-image-generation" in env_example
    assert "SHOPAIKEY_VIDEO_URL=https://api.shopaikey.com/v1/video/generations" in env_example
    assert "SHOPAIKEY_VIDEO_MODEL=veo3.1-fast" in env_example
    assert "SHOPAIKEY_VIDEO_FALLBACK_MODELS=veo3.1,veo3.1-fast,veo3.1-pro" in env_example
    assert "SHOPAIKEY_PUBLIC_IMAGE_ENABLED=true" in env_example
    assert "SHOPAIKEY_PUBLIC_VIDEO_ENABLED=true" in env_example
    assert "PUBLIC_VIDEO_GENERATION_ENABLED=true" in env_example
    assert "IMAGE_TIER_LOW_ENABLED=true" in env_example
    assert "IMAGE_TIER_STANDARD_ENABLED=true" in env_example
    assert "IMAGE_TIER_HIGH_ENABLED=true" in env_example
    assert "SHOPAIKEY_IMAGE_DEFAULT_TIER=low" in env_example
    assert "VIDEO_TIER_LOW_ENABLED=true" in env_example
    assert "VIDEO_TIER_BASIC_ENABLED=true" in env_example
    assert "VIDEO_TIER_COMMON_ENABLED=true" in env_example
    assert "VIDEO_TIER_STANDARD_ENABLED=true" in env_example
    assert "VIDEO_TIER_HIGH_ENABLED=true" in env_example
    assert "VIDEO_TIER_PREMIUM_ENABLED=false" in env_example
    assert "VIDEO_PREMIUM_ADMIN_ONLY=true" in env_example
    assert "SHOPAIKEY_VIDEO_DEFAULT_TIER=low" in env_example
    assert "CREATIVE_MOTION_GUIDE_COST_XU=0" in env_example
    assert "IMAGE_BASE_COST_XU=50" in env_example
    assert "VIDEO_BASE_COST_XU=300" in env_example
    assert "MEDIA_PRICE_MULTIPLIER=2" in env_example
    assert "IMAGE_LOW_COST_XU=50" in env_example
    assert "IMAGE_STANDARD_COST_XU=200" in env_example
    assert "IMAGE_STANDARD_WARRANTY_COST_XU=250" in env_example
    assert "IMAGE_HIGH_COST_XU=400" in env_example
    assert "IMAGE_HIGH_WARRANTY_COST_XU=500" in env_example
    assert "VIDEO_LOW_COST_XU=200" in env_example
    assert "VIDEO_BASIC_COST_XU=300" in env_example
    assert "VIDEO_COMMON_COST_XU=400" in env_example
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
    assert "TREND_WORKFLOW_PUBLIC_ENABLED=true" in env_example
    assert "TREND_WORKFLOW_BILLING_ENABLED=true" in env_example
    assert "TREND_WORKFLOW_REQUIRE_CONFIRM=true" in env_example
    assert "TREND_WORKFLOW_CONTENT_ONLY=true" in env_example
    assert "SYSTEM_MAINTENANCE_MODE=false" in env_example
    assert "PROVIDER_FREEZE_ENABLED=false" in env_example
    assert "TOOL_FREEZE_IMAGE=false" in env_example
    assert "SHOPAIKEY_AUTO_FREEZE_ENABLED=true" in env_example
    assert "SHOPAIKEY_LOW_CREDIT_FREEZE_PERCENT=5" in env_example
    assert "SHOPAIKEY_ERROR_FREEZE_THRESHOLD=5" in env_example
    assert "SHOPAIKEY_VIDEO_ERROR_FREEZE_THRESHOLD_SHORT=5" in env_example
    assert "SHOPAIKEY_VIDEO_ERROR_FREEZE_THRESHOLD_LONG=10" in env_example
    assert "SHOPAIKEY_VIDEO_STALE_TIMEOUT_LOW_MINUTES=15" in env_example
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
    video_command_source = source_between(source, "async def cmd_tool_test_shopaikey_video", "def shopaikey_video_job_check_keyboard")
    assert "lang = user_ui_lang(uid)" in video_command_source
    assert "safe_reply_text" in video_command_source
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
    assert "async def cmd_freeze_status" in source
    assert "async def cmd_freeze_video" in source
    assert "async def cmd_unfreeze_video" in source
    assert "async def cmd_queue_status" in source
    assert "async def cmd_job_status" in source
    assert "async def cmd_refund_job" in source
    assert "async def cmd_clear_job_lock" in source
    assert 'provider_freeze_display("shopaikey")' in source
    assert 'provider_freeze_runtime_on("shopaikey")' in source
    assert 'CommandHandler("maintenance_status", cmd_maintenance_status)' in source
    assert 'CommandHandler("provider_freeze", cmd_provider_freeze)' in source
    assert 'CommandHandler("provider_unfreeze", cmd_provider_unfreeze)' in source
    assert 'CommandHandler("freeze_status", cmd_freeze_status)' in source
    assert 'CommandHandler("freeze_video", cmd_freeze_video)' in source
    assert 'CommandHandler("unfreeze_video", cmd_unfreeze_video)' in source
    assert 'CommandHandler("queue_status", cmd_queue_status)' in source
    assert 'CommandHandler("job_status", cmd_job_status)' in source
    assert 'CommandHandler("refund_job", cmd_refund_job)' in source
    assert 'CommandHandler("clear_job_lock", cmd_clear_job_lock)' in source
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


def test_video_provider_freeze_does_not_block_public_image(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "SHOPAIKEY_AUTO_FREEZE_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_ERROR_FREEZE_THRESHOLD", 2)
    monkeypatch.setattr(bot, "SHOPAIKEY_ERROR_FREEZE_WINDOW_MINUTES", 15)
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_IMAGE_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_VIDEO_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "test-key")
    monkeypatch.setattr(bot, "SYSTEM_MAINTENANCE_MODE", False)
    monkeypatch.setattr(bot, "PROVIDER_FREEZE_ENABLED", False)
    monkeypatch.setattr(bot, "TOOL_FREEZE_IMAGE", False)
    monkeypatch.setattr(bot, "TOOL_FREEZE_VIDEO", False)
    try:
        bot.init_db()
        bot.record_provider_error("shopaikey", "video", "NO_CHANNEL", "video no channel one")
        bot.record_provider_error("shopaikey", "video", "NO_CHANNEL", "video no channel two")
        assert int(bot.provider_freeze_row("shopaikey_video").get("is_frozen") or 0) == 1
        assert int(bot.provider_freeze_row("shopaikey").get("is_frozen") or 0) == 0
        ok_video, video_message = bot.shopaikey_public_generation_guard("video")
        assert ok_video is False
        assert video_message == bot.USER_VIDEO_PROVIDER_FROZEN_MESSAGE
        assert bot.public_video_runtime_status_text() == "FROZEN"
        assert bot.shopaikey_public_generation_guard("image")[0] is True
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_video_maintenance_guard_low_credit_lock_refund_and_stale(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "SHOPAIKEY_AUTO_FREEZE_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_LOW_CREDIT_FREEZE_PERCENT", 5)
    monkeypatch.setattr(bot, "SHOPAIKEY_LOW_CREDIT_WARN_PERCENT", 10)
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_IMAGE_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_VIDEO_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "test-key")
    monkeypatch.setattr(bot, "SYSTEM_MAINTENANCE_MODE", False)
    monkeypatch.setattr(bot, "PROVIDER_FREEZE_ENABLED", False)
    monkeypatch.setattr(bot, "TOOL_FREEZE_IMAGE", False)
    monkeypatch.setattr(bot, "TOOL_FREEZE_VIDEO", False)
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_STALE_TIMEOUT_LOW_MINUTES", 1)
    monkeypatch.setattr(bot, "VIDEO_LOW_COST_XU", 200)
    try:
        bot.init_db()
        bot.save_shopaikey_usage_snapshot(
            {
                "total": 100,
                "used": 96,
                "balance": 4,
                "remaining": 4,
                "remaining_percent": 4,
                "group_name": "cheap",
                "token_name": "masked",
            },
            "test",
        )
        assert int(bot.provider_freeze_row("shopaikey_video").get("is_frozen") or 0) == 1
        assert int(bot.provider_freeze_row("shopaikey").get("is_frozen") or 0) == 0
        ok_video, video_message = bot.shopaikey_public_generation_guard("video")
        assert ok_video is False
        assert video_message == bot.USER_VIDEO_PROVIDER_FROZEN_MESSAGE
        assert bot.public_video_runtime_status_text() == "FROZEN"
        assert bot.shopaikey_public_generation_guard("image")[0] is True

        bot.set_provider_freeze_state("shopaikey_video", False, "manual_unfreeze", "ok", "test")
        bot.record_provider_error("shopaikey", "video", "NO_CHANNEL", "no available channel")
        assert int(bot.provider_freeze_row("shopaikey_video").get("is_frozen") or 0) == 1
        assert "/queue_status" in bot.menu_text_admin()
        assert "/refund_job" in bot.menu_text_admin()
        bot.set_provider_freeze_state("shopaikey_video", False, "manual_unfreeze", "ok", "test")

        bot.get_user("lock_user", "Lock user")
        lock_job_id = bot.create_shopaikey_job("lock_user", "chat", "video", model="veo3.1-fast", prompt="video", status="PROCESSING", admin_only=False, xu_cost_planned=200)
        bot.update_shopaikey_job(job_id=lock_job_id, task_id="task_lock")
        active = bot.shopaikey_active_job_for_user("lock_user", "video")
        assert active and int(active["id"]) == lock_job_id
        assert "Video sẽ được gửi tự động" in bot.public_video_active_job_text("vi")
        lock_buttons = [button.text for row in bot.public_video_active_job_keyboard(active, "vi").inline_keyboard for button in row]
        assert "🔄 Kiểm tra trạng thái video" in lock_buttons
        assert "🏠 Menu chính" in lock_buttons

        bot.get_user("refund_video", "Refund video")
        conn = bot.db_connect()
        try:
            conn.execute("UPDATE users SET credits=500, total_spent=0 WHERE user_id=?", ("refund_video",))
            conn.commit()
        finally:
            conn.close()
        charge = bot.spend_fixed_credit_info("refund_video", 200, "shopaikey_video", "unit video refund", True)
        assert charge["ok"] is True
        refund_job_id = bot.create_shopaikey_job("refund_video", "chat", "video", model="veo3.1-fast", prompt="video", status="FAILED", admin_only=False, xu_cost_planned=200)
        bot.update_shopaikey_job(job_id=refund_job_id, xu_deducted=200, refund_status="pending", refund_reason="provider_fail")
        assert bot.refund_shopaikey_job_if_needed("refund_video", refund_job_id, "", "provider fail") is True
        credits_after_refund, _, _ = bot.get_user("refund_video")
        assert int(credits_after_refund) == 500
        assert bot.refund_shopaikey_job_if_needed("refund_video", refund_job_id, "", "provider fail") is False
        credits_after_second_refund, _, _ = bot.get_user("refund_video")
        assert int(credits_after_second_refund) == 500

        bot.get_user("stale_video", "Stale video")
        conn = bot.db_connect()
        try:
            conn.execute("UPDATE users SET credits=500, total_spent=0 WHERE user_id=?", ("stale_video",))
            conn.commit()
        finally:
            conn.close()
        assert bot.spend_fixed_credit_info("stale_video", 200, "shopaikey_video", "unit stale video", True)["ok"] is True
        stale_job_id = bot.create_shopaikey_job("stale_video", "chat", "video", model="veo3.1-fast", prompt="video", status="QUEUED", admin_only=False, xu_cost_planned=200)
        bot.update_shopaikey_job(job_id=stale_job_id, task_id="task_stale", xu_deducted=200, refund_status="pending")
        old_at = "2000-01-01 00:00:00"
        conn = bot.db_connect()
        try:
            conn.execute("UPDATE shopaikey_jobs SET created_at=?, updated_at=? WHERE id=?", (old_at, old_at, stale_job_id))
            conn.commit()
        finally:
            conn.close()
        stale = bot.mark_stale_public_video_jobs("stale_video")
        assert stale and int(stale[0]["id"]) == stale_job_id
        fresh = bot.shopaikey_job_by_id(stale_job_id)
        assert fresh["status"] == "FAILED_TIMEOUT"
        assert fresh["refund_status"] == "refunded"
        credits_after_stale, _, _ = bot.get_user("stale_video")
        assert int(credits_after_stale) == 500
        assert bot.shopaikey_active_job_for_user("stale_video", "video") is None
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
    video_source = source_between(source, "async def cmd_shopaikey_video_public", "async def handle_shopaikey_public_callback")
    callback_source = source_between(source, "async def handle_shopaikey_public_callback", "class TranslationProviderError")
    assert "shopaikey_public_generation_guard" in image_source
    assert "shopaikey_public_generation_guard" in video_source
    assert "set_media_aspect_pending" in image_source
    assert "set_media_aspect_pending" in video_source
    assert "public_media_aspect_ratio_keyboard" in image_source
    assert "public_media_aspect_ratio_keyboard" in video_source
    assert "spend_fixed_credit_info" not in image_source
    assert "spend_fixed_credit_info" not in video_source
    assert "spend_fixed_credit_info" in callback_source
    assert "set_shopaikey_pending_confirmation" in source_between(source, "async def handle_create_media_callback", "async def cmd_tool_test_workflow_image")
    assert "refund_shopaikey_job_if_needed" in callback_source
    assert "record_shopaikey_billing_event" in callback_source
    assert "SHOPAIKEY_REQUIRE_CONFIRM_BEFORE_DEDUCT" in source
    assert "SHOPAIKEY_REFUND_ON_PROVIDER_FAIL" in source
    assert "Pricing mode:" in source and "tiered_media_pricing" in source
    assert "Image tiers:" in source
    assert "Video tier config:" in source
    assert "Public video generation:" in source
    assert "Price table source:" in source
    assert "deduct_dynamic_credit(" not in callback_source
    assert "add_credit(" not in callback_source
    assert "Bot chưa trừ Xu hoặc chưa thể hoàn tự động" not in callback_source
    assert "public_image_provider_fail_message" in callback_source
    assert "public_video_provider_fail_message" in callback_source
    assert "alert_public_image_refund_failure" in callback_source
    assert "alert_public_video_refund_failure" in callback_source
    assert "refund_failed" in callback_source
    assert "provider_fail" in callback_source
    for event_name in [
        "video_cancelled",
        "video_insufficient_balance",
        "video_deducted",
        "video_provider_submitted",
        "video_provider_fail",
        "video_refunded",
        "video_refund_failed",
    ]:
        assert event_name in callback_source
    for event_name in ["video_prompt_received", "video_confirm_shown", "video_polling", "video_success", "video_timeout"]:
        assert event_name in source
    assert "Public image generation:" in source
    assert "Public video generation:" in source
    assert "Admin smoke image tests:" in source
    assert "Image: <code>admin-only custom Google image endpoint; public OFF" not in source
    assert bot.public_image_provider_fail_message(0, False) == "⚙️ Model tạo ảnh đang bận hoặc cần bảo trì. TOAN AAS chưa trừ Xu hoặc đã hoàn Xu nếu có trừ. Vui lòng thử lại sau."
    assert bot.public_image_provider_fail_message(50, True) == "⚙️ Model tạo ảnh đang bận hoặc cần bảo trì. TOAN AAS chưa trừ Xu hoặc đã hoàn Xu nếu có trừ. Vui lòng thử lại sau."
    assert "Admin đã được ghi nhận" in bot.public_image_provider_fail_message(50, False)
    assert bot.public_video_provider_fail_message(0, False) == "⚙️ Model tạo video đang bận hoặc lỗi tạm thời. Bot chưa trừ Xu của bạn. Vui lòng thử lại sau."
    assert bot.public_video_provider_fail_message(300, True) == "⚙️ Model tạo video đang bận hoặc lỗi tạm thời. TOAN AAS đã hoàn lại 300 Xu cho bạn. Vui lòng thử lại sau."
    assert "Admin đã được ghi nhận" in bot.public_video_provider_fail_message(300, False)

    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_IMAGE_ENABLED", False)
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_VIDEO_ENABLED", False)
    public_off_message = "🧪 Tính năng này đang thử nghiệm nội bộ, chưa mở công khai. TOAN AAS sẽ mở sau khi kiểm tra ổn định."
    assert bot.shopaikey_public_generation_guard("image") == (False, public_off_message)
    assert bot.shopaikey_public_generation_guard("video") == (False, public_off_message)
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_IMAGE_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_VIDEO_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "test-key")
    assert bot.shopaikey_public_generation_guard("image")[0] is True
    assert bot.shopaikey_public_generation_guard("video")[0] is True

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
    assert pricing["trend_workflow_content_only"] is True
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
        bot.get_user("no_deduct_user", "No deduct")
        conn = bot.db_connect()
        try:
            conn.execute("UPDATE users SET credits=100, total_spent=0 WHERE user_id=?", ("no_deduct_user",))
            conn.commit()
        finally:
            conn.close()
        assert bot.public_image_provider_fail_message(0, False).startswith("⚙️ Model tạo ảnh")
        credits_before_no_deduct, _, _ = bot.get_user("no_deduct_user")
        assert int(credits_before_no_deduct) == 100

        bot.get_user("refund_user", "Refund user")
        conn = bot.db_connect()
        try:
            conn.execute("UPDATE users SET credits=100, total_spent=0 WHERE user_id=?", ("refund_user",))
            conn.commit()
        finally:
            conn.close()
        charge = bot.spend_fixed_credit_info("refund_user", 50, "shopaikey_image", "unit public image", True)
        assert charge["ok"] is True
        assert int(charge["final_cost"]) == 50
        credits_after_deduct, _, _ = bot.get_user("refund_user")
        assert int(credits_after_deduct) == 50
        refund_job_id = bot.create_shopaikey_job("refund_user", "c2", "image", model="nano-banana", prompt="prompt", status="FAILED", admin_only=False, xu_cost_planned=50)
        bot.update_shopaikey_job(job_id=refund_job_id, xu_deducted=50, refund_status="pending", refund_reason="provider_fail")
        assert bot.refund_shopaikey_job_if_needed("refund_user", refund_job_id, "", "provider fail") is True
        credits_after_refund, _, _ = bot.get_user("refund_user")
        assert int(credits_after_refund) == 100
        assert bot.shopaikey_video_cost_for_flow(True, "u2") == 640
        image_job_id = bot.create_shopaikey_job("u2", "c2", "image", model="nano-banana", prompt="prompt", status="SUCCESS", admin_only=False, xu_cost_planned=320)
        bot.update_shopaikey_job(job_id=image_job_id, xu_deducted=320, result_url="https://example.com/image.png", output_file_id="telegram_photo_id")
        assert bot.shopaikey_paid_image_source_available("u2", str(image_job_id)) is True
        image_package = bot.build_image_to_video_public_package("u2", image_job_id, 1)
        assert image_package["source_job_id"] == str(image_job_id)
        assert image_package["image_job_id"] == str(image_job_id)
        assert image_package["image_url"] == "https://example.com/image.png"
        assert image_package["telegram_file_id"] == "telegram_photo_id"
        package_payload = bot.public_video_pending_payload_from_package("low", image_package)
        assert package_payload["source_job_id"] == str(image_job_id)
        assert package_payload["image_url"] == "https://example.com/image.png"
        assert bot.shopaikey_video_cost_for_flow(True, "u2") == 640
        video_job_id = bot.create_shopaikey_job("u2", "c2", "video", model="veo3.1-fast", prompt="video", status="QUEUED", admin_only=False, xu_cost_planned=640, source_job_id=str(image_job_id))
        assert video_job_id > 0
        assert bot.shopaikey_paid_image_source_available("u2", str(image_job_id)) is True
        assert bot.shopaikey_video_cost_for_flow(True, "u2") == 640
        queue_text = bot.ui_text("vi", "video.queue_submitted", task_id="task_123", auto_poll="ON")
        assert "Video sẽ được gửi tự động trong vài phút khi hoàn tất" in queue_text
        assert "Vui lòng không gửi lại lệnh hoặc bấm tạo nhiều lần" in queue_text
        public_queue_buttons = [button.text for row in bot.shopaikey_video_job_check_keyboard("task_123", "vi", public_user=True).inline_keyboard for button in row]
        assert "🔄 Kiểm tra trạng thái video" in public_queue_buttons
        assert "🏠 Menu chính" in public_queue_buttons
        assert not any("ShopAIKey" in text for text in public_queue_buttons)
        admin_queue_buttons = [button.text for row in bot.shopaikey_video_job_check_keyboard("task_123", "vi").inline_keyboard for button in row]
        assert any("ShopAIKey" in text for text in admin_queue_buttons)
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_package_wallet_admin_grant_deduct_refund_and_revoke(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    try:
        bot.init_db()
        conn = bot.db_connect()
        try:
            package_tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('user_packages','user_package_items','package_events')"
                ).fetchall()
            }
            job_cols = {row[1] for row in conn.execute("PRAGMA table_info(shopaikey_jobs)").fetchall()}
        finally:
            conn.close()
        assert {"user_packages", "user_package_items", "package_events"}.issubset(package_tables)
        assert {"package_id", "package_item_id", "package_item_type", "package_units_used", "package_refund_status"}.issubset(job_cols)
        assert "tiktok_99k" in bot.package_catalog_payload()["combos"]
        assert "starter_monthly" in bot.package_catalog_payload()["monthly"]
        assert bot.package_item_type_for_video_tier("common") == "video_common"
        assert bot.package_item_type_for_image_tier("standard_warranty") == "image_standard_warranty"

        bot.get_user("pkg_user", "Pkg User")
        conn = bot.db_connect()
        try:
            conn.execute("UPDATE users SET credits=777, total_spent=0 WHERE user_id=?", ("pkg_user",))
            conn.commit()
        finally:
            conn.close()
        before_credits, before_spent, _ = bot.get_user("pkg_user")
        granted = bot.grant_user_package("pkg_user", "tiktok_99k", "combo", "admin", 0, "pytest")
        assert granted["ok"] is True
        item = bot.active_package_item_for_user("pkg_user", "video_common")
        assert item
        assert int(item["remaining_quantity"]) == 3
        after_grant_credits, after_grant_spent, _ = bot.get_user("pkg_user")
        assert int(after_grant_credits) == int(before_credits)
        assert int(after_grant_spent) == int(before_spent)

        job_id = bot.create_shopaikey_job(
            "pkg_user",
            "chat",
            "video",
            model="veo3.1-fast",
            prompt="video prompt",
            status="QUEUED",
            admin_only=False,
            xu_cost_planned=bot.video_tier_cost_xu("common"),
            package_id=int(item["package_id"]),
            package_item_id=int(item["id"]),
            package_item_type="video_common",
            package_units_used=1,
        )
        used = bot.deduct_package_item_for_job("pkg_user", "video_common", job_id, "pytest use")
        assert used["ok"] is True
        assert int(used["remaining_after"]) == 2
        credits_after_use, spent_after_use, _ = bot.get_user("pkg_user")
        assert int(credits_after_use) == int(before_credits)
        assert int(spent_after_use) == int(before_spent)

        assert bot.refund_package_item_for_job("pkg_user", job_id, "provider_fail") is True
        assert bot.refund_package_item_for_job("pkg_user", job_id, "provider_fail_again") is False
        refunded_item = bot.active_package_item_for_user("pkg_user", "video_common")
        assert int(refunded_item["remaining_quantity"]) == 3
        bot.update_shopaikey_job(job_id=job_id, status="FAILED", finished_at=bot.now_text())

        job_id2 = bot.create_shopaikey_job(
            "pkg_user",
            "chat",
            "video",
            model="veo3.1-fast",
            prompt="video prompt retry guard",
            status="IN_PROGRESS",
            admin_only=False,
            xu_cost_planned=bot.video_tier_cost_xu("common"),
            package_id=int(item["package_id"]),
            package_item_id=int(item["id"]),
            package_item_type="video_common",
            package_units_used=1,
        )
        used2 = bot.deduct_package_item_for_job("pkg_user", "video_common", job_id2, "pytest terminal fail")
        assert used2["ok"] is True
        assert int(used2["remaining_after"]) == 2
        terminal_summary = bot.finalize_public_video_terminal_failure(
            bot.shopaikey_job_by_id(job_id2),
            {"status": "FAILED", "detail": "No available channel"},
            "FAILED",
        )
        assert terminal_summary["package_refunded"] is True
        assert bot.shopaikey_active_job_for_user("pkg_user", "video") is None
        terminal_summary_again = bot.finalize_public_video_terminal_failure(
            bot.shopaikey_job_by_id(job_id2),
            {"status": "FAILED", "detail": "No available channel again"},
            "FAILED",
        )
        assert terminal_summary_again["package_refunded"] is True
        terminal_item = bot.active_package_item_for_user("pkg_user", "video_common")
        assert int(terminal_item["remaining_quantity"]) == 3

        adjusted = bot.adjust_user_package_item("pkg_user", str(granted["package_id"]), "video_common", 2, "admin", "pytest adjust")
        assert adjusted["ok"] is True
        assert int(adjusted["after"]) == 5
        revoked = bot.revoke_user_package("pkg_user", str(granted["package_id"]), "admin", "pytest revoke")
        assert revoked["ok"] is True
        assert bot.active_package_item_for_user("pkg_user", "video_common") is None
        summary = bot.user_package_summary_text("pkg_user", admin_view=True)
        assert "revoked" in summary
        assert "Combo Ưu Đãi TikTok" in summary
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_payos_package_purchase_grants_wallet_without_xu_or_rank_points(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "ADMIN_ID", "admin-only")
    try:
        bot.init_db()
        user_id = "pkg-payos-user"
        bot.get_user(user_id, "PayOS Package User")
        before_credits, before_spent, _ = bot.get_user(user_id)
        metadata = {
            "type": "package_purchase",
            "package_type": "combo",
            "package_code": "tiktok_99k",
            "package_label": "🎁 Combo Ưu Đãi TikTok — 99k",
        }
        bot.create_order(
            "900001",
            user_id,
            99000,
            0,
            base_xu=0,
            launch_bonus_xu=0,
            package_amount_vnd=0,
            order_type="package_purchase",
            plan_id="tiktok_99k",
            plan_name="🎁 Combo Ưu Đãi TikTok — 99k",
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        )
        processed, desc, info = bot.process_payos_paid_order("900001", 99000)
        assert processed is True
        assert desc == "package_success"
        assert info["order_type"] == "package_purchase"
        assert info["package_type"] == "combo"
        assert info["package_code"] == "tiktok_99k"
        item = bot.active_package_item_for_user(user_id, "video_common")
        assert item
        assert int(item["remaining_quantity"]) == 3
        after_credits, after_spent, _ = bot.get_user(user_id)
        assert int(after_credits) == int(before_credits)
        assert int(after_spent) == int(before_spent)
        assert bot.member_total_paid_vnd(user_id) == 0
        message = bot.package_purchase_success_message(info)
        assert "📦 Gói của tôi" in message
        assert "không cộng điểm nâng hạng" in message
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


def test_shopaikey_video_status_stale_timeout_and_success_event(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    try:
        bot.init_db()
        bot.save_shopaikey_component_snapshot(
            "video",
            {"status": "IN_PROGRESS", "model": "veo3.1-fast", "http_status": 200, "latency_ms": 0},
            "model=veo3.1-fast; task_id=old_task",
            "test",
        )
        bot.set_system_setting("shopaikey_video_last_at", "2000-01-01 00:00:00", "test stale timestamp", "test")
        monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_STATUS_STALE_SECONDS", 60)
        stale = bot.shopaikey_video_status_snapshot()
        assert stale["status"] == "STALE_TIMEOUT"
        assert "stale video smoke status" in stale["detail"]

        bot.record_api_debug("shopaikey", "shopaikey_video_job", "SUCCESS", 200, "model=veo3.1-fast; task_id=new_task; result_url=sent")
        latest = bot.shopaikey_video_status_snapshot()
        assert latest["status"] == "SUCCESS"
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
    assert bot.shopaikey_db_video_status("FAILED_TIMEOUT") == "TIMEOUT"

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
    failed_text = bot.public_video_status_message("FAILED", job={}, fail_summary={"not_charged": True}, lang="vi")
    assert "Video tạo thất bại" in failed_text
    assert "Video sẽ được gửi tự động" not in failed_text
    failed_buttons = [button.text for row in bot.public_video_failed_keyboard(123, "vi").inline_keyboard for button in row]
    assert "🔁 Thử tạo lại" in failed_buttons
    assert "🎬 Chọn gói video khác" in failed_buttons
    assert "👨‍💼 Liên hệ admin" in failed_buttons
    processing_text = bot.public_video_status_message("IN_PROGRESS", progress="20", lang="vi")
    assert "Video sẽ được gửi tự động trong vài phút khi hoàn tất" in processing_text

    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_IMAGE_ENABLED", False)
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_VIDEO_ENABLED", False)
    assert bot.shopaikey_public_generation_guard("image")[0] is False
    assert bot.shopaikey_public_generation_guard("video")[0] is False
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_IMAGE_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_VIDEO_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "test-key")
    assert bot.shopaikey_public_generation_guard("image")[0] is True
    assert bot.shopaikey_public_generation_guard("video")[0] is True

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
    assert "TREND_WORKFLOW_CONTENT_ONLY" in source
    assert "Trend video workflow:" in source
    assert "Workflow image generation:" in source
    assert "Bạn muốn làm gì tiếp" in source
    assert "tvflow|image_scene_1" in source
    assert "tvflow|image_scene_2" in source
    assert "tvflow|image_scene_3" in source
    assert 'set_trend_video_flow_pending(uid, "topic")' in command_source
    assert "trend_video_pending_prompt_text(lang)" in command_source
    assert "pending_action" in source and "trend_video_flow" in source
    assert "TREND_VIDEO_PENDING_TTL_SECONDS" in source
    assert "handle_trend_video_flow_pending_text(update, context)" in message_source
    assert message_source.index("handle_trend_video_flow_pending_text(update, context)") < message_source.index("is_probable_media_tags_text")
    assert "send_trend_guided_source_message(update.message, uid, topic, lang)" in pending_source
    assert "trend_guided_trend_source_text" in source
    assert "trendg|trend_source_popular" in source
    assert "trendg|trend_source_search" in source
    assert "trendg|trend_source_custom" in source
    assert "trendg|trend_source_skip" in source
    assert "clear_trend_video_flow_pending(uid)" in source
    assert "shopaikey_image_generate" not in combined_source
    assert "shopaikey_video_create" not in combined_source
    assert "spend_fixed_credit_info" in combined_source
    assert "trend_workflow_content" in combined_source
    assert "apply_member_discount_flag=False" in combined_source
    assert "record_trend_workflow_billing_event" in combined_source
    assert "trend_workflow_insufficient_credits_text" in combined_source
    assert "insufficient_balance" in combined_source
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
    assert "image.success" in shopai_callback_source
    assert "🎬 Biến ảnh thành video" in source

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
            "public image: off; public video: on",
            "gợi ý chuyển động/cảnh quay",
            "motion đơn giản/dễ tạo",
            "motion cinematic",
            "motion viral/tiktok style",
        "không tạo ảnh-video thật",
    ]:
        assert marker in joined
    assert "admin preview / content-only / no xu deducted" in joined
    billed_sections = bot.trend_video_flow_sections("affiliate AI tool cho người mới", billing_note=bot.trend_workflow_billed_note(70))
    billed_joined = "\n".join(billed_sections).lower()
    assert "70 xu" in billed_joined
    assert "tạo ảnh 50 xu" in billed_joined
    assert "tạo video 200 xu" in billed_joined
    assert "Bot chưa trừ Xu" in bot.TREND_VIDEO_WORKFLOW_PUBLIC_OFF_MESSAGE or "thử nghiệm nội bộ" in bot.TREND_VIDEO_WORKFLOW_PUBLIC_OFF_MESSAGE
    assert bot.TREND_VIDEO_WORKFLOW_PUBLIC_OFF_MESSAGE == "🧪 Tính năng tạo video theo trend đang thử nghiệm nội bộ, chưa mở công khai."
    breakdown = bot.trend_workflow_content_cost_breakdown()
    assert breakdown["trend_analysis"] == 20
    assert breakdown["script_storyboard"] == 30
    assert breakdown["prompt_pack"] == 20
    assert breakdown["total"] == 70
    assert breakdown["image_separate"] == 50
    assert breakdown["video_separate"] == 200
    assert "70 Xu" in bot.trend_workflow_content_confirm_text("affiliate AI", 200)
    assert "tvflow|confirm_content" in source
    assert "tvflow|cancel_content" in source
    assert "Đã hủy gói nội dung theo trend" in callback_source
    assert "image_to_video_prompt_choices_text" in callback_source
    assert "image_to_video_public_off_from_prompt_text" in callback_source
    assert "safe_edit_or_send" in callback_source

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
    quick_smoke_source = source_between(source, "async def run_quick_image_admin_smoke", "async def handle_quick_media_pending_text")
    frame_video_source = source_between(source, "async def cmd_frame_video_status", "async def run_quick_image_admin_smoke")
    message_source = source_between(source, "async def handle_message", "TELEGRAM_STARTUP_ERROR =")

    assert 'CommandHandler("create_media", cmd_create_media)' in source
    assert 'CommandHandler("quick_image_test", cmd_quick_image_test)' in source
    assert 'CommandHandler("quick_video_test", cmd_quick_video_test)' in source
    assert 'CommandHandler("frame_video_status", cmd_frame_video_status)' in source
    assert 'CommandHandler("tool_test_frame_video", cmd_tool_test_frame_video)' in source
    assert 'CallbackQueryHandler(handle_create_media_callback, pattern=r"^create_media\\|")' in source
    assert 'CallbackQueryHandler(handle_frame_video_callback, pattern=r"^framevideo\\|")' in source
    assert "def public_image_tier_selection_text" in source
    assert "def public_image_tier_keyboard" in source
    assert "def public_image_success_keyboard" in source
    assert "async def handle_public_image_prompt_pending_text" in source
    assert "def public_video_tier_selection_text" in source
    assert "def public_video_tier_keyboard" in source
    assert "def public_video_success_keyboard" in source
    assert "async def handle_public_video_prompt_pending_text" in source
    assert "media.creator_title" in helper_source
    assert "ADMIN_DEBUG_PUBLIC_ERRORS" in source
    assert "BOT COMMAND ERROR" not in source
    assert "BOT COMMAND DEBUG ERROR" in source
    assert "def safe_edit_or_send" in source
    assert bot.is_soft_telegram_edit_error(Exception("BadRequest: There is no text in the message to edit")) is True
    assert bot.is_soft_telegram_edit_error(Exception("RateLimitError")) is False
    safe_edit_source = source_between(source, "async def safe_edit_or_send", "async def handle_menu_callback")
    assert "Có lỗi nhỏ khi cập nhật màn hình" not in safe_edit_source
    assert "message.reply_text" in safe_edit_source
    assert 'InlineKeyboardButton("🎨 Media Creator", callback_data="menu|create_media")' not in source_between(source, "def main_menu_keyboard", "def language_choice_text")
    assert 'InlineKeyboardButton("👨‍💼 Hỗ trợ", callback_data="menu|support")' in source
    assert 'InlineKeyboardButton("🖼 Tạo ảnh AI", callback_data="menu|main_image")' in source
    assert 'InlineKeyboardButton("🎬 Tạo video AI", callback_data="menu|main_video")' in source
    assert 'InlineKeyboardButton("🔥 Video theo trend", callback_data="trendg|start")' in source
    assert 'InlineKeyboardButton("💬 Góp ý / Báo lỗi", callback_data="feedback|start")' in source
    assert 'InlineKeyboardButton("🎬 Tạo nội dung / Video", callback_data="menu|main_video")' not in source_between(source, "def main_menu_keyboard", "def language_choice_text")
    video_keyboard_source = source_between(source, "def main_video_keyboard", "def main_ai_keyboard")
    assert 'InlineKeyboardButton("🖼 Tạo ảnh nhanh", callback_data="create_media|quick_image")' in source
    assert 'ui_text(lang, "video.guided_flow")' not in video_keyboard_source
    assert 'ui_text(lang, "video.quick_admin_public")' in video_keyboard_source
    assert 'ui_text(lang, "video.trend_short")' in video_keyboard_source
    assert 'callback_data="trendg|start"' in video_keyboard_source
    assert 'callback_data="framevideo|start"' in video_keyboard_source
    assert 'ui_text(lang, "video.motion_short")' in video_keyboard_source
    assert 'ui_text(lang, "video.concept_short")' in video_keyboard_source or "Concept quảng cáo" in video_keyboard_source
    assert "create_media_open_text(query.from_user.id)" in source
    assert "create_media_open_text(uid)" in quick_source
    for callback_data in [
        "create_media|quick_image",
        "create_media|quick_video",
        "create_media|main",
        "create_media|cancel",
        "framevideo|start",
        "framevideo|done",
        "framevideo|confirm",
        "framevideo|cancel",
    ]:
        assert callback_data in source
        assert 'image_tier_choice_rows(lambda tier: f"create_media|image_tier_{tier}", lang)' in source
    assert 'callback_data=f"create_media|video_tier_{tier}"' in source
    create_media_keyboard_source = source_between(source, "def create_media_menu_keyboard", "def create_media_pricing_text")
    assert "create_media|trend" not in create_media_keyboard_source
    assert "create_media|pricing" not in create_media_keyboard_source
    assert "support_contact_text()" in source
    assert "clear_pending_start_notice(uid)" in source_between(source, "async def cmd_start", "async def cmd_menu")
    assert "common.pending_cancelled_main" in source_between(source, "def clear_pending_start_notice", "def shopaikey_generation_unavailable_message")
    assert 'IMAGE_BASE_COST_XU = env_int("IMAGE_BASE_COST_XU", 50)' in source
    assert 'VIDEO_BASE_COST_XU = env_int("VIDEO_BASE_COST_XU", 300)' in source
    assert 'MEDIA_PRICE_MULTIPLIER = env_int("MEDIA_PRICE_MULTIPLIER", 2)' in source
    assert 'IMAGE_LOW_COST_XU = env_int("IMAGE_LOW_COST_XU"' in source
    assert 'VIDEO_LOW_COST_XU = env_int("VIDEO_LOW_COST_XU", 200)' in source
    assert 'FRAME_VIDEO_PRICE_XU = env_int("FRAME_VIDEO_PRICE_XU", 50)' in source
    assert 'FRAME_VIDEO_PUBLIC_ENABLED = env_flag("FRAME_VIDEO_PUBLIC_ENABLED", "true")' in source
    assert 'WORKFLOW_TREND_ANALYSIS_COST_XU = env_int("WORKFLOW_TREND_ANALYSIS_COST_XU", 20)' in source
    assert 'WORKFLOW_SCRIPT_STORYBOARD_COST_XU = env_int("WORKFLOW_SCRIPT_STORYBOARD_COST_XU", 30)' in source
    assert 'WORKFLOW_PROMPT_PACK_COST_XU = env_int("WORKFLOW_PROMPT_PACK_COST_XU", 20)' in source
    assert "media.public_off" in helper_source
    assert "Giá chính thức được gom về một nơi duy nhất" in helper_source
    assert "set_quick_media_pending(uid, action)" in source
    assert 'set_quick_media_pending(uid, "quick_image_prompt")' not in source  # action is centralized through start/callback helpers.
    assert "quick_image_prompt" in source and "quick_video_prompt" in source
    assert 'set_quick_media_pending(uid, "quick_video_prompt")' in quick_source
    assert "video.quick_admin_prompt" in quick_source
    assert "video.admin_smoke_warning" in quick_source
    assert "public_video_off_options_text(lang)" in quick_source
    assert "public_image_prompt" in source
    assert "set_public_image_prompt_pending(uid, tier)" in source
    assert "clear_public_image_prompt_pending(uid)" in source
    assert "public_video_prompt" in source
    assert "set_public_video_prompt_pending(uid, tier)" in source
    assert "clear_public_video_prompt_pending(uid)" in source
    assert "handle_quick_media_pending_text(update, context)" in message_source
    assert "handle_feedback_pending_text(update, context)" in message_source
    assert "handle_public_image_prompt_pending_text(update, context)" in message_source
    assert "handle_public_video_prompt_pending_text(update, context)" in message_source
    assert "handle_creative_motion_pending_text(update, context)" in message_source
    assert "handle_cinematic_ad_pending_text(update, context)" in message_source
    photo_handler_source = source_between(source, "async def handle_photo", "async def handle_document_cache_only")
    assert "handle_frame_video_photo(update, context)" in photo_handler_source
    assert photo_handler_source.index("handle_frame_video_photo(update, context)") < photo_handler_source.index("remember_last_user_file(update)")
    assert message_source.index("handle_feedback_pending_text(update, context)") < message_source.index("handle_trend_video_flow_pending_text(update, context)")
    assert message_source.index("handle_public_image_prompt_pending_text(update, context)") < message_source.index("handle_quick_media_pending_text(update, context)")
    assert message_source.index("handle_public_video_prompt_pending_text(update, context)") < message_source.index("handle_quick_media_pending_text(update, context)")
    assert message_source.index("handle_creative_motion_pending_text(update, context)") < message_source.index("handle_quick_media_pending_text(update, context)")
    assert message_source.index("handle_cinematic_ad_pending_text(update, context)") < message_source.index("handle_quick_media_pending_text(update, context)")
    assert message_source.index("handle_quick_media_pending_text(update, context)") < message_source.index("is_probable_media_tags_text")
    assert "clear_quick_media_pending(uid)" in quick_source
    assert "clear_media_creator_pending_states(uid)" in source_between(source, "async def cmd_cancel", "async def cmd_create_media")
    assert 'CallbackQueryHandler(handle_feedback_callback, pattern=r"^feedback\\|")' in source
    assert 'CommandHandler("feedback",    cmd_admin_gopy)' in source
    assert "run_quick_image_admin_smoke" in quick_source
    assert "run_quick_video_admin_smoke" in quick_source
    assert "shopaikey_image_generate(prompt)" in quick_source
    assert "shopaikey_video_create_smoke_test(model, prompt)" in quick_source
    assert "render_frame_video_paths" in frame_video_source
    assert "shopaikey_video_create_smoke_test" not in frame_video_source
    assert "SHOPAIKEY_VIDEO_URL" not in frame_video_source
    assert "spend_fixed_credit_info" not in quick_smoke_source
    assert "deduct_dynamic_credit" not in quick_smoke_source
    assert "add_credit(" not in quick_smoke_source

    assert "PAYOS" not in quick_source.upper()
    assert 'ui_text(lang, "media.job_lock")' in quick_source
    assert "/quick_image_test" in quick_source and "/quick_video_test" in quick_source
    assert "No Xu deducted" in quick_source or "Không trừ Xu" in quick_source
    assert "Quick media menu: <code>enabled/guarded</code>" in source
    assert "Image tier public:" in source
    assert "Video tier public:" not in source
    assert "Public video generation:" in source
    assert "Public user can generate real video:" in source
    assert "Admin video smoke tests:" in source
    assert "Image pricing source: <code>tiered_media_pricing</code>" in source
    assert "Pricing mode: <code>{html.escape(pricing['billing_mode'])}</code>" in source
    assert "Price table source: <code>{html.escape(pricing['price_table_source'])}</code>" in source

    monkeypatch.setattr(bot, "MEDIA_PRICE_MULTIPLIER", 2)
    monkeypatch.setattr(bot, "IMAGE_LOW_PROVIDER_COST_XU", 161)
    monkeypatch.setattr(bot, "VIDEO_LOW_PROVIDER_COST_XU", 327)
    monkeypatch.setattr(bot, "IMAGE_LOW_COST_XU", 321)
    monkeypatch.setattr(bot, "VIDEO_LOW_COST_XU", 654)
    monkeypatch.setattr(bot, "IMAGE_STANDARD_COST_XU", 777)
    monkeypatch.setattr(bot, "IMAGE_STANDARD_WARRANTY_COST_XU", 799)
    monkeypatch.setattr(bot, "IMAGE_HIGH_COST_XU", 888)
    monkeypatch.setattr(bot, "IMAGE_HIGH_WARRANTY_COST_XU", 999)
    monkeypatch.setattr(bot, "IMAGE_TIER_LOW_ENABLED", True)
    monkeypatch.setattr(bot, "IMAGE_TIER_STANDARD_ENABLED", True)
    monkeypatch.setattr(bot, "IMAGE_TIER_HIGH_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_IMAGE_DEFAULT_TIER", "low")
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_IMAGE_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_VIDEO_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_TIER_LOW_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_TIER_BASIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_TIER_COMMON_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_TIER_STANDARD_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_TIER_HIGH_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_TIER_PREMIUM_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_PREMIUM_ADMIN_ONLY", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_DEFAULT_TIER", "low")
    monkeypatch.setattr(bot, "VIDEO_BASIC_COST_XU", 765)
    monkeypatch.setattr(bot, "VIDEO_COMMON_COST_XU", 876)
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
    assert pricing["image_tiers"]["standard_warranty"]["cost"] == 799
    assert pricing["image_tiers"]["standard_warranty"]["retry_warranty_count"] == 1
    assert pricing["image_tiers"]["high"]["cost"] == 888
    assert pricing["image_tiers"]["high_warranty"]["cost"] == 999
    assert pricing["image_tiers"]["high_warranty"]["retry_warranty_count"] == 1
    assert pricing["video_tiers"]["low"]["cost"] == 654
    assert pricing["video_tiers"]["basic"]["cost"] == 765
    assert pricing["video_tiers"]["common"]["cost"] == 876
    assert pricing["video_tiers"]["standard"]["cost"] == 999
    assert pricing["video_tiers"]["high"]["cost"] == 1111
    assert pricing["video_tiers"]["premium"]["cost"] == 2222
    assert pricing["quick_image_cost"] == 321
    assert pricing["quick_video_cost"] == 654
    assert bot.image_tier_cost_xu("low") == 321
    assert bot.image_tier_cost_xu("standard") == 777
    assert bot.image_tier_cost_xu("standard_warranty") == 799
    assert bot.image_tier_cost_xu("high") == 888
    assert bot.image_tier_cost_xu("high_warranty") == 999
    assert bot.image_tier_retry_warranty_count("standard_warranty") == 1
    assert bot.image_tier_retry_warranty_count("high") == 0
    assert bot.image_tier_payload("pro")["tier"] == "high"
    assert bot.image_tier_public_status_text() == "low:ON / standard:ON / standard_warranty:ON / high:ON / high_warranty:ON"
    assert bot.video_tier_cost_xu("low") == 654
    assert bot.video_tier_cost_xu("basic") == 765
    assert bot.video_tier_cost_xu("common") == 876
    assert bot.video_tier_cost_xu("standard") == 999
    assert bot.video_tier_cost_xu("high") == 1111
    assert bot.video_tier_payload("starter")["tier"] == "basic"
    assert bot.video_tier_payload("regular")["tier"] == "common"
    assert bot.video_tier_payload("vip")["tier"] == "premium"
    assert bot.video_tier_payload("premium")["admin_only"] is True
    assert bot.video_tier_payload("premium")["enabled"] is False
    assert bot.video_tier_public_status_text() == "low:ON / basic:ON / common:ON / standard:ON / high:ON / premium:OFF"
    callback_source = source_between(bot_source_text(), "async def handle_shopaikey_public_callback", "class TranslationProviderError")
    assert "shopaikey_recent_image_job_for_callback" in callback_source
    assert callback_source.index("shopaikey_recent_image_job_for_callback") < callback_source.index("common.expired_not_charged")
    tier_text = bot.public_image_tier_selection_text()
    assert "Bạn muốn tạo ảnh chất lượng nào" in tier_text
    tier_buttons = [button for row in bot.public_image_tier_keyboard().inline_keyboard for button in row]
    assert any(button.callback_data == "create_media|image_tier_low" for button in tier_buttons)
    assert any(button.callback_data == "create_media|image_tier_standard" for button in tier_buttons)
    assert any(button.callback_data == "create_media|image_tier_standard_warranty" for button in tier_buttons)
    assert any(button.callback_data == "create_media|image_tier_high" for button in tier_buttons)
    assert any(button.callback_data == "create_media|image_tier_high_warranty" for button in tier_buttons)
    assert any("Ảnh tiết kiệm" in button.text and "321 Xu" in button.text for button in tier_buttons)
    assert any("Ảnh tiêu chuẩn + bảo hành" in button.text and "799 Xu" in button.text for button in tier_buttons)
    assert "Gửi mô tả ảnh bạn muốn tạo" in bot.public_image_prompt_request_text("standard")
    assert "777 Xu" in bot.public_image_confirm_text("standard", "ảnh sản phẩm", 1000)
    assert "Gói này không kèm tạo lại miễn phí" in bot.public_image_confirm_text("standard", "ảnh sản phẩm", 1000)
    assert "Gói này kèm 1 lần tạo lại trong cùng yêu cầu" in bot.public_image_confirm_text("standard_warranty", "ảnh sản phẩm", 1000)
    image_confirm_16x9 = bot.public_image_confirm_text("standard", "ảnh sản phẩm", 1000, aspect_ratio="16:9")
    assert "Tỉ lệ khung hình" in image_confirm_16x9
    assert "16:9" in image_confirm_16x9
    assert "YouTube ngang" in image_confirm_16x9
    size_16x9 = bot.get_image_size_for_ratio("16:9", "standard", "shopaikey")
    assert size_16x9["size_string"] == "1344x768"
    assert size_16x9["width"] > size_16x9["height"]
    assert bot.get_image_size_for_ratio("9:16", "low", "shopaikey")["size_string"] == "768x1344"
    assert bot.get_image_size_for_ratio("16:9", "low", "gemini-2.5-flash-image")["size_string"] == "1344x768"
    assert bot.get_image_size_for_ratio("2:1", "low", "shopaikey")["provider_supported"] is False
    assert bot.infer_image_aspect_ratio_from_prompt("Product scene. Aspect ratio 4:5. No watermark.") == "4:5"
    assert bot.shopaikey_image_model_sequence("nano-banana", "gemini-2.5-flash-image,nano-banana,gemini-2.0-flash-preview-image-generation") == [
        "nano-banana",
        "gemini-2.5-flash-image",
        "gemini-2.0-flash-preview-image-generation",
    ]
    assert bot.shopaikey_image_model_invalid_error(429, "Model not found or invalid")
    assert bot.shopaikey_classify_error(429, "Model not found or invalid") == "FAIL_MODEL_INVALID"
    image_generate_source = source_between(bot_source_text(), "async def shopaikey_image_generate", "async def shopaikey_image_smoke_test")
    assert '"size": "9:16"' not in image_generate_source
    assert '"size": size_info["size_string"]' in image_generate_source
    assert "get_image_size_for_ratio" in image_generate_source
    assert "shopaikey_image_output_from_payload" in image_generate_source
    assert "models_tried" in image_generate_source
    assert "fallback_used" in image_generate_source
    assert "shopaikey_image_model_invalid_error" in image_generate_source
    image_smoke_source = source_between(bot_source_text(), "async def cmd_tool_test_shopaikey_image", "async def cmd_tool_test_shopaikey_video")
    assert "context.args" in image_smoke_source
    assert "Ratio requested" in image_smoke_source
    assert "Size sent" in image_smoke_source
    assert "Models tried" in image_smoke_source
    assert "Final model" in image_smoke_source
    assert "Fallback used" in image_smoke_source
    public_callback_source = source_between(bot_source_text(), "async def handle_shopaikey_public_callback", "class TranslationProviderError")
    assert "image_aspect_ratio" in public_callback_source
    assert "shopaikey_image_generate(prompt, model, aspect_ratio=image_aspect_ratio, tier=image_tier)" in public_callback_source
    assert "send_generated_image_result" in public_callback_source
    assert "FAIL_SEND_IMAGE" in public_callback_source
    assert "shopaikey_public_image_error_notified_at" in public_callback_source
    warranty_retry_source = source_between(bot_source_text(), "async def execute_image_warranty_retry", "def public_image_tier_selection_text")
    assert "retry_aspect_ratio = infer_image_aspect_ratio_from_prompt" in warranty_retry_source
    assert "shopaikey_image_generate(retry_prompt, model, aspect_ratio=retry_aspect_ratio)" in warranty_retry_source
    assert "send_generated_image_result" in warranty_retry_source
    success_buttons = [button for row in bot.public_image_success_keyboard(123, "low").inline_keyboard for button in row]
    assert any(button.callback_data == "tvflow|image_video_prompts_123" for button in success_buttons)
    assert any(button.callback_data == "create_media|image_tier_low" for button in success_buttons)
    assert any(button.text == "💾 Lưu ảnh/package" for button in success_buttons)
    assert len(success_buttons) == 7
    assert not any(button.callback_data == "tvflow|music_image_123" for button in success_buttons)
    missing_source_buttons = [button.text for row in bot.video_missing_source_keyboard().inline_keyboard for button in row]
    assert "🖼 Tạo lại ảnh khung chính" in missing_source_buttons
    assert "🎞 Tạo video từ prompt text thay vì ảnh" in missing_source_buttons
    assert "✍️ Sửa prompt ảnh" in missing_source_buttons
    assert "TOAN AAS chưa có đủ ảnh/prompt để tạo video" in bot.video_missing_source_text()
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    try:
        bot.init_db()
        warranty_job_id = bot.create_shopaikey_job(
            "u_warranty",
            "chat_warranty",
            "image",
            model="nano-banana",
            prompt="warranty prompt",
            status="IN_PROGRESS",
            admin_only=False,
            xu_cost_planned=250,
            retry_warranty_count=1,
        )
        assert bot.image_job_retry_warranty_remaining(warranty_job_id) == 0
        active_callback_job = bot.shopaikey_recent_image_job_for_callback("u_warranty")
        assert active_callback_job and int(active_callback_job["id"]) == warranty_job_id
        assert "đã được xử lý" in bot.shopaikey_processed_callback_text("vi", active_callback_job)
        assert "Bot chưa trừ Xu" not in bot.shopaikey_processed_callback_text("vi", active_callback_job)
        bot.update_shopaikey_job(job_id=warranty_job_id, status="SUCCESS")
        assert bot.image_job_retry_warranty_remaining(warranty_job_id) == 1
        success_callback_job = bot.shopaikey_recent_image_job_for_callback("u_warranty")
        assert success_callback_job and int(success_callback_job["id"]) == warranty_job_id
        warranty_buttons = [button for row in bot.public_image_success_keyboard(warranty_job_id, "standard_warranty").inline_keyboard for button in row]
        assert any(button.callback_data == f"tvflow|image_warranty_retry_{warranty_job_id}" for button in warranty_buttons)
        bot.update_shopaikey_job(job_id=warranty_job_id, retry_warranty_used=1)
        assert bot.image_job_retry_warranty_remaining(warranty_job_id) == 0
        exhausted_buttons = [button.text for row in bot.image_warranty_retry_exhausted_keyboard().inline_keyboard for button in row]
        assert "🖼 Tạo ảnh mới theo bảng giá" in exhausted_buttons
        assert "✍️ Sửa prompt ảnh" in exhausted_buttons
        assert "Bạn đã dùng hết 1 lần tạo lại bảo hành" in bot.image_warranty_retry_exhausted_text()
        conn = bot.db_connect()
        try:
            old_time = "2000-01-01 00:00:00"
            conn.execute("UPDATE shopaikey_jobs SET updated_at=?, created_at=? WHERE id=?", (old_time, old_time, warranty_job_id))
            conn.commit()
        finally:
            conn.close()
        assert bot.shopaikey_recent_image_job_for_callback("u_warranty", minutes=30) is None
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)

    video_tier_text = bot.public_video_tier_selection_text()
    assert "Bạn muốn tạo video chất lượng nào" in video_tier_text
    video_tier_buttons = [button for row in bot.public_video_tier_keyboard().inline_keyboard for button in row]
    assert any(button.callback_data == "create_media|video_tier_low" for button in video_tier_buttons)
    assert any(button.callback_data == "create_media|video_tier_basic" for button in video_tier_buttons)
    assert any(button.callback_data == "create_media|video_tier_common" for button in video_tier_buttons)
    assert any(button.callback_data == "create_media|video_tier_standard" for button in video_tier_buttons)
    assert any(button.callback_data == "create_media|video_tier_high" for button in video_tier_buttons)
    assert any(button.callback_data == "create_media|video_tier_premium" for button in video_tier_buttons)
    assert any("Video Trải Nghiệm" in button.text and "654 Xu" in button.text for button in video_tier_buttons)
    assert any("Video Cơ Bản" in button.text and "765 Xu" in button.text for button in video_tier_buttons)
    assert any("Video Phổ Thông" in button.text and "876 Xu" in button.text for button in video_tier_buttons)
    assert any("Video premium" in button.text and "liên hệ admin" in button.text for button in video_tier_buttons)
    assert "Gửi mô tả video bạn muốn tạo" in bot.public_video_prompt_request_text("standard")
    assert "999 Xu" in bot.public_video_confirm_text("standard", "video sản phẩm", 1500, aspect_ratio="9:16")
    assert "Tỉ lệ khung hình: <b>9:16</b>" in bot.public_video_confirm_text("standard", "video sản phẩm", 1500, aspect_ratio="9:16")
    assert "Public video" in bot.public_video_confirm_text("standard", "video sản phẩm", 1500, music_label="piano cinematic", aspect_ratio="4:5")
    assert bot.media_aspect_ratio_options("video") == ("9:16", "16:9", "1:1", "4:5", "3:4")
    assert "3:2" in bot.media_aspect_ratio_options("image")
    aspect_buttons = [button.callback_data for row in bot.public_media_aspect_ratio_keyboard("video").inline_keyboard for button in row]
    aspect_labels = [button.text for row in bot.public_media_aspect_ratio_keyboard("video").inline_keyboard for button in row]
    assert "create_media|video_aspect_9x16" in aspect_buttons
    assert "create_media|video_aspect_4x5" in aspect_buttons
    assert "📱 9:16 — TikTok/Reels/Shorts" in aspect_labels
    assert "📺 16:9 — YouTube ngang" in aspect_labels
    assert "⬛ 1:1 — Instagram/Facebook post" in aspect_labels
    assert "🖼 4:5 — Ads/Feed dọc" in aspect_labels
    assert "📷 3:4 — Chân dung/Sản phẩm" in aspect_labels
    image_aspect_buttons = [button.callback_data for row in bot.public_media_aspect_ratio_keyboard("image").inline_keyboard for button in row]
    image_aspect_labels = [button.text for row in bot.public_media_aspect_ratio_keyboard("image").inline_keyboard for button in row]
    assert "create_media|image_aspect_3x2" in image_aspect_buttons
    assert "🧾 3:2 — Ảnh ngang sản phẩm" in image_aspect_labels
    assert "🖥 4:3 — Slide/Màn hình cũ" in image_aspect_labels
    guarded_prompt = bot.video_tier_prompt_for_generation("phone screen product demo", "low", "9:16")
    assert "aspect ratio 9:16" in guarded_prompt
    assert "no text" in guarded_prompt.lower()
    assert "no caption" in guarded_prompt.lower()
    assert "no watermark" in guarded_prompt.lower()
    assert "screen clean or slightly blurred" in guarded_prompt.lower()
    package = bot.set_public_video_package_context("u_video", {
        "source": "cinematic_ad",
        "video_prompt": "cinematic product demo",
        "music_choice": {"type": "library", "label": "piano cinematic"},
    })
    assert bot.get_public_video_package_context("u_video")["video_prompt"] == "cinematic product demo"
    pending_payload = bot.public_video_pending_payload_from_package("low", package, "4:5")
    assert pending_payload["job_type"] == "video"
    assert pending_payload["video_tier"] == "low"
    assert pending_payload["base_cost"] == bot.video_tier_cost_xu("low")
    assert pending_payload["aspect_ratio"] == "4:5"
    assert "piano cinematic" in pending_payload["prompt"]
    assert "aspect ratio 4:5" in pending_payload["prompt"]
    assert bot.clear_public_video_package_context("u_video") is True
    assert "321 Xu" not in bot.create_media_pricing_text()
    assert "654 Xu" not in bot.create_media_pricing_text()
    pricing_text = "\n".join(bot.pricing_main_lines())
    assert "BẢNG GIÁ TOAN AAS" in pricing_text
    assert "Nạp Xu / Mệnh giá" in pricing_text
    assert "Hình ảnh AI" in pricing_text
    assert "Video AI" in pricing_text
    assert "Combo dịch vụ" in pricing_text
    assert "Workflow nội dung theo trend" in pricing_text
    assert "provider cost" not in pricing_text.lower()
    assert "tiered_media_pricing" in pricing_text
    price_keyboard_labels = [button.text for row in bot.pricing_main_keyboard("vi").inline_keyboard for button in row]
    assert price_keyboard_labels == [
        "💳 Nạp Xu",
        "🎬 Giá video",
        "🖼 Giá ảnh",
        "🎁 Combo",
        "📦 Gói của tôi",
        "📅 Gói tháng",
        "📜 Điều khoản Xu",
        "🏠 Menu chính",
    ]
    image_price_text = "\n".join(bot.pricing_image_lines())
    video_price_text = "\n".join(bot.pricing_video_lines())
    combo_price_text = "\n".join(bot.pricing_combo_lines())
    assert "Ảnh tiết kiệm: <b>321 Xu</b>" in image_price_text
    assert "Ảnh tiêu chuẩn: <b>777 Xu</b>" in image_price_text
    assert "Video Trải Nghiệm: <b>654 Xu</b>" in video_price_text
    assert "Video Cơ Bản: <b>765 Xu</b>" in video_price_text
    assert "Video Phổ Thông: <b>876 Xu</b>" in video_price_text
    assert "Video premium/admin-only: <b>admin-only / liên hệ admin</b>" in video_price_text
    assert "Combo Ưu Đãi TikTok" in combo_price_text
    assert "khuyến nghị 9:16" in combo_price_text
    assert "không cộng điểm nâng hạng/thưởng nạp" in combo_price_text
    combo_callbacks = [button.callback_data for row in bot.pricing_detail_keyboard("combo", "vi").inline_keyboard for button in row]
    assert "pkgbuy|combo|tiktok_99k" in combo_callbacks
    assert "pkgbuy|combo|posting_499k" in combo_callbacks
    xu_text = "\n".join(bot.pricing_xu_lines())
    assert xu_text.count("💰 <b>BẢNG GIÁ XU DỊCH VỤ</b>") == 1
    plan_text = "\n".join(bot.pricing_plans_lines())
    assert "Gói tháng là hạn mức dịch vụ theo tháng" in plan_text
    assert "📦 Gói của tôi" in plan_text
    assert "/buy_plan" not in plan_text
    plan_callbacks = [button.callback_data for row in bot.pricing_plans_keyboard("vi").inline_keyboard for button in row]
    assert "pkgbuy|monthly|starter_monthly" in plan_callbacks
    assert "pkgbuy|monthly|pro_monthly" in plan_callbacks
    assert "Giá tác vụ dịch tham khảo" not in plan_text
    assert "<code>/translate_voice</code>: từ 30–80 Xu/audio ngắn" not in plan_text
    assert "Music / Audio Factory" not in plan_text
    pricing_callback_source = source_between(source, "async def handle_pricing_callback", "def parse_chat_pro_args")
    assert "edit_or_send_pricing_lines(query, pricing_xu_lines_i18n(lang), pricing_xu_keyboard(lang))" in pricing_callback_source
    assert "send_pricing_lines(query.message, pricing_xu_lines()" not in pricing_callback_source
    start_labels = [button.text for row in bot.localized_main_menu_keyboard(False, "vi").inline_keyboard for button in row]
    assert "🎨 Media Creator" not in start_labels
    assert "🖼 Tạo ảnh AI" in start_labels
    assert "🎬 Tạo video AI" in start_labels
    assert "🔥 Video theo trend" not in start_labels
    assert "📝 Ghi chú / Tài liệu" in start_labels
    assert "🎙 Voice / Nhạc" in start_labels
    assert "🎞 Video" not in start_labels
    assert "👨‍💼 Hỗ trợ" in start_labels
    assert "💰 Nạp Xu / Bảng giá" in start_labels
    assert "💬 Góp ý / Báo lỗi" in start_labels
    for keyboard in [
        bot.main_menu_keyboard(False),
        bot.localized_main_menu_keyboard(False, "vi"),
        bot.localized_main_menu_keyboard(False, "en"),
        bot.localized_main_menu_keyboard(False, "zh"),
    ]:
        voice_rows = [row for row in keyboard.inline_keyboard if any(button.callback_data == "menu|main_music" for button in row)]
        assert voice_rows
    image_labels = [button.text for row in bot.main_image_keyboard("vi").inline_keyboard for button in row]
    assert "🖼 Tạo ảnh nhanh" in image_labels
    assert "💳 Xem bảng giá" not in image_labels
    assert "💰 Xem giá" not in image_labels
    assert "📞 Liên hệ admin" not in image_labels
    video_buttons = [button for row in bot.main_video_keyboard("vi").inline_keyboard for button in row]
    assert any(button.text == "🎬 Tạo video nhanh" and button.callback_data == "create_media|quick_video" for button in video_buttons)
    assert not any(button.text == "✨ Làm theo từng bước" for button in video_buttons)
    assert any(button.text == "🔥 Video theo trend" and button.callback_data == "trendg|start" for button in video_buttons)
    video_labels = [button.text for button in video_buttons]
    assert video_labels == [
        "🧩 Kịch bản → Ảnh → Video",
        "🎞 Ghép ảnh có sẵn thành video",
        "🎬 Tạo video nhanh",
        "🖼➡️🎬 Tạo video AI từ ảnh",
        "🔥 Video theo trend",
        "🧠 Concept quảng cáo",
        "🎥 Gợi ý chuyển động / prompt video",
        "🔙 Quay lại",
        "🏠 Menu chính",
    ]
    assert "🖼➡️🎬 Tạo video AI từ ảnh" in video_labels
    assert "✍️ Tạo prompt video" not in video_labels
    assert "💳 Xem bảng giá" not in video_labels
    assert "💰 Xem giá" not in video_labels
    assert "📞 Liên hệ admin" not in video_labels
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_VIDEO_ENABLED", False)
    vi_video_off = bot.public_video_off_options_text("vi")
    assert "Video thật chưa mở công khai" in vi_video_off
    assert "Bot chưa gọi API video" in vi_video_off
    assert "chưa trừ Xu" in vi_video_off
    en_video_off = bot.public_video_off_options_text("en")
    assert "Real video generation is not public yet" in en_video_off
    assert "has not called the video API" in en_video_off
    from_image_off = bot.image_to_video_public_off_prompt(0, "u_video_off", "vi")
    assert "Prompt image-to-video" in from_image_off
    assert "Bot chưa gọi API video" in from_image_off
    assert "shopaikey_video_create" not in from_image_off
    docs_labels = [button.text for row in bot.main_docs_keyboard("vi").inline_keyboard for button in row]
    assert "💰 Xem giá" not in docs_labels
    assert "📄 PDF sang Word" in docs_labels
    assert "🖼 Ảnh sang PDF" in docs_labels
    memory_labels = [button.text for row in bot.main_memory_keyboard("vi").inline_keyboard for button in row]
    assert "📄 Công cụ tài liệu" in memory_labels
    assert "📄 PDF sang Word" in memory_labels
    assert "🖼 Ảnh sang PDF" in memory_labels
    assert "🗜 Nén PDF" in memory_labels
    assert "✂️ Tách PDF" in memory_labels
    assert "🧩 Gộp PDF" in memory_labels
    assert [button.text for button in bot.main_memory_keyboard("vi").inline_keyboard[-1]] == ["🧩 Gộp PDF", "⬅️ Về menu chính"]
    merge_section, merge_hint = bot.menu_hint_text("hint_doc_merge_pdf")
    assert merge_section == "main_memory"
    assert "Công cụ gộp PDF đang bảo trì hoặc chưa bật" in merge_hint
    assert "chưa trừ Xu" in merge_hint
    memory_text = bot.menu_text_main_memory()
    assert "TÀI LIỆU" in memory_text
    assert "/doc_tools" in memory_text
    assert "/pdf_to_word" in memory_text
    assert "/image_to_pdf" in memory_text
    topup_labels = [button.text for row in bot.main_topup_keyboard("vi").inline_keyboard for button in row]
    assert "💰 Xem giá" not in topup_labels
    assert [[button.text for button in row] for row in bot.main_topup_keyboard("vi").inline_keyboard] == [
        ["💳 10k", "💳 20k"],
        ["💳 50k", "💳 100k"],
        ["💳 200k", "💳 500k"],
        ["🏦 Nạp thủ công", "🔙 Quay lại bảng giá"],
        ["🏠 Menu chính"],
    ]
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
    bot.set_public_image_prompt_pending("u6", "high")
    public_pending = bot.get_public_image_prompt_pending("u6")
    assert public_pending and public_pending["pending_action"] == "public_image_prompt"
    assert public_pending["tier"] == "high"
    assert bot.clear_public_image_prompt_pending("u6") is True
    bot.set_public_image_prompt_pending("u6", "standard")
    public_key = bot.public_image_pending_key("u6")
    bot.USER_PENDING[public_key]["created_at_ts"] = 0
    assert bot.get_public_image_prompt_pending("u6") is None
    assert public_key not in bot.USER_PENDING
    bot.set_public_video_prompt_pending("u6", "high")
    public_video_pending = bot.get_public_video_prompt_pending("u6")
    assert public_video_pending and public_video_pending["pending_action"] == "public_video_prompt"
    assert public_video_pending["tier"] == "high"
    assert bot.clear_public_video_prompt_pending("u6") is True
    bot.set_public_video_prompt_pending("u6", "standard")
    public_video_key = bot.public_video_pending_key("u6")
    bot.USER_PENDING[public_video_key]["created_at_ts"] = 0
    assert bot.get_public_video_prompt_pending("u6") is None
    assert public_video_key not in bot.USER_PENDING
    bot.set_quick_media_pending("u6", "quick_video_prompt")
    bot.USER_PENDING[key]["created_at_ts"] = 0
    assert bot.get_quick_media_pending("u6") is None
    assert key not in bot.USER_PENDING
    bot.set_quick_media_pending("u7", "quick_image_prompt")
    assert bot.create_media_open_text("u7").startswith("ℹ️ Đã hủy thao tác cũ")
    assert bot.get_quick_media_pending("u7") is None
    bot.set_public_image_prompt_pending("u7", "low")
    assert bot.create_media_open_text("u7").startswith("ℹ️ Đã hủy thao tác cũ")
    assert bot.get_public_image_prompt_pending("u7") is None
    bot.set_public_video_prompt_pending("u7", "low")
    assert bot.create_media_open_text("u7").startswith("ℹ️ Đã hủy thao tác cũ")
    assert bot.get_public_video_prompt_pending("u7") is None
    bot.set_trend_video_flow_pending("u7")
    assert bot.create_media_open_text("u7").startswith("ℹ️ Đã hủy thao tác cũ")
    assert bot.get_trend_video_flow_pending("u7") is None
    bot.set_quick_media_pending("u8", "quick_video_prompt")
    bot.set_public_image_prompt_pending("u8", "low")
    bot.set_public_video_prompt_pending("u8", "low")
    bot.set_trend_video_flow_pending("u8")
    assert bot.create_media_open_text("u8").startswith("ℹ️ Đã hủy thao tác cũ")
    assert bot.get_quick_media_pending("u8") is None
    assert bot.get_public_image_prompt_pending("u8") is None
    assert bot.get_public_video_prompt_pending("u8") is None
    assert bot.get_trend_video_flow_pending("u8") is None
    bot.set_quick_media_pending("u9", "quick_image_prompt")
    bot.set_public_image_prompt_pending("u9", "standard")
    bot.set_public_video_prompt_pending("u9", "standard")
    bot.set_creative_motion_pending("u9", "topic")
    bot.set_trend_video_flow_pending("u9")
    assert bot.clear_pending_start_notice("u9").startswith("❌ Đã hủy thao tác đang chờ")
    assert bot.get_quick_media_pending("u9") is None
    assert bot.get_public_image_prompt_pending("u9") is None
    assert bot.get_public_video_prompt_pending("u9") is None
    assert bot.get_creative_motion_pending("u9") is None
    assert bot.get_cinematic_ad_pending("u9") is None
    assert bot.get_trend_video_flow_pending("u9") is None


def test_frame_video_helper_defaults_and_state():
    assert bot.frame_video_ratio_payload("9x16")["width"] == 720
    assert bot.frame_video_ratio_payload("16x9")["height"] == 720
    assert bot.frame_video_ratio_payload("4x5")["height"] == 900
    assert bot.frame_video_duration_payload("standard")["seconds"] == 3.0
    assert bot.frame_video_effect_payload("fade")["token"] == "fade"
    assert bot.frame_video_effect_payload("pan")["token"] == "pan"
    assert bot.frame_video_effect_payload("slide")["token"] == "slide"
    assert bot.frame_video_effect_payload("random")["token"] == "random"
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(5)], "duration": "fast", "effect": "fade"}) == 50
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(7)], "duration": "fast", "effect": "fade"}) == 100
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(5)], "duration": "standard", "effect": "fade"}) == 70
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(10)], "duration": "standard", "effect": "zoom"}) == 120
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(5)], "duration": "slow", "effect": "zoom"}) == 110
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(10)], "duration": "slow", "effect": "pan"}) == 140
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(15)], "duration": "slow", "effect": "random"}) == 190
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(20)], "duration": "fast", "effect": "pan"}) == 290
    status = bot.frame_video_status_payload()
    assert int(status["price_xu"]) == int(bot.FRAME_VIDEO_BASE_2_5_XU)
    assert status["direct_render_enabled"] == bot.FRAME_VIDEO_DIRECT_RENDER_ENABLED
    assert status["require_local_worker"] == bot.FRAME_VIDEO_REQUIRE_LOCAL_WORKER
    local_worker_lines = "\n".join(bot.local_worker_status_lines())
    assert "Require Local Worker" in local_worker_lines
    assert "Direct Render Enabled" in local_worker_lines
    assert "Frame video render" in local_worker_lines
    assert "Telegram Bot Token for worker" in local_worker_lines
    assert int(status["base_6_10_xu"]) == int(bot.FRAME_VIDEO_BASE_6_10_XU)
    assert int(status["motion_effect_extra_xu"]) == int(bot.FRAME_VIDEO_MOTION_EFFECT_EXTRA_XU)
    assert int(status["random_effect_extra_xu"]) == int(bot.FRAME_VIDEO_RANDOM_EFFECT_EXTRA_XU)
    assert int(status["fast_extra_per_image_after_5_xu"]) == int(bot.FRAME_VIDEO_FAST_EXTRA_PER_IMAGE_AFTER_5_XU)
    assert int(status["max_images"]) == int(bot.FRAME_VIDEO_MAX_IMAGES)
    uid = "frame_video_unit"
    try:
        bot.clear_frame_video_state(uid)
        state = bot.set_frame_video_state(uid, {"step": "collect", "photos": [{"file_id": "a"}, {"file_id": "b"}]})
        assert state["type"] == "frame_video"
        assert bot.get_frame_video_state(uid)["step"] == "collect"
        job_id = bot.create_frame_video_job(uid, "chat", state, 70, "queued")
        assert bot.frame_video_job_for_user(job_id, uid)["status"] == "queued"
        bot.update_frame_video_job(job_id, status="success")
        assert "success" in bot.frame_video_job_status_text(bot.frame_video_job_for_user(job_id, uid))
        assert bot.clear_frame_video_state(uid) is True
        assert bot.get_frame_video_state(uid) == {}
    finally:
        bot.clear_frame_video_state(uid)


def test_frame_video_oom_guard_blocks_unsafe_render(monkeypatch):
    state = {
        "photos": [{"file_id": "a", "file_size": 1024}, {"file_id": "b", "file_size": 1024}],
        "duration": "fast",
        "effect": "fade",
    }
    monkeypatch.setattr(bot, "FRAME_VIDEO_ENABLED", True)
    monkeypatch.setattr(bot, "FRAME_VIDEO_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "FRAME_VIDEO_DIRECT_RENDER_ENABLED", False)
    monkeypatch.setattr(bot, "FRAME_VIDEO_REQUIRE_LOCAL_WORKER", True)
    monkeypatch.setattr(bot, "FRAME_VIDEO_MAX_INPUT_MB", 50)
    monkeypatch.setattr(bot, "FRAME_VIDEO_MAX_OUTPUT_SECONDS", 60)
    monkeypatch.setattr(bot, "FRAME_VIDEO_MAX_CONCURRENT_JOBS", 999)
    monkeypatch.setattr(bot, "local_worker_status_payload", lambda: {
        "enabled": True,
        "poll_enabled": True,
        "token_configured": True,
        "connected": False,
    })
    guard = bot.frame_video_runtime_guard(state, 987654321)
    assert guard["ok"] is False
    assert guard["reason"] == "worker_unavailable"
    assert "chưa trừ Xu" in guard["message"]

    monkeypatch.setattr(bot, "local_worker_status_payload", lambda: {
        "enabled": True,
        "poll_enabled": True,
        "token_configured": True,
        "connected": True,
    })
    guard = bot.frame_video_runtime_guard(state, 987654321)
    assert guard["action"] == "worker_queue"
    payload = json.loads(bot.frame_video_worker_payload("fv_test", 987654321, "chat", state, 50))
    assert payload["frame_job_id"] == "fv_test"
    assert payload["charged_amount"] == 50
    assert len(payload["photos"]) == 2

    monkeypatch.setattr(bot, "FRAME_VIDEO_DIRECT_RENDER_ENABLED", True)
    monkeypatch.setattr(bot, "FRAME_VIDEO_REQUIRE_LOCAL_WORKER", False)
    monkeypatch.setattr(bot, "FRAME_VIDEO_MAX_INPUT_MB", 1)
    too_large = dict(state)
    too_large["photos"] = [{"file_id": "a", "file_size": 2 * 1024 * 1024}, {"file_id": "b", "file_size": 1}]
    guard = bot.frame_video_runtime_guard(too_large, 987654321)
    assert guard["reason"] == "input_too_large"

    monkeypatch.setattr(bot, "FRAME_VIDEO_MAX_INPUT_MB", 50)
    monkeypatch.setattr(bot, "FRAME_VIDEO_MAX_OUTPUT_SECONDS", 2)
    guard = bot.frame_video_runtime_guard(state, 987654321)
    assert guard["reason"] == "output_too_long"


def test_shopaikey_chat_fallback_sequence_excludes_gpt5_and_retries(monkeypatch):
    monkeypatch.setattr(bot, "SHOPAIKEY_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "test-key")
    monkeypatch.setattr(bot, "SHOPAIKEY_BASE_URL", "https://example.test/v1")
    monkeypatch.setattr(bot, "SHOPAIKEY_CHAT_MODEL", "gpt-5-mini")
    monkeypatch.setattr(bot, "SHOPAIKEY_CHAT_FALLBACK_MODELS", "gpt-4o-mini,gpt-4.1-mini,qwen-plus,gpt-5-mini")
    sequence = bot.shopaikey_chat_model_sequence()
    assert "gpt-5-mini" not in sequence
    assert sequence[:3] == ["gpt-4o-mini", "gpt-4.1-mini", "qwen-plus"]

    calls = []

    async def fake_single_model(system_prompt, user_text, model, max_tokens=1200):
        calls.append(model)
        if model == "gpt-4o-mini":
            return {
                "status": "FAIL_CONTENT_EMPTY",
                "provider": "shopaikey",
                "model": model,
                "text": "",
                "http_status": 200,
                "latency_ms": 1,
                "error_class": "FAIL_CONTENT_EMPTY",
            }
        return {
            "status": "PASS",
            "provider": "shopaikey",
            "model": model,
            "text": "Xin chào TOAN AAS",
            "http_status": 200,
            "latency_ms": 2,
            "error_class": "",
        }

    monkeypatch.setattr(bot, "shopaikey_chat_completion_single_model", fake_single_model)
    monkeypatch.setattr(bot, "save_tool_test_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(bot, "save_shopaikey_chat_snapshot", lambda *args, **kwargs: None)
    result = asyncio.run(bot.shopaikey_chat_completion("system", "alo", "user-chat-test", max_tokens=80))
    assert result["ok"] is True
    assert result["provider"] == "shopaikey"
    assert result["model"] == "gpt-4.1-mini"
    assert calls == ["gpt-4o-mini", "gpt-4.1-mini"]


def test_public_ai_chat_router_uses_shopaikey_when_primary_missing(monkeypatch):
    monkeypatch.setattr(bot, "gemini_client", None)
    monkeypatch.setattr(bot, "openai_client", None)
    monkeypatch.setattr(bot, "shopaikey_public_chat_fallback_enabled", lambda: True)

    async def fake_shopaikey_chat(system_prompt, user_text, user_id, max_tokens=1200):
        return {
            "ok": True,
            "provider": "shopaikey",
            "model": "gpt-4o-mini",
            "text": "Xin chào, tôi có thể hỗ trợ bạn.",
            "attempts": [{"model": "gpt-4o-mini", "status": "PASS"}],
            "status": "PASS",
        }

    monkeypatch.setattr(bot, "shopaikey_chat_completion", fake_shopaikey_chat)
    monkeypatch.setattr(bot, "record_api_debug", lambda *args, **kwargs: None)
    result = asyncio.run(bot.call_ai_chat_with_fallback("system", "alo", "user-chat-router-test", max_tokens=80))
    assert result["ok"] is True
    assert result["provider"] == "shopaikey"
    assert "Xin chào" in result["text"]


def test_feedback_schema_migration_handles_legacy_table(monkeypatch, tmp_path):
    db_path = tmp_path / "legacy_feedback.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """CREATE TABLE feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                username TEXT,
                content TEXT,
                timestamp DATETIME
            )"""
        )
        conn.execute(
            "INSERT INTO feedback (user_id, username, content, timestamp) VALUES (?, ?, ?, ?)",
            ("legacy-user", "legacy", "old feedback stays", "2026-06-01 00:00:00"),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "DB_STARTUP_BACKUP_PATHS", set())
    bot.init_db()
    bot.init_db()

    conn = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(feedback)").fetchall()}
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(feedback)").fetchall()}
        row = conn.execute(
            "SELECT user_id, username, content, status, category, context FROM feedback WHERE user_id=?",
            ("legacy-user",),
        ).fetchone()
    finally:
        conn.close()

    assert {"status", "category", "context", "reviewed_at", "resolved_at"}.issubset(columns)
    assert "idx_feedback_status" in indexes
    assert "idx_feedback_category" in indexes
    assert "idx_feedback_user_id" in indexes
    assert row == ("legacy-user", "legacy", "old feedback stays", "new", "", "")


def test_customer_feedback_loop_state_and_storage(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    try:
        bot.init_db()
        conn = bot.db_connect()
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(feedback)").fetchall()}
        finally:
            conn.close()
        assert {"category", "context", "status", "reviewed_at", "resolved_at"}.issubset(columns)
        assert "Góp ý / Báo lỗi" in bot.feedback_start_text("vi")
        feedback_buttons = [button.callback_data for row in bot.feedback_category_keyboard("vi").inline_keyboard for button in row if button.callback_data]
        assert "feedback|cat|image_not_right" in feedback_buttons
        assert "feedback|cat|video_slow" in feedback_buttons
        assert "feedback|cancel" in feedback_buttons

        bot.USER_PENDING.pop(bot.feedback_pending_key("u_feedback"), None)
        bot.set_feedback_pending("u_feedback", "video_slow")
        pending = bot.get_feedback_pending("u_feedback")
        assert pending and pending["pending_action"] == "feedback"
        assert pending["category"] == "video_slow"

        class FakeUser:
            id = "u_feedback"
            username = "tester"
            first_name = "Tester"

        feedback_id = bot.store_customer_feedback(FakeUser(), "video_slow", "Video tạo hơi lâu", "trend_video_flow")
        assert feedback_id > 0
        conn = bot.db_connect()
        try:
            row = conn.execute("SELECT category, content, context, status FROM feedback WHERE id=?", (feedback_id,)).fetchone()
        finally:
            conn.close()
        assert row == ("video_slow", "Video tạo hơi lâu", "trend_video_flow", "new")
        assert bot.clear_feedback_pending("u_feedback") is True
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_public_flow_i18n_helpers_do_not_mix_vietnamese():
    vietnamese_fragments = [
        "Bạn", "Quay lại", "Hủy", "Menu chính", "Bảng giá", "Tài khoản", "Số dư",
        "Đã trừ", "vui lòng", "chưa trừ", "Tạo ảnh", "Tạo video", "Gợi ý",
        "Link giới thiệu", "Gói tháng", "không gọi", "trừ Xu", "Sản phẩm",
        "Thông điệp", "Phong cách", "Đã hủy",
    ]

    def flatten_keyboard_text(keyboard):
        return "\n".join(button.text for row in keyboard.inline_keyboard for button in row if getattr(button, "text", None))

    def assert_no_vi(text):
        leaked = [fragment for fragment in vietnamese_fragments if fragment in text]
        assert not leaked, leaked

    english_samples = [
        flatten_keyboard_text(bot.localized_main_menu_keyboard(False, "en")),
        flatten_keyboard_text(bot.main_video_keyboard("en")),
        flatten_keyboard_text(bot.main_image_keyboard("en")),
        flatten_keyboard_text(bot.main_profile_keyboard("en")),
        flatten_keyboard_text(bot.pricing_main_keyboard("en")),
        flatten_keyboard_text(bot.public_image_tier_keyboard("en")),
        flatten_keyboard_text(bot.public_video_tier_keyboard("en")),
        flatten_keyboard_text(bot.creative_motion_topic_keyboard("en")),
        flatten_keyboard_text(bot.cinematic_ad_message_keyboard("en")),
        flatten_keyboard_text(bot.cinematic_ad_style_keyboard("en")),
        flatten_keyboard_text(bot.cinematic_ad_continuation_keyboard("en")),
        flatten_keyboard_text(bot.trend_video_flow_keyboard("en")),
        "\n".join(bot.pricing_main_lines_i18n("en")),
        "\n".join(bot.pricing_xu_lines_i18n("en")),
        "\n".join(bot.pricing_plans_lines_i18n("en")),
        bot.public_image_tier_selection_text("en"),
        bot.public_image_prompt_request_text("standard", "en"),
        bot.public_image_confirm_text("standard", "turquoise product photo", 1000, "en"),
        bot.public_video_tier_selection_text("en"),
        bot.public_video_prompt_request_text("standard", "en"),
        bot.public_video_confirm_text("standard", "short product video", 1000, "en"),
        bot.public_image_provider_fail_message(50, True, "en"),
        bot.public_video_provider_fail_message(200, False, "en"),
        bot.creative_motion_topic_text("en"),
        bot.creative_motion_style_text("mini blender ad", "en"),
        bot.creative_motion_guide_text("mini blender product ad", "cinematic", "en"),
        bot.cinematic_ad_product_text("en"),
        bot.cinematic_ad_message_text("mini blender", "en"),
        bot.cinematic_ad_style_text("mini blender", "save time", "en"),
        bot.cinematic_ad_concept_text("mini blender", "save time", "cinematic", "en"),
        bot.cinematic_ad_continue_text({"product": "mini blender", "message": "save time", "style": "cinematic"}, "en"),
        bot.cinematic_ad_motion_from_concept_text({"product": "mini blender", "message": "save time", "style": "cinematic"}, "en"),
        bot.cinematic_ad_image_prompts_from_concept_text({"product": "mini blender", "message": "save time", "style": "cinematic"}, "en"),
        bot.cinematic_ad_video_prompt_from_concept_text({"product": "mini blender", "message": "save time", "style": "cinematic"}, "en"),
        bot.cinematic_ad_music_from_concept_text({"product": "mini blender", "message": "save time", "style": "cinematic"}, "en"),
        bot.cinematic_ad_video_from_concept_text({"product": "mini blender", "message": "save time", "style": "cinematic"}, "en"),
        flatten_keyboard_text(bot.cinematic_ad_locked_keyboard("en")),
        flatten_keyboard_text(bot.cinematic_ad_motion_keyboard("en")),
        flatten_keyboard_text(bot.cinematic_ad_image_prompt_keyboard("en")),
        flatten_keyboard_text(bot.cinematic_ad_video_prompt_keyboard("en")),
        flatten_keyboard_text(bot.cinematic_ad_video_off_keyboard("en")),
        "\n".join(bot.trend_video_flow_sections_i18n("mini blender product review", "Xu: 0 Xu — no charge.", "en")),
        bot.trend_workflow_content_confirm_text("mini blender", 1000, "en"),
        flatten_keyboard_text(bot.trend_workflow_content_confirm_keyboard("en")),
        bot.trend_workflow_insufficient_credits_text(10, 70, "en"),
        bot.trend_video_pending_prompt_text("en"),
        flatten_keyboard_text(bot.trend_video_pending_keyboard("en")),
    ]
    for sample in english_samples:
        assert_no_vi(str(sample))

    chinese_samples = [
        flatten_keyboard_text(bot.localized_main_menu_keyboard(False, "zh")),
        flatten_keyboard_text(bot.main_video_keyboard("zh")),
        flatten_keyboard_text(bot.main_image_keyboard("zh")),
        flatten_keyboard_text(bot.main_profile_keyboard("zh")),
        flatten_keyboard_text(bot.pricing_main_keyboard("zh")),
        flatten_keyboard_text(bot.public_image_tier_keyboard("zh")),
        flatten_keyboard_text(bot.public_video_tier_keyboard("zh")),
        flatten_keyboard_text(bot.creative_motion_topic_keyboard("zh")),
        flatten_keyboard_text(bot.cinematic_ad_message_keyboard("zh")),
        flatten_keyboard_text(bot.cinematic_ad_style_keyboard("zh")),
        flatten_keyboard_text(bot.cinematic_ad_continuation_keyboard("zh")),
        flatten_keyboard_text(bot.trend_video_flow_keyboard("zh")),
        "\n".join(bot.pricing_main_lines_i18n("zh")),
        "\n".join(bot.pricing_xu_lines_i18n("zh")),
        "\n".join(bot.pricing_plans_lines_i18n("zh")),
        bot.public_image_prompt_request_text("standard", "zh"),
        bot.public_video_prompt_request_text("standard", "zh"),
        bot.public_image_provider_fail_message(50, True, "zh"),
        bot.public_video_provider_fail_message(200, False, "zh"),
        bot.creative_motion_topic_text("zh"),
        bot.creative_motion_style_text("迷你搅拌机广告", "zh"),
        bot.creative_motion_guide_text("迷你搅拌机广告", "cinematic", "zh"),
        bot.cinematic_ad_product_text("zh"),
        bot.cinematic_ad_message_text("迷你搅拌机", "zh"),
        bot.cinematic_ad_style_text("迷你搅拌机", "节省时间", "zh"),
        bot.cinematic_ad_concept_text("迷你搅拌机", "节省时间", "cinematic", "zh"),
        bot.cinematic_ad_continue_text({"product": "迷你搅拌机", "message": "节省时间", "style": "cinematic"}, "zh"),
        bot.cinematic_ad_motion_from_concept_text({"product": "迷你搅拌机", "message": "节省时间", "style": "cinematic"}, "zh"),
        bot.cinematic_ad_image_prompts_from_concept_text({"product": "迷你搅拌机", "message": "节省时间", "style": "cinematic"}, "zh"),
        bot.cinematic_ad_video_prompt_from_concept_text({"product": "迷你搅拌机", "message": "节省时间", "style": "cinematic"}, "zh"),
        bot.cinematic_ad_music_from_concept_text({"product": "迷你搅拌机", "message": "节省时间", "style": "cinematic"}, "zh"),
        bot.cinematic_ad_video_from_concept_text({"product": "迷你搅拌机", "message": "节省时间", "style": "cinematic"}, "zh"),
        flatten_keyboard_text(bot.cinematic_ad_locked_keyboard("zh")),
        flatten_keyboard_text(bot.cinematic_ad_motion_keyboard("zh")),
        flatten_keyboard_text(bot.cinematic_ad_image_prompt_keyboard("zh")),
        flatten_keyboard_text(bot.cinematic_ad_video_prompt_keyboard("zh")),
        flatten_keyboard_text(bot.cinematic_ad_video_off_keyboard("zh")),
        "\n".join(bot.trend_video_flow_sections_i18n("迷你搅拌机产品广告", "Xu: 0 Xu — no charge.", "zh")),
        bot.trend_workflow_content_confirm_text("迷你搅拌机", 1000, "zh"),
        bot.trend_workflow_insufficient_credits_text(10, 70, "zh"),
        bot.trend_video_pending_prompt_text("zh"),
    ]
    for sample in chinese_samples:
        assert_no_vi(str(sample))

    assert bot.ui_text("en", "missing.translation.key.for.test") == "missing.translation.key.for.test"
    assert "Back" in bot.ui_text("en", "common.back")
    assert "返回" in bot.ui_text("zh", "common.back")
    assert "Quay lại" in bot.ui_text("vi", "common.back")


def test_account_referral_monthly_plan_guard_and_motion_guide(monkeypatch):
    source = bot_source_text()
    motion_source = source_between(source, "def creative_motion_pending_key", "TREND_VIDEO_WORKFLOW_PUBLIC_OFF_MESSAGE")
    ad_source = source_between(source, "def cinematic_ad_pending_key", "TREND_VIDEO_WORKFLOW_PUBLIC_OFF_MESSAGE")
    assert 'SHOPAIKEY_PUBLIC_VIDEO_ENABLED = env_flag("SHOPAIKEY_PUBLIC_VIDEO_ENABLED", _env("PUBLIC_VIDEO_GENERATION_ENABLED", "true"))' in source
    assert 'CREATIVE_MOTION_GUIDE_COST_XU = env_int("CREATIVE_MOTION_GUIDE_COST_XU", 0)' in source
    assert 'CallbackQueryHandler(handle_creative_motion_callback, pattern=r"^motion\\|")' in source
    assert 'CallbackQueryHandler(handle_cinematic_ad_callback, pattern=r"^adconcept\\|")' in source
    assert "shopaikey_image_generate" not in motion_source
    assert "shopaikey_video_create_smoke_test" not in motion_source
    assert "spend_fixed_credit_info" not in motion_source
    assert "shopaikey_image_generate" not in ad_source
    assert "shopaikey_video_create_smoke_test" not in ad_source
    assert "spend_fixed_credit_info" not in ad_source
    assert "deduct_dynamic_credit" not in ad_source

    assert bot.referral_link_for_user("123456", "toanaasbot") == "https://t.me/toanaasbot?start=ref_123456"
    profile_text_source = source_between(source, "def menu_text_main_profile", "def main_profile_keyboard")
    assert "🎁 <b>Link giới thiệu của bạn</b>" not in profile_text_source
    assert "referral_link_for_user(user_id" not in profile_text_source
    assert "Bấm nút bên dưới để xem link giới thiệu, quyền lợi và lịch sử" in profile_text_source
    assert "https://t.me/" not in profile_text_source
    profile_buttons = [button.text for row in bot.main_profile_keyboard("vi").inline_keyboard for button in row]
    assert "🎁 Link giới thiệu" in profile_buttons
    assert "📋 Cách nhận thưởng" in profile_buttons
    assert "👥 Người đã giới thiệu" in profile_buttons
    assert "Ghi nhận giới thiệu trước" in bot.referral_account_link_text("123456", "toanaasbot")
    assert "https://t.me/toanaasbot?start=ref_123456" in bot.referral_account_link_text("123456", "toanaasbot")

    plan_text = "\n".join(bot.pricing_plans_lines())
    assert "Gói tháng là hạn mức dịch vụ theo tháng" in plan_text
    assert "PayOS thanh toán thành công thì hạn mức tự lưu vào <b>📦 Gói của tôi</b>" in plan_text
    assert "📆 Starter Monthly" in plan_text
    assert "📆 Creator Monthly" in plan_text
    assert "📆 Shop Monthly" in plan_text
    assert "📆 Pro Monthly" in plan_text
    assert "Bot không yêu cầu khách gõ lệnh mua gói" in plan_text
    assert "/buy_plan" not in plan_text
    assert "Tiền mua gói tháng không tính vào tổng nạp" in plan_text

    topic_text = bot.creative_motion_topic_text()
    assert "Bạn muốn làm video về vấn đề gì" in topic_text
    assert "không gọi API ảnh/video thật" in topic_text
    motion_buttons = [button.text for row in bot.creative_motion_topic_keyboard().inline_keyboard for button in row]
    assert "Sản phẩm / quảng cáo" in motion_buttons
    assert "Affiliate / TikTok Shop" in motion_buttons
    assert "✍️ Nhập chủ đề khác" in motion_buttons
    style_text = bot.creative_motion_style_text("video quảng cáo AI tool cho affiliate")
    assert "Bạn muốn phong cách nào" in style_text
    guide = bot.creative_motion_guide_text("video quảng cáo AI tool cho người mới làm affiliate", "tiktok").lower()
    assert "0–3s" in guide
    assert "3–6s" in guide
    assert "6–12s" in guide
    assert "12–15s" in guide
    assert "prompt ảnh đầu vào" in guide
    assert "prompt video motion" in guide
    assert "text overlay" in guide
    assert "voiceover ngắn" in guide
    assert "cta" in guide

    bot.USER_PENDING.pop(bot.creative_motion_pending_key("u_motion"), None)
    bot.set_creative_motion_pending("u_motion", "topic")
    pending = bot.get_creative_motion_pending("u_motion")
    assert pending and pending["pending_action"] == "creative_motion"
    assert pending["step"] == "topic"
    bot.set_creative_motion_pending("u_motion", "style", "AI tool affiliate")
    pending = bot.get_creative_motion_pending("u_motion")
    assert pending and pending["topic"] == "AI tool affiliate"
    assert bot.clear_creative_motion_pending("u_motion") is True

    trend_prompt = bot.trend_video_pending_prompt_text()
    assert "Bạn muốn làm video theo trend cho sản phẩm/dịch vụ/chủ đề gì" in trend_prompt
    assert "mục tiêu + phong cách + nền tảng" not in trend_prompt
    bot.USER_PENDING.pop(bot.trend_video_pending_key("u_trend"), None)
    bot.set_trend_video_flow_pending("u_trend", "trend_source", topic="máy xay sinh tố mini")
    pending = bot.get_trend_video_flow_pending("u_trend")
    assert pending and pending["pending_action"] == "trend_video_flow"
    assert pending["topic"] == "máy xay sinh tố mini"
    source_text = bot.trend_guided_trend_source_text("máy xay sinh tố mini")
    assert "Bạn muốn TOAN AAS lấy trend theo cách nào" in source_text
    source_callbacks = [button.callback_data for row in bot.trend_guided_trend_source_keyboard().inline_keyboard for button in row]
    assert "trendg|trend_source_popular" in source_callbacks
    assert "trendg|trend_source_search" in source_callbacks
    assert "trendg|trend_source_custom" in source_callbacks
    assert "trendg|trend_source_skip" in source_callbacks
    bot.set_trend_video_flow_pending("u_trend", "trend_choices", topic="máy xay sinh tố mini", trend_source="popular")
    trend_text = bot.trend_guided_trend_choices_text("máy xay sinh tố mini")
    assert "Chọn 1 trong 3 trend video" in trend_text
    assert "Trend before/after" in trend_text
    assert "Trend POV / tình huống đời thường" in trend_text
    assert "Trend quick tips / mẹo nhanh" in trend_text
    assert "Trend live từ internet sẽ mở sau" in trend_text
    trend_callbacks = [button.callback_data for row in bot.trend_guided_trend_choices_keyboard().inline_keyboard for button in row]
    assert "trendg|trend_select_1" in trend_callbacks
    assert "trendg|trend_select_2" in trend_callbacks
    assert "trendg|trend_select_3" in trend_callbacks
    assert "trendg|trend_source_popular" in trend_callbacks
    selected_trend_text = bot.trend_guided_selected_trend_text(bot.get_trend_video_flow_pending("u_trend") or {}, 1)
    assert "Đã chọn trend" in selected_trend_text
    assert "Bot sẽ dùng trend này để tạo concept/chuyển động/prompt ảnh/prompt video" in selected_trend_text
    motion_callbacks = [button.callback_data for row in bot.trend_guided_motion_choices_keyboard().inline_keyboard for button in row]
    assert "trendg|motion_select_1" in motion_callbacks
    assert "trendg|motion_select_2" in motion_callbacks
    assert "trendg|motion_select_3" in motion_callbacks
    image_callbacks = [button.callback_data for row in bot.trend_guided_image_prompt_choices_keyboard().inline_keyboard for button in row]
    assert "trendg|image_prompt_select_1" in image_callbacks
    assert "trendg|image_prompt_select_2" in image_callbacks
    assert "trendg|image_prompt_select_3" in image_callbacks
    video_callbacks = [button.callback_data for row in bot.trend_guided_video_prompt_choices_keyboard().inline_keyboard for button in row]
    assert "trendg|video_prompt_select_1" in video_callbacks
    assert "trendg|video_prompt_select_2" in video_callbacks
    assert "trendg|video_prompt_select_3" in video_callbacks
    music_callbacks = [button.callback_data for row in bot.trend_guided_music_suggestions_keyboard().inline_keyboard for button in row]
    assert "trendg|music_select_1" in music_callbacks
    assert "trendg|music_select_2" in music_callbacks
    assert "trendg|music_select_3" in music_callbacks
    trend_music_selected_buttons = [button.text for row in bot.trend_guided_music_selected_keyboard().inline_keyboard for button in row]
    assert "✅ Chốt nhạc này" in trend_music_selected_buttons
    assert "🎬 Tạo video / chốt video với nhạc này" in trend_music_selected_buttons
    assert "🚫 Bỏ nhạc và tạo video không nhạc" in trend_music_selected_buttons
    assert "🎞 Quay lại prompt video" in trend_music_selected_buttons
    trend_library_followup_buttons = [button.text for row in bot.selected_music_video_followup_keyboard("trend_guided").inline_keyboard for button in row]
    assert "🎬 Tạo video / chốt video với nhạc này" in trend_library_followup_buttons
    assert "🚫 Bỏ nhạc và tạo video không nhạc" in trend_library_followup_buttons
    trend_ai_music_buttons = [button.text for row in bot.trend_guided_music_ai_selected_keyboard().inline_keyboard for button in row]
    assert "🎬 Tạo video / chốt video với prompt nhạc này" in trend_ai_music_buttons
    video_off_text = bot.trend_guided_video_public_off_text(bot.get_trend_video_flow_pending("u_trend") or {})
    assert "Tạo video thật chưa mở công khai" in video_off_text
    assert "chưa trừ Xu" in video_off_text
    bot.USER_PENDING.pop(bot.trend_video_pending_key("u_trend_en"), None)
    bot.set_trend_video_flow_pending(
        "u_trend_en",
        "video_prompt_selected",
        topic="mini blender",
        trend_choice=1,
        motion_choice=1,
        image_prompt_choice=1,
        video_prompt_choice=1,
    )
    english_state = bot.get_trend_video_flow_pending("u_trend_en") or {}
    english_image_prompt = bot.trend_guided_image_prompt_for_index(english_state, 1, "en")
    english_video_prompt = bot.trend_guided_video_prompt_for_index(english_state, 1, "en")
    english_video_off = bot.trend_guided_video_public_off_text(english_state, "en")
    assert "Main product image" in english_image_prompt
    assert "Video prompt 5 seconds" in english_video_prompt
    assert "Real video generation is not public yet" in english_video_off
    assert "Ảnh" not in english_image_prompt
    assert "Gợi ý video" not in english_video_prompt
    assert "Tạo video thật chưa mở công khai" not in english_video_off
    assert "callback_data=\"trendg|start\"" in source
    assert "CallbackQueryHandler(handle_trend_guided_callback, pattern=r\"^trendg\\|\")" in source

    product_text = bot.cinematic_ad_product_text()
    assert "Bạn muốn làm quảng cáo cho sản phẩm/dịch vụ gì" in product_text
    assert "không gọi API ảnh/video thật" in product_text
    ad_buttons = [button.text for row in bot.cinematic_ad_message_keyboard().inline_keyboard for button in row]
    assert "Thời gian / ký ức" in ad_buttons
    assert "Before / After" in ad_buttons
    assert "✍️ Nhập thông điệp khác" in ad_buttons
    assert "⏭ Bỏ qua" in ad_buttons
    ad_callback_data = [button.callback_data for row in bot.cinematic_ad_message_keyboard().inline_keyboard for button in row]
    assert "adconcept|message|skip" in ad_callback_data
    assert bot.cinematic_ad_default_message() == "giới thiệu sản phẩm/dịch vụ rõ ràng, dễ hiểu, tạo sự tin tưởng và kêu gọi hành động nhẹ nhàng."
    style_buttons = [button.text for row in bot.cinematic_ad_style_keyboard().inline_keyboard for button in row]
    assert "🎬 Điện ảnh cảm xúc" in style_buttons
    assert "🖤 Đen trắng cao cấp" in style_buttons
    assert "📱 Viral TikTok/Reels" in style_buttons
    assert "🛒 Bán hàng trực tiếp" in style_buttons
    assert "👤 UGC đời thường" in style_buttons
    assert "🚁 Góc bay / quay lướt" in style_buttons
    assert "🧊 Hé lộ sản phẩm 3D" in style_buttons
    assert "⏭ Bỏ qua" in style_buttons
    style_callback_data = [button.callback_data for row in bot.cinematic_ad_style_keyboard().inline_keyboard for button in row]
    assert "adconcept|concept_style_cinematic" in style_callback_data
    assert "adconcept|concept_style_luxury_bw" in style_callback_data
    assert "adconcept|concept_style_viral" in style_callback_data
    assert "adconcept|concept_style_direct_sales" in style_callback_data
    assert "adconcept|concept_style_ugc" in style_callback_data
    assert "adconcept|concept_style_fpv" in style_callback_data
    assert "adconcept|concept_style_product_reveal" in style_callback_data
    assert "adconcept|concept_style_skip" in style_callback_data
    assert "adconcept|style|skip" not in style_callback_data
    assert bot.normalize_cinematic_ad_style_code("luxury_bw") == "bw_luxury"
    assert bot.normalize_cinematic_ad_style_code("product_reveal") == "product_reveal"
    assert bot.normalize_cinematic_ad_style_code("skip") == "direct_sales"
    assert bot.cinematic_ad_expired_session_text() == "⚠️ Phiên làm việc đã hết hạn. Vui lòng bắt đầu lại từ menu."
    for style_code in ["cinematic", "bw_luxury", "viral", "direct_sales", "ugc", "fpv", "product_reveal"]:
        concept_text = bot.cinematic_ad_concept_text("máy xay sinh tố mini", bot.cinematic_ad_default_message(), style_code)
        assert len(concept_text) > 3900
        assert all(len(chunk) <= 3600 for chunk in bot.split_telegram_html_text(concept_text))
    continuation_buttons = [button.text for row in bot.cinematic_ad_continuation_keyboard().inline_keyboard for button in row]
    assert "1️⃣ Chọn gợi ý 1" in continuation_buttons
    assert "2️⃣ Chọn gợi ý 2" in continuation_buttons
    assert "3️⃣ Chọn gợi ý 3" in continuation_buttons
    assert "✅ Hoàn tất / Chốt concept này" in continuation_buttons
    assert "🔁 Tạo lại 3 gợi ý" in continuation_buttons
    assert "✍️ Sửa concept" in continuation_buttons
    locked_buttons = [button.text for row in bot.cinematic_ad_locked_keyboard().inline_keyboard for button in row]
    assert "🖼 Ảnh / Prompt ảnh" in locked_buttons
    assert "🎞 Tạo prompt video từ concept này" in locked_buttons
    assert "🎬 Tạo video từ concept này" in locked_buttons
    assert "🎵 Nhạc / Âm thanh" in locked_buttons
    motion_choice_buttons = [button.text for row in bot.cinematic_ad_motion_choices_keyboard().inline_keyboard for button in row]
    assert "1️⃣ Chọn gợi ý 1" in motion_choice_buttons
    assert "2️⃣ Chọn gợi ý 2" in motion_choice_buttons
    assert "3️⃣ Chọn gợi ý 3" in motion_choice_buttons
    assert "🔙 Quay lại concept đã chốt" in [button.text for row in bot.cinematic_ad_motion_keyboard().inline_keyboard for button in row]
    assert "✅ Lưu hướng chuyển động" in [button.text for row in bot.cinematic_ad_motion_keyboard().inline_keyboard for button in row]
    image_choice_buttons = [button.text for row in bot.cinematic_ad_image_prompt_choices_keyboard().inline_keyboard for button in row]
    assert "1️⃣ Chọn gợi ý 1" in image_choice_buttons
    assert "2️⃣ Chọn gợi ý 2" in image_choice_buttons
    assert "3️⃣ Chọn gợi ý 3" in image_choice_buttons
    selected_image_buttons = [button.text for row in bot.cinematic_ad_image_prompt_selected_keyboard(1).inline_keyboard for button in row]
    assert "✅ Lưu prompt ảnh" in selected_image_buttons
    assert any("Ảnh tiết kiệm" in label for label in selected_image_buttons)
    assert any("Ảnh tiêu chuẩn + bảo hành" in label and "250 Xu" in label for label in selected_image_buttons)
    assert any("Ảnh chất lượng cao + bảo hành" in label and "500 Xu" in label for label in selected_image_buttons)
    video_choice_buttons = [button.text for row in bot.cinematic_ad_video_prompt_choices_keyboard().inline_keyboard for button in row]
    assert "1️⃣ Chọn gợi ý 1" in video_choice_buttons
    assert "2️⃣ Chọn gợi ý 2" in video_choice_buttons
    assert "3️⃣ Chọn gợi ý 3" in video_choice_buttons
    selected_video_buttons = [button.text for row in bot.cinematic_ad_video_prompt_selected_keyboard(1).inline_keyboard for button in row]
    assert "✅ Lưu prompt video" in selected_video_buttons
    assert "🎬 Tạo video thật từ prompt này" in selected_video_buttons
    music_choice_buttons = [button.text for row in bot.cinematic_ad_music_suggestion_keyboard().inline_keyboard for button in row]
    assert "1️⃣ Chọn gợi ý 1" in music_choice_buttons
    assert "2️⃣ Chọn gợi ý 2" in music_choice_buttons
    assert "3️⃣ Chọn gợi ý 3" in music_choice_buttons
    music_selected_buttons = [button.text for row in bot.cinematic_ad_music_selected_keyboard().inline_keyboard for button in row]
    assert "✅ Chốt nhạc này" in music_selected_buttons
    assert "🎬 Tạo video / chốt video với nhạc này" in music_selected_buttons
    assert "🚫 Bỏ nhạc và tạo video không nhạc" in music_selected_buttons
    assert "🎞 Quay lại prompt video" in music_selected_buttons
    assert "🎵 Chọn nhạc khác" in music_selected_buttons
    no_music_buttons = [button.text for row in bot.cinematic_ad_no_music_keyboard().inline_keyboard for button in row]
    assert "🎬 Chốt video không nhạc" in no_music_buttons
    assert "🎵 Chọn nhạc lại" in no_music_buttons
    package_pending_buttons = [button.text for row in bot.cinematic_ad_video_package_pending_keyboard().inline_keyboard for button in row]
    assert "✅ Lưu bản chốt video" in package_pending_buttons
    assert "🎵 Đổi nhạc" in package_pending_buttons
    assert "🎵 Tìm nhạc trong kho" not in music_selected_buttons
    assert "🤖 Prompt tạo nhạc AI" not in music_selected_buttons
    assert "💡 Gợi ý thể loại nhạc" in [button.text for row in bot.cinematic_ad_music_menu_keyboard().inline_keyboard for button in row]
    assert "adconcept|motion_current" in ad_source
    assert "adconcept|image_menu" in ad_source
    assert "adconcept|video_prompt_current" in ad_source
    assert "adconcept|video_current" in ad_source
    assert "adconcept|music_menu" in ad_source
    assert "adconcept|image_prompt_current" in ad_source
    assert "adconcept|image_prompt_choice|1" in ad_source
    assert "adconcept|video_prompt_current" in ad_source
    assert "adconcept|video_prompt_choice|1" in ad_source
    assert "adconcept|music_choice|1" in ad_source
    assert 'image_tier_choice_rows(lambda tier: f"adconcept|image_ai_tier|1|{tier}", lang)' in ad_source
    assert "adconcept|create_video_current" in ad_source
    assert "adconcept|edit_current" in ad_source
    assert "send_or_confirm_trend_video_flow_from_callback" in ad_source
    assert "safe_edit_or_send_long_html" in source
    ad_concept = bot.cinematic_ad_concept_text("máy xay sinh tố mini", "tiết kiệm thời gian", "cinematic").lower()
    assert "big idea" in ad_concept
    assert "brand story" in ad_concept
    assert "script 15s / 30s / 60s" in ad_concept
    assert "storyboard từng cảnh" in ad_concept
    assert "shot list cinematic" in ad_concept
    assert "prompt ảnh từng cảnh" in ad_concept
    assert "prompt video motion từng cảnh" in ad_concept
    assert "gợi ý nhạc/mood" in ad_concept
    assert "cta" in ad_concept
    assert "không gọi api ảnh/video thật" in ad_concept
    assert "3 hướng ý tưởng để chọn" in ad_concept
    bot.USER_PENDING.pop(bot.cinematic_ad_pending_key("u_ad"), None)
    bot.set_cinematic_ad_pending("u_ad", "product")
    pending = bot.get_cinematic_ad_pending("u_ad")
    assert pending and pending["pending_action"] == "cinematic_ad_concept"
    assert pending["step"] == "product"
    bot.set_cinematic_ad_pending("u_ad", "message", "máy xay sinh tố mini")
    pending = bot.get_cinematic_ad_pending("u_ad")
    assert pending and pending["product"] == "máy xay sinh tố mini"
    bot.set_cinematic_ad_pending("u_ad", "style", "máy xay sinh tố mini", "tiết kiệm thời gian")
    pending = bot.get_cinematic_ad_pending("u_ad")
    assert pending and pending["message"] == "tiết kiệm thời gian"
    bot.set_cinematic_ad_pending("u_ad", "edit", "máy xay sinh tố mini", "tiết kiệm thời gian", "cinematic")
    pending = bot.get_cinematic_ad_pending("u_ad")
    assert pending and pending["style"] == "cinematic"
    assert bot.clear_cinematic_ad_pending("u_ad") is True
    concept = bot.save_cinematic_ad_concept("u_ad", "máy xay sinh tố mini", "tiết kiệm thời gian", "cinematic")
    latest = bot.get_latest_cinematic_ad_concept("u_ad")
    assert latest and latest["product"] == "máy xay sinh tố mini"
    assert "concept quảng cáo" in latest["topic"]
    locked = bot.lock_latest_cinematic_ad_concept("u_ad")
    assert locked and locked["locked"] is True
    assert "dùng lại dữ liệu concept hiện tại" in bot.cinematic_ad_continue_text(concept).lower()
    motion_from_concept = bot.cinematic_ad_motion_from_concept_text(concept).lower()
    assert "hướng chuyển động" in motion_from_concept
    assert "ý tưởng video 15 giây" in motion_from_concept
    assert "chuyển động camera" in motion_from_concept
    assert "không gọi api video thật" in motion_from_concept
    motion_choices = bot.cinematic_ad_motion_choices_text(concept).lower()
    assert "1. chuyển động đơn giản" in motion_choices
    assert "2. chuyển động điện ảnh" in motion_choices
    assert "3. chuyển động tiktok/reels" in motion_choices
    image_prompts = bot.cinematic_ad_image_prompts_from_concept_text(concept).lower()
    assert "prompt ảnh khung chính từ concept này" in image_prompts
    assert "prompt ảnh 1: ảnh sản phẩm chính" in image_prompts
    assert "prompt ảnh 2: ảnh bối cảnh sử dụng" in image_prompts
    assert "điều cần tránh" in image_prompts
    assert "đã chọn prompt ảnh 1" in bot.cinematic_ad_selected_image_prompt_text(concept, 1).lower()
    video_prompts = bot.cinematic_ad_video_prompt_from_concept_text(concept).lower()
    assert "gợi ý video 5 giây" in video_prompts
    assert "dùng prompt này để tạo video thật" in video_prompts
    assert "điều cần tránh" in video_prompts
    assert "không tạo chữ/text/logo giả" in video_prompts
    assert "đã chọn prompt video 1" in bot.cinematic_ad_selected_video_prompt_text(concept, 1).lower()
    music_suggestions = bot.cinematic_ad_music_from_concept_text(concept).lower()
    assert "bạn có muốn thêm nhạc không" in music_suggestions
    assert "1. nhạc điện ảnh cảm xúc" in music_suggestions
    assert "2. nhạc hiện đại/công nghệ" in music_suggestions
    assert "3. nhạc tiktok/reels" in music_suggestions
    assert "đã chọn hướng nhạc 1" in bot.cinematic_ad_music_choice_text(concept, 1).lower()
    assert "tạo nhạc ai/ghép nhạc sẽ mở sau" in bot.ui_text("vi", "concept.music_saved_next").lower()
    no_music_text = bot.cinematic_ad_no_music_selected_text(concept).lower()
    assert "đã chọn không thêm nhạc" in no_music_text
    package = bot.save_latest_video_package("u_ad", bot.build_cinematic_ad_video_package("u_ad", concept, no_music=True))
    assert package["source"] == "cinematic_ad"
    assert package["no_music"] is True
    assert "video thật chưa mở công khai" in bot.cinematic_ad_video_public_off_package_text(package).lower()
    assert "đã chốt bản video" in bot.cinematic_ad_video_package_saved_text(package).lower()
    video_from_concept = bot.cinematic_ad_video_from_concept_text(concept).lower()
    assert "tạo video thật chưa mở công khai" in video_from_concept
    assert "prompt video đã lưu" in video_from_concept
    assert "không gọi api video và không trừ xu" in video_from_concept
    assert "đã hoàn tất luồng sáng tạo" in bot.cinematic_ad_finalize_text(concept).lower()

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    try:
        bot.init_db()
        conn = bot.db_connect()
        try:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(plan_purchases)").fetchall()}
            assert {"user_id", "plan_code", "purchase_month", "purchase_count", "order_code", "status"}.issubset(cols)
            conn.execute(
                "INSERT OR REPLACE INTO member_tier_overrides (user_id, tier, reason, updated_at) VALUES (?,?,?,?)",
                ("9001", "gold", "unit test", bot.now_text()),
            )
            conn.execute(
                "INSERT OR REPLACE INTO member_tier_overrides (user_id, tier, reason, updated_at) VALUES (?,?,?,?)",
                ("9002", "silver", "unit test", bot.now_text()),
            )
            conn.commit()
        finally:
            conn.close()

        assert bot.user_can_buy_plan("9003", "starter")[0] is False
        assert bot.user_can_buy_plan("9002", "starter")[0] is True
        assert bot.user_can_buy_plan("9001", "pro")[0] is True
        assert bot.can_purchase_monthly_plan("9001", "creator")[0] is True
        conn = bot.db_connect()
        try:
            info = bot.activate_user_plan_conn(conn, "9001", "creator", order_code="order_creator", source="payos")
            conn.commit()
        finally:
            conn.close()
        assert info["plan_id"] == "creator"
        assert bot.can_purchase_monthly_plan("9001", "creator")[0] is False
        assert "Mỗi gói chỉ mua 1 lần/tháng" in bot.can_purchase_monthly_plan("9001", "creator")[1]
        assert bot.can_purchase_monthly_plan("9001", "pro")[0] is True
        credits, total_spent, _ = bot.get_user("9001")
        assert int(total_spent or 0) == 0

        ref_result = bot.register_referral("9004", "9001", user_existed_before=False)
        assert ref_result["registered"] is True
        conn = bot.db_connect()
        try:
            row = conn.execute("SELECT referrer_user_id, status FROM referrals WHERE referred_user_id=?", ("9004",)).fetchone()
            user_row = conn.execute("SELECT referred_by FROM users WHERE user_id=?", ("9004",)).fetchone()
        finally:
            conn.close()
        assert row[0] == "9001"
        assert row[1] == "registered"
        assert user_row[0] == "9001"
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_shopaikey_image_output_parser_and_send_helper_source():
    assert bot.shopaikey_image_output_from_payload({"url": "https://cdn.example/a.png"})["image_url"] == "https://cdn.example/a.png"
    assert bot.shopaikey_image_output_from_payload({"image_url": "https://cdn.example/b.png"})["image_url"] == "https://cdn.example/b.png"
    parsed_data_url = bot.shopaikey_image_output_from_payload({"data": [{"url": "https://cdn.example/c.png", "size": "768x1344"}]})
    assert parsed_data_url["image_url"] == "https://cdn.example/c.png"
    assert parsed_data_url["size"] == "768x1344"
    assert bot.shopaikey_image_output_from_payload({"data": [{"b64_json": "a" * 120}]})["b64_json"] == "a" * 120
    assert bot.shopaikey_image_output_from_payload({"output": ["https://cdn.example/d.png"]})["image_url"] == "https://cdn.example/d.png"
    helper_source = source_between(bot_source_text(), "async def send_generated_image_result", "async def resolve_video_source")
    assert "send_photo" in helper_source
    assert "send_document" in helper_source
    assert "image.success_link" in helper_source
    assert "return False, output_file_id" in helper_source


def test_setvip_is_limited_to_five_member_tiers():
    source = bot_source_text()
    setvip_source = source_between(source, "async def cmd_setvip", "async def cmd_backup_db")
    assert 'valid_tiers = {"silver", "gold", "platinum", "diamond", "vip"}' in setvip_source
    assert "Chỉ hỗ trợ: silver, gold, platinum, diamond, vip" in setvip_source
    assert 'raw_tier == "1"' in setvip_source
    assert 'raw_tier == "0"' in setvip_source
    assert "member_tier_overrides" in setvip_source
    assert "vip_tier_override" in setvip_source
    assert "Tiêu Chuẩn" not in setvip_source
    assert "<1|0>" not in setvip_source
    admin_help = bot.admin_center_text("member")
    assert "/setvip" in admin_help
    assert "silver|gold|platinum|diamond|vip" in admin_help
    assert "<1|0>" not in admin_help


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
    assert "image_to_video_public_off_from_prompt_text" in callback_source
    assert "safe_edit_or_send" in callback_source
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


def test_shopaikey_tts_smoke_suppresses_generic_error_after_audio_sent():
    source = bot_source_text()
    tts_source = source_between(source, "async def cmd_tool_test_shopaikey_tts", "async def cmd_tool_test_shopaikey_image")
    assert "final_report_sent = False" in tts_source
    assert "async def send_tts_smoke_final_report" in tts_source
    assert "output_sent = False" in tts_source
    assert "output_sent, send_error, send_attempts = await send_shopaikey_tts_audio_with_retry" in tts_source
    assert "provider_ok = False" in tts_source
    assert "audio_exists = False" in tts_source
    assert "FAIL_SEND_AUDIO" in tts_source
    assert "TTS đã tạo audio nhưng Telegram gửi file thất bại" in tts_source
    assert "send_shopaikey_tts_audio_with_retry" in tts_source
    assert "✅ TTS đã tạo xong. Không trừ Xu." in tts_source
    assert "USER_TTS_PROVIDER_BUSY_MESSAGE" in tts_source
    assert "Có lỗi khi xử lý lệnh" not in tts_source
    assert 'if status != "PASS"' not in tts_source
    voice_source = source_between(source, "async def cmd_voiceover", "async def cmd_public_admin_first_placeholder")
    assert "Voice/TTS đang trong giai đoạn thử nghiệm" in voice_source
    assert "Bot chưa trừ Xu" in voice_source
    assert bot.public_voice_runtime_status_text() == "admin-only"


def test_shopaikey_tts_smoke_uses_one_final_status(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "SHOPAIKEY_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_ADMIN_ONLY", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_TTS_MODEL", "tts-1")
    monkeypatch.setattr(bot, "SHOPAIKEY_TTS_VOICE", "alloy")
    monkeypatch.setattr(bot, "is_admin_user", lambda user_id: True)
    waiting_updates = []

    async def fake_send_waiting_message(update, context, job_type):
        return SimpleNamespace(job_type=job_type)

    async def fake_update_waiting_message(waiting_message, text):
        waiting_updates.append(text)

    monkeypatch.setattr(bot, "send_waiting_message", fake_send_waiting_message)
    monkeypatch.setattr(bot, "update_waiting_message", fake_update_waiting_message)

    class FakeMessage:
        def __init__(self):
            self.replies = []

        async def reply_text(self, text, **kwargs):
            self.replies.append(text)
            return SimpleNamespace(text=text, kwargs=kwargs)

    class FakeBot:
        def __init__(self, fail_send=False, fail_once_timeout=False):
            self.fail_send = fail_send
            self.fail_once_timeout = fail_once_timeout
            self.audio_calls = []
            self.send_attempts = 0

        async def send_audio(self, **kwargs):
            self.send_attempts += 1
            if self.fail_once_timeout and self.send_attempts == 1:
                raise TimeoutError("telegram send timed out")
            if self.fail_send:
                raise RuntimeError("telegram send failed")
            self.audio_calls.append(kwargs)
            return SimpleNamespace()

    async def run_case(provider_result, fail_send=False, fail_once_timeout=False):
        bot.GENERATION_PENDING_JOBS.clear()
        message = FakeMessage()
        telegram_bot = FakeBot(fail_send=fail_send, fail_once_timeout=fail_once_timeout)
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=777),
            effective_chat=SimpleNamespace(id=888),
            message=message,
        )
        context = SimpleNamespace(bot=telegram_bot)

        async def fake_smoke_test():
            return provider_result

        monkeypatch.setattr(bot, "shopaikey_tts_smoke_test", fake_smoke_test)
        await bot.cmd_tool_test_shopaikey_tts(update, context)
        return message.replies, telegram_bot.audio_calls, telegram_bot.send_attempts, bot.shopaikey_tts_status_snapshot()

    try:
        bot.init_db()
        replies, audio_calls, send_attempts, snapshot = asyncio.run(run_case(("FAIL_PROVIDER_ERROR", b"x" * 2048, "provider parsed fail but returned audio", 200)))
        assert len(audio_calls) == 1
        assert send_attempts == 1
        assert "ShopAIKey TTS audio test" in audio_calls[0]["caption"]
        assert not any("FAIL_PROVIDER_ERROR" in reply for reply in replies)
        assert len(replies) == 1
        assert "ShopAIKey TTS Smoke Test — PASS" in replies[0]
        assert snapshot["status"] == "PASS"

        replies, audio_calls, send_attempts, snapshot = asyncio.run(run_case(("FAIL_PROVIDER_ERROR", b"", "provider busy", 503)))
        assert audio_calls == []
        assert send_attempts == 0
        assert len(replies) == 1
        assert "FAIL_PROVIDER_ERROR" in replies[0]
        assert "PASS" not in replies[0]
        assert snapshot["status"] == "FAIL_PROVIDER_ERROR"

        replies, audio_calls, send_attempts, snapshot = asyncio.run(run_case(("PASS", b"x" * 2048, "http=200", 200), fail_send=True))
        assert audio_calls == []
        assert send_attempts == 1
        assert len(replies) == 1
        assert "FAIL_SEND_AUDIO" in replies[0]
        assert "PASS" not in replies[0]
        assert snapshot["status"] == "FAIL_SEND_AUDIO"

        replies, audio_calls, send_attempts, snapshot = asyncio.run(run_case(("PASS", b"x" * 2048, "http=200", 200), fail_once_timeout=True))
        assert len(audio_calls) == 1
        assert send_attempts == 2
        assert len(replies) == 1
        assert "ShopAIKey TTS Smoke Test — PASS" in replies[0]
        assert "FAIL_SEND_AUDIO" not in replies[0]
        assert snapshot["status"] == "PASS"
    finally:
        bot.GENERATION_PENDING_JOBS.clear()
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_generation_waiting_duplicate_and_guidance_helpers():
    bot.GENERATION_PENDING_JOBS.clear()
    try:
        assert "TOAN AAS đang tạo ảnh" in bot.get_generation_wait_text("image")
        assert "không cần gửi lại lệnh" in bot.get_generation_wait_text("image")
        assert "Ảnh chất lượng cao có thể lâu hơn một chút" in bot.public_image_waiting_text("high")
        assert "Ảnh chất lượng cao có thể lâu hơn một chút" in bot.public_image_waiting_text("high_warranty")
        assert "Ảnh chất lượng cao" not in bot.public_image_waiting_text("standard")
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


def test_storyboard_to_image_sequence_video_flow_v1(monkeypatch):
    source = bot_source_text()
    assert 'CommandHandler("storyboard_video", cmd_storyboard_video)' in source
    assert 'CallbackQueryHandler(handle_storyboard_callback, pattern=r"^storyboard\\|")' in source
    assert "handle_storyboard_pending_text(update, context)" in source
    message_source = source_between(source, "async def handle_message", "TELEGRAM_STARTUP_ERROR =")
    assert message_source.index("handle_storyboard_pending_text") < message_source.index("is_probable_media_tags_text")
    video_keyboard_source = source_between(source, "def main_video_keyboard", "def main_ai_keyboard")
    assert "🧩 Kịch bản → Ảnh → Video" in video_keyboard_source
    assert "🎞 Ghép ảnh có sẵn thành video" in video_keyboard_source
    assert "🎬 Tạo video nhanh" in video_keyboard_source
    assert "🖼➡️🎬 Tạo video AI từ ảnh" in video_keyboard_source
    assert "🔥 Video theo trend" in video_keyboard_source
    assert "🧠 Concept quảng cáo" in video_keyboard_source

    init_source = source_between(source, "def init_db():", "def get_user_language")
    assert "CREATE TABLE IF NOT EXISTS storyboard_projects" in init_source
    assert "CREATE TABLE IF NOT EXISTS storyboard_scenes" in init_source
    assert "CREATE TABLE IF NOT EXISTS storyboard_videos" in init_source
    assert "DROP TABLE" not in init_source

    scripts = bot.storyboard_suggest_scripts("máy xay sinh tố mini màu xanh ngọc")
    assert len(scripts) == 3
    scripts_text = bot.storyboard_scripts_text("máy xay sinh tố mini màu xanh ngọc", scripts)
    assert "Kịch bản 1" in scripts_text
    assert "Kịch bản 2" in scripts_text
    assert "Kịch bản 3" in scripts_text
    scenes3 = bot.storyboard_build_scenes("review sản phẩm nhanh", 3)
    scenes5 = bot.storyboard_build_scenes("review sản phẩm nhanh", 5)
    scenes7 = bot.storyboard_build_scenes("review sản phẩm nhanh", 7)
    scenes4 = bot.storyboard_build_scenes("review sản phẩm nhanh", 4)
    assert len(scenes3) == 3
    assert len(scenes5) == 5
    assert len(scenes7) == 7
    assert len(scenes4) == 4
    assert "Prompt ảnh" in bot.storyboard_text(scenes3)

    tier_text_7 = bot.storyboard_image_tier_selection_text(7)
    assert "Bạn đang tạo 7 ảnh storyboard" in tier_text_7
    assert "Tiết kiệm: 40 Xu/ảnh" in tier_text_7
    assert "Tiêu chuẩn: 190 Xu/ảnh" in tier_text_7
    assert "Chất lượng cao: 380 Xu/ảnh" in tier_text_7
    assert "flow kịch bản/storyboard" in tier_text_7
    tier_labels = [button.text for row in bot.storyboard_image_tier_keyboard(7).inline_keyboard for button in row]
    assert "🟢 Tiết kiệm" in tier_labels
    assert "🔵 Tiêu chuẩn" in tier_labels
    assert "🟣 Chất lượng cao" in tier_labels
    assert "🛡 Thêm bảo hành" in tier_labels
    assert bot.storyboard_image_unit_cost("low", 5) == 45
    assert bot.storyboard_image_unit_cost("low", 7) == 40
    assert bot.storyboard_image_unit_cost("low", 15) == 35
    assert bot.storyboard_image_unit_cost("low", 25) == 30
    monkeypatch.setattr(bot, "shopaikey_preview_final_cost", lambda _user_id, base_cost, _event_type: int(base_cost or 0))
    state = {"scenes": scenes5, "image_tier": "standard"}
    confirm_text = bot.storyboard_image_confirm_text(state, "not_admin_user")
    assert "5" in confirm_text
    assert "195 Xu/ảnh" in confirm_text
    assert "975 Xu" in confirm_text
    assert "Giá storyboard bulk" in confirm_text
    warranty_buttons = [button.text for row in bot.storyboard_image_confirm_keyboard("standard").inline_keyboard for button in row]
    assert any("Thêm bảo hành" in label and "250 Xu/ảnh" in label for label in warranty_buttons)

    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(5)], "duration": "fast", "effect": "none"}) == 50
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(5)], "duration": "fast", "effect": "fade"}) == 50
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(7)], "duration": "fast", "effect": "fade"}) == 100
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(10)], "duration": "standard", "effect": "zoom"}) == 120
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(5)], "duration": "slow", "effect": "zoom"}) == 110
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(10)], "duration": "slow", "effect": "pan"}) == 140
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(15)], "duration": "slow", "effect": "random"}) == 190
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(20)], "duration": "fast", "effect": "pan"}) == 290
    status = bot.frame_video_status_payload()
    assert status["base_2_5_xu"] == bot.FRAME_VIDEO_BASE_2_5_XU
    assert status["base_6_10_xu"] == bot.FRAME_VIDEO_BASE_6_10_XU
    assert status["motion_effect_extra_xu"] == bot.FRAME_VIDEO_MOTION_EFFECT_EXTRA_XU
    assert status["random_effect_extra_xu"] == bot.FRAME_VIDEO_RANDOM_EFFECT_EXTRA_XU
    assert status["direct_render_enabled"] == bot.FRAME_VIDEO_DIRECT_RENDER_ENABLED
    assert status["max_concurrent_jobs"] == bot.FRAME_VIDEO_MAX_CONCURRENT_JOBS
    effect_labels = str(bot.frame_video_effect_keyboard().inline_keyboard)
    assert "Pan trái/phải" in effect_labels
    assert "Slide ngang" in effect_labels
    assert "Random nhẹ" in effect_labels
    assert "Chọn nhạc có sẵn" in str(bot.frame_video_music_keyboard().inline_keyboard)
    assert "Thêm voice/TTS" in str(bot.frame_video_music_keyboard().inline_keyboard)
    mode_labels = str(bot.storyboard_after_images_keyboard(123).inline_keyboard)
    assert "Ghép các ảnh này thành video" in mode_labels
    assert "Biến ảnh thành video AI" in mode_labels
    assert "Tạo lại cảnh chưa ưng" in mode_labels
    assert "Thêm nhạc / voice" in mode_labels
    assert "Bạn muốn tạo video theo kiểu nào" in bot.storyboard_video_mode_text(123)
    assert "Video AI đang bận" in bot.storyboard_ai_video_busy_text()
    assert "shopaikey_video_create_smoke_test" not in source_between(source, "async def handle_storyboard_callback", "async def handle_storyboard_pending_text")


def test_critical_sales_ready_commands_remain_registered():
    source = bot_source_text()
    handler_lines = [line.strip() for line in source.splitlines() if "CommandHandler(" in line]
    literal_commands = re.findall(r'CommandHandler\("([^"]+)"', source)
    assert literal_commands
    assert all(len(command) <= 32 for command in literal_commands), [command for command in literal_commands if len(command) > 32]
    assert literal_commands.count("tool_test_shopaikey_tts") == 1
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
        "local_worker_status": "cmd_local_status",
        "local_worker_ping": "cmd_local_worker_ping",
        "tool_test_ffmpeg_local": "cmd_tool_test_ffmpeg_local",
        "orchestrator_status": "cmd_orchestrator_status",
        "provider_matrix": "cmd_provider_matrix",
        "tool_test_openrouter": "cmd_tool_test_openrouter",
        "tool_test_shopaikey": "cmd_tool_test_shopaikey",
        "tool_test_shopaikey_chat": "cmd_tool_test_shopaikey_chat",
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
        "storyboard_video": "cmd_storyboard_video",
        "quick_image_test": "cmd_quick_image_test",
        "quick_video_test": "cmd_quick_video_test",
        "frame_video_status": "cmd_frame_video_status",
        "tool_test_frame_video": "cmd_tool_test_frame_video",
        "shopaikey_status": "cmd_shopaikey_status",
        "image_provider_status": "cmd_image_provider_status",
        "shopaikey_usage": "cmd_shopaikey_usage",
        "package_catalog": "cmd_package_catalog",
        "grant_combo": "cmd_grant_combo",
        "grant_monthly": "cmd_grant_monthly",
        "user_packages": "cmd_user_packages",
        "adjust_package": "cmd_adjust_package",
        "revoke_package": "cmd_revoke_package",
        "freeze_status": "cmd_freeze_status",
        "freeze_video": "cmd_freeze_video",
        "unfreeze_video": "cmd_unfreeze_video",
        "queue_status": "cmd_queue_status",
        "job_status": "cmd_job_status",
        "refund_job": "cmd_refund_job",
        "clear_job_lock": "cmd_clear_job_lock",
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
    guide_quick = bot.guide_section_text("quick_start")
    guide_credit = bot.guide_section_text("credits")
    guide_image = bot.guide_section_text("image_ai")
    guide_video = bot.guide_section_text("video_ai")
    guide_step = bot.guide_section_text("guided_video")
    guide_music = bot.guide_section_text("music_add")
    guide_refund = bot.guide_section_text("refund")
    guide_faq = bot.guide_section_text("faq")
    keyboard = bot.main_menu_keyboard(False)
    button_texts = [button.text for row in keyboard.inline_keyboard for button in row]
    guide_labels = [button.text for row in bot.main_guide_keyboard("vi").inline_keyboard for button in row]
    guide_callbacks = [button.callback_data for row in bot.main_guide_keyboard("vi").inline_keyboard for button in row if button.callback_data]

    assert "/huongdan 1" in guide_index
    assert "Hướng dẫn tạo ảnh AI" in guide_index
    assert "Hướng dẫn tạo video AI" in guide_index
    assert "Làm video theo trend từng bước" in guide_index
    assert "Hướng dẫn thêm nhạc" in guide_index
    assert "📚 Hướng dẫn" in button_texts
    assert "💬 Góp ý / Báo lỗi" in button_texts
    assert "🚀 Bắt đầu nhanh" in guide_labels
    assert "🖼 Tạo ảnh" in guide_labels
    assert "🎬 Tạo video" in guide_labels
    assert "🔥 Video trend" in guide_labels
    assert "🎵 Nhạc video" in guide_labels
    assert "💰 Xu & nạp" in guide_labels
    assert "❓ FAQ & hoàn Xu" in guide_labels
    assert "👨‍💼 Admin" in guide_labels
    assert "📜 Điều khoản" not in guide_labels
    assert "menu|guide_quick_start" in guide_callbacks
    assert "menu|guide_refund" not in guide_callbacks
    assert "menu|guide_faq" in guide_callbacks
    assert "Bắt đầu nhanh với TOAN AAS" in guide_quick
    assert "Tạo ảnh AI" in guide_quick
    assert "Tạo video AI" in guide_quick
    assert "Video theo trend" in guide_quick
    assert "50.000đ → 500 Xu + 30 Xu Launch Bonus" in guide_credit
    assert "100.000đ → 1.000 Xu + 50 Xu Launch Bonus" in guide_credit
    assert "chỉ sau khi bạn xác nhận" in guide_image.lower()
    assert "Ảnh tiêu chuẩn" in guide_image
    assert "bảo hành" in guide_image.lower()
    assert "không gọi api video và không trừ xu" in guide_video.lower()
    assert "Video Trải Nghiệm: 200 Xu" in guide_video
    assert "Video Cơ Bản: 300 Xu" in guide_video
    assert "Video Phổ Thông: 400 Xu" in guide_video
    assert "Video Tiêu Chuẩn: 600 Xu" in guide_video
    assert "Video Cao Cấp: 1200 Xu" in guide_video
    assert "3 gợi ý" in guide_step.lower()
    assert "chọn cách lấy trend" in guide_step.lower()
    assert "nhạc là tùy chọn" in guide_music.lower()
    assert "bỏ nhạc" in guide_music.lower()
    assert "Hoàn Xu khi lỗi" in guide_refund
    assert "provider hết quota" in guide_refund
    assert guide_faq.count("<b>") >= 8
    assert len(guide_faq) < 2600
    image_buttons = [button.text for row in bot.guide_keyboard("image_ai", "vi").inline_keyboard for button in row]
    video_buttons = [button.text for row in bot.guide_keyboard("video_ai", "vi").inline_keyboard for button in row]
    trend_buttons = [button.text for row in bot.guide_keyboard("guided_video", "vi").inline_keyboard for button in row]
    xu_buttons = [button.text for row in bot.guide_keyboard("credits", "vi").inline_keyboard for button in row]
    quick_buttons = [button.text for row in bot.guide_keyboard("quick_start", "vi").inline_keyboard for button in row]
    assert "🖼 Tạo ảnh ngay" in image_buttons
    assert "🎬 Tạo video ngay" in video_buttons
    assert "🔥 Tạo video theo trend" in trend_buttons
    assert "💳 Nạp Xu" in xu_buttons
    assert "🖼 Tạo ảnh AI" in quick_buttons
    assert "🎬 Tạo video AI" in quick_buttons
    assert "🔥 Video theo trend" in quick_buttons
    en_text, en_keyboard = bot.localized_menu_content("guide_image_ai", False, "en", "u_en")
    assert "AI Image Guide" in en_text
    assert "Hướng dẫn" not in en_text
    assert any(button.text == "🔙 Back to guide" for row in en_keyboard.inline_keyboard for button in row)
    vi_guide_text, vi_guide_keyboard = bot.localized_menu_content("main_guide", False, "vi", "u_vi")
    assert "HƯỚNG DẪN" in vi_guide_text
    assert any(button.text == "🚀 Bắt đầu nhanh" for row in vi_guide_keyboard.inline_keyboard for button in row)
    sales_payload = bot.sales_readiness_payload()
    assert sales_payload["commands"]["guide_menu"] is True
    assert "basic" in sales_payload["video_tier_names"]
    assert "common" in sales_payload["video_tier_names"]
    assert "9:16" in sales_payload["video_aspect_ratios"]
    assert "3:2" in sales_payload["image_aspect_ratios"]
    assert len(sales_payload["video_combos"]) >= 5
    assert sales_payload["combo_rank_points_excluded"] is True
    assert "Guide menu: <code>{'ON' if commands.get('guide_menu') else 'OFF'}</code>" in bot_source_text()
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


def test_finance_ledger_revenue_usage_expense_and_year_profit(monkeypatch):
    source = bot_source_text()
    init_source = source_between(source, "def init_db():", "def now_text():")
    assert "finance_revenue_events" in init_source
    assert "finance_usage_events" in init_source
    assert "finance_expense_events" in init_source
    assert "DROP TABLE" not in init_source.upper()
    assert 'CommandHandler("finance_dashboard", cmd_finance_dashboard)' in source
    assert 'CommandHandler("revenue_report", cmd_revenue_report)' in source
    assert 'CommandHandler("expense_report", cmd_expense_report)' in source
    assert 'CommandHandler("profit_report", cmd_profit_report)' in source
    assert 'CommandHandler("finance_export", cmd_finance_export)' in source
    assert "💰 Tài chính" in source

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "ADMIN_ID", "admin-only")
    monkeypatch.setattr(bot, "TAX_RESERVE_RATE", 0.05)
    try:
        bot.init_db()
        user_id = "finance-user"
        bot.create_order("fin-10001", user_id, 50000, 500)
        processed, desc, paid_info = bot.process_payos_paid_order("fin-10001", 50000)
        assert processed is True
        assert desc == "success"
        assert int(paid_info.get("base_xu") or paid_info.get("xu") or 0) >= 500

        conn = bot.db_connect()
        try:
            revenue_rows = conn.execute(
                "SELECT source_type, source_id, amount_vnd, xu_credited FROM finance_revenue_events WHERE source_id=?",
                ("fin-10001",),
            ).fetchall()
            assert len(revenue_rows) == 1
            assert revenue_rows[0][0] == "payos_topup"
            assert revenue_rows[0][2] == 50000
        finally:
            conn.close()

        processed, desc, _paid_info = bot.process_payos_paid_order("fin-10001", 50000)
        assert processed is False
        conn = bot.db_connect()
        try:
            assert conn.execute("SELECT COUNT(*) FROM finance_revenue_events WHERE source_id=?", ("fin-10001",)).fetchone()[0] == 1
        finally:
            conn.close()

        charge = bot.spend_fixed_credit_info(user_id, 50, "shopaikey_image", "unit finance image", True)
        assert charge["ok"] is True
        charged_amount = int(charge.get("final_cost") or 0)
        assert charged_amount >= 0
        conn = bot.db_connect()
        try:
            assert conn.execute(
                "SELECT COUNT(*) FROM finance_usage_events WHERE user_id=? AND service_type='image' AND status='success'",
                (user_id,),
            ).fetchone()[0] >= 1
        finally:
            conn.close()
        if charged_amount > 0:
            assert bot.refund_charged_credit(user_id, charged_amount, "image_refund", "job-1", "unit refund", True) is True
            conn = bot.db_connect()
            try:
                assert conn.execute(
                    "SELECT COUNT(*) FROM finance_usage_events WHERE user_id=? AND status='refunded'",
                    (user_id,),
                ).fetchone()[0] >= 1
            finally:
                conn.close()

        expense_id = bot.add_finance_expense(32500, "provider_ai", "ShopAIKey", "nap api credit", "admin-only")
        pre_id = bot.add_finance_expense(3000000, "provider_ai", "ShopAIKey_ChatGPT", "chi phi truoc thanh lap", "admin-only", pre_establishment=True)
        assert expense_id > 0
        assert pre_id > 0
        start_at, end_at, label, kind = bot.finance_period_bounds(str(datetime.now().year), "year")
        assert kind == "year"
        payload = bot.finance_summary_payload(start_at, end_at, label)
        assert payload["revenue_success"] >= 50000
        assert payload["expenses_after"] >= 32500
        assert payload["expenses_pre_total"] >= 3000000
        assert payload["tax_reserve"] >= 2500
        assert "Lãi/lỗ" in bot.finance_report_text(payload)
        assert "finance_revenue_events" not in bot.finance_report_text(payload).lower()
        assert "fin-10001" in bot.finance_csv("revenue", start_at, end_at)
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
