import asyncio
import re
import unittest
from pathlib import Path
from types import SimpleNamespace


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"
BOT_SOURCE = BOT_PATH.read_text(encoding="utf-8")


def _function_source(name):
    start = re.search(rf"(?m)^(?:async\s+)?def {re.escape(name)}\s*\(", BOT_SOURCE)
    assert start is not None, f"missing source function: {name}"
    boundary = re.search(
        r"(?m)^(?:async\s+)?def\s+\w+\s*\(|^class\s+\w+|^[A-Z][A-Z0-9_]*\s*=",
        BOT_SOURCE[start.end():],
    )
    end = start.end() + boundary.start() if boundary else len(BOT_SOURCE)
    return BOT_SOURCE[start.start():end].rstrip()


class _Button:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class _Query:
    def __init__(self, user_id, data):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


def _load_functions(*names, **dependencies):
    namespace = {
        "SimpleNamespace": SimpleNamespace,
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        **dependencies,
    }
    source = "from __future__ import annotations\n\n" + "\n\n".join(
        _function_source(name) for name in names
    )
    exec(compile(source, str(BOT_PATH), "exec"), namespace)
    return namespace


def _run_no_io(coro):
    try:
        coro.send(None)
    except StopIteration as done:
        return done.value
    coro.close()
    raise AssertionError("fixture callback yielded; refusing external I/O")


