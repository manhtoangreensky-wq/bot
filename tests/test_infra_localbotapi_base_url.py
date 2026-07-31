"""INFRA.LOCALBOTAPI - configurable Telegram Bot API base URL.

Gate for the self-hosted (local) Bot API server work:
  * ENV unset  -> byte-for-byte today's cloud behaviour and today's ~20 MB wall.
  * ENV set    -> requests target the configured base, the single-source-of-truth
                  intake ceiling rises with it, diagnostics tell the truth.
  * base down  -> accurate Vietnamese "chua tru Xu" copy, zero charge, and no
                  silent fallback to the cloud endpoint.

No network, no provider calls, no wallet mutations.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import bot


REPO_ROOT = Path(__file__).resolve().parents[1]

CLOUD_BASE = "https://api.telegram.org/bot"
CLOUD_FILE_BASE = "https://api.telegram.org/file/bot"


def _fresh_constants(**env_overrides) -> dict:
    """Import bot.py in a clean subprocess and read the import-time constants."""
    env = dict(os.environ)
    env.pop("TELEGRAM_API_BASE_URL", None)
    env.pop("SUBDUB_MAX_INPUT_MB", None)
    env.pop("SUBDUB_TELEGRAM_DOWNLOAD_LIMIT_MB", None)
    tmp_root = REPO_ROOT / ".pytest_tmp" / "localbotapi_env"
    tmp_root.mkdir(parents=True, exist_ok=True)
    env.setdefault("DB_PATH", str(tmp_root / "probe.db"))
    env.setdefault("WEBAPP_SESSION_DB_PATH", str(tmp_root / "probe_sessions.db"))
    env.update({key: str(value) for key, value in env_overrides.items()})
    code = (
        "import json, bot;"
        "print('<<<'+json.dumps({"
        "'local_enabled': bot.telegram_local_api_enabled(),"
        "'source': bot.telegram_api_source_label(),"
        "'urls': list(bot.telegram_api_urls()),"
        "'download_limit_mb': int(bot.SUBDUB_TELEGRAM_DOWNLOAD_LIMIT_MB),"
        "'max_input_mb': int(bot.SUBDUB_MAX_INPUT_MB),"
        "'effective_limit_mb': int(bot.subdub_input_limit_mb(False)),"
        "})+'>>>')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if "<<<" not in result.stdout:
        pytest.fail(f"bot import probe failed rc={result.returncode}\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}")
    payload = result.stdout.split("<<<", 1)[1].split(">>>", 1)[0]
    return json.loads(payload)


# ─────────────────────────── pure helpers ────────────────────────────────────

def test_normalize_root_accepts_root_bot_and_file_bot_forms():
    assert bot.normalize_telegram_api_root("") == ""
    assert bot.normalize_telegram_api_root("   ") == ""
    assert bot.normalize_telegram_api_root("https://tg.example.com") == "https://tg.example.com"
    assert bot.normalize_telegram_api_root("https://tg.example.com/") == "https://tg.example.com"
    assert bot.normalize_telegram_api_root("https://tg.example.com/bot") == "https://tg.example.com"
    assert bot.normalize_telegram_api_root("https://tg.example.com/file/bot") == "https://tg.example.com"
    assert bot.normalize_telegram_api_root("tg.example.com") == "https://tg.example.com"


def test_normalize_root_rejects_remote_cleartext_before_credentials_are_used():
    with pytest.raises(ValueError, match="HTTPS"):
        bot.normalize_telegram_api_root("http://tg.example.com")


@pytest.mark.parametrize(
    "value",
    (
        "http://127.0.0.1:8081",
        "http://[::1]:8081",
        "http://localhost:8081",
    ),
)
def test_normalize_root_allows_explicit_loopback_http(value):
    assert bot.normalize_telegram_api_root(value) == value


@pytest.mark.parametrize(
    "value",
    (
        "http://localhost.example.com",
        "ftp://tg.example.com",
        "https://user:pass@tg.example.com",
        "https://tg.example.com?token=leak",
        "https://tg.example.com#fragment",
    ),
)
def test_normalize_root_rejects_ambiguous_or_unsafe_urls(value):
    with pytest.raises(ValueError):
        bot.normalize_telegram_api_root(value)


def test_cloud_root_is_never_treated_as_local(monkeypatch):
    monkeypatch.setattr(bot, "TELEGRAM_API_ROOT", bot.TELEGRAM_CLOUD_API_ROOT)
    assert bot.telegram_local_api_enabled() is False
    assert bot.telegram_api_source_label() == "cloud_bot_api"


def test_env_unset_targets_cloud_endpoint_and_sends_no_secret(monkeypatch):
    monkeypatch.setattr(bot, "TELEGRAM_API_ROOT", "")
    monkeypatch.setattr(bot, "TELEGRAM_API_PROXY_SECRET", "should-never-be-sent")
    assert bot.telegram_local_api_enabled() is False
    assert bot.telegram_api_urls() == (CLOUD_BASE, CLOUD_FILE_BASE)
    assert bot.telegram_api_source_label() == "cloud_bot_api"
    assert bot.telegram_api_proxy_headers() == {}


def test_env_set_targets_configured_base_and_sends_secret(monkeypatch):
    monkeypatch.setattr(bot, "TELEGRAM_API_ROOT", "https://tg.example.com")
    monkeypatch.setattr(bot, "TELEGRAM_API_PROXY_SECRET", "s3cr3t")
    monkeypatch.setattr(bot, "TELEGRAM_API_PROXY_SECRET_HEADER", "X-Toanaas-Proxy-Secret")
    assert bot.telegram_local_api_enabled() is True
    assert bot.telegram_api_urls() == (
        "https://tg.example.com/bot",
        "https://tg.example.com/file/bot",
    )
    assert bot.telegram_api_source_label() == "local_bot_api"
    assert bot.telegram_api_proxy_headers() == {"X-Toanaas-Proxy-Secret": "s3cr3t"}


def test_application_builder_uses_configured_base(monkeypatch):
    monkeypatch.setattr(bot, "TELEGRAM_API_ROOT", "https://tg.example.com")
    monkeypatch.setattr(bot, "TELEGRAM_API_PROXY_SECRET", "s3cr3t")
    monkeypatch.setattr(bot, "TELEGRAM_TOKEN", "123456:AAHtest-token-value-for-builder-only")
    app = bot.build_telegram_application()
    assert app.bot.base_url.startswith("https://tg.example.com/bot")
    assert app.bot.base_file_url.startswith("https://tg.example.com/file/bot")
    assert "api.telegram.org" not in app.bot.base_url


def test_application_builder_default_stays_on_cloud(monkeypatch):
    monkeypatch.setattr(bot, "TELEGRAM_API_ROOT", "")
    monkeypatch.setattr(bot, "TELEGRAM_TOKEN", "123456:AAHtest-token-value-for-builder-only")
    app = bot.build_telegram_application()
    assert app.bot.base_url.startswith(CLOUD_BASE)
    assert app.bot.base_file_url.startswith(CLOUD_FILE_BASE)


# ─────────────────────────── intake ceiling ──────────────────────────────────

def test_cloud_ceiling_cannot_be_raised_by_env():
    """The 20 MB wall is Telegram's, not ours: ENV must not be able to fake it."""
    fresh = _fresh_constants(SUBDUB_TELEGRAM_DOWNLOAD_LIMIT_MB="500", SUBDUB_MAX_INPUT_MB="500")
    assert fresh["local_enabled"] is False
    assert fresh["source"] == "cloud_bot_api"
    assert fresh["urls"] == [CLOUD_BASE, CLOUD_FILE_BASE]
    assert fresh["download_limit_mb"] == 20
    assert fresh["max_input_mb"] == 50
    assert fresh["effective_limit_mb"] == 20


