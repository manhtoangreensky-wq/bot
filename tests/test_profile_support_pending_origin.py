"""Account Support input preserves origin through the real pending helpers."""
import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location("support_pending_fixture", Path(__file__).with_name("test_profile_support_read_back_origin.py"))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)

EXPECTED_BACK = {
    "ticket": "support|start|profile",
    "premium": "support|premium|profile",
    "bot": "support|bot_type|shop|profile",
    "consult": "support|consult_type|video|profile",
}


class Message:
    def __init__(self, text):
        self.text, self.replies = text, []
    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


def _runtime():
    ns, menu, support, _ = fixture._runtime()
    calls, now = [], {"value": 1000.0}
    ns.update(USER_PENDING={}, time=SimpleNamespace(time=lambda: now["value"]), SUPPORT_TICKET_TTL_SECONDS=900)
    source = fixture.fixture.fixture
    for name in ("support_ticket_pending_key", "support_last_ticket_key", "set_support_ticket_pending",
                 "get_support_ticket_pending", "clear_support_ticket_pending", "remember_last_support_ticket",
                 "complete_support_pending", "support_pending_back_keyboard", "support_flow_back_keyboard", "support_general_ticket_prompt",
                 "support_lead_input_text", "support_ticket_input_keyboard", "support_ticket_created_keyboard",
                 "handle_support_pending_input"):
        exec(compile("from __future__ import annotations\n" + source._function(name), "bot.py:" + name, "exec"), ns)
    async def classify(text, uid):
        calls.append(("classify", text, uid))
        return {"needs_admin": False, "priority": "normal"}
    def create(user, category, text, classification):
        calls.append(("create", user.id, category, text, dict(classification)))
        return {"id": 901, "ticket_code": "FIXTURE-901", "status": "new", "user_id": str(user.id)}, True
    async def notify(*args, **kwargs):
        calls.append(("notify", kwargs))
    ns.update({
        "classify_support_message": classify, "create_or_append_support_ticket": create,
        "notify_admin_new_support_ticket": notify,
        "support_reply_for_classification": lambda *_args: "ACK",
        "support_ticket_customer_acknowledgement": lambda *_args, **_kwargs: "ACK",
        "public_support_ticket_status_label": lambda *_args: "new",
        "support_ticket_created_text": lambda *_args: "CREATED",
    })
    return ns, menu, support, calls, now


def _select(query, action, value=None):
    return next(button.callback_data for button in fixture.fixture._buttons(query)
                if str(button.callback_data).split("|")[1:2] == [action]
                and (value is None or str(button.callback_data).split("|")[2:3] == [value]))


def _form(ns, menu, support, scenario):
    hub = fixture.fixture._dispatch(menu, fixture._entry(ns))
    if scenario == "ticket":
        return fixture.fixture._dispatch(support, _select(hub, "ticket"))
    parent = fixture.fixture._dispatch(support, _select(hub, scenario))
    if scenario == "premium":
        return fixture.fixture._dispatch(support, _select(parent, "premium_type", "personal"))
    kind, option, action = ("bot_type", "shop", "bot_input") if scenario == "bot" else ("consult_type", "video", "consult_need")
    detail = fixture.fixture._dispatch(support, _select(parent, kind, option))
    return fixture.fixture._dispatch(support, _select(detail, action, option))


