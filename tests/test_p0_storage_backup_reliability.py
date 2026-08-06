import inspect
import asyncio
import os
import sqlite3
from types import SimpleNamespace

import pytest
import bot


def test_storage_tasks_start_before_telegram_initialization_and_create_real_backups():
    source = inspect.getsource(bot.lifespan)
    task_marker = "tg_auto_backup_task = asyncio.create_task(auto_backup_loop())"
    telegram_marker = "tg_app = Application.builder().token(TELEGRAM_TOKEN).build()"
    assert task_marker in source
    assert source.index(task_marker) < source.index(telegram_marker)
    loop_start = source.index("async def auto_backup_loop():")
    loop_end = source.index(task_marker, loop_start)
    loop_source = source[loop_start:loop_end]
    assert "create_db_backup_now" in loop_source
    assert "Không gửi file DB qua Telegram" in loop_source


def test_webhook_returns_service_unavailable_when_telegram_not_ready(monkeypatch):
    monkeypatch.setattr(bot, "tg_app", object())
    monkeypatch.setattr(bot, "TELEGRAM_APP_READY", False, raising=False)
    monkeypatch.setattr(bot, "TELEGRAM_WEBHOOK_SECRET", "")
    request = SimpleNamespace(headers={})
    with pytest.raises(bot.HTTPException) as exc_info:
        asyncio.run(bot.telegram_webhook(request))
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Telegram app is not ready"


def test_create_db_backup_now_creates_verified_sqlite_file(tmp_path, monkeypatch):
    db_path = tmp_path / "live.db"
    backup_dir = tmp_path / "backups"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO events(value) VALUES ('ok')")
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "DB_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(bot, "DATA_PERSISTENCE_MODE", "sqlite")
    monkeypatch.setattr(bot, "DB_BACKUP_KEEP_LAST", 3)
    monkeypatch.setattr(bot, "set_system_setting", None, raising=False)

    result = bot.create_db_backup_now("system", "pytest-auto")

    assert result["ok"] is True
    backup_path = backup_dir / result["filename"]
    assert backup_path.exists()
    assert backup_path.suffix == ".sqlite3"
    with sqlite3.connect(backup_path) as conn:
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT value FROM events").fetchone() == ("ok",)


def test_backup_retention_keeps_three_total_startup_and_auto_files(tmp_path, monkeypatch):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    names = (
        "toandaas_system_20260801_000000_startup.db",
        "toandaas_system_20260802_000000.sqlite3",
        "toandaas_system_20260803_000000_startup.db",
        "toandaas_system_20260804_000000.sqlite3",
    )
    for index, name in enumerate(names):
        path = backup_dir / name
        path.write_bytes(b"backup")
        os.utime(path, (index, index))
    monkeypatch.setattr(bot, "DB_BACKUP_DIR", str(backup_dir))

    removed = bot.cleanup_old_db_backups(3)

    remaining = sorted(path.name for path in backup_dir.iterdir())
    assert len(remaining) == 3
    assert removed == [names[0]]
