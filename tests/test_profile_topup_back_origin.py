"""Account Top-up selector Back changes only the read-only menu origin."""
import importlib.util
from pathlib import Path
import re
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location("account_topup_fixture", Path(__file__).with_name("test_profile_credit_guide_back_origin.py"))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def _runtime(lang="vi", admin=False):
    ns, route, cleared = fixture._runtime(lang, admin)
    ns.setdefault("_local_video_planning_clear_pending", lambda _context: None)
    reads = []
    original_copy = ns["public_hub_copy"]
    ns.update({
        "public_hub_copy": lambda locale: {**original_copy(locale), "manual_topup": "Manual"},
        "public_page_title": lambda page, _locale: page,
        "menu_text_main_topup_i18n": lambda locale, uid: reads.append((uid, locale)) or "TOPUP SELECTOR",
    })
    for name in ("payos_package_callback_data", "manual_package_callback_data", "main_topup_keyboard"):
        exec(compile("from __future__ import annotations\n" + fixture.fixture._function(name), "bot.py:" + name, "exec"), ns)
    return ns, route, cleared, reads


def _entry(ns, lang="vi"):
    return next(button.callback_data for row in ns["main_profile_keyboard"](lang).inline_keyboard
                for button in row if button.callback_data.startswith("menu|main_topup"))


def _back(page):
    return next(button.callback_data for button in fixture._buttons(page) if button.text.startswith(("🔙", "⬅")))


def _run_no_io(awaitable):
    try:
        awaitable.send(None)
    except StopIteration as completed:
        return completed.value
    raise AssertionError("fixture callback unexpectedly yielded I/O")


def _dispatch_menu(route, data):
    handler, pattern = route
    assert pattern.match(data), "emitted callback has no registered owner"
    query = fixture.fixture.Query(data)
    _run_no_io(handler(SimpleNamespace(callback_query=query), SimpleNamespace(user_data={})))
    return query


