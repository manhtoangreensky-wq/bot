"""A start/menu command releases Broadcast Lite input ownership only."""

import ast
import asyncio
import copy
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

import admin_broadcast


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
FUNCTIONS = {
    node.name: node
    for node in TREE.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}


def _compile_function(namespace, name):
    node = copy.deepcopy(FUNCTIONS[name])
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), "bot.py:" + name, "exec"), namespace)


def _compile_actual_broadcast_dispatch(namespace):
    handler = FUNCTIONS["handle_message"]
    handler_source = ast.get_source_segment(SOURCE, handler)
    start = handler_source.index("    if await handle_broadcast_lite_pending_text(update, context):")
    end = handler_source.index("    # A specific SubDub input state owns", start)
    branch = handler_source[start:end]
    wrapper = "async def actual_broadcast_dispatch(update, context):\n" + branch + "    return False\n"
    exec(compile(wrapper, "bot.py:handle_message Broadcast Lite branch", "exec"), namespace)


class BroadcastLiteStartPendingResetTests(unittest.TestCase):
    def _run_command_and_actual_pending_dispatch(self, command_name):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "broadcast-lite.db"
            admin_id = 9001
            original_content = "Nội dung bản nháp cần được giữ nguyên"
            draft = admin_broadcast.create_empty_draft(db_path, admin_id, state="draft")
            draft = admin_broadcast.set_draft_message(db_path, draft["draft_id"], admin_id, original_content)
            draft = admin_broadcast.set_draft_state(db_path, draft["draft_id"], admin_id, "awaiting_content")

            namespace = {
                "DB_FILE": str(db_path),
                "Update": object,
                "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
                "logger": SimpleNamespace(warning=lambda *args, **kwargs: None),
                "clear_broadcast_lite_pending_drafts": admin_broadcast.clear_pending_drafts,
                "get_latest_broadcast_lite_draft": admin_broadcast.get_latest_draft,
                "set_broadcast_lite_message": admin_broadcast.set_draft_message,
                "_broadcast_lite_cta_selection_text": lambda _draft: "CTA options",
                "broadcast_lite_cta_keyboard": lambda _draft: "CTA keyboard",
                "is_admin_user": lambda user_id: int(user_id) == admin_id,
                "log_command_received": lambda *args, **kwargs: None,
                "user_exists": lambda _uid: True,
                "get_user": lambda *args, **kwargs: None,
                "record_usage_event": lambda *args, **kwargs: None,
                "has_user_language": lambda _uid: True,
                "user_ui_lang": lambda _uid: "vi",
                "ui_text": lambda _lang, key: key,
                "get_user_language": lambda _uid: "vi",
                "user_selected_vietnamese_initially": lambda _uid: False,
                "localized_start_menu_text": lambda *_args: "Main menu",
                "mode_start_notice": lambda _uid: "",
                "localized_main_menu_keyboard": lambda *_args: "Main keyboard",
                "maybe_auto_grant_birthday_gift": _async_noop,
            }

            def clear_nothing_sync(_uid):
                return False

            for function_name in (
                "clear_free_hub_pending", "clear_support_ticket_pending", "clear_quick_media_pending",
                "clear_quick_image_flow", "clear_public_image_prompt_pending", "clear_public_video_prompt_pending",
                "clear_media_aspect_pending", "clear_public_video_package_context", "clear_creative_motion_pending",
                "clear_cinematic_ad_pending", "clear_trend_video_flow_pending", "clear_trend_workflow_confirm_pending",
                "clear_feedback_pending", "clear_image_menu_pending", "clear_frame_video_state",
                "clear_storyboard_state", "clear_developing_video_pending", "clear_product_context",
                "clear_music_guided_pending", "clear_translation_menu_pending", "clear_video_editor_pending",
                "clear_video_downloader_pending", "clear_video_dubbing_pending", "clear_video_finalization_state",
                "clear_video_addon_state", "clear_marketing_pending", "clear_shopaikey_pending_confirmations_for_user",
            ):
                namespace[function_name] = clear_nothing_sync
            namespace["video_ai_edit_state"] = SimpleNamespace(clear_draft=clear_nothing_sync)

            _compile_function(namespace, "clear_broadcast_lite_pending")
            _compile_function(namespace, "clear_media_creator_pending_states")
            _compile_function(namespace, "clear_pending_start_notice")
            _compile_function(namespace, "cmd_start")
            _compile_function(namespace, "cmd_menu")
            _compile_function(namespace, "handle_broadcast_lite_pending_text")
            _compile_actual_broadcast_dispatch(namespace)

            sent_messages = []

            async def reply_text(text, **_kwargs):
                sent_messages.append(str(text))

            user = SimpleNamespace(id=admin_id, first_name="Admin", username="admin")
            update = SimpleNamespace(
                effective_user=user,
                message=SimpleNamespace(text="This ordinary message must not become the old draft", reply_text=reply_text),
            )
            context = SimpleNamespace(args=[], user_data={})
            asyncio.run(namespace[command_name](update, context))

            after_command = admin_broadcast.get_draft(db_path, draft["draft_id"], admin_id)
            consumed = asyncio.run(namespace["actual_broadcast_dispatch"](update, context))
            after_dispatch = admin_broadcast.get_draft(db_path, draft["draft_id"], admin_id)
            return after_command, consumed, after_dispatch, sent_messages

    def test_start_and_menu_release_broadcast_input_without_changing_saved_draft(self):
        self.assertIn('CommandHandler("start",       cmd_start)', SOURCE)
        self.assertIn('CommandHandler("menu",        cmd_menu)', SOURCE)
        self.assertIn('MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)', SOURCE)
        for command_name in ("cmd_start", "cmd_menu"):
            with self.subTest(command=command_name):
                after_command, consumed, after_dispatch, _sent_messages = self._run_command_and_actual_pending_dispatch(command_name)
                self.assertEqual(after_command["state"], "draft")
                self.assertFalse(consumed)
                self.assertEqual(after_dispatch["message_text"], "Nội dung bản nháp cần được giữ nguyên")


async def _async_noop(*_args, **_kwargs):
    return None


if __name__ == "__main__":
    unittest.main()
