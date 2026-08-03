import asyncio
import inspect
from types import SimpleNamespace

from telegram import CallbackQuery, User

import bot


def _frozen_videoedit_query(
    data: str,
    *,
    callback_id: str = "videoedit-frozen-callback",
) -> CallbackQuery:
    return CallbackQuery(
        id=callback_id,
        from_user=User(id=7126457028, first_name="Owner", is_bot=False),
        chat_instance="videoedit-live-smoke",
        data=data,
    )


def _patch_stale_videoedit_tail(monkeypatch, winner: dict) -> None:
    monkeypatch.setattr(bot, "get_user_language", lambda _user_id: "vi")
    monkeypatch.setattr(
        bot,
        "video_tail9_context",
        lambda _user_id, _context: ({}, "video_edit", dict(winner)),
    )
    monkeypatch.setattr(
        bot.video_tail9,
        "claim_callback",
        lambda tail, callback_id: (
            {**dict(tail), "last_callback_id": callback_id},
            True,
        ),
    )
    monkeypatch.setattr(
        bot,
        "compare_and_set_video_editor_pending",
        lambda *_args, **_kwargs: (False, dict(winner)),
    )
    monkeypatch.setattr(
        bot,
        "video_editor_current_render_model",
        lambda _state, _lang: ("winning Video Edit screen", None, "HTML"),
    )


def test_videoedit_hub_answers_without_mutating_frozen_callbackquery(monkeypatch):
    edits: list[str] = []
    answers: list[tuple[object, bool]] = []
    query = _frozen_videoedit_query("videoedit|hub")
    user_id = query.from_user.id

    async def fake_edit_message_text(self, text, **_kwargs):
        edits.append(str(text))
        return SimpleNamespace(message_id=101)

    async def fake_answer(self, text=None, show_alert=False, **_kwargs):
        answers.append((text, bool(show_alert)))
        return True

    monkeypatch.setattr(CallbackQuery, "edit_message_text", fake_edit_message_text)
    monkeypatch.setattr(CallbackQuery, "answer", fake_answer)
    monkeypatch.setattr(bot, "get_user_language", lambda _user_id: "vi")

    bot.clear_video_editor_pending(user_id)
    bot.clear_video_session(user_id)
    bot.clear_developing_video_pending(user_id)
    try:
        asyncio.run(
            bot.handle_video_editor_callback(
                SimpleNamespace(callback_query=query),
                SimpleNamespace(user_data={}),
            )
        )
    finally:
        bot.clear_video_editor_pending(user_id)
        bot.clear_video_session(user_id)
        bot.clear_developing_video_pending(user_id)

    assert len(edits) == 1
    assert answers == [(None, False)]


def test_legacy_videoedit_hub_delegation_keeps_frozen_callback_payload(monkeypatch):
    edits: list[str] = []
    answers: list[tuple[object, bool]] = []
    legacy_payload = "vproduct|legacy|video_local_edit"
    query = _frozen_videoedit_query(legacy_payload)
    user_id = query.from_user.id

    async def fake_edit_message_text(self, text, **_kwargs):
        edits.append(str(text))
        return SimpleNamespace(message_id=102)

    async def fake_answer(self, text=None, show_alert=False, **_kwargs):
        answers.append((text, bool(show_alert)))
        return True

    monkeypatch.setattr(CallbackQuery, "edit_message_text", fake_edit_message_text)
    monkeypatch.setattr(CallbackQuery, "answer", fake_answer)
    monkeypatch.setattr(bot, "get_user_language", lambda _user_id: "vi")

    bot.clear_video_editor_pending(user_id)
    bot.clear_video_session(user_id)
    bot.clear_developing_video_pending(user_id)
    bot.set_video_route_session(
        user_id,
        "video_local_edit",
        "tool_home",
        product_id="video_local_edit",
    )
    try:
        asyncio.run(
            bot.handle_video_product_callback(
                SimpleNamespace(callback_query=query),
                SimpleNamespace(user_data={}),
            )
        )
    finally:
        bot.clear_video_editor_pending(user_id)
        bot.clear_video_session(user_id)
        bot.clear_developing_video_pending(user_id)

    assert edits == [bot.video_edit_hub_text("vi")]
    assert answers == [(None, False)]
    assert query.data == legacy_payload


