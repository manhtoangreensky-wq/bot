import asyncio
from types import SimpleNamespace

import bot


class FakeQuery:
    def __init__(self, user_id: int, data: str):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id, username="tester", first_name="Tester")
        self.message = SimpleNamespace(chat_id=user_id)
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


def test_system_runtime_help_callback_uses_current_runtime_copy(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    for helper_name in (
        "clear_broadcast_lite_pending",
        "clear_translation_menu_pending",
        "clear_translation_session",
        "clear_media_creator_pending_states",
        "clear_support_ticket_pending",
        "clear_finance_compliance_pending",
        "clear_internal_archive_pending",
        "clear_doc_tool_pending",
        "clear_storage_addon_pending",
        "clear_memory_guided_pending",
        "clear_music_guided_pending",
    ):
        monkeypatch.setattr(bot, helper_name, lambda *_args, **_kwargs: None)

    query = FakeQuery(999, "menu|system_runtime_help")
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(user_data={})

    asyncio.run(bot.handle_menu_callback(update, context))

    assert len(query.edits) == 1
    text, kwargs = query.edits[0]
    assert "Railway" not in text
    assert "trạng thái runtime" in text
    callbacks = [
        button.callback_data
        for row in kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert callbacks == ["menu|admin", "menu|system", "menu|main"]
