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


def _run_immediate(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    coroutine.close()
    raise AssertionError("callback unexpectedly yielded I/O in no-I/O fixture")


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
    def test_freehub_downloader_primary_back_restores_emitting_parent(self):
        copy = {
            "freehub_enable_ai_chatbot": "AI chatbot",
            "freehub_utilities": "Utilities",
            "freehub_meta": "Meta",
            "freehub_caption": "Caption",
            "freehub_ideas": "Ideas",
            "freehub_prompts": "Prompts",
            "freehub_library": "Library",
            "freehub_publish_package": "Publish package",
            "freehub_notes_docs": "Notes / documents",
            "freehub_save_temp_media": "Save media",
            "freehub_voice_subdub_script": "Voice/SubDub script",
            "freehub_music_sfx_ideas": "Music ideas",
            "freehub_translation": "Translation",
            "freehub_video_downloader": "Download video from link",
            "main_menu": "Main menu",
            "video_label": "Video Studio",
            "free_tools_label": "Free Tools",
        }
        pending = {9002: {"pending_action": "video_downloader", "step": "await_link"}}
        freehub_pending = {}
        rendered = []

        class Query:
            def __init__(self, data, user_id):
                self.data = data
                self.from_user = SimpleNamespace(id=user_id)
                self.answers = []

            async def answer(self):
                self.answers.append(())

        def set_downloader_pending(user_id, step, **fields):
            pending[user_id] = {"pending_action": "video_downloader", "step": step, **fields}

        def clear_downloader_pending(user_id):
            return pending.pop(user_id, None) is not None

        async def safe_edit_or_send(_query, text, **kwargs):
            rendered.append((text, kwargs.get("reply_markup")))

        scope = {
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "public_hub_copy": lambda _lang: copy,
            "normalize_user_language": lambda lang: lang or "vi",
            "ui_text": lambda _lang, key: "Back" if key == "common.back" else "Main menu",
            "get_user_language": lambda _uid: "vi",
            "video_downloader_start_text": lambda _lang: "Paste a public video link",
            "set_video_route_session": lambda *_args: None,
            "set_video_downloader_pending": set_downloader_pending,
            "clear_video_downloader_pending": clear_downloader_pending,
            "clear_free_hub_pending": lambda uid: freehub_pending.pop(uid, None) is not None,
            "free_hub_main_text": lambda _lang: "Free Tools root fixture",
            "video_public_visible_menu_rows": lambda: [["video_downloader"], ["main_menu"]],
            "video_public_route_for_tool": lambda _tool: {"entry_callback": "vdownload|start"},
            "video_public_menu_label": lambda _tool, _lang: "Download video",
            "localized_public_back_keyboard": lambda _lang: "maintenance keyboard",
            "safe_edit_or_send": safe_edit_or_send,
            "FREE_HUB_ENABLED": True,
        }
        for name in (
            "build_2col_keyboard",
            "free_hub_main_keyboard",
            "main_video_keyboard",
            "video_downloader_start_keyboard",
            "video_downloader_choice_keyboard",
            "handle_video_downloader_callback",
            "handle_free_hub_callback",
        ):
            exec(compile(_source_function(name), f"bot.py:{name}", "exec"), scope)

        freehub_markup = scope["free_hub_main_keyboard"]("vi")
        freehub_buttons = [button for row in freehub_markup.inline_keyboard for button in row]
        entry = next(button for button in freehub_buttons if button.callback_data == "vdownload|start|freehub")
        self.assertIn(
            'CallbackQueryHandler(handle_video_downloader_callback, pattern=r"^vdownload\\|")',
            BOT_SOURCE,
        )
        self.assertIn(
            'CallbackQueryHandler(handle_free_hub_callback, pattern=r"^freehub\\|")',
            BOT_SOURCE,
        )

        actor = 9001
        start_query = Query(entry.callback_data, actor)
        scope_run = lambda coroutine: _run_immediate(coroutine)
        scope_run(scope["handle_video_downloader_callback"](
            SimpleNamespace(callback_query=start_query), SimpleNamespace()
        ))
        self.assertEqual([()], start_query.answers)
        self.assertEqual("await_link", pending[actor]["step"])

        start_markup = rendered[-1][1]
        start_buttons = [button for row in start_markup.inline_keyboard for button in row]
        primary_back = next(button for button in start_buttons if button.text.startswith("⬅"))
        self.assertEqual("freehub|main", primary_back.callback_data)
        self.assertEqual("menu|main_video", next(
            button.callback_data for button in start_buttons if button.callback_data == "menu|main_video"
        ))
        self.assertIn("menu|main", [button.callback_data for button in start_buttons])

        choice_buttons = [
            button for row in scope["video_downloader_choice_keyboard"]("vi", origin="freehub").inline_keyboard
            for button in row
        ]
        choice_back = next(button for button in choice_buttons if button.text.startswith("⬅"))
        self.assertEqual("freehub|main", choice_back.callback_data)

        back_query = Query(primary_back.callback_data, actor)
        scope_run(scope["handle_free_hub_callback"](
            SimpleNamespace(callback_query=back_query), SimpleNamespace(user_data={})
        ))
        self.assertEqual([()], back_query.answers)
        self.assertEqual("Free Tools root fixture", rendered[-1][0])
        self.assertEqual(
            [button.callback_data for button in freehub_buttons],
            [button.callback_data for row in rendered[-1][1].inline_keyboard for button in row],
        )
        self.assertNotIn(actor, pending)
        self.assertEqual({"pending_action": "video_downloader", "step": "await_link"}, pending[9002])

        video_markup = scope["main_video_keyboard"]("vi")
        video_buttons = [button for row in video_markup.inline_keyboard for button in row]
        video_entry = next(button for button in video_buttons if button.text == "Download video")
        self.assertEqual("vdownload|start", video_entry.callback_data)
        video_query = Query(video_entry.callback_data, 9003)
        scope_run(scope["handle_video_downloader_callback"](
            SimpleNamespace(callback_query=video_query), SimpleNamespace()
        ))
        video_start_buttons = [
            button for row in rendered[-1][1].inline_keyboard for button in row
        ]
        video_back = next(button for button in video_start_buttons if button.text.startswith("⬅"))
        self.assertEqual("menu|main_video", video_back.callback_data)

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
                _run_immediate(
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
                _run_immediate(
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
                consumed = _run_immediate(
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
