import asyncio
import os
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

import bot


def _init_db(monkeypatch, tmp_path, name="p0_17c4.db"):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / name))
    monkeypatch.setattr(bot, "DB_BACKUP_DIR", str(tmp_path / "db_backups"))
    monkeypatch.setattr(bot, "DATA_PERSISTENCE_MODE", "sqlite")
    bot.init_db()


def _security_events():
    conn = bot.db_connect()
    try:
        return conn.execute(
            "SELECT event_type,severity,user_id,detail FROM security_events ORDER BY id"
        ).fetchall()
    finally:
        conn.close()


def _keyboard_labels(markup):
    return [[button.text for button in row] for row in markup.inline_keyboard]


class FakeMessage:
    def __init__(self, text="/db_status"):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class FakeBot:
    def __init__(self):
        self.documents = []

    async def send_document(self, **kwargs):
        self.documents.append(kwargs)


class FakeTelegramApp:
    def __init__(self):
        self.bot = SimpleNamespace(name="fake-bot")
        self.updates = []

    async def process_update(self, update):
        self.updates.append(update)


class FakeWebhookBot:
    def __init__(self):
        self.webhook_kwargs = None

    async def set_webhook(self, **kwargs):
        self.webhook_kwargs = dict(kwargs)

    async def get_webhook_info(self):
        return SimpleNamespace(
            url=bot.expected_telegram_webhook_url(),
            pending_update_count=0,
            last_error_date="",
            last_error_message="",
            max_connections=40,
            allowed_updates=None,
            ip_address="",
        )


def _update(uid=999, text="/db_status"):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=uid, username=f"user{uid}", first_name="Admin"),
        effective_chat=SimpleNamespace(id=uid),
        message=FakeMessage(text),
    )


def test_telegram_webhook_secret_rejects_missing_bad_token_and_logs_ip_user_agent(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "TELEGRAM_WEBHOOK_SECRET", "telegram-webhook-secret-c4")
    monkeypatch.setattr(bot, "tg_app", None)
    client = TestClient(bot.fastapi_app)

    missing = client.post(
        bot.TELEGRAM_WEBHOOK_PATH,
        json={"update_id": 1},
        headers={"user-agent": "pytest-c4-agent"},
    )
    bad = client.post(
        bot.TELEGRAM_WEBHOOK_PATH,
        json={"update_id": 2},
        headers={
            "x-telegram-bot-api-secret-token": "wrong-c4-token",
            "user-agent": "pytest-c4-agent",
        },
    )

    assert missing.status_code == 401
    assert bad.status_code == 401
    events = _security_events()
    event_types = [row[0] for row in events]
    joined_details = "\n".join(row[3] for row in events)
    assert "telegram_webhook_secret_missing" in event_types
    assert "telegram_webhook_secret_invalid" in event_types
    assert bot.TELEGRAM_WEBHOOK_PATH in joined_details
    assert "pytest-c4-agent" in joined_details
    assert "wrong-c4-token" not in joined_details
    assert "telegram-webhook-secret-c4" not in joined_details


