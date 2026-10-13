import ast
import asyncio
import html
import re
import unittest
from pathlib import Path
from types import SimpleNamespace


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"
BOT_SOURCE = BOT_PATH.read_text(encoding="utf-8")


def _function_source(name):
    start = re.search(rf"(?m)^(?:async\s+)?def {re.escape(name)}\s*\(", BOT_SOURCE)
    assert start is not None, f"missing source function: {name}"
    boundary = re.search(
        r"(?m)^(?:async\s+)?def\s+\w+\s*\(|^class\s+\w+|^[A-Z][A-Z0-9_]*\s*=",
        BOT_SOURCE[start.end():],
    )
    end = start.end() + boundary.start() if boundary else len(BOT_SOURCE)
    return BOT_SOURCE[start.start():end].rstrip()


class _Button:
    def __init__(self, text, callback_data=None, url=None):
        self.text = text
        self.callback_data = callback_data
        self.url = url


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class _Query:
    def __init__(self, user_id, data):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id, username="admin", first_name="Admin")
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _load_functions(*names, **dependencies):
    namespace = {"SimpleNamespace": SimpleNamespace, **dependencies}
    source = "from __future__ import annotations\n\n" + "\n\n".join(
        _function_source(name) for name in names
    )
    exec(compile(source, f"{BOT_PATH}:extracted_callbacks", "exec"), namespace)
    return namespace