def test_default_unset_env_is_unchanged_from_today():
    fresh = _fresh_constants()
    assert fresh["local_enabled"] is False
    assert fresh["download_limit_mb"] == 20
    assert fresh["max_input_mb"] == 50
    assert fresh["effective_limit_mb"] == 20


def test_local_base_raises_advertised_and_enforced_ceiling_together():
    fresh = _fresh_constants(TELEGRAM_API_BASE_URL="https://tg.example.com")
    assert fresh["local_enabled"] is True
    assert fresh["source"] == "local_bot_api"
    assert fresh["urls"] == ["https://tg.example.com/bot", "https://tg.example.com/file/bot"]
    assert fresh["download_limit_mb"] == 500
    assert fresh["max_input_mb"] == 500
    # single source of truth: advertised == enforced == min(both)
    assert fresh["effective_limit_mb"] == 500


def test_local_base_ceiling_is_env_tunable_but_hard_capped():
    fresh = _fresh_constants(
        TELEGRAM_API_BASE_URL="https://tg.example.com",
        SUBDUB_MAX_INPUT_MB="9000",
        SUBDUB_TELEGRAM_DOWNLOAD_LIMIT_MB="9000",
    )
    assert fresh["download_limit_mb"] == 2000
    assert fresh["max_input_mb"] == 2000
    assert fresh["effective_limit_mb"] == 2000


