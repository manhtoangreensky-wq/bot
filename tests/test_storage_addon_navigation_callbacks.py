"""Exercise Storage Add-on custom-input Back through its registered callback."""
import asyncio
import re
import time
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


class _Button:
    def __init__(self, text, callback_data=None, **kwargs):
        self.text = text
        self.callback_data = callback_data
        self.url = kwargs.get("url")


class _Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class _Query:
    def __init__(self, data, user_id):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = object()
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _source_function(name):
    start = re.search(rf"(?m)^(?:async )?def {re.escape(name)}\(", SOURCE)
    assert start, f"missing source function: {name}"
    following = re.search(r"(?m)^(?:async )?def [A-Za-z_]\w*\(", SOURCE[start.end():])
    end = start.end() + following.start() if following else len(SOURCE)
    return SOURCE[start.start():end]


def _runtime(lang="vi"):
    screens = []
    routes = []
    tiers = [{"code": "test-tier", "addon_mb": 50, "amount_vnd": 10000}]

    async def render(query, text, **kwargs):
        screens.append((query, text, kwargs))

    scope = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "public_hub_copy": lambda _lang: defaultdict(
            lambda: "label",
            {
                "storage_addon_custom": "Custom amount",
                "storage_addon_back": "Back to Notes",
                "common_main_menu": "Main menu",
            },
        ),
        "normalize_user_language": lambda lang: lang,
        "storage_addon_tiers": lambda: tiers,
        "storage_addon_label": lambda _spec: "50MB",
        "get_user_language": lambda _uid: lang,
        "user_ui_lang": lambda _uid: lang,
        "ui_text": lambda lang, key, **_kwargs: f"{key}:{lang}",
        "safe_edit_or_send": render,
        "memory_storage_addon_text": lambda _lang: "Storage add-on menu",
        "time": time,
        "QUICK_MEDIA_PENDING_TTL_SECONDS": 600,
        "USER_PENDING": {},
        "start_storage_addon_purchase": lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("navigation must not start a purchase")
        ),
    }
    for name in (
        "memory_storage_addon_keyboard",
        "storage_addon_pending_key",
        "set_storage_addon_pending",
        "get_storage_addon_pending",
        "clear_storage_addon_pending",
        "storage_addon_expired_custom_text",
        "handle_storage_addon_callback",
        "handle_storage_addon_pending_text",
    ):
        exec(compile(_source_function(name), f"bot.py:{name}", "exec"), scope)

    registration = re.search(
        r"(?m)^\s*tg_app\.add_handler\(CallbackQueryHandler\(handle_storage_addon_callback,.*$",
        SOURCE,
    )
    assert registration, "storage callback registration is missing"
    scope.update(
        tg_app=SimpleNamespace(add_handler=routes.append),
        CallbackQueryHandler=lambda callback, pattern: (callback, re.compile(pattern)),
    )
    exec(compile(registration.group(0).strip(), "bot.py:storage callback registration", "exec"), scope)
    assert len(routes) == 1
    callback, pattern = routes[0]
    return scope, screens, callback, pattern


