"""Exercise emitted SubDub buttons with real routing/state code, without bot startup."""
import ast
import asyncio
import hashlib
import re
import time
import unittest
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace


SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def _function_code(name):
    start = re.search(rf"(?m)^(?:async )?def {re.escape(name)}\b", SOURCE)
    assert start, name
    boundary = re.search(r"(?m)^(?:async )?def |^class |^[A-Z][A-Z0-9_]*\s*=|^@", SOURCE[start.end():])
    end = start.end() + boundary.start() if boundary else len(SOURCE)
    return compile("from __future__ import annotations\n" + SOURCE[start.start():end], "bot.py:" + name, "exec")


class _Button:
    def __init__(self, text, callback_data=None, **kwargs):
        self.text, self.callback_data = text, callback_data


class _Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class _Query:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=81001)
        self.message = SimpleNamespace(chat_id=81001)
        self.answers, self.screens = [], []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


@lru_cache(maxsize=1)
def _constants():
    values = {}
    for match in re.finditer(r'(?m)^((?:VIDEO_SUBTITLE_MODE_|VIDEO_DUBBING_FLOW_|VIDEO_DUBBING_NO_SUBTITLE_|SUBDUB_PRODUCT_TYPE_)\w+)\s*=\s*("[^"\n]*")', SOURCE):
        values[match.group(1)] = ast.literal_eval(match.group(2))
    values["VIDEO_TRANSLATE_MODES"] = {v for k, v in values.items() if k.startswith("VIDEO_SUBTITLE_MODE_")}
    values["SUBDUB_PRODUCT_TYPES"] = {v for k, v in values.items() if k.startswith("SUBDUB_PRODUCT_TYPE_")}
    for name in ("SUBDUB_MANUAL_VOICE_FIELDS", "SUBDUB_AUTO_VOICE_FIELDS", "SUBDUB_VOICE_CONFIRMATION_FIELDS"):
        match = re.search(rf"(?ms)^{name} = frozenset\((\{{.*?\}})\)", SOURCE)
        assert match, name
        values[name] = frozenset(ast.literal_eval(match.group(1)))
    return values


@lru_cache(maxsize=1)
def _registration_code():
    registration = re.search(r'(?m)^\s*tg_app\.add_handler\(CallbackQueryHandler\(handle_video_dubbing_callback,.*$', SOURCE)
    assert registration
    return compile(registration.group(0).strip(), "bot.py:SubDub registration", "exec")


