from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(
    encoding="utf-8"
)


def _function_source(name: str) -> str:
    starts = [
        position
        for marker in (f"def {name}(", f"async def {name}(")
        if (position := BOT_SOURCE.find(marker)) >= 0
    ]
    start = min(starts)
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


def test_scene3_tail_save_persists_selected_postproduction_addons() -> None:
    saved_hosts: list[dict] = []

    class Tail9:
        @staticmethod
        def normalize_state(state):
            return dict(state)

    namespace = {
        "deepcopy": deepcopy,
        "video_tail9": Tail9,
        "VIDEO_TAIL9_STATE_KEY": "video_tail9",
        "save_video_profile_studio_state": (
            lambda _context, host: saved_hosts.append(dict(host)) or dict(host)
        ),
    }
    exec(
        compile(
            "from __future__ import annotations\n"
            + _function_source("save_video_tail9_state"),
            "<product-video-scene3-addon-save>",
            "exec",
        ),
        namespace,
    )
    subtitles = {
        "enabled": True,
        "value": {
            "source": "auto",
            "translation": False,
            "target_language": "",
        },
    }
    tail = {
        "audio_config": {
            "subtitles": True,
            "volumes": {},
        },
        "addon_config": {
            "postprocessing": {
                "subtitles": subtitles,
            }
        },
    }

    namespace["save_video_tail9_state"](
        7126457028,
        object(),
        tail,
        "scene3",
        {"postproduction_addons": {}},
    )

    assert saved_hosts[-1]["postproduction_addons"]["subtitles"] == subtitles


def test_long_html_renderer_converts_oversize_html_before_chunking() -> None:
    calls: list[tuple[str, str, object]] = []

    class CallbackQuery:
        async def edit_message_text(self, *_args, **_kwargs):
            raise AssertionError("oversize HTML reached direct edit path")

    async def long_plain(_query, text, reply_markup=None):
        calls.append(("plain", str(text), reply_markup))
        return "plain-rendered"

    async def edit_oversize(*_args, **_kwargs):
        raise AssertionError("oversize HTML reached direct edit path")

    namespace = {
        "html_message_to_plain_text": (
            lambda text: str(text).replace("<code>", "").replace("</code>", "")
        ),
        "safe_edit_or_send_long_plain": long_plain,
        "safe_reply_long_plain": long_plain,
        "safe_reply_long_html": lambda *_args, **_kwargs: None,
        "split_telegram_html_text": lambda text: [str(text)],
        "safe_edit_query_message": edit_oversize,
        "safe_reply_text": lambda *_args, **_kwargs: None,
    }
    exec(
        compile(
            "from __future__ import annotations\n"
            + _function_source("safe_edit_or_send_long_html"),
            "<product-video-long-html-safe>",
            "exec",
        ),
        namespace,
    )
    oversized = "<code>" + ("Cảnh và chất lượng " * 250) + "</code>"

    result = asyncio.run(
        namespace["safe_edit_or_send_long_html"](
            CallbackQuery(),
            oversized,
            reply_markup="quality-keyboard",
        )
    )

    assert result == "plain-rendered"
    assert calls == [
        (
            "plain",
            oversized.replace("<code>", "").replace("</code>", ""),
            "quality-keyboard",
        )
    ]


def test_tail_callback_ack_timeout_is_best_effort() -> None:
    class TimedOutQuery:
        async def answer(self, *_args, **_kwargs):
            raise TimeoutError("telegram callback acknowledgement timed out")

    namespace: dict = {}
    exec(
        compile(
            "from __future__ import annotations\n"
            + _function_source("video_tail9_answer_best_effort"),
            "<product-video-callback-ack-timeout>",
            "exec",
        ),
        namespace,
    )

    result = asyncio.run(
        namespace["video_tail9_answer_best_effort"](TimedOutQuery())
    )

    assert result is None
