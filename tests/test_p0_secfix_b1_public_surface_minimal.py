"""SECFIX B1: the unauthenticated HTTP surface must not leak internal facts.

/health, /api/v1/health and /api/v1/metrics-lite are reachable by anyone on
the internet. They may report liveness and nothing else: no provider
inventory, no freeze/maintenance state, no database detail, no build or PID.
The full operator view stays available, but only behind the operator token.

/aichat_test used to print routing internals (intent, permission,
provider_call_allowed, xu_charge_allowed) to any caller; it is now
owner-gated like every other diagnostic command.
"""

from types import SimpleNamespace

from fastapi.testclient import TestClient

import bot

OPERATOR_TOKEN = "secfix-b1-operator-token"

PUBLIC_HEALTH_KEYS = {"status", "version", "timestamp"}
PUBLIC_METRICS_KEYS = {"ok", "time", "db_ok", "queue"}

# Distinctive substrings that must never appear in an unauthenticated body.
INTERNAL_LEAK_MARKERS = (
    "payos",
    "gemini",
    "openai",
    "deepgram",
    "fish_audio",
    "removebg",
    "cutout",
    "freeze",
    "db_file",
    "db_error",
    "data_loss_risk",
    "emergency_lock",
    "maintenance_mode",
    "system_mode",
    "app_version",
    "uptime_seconds",
    "telegram_configured",
    "public_base_url",
)


def _init_db(monkeypatch, tmp_path, name="secfix_b1.db"):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / name))
    monkeypatch.setattr(bot, "DB_BACKUP_DIR", str(tmp_path / "db_backups"))
    monkeypatch.setattr(bot, "DATA_PERSISTENCE_MODE", "sqlite")
    bot.init_db()


def _client(monkeypatch, tmp_path, operator_token=OPERATOR_TOKEN):
    _init_db(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "OPERATOR_API_TOKEN", operator_token)
    return TestClient(bot.fastapi_app)


class _FakeMessage:
    def __init__(self, text="/aichat_test xin chao"):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


def _update(uid, text="/aichat_test xin chao"):
    message = _FakeMessage(text)
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=uid, username=f"u{uid}", first_name="Khach"),
        effective_chat=SimpleNamespace(id=uid),
        effective_message=message,
        message=message,
        callback_query=None,
    )


def test_public_health_payload_exposes_only_liveness(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    payload = bot.public_health_payload()
    assert set(payload) == PUBLIC_HEALTH_KEYS
    assert payload["status"] in {"ok", "degraded"}


def test_public_health_endpoints_hide_provider_and_infra(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    for path in ("/health", "/api/v1/health"):
        res = client.get(path)
        assert res.status_code == 200, path
        assert set(res.json()) == PUBLIC_HEALTH_KEYS, path
        lowered = res.text.lower()
        for marker in INTERNAL_LEAK_MARKERS:
            assert marker not in lowered, f"{path} leaked '{marker}'"


def test_operator_token_still_sees_full_health(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    res = client.get("/health", headers={"x-operator-token": OPERATOR_TOKEN})
    assert res.status_code == 200
    body = res.json()
    assert body.get("service") == "TOAN AAS"
    for key in ("payos_configured", "deepgram_configured", "system_mode", "db_file"):
        assert key in body, key


def test_wrong_operator_token_gets_public_shape_only(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    res = client.get("/health", headers={"x-operator-token": "not-the-token"})
    assert res.status_code == 200
    assert set(res.json()) == PUBLIC_HEALTH_KEYS


def test_unset_operator_token_cannot_unlock_health(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path, operator_token="")
    res = client.get("/health", headers={"x-operator-token": "anything"})
    assert res.status_code == 200
    assert set(res.json()) == PUBLIC_HEALTH_KEYS


def test_public_metrics_lite_hides_pid_and_provider_freeze(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    res = client.get("/api/v1/metrics-lite")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == PUBLIC_METRICS_KEYS
    assert "providers" not in body
    assert "runtime" not in body
    assert "pid" not in res.text.lower()


def test_operator_metrics_lite_keeps_full_detail(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    res = client.get("/api/v1/metrics-lite", headers={"x-operator-token": OPERATOR_TOKEN})
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body["providers"]["shopaikey_freeze"], bool)
    assert body["runtime"]["pid"]


def test_aichat_test_is_wrapped_by_the_shared_owner_gate():
    source = bot.BOT_SOURCE if hasattr(bot, "BOT_SOURCE") else None
    if source is None:
        from pathlib import Path

        source = Path(bot.__file__).read_text(encoding="utf-8", errors="replace")
    assert "@admin_internal_command\nasync def cmd_aichat_test(" in source


def test_aichat_test_denies_non_owner_without_leaking_internals(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "ADMIN_IDS", {"777000"})
    monkeypatch.setattr(bot, "OWNER_IDS", set())
    update = _update(424242)
    import asyncio

    asyncio.run(bot.cmd_aichat_test(update, SimpleNamespace(args=["xin", "chao"])))
    joined = " ".join(update.message.replies).lower()
    assert joined, "non-owner should still receive a safe reply"
    for leaked in ("intent:", "permission:", "action guard", "provider call allowed", "xu charge allowed"):
        assert leaked not in joined, f"non-owner saw internal field '{leaked}'"


def test_aichat_test_still_works_for_owner(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "ADMIN_IDS", {"424242"})
    monkeypatch.setattr(bot, "OWNER_IDS", set())
    update = _update(424242)
    import asyncio

    asyncio.run(bot.cmd_aichat_test(update, SimpleNamespace(args=["xin", "chao"])))
    joined = " ".join(update.message.replies)
    assert "AI Chatbot test" in joined
