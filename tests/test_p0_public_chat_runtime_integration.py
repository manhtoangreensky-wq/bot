"""Focused tests for the functional bot-facing public-chat seam."""

from __future__ import annotations

import asyncio
import sqlite3
from types import SimpleNamespace

import pytest

from services.chat_pro_pricing import calculate_opus_charge_xu
from services.public_chat_runtime import (
    _usage_from_result,
    resolve_public_chat_mode_action,
    run_public_chat_request,
)
from services.public_chat_store import ensure_schema


_INVALID_CACHE_VALUES = (
    pytest.param(False, id="false"),
    pytest.param(None, id="none"),
    pytest.param("", id="empty-string"),
    pytest.param(1.5, id="fractional"),
    pytest.param("not-a-number", id="nonnumeric"),
    pytest.param(-1, id="negative"),
)


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE users (user_id TEXT PRIMARY KEY, credits INTEGER NOT NULL, total_spent INTEGER NOT NULL DEFAULT 0)")
    conn.execute("CREATE TABLE credit_events (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, delta INTEGER, balance_after INTEGER, event_type TEXT, ref_id TEXT, note TEXT, created_at TEXT)")
    conn.execute("INSERT INTO users(user_id, credits) VALUES ('u1', 10000), ('admin', 0)")
    ensure_schema(conn)
    conn.commit()
    return conn


def _record(conn, user_id, delta, event_type, ref_id, note):
    balance = conn.execute("SELECT credits FROM users WHERE user_id=?", (str(user_id),)).fetchone()[0]
    conn.execute(
        "INSERT INTO credit_events(user_id, delta, balance_after, event_type, ref_id, note, created_at) VALUES (?,?,?,?,?,?,?)",
        (str(user_id), int(delta), int(balance), str(event_type), str(ref_id), str(note), "now"),
    )


class _GeminiModels:
    def __init__(self):
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text="free integration answer", usage_metadata=SimpleNamespace(prompt_token_count=3, candidates_token_count=2))


class _Gemini:
    def __init__(self):
        self.models = _GeminiModels()


class _Opus:
    def __init__(self, *, usage=None):
        self.calls = []
        self.usage = usage or {"input_tokens": 1000, "output_tokens": 500}

    async def public_chat_completion(self, messages, *, max_tokens=1200, **kwargs):
        self.calls.append({"messages": messages, "max_tokens": max_tokens, **kwargs})
        return {"ok": True, "text": "pro integration answer", "model": "claude-opus-4-8", "usage": self.usage, "provider_request_id": "key4u-test-1"}


class _SensitiveGeminiModels(_GeminiModels):
    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            text="answer token:supersecret",
            usage_metadata=SimpleNamespace(
                prompt_token_count=3, candidates_token_count=2
            ),
        )


class _SensitiveGemini:
    def __init__(self):
        self.models = _SensitiveGeminiModels()


class _SensitiveOpus(_Opus):
    async def public_chat_completion(self, messages, *, max_tokens=1200, **kwargs):
        self.calls.append({"messages": messages, "max_tokens": max_tokens, **kwargs})
        return {
            "ok": True,
            "text": "answer token:supersecret",
            "model": "claude-opus-4-8",
            "usage": self.usage,
            "provider_request_id": "key4u-sensitive-1",
        }


def _run(conn, **kwargs):
    record_credit_event = kwargs.pop("record_credit_event", _record)
    return asyncio.run(run_public_chat_request(conn=conn, owner_id=kwargs.pop("owner_id", "u1"), chat_id="chat", source_message_id=kwargs.pop("source_message_id", "m1"), text=kwargs.pop("text", "hello"), record_credit_event=record_credit_event, **kwargs))


def test_explicit_pro_mode_actions_are_idempotent_for_duplicate_callbacks():
    assert resolve_public_chat_mode_action("chat_pro_on", "normal") == "pro"
    assert resolve_public_chat_mode_action("chat_pro_on", "pro") == "pro"
    assert resolve_public_chat_mode_action("chat_pro_off", "pro") == "normal"
    assert resolve_public_chat_mode_action("chat_pro_off", "normal") == "normal"


