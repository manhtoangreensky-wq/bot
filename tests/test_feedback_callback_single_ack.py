import asyncio
import html
import re
from pathlib import Path
from types import SimpleNamespace


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def _run_immediate(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as stop:
        return stop.value
    coroutine.close()
    raise AssertionError("fixture callback unexpectedly yielded asynchronous I/O")


class _Query:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=123, username="tester", first_name="Tester")
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _load_handler(side_effects, edits, user_lang=None):
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
        "user_ui_lang": user_lang or (lambda _uid: "vi"),
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


def _emitted_feedback_category_callbacks():
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
    return namespace["FEEDBACK_CATEGORY_LABELS"], callbacks


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


def test_feedback_start_acknowledges_before_user_language_lookup():
    query = _Query("feedback|start")
    side_effects = []
    edits = []
    language_lookups = []

    def user_lang_after_ack(uid):
        assert query.answers == [((), {})]
        language_lookups.append(uid)
        return "vi"

    handler = _load_handler(side_effects, edits, user_lang=user_lang_after_ack)
    _run_immediate(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [((), {})]
    assert language_lookups == [123]
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
        "ticket_customer_origin_keyboard": lambda markup, *_args, **_kwargs: markup,
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
    labels, callbacks = _emitted_feedback_category_callbacks()
    emitted = [data.split("|", 2)[2] for data in callbacks if data.startswith("feedback|cat|")]

    assert len(emitted) == 8
    assert len(set(emitted)) == 8
    assert set(emitted) == set(labels)
    assert "menu|main" in callbacks


def test_every_emitted_feedback_category_reaches_registered_handler():
    labels, callbacks = _emitted_feedback_category_callbacks()
    category_callbacks = [data for data in callbacks if data.startswith("feedback|cat|")]

    assert len(category_callbacks) == 8
    assert {data.split("|", 2)[2] for data in category_callbacks} == set(labels)

    for callback_data in category_callbacks:
        category = callback_data.split("|", 2)[2]
        query = _Query(callback_data)
        side_effects = []
        edits = []
        handler = _load_handler(side_effects, edits)

        assert _registered_feedback_pattern().match(callback_data)
        asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

        assert query.answers == [((), {})]
        assert side_effects == [("set_feedback_pending", 123, category)]
        assert len(edits) == 1
        assert edits[0][1] == f"prompt-{category}"
        assert edits[0][2]["parse_mode"] == "HTML"
        assert [button[1] for button in edits[0][2]["reply_markup"][0]] == [
            "feedback|start",
            "menu|main",
        ]


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


def test_transient_feedback_classification_failure_preserves_pending_for_same_message_retry():
    message_handler_match = re.search(
        r"(?ms)^@telegram_message_idempotent\s*\nasync def handle_message\(.*?handle_feedback_pending_text\(update, context\)",
        BOT_SOURCE,
    )
    assert message_handler_match, "the registered message path must dispatch Feedback pending text"

    def _source_function(name):
        start = re.search(rf"(?m)^(?:async\s+)?def {re.escape(name)}\b", BOT_SOURCE)
        assert start, name
        following = re.search(r"(?m)^(?:async\s+)?def [A-Za-z_]\w*\s*\(", BOT_SOURCE[start.end():])
        end = start.end() + following.start() if following else len(BOT_SOURCE)
        return BOT_SOURCE[start.start():end]

    user_pending = {
        "feedback:123": {
            "pending_action": "feedback",
            "category": "image_error",
            "created_at_ts": __import__("time").time(),
        }
    }
    calls = []
    classify_attempts = 0

    async def _classify(text, uid):
        nonlocal classify_attempts
        classify_attempts += 1
        calls.append(("classify", text, uid))
        if classify_attempts == 1:
            raise RuntimeError("transient classifier fixture failure")
        return {"suggested_reply_id": "technical_image_error"}

    def _create(user, category, text, _classification):
        calls.append(("create", user.id, category, text))
        return {"id": 901, "ticket_code": "FIXTURE-901"}, True

    async def _notify(*_args, **kwargs):
        calls.append(("notify", kwargs.get("customer_message")))

    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "USER_PENDING": user_pending,
        "QUICK_MEDIA_PENDING_TTL_SECONDS": 600,
        "SUPPORT_CATEGORIES": {"image_error"},
        "time": __import__("time"),
        "asyncio": asyncio,
        "wraps": __import__("functools").wraps,
        "html": html,
        "TELEGRAM_MESSAGE_DEDUPE_TTL_SECONDS": 600,
        "TELEGRAM_MESSAGE_DEDUPE_MAX": 5000,
        "TELEGRAM_MESSAGE_DEDUPE_DONE": {},
        "TELEGRAM_MESSAGE_DEDUPE_LOCKS": {},
        "safe_int": lambda value, fallback=0: int(value) if str(value or "").isdigit() else fallback,
        "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
        "normalize_user_language": lambda lang: lang,
        "user_ui_lang": lambda _uid: "vi",
        "classify_support_message": _classify,
        "support_ticket_priority": lambda _category, _text: "normal",
        "create_or_append_support_ticket": _create,
        "clear_feedback_pending": lambda uid: (calls.append(("clear", uid)), user_pending.pop(f"feedback:{uid}", None)),
        "public_hub_copy": lambda _lang: {
            "support_ticket_feedback_notice": "Feedback received",
            "support_ticket_label_code": "Ticket",
            "support_ticket_view_current": "View current",
            "support_ticket_add_message": "Add message",
            "support_ticket_add_attachment": "Add attachment",
            "support_my_tickets": "My tickets",
            "support_back": "Support",
            "main_menu": "Main",
        },
        "support_ticket_created_keyboard": lambda *_args: "fixture-actions",
        "InlineKeyboardButton": lambda text, callback_data: SimpleNamespace(text=text, callback_data=callback_data),
        "InlineKeyboardMarkup": lambda rows: SimpleNamespace(inline_keyboard=rows),
        "ui_text": lambda _lang, _key: "Back",
        "notify_admin_new_support_ticket": _notify,
        "support_reply_for_classification": lambda _classification: "ACK",
    }
    for name in (
        "support_ticket_created_keyboard",
        "ticket_customer_origin_keyboard",
        "feedback_pending_key",
        "get_feedback_pending",
        "handle_feedback_pending_text",
        "telegram_message_dedupe_key",
        "_prune_telegram_message_dedupe",
        "telegram_message_idempotent",
    ):
        exec(compile(_source_function(name), f"bot.py:{name}", "exec"), namespace)

    async def _not_pending(*_args, **_kwargs):
        return False

    namespace.update(
        handle_state_reset_slash_command=_not_pending,
        get_video_downloader_pending=lambda _uid: None,
        handle_video_ai_edit_pending_text=_not_pending,
        get_video_editor_pending=lambda _uid: None,
        handle_broadcast_lite_pending_text=_not_pending,
        get_video_dubbing_pending=lambda _uid: {},
        VIDEO_DUBBING_PENDING_TEXT_STEPS=set(),
        handle_manual_approval_pending_text=_not_pending,
        handle_manual_topup_pending_text=_not_pending,
        handle_local_video_planning_pending_text=_not_pending,
        handle_free_hub_pending_text=_not_pending,
        handle_translation_menu_pending_text=_not_pending,
        handle_translation_session_text=_not_pending,
        handle_finance_compliance_pending_text=_not_pending,
    )
    handle_message_source = _source_function("handle_message").split("\ntg_app: Application = None", 1)[0]
    exec(
        compile("@telegram_message_idempotent\n" + handle_message_source,
                "bot.py:handle_message", "exec"),
        namespace,
    )
    registrations = []
    namespace.update(
        tg_app=SimpleNamespace(add_handler=registrations.append),
        filters=SimpleNamespace(TEXT=1, COMMAND=2),
        MessageHandler=lambda filter_, callback: (filter_, callback),
    )
    message_registration = next(
        line.strip()
        for line in BOT_SOURCE.splitlines()
        if "MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)" in line
    )
    exec(message_registration, namespace)
    assert len(registrations) == 1
    assert registrations[0][1] is namespace["handle_message"]

    class _Message:
        message_id = 444
        text = "Fixture feedback"
        chat = SimpleNamespace(id=123)

        def __init__(self):
            self.replies = []

        async def reply_text(self, text, **kwargs):
            self.replies.append((text, kwargs))

    message = _Message()
    update = SimpleNamespace(
        message=message,
        effective_user=SimpleNamespace(id=123, username="tester", first_name="Tester"),
    )
    context = SimpleNamespace(user_data={})
    handler = registrations[0][1]

    async def _fail_then_retry():
        try:
            await handler(update, context)
        except RuntimeError as exc:
            assert str(exc) == "transient classifier fixture failure"
        else:
            raise AssertionError("the first fixture classification must fail")

        assert user_pending["feedback:123"]["pending_action"] == "feedback"
        assert namespace["TELEGRAM_MESSAGE_DEDUPE_DONE"] == {}
        assert calls == [("classify", "Fixture feedback", 123)]
        assert message.replies == []

        assert await handler(update, context) is None

    _run_immediate(_fail_then_retry())

    assert user_pending == {}
    assert calls == [
        ("classify", "Fixture feedback", 123),
        ("classify", "Fixture feedback", 123),
        ("create", 123, "image_error", "Fixture feedback"),
        ("clear", 123),
        ("notify", "Fixture feedback"),
    ]
    assert len(message.replies) == 1
    assert set(namespace["TELEGRAM_MESSAGE_DEDUPE_DONE"]) == {"123:444"}
    reply_markup = message.replies[0][1]["reply_markup"]
    emitted_view = next(
        button.callback_data
        for row in reply_markup.inline_keyboard
        for button in row
        if button.callback_data.startswith("ticket|pv|")
    )
    assert emitted_view == "ticket|pv|901|feedback_result"