def _click(callback, pattern, data, user_id):
    assert pattern.search(data), f"registered storage handler does not accept {data!r}"
    query = _Query(data, user_id)
    asyncio.run(callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert query.answers == [((), {})]
    return query


class StorageAddonNavigationCallbacksTests(unittest.TestCase):
    def test_custom_amount_back_returns_to_storage_menu_and_keeps_memory_parent_route(self):
        user_id = 90817
        scope, screens, callback, pattern = _runtime()
        menu = scope["memory_storage_addon_keyboard"]("vi")
        menu_buttons = [button for row in menu.inline_keyboard for button in row]
        custom = next(button for button in menu_buttons if button.callback_data == "storage|custom")
        parent_back = next(button for button in menu_buttons if button.text.startswith("⬅️"))
        self.assertEqual(parent_back.callback_data, "menu|main_memory")
        menu_route = re.search(
            r"CallbackQueryHandler\(handle_menu_callback,\s*pattern=r(['\"])(.*?)\1",
            SOURCE,
        )
        self.assertIsNotNone(menu_route)
        self.assertRegex(parent_back.callback_data, re.compile(menu_route.group(2)))

        _click(callback, pattern, custom.callback_data, user_id)
        pending = scope["get_storage_addon_pending"](user_id)
        self.assertEqual(pending["pending_action"], "custom")
        custom_markup = screens[-1][2]["reply_markup"]
        custom_buttons = [button for row in custom_markup.inline_keyboard for button in row]
        back = next(button for button in custom_buttons if button.text.startswith("⬅️"))
        home = next(button for button in custom_buttons if button.text.startswith("🏠"))
        self.assertEqual(back.callback_data, "storage|menu")
        self.assertEqual(home.callback_data, "menu|main")

        _click(callback, pattern, back.callback_data, user_id)
        self.assertIsNone(scope["get_storage_addon_pending"](user_id))
        self.assertEqual(screens[-1][1], "Storage add-on menu")
        self.assertEqual(
            [
                button.callback_data
                for row in screens[-1][2]["reply_markup"].inline_keyboard
                for button in row
            ],
            [button.callback_data for button in menu_buttons],
        )

    def test_expired_custom_amount_is_consumed_and_returns_to_storage_menu(self):
        user_id = 90818
        other_user_id = 90819
        scope, _screens, callback, pattern = _runtime()
        menu = scope["memory_storage_addon_keyboard"]("vi")
        custom = next(
            button
            for row in menu.inline_keyboard
            for button in row
            if button.callback_data == "storage|custom"
        )
        _click(callback, pattern, custom.callback_data, user_id)

        pending_key = scope["storage_addon_pending_key"](user_id)
        scope["USER_PENDING"][pending_key]["created_at_ts"] = time.time() - 601
        scope["set_storage_addon_pending"](other_user_id, "custom")

        class _Message:
            text = "150MB"

            def __init__(self):
                self.replies = []

            async def reply_text(self, text, **kwargs):
                self.replies.append((text, kwargs))

        message = _Message()
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=user_id),
        )
        async def _not_pending(*_args):
            return False

        scope.update(
            Application=object,
            telegram_message_idempotent=lambda handler: handler,
            handle_state_reset_slash_command=_not_pending,
            get_video_downloader_pending=lambda _uid: None,
            handle_video_ai_edit_pending_text=_not_pending,
            get_video_editor_pending=lambda _uid: None,
            handle_video_editor_invalid_intake_text=_not_pending,
            handle_video_editor_pending_text=_not_pending,
            handle_video_editor_owned_text_fallback=_not_pending,
            VideoEditorStateUnavailableError=type("VideoEditorStateUnavailableError", (Exception,), {}),
            handle_broadcast_lite_pending_text=_not_pending,
            get_video_dubbing_pending=lambda _uid: {},
            VIDEO_DUBBING_PENDING_TEXT_STEPS=set(),
            handle_video_dubbing_pending_text=_not_pending,
            handle_manual_approval_pending_text=_not_pending,
            handle_manual_topup_pending_text=_not_pending,
            handle_local_video_planning_pending_text=_not_pending,
            handle_free_hub_pending_text=_not_pending,
            handle_translation_menu_pending_text=_not_pending,
            handle_translation_session_text=_not_pending,
            handle_finance_compliance_pending_text=_not_pending,
            handle_feedback_pending_text=_not_pending,
            handle_internal_archive_pending_text=_not_pending,
            handle_doc_tool_pending_text=_not_pending,
            handle_storyboard2_pending_text=_not_pending,
            handle_video_uiflow3_pending_text=_not_pending,
            handle_frame_video_pending_text=_not_pending,
            handle_architecture_profile_pending_text=_not_pending,
            handle_video_tail9_pending_text=_not_pending,
            handle_video_profile_studio_pending_text=_not_pending,
            handle_video_product_pending_text=_not_pending,
            handle_memory_pending_text=lambda *_args: (_ for _ in ()).throw(
                AssertionError("expired Storage input must be consumed before Memory")
            ),
        )
        exec(compile(_source_function("handle_message"), "bot.py:handle_message", "exec"), scope)
        context = SimpleNamespace(user_data={})
        result = asyncio.run(scope["handle_message"](update, context))

        self.assertIsNone(result)
        self.assertNotIn(pending_key, scope["USER_PENDING"])
        self.assertEqual(
            scope["get_storage_addon_pending"](other_user_id)["pending_action"],
            "custom",
        )
        self.assertEqual(len(message.replies), 1)
        text, kwargs = message.replies[0]
        self.assertEqual(
            text,
            "⏰ Yêu cầu nhập dung lượng tùy chỉnh đã hết hạn. Bot chưa trừ Xu.",
        )
        callbacks = [
            button.callback_data
            for row in kwargs["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertIn("storage|custom", callbacks)
        self.assertIn("menu|main_memory", callbacks)
        self.assertIn("menu|main", callbacks)

    def test_expired_storage_notice_is_localized_for_spanish(self):
        user_id = 90822
        scope, _screens, callback, pattern = _runtime("es")
        _click(callback, pattern, "storage|custom", user_id)
        pending_key = scope["storage_addon_pending_key"](user_id)
        scope["USER_PENDING"][pending_key]["created_at_ts"] = time.time() - 601

        class _Message:
            text = "150MB"

            def __init__(self):
                self.replies = []

            async def reply_text(self, text, **kwargs):
                self.replies.append((text, kwargs))

        message = _Message()
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=user_id),
        )
        handled = asyncio.run(
            scope["handle_storage_addon_pending_text"](update, SimpleNamespace())
        )

        self.assertTrue(handled)
        self.assertEqual(
            message.replies[0][0],
            "⏰ La solicitud de almacenamiento personalizado ha caducado. "
            "No se han descontado Xu.",
        )

    def test_expired_storage_notice_has_copy_for_all_supported_locales(self):
        scope, _screens, _callback, _pattern = _runtime()
        expected = {
            "vi": "⏰ Yêu cầu nhập dung lượng tùy chỉnh đã hết hạn. Bot chưa trừ Xu.",
            "en": "⏰ The custom storage request expired. The bot has not charged Xu.",
            "zh": "⏰ 自定义存储请求已过期。本次未扣除 Xu。",
            "es": "⏰ La solicitud de almacenamiento personalizado ha caducado. No se han descontado Xu.",
            "pt": "⏰ A solicitação de armazenamento personalizado expirou. Nenhum Xu foi cobrado.",
            "fr": "⏰ La demande de stockage personnalisé a expiré. Aucun Xu n’a été débité.",
            "de": "⏰ Die Anfrage für benutzerdefinierten Speicher ist abgelaufen. Es wurden keine Xu abgezogen.",
            "ja": "⏰ カスタムストレージのリクエストは期限切れです。Xuは差し引かれていません。",
            "ko": "⏰ 사용자 지정 저장 공간 요청이 만료되었습니다. Xu는 차감되지 않았습니다.",
            "hi": "⏰ कस्टम स्टोरेज अनुरोध की समय-सीमा समाप्त हो गई है। कोई Xu नहीं काटा गया है।",
            "ar": "⏰ انتهت صلاحية طلب التخزين المخصص. لم يتم خصم أي Xu.",
            "ru": "⏰ Срок действия запроса на дополнительное хранилище истёк. Xu не списаны.",
            "tr": "⏰ Özel depolama isteğinin süresi doldu. Xu kesilmedi.",
            "th": "⏰ คำขอพื้นที่จัดเก็บแบบกำหนดเองหมดอายุแล้ว ไม่มีการหัก Xu",
            "fil": "⏰ Nag-expire na ang kahilingan para sa custom na storage. Walang Xu na ibinawas.",
            "it": "⏰ La richiesta di spazio di archiviazione personalizzato è scaduta. Non è stato addebitato alcun Xu.",
            "id": "⏰ Permintaan penyimpanan kustom telah kedaluwarsa. Tidak ada Xu yang dipotong.",
        }
        text_for_language = scope["storage_addon_expired_custom_text"]
        self.assertEqual(
            {lang: text_for_language(lang) for lang in expected},
            expected,
        )
        self.assertEqual(text_for_language("unsupported"), expected["en"])

    def test_active_custom_amount_still_reaches_confirmation(self):
        user_id = 90821
        scope, _screens, callback, pattern = _runtime()
        _click(callback, pattern, "storage|custom", user_id)
        scope["storage_addon_spec_from_custom"] = lambda value: {"addon_mb": value}
        scope["memory_storage_addon_confirm_text"] = lambda spec, lang: (
            f"confirm:{spec['addon_mb']}:{lang}"
        )
        scope["memory_storage_addon_confirm_keyboard"] = lambda *_args: _Markup([])

        class _Message:
            text = "150"

            def __init__(self):
                self.replies = []

            async def reply_text(self, text, **kwargs):
                self.replies.append((text, kwargs))

        message = _Message()
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=user_id),
        )
        handled = asyncio.run(
            scope["handle_storage_addon_pending_text"](update, SimpleNamespace())
        )

        self.assertTrue(handled)
        self.assertEqual(message.replies[0][0], "confirm:150:vi")
        self.assertNotIn(scope["storage_addon_pending_key"](user_id), scope["USER_PENDING"])

    def test_expired_custom_pending_does_not_swallow_slash_command(self):
        user_id = 90820
        scope, _screens, callback, pattern = _runtime()
        _click(callback, pattern, "storage|custom", user_id)
        pending_key = scope["storage_addon_pending_key"](user_id)
        scope["USER_PENDING"][pending_key]["created_at_ts"] = time.time() - 601

        class _Message:
            text = "/start"

            def __init__(self):
                self.replies = []

            async def reply_text(self, text, **kwargs):
                self.replies.append((text, kwargs))

        message = _Message()
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=user_id),
        )
        handled = asyncio.run(
            scope["handle_storage_addon_pending_text"](update, SimpleNamespace())
        )

        self.assertFalse(handled)
        self.assertNotIn(pending_key, scope["USER_PENDING"])
        self.assertEqual(message.replies, [])


if __name__ == "__main__":
    unittest.main()