def test_usage_parser_defaults_cache_only_when_cache_field_is_absent():
    usage = _usage_from_result(
        {"usage": {"input_tokens": 100, "output_tokens": 10}}
    )

    assert usage is not None
    assert (usage.input_tokens, usage.output_tokens, usage.cache_read_tokens) == (100, 10, 0)


@pytest.mark.parametrize("cache_read_tokens", _INVALID_CACHE_VALUES)
def test_usage_parser_rejects_explicit_invalid_cache_values(cache_read_tokens):
    usage = _usage_from_result(
        {
            "usage": {
                "input_tokens": 100,
                "output_tokens": 10,
                "cache_read_tokens": cache_read_tokens,
            }
        }
    )

    assert usage is None


@pytest.mark.parametrize("cache_read_tokens", _INVALID_CACHE_VALUES)
def test_functional_pro_refunds_explicit_invalid_cache_usage(cache_read_tokens):
    conn = _db()
    opus = _Opus(
        usage={
            "input_tokens": 100,
            "output_tokens": 10,
            "cache_read_tokens": cache_read_tokens,
        }
    )

    result = _run(
        conn,
        mode="pro",
        key4u_provider=opus,
        source_message_id="explicit-invalid-cache",
    )

    assert result["ok"] is False
    assert result["status"] == "provider_failure"
    assert result["provider_calls"] == 1
    assert len(opus.calls) == 1
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 10000
    assert conn.execute("SELECT status FROM public_chat_requests").fetchone()[0] == "refunded"
    assert conn.execute("SELECT COUNT(*) FROM public_chat_turns").fetchone()[0] == 0
    events = conn.execute(
        "SELECT delta,event_type FROM credit_events ORDER BY id"
    ).fetchall()
    assert len(events) == 2
    assert events[0][0] < 0
    assert [(event[0], event[1]) for event in events] == [
        (events[0][0], "public_chat_reserve"),
        (-events[0][0], "public_chat_refund"),
    ]


def test_functional_free_path_uses_pinned_gemini_and_consumes_success():
    conn = _db()
    gemini = _Gemini()
    result = _run(conn, gemini_client=gemini)

    assert result["ok"] is True, result
    assert result["model"] == "gemini-3.6-flash"
    assert len(gemini.models.calls) == 1
    assert gemini.models.calls[0]["model"] == "gemini-3.6-flash"
    assert conn.execute("SELECT COUNT(*) FROM public_chat_turns").fetchone()[0] == 2


def test_functional_pro_path_uses_public_key4u_adapter_and_settles_actual_usage():
    conn = _db()
    opus = _Opus()
    result = _run(conn, mode="pro", key4u_provider=opus, source_message_id="pro-1")

    assert result["ok"] is True, result
    assert result["model"] == "claude-opus-4-8"
    assert len(opus.calls) == 1
    assert opus.calls[0]["messages"][-1]["role"] == "user"
    assert result["charged_xu"] > 0
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] < 10000
    events = conn.execute(
        "SELECT delta,event_type FROM credit_events WHERE ref_id=? ORDER BY id",
        (result["request_id"],),
    ).fetchall()
    assert len(events) == 2
    assert events[0][0] < 0
    assert events[0][1] == "public_chat_reserve"
    assert tuple(events[1]) == (result["refunded_xu"], "public_chat_refund")
    assert sum(row[0] for row in events) == -result["charged_xu"]


def test_functional_owner_pro_is_free_without_credit_event():
    conn = _db()
    opus = _Opus()
    result = _run(conn, owner_id="admin", mode="pro", key4u_provider=opus, is_admin=True)

    assert result["ok"] is True, result
    assert result["charged_xu"] == 0
    assert conn.execute("SELECT credits FROM users WHERE user_id='admin'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM credit_events WHERE user_id='admin'").fetchone()[0] == 0


