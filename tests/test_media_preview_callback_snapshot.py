"""Stale media-library item buttons must not act on a newer per-user cache."""
import asyncio
import html
import inspect
from pathlib import Path
import re
import time
import uuid
from types import SimpleNamespace
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def _source(name):
    start = re.search(rf"(?m)^(?:async )?def {name}\(", SOURCE)
    if not start:
        raise AssertionError(f"missing production function: {name}")
    following = re.search(r"(?m)^(?:async )?def \w+\(", SOURCE[start.end():])
    end = start.end() + following.start() if following else len(SOURCE)
    return SOURCE[start.start():end]


class Button:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


class Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class Query:
    def __init__(self, data):
        self.data = data
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _registered_route(name, namespace):
    lines = re.findall(
        rf"(?m)^\s*tg_app\.add_handler\(CallbackQueryHandler\({name},.*$", SOURCE
    )
    if len(lines) != 1:
        raise AssertionError(f"expected one registered route for {name}, got {len(lines)}")
    routes = []
    namespace["tg_app"] = SimpleNamespace(add_handler=routes.append)
    namespace["CallbackQueryHandler"] = lambda callback, pattern: SimpleNamespace(
        callback=callback, pattern=re.compile(pattern)
    )
    exec(lines[0].strip(), namespace)
    return routes[0]


def _runtime():
    namespace = {
        "time": time,
        "uuid": uuid,
        "html": html,
        "re": re,
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "InlineKeyboardButton": Button,
        "InlineKeyboardMarkup": Markup,
        "PRODUCT_CONTEXT_SHOWROOM": "showroom",
        "PRODUCT_CONTEXT_VIDEO_ADDON": "video_addon",
        "PRODUCT_CONTEXTS": {"showroom", "video_addon"},
        "PRODUCT_CONTEXT_TTL_SECONDS": 3600,
        "MEDIA_PREVIEW_TTL_SECONDS": 600,
        "LAST_SFX_RESULTS": {},
        "LAST_MUSIC_RESULTS": {},
        "LAST_MEDIA_RESULTS": {},
        "SELECTED_SFX": {},
        "SELECTED_MUSIC": {},
        "SELECTED_MEDIA": {},
        "USER_PENDING": {},
        "music_ui_lang": lambda *_args, **_kwargs: "vi",
        "music_no_xu_text": lambda *_args: "Bot chưa trừ Xu.",
        "selected_media_license_warning": lambda *_args: "License fixture warning.",
        "get_video_music_context": lambda *_args: {},
        "send_audio_item_to_chat": lambda *_args, **_kwargs: None,
        "ui_text": lambda *_args: "Home",
    }
    def build_2col_keyboard(items, nav_main=False, lang="vi"):
        rows = []
        row = []
        for label, callback_data in items:
            row.append(Button(label, callback_data))
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        return Markup(rows)
    namespace["build_2col_keyboard"] = build_2col_keyboard
    for name in (
        "normalize_product_context",
        "product_context_key",
        "get_product_context_state",
        "current_product_context",
        "product_context_callback",
        "save_media_preview_results",
        "get_media_preview_item",
        "media_preview_keyboard",
        "selected_music_video_followup_keyboard",
        "select_media_preview",
        "handle_media_preview_callback",
        "save_pixabay_media_results",
        "get_pixabay_media_item",
        "pixabay_media_keyboard",
        "select_pixabay_media",
        "handle_pixabay_media_callback",
    ):
        exec(compile("from __future__ import annotations\n" + _source(name), f"bot.py:{name}", "exec"), namespace)

    calls = []

    async def capture_music(update, context, kind, index_text, *args, **kwargs):
        token = kwargs.get("callback_token")
        user_id = update.effective_user.id
        getter = namespace["get_media_preview_item"]
        if "callback_token" in inspect.signature(getter).parameters:
            item, error = getter(kind, user_id, index_text, callback_token=token)
        else:
            item, error = getter(kind, user_id, index_text)
        calls.append(("music", kind, index_text, token, error, item))

    async def capture_pixabay(update, context, index_text, *args, **kwargs):
        token = kwargs.get("callback_token")
        user_id = update.effective_user.id
        getter = namespace["get_pixabay_media_item"]
        if "callback_token" in inspect.signature(getter).parameters:
            item, error = getter(user_id, index_text, callback_token=token)
        else:
            item, error = getter(user_id, index_text)
        calls.append(("pixabay", index_text, token, error, item))

    for helper in (
        "send_media_preview_audio", "send_media_preview_source",
        "send_media_preview_license",
    ):
        namespace[helper] = capture_music
    namespace["send_pixabay_media_preview"] = capture_pixabay
    music_route = _registered_route("handle_media_preview_callback", namespace)
    pixabay_route = _registered_route("handle_pixabay_media_callback", namespace)
    return namespace, calls, music_route, pixabay_route


