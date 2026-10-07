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
    for name in ("pricing_hub_lines", "pricing_catalog_lines", "pricing_video_lines"):
        ns[name] = lambda *args, name=name: reads.append((name, args)) or [name]
    for name in ("pricing_main_keyboard", "pricing_catalog_keyboard", "pricing_detail_keyboard",
                 "member_policy_keyboard", "handle_pricing_callback"):
        exec(compile("from __future__ import annotations\n" + fixture.fixture._function(name), "bot.py:" + name, "exec"), ns)
    routes = []
    ns.update(tg_app=SimpleNamespace(add_handler=routes.append),
              CallbackQueryHandler=lambda callback, pattern: (callback, re.compile(pattern)))
    registration = next(line.strip() for line in fixture.fixture.SOURCE.splitlines()
                        if "tg_app.add_handler(CallbackQueryHandler(handle_pricing_callback," in line)
    exec(registration, ns)
    return ns, routes[0], menu_route, reads, clears


def _buttons(query):
    return fixture._buttons(query)


def _back(query):
    return next(button.callback_data for button in _buttons(query)
                if button.text.startswith(("⬅", "🔙", "←")))


def _callback(query, action):
    return next(button.callback_data for button in _buttons(query)
                if button.callback_data.split("|")[:2] == ["pricing", action])


class AccountPricingOriginTests(unittest.TestCase):
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
        self.assertEqual([button.callback_data for row in ns["pricing_main_keyboard"]("vi", 123).inline_keyboard
                          for button in row], [button.callback_data for button in _buttons(legacy)])
        scoped = fixture._dispatch(route, "pricing|main|profile")
        original_other = [button.callback_data for button in _buttons(legacy)
                          if not button.callback_data.startswith("pricing|")]
        scoped_other = [button.callback_data for button in _buttons(scoped)
                        if not button.callback_data.startswith("pricing|") and button.callback_data != "menu|main_profile"]
        self.assertEqual(original_other, scoped_other)
        member = fixture._dispatch(route, "pricing|member")
        self.assertEqual("pricing|main", _back(member))
        for button in _buttons(scoped):
            self.assertLessEqual(len(button.callback_data.encode("utf-8")), 64)


if __name__ == "__main__":
    unittest.main()
