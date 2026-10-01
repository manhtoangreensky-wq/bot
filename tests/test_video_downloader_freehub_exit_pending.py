import asyncio
import re
import time
import unittest
from pathlib import Path
from types import SimpleNamespace


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def _source_function(name):
    start = re.search(rf"(?m)^(?:async )?def {re.escape(name)}\(", BOT_SOURCE)
    if not start:
        raise AssertionError(f"missing actual source function: {name}")
    following = re.search(r"(?m)^(?:async )?def [A-Za-z_]\w*\(", BOT_SOURCE[start.end():])
    end = start.end() + following.start() if following else len(BOT_SOURCE)
    return BOT_SOURCE[start.start():end]


class _Button:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class _DownloaderAdapter:
    def __init__(self):
        self.detect_calls = 0

    def detect_link(self, _url):
        self.detect_calls += 1
        return {"ok": False, "reason": "unsupported_platform"}


class _Message:
    def __init__(self, text=""):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class VideoDownloaderFreeHubExitTest(unittest.TestCase):
    def test_freehub_main_releases_downloader_input_before_next_text(self):
        events = []
        adapter = _DownloaderAdapter()
        scope = {
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "USER_PENDING": {},
            "time": time,
            "VIDEO_DOWNLOADER_PENDING_TTL_SECONDS": 600,
            "FREE_HUB_ENABLED": True,
            "public_hub_copy": lambda _lang: {},
            "normalize_user_language": lambda _lang: "vi",
            "get_user_language": lambda _uid: "vi",
            "localized_public_back_keyboard": lambda _lang: "maintenance keyboard",
            "set_video_route_session": lambda *_args: None,
            "free_hub_main_text": lambda _lang: "free hub main",
            "free_hub_main_keyboard": lambda _lang: "free hub keyboard",
            "video_downloader_start_text": lambda _lang: "paste a public link",
            "safe_edit_or_send": None,
        }

        async def safe_edit_or_send(_query, text, **kwargs):
            events.append((text, kwargs.get("reply_markup")))
            return "rendered"

        scope["safe_edit_or_send"] = safe_edit_or_send
        for name in (
            "free_hub_pending_key",
            "clear_free_hub_pending",
            "video_downloader_pending_key",
            "set_video_downloader_pending",
            "get_video_downloader_pending",
            "clear_video_downloader_pending",
            "video_downloader_start_keyboard",
            "handle_video_downloader_callback",
            "handle_free_hub_callback",
            "handle_video_downloader_pending_text",
        ):
            exec(compile(_source_function(name), f"bot.py:{name}", "exec"), scope)

        start_markup = scope["video_downloader_start_keyboard"]("vi")
        callbacks = [button.callback_data for row in start_markup.inline_keyboard for button in row]
        self.assertIn("freehub|main", callbacks)
        self.assertIn(
            'CallbackQueryHandler(handle_free_hub_callback, pattern=r"^freehub\\|")',
            BOT_SOURCE,
        )
        self.assertIn(
            'CallbackQueryHandler(handle_video_downloader_callback, pattern=r"^vdownload\\|")',
            BOT_SOURCE,
        )
        message_handler = _source_function("handle_message")
        self.assertRegex(
            message_handler,
            r"if await handle_video_downloader_pending_text\(update, context\):",
        )

        async def answer():
            return None

        scope["extract_first_http_url"] = lambda _text: None
        scope["video_downloader_guard_text"] = lambda *_args: "unsupported link"
        for freehub_enabled in (True, False):
            with self.subTest(freehub_enabled=freehub_enabled):
                scope["FREE_HUB_ENABLED"] = freehub_enabled
                adapter = _DownloaderAdapter()
                scope["video_downloader_provider"] = lambda: adapter
                uid = 834201 + int(freehub_enabled)
                start_query = SimpleNamespace(
                    data="vdownload|start",
                    from_user=SimpleNamespace(id=uid),
                    answer=answer,
                )
                asyncio.run(
                    scope["handle_video_downloader_callback"](
                        SimpleNamespace(callback_query=start_query), SimpleNamespace()
                    )
                )
                self.assertEqual("await_link", scope["get_video_downloader_pending"](uid)["step"])

                freehub_query = SimpleNamespace(
                    data="freehub|main",
                    from_user=SimpleNamespace(id=uid),
                    answer=answer,
                )
                asyncio.run(
                    scope["handle_free_hub_callback"](
                        SimpleNamespace(callback_query=freehub_query), SimpleNamespace()
                    )
                )
                if freehub_enabled:
                    self.assertEqual(("free hub main", "free hub keyboard"), events[-1])
                else:
                    self.assertIn("đang bảo trì", events[-1][0])
                    self.assertEqual("maintenance keyboard", events[-1][1])

                message = _Message("ordinary Free Tools text")
                consumed = asyncio.run(
                    scope["handle_video_downloader_pending_text"](
                        SimpleNamespace(
                            message=message,
                            effective_user=SimpleNamespace(id=uid),
                            effective_chat=SimpleNamespace(id=uid),
                        ),
                        SimpleNamespace(),
                    )
                )
                self.assertEqual(
                    (False, 0),
                    (consumed, adapter.detect_calls),
                    "after leaving for Free Tools, plain text must be unconsumed and never inspected as a URL",
                )


if __name__ == "__main__":
    unittest.main()
