"""Focused admin-report source availability regression; no bot import or I/O."""

import ast
import html
from pathlib import Path
import re
import sqlite3
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def source_function(name):
    match = re.search(rf"(?m)^(?:async )?def {re.escape(name)}\(", SOURCE)
    if not match:
        raise AssertionError(f"Missing report function: {name}")
    following = re.search(r"(?m)^(?:async )?def \w+\(", SOURCE[match.end():])
    end = match.end() + following.start() if following else len(SOURCE)
    node = ast.parse(SOURCE[match.start():end]).body[0]
    return compile(ast.Module(body=[node], type_ignores=[]), f"bot.py:{name}", "exec")


def report_with_provider_source(missing_provider):
    conn = sqlite3.connect(":memory:")
    schema = (
        "CREATE TABLE users(user_id INTEGER, join_date TEXT, credits INTEGER)",
        "CREATE TABLE usage_events(user_id INTEGER, created_at TEXT, event_type TEXT, "
        "tool_name TEXT, command TEXT DEFAULT '', amount_vnd INTEGER DEFAULT 0, xu_delta INTEGER DEFAULT 0)",
        "CREATE TABLE payos_orders(status TEXT, paid_at TEXT, amount INTEGER, xu INTEGER)",
        "CREATE TABLE pending_deposits(status TEXT, submitted_at TEXT, amount INTEGER, xu INTEGER)",
        "CREATE TABLE credit_events(delta INTEGER, created_at TEXT, event_type TEXT)",
        "CREATE TABLE referrals(created_at TEXT, status TEXT, rewarded_at TEXT, reward_xu INTEGER)",
        "CREATE TABLE birthday_gifts(granted_at TEXT, gift_xu INTEGER)",
        "CREATE TABLE birthday_review_requests(status TEXT)",
        "CREATE TABLE api_debug_events(provider TEXT, status TEXT, created_at TEXT)",
    )
    for statement in schema:
        if not (missing_provider and "api_debug_events" in statement):
            conn.execute(statement)
    conn.executemany(
        "INSERT INTO users(user_id, join_date, credits) VALUES (?, ?, ?)",
        [(1001, "2026-10-03 09:00:00", 100), (1002, "2026-10-02 09:00:00", 40)],
    )
    conn.executemany(
        "INSERT INTO usage_events(user_id, created_at, event_type, tool_name, command, amount_vnd, xu_delta) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (1001, "2026-10-03 10:00:00", "tool_use", "video", "/video", 0, 0),
            (1001, "2026-10-03 10:05:00", "tool_success", "video", "/video", 0, 0),
            (1002, "2026-10-03 10:10:00", "provider_error", "voice", "/voice", 0, 0),
            (1001, "2026-10-03 10:15:00", "payment_manual_approved", "", "/admin_approve", 5000, 50),
        ],
    )
    conn.execute(
        "INSERT INTO payos_orders(status, paid_at, amount, xu) VALUES (?, ?, ?, ?)",
        ("paid", "2026-10-03 10:20:00", 25000, 250),
    )
    conn.execute(
        "INSERT INTO pending_deposits(status, submitted_at, amount, xu) VALUES (?, ?, ?, ?)",
        ("pending", "2026-10-03 10:25:00", 10000, 100),
    )
    conn.executemany(
        "INSERT INTO credit_events(delta, created_at, event_type) VALUES (?, ?, ?)",
        [(100, "2026-10-03 10:30:00", "gift_xu"), (-25, "2026-10-03 10:35:00", "spend")],
    )
    conn.execute(
        "INSERT INTO referrals(created_at, status, rewarded_at, reward_xu) VALUES (?, ?, ?, ?)",
        ("2026-10-03 10:40:00", "rewarded", "2026-10-03 10:40:00", 15),
    )
    conn.execute(
        "INSERT INTO birthday_gifts(granted_at, gift_xu) VALUES (?, ?)",
        ("2026-10-03 10:45:00", 10),
    )
    conn.execute("INSERT INTO birthday_review_requests(status) VALUES ('pending')")
    if not missing_provider:
        conn.execute(
            "INSERT INTO api_debug_events(provider, status, created_at) VALUES (?, ?, ?)",
            ("fixture-provider", "TIMEOUT", "2026-10-03 10:50:00"),
        )
    conn.commit()
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
    conn.set_authorizer(lambda action, *_args: sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY)

    namespace = {
        "db_connect": lambda: conn,
        "html": html,
        "re": re,
        "PAYOS_STATUS_PAID": "paid",
    }
    for name in (
        "sql_scalar",
        "sql_rows",
        "vnd_text",
        "xu_text",
        "admin_report_payload",
        "format_admin_report",
        "admin_report_plain",
        "offline_admin_insight",
    ):
        exec(source_function(name), namespace)

    payload = namespace["admin_report_payload"](
        "2026-10-03 00:00:00", "2026-10-03 23:59:59", "today"
    )
    return (
        payload,
        namespace["format_admin_report"](payload),
        namespace["offline_admin_insight"](payload),
    )


