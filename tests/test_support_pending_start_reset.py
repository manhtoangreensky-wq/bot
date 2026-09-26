import asyncio
from types import SimpleNamespace

import pytest

import bot


@pytest.mark.parametrize("is_admin", [False, True], ids=["customer", "admin"])
@pytest.mark.parametrize("entrypoint", ["cmd_start", "cmd_menu"], ids=["start", "menu"])
def test_home_command_releases_support_input_without_losing_ticket_return(
    monkeypatch, is_admin, entrypoint
):
    monkeypatch.setattr(bot, "USER_PENDING", {})
    user_id = 941020 if is_admin else 941019
    step = "admin_search" if is_admin else "awaiting_ticket_reply"
    bot.clear_support_ticket_pending(user_id)
    bot.set_support_ticket_pending(user_id, step, ticket_id=42)
    bot.remember_last_support_ticket(user_id, 42)
    sent = []

    async def reply_text(*args, **kwargs):
        sent.append((args, kwargs))

    monkeypatch.setattr(bot, "log_command_received", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bot, "user_exists", lambda _uid: True)
    monkeypatch.setattr(bot, "get_user", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bot, "record_usage_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bot, "clear_pending_start_notice", lambda _uid: "")
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: is_admin)
    monkeypatch.setattr(bot, "has_user_language", lambda _uid: True)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "user_selected_vietnamese_initially", lambda _uid: False)
    monkeypatch.setattr(bot, "localized_start_menu_text", lambda *_args: "Home")
    monkeypatch.setattr(bot, "mode_start_notice", lambda _uid: "")
    monkeypatch.setattr(bot, "localized_main_menu_keyboard", lambda *_args: object())

    async def no_birthday_gift(*_args, **_kwargs):
        return None

    monkeypatch.setattr(bot, "maybe_auto_grant_birthday_gift", no_birthday_gift)
    user = SimpleNamespace(id=user_id, first_name="Test", username="test")
    update = SimpleNamespace(effective_user=user, message=SimpleNamespace(reply_text=reply_text))
    context = SimpleNamespace(args=[], user_data={})

    try:
        asyncio.run(getattr(bot, entrypoint)(update, context))

        assert sent
        assert bot.get_support_ticket_pending(user_id) is None
        assert bot.get_last_support_ticket_id(user_id) == 42
        ordinary_message = SimpleNamespace(text="nội dung bình thường", reply_text=reply_text)
        assert asyncio.run(bot.handle_support_pending_input(
            SimpleNamespace(effective_user=user, message=ordinary_message),
            context,
        )) is False
    finally:
        bot.clear_support_ticket_pending(user_id)
