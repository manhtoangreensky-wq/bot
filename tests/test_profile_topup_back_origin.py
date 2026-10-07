"""Account Top-up selector Back changes only the read-only menu origin."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("account_topup_fixture", Path(__file__).with_name("test_profile_credit_guide_back_origin.py"))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def _runtime(lang="vi", admin=False):
    ns, route, cleared = fixture._runtime(lang, admin)
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


class AccountTopupOriginTests(unittest.TestCase):
    def test_account_selector_back_returns_to_account(self):
        ns, route, _, reads = _runtime()
        for lang in ("vi", "en", "zh"):
            with self.subTest(lang=lang):
                ns["get_user_language"] = lambda _uid, lang=lang: lang
                page = fixture._dispatch(route, _entry(ns, lang))
                self.assertEqual("TOPUP SELECTOR", page.edits[0][0])
                self.assertEqual("menu|main_profile", _back(page))
                account = fixture._dispatch(route, _back(page))
                self.assertEqual("ACCOUNT SCREEN", account.edits[0][0])
                self.assertEqual([((), {})], page.answers)
        self.assertEqual([(123, locale) for locale in ("vi", "en", "zh")], reads)

    def test_legacy_selector_keeps_pricing_parent_and_payment_payloads(self):
        _ns, route, _, _ = _runtime()
        page = fixture._dispatch(route, "menu|main_topup")
        self.assertEqual("pricing|main", _back(page))
        payments = [button.callback_data for button in fixture._buttons(page)
                    if button.callback_data.startswith(("payos_pkg|", "manual|"))]
        self.assertEqual(["payos_pkg|10k|123", "payos_pkg|20k|123", "payos_pkg|50k|123",
                          "payos_pkg|100k|123", "payos_pkg|200k|123", "payos_pkg|500k|123",
                          "manual|start|manual_custom|123"], payments)

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
                    page = fixture._dispatch(route, _entry(ns, locale))
                    callbacks = [button.callback_data for button in fixture._buttons(page)]
                    self.assertEqual(expected, [data for data in callbacks if data.startswith(("payos_pkg|", "manual|"))])
                    self.assertIn("menu|main", callbacks)
                    self.assertEqual("menu|main_profile", _back(page))
                    self.assertEqual((123, locale), reads[-1])
                    self.assertTrue(all(len(data.encode("utf-8")) <= 64 for data in callbacks))

    def test_invalid_selector_origin_stops_before_cleanup_read_or_render(self):
        _ns, route, cleared, reads = _runtime()
        for origin in ("", "admin", "main", "main_profile|extra"):
            query = fixture._dispatch(route, "menu|main_topup|" + origin)
            self.assertEqual(1, len(query.answers))
            self.assertTrue(query.answers[0][1].get("show_alert"))
            self.assertEqual([], query.edits)
        self.assertEqual([], cleared)
        self.assertEqual([], reads)


if __name__ == "__main__":
    unittest.main()