class AdminReportSourceAvailabilityTest(unittest.TestCase):
    def test_missing_provider_log_is_not_reported_as_healthy_zero(self):
        healthy, healthy_text, _ = report_with_provider_source(missing_provider=False)
        missing, missing_text, offline_insight = report_with_provider_source(missing_provider=True)

        self.assertIs(healthy["providers"].get("available"), True)
        self.assertEqual(healthy["providers"]["errors"], 1)
        self.assertIn("Provider error/debug fail: <b>1</b>", healthy_text)

        self.assertIs(missing["providers"].get("available"), False)
        self.assertIsNone(missing["providers"]["errors"])
        self.assertIn("không khả dụng", missing_text.lower())
        self.assertNotIn("Provider error/debug fail: <b>0</b>", missing_text)
        self.assertIn("Provider errors: <b>không khả dụng</b>", offline_insight)

    def test_report_payload_aggregates_period_fixture_rows(self):
        payload, _formatted, _insight = report_with_provider_source(missing_provider=False)
        self.assertEqual(payload["users"], {"total": 2, "new": 1, "active": 2, "returning": 1})
        self.assertEqual(
            payload["money"],
            {
                "payos_amount": 25000,
                "payos_count": 1,
                "payos_xu": 250,
                "manual_amount": 5000,
                "manual_count": 1,
                "manual_xu": 50,
                "total_amount": 30000,
                "total_count": 2,
                "xu_sold": 300,
                "pending_deposits": 1,
            },
        )
        self.assertEqual(payload["credits"], {"added": 100, "spent": 25, "circulating": 140})
        self.assertEqual(
            (payload["tools"]["requested"], payload["tools"]["success"], payload["tools"]["fail"]),
            (1, 1, 1),
        )
        self.assertEqual(payload["providers"], {
            "available": True,
            "errors": 1,
            "rows": [("fixture-provider", "TIMEOUT", 1)],
        })
        self.assertEqual(
            (payload["growth"]["ref_starts"], payload["growth"]["ref_qualified"], payload["growth"]["ref_xu_rewarded"]),
            (1, 1, 15),
        )


def run_immediate(coro):
    try:
        coro.send(None)
    except StopIteration as completed:
        return completed.value
    raise AssertionError("report command fixture unexpectedly yielded I/O")


