"""Voice settings prompt Back through actual buttons, registered handler and state."""
import asyncio
from collections import defaultdict
from copy import deepcopy
from functools import cache
from pathlib import Path
import re
import time
from types import SimpleNamespace

import pytest


SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


@cache
def _source(name):
    start = re.search(rf"(?m)^(?:async )?def {name}\(", SOURCE)
    assert start, name
    following = re.search(r"(?m)^(?:async )?def \w+\(", SOURCE[start.end():])
    end = start.end() + following.start() if following else len(SOURCE)
    return SOURCE[start.start():end]


class Button:
    def __init__(self, text, callback_data=None):
        self.text, self.callback_data = text, callback_data


class Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class Message:
    def __init__(self, text=""):
        self.text, self.replies = text, []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs.get("reply_markup")))


class Query:
    def __init__(self, data):
        self.data, self.message, self.answers = data, Message(), []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _runtime(source_kind, product_context):
    ns = {
        "Update": object, "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "InlineKeyboardButton": Button, "InlineKeyboardMarkup": Markup,
        "time": time, "re": re, "USER_PENDING": {},
        "PRODUCT_CONTEXT_SHOWROOM": "showroom", "PRODUCT_CONTEXT_VIDEO_ADDON": "video_addon",
        "PRODUCT_CONTEXTS": {"showroom", "video_addon"},
        "QUICK_MEDIA_PENDING_TTL_SECONDS": 600, "TREND_WORKFLOW_TTL_SECONDS": 600,
        "VOICE_TTS_DEFAULT_SPEED": "1.0", "VOICE_TTS_DEFAULT_VOLUME_PERCENT": 100,
        "VOICE_TTS_MIN_SPEED": .5, "VOICE_TTS_MAX_SPEED": 2,
        "VOICE_TTS_MIN_VOLUME_PERCENT": 0, "VOICE_TTS_MAX_VOLUME_PERCENT": 100,
        "LEGACY_CANONICAL_CALLBACK_REDIRECTS": {},
        "_short_pending_text": lambda value, limit: str(value)[:limit],
        "music_ui_lang": lambda *_args, **_kwargs: "vi",
        "_audio_label": lambda _lang, key: key, "_audio_copy": lambda _lang, key: key,
        "enter_product_context": lambda *_args, **_kwargs: None,
        "voice_tts_speed_input_text": lambda _lang: "Enter speed",
        "voice_tts_volume_input_text": lambda _lang: "Enter volume",
        "voice_tts_speed_invalid_text": lambda _lang: "Invalid speed",
        "voice_tts_volume_invalid_text": lambda _lang: "Invalid volume",
        "get_user_voice_profile": lambda _uid, pid: {"id": pid, "display_name": "Saved voice"},
        "default_voice_confirm_text": lambda *_args: "previous:default",
        "default_voice_confirm_keyboard": lambda *_args: Markup([]),
        "saved_voice_tts_confirm_text": lambda *_args: "previous:saved",
        "saved_voice_tts_confirm_keyboard": lambda *_args: Markup([]),
        "custom_voice_usage_price_xu": lambda _text: 0,
        "voice_tts_ready_text": lambda *_args: "previous:standalone",
        "voice_tts_choice_keyboard": lambda *_args: Markup([]),
    }

    def forbid(*_args, **_kwargs):
        raise AssertionError("Generation/provider/price-summary action is forbidden in Back tests")

    for name in ("voice_tts_create_from_settings", "voice_tts_generate_after_confirm", "show_voice_tts_price_summary"):
        ns[name] = forbid
    for name in (
        "_safe_int", "normalize_product_context", "infer_product_context_from_callback", "parse_product_context_callback",
        "product_context_callback", "music_guided_pending_key", "music_guided_result_key",
        "set_music_guided_pending", "get_music_guided_pending", "clear_music_guided_pending",
        "save_music_guided_result", "get_music_guided_result", "default_voice_gender_from_kind",
        "parse_voice_tts_speed_input", "parse_voice_tts_volume_input", "voice_tts_speed_value",
        "voice_tts_volume_percent", "voice_tts_speed_display", "voice_tts_settings_state",
        "voice_tts_settings_text", "voice_tts_settings_keyboard", "show_voice_tts_settings_screen",
        "voice_tts_return_previous_screen", "handle_music_quick_callback", "handle_music_guided_pending_text",
    ):
        exec(compile("from __future__ import annotations\n" + _source(name), f"bot.py:{name}", "exec"), ns)
    ns["save_music_guided_result"](901, {
        "voice_text": "Keep this spoken text", "tts_speed": "1.2", "voice_tts_volume_percent": 80,
        "voice_tts_settings_source": source_kind, "voice_tts_settings_gender": "female",
        "voice_tts_settings_profile_id": 23, "voice_tts_settings_voice_id": "keep-voice",
        "voice_tts_settings_product_context": product_context,
    })
    routes = []
    ns.update(tg_app=SimpleNamespace(add_handler=routes.append),
              CallbackQueryHandler=lambda callback, pattern: (callback, re.compile(pattern)))
    registrations = re.findall(
        r"(?m)^\s*tg_app\.add_handler\(CallbackQueryHandler\(handle_music_quick_callback,.*$", SOURCE
    )
    assert len(registrations) == 1
    exec(registrations[0].strip(), ns)
    return ns, routes[0]


