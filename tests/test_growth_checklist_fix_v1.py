import json
from pathlib import Path

import bot


ROOT = Path(bot.__file__).resolve().parent


def _init_temp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "growth_checklist.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "DB_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(bot, "DATA_PERSISTENCE_MODE", "sqlite")
    monkeypatch.setattr(bot, "DATABASE_URL", "")
    monkeypatch.setattr(bot, "DB_STARTUP_BACKUP_ENABLED", False)
    monkeypatch.setattr(bot, "DB_ALLOW_DESTRUCTIVE_MIGRATION", False)
    monkeypatch.setattr(bot, "DB_STARTUP_BACKUP_PATHS", set())
    monkeypatch.setattr(bot, "DB_STARTUP_PREP_RESULT", {"status": "not_run", "path": "", "created_at": "", "reason": ""})
    monkeypatch.setattr(bot, "DB_STARTUP_BACKUP_RESULT", {"status": "not_run", "path": "", "created_at": "", "reason": ""})
    bot.init_db()
    return db_path


def test_operator_bridge_disabled_is_optional_and_safe():
    result = bot.check_operator_bridge_config(public_base_url="", operator_api_token="", enabled=False)

    assert result["ok"] is True
    assert result["status"] == "disabled"
    assert result["severity"] == "disabled"
    assert result["reason"] == "operator_api_disabled"
    assert "OPERATOR_API_ENABLED=false" in result["safe_message"]
    assert "token" not in result


def test_operator_bridge_enabled_requires_public_url_and_strong_token():
    missing = bot.check_operator_bridge_config(public_base_url="", operator_api_token="", enabled=True)
    assert missing["ok"] is False
    assert missing["status"] == "fail"
    assert "PUBLIC_BASE_URL" in missing["missing"]
    assert "OPERATOR_API_TOKEN" in missing["missing"]

    localhost = bot.check_operator_bridge_config(
        public_base_url="http://localhost:8000",
        operator_api_token="x" * 32,
        enabled=True,
    )
    assert localhost["ok"] is False
    assert localhost["reason"] == "public_base_url_localhost"

    short_token = bot.check_operator_bridge_config(
        public_base_url="https://toanaas.vn",
        operator_api_token="too-short",
        enabled=True,
    )
    assert short_token["ok"] is False
    assert short_token["reason"] == "operator_token_too_short"
    assert "too-short" not in short_token["safe_message"]

    ready = bot.check_operator_bridge_config(
        public_base_url="https://toanaas.vn",
        operator_api_token="x" * 32,
        enabled=True,
    )
    assert ready["ok"] is True
    assert ready["status"] == "pass"


def test_goal_audit_marks_disabled_bridge_as_non_blocking(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "OPERATOR_API_ENABLED", False)
    payload = bot.operator_goal_audit_data("admin")
    bridge_item = next(item for item in payload["requirements"] if item["key"] == "api_commander_bridge")

    assert bridge_item["ok"] is True
    assert bridge_item["status"] == "disabled"
    assert bridge_item["severity"] == "disabled"
    assert bridge_item["soft"] is True
    assert bridge_item not in payload["hard_blockers"]


def test_affiliate_import_creates_defaults_only_after_real_affiliate(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)

    no_data = bot.ensure_growth_content_defaults_after_affiliate_import("admin")
    assert no_data["active_affiliates"] == 0
    assert no_data["created_channel"] is None
    assert no_data["created_campaign"] is None
    assert "no_real_affiliate_data" in no_data["skipped"]

    created, skipped, errors = bot.import_affiliate_links_from_text(
        "admin",
        "https://shorten.asia/toanaas-test (TOAN AAS test affiliate)",
    )
    assert len(created) == 1
    assert skipped == []
    assert errors == []

    defaults = bot.ensure_growth_content_defaults_after_affiliate_import("admin")
    assert defaults["active_affiliates"] == 1
    assert defaults["created_channel"]["status"] == "active"
    assert defaults["created_campaign"]["status"] == "active"

    created_again, skipped_again, errors_again = bot.import_affiliate_links_from_text(
        "admin",
        "https://shorten.asia/toanaas-test (TOAN AAS test affiliate)",
    )
    assert created_again == []
    assert len(skipped_again) == 1
    assert errors_again == []


def test_reference_catalog_seed_warns_without_fake_references():
    catalog_path = ROOT / "data" / "reference_videos" / "catalog.json"
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))

    assert payload["version"] == "1.0"
    assert payload["references"] == []


def test_growth_checklist_command_and_env_registry():
    source = (ROOT / "bot.py").read_text(encoding="utf-8")
    env_text = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "OPERATOR_API_ENABLED=false" in env_text
    assert "CommandHandler(\"admin_import_affiliate_inventory\"" in source
    assert "cmd_admin_import_affiliate_inventory" in source
    assert "Railway không tự đọc được ổ D local" in source
    assert "item.get(\"severity\") == \"disabled\"" in source
    assert "soft\": bridge.get(\"status\") == \"disabled\"" in source
    assert "/api/operator/affiliates/import" in source
    assert "OPERATOR_API_TOKEN" in source
    assert "logger.info(OPERATOR_API_TOKEN" not in source
    assert "logger.warning(OPERATOR_API_TOKEN" not in source
