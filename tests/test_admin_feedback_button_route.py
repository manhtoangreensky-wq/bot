import ast
import asyncio
import html
import re
from pathlib import Path
from types import SimpleNamespace


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"
BOT_SOURCE = BOT_PATH.read_text(encoding="utf-8")


def _function_source(name):
    start = re.search(rf"(?m)^(?:async\s+)?def {re.escape(name)}\s*\(", BOT_SOURCE)
    assert start is not None, f"missing callback/command function: {name}"
    boundary = re.search(
        r"(?m)^(?:async\s+)?def\s+\w+\s*\(|^class\s+\w+|^[A-Z][A-Z0-9_]*\s*=",
        BOT_SOURCE[start.end():],
    )
    end = start.end() + boundary.start() if boundary else len(BOT_SOURCE)
    return BOT_SOURCE[start.start():end].rstrip()


def _admin_modules():
    start = BOT_SOURCE.index("ADMIN_CONTROL_MODULES = {")
    end = BOT_SOURCE.index("\ndef admin_module_command_lines", start)
    assignment = ast.parse(BOT_SOURCE[start:end], filename=str(BOT_PATH)).body[0]
    return ast.literal_eval(assignment.value)


class _Button:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class _Message:
    chat_id = 123

    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))
        return self.replies[-1]


class _Query:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=123, username="tester", first_name="Tester")
        self.message = _Message()
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))
        return self.edits[-1]


def _load_functions(names, **dependencies):
    namespace = {
        "SimpleNamespace": SimpleNamespace,
        "ADMIN_CONTROL_MODULES": _admin_modules(),
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "html": html,
        **dependencies,
    }
    names = list(names)
    if "cmd_admin_gopy" in names:
        for helper in ("admin_child_keyboard", "send_pricing_lines"):
            if helper not in names:
                names.append(helper)
    source = "from __future__ import annotations\n\n" + "\n\n".join(
        _function_source(name) for name in names
    )
    exec(compile(source, str(BOT_PATH), "exec"), namespace)
    return namespace


def test_admin_support_buttons_open_their_labeled_destinations():
    namespace = _load_functions(["admin_module_keyboard"])
    markup = namespace["admin_module_keyboard"]("support")
    buttons = {
        button.text: button.callback_data
        for row in markup.inline_keyboard
        for button in row
    }

    assert buttons["📝 Góp ý admin"] == "admin_gopy|inbox"
    assert buttons["📌 Hướng dẫn hỗ trợ"] == "admin_help|support|admin_support"
    assert 'CallbackQueryHandler(handle_admin_gopy_callback, pattern=r"^admin_gopy\\|")' in BOT_SOURCE
    assert 'CallbackQueryHandler(handle_admin_help_callback, pattern=r"^admin_help\\|")' in BOT_SOURCE


def test_admin_feedback_callback_renders_existing_inbox_without_status_mutations():
    row = (7, "42", "@tester", "bug", "Broken button", "support", "new", "2026-09-26")

    class _Connection:
        def __init__(self):
            self.statements = []
            self.commits = 0
            self.closed = False

        def execute(self, statement, params=()):
            sql = " ".join(statement.split())
            self.statements.append((sql, params))
            assert sql.upper().startswith("SELECT "), "feedback callback must be read-only"
            return self

        def fetchall(self):
            return [row]

        def commit(self):
            self.commits += 1

        def close(self):
            self.closed = True

    connection = _Connection()
    namespace = _load_functions(
        ["cmd_admin_gopy", "handle_admin_gopy_callback"],
        db_connect=lambda: connection,
        is_admin_user=lambda user_id: user_id == 123,
        now_text=lambda: "unused",
    )
    query = _Query("admin_gopy|resolved|7")
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(args=["resolved", "7"])

    asyncio.run(namespace["handle_admin_gopy_callback"](update, context))

    assert query.answers == [((), {})]
    assert connection.closed
    assert connection.commits == 0
    assert len(connection.statements) == 1
    assert connection.statements[0][0].upper().startswith("SELECT ")
    assert len(query.message.replies) == 1
    assert "GÓP Ý / BÁO LỖI MỚI NHẤT" in query.message.replies[0][0]
    assert "Broken button" in query.message.replies[0][0]


def test_admin_support_guidance_callback_still_renders_the_handbook():
    async def safe_edit(query, text, reply_markup=None):
        query.edits.append((text, reply_markup))

    namespace = _load_functions(
        ["handle_admin_help_callback"],
        is_admin_user=lambda user_id: user_id == 123,
        admin_handbook_section_text=lambda kind: f"handbook:{kind}",
        admin_handbook_section_keyboard=lambda kind, return_action="": f"keyboard:{kind}",
        safe_edit_query_message=safe_edit,
    )
    query = _Query("admin_help|support")
    update = SimpleNamespace(callback_query=query)

    asyncio.run(namespace["handle_admin_help_callback"](update, SimpleNamespace()))

    assert query.answers == [((), {})]
    assert query.edits == [("handbook:support", "keyboard:support")]