def _button(markup, callback_prefix):
    for row in markup.inline_keyboard:
        for button in row:
            if button.callback_data.startswith(callback_prefix):
                return button.callback_data
    raise AssertionError(f"button not found: {callback_prefix}")


def _music_markup(namespace, items, product_context="showroom", kind="music"):
    getter = namespace["media_preview_keyboard"]
    cache_name = "LAST_SFX_RESULTS" if kind == "sfx" else "LAST_MUSIC_RESULTS"
    token = (namespace[cache_name].get(901) or {}).get("callback_token", "")
    if "callback_token" in inspect.signature(getter).parameters:
        return getter(kind, items, "vi", product_context, callback_token=token)
    return getter(kind, items, "vi", product_context)


def _pixabay_markup(namespace, items):
    getter = namespace["pixabay_media_keyboard"]
    token = (namespace["LAST_MEDIA_RESULTS"].get(901) or {}).get("callback_token", "")
    if "callback_token" in inspect.signature(getter).parameters:
        return getter(items, "vi", callback_token=token)
    return getter(items, "vi")


def _dispatch(route, data, user_id=901):
    if not route.pattern.fullmatch(data):
        raise AssertionError(f"registered handler does not accept emitted callback: {data}")
    query = Query(data)
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(id=user_id),
    )
    class Bot:
        def __init__(self):
            self.sent = []

        async def send_message(self, **kwargs):
            self.sent.append(kwargs)

    asyncio.run(route.callback(update, SimpleNamespace(bot=Bot())))
    return query