def _load_scope(public):
    copy = {
        "back": "⬅️ Back", "main": "Home", "voice_default_female": "Female",
        "voice_default_male": "Male", "saved_voice": "Saved voices", "voice_custom_create": "Create voice",
        "auto": "Subtitles", "translate": "Translate", "dub": "Dub", "combo": "Subtitles and dub", "menu": "SubDub",
    }
    scope = {
        "re": re, "time": time, "hashlib": hashlib, "USER_PENDING": {},
        "VIDEO_DUBBING_TTL_SECONDS": 3600,
        "InlineKeyboardButton": _Button, "InlineKeyboardMarkup": _Markup,
        "normalize_user_language": lambda lang: lang,
        "get_user_language": lambda uid: "vi", "ui_text": lambda *args: "Home",
        "SUBDUB_VOLUME_MIX_UI_ENABLED": True,
        "subdub_audio_mix_state_fields": lambda _state: {
            "keep_original_audio": False,
            "original_audio_volume_percent": 0,
            "dubbed_voice_volume_percent": 100,
        },
        "subdub_audio_mix_text": lambda _state, _lang: "Audio mix settings",
        "public_subdub_deep_copy": lambda lang: copy,
        "current_product_context": lambda uid: "showroom",
        "PRODUCT_CONTEXT_SHOWROOM": "showroom", "PRODUCT_CONTEXT_VIDEO_ADDON": "video_addon",
        "enter_product_context": lambda *args, **kwargs: None,
        "video_dubbing_custom_voice_public_locked": lambda uid: public,
        "video_dubbing_video_addon_session_ready": lambda uid: True,
        "subdub_auto_provider_capacity_ready": lambda: False,
        "voice_vault_page_size": lambda count: count,
        "user_voice_profile_count": lambda uid: 6,
        "user_voice_profile_rows": lambda uid, size, offset: [{}] * min(size, 6 - offset),
        "voice_profile_display_code": lambda page, index, size: page * size + index + 1,
        "video_dubbing_custom_voice_admin_test_text": lambda lang: "Saved voice library",
        "video_dubbing_voice_text": lambda *args: "Choose voice",
        "subtitle_plus_dub_voice_text": lambda *args: "Choose combo voice",
        "video_dubbing_language_text": lambda *args: "Choose language",
        "video_dubbing_language_keyboard": lambda *args: _Markup([]),
        "logger": SimpleNamespace(warning=lambda *args, **kwargs: None),
        # Navigation uses no acoustic input or provider. Bound only that external seam.
        "auto_multi_speaker": SimpleNamespace(
            bounded_multi_acoustic_evidence=lambda fields: {}, MULTI_ACOUSTIC_STATE_FIELDS=frozenset(),
        ),
        "auto_smart_multivoice": SimpleNamespace(AUTO_SMART_MULTIVOICE_LANE="auto_smart_multivoice"),
    }
    scope.update(_constants())

    async def render(query, text, **kwargs):
        query.screens.append((text, kwargs.get("reply_markup")))

    scope["safe_edit_or_send"] = render
    for name in (
        "build_2col_keyboard", "_short_pending_text", "_safe_int", "video_v6_keyboard",
        "normalize_video_translate_mode", "video_dubbing_pending_key", "get_video_dubbing_pending",
        "set_video_dubbing_pending", "_clear_subdub_smart_multivoice_markers", "reset_subdub_voice_selection",
        "_persist_subdub_voice_reset", "_clear_subdub_voice_for_navigation", "subdub_back_stack_for_entry",
        "subdub_expected_product_type_from_state", "subdub_product_type_from_mode", "subdub_expected_media_for_product",
        "subtitle_plus_dub_is_active", "subtitle_plus_dub_no_subtitle_subpath",
        "video_dubbing_voice_keyboard", "subtitle_plus_dub_voice_keyboard",
        "video_dubbing_custom_voice_guard_text", "video_dubbing_custom_voice_guard_keyboard",
        "video_dubbing_saved_voice_keyboard", "handle_video_dubbing_callback",
        "video_dubbing_missing_upload_recovery_text", "video_dubbing_missing_upload_recovery_keyboard",
        "video_dubbing_back_target", "video_dubbing_menu_keyboard",
        "subdub_audio_mix_available", "subdub_audio_mix_keyboard", "subdub_audio_layer_keyboard",
    ):
        exec(_function_code(name), scope)
    return scope


def _seed(scope, combo=False, origin="translation", direct=False):
    mode = "subtitle_plus_dub" if combo else "dub"
    state = {
        "pending_action": "video_dubbing", "created_at_ts": time.time(),
        "mode": mode, "video_processing_mode": mode, "requested_mode": mode,
        "active_flow": "subtitle_plus_dub" if combo else "dub_audio",
        "step": "choosing_voice" if combo else "voice", "origin": origin,
        "source_file_id": "fixture-video", "target_language": "Tiếng Việt",
        "subtitle_ref": "fixture-subtitle", "translated_subtitle_ref": "fixture-translation",
        "translated_subtitle_target_language": "Tiếng Việt", "translation_session_id": "fixture-session",
        "dub_source": "translated_subtitle", "unrelated_option": "preserved",
    }
    if direct:
        state["combo_subpath"] = scope["VIDEO_DUBBING_NO_SUBTITLE_DIRECT_DUB"]
    scope["USER_PENDING"][scope["video_dubbing_pending_key"](81001)] = state
    scope["USER_PENDING"]["video_dubbing_artifact:81001:subtitle"] = {"value": "cached-subtitle"}
    return dict(state)


def _dispatch(scope, query):
    # Execute the actual source registration; clicking a emitted button must reach its owner.
    routes = []
    runtime = dict(scope, tg_app=SimpleNamespace(add_handler=routes.append),
                   CallbackQueryHandler=lambda callback, pattern: (callback, re.compile(pattern)))
    exec(_registration_code(), runtime)
    callback, pattern = routes[0]
    assert pattern.search(query.data), query.data
    asyncio.run(callback(SimpleNamespace(callback_query=query), SimpleNamespace()))


def _back(markup):
    # The navigation row follows pagination; Previous Page is not the parent Back.
    return [button.callback_data for row in markup.inline_keyboard for button in row
            if button.text.startswith("⬅️")][-1]


