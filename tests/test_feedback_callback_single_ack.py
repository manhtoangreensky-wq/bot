import asyncio
import re
from pathlib import Path
from types import SimpleNamespace


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


class _Query:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=123, username="tester", first_name="Tester")
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _load_handler(side_effects, edits):
    match = re.search(
        r"(?ms)^async def handle_feedback_callback\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)",
        BOT_SOURCE,
    )
    assert match, "feedback callback handler is missing"

    async def _safe_edit_or_send(query, text, **kwargs):
        edits.append((query, text, kwargs))

    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "user_ui_lang": lambda _uid: "vi",
        "clear_feedback_pending": lambda uid: side_effects.append(("clear_feedback_pending", uid)),
        "clear_support_ticket_pending": lambda uid: side_effects.append(("clear_support_ticket_pending", uid)),
        "feedback_start_text": lambda lang: f"feedback-{lang}",
        "feedback_category_keyboard": lambda lang: f"categories-{lang}",
        "safe_edit_or_send": _safe_edit_or_send,
        "ui_text": lambda _lang, key: key,
        "InlineKeyboardMarkup": lambda rows: rows,
        "InlineKeyboardButton": lambda text, callback_data: (text, callback_data),
        "set_feedback_pending": lambda uid, category: side_effects.append(("set_feedback_pending", uid, category)),
        "public_hub_copy": lambda _lang: {
            "feedback_prompt_back": "Back",
            "main_menu": "Main menu",
        },
        "feedback_message_prompt": lambda category, _lang: f"prompt-{category}",
    }
    exec(compile(match.group(0), "bot.py:handle_feedback_callback", "exec"), namespace)
    return namespace["handle_feedback_callback"]


def _registered_feedback_pattern():
    match = re.search(
        r"CallbackQueryHandler\(\s*handle_feedback_callback\s*,\s*pattern\s*=\s*r(['\"])(.*?)\1\s*\)",
        BOT_SOURCE,
    )
    assert match, "feedback callback handler is not registered"
    return re.compile(match.group(2))


def test_unsupported_feedback_callback_gets_one_alert_ack():
    query = _Query("feedback|unexpected")
    assert _registered_feedback_pattern().match(query.data)
    side_effects = []
    handler = _load_handler(side_effects, [])

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [(("Feedback action not supported.",), {"show_alert": True})], query.answers
    assert side_effects == []


def test_feedback_start_keeps_one_ack_and_existing_screen():
    query = _Query("feedback|start")
    assert _registered_feedback_pattern().match(query.data)
    side_effects = []
    edits = []
    handler = _load_handler(side_effects, edits)

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [((), {})]
    assert side_effects == [("clear_feedback_pending", 123), ("clear_support_ticket_pending", 123)]
    assert edits == [(query, "feedback-vi", {"parse_mode": "HTML", "reply_markup": "categories-vi"})]


def test_feedback_category_keeps_pending_owner_and_emits_back_and_home():
    query = _Query("feedback|cat|image_error")
    assert _registered_feedback_pattern().match(query.data)
    side_effects = []
    edits = []
    handler = _load_handler(side_effects, edits)

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [((), {})]
    assert side_effects == [("set_feedback_pending", 123, "image_error")]
    text, kwargs = edits[0][1], edits[0][2]
    assert text == "prompt-image_error"
    assert kwargs["reply_markup"] == [
        [("⬅️ Back", "feedback|start"), ("🏠 Main menu", "menu|main")],
    ]


def test_feedback_cancel_clears_only_its_pending_state_and_returns_home():
    query = _Query("feedback|cancel")
    assert _registered_feedback_pattern().match(query.data)
    side_effects = []
    edits = []
    handler = _load_handler(side_effects, edits)

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [((), {})]
    assert side_effects == [("clear_feedback_pending", 123)]
    assert edits[0][1:] == (
        "common.cancelled_not_charged",
        {"reply_markup": [[("common.main_menu", "menu|main")]]},
    )