def test_openai_cache_is_subtracted_once_before_billing_and_storage():
    conn = _db()
    usage = {
        "input_tokens": 1_000,
        "output_tokens": 1,
        "cache_read_tokens": 200,
        "input_tokens_include_cache": True,
    }

    result = _run(
        conn,
        mode="pro",
        key4u_provider=_Opus(usage=usage),
        source_message_id="openai-cache",
    )

    assert result["ok"] is True, result
    assert result["actual_xu"] == calculate_opus_charge_xu(800, 1, 200)
    stored = conn.execute(
        "SELECT input_tokens,output_tokens,cache_read_tokens FROM public_chat_requests"
    ).fetchone()
    assert tuple(stored) == (800, 1, 200)


def test_anthropic_cache_keeps_separate_uncached_input_for_billing_and_storage():
    conn = _db()
    usage = {
        "input_tokens": 1_000,
        "output_tokens": 1,
        "cache_read_tokens": 200,
        "input_tokens_include_cache": False,
    }

    result = _run(
        conn,
        mode="pro",
        key4u_provider=_Opus(usage=usage),
        source_message_id="anthropic-cache",
    )

    assert result["ok"] is True, result
    assert result["actual_xu"] == calculate_opus_charge_xu(1_000, 1, 200)
    stored = conn.execute(
        "SELECT input_tokens,output_tokens,cache_read_tokens FROM public_chat_requests"
    ).fetchone()
    assert tuple(stored) == (1_000, 1, 200)


def test_inclusive_cache_larger_than_raw_input_is_rejected_and_refunded():
    conn = _db()
    usage = {
        "input_tokens": 100,
        "output_tokens": 10,
        "cache_read_tokens": 200,
        "input_tokens_include_cache": True,
    }

    result = _run(
        conn,
        mode="pro",
        key4u_provider=_Opus(usage=usage),
        source_message_id="invalid-cache",
    )

    assert result["ok"] is False
    assert result["status"] == "provider_failure"
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 10000
    assert conn.execute("SELECT status FROM public_chat_requests").fetchone()[0] == "refunded"
    assert conn.execute("SELECT COUNT(*) FROM public_chat_turns").fetchone()[0] == 0


def test_under_reserved_usage_refunds_all_and_never_delivers_partial_paid_output():
    conn = _db()
    conn.execute("UPDATE users SET credits=100 WHERE user_id='u1'")
    conn.commit()
    opus = _Opus(
        usage={
            "input_tokens": 10_000,
            "output_tokens": 10_000,
            "cache_read_tokens": 0,
            "input_tokens_include_cache": False,
        }
    )

    result = _run(
        conn,
        mode="pro",
        key4u_provider=opus,
        source_message_id="under-reserved-runtime",
    )

    row = conn.execute(
        """SELECT status,reserved_xu,actual_xu,settled_xu,refunded_xu,
                  uncollected_xu,reason FROM public_chat_requests"""
    ).fetchone()
    assert result["ok"] is False
    assert result["status"] == "insufficient_balance_after_usage"
    assert result["charged_xu"] == 0
    assert result["refunded_xu"] == row[1]
    assert result["uncollected_xu"] == row[2]
    assert "text" not in result
    assert tuple(row) == (
        "under_reserved_refunded",
        row[1],
        calculate_opus_charge_xu(10_000, 10_000),
        0,
        row[1],
        calculate_opus_charge_xu(10_000, 10_000),
        "insufficient_balance_after_usage",
    )
    assert tuple(conn.execute("SELECT credits,total_spent FROM users WHERE user_id='u1'").fetchone()) == (100, 0)
    assert conn.execute("SELECT COUNT(*) FROM public_chat_turns").fetchone()[0] == 0
    events = conn.execute(
        "SELECT delta,event_type FROM credit_events WHERE ref_id=? ORDER BY id",
        (result["request_id"],),
    ).fetchall()
    assert [(item[0], item[1]) for item in events] == [
        (-row[1], "public_chat_reserve"),
        (row[1], "public_chat_refund"),
    ]

    duplicate = _run(
        conn,
        mode="pro",
        key4u_provider=opus,
        source_message_id="under-reserved-runtime",
    )
    assert duplicate["status"] == "duplicate"
    assert duplicate["provider_calls"] == 0
    assert len(opus.calls) == 1
    assert tuple(conn.execute("SELECT credits,total_spent FROM users WHERE user_id='u1'").fetchone()) == (100, 0)
    assert conn.execute("SELECT COUNT(*) FROM credit_events WHERE ref_id=?", (result["request_id"],)).fetchone()[0] == 2


