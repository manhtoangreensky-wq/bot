import re
from pathlib import Path
from types import SimpleNamespace
import unittest


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


class _Button:
    def __init__(self, text, callback_data=None, url=None, **_kwargs):
        self.text = text
        self.callback_data = callback_data
        self.url = url


class _Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class _Query:
    def __init__(self, user_id, data, events):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.events = events
        self.answers = []
        self.message = SimpleNamespace(reply_text=self._reply_text)

    async def answer(self, *args, **kwargs):
        self.events.append("ack")
        self.answers.append((args, kwargs))

    async def _reply_text(self, text, **kwargs):
        self.events.append("reply")
        self.reply = (text, kwargs)


def _source_function(name):
    starts = (
        BOT_SOURCE.find(f"\nasync def {name}(") + 1,
        BOT_SOURCE.find(f"\ndef {name}(") + 1,
    )
    start = next((position for position in starts if position > 0), -1)
    assert start >= 0, f"production function {name} is missing"
    lines = BOT_SOURCE[start:].splitlines(keepends=True)
    body = [lines[0]]
    for line in lines[1:]:
        if line.startswith(("async def ", "def ", "class ")):
            break
        body.append(line)
    return "".join(body)


def _registered_manual_route(*, is_admin, events, db_connect=None):
    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "SimpleNamespace": SimpleNamespace,
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "is_admin_user": is_admin,
        "db_connect": db_connect or (lambda: (_ for _ in ()).throw(AssertionError("unexpected DB access"))),
        "set_manual_approval_state": lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("approval state must not change")),
        "cmd_duyet": lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("wallet approval must not run")),
        "cmd_tuchoi": lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("bill rejection must not run")),
    }
    for name in ("manual_pending_admin_keyboard", "handle_manual_package_choice"):
        exec(compile(_source_function(name), f"bot.py:{name}", "exec"), namespace)

    registrations = []
    namespace.update(
        tg_app=SimpleNamespace(add_handler=registrations.append),
        CallbackQueryHandler=lambda callback, pattern: SimpleNamespace(
            callback=callback,
            pattern=re.compile(pattern),
        ),
    )
    registration = next(
        line.strip()
        for line in BOT_SOURCE.splitlines()
        if "tg_app.add_handler(CallbackQueryHandler(handle_manual_package_choice," in line
    )
    exec(registration, namespace)

    keyboard = namespace["manual_pending_admin_keyboard"]({"id": 902, "user_id": "123"})
    emitted = next(
        button
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data == "manual|approve_expected|902"
    )
    route = next(item for item in registrations if item.pattern.match(emitted.callback_data))
    assert route.callback is namespace["handle_manual_package_choice"]
    return emitted.callback_data, route


def _run_no_io(awaitable):
    try:
        awaitable.send(None)
    except StopIteration:
        return
    raise AssertionError("fixture callback unexpectedly yielded I/O")


class ManualPackageCallbackSingleAckTests(unittest.TestCase):
    def test_emitted_bill_approval_denial_returns_only_one_alert_ack(self):
        events = []
        callback_data, route = _registered_manual_route(
            is_admin=lambda _uid: False,
            events=events,
        )
        query = _Query(456, callback_data, events)

        _run_no_io(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace(args=[])))

        self.assertEqual(
            query.answers,
            [(("Bạn không có quyền duyệt bill.",), {"show_alert": True})],
        )
        self.assertEqual(events, ["ack"])

    def test_authorized_emitted_approval_acknowledges_before_read_only_lookup(self):
        events = []

        class _Cursor:
            def fetchone(self):
                events.append("fetch")
                return None

        class _Connection:
            def execute(self, *_args):
                events.append("db_read")
                return _Cursor()

            def close(self):
                events.append("db_close")

        callback_data, route = _registered_manual_route(
            is_admin=lambda uid: uid == 123,
            events=events,
            db_connect=lambda: _Connection(),
        )
        query = _Query(123, callback_data, events)

        _run_no_io(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace(args=[])))

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(events, ["ack", "db_read", "fetch", "db_close", "reply"])
        self.assertIn("không còn ở trạng thái chờ duyệt", query.reply[0])


if __name__ == "__main__":
    unittest.main()
