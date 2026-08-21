"""TDD contract tests for the isolated public Chat Free/Chat Pro store.

These tests intentionally use only temporary/in-memory SQLite connections.  A
provider adapter or Telegram transport is never imported or called here.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
import sqlite3
from threading import Barrier
from zoneinfo import ZoneInfo

import pytest


def _connection() -> sqlite3.Connection:
    from services.public_chat_store import ensure_schema

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    ensure_schema(connection)
    connection.commit()
    return connection


def test_sanitize_redacts_short_named_credential_values() -> None:
    from services.public_chat_store import sanitize_public_chat_content

    sanitized, redaction_applied = sanitize_public_chat_content("please hide token:abcde")

    assert sanitized == "please hide [đã ẩn thông tin nhạy cảm]"
    assert redaction_applied is True


def test_sanitize_redacts_private_unix_application_paths() -> None:
    from services.public_chat_store import sanitize_public_chat_content

    sanitized, redaction_applied = sanitize_public_chat_content(
        "do not persist /workspace/secrets.txt"
    )

    assert sanitized == "do not persist [đã ẩn thông tin nhạy cảm]"
    assert redaction_applied is True


@pytest.mark.parametrize(
    "content, secret_fragment",
    [
        (r"open \\server\private share\customer.txt", "customer.txt"),
        ("open /Users/owner/Private/customer.txt", "customer.txt"),
        (r"open C:\Users\Owner Name\Private\customer.txt", "customer.txt"),
    ],
)
def test_sanitize_redacts_private_paths_with_unc_macos_or_spaces(
    content: str, secret_fragment: str
) -> None:
    from services.public_chat_store import sanitize_public_chat_content

    sanitized, redaction_applied = sanitize_public_chat_content(content)

    assert secret_fragment not in sanitized
    assert redaction_applied is True


@pytest.mark.parametrize(
    "content",
    ["/start", "open https://example.com/docs/start"],
)
def test_sanitize_keeps_commands_and_https_urls(content: str) -> None:
    from services.public_chat_store import sanitize_public_chat_content

    sanitized, redaction_applied = sanitize_public_chat_content(content)

    assert sanitized == content
    assert redaction_applied is False


@pytest.mark.parametrize(
    "content, credential",
    [
        ("Authorization: Basic dXNlcjpwYXNzd29yZA==", "dXNlcjpwYXNzd29yZA=="),
        ("Authorization: Bearer bearer-secret-value", "bearer-secret-value"),
        (
            "Authorization: Digest username=alice, response=digest-secret-value",
            "digest-secret-value",
        ),
    ],
)
def test_sanitize_redacts_entire_authorization_credentials(
    content: str,
    credential: str,
) -> None:
    from services.public_chat_store import sanitize_public_chat_content

    sanitized, redaction_applied = sanitize_public_chat_content(content)

    assert credential not in sanitized
    assert sanitized == "[đã ẩn thông tin nhạy cảm]"
    assert redaction_applied is True


@pytest.mark.parametrize(
    "query_key",
    [
        "X-Amz-Signature",
        "X-Amz-Credential",
        "X-Amz-Security-Token",
        "signature",
        "sig",
        "token",
        "access_token",
        "api_key",
        "key",
    ],
)
def test_sanitize_redacts_urls_with_sensitive_query_keys(query_key: str) -> None:
    from services.public_chat_store import sanitize_public_chat_content

    content = f"download https://example.com/file?format=json&{query_key}=supersecret"
    sanitized, redaction_applied = sanitize_public_chat_content(content)

    assert "supersecret" not in sanitized
    assert "https://example.com/file" not in sanitized
    assert sanitized == "download [đã ẩn thông tin nhạy cảm]"
    assert redaction_applied is True


def test_opus_customer_price_uses_rounded_public_tariff_and_rounds_up() -> None:
    from services.chat_pro_pricing import calculate_opus_charge_xu

    assert calculate_opus_charge_xu(500, 300) == 10
    assert calculate_opus_charge_xu(1_000, 500) == 18
    assert calculate_opus_charge_xu(2_000, 1_000) == 35
    assert calculate_opus_charge_xu(0, 0, 1_000) == 1


def test_opus_display_rates_use_rounded_public_tariff_and_request_rounding_happens_once() -> None:
    from decimal import Decimal

    from services.chat_pro_pricing import (
        opus_price_per_thousand_labels,
        opus_price_per_thousand_xu,
    )

    assert opus_price_per_thousand_xu() == {
        "input": Decimal("5"),
        "output": Decimal("25"),
        "cache_read": Decimal("0.45"),
    }
    assert opus_price_per_thousand_labels() == {
        "input": "5",
        "output": "25",
        "cache_read": "0.45",
    }

    # 500 input + 500 output = 2.5 + 12.5 = 15 Xu, then one request-level ceil.
    from services.chat_pro_pricing import TokenUsage, calculate_actual_xu, calculate_opus_charge_xu
    from services.public_chat_runtime import _default_pricing

    assert calculate_opus_charge_xu(500, 500) == 15
    assert calculate_actual_xu(TokenUsage(1_000, 1_000), _default_pricing()) == 30


def test_opus_reservation_is_utf8_conservative_bounded_and_rate_reviewed() -> None:
    from services.chat_pro_pricing import (
        KEY4U_RATE_EFFECTIVE_DATE,
        KEY4U_RATE_REVIEW_BY,
        MAX_PRO_OUTPUT_TOKENS,
        pricing_rate_review_status,
        reserve_xu,
    )

    english = reserve_xu([{"role": "user", "content": "hello"}], 1_000)
    vietnamese = reserve_xu([{"role": "user", "content": "xin chào Việt Nam"}], 1_000)
    bounded = reserve_xu(
        [{"role": "user", "content": "hello"}],
        MAX_PRO_OUTPUT_TOKENS * 10,
    )
    at_cap = reserve_xu(
        [{"role": "user", "content": "hello"}],
        MAX_PRO_OUTPUT_TOKENS,
    )

    assert vietnamese >= english > 0
    assert english == 26
    assert bounded == at_cap
    assert KEY4U_RATE_EFFECTIVE_DATE <= date(2026, 8, 9) <= KEY4U_RATE_REVIEW_BY
    assert pricing_rate_review_status(date(2026, 8, 9))["review_required"] is False
    assert pricing_rate_review_status(KEY4U_RATE_REVIEW_BY.replace(year=2027))["review_required"] is True


def test_free_quota_allows_twenty_successes_and_rejects_the_21st() -> None:
    from services.public_chat_store import (
        complete_free_request,
        reserve_free_request,
    )

    conn = _connection()
    for index in range(20):
        reservation = reserve_free_request(
            conn,
            owner_id="u1",
            chat_id="c1",
            source_message_id=str(index),
            now=1_754_000_000,
        )
        assert reservation["accepted"] is True
        completed = complete_free_request(
            conn,
            reservation["request_id"],
            user_content=f"question {index}",
            assistant_content=f"answer {index}",
            now=1_754_000_001 + index,
        )
        assert completed["consumed"] is True
        conn.commit()

    exhausted = reserve_free_request(
        conn,
        owner_id="u1",
        chat_id="c1",
        source_message_id="21",
        now=1_754_000_100,
    )
    assert exhausted["accepted"] is False
    assert exhausted["exhausted"] is True
    assert exhausted["remaining"] == 0


def test_free_quota_twentieth_and_twenty_first_reservations_are_atomic(tmp_path) -> None:
    from services.public_chat_store import (
        complete_free_request,
        ensure_schema,
        reserve_free_request,
    )

    db_path = tmp_path / "public-chat-quota-race.sqlite"
    setup = sqlite3.connect(db_path, timeout=10)
    setup.row_factory = sqlite3.Row
    ensure_schema(setup)
    now = datetime(2026, 8, 9, 12, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")).timestamp()
    for index in range(19):
        request = reserve_free_request(
            setup,
            owner_id="race-owner",
            chat_id="chat",
            source_message_id=f"warmup-{index}",
            now=now,
        )
        assert request["accepted"] is True
        assert complete_free_request(
            setup,
            request["request_id"],
            user_content="q",
            assistant_content="a",
            now=now,
        )["consumed"] is True
        setup.commit()
    setup.close()

    barrier = Barrier(2)

    def reserve_at_boundary(source_message_id: str) -> dict:
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            barrier.wait(timeout=5)
            result = reserve_free_request(
                conn,
                owner_id="race-owner",
                chat_id="chat",
                source_message_id=source_message_id,
                now=now,
            )
            conn.commit()
            return result
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(reserve_at_boundary, ("turn-20", "turn-21")))

    assert sum(bool(result["accepted"]) for result in results) == 1
    assert sum(bool(result["exhausted"]) for result in results) == 1
    verify = sqlite3.connect(db_path)
    try:
        used = verify.execute(
            """SELECT COUNT(*) FROM public_chat_requests
               WHERE owner_id='race-owner' AND mode='free'
                 AND status IN ('reserved', 'consumed')"""
        ).fetchone()[0]
    finally:
        verify.close()
    assert used == 20


def test_free_failure_is_released_and_duplicate_update_is_idempotent() -> None:
    from services.public_chat_store import (
        complete_free_request,
        release_request,
        reserve_free_request,
    )

    conn = _connection()
    first = reserve_free_request(
        conn,
        owner_id="u1",
        chat_id="c1",
        source_message_id="same-message",
        now=1_754_000_000,
    )
    duplicate = reserve_free_request(
        conn,
        owner_id="u1",
        chat_id="c1",
        source_message_id="same-message",
        now=1_754_000_001,
    )
    assert first["accepted"] is True
    assert duplicate["duplicate"] is True
    assert duplicate["request_id"] == first["request_id"]

    released = release_request(conn, first["request_id"], reason="timeout")
    released_again = release_request(conn, first["request_id"], reason="retry")
    assert released["released"] is True
    assert released_again["released"] is False

    retry = reserve_free_request(
        conn,
        owner_id="u1",
        chat_id="c1",
        source_message_id="new-message",
        now=1_754_000_002,
    )
    assert retry["accepted"] is True
    complete_free_request(
        conn,
        retry["request_id"],
        user_content="new",
        assistant_content="reply",
        now=1_754_000_003,
    )
    duplicate_completion = complete_free_request(
        conn,
        retry["request_id"],
        user_content="new",
        assistant_content="reply again",
        now=1_754_000_004,
    )
    assert duplicate_completion["consumed"] is False
    assert duplicate_completion["duplicate"] is True
    assert conn.execute("SELECT COUNT(*) FROM public_chat_turns").fetchone()[0] == 2


def test_free_quota_resets_on_vietnam_day_releases_stale_and_is_owner_scoped() -> None:
    from services.public_chat_store import (
        complete_free_request,
        reserve_free_request,
    )

    conn = _connection()
    vietnam = ZoneInfo("Asia/Ho_Chi_Minh")
    before_midnight = datetime(2026, 8, 9, 23, 59, tzinfo=vietnam).timestamp()
    for index in range(20):
        request = reserve_free_request(
            conn,
            owner_id="limited",
            chat_id="chat",
            source_message_id=f"day-one-{index}",
            now=before_midnight,
        )
        complete_free_request(
            conn,
            request["request_id"],
            user_content="q",
            assistant_content="a",
            now=before_midnight,
        )
    assert reserve_free_request(
        conn,
        owner_id="limited",
        chat_id="chat",
        source_message_id="blocked",
        now=before_midnight,
    )["exhausted"] is True
    assert reserve_free_request(
        conn,
        owner_id="other-owner",
        chat_id="chat",
        source_message_id="independent",
        now=before_midnight,
    )["accepted"] is True

    next_day = datetime(2026, 8, 10, 0, 0, tzinfo=vietnam).timestamp()
    assert reserve_free_request(
        conn,
        owner_id="limited",
        chat_id="chat",
        source_message_id="next-day",
        now=next_day,
    )["accepted"] is True

    stale_owner = "stale-owner"
    for index in range(20):
        assert reserve_free_request(
            conn,
            owner_id=stale_owner,
            chat_id="chat",
            source_message_id=f"stale-{index}",
            now=next_day,
        )["accepted"] is True
    released_slot = reserve_free_request(
        conn,
        owner_id=stale_owner,
        chat_id="chat",
        source_message_id="after-stale",
        now=next_day + 901,
    )
    assert released_slot["accepted"] is True
    assert conn.in_transaction is True


def test_free_and_pro_share_only_public_48h_context_and_expire_at_boundary() -> None:
    from services.public_chat_store import (
        complete_free_request,
        load_public_context,
        reserve_free_request,
        reserve_pro_request,
        settle_pro_request,
    )

    conn = _connection()
    free = reserve_free_request(
        conn,
        owner_id="u1",
        chat_id="c1",
        source_message_id="free-1",
        now=1_000,
    )
    complete_free_request(
        conn,
        free["request_id"],
        user_content="free question",
        assistant_content="free answer",
        now=1_001,
    )
    conn.commit()

    conn.execute(
        "CREATE TABLE users (user_id TEXT PRIMARY KEY, credits INTEGER NOT NULL, total_spent INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute("INSERT INTO users(user_id, credits) VALUES (?, ?)", ("u1", 100))
    pro = reserve_pro_request(
        conn,
        owner_id="u1",
        chat_id="c1",
        source_message_id="pro-1",
        reserved_xu=20,
        now=1_002,
    )
    settle_pro_request(
        conn,
        pro["request_id"],
        input_tokens=100,
        output_tokens=100,
        user_content="pro question",
        assistant_content="pro answer",
        provider_request_id="key4u-context-1",
        now=1_003,
    )
    conn.commit()

    context = load_public_context(conn, "u1", "c1", now=1_004)
    assert [turn["content"] for turn in context["turns"]] == [
        "free question",
        "free answer",
        "pro question",
        "pro answer",
    ]
    assert {turn["mode"] for turn in context["turns"]} == {"free", "pro"}
    assert context["session_id"]

    expired = load_public_context(conn, "u1", "c1", now=1_003 + 48 * 60 * 60 + 1)
    assert expired["turns"] == []
    assert expired["session_id"] != context["session_id"]
    assert conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='conversation_turns'"
    ).fetchone()[0] == 0


def test_public_store_is_structurally_isolated_from_cskh_and_aichat_tables() -> None:
    conn = _connection()
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "public_chat_turns" in tables
    assert "public_chat_requests" in tables
    assert "conversation_turns" not in tables
    assert "ai_chatbot_state" not in tables


def test_successful_turns_are_sanitized_before_public_persistence() -> None:
    from services.public_chat_store import (
        complete_free_request,
        load_public_context,
        reserve_free_request,
    )

    conn = _connection()
    request = reserve_free_request(
        conn,
        owner_id="u1",
        chat_id="c1",
        source_message_id="secret-message",
        now=10_000,
    )
    complete_free_request(
        conn,
        request["request_id"],
        user_content=r"api_key=sk-secret-123456789 path C:\Users\owner\secret.txt",
        assistant_content="Đã nhận nhưng sẽ không lặp bí mật.",
        now=10_001,
    )
    context = load_public_context(conn, "u1", "c1", now=10_002)
    persisted = " ".join(turn["content"] for turn in context["turns"])

    assert "sk-secret" not in persisted
    assert "C:\\Users" not in persisted
    assert "[đã ẩn thông tin nhạy cảm]" in persisted


def test_pro_reservation_settlement_refund_and_retry_are_exactly_once() -> None:
    from services.public_chat_store import (
        reserve_pro_request,
        settle_pro_request,
    )

    conn = _connection()
    conn.execute(
        "CREATE TABLE users (user_id TEXT PRIMARY KEY, credits INTEGER NOT NULL, total_spent INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute("INSERT INTO users(user_id, credits) VALUES (?, ?)", ("u1", 100))

    reserved = reserve_pro_request(
        conn,
        owner_id="u1",
        chat_id="c1",
        source_message_id="pro-1",
        reserved_xu=50,
        now=2_000,
    )
    assert reserved["accepted"] is True
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 50

    settled = settle_pro_request(
        conn,
        reserved["request_id"],
        input_tokens=1_000,
        output_tokens=500,
        provider_request_id="key4u-request-1",
        now=2_001,
    )
    assert settled["settled"] is True
    assert settled["charged_xu"] == 18
    assert settled["refunded_xu"] == 32
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 82
    assert conn.execute("SELECT total_spent FROM users WHERE user_id='u1'").fetchone()[0] == 18
    stored_provider_id = conn.execute(
        "SELECT provider_request_id FROM public_chat_requests WHERE request_id=?",
        (reserved["request_id"],),
    ).fetchone()[0]
    assert stored_provider_id == "key4u-request-1"

    duplicate = settle_pro_request(
        conn,
        reserved["request_id"],
        input_tokens=99_999,
        output_tokens=99_999,
        provider_request_id="must-not-replace",
        now=2_002,
    )
    assert duplicate["duplicate"] is True
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 82
    assert conn.execute("SELECT total_spent FROM users WHERE user_id='u1'").fetchone()[0] == 18
    assert conn.in_transaction is True


def test_pro_failure_refunds_once_and_never_makes_balance_negative() -> None:
    from services.public_chat_store import (
        refund_pro_request,
        reserve_pro_request,
    )

    conn = _connection()
    conn.execute(
        "CREATE TABLE users (user_id TEXT PRIMARY KEY, credits INTEGER NOT NULL, total_spent INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute("INSERT INTO users(user_id, credits) VALUES (?, ?)", ("u1", 10))

    request = reserve_pro_request(
        conn,
        owner_id="u1",
        chat_id="c1",
        source_message_id="failed",
        reserved_xu=10,
        now=3_000,
    )
    assert request["accepted"] is True
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 0

    first = refund_pro_request(conn, request["request_id"], reason="provider_error")
    second = refund_pro_request(conn, request["request_id"], reason="retry")
    assert first["refunded"] is True
    assert first["refunded_xu"] == 10
    assert second["refunded"] is False
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 10
    assert conn.execute("SELECT total_spent FROM users WHERE user_id='u1'").fetchone()[0] == 0

    low = reserve_pro_request(
        conn,
        owner_id="u1",
        chat_id="c1",
        source_message_id="too-expensive",
        reserved_xu=11,
        now=3_001,
    )
    assert low["accepted"] is False
    assert low["insufficient_balance"] is True
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 10


def test_stale_pro_reconciler_refunds_owner_requests_once_and_keeps_boundary_fresh() -> None:
    from services.public_chat_store import (
        reconcile_stale_pro_reservations,
        reserve_pro_request,
    )

    conn = _connection()
    conn.execute(
        "CREATE TABLE users (user_id TEXT PRIMARY KEY, credits INTEGER NOT NULL, total_spent INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute("INSERT INTO users(user_id, credits) VALUES ('u1', 47), ('u2', 100)")
    stale_paid = reserve_pro_request(
        conn,
        owner_id="u1",
        chat_id="c1",
        source_message_id="stale-paid",
        reserved_xu=30,
        now=100,
    )
    stale_admin = reserve_pro_request(
        conn,
        owner_id="u1",
        chat_id="c1",
        source_message_id="stale-admin",
        reserved_xu=999,
        is_admin=True,
        now=101,
    )
    boundary = reserve_pro_request(
        conn,
        owner_id="u1",
        chat_id="c1",
        source_message_id="boundary",
        reserved_xu=5,
        now=1_000,
    )
    fresh = reserve_pro_request(
        conn,
        owner_id="u1",
        chat_id="c1",
        source_message_id="fresh",
        reserved_xu=10,
        now=1_001,
    )
    preflight = reserve_pro_request(
        conn,
        owner_id="u1",
        chat_id="c1",
        source_message_id="preflight",
        reserved_xu=1,
        now=100,
    )
    settled = reserve_pro_request(
        conn,
        owner_id="u1",
        chat_id="c1",
        source_message_id="settled",
        reserved_xu=1,
        now=100,
    )
    conn.execute(
        "UPDATE public_chat_requests SET status='preflight' WHERE request_id=?",
        (preflight["request_id"],),
    )
    conn.execute(
        "UPDATE public_chat_requests SET status='settled' WHERE request_id=?",
        (settled["request_id"],),
    )
    other_owner = reserve_pro_request(
        conn,
        owner_id="u2",
        chat_id="c2",
        source_message_id="other-owner",
        reserved_xu=20,
        now=100,
    )
    conn.commit()
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 0

    refunds = reconcile_stale_pro_reservations(conn, owner_id="u1", now=1_900)
    refunds_by_id = {item["request_id"]: item["refunded_xu"] for item in refunds}

    assert refunds_by_id == {
        stale_paid["request_id"]: 30,
        stale_admin["request_id"]: 0,
    }
    assert sum(item["refunded_xu"] for item in refunds) == 30
    rows = {
        row[0]: tuple(row[1:])
        for row in conn.execute(
            "SELECT request_id,status,refunded_xu,reason FROM public_chat_requests"
        ).fetchall()
    }
    assert rows[stale_paid["request_id"]] == ("refunded", 30, "stale_reservation")
    assert rows[stale_admin["request_id"]] == ("refunded", 0, "stale_reservation")
    assert rows[boundary["request_id"]][0] == "reserved"
    assert rows[fresh["request_id"]][0] == "reserved"
    assert rows[preflight["request_id"]][0] == "preflight"
    assert rows[settled["request_id"]][0] == "settled"
    assert rows[other_owner["request_id"]][0] == "reserved"
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 30
    assert conn.execute("SELECT credits FROM users WHERE user_id='u2'").fetchone()[0] == 80
    assert conn.execute("SELECT MIN(credits) FROM users").fetchone()[0] >= 0

    conn.commit()
    assert reconcile_stale_pro_reservations(conn, owner_id="u1", now=1_900) == []
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 30


def test_stale_pro_reconciler_is_exactly_once_across_concurrent_connections(tmp_path) -> None:
    from services.public_chat_store import (
        ensure_schema,
        reconcile_stale_pro_reservations,
        reserve_pro_request,
    )

    db_path = tmp_path / "public-chat-stale-pro-race.sqlite"
    setup = sqlite3.connect(db_path, timeout=10)
    setup.row_factory = sqlite3.Row
    ensure_schema(setup)
    setup.execute(
        "CREATE TABLE users (user_id TEXT PRIMARY KEY, credits INTEGER NOT NULL, total_spent INTEGER NOT NULL DEFAULT 0)"
    )
    setup.execute("INSERT INTO users(user_id, credits) VALUES ('u1', 10)")
    stale = reserve_pro_request(
        setup,
        owner_id="u1",
        chat_id="c1",
        source_message_id="stale-race",
        reserved_xu=10,
        now=100,
    )
    setup.commit()
    setup.close()

    barrier = Barrier(2)

    def reconcile() -> list[dict]:
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            barrier.wait(timeout=5)
            refunds = reconcile_stale_pro_reservations(conn, owner_id="u1", now=1_001)
            conn.commit()
            return refunds
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: reconcile(), range(2)))

    refunds = [item for result in results for item in result]
    assert refunds == [{"request_id": stale["request_id"], "refunded_xu": 10}]
    assert sum(item["refunded_xu"] for item in refunds) == 10

    verify = sqlite3.connect(db_path)
    try:
        assert verify.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 10
        assert tuple(
            verify.execute(
                "SELECT status,refunded_xu,reason FROM public_chat_requests WHERE request_id=?",
                (stale["request_id"],),
            ).fetchone()
        ) == ("refunded", 10, "stale_reservation")
    finally:
        verify.close()


def test_same_telegram_message_is_duplicate_across_free_and_pro_modes() -> None:
    from services.public_chat_store import (
        complete_free_request,
        reserve_free_request,
        reserve_pro_request,
    )

    conn = _connection()
    conn.execute(
        "CREATE TABLE users (user_id TEXT PRIMARY KEY, credits INTEGER NOT NULL, total_spent INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute("INSERT INTO users(user_id, credits) VALUES ('u1', 100)")
    free = reserve_free_request(
        conn,
        owner_id="u1",
        chat_id="c1",
        source_message_id="same-update",
        now=3_100,
    )
    complete_free_request(
        conn,
        free["request_id"],
        user_content="free",
        assistant_content="answer",
        now=3_101,
    )
    balance_before = conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0]

    pro = reserve_pro_request(
        conn,
        owner_id="u1",
        chat_id="c1",
        source_message_id="same-update",
        reserved_xu=50,
        now=3_102,
    )
    assert pro["accepted"] is False
    assert pro["duplicate"] is True
    assert pro["request_id"] == free["request_id"]
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == balance_before


def test_admin_free_quota_and_pro_wallet_bypass() -> None:
    from services.public_chat_store import (
        complete_free_request,
        reserve_free_request,
        reserve_pro_request,
    )

    conn = _connection()
    conn.execute(
        "CREATE TABLE users (user_id TEXT PRIMARY KEY, credits INTEGER NOT NULL, total_spent INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute("INSERT INTO users(user_id, credits) VALUES (?, ?)", ("admin", 0))

    for index in range(21):
        request = reserve_free_request(
            conn,
            owner_id="admin",
            chat_id="c1",
            source_message_id=f"admin-{index}",
            is_admin=True,
            now=4_000,
        )
        assert request["accepted"] is True
        complete_free_request(
            conn,
            request["request_id"],
            user_content="q",
            assistant_content="a",
            now=4_001 + index,
        )
        conn.commit()

    pro = reserve_pro_request(
        conn,
        owner_id="admin",
        chat_id="c1",
        source_message_id="admin-pro",
        reserved_xu=10_000,
        is_admin=True,
        now=4_100,
    )
    assert pro["accepted"] is True
    assert pro["reserved_xu"] == 0
    assert conn.execute("SELECT credits FROM users WHERE user_id='admin'").fetchone()[0] == 0


@pytest.mark.parametrize("value", [1.9, "1.9"])
def test_pricing_rejects_fractional_integer_inputs(value: object) -> None:
    from services.chat_pro_pricing import calculate_opus_charge_xu

    with pytest.raises(ValueError, match="non-negative integer"):
        calculate_opus_charge_xu(value, 0)


def test_pricing_accepts_integer_like_inputs() -> None:
    from services.chat_pro_pricing import calculate_opus_charge_xu

    assert calculate_opus_charge_xu(1, "1") == calculate_opus_charge_xu("1", 1)


def test_pro_settlement_fails_closed_without_total_spent_and_caller_rollback_restores() -> None:
    from services.public_chat_store import reserve_pro_request, settle_pro_request

    conn = _connection()
    conn.execute("CREATE TABLE users (user_id TEXT PRIMARY KEY, credits INTEGER NOT NULL)")
    conn.execute("INSERT INTO users(user_id, credits) VALUES ('u1', 100)")
    conn.commit()
    reserved = reserve_pro_request(
        conn,
        owner_id="u1",
        chat_id="c1",
        source_message_id="missing-total-spent",
        reserved_xu=50,
        now=5_000,
    )
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 50

    with pytest.raises(RuntimeError, match="total_spent"):
        settle_pro_request(
            conn,
            reserved["request_id"],
            input_tokens=1_000,
            output_tokens=500,
            provider_request_id="key4u-missing-total-spent",
            now=5_001,
        )
    assert conn.in_transaction is True
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 50
    assert conn.execute(
        "SELECT status FROM public_chat_requests WHERE request_id=?", (reserved["request_id"],)
    ).fetchone()[0] == "reserved"

    conn.rollback()
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 100
    assert conn.execute(
        "SELECT COUNT(*) FROM public_chat_requests WHERE request_id=?", (reserved["request_id"],)
    ).fetchone()[0] == 0


def test_pro_settlement_over_reserved_with_sufficient_balance_charges_actual_once() -> None:
    from services.public_chat_store import reserve_pro_request, settle_pro_request

    conn = _connection()
    conn.execute(
        "CREATE TABLE users (user_id TEXT PRIMARY KEY, credits INTEGER NOT NULL, total_spent INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute("INSERT INTO users(user_id, credits) VALUES ('u1', 100)")
    reserved = reserve_pro_request(
        conn,
        owner_id="u1",
        chat_id="c1",
        source_message_id="over-reserved-enough",
        reserved_xu=5,
        now=5_100,
    )
    settled = settle_pro_request(
        conn,
        reserved["request_id"],
        input_tokens=1_000,
        output_tokens=500,
        provider_request_id="key4u-over-reserved-enough",
        now=5_101,
    )
    assert settled["status"] == "settled"
    assert settled["charged_xu"] == 18
    assert settled["uncollected_xu"] == 0
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 82
    assert conn.execute("SELECT total_spent FROM users WHERE user_id='u1'").fetchone()[0] == 18

    duplicate = settle_pro_request(
        conn,
        reserved["request_id"],
        input_tokens=1_000,
        output_tokens=500,
        provider_request_id="key4u-over-reserved-enough",
        now=5_102,
    )
    assert duplicate["duplicate"] is True
    assert duplicate["charged_xu"] == 18
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 82
    assert conn.execute("SELECT total_spent FROM users WHERE user_id='u1'").fetchone()[0] == 18


def test_pro_settlement_over_reserved_with_insufficient_balance_refunds_all_once() -> None:
    from services.public_chat_store import reserve_pro_request, settle_pro_request

    conn = _connection()
    conn.execute(
        "CREATE TABLE users (user_id TEXT PRIMARY KEY, credits INTEGER NOT NULL, total_spent INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute("INSERT INTO users(user_id, credits) VALUES ('u1', 10)")
    reserved = reserve_pro_request(
        conn,
        owner_id="u1",
        chat_id="c1",
        source_message_id="over-reserved-short",
        reserved_xu=5,
        now=5_200,
    )
    settled = settle_pro_request(
        conn,
        reserved["request_id"],
        input_tokens=1_000,
        output_tokens=500,
        user_content="do not persist this prompt",
        assistant_content="do not deliver this answer",
        provider_request_id="key4u-over-reserved-short",
        now=5_201,
    )
    assert settled["status"] == "under_reserved_refunded"
    assert settled["charged_xu"] == 0
    assert settled["refunded_xu"] == 5
    assert settled["uncollected_xu"] == 18
    assert settled["balance_xu"] == 10
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 10
    assert conn.execute("SELECT total_spent FROM users WHERE user_id='u1'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM public_chat_turns").fetchone()[0] == 0
    assert tuple(
        conn.execute(
            "SELECT status,settled_xu,refunded_xu,uncollected_xu,reason FROM public_chat_requests"
        ).fetchone()
    ) == ("under_reserved_refunded", 0, 5, 18, "insufficient_balance_after_usage")

    duplicate = settle_pro_request(
        conn,
        reserved["request_id"],
        input_tokens=1_000,
        output_tokens=500,
        user_content="do not persist this prompt",
        assistant_content="do not deliver this answer",
        provider_request_id="key4u-over-reserved-short",
        now=5_202,
    )
    assert duplicate["duplicate"] is True
    assert duplicate["status"] == "under_reserved_refunded"
    assert duplicate["charged_xu"] == 0
    assert duplicate["refunded_xu"] == 5
    assert duplicate["uncollected_xu"] == 18
    assert tuple(conn.execute("SELECT credits,total_spent FROM users WHERE user_id='u1'").fetchone()) == (10, 0)
    assert conn.execute("SELECT COUNT(*) FROM public_chat_turns").fetchone()[0] == 0


def test_settlement_changes_are_rolled_back_by_caller_transaction() -> None:
    from services.public_chat_store import reserve_pro_request, settle_pro_request

    conn = _connection()
    conn.execute(
        "CREATE TABLE users (user_id TEXT PRIMARY KEY, credits INTEGER NOT NULL, total_spent INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute("INSERT INTO users(user_id, credits) VALUES ('u1', 100)")
    reserved = reserve_pro_request(
        conn,
        owner_id="u1",
        chat_id="c1",
        source_message_id="caller-rollback",
        reserved_xu=50,
        now=5_300,
    )
    conn.commit()
    settled = settle_pro_request(
        conn,
        reserved["request_id"],
        input_tokens=1_000,
        output_tokens=500,
        provider_request_id="key4u-caller-rollback",
        now=5_301,
    )
    assert settled["status"] == "settled"
    assert conn.in_transaction is True
    conn.rollback()
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 50
    assert conn.execute("SELECT total_spent FROM users WHERE user_id='u1'").fetchone()[0] == 0
    assert tuple(
        conn.execute(
            "SELECT status, settled_xu, refunded_xu FROM public_chat_requests WHERE request_id=?",
            (reserved["request_id"],),
        ).fetchone()
    ) == ("reserved", 0, 0)
