import asyncio
import hmac
import hashlib
import io
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
import local_worker


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
    assert "TOAN_AAS_HUONG_DAN_SU_DUNG_CHO_KHACH_V2.docx" in docx.headers["content-disposition"]


def test_public_branding_and_scope_static_guard():
    repo_root = Path(bot.__file__).resolve().parent
    bot_source = (repo_root / "bot.py").read_text(encoding="utf-8")
    index_html = (repo_root / "index.html").read_text(encoding="utf-8")
    public_surface = bot_source + "\n" + index_html

    assert bot.BOT_USERNAME == "toanaasbot"
    assert bot.make_payos_description("50k") == "AAS50K"
    assert bot.manual_qr_url(123, 50000, 999).find("AAS+123+999") >= 0
    assert "https://t.me/toanaasbot" in index_html
    assert "Quy trình tạo video TOAN AAS" in index_html
    assert "Xu là đơn vị sử dụng trong bot TOAN AAS" in index_html
    assert "/download/dieu-khoan-su-dung-toan-aas.pdf" in index_html
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


def _plain_start_text(text: str) -> str:
    return re.sub(r"</?(?:b|code)>", "", text)


def _patched_vi_start_text(monkeypatch):
    monkeypatch.setattr(bot, "get_user", lambda user_id, *args, **kwargs: (777, 0, False))
    monkeypatch.setattr(bot, "is_admin_user", lambda user_id: False)
    monkeypatch.setattr(bot, "get_role_badge", lambda user_id: "🌱 Newbie")
    monkeypatch.setattr(bot, "user_language_label", lambda lang: "Tiếng Việt")
    return bot.localized_start_menu_text(424242, "vi")


def test_start_text_contains_toan_aas_title(monkeypatch):
    text = _plain_start_text(_patched_vi_start_text(monkeypatch))
    assert text.startswith("👑 TOAN AAS — AI AUTOMATION SYSTEM")
    assert "Trợ lý AI tự động hóa công việc trên Telegram:" in text


def test_start_text_contains_dynamic_balance_id_tier_language(monkeypatch):
    text = _plain_start_text(_patched_vi_start_text(monkeypatch))
    assert "🎁 Số dư: 777 Xu" in text
    assert "👤 ID: 424242" in text
    assert "🪪 Hạng: 🌱 Newbie" in text
    assert "🌐 Ngôn ngữ: Tiếng Việt" in text


def test_start_text_contains_all_product_categories(monkeypatch):
    text = _plain_start_text(_patched_vi_start_text(monkeypatch))
    expected_lines = [
        "🎬 Tạo nội dung: Kịch bản, storyboard, chia cảnh, caption, prompt video.",
        "🤖 Hỏi AI: Viết bài, lên ý tưởng, sửa nội dung, viết code, lập kế hoạch.",
        "📄 Tài liệu: PDF, Word, ảnh sang PDF, nén/tách/gộp tài liệu.",
        "🖼 Hình ảnh: Prompt ảnh, xử lý ảnh, tách nền, chuẩn bị hình ảnh cho video.",
        "🎵 Nhạc / SFX: Tìm nhạc nền, hiệu ứng âm thanh và chuẩn bị âm thanh cho video.",
        "🎤 Voice: Bóc băng audio/video, tạo giọng đọc và chuẩn bị voice cho nội dung.",
        "🌐 Dịch thuật: Dịch văn bản, transcript, phụ đề và nội dung video.",
        "🧠 Ghi nhớ: Lưu ghi chú, tìm lại thông tin, đặt nhắc việc.",
        "💳 Xu dịch vụ: dùng để sử dụng các dịch vụ của toanaasbot.",
    ]
    for line in expected_lines:
        assert line in text
    assert "Trước khi nạp xu mọi người nhớ vào kiểm tra và gửi mã khuyến mãi theo hướng dẫn trước nhé!" in text


def test_start_text_contains_legal_links(monkeypatch):
    text = _plain_start_text(_patched_vi_start_text(monkeypatch))
    for command in ["/legal", "/privacy", "/dieukhoan_xu", "/refund_policy"]:
        assert command in text
    assert "chính sách sở hữu trí tuệ của TOAN AAS" in text


def test_start_keyboard_callbacks_unchanged():
    rows = [
        [(button.text, button.callback_data, button.url) for button in row]
        for row in bot.localized_main_menu_keyboard(False, "vi").inline_keyboard
    ]
    assert rows == [
        [("🆓 Công cụ miễn phí", "freehub|main", None), ("👤 Tài khoản", "menu|main_profile", None)],
        [("🖼 Tạo ảnh AI", "menu|main_image", None), ("🎬 Tạo video AI", "menu|main_video", None)],
        [("🎧 Studio âm thanh", "music_quick|showroom|root", None), ("🌐 Dịch / Phụ đề / Lồng tiếng Studio", "menu|translate", None)],
        [("📝 Ghi chú / Tài liệu", "menu|main_memory", None), ("📚 Hướng dẫn", "menu|main_guide", None)],
        [("👨‍💼 Hỗ trợ", "menu|support", None), ("💰 Nạp Xu / Bảng giá", "pricing|main", None)],
        [("💬 Góp ý / Báo lỗi", "feedback|start", None), ("🌐 Trung tâm", None, bot.TOAN_AAS_COMMUNITY_URL)],
    ]


def test_no_payos_touched():
    source = bot_source_text()
    start_source = source_between(source, "def localized_start_menu_text", "def public_back_keyboard")
    assert "PAYOS" not in start_source.upper()
    assert "/naptien" not in start_source
    assert "wallet" not in start_source.lower()
    assert "webhook" not in start_source.lower()


def test_no_provider_logic_touched():
    source = bot_source_text()
    start_source = source_between(source, "def localized_start_menu_text", "def public_back_keyboard")
    forbidden = ["provider", "export_video", "finalize_video", "Task 1", "Task 2", "Task 3D"]
    assert not any(item.lower() in start_source.lower() for item in forbidden)


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
    assert "🤖 Provider" in admin_nav_labels
    admin_nav_rows = [[button.text for button in row] for row in bot.menu_nav_keyboard("admin", True).inline_keyboard]
    assert ["💰 Tài chính", "🧊 Freeze / Queue"] in admin_nav_rows
    assert ["🤖 Provider", "📣 Marketing tự động"] in admin_nav_rows
    assert ["⬅️ Quay lại", "🏠 Menu chính"] in admin_nav_rows
    finance_labels = [button.text for row in bot.finance_admin_keyboard().inline_keyboard for button in row]
    for label in ["📊 Tổng quan", "💵 Doanh thu", "📅 Doanh thu tháng", "📉 Chi phí tháng", "📈 Lãi / Lỗ", "📤 Xuất báo cáo", "➕ Thêm chi phí", "📚 Hướng dẫn lệnh"]:
        assert label in finance_labels
    freeze_labels = [button.text for row in bot.freeze_queue_keyboard().inline_keyboard for button in row]
    for label in ["📊 Queue Status", "🧊 Freeze Status", "🖼 Freeze Image", "🎬 Freeze Video", "🎞 Freeze Frame", "🤖 Freeze Provider", "✅ Unfreeze Tool", "🧹 Clear Stale Jobs"]:
        assert label in freeze_labels
    assert "Thu chi / Báo cáo nội bộ TOAN AAS" in bot.finance_menu_text()
    assert "🟢 Miễn/ưu đãi thuế phí" in finance_labels
    assert "không tự nộp thuế" in bot.finance_menu_text()
    assert "Mục này dùng để kiểm tra hàng đợi job" in bot.freeze_queue_menu_text()
    assert "thao tác nguy hiểm luôn đi qua màn xác nhận" in bot.freeze_queue_menu_text()
    assert "Báo cáo tổng TOAN AAS" in bot.admin_overview_text()
    smoke_labels = [button.text for row in bot.smoke_test_menu_keyboard().inline_keyboard for button in row]
    for label in ["🤖 Test ShopAIKey", "🗣 Test TTS", "🖼 Test Image", "🎬 Test Video", "🎞 Test FFmpeg", "🧩 Test ComfyUI", "📊 Providers", "✅ Sales Ready"]:
        assert label in smoke_labels
    provider_labels = [button.text for row in bot.admin_provider_keyboard().inline_keyboard for button in row]
    for label in ["📊 Provider Status", "🧪 Test Provider", "🟡 Freeze Provider", "🟢 Unfreeze Provider", "🧾 Provider Usage"]:
        assert label in provider_labels
    assert "Provider Management" in bot.admin_provider_menu_text()
    assert "không tự gọi provider" in bot.admin_provider_menu_text()
    queue_labels = [button.text for row in bot.queue_status_keyboard().inline_keyboard for button in row]
    assert "🔄 Refresh Queue" in queue_labels
    assert "🧹 Dọn job kẹt" in queue_labels
    confirm_labels = [button.text for row in bot.admin_confirm_keyboard("freeze_video").inline_keyboard for button in row]
    assert "✅ Xác nhận" in confirm_labels
    assert "❌ Hủy" in confirm_labels
    assert "⬅️ Quay lại" in confirm_labels
    assert "/freeze_video" in bot.admin_confirm_text("freeze_video")
    system_labels = [button.text for row in bot.menu_nav_keyboard("system", True).inline_keyboard for button in row]
    assert "🧬 Runtime" in system_labels
    assert "🗄 Data Status" in system_labels
    admin_menu = bot.menu_text_admin()
    assert len(admin_menu) < 4096
    admin_content, admin_markup = bot.localized_menu_content("admin", True, "vi", user_id=bot.ADMIN_ID)
    assert admin_content == admin_menu
    assert len(admin_content) < 4096
    assert admin_markup.inline_keyboard
    assert all(
        len(button.callback_data or "") <= 64
        for row in admin_markup.inline_keyboard
        for button in row
        if button.callback_data
    )
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
    assert "IMAGE_STANDARD_WARRANTY_COST_XU=300" in env_example
    assert "IMAGE_HIGH_COST_XU=400" in env_example
    assert "IMAGE_HIGH_WARRANTY_COST_XU=600" in env_example
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
    monkeypatch.setattr(bot, "VIDEO_AI_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_PUBLIC_BETA_ENABLED", True)
    monkeypatch.setattr(bot, "video_public_beta_enabled_runtime", lambda: True)
    monkeypatch.setattr(bot, "shopaikey_public_video_enabled_runtime", lambda: True)
    monkeypatch.setattr(bot, "video_ai_public_enabled_runtime", lambda: True)
    monkeypatch.setattr(bot, "is_tool_frozen", lambda *_args, **_kwargs: {"frozen": False})
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
    monkeypatch.setattr(bot, "VIDEO_AI_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_PUBLIC_BETA_ENABLED", True)
    monkeypatch.setattr(bot, "video_public_beta_enabled_runtime", lambda: True)
    monkeypatch.setattr(bot, "shopaikey_public_video_enabled_runtime", lambda: True)
    monkeypatch.setattr(bot, "video_ai_public_enabled_runtime", lambda: True)
    monkeypatch.setattr(bot, "is_tool_frozen", lambda *_args, **_kwargs: {"frozen": False})
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
    assert bot.public_video_provider_fail_message(0, False) == "🛠 Hệ thống tạo video đang bảo trì/nâng cấp nhẹ nên chưa xuất được lúc này. TOAN AAS chưa trừ Xu của bạn. Vui lòng thử lại sau."
    assert bot.public_video_provider_fail_message(300, True) == "🛠 Hệ thống tạo video đang bảo trì/nâng cấp nhẹ nên chưa xuất được lúc này. TOAN AAS đã hoàn lại 300 Xu cho bạn. Vui lòng thử lại sau."
    assert "Admin đã được ghi nhận" in bot.public_video_provider_fail_message(300, False)

    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_IMAGE_ENABLED", False)
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_VIDEO_ENABLED", False)
    public_off_message = "🧪 Tính năng này đang thử nghiệm nội bộ, chưa mở công khai. TOAN AAS sẽ mở sau khi kiểm tra ổn định."
    assert bot.shopaikey_public_generation_guard("image") == (False, public_off_message)
    assert bot.shopaikey_public_generation_guard("video") == (False, public_off_message)
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_IMAGE_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_VIDEO_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_AI_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "video_public_beta_enabled_runtime", lambda: True)
    monkeypatch.setattr(bot, "shopaikey_public_video_enabled_runtime", lambda: True)
    monkeypatch.setattr(bot, "video_ai_public_enabled_runtime", lambda: True)
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


def test_package_purchase_selection_requires_confirm_before_checkout(monkeypatch):
    captured = {"details": [], "checkout": []}

    async def fake_edit(_query, lines, reply_markup=None, limit=3600):
        captured["details"].append((list(lines), reply_markup, limit))

    async def fake_start(_update, _context, package_type, code, message=None):
        captured["checkout"].append((package_type, code, message))

    class FakeQuery:
        def __init__(self, data):
            self.data = data
            self.from_user = SimpleNamespace(id=123, first_name="Buyer", username="buyer")
            self.message = SimpleNamespace()

        async def answer(self, *args, **kwargs):
            return None

    monkeypatch.setattr(bot, "edit_or_send_pricing_lines", fake_edit)
    monkeypatch.setattr(bot, "start_package_purchase", fake_start)
    context = SimpleNamespace()

    update = SimpleNamespace(callback_query=FakeQuery("pkgbuy|combo|tiktok_99k"))
    asyncio.run(bot.handle_package_purchase_callback(update, context))
    assert captured["checkout"] == []
    assert "Bạn có muốn thanh toán" in "\n".join(captured["details"][0][0])
    detail_callbacks = [
        button.callback_data
        for row in captured["details"][0][1].inline_keyboard
        for button in row
    ]
    assert "pkgbuy|confirm|combo|tiktok_99k" in detail_callbacks
    assert "pricing|combo" in detail_callbacks

    update = SimpleNamespace(callback_query=FakeQuery("pkgbuy|confirm|combo|tiktok_99k"))
    asyncio.run(bot.handle_package_purchase_callback(update, context))
    assert captured["checkout"][0][:2] == ("combo", "tiktok_99k")


def test_package_purchase_checkout_metadata_is_classified(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "PAYOS_CLIENT_ID", "client")
    monkeypatch.setattr(bot, "PAYOS_API_KEY", "api")
    monkeypatch.setattr(bot, "PAYOS_CHECKSUM_KEY", "checksum")
    monkeypatch.setattr(bot, "generate_order_code", lambda: "900002")
    monkeypatch.setattr(bot, "make_payos_return_url", lambda _context: "https://www.toanaas.vn/")
    monkeypatch.setattr(bot, "record_usage_event", lambda *args, **kwargs: None)

    async def fake_payos(_body):
        return SimpleNamespace(status_code=200), {"code": "00", "data": {"checkoutUrl": "https://pay.example/900002", "paymentLinkId": "link-900002"}}, "", ""

    class FakeMessage:
        def __init__(self):
            self.sent = []

        async def reply_text(self, text, **kwargs):
            self.sent.append((text, kwargs))

    monkeypatch.setattr(bot, "create_payos_payment_request", fake_payos)
    try:
        bot.init_db()
        message = FakeMessage()
        user = SimpleNamespace(id=456, first_name="Package Buyer", username="package_buyer")
        update = SimpleNamespace(effective_user=user, message=message)
        asyncio.run(bot.start_package_purchase(update, SimpleNamespace(), "combo", "tiktok_99k", message=message))
        conn = bot.db_connect()
        try:
            order = conn.execute(
                "SELECT order_type, metadata_json FROM payos_orders WHERE order_code=?",
                ("900002",),
            ).fetchone()
        finally:
            conn.close()
        metadata = json.loads(order[1])
        assert metadata["payment_type"] == "combo_purchase"
        assert metadata["item_id"] == "tiktok_99k"
        assert metadata["user_id"] == "456"
        assert metadata["amount_vnd"] == 99000
        assert metadata["status"] == "pending"
        assert metadata["created_at"]
        assert metadata["expires_at"]
        assert metadata["note"] == "combo_purchase:tiktok_99k"
        assert order[0] == "package_purchase"
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)

def test_storage_addon_menu_and_payos_paid_grants_storage_without_xu(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "ADMIN_ID", "admin-only")
    try:
        bot.init_db()
        labels = [button.text for row in bot.memory_storage_addon_keyboard("vi").inline_keyboard for button in row]
        callbacks = [button.callback_data for row in bot.memory_storage_addon_keyboard("vi").inline_keyboard for button in row]
        assert "💳 10k — +50MB/tháng" in labels
        assert "💳 20k — +100MB/tháng" in labels
        assert "💳 50k — +250MB/tháng" in labels
        assert "💳 100k — +500MB/tháng" in labels
        assert "storage|custom" in callbacks
        assert "storage|select|50mb" in callbacks

        user_id = "storage-payos-user"
        bot.get_user(user_id, "Storage Buyer")
        before_credits, before_spent, _ = bot.get_user(user_id)
        metadata = {
            "type": "storage_addon",
            "payment_type": "storage_addon",
            "item_id": "50mb",
            "user_id": user_id,
            "amount_vnd": 10000,
            "status": "pending",
            "addon_mb": 50,
            "months": 1,
        }
        bot.create_order(
            "920001",
            user_id,
            10000,
            0,
            base_xu=0,
            launch_bonus_xu=0,
            package_amount_vnd=0,
            order_type="storage_addon",
            plan_id="50mb",
            plan_name="+50MB/tháng",
            duration_days=30,
            plan_xu=0,
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        )
        processed, desc, info = bot.process_payos_paid_order("920001", 10000)
        assert processed is True
        assert desc == "storage_addon_success"
        assert info["order_type"] == "storage_addon"
        assert int(info["addon_mb"]) == 50
        status = bot.memory_status_payload(user_id)
        assert int(status["active_storage_addon_mb"]) == 50
        assert int(status["total_limit_mb"]) >= bot.TOTAL_FREE_STORAGE_MB + 50
        after_credits, after_spent, _ = bot.get_user(user_id)
        assert int(after_credits) == int(before_credits)
        assert int(after_spent) == int(before_spent)
        assert bot.member_total_paid_vnd(user_id) == 0
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_storage_addon_checkout_metadata_and_admin_grant(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "PAYOS_CLIENT_ID", "client")
    monkeypatch.setattr(bot, "PAYOS_API_KEY", "api")
    monkeypatch.setattr(bot, "PAYOS_CHECKSUM_KEY", "checksum")
    monkeypatch.setattr(bot, "generate_order_code", lambda: "920002")
    monkeypatch.setattr(bot, "make_payos_return_url", lambda _context: "https://www.toanaas.vn/")
    monkeypatch.setattr(bot, "record_usage_event", lambda *args, **kwargs: None)

    async def fake_payos(body):
        assert body["amount"] == 10000
        assert body["description"] == "AASSTOR50MB"
        return SimpleNamespace(status_code=200), {"code": "00", "data": {"checkoutUrl": "https://pay.example/920002", "paymentLinkId": "link-920002"}}, "", ""

    class FakeMessage:
        def __init__(self):
            self.sent = []

        async def reply_text(self, text, **kwargs):
            self.sent.append((text, kwargs))

    monkeypatch.setattr(bot, "create_payos_payment_request", fake_payos)
    try:
        bot.init_db()
        message = FakeMessage()
        user = SimpleNamespace(id=789, first_name="Storage Buyer", username="storage_buyer")
        update = SimpleNamespace(effective_user=user, message=message, callback_query=None)
        asyncio.run(bot.start_storage_addon_purchase(update, SimpleNamespace(), bot.storage_addon_spec_by_code("50mb"), message=message))
        conn = bot.db_connect()
        try:
            order = conn.execute(
                "SELECT order_type, xu, base_xu, launch_bonus_xu, package_amount_vnd, metadata_json FROM payos_orders WHERE order_code=?",
                ("920002",),
            ).fetchone()
            grant = bot.grant_memory_storage_addon_conn(conn, "admin-granted-user", 100, amount_vnd=0, months=2, source="admin_grant", granted_by="pytest")
            conn.commit()
        finally:
            conn.close()
        metadata = json.loads(order[5])
        assert order[0] == "storage_addon"
        assert int(order[1]) == 0
        assert int(order[2]) == 0
        assert int(order[3]) == 0
        assert int(order[4]) == 0
        assert metadata["payment_type"] == "storage_addon"
        assert metadata["item_id"] == "50mb"
        assert int(metadata["addon_mb"]) == 50
        assert "Không cộng Xu" in message.sent[-1][0]
        assert grant["ok"] is True
        assert int(bot.memory_status_payload("admin-granted-user")["active_storage_addon_mb"]) == 100
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
        assert stale["status"] == "TIMEOUT_STALE"
        assert "maximum job age" in stale["detail"]

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
    assert "Video tạm thời chưa xuất được" in failed_text
    assert "bảo trì/nâng cấp nhẹ" in failed_text
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
    monkeypatch.setattr(bot, "VIDEO_AI_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "video_public_beta_enabled_runtime", lambda: True)
    monkeypatch.setattr(bot, "shopaikey_public_video_enabled_runtime", lambda: True)
    monkeypatch.setattr(bot, "video_ai_public_enabled_runtime", lambda: True)
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

        admin_job_id = bot.create_shopaikey_job(
            "admin1",
            "c1",
            "video",
            model="veo3.1-fast",
            prompt="admin smoke prompt that must not be shown in lock text",
            status="IN_PROGRESS",
            admin_only=True,
        )
        conn = bot.db_connect()
        try:
            conn.execute(
                "UPDATE shopaikey_jobs SET created_at=?, updated_at=? WHERE id=?",
                ("2000-01-01 00:00:00", "2000-01-01 00:00:00", admin_job_id),
            )
            conn.commit()
        finally:
            conn.close()
        stale_admin = bot.mark_stale_admin_video_jobs("admin1")
        assert len(stale_admin) == 1
        admin_job = bot.shopaikey_job_by_id(admin_job_id)
        assert admin_job["status"] == "FAILED_TIMEOUT"
        assert admin_job["error_class"] == "ADMIN_STALE_TIMEOUT"
        assert bot.shopaikey_active_job_for_user("admin1", "video") is None
        block_text = bot.shopaikey_active_video_admin_block_text(
            {"id": 99, "task_id": "task_live", "status": "IN_PROGRESS", "created_at": "2026-06-14 19:11:00"},
            "admin1",
        )
        assert "/shopaikey_video_job task_live" in block_text
        assert "/job_status 99" in block_text
        assert "/clear_job_lock admin1" in block_text
        assert "admin smoke prompt" not in block_text
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
    image_callbacks = {
        button.text: button.callback_data
        for row in bot.main_image_keyboard("vi").inline_keyboard
        for button in row
    }
    assert image_callbacks["🖼 Tạo ảnh nhanh"] == "create_media|quick_image"
    assert 'ui_text(lang, "video.guided_flow")' not in video_keyboard_source
    video_callbacks = {
        button.callback_data
        for row in bot.main_video_keyboard("vi").inline_keyboard
        for button in row
    }
    assert "vproduct|open|video_ai_real" in video_callbacks
    assert "vproduct|open|frame_video_local" in video_callbacks
    assert "vproduct|open|self_shot_scene_change" in video_callbacks
    assert "vproduct|open|multi_scene_film" in video_callbacks
    assert "vproduct|open|video_trend" in video_callbacks
    assert 'callback_data="framevideo|start"' in source
    video_labels = {
        button.text
        for row in bot.main_video_keyboard("vi").inline_keyboard
        for button in row
    }
    assert "🧠 Ý tưởng video" in video_labels
    assert "📢 Concept quảng cáo" not in video_labels
    assert "🎥 Prompt / Chuyển động" in video_labels
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
    assert 'start_video_addon_step(query, uid, pending_payload, tier, lang, source="ai")' in quick_source
    assert "video_addon_menu_text" in source
    assert "video_addon_runtime_guard(pending)" in source
    assert "Hệ thống tạo video đang bảo trì/nâng cấp nhẹ" in source
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
    assert "handle_developing_video_pending_text(update, context)" in message_source
    photo_handler_source = source_between(source, "async def handle_photo", "async def handle_document_cache_only")
    assert "handle_frame_video_photo(update, context)" in photo_handler_source
    assert photo_handler_source.index("handle_frame_video_photo(update, context)") < photo_handler_source.index("remember_last_user_file(update)")
    assert message_source.index("handle_feedback_pending_text(update, context)") < message_source.index("handle_trend_video_flow_pending_text(update, context)")
    assert message_source.index("handle_public_image_prompt_pending_text(update, context)") < message_source.index("handle_quick_media_pending_text(update, context)")
    assert message_source.index("handle_public_video_prompt_pending_text(update, context)") < message_source.index("handle_quick_media_pending_text(update, context)")
    assert message_source.index("handle_creative_motion_pending_text(update, context)") < message_source.index("handle_quick_media_pending_text(update, context)")
    assert message_source.index("handle_cinematic_ad_pending_text(update, context)") < message_source.index("handle_quick_media_pending_text(update, context)")
    assert message_source.index("handle_developing_video_pending_text(update, context)") < message_source.index("handle_quick_media_pending_text(update, context)")
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
    monkeypatch.setattr(bot, "VIDEO_PUBLIC_BETA_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_PUBLIC_ALLOWED_TIERS", "low,basic,common")
    monkeypatch.setattr(bot, "VIDEO_PREMIUM_ADMIN_ONLY", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_DEFAULT_TIER", "low")
    monkeypatch.setattr(bot, "VIDEO_BASIC_COST_XU", 765)
    monkeypatch.setattr(bot, "VIDEO_COMMON_COST_XU", 876)
    monkeypatch.setattr(bot, "VIDEO_ADVANCED_COST_XU", 950)
    monkeypatch.setattr(bot, "VIDEO_STANDARD_COST_XU", 999)
    monkeypatch.setattr(bot, "VIDEO_HIGH_COST_XU", 1111)
    monkeypatch.setattr(bot, "VIDEO_FUTURE_1000_COST_XU", 1000)
    monkeypatch.setattr(bot, "VIDEO_FUTURE_1500_COST_XU", 1500)
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
    assert pricing["video_tiers"]["advanced"]["cost"] == 950
    assert pricing["video_tiers"]["standard"]["cost"] == 999
    assert pricing["video_tiers"]["high"]["cost"] == 1111
    assert pricing["video_tiers"]["future_1000"]["cost"] == 1000
    assert pricing["video_tiers"]["future_1500"]["cost"] == 1500
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
    assert bot.video_tier_cost_xu("advanced") == 950
    assert bot.video_tier_cost_xu("standard") == 999
    assert bot.video_tier_cost_xu("high") == 1111
    assert bot.video_tier_payload("starter")["tier"] == "basic"
    assert bot.video_tier_payload("regular")["tier"] == "common"
    assert bot.video_tier_payload("vip")["tier"] == "future_1500"
    assert bot.video_tier_payload("future_1500")["admin_only"] is False
    assert bot.video_tier_payload("future_1500")["enabled"] is True
    assert bot.video_tier_public_status_text() == "low:ON / basic:ON / common:ON / advanced:ON / standard:ON / high:ON / future_1000:ON / future_1200:ON / future_1500:ON"
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
    assert any("Tiết kiệm" in button.text and "321 Xu" in button.text for button in tier_buttons)
    assert any("Chuẩn + BH" in button.text and "799 Xu" in button.text for button in tier_buttons)
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
    assert bot.get_image_size_for_ratio("2:1", "low", "shopaikey")["ratio"] == "1:1"
    assert bot.normalize_image_aspect_ratio("square") == "1:1"
    assert bot.normalize_image_aspect_ratio("portrait") == "9:16"
    assert bot.normalize_image_aspect_ratio("vertical") == "9:16"
    assert bot.normalize_image_aspect_ratio("landscape") == "16:9"
    assert bot.normalize_image_aspect_ratio("horizontal") == "16:9"
    assert bot.normalize_image_aspect_ratio("1024x1024") == "1:1"
    assert bot.normalize_image_aspect_ratio("auto") == "1:1"
    assert bot.normalize_image_aspect_ratio(None) == "1:1"
    assert bot.normalize_image_aspect_ratio("1:1") == "1:1"
    assert bot.normalize_image_aspect_ratio("9:16") == "9:16"
    assert bot.normalize_image_aspect_ratio("16:9") == "16:9"
    assert bot.normalize_image_aspect_ratio("4:5") == "4:5"
    assert bot.normalize_image_aspect_ratio("invalid_value") == "1:1"
    shopaikey_payload = bot.build_shopaikey_google_image_payload("p", "nano-banana", "16:9")
    assert shopaikey_payload["size"] == "16:9"
    assert "aspect_ratio" not in shopaikey_payload
    assert "aspectRatio" not in shopaikey_payload
    assert "1344x768" not in shopaikey_payload.values()
    google_payload = bot.build_google_genai_image_payload("p", "gemini-image", "16:9")
    assert google_payload["generationConfig"]["responseFormat"]["image"]["aspectRatio"] == "16:9"
    assert google_payload["generationConfig"]["responseFormat"]["image"]["imageSize"] == "2K"
    assert "size" not in google_payload
    assert bot.infer_image_aspect_ratio_from_prompt("Product scene. Aspect ratio 4:5. No watermark.") == "4:5"
    assert bot.infer_image_aspect_ratio_from_prompt("Wide cinematic banner 21:9") == "21:9"
    assert bot.shopaikey_image_model_sequence("nano-banana", "gemini-2.5-flash-image,nano-banana,gemini-2.0-flash-preview-image-generation") == [
        "nano-banana",
        "gemini-2.5-flash-image",
        "gemini-2.0-flash-preview-image-generation",
    ]
    assert bot.shopaikey_image_model_invalid_error(429, "Model not found or invalid")
    assert bot.shopaikey_classify_error(429, "Model not found or invalid") == "FAIL_MODEL_INVALID"
    shopaikey_builder_source = source_between(bot_source_text(), "def build_shopaikey_google_image_payload", "def build_google_genai_image_payload")
    assert '"size": normalized_ratio' in shopaikey_builder_source
    assert '"aspect_ratio"' not in shopaikey_builder_source
    assert '"aspectRatio"' not in shopaikey_builder_source
    assert 'size_info["size_string"]' not in shopaikey_builder_source
    image_generate_source = source_between(bot_source_text(), "async def shopaikey_image_generate", "async def shopaikey_image_smoke_test")
    assert "build_shopaikey_google_image_payload" in image_generate_source
    assert '"aspect_ratio": provider_aspect_ratio' not in image_generate_source
    assert '"aspectRatio": provider_aspect_ratio' not in image_generate_source
    assert "payload_mode" in image_generate_source
    assert "field_used" in image_generate_source
    assert "get_image_size_for_ratio" in image_generate_source
    assert "shopaikey_image_output_from_payload" in image_generate_source
    assert "models_tried" in image_generate_source
    assert "fallback_used" in image_generate_source
    assert "shopaikey_image_model_invalid_error" in image_generate_source
    image_smoke_source = source_between(bot_source_text(), "async def cmd_tool_test_shopaikey_image", "async def cmd_tool_test_shopaikey_video")
    assert "context.args" in image_smoke_source
    assert "Ratio requested" in image_smoke_source
    assert "Payload mode" in image_smoke_source
    assert "Field used" in image_smoke_source
    assert "aspect_ratio sent" in image_smoke_source
    assert "aspectRatio sent" in image_smoke_source
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
    assert "Video AI chân thật Beta" in video_tier_text
    video_tier_buttons = [button for row in bot.public_video_tier_keyboard().inline_keyboard for button in row]
    assert any(button.callback_data == "create_media|video_tier_low" for button in video_tier_buttons)
    assert any(button.callback_data == "create_media|video_tier_basic" for button in video_tier_buttons)
    assert any(button.callback_data == "create_media|video_tier_common" for button in video_tier_buttons)
    assert any(button.callback_data == "create_media|video_tier_standard" for button in video_tier_buttons)
    assert any(button.callback_data == "create_media|video_tier_high" for button in video_tier_buttons)
    assert any(button.callback_data == "create_media|video_tier_future_1500" for button in video_tier_buttons)
    assert not any(button.callback_data == "create_media|video_tier_premium" for button in video_tier_buttons)
    assert any("Trải nghiệm" in button.text and "654 Xu" in button.text for button in video_tier_buttons)
    assert any("Cơ bản" in button.text and "765 Xu" in button.text for button in video_tier_buttons)
    assert any("Phổ thông" in button.text and "876 Xu" in button.text for button in video_tier_buttons)
    assert "Gửi mô tả video bạn muốn tạo" in bot.public_video_prompt_request_text("common")
    assert "876 Xu" in bot.public_video_confirm_text("common", "video sản phẩm", 1500, aspect_ratio="9:16")
    assert "Tỉ lệ khung hình: <b>9:16</b>" in bot.public_video_confirm_text("common", "video sản phẩm", 1500, aspect_ratio="9:16")
    assert "Public video" in bot.public_video_confirm_text("common", "video sản phẩm", 1500, music_label="piano cinematic", aspect_ratio="4:5")
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
    pricing_hub_text = "\n".join(bot.pricing_hub_lines("vi"))
    assert "Nạp Xu / Bảng giá TOAN AAS" in pricing_hub_text
    assert "xem bảng giá, nạp Xu, xem ưu đãi hay mua gói/combo" in pricing_hub_text
    assert "Launch Bonus cho thanh toán nội địa Việt Nam" in pricing_hub_text
    price_keyboard_labels = [button.text for row in bot.pricing_main_keyboard("vi").inline_keyboard for button in row]
    assert price_keyboard_labels == [
        "📋 Bảng giá",
        "🎁 Xem ưu đãi",
        "💳 Nạp Xu",
        "🎁 Gói / Combo",
        "🏠 Menu chính",
    ]
    pricing_callbacks = [button.callback_data for row in bot.pricing_main_keyboard("vi").inline_keyboard for button in row]
    assert pricing_callbacks == [
        "pricing|catalog",
        "pricing|promotions",
        "menu|main_topup",
        "pricing|packages",
        "menu|main",
    ]
    en_pricing_labels = [button.text for row in bot.pricing_main_keyboard("en").inline_keyboard for button in row]
    assert "🎁 Xem ưu đãi" not in en_pricing_labels
    assert en_pricing_labels == ["📋 Pricing", "💳 Top up Xu", "🎁 Plans / Combos", "🏠 Main menu"]
    assert "Vietnam local top-up promotions are not available for international payments" in "\n".join(bot.pricing_hub_lines("en"))
    promo_text = "\n".join(bot.billing_promotions_lines("vi"))
    assert "ƯU ĐÃI TOAN AAS" in promo_text
    assert "FIRST30" in promo_text
    assert "SECOND15" in promo_text
    assert "MONTHLY20" in promo_text
    assert "WEEKLY10" in promo_text
    assert "DAILY5" in promo_text
    assert "Launch Bonus theo mệnh giá" in promo_text
    assert "PayOS, QR ngân hàng/VietQR" in promo_text
    assert "ZaloPay/MoMo, USDT và thanh toán quốc tế không áp dụng" in promo_text
    promo_callbacks = [button.callback_data for row in bot.billing_promotions_keyboard("vi").inline_keyboard for button in row]
    assert promo_callbacks == ["pricing|promo_apply", "pricing|gift_code", "menu|main_topup", "pricing|catalog", "pricing|main", "menu|main"]
    assert bot.hidden_active_features_audit("vi") == []
    assert bot.hidden_active_features_audit("vi", ["📋 Bảng giá", "💳 Nạp Xu"])[0]["code"] == "HIDDEN_ACTIVE_FEATURE"
    catalog_labels = [button.text for row in bot.pricing_catalog_keyboard("vi").inline_keyboard for button in row]
    catalog_callbacks = [button.callback_data for row in bot.pricing_catalog_keyboard("vi").inline_keyboard for button in row]
    assert "🆓 Miễn phí" not in catalog_labels
    assert "🖼 Hình ảnh" in catalog_labels
    assert "🎬 Video" in catalog_labels
    assert "📄 Tài liệu/PDF" in catalog_labels
    assert "📝 Ghi chú/Lưu trữ" in catalog_labels
    assert "pricing|package_summary" in catalog_callbacks
    image_price_text = "\n".join(bot.pricing_image_lines())
    video_price_text = "\n".join(bot.pricing_video_lines())
    combo_price_text = "\n".join(bot.pricing_combo_lines())
    frame_price_text = "\n".join(bot.pricing_frame_video_lines())
    docs_price_text = "\n".join(bot.pricing_docs_lines())
    storage_price_text = "\n".join(bot.pricing_storage_lines())
    audit_price_text = "\n".join(bot.pricing_audit_lines())
    assert "Ảnh tiết kiệm: <b>321 Xu</b>" in image_price_text
    assert "Ảnh tiêu chuẩn: <b>777 Xu</b>" in image_price_text
    assert "Video Trải Nghiệm: <b>654 Xu</b>" in video_price_text
    assert "Video Cơ Bản: <b>765 Xu</b>" in video_price_text
    assert "Video Phổ Thông: <b>876 Xu</b>" in video_price_text
    assert "Video Nâng Cao: <b>950 Xu</b>" in video_price_text
    assert "Video Bán Hàng: <b>999 Xu</b>" in video_price_text
    assert "Video Cao Cấp: <b>1111 Xu</b>" in video_price_text
    assert "Video Chuyên Nghiệp: <b>1000 Xu</b>" in video_price_text
    assert "Video Pro Plus: <b>1200 Xu</b>" in video_price_text
    assert "Video Premium: <b>1500 Xu</b>" in video_price_text
    assert "Combo Ưu Đãi TikTok" in combo_price_text
    assert "khuyến nghị 9:16" in combo_price_text
    assert "không cộng điểm nâng hạng/thưởng nạp" in combo_price_text
    assert "Local Worker/FFmpeg" in frame_price_text
    assert "Ảnh sang PDF: <b>0 Xu</b>" in docs_price_text
    assert "PDF sang ảnh: <b>0 Xu</b>" in docs_price_text
    assert "Gộp PDF: <b>0 Xu</b>" in docs_price_text
    assert "đang thử nghiệm" in docs_price_text
    assert "5 Xu" not in docs_price_text
    assert "10 Xu" not in docs_price_text
    assert "10MB cho ghi chú" in storage_price_text
    assert "40MB cho tệp" in storage_price_text
    assert "Tổng miễn phí: 50MB/tài khoản" in storage_price_text
    assert "+50MB/tháng: 10.000đ" in storage_price_text
    assert "+100MB/tháng: 20.000đ" in storage_price_text
    assert "+250MB/tháng: 50.000đ" in storage_price_text
    assert "+500MB/tháng: 100.000đ" in storage_price_text
    assert "500MB/tháng: 29.000đ" not in storage_price_text
    assert "TOAN AAS Pricing Audit V6" in audit_price_text
    assert "Feature | Price | Source | Guard" in audit_price_text
    assert "50MB free; +50MB 10.000đ/month" in audit_price_text
    assert "key/token/raw provider response" in audit_price_text
    assert 'CommandHandler("pricing_audit", cmd_pricing_audit)' in source
    combo_callbacks = [button.callback_data for row in bot.pricing_combo_keyboard("vi").inline_keyboard for button in row]
    assert "pkgbuy|combo|tiktok_99k" in combo_callbacks
    assert "pkgbuy|combo|posting_499k" in combo_callbacks
    assert "pricing|packages" in combo_callbacks
    package_hub_callbacks = [button.callback_data for row in bot.pricing_packages_keyboard("vi").inline_keyboard for button in row]
    assert package_hub_callbacks == ["pricing|plans", "pricing|combo", "pricing|my_packages", "pricing|main", "menu|main"]
    xu_text = "\n".join(bot.pricing_xu_lines())
    assert xu_text.count("💰 <b>BẢNG GIÁ XU DỊCH VỤ</b>") == 1
    plan_text = "\n".join(bot.pricing_plans_lines())
    assert "Gói tháng là hạn mức dịch vụ theo tháng" in plan_text
    assert "📦 Gói của tôi" in plan_text
    assert "/buy_plan" not in plan_text
    plan_callbacks = [button.callback_data for row in bot.pricing_plans_keyboard("vi").inline_keyboard for button in row]
    assert "pkgbuy|monthly|starter_monthly" in plan_callbacks
    assert "pkgbuy|monthly|pro_monthly" in plan_callbacks
    assert "pricing|packages" in plan_callbacks
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
    assert "🎧 Studio âm thanh" in start_labels
    assert "🎙 Voice Studio" not in start_labels
    assert "🎵 Music Studio" not in start_labels
    assert "🌐 Dịch / Phụ đề / Lồng tiếng Studio" in start_labels
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
        callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row if button.callback_data]
        assert "music_quick|showroom|root" in callbacks
        assert "menu|translate" in callbacks
        assert "menu|main_music" not in callbacks
    image_labels = [button.text for row in bot.main_image_keyboard("vi").inline_keyboard for button in row]
    assert "🖼 Tạo ảnh nhanh" in image_labels
    assert "✍️ Tạo prompt từ ảnh" in image_labels
    assert "✨ Chỉnh sửa AI" in image_labels
    assert "🧩 Chỉnh sửa ảnh" in image_labels
    assert "🎨 Công thức màu" not in image_labels
    assert "✂️ Cắt / Đổi tỉ lệ ảnh" not in image_labels
    assert "🔠 Thêm chữ / logo" not in image_labels
    assert "✨ Nâng chất lượng AI" not in image_labels
    assert "🖼 Làm nét / nâng chất lượng ảnh" not in image_labels
    assert "📐 Nâng cấp / đổi kích thước" not in image_labels
    assert "🧩 Sửa ảnh / edit ảnh" not in image_labels
    assert "🎬 Tạo video từ ảnh" not in image_labels
    image_buttons = [button for row in bot.main_image_keyboard("vi").inline_keyboard for button in row]
    image_callback_by_label = {button.text: button.callback_data for button in image_buttons}
    assert image_callback_by_label["✍️ Tạo prompt từ ảnh"] == "menu|image_prompt_start"
    assert image_callback_by_label["✨ Chỉnh sửa AI"] == "imgtool|edit_ai_start"
    assert image_callback_by_label["🧩 Chỉnh sửa ảnh"] == "menu|image_edit_start"
    image_menu_text = bot.menu_text_main_image()
    assert "Tạo ảnh nhanh" in image_menu_text
    assert "Tạo prompt từ ảnh" in image_menu_text
    assert "Chỉnh sửa ảnh" in image_menu_text
    assert "Nâng cấp / đổi kích thước" not in image_menu_text
    prompt_start_labels = [button.text for row in bot.image_prompt_start_keyboard("vi").inline_keyboard for button in row]
    assert "📷 Gửi ảnh" in prompt_start_labels
    assert "✍️ Nhập mô tả thủ công" in prompt_start_labels
    assert "Tạo prompt từ ảnh" in bot.image_prompt_menu_start_text("vi")
    prompt_goal_labels = [button.text for row in bot.image_prompt_goal_keyboard("vi").inline_keyboard for button in row]
    assert "📦 Ảnh sản phẩm" in prompt_goal_labels
    assert "📢 Ảnh quảng cáo" in prompt_goal_labels
    assert "🎬 Ảnh cinematic/video" in prompt_goal_labels
    assert bot.image_prompt_style_suggestions("product") == ["Studio sạch đẹp", "Luxury showroom", "Lifestyle đời thường"]
    prompt_text, prompt_value = bot.build_image_prompt_output({
        "goal_code": "product",
        "subject": "máy xay sinh tố mini màu xanh ngọc",
        "style": "Luxury showroom",
        "ratio": "16:9",
    })
    assert "Prompt ảnh đã tạo" in prompt_text
    assert "Prompt ngắn" in prompt_text
    assert "Prompt chi tiết" in prompt_text
    assert "Negative prompt" in prompt_text
    assert "Bot chưa gọi provider ảnh và chưa trừ Xu" in prompt_text
    assert "máy xay sinh tố mini màu xanh ngọc" in prompt_value
    prompt_output_callbacks = [button.callback_data for row in bot.image_prompt_output_keyboard("vi").inline_keyboard for button in row]
    assert "imgtool|prompt_use" in prompt_output_callbacks
    assert "imgtool|prompt_change_ratio" in prompt_output_callbacks
    assert "imgtool|prompt_variants" in prompt_output_callbacks
    assert "imgtool|prompt_save" in prompt_output_callbacks
    prompt_tier_callbacks = [button.callback_data for row in bot.image_prompt_tier_keyboard("vi").inline_keyboard for button in row]
    assert any(callback.startswith("imgtool|prompt_tier|") for callback in prompt_tier_callbacks)
    edit_start_labels = [button.text for row in bot.image_edit_start_keyboard("vi").inline_keyboard for button in row]
    assert "📷 Gửi ảnh" in edit_start_labels
    assert "✍️ Chỉ tạo prompt sửa ảnh" not in edit_start_labels
    edit_choice_labels = [button.text for row in bot.image_edit_choice_keyboard("vi").inline_keyboard for button in row]
    assert "✂️ Cắt / đổi tỉ lệ" in edit_choice_labels
    assert "📐 Resize pixel" in edit_choice_labels
    assert "🔤 Thêm chữ / logo" in edit_choice_labels
    assert "🎨 Công thức màu" in edit_choice_labels
    assert "✨ Chỉnh sửa AI" not in edit_choice_labels
    assert "✨ Nâng chất lượng AI" in edit_choice_labels
    assert "✍️ Nhập yêu cầu riêng" in edit_choice_labels
    assert "🎬 Chuẩn bị ảnh cho video" not in edit_choice_labels
    assert bot.image_edit_suggestions("background_color") == ["Nền trắng studio sạch đẹp", "Luxury showroom", "Đổi tông màu nhưng giữ sản phẩm"]
    edit_prompt = bot.image_edit_prompt_text({"edit_type": "background_color", "edit_request": "Luxury showroom"})
    assert "Prompt sửa ảnh đã sẵn sàng" in edit_prompt
    assert "prompt-only" in edit_prompt
    assert "chưa gọi provider" in edit_prompt and "chưa trừ Xu" in edit_prompt
    assert bot.IMAGE_EDIT_BASIC_XU == 50
    assert bot.IMAGE_EDIT_STANDARD_XU == 200
    resize_choice_labels = [button.text for row in bot.image_resize_choice_keyboard("vi").inline_keyboard for button in row]
    assert "✂️ Cắt / đổi tỉ lệ" in resize_choice_labels
    assert "📐 Resize pixel" in resize_choice_labels
    assert "🔤 Thêm chữ / logo" in resize_choice_labels
    assert "🎨 Công thức màu" in resize_choice_labels
    assert "✨ Chỉnh sửa AI" not in resize_choice_labels
    assert "✨ Nâng chất lượng AI" in resize_choice_labels
    assert "✍️ Nhập yêu cầu riêng" in resize_choice_labels
    assert "🎬 Chuẩn bị ảnh cho video" not in resize_choice_labels
    resize_method_labels = [button.text for row in bot.image_resize_method_keyboard("vi").inline_keyboard for button in row]
    assert resize_method_labels[0] == "🌫 Nền mờ, không cắt chủ thể"
    assert "✂️ Cắt vừa khung" in resize_method_labels
    assert "⬜ Thêm nền/viền" in resize_method_labels
    assert bot.parse_image_pixel_size("1920x1080") == (1920, 1080)
    assert bot.normalize_image_tool_ratio("9x16") == "9:16"
    if bot.Image is not None:
        src = bot.Image.new("RGB", (320, 180), (10, 120, 200))
        src_buf = io.BytesIO()
        src.save(src_buf, format="PNG")
        ok, out_bytes, size_text, method = bot.process_image_local_resize_bytes(src_buf.getvalue(), "9:16", "pad")
        assert ok
        assert size_text == "1080x1920"
        assert method == "pad"
        assert out_bytes.startswith(b"\x89PNG")
    assert 'CallbackQueryHandler(handle_image_tools_callback, pattern=r"^imgtool\\|")' in source
    assert "menu|hint_image_to_video_pack" not in [button.callback_data for button in image_buttons]
    assert "menu|hint_image_tools" not in [button.callback_data for button in image_buttons]
    assert "💳 Xem bảng giá" not in image_labels
    assert "💰 Xem giá" not in image_labels
    assert "📞 Liên hệ admin" not in image_labels
    video_buttons = [button for row in bot.main_video_keyboard("vi").inline_keyboard for button in row]
    assert any(button.text == "🎬 Video AI chân thật" and button.callback_data == "vproduct|open|video_ai_real" for button in video_buttons)
    assert not any(button.text == "✨ Làm theo từng bước" for button in video_buttons)
    assert any(button.text == "🔥 Video theo trend" and button.callback_data == "vproduct|open|video_trend" for button in video_buttons)
    video_labels = [button.text for button in video_buttons]
    assert video_labels == [
        "🔥 Video theo trend",
        "🧠 Ý tưởng video",
        "🎞 Storyboard + Prompt",
        "🎥 Prompt / Chuyển động",
        "🎬 Video AI chân thật",
        "🧩 Kịch bản → Ảnh → Video",
        "🖼 Ảnh → Video",
        "🎞 Ghép ảnh thành video",
        "🎥 Tự quay & đổi cảnh AI",
        "🎬 Phim AI nhiều cảnh",
        "📥 Video mẫu / Kênh mẫu",
        "🎵 Nhạc / Voice / SFX",
        "🛠 Chỉnh sửa video local",
        "🏠 Menu chính",
    ]
    assert "🎬 Tạo video nhanh" not in video_labels
    assert "🖼➡️🎬 Tạo video AI từ ảnh" not in video_labels
    assert "✍️ Tạo prompt video" not in video_labels
    assert "💳 Xem bảng giá" not in video_labels
    assert "💰 Xem giá" not in video_labels
    assert "📞 Liên hệ admin" not in video_labels
    video_ai_labels = [button.text for row in bot.video_ai_true_keyboard("vi").inline_keyboard for button in row]
    assert video_ai_labels == ["📝 Prompt → Video AI", "🖼 Ảnh → Video AI", "🎞 Video mẫu → Video AI", "📊 Trạng thái video", "🔙 Quay lại Video", "🏠 Menu chính"]
    video_ai_callbacks = [button.callback_data for row in bot.video_ai_true_keyboard("vi").inline_keyboard for button in row]
    assert "promptvideo|start" in video_ai_callbacks
    assert "imagevideo|start" in video_ai_callbacks
    assert "videoref|start" in video_ai_callbacks
    assert "create_media|quick_video" not in video_ai_callbacks
    assert "menu|hint_image_to_video_pack" not in video_ai_callbacks
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_VIDEO_ENABLED", False)
    assert "Video AI chân thật hiện đang được bảo trì" in bot.video_ai_true_text("vi")
    frame_intro_labels = [button.text for row in bot.video_frame_intro_keyboard("vi").inline_keyboard for button in row]
    assert "📷 Bắt đầu ghép ảnh" in frame_intro_labels
    assert "Local Worker + ffmpeg" in bot.video_frame_intro_text("vi")
    assert "Không dùng VEO" in bot.video_frame_intro_text("vi")
    assert "Tự quay & đổi cảnh AI" in bot.video_self_scene_ai_text("vi")
    assert "Mở màn hình này chưa xử lý video và chưa trừ Xu" in bot.video_self_scene_ai_text("vi")
    self_scene_labels = [button.text for row in bot.self_scene_input_keyboard("vi").inline_keyboard for button in row]
    assert "1️⃣ Chọn hướng 1" in self_scene_labels
    assert "2️⃣ Chọn hướng 2" in self_scene_labels
    assert "3️⃣ Chọn hướng 3" in self_scene_labels
    assert "🔄 Đổi gợi ý khác" in self_scene_labels
    assert "✍️ Nhập hướng riêng" in self_scene_labels
    self_scene_object_labels = [button.text for row in bot.self_scene_object_keyboard("vi").inline_keyboard for button in row]
    assert "👤 Người thật" in self_scene_object_labels
    assert "📦 Sản phẩm" in self_scene_object_labels
    assert "🐶 Thú cưng/vật phẩm" in self_scene_object_labels
    assert "✍️ Nhập riêng" in self_scene_object_labels
    product_contexts = bot.self_scene_context_suggestions("product", "máy xay sinh tố mini màu xanh ngọc")
    assert len(product_contexts) == 3
    assert any("Luxury showroom" in item for item in product_contexts)
    assert any("Nhà bếp hiện đại" in item for item in product_contexts)
    assert any("Quán cafe / lifestyle" in item for item in product_contexts)
    self_scene_plan = bot.self_scene_plan_text({
        "input_type": "product",
        "selected_topic": "máy xay sinh tố mini màu xanh ngọc",
        "selected_context": product_contexts[0],
        "selected_style": "cinematic",
    })
    assert "Kế hoạch đổi cảnh video" in self_scene_plan
    assert "Prompt ảnh/keyframe" in self_scene_plan
    assert "Prompt video" in self_scene_plan
    assert "Gợi ý chuyển động" in self_scene_plan
    assert "Lưu ý giữ nhận diện" in self_scene_plan
    assert "TOAN AAS chưa xử lý video thật và chưa trừ Xu" in self_scene_plan
    long_script_labels = [button.text for row in bot.video_long_script_keyboard("vi").inline_keyboard for button in row]
    assert "3 phút" in long_script_labels and "60 phút" in long_script_labels
    assert "Chưa tạo video dài hàng loạt" in bot.video_long_script_text("vi")
    long_topic_labels = [button.text for row in bot.long_video_topic_keyboard("vi").inline_keyboard for button in row]
    assert "1️⃣ Bán hàng / affiliate" in long_topic_labels
    assert "2️⃣ Giáo dục / hướng dẫn" in long_topic_labels
    assert "3️⃣ Kể chuyện / giải trí" in long_topic_labels
    assert bot.long_video_structure_suggestions("10 phút") == ["10 đoạn x 60 giây", "20 đoạn x 30 giây", "5 chương x 2 phút"]
    long_plan = bot.long_video_plan_text({
        "selected_topic": "affiliate AI tool cho người mới",
        "duration": "10 phút",
        "selected_style": "professional",
    })
    assert "Lộ trình video dài AI" in long_plan
    assert "Prompt ảnh" in long_plan
    assert "Prompt video" in long_plan
    assert "Phong cách voice gợi ý" in long_plan
    assert "Nhạc/SFX gợi ý" in long_plan
    assert "TOAN AAS chưa xử lý thật và chưa trừ Xu" in long_plan
    vi_video_off = bot.public_video_off_options_text("vi")
    assert "Hệ thống tạo video đang bảo trì/nâng cấp nhẹ" in vi_video_off
    assert "TOAN AAS chưa xử lý video" in vi_video_off
    assert "chưa trừ Xu" in vi_video_off
    en_video_off = bot.public_video_off_options_text("en")
    assert "Real video generation is not public yet" in en_video_off
    assert "has not called the video API" in en_video_off
    from_image_off = bot.image_to_video_public_off_prompt(0, "u_video_off", "vi")
    assert "Prompt ảnh thành video" in from_image_off
    assert "TOAN AAS chưa xử lý video" in from_image_off
    assert "shopaikey_video_create" not in from_image_off
    docs_labels = [button.text for row in bot.main_docs_keyboard("vi").inline_keyboard for button in row]
    assert "💰 Xem giá" not in docs_labels
    assert "📄 PDF sang Word" in docs_labels
    assert "🖼 Ảnh sang PDF" in docs_labels
    memory_labels = [button.text for row in bot.main_memory_keyboard("vi").inline_keyboard for button in row]
    assert "📝 Tạo ghi chú" in memory_labels
    assert "⏰ Nhắc hẹn" in memory_labels
    assert "📄 Lưu tài liệu" in memory_labels
    assert "💾 Dung lượng của tôi" in memory_labels
    assert "📦 Mua thêm dung lượng" in memory_labels
    assert "🧹 Dọn file cũ" in memory_labels
    assert "📄 PDF sang Word" not in memory_labels
    assert "🧩 Gộp PDF" not in memory_labels
    image_keyboard_source = source_between(source, "def main_image_keyboard", "def main_audio_keyboard")
    assert "hint_image_tools" not in image_keyboard_source
    assert "hint_image_to_video_pack" not in image_keyboard_source
    assert "image_prompt_start" in image_keyboard_source
    assert "image_edit_start" in image_keyboard_source
    assert "image_upscale_start" not in image_keyboard_source
    assert "Tạo prompt từ ảnh" in image_keyboard_source
    assert "Chỉnh sửa ảnh" in image_keyboard_source
    image_video_parent, _hint = bot.menu_hint_text("hint_image_to_video_pack")
    assert image_video_parent == "main_video"
    assert "/image_to_video_pack" not in bot.menu_text_main_image_i18n("en")
    message_handler_source = message_source
    assert "handle_image_menu_pending_text(update, context)" in message_handler_source
    assert message_handler_source.index("handle_image_menu_pending_text") < message_handler_source.index("handle_quick_media_pending_text")
    photo_handler_source = source_between(source, "async def handle_photo", "async def handle_document_cache_only")
    assert "handle_image_menu_pending_photo(update, context)" in photo_handler_source
    assert photo_handler_source.index("handle_image_menu_pending_photo") < photo_handler_source.index("handle_frame_video_photo")
    outside_image_labels = [button.text for row in bot.image_upload_outside_flow_keyboard("vi").inline_keyboard for button in row]
    assert "🧩 Chỉnh sửa ảnh" in outside_image_labels
    assert "✍️ Tạo prompt từ ảnh" in outside_image_labels
    assert "📄 Ảnh sang PDF" in outside_image_labels
    assert "🎞 Dùng ảnh làm video" in outside_image_labels
    outside_image_text = bot.image_upload_outside_flow_text("vi")
    assert "TOAN AAS đã nhận ảnh" in outside_image_text
    assert "/image_to_music_video" not in photo_handler_source
    assert "/remove_bg" not in photo_handler_source
    assert "/ai_image_edit" not in photo_handler_source
    assert "🧩 Gộp PDF" in docs_labels
    assert ["⬅️ Ghi chú / Tài liệu", "🏠 Menu chính"] in [
        [button.text for button in row] for row in bot.main_docs_keyboard("vi").inline_keyboard
    ]
    merge_section, merge_hint = bot.menu_hint_text("hint_doc_merge_pdf")
    assert merge_section == "main_docs"
    assert "Gộp PDF" in merge_hint
    assert "gửi từng file PDF" in merge_hint
    memory_text = bot.menu_text_main_memory()
    assert "Ghi chú / Tài liệu" in memory_text
    assert "10MB cho ghi chú/text/nhắc hẹn" in memory_text
    assert "40MB cho tệp/ảnh/âm thanh" in memory_text
    assert "Tổng 50MB miễn phí" in memory_text
    assert "+50MB/tháng: 10.000đ" in memory_text
    assert "Ghi chú text nhỏ vẫn tính dung lượng thật" in memory_text
    assert "File đính kèm tính đúng size file" in memory_text
    assert "File tạm không tính vào quota lâu dài" in memory_text
    assert "Flow tài liệu sẽ hướng dẫn gửi file" in memory_text
    assert "/pdf_to_word" not in memory_text
    assert "/image_to_pdf" not in memory_text
    memory_plan_text = bot.memory_plan_text()
    assert "Tổng 50MB miễn phí" in memory_plan_text
    assert "+50MB/tháng: 10.000đ" in memory_plan_text
    assert "+100MB/tháng: 20.000đ" in memory_plan_text
    assert "+250MB/tháng: 50.000đ" in memory_plan_text
    assert "+500MB/tháng: 100.000đ" in memory_plan_text
    assert "Lite — 19.000" not in memory_plan_text
    assert "5MB storage" not in memory_plan_text
    assert bot.TOTAL_FREE_STORAGE_MB == 50
    assert bot.NOTES_TEXT_FREE_MB == 10
    assert bot.FILES_AUDIO_FREE_MB == 40
    topup_labels = [button.text for row in bot.main_topup_keyboard("vi").inline_keyboard for button in row]
    assert "💰 Xem giá" not in topup_labels
    assert [[button.text for button in row] for row in bot.main_topup_keyboard("vi").inline_keyboard] == [
        ["💳 10k", "💳 20k"],
        ["💳 50k", "💳 100k"],
        ["💳 200k", "💳 500k"],
        ["🏦 Nạp thủ công"],
        ["🔙 Quay lại bảng giá", "🏠 Menu chính"],
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
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(5)], "duration": "fast", "effect": "fade"}) == 20
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(7)], "duration": "fast", "effect": "fade"}) == 30
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(5)], "duration": "standard", "effect": "fade"}) == 30
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(10)], "duration": "standard", "effect": "zoom"}) == 60
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(5)], "duration": "slow", "effect": "zoom"}) == 40
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(10)], "duration": "slow", "effect": "pan"}) == 80
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(15)], "duration": "slow", "effect": "random"}) == 120
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(20)], "duration": "fast", "effect": "pan"}) == 60
    status = bot.frame_video_status_payload()
    assert int(status["price_xu"]) == int(bot.LOCAL_FRAME_VIDEO_MIN_XU)
    assert int(status["price_per_second_xu"]) == int(bot.LOCAL_FRAME_VIDEO_XU_PER_SECOND)
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
        assert "feedback|cat|payment_topup" in feedback_buttons
        assert "feedback|cat|image_error" in feedback_buttons
        assert "feedback|cat|video_error" in feedback_buttons
        assert "feedback|cat|refund" in feedback_buttons
        assert "feedback|cancel" not in feedback_buttons

        bot.USER_PENDING.pop(bot.feedback_pending_key("u_feedback"), None)
        bot.set_feedback_pending("u_feedback", "video_error")
        pending = bot.get_feedback_pending("u_feedback")
        assert pending and pending["pending_action"] == "feedback"
        assert pending["category"] == "video_error"

        class FakeUser:
            id = "u_feedback"
            username = "tester"
            first_name = "Tester"

        feedback_id = bot.store_customer_feedback(FakeUser(), "video_error", "Video tạo hơi lâu", "trend_video_flow")
        assert feedback_id > 0
        conn = bot.db_connect()
        try:
            row = conn.execute("SELECT category, content, context, status FROM feedback WHERE id=?", (feedback_id,)).fetchone()
        finally:
            conn.close()
        assert row == ("video_error", "Video tạo hơi lâu", "trend_video_flow", "new")
        assert bot.clear_feedback_pending("u_feedback") is True
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_support_ticket_schema_migration_is_additive_and_idempotent(monkeypatch, tmp_path):
    db_path = tmp_path / "legacy_support.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """CREATE TABLE support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                message TEXT
            )"""
        )
        conn.execute("INSERT INTO support_tickets (user_id, message) VALUES (?, ?)", ("legacy-user", "keep this ticket"))
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "DB_STARTUP_BACKUP_PATHS", set())
    bot.init_db()
    bot.init_db()

    conn = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(support_tickets)").fetchall()}
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(support_tickets)").fetchall()}
        legacy = conn.execute("SELECT user_id, message FROM support_tickets WHERE user_id='legacy-user'").fetchone()
        message_table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='support_ticket_messages'").fetchone()
    finally:
        conn.close()

    assert {
        "ticket_code", "category", "priority", "status", "attachment_file_id",
        "admin_note", "suggested_reply", "assigned_admin_id", "closed_at",
    }.issubset(columns)
    assert "idx_support_tickets_status" in indexes
    assert "idx_support_tickets_user" in indexes
    assert legacy == ("legacy-user", "keep this ticket")
    assert message_table == ("support_ticket_messages",)


def test_support_ticket_public_isolation_reply_and_refund_marker(monkeypatch, tmp_path):
    db_path = tmp_path / "support.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "DB_STARTUP_BACKUP_PATHS", set())
    bot.init_db()

    class UserOne:
        id = "support-user-1"
        username = "customer_one"
        first_name = "Customer One"

    class UserTwo:
        id = "support-user-2"
        username = "customer_two"
        first_name = "Customer Two"

    ticket = bot.create_support_ticket(UserOne(), "payment_topup", "Tôi đã nạp nhưng chưa thấy Xu")
    other = bot.create_support_ticket(UserTwo(), "image_error", "Ảnh chưa đúng prompt")
    assert ticket["priority"] == "high"
    assert bot.get_support_ticket(ticket["id"], UserOne.id)["id"] == ticket["id"]
    assert bot.get_support_ticket(ticket["id"], UserTwo.id) is None
    assert [row["id"] for row in bot.list_support_tickets(user_id=UserOne.id)] == [ticket["id"]]
    assert [row["id"] for row in bot.list_support_tickets(user_id=UserTwo.id)] == [other["id"]]

    bot.update_support_ticket(ticket["id"], admin_note="internal-only-note", status="refund_pending")
    bot.add_support_ticket_message(ticket["id"], "admin", "admin-1", "TOAN AAS đang kiểm tra giao dịch.", "sent")
    refreshed = bot.get_support_ticket(ticket["id"])
    public_text = bot.public_support_ticket_text(refreshed)
    assert refreshed["status"] == "refund_pending"
    assert "internal-only-note" not in public_text
    assert "TOAN AAS đang kiểm tra giao dịch" in public_text


def test_support_ticket_priority_overdue_and_templates():
    from support_v1b import (
        AAS_SUPPORT_SYSTEM_PERSONA,
        SUPPORT_REPLY_TEMPLATES,
        classify_support_escalation,
        format_support_reply,
        overdue_reason,
        suggested_reply,
        support_reply_for_classification,
        ticket_priority,
    )

    assert ticket_priority("payment_topup", "missing") == "high"
    assert ticket_priority("refund", "please check") == "high"
    assert ticket_priority("video_error", "Video lỗi và bị trừ Xu") == "high"
    assert ticket_priority("other", "Bot làm ăn kiểu gì, trừ Xu mà không ra video") == "urgent"
    assert ticket_priority("feature_request", "new idea") == "low"
    assert ticket_priority("image_error", "wrong image") == "normal"
    assert overdue_reason("new", "2026-06-01 00:00:00", datetime(2026, 6, 2, 1, 0, 0))
    assert overdue_reason("waiting_provider", "2026-06-01 00:00:00", datetime(2026, 6, 3, 23, 0, 0)) == ""
    assert overdue_reason("waiting_provider", "2026-06-01 00:00:00", datetime(2026, 6, 4, 1, 0, 0))
    assert "chưa tự động" in suggested_reply("refund", 0).lower()
    assert "không khẳng định đã hoàn xu" in AAS_SUPPORT_SYSTEM_PERSONA.lower()
    assert {
        "onboarding", "pricing", "payment", "technical_error", "refund_complaint",
        "feature_question", "admin_escalation", "out_of_scope", "closing",
    }.issubset(SUPPORT_REPLY_TEMPLATES)

    onboarding = classify_support_escalation("Bot này làm được gì?")
    assert onboarding["category"] == "onboarding"
    assert onboarding["needs_admin"] is False
    assert "tạo ảnh AI" in support_reply_for_classification(onboarding)

    payment = classify_support_escalation("Tôi nạp tiền rồi chưa thấy Xu")
    assert payment["ticket_category"] == "payment_topup"
    assert payment["needs_admin"] is True
    assert payment["priority"] == "high"
    assert payment["should_alert_admin"] is True

    angry = classify_support_escalation("Bot làm ăn kiểu gì, trừ Xu mà không ra video")
    assert angry["suggested_reply_id"] == "angry_customer"
    assert angry["priority"] == "urgent"
    assert "đã hoàn Xu" not in support_reply_for_classification(angry)

    pricing = classify_support_escalation("Gói AI này đắt quá")
    assert pricing["suggested_reply_id"] == "pricing_objection"
    assert pricing["needs_admin"] is False

    b2b = classify_support_escalation("Anh muốn làm hợp đồng doanh nghiệp")
    assert b2b["category"] == "admin_escalation"
    assert b2b["priority"] == "high"
    assert b2b["should_create_ticket"] is True

    unsafe = classify_support_escalation("Bên em hack nick Facebook được không?")
    assert unsafe["category"] == "out_of_scope"
    assert unsafe["needs_admin"] is False

    technical = classify_support_escalation("Deepgram có nhận diện từ lóng không?")
    assert technical["category"] == "technical_error"
    assert technical["needs_admin"] is True

    formatted = format_support_reply("Kính gửi quý khách. Đã hoàn Xu. Chắc chắn 100%.")
    assert "Kính gửi quý khách" not in formatted
    assert "Đã hoàn Xu" not in formatted
    assert "Chắc chắn 100%" not in formatted


def test_support_ticket_menu_admin_registry_and_no_auto_refund():
    source = bot_source_text()
    admin_buttons = [
        button.callback_data
        for row in bot.menu_nav_keyboard("admin", True).inline_keyboard
        for button in row
        if button.callback_data
    ]
    public_buttons = [
        button.callback_data
        for row in bot.support_ticket_menu_keyboard().inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "ticket|admin" in admin_buttons
    assert "ticket|cat|payment_topup" in public_buttons
    assert "ticket|cat|lead_consulting" in public_buttons
    assert "ticket|mine" in public_buttons
    assert 'CommandHandler("tickets",     cmd_tickets)' in source
    assert 'CommandHandler("ticket_admin", cmd_ticket_admin)' in source
    assert 'CommandHandler("ticket_overdue", cmd_ticket_overdue)' in source
    assert 'CommandHandler("support_persona_test", cmd_support_persona_test)' in source
    assert 'CallbackQueryHandler(handle_ticket_callback, pattern=r"^ticket\\|")' in source
    ticket_callback_source = source_between(source, "async def handle_ticket_callback", "async def handle_menu_callback")
    assert 'status="refund_pending"' not in ticket_callback_source
    assert "update_support_ticket(ticket_id, status=new_status)" in ticket_callback_source
    assert "add_credits(" not in ticket_callback_source
    assert "refund_shopaikey_job(" not in ticket_callback_source


def test_support_persona_ticket_dedupes_same_user_category(monkeypatch, tmp_path):
    db_path = tmp_path / "support_persona.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "DB_STARTUP_BACKUP_PATHS", set())
    bot.init_db()

    customer = SimpleNamespace(id="persona-customer", username="persona", first_name="Persona")
    classification = bot.classify_support_escalation("Tôi nạp tiền rồi chưa thấy Xu")
    first, first_is_new = bot.create_or_append_support_ticket(
        customer, "payment_topup", "Tôi nạp tiền rồi chưa thấy Xu", classification
    )
    second, second_is_new = bot.create_or_append_support_ticket(
        customer, "payment_topup", "Số tiền là 100k, chuyển lúc 10 giờ", classification
    )

    assert first_is_new is True
    assert second_is_new is False
    assert second["id"] == first["id"]
    conn = sqlite3.connect(db_path)
    try:
        messages = conn.execute(
            "SELECT message FROM support_ticket_messages WHERE ticket_id=? ORDER BY id",
            (first["id"],),
        ).fetchall()
    finally:
        conn.close()
    assert [row[0] for row in messages] == [
        "Tôi nạp tiền rồi chưa thấy Xu",
        "Số tiền là 100k, chuyển lúc 10 giờ",
    ]


def test_support_persona_admin_test_is_preview_only(monkeypatch):
    class FakeMessage:
        def __init__(self):
            self.sent = []

        async def reply_text(self, text, **kwargs):
            self.sent.append((text, kwargs))

    message = FakeMessage()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=str(bot.ADMIN_ID)),
        message=message,
    )
    context = SimpleNamespace(args=["Bot", "làm", "ăn", "kiểu", "gì,", "trừ", "Xu", "mà", "không", "ra", "video"])

    monkeypatch.setattr(bot, "create_or_append_support_ticket", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not create ticket")))
    asyncio.run(bot.cmd_support_persona_test(update, context))

    payload = message.sent[0][0]
    assert "CSKH Persona Test" in payload
    assert "Priority: <code>urgent</code>" in payload
    assert "Would create ticket: <b>yes</b>" in payload
    assert "Không tạo ticket" in payload


def test_support_feedback_split_and_lead_menus():
    support_labels = [
        button.text
        for row in bot.human_support_keyboard().inline_keyboard
        for button in row
    ]
    feedback_callbacks = [
        button.callback_data
        for row in bot.feedback_category_keyboard("vi").inline_keyboard
        for button in row
        if button.callback_data
    ]
    premium_callbacks = [
        button.callback_data
        for row in bot.support_premium_keyboard().inline_keyboard
        for button in row
        if button.callback_data
    ]
    bot_callbacks = [
        button.callback_data
        for row in bot.support_custom_bot_keyboard().inline_keyboard
        for button in row
        if button.callback_data
    ]
    source = bot_source_text()

    assert "👨‍💼 Nhắn admin @toanaas" in support_labels
    assert "🎫 Tạo ticket hỗ trợ" in support_labels
    assert "⭐ Đăng ký Premium" in support_labels
    assert "🤖 Kết nối bot riêng" in support_labels
    assert "📦 Tư vấn gói dịch vụ" in support_labels
    assert "Góp ý / Báo lỗi" in bot.human_support_text()
    assert "Premium" not in bot.feedback_start_text("vi")
    assert "feedback|cat|payment_topup" in feedback_callbacks
    assert "feedback|cat|refund" in feedback_callbacks
    assert "support|premium_type|business" in premium_callbacks
    assert "support|bot_type|support" in bot_callbacks
    assert 'CallbackQueryHandler(handle_human_support_callback, pattern=r"^support\\|")' in source


def test_support_v3_menu_states_and_back_routing(monkeypatch):
    replies = []

    async def fake_edit(_query, text, reply_markup=None, **kwargs):
        replies.append({"text": str(text), "reply_markup": reply_markup})
        return SimpleNamespace(text=text, reply_markup=reply_markup)

    class FakeQuery:
        def __init__(self, data, user_id=93001):
            self.data = data
            self.from_user = SimpleNamespace(id=user_id)
            self.message = SimpleNamespace()

        async def answer(self, *args, **kwargs):
            return None

    async def press(data, user_id=93001):
        await bot.handle_human_support_callback(
            SimpleNamespace(callback_query=FakeQuery(data, user_id)),
            SimpleNamespace(),
        )
        return replies[-1]

    monkeypatch.setattr(bot, "safe_edit_or_send", fake_edit)
    labels = [button.text for row in bot.human_support_keyboard().inline_keyboard for button in row]
    assert "📂 Ticket của tôi" in labels
    assert "👨‍💼 Nhắn admin @toanaas" in labels
    assert "🎫 Tạo ticket hỗ trợ" in labels

    bot.clear_support_ticket_pending(93001)
    asyncio.run(press("support|ticket"))
    state = bot.get_support_ticket_pending(93001)
    assert state["support_flow"] == "create_support_ticket"
    assert state["support_pending_input"] is True
    assert state["support_origin"] == "support_main"
    assert state["awaiting_support_message"] == "1"
    ticket_prompt_callbacks = [
        button.callback_data
        for row in replies[-1]["reply_markup"].inline_keyboard
        for button in row
    ]
    assert "ticket|mine" in ticket_prompt_callbacks
    assert "support|start" in ticket_prompt_callbacks

    bot.clear_support_ticket_pending(93001)
    shop_page = asyncio.run(press("support|bot_type|shop"))
    assert "Bot bán hàng/shop online" in shop_page["text"]
    shop_callbacks = [button.callback_data for row in shop_page["reply_markup"].inline_keyboard for button in row]
    assert "support|bot_input|shop" in shop_callbacks
    assert "support|bot" in shop_callbacks
    asyncio.run(press("support|bot_input|shop"))
    shop_state = bot.get_support_ticket_pending(93001)
    assert shop_state["category"] == "custom_bot_lead"
    assert shop_state["lead_type"] == "shop_bot"
    assert shop_state["support_flow"] == "custom_bot_lead"
    assert shop_state["support_origin"] == "custom_bot"
    assert shop_state["back_to"] == "support|bot_type|shop"

    bot.clear_support_ticket_pending(93001)
    video_page = asyncio.run(press("support|consult_type|video"))
    video_callbacks = [button.callback_data for row in video_page["reply_markup"].inline_keyboard for button in row]
    assert "support|consult_need|video|0" in video_callbacks
    assert "support|consult" in video_callbacks
    asyncio.run(press("support|consult_need|video|0"))
    consult_state = bot.get_support_ticket_pending(93001)
    assert consult_state["category"] == "service_consulting"
    assert consult_state["service_type"] == "video"
    assert consult_state["service_group"] == "video"
    assert consult_state["support_origin"] == "service_consulting"
    assert consult_state["back_to"] == "support|consult_type|video"

    bot.clear_support_ticket_pending(93001)
    asyncio.run(press("support|premium_type|shop"))
    premium_state = bot.get_support_ticket_pending(93001)
    assert premium_state["category"] == "premium_lead"
    assert premium_state["support_flow"] == "premium_lead"
    assert premium_state["support_origin"] == "premium"
    assert premium_state["back_to"] == "support|premium"


def test_support_v3_pending_input_creates_tickets_and_auto_replies(monkeypatch, tmp_path):
    db_path = tmp_path / "support_v3.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "DB_STARTUP_BACKUP_PATHS", set())
    bot.init_db()

    class FakeMessage:
        def __init__(self, text):
            self.text = text
            self.sent = []

        async def reply_text(self, text, **kwargs):
            self.sent.append((str(text), kwargs))

    class FakeBot:
        def __init__(self):
            self.sent = []

        async def send_message(self, **kwargs):
            self.sent.append(kwargs)

    async def submit(user_id, text, **state):
        user = SimpleNamespace(id=user_id, username=f"user_{user_id}", first_name="Support")
        message = FakeMessage(text)
        fake_bot = FakeBot()
        bot.set_support_ticket_pending(user_id, state.pop("step", "awaiting_message"), **state)
        handled = await bot.handle_support_ticket_pending_text(
            SimpleNamespace(effective_user=user, message=message),
            SimpleNamespace(bot=fake_bot),
        )
        return handled, message, fake_bot, bot.list_support_tickets(user_id=user_id)[0]

    handled, payment_message, payment_alert, payment_ticket = asyncio.run(submit(
        "support-payment",
        "Tôi nạp tiền chưa thấy Xu",
        category="general_support",
    ))
    assert handled is True
    assert payment_ticket["category"] == "payment_topup"
    assert payment_ticket["priority"] == "high"
    assert "Mã ticket" in payment_message.sent[0][0]
    assert payment_alert.sent
    assert bot.get_support_ticket_pending("support-payment") is None
    assert bot.get_last_support_ticket_id("support-payment") == payment_ticket["id"]

    handled, angry_message, angry_alert, angry_ticket = asyncio.run(submit(
        "support-angry",
        "Bot trừ Xu mà không ra video",
        category="general_support",
    ))
    assert handled is True
    assert angry_ticket["priority"] == "urgent"
    assert "đã hoàn Xu" not in angry_message.sent[0][0]
    assert angry_alert.sent

    handled, shop_message, shop_alert, shop_ticket = asyncio.run(submit(
        "support-shop",
        "Tôi bán mỹ phẩm trên TikTok Shop và muốn tự động trả lời khách, lưu lead",
        step="lead_input",
        category="custom_bot_lead",
        selected_option="🛒 Bot bán hàng/shop online",
        lead_type="shop_bot",
    ))
    assert handled is True
    assert shop_ticket["category"] == "custom_bot_lead"
    assert shop_ticket["priority"] == "high"
    assert "bot bán hàng/shop online" in shop_message.sent[0][0]
    assert shop_alert.sent

    handled, premium_message, premium_alert, premium_ticket = asyncio.run(submit(
        "support-premium",
        "Tôi cần tạo ảnh và video mỗi ngày cho shop",
        step="lead_input",
        category="premium_lead",
        selected_option="Shop/Affiliate",
        lead_type="premium_shop",
    ))
    assert handled is True
    assert premium_ticket["category"] == "premium_lead"
    assert premium_ticket["priority"] == "high"
    assert "Mã ticket" in premium_message.sent[0][0]
    assert premium_alert.sent

    handled, consult_message, consult_alert, consult_ticket = asyncio.run(submit(
        "support-consult",
        "Tôi cần 20 video TikTok mỗi tháng, ngân sách vừa phải",
        step="lead_input",
        category="service_consulting",
        selected_option="🎬 Tư vấn tạo video — TikTok/Affiliate",
        service_type="video",
        lead_type="video",
    ))
    assert handled is True
    assert consult_ticket["category"] == "service_consulting"
    assert "tư vấn gói video" in consult_message.sent[0][0]
    assert consult_alert.sent == []


def test_support_auto_test_command_is_preview_only(monkeypatch):
    class FakeMessage:
        def __init__(self):
            self.sent = []

        async def reply_text(self, text, **kwargs):
            self.sent.append((str(text), kwargs))

    message = FakeMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=str(bot.ADMIN_ID)), message=message)
    context = SimpleNamespace(args=["tôi", "muốn", "đăng", "ký", "premium"])
    monkeypatch.setattr(
        bot,
        "create_or_append_support_ticket",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("preview must not create ticket")),
    )

    asyncio.run(bot.cmd_support_auto_test(update, context))

    payload = message.sent[0][0]
    assert "Support Auto Reply Test" in payload
    assert "Category: <code>premium_lead</code>" in payload
    assert "Priority: <code>high</code>" in payload
    assert "Needs admin: <b>yes</b>" in payload
    assert "Không tạo ticket thật" in payload


def test_support_answers_topup_question_before_ticket_details(monkeypatch, tmp_path):
    db_path = tmp_path / "support_topup_answer.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "DB_STARTUP_BACKUP_PATHS", set())
    bot.init_db()

    classification = bot.classify_support_escalation("Làm sao để nạp tiền vào bot?")
    assert classification["matched"] is True
    assert classification["reason"] == "payment_how_to_topup"
    assert classification["should_create_ticket"] is False
    direct_reply = bot.support_reply_for_classification(classification)
    assert "/naptien" in direct_reply
    assert "10k, 20k, 50k, 100k, 200k hoặc 500k" in direct_reply

    class FakeMessage:
        def __init__(self):
            self.text = "Làm sao để nạp tiền vào bot?"
            self.sent = []

        async def reply_text(self, text, **kwargs):
            self.sent.append((str(text), kwargs))

    class FakeBot:
        async def send_message(self, **kwargs):
            raise AssertionError("simple top-up guidance must not alert admin")

    user = SimpleNamespace(id="support-topup-guide", username="topup_user", first_name="Topup")
    message = FakeMessage()
    bot.set_support_ticket_pending(user.id, "awaiting_message", category="general_support")
    handled = asyncio.run(bot.handle_support_ticket_pending_text(
        SimpleNamespace(effective_user=user, message=message),
        SimpleNamespace(bot=FakeBot()),
    ))

    assert handled is True
    payload = message.sent[0][0]
    assert payload.index("Cách nạp Xu TOAN AAS") < payload.index("Mã ticket")
    assert "/naptien" in payload
    assert bot.list_support_tickets(user_id=user.id)


def test_support_persona_topup_faq_does_not_create_ticket(monkeypatch):
    class FakeMessage:
        def __init__(self):
            self.text = "Tôi muốn nạp Xu, làm sao nạp?"
            self.sent = []

        async def reply_text(self, text, **kwargs):
            self.sent.append((str(text), kwargs))

    message = FakeMessage()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id="support-faq", username="faq_user", first_name="FAQ"),
        message=message,
    )
    context = SimpleNamespace(bot=SimpleNamespace())
    monkeypatch.setattr(
        bot,
        "create_or_append_support_ticket",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("FAQ must not create a ticket")),
    )

    handled = asyncio.run(bot.handle_support_persona_message(update, context))

    assert handled is True
    assert "/naptien" in message.sent[0][0]


def test_support_classifier_handles_explicit_public_support_keywords():
    technical = bot.classify_support_escalation("Bot đứng im và lỗi video")
    admin = bot.classify_support_escalation("Tôi muốn gặp admin")
    custom_bot = bot.classify_support_escalation("Tôi muốn kết nối bot riêng cho shop")
    payment = bot.classify_support_escalation("Tôi nạp tiền rồi chưa thấy Xu")

    assert technical["ticket_category"] == "video_error"
    assert technical["support_category"] == "technical_error"
    assert technical["needs_admin"] is True
    assert admin["ticket_category"] == "general_support"
    assert admin["support_category"] == "admin_contact"
    assert admin["should_alert_admin"] is True
    assert custom_bot["ticket_category"] == "custom_bot_lead"
    assert custom_bot["priority"] == "high"
    assert payment["support_category"] == "payment"


def test_support_pending_router_runs_after_product_pending_handlers():
    source = bot_source_text()
    handle_message_source = source_between(source, "async def handle_message", "@asynccontextmanager")
    support_position = handle_message_source.index("handle_support_pending_input")

    assert handle_message_source.index("handle_storyboard_pending_text") < support_position
    assert handle_message_source.index("handle_quick_image_flow_pending_text") < support_position
    assert handle_message_source.index("handle_public_video_prompt_pending_text") < support_position


def test_support_v3_my_tickets_reply_and_done(monkeypatch, tmp_path):
    db_path = tmp_path / "support_v3_reply.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "DB_STARTUP_BACKUP_PATHS", set())
    bot.init_db()
    user = SimpleNamespace(id="support-owner", username="owner", first_name="Owner")
    ticket = bot.create_support_ticket(user, "general_support", "Nội dung ban đầu")

    list_text, list_keyboard = bot.public_support_ticket_list_keyboard(user.id)
    assert "Ticket của tôi" in list_text
    list_callbacks = [button.callback_data for row in list_keyboard.inline_keyboard for button in row]
    assert f"ticket|pv|{ticket['id']}" in list_callbacks
    assert "support|ticket" in list_callbacks
    assert "support|start" in list_callbacks

    edits = []

    async def fake_edit(_query, text, reply_markup=None, **kwargs):
        edits.append({"text": str(text), "reply_markup": reply_markup})
        return None

    class FakeQuery:
        def __init__(self, data):
            self.data = data
            self.from_user = SimpleNamespace(id=user.id)
            self.message = SimpleNamespace()

        async def answer(self, *args, **kwargs):
            return None

    monkeypatch.setattr(bot, "safe_edit_or_send", fake_edit)
    asyncio.run(bot.handle_ticket_callback(
        SimpleNamespace(callback_query=FakeQuery(f"ticket|reply_user|{ticket['id']}")),
        SimpleNamespace(),
    ))
    state = bot.get_support_ticket_pending(user.id)
    assert state["step"] == "awaiting_ticket_reply"
    assert state["ticket_id"] == str(ticket["id"])

    class ReplyMessage:
        text = "Tôi bổ sung mã job VIDEO-123"

        def __init__(self):
            self.sent = []

        async def reply_text(self, text, **kwargs):
            self.sent.append((str(text), kwargs))

    class FakeBot:
        async def send_message(self, **kwargs):
            return None

    reply_message = ReplyMessage()
    assert asyncio.run(bot.handle_support_ticket_pending_text(
        SimpleNamespace(effective_user=user, message=reply_message),
        SimpleNamespace(bot=FakeBot()),
    )) is True
    assert "VIDEO-123" in bot.latest_support_ticket_message(ticket["id"], "user")
    assert bot.get_support_ticket_pending(user.id) is None

    asyncio.run(bot.handle_ticket_callback(
        SimpleNamespace(callback_query=FakeQuery(f"ticket|done|{ticket['id']}")),
        SimpleNamespace(),
    ))
    assert bot.get_support_ticket(ticket["id"], user.id)["status"] == "resolved"


def test_feedback_public_flow_creates_ticket_not_auto_refund(monkeypatch, tmp_path):
    db_path = tmp_path / "feedback_ticket.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "DB_STARTUP_BACKUP_PATHS", set())
    bot.init_db()

    class FakeMessage:
        text = "Video bị lỗi và đã trừ Xu nhưng không có kết quả"

        def __init__(self):
            self.sent = []

        async def reply_text(self, text, **kwargs):
            self.sent.append((text, kwargs))

    class FakeBot:
        def __init__(self):
            self.sent = []

        async def send_message(self, **kwargs):
            self.sent.append(kwargs)

    user = SimpleNamespace(id="feedback-ticket-user", username="feedback_user", first_name="Feedback")
    message = FakeMessage()
    update = SimpleNamespace(effective_user=user, message=message)
    context = SimpleNamespace(bot=FakeBot())
    bot.set_feedback_pending(user.id, "video_error")

    assert asyncio.run(bot.handle_feedback_pending_text(update, context)) is True
    tickets = bot.list_support_tickets(user_id=user.id)
    assert len(tickets) == 1
    assert tickets[0]["category"] == "video_error"
    assert tickets[0]["priority"] in {"high", "urgent"}
    assert "Mã ticket" in message.sent[0][0]
    assert "chưa tự hoàn Xu" in message.sent[0][0]


def test_premium_lead_pending_creates_high_priority_ticket(monkeypatch, tmp_path):
    db_path = tmp_path / "premium_lead.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "DB_STARTUP_BACKUP_PATHS", set())
    bot.init_db()

    class FakeMessage:
        text = "Tôi cần ảnh và video hằng ngày cho shop. Liên hệ qua email test@example.com"

        def __init__(self):
            self.sent = []

        async def reply_text(self, text, **kwargs):
            self.sent.append((text, kwargs))

    class FakeBot:
        async def send_message(self, **kwargs):
            return None

    user = SimpleNamespace(id="premium-lead-user", username="premium", first_name="Premium")
    message = FakeMessage()
    update = SimpleNamespace(effective_user=user, message=message)
    context = SimpleNamespace(bot=FakeBot())
    bot.set_support_ticket_pending(
        user.id,
        "lead_input",
        category="premium_lead",
        selected_option="Shop/Affiliate",
    )

    assert asyncio.run(bot.handle_support_ticket_pending_text(update, context)) is True
    ticket = bot.list_support_tickets(user_id=user.id)[0]
    assert ticket["category"] == "premium_lead"
    assert ticket["priority"] == "high"
    assert "Mã ticket" in message.sent[0][0]


def test_support_ticket_admin_reply_requires_preview_and_targets_ticket_owner(monkeypatch, tmp_path):
    db_path = tmp_path / "support_reply.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "DB_STARTUP_BACKUP_PATHS", set())
    bot.init_db()

    customer = SimpleNamespace(id="ticket-customer", username="customer", first_name="Customer")
    ticket = bot.create_support_ticket(customer, "video_error", "Video bị lỗi")
    admin_id = str(bot.ADMIN_ID)
    bot.set_support_ticket_pending(
        admin_id,
        "admin_reply_preview",
        ticket_id=ticket["id"],
        reply_text="TOAN AAS đang kiểm tra video của bạn.",
    )

    class FakeMessage:
        chat_id = admin_id

        async def reply_text(self, *args, **kwargs):
            return None

    class FakeQuery:
        data = f"ticket|send|{ticket['id']}"
        from_user = SimpleNamespace(id=admin_id)
        message = FakeMessage()

        async def answer(self, *args, **kwargs):
            return None

        async def edit_message_text(self, *args, **kwargs):
            return None

    class FakeBot:
        def __init__(self):
            self.sent = []

        async def send_message(self, **kwargs):
            self.sent.append(kwargs)
            return None

    fake_bot = FakeBot()
    update = SimpleNamespace(callback_query=FakeQuery())
    context = SimpleNamespace(bot=fake_bot)
    asyncio.run(bot.handle_ticket_callback(update, context))

    assert len(fake_bot.sent) == 1
    assert fake_bot.sent[0]["chat_id"] == customer.id
    refreshed = bot.get_support_ticket(ticket["id"])
    assert refreshed["status"] == "waiting_user"
    assert "TOAN AAS đang kiểm tra video" in bot.latest_admin_ticket_reply(ticket["id"])

    asyncio.run(bot.handle_ticket_callback(update, context))
    assert len(fake_bot.sent) == 1


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
    assert "trendg|trend_refresh" in trend_callbacks
    assert "trendg|cancel" not in trend_callbacks
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
    assert "🎬 Chốt video với nhạc" in trend_music_selected_buttons
    assert "🚫 Tạo video không nhạc" in trend_music_selected_buttons
    assert "🎞 Quay lại prompt video" in trend_music_selected_buttons
    trend_library_followup_buttons = [button.text for row in bot.selected_music_video_followup_keyboard("trend_guided").inline_keyboard for button in row]
    assert "🎬 Chốt video với nhạc" in trend_library_followup_buttons
    assert "🚫 Tạo video không nhạc" in trend_library_followup_buttons
    trend_ai_music_buttons = [button.text for row in bot.trend_guided_music_ai_selected_keyboard().inline_keyboard for button in row]
    assert "🎬 Chốt video với nhạc" in trend_ai_music_buttons
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
    assert 'CallbackQueryHandler(handle_self_scene_ai_callback, pattern=r"^selfscene\\|")' in source
    assert 'CallbackQueryHandler(handle_long_video_callback, pattern=r"^longvideo\\|")' in source
    assert "handle_developing_video_pending_text(update, context)" in source

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
    assert any("Tiết kiệm" in label for label in selected_image_buttons)
    assert any("Chuẩn + BH" in label and "300 Xu" in label for label in selected_image_buttons)
    assert any("Cao + BH" in label and "600 Xu" in label for label in selected_image_buttons)
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
    assert "🎬 Chốt video với nhạc" in music_selected_buttons
    assert "🚫 Tạo video không nhạc" in music_selected_buttons
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
    video_labels = {
        button.text
        for row in bot.main_video_keyboard("vi").inline_keyboard
        for button in row
    }
    assert "🧩 Kịch bản → Ảnh → Video" in video_labels
    assert "🎞 Ghép ảnh thành video" in video_labels
    assert "🎬 Video AI chân thật" in video_labels
    assert "🎥 Tự quay & đổi cảnh AI" in video_labels
    assert "🎬 Phim AI nhiều cảnh" in video_labels
    assert "🎞 Storyboard + Prompt" in video_labels
    assert "🔥 Video theo trend" in video_labels
    assert "🧠 Ý tưởng video" in video_labels
    assert "📢 Concept quảng cáo" not in video_labels

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
    assert any("Thêm bảo hành" in label and "300 Xu/ảnh" in label for label in warranty_buttons)

    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(5)], "duration": "fast", "effect": "none"}) == 20
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(5)], "duration": "fast", "effect": "fade"}) == 20
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(7)], "duration": "fast", "effect": "fade"}) == 30
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(10)], "duration": "standard", "effect": "zoom"}) == 60
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(5)], "duration": "slow", "effect": "zoom"}) == 40
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(10)], "duration": "slow", "effect": "pan"}) == 80
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(15)], "duration": "slow", "effect": "random"}) == 120
    assert bot.frame_video_price_for_state({"photos": [{"file_id": str(i)} for i in range(20)], "duration": "fast", "effect": "pan"}) == 60
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


def test_safe_public_video_activation_commands_registered_and_admin_only():
    source = bot_source_text()
    assert 'CommandHandler("video_public_status", cmd_video_public_status)' in source
    assert 'CommandHandler("video_gate_status", cmd_video_gate_status)' in source
    assert 'CommandHandler("video_public_open_safe", cmd_video_public_open_safe)' in source
    assert 'CommandHandler("video_beta_open", cmd_video_beta_open)' in source
    assert 'CommandHandler("video_beta_close", cmd_video_beta_close)' in source
    assert 'CommandHandler("video_beta_limits", cmd_video_beta_limits)' in source
    assert 'CommandHandler("video_open_all_current_tiers", cmd_video_open_all_current_tiers)' in source
    assert 'CommandHandler("video_open_high_tiers", cmd_video_open_high_tiers)' in source
    assert 'CommandHandler("video_close_high_tiers", cmd_video_close_high_tiers)' in source
    assert 'CommandHandler("video_smoke_tier_500", cmd_video_smoke_tier_500)' in source
    assert 'CommandHandler("video_smoke_tier_600", cmd_video_smoke_tier_600)' in source
    assert 'CommandHandler("video_smoke_tier_800", cmd_video_smoke_tier_800)' in source
    assert 'CommandHandler("video_cost_status", cmd_video_cost_status)' in source
    assert 'CommandHandler("system_public_status", cmd_system_public_status)' in source
    assert 'CommandHandler("tool_public_status", cmd_tool_public_status)' in source
    assert "async def cmd_video_public_status" in source
    assert "async def cmd_video_gate_status" in source
    assert "async def cmd_video_public_open_safe" in source
    assert "async def cmd_video_beta_open" in source
    assert "async def cmd_video_cost_status" in source
    assert "async def cmd_video_open_all_current_tiers" in source
    assert "async def cmd_video_open_high_tiers" in source
    assert "async def cmd_video_smoke_tier_600" in source
    assert source_between(source, "async def cmd_video_public_status", "async def cmd_video_gate_status").count("is_admin_user") >= 1
    assert source_between(source, "async def cmd_video_gate_status", "async def cmd_video_public_open_safe").count("is_admin_user") >= 1


def test_p0_video_command_registry_hotfix_commands_registered_and_documented():
    source = bot_source_text()
    registry = (Path(bot.__file__).resolve().parent / "docs" / "COMMAND_REGISTRY.md").read_text(encoding="utf-8")
    required = {
        "video_tier_matrix": "cmd_video_tier_matrix",
        "video_debug_tier_payload": "cmd_video_debug_tier_payload",
        "video_test_tier_duration": "cmd_video_test_tier_duration",
        "video_test_tier_200": "cmd_video_test_tier_200",
        "video_test_tier_300": "cmd_video_test_tier_300",
        "video_test_tier_400": "cmd_video_test_tier_400",
        "video_test_tier_500": "cmd_video_test_tier_500",
        "video_test_tier_600": "cmd_video_test_tier_600",
        "video_test_tier_800": "cmd_video_test_tier_800",
        "video_test_tier_1000": "cmd_video_test_tier_1000",
        "video_test_tier_1200": "cmd_video_test_tier_1200",
        "video_test_tier_1500": "cmd_video_test_tier_1500",
        "video_test_all_tiers": "cmd_video_test_all_tiers",
        "video_recent_jobs": "cmd_video_recent_jobs",
        "video_failed_jobs": "cmd_video_failed_jobs",
        "video_error_report": "cmd_video_error_report",
        "test_all_safe": "cmd_test_all_safe",
        "test_all_video": "cmd_test_all_video",
        "test_all_provider": "cmd_test_all_provider",
        "test_all_system": "cmd_test_all_system",
    }
    for command, handler in required.items():
        assert f'CommandHandler("{command}", {handler})' in source
        assert f"| `/{command}` | `{handler}` |" in registry
    assert '"future_1000": video_tier_public_flag("future_1000")' in source
    assert '"future_1200": video_tier_public_flag("future_1200")' in source
    assert '"future_1500": video_tier_public_flag("future_1500")' in source
    assert "PUBLIC_WITH_PROVIDER_GUARD" in source


def test_video_duration_debug_payload_is_safe_and_detects_missing_duration_field():
    payload = bot.video_duration_debug_payload("future_1000", 8)
    assert payload["tier"] == "future_1000"
    assert payload["requested_seconds"] == 8
    assert payload["provider_call"] == "NO"
    assert payload["xu_deducted"] == "NO"
    assert payload["duration_enforced"] is False
    assert payload["shopaikey_has_duration_field"] is False
    assert payload["key4u_has_duration_field"] is False
    lines = "\n".join(bot.video_duration_debug_lines("future_1000", 8))
    assert "DURATION_NOT_ENFORCED_IN_CURRENT_SUBMIT_PAYLOAD" in lines
    assert "Không bán cộng giây lẻ" in lines


def test_video_public_open_safe_blocks_when_veo_timeout_stale(monkeypatch):
    monkeypatch.setattr(bot, "VIDEO_AI_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_VIDEO_ENABLED", False)
    monkeypatch.setattr(bot, "set_system_setting", lambda *args, **kwargs: None)
    monkeypatch.setattr(bot, "record_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        bot,
        "video_ai_provider_smoke_gate",
        lambda: {
            "ready": False,
            "status": "TIMEOUT_STALE",
            "detail": "video smoke exceeded configured maximum job age",
            "model": "veo3.1-fast",
            "tested_at": "2026-06-16 00:00:00",
            "has_output": False,
            "blockers": ["Last video smoke: TIMEOUT_STALE", "Provider output/result_url and Telegram output_sent not confirmed"],
        },
    )
    monkeypatch.setattr(
        bot,
        "frame_video_public_gate",
        lambda: {
            "ready": False,
            "status": "FAIL",
            "frame": {
                "local_worker_connected": False,
                "ffmpeg_configured": False,
                "last_error": "worker_failed frame_video_render",
            },
            "blockers": ["Local Worker not connected", "/tool_test_frame_video status is FAIL"],
        },
    )
    monkeypatch.setattr(
        bot,
        "video_billing_public_gate",
        lambda: {"ready": True, "allowed_tiers": ["low", "basic", "common"], "blockers": []},
    )
    result = bot.video_public_open_safe_result("admin-test")
    assert "video_ai_from_prompt" in result["kept_off"]
    assert "video_ai_realistic" in result["kept_off"]
    assert any("TIMEOUT_STALE" in item for item in result["blockers"])
    assert bot.VIDEO_AI_PUBLIC_ENABLED is False
    assert bot.SHOPAIKEY_PUBLIC_VIDEO_ENABLED is False


def test_video_open_all_current_tiers_opens_200_to_1000(monkeypatch):
    settings = {}
    monkeypatch.setattr(bot, "VIDEO_PUBLIC_ALLOWED_TIERS", "low,basic,common")
    monkeypatch.setattr(bot, "VIDEO_PUBLIC_BETA_ENABLED", False)
    monkeypatch.setattr(bot, "set_system_setting", lambda key, value, note="", updated_by="": settings.__setitem__(key, value))
    monkeypatch.setattr(bot, "record_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(bot, "current_system_mode", lambda: {"maintenance_mode": False, "tool_freeze": False, "provider_freeze": False})
    monkeypatch.setattr(
        bot,
        "video_ai_provider_smoke_gate",
        lambda: {"ready": True, "status": "SUCCESS", "blockers": [], "has_output": True},
    )
    monkeypatch.setattr(
        bot,
        "video_billing_public_gate",
        lambda: {"ready": True, "allowed_tiers": ["low", "basic", "common", "advanced", "standard", "high", "future_1000"], "blockers": [], "cost_rows": []},
    )
    monkeypatch.setattr(bot, "video_tier_public_flag", lambda tier: bot.normalize_video_tier(tier) in {"low", "basic", "common", "advanced", "standard", "high", "future_1000"})
    monkeypatch.setattr(bot, "video_tier_base_public_flag", lambda tier: bot.normalize_video_tier(tier) in {"low", "basic", "common", "advanced", "standard", "high", "future_1000"})

    result = bot.video_open_all_current_tiers_result("admin-test")

    assert result["status"] == "OPENED"
    assert result["opened_tiers"] == ["low", "basic", "common", "advanced", "standard", "high", "future_1000"]
    assert "video_1000" not in result["kept_off"]
    assert "video_1500" in result["kept_off"]
    assert "key4u_public_video" in result["kept_off"]
    assert settings["video_public_allowed_tiers"] == "low,basic,common,advanced,standard,high,future_1000"


def test_video_beta_cost_status_and_public_tiers(monkeypatch):
    monkeypatch.setattr(bot, "get_system_setting", lambda key, default="": "")
    monkeypatch.setattr(bot, "VIDEO_PUBLIC_BETA_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_PUBLIC_ALLOWED_TIERS", "200,300,400,500,600,800,1000")
    monkeypatch.setattr(bot, "VIDEO_LOW_COST_XU", 200)
    monkeypatch.setattr(bot, "VIDEO_BASIC_COST_XU", 300)
    monkeypatch.setattr(bot, "VIDEO_COMMON_COST_XU", 400)
    monkeypatch.setattr(bot, "VIDEO_ADVANCED_COST_XU", 500)
    monkeypatch.setattr(bot, "VIDEO_STANDARD_COST_XU", 600)
    monkeypatch.setattr(bot, "VIDEO_HIGH_COST_XU", 800)
    monkeypatch.setattr(bot, "VIDEO_LOW_PROVIDER_COST_XU", 100)
    monkeypatch.setattr(bot, "VIDEO_BASIC_PROVIDER_COST_XU", 150)
    monkeypatch.setattr(bot, "VIDEO_COMMON_PROVIDER_COST_XU", 220)
    monkeypatch.setattr(bot, "VIDEO_ADVANCED_PROVIDER_COST_XU", 0)
    monkeypatch.setattr(bot, "VIDEO_STANDARD_PROVIDER_COST_XU", 0)
    monkeypatch.setattr(bot, "VIDEO_HIGH_PROVIDER_COST_XU", 0)
    monkeypatch.setattr(bot, "VIDEO_PREMIUM_PROVIDER_COST_XU", 0)
    monkeypatch.setattr(bot, "VIDEO_TIER_LOW_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_TIER_BASIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_TIER_COMMON_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_TIER_500_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_TIER_600_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_TIER_800_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_TIER_1000_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_TIER_STANDARD_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_TIER_HIGH_ENABLED", True)
    assert bot.video_tier_enabled_map()["low"] is True
    assert bot.video_tier_enabled_map()["basic"] is True
    assert bot.video_tier_enabled_map()["common"] is True
    assert bot.video_tier_enabled_map()["advanced"] is True
    assert bot.video_tier_enabled_map()["standard"] is True
    assert bot.video_tier_enabled_map()["high"] is True
    assert bot.video_tier_enabled_map()["future_1000"] is True
    assert bot.video_tier_enabled_map()["future_1200"] is True
    assert bot.video_tier_enabled_map()["future_1500"] is True
    assert bot.check_video_margin("low")["status"] == "MARKETING_LOSS_ON"
    assert bot.check_video_margin("common")["status"] == "WARN_MARGIN"
    assert bot.check_video_margin("advanced")["status"] in {"COST_REVIEW_ONLY", "PASS", "WARN_MARGIN"}
    cost_text = bot.video_cost_status_text()
    assert "VIDEO COST STATUS" in cost_text
    assert "500/600/800/1000/1200/1500" in cost_text
    assert "cost is report-only" in cost_text
    system_text = bot.system_public_status_text()
    assert "TOAN AAS PUBLIC STATUS" in system_text
    assert "Video 500" in system_text
    assert "Video 800" in system_text
    assert "Long video" in system_text


def test_video_public_status_and_gate_text_do_not_expose_secrets(monkeypatch):
    status_text = bot.video_public_status_text()
    gate_text = bot.video_gate_status_text()
    assert "VIDEO PUBLIC STATUS" in status_text
    assert "VIDEO GATE STATUS" in gate_text
    assert "Bearer " not in status_text
    assert "sk-" not in status_text
    assert "xoxb-" not in status_text


def test_video_output_confirmed_marks_smoke_success(monkeypatch):
    settings = {}
    tool_results = []
    snapshots = []
    debug_events = []

    monkeypatch.setattr(bot, "set_system_setting", lambda key, value, note="", updated_by="": settings.__setitem__(key, value))
    monkeypatch.setattr(bot, "save_tool_test_result", lambda tool, status, detail="", updated_by="": tool_results.append((tool, status, detail)))
    monkeypatch.setattr(bot, "save_shopaikey_component_snapshot", lambda component, result, detail, updated_by="": snapshots.append((component, result, detail)))
    monkeypatch.setattr(bot, "record_api_debug", lambda provider, action, status, http_status, detail="": debug_events.append((provider, action, status, http_status, detail)))

    bot.mark_shopaikey_video_output_confirmed("task_123", "veo3.1-fast", "admin", "pytest")

    assert ("shopaikey_video", "SUCCESS") in [(tool, status) for tool, status, _ in tool_results]
    assert ("shopaikey_video_job", "SUCCESS") in [(tool, status) for tool, status, _ in tool_results]
    assert settings["shopaikey_video_last_output"] == "confirmed"
    assert settings["shopaikey_video_last_output_sent"] == "true"
    assert snapshots and snapshots[0][1]["status"] == "SUCCESS"
    assert debug_events and debug_events[0][2] == "SUCCESS"


def test_video_ai_provider_gate_treats_confirmed_output_as_success(monkeypatch):
    monkeypatch.setattr(bot, "shopaikey_video_status_snapshot", lambda: {
        "status": "IN_PROGRESS",
        "detail": "task_id=abc; output_sent=yes; provider_status=SUCCESS",
        "model": "veo3.1-fast",
        "tested_at": "2026-06-16 00:00:00",
    })
    monkeypatch.setattr(bot, "provider_freeze_runtime_on", lambda name: False)
    monkeypatch.setattr(bot, "SHOPAIKEY_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "configured")
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_URL", "https://api.shopaikey.com/v1/video/generations")
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_MODEL", "veo3.1-fast")

    gate = bot.video_ai_provider_smoke_gate()

    assert gate["ready"] is True
    assert gate["status"] == "SUCCESS"
    assert gate["has_output"] is True
    assert gate["blockers"] == []


def test_video_beta_open_300_400_does_not_enable_200_without_override(monkeypatch):
    settings = {}
    monkeypatch.setattr(bot, "set_system_setting", lambda key, value, note="", updated_by="": settings.__setitem__(key, value))
    monkeypatch.setattr(bot, "record_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(bot, "current_system_mode", lambda: {"maintenance_mode": False, "tool_freeze": False, "provider_freeze": False})
    monkeypatch.setattr(bot, "video_ai_provider_smoke_gate", lambda: {"ready": True, "status": "SUCCESS", "has_output": True, "blockers": []})
    monkeypatch.setattr(bot, "get_system_setting", lambda key, default="": settings.get(key, default))
    monkeypatch.setattr(bot, "VIDEO_PUBLIC_BETA_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_PUBLIC_ALLOWED_TIERS", "low,basic,common")
    monkeypatch.setattr(bot, "VIDEO_LOW_COST_XU", 200)
    monkeypatch.setattr(bot, "VIDEO_BASIC_COST_XU", 300)
    monkeypatch.setattr(bot, "VIDEO_COMMON_COST_XU", 400)
    monkeypatch.setattr(bot, "VIDEO_LOW_PROVIDER_COST_XU", 600)
    monkeypatch.setattr(bot, "VIDEO_BASIC_PROVIDER_COST_XU", 150)
    monkeypatch.setattr(bot, "VIDEO_COMMON_PROVIDER_COST_XU", 220)

    result = bot.video_beta_open_result("admin", ["tiers=300,400"])

    assert result["status"] == "OPENED"
    assert result["opened_tiers"] == ["basic", "common"]
    assert "low" not in result["opened_tiers"]
    assert settings["video_public_allowed_tiers"] == "basic,common"
    assert settings["video_beta_tier_200_enabled"] == "false"


def test_video_beta_open_200_is_public_starter_when_requested(monkeypatch):
    settings = {}
    monkeypatch.setattr(bot, "set_system_setting", lambda key, value, note="", updated_by="": settings.__setitem__(key, value))
    monkeypatch.setattr(bot, "record_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(bot, "current_system_mode", lambda: {"maintenance_mode": False, "tool_freeze": False, "provider_freeze": False})
    monkeypatch.setattr(bot, "video_ai_provider_smoke_gate", lambda: {"ready": True, "status": "SUCCESS", "has_output": True, "blockers": []})
    monkeypatch.setattr(bot, "get_system_setting", lambda key, default="": settings.get(key, default))
    monkeypatch.setattr(bot, "VIDEO_PUBLIC_ALLOWED_TIERS", "low,basic,common")
    monkeypatch.setattr(bot, "VIDEO_LOW_COST_XU", 200)
    monkeypatch.setattr(bot, "VIDEO_BASIC_COST_XU", 300)
    monkeypatch.setattr(bot, "VIDEO_COMMON_COST_XU", 400)
    monkeypatch.setattr(bot, "VIDEO_LOW_PROVIDER_COST_XU", 600)
    monkeypatch.setattr(bot, "VIDEO_BASIC_PROVIDER_COST_XU", 150)
    monkeypatch.setattr(bot, "VIDEO_COMMON_PROVIDER_COST_XU", 220)

    starter = bot.video_beta_open_result("admin", ["tiers=200"])
    assert starter["status"] == "OPENED"
    assert starter["opened_tiers"] == ["low"]
    assert settings["video_beta_tier_200_enabled"] == "true"

    opened = bot.video_beta_open_result("admin", ["tiers=200,300,400"])
    assert opened["status"] == "OPENED"
    assert opened["opened_tiers"] == ["low", "basic", "common"]
    assert settings["video_beta_tier_200_enabled"] == "true"


def test_video_beta_open_response_and_status_show_200_marketing_loss(monkeypatch):
    settings = {
        "video_public_beta_enabled": "true",
        "video_ai_public_enabled": "true",
        "video_ai_master_enabled": "true",
        "shopaikey_public_video_enabled": "true",
        "video_public_allowed_tiers": "low,basic,common",
        "video_beta_200_marketing_loss_enabled": "true",
    }
    monkeypatch.setattr(bot, "get_system_setting", lambda key, default="": settings.get(key, default))
    monkeypatch.setattr(bot, "current_system_mode", lambda: {"maintenance_mode": False, "payment_freeze": False, "tool_freeze": False, "provider_freeze": False})
    monkeypatch.setattr(bot, "provider_freeze_runtime_on", lambda provider="": False)
    monkeypatch.setattr(bot, "shopaikey_video_status_snapshot", lambda: {"status": "SUCCESS", "detail": "output_sent=yes", "model": "veo3.1-fast", "tested_at": "now"})
    monkeypatch.setattr(bot, "video_gate_tool_status", lambda _tool: "PASS")
    monkeypatch.setattr(bot, "local_worker_status_payload", lambda: {"connected": True})
    monkeypatch.setattr(bot, "frame_video_status_payload", lambda: {"local_worker_connected": True, "ffmpeg_configured": True, "last_error": ""})
    monkeypatch.setattr(bot, "SHOPAIKEY_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "test-key")
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_URL", "https://provider.test/video")
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_MODEL", "veo3.1-fast")
    monkeypatch.setattr(bot, "VIDEO_LOW_PROVIDER_COST_XU", 600)
    monkeypatch.setattr(bot, "VIDEO_LOW_COST_XU", 200)
    monkeypatch.setattr(bot, "VIDEO_BASIC_PROVIDER_COST_XU", 150)
    monkeypatch.setattr(bot, "VIDEO_COMMON_PROVIDER_COST_XU", 200)
    monkeypatch.setattr(bot, "VIDEO_PUBLIC_BLOCK_TIERS", "low,standard,high,premium")

    row = bot.check_video_margin("low")
    assert row["status"] == "MARKETING_LOSS_ON"
    assert row["can_open"] is True
    assert bot.video_public_tier_enabled("low") is True

    text = bot.video_public_status_text()
    assert "Video Beta 200" in text
    assert "PUBLIC_MARKETING_LOSS" in text
    assert "MARKETING_LOSS_ON" in text

    response = bot.video_beta_open_text({"status": "OPENED", "opened_tiers": ["low", "basic", "common"], "blockers": []})
    assert "200 Xu" in response
    assert "MARKETING_LOSS" in response
    assert "giới hạn" in response


def test_video_beta_200_starter_stays_allowed_with_legacy_300_400_setting(monkeypatch):
    settings = {
        "video_public_beta_enabled": "true",
        "video_ai_public_enabled": "true",
        "video_ai_master_enabled": "true",
        "shopaikey_public_video_enabled": "true",
        "video_public_allowed_tiers": "basic,common",
    }
    monkeypatch.setattr(bot, "get_system_setting", lambda key, default="": settings.get(key, default))
    monkeypatch.setattr(bot, "current_system_mode", lambda: {"maintenance_mode": False, "payment_freeze": False, "tool_freeze": False, "provider_freeze": False})
    monkeypatch.setattr(bot, "provider_freeze_runtime_on", lambda provider="": False)
    monkeypatch.setattr(bot, "shopaikey_video_status_snapshot", lambda: {"status": "SUCCESS", "detail": "output_sent=yes", "model": "veo3.1-fast", "tested_at": "now"})
    monkeypatch.setattr(bot, "video_gate_tool_status", lambda _tool: "PASS")
    monkeypatch.setattr(bot, "local_worker_status_payload", lambda: {"connected": True})
    monkeypatch.setattr(bot, "frame_video_status_payload", lambda: {"local_worker_connected": True, "ffmpeg_configured": True, "last_error": ""})
    monkeypatch.setattr(bot, "SHOPAIKEY_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "test-key")
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_URL", "https://provider.test/video")
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_MODEL", "veo3.1-fast")
    monkeypatch.setattr(bot, "VIDEO_LOW_PROVIDER_COST_XU", 9999)
    monkeypatch.setattr(bot, "VIDEO_LOW_COST_XU", 200)

    assert bot.video_public_allowed_tiers()[0] == "low"
    assert bot.video_public_tier_enabled("low") is True
    status = bot.get_public_video_tier_ui_status("low")
    assert status["enabled"] is True
    assert status["public_status"] == "PUBLIC_MARKETING_LOSS"


def test_video_beta_open_allow_loss_aliases_parse():
    for args in (
        ["tiers=200,300,400", "allow_loss_200=true"],
        ["tiers=200,300,400", "allow_loss_200=1"],
        ["tiers=200,300,400", "allow_loss=true"],
        ["tiers=200,300,400", "allow_loss"],
        ["tiers=200,300,400", "marketing_loss_200=true"],
        ["tiers=200,300,400", "loss_200=true"],
    ):
        parsed = bot.video_beta_open_parse_args(args)
        assert parsed["allow_loss_200"] is True
    assert bot.video_beta_open_parse_args(["tiers=200", "allow_loss=false"])["allow_loss_200"] is False


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


def test_operations_v1a_tax_prep_and_accounting_exports(monkeypatch):
    source = bot_source_text()
    assert 'CommandHandler("tax_status", cmd_tax_status)' in source
    assert 'CommandHandler("tax_report", cmd_tax_report)' in source
    assert 'CommandHandler("tax_export", cmd_tax_export)' in source
    assert 'CommandHandler("tax_config", cmd_tax_config)' in source
    assert "DROP TABLE" not in source_between(source, "def migrate_operations_v1a_schema", "def init_db").upper()
    assert set(bot.REVENUE_CATEGORIES) >= {
        "payos_topup_xu",
        "manual_topup_xu",
        "combo_package_sale",
        "storage_addon",
        "image_service",
        "video_service",
        "refund_reversal",
    }
    assert set(bot.OPERATIONS_EXPENSE_CATEGORIES) >= {
        "provider_ai_api",
        "shopaikey",
        "railway",
        "domain",
        "bank_fee",
        "accounting_service",
        "legal_service",
    }
    finance_labels = [button.text for row in bot.finance_admin_keyboard().inline_keyboard for button in row]
    assert "🟢 Miễn/ưu đãi thuế phí" in finance_labels
    assert "🧾 Báo cáo kế toán" in finance_labels
    tax_callbacks = [
        button.callback_data
        for row in bot.tax_accounting_menu_keyboard().inline_keyboard
        for button in row
    ]
    assert {"menu|tax_estimate", "menu|tax_export", "menu|tax_checklist", "menu|tax_config", "menu|finance_compliance"}.issubset(set(tax_callbacks))
    assert "Thu chi / Báo cáo nội bộ" in bot.tax_accounting_menu_text()
    assert "không tự nộp thuế" in bot.tax_accounting_menu_text()
    assert "CREATE TABLE IF NOT EXISTS finance_compliance_notes" in source

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    try:
        bot.init_db()
        profile = bot.get_tax_profile("tax-admin")
        assert profile["tax_method"] == "manual_config"
        assert profile["vat_rate_percent"] == 0
        assert profile["pit_rate_percent"] == 0
        assert profile["license_fee_enabled"] is False

        updated = bot.update_tax_profile("tax-admin", {
            "vat_rate_percent": 3.0,
            "pit_rate_percent": 1.5,
            "license_fee_enabled": 1,
            "license_fee_amount_vnd": 1000000,
        })
        assert updated["vat_rate_percent"] == 3.0
        assert updated["pit_rate_percent"] == 1.5
        assert updated["license_fee_enabled"] is True

        estimate = bot.calculate_tax_estimate(10000000, updated)
        assert estimate["vat_estimate"] == 300000
        assert estimate["pit_estimate"] == 150000
        assert estimate["total_tax_estimate"] == 1450000

        compliance_id = bot.save_finance_compliance_note(
            "license_fee_exempt",
            "Miễn lệ phí môn bài",
            "Đang áp dụng theo ghi chú quản trị nội bộ",
            "tax-admin",
            effective_from="2026-01-01",
            effective_to="2026-12-31",
            source_note="Chờ kế toán đối chiếu căn cứ",
        )
        assert compliance_id > 0
        compliance = bot.finance_compliance_notes()
        assert compliance[0]["status_type"] == "license_fee_exempt"
        assert compliance[0]["confirmed_by_admin"] == "tax-admin"
        compliance_text = bot.finance_compliance_status_text()
        assert "Miễn lệ phí môn bài" in compliance_text
        assert "Chờ kế toán đối chiếu căn cứ" in compliance_text
        bot.init_db()
        assert bot.finance_compliance_notes()[0]["id"] == compliance_id

        start_at, end_at, label, _ = bot.finance_period_bounds("2026-06", "month")
        files = dict(bot.tax_accounting_export_files(start_at, end_at, label, "tax-admin"))
        assert set(files) == {
            "revenue_report_2026_06.csv",
            "expense_report_2026_06.csv",
            "profit_loss_summary_2026_06.csv",
            "xu_ledger_2026_06.csv",
            "refund_report_2026_06.csv",
            "compliance_notes_2026_06.csv",
        }
        assert "No data" in files["revenue_report_2026_06.csv"]
        assert "No data" in files["expense_report_2026_06.csv"]
        assert "date,user_id,source,category" in files["revenue_report_2026_06.csv"]
        assert "internal_finance_report" in files["profit_loss_summary_2026_06.csv"]
        assert "không tự nộp thuế" in files["profit_loss_summary_2026_06.csv"]
        assert "license_fee_exempt" in files["compliance_notes_2026_06.csv"]

        conn = bot.db_connect()
        try:
            conn.execute(
                """INSERT INTO finance_revenue_events
                (created_at,user_id,source_type,source_id,amount_vnd,xu_credited,payment_method,status,note)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                ("2026-06-10 10:00:00", "u-tax", "payos_topup", "tax-order-1", 50000, 500, "payos", "success", "paid"),
            )
            conn.commit()
        finally:
            conn.close()
        revenue_csv = bot.tax_accounting_csv("revenue", start_at, end_at, label, "tax-admin")
        assert "payos_topup_xu" in revenue_csv
        assert "tax-order-1" in revenue_csv
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_operations_v1a_internal_archive_schema_flow_and_routing(monkeypatch):
    source = bot_source_text()
    init_source = source_between(source, "def init_db():", "def now_text():")
    assert "CREATE TABLE IF NOT EXISTS internal_documents" in init_source
    assert "DROP TABLE" not in init_source.upper()
    assert 'CommandHandler("internal_docs", cmd_internal_docs)' in source
    assert 'CommandHandler("search_internal_doc", cmd_search_internal_doc)' in source
    assert 'CallbackQueryHandler(handle_internal_archive_callback, pattern=r"^archive\\|")' in source

    memory_labels = [button.text for row in bot.main_memory_keyboard("vi").inline_keyboard for button in row]
    assert "🏢 Hồ sơ nội bộ" not in memory_labels
    monkeypatch.setattr(bot, "ADMIN_IDS", {"archive-admin"})
    admin_memory_labels = [button.text for row in bot.main_memory_keyboard("vi", "archive-admin").inline_keyboard for button in row]
    assert "🏢 Hồ sơ nội bộ" in admin_memory_labels
    archive_callbacks = [
        button.callback_data
        for row in bot.internal_archive_menu_keyboard().inline_keyboard
        for button in row
    ]
    assert "archive|dept|finance_accounting" in archive_callbacks
    assert "archive|dept|tax_invoice" in archive_callbacks
    assert "archive|search" in archive_callbacks
    assert "menu|main_memory" in archive_callbacks
    assert all(len(row) <= 2 for row in bot.internal_archive_menu_keyboard().inline_keyboard)

    photo_source = source_between(source, "async def handle_photo", "async def handle_document_cache_only")
    document_source = source_between(source, "async def handle_document_cache_only", "async def handle_media")
    message_source = source_between(source, "async def handle_message", "TELEGRAM_STARTUP_ERROR =")
    assert photo_source.index("handle_internal_archive_pending_upload") < photo_source.index("handle_doc_tool_pending_upload")
    assert document_source.index("handle_internal_archive_pending_upload") < document_source.index("handle_doc_tool_pending_upload")
    assert message_source.index("handle_internal_archive_pending_text") < message_source.index("handle_doc_tool_pending_text")
    assert "Hồ sơ nội bộ chỉ dành cho admin/owner" in source_between(
        source,
        "async def handle_internal_archive_callback",
        "async def handle_internal_archive_pending_upload",
    )
    customer_dashboard = bot.internal_archive_department_text("customers")
    assert "Dùng để lưu thông tin khách hàng" in customer_dashboard
    assert "Hồ sơ khách hàng" in customer_dashboard
    assert "Case hoàn Xu / refund" in customer_dashboard
    assert "customer_profile" not in customer_dashboard
    provider_dashboard = bot.internal_archive_department_text("provider_api")
    assert "Tài liệu provider" in provider_dashboard
    assert "Không lưu API key/token thật" in provider_dashboard
    department_callbacks = [
        button.callback_data
        for row in bot.internal_archive_department_keyboard().inline_keyboard
        for button in row
    ]
    assert department_callbacks == [
        "archive|quick", "archive|recent",
        "archive|types", "archive|search_dept",
        "archive|help", "archive|root",
        "menu|main",
    ]
    assert all(len(row) <= 2 for row in bot.internal_archive_department_keyboard().inline_keyboard)
    type_labels = [
        button.text
        for row in bot.internal_archive_type_keyboard("customers").inline_keyboard
        for button in row
    ]
    assert "Hồ sơ khách hàng" in type_labels
    assert "Lead B2B / khách tiềm năng" in type_labels
    assert "customer_profile" not in type_labels
    assert bot.document_type_label("customer_request") == "Yêu cầu khách gửi"
    assert bot.document_type_label("unknown_legacy_type") == "Hồ sơ khác"
    assert "KH_TenKhach_NoiDung_YYYYMMDD" in bot.internal_archive_help_text("customers")

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    try:
        bot.init_db()
        state = {
            "department": "tax_invoice",
            "title": "Thuế tháng 6",
            "document_type": "tax_prep_file",
            "file_info": {
                "file_id": "telegram-file-id",
                "file_name": "tax-june.csv",
                "mime_type": "text/csv",
                "size_bytes": 2048,
            },
            "tags": "tax,2026-06",
            "description": "File chuẩn bị cho kế toán",
            "retention_policy": "10_years",
            "confidentiality_level": "internal",
        }
        document_id = bot.save_internal_document("archive-admin", state)
        assert document_id > 0
        rows = bot.search_internal_documents("archive-admin", "2026-06")
        assert len(rows) == 1
        assert rows[0]["file_name"] == "tax-june.csv"
        assert rows[0]["file_id"] == "telegram-file-id"
        preview = bot.internal_archive_preview_text(state)
        assert "File chuẩn bị thuế" in preview
        assert "tax_prep_file" not in preview
        assert "10 năm" in preview
        result_text = bot.internal_archive_search_results_text(rows, "2026-06")
        assert "File chuẩn bị thuế" in result_text
        assert "tax_prep_file" not in result_text
        recent_rows = bot.recent_internal_documents("archive-admin", "tax_invoice")
        assert len(recent_rows) == 1
        assert "File chuẩn bị thuế" in bot.internal_archive_recent_text(recent_rows, "tax_invoice")
        assert bot.recent_internal_documents("archive-admin", "customers") == []
        assert "Chưa có hồ sơ nào trong nhóm này" in bot.internal_archive_recent_text([], "customers")

        customer_state = dict(state)
        customer_state.update({
            "department": "customers",
            "title": "Khách tháng 6",
            "document_type": "customer_request",
            "file_info": {
                "file_id": "telegram-file-id-2",
                "file_name": "customer-june.txt",
                "mime_type": "text/plain",
                "size_bytes": 1024,
            },
            "tags": "customer,2026-06",
        })
        bot.save_internal_document("archive-admin", customer_state)
        scoped_rows = bot.search_internal_documents("archive-admin", "2026-06", department="tax_invoice")
        assert len(scoped_rows) == 1
        assert scoped_rows[0]["department"] == "tax_invoice"
        assert "Khách tháng 6" not in bot.internal_archive_search_results_text(scoped_rows, "2026-06", "tax_invoice")
        assert bot.internal_archive_storage_used_bytes("archive-admin") == 3072
        item = bot.get_internal_document("archive-admin", document_id)
        assert item["department"] == "tax_invoice"
        assert item["retention_policy"] == "10_years"
        assert "tax_prep_file" not in bot.internal_archive_document_text(item)
        assert "File chuẩn bị thuế" in bot.internal_archive_document_text(item)
        bot.init_db()
        assert bot.get_internal_document("archive-admin", document_id)["title"] == "Thuế tháng 6"
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_internal_archive_department_callbacks_keep_department_state(monkeypatch):
    captured = []
    user_id = 778899

    class FakeQuery:
        def __init__(self, data):
            self.data = data
            self.from_user = SimpleNamespace(id=user_id)
            self.message = SimpleNamespace()

        async def answer(self, *args, **kwargs):
            return None

    async def fake_edit(_query, text, **kwargs):
        captured.append((text, kwargs.get("reply_markup")))

    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "safe_edit_query_message", fake_edit)
    bot.clear_internal_archive_pending(user_id)
    context = SimpleNamespace()

    asyncio.run(bot.handle_internal_archive_callback(
        SimpleNamespace(callback_query=FakeQuery("archive|dept|customers")),
        context,
    ))
    state = bot.get_internal_archive_pending(user_id)
    assert state["step"] == "department_dashboard"
    assert state["department"] == "customers"
    assert "Hồ sơ khách hàng" in captured[-1][0]

    asyncio.run(bot.handle_internal_archive_callback(
        SimpleNamespace(callback_query=FakeQuery("archive|types")),
        context,
    ))
    assert bot.get_internal_archive_pending(user_id)["step"] == "choosing_type"

    asyncio.run(bot.handle_internal_archive_callback(
        SimpleNamespace(callback_query=FakeQuery("archive|type|refund_case")),
        context,
    ))
    state = bot.get_internal_archive_pending(user_id)
    assert state["step"] == "awaiting_file"
    assert state["department"] == "customers"
    assert state["document_type"] == "refund_case"
    assert "Case hoàn Xu / refund" in captured[-1][0]

    asyncio.run(bot.handle_internal_archive_callback(
        SimpleNamespace(callback_query=FakeQuery("archive|back_department")),
        context,
    ))
    state = bot.get_internal_archive_pending(user_id)
    assert state["step"] == "department_dashboard"
    assert state["department"] == "customers"

    asyncio.run(bot.handle_internal_archive_callback(
        SimpleNamespace(callback_query=FakeQuery("archive|quick")),
        context,
    ))
    state = bot.get_internal_archive_pending(user_id)
    assert state["step"] == "awaiting_file"
    assert state["document_type"] == "general"
    bot.clear_internal_archive_pending(user_id)


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


def test_video_upload_ideas_selfscene_longvideo_and_music_ux_v5(monkeypatch):
    source = bot_source_text()

    monkeypatch.setattr(bot, "is_admin_user", lambda user_id: str(user_id) == "1")
    public_upload_buttons = [
        button.text
        for row in bot.video_upload_received_keyboard("2", "vi").inline_keyboard
        for button in row
    ]
    admin_upload_buttons = [
        button.text
        for row in bot.video_upload_received_keyboard("1", "vi").inline_keyboard
        for button in row
    ]
    upload_text = bot.video_upload_received_text("vi")
    assert "TOAN AAS đã nhận video của bạn" in upload_text
    assert "/add_music" not in upload_text
    assert "/video_enhance" not in upload_text
    assert "🎞 Video mẫu → Video AI" in public_upload_buttons
    assert "🎥 Tự quay & đổi cảnh AI" in public_upload_buttons
    assert "🎵 Thêm nhạc / voice" in public_upload_buttons
    assert "🧠 Tạo ý tưởng video" in public_upload_buttons
    assert "🎥 Prompt / chuyển động" in public_upload_buttons
    assert "✨ Nâng cấp video" in public_upload_buttons
    assert "💾 Lưu video tham khảo" in public_upload_buttons
    assert "🔐 Công cụ admin" not in public_upload_buttons
    assert "🔐 Công cụ admin" in admin_upload_buttons
    assert 'CallbackQueryHandler(handle_video_upload_callback, pattern=r"^video_upload\\|")' in source
    assert 'CallbackQueryHandler(handle_video_reference_callback, pattern=r"^videoref\\|")' in source
    assert 'CallbackQueryHandler(handle_video_dubbing_callback, pattern=r"^videodub\\|")' in source

    selfscene_start = bot.self_scene_start_text("vi")
    selfscene_direction_callbacks = [
        button.callback_data
        for row in bot.self_scene_input_keyboard("vi").inline_keyboard
        for button in row
    ]
    assert "Bạn muốn đổi video này theo hướng nào" in selfscene_start
    assert "selfscene|direction_choice|1" in selfscene_direction_callbacks
    assert "selfscene|direction_choice|2" in selfscene_direction_callbacks
    assert "selfscene|direction_choice|3" in selfscene_direction_callbacks
    assert "selfscene|direction_refresh" in selfscene_direction_callbacks
    assert "selfscene|direction_custom" in selfscene_direction_callbacks
    assert "Trong video này cần giữ ổn định đối tượng nào" in bot.self_scene_object_text({"direction": "context"}, "vi")
    motion_buttons = [
        button.text
        for row in bot.self_scene_style_keyboard("vi").inline_keyboard
        for button in row
    ]
    music_buttons = [
        button.text
        for row in bot.self_scene_music_keyboard("vi").inline_keyboard
        for button in row
    ]
    assert {"1️⃣ Chọn chuyển động 1", "2️⃣ Chọn chuyển động 2", "3️⃣ Chọn chuyển động 3", "🔄 Đổi gợi ý khác"}.issubset(set(motion_buttons))
    assert {"🎛 Tùy chọn hoàn thiện video", "✅ Tiếp tục chọn gói"}.issubset(set(music_buttons))
    legacy_music_voice = "Chọn nhạc" + "/voice"
    assert not any(legacy_music_voice in label for label in music_buttons)
    selfscene_plan = bot.self_scene_plan_text(
        {
            "direction": "ad",
            "input_type": "product",
            "selected_topic": "máy xay mini",
            "selected_context": "nhà bếp hiện đại",
            "selected_motion": "orbit",
            "selected_music": "tech",
        },
        "vi",
    )
    for expected in [
        "Video đã nhận",
        "Đối tượng cần giữ",
        "Bối cảnh mới",
        "Chuyển động",
        "Nhạc/âm thanh",
        "Prompt video chính",
        "Prompt ảnh/keyframe",
        "Lưu ý giữ nhận diện",
        "chưa trừ Xu",
    ]:
        assert expected in selfscene_plan
    assert "Video AI chân thật hiện đang được bảo trì hoặc chưa mở công khai" in bot.self_scene_guard_text("video_guard", "vi")

    video_menu_buttons = [
        button.text
        for row in bot.main_video_keyboard("vi").inline_keyboard
        for button in row
    ]
    idea_buttons = [
        button.text
        for row in bot.video_idea_menu_keyboard("vi").inline_keyboard
        for button in row
    ]
    idea_callbacks = [
        button.callback_data
        for row in bot.video_idea_menu_keyboard("vi").inline_keyboard
        for button in row
    ]
    assert "🧠 Ý tưởng video" in video_menu_buttons
    assert "📢 Concept quảng cáo" not in video_menu_buttons
    assert "📢 Ý tưởng quảng cáo" in idea_buttons
    assert "🔥 Ý tưởng theo xu hướng" not in idea_buttons
    assert "🎬 Ý tưởng điện ảnh / kể chuyện" in idea_buttons
    assert "videoidea|kind|ad" in idea_callbacks
    assert "videoidea|kind|trend" not in idea_callbacks
    assert 'CallbackQueryHandler(handle_video_idea_callback, pattern=r"^videoidea\\|")' in source
    assert 'CallbackQueryHandler(handle_prompt_video_callback, pattern=r"^promptvideo\\|")' in source
    assert 'CallbackQueryHandler(handle_image_video_callback, pattern=r"^imagevideo\\|")' in source
    idea_result = bot.video_idea_result_text(
        {"selected_topic": "app AI", "goal": "bán hàng", "context": "TikTok/Reels"},
        1,
        "vi",
    )
    for expected in [
        "Hook 3 giây đầu",
        "Kịch bản voice",
        "Storyboard 6 cảnh",
        "Danh sách cảnh quay",
        "Prompt ảnh từng cảnh",
        "Prompt video từng cảnh",
        "Gợi ý chuyển động",
        "Gợi ý nhạc/SFX",
        "Caption",
        "CTA",
        "Hashtag",
        "chưa trừ Xu",
    ]:
        assert expected in idea_result
    ad_product_buttons = [button.callback_data for row in bot.video_idea_product_type_keyboard("vi").inline_keyboard for button in row]
    assert {"videoidea|product_type|physical", "videoidea|product_type|service", "videoidea|product_type|affiliate"}.issubset(set(ad_product_buttons))
    assert "Nhà bếp hiện đại" in "\n".join(bot.video_idea_context_options("physical", "vi"))
    idea_followup = bot.video_idea_followup_text("video_prompts", {"selected_topic": "app AI", "context": "TikTok/Reels"}, "vi")
    assert "Prompt video từng cảnh" in idea_followup
    assert "Match cut before/after" in idea_followup or "before/after" in idea_followup

    structure_callbacks = [
        button.callback_data
        for row in bot.long_video_structure_keyboard("10 phút", "vi").inline_keyboard
        for button in row
    ]
    assert "longvideo|structure|1" in structure_callbacks
    assert "longvideo|structure|2" in structure_callbacks
    assert "longvideo|structure|3" in structure_callbacks
    long_plan = bot.long_video_plan_text(
        {
            "selected_topic": "affiliate AI cho người mới",
            "duration": "10 phút",
            "selected_style": "viral",
            "structure": "10 đoạn x 60 giây",
        },
        "vi",
    )
    for expected in [
        "Outline tổng thể",
        "Danh sách chương/phân đoạn",
        "Hook từng chương",
        "Kịch bản từng đoạn",
        "Cảnh cần có",
        "Prompt ảnh từng cảnh",
        "Prompt video từng cảnh",
        "Phong cách voice gợi ý",
        "Nhạc/SFX gợi ý",
        "CTA/caption",
    ]:
        assert expected in long_plan
    long_storyboard = bot.long_video_followup_text("storyboard", {
        "selected_topic": "affiliate AI cho người mới",
        "duration": "10 phút",
        "selected_style": "viral",
        "structure": "10 đoạn x 60 giây",
    }, "vi")
    assert "Storyboard video dài theo từng cảnh" in long_storyboard
    assert "Cảnh 10" in long_storyboard
    long_image_prompts = bot.long_video_followup_text("image_prompts", {
        "selected_topic": "affiliate AI cho người mới",
        "duration": "10 phút",
        "selected_style": "viral",
        "structure": "10 đoạn x 60 giây",
    }, "vi")
    assert "Prompt ảnh từng cảnh" in long_image_prompts
    assert "Negative prompt" in long_image_prompts
    long_video_prompts = bot.long_video_followup_text("video_prompts", {
        "selected_topic": "affiliate AI cho người mới",
        "duration": "10 phút",
        "selected_style": "viral",
        "structure": "10 đoạn x 60 giây",
    }, "vi")
    assert "Prompt video từng cảnh" in long_video_prompts
    assert "Thời lượng gợi ý" in long_video_prompts
    prompt_video_callbacks = [button.callback_data for row in bot.prompt_video_start_keyboard("vi").inline_keyboard for button in row]
    assert "promptvideo|kind|ad" in prompt_video_callbacks
    prompt_choices = bot.prompt_video_choices_text({"selected_topic": "máy xay mini", "prompt_kind": "ad"}, "vi")
    assert "3 prompt video gợi ý" in prompt_choices
    assert "Prompt A" in prompt_choices
    prompt_motion_callbacks = [button.callback_data for row in bot.guided_video_motion_keyboard("promptvideo", "vi").inline_keyboard for button in row]
    assert "promptvideo|back_choices" in prompt_motion_callbacks
    prompt_result = bot.guided_video_plan_text({"prompt_kind": "ad", "selected_prompt": "demo video", "selected_motion": "pushin", "selected_music": "none"}, "vi")
    assert "Prompt video đã sẵn sàng" in prompt_result
    assert "chưa gọi API video" in prompt_result
    image_start_callbacks = [button.callback_data for row in bot.image_video_start_keyboard("vi").inline_keyboard for button in row]
    assert "imagevideo|await_image" in image_start_callbacks
    image_style_callbacks = [button.callback_data for row in bot.image_video_style_keyboard("vi").inline_keyboard for button in row]
    assert {"imagevideo|style_choice|1", "imagevideo|style_choice|2", "imagevideo|style_choice|3"}.issubset(set(image_style_callbacks))
    assert "imagevideo|style_refresh" in image_style_callbacks
    assert "imagevideo|style_custom" in image_style_callbacks
    image_result = bot.guided_video_plan_text({"prompt_kind": "ad", "selected_prompt": "animate image", "selected_motion": "orbit", "selected_music": "tech"}, "vi", from_image=True)
    assert "Prompt video từ ảnh đã sẵn sàng" in image_result
    assert "/image_to_video_pack" not in bot.menu_hint_text("hint_image_to_video_pack")[1]

    music_text = bot.select_music_no_context_text("vi")
    music_buttons = [
        button.text
        for row in bot.select_music_no_context_keyboard("vi").inline_keyboard
        for button in row
    ]
    assert "Bạn muốn tìm nhạc theo phong cách nào" in music_text
    assert "Không tìm thấy kết quả số này" not in music_text
    assert {"1️⃣ Điện ảnh", "2️⃣ Công nghệ", "3️⃣ Viral/TikTok", "4️⃣ Nhẹ nhàng"}.issubset(set(music_buttons))


def test_video_ux_v6_shared_suggestions_and_navigation():
    bank_keys = [
        "prompt_ad",
        "prompt_cinema",
        "prompt_viral",
        "long_sales",
        "long_education",
        "long_story",
        "idea_physical",
        "idea_service",
        "idea_affiliate",
        "motion_place",
        "motion_fashion",
        "motion_food",
        "motion_education",
        "motion_story",
        "image_video_style",
    ]
    for key in bank_keys:
        assert len(bot.video_v6_suggestion_bank(key, "vi")) >= 10

    shared_keys = [
        "video_topic_suggestions",
        "video_motion_suggestions",
        "video_transition_suggestions",
        "video_music_voice_suggestions",
        "video_reference_analysis_templates",
        "marketing_campaign_suggestions",
        "image_topic_suggestions",
    ]
    for key in shared_keys:
        assert len(bot.creative_suggestion_bank(key, "vi")) >= 9
    assert bot.rotating_suggestions(["a", "b", "c", "d"], 2, 3) == ["c", "d", "a"]

    main_rows = bot.main_video_keyboard("vi").inline_keyboard
    assert [button.callback_data for button in main_rows[-1]] == ["vproduct|open|video_local_edit", "menu|main"]
    assert len(main_rows[-1]) == 2

    ai_rows = bot.video_ai_true_keyboard("vi").inline_keyboard
    assert [button.callback_data for button in ai_rows[-1]] == ["menu|main_video", "menu|main"]
    ai_callbacks = [button.callback_data for row in ai_rows for button in row]
    assert "videoref|start" in ai_callbacks

    self_scene_rows = bot.video_self_scene_ai_keyboard("vi").inline_keyboard
    assert all(len(row) <= 2 for row in self_scene_rows)
    assert [button.callback_data for button in self_scene_rows[-1]] == ["menu|main_video", "menu|main"]

    storyboard_rows = bot.storyboard_start_keyboard().inline_keyboard
    assert [button.callback_data for button in storyboard_rows[-1]] == ["menu|main_video", "menu|main"]
    storyboard_callbacks = [button.callback_data for row in bot.storyboard_scripts_keyboard().inline_keyboard for button in row]
    assert "storyboard|script_refresh" in storyboard_callbacks
    assert "storyboard|idea_custom" in storyboard_callbacks

    motion_first = bot.creative_motion_suggestions("product", 0, "vi")
    motion_next = bot.creative_motion_suggestions("product", 3, "vi")
    assert len(motion_first) == 3
    assert [item["title"] for item in motion_first] != [item["title"] for item in motion_next]
    for item in motion_first:
        assert item["prompt"]
        assert item["motion"]
        assert item["music"]
    motion_text = bot.creative_motion_suggestions_text({"kind": "product", "suggest_offset": 0}, "vi")
    assert "3 gợi ý Prompt / Chuyển động" in motion_text
    assert "Prompt video" in motion_text
    assert "Âm thanh" in motion_text
    motion_callbacks = [button.callback_data for row in bot.creative_motion_suggestions_keyboard("vi").inline_keyboard for button in row]
    assert {"motion|choice|1", "motion|choice|2", "motion|choice|3", "motion|refresh"}.issubset(set(motion_callbacks))
    assert "motion|cancel" not in motion_callbacks

    image_first = bot.image_video_style_suggestions(0, "vi")
    image_next = bot.image_video_style_suggestions(3, "vi")
    assert len(image_first) == 3
    assert image_first != image_next
    image_rows = bot.image_video_style_keyboard("vi").inline_keyboard
    assert [button.callback_data for button in image_rows[-1]] == ["imagevideo|back_image", "menu|main"]

    result_rows = bot.guided_video_result_keyboard("promptvideo", "vi").inline_keyboard
    assert [button.callback_data for button in result_rows[-1]] == ["promptvideo|back_music", "menu|main"]
    idea_result_rows = bot.video_idea_result_keyboard("vi").inline_keyboard
    assert [button.callback_data for button in idea_result_rows[-1]] == ["videoidea|back_choices", "menu|main"]

    frame_state = {"photos": [{"file_id": "a"}, {"file_id": "b"}], "planning_offset": 0}
    frame_next = {"photos": [{"file_id": "a"}, {"file_id": "b"}], "planning_offset": 3}
    frame_plan_text = bot.frame_video_planning_text(frame_state, "vi")
    assert "Kế hoạch ghép ảnh thành video" in frame_plan_text
    assert "Gợi ý phong cách" in frame_plan_text
    assert "Gợi ý transition" in frame_plan_text
    assert bot.frame_video_planning_suggestions(frame_state, "vi") != bot.frame_video_planning_suggestions(frame_next, "vi")
    frame_plan_callbacks = [button.callback_data for row in bot.frame_video_planning_keyboard("vi").inline_keyboard for button in row]
    assert {"framevideo|planning_continue", "framevideo|planning_refresh", "framevideo|back|collect"}.issubset(set(frame_plan_callbacks))


def test_video_ux_v7_trend_back_and_suggestion_flow():
    source = bot_source_text()
    trend_handler = source_between(source, "async def handle_trend_guided_callback", "async def handle_trend_video_flow_callback")
    self_scene_handler = source_between(source, "async def handle_self_scene_ai_callback", "async def handle_long_video_callback")

    group_text = bot.trend_guided_topic_group_text("vi")
    assert "Video theo trend" in group_text
    assert "gợi ý 3 chủ đề video trend" in group_text
    group_callbacks = [button.callback_data for row in bot.trend_guided_topic_group_keyboard("vi").inline_keyboard for button in row]
    assert {
        "trendg|topic_group|product",
        "trendg|topic_group|affiliate",
        "trendg|topic_group|ai_tool",
        "trendg|topic_custom",
    }.issubset(set(group_callbacks))
    assert "trendg|cancel" not in group_callbacks

    state = {"topic_group": "product", "suggest_offset": 0}
    first_topics = bot.trend_guided_topic_suggestions("product", 0, "vi")
    second_topics = bot.trend_guided_topic_suggestions("product", 3, "vi")
    assert len(first_topics) == 3
    assert first_topics != second_topics
    assert any("Nước hoa" in item or "Balo" in item for item in first_topics)
    topic_callbacks = [button.callback_data for row in bot.trend_guided_topic_suggestions_keyboard("vi").inline_keyboard for button in row]
    assert {"trendg|topic_select_1", "trendg|topic_select_2", "trendg|topic_select_3", "trendg|topic_refresh", "trendg|topic_custom"}.issubset(set(topic_callbacks))
    assert "trendg|cancel" not in topic_callbacks

    source_callbacks = [button.callback_data for row in bot.trend_guided_trend_source_keyboard("vi").inline_keyboard for button in row]
    assert "trendg|topic_back" in source_callbacks
    assert "trendg|cancel" not in source_callbacks
    assert "trendg|topic_group" in trend_handler
    assert "trendg|topic_select_1" in source

    trend_state = {"topic": "nước hoa nam", "trend_offset": 0}
    trend_text = bot.trend_guided_trend_choices_text_from_state(trend_state, "vi")
    trend_text_next = bot.trend_guided_trend_choices_text_from_state({"topic": "nước hoa nam", "trend_offset": 3}, "vi")
    assert "nước hoa nam" in trend_text
    assert trend_text != trend_text_next
    trend_callbacks = [button.callback_data for row in bot.trend_guided_trend_choices_keyboard("vi").inline_keyboard for button in row]
    assert {"trendg|trend_select_1", "trendg|trend_select_2", "trendg|trend_select_3", "trendg|trend_refresh"}.issubset(set(trend_callbacks))
    assert "trendg|cancel" not in trend_callbacks

    motion_state = {"topic": "nước hoa nam", "trend_choice": 1, "selected_trend_title": "Trend before/after", "motion_offset": 0}
    motion_first = bot.trend_guided_motion_ideas(motion_state, "vi")
    motion_second = bot.trend_guided_motion_ideas({**motion_state, "motion_offset": 3}, "vi")
    assert len(motion_first) == 3
    assert motion_first != motion_second
    assert "nước hoa nam" in " ".join(item["summary"] for item in motion_first)
    trend_motion_callbacks = [button.callback_data for row in bot.trend_guided_motion_choices_keyboard("vi").inline_keyboard for button in row]
    assert {"trendg|motion_select_1", "trendg|motion_select_2", "trendg|motion_select_3", "trendg|motion_refresh"}.issubset(set(trend_motion_callbacks))

    guided_state = {"selected_topic": "app AI automation", "selected_prompt": "video app AI automation", "motion_offset": 0, "music_offset": 0}
    guided_motion_first = bot.guided_video_motion_suggestions(guided_state, "vi")
    guided_motion_second = bot.guided_video_motion_suggestions({**guided_state, "motion_offset": 3}, "vi")
    assert len(guided_motion_first) == 3
    assert guided_motion_first != guided_motion_second
    guided_music_first = bot.guided_video_music_suggestions(guided_state, "vi")
    guided_music_second = bot.guided_video_music_suggestions({**guided_state, "music_offset": 3}, "vi")
    assert len(guided_music_first) == 3
    assert guided_music_first != guided_music_second
    prompt_motion_callbacks = [button.callback_data for row in bot.guided_video_motion_keyboard("promptvideo", "vi").inline_keyboard for button in row]
    prompt_music_callbacks = [button.callback_data for row in bot.guided_video_music_keyboard("promptvideo", "vi").inline_keyboard for button in row]
    assert "promptvideo|motion_refresh" in prompt_motion_callbacks
    assert "promptvideo|music_refresh" in prompt_music_callbacks
    assert "affiliate" in " ".join(bot.long_video_topic_suggestions("sales", 0, "en")).lower()
    assert "product" in " ".join(bot.image_video_style_suggestions(0, "en")).lower()
    assert "cafe" in " ".join(bot.video_v6_suggestion_bank("motion_place", "en")).lower()

    cinema_first = bot.video_idea_cinema_suggestions(0, "vi")
    cinema_second = bot.video_idea_cinema_suggestions(3, "vi")
    assert len(cinema_first) == 3
    assert cinema_first != cinema_second
    cinema_callbacks = [button.callback_data for row in bot.video_idea_cinema_suggestions_keyboard("vi").inline_keyboard for button in row]
    assert {"videoidea|cinema_choice|1", "videoidea|cinema_refresh", "videoidea|cinema_custom"}.issubset(set(cinema_callbacks))
    assert "videoidea|kind|cinema" in source_between(source, "async def handle_video_idea_callback", "def menu_text_main_ai")

    self_scene_callbacks = [button.callback_data for row in bot.self_scene_input_keyboard("vi").inline_keyboard for button in row]
    assert "selfscene|direction_refresh" in self_scene_callbacks
    assert "selfscene|direction_choice|1" in self_scene_callbacks
    assert bot.self_scene_direction_suggestions(0, "vi") != bot.self_scene_direction_suggestions(3, "vi")
    assert bot.self_scene_context_suggestions("product", "nước hoa nam", "vi", 0) != bot.self_scene_context_suggestions("product", "nước hoa nam", "vi", 6)
    self_scene_motion_callbacks = [button.callback_data for row in bot.self_scene_style_keyboard("vi").inline_keyboard for button in row]
    self_scene_music_callbacks = [button.callback_data for row in bot.self_scene_music_keyboard("vi").inline_keyboard for button in row]
    assert "selfscene|style_refresh" in self_scene_motion_callbacks
    assert "selfscene|finalization" in self_scene_music_callbacks
    assert "selfscene|music|none" in self_scene_music_callbacks
    assert "selfscene|music_refresh" not in self_scene_music_callbacks
    assert "selfscene|back_context" in self_scene_handler
    assert "selfscene|back_style" in self_scene_handler
    assert "selfscene|back_music" in self_scene_handler
    long_result_callbacks = [button.callback_data for row in bot.long_video_result_keyboard("vi").inline_keyboard for button in row]
    assert "longvideo|back_structure" in long_result_callbacks


def test_trend_guided_video_prompt_callbacks_are_telegram_safe():
    state = {
        "topic": "Nước hoa nam giúp tự tin trước buổi gặp khách hàng quan trọng",
        "trend_choice": 1,
        "selected_trend_title": "Before / After",
        "motion_choice": 1,
        "selected_motion_title": "Push-in sản phẩm chậm",
        "selected_motion_summary": "0-3s camera tiến vào sản phẩm; 3-8s orbit nhẹ; 8-15s giữ khung CTA sạch.",
        "image_prompt_choice": 1,
        "video_prompt_choice": 1,
    }

    full_prompt = bot.trend_guided_video_prompt_for_index(state, 1, "vi")
    assert len(full_prompt) > len(bot.trend_guided_video_prompt_preview(full_prompt, 1700))

    text_screens = [
        bot.trend_guided_video_prompts_text(state, "vi"),
        bot.trend_guided_selected_video_prompt_text(state, 1, "vi"),
        bot.trend_guided_video_public_off_text(state, "vi"),
    ]
    for text in text_screens:
        assert len(text) < 4096
        assert "Prompt đầy đủ vẫn được giữ" in text
        assert "chưa trừ Xu" in text

    keyboards = [
        bot.trend_guided_selected_motion_keyboard("vi"),
        bot.trend_guided_image_prompt_choices_keyboard("vi"),
        bot.trend_guided_selected_image_prompt_keyboard("vi"),
        bot.trend_guided_video_prompt_choices_keyboard("vi"),
        bot.trend_guided_selected_video_prompt_keyboard("vi", is_admin=True),
        bot.trend_guided_video_public_off_keyboard("vi", is_admin=True),
    ]
    for keyboard in keyboards:
        assert max(len(row) for row in keyboard.inline_keyboard) <= 2
        callbacks = [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if getattr(button, "callback_data", None)
        ]
        assert max(len(callback) for callback in callbacks) <= 64
        assert "trendg|cancel" not in callbacks


def test_trend_guided_video_prompt_callbacks_open_finalization(monkeypatch):
    replies = []

    async def fake_edit(query, text, reply_markup=None, parse_mode="HTML"):
        replies.append({"text": str(text), "reply_markup": reply_markup, "parse_mode": parse_mode})
        assert len(str(text)) < 4096
        return SimpleNamespace(text=text, reply_markup=reply_markup)

    monkeypatch.setattr(bot, "safe_edit_or_send", fake_edit)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "user_ui_lang", lambda _uid: "vi")

    class FakeQuery:
        def __init__(self, data, user_id=97701):
            self.data = data
            self.from_user = SimpleNamespace(id=user_id, first_name="Video UX", username="video_ux")
            self.message = SimpleNamespace(chat_id=97702)

        async def answer(self):
            return None

    async def press(data):
        await bot.handle_trend_guided_callback(
            SimpleNamespace(callback_query=FakeQuery(data)),
            SimpleNamespace(),
        )
        return replies[-1]

    uid = 97701
    bot.clear_trend_video_flow_pending(uid)
    bot.set_trend_video_flow_pending(
        uid,
        "image_prompt_selected",
        topic="Nước hoa nam giúp tự tin trước buổi gặp khách hàng quan trọng",
        trend_choice=1,
        selected_trend_title="Before / After",
        motion_choice=1,
        selected_motion_title="Push-in sản phẩm chậm",
        selected_motion_summary="0-3s camera tiến vào sản phẩm; 3-8s orbit nhẹ; 8-15s giữ khung CTA sạch.",
        image_prompt_choice=1,
    )

    prompt_choices = asyncio.run(press("trendg|video_prompt_step"))
    assert "Chọn 1 prompt video" in prompt_choices["text"]
    assert "Prompt đầy đủ vẫn được giữ" in prompt_choices["text"]

    selected_prompt = asyncio.run(press("trendg|video_prompt_select_1"))
    assert "Đã chọn prompt video" in selected_prompt["text"]

    finalization = asyncio.run(press("trendg|finalization"))
    assert "Tùy chọn hoàn thiện video" in finalization["text"]
    assert "chưa xử lý video và chưa trừ Xu" in finalization["text"]

    real_video = asyncio.run(press("trendg|video_real"))
    assert "Chọn gói xuất video AI" in real_video["text"]


def test_free_tools_guided_outputs_and_followups(monkeypatch):
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "free_hub_quota_payload", lambda _uid: {"allowed": True})
    monkeypatch.setattr(bot, "free_hub_record_success", lambda *_args, **_kwargs: 1)

    async def no_promo(*_args, **_kwargs):
        return None

    monkeypatch.setattr(bot, "maybe_send_free_hub_promo", no_promo)

    class FakeMessage:
        def __init__(self, text):
            self.text = text
            self.replies = []

        async def reply_text(self, text, parse_mode=None, reply_markup=None):
            self.replies.append({"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup})
            return SimpleNamespace(text=text, reply_markup=reply_markup)

    async def run_tool(task_type, user_text):
        uid = 871001
        bot.clear_free_hub_pending(uid)
        bot.set_free_hub_pending(uid, "input", task_type=task_type)
        message = FakeMessage(user_text)
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=uid, first_name="Free Tool", username="free_tool"),
        )
        handled = await bot.handle_free_hub_pending_text(update, SimpleNamespace())
        assert handled is True
        assert message.replies
        return message.replies[-1]

    meta = asyncio.run(run_tool("meta_ai_prompt", "Nước hoa nam dùng khi đi hẹn hò"))
    assert "Prompt ngắn" in meta["text"]
    assert "Prompt chi tiết" in meta["text"]
    assert "Prompt quảng cáo" in meta["text"]
    meta_buttons = [button.text for row in meta["reply_markup"].inline_keyboard for button in row]
    assert "🔁 Đổi 3 prompt khác" in meta_buttons
    assert "✅ Dùng prompt 1" in meta_buttons
    assert "✅ Dùng prompt 2" in meta_buttons
    assert "✅ Dùng prompt 3" in meta_buttons
    assert "🖼 Tạo prompt ảnh/video từ ý này" in meta_buttons
    assert "✍️ Viết caption/hashtag" in meta_buttons

    caption = asyncio.run(run_tool("caption_hashtag", "Máy xay sinh tố mini cho dân văn phòng, đăng TikTok"))
    assert "Caption ngắn" in caption["text"]
    assert "Caption bán hàng" in caption["text"]
    assert "Hashtag" in caption["text"]
    caption_buttons = [button.text for row in caption["reply_markup"].inline_keyboard for button in row]
    assert "🧠 Tạo thêm ý tưởng content" in caption_buttons
    assert "🖼 Tạo prompt ảnh/video" in caption_buttons

    ideas = asyncio.run(run_tool("content_idea", "Dịch vụ tạo video AI cho shop mỹ phẩm"))
    assert "3 ý tưởng video ngắn" in ideas["text"]
    assert "3 ý tưởng bài đăng" in ideas["text"]
    assert "Hướng nên làm trước" in ideas["text"]
    idea_buttons = [button.text for row in ideas["reply_markup"].inline_keyboard for button in row]
    assert "🎬 Tạo concept quảng cáo cinematic" in idea_buttons
    assert "✍️ Viết caption từ ý này" in idea_buttons

    prompts = asyncio.run(run_tool("image_video_prompt", "Nước hoa nam cao cấp"))
    assert "Prompt ảnh 9:16" in prompts["text"]
    assert "Prompt ảnh 1:1" in prompts["text"]
    assert "Prompt video AI" in prompts["text"]
    assert "Prompt ghép ảnh/video" in prompts["text"]
    prompt_buttons = [button.text for row in prompts["reply_markup"].inline_keyboard for button in row]
    assert "✅ Dùng prompt 1" in prompt_buttons
    assert "✅ Dùng prompt 2" in prompt_buttons
    assert "✅ Dùng prompt 3" in prompt_buttons
    assert "🔁 Đổi 3 prompt khác" in prompt_buttons
    assert "🎬 Tạo video AI từ prompt" in prompt_buttons


def test_free_tools_menu_byok_and_docs_are_guarded():
    main_text = bot.free_hub_main_text("vi")
    assert "chuẩn bị nội dung" in main_text
    main_buttons = [button.text for row in bot.free_hub_main_keyboard("vi").inline_keyboard for button in row]
    assert "🤖 Prompt Meta AI" in main_buttons
    assert "📝 Ghi chú / Tài liệu" in main_buttons
    assert "🔐 Kết nối API riêng" not in main_buttons
    assert "🔑 API riêng của tôi" not in main_buttons

    byok_text = bot.free_hub_byok_text("vi")
    byok_buttons = [button.text for row in bot.free_hub_byok_keyboard("vi").inline_keyboard for button in row]
    assert "không nên gửi api key" in byok_text.lower()
    assert "👨‍💼 Liên hệ admin" in byok_buttons
    assert not any("API key" in button for button in byok_buttons)

    docs_callbacks = [button.callback_data for row in bot.free_hub_docs_keyboard("vi").inline_keyboard for button in row]
    assert "menu|hint_doc_image_to_pdf" in docs_callbacks
    assert "freehub|docs_split_merge" in docs_callbacks
    assert "freehub|docs_summary_guard" in docs_callbacks


def test_free_tools_followup_buttons_have_handlers(monkeypatch):
    replies = []

    async def fake_edit(query, text, reply_markup=None, parse_mode="HTML"):
        replies.append({"text": str(text), "reply_markup": reply_markup, "parse_mode": parse_mode})
        return SimpleNamespace(text=text, reply_markup=reply_markup)

    async def no_promo(*_args, **_kwargs):
        return None

    monkeypatch.setattr(bot, "safe_edit_or_send", fake_edit)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "free_hub_record_success", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(bot, "maybe_send_free_hub_promo", no_promo)

    class FakeQuery:
        def __init__(self, data, user_id=871002):
            self.data = data
            self.from_user = SimpleNamespace(id=user_id, first_name="Free Tool", username="free_tool")
            self.message = SimpleNamespace(chat_id=871003)
            self.answers = []

        async def answer(self, text=None, show_alert=False):
            self.answers.append({"text": text, "show_alert": show_alert})
            return None

    async def press(data, uid=871002):
        await bot.handle_free_hub_callback(
            SimpleNamespace(callback_query=FakeQuery(data, uid)),
            SimpleNamespace(),
        )
        return replies[-1]

    uid = 871002
    bot.clear_free_hub_pending(uid)
    result = bot.free_hub_meta_prompt_pack("Nước hoa nam dùng khi đi hẹn hò")
    bot.set_free_hub_pending(
        uid,
        "result",
        task_type="meta_ai_prompt",
        user_input="Nước hoa nam dùng khi đi hẹn hò",
        result=result,
        provider="local_prompt_library",
    )

    variant = asyncio.run(press("freehub|variant", uid))
    assert "Prompt ngắn" in variant["text"]
    assert "Xu deducted" in variant["text"]

    prompts = asyncio.run(press("freehub|to_prompts", uid))
    assert "Prompt ảnh 9:16" in prompts["text"]
    assert "Prompt video AI" in prompts["text"]

    use_video = asyncio.run(press("freehub|use_video", uid))
    assert "Hệ thống tạo video đang bảo trì/nâng cấp nhẹ" in use_video["text"]
    assert "chưa xử lý video" in use_video["text"]
    use_video_buttons = [button.text for row in use_video["reply_markup"].inline_keyboard for button in row]
    assert "⬅️ Quay lại prompt" in use_video_buttons
    assert "🎞 Xuất video local" not in use_video_buttons

    byok = asyncio.run(press("freehub|byok", uid))
    assert "Kết nối API riêng chưa mở" in byok["text"]
    assert "chưa nhận API key" in byok["text"]


def test_video_regression_v91_callback_chains_restore_planning_flows(monkeypatch):
    replies = []

    async def fake_edit(query, text, reply_markup=None, parse_mode="HTML"):
        replies.append({"text": str(text), "reply_markup": reply_markup, "parse_mode": parse_mode})
        return SimpleNamespace(text=text, reply_markup=reply_markup)

    monkeypatch.setattr(bot, "safe_edit_or_send", fake_edit)
    monkeypatch.setattr(bot, "safe_edit_query_message", fake_edit)
    monkeypatch.setattr(bot, "safe_edit_or_send_long_html", fake_edit)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "user_ui_lang", lambda _uid: "vi")

    class FakeQuery:
        def __init__(self, data, user_id=91001):
            self.data = data
            self.from_user = SimpleNamespace(id=user_id, first_name="Video Test", username="video_test")
            self.message = SimpleNamespace(chat_id=92001)

        async def answer(self):
            return None

    async def press(handler, data, user_id=91001):
        query = FakeQuery(data, user_id)
        await handler(SimpleNamespace(callback_query=query), SimpleNamespace())
        return replies[-1]

    uid = 91001
    bot.clear_developing_video_pending(uid)
    bot.LAST_DEVELOPING_VIDEO_PLANS.pop(bot.developing_video_latest_key(uid, "videoidea"), None)
    bot.LAST_DEVELOPING_VIDEO_PLANS.pop(bot.developing_video_latest_key(uid, "selfscene"), None)
    bot.LAST_DEVELOPING_VIDEO_PLANS.pop(bot.developing_video_latest_key(uid, "longvideo"), None)

    asyncio.run(press(bot.handle_video_idea_callback, "videoidea|kind|ad", uid))
    asyncio.run(press(bot.handle_video_idea_callback, "videoidea|product_type|physical", uid))
    asyncio.run(press(bot.handle_video_idea_callback, "videoidea|product_choice|1", uid))
    asyncio.run(press(bot.handle_video_idea_callback, "videoidea|goal|sales", uid))
    ad_choices = asyncio.run(press(bot.handle_video_idea_callback, "videoidea|context|1", uid))
    assert "3 ý tưởng video quảng cáo" in ad_choices["text"]
    ad_result = asyncio.run(press(bot.handle_video_idea_callback, "videoidea|choose|1", uid))
    assert "Ý tưởng quảng cáo hoàn chỉnh" in ad_result["text"]
    assert "Prompt video từng cảnh" in ad_result["text"]

    asyncio.run(press(bot.handle_video_idea_callback, "videoidea|kind|cinema", uid))
    cinema_choices = asyncio.run(press(bot.handle_video_idea_callback, "videoidea|cinema_choice|1", uid))
    assert "3 ý tưởng điện ảnh / kể chuyện" in cinema_choices["text"]
    cinema_callbacks = [
        button.callback_data
        for row in cinema_choices["reply_markup"].inline_keyboard
        for button in row
    ]
    assert "videoidea|kind|cinema" in cinema_callbacks
    cinema_result = asyncio.run(press(bot.handle_video_idea_callback, "videoidea|choose|1", uid))
    assert "Kế hoạch điện ảnh / kể chuyện" in cinema_result["text"]
    assert "Mâu thuẫn/chuyển biến" in cinema_result["text"]
    cinema_storyboard = asyncio.run(press(bot.handle_video_idea_callback, "videoidea|storyboard", uid))
    assert "Storyboard điện ảnh" in cinema_storyboard["text"]

    bot.LAST_USER_VIDEO[uid] = {
        "file_id": "self-shot-video-file",
        "file_name": "self-shot.mp4",
        "mime_type": "video/mp4",
        "duration": 12,
        "file_size": 12345,
        "created_at": bot.time.time(),
    }
    asyncio.run(press(bot.handle_self_scene_ai_callback, "selfscene|start", uid))
    asyncio.run(press(bot.handle_self_scene_ai_callback, "selfscene|use_recent_video", uid))
    asyncio.run(press(bot.handle_self_scene_ai_callback, "selfscene|object|product", uid))
    asyncio.run(press(bot.handle_self_scene_ai_callback, "selfscene|direction_choice|1", uid))
    asyncio.run(press(bot.handle_self_scene_ai_callback, "selfscene|context|1", uid))
    selfscene_result = asyncio.run(press(bot.handle_self_scene_ai_callback, "selfscene|style_choice|1", uid))
    assert "Tùy chọn hoàn thiện video" in selfscene_result["text"]
    assert bot.get_latest_developing_video_plan(uid, "selfscene")["source_file_id"] == "self-shot-video-file"
    music_result = asyncio.run(press(bot.handle_self_scene_ai_callback, "selfscene|music_guard", uid))
    assert "Gợi ý nhạc/SFX" in music_result["text"]
    assert "Bạn muốn đổi video này theo hướng nào" not in music_result["text"]
    frame_guard = asyncio.run(press(bot.handle_self_scene_ai_callback, "selfscene|frame_hint", uid))
    assert "chưa có bộ ảnh" in frame_guard["text"].lower()
    image_prompt = asyncio.run(press(bot.handle_self_scene_ai_callback, "selfscene|image_guard", uid))
    assert "Prompt ảnh khung chính" in image_prompt["text"]

    asyncio.run(press(bot.handle_long_video_callback, "longvideo|start", uid))
    asyncio.run(press(bot.handle_long_video_callback, "longvideo|topic|sales", uid))
    asyncio.run(press(bot.handle_long_video_callback, "longvideo|topic_choice|1", uid))
    asyncio.run(press(bot.handle_long_video_callback, "longvideo|duration|3 phút", uid))
    asyncio.run(press(bot.handle_long_video_callback, "longvideo|style|professional", uid))
    long_result = asyncio.run(press(bot.handle_long_video_callback, "longvideo|structure|1", uid))
    assert "Lộ trình video dài AI" in long_result["text"]
    long_back = asyncio.run(press(bot.handle_long_video_callback, "longvideo|back_structure", uid))
    assert "Chọn cấu trúc" in long_back["text"]
    assert bot.get_developing_video_pending(uid)["step"] == "structure"

    bot.clear_trend_video_flow_pending(uid)
    bot.set_trend_video_flow_pending(uid, "topic_group")
    asyncio.run(press(bot.handle_trend_guided_callback, "trendg|topic_group|product", uid))
    asyncio.run(press(bot.handle_trend_guided_callback, "trendg|topic_select_1", uid))
    asyncio.run(press(bot.handle_trend_guided_callback, "trendg|trend_source_popular", uid))
    trend_selected = asyncio.run(press(bot.handle_trend_guided_callback, "trendg|trend_select_1", uid))
    assert "Đã chọn trend" in trend_selected["text"]
    trend_locked = asyncio.run(press(bot.handle_trend_guided_callback, "trendg|trend_lock", uid))
    assert "chọn chuyển động" in trend_locked["text"].lower()

    monkeypatch.setattr(bot, "SHOPAIKEY_PUBLIC_VIDEO_ENABLED", False)
    monkeypatch.setattr(bot, "shopaikey_active_job_for_user", lambda *_args, **_kwargs: None)
    bot.save_developing_video_plan(uid, "promptvideo", {
        "prompt_kind": "ad",
        "selected_topic": "app AI",
        "selected_prompt": "clean product demo",
        "selected_motion": "slow push-in",
        "selected_music": "none",
    })
    provider_guard = asyncio.run(press(bot.handle_prompt_video_callback, "promptvideo|generate", uid))
    assert "Tùy chọn hoàn thiện video" in provider_guard["text"]
    assert "chưa xử lý video và chưa trừ Xu" in provider_guard["text"]

    bot.clear_developing_video_pending(uid)
    bot.clear_trend_video_flow_pending(uid)


def test_long_ai_story_video_and_cinematic_storyboard_pack_v1(monkeypatch, tmp_path):
    source = bot_source_text()
    labels = [button.text for row in bot.main_video_keyboard("vi").inline_keyboard for button in row]
    callbacks = [button.callback_data for row in bot.main_video_keyboard("vi").inline_keyboard for button in row]
    assert "🎬 Phim AI nhiều cảnh" in labels
    assert "🎞 Storyboard + Prompt" in labels
    assert "vproduct|open|multi_scene_film" in callbacks
    assert "vproduct|open|storyboard_prompt" in callbacks
    assert 'CallbackQueryHandler(handle_storyboard_pack_callback, pattern=r"^storypack\\|")' in source
    assert 'CommandHandler("long_video_status", cmd_long_video_status)' in source

    long_plan = bot.long_video_plan_text(
        {
            "selected_topic": "nước hoa nam dùng khi đi hẹn hò",
            "duration": "60 giây",
            "selected_style": "cinematic",
            "structure": "10 shot x 6 giây",
            "project_id": 12,
        },
        "vi",
    )
    assert "Character Bible" in long_plan
    assert "Project ID" in long_plan
    assert "không bắt chước người nổi tiếng" in long_plan
    assert "TOAN AAS chưa xử lý thật và chưa trừ Xu" in long_plan

    story_state = {
        "selected_topic": "máy xay sinh tố mini cho dân văn phòng",
        "shot_type": "8",
        "shot_count": 8,
        "selected_style": "clean",
    }
    story_text = bot.storyboard_pack_result_text(story_state, "vi")
    for expected in [
        "Storyboard + Prompt điện ảnh",
        "3 hướng prompt có thể dùng",
        "Shot 1",
        "Prompt ảnh",
        "Prompt video",
        "Negative prompt",
        "TOAN AAS chỉ bắt đầu xử lý sau khi quý khách xác nhận ở bước cuối",
    ]:
        assert expected in story_text
    story_callbacks = [button.callback_data for row in bot.storyboard_pack_result_keyboard("vi").inline_keyboard for button in row]
    assert {
        "storypack|image_prompts",
        "storypack|video_prompts",
        "storypack|meta_ai_prompt",
        "storypack|create_video_ai",
        "storypack|create_or_upload_images",
        "storypack|save",
    }.issubset(set(story_callbacks))
    assert "Hệ thống tạo video đang bảo trì/nâng cấp nhẹ" in bot.storyboard_pack_guard_text("ai_video", "vi")

    db_path = tmp_path / "long-story.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "DB_BACKUP_DIR", str(tmp_path / "backups"))
    bot.init_db()
    project_id = bot.create_long_video_project_from_plan("story-user", {
        "selected_topic": "nước hoa nam cinematic",
        "duration": "60 giây",
        "selected_style": "cinematic",
        "structure": "10 shot x 6 giây",
    })
    assert project_id > 0
    status_text = bot.long_video_project_status_text(project_id, "story-user", "vi")
    assert "Trạng thái project video dài" in status_text
    assert "10" in status_text
    pack_id = bot.save_storyboard_prompt_pack("story-user", story_state, "locked")
    assert pack_id > 0


def test_video_regression_v91_storyboard_restores_project_and_reuses_frame_flow(monkeypatch):
    replies = []
    uid = 93001
    project_id = 77

    async def fake_edit(query, text, reply_markup=None, parse_mode="HTML"):
        replies.append({"text": str(text), "reply_markup": reply_markup, "parse_mode": parse_mode})
        return SimpleNamespace(text=text, reply_markup=reply_markup)

    monkeypatch.setattr(bot, "safe_edit_or_send", fake_edit)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(
        bot,
        "storyboard_project_for_user",
        lambda pid, user_id: {
            "id": project_id,
            "user_id": str(uid),
            "scene_count": 3,
            "source_type": "ai_suggested",
        }
        if int(pid) == project_id and int(user_id) == uid
        else {},
    )
    monkeypatch.setattr(
        bot,
        "storyboard_scenes_for_project",
        lambda pid: [
            {"scene_index": 1, "image_file_id": "image-1", "image_url": ""},
            {"scene_index": 2, "image_file_id": "image-2", "image_url": ""},
            {"scene_index": 3, "image_file_id": "image-3", "image_url": ""},
        ]
        if int(pid) == project_id
        else [],
    )
    monkeypatch.setattr(bot, "create_storyboard_video_record", lambda *args, **kwargs: 1)

    class FakeQuery:
        data = f"storyboard|mode_frame|{project_id}"
        from_user = SimpleNamespace(id=uid, first_name="Storyboard", username="storyboard")
        message = SimpleNamespace(chat_id=94001)

        async def answer(self):
            return None

    bot.clear_storyboard_state(uid)
    bot.clear_frame_video_state(uid)
    asyncio.run(bot.handle_storyboard_callback(SimpleNamespace(callback_query=FakeQuery()), SimpleNamespace()))
    frame_state = bot.get_frame_video_state(uid)
    assert frame_state["step"] == "planning"
    assert frame_state["source"] == "storyboard_project"
    assert frame_state["project_id"] == project_id
    assert len(frame_state["photos"]) == 3
    assert "Kế hoạch ghép ảnh thành video" in replies[-1]["text"]
    callbacks = [
        button.callback_data
        for row in replies[-1]["reply_markup"].inline_keyboard
        for button in row
    ]
    assert "framevideo|planning_continue" in callbacks
    assert "framevideo|planning_refresh" in callbacks

    bot.clear_storyboard_state(uid)
    bot.clear_frame_video_state(uid)


def test_video_regression_v91_storyboard_sqlite_rows_are_mapping_safe(monkeypatch, tmp_path):
    db_path = tmp_path / "storyboard-regression.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "DB_STARTUP_BACKUP_ENABLED", False)
    bot.init_db()

    scenes = bot.storyboard_build_scenes("Máy xay mini cho dân văn phòng", 3)
    project_id = bot.create_storyboard_project(
        "storyboard-owner",
        "user_script",
        "Máy xay mini",
        "Máy xay mini cho dân văn phòng",
        scenes,
    )
    bot.update_storyboard_scene_asset(project_id, 1, image_job_id=101, image_file_id="file-1", status="image_ready")
    bot.update_storyboard_scene_asset(project_id, 2, image_job_id=102, image_file_id="file-2", status="image_ready")

    project = bot.storyboard_project_for_user(project_id, "storyboard-owner")
    rows = bot.storyboard_scenes_for_project(project_id)
    assert project["id"] == project_id
    assert project["user_id"] == "storyboard-owner"
    assert len(rows) == 3
    assert rows[0]["image_file_id"] == "file-1"
    assert rows[1]["image_file_id"] == "file-2"
    assert bot.storyboard_project_for_user(project_id, "different-user") == {}


def test_video_regression_v91_callback_prefixes_are_registered_and_not_orphaned():
    source = bot_source_text()
    handler_by_prefix = {
        "videoidea": "CallbackQueryHandler(handle_video_idea_callback",
        "selfscene": "CallbackQueryHandler(handle_self_scene_ai_callback",
        "longvideo": "CallbackQueryHandler(handle_long_video_callback",
        "trendg": "CallbackQueryHandler(handle_trend_guided_callback",
        "storyboard": "CallbackQueryHandler(handle_storyboard_callback",
        "framevideo": "CallbackQueryHandler(handle_frame_video_callback",
        "promptvideo": "CallbackQueryHandler(handle_prompt_video_callback",
        "imagevideo": "CallbackQueryHandler(handle_image_video_callback",
        "videoref": "CallbackQueryHandler(handle_video_reference_callback",
    }
    keyboards = [
        bot.main_video_keyboard("vi"),
        bot.video_idea_menu_keyboard("vi"),
        bot.video_idea_cinema_suggestions_keyboard("vi"),
        bot.video_idea_choice_keyboard("vi", "cinema"),
        bot.video_idea_result_keyboard("vi"),
        bot.self_scene_input_keyboard("vi"),
        bot.self_scene_object_keyboard("vi"),
        bot.self_scene_context_keyboard("vi"),
        bot.self_scene_style_keyboard("vi"),
        bot.self_scene_music_keyboard("vi"),
        bot.self_scene_result_keyboard("vi"),
        bot.long_video_topic_keyboard("vi"),
        bot.long_video_topic_suggestions_keyboard("vi"),
        bot.long_video_duration_keyboard("vi"),
        bot.long_video_style_keyboard("vi"),
        bot.long_video_structure_keyboard("10 phút", "vi"),
        bot.long_video_result_keyboard("vi"),
        bot.trend_guided_topic_group_keyboard("vi"),
        bot.trend_guided_trend_source_keyboard("vi"),
        bot.trend_guided_trend_choices_keyboard("vi"),
        bot.storyboard_start_keyboard(),
        bot.storyboard_scripts_keyboard(),
        bot.storyboard_ready_keyboard(),
        bot.storyboard_after_images_keyboard(77),
        bot.frame_video_planning_keyboard("vi"),
    ]
    callbacks = [
        button.callback_data
        for keyboard in keyboards
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "selfscene|music_guard" in callbacks
    assert "selfscene|music" not in [
        button.callback_data
        for row in bot.self_scene_result_keyboard("vi").inline_keyboard
        for button in row
    ]
    for callback in callbacks:
        assert len(callback.encode("utf-8")) <= 64
        prefix = callback.split("|", 1)[0]
        if prefix in handler_by_prefix:
            assert handler_by_prefix[prefix] in source


def test_video_ai_system_v81_reference_dubbing_marketing_and_free_planning(monkeypatch):
    source = bot_source_text()
    monkeypatch.setattr(bot, "is_admin_user", lambda user_id: str(user_id) == "1")

    main_labels = [button.text for row in bot.main_video_keyboard("vi").inline_keyboard for button in row]
    assert "🌐 Dịch/Lồng tiếng video" not in main_labels
    assert "🎞 Video mẫu → Video AI" in [button.text for row in bot.video_ai_true_keyboard("vi").inline_keyboard for button in row]
    assert "🎞 Video mẫu → Video AI" not in main_labels

    ref_start = bot.video_reference_start_text("vi")
    assert "Video mẫu → Video AI" in ref_start
    assert "chưa trừ Xu" in ref_start
    ref_callbacks = [button.callback_data for row in bot.video_reference_start_keyboard("vi").inline_keyboard for button in row]
    assert "videoref|await_video" in ref_callbacks
    ref_state = {"analysis_kind": "ad", "suggest_offset": 0, "selected_topic": "App AI automation cho chủ shop nhỏ"}
    assert len(bot.video_reference_topic_suggestions(ref_state, "vi")) == 3
    assert bot.video_reference_topic_suggestions(ref_state, "vi") != bot.video_reference_topic_suggestions({**ref_state, "suggest_offset": 3}, "vi")
    ref_plan = bot.video_reference_plan_text(ref_state, "vi")
    for expected in ["Tóm tắt video mẫu", "Phong cách video mẫu", "Prompt ảnh", "Prompt video", "không sao chép"]:
        assert expected in ref_plan
    ref_result_callbacks = [button.callback_data for row in bot.video_reference_result_keyboard("vi").inline_keyboard for button in row]
    assert {"videoref|image_prompts", "videoref|frame_plan", "videoref|generate", "videoref|save"}.issubset(set(ref_result_callbacks))

    dub_labels = [button.text for row in bot.video_dubbing_menu_keyboard("vi").inline_keyboard for button in row]
    assert {"👁 Tạo phụ đề tự động", "🗣 Lồng tiếng tự động", "🎬 Phụ đề + lồng tiếng", "🔗 Tải video từ link"}.issubset(set(dub_labels))
    assert "🎭 Dịch + lồng tiếng" not in dub_labels
    assert "🎬 Dịch + lồng tiếng + video" not in dub_labels
    assert "🎙 Lồng tiếng voice" not in dub_labels
    dub_confirm = bot.video_dubbing_confirm_text(
        {
            "mode": "translate_dub",
            "video_file_id": "video-1",
            "video_duration": 383,
            "target_language": "Tiếng Anh",
            "voice_style": "Nữ tự nhiên",
        },
        "vi",
    )
    assert "Video đã sẵn sàng lồng tiếng" in dub_confirm
    assert "1.050 Xu" not in dub_confirm
    assert "Chi phí dự kiến" not in dub_confirm
    assert "trừ Xu" in dub_confirm
    assert "Tác vụ:" not in dub_confirm

    subtitle_confirm = bot.video_dubbing_confirm_text(
        {"mode": "subtitle", "video_file_id": "video-2", "source_language": "auto", "video_duration": 45},
        "vi",
    )
    assert "Video đã sẵn sàng tạo phụ đề" in subtitle_confirm
    assert "Kiểu giọng" not in subtitle_confirm
    translated_subtitle_confirm = bot.video_dubbing_confirm_text(
        {"mode": "translate_subtitle", "video_file_id": "video-3", "target_language": "Tiếng Việt", "video_duration": 61},
        "vi",
    )
    assert "Video đã sẵn sàng tạo phụ đề dịch" in translated_subtitle_confirm
    assert "Kiểu giọng" not in translated_subtitle_confirm

    pricing = bot.calculate_video_translate_price("translate_subtitle", 383)
    assert pricing == {
        "mode": "subtitle_translate",
        "duration_seconds": 383,
        "billable_minutes": 7,
        "unit_price_xu": 40,
        "total_price_xu": 280,
    }
    assert bot.calculate_video_translate_price("subtitle", 0)["total_price_xu"] == 20
    pricing_text = bot.video_dubbing_pricing_text("vi")
    for marker in ["20 Xu/phút", "40 Xu/phút", "100 Xu/phút", "150 Xu/phút", "chưa xử lý và chưa trừ Xu"]:
        assert marker in pricing_text
    assert "API" not in pricing_text
    assert "provider" not in pricing_text.lower()
    dub_voice_buttons = [button for row in bot.video_dubbing_voice_keyboard("vi", {"mode": "dub"}).inline_keyboard for button in row]
    translate_dub_voice_buttons = [button for row in bot.video_dubbing_voice_keyboard("vi", {"mode": "translate_dub"}).inline_keyboard for button in row]
    assert any(button.text == "⬅️ Quay lại ngôn ngữ" and button.callback_data == "videodub|back_voice" for button in dub_voice_buttons)
    assert any(button.text == "⬅️ Quay lại ngôn ngữ" and button.callback_data == "videodub|back_voice" for button in translate_dub_voice_buttons)

    bot.clear_video_dubbing_pending("dub-state")
    bot.set_video_dubbing_pending("dub-state", "await_video", mode="translate_subtitle")
    bot.set_video_dubbing_pending(
        "dub-state",
        "language",
        video_file_id="file-123",
        video_message_id="456",
        video_duration="75",
        video_file_size="1000",
    )
    bot.set_video_dubbing_pending("dub-state", "confirm", target_language="Tiếng Việt")
    saved_state = bot.get_video_dubbing_pending("dub-state")
    assert saved_state["mode"] == "subtitle_translate"
    assert saved_state["video_file_id"] == "file-123"
    assert saved_state["video_message_id"] == "456"
    assert saved_state["target_language"] == "Tiếng Việt"
    assert bot.clear_video_dubbing_pending("dub-state") is True

    dubbing_callback_source = source_between(source, "async def handle_video_dubbing_callback", "def marketing_pending_key")
    assert "spend_fixed_credit_info" not in dubbing_callback_source
    assert "deduct_dynamic_credit" not in dubbing_callback_source
    assert "shopaikey_video_create" not in dubbing_callback_source
    assert "execute_video_dubbing_pipeline" in dubbing_callback_source
    assert "confirm_subtitle_create" in dubbing_callback_source
    assert "confirm_subtitle_translate" in dubbing_callback_source
    assert "confirm_subtitle_plus_dub" in dubbing_callback_source

    admin_labels = [button.text for row in bot.menu_nav_keyboard("admin", True).inline_keyboard for button in row]
    assert "📣 Marketing tự động" in admin_labels
    public_admin_labels = [button.text for row in bot.menu_nav_keyboard("admin", False).inline_keyboard for button in row]
    assert "📣 Marketing tự động" not in public_admin_labels
    marketing_callbacks = [button.callback_data for row in bot.marketing_menu_keyboard().inline_keyboard for button in row]
    assert {"marketing|kind|physical", "marketing|kind|affiliate", "marketing|kind_custom"}.issubset(set(marketing_callbacks))
    market_state = {"kind": "service", "suggest_offset": 0}
    assert len(bot.marketing_suggestions(market_state)) == 3
    assert bot.marketing_suggestions(market_state) != bot.marketing_suggestions({"kind": "service", "suggest_offset": 3})
    market_plan = bot.marketing_plan_text({"kind": "service", "selected_brief": "ra mắt app AI"})
    assert "Admin V1" in market_plan
    for expected in ["Sản phẩm/dịch vụ", "Khách hàng mục tiêu", "Kênh đề xuất", "Lịch đăng 7 ngày", "Bước tiếp theo"]:
        assert expected in market_plan
    assert "Chưa tự đăng bài" in market_plan
    assert "chưa trừ Xu" in market_plan

    assert 'CallbackQueryHandler(handle_video_reference_callback, pattern=r"^videoref\\|")' in source
    assert 'CallbackQueryHandler(handle_video_dubbing_callback, pattern=r"^videodub\\|")' in source
    assert 'CallbackQueryHandler(handle_marketing_callback, pattern=r"^marketing\\|")' in source
    assert "handle_marketing_pending_text(update, context)" in source
    assert "handle_video_reference_pending_upload(update, context)" in source
    assert "handle_video_dubbing_pending_upload(update, context)" in source


def test_video_subtitle_v22_mode_routing_and_upload_confirm(monkeypatch):
    replies = []

    async def fake_edit(_query, text, reply_markup=None, parse_mode="HTML"):
        replies.append({"text": str(text), "reply_markup": reply_markup, "parse_mode": parse_mode})
        return SimpleNamespace(text=text, reply_markup=reply_markup)

    class FakeMessage:
        def __init__(self, file_id="video-file"):
            self.video = SimpleNamespace(
                file_id=file_id,
                file_unique_id=f"{file_id}-unique",
                file_name=f"{file_id}.mp4",
                mime_type="video/mp4",
                duration=65,
                file_size=1024,
                width=720,
                height=1280,
            )
            self.document = None
            self.message_id = 88
            self.sent = []

        async def reply_text(self, text, **kwargs):
            self.sent.append({"text": str(text), **kwargs})
            return SimpleNamespace(text=text)

    class FakeQuery:
        def __init__(self, data, user_id):
            self.data = data
            self.from_user = SimpleNamespace(id=user_id)
            self.message = FakeMessage()

        async def answer(self):
            return None

    async def press(data, user_id):
        query = FakeQuery(data, user_id)
        await bot.handle_video_dubbing_callback(
            SimpleNamespace(callback_query=query),
            SimpleNamespace(),
        )
        return replies[-1]

    monkeypatch.setattr(bot, "safe_edit_or_send", fake_edit)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: None)
    monkeypatch.setattr(bot, "remember_last_media", lambda _update: None)
    monkeypatch.setattr(bot, "video_dubbing_capability", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(bot, "video_dubbing_public_processing_ready", lambda *_args, **_kwargs: True)

    async def fake_prepare(_context, state, user_id, allow_admin=False):
        translated_ref = bot.set_video_dubbing_artifact(user_id, "translated_subtitle", "Translated subtitle")
        state = bot.set_video_dubbing_pending(user_id, state.get("step") or "output", translated_subtitle_ref=translated_ref)
        return {"state": state, "output_subtitle": "Translated subtitle", "output_script": "Translated subtitle"}

    monkeypatch.setattr(bot, "video_dubbing_prepare_subtitles", fake_prepare)

    cases = [
        (71001, bot.VIDEO_SUBTITLE_MODE_CREATE, "Tạo phụ đề tự động"),
        (71002, bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "Dịch phụ đề"),
        (71003, bot.VIDEO_SUBTITLE_MODE_DUB, "Lồng tiếng tự động"),
        (71004, bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "Phụ đề + lồng tiếng"),
    ]
    for uid, mode, expected_text in cases:
        bot.clear_video_dubbing_pending(uid)
        result = asyncio.run(press(f"videodub|type|{mode}", uid))
        state = bot.get_video_dubbing_pending(uid)
        assert state["video_processing_mode"] == mode
        assert state["step"] == "source"
        assert "gửi video/audio" in result["text"].lower()
        callbacks = [button.callback_data for row in result["reply_markup"].inline_keyboard for button in row]
        assert "videodub|link_start" not in callbacks
        result = asyncio.run(press("videodub|source_upload", uid))
        state = bot.get_video_dubbing_pending(uid)
        assert state["step"] == "await_video"
        assert expected_text.lower() in result["text"].lower()
        assert "gửi hoặc reply video/audio" in result["text"].lower()
        assert "API" not in result["text"]
        assert "provider" not in result["text"].lower()

    create_state = bot.get_video_dubbing_pending(71001)
    assert not create_state.get("target_language")
    assert not create_state.get("voice_style")
    translate_state = bot.get_video_dubbing_pending(71002)
    assert translate_state["step"] == "await_video"
    assert not translate_state.get("voice_style")
    dub_state = bot.get_video_dubbing_pending(71003)
    assert dub_state["step"] == "await_video"
    assert not dub_state.get("target_language")

    message = FakeMessage("video-71004")
    update = SimpleNamespace(effective_user=SimpleNamespace(id=71004), message=message)
    assert asyncio.run(bot.handle_video_dubbing_pending_upload(update, SimpleNamespace())) is True
    assert bot.get_video_dubbing_pending(71004)["step"] == "language"
    asyncio.run(press("videodub|language|English", 71004))
    plus_state = bot.get_video_dubbing_pending(71004)
    assert plus_state["step"] == "output"
    assert plus_state["target_language"] == "English"
    asyncio.run(press("videodub|continue_dubbing", 71004))
    assert bot.get_video_dubbing_pending(71004)["step"] == "voice"
    asyncio.run(press("videodub|voice|default_female", 71004))
    assert bot.get_video_dubbing_pending(71004)["step"] == "voice_speed"
    asyncio.run(press("videodub|speed_default", 71004))
    assert bot.get_video_dubbing_pending(71004)["step"] == "confirm"

    upload_cases = [
        (71101, bot.VIDEO_SUBTITLE_MODE_CREATE, {}, "output", "videodub|final", "Video đã sẵn sàng tạo phụ đề"),
        (
            71102,
            bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            {"target_language": "English", "translate_requested": "1"},
            "output",
            "videodub|final",
            "Xuất phụ đề dịch",
        ),
        (
            71103,
            bot.VIDEO_SUBTITLE_MODE_DUB,
            {"target_language": "Tiếng Việt", "voice_style": "Nữ tự nhiên", "voice_speed": "1.0"},
            "confirm",
            "videodub|confirm_dub",
            "Video đã sẵn sàng lồng tiếng",
        ),
        (
            71104,
            bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            {"target_language": "English", "translate_requested": "1"},
            "output",
            "videodub|final",
            "Video đã sẵn sàng tạo phụ đề dịch",
        ),
    ]
    for uid, mode, extra, expected_step, expected_callback, expected_label in upload_cases:
        bot.clear_video_dubbing_pending(uid)
        bot.set_video_dubbing_pending(uid, "await_video", video_processing_mode=mode, **extra)
        message = FakeMessage(f"video-{uid}")
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=uid),
            message=message,
        )
        handled = asyncio.run(bot.handle_video_dubbing_pending_upload(update, SimpleNamespace()))
        assert handled is True
        state = bot.get_video_dubbing_pending(uid)
        assert state["step"] == expected_step
        if mode == bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB:
            assert state["video_processing_mode"] == bot.VIDEO_SUBTITLE_MODE_TRANSLATE
            assert state["requested_mode"] == bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB
        else:
            assert state["video_processing_mode"] == mode
        assert expected_label in message.sent[-1]["text"]
        callbacks = [
            button.callback_data
            for row in message.sent[-1]["reply_markup"].inline_keyboard
            for button in row
        ]
        assert expected_callback in callbacks


def test_video_subtitle_v22_per_mode_guard_and_pipeline_outputs(monkeypatch):
    source = bot_source_text()
    pipeline_source = source_between(source, "async def execute_video_dubbing_pipeline", "async def handle_video_dubbing_pending_upload")
    prepare_source = source_between(source, "async def video_dubbing_prepare_subtitles", "async def execute_video_dubbing_pipeline")
    resolver_source = source_between(source, "async def video_dubbing_resolve_source_script", "async def video_dubbing_render_video")
    assert "video_dubbing_prepare_subtitles" in pipeline_source
    assert "video_dubbing_transcribe_bytes" in resolver_source
    assert "translate_subtitle_text" in prepare_source
    assert "video_dubbing_tts_bytes" in pipeline_source
    assert pipeline_source.index("video_dubbing_prepare_subtitles") < pipeline_source.index("spend_fixed_credit_info")

    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_TRANSLATE_SUBTITLE_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_DUB_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PLUS_DUB_ENABLED", False)
    for mode, maintenance_text in [
        (bot.VIDEO_SUBTITLE_MODE_CREATE, "Tạo/gắn phụ đề vào video đang bảo trì/nâng cấp"),
        (bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "Dịch video, phụ đề và lồng tiếng đang bảo trì/nâng cấp"),
        (bot.VIDEO_SUBTITLE_MODE_DUB, "Dịch video, phụ đề và lồng tiếng đang bảo trì/nâng cấp"),
        (bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "Dịch video, phụ đề và lồng tiếng đang bảo trì/nâng cấp"),
    ]:
        capability = bot.video_dubbing_capability(mode, {})
        assert capability["reason"] == "mode_disabled"
        guard = bot.video_dubbing_guard_text(mode, {}, "vi")
        assert maintenance_text in guard
        assert "chưa trừ Xu" in guard
        assert "API" not in guard
        assert "provider" not in guard.lower()

    monkeypatch.setattr(bot, "video_dubbing_public_processing_ready", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(bot, "apply_member_service_discount", lambda _uid, amount, _event: {"final_cost": amount})
    monkeypatch.setattr(bot, "get_user", lambda _uid: (99999, 0, 0))
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "video_dubbing_download_source", lambda *_args, **_kwargs: None)

    async def fake_download(_context, _state):
        return b"video-bytes", "video/mp4"

    async def fake_transcribe(_data, _context, content_type="application/octet-stream"):
        assert content_type == "video/mp4"
        return "Test ASR", "Xin chào từ video", "chars=17"

    async def fake_translate(text, target, **_kwargs):
        return {"text": f"{text} translated to {target}"}

    async def fake_tts(text, voice_style="", voice_id="", voice_speed="1.0"):
        return "Test TTS", b"audio-bytes", f"voice={voice_style}; voice_id={voice_id}; speed={voice_speed}; chars={len(text)}"

    monkeypatch.setattr(bot, "video_dubbing_download_source", fake_download)
    monkeypatch.setattr(bot, "video_dubbing_transcribe_bytes", fake_transcribe)
    monkeypatch.setattr(bot, "translate_subtitle_text", fake_translate)
    monkeypatch.setattr(bot, "video_dubbing_tts_bytes", fake_tts)
    monkeypatch.setattr(
        bot,
        "spend_fixed_credit_info",
        lambda _uid, amount, _event, _note: {"ok": True, "final_cost": amount},
    )

    class OutputMessage:
        def __init__(self):
            self.documents = []
            self.audio = []

        async def reply_document(self, document, **kwargs):
            self.documents.append((document, kwargs))

        async def reply_audio(self, audio, **kwargs):
            self.audio.append((audio, kwargs))

    for mode, expect_subtitle, expect_audio in [
        (bot.VIDEO_SUBTITLE_MODE_CREATE, True, False),
        (bot.VIDEO_SUBTITLE_MODE_TRANSLATE, True, False),
        (bot.VIDEO_SUBTITLE_MODE_DUB, False, True),
        (bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, True, True),
    ]:
        message = OutputMessage()
        query = SimpleNamespace(from_user=SimpleNamespace(id=72001), message=message)
        state = {
            "video_processing_mode": mode,
            "video_file_id": "video-file",
            "video_duration": 30,
            "target_language": "English",
            "voice_style": "Nữ tự nhiên",
            "translate_requested": "1",
        }
        result = asyncio.run(bot.execute_video_dubbing_pipeline(query, SimpleNamespace(), state, "vi"))
        assert result["ok"] is True
        assert bool(message.documents) is expect_subtitle
        assert bool(message.audio) is expect_audio
        assert result["has_subtitle"] is expect_subtitle
        assert result["has_audio"] is expect_audio


def test_quick_image_flow_prompt_before_ratio_and_pricing():
    source = bot_source_text()
    callback_source = source_between(source, "async def handle_create_media_callback", "async def cmd_tool_test_workflow_image")
    quick_entry_source = source_between(callback_source, 'if action == "quick_image":', 'if action == "qi_entry":')
    message_source = source_between(source, "async def handle_message", "TELEGRAM_STARTUP_ERROR =")

    assert "quick_image_entry_text(lang)" in quick_entry_source
    assert "quick_image_entry_keyboard(lang)" in quick_entry_source
    assert "public_image_tier_selection_text(lang)" not in quick_entry_source
    assert message_source.index("handle_quick_image_flow_pending_text(update, context)") < message_source.index("handle_public_image_prompt_pending_text(update, context)")

    entry_text = bot.quick_image_entry_text("vi")
    assert "Tạo ảnh nhanh" in entry_text
    assert "chọn prompt trước" in entry_text
    assert "chưa gọi API" in entry_text
    entry_rows = bot.quick_image_entry_keyboard("vi").inline_keyboard
    assert [button.callback_data for button in entry_rows[0]] == ["create_media|qi_suggest", "create_media|qi_refresh"]
    assert [button.callback_data for button in entry_rows[1]] == ["create_media|qi_custom", "menu|main_image"]

    first = bot.quick_image_suggestions(0, "vi")
    second = bot.quick_image_suggestions(3, "vi")
    assert len(bot.quick_image_suggestion_bank("vi")) >= 20
    assert len(first) == 3
    assert first != second
    suggestions_text = bot.quick_image_suggestions_text({"suggest_offset": 0}, "vi")
    assert "3 chủ đề gợi ý tạo ảnh" in suggestions_text
    assert "soạn prompt hoàn chỉnh" in suggestions_text
    assert first[0] in suggestions_text
    suggestion_callbacks = [
        button.callback_data
        for row in bot.quick_image_suggestions_keyboard("vi").inline_keyboard
        for button in row
    ]
    assert {"create_media|qi_pick_1", "create_media|qi_pick_2", "create_media|qi_pick_3", "create_media|qi_refresh", "create_media|qi_custom"}.issubset(set(suggestion_callbacks))

    prepared_prompt, negative_prompt = bot.quick_image_prompt_from_topic(first[0], "vi")
    rewritten_prompt, rewritten_negative = bot.quick_image_prompt_from_topic(first[0], "vi", 1)
    assert first[0] in prepared_prompt
    assert negative_prompt
    assert rewritten_prompt != prepared_prompt
    assert rewritten_negative == negative_prompt

    bot.clear_quick_image_flow("quick-image-test")
    state = bot.set_quick_image_flow(
        "quick-image-test",
        "prepared_prompt",
        selected_topic=first[0],
        prompt=prepared_prompt,
        negative_prompt=negative_prompt,
        prompt_source="suggestion",
        suggest_offset=3,
    )
    assert state["step"] == "prepared_prompt"
    assert state["prompt_source"] == "suggestion"
    assert bot.get_quick_image_flow("quick-image-test")["selected_topic"] == first[0]
    prepared_text = bot.quick_image_prepared_prompt_text(state, "vi")
    assert "Prompt ảnh đã được soạn" in prepared_text
    assert first[0] in prepared_text
    prepared_callbacks = [
        button.callback_data
        for row in bot.quick_image_prepared_prompt_keyboard("vi").inline_keyboard
        for button in row
    ]
    assert {
        "create_media|qi_choose_ratio",
        "create_media|qi_rewrite",
        "create_media|qi_topics",
        "create_media|qi_custom",
        "create_media|qi_back_suggestions",
    }.issubset(set(prepared_callbacks))

    state = bot.set_quick_image_flow("quick-image-test", "ratio")
    state = bot.set_quick_image_flow("quick-image-test", "tier", aspect_ratio="16:9")
    assert state["prompt"] == prepared_prompt
    assert state["aspect_ratio"] == "16:9"

    ratio_text = bot.quick_image_ratio_text(state, "vi")
    assert "Chọn tỉ lệ khung hình" in ratio_text
    assert first[0] in ratio_text
    ratio_rows = bot.quick_image_ratio_keyboard("vi").inline_keyboard
    ratio_callbacks = [button.callback_data for row in ratio_rows for button in row]
    assert "create_media|qi_ratio_16x9" in ratio_callbacks
    assert [button.callback_data for button in ratio_rows[-1]] == ["create_media|qi_back_prompt", "menu|main"]

    tier_text = bot.quick_image_tier_text(state, "vi")
    assert "Bạn muốn tạo ảnh chất lượng nào" in tier_text
    assert "16:9" in tier_text
    tier_rows = bot.quick_image_tier_keyboard("vi").inline_keyboard
    tier_callbacks = [button.callback_data for row in tier_rows for button in row]
    assert {
        "create_media|qi_tier_low",
        "create_media|qi_tier_standard",
        "create_media|qi_tier_standard_warranty",
        "create_media|qi_tier_high",
        "create_media|qi_tier_high_warranty",
    }.issubset(set(tier_callbacks))
    assert "create_media|qi_back_ratio" in tier_callbacks

    confirm_rows = bot.quick_image_confirm_keyboard("token-1", "vi").inline_keyboard
    assert [button.callback_data for button in confirm_rows[0]] == ["shopai|confirm|token-1", "create_media|qi_back_tier"]
    assert [button.callback_data for button in confirm_rows[-1]] == ["menu|main"]

    planning_keyboards = [
        bot.quick_image_entry_keyboard("vi"),
        bot.quick_image_suggestions_keyboard("vi"),
        bot.quick_image_prepared_prompt_keyboard("vi"),
        bot.quick_image_custom_prompt_keyboard("vi"),
        bot.quick_image_ratio_keyboard("vi"),
        bot.quick_image_tier_keyboard("vi"),
        bot.quick_image_confirm_keyboard("token-1", "vi"),
    ]
    for keyboard in planning_keyboards:
        assert all(len(row) <= 2 for row in keyboard.inline_keyboard)
        assert all("Hủy" not in button.text for row in keyboard.inline_keyboard for button in row)

    assert '"source": "quick_image_v6"' in callback_source
    assert 'set_quick_image_flow(\n            uid,\n            "prepared_prompt"' in callback_source
    assert 'if action == "qi_choose_ratio":' in callback_source
    assert 'if action == "qi_rewrite":' in callback_source
    assert "shopaikey_image_generate" not in callback_source
    assert "spend_fixed_credit_info" not in callback_source
    assert bot.clear_quick_image_flow("quick-image-test") is True


def test_image_system_v9_structured_prompt_quality_and_unavailable_tool_guards():
    product = bot.build_image_prompt(
        "chai nước hoa nam cao cấp",
        "product_photo",
        "luxury studio",
        "9:16",
        "high",
    )
    assert product["purpose"] == "product_photo"
    assert "Professional product photography" in product["prompt"]
    assert "vertical composition" in product["prompt"]
    assert "TikTok, Reels and Shorts" in product["prompt"]
    assert "premium cinematic and commercial grade" in product["prompt"]
    assert "controlled lighting" in product["prompt"]
    assert "distorted product" in product["negative_prompt"]
    assert product["suggested_ratio"] == "9:16"

    logo = bot.build_image_prompt("logo TOAN AAS màu xanh ngọc", "", "minimal", "1:1", "standard")
    assert logo["purpose"] == "logo_branding"
    assert "concept-first" in logo["prompt"]
    assert "avoid random text" in logo["prompt"]
    assert "sai chữ hoặc logo" in logo["text_logo_caution"]
    assert "misspelled brand name" in logo["negative_prompt"]

    wide = bot.build_image_prompt("banner app AI", "social_banner", "modern", "16:9", "standard")
    assert "wide composition" in wide["prompt"]
    assert "YouTube, banners and video thumbnails" in wide["prompt"]
    assert bot.build_image_prompt("tạo ảnh đẹp")["needs_clarification"] is True

    generated = bot.image_tier_prompt_for_generation("chai nước hoa nam cao cấp", "high", "9:16")
    assert "Aspect ratio 9:16" in generated
    assert "premium cinematic and commercial grade" in generated
    assert "Negative prompt:" in generated

    preview_state = {
        "selected_topic": "logo TOAN AAS màu xanh ngọc",
        "original_request": "logo TOAN AAS màu xanh ngọc",
        "prompt": logo["prompt"],
        "negative_prompt": logo["negative_prompt"],
        "image_purpose": logo["purpose"],
        "purpose_label": logo["purpose_label"],
        "suggested_ratio": logo["suggested_ratio"],
        "text_logo_caution": logo["text_logo_caution"],
    }
    preview = bot.quick_image_prepared_prompt_text(preview_state, "vi")
    assert "Prompt ảnh đã được soạn và tối ưu" in preview
    assert "Mục tiêu:" in preview
    assert "Negative prompt:" in preview
    assert "Tỉ lệ đề xuất:" in preview
    assert "AI tạo ảnh có thể sai chữ hoặc logo" in preview
    assert "chưa gọi API và chưa trừ Xu" in preview

    confirm = bot.public_image_confirm_text("high", logo["prompt"], 1000, "vi", "1:1")
    assert "Kiểm soát chất lượng" in confirm
    assert "key visual" in confirm

    source = bot_source_text()
    callback_source = source_between(source, "async def handle_image_tools_callback", "async def handle_image_menu_pending_text")
    custom_pending_source = source_between(source, "async def handle_quick_image_flow_pending_text", "async def handle_quick_media_pending_text")
    assert '"prepared_prompt"' in custom_pending_source
    assert "build_image_prompt(" in custom_pending_source
    assert "quick_image_prepared_prompt_text" in custom_pending_source
    assert "quick_image_ratio_text" not in custom_pending_source

    for guard_text in (
        bot.image_manual_edit_guard_text("vi"),
        bot.image_edit_ai_guard_text("vi"),
        bot.image_upscale_ai_guard_text("vi"),
    ):
        assert "chưa xử lý ảnh" in guard_text
        assert "chưa gọi provider" in guard_text
        assert "chưa trừ Xu" in guard_text
    assert "shopaikey_image_generate(" not in callback_source
    assert "spend_fixed_credit_info(" not in callback_source


def test_image_ux_v8_manual_and_ai_edit_confirmation_guards():
    source = bot_source_text()
    callback_source = source_between(source, "async def handle_image_tools_callback", "async def handle_image_menu_pending_text")
    pending_source = source_between(source, "async def handle_image_menu_pending_text", "async def handle_image_menu_pending_photo")

    manual_request = bot.image_manual_edit_request_text("text", "vi")
    assert "Mô tả yêu cầu chỉnh sửa" in manual_request
    assert "chưa xử lý ảnh" in manual_request
    manual_request_callbacks = [
        button.callback_data
        for row in bot.image_manual_edit_request_keyboard("vi").inline_keyboard
        for button in row
    ]
    assert manual_request_callbacks == ["imgtool|edit_manual", "menu|main"]

    manual_state = {
        "file_id": "image-file",
        "manual_action": "blur",
        "edit_request": "Che mờ biển số ở góc phải",
    }
    manual_confirm = bot.image_manual_edit_confirm_text(manual_state, "vi")
    assert "Xác nhận yêu cầu chỉnh sửa thủ công" in manual_confirm
    assert "Che mờ biển số" in manual_confirm
    manual_confirm_callbacks = [
        button.callback_data
        for row in bot.image_manual_edit_confirm_keyboard("vi").inline_keyboard
        for button in row
    ]
    assert {"imgtool|edit_manual_confirm", "imgtool|edit_manual_change", "imgtool|edit_manual", "menu|main"}.issubset(set(manual_confirm_callbacks))
    assert "image_edit_manual_request" in bot.IMAGE_MENU_PENDING_ACTIONS
    assert "image_edit_manual_confirm" in bot.IMAGE_MENU_PENDING_ACTIONS
    assert 'if action == "image_edit_manual_request":' in pending_source
    assert 'if action == "edit_manual_confirm":' in callback_source
    assert "shopaikey_image_generate(" not in callback_source

    ai_callbacks = [
        button.callback_data
        for row in bot.image_edit_result_keyboard("vi").inline_keyboard
        for button in row
    ]
    assert "imgtool|edit_ai" in ai_callbacks
    assert "imgtool|edit_request_custom" in ai_callbacks
    assert "imgtool|edit_back_suggestions" in ai_callbacks
    assert all("cancel" not in callback.lower() for callback in ai_callbacks)
    ai_guard_callbacks = [
        button.callback_data
        for row in bot.image_edit_ai_guard_keyboard("vi").inline_keyboard
        for button in row
    ]
    assert {"imgtool|edit_back_result", "imgtool|edit_ai_menu", "menu|main"}.issubset(set(ai_guard_callbacks))
    assert 'if action == "edit_back_suggestions":' in callback_source
    assert "image_edit_ai_guard_keyboard(lang)" in bot_source_text()
    assert "chưa gọi API và chưa trừ Xu" in bot.image_edit_ai_guard_text("vi")


def test_global_ux_polish_v6_keyboard_navigation_and_storage_policy():
    def rows(keyboard):
        return [[button.text for button in row] for row in keyboard.inline_keyboard]

    def callbacks(keyboard):
        return [[button.callback_data for button in row] for row in keyboard.inline_keyboard]

    polished_keyboards = [
        bot.main_image_keyboard("vi"),
        bot.image_menu_child_keyboard("vi"),
        bot.image_prompt_goal_keyboard("vi"),
        bot.image_prompt_ratio_keyboard("vi"),
        bot.image_prompt_output_keyboard("vi"),
        bot.image_prompt_tier_keyboard("vi"),
        bot.image_prompt_variants_keyboard("vi"),
        bot.image_prompt_save_choice_keyboard("vi"),
        bot.image_edit_start_keyboard("vi"),
        bot.image_edit_choice_keyboard("vi"),
        bot.image_edit_tier_keyboard("vi"),
        bot.image_resize_start_keyboard("vi"),
        bot.image_resize_choice_keyboard("vi"),
        bot.image_resize_method_keyboard("vi"),
        bot.image_resize_pixels_keyboard("vi"),
        bot.main_video_keyboard("vi"),
        bot.video_ai_true_keyboard("vi"),
        bot.frame_video_collect_keyboard(),
        bot.frame_video_planning_keyboard("vi"),
        bot.frame_video_ratio_keyboard(),
        bot.frame_video_duration_keyboard(),
        bot.frame_video_effect_keyboard(),
        bot.frame_video_music_keyboard(),
        bot.frame_video_confirm_keyboard(),
        bot.frame_video_success_keyboard(),
        bot.main_memory_keyboard("vi"),
        bot.main_docs_keyboard("vi"),
        bot.create_media_menu_keyboard("vi"),
        bot.main_topup_keyboard("vi"),
        bot.menu_nav_keyboard("admin", True),
        bot.freeze_queue_keyboard(),
        bot.freeze_status_keyboard(),
        bot.smoke_test_menu_keyboard(),
        bot.smoke_action_keyboard(),
        bot.admin_provider_keyboard(),
    ]
    assert all(all(len(row) <= 2 for row in keyboard.inline_keyboard) for keyboard in polished_keyboards)

    assert callbacks(bot.main_image_keyboard("vi"))[-1] == ["menu|main", "menu|main"]
    assert callbacks(bot.image_menu_child_keyboard("vi"))[-1] == ["menu|main_image", "menu|main"]
    assert callbacks(bot.image_prompt_goal_keyboard("vi"))[-1] == ["imgtool|prompt_back_wait_image", "menu|main"]
    assert callbacks(bot.image_prompt_ratio_keyboard("vi"))[-1] == ["imgtool|prompt_back_style", "menu|main"]
    assert callbacks(bot.image_prompt_output_keyboard("vi"))[-1] == ["imgtool|prompt_back_ratio", "menu|main"]
    assert callbacks(bot.main_docs_keyboard("vi"))[-1] == ["menu|main_memory", "menu|main"]
    assert callbacks(bot.menu_nav_keyboard("admin", True))[-1] == ["menu|main", "menu|main"]
    assert callbacks(bot.freeze_queue_keyboard())[-1] == ["menu|admin", "menu|main"]
    assert callbacks(bot.smoke_test_menu_keyboard())[-1] == ["menu|admin", "menu|main"]

    planning_keyboards = [
        bot.main_image_keyboard("vi"),
        bot.image_prompt_goal_keyboard("vi"),
        bot.image_prompt_ratio_keyboard("vi"),
        bot.image_prompt_output_keyboard("vi"),
        bot.image_prompt_variants_keyboard("vi"),
        bot.image_prompt_save_choice_keyboard("vi"),
        bot.image_edit_start_keyboard("vi"),
        bot.image_edit_choice_keyboard("vi"),
        bot.image_resize_start_keyboard("vi"),
        bot.image_resize_choice_keyboard("vi"),
        bot.image_resize_method_keyboard("vi"),
        bot.image_resize_pixels_keyboard("vi"),
        bot.create_media_menu_keyboard("vi"),
    ]
    assert all(
        "Hủy" not in button.text
        for keyboard in planning_keyboards
        for row in keyboard.inline_keyboard
        for button in row
    )
    image_edit_result_labels = [button.text for row in bot.image_edit_result_keyboard("vi").inline_keyboard for button in row]
    assert "❌ Hủy" not in image_edit_result_labels
    assert "🔙 Quay lại" in image_edit_result_labels

    memory_rows = rows(bot.main_memory_keyboard("vi"))
    assert memory_rows[:5] == [
        ["📝 Tạo ghi chú", "📋 Ghi chú đã lưu"],
        ["⏰ Nhắc hẹn", "📄 Lưu tài liệu"],
        ["🔍 Tìm ghi chú", "🗑 Xóa ghi chú"],
        ["💾 Dung lượng của tôi", "📦 Mua thêm dung lượng"],
        ["🧹 Dọn file cũ", "🧰 Công cụ PDF / Word"],
    ]
    assert memory_rows[-1] == ["⬅️ Quay lại", "🏠 Menu chính"]
    storage_text = "\n".join(bot.storage_addon_lines())
    assert "+50MB/tháng: 10.000đ" in storage_text
    assert "+100MB/tháng: 20.000đ" in storage_text
    assert "+250MB/tháng: 50.000đ" in storage_text
    assert "+500MB/tháng: 100.000đ" in storage_text
    assert bot.TOTAL_FREE_STORAGE_MB == 50


def test_image_notes_voice_music_guided_flow_v1(monkeypatch):
    source = bot_source_text()
    message_source = source_between(source, "async def handle_message", "TELEGRAM_STARTUP_ERROR =")
    menu_source = source_between(source, "async def handle_menu_callback", "async def handle_free_hub_callback")

    assert bot.IMAGE_STANDARD_WARRANTY_COST_XU == 300
    assert bot.IMAGE_HIGH_WARRANTY_COST_XU == 600
    assert bot.image_tier_cost_xu("standard_warranty") == 300
    assert bot.image_tier_cost_xu("high_warranty") == 600

    memory_callbacks = [button.callback_data for row in bot.main_memory_keyboard("vi").inline_keyboard for button in row]
    assert {"memory|create", "memory|list", "memory|search", "memory|delete_start"}.issubset(set(memory_callbacks))
    assert "menu|internal_archive" not in memory_callbacks
    monkeypatch.setattr(bot, "ADMIN_ID", "123456")
    monkeypatch.setattr(bot, "ADMIN_IDS", {"123456"})
    admin_memory_callbacks = [button.callback_data for row in bot.main_memory_keyboard("vi", 123456).inline_keyboard for button in row]
    assert "menu|internal_archive" in admin_memory_callbacks
    assert "Copy lệnh" not in bot.menu_hint_text("hint_note")[1]
    assert "Copy lệnh" not in bot.menu_hint_text("hint_search_note")[1]
    assert 'CallbackQueryHandler(handle_memory_callback, pattern=r"^memory\\|")' in source
    assert "handle_memory_pending_text(update, context)" in message_source
    assert "set_memory_guided_pending(query.from_user.id, \"create\")" in menu_source
    assert "set_memory_guided_pending(query.from_user.id, \"search\")" in menu_source
    assert "memory_format_note_item_with_time" in source

    music_labels = [button.text for row in bot.music_tools_keyboard("vi").inline_keyboard for button in row]
    assert music_labels[:2] == ["🎙 Giọng đọc", "🎵 Nhạc"]
    assert "📁 Kho voice" not in music_labels
    assert "🎼 Kho nhạc / SFX" not in music_labels
    assert "📁 Media âm thanh" not in music_labels
    assert "🗣 Chọn giọng" not in music_labels
    music_callbacks = [button.callback_data for row in bot.music_tools_keyboard("vi").inline_keyboard for button in row]
    assert "music_quick|showroom|voice_hub" in music_callbacks
    assert "music_quick|showroom|music_hub" in music_callbacks
    assert "music_quick|showroom|voice_profiles" not in music_callbacks
    assert "music_quick|showroom|ai_music" not in music_callbacks
    assert "music_quick|showroom|media" not in music_callbacks
    assert "music_quick|voice_pick" not in music_callbacks

    voice_hub_labels = [button.text for row in bot.voice_hub_keyboard("vi").inline_keyboard for button in row]
    for label in ["✍️ Văn bản thành giọng nói", "🎧 Giọng nói thành văn bản", "👩 Giọng nữ", "👨 Giọng nam", "📂 Kho voice", "🎙 Tạo voice riêng"]:
        assert label in voice_hub_labels
    for label in ["🎵 Tạo nhạc nền", "🎼 Kho nhạc / SFX", "📁 Media âm thanh"]:
        assert label not in voice_hub_labels
    for label in ["👩 Demo giọng nữ" + " miễn phí", "👨 Demo giọng nam" + " miễn phí", "🎙 Nhập chữ" + " để đọc thử"]:
        assert label not in voice_hub_labels
    assert "🚫 Không thêm giọng" not in voice_hub_labels
    music_hub_labels = [button.text for row in bot.music_hub_keyboard("vi").inline_keyboard for button in row]
    for label in ["🎵 Tạo nhạc nền", "🎤 Bài hát có lời", "📂 Kho nhạc", "🎚 Cắt/ghép nhạc"]:
        assert label in music_hub_labels
    for label in ["📝 Tạo prompt nhạc", "✨ Tạo nhạc AI"]:
        assert label not in music_hub_labels
    assert "🚫 Không thêm nhạc" not in music_hub_labels

    prompt_entry_callbacks = [button.callback_data for row in bot.music_prompt_entry_keyboard("vi").inline_keyboard for button in row]
    assert {"music_quick|showroom|prompt_seed", "music_quick|showroom|prompt_seed_more", "music_quick|showroom|prompt_custom", "music_quick|showroom|ai_music"}.issubset(set(prompt_entry_callbacks))

    voice_entry_callbacks = [button.callback_data for row in bot.voice_prompt_entry_keyboard("vi").inline_keyboard for button in row]
    assert {"music_quick|showroom|voice_seed", "music_quick|showroom|voice_custom", "music_quick|showroom|voice_clone", "music_quick|showroom|voice_profiles"}.issubset(set(voice_entry_callbacks))

    suggestions = bot.music_prompt_suggestions("video review máy xay sinh tố mini", 0, "vi")
    next_suggestions = bot.music_prompt_suggestions("video review máy xay sinh tố mini", 3, "vi")
    assert len(suggestions) == 3
    assert suggestions != next_suggestions
    suggestions_text = bot.music_prompt_suggestions_text("video review máy xay sinh tố mini", 0, "vi")
    assert "3 prompt nhạc gợi ý" in suggestions_text
    assert "Prompt:" in suggestions_text
    lyrics_desc = bot.music_ai_default_description("lyrics", "vi")
    lyrics_suggestions = bot.music_prompt_suggestions(lyrics_desc, 0, "vi", "lyrics")
    assert len(lyrics_suggestions) == 3
    assert any("no vocal" not in str(item.get("vocal") or "").lower() for item in lyrics_suggestions)
    assert "original lyrics" in bot.music_prompt_from_suggestion(lyrics_suggestions[0])
    melody_text = bot.music_prompt_suggestions_text(bot.music_ai_default_description("melody", "vi"), 0, "vi", "melody")
    assert "giai điệu" in melody_text.lower() or "melody" in melody_text.lower()
    prompt_callbacks = [button.callback_data for row in bot.music_prompt_result_keyboard("vi").inline_keyboard for button in row]
    assert {"music_quick|showroom|prompt_choose_1", "music_quick|showroom|prompt_more", "music_quick|showroom|save_prompt", "music_quick|showroom|find_from_prompt", "music_quick|showroom|music_ai_guard"}.issubset(set(prompt_callbacks))

    voice_suggestions = bot.voice_style_suggestions("Nước hoa nam cao cấp giúp tự tin hơn", 0, "vi")
    next_voice_suggestions = bot.voice_style_suggestions("Nước hoa nam cao cấp giúp tự tin hơn", 3, "vi")
    assert len(voice_suggestions) == 3
    assert voice_suggestions != next_voice_suggestions
    voice_text = bot.voice_style_suggestions_text("Nước hoa nam cao cấp giúp tự tin hơn", "vi", 0)
    assert "Chọn kiểu giọng" in voice_text
    voice_callbacks = [button.callback_data for row in bot.voice_style_keyboard("vi").inline_keyboard for button in row]
    assert {"music_quick|showroom|voice_style_1", "music_quick|showroom|voice_style_2", "music_quick|showroom|voice_style_3", "music_quick|showroom|voice_custom"}.issubset(set(voice_callbacks))
    assert "music_quick|showroom|voice_more" not in voice_callbacks
    assert "music_quick|showroom|voice_tts_guard" not in voice_callbacks
    assert "music_quick|showroom|voice_video" not in voice_callbacks

    merge_music_callbacks = [button.callback_data for row in bot.music_merge_keyboard("music", "vi").inline_keyboard for button in row]
    assert {"music_quick|showroom|merge_music_video", "music_quick|showroom|merge_music_audio", "music_quick|showroom|merge_music_run", "music_quick|showroom|ai_music"}.issubset(set(merge_music_callbacks))
    merge_voice_callbacks = [button.callback_data for row in bot.music_merge_keyboard("voice", "vi").inline_keyboard for button in row]
    assert {"music_quick|showroom|merge_voice_video", "music_quick|showroom|merge_voice_audio", "music_quick|showroom|merge_voice_run"}.issubset(set(merge_voice_callbacks))

    for keyboard in [bot.music_library_quick_keyboard("vi"), bot.sfx_library_quick_keyboard("vi"), bot.media_library_quick_keyboard("vi")]:
        callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
        assert any(callback.startswith(("music_quick|showroom|", "sfx_quick|showroom|", "media_quick|showroom|")) for callback in callbacks)
        assert "menu|main_music" not in callbacks
        assert "menu|main" in callbacks
    assert "handle_music_guided_pending_text(update, context)" in message_source
    assert "handle_music_guided_pending_media(update, context)" in source


def test_music_ai_buttons_open_suggestions_without_waiting_for_text():
    replies = []
    uid = 88123
    bot.clear_music_guided_pending(uid)
    bot.USER_PENDING.pop(bot.music_guided_result_key(uid), None)

    class FakeMessage:
        async def reply_text(self, text, parse_mode=None, reply_markup=None, disable_web_page_preview=None):
            replies.append({
                "text": str(text),
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
                "disable_web_page_preview": disable_web_page_preview,
            })
            return SimpleNamespace(text=text, reply_markup=reply_markup)

    class FakeQuery:
        def __init__(self, data):
            self.data = data
            self.message = FakeMessage()

        async def answer(self, *args, **kwargs):
            return None

    async def press(data):
        await bot.handle_music_quick_callback(
            SimpleNamespace(callback_query=FakeQuery(data), effective_user=SimpleNamespace(id=uid)),
            SimpleNamespace(),
        )

    asyncio.run(press("music_quick|music_ai_lyrics"))
    assert replies
    assert "3 prompt nhạc gợi ý" in replies[-1]["text"]
    assert "Nhạc có lời" in replies[-1]["text"]
    assert bot.get_music_guided_pending(uid) is None
    result = bot.get_music_guided_result(uid) or {}
    assert result.get("music_ai_kind") == "lyrics"
    assert any("no vocal" not in str(item.get("vocal") or "").lower() for item in result.get("suggestions") or [])

    asyncio.run(press("music_quick|music_ai_background"))
    result = bot.get_music_guided_result(uid) or {}
    assert result.get("music_ai_kind") == "background"
    assert all("no vocal" in str(item.get("vocal") or "").lower() for item in result.get("suggestions") or [])


def test_document_pdf_tools_v6_guided_upload_confirm_flow():
    source = bot_source_text()
    menu_source = source_between(source, "async def handle_menu_callback", "async def handle_feedback_callback")
    photo_source = source_between(source, "async def handle_photo", "async def handle_document_cache_only")
    document_source = source_between(source, "async def handle_document_cache_only", "async def handle_media")
    message_source = source_between(source, "async def handle_message", "TELEGRAM_STARTUP_ERROR =")

    assert 'CallbackQueryHandler(handle_doc_tool_callback, pattern=r"^docflow\\|")' in source
    assert "DOC_TOOL_MENU_ACTIONS" in source
    assert "start_doc_tool_flow(query, query.from_user.id, DOC_TOOL_MENU_ACTIONS[action], lang)" in menu_source
    assert "handle_doc_tool_pending_upload(update, context)" in photo_source
    assert photo_source.index("handle_doc_tool_pending_upload(update, context)") < photo_source.index("handle_image_menu_pending_photo(update, context)")
    assert "handle_doc_tool_pending_upload(update, context)" in document_source
    assert document_source.index("handle_doc_tool_pending_upload(update, context)") < document_source.index("handle_image_menu_pending_document(update, context)")
    assert "handle_doc_tool_pending_text(update, context)" in message_source
    assert message_source.index("handle_doc_tool_pending_text(update, context)") < message_source.index("handle_storyboard_pending_text(update, context)")

    docs_callbacks = [button.callback_data for row in bot.main_docs_keyboard("vi").inline_keyboard for button in row]
    assert "menu|hint_doc_pdf_to_word" in docs_callbacks
    assert "menu|hint_doc_image_to_pdf" in docs_callbacks
    assert "menu|hint_doc_compress_pdf" in docs_callbacks
    assert "menu|hint_doc_split_pdf" in docs_callbacks
    assert "menu|hint_doc_merge_pdf" in docs_callbacks

    memory_callbacks = [button.callback_data for row in bot.main_memory_keyboard("vi").inline_keyboard for button in row]
    assert "menu|hint_doc_save_document" in memory_callbacks
    assert "menu|doc_tools" not in memory_callbacks
    assert "menu|main_docs" in memory_callbacks

    for text in [
        bot.menu_text_main_docs(),
        bot.menu_text_main_docs_i18n("en"),
        bot.doc_tools_menu_text(),
        bot.doc_tools_menu_text_i18n("en"),
    ]:
        assert "/image_to_pdf" not in text
        assert "/pdf_to_word" not in text
        assert "/compress_pdf" not in text
        assert "/split_pdf" not in text
        assert "/merge_pdf" not in text
        assert "xác nhận" in text.lower() or "confirm" in text.lower()

    image_state = bot.set_doc_tool_pending("u-doc", "image_to_pdf")
    assert image_state["doc_tool_current"] == "image_to_pdf"
    assert image_state["doc_tool_expected_type"] == "image"
    assert image_state["doc_tool_file_count"] == 0
    assert image_state["doc_tool_max_files"] == bot.DOC_TOOL_MAX_FILES
    assert image_state["doc_tool_user_id"] == "u-doc"
    assert "doc_tool_options" in image_state
    assert "doc_tool_previous_step" in image_state
    assert image_state["doc_menu_origin"] == "pdf_tools"
    assert image_state["doc_current_menu"] == "pdf_tools"
    assert image_state["doc_current_tool"] == "image_to_pdf"
    assert image_state["doc_previous_menu"] == "main_docs"
    assert image_state["doc_expected_type"] == "image"
    assert bot.doc_tool_parent_action(image_state) == "main_docs"
    assert "Công cụ PDF / Word" in bot.doc_tool_parent_label(image_state, lang="vi")
    assert "Ảnh sang PDF" in bot.doc_tool_start_text("image_to_pdf")
    assert "gửi từng ảnh" in bot.doc_tool_start_text("image_to_pdf")
    start_labels = [button.text for row in bot.doc_tool_start_keyboard("image_to_pdf").inline_keyboard for button in row]
    assert "➕ Tôi sẽ gửi ảnh" in start_labels
    assert "⬅️ Công cụ PDF / Word" in start_labels and "🏠 Menu chính" in start_labels

    image_info = {"kind": "photo", "file_id": "photo-file", "file_name": "a.jpg", "mime_type": "image/jpeg", "file_size": 1024}
    pdf_info = {"kind": "document", "file_id": "pdf-file", "file_name": "a.pdf", "mime_type": "application/pdf", "file_size": 2048}
    assert bot.doc_tool_file_matches(image_state, image_info) is True
    assert bot.doc_tool_file_matches(image_state, pdf_info) is False
    assert "Công cụ này cần ảnh" in bot.doc_tool_wrong_file_text(image_state, pdf_info)

    image_state["doc_tool_files"] = [image_info, {**image_info, "file_name": "b.jpg"}]
    image_state["doc_tool_file_count"] = 2
    received_text = bot.doc_tool_received_text(image_state)
    assert "Số ảnh hiện có" in received_text
    assert "✅ Tạo PDF" in str(bot.doc_tool_after_file_keyboard(image_state).inline_keyboard)
    confirm_text = bot.doc_tool_confirm_text(image_state)
    assert "Phí: <b>0 Xu</b>" in confirm_text
    assert "Local engine" in confirm_text
    assert "a.jpg" in confirm_text and "b.jpg" in confirm_text
    confirm_callbacks = [button.callback_data for row in bot.doc_tool_confirm_keyboard().inline_keyboard for button in row]
    assert "docflow|run" in confirm_callbacks
    assert "docflow|reset_files" in confirm_callbacks
    assert "docflow|back" in confirm_callbacks

    merge_state = bot.set_doc_tool_pending("u-doc", "merge_pdf")
    merge_state["doc_tool_files"] = [pdf_info, {**pdf_info, "file_name": "b.pdf"}]
    assert "Thứ tự" in bot.doc_tool_confirm_text(merge_state)
    split_state = bot.set_doc_tool_pending("u-doc", "split_pdf")
    split_state["doc_tool_files"] = [pdf_info]
    split_state["awaiting_page_spec"] = "1"
    assert bot.doc_tool_after_file_keyboard(split_state).inline_keyboard[0][0].callback_data == "docflow|ask_pages"
    save_state = bot.set_doc_tool_pending("u-doc", "save_document")
    assert save_state["doc_tool_expected_type"] == "any"
    assert save_state["doc_menu_origin"] == "notes_root"
    assert save_state["doc_previous_menu"] == "main_memory"
    assert bot.doc_tool_parent_action(save_state) == "main_memory"
    assert "Ghi chú / Tài liệu" in bot.doc_tool_parent_label(save_state, lang="vi")
    assert "Lưu tài liệu" in bot.doc_tool_start_text("save_document")
    save_start_callbacks = [
        button.callback_data
        for row in bot.doc_tool_start_keyboard("save_document", "vi", save_state).inline_keyboard
        for button in row
    ]
    assert save_start_callbacks == [
        "docflow|send_more",
        "menu|memory_storage_status",
        "docflow|back",
        "menu|main",
    ]
    callback_source = source_between(source, "async def handle_doc_tool_callback", "async def cmd_doc_tools")
    assert 'if parent_action == "main_memory":' in callback_source
    assert "menu_text_main_memory_i18n(lang)" in callback_source
    assert "menu_text_main_docs_i18n(lang)" in callback_source
    bot.clear_doc_tool_pending("u-doc")


def test_image_tools_v5_unified_hotfix_state_resize_and_guards():
    source = bot_source_text()
    callback_source = source_between(source, "async def handle_image_tools_callback", "async def handle_image_menu_pending_text")
    pending_text_source = source_between(source, "async def handle_image_menu_pending_text", "async def handle_image_menu_pending_photo")
    resize_source = source_between(source, "async def send_local_resized_image", "def image_upscale_ai_guard_text")
    document_source = source_between(source, "async def handle_document_cache_only", "async def handle_media")

    base_state = {
        "goal_code": "product",
        "subject": "chai nước hoa nam cao cấp",
        "style": "Luxury showroom",
        "ratio": "16:9",
    }
    prompt_text, prompt_value = bot.build_image_prompt_output(base_state)
    payload = bot.image_prompt_result_payload(base_state, prompt_value)
    assert payload["ratio"] == "16:9"
    assert payload["current_prompt"] == prompt_value
    assert payload["detail_prompt"] == prompt_value
    assert payload["image_prompt_current_prompt"] == prompt_value
    assert payload["image_prompt_selected_ratio"] == "16:9"
    assert payload["image_prompt_subject"] == "chai nước hoa nam cao cấp"
    assert "Tỷ lệ:</b> 16:9" in prompt_text
    changed_ratio = bot.image_prompt_state_with_ratio(payload, "9:16")
    assert changed_ratio["ratio"] == "9:16"
    assert "9:16" in changed_ratio["current_prompt"]
    assert "16:9" not in changed_ratio["current_prompt"]

    prompt_callbacks = [
        button.callback_data
        for row in bot.image_prompt_output_keyboard("vi").inline_keyboard
        for button in row
    ]
    assert "imgtool|prompt_use" in prompt_callbacks
    assert "imgtool|prompt_change_ratio" in prompt_callbacks
    ratio_callbacks = [
        button.callback_data
        for row in bot.image_prompt_ratio_keyboard("vi").inline_keyboard
        for button in row
    ]
    assert "imgtool|prompt_ratio|3x4" in ratio_callbacks
    assert "imgtool|prompt_ratio|3x2" not in ratio_callbacks
    assert "imgtool|prompt_ratio|4x3" in ratio_callbacks

    variants = bot.image_prompt_variants(payload)
    assert len(variants) == 3
    assert all("chai nước hoa nam cao cấp" in item for item in variants)
    variant_callbacks = [
        button.callback_data
        for row in bot.image_prompt_variants_keyboard("vi").inline_keyboard
        for button in row
    ]
    assert variant_callbacks[:3] == [
        "imgtool|prompt_variant_select|1",
        "imgtool|prompt_variant_select|2",
        "imgtool|prompt_variant_select|3",
    ]
    assert "selected_ratio" in callback_source
    assert "show_image_prompt_confirmation(query, uid, tier, prompt, selected_ratio" in callback_source
    assert "set_media_aspect_pending(uid, \"image\", tier, prompt)" in callback_source
    assert "prompt_save_variant" in callback_source

    edit_ready = bot.image_edit_ready_text({
        "file_id": "photo-file",
        "edit_type": "background_color",
        "edit_request": "Nền trắng studio sạch đẹp",
        "selected_variant": "Phương án 1 — An toàn, giữ ảnh tự nhiên",
    })
    assert "Xác nhận chỉnh sửa AI" in edit_ready
    assert "Provider:" in edit_ready
    assert "Chỉ tạo prompt sửa ảnh" not in edit_ready
    options = bot.image_edit_option_variants("background_color", "Nền trắng studio sạch đẹp")
    assert len(options) == 3
    options_text = bot.image_edit_options_text({"edit_type": "background_color", "edit_request": "Nền trắng studio sạch đẹp", "variants": options})
    assert "3 phương án chỉnh sửa AI" in options_text
    assert "Phương án 1" in options_text
    edit_callbacks = [
        button.callback_data
        for row in bot.image_edit_result_keyboard("vi").inline_keyboard
        for button in row
    ]
    assert "imgtool|edit_ai" in edit_callbacks
    assert "imgtool|edit_request_custom" in edit_callbacks
    assert "imgtool|edit_prompt_output" not in edit_callbacks
    assert "imgtool|edit_create_new" not in edit_callbacks
    assert "imgtool|edit_save" not in edit_callbacks
    assert "chưa gọi API và chưa trừ Xu" in bot.image_edit_ai_guard_text("vi")
    readiness = bot.get_image_ai_edit_readiness()
    assert {"ready", "provider", "model", "endpoint", "reason"}.issubset(set(readiness))
    run_edit_source = source_between(source, "async def run_image_ai_edit_from_state", "def image_edit_create_new_text")
    assert "if is_admin_user(uid):" in run_edit_source
    assert "Lý do kỹ thuật:" in run_edit_source
    public_guard_branch = run_edit_source[
        run_edit_source.index("else:"):
        run_edit_source.index("await safe_edit_query_message")
    ]
    assert "KEY4U_" not in public_guard_branch
    assert "ENABLE_OPENAI_IMAGE_EDIT" not in public_guard_branch
    assert "Lý do:" not in public_guard_branch
    assert "không phải sửa trực tiếp ảnh gốc" in bot.image_edit_create_new_text({}, "vi")
    assert "image_edit_prompt_ready" in bot.IMAGE_MENU_PENDING_ACTIONS
    assert "image_edit_option_ready" in bot.IMAGE_MENU_PENDING_ACTIONS
    assert "image_edit_waiting_action" in bot.IMAGE_MENU_PENDING_ACTIONS
    assert 'action in {"image_edit_request_custom", "image_edit_prompt_ready", "image_edit_waiting_action"}' in pending_text_source
    assert "image_edit_options_text(state, lang)" in pending_text_source
    assert "shopaikey_image_generate(" not in callback_source

    resize_labels = [
        button.text
        for row in bot.image_resize_choice_keyboard("vi").inline_keyboard
        for button in row
    ]
    assert "✂️ Cắt / đổi tỉ lệ" in resize_labels
    assert "📐 Resize pixel" in resize_labels
    assert "🔤 Thêm chữ / logo" in resize_labels
    assert "🎨 Công thức màu" in resize_labels
    assert "✨ Chỉnh sửa AI" not in resize_labels
    assert "✨ Nâng chất lượng AI" in resize_labels
    assert "✍️ Nhập yêu cầu riêng" in resize_labels
    assert "🎬 Chuẩn bị ảnh cho video" not in resize_labels
    assert "✨ Biến đổi tỉ lệ bằng AI" not in resize_labels
    method_labels = [
        button.text
        for row in bot.image_resize_method_keyboard("vi").inline_keyboard
        for button in row
    ]
    assert method_labels[0] == "🌫 Nền mờ, không cắt chủ thể"
    assert "chưa gọi API và chưa trừ Xu" in bot.image_aspect_ai_guard_text("vi")
    assert "image_action_waiting_text" in resize_source
    assert "acquire_image_action_lock" in resize_source
    assert "release_image_action_lock" in resize_source
    assert "handle_image_menu_pending_document(update, context)" in document_source

    bot.IMAGE_ACTION_LOCKS.clear()
    assert bot.acquire_image_action_lock("u-image", "resize_ratio", "file:16:9:blur") is True
    assert bot.acquire_image_action_lock("u-image", "resize_ratio", "file:16:9:blur") is False
    bot.release_image_action_lock("u-image", "resize_ratio", "file:16:9:blur")
    assert bot.acquire_image_action_lock("u-image", "resize_ratio", "file:16:9:blur") is True
    bot.release_image_action_lock("u-image", "resize_ratio", "file:16:9:blur")

    if bot.Image is not None:
        source_image = bot.Image.new("RGBA", (640, 480), (10, 120, 200, 180))
        source_buffer = io.BytesIO()
        source_image.save(source_buffer, format="WEBP")
        for ratio, expected_size in {
            "16:9": (1920, 1080),
            "9:16": (1080, 1920),
            "1:1": (1024, 1024),
            "4:5": (1080, 1350),
        }.items():
            ok, output, size_text, method = bot.process_image_local_resize_bytes(
                source_buffer.getvalue(),
                ratio,
                "blur",
            )
            assert ok is True
            assert size_text == f"{expected_size[0]}x{expected_size[1]}"
            assert method == "blur"
            with bot.Image.open(io.BytesIO(output)) as rendered:
                assert rendered.size == expected_size
                assert rendered.mode == "RGB"


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


def test_video_system_v9_intent_parser_and_flow_specific_builders():
    request = (
        "tạo video sản phẩm nước hoa cho TikTok, camera zoom nhẹ vào chai, "
        "sản phẩm xoay 360, ánh sáng luxury, giữ logo, không thêm chữ"
    )
    intent = bot.parse_video_user_intent(request, "promptvideo", {})
    assert intent["task_type"] == "prompt_to_video"
    assert intent["target_subject"] == "physical product"
    assert intent["platform"] == "tiktok"
    assert intent["ratio"] == "9:16"
    assert "slow push-in" in intent["camera_motion"]
    assert "product rotates slowly" in intent["subject_motion"]
    assert "logo" in " ".join(intent["must_keep"]).lower()
    assert "random or readable generated text" in intent["must_avoid"]

    prompt_package = bot.build_video_prompt(intent)
    prompt = prompt_package["prompt"]
    assert "nước hoa" in prompt
    assert "slow push-in" in prompt
    assert "product rotates slowly" in prompt
    assert "luxury controlled lighting" in prompt
    assert "aspect ratio 9:16" in prompt
    assert "no readable UI text" in prompt
    assert bot.validate_video_prompt_against_user_request(request, prompt, intent)["ok"] is True
    assert "Video AI may slightly distort" in prompt_package["caution"]

    image_intent = bot.parse_video_user_intent(
        "làm mượt hơn, chuyển động nhẹ, giữ sản phẩm và không méo logo",
        "imagevideo",
        {"ratio": "9:16"},
    )
    image_package = bot.build_video_prompt(image_intent)
    assert "Use the uploaded image as the visual reference" in image_package["prompt"]
    assert "Preserve the main subject" in image_package["prompt"]
    assert "warped source image" in image_package["negative_prompt"]
    image_pending = bot.public_video_pending_payload_from_package(
        "low",
        {"source": "image_to_video", "video_prompt": "animate this perfume product with subtle motion"},
        "9:16",
    )
    assert "Use the uploaded image as the visual reference" in image_pending["prompt"]

    reference_package = bot.build_video_prompt(
        bot.parse_video_user_intent("quảng cáo app AI cho chủ shop", "videoref", {"ratio": "16:9"})
    )
    assert "reference video structure" in reference_package["prompt"]
    assert "Do not copy the original video exactly" in reference_package["prompt"]

    trend_package = bot.build_video_prompt(
        bot.parse_video_user_intent("video trend nước hoa nam cho Reels", "trend", {})
    )
    assert "opening 1-3 seconds" in trend_package["prompt"]
    assert "soft CTA" in trend_package["prompt"]

    change_scene_package = bot.build_video_prompt(
        bot.parse_video_user_intent(
            "giữ người trong video, đổi nền thành thành phố tương lai, camera orbit nhẹ, không méo mặt",
            "selfscene",
            {},
        )
    )
    assert "Keep the original person or product identity stable" in change_scene_package["prompt"]
    assert "thành phố tương lai" in change_scene_package["prompt"]
    assert "orbit shot" in change_scene_package["prompt"]
    assert "distorted face" in change_scene_package["negative_prompt"]

    frame_package = bot.build_video_prompt(
        bot.parse_video_user_intent("ghép 5 ảnh, zoom nhẹ và fade", "framevideo", {"ratio": "9:16"})
    )
    assert frame_package["provider_video_allowed"] is False
    assert "Do not call a generative video provider" in frame_package["prompt"]

    high_prompt = bot.video_tier_prompt_for_generation(request, "high", "9:16")
    for phrase in ("premium cinematic quality", "realistic motion", "polished commercial look", "stable identity"):
        assert phrase in high_prompt
    assert bot.video_request_is_vague("làm video bán hàng") is True
    assert bot.video_request_is_vague(request) is False


def test_video_system_v9_preview_and_stable_flow_linkage():
    preview = bot.guided_video_plan_text(
        {
            "prompt_kind": "ad",
            "selected_prompt": "video nước hoa luxury cho TikTok, camera zoom nhẹ, không thêm chữ",
            "selected_motion": "camera zoom nhẹ",
            "selected_music": "ambient luxury",
            "aspect_ratio": "9:16",
        },
        "vi",
    )
    for expected in (
        "Prompt video đã sẵn sàng",
        "Kế hoạch video đã tối ưu",
        "Chuyển động camera",
        "Chuyển động chủ thể",
        "Điều cần giữ",
        "Điều cần tránh",
        "chưa gọi API video",
        "chưa trừ Xu",
    ):
        assert expected in preview

    image_preview = bot.guided_video_plan_text(
        {"selected_prompt": "làm ảnh sản phẩm chuyển động nhẹ", "selected_motion": "orbit"},
        "vi",
        from_image=True,
    )
    assert "Prompt video từ ảnh đã sẵn sàng" in image_preview
    assert "Use the uploaded image as the visual reference" in image_preview

    reference_plan = bot.video_reference_plan_text(
        {"analysis_kind": "ad", "selected_topic": "máy pha cà phê mini"},
        "vi",
    )
    assert "Prompt render mới, không sao chép" in reference_plan
    assert "Do not copy the original video exactly" in reference_plan

    self_scene = bot.self_scene_plan_text(
        {
            "selected_topic": "người mẫu nam",
            "selected_context": "thành phố tương lai",
            "direction": "cinema",
            "selected_motion": "orbit",
            "selected_music": "cinematic",
        },
        "vi",
    )
    assert "Keep the original person or product identity stable" in self_scene
    assert "thành phố tương lai" in self_scene
    assert "orbit shot" in self_scene


def _button_texts(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _button_callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_video_export_vfinal_addons_and_tier_gate_labels(monkeypatch):
    state = {
        "source": "trend",
        "source_label": "Video theo trend",
        "has_script": True,
        "has_video_prompt": True,
        "session_context": {"video_prompt": "video quảng cáo nước hoa nam, camera push-in, ánh sáng luxury"},
        "source_payload": {"video_prompt": "video quảng cáo nước hoa nam, camera push-in, ánh sáng luxury"},
        "video_finalization": bot.video_finalization_defaults(),
    }
    menu_text = bot.video_finalization_menu_text(state, "vi")
    menu_buttons = _button_texts(bot.video_finalization_menu_keyboard("vi"))
    assert "Tùy chọn hoàn thiện video" in menu_text
    assert any("Tiếp tục chọn gói" in text for text in menu_buttons)
    assert "Bỏ qua & xuất video" not in menu_buttons
    assert "Hoàn thiện video" not in menu_text

    tier_text = bot.video_finalization_tier_text(state, "vi")
    tier_markup = bot.video_finalization_tier_keyboard("vi")
    tier_callbacks = _button_callbacks(tier_markup)
    assert "Chọn gói xuất video AI" in tier_text
    for price in ("200 Xu", "300 Xu", "400 Xu", "500 Xu", "600 Xu", "800 Xu", "1000 Xu", "1200 Xu", "1500 Xu"):
        assert price in tier_text
    for tier in ("low", "basic", "common", "advanced", "standard", "high", "future_1000", "future_1200", "future_1500"):
        assert f"vfinal|tier|{tier}" in tier_callbacks
    assert "kiểm soát chi phí" not in tier_text.lower()


def test_video_export_vfinal_not_ready_hides_fake_maintenance_action(monkeypatch):
    monkeypatch.setattr(bot, "VIDEO_AI_PUBLIC_ENABLED", False)
    state = {
        "source": "trend",
        "source_label": "Video theo trend",
        "has_script": True,
        "has_video_prompt": True,
        "selected_video_tier": "low",
        "session_context": {"video_prompt": "video quảng cáo nước hoa nam"},
        "source_payload": {"video_prompt": "video quảng cáo nước hoa nam"},
        "video_finalization": bot.video_finalization_defaults(),
    }
    text = bot.video_finalization_confirm_not_ready_text(state, "vi")
    buttons = _button_texts(bot.video_finalization_confirm_not_ready_keyboard(state, "vi"))
    callbacks = _button_callbacks(bot.video_finalization_confirm_not_ready_keyboard(state, "vi"))
    assert "Đang bảo trì/nâng cấp nhẹ" in text
    assert "✅ Xác nhận xuất video" not in buttons
    assert "Video AI bảo trì/nâng cấp" not in buttons
    assert "📋 Copy prompt" in buttons
    assert "💾 Lưu kế hoạch" in buttons
    assert "🎛 Thêm tính năng khác" in buttons
    assert "vfinal|tier" in callbacks


def test_video_export_vfinal_ready_uses_confirm_path(monkeypatch):
    monkeypatch.setattr(bot, "video_tier_enabled_map", lambda: {"low": False, "basic": True, "common": True, "standard": False, "high": False, "premium": False})
    monkeypatch.setattr(bot, "video_billing_public_gate", lambda: {"ready": True, "allowed_tiers": ["basic", "common"], "blockers": []})
    monkeypatch.setattr(
        bot,
        "get_video_prompt_export_readiness",
        lambda user_is_admin=False: {
            "public_ready": True,
            "admin_ready": False,
            "ready": True,
            "missing_public": [],
            "missing_admin": ["admin required"],
            "reason": "ready",
        },
    )
    state = {
        "source": "trend",
        "source_label": "Video theo trend",
        "has_script": True,
        "has_video_prompt": True,
        "session_context": {"video_prompt": "video quảng cáo nước hoa nam"},
        "source_payload": {"video_prompt": "video quảng cáo nước hoa nam"},
        "video_finalization": bot.video_finalization_defaults(),
    }
    status = bot.get_public_video_tier_ui_status("basic", False)
    assert status["enabled"] is True
    assert bot.get_public_video_tier_ui_status("low", False)["enabled"] is True
    buttons = _button_texts(bot.video_finalization_summary_keyboard(state, "vi"))
    callbacks = _button_callbacks(bot.video_finalization_summary_keyboard(state, "vi"))
    assert "✅ Xác nhận xuất video" in buttons
    assert "📋 Copy prompt" in buttons
    assert "Video AI bảo trì/nâng cấp" not in buttons
    assert "vfinal|export_ai" in callbacks
    assert "vfinal|copy_prompt" in callbacks


def test_video_export_vfinal_restores_business_tiers_even_when_old_gate_is_stale(monkeypatch):
    monkeypatch.setattr(bot, "video_public_beta_enabled_runtime", lambda: True)
    monkeypatch.setattr(bot, "video_public_allowed_tiers", lambda: ["low", "basic", "common", "advanced", "standard", "high"])
    monkeypatch.setattr(bot, "video_tier_public_flag", lambda tier: bot.normalize_video_tier(tier) in {"low", "basic", "common", "advanced", "standard", "high"})
    monkeypatch.setattr(
        bot,
        "video_tier_enabled_map",
        lambda: {"low": True, "basic": True, "common": True, "advanced": True, "standard": True, "high": True, "future_1000": False, "future_1500": False},
    )
    monkeypatch.setattr(bot, "video_billing_public_gate", lambda: {"ready": True, "allowed_tiers": ["advanced", "standard", "high"], "blockers": [], "cost_rows": []})
    monkeypatch.setattr(
        bot,
        "get_video_prompt_export_readiness",
        lambda user_is_admin=False: {
            "public_ready": True,
            "admin_ready": True,
            "ready": True,
            "missing_public": [],
            "missing_admin": [],
            "reason": "ready",
        },
    )
    for tier in ("advanced", "standard", "high"):
        status = bot.get_public_video_tier_ui_status(tier, False)
        assert status["enabled"] is True
        assert status["visible"] is True
        assert status["public_status"] == "PUBLIC"
        assert status["reason"] == "ready"
    assert bot.get_public_video_tier_ui_status("future_1000", False)["enabled"] is True
    tier_text = bot.video_finalization_tier_text({}, "vi")
    for price in ("500 Xu", "600 Xu", "800 Xu", "1000 Xu", "1200 Xu", "1500 Xu"):
        assert price in tier_text
    assert "cost is report-only" in bot.video_cost_status_text()


def test_public_video_tier_keyboard_exposes_all_business_packages():
    buttons = _button_texts(bot.public_video_tier_keyboard("vi"))
    callbacks = _button_callbacks(bot.public_video_tier_keyboard("vi"))
    for label in ("200 Xu", "300 Xu", "400 Xu", "500 Xu", "600 Xu", "800 Xu", "1000 Xu", "1200 Xu", "1500 Xu"):
        assert any(label in button for button in buttons)
    for label in ("Trải nghiệm", "Cơ bản", "Phổ thông", "Nâng cao", "Bán hàng", "Cao cấp", "Chuyên nghiệp", "Pro Plus", "Premium"):
        assert any(label in button for button in buttons)
    for tier in ("low", "basic", "common", "advanced", "standard", "high", "future_1000", "future_1200", "future_1500"):
        assert f"create_media|video_tier_{tier}" in callbacks


def test_video_prompt_result_uses_create_now_and_addons_labels():
    buttons = _button_texts(bot.trend_guided_selected_video_prompt_keyboard("vi", is_admin=False))
    assert "🎛 Thêm tính năng khác" in buttons
    assert "🎬 Tạo video ngay" in buttons
    assert "🎛 Hoàn thiện video" not in buttons
    assert "🎬 Tạo video thật" not in buttons

    trend_prompt = bot.trend_guided_video_prompt_for_index(
        {
            "topic": "máy xay sinh tố mini",
            "selected_trend_title": "Trend before/after",
            "selected_motion_title": "zoom nhẹ vào sản phẩm",
        },
        1,
        "vi",
    )
    assert "opening 1-3 seconds" in trend_prompt
    assert "aspect ratio 9:16" in trend_prompt

    long_plan = bot.long_video_plan_text(
        {"selected_topic": "khóa học affiliate", "duration": "10 phút", "selected_style": "giáo dục"},
        "vi",
    )
    assert "Prompt video từng cảnh" in long_plan

    source = bot_source_text()
    prompt_handler = source_between(source, "async def handle_prompt_video_callback", "async def handle_image_video_callback")
    reference_handler = source_between(source, "async def handle_video_reference_callback", "async def handle_video_dubbing_callback")
    vague_handler = source_between(source, "async def handle_public_video_prompt_pending_text", "async def cmd_shopaikey_video_public")
    assert "open_prompt_video_finalization_from_state(query, uid, state, lang" in prompt_handler
    assert 'structured_video_plan(state, "promptvideo")' in source_between(source, "async def open_prompt_video_finalization_from_state", "async def open_image_video_finalization_from_state")
    assert 'structured_video_plan(plan, "videoref")' in reference_handler
    assert "video_request_is_vague(prompt)" in vague_handler
    assert "TOAN AAS chưa xử lý video và chưa trừ Xu" in vague_handler


def test_video_module_v10_feature_flags_callbacks_and_detailed_prompts(monkeypatch):
    assert bot.VIDEO_SAMPLE_MAX_SECONDS >= 60
    assert bot.VIDEO_SAMPLE_MAX_MB >= 1
    assert bot.VIDEO_PROVIDER_RENDER_MAX_SECONDS >= 1
    assert isinstance(bot.VIDEO_TEMP_STORAGE_ENABLED, bool)

    monkeypatch.setattr(bot, "VIDEO_AI_PUBLIC_ENABLED", False)
    assert bot.video_render_feature_enabled("promptvideo") is False
    monkeypatch.setattr(bot, "VIDEO_AI_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_LONG_RENDER_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_VIDEO_TO_VIDEO_ENABLED", True)
    assert bot.video_render_feature_enabled("longvideo") is True
    assert bot.video_render_feature_enabled("selfscene") is True

    idea_callbacks = [
        button.callback_data
        for row in bot.video_idea_result_keyboard("vi").inline_keyboard
        for button in row
    ]
    assert "videoidea|frame_video" in idea_callbacks
    assert "videoidea|render_ai" in idea_callbacks
    long_callbacks = [
        button.callback_data
        for row in bot.long_video_result_keyboard("vi").inline_keyboard
        for button in row
    ]
    assert "longvideo|frame_video" in long_callbacks
    assert "longvideo|render_segments" in long_callbacks
    reference_callbacks = [
        button.callback_data
        for row in bot.video_reference_result_keyboard("vi").inline_keyboard
        for button in row
    ]
    assert "videoref|sample_segments" in reference_callbacks
    assert "videoref|video_prompts" in reference_callbacks

    detailed = bot.detailed_video_scene_prompts_text(
        {
            "selected_topic": "nước hoa nam",
            "selected_context": "studio luxury",
            "selected_motion": "slow push-in",
            "selected_style": "cinematic",
            "aspect_ratio": "9:16",
        },
        "videoidea",
        "vi",
        scene_count=3,
    )
    for expected in ("Cảnh 1", "Thời lượng", "Chủ thể/bối cảnh", "Hành động", "Camera", "Ánh sáng/phong cách", "Chuyển cảnh/âm thanh", "Negative"):
        assert expected in detailed

    source = bot_source_text()
    idea_handler = source_between(source, "async def handle_video_idea_callback", "def menu_text_main_ai")
    long_handler = source_between(source, "async def handle_long_video_callback", "async def handle_video_idea_callback")
    reference_handler = source_between(source, "async def handle_video_reference_callback", "async def handle_video_dubbing_callback")
    for action in ("frame_video", "render_ai"):
        assert f'action == "{action}"' in idea_handler
    for action in ("frame_video", "render_segments"):
        assert f'action == "{action}"' in long_handler
    for action in ("sample_segments", "video_prompts"):
        assert f'action == "{action}"' in reference_handler


def test_video_module_v10_reference_sample_accepts_long_planning_without_provider(monkeypatch):
    uid = 991001
    replies = []

    class FakeMessage:
        def __init__(self):
            self.video = SimpleNamespace(
                file_id="video-file-id",
                file_unique_id="video-unique-id",
                file_name="reference.mp4",
                mime_type="video/mp4",
                duration=120,
                file_size=5 * 1024 * 1024,
                width=1080,
                height=1920,
            )
            self.document = None

        async def reply_text(self, text, **kwargs):
            replies.append((text, kwargs))

    bot.clear_developing_video_pending(uid)
    bot.set_developing_video_pending(uid, "videoref", "await_video")
    monkeypatch.setattr(bot, "VIDEO_ANALYZE_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_SAMPLE_MAX_SECONDS", 600)
    monkeypatch.setattr(bot, "VIDEO_SAMPLE_MAX_MB", 100)
    update = SimpleNamespace(message=FakeMessage(), effective_user=SimpleNamespace(id=uid))
    assert asyncio.run(bot.handle_video_reference_pending_upload(update, SimpleNamespace())) is True
    state = bot.get_developing_video_pending(uid)
    assert state and state["step"] == "direction"
    assert state["source_file_id"] == "video-file-id"
    assert int(state["source_duration"]) == 120
    assert replies and "Đã nhận video mẫu" in replies[-1][0]
    assert "chia từng đoạn" in replies[-1][0]
    bot.clear_developing_video_pending(uid)
    bot.LAST_USER_VIDEO.pop(uid, None)


def test_video_module_v10_self_scene_source_status_and_safe_guard():
    without_source = bot.self_scene_plan_text(
        {
            "selected_topic": "người mẫu",
            "selected_context": "studio",
            "direction": "cinema",
            "selected_motion": "orbit",
            "selected_music": "cinematic",
        },
        "vi",
    )
    assert "Video đã nhận: <b>chưa — mới lập kế hoạch</b>" in without_source
    with_source = bot.self_scene_plan_text(
        {
            "source_file_id": "telegram-video-id",
            "selected_topic": "người mẫu",
            "selected_context": "studio",
            "direction": "cinema",
            "selected_motion": "orbit",
            "selected_music": "cinematic",
        },
        "vi",
    )
    assert "Video đã nhận: <b>có</b>" in with_source
    assert "chưa xử lý video thật" in bot.developing_video_render_guard_text("selfscene", "vi")
    assert "chưa trừ Xu" in bot.developing_video_render_guard_text("selfscene", "vi")


def test_manual_topup_menu_methods(monkeypatch):
    monkeypatch.setattr(bot, "MANUAL_BANK_ENABLED", True)
    monkeypatch.setattr(bot, "MANUAL_ZALOPAY_PERSONAL_ENABLED", True)
    monkeypatch.setattr(bot, "MANUAL_ZALOPAY_MERCHANT_ENABLED", True)
    monkeypatch.setattr(bot, "MANUAL_MOMO_TUITHANTAI_ENABLED", True)
    monkeypatch.setattr(bot, "MANUAL_USDT_TRC20_ENABLED", False)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    currency_labels = [button.text for row in bot.manual_payment_menu_keyboard(123).inline_keyboard for button in row]
    assert "🇻🇳 VND" in currency_labels
    assert "🇺🇸 USD" in currency_labels
    assert "🇨🇳 CNY" in currency_labels
    labels = [button.text for row in bot.manual_domestic_method_keyboard(123).inline_keyboard for button in row]
    assert "🏦 Ngân hàng ACB/VietQR" in labels
    assert "💚 ZaloPay cá nhân" in labels
    assert "🛍 ZaloPay cửa hàng" in labels
    assert "💗 MoMo/Túi Thần Tài" in labels
    assert "🪙 USDT TRC20" not in labels


def test_manual_bank_qr_asset_send_and_missing_no_crash(monkeypatch, tmp_path):
    class FakeBot:
        def __init__(self):
            self.photos = []

        async def send_photo(self, **kwargs):
            self.photos.append(kwargs)

    fake_bot = FakeBot()
    context = SimpleNamespace(bot=fake_bot)
    qr_path = tmp_path / "acb.jpg"
    qr_path.write_bytes(b"test-qr")
    monkeypatch.setattr(bot, "MANUAL_BANK_QR_PATH", str(qr_path))
    assert asyncio.run(bot.send_manual_method_qr(context, 1, 1, "bank_acb")) is True
    assert len(fake_bot.photos) == 1

    alerts = []

    async def fake_alert(_context, service, detail):
        alerts.append((service, detail))

    monkeypatch.setattr(bot, "alert_admin", fake_alert)
    monkeypatch.setattr(bot, "MANUAL_BANK_QR_PATH", str(tmp_path / "missing.jpg"))
    assert asyncio.run(bot.send_manual_method_qr(context, 1, 1, "bank_acb")) is False
    assert alerts and "missing manual payment QR asset" in alerts[0][1]


def test_manual_menu_bonus_text_no_zalopay_momo():
    text = bot.manual_payment_menu_text()
    assert "PayOS hoặc QR ngân hàng Việt Nam/ACB/VietQR" in text
    assert "ZaloPay/MoMo: dùng cho thanh toán CNY nếu chuyển được" in text
    assert "USD/CNY/USDT không áp dụng ưu đãi cộng Xu" in text
    assert "QR ngân hàng Việt Nam, ZaloPay hoặc MoMo" not in text


def test_bonus_only_payos_bank_vnd():
    allowed = (
        {"currency": "VND", "method": "payos", "foreign_manual": False},
        {"currency": "VND", "method": "bank_acb", "foreign_manual": False},
        {"currency": "VND", "method": "manual_vietqr_vnd", "foreign_manual": False},
    )
    blocked = (
        {"currency": "VND", "method": "zalopay_personal", "foreign_manual": False},
        {"currency": "VND", "method": "zalopay_merchant", "foreign_manual": False},
        {"currency": "VND", "method": "momo_tuithantai", "foreign_manual": False},
        {"currency": "USD", "method": "usdt_trc20", "foreign_manual": True},
        {"currency": "CNY", "method": "zalopay_personal", "foreign_manual": True},
    )
    assert all(bot.is_topup_bonus_allowed(item) for item in allowed)
    assert all(bot.is_topup_bonus_blocked(item) for item in blocked)
    assert all(not bot.is_topup_bonus_allowed(item) for item in blocked)


def test_topup_promo_payment_eligibility_keeps_zalopay_momo_blocked():
    assert bot.is_vietnam_local_payment_method("payos") is True
    assert bot.is_vietnam_local_payment_method("bank_qr") is True
    assert bot.is_vietnam_local_payment_method("manual_bank") is True
    assert bot.is_vietnam_local_payment_method("vietqr") is True
    assert bot.is_vietnam_local_payment_method("zalopay_personal") is False
    assert bot.is_vietnam_local_payment_method("zalopay_merchant") is False
    assert bot.is_vietnam_local_payment_method("momo") is False
    assert bot.is_vietnam_local_payment_method("usdt_trc20") is False

    assert bot.should_apply_topup_promo("topup_xu", "payos", "VND", 50000, "50k", 50000) is True
    assert bot.should_apply_topup_promo("topup_xu", "manual_vietqr_vnd", "VND", 50000, "50k", 50000) is True
    assert bot.should_apply_topup_promo("topup_xu", "zalopay_personal", "VND", 50000, "50k", 50000) is False
    assert bot.should_apply_topup_promo("topup_xu", "momo_tuithantai", "VND", 50000, "50k", 50000) is False
    assert bot.should_apply_topup_promo("topup_xu", "payos", "VND", 10000, "10k", 50000) is False
    assert bot.should_apply_topup_promo("topup_xu", "payos", "VND", 20000, "20k", 50000) is False
    assert bot.should_apply_topup_promo("storage_addon", "payos", "VND", 50000, "50mb", 50000) is False
    assert bot.should_apply_topup_promo("combo_purchase", "payos", "VND", 99000, "tiktok_99k", 50000) is False
    assert bot.should_apply_topup_promo("monthly_package", "payos", "VND", 99000, "creator_monthly", 50000) is False
    assert bot.should_apply_topup_promo("topup_xu", "usdt_trc20", "USD", 250000, "", 50000, foreign_manual=True) is False
    assert bot.launch_bonus_eligible_for_payment("topup_xu", "payos", "VND", 50000, "50k") is True
    assert bot.launch_bonus_eligible_for_payment("topup_xu", "usdt_trc20", "USD", 250000, "", True) is False
    assert bot.launch_bonus_eligible_for_payment("topup_xu", "zalopay_personal", "VND", 50000, "50k") is False
    assert bot.membership_rank_volume_eligible("topup_xu", "usdt_trc20", "USD") is True
    assert bot.membership_rank_volume_eligible("storage_addon", "payos", "VND") is False


def test_qr_paths_exist_or_alert():
    for method in ("bank_acb", "usdt_trc20", "zalopay_personal", "zalopay_merchant", "momo_tuithantai"):
        assert os.path.isfile(bot.manual_method_asset_path(method)), method


def test_all_manual_qr_methods_send_photo_not_text(monkeypatch, tmp_path):
    class FakeBot:
        def __init__(self):
            self.photos = []
            self.messages = []

        async def send_photo(self, **kwargs):
            self.photos.append(kwargs)

        async def send_message(self, **kwargs):
            self.messages.append(kwargs)

    method_paths = {
        "bank_acb": "MANUAL_BANK_QR_PATH",
        "usdt_trc20": "MANUAL_USDT_TRC20_QR_PATH",
        "zalopay_personal": "MANUAL_ZALOPAY_PERSONAL_QR_PATH",
        "zalopay_merchant": "MANUAL_ZALOPAY_MERCHANT_QR_PATH",
        "momo_tuithantai": "MANUAL_MOMO_TUITHANTAI_QR_PATH",
    }
    for method, attribute in method_paths.items():
        qr_path = tmp_path / f"{method}.jpg"
        qr_path.write_bytes(b"qr")
        monkeypatch.setattr(bot, attribute, str(qr_path))
        fake_bot = FakeBot()
        context = SimpleNamespace(bot=fake_bot)
        bot.set_manual_bill_state(
            123,
            order_code="MANUAL",
            currency="VND" if method != "usdt_trc20" else "USD",
            amount=50000,
            amount_vnd=50000,
            base_xu=500,
            expected_xu=500,
            xu=500,
            method=method,
            pkg_key="50k",
            foreign_manual=method == "usdt_trc20",
        )
        assert asyncio.run(bot.send_manual_method_qr(context, 1, 123, method)) is True
        assert len(fake_bot.photos) == 1
        assert fake_bot.messages == []
        assert fake_bot.photos[0]["caption"]
        assert fake_bot.photos[0]["reply_markup"] is not None


def test_momo_asset_is_public_manual_method(monkeypatch):
    monkeypatch.setattr(bot, "MANUAL_MOMO_TUITHANTAI_ENABLED", True)
    labels = [button.text for row in bot.manual_domestic_method_keyboard(123).inline_keyboard for button in row]
    assert "💗 MoMo/Túi Thần Tài" in labels
    assert os.path.isfile(bot.manual_method_asset_path("momo_tuithantai"))


def test_manual_vnd_amount_then_method_and_blocked_bonus(monkeypatch):
    monkeypatch.setattr(
        bot,
        "calculate_package_credit_for_user",
        lambda _uid, amount: {"base_xu": amount // 100, "launch_bonus_xu": 100},
    )
    amount_labels = [button.text for row in bot.manual_domestic_amount_keyboard(123).inline_keyboard for button in row]
    assert amount_labels[:6] == ["💳 10k", "💳 20k", "💳 50k", "💳 100k", "💳 200k", "💳 500k"]
    bank = bot.manual_vnd_topup_preview(123, "50k", "bank_acb")
    zalo = bot.manual_vnd_topup_preview(123, "50k", "zalopay_personal")
    assert bank["bonus_allowed"] is True and bank["expected_xu"] == 600
    assert zalo["bonus_allowed"] is False and zalo["bonus_xu"] == 0 and zalo["expected_xu"] == 500


def _create_manual_deposit_test_db(path):
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE pending_deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT, username TEXT, file_id TEXT, file_unique_id TEXT,
            submitted_at TEXT, status TEXT, order_code TEXT, amount INTEGER, xu INTEGER,
            method TEXT, tx_hash TEXT, admin_note TEXT, approved_by TEXT,
            approved_at TEXT, updated_at TEXT,
            currency TEXT DEFAULT 'VND', original_amount REAL DEFAULT 0,
            fixed_rate_vnd INTEGER DEFAULT 1, amount_vnd INTEGER DEFAULT 0,
            base_xu INTEGER DEFAULT 0, bonus_xu INTEGER DEFAULT 0,
            expected_xu INTEGER DEFAULT 0, approved_xu INTEGER DEFAULT 0,
            foreign_manual INTEGER DEFAULT 0, first_bonus_applied INTEGER DEFAULT 0,
            launch_bonus_applied INTEGER DEFAULT 0, rank_topup_reward_applied INTEGER DEFAULT 0,
            extra_xu_percent_bonus_applied INTEGER DEFAULT 0,
            rank_discount_percent_preserved INTEGER DEFAULT 1,
            member_points_eligible INTEGER DEFAULT 1, transfer_content TEXT DEFAULT '',
            bill_file_id TEXT DEFAULT ''
        )"""
    )
    conn.commit()
    conn.close()


def test_admin_approve_no_bonus_for_blocked_methods(monkeypatch, tmp_path):
    db_path = tmp_path / "manual-blocked-bonus.db"
    _create_manual_deposit_test_db(db_path)
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    result = bot.create_manual_pending_deposit(
        SimpleNamespace(id=123, first_name="Customer"),
        {
            "currency": "VND",
            "method": "zalopay_personal",
            "foreign_manual": False,
            "amount": 50000,
            "amount_vnd": 50000,
            "base_xu": 500,
            "bonus_xu": 100,
            "expected_xu": 600,
            "xu": 600,
        },
        tx_hash="blocked-bonus-test",
    )
    assert result["ok"] is True
    assert result["bonus_allowed"] is False
    assert result["bonus_xu"] == 0
    assert result["expected_xu"] == 500
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT base_xu,bonus_xu,expected_xu FROM pending_deposits WHERE id=?", (result["id"],)).fetchone()
    finally:
        conn.close()
    assert row == (500, 0, 500)


def test_manual_bill_upload_creates_pending_review_without_credit(monkeypatch, tmp_path):
    db_path = tmp_path / "manual.db"
    _create_manual_deposit_test_db(db_path)
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "owner_and_admin_ids", lambda: ["999"])
    monkeypatch.setattr(bot, "add_credit", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not add credit")))

    class FakeBot:
        def __init__(self):
            self.photos = []

        async def send_photo(self, **kwargs):
            self.photos.append(kwargs)

    replies = []

    async def reply_text(text, **kwargs):
        replies.append(text)

    photo = SimpleNamespace(file_id="bill-file", file_unique_id="bill-unique")
    message = SimpleNamespace(photo=[photo], reply_text=reply_text)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123, first_name="Customer"),
        message=message,
    )
    context = SimpleNamespace(bot=FakeBot())
    bot.set_manual_bill_state(123, order_code="MANUAL", method="bank_acb")
    asyncio.run(bot.handle_photo(update, context))
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT status,method,file_id,file_unique_id FROM pending_deposits").fetchone()
    finally:
        conn.close()
    assert row == ("pending_admin_review", "bank_acb", "bill-file", "bill-unique")
    assert context.bot.photos and context.bot.photos[0]["chat_id"] == "999"
    assert replies and "Đã gửi bill" in replies[0]


def test_manual_approve_requires_second_confirmation(monkeypatch, tmp_path):
    db_path = tmp_path / "manual-approve.db"
    _create_manual_deposit_test_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO pending_deposits (user_id,status,xu,method,submitted_at) VALUES (?,?,?,?,?)",
        ("123", "pending_admin_review", 500, "bank_acb", "2026-06-13 10:00:00"),
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: uid == 999)
    monkeypatch.setattr(bot, "add_credit", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must wait for confirm")))
    bot.MANUAL_APPROVAL_STATE.clear()
    replies = []

    async def answer(*args, **kwargs):
        return None

    async def reply_text(text, **kwargs):
        replies.append(text)

    query = SimpleNamespace(
        data="manual|approve|1",
        from_user=SimpleNamespace(id=999),
        message=SimpleNamespace(reply_text=reply_text),
        answer=answer,
    )
    asyncio.run(bot.handle_manual_package_choice(SimpleNamespace(callback_query=query), SimpleNamespace(args=[], bot=SimpleNamespace())))
    state = bot.get_manual_approval_state(999)
    assert state and state["deposit_id"] == 1 and state["step"] == "await_amount"
    assert any("chưa cộng Xu" in item for item in replies)


def test_manual_international_topup_fixed_rates_and_bonus_guards(monkeypatch):
    monkeypatch.setattr(bot, "XU_TO_VND", 100)
    monkeypatch.setattr(bot, "USD_FIXED_RATE_VND", 25000)
    monkeypatch.setattr(bot, "CNY_FIXED_RATE_VND", 3800)
    monkeypatch.setattr(bot, "FOREIGN_XU_ROUND_TO", 10)
    monkeypatch.setattr(bot, "FOREIGN_XU_ROUNDING_MODE", "floor")

    usd = bot.foreign_topup_preview("USD", 10, "usdt_trc20")
    cny = bot.foreign_topup_preview("CNY", 10, "zalopay_personal")
    assert usd["amount_vnd"] == 250000
    assert usd["base_xu"] == 2500
    assert usd["bonus_xu"] == 0
    assert usd["expected_xu"] == 2500
    assert cny["amount_vnd"] == 38000
    assert cny["base_xu"] == 380
    assert cny["bonus_xu"] == 0
    assert cny["expected_xu"] == 380

    for preview in (usd, cny):
        assert bot.is_foreign_topup(preview) is True
        assert bot.is_topup_bonus_allowed(preview) is False
        assert bot.is_first_topup_bonus_allowed(preview) is False
        assert bot.is_launch_bonus_allowed(preview) is False
        assert bot.is_rank_topup_reward_allowed(preview) is False
        assert preview["extra_xu_percent_bonus_applied"] is False
        assert preview["rank_discount_percent_preserved"] is True


def test_cny_zalopay_is_foreign_and_vnd_zalopay_blocks_bonus():
    cny_zalopay = {"currency": "CNY", "method": "zalopay_personal", "foreign_manual": True}
    vnd_bank = {"currency": "VND", "method": "bank_acb", "foreign_manual": False}
    vnd_zalopay = {"currency": "VND", "method": "zalopay_personal", "foreign_manual": False}

    assert bot.is_foreign_topup(cny_zalopay) is True
    assert bot.is_topup_bonus_allowed(cny_zalopay) is False
    assert bot.is_domestic_vnd_topup(vnd_bank) is True
    assert bot.is_launch_bonus_allowed(vnd_bank) is True
    assert bot.is_first_topup_bonus_allowed(vnd_zalopay) is False
    assert bot.is_launch_bonus_allowed(vnd_zalopay) is False
    assert bot.is_rank_topup_reward_allowed(vnd_zalopay) is False
    assert bot.is_rank_discount_percent_allowed(None, cny_zalopay) is True


def test_foreign_topup_i18n_hides_bonus_promises_and_vi_has_domestic_notice():
    en = bot.menu_text_main_topup_i18n("en")
    zh = bot.menu_text_main_topup_i18n("zh")
    vi = bot.domestic_topup_bonus_notice()

    assert "does not include first top-up bonus" in en
    assert "30%" not in en
    assert "不包含首次充值奖励" in zh
    assert "首充 30%" not in zh
    assert "chỉ áp dụng cho khách nội địa Việt Nam" in vi
    assert "PayOS" in vi
    assert "QR ngân hàng Việt Nam/ACB/VietQR" in vi
    assert "ZaloPay, MoMo, USD, CNY và USDT TRC20 không áp dụng" in vi


def test_manual_foreign_session_saves_bonus_flags_and_duplicate_tx(monkeypatch, tmp_path):
    db_path = tmp_path / "manual-foreign.db"
    _create_manual_deposit_test_db(db_path)
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    preview = bot.foreign_topup_preview("USD", 10, "usdt_trc20")
    state = {**preview, "order_code": "MANUAL", "transfer_content": "AAS 123 USD MANUAL"}
    user = SimpleNamespace(id=123, first_name="Foreign customer", username="foreign")

    first = bot.create_manual_pending_deposit(user, state, tx_hash="txid-unique-001")
    second = bot.create_manual_pending_deposit(user, state, tx_hash="txid-unique-001")
    assert first["ok"] is True
    assert second["ok"] is False
    assert second["reason"] == "duplicate_tx_hash"

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """SELECT currency,original_amount,fixed_rate_vnd,amount_vnd,base_xu,bonus_xu,expected_xu,
                      foreign_manual,first_bonus_applied,launch_bonus_applied,rank_topup_reward_applied,
                      extra_xu_percent_bonus_applied,rank_discount_percent_preserved
               FROM pending_deposits WHERE id=?""",
            (first["id"],),
        ).fetchone()
    finally:
        conn.close()
    assert row == ("USD", 10.0, 25000, 250000, 2500, 0, 2500, 1, 0, 0, 0, 0, 1)


def test_manual_custom_xu_requires_reason_before_confirm(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: uid == 999)
    bot.MANUAL_APPROVAL_STATE.clear()
    bot.set_manual_approval_state(999, 7, "123", step="await_amount", amount=2500, expected_xu=2500)
    replies = []

    async def reply_text(text, **kwargs):
        replies.append((str(text), kwargs))

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=999),
        effective_message=SimpleNamespace(text="2450", reply_text=reply_text),
    )
    assert asyncio.run(bot.handle_manual_approval_pending_text(update, SimpleNamespace())) is True
    state = bot.get_manual_approval_state(999)
    assert state["step"] == "await_reason"
    assert state["amount"] == 2450
    assert "lý do" in replies[-1][0].lower()

    update.effective_message.text = "phí chuyển USDT"
    assert asyncio.run(bot.handle_manual_approval_pending_text(update, SimpleNamespace())) is True
    state = bot.get_manual_approval_state(999)
    assert state["step"] == "confirm"
    assert state["reason"] == "phí chuyển USDT"
    assert "Xác nhận duyệt Xu điều chỉnh" in replies[-1][0]


def test_fx_price_test_command_is_admin_preview_only(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: uid == 999)
    replies = []

    async def reply_text(text, **kwargs):
        replies.append(str(text))

    update = SimpleNamespace(effective_user=SimpleNamespace(id=999), message=SimpleNamespace(reply_text=reply_text))
    asyncio.run(bot.cmd_fx_price_test(update, SimpleNamespace(args=["USD", "10"])))
    payload = replies[-1]
    assert "250.000đ" in payload
    assert "2.500 Xu" in payload
    assert "Bonus Xu: <b>0</b>" in payload
    assert "không tạo payment" in payload


def test_payos_failure_alert_cooldown(monkeypatch):
    class FakeBot:
        def __init__(self):
            self.messages = []

        async def send_message(self, **kwargs):
            self.messages.append(kwargs)

    fake_bot = FakeBot()
    monkeypatch.setattr(bot, "owner_and_admin_ids", lambda: ["999"])
    monkeypatch.setattr(bot, "PAYOS_ALERT_COOLDOWN_MINUTES", 60)
    bot.PAYOS_FAILURE_EVENTS = []
    bot.PAYOS_LAST_ALERT_AT = 0.0
    bot.PAYOS_ALERT_MUTED_UNTIL = 0.0
    context = SimpleNamespace(bot=fake_bot)
    assert asyncio.run(bot.record_payos_failure_and_maybe_alert(context, "timeout", 123, now_ts=1000)) is False
    assert asyncio.run(bot.record_payos_failure_and_maybe_alert(context, "timeout", 123, now_ts=1010)) is False
    assert asyncio.run(bot.record_payos_failure_and_maybe_alert(context, "timeout", 123, now_ts=1020)) is True
    assert asyncio.run(bot.record_payos_failure_and_maybe_alert(context, "timeout", 123, now_ts=1030)) is False
    assert len(fake_bot.messages) == 1


def test_payos_expiry_reminder_and_fallback_message(monkeypatch):
    class FakeBot:
        def __init__(self):
            self.messages = []

        async def send_message(self, **kwargs):
            self.messages.append(kwargs)

    stored = {}
    monkeypatch.setattr(bot, "PAYOS_EXPIRY_ALERT_ENABLED", True)
    monkeypatch.setattr(bot, "PAYOS_REGISTRATION_EXPIRES_AT", "2026-07-28")
    monkeypatch.setattr(bot, "PAYOS_EXPIRY_REMINDER_DAYS", (45, 30, 15, 7, 3, 1))
    monkeypatch.setattr(bot, "owner_and_admin_ids", lambda: ["999"])
    monkeypatch.setattr(bot, "get_system_setting", lambda key, default="": stored.get(key, default))
    monkeypatch.setattr(bot, "set_system_setting", lambda key, value, **kwargs: stored.__setitem__(key, value))
    fake_bot = FakeBot()
    assert bot.payos_expiry_days_remaining(datetime(2026, 6, 13).date()) == 45
    assert asyncio.run(bot.maybe_send_payos_expiry_reminder(fake_bot, datetime(2026, 6, 13).date())) is True
    assert asyncio.run(bot.maybe_send_payos_expiry_reminder(fake_bot, datetime(2026, 6, 13).date())) is False
    fallback = bot.payos_checkout_unavailable_text("50k", 50000, 123456, "secret technical error")
    assert "tạm thời không tạo được" in fallback
    assert "Nạp thủ công" in fallback
    assert "secret technical error" not in fallback


def test_video_pricing_v2_xu_conversion_and_base_prices():
    assert bot.XU_TO_VND == 100
    assert 1000 * bot.XU_TO_VND == 100000
    assert 1250 * bot.XU_TO_VND == 125000
    assert bot.calculate_video_base_price(60, "local_frame_video", "fast")["base_video_xu"] == 120
    assert bot.calculate_video_base_price(24, "ai_text_to_video", "fast")["base_video_xu"] == 720
    assert bot.calculate_video_base_price(24, "ai_image_to_video", "standard")["base_video_xu"] == 1320
    assert bot.calculate_video_base_price(24, "ai_video_to_video", "high")["base_video_xu"] == 2160
    long_price = bot.calculate_video_base_price(180, "long_ai_video", "standard")
    assert long_price["segments"] == 18
    assert long_price["segment_seconds"] == 10
    assert long_price["base_video_xu"] == 11390


def test_video_pricing_v2_subtitle_and_dubbing_prices():
    assert bot.calculate_video_addon_price(60, "subtitle_original", "none")["subtitle_xu"] == 120
    assert bot.calculate_video_addon_price(180, "subtitle_original", "none")["subtitle_xu"] == 240
    assert bot.calculate_video_addon_price(60, "none", "dub_original")["dubbing_xu"] == 250
    assert bot.calculate_video_addon_price(180, "none", "dub_original")["dubbing_xu"] == 500
    assert bot.calculate_video_addon_price(60, "subtitle_original", "dub_original")["addon_xu"] == 350
    assert bot.calculate_video_addon_price(180, "subtitle_original", "dub_original")["addon_xu"] == 700
    assert bot.calculate_video_addon_price(60, "subtitle_translated", "dub_translated", True)["addon_xu"] == 350
    assert bot.calculate_video_addon_price(180, "subtitle_translated", "dub_translated", True)["addon_xu"] == 700


def test_video_total_price_v2_is_itemized():
    pricing = bot.calculate_video_total_price(
        24,
        "ai_image_to_video",
        "standard",
        "subtitle_original",
        "dub_original",
    )
    assert pricing["base_video_xu"] == 1320
    assert pricing["subtitle_xu"] == 120
    assert pricing["dubbing_xu"] == 230
    assert pricing["addon_xu"] == 350
    assert pricing["total_xu"] == 1670
    assert pricing["estimated_vnd"] == 167000
    invoice = bot.video_price_invoice_text({
        "current_video_duration_seconds": 24,
        "current_video_processing_type": "ai_image_to_video",
        "current_video_quality_tier": "standard",
        "current_video_subtitle_option": "subtitle_original",
        "current_video_dubbing_option": "dub_original",
        "current_video_price_preview": pricing,
    })
    for marker in ["Video: <b>1.320 Xu</b>", "Phụ đề và lồng tiếng: <b>+350 Xu</b>", "Tổng: <b>1.670 Xu</b>", "167.000đ"]:
        assert marker in invoice


def test_video_200_experience_tier_locks_paid_addons_and_extensions():
    policy = bot.video_tier_policy("low")
    assert policy["role"] == "experience_trial"
    assert policy["allow_paid_addons"] is False
    assert policy["limits"] == {"per_day": 3, "per_week": 10, "per_month": 30}
    assert bot.video_tier_policy("basic")["same_base_model_as"] == "low"
    assert bot.video_tier_policy("basic")["allow_paid_addons"] is True
    for tier in ("common", "advanced", "standard", "high", "future_1000"):
        assert bot.video_tier_policy(tier)["allow_paid_addons"] is True
    quote = bot.calculate_short_video_quote("low", 8, 1, [])
    assert quote["total_xu"] == 200
    assert not quote.get("starter_tier_locked")
    locked_quote = bot.calculate_short_video_quote("low", 20, 2, ["subtitle_auto"])
    assert locked_quote["starter_tier_locked"] is True
    assert locked_quote["total_xu"] == 200
    assert "extra_duration" in locked_quote["reasons"]
    assert "subtitle_auto" in locked_quote["reasons"]
    assert bot.calculate_short_video_quote("standard", 20, 3, [])["total_xu"] == 1400
    assert bot.calculate_short_video_quote("future_1000", 20, 3, [])["total_xu"] == 2600
    assert bot.calculate_short_video_quote("standard", 61, 8, [])["route_to_long_video"] is True


def test_media_ai_readiness_contracts_and_commands_registered():
    source = bot_source_text()
    required_commands = {
        "tool_test_openai_image_edit": "cmd_tool_test_ai_image_edit",
        "tool_test_suno_music": "cmd_tool_test_key4u_suno",
        "suno_job": "cmd_key4u_suno_job",
        "suno_public_open": "cmd_suno_public_open",
        "suno_public_close": "cmd_suno_public_close",
        "minimax_status": "cmd_minimax_status",
        "tool_test_minimax_tts": "cmd_tool_test_minimax_tts",
        "tool_test_minimax_voice_clone": "cmd_tool_test_minimax_voice_clone",
        "minimax_voice_job": "cmd_minimax_voice_job",
        "voice_public_open": "cmd_voice_public_open",
        "voice_public_close": "cmd_voice_public_close",
        "tool_test_subtitle_generate": "cmd_tool_test_subtitle_generate",
        "tool_test_subtitle_translate": "cmd_tool_test_subtitle_translate",
        "tool_test_minimax_dub": "cmd_tool_test_minimax_dub",
        "subtitle_translate_public_open": "cmd_subtitle_translate_public_open",
        "subtitle_dub_public_open": "cmd_subtitle_dub_public_open",
    }
    for command, handler in required_commands.items():
        assert len(command) <= 32
        assert f'CommandHandler("{command}", {handler})' in source

    for payload in [
        bot.get_image_edit_provider_readiness(),
        bot.get_suno_music_readiness(),
        bot.get_minimax_voice_readiness(),
        bot.get_asr_readiness(),
        bot.get_subtitle_dub_readiness(),
    ]:
        for field in [
            "ready",
            "provider",
            "model",
            "endpoint_configured",
            "api_key_configured",
            "public_enabled",
            "admin_smoke_status",
            "last_smoke_at",
            "safe_user_message",
            "admin_debug_reason",
        ]:
            assert field in payload

    suno_readiness = bot.get_suno_music_readiness()
    assert set(suno_readiness.get("providers") or {}) >= {"key4u_suno", "shopaikey_music"}
    assert "key4u=" in suno_readiness.get("admin_smoke_status", "")
    assert "shopaikey=" in suno_readiness.get("admin_smoke_status", "")

    public_status = bot.get_media_ai_public_status()
    assert public_status["video_200_paid_addons_locked"] is True
    assert set(public_status) >= {"image_edit", "suno_music", "minimax_voice", "asr", "subtitle_dub"}


def test_media_ai_voice_profiles_schema_and_pricing_matrix():
    source = bot_source_text()
    assert "CREATE TABLE IF NOT EXISTS voice_profiles" in source
    assert "consent_status TEXT DEFAULT 'required'" in source
    assert "idx_voice_profiles_user_id" in source
    matrix = json.loads(Path("config/pricing_matrix_draft.json").read_text(encoding="utf-8"))
    paid_addons = matrix["video_addons"]["paid_addons_under_60s"]
    assert paid_addons["ai_voice_minimax_basic"] > 0
    assert paid_addons["voice_clone_profile"] == paid_addons["voice_clone_create"]
    assert "ai_upscale" in matrix["image_tools"]
    assert matrix["video_tiers"]["low"]["allow_paid_addons"] is False


def test_video_addon_menu_and_shared_flow_hooks():
    callbacks = [button.callback_data for row in bot.video_addon_menu_keyboard("vi").inline_keyboard for button in row]
    for callback in [
        "videoaddon|none",
        "videoaddon|subtitle",
        "videoaddon|dub",
        "videoaddon|combo",
        "videoaddon|translate_sub",
        "videoaddon|back",
    ]:
        assert callback in callbacks
    source = bot_source_text()
    frame_source = source_between(source, "async def handle_frame_video_callback", "async def handle_storyboard_callback")
    assert 'start_video_addon_step(query, uid, pending_payload, tier, lang, source="ai")' in source
    assert 'start_video_addon_step(query, uid, state, "low", lang, source="frame")' in frame_source
    for flow_marker in ["trend", "selfscene", "videoref", "imagevideo", "promptvideo"]:
        assert flow_marker in source


def test_test_all_video_does_not_crash():
    source = bot_source_text()
    init_source = source_between(source, "def init_db():", "def now_text():")
    command_source = source_between(source, "async def cmd_test_all_video", "async def cmd_video_tier_status")
    assert "error_class" in init_source
    assert "provider_error_code" in init_source
    assert "provider_message" in init_source
    assert "video_error_report_lines()" in command_source


def test_video_state_machine_stack_pop_one_step():
    uid = "pytest_video_stack"
    bot.clear_video_session(uid)
    bot.push_video_screen(uid, "selfscene:upload", "selfscene")
    bot.push_video_screen(uid, "selfscene:object", "selfscene")
    bot.push_video_screen(uid, "selfscene:direction", "selfscene")
    assert bot.pop_video_screen(uid, "selfscene:upload") == "selfscene:object"
    session = bot.get_video_session(uid)
    assert session["current_screen"] == "selfscene:object"
    bot.clear_video_session(uid)


def test_no_provider_call_before_confirm():
    source = bot_source_text()
    menu_source = source_between(source, "def video_finalization_menu_text", "def video_finalization_selected_aspect")
    callback_source = source_between(source, "async def handle_video_finalization_callback", "if action in {\"export_local\", \"export_ai\"}:")
    assert "spend_fixed_credit_info" not in menu_source
    assert "set_shopaikey_pending_confirmation" not in menu_source
    assert "spend_fixed_credit_info" not in callback_source


def test_no_xu_before_confirm():
    for text in [
        bot.video_finalization_menu_text({"source": "selfscene"}, "vi"),
        bot.self_scene_upload_text("vi", False),
        bot.storyboard_pack_result_text({"selected_topic": "máy lọc nước"}, "vi"),
    ]:
        assert "chỉ bắt đầu xử lý" in text or "chưa xử lý" in text or "chưa trừ Xu" in text


def test_no_user_copy_api_provider_env():
    public_texts = [
        bot.video_finalization_menu_text({"source": "storypack"}, "vi"),
        bot.storyboard_pack_result_text({"selected_topic": "máy lọc nước"}, "vi"),
        bot.storyboard_pack_scene_prompts_text({"selected_topic": "máy lọc nước"}, "image", "vi"),
        bot.self_scene_upload_text("vi", False),
        bot.USER_VIDEO_PROVIDER_FROZEN_MESSAGE,
        bot.USER_TTS_PROVIDER_BUSY_MESSAGE,
    ]
    banned = ["Bot chưa gọi API", "provider", "ENV", "HTTP", "feature not public", "Traceback"]
    for text in public_texts:
        for marker in banned:
            assert marker not in text


def test_self_shot_requires_video_first():
    source = bot_source_text()
    handler = source_between(source, "async def handle_self_scene_ai_callback", "async def handle_long_video_callback")
    assert 'set_developing_video_pending(uid, "selfscene", "await_video", input_type="video")' in handler
    assert "self_scene_upload_text" in handler
    upload_text = bot.self_scene_upload_text("vi", False)
    assert "Hãy gửi video nguồn" in upload_text
    assert upload_text.index("Hãy gửi video nguồn") < upload_text.index("Chọn đối tượng cần giữ ổn định")


def test_self_shot_accepts_video():
    source = bot_source_text()
    upload_handler = source_between(source, "async def handle_self_scene_pending_upload", "def self_scene_input_label")
    assert "sync_self_scene_source_video(uid, info, lang)" in upload_handler
    assert '"object"' in upload_handler
    assert "input_video_file_id" in source_between(source, "def sync_self_scene_source_video", "def developing_video_pending_key")


def test_self_shot_music_back_not_reset_flow():
    source = bot_source_text()
    handler = source_between(source, "async def handle_self_scene_ai_callback", "async def handle_long_video_callback")
    assert 'back=("⬅️ Quay lại âm thanh"' in handler
    style_block = source_between(handler, 'if action in {"style", "style_choice"}:', 'if action == "music_custom":')
    assert 'open_video_finalization(query, uid, "selfscene"' in style_block
    assert 'clear_developing_video_pending(uid)' not in style_block
    music_block = source_between(handler, 'if action in {"music", "music_choice"}:', 'if action == "plan":')
    assert 'open_video_finalization(query, uid, "selfscene"' in music_block
    assert 'clear_developing_video_pending(uid)' not in music_block


def test_self_shot_direction_buttons_do_not_error():
    callbacks = [button.callback_data for row in bot.self_scene_input_keyboard("vi").inline_keyboard for button in row]
    assert {"selfscene|direction_choice|1", "selfscene|direction_choice|2", "selfscene|direction_choice|3", "selfscene|direction_refresh"}.issubset(set(callbacks))


def test_self_shot_subject_buttons_do_not_error():
    callbacks = [button.callback_data for row in bot.self_scene_object_keyboard("vi").inline_keyboard for button in row]
    assert {"selfscene|object|person", "selfscene|object|product", "selfscene|object|pet", "selfscene|object|custom"}.issubset(set(callbacks))


def test_script_image_video_correct_order():
    callbacks = [button.callback_data for row in bot.storyboard_pack_result_keyboard("vi").inline_keyboard for button in row]
    assert callbacks.index("storypack|image_prompts") < callbacks.index("storypack|create_video_ai")
    assert callbacks.index("storypack|video_prompts") < callbacks.index("storypack|create_video_ai")


def test_storyboard_before_tier():
    source = bot_source_text()
    storypack_handler = source_between(source, "async def handle_storyboard_pack_callback", "def menu_text_main_ai")
    assert '"storypack|create_video_ai"' in source
    assert "open_video_finalization" in storypack_handler
    assert "video_finalization_tier_keyboard" not in source_between(storypack_handler, 'if action == "concept":', 'if action in {"back_detail", "detail"}:')


def test_storyboard_visual_canon_created():
    payload = bot.storyboard_pack_build_payload({"selected_topic": "máy lọc nước"}, "vi")
    canon = payload["storyboard_visual_canon"]
    for key in ["main_subject", "product", "brand_style", "color_palette", "location_style", "lighting", "camera_style", "character_consistency", "product_consistency", "forbidden_elements"]:
        assert key in canon


def test_storyboard_image_prompts_match_concept():
    payload = bot.storyboard_pack_build_payload({"selected_topic": "máy lọc nước", "selected_style": "premium"}, "vi")
    canon = payload["storyboard_visual_canon"]
    for shot in payload["shots"]:
        assert canon["main_subject"] in shot["image_prompt"]
        assert canon["product"] in shot["video_prompt"]
        assert canon["forbidden_elements"] in shot["negative_prompt"]


def test_scene_image_retry_same_scene():
    payload = bot.storyboard_pack_build_payload({"selected_topic": "máy lọc nước"}, "vi")
    assert {shot["retry_scope"] for shot in payload["shots"]} == {"retry_scene_only"}


def test_tier_back_returns_storyboard():
    source = bot_source_text()
    back_source = source_between(source, "async def video_finalization_back_to_source", "async def render_video_finalization_stack_target")
    assert 'source == "storypack"' in back_source
    assert "storyboard_pack_result_text" in back_source


def test_trend_flow_distinct():
    source = bot_source_text()
    trend_source = source_between(source, "async def handle_trend_guided_callback", "async def handle_trend_video_flow_callback")
    assert "trend" in trend_source.lower()
    assert "hook" in source.lower()
    assert "CTA" in source


def test_idea_flow_distinct():
    source = bot_source_text()
    idea_source = source_between(source, "def video_idea_menu_text", "def video_idea_menu_keyboard")
    for marker in ["sales", "review", "education", "viral", "affiliate", "CSKH", "automation"]:
        assert marker in idea_source or marker.lower() in idea_source.lower()


def test_realistic_flow_distinct():
    source = bot_source_text()
    prompt_source = source_between(source, "async def handle_prompt_video_callback", "async def handle_image_video_callback")
    assert "promptvideo" in prompt_source
    assert "ratio" in source.lower()
    assert "tier" in source.lower()


def test_free_addon_screen_before_paid_tier():
    text = bot.video_finalization_menu_text({"source": "storypack"}, "vi")
    for marker in ["Chọn giọng đọc", "nhạc", "phụ đề", "dịch", "lồng tiếng", "Sau đó mới chọn gói"]:
        assert marker in text


def test_paid_addons_are_configured_before_tier():
    menu_callbacks = [button.callback_data for row in bot.video_finalization_menu_keyboard("vi").inline_keyboard for button in row]
    assert {"vfinal|voice", "vfinal|music", "vfinal|addon", "vfinal|tier"}.issubset(set(menu_callbacks))
    addon_callbacks = [button.callback_data for row in bot.video_finalization_addon_keyboard("vi").inline_keyboard for button in row]
    assert "videodub|start|video_addon" in addon_callbacks
    assert "vfinal|addon_none" in addon_callbacks
    assert {"vfinal|subtitle", "vfinal|dub", "vfinal|combo", "vfinal|translate_sub"}.isdisjoint(set(addon_callbacks))


def test_music_menu_not_stuck():
    callbacks = [button.callback_data for row in bot.video_finalization_music_keyboard("vi").inline_keyboard for button in row]
    for callback in ["vfinal|music_library", "vfinal|music_sfx", "vfinal|my_media", "vfinal|music_ai", "vfinal|music_none", "vfinal|menu", "vfinal|main"]:
        assert callback in callbacks


def test_music_menu_origin_back_correct():
    source = bot_source_text()
    assert "set_music_nav_origin" in source
    assert "get_music_nav_back_callback" in source
    assert "get_video_finalization_state(user_id)" in source


def test_stock_music_visible():
    labels = [button.text for row in bot.video_finalization_music_keyboard("vi").inline_keyboard for button in row]
    assert "🎼 Kho nhạc có sẵn" in labels


def test_sfx_visible():
    labels = [button.text for row in bot.video_finalization_music_keyboard("vi").inline_keyboard for button in row]
    assert "🔊 Kho hiệu ứng âm thanh" in labels


def test_my_media_visible():
    labels = [button.text for row in bot.video_finalization_music_keyboard("vi").inline_keyboard for button in row]
    assert "📁 Media âm thanh của tôi" in labels


def test_suno_button_has_handler():
    callbacks = [button.callback_data for row in bot.video_finalization_music_keyboard("vi").inline_keyboard for button in row]
    assert "vfinal|music_ai" in callbacks
    assert 'if action == "music_ai":' in bot_source_text()


def test_suno_missing_key_user_guard_admin_reason():
    source = bot_source_text()
    video_handler = source_between(source, "async def handle_video_finalization_callback", "async def handle_video_finalization_pending_text")
    music_ai_block = source_between(video_handler, 'if action == "music_ai":', 'if action == "music_suggest":')
    assert 'music_guided_step_keyboard("purpose", lang, PRODUCT_CONTEXT_VIDEO_ADDON, 0)' in music_ai_block
    assert "music_guided_step_text" in music_ai_block
    assert "Provider:" not in music_ai_block
    assert "spend_fixed_credit_info" not in music_ai_block


def test_voice_vault_visible():
    labels = [button.text for row in bot.video_finalization_voice_keyboard("vi").inline_keyboard for button in row]
    assert "📁 Voice đã lưu" in labels


def test_create_new_voice_flow():
    source = bot_source_text()
    flow = source_between(source, "def voice_clone_intro_text", "def voice_hub_text")
    assert "Tôi xác nhận" in flow
    assert "voice_clone_upload" in source
    assert "voice_clone_name" in source
    assert "voice_clone_confirm" in source


def test_voice_requires_consent():
    source = bot_source_text()
    assert "consent_at=now_text()" in source
    assert "consent_status" in source


def test_voice_asks_name():
    source = bot_source_text()
    assert "voice_clone_name" in source
    assert "Hãy đặt tên" in source or "tên" in source_between(source, "async def handle_music_guided_pending_text", "async def handle_music_guided_pending_media")


def test_voice_preview_text():
    assert bot.VOICE_PROFILE_PREVIEW_TEXT == "Xin chào, đây là bản nghe thử giọng TOAN AAS."


def test_voice_profile_saved():
    source = bot_source_text()
    assert "def save_user_voice_profile" in source
    assert "INSERT INTO voice_profiles" in source
    assert "voice_profile_save" in source


def test_default_voice_free():
    labels = [button.text for row in bot.video_finalization_voice_keyboard("vi").inline_keyboard for button in row]
    assert "👩 Giọng nữ miễn phí" in labels
    assert "👨 Giọng nam miễn phí" in labels


def test_subtitle_menu_has_4_named_modes():
    labels = [button.text for row in bot.video_addon_menu_keyboard("vi", {"video_tier": "basic"}).inline_keyboard for button in row]
    joined = "\n".join(labels)
    for label in ["Tạo phụ đề", "Dịch phụ đề", "Lồng tiếng", "Dịch + lồng tiếng tự động"]:
        assert label in joined
    assert "Dịch phụ đề + lồng tiếng" not in joined


def test_no_icon_price_only_buttons():
    labels = [button.text for row in bot.video_addon_menu_keyboard("vi", {"video_tier": "basic"}).inline_keyboard for button in row]
    assert not any(label.strip().startswith(("📝 +", "🎙 +", "🎬 +", "🌐 +")) for label in labels)


def test_subtitle_price_under_60():
    assert bot.calculate_subtitle_dub_price("subtitle", 60) == 120
    assert bot.calculate_subtitle_dub_price("translate_subtitle", 60) == 150
    assert bot.calculate_subtitle_dub_price("dubbing", 60) == 250
    assert bot.calculate_subtitle_dub_price("subtitle_plus_dubbing", 60) == 350


def test_subtitle_price_over_60_blocks():
    assert bot.calculate_subtitle_dub_price("subtitle", 61) == 180
    assert bot.calculate_subtitle_dub_price("translate_subtitle", 90) == 225
    assert bot.calculate_subtitle_dub_price("dubbing", 120) == 375
    assert bot.calculate_subtitle_dub_price("subtitle_plus_dubbing", 180) == 700


def test_translate_subtitle_describes_target_language():
    source = bot_source_text()
    handler_source = source_between(source, "async def handle_video_finalization_callback", "async def handle_video_finalization_pending_text")
    translate_block = source_between(handler_source, 'if action == "translate_sub":', 'if action == "translate_lang":')
    assert "apply_video_finalization_subdub_choice(uid, action)" in translate_block
    assert "video_finalization_return_after_addon" in translate_block
    assert "video_finalization_translation_language_keyboard" not in translate_block

    user_id = "translate-subtitle-draft"
    bot.clear_video_finalization_state(user_id)
    bot.set_video_finalization_state(user_id, {"pending_action": "video_finalization", "video_finalization": {}})
    state = bot.apply_video_finalization_subdub_choice(user_id, "translate_sub")
    finalization = state["video_finalization"]
    assert finalization["subtitle_enabled"] is True
    assert finalization["subtitle_mode"] == "translate_subtitle"
    assert finalization["translation_enabled"] is True
    assert finalization["dub_enabled"] is False


def test_subtitle_plus_dubbing_exists():
    assert bot.normalize_subtitle_dub_mode("subtitle_plus_dub") == "subtitle_plus_dubbing"
    assert bot.SUBTITLE_DUB_PRICE_RULES["subtitle_plus_dubbing"]["base_xu"] == 350


def test_subtitle_updates_video_order():
    state = {"video_tier": "basic", "current_video_subtitle_option": "subtitle_original", "current_video_dubbing_option": "dub_original"}
    order = bot.video_order_from_state(state, 123)
    assert any(item["key"] == "subtitle_plus_dubbing" and item["price_xu"] == 350 for item in order["paid_items"])


def test_reference_video_channel_flow():
    labels = [button.text for row in bot.video_reference_hub_keyboard("vi").inline_keyboard for button in row]
    joined = "\n".join(labels)
    for label in ["Phân tích link video", "Upload video mẫu", "Hồ sơ kênh của tôi", "Tạo video theo format"]:
        assert label in joined
    source = bot_source_text()
    plan_source = source_between(source, "def video_reference_plan_text", "def video_reference_result_keyboard")
    for marker in ["hook", "structure", "pacing", "caption", "SFX", "CTA"]:
        assert marker.lower() in plan_source.lower()


def test_reference_workflow_doc_created():
    path = Path("docs/knowledge/TOAN_AAS_REFERENCE_VIDEO_WORKFLOW_20260618.md")
    text = path.read_text(encoding="utf-8")
    for marker in ["AI CSKH", "power, capacity, features", "trend -> hook -> script -> storyboard", "reference channel/video template"]:
        assert marker in text


def test_video_order_builder_base_price():
    order = bot.video_order_create(123, "basic", {"prompt": "video quảng cáo"}, {"video_tier": "basic"})
    assert order["tier"] == "basic"
    assert order["base_price_xu"] == bot.video_tier_cost_xu("basic")
    assert order["total_xu"] == order["base_price_xu"]
    assert order["current_screen"] == "video_addon_menu"


def test_video_order_builder_addon_total():
    state = {
        "video_tier": "basic",
        "current_video_subtitle_option": "subtitle_original",
        "current_video_dubbing_option": "dub_original",
    }
    order = bot.video_order_from_state(state, 123)
    expected = (
        bot.video_tier_cost_xu("basic")
        + bot.calculate_subtitle_dub_price("subtitle_plus_dubbing", 60)
    )
    assert order["total_xu"] == expected
    assert any("Phụ đề và lồng tiếng" in item["label"] for item in order["paid_items"])


def test_video_confirm_never_zero_without_valid_discount():
    order = bot.video_order_create(123, "basic", {}, {"video_tier": "basic"})
    order["discounts"] = [{"label": "invalid member discount", "price_xu": order["base_price_xu"]}]
    recalculated = bot.video_order_recalculate(order, {"video_tier": "basic"})
    assert recalculated["total_xu"] == bot.video_tier_cost_xu("basic")


def test_video_confirm_no_invalid_member_discount():
    state = {"video_tier": "basic", "video_order": {"tier": "basic", "discounts": [{"label": "member", "price_xu": 300}]}}
    text = bot.video_price_invoice_text(state, "vi")
    assert "Ưu đãi thành viên" not in text
    assert "Tổng: <b>0 Xu</b>" not in text


def test_video_200_hides_paid_addons():
    markup = bot.video_addon_menu_keyboard("vi", {"video_tier": "low"})
    callbacks = _button_callbacks(markup)
    assert "videoaddon|subtitle" not in callbacks
    assert "videoaddon|dub" not in callbacks
    assert "videoaddon|none" in callbacks
    order = bot.video_order_from_state({"video_tier": "low", "current_video_subtitle_option": "subtitle_original"}, 123)
    assert order["paid_items"] == []
    assert order["total_xu"] == bot.video_tier_cost_xu("low")


def test_video_300_shows_paid_addons():
    markup = bot.video_addon_menu_keyboard("vi", {"video_tier": "basic"})
    callbacks = _button_callbacks(markup)
    assert "videoaddon|subtitle" in callbacks
    assert "videoaddon|dub" in callbacks
    assert "videoaddon|combo" in callbacks
    assert "videoaddon|translate_sub" in callbacks
    assert "videoaddon|translate_combo" not in callbacks


def test_subtitle_dub_screen_has_clear_descriptions():
    text = bot.video_order_screen_text("subtitle_dub", {"video_tier": "basic"}, "vi")
    assert "Tạo phụ đề tự động" in text
    assert "Dịch phụ đề" in text
    assert "Lồng tiếng" in text
    assert "hóa đơn" in text.lower()


def test_subtitle_dub_screen_no_provider_word():
    text = bot.video_order_screen_text("subtitle_dub", {"video_tier": "basic"}, "vi")
    assert "provider" not in text.lower()
    assert "api" not in text.lower()


def test_subtitle_dub_back_returns_to_addon_menu():
    order = bot.video_order_create(123, "basic")
    order = bot.video_order_push_screen(order, "addon_voice")
    order = bot.video_order_back_screen(order)
    assert order["current_screen"] == "video_addon_menu"


def test_music_screen_free_and_paid_clear():
    text = bot.video_order_screen_text("music", {"video_tier": "basic"}, "vi")
    assert "Miễn phí" in text
    assert "Cộng phí" in text
    assert "Tạo nhạc AI" in text
    assert "Suno" not in text


def test_voice_screen_free_and_paid_clear():
    text = bot.video_order_screen_text("voice", {"video_tier": "basic"}, "vi")
    assert "Miễn phí" in text
    assert "Cộng phí" in text
    assert "Lồng tiếng AI" in text


def test_confirm_screen_professional_copy():
    state = {"video_tier": "basic", "current_video_subtitle_option": "subtitle_original"}
    text = bot.video_price_invoice_text(state, "vi")
    assert "Hóa đơn xác nhận video" in text
    assert "Dịch vụ chính" in text
    assert "Add-on có phí" in text
    assert "TOAN AAS chỉ bắt đầu xử lý" in text
    assert "provider" not in text.lower()
    assert "api" not in text.lower()


def test_confirm_screen_total_matches_order():
    state = {"video_tier": "basic", "current_video_subtitle_option": "subtitle_original"}
    order = bot.video_order_from_state(state, 123)
    text = bot.video_price_invoice_text(state, "vi")
    assert f"Tổng: <b>{bot.xu_number(order['total_xu'])} Xu</b>" in text


def test_no_xu_before_confirm():
    source = source_between(bot_source_text(), "async def start_video_addon_step", "async def finalize_video_addon_confirmation")
    assert "spend_fixed_credit_info(" not in source
    assert "deduct" not in source.lower()


def test_no_processing_before_confirm():
    text = bot.video_price_invoice_text({"video_tier": "basic"}, "vi")
    assert "sau khi bạn bấm xác nhận cuối" in text
    assert "đã xử lý" not in text.lower()


def test_high_public_tiers_are_billable():
    assert bot.video_order_create(123, "future_1000")["billable"] is True
    assert bot.video_order_create(123, "future_1200")["billable"] is True
    assert bot.video_order_create(123, "future_1500")["billable"] is True


def test_200_addon_callback_guard_runs_only_on_export():
    source = source_between(bot_source_text(), "async def handle_video_addon_callback", "async def cmd_video_price_test")
    assert 'if action == "export"' in source
    assert "handle_video_export_confirm(update, context, token)" in source
    dispatcher = source_between(bot_source_text(), "async def handle_video_export_confirm", "def image_tool_pricing_matrix")
    assert 'tier == "low"' in dispatcher
    assert "classify_video_addons_for_package(state)" in dispatcher
    assert "video_experience_tier_lock_text" in dispatcher
    assert dispatcher.index("classify_video_addons_for_package(state)") < dispatcher.index('canonical_callback = f"shopai|confirm|{token}"')
    assert "handle_shopaikey_public_callback(update, context, canonical_callback)" in dispatcher
    assert 'query.data = f"shopai|confirm|{token}"' not in dispatcher
    assert 'tier == "low" and str(state.get("source")' not in source


def test_back_stack_preserves_video_order():
    order = bot.video_order_create(123, "basic")
    order = bot.video_order_push_screen(order, "addon_language")
    order = bot.video_order_push_screen(order, "addon_voice")
    order = bot.video_order_back_screen(order)
    assert order["current_screen"] == "addon_language"
    order = bot.video_order_back_screen(order)
    assert order["current_screen"] == "video_addon_menu"


def test_video_addon_provider_guard_happens_before_charge(monkeypatch):
    monkeypatch.setattr(bot, "VIDEO_CREATION_ADDON_PIPELINE_ENABLED", False)
    blocked = bot.video_addon_runtime_guard({
        "subtitle_option": "subtitle_original",
        "dubbing_option": "none",
    })
    assert blocked == {"ok": False, "reason": "pipeline_off"}
    assert bot.video_addon_runtime_guard({"subtitle_option": "none", "dubbing_option": "none"})["ok"] is True
    callback_source = source_between(bot_source_text(), "async def handle_shopaikey_public_callback", "class TranslationProviderError")
    assert callback_source.index("video_addon_runtime_guard(pending)") < callback_source.index("spend_fixed_credit_info(")


def test_video_price_test_command_registered_and_preview_only():
    source = bot_source_text()
    command_source = source_between(source, "async def cmd_video_price_test", "def public_video_provider_fail_message")
    assert "No job created and no Xu deducted" in command_source
    assert 'CommandHandler("video_price_test", cmd_video_price_test)' in source
    assert 'CallbackQueryHandler(handle_video_addon_callback, pattern=r"^videoaddon\\|")' in source


def test_provider_pipeline_v32_status_handler_is_chunked_and_safe():
    source = bot_source_text()
    impl = source_between(source, "async def _cmd_shopaikey_status_impl", "async def cmd_shopaikey_status")
    wrapper = source_between(source, "async def cmd_shopaikey_status", "async def cmd_shopaikey_status_debug")
    assert "reply_html_lines(update, lines)" in impl
    assert "except Exception as exc" in wrapper
    assert "Bot chưa ảnh hưởng ví/Xu của user" in wrapper
    assert "API key: <code>{'configured' if SHOPAIKEY_API_KEY else 'missing'}" in wrapper


def test_provider_pipeline_v32_video_processing_is_not_immediate_stale(monkeypatch):
    monkeypatch.setattr(bot, "latest_api_debug_event", lambda *_args, **_kwargs: {})
    snapshot = {
        "status": "PASS_SUBMITTED",
        "tested_at": bot.now_text(),
        "detail": "task_id=active_job",
    }
    normalized = bot.normalize_shopaikey_video_snapshot(snapshot)
    assert normalized["status"] == "PASS_SUBMITTED"


def test_provider_pipeline_v32_brief_video_poll_returns_processing(monkeypatch):
    async def fake_status(_task_id):
        return {"status": "PROCESSING", "provider_status": "processing", "task_id": "job_1"}

    monkeypatch.setattr(bot, "shopaikey_video_job_status", fake_status)
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_SMOKE_MAX_WAIT_SECONDS", -1)
    result = asyncio.run(bot.poll_shopaikey_video_smoke_job("job_1"))
    assert result["lifecycle_status"] == "processing"
    assert result["task_id"] == "job_1"


def test_provider_pipeline_v32_public_subtitle_guards_are_separate(monkeypatch):
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PUBLIC_ENABLED", False)
    capability = bot.video_dubbing_capability(bot.VIDEO_SUBTITLE_MODE_CREATE, {}, public=True)
    assert capability["ok"] is False
    assert capability["reason"] == "public_disabled"
    guard = bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_CREATE, {}, "vi")
    assert "Tạo/gắn phụ đề vào video đang bảo trì/nâng cấp" in guard
    assert "chưa trừ Xu" in guard
    assert "API" not in guard
    assert "provider" not in guard.lower()


def test_provider_pipeline_v32_admin_smoke_commands_registered_and_no_charge():
    source = bot_source_text()
    for command, handler in {
        "shopaikey_status_debug": "cmd_shopaikey_status_debug",
        "tool_test_asr": "cmd_tool_test_asr",
        "tool_test_video_subtitle": "cmd_tool_test_video_subtitle",
        "tool_test_video_dub": "cmd_tool_test_video_dub",
        "tool_test_subtitle_plus_dub": "cmd_tool_test_subtitle_plus_dub",
        "clear_frame_video_error": "cmd_clear_frame_video_error",
    }.items():
        assert f'CommandHandler("{command}", {handler})' in source
        assert len(command) <= 32
    smoke_source = source_between(source, "async def run_admin_video_pipeline_smoke", "async def cmd_tool_test_video_subtitle")
    assert "spend_fixed_credit_info" not in smoke_source
    assert "No Xu deducted" in smoke_source


def test_provider_pipeline_v32_wf_i2v_and_frame_error_guards_present():
    source = bot_source_text()
    wf_source = source_between(source, "async def cmd_tool_test_workflow_image_to_video", "async def cmd_image_tools")
    assert "SHOPAIKEY_WF_I2V_SMOKE_ENABLED" in wf_source
    assert "Workflow image-to-video đang OFF" in wf_source
    frame_source = source_between(source, "async def cmd_frame_video_status", "async def cmd_clear_frame_video_error")
    assert "Last error" in frame_source


def _editor_test_image_bytes(size=(640, 480), color=(80, 150, 190)):
    image = bot.Image.new("RGB", size, color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_image_enhance_menu():
    labels = [button.text for row in bot.main_image_keyboard("vi").inline_keyboard for button in row]
    assert "✨ Chỉnh sửa AI" in labels
    assert "🧩 Chỉnh sửa ảnh" in labels
    assert "🎨 Công thức màu" not in labels
    assert "✂️ Cắt / Đổi tỉ lệ ảnh" not in labels
    assert "🔠 Thêm chữ / logo" not in labels
    assert "✨ Nâng chất lượng AI" not in labels
    assert "🪄 Chỉnh ảnh tự động" not in labels
    assert "🖼 Làm nét / nâng chất lượng ảnh" not in labels


def test_image_menu_structure_v2_exact_groups():
    main_rows = [[button.text for button in row] for row in bot.main_image_keyboard("vi").inline_keyboard]
    assert main_rows == [
        ["🖼 Tạo ảnh nhanh", "✍️ Tạo prompt từ ảnh"],
        ["✨ Chỉnh sửa AI", "🧩 Chỉnh sửa ảnh"],
        ["⬅️ Quay lại", "🏠 Menu chính"],
    ]

    edit_rows = [[button.text for button in row] for row in bot.image_edit_choice_keyboard("vi").inline_keyboard]
    assert edit_rows == [
        ["✂️ Cắt / đổi tỉ lệ", "📐 Resize pixel"],
        ["🔤 Thêm chữ / logo", "🎨 Công thức màu"],
        ["✨ Nâng chất lượng AI", "✍️ Nhập yêu cầu riêng"],
        ["⬅️ Về menu ảnh", "🏠 Menu chính"],
    ]
    assert "✨ Chỉnh sửa AI" not in [label for row in edit_rows for label in row]

    action_callbacks = [button.callback_data for row in bot.image_editor_action_keyboard("vi").inline_keyboard for button in row]
    preset_callbacks = [button.callback_data for row in bot.image_editor_preset_keyboard("vi").inline_keyboard for button in row]
    overlay_callbacks = [button.callback_data for row in bot.image_editor_overlay_keyboard("vi").inline_keyboard for button in row]
    assert "imgtool|edit_ai_menu" not in action_callbacks
    assert "imgtool|edit_back_choice" in action_callbacks
    assert "imgtool|edit_back_choice" in preset_callbacks
    assert "imgtool|edit_back_choice" in overlay_callbacks


def test_image_enhance_preview():
    ok, output, size_text, preset = bot.process_image_local_editor_bytes(_editor_test_image_bytes(), "photo_clear_detail")
    assert ok is True
    assert output.startswith(b"\x89PNG")
    assert size_text == "640x480"
    assert preset == "photo_clear_detail"


def test_image_preset_clear_detail():
    preset = bot.IMAGE_EDITOR_PRESETS["photo_clear_detail"]
    assert preset["contrast"] > 1
    assert preset["sharpness"] > 1
    assert bot.image_editor_preset_label("photo_clear_detail") == "Ảnh rõ và chi tiết"


def test_image_crop_ratios():
    source = _editor_test_image_bytes((800, 600))
    for ratio, expected in {"1:1": "1024x1024", "4:5": "1080x1350", "9:16": "1080x1920", "16:9": "1920x1080"}.items():
        ok, output, size_text, method = bot.process_image_local_resize_bytes(source, ratio, "crop")
        assert ok is True
        assert output.startswith(b"\x89PNG")
        assert size_text == expected
        assert method == "crop"


def test_video_enhance_menu():
    labels = [button.text for row in bot.video_editor_menu_keyboard("vi").inline_keyboard for button in row]
    assert "🪄 Chỉnh màu video" in labels
    assert "✂️ Cắt / Đổi tỉ lệ video" in labels
    assert "📱 Làm video dọc 9:16" in labels
    assert "🔠 Thêm chữ / watermark" in labels
    assert "🎞 Tăng nét video cơ bản" in labels


def test_video_preset_clear():
    payload = {"preset": "video_clear"}
    filter_value, is_complex = local_worker.video_editor_filter(payload)
    assert "eq=" in filter_value
    assert "unsharp=" in filter_value
    assert is_complex is False


def test_video_crop_9_16():
    filter_value, is_complex = local_worker.video_editor_filter({"ratio": "9:16", "method": "crop", "preset": "video_clear"})
    assert "scale=720:1280" in filter_value
    assert "crop=720:1280" in filter_value
    assert is_complex is False


def test_video_blur_background():
    filter_value, is_complex = local_worker.video_editor_filter({"ratio": "9:16", "method": "blur", "preset": "video_clear"})
    assert "gblur=sigma=28" in filter_value
    assert "overlay=(W-w)/2:(H-h)/2" in filter_value
    assert is_complex is True


def test_add_text_to_image():
    ok, output, size_text, _preset = bot.process_image_local_editor_bytes(
        _editor_test_image_bytes(), "photo_clear_detail", overlay_text="TOAN AAS local editor"
    )
    assert ok is True
    assert output.startswith(b"\x89PNG")
    assert size_text == "640x480"


def test_add_watermark_to_image():
    logo = _editor_test_image_bytes((120, 60), (20, 220, 180))
    ok, output, size_text, _preset = bot.process_image_local_editor_bytes(
        _editor_test_image_bytes(), "product_clean", logo_bytes=logo
    )
    assert ok is True
    assert output.startswith(b"\x89PNG")
    assert size_text == "640x480"


def test_add_text_to_video_guard_or_render():
    filter_value, _is_complex = local_worker.video_editor_filter({"preset": "video_clear", "overlay_text": "TOAN AAS"})
    assert "drawtext=" in filter_value
    assert "TOAN AAS" in filter_value
    source = bot_source_text()
    assert 'job_type="video_local_edit"' in source


def test_local_worker_offline_guard(monkeypatch):
    monkeypatch.setattr(bot, "local_worker_status_payload", lambda: {
        "enabled": True,
        "poll_enabled": True,
        "token_configured": True,
        "connected": False,
    })
    assert bot.video_editor_worker_ready() is False
    monkeypatch.setattr(bot, "local_worker_status_payload", lambda: {
        "enabled": True,
        "poll_enabled": True,
        "token_configured": True,
        "connected": True,
    })
    assert bot.video_editor_worker_ready() is True


def test_no_provider_called_in_v1():
    source = bot_source_text()
    editor_source = source_between(source, "IMAGE_EDITOR_WEB_ROUTE_TEMPLATE", "def image_resize_method_label")
    video_source = source_between(source, "async def submit_local_video_editor_job", "async def handle_video_upload_callback")
    for forbidden in ["shopaikey_image", "shopaikey_video", "REPLICATE_API_TOKEN", "OPENAI_API_KEY"]:
        assert forbidden not in editor_source
        assert forbidden not in video_source
    assert "create_local_worker_job" in video_source


def test_no_charge_before_confirm():
    source = bot_source_text()
    editor_source = source_between(source, "IMAGE_EDITOR_WEB_ROUTE_TEMPLATE", "def image_resize_method_label")
    video_source = source_between(source, "async def submit_local_video_editor_job", "async def handle_video_upload_callback")
    for charge_call in ["spend_fixed_credit_info", "deduct", "charge_user", "refund_charged_credit"]:
        assert charge_call not in editor_source
        assert charge_call not in video_source
    assert "xu_cost=0" in video_source


def test_video_prompt_engine_v10_strength_controls_are_prompt_only():
    callbacks = [
        button.callback_data
        for row in bot.guided_video_result_keyboard("promptvideo", "vi").inline_keyboard
        for button in row
    ]
    for strength in ("quick", "director", "viral", "provider_safe", "premium"):
        assert f"promptvideo|strength|{strength}" in callbacks

    plan = bot.structured_video_plan(
        {
            "selected_prompt": "TOAN AAS AI automation business promo, 15 seconds",
            "prompt_strength": "premium",
            "selected_motion": "slow push-in",
            "selected_music": "modern electronic",
        },
        "promptvideo",
    )
    assert plan["intent"]["prompt_strength"] == "premium"
    assert "[Global Vision & Tone]" in plan["prompt"]
    assert "[Shot Breakdown]" in plan["prompt"]
    assert "[Audio / SFX]" in plan["prompt"]
