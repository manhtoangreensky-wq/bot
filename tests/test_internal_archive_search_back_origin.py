import asyncio
import html
import re
import unittest
from pathlib import Path
from types import SimpleNamespace


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def _source_function(name):
    start = re.search(rf"(?m)^(?:async )?def {re.escape(name)}\(", BOT_SOURCE)
    if not start:
        raise AssertionError(f"missing actual source function: {name}")
    following = re.search(r"(?m)^(?:async )?def [A-Za-z_]\w*\(", BOT_SOURCE[start.end():])
    end = start.end() + following.start() if following else len(BOT_SOURCE)
    return BOT_SOURCE[start.start():end]


class _Button:
    def __init__(self, text, callback_data):
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

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def _runtime():
    clock = [1000.0]
    captured = []
    namespace = {
        "USER_PENDING": {},
        "html": html,
        "time": SimpleNamespace(time=lambda: clock[0]),
        "INTERNAL_ARCHIVE_TTL_SECONDS": 900,
        "INTERNAL_DOC_DEPARTMENTS": {
            "customers": "Hồ sơ khách hàng",
            "sales": "Hồ sơ kinh doanh",
        },
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "SimpleNamespace": SimpleNamespace,
        "is_admin_user": lambda _uid: True,
        "clear_doc_tool_pending": lambda _uid: None,
        "clear_media_creator_pending_states": lambda _uid: None,
        "internal_archive_menu_text": lambda: "ARCHIVE ROOT",
        "internal_archive_department_text": lambda department: f"DEPARTMENT DASHBOARD: {department}",
        "safe_edit_query_message": None,
    }
    for name in (
        "internal_archive_pending_key",
        "set_internal_archive_pending",
        "get_internal_archive_pending",
        "clear_internal_archive_pending",
        "internal_archive_menu_keyboard",
        "internal_archive_department_keyboard",
        "handle_internal_archive_callback",
    ):
        exec(compile("from __future__ import annotations\n" + _source_function(name), f"bot.py:{name}", "exec"), namespace)

    async def safe_edit(_query, text, **kwargs):
        captured.append((text, kwargs.get("reply_markup")))

    namespace["safe_edit_query_message"] = safe_edit
    registration = re.search(
        r"CallbackQueryHandler\(handle_internal_archive_callback,\s*pattern=r(['\"])(.*?)\1\)",
        BOT_SOURCE,
    )
    if not registration:
        raise AssertionError("actual Internal Archive callback registration is missing")
    route_pattern = re.compile(registration.group(2))

    async def click(user_id, callback_data):
        query = _Query(user_id, callback_data)
        if not route_pattern.match(callback_data):
            raise AssertionError(f"emitted callback is not handled by Archive route: {callback_data}")
        await namespace["handle_internal_archive_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace()
        )
        if len(query.answers) != 1:
            raise AssertionError(f"expected one callback acknowledgement, got {len(query.answers)}")
        return query

    return namespace, captured, clock, click


class InternalArchiveSearchBackOriginTests(unittest.TestCase):
    def test_root_search_prompt_back_returns_to_archive_root(self):
        runtime, captured, _clock, click = _runtime()
        user_id = 700101
        root_markup = runtime["internal_archive_menu_keyboard"]()
        self.assertEqual(
            _callbacks(root_markup),
            [
                "archive|dept|customers", "archive|dept|sales", "archive|search",
                "menu|main_memory", "menu|main",
            ],
        )

        asyncio.run(click(user_id, "archive|search"))
        back_markup = captured[-1][1]
        self.assertEqual(_callbacks(back_markup), ["archive|root", "menu|main"])
        self.assertEqual(runtime["get_internal_archive_pending"](user_id)["step"], "awaiting_search")

        asyncio.run(click(user_id, "archive|root"))
        self.assertEqual(captured[-1][0], "ARCHIVE ROOT")
        self.assertEqual(_callbacks(captured[-1][1]), _callbacks(root_markup))
        self.assertIsNone(runtime["get_internal_archive_pending"](user_id))

    def test_expired_department_search_back_still_returns_to_its_department(self):
        runtime, captured, clock, click = _runtime()
        user_id = 700102
        await_click = lambda callback: asyncio.run(click(user_id, callback))

        await_click("archive|dept|customers")
        department_markup = captured[-1][1]
        self.assertEqual(
            _callbacks(department_markup),
            [
                "archive|quick", "archive|recent", "archive|types", "archive|search_dept",
                "archive|help", "archive|root", "menu|main",
            ],
        )
        await_click("archive|search_dept")
        search_prompt_markup = captured[-1][1]
        self.assertEqual(_callbacks(search_prompt_markup), ["archive|back_department|customers", "menu|main"])
        self.assertEqual(runtime["get_internal_archive_pending"](user_id)["step"], "awaiting_search_department")

        clock[0] += 901
        await_click(_callbacks(search_prompt_markup)[0])

        state = runtime["get_internal_archive_pending"](user_id)
        self.assertEqual(state and state.get("step"), "department_dashboard")
        self.assertEqual(state and state.get("department"), "customers")
        self.assertEqual(captured[-1][0], "DEPARTMENT DASHBOARD: customers")
        self.assertEqual(_callbacks(captured[-1][1]), _callbacks(department_markup))

    def test_live_department_state_outranks_stale_search_back_payload(self):
        runtime, captured, _clock, click = _runtime()
        user_id = 700103
        runtime["set_internal_archive_pending"](
            user_id, "department_dashboard", department="sales"
        )

        asyncio.run(click(user_id, "archive|back_department|customers"))

        state = runtime["get_internal_archive_pending"](user_id)
        self.assertEqual(state["step"], "department_dashboard")
        self.assertEqual(state["department"], "sales")
        self.assertEqual(captured[-1][0], "DEPARTMENT DASHBOARD: sales")
        self.assertEqual(
            _callbacks(captured[-1][1]),
            [
                "archive|quick", "archive|recent", "archive|types", "archive|search_dept",
                "archive|help", "archive|root", "menu|main",
            ],
        )


if __name__ == "__main__":
    unittest.main()