class SubDubVoiceChildBackTests(unittest.TestCase):
    def test_audio_layer_back_returns_to_audio_mix_parent_via_registered_handler(self):
        scope = _load_scope(False)
        state = _seed(scope)
        layer = scope["subdub_audio_layer_keyboard"](state, "original", "vi")
        back = _back(layer)
        self.assertEqual(back, "videodub|audio_mix")

        query = _Query(back)
        _dispatch(scope, query)

        restored = scope["get_video_dubbing_pending"](81001)
        self.assertEqual(restored["step"], "audio_mix")
        self.assertEqual(query.screens[-1][0], "Audio mix settings")
        parent_callbacks = {
            button.callback_data
            for row in query.screens[-1][1].inline_keyboard
            for button in row
        }
        self.assertIn("videodub|audio_original", parent_callbacks)
        self.assertIn("videodub|audio_dub", parent_callbacks)
        self.assertEqual(len(query.answers), 1)

    def test_expired_child_back_recovers_to_subdub_menu_without_recreating_session(self):
        scope = _load_scope(False)
        _seed(scope)
        scope["USER_PENDING"][scope["video_dubbing_pending_key"](81001)]["created_at_ts"] = 0
        markup = scope["video_dubbing_saved_voice_keyboard"](81001, "vi")
        query = _Query(_back(markup))
        _dispatch(scope, query)
        callbacks = {b.callback_data for row in query.screens[-1][1].inline_keyboard for b in row}
        self.assertIn("videodub|type|dub", callbacks)
        self.assertIsNone(scope["get_video_dubbing_pending"](81001))
        self.assertEqual(len(query.answers), 1)

    def test_emitted_child_back_returns_voice_parent_and_preserves_source(self):
        # Wrong reuse of back_voice must fail: it jumps over the parent to Language.
        for combo in (False, True):
            actions = ("voice_saved", "voice_library") if combo else ("voice_saved", "voice_create", "voice_custom")
            for public in (False, True):
                for action in actions:
                    with self.subTest(combo=combo, public=public, action=action):
                        scope = _load_scope(public)
                        initial = _seed(scope, combo=combo, direct=combo)
                        query = _Query("videodub|" + action)
                        _dispatch(scope, query)
                        query.data = _back(query.screens[-1][1])
                        _dispatch(scope, query)
                        state = scope["get_video_dubbing_pending"](81001)
                        self.assertEqual(state["step"], "choosing_voice" if combo else "voice")
                        for key in ("mode", "origin", "source_file_id", "target_language", "subtitle_ref",
                                    "translated_subtitle_ref", "translation_session_id", "dub_source", "unrelated_option"):
                            self.assertEqual(state[key], initial[key], key)
                        self.assertEqual(scope["USER_PENDING"]["video_dubbing_artifact:81001:subtitle"]["value"], "cached-subtitle")
                        callbacks = {b.callback_data for row in query.screens[-1][1].inline_keyboard for b in row}
                        self.assertIn("videodub|voice|default_female", callbacks)
                        self.assertIn("videodub|voice|default_male", callbacks)
                        self.assertEqual(len(query.answers), 2)  # one per distinct click

    def test_saved_voice_pagination_emits_back_to_voice_parent(self):
        for page in (0, 1):
            with self.subTest(page=page):
                scope = _load_scope(False)
                _seed(scope)
                query = _Query(f"videodub|voice_profile_page|{page}")
                _dispatch(scope, query)
                query.data = _back(query.screens[-1][1])
                _dispatch(scope, query)
                self.assertEqual(scope["get_video_dubbing_pending"](81001)["step"], "voice")

    def test_main_voice_back_still_returns_language_for_original_origin(self):
        for origin in ("translation", "video", "video_addon"):
            for combo in (False, True):
                with self.subTest(origin=origin, combo=combo):
                    scope = _load_scope(False)
                    _seed(scope, combo=combo, origin=origin, direct=combo)
                    markup = scope["video_dubbing_voice_keyboard"]("vi", scope["get_video_dubbing_pending"](81001))
                    query = _Query(_back(markup))
                    _dispatch(scope, query)
                    state = scope["get_video_dubbing_pending"](81001)
                    self.assertEqual(state["step"], "language")
                    self.assertEqual(state["origin"], origin)
                    self.assertEqual(state["source_file_id"], "fixture-video")
                    self.assertEqual(len(query.answers), 1)
