from __future__ import annotations

import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

from services.chat_pro_pricing import (
    CLAUDE_OPUS_MODEL,
    ClaudeOpusPricing,
    TokenUsage,
    calculate_actual_xu,
)
from services.public_chat_runtime import PublicChatRequest, PublicChatRuntime
from services.public_chat_store import PublicChatStore, vietnam_quota_date


class _Provider:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    async def __call__(self, request, *, model):
        self.calls.append({"request": request, "model": model})
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


class _Wallet:
    def __init__(self, balance=10_000):
        self.balance = balance
        self.balance_calls = []
        self.reserves = []
        self.settles = []
        self.releases = []

    async def get_balance(self, account_id):
        self.balance_calls.append(account_id)
        return self.balance

    async def reserve(self, account_id, amount_xu, request_id):
        self.reserves.append((account_id, amount_xu, request_id))
        if amount_xu > self.balance:
            return {"ok": False, "reason": "insufficient_xu"}
        self.balance -= amount_xu
        return {"ok": True, "reservation_id": f"wallet:{request_id}", "reserved_xu": amount_xu}

    async def settle(self, account_id, reservation_id, actual_xu, request_id):
        self.settles.append((account_id, reservation_id, actual_xu, request_id))
        return {"ok": True}

    async def release(self, account_id, reservation_id, request_id):
        self.releases.append((account_id, reservation_id, request_id))
        return {"ok": True}


def _pricing():
    return ClaudeOpusPricing(input_xu_per_million=100, output_xu_per_million=500, multiplier=3)


def _request(source="m1", *, mode="free", role="user"):
    return PublicChatRequest(
        account_id="u1",
        chat_id="chat-1",
        source_message_id=source,
        mode=mode,
        prompt="hello",
        role=role,
        estimated_input_tokens=200_000,
        max_output_tokens=100_000,
    )


def test_vietnam_quota_date_uses_ho_chi_minh_day_boundary():
    utc_time = datetime(2026, 8, 9, 17, 0, tzinfo=timezone.utc)

    assert vietnam_quota_date(utc_time) == "2026-08-10"


def test_free_quota_atomic_race_allows_exactly_20_of_21(tmp_path):
    store = PublicChatStore(tmp_path / "chat.sqlite3")
    gate = Barrier(21)

    def reserve(index):
        gate.wait()
        return store.reserve_free_request("u1", f"chat-{index}", f"message-{index}", quota_date="2026-08-10")

    with ThreadPoolExecutor(max_workers=21) as pool:
        decisions = list(pool.map(reserve, range(21)))

    assert sum(item.status == "reserved" for item in decisions) == 20
    assert sum(item.status == "quota_exhausted" for item in decisions) == 1
    assert store.free_usage_count("u1", "2026-08-10") == 20


def test_free_duplicate_is_single_request_and_success_consumes_once(tmp_path):
    store = PublicChatStore(tmp_path / "chat.sqlite3")
    provider = _Provider([{"ok": True, "text": " final ", "model": "gemini-3.7-flash"}])
    runtime = PublicChatRuntime(store=store, free_provider=provider)
    request = _request()

    first = asyncio.run(runtime.run(request))
    duplicate = asyncio.run(runtime.run(request))

    assert first["ok"] is True
    assert duplicate == first
    assert len(provider.calls) == 1
    assert store.free_usage_count("u1", vietnam_quota_date()) == 1


def test_free_fail_timeout_empty_and_invalid_release_without_consuming(tmp_path):
    store = PublicChatStore(tmp_path / "chat.sqlite3")
    provider = _Provider(
        [
            {"ok": False, "text": "", "status": "FAIL"},
            TimeoutError("slow provider"),
            {"ok": True, "text": "   ", "model": "gemini-3.7-flash"},
            {"ok": True, "text": {"not": "text"}, "model": "gemini-3.7-flash"},
        ]
    )
    runtime = PublicChatRuntime(store=store, free_provider=provider)

    results = [asyncio.run(runtime.run(_request(f"m{index}"))) for index in range(4)]

    assert all(result["ok"] is False for result in results)
    assert store.free_usage_count("u1", vietnam_quota_date()) == 0
    assert len(provider.calls) == 4


def test_free_cancellation_releases_daily_quota_and_propagates(tmp_path):
    db_path = tmp_path / "free-cancelled.sqlite3"
    store = PublicChatStore(db_path)
    provider = _Provider([asyncio.CancelledError()])
    runtime = PublicChatRuntime(store=store, free_provider=provider)

    try:
        asyncio.run(runtime.run(_request(mode="free")))
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("cancellation must propagate after quota release")

    assert store.free_usage_count("u1", vietnam_quota_date()) == 0
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT status,reason FROM public_chat_requests"
        ).fetchone() == ("released", "cancelled")


