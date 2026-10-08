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
            asyncio.run(namespace["handle_translation_callback"](update, SimpleNamespace()))
            self.assertEqual(query.answers, [((), {})])
            return query

        for source_type in ("text", "file"):
            with self.subTest(source_type=source_type):
                initial_update = SimpleNamespace(
                    callback_query=None,
                    effective_user=user,
                    message=_Message(),
                )
                asyncio.run(namespace["show_translation_picker"](
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

    def test_translation_voice_picker_label_matches_audio_callback_and_returns_from_more(self):
        edits = []
        contexts = []
        copy = {
            "translation_audio": "Dịch audio",
            "translation_text": "Văn bản",
            "translation_session_enable_voice": "Bật giọng nói",
            "translation_language": "Dịch ngôn ngữ",
            "translation_subtitle_dubbing": "Phụ đề và lồng tiếng",
            "translation_picker_choose": "Chọn nội dung",
            "translation_picker_target": "Ngôn ngữ đích",
            "translation_picker_no_charge": "Chưa xử lý ở bước này",
            "translation_picker_more": "Thêm ngôn ngữ",
            "translation_picker_back": "Quay lại",
            "main_menu": "Menu chính",
        }

        async def safe_edit(query, text, **kwargs):
            edits.append((query.data, text, kwargs))

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
            "build_2col_keyboard": build_two_column_keyboard,
            "get_user_language": lambda _uid: "vi",
            "enter_product_context": lambda *_args, **_kwargs: contexts.append("context"),
            "PRODUCT_CONTEXT_SHOWROOM": "showroom",
            "has_recent_audio_input": lambda _update: True,
            "safe_edit_query_message": safe_edit,
        }
        namespace = _load_functions(
            "translation_voice_menu_keyboard", "translation_pick_text",
            "translation_target_keyboard", "show_translation_picker",
            "handle_translation_callback", **dependencies,
        )
        route_pattern = _registered_pattern("handle_translation_callback")
        voice_menu = namespace["translation_voice_menu_keyboard"]("vi", parent="language")
        voice_button = next(
            button
            for row in voice_menu.inline_keyboard
            for button in row
            if button.callback_data == "tr_pick|voice"
        )
        self.assertEqual(voice_button.text, "🌐 Dịch audio")

        def press(callback):
            self.assertRegex(callback, route_pattern)
            query = _Query(991179, callback)
            update = SimpleNamespace(
                callback_query=query,
                effective_user=query.from_user,
                effective_message=SimpleNamespace(reply_to_message=None),
            )
            asyncio.run(namespace["handle_translation_callback"](update, SimpleNamespace()))
            self.assertEqual(query.answers, [((), {})])
            return query

        press(voice_button.callback_data)
        first_markup = edits[-1][2]["reply_markup"]
        first_callbacks = [
            button.callback_data
            for row in first_markup.inline_keyboard
            for button in row
        ]
        self.assertIn("tr_more|voice", first_callbacks)
        press("tr_more|voice")
        expanded_callbacks = [
            button.callback_data
            for row in edits[-1][2]["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertIn("tr_pick|voice", expanded_callbacks)
        press("tr_pick|voice")
        restored_callbacks = [
            button.callback_data
            for row in edits[-1][2]["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertEqual(restored_callbacks, first_callbacks)
        self.assertEqual(len(edits), 3)
        self.assertEqual(contexts, ["context"] * 3)

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

    def test_customer_image_menu_renders_and_its_back_returns_home_without_entering_tools(self):
        effects = []
        dependencies = _main_menu_dependencies(False, effects)
        copy = {
            "image_quick": "Quick image",
            "image_prompt_from_image": "Prompt from image",
            "image_ai_edit": "AI image edit",
            "image_edit": "Image edit",
            "back": "Back",
            "main_menu": "Main menu",
        }

        def build_two_column_keyboard(buttons, *, nav_back, lang, main_label):
            flat = [_Button(label, callback) for label, callback in buttons]
            rows = [flat[index:index + 2] for index in range(0, len(flat), 2)]
            rows.append([_Button(nav_back[0], nav_back[1]), _Button(main_label, "menu|main")])
            return _Markup(rows)

        dependencies.update({
            "public_hub_copy": lambda _lang: copy,
            "build_2col_keyboard": build_two_column_keyboard,
            "image_menu_v5_text": lambda _lang: "actual image menu",
            "localized_start_menu_text": lambda *_args: "actual main menu",
            "localized_main_menu_keyboard": lambda *_args: _Markup([]),
            "time": SimpleNamespace(perf_counter=lambda: 1.0),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
        })
        namespace = _load_functions(
            "menu_text_main_image", "menu_text_main_image_i18n", "main_image_keyboard",
            "localized_menu_content", "handle_menu_callback", **dependencies,
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
        # The image-tool callbacks are inspected only; no tool/engine callback is dispatched.
        home_query = _Query(991126, "menu|main")
        self.assertRegex(home_query.data, route_pattern)
        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=home_query), context,
        ))
        self.assertEqual([((), {})], home_query.answers)
        self.assertEqual("actual main menu", home_query.edits[0][0])

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

        def dispatch(callback_data):
            self.assertRegex(callback_data, route_pattern)
            query = _Query(user_id, callback_data)
            asyncio.run(namespace["handle_memory_callback"](
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

        dispatch(fresh_confirm)

        self.assertEqual("archived", notes[note["id"]]["status"])
        self.assertEqual(1, notes[note["id"]]["is_archived"])
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
            memory_require_access=lambda _update: asyncio.sleep(0, result=True),
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
            "free_hub_library_suggestions_text", "free_hub_library_suggestions_keyboard",
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
            FREE_HUB_LIBRARY_CATEGORIES={"video": ("video_prompt", "Prompt video")},
            FREE_HUB_LIBRARY_INDUSTRY_FILTERS={}, get_user_language=lambda _uid: "vi",
            clear_video_downloader_pending=lambda _uid: None,
            clear_free_hub_pending=clear_pending,
            get_free_hub_pending=lambda owner_id: dict(pending.get(owner_id, {})),
            set_free_hub_pending=set_pending,
            free_hub_main_text=lambda _lang: "Free Tools root fixture",
            prompt_library_suggestions=suggestions,
            prompt_library_item=lambda _library, item_id: (
                {"id": item_id, "title": item_id, "prompt": f"Text {item_id}"}
                if item_id == "fixture-1" else None
            ),
            safe_edit_or_send=render, time=SimpleNamespace(time=lambda: 1.0),
        )
        hub_pattern = _registered_pattern("handle_free_hub_callback")
        context = SimpleNamespace(user_data={})

        def dispatch(callback_data):
            self.assertRegex(callback_data, hub_pattern)
            query = _Query(user_id, callback_data)
            asyncio.run(hub["handle_free_hub_callback"](
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
            [("image_video_prompt", 0), ("meta_ai_prompt", 0), ("caption_hashtag", 0), ("content_idea", 0)],
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

    def test_free_tools_translation_prompt_back_clears_only_its_pending_state(self):
        user_id = 991137
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
        self.assertRegex(translate_entry, _registered_pattern("handle_free_hub_callback"))

        pending = {}

        def clear_pending(owner_id):
            return pending.pop(owner_id, None) is not None

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

        prompt = dispatch(translate_entry)
        back = prompt.edits[0][1]["reply_markup"].inline_keyboard[-1][0]
        self.assertEqual("freehub|main", back.callback_data)
        self.assertEqual("open_translate", pending[user_id]["task_type"])

        returned = dispatch(back.callback_data)
        self.assertEqual("Free Tools root fixture", returned.edits[0][0])
        self.assertNotIn(user_id, pending)

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

    async def _record_safe_edit(self, query, text, **kwargs):
        query.edits.append((text, kwargs))


if __name__ == "__main__":
    unittest.main()