class MediaPreviewCallbackSnapshotTests(unittest.TestCase):
    def test_music_buttons_include_the_cache_snapshot_token(self):
        namespace, _, _, _ = _runtime()
        item = {"title": "Track A", "preview_url": "https://example.invalid/a.mp3"}
        for kind, cache_name in (("music", "LAST_MUSIC_RESULTS"), ("sfx", "LAST_SFX_RESULTS")):
            with self.subTest(kind=kind):
                namespace["save_media_preview_results"](kind, 901, "first", [item])
                callback = _button(_music_markup(namespace, [item], kind=kind), f"select_{kind}|")
                parts = callback.split("|")
                self.assertEqual(3, len(parts), "item callback must carry its search snapshot token")
                self.assertEqual(namespace[cache_name][901]["callback_token"], parts[1])
                self.assertLessEqual(len(callback.encode("utf-8")), 64)

    def test_old_music_button_cannot_select_the_replacement_search_result(self):
        namespace, calls, route, _ = _runtime()
        first = [{"title": "Track A", "preview_url": "https://example.invalid/a.mp3"}]
        namespace["save_media_preview_results"]("music", 901, "first", first)
        old_button = _button(_music_markup(namespace, first), "select_music|")

        second = [{"title": "Track B", "preview_url": "https://example.invalid/b.mp3"}]
        namespace["save_media_preview_results"]("music", 901, "second", second)
        query = _dispatch(route, old_button)

        self.assertEqual([], calls, "stale control must not reach selection or preview helpers")
        self.assertNotIn(901, namespace["SELECTED_MUSIC"])
        self.assertEqual(1, len(query.answers))
        self.assertTrue(query.answers[0][1].get("show_alert"), "stale control should explain expiry")

    def test_old_sfx_button_cannot_preview_the_replacement_search_result(self):
        namespace, calls, route, _ = _runtime()
        first = [{"title": "SFX A", "preview_url": "https://example.invalid/a.mp3"}]
        namespace["save_media_preview_results"]("sfx", 901, "first", first)
        old_button = _button(_music_markup(namespace, first, kind="sfx"), "play_sfx|")

        second = [{"title": "SFX B", "preview_url": "https://example.invalid/b.mp3"}]
        namespace["save_media_preview_results"]("sfx", 901, "second", second)
        query = _dispatch(route, old_button)

        self.assertEqual([], calls, "stale control must not reach SFX preview")
        self.assertEqual(1, len(query.answers))
        self.assertTrue(query.answers[0][1].get("show_alert"))

    def test_current_music_button_reaches_registered_route_with_its_own_result(self):
        namespace, calls, route, _ = _runtime()
        item = {"title": "Track A", "preview_url": "https://example.invalid/a.mp3"}
        namespace["save_media_preview_results"]("music", 901, "first", [item])
        callback = _button(_music_markup(namespace, [item]), "select_music|")

        query = _dispatch(route, callback)

        self.assertEqual([], calls)
        self.assertEqual("Track A", namespace["SELECTED_MUSIC"][901]["title"])
        self.assertEqual(1, len(query.answers))

    def test_valid_music_preview_button_reaches_registered_helper_with_same_snapshot(self):
        namespace, calls, route, _ = _runtime()
        item = {"title": "Track A", "preview_url": "https://example.invalid/a.mp3"}
        namespace["save_media_preview_results"]("music", 901, "first", [item])
        token = namespace["LAST_MUSIC_RESULTS"][901]["callback_token"]
        callback = _button(_music_markup(namespace, [item]), "play_music|")

        query = _dispatch(route, callback)

        self.assertEqual([("music", "music", "1", token, "", item)], calls)
        self.assertEqual(1, len(query.answers))

    def test_legacy_tokenless_music_control_fails_closed(self):
        _, calls, route, _ = _runtime()
        query = _dispatch(route, "select_music|1")
        self.assertEqual([], calls)
        self.assertEqual(1, len(query.answers))
        self.assertTrue(query.answers[0][1].get("show_alert"))

    def test_direct_music_play_and_select_commands_keep_their_existing_behavior(self):
        namespace, _, _, _ = _runtime()
        item = {"title": "Track A", "preview_url": "https://example.invalid/a.mp3"}
        namespace["save_media_preview_results"]("music", 901, "first", [item])
        sent_audio = []

        async def capture_audio(_context, _chat_id, selected, _lang):
            sent_audio.append(selected)

        namespace["send_audio_item_to_chat"] = capture_audio
        for name in ("send_media_preview_audio", "cmd_play_music", "cmd_select_music"):
            exec(compile("from __future__ import annotations\n" + _source(name), f"bot.py:{name}", "exec"), namespace)

        class Bot:
            async def send_message(self, **_kwargs):
                return None

        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=901),
            effective_chat=SimpleNamespace(id=901),
            callback_query=None,
        )
        context = SimpleNamespace(args=["1"], bot=Bot())
        asyncio.run(namespace["cmd_play_music"](update, context))
        asyncio.run(namespace["cmd_select_music"](update, context))

        self.assertEqual("Track A", sent_audio[0]["title"])
        self.assertEqual("Track A", namespace["SELECTED_MUSIC"][901]["title"])

    def test_music_button_expires_after_product_context_changes(self):
        namespace, calls, route, _ = _runtime()
        item = [{"title": "Track A", "preview_url": "https://example.invalid/a.mp3"}]
        namespace["save_media_preview_results"]("music", 901, "first", item)
        button = _button(_music_markup(namespace, item), "select_music|")
        namespace["USER_PENDING"][namespace["product_context_key"](901)] = {
            "product_context": "video_addon", "created_at_ts": time.time(),
        }

        query = _dispatch(route, button)

        self.assertEqual([], calls, "a showroom result must not act inside the video-add-on context")
        self.assertEqual(1, len(query.answers))
        self.assertTrue(query.answers[0][1].get("show_alert"))

    def test_pixabay_buttons_include_the_cache_snapshot_token(self):
        namespace, _, _, _ = _runtime()
        items = [{"type": "image", "preview_url": "https://example.invalid/a.jpg", "source_url": "https://example.invalid"}]
        namespace["save_pixabay_media_results"](901, "first", items)
        markup = _pixabay_markup(namespace, items)
        callback = _button(markup, "select_media|")
        parts = callback.split("|")
        self.assertEqual(3, len(parts), "item callback must carry its search snapshot token")
        self.assertEqual(namespace["LAST_MEDIA_RESULTS"][901]["callback_token"], parts[1])
        self.assertLessEqual(len(callback.encode("utf-8")), 64)

    def test_current_pixabay_button_reaches_registered_route_with_its_own_result(self):
        namespace, calls, _, route = _runtime()
        item = {"type": "image", "tags": "A", "preview_url": "https://example.invalid/a.jpg", "source_url": "https://example.invalid/a"}
        namespace["save_pixabay_media_results"](901, "first", [item])
        callback = _button(_pixabay_markup(namespace, [item]), "select_media|")

        query = _dispatch(route, callback)

        self.assertEqual([], calls)
        self.assertEqual("A", namespace["SELECTED_MEDIA"][901]["tags"])
        self.assertEqual(1, len(query.answers))

    def test_valid_pixabay_preview_button_reaches_registered_helper_with_same_snapshot(self):
        namespace, calls, _, route = _runtime()
        item = {"type": "image", "tags": "A", "preview_url": "https://example.invalid/a.jpg", "source_url": "https://example.invalid/a"}
        namespace["save_pixabay_media_results"](901, "first", [item])
        token = namespace["LAST_MEDIA_RESULTS"][901]["callback_token"]
        callback = _button(_pixabay_markup(namespace, [item]), "play_media|")

        query = _dispatch(route, callback)

        self.assertEqual([("pixabay", "1", token, "", item)], calls)
        self.assertEqual(1, len(query.answers))

    def test_old_pixabay_button_cannot_read_the_replacement_search_result(self):
        namespace, calls, _, route = _runtime()
        first = [{"type": "image", "tags": "A", "preview_url": "https://example.invalid/a.jpg", "source_url": "https://example.invalid/a"}]
        namespace["save_pixabay_media_results"](901, "first", first)
        old_button = _button(_pixabay_markup(namespace, first), "play_media|")

        second = [{"type": "image", "tags": "B", "preview_url": "https://example.invalid/b.jpg", "source_url": "https://example.invalid/b"}]
        namespace["save_pixabay_media_results"](901, "second", second)
        query = _dispatch(route, old_button)

        self.assertEqual([], calls, "stale control must not reach media preview/select helpers")
        self.assertEqual(1, len(query.answers))
        self.assertTrue(query.answers[0][1].get("show_alert"), "stale control should explain expiry")

    def test_pixabay_button_expires_after_product_context_changes(self):
        namespace, calls, _, route = _runtime()
        items = [{"type": "image", "preview_url": "https://example.invalid/a.jpg", "source_url": "https://example.invalid/a"}]
        namespace["save_pixabay_media_results"](901, "first", items)
        button = _button(_pixabay_markup(namespace, items), "select_media|")
        namespace["USER_PENDING"][namespace["product_context_key"](901)] = {
            "product_context": "video_addon", "created_at_ts": time.time(),
        }

        query = _dispatch(route, button)

        self.assertEqual([], calls, "a showroom result must not act inside the video-add-on context")
        self.assertEqual(1, len(query.answers))
        self.assertTrue(query.answers[0][1].get("show_alert"))

    def test_valid_token_with_missing_result_number_fails_closed(self):
        namespace, calls, route, _ = _runtime()
        items = [{"title": "Track A", "preview_url": "https://example.invalid/a.mp3"}]
        namespace["save_media_preview_results"]("music", 901, "first", items)
        token = namespace["LAST_MUSIC_RESULTS"][901]["callback_token"]

        query = _dispatch(route, f"select_music|{token}|9")

        self.assertEqual([], calls)
        self.assertEqual(1, len(query.answers))
        self.assertTrue(query.answers[0][1].get("show_alert"))

    def test_media_button_from_another_user_is_rejected(self):
        namespace, calls, route, _ = _runtime()
        item = [{"title": "Track A", "preview_url": "https://example.invalid/a.mp3"}]
        namespace["save_media_preview_results"]("music", 901, "first", item)
        callback = _button(_music_markup(namespace, item), "select_music|")

        query = _dispatch(route, callback, user_id=902)

        self.assertEqual([], calls)
        self.assertEqual(1, len(query.answers))
        self.assertTrue(query.answers[0][1].get("show_alert"))

    def test_media_button_expires_after_ten_minutes(self):
        namespace, calls, route, _ = _runtime()
        clock = [1000.0]
        namespace["time"] = SimpleNamespace(time=lambda: clock[0])
        item = [{"title": "Track A", "preview_url": "https://example.invalid/a.mp3"}]
        namespace["save_media_preview_results"]("music", 901, "first", item)
        callback = _button(_music_markup(namespace, item), "select_music|")
        clock[0] += 601

        query = _dispatch(route, callback)

        self.assertEqual([], calls)
        self.assertEqual(1, len(query.answers))
        self.assertTrue(query.answers[0][1].get("show_alert"))

    def test_selected_video_followup_license_keeps_original_result_token(self):
        namespace, _, _, _ = _runtime()
        item = [{"title": "Track A", "preview_url": "https://example.invalid/a.mp3"}]
        namespace["save_media_preview_results"]("music", 901, "first", item)
        token = namespace["LAST_MUSIC_RESULTS"][901]["callback_token"]

        markup = namespace["selected_music_video_followup_keyboard"](
            "cinematic_ad", "1", "vi", token
        )

        self.assertEqual(f"license_music|{token}|1", _button(markup, "license_music|"))

    def test_selected_video_followup_license_reaches_registered_route_with_snapshot(self):
        namespace, calls, route, _ = _runtime()
        item = {"title": "Track A", "preview_url": "https://example.invalid/a.mp3"}
        namespace["save_media_preview_results"]("music", 901, "first", [item])
        token = namespace["LAST_MUSIC_RESULTS"][901]["callback_token"]
        markup = namespace["selected_music_video_followup_keyboard"](
            "cinematic_ad", "1", "vi", token
        )
        callback = _button(markup, "license_music|")

        query = _dispatch(route, callback)

        self.assertEqual([("music", "music", "1", token, "", item)], calls)
        self.assertEqual(1, len(query.answers))

    def test_stale_selected_video_followup_license_cannot_resolve_replacement_result(self):
        namespace, calls, route, _ = _runtime()
        first = {"title": "Track A", "preview_url": "https://example.invalid/a.mp3"}
        namespace["save_media_preview_results"]("music", 901, "first", [first])
        token = namespace["LAST_MUSIC_RESULTS"][901]["callback_token"]
        markup = namespace["selected_music_video_followup_keyboard"](
            "cinematic_ad", "1", "vi", token
        )
        callback = _button(markup, "license_music|")
        second = {"title": "Track B", "preview_url": "https://example.invalid/b.mp3"}
        namespace["save_media_preview_results"]("music", 901, "second", [second])

        query = _dispatch(route, callback)

        self.assertEqual([], calls)
        self.assertEqual(1, len(query.answers))
        self.assertTrue(query.answers[0][1].get("show_alert"))


if __name__ == "__main__":
    unittest.main()
