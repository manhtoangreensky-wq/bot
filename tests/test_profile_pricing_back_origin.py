"""Account-origin pricing screens keep their read-only navigation ancestry."""
import asyncio
import html
import importlib.util
import io
from pathlib import Path
import re
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location("account_pricing_fixture", Path(__file__).with_name("test_profile_credit_guide_back_origin.py"))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def _runtime(lang="vi"):
    ns, menu_route, _ = fixture._runtime(lang)
    reads, clears = [], []

    async def render(query, lines, markup):
        query.edits.append(("\n".join(lines), {"reply_markup": markup}))

    async def edit(query, text, **kwargs):
        query.edits.append((text, kwargs))

    ns.update({
        "html": html,
        "pricing_copy_language": lambda value: value,
        "public_page_title": lambda page, _locale: page,
        "user_is_vietnam_market": lambda _uid: False,
        "public_pricing_context": lambda: "CANONICAL",
        "public_pricing_lines": lambda section, ctx, _lang: reads.append((section, ctx)) or ["MEMBER CONTENT"],
        "public_account_flow_copy": lambda _lang: {key: key for key in
            ("save_birthday", "birthday_intro", "example", "birthday_manual_review")},
        "clear_media_creator_pending_states": lambda uid, **_kwargs: clears.append(uid),
        "edit_or_send_pricing_lines": render,
        "safe_edit_or_send": edit,
    })
    original_copy = ns["public_hub_copy"]
    ns["public_hub_copy"] = lambda locale: {**original_copy(locale), "common_no_charge": "No charge", "packages_label": "Packages"}
    for name in ("pricing_hub_lines", "pricing_catalog_lines", "pricing_video_lines", "pricing_image_lines", "pricing_main_lines",
                 "pricing_xu_lines_i18n", "billing_promotions_lines", "billing_promo_apply_lines"):
        ns[name] = lambda *args, name=name: reads.append((name, args)) or [name]
    for name in ("pricing_main_keyboard", "pricing_catalog_keyboard", "pricing_detail_keyboard",
                 "member_policy_keyboard", "billing_promotions_keyboard", "handle_pricing_callback"):
        exec(compile("from __future__ import annotations\n" + fixture.fixture._function(name), "bot.py:" + name, "exec"), ns)
    routes = []
    ns.update(tg_app=SimpleNamespace(add_handler=routes.append),
              CallbackQueryHandler=lambda callback, pattern: (callback, re.compile(pattern)))
    registration = next(line.strip() for line in fixture.fixture.SOURCE.splitlines()
                        if "tg_app.add_handler(CallbackQueryHandler(handle_pricing_callback," in line)
    exec(registration, ns)
    return ns, routes[0], menu_route, reads, clears


def _install_topup_fixture(ns):
    original_copy = ns["public_hub_copy"]
    ns.update({
        "public_hub_copy": lambda locale: {**original_copy(locale), "topup_label": "Top up",
                                             "manual_topup": "Manual top up", "main_menu": "Main menu"},
        "ui_text": lambda _locale, key: "🔙 Back" if key in {"common.back", "pricing.back"} else "Main menu",
        "menu_text_main_topup_i18n": lambda _locale, _uid: "TOPUP SELECTOR",
        "payos_package_callback_data": lambda package, uid: f"payos_pkg|{package}|{uid}",
        "manual_package_callback_data": lambda package, uid: f"manual|start|{package}|{uid}",
    })
    for name in ("main_topup_keyboard", "pricing_xu_keyboard", "vip_services_keyboard"):
        exec(compile("from __future__ import annotations\n" + fixture.fixture._function(name),
                     "bot.py:" + name, "exec"), ns)


def _buttons(query):
    return fixture._buttons(query)


def _back(query):
    return next(button.callback_data for button in _buttons(query)
                if button.text.startswith(("⬅", "🔙", "←")))


def _callback(query, action):
    return next(button.callback_data for button in _buttons(query)
                if button.callback_data.split("|")[:2] == ["pricing", action])


def _dispatch_immediate(route, data):
    handler, pattern = route
    assert pattern.match(data), f"registered route does not accept {data!r}"
    query = fixture.fixture.Query(data)
    coroutine = handler(SimpleNamespace(callback_query=query), SimpleNamespace(user_data={}))
    try:
        coroutine.send(None)
    except StopIteration:
        pass
    else:
        coroutine.close()
        raise AssertionError("fixture callback unexpectedly yielded asynchronous I/O")
    if query.answers != [((), {})]:
        raise AssertionError(f"callback acknowledgement mismatch: {query.answers!r}")
    return query