class OperatorMenuCallbackSingleAckTests(unittest.TestCase):
    def test_real_operator_menu_callback_route_is_registered(self):
        self.assertIn(
            r'tg_app.add_handler(CallbackQueryHandler(handle_operator_menu_callback, pattern=r"^opmenu\|"))',
            BOT_SOURCE,
        )

    def test_stale_operator_button_denies_non_admin_with_one_alert(self):
        namespace = _load_functions(
            "operator_menu_keyboard",
            "handle_operator_menu_callback",
            is_admin_user=lambda _uid: False,
        )
        markup = namespace["operator_menu_keyboard"]()
        callbacks = [
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
        ]
        self.assertIn("opmenu|cat_control", callbacks)

        query = _Query(991122, "opmenu|cat_control")
        _run_no_io(namespace["handle_operator_menu_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(),
        ))

        self.assertEqual(query.answers, [(("Chỉ Admin được dùng.",), {"show_alert": True})])
        self.assertEqual(query.edits, [], "denied stale callbacks must not open an operator command")

    def test_admin_category_keeps_one_normal_ack_and_existing_destination(self):
        namespace = _load_functions(
            "operator_menu_keyboard",
            "handle_operator_menu_callback",
            is_admin_user=lambda uid: uid == 123,
            operator_category_title=lambda action: f"title:{action}",
            operator_category_keyboard=lambda action: f"keyboard:{action}",
        )
        markup = namespace["operator_menu_keyboard"]()
        callback = next(
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.callback_data == "opmenu|cat_control"
        )
        query = _Query(123, callback)
        _run_no_io(namespace["handle_operator_menu_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(),
        ))

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(
            query.edits,
            [(
                "title:cat_control\n\nChọn lệnh cần xem hướng dẫn:",
                {"parse_mode": "HTML", "reply_markup": "keyboard:cat_control"},
            )],
        )

    def test_command_guide_back_returns_to_the_emitting_category(self):
        namespace = _load_functions(
            "operator_category_keyboard",
            "handle_operator_menu_callback",
            is_admin_user=lambda uid: uid == 123,
            operator_category_title=lambda action: action,
            operator_category_keyboard=lambda _category: None,
            html=SimpleNamespace(escape=lambda value: value),
        )
        registration = re.search(
            r'CallbackQueryHandler\(handle_operator_menu_callback,\s*pattern=r"([^"]+)"\)',
            BOT_SOURCE,
        )
        self.assertIsNotNone(registration)
        for category in (
            "cat_control", "cat_trend", "cat_affiliate", "cat_schedule",
            "cat_production", "cat_publish", "cat_money", "cat_api", "cat_internal",
        ):
            category_markup = namespace["operator_category_keyboard"](category)
            controls = [button for row in category_markup.inline_keyboard for button in row]
            for emitted in controls:
                if emitted.text.startswith("⬅️"):
                    self.assertEqual(emitted.callback_data, "opmenu|root")
                    continue
                with self.subTest(category=category, callback=emitted.callback_data):
                    self.assertRegex(emitted.callback_data, re.compile(registration.group(1)))
                    self.assertLessEqual(len(emitted.callback_data.encode("utf-8")), 64)
                    query = _Query(123, emitted.callback_data)
                    _run_no_io(namespace["handle_operator_menu_callback"](
                        SimpleNamespace(callback_query=query), SimpleNamespace(),
                    ))

                    self.assertEqual(query.answers, [((), {})])
                    guide_markup = query.edits[0][1]["reply_markup"]
                    back = next(
                        button
                        for row in guide_markup.inline_keyboard
                        for button in row
                        if button.text.startswith("⬅️")
                    )
                    self.assertEqual(back.callback_data, f"opmenu|{category}")

    def test_operator_root_dashboard_button_is_labeled_as_a_command_guide(self):
        namespace = _load_functions(
            "operator_menu_keyboard",
            "handle_operator_menu_callback",
            is_admin_user=lambda uid: uid == 123,
            operator_category_title=lambda action: action,
            operator_category_keyboard=lambda _category: None,
            html=SimpleNamespace(escape=lambda value: value),
        )
        root = namespace["operator_menu_keyboard"]()
        button = next(
            button
            for row in root.inline_keyboard
            for button in row
            if button.callback_data == "opmenu|dashboard"
        )
        registration = re.search(
            r'CallbackQueryHandler\(handle_operator_menu_callback,\s*pattern=r"([^"]+)"\)',
            BOT_SOURCE,
        )
        self.assertIsNotNone(registration)
        self.assertRegex(button.callback_data, re.compile(registration.group(1)))
        self.assertTrue(button.text.startswith("📘 Hướng dẫn"), button.text)

        query = _Query(123, button.callback_data)
        _run_no_io(namespace["handle_operator_menu_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(),
        ))
        self.assertEqual(query.answers, [((), {})])
        self.assertIn("/operator_dashboard", query.edits[0][0])
        back = query.edits[0][1]["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(back.callback_data, "opmenu|root")

    def test_publish_approval_instruction_is_not_labeled_as_completed_action(self):
        namespace = _load_functions(
            "operator_category_keyboard",
            "handle_operator_menu_callback",
            is_admin_user=lambda uid: uid == 123,
            operator_category_title=lambda action: action,
            html=SimpleNamespace(escape=lambda value: value),
        )
        category = "cat_publish"
        category_markup = namespace["operator_category_keyboard"](category)
        button = next(
            button
            for row in category_markup.inline_keyboard
            for button in row
            if button.callback_data == "opmenu|approvepublish|cat_publish"
        )
        self.assertTrue(button.text.startswith("📘 Hướng dẫn"), button.text)

        query = _Query(123, button.callback_data)
        _run_no_io(namespace["handle_operator_menu_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(),
        ))
        self.assertEqual(query.answers, [((), {})])
        self.assertIn("/approve_publish", query.edits[0][0])
        back = query.edits[0][1]["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(back.callback_data, "opmenu|cat_publish")

    def test_mark_published_instruction_is_not_labeled_as_completed_action(self):
        namespace = _load_functions(
            "operator_category_keyboard",
            "handle_operator_menu_callback",
            is_admin_user=lambda uid: uid == 123,
            operator_category_title=lambda action: action,
            html=SimpleNamespace(escape=lambda value: value),
        )
        category = "cat_publish"
        category_markup = namespace["operator_category_keyboard"](category)
        button = next(
            button
            for row in category_markup.inline_keyboard
            for button in row
            if button.callback_data == "opmenu|markpublished|cat_publish"
        )
        self.assertTrue(button.text.startswith("📘 Hướng dẫn"), button.text)

        query = _Query(123, button.callback_data)
        _run_no_io(namespace["handle_operator_menu_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(),
        ))
        self.assertEqual(query.answers, [((), {})])
        self.assertIn("/mark_published", query.edits[0][0])
        back = query.edits[0][1]["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(back.callback_data, "opmenu|cat_publish")

    def test_publisher_run_instruction_is_labeled_as_a_guide(self):
        namespace = _load_functions(
            "operator_category_keyboard",
            "handle_operator_menu_callback",
            is_admin_user=lambda uid: uid == 123,
            operator_category_title=lambda action: action,
            html=SimpleNamespace(escape=lambda value: value),
        )
        category = "cat_publish"
        category_markup = namespace["operator_category_keyboard"](category)
        button = next(
            button
            for row in category_markup.inline_keyboard
            for button in row
            if button.callback_data == "opmenu|publisherrun|cat_publish"
        )
        self.assertTrue(button.text.startswith("📘 Hướng dẫn"), button.text)

        query = _Query(123, button.callback_data)
        _run_no_io(namespace["handle_operator_menu_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(),
        ))
        self.assertEqual(query.answers, [((), {})])
        self.assertIn("/publisher_run", query.edits[0][0])
        back = query.edits[0][1]["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(back.callback_data, "opmenu|cat_publish")

    def test_publisher_status_instruction_is_not_mislabeled_as_live_status(self):
        namespace = _load_functions(
            "operator_category_keyboard",
            "handle_operator_menu_callback",
            is_admin_user=lambda uid: uid == 123,
            operator_category_title=lambda action: action,
            html=SimpleNamespace(escape=lambda value: value),
        )
        category = "cat_publish"
        category_markup = namespace["operator_category_keyboard"](category)
        button = next(
            button
            for row in category_markup.inline_keyboard
            for button in row
            if button.callback_data == "opmenu|publisherstatus|cat_publish"
        )
        self.assertTrue(button.text.startswith("📘 Hướng dẫn"), button.text)

        query = _Query(123, button.callback_data)
        _run_no_io(namespace["handle_operator_menu_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(),
        ))
        self.assertEqual(query.answers, [((), {})])
        self.assertIn("/publisher_status", query.edits[0][0])
        back = query.edits[0][1]["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(back.callback_data, "opmenu|cat_publish")

    def test_publish_queue_instruction_is_labeled_as_a_guide(self):
        namespace = _load_functions(
            "operator_category_keyboard",
            "handle_operator_menu_callback",
            is_admin_user=lambda uid: uid == 123,
            operator_category_title=lambda action: action,
            html=SimpleNamespace(escape=lambda value: value),
        )
        category = "cat_publish"
        category_markup = namespace["operator_category_keyboard"](category)
        button = next(
            button
            for row in category_markup.inline_keyboard
            for button in row
            if button.callback_data == "opmenu|publishqueue|cat_publish"
        )
        self.assertTrue(button.text.startswith("📘 Hướng dẫn"), button.text)

        query = _Query(123, button.callback_data)
        _run_no_io(namespace["handle_operator_menu_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(),
        ))
        self.assertEqual(query.answers, [((), {})])
        self.assertIn("/publish_queue", query.edits[0][0])
        back = query.edits[0][1]["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(back.callback_data, "opmenu|cat_publish")

    def test_publisher_handoff_instruction_is_labeled_as_a_guide(self):
        namespace = _load_functions(
            "operator_category_keyboard",
            "handle_operator_menu_callback",
            is_admin_user=lambda uid: uid == 123,
            operator_category_title=lambda action: action,
            html=SimpleNamespace(escape=lambda value: value),
        )
        category = "cat_publish"
        category_markup = namespace["operator_category_keyboard"](category)
        button = next(
            button
            for row in category_markup.inline_keyboard
            for button in row
            if button.callback_data == "opmenu|publisherhandoff|cat_publish"
        )
        self.assertTrue(button.text.startswith("📘 Hướng dẫn"), button.text)

        query = _Query(123, button.callback_data)
        _run_no_io(namespace["handle_operator_menu_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(),
        ))
        self.assertEqual(query.answers, [((), {})])
        self.assertIn("/publisher_handoff", query.edits[0][0])
        back = query.edits[0][1]["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(back.callback_data, "opmenu|cat_publish")

    def test_publish_cockpit_instruction_is_not_mislabeled_as_a_dashboard(self):
        namespace = _load_functions(
            "operator_category_keyboard",
            "handle_operator_menu_callback",
            is_admin_user=lambda uid: uid == 123,
            operator_category_title=lambda action: action,
            html=SimpleNamespace(escape=lambda value: value),
        )
        category = "cat_publish"
        category_markup = namespace["operator_category_keyboard"](category)
        button = next(
            button
            for row in category_markup.inline_keyboard
            for button in row
            if button.callback_data == "opmenu|publishcockpit|cat_publish"
        )
        self.assertTrue(button.text.startswith("📘 Hướng dẫn"), button.text)

        query = _Query(123, button.callback_data)
        _run_no_io(namespace["handle_operator_menu_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(),
        ))
        self.assertEqual(query.answers, [((), {})])
        self.assertIn("/publish_cockpit", query.edits[0][0])
        back = query.edits[0][1]["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(back.callback_data, "opmenu|cat_publish")

    def test_publish_readiness_instruction_is_not_mislabeled_as_a_check(self):
        namespace = _load_functions(
            "operator_category_keyboard",
            "handle_operator_menu_callback",
            is_admin_user=lambda uid: uid == 123,
            operator_category_title=lambda action: action,
            html=SimpleNamespace(escape=lambda value: value),
        )
        category = "cat_publish"
        category_markup = namespace["operator_category_keyboard"](category)
        button = next(
            button
            for row in category_markup.inline_keyboard
            for button in row
            if button.callback_data == "opmenu|readiness|cat_publish"
        )
        self.assertTrue(button.text.startswith("📘 Hướng dẫn"), button.text)

        query = _Query(123, button.callback_data)
        _run_no_io(namespace["handle_operator_menu_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(),
        ))
        self.assertEqual(query.answers, [((), {})])
        self.assertIn("/publish_readiness", query.edits[0][0])
        back = query.edits[0][1]["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(back.callback_data, "opmenu|cat_publish")


if __name__ == "__main__":
    unittest.main()
