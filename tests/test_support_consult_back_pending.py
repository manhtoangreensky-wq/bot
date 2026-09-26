"""Regression contract for leaving the Support consultation lead prompt."""

import asyncio
from types import SimpleNamespace

import bot


class _FakeQuery:
    def __init__(self, data, user_id):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace()

    async def answer(self, *_args, **_kwargs):
        return None


async def _press(data, user_id):
    await bot.handle_human_support_callback(
        SimpleNamespace(callback_query=_FakeQuery(data, user_id)),
        SimpleNamespace(),
    )


def test_consult_back_releases_lead_input_before_normal_text():
    user_id = 971226
    original_edit = bot.safe_edit_or_send
    original_language = bot.get_user_language

    async def fake_edit(*_args, **_kwargs):
        return SimpleNamespace()

    bot.safe_edit_or_send = fake_edit
    bot.get_user_language = lambda _user_id: "vi"
    bot.clear_support_ticket_pending(user_id)
    try:
        asyncio.run(_press("support|consult_type|video", user_id))
        asyncio.run(_press("support|consult_need|video|0", user_id))
        assert bot.get_support_ticket_pending(user_id)["step"] == "lead_input"

        asyncio.run(_press("support|consult_type|video", user_id))
        assert bot.get_support_ticket_pending(user_id) is None

        handled = asyncio.run(bot.handle_support_pending_input(
            SimpleNamespace(
                effective_user=SimpleNamespace(id=user_id),
                message=SimpleNamespace(text="Tin nhắn bình thường sau khi quay lại"),
            ),
            SimpleNamespace(),
        ))
        assert handled is False
    finally:
        bot.clear_support_ticket_pending(user_id)
        bot.safe_edit_or_send = original_edit
        bot.get_user_language = original_language
