import asyncio
import html
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
    labels_match = re.search(r"(?ms)^FEEDBACK_CATEGORY_LABELS\s*=\s*\{.*?^\}", BOT_SOURCE)
    assert labels_match, "Feedback category labels are missing"
    exec(compile(labels_match.group(0), "bot.py:FEEDBACK_CATEGORY_LABELS", "exec"), namespace)
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


def test_concurrent_duplicate_feedback_update_is_suppressed_before_pending_handler():
    pending_match = re.search(
        r"(?ms)^async def handle_feedback_pending_text\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)",
        BOT_SOURCE,
    )
    assert pending_match, "feedback pending-text handler is missing"
    dedupe_key_match = re.search(
        r"(?ms)^def telegram_message_dedupe_key\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)",
        BOT_SOURCE,
    )
    prune_match = re.search(
        r"(?ms)^def _prune_telegram_message_dedupe\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)",
        BOT_SOURCE,
    )
    idempotent_match = re.search(
        r"(?ms)^def telegram_message_idempotent\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)",
        BOT_SOURCE,
    )
    assert dedupe_key_match and prune_match and idempotent_match
    message_handler_match = re.search(
        r"(?ms)^@telegram_message_idempotent\s*\nasync def handle_message\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)",
        BOT_SOURCE,
    )
    assert message_handler_match and "handle_feedback_pending_text(update, context)" in message_handler_match.group(0)

    user_pending = {
        "feedback:123": {
            "pending_action": "feedback",
            "category": "image_error",
        }
    }
    calls = []

    async def _classify(text, uid):
        calls.append(("classify", text, uid))
        return {"suggested_reply_id": "technical_image_error"}

    def _create(user, category, text, classification):
        calls.append(("create", user.id, category, text))
        return {"id": 901, "ticket_code": "FIXTURE-901"}, True

    async def _notify(*args, **kwargs):
        calls.append(("notify", kwargs.get("is_new"), kwargs.get("customer_message")))

    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "USER_PENDING": user_pending,
        "feedback_pending_key": lambda uid: f"feedback:{uid}",
        "get_feedback_pending": lambda uid: dict(user_pending.get(f"feedback:{uid}") or {}) or None,
        "clear_feedback_pending": lambda uid: (calls.append(("clear",)), user_pending.pop(f"feedback:{uid}", None)),
        "SUPPORT_CATEGORIES": {"image_error"},
        "classify_support_message": _classify,
        "support_ticket_priority": lambda _category, _text: "normal",
        "create_or_append_support_ticket": _create,
        "normalize_user_language": lambda lang: lang,
        "user_ui_lang": lambda _uid: "vi",
        "public_hub_copy": lambda _lang: {
            "support_ticket_feedback_notice": "Created",
            "support_ticket_label_code": "Ticket",
        },
        "html": html,
        "support_ticket_created_keyboard": lambda _ticket_id, _lang: "fixture-actions",
        "notify_admin_new_support_ticket": _notify,
        "support_reply_for_classification": lambda _classification: "ACK",
    }
    exec(compile(pending_match.group(0), "bot.py:handle_feedback_pending_text", "exec"), namespace)

    class _Message:
        text = "Fixture feedback"

        def __init__(self):
            self.message_id = 444
            self.chat = SimpleNamespace(id=123)
            self.replies = []

        async def reply_text(self, text, **kwargs):
            self.replies.append((text, kwargs))

    message = _Message()
    user = SimpleNamespace(id=123, username="tester", first_name="Tester")
    update = SimpleNamespace(message=message, effective_user=user)
    namespace.update({
        "asyncio": asyncio,
        "time": __import__("time"),
        "wraps": __import__("functools").wraps,
        "safe_int": lambda value, fallback=0: int(value) if str(value or "").isdigit() else fallback,
        "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
        "TELEGRAM_MESSAGE_DEDUPE_TTL_SECONDS": 600,
        "TELEGRAM_MESSAGE_DEDUPE_MAX": 5000,
        "TELEGRAM_MESSAGE_DEDUPE_DONE": {},
        "TELEGRAM_MESSAGE_DEDUPE_LOCKS": {},
    })
    for match in (dedupe_key_match, prune_match, idempotent_match):
        exec(compile(match.group(0), "bot.py:telegram_message_idempotency", "exec"), namespace)
    guarded_handler = namespace["telegram_message_idempotent"](
        namespace["handle_feedback_pending_text"]
    )

    async def _deliver_duplicate_update_concurrently():
        return await asyncio.gather(
            guarded_handler(update, SimpleNamespace()),
            guarded_handler(update, SimpleNamespace()),
        )

    results = asyncio.run(_deliver_duplicate_update_concurrently())

    assert results == [True, True]
    assert user_pending == {}
    assert calls == [
        ("classify", "Fixture feedback", 123),
        ("create", 123, "image_error", "Fixture feedback"),
        ("clear",),
        ("notify", True, "Fixture feedback"),
    ]
    assert len(message.replies) == 1
    assert set(namespace["TELEGRAM_MESSAGE_DEDUPE_DONE"]) == {"123:444"}