def _source_function(name):
    match = re.search(
        rf"(?m)^(?:async\s+)?def {re.escape(name)}\s*\(",
        BOT_SOURCE,
    )
    assert match, f"missing source function: {name}"
    boundary = re.search(
        r"(?m)^(?:async\s+)?def\s+\w+\s*\(|^class\s+\w+|^[A-Z][A-Z0-9_]*\s*=",
        BOT_SOURCE[match.end():],
    )
    end = match.end() + boundary.start() if boundary else len(BOT_SOURCE)
    return BOT_SOURCE[match.start():end].rstrip()


def test_feedback_home_callback_returns_main_and_releases_only_feedback_pending():
    _labels, emitted_callbacks = _emitted_feedback_category_callbacks()
    home_callback = next(callback for callback in emitted_callbacks if callback == "menu|main")
    assert 'CallbackQueryHandler(handle_menu_callback, pattern=r"^menu\\|")' in BOT_SOURCE
    assert re.match(r"^menu\|", home_callback)

    user_id = 123
    pending = {
        f"feedback:{user_id}": {"pending_action": "feedback", "category": "image_error"},
        f"unrelated:{user_id}": {"pending_action": "preserve"},
    }
    cleanup_calls = []
    dependencies = {
        "USER_PENDING": pending,
        "feedback_pending_key": lambda uid: f"feedback:{uid}",
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "VIDEO_TAIL9_TEXT_INPUT_KEY": "video_tail_pending",
        "DOC_TOOL_MENU_ACTIONS": set(),
        "InlineKeyboardButton": lambda text, callback_data=None: SimpleNamespace(
            text=text, callback_data=callback_data
        ),
        "InlineKeyboardMarkup": lambda rows: SimpleNamespace(inline_keyboard=rows),
        "time": SimpleNamespace(perf_counter=lambda: 1.0, time=__import__("time").time),
        "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
        "is_admin_user": lambda _uid: False,
        "get_user_language": lambda _uid: "vi",
        "clear_translation_session": lambda _uid: False,
        "localized_menu_content": lambda action, *_args: (f"main:{action}", "main-keyboard"),
    }

    async def render(query, text, **kwargs):
        query.edits.append((text, kwargs))

    dependencies["safe_edit_query_message"] = render
    cleanup_names = (
        "clear_free_hub_pending", "clear_support_ticket_pending",
        "clear_quick_media_pending", "clear_quick_image_flow",
        "clear_public_image_prompt_pending", "clear_public_video_prompt_pending",
        "clear_media_aspect_pending", "clear_public_video_package_context",
        "clear_creative_motion_pending", "clear_cinematic_ad_pending",
        "clear_trend_video_flow_pending", "clear_trend_workflow_confirm_pending",
        "clear_image_menu_pending", "clear_frame_video_state", "clear_storyboard_state",
        "clear_developing_video_pending", "clear_product_context",
        "clear_music_guided_pending", "clear_translation_menu_pending",
        "clear_video_editor_pending", "clear_video_downloader_pending",
        "clear_video_dubbing_pending", "clear_video_finalization_state",
        "clear_video_addon_state", "clear_marketing_pending",
        "clear_shopaikey_pending_confirmations_for_user",
        "clear_finance_compliance_pending",
        "clear_internal_archive_pending", "clear_doc_tool_pending",
        "clear_storage_addon_pending", "clear_memory_guided_pending",
        "clear_pending_admin_tool_test",
        "_local_video_planning_clear_pending",
    )
    dependencies.update({name: lambda _uid: False for name in cleanup_names})
    dependencies["video_ai_edit_state"] = SimpleNamespace(clear_draft=lambda _uid: False)
    source = "\n\n".join(
        _source_function(name)
        for name in (
            "feedback_pending_key", "get_feedback_pending", "handle_feedback_pending_text",
            "clear_feedback_pending", "clear_media_creator_pending_states", "handle_menu_callback",
        )
    )
    namespace = {**dependencies, "QUICK_MEDIA_PENDING_TTL_SECONDS": 900}
    exec(compile(source, "bot.py:feedback_to_main_navigation", "exec"), namespace)
    actual_clear_feedback_pending = namespace["clear_feedback_pending"]

    def track_feedback_cleanup(uid):
        cleanup_calls.append(uid)
        return actual_clear_feedback_pending(uid)

    namespace["clear_feedback_pending"] = track_feedback_cleanup

    class MenuQuery:
        def __init__(self, data):
            self.data = data
            self.from_user = SimpleNamespace(id=user_id, username="tester", first_name="Tester")
            self.answers = []
            self.edits = []

        async def answer(self, *args, **kwargs):
            self.answers.append((args, kwargs))

    query = MenuQuery(home_callback)
    context = SimpleNamespace(user_data={})
    _run_immediate(namespace["handle_menu_callback"](
        SimpleNamespace(callback_query=query), context,
    ))

    assert query.answers == [((), {})]
    assert query.edits == [("main:main", {"reply_markup": "main-keyboard"})]
    assert cleanup_calls == [user_id]
    assert pending == {f"unrelated:{user_id}": {"pending_action": "preserve"}}

    class Message:
        text = "feedback content after leaving the form"

        async def reply_text(self, *_args, **_kwargs):
            raise AssertionError("feedback text must not be consumed after Home")

    update = SimpleNamespace(
        message=Message(),
        effective_user=SimpleNamespace(id=user_id),
    )
    assert _run_immediate(namespace["handle_feedback_pending_text"](update, context)) is False