class AdminReportCommandRouteTests(unittest.TestCase):
    def test_registered_month_and_year_commands_render_and_deny_before_reads(self):
        bounds_calls = []
        payload_calls = []
        replies = []

        def month_bounds(raw):
            bounds_calls.append(("month", raw))
            if raw != "2026-10":
                raise ValueError("bad month")
            return "2026-10-01 00:00:00", "2026-11-01 00:00:00", "Month 2026-10"

        def year_bounds(raw):
            bounds_calls.append(("year", raw))
            if raw != "2026":
                raise ValueError("bad year")
            return "2026-01-01 00:00:00", "2027-01-01 00:00:00", "Year 2026"

        class Message:
            async def reply_text(self, text, **kwargs):
                replies.append((text, kwargs))

        class CommandHandlerFixture:
            def __init__(self, command, callback):
                self.command = command
                self.callback = callback

        handlers = []
        namespace = {
            "Update": object,
            "ContextTypes": type("ContextTypes", (), {"DEFAULT_TYPE": object}),
            "is_admin_user": lambda user_id: user_id == 42,
            "month_report_bounds": month_bounds,
            "year_report_bounds": year_bounds,
            "admin_report_payload": lambda start, end, label: (
                payload_calls.append((start, end, label)) or {"label": label}
            ),
            "format_admin_report": lambda payload: f"REPORT::{payload['label']}",
            "tg_app": type("App", (), {"add_handler": lambda _self, handler: handlers.append(handler)})(),
            "CommandHandler": CommandHandlerFixture,
        }
        for function_name in ("cmd_admin_report_month", "cmd_admin_report_year"):
            exec(source_function(function_name), namespace)

        registration_lines = re.findall(
            r'(?m)^\s*tg_app\.add_handler\(CommandHandler\("admin_report_(?:month|year)", '
            r'cmd_admin_report_(?:month|year)\)\)\s*$',
            SOURCE,
        )
        self.assertEqual(len(registration_lines), 2)
        for line in registration_lines:
            exec(compile(line.strip(), "bot.py:admin report command registration", "exec"), namespace)
        self.assertEqual(
            {handler.command for handler in handlers},
            {"admin_report_month", "admin_report_year"},
        )

        callbacks = {handler.command: handler.callback for handler in handlers}
        for command, args in (
            ("admin_report_month", ["2026-10"]),
            ("admin_report_year", ["2026"]),
        ):
            update = type(
                "Update",
                (),
                {
                    "effective_user": type("User", (), {"id": 42})(),
                    "message": Message(),
                },
            )()
            run_immediate(callbacks[command](update, type("Context", (), {"args": args})()))

        self.assertEqual(
            payload_calls,
            [
                ("2026-10-01 00:00:00", "2026-11-01 00:00:00", "Month 2026-10"),
                ("2026-01-01 00:00:00", "2027-01-01 00:00:00", "Year 2026"),
            ],
        )
        self.assertIn("REPORT::Month 2026-10", replies[0][0])
        self.assertIn("/export_accounting_month 2026-10", replies[0][0])
        self.assertIn("REPORT::Year 2026", replies[1][0])
        self.assertIn("/export_accounting_year 2026", replies[1][0])

        before = (len(bounds_calls), len(payload_calls))
        for command, args in (
            ("admin_report_month", ["2026-10"]),
            ("admin_report_year", ["2026"]),
        ):
            unauthorized = type(
                "Update",
                (),
                {
                    "effective_user": type("User", (), {"id": 7})(),
                    "message": Message(),
                },
            )()
            run_immediate(callbacks[command](unauthorized, type("Context", (), {"args": args})()))
            self.assertIn("không có quyền", replies[-1][0].lower())
            self.assertEqual((len(bounds_calls), len(payload_calls)), before)

        invalid = type(
            "Update",
            (),
            {
                "effective_user": type("User", (), {"id": 42})(),
                "message": Message(),
            },
        )()
        run_immediate(callbacks["admin_report_month"](invalid, type("Context", (), {"args": ["bad"]})()))
        self.assertIn("/admin_report_month YYYY-MM", replies[-1][0])
        self.assertEqual(len(payload_calls), before[1])

    def test_standard_report_quick_commands_map_periods_and_range_args(self):
        period_calls = []
        range_calls = []
        payload_calls = []
        replies = []

        class Message:
            async def reply_text(self, text, **kwargs):
                replies.append((text, kwargs))

        class CommandHandlerFixture:
            def __init__(self, command, callback):
                self.command = command
                self.callback = callback

        period_data = {
            "today": ("today-start", "today-end", "Today"),
            "week": ("week-start", "week-end", "Week"),
            "month": ("month-start", "month-end", "Month"),
            "year": ("year-start", "year-end", "Year"),
        }

        def report_period_bounds(period):
            period_calls.append(period)
            return period_data[period]

        def report_range_bounds(args):
            range_calls.append(list(args))
            return "range-start", "range-end", "Range"

        handlers = []
        namespace = {
            "Update": object,
            "ContextTypes": type("ContextTypes", (), {"DEFAULT_TYPE": object}),
            "is_admin_user": lambda user_id: user_id == 42,
            "report_period_bounds": report_period_bounds,
            "report_range_bounds": report_range_bounds,
            "admin_report_payload": lambda start, end, label: (
                payload_calls.append((start, end, label)) or {"label": label}
            ),
            "format_admin_report": lambda payload: f"REPORT::{payload['label']}",
            "tg_app": type("App", (), {"add_handler": lambda _self, handler: handlers.append(handler)})(),
            "CommandHandler": CommandHandlerFixture,
        }
        for function_name in (
            "send_admin_report",
            "cmd_report_today",
            "cmd_report_week",
            "cmd_report_month",
            "cmd_report_year",
            "cmd_report_range",
        ):
            exec(source_function(function_name), namespace)

        registration_lines = re.findall(
            r'(?m)^\s*tg_app\.add_handler\(CommandHandler\("report_(?:today|week|month|year|range)", '
            r'cmd_report_(?:today|week|month|year|range)\)\)\s*$',
            SOURCE,
        )
        self.assertEqual(len(registration_lines), 5)
        for line in registration_lines:
            exec(compile(line.strip(), "bot.py:standard report registration", "exec"), namespace)
        callbacks = {handler.command: handler.callback for handler in handlers}
        self.assertEqual(
            set(callbacks),
            {"report_today", "report_week", "report_month", "report_year", "report_range"},
        )

        args_by_command = {
            "report_today": [],
            "report_week": [],
            "report_month": [],
            "report_year": [],
            "report_range": ["2026-10-01", "2026-10-05"],
        }
        expected_periods = ["today", "week", "month", "year"]
        for command, args in args_by_command.items():
            update = type(
                "Update",
                (),
                {
                    "effective_user": type("User", (), {"id": 42})(),
                    "message": Message(),
                },
            )()
            run_immediate(callbacks[command](update, type("Context", (), {"args": args})()))

        self.assertEqual(period_calls, expected_periods)
        self.assertEqual(range_calls, [["2026-10-01", "2026-10-05"]])
        self.assertEqual(
            payload_calls,
            [period_data[period] for period in expected_periods]
            + [("range-start", "range-end", "Range")],
        )
        self.assertEqual(
            [reply[0] for reply in replies],
            [f"REPORT::{period_data[period][2]}" for period in expected_periods]
            + ["REPORT::Range"],
        )

        before = (len(period_calls), len(range_calls), len(payload_calls))
        for command, args in args_by_command.items():
            unauthorized = type(
                "Update",
                (),
                {
                    "effective_user": type("User", (), {"id": 7})(),
                    "message": Message(),
                },
            )()
            run_immediate(callbacks[command](unauthorized, type("Context", (), {"args": args})()))
            self.assertIn("không có quyền", replies[-1][0].lower())
            self.assertEqual((len(period_calls), len(range_calls), len(payload_calls)), before)


if __name__ == "__main__":
    unittest.main()