def test_legacy_users_free_columns_are_not_quota_authority(tmp_path):
    db_path = tmp_path / "chat.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE users (user_id TEXT PRIMARY KEY, free_chat_count INTEGER, free_chat_date TEXT)")
        conn.execute("INSERT INTO users VALUES ('u1', 20, '2026-08-10')")
    store = PublicChatStore(db_path)

    decision = store.reserve_free_request("u1", "chat", "message", quota_date="2026-08-10")

    assert decision.status == "reserved"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT free_chat_count, free_chat_date FROM users WHERE user_id='u1'").fetchone() == (20, "2026-08-10")


def test_claude_actual_provider_tokens_are_priced_at_three_times_rate():
    usage = TokenUsage(input_tokens=200_000, output_tokens=100_000)

    assert CLAUDE_OPUS_MODEL == "claude-opus-4-8"
    assert calculate_actual_xu(usage, _pricing()) == 210


def test_pro_preflight_insufficient_xu_skips_provider_and_reservation(tmp_path):
    store = PublicChatStore(tmp_path / "chat.sqlite3")
    provider = _Provider([{"ok": True, "text": "must not run"}])
    wallet = _Wallet(balance=1)
    runtime = PublicChatRuntime(store=store, pro_provider=provider, wallet=wallet, pricing=_pricing())

    result = asyncio.run(runtime.run(_request(mode="pro")))

    assert result["ok"] is False
    assert result["status"] == "INSUFFICIENT_XU"
    assert provider.calls == []
    assert wallet.reserves == []


def test_pro_reserves_then_settles_actual_usage_exactly_once_for_duplicates(tmp_path):
    store = PublicChatStore(tmp_path / "chat.sqlite3")
    provider = _Provider(
        [{"ok": True, "text": "pro answer", "model": "claude-opus-4-8", "usage": {"input_tokens": 200_000, "output_tokens": 100_000}}]
    )
    wallet = _Wallet()
    runtime = PublicChatRuntime(store=store, pro_provider=provider, wallet=wallet, pricing=_pricing())
    request = _request(mode="pro")

    first = asyncio.run(runtime.run(request))
    duplicate = asyncio.run(runtime.run(request))

    assert first["ok"] is True
    assert duplicate == first
    assert first["cost_xu"] == 210
    assert [call["model"] for call in provider.calls] == ["claude-opus-4-8"]
    assert len(wallet.reserves) == 1
    assert len(wallet.settles) == 1
    assert wallet.settles[0][2] == 210
    assert wallet.releases == []


def test_pro_failure_or_missing_actual_usage_releases_once(tmp_path):
    for index, provider_result in enumerate(
        [
            {"ok": False, "status": "FAIL_PROVIDER"},
            {"ok": True, "text": "answer", "model": "claude-opus-4-8"},
        ]
    ):
        store = PublicChatStore(tmp_path / f"chat-{index}.sqlite3")
        provider = _Provider([provider_result])
        wallet = _Wallet()
        runtime = PublicChatRuntime(store=store, pro_provider=provider, wallet=wallet, pricing=_pricing())
        request = _request(mode="pro")

        first = asyncio.run(runtime.run(request))
        duplicate = asyncio.run(runtime.run(request))

        assert first["ok"] is False
        assert duplicate == first
        assert len(wallet.reserves) == 1
        assert len(wallet.releases) == 1
        assert wallet.settles == []


def test_pro_cancellation_releases_wallet_reservation_and_terminalizes_request(tmp_path):
    db_path = tmp_path / "cancelled.sqlite3"
    store = PublicChatStore(db_path)
    provider = _Provider([asyncio.CancelledError()])
    wallet = _Wallet()
    runtime = PublicChatRuntime(store=store, pro_provider=provider, wallet=wallet, pricing=_pricing())

    try:
        asyncio.run(runtime.run(_request(mode="pro")))
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("cancellation must propagate after compensation")

    assert len(wallet.reserves) == 1
    assert len(wallet.releases) == 1
    assert wallet.settles == []
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT status,reason FROM public_chat_requests"
        ).fetchone() == ("refunded", "cancelled")


def test_owner_and_admin_pro_cost_zero_without_any_wallet_mutation(tmp_path):
    for role in ("owner", "admin"):
        store = PublicChatStore(tmp_path / f"{role}.sqlite3")
        provider = _Provider(
            [{"ok": True, "text": "answer", "model": "claude-opus-4-8", "usage": {"input_tokens": 20, "output_tokens": 10}}]
        )
        wallet = _Wallet(balance=0)
        runtime = PublicChatRuntime(store=store, pro_provider=provider, wallet=wallet, pricing=_pricing())

        result = asyncio.run(runtime.run(_request(mode="pro", role=role)))

        assert result["ok"] is True
        assert result["cost_xu"] == 0
        assert wallet.balance_calls == []
        assert wallet.reserves == []
        assert wallet.settles == []
        assert wallet.releases == []
