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
    match = re.search(rf"(?m)^def {re.escape(name)}\(", SOURCE)
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
        healthy_empty, healthy_text, _ = report_with_provider_source(missing_provider=False)
        missing, missing_text, offline_insight = report_with_provider_source(missing_provider=True)

        self.assertIs(healthy_empty["providers"].get("available"), True)
        self.assertEqual(healthy_empty["providers"]["errors"], 0)
        self.assertIn("Provider error/debug fail: <b>0</b>", healthy_text)

        self.assertIs(missing["providers"].get("available"), False)
        self.assertIsNone(missing["providers"]["errors"])
        self.assertIn("không khả dụng", missing_text.lower())
        self.assertNotIn("Provider error/debug fail: <b>0</b>", missing_text)
        self.assertIn("Provider errors: <b>không khả dụng</b>", offline_insight)


if __name__ == "__main__":
    unittest.main()
