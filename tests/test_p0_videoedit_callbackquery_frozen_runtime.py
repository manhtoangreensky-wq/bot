import asyncio
import inspect
from types import SimpleNamespace

from telegram import CallbackQuery, User

import bot


def _frozen_videoedit_query(data: str) -> CallbackQuery:
    return CallbackQuery(
        id="videoedit-frozen-callback",
        from_user=User(id=7126457028, first_name="Owner", is_bot=False),
        chat_instance="videoedit-live-smoke",
        data=data,
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