def test_next_valid_request_reconciles_stale_pro_once_even_if_refund_event_fails():
    from services.public_chat_store import reserve_pro_request

    conn = _db()
    stale = reserve_pro_request(
        conn,
        owner_id="u1",
        chat_id="stale-chat",
        source_message_id="stale-pro",
        reserved_xu=50,
        now=100,
    )
    conn.commit()
    attempted_events = []

    def failing_refund_event(conn, user_id, delta, event_type, ref_id, note):
        attempted_events.append((delta, event_type, ref_id))
        raise RuntimeError("credit event unavailable")

    first = _run(
        conn,
        mode="free",
        gemini_client=_Gemini(),
        source_message_id="after-stale-1",
        now=1_001,
        record_credit_event=failing_refund_event,
    )
    second = _run(
        conn,
        mode="free",
        gemini_client=_Gemini(),
        source_message_id="after-stale-2",
        now=1_002,
        record_credit_event=failing_refund_event,
    )

    assert first["ok"] is True
    assert second["ok"] is True
    assert attempted_events == [(50, "public_chat_refund", stale["request_id"])]
    assert tuple(
        conn.execute(
            "SELECT status,refunded_xu,reason FROM public_chat_requests WHERE request_id=?",
            (stale["request_id"],),
        ).fetchone()
    ) == ("refunded", 50, "stale_reservation")
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 10000
    assert conn.in_transaction is False


def test_stale_refund_commits_before_new_pro_preflight_rejects(monkeypatch):
    from services import public_chat_runtime as runtime
    from services.public_chat_store import reserve_pro_request

    conn = _db()
    stale = reserve_pro_request(
        conn,
        owner_id="u1",
        chat_id="stale-chat",
        source_message_id="stale-before-invalid-preflight",
        reserved_xu=50,
        now=100,
    )
    conn.commit()

    def invalid_reserve(*args, **kwargs):
        raise ValueError("invalid reservation input")

    monkeypatch.setattr(runtime, "reserve_xu", invalid_reserve)
    result = _run(
        conn,
        mode="pro",
        key4u_provider=_Opus(),
        source_message_id="invalid-pro-preflight",
        now=1_001,
    )

    assert result == {
        "ok": False,
        "status": "invalid_input",
        "mode": "pro",
        "provider_calls": 0,
    }
    assert conn.in_transaction is False
    conn.rollback()
    assert tuple(
        conn.execute(
            "SELECT status,refunded_xu,reason FROM public_chat_requests WHERE request_id=?",
            (stale["request_id"],),
        ).fetchone()
    ) == ("refunded", 50, "stale_reservation")
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 10000


