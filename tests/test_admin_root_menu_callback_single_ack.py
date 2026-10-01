import ast
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
    def __init__(self, text, callback_data=None, url=None):
        self.text = text
        self.callback_data = callback_data
        self.url = url


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class _Query:
    def __init__(self, user_id, data):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id, username="admin", first_name="Admin")
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _load_functions(*names, **dependencies):
    namespace = {"SimpleNamespace": SimpleNamespace, **dependencies}
    source = "from __future__ import annotations\n\n" + "\n\n".join(
        _function_source(name) for name in names
    )
    exec(compile(source, str(BOT_PATH), "exec"), namespace)
    return namespace


def _main_menu_dependencies(is_admin, effects):
    copy = {
        key: key
        for key in (
            "free_tools_label", "video_label", "image_label", "translation_label",
            "audio_studio_label", "account_label", "topup_pricing_label", "autopost_label",
            "chat_pro_label", "notes_docs_label", "support", "guide_label", "feedback_label",
            "center", "change_language", "admin_label",
        )
    }

    def record(name):
        return lambda *_args, **_kwargs: effects.append(name)

    async def safe_edit(query, text, **kwargs):
        query.edits.append((text, kwargs))

    return {
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "normalize_user_language": lambda lang: lang,
        "public_hub_copy": lambda _lang: copy,
        "product_context_callback": lambda *_args: "music_quick|root",
        "PRODUCT_CONTEXT_SHOWROOM": "showroom",
        "TOAN_AAS_COMMUNITY_URL": "https://community.toanaas.vn",
        "public_chat_runtime": SimpleNamespace(CHAT_PRO_RATE_LABEL="test rate"),
        "VIDEO_TAIL9_TEXT_INPUT_KEY": "video_tail_pending",
        "DOC_TOOL_MENU_ACTIONS": set(),
        "is_admin_user": lambda _uid: is_admin,
        "get_user_language": lambda _uid: "vi",
        "clear_broadcast_lite_pending": record("broadcast"),
        "clear_translation_menu_pending": record("translation_menu"),
        "clear_translation_session": record("translation_session"),
        "clear_media_creator_pending_states": record("media_creator"),
        "clear_support_ticket_pending": record("support_ticket"),
        "clear_finance_compliance_pending": record("finance_compliance"),
        "clear_internal_archive_pending": record("internal_archive"),
        "clear_doc_tool_pending": record("doc_tool"),
        "clear_storage_addon_pending": record("storage_addon"),
        "clear_memory_guided_pending": record("memory_guided"),
        "clear_music_guided_pending": record("music_guided"),
        "safe_edit_query_message": safe_edit,
        "localized_menu_content": lambda action, _admin, _lang, _uid: (
            f"existing screen:{action}", f"existing keyboard:{action}"
        ),
    }


def _registered_menu_pattern():
    match = re.search(
        r"CallbackQueryHandler\(\s*handle_menu_callback\s*,\s*pattern\s*=\s*(r?['\"][^'\"]+['\"])\s*\)",
        BOT_SOURCE,
    )
    assert match is not None, "handle_menu_callback must be registered"
    return re.compile(ast.literal_eval(match.group(1)))


class AdminRootMenuCallbackSingleAckTests(unittest.TestCase):
    def _emitted_admin_callback(self):
        keyboard_dependencies = _main_menu_dependencies(True, [])
        keyboard_namespace = _load_functions(
            "localized_main_menu_keyboard", **keyboard_dependencies
        )
        markup = keyboard_namespace["localized_main_menu_keyboard"](True, "vi")
        callbacks = [
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.callback_data
        ]
        self.assertIn("menu|admin", callbacks)
        self.assertRegex("menu|admin", _registered_menu_pattern())
        return "menu|admin"

    def test_revoked_admin_root_button_is_denied_once_before_state_cleanup(self):
        effects = []
        dependencies = _main_menu_dependencies(False, effects)
        namespace = _load_functions("handle_menu_callback", **dependencies)
        query = _Query(991122, self._emitted_admin_callback())
        pending = {"video_tail_pending": "must remain"}
        context = SimpleNamespace(user_data=pending)

        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=query), context,
        ))

        self.assertEqual(
            query.answers,
            [(("Khu vực này chỉ dành cho Admin.",), {"show_alert": True})],
        )
        self.assertEqual(query.edits, [], "stale admin buttons must not render an admin screen")
        self.assertEqual(effects, [], "denial must not clear user pending state")
        self.assertEqual(pending, {"video_tail_pending": "must remain"})

    def test_authorized_admin_root_button_keeps_ack_and_destination(self):
        effects = []
        dependencies = _main_menu_dependencies(True, effects)
        namespace = _load_functions("handle_menu_callback", **dependencies)
        query = _Query(123, self._emitted_admin_callback())

        asyncio.run(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(user_data={}),
        ))

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(
            query.edits,
            [("existing screen:admin", {"reply_markup": "existing keyboard:admin"})],
        )


if __name__ == "__main__":
    unittest.main()