def test_stale_legacy_tail_then_direct_callback_restores_task_local_flags(monkeypatch):
    answers: dict[str, list[tuple[object, bool]]] = {}
    edits: dict[str, list[str]] = {}
    tail_query = _frozen_videoedit_query(
        "video_tail|review|open",
        callback_id="videoedit-stale-tail-sequential",
    )
    direct_query = _frozen_videoedit_query(
        "videoedit|hub",
        callback_id="videoedit-direct-after-stale",
    )
    user_id = tail_query.from_user.id
    winner = {"step": "review", "current_screen": "review", "status": "review_ready"}

    async def fake_edit_message_text(self, text, **_kwargs):
        edits.setdefault(self.id, []).append(str(text))
        return SimpleNamespace(message_id=103)

    async def fake_answer(self, text=None, show_alert=False, **_kwargs):
        answers.setdefault(self.id, []).append((text, bool(show_alert)))
        return True

    monkeypatch.setattr(CallbackQuery, "edit_message_text", fake_edit_message_text)
    monkeypatch.setattr(CallbackQuery, "answer", fake_answer)
    _patch_stale_videoedit_tail(monkeypatch, winner)

    async def scenario():
        await bot.handle_video_tail_callback(
            SimpleNamespace(callback_query=tail_query),
            SimpleNamespace(user_data={}),
        )
        after_stale = (
            bot._VIDEO_EDIT_CALLBACK_ANSWERED.get(),
            bot._VIDEO_EDIT_CALLBACK_TRANSACTIONAL.get(),
        )
        await bot.handle_video_editor_callback(
            SimpleNamespace(callback_query=direct_query),
            SimpleNamespace(user_data={}),
        )
        after_direct = (
            bot._VIDEO_EDIT_CALLBACK_ANSWERED.get(),
            bot._VIDEO_EDIT_CALLBACK_TRANSACTIONAL.get(),
        )
        return after_stale, after_direct

    original_answered = bot._VIDEO_EDIT_CALLBACK_ANSWERED.get()
    original_transactional = bot._VIDEO_EDIT_CALLBACK_TRANSACTIONAL.get()
    answered_token = bot._VIDEO_EDIT_CALLBACK_ANSWERED.set(False)
    transactional_token = bot._VIDEO_EDIT_CALLBACK_TRANSACTIONAL.set(False)
    bot.clear_video_editor_pending(user_id)
    bot.clear_video_session(user_id)
    bot.clear_developing_video_pending(user_id)
    try:
        after_stale, after_direct = asyncio.run(scenario())
    finally:
        bot.clear_video_editor_pending(user_id)
        bot.clear_video_session(user_id)
        bot.clear_developing_video_pending(user_id)
        bot._VIDEO_EDIT_CALLBACK_TRANSACTIONAL.reset(transactional_token)
        bot._VIDEO_EDIT_CALLBACK_ANSWERED.reset(answered_token)

    assert after_stale == (False, False)
    assert after_direct == (False, False)
    assert answers[tail_query.id] == [
        (
            "Màn hình vừa thay đổi. TOAN AAS đã giữ phiên mới nhất; vui lòng thao tác lại.",
            True,
        )
    ]
    assert answers[direct_query.id] == [(None, False)]
    assert edits[tail_query.id] == ["winning Video Edit screen"]
    assert edits[direct_query.id] == [bot.video_edit_hub_text("vi")]
    assert bot._VIDEO_EDIT_CALLBACK_ANSWERED.get() is original_answered
    assert bot._VIDEO_EDIT_CALLBACK_TRANSACTIONAL.get() is original_transactional