def test_expired_feedback_pending_is_consumed_and_offers_category_restart():
    handler_match = re.search(
        r"(?ms)^async def handle_feedback_pending_text\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)",
        BOT_SOURCE,
    )
    key_match = re.search(
        r"(?ms)^def feedback_pending_key\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)",
        BOT_SOURCE,
    )
    getter_match = re.search(
        r"(?ms)^def get_feedback_pending\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)",
        BOT_SOURCE,
    )
    assert handler_match and key_match and getter_match

    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "USER_PENDING": {
            "feedback:123": {
                "pending_action": "feedback",
                "category": "image_error",
                "created_at_ts": 1000,
            }
        },
        "time": SimpleNamespace(time=lambda: 1601),
        "QUICK_MEDIA_PENDING_TTL_SECONDS": 600,
        "normalize_user_language": lambda lang: lang,
        "user_ui_lang": lambda _uid: "vi",
        "feedback_expired_text": lambda lang: f"expired-{lang}",
        "feedback_category_keyboard": lambda lang: f"categories-{lang}",
    }
    for match in (key_match, getter_match, handler_match):
        exec(compile(match.group(0), "bot.py:feedback_expiry", "exec"), namespace)

    class _Message:
        text = "Feedback submitted after the form expired"

        def __init__(self):
            self.replies = []

        async def reply_text(self, text, **kwargs):
            self.replies.append((text, kwargs))

    message = _Message()
    update = SimpleNamespace(
        message=message,
        effective_user=SimpleNamespace(id=123),
    )

    handled = asyncio.run(namespace["handle_feedback_pending_text"](update, SimpleNamespace()))

    assert handled is True
    assert namespace["USER_PENDING"] == {}
    assert message.replies == [(
        "expired-vi",
        {"reply_markup": "categories-vi"},
    )]


def test_unsupported_feedback_category_callback_fails_closed():
    query = _Query("feedback|cat|retired_category")
    assert _registered_feedback_pattern().match(query.data)
    side_effects = []
    edits = []
    handler = _load_handler(side_effects, edits)

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [(("Feedback category not supported.",), {"show_alert": True})]
    assert side_effects == []
    assert edits == []


def test_feedback_category_keyboard_emits_only_whitelisted_categories_and_home():
    labels_match = re.search(r"(?ms)^FEEDBACK_CATEGORY_LABELS\s*=\s*\{.*?^\}", BOT_SOURCE)
    keyboard_match = re.search(
        r"(?ms)^def feedback_category_keyboard\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)",
        BOT_SOURCE,
    )
    assert labels_match and keyboard_match
    namespace = {
        "InlineKeyboardButton": lambda text, callback_data: SimpleNamespace(
            text=text, callback_data=callback_data
        ),
        "InlineKeyboardMarkup": lambda rows: SimpleNamespace(inline_keyboard=rows),
        "normalize_user_language": lambda lang: lang,
        "public_hub_copy": lambda _lang: {
            "feedback_payment_topup": "Payment",
            "feedback_image_error": "Image",
            "feedback_video_error": "Video",
            "feedback_document_pdf": "Documents",
            "feedback_package_combo": "Packages",
            "feedback_refund": "Refund",
            "feedback_feature_request": "Feature",
            "feedback_other": "Other",
            "main_menu": "Main",
        },
    }
    exec(compile(labels_match.group(0), "bot.py:FEEDBACK_CATEGORY_LABELS", "exec"), namespace)
    exec(compile(keyboard_match.group(0), "bot.py:feedback_category_keyboard", "exec"), namespace)
    keyboard = namespace["feedback_category_keyboard"]("vi")
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    ]
    emitted = [data.split("|", 2)[2] for data in callbacks if data.startswith("feedback|cat|")]

    assert len(emitted) == 8
    assert len(set(emitted)) == 8
    assert set(emitted) == set(namespace["FEEDBACK_CATEGORY_LABELS"])
    assert "menu|main" in callbacks


def test_feedback_expired_copy_covers_all_supported_locales():
    languages_match = re.search(r"(?ms)^USER_LANGUAGE_LABELS\s*=\s*\{.*?^\}", BOT_SOURCE)
    text_match = re.search(
        r"(?ms)^def feedback_expired_text\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)",
        BOT_SOURCE,
    )
    assert languages_match and text_match
    namespace = {"normalize_user_language": lambda lang: lang}
    exec(compile(languages_match.group(0), "bot.py:USER_LANGUAGE_LABELS", "exec"), namespace)
    exec(compile(text_match.group(0), "bot.py:feedback_expired_text", "exec"), namespace)

    messages = {
        language: namespace["feedback_expired_text"](language)
        for language in namespace["USER_LANGUAGE_LABELS"]
    }

    assert len(messages) == 17
    assert all(text.strip() and text != "common.expired_not_charged" for text in messages.values())
    assert namespace["feedback_expired_text"]("unsupported") == messages["en"]
