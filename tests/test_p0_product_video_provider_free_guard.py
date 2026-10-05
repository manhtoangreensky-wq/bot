"""Canary test suite proving tests.pv_provider_free_guard enforces network, credential, and path isolation.

SPEC_ID: PRODUCT-VIDEO-S00-PROVIDER-FREE-GUARD
Governed by: owner-governed-codex, locked-focus-engineering
"""

import socket
import pytest

from tests.pv_provider_free_guard import (
    get_blocked_attempts_count,
    get_blocked_attempts,
    reset_blocked_attempts,
    verify_no_real_credentials,
    verify_safe_storage_paths,
    is_production_path,
    is_test_token,
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


def test_guard_allows_reviewed_loopback():
    # Loopback getaddrinfo should not raise PROVIDER_FREE_GUARD_BLOCKED
    addr = socket.getaddrinfo("127.0.0.1", 80)
    assert len(addr) > 0


def test_guard_canary_blocks_real_looking_provider_credentials():
    # 1. Real-looking ShopAIKey secret must fail closed without rewriting
    with pytest.raises(RuntimeError) as exc_info:
        verify_no_real_credentials({"SHOPAIKEY_API_KEY": "sk-live-shopaikey-secret-1234567890"})
    assert "PROVIDER_FREE_GUARD_BLOCKED" in str(exc_info.value)
    assert "REAL_PROVIDER_CREDENTIAL_REWRITE_ALLOWED=NO" in str(exc_info.value)

    # 2. Real-looking Key4U secret must fail closed
    with pytest.raises(RuntimeError) as exc_info:
        verify_no_real_credentials({"KEY4U_API_KEY": "k4u_live_prod_token_abc"})
    assert "PROVIDER_FREE_GUARD_BLOCKED" in str(exc_info.value)


def test_guard_canary_accepts_test_mock_credentials():
    # Test tokens must be accepted without error
    verify_no_real_credentials({"SHOPAIKEY_API_KEY": "test_mock_shopaikey_key"})
    verify_no_real_credentials({"KEY4U_API_KEY": "mock_key4u_key"})
    verify_no_real_credentials({"FAL_KEY": "fake_fal_key"})
    verify_no_real_credentials({"MINIMAX_API_KEY": "dummy_minimax_key"})
    verify_no_real_credentials({"OPENAI_API_KEY": ""})


def test_guard_canary_blocks_production_database_and_paths():
    # 1. Production SQLite DB path
    with pytest.raises(RuntimeError) as exc_info:
        verify_safe_storage_paths({"DB_PATH": "/data/toandaas_system.db"})
    assert "PROVIDER_FREE_GUARD_BLOCKED" in str(exc_info.value)

    # 2. Production VPS directory
    with pytest.raises(RuntimeError) as exc_info:
        verify_safe_storage_paths({"DATA_DIR": "/opt/toanaas/data"})
    assert "PROVIDER_FREE_GUARD_BLOCKED" in str(exc_info.value)

    # 3. Direct production path detector
    assert is_production_path("/data/toandaas_system.db") is True
    assert is_production_path("/opt/toanaas-worker/db.sqlite") is True


def test_guard_canary_accepts_temp_sandbox_paths():
    # Temp sandbox paths must be accepted
    verify_safe_storage_paths({"DB_PATH": ":memory:"})
    verify_safe_storage_paths({"DB_PATH": "D:/TOANAAS/wt_video_ref_i2v_r16_09ab1/.pytest_tmp/test.db"})
    verify_safe_storage_paths({"DATA_DIR": "C:/Users/toann/AppData/Local/Temp/pytest-123"})
    assert is_production_path(":memory:") is False
    assert is_production_path("D:/TOANAAS/wt_video_ref_i2v_r16_09ab1/.pytest_tmp/db.sqlite") is False