def test_telegram_webhook_secret_accepts_valid_token_and_dev_without_secret(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    fake = FakeTelegramApp()
    monkeypatch.setattr(bot, "tg_app", fake)
    monkeypatch.setattr(bot, "TELEGRAM_WEBHOOK_SECRET", "telegram-webhook-secret-c4")
    monkeypatch.setattr(bot.Update, "de_json", staticmethod(lambda payload, bot_obj: {"payload": payload, "bot": bot_obj}))
    client = TestClient(bot.fastapi_app)

    accepted = client.post(
        bot.TELEGRAM_WEBHOOK_PATH,
        json={"update_id": 3},
        headers={"x-telegram-bot-api-secret-token": "telegram-webhook-secret-c4"},
    )
    assert accepted.status_code == 200
    assert fake.updates and fake.updates[-1]["payload"]["update_id"] == 3

    dev_fake = FakeTelegramApp()
    monkeypatch.setattr(bot, "tg_app", dev_fake)
    monkeypatch.setattr(bot, "TELEGRAM_WEBHOOK_SECRET", "")
    dev_response = client.post(bot.TELEGRAM_WEBHOOK_PATH, json={"update_id": 4})
    assert dev_response.status_code == 200
    assert dev_fake.updates and dev_fake.updates[-1]["payload"]["update_id"] == 4


def test_set_telegram_webhook_includes_secret_token_when_configured(monkeypatch):
    fake_bot = FakeWebhookBot()
    monkeypatch.setattr(bot, "PUBLIC_BASE_URL", "https://bot.example.com")
    monkeypatch.setattr(bot, "TELEGRAM_WEBHOOK_SECRET", "telegram-webhook-secret-c4")

    result = asyncio.run(bot.set_telegram_webhook_takeover(fake_bot))

    assert fake_bot.webhook_kwargs["secret_token"] == "telegram-webhook-secret-c4"
    assert fake_bot.webhook_kwargs["url"] == "https://bot.example.com" + bot.TELEGRAM_WEBHOOK_PATH
    assert "telegram-webhook-secret-c4" not in str(result)


def test_runtime_flags_include_c4_security_fields(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "TELEGRAM_WEBHOOK_SECRET", "telegram-webhook-secret-c4")
    monkeypatch.setattr(bot, "OPERATOR_API_TOKEN", "runtime-token-c4")
    monkeypatch.setattr(bot, "tg_app", None)
    client = TestClient(bot.fastapi_app)

    response = client.get("/runtime", headers={"x-operator-token": "runtime-token-c4"})
    payload = response.json()

    assert response.status_code == 200
    assert payload["public_version"] == "v1.0 Beta"
    assert payload["telegram_webhook_secret_configured"] is True
    assert payload["telegram_webhook_secret_enforced"] is True
    assert payload["db_backup_enabled"] is True
    assert payload["security_event_logging_enabled"] is True
    assert payload["security"]["telegram_webhook_secret_configured"] is True


def test_db_backup_now_creates_safe_filename_retention_and_status(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "DB_BACKUP_KEEP_LAST", 2)
    backup_dir = Path(bot.DB_BACKUP_DIR)
    backup_dir.mkdir(parents=True, exist_ok=True)
    old_a = backup_dir / "toanaas_system_20260101_000000.sqlite3"
    old_b = backup_dir / "toanaas_system_20260101_000001.sqlite3"
    old_a.write_bytes(b"old-a")
    old_b.write_bytes(b"old-b")
    os.utime(old_a, (1, 1))
    os.utime(old_b, (2, 2))

    result = bot.create_db_backup_now("999", "pytest-c4")

    assert result["ok"] is True
    assert re.match(r"^toanaas_system_\d{8}_\d{6}(?:_\d+)?\.sqlite3$", result["filename"])
    assert Path(result["path"]).exists()
    assert Path(result["path"]).parent == backup_dir
    assert not bot.db_backup_dir_is_public(str(backup_dir))
    assert not old_a.exists()
    assert bot.latest_db_backup_info()["filename"] == result["filename"]
    status_text = bot.db_status_admin_text()
    assert "DB trạng thái" in status_text
    assert str(tmp_path) not in status_text


def test_db_status_backup_commands_are_admin_only_and_log_events(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "ADMIN_IDS", {"999"})
    monkeypatch.setattr(bot, "OWNER_IDS", set())
    monkeypatch.setattr(bot, "BACKUP_MAX_BYTES", 0)
    public_update = _update(uid=123, text="/db_status")
    admin_update = _update(uid=999, text="/backup_db_now")
    context = SimpleNamespace(args=[], bot=FakeBot())

    asyncio.run(bot.cmd_db_status(public_update, context))
    assert public_update.message.replies and "không có quyền" in public_update.message.replies[0][0]
    asyncio.run(bot.cmd_db_status(admin_update, context))
    asyncio.run(bot.cmd_backup_db(admin_update, context))

    replies = "\n".join(text for text, _kwargs in admin_update.message.replies)
    assert "DB trạng thái" in replies
    assert "Đã sao lưu DB" in replies
    assert context.bot.documents == []
    event_types = [row[0] for row in _security_events()]
    assert "db_status_viewed" in event_types
    assert "db_backup_created" in event_types


def test_secret_file_risk_check_masks_env_secret_and_public_backup_names(tmp_path):
    (tmp_path / ".env").write_text("TELEGRAM_TOKEN=secret", encoding="utf-8")
    (tmp_path / "PAYOS_CHECKSUM_SECRET.txt").write_text("secret", encoding="utf-8")
    public_dir = tmp_path / "public"
    public_dir.mkdir()
    (public_dir / "customer_backup.sqlite3").write_bytes(b"db")

    result = bot.secret_file_risk_check(str(tmp_path))
    names = "\n".join(item["masked_name"] for item in result["risks"])
    reasons = {item["reason"] for item in result["risks"]}

    assert result["ok"] is False
    assert {"env_file", "secret_like_filename", "public_db_backup"} <= reasons
    assert "PAYOS_CHECKSUM_SECRET" not in names
    assert "customer_backup" not in names


def test_html_escape_for_admin_security_surfaces(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    assert bot.safe_html('<target_id username="x">&') == "&lt;target_id username=&quot;x&quot;&gt;&amp;"
    backup_text = bot.backup_db_result_text({"ok": False, "reason": "<bad&reason>", "backup_dir": "<private/path>"})
    assert "<bad&reason>" not in backup_text
    assert "&lt;bad&amp;reason&gt;" in backup_text

    bot.record_security_event('event<tag>', "medium", {"note": "<unsafe>"}, user_id='u<1>')
    log_text = bot.security_log_text()
    assert "event<tag>" not in log_text
    assert "u<1>" not in log_text
    assert "event&lt;tag&gt;" in log_text


def test_c4_admin_buttons_public_version_and_report_present():
    rows = _keyboard_labels(bot.admin_module_keyboard("security_db"))
    flat = [label for row in rows for label in row]
    report = Path(bot.__file__).resolve().parent / "docs/reports/P0_17C4_WEBHOOK_DB_HTML_SECURITY_EVENTS.md"

    assert ["🗄 DB trạng thái", "💾 Sao lưu DB"] in rows
    assert "🛡 Nhật ký bảo mật" in flat
    assert bot.PUBLIC_VERSION == "v1.0 Beta"
    assert report.exists()


def test_p0_17c4_command_handlers_registered_and_no_payment_core_markers_added():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert 'CommandHandler("db_status", cmd_db_status)' in source
    assert 'CommandHandler("backup_db_now", cmd_backup_db)' in source
    assert 'CommandHandler("security_log", cmd_security_log)' in source
    assert 'callback_data="menu|admin_db_status"' in source
    assert 'callback_data="menu|admin_backup_db"' in source
    assert 'callback_data="menu|admin_security_log"' in source
    assert 'webhook_kwargs["secret_token"] = TELEGRAM_WEBHOOK_SECRET' in source


def test_p0_17c4_static_guard_no_unrelated_files_touched():
    repo = Path(bot.__file__).resolve().parent
    result = subprocess.run(["git", "diff", "--name-only", "origin/main"], cwd=repo, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    changed = {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}
    allowed = {
        "bot.py",
        "docs/reports/P0_17C4_WEBHOOK_DB_HTML_SECURITY_EVENTS.md",
        "tests/test_core.py",
        "tests/test_p0_17a1_admin_control_center_handbook.py",
        "tests/test_p0_4_hard_reset_audio_video_flow.py",
        "tests/test_p0_5_audio_video_addon_button_logic.py",
        "tests/test_p0_17c1_payos_signature_idempotency.py",
        "tests/test_p0_17c2_payos_auto_topup_limits.py",
        "tests/test_p0_17c3_payos_admin_risk_lock_review.py",
        "tests/test_p0_17c4_webhook_db_html_security_events.py",
        "docs/reports/P0_17B14_5_VIDEO_FLOW_ROUTER_BACKSTACK_AUDIT.md",
        "tests/test_p0_17b14_5_video_flow_router_backstack.py",
    }
    assert changed <= allowed
