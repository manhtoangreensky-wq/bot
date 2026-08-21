"""TDD contract for the isolated Telegram public-chat runtime seam.

The tests use in-memory SQLite and injected provider doubles.  They do not
import the monolithic Telegram module or make network/Telegram calls.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from services import public_chat_store
from services.public_chat_media import PublicChatAttachment
from services.public_chat_runtime import (
    CHAT_PRO_RATE_LABEL,
    public_chat_menu_rows,
    run_public_chat_request,
)


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE users (user_id TEXT PRIMARY KEY, credits INTEGER NOT NULL, total_spent INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute("CREATE TABLE credit_events (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, delta INTEGER, balance_after INTEGER, event_type TEXT, ref_id TEXT, note TEXT, created_at TEXT)")
    conn.execute("INSERT INTO users(user_id, credits) VALUES ('u1', 1000), ('admin', 0)")
    public_chat_store.ensure_schema(conn)
    conn.commit()
    return conn


class FakeGemini:
    def __init__(self, *, text: str = "free answer", error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.calls: list[dict] = []
        self.models = SimpleNamespace(generate_content=self.generate_content)

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.text)


class FakeOpus:
    def __init__(self, *, text: str = "pro answer", usage: dict | None = None, error: Exception | None = None) -> None:
        self.text = text
        self.usage = usage if usage is not None else {"input_tokens": 1000, "output_tokens": 500, "cache_read_tokens": 0}
        self.error = error
        self.calls: list[dict] = []
        self.connection: sqlite3.Connection | None = None

    async def chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        if self.connection is not None:
            assert self.connection.in_transaction is False
        if self.error:
            raise self.error
        return {"ok": True, "text": self.text, "model": "claude-opus-4-8", **self.usage, "provider_request_id": "opus-req"}

    async def document_completion(self, **kwargs):
        return await self.chat_completion(**kwargs)


def _record_credit(conn: sqlite3.Connection, user_id, delta, event_type, ref_id, note):
    balance = conn.execute("SELECT credits FROM users WHERE user_id=?", (str(user_id),)).fetchone()[0]
    conn.execute(
        "INSERT INTO credit_events(user_id,delta,balance_after,event_type,ref_id,note,created_at) VALUES (?,?,?,?,?,?,?)",
        (str(user_id), int(delta), int(balance), str(event_type), str(ref_id), str(note), "now"),
    )


def _run(conn, **kwargs):
    return asyncio.run(
        run_public_chat_request(
            conn=conn,
            owner_id=kwargs.pop("owner_id", "u1"),
            chat_id=kwargs.pop("chat_id", "chat-1"),
            source_message_id=kwargs.pop("source_message_id", "m-1"),
            text=kwargs.pop("text", "hello"),
            mode=kwargs.pop("mode", "free"),
            gemini_client=kwargs.pop("gemini_client", FakeGemini()),
            key4u_provider=kwargs.pop("key4u_provider", FakeOpus()),
            record_credit_event=_record_credit,
            **kwargs,
        )
    )


def test_free_routes_only_to_pinned_gemini_and_never_charges_wallet():
    conn = _connection()
    gemini = FakeGemini()
    opus = FakeOpus()
    result = _run(conn, gemini_client=gemini, key4u_provider=opus)

    assert result["ok"] is True
    assert result["mode"] == "free"
    assert len(gemini.calls) == 1
    assert gemini.calls[0]["model"] == "gemini-3.6-flash"
    assert opus.calls == []
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 1000


def test_free_21st_successful_turn_has_no_provider_call():
    conn = _connection()
    gemini = FakeGemini()
    for index in range(20):
        result = _run(conn, gemini_client=gemini, source_message_id=f"free-{index}")
        assert result["ok"] is True
    calls_before = len(gemini.calls)
    exhausted = _run(conn, gemini_client=gemini, source_message_id="free-21")

    assert exhausted["status"] == "free_quota_exhausted"
    assert len(gemini.calls) == calls_before


def test_free_failure_releases_slot_without_memory_or_charge():
    failure_clients = (
        FakeGemini(error=TimeoutError("timeout")),
        FakeGemini(error=RuntimeError("provider error")),
        FakeGemini(text=""),
        FakeGemini(text=None),
    )
    for index, gemini in enumerate(failure_clients):
        conn = _connection()
        result = _run(conn, gemini_client=gemini, source_message_id=f"failed-{index}")

        assert result["ok"] is False
        assert result["status"] == "provider_failure"
        assert conn.execute("SELECT COUNT(*) FROM public_chat_turns").fetchone()[0] == 0
        assert conn.execute("SELECT status FROM public_chat_requests").fetchone()[0] == "released"

    conn = _connection()
    gemini = FakeGemini()
    unsupported = PublicChatAttachment(
        "unknown", "application/octet-stream", "unsupported.bin", 0, 0, "a" * 64, Path("unused")
    )
    result = _run(conn, gemini_client=gemini, attachments=[unsupported], source_message_id="routing-failure")
    assert result["status"] == "unsupported"
    assert gemini.calls == []
    assert conn.execute("SELECT COUNT(*) FROM public_chat_requests").fetchone()[0] == 0


def test_pro_reserves_before_provider_and_settles_actual_usage():
    conn = _connection()
    opus = FakeOpus()
    opus.connection = conn
    result = _run(conn, mode="pro", key4u_provider=opus, source_message_id="pro-1")

    assert result["ok"] is True
    assert result["model"] == "claude-opus-4-8"
    assert opus.calls[0]["model"] == "claude-opus-4-8"
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] < 1000
    events = conn.execute("SELECT delta FROM credit_events WHERE ref_id LIKE 'public-chat-%' ORDER BY id").fetchall()
    assert events


def test_pro_has_no_daily_turn_limit_while_balance_is_sufficient():
    conn = _connection()
    opus = FakeOpus()

    for index in range(25):
        result = _run(
            conn,
            mode="pro",
            key4u_provider=opus,
            source_message_id=f"pro-unlimited-{index}",
        )
        assert result["ok"] is True

    assert len(opus.calls) == 25
    conn.execute("UPDATE users SET credits=0 WHERE user_id='u1'")
    conn.commit()
    blocked = _run(
        conn,
        mode="pro",
        key4u_provider=opus,
        source_message_id="pro-insufficient-balance",
    )
    assert blocked["status"] == "insufficient_balance"
    assert len(opus.calls) == 25


def test_pro_missing_usage_is_refunded_and_not_delivered():
    conn = _connection()
    opus = FakeOpus(usage={})
    result = _run(conn, mode="pro", key4u_provider=opus, source_message_id="pro-missing")

    assert result["ok"] is False
    assert result["status"] == "provider_failure"
    assert conn.execute("SELECT credits FROM users WHERE user_id='u1'").fetchone()[0] == 1000
    assert conn.execute("SELECT status FROM public_chat_requests").fetchone()[0] == "refunded"


def test_owner_pro_is_free_and_public_context_is_shared_for_48_hours():
    conn = _connection()
    _run(conn, text="first free question", source_message_id="f-1")
    shared = _run(conn, mode="pro", text="follow-up question", source_message_id="p-1")
    admin_opus = FakeOpus()
    for index in range(25):
        admin = _run(
            conn,
            owner_id="admin",
            mode="pro",
            is_admin=True,
            text=f"owner question {index}",
            source_message_id=f"admin-{index}",
            key4u_provider=admin_opus,
        )
        assert admin["ok"] is True

    assert shared["ok"] is True
    assert "first free question" in str(shared["provider_messages"])
    assert len(admin_opus.calls) == 25
    assert conn.execute("SELECT credits FROM users WHERE user_id='admin'").fetchone()[0] == 0


def test_duplicate_update_calls_provider_once():
    conn = _connection()
    gemini = FakeGemini()
    first = _run(conn, gemini_client=gemini, source_message_id="same")
    second = _run(conn, gemini_client=gemini, source_message_id="same")

    assert first["ok"] is True
    assert second["status"] == "ok"
    assert second["replay"] is True
    assert second["provider_calls"] == 0
    assert len(gemini.calls) == 1


def test_attachment_memory_keeps_only_safe_label_not_temp_path(tmp_path):
    conn = _connection()
    path = tmp_path / "private-image.png"
    payload = b"\x89PNG\r\n\x1a\nsmall"
    path.write_bytes(payload)
    attachment = PublicChatAttachment(
        "image", "image/png", "private-image.png", len(payload), len(payload), "a" * 64, path
    )

    result = _run(conn, attachments=[attachment], source_message_id="image-memory")
    context = public_chat_store.load_public_context(conn, "u1", "chat-1")
    stored = " ".join(turn["content"] for turn in context["turns"])

    assert result["ok"] is True
    assert "image:private-image.png:aaaaaaaaaaaa" in stored
    assert str(path) not in stored


def test_menu_puts_free_first_and_shows_exact_pro_rates():
    assert public_chat_menu_rows("vi") == [
        ["🆓 Công cụ miễn phí"],
        [f"💎 Chat Pro • {CHAT_PRO_RATE_LABEL}", "👤 Tài khoản"],
    ]
    assert public_chat_menu_rows("en")[0][0].startswith("🆓")
    assert public_chat_menu_rows("zh")[0][0].startswith("🆓")


def test_bot_source_connects_public_chat_only_after_protected_handlers():
    source = (Path(__file__).parents[1] / "bot.py").read_text(encoding="utf-8")

    ordinary = source.index("if not detected_video_url:\n        return await handle_public_chat_text(update, context)")
    assert ordinary > source.index("if await handle_support_pending_input(update, context):")
    assert ordinary > source.index("if pending_text_owner_active(uid):")

    photo = source[source.index("async def handle_photo"):source.index("async def handle_translation_media_pending_upload")]
    assert photo.index("handle_public_chat_attachment") > photo.index("handle_video_product_pending_media")
    document = source[source.index("async def handle_document_cache_only"):source.index("async def handle_caption_admin_tool_test_media")]
    assert document.index("handle_public_chat_attachment") > document.index("handle_image_menu_pending_document")
    media = source[source.index("async def handle_media("):source.index("VIDEO_DUBBING_TTL_SECONDS")]
    assert media.index("handle_public_chat_attachment") > media.index("handle_music_guided_pending_media")


def test_bot_source_exposes_only_free_and_pro_and_keeps_exact_menu_rows():
    source = (Path(__file__).parents[1] / "bot.py").read_text(encoding="utf-8")

    assert "Chat Deep" not in source
    assert "/chat_deep" not in source
    assert 'CommandHandler("chat_deep' not in source
    assert '[InlineKeyboardButton("🆓 Công cụ miễn phí", callback_data="freehub|main")]' in source
    assert 'InlineKeyboardButton(f"💎 Chat Pro • {public_chat_runtime.CHAT_PRO_RATE_LABEL}", callback_data="menu|chat_pro")' in source
