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
        "time": SimpleNamespace(perf_counter=lambda: 1.0),
        "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
        "public_hub_copy": lambda _lang: Copy(),
        "safe_edit_or_send": edit,
        "clear_support_ticket_pending": lambda uid: cleared.append(uid),
        "SUPPORT_TELEGRAM_URL": "https://t.me/example",
        "public_support_consult_choices": public_support_consult_choices,
    })
    for name in ("SUPPORT_CUSTOM_BOT_DETAILS", "SUPPORT_CONSULT_DETAILS"):
        exec(fixture.fixture._assignment(name), ns)
    for name in ("ticket_customer_origin_keyboard", "support_form_origin_keyboard", "support_read_origin_keyboard", "human_support_text", "human_support_keyboard", "support_admin_contact_text",
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


def _dispatch_now(route, data):
    handler, pattern = route
    assert pattern.match(data), "emitted callback has no registered owner"
    query = fixture.fixture.Query(data)
    coroutine = handler(SimpleNamespace(callback_query=query), SimpleNamespace(user_data={}))
    try:
        coroutine.send(None)
    except StopIteration:
        return query
    coroutine.close()
    raise AssertionError("fixture callback unexpectedly yielded I/O")


class AccountSupportReadOriginTests(unittest.TestCase):
    def test_emitted_public_auto_support_page_back_and_home_restore_their_parents(self):
        ns, menu, support, cleared = _runtime()
        public_root = ns["human_support_keyboard"]("vi")
        root_callbacks = [
            button.callback_data
            for row in public_root.inline_keyboard
            for button in row
        ]
        auto_entry = next(button.callback_data for row in public_root.inline_keyboard for button in row
                          if button.callback_data == "support|cskh_auto")

        page = _dispatch_now(support, auto_entry)
        self.assertIn("support_auto_title", page.edits[0][0])
        self.assertEqual([((), {})], page.answers)
        self.assertEqual([123], cleared)
        page_buttons = fixture._buttons(page)
        back = next(button.callback_data for button in page_buttons if button.text.startswith("⬅"))
        home = next(button.callback_data for button in page_buttons if button.callback_data == "menu|main")
        self.assertEqual("support|start", back)

        returned = _dispatch_now(support, back)
        self.assertEqual([((), {})], returned.answers)
        self.assertIn("support", returned.edits[0][0].lower())
        self.assertEqual(root_callbacks, [button.callback_data for button in fixture._buttons(returned)])
        self.assertEqual([123, 123], cleared)
        main = _dispatch_now(menu, home)
        self.assertEqual([((), {})], main.answers)
        self.assertIn("MAIN MENU", main.edits[0][0])
        self.assertEqual({123}, set(cleared))

    def test_public_support_information_buttons_back_to_exact_support_root(self):
        expected_pages = {
            "admin_contact": "support_contact_title",
            "premium": "support_premium",
            "bot": "support_custom_bot",
            "consult": "support_consult",
        }
        for action, expected_heading in expected_pages.items():
            with self.subTest(action=action):
                ns, menu, support, cleared = _runtime()
                root = ns["human_support_keyboard"]("vi")
                root_callbacks = [button.callback_data for row in root.inline_keyboard for button in row]
                entry = next(callback for callback in root_callbacks if callback == f"support|{action}")

                page = _dispatch_now(support, entry)
                self.assertEqual([((), {})], page.answers)
                self.assertIn(expected_heading, page.edits[0][0])
                page_buttons = fixture._buttons(page)
                back = next(button.callback_data for button in page_buttons if button.text.startswith("⬅"))
                self.assertIn("menu|main", [button.callback_data for button in page_buttons])
                self.assertEqual("support|start", back)
                # URLs in the Admin-contact keyboard are only inspected as data; they are never opened.

                returned = _dispatch_now(support, back)
                self.assertEqual([((), {})], returned.answers)
                self.assertEqual(root_callbacks, [button.callback_data for button in fixture._buttons(returned)])
                self.assertEqual([123, 123], cleared)

                main = _dispatch_now(menu, "menu|main")
                self.assertEqual([((), {})], main.answers)
                self.assertIn("MAIN MENU", main.edits[0][0])

    def test_account_support_has_back_to_account_and_keeps_home(self):
        ns, menu, _, _ = _runtime()
        hub = _dispatch_now(menu, _entry(ns))
        callbacks = [button.callback_data for button in fixture._buttons(hub)]
        self.assertIn("menu|main_profile", callbacks)
        self.assertIn("menu|main", callbacks)

    def test_read_only_children_back_retains_account_hub(self):
        for action in ("admin_contact", "cskh_auto", "premium", "bot", "consult"):
            with self.subTest(action=action):
                ns, menu, support, _ = _runtime()
                hub = _dispatch_now(menu, _entry(ns))
                child = next(button.callback_data for button in fixture._buttons(hub)
                             if str(button.callback_data).split("|")[:2] == ["support", action])
                page = _dispatch_now(support, child)
                back = next(button.callback_data for button in fixture._buttons(page) if button.text.startswith("⬅"))
                hub_again = _dispatch_now(support, back)
                self.assertIn("menu|main_profile", [button.callback_data for button in fixture._buttons(hub_again)])

    def test_account_support_information_pages_exact_back_and_home(self):
        for action in ("admin_contact", "cskh_auto", "premium", "bot", "consult"):
            for exit_action in ("back", "home"):
                with self.subTest(action=action, exit_action=exit_action):
                    ns, menu, support, _ = _runtime()
                    hub = _dispatch_now(menu, _entry(ns))
                    hub_callbacks = [button.callback_data for button in fixture._buttons(hub)]
                    child = next(button.callback_data for button in fixture._buttons(hub)
                                 if str(button.callback_data).split("|")[:2] == ["support", action])
                    page = _dispatch_now(support, child)
                    self.assertEqual([((), {})], page.answers)
                    page_buttons = fixture._buttons(page)
                    back = next(button.callback_data for button in page_buttons if button.text.startswith("⬅"))
                    home = next(button.callback_data for button in page_buttons if button.callback_data == "menu|main")

                    if exit_action == "back":
                        returned = _dispatch_now(support, back)
                        self.assertEqual(hub_callbacks, [button.callback_data for button in fixture._buttons(returned)])
                    else:
                        returned = _dispatch_now(menu, home)
                        self.assertIn("MAIN MENU", returned.edits[0][0])

                    self.assertEqual([((), {})], returned.answers)

    def test_bot_and_consult_details_back_retain_their_read_only_parent(self):
        ns, menu, support, _ = _runtime()
        for action, child_action, heading in (("bot", "bot_type", "support_custom_bot"), ("consult", "consult_type", "support_consult")):
            hub = _dispatch_now(menu, _entry(ns))
            parent_data = next(button.callback_data for button in fixture._buttons(hub)
                               if str(button.callback_data).split("|")[:2] == ["support", action])
            parent = _dispatch_now(support, parent_data)
            for button in fixture._buttons(parent):
                if str(button.callback_data).split("|")[:2] != ["support", child_action]:
                    continue
                with self.subTest(callback=button.callback_data):
                    detail = _dispatch_now(support, button.callback_data)
                    back = next(item.callback_data for item in fixture._buttons(detail) if item.text.startswith("⬅"))
                    returned = _dispatch_now(support, back)
                    self.assertIn(heading, returned.edits[0][0])
                    hub_back = next(item.callback_data for item in fixture._buttons(returned) if item.text.startswith("⬅"))
                    hub_again = _dispatch_now(support, hub_back)
                    self.assertIn("menu|main_profile", [item.callback_data for item in fixture._buttons(hub_again)])

    def test_invalid_read_origin_stops_before_pending_cleanup_or_render(self):
        _ns, menu, support, cleared = _runtime()
        for route, data in ((menu, "menu|support|admin"), (menu, "menu|support|main_profile|extra"),
                            (support, "support|start|admin"), (support, "support|bot_type|shop|profile|extra")):
            query = _dispatch_now(route, data)
            self.assertEqual(1, len(query.answers))
            self.assertTrue(query.answers[0][1].get("show_alert"))
            self.assertEqual([], query.edits)
        self.assertEqual([], cleared)

    def test_legacy_and_account_scoped_ticket_controls_keep_their_origins(self):
        ns, menu, _, _ = _runtime()
        legacy = _dispatch_now(menu, "menu|support")
        self.assertEqual([button.callback_data for row in ns["human_support_keyboard"]().inline_keyboard for button in row],
                         [button.callback_data for button in fixture._buttons(legacy)])
        for builder, args in (("human_support_keyboard", ()), ("support_premium_keyboard", ()),
                              ("support_custom_bot_detail_keyboard", ("shop",)), ("support_consult_detail_keyboard", ("video",))):
            original = ns[builder](*args)
            scoped = ns["support_read_origin_keyboard"](original, True)
            protected = lambda markup: [button.callback_data for row in markup.inline_keyboard for button in row
                                         if str(button.callback_data).startswith("ticket|") or str(button.callback_data).split("|")[1:2] in
                                         (["ticket"], ["premium_type"], ["bot_input"], ["consult_need"], ["consult_input"])]
            expected = []
            for callback in protected(original):
                if callback == "ticket|mine|premium":
                    expected.append("ticket|mine|profile_premium")
                elif callback == "ticket|mine|support":
                    expected.append("ticket|mine|profile")
                elif callback in {"ticket|mine", "support|ticket"}:
                    expected.append(callback + "|profile")
                else:
                    expected.append(callback)
            self.assertEqual(expected, protected(scoped))
            self.assertTrue(all(len(button.callback_data.encode("utf-8")) <= 64 for row in scoped.inline_keyboard
                                for button in row if button.callback_data))


if __name__ == "__main__":
    unittest.main()
