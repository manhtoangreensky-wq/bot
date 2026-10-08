"""The Admin Support marketing planner must retain its opening menu as Back."""
import asyncio
import importlib.util
import re
import unittest
from pathlib import Path
from types import SimpleNamespace


_spec = importlib.util.spec_from_file_location(
    "marketing_support_menu_fixture",
    Path(__file__).with_name("test_admin_billing_guide_labels.py"),
)
fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixture)


def _runtime():
    pending = {}
    ns = {
        "InlineKeyboardButton": fixture.Button,
        "InlineKeyboardMarkup": fixture.Markup,
        "is_admin_user": lambda _uid: True,
        "VIDEO_WAITING_LOCK_ENABLED": False,
        "marketing_menu_text": lambda: "INERT MARKETING MENU",
        "marketing_suggestions_text": lambda _state: "INERT MARKETING SUGGESTIONS",
        "marketing_suggestions": lambda _state: ["INERT SUGGESTION"],
        "marketing_waiting_text": lambda: "INERT PLANNING WAIT",
        "marketing_plan_text": lambda _state: "INERT MARKETING PLAN",
        "marketing_followup_text": lambda _action, _state: "INERT MARKETING FOLLOWUP",
        "_short_pending_text": lambda text, limit: text[:limit],
    }
    source = "from __future__ import annotations\n\n" + "\n\n".join(
        [
            fixture._assignment("ADMIN_CONTROL_MODULES"),
            fixture._function("admin_module_keyboard"),
            fixture._function("video_v6_keyboard"),
            fixture._function("marketing_menu_keyboard"),
            fixture._function("marketing_suggestions_keyboard"),
            fixture._function("marketing_result_keyboard"),
            fixture._function("handle_marketing_callback"),
            fixture._function("handle_marketing_pending_text"),
        ]
    )
    exec(compile(source, "bot.py:admin-marketing-support-navigation", "exec"), ns)

    def build_keyboard(items, nav_back=None, nav_main=True, lang="vi"):
        rows = [[fixture.Button(label, callback) for label, callback in items]]
        if nav_back:
            rows.append([fixture.Button(*nav_back)])
        if nav_main:
            rows.append([fixture.Button("🏠 Menu chính", "menu|main")])
        return fixture.Markup(rows)

    async def capture_edit(query, text, **kwargs):
        query.edits.append((text, kwargs))

    ns.update(
        build_2col_keyboard=build_keyboard,
        safe_edit_or_send=capture_edit,
        safe_edit_or_send_long_html=capture_edit,
        get_marketing_pending=lambda uid: dict(pending.get(uid) or {}),
        clear_marketing_pending=lambda uid: pending.pop(uid, None) is not None,
        set_marketing_pending=lambda uid, step, **values: pending.setdefault(uid, {}).update(
            values, type="marketing_auto", step=step
        ) or pending[uid],
    )
    registered = []
    ns["tg_app"] = SimpleNamespace(add_handler=registered.append)
    ns["CallbackQueryHandler"] = lambda callback, pattern: SimpleNamespace(
        callback=callback, pattern=re.compile(pattern)
    )
    registration = next(
        line.strip()
        for line in fixture.SOURCE.splitlines()
        if "tg_app.add_handler(CallbackQueryHandler(handle_marketing_callback," in line
    )
    exec(registration, ns)
    ns["registered_marketing_route"] = registered[0]
    return ns


def _controls(query):
    return [button for row in query.edits[-1][1]["reply_markup"].inline_keyboard for button in row]


def _dispatch(ns, callback, context):
    route = ns["registered_marketing_route"]
    if not route.pattern.match(callback):
        raise AssertionError("callback is not handled by the registered Marketing route")
    query = fixture.Query(callback)
    asyncio.run(route.callback(
        SimpleNamespace(callback_query=query), context,
    ))
    return query


