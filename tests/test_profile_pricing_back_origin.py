"""Account-origin pricing screens keep their read-only navigation ancestry."""
import asyncio
import html
import importlib.util
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


class AccountPricingOriginTests(unittest.TestCase):
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

    def test_invalid_origin_stops_before_cleanup_data_or_render(self):
        _ns, route, _, reads, clears = _runtime()
        for data in ("pricing|main|", "pricing|main|admin", "pricing|main|profile|extra",
                     "pricing|video|profile_catalog", "pricing|gift_code|profile", "pricing|unsupported|profile"):
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
        expected_scoped_other = ["menu|main_topup|pricing_main_profile" if data == "menu|main_topup|pricing_main" else data
                                 for data in original_other]
        self.assertEqual(expected_scoped_other, scoped_other)
        member = fixture._dispatch(route, "pricing|member")
        self.assertEqual("pricing|main", _back(member))
        for button in _buttons(scoped):
            self.assertLessEqual(len(button.callback_data.encode("utf-8")), 64)


if __name__ == "__main__":
    unittest.main()