def test_feedback_prompt_back_restores_category_picker_and_releases_old_pending():
    labels, emitted_callbacks = _emitted_feedback_category_callbacks()
    category_callback = next(
        callback for callback in emitted_callbacks
        if callback == "feedback|cat|image_error"
    )
    assert _registered_feedback_pattern().match(category_callback)
    pending = {"feedback:1234": {"pending_action": "preserve"}}
    copy = {
        **{f"feedback_{key}": key for key in (
            "payment_topup", "image_error", "video_error", "document_pdf",
            "package_combo", "refund", "feature_request", "other",
        )},
        "main_menu": "Main",
        "feedback_prompt_back": "Back",
        "feedback_prompt_title": "Feedback",
        "feedback_prompt_body": "Enter details",
    }
    dependencies = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "USER_PENDING": pending,
        "FEEDBACK_CATEGORY_LABELS": labels,
        "QUICK_MEDIA_PENDING_TTL_SECONDS": 900,
        "time": __import__("time"),
        "html": html,
        "normalize_user_language": lambda lang: lang or "vi",
        "user_ui_lang": lambda _uid: "vi",
        "public_hub_copy": lambda _lang: copy,
        "sanitize_log_text": lambda value: value,
        "clear_support_ticket_pending": lambda _uid: False,
        "InlineKeyboardButton": lambda text, callback_data=None: SimpleNamespace(
            text=text, callback_data=callback_data
        ),
        "InlineKeyboardMarkup": lambda rows: SimpleNamespace(inline_keyboard=rows),
    }
    async def render(query, text, **kwargs):
        query.edits.append((text, kwargs))

    dependencies["safe_edit_or_send"] = render
    source = "\n\n".join(
        _source_function(name)
        for name in (
            "feedback_pending_key", "set_feedback_pending", "get_feedback_pending",
            "clear_feedback_pending", "feedback_start_text", "feedback_category_keyboard",
            "feedback_message_prompt", "handle_feedback_pending_text", "handle_feedback_callback",
        )
    )
    namespace = dict(dependencies)
    exec(compile(source, "bot.py:feedback_prompt_back", "exec"), namespace)

    def dispatch(callback_data):
        query = _Query(callback_data)
        query.edits = []
        query.from_user.id = 123
        _run_immediate(namespace["handle_feedback_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(),
        ))
        assert query.answers == [((), {})]
        return query

    prompt = dispatch(category_callback)
    assert pending["feedback:123"]["category"] == "image_error"
    back = next(
        button.callback_data
        for row in prompt.edits[0][1]["reply_markup"].inline_keyboard
        for button in row
        if button.text.startswith("⬅")
    )
    assert back == "feedback|start"
    assert _registered_feedback_pattern().match(back)

    picker = dispatch(back)
    assert picker.edits[0][0] == namespace["feedback_start_text"]("vi")
    assert "feedback:123" not in pending
    assert pending["feedback:1234"] == {"pending_action": "preserve"}
    picker_callbacks = {
        button.callback_data
        for row in picker.edits[0][1]["reply_markup"].inline_keyboard
        for button in row
        if button.callback_data
    }
    assert set(emitted_callbacks) <= picker_callbacks

    class Message:
        text = "ordinary text after Back"

        async def reply_text(self, *_args, **_kwargs):
            raise AssertionError("feedback text must not be consumed after Back")

    update = SimpleNamespace(
        message=Message(),
        effective_user=SimpleNamespace(id=123),
    )
    assert _run_immediate(namespace["handle_feedback_pending_text"](update, SimpleNamespace())) is False