class AccountSupportPendingOriginTests(unittest.TestCase):
    def test_all_four_form_emitters_persist_their_account_back_context(self):
        for scenario, expected in EXPECTED_BACK.items():
            with self.subTest(scenario=scenario):
                ns, menu, support, calls, _ = _runtime()
                prompt = _form(ns, menu, support, scenario)
                state = ns["get_support_ticket_pending"](123)
                self.assertEqual(expected, state["back_to"])
                self.assertIn(expected, [button.callback_data for button in fixture.fixture._buttons(prompt)])
                self.assertEqual([], calls)

    def test_short_ticket_input_keeps_pending_and_scoped_retry_back(self):
        ns, menu, support, calls, _ = _runtime()
        _form(ns, menu, support, "ticket")
        before = dict(ns["get_support_ticket_pending"](123))
        message = Message("x")
        update = SimpleNamespace(effective_user=SimpleNamespace(id=123), message=message)
        self.assertTrue(asyncio.run(ns["handle_support_pending_input"](update, SimpleNamespace())))
        self.assertEqual(before, ns["get_support_ticket_pending"](123))
        self.assertEqual([], calls)
        retry = message.replies[-1][1]["reply_markup"]
        back = next(button.callback_data for row in retry.inline_keyboard for button in row if button.text.startswith("⬅"))
        self.assertEqual("support|start|profile", back)
        hub = fixture.fixture._dispatch(support, back)
        self.assertIn("menu|main_profile", [button.callback_data for button in fixture.fixture._buttons(hub)])
        self.assertIsNone(ns["get_support_ticket_pending"](123))

    def test_all_four_fixture_submissions_keep_account_after_pending_completion(self):
        expected_categories = {"ticket": "general_support", "premium": "premium_lead",
                               "bot": "custom_bot_lead", "consult": "service_consulting"}
        for scenario, category in expected_categories.items():
            with self.subTest(scenario=scenario):
                ns, menu, support, calls, _ = _runtime()
                _form(ns, menu, support, scenario)
                before = dict(ns["get_support_ticket_pending"](123))
                message = Message("Fixture customer input")
                user = SimpleNamespace(id=123, username="fixture", first_name="Fixture")
                update = SimpleNamespace(effective_user=user, message=message)
                self.assertTrue(asyncio.run(ns["handle_support_pending_input"](update, SimpleNamespace())))
                self.assertIsNone(ns["get_support_ticket_pending"](123))
                created = [call for call in calls if call[0] == "create"]
                self.assertEqual(1, len(created))
                self.assertEqual((123, category), created[0][1:3])
                expected_text = "Fixture customer input" if scenario == "ticket" else before["selected_option"] + "\nFixture customer input"
                self.assertEqual(expected_text, created[0][3])
                self.assertEqual(0 if scenario == "consult" else 1, len([call for call in calls if call[0] == "notify"]))
                markup = message.replies[-1][1]["reply_markup"]
                back = next(button.callback_data for row in markup.inline_keyboard for button in row
                            if str(button.callback_data).startswith("support|start"))
                self.assertEqual("support|start|profile", back)
                hub = fixture.fixture._dispatch(support, back)
                self.assertIn("menu|main_profile", [button.callback_data for button in fixture.fixture._buttons(hub)])

    def test_malformed_scoped_forms_do_not_create_pending_or_call_business_seams(self):
        ns, _, support, calls, _ = _runtime()
        for data in ("support|ticket|admin", "support|premium_type|personal|profile|extra",
                     "support|bot_input|shop|admin", "support|consult_need|video|bad|profile"):
            query = fixture.fixture._dispatch(support, data)
            self.assertEqual(1, len(query.answers))
            self.assertTrue(query.answers[0][1].get("show_alert"))
            self.assertEqual([], query.edits)
        self.assertIsNone(ns["get_support_ticket_pending"](123))
        self.assertEqual([], calls)

    def test_expired_pending_is_not_consumed_and_legacy_ticket_stays_legacy(self):
        ns, menu, support, calls, now = _runtime()
        _form(ns, menu, support, "ticket")
        now["value"] += 901
        message = Message("Expired fixture input")
        update = SimpleNamespace(effective_user=SimpleNamespace(id=123), message=message)
        self.assertFalse(asyncio.run(ns["handle_support_pending_input"](update, SimpleNamespace())))
        self.assertEqual([], message.replies)
        self.assertEqual([], calls)
        prompt = fixture.fixture._dispatch(support, "support|ticket")
        self.assertEqual("support|start", ns["get_support_ticket_pending"](123)["back_to"])
        self.assertIn("support|start", [button.callback_data for button in fixture.fixture._buttons(prompt)])


if __name__ == "__main__":
    unittest.main()
