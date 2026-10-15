"""The Menu handler must preserve the valid Free Hub memory origin only."""

import unittest
from types import SimpleNamespace

from tests.test_admin_root_menu_callback_single_ack import (
    _Button,
    _Markup,
    _Query,
    _load_functions,
    _main_menu_dependencies,
    _run_no_io,
)


def _namespace():
    effects = []
    dependencies = _main_menu_dependencies(False, effects)
    dependencies.update({
        "time": SimpleNamespace(perf_counter=lambda: 1.0),
        "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
        "localized_menu_content": lambda *_args: (
            "memory screen",
            _Markup([[_Button("⬅️ Main", "menu|main")]]),
        ),
    })
    return _load_functions("handle_menu_callback", **dependencies), effects


def _dispatch(namespace, callback):
    query = _Query(991003, callback)
    context = SimpleNamespace(user_data={})
    _run_no_io(namespace["handle_menu_callback"](
        SimpleNamespace(callback_query=query), context,
    ))
    return query, context


class MainMemoryRootSuffixGuardTests(unittest.TestCase):
    def test_exact_memory_root_remains_valid(self):
        namespace, _effects = _namespace()
        query, _context = _dispatch(namespace, "menu|main_memory")
        self.assertEqual([((), {})], query.answers)
        self.assertEqual(1, len(query.edits))

    def test_freehub_memory_origin_remains_valid(self):
        namespace, _effects = _namespace()
        query, context = _dispatch(namespace, "menu|main_memory|freehub")
        self.assertEqual([((), {})], query.answers)
        self.assertEqual(1, len(query.edits))
        callbacks = [
            button.callback_data
            for row in query.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertIn("freehub|main", callbacks)
        self.assertEqual("freehub", context.user_data.get("memory_nav_origin"))

    def test_unproduced_memory_suffix_alerts_before_ack_cleanup_or_render(self):
        namespace, effects = _namespace()
        query, context = _dispatch(namespace, "menu|main_memory|unsupported_context")
        self.assertEqual(1, len(query.answers))
        self.assertEqual({"show_alert": True}, query.answers[0][1])
        self.assertIn("hết phiên", query.answers[0][0][0])
        self.assertEqual([], query.edits)
        self.assertEqual([], effects)
        self.assertEqual({}, context.user_data)


if __name__ == "__main__":
    unittest.main()