def test_effective_limit_stays_min_of_the_two_constants(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_MAX_INPUT_MB", 120)
    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_DOWNLOAD_LIMIT_MB", 300)
    assert bot.subdub_input_limit_mb(False) == 120
    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_DOWNLOAD_LIMIT_MB", 80)
    assert bot.subdub_input_limit_mb(True) == 80


# ─────────────────────────── truthful diagnostics ────────────────────────────

def test_diagnostics_report_cloud_source_when_env_unset(monkeypatch):
    monkeypatch.setattr(bot, "TELEGRAM_API_ROOT", "")
    fields = bot.subdub_input_save_debug_fields(
        {"ok": False, "telegram_download_method": "bot_api_direct", "detail": "telegram_download_failed:timeout"},
        {},
    )
    assert fields["large_media_intake_supported"] is False
    assert fields["large_media_intake_source"] == ""
    assert fields["telegram_api_source"] == "cloud_bot_api"


def test_diagnostics_report_local_source_when_env_set(monkeypatch):
    monkeypatch.setattr(bot, "TELEGRAM_API_ROOT", "https://tg.example.com")
    fields = bot.subdub_input_save_debug_fields(
        {"ok": True, "file_saved": True, "exists": True, "size": 40 * 1024 * 1024,
         "telegram_download_method": "bot_api_direct"},
        {},
    )
    assert fields["large_media_intake_supported"] is True
    assert fields["large_media_intake_source"] == "local_bot_api"
    assert fields["telegram_api_source"] == "local_bot_api"


def test_runtime_status_payload_exposes_api_source(monkeypatch):
    monkeypatch.setattr(bot, "TELEGRAM_API_ROOT", "https://tg.example.com")
    payload = bot.subdub_runtime_status_payload()
    assert payload["telegram_api_source"] == "local_bot_api"
    assert payload["large_media_intake_supported"] is True
    text = bot.subdub_runtime_status_text(payload)
    assert "local_bot_api" in text


# ─────────────────────────── degraded mode ───────────────────────────────────

def test_unreachable_base_is_classified_and_never_silently_cloud():
    assert bot.subdub_telegram_api_base_unreachable("telegram_download_failed:network") is True
    assert bot.subdub_telegram_api_base_unreachable("ConnectError: connection refused") is True
    assert bot.subdub_telegram_api_base_unreachable("") is False
    assert bot.subdub_telegram_api_base_unreachable("bad request: chat not found") is False


def test_unreachable_base_shows_no_charge_copy_and_hides_endpoint():
    text = bot.subdub_input_save_failure_public_text(
        {"ok": False, "input_save_blocker": "telegram_api_base_unreachable",
         "detail": "telegram_download_failed:network https://tg.example.com"},
        "vi",
    )
    assert "chưa trừ Xu" in text
    assert "tg.example.com" not in text
    assert "http" not in text.lower()
    assert "bot_api" not in text.lower()


def test_oversize_on_local_api_uses_the_new_limit_in_customer_copy(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_DOWNLOAD_LIMIT_MB", 300)
    text = bot.subdub_input_save_failure_public_text(
        {"ok": False, "telegram_download_limit_hit": True, "input_save_blocker": "video_too_large"},
        "vi",
    )
    assert "300 MB" in text
    assert "chưa trừ Xu" in text


def test_business_raw_api_follows_bot_base_url(monkeypatch):
    from types import SimpleNamespace

    import services.telegram_business_support as tbs

    local_bot = SimpleNamespace(base_url="https://tg.example.com/bot123456:AAH", token="123456:AAH")
    assert tbs.raw_bot_api_endpoint(local_bot, "sendMessage") == "https://tg.example.com/bot123456:AAH/sendMessage"

    cloud_bot = SimpleNamespace(base_url="https://api.telegram.org/bot123456:AAH", token="123456:AAH")
    assert tbs.raw_bot_api_endpoint(cloud_bot, "sendMessage") == "https://api.telegram.org/bot123456:AAH/sendMessage"

    monkeypatch.setenv("TELEGRAM_API_PROXY_SECRET", "s3cr3t")
    assert tbs.raw_bot_api_headers("https://api.telegram.org/bot1/sendMessage") == {}
    assert tbs.raw_bot_api_headers("https://tg.example.com/bot1/sendMessage") == {
        "X-Toanaas-Proxy-Secret": "s3cr3t"
    }


def test_business_raw_api_rejects_remote_http_before_request():
    from types import SimpleNamespace

    import services.telegram_business_support as tbs

    local_bot = SimpleNamespace(base_url="http://tg.example.com/bot123456:AAH", token="123456:AAH")
    with pytest.raises(ValueError, match="HTTPS"):
        tbs.raw_bot_api_endpoint(local_bot, "sendMessage")


def test_business_raw_api_custom_hook_cannot_bypass_transport_policy():
    import asyncio

    import services.telegram_business_support as tbs

    class UnsafeBot:
        base_url = "http://tg.example.com/bot123456:AAH"
        token = "123456:AAH"
        called = False

        async def raw_bot_api_request(self, method, payload):
            self.called = True
            return {"ok": True}

    unsafe = UnsafeBot()
    with pytest.raises(ValueError, match="HTTPS"):
        asyncio.run(tbs.raw_bot_api_request(unsafe, "sendMessage", {"text": "probe"}))
    assert unsafe.called is False


def test_no_provider_or_wallet_symbols_touched_by_this_change():
    """Scope guard: this task must not reach into providers, wallet or PayOS."""
    diff = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if diff.returncode != 0:
        pytest.skip("git diff unavailable in this environment")
    changed = {line.strip().replace("\\", "/") for line in diff.stdout.splitlines() if line.strip()}
    if not changed:
        pytest.skip("no diff against origin/main (already merged or detached)")
    forbidden_exact = {"remote_worker.py", "local_worker.py", ".gitignore", "AGENTS.md"}
    forbidden_prefixes = ("providers/", ".agents/", ".codex/")
    for path in changed:
        assert path not in forbidden_exact, f"out-of-scope file changed: {path}"
        assert not path.startswith(forbidden_prefixes), f"out-of-scope file changed: {path}"


# ────────────── --local mode media fetch (the real 20 MB wall remover) ───────

def test_local_media_url_from_raw_server_path(monkeypatch):
    monkeypatch.setattr(bot, "TELEGRAM_API_ROOT", "https://tg.example.com")
    raw = "/var/lib/telegram-bot-api/123456:AAH/videos/file_0"
    assert bot.telegram_local_media_url(raw) == (
        "https://tg.example.com/localfile/123456:AAH/videos/file_0"
    )


def test_local_media_url_from_ptb_concatenated_url(monkeypatch):
    """PTB prefixes base_file_url when it cannot see the path locally."""
    monkeypatch.setattr(bot, "TELEGRAM_API_ROOT", "https://tg.example.com")
    ptb = (
        "https://tg.example.com/file/bot123456:AAH"
        "//var/lib/telegram-bot-api/123456:AAH/videos/file_1"
    )
    assert bot.telegram_local_media_url(ptb) == (
        "https://tg.example.com/localfile/123456:AAH/videos/file_1"
    )


def test_local_media_url_is_empty_on_cloud_and_on_traversal(monkeypatch):
    monkeypatch.setattr(bot, "TELEGRAM_API_ROOT", "")
    assert bot.telegram_local_media_url("/var/lib/telegram-bot-api/x/videos/file_0") == ""
    monkeypatch.setattr(bot, "TELEGRAM_API_ROOT", "https://tg.example.com")
    assert bot.telegram_local_media_url("") == ""
    assert bot.telegram_local_media_url("videos/file_0") == ""
    assert bot.telegram_local_media_url("/var/lib/telegram-bot-api/../../etc/passwd") == ""


class _FakeResponse:
    def __init__(self, status_code=200, chunks=(b"abc",)):
        self.status_code = status_code
        self._chunks = chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def aiter_bytes(self, chunk_size=0):
        for chunk in self._chunks:
            yield chunk


class _FakeClient:
    calls = []

    def __init__(self, *args, **kwargs):
        self._response = _FakeClient.response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def stream(self, method, url, headers=None):
        _FakeClient.calls.append({"method": method, "url": url, "headers": dict(headers or {})})
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _install_fake_httpx(monkeypatch, response):
    _FakeClient.calls = []
    _FakeClient.response = response
    monkeypatch.setattr(bot.httpx, "AsyncClient", _FakeClient)


def test_local_media_fetch_sends_shared_secret_and_returns_bytes(monkeypatch):
    import asyncio

    monkeypatch.setattr(bot, "TELEGRAM_API_ROOT", "https://tg.example.com")
    monkeypatch.setattr(bot, "TELEGRAM_API_PROXY_SECRET", "s3cr3t")
    monkeypatch.setattr(bot, "TELEGRAM_API_PROXY_SECRET_HEADER", "X-Toanaas-Proxy-Secret")
    _install_fake_httpx(monkeypatch, _FakeResponse(200, (b"aa", b"bb")))
    out = asyncio.run(
        bot.telegram_local_media_fetch("https://tg.example.com/localfile/1:A/videos/file_0", 1024, 10)
    )
    assert out == b"aabb"
    assert _FakeClient.calls[0]["headers"] == {"X-Toanaas-Proxy-Secret": "s3cr3t"}


def test_local_media_fetch_enforces_size_cap(monkeypatch):
    import asyncio

    monkeypatch.setattr(bot, "TELEGRAM_API_ROOT", "https://tg.example.com")
    _install_fake_httpx(monkeypatch, _FakeResponse(200, (b"x" * 10, b"x" * 10)))
    with pytest.raises(RuntimeError) as excinfo:
        asyncio.run(bot.telegram_local_media_fetch("https://tg.example.com/localfile/a", 15, 10))
    assert "file is too big" in str(excinfo.value)


def test_local_media_fetch_never_leaks_the_token_url_in_errors(monkeypatch):
    import asyncio

    monkeypatch.setattr(bot, "TELEGRAM_API_ROOT", "https://tg.example.com")
    url = "https://tg.example.com/localfile/123456:AAHsecrettoken/videos/file_0"
    _install_fake_httpx(monkeypatch, RuntimeError("boom " + url))
    with pytest.raises(RuntimeError) as excinfo:
        asyncio.run(bot.telegram_local_media_fetch(url, 1024, 10))
    message = str(excinfo.value)
    assert "AAHsecrettoken" not in message
    assert "https://" not in message

    _install_fake_httpx(monkeypatch, _FakeResponse(403, ()))
    with pytest.raises(RuntimeError) as excinfo2:
        asyncio.run(bot.telegram_local_media_fetch(url, 1024, 10))
    assert "AAHsecrettoken" not in str(excinfo2.value)
    assert str(excinfo2.value) == "telegram_download_failed:api:forbidden"


def test_local_media_fetch_maps_status_codes_to_degraded_reasons(monkeypatch):
    import asyncio

    monkeypatch.setattr(bot, "TELEGRAM_API_ROOT", "https://tg.example.com")
    for status, expected in ((404, "not_found"), (502, "network"), (418, "api")):
        _install_fake_httpx(monkeypatch, _FakeResponse(status, ()))
        with pytest.raises(RuntimeError) as excinfo:
            asyncio.run(bot.telegram_local_media_fetch("https://tg.example.com/localfile/a", 99, 5))
        assert expected in str(excinfo.value)
        if status >= 500:
            assert bot.subdub_telegram_api_base_unreachable(str(excinfo.value)) is True
