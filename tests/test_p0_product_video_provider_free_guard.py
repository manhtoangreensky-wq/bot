"""Canary test proving that tests.pv_provider_free_guard intercepts outbound network calls.

SPEC_ID: PRODUCT-VIDEO-S00-PROVIDER-FREE-GUARD
"""

import socket
import pytest

from tests.pv_provider_free_guard import (
    get_blocked_attempts_count,
    get_blocked_attempts,
    reset_blocked_attempts,
)


def test_guard_canary_blocks_external_dns():
    reset_blocked_attempts()
    initial_count = get_blocked_attempts_count()

    with pytest.raises(RuntimeError) as exc_info:
        socket.getaddrinfo("example.invalid", 443)

    assert "PROVIDER_FREE_GUARD_BLOCKED" in str(exc_info.value)
    assert get_blocked_attempts_count() == initial_count + 1
    assert any("example.invalid" in attempt for attempt in get_blocked_attempts())


def test_guard_canary_blocks_external_ip_connection():
    reset_blocked_attempts()
    initial_count = get_blocked_attempts_count()

    with pytest.raises(RuntimeError) as exc_info:
        socket.create_connection(("192.0.2.1", 443), timeout=1.0)

    assert "PROVIDER_FREE_GUARD_BLOCKED" in str(exc_info.value)
    assert get_blocked_attempts_count() == initial_count + 1
    assert any("192.0.2.1" in attempt for attempt in get_blocked_attempts())


def test_guard_allows_loopback_dns():
    # Loopback getaddrinfo should not raise PROVIDER_FREE_GUARD_BLOCKED
    addr = socket.getaddrinfo("127.0.0.1", 80)
    assert len(addr) > 0
