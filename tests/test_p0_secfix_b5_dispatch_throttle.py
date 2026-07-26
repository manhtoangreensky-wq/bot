"""SECFIX B5: a per-user token bucket in front of every handler.

Before this, the only abuse controls were per-job: one render at a time, a
duplicate-prompt check, a five second image cooldown. Nothing limited how fast
a single account could push updates in, so a flood reached job creation, the
provider gate and the wallet before anything said no.

The bucket runs at handler group -11, ahead of the safe-mode guards, and is
deliberately generous: a real person typing and tapping never meets it.
"""

from types import SimpleNamespace

import pytest

import bot


class _FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


class _FakeQuery:
    def __init__(self, uid):
        self.from_user = SimpleNamespace(id=uid)
        self.answers = []

    async def answer(self, text=None, **kwargs):
        self.answers.append(text)


def _update(uid):
    message = _FakeMessage()
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=uid, username=f"u{uid}"),
        effective_chat=SimpleNamespace(id=uid),
        effective_message=message,
        message=message,
        callback_query=None,
    )


@pytest.fixture(autouse=True)
def _clean_buckets(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", {"555000"})
    monkeypatch.setattr(bot, "OWNER_IDS", set())
    monkeypatch.setattr(bot, "DISPATCH_THROTTLE_ENABLED", True)
    monkeypatch.setattr(bot, "DISPATCH_THROTTLE_BURST", 5)
    monkeypatch.setattr(bot, "DISPATCH_THROTTLE_PER_MINUTE", 60)
    bot.dispatch_throttle_reset_state()
    yield
    bot.dispatch_throttle_reset_state()


def test_a_burst_from_one_user_is_cut_off():
    allowed = [bot.dispatch_throttle_allow(1001, now=100.0) for _ in range(12)]
    assert allowed[:5] == [True] * 5, "the configured burst must pass untouched"
    assert allowed[5:] == [False] * 7, "everything past the burst is dropped"


def test_normal_human_cadence_is_never_throttled():
    # One action every two seconds for a minute: far below the refill rate.
    moment = 500.0
    for _ in range(30):
        assert bot.dispatch_throttle_allow(1002, now=moment) is True
        moment += 2.0


def test_bucket_refills_over_time():
    for _ in range(5):
        assert bot.dispatch_throttle_allow(1003, now=0.0) is True
    assert bot.dispatch_throttle_allow(1003, now=0.0) is False
    # One token per second at 60/minute, so a two second pause buys two calls.
    assert bot.dispatch_throttle_allow(1003, now=2.0) is True
    assert bot.dispatch_throttle_allow(1003, now=2.0) is True
    assert bot.dispatch_throttle_allow(1003, now=2.0) is False


def test_two_users_have_independent_buckets():
    for _ in range(5):
        assert bot.dispatch_throttle_allow(1004, now=10.0) is True
    assert bot.dispatch_throttle_allow(1004, now=10.0) is False
    assert bot.dispatch_throttle_allow(1005, now=10.0) is True


def test_owner_is_exempt():
    for _ in range(50):
        assert bot.dispatch_throttle_allow(555000, now=20.0) is True


def test_disabled_flag_lets_everything_through(monkeypatch):
    monkeypatch.setattr(bot, "DISPATCH_THROTTLE_ENABLED", False)
    for _ in range(50):
        assert bot.dispatch_throttle_allow(1006, now=30.0) is True


def test_throttled_message_stops_the_handler_chain_and_answers_once():
    import asyncio

    from telegram.ext import ApplicationHandlerStop

    # Drain on the same clock the guard uses, otherwise the bucket refills
    # between the setup and the call under test.
    for _ in range(bot.DISPATCH_THROTTLE_BURST):
        assert bot.dispatch_throttle_allow(1007) is True
    assert bot.dispatch_throttle_allow(1007) is False

    first = _update(1007)
    with pytest.raises(ApplicationHandlerStop):
        asyncio.run(bot.dispatch_throttle_message_guard(first, SimpleNamespace()))
    assert first.message.replies, "a throttled user should be told once"
    assert "Xu" not in first.message.replies[0]

    second = _update(1007)
    with pytest.raises(ApplicationHandlerStop):
        asyncio.run(bot.dispatch_throttle_message_guard(second, SimpleNamespace()))
    assert second.message.replies == [], "the notice must not repeat on every drop"


def test_allowed_message_passes_through_without_stopping():
    import asyncio

    update = _update(1008)
    asyncio.run(bot.dispatch_throttle_message_guard(update, SimpleNamespace()))
    assert update.message.replies == []


def test_throttled_callback_is_answered_and_stopped():
    import asyncio

    from telegram.ext import ApplicationHandlerStop

    for _ in range(bot.DISPATCH_THROTTLE_BURST):
        assert bot.dispatch_throttle_allow(1009) is True
    assert bot.dispatch_throttle_allow(1009) is False
    query = _FakeQuery(1009)
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=1009))
    with pytest.raises(ApplicationHandlerStop):
        asyncio.run(bot.dispatch_throttle_callback_guard(update, SimpleNamespace()))
    assert query.answers, "a throttled tap should still get feedback"


def test_guards_are_registered_ahead_of_every_other_handler():
    from pathlib import Path

    source = Path(bot.__file__).read_text(encoding="utf-8", errors="replace")
    assert "dispatch_throttle_message_guard), group=-11)" in source
    assert "dispatch_throttle_callback_guard), group=-11)" in source