def _callback(markup, action):
    return next(button.callback_data for row in markup.inline_keyboard for button in row
                if str(button.callback_data).endswith("|" + action))


def _click(route, data):
    handler, pattern = route
    assert pattern.search(data)
    query = Query(data)
    user = SimpleNamespace(id=901)
    asyncio.run(handler(SimpleNamespace(callback_query=query, effective_user=user), SimpleNamespace()))
    assert query.answers == [((), {})]
    return query


@pytest.mark.parametrize("source_kind", ["default", "saved", "standalone"])
@pytest.mark.parametrize("product_context", ["showroom", "video_addon"])
@pytest.mark.parametrize("setting", ["speed", "volume"])
def test_prompt_back_returns_settings_releases_input_and_keeps_voice_options(source_kind, product_context, setting):
    ns, route = _runtime(source_kind, product_context)
    before = deepcopy(ns["get_music_guided_result"](901))
    settings_keyboard = ns["voice_tts_settings_keyboard"]("vi", product_context)
    prompt = _click(route, _callback(settings_keyboard, f"voice_tts_set_{setting}"))
    assert ns["get_music_guided_pending"](901)["pending_action"] == f"voice_tts_{setting}_input"
    back = _click(route, _callback(prompt.message.replies[-1][1], "voice_tts_settings_back"))

    assert ns["get_music_guided_pending"](901) is None
    text, markup = back.message.replies[-1]
    assert "settings_title" in text
    assert _callback(markup, "voice_tts_settings_back") == ns["product_context_callback"]("music_quick", product_context, "voice_tts_settings_back")
    after = ns["get_music_guided_result"](901)
    for key in before.keys() - {"created_at_ts"}:
        assert after[key] == before[key]
    ordinary = Message("ordinary text after Back")
    consumed = asyncio.run(ns["handle_music_guided_pending_text"](
        SimpleNamespace(message=ordinary, effective_user=SimpleNamespace(id=901)), SimpleNamespace()
    ))
    assert consumed is False and ordinary.replies == []


@pytest.mark.parametrize("source_kind", ["default", "saved", "standalone"])
@pytest.mark.parametrize("product_context", ["showroom", "video_addon"])
def test_settings_parent_back_keeps_previous_source_screen(source_kind, product_context):
    ns, route = _runtime(source_kind, product_context)
    markup = ns["voice_tts_settings_keyboard"]("vi", product_context)
    query = _click(route, _callback(markup, "voice_tts_settings_back"))
    assert query.message.replies[-1][0] == f"previous:{source_kind}"


def test_old_settings_back_does_not_clear_other_pending_action_or_context():
    ns, route = _runtime("default", "showroom")
    markup = ns["voice_tts_settings_keyboard"]("vi", "showroom")
    for action, ctx in (("music_prompt_input", "showroom"), ("voice_tts_speed_input", "video_addon")):
        ns["set_music_guided_pending"](901, action, product_context=ctx)
        before = deepcopy(ns["get_music_guided_pending"](901))
        _click(route, _callback(markup, "voice_tts_settings_back"))
        assert ns["get_music_guided_pending"](901) == before
