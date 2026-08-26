from __future__ import annotations

import asyncio
from pathlib import Path


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(
    encoding="utf-8"
)


def _function_source(name: str) -> str:
    start = BOT_SOURCE.index(f"async def {name}(")
    candidates = [
        position
        for marker in ("\ndef ", "\nasync def ")
        if (position := BOT_SOURCE.find(marker, start + 1)) >= 0
    ]
    end = min(candidates) if candidates else len(BOT_SOURCE)
    return BOT_SOURCE[start:end]


def test_long_html_renderer_replies_when_target_is_a_normal_message() -> None:
    calls: list[tuple[str, str]] = []

    class Message:
        async def reply_text(self, text, **_kwargs):
            calls.append(("reply", str(text)))
            return "replied"

    async def edit_only(*_args, **_kwargs):
        raise AssertionError("normal Message reached CallbackQuery edit renderer")

    async def reply_long(message, text, reply_markup=None):
        _ = reply_markup
        return await message.reply_text(text)

    namespace = {
        "split_telegram_html_text": lambda text: [str(text)],
        "safe_edit_query_message": edit_only,
        "safe_reply_long_html": reply_long,
        "safe_reply_text": lambda *_args, **_kwargs: None,
    }
    exec(
        compile(
            "from __future__ import annotations\n"
            + _function_source("safe_edit_or_send_long_html"),
            "<product-video-message-tail-render>",
            "exec",
        ),
        namespace,
    )

    result = asyncio.run(
        namespace["safe_edit_or_send_long_html"](
            Message(),
            "<b>Add-on video</b>",
            reply_markup="keyboard",
        )
    )

    assert result == "replied"
    assert calls == [("reply", "<b>Add-on video</b>")]


def test_long_html_renderer_keeps_callback_query_edit_path() -> None:
    calls: list[tuple[str, str]] = []

    class CallbackQuery:
        async def edit_message_text(self, text, **_kwargs):
            calls.append(("edit", str(text)))
            return "edited"

    async def edit_query(query, text, **_kwargs):
        return await query.edit_message_text(text)

    async def reply_only(*_args, **_kwargs):
        raise AssertionError("CallbackQuery reached normal Message reply renderer")

    namespace = {
        "split_telegram_html_text": lambda text: [str(text)],
        "safe_edit_query_message": edit_query,
        "safe_reply_long_html": reply_only,
        "safe_reply_text": lambda *_args, **_kwargs: None,
    }
    exec(
        compile(
            "from __future__ import annotations\n"
            + _function_source("safe_edit_or_send_long_html"),
            "<product-video-callback-tail-render>",
            "exec",
        ),
        namespace,
    )

    result = asyncio.run(
        namespace["safe_edit_or_send_long_html"](
            CallbackQuery(),
            "<b>Add-on video</b>",
            reply_markup="keyboard",
        )
    )

    assert result == "edited"
    assert calls == [("edit", "<b>Add-on video</b>")]
