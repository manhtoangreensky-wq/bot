"""Pytest plugin enforcing zero outbound network / provider calls and isolated sandboxes in provider-free testing.

Governed by: owner-governed-codex, locked-focus-engineering
SPEC_ID: PRODUCT-VIDEO-S00-PROVIDER-FREE-GUARD
"""

from __future__ import annotations

import os
import socket
import urllib.request
from typing import Any, Mapping

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testserver"})
BLOCKED_ATTEMPTS: list[str] = []

AUDITED_CREDENTIAL_ENV_KEYS = frozenset({
    "SHOPAIKEY_API_KEY",
    "KEY4U_API_KEY",
    "KEY4U_VIDEO_AUTH_HEADER_VALUE",
    "FAL_KEY",
    "MINIMAX_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "KLING_ACCESS_KEY",
    "KLING_SECRET_KEY",
    "BOT_INTERNAL_SECRET",
    "CORE_BRIDGE_TOKEN",
    "CORE_BRIDGE_HMAC_SECRET",
    "CORE_BRIDGE_CALLBACK_TOKEN",
    "CORE_BRIDGE_CALLBACK_HMAC_SECRET",
    "WEBAPP_LINK_CALLBACK_TOKEN",
    "WEBAPP_LINK_CALLBACK_HMAC_SECRET",
    "INTERNAL_API_SECRET",
    "TELEGRAM_API_PROXY_SECRET",
})

PRODUCTION_PATH_MARKERS = frozenset({
    "/data/toandaas_system.db",
    "/data/toan_aas.db",
    "/opt/toanaas",
    "/opt/toanaas-worker",
})

_orig_getaddrinfo = socket.getaddrinfo
_orig_create_connection = socket.create_connection
_orig_socket_connect = socket.socket.connect
_orig_urlopen = urllib.request.urlopen


def is_loopback(host: str) -> bool:
    clean = str(host or "").strip().lower()
    return clean in LOOPBACK_HOSTS or clean.startswith("127.") or clean == "::1"


def is_test_token(value: str) -> bool:
    clean = str(value or "").strip().lower()
    if not clean:
        return True
    return clean.startswith(("test", "mock", "fake", "dummy", "stub")) or clean in {"none", "null", "false", "0"}


def verify_no_real_credentials(environ: Mapping[str, str] | None = None) -> None:
    env = os.environ if environ is None else environ
    for key, val in env.items():
        key_upper = key.upper()
        if key_upper in AUDITED_CREDENTIAL_ENV_KEYS or (
            any(term in key_upper for term in ["_API_KEY", "_SECRET", "_TOKEN"])
            and any(p in key_upper for p in ["SHOPAIKEY", "KEY4U", "FAL", "MINIMAX", "OPENAI", "GEMINI", "KLING"])
        ):
            if val and not is_test_token(val):
                raise RuntimeError(
                    f"PROVIDER_FREE_GUARD_BLOCKED: Real-looking provider credential detected in environment: {key}. "
                    "REAL_PROVIDER_CREDENTIAL_REWRITE_ALLOWED=NO. Fail-closed without charge."
                )


def is_production_path(path: str) -> bool:
    clean = str(path or "").replace("\\", "/").strip().lower()
    if not clean:
        return False
    if clean in {":memory:", ""}:
        return False
    if any(m in clean for m in ["pytest_tmp", "tmp", "temp", "scratch"]):
        return False
    if clean.endswith("/toandaas_system.db") and not any(m in clean for m in ["pytest_tmp", "tmp", "temp", "scratch"]):
        return True
    if clean.startswith("/data/") or clean == "/data":
        return True
    if "/opt/toanaas" in clean:
        return True
    return False


def verify_safe_storage_paths(environ: Mapping[str, str] | None = None) -> None:
    env = os.environ if environ is None else environ
    for key in ["DB_PATH", "DB_FILE", "DATABASE_URL", "DATA_DIR", "LINKDL_DATA_DIR", "SQLITE_PATH"]:
        val = env.get(key)
        if val and is_production_path(val):
            raise RuntimeError(
                f"PROVIDER_FREE_GUARD_BLOCKED: Production storage path detected in environment {key}={val}. "
                "Only isolated temp sandbox is permitted in provider-free testing."
            )


def guarded_getaddrinfo(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
    host_str = str(host or "")
    if is_loopback(host_str):
        return _orig_getaddrinfo(host, port, *args, **kwargs)
    record = f"getaddrinfo({host_str}:{port})"
    BLOCKED_ATTEMPTS.append(record)
    raise RuntimeError(f"PROVIDER_FREE_GUARD_BLOCKED: External DNS lookup intercepted: {record}")


def guarded_create_connection(address: tuple[Any, Any], *args: Any, **kwargs: Any) -> Any:
    host, port = address[0], address[1]
    host_str = str(host or "")
    if is_loopback(host_str):
        return _orig_create_connection(address, *args, **kwargs)
    record = f"create_connection({host_str}:{port})"
    BLOCKED_ATTEMPTS.append(record)
    raise RuntimeError(f"PROVIDER_FREE_GUARD_BLOCKED: External connection intercepted: {record}")


def guarded_socket_connect(self: socket.socket, address: Any) -> Any:
    if isinstance(address, (tuple, list)) and len(address) >= 2:
        host, port = address[0], address[1]
        host_str = str(host or "")
        if not is_loopback(host_str):
            record = f"socket.connect({host_str}:{port})"
            BLOCKED_ATTEMPTS.append(record)
            raise RuntimeError(f"PROVIDER_FREE_GUARD_BLOCKED: Outbound socket connect intercepted: {record}")
    return _orig_socket_connect(self, address)


def guarded_urlopen(url: Any, *args: Any, **kwargs: Any) -> Any:
    url_str = str(url or "")
    record = f"urlopen({url_str[:80]})"
    BLOCKED_ATTEMPTS.append(record)
    raise RuntimeError(f"PROVIDER_FREE_GUARD_BLOCKED: urllib urlopen intercepted: {record}")


def get_blocked_attempts_count() -> int:
    return len(BLOCKED_ATTEMPTS)


def get_blocked_attempts() -> list[str]:
    return list(BLOCKED_ATTEMPTS)


def reset_blocked_attempts() -> None:
    BLOCKED_ATTEMPTS.clear()


def install_guard() -> None:
    # 1. Enforce zero real provider credentials without rewriting
    verify_no_real_credentials()

    # 2. Enforce sandbox storage path isolation
    verify_safe_storage_paths()

    # 3. Network hooks
    socket.getaddrinfo = guarded_getaddrinfo
    socket.create_connection = guarded_create_connection
    socket.socket.connect = guarded_socket_connect
    urllib.request.urlopen = guarded_urlopen


def pytest_configure(config: Any) -> None:
    install_guard()


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_bot_db_connect():
    """Ensure bot.db_connect is isolated and restored across tests."""
    orig = None
    try:
        import bot
        orig = bot.db_connect
    except Exception:
        pass
    yield
    if orig is not None:
        try:
            import bot
            bot.db_connect = orig
        except Exception:
            pass

