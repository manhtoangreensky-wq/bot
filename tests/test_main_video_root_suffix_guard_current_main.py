"""The registered Menu handler must reject stale Video-menu suffixes."""

import unittest
from types import SimpleNamespace

from tests.test_admin_root_menu_callback_single_ack import (
    _Query,
    _load_functions,
    _main_menu_dependencies,
    _run_no_io,
)


class MainVideoRootSuffixGuardTests(unittest.TestCase):
    def test_unproduced_video_suffix_alerts_before_ack_cleanup_or_render(self):
        effects = []
        dependencies = _main_menu_dependencies(False, effects)
        dependencies.update({
            "time": SimpleNamespace(perf_counter=lambda: 1.0),
            "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
        })
        namespace = _load_functions("handle_menu_callback", **dependencies)
        query = _Query(991004, "menu|main_video|unsupported_context")
        _run_no_io(namespace["handle_menu_callback"](
            SimpleNamespace(callback_query=query),
            SimpleNamespace(user_data={}),
        ))
        self.assertEqual(1, len(query.answers))
        self.assertEqual({"show_alert": True}, query.answers[0][1])
        self.assertIn("hết phiên", query.answers[0][0][0])
        self.assertEqual([], query.edits)
        self.assertEqual([], effects)


if __name__ == "__main__":
    unittest.main()
