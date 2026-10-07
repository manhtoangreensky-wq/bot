"""Account Support read-only screens preserve their opening Account menu."""
import asyncio
import html
import importlib.util
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from services.pricing_guide_content import public_support_consult_choices

spec = importlib.util.spec_from_file_location("account_support_fixture", Path(__file__).with_name("test_profile_credit_guide_back_origin.py"))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class Button:
    def __init__(self, text, callback_data=None, url=None):
        self.text, self.callback_data, self.url = text, callback_data, url


class Copy(dict):
    def __missing__(self, key):
        return key


def _runtime():
    ns, menu, _ = fixture._runtime()
    cleared = []
    async def edit(query, text, **kwargs):
        query.edits.append((text, kwargs))
    ns.update({
        "InlineKeyboardButton": Button, "html": html,
        "public_hub_copy": lambda _lang: Copy(),
        "safe_edit_or_send": edit,
        "clear_support_ticket_pending": lambda uid: cleared.append(uid),
        "SUPPORT_TELEGRAM_URL": "https://t.me/example",
        "public_support_consult_choices": public_support_consult_choices,
    })
    for name in ("SUPPORT_CUSTOM_BOT_DETAILS", "SUPPORT_CONSULT_DETAILS"):
        exec(fixture.fixture._assignment(name), ns)
    for name in ("support_form_origin_keyboard", "support_read_origin_keyboard", "human_support_text", "human_support_keyboard", "support_admin_contact_text",
                 "support_admin_contact_keyboard", "support_cskh_auto_text", "support_cskh_auto_keyboard",
                 "support_premium_text", "support_premium_keyboard", "support_custom_bot_text",
                 "support_custom_bot_keyboard", "support_consult_keyboard", "support_custom_bot_public_label",
                 "support_consult_public_label", "support_consult_choice_labels", "support_custom_bot_detail_text",
                 "support_custom_bot_detail_keyboard", "support_consult_detail_text", "support_consult_detail_keyboard",
                 "handle_human_support_callback"):
        exec(compile("from __future__ import annotations\n" + fixture.fixture._function(name), "bot.py:" + name, "exec"), ns)
    routes = []
    ns.update(tg_app=SimpleNamespace(add_handler=routes.append),
              CallbackQueryHandler=lambda callback, pattern: (callback, re.compile(pattern)))
    registration = next(line.strip() for line in fixture.fixture.SOURCE.splitlines()
                        if "tg_app.add_handler(CallbackQueryHandler(handle_human_support_callback," in line)
    exec(registration, ns)
    return ns, menu, routes[0], cleared


def _entry(ns):
    return next(button.callback_data for row in ns["main_profile_keyboard"]().inline_keyboard
                for button in row if button.callback_data.startswith("menu|support"))


class AccountSupportReadOriginTests(unittest.TestCase):
    def test_account_support_has_back_to_account_and_keeps_home(self):
        ns, menu, _, _ = _runtime()
        hub = fixture._dispatch(menu, _entry(ns))
        callbacks = [button.callback_data for button in fixture._buttons(hub)]
        self.assertIn("menu|main_profile", callbacks)
        self.assertIn("menu|main", callbacks)

    def test_read_only_children_back_retains_account_hub(self):
        for action in ("admin_contact", "cskh_auto", "premium", "bot", "consult"):
            with self.subTest(action=action):
                ns, menu, support, _ = _runtime()
                hub = fixture._dispatch(menu, _entry(ns))
                child = next(button.callback_data for button in fixture._buttons(hub)
                             if str(button.callback_data).split("|")[:2] == ["support", action])
                page = fixture._dispatch(support, child)
                back = next(button.callback_data for button in fixture._buttons(page) if button.text.startswith("⬅"))
                hub_again = fixture._dispatch(support, back)
                self.assertIn("menu|main_profile", [button.callback_data for button in fixture._buttons(hub_again)])

    def test_bot_and_consult_details_back_retain_their_read_only_parent(self):
        ns, menu, support, _ = _runtime()
        for action, child_action, heading in (("bot", "bot_type", "support_custom_bot"), ("consult", "consult_type", "support_consult")):
            hub = fixture._dispatch(menu, _entry(ns))
            parent_data = next(button.callback_data for button in fixture._buttons(hub)
                               if str(button.callback_data).split("|")[:2] == ["support", action])
            parent = fixture._dispatch(support, parent_data)
            for button in fixture._buttons(parent):
                if str(button.callback_data).split("|")[:2] != ["support", child_action]:
                    continue
                with self.subTest(callback=button.callback_data):
                    detail = fixture._dispatch(support, button.callback_data)
                    back = next(item.callback_data for item in fixture._buttons(detail) if item.text.startswith("⬅"))
                    returned = fixture._dispatch(support, back)
                    self.assertIn(heading, returned.edits[0][0])
                    hub_back = next(item.callback_data for item in fixture._buttons(returned) if item.text.startswith("⬅"))
                    hub_again = fixture._dispatch(support, hub_back)
                    self.assertIn("menu|main_profile", [item.callback_data for item in fixture._buttons(hub_again)])

    def test_invalid_read_origin_stops_before_pending_cleanup_or_render(self):
        _ns, menu, support, cleared = _runtime()
        for route, data in ((menu, "menu|support|admin"), (menu, "menu|support|main_profile|extra"),
                            (support, "support|start|admin"), (support, "support|bot_type|shop|profile|extra")):
            query = fixture._dispatch(route, data)
            self.assertEqual(1, len(query.answers))
            self.assertTrue(query.answers[0][1].get("show_alert"))
            self.assertEqual([], query.edits)
        self.assertEqual([], cleared)

    def test_legacy_and_pending_form_ticket_controls_are_unchanged(self):
        ns, menu, _, _ = _runtime()
        legacy = fixture._dispatch(menu, "menu|support")
        self.assertEqual([button.callback_data for row in ns["human_support_keyboard"]().inline_keyboard for button in row],
                         [button.callback_data for button in fixture._buttons(legacy)])
        for builder, args in (("human_support_keyboard", ()), ("support_premium_keyboard", ()),
                              ("support_custom_bot_detail_keyboard", ("shop",)), ("support_consult_detail_keyboard", ("video",))):
            original = ns[builder](*args)
            scoped = ns["support_read_origin_keyboard"](original, True)
            protected = lambda markup: [button.callback_data for row in markup.inline_keyboard for button in row
                                         if str(button.callback_data).startswith("ticket|") or str(button.callback_data).split("|")[1:2] in
                                         (["ticket"], ["premium_type"], ["bot_input"], ["consult_need"], ["consult_input"])]
            self.assertEqual(protected(original), protected(scoped))
            self.assertTrue(all(len(button.callback_data.encode("utf-8")) <= 64 for row in scoped.inline_keyboard
                                for button in row if button.callback_data))


if __name__ == "__main__":
    unittest.main()
