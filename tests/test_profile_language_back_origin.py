"""Account language picker retains Account on Back and language selection."""
import asyncio
import importlib.util
from pathlib import Path
import re
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location("account_language_fixture", Path(__file__).with_name("test_profile_credit_guide_back_origin.py"))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def _runtime():
    ns, menu, _ = fixture._runtime()
    effects, stored = [], {"lang": "vi"}
    original_copy = ns["public_hub_copy"]
    ns["public_hub_copy"] = lambda lang: {**original_copy(lang), "back": "Back", "language_picker_title": "Language", "language_picker_intro": "Choose"}
    ns.update({
        "asyncio": asyncio,
        "_TelegramInlineKeyboardMarkup": ns["InlineKeyboardMarkup"],
        "get_user_language": lambda _uid: stored["lang"],
        "is_admin_user": lambda _uid: False,
        "user_selected_vietnamese_initially": lambda _uid: False,
        "record_usage_event": lambda *args, **kwargs: effects.append(("usage", args, kwargs)),
        "localized_start_menu_text": lambda _uid, _lang: "MAIN SCREEN",
        "localized_main_menu_keyboard": lambda *_args: ns["InlineKeyboardMarkup"]([]),
    })
    def set_language(uid, lang):
        effects.append(("set", uid, lang)); stored["lang"] = lang
        return lang
    ns["set_user_language"] = set_language
    for name in ("USER_LANGUAGE_LABELS", "USER_LANGUAGE_FLAGS"):
        exec(fixture.fixture._assignment(name), ns)
    order = re.search(r"(?ms)^USER_LANGUAGE_ORDER = \(.*?^\)", fixture.fixture.SOURCE).group(0)
    exec(order, ns)
    for name in ("normalize_user_language", "language_choice_text", "language_choice_keyboard", "handle_language_callback"):
        exec(compile("from __future__ import annotations\n" + fixture.fixture._function(name), "bot.py:" + name, "exec"), ns)
    routes = []
    ns.update(tg_app=SimpleNamespace(add_handler=routes.append),
              CallbackQueryHandler=lambda callback, pattern: (callback, re.compile(pattern)))
    registration = next(line.strip() for line in fixture.fixture.SOURCE.splitlines()
                        if "tg_app.add_handler(CallbackQueryHandler(handle_language_callback," in line)
    exec(registration, ns)
    return ns, routes[0], menu, effects, stored


def _entry(ns):
    return next(button.callback_data for row in ns["main_profile_keyboard"]().inline_keyboard
                for button in row if button.callback_data.startswith("back_lang"))


class AccountLanguageOriginTests(unittest.TestCase):
    def test_account_picker_back_returns_to_account_without_preference_write(self):
        ns, route, _, effects, _ = _runtime()
        picker = fixture._dispatch(route, _entry(ns))
        back = next(button.callback_data for button in fixture._buttons(picker) if button.text.startswith("⬅"))
        returned = fixture._dispatch(route, back)
        self.assertEqual("ACCOUNT SCREEN", returned.edits[0][0])
        self.assertEqual([], effects)

    def test_account_picker_selection_updates_once_and_returns_to_account(self):
        ns, route, _, effects, stored = _runtime()
        picker = fixture._dispatch(route, _entry(ns))
        selected = next(button.callback_data for button in fixture._buttons(picker)
                        if button.callback_data.split("|")[:2] == ["lang", "en"])
        returned = fixture._dispatch(route, selected)
        self.assertEqual("ACCOUNT SCREEN", returned.edits[0][0])
        self.assertEqual("en", stored["lang"])
        self.assertEqual([("set", 123, "en")], [event for event in effects if event[0] == "set"])
        self.assertEqual(1, len([event for event in effects if event[0] == "usage"]))

    def test_all_emitted_locales_preserve_context_payload_and_single_update(self):
        ns, route, _, effects, stored = _runtime()
        picker = fixture._dispatch(route, _entry(ns))
        choices = [button for button in fixture._buttons(picker) if button.callback_data.startswith("lang|")]
        self.assertEqual(set(ns["USER_LANGUAGE_ORDER"]), {button.callback_data.split("|")[1] for button in choices})
        self.assertIn("menu|main", [button.callback_data for button in fixture._buttons(picker)])
        for button in choices:
            with self.subTest(locale=button.callback_data):
                before = len(effects)
                returned = fixture._dispatch(route, button.callback_data)
                self.assertEqual(button.callback_data, returned.data)
                self.assertLessEqual(len(button.callback_data.encode("utf-8")), 64)
                self.assertEqual("ACCOUNT SCREEN", returned.edits[0][0])
                self.assertEqual(button.callback_data.split("|")[1], stored["lang"])
                self.assertEqual(["set", "usage"], [event[0] for event in effects[before:]])
                self.assertEqual([((), {})], returned.answers)

    def test_invalid_scoped_controls_alert_without_preference_or_event_write(self):
        _ns, route, _, effects, _ = _runtime()
        for data in ("back_lang|admin", "lang_back|profile|extra", "lang|en|admin", "lang|en|profile|extra", "lang|xx|profile"):
            query = fixture._dispatch(route, data)
            self.assertEqual(1, len(query.answers))
            self.assertTrue(query.answers[0][1].get("show_alert"))
            self.assertEqual([], query.edits)
        self.assertEqual([], effects)

    def test_legacy_picker_and_selection_keep_main_destination(self):
        _ns, route, _, effects, _ = _runtime()
        picker = fixture._dispatch(route, "back_lang")
        self.assertTrue(all("|profile" not in str(button.callback_data) for button in fixture._buttons(picker)))
        back = fixture._dispatch(route, "lang_back")
        self.assertEqual("MAIN SCREEN", back.edits[0][0])
        self.assertEqual([], effects)
        selected = fixture._dispatch(route, "lang|en")
        self.assertEqual("MAIN SCREEN", selected.edits[0][0])

    def test_old_more_language_control_keeps_account_context_when_scoped(self):
        _ns, route, _, effects, _ = _runtime()
        picker = fixture._dispatch(route, "lang_more|profile")
        back = next(button.callback_data for button in fixture._buttons(picker) if button.text.startswith("⬅"))
        returned = fixture._dispatch(route, back)
        self.assertEqual("ACCOUNT SCREEN", returned.edits[0][0])
        self.assertEqual([], effects)


if __name__ == "__main__":
    unittest.main()