def test_overlapping_stale_tail_and_direct_callback_keep_contexts_isolated(monkeypatch):
    answers: dict[str, list[tuple[object, bool]]] = {}
    edits: dict[str, list[str]] = {}
    tail_query = _frozen_videoedit_query(
        "video_tail|review|open",
        callback_id="videoedit-stale-tail-overlap",
    )
    direct_query = _frozen_videoedit_query(
        "videoedit|hub",
        callback_id="videoedit-direct-overlap",
    )
    user_id = tail_query.from_user.id
    winner = {"step": "review", "current_screen": "review", "status": "review_ready"}
    both_rendering = asyncio.Event()
    render_arrivals = 0

    async def fake_edit_message_text(self, text, **_kwargs):
        nonlocal render_arrivals
        edits.setdefault(self.id, []).append(str(text))
        render_arrivals += 1
        if render_arrivals == 2:
            both_rendering.set()
        await asyncio.wait_for(both_rendering.wait(), timeout=1.0)
        return SimpleNamespace(message_id=104)

    async def fake_answer(self, text=None, show_alert=False, **_kwargs):
        answers.setdefault(self.id, []).append((text, bool(show_alert)))
        return True

    monkeypatch.setattr(CallbackQuery, "edit_message_text", fake_edit_message_text)
    monkeypatch.setattr(CallbackQuery, "answer", fake_answer)
    _patch_stale_videoedit_tail(monkeypatch, winner)

    async def run_tail():
        await bot.handle_video_tail_callback(
            SimpleNamespace(callback_query=tail_query),
            SimpleNamespace(user_data={}),
        )
        return (
            bot._VIDEO_EDIT_CALLBACK_ANSWERED.get(),
            bot._VIDEO_EDIT_CALLBACK_TRANSACTIONAL.get(),
        )

    async def run_direct():
        await bot.handle_video_editor_callback(
            SimpleNamespace(callback_query=direct_query),
            SimpleNamespace(user_data={}),
        )
        return (
            bot._VIDEO_EDIT_CALLBACK_ANSWERED.get(),
            bot._VIDEO_EDIT_CALLBACK_TRANSACTIONAL.get(),
        )

    async def scenario():
        return await asyncio.gather(run_tail(), run_direct())

    original_answered = bot._VIDEO_EDIT_CALLBACK_ANSWERED.get()
    original_transactional = bot._VIDEO_EDIT_CALLBACK_TRANSACTIONAL.get()
    answered_token = bot._VIDEO_EDIT_CALLBACK_ANSWERED.set(False)
    transactional_token = bot._VIDEO_EDIT_CALLBACK_TRANSACTIONAL.set(False)
    bot.clear_video_editor_pending(user_id)
    bot.clear_video_session(user_id)
    bot.clear_developing_video_pending(user_id)
    try:
        tail_flags, direct_flags = asyncio.run(scenario())
    finally:
        bot.clear_video_editor_pending(user_id)
        bot.clear_video_session(user_id)
        bot.clear_developing_video_pending(user_id)
        bot._VIDEO_EDIT_CALLBACK_TRANSACTIONAL.reset(transactional_token)
        bot._VIDEO_EDIT_CALLBACK_ANSWERED.reset(answered_token)

    assert tail_flags == (False, False)
    assert direct_flags == (False, False)
    assert len(answers[tail_query.id]) == 1
    assert len(answers[direct_query.id]) == 1
    assert len(edits[tail_query.id]) == 1
    assert len(edits[direct_query.id]) == 1
    assert bot._VIDEO_EDIT_CALLBACK_ANSWERED.get() is original_answered
    assert bot._VIDEO_EDIT_CALLBACK_TRANSACTIONAL.get() is original_transactional


def test_videoedit_runtime_flags_are_kept_off_telegram_callback_objects():
    source = "\n".join(
        (
            inspect.getsource(bot.safe_edit_or_send),
            inspect.getsource(bot.rerender_video_editor_after_stale_commit),
            inspect.getsource(bot.handle_video_tail_callback),
        )
    )

    assert 'setattr(query, "_video_edit_callback_answered"' not in source
    assert 'setattr(query, "_video_edit_transactional"' not in source
