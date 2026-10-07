"""Account -> credit guide -> Back returns to Account through registered UI."""
import asyncio
import importlib.util
from pathlib import Path
import re
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location("profile_guide_fixture", Path(__file__).with_name("test_admin_billing_guide_labels.py"))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def _runtime(lang="vi", admin=False):
    ns, cleared = fixture._load(admin)
    fields = ("profile_topup", "profile_pricing", "profile_packages", "profile_membership",
              "profile_xu_guide", "support", "profile_referral_link", "profile_referral_stats",
              "profile_referral_policy", "profile_change_language", "main_menu", "account_label")
    ns.update({
        "get_user_language": lambda _uid: lang,
        "public_hub_copy": lambda _lang: {key: key for key in fields},
        "public_pricing_locale": lambda value: value,
        "GUIDE_SECTION_ALIASES": {"credits": "credits"},
        "guide_section_text_i18n": lambda section, _lang: "GUIDE: " + section,
        "menu_text_main_profile_i18n": lambda *_args: "ACCOUNT SCREEN",
        "ui_text": lambda _lang, _key: "🔙 Back",
    })
    for name in ("main_profile_keyboard", "normalize_guide_section_key", "guide_keyboard"):
        exec(compile("from __future__ import annotations\n" + fixture._function(name), "bot.py:" + name, "exec"), ns)
    routes = []
    ns.update(tg_app=SimpleNamespace(add_handler=routes.append),
              CallbackQueryHandler=lambda callback, pattern: (callback, re.compile(pattern)))
    registration = next(line.strip() for line in fixture.SOURCE.splitlines()
                        if "tg_app.add_handler(CallbackQueryHandler(handle_menu_callback," in line)
    exec(registration, ns)
    return ns, routes[0], cleared


def _dispatch(route, data):
    handler, pattern = route
    assert pattern.match(data), "emitted callback has no registered owner"
    query = fixture.Query(data)
    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace(user_data={})))
    return query


def _buttons(query):
    return [button for row in query.edits[0][1]["reply_markup"].inline_keyboard for button in row]


class ProfileCreditGuideOriginTests(unittest.TestCase):
    def test_emitted_account_credit_guide_returns_to_account(self):
        for lang in ("vi", "en"):
            with self.subTest(lang=lang):
                ns, route, _ = _runtime(lang)
                guide = next(button for row in ns["main_profile_keyboard"](lang).inline_keyboard
                             for button in row if button.callback_data.startswith("menu|guide_credits"))
                page = _dispatch(route, guide.callback_data)
                self.assertEqual("GUIDE: credits", page.edits[0][0])
                back = next(button for button in _buttons(page) if button.text.startswith("🔙"))
                self.assertEqual("menu|main_profile", back.callback_data)
                returned = _dispatch(route, back.callback_data)
                self.assertEqual("ACCOUNT SCREEN", returned.edits[0][0])
                self.assertEqual([((), {})], page.answers)
                self.assertEqual([((), {})], returned.answers)

    def test_legacy_credit_guide_keeps_guide_index_parent(self):
        _ns, route, _ = _runtime()
        page = _dispatch(route, "menu|guide_credits")
        back = next(button for button in _buttons(page) if button.text.startswith("🔙"))
        self.assertEqual("menu|main_guide", back.callback_data)

    def test_invalid_credit_guide_origin_stops_before_cleanup_or_render(self):
        _ns, route, cleared = _runtime()
        for origin in ("", "main", "admin", "main_profile|extra", " main_profile"):
            query = _dispatch(route, "menu|guide_credits|" + origin)
            self.assertEqual(1, len(query.answers))
            self.assertTrue(query.answers[0][1].get("show_alert"))
            self.assertEqual([], query.edits)
        self.assertEqual([], cleared)


if __name__ == "__main__":
    unittest.main()
