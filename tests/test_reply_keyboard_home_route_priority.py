import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"
HOME_LABELS = ("🏠 TOAN AAS MENU", "🛸 MENU DỊCH VỤ TOAN AAS")


def _load_handle_message(source, events):
    start = source.index("@telegram_message_idempotent\nasync def handle_message(")
    end = source.index("\n# ─── FASTAPI + LIFESPAN", start)
    function_source = source[start:end]

    async def no_slash_reset(_update, _context, _text):
        return False

    async def open_home(_update, _context):
        events.append("home")
        return "home"

    async def reply_text(_text, **_kwargs):
        events.append("autopost_reply")
        return "autopost"

    namespace = {
        "telegram_message_idempotent": lambda function: function,
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "handle_state_reset_slash_command": no_slash_reset,
        "cmd_start": open_home,
        "save_content_input": lambda *_args, **_kwargs: events.append("save_content_input") or 1,
        "get_effective_brand_profile": lambda *_args, **_kwargs: {},
        "match_affiliate_for_post": lambda *_args, **_kwargs: {"primary_affiliate": None},
        "generate_single_post_draft": lambda *_args, **_kwargs: {},
        "autopost_draft_view_text": lambda *_args, **_kwargs: "draft",
        "autopost_draft_keyboard": lambda *_args, **_kwargs: None,
    }
    exec(compile(function_source, "bot.py:handle_message", "exec"), namespace)
    namespace["_reply_text"] = reply_text
    return namespace["handle_message"]


@pytest.mark.parametrize("label", HOME_LABELS)
def test_home_reply_keyboard_preempts_pending_autopost_content(label):
    source = BOT_PATH.read_text(encoding="utf-8")
    assert 'ReplyKeyboardMarkup([[KeyboardButton("🏠 TOAN AAS MENU")' in source
    assert "MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)" in source
    events = []
    handler = _load_handle_message(source, events)

    class Message:
        text = label

        async def reply_text(self, text, **kwargs):
            return await handler_namespace["_reply_text"](text, **kwargs)

    handler_namespace = handler.__globals__
    update = SimpleNamespace(
        message=Message(),
        effective_user=SimpleNamespace(id=7001),
    )
    context = SimpleNamespace(user_data={"awaiting_content_input_type": "text"})

    result = asyncio.run(handler(update, context))

    assert result == "home"
    assert events == ["home"]
    assert context.user_data["awaiting_content_input_type"] == "text"


def test_regular_text_still_completes_pending_autopost_content():
    source = BOT_PATH.read_text(encoding="utf-8")
    events = []
    handler = _load_handle_message(source, events)

    class Message:
        text = "draft content"

        async def reply_text(self, text, **kwargs):
            return await handler_namespace["_reply_text"](text, **kwargs)

    handler_namespace = handler.__globals__
    update = SimpleNamespace(
        message=Message(),
        effective_user=SimpleNamespace(id=7001),
    )
    context = SimpleNamespace(user_data={"awaiting_content_input_type": "text"})

    result = asyncio.run(handler(update, context))

    assert result == "autopost"
    assert events == ["save_content_input", "autopost_reply"]
    assert "awaiting_content_input_type" not in context.user_data