class AccountPricingOriginTests(unittest.TestCase):
    def test_public_catalog_back_returns_to_hub_and_home_to_main(self):
        ns, route, menu, _, _ = _runtime("vi")
        ns["time"] = SimpleNamespace(perf_counter=lambda: 1.0)
        ns["logger"] = SimpleNamespace(info=lambda *_args, **_kwargs: None)

        hub = fixture._dispatch(route, "pricing|main")
        catalog = fixture._dispatch(route, _callback(hub, "catalog"))
        returned_hub = fixture._dispatch(route, _back(catalog))
        self.assertEqual("pricing|main", _back(catalog))
        self.assertEqual("pricing_hub_lines", returned_hub.edits[0][0])
        self.assertEqual(
            [button.callback_data for button in _buttons(hub)],
            [button.callback_data for button in _buttons(returned_hub)],
        )

        main = fixture._dispatch(menu, next(button.callback_data for button in _buttons(catalog)
                                             if button.callback_data == "menu|main"))
        self.assertEqual("MAIN MENU", main.edits[0][0])
        for query in (hub, catalog, returned_hub, main):
            self.assertEqual([((), {})], query.answers)

    def test_public_storage_pricing_back_returns_to_catalog(self):
        ns, route, menu, _, _ = _runtime("vi")
        ns["time"] = SimpleNamespace(perf_counter=lambda: 1.0)
        ns["logger"] = SimpleNamespace(info=lambda *_args, **_kwargs: None)
        ns.update(NOTES_TEXT_FREE_MB=10, FILES_AUDIO_FREE_MB=20, TOTAL_FREE_STORAGE_MB=30,
                  storage_addon_lines=lambda: ["STORAGE ADD-ON FIXTURE"])
        for name in ("pricing_detail_keyboard", "pricing_storage_lines"):
            exec(compile("from __future__ import annotations\n" + fixture.fixture._function(name),
                         "bot.py:" + name, "exec"), ns)

        hub = fixture._dispatch(route, "pricing|main")
        catalog = fixture._dispatch(route, _callback(hub, "catalog"))
        storage = fixture._dispatch(route, _callback(catalog, "storage"))
        self.assertIn("STORAGE ADD-ON FIXTURE", storage.edits[0][0])
        self.assertEqual(
            ["menu|memory_storage_addon", "menu|memory_storage_status", "pricing|catalog", "menu|main"],
            [button.callback_data for button in _buttons(storage)],
        )

        returned_catalog = fixture._dispatch(route, _back(storage))
        self.assertEqual(catalog.edits[0][0], returned_catalog.edits[0][0])
        self.assertEqual(
            [button.callback_data for button in _buttons(catalog)],
            [button.callback_data for button in _buttons(returned_catalog)],
        )
        main_screen = fixture._dispatch(menu, next(button.callback_data for button in _buttons(storage)
                                                   if button.callback_data == "menu|main"))
        self.assertEqual("MAIN MENU", main_screen.edits[0][0])
        for query in (hub, catalog, storage, returned_catalog, main_screen):
            self.assertEqual([((), {})], query.answers)

    def test_public_free_pricing_back_returns_to_catalog(self):
        ns, route, menu, reads, _ = _runtime("vi")
        ns["time"] = SimpleNamespace(perf_counter=lambda: 1.0)
        ns["logger"] = SimpleNamespace(info=lambda *_args, **_kwargs: None)
        ns["public_pricing_locale"] = lambda lang: lang
        for name in ("pricing_detail_keyboard", "pricing_free_lines"):
            exec(compile("from __future__ import annotations\n" + fixture.fixture._function(name),
                         "bot.py:" + name, "exec"), ns)

        hub = fixture._dispatch(route, "pricing|main")
        catalog = fixture._dispatch(route, _callback(hub, "catalog"))
        free = fixture._dispatch(route, _callback(catalog, "free"))
        self.assertEqual("MEMBER CONTENT", free.edits[0][0])
        self.assertEqual("free", reads[-1][0])

        returned_catalog = fixture._dispatch(route, _back(free))
        self.assertEqual("pricing|catalog", _back(free))
        self.assertEqual(catalog.edits[0][0], returned_catalog.edits[0][0])
        self.assertEqual(
            [button.callback_data for button in _buttons(catalog)],
            [button.callback_data for button in _buttons(returned_catalog)],
        )
        main_screen = fixture._dispatch(menu, next(button.callback_data for button in _buttons(free)
                                                   if button.callback_data == "menu|main"))
        self.assertEqual("MAIN MENU", main_screen.edits[0][0])
        for query in (hub, catalog, free, returned_catalog, main_screen):
            self.assertEqual([((), {})], query.answers)

    def test_public_docs_pricing_back_returns_to_catalog(self):
        ns, route, menu, reads, _ = _runtime("vi")
        ns["time"] = SimpleNamespace(perf_counter=lambda: 1.0)
        ns["logger"] = SimpleNamespace(info=lambda *_args, **_kwargs: None)
        ns["public_pricing_locale"] = lambda lang: lang
        for name in ("pricing_detail_keyboard", "pricing_docs_lines"):
            exec(compile("from __future__ import annotations\n" + fixture.fixture._function(name),
                         "bot.py:" + name, "exec"), ns)

        hub = fixture._dispatch(route, "pricing|main")
        catalog = fixture._dispatch(route, _callback(hub, "catalog"))
        docs = fixture._dispatch(route, _callback(catalog, "docs"))
        self.assertEqual("MEMBER CONTENT", docs.edits[0][0])
        self.assertEqual("docs", reads[-1][0])

        returned_catalog = fixture._dispatch(route, _back(docs))
        self.assertEqual("pricing|catalog", _back(docs))
        self.assertEqual(catalog.edits[0][0], returned_catalog.edits[0][0])
        self.assertEqual(
            [button.callback_data for button in _buttons(catalog)],
            [button.callback_data for button in _buttons(returned_catalog)],
        )
        main_screen = fixture._dispatch(menu, next(button.callback_data for button in _buttons(docs)
                                                   if button.callback_data == "menu|main"))
        self.assertEqual("MAIN MENU", main_screen.edits[0][0])
        for query in (hub, catalog, docs, returned_catalog, main_screen):
            self.assertEqual([((), {})], query.answers)

    def test_public_image_pricing_back_returns_to_catalog(self):
        ns, route, menu, _, _ = _runtime("vi")
        ns["time"] = SimpleNamespace(perf_counter=lambda: 1.0)
        ns["logger"] = SimpleNamespace(info=lambda *_args, **_kwargs: None)
        exec(compile("from __future__ import annotations\n" + fixture.fixture._function("pricing_detail_keyboard"),
                     "bot.py:pricing_detail_keyboard", "exec"), ns)

        hub = fixture._dispatch(route, "pricing|main")
        catalog = fixture._dispatch(route, _callback(hub, "catalog"))
        image = fixture._dispatch(route, _callback(catalog, "image"))
        self.assertEqual("pricing_image_lines", image.edits[0][0])
        self.assertEqual(
            ["menu|main_topup|pricing_image", "pkgcombo:home:pricing_image", "pricing|catalog", "menu|main"],
            [button.callback_data for button in _buttons(image)],
        )

        returned_catalog = fixture._dispatch(route, _back(image))
        self.assertEqual(catalog.edits[0][0], returned_catalog.edits[0][0])
        self.assertEqual(
            [button.callback_data for button in _buttons(catalog)],
            [button.callback_data for button in _buttons(returned_catalog)],
        )
        main_screen = fixture._dispatch(menu, next(button.callback_data for button in _buttons(image)
                                                   if button.callback_data == "menu|main"))
        self.assertEqual("MAIN MENU", main_screen.edits[0][0])
        for query in (hub, catalog, image, returned_catalog, main_screen):
            self.assertEqual([((), {})], query.answers)

    def test_public_video_pricing_back_returns_to_catalog(self):
        ns, route, menu, _, _ = _runtime("vi")
        ns["time"] = SimpleNamespace(perf_counter=lambda: 1.0)
        ns["logger"] = SimpleNamespace(info=lambda *_args, **_kwargs: None)
        exec(compile("from __future__ import annotations\n" + fixture.fixture._function("pricing_detail_keyboard"),
                     "bot.py:pricing_detail_keyboard", "exec"), ns)

        hub = fixture._dispatch(route, "pricing|main")
        catalog = fixture._dispatch(route, _callback(hub, "catalog"))
        video = fixture._dispatch(route, _callback(catalog, "video"))
        self.assertEqual("pricing_video_lines", video.edits[0][0])

        returned_catalog = fixture._dispatch(route, _back(video))
        self.assertEqual("pricing|catalog", _back(video))
        self.assertEqual(catalog.edits[0][0], returned_catalog.edits[0][0])
        self.assertEqual(
            [button.callback_data for button in _buttons(catalog)],
            [button.callback_data for button in _buttons(returned_catalog)],
        )
        main_screen = fixture._dispatch(menu, next(button.callback_data for button in _buttons(video)
                                                   if button.callback_data == "menu|main"))
        self.assertEqual("MAIN MENU", main_screen.edits[0][0])
        for query in (hub, catalog, video, returned_catalog, main_screen):
            self.assertEqual([((), {})], query.answers)

    def test_public_music_pricing_back_returns_to_catalog(self):
        ns, route, menu, reads, _ = _runtime("vi")
        ns["time"] = SimpleNamespace(perf_counter=lambda: 1.0)
        ns["logger"] = SimpleNamespace(info=lambda *_args, **_kwargs: None)
        ns["public_pricing_locale"] = lambda lang: lang
        for name in ("pricing_detail_keyboard", "pricing_music_lines"):
            exec(compile("from __future__ import annotations\n" + fixture.fixture._function(name),
                         "bot.py:" + name, "exec"), ns)

        hub = fixture._dispatch(route, "pricing|main")
        catalog = fixture._dispatch(route, _callback(hub, "catalog"))
        music = fixture._dispatch(route, _callback(catalog, "music"))
        self.assertEqual("MEMBER CONTENT", music.edits[0][0])
        self.assertEqual("music", reads[-1][0])

        returned_catalog = fixture._dispatch(route, _back(music))
        self.assertEqual("pricing|catalog", _back(music))
        self.assertEqual(catalog.edits[0][0], returned_catalog.edits[0][0])
        self.assertEqual(
            [button.callback_data for button in _buttons(catalog)],
            [button.callback_data for button in _buttons(returned_catalog)],
        )
        main_screen = fixture._dispatch(menu, next(button.callback_data for button in _buttons(music)
                                                   if button.callback_data == "menu|main"))
        self.assertEqual("MAIN MENU", main_screen.edits[0][0])
        for query in (hub, catalog, music, returned_catalog, main_screen):
            self.assertEqual([((), {})], query.answers)

    def test_public_subtitle_pricing_back_returns_to_catalog(self):
        ns, route, menu, reads, _ = _runtime("vi")
        ns["time"] = SimpleNamespace(perf_counter=lambda: 1.0)
        ns["logger"] = SimpleNamespace(info=lambda *_args, **_kwargs: None)
        ns["public_pricing_locale"] = lambda lang: lang
        for name in ("pricing_detail_keyboard", "pricing_subtitle_lines"):
            exec(compile("from __future__ import annotations\n" + fixture.fixture._function(name),
                         "bot.py:" + name, "exec"), ns)

        hub = fixture._dispatch(route, "pricing|main")
        catalog = fixture._dispatch(route, _callback(hub, "catalog"))
        subtitle = fixture._dispatch(route, _callback(catalog, "subtitle"))
        self.assertEqual("MEMBER CONTENT", subtitle.edits[0][0])
        self.assertEqual("subtitle", reads[-1][0])

        returned_catalog = fixture._dispatch(route, _back(subtitle))
        self.assertEqual("pricing|catalog", _back(subtitle))
        self.assertEqual(catalog.edits[0][0], returned_catalog.edits[0][0])
        self.assertEqual(
            [button.callback_data for button in _buttons(catalog)],
            [button.callback_data for button in _buttons(returned_catalog)],
        )
        main_screen = fixture._dispatch(menu, next(button.callback_data for button in _buttons(subtitle)
                                                   if button.callback_data == "menu|main"))
        self.assertEqual("MAIN MENU", main_screen.edits[0][0])
        for query in (hub, catalog, subtitle, returned_catalog, main_screen):
            self.assertEqual([((), {})], query.answers)

    def test_public_catalog_total_back_returns_to_catalog(self):
        ns, route, _, _, _ = _runtime("vi")
        hub = fixture._dispatch(route, "pricing|main")
        catalog = fixture._dispatch(route, _callback(hub, "catalog"))
        total = fixture._dispatch(route, _callback(catalog, "total"))
        self.assertEqual("pricing_main_lines", total.edits[0][0])

        total_back = _back(total)
        self.assertEqual("pricing|catalog", total_back)
        catalog_again = fixture._dispatch(route, total_back)
        self.assertEqual(catalog.edits[0][0], catalog_again.edits[0][0])
        self.assertEqual(
            [button.callback_data for button in _buttons(catalog)],
            [button.callback_data for button in _buttons(catalog_again)],
        )
        for query in (hub, catalog, total, catalog_again):
            self.assertEqual([((), {})], query.answers)

    def test_public_catalog_member_back_returns_to_catalog(self):
        ns, route, _, _, _ = _runtime("vi")
        hub = fixture._dispatch(route, "pricing|main")
        catalog = fixture._dispatch(route, _callback(hub, "catalog"))
        member = fixture._dispatch(route, _callback(catalog, "member"))
        self.assertEqual("MEMBER CONTENT", member.edits[0][0])
        catalog_back = _back(member)
        self.assertEqual("pricing|catalog", catalog_back)

        birthday_callback = next(button.callback_data for button in _buttons(member)
                                 if button.callback_data.startswith("pricing|birthday"))
        self.assertEqual("pricing|birthday|catalog", birthday_callback)
        birthday = fixture._dispatch(route, birthday_callback)
        birthday_back = _back(birthday)
        self.assertEqual("pricing|member|catalog", birthday_back)
        member_again = fixture._dispatch(route, birthday_back)
        self.assertEqual("MEMBER CONTENT", member_again.edits[0][0])

        catalog_again = fixture._dispatch(route, catalog_back)
        self.assertEqual(catalog.edits[0][0], catalog_again.edits[0][0])
        self.assertEqual(
            [button.callback_data for button in _buttons(catalog)],
            [button.callback_data for button in _buttons(catalog_again)],
        )
        legacy_member = fixture._dispatch(route, "pricing|member")
        self.assertEqual("pricing|main", _back(legacy_member))
        for query in (hub, catalog, member, birthday, member_again, catalog_again, legacy_member):
            self.assertEqual([((), {})], query.answers)

    def test_public_voice_pricing_back_restores_catalog_then_pricing_hub(self):
        ns, route, menu, _, _ = _runtime("vi")
        ns["pricing_voice_lines"] = lambda _lang: ["VOICE PRICING FIXTURE"]
        ns["time"] = SimpleNamespace(perf_counter=lambda: 1.0)
        ns["logger"] = SimpleNamespace(info=lambda *_args, **_kwargs: None)

        hub = fixture._dispatch(route, "pricing|main")
        catalog = fixture._dispatch(route, _callback(hub, "catalog"))
        voice = fixture._dispatch(route, _callback(catalog, "voice"))
        self.assertEqual("VOICE PRICING FIXTURE", voice.edits[0][0])

        returned_catalog = fixture._dispatch(route, _back(voice))
        self.assertEqual("pricing|catalog", _back(voice))
        self.assertEqual(catalog.edits[0][0], returned_catalog.edits[0][0])
        self.assertEqual(
            [button.callback_data for button in _buttons(catalog)],
            [button.callback_data for button in _buttons(returned_catalog)],
        )

        returned_hub = fixture._dispatch(route, _back(returned_catalog))
        self.assertEqual("pricing|main", _back(returned_catalog))
        self.assertEqual("pricing_hub_lines", returned_hub.edits[0][0])
        home = next(button.callback_data for button in _buttons(returned_hub)
                    if button.callback_data == "menu|main")
        main_screen = fixture._dispatch(menu, home)
        self.assertEqual("MAIN MENU", main_screen.edits[0][0])

        for query in (hub, catalog, voice, returned_catalog, returned_hub, main_screen):
            self.assertEqual([((), {})], query.answers)

    def test_public_pricing_guide_back_returns_to_pricing_hub(self):
        ns, route, menu, _, _ = _runtime("vi")
        ns["pricing_guide_lines"] = lambda _lang: ["GUIDE FIXTURE"]
        ns["effective_public_base_url"] = lambda: ""
        ns["time"] = SimpleNamespace(perf_counter=lambda: 1.0)
        ns["logger"] = SimpleNamespace(info=lambda *_args, **_kwargs: None)

        hub = fixture._dispatch(route, "pricing|main")
        catalog = fixture._dispatch(route, _callback(hub, "catalog"))
        guide = fixture._dispatch(route, _callback(catalog, "guide"))
        self.assertEqual("GUIDE FIXTURE", guide.edits[0][0])
        self.assertIn("pricing|download_pricing", [button.callback_data for button in _buttons(guide)])
        self.assertIn("pricing|download_guide", [button.callback_data for button in _buttons(guide)])

        guide_back = _back(guide)
        self.assertEqual("pricing|main", guide_back)
        returned_hub = fixture._dispatch(route, guide_back)
        self.assertEqual("pricing_hub_lines", returned_hub.edits[0][0])
        home = next(button.callback_data for button in _buttons(returned_hub)
                    if button.callback_data == "menu|main")
        main_screen = fixture._dispatch(menu, home)
        self.assertEqual("MAIN MENU", main_screen.edits[0][0])
        for query in (hub, catalog, guide, returned_hub, main_screen):
            self.assertEqual([((), {})], query.answers)

    def test_public_pricing_guide_back_and_home_return_to_hub_for_all_fallback_locales(self):
        from services.pricing_guide_content import PUBLIC_COPY_LOCALES

        for locale in sorted(PUBLIC_COPY_LOCALES - {"vi", "en", "zh"}):
            with self.subTest(locale=locale):
                ns, pricing_route, menu_route, _, _ = _runtime(locale)
                ns.update(
                    pricing_guide_lines=lambda lang: [f"GUIDE FIXTURE:{lang}"],
                    effective_public_base_url=lambda: "",
                    time=SimpleNamespace(perf_counter=lambda: 1.0),
                    logger=SimpleNamespace(info=lambda *_args, **_kwargs: None),
                )

                hub = _dispatch_immediate(pricing_route, "pricing|main")
                hub_callbacks = [button.callback_data for button in _buttons(hub)]
                self.assertIn("pricing|guide", hub_callbacks)
                guide = _dispatch_immediate(pricing_route, "pricing|guide")
                self.assertEqual(f"GUIDE FIXTURE:{locale}", guide.edits[0][0])

                guide_buttons = _buttons(guide)
                back = next(button for button in guide_buttons
                            if button.text.startswith(("⬅", "🔙", "←")))
                home = next(button for button in guide_buttons
                            if button.callback_data == "menu|main")
                self.assertEqual("pricing|main", back.callback_data)

                returned_hub = _dispatch_immediate(pricing_route, back.callback_data)
                self.assertEqual("pricing_hub_lines", returned_hub.edits[0][0])
                self.assertEqual(hub_callbacks, [button.callback_data for button in _buttons(returned_hub)])
                main = _dispatch_immediate(menu_route, home.callback_data)
                self.assertEqual("MAIN MENU", main.edits[0][0])

    def test_emitted_pricing_download_buttons_send_generated_documents(self):
        from services.pricing_guide_content import GUIDE_DOWNLOAD_FILENAME, PRICING_DOWNLOAD_FILENAME

        ns, route, _, _, _ = _runtime("vi")
        ns.update(
            time=SimpleNamespace(perf_counter=lambda: 1.0),
            logger=SimpleNamespace(info=lambda *_args, **_kwargs: None),
            io=io,
            PRICING_DOWNLOAD_FILENAME=PRICING_DOWNLOAD_FILENAME,
            GUIDE_DOWNLOAD_FILENAME=GUIDE_DOWNLOAD_FILENAME,
            public_pricing_context=lambda: "FIXTURE-CONTEXT",
            public_pricing_markdown=lambda context, locale: f"PRICING:{locale}:{context}",
            public_guide_markdown=lambda locale: f"GUIDE:{locale}",
            public_page_title=lambda page, _locale: {"pricing": "Bảng giá", "guide": "Hướng dẫn"}[page],
            pricing_guide_lines=lambda _lang: ["GUIDE FIXTURE"],
            effective_public_base_url=lambda: "",
        )
        helper = fixture.fixture._function("send_generated_markdown_document")
        exec(compile("from __future__ import annotations\n" + helper, "bot.py:send_generated_markdown_document", "exec"), ns)

        handler, pattern = route

        def dispatch(callback_data, message=None):
            self.assertRegex(callback_data, pattern)
            query = fixture.fixture.Query(callback_data)
            if message is not None:
                query.message = message
            coroutine = handler(SimpleNamespace(callback_query=query), SimpleNamespace(user_data={}))
            try:
                coroutine.send(None)
            except StopIteration:
                return query
            coroutine.close()
            self.fail("fixture callback yielded I/O")

        hub = dispatch("pricing|main")
        catalog = dispatch(_callback(hub, "catalog"))
        guide = dispatch(_callback(catalog, "guide"))
        emitted = (
            (catalog, "pricing|download_pricing", PRICING_DOWNLOAD_FILENAME, "PRICING:vi:FIXTURE-CONTEXT", "📥 Bảng giá"),
            (guide, "pricing|download_guide", GUIDE_DOWNLOAD_FILENAME, "GUIDE:vi", "📘 Hướng dẫn"),
        )

        for _screen, callback_data, filename, expected_content, expected_caption in emitted:
            with self.subTest(callback_data=callback_data):
                button = next(button for button in _buttons(_screen) if button.callback_data == callback_data)
                self.assertIsNotNone(button)
                sent = []

                async def reply_document(**kwargs):
                    sent.append((kwargs["document"].getvalue().decode("utf-8"), kwargs))

                query = dispatch(button.callback_data, SimpleNamespace(reply_document=reply_document))

                self.assertEqual([((), {})], query.answers)
                self.assertEqual(1, len(sent))
                content, payload = sent[0]
                self.assertEqual(expected_content, content)
                self.assertEqual(filename, payload["filename"])
                self.assertEqual(filename, payload["document"].name)
                self.assertEqual(expected_caption, payload["caption"])

    def test_direct_pricing_xu_command_topup_back_returns_to_xu(self):
        ns, route, menu, _, _ = _runtime()
        _install_topup_fixture(ns)
        sent = []

        async def send_pricing(_message, lines, keyboard, **_kwargs):
            sent.append((lines, keyboard))

        ns.update(get_user_language=lambda _uid: "vi", send_pricing_lines=send_pricing)
        command = fixture.fixture._function("cmd_pricing_xu")
        exec(compile("from __future__ import annotations\n" + command, "bot.py:cmd_pricing_xu", "exec"), ns)
        update = SimpleNamespace(effective_user=SimpleNamespace(id=123), message=object())
        asyncio.run(ns["cmd_pricing_xu"](update, SimpleNamespace()))

        emitted = next(button.callback_data for row in sent[0][1].inline_keyboard for button in row
                       if button.callback_data.startswith("menu|main_topup"))
        self.assertEqual("menu|main_topup|pricing_xu", emitted)
        self.assertLessEqual(len(emitted.encode("utf-8")), 64)
        topup = fixture._dispatch(menu, emitted)
        self.assertEqual("pricing|xu", _back(topup))
        returned = fixture._dispatch(route, _back(topup))
        self.assertEqual("pricing_xu_lines_i18n", returned.edits[0][0])

    def test_unsupported_locale_catalog_topup_returns_to_catalog(self):
        from services.pricing_guide_content import PUBLIC_COPY_LOCALES
        for locale in sorted(PUBLIC_COPY_LOCALES - {"vi", "en", "zh"}):
            with self.subTest(locale=locale):
                ns, route, menu, _, _ = _runtime(locale)
                _install_topup_fixture(ns)
                entry = next(button.callback_data for row in ns["main_profile_keyboard"](locale).inline_keyboard
                             for button in row if button.callback_data.split("|")[:2] == ["pricing", "main"])
                main = fixture._dispatch(route, entry)
                catalog = fixture._dispatch(route, _callback(main, "catalog"))
                topup_callback = next(button.callback_data for button in _buttons(catalog)
                                      if button.callback_data.startswith("menu|main_topup"))
                topup = fixture._dispatch(menu, topup_callback)
                self.assertEqual("pricing|catalog|profile", _back(topup))
                returned = fixture._dispatch(route, _back(topup))
                self.assertEqual(catalog.edits[0][0], returned.edits[0][0])

    def test_xu_read_screen_topup_returns_to_the_same_xu_screen(self):
        ns, route, menu, _, _ = _runtime()
        _install_topup_fixture(ns)
        source = ns["vip_services_keyboard"]("vi")
        xu_callback = next(button.callback_data for row in source.inline_keyboard for button in row
                           if button.callback_data == "pricing|xu")
        xu = fixture._dispatch(route, xu_callback)
        topup_callback = next(button.callback_data for button in _buttons(xu)
                              if button.callback_data.startswith("menu|main_topup"))
        topup = fixture._dispatch(menu, topup_callback)
        self.assertEqual("pricing|xu", _back(topup))
        returned = fixture._dispatch(route, _back(topup))
        self.assertEqual(xu.edits[0][0], returned.edits[0][0])

    def test_topup_back_returns_to_the_pricing_screen_that_emitted_it(self):
        ns, route, menu, _, _ = _runtime()
        _install_topup_fixture(ns)
        ns["user_is_vietnam_market"] = lambda _uid: True

        main = fixture._dispatch(route, "pricing|main|profile")
        offers = fixture._dispatch(route, _callback(main, "promotions"))
        promo_guide = fixture._dispatch(route, _callback(offers, "promo_apply"))
        catalog = fixture._dispatch(route, _callback(main, "catalog"))
        video = fixture._dispatch(route, _callback(catalog, "video"))
        image = fixture._dispatch(route, _callback(catalog, "image"))
        cases = (
            (main, "pricing|main|profile"),
            (offers, "pricing|promotions|profile"),
            (promo_guide, "pricing|promo_apply|profile"),
            (video, "pricing|video|profile"),
            (image, "pricing|image|profile"),
        )
        for parent, expected_parent in cases:
            with self.subTest(parent=expected_parent):
                topup_callback = next(button.callback_data for button in _buttons(parent)
                                      if button.callback_data.startswith("menu|main_topup"))
                topup = fixture._dispatch(menu, topup_callback)
                self.assertEqual("TOPUP SELECTOR", topup.edits[0][0])
                callbacks = [button.callback_data for button in _buttons(topup)]
                self.assertEqual(
                    ["payos_pkg|10k|123", "payos_pkg|20k|123", "payos_pkg|50k|123",
                     "payos_pkg|100k|123", "payos_pkg|200k|123", "payos_pkg|500k|123",
                     "manual|start|manual_custom|123"],
                    [data for data in callbacks if data.startswith(("payos_pkg|", "manual|"))],
                )
                self.assertIn("menu|main", callbacks)
                self.assertTrue(all(len(data.encode("utf-8")) <= 64 for data in callbacks))
                self.assertEqual(expected_parent, _back(topup))
                returned = fixture._dispatch(route, _back(topup))
                self.assertEqual(parent.edits[0][0], returned.edits[0][0])

    def test_legacy_pricing_screens_keep_their_exact_topup_parent(self):
        ns, route, menu, _, _ = _runtime()
        _install_topup_fixture(ns)
        ns["user_is_vietnam_market"] = lambda _uid: True

        main = fixture._dispatch(route, "pricing|main")
        offers = fixture._dispatch(route, _callback(main, "promotions"))
        promo_guide = fixture._dispatch(route, _callback(offers, "promo_apply"))
        catalog = fixture._dispatch(route, _callback(main, "catalog"))
        video = fixture._dispatch(route, _callback(catalog, "video"))
        image = fixture._dispatch(route, _callback(catalog, "image"))
        cases = (
            (main, "pricing|main"),
            (offers, "pricing|promotions"),
            (promo_guide, "pricing|promo_apply"),
            (video, "pricing|video"),
            (image, "pricing|image"),
        )
        for parent, expected_parent in cases:
            with self.subTest(parent=expected_parent):
                topup_callback = next(button.callback_data for button in _buttons(parent)
                                      if button.callback_data.startswith("menu|main_topup"))
                topup = fixture._dispatch(menu, topup_callback)
                self.assertEqual(expected_parent, _back(topup))
                returned = fixture._dispatch(route, _back(topup))
                self.assertEqual(parent.edits[0][0], returned.edits[0][0])

    def test_account_pricing_catalog_detail_back_chain_returns_to_account(self):
        for lang in ("vi", "en", "zh"):
            with self.subTest(lang=lang):
                ns, route, menu, _, _ = _runtime(lang)
                entry = next(button.callback_data for row in ns["main_profile_keyboard"](lang).inline_keyboard
                             for button in row if button.callback_data.split("|")[:2] == ["pricing", "main"])
                main = fixture._dispatch(route, entry)
                self.assertIn("menu|main_profile", [button.callback_data for button in _buttons(main)])
                catalog = fixture._dispatch(route, _callback(main, "catalog"))
                detail = fixture._dispatch(route, _callback(catalog, "video"))
                catalog_again = fixture._dispatch(route, _back(detail))
                main_again = fixture._dispatch(route, _back(catalog_again))
                self.assertEqual("menu|main_profile", _back(main_again))
                account = fixture._dispatch(menu, _back(main_again))
                self.assertEqual("ACCOUNT SCREEN", account.edits[0][0])

    def test_account_member_birthday_back_retains_member_then_account(self):
        ns, route, _, _, _ = _runtime()
        entry = next(button.callback_data for row in ns["main_profile_keyboard"]().inline_keyboard
                     for button in row if button.callback_data.split("|")[:2] == ["pricing", "member"])
        member = fixture._dispatch(route, entry)
        self.assertEqual("menu|main_profile", _back(member))
        birthday = fixture._dispatch(route, _callback(member, "birthday"))
        member_again = fixture._dispatch(route, _back(birthday))
        self.assertEqual("MEMBER CONTENT", member_again.edits[0][0])
        self.assertEqual("menu|main_profile", _back(member_again))

    def test_member_opened_from_account_catalog_returns_to_catalog(self):
        ns, route, _, _, _ = _runtime()
        entry = next(button.callback_data for row in ns["main_profile_keyboard"]().inline_keyboard
                     for button in row if button.callback_data.split("|")[:2] == ["pricing", "main"])
        main = fixture._dispatch(route, entry)
        catalog = fixture._dispatch(route, _callback(main, "catalog"))
        member = fixture._dispatch(route, _callback(catalog, "member"))
        catalog_again = fixture._dispatch(route, _back(member))
        self.assertEqual("pricing_catalog_lines", catalog_again.edits[0][0])
        main_again = fixture._dispatch(route, _back(catalog_again))
        self.assertEqual("menu|main_profile", _back(main_again))

    def test_catalog_total_returns_to_catalog_before_account_pricing(self):
        ns, route, _, _, _ = _runtime()
        main = fixture._dispatch(route, "pricing|main|profile")
        catalog = fixture._dispatch(route, _callback(main, "catalog"))
        total = fixture._dispatch(route, _callback(catalog, "total"))
        catalog_again = fixture._dispatch(route, _back(total))
        self.assertEqual("pricing_catalog_lines", catalog_again.edits[0][0])

    def test_offer_code_guide_returns_to_offers_before_account_pricing(self):
        ns, route, _, _, _ = _runtime()
        ns["user_is_vietnam_market"] = lambda _uid: True
        main = fixture._dispatch(route, "pricing|main|profile")
        offers = fixture._dispatch(route, _callback(main, "promotions"))
        guide = fixture._dispatch(route, _callback(offers, "promo_apply"))
        offers_again = fixture._dispatch(route, _back(guide))
        self.assertEqual("billing_promotions_lines", offers_again.edits[0][0])

    def test_international_catalog_fallback_keeps_account_back_chain(self):
        from services.pricing_guide_content import PUBLIC_COPY_LOCALES
        ns, route, _, _, _ = _runtime("fr")
        for locale in sorted(PUBLIC_COPY_LOCALES - {"vi", "en", "zh"}):
            with self.subTest(locale=locale):
                ns["get_user_language"] = lambda _uid, locale=locale: locale
                entry = next(button.callback_data for row in ns["main_profile_keyboard"](locale).inline_keyboard
                             for button in row if button.callback_data.split("|")[:2] == ["pricing", "main"])
                main = fixture._dispatch(route, entry)
                catalog = fixture._dispatch(route, _callback(main, "catalog"))
                main_again = fixture._dispatch(route, _back(catalog))
                self.assertEqual("menu|main_profile", _back(main_again))
                self.assertTrue(all(len(button.callback_data.encode("utf-8")) <= 64 for button in _buttons(catalog)))

    def test_public_international_catalog_back_returns_to_pricing_hub(self):
        from services.pricing_guide_content import PUBLIC_COPY_LOCALES
        ns, route, _, _, _ = _runtime("fr")
        for locale in sorted(PUBLIC_COPY_LOCALES - {"vi", "en", "zh"}):
            with self.subTest(locale=locale):
                ns["get_user_language"] = lambda _uid, locale=locale: locale
                hub = fixture._dispatch(route, "pricing|main")
                catalog = fixture._dispatch(route, _callback(hub, "catalog"))

                back_buttons = [button for button in _buttons(catalog)
                                if button.text.startswith(("⬅", "🔙", "←"))]
                self.assertEqual(1, len(back_buttons))
                self.assertEqual("pricing|main", back_buttons[0].callback_data)
                self.assertEqual(ns["ui_text"](locale, "common.back"), back_buttons[0].text)

                original = [button.callback_data for row in ns["pricing_main_keyboard"](locale).inline_keyboard
                            for button in row]
                expected = [
                    "pricing|main" if data == "pricing|catalog"
                    else "menu|main_topup|pricing_catalog" if data == "menu|main_topup"
                    else "pkgcombo:home:pricing_catalog" if data == "pkgcombo:home"
                    else data
                    for data in original
                ]
                actual = [button.callback_data for button in _buttons(catalog)]
                self.assertEqual(expected, actual)

                returned = fixture._dispatch(route, back_buttons[0].callback_data)
                self.assertEqual("pricing_hub_lines", returned.edits[0][0])
                self.assertEqual([((), {})], returned.answers)

    def test_public_english_chinese_catalog_details_return_to_catalog(self):
        expected_catalog_callbacks = [
            "pricing|image", "pricing|video", "pricing|frame", "pricing|voice",
            "pricing|docs", "pricing|storage", "pricing|package_summary",
            "pricing|premium", "pricing|main", "menu|main",
        ]
        line_helpers = (
            "pricing_frame_video_lines", "pricing_voice_lines", "pricing_docs_lines",
            "pricing_storage_lines", "pricing_package_summary_lines", "pricing_premium_lines",
        )
        for locale, back_label in (("en", "⬅️ Back"), ("zh", "⬅️ 返回")):
            with self.subTest(locale=locale):
                ns, route, menu, _, _ = _runtime(locale)
                ns["pricing_copy_language"] = lambda value: value
                for name in line_helpers:
                    ns[name] = lambda *args, _name=name: [_name]
                exec(compile("from __future__ import annotations\n" + fixture.fixture._function("pricing_package_summary_keyboard"),
                             "bot.py:pricing_package_summary_keyboard", "exec"), ns)

                hub = fixture._dispatch(route, "pricing|main")
                self.assertEqual("pricing_hub_lines", hub.edits[0][0])
                self.assertEqual([((), {})], hub.answers)
                catalog = fixture._dispatch(route, _callback(hub, "catalog"))
                self.assertEqual("pricing_catalog_lines", catalog.edits[0][0])
                self.assertEqual(expected_catalog_callbacks,
                                 [button.callback_data for button in _buttons(catalog)])
                self.assertEqual([((), {})], catalog.answers)

                back = next(button for button in _buttons(catalog)
                            if button.text.startswith(("⬅", "🔙", "←")))
                home = next(button for button in _buttons(catalog)
                            if button.callback_data == "menu|main")
                self.assertEqual(back_label, back.text)
                self.assertEqual("pricing|main", back.callback_data)
                self.assertTrue(all(len(button.callback_data.encode("utf-8")) <= 64
                                    for button in _buttons(catalog)))

                for action in expected_catalog_callbacks[:8]:
                    detail = fixture._dispatch(route, action)
                    self.assertEqual([((), {})], detail.answers)
                    detail_back = _back(detail)
                    self.assertEqual("pricing|catalog", detail_back)
                    returned_catalog = fixture._dispatch(route, detail_back)
                    self.assertEqual("pricing_catalog_lines", returned_catalog.edits[0][0])
                    self.assertEqual(expected_catalog_callbacks,
                                     [button.callback_data for button in _buttons(returned_catalog)])
                    self.assertEqual([((), {})], returned_catalog.answers)

                returned_hub = fixture._dispatch(route, back.callback_data)
                self.assertEqual("pricing_hub_lines", returned_hub.edits[0][0])
                self.assertEqual([((), {})], returned_hub.answers)
                ns.update(time=SimpleNamespace(perf_counter=lambda: 1.0),
                          logger=SimpleNamespace(info=lambda *_args, **_kwargs: None))
                main = fixture._dispatch(menu, home.callback_data)
                self.assertEqual("MAIN MENU", main.edits[0][0])
                self.assertEqual([((), {})], main.answers)

    def test_invalid_origin_stops_before_cleanup_data_or_render(self):
        _ns, route, _, reads, clears = _runtime()
        for data in ("pricing|main|", "pricing|main|admin", "pricing|main|profile|extra",
                     "pricing|video|profile_catalog", "pricing|video|catalog",
                     "pricing|main|catalog", "pricing|gift_code|profile", "pricing|unsupported|profile"):
            query = fixture._dispatch(route, data)
            self.assertEqual(1, len(query.answers))
            self.assertTrue(query.answers[0][1].get("show_alert"))
            self.assertEqual([], query.edits)
        self.assertEqual([], reads)
        self.assertEqual([], clears)

    def test_legacy_destinations_and_non_pricing_controls_are_preserved(self):
        ns, route, _, _, _ = _runtime()
        legacy = fixture._dispatch(route, "pricing|main")
        raw_callbacks = [button.callback_data for row in ns["pricing_main_keyboard"]("vi", 123).inline_keyboard
                         for button in row]
        expected_legacy = ["menu|main_topup|pricing_main" if data == "menu|main_topup" else data
                           for data in raw_callbacks]
        self.assertEqual(expected_legacy, [button.callback_data for button in _buttons(legacy)])
        scoped = fixture._dispatch(route, "pricing|main|profile")
        original_other = [button.callback_data for button in _buttons(legacy)
                          if not button.callback_data.startswith("pricing|")]
        scoped_other = [button.callback_data for button in _buttons(scoped)
                        if not button.callback_data.startswith("pricing|") and button.callback_data != "menu|main_profile"]
        expected_scoped_other = [
            "menu|main_topup|pricing_main_profile" if data == "menu|main_topup|pricing_main"
            else "pkgcombo:home:pricing_main_profile" if data == "pkgcombo:home"
            else data
            for data in original_other
        ]
        self.assertEqual(expected_scoped_other, scoped_other)
        member = fixture._dispatch(route, "pricing|member")
        self.assertEqual("pricing|main", _back(member))
        for button in _buttons(scoped):
            self.assertLessEqual(len(button.callback_data.encode("utf-8")), 64)

    def test_public_main_menu_pricing_button_opens_hub_and_home_returns_to_main(self):
        from services.pricing_guide_content import public_hub_copy

        root_spec = importlib.util.spec_from_file_location(
            "main_menu_pricing_route_fixture",
            Path(__file__).with_name("test_admin_root_menu_callback_single_ack.py"),
        )
        root_fixture = importlib.util.module_from_spec(root_spec)
        root_spec.loader.exec_module(root_fixture)
        root_dependencies = root_fixture._main_menu_dependencies(False, [])
        root_dependencies["public_hub_copy"] = public_hub_copy
        root_namespace = root_fixture._load_functions(
            "localized_main_menu_keyboard", **root_dependencies,
        )
        main_markup = root_namespace["localized_main_menu_keyboard"](False, "vi")
        entry = next(
            button
            for row in main_markup.inline_keyboard
            for button in row
            if button.callback_data == "pricing|main"
        )
        self.assertIn("Bảng giá", entry.text)

        ns, pricing_route, menu_route, _, _ = _runtime("vi")
        ns["localized_main_menu_keyboard"] = lambda *_args: main_markup
        pricing = fixture._dispatch(pricing_route, entry.callback_data)
        self.assertEqual([((), {})], pricing.answers)
        self.assertEqual("pricing_hub_lines", pricing.edits[0][0])
        back = next(button for button in _buttons(pricing) if button.callback_data == "menu|main")

        ns.update(time=SimpleNamespace(perf_counter=lambda: 1.0),
                  logger=SimpleNamespace(info=lambda *_args, **_kwargs: None))
        returned = fixture._dispatch(menu_route, back.callback_data)
        self.assertEqual([((), {})], returned.answers)
        self.assertEqual("MAIN MENU", returned.edits[0][0])
        self.assertEqual(
            [button.callback_data for row in main_markup.inline_keyboard for button in row],
            [button.callback_data for button in _buttons(returned)],
        )

    def test_public_stale_buy_plan_callback_is_safe_and_registered(self):
        ns, _, _, _, _ = _runtime("vi")
        source_fixture = fixture.fixture
        purchase_calls = []
        ns.update(
            get_user_language=lambda _uid: "vi",
            is_admin_user=lambda _uid: False,
            pricing_copy_language=lambda locale: locale,
            start_plan_purchase=lambda *args, **kwargs: purchase_calls.append((args, kwargs)),
        )
        for name in ("pricing_plans_keyboard", "handle_buy_plan_callback"):
            exec(compile("from __future__ import annotations\n" + source_fixture._function(name),
                         "bot.py:" + name, "exec"), ns)

        routes = []
        ns.update(tg_app=SimpleNamespace(add_handler=routes.append),
                  CallbackQueryHandler=lambda callback, pattern: (callback, re.compile(pattern)))
        registration = next(
            line.strip() for line in source_fixture.SOURCE.splitlines()
            if "tg_app.add_handler(CallbackQueryHandler(handle_buy_plan_callback," in line
        )
        exec(registration, ns)
        self.assertEqual(1, len(routes))
        self.assertIs(ns["handle_buy_plan_callback"], routes[0][0])

        callback_data = "buy_plan|stale-monthly"
        query = _dispatch_immediate(routes[0], callback_data)
        text, options = query.edits[0]
        self.assertIn("Bot chưa tạo đơn.", text)
        actual_callbacks = [button.callback_data for row in options["reply_markup"].inline_keyboard
                            for button in row]
        expected = ns["pricing_plans_keyboard"]("vi")
        expected_callbacks = [button.callback_data for row in expected.inline_keyboard for button in row]
        self.assertEqual(expected_callbacks, actual_callbacks)
        self.assertTrue(all(not value.startswith("buy_plan|") for value in actual_callbacks))
        self.assertEqual([], purchase_calls)

        emitted_callback_lines = [
            line.strip() for line in source_fixture.SOURCE.splitlines()
            if "buy_plan|" in line and "CallbackQueryHandler(handle_buy_plan_callback," not in line
        ]
        self.assertEqual([], emitted_callback_lines)


if __name__ == "__main__":
    unittest.main()