def _run_no_io(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as completed:
        return completed.value
    coroutine.close()
    raise AssertionError("callback fixture unexpectedly yielded I/O")


def _main_menu_dependencies(is_admin, effects):
    copy = {
        key: key
        for key in (
            "free_tools_label", "video_label", "image_label", "translation_label",
            "audio_studio_label", "account_label", "topup_pricing_label", "autopost_label",
            "chat_pro_label", "notes_docs_label", "support", "guide_label", "feedback_label",
            "center", "change_language", "admin_label",
            "support_admin", "support_ticket", "support_my_tickets", "support_premium",
            "support_custom_bot", "support_consult", "support_auto", "main_menu",
        )
    }

    def record(name):
        return lambda *_args, **_kwargs: effects.append(name)

    async def safe_edit(query, text, **kwargs):
        query.edits.append((text, kwargs))

    return {
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "normalize_user_language": lambda lang: lang,
        "public_hub_copy": lambda _lang: copy,
        "product_context_callback": lambda *_args: "music_quick|root",
        "PRODUCT_CONTEXT_SHOWROOM": "showroom",
        "TOAN_AAS_COMMUNITY_URL": "https://community.toanaas.vn",
        "public_chat_runtime": SimpleNamespace(CHAT_PRO_RATE_LABEL="test rate"),
        "VIDEO_TAIL9_TEXT_INPUT_KEY": "video_tail_pending",
        "DOC_TOOL_MENU_ACTIONS": set(),
        "is_admin_user": lambda _uid: is_admin,
        "get_user_language": lambda _uid: "vi",
        "clear_broadcast_lite_pending": record("broadcast"),
        "clear_translation_menu_pending": record("translation_menu"),
        "clear_translation_session": record("translation_session"),
        "clear_media_creator_pending_states": record("media_creator"),
        "clear_support_ticket_pending": record("support_ticket"),
        "clear_finance_compliance_pending": record("finance_compliance"),
        "clear_internal_archive_pending": record("internal_archive"),
        "clear_doc_tool_pending": record("doc_tool"),
        "clear_storage_addon_pending": record("storage_addon"),
        "clear_memory_guided_pending": record("memory_guided"),
        "clear_music_guided_pending": record("music_guided"),
        "clear_pending_admin_tool_test": record("admin_tool_test"),
        "_local_video_planning_clear_pending": lambda _context: None,
        "safe_edit_query_message": safe_edit,
        "menu_text_main_guide_i18n": lambda _lang: "existing screen:main_guide",
        "main_guide_keyboard": lambda _lang: "existing keyboard:main_guide",
        "human_support_text": lambda _lang: "existing screen:support",
        "human_support_keyboard": lambda _lang: "existing keyboard:support",
        "support_read_origin_keyboard": lambda markup, *_args, **_kwargs: markup,
        "support_form_origin_keyboard": lambda markup, *_args, **_kwargs: markup,
        "localized_menu_content": lambda action, _admin, _lang, _uid: (
            f"existing screen:{action}", f"existing keyboard:{action}"
        ),
    }


def _registered_menu_pattern():
    match = re.search(
        r"CallbackQueryHandler\(\s*handle_menu_callback\s*,\s*pattern\s*=\s*(r?['\"][^'\"]+['\"])\s*\)",
        BOT_SOURCE,
    )
    assert match is not None, "handle_menu_callback must be registered"
    return re.compile(ast.literal_eval(match.group(1)))


def _registered_pattern(handler_name):
    match = re.search(
        rf"CallbackQueryHandler\(\s*{re.escape(handler_name)}\s*,\s*pattern\s*=\s*(r?['\"][^'\"]+['\"])\s*\)",
        BOT_SOURCE,
    )
    assert match is not None, f"{handler_name} must be registered"
    return re.compile(ast.literal_eval(match.group(1)))


class AdminRootMenuCallbackSingleAckTests(unittest.TestCase):
    def test_public_and_admin_root_menus_keep_registered_routes_across_all_locales(self):
        from services.pricing_guide_content import public_hub_copy

        locale_start = re.search(r"(?m)^USER_LANGUAGE_ORDER\s*=", BOT_SOURCE)
        self.assertIsNotNone(locale_start)
        locale_end_match = re.search(
            r"(?m)^[A-Z][A-Z0-9_]*\s*=", BOT_SOURCE[locale_start.end():]
        )
        self.assertIsNotNone(locale_end_match)
        locale_end = locale_start.end() + locale_end_match.start()
        locale_scope = {}
        exec(
            compile(BOT_SOURCE[locale_start.start():locale_end], "bot.py:USER_LANGUAGE_ORDER", "exec"),
            locale_scope,
        )

        handlers = {
            "freehub|": "handle_free_hub_callback",
            "menu|": "handle_menu_callback",
            "music_quick|": "handle_music_quick_callback",
            "pricing|": "handle_pricing_callback",
            "feedback|": "handle_feedback_callback",
            "back_lang": "handle_language_callback",
        }
        callback_patterns = {
            prefix: _registered_pattern(handler)
            for prefix, handler in handlers.items()
        }
        copy_keys = (
            "free_tools_label", "video_label", "image_label", "translation_label",
            "audio_studio_label", "account_label", "topup_pricing_label",
            "autopost_label", "chat_pro_label", "notes_docs_label", "support",
            "guide_label", "feedback_label", "center", "change_language", "admin_label",
        )

        for is_admin in (False, True):
            baseline_callbacks = None
            for locale in locale_scope["USER_LANGUAGE_ORDER"]:
                with self.subTest(is_admin=is_admin, locale=locale):
                    dependencies = _main_menu_dependencies(is_admin, [])
                    dependencies["public_hub_copy"] = public_hub_copy
                    markup = _load_functions(
                        "localized_main_menu_keyboard", **dependencies
                    )["localized_main_menu_keyboard"](is_admin, locale)
                    buttons = [button for row in markup.inline_keyboard for button in row]
                    copy = public_hub_copy(locale)

                    for key in copy_keys:
                        self.assertTrue(copy.get(key, "").strip(), key)
                        self.assertNotEqual(copy[key], key)
                    self.assertTrue(all(button.text.strip() for button in buttons))

                    callbacks = [button.callback_data for button in buttons if button.callback_data]
                    if baseline_callbacks is None:
                        baseline_callbacks = callbacks
                    else:
                        self.assertEqual(callbacks, baseline_callbacks)

                    for callback_data in callbacks:
                        self.assertLessEqual(len(callback_data.encode("utf-8")), 64)
                        matching = next(
                            (pattern for prefix, pattern in callback_patterns.items()
                             if callback_data.startswith(prefix)),
                            None,
                        )
                        self.assertIsNotNone(matching, callback_data)
                        self.assertRegex(callback_data, matching)

    def test_public_main_menu_small_flow_callbacks_match_their_registered_handlers(self):
        dependencies = _main_menu_dependencies(False, [])
        namespace = _load_functions("localized_main_menu_keyboard", **dependencies)
        markup = namespace["localized_main_menu_keyboard"](False, "vi")
        self.assertEqual([len(row) for row in markup.inline_keyboard], [1, 2, 2, 2, 2, 2, 2, 2])
        self.assertEqual(markup.inline_keyboard[0][0].callback_data, "freehub|main")
        self.assertEqual(
            [button.callback_data for button in markup.inline_keyboard[4]],
            ["menu|autopost", "menu|chat_pro"],
        )
        self.assertEqual(
            [button.callback_data for button in markup.inline_keyboard[7]],
            [None, "back_lang"],
        )
        emitted = {
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.callback_data
        }
        safe_small_flow_routes = {
            "freehub|main": "handle_free_hub_callback",
            "pricing|main": "handle_pricing_callback",
            "back_lang": "handle_language_callback",
            "feedback|start": "handle_feedback_callback",
            "menu|main_video": "handle_menu_callback",
            "menu|main_image": "handle_menu_callback",
            "menu|main_profile": "handle_menu_callback",
            "menu|main_memory": "handle_menu_callback",
            "menu|support": "handle_menu_callback",
            "menu|main_guide": "handle_menu_callback",
        }
        self.assertTrue(set(safe_small_flow_routes) <= emitted)
        for callback, handler_name in safe_small_flow_routes.items():
            with self.subTest(callback=callback):
                self.assertRegex(callback, _registered_pattern(handler_name))

    def test_public_root_language_picker_back_restores_exact_main_menu_without_preference_write(self):
        user_id = 991181
        effects = []
        dependencies = _main_menu_dependencies(False, effects)
        copy = {
            **dependencies["public_hub_copy"]("vi"),
            "back": "Back",
            "main_menu": "Main menu",
            "language_picker_title": "Language",
            "language_picker_intro": "Choose a language",
        }
        dependencies.update({
            "public_hub_copy": lambda _lang: copy,
            "_TelegramInlineKeyboardMarkup": _Markup,
            "USER_LANGUAGE_ORDER": ("vi", "en"),
            "USER_LANGUAGE_LABELS": {"vi": "Vietnamese", "en": "English"},
            "USER_LANGUAGE_FLAGS": {"vi": "🇻🇳", "en": "🇬🇧"},
            "set_user_language": lambda uid, lang: effects.append(("set", uid, lang)),
            "record_usage_event": lambda *args, **kwargs: effects.append(("usage", args, kwargs)),
            "user_selected_vietnamese_initially": lambda _uid: False,
            "enqueue_broadcast_first_start_safe": lambda uid: effects.append(("broadcast", uid)),
            "localized_start_menu_text": lambda _uid, lang: f"main-{lang}",
        })
        namespace = _load_functions(
            "localized_main_menu_keyboard",
            "language_choice_text",
            "language_choice_keyboard",
            **dependencies,
        )
        root_markup = namespace["localized_main_menu_keyboard"](False, "vi")
        root_callbacks = [
            button.callback_data
            for row in root_markup.inline_keyboard
            for button in row
            if button.callback_data
        ]
        self.assertIn("back_lang", root_callbacks)

        handler_namespace = _load_functions(
            "handle_language_callback",
            language_choice_text=namespace["language_choice_text"],
            language_choice_keyboard=namespace["language_choice_keyboard"],
            localized_main_menu_keyboard=namespace["localized_main_menu_keyboard"],
            **dependencies,
        )
        route_pattern = _registered_pattern("handle_language_callback")

        def dispatch(callback_data):
            self.assertRegex(callback_data, route_pattern)
            query = _Query(user_id, callback_data)
            asyncio.run(handler_namespace["handle_language_callback"](
                SimpleNamespace(callback_query=query), SimpleNamespace(),
            ))
            self.assertEqual(query.answers, [((), {})])
            self.assertEqual(len(query.edits), 1)
            return query

        picker_screen = dispatch("back_lang")
        picker_markup = picker_screen.edits[0][1]["reply_markup"]
        picker_callbacks = [
            button.callback_data
            for row in picker_markup.inline_keyboard
            for button in row
            if button.callback_data
        ]
        self.assertIn("lang|vi", picker_callbacks)
        self.assertIn("lang|en", picker_callbacks)
        self.assertIn("menu|main", picker_callbacks)
        back_callback = next(
            button.callback_data
            for row in picker_markup.inline_keyboard
            for button in row
            if button.text.startswith("⬅")
        )

        returned = dispatch(back_callback)
        self.assertEqual(returned.edits[0][0], "main-vi")
        returned_markup = returned.edits[0][1]["reply_markup"]
        returned_callbacks = [
            button.callback_data
            for row in returned_markup.inline_keyboard
            for button in row
            if button.callback_data
        ]
        self.assertEqual(returned_callbacks, root_callbacks)
        self.assertEqual(effects, [])

    def test_public_root_language_picker_emitted_locales_update_only_fixture_and_restore_main(self):
        constants = {}
        for name in ("USER_LANGUAGE_LABELS", "USER_LANGUAGE_FLAGS", "USER_LANGUAGE_ORDER"):
            start = re.search(rf"(?m)^{name}\s*=", BOT_SOURCE)
            self.assertIsNotNone(start, name)
            following = re.search(r"(?m)^[A-Z][A-Z0-9_]*\s*=", BOT_SOURCE[start.end():])
            end = start.end() + following.start() if following else len(BOT_SOURCE)
            exec(compile(BOT_SOURCE[start.start():end], f"bot.py:{name}", "exec"), constants)

        normalizer = _load_functions("normalize_user_language", **constants)["normalize_user_language"]
        picker_copy = {
            "language_picker_title": "Choose language",
            "language_picker_intro": "Choose the language for TOAN AAS.",
            "back": "Back",
            "main_menu": "Main menu",
        }
        picker_namespace = _load_functions(
            "language_choice_text",
            "language_choice_keyboard",
            normalize_user_language=normalizer,
            public_hub_copy=lambda _lang: picker_copy,
            USER_LANGUAGE_ORDER=constants["USER_LANGUAGE_ORDER"],
            USER_LANGUAGE_LABELS=constants["USER_LANGUAGE_LABELS"],
            USER_LANGUAGE_FLAGS=constants["USER_LANGUAGE_FLAGS"],
            InlineKeyboardButton=_Button,
            _TelegramInlineKeyboardMarkup=_Markup,
        )

        user_id = 991182
        stored = {"lang": "vi"}
        effects = []
        async def safe_edit(query, text, **kwargs):
            query.edits.append((text, kwargs))

        def set_language(uid, lang):
            effects.append(("set", uid, lang))
            stored["lang"] = lang
            return lang

        handler_namespace = _load_functions(
            "handle_language_callback",
            language_choice_text=picker_namespace["language_choice_text"],
            language_choice_keyboard=picker_namespace["language_choice_keyboard"],
            normalize_user_language=normalizer,
            get_user_language=lambda _uid: stored["lang"],
            set_user_language=set_language,
            is_admin_user=lambda _uid: False,
            user_selected_vietnamese_initially=lambda _uid: False,
            enqueue_broadcast_first_start_safe=lambda _uid: None,
            record_usage_event=lambda *args, **kwargs: effects.append(("usage", args, kwargs)),
            localized_start_menu_text=lambda _uid, lang: f"main:{lang}",
            localized_main_menu_keyboard=lambda is_admin, lang: ("main-keyboard", is_admin, lang),
            safe_edit_query_message=safe_edit,
            asyncio=asyncio,
        )
        route_pattern = _registered_pattern("handle_language_callback")

        def dispatch(callback_data):
            self.assertRegex(callback_data, route_pattern)
            query = _Query(user_id, callback_data)
            asyncio.run(handler_namespace["handle_language_callback"](
                SimpleNamespace(callback_query=query), SimpleNamespace(),
            ))
            return query

        root_namespace = _load_functions(
            "localized_main_menu_keyboard",
            **_main_menu_dependencies(False, []),
        )
        root_markup = root_namespace["localized_main_menu_keyboard"](False, "vi")
        root_language_callback = next(
            button.callback_data
            for row in root_markup.inline_keyboard
            for button in row
            if button.text.endswith("change_language")
        )
        picker_query = dispatch(root_language_callback)
        self.assertEqual(picker_query.answers, [((), {})])
        picker_markup = picker_query.edits[0][1]["reply_markup"]
        emitted = [
            button.callback_data
            for row in picker_markup.inline_keyboard
            for button in row
            if str(button.callback_data or "").startswith("lang|")
        ]
        self.assertEqual(
            set(constants["USER_LANGUAGE_ORDER"]),
            {callback.split("|", 1)[1] for callback in emitted},
        )

        for callback_data in emitted:
            locale = callback_data.split("|", 1)[1]
            with self.subTest(locale=locale):
                effects.clear()
                query = dispatch(callback_data)
                self.assertEqual(query.answers, [((), {})])
                self.assertEqual(query.edits, [
                    (f"main:{locale}", {"reply_markup": ("main-keyboard", False, locale)})
                ])
                self.assertEqual(stored["lang"], locale)
                self.assertEqual(effects[0], ("set", user_id, locale))
                self.assertEqual(effects[1][0], "usage")
                self.assertEqual(effects[1][2]["status"], locale)
                self.assertEqual([effect[0] for effect in effects], ["set", "usage"])

    def test_customer_ui_root_entries_dispatch_to_their_emitted_screens(self):
        dependencies = _main_menu_dependencies(False, [])
        dependencies.update(
            time=SimpleNamespace(perf_counter=lambda: 1.0),
            logger=SimpleNamespace(info=lambda *_args, **_kwargs: None),
        )
        keyboard_namespace = _load_functions("localized_main_menu_keyboard", **dependencies)
        markup = keyboard_namespace["localized_main_menu_keyboard"](False, "vi")
        emitted = {
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.callback_data
        }
        emitted_expected = {
            "menu|main_video", "menu|main_image", "menu|main_profile", "menu|main_memory",
            "menu|support", "menu|main_guide",
        }
        self.assertTrue(emitted_expected <= emitted)
        # Video has a separate timing/navigation test because its route clears only
        # the intended pending trend state before rendering the menu.
        dispatch_expected = emitted_expected - {"menu|main_video"}
        pattern = _registered_menu_pattern()

        for callback in sorted(dispatch_expected):
            with self.subTest(callback=callback):
                dependencies["localized_menu_content"] = lambda action, *_args: (
                    f"existing screen:{action}", f"existing keyboard:{action}"
                )
                namespace = _load_functions("handle_menu_callback", **dependencies)
                query = _Query(991123, callback)
                asyncio.run(namespace["handle_menu_callback"](
                    SimpleNamespace(callback_query=query), SimpleNamespace(user_data={}),
                ))

                self.assertRegex(callback, pattern)
                self.assertEqual(query.answers, [((), {})])
                self.assertEqual(
                    query.edits,
                    [(f"existing screen:{callback.split('|', 1)[1]}",
                      {"reply_markup": f"existing keyboard:{callback.split('|', 1)[1]}"})],
                )

    def test_customer_translation_entry_and_hub_back_home_dispatch_registered_menu(self):
        effects = []
        dependencies = _main_menu_dependencies(False, effects)
        labels = {
            key: key for key in (
                "free_tools_label", "video_label", "image_label", "translation_label",
                "audio_studio_label", "account_label", "topup_pricing_label",
                "autopost_label", "chat_pro_label", "notes_docs_label", "support",
                "guide_label", "feedback_label", "center", "change_language", "admin_label",
            )
        }
        labels.update({
            "translation_title": "Dịch",
            "translation_body": "Chọn nội dung",
            "translation_language": "Ngôn ngữ",
            "translation_subtitle_dubbing": "Dịch phụ đề",
            "translation_text": "Văn bản",
            "translation_file": "Tệp",
            "translation_audio": "Âm thanh",
            "translation_conversation": "Hội thoại",
            "translation_two_way": "Hai chiều",
            "translation_auto": "Tự động",
            "translation_languages": "Ngôn ngữ",
            "translation_stop": "Dừng",
            "translation_label": "Dịch",
            "back": "Quay lại",
            "main_menu": "Menu chính",
        })

        def build_two_column_keyboard(buttons, *, nav_back, nav_main, lang, main_label):
            flat = [_Button(label, callback) for label, callback in buttons]
            rows = [flat[index:index + 2] for index in range(0, len(flat), 2)]
            if nav_back:
                nav = [_Button(nav_back[0], nav_back[1])]
                if nav_main:
                    nav.append(_Button(main_label, "menu|main"))
                rows.append(nav)
            return _Markup(rows)

        dependencies.update({
            "time": SimpleNamespace(perf_counter=lambda: 1.0),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
            "public_hub_copy": lambda _lang: labels,
            "build_2col_keyboard": build_two_column_keyboard,
            "localized_start_menu_text": lambda *_args: "MAIN SCREEN",
            "localized_main_menu_keyboard": lambda *_args: _Markup([]),
            "enter_product_context": lambda *_args, **_kwargs: effects.append("context"),
            "PRODUCT_CONTEXT_SHOWROOM": "showroom",
        })
        namespace = _load_functions(
            "localized_main_menu_keyboard", "translation_menu_text", "translation_menu_keyboard",
            "translation_language_hub_text", "translation_language_hub_keyboard",
            "localized_menu_content", "handle_menu_callback", **dependencies,
        )
        route_pattern = _registered_menu_pattern()

        def press(callback):
            self.assertRegex(callback, route_pattern)
            query = _Query(991177, callback)
            asyncio.run(namespace["handle_menu_callback"](
                SimpleNamespace(callback_query=query),
                SimpleNamespace(user_data={}),
            ))
            self.assertEqual(query.answers, [((), {})])
            self.assertEqual(len(query.edits), 1)
            return query.edits[0]

        emitted_root = namespace["localized_main_menu_keyboard"](False, "vi")
        translate_entry = next(
            button.callback_data
            for row in emitted_root.inline_keyboard
            for button in row
            if button.callback_data == "menu|translate"
        )
        root_text, root_markup = press(translate_entry)
        self.assertIn("Trung tâm dịch", root_text)
        self.assertIn(
            "menu|translation_language_hub",
            {button.callback_data for row in root_markup["reply_markup"].inline_keyboard for button in row},
        )
        self.assertEqual({"menu|main"},
            {button.callback_data for button in root_markup["reply_markup"].inline_keyboard[-1]},
        )

        hub_entry = next(
            button.callback_data
            for row in root_markup["reply_markup"].inline_keyboard
            for button in row
            if button.callback_data == "menu|translation_language_hub"
        )
        language_text, language_markup = press(hub_entry)
        self.assertIn("Dịch ngôn ngữ", language_text)
        language_buttons = [button for row in language_markup["reply_markup"].inline_keyboard for button in row]
        back_entry = next(button.callback_data for button in language_buttons if button.callback_data == "menu|translate")
        home_entry = next(button.callback_data for button in language_buttons if button.callback_data == "menu|main")

        back_text, back_markup = press(back_entry)
        self.assertIn("Trung tâm dịch", back_text)
        self.assertIn("menu|translation_language_hub",
            {button.callback_data for row in back_markup["reply_markup"].inline_keyboard for button in row},
        )
        home_text, _home_markup = press(home_entry)
        self.assertEqual("MAIN SCREEN", home_text)
        self.assertNotIn("provider", effects)

    def test_subdub_menu_back_and_home_restore_translation_parent_and_clear_pending(self):
        user_id = 991178
        other_user_state_key = "video_dubbing:991179"
        pending = {}
        pending[other_user_state_key] = {"pending_action": "video_dubbing", "step": "other-user"}
        labels = {
            key: key
            for key in (
                "free_tools_label", "video_label", "image_label", "translation_label",
                "audio_studio_label", "account_label", "topup_pricing_label", "autopost_label",
                "chat_pro_label", "notes_docs_label", "support", "guide_label", "feedback_label",
                "center", "change_language", "admin_label", "translation_title", "translation_body",
                "translation_language", "translation_subtitle_dubbing", "translation_text",
                "translation_file", "translation_audio", "translation_conversation",
                "translation_two_way", "translation_auto", "translation_languages",
                "translation_stop", "back", "main_menu",
            )
        }
        subdub_copy = {
            "menu": "SUBDUB MENU",
            "menu_body": "Choose a read-only menu option",
            "auto": "Auto subtitles",
            "translate": "Translate subtitles",
            "dub": "Dub video",
            "combo": "Subtitle + dub",
            "main": "Main menu",
            "back": "Back",
        }
        dependencies = _main_menu_dependencies(False, [])
        dependencies.update({
            "public_hub_copy": lambda _lang: labels,
            "public_subdub_deep_copy": lambda _lang: subdub_copy,
            "PRODUCT_CONTEXT_SHOWROOM": "showroom",
            "product_context_callback": lambda namespace, context, action: f"{namespace}|{context}|{action}",
            "localized_start_menu_text": lambda *_args: "MAIN SCREEN",
            "enter_product_context": lambda *_args, **_kwargs: None,
            "set_video_dubbing_pending": lambda uid, step, **fields: pending.__setitem__(
                f"video_dubbing:{uid}", {"pending_action": "video_dubbing", "step": step, **fields}
            ),
            "video_dubbing_pending_key": lambda uid: f"video_dubbing:{uid}",
            "USER_PENDING": pending,
            "VIDEO_TAIL9_TEXT_INPUT_KEY": "video_tail_pending",
            "VIDEO_SUBTITLE_MODE_CREATE": "create",
            "VIDEO_SUBTITLE_MODE_TRANSLATE": "translate",
            "VIDEO_SUBTITLE_MODE_DUB": "dub",
            "VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB": "subtitle_plus_dub",
            "time": SimpleNamespace(perf_counter=lambda: 1.0),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
        })
        def no_clear(*_args, **_kwargs):
            return False

        clear_stubs = (
            "clear_free_hub_pending", "clear_support_ticket_pending", "clear_quick_media_pending",
            "clear_quick_image_flow", "clear_public_image_prompt_pending", "clear_public_video_prompt_pending",
            "clear_media_aspect_pending", "clear_public_video_package_context", "clear_creative_motion_pending",
            "clear_cinematic_ad_pending", "clear_trend_video_flow_pending", "clear_trend_workflow_confirm_pending",
            "clear_feedback_pending", "clear_image_menu_pending", "clear_frame_video_state",
            "clear_storyboard_state", "clear_developing_video_pending", "clear_product_context",
            "clear_music_guided_pending", "clear_translation_menu_pending", "clear_video_editor_pending",
            "clear_video_downloader_pending", "clear_video_finalization_state", "clear_video_addon_state",
            "clear_marketing_pending", "clear_shopaikey_pending_confirmations_for_user",
            "clear_finance_compliance_pending", "clear_internal_archive_pending", "clear_doc_tool_pending",
            "clear_storage_addon_pending", "clear_memory_guided_pending", "clear_pending_admin_tool_test",
        )
        dependencies.update({name: no_clear for name in clear_stubs})
        dependencies["video_ai_edit_state"] = SimpleNamespace(clear_draft=lambda _uid: False)
        route_pattern = _registered_menu_pattern()
        namespace = _load_functions(
            "localized_main_menu_keyboard", "translation_menu_text", "translation_menu_keyboard",
            "video_dubbing_menu_text", "video_dubbing_back_target", "video_dubbing_menu_keyboard",
            "clear_video_dubbing_pending", "clear_media_creator_pending_states", "localized_menu_content",
            "handle_menu_callback", **dependencies,
        )

        def press(callback):
            self.assertRegex(callback, route_pattern)
            query = _Query(user_id, callback)
            _run_no_io(namespace["handle_menu_callback"](
                SimpleNamespace(callback_query=query), SimpleNamespace(user_data={}),
            ))
            self.assertEqual([((), {})], query.answers)
            self.assertEqual(1, len(query.edits))
            return query.edits[0]

        main_markup = namespace["localized_main_menu_keyboard"](False, "vi")
        translate_entry = next(
            button.callback_data for row in main_markup.inline_keyboard for button in row
            if button.callback_data == "menu|translate"
        )
        translation_text, translation_options = press(translate_entry)
        self.assertIn("Trung tâm dịch", translation_text)
        translation_markup = translation_options["reply_markup"]
        factory_entry = next(
            button.callback_data for row in translation_markup.inline_keyboard for button in row
            if button.callback_data == "menu|translation_video_factory"
        )

        subdub_text, subdub_options = press(factory_entry)
        self.assertIn("SUBDUB MENU", subdub_text)
        state_key = f"video_dubbing:{user_id}"
        self.assertEqual("video_dubbing", pending[state_key]["pending_action"])
        subdub_buttons = [
            button for row in subdub_options["reply_markup"].inline_keyboard for button in row
        ]
        back_button = next(button for button in subdub_buttons if button.text.startswith("⬅️"))
        home_button = next(button for button in subdub_buttons if button.callback_data == "menu|main")
        self.assertEqual("menu|translate", back_button.callback_data)
        self.assertFalse(
            any(button.callback_data.startswith("videodub|") for button in (back_button, home_button))
        )

        back_text, back_options = press(back_button.callback_data)
        self.assertIn("Trung tâm dịch", back_text)
        self.assertIn(
            "menu|translation_video_factory",
            {button.callback_data for row in back_options["reply_markup"].inline_keyboard for button in row},
        )
        self.assertNotIn(state_key, pending)
        self.assertEqual("other-user", pending[other_user_state_key]["step"])

        press(factory_entry)
        home_text, home_options = press(home_button.callback_data)
        self.assertEqual("MAIN SCREEN", home_text)
        self.assertIn(
            "menu|translate",
            {button.callback_data for row in home_options["reply_markup"].inline_keyboard for button in row},
        )
        self.assertNotIn(state_key, pending)
        self.assertEqual("other-user", pending[other_user_state_key]["step"])

    def test_translation_text_and_file_picker_more_and_back_dispatch_registered_callback(self):
        edits = []
        replies = []
        contexts = []
        labels = {
            "translation_picker_choose": "Choose target",
            "translation_text": "Text",
            "translation_file": "File",
            "translation_pair_source": "Source",
            "translation_picker_target": "Target language",
            "translation_picker_no_charge": "No processing at this step",
            "translation_picker_more": "More languages",
            "translation_picker_back": "Back",
            "main_menu": "Main menu",
        }

        class _Message:
            async def reply_text(self, text, **kwargs):
                replies.append((text, kwargs))

        async def safe_edit(query, text, **kwargs):
            edits.append((query.data, text, kwargs))

        dependencies = {
            "html": html,
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "TRANSLATION_MORE_LANGS": ("fr", "de"),
            "normalize_user_language": lambda lang: lang or "vi",
            "public_hub_copy": lambda _lang: labels,
            "translate_target_button_label": lambda code: code.upper(),
            "get_user_language": lambda _uid: "vi",
            "enter_product_context": lambda *_args, **_kwargs: contexts.append("context"),
            "PRODUCT_CONTEXT_SHOWROOM": "showroom",
            "safe_edit_query_message": safe_edit,
        }
        namespace = _load_functions(
            "translation_pick_text", "translation_target_keyboard",
            "reply_translation_surface", "show_translation_picker",
            "handle_translation_callback", **dependencies,
        )
        route_pattern = _registered_pattern("handle_translation_callback")
        user = SimpleNamespace(id=991178)

        def press(callback):
            self.assertRegex(callback, route_pattern)
            query = _Query(user.id, callback)
            update = SimpleNamespace(callback_query=query, effective_user=user)
            _run_no_io(namespace["handle_translation_callback"](update, SimpleNamespace()))
            self.assertEqual(query.answers, [((), {})])
            return query

        for source_type in ("text", "file"):
            with self.subTest(source_type=source_type):
                initial_update = SimpleNamespace(
                    callback_query=None,
                    effective_user=user,
                    message=_Message(),
                )
                _run_no_io(namespace["show_translation_picker"](
                    initial_update, source_type, lang="vi",
                ))
                initial_markup = replies[-1][1]["reply_markup"]
                initial_callbacks = [
                    button.callback_data
                    for row in initial_markup.inline_keyboard
                    for button in row
                ]
                more_callback = f"tr_more|{source_type}"
                self.assertIn(more_callback, initial_callbacks)

                more_query = press(more_callback)
                more_markup = edits[-1][2]["reply_markup"]
                more_callbacks = [
                    button.callback_data
                    for row in more_markup.inline_keyboard
                    for button in row
                ]
                back_callback = f"tr_pick|{source_type}"
                self.assertIn(back_callback, more_callbacks)

                back_query = press(back_callback)
                restored_markup = edits[-1][2]["reply_markup"]
                restored_callbacks = [
                    button.callback_data
                    for row in restored_markup.inline_keyboard
                    for button in row
                ]
                self.assertEqual(restored_callbacks, initial_callbacks)
                self.assertEqual(
                    [item[0] for item in edits[-2:]],
                    [more_query.data, back_query.data],
                )

        self.assertEqual(len(replies), 2)
        self.assertEqual(len(edits), 4)
        self.assertEqual(contexts, ["context"] * 4)

    def test_emitted_translation_text_target_reaches_registered_pre_provider_boundary(self):
        replies = []
        target_calls = []
        labels = {
            "translation_picker_choose": "Choose target",
            "translation_text": "Text",
            "translation_pair_source": "Source",
            "translation_picker_target": "Target language",
            "translation_picker_no_charge": "No processing at this step",
            "translation_picker_more": "More languages",
            "main_menu": "Main menu",
        }

        class _Message:
            async def reply_text(self, text, **kwargs):
                replies.append((text, kwargs))

        async def run_translation_boundary(update, context, source_text, target):
            target_calls.append((source_text, target, list(update.callback_query.answers)))

        dependencies = {
            "html": html,
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "TRANSLATION_MORE_LANGS": ("fr", "de"),
            "normalize_user_language": lambda lang: lang or "vi",
            "public_hub_copy": lambda _lang: labels,
            "translate_target_button_label": lambda code: code.upper(),
            "get_user_language": lambda _uid: "vi",
            "enter_product_context": lambda *_args, **_kwargs: None,
            "PRODUCT_CONTEXT_SHOWROOM": "showroom",
            "normalize_translate_target": lambda value: value if value in {"vi", "en", "zh", "fr", "de"} else "",
            "get_translation_request": lambda uid, source: (
                {"source_text": "fixture source text"}
                if uid == 991181 and source == "text"
                else {}
            ),
            "run_translate_text_to_target": run_translation_boundary,
        }
        namespace = _load_functions(
            "translation_pick_text", "translation_target_keyboard",
            "reply_translation_surface", "show_translation_picker",
            "handle_translation_callback", **dependencies,
        )
        route_pattern = _registered_pattern("handle_translation_callback")
        user = SimpleNamespace(id=991181)
        initial_update = SimpleNamespace(
            callback_query=None,
            effective_user=user,
            message=_Message(),
        )
        _run_no_io(namespace["show_translation_picker"](
            initial_update, "text", lang="vi",
        ))
        emitted_markup = replies[0][1]["reply_markup"]
        target_button = next(
            button
            for row in emitted_markup.inline_keyboard
            for button in row
            if button.callback_data == "tr_target|text|en"
        )

        query = _Query(user.id, target_button.callback_data)
        update = SimpleNamespace(callback_query=query, effective_user=user)
        self.assertRegex(target_button.callback_data, route_pattern)
        _run_no_io(namespace["handle_translation_callback"](update, SimpleNamespace()))

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(
            target_calls,
            [("fixture source text", "en", [((), {})])],
        )
        self.assertEqual(len(replies), 1)

    def test_emitted_translation_file_and_voice_targets_reach_inert_boundaries(self):
        replies = []
        runner_calls = []
        saved_requests = []
        contexts = []
        labels = {
            "translation_picker_choose": "Choose target",
            "translation_audio": "Audio",
            "translation_text": "Text",
            "translation_file": "File",
            "translation_pair_source": "Source",
            "translation_picker_target": "Target language",
            "translation_picker_no_charge": "No processing at this step",
            "translation_picker_more": "More languages",
            "translation_picker_back": "Back",
            "main_menu": "Main menu",
        }

        class _Message:
            async def reply_text(self, text, **kwargs):
                replies.append((text, kwargs))

        async def run_voice_boundary(update, context, target):
            runner_calls.append((
                "voice", target, list(update.callback_query.answers),
            ))

        async def run_file_boundary(update, context, target, *, info):
            runner_calls.append((
                "file", target, info, list(update.callback_query.answers),
            ))

        def get_request(uid, source_type):
            if uid != 991182:
                return None
            if source_type == "file":
                return {"source_ref": {"file_id": "fixture-file"}}
            if source_type == "voice":
                return {"source_ref": {"file_id": "fixture-audio"}}
            return None

        dependencies = {
            "html": html,
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "TRANSLATION_MORE_LANGS": ("fr", "de"),
            "normalize_user_language": lambda lang: lang or "vi",
            "public_hub_copy": lambda _lang: labels,
            "translate_target_button_label": lambda code: code.upper(),
            "get_user_language": lambda _uid: "vi",
            "enter_product_context": lambda *_args, **_kwargs: contexts.append("context"),
            "PRODUCT_CONTEXT_SHOWROOM": "showroom",
            "normalize_translate_target": lambda value: value if value in {"vi", "en", "zh", "fr", "de"} else "",
            "get_translation_request": get_request,
            "has_recent_audio_input": lambda _update: True,
            "save_translation_request": lambda uid, source: saved_requests.append((uid, source)),
            "run_translate_voice_to_target": run_voice_boundary,
            "run_translate_file_to_target": run_file_boundary,
        }
        namespace = _load_functions(
            "translation_pick_text", "translation_target_keyboard",
            "reply_translation_surface", "show_translation_picker",
            "handle_translation_callback", **dependencies,
        )
        route_pattern = _registered_pattern("handle_translation_callback")
        user = SimpleNamespace(id=991182)

        for source_type in ("file", "voice"):
            with self.subTest(source_type=source_type):
                initial_update = SimpleNamespace(
                    callback_query=None,
                    effective_user=user,
                    message=_Message(),
                )
                _run_no_io(namespace["show_translation_picker"](
                    initial_update, source_type, lang="vi",
                ))
                markup = replies[-1][1]["reply_markup"]
                target_button = next(
                    button
                    for row in markup.inline_keyboard
                    for button in row
                    if button.callback_data == f"tr_target|{source_type}|en"
                )
                self.assertRegex(target_button.callback_data, route_pattern)

                query = _Query(user.id, target_button.callback_data)
                update = SimpleNamespace(callback_query=query, effective_user=user)
                _run_no_io(namespace["handle_translation_callback"](
                    update, SimpleNamespace(),
                ))
                self.assertEqual(query.answers, [((), {})])

        self.assertEqual(
            runner_calls,
            [
                ("file", "en", {"file_id": "fixture-file"}, [((), {})]),
                ("voice", "en", [((), {})]),
            ],
        )
        self.assertEqual(saved_requests, [(991182, "voice")])
        self.assertEqual(contexts, ["context"] * 2)
        self.assertEqual(len(replies), 2)

    def test_translation_voice_picker_label_matches_audio_callback_and_returns_from_more(self):
        edits = []
        contexts = []
        replies = []
        runner_calls = []
        audio_available = {"value": True}
        copy = {
            "translation_audio": "Dịch audio",
            "translation_transcribe": "Bóc băng",
            "translation_text": "Văn bản",
            "translation_session_enable_voice": "Bật giọng nói",
            "translation_language": "Dịch ngôn ngữ",
            "translation_subtitle_dubbing": "Phụ đề và lồng tiếng",
            "translation_picker_choose": "Chọn nội dung",
            "translation_picker_target": "Ngôn ngữ đích",
            "translation_picker_no_charge": "Chưa xử lý ở bước này",
            "translation_picker_more": "Thêm ngôn ngữ",
            "translation_picker_back": "Quay lại",
            "translation_recent_media_missing": "Gửi audio lại để tiếp tục",
            "translation_audio_received_body": "Audio đã nhận",
            "main_menu": "Menu chính",
        }

        async def safe_edit(query, text, **kwargs):
            edits.append((query.data, text, kwargs))

        async def reply_text(text, **kwargs):
            replies.append((text, kwargs))

        def build_two_column_keyboard(items, *, nav_back, nav_main, lang, main_label):
            flat = [_Button(label, callback) for label, callback in items]
            rows = [flat[index:index + 2] for index in range(0, len(flat), 2)]
            if nav_back:
                rows.append([_Button(nav_back[0], nav_back[1]), _Button(main_label, "menu|main")])
            return _Markup(rows)

        dependencies = {
            "html": html,
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "TRANSLATION_MORE_LANGS": ("fr", "de"),
            "normalize_user_language": lambda lang: lang or "vi",
            "public_hub_copy": lambda _lang: copy,
            "translate_target_button_label": lambda code: code.upper(),
            "normalize_translate_target": lambda value: value if value in {"vi", "en", "zh", "fr", "de"} else "",
            "build_2col_keyboard": build_two_column_keyboard,
            "get_user_language": lambda _uid: "vi",
            "enter_product_context": lambda *_args, **_kwargs: contexts.append("context"),
            "PRODUCT_CONTEXT_SHOWROOM": "showroom",
            "has_recent_audio_input": lambda _update: audio_available["value"],
            "safe_edit_query_message": safe_edit,
            "translation_voice_menu_text": lambda _lang: "voice menu parent",
            "voice_translation_action_keyboard": lambda _lang: _Markup([]),
            "run_translate_voice_to_target": lambda *_args, **_kwargs: runner_calls.append("run"),
            "save_translation_request": lambda *_args, **_kwargs: runner_calls.append("save"),
        }
        namespace = _load_functions(
            "translation_voice_menu_keyboard", "translation_voice_recovery_keyboard",
            "translation_pick_text",
            "translation_target_keyboard", "voice_translation_action_keyboard",
            "audio_voice_received_text", "show_translation_picker",
            "handle_translation_callback", **dependencies,
        )
        route_pattern = _registered_pattern("handle_translation_callback")
        voice_menu = namespace["translation_voice_menu_keyboard"]("vi", parent="language")
        voice_button = next(
            button
            for row in voice_menu.inline_keyboard
            for button in row
            if button.callback_data.startswith("tr_pick|voice")
        )
        self.assertEqual(voice_button.text, "🌐 Dịch audio")

        async def receive_warning(text, **kwargs):
            replies.append((text, kwargs))

        def press(callback):
            self.assertRegex(callback, route_pattern)
            query = _Query(991179, callback)
            query.message = SimpleNamespace(text="", reply_text=receive_warning)
            update = SimpleNamespace(
                callback_query=query,
                effective_user=query.from_user,
                effective_message=SimpleNamespace(reply_to_message=None),
            )
            _run_no_io(namespace["handle_translation_callback"](update, SimpleNamespace()))
            self.assertEqual(query.answers, [((), {})])
            return query

        press(voice_button.callback_data)
        first_markup = edits[-1][2]["reply_markup"]
        first_callbacks = [
            button.callback_data
            for row in first_markup.inline_keyboard
            for button in row
        ]
        self.assertEqual(voice_button.callback_data, "tr_pick|voice|language")
        self.assertIn("tr_more|voice|language", first_callbacks)
        self.assertIn("tr_back|voice|language", first_callbacks)
        self.assertIn("menu|main", first_callbacks)
        press("tr_more|voice|language")
        expanded_callbacks = [
            button.callback_data
            for row in edits[-1][2]["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertIn("tr_pick_back|voice|language", expanded_callbacks)
        self.assertIn("menu|main", expanded_callbacks)
        audio_available["value"] = False
        press("tr_pick_back|voice|language")
        restored_callbacks = [
            button.callback_data
            for row in edits[-1][2]["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertEqual(restored_callbacks, first_callbacks)
        press("tr_target|voice|en|language")
        self.assertEqual(len(replies), 1)
        press("tr_back|voice|language")
        self.assertEqual(edits[-1][1], "voice menu parent")
        self.assertEqual(
            next(
                button.callback_data
                for row in edits[-1][2]["reply_markup"].inline_keyboard
                for button in row
                if button.text == "🌐 Dịch audio"
            ),
            "tr_pick|voice|language",
        )
        press(voice_button.callback_data)
        self.assertEqual(len(replies), 2)
        recovery_callbacks = [
            button.callback_data
            for row in replies[-1][1]["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertIn("tr_pick|voice|language", recovery_callbacks)
        self.assertIn("menu|translation_language_hub", recovery_callbacks)
        self.assertEqual(runner_calls, [])

        audio_available["value"] = True
        media_menu = namespace["translation_voice_menu_keyboard"]("vi", parent="media")
        media_button = next(
            button
            for row in media_menu.inline_keyboard
            for button in row
            if button.text == "🌐 Dịch audio"
        )
        self.assertEqual(media_button.callback_data, "tr_pick|voice|media")
        press(media_button.callback_data)
        press("tr_back|voice|media")
        self.assertEqual(edits[-1][1], "voice menu parent")
        self.assertEqual(
            next(
                button.callback_data
                for row in edits[-1][2]["reply_markup"].inline_keyboard
                for button in row
                if button.text.startswith("⬅️")
            ),
            "menu|translation_video_factory",
        )

        action_keyboard = namespace["voice_translation_action_keyboard"]("vi")
        action_callbacks = [
            button.callback_data
            for row in action_keyboard.inline_keyboard
            for button in row
        ]
        self.assertIn("menu|main", action_callbacks)
        press("tr_pick|voice|actions")
        action_picker_callbacks = [
            button.callback_data
            for row in edits[-1][2]["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertIn("tr_back|voice|actions", action_picker_callbacks)
        press("tr_back|voice|actions")
        self.assertEqual(edits[-1][1], namespace["audio_voice_received_text"]("vi"))
        self.assertEqual(len(edits), 8)
        self.assertEqual(contexts, ["context"] * 10)

    def test_translation_transcribe_missing_audio_returns_emitted_recovery_keyboard(self):
        copy = {
            "translation_transcribe": "Bóc băng",
            "translation_audio": "Dịch audio",
            "translation_session_enable_voice": "Bật giọng nói",
            "translation_picker_more": "Thêm ngôn ngữ",
            "translation_recent_media_missing": "Gửi audio lại để tiếp tục",
            "main_menu": "Menu chính",
        }
        provider_calls = []
        replies = []
        contexts = []

        async def reply_text(text, **kwargs):
            replies.append((text, kwargs))

        def forbidden_transcribe(*_args, **_kwargs):
            provider_calls.append("transcribe")
            raise AssertionError("missing-audio recovery must stop before transcription")

        namespace = _load_functions(
            "voice_translation_action_keyboard",
            "translation_voice_recovery_keyboard",
            "handle_translation_callback",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
            public_hub_copy=lambda _lang: copy,
            normalize_user_language=lambda lang: lang or "vi",
            get_user_language=lambda _uid: "vi",
            has_recent_audio_input=lambda _update: False,
            enter_product_context=lambda *_args, **_kwargs: contexts.append("entered"),
            PRODUCT_CONTEXT_SHOWROOM="showroom",
            cmd_transcribe=forbidden_transcribe,
        )
        emitted_keyboard = namespace["voice_translation_action_keyboard"]("vi")
        emitted = next(
            button for row in emitted_keyboard.inline_keyboard for button in row
            if button.text == "Bóc băng"
        )
        self.assertEqual("tr_transcribe", emitted.callback_data)

        registrations = []
        namespace["tg_app"] = SimpleNamespace(add_handler=registrations.append)
        namespace["CallbackQueryHandler"] = lambda callback, pattern: SimpleNamespace(
            callback=callback,
            pattern=re.compile(pattern),
        )
        registration = next(
            line.strip()
            for line in BOT_SOURCE.splitlines()
            if "tg_app.add_handler(CallbackQueryHandler(handle_translation_callback," in line
        )
        exec(registration, namespace)
        route = next(
            item for item in registrations
            if item.callback is namespace["handle_translation_callback"]
        )
        self.assertIsNotNone(route.pattern.match(emitted.callback_data))

        query = _Query(991185, emitted.callback_data)
        query.message = SimpleNamespace(reply_text=reply_text)
        _run_no_io(route.callback(
            SimpleNamespace(callback_query=query),
            SimpleNamespace(),
        ))

        self.assertEqual(1, len(query.answers))
        self.assertIn("Gửi audio lại", replies[0][0])
        self.assertIn("reply_markup", replies[0][1])
        recovery_callbacks = [
            button.callback_data
            for row in replies[0][1]["reply_markup"].inline_keyboard
            for button in row
        ]
        emitted_callbacks = [
            button.callback_data
            for row in emitted_keyboard.inline_keyboard
            for button in row
        ]
        self.assertEqual(emitted_callbacks, recovery_callbacks)
        self.assertIn("menu|main", recovery_callbacks)
        self.assertEqual(["entered"], contexts)
        self.assertEqual([], provider_calls)

    def test_free_tools_aichat_entry_requires_consent_and_back_returns_to_free_tools(self):
        user_id = 991180
        state = {"value": {}}
        consent_requests = []
        consent_grants = []
        saved_states = []
        rendered = []
        copy = {
            "freehub_enable_ai_chatbot": "AI Chatbot",
            "freehub_utilities": "Utilities",
            "freehub_meta": "Meta prompts",
            "freehub_caption": "Captions",
            "freehub_ideas": "Ideas",
            "freehub_prompts": "Prompt library",
            "freehub_library": "Saved prompts",
            "freehub_publish_package": "Publishing packages",
            "freehub_notes_docs": "Notes / Documents",
            "freehub_save_temp_media": "Temporary media",
            "freehub_voice_subdub_script": "Voiceover scripts",
            "freehub_music_sfx_ideas": "Music / SFX",
            "freehub_translation": "Translation",
            "freehub_video_downloader": "Video downloader",
            "main_menu": "Main menu",
        }

        def build_two_column_keyboard(items, *, nav_back, nav_main, lang, main_label):
            flat = [_Button(label, callback) for label, callback in items]
            rows = [flat[index:index + 2] for index in range(0, len(flat), 2)]
            if nav_back:
                rows.append([_Button(nav_back[0], nav_back[1])])
            if nav_main:
                rows.append([_Button(main_label, "menu|main")])
            return _Markup(rows)

        keyboard_dependencies = {
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "normalize_user_language": lambda lang: lang or "vi",
            "public_hub_copy": lambda _lang: copy,
            "build_2col_keyboard": build_two_column_keyboard,
        }
        keyboard_namespace = _load_functions(
            "build_2col_keyboard", "free_hub_main_keyboard", **keyboard_dependencies,
        )
        consent_namespace = _load_functions(
            "aichat_consent_keyboard",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
        )

        async def safe_edit_or_send(query, text, **kwargs):
            rendered.append((text, kwargs))
            query.edits.append((text, kwargs))

        def request_enable(current, target_user_id):
            consent_requests.append(target_user_id)
            return {**current, "pending_consent_for": target_user_id}, {"reply": "Consent is required."}

        def enable_with_consent(_current, target_user_id):
            consent_grants.append(target_user_id)
            return {"enabled_for": target_user_id}, {"reply": "Enabled."}

        dependencies = {
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "normalize_user_language": lambda lang: lang or "vi",
            "public_hub_copy": lambda _lang: copy,
            "build_2col_keyboard": build_two_column_keyboard,
            "get_user_language": lambda _uid: "vi",
            "aichat_state": lambda: state["value"],
            "save_aichat_state": lambda value: (state.update(value=value), saved_states.append(value)),
            "ai_chatbot_copilot": SimpleNamespace(
                request_enable=request_enable,
                enable_with_consent=enable_with_consent,
            ),
            "free_hub_main_text": lambda _lang: "Free Tools root",
            "free_hub_main_keyboard": keyboard_namespace["free_hub_main_keyboard"],
            "aichat_consent_keyboard": consent_namespace["aichat_consent_keyboard"],
            "safe_edit_or_send": safe_edit_or_send,
        }
        namespace = _load_functions("handle_aichat_callback", **dependencies)
        route_pattern = _registered_pattern("handle_aichat_callback")
        freehub_markup = keyboard_namespace["free_hub_main_keyboard"]("vi")
        entry = next(
            button
            for row in freehub_markup.inline_keyboard
            for button in row
            if button.callback_data == "aichat|on"
        )

        def press(callback):
            self.assertRegex(callback, route_pattern)
            query = _Query(user_id, callback)
            asyncio.run(namespace["handle_aichat_callback"](
                SimpleNamespace(callback_query=query), SimpleNamespace(),
            ))
            self.assertEqual(query.answers, [((), {})])
            self.assertEqual(len(query.edits), 1)
            return query

        consent_screen = press(entry.callback_data)
        self.assertIn("Consent is required.", consent_screen.edits[0][0])
        consent_keyboard = consent_screen.edits[0][1]["reply_markup"]
        consent_callbacks = [
            button.callback_data
            for row in consent_keyboard.inline_keyboard
            for button in row
        ]
        self.assertEqual(consent_callbacks, [
            "aichat|consent_on", "aichat|back_freehub", "menu|main",
        ])

        returned = press("aichat|back_freehub")
        self.assertEqual(returned.edits[0][0], "Free Tools root")
        self.assertIn(
            "aichat|on",
            [
                button.callback_data
                for row in returned.edits[0][1]["reply_markup"].inline_keyboard
                for button in row
            ],
        )
        self.assertEqual(consent_requests, [user_id])
        self.assertEqual(consent_grants, [])
        self.assertEqual(len(saved_states), 1)

    def test_aichat_consent_requires_pending_state_and_preserves_valid_grant(self):
        user_id = 991181
        state = {"enabled": False, "consented": True, "pending_consent": False}
        consent_grants = []
        saved_states = []

        consent_namespace = _load_functions(
            "aichat_consent_keyboard",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
        )
        stale_button = next(
            button
            for row in consent_namespace["aichat_consent_keyboard"]().inline_keyboard
            for button in row
            if button.callback_data == "aichat|consent_on"
        )
        holder = {"state": state}
        rendered = []

        async def safe_edit_or_send(query, text, **kwargs):
            rendered.append((text, kwargs))
            query.edits.append((text, kwargs))

        def status_payload(current, _target_user_id):
            return {
                "enabled": bool(current.get("enabled")),
                "consented": bool(current.get("consented")),
                "pending_consent": bool(current.get("pending_consent")),
                "assist_actions": False,
                "last_trace": {},
            }

        def enable_with_consent(current, target_user_id):
            consent_grants.append(target_user_id)
            return {
                **current,
                "enabled": True,
                "consented": True,
                "pending_consent": False,
            }, {"reply": "Enabled."}

        keyboard_namespace = _load_functions(
            "aichat_control_keyboard",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
        )
        dependencies = {
            "get_user_language": lambda _uid: "vi",
            "aichat_state": lambda: holder["state"],
            "save_aichat_state": lambda value: (holder.update(state=value), saved_states.append(value)),
            "ai_chatbot_copilot": SimpleNamespace(
                enable_with_consent=enable_with_consent,
                status_payload=status_payload,
            ),
            "aichat_control_keyboard": keyboard_namespace["aichat_control_keyboard"],
            "free_hub_main_text": lambda _lang: "Free Tools root",
            "free_hub_main_keyboard": lambda _lang: _Markup([[_Button("AI Chatbot", "aichat|on")]]),
            "safe_edit_or_send": safe_edit_or_send,
        }
        namespace = _load_functions("handle_aichat_callback", **dependencies)
        self.assertRegex(stale_button.callback_data, _registered_pattern("handle_aichat_callback"))

        query = _Query(user_id, stale_button.callback_data)
        asyncio.run(namespace["handle_aichat_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(),
        ))

        self.assertEqual(query.answers, [((), {})])
        self.assertFalse(holder["state"]["enabled"])
        self.assertFalse(holder["state"]["pending_consent"])
        self.assertEqual(consent_grants, [])
        self.assertEqual(saved_states, [])
        self.assertEqual(rendered[0][0], "Free Tools root")

        holder["state"] = {"enabled": False, "consented": False, "pending_consent": True}
        pending_query = _Query(user_id, stale_button.callback_data)
        asyncio.run(namespace["handle_aichat_callback"](
            SimpleNamespace(callback_query=pending_query), SimpleNamespace(),
        ))

        self.assertEqual(pending_query.answers, [((), {})])
        self.assertEqual(consent_grants, [user_id])
        self.assertTrue(holder["state"]["enabled"])
        self.assertEqual(len(saved_states), 1)
        self.assertEqual(pending_query.edits[0][0], "Enabled.")

    def test_aichat_trace_emitted_back_returns_to_enabled_status_without_state_write(self):
        user_id = 991182
        state = {"enabled": True, "consented": True, "pending_consent": False}
        payload = {
            "enabled": True,
            "consented": True,
            "assist_actions": False,
            "last_trace": {},
            "trace": [],
            "state_source": "fixture",
        }
        state_before = dict(state)
        rendered = []

        async def safe_edit_or_send(query, text, **kwargs):
            query.edits.append((text, kwargs))
            rendered.append((text, kwargs))

        dependencies = {
            "html": html,
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "get_user_language": lambda _uid: "vi",
            "aichat_state": lambda: state,
            "save_aichat_state": lambda _value: self.fail("read-only route must not save state"),
            "ai_chatbot_copilot": SimpleNamespace(
                status_payload=lambda _current, _uid: dict(payload),
            ),
            "aichat_control_keyboard": _load_functions(
                "aichat_control_keyboard",
                InlineKeyboardButton=_Button,
                InlineKeyboardMarkup=_Markup,
            )["aichat_control_keyboard"],
            "aichat_trace_keyboard": _load_functions(
                "aichat_trace_keyboard",
                InlineKeyboardButton=_Button,
                InlineKeyboardMarkup=_Markup,
            )["aichat_trace_keyboard"],
            "aichat_status_text": _load_functions("aichat_status_text", html=html)["aichat_status_text"],
            "aichat_trace_text": _load_functions("aichat_trace_text", html=html)["aichat_trace_text"],
            "safe_edit_or_send": safe_edit_or_send,
        }
        namespace = _load_functions("handle_aichat_callback", **dependencies)
        route_pattern = _registered_pattern("handle_aichat_callback")

        emitted_control_keyboard = dependencies["aichat_control_keyboard"](payload)
        trace_button = next(
            button
            for row in emitted_control_keyboard.inline_keyboard
            for button in row
            if button.text == "Trace"
        )
        self.assertEqual(trace_button.callback_data, "aichat|trace")
        self.assertRegex(trace_button.callback_data, route_pattern)
        trace_query = _Query(user_id, trace_button.callback_data)
        asyncio.run(namespace["handle_aichat_callback"](
            SimpleNamespace(callback_query=trace_query), SimpleNamespace(),
        ))

        self.assertEqual(trace_query.answers, [((), {})])
        self.assertIn("AI Chatbot Trace", trace_query.edits[0][0])
        trace_markup = trace_query.edits[0][1]["reply_markup"]
        back_button = next(
            button
            for row in trace_markup.inline_keyboard
            for button in row
            if button.callback_data == "aichat|back_active"
        )
        self.assertEqual(back_button.text, "⬅️ AI Chatbot")
        self.assertRegex(back_button.callback_data, route_pattern)

        back_query = _Query(user_id, back_button.callback_data)
        asyncio.run(namespace["handle_aichat_callback"](
            SimpleNamespace(callback_query=back_query), SimpleNamespace(),
        ))

        self.assertEqual(back_query.answers, [((), {})])
        self.assertIn("Enabled: <code>yes</code>", back_query.edits[0][0])
        self.assertEqual(
            [
                button.callback_data
                for row in back_query.edits[0][1]["reply_markup"].inline_keyboard
                for button in row
            ],
            [
                "aichat|off", "aichat|assist_on", "aichat|status",
                "aichat|trace", "aichat|back_freehub", "menu|main",
            ],
        )
        self.assertEqual(state, state_before)
        self.assertEqual(len(rendered), 2)

    def test_aichat_status_emitted_control_renders_status_without_state_write(self):
        user_id = 991183
        state = {"enabled": True, "consented": True, "pending_consent": False}
        payload = {
            "enabled": True,
            "consented": True,
            "assist_actions": False,
            "last_trace": {},
            "state_source": "fixture",
        }
        state_before = dict(state)
        rendered = []

        async def safe_edit_or_send(query, text, **kwargs):
            query.edits.append((text, kwargs))
            rendered.append((text, kwargs))

        control_keyboard = _load_functions(
            "aichat_control_keyboard",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
        )["aichat_control_keyboard"]
        trace_keyboard = _load_functions(
            "aichat_trace_keyboard",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
        )["aichat_trace_keyboard"]
        status_text = _load_functions("aichat_status_text", html=html)["aichat_status_text"]
        dependencies = {
            "html": html,
            "get_user_language": lambda _uid: "vi",
            "aichat_state": lambda: state,
            "save_aichat_state": lambda _value: self.fail("read-only status route must not save state"),
            "ai_chatbot_copilot": SimpleNamespace(
                status_payload=lambda _current, _uid: dict(payload),
            ),
            "aichat_control_keyboard": control_keyboard,
            "aichat_trace_keyboard": trace_keyboard,
            "aichat_status_text": status_text,
            "safe_edit_or_send": safe_edit_or_send,
        }
        namespace = _load_functions("handle_aichat_callback", **dependencies)
        route_pattern = _registered_pattern("handle_aichat_callback")
        emitted_control_keyboard = control_keyboard(payload)
        status_button = next(
            button
            for row in emitted_control_keyboard.inline_keyboard
            for button in row
            if button.text == "AI Chatbot status"
        )
        self.assertEqual(status_button.callback_data, "aichat|status")
        self.assertRegex(status_button.callback_data, route_pattern)

        query = _Query(user_id, status_button.callback_data)
        asyncio.run(namespace["handle_aichat_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(),
        ))

        self.assertEqual(query.answers, [((), {})])
        self.assertIn("Enabled: <code>yes</code>", query.edits[0][0])
        self.assertIn("Consent: <code>yes</code>", query.edits[0][0])
        self.assertEqual(
            [
                button.callback_data
                for row in query.edits[0][1]["reply_markup"].inline_keyboard
                for button in row
            ],
            ["aichat|back_active", "menu|main"],
        )
        self.assertEqual(state, state_before)
        self.assertEqual(len(rendered), 1)

    def test_aichat_enabled_back_emitted_control_restores_free_tools_root(self):
        user_id = 991184
        state = {"enabled": True, "consented": True, "pending_consent": False}
        state_before = dict(state)
        copy = {
            "freehub_enable_ai_chatbot": "AI Chatbot",
            "freehub_meta": "Meta prompts",
            "freehub_caption": "Captions",
            "freehub_ideas": "Ideas",
            "freehub_prompts": "Prompt library",
            "freehub_library": "Saved prompts",
            "freehub_publish_package": "Publishing packages",
            "freehub_notes_docs": "Notes / Documents",
            "freehub_save_temp_media": "Temporary media",
            "freehub_voice_subdub_script": "Voiceover scripts",
            "freehub_music_sfx_ideas": "Music / SFX",
            "main_menu": "Main menu",
        }

        def build_two_column_keyboard(items, *, nav_back, nav_main, lang, main_label):
            flat = [_Button(label, callback) for label, callback in items]
            rows = [flat[index:index + 2] for index in range(0, len(flat), 2)]
            if nav_back:
                rows.append([_Button(nav_back[0], nav_back[1])])
            if nav_main:
                rows.append([_Button(main_label, "menu|main")])
            return _Markup(rows)

        freehub_namespace = _load_functions(
            "build_2col_keyboard", "free_hub_main_keyboard",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
            normalize_user_language=lambda lang: lang or "vi",
            public_hub_copy=lambda _lang: copy,
            build_2col_keyboard=build_two_column_keyboard,
        )
        control_namespace = _load_functions(
            "aichat_control_keyboard",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
        )
        rendered = []

        async def safe_edit_or_send(query, text, **kwargs):
            query.edits.append((text, kwargs))
            rendered.append((text, kwargs))

        dependencies = {
            "get_user_language": lambda _uid: "vi",
            "aichat_state": lambda: state,
            "save_aichat_state": lambda _value: self.fail("navigation must not save AI Chat state"),
            "free_hub_main_text": lambda _lang: "Free Tools root",
            "free_hub_main_keyboard": freehub_namespace["free_hub_main_keyboard"],
            "aichat_control_keyboard": control_namespace["aichat_control_keyboard"],
            "safe_edit_or_send": safe_edit_or_send,
        }
        namespace = _load_functions("handle_aichat_callback", **dependencies)
        route_pattern = _registered_pattern("handle_aichat_callback")
        emitted_control = control_namespace["aichat_control_keyboard"]({
            "enabled": True,
            "consented": True,
            "assist_actions": False,
        })
        back_button = next(
            button
            for row in emitted_control.inline_keyboard
            for button in row
            if button.callback_data == "aichat|back_freehub"
        )
        self.assertEqual(back_button.text, "⬅️ Quay lại")
        self.assertRegex(back_button.callback_data, route_pattern)

        query = _Query(user_id, back_button.callback_data)
        _run_no_io(namespace["handle_aichat_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(),
        ))

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(query.edits[0][0], "Free Tools root")
        self.assertEqual(
            [
                button.callback_data
                for row in query.edits[0][1]["reply_markup"].inline_keyboard
                for button in row
            ],
            [
                "aichat|on", "freehub|open_utilities", "freehub|meta",
                "freehub|caption", "freehub|ideas", "freehub|prompts",
                "freehub|library", "freehub|publish_package",
                "menu|main_memory|freehub", "freehub|upload", "freehub|hook",
                "freehub|lib_music_root", "freehub|open_translate", "vdownload|start|freehub",
                "menu|main",
            ],
        )
        self.assertEqual(state, state_before)
        self.assertEqual(len(rendered), 1)

    def test_customer_image_menu_prompt_back_and_home_restore_expected_parent_without_entering_tools(self):
        effects = []
        dependencies = _main_menu_dependencies(False, effects)
        copy = {
            "image_quick": "Quick image",
            "image_prompt_from_image": "Prompt from image",
            "image_upload_reference": "Upload a reference image",
            "common_no_charge": "No charge",
            "image_ai_edit": "AI image edit",
            "image_edit": "Image edit",
            "back": "Back",
            "main_menu": "Main menu",
        }
        image_screen_copy = {
            "send_image": "Send image",
            "manual_description": "Manual description",
            "back_image": "Back to Image",
            "send_prompt_hint": "Send an image to start",
        }

        def build_two_column_keyboard(buttons, *, nav_back, lang, main_label):
            flat = [_Button(label, callback) for label, callback in buttons]
            rows = [flat[index:index + 2] for index in range(0, len(flat), 2)]
            rows.append([_Button(nav_back[0], nav_back[1]), _Button(main_label, "menu|main")])
            return _Markup(rows)

        dependencies.update({
            "public_hub_copy": lambda _lang: copy,
            "public_image_screen_copy": lambda _lang: image_screen_copy,
            "ui_text": lambda _lang, key: "Main menu" if key == "common.main_menu" else key,
            "build_2col_keyboard": build_two_column_keyboard,
            "image_menu_v5_text": lambda _lang: "actual image menu",
            "image_prompt_menu_start_text": lambda _lang: "actual prompt screen",
            "set_image_menu_pending": lambda *_args, **_kwargs: None,
            "localized_start_menu_text": lambda *_args: "actual main menu",
            "localized_main_menu_keyboard": lambda *_args: _Markup([]),
            "time": SimpleNamespace(perf_counter=lambda: 1.0),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
        })
        namespace = _load_functions(
            "menu_text_main_image", "menu_text_main_image_i18n", "main_image_keyboard",
            "image_prompt_start_keyboard", "localized_menu_content", "handle_menu_callback",
            **dependencies,
        )
        route_pattern = _registered_menu_pattern()
        image_entry = "menu|main_image"
        self.assertRegex(image_entry, route_pattern)
        image_query = _Query(991126, image_entry)
        context = SimpleNamespace(user_data={})
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=image_query), context,
        ))

        self.assertEqual([((), {})], image_query.answers)
        self.assertEqual("actual image menu", image_query.edits[0][0])
        image_markup = image_query.edits[0][1]["reply_markup"]
        image_callbacks = [button.callback_data for row in image_markup.inline_keyboard for button in row]
        self.assertEqual(
            ["create_media|quick_image", "menu|image_prompt_start", "imgtool|edit_ai_start",
             "menu|image_edit_start", "menu|main", "menu|main"],
            image_callbacks,
        )

        prompt_entry = next(data for data in image_callbacks if data == "menu|image_prompt_start")
        self.assertRegex(prompt_entry, route_pattern)
        prompt_query = _Query(991126, prompt_entry)
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=prompt_query), context,
        ))
        self.assertEqual([((), {})], prompt_query.answers)
        self.assertEqual("actual prompt screen", prompt_query.edits[0][0])
        prompt_markup = prompt_query.edits[0][1]["reply_markup"]
        prompt_back = next(
            button for row in prompt_markup.inline_keyboard for button in row
            if button.text.startswith("⬅️")
        )
        self.assertEqual("menu|main_image", prompt_back.callback_data)
        self.assertRegex(prompt_back.callback_data, route_pattern)

        back_query = _Query(991126, prompt_back.callback_data)
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=back_query), context,
        ))
        self.assertEqual([((), {})], back_query.answers)
        self.assertEqual("actual image menu", back_query.edits[0][0])
        restored_callbacks = [
            button.callback_data
            for row in back_query.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertEqual(image_callbacks, restored_callbacks)

        # Other image-tool callbacks are inspected only; no tool/engine callback is dispatched.
        home_query = _Query(991126, "menu|main")
        self.assertRegex(home_query.data, route_pattern)
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=home_query), context,
        ))
        self.assertEqual([((), {})], home_query.answers)
        self.assertEqual("actual main menu", home_query.edits[0][0])

    def test_image_prompt_send_image_back_clears_only_actor_pending_and_returns_to_image_hub(self):
        user_id, other_user_id = 991127, 991128
        effects = []
        dependencies = _main_menu_dependencies(False, effects)
        copy = {
            "image_quick": "Quick image",
            "image_prompt_from_image": "Prompt from image",
            "image_upload_reference": "Upload a reference image",
            "common_no_charge": "No charge",
            "image_ai_edit": "AI image edit",
            "image_edit": "Image edit",
            "back": "Back",
            "main_menu": "Main menu",
        }
        image_screen_copy = {
            "send_image": "Send image",
            "manual_description": "Manual description",
            "back_image": "Back to Image",
            "send_prompt_hint": "Send an image to start",
        }

        def build_two_column_keyboard(buttons, *, nav_back, lang, main_label):
            flat = [_Button(label, callback) for label, callback in buttons]
            rows = [flat[index:index + 2] for index in range(0, len(flat), 2)]
            rows.append([_Button(nav_back[0], nav_back[1]), _Button(main_label, "menu|main")])
            return _Markup(rows)

        clear_helpers = (
            "clear_free_hub_pending", "clear_support_ticket_pending", "clear_quick_media_pending",
            "clear_quick_image_flow", "clear_public_image_prompt_pending",
            "clear_public_video_prompt_pending", "clear_media_aspect_pending",
            "clear_public_video_package_context", "clear_creative_motion_pending",
            "clear_cinematic_ad_pending", "clear_trend_video_flow_pending",
            "clear_trend_workflow_confirm_pending", "clear_feedback_pending",
            "clear_frame_video_state", "clear_storyboard_state",
            "clear_developing_video_pending", "clear_product_context",
            "clear_video_editor_pending", "clear_video_downloader_pending",
            "clear_video_dubbing_pending", "clear_video_finalization_state",
            "clear_video_addon_state", "clear_marketing_pending",
            "clear_shopaikey_pending_confirmations_for_user",
        )
        dependencies.update({
            "public_hub_copy": lambda _lang: copy,
            "public_image_screen_copy": lambda _lang: image_screen_copy,
            "ui_text": lambda _lang, key: "Main menu" if key == "common.main_menu" else key,
            "build_2col_keyboard": build_two_column_keyboard,
            "image_menu_v5_text": lambda _lang: "actual image menu",
            "image_prompt_menu_start_text": lambda _lang: "actual prompt screen",
            "image_prompt_send_image_hint_text": lambda _lang: "fixture image intake prompt",
            "localized_start_menu_text": lambda *_args: "actual main menu",
            "localized_main_menu_keyboard": lambda *_args: _Markup([]),
            "get_user_language": lambda _uid: "vi",
            "QUICK_MEDIA_PENDING_TTL_SECONDS": 600,
            "IMAGE_MENU_PENDING_ACTIONS": {"image_prompt_wait_image"},
            "USER_PENDING": {},
            "time": SimpleNamespace(time=lambda: 100.0, perf_counter=lambda: 1.0),
            "video_ai_edit_state": SimpleNamespace(clear_draft=lambda _uid: False),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
        })
        dependencies.update({name: (lambda *_args, **_kwargs: False) for name in clear_helpers})
        namespace = _load_functions(
            "menu_text_main_image", "menu_text_main_image_i18n", "main_image_keyboard",
            "image_prompt_menu_start_text", "image_prompt_start_keyboard",
            "image_menu_pending_key", "set_image_menu_pending", "get_image_menu_pending",
            "clear_image_menu_pending", "clear_media_creator_pending_states",
            "localized_menu_content", "handle_menu_callback", "handle_image_tools_callback",
            **dependencies,
        )
        # The actual shared cleanup helper runs with all unrelated cleanup seams inert.
        namespace["clear_media_creator_pending_states"] = _load_functions(
            "clear_media_creator_pending_states",
            **{key: value for key, value in namespace.items() if key.startswith("clear_")},
            video_ai_edit_state=dependencies["video_ai_edit_state"],
        )["clear_media_creator_pending_states"]
        registered = []
        namespace.update(
            tg_app=SimpleNamespace(add_handler=registered.append),
            CallbackQueryHandler=lambda callback, pattern: (callback, re.compile(pattern)),
        )
        for handler_name in ("handle_menu_callback", "handle_image_tools_callback"):
            registration = re.search(
                rf"(?m)^\s*tg_app\.add_handler\(CallbackQueryHandler\({handler_name},.*$",
                BOT_SOURCE,
            )
            self.assertIsNotNone(registration, f"missing registration for {handler_name}")
            exec(compile(registration.group(0).strip(), f"bot.py:{handler_name} registration", "exec"), namespace)
        callbacks_by_handler = {callback.__name__: (callback, pattern) for callback, pattern in registered}
        menu_callback, menu_pattern = callbacks_by_handler["handle_menu_callback"]
        image_callback, image_pattern = callbacks_by_handler["handle_image_tools_callback"]
        context = SimpleNamespace(user_data={})

        image_query = _Query(user_id, "menu|main_image")
        self.assertRegex(image_query.data, menu_pattern)
        asyncio.run(menu_callback(
            SimpleNamespace(callback_query=image_query), context,
        ))
        self.assertEqual([((), {})], image_query.answers)
        image_callbacks = [
            button.callback_data
            for row in image_query.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
        ]
        prompt_entry = next(data for data in image_callbacks if data == "menu|image_prompt_start")
        prompt_query = _Query(user_id, prompt_entry)
        asyncio.run(menu_callback(
            SimpleNamespace(callback_query=prompt_query), context,
        ))
        self.assertEqual([((), {})], prompt_query.answers)
        send_image = next(
            button for row in prompt_query.edits[0][1]["reply_markup"].inline_keyboard
            for button in row if button.callback_data == "imgtool|prompt_need_image"
        )
        self.assertRegex(send_image.callback_data, image_pattern)

        send_query = _Query(user_id, send_image.callback_data)
        asyncio.run(image_callback(
            SimpleNamespace(callback_query=send_query), context,
        ))
        self.assertEqual([((), {})], send_query.answers)
        self.assertEqual("image_prompt_wait_image", namespace["get_image_menu_pending"](user_id)["pending_action"])
        self.assertEqual("fixture image intake prompt", send_query.edits[0][0])
        back = next(
            button for row in send_query.edits[0][1]["reply_markup"].inline_keyboard
            for button in row if button.callback_data == "menu|main_image"
        )
        self.assertRegex(back.callback_data, menu_pattern)
        namespace["set_image_menu_pending"](other_user_id, "image_prompt_wait_image")

        back_query = _Query(user_id, back.callback_data)
        asyncio.run(menu_callback(
            SimpleNamespace(callback_query=back_query), context,
        ))
        self.assertEqual([((), {})], back_query.answers)
        restored_callbacks = [
            button.callback_data
            for row in back_query.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertEqual(image_callbacks, restored_callbacks)
        self.assertEqual([((), {})], back_query.answers)
        self.assertIsNone(namespace["get_image_menu_pending"](user_id))
        self.assertEqual("image_prompt_wait_image", namespace["get_image_menu_pending"](other_user_id)["pending_action"])

    def test_image_ai_edit_intake_back_restores_hub_and_clears_only_actor_pending(self):
        user_id, other_user_id = 991129, 991130
        dependencies = _main_menu_dependencies(False, [])
        hub_copy = {
            "image_quick": "Quick image", "image_prompt_from_image": "Prompt from image",
            "image_ai_edit": "AI image edit", "image_edit": "Image edit",
            "back": "Back", "main_menu": "Main menu",
        }
        screen_copy = {"send_image": "Send image", "back_image": "Back to Image"}

        def build_two_column_keyboard(buttons, *, nav_back, lang, main_label="Main menu"):
            flat = [_Button(label, callback) for label, callback in buttons]
            rows = [flat[index:index + 2] for index in range(0, len(flat), 2)]
            rows.append([_Button(nav_back[0], nav_back[1]), _Button(main_label, "menu|main")])
            return _Markup(rows)

        clear_helpers = (
            "clear_free_hub_pending", "clear_support_ticket_pending", "clear_quick_media_pending",
            "clear_quick_image_flow", "clear_public_image_prompt_pending",
            "clear_public_video_prompt_pending", "clear_media_aspect_pending",
            "clear_public_video_package_context", "clear_creative_motion_pending",
            "clear_cinematic_ad_pending", "clear_trend_video_flow_pending",
            "clear_trend_workflow_confirm_pending", "clear_feedback_pending",
            "clear_frame_video_state", "clear_storyboard_state",
            "clear_developing_video_pending", "clear_product_context",
            "clear_video_editor_pending", "clear_video_downloader_pending",
            "clear_video_dubbing_pending", "clear_video_finalization_state",
            "clear_video_addon_state", "clear_marketing_pending",
            "clear_shopaikey_pending_confirmations_for_user",
        )
        dependencies.update({
            "public_hub_copy": lambda _lang: hub_copy,
            "public_image_screen_copy": lambda _lang: screen_copy,
            "build_2col_keyboard": build_two_column_keyboard,
            "image_menu_v5_text": lambda _lang: "actual image menu",
            "get_user_language": lambda _uid: "vi",
            "recent_image_file_state": lambda _uid: {},
            "QUICK_MEDIA_PENDING_TTL_SECONDS": 600,
            "IMAGE_MENU_PENDING_ACTIONS": {"image_edit_wait_image"},
            "USER_PENDING": {},
            "time": SimpleNamespace(time=lambda: 100.0, perf_counter=lambda: 1.0),
            "re": re,
            "video_ai_edit_state": SimpleNamespace(clear_draft=lambda _uid: False),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
        })
        dependencies.update({name: (lambda *_args, **_kwargs: False) for name in clear_helpers})
        namespace = _load_functions(
            "menu_text_main_image", "menu_text_main_image_i18n", "main_image_keyboard",
            "image_edit_start_keyboard", "image_menu_pending_key", "set_image_menu_pending",
            "get_image_menu_pending", "clear_image_menu_pending", "clear_media_creator_pending_states",
            "localized_menu_content", "handle_menu_callback", "handle_image_tools_callback",
            **dependencies,
        )
        namespace["clear_media_creator_pending_states"] = _load_functions(
            "clear_media_creator_pending_states",
            **{key: value for key, value in namespace.items() if key.startswith("clear_")},
            video_ai_edit_state=dependencies["video_ai_edit_state"],
        )["clear_media_creator_pending_states"]

        registered = []
        namespace.update(
            tg_app=SimpleNamespace(add_handler=registered.append),
            CallbackQueryHandler=lambda callback, pattern: (callback, re.compile(pattern)),
        )
        for handler_name in ("handle_menu_callback", "handle_image_tools_callback"):
            registration = re.search(
                rf"(?m)^\s*tg_app\.add_handler\(CallbackQueryHandler\({handler_name},.*$",
                BOT_SOURCE,
            )
            self.assertIsNotNone(registration, f"missing registration for {handler_name}")
            exec(compile(registration.group(0).strip(), f"bot.py:{handler_name} registration", "exec"), namespace)
        callbacks_by_handler = {callback.__name__: (callback, pattern) for callback, pattern in registered}
        menu_callback, menu_pattern = callbacks_by_handler["handle_menu_callback"]
        image_callback, image_pattern = callbacks_by_handler["handle_image_tools_callback"]
        context = SimpleNamespace(user_data={})

        root_query = _Query(user_id, "menu|main_image")
        self.assertRegex(root_query.data, menu_pattern)
        asyncio.run(menu_callback(SimpleNamespace(callback_query=root_query), context))
        root_callbacks = [
            button.callback_data
            for row in root_query.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertEqual(((), {}), root_query.answers[0])

        ai_edit = next(
            button for row in root_query.edits[0][1]["reply_markup"].inline_keyboard
            for button in row if button.callback_data == "imgtool|edit_ai_start"
        )
        self.assertRegex(ai_edit.callback_data, image_pattern)
        edit_query = _Query(user_id, ai_edit.callback_data)
        asyncio.run(image_callback(SimpleNamespace(callback_query=edit_query), context))
        self.assertEqual([((), {})], edit_query.answers)
        self.assertEqual(
            "image_edit_wait_image",
            namespace["get_image_menu_pending"](user_id)["pending_action"],
        )
        self.assertEqual("ai_edit", namespace["get_image_menu_pending"](user_id)["edit_type"])
        back = next(
            button for row in edit_query.edits[0][1]["reply_markup"].inline_keyboard
            for button in row if button.text.startswith("⬅️")
        )
        self.assertEqual("menu|main_image", back.callback_data)
        self.assertRegex(back.callback_data, menu_pattern)
        namespace["set_image_menu_pending"](other_user_id, "image_edit_wait_image", edit_type="ai_edit")

        back_query = _Query(user_id, back.callback_data)
        asyncio.run(menu_callback(SimpleNamespace(callback_query=back_query), context))
        self.assertEqual([((), {})], back_query.answers)
        restored_callbacks = [
            button.callback_data
            for row in back_query.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertEqual(root_callbacks, restored_callbacks)
        self.assertIsNone(namespace["get_image_menu_pending"](user_id))
        self.assertEqual(
            "image_edit_wait_image",
            namespace["get_image_menu_pending"](other_user_id)["pending_action"],
        )

    def test_customer_notes_documents_landing_and_back_stay_in_the_same_ui_flow(self):
        dependencies = _main_menu_dependencies(False, [])
        labels = {
            "notes_create": "Create note", "notes_saved": "Saved notes",
            "notes_reminder": "Reminder", "notes_save_document": "Save document",
            "notes_search": "Search", "notes_delete": "Delete",
            "notes_storage": "Storage", "notes_add_storage": "Add storage",
            "notes_clean_files": "Clean files", "docs_tools": "PDF / Word tools",
            "internal_archive": "Internal archive", "back": "Back",
            "main_menu": "Main menu", "notes_docs_label": "Notes / Documents",
            "docs_pdf_to_word": "PDF to Word", "docs_image_to_pdf": "Images to PDF",
            "docs_compress_pdf": "Compress PDF", "docs_split_pdf": "Split PDF",
            "docs_merge_pdf": "Merge PDF", "docs_all_tools": "All document tools",
        }
        dependencies.update({
            "public_hub_copy": lambda _lang: labels,
            "public_command_exists": lambda _name: True,
            "storage_policy_short_lines": lambda: ["fixture storage policy"],
            "storage_addon_lines": lambda: ["fixture storage add-on"],
            "ui_text": lambda _lang, _key: "Main menu",
            "localized_start_menu_text": lambda *_args: "actual main menu",
            "localized_main_menu_keyboard": lambda *_args: _Markup([]),
            "time": SimpleNamespace(perf_counter=lambda: 1.0),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
        })
        namespace = _load_functions(
            "build_2col_keyboard", "menu_text_main_memory",
            "menu_text_main_memory_i18n", "main_memory_keyboard",
            "menu_text_main_docs", "menu_text_main_docs_i18n",
            "main_docs_keyboard", "localized_menu_content", "handle_menu_callback",
            **dependencies,
        )
        route_pattern = _registered_menu_pattern()
        context = SimpleNamespace(user_data={})

        memory_query = _Query(991127, "menu|main_memory")
        self.assertRegex(memory_query.data, route_pattern)
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=memory_query), context,
        ))
        self.assertIn("Ghi chú / Tài liệu", memory_query.edits[0][0])
        memory_markup = memory_query.edits[0][1]["reply_markup"]
        memory_back = next(
            button.callback_data for row in memory_markup.inline_keyboard for button in row
            if button.text.startswith("⬅")
        )
        self.assertEqual("menu|main", memory_back)
        docs_entry = next(
            button.callback_data for row in memory_markup.inline_keyboard for button in row
            if button.callback_data == "menu|main_docs"
        )

        docs_query = _Query(991127, docs_entry)
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=docs_query), context,
        ))
        self.assertIn("Công cụ PDF / Word", docs_query.edits[0][0])
        docs_markup = docs_query.edits[0][1]["reply_markup"]
        docs_back = next(button.callback_data for row in docs_markup.inline_keyboard
                         for button in row if button.text.startswith("⬅"))
        docs_home = next(button.callback_data for row in docs_markup.inline_keyboard
                         for button in row if button.text.startswith("🏠"))
        self.assertEqual("menu|main_memory", docs_back)
        self.assertEqual("menu|main", docs_home)
        self.assertEqual([((), {})], memory_query.answers)
        self.assertEqual([((), {})], docs_query.answers)

        returned = _Query(991127, docs_back)
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=returned), context,
        ))
        self.assertIn("Ghi chú / Tài liệu", returned.edits[0][0])
        self.assertEqual([((), {})], returned.answers)

        home_query = _Query(991127, docs_home)
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=home_query), context,
        ))
        self.assertEqual("actual main menu", home_query.edits[0][0])
        self.assertEqual([((), {})], home_query.answers)

    def test_free_tools_notes_docs_memory_prompt_back_returns_to_free_tools(self):
        user_id = 991128
        labels = {
            "free_title": "Công cụ miễn phí", "free_body": "Free tools",
            "freehub_enable_ai_chatbot": "Chatbot", "freehub_utilities": "Tiện ích",
            "freehub_meta": "Meta", "freehub_caption": "Caption", "freehub_ideas": "Ý tưởng",
            "freehub_prompts": "Prompt ảnh/video", "freehub_library": "Kho Prompt",
            "freehub_publish_package": "Gói đăng bài", "freehub_notes_docs": "Ghi chú / Tài liệu",
            "freehub_save_temp_media": "Lưu tệp tạm", "freehub_voice_subdub_script": "Kịch bản",
            "freehub_music_sfx_ideas": "Nhạc/SFX", "freehub_translation": "Dịch thuật",
            "freehub_video_downloader": "Tải video", "main_menu": "Trang chủ",
            "notes_create": "Tạo ghi chú", "notes_saved": "Ghi chú đã lưu",
            "notes_reminder": "Nhắc việc", "notes_save_document": "Lưu tài liệu",
            "notes_search": "Tìm kiếm", "notes_delete": "Xóa ghi chú",
            "notes_storage": "Dung lượng", "notes_add_storage": "Mua thêm dung lượng",
            "notes_clean_files": "Dọn tệp", "docs_tools": "Công cụ PDF / Word",
            "notes_docs_label": "Ghi chú / Tài liệu", "back": "Quay lại",
        }
        effects = []

        async def render(query, text, **kwargs):
            query.edits.append((text, kwargs))

        dependencies = _main_menu_dependencies(False, effects)
        dependencies.update({
            "public_hub_copy": lambda _lang: labels,
            "ui_text": lambda _lang, key: labels.get(key, key),
            "FREE_HUB_ENABLED": True,
            "get_user_language": lambda _uid: "vi",
            "clear_video_downloader_pending": lambda _uid: None,
            "clear_free_hub_pending": lambda _uid: None,
            "free_hub_main_text": lambda _lang: "Free Tools root fixture",
            "menu_text_main_memory_i18n": lambda _lang: "Ghi chú / Tài liệu fixture",
            "memory_can_use_full": lambda _uid: True,
            "set_memory_guided_pending": lambda uid, action: effects.append(("memory_pending", uid, action)),
            "memory_create_prompt_text": lambda _lang: "Tạo ghi chú fixture",
            "safe_edit_or_send": render,
            "time": SimpleNamespace(perf_counter=lambda: 1.0),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
        })
        namespace = _load_functions(
            "build_2col_keyboard", "free_hub_main_keyboard", "main_memory_keyboard",
            "memory_main_keyboard", "handle_memory_callback", "localized_menu_content",
            "handle_menu_callback", "handle_free_hub_callback", **dependencies,
        )
        context = SimpleNamespace(user_data={})
        patterns = {
            "handle_menu_callback": _registered_menu_pattern(),
            "handle_memory_callback": _registered_pattern("handle_memory_callback"),
            "handle_free_hub_callback": _registered_pattern("handle_free_hub_callback"),
        }

        def dispatch(handler_name, callback_data):
            self.assertRegex(callback_data, patterns[handler_name])
            query = _Query(user_id, callback_data)
            asyncio.run(namespace[handler_name](SimpleNamespace(callback_query=query), context))
            self.assertEqual([((), {})], query.answers)
            self.assertEqual(1, len(query.edits))
            return query

        freehub_markup = namespace["free_hub_main_keyboard"]("vi")
        notes_entry = next(
            button.callback_data for row in freehub_markup.inline_keyboard for button in row
            if button.text.endswith("Ghi chú / Tài liệu")
        )
        memory_root = dispatch("handle_menu_callback", notes_entry)
        self.assertIn("Ghi chú / Tài liệu fixture", memory_root.edits[0][0])
        create_entry = next(
            button.callback_data for row in memory_root.edits[0][1]["reply_markup"].inline_keyboard
            for button in row if button.callback_data == "memory|create"
        )
        prompt = dispatch("handle_memory_callback", create_entry)
        self.assertIn("Tạo ghi chú fixture", prompt.edits[0][0])
        prompt_back = prompt.edits[0][1]["reply_markup"].inline_keyboard[-1][0]
        self.assertEqual("menu|main_memory", prompt_back.callback_data)

        returned_memory = dispatch("handle_menu_callback", prompt_back.callback_data)
        memory_back = next(
            button for row in returned_memory.edits[0][1]["reply_markup"].inline_keyboard
            for button in row if button.text.startswith("⬅")
        )
        self.assertEqual("freehub|main", memory_back.callback_data)
        self.assertIn(("memory_pending", user_id, "create"), effects)
        returned_freehub = dispatch("handle_free_hub_callback", memory_back.callback_data)
        self.assertEqual("Free Tools root fixture", returned_freehub.edits[0][0])
        self.assertNotIn("memory_nav_origin", context.user_data)

    def test_admin_internal_archive_returns_to_its_notes_parent(self):
        user_id = 991130
        other_user_id = 991132
        effects = []
        dependencies = _main_menu_dependencies(True, effects)
        archive_pending = {
            user_id: {"pending_action": "preview"},
            other_user_id: {"pending_action": "preview"},
        }
        archive_clear_calls = []

        def clear_archive_pending(actor_id):
            archive_clear_calls.append(actor_id)
            return archive_pending.pop(actor_id, None) is not None

        dependencies["clear_internal_archive_pending"] = clear_archive_pending
        labels = {
            "notes_create": "Create note", "notes_saved": "Saved notes",
            "notes_reminder": "Reminder", "notes_save_document": "Save document",
            "notes_search": "Search", "notes_delete": "Delete",
            "notes_storage": "Storage", "notes_add_storage": "Add storage",
            "notes_clean_files": "Clean files", "docs_tools": "PDF / Word tools",
            "internal_archive": "Internal archive", "back": "Back",
            "main_menu": "Main menu",
        }
        dependencies.update({
            "public_hub_copy": lambda _lang: labels,
            "build_2col_keyboard": lambda buttons, *, nav_back, lang, main_label: _Markup(
                [[_Button(label, callback) for label, callback in buttons],
                 [_Button(nav_back[0], nav_back[1]), _Button(main_label, "menu|main")]]
            ),
            "INTERNAL_DOC_DEPARTMENTS": {"customers": "Customer files"},
            "internal_archive_menu_text": lambda: "Internal archive",
            "time": SimpleNamespace(perf_counter=lambda: 1.0),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
            "localized_menu_content": lambda action, _admin, _lang, _uid: (
                f"existing screen:{action}", notes_markup
            ),
        })
        namespace = _load_functions(
            "main_memory_keyboard", "internal_archive_menu_keyboard", "handle_menu_callback",
            **dependencies,
        )
        notes_markup = namespace["main_memory_keyboard"]("vi", user_id)
        root_buttons = [button for row in notes_markup.inline_keyboard for button in row]
        archive_entry = next(
            button.callback_data for button in root_buttons
            if button.callback_data == "menu|internal_archive"
        )
        self.assertIn(
            "🏢 Internal archive",
            [button.text for button in root_buttons if button.callback_data == archive_entry],
        )
        route_pattern = _registered_menu_pattern()
        self.assertRegex(archive_entry, route_pattern)

        context = SimpleNamespace(user_data={})
        archive_query = _Query(user_id, archive_entry)
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=archive_query), context,
        ))
        self.assertEqual([((), {})], archive_query.answers)
        self.assertEqual("Internal archive", archive_query.edits[0][0])
        archive_markup = archive_query.edits[0][1]["reply_markup"]
        back = next(
            button for row in archive_markup.inline_keyboard for button in row
            if button.text.startswith("⬅️")
        )
        self.assertEqual("menu|main_memory", back.callback_data)
        self.assertEqual("⬅️ Ghi chú/Tài liệu", back.text)
        self.assertRegex(back.callback_data, route_pattern)

        notes_query = _Query(user_id, back.callback_data)
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=notes_query), context,
        ))
        self.assertEqual([((), {})], notes_query.answers)
        self.assertEqual(
            [("existing screen:main_memory", {"reply_markup": notes_markup})],
            notes_query.edits,
        )
        self.assertEqual([user_id], archive_clear_calls)
        self.assertNotIn(user_id, archive_pending)
        self.assertIn(other_user_id, archive_pending)

    def test_internal_archive_preview_home_returns_to_main_and_clears_only_actor_pending(self):
        user_id = 991133
        other_user_id = 991134
        archive_pending = {
            user_id: {"pending_action": "preview"},
            other_user_id: {"pending_action": "preview"},
        }

        def clear_archive_pending(actor_id):
            return archive_pending.pop(actor_id, None) is not None

        dependencies = _main_menu_dependencies(True, [])
        dependencies.update({
            "clear_internal_archive_pending": clear_archive_pending,
            "time": SimpleNamespace(perf_counter=lambda: 1.0),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
        })
        namespace = _load_functions(
            "internal_archive_preview_keyboard", "handle_menu_callback",
            **dependencies,
        )
        preview_markup = namespace["internal_archive_preview_keyboard"]()
        home = next(
            button
            for row in preview_markup.inline_keyboard
            for button in row
            if button.callback_data == "menu|main"
        )
        self.assertEqual("🏠 Menu chính", home.text)
        self.assertRegex(home.callback_data, _registered_menu_pattern())

        query = _Query(user_id, home.callback_data)
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(user_data={}),
        ))

        self.assertEqual([((), {})], query.answers)
        self.assertEqual(
            [("existing screen:main", {"reply_markup": "existing keyboard:main"})],
            query.edits,
        )
        self.assertNotIn(user_id, archive_pending)
        self.assertIn(other_user_id, archive_pending)

    def test_internal_archive_department_search_home_returns_to_main_and_clears_only_actor_pending(self):
        user_id = 991135
        other_user_id = 991136
        effects = []
        user_pending = {}

        def clear_archive_pending(actor_id):
            return user_pending.pop(f"internal_archive:{actor_id}", None) is not None

        async def archive_render(query, text, **kwargs):
            query.edits.append((text, kwargs))

        dependencies = _main_menu_dependencies(True, effects)
        dependencies.update({
            "INTERNAL_ARCHIVE_TTL_SECONDS": 900,
            "INTERNAL_DOC_DEPARTMENTS": {"customers": "Hồ sơ khách hàng"},
            "USER_PENDING": user_pending,
            "time": SimpleNamespace(time=lambda: 1000.0, perf_counter=lambda: 1.0),
            "html": html,
            "clear_doc_tool_pending": lambda _uid: None,
            "clear_media_creator_pending_states": lambda _uid, **_kwargs: None,
            "clear_internal_archive_pending": clear_archive_pending,
            "internal_archive_menu_text": lambda: "Archive root",
            "internal_archive_menu_keyboard": lambda: _Markup([]),
            "internal_archive_department_text": lambda _department: "Department",
            "internal_archive_department_keyboard": lambda: _Markup([]),
            "safe_edit_query_message": archive_render,
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
        })
        namespace = _load_functions(
            "internal_archive_pending_key",
            "set_internal_archive_pending",
            "get_internal_archive_pending",
            "clear_internal_archive_pending",
            "handle_internal_archive_callback",
            "handle_menu_callback",
            **dependencies,
        )
        namespace["set_internal_archive_pending"](
            user_id, "department_dashboard", department="customers",
        )
        namespace["set_internal_archive_pending"](
            other_user_id, "awaiting_search_department", department="customers",
        )

        search_query = _Query(user_id, "archive|search_dept")
        asyncio.run(namespace["handle_internal_archive_callback"](
            SimpleNamespace(callback_query=search_query), SimpleNamespace(),
        ))
        self.assertEqual([((), {})], search_query.answers)
        home = next(
            button
            for row in search_query.edits[-1][1]["reply_markup"].inline_keyboard
            for button in row
            if button.callback_data == "menu|main"
        )
        self.assertEqual("🏠 Menu chính", home.text)
        self.assertRegex(home.callback_data, _registered_menu_pattern())
        self.assertEqual(
            "awaiting_search_department",
            namespace["get_internal_archive_pending"](user_id)["step"],
        )

        menu_query = _Query(user_id, home.callback_data)
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=menu_query), SimpleNamespace(user_data={}),
        ))

        self.assertEqual([((), {})], menu_query.answers)
        self.assertEqual(
            [("existing screen:main", {"reply_markup": "existing keyboard:main"})],
            menu_query.edits,
        )
        self.assertIsNone(namespace["get_internal_archive_pending"](user_id))
        self.assertEqual(
            "awaiting_search_department",
            namespace["get_internal_archive_pending"](other_user_id)["step"],
        )

    def test_memory_empty_delete_back_returns_to_notes_docs_through_registered_handlers(self):
        user_id = 991131
        effects = []
        dependencies = _main_menu_dependencies(False, effects)
        labels = {
            "notes_create": "Create note", "notes_saved": "Saved notes",
            "notes_search": "Search", "notes_delete": "Delete",
            "notes_storage": "Storage", "docs_tools": "PDF / Word tools",
            "notes_docs_label": "Notes / Documents", "common_main_menu": "Main menu",
        }
        pending = {user_id: {"pending_action": "delete_id"}}
        reads = []

        def build_keyboard(buttons, *, nav_back, lang):
            del lang
            rows = [
                [_Button(label, callback) for label, callback in buttons[index:index + 2]]
                for index in range(0, len(buttons), 2)
            ]
            rows.append([_Button(*nav_back), _Button("Main menu", "menu|main")])
            return _Markup(rows)

        async def render(query, text, **kwargs):
            query.edits.append((text, kwargs))

        def clear_pending(uid):
            return pending.pop(uid, None) is not None

        dependencies.update({
            "public_hub_copy": lambda _lang: labels,
            "build_2col_keyboard": build_keyboard,
            "time": SimpleNamespace(perf_counter=lambda: 1.0),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
            "memory_can_use_full": lambda _uid: True,
            "clear_memory_guided_pending": clear_pending,
            "memory_list_notes": lambda uid, **_kwargs: reads.append(uid) or [],
            "memory_notes_list_text": lambda *_args: "Empty notes",
            "safe_edit_or_send": render,
        })
        namespace = _load_functions(
            "memory_main_keyboard", "handle_memory_callback", "handle_menu_callback",
            **dependencies,
        )

        emitted = namespace["memory_main_keyboard"]("vi")
        delete_button = next(
            button for row in emitted.inline_keyboard for button in row
            if button.callback_data == "memory|delete_start"
        )
        memory_pattern = _registered_pattern("handle_memory_callback")
        self.assertRegex(delete_button.callback_data, memory_pattern)
        delete_query = _Query(user_id, delete_button.callback_data)
        context = SimpleNamespace(user_data={})
        asyncio.run(namespace["handle_memory_callback"](
            SimpleNamespace(callback_query=delete_query), context,
        ))
        self.assertEqual([((), {})], delete_query.answers)
        self.assertEqual([user_id], reads)
        self.assertEqual({}, pending)
        self.assertEqual("Empty notes", delete_query.edits[0][0])

        back = next(
            button for row in delete_query.edits[0][1]["reply_markup"].inline_keyboard
            for button in row if button.text.startswith("⬅")
        )
        self.assertEqual("menu|main_memory", back.callback_data)
        self.assertEqual("⬅️ Notes / Documents", back.text)
        self.assertRegex(back.callback_data, _registered_menu_pattern())

        back_query = _Query(user_id, back.callback_data)
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=back_query), context,
        ))
        self.assertEqual([((), {})], back_query.answers)
        self.assertEqual(
            [("existing screen:main_memory", {"reply_markup": "existing keyboard:main_memory"})],
            back_query.edits,
        )

    def test_saved_note_detail_cancel_and_back_preserve_saved_list_origin(self):
        user_id = 991132
        note = {
            "id": 440, "user_id": str(user_id), "title": "Fixture note",
            "content": "Fixture body", "summary": "Fixture summary", "tags": "test",
            "category": "General", "priority": "normal", "status": "active",
            "source_type": "manual", "file_id": None, "file_name": None,
            "file_size": 0, "is_archived": 0, "created_at": "2026-10-08",
            "updated_at": "2026-10-08",
        }
        labels = {
            "notes_create": "Tạo ghi chú", "notes_search": "Tìm ghi chú",
            "notes_delete": "Xóa", "notes_docs_label": "Ghi chú/Tài liệu",
            "notes_saved": "Ghi chú đã lưu", "notes_reminder": "Nhắc việc",
            "notes_save_document": "Lưu tài liệu", "notes_storage": "Lưu trữ",
            "notes_add_storage": "Thêm lưu trữ", "notes_clean_files": "Dọn tệp",
            "docs_tools": "Công cụ PDF/Word", "back": "Quay lại", "main_menu": "Trang chủ",
            "memory_detail_title": "Chi tiết ghi chú", "memory_list_title": "Ghi chú đã lưu",
            "memory_delete_confirm": "Xác nhận xóa", "memory_delete_confirm_body": "Xác nhận?",
            "common_cancel": "Hủy", "common_main_menu": "Trang chủ",
            "memory_field_title": "Tiêu đề", "memory_field_category": "Danh mục",
            "memory_field_priority": "Ưu tiên", "memory_field_tags": "Nhãn",
            "memory_field_source": "Nguồn", "memory_field_created": "Ngày tạo",
            "memory_field_updated": "Cập nhật", "memory_field_content": "Nội dung",
            "memory_field_summary": "Tóm tắt", "memory_empty": "Chưa có ghi chú.",
        }
        rendered = []
        database_calls = []

        async def safe_render(query, text, **kwargs):
            query.edits.append((text, kwargs))

        def memory_fetch(owner_id, note_id):
            return dict(note) if str(owner_id) == str(user_id) and int(note_id) == note["id"] else None

        def forbidden_db_connect():
            database_calls.append("connect")
            raise AssertionError("saved-list navigation must not open the production database")

        namespace = _load_functions(
            "build_2col_keyboard", "main_memory_keyboard", "memory_notes_list_text", "memory_notes_list_keyboard",
            "memory_note_detail_text", "memory_note_detail_keyboard", "memory_delete_confirm_text",
            "memory_delete_confirm_keyboard", "handle_memory_callback",
            InlineKeyboardButton=_Button, InlineKeyboardMarkup=_Markup, html=html,
            time=SimpleNamespace(time=lambda: 1000.0, time_ns=lambda: 123456789),
            ui_text=lambda _lang, _key: "Trang chủ",
            normalize_user_language=lambda lang: lang or "vi",
            is_admin_user=lambda _uid: False,
            public_hub_copy=lambda _lang: labels,
            get_user_language=lambda _uid: "vi", memory_can_use_full=lambda _uid: True,
            clear_memory_guided_pending=lambda _uid: False,
            set_memory_guided_pending=lambda _uid, _action, **_fields: None,
            memory_list_notes=lambda _uid, **_kwargs: [dict(note)],
            memory_fetch_note=memory_fetch,
            memory_delete_confirm_text=lambda _note, _lang: "Confirm delete fixture",
            safe_edit_or_send=safe_render,
            safe_int=lambda value, default=0: int(value) if str(value).isdigit() else default,
            memory_access_message=lambda: "Denied",
            memory_main_keyboard=lambda *_args: _Markup([]),
            memory_record_event=lambda *_args, **_kwargs: rendered.append("record-event"),
            db_connect=forbidden_db_connect,
        )
        registered_pattern = _registered_pattern("handle_memory_callback")
        context = SimpleNamespace(user_data={})

        def dispatch(callback_data):
            self.assertRegex(callback_data, registered_pattern)
            query = _Query(user_id, callback_data)
            asyncio.run(namespace["handle_memory_callback"](
                SimpleNamespace(callback_query=query), context,
            ))
            self.assertEqual([((), {})], query.answers)
            return query

        root_markup = namespace["main_memory_keyboard"]("vi", user_id)
        saved_notes_button = next(
            button for row in root_markup.inline_keyboard for button in row
            if button.callback_data == "memory|list"
        )
        list_query = dispatch(saved_notes_button.callback_data)
        list_markup = list_query.edits[0][1]["reply_markup"]
        view = next(
            button for row in list_markup.inline_keyboard for button in row
            if button.text.startswith("👁")
        )
        self.assertEqual("memory|view|440|list", view.callback_data)

        detail_query = dispatch(view.callback_data)
        detail_markup = detail_query.edits[0][1]["reply_markup"]
        detail_back = next(
            button for row in detail_markup.inline_keyboard for button in row
            if button.text.startswith("⬅")
        )
        delete = next(
            button for row in detail_markup.inline_keyboard for button in row
            if button.text.startswith("🗑")
        )
        self.assertEqual("memory|list", detail_back.callback_data)
        self.assertEqual("memory|delete|440|list", delete.callback_data)

        confirm_query = dispatch(delete.callback_data)
        confirm_markup = confirm_query.edits[0][1]["reply_markup"]
        cancel = next(
            button for row in confirm_markup.inline_keyboard for button in row
            if button.text.startswith("❌")
        )
        self.assertEqual("memory|view|440|list", cancel.callback_data)

        restored_detail = dispatch(cancel.callback_data)
        restored_back = next(
            button for row in restored_detail.edits[0][1]["reply_markup"].inline_keyboard
            for button in row if button.text.startswith("⬅")
        )
        self.assertEqual("memory|list", restored_back.callback_data)

        restored_list = dispatch(restored_back.callback_data)
        self.assertIn("Fixture note", restored_list.edits[0][0])
        self.assertEqual([], database_calls)
        self.assertEqual([], rendered)

    def test_memory_delete_picker_emits_a_cancel_route_to_its_parent(self):
        user_id = 991133
        note = {"id": 441, "user_id": str(user_id), "title": "Fixture note"}
        labels = {
            "notes_create": "Tạo ghi chú", "notes_saved": "Ghi chú đã lưu",
            "notes_reminder": "Nhắc việc", "notes_save_document": "Lưu tài liệu",
            "notes_search": "Tìm ghi chú", "notes_delete": "Xóa",
            "notes_storage": "Lưu trữ", "notes_add_storage": "Thêm lưu trữ",
            "notes_clean_files": "Dọn tệp", "docs_tools": "Công cụ PDF/Word",
            "back": "Quay lại", "notes_docs_label": "Ghi chú/Tài liệu",
            "memory_list_title": "Ghi chú đã lưu", "common_cancel": "Hủy",
            "common_main_menu": "Trang chủ", "main_menu": "Trang chủ",
        }
        pending_states = []
        database_calls = []

        def forbidden_db_connect():
            database_calls.append("connect")
            raise AssertionError("cancel navigation must not connect to the production database")

        def fetch_owned_note(owner_id, note_id):
            return dict(note) if str(owner_id) == str(user_id) and int(note_id) == note["id"] else None

        async def render(query, text, **kwargs):
            query.edits.append((text, kwargs))

        namespace = _load_functions(
            "build_2col_keyboard", "main_memory_keyboard", "memory_notes_list_keyboard",
            "memory_delete_confirm_keyboard", "handle_memory_callback",
            InlineKeyboardButton=_Button, InlineKeyboardMarkup=_Markup,
            normalize_user_language=lambda lang: lang or "vi",
            public_hub_copy=lambda _lang: labels,
            ui_text=lambda _lang, _key: "Trang chủ",
            is_admin_user=lambda _uid: False,
            get_user_language=lambda _uid: "vi", memory_can_use_full=lambda _uid: True,
            clear_memory_guided_pending=lambda _uid: False,
            set_memory_guided_pending=lambda uid, action, **_fields: pending_states.append((uid, action)),
            time=SimpleNamespace(time=lambda: 1000.0, time_ns=lambda: 123456789),
            memory_list_notes=lambda _uid, **_kwargs: [dict(note)],
            memory_format_note_item_with_time=lambda item: f"#{item['id']} {item['title']}",
            memory_fetch_note=fetch_owned_note,
            memory_delete_confirm_text=lambda *_args: "Confirm delete fixture",
            safe_edit_or_send=render,
            safe_int=lambda value, default=0: int(value) if str(value).isdigit() else default,
            memory_main_keyboard=lambda *_args: _Markup([]),
            db_connect=forbidden_db_connect,
        )
        route_pattern = _registered_pattern("handle_memory_callback")
        context = SimpleNamespace(user_data={})

        def dispatch(callback_data):
            self.assertRegex(callback_data, route_pattern)
            query = _Query(user_id, callback_data)
            asyncio.run(namespace["handle_memory_callback"](
                SimpleNamespace(callback_query=query), context,
            ))
            self.assertEqual([((), {})], query.answers)
            return query

        root_markup = namespace["main_memory_keyboard"]("vi", user_id)
        delete_start = next(
            button for row in root_markup.inline_keyboard for button in row
            if button.callback_data == "memory|delete_start"
        )
        picker_query = dispatch(delete_start.callback_data)
        self.assertEqual([(user_id, "delete_id")], pending_states)
        delete_note = next(
            button for row in picker_query.edits[0][1]["reply_markup"].inline_keyboard
            for button in row if button.text.startswith("🗑")
        )
        self.assertEqual("memory|delete|441|delete_start", delete_note.callback_data)

        confirm_query = dispatch(delete_note.callback_data)
        confirm_markup = confirm_query.edits[0][1]["reply_markup"]
        cancel = next(
            button for row in confirm_markup.inline_keyboard for button in row
            if button.text.startswith("❌")
        )
        self.assertEqual("memory|delete_start", cancel.callback_data)
        self.assertNotIn(
            "memory|list",
            [button.callback_data for row in confirm_markup.inline_keyboard for button in row],
        )

        restored_picker = dispatch(cancel.callback_data)
        restored_delete = next(
            button for row in restored_picker.edits[0][1]["reply_markup"].inline_keyboard
            for button in row if button.text.startswith("🗑")
        )
        self.assertEqual("memory|delete|441|delete_start", restored_delete.callback_data)
        self.assertEqual(
            [(user_id, "delete_id"), (user_id, "delete_confirm"), (user_id, "delete_id")],
            pending_states,
        )
        self.assertEqual([], database_calls)

    def test_stale_memory_delete_confirmation_cannot_archive_reconfirmed_note(self):
        user_id = 991137
        note = {
            "id": 445, "user_id": str(user_id), "title": "Fixture note",
            "content": "Fixture body", "summary": "Fixture summary", "tags": "test",
            "category": "General", "priority": "normal", "status": "active",
            "source_type": "manual", "file_id": None, "file_name": None,
            "file_size": 0, "is_archived": 0, "created_at": "2026-10-08",
            "updated_at": "2026-10-08",
        }
        notes = {note["id"]: dict(note)}
        archive_updates = []
        recorded_events = []
        confirm_tokens = iter((123456789, 987654321))
        labels = {
            "notes_create": "Tạo ghi chú", "notes_saved": "Ghi chú đã lưu",
            "notes_reminder": "Nhắc việc", "notes_save_document": "Lưu tài liệu",
            "notes_search": "Tìm ghi chú", "notes_delete": "Xóa",
            "notes_storage": "Lưu trữ", "notes_add_storage": "Thêm lưu trữ",
            "notes_clean_files": "Dọn tệp", "docs_tools": "Công cụ PDF/Word",
            "back": "Quay lại", "notes_docs_label": "Ghi chú/Tài liệu",
            "memory_list_title": "Ghi chú đã lưu", "memory_detail_title": "Chi tiết",
            "memory_delete_confirm": "Xác nhận xóa", "memory_delete_confirm_body": "Không thể hoàn tác",
            "common_cancel": "Hủy", "common_main_menu": "Trang chủ", "main_menu": "Trang chủ",
        }

        def build_keyboard(buttons, *, nav_back=None, nav_main=False, lang="vi", main_label=None):
            flat = [_Button(label, callback) for label, callback in buttons]
            rows = [flat[index:index + 2] for index in range(0, len(flat), 2)]
            if nav_back:
                rows.append([_Button(*nav_back)])
            if nav_main:
                rows.append([_Button(main_label or "Trang chủ", "menu|main")])
            return _Markup(rows)

        class MemoryConnection:
            def execute(self, sql, params):
                archive_updates.append((sql, params))
                _updated_at, note_id, owner_id = params
                row = notes.get(int(note_id))
                if row and row["user_id"] == str(owner_id):
                    row["is_archived"] = 1
                    row["status"] = "archived"
                return SimpleNamespace(rowcount=1)

            def commit(self):
                return None

            def close(self):
                return None

        def list_owned_notes(owner_id, limit=10, *_args, **_kwargs):
            return [
                dict(item) for item in notes.values()
                if item["user_id"] == str(owner_id) and not item["is_archived"]
            ][:limit]

        def fetch_owned_note(owner_id, note_id):
            row = notes.get(int(note_id))
            if not row or row["user_id"] != str(owner_id) or row["is_archived"]:
                return {}
            return dict(row)

        async def render(query, text, **kwargs):
            query.edits.append((text, kwargs))

        namespace = _load_functions(
            "memory_guided_pending_key", "set_memory_guided_pending", "get_memory_guided_pending",
            "clear_memory_guided_pending", "main_memory_keyboard", "memory_notes_list_keyboard",
            "memory_delete_confirm_keyboard", "handle_memory_callback",
            InlineKeyboardButton=_Button, InlineKeyboardMarkup=_Markup,
            normalize_user_language=lambda lang: lang or "vi",
            public_hub_copy=lambda _lang: labels,
            build_2col_keyboard=build_keyboard,
            ui_text=lambda _lang, _key: "Trang chủ",
            is_admin_user=lambda _uid: False,
            get_user_language=lambda _uid: "vi", memory_can_use_full=lambda _uid: True,
            USER_PENDING={}, QUICK_MEDIA_PENDING_TTL_SECONDS=900,
            time=SimpleNamespace(time=lambda: 1000.0, time_ns=lambda: next(confirm_tokens)),
            _short_pending_text=lambda value, _limit: str(value),
            memory_list_notes=list_owned_notes,
            memory_format_note_item_with_time=lambda item: f"#{item['id']} {item['title']}",
            memory_fetch_note=fetch_owned_note,
            memory_delete_confirm_text=lambda *_args: "Confirm delete fixture",
            safe_edit_or_send=render,
            safe_int=lambda value, default=0: int(value) if str(value).isdigit() else default,
            memory_main_keyboard=lambda *_args: _Markup([]),
            menu_text_main_memory_i18n=lambda _lang: "Memory home fixture",
            db_connect=lambda: MemoryConnection(), now_text=lambda: "fixture-time",
            memory_record_event=lambda *_args, **_kwargs: recorded_events.append("recorded"),
        )
        route_pattern = _registered_pattern("handle_memory_callback")
        context = SimpleNamespace(user_data={})
        query_sequence = [0]

        def dispatch(callback_data):
            self.assertRegex(callback_data, route_pattern)
            query = _Query(user_id, callback_data)
            query.id = f"memory-test-{query_sequence[0]}"
            query_sequence[0] += 1
            _run_no_io(namespace["handle_memory_callback"](
                SimpleNamespace(callback_query=query), context,
            ))
            self.assertEqual([((), {})], query.answers)
            return query

        root = namespace["main_memory_keyboard"]("vi")
        delete_start = next(
            button.callback_data for row in root.inline_keyboard for button in row
            if button.callback_data == "memory|delete_start"
        )
        picker = dispatch(delete_start).edits[0][1]["reply_markup"]
        note_delete = next(
            button.callback_data for row in picker.inline_keyboard for button in row
            if button.text.startswith("🗑")
        )
        confirm_markup = dispatch(note_delete).edits[0][1]["reply_markup"]
        stale_confirm = next(
            button.callback_data for row in confirm_markup.inline_keyboard for button in row
            if button.text.startswith("✅")
        )
        cancel = next(
            button.callback_data for row in confirm_markup.inline_keyboard for button in row
            if button.text.startswith("❌")
        )
        dispatch(cancel)
        fresh_markup = dispatch(note_delete).edits[0][1]["reply_markup"]
        fresh_confirm = next(
            button.callback_data for row in fresh_markup.inline_keyboard for button in row
            if button.text.startswith("✅")
        )
        self.assertNotEqual(stale_confirm, fresh_confirm)

        dispatch(f"memory|delete_yes|{note['id']}")
        dispatch(stale_confirm)

        self.assertEqual("active", notes[note["id"]]["status"])
        self.assertEqual(0, notes[note["id"]]["is_archived"])
        self.assertEqual([], archive_updates)
        self.assertEqual([], recorded_events)

        class _YieldAfterAck:
            def __await__(self):
                yield "ack-yield"
                return None

        concurrent_queries = []
        concurrent_handlers = []
        for _ in range(2):
            query = _Query(user_id, fresh_confirm)
            query.id = f"memory-concurrent-{query_sequence[0]}"
            query_sequence[0] += 1

            async def delayed_answer(*args, _query=query, **kwargs):
                _query.answers.append((args, kwargs))
                await _YieldAfterAck()

            query.answer = delayed_answer
            self.assertRegex(query.data, route_pattern)
            concurrent_queries.append(query)
            concurrent_handlers.append(namespace["handle_memory_callback"](
                SimpleNamespace(callback_query=query), context,
            ))

        # Suspend both emitted confirmations at ACK, then resume each callback.
        # This deterministic fixture scheduler avoids Windows asyncio startup/I/O.
        for coroutine in concurrent_handlers:
            self.assertEqual(coroutine.send(None), "ack-yield")
        for coroutine in concurrent_handlers:
            with self.assertRaises(StopIteration):
                coroutine.send(None)

        self.assertEqual([[((), {})], [((), {})]], [query.answers for query in concurrent_queries])
        self.assertEqual(1, sum("✅ Đã xóa/ẩn" in query.edits[0][0] for query in concurrent_queries))
        self.assertEqual(1, sum("hết hạn hoặc không còn hợp lệ" in query.edits[0][0] for query in concurrent_queries))
        self.assertEqual("archived", notes[note["id"]]["status"])
        self.assertEqual(1, len(archive_updates))
        self.assertEqual(["recorded"], recorded_events)

        confirmed_query = dispatch(fresh_confirm)

        self.assertEqual("archived", notes[note["id"]]["status"])
        self.assertEqual(1, notes[note["id"]]["is_archived"])
        self.assertEqual(1, len(archive_updates))
        self.assertEqual(["recorded"], recorded_events)

        duplicate_query = dispatch(fresh_confirm)
        self.assertIsNot(confirmed_query, duplicate_query)
        self.assertNotEqual(confirmed_query.id, duplicate_query.id)
        self.assertEqual(
            "⚠️ Xác nhận xóa đã hết hạn hoặc không còn hợp lệ. Vui lòng chọn lại.",
            duplicate_query.edits[0][0],
        )
        self.assertEqual(1, len(archive_updates))
        self.assertEqual(["recorded"], recorded_events)

    def test_memory_search_result_detail_back_restores_the_same_search_results(self):
        user_id = 991134
        note = {
            "id": 442, "user_id": str(user_id), "title": "Urgent fixture",
            "content": "urgent body", "summary": "urgent summary", "tags": "urgent",
            "category": "work", "priority": "normal", "status": "active",
            "source_type": "manual", "created_at": "2026-10-08", "updated_at": "2026-10-08",
        }
        labels = {
            "notes_create": "Tạo ghi chú", "notes_saved": "Ghi chú đã lưu",
            "notes_search": "Tìm ghi chú", "notes_delete": "Xóa",
            "notes_storage": "Lưu trữ", "docs_tools": "Công cụ PDF/Word",
            "notes_docs_label": "Ghi chú/Tài liệu", "memory_search_title": "Tìm ghi chú",
            "memory_search_body": "Gửi từ khóa", "memory_list_title": "Ghi chú đã lưu",
            "memory_empty": "Chưa có ghi chú", "memory_field_category": "Nhóm",
            "memory_field_priority": "Ưu tiên", "memory_field_updated": "Cập nhật",
            "memory_detail_title": "Chi tiết ghi chú", "memory_field_title": "Tiêu đề",
            "memory_field_tags": "Thẻ", "memory_field_source": "Nguồn",
            "memory_field_created": "Tạo lúc", "memory_field_content": "Nội dung",
            "memory_delete_confirm": "Xác nhận xóa", "memory_delete_confirm_body": "Không thể hoàn tác",
            "common_cancel": "Hủy",
            "common_main_menu": "Trang chủ", "main_menu": "Trang chủ",
        }
        pending = {}
        result_reads = []
        note_reads = []
        replied = []

        def set_pending(owner_id, action, **fields):
            pending[owner_id] = {"pending_action": action, **fields}

        def clear_pending(owner_id):
            pending.pop(owner_id, None)

        async def render(query, text, **kwargs):
            query.edits.append((text, kwargs))

        async def allow_memory_access(_update):
            return True

        def list_notes(owner_id, where_sql="", params=(), limit=10):
            result_reads.append((owner_id, where_sql, params, limit))
            if str(owner_id) != str(user_id):
                return []
            if "LIKE" in where_sql or "id IN" in where_sql:
                return [dict(note)]
            return []

        def fetch_note(owner_id, note_id):
            note_reads.append((owner_id, note_id))
            return dict(note) if str(owner_id) == str(user_id) and int(note_id) == note["id"] else None

        namespace = _load_functions(
            "build_2col_keyboard", "memory_main_keyboard", "memory_search_prompt_text",
            "memory_notes_list_text", "memory_notes_list_keyboard", "memory_note_detail_text",
            "memory_note_detail_keyboard", "memory_delete_confirm_keyboard",
            "handle_memory_callback", "handle_memory_pending_text",
            InlineKeyboardButton=_Button, InlineKeyboardMarkup=_Markup, html=html,
            time=SimpleNamespace(time=lambda: 1_797_000_000.0, time_ns=lambda: 1_797_000_000_000_000_000),
            QUICK_MEDIA_PENDING_TTL_SECONDS=900,
            normalize_user_language=lambda lang: lang or "vi", public_hub_copy=lambda _lang: labels,
            ui_text=lambda _lang, key: labels.get(key, key),
            get_user_language=lambda _uid: "vi", is_admin_user=lambda _uid: False,
            memory_can_use_full=lambda _uid: True, memory_access_message=lambda: "Denied",
            set_memory_guided_pending=set_pending, clear_memory_guided_pending=clear_pending,
            get_memory_guided_pending=lambda owner_id: pending.get(owner_id),
            memory_require_access=allow_memory_access,
            memory_list_notes=list_notes,
            memory_fetch_note=fetch_note,
            memory_delete_confirm_text=lambda *_args: "Confirm delete fixture",
            safe_edit_or_send=render, safe_int=lambda value, default=0: int(value) if str(value).isdigit() else default,
            menu_text_main_memory_i18n=lambda _lang: "Memory root fixture",
            main_memory_keyboard=lambda *_args: _Markup([]),
        )
        context = SimpleNamespace(user_data={})
        route_pattern = _registered_pattern("handle_memory_callback")

        def dispatch(callback_data):
            self.assertRegex(callback_data, route_pattern)
            query = _Query(user_id, callback_data)
            asyncio.run(namespace["handle_memory_callback"](
                SimpleNamespace(callback_query=query), context,
            ))
            self.assertEqual([((), {})], query.answers)
            return query

        root_markup = namespace["memory_main_keyboard"]("vi")
        search = next(
            button for row in root_markup.inline_keyboard for button in row
            if button.callback_data == "memory|search"
        )
        dispatch(search.callback_data)

        class SearchMessage:
            text = "urgent"

            async def reply_text(self, text, **kwargs):
                replied.append((text, kwargs))

        update = SimpleNamespace(
            message=SearchMessage(), effective_user=SimpleNamespace(id=user_id),
        )
        self.assertTrue(asyncio.run(namespace["handle_memory_pending_text"](
            update, context,
        )))
        search_text, search_kwargs = replied[0]
        self.assertIn("Kết quả tìm: urgent", search_text)
        result_markup = search_kwargs["reply_markup"]
        open_note = next(
            button for row in result_markup.inline_keyboard for button in row
            if button.text.startswith("👁")
        )
        self.assertRegex(open_note.callback_data, re.compile(r"^memory\|view\|442\|search\|[0-9]+$"))
        self.assertLessEqual(len(open_note.callback_data.encode("utf-8")), 64)

        detail = dispatch(open_note.callback_data)
        delete = next(
            button for row in detail.edits[0][1]["reply_markup"].inline_keyboard
            for button in row if button.text.startswith("🗑")
        )
        self.assertRegex(delete.callback_data, re.compile(r"^memory\|delete\|442\|search\|[0-9]+$"))
        self.assertLessEqual(len(delete.callback_data.encode("utf-8")), 64)
        confirmation = dispatch(delete.callback_data)
        cancel = next(
            button for row in confirmation.edits[0][1]["reply_markup"].inline_keyboard
            for button in row if button.text.startswith("❌")
        )
        self.assertRegex(cancel.callback_data, re.compile(r"^memory\|view\|442\|search\|[0-9]+$"))
        self.assertLessEqual(len(cancel.callback_data.encode("utf-8")), 64)
        detail = dispatch(cancel.callback_data)
        back = next(
            button for row in detail.edits[0][1]["reply_markup"].inline_keyboard
            for button in row if button.text.startswith("⬅")
        )
        self.assertRegex(back.callback_data, re.compile(r"^memory\|search_results\|[0-9]+$"))
        self.assertLessEqual(len(back.callback_data.encode("utf-8")), 64)
        restored = dispatch(back.callback_data)
        self.assertEqual(search_text, restored.edits[0][0])
        self.assertEqual({}, pending)
        self.assertGreaterEqual(len(result_reads), 2)

        original_snapshot = dict(context.user_data["memory_search_results"])
        for reason, changed_fields in (
            ("replaced", {"token": "new-session"}),
            ("expired", {"created_at_ts": 1_797_000_000.0 - 901}),
            ("not-in-results", {"note_ids": [999]}),
            ("invalid-timestamp", {"created_at_ts": "invalid"}),
        ):
            context.user_data["memory_search_results"] = {**original_snapshot, **changed_fields}
            for callback in (open_note.callback_data, delete.callback_data):
                with self.subTest(reason=reason, callback=callback):
                    set_pending(user_id, "create")
                    before_pending = dict(pending)
                    reads_before = len(note_reads)
                    rejected = dispatch(callback)
                    self.assertEqual("Memory root fixture", rejected.edits[0][0])
                    self.assertEqual(reads_before, len(note_reads))
                    self.assertEqual(before_pending, pending)

        context.user_data["memory_search_results"] = original_snapshot
        set_pending(user_id, "create")
        set_pending(user_id + 1, "search")
        with self.subTest("valid-back-releases-only-owner-draft"):
            valid_back = dispatch(back.callback_data)
            self.assertEqual(search_text, valid_back.edits[0][0])
            self.assertNotIn(user_id, pending)
            self.assertEqual({"pending_action": "search"}, pending[user_id + 1])

        stale = dispatch("memory|search_results|1")
        self.assertEqual("Memory root fixture", stale.edits[0][0])
        self.assertNotIn("urgent", stale.edits[0][0])

        foreign_context = SimpleNamespace(user_data={})
        foreign_query = _Query(user_id + 1, back.callback_data)
        reads_before_foreign = len(result_reads)
        asyncio.run(namespace["handle_memory_callback"](
            SimpleNamespace(callback_query=foreign_query), foreign_context,
        ))
        self.assertEqual([((), {})], foreign_query.answers)
        self.assertEqual("Memory root fixture", foreign_query.edits[0][0])
        self.assertEqual(reads_before_foreign, len(result_reads))
        for callback in (open_note.callback_data, delete.callback_data):
            with self.subTest(foreign_callback=callback):
                foreign_query = _Query(user_id + 1, callback)
                reads_before = len(note_reads)
                before_pending = dict(pending)
                asyncio.run(namespace["handle_memory_callback"](
                    SimpleNamespace(callback_query=foreign_query), foreign_context,
                ))
                self.assertEqual("Memory root fixture", foreign_query.edits[0][0])
                self.assertEqual(reads_before, len(note_reads))
                self.assertEqual(before_pending, pending)

        context.user_data["memory_search_results"]["created_at_ts"] = 1_797_000_000.0 - 901
        reads_before_expiry = len(result_reads)
        expired = dispatch(back.callback_data)
        self.assertEqual("Memory root fixture", expired.edits[0][0])
        self.assertEqual(reads_before_expiry, len(result_reads))

        max_sqlite_id = 9_223_372_036_854_775_807
        long_token = "9" * 19
        long_view = namespace["memory_notes_list_keyboard"](
            [{"id": max_sqlite_id}], "vi", search_token=long_token,
        ).inline_keyboard[0][0].callback_data
        long_delete = namespace["memory_notes_list_keyboard"](
            [{"id": max_sqlite_id}], "vi", delete_mode=True, search_token=long_token,
        ).inline_keyboard[0][0].callback_data
        self.assertLessEqual(len(long_view.encode("utf-8")), 64)
        self.assertLessEqual(len(long_delete.encode("utf-8")), 64)

    def test_free_tools_prompt_picker_back_and_home_round_trip_through_registered_handlers(self):
        user_id = 991135
        labels = {
            "free_title": "Công cụ miễn phí", "free_body": "Free tools",
            "freehub_enable_ai_chatbot": "Chatbot", "freehub_utilities": "Tiện ích",
            "freehub_meta": "Meta prompt", "freehub_caption": "Caption",
            "freehub_ideas": "Ý tưởng", "freehub_prompts": "Thư viện prompt",
            "freehub_library": "Thư viện", "freehub_publish_package": "Gói đăng bài",
            "freehub_notes_docs": "Ghi chú", "freehub_save_temp_media": "Lưu tệp tạm",
            "freehub_voice_subdub_script": "Kịch bản giọng nói",
            "freehub_music_sfx_ideas": "Nhạc/SFX", "freehub_translation": "Dịch",
            "freehub_video_downloader": "Tải video", "main_menu": "Trang chủ",
            "freehub_back": "Quay lại", "freehub_use_suggestion_1": "Dùng 1",
            "freehub_use_suggestion_2": "Dùng 2", "freehub_use_suggestion_3": "Dùng 3",
            "freehub_more_suggestions": "Thêm gợi ý", "freehub_custom_input": "Tự nhập",
        }
        root_dependencies = _main_menu_dependencies(False, [])
        root = _load_functions(
            "localized_main_menu_keyboard", **root_dependencies,
        )["localized_main_menu_keyboard"](False, "vi")
        freehub_entry = next(
            button.callback_data for row in root.inline_keyboard for button in row
            if button.callback_data == "freehub|main"
        )
        self.assertRegex(freehub_entry, _registered_pattern("handle_free_hub_callback"))

        pending = {}
        pending_events = []
        replies = []

        async def render(query, text, **kwargs):
            query.edits.append((text, kwargs))

        def clear_free_hub(owner_id):
            pending.pop(owner_id, None)
            pending_events.append(("clear", owner_id))

        hub = _load_functions(
            "build_2col_keyboard", "free_hub_main_keyboard", "free_hub_suggestions_keyboard",
            "handle_free_hub_callback",
            InlineKeyboardButton=_Button, InlineKeyboardMarkup=_Markup,
            normalize_user_language=lambda lang: lang or "vi",
            public_hub_copy=lambda _lang: labels,
            ui_text=lambda _lang, key: labels.get(key, key),
            FREE_HUB_ENABLED=True, get_user_language=lambda _uid: "vi",
            clear_video_downloader_pending=lambda owner_id: pending_events.append(("clear_downloader", owner_id)),
            clear_free_hub_pending=clear_free_hub,
            free_hub_main_text=lambda _lang: "Công cụ miễn phí fixture",
            free_hub_quota_payload=lambda _uid: {"allowed": True},
            free_hub_suggestion_items=lambda _task, _offset: ["fixture suggestion"],
            set_free_hub_pending=lambda owner_id, step, **fields: pending.update(
                {owner_id: {"step": step, **fields}}
            ) or pending_events.append(("set", owner_id, step)),
            free_hub_suggestions_text=lambda *_args: "Prompt picker fixture",
            safe_edit_or_send=render,
        )
        hub_context = SimpleNamespace(user_data={})
        hub_pattern = _registered_pattern("handle_free_hub_callback")

        def dispatch_hub(callback_data):
            self.assertRegex(callback_data, hub_pattern)
            query = _Query(user_id, callback_data)
            asyncio.run(hub["handle_free_hub_callback"](
                SimpleNamespace(callback_query=query), hub_context,
            ))
            self.assertEqual([((), {})], query.answers)
            return query

        opened = dispatch_hub(freehub_entry)
        self.assertEqual("Công cụ miễn phí fixture", opened.edits[0][0])
        main_markup = opened.edits[0][1]["reply_markup"]
        pending_events.clear()
        prompt_entry = next(
            button.callback_data for row in main_markup.inline_keyboard for button in row
            if button.callback_data == "freehub|prompts"
        )
        prompt_screen = dispatch_hub(prompt_entry)
        self.assertEqual("Prompt picker fixture", prompt_screen.edits[0][0])
        self.assertEqual("suggestions", pending[user_id]["step"])
        prompt_markup = prompt_screen.edits[0][1]["reply_markup"]
        prompt_back, home = prompt_markup.inline_keyboard[-1]
        self.assertEqual("freehub|main", prompt_back.callback_data)
        self.assertEqual("menu|main", home.callback_data)

        returned_hub = dispatch_hub(prompt_back.callback_data)
        self.assertEqual("Công cụ miễn phí fixture", returned_hub.edits[0][0])
        self.assertNotIn(user_id, pending)
        self.assertEqual("menu|main", home.callback_data)

        menu_dependencies = _main_menu_dependencies(False, [])
        menu_dependencies.update({
            "time": SimpleNamespace(perf_counter=lambda: 1.0),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
            "localized_menu_content": lambda action, *_args: (f"Main fixture:{action}", _Markup([])),
        })
        menu = _load_functions("handle_menu_callback", **menu_dependencies)
        self.assertRegex(home.callback_data, _registered_menu_pattern())
        home_query = _Query(user_id, home.callback_data)
        asyncio.run(menu["handle_menu_callback"](
            SimpleNamespace(callback_query=home_query), SimpleNamespace(user_data={}),
        ))
        self.assertEqual([((), {})], home_query.answers)
        self.assertEqual("Main fixture:main", home_query.edits[0][0])
        self.assertEqual([("set", user_id, "suggestions"), ("clear_downloader", user_id), ("clear", user_id)], pending_events)

    def test_free_tools_prompt_library_back_stack_restores_parent_and_exact_results(self):
        user_id = 991136
        labels = {
            "free_title": "Công cụ miễn phí", "free_body": "Free tools",
            "freehub_enable_ai_chatbot": "Chatbot", "freehub_utilities": "Tiện ích",
            "freehub_meta": "Meta", "freehub_caption": "Caption", "freehub_ideas": "Ý tưởng",
            "freehub_prompts": "Prompt ảnh/video", "freehub_library": "Kho Prompt",
            "freehub_library_title": "Kho Prompt", "freehub_library_body": "Chọn danh mục",
            "freehub_publish_package": "Gói đăng bài", "freehub_notes_docs": "Ghi chú",
            "freehub_save_temp_media": "Lưu tệp tạm", "freehub_voice_subdub_script": "Kịch bản",
            "freehub_music_sfx_ideas": "Nhạc/SFX", "freehub_translation": "Dịch",
            "freehub_video_downloader": "Tải video", "freehub_main": "Công cụ miễn phí",
            "free_tools_label": "Công cụ miễn phí", "freehub_open_utilities_title": "Tiện ích",
            "freehub_open_utilities_body": "Chọn tiện ích", "freehub_util_rate": "Tỷ giá",
            "freehub_util_weather": "Thời tiết", "freehub_util_qr": "QR", "freehub_util_avatar": "Avatar",
            "freehub_choose_1": "Dùng 1", "freehub_choose_2": "Dùng 2",
            "freehub_choose_3": "Dùng 3", "freehub_more": "Thêm gợi ý",
            "freehub_choose_template": "Chọn mẫu", "freehub_prompts_title": "Prompt video",
            "freehub_result_to_prompts": "Prompt ảnh", "freehub_meta_title": "Meta",
            "freehub_result_to_caption": "Caption", "freehub_music_sfx_ideas": "Nhạc/SFX",
            "freehub_sales": "Shop", "freehub_realistic": "Mỹ phẩm", "main_menu": "Trang chủ",
            "freehub_save_template": "Lưu mẫu", "freehub_use_product": "Dùng cho sản phẩm",
            "freehub_use_meta": "Dùng cho Meta", "freehub_caption_from_prompt": "Tạo caption",
            "freehub_result_title": "Kết quả", "freehub_result_variant": "Biến thể",
            "freehub_result_edit": "Sửa", "freehub_result_save": "Lưu", "freehub_result_copy": "Sao chép",
            "freehub_result_publish": "Gói đăng bài", "freehub_service_advice": "Dịch vụ",
            "freehub_input_free": "Miễn phí",
        }
        root_dependencies = _main_menu_dependencies(False, [])
        root = _load_functions(
            "localized_main_menu_keyboard", **root_dependencies,
        )["localized_main_menu_keyboard"](False, "vi")
        freehub_entry = root.inline_keyboard[0][0].callback_data
        self.assertEqual("freehub|main", freehub_entry)

        other_user_id = user_id + 1
        pending = {other_user_id: {"step": "unrelated"}}
        suggestion_calls = []
        weather_calls = []

        def suggestions(*_args, **_kwargs):
            suggestion_calls.append(len(suggestion_calls) + 1)
            item_id = f"fixture-{suggestion_calls[-1]}"
            return [{"id": item_id, "title": item_id, "prompt": f"Text {item_id}"}]

        def set_pending(owner_id, step, **fields):
            state = dict(pending.get(owner_id, {}))
            state.update({"step": step, **fields})
            pending[owner_id] = state
            return state

        def clear_pending(owner_id):
            pending.pop(owner_id, None)

        def weather_report(city):
            weather_calls.append(city)
            return {"temperature": 24, "description": "Trời quang", "windspeed": 5, "humidity": 70}

        async def render(query, text, **kwargs):
            query.edits.append((text, kwargs))

        hub = _load_functions(
            "build_2col_keyboard", "free_hub_main_keyboard", "free_hub_library_text",
            "free_hub_library_keyboard", "free_hub_library_category_label", "free_hub_library_item_keyboard",
            "free_hub_library_item_keyboard_for_parent", "free_hub_library_suggestions_text",
            "free_hub_library_suggestions_keyboard", "free_hub_library_suggestions_keyboard_for_parent",
            "free_hub_prompt_result_text", "free_hub_result_keyboard",
            "handle_free_hub_callback",
            InlineKeyboardButton=_Button, InlineKeyboardMarkup=_Markup, html=html,
            normalize_user_language=lambda lang: lang or "vi",
            public_hub_copy=lambda _lang: labels,
            ui_text=lambda _lang, key: labels.get(key, key),
            FREE_HUB_ENABLED=True, FREE_PROMPT_LIBRARY={"_expanded_items": [1]},
            opt=SimpleNamespace(
                format_exchange_rate_overview=lambda _lang: "Exchange overview fixture",
                fetch_weather_report=weather_report,
            ),
            FREE_HUB_LIBRARY_CATEGORIES={
                "video": ("video_prompt", "Prompt video"),
                "music": ("music_sfx", "Nhạc/SFX"),
            },
            FREE_HUB_LIBRARY_INDUSTRY_FILTERS={}, get_user_language=lambda _uid: "vi",
            clear_video_downloader_pending=lambda _uid: None,
            clear_free_hub_pending=clear_pending,
            get_free_hub_pending=lambda owner_id: dict(pending.get(owner_id, {})),
            set_free_hub_pending=set_pending,
            free_hub_main_text=lambda _lang: "Free Tools root fixture",
            prompt_library_suggestions=suggestions,
            prompt_library_item=lambda _library, item_id: (
                {"id": item_id, "title": item_id, "prompt": f"Text {item_id}"}
                if item_id else None
            ),
            safe_edit_or_send=render, time=SimpleNamespace(time=lambda: 1.0),
        )
        hub_pattern = _registered_pattern("handle_free_hub_callback")
        context = SimpleNamespace(user_data={})

        def dispatch(callback_data):
            self.assertRegex(callback_data, hub_pattern)
            query = _Query(user_id, callback_data)
            _run_no_io(hub["handle_free_hub_callback"](
                SimpleNamespace(callback_query=query), context,
            ))
            self.assertEqual([((), {})], query.answers)
            return query

        opened_hub = dispatch(freehub_entry)
        main_markup = opened_hub.edits[0][1]["reply_markup"]
        library_entry = next(
            button.callback_data for row in main_markup.inline_keyboard for button in row
            if button.callback_data == "freehub|library"
        )
        library_screen = dispatch(library_entry)
        library_markup = library_screen.edits[0][1]["reply_markup"]
        self.assertIn("freehub|lib_video", [
            button.callback_data for row in library_markup.inline_keyboard for button in row
        ])

        category_screen = dispatch("freehub|lib_video")
        suggestion_markup = category_screen.edits[0][1]["reply_markup"]
        original_suggestion_text = category_screen.edits[0][0]
        original_ids = list(pending[user_id]["library_ids"])
        selected = dispatch("freehub|lib_pick1")
        self.assertIn("Text fixture-1", selected.edits[0][0])
        copy_control = next(
            button for row in selected.edits[0][1]["reply_markup"].inline_keyboard
            for button in row if button.callback_data == "freehub|copy"
        )
        copied = dispatch(copy_control.callback_data)
        with self.subTest("copy-label"):
            self.assertEqual("📋 Sao chép", copy_control.text)
        with self.subTest("manual-copy-help"):
            self.assertIn("Chạm giữ", copied.edits[0][0])
        self.assertEqual(original_ids, pending[user_id]["library_ids"])
        selected = copied
        item_back = selected.edits[0][1]["reply_markup"].inline_keyboard[-1][0]
        self.assertEqual("freehub|lib_back", item_back.callback_data)

        restored_suggestions = dispatch(item_back.callback_data)
        self.assertEqual(original_suggestion_text, restored_suggestions.edits[0][0])
        self.assertEqual(original_ids, pending[user_id]["library_ids"])
        self.assertEqual([1], suggestion_calls)
        suggestion_markup = restored_suggestions.edits[0][1]["reply_markup"]
        back, home = suggestion_markup.inline_keyboard[-1]
        self.assertEqual("freehub|library", back.callback_data)
        self.assertEqual("menu|main", home.callback_data)

        returned_library = dispatch(back.callback_data)
        self.assertEqual("Kho Prompt", returned_library.edits[0][0].splitlines()[0].replace("📚 <b>", "").replace("</b>", ""))
        self.assertIn("freehub|lib_video", [
            button.callback_data for row in returned_library.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
        ])
        self.assertNotIn(user_id, pending)

        library_back = returned_library.edits[0][1]["reply_markup"].inline_keyboard[-1][0]
        self.assertEqual("freehub|main", library_back.callback_data)
        hub_again = dispatch(library_back.callback_data)
        utilities_entry = next(
            button.callback_data for row in hub_again.edits[0][1]["reply_markup"].inline_keyboard
            for button in row if button.callback_data == "freehub|open_utilities"
        )
        utilities_screen = dispatch(utilities_entry)
        self.assertIn("Tiện ích", utilities_screen.edits[0][0])
        utility_rows = utilities_screen.edits[0][1]["reply_markup"].inline_keyboard
        self.assertEqual(
            {"freehub|util_rate", "freehub|util_weather", "freehub|util_qr", "freehub|util_avatar", "freehub|main"},
            {button.callback_data for row in utility_rows for button in row},
        )
        rate_overview = dispatch("freehub|util_rate")
        self.assertEqual("Exchange overview fixture", rate_overview.edits[0][0])
        rate_input = next(
            button.callback_data for row in rate_overview.edits[0][1]["reply_markup"].inline_keyboard
            for button in row if button.callback_data == "freehub|util_rate_input"
        )
        rate_prompt = dispatch(rate_input)
        self.assertIn("QUY ĐỔI TỶ GIÁ & XU", rate_prompt.edits[0][0])
        self.assertEqual({"step": "input", "task_type": "util_rate"}, pending[user_id])
        rate_back = rate_prompt.edits[0][1]["reply_markup"].inline_keyboard[-1][0]
        self.assertEqual("freehub|open_utilities", rate_back.callback_data)
        returned_utilities = dispatch(rate_back.callback_data)
        self.assertEqual(
            {"freehub|util_rate", "freehub|util_weather", "freehub|util_qr", "freehub|util_avatar", "freehub|main"},
            {button.callback_data for row in returned_utilities.edits[0][1]["reply_markup"].inline_keyboard for button in row},
        )
        self.assertNotIn(user_id, pending)
        self.assertEqual({"step": "unrelated"}, pending[other_user_id])

        weather_entry = next(
            button.callback_data for row in returned_utilities.edits[0][1]["reply_markup"].inline_keyboard
            for button in row if button.callback_data == "freehub|util_weather"
        )
        weather_overview = dispatch(weather_entry)
        self.assertIn("Hà Nội:", weather_overview.edits[0][0])
        self.assertEqual(["Hà Nội", "Đà Nẵng", "Hồ Chí Minh"], weather_calls)
        weather_input = next(
            button.callback_data for row in weather_overview.edits[0][1]["reply_markup"].inline_keyboard
            for button in row if button.callback_data == "freehub|util_weather_input"
        )
        weather_prompt = dispatch(weather_input)
        self.assertIn("TRA CỨU THỜI TIẾT ĐỊA ĐIỂM BẤT KỲ", weather_prompt.edits[0][0])
        self.assertEqual({"step": "input", "task_type": "util_weather"}, pending[user_id])
        self.assertEqual(["Hà Nội", "Đà Nẵng", "Hồ Chí Minh"], weather_calls)
        weather_back = weather_prompt.edits[0][1]["reply_markup"].inline_keyboard[-1][0]
        self.assertEqual("freehub|open_utilities", weather_back.callback_data)
        returned_utilities = dispatch(weather_back.callback_data)
        self.assertEqual(
            {"freehub|util_rate", "freehub|util_weather", "freehub|util_qr", "freehub|util_avatar", "freehub|main"},
            {button.callback_data for row in returned_utilities.edits[0][1]["reply_markup"].inline_keyboard for button in row},
        )
        self.assertNotIn(user_id, pending)
        self.assertEqual({"step": "unrelated"}, pending[other_user_id])

        qr_entry = next(
            button.callback_data for row in utility_rows for button in row
            if button.callback_data == "freehub|util_qr"
        )
        qr_prompt = dispatch(qr_entry)
        self.assertIn("Tạo mã QR nhanh", qr_prompt.edits[0][0])
        self.assertEqual({"step": "input", "task_type": "util_qr"}, pending[user_id])
        qr_back = qr_prompt.edits[0][1]["reply_markup"].inline_keyboard[-1][0]
        self.assertEqual("freehub|open_utilities", qr_back.callback_data)

        returned_utilities = dispatch(qr_back.callback_data)
        returned_callbacks = {
            button.callback_data
            for row in returned_utilities.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
        }
        self.assertEqual(
            {"freehub|util_rate", "freehub|util_weather", "freehub|util_qr", "freehub|util_avatar", "freehub|main"},
            returned_callbacks,
        )
        self.assertNotIn(user_id, pending)
        self.assertEqual({"step": "unrelated"}, pending[other_user_id])

        avatar_entry = next(
            button.callback_data for row in returned_utilities.edits[0][1]["reply_markup"].inline_keyboard
            for button in row if button.callback_data == "freehub|util_avatar"
        )
        avatar_prompt = dispatch(avatar_entry)
        self.assertIn("Robot AI", avatar_prompt.edits[0][0])
        self.assertEqual({"step": "input", "task_type": "util_avatar", "avatar_set": 1}, pending[user_id])
        avatar_style = next(
            button.callback_data for row in avatar_prompt.edits[0][1]["reply_markup"].inline_keyboard
            for button in row if button.callback_data == "freehub|avatar_set|2"
        )
        selected_avatar_style = dispatch(avatar_style)
        self.assertIn("Quái vật cute", selected_avatar_style.edits[0][0])
        self.assertEqual({"step": "input", "task_type": "util_avatar", "avatar_set": 2}, pending[user_id])
        avatar_back = selected_avatar_style.edits[0][1]["reply_markup"].inline_keyboard[-1][0]
        self.assertEqual("freehub|open_utilities", avatar_back.callback_data)

        returned_utilities = dispatch(avatar_back.callback_data)
        self.assertEqual(
            {"freehub|util_rate", "freehub|util_weather", "freehub|util_qr", "freehub|util_avatar", "freehub|main"},
            {button.callback_data for row in returned_utilities.edits[0][1]["reply_markup"].inline_keyboard for button in row},
        )
        self.assertNotIn(user_id, pending)
        self.assertEqual({"step": "unrelated"}, pending[other_user_id])

        utilities_back = returned_utilities.edits[0][1]["reply_markup"].inline_keyboard[-1][0]
        returned_hub = dispatch(utilities_back.callback_data)
        self.assertEqual("Free Tools root fixture", returned_hub.edits[0][0])
        self.assertNotIn(user_id, pending)
        self.assertEqual({"step": "unrelated"}, pending[other_user_id])

        music_entry = next(
            button.callback_data
            for row in returned_hub.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
            if button.callback_data == "freehub|lib_music_root"
        )
        music_suggestions = dispatch(music_entry)
        self.assertIn('"music": ("music_sfx",', BOT_SOURCE)
        self.assertIn("Nhạc/SFX", music_suggestions.edits[0][0])
        self.assertEqual(2, len(suggestion_calls))
        self.assertEqual("music_sfx", pending[user_id]["library_category"])
        self.assertEqual("Nhạc/SFX", pending[user_id]["library_label"])
        music_back = music_suggestions.edits[0][1]["reply_markup"].inline_keyboard[-1][0]
        self.assertEqual("freehub|main", music_back.callback_data)
        self.assertIn("freehub|lib_more_root", {
            button.callback_data
            for row in music_suggestions.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
        })
        music_pick = next(
            button.callback_data
            for row in music_suggestions.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
            if button.callback_data == "freehub|lib_pick1_root"
        )
        music_item = dispatch(music_pick)
        self.assertIn("Text fixture-2", music_item.edits[0][0])
        music_copy_control = next(
            button.callback_data
            for row in music_item.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
            if button.callback_data == "freehub|copy"
        )
        music_copy = dispatch(music_copy_control)
        self.assertIn("Chạm giữ", music_copy.edits[0][0])
        item_back = music_copy.edits[0][1]["reply_markup"].inline_keyboard[-1][0]
        self.assertEqual("freehub|lib_back_root", item_back.callback_data)
        restored_music = dispatch(item_back.callback_data)
        restored_back = restored_music.edits[0][1]["reply_markup"].inline_keyboard[-1][0]
        self.assertEqual("freehub|main", restored_back.callback_data)
        returned_hub = dispatch(restored_back.callback_data)
        self.assertEqual("Free Tools root fixture", returned_hub.edits[0][0])
        self.assertNotIn(user_id, pending)
        self.assertEqual({"step": "unrelated"}, pending[other_user_id])

        music_suggestions = dispatch(music_entry)
        more_control = next(
            button.callback_data
            for row in music_suggestions.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
            if button.callback_data == "freehub|lib_more_root"
        )
        more_music = dispatch(more_control)
        more_back = more_music.edits[0][1]["reply_markup"].inline_keyboard[-1][0]
        self.assertEqual("freehub|main", more_back.callback_data)
        self.assertEqual("Free Tools root fixture", dispatch(more_back.callback_data).edits[0][0])
        clear_pending(user_id)
        expired_more = dispatch(more_control)
        self.assertEqual("Free Tools root fixture", expired_more.edits[0][0])
        self.assertEqual({"step": "unrelated"}, pending[other_user_id])

        library_screen = dispatch("freehub|library")
        library_music = next(
            button.callback_data
            for row in library_screen.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
            if button.callback_data == "freehub|lib_music"
        )
        generic_music = dispatch(library_music)
        generic_back = generic_music.edits[0][1]["reply_markup"].inline_keyboard[-1][0]
        self.assertEqual("freehub|library", generic_back.callback_data)
        self.assertIn("freehub|lib_music", {
            button.callback_data
            for row in dispatch(generic_back.callback_data).edits[0][1]["reply_markup"].inline_keyboard
            for button in row
        })
        self.assertNotIn(user_id, pending)
        self.assertEqual({"step": "unrelated"}, pending[other_user_id])

    def test_free_tools_prompt_generator_back_returns_to_hub_and_clears_only_its_pending_state(self):
        user_id = 991138
        other_user_id = 991139
        labels = {
            "free_title": "Công cụ miễn phí", "free_body": "Free tools",
            "freehub_enable_ai_chatbot": "Chatbot", "freehub_utilities": "Tiện ích",
            "freehub_meta": "Meta", "freehub_caption": "Caption", "freehub_ideas": "Ý tưởng",
            "freehub_prompts": "Prompt ảnh/video", "freehub_library": "Kho Prompt",
            "freehub_publish_package": "Gói đăng bài", "freehub_notes_docs": "Ghi chú",
            "freehub_save_temp_media": "Lưu tệp tạm", "freehub_voice_subdub_script": "Kịch bản",
            "freehub_music_sfx_ideas": "Nhạc/SFX", "freehub_translation": "Dịch thuật",
            "freehub_video_downloader": "Tải video", "main_menu": "Trang chủ",
            "freehub_use_suggestion_1": "Dùng 1", "freehub_use_suggestion_2": "Dùng 2",
            "freehub_use_suggestion_3": "Dùng 3", "freehub_more_suggestions": "Thêm gợi ý",
            "freehub_custom_input": "Tự nhập", "freehub_back": "Quay lại",
        }
        builders = _load_functions(
            "build_2col_keyboard", "free_hub_main_keyboard", "free_hub_suggestions_keyboard",
            InlineKeyboardButton=_Button, InlineKeyboardMarkup=_Markup,
            normalize_user_language=lambda lang: lang or "vi",
            public_hub_copy=lambda _lang: labels,
            ui_text=lambda _lang, key: labels.get(key, key),
        )
        pending = {other_user_id: {"pending_action": "free_hub", "task_type": "other-user"}}
        suggestion_calls = []

        def set_pending(owner_id, step, **fields):
            state = dict(pending.get(owner_id, {}))
            state.update({"pending_action": "free_hub", "step": step, **fields})
            pending[owner_id] = state
            return state

        def clear_pending(owner_id):
            return pending.pop(owner_id, None) is not None

        def suggestions(task_type, offset):
            suggestion_calls.append((task_type, offset))
            return [f"fixture-{index}" for index in range(offset + 1, offset + 4)]

        async def render(query, text, **kwargs):
            query.edits.append((text, kwargs))

        handler = _load_functions(
            "handle_free_hub_callback",
            InlineKeyboardButton=_Button, InlineKeyboardMarkup=_Markup,
            normalize_user_language=lambda lang: lang or "vi",
            public_hub_copy=lambda _lang: labels,
            normalize_free_hub_task_type=lambda task_type: task_type,
            FREE_HUB_ENABLED=True, get_user_language=lambda _uid: "vi",
            clear_video_downloader_pending=lambda _uid: None,
            clear_free_hub_pending=clear_pending, set_free_hub_pending=set_pending,
            get_free_hub_pending=lambda owner_id: dict(pending.get(owner_id, {})),
            free_hub_main_text=lambda _lang: "Free Tools root fixture",
            free_hub_main_keyboard=builders["free_hub_main_keyboard"],
            free_hub_quota_payload=lambda _uid: {"allowed": True},
            free_hub_suggestion_items=suggestions,
            free_hub_suggestions_text=lambda task, items, _lang: f"{task}: {', '.join(items)}",
            free_hub_suggestions_keyboard=builders["free_hub_suggestions_keyboard"],
            safe_edit_or_send=render,
        )
        route_pattern = _registered_pattern("handle_free_hub_callback")
        context = SimpleNamespace(user_data={})

        def dispatch(callback_data):
            self.assertRegex(callback_data, route_pattern)
            query = _Query(user_id, callback_data)
            asyncio.run(handler["handle_free_hub_callback"](
                SimpleNamespace(callback_query=query), context,
            ))
            self.assertEqual([((), {})], query.answers)
            return query

        root = dispatch("freehub|main")
        prompt_entry = next(
            button.callback_data for row in root.edits[0][1]["reply_markup"].inline_keyboard
            for button in row if button.text == "🖼 Prompt ảnh/video"
        )
        suggestions_screen = dispatch(prompt_entry)
        self.assertIn("image_video_prompt", suggestions_screen.edits[0][0])
        self.assertEqual(
            {"pending_action": "free_hub", "step": "suggestions", "task_type": "image_video_prompt",
             "suggestion_offset": 0, "suggestion_items": ["fixture-1", "fixture-2", "fixture-3"]},
            pending[user_id],
        )
        back, home = suggestions_screen.edits[0][1]["reply_markup"].inline_keyboard[-1]
        self.assertEqual("freehub|main", back.callback_data)
        self.assertEqual("menu|main", home.callback_data)

        returned = dispatch(back.callback_data)
        self.assertEqual("Free Tools root fixture", returned.edits[0][0])
        self.assertNotIn(user_id, pending)
        self.assertEqual({"pending_action": "free_hub", "task_type": "other-user"}, pending[other_user_id])
        self.assertEqual([("image_video_prompt", 0)], suggestion_calls)

        for callback_data, task_type in (
            ("freehub|meta", "meta_ai_prompt"),
            ("freehub|caption", "caption_hashtag"),
            ("freehub|ideas", "content_idea"),
            ("freehub|hook", "hook_script"),
        ):
            with self.subTest(callback_data=callback_data):
                root_callbacks = {
                    button.callback_data
                    for row in root.edits[0][1]["reply_markup"].inline_keyboard
                    for button in row
                }
                self.assertIn(callback_data, root_callbacks)

                suggestions_screen = dispatch(callback_data)
                self.assertIn(task_type, suggestions_screen.edits[0][0])
                self.assertEqual(
                    {
                        "pending_action": "free_hub", "step": "suggestions", "task_type": task_type,
                        "suggestion_offset": 0, "suggestion_items": ["fixture-1", "fixture-2", "fixture-3"],
                    },
                    pending[user_id],
                )
                back, home = suggestions_screen.edits[0][1]["reply_markup"].inline_keyboard[-1]
                self.assertEqual("freehub|main", back.callback_data)
                self.assertEqual("menu|main", home.callback_data)

                returned = dispatch(back.callback_data)
                self.assertEqual("Free Tools root fixture", returned.edits[0][0])
                self.assertNotIn(user_id, pending)
                self.assertEqual({"pending_action": "free_hub", "task_type": "other-user"}, pending[other_user_id])

        self.assertEqual(
            [
                ("image_video_prompt", 0),
                ("meta_ai_prompt", 0),
                ("caption_hashtag", 0),
                ("content_idea", 0),
                ("hook_script", 0),
            ],
            suggestion_calls,
        )

    def test_free_tools_upload_prompt_back_clears_only_its_pending_state(self):
        user_id = 991140
        other_user_id = 991141
        labels = {
            "free_title": "Công cụ miễn phí", "free_body": "Free tools",
            "freehub_enable_ai_chatbot": "Chatbot", "freehub_utilities": "Tiện ích",
            "freehub_meta": "Meta", "freehub_caption": "Caption", "freehub_ideas": "Ý tưởng",
            "freehub_prompts": "Prompt ảnh/video", "freehub_library": "Kho Prompt",
            "freehub_publish_package": "Gói đăng bài", "freehub_notes_docs": "Ghi chú",
            "freehub_save_temp_media": "Lưu tệp tạm", "freehub_voice_subdub_script": "Kịch bản",
            "freehub_music_sfx_ideas": "Nhạc/SFX", "freehub_translation": "Dịch thuật",
            "freehub_video_downloader": "Tải video", "freehub_upload_title": "Lưu tệp tạm",
            "freehub_upload_body": "Gửi tệp muốn xử lý sau", "freehub_input_free": "Gửi nội dung",
            "freehub_main": "Công cụ miễn phí", "freehub_back": "Quay lại", "main_menu": "Trang chủ",
        }
        builders = _load_functions(
            "build_2col_keyboard", "free_hub_main_keyboard", "free_hub_input_keyboard",
            "free_hub_upload_text", "free_hub_upload_keyboard",
            InlineKeyboardButton=_Button, InlineKeyboardMarkup=_Markup,
            normalize_user_language=lambda lang: lang or "vi",
            public_hub_copy=lambda _lang: labels,
            ui_text=lambda _lang, key: labels.get(key, key),
        )
        pending = {other_user_id: {"pending_action": "free_hub", "task_type": "other-user"}}

        def set_pending(owner_id, step, **fields):
            state = {"pending_action": "free_hub", "step": step, **fields}
            pending[owner_id] = state
            return state

        def clear_pending(owner_id):
            return pending.pop(owner_id, None) is not None

        async def render(query, text, **kwargs):
            query.edits.append((text, kwargs))

        handler = _load_functions(
            "handle_free_hub_callback",
            InlineKeyboardButton=_Button, InlineKeyboardMarkup=_Markup,
            normalize_user_language=lambda lang: lang or "vi",
            public_hub_copy=lambda _lang: labels,
            FREE_HUB_ENABLED=True, get_user_language=lambda _uid: "vi",
            clear_video_downloader_pending=lambda _uid: None,
            clear_free_hub_pending=clear_pending, set_free_hub_pending=set_pending,
            free_hub_main_text=lambda _lang: "Free Tools root fixture",
            free_hub_main_keyboard=builders["free_hub_main_keyboard"],
            free_hub_upload_text=builders["free_hub_upload_text"],
            free_hub_upload_keyboard=builders["free_hub_upload_keyboard"],
            safe_edit_or_send=render,
        )
        route_pattern = _registered_pattern("handle_free_hub_callback")
        context = SimpleNamespace(user_data={})

        def dispatch(callback_data):
            self.assertRegex(callback_data, route_pattern)
            query = _Query(user_id, callback_data)
            asyncio.run(handler["handle_free_hub_callback"](
                SimpleNamespace(callback_query=query), context,
            ))
            self.assertEqual([((), {})], query.answers)
            return query

        root = dispatch("freehub|main")
        upload_entry = next(
            button.callback_data for row in root.edits[0][1]["reply_markup"].inline_keyboard
            for button in row if button.text == "📥 Lưu tệp tạm"
        )
        upload_prompt = dispatch(upload_entry)
        self.assertIn("Lưu tệp tạm", upload_prompt.edits[0][0])
        self.assertEqual(
            {"pending_action": "free_hub", "step": "upload", "task_type": "upload_for_postprocess"},
            pending[user_id],
        )
        back, home = upload_prompt.edits[0][1]["reply_markup"].inline_keyboard[-1]
        self.assertEqual("freehub|main", back.callback_data)
        self.assertEqual("menu|main", home.callback_data)

        returned = dispatch(back.callback_data)
        self.assertEqual("Free Tools root fixture", returned.edits[0][0])
        self.assertNotIn(user_id, pending)
        self.assertEqual({"pending_action": "free_hub", "task_type": "other-user"}, pending[other_user_id])

    def test_freehub_empty_publish_package_routes_to_guidance_without_publish_action(self):
        from services.pricing_guide_content import public_hub_copy

        user_id = 991143
        copy = public_hub_copy("vi")
        pending_reads = []
        pending_clears = []
        rendered = []

        def build_2col_keyboard(items, *, nav_back=None, nav_main=False, lang="vi", main_label="Main"):
            flat = [_Button(label, callback) for label, callback in items]
            rows = [flat[index:index + 2] for index in range(0, len(flat), 2)]
            if nav_back:
                rows.append([_Button(nav_back[0], nav_back[1])])
            if nav_main:
                rows.append([_Button(main_label, "menu|main")])
            return _Markup(rows)

        async def render(query, text, **kwargs):
            rendered.append((text, kwargs))
            query.edits.append((text, kwargs))

        forbidden = lambda *_args, **_kwargs: self.fail("empty package guide must not invoke publish/provider helpers")
        namespace = _load_functions(
            "free_hub_main_keyboard", "handle_free_hub_callback",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
            build_2col_keyboard=build_2col_keyboard,
            normalize_user_language=lambda lang: lang or "vi",
            public_hub_copy=public_hub_copy,
            FREE_HUB_ENABLED=True,
            get_user_language=lambda _uid: "vi",
            clear_video_downloader_pending=lambda _uid: None,
            clear_free_hub_pending=lambda uid: pending_clears.append(uid),
            get_free_hub_pending=lambda uid: pending_reads.append(uid) or {},
            free_hub_publish_package_text=forbidden,
            free_hub_publish_package_keyboard=forbidden,
            free_hub_main_text=lambda _lang: "Free Tools root",
            safe_edit_or_send=render,
        )

        registrations = []
        namespace["tg_app"] = SimpleNamespace(add_handler=registrations.append)
        namespace["CallbackQueryHandler"] = lambda callback, pattern: SimpleNamespace(
            callback=callback, pattern=re.compile(pattern)
        )
        registration = next(
            line.strip()
            for line in BOT_SOURCE.splitlines()
            if "tg_app.add_handler(CallbackQueryHandler(handle_free_hub_callback," in line
        )
        exec(registration, namespace)
        route = next(item for item in registrations if item.callback is namespace["handle_free_hub_callback"])

        root = namespace["free_hub_main_keyboard"]("vi")
        emitted = next(
            button.callback_data
            for row in root.inline_keyboard
            for button in row
            if button.callback_data == "freehub|publish_package"
        )
        self.assertIsNotNone(route.pattern.match(emitted))
        query = _Query(user_id, emitted)
        _run_no_io(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace(user_data={})))

        self.assertEqual([((), {})], query.answers)
        self.assertEqual([user_id], pending_reads)
        self.assertEqual([], pending_clears)
        self.assertEqual(1, len(rendered))
        for text in (copy["freehub_publish_title"], copy["freehub_prompts_body"], copy["freehub_input_free"]):
            self.assertIn(text, rendered[0][0])
        returned_callbacks = [
            button.callback_data
            for row in rendered[0][1]["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertEqual(
            [button.callback_data for row in root.inline_keyboard for button in row],
            returned_callbacks,
        )

    def test_freehub_result_package_back_restores_same_result_context(self):
        from services.pricing_guide_content import public_hub_copy

        user_id = 991144
        other_user_id = user_id + 1
        result = {
            "title": "Fixture result",
            "topic": "Fixture topic",
            "caption": "Caption fixture",
            "hashtags": ["#fixture"],
            "cta": "CTA fixture",
        }
        pending = {
            user_id: {
                "pending_action": "free_hub",
                "step": "result",
                "task_type": "caption_hashtag",
                "user_input": "Fixture topic",
                "result": result,
                "provider": "local_prompt_library",
            },
            other_user_id: {"pending_action": "free_hub", "step": "other-user"},
        }
        original_state = dict(pending[user_id])
        other_state = dict(pending[other_user_id])
        clears = []
        rendered = []

        def build_2col_keyboard(items, *, nav_back=None, nav_main=False, lang="vi", main_label="Main"):
            flat = [_Button(label, callback) for label, callback in items]
            rows = [flat[index:index + 2] for index in range(0, len(flat), 2)]
            if nav_back:
                rows.append([_Button(nav_back[0], nav_back[1])])
            if nav_main:
                rows.append([_Button(main_label, "menu|main")])
            return _Markup(rows)

        async def render(query, text, **kwargs):
            rendered.append((text, kwargs))
            query.edits.append((text, kwargs))

        def clear_free_hub(uid):
            pending.pop(uid, None)
            clears.append(uid)

        namespace = _load_functions(
            "free_hub_main_keyboard",
            "free_hub_publish_package_text",
            "free_hub_publish_package_keyboard",
            "free_hub_prompt_result_text",
            "free_hub_result_keyboard",
            "handle_free_hub_callback",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
            build_2col_keyboard=build_2col_keyboard,
            normalize_user_language=lambda lang: lang or "vi",
            public_hub_copy=public_hub_copy,
            html=html,
            FREE_HUB_ENABLED=True,
            get_user_language=lambda _uid: "vi",
            get_free_hub_pending=lambda uid: dict(pending.get(uid, {})),
            clear_free_hub_pending=clear_free_hub,
            clear_video_downloader_pending=lambda _uid: None,
            free_hub_main_text=lambda _lang: "Free Tools root fixture",
            safe_edit_or_send=render,
        )
        registrations = []
        namespace["tg_app"] = SimpleNamespace(add_handler=registrations.append)
        namespace["CallbackQueryHandler"] = lambda callback, pattern: SimpleNamespace(
            callback=callback, pattern=re.compile(pattern)
        )
        registration = next(
            line.strip()
            for line in BOT_SOURCE.splitlines()
            if "tg_app.add_handler(CallbackQueryHandler(handle_free_hub_callback," in line
        )
        exec(registration, namespace)
        route = next(item for item in registrations if item.callback is namespace["handle_free_hub_callback"])

        result_keyboard = namespace["free_hub_result_keyboard"]("vi", "caption_hashtag")
        package_callback = next(
            button.callback_data
            for row in result_keyboard.inline_keyboard
            for button in row
            if button.callback_data == "freehub|publish_package"
        )

        def dispatch(callback):
            self.assertIsNotNone(route.pattern.match(callback))
            query = _Query(user_id, callback)
            _run_no_io(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace(user_data={})))
            self.assertEqual([((), {})], query.answers)
            return query

        package_page = dispatch(package_callback)
        package_text = package_page.edits[0][0]
        self.assertIn("Fixture topic", package_text)
        self.assertIn("Caption fixture", package_text)
        self.assertIn("chưa tự đăng", package_text)
        self.assertIn("chưa gọi provider", package_text)
        package_callbacks = [
            button.callback_data
            for row in package_page.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertIn("freehub|prompt_back", package_callbacks)
        self.assertIn("freehub|copy", package_callbacks)
        self.assertIn("freehub|save", package_callbacks)

        returned = dispatch("freehub|prompt_back")
        self.assertIn("Fixture result", returned.edits[0][0])
        self.assertIn("Fixture topic", returned.edits[0][0])
        returned_callbacks = [
            button.callback_data
            for row in returned.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertEqual(
            [button.callback_data for row in result_keyboard.inline_keyboard for button in row],
            returned_callbacks,
        )
        copy_callback = next(callback for callback in returned_callbacks if callback == "freehub|copy")
        copied = dispatch(copy_callback)
        self.assertIn("Chạm giữ đoạn văn bản phía trên", copied.edits[0][0])
        self.assertEqual(original_state, pending[user_id])
        self.assertEqual(
            returned_callbacks,
            [button.callback_data for row in copied.edits[0][1]["reply_markup"].inline_keyboard for button in row],
        )
        self.assertEqual(original_state, pending[user_id])
        self.assertEqual(other_state, pending[other_user_id])
        self.assertEqual([], clears)
        self.assertEqual(3, len(rendered))

        hub_back = next(button.callback_data for row in copied.edits[0][1]["reply_markup"].inline_keyboard for button in row if button.callback_data == "freehub|main")
        hub = dispatch(hub_back)
        self.assertEqual("Free Tools root fixture", hub.edits[0][0])
        self.assertNotIn(user_id, pending)
        self.assertEqual(other_state, pending[other_user_id])
        self.assertEqual([user_id], clears)
        self.assertIn("menu|main", [button.callback_data for row in hub.edits[0][1]["reply_markup"].inline_keyboard for button in row])

    def test_free_tools_translation_prompt_back_clears_only_its_pending_state(self):
        user_id = 991137
        other_user_id = user_id + 1
        labels = {
            "freehub_enable_ai_chatbot": "Chatbot", "freehub_utilities": "Tiện ích",
            "freehub_meta": "Meta", "freehub_caption": "Caption", "freehub_ideas": "Ý tưởng",
            "freehub_prompts": "Prompt ảnh/video", "freehub_library": "Kho Prompt",
            "freehub_publish_package": "Gói đăng bài", "freehub_notes_docs": "Ghi chú",
            "freehub_save_temp_media": "Lưu tệp tạm", "freehub_voice_subdub_script": "Kịch bản",
            "freehub_music_sfx_ideas": "Nhạc/SFX", "freehub_translation": "Dịch thuật",
            "freehub_video_downloader": "Tải video", "freehub_main": "Công cụ miễn phí",
            "free_tools_label": "Công cụ miễn phí", "main_menu": "Trang chủ",
        }
        builders = _load_functions(
            "build_2col_keyboard", "free_hub_main_keyboard",
            InlineKeyboardButton=_Button, InlineKeyboardMarkup=_Markup,
            normalize_user_language=lambda lang: lang or "vi",
            public_hub_copy=lambda _lang: labels,
            ui_text=lambda _lang, key: labels.get(key, key),
        )
        main_keyboard = builders["free_hub_main_keyboard"]("vi")
        translate_entry = next(
            button.callback_data for row in main_keyboard.inline_keyboard for button in row
            if button.callback_data == "freehub|open_translate"
        )
        pending = {other_user_id: {"pending_action": "free_hub", "step": "other-user"}}
        other_state = dict(pending[other_user_id])
        cleared = []

        def clear_pending(owner_id):
            existed = pending.pop(owner_id, None) is not None
            if existed:
                cleared.append(owner_id)
            return existed

        def set_pending(owner_id, step, **fields):
            pending[owner_id] = {"pending_action": "free_hub", "step": step, **fields}
            return pending[owner_id]

        async def render(query, text, **kwargs):
            query.edits.append((text, kwargs))

        handler = _load_functions(
            "handle_free_hub_callback",
            InlineKeyboardButton=_Button, InlineKeyboardMarkup=_Markup,
            normalize_user_language=lambda lang: lang or "vi",
            public_hub_copy=lambda _lang: labels,
            FREE_HUB_ENABLED=True, get_user_language=lambda _uid: "vi",
            clear_video_downloader_pending=lambda _uid: None,
            clear_free_hub_pending=clear_pending, set_free_hub_pending=set_pending,
            get_free_hub_pending=lambda owner_id: dict(pending.get(owner_id, {})),
            free_hub_main_text=lambda _lang: "Free Tools root fixture",
            free_hub_main_keyboard=builders["free_hub_main_keyboard"],
            safe_edit_or_send=render,
        )
        registrations = []
        handler["tg_app"] = SimpleNamespace(add_handler=registrations.append)
        handler["CallbackQueryHandler"] = lambda callback, pattern: SimpleNamespace(
            callback=callback, pattern=re.compile(pattern)
        )
        registration = next(
            line.strip()
            for line in BOT_SOURCE.splitlines()
            if "tg_app.add_handler(CallbackQueryHandler(handle_free_hub_callback," in line
        )
        exec(registration, handler)
        route = next(item for item in registrations if item.callback is handler["handle_free_hub_callback"])
        self.assertTrue(route.pattern.match(translate_entry))
        context = SimpleNamespace(user_data={})

        def dispatch(callback_data):
            self.assertTrue(route.pattern.match(callback_data))
            query = _Query(user_id, callback_data)
            _run_no_io(route.callback(SimpleNamespace(callback_query=query), context))
            self.assertEqual([((), {})], query.answers)
            return query

        prompt = dispatch(translate_entry)
        back = prompt.edits[0][1]["reply_markup"].inline_keyboard[-1][0]
        self.assertEqual("freehub|main", back.callback_data)
        self.assertEqual("open_translate", pending[user_id]["task_type"])
        self.assertEqual(other_state, pending[other_user_id])

        returned = dispatch(back.callback_data)
        self.assertEqual("Free Tools root fixture", returned.edits[0][0])
        self.assertNotIn(user_id, pending)
        self.assertEqual(other_state, pending[other_user_id])
        self.assertEqual([user_id], cleared)

    def test_freehub_legacy_byok_callback_stays_disabled_and_returns_to_hub(self):
        from services.pricing_guide_content import public_hub_copy

        user_id = 991147
        other_user_id = user_id + 1
        copy = public_hub_copy("vi")
        pending = {
            user_id: {"pending_action": "free_hub", "step": "old-input"},
            other_user_id: {"pending_action": "free_hub", "step": "other-user"},
        }
        other_state = dict(pending[other_user_id])
        cleared = []
        rendered = []

        def build_2col_keyboard(items, *, nav_back=None, nav_main=False, lang="vi", main_label="Main"):
            flat = [_Button(label, callback) for label, callback in items]
            rows = [flat[index:index + 2] for index in range(0, len(flat), 2)]
            if nav_back:
                rows.append([_Button(nav_back[0], nav_back[1])])
            if nav_main:
                rows.append([_Button(main_label, "menu|main")])
            return _Markup(rows)

        async def render(query, text, **kwargs):
            rendered.append((text, kwargs))
            query.edits.append((text, kwargs))

        def clear_actor(uid):
            pending.pop(uid, None)
            cleared.append(uid)

        namespace = _load_functions(
            "free_hub_main_keyboard",
            "free_hub_byok_text",
            "handle_free_hub_callback",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
            build_2col_keyboard=build_2col_keyboard,
            normalize_user_language=lambda lang: lang or "vi",
            public_hub_copy=public_hub_copy,
            FREE_HUB_ENABLED=True,
            FREE_HUB_BYOK_ENABLED=False,
            get_user_language=lambda _uid: "vi",
            clear_free_hub_pending=clear_actor,
            clear_video_downloader_pending=lambda _uid: None,
            free_hub_main_text=lambda _lang: "Free Tools root fixture",
            safe_edit_or_send=render,
        )
        english_warning = namespace["free_hub_byok_text"]("en")
        self.assertIn("Private API connection is not available", english_warning)
        self.assertIn("not accepting API keys", english_warning)
        self.assertIn("do not send an API key", english_warning)
        registrations = []
        namespace["tg_app"] = SimpleNamespace(add_handler=registrations.append)
        namespace["CallbackQueryHandler"] = lambda callback, pattern: SimpleNamespace(
            callback=callback, pattern=re.compile(pattern)
        )
        registration = next(
            line.strip()
            for line in BOT_SOURCE.splitlines()
            if "tg_app.add_handler(CallbackQueryHandler(handle_free_hub_callback," in line
        )
        exec(registration, namespace)
        route = next(item for item in registrations if item.callback is namespace["handle_free_hub_callback"])

        root = namespace["free_hub_main_keyboard"]("vi")
        root_callbacks = [button.callback_data for row in root.inline_keyboard for button in row]
        self.assertNotIn("freehub|byok", root_callbacks)
        self.assertIsNotNone(route.pattern.match("freehub|byok"), "legacy callback remains safely handled")

        query = _Query(user_id, "freehub|byok")
        _run_no_io(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace(user_data={})))

        self.assertEqual([((), {})], query.answers)
        self.assertIn("Kết nối API riêng chưa mở", rendered[0][0])
        self.assertIn("chưa nhận API key", rendered[0][0])
        self.assertEqual([user_id], cleared)
        self.assertNotIn(user_id, pending)
        self.assertEqual(other_state, pending[other_user_id])
        self.assertEqual(
            root_callbacks,
            [button.callback_data for row in rendered[0][1]["reply_markup"].inline_keyboard for button in row],
        )

    def test_freehub_docs_guidance_back_restores_uploaded_docs_tools_screen(self):
        from services.pricing_guide_content import public_hub_copy

        user_id = 991145
        copy = public_hub_copy("vi")
        renders = []

        def build_2col_keyboard(items, *, nav_back=None, nav_main=False, lang="vi", main_label="Main"):
            flat = [_Button(label, callback) for label, callback in items]
            rows = [flat[index:index + 2] for index in range(0, len(flat), 2)]
            if nav_back:
                rows.append([_Button(nav_back[0], nav_back[1])])
            if nav_main:
                rows.append([_Button(main_label, "menu|main")])
            return _Markup(rows)

        async def render(query, text, **kwargs):
            renders.append((text, kwargs))
            query.edits.append((text, kwargs))

        namespace = _load_functions(
            "free_hub_docs_text",
            "free_hub_docs_keyboard",
            "handle_free_hub_callback",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
            build_2col_keyboard=build_2col_keyboard,
            normalize_user_language=lambda lang: lang or "vi",
            public_hub_copy=public_hub_copy,
            FREE_HUB_ENABLED=True,
            get_user_language=lambda _uid: "vi",
            clear_video_downloader_pending=lambda _uid: None,
            clear_free_hub_pending=lambda _uid: None,
            menu_text_main_memory_i18n=lambda _lang: "Memory/Docs landing fixture",
            main_memory_keyboard=lambda *_args: _Markup([[_Button("Memory", "menu|main_memory")]]),
            safe_edit_or_send=render,
        )
        registrations = []
        namespace["tg_app"] = SimpleNamespace(add_handler=registrations.append)
        namespace["CallbackQueryHandler"] = lambda callback, pattern: SimpleNamespace(
            callback=callback, pattern=re.compile(pattern)
        )
        registration = next(
            line.strip()
            for line in BOT_SOURCE.splitlines()
            if "tg_app.add_handler(CallbackQueryHandler(handle_free_hub_callback," in line
        )
        exec(registration, namespace)
        route = next(item for item in registrations if item.callback is namespace["handle_free_hub_callback"])

        docs_keyboard = namespace["free_hub_docs_keyboard"]("vi")
        docs_text = namespace["free_hub_docs_text"]("vi")
        docs_callbacks = [button.callback_data for row in docs_keyboard.inline_keyboard for button in row]
        mismatches = []

        def dispatch(callback):
            self.assertIsNotNone(route.pattern.match(callback))
            query = _Query(user_id, callback)
            _run_no_io(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace(user_data={})))
            self.assertEqual([((), {})], query.answers)
            return query

        for entry in ("freehub|docs_split_merge", "freehub|docs_summary_guard"):
            with self.subTest(entry=entry):
                self.assertIn(entry, docs_callbacks)
                guide = dispatch(entry)
                back = next(button for row in guide.edits[0][1]["reply_markup"].inline_keyboard for button in row if button.callback_data == "freehub|docs")
                returned = dispatch(back.callback_data)
                actual_callbacks = [button.callback_data for row in returned.edits[0][1]["reply_markup"].inline_keyboard for button in row]
                if (
                    returned.edits[0][0] != docs_text
                    or actual_callbacks != docs_callbacks
                    or returned.edits[0][1].get("parse_mode") != "HTML"
                ):
                    mismatches.append((entry, returned.edits[0][0], actual_callbacks, returned.edits[0][1].get("parse_mode")))

        self.assertFalse(
            mismatches,
            f"FreeHub docs Back must restore the emitter screen, not another landing: {mismatches}",
        )
        legacy_notes = dispatch("freehub|notes")
        self.assertEqual("Memory/Docs landing fixture", legacy_notes.edits[0][0])
        self.assertEqual(
            ["menu|main_memory"],
            [button.callback_data for row in legacy_notes.edits[0][1]["reply_markup"].inline_keyboard for button in row],
        )

    def test_freehub_image_pdf_and_compress_hints_keep_docs_origin(self):
        from services.pricing_guide_content import public_hub_copy

        user_id = 991146
        copy = public_hub_copy("vi")
        effects = []

        def build_2col_keyboard(items, *, nav_back=None, nav_main=False, lang="vi", main_label="Main"):
            flat = [_Button(label, callback) for label, callback in items]
            rows = [flat[index:index + 2] for index in range(0, len(flat), 2)]
            if nav_back:
                rows.append([_Button(nav_back[0], nav_back[1])])
            if nav_main:
                rows.append([_Button(main_label, "menu|main")])
            return _Markup(rows)

        async def edit_menu(query, text, **kwargs):
            query.edits.append((text, kwargs))

        async def edit_freehub(query, text, **kwargs):
            query.edits.append((text, kwargs))

        dependencies = _main_menu_dependencies(False, effects)
        dependencies.update({
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "ADMIN_MENU_PAGE_HANDLERS": {},
            "normalize_user_language": lambda lang: lang or "vi",
            "public_hub_copy": public_hub_copy,
            "build_2col_keyboard": build_2col_keyboard,
            "public_command_exists": lambda _name: True,
            "time": SimpleNamespace(perf_counter=lambda: 1.0),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
            "safe_edit_query_message": edit_menu,
            "safe_edit_or_send": edit_freehub,
            "FREE_HUB_ENABLED": True,
            "get_user_language": lambda _uid: "vi",
            "clear_free_hub_pending": lambda _uid: None,
            "clear_video_downloader_pending": lambda _uid: None,
            "free_hub_main_text": lambda _lang: "Free Tools root fixture",
            "menu_text_main_memory_i18n": lambda _lang: "Memory/Docs landing fixture",
            "main_memory_keyboard": lambda *_args: _Markup([[_Button("Memory", "menu|main_memory")]]),
        })
        namespace = _load_functions(
            "menu_parent_action", "menu_nav_keyboard_i18n", "menu_hint_text", "menu_hint_text_i18n",
            "main_docs_keyboard", "menu_text_main_docs", "menu_text_main_docs_i18n",
            "localized_menu_content", "handle_menu_callback",
            "free_hub_docs_text", "free_hub_docs_keyboard", "handle_free_hub_callback",
            **dependencies,
        )
        registrations = []
        namespace["tg_app"] = SimpleNamespace(add_handler=registrations.append)
        namespace["CallbackQueryHandler"] = lambda callback, pattern: SimpleNamespace(
            callback=callback, pattern=re.compile(pattern)
        )
        for handler_name in ("handle_menu_callback", "handle_free_hub_callback"):
            registration = next(
                line.strip()
                for line in BOT_SOURCE.splitlines()
                if f"tg_app.add_handler(CallbackQueryHandler({handler_name}," in line
            )
            exec(registration, namespace)
        routes = {route.callback.__name__: route for route in registrations}

        def dispatch(callback):
            handler_name = "handle_free_hub_callback" if callback.startswith("freehub|") else "handle_menu_callback"
            route = routes[handler_name]
            self.assertIsNotNone(route.pattern.match(callback))
            query = _Query(user_id, callback)
            _run_no_io(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace(user_data={})))
            self.assertEqual([((), {})], query.answers)
            return query

        docs_keyboard = namespace["free_hub_docs_keyboard"]("vi")
        docs_text = namespace["free_hub_docs_text"]("vi")
        expected = {
            "image": "freehub|docs_image_to_pdf",
            "compress": "freehub|docs_compress_pdf",
        }
        mismatches = []
        for kind, expected_callback in expected.items():
            icon = "🖼" if kind == "image" else "🗜"
            button = next(button for row in docs_keyboard.inline_keyboard for button in row if button.text.startswith(icon))
            guide_action = "hint_doc_image_to_pdf" if kind == "image" else "hint_doc_compress_pdf"
            guide = dispatch(button.callback_data)
            expected_guide = namespace["menu_hint_text_i18n"](guide_action, "vi")[1]
            backs = [item for row in guide.edits[0][1]["reply_markup"].inline_keyboard for item in row if item.callback_data]
            back = next(item for item in backs if item.text.startswith("⬅"))
            returned = dispatch(back.callback_data)
            callbacks = [item.callback_data for row in returned.edits[0][1]["reply_markup"].inline_keyboard for item in row]
            actual = (button.callback_data, back.callback_data, guide.edits[0][0], returned.edits[0][0], callbacks)
            wanted = (expected_callback, "freehub|docs", expected_guide, docs_text,
                      [item.callback_data for row in docs_keyboard.inline_keyboard for item in row])
            if actual != wanted:
                mismatches.append((kind, actual, wanted))

        self.assertFalse(mismatches, f"FreeHub Docs inline hint lost its parent: {mismatches}")

        main_docs_keyboard = namespace["main_docs_keyboard"]("vi")
        generic_callbacks = [
            button.callback_data
            for row in main_docs_keyboard.inline_keyboard
            for button in row
            if button.callback_data and button.callback_data.startswith("menu|hint_doc_")
        ]
        self.assertEqual({
            "menu|hint_doc_pdf_to_word", "menu|hint_doc_image_to_pdf",
            "menu|hint_doc_compress_pdf", "menu|hint_doc_split_pdf", "menu|hint_doc_merge_pdf",
        }, set(generic_callbacks))
        main_docs_text = namespace["menu_text_main_docs_i18n"]("vi")
        main_docs_callbacks = [
            button.callback_data for row in main_docs_keyboard.inline_keyboard for button in row
        ]
        for callback in generic_callbacks:
            with self.subTest(generic_docs_hint=callback):
                guide = dispatch(callback)
                expected_guide = namespace["menu_hint_text_i18n"](callback.split("|", 1)[1], "vi")[1]
                self.assertEqual(expected_guide, guide.edits[0][0])
                back = next(
                    button
                    for row in guide.edits[0][1]["reply_markup"].inline_keyboard
                    for button in row
                    if button.text.startswith("⬅")
                )
                self.assertEqual("menu|main_docs", back.callback_data)
                generic_docs_return = dispatch(back.callback_data)
                self.assertEqual(main_docs_text, generic_docs_return.edits[0][0])
                self.assertEqual(
                    main_docs_callbacks,
                    [button.callback_data for row in generic_docs_return.edits[0][1]["reply_markup"].inline_keyboard for button in row],
                )

    def test_customer_guide_landing_renders_through_registered_handler_and_returns_home(self):
        dependencies = _main_menu_dependencies(False, [])
        dependencies.update({
            "public_pricing_locale": lambda lang: lang,
            "menu_text_main_guide_i18n": lambda lang: "actual guide menu" if lang == "vi" else "guide",
            "localized_start_menu_text": lambda *_args: "actual main menu",
            "localized_main_menu_keyboard": lambda *_args: _Markup([]),
            "time": SimpleNamespace(perf_counter=lambda: 1.0),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
        })
        namespace = _load_functions(
            "main_guide_keyboard", "localized_menu_content", "handle_menu_callback",
            **dependencies,
        )
        route_pattern = _registered_menu_pattern()
        context = SimpleNamespace(user_data={})

        guide_query = _Query(991128, "menu|main_guide")
        self.assertRegex(guide_query.data, route_pattern)
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=guide_query), context,
        ))
        self.assertEqual([((), {})], guide_query.answers)
        self.assertEqual("actual guide menu", guide_query.edits[0][0])
        guide_markup = guide_query.edits[0][1]["reply_markup"]
        guide_callbacks = [
            button.callback_data for row in guide_markup.inline_keyboard for button in row
            if button.callback_data
        ]
        self.assertIn("menu|main", guide_callbacks)

        # Guide/article controls are inspected as rendered UI only; none is dispatched.
        home_query = _Query(991128, "menu|main")
        self.assertRegex(home_query.data, route_pattern)
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=home_query), context,
        ))
        self.assertEqual([((), {})], home_query.answers)
        self.assertEqual("actual main menu", home_query.edits[0][0])

    def test_customer_guide_articles_return_to_guide_and_home_through_registered_handler(self):
        dependencies = _main_menu_dependencies(False, [])
        dependencies.update({
            "public_pricing_locale": lambda lang: lang,
            "normalize_user_language": lambda lang: lang or "vi",
            "GUIDE_SECTION_ALIASES": {},
            "ui_text": lambda _lang, key: {
                "common.back": "⬅️ Quay lại",
                "common.main_menu": "🏠 Menu chính",
            }[key],
            "guide_section_text_i18n": lambda section, _lang: f"article:{section}",
            "video_uiflow3_guide_text": lambda _lang: "video guide article",
            "menu_text_main_guide_i18n": lambda _lang: "actual guide menu",
            "localized_start_menu_text": lambda *_args: "actual main menu",
            "localized_main_menu_keyboard": lambda *_args: _Markup([]),
            "time": SimpleNamespace(perf_counter=lambda: 1.0),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
        })
        namespace = _load_functions(
            "normalize_guide_section_key", "guide_keyboard", "main_guide_keyboard",
            "video_uiflow3_guide_keyboard", "localized_menu_content", "handle_menu_callback",
            **dependencies,
        )
        route_pattern = _registered_menu_pattern()
        context = SimpleNamespace(user_data={})
        guide_query = _Query(991129, "menu|main_guide")
        self.assertRegex(guide_query.data, route_pattern)
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=guide_query), context,
        ))
        self.assertEqual("actual guide menu", guide_query.edits[0][0])

        guide_markup = guide_query.edits[0][1]["reply_markup"]
        article_callbacks = [
            button.callback_data
            for row in guide_markup.inline_keyboard
            for button in row
            if button.callback_data and button.callback_data.startswith("menu|guide_")
        ]
        self.assertEqual(7, len(article_callbacks))
        dispatched = []

        for callback in article_callbacks:
            with self.subTest(article=callback):
                self.assertRegex(callback, route_pattern)
                article_query = _Query(991129, callback)
                asyncio.run(namespace["handle_menu_callback"](
                    SimpleNamespace(callback_query=article_query), context,
                ))
                dispatched.append(callback)
                self.assertEqual([((), {})], article_query.answers)
                article_text, article_options = article_query.edits[0]
                if callback.startswith("menu|guide_video_ai"):
                    self.assertEqual("video guide article", article_text)
                else:
                    self.assertEqual(f"article:{callback.split('|')[1][6:]}", article_text)

                article_markup = article_options["reply_markup"]
                back = next(
                    button for row in article_markup.inline_keyboard for button in row
                    if button.text.startswith(("⬅", "🔙"))
                )
                home = next(
                    button for row in article_markup.inline_keyboard for button in row
                    if button.text.startswith("🏠")
                )
                self.assertEqual("menu|main_guide", back.callback_data)
                self.assertEqual("menu|main", home.callback_data)

                back_query = _Query(991129, back.callback_data)
                asyncio.run(namespace["handle_menu_callback"](
                    SimpleNamespace(callback_query=back_query), context,
                ))
                dispatched.append(back.callback_data)
                self.assertEqual("actual guide menu", back_query.edits[0][0])

                home_query = _Query(991129, home.callback_data)
                asyncio.run(namespace["handle_menu_callback"](
                    SimpleNamespace(callback_query=home_query), context,
                ))
                dispatched.append(home.callback_data)
                self.assertEqual("actual main menu", home_query.edits[0][0])

        self.assertEqual(7, len([item for item in dispatched if item.startswith("menu|guide_")]))
        self.assertNotIn("create_media|quick_video", dispatched)
        self.assertNotIn("menu|main_video", dispatched)

    def test_legacy_video_guide_entry_keeps_video_menu_back(self):
        dependencies = _main_menu_dependencies(False, [])
        dependencies.update({
            "normalize_user_language": lambda lang: lang or "vi",
            "ui_text": lambda _lang, key: {
                "common.back": "⬅️ Quay lại",
                "common.main_menu": "🏠 Menu chính",
            }[key],
            "video_uiflow3_guide_text": lambda _lang: "video guide article",
            "time": SimpleNamespace(perf_counter=lambda: 1.0),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
        })
        namespace = _load_functions(
            "video_uiflow3_guide_keyboard", "localized_menu_content", "handle_menu_callback",
            **dependencies,
        )
        callback = "menu|guide_video_ai"
        self.assertRegex(callback, _registered_menu_pattern())
        query = _Query(991130, callback)
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(user_data={}),
        ))
        self.assertEqual("video guide article", query.edits[0][0])
        markup = query.edits[0][1]["reply_markup"]
        back = next(
            button for row in markup.inline_keyboard for button in row
            if button.text.startswith("⬅")
        )
        self.assertEqual("menu|main_video", back.callback_data)

    def test_vietnamese_guide_support_label_matches_its_support_destination(self):
        dependencies = _main_menu_dependencies(False, [])
        dependencies["public_pricing_locale"] = lambda lang: lang
        namespace = _load_functions("main_guide_keyboard", **dependencies)
        markup = namespace["main_guide_keyboard"]("vi")
        support_button = next(
            button for row in markup.inline_keyboard for button in row
            if button.callback_data == "menu|support"
        )

        self.assertEqual("👨‍💼 Hỗ trợ", support_button.text)
        self.assertRegex(support_button.callback_data, _registered_menu_pattern())

    def test_customer_root_support_home_returns_to_main_menu(self):
        dependencies = _main_menu_dependencies(False, [])
        dependencies.update({
            "time": SimpleNamespace(perf_counter=lambda: 1.0),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
            "human_support_text": lambda _lang: "support screen",
            "support_read_origin_keyboard": lambda markup, *_args, **_kwargs: markup,
            "support_form_origin_keyboard": lambda markup, *_args, **_kwargs: markup,
        })
        namespace = _load_functions(
            "handle_menu_callback", "human_support_keyboard",
            "support_read_origin_keyboard", "support_form_origin_keyboard",
            **dependencies,
        )
        main_keyboard = _load_functions(
            "localized_main_menu_keyboard", **dependencies,
        )["localized_main_menu_keyboard"](False, "vi")
        support_callback = next(
            button.callback_data
            for row in main_keyboard.inline_keyboard
            for button in row
            if button.callback_data == "menu|support"
        )
        pattern = _registered_menu_pattern()
        self.assertRegex(support_callback, pattern)
        support_query = _Query(991125, support_callback)
        context = SimpleNamespace(user_data={})

        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=support_query), context,
        ))

        support_markup = support_query.edits[0][1]["reply_markup"]
        home = next(
            button.callback_data
            for row in support_markup.inline_keyboard
            for button in row
            if button.callback_data == "menu|main"
        )
        self.assertEqual("support screen", support_query.edits[0][0])
        self.assertEqual([((), {})], support_query.answers)
        self.assertRegex(home, pattern)
        home_query = _Query(991125, home)
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=home_query), context,
        ))
        self.assertEqual("existing screen:main", home_query.edits[0][0])
        self.assertEqual([((), {})], home_query.answers)

    def test_customer_root_chat_pro_opens_read_only_menu_and_home_returns_to_main(self):
        dependencies = _main_menu_dependencies(False, [])
        user_reads = []
        mode_writes = []
        root_copy = dependencies["public_hub_copy"]
        chat_copy = {
            "chat_menu_title": "Chat menu",
            "chat_mode_label": "Mode",
            "chat_mode_pro": "Pro",
            "chat_mode_free": "Free",
            "profile_unlimited": "Unlimited",
            "chat_balance_label": "Balance",
            "chat_free_summary": "Free summary",
            "chat_pro_summary": "Pro summary {rate}",
            "chat_memory_summary": "Memory summary",
            "chat_owner_admin_summary": "Owner summary",
            "chat_pro_disable": "Disable Pro",
            "chat_pro_enable": "Enable Pro",
            "chat_free_label": "Free Chat",
            "chat_account_label": "Account",
            "main_menu": "Main menu",
        }
        dependencies.update({
            "html": html,
            "time": SimpleNamespace(perf_counter=lambda: 1.0),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
            "ensure_user_modes": lambda _uid: {"chat_mode": "normal"},
            "normalize_chat_tier": lambda tier: tier,
            "get_user": lambda uid: user_reads.append(uid) or [37],
            "set_user_chat_mode": lambda *args, **kwargs: mode_writes.append((args, kwargs)),
            "public_chat_runtime": SimpleNamespace(CHAT_PRO_RATE_LABEL="fixture rate"),
            "public_hub_copy": lambda lang: {**root_copy(lang), **chat_copy},
        })
        ui = _load_functions("public_chat_menu_text", "public_chat_menu_keyboard", **dependencies)
        dependencies.update(ui)
        root = _load_functions("localized_main_menu_keyboard", **dependencies)[
            "localized_main_menu_keyboard"
        ](False, "vi")
        chat_entry = next(
            button.callback_data
            for row in root.inline_keyboard
            for button in row
            if button.callback_data == "menu|chat_pro"
        )
        pattern = _registered_menu_pattern()
        self.assertRegex(chat_entry, pattern)

        namespace = _load_functions("handle_menu_callback", **dependencies)
        context = SimpleNamespace(user_data={})
        chat_query = _Query(991126, chat_entry)
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=chat_query), context,
        ))

        self.assertEqual([((), {})], chat_query.answers)
        self.assertEqual(1, len(chat_query.edits))
        chat_text, chat_markup = chat_query.edits[0]
        self.assertIn("Chat menu", chat_text)
        self.assertIn("37 Xu", chat_text)
        home = next(
            button.callback_data
            for row in chat_markup["reply_markup"].inline_keyboard
            for button in row
            if button.callback_data == "menu|main"
        )
        self.assertRegex(home, pattern)

        home_query = _Query(991126, home)
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=home_query), context,
        ))
        self.assertEqual([((), {})], home_query.answers)
        self.assertEqual(
            [("existing screen:main", {"reply_markup": "existing keyboard:main"})],
            home_query.edits,
        )
        self.assertEqual([991126], user_reads, "opening Chat Pro reads the fixture balance once")
        self.assertEqual([], mode_writes, "opening the menu must not toggle Chat Pro or alter billing")

    def test_customer_root_account_renders_actual_keyboard_and_home_returns_to_main(self):
        dependencies = _main_menu_dependencies(False, [])
        root_copy = dependencies["public_hub_copy"]
        profile_copy = {
            "profile_title": "Account",
            "profile_body": "Account body",
            "profile_unlimited": "Unlimited",
            "profile_id": "ID",
            "profile_tier": "Tier",
            "profile_balance": "Balance",
            "profile_detail_hint": "Account details",
            "profile_topup": "Top up",
            "profile_pricing": "Pricing",
            "profile_packages": "Packages",
            "profile_membership": "Membership",
            "profile_xu_guide": "Xu guide",
            "profile_referral_link": "Referral link",
            "profile_referral_stats": "Referral stats",
            "profile_referral_policy": "Referral policy",
            "profile_change_language": "Language",
            "profile_back_account": "Back to Account",
            "main_menu": "Main menu",
        }
        dependencies.update({
            "time": SimpleNamespace(perf_counter=lambda: 1.0),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
            "html": html,
            "get_user": lambda uid: (37, 120, False),
            "get_role_badge": lambda _uid: "Member",
            "user_package_account_short_text": lambda _uid, _lang: "Packages: none",
            "user_package_summary_text": lambda _uid, lang="vi": "Packages: fixture only",
            "referral_account_link_text": lambda _uid, _bot, _lang: "Referral link fixture",
            "referral_account_stats_text": lambda _uid, _lang: "Referral stats fixture",
            "referral_account_policy_text": lambda _uid, _lang: "Referral policy fixture",
            "BOT_USERNAME": "fixture_bot",
            "public_hub_copy": lambda lang: {**root_copy(lang), **profile_copy},
            "localized_start_menu_text": lambda _uid, _lang: "MAIN SCREEN",
        })
        ui = _load_functions(
            "localized_main_menu_keyboard", "main_profile_keyboard", "profile_child_keyboard",
            "menu_text_main_profile_i18n", "localized_menu_content",
            **dependencies,
        )
        dependencies.update({
            name: ui[name]
            for name in (
                "localized_main_menu_keyboard", "main_profile_keyboard",
                "profile_child_keyboard",
                "menu_text_main_profile_i18n", "localized_menu_content",
            )
        })
        root = ui["localized_main_menu_keyboard"](False, "vi")
        account_entry = next(
            button.callback_data
            for row in root.inline_keyboard
            for button in row
            if button.callback_data == "menu|main_profile"
        )
        self.assertRegex(account_entry, _registered_menu_pattern())

        namespace = _load_functions("handle_menu_callback", **dependencies)
        context = SimpleNamespace(user_data={})
        account_query = _Query(991127, account_entry)
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=account_query), context,
        ))
        self.assertEqual([((), {})], account_query.answers)
        self.assertEqual(1, len(account_query.edits))
        self.assertIn("<b>Account</b>", account_query.edits[0][0])
        self.assertIn("37 Xu", account_query.edits[0][0])
        self.assertIn("Member", account_query.edits[0][0])

        account_markup = account_query.edits[0][1]["reply_markup"]
        account_buttons = [button for row in account_markup.inline_keyboard for button in row]
        emitted = {button.callback_data for button in account_buttons}
        expected = {
            "menu|main_topup|main_profile": "handle_menu_callback",
            "pricing|main|profile": "handle_pricing_callback",
            "menu|profile_packages": "handle_menu_callback",
            "pricing|member|profile": "handle_pricing_callback",
            "menu|guide_credits|main_profile": "handle_menu_callback",
            "menu|support|main_profile": "handle_menu_callback",
            "menu|profile_ref_link": "handle_menu_callback",
            "menu|profile_ref_stats": "handle_menu_callback",
            "menu|profile_ref_policy": "handle_menu_callback",
            "back_lang|profile": "handle_language_callback",
            "menu|main": "handle_menu_callback",
        }
        self.assertEqual(set(expected), emitted)
        for callback, handler_name in expected.items():
            with self.subTest(callback=callback):
                self.assertRegex(callback, _registered_pattern(handler_name))

        home_query = _Query(991127, "menu|main")
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=home_query), context,
        ))
        self.assertEqual([((), {})], home_query.answers)
        self.assertEqual("MAIN SCREEN", home_query.edits[0][0])
        self.assertIsInstance(home_query.edits[0][1]["reply_markup"], _Markup)

        packages_callback = next(
            button.callback_data
            for row in account_markup.inline_keyboard
            for button in row
            if button.callback_data == "menu|profile_packages"
        )
        self.assertRegex(packages_callback, _registered_menu_pattern())
        packages_query = _Query(991127, packages_callback)
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=packages_query), context,
        ))
        self.assertEqual([((), {})], packages_query.answers)
        self.assertEqual("Packages: fixture only", packages_query.edits[0][0])
        packages_markup = packages_query.edits[0][1]["reply_markup"]
        packages_callbacks = [
            button.callback_data
            for row in packages_markup.inline_keyboard
            for button in row
        ]
        self.assertIn("menu|main_profile", packages_callbacks)
        self.assertIn("menu|main", packages_callbacks)

        account_back = next(
            callback for callback in packages_callbacks
            if callback == "menu|main_profile"
        )
        self.assertRegex(account_back, _registered_menu_pattern())
        account_return_query = _Query(991127, account_back)
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=account_return_query), context,
        ))
        self.assertEqual([((), {})], account_return_query.answers)
        self.assertIn("<b>Account</b>", account_return_query.edits[0][0])
        returned_account_callbacks = [
            button.callback_data
            for row in account_return_query.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertEqual(
            [button.callback_data for button in account_buttons],
            returned_account_callbacks,
        )

        for referral_callback, expected_text in (
            ("menu|profile_ref_link", "Referral link fixture"),
            ("menu|profile_ref_stats", "Referral stats fixture"),
            ("menu|profile_ref_policy", "Referral policy fixture"),
        ):
            with self.subTest(referral_callback=referral_callback):
                self.assertRegex(referral_callback, _registered_menu_pattern())
                referral_query = _Query(991127, referral_callback)
                asyncio.run(namespace["handle_menu_callback"](
                    SimpleNamespace(callback_query=referral_query), context,
                ))
                self.assertEqual([((), {})], referral_query.answers)
                self.assertEqual(expected_text, referral_query.edits[0][0])
                child_callbacks = [
                    button.callback_data
                    for row in referral_query.edits[0][1]["reply_markup"].inline_keyboard
                    for button in row
                ]
                self.assertEqual(["menu|main_profile", "menu|main"], child_callbacks)

                referral_back = _Query(991127, "menu|main_profile")
                asyncio.run(namespace["handle_menu_callback"](
                    SimpleNamespace(callback_query=referral_back), context,
                ))
                self.assertEqual([((), {})], referral_back.answers)
                self.assertIn("<b>Account</b>", referral_back.edits[0][0])
                self.assertEqual(
                    [button.callback_data for button in account_buttons],
                    [
                        button.callback_data
                        for row in referral_back.edits[0][1]["reply_markup"].inline_keyboard
                        for button in row
                    ],
                )

    def test_profile_command_registration_sends_the_actual_localized_account_keyboard(self):
        class Copy(dict):
            def __missing__(self, key):
                return key

        side_effects = []
        locale_inputs = []

        async def inert_birthday_check(*_args):
            side_effects.append("birthday-check")

        def copy_for_locale(lang):
            locale_inputs.append(lang)
            return Copy()

        dependencies = _main_menu_dependencies(False, [])
        dependencies.update({
            "html": html,
            "public_pricing_locale": lambda lang: locale_inputs.append(lang) or lang,
            "get_user_language": lambda _uid: "en",
            "public_account_flow_copy": lambda lang: locale_inputs.append(lang) or Copy(
                profile_title="Account", save_service_xu="Save {discount}%"
            ),
            "maybe_auto_grant_birthday_gift": inert_birthday_check,
            "get_user": lambda *_args: (100, 20, False),
            "get_member_profile": lambda _uid: {"total_paid_vnd": 0},
            "referral_stats_for_user": lambda _uid: {"pending": 0, "rewarded": 0, "reward_xu": 0},
            "admin_display_badge": lambda _uid: "",
            "get_role_badge": lambda _uid: "Member",
            "public_hub_copy": copy_for_locale,
            "referral_link_for_user": lambda _uid: "https://example.test/ref",
            "birthday_gift_status": lambda _uid: {"birthday": None},
            "get_user_plan": lambda _uid: {"active": False},
            "get_member_service_discount_rate": lambda _uid: 0,
        })
        namespace = _load_functions("cmd_profile", "main_profile_keyboard", **dependencies)
        registrations = []
        namespace.update({
            "CommandHandler": lambda command, callback: SimpleNamespace(command=command, callback=callback),
            "tg_app": SimpleNamespace(add_handler=registrations.append),
        })
        registration_line = next(
            line.strip() for line in BOT_SOURCE.splitlines()
            if 'CommandHandler("profile"' in line and "cmd_profile" in line
        )
        exec(registration_line, namespace)
        self.assertEqual(1, len(registrations))
        self.assertEqual("profile", registrations[0].command)
        self.assertIs(registrations[0].callback, namespace["cmd_profile"])

        sent = {}

        async def capture_reply(text, **kwargs):
            sent["text"] = text
            sent.update(kwargs)

        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=987654321, first_name="Fixture"),
            message=SimpleNamespace(reply_text=capture_reply),
        )
        coroutine = registrations[0].callback(update, SimpleNamespace())
        try:
            coroutine.send(None)
        except StopIteration:
            pass
        else:
            coroutine.close()
            self.fail("profile command fixture unexpectedly yielded I/O")

        self.assertEqual(["birthday-check"], side_effects)
        self.assertEqual("HTML", sent["parse_mode"])
        self.assertIn("Account", sent["text"])
        expected = namespace["main_profile_keyboard"]("en")
        self.assertEqual(
            [[button.callback_data for button in row] for row in expected.inline_keyboard],
            [[button.callback_data for button in row] for row in sent["reply_markup"].inline_keyboard],
        )
        self.assertEqual(6, len(sent["reply_markup"].inline_keyboard))
        self.assertEqual({"en"}, set(locale_inputs))

        callback_dependencies = _main_menu_dependencies(False, [])
        callback_dependencies.update({
            "time": SimpleNamespace(perf_counter=lambda: 1.0),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
            "get_user_language": lambda _uid: "en",
            "public_hub_copy": copy_for_locale,
            "main_profile_keyboard": namespace["main_profile_keyboard"],
            "user_package_summary_text": lambda _uid, lang="vi": "Packages: command fixture",
            "menu_text_main_profile_i18n": lambda *_args: "Account screen from /profile",
            "localized_start_menu_text": lambda *_args: "Main screen from /profile",
            "localized_main_menu_keyboard": lambda *_args: _Markup([]),
        })
        callback_namespace = _load_functions(
            "profile_child_keyboard", "localized_menu_content", "handle_menu_callback",
            **callback_dependencies,
        )
        menu_registrations = []
        callback_namespace.update({
            "tg_app": SimpleNamespace(add_handler=menu_registrations.append),
            "CallbackQueryHandler": lambda callback, pattern: SimpleNamespace(
                callback=callback,
                pattern=re.compile(pattern),
            ),
        })
        menu_registration = next(
            line.strip()
            for line in BOT_SOURCE.splitlines()
            if "tg_app.add_handler(CallbackQueryHandler(handle_menu_callback," in line
        )
        exec(menu_registration, callback_namespace)
        menu_route = next(
            item for item in menu_registrations
            if item.callback is callback_namespace["handle_menu_callback"]
        )
        context = SimpleNamespace(user_data={})

        def dispatch_command_keyboard(callback_data):
            self.assertIsNotNone(menu_route.pattern.match(callback_data))
            query = _Query(987654321, callback_data)
            _run_no_io(menu_route.callback(
                SimpleNamespace(callback_query=query),
                context,
            ))
            self.assertEqual([((), {})], query.answers)
            self.assertEqual(1, len(query.edits))
            return query

        packages_callback = next(
            button.callback_data
            for row in sent["reply_markup"].inline_keyboard
            for button in row
            if button.callback_data == "menu|profile_packages"
        )
        packages = dispatch_command_keyboard(packages_callback)
        self.assertEqual("Packages: command fixture", packages.edits[0][0])
        child_callbacks = [
            button.callback_data
            for row in packages.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertEqual(["menu|main_profile", "menu|main"], child_callbacks)

        account = dispatch_command_keyboard(child_callbacks[0])
        self.assertEqual("Account screen from /profile", account.edits[0][0])
        self.assertEqual(
            [[button.callback_data for button in row]
             for row in sent["reply_markup"].inline_keyboard],
            [[button.callback_data for button in row]
             for row in account.edits[0][1]["reply_markup"].inline_keyboard],
        )
        home = dispatch_command_keyboard(child_callbacks[1])
        self.assertEqual("Main screen from /profile", home.edits[0][0])

    def test_customer_feedback_root_button_dispatches_to_registered_feedback_handler(self):
        effects = []
        dependencies = _main_menu_dependencies(False, effects)
        keyboard_namespace = _load_functions("localized_main_menu_keyboard", **dependencies)
        markup = keyboard_namespace["localized_main_menu_keyboard"](False, "vi")
        feedback_callback = next(
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.callback_data == "feedback|start"
        )
        registration = re.search(
            r"CallbackQueryHandler\(\s*handle_feedback_callback\s*,\s*pattern\s*=\s*(r?['\"][^'\"]+['\"])\s*\)",
            BOT_SOURCE,
        )
        self.assertIsNotNone(registration, "feedback callback must be registered")
        self.assertRegex(feedback_callback, re.compile(ast.literal_eval(registration.group(1))))

        async def safe_edit_or_send(query, text, **kwargs):
            query.edits.append((text, kwargs))

        dependencies.update({
            "user_ui_lang": lambda _uid: "vi",
            "clear_feedback_pending": lambda uid: effects.append(("clear_feedback_pending", uid)),
            "clear_support_ticket_pending": lambda uid: effects.append(("clear_support_ticket_pending", uid)),
            "feedback_start_text": lambda lang: f"feedback-{lang}",
            "feedback_category_keyboard": lambda lang: f"categories-{lang}",
            "safe_edit_or_send": safe_edit_or_send,
        })
        namespace = _load_functions("handle_feedback_callback", **dependencies)
        query = _Query(991124, feedback_callback)
        asyncio.run(namespace["handle_feedback_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(),
        ))

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(
            effects,
            [("clear_feedback_pending", 991124), ("clear_support_ticket_pending", 991124)],
        )
        self.assertEqual(
            query.edits,
            [("feedback-vi", {"parse_mode": "HTML", "reply_markup": "categories-vi"})],
        )

    def _emitted_admin_callback(self):
        keyboard_dependencies = _main_menu_dependencies(True, [])
        keyboard_namespace = _load_functions(
            "localized_main_menu_keyboard", **keyboard_dependencies
        )
        markup = keyboard_namespace["localized_main_menu_keyboard"](True, "vi")
        callbacks = [
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.callback_data
        ]
        self.assertIn("menu|admin", callbacks)
        self.assertRegex("menu|admin", _registered_menu_pattern())
        return "menu|admin"

    def test_revoked_admin_root_button_is_denied_once_before_state_cleanup(self):
        effects = []
        dependencies = _main_menu_dependencies(False, effects)
        namespace = _load_functions("handle_menu_callback", **dependencies)
        query = _Query(991122, self._emitted_admin_callback())
        pending = {"video_tail_pending": "must remain"}
        context = SimpleNamespace(user_data=pending)

        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=query), context,
        ))

        self.assertEqual(
            query.answers,
            [(("Khu vực này chỉ dành cho Admin.",), {"show_alert": True})],
        )
        self.assertEqual(query.edits, [], "stale admin buttons must not render an admin screen")
        self.assertEqual(effects, [], "denial must not clear user pending state")
        self.assertEqual(pending, {"video_tail_pending": "must remain"})

    def test_authorized_admin_root_button_keeps_ack_and_destination(self):
        effects = []
        dependencies = _main_menu_dependencies(True, effects)
        namespace = _load_functions("handle_menu_callback", **dependencies)
        query = _Query(123, self._emitted_admin_callback())

        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(user_data={}),
        ))

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(
            query.edits,
            [("existing screen:admin", {"reply_markup": "existing keyboard:admin"})],
        )

    def test_knowledge_vault_home_returns_to_main_via_registered_menu_handler(self):
        keyboard_namespace = _load_functions(
            "vault_admin_keyboard",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
        )
        keyboard = keyboard_namespace["vault_admin_keyboard"]()
        callbacks = [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        ]
        self.assertIn("menu|main", callbacks)
        self.assertRegex("vault|status", _registered_pattern("handle_knowledge_vault_callback"))
        self.assertRegex("menu|main", _registered_menu_pattern())

        dependencies = _main_menu_dependencies(True, [])
        dependencies["time"] = SimpleNamespace(perf_counter=lambda: 0.0)
        dependencies["logger"] = SimpleNamespace(info=lambda *_args, **_kwargs: None)
        namespace = _load_functions("handle_menu_callback", **dependencies)
        query = _Query(123, "menu|main")
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(user_data={}),
        ))

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(query.edits, [
            ("existing screen:main", {"reply_markup": "existing keyboard:main"}),
        ])

    def test_knowledge_vault_status_dispatches_emitted_control_to_read_only_status(self):
        keyboard_namespace = _load_functions(
            "vault_admin_keyboard",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
        )
        keyboard = keyboard_namespace["vault_admin_keyboard"]()
        status_button = next(
            button
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data == "vault|status"
        )
        self.assertRegex(
            status_button.callback_data,
            _registered_pattern("handle_knowledge_vault_callback"),
        )

        status = {"importer": "ready", "pending": 0}
        effects = []

        class _Importer:
            def debug_status(self):
                effects.append("read_status")
                return status

        async def edit_message_text(text, **kwargs):
            effects.append(("edit", text, kwargs))

        query = _Query(123, status_button.callback_data)
        query.edit_message_text = edit_message_text
        dependencies = {
            "is_admin_user": lambda user_id: user_id == 123,
            "toan_knowledge_vault": lambda: effects.append("vault_factory") or object(),
            "toan_vault_importer": lambda: _Importer(),
            "vault_json_block": lambda payload: f"<status>{payload!r}</status>",
            "vault_admin_keyboard": lambda: keyboard,
        }
        namespace = _load_functions("handle_knowledge_vault_callback", **dependencies)

        _run_no_io(namespace["handle_knowledge_vault_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(),
        ))

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(effects, [
            "vault_factory",
            "read_status",
            (
                "edit",
                "🧠 <b>Kho học liệu TOAN AAS</b>\n\n<status>{'importer': 'ready', 'pending': 0}</status>",
                {"parse_mode": "HTML", "reply_markup": keyboard},
            ),
        ])

    def test_knowledge_vault_instruction_shortcuts_are_labeled_as_guides(self):
        keyboard_namespace = _load_functions(
            "vault_admin_keyboard",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
        )
        keyboard = keyboard_namespace["vault_admin_keyboard"]()
        labels_by_callback = {
            button.callback_data: button.text
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        }

        self.assertTrue(labels_by_callback["vault|import"].startswith("📘 Hướng dẫn import"))
        self.assertTrue(labels_by_callback["vault|search"].startswith("📘 Hướng dẫn tìm kiếm"))
        self.assertIn("vault|prompts", labels_by_callback)
        self.assertIn("vault|assets|video", labels_by_callback)
        self.assertIn("vault|assets|image", labels_by_callback)
        self.assertIn("vault|assets|audio", labels_by_callback)
        self.assertIn("vault|review", labels_by_callback)
        self.assertIn("menu|main", labels_by_callback)

    def test_knowledge_vault_import_and_search_guides_dispatch_without_vault_operations(self):
        keyboard_namespace = _load_functions(
            "vault_admin_keyboard",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
        )
        keyboard = keyboard_namespace["vault_admin_keyboard"]()
        expected_guides = {
            "vault|import": (
                "📥 <b>Import học liệu</b>\n\n"
                "• <code>/vault_import_folder</code> dùng thư mục import mặc định.\n"
                "• <code>/vault_import_video_refs</code> nhập Kho Video tham khảo.\n"
                "• Reply video/ảnh/audio/file rồi gửi <code>/vault_import_file</code>.\n"
                "• Prompt text: <code>/vault_import_file Video prompt: ...</code>\n"
                "• Online refs: <code>/vault_import_online_sources &lt;url1&gt; &lt;url2&gt;</code>\n"
                "• Sync/backup: <code>/vault_sync_index</code>, <code>/vault_backup</code>"
            ),
            "vault|search": (
                "🔎 Dùng <code>/kho_prompt &lt;từ khóa&gt;</code> để tìm prompt public/admin, "
                "hoặc <code>/vault_prompt_debug &lt;id&gt;</code> để xem chi tiết admin."
            ),
        }

        for callback_data, expected_text in expected_guides.items():
            with self.subTest(callback_data=callback_data):
                button = next(
                    button
                    for row in keyboard.inline_keyboard
                    for button in row
                    if button.callback_data == callback_data
                )
                self.assertTrue(button.text.startswith("📘 Hướng dẫn"))
                self.assertRegex(
                    callback_data,
                    _registered_pattern("handle_knowledge_vault_callback"),
                )

                effects = []
                query = _Query(123, callback_data)

                async def edit_message_text(text, **kwargs):
                    effects.append(("edit", text, kwargs))

                query.edit_message_text = edit_message_text
                namespace = _load_functions(
                    "handle_knowledge_vault_callback",
                    is_admin_user=lambda user_id: user_id == 123,
                    toan_knowledge_vault=lambda: effects.append("vault_factory") or object(),
                    toan_vault_importer=lambda: self.fail("guide callback must not access importer"),
                    vault_admin_keyboard=lambda: keyboard,
                )

                _run_no_io(namespace["handle_knowledge_vault_callback"](
                    SimpleNamespace(callback_query=query), SimpleNamespace(),
                ))

                self.assertEqual(query.answers, [((), {})])
                self.assertEqual(effects, [
                    "vault_factory",
                    ("edit", expected_text, {"parse_mode": "HTML", "reply_markup": keyboard}),
                ])

    def test_knowledge_vault_nonempty_prompt_and_review_lists_retain_back_and_home(self):
        keyboard_namespace = _load_functions(
            "vault_admin_keyboard",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
        )
        root_keyboard = keyboard_namespace["vault_admin_keyboard"]()
        fixture_prompts = {
            "vault|prompts": [{"id": 71, "prompt_text": "fixture prompt", "status": "approved"}],
            "vault|review": [{"id": 72, "prompt_text": "fixture draft", "status": "pending"}],
        }

        for emitted_action, prompts in fixture_prompts.items():
            with self.subTest(emitted_action=emitted_action):
                action_button = next(
                    button
                    for row in root_keyboard.inline_keyboard
                    for button in row
                    if button.callback_data == emitted_action
                )
                self.assertRegex(
                    action_button.callback_data,
                    _registered_pattern("handle_knowledge_vault_callback"),
                )
                effects = []

                class _VaultFixture:
                    def search_prompt(self, **kwargs):
                        effects.append(("search_prompt", kwargs))
                        return prompts

                query = _Query(123, action_button.callback_data)

                async def edit_message_text(text, **kwargs):
                    effects.append(("edit", text, kwargs))

                query.edit_message_text = edit_message_text
                namespace = _load_functions(
                    "handle_knowledge_vault_callback",
                    is_admin_user=lambda user_id: user_id == 123,
                    toan_knowledge_vault=lambda: effects.append("vault_factory") or _VaultFixture(),
                    vault_prompt_list_text=lambda items, title="fixture list": f"{title}:{len(items)}",
                    InlineKeyboardButton=_Button,
                    InlineKeyboardMarkup=_Markup,
                    vault_admin_keyboard=lambda: root_keyboard,
                )

                _run_no_io(namespace["handle_knowledge_vault_callback"](
                    SimpleNamespace(callback_query=query), SimpleNamespace(),
                ))

                self.assertEqual(query.answers, [((), {})])
                self.assertEqual(effects[0], "vault_factory")
                list_keyboard = effects[-1][2]["reply_markup"]
                emitted_callbacks = [
                    button.callback_data
                    for row in list_keyboard.inline_keyboard
                    for button in row
                    if button.callback_data
                ]
                self.assertTrue(
                    any(value.startswith("vault|use|") for value in emitted_callbacks)
                    or any(value.startswith("vault|approve_prompt|") for value in emitted_callbacks)
                )
                self.assertIn("vault|status", emitted_callbacks)
                self.assertIn("menu|main", emitted_callbacks)
                back_button = next(
                    button
                    for row in list_keyboard.inline_keyboard
                    for button in row
                    if button.callback_data == "vault|status"
                )
                home_button = next(
                    button
                    for row in list_keyboard.inline_keyboard
                    for button in row
                    if button.callback_data == "menu|main"
                )
                self.assertIn("Quay lại", back_button.text)
                self.assertRegex(
                    back_button.callback_data,
                    _registered_pattern("handle_knowledge_vault_callback"),
                )
                self.assertRegex(home_button.callback_data, _registered_menu_pattern())

                back_query = _Query(123, back_button.callback_data)
                back_edits = []

                async def edit_vault_root(text, **kwargs):
                    back_edits.append((text, kwargs))

                back_query.edit_message_text = edit_vault_root

                class _ImporterFixture:
                    def debug_status(self):
                        return {"status": "fixture"}

                back_namespace = _load_functions(
                    "handle_knowledge_vault_callback",
                    is_admin_user=lambda user_id: user_id == 123,
                    toan_knowledge_vault=object,
                    toan_vault_importer=_ImporterFixture,
                    vault_json_block=lambda payload: f"<status>{payload!r}</status>",
                    vault_admin_keyboard=lambda: root_keyboard,
                )
                _run_no_io(back_namespace["handle_knowledge_vault_callback"](
                    SimpleNamespace(callback_query=back_query), SimpleNamespace(),
                ))
                self.assertEqual(back_query.answers, [((), {})])
                self.assertEqual(back_edits[-1][1]["reply_markup"], root_keyboard)
                self.assertIn("Kho học liệu TOAN AAS", back_edits[-1][0])

                home_dependencies = _main_menu_dependencies(True, [])
                home_dependencies["time"] = SimpleNamespace(perf_counter=lambda: 0.0)
                home_dependencies["logger"] = SimpleNamespace(info=lambda *_args, **_kwargs: None)
                home_namespace = _load_functions("handle_menu_callback", **home_dependencies)
                home_query = _Query(123, home_button.callback_data)
                _run_no_io(home_namespace["handle_menu_callback"](
                    SimpleNamespace(callback_query=home_query), SimpleNamespace(user_data={}),
                ))
                self.assertEqual(home_query.answers, [((), {})])
                self.assertEqual(home_query.edits, [
                    ("existing screen:main", {"reply_markup": "existing keyboard:main"}),
                ])

    def test_knowledge_vault_asset_category_buttons_dispatch_to_matching_read_only_lists(self):
        root_keyboard = _load_functions(
            "vault_admin_keyboard",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
        )["vault_admin_keyboard"]()
        category_fixtures = {
            "vault|assets|video": ("video", "Video fixture", "🎬 Kho Video"),
            "vault|assets|image": ("image", "Image fixture", "🖼 Kho Ảnh"),
            "vault|assets|audio": ("audio", "Audio fixture", "🎵 Kho Nhạc/SFX"),
        }

        for callback_data, (category, title, expected_button_text) in category_fixtures.items():
            with self.subTest(callback_data=callback_data):
                button = next(
                    button
                    for row in root_keyboard.inline_keyboard
                    for button in row
                    if button.callback_data == callback_data
                )
                self.assertEqual(button.text, expected_button_text)
                self.assertRegex(
                    button.callback_data,
                    _registered_pattern("handle_knowledge_vault_callback"),
                )
                list_calls = []
                rendered = []

                class _VaultFixture:
                    def list_assets(self, **kwargs):
                        list_calls.append(kwargs)
                        return [{"type": kwargs["asset_type"]}]

                query = _Query(123, button.callback_data)

                async def edit_message_text(text, **kwargs):
                    rendered.append((text, kwargs))

                query.edit_message_text = edit_message_text
                namespace = _load_functions(
                    "handle_knowledge_vault_callback",
                    is_admin_user=lambda user_id: user_id == 123,
                    toan_knowledge_vault=_VaultFixture,
                    vault_asset_list_text=lambda assets, title: f"{title}:{len(assets)}",
                    VAULT_ASSET_LABELS={
                        "video": "Video fixture",
                        "image": "Image fixture",
                        "audio": "Audio fixture",
                    },
                    vault_admin_keyboard=lambda: root_keyboard,
                )

                _run_no_io(namespace["handle_knowledge_vault_callback"](
                    SimpleNamespace(callback_query=query), SimpleNamespace(),
                ))

                self.assertEqual(query.answers, [((), {})])
                if category == "audio":
                    self.assertEqual(
                        [call["asset_type"] for call in list_calls],
                        ["music", "sfx", "voice", "audio"],
                    )
                    self.assertTrue(all(call["public_only"] is False and call["limit"] == 8 for call in list_calls))
                    expected_count = 4
                else:
                    self.assertEqual(list_calls, [{
                        "asset_type": category,
                        "public_only": False,
                        "limit": 12,
                    }])
                    expected_count = 1
                self.assertEqual(rendered, [(
                    f"{title}:{expected_count}",
                    {"parse_mode": "HTML", "reply_markup": root_keyboard},
                )])
                navigation_callbacks = {
                    button.callback_data
                    for row in root_keyboard.inline_keyboard
                    for button in row
                    if button.callback_data
                }
                self.assertIn("vault|status", navigation_callbacks)
                self.assertIn("menu|main", navigation_callbacks)

    def test_admin_vault_review_command_emits_registered_back_and_home(self):
        self.assertIn(
            'CommandHandler("vault_review", admin_internal_command(cmd_vault_review))',
            BOT_SOURCE,
        )
        root_keyboard = _load_functions(
            "vault_admin_keyboard",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
        )["vault_admin_keyboard"]()
        fixture_drafts = [{"id": 91, "prompt_text": "fixture draft", "status": "pending"}]
        command_effects = []

        class _VaultFixture:
            def search_prompt(self, **kwargs):
                command_effects.append(("search_prompt", kwargs))
                return fixture_drafts

        async def reply_text(text, **kwargs):
            command_effects.append(("reply", text, kwargs))

        command_namespace = _load_functions(
            "cmd_vault_review",
            toan_knowledge_vault=lambda: _VaultFixture(),
            vault_prompt_list_text=lambda items, title: f"{title}:{len(items)}",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
            vault_admin_keyboard=lambda: root_keyboard,
        )
        wrapper_namespace = _load_functions(
            "admin_internal_command",
            is_admin_user=lambda user_id: user_id == 123,
            record_anomaly=lambda *_args, **_kwargs: self.fail("authorized admin must not be denied"),
            extract_command_name=lambda _update: "vault_review",
            reply_internal_customer_feature=lambda *_args: self.fail("admin wrapper must reach command"),
        )
        wrapped_command = wrapper_namespace["admin_internal_command"](
            command_namespace["cmd_vault_review"]
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=123, username="admin", first_name="Admin"),
            message=SimpleNamespace(reply_text=reply_text),
        )
        _run_no_io(wrapped_command(update, SimpleNamespace()))

        self.assertEqual(command_effects[0], (
            "search_prompt",
            {"public_only": False, "limit": 12},
        ))
        self.assertEqual(len(command_effects), 2)
        self.assertEqual(command_effects[1][1], "🧾 Nháp cần duyệt:1")
        list_keyboard = command_effects[1][2]["reply_markup"]
        emitted_callbacks = [
            button.callback_data
            for row in list_keyboard.inline_keyboard
            for button in row
            if button.callback_data
        ]
        self.assertIn("vault|approve_prompt|91", emitted_callbacks)
        self.assertIn("vault|status", emitted_callbacks)
        self.assertIn("menu|main", emitted_callbacks)
        self.assertRegex(
            "vault|approve_prompt|91",
            _registered_pattern("handle_knowledge_vault_callback"),
        )
        self.assertRegex(
            "vault|status",
            _registered_pattern("handle_knowledge_vault_callback"),
        )
        self.assertRegex("menu|main", _registered_menu_pattern())

        back_query = _Query(123, "vault|status")
        back_edits = []

        async def edit_vault_root(text, **kwargs):
            back_edits.append((text, kwargs))

        back_query.edit_message_text = edit_vault_root

        class _ImporterFixture:
            def debug_status(self):
                return {"status": "fixture"}

        back_namespace = _load_functions(
            "handle_knowledge_vault_callback",
            is_admin_user=lambda user_id: user_id == 123,
            toan_knowledge_vault=object,
            toan_vault_importer=_ImporterFixture,
            vault_json_block=lambda payload: f"<status>{payload!r}</status>",
            vault_admin_keyboard=lambda: root_keyboard,
        )
        _run_no_io(back_namespace["handle_knowledge_vault_callback"](
            SimpleNamespace(callback_query=back_query), SimpleNamespace(),
        ))
        self.assertEqual(back_query.answers, [((), {})])
        self.assertEqual(back_edits[-1][1]["reply_markup"], root_keyboard)
        self.assertIn("Kho học liệu TOAN AAS", back_edits[-1][0])

        home_dependencies = _main_menu_dependencies(True, [])
        home_dependencies["time"] = SimpleNamespace(perf_counter=lambda: 0.0)
        home_dependencies["logger"] = SimpleNamespace(info=lambda *_args, **_kwargs: None)
        home_namespace = _load_functions("handle_menu_callback", **home_dependencies)
        home_query = _Query(123, "menu|main")
        _run_no_io(home_namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=home_query), SimpleNamespace(user_data={}),
        ))
        self.assertEqual(home_query.answers, [((), {})])
        self.assertEqual(home_query.edits, [
            ("existing screen:main", {"reply_markup": "existing keyboard:main"}),
        ])

    def test_vault_prompt_commands_keep_role_appropriate_exit_controls(self):
        self.assertIn('CommandHandler("kho_prompt", cmd_vault_prompt_library)', BOT_SOURCE)
        self.assertIn('CommandHandler("vault_prompt", cmd_vault_prompt_library)', BOT_SOURCE)
        root_keyboard = _load_functions(
            "vault_admin_keyboard",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
        )["vault_admin_keyboard"]()
        scenarios = (
            (123, True, [{"id": 92, "prompt_text": "fixture prompt"}]),
            (123, True, []),
            (999, False, [{"id": 93, "prompt_text": "public fixture"}]),
            (999, False, []),
        )

        for user_id, is_admin, prompts in scenarios:
            with self.subTest(user_id=user_id, has_prompts=bool(prompts)):
                effects = []

                class _VaultFixture:
                    def search_prompt(self, **kwargs):
                        effects.append(("search_prompt", kwargs))
                        return prompts

                async def reply_text(text, **kwargs):
                    effects.append(("reply", text, kwargs))

                namespace = _load_functions(
                    "cmd_vault_prompt_library",
                    is_admin_user=lambda candidate: candidate == user_id and is_admin,
                    toan_knowledge_vault=lambda: _VaultFixture(),
                    vault_prompt_list_text=lambda items, title: f"{title}:{len(items)}",
                    InlineKeyboardButton=_Button,
                    InlineKeyboardMarkup=_Markup,
                    vault_admin_keyboard=lambda: root_keyboard,
                )
                update = SimpleNamespace(
                    effective_user=SimpleNamespace(id=user_id),
                    message=SimpleNamespace(reply_text=reply_text),
                )
                context = SimpleNamespace(args=[])
                _run_no_io(namespace["cmd_vault_prompt_library"](update, context))

                self.assertEqual(effects[0], (
                    "search_prompt",
                    {"query": "", "public_only": not is_admin, "limit": 10},
                ))
                self.assertEqual(len(effects), 2)
                markup = effects[1][2]["reply_markup"]
                self.assertIsNotNone(markup)
                emitted_callbacks = [
                    button.callback_data
                    for row in markup.inline_keyboard
                    for button in row
                    if button.callback_data
                ]
                if prompts:
                    prompt_id = prompts[0]["id"]
                    self.assertIn(f"vault|use|{prompt_id}", emitted_callbacks)
                    self.assertRegex(
                        f"vault|use|{prompt_id}",
                        _registered_pattern("handle_knowledge_vault_callback"),
                    )
                if is_admin:
                    self.assertIn("vault|status", emitted_callbacks)
                    self.assertRegex(
                        "vault|status",
                        _registered_pattern("handle_knowledge_vault_callback"),
                    )
                self.assertIn("menu|main", emitted_callbacks)
                self.assertRegex("menu|main", _registered_menu_pattern())

                if is_admin:
                    back_query = _Query(user_id, "vault|status")
                    back_edits = []

                    async def edit_vault_root(text, **kwargs):
                        back_edits.append((text, kwargs))

                    back_query.edit_message_text = edit_vault_root

                    class _ImporterFixture:
                        def debug_status(self):
                            return {"status": "fixture"}

                    back_namespace = _load_functions(
                        "handle_knowledge_vault_callback",
                        is_admin_user=lambda candidate: candidate == user_id,
                        toan_knowledge_vault=object,
                        toan_vault_importer=_ImporterFixture,
                        vault_json_block=lambda payload: f"<status>{payload!r}</status>",
                        vault_admin_keyboard=lambda: root_keyboard,
                    )
                    _run_no_io(back_namespace["handle_knowledge_vault_callback"](
                        SimpleNamespace(callback_query=back_query), SimpleNamespace(),
                    ))
                    self.assertEqual(back_query.answers, [((), {})])
                    self.assertIn("Kho học liệu TOAN AAS", back_edits[-1][0])

                home_dependencies = _main_menu_dependencies(is_admin, [])
                home_dependencies["time"] = SimpleNamespace(perf_counter=lambda: 0.0)
                home_dependencies["logger"] = SimpleNamespace(info=lambda *_args, **_kwargs: None)
                home_namespace = _load_functions("handle_menu_callback", **home_dependencies)
                home_query = _Query(user_id, "menu|main")
                _run_no_io(home_namespace["handle_menu_callback"](
                    SimpleNamespace(callback_query=home_query), SimpleNamespace(user_data={}),
                ))
                self.assertEqual(home_query.answers, [((), {})])
                self.assertEqual(home_query.edits, [
                    ("existing screen:main", {"reply_markup": "existing keyboard:main"}),
                ])

    def test_vault_review_emitted_approve_callback_is_admin_only_and_acknowledged(self):
        self.assertIn(
            'CommandHandler("vault_review", admin_internal_command(cmd_vault_review))',
            BOT_SOURCE,
        )
        self.assertRegex("vault|approve_prompt|91", _registered_pattern("handle_knowledge_vault_callback"))
        root_keyboard = _load_functions(
            "vault_admin_keyboard",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
        )["vault_admin_keyboard"]()
        drafts = [{"id": 91, "prompt_text": "fixture pending", "status": "pending"}]

        class _CommandVault:
            def search_prompt(self, **kwargs):
                self.assert_search = kwargs
                return drafts

        command_outputs = []

        async def reply_text(text, **kwargs):
            command_outputs.append((text, kwargs))

        command_ns = _load_functions(
            "cmd_vault_review",
            toan_knowledge_vault=lambda: _CommandVault(),
            vault_prompt_list_text=lambda items, title: f"{title}:{len(items)}",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
            vault_admin_keyboard=lambda: root_keyboard,
        )
        wrapper_ns = _load_functions(
            "admin_internal_command",
            is_admin_user=lambda user_id: user_id == 123,
            record_anomaly=lambda *_args, **_kwargs: self.fail("admin command unexpectedly denied"),
            extract_command_name=lambda _update: "vault_review",
            reply_internal_customer_feature=lambda *_args: self.fail("admin wrapper did not call command"),
        )
        command_update = SimpleNamespace(
            effective_user=SimpleNamespace(id=123, username="admin", first_name="Admin"),
            message=SimpleNamespace(reply_text=reply_text),
        )
        _run_no_io(wrapper_ns["admin_internal_command"](command_ns["cmd_vault_review"])(
            command_update, SimpleNamespace(),
        ))
        emitted = next(
            button.callback_data
            for row in command_outputs[0][1]["reply_markup"].inline_keyboard
            for button in row
            if button.callback_data and button.callback_data.startswith("vault|approve_prompt|")
        )
        self.assertEqual(emitted, "vault|approve_prompt|91")

        admin_calls = []

        class _AdminVault:
            def approve_prompt(self, prompt_id, *, approved_by):
                admin_calls.append((prompt_id, approved_by))
                return {"id": prompt_id, "status": "approved"}

        async def admin_edit(text, **kwargs):
            admin_edits.append((text, kwargs))

        admin_query = _Query(123, emitted)
        admin_edits = []
        admin_query.edit_message_text = admin_edit
        admin_ns = _load_functions(
            "handle_knowledge_vault_callback",
            is_admin_user=lambda user_id: user_id == 123,
            toan_knowledge_vault=lambda: _AdminVault(),
            vault_json_block=lambda payload: f"<fixture>{payload!r}</fixture>",
            vault_admin_keyboard=lambda: root_keyboard,
        )
        _run_no_io(admin_ns["handle_knowledge_vault_callback"](
            SimpleNamespace(callback_query=admin_query), SimpleNamespace(),
        ))
        self.assertEqual(admin_query.answers, [((), {})])
        self.assertEqual(admin_calls, [(91, 123)])
        self.assertIn("✅ Đã duyệt prompt.", admin_edits[0][0])
        self.assertEqual(admin_edits[0][1]["reply_markup"], root_keyboard)

        public_calls = []

        class _PublicVault:
            def search_prompt(self, **kwargs):
                public_calls.append(("search_prompt", kwargs))
                return [{"id": 92, "prompt_text": "fixture public"}]

            def approve_prompt(self, *_args, **_kwargs):
                raise AssertionError("public user must not approve prompts")

        async def public_edit(text, **kwargs):
            public_edits.append((text, kwargs))

        public_query = _Query(999, emitted)
        public_edits = []
        public_query.edit_message_text = public_edit
        public_ns = _load_functions(
            "handle_knowledge_vault_callback",
            is_admin_user=lambda user_id: False,
            toan_knowledge_vault=lambda: _PublicVault(),
            vault_prompt_list_text=lambda items, title="public fixture": f"{title}:{len(items)}",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
            vault_admin_keyboard=lambda: root_keyboard,
        )
        _run_no_io(public_ns["handle_knowledge_vault_callback"](
            SimpleNamespace(callback_query=public_query), SimpleNamespace(),
        ))
        self.assertEqual(public_query.answers, [((), {})])
        self.assertEqual(public_calls, [
            ("search_prompt", {"public_only": True, "limit": 10}),
        ])
        self.assertEqual(public_edits[0][0], "📚 Kho Prompt TOAN AAS:1")

    def test_vault_prompt_use_button_displays_fixture_prompt_by_visibility(self):
        self.assertIn('CommandHandler("kho_prompt", cmd_vault_prompt_library)', BOT_SOURCE)
        self.assertIn('CommandHandler("vault_prompt", cmd_vault_prompt_library)', BOT_SOURCE)
        for user_id, is_admin, prompt_id, expected_public in (
            (123, True, 92, False),
            (999, False, 93, True),
        ):
            with self.subTest(user_id=user_id, is_admin=is_admin):
                namespace = _load_functions(
                    "cmd_vault_prompt_library",
                    is_admin_user=lambda candidate: candidate == user_id and is_admin,
                    toan_knowledge_vault=lambda: SimpleNamespace(search_prompt=lambda **_kwargs: [
                        {"id": prompt_id, "prompt_text": "<fixture prompt>"},
                    ]),
                    vault_prompt_list_text=lambda items, title: f"{title}:{len(items)}",
                    InlineKeyboardButton=_Button,
                    InlineKeyboardMarkup=_Markup,
                    vault_admin_keyboard=lambda: _Markup([]),
                )
                command_outputs = []

                async def reply_text(text, **kwargs):
                    command_outputs.append((text, kwargs))

                update = SimpleNamespace(
                    effective_user=SimpleNamespace(id=user_id),
                    message=SimpleNamespace(reply_text=reply_text),
                )
                _run_no_io(namespace["cmd_vault_prompt_library"](update, SimpleNamespace(args=[])))
                emitted = next(
                    button.callback_data
                    for row in command_outputs[0][1]["reply_markup"].inline_keyboard
                    for button in row
                    if button.callback_data and button.callback_data.startswith("vault|use|")
                )
                self.assertEqual(emitted, f"vault|use|{prompt_id}")
                self.assertRegex(emitted, _registered_pattern("handle_knowledge_vault_callback"))

                lookups = []
                replies = []

                class _VaultFixture:
                    def get_prompt(self, selected_id, *, public):
                        lookups.append((selected_id, public))
                        return {"id": selected_id, "prompt_text": "<fixture prompt>"}

                async def reply_prompt(text, **kwargs):
                    replies.append((text, kwargs))

                query = _Query(user_id, emitted)
                query.message = SimpleNamespace(reply_text=reply_prompt)
                handler = _load_functions(
                    "handle_knowledge_vault_callback",
                    is_admin_user=lambda candidate: candidate == user_id and is_admin,
                    toan_knowledge_vault=lambda: _VaultFixture(),
                    html=html,
                )
                _run_no_io(handler["handle_knowledge_vault_callback"](
                    SimpleNamespace(callback_query=query), SimpleNamespace(),
                ))

                self.assertEqual(query.answers, [((), {})])
                self.assertEqual(lookups, [(prompt_id, expected_public)])
                self.assertEqual(replies, [(
                    "📋 <b>Prompt sẵn sàng dùng</b>\n\n<pre>&lt;fixture prompt&gt;</pre>",
                    {"parse_mode": "HTML"},
                )])

    def test_public_audio_studio_landing_back_and_home_return_to_main_via_registered_handlers(self):
        showroom = "showroom"
        video_addon = "video_addon"
        product_helpers = _load_functions(
            "normalize_product_context",
            "product_context_callback",
            "infer_product_context_from_callback",
            "parse_product_context_callback",
            PRODUCT_CONTEXT_SHOWROOM=showroom,
            PRODUCT_CONTEXT_VIDEO_ADDON=video_addon,
            PRODUCT_CONTEXTS={showroom, video_addon},
        )

        root_dependencies = _main_menu_dependencies(False, [])
        root_dependencies.update({
            "PRODUCT_CONTEXT_SHOWROOM": showroom,
            "product_context_callback": product_helpers["product_context_callback"],
        })
        root_namespace = _load_functions(
            "localized_main_menu_keyboard", **root_dependencies,
        )
        main_markup = root_namespace["localized_main_menu_keyboard"](False, "vi")
        root_button = next(
            button
            for row in main_markup.inline_keyboard
            for button in row
            if button.callback_data == "music_quick|showroom|root"
        )

        copy = {
            "audio_root_voice": "Voice",
            "audio_root_music": "Music",
            "audio_root_back": "Back",
            "main_menu": "Main menu",
        }
        music_keyboard_namespace = _load_functions(
            "build_2col_keyboard",
            "music_tools_keyboard",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
            music_ui_lang=lambda user_id=None, lang="": "vi",
            public_hub_copy=lambda _lang: copy,
            _audio_label=lambda _lang, key: key,
            product_context_callback=product_helpers["product_context_callback"],
            PRODUCT_CONTEXT_SHOWROOM=showroom,
            PRODUCT_CONTEXT_VIDEO_ADDON=video_addon,
        )
        music_effects = []
        music_keyboard_calls = []

        def record_context(user_id, context, *, origin_screen="", product_area="", **_fields):
            music_effects.append(("context", user_id, context, origin_screen, product_area))

        async def record_reply_text(text, **kwargs):
            replies.append((text, kwargs))

        def render_music_keyboard(lang, back_callback="menu|main"):
            music_keyboard_calls.append(back_callback)
            return music_keyboard_namespace["music_tools_keyboard"](lang, back_callback)

        music_handler_namespace = _load_functions(
            "handle_music_quick_callback",
            Update=object,
            ContextTypes=SimpleNamespace(DEFAULT_TYPE=object),
            LEGACY_CANONICAL_CALLBACK_REDIRECTS={},
            PRODUCT_CONTEXT_SHOWROOM=showroom,
            PRODUCT_CONTEXT_VIDEO_ADDON=video_addon,
            parse_product_context_callback=product_helpers["parse_product_context_callback"],
            music_ui_lang=lambda _uid: "vi",
            normalize_product_context=product_helpers["normalize_product_context"],
            enter_product_context=record_context,
            clear_music_guided_pending=lambda uid: music_effects.append(("clear_pending", uid)),
            menu_text_main_music_i18n=lambda _lang: "Studio âm thanh fixture",
            music_tools_keyboard=render_music_keyboard,
        )
        music_pattern = _registered_pattern("handle_music_quick_callback")
        self.assertRegex(root_button.callback_data, music_pattern)
        user_id = 991125
        query = _Query(user_id, root_button.callback_data)
        replies = []
        query.message = SimpleNamespace(reply_text=record_reply_text)

        asyncio.run(music_handler_namespace["handle_music_quick_callback"](
            SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=user_id)),
            SimpleNamespace(),
        ))

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0][0], "Studio âm thanh fixture")
        self.assertEqual(replies[0][1]["parse_mode"], "HTML")
        self.assertEqual(music_keyboard_calls, ["menu|main"])
        music_keyboard = replies[0][1]["reply_markup"]
        self.assertEqual(
            [button.callback_data for row in music_keyboard.inline_keyboard for button in row],
            [
                "music_quick|showroom|voice_hub",
                "music_quick|showroom|music_hub",
                "menu|main",
                "menu|main",
            ],
        )
        back_button, home_button = music_keyboard.inline_keyboard[-1]
        self.assertEqual(back_button.callback_data, "menu|main")
        self.assertEqual(home_button.callback_data, "menu|main")
        self.assertEqual(
            music_effects,
            [
                ("context", user_id, showroom, "menu|main", "music"),
                ("clear_pending", user_id),
                ("context", user_id, showroom, "menu|main", "voice_music"),
            ],
        )

        menu_effects = []
        menu_dependencies = _main_menu_dependencies(False, menu_effects)
        menu_dependencies.update({
            "time": SimpleNamespace(perf_counter=lambda: 1.0),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
            "localized_menu_content": lambda action, *_args: ("Main menu fixture", main_markup),
        })
        menu_namespace = _load_functions("handle_menu_callback", **menu_dependencies)
        menu_pattern = _registered_menu_pattern()
        for navigation_button in (back_button, home_button):
            with self.subTest(button=navigation_button.text):
                self.assertRegex(navigation_button.callback_data, menu_pattern)
                return_query = _Query(user_id, navigation_button.callback_data)
                asyncio.run(menu_namespace["handle_menu_callback"](
                    SimpleNamespace(callback_query=return_query),
                    SimpleNamespace(user_data={}),
                ))
                self.assertEqual(return_query.answers, [((), {})])
                self.assertEqual(
                    return_query.edits,
                    [("Main menu fixture", {"reply_markup": main_markup})],
                )

    def test_public_voice_hub_back_returns_audio_studio_and_home_returns_main(self):
        showroom = "showroom"
        video_addon = "video_addon"
        product_helpers = _load_functions(
            "normalize_product_context",
            "product_context_callback",
            "infer_product_context_from_callback",
            "parse_product_context_callback",
            PRODUCT_CONTEXT_SHOWROOM=showroom,
            PRODUCT_CONTEXT_VIDEO_ADDON=video_addon,
            PRODUCT_CONTEXTS={showroom, video_addon},
        )

        copy = {
            "audio_root_voice": "Voice",
            "audio_root_music": "Music",
            "audio_root_back": "Back",
            "audio_studio_label": "Audio Studio",
            "voice_hub_title": "Voice Hub",
            "voice_hub_body": "Choose a voice tool",
            "voice_text_to_speech": "Text to speech",
            "voice_speech_to_text": "Speech to text",
            "voice_default_female": "Female voice",
            "voice_default_male": "Male voice",
            "voice_vault": "Saved voices",
            "voice_create_custom": "Create voice",
            "main_menu": "Main menu",
        }
        audio_namespace = _load_functions(
            "build_2col_keyboard",
            "music_tools_keyboard",
            "voice_hub_keyboard",
            "voice_hub_text",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
            normalize_product_context=product_helpers["normalize_product_context"],
            PRODUCT_CONTEXT_SHOWROOM=showroom,
            PRODUCT_CONTEXT_VIDEO_ADDON=video_addon,
            music_ui_lang=lambda user_id=None, lang="": "vi",
            public_hub_copy=lambda _lang: copy,
            product_context_callback=product_helpers["product_context_callback"],
            _audio_label=lambda _lang, key: key,
            default_tts_voices_distinct=lambda: True,
            video_order_screen_text=lambda *_args: "Video Add-on Voice",
        )
        audio_root = audio_namespace["music_tools_keyboard"]("vi", "menu|main")
        voice_entry = next(
            button
            for row in audio_root.inline_keyboard
            for button in row
            if button.callback_data == "music_quick|showroom|voice_hub"
        )

        main_dependencies = _main_menu_dependencies(False, [])
        main_dependencies.update({"PRODUCT_CONTEXT_SHOWROOM": showroom})
        main_namespace = _load_functions(
            "localized_main_menu_keyboard", **main_dependencies,
        )
        main_markup = main_namespace["localized_main_menu_keyboard"](False, "vi")

        effects = []
        screens = []

        def record_context(user_id, context, *, origin_screen="", product_area="", **_fields):
            effects.append(("context", user_id, context, origin_screen, product_area))

        async def record_reply(text, **kwargs):
            screens.append((text, kwargs))

        handler_namespace = _load_functions(
            "handle_music_quick_callback",
            Update=object,
            ContextTypes=SimpleNamespace(DEFAULT_TYPE=object),
            LEGACY_CANONICAL_CALLBACK_REDIRECTS={},
            PRODUCT_CONTEXT_SHOWROOM=showroom,
            PRODUCT_CONTEXT_VIDEO_ADDON=video_addon,
            parse_product_context_callback=product_helpers["parse_product_context_callback"],
            music_ui_lang=lambda _uid: "vi",
            normalize_product_context=product_helpers["normalize_product_context"],
            enter_product_context=record_context,
            clear_music_guided_pending=lambda uid: effects.append(("clear_pending", uid)),
            menu_text_main_music_i18n=lambda _lang: "Audio Studio screen",
            music_tools_keyboard=lambda _lang, _back="menu|main": audio_root,
            voice_hub_text=audio_namespace["voice_hub_text"],
            voice_hub_keyboard=audio_namespace["voice_hub_keyboard"],
        )
        music_pattern = _registered_pattern("handle_music_quick_callback")
        user_id = 991126
        voice_query = _Query(user_id, voice_entry.callback_data)
        voice_query.message = SimpleNamespace(reply_text=record_reply)
        self.assertRegex(voice_entry.callback_data, music_pattern)
        asyncio.run(handler_namespace["handle_music_quick_callback"](
            SimpleNamespace(callback_query=voice_query, effective_user=SimpleNamespace(id=user_id)),
            SimpleNamespace(),
        ))
        self.assertEqual(voice_query.answers, [((), {})])
        self.assertEqual(screens[-1][0], "🎙 <b>Voice Hub</b>\n\nChoose a voice tool")
        voice_keyboard = screens[-1][1]["reply_markup"]

        back_button = next(
            button for row in voice_keyboard.inline_keyboard for button in row
            if button.callback_data == "music_quick|showroom|root"
        )
        home_button = next(
            button for row in voice_keyboard.inline_keyboard for button in row
            if button.callback_data == "menu|main"
        )

        back_query = _Query(user_id, back_button.callback_data)
        back_query.message = SimpleNamespace(reply_text=record_reply)
        self.assertRegex(back_button.callback_data, music_pattern)
        asyncio.run(handler_namespace["handle_music_quick_callback"](
            SimpleNamespace(callback_query=back_query, effective_user=SimpleNamespace(id=user_id)),
            SimpleNamespace(),
        ))
        self.assertEqual(back_query.answers, [((), {})])
        self.assertEqual(screens[-1][0], "Audio Studio screen")
        self.assertEqual(screens[-1][1]["reply_markup"].inline_keyboard, audio_root.inline_keyboard)

        menu_dependencies = _main_menu_dependencies(False, [])
        menu_dependencies.update({
            "time": SimpleNamespace(perf_counter=lambda: 1.0),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
            "localized_menu_content": lambda action, *_args: ("Main menu fixture", main_markup),
        })
        menu_namespace = _load_functions("handle_menu_callback", **menu_dependencies)
        menu_pattern = _registered_menu_pattern()
        self.assertRegex(home_button.callback_data, menu_pattern)
        home_query = _Query(user_id, home_button.callback_data)
        asyncio.run(menu_namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=home_query),
            SimpleNamespace(user_data={}),
        ))
        self.assertEqual(home_query.answers, [((), {})])
        self.assertEqual(home_query.edits, [("Main menu fixture", {"reply_markup": main_markup})])
        self.assertIn(("context", user_id, showroom, "menu|main", "voice"), effects)

    def test_public_music_hub_back_restores_audio_studio_and_home_returns_main_via_registered_handlers(self):
        showroom = "showroom"
        video_addon = "video_addon"
        product_helpers = _load_functions(
            "normalize_product_context",
            "product_context_callback",
            "infer_product_context_from_callback",
            "parse_product_context_callback",
            PRODUCT_CONTEXT_SHOWROOM=showroom,
            PRODUCT_CONTEXT_VIDEO_ADDON=video_addon,
            PRODUCT_CONTEXTS={showroom, video_addon},
        )
        copy = {
            "audio_root_voice": "Voice",
            "audio_root_music": "Music",
            "audio_root_back": "Back",
            "audio_studio_label": "Audio Studio",
            "music_background": "Background music",
            "music_song": "Lyrics song",
            "music_vault": "Music library",
            "music_edit": "Music editor",
            "music_hub_title": "Music Hub",
            "music_hub_body": "Choose an option",
            "main_menu": "Main menu",
        }
        keyboard_namespace = _load_functions(
            "build_2col_keyboard",
            "music_tools_keyboard",
            "music_hub_text",
            "music_hub_keyboard",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
            ui_text=lambda _lang, key: key,
            music_ui_lang=lambda user_id=None, lang="": "vi",
            public_hub_copy=lambda _lang: copy,
            _audio_label=lambda _lang, key: copy.get(key, key),
            normalize_product_context=product_helpers["normalize_product_context"],
            product_context_callback=product_helpers["product_context_callback"],
            PRODUCT_CONTEXT_SHOWROOM=showroom,
            PRODUCT_CONTEXT_VIDEO_ADDON=video_addon,
        )
        audio_markup = keyboard_namespace["music_tools_keyboard"]("vi", "menu|main")
        music_button = next(
            button
            for row in audio_markup.inline_keyboard
            for button in row
            if button.callback_data == "music_quick|showroom|music_hub"
        )

        replies = []

        async def record_reply(text, **kwargs):
            replies.append((text, kwargs))

        music_namespace = _load_functions(
            "handle_music_quick_callback",
            Update=object,
            ContextTypes=SimpleNamespace(DEFAULT_TYPE=object),
            LEGACY_CANONICAL_CALLBACK_REDIRECTS={},
            PRODUCT_CONTEXT_SHOWROOM=showroom,
            PRODUCT_CONTEXT_VIDEO_ADDON=video_addon,
            parse_product_context_callback=product_helpers["parse_product_context_callback"],
            music_ui_lang=lambda _uid: "vi",
            normalize_product_context=product_helpers["normalize_product_context"],
            enter_product_context=lambda *_args, **_kwargs: None,
            clear_music_guided_pending=lambda _uid: None,
            menu_text_main_music_i18n=lambda _lang: "Audio Studio screen",
            music_tools_keyboard=keyboard_namespace["music_tools_keyboard"],
            music_hub_text=keyboard_namespace["music_hub_text"],
            music_hub_keyboard=keyboard_namespace["music_hub_keyboard"],
        )
        user_id = 991131
        music_pattern = _registered_pattern("handle_music_quick_callback")

        def dispatch_music(callback_data):
            self.assertRegex(callback_data, music_pattern)
            query = _Query(user_id, callback_data)
            query.message = SimpleNamespace(reply_text=record_reply)
            asyncio.run(music_namespace["handle_music_quick_callback"](
                SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=user_id)),
                SimpleNamespace(),
            ))
            self.assertEqual(query.answers, [((), {})])
            return query

        self.assertRegex(music_button.callback_data, music_pattern)
        self.assertEqual(music_button.callback_data, "music_quick|showroom|music_hub")
        dispatch_music(music_button.callback_data)
        self.assertEqual(replies[-1][0], "🎵 <b>Music Hub</b>\n\nChoose an option")
        self.assertEqual(
            [button.callback_data for row in replies[-1][1]["reply_markup"].inline_keyboard for button in row],
            [
                "music_quick|showroom|ai_music",
                "music_quick|showroom|song_menu",
                "music_quick|showroom|music",
                "music_quick|showroom|music_edit",
                "music_quick|showroom|root",
                "menu|main",
            ],
        )
        back_button, home_button = replies[-1][1]["reply_markup"].inline_keyboard[-1]
        self.assertEqual((back_button.callback_data, home_button.callback_data),
                         ("music_quick|showroom|root", "menu|main"))
        dispatch_music(back_button.callback_data)
        self.assertEqual(replies[-1][0], "Audio Studio screen")
        self.assertEqual(replies[-1][1]["parse_mode"], "HTML")
        self.assertEqual(
            [button.callback_data for row in replies[-1][1]["reply_markup"].inline_keyboard for button in row],
            [
                "music_quick|showroom|voice_hub",
                "music_quick|showroom|music_hub",
                "menu|main",
                "menu|main",
            ],
        )

        main_dependencies = _main_menu_dependencies(False, [])
        main_dependencies.update({
            "PRODUCT_CONTEXT_SHOWROOM": showroom,
            "product_context_callback": product_helpers["product_context_callback"],
        })
        main_markup = _load_functions(
            "localized_main_menu_keyboard", **main_dependencies,
        )["localized_main_menu_keyboard"](False, "vi")
        main_dependencies.update({
            "time": SimpleNamespace(perf_counter=lambda: 1.0),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
            "localized_menu_content": lambda action, *_args: ("Main menu fixture", main_markup),
        })
        menu_namespace = _load_functions("handle_menu_callback", **main_dependencies)
        menu_pattern = _registered_menu_pattern()
        self.assertRegex(home_button.callback_data, menu_pattern)
        home_query = _Query(user_id, home_button.callback_data)
        asyncio.run(menu_namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=home_query),
            SimpleNamespace(user_data={}),
        ))
        self.assertEqual(home_query.answers, [((), {})])
        self.assertEqual(home_query.edits, [("Main menu fixture", {"reply_markup": main_markup})])

    def test_customer_ticket_category_prompt_back_restores_category_menu(self):
        class Copy(dict):
            def __missing__(self, key):
                return key

        user_id = 991127
        namespace = _load_functions(
            "support_ticket_pending_key",
            "set_support_ticket_pending",
            "get_support_ticket_pending",
            "clear_support_ticket_pending",
            "support_ticket_menu_text",
            "support_ticket_menu_keyboard",
            "public_support_ticket_category_label",
            "support_ticket_message_prompt",
            "support_ticket_input_keyboard",
            "handle_ticket_callback",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
            normalize_user_language=lambda _lang: "vi",
            get_user_language=lambda _uid: "vi",
            public_hub_copy=lambda _lang: Copy(support_ticket_prompt_body="Describe the issue"),
            is_admin_user=lambda _uid: False,
            html=html,
            time=SimpleNamespace(time=lambda: 1_000.0),
            USER_PENDING={},
            SUPPORT_TICKET_TTL_SECONDS=900,
            SUPPORT_CATEGORIES={
                "payment_topup", "image_error", "video_error", "document_pdf",
                "package_combo", "refund", "feature_request", "lead_consulting", "other",
            },
            safe_edit_or_send=self._record_safe_edit,
        )
        route_pattern = _registered_pattern("handle_ticket_callback")

        def dispatch(data):
            query = _Query(user_id, data)
            self.assertRegex(data, route_pattern)
            asyncio.run(namespace["handle_ticket_callback"](
                SimpleNamespace(callback_query=query), SimpleNamespace(),
            ))
            self.assertEqual(query.answers, [((), {})])
            self.assertEqual(len(query.edits), 1)
            return query

        category_page = dispatch("ticket|start")
        category_markup = category_page.edits[0][1]["reply_markup"]
        category_callbacks = [
            button.callback_data
            for row in category_markup.inline_keyboard
            for button in row
            if button.callback_data and button.callback_data.startswith("ticket|cat|")
        ]
        self.assertIn("ticket|cat|image_error", category_callbacks)

        prompt = dispatch("ticket|cat|image_error")
        self.assertEqual(
            namespace["get_support_ticket_pending"](user_id),
            {
                "pending_action": "support_ticket",
                "step": "awaiting_message",
                "support_pending_input": True,
                "created_at_ts": 1_000.0,
                "category": "image_error",
            },
        )
        prompt_markup = prompt.edits[0][1]["reply_markup"]
        back = next(
            button.callback_data
            for row in prompt_markup.inline_keyboard
            for button in row
            if button.text.startswith("⬅")
        )
        self.assertEqual(back, "ticket|start")

        returned = dispatch(back)
        self.assertIsNone(namespace["get_support_ticket_pending"](user_id))
        self.assertEqual(
            [button.callback_data for row in returned.edits[0][1]["reply_markup"].inline_keyboard for button in row],
            [button.callback_data for row in category_markup.inline_keyboard for button in row],
        )

    def test_image_story_render_hint_only_informs_without_creating_media_job(self):
        acknowledgements = []
        replies = []
        media_jobs = []

        class Message:
            async def reply_text(self, text, **kwargs):
                replies.append((text, kwargs))

        async def answer(text=None, **kwargs):
            acknowledgements.append((text, kwargs))

        namespace = _load_functions(
            "image_story_keyboard",
            "handle_image_story_callback",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
            html=html,
            create_media_factory_job=lambda *args, **kwargs: media_jobs.append((args, kwargs)),
        )
        keyboard = namespace["image_story_keyboard"]()
        callback_data = next(
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data == "image_story_render_hint"
        )
        self.assertRegex(callback_data, _registered_pattern("handle_image_story_callback"))

        query = SimpleNamespace(
            data=callback_data,
            from_user=SimpleNamespace(id=991130),
            message=Message(),
            answer=answer,
        )
        asyncio.run(namespace["handle_image_story_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(args=[]),
        ))

        self.assertEqual(acknowledgements, [(None, {})])
        self.assertEqual(
            replies,
            [("🧪 Render thật đang admin-test. Khách dùng /image_story để lấy shot pack/prompt trước. Bot chưa trừ Xu.", {})],
        )
        self.assertEqual(media_jobs, [])

    def test_media_library_home_button_returns_to_registered_main_menu(self):
        effects = []
        dependencies = _main_menu_dependencies(False, effects)
        dependencies.update({
            "normalize_product_context": lambda context: context,
            "product_context_callback": lambda namespace, context, action: f"{namespace}|{context}|{action}",
            "music_ui_lang": lambda *_args, **_kwargs: "vi",
            "_audio_topic": lambda _lang, key: key,
            "_audio_label": lambda _lang, key: key,
            "time": SimpleNamespace(perf_counter=lambda: 1.0),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
            "localized_start_menu_text": lambda *_args: "MAIN SCREEN",
            "localized_main_menu_keyboard": lambda *_args: _Markup([]),
            "PRODUCT_CONTEXT_VIDEO_ADDON": "video_addon",
        })
        namespace = _load_functions("media_library_quick_keyboard", "handle_menu_callback", **dependencies)
        media_keyboard = namespace["media_library_quick_keyboard"]("vi", "showroom")
        callback = next(
            button.callback_data
            for row in media_keyboard.inline_keyboard
            for button in row
            if button.callback_data == "menu|main"
        )
        self.assertRegex(callback, _registered_menu_pattern())

        query = _Query(991177, callback)
        _run_no_io(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=query),
            SimpleNamespace(user_data={}),
        ))

        self.assertEqual([((), {})], query.answers)
        self.assertEqual(
            [("existing screen:main", {"reply_markup": "existing keyboard:main"})],
            query.edits,
        )

    def test_product_progress_update_button_dispatches_registered_read_only_handler(self):
        from services import product_progress_status
        from services.pricing_guide_content import public_hub_copy

        user_id = 991178
        job_id = "job123"
        job_reads = []
        refresh_registrations = []
        renders = []
        job_record = {
            "internal_job_id": job_id,
            "job_id": job_id,
            "user_id": str(user_id),
            "product_type": "video_ai_real",
            "status": "processing",
            "progress_percent": 42,
        }

        def get_job(selected_job_id):
            job_reads.append(selected_job_id)
            return dict(job_record)

        async def render(query, text, **kwargs):
            renders.append((text, kwargs))
            query.edits.append((text, kwargs))

        def forbidden(*_args, **_kwargs):
            self.fail("video progress refresh must not deliver or reprocess an artifact")

        namespace = _load_functions(
            "product_progress_status_keyboard",
            "product_progress_state_from_job",
            "product_progress_status_from_job_text",
            "handle_product_progress_callback",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
            product_progress_status=product_progress_status,
            public_hub_copy=public_hub_copy,
            resolve_progress_product_type=lambda _job_id, product_type, _job: product_type,
            progress_product_type_is_music=lambda *_args: False,
            product_progress_status_text=product_progress_status.render_product_progress_panel,
            user_ui_lang=lambda _uid: "vi",
            is_admin_user=lambda _uid: False,
            get_engine_async_job=get_job,
            safe_edit_or_send=render,
            progress_auto_refresh_register_message=lambda *args, **kwargs: refresh_registrations.append((args, kwargs)),
            execute_engine=forbidden,
            maybe_deliver_music_progress_job=forbidden,
            subdub_recover_existing_mp4_delivery=forbidden,
            subdub_finalize_delivered_panel=forbidden,
            subdub_send_success_receipt_once=forbidden,
        )

        registrations = []
        namespace["tg_app"] = SimpleNamespace(add_handler=registrations.append)
        namespace["CallbackQueryHandler"] = lambda callback, pattern: SimpleNamespace(
            callback=callback, pattern=re.compile(pattern),
        )
        registration = next(
            line.strip()
            for line in BOT_SOURCE.splitlines()
            if "tg_app.add_handler(CallbackQueryHandler(handle_product_progress_callback," in line
        )
        exec(registration, namespace)
        route = next(
            item for item in registrations
            if item.callback is namespace["handle_product_progress_callback"]
        )

        keyboard = namespace["product_progress_status_keyboard"]("video_ai_real", job_id, "vi")
        refresh_button = next(
            button for row in keyboard.inline_keyboard for button in row
            if button.text == "🔄 Cập nhật trạng thái"
        )
        self.assertEqual("progress|status|video_ai_real|job123", refresh_button.callback_data)
        self.assertIsNotNone(route.pattern.match(refresh_button.callback_data))

        for _ in range(2):
            query = _Query(user_id, refresh_button.callback_data)
            query.message = SimpleNamespace(chat_id=user_id, message_id=44)
            _run_no_io(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
            self.assertEqual([((), {})], query.answers)
            self.assertEqual(1, len(query.edits))
            panel_text, panel_options = query.edits[0]
            self.assertIn("Tiến độ:", panel_text)
            returned_callbacks = [
                button.callback_data
                for row in panel_options["reply_markup"].inline_keyboard
                for button in row
                if button.callback_data
            ]
            self.assertIn(refresh_button.callback_data, returned_callbacks)
            self.assertIn("menu|main_video", returned_callbacks)
            self.assertIn("menu|main", returned_callbacks)
            for navigation_callback in ("menu|main_video", "menu|main"):
                self.assertRegex(navigation_callback, _registered_menu_pattern())

        self.assertEqual([job_id, job_id], job_reads)
        self.assertEqual(2, len(refresh_registrations))
        self.assertEqual(2, len(renders))

        job_record.clear()
        stale_query = _Query(user_id, refresh_button.callback_data)
        stale_query.message = SimpleNamespace(chat_id=user_id, message_id=44)
        _run_no_io(route.callback(SimpleNamespace(callback_query=stale_query), SimpleNamespace()))
        self.assertEqual([((), {})], stale_query.answers)
        stale_text, stale_options = stale_query.edits[0]
        copy = public_hub_copy("vi")
        self.assertIn(copy["common_failed"], stale_text)
        self.assertIn(copy["common_retry"], stale_text)
        self.assertNotIn("Tiến độ: 0%", stale_text)
        self.assertNotIn(job_id, stale_text)
        self.assertEqual(
            {"menu|main_video", "menu|main"},
            {
                button.callback_data
                for row in stale_options["reply_markup"].inline_keyboard
                for button in row
            },
        )
        self.assertEqual([job_id, job_id, job_id], job_reads)
        self.assertEqual(2, len(refresh_registrations), "missing job must not register a refresh loop")
        self.assertEqual(3, len(renders))

        latest_keyboard = namespace["product_progress_status_keyboard"]("video_ai_real", "latest", "vi")
        latest_callback = next(
            button.callback_data
            for row in latest_keyboard.inline_keyboard
            for button in row
            if button.text == "🔄 Cập nhật trạng thái"
        )
        latest_query = _Query(user_id, latest_callback)
        latest_query.message = SimpleNamespace(chat_id=user_id, message_id=44)
        _run_no_io(route.callback(SimpleNamespace(callback_query=latest_query), SimpleNamespace()))
        self.assertEqual([((), {})], latest_query.answers)
        latest_text, latest_options = latest_query.edits[0]
        self.assertIn(copy["common_failed"], latest_text)
        self.assertNotIn("Tiến độ: 0%", latest_text)
        self.assertNotIn(job_id, latest_text)
        self.assertEqual(
            {"menu|main_video", "menu|main"},
            {
                button.callback_data
                for row in latest_options["reply_markup"].inline_keyboard
                for button in row
            },
        )
        self.assertEqual([job_id, job_id, job_id], job_reads, "latest must not invent a job lookup")
        self.assertEqual(2, len(refresh_registrations))

        job_record.update({
            "internal_job_id": job_id,
            "job_id": job_id,
            "user_id": str(user_id + 1),
            "product_type": "video_ai_real",
            "status": "processing",
            "progress_percent": 42,
        })
        foreign_query = _Query(user_id, refresh_button.callback_data)
        foreign_query.message = SimpleNamespace(chat_id=user_id, message_id=44)
        _run_no_io(route.callback(SimpleNamespace(callback_query=foreign_query), SimpleNamespace()))
        self.assertEqual([((), {})], foreign_query.answers)
        foreign_text, foreign_options = foreign_query.edits[0]
        self.assertIn(copy["common_failed"], foreign_text)
        self.assertNotIn(job_id, foreign_text)
        self.assertEqual(
            {"menu|main_video", "menu|main"},
            {
                button.callback_data
                for row in foreign_options["reply_markup"].inline_keyboard
                for button in row
            },
        )
        self.assertEqual([job_id, job_id, job_id, job_id], job_reads)
        self.assertEqual(2, len(refresh_registrations), "foreign job must not register a refresh loop")
        self.assertEqual(5, len(renders))

    def test_local_video_studio_preview_emitted_callbacks_use_registered_admin_handler(self):
        from services import local_video_studio_preview

        admin_id = 991179
        context = SimpleNamespace(user_data={})
        command_replies = []

        class _Message:
            async def reply_text(self, text, **kwargs):
                record = {"text": text, **kwargs}
                command_replies.append(record)
                return record

        namespace = _load_functions(
            "local_video_studio_preview_keyboard",
            "cmd_local_video_studio_preview",
            "handle_local_video_studio_preview_callback",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
            local_video_studio_preview=local_video_studio_preview,
            is_admin_user=lambda candidate: int(candidate) == admin_id,
        )
        command_update = SimpleNamespace(
            effective_user=SimpleNamespace(id=admin_id),
            effective_message=_Message(),
        )
        _run_no_io(namespace["cmd_local_video_studio_preview"](command_update, context))
        self.assertEqual("home", context.user_data[local_video_studio_preview.STATE_KEY]["screen"])
        root_markup = command_replies[0]["reply_markup"]
        open_callback = next(
            button.callback_data
            for row in root_markup.inline_keyboard
            for button in row
            if button.callback_data == "lvs27a|open|create"
        )

        registrations = []
        namespace["tg_app"] = SimpleNamespace(add_handler=registrations.append)
        namespace["CallbackQueryHandler"] = lambda callback, pattern: SimpleNamespace(
            callback=callback, pattern=re.compile(pattern),
        )
        registration = next(
            line.strip()
            for line in BOT_SOURCE.splitlines()
            if "tg_app.add_handler(CallbackQueryHandler(handle_local_video_studio_preview_callback," in line
        )
        exec(registration, namespace)
        route = next(
            item for item in registrations
            if item.callback is namespace["handle_local_video_studio_preview_callback"]
        )
        self.assertIsNotNone(route.pattern.match(open_callback))

        async def edit(query, text, **kwargs):
            query.edits.append((text, kwargs))

        open_query = _Query(admin_id, open_callback)
        open_query.edit_message_text = lambda text, **kwargs: edit(open_query, text, **kwargs)
        _run_no_io(route.callback(
            SimpleNamespace(effective_user=SimpleNamespace(id=admin_id), callback_query=open_query),
            context,
        ))
        self.assertEqual(1, len(open_query.answers))
        self.assertEqual(1, len(open_query.edits))
        self.assertEqual("create_goal", context.user_data[local_video_studio_preview.STATE_KEY]["screen"])
        self.assertIn("Mục tiêu video mới", open_query.edits[0][0])

        back_callback = next(
            button.callback_data
            for row in open_query.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
            if button.callback_data == "lvs27a|back"
        )
        self.assertIsNotNone(route.pattern.match(back_callback))
        back_query = _Query(admin_id, back_callback)
        back_query.edit_message_text = lambda text, **kwargs: edit(back_query, text, **kwargs)
        _run_no_io(route.callback(
            SimpleNamespace(effective_user=SimpleNamespace(id=admin_id), callback_query=back_query),
            context,
        ))
        self.assertEqual(1, len(back_query.answers))
        self.assertEqual("home", context.user_data[local_video_studio_preview.STATE_KEY]["screen"])
        self.assertIn("LOCAL VIDEO STUDIO — PREVIEW 27A", back_query.edits[0][0])

        reopen_query = _Query(admin_id, open_callback)
        reopen_query.edit_message_text = lambda text, **kwargs: edit(reopen_query, text, **kwargs)
        _run_no_io(route.callback(
            SimpleNamespace(effective_user=SimpleNamespace(id=admin_id), callback_query=reopen_query),
            context,
        ))
        home_callback = next(
            button.callback_data
            for row in reopen_query.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
            if button.callback_data == "lvs27a|home"
        )
        home_query = _Query(admin_id, home_callback)
        home_query.edit_message_text = lambda text, **kwargs: edit(home_query, text, **kwargs)
        _run_no_io(route.callback(
            SimpleNamespace(effective_user=SimpleNamespace(id=admin_id), callback_query=home_query),
            context,
        ))
        self.assertEqual(1, len(home_query.answers))
        self.assertEqual("home", context.user_data[local_video_studio_preview.STATE_KEY]["screen"])

        close_callback = next(
            button.callback_data
            for row in home_query.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
            if button.callback_data == "lvs27a|close"
        )
        close_query = _Query(admin_id, close_callback)
        close_query.edit_message_text = lambda text, **kwargs: edit(close_query, text, **kwargs)
        _run_no_io(route.callback(
            SimpleNamespace(effective_user=SimpleNamespace(id=admin_id), callback_query=close_query),
            context,
        ))
        self.assertEqual(1, len(close_query.answers))
        self.assertIn("Đã đóng Local Video Studio Preview", close_query.edits[0][0])
        self.assertNotIn(local_video_studio_preview.STATE_KEY, context.user_data)

        stale_query = _Query(admin_id, back_callback)
        stale_query.edit_message_text = lambda text, **kwargs: edit(stale_query, text, **kwargs)
        _run_no_io(route.callback(
            SimpleNamespace(effective_user=SimpleNamespace(id=admin_id), callback_query=stale_query),
            context,
        ))
        self.assertEqual(1, len(stale_query.answers))
        self.assertTrue(stale_query.answers[0][1].get("show_alert"))
        self.assertEqual([], stale_query.edits)
        self.assertNotIn(local_video_studio_preview.STATE_KEY, context.user_data)

        unauth_context = SimpleNamespace(user_data={local_video_studio_preview.STATE_KEY: {"owner_state": "keep"}})
        before = dict(unauth_context.user_data)
        unauth_query = _Query(admin_id + 1, open_callback)
        _run_no_io(route.callback(
            SimpleNamespace(effective_user=SimpleNamespace(id=admin_id + 1), callback_query=unauth_query),
            unauth_context,
        ))
        self.assertEqual(1, len(unauth_query.answers))
        self.assertTrue(unauth_query.answers[0][1].get("show_alert"))
        self.assertEqual(before, unauth_context.user_data)

    def test_local_video_public_planner_entry_dispatches_registered_and_back_expires(self):
        from services import video_planning_assistant as planning_service
        from services import video_uifreeze1
        from services.pricing_guide_content import public_hub_copy

        route_start = BOT_SOURCE.index("VIDEO_PUBLIC_ROUTE_MATRIX = {")
        route_end = BOT_SOURCE.index("def video_public_route_for_tool", route_start)
        route_assignment = ast.parse(BOT_SOURCE[route_start:route_end]).body[0]
        route_matrix = ast.literal_eval(route_assignment.value)
        service_names = (
            "PLAN_SCHEMA_VERSION", "STATE_KEY", "SESSION_TTL_SECONDS",
            "PreviewActionError", "PreviewDataError", "PublicSessionExpired",
            "serialize_plan", "parse_callback", "open_transaction_lock",
            "session_transaction_lock", "new_store", "store_has_callback_id",
            "new_session", "apply_callback", "render_view", "commit_callback_id",
            "put_session", "delete_session", "get_session", "deliver_then_commit",
        )
        service = SimpleNamespace(**{
            name: getattr(planning_service, name)
            for name in service_names
        })

        class _ImmediateLock:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

        service.open_transaction_lock = lambda *_args: _ImmediateLock()
        service.session_transaction_lock = lambda *_args: _ImmediateLock()
        menu_namespace = _load_functions(
            "video_public_visible_menu_rows",
            "video_public_route_for_tool",
            "video_public_menu_label",
            "main_video_keyboard",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
            normalize_user_language=lambda lang: lang or "vi",
            public_hub_copy=public_hub_copy,
            public_video_menu_label=lambda *_args: "",
            local_video_studio_public_enabled=lambda: True,
            VIDEO_PUBLIC_MENU_ROWS=video_uifreeze1.PUBLIC_MENU_ROWS,
            VIDEO_PUBLIC_ROUTE_MATRIX=route_matrix,
        )
        video_menu = menu_namespace["main_video_keyboard"]("vi")
        entry = next(
            button
            for row in video_menu.inline_keyboard
            for button in row
            if button.callback_data == "lvs27b|open"
        )
        self.assertIn("Lên kế hoạch", entry.text)
        self.assertIn('"entry_callback": "lvs27b|open"', BOT_SOURCE)

        namespace = _load_functions(
            "local_video_studio_public_keyboard",
            "_local_video_studio_is_option_c",
            "_local_video_studio_public_store",
            "_local_video_studio_public_cleanup_store",
            "_local_video_studio_public_identity",
            "_local_video_planning_user_data",
            "_local_video_planning_clear_pending",
            "_local_video_studio_public_deliver",
            "_handle_option_c_video_planning_callback",
            "handle_local_video_studio_public_callback",
            InlineKeyboardButton=_Button,
            InlineKeyboardMarkup=_Markup,
            local_video_studio_public=service,
            local_video_planning_store=SimpleNamespace(PlanStoreError=RuntimeError),
            local_video_studio_public_enabled=lambda: True,
            normalize_user_language=lambda lang: lang or "vi",
            get_user_language=lambda _uid: "vi",
            menu_text_main_video_i18n=lambda _lang: "MAIN VIDEO MENU FIXTURE",
            main_video_keyboard=menu_namespace["main_video_keyboard"],
            VIDEO_PUBLIC_MENU_ROWS=video_uifreeze1.PUBLIC_MENU_ROWS,
            VIDEO_PUBLIC_ROUTE_MATRIX=route_matrix,
            video_public_visible_menu_rows=menu_namespace["video_public_visible_menu_rows"],
            video_public_route_for_tool=menu_namespace["video_public_route_for_tool"],
            video_public_menu_label=menu_namespace["video_public_menu_label"],
            public_video_menu_label=lambda *_args: "",
            public_hub_copy=public_hub_copy,
            local_video_planning_store_version=1,
            _LOCAL_VIDEO_PLANNING_PENDING_KEY="local_video_planning_pending_brief",
            time=SimpleNamespace(time=lambda: 1_800_000_000),
        )
        registrations = []
        namespace["tg_app"] = SimpleNamespace(add_handler=registrations.append)
        namespace["CallbackQueryHandler"] = lambda callback, pattern: SimpleNamespace(
            callback=callback, pattern=re.compile(pattern),
        )
        registration = next(
            line.strip()
            for line in BOT_SOURCE.splitlines()
            if "tg_app.add_handler(CallbackQueryHandler(handle_local_video_studio_public_callback," in line
        )
        exec(registration, namespace)
        route = next(
            item for item in registrations
            if item.callback is namespace["handle_local_video_studio_public_callback"]
        )
        self.assertIsNotNone(route.pattern.match(entry.callback_data))

        async def edit(query, text, **kwargs):
            query.edits.append((text, kwargs))
            return True

        user_id, chat_id = 7, 70
        context = SimpleNamespace(user_data={"video_edit_sentinel": {"unchanged": True}})
        open_query = _Query(user_id, entry.callback_data)
        open_query.id = "lvs27b-open-1"
        open_query.message = SimpleNamespace(chat_id=chat_id, message_id=91)
        open_query.edit_message_text = lambda text, **kwargs: edit(open_query, text, **kwargs)
        _run_no_io(route.callback(
            SimpleNamespace(
                callback_query=open_query,
                effective_user=SimpleNamespace(id=user_id),
                effective_chat=SimpleNamespace(id=chat_id),
            ),
            context,
        ))
        self.assertEqual(1, len(open_query.answers))
        self.assertIn("LÊN KẾ HOẠCH", open_query.edits[0][0])
        goal_back = next(
            button.callback_data
            for row in open_query.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
            if button.callback_data.endswith("|back")
        )
        self.assertIsNotNone(route.pattern.match(goal_back))
        self.assertTrue(context.user_data.get(service.STATE_KEY))

        back_query = _Query(user_id, goal_back)
        back_query.id = "lvs27b-back-1"
        back_query.message = SimpleNamespace(chat_id=chat_id, message_id=91)
        back_query.edit_message_text = lambda text, **kwargs: edit(back_query, text, **kwargs)
        _run_no_io(route.callback(
            SimpleNamespace(
                callback_query=back_query,
                effective_user=SimpleNamespace(id=user_id),
                effective_chat=SimpleNamespace(id=chat_id),
            ),
            context,
        ))
        self.assertEqual(1, len(back_query.answers))
        self.assertEqual("MAIN VIDEO MENU FIXTURE", back_query.edits[0][0])
        back_callbacks = {
            button.callback_data
            for row in back_query.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
            if button.callback_data
        }
        self.assertIn("lvs27b|open", back_callbacks)
        self.assertIn("menu|main", back_callbacks)
        self.assertNotIn(service.STATE_KEY, context.user_data)
        self.assertEqual({"unchanged": True}, context.user_data["video_edit_sentinel"])

        stale_query = _Query(user_id, goal_back)
        stale_query.id = "lvs27b-back-stale"
        stale_query.message = SimpleNamespace(chat_id=chat_id, message_id=91)
        stale_query.edit_message_text = lambda text, **kwargs: edit(stale_query, text, **kwargs)
        _run_no_io(route.callback(
            SimpleNamespace(
                callback_query=stale_query,
                effective_user=SimpleNamespace(id=user_id),
                effective_chat=SimpleNamespace(id=chat_id),
            ),
            context,
        ))
        self.assertEqual(1, len(stale_query.answers))
        self.assertTrue(stale_query.answers[0][1].get("show_alert"))
        self.assertEqual([], stale_query.edits)
        self.assertNotIn(service.STATE_KEY, context.user_data)

    def test_local_video_public_plan_save_button_uses_registered_handler_idempotently(self):
        import copy
        import html
        import sqlite3
        import time
        import uuid

        from services import local_video_planning_store
        from services import video_planning_assistant as planning_service

        user_id, chat_id, session_id = 7, 70, "lvsave01"
        state = planning_service.new_session(session_id, now=int(time.time()))

        def choose(current, verb, *args):
            return planning_service.apply_callback(
                current,
                planning_service.callback_data(current["session_id"], verb, *args),
            )["session"]

        state = choose(state, "goal", "cut_pacing")
        state = planning_service.apply_text_input(
            state,
            "Video bán hàng cần nhanh, sáng, rõ lời nói và logo không che sản phẩm.",
        )["session"]
        state = choose(state, "platform", "tiktok_9x16")
        state = choose(state, "source", "60_120")
        state = choose(state, "target", "30")
        state = choose(state, "asset", "video")
        state = choose(state, "asset", "logo")
        state = choose(state, "assets_done")
        state = choose(state, "priority", "pace")
        state = choose(state, "priority", "product_focus")
        state = choose(state, "priorities_done")
        state = choose(state, "operations_done")
        state = choose(state, "safety_done")
        self.assertEqual("summary", state["screen"])

        memory_uri = f"file:lvs27b_plans_{uuid.uuid4().hex}?mode=memory&cache=shared"
        anchor = sqlite3.connect(memory_uri, uri=True)
        anchor.row_factory = sqlite3.Row
        self.addCleanup(anchor.close)

        def db_connect():
            return sqlite3.connect(memory_uri, uri=True)

        class _ImmediateLock:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

        public_adapter = SimpleNamespace(**{
            name: getattr(planning_service, name)
            for name in vars(planning_service)
            if not name.startswith("__")
        })
        public_adapter.open_transaction_lock = lambda *_args: _ImmediateLock()
        public_adapter.session_transaction_lock = lambda *_args: _ImmediateLock()
        start = BOT_SOURCE.index("# --- LOCAL VIDEO STUDIO 27B PUBLIC ---")
        end = BOT_SOURCE.index("# --- END LOCAL VIDEO STUDIO 27B PUBLIC ---", start)
        namespace = {
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "local_video_studio_public": public_adapter,
            "local_video_planning_store": local_video_planning_store,
            "local_video_studio_public_enabled": lambda: True,
            "menu_text_main_video_i18n": lambda _lang: "MAIN VIDEO MENU",
            "main_video_keyboard": lambda _lang: _Markup([]),
            "video_edit_hub_text": lambda _lang: "VIDEO EDIT HUB",
            "video_edit_hub_keyboard": lambda _lang: _Markup([]),
            "get_user_language": lambda _uid: "vi",
            "normalize_user_language": lambda lang: lang or "vi",
            "db_connect": db_connect,
            "copy": copy,
            "html": html,
            "sqlite3": sqlite3,
            "time": time,
        }
        source = "from __future__ import annotations\n\n" + BOT_SOURCE[start:end]
        exec(compile(source, "bot.py:lvs27b-persist-route", "exec"), namespace)

        store = planning_service.new_store()
        planning_service.put_session(store, str(user_id), str(chat_id), state)
        context = SimpleNamespace(user_data={
            planning_service.STATE_KEY: store,
            "video_edit_sentinel": {"unchanged": True},
        })
        view = planning_service.render_view(state)
        summary_keyboard = namespace["local_video_studio_public_keyboard"](view)
        persist_callback = next(
            button.callback_data
            for row in summary_keyboard.inline_keyboard
            for button in row
            if button.callback_data.endswith("|persist")
        )
        registrations = []
        namespace["tg_app"] = SimpleNamespace(add_handler=registrations.append)
        namespace["CallbackQueryHandler"] = lambda callback, pattern: SimpleNamespace(
            callback=callback, pattern=re.compile(pattern),
        )
        registration = next(
            line.strip()
            for line in BOT_SOURCE.splitlines()
            if "tg_app.add_handler(CallbackQueryHandler(handle_local_video_studio_public_callback," in line
        )
        exec(registration, namespace)
        route = next(
            item for item in registrations
            if item.callback is namespace["handle_local_video_studio_public_callback"]
        )
        self.assertIsNotNone(route.pattern.match(persist_callback))

        async def edit(query, text, **kwargs):
            query.edits.append((text, kwargs))
            return True

        def dispatch(callback_id):
            query = _Query(user_id, persist_callback)
            query.id = callback_id
            query.message = SimpleNamespace(chat_id=chat_id, message_id=91)
            query.edit_message_text = lambda text, **kwargs: edit(query, text, **kwargs)
            _run_no_io(route.callback(
                SimpleNamespace(
                    callback_query=query,
                    effective_user=SimpleNamespace(id=user_id),
                    effective_chat=SimpleNamespace(id=chat_id),
                ),
                context,
            ))
            return query

        first = dispatch("persist-callback-1")
        self.assertEqual(1, len(first.answers))
        self.assertIn("Đã lưu kế hoạch", first.edits[0][0])
        row = anchor.execute(
            "SELECT plan_key, version FROM local_video_plans WHERE owner_id=? AND chat_id=? AND deleted_at=''",
            (str(user_id), str(chat_id)),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(1, anchor.execute(
            "SELECT COUNT(*) FROM local_video_plans WHERE owner_id=? AND chat_id=? AND deleted_at=''",
            (str(user_id), str(chat_id)),
        ).fetchone()[0])
        original_version = int(row["version"])

        same_callback_replay = dispatch("persist-callback-1")
        self.assertEqual(1, len(same_callback_replay.answers))
        self.assertFalse(same_callback_replay.edits)

        distinct_tap = dispatch("persist-callback-2")
        self.assertEqual(1, len(distinct_tap.answers))
        self.assertIn("Đã lưu kế hoạch", distinct_tap.edits[0][0])
        self.assertEqual(1, anchor.execute(
            "SELECT COUNT(*) FROM local_video_plans WHERE owner_id=? AND chat_id=? AND deleted_at=''",
            (str(user_id), str(chat_id)),
        ).fetchone()[0])
        stored = anchor.execute(
            "SELECT version FROM local_video_plans WHERE owner_id=? AND chat_id=? AND plan_key=? AND deleted_at=''",
            (str(user_id), str(chat_id), row["plan_key"]),
        ).fetchone()
        self.assertEqual(original_version, int(stored["version"]))
        self.assertEqual({"unchanged": True}, context.user_data["video_edit_sentinel"])

    def test_local_video_public_saved_plan_list_detail_back_uses_registered_route(self):
        import copy
        import html
        import sqlite3
        import time
        import uuid

        from services import local_video_planning_store
        from services import video_planning_assistant as planning_service

        user_id, chat_id, session_id = 7, 70, "lvlist01"
        state = planning_service.new_session(session_id, now=int(time.time()))

        def choose(current, verb, *args):
            return planning_service.apply_callback(
                current,
                planning_service.callback_data(current["session_id"], verb, *args),
            )["session"]

        state = choose(state, "goal", "cut_pacing")
        state = planning_service.apply_text_input(
            state,
            "Kế hoạch fixture: cắt nhịp gọn, giữ rõ sản phẩm.",
        )["session"]
        state = choose(state, "platform", "tiktok_9x16")
        state = choose(state, "source", "60_120")
        state = choose(state, "target", "30")
        state = choose(state, "asset", "video")
        state = choose(state, "assets_done")
        state = choose(state, "priority", "pace")
        state = choose(state, "priorities_done")
        state = choose(state, "operations_done")
        state = choose(state, "safety_done")
        self.assertEqual("summary", state["screen"])

        memory_uri = f"file:lvs27b_library_{uuid.uuid4().hex}?mode=memory&cache=shared"
        anchor = sqlite3.connect(memory_uri, uri=True)
        anchor.row_factory = sqlite3.Row
        self.addCleanup(anchor.close)
        with anchor:
            local_video_planning_store.ensure_schema(anchor)
            saved = local_video_planning_store.save_plan_from_session(
                anchor,
                owner_id=str(user_id),
                chat_id=str(chat_id),
                source_session_id=state["session_id"],
                plan=planning_service.serialize_plan(state),
                summary_text=planning_service.planning_summary_text(state),
            )
            foreign_owner = local_video_planning_store.save_plan_from_session(
                anchor,
                owner_id="8",
                chat_id=str(chat_id),
                source_session_id="lvforeign1",
                plan=planning_service.serialize_plan(state),
                summary_text="FOREIGN OWNER PLAN",
            )
            foreign_chat = local_video_planning_store.save_plan_from_session(
                anchor,
                owner_id=str(user_id),
                chat_id="71",
                source_session_id="lvforeign2",
                plan=planning_service.serialize_plan(state),
                summary_text="FOREIGN CHAT PLAN",
            )

        class _ImmediateLock:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

        service = SimpleNamespace(**{
            name: getattr(planning_service, name)
            for name in vars(planning_service)
            if not name.startswith("__")
        })
        service.open_transaction_lock = lambda *_args: _ImmediateLock()
        service.session_transaction_lock = lambda *_args: _ImmediateLock()

        start = BOT_SOURCE.index("# --- LOCAL VIDEO STUDIO 27B PUBLIC ---")
        end = BOT_SOURCE.index("# --- END LOCAL VIDEO STUDIO 27B PUBLIC ---", start)
        namespace = {
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "local_video_studio_public": service,
            "local_video_planning_store": local_video_planning_store,
            "local_video_studio_public_enabled": lambda: True,
            "menu_text_main_video_i18n": lambda _lang: "MAIN VIDEO MENU",
            "main_video_keyboard": lambda _lang: _Markup([]),
            "video_edit_hub_text": lambda _lang: "VIDEO EDIT HUB",
            "video_edit_hub_keyboard": lambda _lang: _Markup([]),
            "get_user_language": lambda _uid: "vi",
            "normalize_user_language": lambda lang: lang or "vi",
            "db_connect": lambda: sqlite3.connect(memory_uri, uri=True),
            "copy": copy,
            "html": html,
            "sqlite3": sqlite3,
            "time": time,
        }
        source = "from __future__ import annotations\n\n" + BOT_SOURCE[start:end]
        exec(compile(source, "bot.py:lvs27b-saved-plan-list-route", "exec"), namespace)

        registrations = []
        namespace["tg_app"] = SimpleNamespace(add_handler=registrations.append)
        namespace["CallbackQueryHandler"] = lambda callback, pattern: SimpleNamespace(
            callback=callback,
            pattern=re.compile(pattern),
        )
        registration = next(
            line.strip()
            for line in BOT_SOURCE.splitlines()
            if "tg_app.add_handler(CallbackQueryHandler(handle_local_video_studio_public_callback," in line
        )
        exec(registration, namespace)
        route = next(
            item for item in registrations
            if item.callback is namespace["handle_local_video_studio_public_callback"]
        )

        store = service.new_store()
        service.put_session(store, str(user_id), str(chat_id), state)
        context = SimpleNamespace(user_data={
            service.STATE_KEY: store,
            "video_edit_sentinel": {"unchanged": True},
        })

        async def edit(query, text, **kwargs):
            query.edits.append((text, kwargs))
            return True

        def dispatch(callback_data, callback_id):
            self.assertIsNotNone(route.pattern.match(callback_data))
            query = _Query(user_id, callback_data)
            query.id = callback_id
            query.message = SimpleNamespace(chat_id=chat_id, message_id=92)
            query.edit_message_text = lambda text, **kwargs: edit(query, text, **kwargs)
            _run_no_io(route.callback(
                SimpleNamespace(
                    callback_query=query,
                    effective_user=SimpleNamespace(id=user_id),
                    effective_chat=SimpleNamespace(id=chat_id),
                ),
                context,
            ))
            self.assertEqual(1, len(query.answers))
            self.assertEqual(1, len(query.edits))
            return query

        summary_keyboard = namespace["local_video_studio_public_keyboard"](
            service.render_view(state)
        )
        plans_callback = next(
            button.callback_data
            for row in summary_keyboard.inline_keyboard
            for button in row
            if button.callback_data.endswith("|plans")
        )
        list_query = dispatch(plans_callback, "library-list-1")
        list_text, list_kwargs = list_query.edits[-1]
        listed_callbacks = [
            button.callback_data
            for row in list_kwargs["reply_markup"].inline_keyboard
            for button in row
        ]
        detail_callback = service.callback_data(session_id, "view", saved["plan_key"])
        self.assertIn(detail_callback, listed_callbacks)
        self.assertNotIn(foreign_owner["plan_key"], " ".join(listed_callbacks))
        self.assertNotIn(foreign_chat["plan_key"], " ".join(listed_callbacks))
        self.assertIn("KẾ HOẠCH CỦA TÔI", list_text)

        detail_query = dispatch(detail_callback, "library-detail-1")
        detail_text, detail_kwargs = detail_query.edits[-1]
        detail_callbacks = [
            button.callback_data
            for row in detail_kwargs["reply_markup"].inline_keyboard
            for button in row
        ]
        back_to_list = service.callback_data(session_id, "library")
        self.assertIn("Kế hoạch đã lưu", detail_text)
        self.assertIn(back_to_list, detail_callbacks)

        back_query = dispatch(back_to_list, "library-back-1")
        back_text, back_kwargs = back_query.edits[-1]
        back_callbacks = [
            button.callback_data
            for row in back_kwargs["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertIn("KẾ HOẠCH CỦA TÔI", back_text)
        self.assertIn(detail_callback, back_callbacks)
        self.assertEqual(3, anchor.execute(
            "SELECT COUNT(*) FROM local_video_plans WHERE deleted_at=''"
        ).fetchone()[0])
        self.assertEqual({"unchanged": True}, context.user_data["video_edit_sentinel"])

    async def _record_safe_edit(self, query, text, **kwargs):
        query.edits.append((text, kwargs))


if __name__ == "__main__":
    unittest.main()