class AdminMarketingSupportBackOriginTests(unittest.TestCase):
    def test_support_entry_and_nested_return_keep_support_as_back_parent(self):
        self.assertIn(
            'tg_app.add_handler(CallbackQueryHandler(handle_marketing_callback, pattern=r"^marketing\\|"))',
            fixture.SOURCE,
        )
        ns = _runtime()
        context = SimpleNamespace(user_data={})
        support = ns["admin_module_keyboard"]("support")
        entry = next(
            button for row in support.inline_keyboard for button in row
            if button.text == "📣 Marketing tự động"
        )
        self.assertEqual("marketing|start|admin_support", entry.callback_data)

        opened = _dispatch(ns, entry.callback_data, context)
        back = next(button for button in _controls(opened) if button.text.startswith("⬅"))
        self.assertEqual("menu|admin_support", back.callback_data)

        kind = next(button for button in _controls(opened) if button.callback_data.startswith("marketing|kind|"))
        suggestions = _dispatch(ns, kind.callback_data, context)
        return_to_menu = next(button for button in _controls(suggestions) if button.text.startswith("⬅"))
        self.assertEqual("marketing|start", return_to_menu.callback_data)

        returned = _dispatch(ns, return_to_menu.callback_data, context)
        back_to_support = next(button for button in _controls(returned) if button.text.startswith("⬅"))
        self.assertEqual("menu|admin_support", back_to_support.callback_data)
        self.assertEqual("INERT MARKETING MENU", returned.edits[0][0])
        self.assertEqual([((), {})], opened.answers)
        self.assertEqual([((), {})], suggestions.answers)
        self.assertEqual([((), {})], returned.answers)

    def test_unscoped_legacy_start_keeps_admin_root_back(self):
        ns = _runtime()
        context = SimpleNamespace(user_data={})
        opened = _dispatch(ns, "marketing|start", context)
        back = next(button for button in _controls(opened) if button.text.startswith("⬅"))
        self.assertEqual("menu|admin", back.callback_data)

    def test_selected_plan_back_returns_to_suggestions_not_admin_root(self):
        ns = _runtime()
        context = SimpleNamespace(user_data={})
        support = ns["admin_module_keyboard"]("support")
        entry = next(
            button for row in support.inline_keyboard for button in row
            if button.text == "📣 Marketing tự động"
        )
        menu = _dispatch(ns, entry.callback_data, context)
        kind = next(button for button in _controls(menu) if button.callback_data == "marketing|kind|physical")
        suggestions = _dispatch(ns, kind.callback_data, context)
        choice = next(button for button in _controls(suggestions) if button.callback_data == "marketing|choice|1")

        plan = _dispatch(ns, choice.callback_data, context)
        self.assertEqual("INERT MARKETING PLAN", plan.edits[-1][0])
        followup_actions = {"select_video", "caption", "schedule", "cskh", "kpi", "save"}
        for control in _controls(plan):
            if control.callback_data.split("|")[1] not in followup_actions:
                continue
            with self.subTest(followup=control.callback_data):
                followup = _dispatch(ns, control.callback_data, context)
                followup_back = next(button for button in _controls(followup) if button.text.startswith("⬅"))
                self.assertEqual("marketing|back_suggestions", followup_back.callback_data)
                self.assertEqual([((), {})], followup.answers)
        back = next(button for button in _controls(plan) if button.text.startswith("⬅"))
        self.assertEqual("marketing|back_suggestions", back.callback_data)

        returned_suggestions = _dispatch(ns, back.callback_data, context)
        self.assertEqual("INERT MARKETING SUGGESTIONS", returned_suggestions.edits[0][0])
        back_to_landing = next(
            button for button in _controls(returned_suggestions)
            if button.text.startswith("⬅")
        )
        self.assertEqual("marketing|start", back_to_landing.callback_data)
        landing = _dispatch(ns, back_to_landing.callback_data, context)
        back_to_support = next(button for button in _controls(landing) if button.text.startswith("⬅"))
        self.assertEqual("menu|admin_support", back_to_support.callback_data)

    def test_custom_brief_result_retains_support_or_legacy_parent(self):
        for entry, expected_back in (
            ("marketing|start|admin_support", "marketing|back_suggestions"),
            ("marketing|start", "menu|admin"),
        ):
            with self.subTest(entry=entry):
                ns = _runtime()
                context = SimpleNamespace(user_data={})
                menu = _dispatch(ns, entry, context)
                kind = next(button for button in _controls(menu) if button.callback_data == "marketing|kind|physical")
                suggestions = _dispatch(ns, kind.callback_data, context)
                brief = next(button for button in _controls(suggestions) if button.callback_data == "marketing|brief_custom")
                prompt = _dispatch(ns, brief.callback_data, context)
                sent = []

                async def capture_reply(text, **kwargs):
                    sent.append((text, kwargs))

                update = SimpleNamespace(
                    effective_user=fixture.Query("").from_user,
                    message=SimpleNamespace(text="INERT CUSTOM BRIEF", reply_text=capture_reply),
                )
                self.assertTrue(asyncio.run(ns["handle_marketing_pending_text"](update, context)))
                self.assertEqual([((), {})], prompt.answers)
                self.assertEqual("INERT MARKETING PLAN", sent[-1][0])
                back = next(
                    button for row in sent[-1][1]["reply_markup"].inline_keyboard
                    for button in row if button.text.startswith("⬅")
                )
                self.assertEqual(expected_back, back.callback_data)

    def test_unscoped_legacy_plan_result_keeps_admin_back(self):
        ns = _runtime()
        context = SimpleNamespace(user_data={})
        menu = _dispatch(ns, "marketing|start", context)
        kind = next(button for button in _controls(menu) if button.callback_data == "marketing|kind|physical")
        suggestions = _dispatch(ns, kind.callback_data, context)
        choice = next(button for button in _controls(suggestions) if button.callback_data == "marketing|choice|1")
        plan = _dispatch(ns, choice.callback_data, context)
        back = next(button for button in _controls(plan) if button.text.startswith("⬅"))
        self.assertEqual("menu|admin", back.callback_data)


if __name__ == "__main__":
    unittest.main()
