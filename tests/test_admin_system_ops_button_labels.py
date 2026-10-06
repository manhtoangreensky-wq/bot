import asyncio
import inspect
from types import SimpleNamespace

import bot


class FakeQuery:
    def __init__(self, user_id, data):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace(chat_id=user_id, message_id=1)
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


def _buttons(markup):
    return {
        button.text: button.callback_data
        for row in markup.inline_keyboard
        for button in row
    }


def test_system_ops_runtime_shortcuts_are_labeled_as_guides_without_retargeting():
    buttons = _buttons(bot.admin_module_keyboard("system_ops"))

    assert buttons["📘 Hướng dẫn kiểm tra Telegram"] == "admin_help|runtime|admin_system_ops"
    assert buttons["📘 Hướng dẫn nhận quyền webhook Telegram"] == "admin_help|runtime|admin_system_ops"
    assert buttons["📘 Hướng dẫn dọn file tạm"] == "admin_help|runtime|admin_system_ops"
    assert buttons["📊 Dashboard"] == "menu|admin_overview"


def test_all_system_runtime_help_shortcuts_are_labeled_as_guides_without_retargeting():
    screens = [
        bot.menu_nav_keyboard("system", True),
        bot.admin_module_keyboard("security_db"),
        bot.admin_module_keyboard("system_ops"),
    ]
    runtime_buttons = [
        button
        for screen in screens
        for row in screen.inline_keyboard
        for button in row
        if button.callback_data == "menu|system_runtime_help"
    ]

    assert len(runtime_buttons) == 3
    assert all(button.text == "📘 Hướng dẫn Runtime" for button in runtime_buttons)


def test_all_system_ops_guide_callbacks_are_registered_and_open_runtime_handbook(monkeypatch):
    source = inspect.getsource(bot.lifespan)
    assert 'CallbackQueryHandler(handle_admin_help_callback, pattern=r"^admin_help\\|")' in source

    monkeypatch.setattr(bot, "ADMIN_IDS", {"999"})
    monkeypatch.setattr(bot, "OWNER_IDS", set())
    guide_callbacks = [
        callback
        for row in bot.ADMIN_CONTROL_MODULES["system_ops"]["buttons"]
        for _label, callback in row
        if callback == "admin_help|runtime"
    ]
    assert len(guide_callbacks) == 3

    for callback in guide_callbacks:
        query = FakeQuery(999, callback)
        asyncio.run(
            bot.handle_admin_help_callback(
                SimpleNamespace(callback_query=query), SimpleNamespace()
            )
        )
        assert query.edits[0][0] == bot.admin_handbook_section_text("runtime")
        assert query.edits[0][1]["reply_markup"] is not None
