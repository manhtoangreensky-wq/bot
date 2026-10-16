"""The registered Menu handler must reject a stale main-root suffix."""

import unittest
from types import SimpleNamespace

from tests.test_admin_root_menu_callback_single_ack import (
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
    })
    return _load_functions("handle_menu_callback", **dependencies), effects


def _dispatch(namespace, callback):
    query = _Query(991001, callback)
    _run_no_io(namespace["handle_menu_callback"](
        SimpleNamespace(callback_query=query),
        SimpleNamespace(user_data={}),
    ))
    return query


class MainRootSuffixGuardTests(unittest.TestCase):
    def test_exact_main_still_renders_once(self):
        namespace, _effects = _namespace()
        query = _dispatch(namespace, "menu|main")
        self.assertEqual([((), {})], query.answers)
        self.assertEqual(1, len(query.edits))

    def test_unproduced_main_suffix_alerts_before_ack_cleanup_or_render(self):
        namespace, effects = _namespace()
        query = _dispatch(namespace, "menu|main|unsupported_context")
        self.assertEqual(1, len(query.answers))
        self.assertEqual({"show_alert": True}, query.answers[0][1])
        self.assertIn("hết phiên", query.answers[0][0][0])
        self.assertEqual([], query.edits)
        self.assertEqual([], effects)


if __name__ == "__main__":
    unittest.main()