class AccountTopupOriginTests(unittest.TestCase):
    def test_account_selector_back_returns_to_account(self):
        ns, route, _, reads = _runtime()
        for lang in ("vi", "en", "zh"):
            with self.subTest(lang=lang):
                ns["get_user_language"] = lambda _uid, lang=lang: lang
                page = _dispatch_menu(route, _entry(ns, lang))
                self.assertEqual("TOPUP SELECTOR", page.edits[0][0])
                self.assertEqual("menu|main_profile", _back(page))
                account = _dispatch_menu(route, _back(page))
                self.assertEqual("ACCOUNT SCREEN", account.edits[0][0])
                self.assertEqual([((), {})], page.answers)
        self.assertEqual([(123, locale) for locale in ("vi", "en", "zh")], reads)

    def test_legacy_selector_keeps_pricing_parent_and_payment_payloads(self):
        _ns, route, _, _ = _runtime()
        page = _dispatch_menu(route, "menu|main_topup")
        self.assertEqual("pricing|main", _back(page))
        payments = [button.callback_data for button in fixture._buttons(page)
                    if button.callback_data.startswith(("payos_pkg|", "manual|"))]
        self.assertEqual(["payos_pkg|10k|123", "payos_pkg|20k|123", "payos_pkg|50k|123",
                          "payos_pkg|100k|123", "payos_pkg|200k|123", "payos_pkg|500k|123",
                          "manual|start|manual_custom|123"], payments)

    def test_emitted_manual_topup_entry_dispatches_to_registered_handler_without_payment_side_effects(self):
        ns, _, _, _ = _runtime()
        events = []

        class Query:
            def __init__(self, callback):
                self.data = callback
                self.from_user = SimpleNamespace(id=123, first_name="Fixture")
                self.answers = []
                self.edits = []

            async def answer(self, *args, **kwargs):
                events.append("ack")
                self.answers.append((args, kwargs))

            async def edit_message_text(self, text, **kwargs):
                events.append(("render", text))
                self.edits.append((text, kwargs))

        def forbidden(*_args, **_kwargs):
            raise AssertionError("manual top-up entry must not create/order/pay/send")

        ns.update({
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "PAYMENT_PACKAGES": {},
            "get_user_language": lambda _uid: "vi",
            "public_hub_copy": lambda _lang: {"common_failed": "failed"},
            "public_account_flow_copy": lambda _lang: {},
            "manual_payment_menu_text": lambda _uid, _lang: "MANUAL PAYMENT MENU",
            "manual_payment_menu_keyboard": lambda _uid, _lang: "MANUAL PAYMENT KEYBOARD",
            "set_manual_bill_state": lambda uid, **values: events.append(("fixture_state", uid, values)),
            "create_order": forbidden,
            "send_manual_payment_qr": forbidden,
            "cmd_duyet": forbidden,
            "cmd_tuchoi": forbidden,
        })
        exec(
            compile(
                "from __future__ import annotations\n" + fixture.fixture._function("handle_manual_package_choice"),
                "bot.py:handle_manual_package_choice",
                "exec",
            ),
            ns,
        )

        registrations = []
        ns.update(
            tg_app=SimpleNamespace(add_handler=registrations.append),
            CallbackQueryHandler=lambda callback, pattern: SimpleNamespace(
                callback=callback,
                pattern=re.compile(pattern),
            ),
        )
        registration = next(
            line.strip()
            for line in fixture.fixture.SOURCE.splitlines()
            if "tg_app.add_handler(CallbackQueryHandler(handle_manual_package_choice," in line
        )
        exec(registration, ns)

        markup = ns["main_topup_keyboard"]("vi", 123)
        entry = next(
            button
            for row in markup.inline_keyboard
            for button in row
            if button.text == "🏦 Nạp thủ công"
        )
        route = next(handler for handler in registrations if handler.pattern.match(entry.callback_data))
        self.assertIs(route.callback, ns["handle_manual_package_choice"])
        self.assertEqual("manual|start|manual_custom|123", entry.callback_data)

        query = Query(entry.callback_data)
        _run_no_io(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace(args=[])))

        self.assertEqual([((), {})], query.answers)
        self.assertEqual(
            [("MANUAL PAYMENT MENU", {
                "parse_mode": "HTML",
                "reply_markup": "MANUAL PAYMENT KEYBOARD",
            })],
            query.edits,
        )
        self.assertEqual(
            ["ack", ("fixture_state", 123, {"order_code": "MANUAL"}), ("render", "MANUAL PAYMENT MENU")],
            events,
        )

    def test_all_locales_and_roles_preserve_amount_callbacks_home_and_actor(self):
        from services.pricing_guide_content import PUBLIC_COPY_LOCALES
        ns, route, _, reads = _runtime()
        expected = ["payos_pkg|10k|123", "payos_pkg|20k|123", "payos_pkg|50k|123",
                    "payos_pkg|100k|123", "payos_pkg|200k|123", "payos_pkg|500k|123", "manual|start|manual_custom|123"]
        for admin in (False, True):
            ns["is_admin_user"] = lambda _uid, admin=admin: admin
            for locale in sorted(PUBLIC_COPY_LOCALES):
                with self.subTest(admin=admin, locale=locale):
                    ns["get_user_language"] = lambda _uid, locale=locale: locale
                    page = _dispatch_menu(route, _entry(ns, locale))
                    callbacks = [button.callback_data for button in fixture._buttons(page)]
                    self.assertEqual(expected, [data for data in callbacks if data.startswith(("payos_pkg|", "manual|"))])
                    self.assertIn("menu|main", callbacks)
                    self.assertEqual("menu|main_profile", _back(page))
                    self.assertEqual((123, locale), reads[-1])
                    self.assertTrue(all(len(data.encode("utf-8")) <= 64 for data in callbacks))

    def test_invalid_selector_origin_stops_before_cleanup_read_or_render(self):
        _ns, route, cleared, reads = _runtime()
        for origin in ("", "admin", "main", "main_profile|extra", "pricing_unknown",
                       "pricing_main|profile", "pricing_promotions_profile|extra", "pricing_download_pricing"):
            query = _dispatch_menu(route, "menu|main_topup|" + origin)
            self.assertEqual(1, len(query.answers))
            self.assertTrue(query.answers[0][1].get("show_alert"))
            self.assertEqual([], query.edits)
        self.assertEqual([], cleared)
        self.assertEqual([], reads)


if __name__ == "__main__":
    unittest.main()
