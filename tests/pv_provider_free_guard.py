"""Pytest plugin enforcing zero outbound network / provider calls in provider-free testing.

Governed by: owner-governed-codex, locked-focus-engineering
SPEC_ID: PRODUCT-VIDEO-S00-PROVIDER-FREE-GUARD
"""

from __future__ import annotations

import os
import socket
import urllib.request
from typing import Any

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testserver"})
BLOCKED_ATTEMPTS: list[str] = []

_orig_getaddrinfo = socket.getaddrinfo
_orig_create_connection = socket.create_connection
_orig_socket_connect = socket.socket.connect
_orig_urlopen = urllib.request.urlopen


def is_loopback(host: str) -> bool:
    clean = str(host or "").strip().lower()
    return clean in LOOPBACK_HOSTS or clean.startswith("127.") or clean == "::1"


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
    socket.getaddrinfo = guarded_getaddrinfo
    socket.create_connection = guarded_create_connection
    socket.socket.connect = guarded_socket_connect
    urllib.request.urlopen = guarded_urlopen

    # Sanitize environment: neutralize real provider secrets to prevent accidental use
    for env_key in [
        "SHOPAIKEY_API_KEY",
        "KEY4U_API_KEY",
        "FAL_KEY",
        "MINIMAX_API_KEY",
        "OPENAI_API_KEY",
    ]:
        if os.environ.get(env_key) and not os.environ.get(env_key, "").startswith("test_"):
            os.environ[env_key] = f"test_mock_{env_key.lower()}"


def pytest_configure(config: Any) -> None:
    install_guard()
