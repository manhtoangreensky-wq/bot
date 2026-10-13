import re
import unittest
from types import SimpleNamespace

from tests.test_admin_root_menu_callback_single_ack import (
    BOT_SOURCE,
    _Button,
    _Markup,
    _Query,
    _load_functions,
    _main_menu_dependencies,
    _run_no_io,
)


class ImageAiEntryBackOriginTests(unittest.TestCase):
    def _check_entry_back(self, input_kind, revisit_choices=False):
        actor, other = 42, 99
        recent_image = (
            {"file_id": "fixture-image", "file_unique_id": "fixture-unique"}
            if input_kind == "recent" else {}
        )
        other_key = f"image_menu:{other}"
        pending = {other_key: {"pending_action": "other-user-input"}}
        other_snapshot = dict(pending[other_key])

        def clear_actor_pending(uid, **_kwargs):
            pending.pop(f"image_menu:{uid}", None)

        def build_keyboard(buttons, *, nav_back, lang, main_label="Main"):
            flat = [_Button(label, callback) for label, callback in buttons]
            rows = [flat[index:index + 2] for index in range(0, len(flat), 2)]
            rows.append([_Button(nav_back[0], nav_back[1]), _Button(main_label, "menu|main")])
            return _Markup(rows)

        flow_keys = (
            "edit_add", "edit_remove", "edit_background", "edit_ad", "edit_product",
            "preset_text", "preset_logo", "edit_ratio", "edit_custom", "resize_crop",
            "resize_pad", "preset_custom", "preset_upscale", "preset_brightness",
        )
        dependencies = _main_menu_dependencies(False, [])
        dependencies.update({
            "public_hub_copy": lambda _lang: {
                key: key for key in (
                    "image_quick", "image_prompt_from_image", "image_ai_edit",
                    "image_edit", "back", "main_menu",
                )
            },
            "public_image_flow_copy": lambda _lang: {key: key for key in flow_keys},
            "public_image_screen_copy": lambda _lang: {"back_image": "Image", "send_image": "Send image"},
            "ui_text": lambda _lang, key: key,
            "build_2col_keyboard": build_keyboard,
            "image_menu_v5_text": lambda _lang: "Image hub",
            "image_edit_ai_choice_text": lambda _lang: "AI edit choices",
            "image_edit_instruction_text": lambda _lang: "Local edit choices",
            "image_edit_detail_request_text": lambda *_args: "AI edit request",
            "public_image_deep_copy": lambda _lang: {"resize_custom": "Custom", "edit_custom": "AI choices"},
            "image_edit_suggestions": lambda *_args: ["fixture suggestion 1", "fixture suggestion 2", "fixture suggestion 3"],
            "USER_PENDING": pending,
            "IMAGE_MENU_PENDING_ACTIONS": {
                "image_edit_wait_image", "image_edit_choice", "image_edit_request_custom",
                "image_resize_choice",
            },
            "QUICK_MEDIA_PENDING_TTL_SECONDS": 600,
            "re": re,
            "recent_image_file_state": lambda uid: dict(recent_image) if uid == actor else {},
            "clear_media_creator_pending_states": clear_actor_pending,
            "remember_last_user_file": lambda _update: None,
            "cache_recent_media_state": lambda _update: None,
            "_local_video_planning_clear_pending": lambda _context: None,
            "time": SimpleNamespace(perf_counter=lambda: 1.0, time=lambda: 100.0),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
        })
        namespace = _load_functions(
            "menu_text_main_image", "menu_text_main_image_i18n", "main_image_keyboard",
            "image_edit_ai_choice_keyboard", "image_edit_choice_keyboard",
            "image_edit_detail_request_keyboard",
            "image_edit_start_keyboard", "handle_image_menu_pending_photo",
            "handle_image_menu_pending_document",
            "image_menu_pending_key", "set_image_menu_pending", "get_image_menu_pending",
            "localized_menu_content", "handle_menu_callback", "handle_image_tools_callback",
            **dependencies,
        )
        registered = []
        namespace.update(
            tg_app=SimpleNamespace(add_handler=registered.append),
            CallbackQueryHandler=lambda callback, pattern: (callback, re.compile(pattern)),
        )
        for name in ("handle_menu_callback", "handle_image_tools_callback"):
            registration = re.search(
                rf"(?m)^\s*tg_app\.add_handler\(CallbackQueryHandler\({name},.*$",
                BOT_SOURCE,
            )
            self.assertIsNotNone(registration)
            exec(registration.group(0).strip(), namespace)

        def dispatch(query):
            matches = [callback for callback, pattern in registered if pattern.match(query.data)]
            self.assertEqual(len(matches), 1, query.data)
            return _run_no_io(matches[0](SimpleNamespace(callback_query=query), context))

        def callbacks(query):
            return [
                button.callback_data
                for row in query.edits[-1][1]["reply_markup"].inline_keyboard
                for button in row
            ]

        context = SimpleNamespace(user_data={})
        root = _Query(actor, "menu|main_image")
        dispatch(root)
        root_callbacks = callbacks(root)
        entry = next(value for value in root_callbacks if value == "imgtool|edit_ai_start")

        choices = _Query(actor, entry)
        dispatch(choices)
        if input_kind == "recent":
            choices_markup = choices.edits[-1][1]["reply_markup"]
        else:
            replies = []

            async def reply_text(text, **kwargs):
                replies.append((text, kwargs))

            image_file = SimpleNamespace(
                file_id="fixture-upload", file_unique_id="fixture-upload-unique",
                mime_type="image/png", file_name="fixture.png",
            )
            message = SimpleNamespace(
                reply_text=reply_text,
                photo=[image_file] if input_kind == "photo" else [],
                document=image_file if input_kind == "document" else None,
            )
            input_update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=actor))
            input_handler = namespace[f"handle_image_menu_pending_{input_kind}"]
            self.assertTrue(_run_no_io(input_handler(input_update, context)))
            choices_markup = replies[-1][1]["reply_markup"]

        if revisit_choices:
            option = next(
                button.callback_data for row in choices_markup.inline_keyboard
                for button in row if button.callback_data == "imgtool|edit_type|add_object"
            )
            request = _Query(actor, option)
            dispatch(request)
            choice_back = request.edits[-1][1]["reply_markup"].inline_keyboard[-1][0]
            restored_choices = _Query(actor, choice_back.callback_data)
            dispatch(restored_choices)
            choices_markup = restored_choices.edits[-1][1]["reply_markup"]

        back = choices_markup.inline_keyboard[-1][0]
        returned = _Query(actor, back.callback_data)
        dispatch(returned)

        self.assertEqual(callbacks(returned), root_callbacks)
        self.assertEqual(returned.answers, [((), {})])
        self.assertNotIn(f"image_menu:{actor}", pending)
        self.assertEqual(pending[other_key], other_snapshot)
        self.assertEqual(namespace["recent_image_file_state"](actor), recent_image)
        self.assertEqual(
            namespace["image_edit_ai_choice_keyboard"]("vi").inline_keyboard[-1][0].callback_data,
            "imgtool|edit_back_choice",
            "internal editor callers retain their existing parent",
        )

    def test_recent_image_ai_entry_back_returns_to_image_hub(self):
        self._check_entry_back("recent")

    def test_uploaded_photo_ai_entry_back_returns_to_image_hub(self):
        self._check_entry_back("photo")

    def test_uploaded_image_document_ai_entry_back_returns_to_image_hub(self):
        self._check_entry_back("document")

    def test_ai_option_back_then_parent_back_keeps_root_origin(self):
        self._check_entry_back("recent", revisit_choices=True)


if __name__ == "__main__":
    unittest.main()
