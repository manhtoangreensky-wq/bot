"""SECFIX B3: one owner gate, checked at the outermost layer.

Two problems are locked down here.

1. Owner checks used to be written two ways. Most handlers call
   is_admin_user(), but 165 sites compared the caller against the single
   ADMIN_ID string, which ignores the ADMIN_IDS / OWNER_IDS sets. Those are
   now all is_admin_user() so there is exactly one definition of "owner".

2. run_admin_video_pipeline_smoke() had no authorisation of its own. It
   forwarded to execute_engine with gate_prechecked=True on the caller's
   behalf and relied on the inner core runner to reject strangers. The
   --confirm-paid flag is not an authorisation check: any caller can type it.
   The gate now sits at the outermost layer, before the engine is reached.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

import bot


class _FakeMessage:
    def __init__(self, text="/tool_test_video_dub"):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)
        return text


def _update(uid, text="/tool_test_video_dub"):
    message = _FakeMessage(text)
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=uid, username=f"u{uid}", first_name="Nguoi"),
        effective_chat=SimpleNamespace(id=uid),
        effective_message=message,
        message=message,
        callback_query=None,
    )


def _ctx(*args):
    return SimpleNamespace(args=list(args))


def _init_db(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "secfix_b3.db"))
    monkeypatch.setattr(bot, "DB_BACKUP_DIR", str(tmp_path / "db_backups"))
    monkeypatch.setattr(bot, "DATA_PERSISTENCE_MODE", "sqlite")
    bot.init_db()


def _as_owner(monkeypatch, uid):
    monkeypatch.setattr(bot, "ADMIN_IDS", {str(uid)})
    monkeypatch.setattr(bot, "OWNER_IDS", set())


def _as_stranger(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", {"777000"})
    monkeypatch.setattr(bot, "OWNER_IDS", set())


def test_no_raw_admin_id_comparison_remains_in_bot_source():
    source = Path(bot.__file__).read_text(encoding="utf-8", errors="replace")
    assert "!= ADMIN_ID" not in source, (
        "a handler still compares the caller against the single ADMIN_ID string; "
        "use is_admin_user() so ADMIN_IDS/OWNER_IDS stay authoritative"
    )


def test_is_admin_user_honours_both_id_sets(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", {"111"})
    monkeypatch.setattr(bot, "OWNER_IDS", {"222"})
    assert bot.is_admin_user(111) is True
    assert bot.is_admin_user("111") is True
    assert bot.is_admin_user(222) is True
    assert bot.is_admin_user(333) is False


def test_rewritten_guard_denies_stranger_and_admits_owner(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    import asyncio

    _as_stranger(monkeypatch)
    stranger = _update(424242, "/customer_surface")
    asyncio.run(bot.cmd_customer_surface(stranger, _ctx()))
    assert stranger.message.replies == [], "stranger must get nothing from an admin command"

    _as_owner(monkeypatch, 424242)
    owner = _update(424242, "/customer_surface")
    asyncio.run(bot.cmd_customer_surface(owner, _ctx()))
    assert owner.message.replies, "owner must still reach the admin command"


def test_smoke_wrapper_denies_stranger_before_reaching_the_engine(monkeypatch, tmp_path):
    """--confirm-paid is not authorisation: a stranger must never reach the engine."""
    _init_db(monkeypatch, tmp_path)
    _as_stranger(monkeypatch)
    import asyncio

    reached = {"engine": False, "core": False}

    async def _explode_engine(*args, **kwargs):
        reached["engine"] = True
        raise AssertionError("execute_engine reached by a non-owner")

    async def _explode_core(*args, **kwargs):
        reached["core"] = True
        raise AssertionError("smoke core reached by a non-owner")

    monkeypatch.setattr(bot, "execute_engine", _explode_engine)
    monkeypatch.setattr(bot, "_run_admin_video_pipeline_smoke_core", _explode_core)

    update = _update(424242)
    asyncio.run(
        bot.run_admin_video_pipeline_smoke(
            update, _ctx(bot.ADMIN_PAID_CONFIRM_FLAG), bot.VIDEO_SUBTITLE_MODE_DUB
        )
    )

    assert reached["engine"] is False
    assert reached["core"] is False
    assert update.message.replies, "stranger should get a refusal, not silence"


def test_smoke_wrapper_still_lets_the_owner_through(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    _as_owner(monkeypatch, 424242)
    import asyncio

    seen = {}

    async def _stub_core(update, context, mode):
        seen["mode"] = mode
        return "core-reached"

    async def _explode_engine(*args, **kwargs):
        raise AssertionError("no-confirm path must not reach the engine")

    monkeypatch.setattr(bot, "_run_admin_video_pipeline_smoke_core", _stub_core)
    monkeypatch.setattr(bot, "execute_engine", _explode_engine)

    update = _update(424242)
    # No --confirm-paid: the wrapper hands straight to the core guard, which is
    # where the NO_CONFIRM answer is produced. No provider call happens.
    result = asyncio.run(
        bot.run_admin_video_pipeline_smoke(update, _ctx(), bot.VIDEO_SUBTITLE_MODE_DUB)
    )
    assert result == "core-reached"
    assert seen["mode"] == bot.VIDEO_SUBTITLE_MODE_DUB


def test_paid_confirmation_flag_is_not_an_authorisation_check():
    assert bot.has_admin_paid_confirmation(SimpleNamespace(args=[bot.ADMIN_PAID_CONFIRM_FLAG])) is True
    assert bot.has_admin_paid_confirmation(SimpleNamespace(args=[])) is False