def test_request_purges_only_public_turns_older_than_48_hours():
    conn = _db()
    now = 200_000
    cutoff = now - 48 * 60 * 60
    conn.executemany(
        """INSERT INTO public_chat_turns(
               owner_id,chat_id,session_id,role,mode,content,source_message_id,
               content_hash,redaction_applied,created_at
           ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        [
            ("u1", "chat", "old-session", "user", "free", "expired", "expired-turn", "old-hash", 0, cutoff - 1),
            ("u1", "chat", "live-session", "user", "free", "boundary", "boundary-turn", "boundary-hash", 0, cutoff),
            ("u1", "chat", "live-session", "assistant", "free", "boundary answer", "boundary-turn", "boundary-answer-hash", 0, cutoff),
            ("other", "other-chat", "other-session", "user", "free", "recent", "recent-other", "recent-hash", 0, now - 1),
        ],
    )
    conn.commit()

    result = _run(
        conn,
        mode="free",
        gemini_client=_Gemini(),
        source_message_id="purge-trigger",
        now=now,
    )

    assert result["ok"] is True, result
    rows = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT source_message_id,created_at FROM public_chat_turns"
        ).fetchall()
    }
    assert "expired-turn" not in rows
    assert rows["boundary-turn"] == cutoff
    assert rows["recent-other"] == now - 1
    assert conn.in_transaction is False


def test_pro_reserve_event_failure_rolls_back_before_provider_call():
    conn = _db()
    opus = _Opus()

    def fail_reserve_event(conn, user_id, delta, event_type, ref_id, note):
        if event_type == "public_chat_reserve":
            raise RuntimeError("credit event unavailable")
        _record(conn, user_id, delta, event_type, ref_id, note)

    result = _run(
        conn,
        mode="pro",
        key4u_provider=opus,
        source_message_id="reserve-event-failure",
        record_credit_event=fail_reserve_event,
    )

    assert result["ok"] is False
    assert result["status"] == "provider_failure"
    assert result["provider_calls"] == 0
    assert opus.calls == []
    assert conn.in_transaction is False
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 10000
    assert conn.execute("SELECT COUNT(*) FROM public_chat_requests").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM credit_events").fetchone()[0] == 0


def test_free_persistence_failure_releases_quota_after_provider_success(monkeypatch):
    from services import public_chat_runtime as runtime

    conn = _db()
    real_complete = runtime.complete_free_request

    def complete_then_fail(*args, **kwargs):
        completed = real_complete(*args, **kwargs)
        assert completed["consumed"] is True
        raise RuntimeError("turn persistence unavailable")

    monkeypatch.setattr(runtime, "complete_free_request", complete_then_fail)
    result = _run(
        conn,
        mode="free",
        gemini_client=_Gemini(),
        source_message_id="free-persistence-failure",
    )

    assert result["ok"] is False
    assert result["status"] == "provider_failure"
    assert result["provider_calls"] == 1
    assert conn.in_transaction is False
    assert tuple(
        conn.execute(
            "SELECT status,reason FROM public_chat_requests WHERE source_message_id='free-persistence-failure'"
        ).fetchone()
    ) == ("released", "persistence_failed")
    assert conn.execute("SELECT COUNT(*) FROM public_chat_turns").fetchone()[0] == 0


@pytest.mark.parametrize("mode", ["free", "pro"])
def test_non_string_provider_output_fails_closed_without_quota_or_xu_charge(monkeypatch, mode):
    from services import public_chat_runtime as runtime

    conn = _db()

    async def structured_output(**kwargs):
        return {
            "ok": True,
            "text": {"image_url": "https://example.invalid/image.png"},
            "usage": {"input_tokens": 10, "output_tokens": 10},
            "provider_request_id": "structured-output",
        }

    monkeypatch.setattr(runtime, "_call_provider", structured_output)
    result = _run(conn, mode=mode, source_message_id=f"structured-{mode}")

    assert result["ok"] is False
    assert result["status"] == "provider_failure"
    assert result["provider_calls"] == 1
    assert conn.execute("SELECT COUNT(*) FROM public_chat_turns").fetchone()[0] == 0
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 10000
    status = conn.execute("SELECT status FROM public_chat_requests").fetchone()[0]
    assert status == ("released" if mode == "free" else "refunded")


def test_pro_zero_token_usage_fails_closed_and_refunds():
    conn = _db()
    opus = _Opus(usage={"input_tokens": 0, "output_tokens": 0})

    result = _run(
        conn,
        mode="pro",
        key4u_provider=opus,
        source_message_id="zero-usage",
    )

    assert result["ok"] is False
    assert result["status"] == "provider_failure"
    assert result["provider_calls"] == 1
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 10000
    assert conn.execute("SELECT status FROM public_chat_requests").fetchone()[0] == "refunded"


def test_pro_receives_public_system_prompt_as_first_message():
    conn = _db()
    opus = _Opus()

    result = _run(
        conn,
        mode="pro",
        key4u_provider=opus,
        source_message_id="system-prompt",
        system_prompt="SYSTEM CONTRACT",
    )

    assert result["ok"] is True, result
    assert opus.calls[0]["messages"][0] == {
        "role": "system",
        "content": "SYSTEM CONTRACT",
    }
    assert opus.calls[0]["messages"][-1]["role"] == "user"


@pytest.mark.parametrize("mode", ["free", "pro"])
def test_pending_delivery_replays_from_cursor_without_second_provider_or_charge(mode):
    from services.public_chat_store import (
        advance_public_chat_delivery,
        load_pending_public_chat_delivery,
    )

    conn = _db()
    provider = _Gemini() if mode == "free" else _Opus()
    kwargs = {"gemini_client": provider} if mode == "free" else {"key4u_provider": provider}
    first = _run(
        conn,
        mode=mode,
        source_message_id=f"delivery-{mode}",
        **kwargs,
    )
    credits_after_first = conn.execute(
        "SELECT credits FROM users WHERE user_id='u1'"
    ).fetchone()[0]

    assert first["ok"] is True
    pending = load_pending_public_chat_delivery(
        conn, owner_id="u1", chat_id="chat", request_id=first["request_id"]
    )
    assert pending["text"] == first["text"]
    assert pending["delivery_cursor"] == 0

    advanced = advance_public_chat_delivery(
        conn, first["request_id"], next_cursor=1, total_chunks=2
    )
    conn.commit()
    assert advanced["delivery_cursor"] == 1
    duplicate = _run(
        conn,
        mode=mode,
        source_message_id=f"delivery-{mode}",
        **kwargs,
    )

    assert duplicate["ok"] is True
    assert duplicate["replay"] is True
    assert duplicate["provider_calls"] == 0
    assert duplicate["delivery_cursor"] == 1
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == credits_after_first
    provider_calls = provider.models.calls if mode == "free" else provider.calls
    assert len(provider_calls) == 1

    completed = advance_public_chat_delivery(
        conn, first["request_id"], next_cursor=2, total_chunks=2
    )
    conn.commit()
    assert completed["delivered"] is True
    assert load_pending_public_chat_delivery(
        conn, owner_id="u1", chat_id="chat", request_id=first["request_id"]
    ) is None


@pytest.mark.parametrize("mode", ["free", "pro"])
def test_initial_delivery_uses_same_canonical_sanitized_payload_as_replay(mode):
    from services.public_chat_store import load_pending_public_chat_delivery

    conn = _db()
    provider = _SensitiveGemini() if mode == "free" else _SensitiveOpus()
    kwargs = {"gemini_client": provider} if mode == "free" else {"key4u_provider": provider}

    first = _run(
        conn,
        mode=mode,
        source_message_id=f"canonical-{mode}",
        **kwargs,
    )
    pending = load_pending_public_chat_delivery(
        conn,
        owner_id="u1",
        chat_id="chat",
        request_id=first["request_id"],
    )

    assert first["ok"] is True
    assert "supersecret" not in first["text"]
    assert pending is not None
    assert first["text"] == pending["text"]


def test_pending_delivery_survives_context_expiry_until_it_is_delivered():
    from services.public_chat_store import (
        load_pending_public_chat_delivery,
        purge_expired_public_turns,
    )

    conn = _db()
    first = _run(
        conn,
        mode="pro",
        source_message_id="old-paid-delivery",
        key4u_provider=_Opus(),
    )
    old_timestamp = 1_700_000_000
    conn.execute(
        "UPDATE public_chat_requests SET created_at=?,updated_at=? WHERE request_id=?",
        (old_timestamp, old_timestamp, first["request_id"]),
    )
    conn.execute("UPDATE public_chat_turns SET created_at=?", (old_timestamp,))
    conn.commit()

    purge_expired_public_turns(conn, now=old_timestamp + 49 * 3600)
    conn.commit()
    pending = load_pending_public_chat_delivery(
        conn,
        owner_id="u1",
        chat_id="chat",
        request_id=first["request_id"],
        now=old_timestamp + 49 * 3600,
    )

    assert pending is not None
    assert pending["text"] == first["text"]
    assert conn.execute("SELECT COUNT(*) FROM public_chat_turns").fetchone()[0] == 0


def test_delivery_cursor_cannot_skip_chunks_or_change_total():
    from services.public_chat_store import (
        advance_public_chat_delivery,
        load_pending_public_chat_delivery,
    )

    conn = _db()
    first = _run(
        conn,
        mode="free",
        source_message_id="cursor-contract",
        gemini_client=_Gemini(),
    )

    gap = advance_public_chat_delivery(
        conn, first["request_id"], next_cursor=2, total_chunks=3
    )
    conn.commit()
    assert gap == {
        "updated": False,
        "delivered": False,
        "request_id": first["request_id"],
        "delivery_cursor": 0,
        "reason": "cursor_gap",
    }

    first_chunk = advance_public_chat_delivery(
        conn, first["request_id"], next_cursor=1, total_chunks=3
    )
    conn.commit()
    assert first_chunk["updated"] is True

    changed_total = advance_public_chat_delivery(
        conn, first["request_id"], next_cursor=2, total_chunks=2
    )
    conn.commit()
    assert changed_total["updated"] is False
    assert changed_total["reason"] == "total_chunks_mismatch"
    pending = load_pending_public_chat_delivery(
        conn, owner_id="u1", chat_id="chat", request_id=first["request_id"]
    )
    assert pending is not None
    assert pending["delivery_cursor"] == 1
    assert pending["delivery_total_chunks"] == 3


@pytest.mark.parametrize("mode", ["free", "pro"])
def test_provider_cancellation_releases_or_refunds_and_reraises(monkeypatch, mode):
    from services import public_chat_runtime as runtime

    conn = _db()

    async def cancelled_provider(**kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(runtime, "_call_provider", cancelled_provider)

    with pytest.raises(asyncio.CancelledError):
        _run(conn, mode=mode, source_message_id=f"cancelled-{mode}")

    row = conn.execute(
        "SELECT status,reason,reserved_xu,refunded_xu FROM public_chat_requests"
    ).fetchone()
    expected_status = "released" if mode == "free" else "refunded"
    assert row[0] == expected_status
    assert row[1] == "cancelled"
    assert row[3] == (0 if mode == "free" else row[2])
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 10000
    assert conn.execute("SELECT COUNT(*) FROM public_chat_turns").fetchone()[0] == 0
    assert conn.in_transaction is False


def test_post_settlement_exception_rolls_back_then_refunds_original_reserve(monkeypatch):
    from services import public_chat_runtime as runtime

    conn = _db()
    real_settle = runtime.settle_pro_request

    def settle_then_fail(*args, **kwargs):
        settled = real_settle(*args, **kwargs)
        assert settled["settled"] is True
        raise RuntimeError("post-settlement failure")

    monkeypatch.setattr(runtime, "settle_pro_request", settle_then_fail)
    result = _run(
        conn,
        mode="pro",
        key4u_provider=_Opus(),
        source_message_id="settlement-exception",
    )

    row = conn.execute(
        "SELECT status,reserved_xu,settled_xu,refunded_xu FROM public_chat_requests"
    ).fetchone()
    assert result["ok"] is False
    assert result["status"] == "provider_failure"
    assert tuple(row) == ("refunded", row[1], 0, row[1])
    assert tuple(conn.execute("SELECT credits,total_spent FROM users WHERE user_id='u1'").fetchone()) == (10000, 0)
    assert conn.execute("SELECT COUNT(*) FROM public_chat_turns").fetchone()[0] == 0
    assert conn.in_transaction is False


def test_settlement_credit_event_exception_cannot_strand_xu_or_turns():
    conn = _db()

    def fail_after_reserve(conn, user_id, delta, event_type, ref_id, note):
        if event_type != "public_chat_reserve":
            raise RuntimeError("credit event unavailable")
        _record(conn, user_id, delta, event_type, ref_id, note)

    result = _run(
        conn,
        mode="pro",
        key4u_provider=_Opus(),
        source_message_id="settlement-event-exception",
        record_credit_event=fail_after_reserve,
    )

    row = conn.execute(
        "SELECT status,reserved_xu,settled_xu,refunded_xu FROM public_chat_requests"
    ).fetchone()
    assert result["ok"] is False
    assert result["status"] == "provider_failure"
    assert tuple(row) == ("refunded", row[1], 0, row[1])
    assert tuple(conn.execute("SELECT credits,total_spent FROM users WHERE user_id='u1'").fetchone()) == (10000, 0)
    assert conn.execute("SELECT COUNT(*) FROM public_chat_turns").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM credit_events").fetchone()[0] == 1
    assert conn.in_transaction is False


def test_provider_failure_refund_commits_once_when_credit_event_callback_raises():
    conn = _db()

    class FailedOpus:
        def __init__(self):
            self.calls = 0

        async def public_chat_completion(self, messages, **kwargs):
            self.calls += 1
            return {"ok": False, "status": "provider_error", "text": ""}

    provider = FailedOpus()

    def fail_refund_event(conn, user_id, delta, event_type, ref_id, note):
        if event_type == "public_chat_refund":
            raise RuntimeError("credit event unavailable")
        _record(conn, user_id, delta, event_type, ref_id, note)

    first = _run(
        conn,
        mode="pro",
        key4u_provider=provider,
        source_message_id="provider-failure-event",
        record_credit_event=fail_refund_event,
    )
    second = _run(
        conn,
        mode="pro",
        key4u_provider=provider,
        source_message_id="provider-failure-event",
        record_credit_event=fail_refund_event,
    )

    row = conn.execute(
        "SELECT status,reserved_xu,settled_xu,refunded_xu FROM public_chat_requests"
    ).fetchone()
    assert first["ok"] is False
    assert first["status"] == "provider_failure"
    assert second["status"] == "duplicate"
    assert provider.calls == 1
    assert tuple(row) == ("refunded", row[1], 0, row[1])
    assert tuple(conn.execute("SELECT credits,total_spent FROM users WHERE user_id='u1'").fetchone()) == (10000, 0)
    assert conn.execute("SELECT COUNT(*) FROM public_chat_turns").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM credit_events").fetchone()[0] == 1
    assert conn.in_transaction is False


def test_actual_over_reserve_charges_actual_once_and_emits_settlement_delta():
    conn = _db()
    provider = _Opus(
        usage={
            "input_tokens": 10_000,
            "output_tokens": 2_000,
            "cache_read_tokens": 0,
            "input_tokens_include_cache": False,
        }
    )
    first = _run(
        conn,
        mode="pro",
        key4u_provider=provider,
        source_message_id="actual-over-reserve",
    )
    row = conn.execute(
        "SELECT reserved_xu,actual_xu,settled_xu,refunded_xu FROM public_chat_requests"
    ).fetchone()
    events = conn.execute(
        "SELECT delta,event_type FROM credit_events WHERE ref_id=? ORDER BY id",
        (first["request_id"],),
    ).fetchall()

    assert first["ok"] is True
    assert 0 < row[0] < row[1]
    assert tuple(row[1:]) == (first["actual_xu"], first["actual_xu"], 0)
    assert [(item[0], item[1]) for item in events] == [
        (-row[0], "public_chat_reserve"),
        (-(row[1] - row[0]), "public_chat_settlement"),
    ]
    assert tuple(conn.execute("SELECT credits,total_spent FROM users WHERE user_id='u1'").fetchone()) == (10000 - row[1], row[1])

    duplicate = _run(
        conn,
        mode="pro",
        key4u_provider=provider,
        source_message_id="actual-over-reserve",
    )
    assert duplicate["status"] == "ok"
    assert duplicate["replay"] is True
    assert duplicate["provider_calls"] == 0
    assert len(provider.calls) == 1
    assert tuple(conn.execute("SELECT credits,total_spent FROM users WHERE user_id='u1'").fetchone()) == (10000 - row[1], row[1])
    assert conn.execute("SELECT COUNT(*) FROM credit_events WHERE ref_id=?", (first["request_id"],)).fetchone()[0] == 2
